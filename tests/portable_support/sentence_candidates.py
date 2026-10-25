"""Diagnostic exact-source inventory; punctuation proposes, never proves meaning.

No ASR text/word is rewritten. Complete original ASR segments remain indivisible.
Thus a sentence boundary inside an ASR segment is recorded but is not cut permission.
"""
from __future__ import annotations
import copy, hashlib, json, math, re
from cutroom.story_budget import story_duration_cost

POLICY='whole-asr-sentence-candidates-2026-10-21-v1'
END=re.compile(r'''[.!?\u061f\u3002\uff01\uff1f]["'\u201d\u2019\u00bb)\]]*$''')
INNER=re.compile(r'''[.!?\u061f\u3002\uff01\uff1f]["'\u201d\u2019\u00bb)\]]*(?=\s|$)''')

def fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,
        separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()

def build_inventory(segments, source_identity, *, source_offset=0., maximum_segments=512):
    if not isinstance(segments,list) or not segments or len(segments)>maximum_segments:
        raise ValueError('Whole-source inventory limit; no first-N truncation permitted')
    if not isinstance(source_identity,dict) or not source_identity:
        raise ValueError('Exact source identity is required')
    identifiers=set(); previous_end=-1.
    for row in segments:
        if not isinstance(row,dict) or not isinstance(row.get('id'),str) or row['id'] in identifiers:
            raise ValueError('Ambiguous original ASR segment identity')
        identifiers.add(row['id'])
        for key in ('start','end'):
            if isinstance(row.get(key),bool) or not isinstance(row.get(key),(int,float)) or not math.isfinite(row[key]):
                raise ValueError('Invalid canonical source geometry')
        if row['start']<0 or row['end']<=row['start'] or row['start']<previous_end-.001:
            raise ValueError('Source order/overlap is invalid; never silently sort it')
        if not isinstance(row.get('text'),str) or not row['text'].strip():
            raise ValueError('Empty source text cannot supply sentence evidence')
        previous_end=row['end']
    binding=fingerprint({'policy':POLICY,'source':source_identity,'segments':segments})
    duration=max(row['end'] for row in segments)
    groups=[]; pending=[]
    def emit(complete):
        text=' '.join(row['text'] for row in pending)
        ids=[row['id'] for row in pending]
        start,end=pending[0]['start'],pending[-1]['end']
        unit={'id':'u_'+fingerprint({'source':binding,'segment_ids':ids})[:20],
              'start':start,'end':end,'duration':end-start,'segment_ids':ids,'text':text,
              'boundary_status':'punctuation_at_full_asr_boundary' if complete else 'unfinished_excerpt_tail',
              'semantic_coherence_verified':False,'source_offset_seconds':source_offset,
              'original_start_seconds':source_offset+start,'original_end_seconds':source_offset+end,
              'cost':story_duration_cost([{'start':start,'end':end}],segments,duration),
              'original_segment_word_spans':[{key:copy.deepcopy(row.get(key)) for key in ('id','start','end','text','words')}
                                             for row in pending],
              'internal_sentence_marks':[{'segment_id':row['id'],'char_end':mark.end(),
                    'cut_permission':False} for row in pending for mark in INNER.finditer(row['text'])
                    if mark.end()<len(row['text'].rstrip())]}
        groups.append(unit);pending.clear()
    for row in segments:
        pending.append(row)
        tail=row['text'].rstrip().rstrip('"\'\u201d\u2019\u00bb)]')
        if END.search(row['text'].strip()) and not tail.endswith(('...','\u2026')):
            emit(True)
    if pending:emit(False)
    assert [identifier for unit in groups for identifier in unit['segment_ids']]==[row['id'] for row in segments]
    return {'policy_version':POLICY,'source_identity':copy.deepcopy(source_identity),
            'source_fingerprint':binding,'coverage_complete':True,'original_segment_count':len(segments),
            'all_original_segment_ids':[row['id'] for row in segments],'units':groups,
            'authority':'Exact-source representation and numeric cost only; semantic review required',
            'canonical_ASR_modified':False,'sub_ASR_sentence_cut_supported':False}

def choose_control(inventory, segments, segment_ids, *, target=60.):
    wanted=set(segment_ids)
    if len(wanted)!=len(segment_ids):raise ValueError('Repeated requested source')
    units=[unit for unit in inventory['units'] if wanted.intersection(unit['segment_ids'])]
    represented={identifier for unit in units for identifier in unit['segment_ids']}
    if represented!=wanted:raise ValueError('Control cannot split an exact-source sentence group or invent IDs')
    if any(unit['boundary_status']!='punctuation_at_full_asr_boundary' for unit in units):
        raise ValueError('An unfinished excerpt tail cannot be declared complete')
    intervals=[{'start':unit['start'],'end':unit['end']} for unit in units]
    cost=story_duration_cost(intervals,segments,max(row['end'] for row in segments),target=target)
    minimum=.9*min(target,max(row['end'] for row in segments))
    numeric=(cost['minimum_safe_seconds']<=target+.05 and cost['approved_seconds']+.05>=minimum)
    return {'scope':'Assistant-selected diagnostic countercontrol, not autonomous source discovery',
            'unit_ids':[unit['id'] for unit in units],'original_segment_ids':segment_ids,
            'approved_intervals':intervals,'cost':cost,'target_seconds':target,
            'required_target_minimum_seconds':minimum,'numerically_feasible':numeric,
            'semantic_fit_verified':False,'source_fingerprint':inventory['source_fingerprint'],
            'no_model_response_or_source_text_repaired':True}

def attach_parent_provenance(inventory, parent_beats):
    """Analysis ownership is provenance, not a compulsory playback grouping."""
    ownership={}
    for beat in parent_beats:
        if not isinstance(beat.get('id'),str) or not isinstance(beat.get('segment_ids'),list):
            raise ValueError('Missing original parent analysis ownership')
        for identifier in beat['segment_ids']:
            if identifier in ownership:raise ValueError('Duplicate parent analysis ownership')
            ownership[identifier]=beat['id']
    if set(ownership)!=set(inventory['all_original_segment_ids']):
        raise ValueError('Missing or unknown original parent ownership')
    result=copy.deepcopy(inventory)
    result['parent_analysis_ownership']=ownership
    for unit in result['units']:
        unit['parent_analysis_beat_ids']=list(dict.fromkeys(ownership[value] for value in unit['segment_ids']))
    result['parent_ownership_fingerprint']=fingerprint(ownership)
    return result
