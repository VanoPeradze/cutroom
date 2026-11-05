"""Diagnostic mapping through existing source locks/pause and frame policies.

This does not grant semantic approval or change renderer rounding behavior.
"""
import math
from cutroom.instruction_contract import explicit_source_continuity_requested
from cutroom.story_budget import compact_story_pauses_to_target,framed_story_duration,story_duration_cost
from cutroom.story_spans import build_source_span_constraints,validate_source_span_constraints
from .sentence_candidates import POLICY,fingerprint

def build_edit_mapping(inventory,segments,selected_ids,brief,*,fps=30,source_offset=120.):
    expected=fingerprint({'policy':POLICY,'source':inventory['source_identity'],'segments':segments})
    if inventory.get('source_fingerprint')!=expected:
        raise ValueError('Stale source inventory cannot map an edit')
    if not isinstance(selected_ids,list) or not selected_ids or len(selected_ids)!=len(set(selected_ids)):
        raise ValueError('Source-unit IDs must be unique and nonempty')
    if isinstance(fps,bool) or not isinstance(fps,(float,int)) or not math.isfinite(fps) or fps<=0:
        raise ValueError('Invalid frame grid')
    by_id={unit['id']:unit for unit in inventory['units']}
    if not set(selected_ids)<=set(by_id):raise ValueError('Unknown source-unit selection')
    units=[by_id[identifier] for identifier in selected_ids]
    if units!=sorted(units,key=lambda row:row['start']):
        raise ValueError('Source order cannot be silently changed')
    if any(unit['boundary_status']!='punctuation_at_full_asr_boundary' for unit in units):
        raise ValueError('An unfinished source tail is not an approved complete unit')
    continuity=explicit_source_continuity_requested(brief)
    if continuity:
        positions=[index for index,unit in enumerate(inventory['units']) if unit['id'] in selected_ids]
        if len(positions)!=positions[-1]-positions[0]+1:
            raise ValueError('Explicit source continuity forbids omitted intervening units')
    proof=build_source_span_constraints(units,segments,selected_beat_ids=selected_ids)
    approved=proof['approved_ranges']
    if continuity:approved=[{'start':approved[0]['start'],'end':approved[-1]['end']}]
    duration=max(row['end'] for row in segments)
    target=float(brief.get('target_duration') or 60.)
    fitted=compact_story_pauses_to_target(approved,segments,duration,target,
        protect_action_span=continuity,fps=fps)
    if fitted is None:raise ValueError('Protected source speech/explicit continuity cannot fit the duration')
    seconds=framed_story_duration(fitted,fps)
    minimum=.9*min(target,duration) if brief.get('duration_mode','target')=='target' else 0.
    if seconds+.05<minimum:raise ValueError('Selected source underfills the target; never pad it')
    validate_source_span_constraints(proof,units,segments,selected_beat_ids=selected_ids,keep_ranges=fitted)
    rows=[];cursor=0;quantized=[]
    for index,item in enumerate(fitted):
        left=math.floor(item['start']*fps+.5);right=math.floor(item['end']*fps+.5)
        if right<=left:raise ValueError('A required range has no output frame')
        active=[unit for unit in units if unit['start']<item['end'] and unit['end']>item['start']]
        ids=[identifier for unit in active for identifier in unit['segment_ids']
             if any(row['id']==identifier and row['start']<item['end'] and row['end']>item['start'] for row in segments)]
        rows.append({'index':index,'source_start_seconds':item['start'],'source_end_seconds':item['end'],
            'original_start_seconds':source_offset+item['start'],'original_end_seconds':source_offset+item['end'],
            'source_start_frame':left,'source_end_frame':right,
            'timeline_start_frame':cursor,'timeline_end_frame':cursor+right-left,
            'timeline_start_seconds':cursor/fps,'timeline_end_seconds':(cursor+right-left)/fps,
            'source_unit_ids':[unit['id'] for unit in active],'canonical_segment_ids':ids})
        quantized.append({'start':left/fps,'end':right/fps});cursor+=right-left
    frame_verified=True;frame_error=None
    try:validate_source_span_constraints(proof,units,segments,selected_beat_ids=selected_ids,keep_ranges=quantized)
    except ValueError as error:frame_verified=False;frame_error=str(error)
    return {'scope':'Exact planned geometry; not semantic approval or encoded audiovisual validation',
        'source_fingerprint':inventory['source_fingerprint'],'selected_unit_ids':selected_ids,
        'canonical_segment_ids':proof['segment_ids'],'fps':fps,'timeline_frames':cursor,
        'timeline_seconds':cursor/fps,'source_offset_seconds':source_offset,
        'approved_ranges':approved,'fitted_ranges':fitted,'mapping':rows,
        'source_retention_proof':proof,'float_retention_validated':True,
        'renderer_nearest_frame_ranges':quantized,'frame_snapped_retention_validated':frame_verified,
        'frame_snapping_limit':frame_error,'explicit_continuity':continuity,
        'cost':story_duration_cost(approved,segments,duration,target=target,protect_action_span=continuity,fps=fps),
        'semantic_approved':False,'media_restored':False,'rendered':False}
