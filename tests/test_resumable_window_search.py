"""Bounded numeric discovery, never proof of a good edit; all calls offline."""
import copy
from dataclasses import replace
import json
from types import SimpleNamespace
import pytest

from cutroom import intelligence as story, director, ai_runtime
from cutroom.edit_windows import EditWindowError, build_canonical_source
from cutroom.story_budget import StoryBudgetError
from cutroom.window_search import (SearchStore,SearchBudget,ResumableSearchRequest,discover_page,MAX_CHECKPOINT_BYTES)
from cutroom.window_semantics import WindowSemanticRequest
from tests.test_prefix_diversity import fixture,unit_source,oracle
from tests.test_speech_unit_search import request,run


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('No inference in resumable search qualification')
    for module in (story,ai_runtime):monkeypatch.setattr(module,'open_ollama',forbidden)
    for name in ('_call_ollama_story_pass','_ollama_chat','hierarchical_story_edit','story_ai_status'):
        monkeypatch.setattr(story,name,forbidden)


def setup(tmp_path,rows=None,**budget):
    rows=fixture() if rows is None else rows
    req=request(rows);source,units=unit_source(rows)
    cursor=ResumableSearchRequest(SearchStore(tmp_path),budget=SearchBudget(**budget))
    return rows,req,source,units,cursor


def collect(source,units,policy,cursor,bounds,**kw):
    pages=[];found=[]
    for _ in range(4097):
        page=discover_page(source,bounds,policy,cursor,['fixture'],units=units,**kw)
        pages.append(page);found.extend(tuple(tuple(p) for p in c['ranges']) for c in page['candidates'])
        if page['indexed_domain_exhausted'] or page['budget_exhausted']:break
        cursor=replace(cursor,revision=page['revision'],ack_page=page['page_id'])
    else:pytest.fail('Unbounded paging')
    return found,pages


@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('durations',[(1.,1.,1.,1.),(2.,3.,4.,2.,3.),(1.,4.,2.,5.,1.,3.),(2.,2.,2.,2.,2.,2.),
    (1.,2.,1.,2.,1.,2.,1.,2.)])
def test_pages_equal_exhaustive_oracle_and_keep_immutable_source(tmp_path,language,durations):
    rows,req,source,units,cursor=setup(tmp_path,fixture(durations,language),batch_expansions=7,page_candidates=3)
    before=copy.deepcopy(rows);bounds={'minimum_seconds':5.,'maximum_seconds':9.}
    expected,_,_=oracle(source,units,5.,9.,req.policy)
    found,pages=collect(source,units,req.policy,cursor,bounds)
    assert set(found)==expected and len(found)==len(set(found))
    assert pages[-1]['indexed_domain_exhausted'] and rows==before
    assert all(p['batch_expansions']<=7 and len(p['candidates'])<=3 for p in pages)
    assert (tmp_path/(cursor.run_id+'.json')).stat().st_size<=MAX_CHECKPOINT_BYTES


@pytest.mark.parametrize('split',[1,7,64])
def test_durable_resumption_equals_uninterrupted_under_same_total_edges(tmp_path,split):
    rows,req,source,units,cursor=setup(tmp_path/'split',fixture((1.,2.,1.,2.,1.,2.,1.,2.)),
        batch_expansions=split,total_expansions=75)
    bounds={'minimum_seconds':3.,'maximum_seconds':8.}
    a,pages=collect(source,units,req.policy,cursor,bounds)
    other=ResumableSearchRequest(SearchStore(tmp_path/'whole'),budget=SearchBudget(batch_expansions=256,total_expansions=75))
    b,whole=collect(source,units,req.policy,other,bounds)
    assert a==b and pages[-1]['total_expansions']==whole[-1]['total_expansions']==75
    assert pages[-1]['search_status']=='total_budget_exhausted_incomplete'
    # Reopen in a new store object; repeated page and old revisions cannot rewind.
    replay=replace(cursor,store=SearchStore(tmp_path/'split'),revision=pages[-2]['revision'] if len(pages)>1 else 0,
        ack_page=pages[-2]['page_id'] if len(pages)>1 else None)
    assert discover_page(source,bounds,req.policy,replay,['fixture'],units=units)==pages[-1]
    if len(pages)>1:
        with pytest.raises(EditWindowError,match='revision'):
            discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)


