from __future__ import annotations

import copy

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.source_tracks import (
    MAX_TRACK_CLIPS, has_source_tracks, source_track_boundaries,
    source_track_clips, track_at,
)


def project(offset=2.0):
    return {
        "sources": {"A": {"duration": 20.0, "has_audio": True}, "B": {"duration": 10.0, "has_audio": True}},
        "analysis": {"sync": {"offset": offset}},
        "manual": {},
        "draft": {
            "cuts": [{"start": 8.0, "end": 10.0}],
            "keep_ranges": [{"start": 0.0, "end": 8.0}, {"start": 10.0, "end": 20.0}],
            "camera_plan": [{"start": 0.0, "end": 20.0, "camera": "stacked"}],
            "output_duration": 18.0, "removed_duration": 2.0,
        },
    }


def edit(value, action, slot="B", **kwargs):
    return apply_manual_edit(value, {"action": f"track_{action}", "slot": slot, **kwargs})


def geometry(value, slot="B"):
    return [(clip["start"], clip["end"], clip["source_start"]) for clip in source_track_clips(value, slot)]


def mixer(**kwargs):
    return {"action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A", **kwargs}


def test_implicit_mappings_are_detached_and_do_not_create_manual_state():
    value = project()
    before = copy.deepcopy(value)
    assert source_track_clips(value, "A") == [{"id": "A:base", "start": 0, "end": 20, "source_start": 0}]
    assert source_track_clips(value, "B") == [{"id": "B:base", "start": 2, "end": 12, "source_start": 0}]
    assert source_track_boundaries(value) == [0, 2, 12, 20]
    assert not has_source_tracks(value)
    source_track_clips(value, "A")[0]["start"] = 8
    assert value == before


@pytest.mark.parametrize("offset,expected", [(-2, [(0, 8, 2)]), (18, [(18, 20, 0)]), (25, []), (-11, [])])
def test_implicit_b_offset_clips_to_a_axis(offset, expected):
    assert geometry(project(offset)) == expected


def test_manual_sync_override_and_half_open_lookup():
    value = project()
    value["manual"]["source_mixer"] = {"sync_offset": -3}
    assert geometry(value) == [(0, 7, 3)]
    assert track_at(value, "B", 0)["source_start"] == 3
    assert track_at(value, "B", 7) is None
    assert track_at(value, "B", float("nan")) is None
    value["sources"]["B"] = None
    assert source_track_clips(value, "B") == []
    assert source_track_clips(value, "Z") == []


def test_split_is_per_source_and_preserves_story_and_other_source():
    value = project()
    draft = copy.deepcopy(value["draft"])
    edit(value, "split", time=6)
    assert geometry(value) == [(2, 6, 0), (6, 12, 4)]
    assert geometry(value, "A") == [(0, 20, 0)]
    assert source_track_clips(value, "B")[0]["id"] == "B:base"
    assert len({clip["id"] for clip in source_track_clips(value, "B")}) == 2
    for key in draft:
        assert value["draft"][key] == draft[key]
    assert has_source_tracks(value)


def test_remove_leaves_gap_does_not_ripple_or_change_source_mapping():
    value = project()
    edit(value, "remove_range", start=4, end=7)
    assert geometry(value) == [(2, 4, 0), (7, 12, 5)]
    assert track_at(value, "B", 5) is None
    assert value["draft"]["output_duration"] == 18
    assert geometry(value, "A") == [(0, 20, 0)]


def test_remove_entire_source_is_explicit_empty_not_implicit_fallback():
    value = project()
    edit(value, "remove_range", start=0, end=20)
    assert value["manual"]["source_tracks"] == {"B": []}
    assert source_track_clips(value, "B") == []
    assert has_source_tracks(value)


def test_move_changes_timeline_location_not_source_start():
    value = project()
    edit(value, "move", clip_id="B:base", start=8)
    assert geometry(value) == [(8, 18, 0)]
    assert geometry(value, "A") == [(0, 20, 0)]
    assert track_at(value, "B", 9)["source_start"] + 9 - track_at(value, "B", 9)["start"] == 1


def test_trim_and_slip_have_explicit_source_mapping():
    value = project()
    edit(value, "trim", clip_id="B:base", start=4, end=8, source_start=1)
    assert geometry(value) == [(4, 8, 1)]
    edit(value, "trim", clip_id="B:base", start=4, end=8, source_start=5)
    assert geometry(value) == [(4, 8, 5)]


