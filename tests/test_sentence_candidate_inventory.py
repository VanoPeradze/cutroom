"""Small text-only inventory prototype; no semantic or audible truth claims."""
import copy, importlib.util
from pathlib import Path
import pytest

from tests.portable_support import sentence_candidates as candidates

@pytest.fixture(params=[
    ['The model must not','omit the qualification.','A different account stays separate.','An unfinished...'],
    ['המודל אינו רשאי','להשמיט את ההסתייגות.','הסבר אחר נשאר נפרד.','משפט לא גמור...'],
],ids=['en','he'])
def source(request):
    return [{'id':f's{i+1:04d}','start':float(i*4),'end':float(i*4+3),
             'text':text,'words':[{'start':float(i*4),'end':float(i*4+3),'word':text}]}
             for i,text in enumerate(request.param)]

def test_cross_segment_sentence_retains_negation_ids_words_and_original_clock(source):
    before=copy.deepcopy(source)
    inventory=candidates.build_inventory(source,{'media_sha':'source'},source_offset=120.)
    assert inventory['coverage_complete'] and inventory['original_segment_count']==4
    unit=inventory['units'][0]
    assert unit['segment_ids']==['s0001','s0002']
    assert unit['text']==' '.join(row['text'] for row in source[:2])
    assert unit['original_start_seconds']==120. and unit['original_end_seconds']==127.
    assert unit['original_segment_word_spans']==source[:2]
    assert unit['semantic_coherence_verified'] is False and source==before

def test_punctuation_inside_asr_segment_never_authorizes_a_partial_cut():
    source=[{'id':'s1','start':0.,'end':5.,'text':'First sentence. Its necessary qualification follows.'}]
    inventory=candidates.build_inventory(source,{'media_sha':'source'})
    assert len(inventory['units'])==1 and inventory['units'][0]['duration']==5.
    assert inventory['units'][0]['internal_sentence_marks']==[{'segment_id':'s1','char_end':15,'cut_permission':False}]
    assert inventory['sub_ASR_sentence_cut_supported'] is False

def test_no_partial_sentence_or_unfinished_tail_is_a_complete_control(source):
    inventory=candidates.build_inventory(source,{'media_sha':'source'})
    with pytest.raises(ValueError,match='split'):
        candidates.choose_control(inventory,source,['s0002'])
    with pytest.raises(ValueError,match='unfinished'):
        candidates.choose_control(inventory,source,['s0004'])

def test_control_cost_is_numeric_only_and_omission_does_not_force_other_source(source):
    inventory=candidates.build_inventory(source,{'media_sha':'source'})
    control=candidates.choose_control(inventory,source,['s0001','s0002'],target=7.)
    assert control['cost']['approved_seconds']==7.
    assert control['numerically_feasible'] is True and control['semantic_fit_verified'] is False
    assert control['original_segment_ids']==['s0001','s0002']
    assert len(inventory['all_original_segment_ids'])==4

def test_source_identity_and_source_word_changes_invalidate_unit_ids(source):
    first=candidates.build_inventory(source,{'media_sha':'source'})
    assert first==candidates.build_inventory(source,{'media_sha':'source'})
    second=candidates.build_inventory(source,{'media_sha':'different'})
    assert first['units'][0]['id']!=second['units'][0]['id']
    altered=copy.deepcopy(source);altered[0]['words'][0]['end']-=.01
    assert first['source_fingerprint']!=candidates.build_inventory(altered,{'media_sha':'source'})['source_fingerprint']

def test_capacity_limit_stops_instead_of_truncating_coverage(source):
    with pytest.raises(ValueError,match='no first-N'):
        candidates.build_inventory(source,{'media_sha':'source'},maximum_segments=3)

@pytest.mark.parametrize('fault',['duplicate','reversed','overlap','unknown_parent','duplicate_parent'])
def test_invalid_identity_or_order_never_silently_repaired(source,fault):
    damaged=copy.deepcopy(source)
    if fault=='duplicate':damaged[1]['id']=damaged[0]['id']
    elif fault=='reversed':damaged.reverse()
    elif fault=='overlap':damaged[1]['start']=1.
    if 'parent' not in fault:
        with pytest.raises(ValueError):candidates.build_inventory(damaged,{'media_sha':'source'})
    else:
        inventory=candidates.build_inventory(source,{'media_sha':'source'})
        parents=[{'id':'b1','segment_ids':[row['id'] for row in source]}]
        if fault=='unknown_parent':parents[0]['segment_ids'][-1]='unknown'
        else:parents.append({'id':'b2','segment_ids':['s0001']})
        with pytest.raises(ValueError,match='ownership'):
            candidates.attach_parent_provenance(inventory,parents)

def test_parent_analysis_units_are_provenance_and_do_not_expand_playback(source):
    inventory=candidates.build_inventory(source,{'media_sha':'source'})
    attached=candidates.attach_parent_provenance(inventory,[{'id':'oversized_parent','segment_ids':[row['id'] for row in source]}])
    assert attached['units'][0]['parent_analysis_beat_ids']==['oversized_parent']
    assert attached['units'][0]['segment_ids']==['s0001','s0002']
    assert attached['units'][0]['duration']==7.
    assert attached['units'][0]['id']==inventory['units'][0]['id']


@pytest.mark.parametrize('text,instruction',[
    (['The experiment looked successful.','It did not establish the expected result.'],
     'Choose one coherent self-contained passage.'),
    (['הניסוי נראה מוצלח.','הוא לא הוכיח את התוצאה המבוקשת.'],
     'בחר קטע אחד שעומד בפני עצמו.'),
],ids=['en','he'])
def test_precision_contract_prices_the_whole_owner_not_just_a_short_quotation(text,instruction):
    import json
    from cutroom import intelligence as story
    segments=[{'id':'s1','start':0.,'end':2.,'text':text[0]},
              {'id':'s2','start':2.,'end':10.,'text':text[1]}]
    unit={'id':'whole_parent','start':0.,'end':10.,'duration':10.,
          'segment_ids':['s1','s2'],'text':' '.join(text)}
    chapters=[{'id':'c1','beats':[unit]}]
    plan={'slots':[{'purpose':'self_contained_passage','chapter_ids':['c1'],
                   'required_context_chapter_ids':[],'desired_seconds':6.}]}
    brief={'goal':'short','target_duration':6.,'duration_mode':'target','instruction':instruction}
    payload,catalog=story._precision_story_payload([unit],segments,chapters,[],{},plan,brief,'fixture','balanced',6.)
    assert 'citing ANY quotation also retains ALL ASR utterances' in payload['messages'][0]['content']
    data=json.loads(payload['messages'][1]['content'])
    assert data['candidate_beats'][0]['duration_cost']['approved_seconds']==10.
    assert data['candidate_beats'][0]['duration_cost']['minimum_safe_seconds']==10.
    quote=next(choice for choice in story._story_evidence_choice_catalog(catalog) if ':s1:' in choice)
    reply={'verdict':'fit','role_selections':{'self_contained_passage':{
        'primary_anchor_choice':quote,'additional_primary_evidence_choices':[],
        'context_evidence_choices_by_chapter':{}}},'highlight_beat_ids':[],
        'title':'Unverified claim','summary':'Unverified interpretation'}
    decoded=story._decode_precision_story_selection(reply,catalog,[unit],segments,chapters,plan,brief)
    assert decoded['keep_beat_ids']==['whole_parent'] and decoded['semantic_mapping_verified'] is False
    cost=story._story_selection_cost(decoded['keep_beat_ids'],[unit],segments,brief)
    assert cost['approved_seconds']==10. and cost['fits_target'] is False
    assert text[1] in unit['text']
