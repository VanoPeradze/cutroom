"""Exact diagnostic mapping preserves source identity and explicit constraints."""
import copy,importlib.util,sys
from pathlib import Path
import pytest

from tests.portable_support import sentence_candidates as candidates, sentence_edit_mapping as mapping

@pytest.fixture
def source():
    rows=[{'id':f's{i+1}','start':float(i*5),'end':float(i*5+4),
           'text':text} for i,text in enumerate(['The trial happened.','It did not prove success.','That limit still matters.'])]
    return rows,candidates.build_inventory(rows,{'media_sha':'original'})

@pytest.mark.parametrize('instruction',['Make one video.','צור סרטון אחד.'])
def test_one_output_can_keep_related_source_cuts_without_expanding_to_parent(source,instruction):
    segments,inventory=source;ids=[inventory['units'][i]['id'] for i in (0,2)]
    before=copy.deepcopy((segments,inventory))
    result=mapping.build_edit_mapping(inventory,segments,ids,{'instruction':instruction,'target_duration':8.,'duration_mode':'target'})
    assert result['canonical_segment_ids']==['s1','s3'] and result['timeline_frames']==240
    assert result['timeline_seconds']==8. and result['explicit_continuity'] is False
    assert [(row['source_start_seconds'],row['source_end_seconds']) for row in result['mapping']]==[(0.,4.),(10.,14.)]
    assert result['mapping'][1]['original_start_seconds']==130.
    assert result['float_retention_validated'] and result['frame_snapped_retention_validated']
    assert result['semantic_approved'] is False and (segments,inventory)==before

def test_explicit_no_cut_request_checks_full_inventory_not_only_nominated_units(source):
    segments,inventory=source;ids=[inventory['units'][i]['id'] for i in (0,2)]
    with pytest.raises(ValueError,match='continuity'):
        mapping.build_edit_mapping(inventory,segments,ids,{'target_duration':8.,
            'instruction':'Keep the source passage continuous without internal cuts.'})

def test_explicit_continuity_keeps_intervening_time_and_reports_duration_conflict(source):
    segments,inventory=source;ids=[row['id'] for row in inventory['units'][:2]]
    brief={'target_duration':9.,'instruction':'Keep the source passage continuous without internal cuts.'}
    result=mapping.build_edit_mapping(inventory,segments,ids,brief)
    assert result['fitted_ranges']==[{'start':0.,'end':9.}]
    assert result['explicit_continuity'] and result['timeline_frames']==270
    with pytest.raises(ValueError,match='cannot fit'):
        mapping.build_edit_mapping(inventory,segments,ids,{**brief,'target_duration':8.})

def test_protected_speech_is_not_arbitrarily_trimmed_to_meet_target(source):
    segments,inventory=source;ids=[inventory['units'][i]['id'] for i in (0,2)]
    with pytest.raises(ValueError,match='cannot fit'):
        mapping.build_edit_mapping(inventory,segments,ids,{'target_duration':7.})

def test_stale_word_or_timestamp_identity_blocks_mapping(source):
    segments,inventory=source;altered=copy.deepcopy(segments);altered[0]['end']-=.01
    with pytest.raises(ValueError,match='Stale'):
        mapping.build_edit_mapping(inventory,altered,[inventory['units'][0]['id']],{'target_duration':4.})

def test_nearest_frame_rounding_is_exposed_when_it_loses_float_retention_edges():
    segments=[{'id':'s1','start':5.16,'end':10.64,'text':'The whole source remains required.'}]
    inventory=candidates.build_inventory(segments,{'media_sha':'original'})
    result=mapping.build_edit_mapping(inventory,segments,[inventory['units'][0]['id']],{'target_duration':5.48})
    assert result['mapping'][0]['source_start_frame']==155
    assert result['mapping'][0]['source_end_frame']==319
    assert result['float_retention_validated'] is True
    assert result['frame_snapped_retention_validated'] is False
    assert result['frame_snapping_limit']
    assert result['rendered'] is result['semantic_approved'] is False

@pytest.mark.parametrize('fault',['duplicate','reverse','unknown'])
def test_invalid_source_ids_or_order_are_not_repaired(source,fault):
    segments,inventory=source;ids=[row['id'] for row in inventory['units'][:2]]
    if fault=='duplicate':ids=[ids[0],ids[0]]
    elif fault=='reverse':ids.reverse()
    else:ids=['unknown']
    with pytest.raises(ValueError):mapping.build_edit_mapping(inventory,segments,ids,{'target_duration':8.})