def test_cancel_commits_work_and_pending_candidates_before_raising(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.};count=0
    # Preparation cancellation is outside a search transaction; inject only
    # after inflight exists to exercise a partially consumed numeric batch.
    def cancel():
        nonlocal count
        file=tmp_path/(cursor.run_id+'.json')
        if file.exists() and '"inflight":true' in file.read_text('utf8'):
            count+=1
            if count==8:raise InterruptedError('stop')
    with pytest.raises(InterruptedError):discover_page(source,bounds,req.policy,cursor,['fixture'],cancel,units=units)
    pending=discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    assert pending['total_expansions']==7 and pending['search_status']=='cancelled'
    next_cursor=replace(cursor,revision=pending['revision'],ack_page=pending['page_id'])
    found,tail=collect(source,units,req.policy,next_cursor,bounds)
    all_found=[tuple(tuple(p) for p in c['ranges']) for c in pending['candidates']]+found
    expected,_,_=oracle(source,units,3.,9.,req.policy)
    assert set(all_found)==expected and len(all_found)==len(expected)


@pytest.mark.parametrize('change',['identity','source','bounds','budget','no_cuts'])
def test_stale_inputs_never_restart_run(tmp_path,change):
    rows,req,source,units,cursor=setup(tmp_path,batch_expansions=2)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    page=discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    cursor=replace(cursor,revision=page['revision'],ack_page=page['page_id'])
    identity=['fixture'];no_cuts=False
    if change=='identity':identity=['different instruction/project/evidence']
    if change=='source':
        changed=copy.deepcopy(rows);changed[0]['text']='Changed word.';source=build_canonical_source(changed,source.descriptor)
        units=unit_source(changed)[1]
    if change=='bounds':bounds={**bounds,'minimum_seconds':4.}
    if change=='budget':cursor=replace(cursor,budget=replace(cursor.budget,total_expansions=4000))
    if change=='no_cuts':no_cuts=True
    with pytest.raises(EditWindowError,match='Stale'):
        discover_page(source,bounds,req.policy,cursor,identity,units=units,no_cuts=no_cuts)


@pytest.mark.parametrize('damage',['tamper','truncated','oversized','duplicate','inflight','missing'])
def test_corrupt_or_uncertain_record_is_error_not_fresh_search(tmp_path,damage):
    rows,req,source,units,cursor=setup(tmp_path,batch_expansions=2)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    page=discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    path=tmp_path/(cursor.run_id+'.json')
    if damage=='tamper':
        record=json.loads(path.read_text('utf8'));record['state']['expansions']=0;path.write_text(json.dumps(record),'utf8')
    if damage=='truncated':path.write_text('{','utf8')
    if damage=='oversized':path.write_bytes(b' '*(MAX_CHECKPOINT_BYTES+1))
    if damage=='duplicate':path.write_text('{"mac":"x","mac":"y"}','utf8')
    if damage=='inflight':
        record=cursor.store.read(path);record['inflight']=True;cursor.store.write(path,record)
    if damage=='missing':path.unlink()
    with pytest.raises(EditWindowError):
        discover_page(source,bounds,req.policy,replace(cursor,revision=page['revision'],ack_page=page['page_id']),['fixture'],units=units)


def test_lock_and_exact_ack_fail_closed(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path,batch_expansions=2)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    with cursor.store.locked(cursor.run_id):
        with pytest.raises(EditWindowError,match='busy'):discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    page=discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    with pytest.raises(EditWindowError,match='ACK'):
        discover_page(source,bounds,req.policy,replace(cursor,revision=page['revision'],ack_page='0'*64),['fixture'],units=units)


def test_rejected_edges_and_cumulative_time_are_bounded(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path,total_expansions=20,batch_expansions=20)
    found,pages=collect(source,units,req.policy,cursor,{'minimum_seconds':3.,'maximum_seconds':4.})
    assert pages[-1]['total_expansions']==20 and len(found)<20
    assert pages[-1]['visited_roots']>1
    cursor=ResumableSearchRequest(SearchStore(tmp_path/'time'),budget=SearchBudget(active_seconds=.1))
    tick=0.
    def clock():
        nonlocal tick
        tick+=.02;return tick
    page=discover_page(source,{'minimum_seconds':3.,'maximum_seconds':9.},req.policy,cursor,['fixture'],units=units,clock=clock)
    assert page['budget_exhausted'] and page['total_expansions']<256


