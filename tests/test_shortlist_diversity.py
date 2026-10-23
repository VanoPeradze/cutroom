"""Bounded retrieval diversity is not semantic approval; no live inference."""
import copy
import io
import itertools
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom import story_passage_options as passage
from cutroom.critic_evidence import validate_review_evidence
from cutroom.config import DEFAULTS, Settings
from tests.test_story_passage_options import fixture, enumerate_fixture
from tests.portable_support.response_fixtures import false_omission_fixture, transport_fixture


@pytest.fixture(autouse=True)
def no_live(monkeypatch):
    monkeypatch.setattr(story, "_call_ollama_story_pass", lambda *_a, **_k: pytest.fail("No live model"))


def ordered_values(language="en", count=12):
    values = fixture(count=count, seconds=10, target=60, language=language,
        instruction="Make one video. Aim for45-60 seconds." if language=="en" else "צור סרטון אחד. באורך45-60 שניות.")
    for unit in values[0]:
        unit["entry_policy"] = "complete-asr-entry-test"
    return values


def pair_overlap(options):
    return sum(len(set(a["beat_ids"]) & set(b["beat_ids"])) /
        len(set(a["beat_ids"]) | set(b["beat_ids"])) for a,b in itertools.combinations(options,2))


@pytest.mark.parametrize("language", ["he", "en"])
def test_ranked_pool_keeps_source_diversity_without_changing_evidence_or_constraints(language, monkeypatch):
    values = ordered_values(language)
    before = copy.deepcopy(values)
    result, _ = enumerate_fixture(values)
    # Counterfactual same numeric pool under the previous lexical-only shortlist.
    monkeypatch.setattr(passage, "_diverse_shortlist", lambda ranked, *_:
        [item[1] for item in sorted(ranked, key=lambda item:item[0], reverse=True)])
    legacy, _ = enumerate_fixture(values)
    options = result["options"]
    assert len(options) == passage.MAX_RANKED_OPTIONS
    assert pair_overlap(options) < pair_overlap(legacy["options"])
    assert values == before
    for option in options:
        assert option["segment_ids"] == [row["id"] for row in values[1] if row["id"] in option["segment_ids"]]
        assert 45 <= option["raw_playable_seconds"] <= 60
        assert not option["semantic_fit_verified"] and not option["context_across_omissions_verified"]
        assert option["frame_validation_required"] and not option["selection_forced"]
    assert len({o["id"] for o in options})==len(options)
    assert not result["receipt"]["all_numeric_options_presented"]


@pytest.mark.parametrize("alphabet", ["en", "he", "symbols"])
def test_near_duplicate_distractors_cannot_fill_all_diversity_slots(alphabet):
    # High-ranked small membership variations around a single source interior.
    ids=[f"{alphabet}{i}" for i in range(20)]
    ranked=[]
    for i,combination in enumerate(itertools.islice(itertools.combinations(ids[1:10],6),64)):
        option={"id":f"copy{i}","beat_ids":[ids[0],*combination,ids[10]]}
        ranked.append(((100.-i,0,0,option["id"]),option))
    alternative={"id":"other-envelope","beat_ids":ids[11:]}
    # No privileged ID, source word or manual candidate is read by the ranker.
    result=passage._diverse_shortlist(ranked,{(ids[11],ids[-1]):[((0.,0,0,"other-envelope"),alternative)]},ids)
    assert alternative in result and len(result)==64
    assert result[:32]==[item[1] for item in ranked[:32]]


@pytest.mark.parametrize("language", ["he", "en"])
def test_no_cuts_stays_consecutive_and_does_not_use_diversity_reservoir(language):
    values=ordered_values(language,8)
    values[-1]["instruction"] += (" Do not cut within the source passage." if language=="en" else " אל תחתוך בתוך קטע המקור.")
    result,_=enumerate_fixture(values)
    assert not result["receipt"]["ordered_noncontiguous_enabled"]
    assert result["receipt"]["shortlist_policy"] is None
    for option in result["options"]:
        assert len(option["playback_ranges"])==1
        assert len(option["selected_source_groups"])==1


@pytest.mark.parametrize("language", ["he", "en"])
def test_topic_partition_and_required_context_filter_before_shortlisting(language):
    units,rows,_,plan,brief=ordered_values(language)
    chapters=[{"id":"context","beats":units[:3]}, {"id":"topic","beats":units[3:9]}, {"id":"unrelated","beats":units[9:]}]
    plan["slots"][0].update(chapter_ids=["topic"],required_context_chapter_ids=["context"])
    result,_=enumerate_fixture((units,rows,chapters,plan,brief),candidates=units[:9])
    assert result["options"]
    for option in result["options"]:
        assert option["chapter_ids"]==["context","topic"]
        assert not set(option["segment_ids"]) & {row["id"] for row in rows[9:]}
        assert option["segment_ids"][-1] in {row["id"] for row in rows[3:9]}
        assert not option["semantic_fit_verified"]  # Shared words never certify topic coherence.


