from __future__ import annotations

import pytest

from cutroom import director
from cutroom.edit_styles import get_edit_style
from cutroom.utils import invert_ranges, range_duration


def _target_policy(style="stream_story"):
    return {**get_edit_style(style)["selection_policy"], "duration_mode": "target"}


def _approved_pause_fixture():
    # An anonymized failure structure: a 21.09s approved passage plus a 6s
    # ending. Their timestamped speech fits a 20s edit; their pauses do not.
    rows = [
        ("setup", 8.41, 29.5, [
            (8.41, 10.48), (10.78, 12.5), (12.68, 13.84), (14.16, 16.46),
            (16.74, 17.44), (18.24, 19.64), (20.34, 21.8), (22.26, 23.18),
            (23.67, 24.45), (25.48, 27.14), (27.36, 29.5),
        ]),
        ("ending", 35.31, 41.31, [(35.31, 35.79), (39.55, 40.59), (40.93, 41.31)]),
    ]
    segments = [{
        "id": identifier, "start": start, "end": end,
        "text": " ".join(f"word{index}" for index in range(len(words))) + ".",
        "editorial_score": .8,
        "words": [{"start": a, "end": b, "word": f"word{index}"}
                  for index, (a, b) in enumerate(words)],
    } for identifier, start, end, words in rows]
    decision = {
        "keep_ids": ["setup", "ending"], "opening_id": "setup", "closing_id": "ending",
        "story_beat_ids": ["setup", "ending"],
        "story_ranges": [{"start": row["start"], "end": row["end"], "beat_id": row["id"]}
                         for row in segments],
        "rejected_story_ranges": [{"start": .5, "end": 2.9}],
        "story_requirements": {"required_beat_ids": ["setup", "ending"],
                               "critic_requested_beat_ids": [], "unresolved_slot_indexes": [],
                               "unapplied_critic_actions": 0},
    }
    return segments, decision


def test_approved_over_budget_story_fits_speech_pauses_before_whole_passage_pruning():
    segments, decision = _approved_pause_fixture()
    selected = director._select_short_story_ranges(
        segments, decision, 45, 20, selection_policy=_target_policy(),
    )
    assert range_duration(selected) == pytest.approx(20, abs=.001)
    for segment in segments:
        for word in segment["words"]:
            covered = sum(max(0, min(word["end"], r["end"]) - max(word["start"], r["start"]))
                          for r in selected)
            assert covered == pytest.approx(word["end"] - word["start"], abs=.001)
    assert not any(r["start"] < 2.9 and r["end"] > .5 for r in selected)
    assert "speech_pause_fit" in [row["stage"] for row in decision["_selection_trace"]]
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, segments, selected, 45, decision=decision,
    )
    assert review["selection_review"]["status"] == "unchanged"
    assert "story_anchor_missing" not in [row["type"] for row in review["warnings"]]


def test_pause_fitting_is_conservative_without_complete_word_timing():
    segments, decision = _approved_pause_fixture()
    segments[0]["words"][0]["start"] = None
    selected = director._compact_story_pauses_to_target(
        decision["story_ranges"], segments, 45, 20,
    )
    assert selected is None


def test_normalization_cannot_turn_dropped_word_timings_into_removable_pauses():
    raw = {"language": "en", "segments": [{
        "id": "speech", "start": 0, "end": 20, "text": "First missing speech last.",
        "words": [{"word": "First", "start": 0, "end": 1},
                  {"word": "missing speech", "start": None, "end": None},
                  {"word": "last.", "start": 19, "end": 20}],
    }]}
    normalized, _ = director._normalize_transcript(raw, "en", 20)
    cached, _ = director._normalize_transcript(normalized, "en", 20)
    assert director._compact_story_pauses_to_target(
        [{"start": 0, "end": 20}], cached["segments"], 20, 8,
    ) is None
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, cached["segments"],
        [{"start": 0, "end": 1}, {"start": 19, "end": 20}], 20,
        decision={"story_ranges": [{"start": 0, "end": 20}]},
    )
    assert review["selection_review"]["status"] == "changed"
    assert review["selection_review"]["partial_segment_ids"] == ["speech"]


