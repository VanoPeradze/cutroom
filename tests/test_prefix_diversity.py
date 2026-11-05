"""Small exhaustive numeric oracle, not an editorial/semantic oracle."""
import copy,socket,urllib.request
from dataclasses import replace
import pytest
from cutroom import intelligence as story,ai_runtime,window_composition as composition
from cutroom.window_composition import (WindowCompositionPolicy,SourceComposition,search_compositions,
    prune_impossible_extensions,PREFIX_SAMPLING_POLICY)
from cutroom.window_retrieval import (WindowCandidate,build_speech_unit_index,sample_entry_groups,EPSILON)
from tests.test_speech_unit_search import request,run

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('No model/network in prefix tests')
    for module in (story,ai_runtime):monkeypatch.setattr(module,'open_ollama',forbidden)
    for name in ('_call_ollama_story_pass','_ollama_chat','hierarchical_story_edit','story_ai_status'):
        monkeypatch.setattr(story,name,forbidden)
    monkeypatch.setattr(socket.socket,'connect',forbidden);monkeypatch.setattr(urllib.request,'urlopen',forbidden)

def fixture(durations=(2.,3.,4.,2.,3.,2.),language='en'):
    rows=[];clock=0.
    for i,duration in enumerate(durations):
        text=('I did not change the evidence.' if language=='en' else
              '\u05dc\u05d0 \u05e9\u05d9\u05e0\u05d9\u05ea\u05d9 \u05d0\u05ea \u05d4\u05e8\u05d0\u05d9\u05d5\u05ea.')
        rows.append({'id':f's{i}','start':clock,'end':clock+duration,'text':text})
        clock+=duration+.25
    return rows

def unit_source(rows):
    req=request(rows);src=req.source
    parents=[{'id':'owner','segment_ids':[r['id'] for r in rows], 'start':rows[0]['start'],'end':rows[-1]['end']}]
    return src,build_speech_unit_index(src,parents)

def oracle(source,units,lower,upper,policy):
    """Independent enumeration, restricted to <=8 rows, no production search."""
    assert len(source.rows)<=8
    rows=source.rows
    components=[(a,b,rows[b].end-rows[a].start) for a in units.starts for b in units.exits
                if b>=a and rows[b].end-rows[a].start<=upper+EPSILON]
    output=set();prefixes={}
    def visit(ranges,total):
        if ranges:
            if lower-EPSILON<=total<=upper+EPSILON:output.add(tuple(ranges))
            if len(ranges)<policy.max_ranges:prefixes[tuple(ranges)]=total
        if len(ranges)==policy.max_ranges:return
        for a,b,duration in components:
            if total+duration>upper+EPSILON:continue
            if ranges and (a<=ranges[-1][1]+1 or rows[a].start<=rows[ranges[-1][1]].end
                    or rows[b].end-rows[ranges[0][0]].start>policy.max_source_span):continue
            visit([*ranges,(a,b)],total+duration)
    visit([],0.)
    return output,components,prefixes

def with_previous_search(monkeypatch,call):
    original=composition.sample_entry_groups
    with monkeypatch.context() as control:
        control.setattr(composition,'prune_impossible_extensions',lambda source,states,*a,**kw:states)
        def prior(*a,**kw):kw.pop('prefix_key',None);return original(*a,**kw)
        control.setattr(composition,'sample_entry_groups',prior)
        return call()

@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('durations,limits',[
    ((1.,1.,1.,1.),(2.,3.)),((2.,3.,4.,2.,3.),(5.,8.)),
    ((1.,4.,2.,5.,1.,3.),(6.,9.)),((2.,2.,2.,2.,2.,2.),(6.,6.))])
def test_nonbinding_actual_search_matches_exhaustive_oracle(language,durations,limits):
    rows=fixture(durations,language);src,units=unit_source(rows);before=copy.deepcopy(rows)
    policy=request(rows).policy;lower,upper=limits
    expected,_,_=oracle(src,units,lower,upper,policy)
    found,receipt=search_compositions(src,{'minimum_seconds':lower,'maximum_seconds':upper},policy,units=units)
    assert {c.ranges for c in found}==expected and expected
    assert receipt['component_domain_exhausted'] and receipt['continuous_domain_exhausted']
    assert receipt['beam_pruned_states']==0 and receipt['unattempted_links_in_examined_beams']==0
    assert receipt['configured_composition_domain_exhausted'] is True and rows==before

