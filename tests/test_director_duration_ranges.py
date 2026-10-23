"""Synthetic Director duration regressions; no model, network or media decoding."""
from __future__ import annotations
import copy
import socket
import urllib.request
import pytest

from cutroom import ai_runtime, director, intelligence
from cutroom.instruction_contract import effective_duration_bounds
from cutroom.story_budget import StoryBudgetError
from cutroom.utils import invert_ranges, range_duration
from test_director_rebuild_cache import (
    _attach_source_proof, _install_story_editorial, _required_story_editorial, semantic_project,
)

RANGE = "Choose one coherent source passage. Aim for 45–60 seconds."
HE_RANGE = "\u05db\u05d5\u05d5\u05df \u05dc\u05be45\u201360 \u05e9\u05e0\u05d9\u05d5\u05ea."

def brief(instruction=RANGE, *, mode="target", target=60):
    return {"goal":"short","instruction":instruction,"duration_mode":mode,"target_duration":target}

def policy(request, duration=180):
    return {"duration_mode":request["duration_mode"],"duration_bounds":effective_duration_bounds(request,duration)}

@pytest.fixture(autouse=True)
def no_model_or_network(monkeypatch):
    def forbidden(*_args,**_kwargs):
        pytest.fail("Synthetic duration tests may not run models or network transports")
    monkeypatch.setattr(intelligence,"open_ollama",forbidden)
    monkeypatch.setattr(ai_runtime,"open_ollama",forbidden)
    monkeypatch.setattr(urllib.request,"urlopen",forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden)
    monkeypatch.setattr(director,"cuda_available",lambda *_a,**_k:False)

@pytest.mark.parametrize("instruction",[RANGE,HE_RANGE])
def test_range_review_accepts_48_seconds_without_rewriting_request(instruction):
    request=brief(instruction)
    before=copy.deepcopy(request)
    result=director._duration_review(request,180,48)
    assert result["minimum_target_seconds"]==45
    assert result["maximum_target_seconds"]==60
    assert result["shortfall"] is False
    assert result["target_feasibility"]["status"]=="met"
    assert request==before

@pytest.mark.parametrize("instruction,mode,source,selected,minimum,shortfall",[
    ("","target",180,48,54,True),
    ("Make it 60 seconds.","target",180,59,60,True),
    ("","max",180,12,0,None),
    (RANGE,"target",40,40,45,True),
])
def test_review_preserves_exact_default_maximum_and_source_shortage(
    instruction,mode,source,selected,minimum,shortfall,
):
    result=director._duration_review(brief(instruction,mode=mode),source,selected)
    assert result["minimum_target_seconds"]==minimum
    if shortfall is not None:
        assert result["shortfall"] is shortfall
    else:
        assert "selected_material_under_target" not in result["target_feasibility"]["reasons"]
    if instruction==RANGE and source<45:
        assert "source_shorter_than_requested" in result["target_feasibility"]["reasons"]

def test_maximum_still_intersects_explicit_range_ceiling():
    result=director._duration_review(brief(mode="max",target=50),180,52)
    assert result["minimum_target_seconds"]==45
    assert result["maximum_target_seconds"]==50
    assert result["exceeds_target"] is True

def test_explicit_range_cleanup_uses_45_floor_without_changing_plain_target_floor():
    story_cuts=[{"start":60,"end":120}]
    candidates=[{"start":50,"end":60,"reason":"silence","priority":2},
                {"start":40,"end":50,"reason":"silence","priority":1}]
    default,_=director._short_cleanup_cuts_with_floor(story_cuts,candidates,[],120,60)
    ranged,counts=director._short_cleanup_cuts_with_floor(
        story_cuts,candidates,[],120,60,duration_bounds=effective_duration_bounds(brief(),120))
    assert range_duration(invert_ranges(default,120))==60
    assert range_duration(invert_ranges(ranged,120))==50
    assert counts=={"silence":1}

def guarded(editorial, request, *, keeps=None, fps=30):
    return director._validate_required_story_selection(
        editorial["decision"],editorial["segments"],180,60,selection_policy=policy(request),
        keep_ranges=keeps,hierarchy=editorial["story_hierarchy"],fps=fps,
        source_segments=editorial["segments"])

def test_authoritative_policy_range_is_used_instead_of_planner_returned_bounds():
    editorial=_required_story_editorial([("complete",0,48)])
    editorial["decision"]["duration_bounds"]={"minimum_seconds":0,"maximum_seconds":1000}
    editorial["decision"]["story_requirements"]["duration_bounds"]={"minimum_seconds":999,"maximum_seconds":1000}
    checked=guarded(editorial,brief(),keeps=[{"start":0,"end":48}])
    assert checked["minimum_target_seconds"]==45
    assert checked["duration_bounds"]["origin"]=="explicit_user_range"
    assert checked["reasons"]==[]

