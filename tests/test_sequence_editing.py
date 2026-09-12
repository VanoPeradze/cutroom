from __future__ import annotations

import copy

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.sequence import editor_sequence_snapshot, materialize_sequence
from cutroom.source_tracks import has_sequence, source_track_clips, timeline_duration


def project():
    return {
        "id": "project_012345abcdef", "settings": {"fps": 30},
        "sources": {"A": {"duration": 20, "has_audio": True}, "B": {"duration": 20, "has_audio": True}},
        "manual": {},
        "analysis": {"sync": {"offset": 0}, "transcript": {"segments": [{"start": 10, "end": 12, "text": "original speech"}]}},
        "draft": {"keep_ranges": [{"start": 0, "end": 4}, {"start": 10, "end": 16}],
                  "cuts": [{"start": 4, "end": 10}, {"start": 16, "end": 20}],
                  "camera_plan": [{"start": 0, "end": 4, "camera": "stacked"}, {"start": 10, "end": 16, "camera": "A"}],
                  "output_duration": 10, "removed_duration": 10},
    }


def edit(value, action, **kwargs):
    return apply_manual_edit(value, {"action": f"sequence_{action}", **kwargs})


def geometry(value, slot="A"):
    return [(clip["start"], clip["end"], clip["source_start"]) for clip in source_track_clips(value, slot)]


def test_virtual_sequence_compacts_every_keep_without_mutating_source_draft_or_transcript():
    value = project()
    before = copy.deepcopy(value)
    view, duration = materialize_sequence(value)
    assert value == before
    assert duration == 10
    assert geometry(view) == [(0, 4, 0), (4, 10, 10)]
    assert geometry(view, "B") == [(0, 4, 0), (4, 10, 10)]
    assert [clip["id"] for clip in source_track_clips(view, "A")] == ["A:sequence:0:0", "A:sequence:1:0"]
    assert view["sources"] == before["sources"]
    assert view["analysis"] == before["analysis"]
    assert view["draft"] == before["draft"]
    snapshot = editor_sequence_snapshot(value)
    assert snapshot["active"] is False
    assert snapshot["duration"] == 10
    assert snapshot["sequence"]["camera_plan"] == [{"start": 0, "end": 4, "camera": "stacked"}, {"start": 4, "end": 10, "camera": "A"}]
    assert "base_source_tracks" not in snapshot["sequence"]
    assert value == before


def test_projection_includes_manual_split_layout_and_existing_independent_track_boundaries():
    value = project()
    value["draft"]["edit_points"] = [1]
    value["draft"]["camera_plan"] = [{"start": 0, "end": 2, "camera": "stacked"}, {"start": 2, "end": 16, "camera": "B"}]
    value["manual"]["source_tracks"] = {"B": [{"id": "custom", "start": 3, "end": 13, "source_start": 1}]}
    view, _ = materialize_sequence(value)
    assert geometry(view) == [(0, 1, 0), (1, 2, 1), (2, 3, 2), (3, 4, 3), (4, 7, 10), (7, 10, 13)]
    assert geometry(view, "B") == [(3, 4, 1), (4, 7, 8)]


def test_first_move_can_extend_past_original_a_and_never_uses_global_keep_mask():
    value = project()
    before = copy.deepcopy(value)
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=24)
    assert timeline_duration(value) == 30
    assert geometry(value) == [(0, 4, 0), (24, 30, 10)]
    assert geometry(value, "B") == [(0, 4, 0), (4, 10, 10)]
    assert value["sources"] == before["sources"]
    assert value["analysis"] == before["analysis"]
    assert value["draft"]["keep_ranges"] == before["draft"]["keep_ranges"]
    assert editor_sequence_snapshot(value)["active"] is True


def test_occupied_move_inserts_and_ripples_only_selected_lane():
    value = project()
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=0)
    assert geometry(value) == [(0, 6, 10), (6, 10, 0)]
    assert geometry(value, "B") == [(0, 4, 0), (4, 10, 10)]


def test_inserting_into_middle_splits_destination_and_preserves_both_halves():
    value = project()
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=2)
    assert geometry(value) == [(0, 2, 0), (2, 8, 10), (8, 10, 2)]
    assert geometry(value, "B") == [(0, 4, 0), (4, 10, 10)]


def test_place_is_non_ripple_and_rejects_collision_atomically():
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="overlap"):
        edit(value, "place", slot="A", clip_id="A:sequence:1:0", start=2)
    assert value == before
    edit(value, "place", slot="A", clip_id="A:sequence:1:0", start=12)
    assert geometry(value) == [(0, 4, 0), (12, 18, 10)]


def test_split_remove_trim_and_duplicate_use_clip_local_media_not_edit_time():
    value = project()
    edit(value, "split", slot="A", time=7)
    assert geometry(value) == [(0, 4, 0), (4, 7, 10), (7, 10, 13)]
    edit(value, "remove_range", slot="A", start=0, end=4)
    edit(value, "trim", slot="A", clip_id="A:sequence:1:0", start=4, end=6, source_start=11)
    assert geometry(value) == [(4, 6, 11), (7, 10, 13)]
    edit(value, "duplicate", slot="A", clip_id="A:sequence:1:0", start=0)
    assert geometry(value) == [(0, 2, 11), (4, 6, 11), (7, 10, 13)]
    assert len({clip["id"] for clip in source_track_clips(value, "A")}) == 3


def test_empty_lane_can_insert_original_source_window_at_any_edit_time():
    value = project()
    edit(value, "remove_range", slot="B", start=0, end=10)
    assert geometry(value, "B") == []
    edit(value, "insert", slot="B", start=2, source_start=15, source_end=19)
    assert geometry(value, "B") == [(2, 6, 15)]
    assert geometry(value) == [(0, 4, 0), (4, 10, 10)]