def test_maximum_supported_domain_work_and_reservoir_are_bounded():
    values=ordered_values(count=20)
    started=time.monotonic()
    result,_=enumerate_fixture(values)
    policy=result["receipt"]["shortlist_policy"]
    assert result["receipt"]["visited_windows"]==60459
    assert len(result["options"])==64
    assert policy["envelope_count"]<=210
    assert policy["retained_numeric_pool_count"]<=210*4+64
    assert time.monotonic()-started<20  # No inference/render; bounded enumeration, not a performance claim.


@pytest.mark.parametrize("language", ["he", "en"])
def test_cancellation_and_stable_order_remain_deterministic(language):
    values=ordered_values(language)
    count=0
    def cancel():
        nonlocal count
        count+=1
        if count==12: raise InterruptedError("Owned test cancellation")
    with pytest.raises(InterruptedError):enumerate_fixture(values,cancel=cancel)
    first,_=enumerate_fixture(values);second,_=enumerate_fixture(values)
    assert first==second


@pytest.mark.parametrize("language", ["he", "en"])
def test_fixed_critic_prompt_and_schema_agree_on_all_return_fields(language, monkeypatch):
    values=ordered_values(language,6)
    units,rows,chapters,plan,brief=values
    option=enumerate_fixture(values)[0]["options"][0]
    seen=[]
    def model(_settings,payload,*_):
        seen.append(payload)
        return {"verdict":"pass","add_beat_ids":[],"remove_beat_ids":[],"issues":[],"summary":"Mock review only", "style_notes":[],"action_evidence":[],"issue_evidence":[]}
    monkeypatch.setattr(story,"_call_ollama_story_pass",model)
    selection={"keep_beat_ids":option["beat_ids"],"passage_option_selection":{"option":option}}
    reviewed=story._critic_story_selection(SimpleNamespace(ai={}),selection,units,{},plan,brief,"fixture",segments=rows)
    system=seen[0]["messages"][0]["content"]
    declared=system.split("Return only ",1)[1].split(". verdict",1)[0].split(",")
    assert all(set(declared)==set(branch["properties"]) for branch in seen[0]["format"]["anyOf"])
    assert "add/remove/action_evidence arrays stay empty" in system
    assert "SELECTED claim" in system and "UNSELECTED prerequisite" in system
    assert all(branch["properties"]["action_evidence"]["maxItems"]==0 for branch in seen[0]["format"]["anyOf"])
    assert not reviewed.get("semantic_mapping_verified")  # Critic is not final approval.


def test_synthetic_wrong_source_citations_remain_invalid_after_prompt_repair():
    data,reply=false_omission_fixture()
    rows=data["source_utterances"];selected=[r["id"] for r in rows if r["selected_in_proposal"]]
    with pytest.raises(ValueError,match="attribution is false"):
        validate_review_evidence(reply["issue_evidence"],rows,selected,data["actual_playback"]["joins"],data["brief"]["instruction"],issue_count=len(reply["issues"]),indexed=True)


def test_source_diversity_is_not_a_semantic_filter_or_an_approval():
    values=ordered_values(count=9)
    # Same nouns in unrelated topics may increase lexical rank. The application
    # must still hand exact unchanged text to semantic review, never certify it.
    for row,unit in zip(values[1],values[0]):
        row["text"]=unit["text"]="The bank is a river bank." if row["id"]<"s004" else "The bank refused the loan."
    result,_=enumerate_fixture(values)
    assert result["options"]
    assert all(not o["semantic_fit_verified"] for o in result["options"])
    assert all(not o["context_across_omissions_verified"] for o in result["options"])


@pytest.mark.parametrize("variant,truncated", [(0,False),(1,True),(2,True),(3,False),(4,True)])
def test_five_synthetic_critic_transports_are_never_repaired_into_approval(variant,truncated,monkeypatch):
    raw=transport_fixture(truncated,variant)
    monkeypatch.setattr(story,"open_ollama",lambda *_a,**_k:io.BytesIO())
    monkeypatch.setattr(story,"_read_ollama_chat_response",lambda *_a,**_k:copy.deepcopy(raw))
    settings=Settings(copy.deepcopy(DEFAULTS),*[Path('.')]*5,'ffmpeg','ffprobe')
    payload={"model":"recorded-only","_single_attempt":True,"messages":[{"role":"user","content":"Recorded transport test"}],"options":{"num_ctx":4096,"num_predict":1500}}
    if truncated:
        with pytest.raises(story.StoryResponseLimitError):story._call_ollama_strict(settings,payload)
    else:
        result=story._call_ollama_strict(settings,payload)
        assert result==json.loads(raw["message"]["content"])
        assert result["verdict"]=="revise"  # Parsing does not validate claims or approve an edit.
