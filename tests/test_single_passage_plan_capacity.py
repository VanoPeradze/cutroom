"""Necessary plan-domain capacity bounds never establish semantic source fit.

These synthetic source intervals exercise orchestration and exact attribution.
No model, media, transcript replacement or editorial-quality claim is involved.
"""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence as story
from cutroom.instruction_contract import explicit_source_continuity_requested, single_source_passage_requested
from cutroom.story_budget import StoryPlanningError


class Settings:
    ai = {"performance_mode": "balanced"}


REQUESTS = {
    "en": "Choose one coherent self-contained passage from the conversation, about a minute long.",
    "he": "בחר קטע אחד ברור ועצמאי מתוך השיחה, באורך של כדקה.",
}


def brief(language="en", **overrides):
    return {"goal": "short", "target_duration": 60, "duration_mode": "target",
            "performance_mode": "balanced", "instruction": REQUESTS[language], **overrides}


def sources(language="en", times=((0., 30.), (31., 60.), (61., 90.))):
    text = ("The original source does not establish success." if language == "en" else
            "המקור המקורי אינו מוכיח הצלחה.")
    segments = [{"id": f"s{index}", "start": start, "end": end, "text": text}
                for index, (start, end) in enumerate(times, 1)]
    beats = [{"id": f"b{index}", "start": segment["start"], "end": segment["end"],
              "duration": segment["end"] - segment["start"], "text": segment["text"],
              "segment_ids": [segment["id"]]} for index, segment in enumerate(segments, 1)]
    chapters = [{"id": "c1", "start": times[0][0], "end": times[0][1], "beats": beats[:1]},
                {"id": "c2", "start": times[1][0], "end": times[-1][1], "beats": beats[1:]}]
    summaries = [{"id": chapter["id"], "summary": "Unverified candidate-region interpretation.",
                  "key_points": [], "depends_on": []} for chapter in chapters]
    return chapters, segments, summaries


def plan(chapter_ids=("c1",), *, seconds=45):
    return {"narrative": "A provisional single idea; exact selection and review remain required.",
            "slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE, "chapter_ids": list(chapter_ids),
                       "desired_seconds": seconds, "reason": "Candidate regions, not required source coverage.",
                       "required_context_chapter_ids": []}]}


def responder(monkeypatch, replies):
    calls = []
    def respond(_settings, payload, *_args, **_kwargs):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(replies[min(len(calls) - 1, len(replies) - 1)])
    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    return calls


def produce(monkeypatch, replies, *, language="en", request=None, data=None):
    chapters, segments, summaries = data or sources(language)
    calls = responder(monkeypatch, replies)
    result = story._build_story_plan(Settings(), summaries, {}, request or brief(language), "fixture",
                                     segments=segments, chapters=chapters)
    return result, calls


@pytest.mark.parametrize("language", ["he", "en"])
def test_capacity_proof_is_scoped_numeric_and_does_not_certify_semantics(language):
    chapters, segments, _ = sources(language)
    proposal = plan()
    request = brief(language)
    original = copy.deepcopy((proposal, chapters, segments, request))
    proof = story._single_passage_plan_capacity(proposal, chapters, segments, request)
    assert proof["scope"] == "nominated_plan_domain_only"
    assert proof["optimistic_upper_bound_seconds"] == 30
    assert proof["required_target_minimum_seconds"] == 54
    assert proof["nominated_chapter_ids"] == ["c1"]
    assert proof["semantic_fit_verified"] is False and proof["selection_forced"] is False
    assert (proposal, chapters, segments, request) == original


