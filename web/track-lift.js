// Lift removes only the chosen occurrence spans. It never inserts a new source,
// shortens the edit or guesses a destination from the currently visible picture.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2';
import {cutVisualTrackWindow,verifyVisualTrackWindow} from './track-overwrite.js?v=20261118-tracklift1';
const fail=issue=>({issue}), ns=x=>Math.round(x*1e9)/1e9, rates=[24,25,30,50,60];
const duration=p=>p?.editor_sequence?.duration??p?.manual?.sequence?.duration??p?.draft?.output_duration;
const clock=(f,r)=>[Math.floor(f/(r*3600)),Math.floor(f/(r*60))%60,Math.floor(f/r)%60,f%r].map(v=>String(v).padStart(2,'0')).join(':');
export function liftFrameRange(range,fps,length){
  if(!rates.includes(fps)||!Number.isFinite(length)||length<=0)return fail('The saved edit has no supported frame clock.');
  if(!range||!Number.isFinite(range.start)||!Number.isFinite(range.end)||range.start<0||range.end<=range.start||range.end>length+5.1e-10)return fail('Mark an In and Out range on the edited timeline first.');
  // Only complete output frames, never silently erase outside a freehand mark.
  // The tolerance recognizes only the nanosecond spelling of an exact frame.
  const snap=t=>{const n=Math.round(t*fps);return Math.abs(t-n/fps)<=5.1e-10?n:t*fps;};
  const start_frame=Math.ceil(snap(range.start)),end_frame=Math.floor(snap(Math.min(length,range.end)));
  if(!Number.isSafeInteger(start_frame)||!Number.isSafeInteger(end_frame)||(end_frame-start_frame)/fps<.08-1e-9)return fail('The marked range must contain at least 0.08 seconds of complete output frames.');
  return {start_frame,end_frame};
}
export function planTrackLift(project,detail){
  const fps=project?.settings?.fps??30,length=duration(project),d=detail||{};
  if(!project?.id||!project.draft||!Number.isInteger(project.revision)||project.revision<1||project.editor_sequence?.error)return fail('Open the saved edit before lifting a track.');
  const state=layerTrackState(project);if(state.issue)return fail(state.issue);
  if(!state.enabled)return fail('Enable editable tracks before lifting from a named visual track.');
  const track=state.tracks.find(t=>t.id===d.track_id);
  if(!track||track.kind!=='visual')return fail('Choose one named visual track to lift. Other tracks will not move.');
  if(track.locked)return fail('Unlock '+track.name+' before lifting any of its clips.');
  if(!rates.includes(fps)||!Number.isFinite(length)||length<=0||!Number.isSafeInteger(d.start_frame)||!Number.isSafeInteger(d.end_frame)
    ||d.start_frame<0||d.end_frame<=d.start_frame||d.end_frame>Math.ceil(length*fps))
    return fail('Choose a valid frame range wholly inside this saved edit.');
  const start=ns(d.start_frame/fps),rawEnd=ns(d.end_frame/fps);
  if(start>=length||rawEnd>length+5.1e-10)return fail('The whole lifted interval must fit inside the saved edit.');
  const end=Math.min(length,rawEnd);
  if(end-start<.08-1e-9)return fail('The lifted interval must cover at least 0.08 seconds.');
  const cut=cutVisualTrackWindow(project,track,start,end,'lift');if(cut.issue)return cut;
  if(!cut.affected.length)return fail('This track is already empty in the marked range. Nothing will be changed.');
  if(cut.rows.length>200)return fail('This split would exceed the 200 media clip limit. Nothing will be lifted.');
  return {issue:'',fps,start,end,startFrame:d.start_frame,endFrame:d.end_frame,track,...cut};
}
export function describeTrackLift(p) {
  if(p.issue)return p.issue;
  const c=p.counts,a=p.affected,names=a.slice(0,3).map(x=>x.name+(x.disabled?' (disabled)':'')).join(', ')+(a.length>3?' and '+(a.length-3)+' more':'');
  return p.track.name+' · '+clock(p.startFrame,p.fps)+' to '+clock(p.endFrame,p.fps)+' (Out excluded). Remove '+c.removed+' whole, trim '+c.trimmed+', split '+c.split+'. Affected: '+names+'.';
}
export function verifyTrackLift(before,after,detail){return verifyVisualTrackWindow(before,after,planTrackLift(before,detail));}

