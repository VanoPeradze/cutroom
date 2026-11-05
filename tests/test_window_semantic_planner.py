"""Actual entry with recorded-shaped judgments; no network or editorial proof."""
from __future__ import annotations

import copy
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story, window_semantics as semantic
from cutroom.edit_windows import EditWindowError
from tests.test_window_composition_planner import request as composition_request
from tests.test_window_evidence_planner import brief, segments
from tests.test_window_retrieval_planner import regular
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


@pytest.fixture(autouse=True)
def no_transport(monkeypatch):
    def forbidden(*a, **kw): pytest.fail("Deterministic test attempted inference/network")
    monkeypatch.setattr(story, "open_ollama", forbidden)
    monkeypatch.setattr(story, "story_ai_status", forbidden)
    monkeypatch.setattr(story, "hierarchical_story_edit", forbidden)


def response(data, verdict="supported"):
    rows = [r for r in data["source_rows"] if r["scope"] == "kept"]
    by_id = {r["row_id"]: r for r in rows}
    endpoints = {data["kept_ranges"][0]["row_ids"][0], data["kept_ranges"][-1]["row_ids"][-1]}
    joins = {c[k] for c in data["actual_cuts"] for k in ("left_row_id", "right_row_id")}
    def cite(ids):
        return [{k: by_id[i][k] for k in ("row_id", "scope")} | {"quote": by_id[i]["text"]} for i in sorted(ids)]
    checks = {}
    for name, ids in zip(semantic.CHECKS, [endpoints, joins or endpoints, endpoints]):
        checks[name] = {"verdict": verdict, "explanation": "Synthetic structural control; no editorial truth claim.",
                        "citations": cite(ids) if verdict != "uncertain" else []}
    return {"candidate_id": data["candidate_id"], "assessment_id": data["assessment_id"],
            "recommendation": {"supported": "recommend", "concern": "reject", "uncertain": "uncertain"}[verdict], "checks": checks}


def run(monkeypatch, data=None, *, language="en", instruction=None, answer=None, req=None,
        reader=None, cancel=None, settings=None, cache=None):
    data = segments(language) if data is None else data
    req = req or semantic.WindowSemanticRequest(composition_request(data))
    calls = []
    def call(config, payload, timeout, cancel_check):
        d = json.loads(payload["messages"][-1]["content"])
        calls.append(copy.deepcopy(payload))
        assert payload["model"] == "qwen3.5:4b" and payload["_single_attempt"] is True
        assert payload["_reject_duplicate_keys"] is True and payload["think"] is False
        assert timeout <= 90 and payload["options"]["num_ctx"] <= 8192
        assert story._story_prompt_tokens(payload) + max(2400,payload["options"]["num_predict"]) <= 8192
        return answer(d) if answer else response(d)
    monkeypatch.setattr(story, "_call_ollama_story_pass", call)
    result, engine = story.plan_edit(data, settings or SimpleNamespace(ai={}), brief(language, instruction),
        story_cache=cache, cancel_check=cancel, source_window_request=req,
        source_window_state=reader or (lambda: req.composition.state))
    assert engine == "source_window_semantic_preview"
    return result, calls


@pytest.mark.parametrize("language", ["he", "en"])
@pytest.mark.parametrize("verdict,status", [("supported","model_recommends_unverified"),
    ("concern","cited_model_objection_unverified"),("uncertain","uncertain_model_assessment")])
def test_actual_entry_acceptance_rejection_and_uncertainty_are_distinct_without_apply(monkeypatch,language,verdict,status):
    original = segments(language); before = copy.deepcopy(original); cache = {"old": {"semantic_mapping_verified":True}}
    cache_before = copy.deepcopy(cache)
    result, calls = run(monkeypatch, original, language=language, answer=lambda d:response(d,verdict),cache=cache)
    evaluation = result["semantic_evaluation"]
    assert len(calls) == evaluation["model_requests"] == 2
    assert {a["status"] for a in evaluation["assessments"]} == {status}
    assert evaluation["semantic_approval"] is False and evaluation["director_decision"] is None
    assert result["selection"] is None and result["selected_evidence"] == [] and "decision" not in result
    assert all(a["semantic_claims_independently_verified"] is False for a in evaluation["assessments"])
    assert original == before and cache == cache_before