def test_cached_underfilled_nomination_cannot_bypass_capacity_before_checkpoint_access(monkeypatch):
    chapters, segments, summaries = sources()
    def forbidden(*_args, **_kwargs):
        raise AssertionError("An impossible saved plan must not open a search checkpoint or call a model")
    monkeypatch.setattr(story, "_prepare_story_window_search", forbidden)
    monkeypatch.setattr(story, "_call_ollama_story_pass", forbidden)
    cached = {"last_proposed_plan": plan()}
    before = copy.deepcopy(cached)
    assert story._resumable_story_plan(Settings(), cached, chapters, summaries, {}, brief(), "fixture",
                                       segments, {"source": "identity"}, None) is None
    assert cached == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_neutral_precision_asks_no_independent_ranking_but_preserves_exact_source_contract(language):
    chapters, segments, summaries = sources(language)
    candidates = [beat for chapter in chapters for beat in chapter["beats"]]
    payload, catalog = story._precision_story_payload(candidates, segments, chapters, summaries, {},
        plan(("c1", "c2"), seconds=60), brief(language), "fixture", "balanced", 60)
    fit = next(branch for branch in payload["format"]["anyOf"]
               if branch["properties"]["verdict"]["enum"] == ["fit"])
    assert fit["properties"]["highlight_beat_ids"] == {"type": "array", "maxItems": 0}
    assert "exact quotation assignments alone determine selected source" in payload["messages"][0]["content"]
    content = json.loads(payload["messages"][1]["content"])
    assert content["source_evidence"] == catalog
    assert [row["id"] for row in content["source_utterances"]] == [row["id"] for row in segments]
    assert content["brief"]["instruction"] == REQUESTS[language]


def test_explicit_role_grammar_retains_existing_selected_highlight_contract():
    chapters, segments, summaries = sources()
    candidates = [beat for chapter in chapters for beat in chapter["beats"]]
    role_plan = plan(("c1", "c2")); role_plan["slots"][0]["purpose"] = "context"
    payload, _ = story._precision_story_payload(candidates, segments, chapters, summaries, {},
        role_plan, brief(instruction="Include context."), "fixture", "balanced", 60)
    fit = next(branch for branch in payload["format"]["anyOf"]
               if branch["properties"]["verdict"]["enum"] == ["fit"])
    assert "maxItems" not in fit["properties"]["highlight_beat_ids"]
    assert fit["properties"]["highlight_beat_ids"]["items"]["enum"] == [row["id"] for row in candidates]


@pytest.mark.parametrize("language", ["he", "en"])
def test_underfilled_pool_gets_one_fresh_correction_with_exact_capacity_and_full_index(monkeypatch, language):
    data = sources(language)
    initial, corrected = plan(), plan(("c1", "c2"), seconds=60)
    before = copy.deepcopy((data, initial, corrected))
    result, calls = produce(monkeypatch, [initial, corrected], language=language, data=data)
    assert len(calls) == 2 and all(row["_single_attempt"] is True for row in calls)
    assert result["slots"][0]["chapter_ids"] == ["c1", "c2"]
    first = json.loads(calls[0]["messages"][1]["content"])
    second = json.loads(calls[1]["messages"][1]["content"])
    assert first["duration_policy"]["minimum_target_seconds"] == 54
    correction = second["plan_correction"]["candidate_capacity"]
    assert correction["optimistic_upper_bound_seconds"] == 30
    assert correction["required_target_minimum_seconds"] == 54
    assert correction["scope"] == "nominated_plan_domain_only"
    assert {row["id"] for row in second["chapters"]} == {"c1", "c2"}
    assert first["source_evidence"] == second["source_evidence"]
    assert second["brief"]["instruction"] == REQUESTS[language]
    assert second["target_seconds"] == 60
    assert result["slots"][0]["required_context_chapter_ids"] == []
    assert (data, initial, corrected) == before


def test_repeated_underfilled_proposal_stops_after_existing_two_planning_calls(monkeypatch):
    data = sources()
    calls = responder(monkeypatch, [plan()])
    original = copy.deepcopy(data)
    with pytest.raises(StoryPlanningError) as caught:
        story._build_story_plan(Settings(), data[2], {}, brief(), "fixture", segments=data[1], chapters=data[0])
    assert len(calls) == 2
    assert caught.value.diagnostic["reason"] == "single_passage_plan_conflict"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert data == original