def test_legacy_flagless_partial_word_cache_does_not_prove_the_middle_is_a_pause():
    legacy = {"language": "en", "segments": [{
        "id": "speech", "start": 0, "end": 20, "text": "First missing speech last.",
        "words": [{"word": "First", "start": 0, "end": 1},
                  {"word": "last.", "start": 19, "end": 20}],
    }]}
    normalized, _ = director._normalize_transcript(legacy, "en", 20)
    assert director._compact_story_pauses_to_target(
        [{"start": 0, "end": 20}], normalized["segments"], 20, 8,
    ) is None


def test_action_protection_does_not_turn_word_gaps_into_action_cuts():
    segments, decision = _approved_pause_fixture()
    director._select_short_story_ranges(
        segments, decision, 45, 20, selection_policy=_target_policy("competitive_clutch"),
    )
    assert "speech_pause_fit" not in [row["stage"] for row in decision.get("_selection_trace", [])]


def test_new_story_requirements_do_not_top_up_with_unapproved_beats():
    segments = [
        {"id": "approved", "start": 30, "end": 38.39, "text": "A complete approved statement.", "editorial_score": .8},
        {"id": "unapproved", "start": 5, "end": 8, "text": "Other footage.", "editorial_score": 1.0},
    ]
    decision = {
        "story_ranges": [{"start": 30, "end": 38.39, "beat_id": "approved"}],
        "story_beat_ids": ["approved"],
        "story_requirements": {"required_beat_ids": ["approved"], "critic_requested_beat_ids": []},
    }
    selected = director._select_short_story_ranges(
        segments, decision, 45, 20, selection_policy=_target_policy(),
        story_beats=[{**row, "segment_ids": [row["id"]]} for row in segments],
    )
    assert selected == [{"start": 30, "end": 38.39}]


def test_short_source_shortcut_keeps_only_the_approved_story():
    segments = [{"id": "approved", "start": 30, "end": 38.39}]
    decision = {"story_ranges": [{"start": 30, "end": 38.39, "beat_id": "approved"}],
                "story_requirements": {"required_beat_ids": ["approved"]}}
    selected = director._select_short_story_ranges(
        segments, decision, 45, 60, selection_policy=_target_policy(),
    )
    assert selected == [{"start": 30, "end": 38.39}]


@pytest.mark.parametrize("output,unresolved,unapplied,reasons", [
    (8.39, [], 0, {"selected_material_under_target"}),
    (20, [1], 0, {"unresolved_story_slots"}),
    (20, [], 1, {"unapplied_critic_actions"}),
])
def test_target_feasibility_names_the_current_selection_limit(output, unresolved, unapplied, reasons):
    review = director._duration_review(
        {"goal": "short", "target_duration": 20, "duration_mode": "target"}, 45, output,
        decision={"story_requirements": {"unresolved_slot_indexes": unresolved,
                                         "unapplied_critic_actions": unapplied}},
    )
    feasibility = review["target_feasibility"]
    assert feasibility["status"] == "limited"
    assert feasibility["scope"] == "current_selection"
    assert feasibility["supported_seconds"] == output
    assert reasons <= set(feasibility["reasons"])
    assert feasibility["unresolved_slot_indexes"] == unresolved
    assert feasibility["unapplied_critic_actions"] == unapplied
    assert "maximum_supported_seconds" not in feasibility


def test_duration_met_without_outstanding_requirements_has_met_assessment():
    review = director._duration_review(
        {"goal": "short", "target_duration": 20, "duration_mode": "target"}, 45, 20,
    )
    assert review["target_feasibility"]["status"] == "met"


def test_available_source_ceiling_does_not_claim_the_larger_requested_target_was_met():
    review = director._duration_review(
        {"goal": "short", "target_duration": 60, "duration_mode": "target"}, 45, 45,
    )
    assert review["target_feasibility"]["status"] == "limited"
    assert "source_shorter_than_requested" in review["target_feasibility"]["reasons"]
    assert "45.0s of the requested 60.0s" in director._target_completion_message(review)


def test_real_spoken_micro_fragment_survives_pause_fitting_cleanup():
    cuts = invert_ranges([{"start": 10, "end": 10.48}, {"start": 20, "end": 24}], 45)
    result, count = director._drop_isolated_micro_keeps(
        cuts, 45, protected_ranges=[{"start": 10, "end": 10.48}],
    )
    assert result == cuts
    assert count == 0
