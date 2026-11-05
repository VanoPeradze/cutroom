"""Append independent ready video without replacing or retiming the A/B edit."""
from __future__ import annotations

import copy
import json
import math

import pytest

import server
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.projects import ProjectStateError, ProjectStore
from cutroom.render import project_caption_items
from cutroom.render_inventory import compile_render_inputs
from cutroom.sequence import editor_sequence_snapshot, materialize_sequence
from cutroom.source_tracks import MAX_SEQUENCE_SECONDS
from cutroom.timeline_bindings import TimelineBindingError, build_timeline_bindings
from test_media_library import ASSET, api as library_api, project as legacy_project


def append_project():
    value = legacy_project()
    value["sources"] = {slot: {
        "duration": 20, "width": 1280, "height": 720, "has_audio": slot == "A",
        "generation": f"generation-{slot}", "relative_path": f"media/source-{slot}.mp4",
    } for slot in ("A", "B")}
    value["assets"][ASSET].update(
        name="third-video.mp4", kind="video", duration=4, width=1280, height=720,
        has_audio=True, path=f"media/assets/{ASSET}/original.mp4",
        preview_path=f"media/assets/{ASSET}/preview.mp4",
    )
    value["draft"].update(edit_points=[], removed_duration=5, active_reel_candidate=None)
    value["analysis"] = {"audio_source": "A", "transcript": {"segments": [
        {"id": "segment-one", "start": 1, "end": 2, "text": "Original source words"},
    ]}}
    value["manual"] = {
        "cuts": [], "keeps": [], "camera_overrides": [],
        "crop": {"A": {"x": 0.1, "y": 0.1, "zoom": 1.2}},
        "source_mixer": {"audio_slot": "A", "screen_slot": "A", "camera_slot": "B", "sync_offset": 0},
        "audio_mixer": {"voice_db": -4, "ducking": True},
        "caption_corrections": {"segment-one": {
            "original": "Original source words", "text": "Corrected source words",
        }},
        "history": {"undo_count": 0, "redo_count": 0},
    }
    value, duration = materialize_sequence(value)
    assert duration == 15  # The source clock is20s; the existing compact edit is15s.
    for clips in value["manual"]["source_tracks"].values():
        for clip in clips:
            clip["caption_origin"] = clip["id"]
    caption = project_caption_items(value, aligned=False)[0]
    value["manual"]["caption_overrides"] = {caption["id"]: {"text": "Local caption wording"}}
    value["manual"]["caption_override_anchors"] = {caption["id"]: copy.deepcopy(caption["_caption_anchor"])}
    value["manual"]["track_locks"] = {"A": True, "B": True}
    return value


@pytest.fixture
def api(library_api):
    app, client, store, pid = library_api
    value = append_project()
    value["id"] = pid
    store.save({**store.load(pid), **value})
    root = store.project_dir(pid)
    relatives = [source["relative_path"] for source in value["sources"].values()]
    relatives += [value["assets"][ASSET][key] for key in ("path", "preview_path")]
    for relative in relatives:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"Synthetic untouched media: {relative}".encode())
    return app, client, store, pid


def post(api, action="media_append", **fields):
    _, client, store, pid = api
    payload = {"action": action, "expected_revision": store.load(pid)["revision"], **fields}
    if action in {"media_append", "media_add"}:
        payload.setdefault("asset_id", ASSET)
    return client.post(f"/api/projects/{pid}/manual/edit", json=payload)


def content(value):
    # Shared history restores optional draft fields asNone and records edit time.
    # Compare all actual draft content and manual layers, excluding bookkeeping.
    return copy.deepcopy({
        "sources": value["sources"], "assets": value["assets"], "analysis": value["analysis"],
        "draft": {key: item for key, item in value["draft"].items()
                  if key not in {"edited_at", "status"} and item is not None},
        "manual": {key: item for key, item in value["manual"].items() if key not in {"history", "_history"}},
    })


