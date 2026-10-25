"""Model source profiles are attributed retrieval advice, never semantic gates."""
import copy
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.passage_quality import validate_source_review, source_review_prior, source_review_schema
from tests.test_shortlist_diversity import ordered_values
from tests.passage_contract_fixture import nominate


def profile(units,status="clear"):
    return {r["id"]:{"status":status,"context_direction":"none","source_segment_ids":[r["segment_ids"][0]],
                     "reason":"Mock source reading, not semantic approval"} for r in units}


@pytest.mark.parametrize("language",["en","he"])
def test_uncertain_source_changes_retrieval_order_but_not_numeric_eligibility_or_source(language):
    u,rows,c,p,b=ordered_values(language,count=10)
    before=copy.deepcopy((u,rows,c,p,b))
    report=profile(u);report[u[0]["id"]]["status"]="uncertain"
    review=validate_source_review(report,u,"fixture")
    plain=story._passage_options(u,rows,c,p,b)
    aware=story._passage_options(u,rows,c,p,b,source_quality=review)
    assert aware["receipt"]["numeric_option_count"]==plain["receipt"]["numeric_option_count"]
    assert aware["options"][0]["retrieval_quality"]["source_uncertain_fraction"]==0
    assert any(u[0]["id"] in o["beat_ids"] for o in aware["options"])
    assert not review["interpretation_verified"] and all(not o["semantic_fit_verified"] for o in aware["options"])
    assert (u,rows,c,p,b)==before


@pytest.mark.parametrize("fault",["missing","foreign","direction","duplicate","status","reason"])
def test_invalid_source_profile_is_rejected_with_originals_intact(fault):
    u,*_=ordered_values(count=10);reply=profile(u);first=reply[u[0]["id"]]
    if fault=="missing":reply.pop(u[-1]["id"])
    elif fault=="foreign":first["source_segment_ids"]=[u[1]["segment_ids"][0]]
    elif fault=="direction":first["context_direction"]="previous"
    elif fault=="duplicate":first["source_segment_ids"]*=2
    elif fault=="status":first["status"]="boring"
    else:first["reason"]=""
    before=copy.deepcopy(reply)
    with pytest.raises(ValueError):validate_source_review(reply,u,"fixture")
    assert reply==before


def test_context_direction_needs_actual_adjacent_source_not_previous_eligible_item():
    u,*_=ordered_values(count=10);report=profile(u)
    report[u[2]["id"]].update(status="context",context_direction="previous")
    review=validate_source_review(report,u,"fixture")
    assert source_review_prior(review,u,[1,2],list(range(10)))[1]==0
    assert source_review_prior(review,u,[2],list(range(10)))[1]==1
    assert source_review_prior(review,u,[1,2],[0,1,5,6,7,8,9,10,11,12])[1]==1


def test_stale_profile_cannot_be_reused_after_source_word_or_time_change():
    u,rows,c,p,b=ordered_values(count=10);review=validate_source_review(profile(u),u,"fixture")
    review["source_identity"]="stale"
    with pytest.raises(story.StoryPlanningError) as exc:story._passage_options(u,rows,c,p,b,source_quality=review)
    assert exc.value.diagnostic["reason"]=="stale_source_quality_assessment"


