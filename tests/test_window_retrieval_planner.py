"""Automatic actual-entry retrieval, not editorial/model or media acceptance."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import socket
import time
import tracemalloc
from types import SimpleNamespace
import urllib.request

import pytest

from cutroom import ai_runtime, intelligence as story, window_retrieval as retrieval
from cutroom import window_evidence as bridge
from cutroom.edit_windows import SourceDescriptor, EditWindowError, build_canonical_source, compile_selected_spans, build_edit_window
from cutroom.instruction_contract import effective_duration_bounds
from cutroom.story_budget import StoryBudgetError, StoryPlanningError
from tests.test_window_evidence_planner import segments, brief
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


@pytest.fixture(autouse=True)
def no_inference_or_network(monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("Automatic window retrieval must not call models/network")
    for module in (story, ai_runtime):
        monkeypatch.setattr(module, "open_ollama", forbidden)
    for name in ("_call_ollama_story_pass", "_ollama_chat", "hierarchical_story_edit", "story_ai_status"):
        monkeypatch.setattr(story, name, forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def request(data, *, policy=None, descriptor=None):
    desc = descriptor or SourceDescriptor("primary:A", "g1", "t1", max(1000., data[-1]["end"] + 121), 120)
    source = build_canonical_source(data, desc)
    state = bridge.WindowSourceState("project_0123456789ab", 3, desc)
    return retrieval.WindowRetrievalRequest(source, state, policy or retrieval.WindowRetrievalPolicy())


def run(data=None, *, language="en", instruction=None, req=None, reader=None, cancel=None, cache=None):
    data = segments(language) if data is None else data
    req = request(data) if req is None else req
    return story.plan_edit(data, SimpleNamespace(ai={}), brief(language, instruction), story_cache=cache,
        cancel_check=cancel, source_window_request=req, source_window_state=reader or (lambda: req.state))


def regular(count=20, width=6., language="en"):
    text = "This is unchanged source evidence, not a semantic conclusion." if language == "en" else "זהו מקור ללא שינוי, ולא אישור למשמעותו."
    return [{"id": f"row-{i}", "start": i * width, "end": (i + 1) * width, "text": text} for i in range(count)]


def brute_pairs(source, bounds):
    return {(i, j) for i, a in enumerate(source.rows) for j in range(i, len(source.rows))
            if bounds["minimum_seconds"] - retrieval.EPSILON <= source.rows[j].end - a.start <= bounds["maximum_seconds"] + retrieval.EPSILON}


@pytest.mark.parametrize("language", ["en", "he"])
def test_automatic_actual_entry_requires_no_nominated_windows_and_preserves_exact_evidence(language):
    data = segments(language)
    req = request(data)
    before = copy.deepcopy(data)
    result, engine = run(data, language=language, req=req)
    assert engine == "source_window_retrieval_preview"
    assert result["status"] == "automatic_window_retrieval_preview_only"
    assert result["retrieval"]["feasible_continuous_pairs"] == 3
    assert result["retrieval"]["retrieved_pairs"] == 3 and result["retrieval"]["continuous_domain_exhausted"]
    assert result["selection"] is None and result["selected_evidence"] == []
    assert result["editorial_status"] == "not_assessed" and "decision" not in result and "draft" not in result
    assert result["instruction_contract"]["verification_status"] == "unverified"
    assert data == before
    for view in result["views"]:
        assert view["source_start"] == view["asr_start"] + 120
        assert view["source_end"] == view["asr_end"] + 120
        assert 45 - retrieval.EPSILON <= view["source_end"] - view["source_start"] <= 60 + retrieval.EPSILON
        assert [r["text"] for r in view["exact_text_by_row"]] == [r["text"] for r in data if r["id"] in view["row_ids"]]
    for ref in result["canonical_evidence"]:
        row = next(r for r in data if r["id"] == ref["segment_id"])
        assert ref["text"] == row["text"][ref["char_start"]:ref["char_end"]]


@pytest.mark.parametrize("language", ["en", "he"])
@pytest.mark.parametrize("width", [3., 5., 7.])
def test_generic_pool_recall_matches_all_numeric_source_windows_when_not_capped(language, width):
    data = regular(30, width, language)
    source = request(data).source
    bounds = effective_duration_bounds(brief(language))
    policy = retrieval.WindowRetrievalPolicy(max_endpoints_per_start=64)
    pool = retrieval.retrieve_windows(source, bounds, policy)
    expected = brute_pairs(source, bounds)
    assert {(c.first, c.last) for c in pool.candidates} == expected
    assert pool.feasible_pairs == len(expected) and len({(c.first, c.last) for c in pool.candidates}) == len(expected)
    assert pool.source_rows_scanned == len(data)


def test_shortlist_diversity_avoids_repeated_near_identical_prefix_windows():
    data = regular(100)
    req = request(data, policy=retrieval.WindowRetrievalPolicy(shortlist_size=8))
    result, _ = run(data, req=req)
    starts = [v["asr_start"] for v in result["views"]]
    assert len(starts) == 8 and max(starts) - min(starts) > 400
    assert len(set(starts)) >= 7
    assert result["retrieval"]["unshortlisted_unreviewed"] > 0
    assert len(result["canonical_ownership"]) == 100
    assert len({r["id"] for r in result["canonical_evidence"]}) == len(result["canonical_evidence"])
    assert result["retrieval"]["ranking_basis"] == "canonical_membership_and_source_time_diversity_only"


def test_ranking_does_not_treat_grammar_negation_or_topic_words_as_verified_quality():
    data = regular(30)
    first, _ = run(data)
    altered = copy.deepcopy(data)
    for i, row in enumerate(altered):
        row["text"] = "I did not approve this. לא אישרתי את זה." if i % 2 else "An unfinished prefix create a"
    # The same timing/membership has the same retrieval priority, not a claim
    # either text is complete/coherent. Actual canonical ownership may change.
    second, _ = run(altered)
    assert [(r["first_row_id"], r["last_row_id"]) for r in first["ranked_candidates"]] == [
        (r["first_row_id"], r["last_row_id"]) for r in second["ranked_candidates"]]
    assert first["cache_key"] != second["cache_key"]
    assert second["retrieval"]["semantic_assessment"] == "not_performed"
    assert [r["text"] for r in second["views"][0]["exact_text_by_row"]] == [
        r["text"] for r in altered if r["id"] in second["views"][0]["row_ids"]]


@pytest.mark.parametrize("language,text", [("en", "unchanged ASR text without terminal punctuation"),
                                          ("he", "תמלול מקורי ללא סימן פיסוק בסיום")])
def test_long_unpunctuated_asr_is_indexed_without_grammar_gate_or_source_rewrite(language, text):
    data = regular(40, 5, language)
    for row in data:
        row["text"] = text
    before = copy.deepcopy(data)
    # Keep the original editing path's guard: this milestone authorizes only
    # unreviewed retrieval, never semantic approval of an unfinished passage.
    with pytest.raises(StoryPlanningError):
        story.plan_edit(data, SimpleNamespace(ai={}), brief(language))
    result, _ = run(data, language=language)
    assert result["ranked_candidates"] and len(result["canonical_ownership"]) == 40
    assert result["retrieval"]["semantic_assessment"] == "not_performed"
    assert result["selection"] is None and "decision" not in result
    assert data == before


@pytest.mark.parametrize("language,one,no_cuts", [
    ("en", "Make one video. Aim for 45–60 seconds.", "Choose one continuous source passage. Aim for 45–60 seconds."),
    ("he", "צור סרטון אחד. כוון ל־45–60 שניות.", "שמור על קטע המקור ללא חיתוכים. כוון ל־45–60 שניות."),
])
def test_one_output_does_not_become_no_cuts_and_cut_composition_gap_is_explicit(language, one, no_cuts):
    a, _ = run(language=language, instruction=one)
    b, _ = run(language=language, instruction=no_cuts)
    assert a["retrieval"]["single_output_requested"] is True
    assert a["retrieval"]["source_continuity"] == "unspecified"
    assert b["retrieval"]["source_continuity"] == "required"
    for result in (a, b):
        assert result["retrieval"]["noncontiguous_composition_search"] == "not_implemented"
        assert result["retrieval"]["candidate_form"] == "one_continuous_whole_ASR_window_per_alternative"
        assert result["selection"] is None  # Alternatives are never concatenated.


@pytest.mark.parametrize("language,instruction", [("en", "Make exactly 60 seconds."), ("he", "צור סרטון של 60 שניות.")])
def test_exact_target_enumerates_only_real_complete_asr_boundaries(language, instruction):
    data = regular(12, 10, language)
    result, _ = run(data, language=language, instruction=instruction)
    assert result["retrieval"]["bounds"]["origin"] == "explicit_user_exact"
    assert result["ranked_candidates"] and all(r["raw_seconds"] == 60 for r in result["ranked_candidates"])
    for view in result["views"]:
        assert len(view["row_ids"]) == 6


@pytest.mark.parametrize("language,instruction", [("en", "Make exactly 60 seconds."), ("he", "צור סרטון של 60 שניות.")])
def test_no_exact_boundary_does_not_pad_trim_source_or_claim_semantic_no_fit(language, instruction):
    data = regular(5, 11, language)
    result, _ = run(data, language=language, instruction=instruction)
    assert result["ranked_candidates"] == [] and result["views"] == [] and result["selection"] is None
    assert result["canonical_evidence"] and len(result["canonical_ownership"]) == 5
    assert result["retrieval"]["status"] == "no_numeric_fit_in_continuous_domain_only"
    assert result["retrieval"]["continuous_domain_exhausted"] is True
    assert result["retrieval"]["noncontiguous_composition_search"] == "not_implemented"
    assert result["instruction_contract"]["verification_status"] == "unverified"
    assert "decision" not in result and result["editorial_status"] == "not_assessed"


def test_pair_and_endpoint_caps_sample_across_full_domain_and_disclose_omissions():
    data = regular(1000, 1)
    policy = retrieval.WindowRetrievalPolicy(max_source_starts=16, max_pairs=32, max_endpoints_per_start=8, shortlist_size=8)
    req = request(data, policy=policy)
    pool = retrieval.retrieve_windows(req.source, effective_duration_bounds(brief()), policy)
    # Pair budget is a ceiling, not a quota; the final eligible start has only
    # one endpoint. Do not duplicate a candidate to fill unused capacity.
    assert 16 <= len(pool.candidates) <= 32 and pool.sampled_starts == 16
    assert min(c.first for c in pool.candidates) == 0 and max(c.first for c in pool.candidates) >= 950
    assert pool.feasible_pairs > len(pool.candidates) and pool.eligible_starts > pool.sampled_starts
    assert pool.source_rows_scanned == 1000
    result, _ = run(data, req=req)
    assert result["retrieval"]["continuous_domain_exhausted"] is False
    assert result["retrieval"]["retrieved_pairs"] <= policy.max_pairs


def test_pool_memory_and_runtime_are_bounded_without_materializing_all_overlapping_memberships():
    data = regular(6000, 1)
    req = request(data, policy=retrieval.WindowRetrievalPolicy(max_source_starts=256, max_pairs=1024))
    tracemalloc.start()
    start = time.monotonic()
    try:
        pool = retrieval.retrieve_windows(req.source, effective_duration_bounds(brief()), req.policy)
        ranked = retrieval.rank_windows(req.source, pool, 16)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert time.monotonic() - start < 10
    assert peak < 8 * 1024**2
    assert len(pool.candidates) <= 1024 and len(ranked) == 16
    assert set(retrieval.WindowCandidate.__dataclass_fields__) == {"first", "last", "duration"}
    assert pool.source_rows_scanned == 6000 and max(c.first for c in pool.candidates) > 5900


def test_actual_entry_builds_only_shortlisted_window_views(monkeypatch):
    data = regular(100)
    req = request(data, policy=retrieval.WindowRetrievalPolicy(shortlist_size=4))
    called = []
    original = retrieval.build_edit_window
    def build(*args):
        called.append(1)
        return original(*args)
    monkeypatch.setattr(retrieval, "build_edit_window", build)
    result, _ = run(data, req=req)
    assert result["retrieval"]["retrieved_pairs"] > 4 and len(called) == 4


@pytest.mark.parametrize("policy,data", [
    (retrieval.WindowRetrievalPolicy(max_view_row_references=128), regular(500, .12)),
    (retrieval.WindowRetrievalPolicy(max_view_text_characters=1000),
     [{"id": f"text-{i}", "start": i * 5., "end": (i+1)*5., "text": "unchanged " * 60} for i in range(12)]),
])
def test_materialization_budget_does_not_become_numeric_or_semantic_no_fit(policy, data):
    req = request(data, policy=policy)
    result, _ = run(data, req=req)
    assert result["retrieval"]["feasible_continuous_pairs"] > 0
    assert result["retrieval"]["retrieved_pairs"] > 0 and result["retrieval"]["shortlisted"] == 0
    assert result["retrieval"]["status"] == "materialization_budget_blocked"
    assert result["views"] == [] and result["selection"] is None
    assert len(result["canonical_ownership"]) == len(data)


def test_complete_actual_planner_path_has_bounded_measured_allocation_and_view_size():
    data = regular(200, .3)
    policy = retrieval.WindowRetrievalPolicy(max_pairs=256, max_source_starts=64,
        max_view_row_references=1000, max_view_text_characters=60000)
    req = request(data, policy=policy)
    tracemalloc.start()
    start = time.monotonic()
    try:
        result, _ = run(data, req=req)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert time.monotonic() - start < 10 and peak < 16 * 1024**2
    assert result["ranked_candidates"] and len(result["canonical_ownership"]) == 200
    assert result["retrieval"]["view_row_references"] <= 1000
    assert result["retrieval"]["view_text_characters"] <= 60000
    assert result["selection"] is None and "decision" not in result


@pytest.mark.parametrize("stage", ["start", "enumeration", "ranking", "last_state_read"])
def test_cancellation_leaves_source_cache_and_user_input_unchanged(monkeypatch, stage):
    data = regular(40)
    original = copy.deepcopy(data)
    req = request(data)
    cache = {"existing_decision": {"semantic_mapping_verified": True}}
    before = copy.deepcopy(cache)
    cancelled = [stage == "start"]
    def cancel():
        if cancelled[0]:
            raise InterruptedError("cancelled")
    if stage in {"enumeration", "ranking"}:
        name = "retrieve_windows" if stage == "enumeration" else "rank_windows"
        method = getattr(retrieval, name)
        def abort(*a, **kw):
            cancelled[0] = True
            return method(*a, **kw)
        monkeypatch.setattr(retrieval, name, abort)
    reads = []
    def reader():
        reads.append(1)
        if stage == "last_state_read" and len(reads) == 5:
            cancelled[0] = True
        return req.state
    with pytest.raises(InterruptedError):
        run(data, req=req, cache=cache, reader=reader, cancel=cancel)
    assert data == original and cache == before


@pytest.mark.parametrize("patch", [{"revision": 4}, {"descriptor": SourceDescriptor("primary:A", "g2", "t1", 1000, 120)},
                                   {"descriptor": SourceDescriptor("primary:A", "g1", "t2", 1000, 120)}])
def test_source_project_staleness_during_retrieval_is_rejected(monkeypatch, patch):
    data = segments()
    req = request(data)
    current = [req.state]
    original = retrieval.rank_windows
    def change(*a, **kw):
        result = original(*a, **kw)
        current[0] = replace(req.state, **patch)
        return result
    monkeypatch.setattr(retrieval, "rank_windows", change)
    with pytest.raises(EditWindowError, match="changed during"):
        run(data, req=req, reader=lambda: current[0])


def test_full_input_identity_rejects_changed_unselected_text_or_metadata():
    data = segments()
    req = request(data)
    data[-1]["words"][0]["probability"] = .5
    with pytest.raises(EditWindowError, match="full canonical"):
        run(data, req=req)


def test_cache_namespace_binds_policy_source_versions_and_entire_original_request():
    data = regular(30)
    req = request(data)
    cache = {"decision": {"semantic_mapping_verified": True}}
    before = copy.deepcopy(cache)
    a, _ = run(data, req=req, cache=cache)
    b, _ = run(data, req=req, cache=cache)
    assert a == b and cache == before and a["cache_key"].startswith("window-retrieval-preview:")
    variants = [replace(req, policy=replace(req.policy, shortlist_size=8)),
                replace(req, state=replace(req.state, revision=4))]
    for desc in [replace(req.source.descriptor, transcript_version="t2"), replace(req.source.descriptor, asr_origin_seconds=121)]:
        variants.append(request(data, descriptor=desc))
    assert all(run(data, req=v)[0]["cache_key"] != a["cache_key"] for v in variants)
    assert run(data, req=req, instruction="Make one video. Aim for 45–60 seconds. Preserve the negation.")[0]["cache_key"] != a["cache_key"]


@pytest.mark.parametrize("patch", [{"max_pairs": True}, {"max_pairs": 16385}, {"max_source_starts": 0},
                                   {"max_endpoints_per_start": 65}, {"shortlist_size": 33}])
def test_invalid_or_unbounded_policy_is_rejected(patch):
    with pytest.raises(EditWindowError):
        replace(retrieval.WindowRetrievalPolicy(), **patch)


def test_request_has_no_candidate_injection_fields_and_cannot_be_mutated():
    req = request(segments())
    assert set(req.__dataclass_fields__) == {"source", "state", "policy"}
    with pytest.raises(TypeError):
        retrieval.WindowRetrievalRequest(req.source, req.state, selected_window_ids=("manual",))
    with pytest.raises(FrozenInstanceError):
        req.policy.shortlist_size = 1


def test_default_entry_cannot_enable_retrieval_from_settings_or_brief(monkeypatch):
    def original(beats, enriched, *_a, **_k):
        return {"keep_ids": [r["id"] for r in enriched], "remove_ids": []}, {}
    monkeypatch.setattr(story, "hierarchical_story_edit", original)
    monkeypatch.setattr(retrieval, "retrieve_windows", lambda *_a: pytest.fail("Default activated retrieval"))
    result, engine = story.plan_edit(segments(), SimpleNamespace(ai={"window_retrieval_enabled": True}),
        brief(window_retrieval_enabled=True, source_window_request=request(segments())))
    assert engine == "ollama_hierarchical_story" and "decision" in result and "retrieval" not in result
    assert inspect.signature(story.plan_edit).parameters["source_window_request"].default is None


def test_portable_retrieval_runs_automatically_without_manual_composition_injection():
    raw = source_bytes()
    assert hashlib.sha256(raw).hexdigest() == source_sha256()
    data = json.loads(raw)["segments"]
    before = copy.deepcopy(data)
    desc = SourceDescriptor("supplied-en-diagnostic", "saved-receipt-not-media-hash", hashlib.sha256(raw).hexdigest(), 3505.002667, 120)
    req = request(data, descriptor=desc)
    result, engine = run(data, req=req)
    expected = brute_pairs(req.source, effective_duration_bounds(brief()))
    assert result["retrieval"]["feasible_continuous_pairs"] == len(expected)
    assert result["retrieval"]["retrieved_pairs"] == len(expected)  # All numeric continuous alternatives, not semantic coverage.
    assert result["retrieval"]["continuous_domain_exhausted"] is True
    assert result["ranked_candidates"] and engine == "source_window_retrieval_preview"
    assert result["selection"] is None and result["selected_evidence"] == [] and "decision" not in result
    for ranked in result["ranked_candidates"]:
        view = next(v for v in result["views"] if v["window_id"] == ranked["window_id"])
        window = build_edit_window(req.source, view["row_ids"][0], view["row_ids"][-1])
        plan = compile_selected_spans(req.source, [window], brief=brief())
        assert 45 - retrieval.EPSILON <= plan.duration <= 60 + retrieval.EPSILON
    # The three-run manual comparator is NOT a continuous alternative and has
    # not been searched/composed here. No assertion that it is an AI winner.
    assert result["retrieval"]["noncontiguous_composition_search"] == "not_implemented"
    assert data == before and source_bytes() == raw