@pytest.mark.parametrize("has_audio", [True, False], ids=["own-audio", "silent"])
def test_append_third_video_extends_edit_end_and_preserves_primary_clocks_layers_and_originals(api, has_audio):
    _, _, store, pid = api
    store.update(pid, lambda value: value["assets"][ASSET].update(has_audio=has_audio))
    before = store.load(pid)
    root = store.project_dir(pid)
    paths = [root / source["relative_path"] for source in before["sources"].values()]
    paths += [root / before["assets"][ASSET][key] for key in ("path", "preview_path")]
    original_bytes = {path: path.read_bytes() for path in paths}
    captions = project_caption_items(before, aligned=False)

    response = post(api)

    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    assert after["manual"]["sequence"]["version"] == 1
    assert after["manual"]["sequence"]["duration"] == 19
    clip = after["manual"]["media_clips"][-1]
    assert (clip["start"], clip["end"], clip["source_start"], clip["asset_id"]) == (15, 19, 0, ASSET)
    assert (clip["x"], clip["y"], clip["w"], clip["h"], clip["fit"], clip["speed"]) == (0, 0, 1, 1, "cover", 1)
    assert clip["audio_enabled"] is has_audio and clip["role"] == "voice" and clip["muted"] is False
    assert after["manual"]["source_tracks"] == before["manual"]["source_tracks"]
    assert after["sources"] == before["sources"] and after["analysis"] == before["analysis"]
    assert after["assets"] == before["assets"]
    for key, layer in before["manual"].items():
        if key not in {"sequence", "history", "_history", "media_clips"}:
            assert after["manual"][key] == layer, key
    assert project_caption_items(after, aligned=False) == captions
    assert captions[0]["text"] == "Local caption wording" and captions[0]["corrected"] is True
    assert all(path.read_bytes() == data for path, data in original_bytes.items())


def test_repeat_asset_has_unique_occurrences_and_exact_shared_undo_redo_save_reopen(api):
    app, _, store, pid = api
    states = [content(store.load(pid))]
    assert post(api, source_start=1, source_end=3).status_code == 200
    first = store.load(pid)
    states.append(content(first))
    assert post(api, source_start=1).status_code == 200  # source_end defaults to4.
    second = store.load(pid)
    states.append(content(second))
    clips = second["manual"]["media_clips"]
    assert len(clips) == 2 and clips[0]["id"] != clips[1]["id"]
    assert [(row["start"], row["end"], row["source_start"]) for row in clips] == [(15, 17, 1), (17, 20, 1)]
    assert second["manual"]["history"] == {"undo_count": 2, "redo_count": 0}
    for expected in (states[1], states[0]):
        assert post(api, "undo").status_code == 200
        assert content(store.load(pid)) == expected
    assert store.load(pid)["manual"]["history"] == {"undo_count": 0, "redo_count": 2}
    for expected in states[1:]:
        assert post(api, "redo").status_code == 200
        assert content(store.load(pid)) == expected
    saved = store.save(store.load(pid))
    reopened = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert reopened == saved and content(reopened) == states[2]
    assert reopened["manual"]["history"] == {"undo_count": 2, "redo_count": 0}


def test_existing_media_add_remains_an_overlay_and_does_not_extend_timeline(api):
    _, _, store, pid = api
    before = store.load(pid)
    assert post(api, "media_add", start=3, end=6).status_code == 200
    after = store.load(pid)
    assert after["manual"]["sequence"] == before["manual"]["sequence"]
    clip = after["manual"]["media_clips"][-1]
    assert (clip["start"], clip["end"], clip["role"], clip["audio_enabled"]) == (3, 6, "voice", True)


@pytest.mark.parametrize(("field", "bad"), [
    ("status", "cancelled"), ("status", "pending"), ("status", "failed"),
    ("kind", "audio"), ("kind", "image"), ("record", None),
], ids=["cancelled", "pending", "failed", "audio", "image", "deleted-record"])
def test_nonready_nonvideo_or_deleted_asset_record_returns_400_without_state_change(api, field, bad):
    _, _, store, pid = api
    def change(value):
        if field == "record":
            value["assets"].pop(ASSET)
        else:
            value["assets"][ASSET][field] = bad
    store.update(pid, change)
    before = store.state_path(pid).read_bytes()
    assert post(api).status_code == 400
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("fields", [
    {"source_start": -1}, {"source_end": math.nan},
    {"source_start": 3, "source_end": 3}, {"source_end": 4.001},
], ids=["negative-start", "nonfinite-end", "empty-range", "beyond-source"])
def test_bad_source_range_returns_400_without_mutation_or_history(api, fields):
    _, _, store, pid = api
    before = store.state_path(pid).read_bytes()
    assert post(api, **fields).status_code == 400
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("missing", ["original", "preview"], ids=["original", "preview"])
def test_missing_physical_asset_returns_safe_409_without_state_change(api, missing):
    _, _, store, pid = api
    asset = store.load(pid)["assets"][ASSET]
    field = "path" if missing == "original" else "preview_path"
    (store.project_dir(pid) / asset[field]).unlink()
    before = store.state_path(pid).read_bytes()
    response = post(api)
    assert response.status_code == 409 and response.get_json()["error"] == "asset_unavailable"
    assert "private-path-sentinel" not in response.get_data(as_text=True)
    assert store.state_path(pid).read_bytes() == before


