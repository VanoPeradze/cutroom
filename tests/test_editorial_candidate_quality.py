"""Retrieval priors are advisory; isolated assessments still require final review."""
import copy
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.passage_quality import SourcePhraseIndex, MAX_INDEXED_WORDS_PER_UNIT
from cutroom.passage_binding import MAX_PASSAGE_ASSESSMENTS
from cutroom.passage_binding import assessment_options
from cutroom.story_passage_options import _keep_diverse_envelope
from tests.test_ordered_source_groups import setup
from tests.passage_contract_fixture import nominate, refuse


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(story, "_call_ollama_story_pass", lambda *_a, **_k: pytest.fail("No live inference"))


@pytest.mark.parametrize("language", ["en", "he"])
def test_long_repeated_source_phrases_are_measured_without_source_changes(language):
    phrase = "The mountain rescue team returned before sunset" if language=="en" else "צוות החילוץ מההר חזר בשלום לפני שקיעת השמש"
    units = [{"id":"a","text":phrase+"."}, {"id":"b","text":phrase+". " + ("Everyone was safe." if language=="en" else "כולם היו בטוחים.")}]
    before=copy.deepcopy(units);index=SourcePhraseIndex(units)
    assert index.measure([0])["duplicate_fraction"]==0
    assert index.measure([0,1])["duplicate_fraction"]>0
    assert index.measure([0,1])["semantic_quality_verified"] is False
    renamed=[{**row,"id":"other"+row["id"]} for row in units]
    assert SourcePhraseIndex(renamed).measure([0,1])==index.measure([0,1])
    assert units==before


@pytest.mark.parametrize("texts", [
    ["The river bank flooded after heavy rain.", "The bank approved a loan for equipment."],
    ["הצוות התכונן לתחרות וסיים את האימון בשלום.", "הצוות חזר הביתה אחרי יום עבודה ארוך."],
    ["Do not enter the tunnel before sunrise.", "Enter the tunnel only after sunrise."],
])
def test_common_words_and_different_claims_are_not_classified_as_same_long_phrase(texts):
    result=SourcePhraseIndex([{"text":t} for t in texts]).measure([0,1])
    assert result["duplicate_phrase_windows"]==0
    assert not result["semantic_quality_verified"]  # Lexical novelty is not coherence.


def test_no_repetition_is_invented_across_edit_joins_and_long_units_are_not_truncated():
    index=SourcePhraseIndex([{"text":t} for t in ["one two three", "four five six", "one two three", "four five six"]])
    assert index.measure([0,1,2,3])["duplicate_phrase_windows"]==0
    original="word "*(MAX_INDEXED_WORDS_PER_UNIT+1)
    row={"text":original};index=SourcePhraseIndex([row])
    assert index.measure([0])["unavailable_units"]==1 and row["text"]==original


@pytest.mark.parametrize("alphabet", ["en", "he", "symbols"])
def test_same_envelope_keeps_different_interiors_instead_of_only_ranked_near_clones(alphabet):
    ids=[f"{alphabet}{i}" for i in range(20)];positions={v:i for i,v in enumerate(ids)}
    reservoir=[]
    for i in range(8):
        option={"id":f"near{i}","beat_ids":[ids[0],*ids[1:9],ids[10+i],ids[-1]]}
        _keep_diverse_envelope(reservoir,((100.-i,),option),positions,4)
    alternative={"id":"different-interior","beat_ids":[ids[0],*ids[11:18],ids[-1]]}
    _keep_diverse_envelope(reservoir,((0.,),alternative),positions,4)
    assert alternative in [row[1] for row in reservoir] and len(reservoir)==4
    assert reservoir[0][1]["id"]=="near0"


def test_three_assessments_do_not_spend_the_budget_on_the_first_three_near_clones():
    ids=[f"u{i}" for i in range(16)]
    values=[{"id":f"near{i}","beat_ids":[*ids[:8],ids[8+i]]} for i in range(4)]
    different={"id":"different","beat_ids":ids[9:]};values.append(different)
    result=assessment_options(values,ids)
    assert len(result)==3 and result[0]==values[0] and different in result


def values(language):
    rows,units,chapters,plan,brief=setup("en")
    texts=(["The rescue team reached the ridge before dawn.", "The first radio signal did not reach base camp.",
            "A second attempt used a higher antenna.", "The new signal reached the village safely.",
            "The rescue team reached the ridge before dawn.", "Everyone returned home and the search ended."] if language=="en" else
           ["צוות החילוץ הגיע לרכס לפני עלות השחר.", "הודעת הרדיו הראשונה לא הגיעה למחנה הבסיס.",
            "בניסיון השני השתמשו באנטנה גבוהה יותר.", "ההודעה החדשה הגיעה לכפר בבטחה.",
            "צוות החילוץ הגיע לרכס לפני עלות השחר.", "כולם חזרו הביתה והחיפוש הסתיים."])
    for row in rows:
        row["text"]=texts[int(row["id"][1:])];row["words"]=[{"word":row["text"],"start":row["start"],"end":row["end"]}]
    units=story.build_story_beats(rows,language,target_seconds=60.,independent_asr_entries=True)
    chapters=story.build_story_chapters(units)
    plan["slots"][0]["chapter_ids"]=[c["id"] for c in chapters]
    brief.update(language=language,instruction="Make one video. Aim for 45-60 seconds." if language=="en" else "צור סרטון אחד באורך 45–60 שניות.")
    return rows,units,chapters,plan,brief


