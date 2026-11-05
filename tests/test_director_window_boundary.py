"""Director rejects experimental previews; synthetic positives prove mapping only."""
from __future__ import annotations

import copy
from dataclasses import replace
from types import SimpleNamespace
import socket
import urllib.request

import pytest

from cutroom import director, intelligence, ai_runtime
from cutroom.jobs import JobCancelled
from cutroom.story_budget import StoryBudgetError
from cutroom.window_semantics import WindowSemanticRequest
from cutroom.window_composition import WindowCompositionRequest
from cutroom.window_evidence import WindowSourceState
from cutroom.edit_windows import SourceDescriptor, build_canonical_source
from cutroom.cache_keys import stable_fingerprint
from tests.test_window_composition_planner import request as composition_request
from tests.test_window_evidence_planner import segments, brief
from test_director_rebuild_cache import semantic_project


@pytest.fixture(autouse=True)
def no_model_media_network(monkeypatch):
    def forbidden(*a, **kw):pytest.fail("Director boundary tests cannot invoke model/network/media")
    for module in (intelligence,ai_runtime):monkeypatch.setattr(module,"open_ollama",forbidden)
    monkeypatch.setattr(intelligence,"_call_ollama_story_pass",forbidden)
    monkeypatch.setattr(urllib.request,"urlopen",forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden)


def control(language="en",instruction=None):
    data=segments(language);request=WindowSemanticRequest(composition_request(data));b=brief(language,instruction)
    result,engine=intelligence.plan_edit(data,SimpleNamespace(ai={}),b,source_window_request=request.composition,
        source_window_state=lambda:request.composition.state)
    result["semantic_evaluation"]={"assessments":[{"status":"model_recommends_unverified"}],"semantic_approval":False}
    result["qualification_origin"]="SYNTHETIC_POSITIVE_MAPPING_ONLY_NOT_REAL_EDITORIAL_QUALIFICATION"
    return data,request,b,result,"source_window_semantic_preview"


def validate(data,request,b,result,engine,*,reader=None,context=None):
    context=context or SimpleNamespace(check_cancelled=lambda:None)
    with pytest.raises(StoryBudgetError) as caught:
        director.validate_experimental_plan_result(context,result,engine,transcript_segments=data,settings=SimpleNamespace(ai={}),
            brief=b,request=request,read_current=reader or (lambda:request.composition.state),fps=30)
    return caught.value.diagnostic


@pytest.mark.parametrize("language",["he","en"])
def test_synthetic_positive_maps_exact_source_and_evidence_but_is_never_approved(language):
    data,request,b,result,engine=control(language);before=copy.deepcopy((data,b,result))
    report=validate(data,request,b,result,engine)
    assert report["mechanical_mapping_validated"] is True
    assert report["semantic_approval"] is False and report["completed_edit"] is False and report["applied_to_timeline"] is False
    assert report["outcome"]=="unapproved_experimental_plan"
    for checked,proposal in zip(report["mapped_proposals"],result["ranked_compositions"]):
        assert checked["clip_map"]==proposal["clip_map"] and checked["exact_evidence_ids"]==proposal["candidate_evidence_ids"]
        assert 45<=checked["raw_seconds"]<=60 and 45<=checked["framed_seconds"]<=60
        assert all(c["source_start"]>=120 for c in checked["clip_map"])
    assert (data,b,result)==before


@pytest.mark.parametrize("status",["uncertain_model_assessment","cited_model_objection_unverified","input_budget_blocked",
    "invalid_model_contract","invalid_model_evidence","model_recommends_unverified"])
def test_every_nonapproved_outcome_preserves_input_and_existing_project_state(status):
    data,request,b,result,engine=control();result["semantic_evaluation"]["assessments"][0]["status"]=status
    existing={"revision":19,"manual":{"cuts":[{"start":5,"end":8}]},"draft":{"output_duration":66},"settings":b}
    before=copy.deepcopy((existing,result,data,b))
    report=validate(data,request,b,result,engine)
    assert report["assessment_statuses"]==[status] and report["completed_edit"] is False
    assert (existing,result,data,b)==before


@pytest.mark.parametrize("patch",[
    {"instruction":"Make one video. Aim for 45-60 seconds. No cuts."},
    {"instruction":"צור סרטון אחד ללא חיתוכים. כוון ל־45–60 שניות."},
    {"instruction":"Make exactly 60 seconds."},
    {"instruction":"צור סרטון באורך בדיוק 60 שניות."},
])
def test_changed_hard_duration_or_no_cuts_request_cannot_reuse_old_result(patch):
    data,request,b,result,engine=control();changed={**b,**patch}
    report=validate(data,request,changed,result,engine)
    assert report["outcome"]=="invalid_experimental_plan" and report["mechanical_mapping_validated"] is False


