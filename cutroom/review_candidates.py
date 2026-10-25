"""Unapplied source candidates for explicit review, never semantic approval."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .cache_keys import stable_fingerprint
from .instruction_contract import assert_instruction_contract, effective_duration_bounds
from .story_budget import framed_story_duration


NOTICE = "Source selection needs review. AI did not verify content or transcription."
REQUEST_FIELDS = ('instruction','goal','output_count','source_continuity','target_duration','duration_mode',
                  'aspect','layout','audio_source','edit_style','captions','burn_captions','fps','resolution','quality')


def media_identity(project, directory):
    source=(project.get('sources') or {}).get('A') or {}
    result={}
    root=Path(directory).resolve()
    for key in ('relative_path','preview_relative_path'):
        relative=source.get(key)
        if not relative and key=='preview_relative_path':continue
        if not isinstance(relative,str):raise ValueError('The reviewed source is unavailable.')
        path=(root/relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():raise ValueError('The reviewed source is unavailable.')
        stat=path.stat();result[key]=[relative,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns]
    return result


def transcript_identity(project):
    transcript=(project.get('analysis') or {}).get('transcript') or {}
    return stable_fingerprint('source-review-transcript-v1',transcript)


def require_supported(project):
    manual=project.get('manual') or {}
    if (not (project.get('sources') or {}).get('A') or (project.get('sources') or {}).get('B')
            or any(key in manual for key in ('sequence','source_tracks'))
            or any(manual.get(key) for key in ('media_clips','text_clips','caption_overrides','caption_corrections',
                                              'caption_dormant_overrides','audio_mixer','caption_alternative','embedded_camera'))):
        raise ValueError('Source review currently supports source A without added media/text, alternate captions or an independent source timeline. Your edit is unchanged.')


def validate_ranges(project,request,ranges,segment_ids):
    require_supported(project)
    duration=(project['sources']['A'] or {}).get('duration')
    if type(duration) not in (int,float) or not math.isfinite(duration) or duration<=0:
        raise ValueError('Source duration is unavailable.')
    contract=assert_instruction_contract(request)
    if request.get('output_count',1)!=1:raise ValueError('Review candidates currently represent one output.')
    if not isinstance(ranges,list) or not 1<=len(ranges)<=48:raise ValueError('Invalid reviewed source ranges.')
    clean=[];previous=-1.
    for row in ranges:
        if not isinstance(row,dict):raise ValueError('Invalid reviewed source range.')
        start,end=row.get('start'),row.get('end')
        if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (start,end))
                or not 0<=start<end<=duration or start<previous):raise ValueError('Invalid reviewed source order.')
        clean.append({'start':start,'end':end});previous=end
    if contract['selection_controls']['source_continuity']=='required' and len(clean)!=1:
        raise ValueError('The candidate conflicts with the explicit no-cuts instruction.')
    segments=((project.get('analysis') or {}).get('transcript') or {}).get('segments') or []
    selected=[]
    for segment in segments:
        overlaps=[r for r in clean if segment['start']<r['end'] and segment['end']>r['start']]
        if overlaps:
            if len(overlaps)!=1 or segment['start']<overlaps[0]['start'] or segment['end']>overlaps[0]['end']:
                raise ValueError('A candidate clips canonical source speech.')
            selected.append(segment)
    if (not selected or [r['id'] for r in selected]!=segment_ids
            or len(segment_ids)!=len(set(segment_ids))):raise ValueError('The candidate source evidence changed.')
    for row in clean:
        inside=[s for s in selected if s['start']>=row['start'] and s['end']<=row['end']]
        if not inside or inside[0]['start']!=row['start'] or inside[-1]['end']!=row['end']:
            raise ValueError('Candidate endpoints need complete canonical source boundaries.')
    output=sum(r['end']-r['start'] for r in clean)
    bounds=effective_duration_bounds(request,duration)
    encoded=framed_story_duration(clean,request.get('fps') or 30)
    if bounds['explicit'] and (min(output,encoded)<bounds['minimum_seconds']-.05 or max(output,encoded)>bounds['maximum_seconds']+.05):
        raise ValueError('The candidate conflicts with the explicitly requested duration.')
    return clean,output,selected


def build_review_shelf(project,request,options,identity,*,revision=None):
    require_supported(project)
    brief={k:copy.deepcopy(request[k]) for k in REQUEST_FIELDS if k in request}
    rows=options.get('review_candidates') or []
    if not isinstance(rows,list) or not 1<=len(rows)<=8:raise ValueError('No bounded source candidates are available.')
    items=[]
    for row in rows:
        ranges,seconds,segments=validate_ranges(project,brief,row['playback_ranges'],row['segment_ids'])
        identifier='review_'+stable_fingerprint('source-review-v1',{'source':project['sources']['A'].get('generation'),
            'request':brief,'segments':row['segment_ids'],'ranges':ranges})[:24]
        items.append({'id':identifier,'kind':'unverified_source_candidate','rank':len(items)+1,
            'ranges':ranges,'segment_ids':list(row['segment_ids']),'output_duration':seconds,
            'preview':'ASR (unverified): '+' '.join(str(r['text']) for r in segments)[:240],
            'status':'needs_user_review','semantic_approval':False,'notice':NOTICE})
    if len({r['id'] for r in items})!=len(items):raise ValueError('Duplicate source proposals are ambiguous.')
    return {'version':'source-review-v1','revision':project['revision'] if revision is None else revision,
        'source_generation':project['sources']['A'].get('generation'),'transcript_identity':transcript_identity(project),
        'media_fingerprint':stable_fingerprint('source-review-media',identity),'request':brief,'items':items,
        'status':'needs_user_review','semantic_approval':False,'notice':NOTICE}


def checked_source_candidate(project,candidate_id,identity):
    shelf=(project.get('analysis') or {}).get('review_candidates') or {}
    if (shelf.get('version')!='source-review-v1' or shelf.get('revision')!=project.get('revision')
            or shelf.get('source_generation')!=(project.get('sources') or {}).get('A',{}).get('generation')
            or shelf.get('transcript_identity')!=transcript_identity(project)
            or shelf.get('media_fingerprint')!=stable_fingerprint('source-review-media',identity)):
        raise ValueError('The source or project changed. Generate or refresh the candidate review; your edit is unchanged.')
    rows=[r for r in shelf.get('items',[]) if r.get('id')==candidate_id]
    if len(rows)!=1:raise ValueError('Select an available source proposal.')
    row=rows[0];validate_ranges(project,shelf['request'],row['ranges'],row['segment_ids'])
    return copy.deepcopy(row),copy.deepcopy(shelf['request'])


def publish_failed_review(store,project_id,request,options,expected_source_generation):
    def publish(current):
        if (current.get('sources') or {}).get('A',{}).get('generation')!=expected_source_generation:
            raise ValueError('Source changed during candidate preparation.')
        shelf=build_review_shelf(current,request,options,media_identity(current,store.project_dir(project_id)),revision=current['revision']+1)
        current.setdefault('analysis',{})['review_candidates']=shelf
    return store.update(project_id,publish)