@pytest.mark.parametrize('durations',[(1.,3.,2.,4.,1.,2.),(2.,2.,2.,2.,2.,2.),(4.,1.,5.,2.,1.,3.)])
def test_extension_bounds_never_remove_a_really_extendable_prefix(durations):
    rows=fixture(durations);src,units=unit_source(rows);policy=request(rows).policy
    _,parts,prefixes=oracle(src,units,3.,10.,policy)
    components=tuple(WindowCandidate(a,b,d) for a,b,d in parts)
    states=[SourceComposition(p,d) for p,d in prefixes.items()]
    kept={s.ranges for s in prune_impossible_extensions(src,states,components,10.,180.)}
    def extends(s):
        return any(a>s.ranges[-1][1]+1 and src.rows[a].start>src.rows[s.ranges[-1][1]].end
            and src.rows[b].end-src.rows[s.ranges[0][0]].start<=180.
            and s.duration+d<=10.+EPSILON for a,b,d in parts)
    assert all(s.ranges in kept for s in states if extends(s))
    assert all(not extends(s) for s in states if s.ranges not in kept)

def test_necessary_bounds_can_keep_uncertain_prefix_not_prove_completion():
    rows=fixture((5.,5.,10.,5.,5.,4.))
    times=[(0.,5.),(10.,15.),(20.,30.),(40.,45.),(50.,55.),(60.,64.)]
    for row,(a,b) in zip(rows,times):row.update(start=a,end=b)
    src,_=unit_source(rows);state=SourceComposition(((0,0),),5.)
    components=(WindowCandidate(2,2,10.),WindowCandidate(5,5,4.))
    assert prune_impossible_extensions(src,[state],components,10.,50.)==[state]
    assert not any(state.duration+c.duration<=10. and src.rows[c.last].end<=50. for c in components)

def test_binary_search_bounds_reject_an_unordered_component_index():
    from cutroom.edit_windows import EditWindowError
    src,_=unit_source(fixture())
    with pytest.raises(EditWindowError,match='source-ordered'):
        prune_impossible_extensions(src,[SourceComposition(((0,0),),2.)],
            (WindowCandidate(4,4,3.),WindowCandidate(2,2,4.)),10.,180.)

def test_already_valid_outputs_survive_even_when_no_further_component_exists():
    rows=fixture((2.,2.,2.,2.));src,units=unit_source(rows);policy=request(rows).policy
    found,receipt=search_compositions(src,{'minimum_seconds':2.,'maximum_seconds':5.},policy,units=units)
    assert ((3,3),) in {c.ranges for c in found} and len(found)>=4
    assert receipt['impossible_extension_prefixes_pruned']>0

@pytest.mark.parametrize('reason',['no_future_entry','duration','source_span'])
def test_proven_impossible_prefix_is_actually_removed_not_merely_left_unverified(reason):
    src,_=unit_source(fixture((2.,2.,2.,2.,2.,2.)))
    if reason=='no_future_entry':
        state=SourceComposition(((4,4),),2.);parts=(WindowCandidate(4,4,2.),);upper,span=10.,180.
    elif reason=='duration':
        state=SourceComposition(((0,0),),2.);parts=(WindowCandidate(2,2,2.),);upper,span=3.,180.
    else:
        state=SourceComposition(((0,0),),2.);parts=(WindowCandidate(4,4,2.),);upper,span=10.,5.
    assert prune_impossible_extensions(src,[state],parts,upper,span)==[]