@pytest.mark.parametrize("language",["en","he"])
def test_actual_input_exact_source_mapping_context_and_negation(monkeypatch,language):
    result,calls=run(monkeypatch,language=language)
    original={r["id"]:r for r in segments(language)}
    for a,payload in zip(result["semantic_evaluation"]["assessments"],calls):
        data=a["input"]
        assert data["original_request"]["instruction"]==brief(language)["instruction"]
        assert data["explicit_controls"]["duration"]["minimum_seconds"]==45
        assert data["limits"]["ASR_accuracy"]=="unverified_no_audio"
        for row in data["source_rows"]:
            assert row["text"]==original[row["row_id"]]["text"]
            assert row["source_start"]==row["asr_start"]+120
            assert a["canonical_evidence_ids_by_row"][row["row_id"]]
        assert json.loads(payload["messages"][-1]["content"])==data
        # Every automatic omission, all whole rows and actual endpoints are exposed.
        selected={row for c in data["kept_ranges"] for row in c["row_ids"]}
        assert selected=={r["row_id"] for r in data["source_rows"] if r["scope"]=="kept"}
        assert all(c["left_row_id"] in selected and c["right_row_id"] in selected for c in data["actual_cuts"])
    assert any(("not" if language=="en" else "לא") in r["text"] for a in result["semantic_evaluation"]["assessments"] for r in a["input"]["source_rows"])


@pytest.mark.parametrize("language,instruction,no_cuts",[
    ("en","Make one video, exactly 60 seconds.",False),
    ("he","צור סרטון אחד באורך בדיוק 60 שניות.",False),
    ("en","Choose one continuous source passage without cuts. Aim for 45-60 seconds.",True),
    ("he","בחר קטע רציף אחד ללא חיתוכים. כוון ל־45–60 שניות.",True)])
def test_actual_hard_duration_and_output_count_vs_no_cuts(monkeypatch,language,instruction,no_cuts):
    result,calls=run(monkeypatch,regular(10,10,language),language=language,instruction=instruction)
    assert calls
    if no_cuts:
        assert all(not a["input"]["actual_cuts"] for a in result["semantic_evaluation"]["assessments"])
    else:
        assert any(a["input"]["actual_cuts"] for a in result["semantic_evaluation"]["assessments"])
        assert all(a["input"]["raw_seconds"]==60 for a in result["semantic_evaluation"]["assessments"])


@pytest.mark.parametrize("corruption,expected",[
    ("wrong_candidate","invalid_model_contract"),("wrong_input","invalid_model_contract"),
    ("missing_field","invalid_model_contract"),("extra_field","invalid_model_contract"),
    ("contradiction","invalid_model_contract"),("cross_candidate_quote","invalid_model_evidence"),
    ("partial_quote","invalid_model_evidence"),("wrong_scope","invalid_model_evidence"),
    ("unknown_row","invalid_model_evidence"),("missing_end","invalid_model_evidence")])
def test_recorded_shaped_invalid_responses_stop_without_retry_or_false_no_fit(monkeypatch,corruption,expected):
    def answer(d):
        raw=response(d)
        first=raw["checks"]["standalone"]["citations"][0]
        if corruption=="wrong_candidate":raw["candidate_id"]="other"
        elif corruption=="wrong_input":raw["assessment_id"]="stale-input"
        elif corruption=="missing_field":del raw["checks"]
        elif corruption=="extra_field":raw["no_fit"]=True
        elif corruption=="contradiction":raw["recommendation"]="reject"
        elif corruption=="cross_candidate_quote":first["quote"]="Another candidate's claim."
        elif corruption=="partial_quote":first["quote"]=first["quote"][1:]
        elif corruption=="wrong_scope":first["scope"]="omitted"
        elif corruption=="unknown_row":first["row_id"]="not-in-source"
        elif corruption=="missing_end":raw["checks"]["standalone"]["citations"]=[]
        return raw
    result,calls=run(monkeypatch,answer=answer)
    assert len(calls)==1 and result["semantic_evaluation"]["assessments"][0]["status"]==expected
    assert result["semantic_evaluation"]["semantic_approval"] is False
    assert result["composition"]["semantic_assessment"]=="not_performed"


