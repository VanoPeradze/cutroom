"""Exercise source edits through Flask's actual JSON/revision/persistence path."""
from __future__ import annotations

import pytest

from cutroom.config import load_settings
from cutroom.source_tracks import TRACK_ACTIONS, source_track_clips
from server import SOURCE_TRACK_EDIT_FIELDS, create_app


@pytest.fixture
def track_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    settings.raw["host"] = "127.0.0.1"
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("Independent source API fixture")
    value["sources"] = {
        "A": {"duration": 20.0, "has_audio": True, "relative_path": "media/source-A.mp4"},
        "B": {"duration": 12.0, "has_audio": True, "relative_path": "media/source-B.mp4"},
    }
    value["analysis"] = {"sync": {"offset": 0}}
    value["draft"] = {
        "cuts": [], "keep_ranges": [{"start": 0, "end": 20}],
        "camera_plan": [{"start": 0, "end": 20, "camera": "stacked"}],
        "output_duration": 20.0, "removed_duration": 0,
    }
    store.save(value)
    yield app.test_client(), store, value["id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def post(track_api, payload, *, revision=None):
    client, store, project_id = track_api
    if revision is None:
        revision = store.load(project_id)["revision"]
    return client.post(f"/api/projects/{project_id}/manual/edit", json={**payload, "expected_revision": revision})


def edit(track_api, action, **kwargs):
    response = post(track_api, {"action": f"track_{action}", "slot": "B", **kwargs})
    assert response.status_code == 200, response.get_json()
    result = response.get_json()["project"]
    assert "_history" not in result["manual"]
    assert result["draft"]["keep_ranges"] == [{"start": 0, "end": 20}]
    assert result["draft"]["output_duration"] == 20
    return result


def geometry(value, slot="B"):
    return [(clip["start"], clip["end"], clip["source_start"]) for clip in source_track_clips(value, slot)]


def test_route_declares_every_model_track_action():
    assert SOURCE_TRACK_EDIT_FIELDS.keys() == TRACK_ACTIONS


def test_flask_source_clip_split_remove_move_trim_reset_and_undo_roundtrip(track_api):
    result = edit(track_api, "split", time=5)
    assert geometry(result) == [(0, 5, 0), (5, 12, 5)]
    assert geometry(result, "A") == [(0, 20, 0)]
    result = edit(track_api, "remove_range", start=5, end=12)
    assert geometry(result) == [(0, 5, 0)]
    result = edit(track_api, "move", clip_id="B:base", start=7)
    assert geometry(result) == [(7, 12, 0)]
    result = edit(track_api, "trim", clip_id="B:base", start=8, end=11, source_start=1)
    assert geometry(result) == [(8, 11, 1)]
    result = edit(track_api, "reset")
    assert "source_tracks" not in result["manual"]
    assert geometry(result) == [(0, 12, 0)]
    undone = post(track_api, {"action": "undo"})
    assert undone.status_code == 200, undone.get_json()
    assert geometry(undone.get_json()["project"]) == [(8, 11, 1)]
    redone = post(track_api, {"action": "redo"})
    assert redone.status_code == 200, redone.get_json()
    assert geometry(redone.get_json()["project"]) == [(0, 12, 0)]
    _, store, project_id = track_api
    saved = store.load(project_id)
    assert "source_tracks" not in saved["manual"]
    assert saved["manual"]["history"] == {"undo_count": 5, "redo_count": 0}


def test_flask_drag_remove_and_restore_accept_slot_and_preserve_a(track_api):
    result = edit(track_api, "remove_range", start=1, end=3)
    assert geometry(result) == [(0, 1, 0), (3, 12, 3)]
    assert geometry(result, "A") == [(0, 20, 0)]
    result = edit(track_api, "restore_range", start=1, end=3)
    assert geometry(result) == [(0, 1, 0), (1, 3, 1), (3, 12, 3)]
    assert geometry(result, "A") == [(0, 20, 0)]


def test_flask_source_a_edits_are_not_routed_to_b(track_api):
    response = post(track_api, {"action": "track_remove_range", "slot": "A", "start": 1, "end": 3})
    assert response.status_code == 200, response.get_json()
    value = response.get_json()["project"]
    assert geometry(value, "A") == [(0, 1, 0), (3, 20, 3)]
    assert geometry(value) == [(0, 12, 0)]
    assert set(value["manual"]["source_tracks"]) == {"A"}


@pytest.mark.parametrize("payload,error", [
    ({"action": "track_split", "slot": "B"}, "invalid_field"),
    ({"action": "track_move", "slot": "B", "start": 1}, "invalid_field"),
    ({"action": "track_trim", "slot": "B", "clip_id": "B:base", "start": 1, "end": 4}, "invalid_field"),
    ({"action": "track_reset", "slot": "B", "start": 1}, "unknown_field"),
    ({"action": "track_split", "slot": "B", "time": 5, "layout": "screen"}, "unknown_field"),
    ({"action": "split", "slot": "B", "time": 5}, "unknown_field"),
    ({"action": "track_split", "slot": 1, "time": 5}, "invalid_field"),
    ({"action": "track_move", "slot": "B", "clip_id": [], "start": 1}, "invalid_field"),
    ({"action": "track_remove_range", "slot": "C", "start": 1, "end": 3}, "invalid_manual_edit"),
    ({"action": "track_remove_range", "slot": "B", "start": 1, "end": 21}, "invalid_manual_edit"),
    ({"action": "track_trim", "slot": "B", "clip_id": "B:base", "start": 1, "end": 4, "source_start": -1}, "invalid_manual_edit"),
    ({"action": "track_trim", "slot": "B", "clip_id": "B:base", "start": 1, "end": 4, "source_start": True}, "invalid_manual_edit"),
])
def test_flask_track_validation_rejects_without_saving_or_consuming_history(track_api, payload, error):
    _, store, project_id = track_api
    before = store.load(project_id)
    response = post(track_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == error
    assert store.load(project_id) == before


def test_flask_track_revision_conflict_does_not_overwrite_later_edit(track_api):
    _, store, project_id = track_api
    revision = store.load(project_id)["revision"]
    edit(track_api, "split", time=5)
    before = store.load(project_id)
    response = post(track_api, {"action": "track_remove_range", "slot": "B", "start": 1, "end": 3}, revision=revision)
    assert response.status_code == 409
    assert response.get_json()["error"] == "revision_conflict"
    assert store.load(project_id) == before


def test_flask_noop_preserves_redo_history(track_api):
    edit(track_api, "split", time=5)
    undo = post(track_api, {"action": "undo"})
    assert undo.status_code == 200
    result = edit(track_api, "reset")
    assert result["manual"]["history"] == {"undo_count": 0, "redo_count": 1}
    redo = post(track_api, {"action": "redo"})
    assert redo.status_code == 200
    assert geometry(redo.get_json()["project"]) == [(0, 5, 0), (5, 12, 5)]


def test_flask_edited_b_sync_guard_is_atomic(track_api):
    _, store, project_id = track_api
    edit(track_api, "split", time=5)
    before = store.load(project_id)
    response = post(track_api, {
        "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
        "primary_role": "screen", "audio_slot": "A", "sync_offset": 2,
    })
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_manual_edit"
    assert "Reset source B" in response.get_json()["message"]
    assert store.load(project_id) == before


def test_editor_sequence_is_read_only_and_virtual_ids_work_in_first_api_move(track_api):
    client, store, project_id = track_api
    before = store.load(project_id)
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    virtual = response.get_json()["project"]["editor_sequence"]
    assert virtual["active"] is False
    assert virtual["duration"] == 20
    assert store.load(project_id) == before
    clip_id = virtual["source_tracks"]["B"][0]["id"]
    moved = post(track_api, {"action": "sequence_move", "slot": "B", "clip_id": clip_id, "start": 22})
    assert moved.status_code == 200, moved.get_json()
    result = moved.get_json()["project"]
    assert result["editor_sequence"]["active"] is True
    assert result["editor_sequence"]["duration"] == 34
    assert geometry(result) == [(22, 34, 0)]
    assert result["sources"]["A"]["duration"] == 20
    assert result["draft"]["keep_ranges"] == before["draft"]["keep_ranges"]
    assert store.load(project_id)["analysis"] == before["analysis"]
    assert "_history" not in result["manual"]
    undo = post(track_api, {"action": "undo"})
    assert undo.status_code == 200
    assert undo.get_json()["project"]["editor_sequence"]["active"] is False
    assert "sequence" not in store.load(project_id)["manual"]


@pytest.mark.parametrize("action,fields", [
    ("sequence_split", {"slot": "B", "time": 4}),
    ("sequence_remove_range", {"slot": "B", "start": 1, "end": 3}),
    ("sequence_trim", {"slot": "B", "clip_id": "B:sequence:0:0", "start": 1, "end": 4, "source_start": 2}),
    ("sequence_place", {"slot": "B", "clip_id": "B:sequence:0:0", "start": 22}),
    ("sequence_duplicate", {"slot": "B", "clip_id": "B:sequence:0:0", "start": 22}),
    ("sequence_insert", {"slot": "B", "start": 3, "source_start": 4, "source_end": 6}),
    ("sequence_layout", {"start": 1, "end": 3, "layout": "pip"}),
    ("sequence_layout", {"start": 1, "end": 3, "layout": "auto"}),
])
def test_sequence_action_fields_are_accepted_and_reset_is_undoable(track_api, action, fields):
    response = post(track_api, {"action": action, **fields})
    assert response.status_code == 200, response.get_json()
    state = response.get_json()["project"]
    assert state["editor_sequence"]["active"] is True
    reset = post(track_api, {"action": "sequence_reset"})
    assert reset.status_code == 200, reset.get_json()
    assert reset.get_json()["project"]["editor_sequence"]["active"] is False
    undo = post(track_api, {"action": "undo"})
    assert undo.status_code == 200
    restored = undo.get_json()["project"]
    assert restored["manual"]["source_tracks"] == state["manual"]["source_tracks"]
    assert restored["manual"]["sequence"] == state["manual"]["sequence"]


def test_sequence_api_requires_revision_and_rejects_unknown_fields_without_materializing(track_api):
    client, store, project_id = track_api
    before = store.load(project_id)
    missing = client.post(f"/api/projects/{project_id}/manual/edit", json={"action": "sequence_split", "slot": "B", "time": 4})
    assert missing.status_code == 400
    assert "expected_revision" in missing.get_json()["message"]
    unknown = post(track_api, {"action": "sequence_move", "slot": "B", "clip_id": "B:sequence:0:0", "start": 1, "ripple": True})
    assert unknown.status_code == 400
    assert unknown.get_json()["error"] == "unknown_field"
    assert store.load(project_id) == before