def test_restore_fills_only_gaps_using_default_mapping_without_overwriting_moved_clip():
    value = project()
    edit(value, "trim", clip_id="B:base", start=6, end=8, source_start=0)
    edit(value, "restore_range", start=0, end=20)
    assert geometry(value) == [(2, 6, 0), (6, 8, 0), (8, 12, 6)]
    assert source_track_clips(value, "B")[1]["id"] == "B:base"


def test_restore_negative_offset_uses_local_source_time():
    value = project(-2)
    edit(value, "remove_range", start=0, end=20)
    edit(value, "restore_range", start=1, end=3)
    assert geometry(value) == [(1, 3, 3)]


def test_undo_redo_preserves_absence_and_generated_ids():
    value = project()
    edit(value, "split", time=6)
    clips = copy.deepcopy(value["manual"]["source_tracks"])
    apply_manual_edit(value, {"action": "undo"})
    assert "source_tracks" not in value["manual"]
    assert geometry(value) == [(2, 12, 0)]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["source_tracks"] == clips
    edit(value, "reset")
    assert "source_tracks" not in value["manual"]
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["source_tracks"] == clips


def test_reset_one_track_preserves_the_other():
    value = project()
    edit(value, "split", slot="A", time=5)
    edit(value, "remove_range", start=0, end=20)
    edit(value, "reset", slot="A")
    assert value["manual"]["source_tracks"] == {"B": []}


@pytest.mark.parametrize("action,kwargs", [
    ("split", {"time": 2}), ("remove_range", {"start": 0, "end": 1}),
    ("restore_range", {"start": 4, "end": 5}), ("move", {"clip_id": "B:base", "start": 2}),
    ("trim", {"clip_id": "B:base", "start": 2, "end": 12, "source_start": 0}), ("reset", {}),
])
def test_noop_has_no_mutation_or_history(action, kwargs):
    value = project()
    before = copy.deepcopy(value)
    edit(value, action, **kwargs)
    assert value == before


def test_noop_preserves_redo():
    value = project()
    edit(value, "split", time=6)
    apply_manual_edit(value, {"action": "undo"})
    before = copy.deepcopy(value)
    edit(value, "restore_range", start=4, end=5)
    assert value == before


@pytest.mark.parametrize("action,kwargs", [
    ("split", {"time": 2.01}), ("split", {"time": 1}), ("split", {"time": float("nan")}),
    ("remove_range", {"start": -1, "end": 3}), ("remove_range", {"start": 4, "end": 21}),
    ("remove_range", {"start": 4, "end": 3}), ("remove_range", {"start": 2.01, "end": 4}),
    ("restore_range", {"start": 1, "end": 1.01}), ("restore_range", {"start": True, "end": 4}),
    ("move", {"clip_id": "B:base", "start": 11}), ("move", {"clip_id": "missing", "start": 1}),
    ("trim", {"clip_id": "B:base", "start": 2, "end": 12, "source_start": 1}),
    ("trim", {"clip_id": "B:base", "start": 2, "end": 4, "source_start": -1}),
    ("trim", {"clip_id": "B:base", "start": 2, "end": float("inf"), "source_start": 0}),
])
def test_invalid_edit_is_atomic(action, kwargs):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        edit(value, action, **kwargs)
    assert value == before


def test_same_track_collision_rejected_not_overwritten():
    value = project()
    edit(value, "split", time=6)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="overlap"):
        edit(value, "move", clip_id="B:base", start=4)
    assert value == before


def test_minimum_80ms_clips_allow_floating_point_boundaries():
    value = project(0)
    edit(value, "trim", clip_id="B:base", start=.1, end=.18, source_start=.1)
    assert geometry(value) == [(.1, .18, .1)]


def test_fragment_limit_and_persisted_invalid_data_are_rejected_atomically():
    value = project(0)
    value["sources"]["A"]["duration"] = value["sources"]["B"]["duration"] = 1000
    value["manual"]["source_tracks"] = {"B": [
        {"id": f"B:{i}", "start": i * 2, "end": i * 2 + 1, "source_start": i * 2}
        for i in range(MAX_TRACK_CLIPS)
    ]}
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="200"):
        edit(value, "split", time=.5)
    assert value == before