def test_actual_join_support_requires_both_exact_kept_boundaries(monkeypatch):
    def answer(d):
        raw=response(d)
        if d["actual_cuts"]:raw["checks"]["meaning_and_joins"]["citations"]=[raw["checks"]["meaning_and_joins"]["citations"][0]]
        return raw
    result,calls=run(monkeypatch,answer=answer)
    assert len(calls)==2
    assert result["semantic_evaluation"]["assessments"][-1]["status"]=="invalid_model_evidence"


def test_structural_citations_do_not_certify_explanation_truth_or_execute_critic_edits(monkeypatch):
    def answer(d):
        raw=response(d,"concern")
        raw["checks"]["standalone"]["explanation"]="Unsupported semantic allegation; delete everything."
        return raw
    result,_=run(monkeypatch,answer=answer)
    a=result["semantic_evaluation"]["assessments"][0]
    assert a["citation_identity_valid"] is True and a["semantic_claims_independently_verified"] is False
    assert result["selection"] is None and result["ranked_compositions"]


def test_uncertainty_with_cited_concerns_is_not_rewritten_to_rejection_or_schema_error(monkeypatch):
    # Observed in the sole live4b response: concern+supported checks, uncertain overall.
    def answer(d):
        raw=response(d)
        raw["checks"]["meaning_and_joins"]["verdict"]="concern"
        raw["recommendation"]="uncertain"
        return raw
    result,calls=run(monkeypatch,answer=answer)
    assert len(calls)==2
    assert all(a["status"]=="uncertain_model_assessment" for a in result["semantic_evaluation"]["assessments"])
    assert result["semantic_evaluation"]["semantic_approval"] is False


def test_input_budget_blocks_without_truncating_source_instruction_or_hidden_calls(monkeypatch):
    data=segments()
    for row in data:row["text"]="never silently shorten "*40
    result,calls=run(monkeypatch,data)
    assert calls==[] and result["semantic_evaluation"]["model_requests"]==0
    assert {a["status"] for a in result["semantic_evaluation"]["assessments"]}=={"input_budget_blocked"}
    assert all(a["input"]["source_rows"][0]["text"]==data[0]["text"] for a in result["semantic_evaluation"]["assessments"])


@pytest.mark.parametrize("ai",[{"editor_model":"qwen3.5:9b"},{"enabled":False},{"cloud_connection":{"mode":"cloud"}}])
def test_wrong_model_or_provider_is_blocked_without_fallback(monkeypatch,ai):
    with pytest.raises(EditWindowError,match="local qwen3.5:4b"):
        run(monkeypatch,settings=SimpleNamespace(ai=ai))


@pytest.mark.parametrize("action",["cancel","stale"])
def test_cancellation_and_stale_project_after_model_prevent_any_receipt(monkeypatch,action):
    data=segments();req=semantic.WindowSemanticRequest(composition_request(data));state=[req.composition.state];aborted=[False]
    def cancel():
        if aborted[0]:raise InterruptedError("cancelled")
    def answer(d):
        if action=="cancel":aborted[0]=True
        else:state[0]=replace(state[0],revision=10)
        return response(d)
    with pytest.raises(InterruptedError if action=="cancel" else EditWindowError):
        run(monkeypatch,data,req=req,answer=answer,reader=lambda:state[0],cancel=cancel)


