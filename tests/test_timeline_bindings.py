"""Acceptance tests for detached, revision-scoped timeline identity bindings.

These metadata-only cases do not decode media, invoke FFmpeg or contact models.
The existing v1 project and renderer remain authoritative.
"""
from __future__ import annotations

import copy
import builtins
import importlib
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ASSET = "asset_" + "b" * 32


@pytest.fixture
def bindings():
    return importlib.import_module("cutroom.timeline_bindings")


@pytest.fixture
def project():
    primary = {"duration": 3.0, "width": 320, "height": 180, "fps": 30, "has_audio": True}
    media_defaults = {"speed": 1, "volume_db": 0, "muted": False, "fade_in": 0, "fade_out": 0,
                      "x": 0, "y": 0, "w": 1, "h": 1, "fit": "cover", "motion": "none"}
    return {"id": "project_123456789abc", "revision": 7,
            "sources": {"A": {**primary, "generation": "ga1", "relative_path": "media/A.mp4"},
                        "B": {**primary, "generation": "gb1", "relative_path": "media/B.mp4"}},
            "settings": {"fps": 30, "editorial_effects": False},
            "draft": {"keep_ranges": [{"start": 0, "end": 3}], "camera_plan": [{"start": 0, "end": 3, "camera": "A"}]},
            "manual": {"media_clips": [
                {**media_defaults, "id": "media_one", "asset_id": ASSET, "start": 0, "end": 1, "source_start": 1,
                 "video_source_start": 2, "speed": 2, "audio_enabled": True, "role": "voice"},
                {**media_defaults, "id": "media_two", "asset_id": ASSET, "start": 1, "end": 2, "source_start": 3,
                 "audio_enabled": True, "role": "effects"}]},
            "assets": {ASSET: {"id": ASSET, "kind": "video", "status": "ready", "duration": 8,
                               "width": 160, "height": 90, "fps": 30, "has_audio": True,
                               "path": f"media/assets/{ASSET}/original.mp4"}}}


def test_repeated_projection_is_stable_detached_and_never_opens_media(bindings, project, monkeypatch):
    before = copy.deepcopy(project)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("An identity projection must not open media or write state")
    monkeypatch.setattr(builtins, "open", forbidden)
    for name in ("open", "is_file", "stat", "resolve"):
        monkeypatch.setattr(Path, name, forbidden)
    first = bindings.build_timeline_bindings(project)
    second = bindings.build_timeline_bindings(project)
    assert first == second and project == before
    assert first["version"] == 1 and first["revision"] == 7
    assert first["clock"] == "edit" and first["selection_scope"] == "project_revision"
    first["tracks"][0]["id"] = "changed"
    first["clips"][0]["state"]["start"] = 999
    first["sources"]["primary:A:ga1"]["generation"] = "changed"
    assert bindings.build_timeline_bindings(project) == second


def test_compacted_legacy_draft_projects_edit_clock_not_source_clock(bindings, project):
    project["draft"]["keep_ranges"] = [{"start": 1, "end": 3}]
    result = bindings.build_timeline_bindings(project)
    clips = [row for row in result["clips"] if row.get("track_id") == result["tracks"][0]["id"]]
    assert len(clips) == 1 and clips[0]["id"] == "A:sequence:0:0"
    assert {key: clips[0]["state"][key] for key in ("start", "end", "source_start")} == {
        "start": 0, "end": 2, "source_start": 1}


def test_supplied_editor_snapshot_is_reused_without_rematerialization(bindings, project, monkeypatch):
    from cutroom import sequence
    snapshot = sequence.editor_sequence_snapshot(project)
    snapshot["source_tracks"]["A"][0]["id"] = "snapshot_only"
    before = copy.deepcopy(snapshot)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Reuse the supplied editor snapshot")
    monkeypatch.setattr(sequence, "materialize_sequence", forbidden)
    result = bindings.build_timeline_bindings(project, editor_sequence=snapshot)
    assert any(row["id"] == "snapshot_only" for row in result["clips"])
    assert snapshot == before


def test_lane_ids_are_project_scoped_and_independent_of_names_and_roles(bindings, project):
    first = bindings.build_timeline_bindings(project)
    assert [row["id"] for row in first["tracks"]] == ["track:project_123456789abc:A", "track:project_123456789abc:B"]
    project["sources"]["A"]["name"] = "renamed.mp4"
    project["manual"]["source_mixer"] = {"screen_slot": "B", "camera_slot": "A"}
    assert [row["id"] for row in bindings.build_timeline_bindings(project)["tracks"]] == [row["id"] for row in first["tracks"]]
    project["id"] = "project_999999999999"
    assert not {row["id"] for row in first["tracks"]} & {row["id"] for row in bindings.build_timeline_bindings(project)["tracks"]}