@pytest.mark.parametrize("instruction,seconds,reason",[
    (RANGE,44.9,"allowed_source_below_target_minimum"),
    ("Make it 60 seconds.",48,"allowed_source_below_target_minimum"),
    (RANGE,60.1,"insufficient_safe_pause_budget"),
])
def test_required_guard_retains_explicit_lower_exact_and_upper_limits(instruction,seconds,reason):
    editorial=_required_story_editorial([("complete",0,seconds)])
    editorial["decision"]["duration_bounds"]={"minimum_seconds":0,"maximum_seconds":1000}
    with pytest.raises(StoryBudgetError) as failure:
        guarded(editorial,brief(instruction),keeps=[{"start":0,"end":seconds}])
    assert reason in failure.value.diagnostic["reasons"]
    assert failure.value.diagnostic["applied_to_timeline"] is False

def pause_editorial():
    editorial=_required_story_editorial([("complete",0,48)])
    words=[{"word":text,"start":start,"end":end} for text,start,end in
           [("A",0,1),("complete",10,11),("synthetic",20,21),("source",30,31),("sentence.",47,48)]]
    editorial["segments"][0]["words"]=words
    editorial["story_beats"][0]["words"]=copy.deepcopy(words)
    return _attach_source_proof(editorial)

@pytest.mark.parametrize("right_start,blocked",[(25.04,False),(25.05,True),(28,True)])
def test_final_guard_checks_raw_and_frame_minimum_after_only_verified_pause_removal(right_start,blocked):
    editorial=pause_editorial()
    keeps=[{"start":0,"end":22},{"start":right_start,"end":48}]
    if not blocked:
        assert guarded(editorial,brief(),keeps=keeps)["reasons"]==[]
        return
    with pytest.raises(StoryBudgetError) as failure:
        guarded(editorial,brief(),keeps=keeps)
    reasons=failure.value.diagnostic["reasons"]
    assert "frame_grid_under_target" in reasons
    assert "required_story_material_omitted" not in reasons
    assert "invalid_story_evidence" not in reasons
    if right_start==25.05:
        assert "selected_material_under_target" not in reasons

@pytest.mark.parametrize("target,mode,upper",[(60,"target",60),(50,"max",50)])
def test_actual_brief_bounds_reach_selection_and_every_guard_without_changing_ui(
    semantic_project,monkeypatch,target,mode,upper,
):
    store,settings,project_id,_calls,context=semantic_project
    editorial=_required_story_editorial([("complete",0,48)])
    editorial["decision"]["duration_bounds"]={"minimum_seconds":0,"maximum_seconds":1000}
    _install_story_editorial(monkeypatch,store,project_id,editorial,"ollama_hierarchical_story")
    observed=[]
    original_guard=director._validate_required_story_selection
    def check(*args,**kwargs):
        observed.append(copy.deepcopy(kwargs["selection_policy"]["duration_bounds"]))
        return original_guard(*args,**kwargs)
    original_select=director._select_short_story_ranges
    def select(*args,**kwargs):
        assert args[3]==upper
        assert kwargs["selection_policy"]["duration_bounds"]["minimum_seconds"]==45
        return original_select(*args,**kwargs)
    monkeypatch.setattr(director,"_validate_required_story_selection",check)
    monkeypatch.setattr(director,"_select_short_story_ranges",select)
    monkeypatch.setattr(director,"_build_reel_candidates",lambda *_a,**_k:[])
    result=director.analyze_project(context(),project_id,store,settings,brief(mode=mode,target=target))
    saved=store.load(project_id)
    assert len(observed)>=3 and all(row["minimum_seconds"]==45 and row["maximum_seconds"]==upper for row in observed)
    assert saved["settings"]["target_duration"]==target
    assert saved["settings"]["instruction"]==RANGE
    assert saved["draft"]["output_duration"]==48
    assert saved["draft"]["generative_approved"] is True
    assert result["draft"]["duration_review"]["shortfall"] is False

def test_under_range_refusal_preserves_saved_draft_settings_manual_and_exports(semantic_project,monkeypatch):
    store,settings,project_id,_calls,context=semantic_project
    editorial=pause_editorial()
    _install_story_editorial(monkeypatch,store,project_id,editorial,"ollama_hierarchical_story")
    monkeypatch.setattr(director,"_select_short_story_ranges",
                        lambda *_a,**_k:[{"start":0,"end":22},{"start":28,"end":48}])
    before=copy.deepcopy(store.load(project_id))
    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(),project_id,store,settings,brief())
    assert "selected_material_under_target" in failure.value.diagnostic["reasons"]
    after=store.load(project_id)
    assert {key:after[key] for key in ("draft","settings","manual","exports")}=={
        key:before[key] for key in ("draft","settings","manual","exports")}