export function initTrackLift(root,{snapshot,commit}) {
  if(!root||typeof snapshot!=='function'||typeof commit!=='function')return null;
  const lane=root.querySelector('#trackLiftLane'),status=root.querySelector('#trackLiftStatus'),apply=root.querySelector('#trackLiftApply'),receipt=root.querySelector('#trackLiftReceipt');
  if(!lane||!status||!apply||!receipt)return null;
  let projectKey=null,choicesKey='',reviewKey='',working=false,record=null,live=true;
  const write=(el,t)=>{if(el.textContent!==t)el.textContent=t;};
  const option=(text,value,disabled=false)=>{const n=root.ownerDocument.createElement('option');n.textContent=text;n.value=value;n.disabled=disabled;return n;};
  const key=(s,id)=>JSON.stringify([s.project?.id,s.view,s.project?.revision,s.range?.start,s.range?.end,id]);
  function refresh(){
    if(!live||!root.open){reviewKey='';return null;}
    const s=snapshot(),p=s.project;const pk=JSON.stringify([p?.id,s.view]);
    if(pk!==projectKey){lane.value='';choicesKey='';record=null;projectKey=pk;}
    const state=p?layerTrackState(p):null,tracks=(state?.enabled&&!state.issue?state.tracks:[]).filter(t=>t.kind==='visual');
    const sig=JSON.stringify(tracks.map(t=>[t.id,t.name,t.locked]));
    if(choicesKey!==sig){const was=lane.value;lane.replaceChildren(option('Choose a visual track',''),...tracks.map(t=>option(t.name+(t.locked?' (locked)':''),t.id,t.locked)));lane.value=tracks.some(t=>t.id===was&&!t.locked)?was:'';choicesKey=sig;}
    const id=lane.value,range=liftFrameRange(s.range,p?.settings?.fps??30,duration(p)),d={track_id:id,start_frame:range.start_frame,end_frame:range.end_frame};
    const p0=s.issue?fail(s.issue):state?.issue?fail(state.issue):!state?.enabled?fail('Enable editable tracks before lifting from a named visual track.'):range.issue?range:planTrackLift(p,d);
    const currentKey=key(s,id);
    if(record && record.key!==currentKey)record=null;
    write(receipt,record?.message||'');receipt.hidden=!record;
    write(status,working?'Saving the reviewed lift…':describeTrackLift(p0));
    lane.disabled=working||!tracks.length;apply.disabled=working||Boolean(p0.issue);
    reviewKey=p0.issue?'':currentKey;return {s,d,plan:p0,key:currentKey};
  }
  const start=async()=>{
    if(working||!live)return;const shown=reviewKey,v=refresh();
    if(!v||v.plan.issue||!shown||shown!==v.key)return;
    const owner={id:v.s.project.id,view:v.s.view,revision:v.s.project.revision,range:{...v.s.range},track:v.d.track_id};
    const owns=()=>live&&root.open&&lane.value===owner.track;
    working=true;record=null;refresh();
    try{const saved=await commit(owner,v.d,owns);if(!owns())return;const now=snapshot();
      if(saved?.id===owner.id&&saved.revision===owner.revision+1&&now.project?.id===saved.id&&now.project.revision===saved.revision&&now.view===owner.view&&now.range?.start===owner.range.start&&now.range?.end===owner.range.end)
        record={key:key(now,owner.track),message:'Lifted from '+v.plan.track.name+'. Edit length and other tracks stayed fixed. Undo restores the lifted material.'};
    }finally{working=false;refresh();}
  };
  const activate=()=>{void start().catch(()=>{if(live)write(status,'The lift could not be confirmed. Reopen the saved edit before retrying.');});};
  const changed=()=>{record=null;refresh();};
  root.addEventListener('toggle',refresh);lane.addEventListener('change',changed);apply.addEventListener('click',activate);refresh();
  return {sync:refresh,destroy(){live=false;root.removeEventListener('toggle',refresh);lane.removeEventListener('change',changed);apply.removeEventListener('click',activate);}};
}
