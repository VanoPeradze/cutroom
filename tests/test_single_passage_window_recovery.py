"""A failed index nomination must not hide later complete canonical passages."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence
from cutroom.jobs import JobCancelled
from cutroom.story_budget import StoryBudgetError, StoryPlanningError


class Settings:
    ai = {"performance_mode": "balanced"}


def source(language):
    text = ("The source keeps the qualification: success was not established."
            if language == "en" else "המקור שומר על ההסתייגות: ההצלחה לא הוכחה.")
    segments = [{"id": f"s{n}", "start": (n - 1) * 10., "end": n * 10.,
                 "text": f"{n}. {text}"} for n in range(1, 9)]
    beats = [{"id": f"b{n}", "start": r["start"], "end": r["end"], "duration": 10.,
              "segment_ids": [r["id"]], "text": r["text"]} for n, r in enumerate(segments, 1)]
    chapters = [{"id": "c1", "start": 0., "end": 80., "duration": 80., "beats": beats}]
    summaries = [{"id": "c1", "summary": "An unverified chapter interpretation.", "key_points": [],
                  "key_beat_ids": [r["id"] for r in beats], "depends_on": []}]
    brief = {"goal": "short", "target_duration": 20., "duration_mode": "target", "performance_mode": "balanced",
             "instruction": "Choose one self-contained passage." if language == "en" else "בחר קטע אחד עצמאי."}
    plan = {"slots": [{"purpose": intelligence.SINGLE_PASSAGE_PURPOSE, "chapter_ids": ["c1"],
                       "required_context_chapter_ids": [], "desired_seconds": 20.}]}
    return beats, segments, chapters, summaries, brief, plan


def install_small_context(monkeypatch):
    # Controlled budget isolates the orchestration boundary. Pure-window tests
    # independently exercise the real full-request token estimator + reserve.
    def fits(payload, _mode):
        data = json.loads(payload["messages"][1]["content"])
        return len(data.get("candidate_beats", [])) <= 3
    monkeypatch.setattr(intelligence, "_story_payload_fits_cap", fits)
    def nominate(_settings, candidates, *_args):
        return candidates[:3], {"version": 1, "retrieved_candidate_ids": [r["id"] for r in candidates[:3]],
                                "authority": "provisional_index_retrieval_requires_complete_source_validation"}
    monkeypatch.setattr(intelligence, "_retrieve_story_candidates", nominate)


def refusal():
    return {"verdict": "no_fit", "reason": "insufficient_context",
            "missing_purposes": [intelligence.SINGLE_PASSAGE_PURPOSE]}


def source_fit(data, identifiers=("b6", "b7")):
    choices = data["source_evidence_choices"]
    selected = [next(s for s in choices if f"[{value}:s{value[1:]}:" in s) for value in identifiers]
    return {"verdict": "fit", "role_selections": {intelligence.SINGLE_PASSAGE_PURPOSE: {
        "primary_anchor_choice": selected[-1], "additional_primary_evidence_choices": selected[:-1],
        "context_evidence_choices_by_chapter": {}}}, "highlight_beat_ids": [],
        "title": "Provisional source passage", "summary": "This model wording cannot replace source quotations."}


@pytest.mark.parametrize("language", ["en", "he"])
def test_tail_passage_reaches_same_strict_precision_decoder_after_initial_no_fit(monkeypatch, language):
    fixture = source(language)
    beats, segments, chapters, summaries, brief, plan = fixture
    before = copy.deepcopy(fixture)
    install_small_context(monkeypatch)
    calls = []
    def respond(_settings, payload, *_args):
        data = json.loads(payload["messages"][1]["content"])
        calls.append(copy.deepcopy(data))
        ids = {r["id"] for r in data["candidate_beats"]}
        canonical = {r["id"]: r for r in segments}
        for utterance in data["source_utterances"]:
            assert utterance == {k: canonical[utterance["id"]][k] for k in ("id", "start", "end", "text")}
        return source_fit(data) if {"b6", "b7"} <= ids else refusal()
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    selection, available = intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief,
                                                            "fixture", segments=segments)
    assert [r["id"] for r in calls[0]["candidate_beats"]] == ["b1", "b2", "b3"]
    assert selection["keep_beat_ids"] == ["b6", "b7"]
    assert {"b6", "b7"} <= {r["id"] for r in available}
    assert selection["semantic_mapping_verified"] is False
    assert selection["semantic_review_status"] == "provisional_precision_selection"
    assert selection["summary"] != "This model wording cannot replace source quotations."
    review = selection["source_retrieval"]["canonical_window_review"]
    assert review["eligible_source_beat_ids"] == [r["id"] for r in beats]
    assert review["trials"][-1]["verdict"] == "provisional_fit"
    assert calls[-1]["minimum_target_seconds"] == 18.
    assert fixture == before


@pytest.mark.parametrize("language", ["en", "he"])
def test_all_window_refusals_remain_scoped_to_plan_domain_and_keep_source(monkeypatch, language):
    fixture = source(language)
    beats, segments, chapters, summaries, brief, plan = fixture
    before = copy.deepcopy(fixture)
    install_small_context(monkeypatch)
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: refusal())
    with pytest.raises(StoryBudgetError) as caught:
        intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief, "fixture", segments=segments)
    diagnostic = caught.value.diagnostic
    assert diagnostic["scope"] == "canonical_plan_domain_windows"
    assert diagnostic["outcome"] == "editorial_no_fit" and diagnostic["applied_to_timeline"] is False
    review = diagnostic["source_retrieval"]["canonical_window_review"]
    assert len(review["trials"]) == review["planned_window_count"]
    assert set().union(*(set(r["candidate_beat_ids"]) for r in review["trials"])) == {r["id"] for r in beats}
    assert all(r["verdict"] == "no_fit" for r in review["trials"])
    assert fixture == before


def test_malformed_claim_does_not_trigger_window_search_or_bypass_source_checks(monkeypatch):
    _beats, segments, chapters, summaries, brief, plan = source("en")
    install_small_context(monkeypatch)
    calls = []
    def respond(*_args):
        calls.append(True)
        return {"verdict": "fit", "role_selections": {}, "highlight_beat_ids": [], "title": "", "summary": ""}
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    with pytest.raises(StoryPlanningError, match="invalid precision source assignments"):
        intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief, "fixture", segments=segments)
    assert len(calls) == 1


def test_cancellation_before_window_search_starts_no_second_model_request(monkeypatch):
    _beats, segments, chapters, summaries, brief, plan = source("en")
    install_small_context(monkeypatch)
    calls = []
    def respond(*_args):
        calls.append(True)
        return refusal()
    def cancel():
        if calls:
            raise JobCancelled("cancel before canonical windows")
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    with pytest.raises(JobCancelled):
        intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief, "fixture",
                                         cancel_check=cancel, segments=segments)
    assert len(calls) == 1


@pytest.mark.parametrize("language", ["en", "he"])
def test_underfilled_valid_fits_do_not_hide_a_later_valid_target_passage(monkeypatch, language):
    _beats, segments, chapters, summaries, brief, plan = source(language)
    install_small_context(monkeypatch)
    calls = []
    def respond(_settings, payload, *_args):
        data = json.loads(payload["messages"][1]["content"])
        ids = [r["id"] for r in data["candidate_beats"]]
        calls.append(ids)
        return source_fit(data) if {"b6", "b7"} <= set(ids) else source_fit(data, [ids[0]])
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    selection, _ = intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief,
                                                   "fixture", segments=segments)
    assert selection["keep_beat_ids"] == ["b6", "b7"] and len(calls) > 2
    review = selection["source_retrieval"]["canonical_window_review"]
    assert review["trials"][0]["verdict"] == "provisional_budget_miss"
    assert all(r["verdict"] == "provisional_budget_miss" for r in review["trials"][:-1])
    assert selection["semantic_mapping_verified"] is False


@pytest.mark.parametrize("limit", ["source_units", "model_calls"])
def test_work_exhaustion_is_a_scoped_technical_failure_not_no_fit(monkeypatch, limit):
    _beats, segments, chapters, summaries, brief, plan = source("en")
    install_small_context(monkeypatch)
    if limit == "source_units":
        monkeypatch.setattr(intelligence, "SINGLE_PASSAGE_WINDOW_MAX_UNITS", 7)
    else:
        monkeypatch.setattr(intelligence, "SINGLE_PASSAGE_WINDOW_MAX_CALLS", 1)
    calls = []
    def respond(*_args):
        calls.append(True)
        return refusal()
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    with pytest.raises(StoryPlanningError) as caught:
        intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief, "fixture", segments=segments)
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "story_window_work_budget_exhausted"
    assert diagnostic["outcome"] == "technical_error" and diagnostic["applied_to_timeline"] is False
    assert diagnostic["scope"] == "canonical_plan_domain_windows"
    assert len(calls) == (1 if limit == "source_units" else 2)


@pytest.mark.parametrize("language", ["en", "he"])
def test_neutral_role_source_order_refusals_do_not_prove_editorial_impossibility(monkeypatch, language):
    _beats, segments, chapters, summaries, brief, plan = source(language)
    install_small_context(monkeypatch)
    reply = {"verdict": "no_fit", "reason": "source_order", "missing_purposes": [intelligence.SINGLE_PASSAGE_PURPOSE]}
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: copy.deepcopy(reply))
    with pytest.raises(StoryPlanningError) as caught:
        intelligence._select_story_beats(Settings(), chapters, summaries, {}, plan, brief, "fixture", segments=segments)
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "precision_semantics_unverified"
    assert diagnostic["outcome"] == "technical_error"
    assert diagnostic["source_order_evidence_verified"] is False
    assert diagnostic["semantic_result_verified"] is False
    assert diagnostic["applied_to_timeline"] is False
    review = diagnostic["source_retrieval"]["canonical_window_review"]
    assert review["search_status"] == "domain_exhausted"
    assert len(review["trials"]) == review["planned_window_count"]
