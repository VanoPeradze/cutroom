"""Timeline bindings are detached public metadata, including on safe failures."""
from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from cutroom.config import load_settings
from cutroom.sequence import editor_sequence_snapshot
from cutroom.source_tracks import TimelineVersionError
from cutroom.timeline_bindings import TimelineBindingError
import server


ASSET = "asset_" + "d" * 32
SAFE_BINDING_ERROR = {
    "error": "The saved timeline cannot be addressed safely. Review your clips or restore an earlier edit.",
    "id_actions": [],
}
SAFE_EDITOR_ERROR = {
    "error": "The saved timeline is invalid. Review your clips or restore an earlier edit.",
}


@pytest.fixture
def bindings_api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = server.create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    project = store.create("Synthetic timeline bindings API")
    source = {"duration": 3, "width": 320, "height": 180, "fps": 30, "has_audio": True}
    project["sources"] = {
        "A": {**source, "generation": "source-A", "relative_path": "media/private_source_sentinel.mp4",
              "preview_relative_path": "media/private_preview_sentinel.mp4"},
        "B": {**source, "generation": "source-B", "relative_path": "media/B.mp4"},
    }
    project["draft"] = {
        "keep_ranges": [{"start": 0, "end": 3}], "cuts": [], "output_duration": 3,
        "camera_plan": [{"start": 0, "end": 3, "camera": "A"}],
        # Existing v1 Undo restores this array even in old drafts that omit it.
        # Seed its normal default so exact content comparisons remain useful.
        "edit_points": [],
        "status": "ready",
    }
    project["analysis"] = {"transcript": {"language": "en", "segments": [
        {"id": "spoken", "start": 0, "end": 3, "text": "A complete synthetic thought."},
    ]}}
    project["assets"] = {ASSET: {
        "id": ASSET, "name": "clip.mp4", "kind": "video", "status": "ready", "duration": 3,
        "width": 160, "height": 90, "fps": 30, "has_audio": True,
        "path": f"media/assets/{ASSET}/private_asset_sentinel.mp4",
        "internal_path": "private_internal_sentinel",
    }}
    project["manual"] = {
        "cuts": [], "keeps": [], "camera_overrides": [],
        "source_tracks": {"A": [{"id": "clip-A", "start": 0, "end": 3, "source_start": 0,
                                    "caption_origin": "private_caption_sentinel"}]},
        "media_clips": [{"id": "library-one", "asset_id": ASSET, "start": 0, "end": 1,
                         "source_start": 0, "audio_enabled": True, "role": "voice"}],
    }
    store.save(project)
    yield app, app.test_client(), store, project["id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def get_project(fixture):
    _, client, _, project_id = fixture
    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200, response.get_json()
    return response, response.get_json()["project"]


def test_get_advertises_revision_scoped_bindings_without_saving_or_leaking_paths(bindings_api):
    _, _, store, project_id = bindings_api
    before = store.state_path(project_id).read_bytes()
    response, public = get_project(bindings_api)
    bindings = public["timeline_bindings"]
    assert bindings["version"] == 1 and bindings["clock"] == "edit"
    assert bindings["revision"] == public["revision"] == store.load(project_id)["revision"]
    assert bindings["selection_scope"] == "project_revision"
    assert [row["legacy_slot"] for row in bindings["tracks"]] == ["A", "B"]
    assert any(row["collection"] == "library" and row["id"] == "library-one" for row in bindings["clips"])
    encoded = response.get_data(as_text=True)
    assert not any(value in encoded for value in (
        "private_source_sentinel", "private_preview_sentinel", "private_asset_sentinel",
        "private_internal_sentinel", "private_caption_sentinel",
    ))
    assert "relative_path" not in json.dumps(bindings) and "caption_origin" not in json.dumps(bindings)
    assert store.state_path(project_id).read_bytes() == before


def test_public_projection_and_repeated_gets_are_detached_from_saved_project(bindings_api):
    _, _, store, project_id = bindings_api
    original = store.load(project_id)
    before = copy.deepcopy(original)
    first = server._public_project(original)
    first["timeline_bindings"]["tracks"][0]["id"] = "foreign-id"
    first["timeline_bindings"]["clips"][0]["state"]["start"] = 99
    first["timeline_bindings"]["sources"]["primary:A:source-A"]["generation"] = "foreign-generation"
    assert original == before
    _, second = get_project(bindings_api)
    _, third = get_project(bindings_api)
    assert second == third
    assert second["timeline_bindings"]["tracks"][0]["id"] == f"track:{project_id}:A"
    assert second["timeline_bindings"]["sources"]["primary:A:source-A"]["generation"] == "source-A"
    assert store.load(project_id) == before


def test_public_projection_reuses_internal_snapshot_before_media_path_redaction(bindings_api, monkeypatch):
    _, _, store, project_id = bindings_api
    build = server.build_timeline_bindings
    captured = {}

    def observe(project, *, editor_sequence=None, input_inventory=None):
        captured["snapshot"] = copy.deepcopy(editor_sequence)
        captured["asset_path"] = project["assets"][ASSET]["path"]
        captured["source_path"] = project["sources"]["A"]["relative_path"]
        return build(project, editor_sequence=editor_sequence, input_inventory=input_inventory)

    monkeypatch.setattr(server, "build_timeline_bindings", observe)
    before = store.state_path(project_id).read_bytes()
    _, public = get_project(bindings_api)
    assert captured["snapshot"] == public["editor_sequence"]
    assert captured["snapshot"] is not None
    assert captured["asset_path"].endswith("private_asset_sentinel.mp4")
    assert captured["source_path"].endswith("private_source_sentinel.mp4")
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("private_detail", [
    "C:/private/recording.mov and traceback sentinel_one",
    "different private asset path sentinel_two",
])
def test_binding_failure_get_has_constant_safe_error_without_partial_editable_addresses(bindings_api, monkeypatch, private_detail):
    _, _, store, project_id = bindings_api

    def fail(*_args, **_kwargs):
        raise TimelineBindingError(private_detail)

    monkeypatch.setattr(server, "build_timeline_bindings", fail)
    before = store.state_path(project_id).read_bytes()
    response, public = get_project(bindings_api)
    assert public["timeline_bindings"] == SAFE_BINDING_ERROR
    assert "tracks" not in public["timeline_bindings"] and "sources" not in public["timeline_bindings"]
    assert "private" not in response.get_data(as_text=True)
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("version", [2, True, "1", 1.0])
def test_unknown_authoritative_sequence_version_get_is_openable_without_legacy_fallback(bindings_api, version):
    _, _, store, project_id = bindings_api
    # Simulate an opaque project written by a future application version.
    # Current writers must reject this version rather than introducing it.
    future = store.load(project_id)
    future["manual"]["sequence"] = {
        "version": version, "duration": 99, "camera_plan": [],
    }
    store.state_path(project_id).write_text(json.dumps(future), encoding="utf-8")
    before = store.state_path(project_id).read_bytes()
    _, public = get_project(bindings_api)
    assert public["timeline_bindings"] == SAFE_BINDING_ERROR
    assert public["editor_sequence"] == SAFE_EDITOR_ERROR
    assert "source_tracks" not in public["editor_sequence"]
    assert public["manual"]["sequence"]["version"] == version
    assert store.state_path(project_id).read_bytes() == before


def test_project_without_draft_get_has_no_invented_bindings_or_editor_footage(bindings_api):
    _, _, store, project_id = bindings_api
    store.update(project_id, lambda project: project.update(draft=None))
    before = store.state_path(project_id).read_bytes()
    _, public = get_project(bindings_api)
    assert public["timeline_bindings"] is None and public["editor_sequence"] is None
    assert store.state_path(project_id).read_bytes() == before


def alias_payload(fixture, action="sequence_split", *, slot="A", **fields):
    _, public = get_project(fixture)
    bindings = public["timeline_bindings"]
    lane = next(row for row in bindings["tracks"] if row["legacy_slot"] == slot)
    clip = next(row for row in bindings["clips"] if row["track_id"] == lane["id"])
    payload = {"action": action, "track_id": lane["id"], "source_ref": lane["source_ref"],
               "expected_revision": public["revision"]}
    if action == "sequence_split":
        payload["time"] = 1
    elif action == "sequence_trim":
        payload.update(clip_id=clip["id"], start=0, end=2, source_start=0)
    elif action == "sequence_speed":
        payload.update(clip_id=clip["id"], speed=0.5)
    payload.update(fields)
    return payload


def post_edit(fixture, payload):
    _, client, _, project_id = fixture
    return client.post(f"/api/projects/{project_id}/manual/edit", json=payload)


def immutable_sections(project):
    # The existing editor timestamps accepted edits and restores old optional
    # draft keys as None during Undo. Neither changes the AI-selected content.
    draft = {key: copy.deepcopy(value) for key, value in (project.get("draft") or {}).items()
             if key not in {"edited_at", "status"} and value is not None}
    return copy.deepcopy({**{key: project.get(key) for key in ("sources", "analysis", "assets")},
                          "draft_content": draft, "media_clips": project.get("manual", {}).get("media_clips")})


def manual_without_history(project):
    return {key: copy.deepcopy(value) for key, value in project["manual"].items() if key not in {"history", "_history"}}


def semantic_snapshot(snapshot):
    value = copy.deepcopy(snapshot)
    for clips in value["source_tracks"].values():
        for clip in clips:
            clip.pop("id", None)
            clip.pop("caption_origin", None)
    return value


@pytest.mark.parametrize("action", ["sequence_split", "sequence_trim", "sequence_speed"])
def test_alias_edits_preserve_other_lane_and_originals_with_exact_undo_redo_and_slot_parity(bindings_api, action):
    _, _, store, project_id = bindings_api
    before = store.load(project_id)
    before_view = editor_sequence_snapshot(before)
    payload = alias_payload(bindings_api, action)
    response = post_edit(bindings_api, payload)
    assert response.status_code == 200, response.get_json()
    public = response.get_json()["project"]
    assert public["timeline_bindings"]["id_actions"] == ["sequence_split", "sequence_trim", "sequence_speed"]
    after = store.load(project_id)
    after_view = editor_sequence_snapshot(after)
    assert immutable_sections(after) == immutable_sections(before)
    assert after_view["source_tracks"]["B"] == before_view["source_tracks"]["B"]
    assert after["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    clips = after_view["source_tracks"]["A"]
    geometry = [(row["start"], row["end"], row["source_start"]) for row in clips]
    if action == "sequence_split":
        assert geometry == [(0, 1, 0), (1, 3, 1)]
    elif action == "sequence_trim":
        assert geometry == [(0, 2, 0)]
    else:
        assert geometry == [(0, 3, 0)]
        assert clips[0]["video_speed"] == 0.5 and clips[0]["video_source_start"] == 0

    undo = post_edit(bindings_api, {"action": "undo", "expected_revision": after["revision"]})
    assert undo.status_code == 200, undo.get_json()
    undone = store.load(project_id)
    assert editor_sequence_snapshot(undone) == before_view
    assert manual_without_history(undone) == manual_without_history(before)
    assert immutable_sections(undone) == immutable_sections(before)
    redo = post_edit(bindings_api, {"action": "redo", "expected_revision": undone["revision"]})
    assert redo.status_code == 200, redo.get_json()
    redone = store.load(project_id)
    assert editor_sequence_snapshot(redone) == after_view
    assert manual_without_history(redone) == manual_without_history(after)
    assert immutable_sections(redone) == immutable_sections(before)

    # The ordinary slot route keeps the same operation semantics. Only newly
    # generated split IDs/private ancestry may differ after a fresh operation.
    undo_again = post_edit(bindings_api, {"action": "undo", "expected_revision": redone["revision"]})
    assert undo_again.status_code == 200, undo_again.get_json()
    legacy = {key: value for key, value in payload.items() if key not in {"track_id", "source_ref"}}
    legacy.update(slot="A", expected_revision=store.load(project_id)["revision"])
    legacy_response = post_edit(bindings_api, legacy)
    assert legacy_response.status_code == 200, legacy_response.get_json()
    assert semantic_snapshot(editor_sequence_snapshot(store.load(project_id))) == semantic_snapshot(after_view)


def test_alias_can_include_an_agreeing_slot_without_changing_binding_meaning(bindings_api):
    payload = alias_payload(bindings_api, slot="A")
    payload["slot"] = "A"
    response = post_edit(bindings_api, payload)
    assert response.status_code == 200, response.get_json()
    _, _, store, project_id = bindings_api
    assert len(editor_sequence_snapshot(store.load(project_id))["source_tracks"]["A"]) == 2


def test_same_clip_id_in_two_lanes_is_resolved_only_with_the_advertised_track(bindings_api):
    _, _, store, project_id = bindings_api
    def collide(project):
        project["manual"]["sequence"] = {"version": 1, "duration": 3,
                                            "camera_plan": [{"start": 0, "end": 3, "camera": "A"}]}
        project["manual"]["source_tracks"] = {slot: [{"id": "same-clip", "start": 0, "end": 3, "source_start": 0}]
                                                for slot in ("A", "B")}
    store.update(project_id, collide)
    before = editor_sequence_snapshot(store.load(project_id))
    payload = alias_payload(bindings_api, "sequence_speed", slot="B")
    assert payload["clip_id"] == "same-clip"
    response = post_edit(bindings_api, payload)
    assert response.status_code == 200, response.get_json()
    after = editor_sequence_snapshot(store.load(project_id))
    assert after["source_tracks"]["A"] == before["source_tracks"]["A"]
    assert after["source_tracks"]["B"][0]["video_speed"] == 0.5


@pytest.mark.parametrize("missing", ["track_id", "source_ref", "expected_revision"])
def test_alias_fields_and_revision_must_be_paired_before_any_state_change(bindings_api, missing):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    del payload[missing]
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_field"
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("field,invalid", [
    ("track_id", ""), ("track_id", True), ("track_id", "x" * 257), ("track_id", []),
    ("source_ref", " "), ("source_ref", 1), ("source_ref", "x" * 257), ("source_ref", {}),
    ("expected_revision", None), ("expected_revision", True), ("expected_revision", 0),
    ("expected_revision", "1"), ("expected_revision", 1.0),
])
def test_malformed_alias_or_revision_is_rejected_atomically(bindings_api, field, invalid):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    payload[field] = invalid
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_field"
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("patch", [
    {"track_id": "track:project_ffffffffffff:A"},
    {"track_id": "track:project_123456789abc:C"},
    {"track_id": "asset:" + ASSET},
    {"track_id": "C:/private/track"},
    {"source_ref": "asset:" + ASSET},
    {"source_ref": "primary:B:source-B"},
    {"slot": "B"},
])
def test_foreign_or_mismatched_identity_cannot_select_another_lane_or_library_asset(bindings_api, patch):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    payload.update(patch)
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_timeline_binding"
    assert "C:/private" not in response.get_data(as_text=True)
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("generation", ["replacement-A", None, "", "missing"])
def test_generation_change_or_unversioned_source_cannot_reuse_an_old_alias_at_current_revision(bindings_api, generation):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    def replace(project):
        if generation == "missing":
            project["sources"]["A"].pop("generation")
        else:
            project["sources"]["A"]["generation"] = generation
    current = store.update(project_id, replace)
    payload["expected_revision"] = current["revision"]
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "source_binding_conflict"
    assert store.state_path(project_id).read_bytes() == before


def test_stale_revision_wins_before_alias_resolution_or_edit_materialization(bindings_api, monkeypatch):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    store.update(project_id, lambda project: project.update(name="A newer saved project"))
    before = store.state_path(project_id).read_bytes()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("A stale alias must fail before resolution or mutation")
    monkeypatch.setattr(server, "primary_track_binding", forbidden)
    monkeypatch.setattr(server, "apply_manual_edit", forbidden)
    response = post_edit(bindings_api, payload)
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "revision_conflict"
    assert store.state_path(project_id).read_bytes() == before


def test_locked_lane_rejects_alias_after_staging_without_consuming_history(bindings_api):
    _, _, store, project_id = bindings_api
    store.update(project_id, lambda project: project["manual"].update(track_locks={"A": True}))
    payload = alias_payload(bindings_api)
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_manual_edit"
    assert "Track A is locked" in response.get_json()["message"]
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("payload", [
    {"action": "sequence_reset"},
    {"action": "sequence_split_all", "time": 1},
    {"action": "sequence_move_range", "start": 0, "end": 1, "to": 1},
    {"action": "sequence_layout", "start": 0, "end": 1, "layout": "A"},
    {"action": "undo"},
])
def test_alias_fields_do_not_expand_global_or_linked_action_api(bindings_api, payload):
    _, _, store, project_id = bindings_api
    address = alias_payload(bindings_api)
    payload = {**payload, **{key: address[key] for key in ("track_id", "source_ref", "expected_revision")}}
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "unknown_field"
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("time", [0, 3])
def test_alias_split_at_existing_edge_keeps_noop_history_and_does_not_materialize(bindings_api, time):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api, time=time)
    before = store.load(project_id)
    response = post_edit(bindings_api, payload)
    assert response.status_code == 200, response.get_json()
    after = store.load(project_id)
    assert after["manual"] == before["manual"]
    assert "sequence" not in after["manual"]
    assert immutable_sections(after) == immutable_sections(before)
    assert after["revision"] >= before["revision"]


@pytest.mark.parametrize("action,invalid", [
    ("sequence_speed", {"speed": 0}),
    ("sequence_trim", {"start": 0, "end": 2, "source_start": 3}),
])
def test_aliases_retain_existing_picture_and_source_bounds_validation(bindings_api, action, invalid):
    _, _, store, project_id = bindings_api
    payload = alias_payload(bindings_api, action, **invalid)
    before = store.state_path(project_id).read_bytes()
    response = post_edit(bindings_api, payload)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["error"] == "invalid_manual_edit"
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("route", ["legacy_slot_edit", "alias_edit", "patch", "render"])
def test_unknown_sequence_version_rejects_mutation_and_render_admission_before_work(bindings_api, monkeypatch, route):
    app, client, store, project_id = bindings_api
    payload = alias_payload(bindings_api)
    future = store.load(project_id)
    future["manual"]["sequence"] = {"version": 2, "duration": 99, "camera_plan": []}
    store.state_path(project_id).write_text(json.dumps(future), encoding="utf-8")
    before = store.state_path(project_id).read_bytes()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unsupported versions must fail before work or mutation")
    monkeypatch.setattr(server, "apply_manual_edit", forbidden)
    monkeypatch.setattr(server, "ensure_render_storage", forbidden)
    monkeypatch.setattr(server, "render_project", forbidden)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", forbidden)
    if route == "legacy_slot_edit":
        response = post_edit(bindings_api, {"action": "sequence_split", "slot": "A", "time": 1,
                                            "expected_revision": future["revision"]})
    elif route == "alias_edit":
        response = post_edit(bindings_api, payload)
    elif route == "patch":
        response = client.patch(f"/api/projects/{project_id}", json={
            "name": "A changed name", "expected_revision": future["revision"],
        })
    else:
        response = client.post(f"/api/projects/{project_id}/render", json={})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "timeline_version_unsupported"
    assert store.state_path(project_id).read_bytes() == before


def test_store_rejects_future_sequence_candidate_without_rewriting_current_project(bindings_api):
    _, _, store, project_id = bindings_api
    before = store.state_path(project_id).read_bytes()
    candidate = store.load(project_id)
    candidate["manual"]["sequence"] = {"version": 2, "duration": 3, "camera_plan": []}
    with pytest.raises(TimelineVersionError):
        store.save(candidate)
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("writer", ["save", "update", "patch"])
def test_opaque_future_current_project_cannot_be_implicitly_restored_or_written(bindings_api, writer):
    _, _, store, project_id = bindings_api
    future = store.load(project_id)
    future["manual"]["sequence"] = {"version": 2, "duration": 99, "camera_plan": []}
    store.state_path(project_id).write_text(json.dumps(future), encoding="utf-8")
    before = store.state_path(project_id).read_bytes()
    def forbidden(_project):
        raise AssertionError("Unsupported current state must fail before a mutator can clear its version")
    with pytest.raises(TimelineVersionError):
        if writer == "save":
            restored = copy.deepcopy(future)
            restored["manual"].pop("sequence")
            store.save(restored)
        elif writer == "update":
            store.update(project_id, forbidden)
        else:
            store.patch(project_id, {"name": "An attempted implicit write"})
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("route", ["source_preflight", "asset_preflight", "multipart_source", "chunk_finalize", "source_delete"])
def test_future_sequence_blocks_source_lifecycle_before_admission_probe_copy_or_job_cancel(bindings_api, monkeypatch, route):
    app, client, store, project_id = bindings_api
    future = store.load(project_id)
    root = store.project_dir(project_id)
    original = root / future["sources"]["A"]["relative_path"]
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"Synthetic original must remain byte-identical")
    original_bytes = original.read_bytes()
    media_names = {path.name for path in original.parent.iterdir()}
    future["manual"]["sequence"] = {"version": 2, "duration": 99, "camera_plan": []}
    store.state_path(project_id).write_text(json.dumps(future), encoding="utf-8")
    before = store.state_path(project_id).read_bytes()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Unknown timeline versions must fail before source lifecycle work")

    with monkeypatch.context() as guarded_patch:
        storage = app.extensions["cutroom_upload_storage"]
        for name in ("admit", "admit_legacy", "begin_finalize"):
            guarded_patch.setattr(storage, name, forbidden)
        for name in ("copy_upload", "probe_media", "_cleanup_old_source"):
            guarded_patch.setattr(server, name, forbidden)
        jobs = app.extensions["cutroom_jobs"]
        guarded_patch.setattr(jobs, "cancel", forbidden)
        guarded_patch.setattr(jobs, "submit", forbidden)
        guarded_patch.setattr(jobs, "active", lambda *_args, **_kwargs: [
            SimpleNamespace(id="existing-preparation", dedupe_key="A:source-A", kind="prepare_source"),
        ])
        if route in {"source_preflight", "asset_preflight"}:
            purpose = "source" if route == "source_preflight" else "asset"
            payload = {"purpose": purpose, "filename": "new.mp4", "size_bytes": 4}
            if purpose == "source":
                payload["slot"] = "A"
            response = client.post(f"/api/projects/{project_id}/uploads/preflight", json=payload)
        elif route == "multipart_source":
            response = client.post(f"/api/projects/{project_id}/sources/A", data={
                "file": (io.BytesIO(b"tiny replacement, never probed"), "new.mp4"),
            }, content_type="multipart/form-data")
        elif route == "chunk_finalize":
            response = client.post(f"/api/projects/{project_id}/sources/A", json={}, headers={
                "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": "f" * 32,
            })
        else:
            response = client.delete(f"/api/projects/{project_id}/sources/A")
        assert response.status_code == 409, response.get_json()
        assert response.get_json()["error"] == "timeline_version_unsupported"
        assert store.state_path(project_id).read_bytes() == before
        assert original.read_bytes() == original_bytes
        assert {path.name for path in original.parent.iterdir()} == media_names
