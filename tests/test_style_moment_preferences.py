"""A preset's moment preference cannot become a hard user requirement."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import director, intelligence
from cutroom.edit_styles import enrich_brief_with_style, get_edit_style
from cutroom.instruction_contract import build_instruction_contract
from cutroom.story_budget import StoryBudgetError


INSTRUCTIONS = (
    "Include 3 moments.",
    "\u05db\u05dc\u05d5\u05dc 3 \u05e8\u05d2\u05e2\u05d9\u05dd.",
)


def brief(instruction, mode):
    value = {"goal": "short", "edit_style": "competitive_clutch", "target_duration": 60,
             "instruction": instruction}
    if mode is not None:
        value["duration_mode"] = mode
    return enrich_brief_with_style(value)


@pytest.mark.parametrize("instruction", INSTRUCTIONS, ids=["english", "hebrew"])
@pytest.mark.parametrize("mode", [None, "style", "target"], ids=["older_project", "style", "target"])
def test_moment_preference_is_advisory_and_unverified_count_request_is_preserved(instruction, mode):
    value = brief(instruction, mode)
    policy = value["style_profile"]["selection_policy"]
    assert value["instruction"] == instruction
    assert policy["max_moments"] is None
    assert policy["preferred_max_moments"] == 1
    assert "Keep at most" not in value["style_profile"]["guidance"]
    contract = build_instruction_contract(value)
    assert contract["instruction"] == instruction
    assert contract["verification_status"] == "unverified"
    assert all(row["status"] != "fulfilled" for row in contract["requirements"])
    # A semantic moment is not established by counting source ranges.
    assert get_edit_style("competitive_clutch")["selection_policy"]["max_moments"] == 1


@pytest.mark.parametrize("mode", ["style", "target"])
def test_selected_style_preferences_are_copied_without_mutating_user_controls(mode):
    raw = {"goal": "short", "edit_style": "competitive_clutch", "target_duration": 60,
           "duration_mode": mode, "instruction": "Include 3 moments.", "pace": "gentle"}
    before = copy.deepcopy(raw)
    value = enrich_brief_with_style(raw)
    assert raw == before
    assert all(value[key] == expected for key, expected in before.items())
    value["style_profile"]["selection_policy"]["preferred_max_moments"] = 99
    assert enrich_brief_with_style(raw)["style_profile"]["selection_policy"]["preferred_max_moments"] == 1


@pytest.mark.parametrize("instruction", INSTRUCTIONS, ids=["english", "hebrew"])
@pytest.mark.parametrize("mode", ["style", "target"])
def test_planner_receives_raw_request_without_a_style_owned_hard_moment_cap(monkeypatch, instruction, mode):
    class Settings:
        ai = {}

    captured = []

    def respond(_settings, payload, *_args):
        captured.append(copy.deepcopy(payload))
        return {"narrative": "Three source-supported passages.", "slots": [
            {"purpose": role, "chapter_ids": ["chapter"], "desired_seconds": 8}
            for role in ("context", "explanation", "conclusion")
        ]}

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    result = intelligence._build_story_plan(Settings(), [{"id": "chapter"}], {}, brief(instruction, mode), "fixture")
    assert len(captured) == 1
    assert [slot["purpose"] for slot in result["slots"]] == ["context", "explanation", "conclusion"]
    assert "Select at most" not in captured[0]["messages"][0]["content"]
    passed = json.loads(captured[0]["messages"][1]["content"])["brief"]
    assert passed["instruction"] == instruction
    assert passed["style_profile"]["selection_policy"]["max_moments"] is None
    assert passed["style_profile"]["selection_policy"]["preferred_max_moments"] == 1


@pytest.mark.parametrize("instruction", INSTRUCTIONS, ids=["english", "hebrew"])
@pytest.mark.parametrize("mode", ["style", "target"])
def test_complete_selected_passages_survive_without_a_style_count_or_unrelated_padding(instruction, mode):
    segments = [{"id": str(index), "start": start, "end": start + 8,
                 "text": "A complete source idea.", "editorial_score": 0.8}
                for index, start in enumerate((10.0, 110.0, 210.0))]
    decision = {"story_ranges": copy.deepcopy(segments)}
    before = copy.deepcopy(segments)
    kept = director._select_short_story_ranges(segments, decision, 300, 60,
                                               selection_policy=brief(instruction, mode)["style_profile"]["selection_policy"])
    assert kept == [{"start": 10.0, "end": 18.0}, {"start": 110.0, "end": 118.0}, {"start": 210.0, "end": 218.0}]
    assert segments == before


@pytest.mark.parametrize("mode", ["style", "target"])
def test_removing_the_style_cap_does_not_restore_rejected_source(mode):
    segments = [{"id": name, "start": start, "end": start + 8, "editorial_score": 0.8}
                for name, start in (("a", 10.0), ("rejected", 110.0), ("c", 210.0))]
    decision = {"story_ranges": copy.deepcopy(segments), "rejected_segment_ids": ["rejected"]}
    kept = director._select_short_story_ranges(segments, decision, 300, 60,
                                               selection_policy=brief(INSTRUCTIONS[0], mode)["style_profile"]["selection_policy"])
    assert kept == [{"start": 10.0, "end": 18.0}, {"start": 210.0, "end": 218.0}]


@pytest.mark.parametrize("mode", ["style", "target"])
def test_preferred_continuity_keeps_measured_event_boundaries_without_a_hard_count(mode):
    from test_highlight_diversity import _profile

    evidence = _profile(360, [(10, 20, -12, -4), (100, 110, -12, -4), (200, 210, -12, -4)], step=1)
    policy = brief(INSTRUCTIONS[0], mode)["style_profile"]["selection_policy"]
    kept = director._select_audio_highlight_ranges(evidence, 360, 90, selection_policy=policy)
    # Each activity event retains its preset's context handles; quiet timeline
    # regions are not added to manufacture the requested length or count.
    assert kept == [{"start": 4.0, "end": 23.0}, {"start": 94.0, "end": 113.0}, {"start": 194.0, "end": 213.0}]


@pytest.mark.parametrize("mode", ["style", "target"])
def test_no_measured_activity_is_not_repaired_with_arbitrary_windows(mode):
    from test_highlight_diversity import _profile

    policy = brief(INSTRUCTIONS[0], mode)["style_profile"]["selection_policy"]
    assert director._select_audio_highlight_ranges(_profile(360, [], step=1), 360, 90, selection_policy=policy) == []


@pytest.mark.parametrize("instruction", INSTRUCTIONS, ids=["english", "hebrew"])
def test_explicit_precision_no_fit_stays_a_no_fit_when_style_count_is_advisory(monkeypatch, instruction):
    from test_precision_contract import Settings, fixture

    beats, segments, chapters, plan, source_brief, _, _ = fixture()
    value = enrich_brief_with_style({**source_brief, "instruction": instruction,
                                    "edit_style": "competitive_clutch", "duration_mode": "style"})
    before = copy.deepcopy((beats, segments, chapters, plan, value))
    calls = []

    def refuse(_settings, payload, *_args):
        calls.append(payload)
        return {"verdict": "no_fit", "reason": "insufficient_context", "missing_purposes": ["result"]}

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", refuse)
    with pytest.raises(StoryBudgetError) as caught:
        intelligence._select_story_beats(Settings(), chapters, [], {}, plan, value, "fixture", segments=segments)
    assert len(calls) == 1
    assert caught.value.diagnostic["outcome"] == "editorial_no_fit"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert caught.value.diagnostic["precision"]["missing_purposes"] == ["result"]
    assert (beats, segments, chapters, plan, value) == before
