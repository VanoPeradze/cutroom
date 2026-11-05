"""Source-bound contracts; no inference/media and no editorial-quality claims."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.critic_evidence import review_evidence_schema,validate_review_evidence
from cutroom.passage_binding import (source_binding,quote_reference,presented_options,
    validate_reason_quotes,review_source_scope,NOMINATION_REASON,PASSAGE_REASON_CONTRACT)
from tests.test_ordered_source_groups import setup
from tests.test_shortlist_diversity import ordered_values
from tests.test_story_passage_options import enumerate_fixture
from tests.passage_contract_fixture import nominate


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(story,"_call_ollama_story_pass",lambda *_a,**_k:pytest.fail("No live inference"))


def selected(language,monkeypatch):
    rows,units,chapters,plan,brief=setup(language)
    seen=[]
    def model(_settings,payload,*_):
        seen.append(payload)
        data=json.loads(payload["messages"][1]["content"])
        return nominate(data["passage_candidates"][0],data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    selection,candidates=story._select_passage_option(SimpleNamespace(ai={}),units,rows,chapters,plan,brief,"fixture",None)
    return rows,candidates,chapters,plan,brief,selection,seen[0]


@pytest.mark.parametrize("language",["he","en"])
def test_actual_nomination_binds_canonical_quotes_not_free_interpretation(language,monkeypatch):
    rows,units,chapters,plan,brief,selection,payload=selected(language,monkeypatch)
    binding=selection["passage_option_selection"]
    proof=binding["rationale_proof"]
    assert proof["attribution_verified"] and not proof["interpretation_verified"]
    assert binding["source_binding"]==source_binding(binding["option"],rows)
    assert binding["model_reason"]==NOMINATION_REASON
    assert not selection["semantic_mapping_verified"]
    data=json.loads(payload["messages"][1]["content"])
    for option in data["passage_candidates"]:
        assert option["source_text"]==" ".join(r["text"] for r in rows if r["id"] in option["segment_ids"])
    assert proof["source_quotes"][0]["quote"] in binding["source_binding"]["selected_text"]


@pytest.mark.parametrize("language",["he","en"])
def test_foreign_candidate_reason_reference_is_rejected(language,monkeypatch):
    rows,units,c,p,b,selection,_=selected(language,monkeypatch)
    option=selection["passage_option_selection"]["option"]
    foreign=next(r for r in rows if r["id"] not in option["segment_ids"])
    with pytest.raises(ValueError,match="another candidate"):
        validate_reason_quotes([quote_reference(foreign)],option,rows,[foreign["id"]])
    with pytest.raises(ValueError,match="another candidate"):
        validate_reason_quotes([{"segment_id":option["segment_ids"][0],"quote":foreign["text"]}],option,rows,[foreign["id"]])


@pytest.mark.parametrize("mutation",["word","time","identity","membership"])
def test_changed_candidate_is_blocked_before_critic_inference(mutation,monkeypatch):
    rows,u,c,p,b,selection,_=selected("en",monkeypatch)
    identifier=selection["passage_option_selection"]["option"]["segment_ids"][0]
    row=next(r for r in rows if r["id"]==identifier)
    if mutation=="word":row["text"]+=" Invented."
    elif mutation=="time":row["start"]+=.001
    elif mutation=="identity":selection["passage_option_selection"]["candidate_id"]="other"
    else:selection["keep_beat_ids"]=selection["keep_beat_ids"][:-1]
    monkeypatch.setattr(story,"_call_ollama_story_pass",lambda *_a:pytest.fail("Binding failure precedes model"))
    with pytest.raises(story.StoryPlanningError) as exc:
        story._critic_story_selection(SimpleNamespace(ai={}),selection,u,{},p,b,"fixture",segments=rows)
    assert exc.value.diagnostic["reason"]=="critic_candidate_binding_invalid"


@pytest.mark.parametrize("language",["he","en"])
@pytest.mark.parametrize("kind",["missing_context","meaning_change","explicit_instruction"])
def test_instruction_evidence_discriminator_matches_validator(language,kind):
    rows,*_=setup(language)
    instruction="Keep the full conclusion. Do not invert the negation." if language=="en" else "שמור את המסקנה המלאה. אל תהפוך את השלילה."
    row={"kind":kind,"source_segment_ids":["s0"],"missing_context_segment_ids":["s1"] if kind=="missing_context" else [],"join_id":None,
        "instruction_quote":instruction if kind=="explicit_instruction" else ""}
    schema=review_evidence_schema(rows,[],selected_segment_ids=["s0"],instruction=instruction)["items"]
    variant=next(v["properties"] for v in schema["anyOf"] if v["properties"]["kind"]["const"]==kind)
    assert variant["instruction_quote"]["const"]==row["instruction_quote"]
    proof=validate_review_evidence([row],rows,["s0"],[],instruction)
    assert proof[0]["attribution_verified"] and not proof[0]["semantic_entailment_verified"]
    bad=copy.deepcopy(row);bad["instruction_quote"]=rows[0]["text"]
    with pytest.raises(ValueError,match="instruction evidence"):
        validate_review_evidence([bad],rows,["s0"],[],instruction)
    if kind=="explicit_instruction":
        bad["instruction_quote"]=instruction.split(".")[0]
        with pytest.raises(ValueError):validate_review_evidence([bad],rows,["s0"],[],instruction)


@pytest.mark.parametrize("count",[1,2])
def test_critic_issue_indices_are_derived_from_order_not_model_output(count,monkeypatch):
    rows,u,c,p,b,s,_=selected("en",monkeypatch)
    option=s["passage_option_selection"]["option"]
    captured=[]
    def model(_settings,payload,*_):
        captured.append(payload)
        return {"verdict":"revise","add_beat_ids":[],"remove_beat_ids":[],"issues":["Mock source uncertainty"]*count,
            "summary":"Unverified source wording","style_notes":[],"action_evidence":[],"issue_evidence":[
            {"kind":"source_text_uncertainty","source_segment_ids":[option["segment_ids"][0]],"missing_context_segment_ids":[],"join_id":None,"instruction_quote":""} for _ in range(count)]}
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    result=story._critic_story_selection(SimpleNamespace(ai={}),s,u,{},p,b,"fixture",segments=rows)
    assert [r["issue_index"] for r in result["critic"]["issue_evidence"]]==list(range(count))
    assert all("issue_index" not in row["properties"] for branch in captured[0]["format"]["anyOf"] for row in branch["properties"]["issue_evidence"]["items"]["anyOf"])
    cardinality=next(v["properties"] for v in captured[0]["format"]["anyOf"] if v["properties"]["issues"].get("minItems")==count)
    assert cardinality["issue_evidence"]["minItems"]==count
    assert cardinality["issue_evidence"]["maxItems"]==count
    assert cardinality["issue_evidence"]["type"]=="array"


@pytest.mark.parametrize("bad",["empty_refusal","actions","model_index","missing_record"])
def test_malformed_fixed_critic_stays_model_error(bad,monkeypatch):
    rows,u,c,p,b,s,_=selected("en",monkeypatch)
    identifier=s["passage_option_selection"]["option"]["segment_ids"][0]
    reply={"verdict":"revise","add_beat_ids":[],"remove_beat_ids":[],"issues":["Mock issue"],"summary":"Mock","style_notes":[],"action_evidence":[],
        "issue_evidence":[{"kind":"incomplete_thought","source_segment_ids":[identifier],"missing_context_segment_ids":[],"join_id":None,"instruction_quote":""}]}
    if bad=="empty_refusal":reply["issues"]=[];reply["issue_evidence"]=[]
    elif bad=="actions":reply["remove_beat_ids"]=[s["keep_beat_ids"][0]]
    elif bad=="model_index":reply["issue_evidence"][0]["issue_index"]=1
    else:reply["issue_evidence"]=[]
    monkeypatch.setattr(story,"_call_ollama_story_pass",lambda *_a:copy.deepcopy(reply))
    with pytest.raises(story.StoryPlanningError) as exc:story._critic_story_selection(SimpleNamespace(ai={}),s,u,{},p,b,"fixture",segments=rows)
    assert exc.value.diagnostic["outcome"]=="invalid_model_output"


def test_quote_reference_output_stays_bounded_even_for_long_whole_asr_row(monkeypatch):
    rows,u,c,p,b,s,_=selected("en",monkeypatch)
    option=s["passage_option_selection"]["option"]
    row=next(r for r in rows if r["id"] in option["segment_ids"])
    row["text"]="Complete source text. "*2000
    reference=quote_reference(row)
    proof=validate_reason_quotes([reference],option,rows,[row["id"]])
    assert len(reference)<40 and proof["source_quotes"][0]["quote"]==row["text"]
    assert len(json.dumps([reference]))<50  # No model copy of thousands of words.


def test_bounded_comparison_keeps_intact_context_and_reports_omitted_choices():
    values=ordered_values(count=12)
    options=enumerate_fixture(values)[0]["options"]
    short=presented_options(options,[u["id"] for u in values[0]])
    assert len(short)==8 and len({o["id"] for o in short})==8
    intact=[o for o in options if len(o["selected_source_groups"])==1][:4]
    assert all(o in short for o in intact)
    assert all(o in options for o in short)
    assert any(len(o["selected_source_groups"])>1 for o in short)


def test_review_scope_does_not_reintroduce_full_long_source(monkeypatch):
    rows,u,c,p,b,s,_=selected("en",monkeypatch)
    extra=[{"id":f"extra{i}","start":1000+i*10.,"end":1009+i*10.,"text":"Unrelated distant chapter. "*20} for i in range(500)]
    combined=rows+extra
    assert review_source_scope(u,combined)==rows
    seen=[]
    def model(_settings,payload,*_):
        seen.append(payload)
        return {"verdict":"pass","add_beat_ids":[],"remove_beat_ids":[],"issues":[],"summary":"Mock only","style_notes":[],"action_evidence":[],"issue_evidence":[]}
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    story._critic_story_selection(SimpleNamespace(ai={}),s,u,{"premise":"Unverified global narrative"},p,b,"fixture",segments=combined)
    data=json.loads(seen[0]["messages"][1]["content"])
    assert "outline" not in data and "plan" not in data and "source_evidence" not in data
    assert not any(r["id"].startswith("extra") for r in data["reference_source_utterances"])
    assert len(seen[0]["messages"][1]["content"])<20000


def test_final_review_and_missing_context_schema_share_the_bounded_reference_scope():
    rows,u,chapters,plan,brief=setup("en")
    extra=[{"id":f"distant{i}","start":1000+i*10.,"end":1009+i*10.,"text":"Different chapter. "*20} for i in range(500)]
    distant_units=[{"id":"u"+r["id"],"start":r["start"],"end":r["end"],"text":r["text"],"segment_ids":[r["id"]]} for r in extra]
    chapters=[*chapters,{"id":"far","beats":distant_units}]
    all_rows=rows+extra
    option=story._passage_options(u,all_rows,chapters,plan,brief)["options"][0]
    selection={"keep_beat_ids":option["beat_ids"],"passage_option_selection":{"candidate_id":option["id"],"option":option,"source_binding":source_binding(option,all_rows)}}
    data={"brief":brief,"source_units":[{**{k:r[k] for k in ("id","start","end","segment_ids")},
        "segments":[v for v in rows if v["id"] in r["segment_ids"]],"selected_in_proposal":r["id"] in option["beat_ids"]} for r in u]}
    payload={"messages":[{"role":"system","content":"fixture"},{"role":"user","content":json.dumps(data)}]}
    request,_,_=story._fixed_passage_final_request(payload,selection,u,all_rows,chapters,plan,brief,[],None)
    actual=json.loads(request["messages"][1]["content"])
    assert "source_evidence" not in actual
    assert not any(r["id"].startswith("distant") for r in actual["reference_source_utterances"])
    for branch in request["format"]["anyOf"]:
        for evidence in branch["properties"]["rejection_evidence"]["items"]["anyOf"]:
            omitted=evidence["properties"]["missing_context_segment_ids"]
            assert not any(v.startswith("distant") for v in omitted.get("items",{}).get("enum",[]))
    assert len(request["messages"][1]["content"])<20000


def recorded():
    with pytest.MonkeyPatch.context() as patch:
        rows,_units,_chapters,_plan,_brief,selection,payload=selected("en",patch)
    option=selection["passage_option_selection"]["option"]
    foreign=[r["id"] for r in rows if r["id"] not in option["segment_ids"]]
    assert foreign
    nomination={"verdict":"fit","candidate_id":option["id"],"semantic_reason":"Foreign source: "+"/".join(foreign),"refusal_category":"none","cited_segment_ids":[],"reason_evidence":[]}
    first=option["segment_ids"][0]
    reply={"verdict":"no_fit","candidate_id":option["id"],"semantic_reason":"Synthetic independent rejection.","refusal_category":"semantic_rejection","cited_segment_ids":[first],"critic_action_decisions":[],"rejection_evidence":[{"kind":"missing_context","source_segment_ids":[first],"missing_context_segment_ids":[foreign[0]],"join_id":None,"instruction_quote":next(r["text"] for r in rows if r["id"]==first)}]}
    objects={"04_precision_RESPONSE.json":nomination,"06_final_RESPONSE.json":reply}
    return lambda name:copy.deepcopy(objects[name]),rows,option


def test_synthetic_cross_candidate_prose_cannot_be_nomination_rationale(monkeypatch):
    read,rows,option=recorded()
    reply=read("04_precision_RESPONSE.json")
    foreign={r["id"] for r in rows if r["id"] not in option["segment_ids"]}
    assert foreign and all(identifier in reply["semantic_reason"] for identifier in foreign)
    # Replay as a current typed response: the old unsupported prose is rejected,
    # even if a well-formed selected quote is attached to it. No source altered.
    reply["reason_evidence"]=[quote_reference(next(r for r in rows if r["id"] in option["segment_ids"]))]
    reply["cited_segment_ids"]=[]
    with pytest.raises(story.StoryPlanningError) as exc:
        story._decode_passage_option_choice(reply,{"options":[option],"receipt":{"scope":"recorded single candidate","rationale_contract":PASSAGE_REASON_CONTRACT}},[],rows,[],{}, {})
    assert exc.value.diagnostic["reason"]=="invalid_passage_rationale"


@pytest.mark.parametrize("change",["original_wrong_quote","missing_record","correct_missing_context","correct_full_instruction"])
def test_synthetic_final_rejection_does_not_turn_into_acceptance(change):
    read,rows,option=recorded();reply=read("06_final_RESPONSE.json")
    if change=="missing_record":reply["rejection_evidence"]=[]
    elif change=="correct_missing_context":reply["rejection_evidence"][0]["instruction_quote"]=""
    elif change=="correct_full_instruction":
        reply["rejection_evidence"][0].update(kind="explicit_instruction",missing_context_segment_ids=[],instruction_quote=option["verbatim_instruction"])
    with pytest.raises(story.StoryPlanningError) as exc:story._decode_fixed_passage_final(reply,option,{},[],rows)
    assert exc.value.diagnostic["reason"]==("fixed_candidate_semantic_rejection" if change.startswith("correct") else "final_review_evidence_invalid")
    assert not exc.value.diagnostic["applied_to_timeline"] and not exc.value.diagnostic["source_wide_no_fit_proven"]