@pytest.mark.parametrize('language',['en','he'])
@pytest.mark.parametrize('no_cuts',[False,True])
def test_actual_entry_preserves_mapping_instructions_and_director_does_not_resume(tmp_path,monkeypatch,language,no_cuts):
    rows=fixture((15.,15.,15.,15.,15.,15.),language);req=request(rows)
    req=replace(req,search=ResumableSearchRequest(SearchStore(tmp_path)))
    instruction=('Make one video. Aim for 45-60 seconds.' if language=='en' else
        '\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05d0\u05d7\u05d3. \u05db\u05d5\u05d5\u05df \u05dc45-60 \u05e9\u05e0\u05d9\u05d5\u05ea.')
    if no_cuts:instruction+=(' Choose one continuous source passage without cuts.' if language=='en' else
        ' \u05d1\u05d7\u05e8 \u05e7\u05d8\u05e2 \u05de\u05e7\u05d5\u05e8 \u05d0\u05d7\u05d3 \u05e8\u05e6\u05d9\u05e3.')
    before=copy.deepcopy(rows);result,engine=run(rows,language=language,req=req,instruction=instruction)
    assert rows==before and result['selection'] is None and result['selected_evidence']==[] and 'decision' not in result
    assert result['composition']['bounds']['minimum_seconds']==45.
    assert (result['composition']['source_continuity']=='required')==no_cuts
    assert all(len(c['ranges'])==1 for c in result['candidate_index']) if no_cuts else any(len(c['ranges'])>1 for c in result['candidate_index'])
    for proposal in result['ranked_compositions']:
        assert 45<=proposal['raw_seconds']<=60 and all(c['source_start']>=120 for c in proposal['clip_map'])
    path=tmp_path/(req.search.run_id+'.json');record=path.read_bytes()
    monkeypatch.setattr(story,'plan_edit',lambda *a,**kw:pytest.fail('Director must not replay stateful discovery'))
    with pytest.raises(StoryBudgetError) as caught:
        director.validate_experimental_plan_result(SimpleNamespace(check_cancelled=lambda:None),result,engine,
            transcript_segments=rows,settings=SimpleNamespace(ai={}),brief={},request=req,read_current=lambda:req.state)
    assert 'resumable' in caught.value.diagnostic['reason'] and path.read_bytes()==record
    with pytest.raises(EditWindowError,match='semantic execution'):WindowSemanticRequest(req)


def test_default_path_still_has_no_search_state_and_cannot_raise_old_total_cap(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path)
    assert req.search is None
    with pytest.raises(EditWindowError,match='raise'):
        discover_page(source,{'minimum_seconds':3.,'maximum_seconds':9.},replace(req.policy,max_transitions=10),cursor,[],units=units)


def test_lost_record_cannot_reset_budget_via_original_initial_request(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path,batch_expansions=2)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    (tmp_path/(cursor.run_id+'.json')).unlink()
    with pytest.raises(EditWindowError,match='previously created'):
        discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)


def test_terminal_ack_cannot_extend_total_budget_or_replace_pending_page(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path,total_expansions=3)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    page=discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    assert page['budget_exhausted'] and page['total_expansions']==3
    acknowledged=replace(cursor,revision=page['revision'],ack_page=page['page_id'])
    assert discover_page(source,bounds,req.policy,acknowledged,['fixture'],units=units)==page


def test_unexpected_error_keeps_inflight_and_forbids_uncertain_retry(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path)
    def unexpected():
        path=tmp_path/(cursor.run_id+'.json')
        if path.exists():raise RuntimeError('unexpected batch failure')
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    with pytest.raises(RuntimeError):discover_page(source,bounds,req.policy,cursor,['fixture'],unexpected,units=units)
    with pytest.raises(EditWindowError,match='uncertain'):
        discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)


