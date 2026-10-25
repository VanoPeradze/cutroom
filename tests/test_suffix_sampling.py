"""Fixed-budget suffix coverage, not a source/meaning quality classifier."""
import copy,socket,urllib.request
from dataclasses import replace
import pytest
from cutroom import intelligence as story,ai_runtime,window_retrieval as retrieval,window_composition as composition
from cutroom.window_retrieval import sample_entry_groups,_stratum_centers,ENTRY_GROUP_SAMPLING
from tests.test_speech_unit_search import data,request,run

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('No model/network in suffix sampling tests')
    for module in (story,ai_runtime):monkeypatch.setattr(module,'open_ollama',forbidden)
    for name in ('_call_ollama_story_pass','_ollama_chat','hierarchical_story_edit','story_ai_status'):
        monkeypatch.setattr(story,name,forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden)

@pytest.mark.parametrize('count,maximum',[(0,0),(5,0),(0,3),(1,1),(2,1),(10,3),(11,4),(97,8),(5000,32),(8,32)])
def test_rank_strata_unique_ordered_bounded_and_interior_when_possible(count,maximum):
    picked=_stratum_centers(count,maximum);take=min(count,maximum)
    assert len(picked)==len(set(picked))==take and picked==sorted(picked)
    assert all(0<=i<count for i in picked)
    if take:
        assert all(abs((index+.5)-((ordinal+.5)*count/take))<=.5
                   for ordinal,index in enumerate(picked))
    if count>=2*maximum and maximum>1:
        assert 0 not in picked and count-1 not in picked

@pytest.mark.parametrize('count,maximum',[(6,2),(10,3),(19,4),(100,8)])
def test_interior_suffix_recall_is_a_tradeoff_not_monotonic_coverage(count,maximum):
    old=set(retrieval._spread(count,maximum));new=set(_stratum_centers(count,maximum))
    assert len(new)==len(old)==maximum and new-old and old-new
    assert 0 in old and 0 not in new  # Explicit counterexample: shortest may be useful.

def test_group_coverage_and_caps_remain_unchanged_despite_dense_distractors():
    values=[(0,i) for i in range(5000)]+[(i,0) for i in range(1,21)]
    selected=sample_entry_groups(values,64,lambda v:v[0])
    assert len(selected)==64 and len({values[i][0] for i in selected})==21
    bounded=sample_entry_groups(values,4,lambda v:v[0])
    assert len(bounded)==4 and values[bounded[0]][0]==0 and values[bounded[-1]][0]==20
    assert values==[(0,i) for i in range(5000)]+[(i,0) for i in range(1,21)]

@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('offset',[0.,137.25])
def test_actual_entry_uses_new_policy_with_exact_mapping_and_same_budget(language,offset):
    rows=data(language,gap=.8)
    for row in rows:
        row['start']+=offset;row['end']+=offset
        for word in row['words']:word['start']+=offset;word['end']+=offset
    before=copy.deepcopy(rows);req=request(rows)
    result,_=run(rows,language=language,req=req)
    assert rows==before and result['composition']['entry_sampling_policy']==ENTRY_GROUP_SAMPLING
    assert result['ranked_compositions'] and result['selection'] is None and result['selected_evidence']==[]
    assert 'decision' not in result and result['editorial_status']=='not_assessed'
    receipt=result['composition'];index=receipt['speech_units']
    assert receipt['budget']['beam_size']==64 and receipt['budget']['successors_per_state']==32
    assert receipt['budget']['max_transitions']==4096 and receipt['attempted_transitions']<=4096
    assert receipt['budget']['windows']['max_pairs']==2048
    ids={r['id']:i for i,r in enumerate(rows)}
    for proposal in result['ranked_compositions']:
        assert 45<=proposal['raw_seconds']<=60
        used=[i for clip in proposal['clip_map'] for i in clip['row_ids']]
        assert len(used)==len(set(used))
        for clip in proposal['clip_map']:
            a,b=ids[clip['row_ids'][0]],ids[clip['row_ids'][-1]]
            assert a in index['entry_rows'] and b in index['exit_rows']
            assert clip['source_start']==pytest.approx(rows[a]['start']+120)
            assert clip['source_end']==pytest.approx(rows[b]['end']+120)

@pytest.mark.parametrize('language',['he','en'])
def test_raw_control_and_explicit_no_cuts_do_not_invoke_suffix_sampling(monkeypatch,language):
    def forbidden(*a,**kw):pytest.fail('Suffix sampler must not run in raw/no-cuts paths')
    monkeypatch.setattr(composition,'sample_entry_groups',forbidden)
    raw,_=run(language=language,units=False)
    assert 'entry_sampling_policy' not in raw['composition']
    instruction=('Choose one continuous source passage without cuts. Aim for 45-60 seconds.' if language=='en'
                 else '\u05d1\u05d7\u05e8 \u05e7\u05d8\u05e2 \u05e8\u05e6\u05d9\u05e3 \u05d0\u05d7\u05d3 \u05dc\u05dc\u05d0 \u05d7\u05d9\u05ea\u05d5\u05db\u05d9\u05dd. \u05db\u05d5\u05d5\u05df \u05dc\u05be45-60 \u05e9\u05e0\u05d9\u05d5\u05ea.')
    result,_=run(language=language,instruction=instruction)
    assert result['ranked_compositions'] and all(len(p['clip_map'])==1 for p in result['ranked_compositions'])

def test_cancellation_during_group_sampling_cannot_return_partial_selection():
    values=[(i//100,i) for i in range(1000)];before=copy.deepcopy(values);calls=[0]
    def check():
        calls[0]+=1
        if calls[0]==3:raise InterruptedError('cancel')
    with pytest.raises(InterruptedError):sample_entry_groups(values,64,lambda v:v[0],check)
    assert values==before

def test_relabelled_content_and_source_ids_cannot_influence_suffix_rank_sampling():
    positions=[(g,i) for g in range(7) for i in range(20-g)]
    a=[{'entry':g,'suffix':i,'text':'unrelated topic'} for g,i in positions]
    b=[{'entry':g,'suffix':i,'text':'\u05e0\u05d5\u05e9\u05d0 \u05d0\u05d7\u05e8','source_id':f'anything-{i}'} for g,i in positions]
    assert sample_entry_groups(a,32,lambda v:v['entry'])==sample_entry_groups(b,32,lambda v:v['entry'])