def test_wholly_empty_sequence_preserves_clock_and_does_not_crash():
    value = project()
    edit(value, "remove_range", slot="A", start=0, end=10)
    edit(value, "remove_range", slot="B", start=0, end=10)
    assert geometry(value) == geometry(value, "B") == []
    assert timeline_duration(value) == 10


def test_reset_and_history_restore_original_coordinate_space_and_ids():
    value = project()
    value["manual"]["source_tracks"] = {"A": [{"id": "old-source-clock", "start": 0, "end": 20, "source_start": 0}]}
    original_tracks = copy.deepcopy(value["manual"]["source_tracks"])
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=0)
    sequence = copy.deepcopy(value["manual"]["sequence"])
    sequence_tracks = copy.deepcopy(value["manual"]["source_tracks"])
    edit(value, "reset")
    assert not has_sequence(value)
    assert value["manual"]["source_tracks"] == original_tracks
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["sequence"] == sequence
    assert value["manual"]["source_tracks"] == sequence_tracks
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"]
    assert value["manual"]["source_tracks"] == original_tracks
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["source_tracks"] == sequence_tracks


@pytest.mark.parametrize("action,payload", [
    ("move", {"slot": "A", "clip_id": "A:sequence:1:0", "start": -1}),
    ("move", {"slot": "A", "clip_id": "A:sequence:1:0", "start": 86400}),
    ("trim", {"slot": "A", "clip_id": "A:sequence:1:0", "start": 4, "end": 12, "source_start": 15}),
    ("split", {"slot": "A", "time": float("nan")}),
    ("insert", {"slot": "B", "start": 1, "source_start": 19, "source_end": 21}),
    ("remove_range", {"slot": "A", "start": 1, "end": 11}),
])
def test_invalid_sequence_operation_is_fully_atomic(action, payload):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        edit(value, action, **payload)
    assert value == before


def test_virtual_noops_never_materialize_or_consume_history():
    value = project()
    before = copy.deepcopy(value)
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=4)
    edit(value, "split", slot="A", time=4)
    edit(value, "reset")
    assert value == before


def test_layout_can_be_applied_to_virtual_compact_clock_before_first_clip_edit():
    value = project()
    original_plan = copy.deepcopy(value["draft"]["camera_plan"])
    edit(value, "layout", start=5, end=8, layout="pip")
    assert has_sequence(value)
    assert value["manual"]["sequence"]["camera_plan"] == [
        {"start": 0, "end": 4, "camera": "stacked"}, {"start": 4, "end": 5, "camera": "A"},
        {"start": 5, "end": 8, "camera": "pip"}, {"start": 8, "end": 10, "camera": "A"},
    ]
    assert value["draft"]["camera_plan"] == original_plan


def test_b_lifecycle_preserves_sequence_clock_and_a_but_discards_b_reset_provenance():
    from server import _reset_manual_after_source_change

    value = project()
    value["manual"]["source_tracks"] = {"B": [{"id": "old-B", "start": 0, "end": 20, "source_start": 0}]}
    edit(value, "move", slot="A", clip_id="A:sequence:1:0", start=24)
    a_clips = copy.deepcopy(value["manual"]["source_tracks"]["A"])
    _reset_manual_after_source_change(value, "B", replacing=True)
    assert timeline_duration(value) == 30
    assert value["manual"]["source_tracks"] == {"A": a_clips, "B": []}
    assert "B" not in value["manual"]["sequence"]["base_source_tracks"]
    _reset_manual_after_source_change(value, "A", replacing=True)
    assert not has_sequence(value)
    assert "source_tracks" not in value["manual"]


def test_60fps_clip_is_not_dropped_by_30fps_export_override():
    value, _ = materialize_sequence(project())
    value["settings"]["fps"] = 60
    value["manual"]["source_tracks"]["A"] = [{"id": "one-frame", "start": 0, "end": 1 / 60, "source_start": 0}]
    assert len(source_track_clips(value, "A")) == 1
    value["settings"]["fps"] = 30
    assert len(source_track_clips(value, "A")) == 1


@pytest.mark.parametrize("default,primary,expected", [
    ("stacked", "screen", "stacked"), ("pip", "camera", "pip"),
    ("auto", "camera", "camera"), (None, "screen", "screen"),
])
def test_sequence_auto_layout_inherits_mixer_default_or_primary_role(default, primary, expected):
    value = project()
    value["manual"]["source_mixer"] = {
        "screen_slot": "B", "camera_slot": "A", "default_layout": default,
        "primary_role": primary,
    }
    edit(value, "layout", start=5, end=8, layout="auto")
    rows = value["manual"]["sequence"]["camera_plan"]
    assert next(row for row in rows if row["start"] == 5)["camera"] == expected
    assert all(row["camera"] != "auto" for row in rows)
    assert rows[0] == {"start": 0, "end": 4, "camera": "stacked"}


@pytest.mark.parametrize("embedded", [False, True])
def test_sequence_auto_single_source_never_invents_b_and_preserves_embedded_framing(embedded):
    value = project()
    value["sources"]["B"] = None
    value["manual"]["source_mixer"] = {"default_layout": "stacked", "primary_role": "camera"}
    if embedded:
        value["draft"]["layout"] = "embedded_stack"
    edit(value, "layout", start=5, end=8, layout="auto")
    row = next(row for row in value["manual"]["sequence"]["camera_plan"] if row["start"] == 5)
    assert row["camera"] == ("embedded_stack" if embedded else "A")
