"""Track protection across editing, history, persistence and source lifecycle."""
from __future__ import annotations

import copy
import io

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.render import _render_input_fingerprint, build_filter_graph
from cutroom.sequence import editor_sequence_snapshot
from cutroom.track_locks import TrackLockedError
from test_sequence_editing import project
from test_source_tracks_api import track_api, post  # noqa: F401


def lock(value, slot="A", locked=True):
    return apply_manual_edit(value, {"action": "set_track_lock", "slot": slot, "locked": locked})


def test_lock_does_not_materialize_clips_touch_history_or_change_rendering():
    value = project()
    before = copy.deepcopy(value)
    graph = build_filter_graph(value, 160, 100)
    fingerprint = _render_input_fingerprint(value)
    lock(value)
    assert value == {**before, "manual": {"track_locks": {"A": True}}}
    assert build_filter_graph(value, 160, 100) == graph
    assert _render_input_fingerprint(value) == fingerprint
    assert editor_sequence_snapshot(value) == editor_sequence_snapshot(before)


@pytest.mark.parametrize("payload", [
    {"slot": "C", "locked": True}, {"slot": "a", "locked": True},
    {"slot": "A", "locked": "false"}, {"slot": "A", "locked": 1},
    {"slot": "A"}, {"locked": True},
])
def test_lock_validation_is_atomic(payload):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "set_track_lock", **payload})
    assert value == before


