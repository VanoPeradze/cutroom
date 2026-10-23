"""Actual-entry source-unit retrieval/composition; proxies are not meaning."""
from __future__ import annotations
import copy,json,socket,urllib.request
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import pytest

from cutroom import intelligence as story,ai_runtime,director
from cutroom.window_retrieval import (WindowRetrievalPolicy,WindowRetrievalRequest,build_speech_unit_index,
    retrieve_windows,sample_entry_groups)
from cutroom.window_composition import WindowCompositionRequest,WindowCompositionPolicy
from cutroom.edit_windows import EditWindowError,SourceDescriptor,build_canonical_source
from cutroom.window_evidence import WindowSourceState
from cutroom.story_budget import StoryBudgetError
from tests.test_window_evidence_planner import brief
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


@pytest.fixture(autouse=True)
def no_inference_or_network(monkeypatch):
    def forbidden(*a,**kw):pytest.fail("Speech-unit milestone cannot call model/network")
    for module in (story,ai_runtime):monkeypatch.setattr(module,"open_ollama",forbidden)
    for name in ("_call_ollama_story_pass","_ollama_chat","story_ai_status"):monkeypatch.setattr(story,name,forbidden)
    monkeypatch.setattr(socket,"create_connection",forbidden);monkeypatch.setattr(urllib.request,"urlopen",forbidden)


def data(language="en",*,punctuated=True,gap=0.):
    texts=(["We tested a simple", "idea and kept the evidence.","A separate example begins here.",
            "The result was not", "what we expected.","We changed the method after that.","An unfinished ending..."] if language=="en" else
           ["בדקנו רעיון", "פשוט ושמרנו את הראיות.","כאן מתחילה דוגמה אחרת.",
            "התוצאה לא הייתה", "מה שציפינו.","שינינו את השיטה בעקבות זאת.","סיום לא גמור..."])
    if not punctuated:texts=[t.rstrip(".…") for t in texts]
    return [{"id":f"s{i}","start":float(i*(10+gap)),"end":float(i*(10+gap)+10),"text":t,
             "words":[{"word":t,"start":float(i*(10+gap)),"end":float(i*(10+gap)+10),"probability":.9}]} for i,t in enumerate(texts)]


def request(rows,*,mode="composition",units=True,policy=None):
    desc=SourceDescriptor("primary:A","g","t",1000.,120.)
    src=build_canonical_source(rows,desc);state=WindowSourceState("project_0123456789ab",3,desc)
    if mode=="retrieval":return WindowRetrievalRequest(src,state,policy or WindowRetrievalPolicy(speech_units=units))
    p=policy or WindowCompositionPolicy();p=replace(p,windows=replace(p.windows,speech_units=units))
    return WindowCompositionRequest(src,state,p)


def run(rows=None,*,language="en",mode="composition",units=True,instruction=None,req=None,reader=None,cancel=None):
    rows=data(language) if rows is None else rows;req=req or request(rows,mode=mode,units=units)
    return story.plan_edit(rows,SimpleNamespace(ai={}),brief(language,instruction),source_window_request=req,
        source_window_state=reader or (lambda:req.state),cancel_check=cancel)


@pytest.mark.parametrize("language",["he","en"])
@pytest.mark.parametrize("mode",["retrieval","composition"])
def test_actual_entry_uses_source_unit_boundaries_preserving_exact_canonical_source(language,mode):
    rows=data(language);before=copy.deepcopy(rows)
    new,engine=run(rows,language=language,mode=mode)
    old,_=run(rows,language=language,mode=mode,units=False)
    receipt=new["composition" if mode=="composition" else "retrieval"];index=receipt["speech_units"]
    assert index["canonical_rows_represented"]==len(rows) and index["unknown_terminal_tail"] is True
    assert new["canonical_evidence"]==old["canonical_evidence"] and new["canonical_ownership"]==old["canonical_ownership"]
    assert new["source_fingerprint"]==old["source_fingerprint"] and rows==before
    assert new["selection"] is None and new["selected_evidence"]==[] and "decision" not in new
    assert index["semantic_truth_verified"] is False
    views={v["window_id"]:v for v in new["views"]};pos={r["id"]:i for i,r in enumerate(rows)}
    for v in views.values():
        assert pos[v["row_ids"][0]] in index["entry_rows"] and pos[v["row_ids"][-1]] in index["exit_rows"]
        assert all(t["text"]==rows[pos[t["segment_id"]]]["text"] for t in v["exact_text_by_row"])
    assert views
    if mode=="composition":
        assert new["ranked_compositions"] and receipt["attempted_transitions"]<=4096
        assert all(p["speech_unit_boundary_refs"] for p in new["ranked_compositions"])
        assert any("לא" in r["text"] if language=="he" else "not" in r["text"] for r in rows)