def test_unsafe_saved_asset_path_is_rejected_by_project_read_validation_before_append(api):
    _, client, store, pid = api
    damaged = store.load(pid)
    damaged["assets"][ASSET]["path"] = "../private-path-sentinel.mp4"
    # Model damaged on-disk state explicitly; normal fixture setup must remain
    # readable so post() cannot accidentally fail before making its HTTP request.
    store.state_path(pid).write_text(json.dumps(damaged), encoding="utf-8")
    before = store.state_path(pid).read_bytes()
    with pytest.raises(ProjectStateError, match="unsafe asset path"):
        store.load(pid)
    response = client.post(f"/api/projects/{pid}/manual/edit", json={
        "action": "media_append", "asset_id": ASSET, "expected_revision": damaged["revision"],
    })
    assert response.status_code == 409 and response.get_json()["error"] == "corrupt_project"
    assert "private-path-sentinel" not in response.get_data(as_text=True)
    assert store.state_path(pid).read_bytes() == before


def test_legacy_append_preserves_gaps_layers_and_captions_and_undo_restores_absent_sequence():
    value = append_project()
    manual = value["manual"]
    manual.pop("sequence")
    manual.pop("source_tracks")
    value["sources"]["B"]["duration"] = 8
    manual["source_mixer"]["sync_offset"] = 2
    manual.pop("caption_overrides")
    manual.pop("caption_override_anchors")
    manual["media_clips"] = [{
        "id": "media_" + "e" * 32, "asset_id": ASSET, "start": 2, "end": 4,
        "source_start": .5, "video_source_start": .5, "speed": 1.25, "volume_db": -8,
        "muted": False, "audio_enabled": True, "role": "effects", "fade_in": .1, "fade_out": .2,
        "x": .1, "y": .2, "w": .4, "h": .5, "fit": "contain", "motion": "pan",
    }]
    manual["text_clips"] = [{
        "id": "text_" + "f" * 32, "kind": "title", "start": 11, "end": 14,
        "text": "Existing title", "position": "top", "style": "boxed", "scale": 125,
        "template": "lower_third", "subtext": "Existing subtext",
    }]
    caption = project_caption_items(value, aligned=False)[0]
    manual["caption_overrides"] = {caption["id"]: {"text": "Legacy local caption wording"}}
    manual["caption_override_anchors"] = {caption["id"]: copy.deepcopy(caption["_caption_anchor"])}
    before, before_view = copy.deepcopy(value), editor_sequence_snapshot(value)
    before_captions = project_caption_items(value, aligned=False)
    assert before_view["duration"] == 15
    assert [(row["start"], row["end"], row["source_start"]) for row in before_view["source_tracks"]["B"]] == [(2, 10, 0)]

    apply_manual_edit(value, {"action": "media_append", "asset_id": ASSET})

    after = copy.deepcopy(value)
    assert value["manual"]["sequence"]["duration"] == 19
    for slot in ("A", "B"):
        # Annotation adds private caption ancestry while retaining selection IDs
        # and every source/edit clock boundary from the legacy read projection.
        without_ancestry = [{key: item for key, item in row.items() if key != "caption_origin"}
                            for row in value["manual"]["source_tracks"][slot]]
        assert without_ancestry == before_view["source_tracks"][slot]
    assert value["manual"]["media_clips"][0] == before["manual"]["media_clips"][0]
    assert value["manual"]["text_clips"] == before["manual"]["text_clips"]
    assert project_caption_items(value, aligned=False) == before_captions
    assert before_captions[0]["text"] == "Legacy local caption wording" and before_captions[0]["corrected"] is True
    assert value["sources"] == before["sources"] and value["analysis"] == before["analysis"]
    assert value["assets"] == before["assets"]
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"] and "source_tracks" not in value["manual"]
    assert content(value) == content(before)
    assert value["manual"]["history"] == {"undo_count": 0, "redo_count": 1}
    apply_manual_edit(value, {"action": "redo"})
    assert content(value) == content(after)
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}


