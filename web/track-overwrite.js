// An explicit three-point overwrite, never a ripple or automatic track placement.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2';

const fail=issue=>({issue}), ns=x=>Math.round(x*1e9)/1e9;
const finite=Number.isFinite, mediaID=s=>typeof s==='string'&&/^media_[0-9a-f]{32}$/.test(s);
const equal=(a,b)=>a===b || (a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)
  && Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
const omit=(o,keys)=>Object.fromEntries(Object.entries(o||{}).filter(([k])=>!keys.includes(k)));

export function planTrackOverwrite(project, detail) {
  if(!project?.id||!project.draft||!Number.isInteger(project.revision)||project.editor_sequence?.error)return fail('Open the saved edit before overwriting a track.');
  const state=layerTrackState(project);if(state.issue)return fail(state.issue);
  if(!state.enabled)return fail('Enable editable tracks to overwrite imported footage on one track.');
  const d=detail||{},track=state.tracks.find(t=>t.id===d.track_id);
  if(!track||track.kind!=='visual')return fail('Choose a named visual Destination track above; Automatic does not overwrite.');
  if(track.locked)return fail('Unlock '+track.name+' before overwriting its clips.');
  const a=project.assets?.[d.asset_id],fps=project.settings?.fps??30,length=project.editor_sequence?.duration??project.manual?.sequence?.duration??project.draft.output_duration;
  if(!a||a.id!==d.asset_id||a.kind!=='video'||a.status!=='ready'||!finite(a.duration)||a.duration<.08||a.duration>14400||typeof a.has_audio!=='boolean')return fail('Choose a ready video with known timing and sound.');
  if(![24,25,30,50,60].includes(fps)||!finite(length)||!Number.isSafeInteger(d.frame)||d.frame<0||d.frame>Math.ceil(length*fps))return fail('Choose an output frame inside this saved edit.');
  if(![d.source_start,d.source_end].every(v=>finite(v)&&v>=0&&v<=a.duration))return fail('Choose valid Source In and Out inside the video.');
  const src=ns(d.source_start),span=ns(ns(d.source_end)-src);if(span<.08-1e-9)return fail('Choose at least 0.08 seconds of this source.');
  const start=ns(d.frame/fps),n=Math.round(span*fps);
  let end=Math.abs(span-n/fps)<=5.1e-10?ns((d.frame+n)/fps):ns(start+span);
  if(start>=length||end>length+5.1e-10)return fail('The full marked shot must fit before the edit end. Overwrite never extends the timeline.');
  end=Math.min(length,end);
  const cut=cutVisualTrackWindow(project,track,start,end);
  if(cut.issue)return cut;
  const {rows,affected,counts}=cut;
  if(rows.length+1>200)return fail('This overwrite would exceed the 200 media clip limit.');
  const placed={id:null,asset_id:a.id,track_id:track.id,start,end,source_start:src,video_source_start:src,speed:1,volume_db:0,
    muted:false,role:'voice',audio_enabled:a.has_audio,fade_in:0,fade_out:0,x:0,y:0,w:1,h:1,fit:'cover',motion:'none'};
  return {issue:'',track,start,end,rows:[...rows,placed],counts,affected,placed};
}

