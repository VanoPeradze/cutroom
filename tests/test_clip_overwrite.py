"""A cut moves on its own, not by rippling the rest of the recording."""
import copy
import json

import pytest

from cutroom import render
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.sequence import editor_sequence_snapshot
from cutroom.source_tracks import source_track_clips, timeline_duration
from test_sequence_editing import edit, geometry, project
from test_source_tracks_api import post, track_api


@pytest.mark.parametrize("fps", [30, 60])
@pytest.mark.parametrize("two_sources", [False, True])
def test_cut_move_reopen_move_again_and_undo_preserve_individual_clips(fps, two_sources):
    value = project()
    value["settings"]["fps"] = fps
    if not two_sources:
        del value["sources"]["B"]
    originals = copy.deepcopy(value)
    edit(value, "split_all", time=2)
    cut_state = copy.deepcopy(value["manual"]["source_tracks"])
    edit(value, "move_range", start=2, end=4, to=7, mode="overwrite")
    assert geometry(value) == [(0, 2, 0), (4, 7, 10), (7, 9, 2), (9, 10, 15)]
    if two_sources:
        assert geometry(value, "B") == geometry(value)
    assert timeline_duration(value) == 10
    for slot in value["sources"]:
        clips = source_track_clips(value, slot)
        assert len({clip["id"] for clip in clips}) == len(clips)
        assert clips[0] == cut_state[slot][0], "the first cut must not move or change identity"
    assert value["sources"] == originals["sources"] and value["analysis"] == originals["analysis"]
    assert render._expected_output_duration(value) == 10
    assert render._caption_transcript(value)["segments"] == [{"start": 4, "end": 6, "text": "original speech"}]
    moved_state = copy.deepcopy(value["manual"]["source_tracks"])
    # The same operation works after reopening a persisted project.
    value = json.loads(json.dumps(value))
    assert editor_sequence_snapshot(value)["source_tracks"] == moved_state
    edit(value, "move_range", start=7, end=9, to=2, mode="overwrite")
    assert geometry(value) == [(0, 2, 0), (2, 4, 2), (4, 7, 10), (9, 10, 15)]
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["source_tracks"] == moved_state
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["source_tracks"] == cut_state
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["source_tracks"] == moved_state


def test_overlapping_own_origin_is_lifted_before_placing_and_layout_follows():
    value = project()
    edit(value, "move_range", start=0, end=4, to=2, mode="overwrite")
    assert geometry(value) == [(2, 6, 0), (6, 10, 12)]
    assert value["manual"]["sequence"]["camera_plan"] == [
        {"start": 0, "end": 2, "camera": "stacked"},
        {"start": 2, "end": 6, "camera": "stacked"},
        {"start": 6, "end": 10, "camera": "A"},
    ]


def test_independent_clip_overwrite_does_not_ripple_its_lane_or_touch_other_lane():
    value = project()
    edit(value, "split_all", time=2)
    other = copy.deepcopy(value["manual"]["source_tracks"]["B"])
    clip = source_track_clips(value, "A")[1]
    edit(value, "move", slot="A", clip_id=clip["id"], start=7, mode="overwrite")
    assert geometry(value) == [(0, 2, 0), (4, 7, 10), (7, 9, 2), (9, 10, 15)]
    assert value["manual"]["source_tracks"]["B"] == other


def test_extending_overwrite_leaves_original_positions_and_fills_layout_gap():
    value = project()
    edit(value, "move_range", start=0, end=4, to=12, mode="overwrite")
    assert geometry(value) == [(4, 10, 10), (12, 16, 0)]
    assert timeline_duration(value) == 16
    assert value["manual"]["sequence"]["camera_plan"][-2:] == [
        {"start": 10, "end": 12, "camera": "A"}, {"start": 12, "end": 16, "camera": "stacked"}]


def test_selected_part_can_move_independently_without_moving_the_enclosing_clip():
    value = project()
    before = editor_sequence_snapshot(value)
    edit(value, "move_range", slot="A", start=1, end=2, to=6, mode="overwrite")
    assert geometry(value) == [(0, 1, 0), (2, 4, 2), (4, 6, 10), (6, 7, 1), (7, 10, 13)]
    assert value["manual"]["source_tracks"]["B"] == before["source_tracks"]["B"]
    assert value["manual"]["sequence"]["camera_plan"] == before["sequence"]["camera_plan"]


@pytest.mark.parametrize("destination", [7.001, -1, 86400])
def test_invalid_overwrite_is_atomic(destination):
    value = project()
    edit(value, "split_all", time=2)
    edit(value, "split_all", time=7)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        edit(value, "move_range", start=0, end=2, to=destination, mode="overwrite")
    assert value == before


def test_api_accepts_overwrite_mode_and_saves_only_the_cut_move(track_api):
    client, store, project_id = track_api
    response = post(track_api, {"action": "sequence_split_all", "time": 2})
    assert response.status_code == 200
    response = post(track_api, {"action": "sequence_move_range", "start": 0, "end": 2, "to": 6, "mode": "overwrite"})
    assert response.status_code == 200, response.get_json()
    saved = store.load(project_id)
    assert geometry(saved)[:2] == [(2, 6, 2), (6, 8, 0)]
    assert timeline_duration(saved) == 20