@pytest.mark.parametrize('language',['en','he'])
def test_actual_entry_stale_instruction_and_project_cannot_advance_search(tmp_path,language):
    rows=fixture((15.,)*6,language);req=replace(request(rows),search=ResumableSearchRequest(SearchStore(tmp_path)))
    result,_=run(rows,language=language,req=req)
    page=result['composition']['resumable_search']
    advanced=replace(req,search=replace(req.search,revision=page['revision'],ack_page=page['page_id']))
    path=tmp_path/(req.search.run_id+'.json');before=path.read_bytes()
    with pytest.raises(EditWindowError,match='Stale'):
        run(rows,language=language,req=advanced,instruction='Make exactly 60 seconds.')
    assert path.read_bytes()==before
    with pytest.raises(EditWindowError):
        run(rows,language=language,req=advanced,reader=lambda:replace(req.state,revision=req.state.revision+1))
    assert path.read_bytes()==before


def test_failed_final_commit_retains_uncertain_inflight_instead_of_reset(tmp_path,monkeypatch):
    rows,req,source,units,cursor=setup(tmp_path);original=cursor.store.write;writes=0
    def failing(path,record):
        nonlocal writes
        writes+=1
        if writes==2:raise OSError('simulated disk/replace failure')
        return original(path,record)
    monkeypatch.setattr(cursor.store,'write',failing)
    bounds={'minimum_seconds':3.,'maximum_seconds':9.}
    with pytest.raises(OSError):discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)
    monkeypatch.setattr(cursor.store,'write',original)
    with pytest.raises(EditWindowError,match='uncertain'):
        discover_page(source,bounds,req.policy,cursor,['fixture'],units=units)


def test_materialization_cancel_retains_pending_page_without_discovery_repeat(tmp_path,monkeypatch):
    from cutroom import window_composition
    rows=fixture((15.,)*6);req=replace(request(rows),search=ResumableSearchRequest(SearchStore(tmp_path)))
    original=window_composition.prepare_window_planner_preview
    monkeypatch.setattr(window_composition,'prepare_window_planner_preview',
        lambda *a,**kw:(_ for _ in ()).throw(InterruptedError('cancel materialization')))
    with pytest.raises(InterruptedError):run(rows,req=req)
    path=tmp_path/(req.search.run_id+'.json');record=req.search.store.read(path);before=path.read_bytes()
    monkeypatch.setattr(window_composition,'prepare_window_planner_preview',original)
    result,_=run(rows,req=req)
    assert result['composition']['resumable_search']['total_expansions']==record['state']['expansions']
    assert path.read_bytes()==before


def test_time_accumulates_across_ack_without_reset(tmp_path):
    rows,req,source,units,cursor=setup(tmp_path,batch_expansions=1,active_seconds=.15)
    tick=0.
    def clock():
        nonlocal tick
        tick+=.01;return tick
    _,pages=collect(source,units,req.policy,cursor,{'minimum_seconds':3.,'maximum_seconds':9.},clock=clock)
    assert len(pages)>1 and pages[-1]['budget_exhausted'] and pages[-1]['active_seconds']>=.15
    assert all(b['active_seconds']>=a['active_seconds'] for a,b in zip(pages,pages[1:]))


@pytest.mark.parametrize('budget',[{'total_expansions':4097},{'batch_expansions':257},{'page_candidates':65},
    {'active_seconds':float('nan')},{'active_seconds':11.},{'total_expansions':True}])
def test_invalid_budget_is_rejected(budget):
    with pytest.raises(EditWindowError):SearchBudget(**budget)


def test_exhausted_sampled_tables_do_not_claim_full_configured_domain(tmp_path):
    rows=fixture((15.,)*8);req=request(rows)
    windows=replace(req.policy.windows,max_source_starts=2,max_pairs=4,max_endpoints_per_start=2)
    req=replace(req,policy=replace(req.policy,windows=windows),search=ResumableSearchRequest(SearchStore(tmp_path)))
    result,_=run(rows,req=req);receipt=result['composition'];page=receipt['resumable_search']
    assert page['indexed_domain_exhausted']
    assert not page['component_index_complete'] or not page['continuous_index_complete']
    assert receipt['configured_composition_domain_exhausted'] is False
