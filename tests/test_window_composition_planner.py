"""Actual-entry ordered composition; numeric/source proof, never editorial QA."""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import itertools
import json
from pathlib import Path
import socket
import time
import tracemalloc
from types import SimpleNamespace
import urllib.request

import pytest

from cutroom import intelligence as story, ai_runtime, window_composition as composition
from cutroom.edit_windows import SourceDescriptor, EditWindowError, build_canonical_source
from cutroom.window_evidence import WindowSourceState
from cutroom.window_retrieval import WindowRetrievalPolicy
from cutroom.instruction_contract import effective_duration_bounds
from cutroom.story_budget import StoryBudgetError
from tests.test_window_evidence_planner import brief, segments
from tests.test_window_retrieval_planner import regular
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


@pytest.fixture(autouse=True)
def no_model_network(monkeypatch):
    def forbidden(*_a, **_kw):
        pytest.fail("Composition qualification cannot invoke inference/network")
    for module in (story, ai_runtime):
        monkeypatch.setattr(module, "open_ollama", forbidden)
    for name in ("_call_ollama_story_pass", "_ollama_chat", "hierarchical_story_edit", "story_ai_status"):
        monkeypatch.setattr(story, name, forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def request(data, policy=None, desc=None):
    desc = desc or SourceDescriptor("primary:A", "generation-one", "transcript-one", max(1000., data[-1]["end"]+121), 120)
    source = build_canonical_source(data, desc)
    return composition.WindowCompositionRequest(source, WindowSourceState("project_0123456789ab", 9, desc),
                                                 policy or composition.WindowCompositionPolicy())


def run(data=None, *, language="en", instruction=None, req=None, reader=None, cancel=None, cache=None):
    data = segments(language) if data is None else data
    req = req or request(data)
    return story.plan_edit(data, SimpleNamespace(ai={}), brief(language, instruction), story_cache=cache,
        cancel_check=cancel, source_window_request=req, source_window_state=reader or (lambda: req.state))


@pytest.mark.parametrize("language", ["en", "he"])
def test_actual_entry_automatically_composes_ordered_nonoverlapping_exact_source_ranges(language):
    data = segments(language)
    original = copy.deepcopy(data)
    result, engine = run(data, language=language)
    assert engine == "source_window_composition_preview"
    assert result["composition"]["multi_range_compositions_visited"] > 0
    assert any(len(p["clip_map"]) > 1 for p in result["ranked_compositions"])
    assert result["selection"] is None and result["selected_evidence"] == []
    assert "decision" not in result and "draft" not in result and result["editorial_status"] == "not_assessed"
    catalog = {r["id"]:r for r in result["canonical_evidence"]}
    for proposal in result["ranked_compositions"]:
        assert 45-1e-7 <= proposal["raw_seconds"] <= 60+1e-7
        clips = proposal["clip_map"]
        assert sum(c["end"]-c["start"] for c in clips) == pytest.approx(proposal["raw_seconds"])
        assert clips[0]["start"] == 0
        for a,b in zip(clips, clips[1:]):
            assert a["end"] == b["start"] and a["source_end"] < b["source_start"]
        selected = {row for c in clips for row in c["row_ids"]}
        assert len(selected) == sum(len(c["row_ids"]) for c in clips)
        assert all(catalog[ref]["segment_id"] in selected for ref in proposal["candidate_evidence_ids"])
        assert len(set(proposal["candidate_evidence_ids"])) == len(proposal["candidate_evidence_ids"])
        for ref in proposal["candidate_evidence_ids"]:
            evidence = catalog[ref];row = next(r for r in data if r["id"] == evidence["segment_id"])
            assert evidence["text"] == row["text"][evidence["char_start"]:evidence["char_end"]]
        for omission in proposal["omitted_source"]:
            assert omission["omitted_row_count"] >= 1 and omission["meaning_and_join_review"] == "pending"
        assert proposal["context_and_join_review"] == "pending"
    assert data == original and result["instruction_contract"]["verification_status"] == "unverified"


@pytest.mark.parametrize("language", ["en", "he"])
def test_exhaustive_small_generic_composition_domain_recall_without_known_examples(language):
    data = regular(6, 10, language)
    req = request(data)
    instruction = "Make one video. Aim for 20–40 seconds." if language == "en" else "צור סרטון אחד. כוון ל־20–40 שניות."
    result, _ = run(data, language=language, instruction=instruction, req=req)
    components = [(i,j) for i in range(6) for j in range(i,6) if (j-i+1)*10 <= 40]
    expected = set()
    for count in range(1,4):
        for ranges in itertools.product(components, repeat=count):
            if all(b+1<c for (a,b),(c,d) in zip(ranges,ranges[1:])):
                seconds = sum((b-a+1)*10 for a,b in ranges)
                if 20<=seconds<=40:
                    expected.add(ranges)
    actual = {tuple(tuple(r) for r in c["ranges"]) for c in result["candidate_index"]}
    assert actual == expected
    assert result["composition"]["configured_composition_domain_exhausted"] is True
    assert result["composition"]["all_legal_edits_exhausted"] is False


@pytest.mark.parametrize("language,instruction", [
    ("en", "Choose one continuous source passage. Aim for 45–60 seconds."),
    ("he", "שמור על קטע המקור ללא חיתוכים. כוון ל־45–60 שניות."),
])
def test_explicit_no_cuts_never_runs_multirange_search(monkeypatch, language, instruction):
    monkeypatch.setattr(composition, "search_compositions", lambda *_a: pytest.fail("No-cuts enabled composition"))
    result, _ = run(language=language, instruction=instruction)
    assert result["composition"]["multi_range_search"] == "disabled_by_explicit_no_cuts"
    assert result["composition"]["source_continuity"] == "required"
    assert all(len(p["clip_map"]) == 1 for p in result["ranked_compositions"])
    assert result["selection"] is None


@pytest.mark.parametrize("language", ["en", "he"])
def test_one_output_does_not_forbid_related_cuts(language):
    result, _ = run(language=language)
    assert result["composition"]["single_output_requested"] is True
    assert result["composition"]["source_continuity"] == "unspecified"
    assert any(len(p["clip_map"]) > 1 for p in result["ranked_compositions"])


@pytest.mark.parametrize("language,instruction", [("en", "Make exactly 60 seconds."), ("he", "צור סרטון של 60 שניות.")])
def test_exact_duration_retains_real_whole_row_boundaries_without_padding(language, instruction):
    data = regular(8, 10, language)
    result, _ = run(data, language=language, instruction=instruction)
    assert result["ranked_compositions"]
    assert any(len(p["clip_map"]) > 1 for p in result["ranked_compositions"])
    assert all(p["raw_seconds"] == 60 for p in result["ranked_compositions"])
    assert result["composition"]["bounds"]["origin"] == "explicit_user_exact"


def test_no_exact_numeric_composition_does_not_claim_semantic_source_failure():
    result, _ = run(regular(5, 11), instruction="Make exactly 60 seconds.")
    assert result["ranked_compositions"] == []
    assert result["composition"]["status"] == "no_numeric_fit_in_configured_search_only"
    assert result["composition"]["all_legal_edits_exhausted"] is False
    assert result["canonical_evidence"] and result["selected_evidence"] == []
    assert result["composition"]["semantic_assessment"] == "not_performed"


def test_internal_untranscribed_gaps_are_retained_and_omissions_are_exact_source_time():
    result, _ = run()
    for proposal in result["ranked_compositions"]:
        for clip in proposal["clip_map"]:
            assert clip["source_start"] >= 120
            assert clip["end"]-clip["start"] == pytest.approx(clip["source_end"]-clip["source_start"])
        for (a,b), omission in zip(zip(proposal["clip_map"],proposal["clip_map"][1:]), proposal["omitted_source"]):
            assert (omission["source_start"],omission["source_end"]) == (a["source_end"],b["source_start"])


def test_default_beam_and_transition_caps_report_partial_search_and_never_overclaim_coverage():
    data = regular(100, 4)
    policy = composition.WindowCompositionPolicy(
        windows=WindowRetrievalPolicy(max_source_starts=16,max_pairs=128,max_endpoints_per_start=8),
        beam_size=4, successors_per_state=2, max_transitions=16, max_source_span=90, shortlist_size=4)
    result, _ = run(data, req=request(data,policy))
    receipt = result["composition"]
    assert receipt["attempted_transitions"] <= 16 and receipt["beam_pruned_states"] > 0
    assert receipt["configured_composition_domain_exhausted"] is False
    assert receipt["component_domain_exhausted"] is False
    for p in result["ranked_compositions"]:
        if len(p["clip_map"]) > 1:
            assert p["clip_map"][-1]["source_end"]-p["clip_map"][0]["source_start"] <= 90
    assert result["selection"] is None


def test_tiny_budget_does_not_overrun_transitions_or_fake_completion():
    policy = composition.WindowCompositionPolicy(max_transitions=1, beam_size=64)
    result, _ = run(regular(20,5), req=request(regular(20,5),policy))
    assert result["composition"]["attempted_transitions"] <= 1
    assert result["composition"]["configured_composition_domain_exhausted"] is False


def test_numeric_tolerance_does_not_prune_a_valid_extension_and_claim_exhaustion():
    # Raw-second algebra only, not a claim these are physical export frames.
    data=[{"id":"a","start":0.,"end":59.99999998,"text":"Source a"},
          {"id":"omitted","start":59.99999998,"end":59.999999985,"text":"Omitted row"},
          {"id":"b","start":59.999999985,"end":60.,"text":"Source b"}]
    req=request(data,desc=SourceDescriptor("asset","g","t",1000))
    result,_=run(data,req=req,instruction="Make exactly 60 seconds.")
    assert ((0,0),(2,2)) in {tuple(tuple(r) for r in c["ranges"]) for c in result["candidate_index"]}
    assert result["composition"]["configured_composition_domain_exhausted"] is True


def test_full_actual_path_runtime_memory_and_materialization_budgets():
    data = regular(40,5)
    policy = composition.WindowCompositionPolicy(
        windows=WindowRetrievalPolicy(max_source_starts=32,max_pairs=256,max_view_row_references=120,max_view_text_characters=12000),
        beam_size=16,max_transitions=256,successors_per_state=8,shortlist_size=6)
    req = request(data, policy)
    tracemalloc.start();started = time.monotonic()
    try:
        result, _ = run(data, req=req)
        _,peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert time.monotonic()-started < 10 and peak < 16*1024**2
    refs = sum(len(c["row_ids"]) for p in result["ranked_compositions"] for c in p["clip_map"])
    assert refs <= 120 and len(result["candidate_index"]) <= 256+256
    assert result["ranked_compositions"]


def test_blocked_materialization_is_distinct_from_no_numeric_solution():
    data = regular(200,.3)
    policy = composition.WindowCompositionPolicy(windows=WindowRetrievalPolicy(max_pairs=256,max_source_starts=32,
        max_view_row_references=1,max_view_text_characters=1),beam_size=4,max_transitions=16)
    result, _ = run(data, req=request(data,policy))
    assert result["candidate_index"] and result["ranked_compositions"] == []
    assert result["composition"]["status"] == "materialization_budget_blocked"


@pytest.mark.parametrize("stage", ["enumeration", "ranking", "last_state"])
def test_cancellation_preserves_inputs_and_existing_semantic_cache(monkeypatch, stage):
    data = regular(12,5);req = request(data);before=copy.deepcopy(data)
    cache={"old_decision":{"semantic_mapping_verified":True}};original=copy.deepcopy(cache)
    aborted=[False]
    def check():
        if aborted[0]:raise InterruptedError("cancelled")
    if stage in {"enumeration","ranking"}:
        name="search_compositions" if stage=="enumeration" else "rank_compositions"
        method=getattr(composition,name)
        def abort(*a,**kw):
            aborted[0]=True
            return method(*a,**kw)
        monkeypatch.setattr(composition,name,abort)
    calls=[]
    def reader():
        calls.append(1)
        if stage=="last_state" and len(calls)==5:aborted[0]=True
        return req.state
    with pytest.raises(InterruptedError):run(data,req=req,reader=reader,cancel=check,cache=cache)
    assert data==before and cache==original


@pytest.mark.parametrize("patch", [{"revision":10},{"descriptor":SourceDescriptor("primary:A","new","transcript-one",1000,120)}])
def test_stale_source_during_composition_aborts_before_preview(monkeypatch,patch):
    data=segments();req=request(data);current=[req.state];method=composition.search_compositions
    def changed(*a,**kw):
        result=method(*a,**kw);current[0]=replace(req.state,**patch);return result
    monkeypatch.setattr(composition,"search_compositions",changed)
    with pytest.raises(EditWindowError,match="changed during"):
        run(data,req=req,reader=lambda:current[0])


def test_full_canonical_metadata_and_versions_bind_preview_and_cache_identity():
    data=segments();req=request(data);cache={"old":True}
    first,_=run(data,req=req,cache=cache);again,_=run(data,req=req,cache=cache)
    assert first==again and cache=={"old":True} and first["cache_key"].startswith("window-composition-preview:")
    for altered in [replace(req,policy=replace(req.policy,beam_size=8)),replace(req,state=replace(req.state,revision=10)),
                    request(data,desc=replace(req.source.descriptor,transcript_version="new"))]:
        assert run(data,req=altered)[0]["cache_key"]!=first["cache_key"]
    data[-1]["words"][0]["probability"]=.4
    with pytest.raises(EditWindowError,match="full canonical"):
        run(data,req=req)


@pytest.mark.parametrize("patch", [{"max_ranges":4},{"max_transitions":16385},{"beam_size":False},
                                   {"max_source_span":float("inf")},{"shortlist_size":17}])
def test_policy_is_bounded_and_request_has_no_injected_candidate_fields(patch):
    with pytest.raises(EditWindowError):replace(composition.WindowCompositionPolicy(),**patch)
    req=request(segments())
    assert set(req.__dataclass_fields__)=={"source","state","policy","search"}
    # Optional durable run reference contains no caller-injected candidates or
    # frontier. The original path still has no local search state by default.
    assert req.search is None
    with pytest.raises(TypeError):composition.WindowCompositionRequest(req.source,req.state,selected_window_ids=("known",))
    with pytest.raises(FrozenInstanceError):req.policy.max_ranges=1


def test_no_unverified_grammar_gate_in_composition_and_no_text_repair():
    data=regular(40,5)
    for row in data:row["text"]="לא שיניתי את התמלול and an unfinished prefix"
    before=copy.deepcopy(data)
    result,_=run(data)
    assert result["ranked_compositions"] and data==before
    assert result["composition"]["semantic_assessment"]=="not_performed"


def test_default_settings_and_brief_cannot_activate_experimental_composition(monkeypatch):
    def original(beats,enriched,*_a,**_kw):return {"keep_ids":[r["id"] for r in enriched],"remove_ids":[]},{}
    monkeypatch.setattr(story,"hierarchical_story_edit",original)
    monkeypatch.setattr(composition,"search_compositions",lambda *_a:pytest.fail("Default enabled composition"))
    result,engine=story.plan_edit(segments(),SimpleNamespace(ai={"composition_enabled":True}),
        brief(composition_enabled=True,source_window_request=request(segments())))
    assert "decision" in result and "ranked_compositions" not in result and engine=="ollama_hierarchical_story"
    assert inspect.signature(story.plan_edit).parameters["source_window_request"].default is None


def test_portable_automatic_composition_is_not_manual_reference_injection():
    raw = source_bytes()
    assert hashlib.sha256(raw).hexdigest() == source_sha256()
    data = json.loads(raw)["segments"]
    before = copy.deepcopy(data)
    desc=SourceDescriptor("supplied-en-diagnostic","saved-receipt-not-media-hash",hashlib.sha256(raw).hexdigest(),3505.002667,120)
    req=request(data,desc=desc)
    result,engine=run(data,req=req)
    assert engine=="source_window_composition_preview" and result["composition"]["multi_range_compositions_visited"]>0
    assert any(len(p["clip_map"])>1 for p in result["ranked_compositions"])
    from tests.test_window_retrieval_planner import request as retrieval_request, run as retrieve
    prior, _ = retrieve(data, req=retrieval_request(data, descriptor=desc))
    assert result["canonical_evidence"] == prior["canonical_evidence"]
    assert result["selection"] is None and result["selected_evidence"]==[] and "decision" not in result
    assert result["composition"]["configured_composition_domain_exhausted"] is False
    assert data == before and source_bytes() == raw