def test_generation_is_a_binding_not_a_lane_id_or_content_hash(bindings, project):
    first = bindings.build_timeline_bindings(project)
    project["sources"]["A"]["generation"] = "ga2"
    project["revision"] += 1
    second = bindings.build_timeline_bindings(project)
    assert first["tracks"][0]["id"] == second["tracks"][0]["id"]
    assert first["tracks"][0]["source_ref"] == "primary:A:ga1"
    assert second["tracks"][0]["source_ref"] == "primary:A:ga2"
    assert second["sources"]["primary:A:ga2"]["binding_state"] == "current_generation"
    assert "sha256" not in second["sources"]["primary:A:ga2"]


def test_unversioned_legacy_source_is_reported_without_hashing_or_pinning(bindings, project):
    del project["sources"]["A"]["generation"]
    before = copy.deepcopy(project)
    result = bindings.build_timeline_bindings(project)
    lane = result["tracks"][0]
    assert lane["source_ref"] == "primary:A:unversioned" and lane["can_edit_by_id"] is False
    assert result["sources"][lane["source_ref"]]["binding_state"] == "unversioned"
    assert project == before


def test_explicit_empty_lane_does_not_regain_implicit_source_footage(bindings, project):
    first = bindings.build_timeline_bindings(project)
    assert any(row.get("track_id") == first["tracks"][0]["id"] for row in first["clips"])
    project["manual"]["source_tracks"] = {"A": []}
    empty = bindings.build_timeline_bindings(project)
    assert not any(row.get("track_id") == empty["tracks"][0]["id"] for row in empty["clips"])


def test_malformed_explicit_lane_never_regains_implicit_footage(bindings, project):
    project["manual"]["source_tracks"] = {"A": [{"id": "broken", "start": 0, "end": 3, "source_start": -1}]}
    before = copy.deepcopy(project)
    result = bindings.build_timeline_bindings(project)
    assert not any(row.get("track_id") == result["tracks"][0]["id"] for row in result["clips"])
    assert project == before


def test_cross_lane_clip_id_collision_is_legal_and_qualified_by_track(bindings, project):
    project["manual"]["sequence"] = {"version": 1, "duration": 3, "camera_plan": [{"start": 0, "end": 3, "camera": "A"}]}
    clip = {"id": "same-id", "start": 0, "end": 3, "source_start": 0, "video_speed": 0.5,
            "video_source_start": 1, "crop": {"x": 0.5, "y": 0.5, "zoom": 1}}
    project["manual"]["source_tracks"] = {"A": [copy.deepcopy(clip)], "B": [copy.deepcopy(clip)]}
    result = bindings.build_timeline_bindings(project)
    clips = [row for row in result["clips"] if row.get("track_id")]
    assert len(clips) == 2 and len({(row["track_id"], row["id"]) for row in clips}) == 2
    assert all(row["state"]["source_start"] == 0 and row["state"]["video_source_start"] == 1
               and row["state"]["video_speed"] == 0.5 for row in clips)


@pytest.mark.parametrize("has_b", [True, False])
def test_library_occurrences_are_stable_addresses_and_distinct_decoders(bindings, project, has_b):
    from cutroom.render_inventory import compile_render_inputs
    if not has_b:
        del project["sources"]["B"]
    base_index = 2 if has_b else 1
    first = bindings.build_timeline_bindings(project)
    expected_sources = {"primary:A:ga1", "asset:" + ASSET} | ({"primary:B:gb1"} if has_b else set())
    assert set(first["sources"]) == expected_sources
    library = [row for row in first["clips"] if row["collection"] == "library"]
    assert [row["id"] for row in library] == ["media_one", "media_two"]
    assert all(row["track_id"] is None for row in library)  # UI packing rows are not saved tracks.
    inputs = [row for row in first["render_bindings"] if row["category"] == "library"]
    assert [(row["clip_id"], row["index"]) for row in inputs] == [("media_one", base_index), ("media_two", base_index + 1)]
    inventory = compile_render_inputs(project)
    assert [(row["category"], row["key"], row["index"]) for row in first["render_bindings"]] == [
        (entry.category, entry.key, entry.index) for entry in inventory.entries]
    project["manual"]["media_clips"].reverse()
    second = bindings.build_timeline_bindings(project)
    assert {row["id"] for row in second["clips"] if row["collection"] == "library"} == {"media_one", "media_two"}
    inputs = [row for row in second["render_bindings"] if row["category"] == "library"]
    assert [(row["clip_id"], row["index"]) for row in inputs] == [("media_two", base_index), ("media_one", base_index + 1)]


@pytest.mark.parametrize("invalid", ["missing", "duplicate"])
def test_ambiguous_library_address_fails_instead_of_using_array_position(bindings, project, invalid):
    if invalid == "missing":
        del project["manual"]["media_clips"][0]["id"]
    else:
        project["manual"]["media_clips"][1]["id"] = "media_one"
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project)


def test_projection_has_no_private_media_paths_or_caption_provenance(bindings, project):
    project["manual"]["source_tracks"] = {"A": [{"id": "a", "start": 0, "end": 3,
        "source_start": 0, "caption_origin": "private_caption_sentinel"}]}
    project["sources"]["A"]["traceback"] = "private_trace_sentinel"
    project["assets"][ASSET]["internal_path"] = "private_path_sentinel"
    before = copy.deepcopy(project)
    result = bindings.build_timeline_bindings(project)
    encoded = json.dumps(result)
    assert "relative_path" not in encoded and "original.mp4" not in encoded and "media/A.mp4" not in encoded
    assert "caption_origin" not in encoded and "traceback" not in encoded
    assert not any(sentinel in encoded for sentinel in ("private_caption_sentinel", "private_trace_sentinel", "private_path_sentinel"))
    assert project == before


