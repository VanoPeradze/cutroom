"""Availability seams must not invent invalid clips during audio/manual edits."""
import copy

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.render import _frame_aligned_plan
from cutroom.sequence import editor_sequence_snapshot, materialize_sequence
from cutroom.source_tracks import SourceTrackError, source_track_clips


def test_add_media_accepts_keeps_ending_eight_ms_after_secondary_source():
    asset_id = "asset_" + "a" * 32
    project = {
        "settings": {"fps": 60},
        "sources": {"A": {"duration": 3.008}, "B": {"duration": 3.000}},
        "manual": {},
        "draft": {"keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 3.008}]},
        "assets": {asset_id: {"id": asset_id, "kind": "audio", "duration": 1, "status": "ready"}},
    }
    before = copy.deepcopy(project)
    apply_manual_edit(project, {"action": "media_add", "asset_id": asset_id, "start": 0})
    clip = project["manual"]["media_clips"][0]
    assert (clip["asset_id"], clip["start"], clip["end"]) == (asset_id, 0, 1)
    assert project["sources"] == before["sources"]


def boundary_project(*, delta=0.008, offset=0, fps=60):
    return {
        "settings": {"fps": fps},
        "sources": {"A": {"duration": 3 + delta}, "B": {"duration": 3}},
        "manual": {"source_mixer": {"sync_offset": offset}},
        "draft": {"keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 3 + delta}]},
    }


def geometry(project, slot):
    return [(row["start"], row["end"], row["source_start"]) for row in source_track_clips(project, slot)]


@pytest.mark.parametrize("action", ["media", "mixer", "text", "split"])
def test_automatic_boundary_allows_manual_audio_and_timeline_actions_with_history(action):
    project = boundary_project()
    asset_id = "asset_" + "b" * 32
    project["assets"] = {asset_id: {"id": asset_id, "kind": "audio", "duration": 1, "status": "ready"}}
    payload = {
        "media": {"action": "media_add", "asset_id": asset_id, "start": 0},
        "mixer": {"action": "set_audio_mixer", "source_db": -3},
        "text": {"action": "text_add", "kind": "title", "start": 0, "end": 1, "text": "Local edit"},
        "split": {"action": "sequence_split", "slot": "A", "time": 0.5},
    }[action]
    before = copy.deepcopy(project)
    assert editor_sequence_snapshot(project)["duration"] == 2.008
    apply_manual_edit(project, payload)
    assert project["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert project["sources"] == before["sources"]
    assert project["draft"]["keep_ranges"] == before["draft"]["keep_ranges"]
    assert editor_sequence_snapshot(project)["duration"] == 2.008
    apply_manual_edit(project, {"action": "undo"})
    assert editor_sequence_snapshot(project)["duration"] == 2.008
    assert "sequence" not in project["manual"]
    apply_manual_edit(project, {"action": "redo"})
    assert editor_sequence_snapshot(project)["duration"] == 2.008


@pytest.mark.parametrize("fps", [30, 60])
@pytest.mark.parametrize("delta", [0.001, 0.008, 0.016, 0.017, 0.033])
def test_implicit_secondary_end_preserves_media_time_and_edit_duration(fps, delta):
    original = boundary_project(delta=delta, fps=fps)
    before = copy.deepcopy(original)
    value, duration = materialize_sequence(original)
    assert duration == pytest.approx(2 + delta)
    assert geometry(value, "B") == [(0, 1, 0), (1, 2, 2)]
    if delta < 1 / 60:
        assert geometry(value, "A") == [(0, 1, 0), (1, 2 + delta, 2)]
        assert [row["id"] for row in source_track_clips(value, "A")] == ["A:sequence:0:0", "A:sequence:1:0"]
        assert value["manual"]["sequence"]["camera_plan"] == [
            {"start": 0, "end": 1, "camera": "A"}, {"start": 1, "end": 2 + delta, "camera": "A"},
        ]
    else:
        assert geometry(value, "A") == [(0, 1, 0), (1, 2, 2), (2, 2 + delta, 3)]
    assert original == before


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
@pytest.mark.parametrize("delta", [0.001, 0.008, 0.016, 0.017, 0.033])
def test_automatic_layout_seam_never_invents_a_zero_frame_export_fragment(fps, delta):
    project = boundary_project(fps=fps, delta=delta)
    for source in project["sources"].values():
        source.update(width=160, height=100, has_audio=True)
    project["draft"]["camera_plan"] = [{"start": 0, "end": 3 + delta, "camera": "stacked"}]
    value, duration = materialize_sequence(project)
    plan = _frame_aligned_plan(value)
    assert sum(row["_end_frame"] - row["_start_frame"] for row in plan) == round(duration * fps)
    assert all(row["camera"] != "black" for row in plan)


@pytest.mark.parametrize("edit_fps", [30, 60])
@pytest.mark.parametrize("export_fps", [24, 25])
@pytest.mark.parametrize("delta", [0.017, 0.033])
def test_automatic_camera_projection_remains_valid_after_export_fps_override(edit_fps, export_fps, delta):
    project = boundary_project(fps=edit_fps, delta=delta)
    for source in project["sources"].values():
        source.update(width=160, height=100, has_audio=True)
    project["draft"]["camera_plan"] = [{"start": 0, "end": 3 + delta, "camera": "stacked"}]
    value, _ = materialize_sequence(project)
    tracks = copy.deepcopy(value["manual"]["source_tracks"])
    value["settings"]["fps"] = export_fps
    assert _frame_aligned_plan(value)
    assert value["manual"]["source_tracks"] == tracks


@pytest.mark.parametrize("offset", [-0.033, -0.017, -0.016, -0.008, -0.001, 0, 0.001, 0.008, 0.016, 0.017, 0.033])
@pytest.mark.parametrize("fps", [30, 60])
def test_implicit_start_and_end_seams_keep_positive_and_negative_sync(offset, fps):
    original = boundary_project(delta=0, offset=offset, fps=fps)
    value, duration = materialize_sequence(original)
    assert duration == 2
    if abs(offset) < 1 / 60:
        assert geometry(value, "A") == [(0, 1, 0), (1, 2, 2)]
    elif offset > 0:
        assert geometry(value, "A") == [(0, offset, 0), (offset, 1, offset), (1, 2, 2)]
    else:
        assert geometry(value, "A") == [(0, 1, 0), (1, 2 + offset, 2), (2 + offset, 2, 3 + offset)]
    if offset > 0:
        assert geometry(value, "B") == [(offset, 1, 0), (1, 2, 2 - offset)]
    elif offset < 0:
        assert geometry(value, "B") == [(0, 1, -offset), (1, 2 + offset, 2 - offset)]
    else:
        assert geometry(value, "B") == [(0, 1, 0), (1, 2, 2)]
    for row in source_track_clips(value, "A"):
        assert set(row) == {"id", "start", "end", "source_start"}  # Local provenance never reaches persisted clips.


def test_same_origin_coalescing_preserves_picture_clock_crop_and_reset_provenance():
    original = boundary_project()
    source = {"id": "framed", "start": 0, "end": 3.008, "source_start": 0,
              "video_speed": 0.5, "video_source_start": 0.25, "crop": {"x": 0.3, "y": 0.6, "zoom": 1.2}}
    original["manual"]["source_tracks"] = {"A": [source]}
    value, _ = materialize_sequence(original)
    clips = source_track_clips(value, "A")
    assert geometry(value, "A") == [(0, 1, 0), (1, 2.008, 2)]
    assert clips[1]["video_source_start"] == 1.25
    assert clips[1]["video_speed"] == 0.5
    assert clips[1]["crop"] == source["crop"]
    assert value["manual"]["sequence"]["base_source_tracks"] == {"A": [source]}
    assert original["manual"]["source_tracks"] == {"A": [source]}


@pytest.mark.parametrize("boundary", ["edit", "layout", "explicit-source"])
def test_explicit_subframe_boundary_is_still_rejected_atomically(boundary):
    project = boundary_project()
    if boundary == "edit":
        project["draft"]["edit_points"] = [3]
    elif boundary == "layout":
        project["draft"]["camera_plan"] = [
            {"start": 0, "end": 3, "camera": "A"}, {"start": 3, "end": 3.008, "camera": "B"},
        ]
    else:
        project["manual"]["source_tracks"] = {"B": [{"id": "user-trimmed", "start": 0, "end": 3, "source_start": 0}]}
    before = copy.deepcopy(project)
    with pytest.raises(ManualEditError, match="at least one output frame"):
        apply_manual_edit(project, {"action": "sequence_split", "slot": "A", "time": 0.5})
    assert project == before


def test_adjacent_keep_boundary_is_not_coalesced_or_silently_dropped():
    project = boundary_project()
    project["draft"]["keep_ranges"] = [{"start": 0, "end": 3}, {"start": 3, "end": 3.008}]
    with pytest.raises(SourceTrackError, match="at least one output frame"):
        materialize_sequence(project)


def test_explicit_valid_split_and_layout_on_foreign_edge_keep_their_virtual_ids():
    project = boundary_project(delta=0.033)
    project["draft"]["edit_points"] = [3]
    project["draft"]["camera_plan"] = [{"start": 0, "end": 3, "camera": "stacked"},
                                      {"start": 3, "end": 3.033, "camera": "A"}]
    value, _ = materialize_sequence(project)
    assert geometry(value, "A") == [(0, 1, 0), (1, 2, 2), (2, 2.033, 3)]
    assert source_track_clips(value, "A")[-1]["id"] == "A:sequence:1:1"
    assert value["manual"]["sequence"]["camera_plan"][-1] == {"start": 2, "end": 2.033, "camera": "A"}
