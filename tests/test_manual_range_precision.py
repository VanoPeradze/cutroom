"""Minimum-range arithmetic must not randomly reject decimal timecodes."""

import pytest

from cutroom.editing import ManualEditError, apply_camera_overrides, apply_manual_edit


def project():
    return {
        "id": "precision", "sources": {"A": {"duration": 400}, "B": {"duration": 400}},
        "manual": {}, "draft": {
            "keep_ranges": [{"start": 0, "end": 400}], "cuts": [],
            "camera_plan": [{"start": 0, "end": 400, "camera": "A"}],
            "output_duration": 400, "removed_duration": 0,
        },
    }


@pytest.mark.parametrize("start,end", [(0.10, 0.18), (1.10, 1.18), (300.10, 300.18)])
def test_exact_80ms_cut_can_be_deleted_restored_and_undone(start, end):
    value = project()
    apply_manual_edit(value, {"action": "delete_range", "start": start, "end": end})
    assert value["draft"]["cuts"] == [{"start": start, "end": end}]
    assert value["draft"]["output_duration"] == 399.92
    apply_manual_edit(value, {"action": "restore_range", "start": start, "end": end})
    assert value["draft"]["cuts"] == []
    assert value["draft"]["keep_ranges"] == [{"start": 0, "end": 400}]
    assert value["manual"]["keeps"] == [{"start": start, "end": end}]
    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["cuts"] == [{"start": start, "end": end}]


@pytest.mark.parametrize("start,end", [(0.10, 0.18), (1.10, 1.18), (300.10, 300.18)])
def test_exact_80ms_layout_survives_override_normalization_and_rebuild(start, end):
    value = project()
    apply_manual_edit(value, {"action": "set_camera_layout", "layout": "pip", "start": start, "end": end})
    assert value["manual"]["camera_overrides"] == [{"start": start, "end": end, "layout": "pip"}]
    expected = [
        {"start": 0, "end": start, "camera": "A"},
        {"start": start, "end": end, "camera": "pip"},
        {"start": end, "end": 400, "camera": "A"},
    ]
    assert value["draft"]["camera_plan"] == expected
    assert apply_camera_overrides(
        value["draft"]["ai_camera_plan"], value["draft"]["keep_ranges"],
        value["manual"]["camera_overrides"], has_b=True,
    ) == expected


@pytest.mark.parametrize("action", ["delete_range", "restore_range", "set_camera_layout"])
def test_precision_epsilon_does_not_admit_a_79ms_edit(action):
    value = project()
    with pytest.raises(ManualEditError, match="at least 0.08"):
        apply_manual_edit(value, {"action": action, "start": 0.10, "end": 0.179, "layout": "pip"})
    assert value["draft"]["keep_ranges"] == [{"start": 0, "end": 400}]


@pytest.mark.parametrize("fps", [30, 29.97, 59.94, 60])
def test_repeated_source_frame_nudges_survive_persistence_without_millisecond_drift(fps):
    value = project()
    for _ in range(100):
        offset = value["manual"].get("source_mixer", {}).get("sync_offset", 0)
        apply_manual_edit(value, {
            "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
            "primary_role": "screen", "audio_slot": "A", "first_slot": "B",
            "sync_offset": offset + 1 / fps,
        })
    assert value["manual"]["source_mixer"]["sync_offset"] == pytest.approx(100 / fps, abs=1e-7)