@pytest.mark.parametrize("language", ["en", "he"])
def test_actual_retrieval_prioritizes_fewer_exact_restarts_without_duration_padding(language):
    rows,u,c,p,b=values(language);before=copy.deepcopy((rows,u,c,p,b))
    result=story._passage_options(u,rows,c,p,b)
    assert result["options"][0]["retrieval_quality"]["duplicate_fraction"]==0
    assert any(o["retrieval_quality"]["duplicate_fraction"]>0 for o in result["options"])
    assert result["receipt"]["shortlist_policy"]["duration_preference_within_band"] is None
    for option in result["options"]:
        assert 45<=option["raw_playable_seconds"]<=60
        assert option["segment_ids"]==[r["id"] for r in rows if r["id"] in option["segment_ids"]]
        assert not option["semantic_fit_verified"]
    assert (rows,u,c,p,b)==before


def refusal(category="semantic_rejection"):
    return {"verdict":"no_fit","candidate_id":None,"semantic_reason":"Fixture independent context cannot be established",
            "refusal_category":category,"cited_segment_ids":[],"reason_evidence":[]}


@pytest.mark.parametrize("language", ["en", "he"])
def test_candidate_specific_refusal_can_advance_without_cross_candidate_text(language,monkeypatch):
    rows,u,c,p,b=values(language);before=copy.deepcopy(rows);calls=[]
    def model(_settings,payload,*_):
        data=json.loads(payload["messages"][-1]["content"]);calls.append(data)
        assert len(data["passage_candidates"])==1
        option=data["passage_candidates"][0]
        assert {r["id"] for r in data["source_utterances"]}==set(option["segment_ids"])
        assert data["brief"]["instruction"]==b["instruction"]
        if len(calls)==1:return refuse(option,data)
        return nominate(option,data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    result,_=story._select_passage_option(SimpleNamespace(ai={}),u,rows,c,p,b,"fixture",None)
    assert len(calls)==2 and rows==before
    assert calls[0]["passage_candidates"][0]["id"]!=calls[1]["passage_candidates"][0]["id"]
    receipt=result["passage_option_selection"]["enumeration"]
    assert [r["outcome"] for r in receipt["candidate_assessments"]]==["editorial_no_fit","provisional_nomination"]
    assert not result["semantic_mapping_verified"]


@pytest.mark.parametrize("language", ["en", "he"])
def test_finite_refusals_leave_remaining_source_unreviewed(language,monkeypatch):
    rows,u,c,p,b=values(language);calls=[]
    def model(_settings,payload,*args):
        calls.append(payload)
        data=json.loads(payload['messages'][-1]['content'])
        return refuse(data['passage_candidates'][0],data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    with pytest.raises(story.StoryPlanningError) as exc:
        story._select_passage_option(SimpleNamespace(ai={}),u,rows,c,p,b,"fixture",None)
    assert len(calls)==MAX_PASSAGE_ASSESSMENTS
    assert not exc.value.diagnostic["source_wide_no_fit_proven"] and not exc.value.diagnostic["applied_to_timeline"]
    receipt=exc.value.diagnostic["passage_options"]
    assert len(receipt["candidate_assessments"])==3 and receipt["unreviewed_retrieved_option_count"]>0


@pytest.mark.parametrize("fault", ["uncertain", "temporal_uncertainty", "malformed", "foreign_quote", "ungrounded_refusal"])
def test_uncertainty_and_invalid_contracts_stop_without_search_retries(fault,monkeypatch):
    rows,u,c,p,b=values("en");calls=[]
    def model(_settings,payload,*_):
        data=json.loads(payload["messages"][-1]["content"]);calls.append(data)
        if fault in {"uncertain","temporal_uncertainty"}:return refusal(fault)
        if fault=="ungrounded_refusal":return refusal()
        if fault=="malformed":return {"candidate_id":data["passage_candidates"][0]["id"]}
        reply=nominate(data["passage_candidates"][0],data);reply["reason_evidence"]=["quote_foreign"];return reply
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    with pytest.raises(story.StoryPlanningError) as exc:
        story._select_passage_option(SimpleNamespace(ai={}),u,rows,c,p,b,"fixture",None)
    assert len(calls)==1 and exc.value.diagnostic["outcome"] in {"technical_error","invalid_model_output"}


def test_repetition_can_be_explicitly_wanted_and_is_never_automatically_deleted(monkeypatch):
    rows,u,c,p,b=values("en");b["instruction"]+=" Preserve the repeated refrain exactly."
    # The source control is a test of retention, never a production preference.
    repeated=next(o for o in story._passage_options(u,rows,c,p,b)["options"] if o["retrieval_quality"]["duplicate_fraction"]>0)
    b["source_candidate_segment_ids"]=repeated["segment_ids"]
    def model(_settings,payload,*_):
        data=json.loads(payload["messages"][-1]["content"])
        assert data["passage_candidates"][0]["segment_ids"]==repeated["segment_ids"]
        return nominate(data["passage_candidates"][0],data)
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    selected,_=story._select_passage_option(SimpleNamespace(ai={}),u,rows,c,p,b,"fixture",None)
    assert selected["passage_option_selection"]["option"]["segment_ids"]==repeated["segment_ids"]


@pytest.mark.parametrize("language", ["en", "he"])
def test_no_cuts_and_explicit_source_constraints_remain_hard(language):
    rows,u,c,p,b=values(language)
    b["instruction"]+=(" Do not cut within the source passage." if language=="en" else " אל תחתוך בתוך קטע המקור.")
    result=story._passage_options(u,rows,c,p,b)
    assert not result["receipt"]["ordered_noncontiguous_enabled"]
    assert all(len(o["playback_ranges"])==1 for o in result["options"])