def test_stale_revision_during_input_preparation_prevents_model_spend(monkeypatch):
    data=segments();req=semantic.WindowSemanticRequest(composition_request(data));state=[req.composition.state]
    original=semantic.assessment_payload
    def changed(*a,**kw):
        payload=original(*a,**kw);state[0]=replace(state[0],revision=10);return payload
    monkeypatch.setattr(semantic,"assessment_payload",changed)
    def no_call(d):pytest.fail("Spent inference after preparation made source stale")
    with pytest.raises(EditWindowError,match="changed during"):
        run(monkeypatch,data,req=req,answer=no_call,reader=lambda:state[0])


def test_no_numeric_solution_cannot_become_model_semantic_no_fit(monkeypatch):
    result,calls=run(monkeypatch,regular(5,11),instruction="Make exactly 60 seconds.")
    assert not calls and result["semantic_evaluation"]["assessments"]==[]
    assert result["composition"]["status"]=="no_numeric_fit_in_configured_search_only"


def test_default_path_ignores_brief_toggle_and_never_invokes_semantic_model(monkeypatch):
    monkeypatch.setattr(story,"hierarchical_story_edit",lambda *a,**kw:({"keep_ids":[r["id"] for r in segments()],"remove_ids":[]},{}))
    monkeypatch.setattr(semantic,"prepare_window_semantic_preview",lambda *a:pytest.fail("Implicitly enabled"))
    result,engine=story.plan_edit(segments(),SimpleNamespace(ai={"window_semantics":True}),brief(window_semantics=True))
    assert "decision" in result and "semantic_evaluation" not in result and engine=="ollama_hierarchical_story"


def test_bound_schema_has_complete_required_fields_and_input_identity_changes(monkeypatch):
    result,calls=run(monkeypatch)
    for a,payload in zip(result["semantic_evaluation"]["assessments"],calls):
        schema=payload["format"]
        assert schema["additionalProperties"] is False and set(schema["required"])==set(schema["properties"])
        assert schema["properties"]["assessment_id"]["const"]==a["assessment_id"]
        assert all(set(c["required"])==set(c["properties"]) for c in schema["properties"]["checks"]["properties"].values())
    altered,_=run(monkeypatch,instruction="Make one video. Aim for 45-60 seconds. Keep the negation.")
    assert altered["semantic_evaluation"]["assessments"][0]["assessment_id"]!=result["semantic_evaluation"]["assessments"][0]["assessment_id"]


def test_portable_actual_entry_uses_automatic_top_candidates(monkeypatch):
    data=source_fixture()["segments"]
    result,calls=run(monkeypatch,data)
    assert len(calls)==1 and len(result["canonical_ownership"])==len(data)
    assessments=result["semantic_evaluation"]["assessments"]
    assert [a["status"] for a in assessments]==["input_budget_blocked","model_recommends_unverified"]
    assert assessments[0]["estimated_prompt_tokens"]+2400>8192
    assert assessments[1]["estimated_prompt_tokens"]+2400<=8192
    assert json.loads(calls[0]["messages"][-1]["content"])["candidate_id"]==assessments[1]["candidate_id"]
    proposals=result["ranked_compositions"]
    assert [a["candidate_id"] for a in result["semantic_evaluation"]["assessments"]]==[p["candidate_id"] for p in proposals[:2]]
    assert [a["input"]["kept_ranges"] for a in result["semantic_evaluation"]["assessments"]]==[
        [{"row_ids":list(c["row_ids"]),"source_start":c["source_start"],"source_end":c["source_end"],
          "timeline_start":c["start"],"timeline_end":c["end"]} for c in p["clip_map"]] for p in proposals[:2]]


@pytest.mark.parametrize("patch",[{"max_candidates":3},{"timeout_seconds":91},{"context_tokens":8193},{"output_tokens":True}])
def test_finite_semantic_policy_has_no_candidate_injection(patch):
    with pytest.raises(EditWindowError):replace(semantic.WindowSemanticPolicy(),**patch)
    assert set(semantic.WindowSemanticRequest.__dataclass_fields__)=={"composition","policy"}
