"""An explicit one-passage request outranks the optional Shorts template."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.story_budget import StoryPlanningError


class Settings:
    ai = {"performance_mode": "balanced"}


REQUESTS = (
    "Choose one interesting self-contained segment from the conversation, about a minute long.",
    "בחר קטע אחד מעניין, ברור ועצמאי מתוך השיחה, באורך של כדקה.",
)


def request(text):
    return enrich_brief_with_style({"goal": "short", "target_duration": 60,
                                   "duration_mode": "target", "instruction": text})


def proposal(purposes=(intelligence.SINGLE_PASSAGE_PURPOSE,), seconds=60):
    return {"narrative": "One actual source idea, subject to later full-source review.", "slots": [
        {"purpose": purpose, "chapter_ids": ["c1", "c2"], "desired_seconds": seconds,
         "reason": "Candidate chapter domains are alternatives, not required coverage.",
         "required_context_chapter_ids": []} for purpose in purposes]}


def responder(monkeypatch, replies):
    calls = []
    def respond(_settings, payload, *_args):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(replies[min(len(calls) - 1, len(replies) - 1)])
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    return calls


@pytest.mark.parametrize("text", REQUESTS, ids=["english", "hebrew"])
def test_one_passage_uses_one_slot_without_artificial_story_roles(monkeypatch, text):
    calls = responder(monkeypatch, [proposal()])
    brief = request(text)
    before = copy.deepcopy(brief)
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, brief, "fixture")
    assert len(calls) == 1 and len(result["slots"]) == 1
    assert result["slots"][0]["chapter_ids"] == ["c1", "c2"]
    assert result["passage_constraint"]["semantic_unit_count"] == 1
    schema = calls[0]["format"]["properties"]["slots"]
    assert schema["minItems"] == schema["maxItems"] == 1
    assert schema["items"]["properties"]["purpose"]["enum"] == [intelligence.SINGLE_PASSAGE_PURPOSE]
    assert calls[0]["_single_attempt"] is True
    assert "hook, minimum context" not in calls[0]["messages"][0]["content"]
    assert "assemble distinct relevant complete" not in brief["style_profile"]["guidance"]
    assert json.loads(calls[0]["messages"][1]["content"])["brief"]["instruction"] == text
    assert brief == before


@pytest.mark.parametrize("text", REQUESTS, ids=["english", "hebrew"])
def test_invalid_multi_topic_template_is_replanned_not_silently_trimmed(monkeypatch, text):
    invalid = proposal(("hook", "setup", "proof", "payoff", "ending"), 18)
    original = copy.deepcopy(invalid)
    calls = responder(monkeypatch, [invalid, proposal()])
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, request(text), "fixture")
    assert len(calls) == 2 and result["slots"][0]["purpose"] == intelligence.SINGLE_PASSAGE_PURPOSE
    correction = json.loads(calls[1]["messages"][-1]["content"])["plan_correction"]
    assert correction["rejected_slot_count"] == 5 and correction["issues"]
    assert invalid == original


def test_an_unrequested_conclusion_is_replanned_as_a_neutral_source_passage(monkeypatch):
    calls = responder(monkeypatch, [proposal(("conclusion",)), proposal()])
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, request(REQUESTS[0]), "fixture")
    assert len(calls) == 2
    assert result["slots"][0]["purpose"] == intelligence.SINGLE_PASSAGE_PURPOSE
    assert "conclusion" in json.loads(calls[1]["messages"][-1]["content"])["plan_correction"]["issues"][0]


@pytest.mark.parametrize("seconds", [61, float("nan"), float("inf"), True, 0, -1])
def test_invalid_passage_allocation_fails_after_one_bounded_correction(monkeypatch, seconds):
    calls = responder(monkeypatch, [proposal(seconds=seconds)])
    with pytest.raises(StoryPlanningError) as caught:
        intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, request(REQUESTS[0]), "fixture")
    assert len(calls) == 2
    assert caught.value.diagnostic["reason"] == "single_passage_plan_conflict"
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("text,roles", [
    (REQUESTS[0] + " Structure: context -> result.", ("context", "result")),
    (REQUESTS[1] + " מבנה: הקשר -> תוצאה.", ("הקשר", "תוצאה")),
])
def test_explicit_roles_are_preserved_inside_the_same_single_passage(monkeypatch, text, roles):
    calls = responder(monkeypatch, [proposal(roles, 60)])
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, request(text), "fixture")
    assert len(calls) == 1
    assert [row["purpose"] for row in result["slots"]] == list(roles)
    assert all(row["origin"] == "user" for row in result["role_requirements"])
    assert result["passage_constraint"]["semantic_unit_count"] == 1
    assert calls[0]["format"]["properties"]["slots"].get("maxItems") != 1
    # Shared footage may support multiple roles: allocation hints are not union cost.


def canonical():
    return [{"id": "c1", "beats": [
        {"id": "b1", "start": 0, "end": 20},
        {"id": "b2", "start": 20, "end": 40}]},
        {"id": "c2", "beats": [{"id": "b3", "start": 40, "end": 60}]}]


@pytest.mark.parametrize("text", REQUESTS, ids=["english", "hebrew"])
def test_passage_may_cross_an_arbitrary_chapter_boundary(text):
    chapters = canonical()
    before = copy.deepcopy(chapters)
    intelligence._validate_single_source_passage(["b2", "b3"], chapters, request(text))
    assert chapters == before


@pytest.mark.parametrize("keep", [["b1", "b3"], ["foreign"], []])
def test_continuity_uses_full_source_even_if_retrieval_omits_middle_unit(keep):
    with pytest.raises(StoryPlanningError) as caught:
        intelligence._validate_single_source_passage(keep, canonical(), request(REQUESTS[0] + " Keep the source passage continuous without internal cuts."))
    assert caught.value.diagnostic["reason"] == "single_passage_source_discontinuity"
    assert caught.value.diagnostic["applied_to_timeline"] is False


def test_unknown_or_multiple_passage_request_keeps_existing_behavior():
    intelligence._validate_single_source_passage(["b1", "b3"], canonical(), request("Include 3 moments."))


def test_cancellation_stops_before_the_single_planning_correction(monkeypatch):
    calls = responder(monkeypatch, [proposal(("hook", "ending"), 30)])
    checks = []
    def cancel():
        checks.append(True)
        if len(checks) == 2:
            raise RuntimeError("cancelled before correction")
    with pytest.raises(RuntimeError, match="cancelled before correction"):
        intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, request(REQUESTS[0]),
                                       "fixture", cancel_check=cancel)
    assert len(calls) == 1 and len(checks) == 2


@pytest.mark.parametrize("text", REQUESTS, ids=["english", "hebrew"])
def test_one_coherent_idea_does_not_forbid_related_source_cuts(monkeypatch, text):
    brief = request(text)
    intelligence._validate_single_source_passage(["b1", "b3"], canonical(), brief)
    calls = responder(monkeypatch, [proposal()])
    plan = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, brief, "fixture")
    assert plan["passage_constraint"]["continuity"] == "unspecified"
    guidance = calls[0]["messages"][0]["content"]
    assert "Meaning-preserving cuts" in guidance
    assert "ONE continuous original source passage" not in guidance
    assert brief["style_profile"]["selection_policy"]["preserve_source_continuity"] is False


@pytest.mark.parametrize("directive", ["Keep the source passage continuous without internal cuts.", "שמור על קטע מקור רציף ללא חיתוכים."])
def test_explicit_continuity_separately_protects_pauses_and_source_units(monkeypatch, directive):
    brief = request(REQUESTS[0] + " " + directive)
    assert brief["style_profile"]["selection_policy"]["preserve_source_continuity"] is True
    calls = responder(monkeypatch, [proposal()])
    plan = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {}, brief, "fixture")
    assert plan["passage_constraint"]["continuity"] == "explicitly_required"
    assert "do not shorten internal pauses" in calls[0]["messages"][0]["content"]
    with pytest.raises(StoryPlanningError):
        intelligence._validate_single_source_passage(["b1", "b3"], canonical(), brief)