@pytest.mark.parametrize("language", ["he", "en"])
def test_broad_domain_is_allowed_without_forcing_all_regions_into_precision_selection(monkeypatch, language):
    chapters, segments, summaries = sources(language)
    result, calls = produce(monkeypatch, [plan(("c1", "c2"), seconds=60)], language=language,
                            data=(chapters, segments, summaries))
    assert len(calls) == 1  # No extra budget-inference or correction request.
    candidates = story._candidate_beats_for_plan(chapters, result)
    proof = story._single_passage_plan_capacity(result, chapters, segments, brief(language))
    assert proof["optimistic_upper_bound_seconds"] > 60
    assert proof["selection_forced"] is False
    _, catalog = story._precision_story_payload(candidates, segments, chapters, summaries, {}, result,
                                               brief(language), "fixture", "balanced", 60)
    choices = [f"{row['text']} [{row['id']}]" for row in catalog if row["beat_id"] in {"b2", "b3"}]
    reply = {"verdict": "fit", "role_selections": {story.SINGLE_PASSAGE_PURPOSE: {
        "primary_anchor_choice": choices[-1], "additional_primary_evidence_choices": choices[:-1],
        "context_evidence_choices_by_chapter": {}}}, "highlight_beat_ids": [],
        "title": "Provisional exact attribution", "summary": "Unverified meaning"}
    selection = story._decode_precision_story_selection(reply, catalog, candidates, segments, chapters, result, brief(language))
    assert selection["keep_beat_ids"] == ["b2", "b3"]
    assert selection["semantic_mapping_verified"] is False
    assert len(calls) == 1  # Source reconstruction did not invoke another model.


def test_short_whole_source_uses_its_own_end_in_the_same_target_minimum(monkeypatch):
    data = sources(times=((0., 10.), (10., 25.), (25., 40.)))
    result, calls = produce(monkeypatch, [plan(("c1", "c2"))], data=data)
    proof = story._single_passage_plan_capacity(result, data[0], data[1], brief())
    assert proof["required_target_minimum_seconds"] == 36
    assert proof["optimistic_upper_bound_seconds"] == 40
    assert len(calls) == 1


def test_max_duration_mode_has_no_target_underfill_correction(monkeypatch):
    request = brief(duration_mode="max")
    data = sources()
    assert story._single_passage_plan_capacity(plan(), data[0], data[1], request) is None
    result, calls = produce(monkeypatch, [plan()], request=request, data=data)
    assert len(calls) == 1 and result["slots"][0]["chapter_ids"] == ["c1"]


@pytest.mark.parametrize("fault", ["missing_end", "nonfinite", "unknown_chapter"])
def test_unknown_geometry_cannot_become_a_false_numeric_underfill_proof(fault):
    chapters, segments, _ = sources()
    proposal = plan()
    if fault == "missing_end": chapters[0]["beats"][0].pop("end")
    elif fault == "nonfinite": chapters[0]["beats"][0]["end"] = float("nan")
    else: proposal["slots"][0]["chapter_ids"].append("unknown")
    assert story._single_passage_plan_capacity(proposal, chapters, segments, brief()) is None
    # Existing source/ID validators retain responsibility for malformed inputs;
    # uncertainty in this arithmetic check cannot certify the proposal itself.


@pytest.mark.parametrize("language", ["he", "en"])
def test_explicit_continuity_uses_optimistic_envelope_but_one_idea_does_not(language):
    chapters, segments, _ = sources(language, times=((0., 20.), (40., 60.), (61., 90.)))
    # Put both separated utterances in one storage chapter, retaining their gap.
    chapters[0]["beats"].append(chapters[1]["beats"].pop(0))
    chapters[0]["end"] = 60.
    chapters[1]["start"] = 61.
    normal = brief(language)
    explicit = brief(language, instruction=REQUESTS[language] + (
        " Keep the selected source passage continuous." if language == "en" else
        " שמור על קטע המקור ללא חיתוכים."))
    assert single_source_passage_requested(normal) and not explicit_source_continuity_requested(normal)
    assert explicit_source_continuity_requested(explicit)
    ordinary_proof = story._single_passage_plan_capacity(plan(), chapters, segments, normal)
    continuous_proof = story._single_passage_plan_capacity(plan(), chapters, segments, explicit)
    assert ordinary_proof["optimistic_upper_bound_seconds"] == 40
    assert continuous_proof["optimistic_upper_bound_seconds"] == 60
    assert continuous_proof["semantic_fit_verified"] is False
    assert continuous_proof["selection_forced"] is False


@pytest.mark.parametrize("instruction", ["Make one video.", "צור סרטון אחד."])
def test_one_output_does_not_create_single_idea_or_source_continuity_capacity_policy(monkeypatch, instruction):
    request = brief(instruction=instruction)
    assert not single_source_passage_requested(request)
    assert not explicit_source_continuity_requested(request)
    data = sources()
    result, calls = produce(monkeypatch, [plan()], request=request, data=data)
    assert len(calls) == 1
    assert "passage_constraint" not in result