@pytest.mark.parametrize("language",["en","he"])
def test_actual_selection_reads_source_once_then_one_isolated_candidate(language,monkeypatch):
    u,rows,c,p,b=ordered_values(language,count=10);seen=[]
    # Real Hebrew/English words in the source-reading input, independent of
    # older private fixtures. IDs, clocks and source partition stay unchanged.
    for row,unit in zip(rows,u):
        row["text"]=unit["text"]=(f"The rescue crew completed stage {row['id']} safely." if language=="en" else f"צוות החילוץ השלים את השלב {row['id']} בבטחה.")
    u=story.build_story_beats(rows,language,target_seconds=60.,independent_asr_entries=True)
    c=story.build_story_chapters(u)
    p["slots"][0]["chapter_ids"]=[chapter["id"] for chapter in c]
    def call(_settings,payload,*_):
        data=json.loads(payload["messages"][-1]["content"]);seen.append(data)
        if "source_units_for_quality" in data:
            assert len(data["source_units_for_quality"])==10
            assert "ASR" in payload["messages"][0]["content"]
            return profile(u)
        assert len(data["passage_candidates"])==1
        return nominate(data["passage_candidates"][0],data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",call)
    selection,_=story._select_passage_option(SimpleNamespace(ai={"source_quality_assessment":True}),u,rows,c,p,b,"fixture",None)
    assert len(seen)==2
    receipt=selection["passage_option_selection"]["enumeration"]
    assert receipt["source_quality"]["authority"]=="retrieval_advice_only"
    assert not selection["semantic_mapping_verified"]
    # The final decoder must reconstruct the SAME profiled option, not silently
    # rerank it without the profile after a successful nomination.
    option=selection["passage_option_selection"]["option"]
    data={"brief":b,"source_units":[{**{k:r[k] for k in ("id","start","end","segment_ids")},
        "segments":[s for s in rows if s["id"] in r["segment_ids"]],"selected_in_proposal":r["id"] in option["beat_ids"]} for r in u]}
    request,rebuilt,_=story._fixed_passage_final_request({"messages":[{"role":"system","content":"fixture"},
        {"role":"user","content":json.dumps(data)}]},selection,u,rows,c,p,b,[],None)
    assert rebuilt==option and request["format"]


def test_bad_quality_response_stops_before_candidate_nomination(monkeypatch):
    u,rows,c,p,b=ordered_values(count=10);calls=[]
    def call(*args):calls.append(args);return {}
    monkeypatch.setattr(story,"_call_ollama_story_pass",call)
    with pytest.raises(story.StoryPlanningError) as exc:
        story._select_passage_option(SimpleNamespace(ai={"source_quality_assessment":True}),u,rows,c,p,b,"fixture",None)
    assert len(calls)==1 and exc.value.diagnostic["reason"]=="invalid_source_quality_assessment"


def test_unqualified_source_reader_is_not_enabled_by_default(monkeypatch):
    u,rows,c,p,b=ordered_values(count=10);calls=[]
    def model(_settings,payload,*_):
        data=json.loads(payload["messages"][-1]["content"]);calls.append(data)
        assert "source_units_for_quality" not in data
        return nominate(data["passage_candidates"][0],data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    selected,_=story._select_passage_option(SimpleNamespace(ai={}),u,rows,c,p,b,"fixture",None)
    assert len(calls)==1 and selected["passage_option_selection"]["enumeration"]["source_quality"] is None


def test_quality_schema_is_closed_per_source_unit_and_has_no_mixed_union():
    u,*_=ordered_values(count=10);schema=source_review_schema(u)
    assert set(schema["required"])=={r["id"] for r in u}
    for unit in u:
        row=schema["properties"][unit["id"]]
        assert set(row)=={"anyOf"}
        for branch in row["anyOf"]:
            assert branch["additionalProperties"] is False and set(branch["required"])==set(branch["properties"])
            assert branch["properties"]["source_segment_ids"]["items"]["enum"]==unit["segment_ids"]


@pytest.mark.parametrize("status",["clear","context","uncertain"])
def test_source_schema_and_validator_agree_on_status_direction_contract(status):
    from tests.test_complete_object_schemas import matches
    u,*_=ordered_values(count=10);reply=profile(u)
    row=reply[u[0]["id"]];row.update(status=status,context_direction="previous" if status=="context" else "none")
    assert matches(reply,source_review_schema(u))
    validate_source_review(reply,u,"fixture")
    row["context_direction"]="none" if status=="context" else "previous"
    assert not matches(reply,source_review_schema(u))
    with pytest.raises(ValueError):validate_source_review(reply,u,"fixture")
