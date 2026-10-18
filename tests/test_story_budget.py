from __future__ import annotations

import copy

import pytest

from cutroom.story_budget import (
    StoryBudgetError, StoryPlanningError, compact_story_pauses_to_target, framed_story_duration,
    segment_speech_ranges, story_duration_cost,
)
from cutroom.utils import range_duration


def segment(identifier, start, end, spans):
    words = [{"word": f"word{i}", "start": left, "end": right}
             for i, (left, right) in enumerate(spans)]
    return {"id": identifier, "start": start, "end": end,
            "text": " ".join(word["word"] for word in words) + ".", "words": words}


def approved_english():
    # Passage and cost structure of the 27.09s failure; word details are synthetic.
    segments = [segment("premise", 8.41, 29.5, [
        (8.41, 10.01), (10.78, 12.5), (12.68, 13.84), (14.16, 16.46),
        (16.74, 17.44), (18.24, 19.64), (20.34, 21.8), (22.26, 23.18),
        (23.67, 24.45), (25.48, 27.14), (27.36, 29.5),
    ]), segment("ending", 35.31, 41.31, [(35.31, 35.79), (39.55, 40.59), (40.93, 41.31)])]
    ranges = [{"start": row["start"], "end": row["end"]} for row in segments]
    return segments, ranges


def test_old_2709_second_selection_is_priced_and_fitted_by_one_policy():
    segments, ranges = approved_english()
    original = copy.deepcopy((segments, ranges))
    cost = story_duration_cost(ranges, segments, 45, target=20)
    fitted = compact_story_pauses_to_target(ranges, segments, 45, 20)
    assert cost["approved_seconds"] == 27.09
    assert cost["protected_speech_seconds"] == 17.74
    assert cost["minimum_safe_seconds"] == 19.34
    assert cost["fits_target"] is True
    assert range_duration(fitted) == 20
    for row in segments:
        for word in row["words"]:
            covered = sum(max(0, min(word["end"], keep["end"]) - max(word["start"], keep["start"]))
                          for keep in fitted)
            assert covered == pytest.approx(word["end"] - word["start"], abs=.001)
    assert all(keep["start"] >= 8.41 for keep in fitted)
    assert (segments, ranges) == original


def test_required_intro_can_make_the_same_english_material_infeasible():
    segments, ranges = approved_english()
    intro = segment("intro", .59, 2.93, [(.59, 1.59), (1.93, 2.93)])
    segments.insert(0, intro)
    ranges.insert(0, {"start": .59, "end": 2.93})
    cost = story_duration_cost(ranges, segments, 45, target=20)
    assert cost["protected_speech_seconds"] == 19.74
    assert cost["minimum_safe_seconds"] == 21.46
    assert cost["minimum_safe_seconds"] > 20
    assert cost["fits_target"] is False
    assert compact_story_pauses_to_target(ranges, segments, 45, 20) is None


@pytest.mark.parametrize("corruption", ["missing_word", "malformed_word", "known_partial", "missing_all"])
def test_incomplete_timing_cannot_make_missing_speech_a_pause(corruption):
    row = segment("speech", 0, 10, [(0, 1), (4, 6), (9, 10)])
    if corruption == "missing_word":
        row["words"].pop(1)
    elif corruption == "malformed_word":
        row["words"][1]["start"] = None
    elif corruption == "known_partial":
        row["word_timing_complete"] = False
    else:
        row.pop("words")
    assert segment_speech_ranges(row) == [{"start": 0, "end": 10}]
    cost = story_duration_cost([{"start": 0, "end": 10}], [row], 10, target=4)
    assert cost["minimum_safe_seconds"] == 10
    assert compact_story_pauses_to_target([{"start": 0, "end": 10}], [row], 10, 4) is None


def test_action_and_untranscribed_passages_do_not_receive_a_speech_discount():
    rows = [segment("words", 0, 10, [(0, 1), (9, 10)])]
    ranges = [{"start": 0, "end": 10}, {"start": 15, "end": 20}]
    cost = story_duration_cost(ranges, rows, 20, target=10, protect_action_span=True)
    assert cost["minimum_safe_seconds"] == 15
    assert compact_story_pauses_to_target(ranges, rows, 20, 10, protect_action_span=True) is None
    speech_cost = story_duration_cost(ranges, rows, 20, target=10)
    assert speech_cost["minimum_safe_seconds"] >= 7
    fitted = compact_story_pauses_to_target(ranges, rows, 20, 10)
    assert fitted[-1] == {"start": 15, "end": 20}


def test_tiny_endpoint_word_survives_exact_subtraction():
    row = segment("tiny", 0, 2, [(0, .01), (1.5, 2)])
    cost = story_duration_cost([{"start": 0, "end": 2}], [row], 2, target=.7)
    fitted = compact_story_pauses_to_target([{"start": 0, "end": 2}], [row], 2, .7)
    assert cost["fits_target"] is True
    assert fitted[0]["start"] == 0
    assert fitted[0]["end"] >= .01
    assert range_duration(fitted) == pytest.approx(.7, abs=.001)


@pytest.mark.parametrize("offset,expected", [(-.051, False), (-.05, True), (0, True), (.2, True)])
def test_cost_and_actual_fitter_agree_at_the_budget_tolerance(offset, expected):
    row = segment("speech", 0, 5, [(0, 1), (4, 5)])
    ranges = [{"start": 0, "end": 5}]
    minimum = story_duration_cost(ranges, [row], 5)["minimum_safe_seconds"]
    target = minimum + offset
    cost = story_duration_cost(ranges, [row], 5, target=target)
    fitted = compact_story_pauses_to_target(ranges, [row], 5, target)
    assert cost["fits_target"] is expected
    assert (fitted is not None) is expected


def test_failure_diagnostic_is_a_detached_specific_planning_error():
    diagnostic = {"scope": "current_required_selection", "required_policy_minimum_seconds": 21.8}
    error = StoryBudgetError("No draft applied; required story needs 21.8 seconds.", diagnostic)
    diagnostic["required_policy_minimum_seconds"] = 0
    assert isinstance(error, StoryPlanningError)
    assert error.diagnostic["required_policy_minimum_seconds"] == 21.8


def test_frame_grid_overhead_is_priced_and_cannot_silently_exceed_the_target(monkeypatch):
    from cutroom import render
    row = segment("speech", 0, 4, [(0, .457), (1.543, 2.457), (3.543, 4)])
    ranges = [{"start": 0, "end": 4}]
    cost = story_duration_cost(ranges, [row], 4, target=2.068, fps=30)
    assert cost["minimum_safe_seconds"] == 2.068
    assert cost["minimum_framed_seconds"] == pytest.approx(2.133333)
    assert cost["fits_target"] is False
    assert compact_story_pauses_to_target(ranges, [row], 4, 2.068, fps=30) is None
    fitted = compact_story_pauses_to_target(ranges, [row], 4, 2.2, fps=30)
    monkeypatch.setattr(render, "_render_plan", lambda _project: fitted)
    aligned = render._frame_aligned_plan({"settings": {"fps": 30}})
    actual = sum(row["end"] - row["start"] for row in aligned)
    assert framed_story_duration(fitted, 30) == pytest.approx(actual, abs=1e-6)
    assert actual <= 2.25


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_approved_english_fit_remains_in_budget_on_each_supported_frame_grid(fps):
    rows, ranges = approved_english()
    fitted = compact_story_pauses_to_target(ranges, rows, 45, 20, fps=fps)
    assert fitted is not None
    assert framed_story_duration(fitted, fps) <= 20.05