// Preserve each surviving occurrence and both clocks. Lift uses this exact same
// half-open geometry but deliberately does not place a source into the hole.
export function cutVisualTrackWindow(project,track,start,end,operation='overwrite') {
  const rows=[],all=project.manual.media_clips||[],affected=[],counts={removed:0,trimmed:0,split:0};
  for(const r of all){
    if(r.track_id!==track.id||r.end<=start||r.start>=end){rows.push(r);continue;}
    const old=project.assets?.[r.asset_id];
    if(!old||old.status!=='ready'||!['video','image'].includes(old.kind))return fail('A destination clip has unavailable original media.');
    if(![r.start,r.end,r.source_start,r.speed,r.fade_in,r.fade_out].every(finite)||r.source_start<0||r.speed<.25||r.speed>4||r.fade_in<0||r.fade_out<0
      ||old.kind==='video'&&(!finite(old.duration)||r.source_start+r.end-r.start>old.duration+1e-8||!finite(r.video_source_start??r.source_start)||(r.video_source_start??r.source_start)<0))
      return fail('A destination clip has invalid timing. Reopen or repair the current edit.');
    const left=r.start<start,right=r.end>end;affected.push({id:r.id,name:old.name||'Untitled',start:r.start,disabled:r.enabled===false});
    if(!left&&!right){counts.removed++;continue;}
    if(r.motion!=='none')return fail('A partial '+operation+' would reshape pan/zoom on '+(old.name||'this clip')+'. Choose its edge or cover it entirely.');
    for(const [boundary,remains] of [[start,left],[end,right]])if(remains&&(boundary-r.start<r.fade_in-1e-9||r.end-boundary<r.fade_out-1e-9))return fail('A cut would enter a saved audio fade on '+(old.name||'this clip')+'.');
    if(left&&start-r.start<.08-1e-9||right&&r.end-end<.08-1e-9)return fail('A retained piece would be shorter than 0.08 seconds.');
    if(left)rows.push({...r,end:start,fade_out:0});
    if(right){
      const piece={...r,start:end,fade_in:0},elapsed=end-r.start;
      if(left)piece.id=null; // The backend allocates exactly one fresh right remainder.
      if(old.kind==='video'){piece.source_start=ns(r.source_start+elapsed);piece.video_source_start=ns((r.video_source_start??r.source_start)+elapsed*r.speed);
        if(piece.video_source_start>57600)return fail('The retained picture clock exceeds the supported source range.');}
      rows.push(piece);
    }
    counts[left&&right?'split':'trimmed']++;
  }
  affected.sort((first,second)=>first.start-second.start);
  return {rows,affected,counts};
}

export function verifyTrackOverwrite(before,after,detail) {
  return verifyVisualTrackWindow(before,after,planTrackOverwrite(before,detail));
}
export function verifyVisualTrackWindow(before,after,p) {
  if(p.issue||after?.id!==before?.id||after.revision!==before.revision+1||!after.manual||layerTrackState(after).issue)return 'Unexpected project, lane or revision.';
  const actual=after.manual.media_clips;
  if(!Array.isArray(actual)||actual.length!==p.rows.length)return 'The number of removed or created pieces differed.';
  const seen=new Set(before.manual.media_clips.map(x=>x.id));
  for(let i=0;i<actual.length;i++){
    const want={...p.rows[i]},got=actual[i];
    if(want.id===null){if(!mediaID(got?.id)||seen.has(got.id))return 'A new occurrence ID was missing or reused.';seen.add(got.id);want.id=got.id;}
    if(!equal(want,got))return 'Clip content, retained timing, source clocks, or position on the track changed unexpectedly.';
  }
  if(!equal(omit(before.manual,['history','media_clips']),omit(after.manual,['history','media_clips']))
      || !equal(omit(before.draft,['status','edited_at']),omit(after.draft,['status','edited_at']))
      || ['settings','sources','assets','review_markers','editor_sequence','editor_captions','exports'].some(k=>!equal(before[k],after[k])))return 'Unrelated saved content changed.';
  if(after.manual.history?.undo_count!==Math.min(20,(before.manual.history?.undo_count??0)+1)||after.manual.history?.redo_count!==0)return 'The saved result did not confirm one Undo step.';
  return '';
}

export function describeTrackOverwrite(plan){
  if(plan.issue)return plan.issue;
  const {counts:c,affected:a}=plan,t=s=>Number(s.toFixed(6))+' s';
  return plan.track.name+' · edit '+t(plan.start)+' to '+t(plan.end)+'. '+(a.length?
    'Remove '+c.removed+' whole, trim '+c.trimmed+', split '+c.split+' around the shot. Affected: '+a.slice(0,3).map(x=>x.name+(x.disabled?' (disabled)':'')).join(', ')+(a.length>3?' and '+(a.length-3)+' more.':'.')
    :'Empty on this track; no clips are removed.')+' All other tracks and edit length stay fixed.';
}