@pytest.mark.parametrize("language,instruction,no_cuts",[
    ("en","Make one video. Aim for45-60seconds.",False),
    ("he","צור סרטון אחד. כוון ל־45–60 שניות.",False),
    ("en","Choose one continuous source passage without cuts. Aim for 45-60 seconds.",True),
    ("he","בחר קטע רציף אחד ללא חיתוכים. כוון ל־45–60 שניות.",True),
])
def test_actual_planner_mapping_preserves_one_output_vs_no_cuts(language,instruction,no_cuts):
    data,request,b,result,engine=control(language,instruction)
    report=validate(data,request,b,result,engine)
    assert report["mechanical_mapping_validated"] is True
    maps=report["mapped_proposals"]
    assert maps and (all(len(p["clip_map"])==1 for p in maps) if no_cuts else any(len(p["clip_map"])>1 for p in maps))
    assert report["semantic_approval"] is False


@pytest.mark.parametrize("tamper",["quote","evidence_membership","clip_time","bool_time","selected_scope","canonical_owner","original_request"])
def test_tampered_canonical_evidence_or_source_mapping_is_rejected(tamper):
    data,request,b,result,engine=control()
    if tamper=="quote":result["canonical_evidence"][0]["text"]="Changed source quote"
    elif tamper=="evidence_membership":result["ranked_compositions"][0]["candidate_evidence_ids"]=["unknown"]
    elif tamper=="clip_time":result["ranked_compositions"][0]["clip_map"][0]["source_start"]+=.01
    elif tamper=="bool_time":result["ranked_compositions"][0]["clip_map"][0]["start"]=False
    elif tamper=="selected_scope":result["selected_evidence"]=result["canonical_evidence"][:1]
    elif tamper=="canonical_owner":result["canonical_ownership"][0]["beat_id"]="alternate-owner"
    elif tamper=="original_request":result["original_request"]["instruction"]="Make it look successful"
    before=copy.deepcopy(result);report=validate(data,request,b,result,engine)
    assert report["outcome"]=="invalid_experimental_plan" and report["mechanical_mapping_validated"] is False
    assert result==before


@pytest.mark.parametrize("change",["revision","asset","transcript","origin"])
def test_current_source_version_must_match_and_stale_results_never_apply(change):
    data,request,b,result,engine=control();state=request.composition.state
    if change=="revision":current=replace(state,revision=state.revision+1)
    else:
        patch={"asset":{"asset_version":"new"},"transcript":{"transcript_version":"new"},"origin":{"asr_origin_seconds":121}}[change]
        current=replace(state,descriptor=replace(state.descriptor,**patch))
    report=validate(data,request,b,result,engine,reader=lambda:current)
    assert report["outcome"]=="invalid_experimental_plan" and "changed during" in report["validation_error"]


def test_unselected_source_text_or_metadata_change_invalidates_result():
    data,request,b,result,engine=control();data[-1]["words"][0]["probability"]=.1
    before=copy.deepcopy(data);report=validate(data,request,b,result,engine)
    assert report["outcome"]=="invalid_experimental_plan" and data==before


@pytest.mark.parametrize("phase",["before","during_rederive","after_rederive"])
def test_cancellation_propagates_without_result_or_mutation(phase):
    data,request,b,result,engine=control();before=copy.deepcopy((data,result));reads=[0]
    def reader():reads[0]+=1;return request.composition.state
    def cancelled():
        if phase=="before" or phase=="during_rederive" and reads[0]>=1 or phase=="after_rederive" and reads[0]>=5:
            raise JobCancelled("cancelled")
    with pytest.raises(JobCancelled):
        director.validate_experimental_plan_result(SimpleNamespace(check_cancelled=cancelled),result,engine,
            transcript_segments=data,settings=SimpleNamespace(ai={}),brief=b,request=request,read_current=reader)
    assert (data,result)==before


@pytest.mark.parametrize("legacy",[False,True])
def test_actual_director_planner_wrapper_blocks_preview_and_legacy_hook( monkeypatch,legacy):
    data,request,b,result,engine=control();before=copy.deepcopy(result)
    if legacy:
        def hook(data,settings,brief,progress=None,story_cache=None):return result,engine
    else:
        def hook(*a,**kw):return result,engine
    monkeypatch.setattr(director,"plan_edit",hook)
    with pytest.raises(StoryBudgetError) as exc:
        director._plan_edit_with_cancel(SimpleNamespace(check_cancelled=lambda:None),data,SimpleNamespace(ai={}),b,
            progress=lambda *_a:None,story_cache=None)
    assert exc.value.diagnostic["applied_to_timeline"] is False and result==before


