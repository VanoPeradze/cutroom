"""Bounded ordered source groups; semantic controls are mocked, never quality proof."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from cutroom import intelligence as story
from cutroom.critic_evidence import review_joins, validate_review_evidence
from cutroom.instruction_contract import single_output_requested
from cutroom.story_candidates import expose_complete_asr_entries
from tests.portable_support.response_fixtures import editorial_control, false_omission_fixture

@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(story,"_call_ollama_story_pass",lambda *_a,**_k:pytest.fail("No live inference"))

def setup(language="en",no_cuts=False):
    texts=(["The experiment had a clear goal.","A different holiday story.","The experiment tested the same goal.","An unrelated shopping story.","The experiment did not support that goal.","The team changed its approach after the experiment."] if language=="en" else
           ["לניסוי הייתה מטרה ברורה.","סיפור אחר על חופשה.","הניסוי בדק את אותה מטרה.","סיפור אחר על קניות.","הניסוי לא תמך בהנחה.","הצוות שינה את הגישה אחרי הניסוי."])
    rows=[{"id":f"s{i}","start":i*12.,"end":(i+1)*12.,"text":t,"words":[{"word":t,"start":i*12.,"end":(i+1)*12.}]} for i,t in enumerate(texts)]
    request={"goal":"short","language":language,"target_duration":60.,"duration_mode":"target","instruction":("Make one video. Aim for 45–60 seconds." if language=="en" else "צור סרטון אחד. כוון ל־45–60 שניות.")}
    if no_cuts: request["instruction"]+=(" Do not cut within the source passage." if language=="en" else " אל תחתוך בתוך קטע המקור.")
    units=story.build_story_beats(rows,language,target_seconds=60.,independent_asr_entries=True)
    chapters=story.build_story_chapters(units)
    plan={"slots":[{"purpose":story.SINGLE_PASSAGE_PURPOSE,"chapter_ids":[c["id"] for c in chapters],"required_context_chapter_ids":[],"desired_seconds":60.}]}
    return rows,units,chapters,plan,request

@pytest.mark.parametrize("language",["en","he"])
def test_ordered_source_groups_are_generic_complete_rows_and_not_semantic_approval(language):
    rows,u,c,p,b=setup(language);before=copy.deepcopy((rows,u,c,p,b))
    b["source_candidate_segment_ids"]=["s0","s2","s4","s5"]
    options=story._passage_options(u,rows,c,p,b)
    option,=options["options"]
    assert option["segment_ids"]==["s0","s2","s4","s5"]
    assert option["selected_source_groups"]==[["s0"],["s2"],["s4","s5"]]
    assert option["raw_playable_seconds"]==48.
    assert option["context_across_omissions_verified"] is False
    assert option["semantic_fit_verified"] is False
    assert options["receipt"]["maximum_retained_runs"]==3
    b.pop("source_candidate_segment_ids");assert (rows,u,c,p,b)==before

@pytest.mark.parametrize("language",["en","he"])
def test_explicit_no_cuts_does_not_admit_disjoint_source_selection(language):
    rows,u,c,p,b=setup(language,True);b["source_candidate_segment_ids"]=["s0","s2","s4","s5"]
    options=story._passage_options(u,rows,c,p,b)
    assert options["options"]==[] and options["receipt"]["ordered_noncontiguous_enabled"] is False

@pytest.mark.parametrize("single,multiple",[("Make one video with related cuts.","Make two videos."),("צור סרטון אחד עם חיתוכים קשורים.","צור שני סרטונים.")])
def test_output_count_does_not_become_continuity_or_multiple_outputs(single,multiple):
    assert single_output_requested({"instruction":single})
    assert not single_output_requested({"instruction":multiple})

@pytest.mark.parametrize("text",["Do not make one video.",'"Make one video."',"Make one video if possible.","אל תיצור סרטון אחד."])
def test_qualified_negated_or_quoted_output_count_is_not_a_hard_single_output(text):
    assert not single_output_requested({"instruction":text})

@pytest.mark.parametrize("language",["en","he"])
def test_complete_asr_entry_is_not_forced_to_retain_an_earlier_fragment(language):
    texts=(["The earlier ending. Another incomplete clause,","This complete definition stands alone."] if language=="en" else ["סוף קודם. התחלה אחרת שלא נגמרה,","ההגדרה הזאת שלמה ועצמאית."])
    rows=[{"id":f"s{i}","start":i*10.,"end":(i+1)*10.,"text":t} for i,t in enumerate(texts)]
    units=story.build_story_beats(rows,language,target_seconds=60.);before=copy.deepcopy((units,rows))
    new=expose_complete_asr_entries(units,rows)
    assert [u["segment_ids"] for u in new]==[["s0"],["s1"]]
    assert new[0]["boundary_status"]=="unfinished_parent_tail"
    assert new[1]["text"]==texts[1] and new[1]["start"]==10.
    assert (units,rows)==before

def evidence(kind="join_context",refs=None,join=None,missing=None):
    return {"kind":kind,"source_segment_ids":refs or ["s0","s2"],"missing_context_segment_ids":missing or [],"join_id":join,"instruction_quote":""}

def test_join_ids_bind_actual_adjacent_selected_source_quotes():
    rows,u,c,p,b=setup();ranges=[{"start":0.,"end":12.},{"start":24.,"end":36.}]
    joins=review_joins(ranges,rows);join,=joins
    assert join["left_segment_id"]=="s0" and join["right_segment_id"]=="s2"
    assert [r["id"] for r in join["omitted_source"]]==["s1"]
    proof=validate_review_evidence([evidence(join=join["id"])],rows,["s0","s2"],joins,"")
    assert proof[0]["attribution_verified"] and not proof[0]["semantic_entailment_verified"]
    with pytest.raises(ValueError,match="does not connect"):
        validate_review_evidence([evidence(refs=["s2","s4"],join=join["id"])],rows,["s0","s2","s4"],joins,"")

def test_present_context_cannot_be_claimed_missing_or_quoted_as_another_source():
    rows,*_=setup()
    with pytest.raises(ValueError,match="attribution is false"):
        validate_review_evidence([evidence("missing_context",["s0"],missing=["s2"])],rows,["s0","s2"],[],"")
    with pytest.raises(ValueError,match="attribution is false"):
        validate_review_evidence([evidence("meaning_change",["madeup"])],rows,["s0"],[],"")

@pytest.mark.parametrize("valid",[False,True])
def test_final_invalid_evidence_is_model_error_and_valid_semantic_refusal_still_blocks(valid):
    rows,u,c,p,b=setup();b["source_candidate_segment_ids"]=["s0","s2","s4","s5"]
    option=story._passage_options(u,rows,c,p,b)["options"][0]
    reply={"verdict":"no_fit","candidate_id":option["id"],"semantic_reason":"Mock uncertain ending.","refusal_category":"semantic_rejection","cited_segment_ids":["s5"],"critic_action_decisions":[],"rejection_evidence":[evidence("incomplete_thought",["s5"])] if valid else []}
    with pytest.raises((story.StoryBudgetError,story.StoryPlanningError)) as failure:
        story._decode_fixed_passage_final(reply,option,{},[],rows)
    assert failure.value.diagnostic["reason"]==("fixed_candidate_semantic_rejection" if valid else "final_review_evidence_invalid")
    assert failure.value.diagnostic["applied_to_timeline"] is False

def test_generated_editorial_control_is_representable_without_product_source_constants():
    source,control=editorial_control()
    rows=story.enrich_segments(source["segments"],"en")
    units=story.build_story_beats(rows,"en",target_seconds=60.,independent_asr_entries=True);chapters=story.build_story_chapters(units)
    wanted=set(control["canonical_segment_ids"]);nominated=[r for r in chapters if any(wanted.intersection(u["segment_ids"]) for u in r["beats"])]
    plan={"slots":[{"purpose":story.SINGLE_PASSAGE_PURPOSE,"chapter_ids":[r["id"] for r in chapters],"required_context_chapter_ids":[],"desired_seconds":60.}]}
    request={"goal":"short","target_duration":60.,"duration_mode":"target","instruction":"Make one video. Aim for 45-60 seconds.","source_candidate_segment_ids":control["canonical_segment_ids"],"source_candidate_origin":"synthetic_editorial_control"}
    options=story._passage_options(units,rows,chapters,plan,request);option,=options["options"]
    # Raw playback retains the real within-run gaps (47.35s), rather than
    # silently compressing them to the sum of spoken rows (46.56s).
    assert option["raw_playable_seconds"]==pytest.approx(47.35)
    assert sum(row["end"]-row["start"] for row in rows if row["id"] in wanted)==pytest.approx(46.56)
    assert len(option["selected_source_groups"]) == 3
    assert sum(row["end"]-row["start"] for row in option["playback_ranges"])==pytest.approx(47.35)
    assert option["segment_ids"]==control["canonical_segment_ids"]
    assert " ".join(r["text"] for r in rows if r["id"] in option["segment_ids"])==control["full_exact_text"]
    assert option["semantic_fit_verified"] is False


def test_source_span_proof_requires_the_actual_consecutive_completion():
    from cutroom.story_spans import build_source_span_constraints
    rows=[{"id":"a","start":0.,"end":4.,"text":"An earlier sentence. This prefix,"},
          {"id":"b","start":5.,"end":9.,"text":"this completes the same thought."},
          {"id":"c","start":10.,"end":14.,"text":"A different ending."}]
    units=story.build_story_beats(rows,"en",target_seconds=60.,independent_asr_entries=True)
    first=next(u for u in units if u["segment_ids"]==["a"])
    mate=next(u for u in units if u["segment_ids"]==["b"])
    other=next(u for u in units if u["segment_ids"]==["c"])
    proof=build_source_span_constraints(units,rows,selected_beat_ids=[first["id"],mate["id"]])
    assert proof["segment_ids"]==["a","b"]
    for ids in [[first["id"]],[first["id"],other["id"]]]:
        with pytest.raises(ValueError,match="complete source text and ending"):
            build_source_span_constraints(units,rows,selected_beat_ids=ids)


def test_review_schema_owns_selected_and_omitted_reference_domains():
    from cutroom.critic_evidence import review_evidence_schema
    rows,*_=setup();schema=review_evidence_schema(rows,[],indexed=True,selected_segment_ids=["s0","s2"])
    for branch in schema["items"]["anyOf"]:
        fields=branch["properties"]
        assert fields["source_segment_ids"]["items"]["enum"]==["s0","s2"]
        assert fields["missing_context_segment_ids"]["items"]["enum"]==["s1","s3","s4","s5"]
    all_selected=review_evidence_schema(rows,[],selected_segment_ids=[r["id"] for r in rows])["items"]["anyOf"]
    for branch in all_selected:
        fields=branch["properties"]
        assert fields["missing_context_segment_ids"]["maxItems"]==0
        assert fields["kind"]["const"]!="missing_context"



def test_synthetic_critic_cannot_call_retained_explanation_missing():
    data,reply=false_omission_fixture()
    rows=data["source_utterances"];selected=[r["id"] for r in rows if r["selected_in_proposal"]]
    assert {"s0015","s0016"}<=set(selected)
    assert "no adhesive" in next(r["text"] for r in rows if r["id"]=="s0015")
    assert "omits" in reply["summary"]
    with pytest.raises(ValueError,match="attribution is false"):
        validate_review_evidence(reply["issue_evidence"],rows,selected,data["actual_playback"]["joins"],data["brief"]["instruction"],issue_count=len(reply["issues"]),indexed=True)