@pytest.mark.parametrize("version", [2, True, "1", 1.0])
def test_unknown_authoritative_sequence_version_cannot_fall_back_to_source_a(bindings, project, version):
    project["manual"]["sequence"] = {"version": version, "duration": 99, "tracks": []}
    before = copy.deepcopy(project)
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project)
    assert project == before


def test_stale_supplied_inventory_is_rejected(bindings, project):
    from cutroom.render_inventory import compile_render_inputs
    inventory = compile_render_inputs(project)
    project["manual"]["media_clips"].reverse()
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project, input_inventory=inventory)


def test_projection_cannot_change_render_graph_maps_or_input_order(bindings, project, tmp_path):
    from cutroom.render import build_filter_graph
    from cutroom.render_inventory import compile_render_inputs
    for item in [*project["sources"].values(), *project["assets"].values()]:
        path = tmp_path / (item.get("relative_path") or item["path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"metadata-only: no decoder is invoked")
    before = (build_filter_graph(project, 320, 180), compile_render_inputs(project).input_args(tmp_path))
    bindings.build_timeline_bindings(project)
    assert (build_filter_graph(project, 320, 180), compile_render_inputs(project).input_args(tmp_path)) == before


def test_project_without_a_draft_has_no_invented_identity_projection(bindings, project):
    project["draft"] = None
    before = copy.deepcopy(project)
    assert bindings.build_timeline_bindings(project) is None
    assert project == before


@pytest.mark.parametrize("identity", ["", True, {"private": "sentinel"}, "../foreign-project"])
def test_malformed_project_identity_fails_without_source_fallback(bindings, project, identity):
    project["id"] = identity
    before = copy.deepcopy(project)
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project)
    assert project == before


@pytest.mark.parametrize("generation", [True, 42, ["ga1"], {"private": "sentinel"}, "../private-source"])
def test_malformed_nonempty_primary_generation_is_not_advertised_as_editable(bindings, project, generation):
    project["sources"]["A"]["generation"] = generation
    before = copy.deepcopy(project)
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project)
    assert project == before


def test_chroma_background_inputs_share_asset_identity_without_becoming_primary_lanes(bindings, project):
    from cutroom.render_inventory import compile_render_inputs

    background = "asset_" + "c" * 32
    project["assets"][background] = {
        "id": background, "kind": "image", "status": "ready", "width": 80, "height": 40,
        "path": f"media/assets/{background}/private-background.png",
    }
    project["manual"]["chroma_key"] = {
        "A": {"enabled": True, "background_asset_id": background},
        ASSET: {"enabled": True, "background_asset_id": background},
    }
    before = copy.deepcopy(project)
    inventory = compile_render_inputs(project)
    result = bindings.build_timeline_bindings(project, input_inventory=inventory)
    background_inputs = [row for row in result["render_bindings"] if row["category"] == "chroma_background"]
    assert [(row["key"], row["index"]) for row in background_inputs] == [
        (entry.key, entry.index) for entry in inventory.inputs("chroma_background")]
    assert {row["key"] for row in background_inputs} == {"background:A", "background:" + ASSET}
    assert all(row["source_ref"] == "asset:" + background for row in background_inputs)
    assert result["sources"]["asset:" + background]["binding_state"] == "asset_id_only"
    assert [row["legacy_slot"] for row in result["tracks"]] == ["A", "B"]
    assert "private-background.png" not in json.dumps(result)
    assert project == before


def test_partial_supplied_inventory_cannot_silently_drop_library_bindings(bindings, project):
    from cutroom.render_inventory import compile_render_inputs

    inventory = compile_render_inputs(project, include_library=False)
    before = copy.deepcopy(project)
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project, input_inventory=inventory)
    assert project == before


@pytest.mark.parametrize("field,invalid", [
    ("motion", {"path": "private-path-sentinel", "caption_origin": "private-caption-sentinel"}),
    ("fit", {"path": "private-path-sentinel"}),
    ("role", {"private": "private-caption-sentinel"}),
    ("x", {"path": "private-path-sentinel"}),
    ("muted", {"path": "private-path-sentinel"}),
    ("motion", "private-unknown-motion"),
    ("fit", "private-unknown-fit"),
    ("role", "private-unknown-role"),
    ("audio_enabled", "private-not-a-boolean"),
])
def test_invalid_library_state_cannot_smuggle_nested_private_metadata_into_public_bindings(bindings, project, field, invalid):
    project["manual"]["media_clips"][0][field] = invalid
    before = copy.deepcopy(project)
    with pytest.raises(bindings.TimelineBindingError):
        bindings.build_timeline_bindings(project)
    assert project == before