@pytest.mark.parametrize("deleted", ["file", "record"], ids=["original-file", "asset-record"])
def test_post_append_asset_deletion_refuses_render_inputs_without_fallback_or_history_change(api, deleted):
    _, _, store, pid = api
    assert post(api).status_code == 200
    before = store.load(pid)
    clip = copy.deepcopy(before["manual"]["media_clips"][-1])
    binding = next(row for row in build_timeline_bindings(before)["clips"] if row["id"] == clip["id"])
    assert binding["source_ref"] == f"asset:{ASSET}"
    if deleted == "file":
        (store.project_dir(pid) / before["assets"][ASSET]["path"]).unlink()
    else:
        def remove_record(value):
            value["assets"].pop(ASSET)
        store.update(pid, remove_record)
    damaged = store.load(pid)
    state_bytes = store.state_path(pid).read_bytes()
    if deleted == "file":
        inventory = compile_render_inputs(damaged)
        assert inventory.inputs("library")[0].clip["id"] == clip["id"]
        with pytest.raises(FileNotFoundError, match="Timeline media is missing"):
            inventory.input_args(store.project_dir(pid))
        after_binding = next(row for row in build_timeline_bindings(damaged)["clips"] if row["id"] == clip["id"])
        assert after_binding["source_ref"] == binding["source_ref"]
    else:
        with pytest.raises(ValueError, match="timeline asset is missing"):
            compile_render_inputs(damaged)
        with pytest.raises(TimelineBindingError):
            build_timeline_bindings(damaged)
    assert damaged["manual"]["media_clips"][-1] == clip
    assert damaged["manual"]["source_tracks"] == before["manual"]["source_tracks"]
    assert damaged["manual"]["history"] == before["manual"]["history"]
    assert store.state_path(pid).read_bytes() == state_bytes


def test_stale_revision_wins_before_asset_path_lookup(api, monkeypatch):
    _, client, store, pid = api
    stale = store.load(pid)["revision"]
    store.patch(pid, {"name": "Newer project revision"})
    before = store.state_path(pid).read_bytes()
    def forbidden(*_args, **_kwargs):
        pytest.fail("A stale request must not inspect asset files")
    with monkeypatch.context() as scoped:
        scoped.setattr(server, "safe_asset_path", forbidden)
        response = client.post(f"/api/projects/{pid}/manual/edit", json={
            "action": "media_append", "asset_id": ASSET, "expected_revision": stale,
        })
    assert response.status_code == 409 and response.get_json()["error"] == "revision_conflict"
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("version", [2, True, "1", 1.0], ids=["future", "boolean", "string", "float"])
def test_unknown_sequence_version_is_rejected_without_rewrite(api, version):
    _, _, store, pid = api
    future = store.load(pid)
    future["manual"]["sequence"]["version"] = version
    store.state_path(pid).write_text(json.dumps(future), encoding="utf-8")
    before = store.state_path(pid).read_bytes()
    response = post(api)
    assert response.status_code == 409 and response.get_json()["error"] == "timeline_version_unsupported"
    assert store.state_path(pid).read_bytes() == before


def test_api_requires_expected_revision_and_rejects_hidden_append_fields(api):
    _, client, store, pid = api
    before = store.state_path(pid).read_bytes()
    endpoint = f"/api/projects/{pid}/manual/edit"
    assert client.post(endpoint, json={"action": "media_append", "asset_id": ASSET}).status_code == 400
    assert post(api, path="C:/untrusted.mp4").status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_append_maximum_duration_and_reset_cannot_discard_media_or_consume_history(api):
    too_long = append_project()
    too_long["manual"]["sequence"]["duration"] = MAX_SEQUENCE_SECONDS - 2
    before_long = copy.deepcopy(too_long)
    with pytest.raises(ManualEditError):
        apply_manual_edit(too_long, {"action": "media_append", "asset_id": ASSET})
    assert too_long == before_long

    _, _, store, pid = api
    assert post(api).status_code == 200
    store.update(pid, lambda value: value["manual"].update(track_locks={"A": False, "B": False}))
    before_reset = store.state_path(pid).read_bytes()
    response = post(api, "sequence_reset")
    assert response.status_code == 400, response.get_json()
    assert "Trim, move, or remove" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before_reset