def test_forged_approval_or_old_decision_fields_cannot_make_preview_a_completed_edit(monkeypatch):
    data,request,b,result,engine=control()
    result.update(semantic_approval=True,decision={"keep_ids":["s1"],"semantic_mapping_verified":True},draft={"ready":True})
    result["semantic_evaluation"]["semantic_approval"]=True
    report=validate(data,request,b,result,"deterministic")
    assert report["applied_to_timeline"] is False and report["completed_edit"] is False and report["semantic_approval"] is False


@pytest.mark.parametrize("location",["editorial_cache","analysis"])
def test_preview_in_actual_project_cache_is_blocked_before_any_project_change(semantic_project,location):
    store,settings,pid,calls,context=semantic_project
    _data,_request,_brief,preview,engine=control()
    def poison(p):
        if location=="analysis":p["analysis"].update(preview)
        else:p["analysis"]["editorial_cache"]=preview
    store.update(pid,poison);before=store.load(pid);raw=store.state_path(pid).read_bytes();prior=copy.deepcopy(calls)
    with pytest.raises(StoryBudgetError):director.analyze_project(context(),pid,store,settings)
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw and calls==prior


@pytest.mark.parametrize("status",["uncertain_model_assessment","input_budget_blocked","invalid_model_contract"])
def test_actual_analysis_plugin_preview_cannot_replace_existing_edit(semantic_project,monkeypatch,status):
    store,settings,pid,_calls,context=semantic_project
    _data,_request,_brief,preview,engine=control();preview["semantic_evaluation"]["assessments"][0]["status"]=status
    monkeypatch.setattr(director,"_plan_edit_with_cancel",lambda *a,**kw:(preview,engine))
    before=store.load(pid);raw=store.state_path(pid).read_bytes()
    with pytest.raises(StoryBudgetError):director.analyze_project(context(),pid,store,settings,{"instruction":"New request; keep my existing edit."})
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw


def test_normal_director_result_and_old_hook_behavior_unchanged(monkeypatch):
    original={"segments":segments(),"decision":{"keep_ids":["s1"],"remove_ids":[]}}
    def legacy(data,settings,brief,progress=None,story_cache=None):return original,"deterministic"
    monkeypatch.setattr(director,"plan_edit",legacy)
    result=director._plan_edit_with_cancel(SimpleNamespace(check_cancelled=lambda:None),segments(),SimpleNamespace(ai={}),brief(),
        progress=lambda *_a:None,story_cache=None)
    assert result==(original,"deterministic") and result[0] is original


@pytest.mark.parametrize("malformed",[None,{},[],{"decision":{"keep_ids":[]}}])
def test_explicit_request_never_bypasses_boundary_by_removing_preview_markers(malformed):
    data,request,b,_result,_engine=control()
    report=validate(data,request,b,malformed,"deterministic")
    assert report["outcome"]=="invalid_experimental_plan" and report["applied_to_timeline"] is False


def test_empty_numeric_search_does_not_claim_a_validated_mapping():
    from tests.test_window_retrieval_planner import regular
    data=regular(5,11);composition=composition_request(data);request=WindowSemanticRequest(composition)
    b=brief(instruction="Make exactly 60 seconds.")
    result,engine=intelligence.plan_edit(data,SimpleNamespace(ai={}),b,source_window_request=composition,
        source_window_state=lambda:composition.state)
    assert not result["ranked_compositions"]
    report=validate(data,request,b,result,engine)
    assert report["canonical_source_validated"] is True and report["mechanical_mapping_validated"] is False
    assert report["mapped_proposals"]==[] and report["completed_edit"] is False


def stored_control(store,settings,pid,status):
    current=store.load(pid);data=current["analysis"]["transcript"]["segments"]
    descriptor=SourceDescriptor("primary:A",current["sources"]["A"]["generation"],stable_fingerprint("test-asr",data),
                                current["sources"]["A"]["duration"])
    composition=WindowCompositionRequest(build_canonical_source(data,descriptor),WindowSourceState(pid,current["revision"],descriptor))
    b=brief();result,engine=intelligence.plan_edit(data,settings,b,source_window_request=composition,source_window_state=lambda:composition.state)
    result["semantic_evaluation"]={"assessments":[{"status":status}],"semantic_approval":False}
    result["qualification_origin"]="SYNTHETIC_MAPPING_ONLY"
    return {"editorial":result,"engine":"source_window_semantic_preview","request":WindowSemanticRequest(composition),"brief":b}