@pytest.mark.parametrize("payload", [
    {"action": "sequence_split", "slot": "A", "time": 2},
    {"action": "sequence_crop", "slot": "A", "start": 0, "end": 2, "x": .3, "y": .5, "zoom": 2},
    {"action": "sequence_speed", "slot": "A", "clip_id": "A:sequence:0:0", "speed": 2},
    {"action": "sequence_move", "slot": "A", "clip_id": "A:sequence:1:0", "start": 0},
    {"action": "sequence_remove_range", "slot": "A", "start": 0, "end": 2},
    {"action": "track_split", "slot": "A", "time": 2},
    {"action": "track_reset", "slot": "A"},
    {"action": "sequence_ripple_delete", "start": 0, "end": 2},
    {"action": "sequence_split_all", "time": 2},
    {"action": "sequence_move_range", "start": 0, "end": 2, "to": 5, "mode": "ripple"},
    {"action": "sequence_duplicate_range", "start": 0, "end": 2, "to": 5},
    {"action": "sequence_insert_linked", "slot": "B", "start": 0, "source_start": 0, "source_end": 2},
    {"action": "sequence_source_remove", "slot": "B", "scope": "edit", "source_start": 0, "source_end": 2},
    {"action": "delete_range", "start": 0, "end": 2},
    {"action": "restore_range", "start": 4, "end": 6},
    {"action": "split", "time": 2},
])
def test_locked_lane_and_cross_lane_changes_reject_atomically(payload):
    value = project()
    lock(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Track A is locked"):
        apply_manual_edit(value, payload)
    assert value == before


@pytest.mark.parametrize("sequence", [False, True])
def test_other_lane_edit_and_undo_redo_preserve_lock(sequence):
    value = project()
    if sequence:
        apply_manual_edit(value, {"action": "sequence_split", "slot": "B", "time": 2})
    lock(value)
    before_a = editor_sequence_snapshot(value)["source_tracks"]["A"]
    apply_manual_edit(value, {"action": "sequence_remove_range", "slot": "B", "start": 0, "end": 1})
    assert editor_sequence_snapshot(value)["source_tracks"]["A"] == before_a
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["track_locks"] == {"A": True}
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["track_locks"] == {"A": True}
    assert editor_sequence_snapshot(value)["source_tracks"]["A"] == before_a


def test_legacy_other_lane_split_and_history_do_not_materialize_or_change_locked_lane():
    value = project()
    lock(value)
    apply_manual_edit(value, {"action": "track_split", "slot": "B", "time": 2})
    assert "A" not in value["manual"]["source_tracks"]
    apply_manual_edit(value, {"action": "undo"})
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["track_locks"] == {"A": True}


@pytest.mark.parametrize("action", ["undo", "redo"])
def test_history_cannot_change_a_track_locked_after_the_edit(action):
    value = project()
    apply_manual_edit(value, {"action": "sequence_split", "slot": "A", "time": 2})
    if action == "redo":
        apply_manual_edit(value, {"action": "undo"})
    lock(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Track A is locked"):
        apply_manual_edit(value, {"action": action})
    assert value == before
    lock(value, locked=False)
    apply_manual_edit(value, {"action": action})
    assert value["manual"]["track_locks"] == {"A": False}


def test_lock_toggling_keeps_existing_redo():
    value = project()
    apply_manual_edit(value, {"action": "sequence_split", "slot": "B", "time": 2})
    apply_manual_edit(value, {"action": "undo"})
    history = copy.deepcopy(value["manual"]["_history"])
    lock(value)
    lock(value, locked=False)
    assert value["manual"]["_history"] == history
    assert value["manual"]["history"] == {"undo_count": 0, "redo_count": 1}


def test_sync_offset_cannot_remap_locked_b():
    value = project()
    lock(value, "B")
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Track B is locked"):
        apply_manual_edit(value, {"action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B", "sync_offset": 1})
    assert value == before


def test_global_layout_and_audio_controls_do_not_unlock_or_block_tracks():
    value = project()
    lock(value)
    apply_manual_edit(value, {"action": "sequence_layout", "start": 0, "end": 2, "layout": "B"})
    apply_manual_edit(value, {"action": "set_audio_mixer", "source_db": -3})
    assert value["manual"]["track_locks"] == {"A": True}


def test_api_lock_persists_with_revision_and_history_rejection(track_api):
    client, store, project_id = track_api
    response = post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    assert response.status_code == 200, response.get_json()
    before = store.load(project_id)
    assert before["manual"]["track_locks"] == {"A": True}
    assert client.get(f"/api/projects/{project_id}").get_json()["project"]["manual"]["track_locks"] == {"A": True}
    response = post(track_api, {"action": "sequence_ripple_delete", "start": 0, "end": 1})
    assert response.status_code == 400, response.get_json()
    assert store.load(project_id) == before
    response = post(track_api, {"action": "set_track_lock", "slot": "A", "locked": False}, revision=before["revision"] - 1)
    assert response.status_code == 409
    assert store.load(project_id) == before
    response = client.post(f"/api/projects/{project_id}/manual/edit", json={"action": "set_track_lock", "slot": "A", "locked": False})
    assert response.status_code == 400
    assert store.load(project_id) == before


@pytest.mark.parametrize("payload", [
    {"manual": {"crop": {"A": {"zoom": 2}}}},
    {"manual": {"cuts": [{"start": 0, "end": 2}]}},
    {"manual": {"keep_ranges": [{"start": 0, "end": 2}]}},
])
def test_patch_cannot_bypass_track_protection(track_api, payload):
    client, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    before = store.load(project_id)
    response = client.patch(f"/api/projects/{project_id}", json=payload)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "track_locked"
    assert store.load(project_id) == before


def test_other_lane_crop_and_export_settings_remain_editable(track_api):
    client, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    response = client.patch(f"/api/projects/{project_id}", json={"manual": {"crop": {"B": {"zoom": 2}}}, "settings": {"fps": 60}})
    assert response.status_code == 200, response.get_json()
    assert store.load(project_id)["manual"]["track_locks"] == {"A": True}


@pytest.mark.parametrize("slot", ["A", "B"])
def test_source_remove_or_replace_cannot_clear_locked_shared_draft(track_api, slot):
    client, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    before = store.load(project_id)
    response = client.delete(f"/api/projects/{project_id}/sources/{slot}")
    assert response.status_code == 409, response.get_json()
    assert store.load(project_id) == before
    response = client.post(f"/api/projects/{project_id}/sources/{slot}", data={"file": (io.BytesIO(b"unchanged"), "new.mp4")})
    assert response.status_code == 409, response.get_json()
    assert store.load(project_id) == before
    assert not list((store.project_dir(project_id) / "media").iterdir())


@pytest.mark.parametrize("route,payload", [("director", {"goal": "youtube"}), ("director/refine", {"command": "shorter"})])
def test_rebuild_and_refine_reject_before_job_or_settings_changes(track_api, route, payload):
    client, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    before = store.load(project_id)
    response = client.post(f"/api/projects/{project_id}/{route}", json=payload)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "track_locked"
    assert store.load(project_id) == before


def test_store_guard_checks_existing_lock_even_if_candidate_unlocks(track_api):
    _, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    before = store.load(project_id)
    candidate = copy.deepcopy(before)
    candidate["manual"]["track_locks"]["A"] = False
    candidate["sources"]["A"]["duration"] = 1
    with pytest.raises(TrackLockedError):
        store.save(candidate)
    assert store.load(project_id) == before
    candidate = copy.deepcopy(before)
    candidate["manual"].pop("track_locks")
    with pytest.raises(TrackLockedError):
        store.save(candidate)
    assert store.load(project_id) == before


def test_proxy_preparation_can_finish_on_locked_source(track_api):
    _, store, project_id = track_api
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    def prepared(value):
        value["sources"]["A"].update(preparation="ready", thumbnail_names=["thumb.jpg"], preview_relative_path="cache/proxy-A.mp4", embedded_camera_detected=True)
    result = store.update(project_id, prepared)
    assert result["manual"]["track_locks"] == {"A": True}
    assert result["sources"]["A"]["preparation"] == "ready"


def test_save_cannot_rewrite_hidden_malformed_clips_on_locked_lane(track_api):
    _, store, project_id = track_api
    value = store.load(project_id)
    value["manual"]["source_tracks"] = {"A": [{"id": "legacy", "start": 0, "end": 99, "source_start": 0}]}
    store.save(value)
    post(track_api, {"action": "set_track_lock", "slot": "A", "locked": True})
    before = store.load(project_id)
    candidate = copy.deepcopy(before)
    candidate["manual"]["source_tracks"]["A"] = []
    with pytest.raises(TrackLockedError):
        store.save(candidate)
    assert store.load(project_id) == before
