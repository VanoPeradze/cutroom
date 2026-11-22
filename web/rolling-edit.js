// The pair is chosen by actual touching times on one saved track, never by list order.
import { layerTrackState } from './layer-tracks.js?v=20261116-track-levels2';

const rates = new Set([24,25,30,50,60]);
const round9 = x => Math.round(x * 1e9) / 1e9;
const gridFrame=(edge,fps)=>{const n=Math.round(edge*fps);return Math.abs(edge-n/fps)<=5.1e-10?n:null;};
const visibleFrame=(edge,fps)=>gridFrame(edge,fps)??Math.ceil(edge*fps);
const shiftEdge=(edge,frames,fps)=>{if(!frames)return edge;const n=gridFrame(edge,fps);return n===null?edge+frames/fps:round9((n+frames)/fps);};
const bad = issue => ({issue});
const equal = (a,b) => a===b || (a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'
  && Array.isArray(a)===Array.isArray(b) && Object.keys(a).length===Object.keys(b).length
  && Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
const tc = (n,fps) => {const s=Math.floor(n/fps);return [Math.floor(s/3600),Math.floor(s/60)%60,s%60,n%fps].map(v=>String(v).padStart(2,'0')).join(':');};

export function rollPair(project, selected, edge) {
  if (!project?.draft || !selected || !['start','end','slide'].includes(edge)) return bad('Select one imported clip in Edited video.');
  const model=layerTrackState(project);if(model.issue)return bad(model.issue);
  if(!model.enabled)return bad('Enable editable tracks in Media > Tracks to roll cuts. No tracks are changed automatically.');
  const rows=project.manual.media_clips||[],clip=rows.find(row=>row.id===selected);
  const track=model.tracks.find(t=>t.id===clip?.track_id);
  if(!clip || !track || !['audio','visual'].includes(track.kind))return bad('Select an imported video, image or audio clip on a saved track.');
  const slide=edge==='slide', peers=rows.filter(r=>r.id!==selected && r.track_id===track.id);
  const previous=peers.filter(r=>r.end===clip.start),next=peers.filter(r=>r.start===clip.end);
  if(slide && (previous.length!==1 || next.length!==1))return bad('Slide needs a touching neighbor on both sides of this clip on '+track.name+'.');
  if(!slide && (edge==='end'?next:previous).length!==1)return bad('No touching neighbor at this edge on '+track.name+'. Choose the other edge or a different clip.');
  const middle=slide?clip:null,left=edge==='end'?clip:previous[0],right=edge==='start'?clip:next[0];
  const a=project.assets[left.asset_id],b=project.assets[right.asset_id],fps=project.settings?.fps??30;
  if(!rates.has(fps))return bad('The saved output frame rate is unsupported.');
  const pair={left,middle,right,a,b,track,fps,duration:project.editor_sequence?.duration??project.manual.sequence?.duration??project.draft.output_duration,cut:left.end};
  const blocked=issue=>({...pair,issue});
  if(track.locked)return blocked('Unlock this track before rolling its cut.');
  const members=slide?[[left,a],[middle,project.assets[middle.asset_id]],[right,b]]:[[left,a],[right,b]];
  for(const [r,asset] of members){
    if(!asset || asset.status!=='ready' || !['audio','video','image'].includes(asset.kind))return blocked(slide?'Prepare all three original media assets before sliding.':'Prepare both original media assets before rolling.');
    if(![r.start,r.end,r.source_start,r.speed,r.fade_in,r.fade_out].every(Number.isFinite)
      || r.source_start<0 || r.speed<.25 || r.speed>4 || r.fade_in<0 || r.fade_out<0
      || asset.kind!=='image'&&(!Number.isFinite(asset.duration)||asset.duration<=0||r.source_start+r.end-r.start>asset.duration+1e-8)
      || asset.kind==='video'&&(!Number.isFinite(r.video_source_start??r.source_start)||(r.video_source_start??r.source_start)<0))
      return blocked('A saved clip has invalid timing or source information. Reopen or repair this edit first.');
    if(r!==middle && asset.kind!=='audio' && r.motion!=='none')return blocked(slide?'A neighbor has pan/zoom motion that a slide would reshape. Turn off its motion first.':'A roll would change the pan/zoom motion phase. Turn off motion first.');
  }
  if(left.fade_out || right.fade_in)return blocked(slide?'Remove the neighbor fades facing the selected clip first. The selected clip may keep its own fades.':'Remove the fades at the shared cut first. Rolling cannot move their audio envelopes.');
  return {...pair,issue:''};
}

export function rollFrame(pair, mode, time) {
  if(!pair?.left || !rates.has(pair.fps))return null;
  const t=pair.cut*pair.fps,near=Math.round(t),base=pair.middle?visibleFrame(pair.cut,pair.fps):Math.abs(t-near)<1e-7?near:t;
  if(mode==='earlier')return Math.ceil(base)-1;
  if(mode==='later')return Math.floor(base)+1;
  return mode==='playhead'&&Number.isFinite(time)?Math.round(time*pair.fps):null;
}

export function planRoll(pair, frame) {
  if(!pair || pair.issue)return bad(pair?.issue||'Select a shared cut first.');
  const {left,middle,right,a,b,fps,duration}=pair;
  if(!Number.isSafeInteger(frame)||frame<0||frame>Math.ceil(duration*fps))return bad('Choose a frame inside the edited timeline.');
  let cut=round9(frame/fps),trailing=cut;
  if(middle){
    const shift=frame-visibleFrame(middle.start,fps);
    cut=shiftEdge(middle.start,shift,fps);trailing=shiftEdge(middle.end,shift,fps);
  }
  const delta=trailing-right.start;
  if(Math.abs(cut-left.end)<=1e-9)return bad(middle?'The clip already starts on this frame.':'The cut is already on this frame.');
  if(Math.min(cut-left.start,right.end-trailing)<.08-1e-9)return bad('Keep at least 0.08 seconds on both sides of the cut.');
  if(left.fade_in>cut-left.start+1e-9 || right.fade_out>right.end-trailing+1e-9)return bad('The cut would enter an outer audio fade.');
  if(a.kind!=='image' && left.source_start+cut-left.start>a.duration+1e-8)return bad('Not enough outgoing source after this cut.');
  if(a.kind==='video'&&delta>0&&(left.video_source_start??left.source_start)+(cut-left.start)*left.speed>a.duration+1e-8)
    return bad('Not enough outgoing picture after the cut; rolling will not add frozen frames.');
  const incoming={start:trailing};
  if(b.kind!=='image'){
    incoming.source_start=round9(right.source_start+delta);
    if(incoming.source_start<0)return bad('Not enough incoming source before this cut.');
  }
  if(b.kind==='video'){
    incoming.video_source_start=round9((right.video_source_start??right.source_start)+delta*right.speed);
    if(incoming.video_source_start<0 || incoming.video_source_start>57600)return bad('Not enough incoming picture for this cut.');
    if(delta<0 && (right.video_source_start??right.source_start)>b.duration+1e-8)return bad('The incoming picture starts in a held frame; there is no continuous picture handle.');
  }
  return {issue:'',cut,trailing,frame,incoming,detail:{left_id:left.id,...(middle?{clip_id:middle.id}:{}),right_id:right.id,frame}};
}

// Verify the narrow transaction on accepted saved data, never on preview overrides.
export function verifyRoll(before,after,detail) {
  const pair=rollPair(before,detail.clip_id??detail.left_id,detail.clip_id?'slide':'end'),plan=planRoll(pair,detail.frame);
  if(plan.issue || pair.left?.id!==detail.left_id || pair.right?.id!==detail.right_id || after?.id!==before?.id || after.revision!==before.revision+1 || !after.manual)
    return 'Unexpected project, cut or revision.';
  if(layerTrackState(after).issue)return 'The returned tracks are invalid.';
  const expected=before.manual.media_clips.map(r=>r.id===detail.left_id?{...r,end:plan.cut}:r.id===detail.clip_id?{...r,start:plan.cut,end:plan.trailing}:r.id===detail.right_id?{...r,...plan.incoming}:r);
  const actual=after.manual.media_clips;
  if(!Array.isArray(actual)||actual.length!==expected.length)return 'The result added or removed clips.';
  for(let i=0;i<expected.length;i++){
    const row={...actual[i]},want=expected[i];
    // Python and JS round a decimal half-nanosecond differently. Only the newly
    // calculated incoming source clocks can differ by one stored nanosecond.
    if(want.id===detail.right_id)for(const k of ['source_start','video_source_start'])if(Object.hasOwn(plan.incoming,k)
      && Number.isFinite(row[k]) && Math.abs(want[k]-row[k])<=1.1e-9)row[k]=want[k];
    if(!equal(row,want))return 'Unexpected change to a clip or source clock.';
  }
  const omit=(o,keys)=>Object.fromEntries(Object.entries(o||{}).filter(([k])=>!keys.includes(k)));
  if(!equal(omit(before.manual,['history','media_clips']),omit(after.manual,['history','media_clips']))
    || !equal(omit(before.draft,['status','edited_at']),omit(after.draft,['status','edited_at']))
    || ['sources','assets','settings','review_markers','editor_sequence','editor_captions'].some(k=>!equal(before[k],after[k])))return 'Other saved content changed.';
  if(after.manual.history?.undo_count!==Math.min(20,(before.manual.history?.undo_count??0)+1) || after.manual.history?.redo_count!==0)
    return 'The result did not confirm one Undo step.';
  return '';
}

export function initRollingEdit(root, host, slide=false) {
  if(!root)return null;
  const verb=slide?'slide':'roll',side=slide?null:root.querySelector('[data-roll-edge]'),edge=()=>slide?'slide':side.value;
  const title=root.querySelector('[data-'+verb+'-pair]'),status=root.querySelector('[data-'+verb+'-status]'),
    buttons=[...root.querySelectorAll('[data-'+verb+']')],text=(el,s)=>{if(el.textContent!==s)el.textContent=s;};
  let cache=null, identity=null, pending=false, notice='', display=null;
  function refresh(){
    if(!root.open){display=null;return;}
    const s=host.snapshot(),key=JSON.stringify([s.project?.id,s.view,s.selected]);
    if(key!==identity){identity=key;cache=null;notice='';
      if(side){side.value='end';if(s.selected && !rollPair(s.project,s.selected,'end').left && rollPair(s.project,s.selected,'start').left)side.value='start';}}
    if(!cache || cache.project!==s.project || cache.rev!==s.project?.revision || cache.edge!==edge()){
      cache={project:s.project,rev:s.project?.revision,edge:edge(),pair:rollPair(s.project,s.selected,edge())};
    }
    const p=cache.pair, block=pending?(slide?'Sliding the three clips…':'Saving the shared cut…'):s.issue||p.issue||'';
    if(side)side.disabled=pending;
    const start=p.left?(slide?visibleFrame(p.cut,p.fps):Math.round(p.cut*p.fps)):0;
    const span=p.middle?visibleFrame(p.middle.end,p.fps)-start:0;
    const rangeText=n=>tc(n,p.fps)+(slide?' to '+tc(n+span,p.fps):'');
    const at=p.left?rangeText(start)+(slide?' ('+span+' frames)':''):'';
    const center=p.middle?s.project.assets?.[p.middle.asset_id]?.name||'Selected clip':'';
    text(title,p.left?p.track.name+' · '+(p.a?.name||'Outgoing')+' → '+(center?center+' → ':'')+(p.b?.name||'Incoming')+' · '+at
      :slide?'Choose a clip between two neighbors':'Choose a shared cut');
    const targets={},reasons=[];
    for(const b of buttons){
      const mode=b.dataset[verb],frame=rollFrame(p,mode,s.time),plan=planRoll(p,frame),issue=block||plan.issue;
      b.disabled=Boolean(issue);b.title=issue||(slide?'Slide the selected shot to ':'Move the shared cut to ')+rangeText(frame)+'. Both outside edges stay fixed.';
      if(!issue)targets[mode]={...plan.detail};
      if(!block && issue)reasons.push((mode==='playhead'?'Playhead':mode==='earlier'?'Earlier':'Later')+': '+issue);
    }
    const play=targets.playhead;
    const phase=p.middle&&gridFrame(p.cut,p.fps)===null?'Subframe start retained; the timecode is its first visible frame.':'';
    text(status,block || [notice,phase,play?'At playhead: '+rangeText(play.frame)+'.':'',...reasons].filter(Boolean).join(' '));
    display={key,revision:s.project?.revision,view:s.view,id:s.project?.id,edge:edge(),targets,selected:s.selected};
  }
  root.addEventListener('toggle',refresh);
  side?.addEventListener('change',()=>{notice='';refresh();});
  for(const b of buttons)b.addEventListener('click',async()=>{
    if(pending || !root.open || b.disabled)return;
    const shown=display,mode=b.dataset[verb],desired=shown?.targets[mode];refresh();
    if(!desired || !display || shown.key!==display.key || shown.revision!==display.revision || shown.edge!==display.edge
      || !equal(desired,display.targets[mode]))return;
    pending=true;notice='';refresh();
    try{
      const result=await host.commit(shown,desired,mode);
      const now=host.snapshot();
      if(now.project?.id===shown.id && now.view===shown.view && now.selected===shown.selected)
        notice=result?(slide?'Clip slid. One Undo restores all three clips.':'Cut saved. One Undo restores both sides.'):'Edit not confirmed. Review the current timeline before trying again.';
    }catch(e){notice=String(e?.message||'Cut not confirmed. Reopen the edit before retrying.');}
    finally{pending=false;refresh();}
  });
  return {refresh};
}