def test_read_helpers_fail_closed_and_edits_reject_corrupt_clips():
    value = project()
    value["manual"]["source_tracks"] = {"B": [
        {"id": "good", "start": 2, "end": 4, "source_start": 0},
        {"id": "overlap", "start": 3, "end": 5, "source_start": 0},
        {"id": "nan", "start": float("nan"), "end": 8, "source_start": 0},
        {"id": "past-media", "start": 8, "end": 10, "source_start": 9},
    ]}
    assert [clip["id"] for clip in source_track_clips(value, "B")] == ["good"]
    with pytest.raises(ManualEditError):
        edit(value, "move", clip_id="good", start=0)
    edit(value, "reset")
    assert geometry(value) == [(2, 12, 0)]


def test_no_draft_or_missing_track_cannot_be_edited():
    value = project()
    value.pop("draft")
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="draft"):
        edit(value, "split", time=6)
    assert value == before
    value = project()
    value["sources"]["B"] = None
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="existing"):
        edit(value, "split", time=6)
    assert value == before


def test_explicit_b_freezes_effective_sync_but_roles_and_audio_remain_editable():
    value = project()
    edit(value, "split", time=6)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Reset source B"):
        apply_manual_edit(value, mixer(sync_offset=3))
    assert value == before
    apply_manual_edit(value, mixer(sync_offset=2, audio_slot="B", screen_slot="B", camera_slot="A"))
    assert geometry(value) == [(2, 6, 0), (6, 12, 4)]
    assert value["manual"]["source_mixer"]["audio_slot"] == "B"
    apply_manual_edit(value, mixer(sync_offset=None))  # Analysis offset is also 2.
    assert geometry(value) == [(2, 6, 0), (6, 12, 4)]


def test_explicit_empty_b_also_freezes_sync_until_reset():
    value = project()
    edit(value, "remove_range", start=0, end=20)
    with pytest.raises(ManualEditError, match="Reset source B"):
        apply_manual_edit(value, mixer(sync_offset=0))
    edit(value, "reset")
    apply_manual_edit(value, mixer(sync_offset=0))
    assert geometry(value) == [(0, 10, 0)]


def test_a_only_edits_do_not_freeze_b_sync_and_global_story_edits_preserve_tracks():
    value = project()
    edit(value, "split", slot="A", time=5)
    tracks = copy.deepcopy(value["manual"]["source_tracks"])
    apply_manual_edit(value, mixer(sync_offset=0))
    assert geometry(value) == [(0, 10, 0)]
    apply_manual_edit(value, {"action": "delete_range", "start": 2, "end": 4})
    assert value["manual"]["source_tracks"] == tracks
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["source_tracks"] == tracks


@pytest.mark.parametrize("replacing", [False, True])
@pytest.mark.parametrize("a_clips", [[], [{"id": "A:moved", "start": 2, "end": 8, "source_start": 1}]])
def test_b_lifecycle_change_preserves_explicit_a_only_and_clears_stale_history(replacing, a_clips):
    from server import _reset_manual_after_source_change

    value = project()
    value["manual"]["source_tracks"] = {
        "A": copy.deepcopy(a_clips), "B": [{"id": "B:old", "start": 2, "end": 4, "source_start": 0}],
    }
    value["manual"]["_history"] = {"undo": [{"old": True}], "redo": []}
    previous_tracks = value["manual"]["source_tracks"]
    if not replacing:
        value["sources"]["B"] = None
    _reset_manual_after_source_change(value, "B", replacing=replacing)
    assert value["manual"]["source_tracks"] == {"A": a_clips}
    assert "_history" not in value["manual"]
    assert value["manual"]["history"] == {"undo_count": 0, "redo_count": 0}
    previous_tracks["A"].append({"id": "stale"})
    assert value["manual"]["source_tracks"] == {"A": a_clips}


@pytest.mark.parametrize("slot", ["A", "B"])
def test_source_change_does_not_materialize_implicit_tracks(slot):
    from server import _reset_manual_after_source_change

    value = project()
    _reset_manual_after_source_change(value, slot, replacing=True)
    assert "source_tracks" not in value["manual"]


@pytest.mark.parametrize("replacing", [False, True])
def test_a_lifecycle_change_discards_both_clip_maps(replacing):
    from server import _reset_manual_after_source_change

    value = project()
    edit(value, "split", slot="A", time=5)
    edit(value, "split", slot="B", time=6)
    if not replacing:
        value["sources"]["A"] = None
    _reset_manual_after_source_change(value, "A", replacing=replacing)
    assert "source_tracks" not in value["manual"]
    assert "_history" not in value["manual"]