@pytest.mark.parametrize("language",["en","he"])
def test_without_punctuation_recorded_timing_and_speaker_hints_still_provide_units(language):
    rows=data(language,punctuated=False,gap=.8)
    rows[3]["speaker"]="person-two";rows[2]["speaker"]="person-one"
    result,_=run(rows,language=language)
    index=result["composition"]["speech_units"]
    hints=[hint for row in index["boundary_hints"] for hint in row["hints"]]
    assert "ASR_interval_gap_unverified" in hints and "recorded_speaker_change_unverified" in hints
    assert "existing_terminal_punctuation_unverified" not in hints
    assert result["ranked_compositions"] and index["semantic_truth_verified"] is False


def test_unpunctuated_without_boundary_evidence_stays_represented_not_global_no_fit():
    rows=data(punctuated=False);result,_=run(rows)
    index=result["composition"]["speech_units"]
    assert index["canonical_rows_represented"]==len(rows) and index["exit_rows"]==[]
    assert result["ranked_compositions"]==[] and result["composition"]["all_legal_edits_exhausted"] is False
    assert result["composition"]["status"]=="no_numeric_fit_in_configured_search_only"


def test_false_or_asr_punctuation_is_not_promoted_to_verified_sentence_or_editorial_truth():
    rows=data();rows[1]["text"]="Incorrect punctuation can end here."
    result,_=run(rows);index=result["composition"]["speech_units"]
    assert index["punctuation_is_a_hint_only"] is True and index["semantic_truth_verified"] is False
    assert result["editorial_status"]=="not_assessed" and "decision" not in result


@pytest.mark.parametrize("language",["en","he"])
def test_arbitrary_analysis_parent_boundaries_do_not_create_utterance_entries(language):
    from cutroom.story_candidates import project_short_source_units
    rows=data(language)[:3]
    parents=[{"id":f"parent{i}","segment_ids":[r["id"]],"start":r["start"],"end":r["end"]}
             for i,r in enumerate(rows)]
    source=request(rows).source
    unexposed=project_short_source_units(parents,rows)
    index=build_speech_unit_index(source,unexposed)
    assert 1 not in index.starts  # Previous row is unfinished, even at an owner boundary.
    assert index.starts==(0,2) and index.units==((0,1),(2,2))
    assert dict(index.boundary_hints)[1]==("existing_terminal_punctuation_unverified",)


def test_entry_recovery_hint_belongs_to_suffix_not_prefix_and_is_reused_once():
    from cutroom.story_candidates import project_short_source_units,expose_complete_asr_entries
    rows=data()[:3]
    rows[0]["text"]="An unfinished introduction"
    rows[1]["text"]="The earlier point ends. Then another unfinished"
    rows[2]["text"]="A complete new sentence starts here."
    parents=[{"id":"p0","segment_ids":["s0"],"start":0.,"end":10.},
             {"id":"p1","segment_ids":["s1","s2"],"start":10.,"end":30.}]
    source=request(rows).source;projected=project_short_source_units(parents,rows)
    exposed=expose_complete_asr_entries(projected,rows)
    index=build_speech_unit_index(source,projected)
    assert index==build_speech_unit_index(source,exposed)
    assert index.starts==(0,2) and index.exits==(2,)
    assert 0 not in dict(index.boundary_hints)
    assert dict(index.boundary_hints)[1]==("existing_entry_recovery_reference_only",)
    assert index.units==((0,1),(2,2))


def test_inconsistent_direct_helper_unit_policy_cannot_silently_change_sampling():
    from cutroom.window_composition import search_compositions
    rows=data();req=request(rows);parents=story.build_story_beats(rows,"en",target_seconds=60.)
    index=build_speech_unit_index(req.source,parents)
    with pytest.raises(EditWindowError,match="explicit speech-unit policy"):
        search_compositions(req.source,{"minimum_seconds":45.,"maximum_seconds":60.},WindowCompositionPolicy(),units=index)


def test_fixed_budget_entry_sampling_resists_a_dense_distractor_group_without_hardcoded_content():
    values=[("dense",i) for i in range(5000)]+[(f"other-{i:02}",0) for i in range(20)]
    chosen=sample_entry_groups(values,64,lambda v:v[0])
    assert len(chosen)==len(set(chosen))==64 and len({values[i][0] for i in chosen})==21
    tiny=sample_entry_groups(values,4,lambda v:v[0]);assert len(tiny)==4 and len({values[i][0] for i in tiny})==4
    assert sample_entry_groups([],64,lambda v:v)==[]


@pytest.mark.parametrize("instruction,no_cuts",[
    ("Make one video. Aim for 45-60 seconds.",False),
    ("צור סרטון אחד. כוון ל־45–60 שניות.",False),
    ("Choose one continuous source passage without cuts. Aim for 45-60 seconds.",True),
    ("בחר קטע רציף אחד ללא חיתוכים. כוון ל־45–60 שניות.",True)])
def test_one_output_does_not_imply_no_cuts_and_explicit_no_cuts_keeps_continuous_units(instruction,no_cuts):
    result,_=run(instruction=instruction)
    assert result["ranked_compositions"]
    assert (all(len(p["clip_map"])==1 for p in result["ranked_compositions"]) if no_cuts else
            any(len(p["clip_map"])>1 for p in result["ranked_compositions"]))
    for p in result["ranked_compositions"]:assert 45<=p["raw_seconds"]<=60