def test_full_prefix_families_receive_shares_independent_of_suffix_density():
    states=[SourceComposition(((0,1),(4,i)),float(i)) for i in range(4,104)]
    states += [SourceComposition(((0,2),(4,i)),float(i)) for i in range(4,8)]
    before=sample_entry_groups(states,8,lambda s:s.ranges[0][0])
    after=sample_entry_groups(states,8,lambda s:s.ranges[0][0],prefix_key=lambda s:s.ranges[:-1])
    assert len(after)==len(set(after))==8
    assert sum(states[i].ranges[0]==(0,2) for i in before)<4
    assert sum(states[i].ranges[0]==(0,2) for i in after)==4
    assert {states[i].ranges for i in before}-{states[i].ranges for i in after}  # Tradeoff, not monotonic recall.

@pytest.mark.parametrize('language',['he','en'])
def test_binding_caps_return_only_oracle_fits_and_honest_incompleteness(monkeypatch,language):
    rows=fixture((2.,1.,3.,2.,1.,4.,2.,3.),language);src,units=unit_source(rows)
    policy=replace(request(rows).policy,beam_size=2,successors_per_state=2,max_transitions=12)
    expected,_,_=oracle(src,units,5.,9.,policy)
    call=lambda:search_compositions(src,{'minimum_seconds':5.,'maximum_seconds':9.},policy,units=units)
    old,_=with_previous_search(monkeypatch,call);new,receipt=call()
    a,b={c.ranges for c in old},{c.ranges for c in new}
    assert a<=expected and b<=expected and b!=expected
    assert receipt['attempted_transitions']<=12 and receipt['configured_composition_domain_exhausted'] is False
    assert len(expected-b)>0 and receipt['prefix_sampling_policy']==PREFIX_SAMPLING_POLICY

@pytest.mark.parametrize('language',['he','en'])
def test_actual_entry_mapping_and_director_guards_are_preserved(language):
    rows=fixture((10.,10.,10.,10.,10.,10.),language);before=copy.deepcopy(rows)
    req=request(rows);result,_=run(rows,language=language,req=req)
    assert rows==before and result['ranked_compositions'] and result['selection'] is None and result['selected_evidence']==[]
    assert 'decision' not in result and result['editorial_status']=='not_assessed'
    assert result['composition']['prefix_sampling_policy']==PREFIX_SAMPLING_POLICY
    assert result['composition']['budget']['beam_size']==64 and result['composition']['attempted_transitions']<=4096
    for stage in result['composition']['stages']:
        assert stage['beam_prefix_families']>=stage['beam_entry_groups']
        if stage['ranges']==2:assert stage['eligible_prefix_families']==stage['eligible_entry_groups']
    for c in result['ranked_compositions']:
        assert 45<=c['raw_seconds']<=60
        ids=[r for clip in c['clip_map'] for r in clip['row_ids']];assert len(ids)==len(set(ids))
        for clip in c['clip_map']:
            positions={r['id']:r for r in rows}
            assert clip['source_start']==pytest.approx(positions[clip['row_ids'][0]]['start']+120.)

def test_raw_and_explicit_no_cuts_do_not_use_new_frontier_pruner(monkeypatch):
    def forbidden(*a,**kw):pytest.fail('New pruning must not affect raw/no-cuts')
    monkeypatch.setattr(composition,'prune_impossible_extensions',forbidden)
    raw,_=run(units=False);assert 'prefix_sampling_policy' not in raw['composition']
    continuous,_=run(instruction='Choose one continuous source passage without cuts. Aim for 45-60 seconds.')
    assert continuous['ranked_compositions'] and all(len(c['clip_map'])==1 for c in continuous['ranked_compositions'])

@pytest.mark.parametrize('where',['bounds','families'])
def test_cancellation_in_new_work_cannot_produce_a_partial_plan(where):
    rows=fixture();src,units=unit_source(rows);before=copy.deepcopy(rows)
    states=[SourceComposition(((0,0),(2,2)),6.)]*100
    def cancel():raise InterruptedError('cancel')
    with pytest.raises(InterruptedError):
        if where=='bounds':prune_impossible_extensions(src,states,(WindowCandidate(4,4,3.),),10.,180.,cancel)
        else:sample_entry_groups(states,32,lambda s:s.ranges[0][0],cancel,prefix_key=lambda s:s.ranges[:-1])
    assert rows==before