@pytest.mark.parametrize("status",["uncertain_model_assessment","cited_model_objection_unverified","input_budget_blocked",
    "invalid_model_contract","invalid_model_evidence","model_recommends_unverified"])
def test_actual_early_validation_no_draft_no_preprocessing_no_project_mutation(semantic_project,monkeypatch,status):
    store,settings,pid,_calls,context=semantic_project
    store.update(pid,lambda p:p.update(draft=None))
    payload=stored_control(store,settings,pid,status);before=store.load(pid);raw=store.state_path(pid).read_bytes()
    def forbidden(*a,**kw):pytest.fail("Early validation entered preprocessing or project save")
    for name in ["_transcribe_safely","analyze_audio","detect_scenes"]:monkeypatch.setattr(director,name,forbidden)
    monkeypatch.setattr(store,"update",forbidden);monkeypatch.setattr(store,"save",forbidden)
    with pytest.raises(StoryBudgetError) as exc:
        director.analyze_project(context(),pid,store,settings,experimental_plan_validation=payload)
    assert exc.value.diagnostic["mechanical_mapping_validated"] is True
    assert exc.value.diagnostic["completed_edit"] is False
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("change",["revision","generation","transcript"])
def test_early_validation_rereads_authoritative_store_and_rejects_stale_snapshot(semantic_project,change):
    store,settings,pid,_calls,context=semantic_project;payload=stored_control(store,settings,pid,"uncertain_model_assessment")
    def change_source(p):
        if change=="generation":p["sources"]["A"]["generation"]="replacement"
        elif change=="transcript":p["analysis"]["transcript"]["segments"][-1]["text"]="Changed unselected source"
        else:p["manual"]["unrelated_edit"]=True
    store.update(pid,change_source);before=store.load(pid);raw=store.state_path(pid).read_bytes()
    with pytest.raises(StoryBudgetError) as exc:
        director.analyze_project(context(),pid,store,settings,experimental_plan_validation=payload)
    assert exc.value.diagnostic["outcome"]=="invalid_experimental_plan"
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("provenance",[{"audio_source":"B","audio_timeline_offset":0.},
    {"audio_source":"A","audio_timeline_offset":3.}, {"audio_source":None,"audio_timeline_offset":0.},
    {"audio_source":"A","audio_timeline_offset":None},{"audio_source":"A","audio_timeline_offset":False}])
def test_cached_wrong_or_unknown_audio_source_timebase_cannot_be_relabelled_primary_a(semantic_project,provenance):
    store,settings,pid,_calls,context=semantic_project
    store.update(pid,lambda p:p["analysis"].update(provenance))
    payload=stored_control(store,settings,pid,"model_recommends_unverified")
    before=store.load(pid);raw=store.state_path(pid).read_bytes()
    with pytest.raises(StoryBudgetError) as exc:
        director.analyze_project(context(),pid,store,settings,experimental_plan_validation=payload)
    assert exc.value.diagnostic["outcome"]=="invalid_experimental_plan"
    assert exc.value.diagnostic["mechanical_mapping_validated"] is False
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("instruction",["Make one video without cuts. Aim for 45-60 seconds.",
    "צור סרטון אחד ללא חיתוכים. כוון ל־45–60 שניות."])
def test_output_no_cut_wording_is_recognized_but_preview_is_never_approved_or_applied(instruction):
    # Output cut policy is now recognized; mechanical mapping still cannot
    # promote an experimental preview to editorial approval or apply authority.
    data,request,b,result,engine=control(instruction=instruction)
    assert result["instruction_contract"]["selection_controls"]["source_continuity"]=="required"
    assert all(len(p["clip_map"])==1 for p in result["ranked_compositions"])
    report=validate(data,request,b,result,engine)
    assert report["semantic_approval"] is False and report["completed_edit"] is False


@pytest.mark.parametrize("edit",[{"brief_patch":{"instruction":"Do something different"}},
    {"source_mixer_patch":{"layout":"B"}},{"selection_variant":1}])
def test_early_validation_cannot_silently_ignore_a_simultaneous_edit_request(semantic_project,edit):
    store,settings,pid,_calls,context=semantic_project;payload=stored_control(store,settings,pid,"model_recommends_unverified")
    before=store.load(pid);raw=store.state_path(pid).read_bytes()
    with pytest.raises(StoryBudgetError) as exc:
        director.analyze_project(context(),pid,store,settings,experimental_plan_validation=payload,**edit)
    assert exc.value.diagnostic["reason"]=="mixed_validation_and_edit_request"
    assert store.load(pid)==before and store.state_path(pid).read_bytes()==raw