@pytest.mark.parametrize("instruction",["Make exactly 60 seconds.","צור סרטון באורך בדיוק 60 שניות."])
def test_exact_duration_is_not_filled_by_padding_repetition_or_unsafe_tail(instruction):
    result,_=run(instruction=instruction)
    assert result["ranked_compositions"]  # Positive exact-duration fixture, not vacuous all().
    assert all(p["raw_seconds"]==60 for p in result["ranked_compositions"])
    for p in result["ranked_compositions"]:
        ids=[i for c in p["clip_map"] for i in c["row_ids"]];assert len(ids)==len(set(ids)) and "s6" not in ids


def test_current_source_and_cache_identity_bind_unit_cues_without_rewriting_rows():
    rows=data();req=request(rows);a,_=run(rows,req=req);raw,_=run(rows,units=False)
    assert a["cache_key"]!=raw["cache_key"]
    changed=copy.deepcopy(rows);changed[2]["speaker"]="a";changed[3]["speaker"]="b"
    with pytest.raises(EditWindowError,match="full canonical"):run(changed,req=req)
    new,_=run(changed);assert new["cache_key"]!=a["cache_key"] and new["source_fingerprint"]!=a["source_fingerprint"]


@pytest.mark.parametrize("stage",["index","sampling","after"])
def test_cancellation_preserves_immutable_source_and_never_returns_a_plan(monkeypatch,stage):
    from cutroom import window_retrieval as retrieval,window_composition as composition
    rows=data();req=request(rows);before=copy.deepcopy(rows);stop=[False]
    def check():
        if stop[0]:raise InterruptedError("cancelled")
    if stage=="index":
        original=composition.build_speech_unit_index
        def index(*a,**kw):stop[0]=True;return original(*a,**kw)
        monkeypatch.setattr(composition,"build_speech_unit_index",index)
    elif stage=="sampling":
        original=composition.sample_entry_groups
        def sample(*a,**kw):stop[0]=True;return original(*a,**kw)
        monkeypatch.setattr(composition,"sample_entry_groups",sample)
    reads=[0]
    def reader():
        reads[0]+=1
        if stage=="after" and reads[0]>=5:stop[0]=True
        return req.state
    with pytest.raises(InterruptedError):run(rows,req=req,reader=reader,cancel=check)
    assert rows==before


def test_stale_revision_and_unit_index_from_another_source_are_rejected():
    rows=data();req=request(rows)
    with pytest.raises(EditWindowError,match="changed during"):
        run(rows,req=req,reader=lambda:replace(req.state,revision=4))
    with pytest.raises(EditWindowError,match="source-derived"):
        retrieve_windows(req.source,{"minimum_seconds":0.,"maximum_seconds":60.},req.policy.windows)


@pytest.mark.parametrize("language",["he","en"])
def test_director_rederives_unit_path_and_remains_fail_closed(language):
    rows=data(language);req=request(rows);result,engine=run(rows,language=language,req=req);before=copy.deepcopy(result)
    with pytest.raises(StoryBudgetError) as exc:
        director.validate_experimental_plan_result(SimpleNamespace(check_cancelled=lambda:None),result,engine,
            transcript_segments=rows,settings=SimpleNamespace(ai={}),brief=brief(language),request=req,read_current=lambda:req.state)
    report=exc.value.diagnostic
    assert report["mechanical_mapping_validated"] is True and report["semantic_approval"] is False and report["applied_to_timeline"] is False
    assert result==before


def test_default_and_resource_caps_are_unchanged_and_mode_has_no_nominated_ids():
    assert WindowRetrievalPolicy().speech_units is False
    p=WindowCompositionPolicy();assert (p.beam_size,p.successors_per_state,p.max_transitions,p.shortlist_size)==(64,32,4096,8)
    assert (p.windows.max_source_starts,p.windows.max_pairs,p.windows.max_endpoints_per_start)==(128,2048,16)
    with pytest.raises(EditWindowError):WindowRetrievalPolicy(speech_units="yes")
    assert set(WindowCompositionRequest.__dataclass_fields__)=={"source","state","policy","search"}
    assert request(data()).search is None  # run reference only; default path unchanged


def test_portable_broken_asr_join_and_tail_are_absent_from_automatic_pool():
    rows=source_fixture()["segments"]
    # The source search never receives these diagnostic ranges.
    result,_=run(rows);old,_=run(rows,units=False)
    formerly_broken=((33,33),(35,43))
    ranges=lambda r:{tuple(tuple(v) for v in c["ranges"]) for c in r["candidate_index"]}
    assert formerly_broken in ranges(old) and formerly_broken not in ranges(result)
    assert all(all(b!=43 for a,b in c["ranges"]) for c in result["candidate_index"])
    assert result["canonical_evidence"]==old["canonical_evidence"]
