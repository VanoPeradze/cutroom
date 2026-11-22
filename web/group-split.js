// Plan a single, frame-accurate split of all selected occurrences, never A/B.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2-opacity1';
const idPattern=/^(media|text)_[0-9a-f]{32}$/,ns=n=>Math.round(n*1e9)/1e9,fail=issue=>({issue});
const arrays=[['media_clips','media_',200],['text_clips','text_',2000]];
function counts(manual){if(!manual||typeof manual!=='object'||Array.isArray(manual))return null;
 if(!Object.hasOwn(manual,'history'))return {undo_count:0,redo_count:0};const h=manual.history;
 return h&&typeof h==='object'&&!Array.isArray(h)&&Object.keys(h).length===2&&['undo_count','redo_count'].every(k=>Number.isInteger(h[k])&&h[k]>=0&&h[k]<=20)?h:null;}
const equal=(a,b)=>a===b||!!a&&!!b&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]));
const except=(obj,keys)=>Object.fromEntries(Object.entries(obj||{}).filter(([k])=>!keys.includes(k)));
export function groupSplitFrame(project,time){
 const fps=project?.settings?.fps;return [24,25,30,50,60].includes(fps)&&Number.isFinite(time)&&time>=0?Math.round(time*fps):null;
}
export function planGroupSplit(project,ids,frame){
 const fps=project?.settings?.fps,duration=project?.editor_sequence?.duration;
 if(!project?.id||!project?.draft||!Number.isInteger(project.revision)||project.revision<1||project.editor_sequence?.error||!Number.isFinite(duration)||duration<=0)return fail('Open a saved edit with a valid edit clock.');
 if(!counts(project.manual))return fail('The saved Undo history is invalid. Reopen a compatible edit before splitting.');
 if(!Array.isArray(ids)||ids.length<2||ids.length>200||ids.some(id=>typeof id!=='string'||!idPattern.test(id))||new Set(ids).size!==ids.length)return fail('Select 2 to 200 different imported media or saved text clips.');
 if(![24,25,30,50,60].includes(fps)||!Number.isSafeInteger(frame)||frame<=0||frame>=Math.ceil(duration*fps))return fail('Place the playhead on an output frame inside all selected clips.');
 const time=ns(frame/fps),tracks=layerTrackState(project);if(tracks.issue)return fail(tracks.issue);
 const locked=new Map(tracks.tracks.filter(t=>t.locked).map(t=>[t.id,t.name])),seen=new Set(),wanted=new Set(ids),pieces=[];
 for(const [key,prefix,cap] of arrays){
   const rows=project?.manual?.[key]??[];if(!Array.isArray(rows)||rows.length>cap)return fail('The saved layer list is unavailable.');
   let added=0;
   for(const old of rows){
     if(!old||typeof old.id!=='string'||!idPattern.test(old.id)||!old.id.startsWith(prefix)||seen.has(old.id))return fail('The saved timeline has ambiguous clip identities. Reopen it before splitting.');seen.add(old.id);
     if(!wanted.has(old.id))continue;added++;
     if(locked.has(old.track_id))return fail('Unlock '+locked.get(old.track_id)+' before splitting this selection. No clips were split.');
     if(!Number.isFinite(old.start)||!Number.isFinite(old.end)||old.start<0||old.end>duration)return fail('A selected clip has invalid saved timing.');
     const elapsed=time-old.start,remaining=old.end-time;
     if(Math.min(elapsed,remaining)<.08-1e-9)return fail('Every selected clip must cross the playhead with at least 0.08 seconds on each side.');
     const left={...old,end:time},right={...old,start:time};
     if(key==='media_clips'){
       const asset=project.assets?.[old.asset_id];
       if(!asset||asset.id!==old.asset_id||asset.status!=='ready'||!['audio','video','image'].includes(asset.kind))return fail('A selected clip needs its ready imported file.');
       if(asset.kind!=='audio'&&old.motion!=='none')return fail('A selected pan/zoom would restart at the cut. Use a static clip or deselect it.');
       if(![old.fade_in,old.fade_out,old.source_start,old.speed].every(Number.isFinite)||old.fade_in<0||old.fade_out<0||old.speed<=0)return fail('A selected clip has invalid media timing.');
       if(elapsed<old.fade_in-1e-9||remaining<old.fade_out-1e-9)return fail('The playhead is inside a selected audio fade. Move outside the fade or deselect that clip.');
       left.fade_out=0;right.fade_in=0;
       if(asset.kind!=='image')right.source_start=ns(old.source_start+elapsed);
       if(asset.kind==='video'){const origin=old.video_source_start??old.source_start;if(!Number.isFinite(origin))return fail('A selected picture has invalid source timing.');right.video_source_start=ns(origin+elapsed*old.speed);}
     }else if(old.template==='chapter')return fail('A Chapter title would restart its built-in fade. Choose a static title or deselect it.');
     pieces.push({id:old.id,left,right});
   }
   if(rows.length+added>cap)return fail('The split would exceed the '+cap+' '+(prefix==='media_'?'media':'text')+' clip limit.');
 }
 if(pieces.length!==ids.length)return fail('A selected clip is no longer in this edit. Select the clips again.');
 return {issue:'',ids:[...ids],frame,fps,time,pieces};
}
export function verifyGroupSplit(before,after,ids,frame,created){
 const plan=planGroupSplit(before,ids,frame);if(plan.issue)return plan;
 if(after?.id!==before.id||after.revision!==before.revision+1)return fail('The returned project or revision did not match this split.');
 if(!Array.isArray(created)||created.length!==ids.length)return fail('The response did not identify every new right-hand piece.');
 const a=counts(before.manual),h=counts(after?.manual);
 if(!a||!h||!Object.hasOwn(after.manual,'history')||h.undo_count!==Math.min(20,a.undo_count+1)||h.redo_count!==0)return fail('The saved edit did not confirm one Undo step.');
 for(const key of ['name','settings','sources','assets','analysis','editor_sequence','exports','review_markers'])if(!equal(before[key],after[key]))return fail('The split unexpectedly changed other project content.');
 if(!equal(except(before.draft,['edited_at','status']),except(after.draft,['edited_at','status']))||after.draft?.status!==before.draft?.status&&after.draft?.status!=='ready')return fail('The draft changed beyond the selected layers.');
 if(!equal(except(before.manual,['history','_history','media_clips','text_clips']),except(after.manual,['history','_history','media_clips','text_clips'])))return fail('The split changed other edit controls or tracks.');
 const wanted=new Set(ids),oldIds=new Set(arrays.flatMap(([k])=>(before.manual[k]||[]).map(x=>x.id))),newIds=new Set(),mapping=Object.create(null),byId=new Map(plan.pieces.map(p=>[p.id,p]));
 for(const e of created){
   if(!e||Object.keys(e).length!==2||!wanted.has(e.source_id)||Object.hasOwn(mapping,e.source_id)||typeof e.clip_id!=='string'||!idPattern.test(e.clip_id)||e.source_id.split('_')[0]!==e.clip_id.split('_')[0]||oldIds.has(e.clip_id)||newIds.has(e.clip_id))return fail('The new right-hand identities are missing, repeated or inconsistent.');
   mapping[e.source_id]=e.clip_id;newIds.add(e.clip_id);
 }
 for(const [key]of arrays){
   const expected=(before.manual[key]||[]).flatMap(row=>{const p=byId.get(row.id);return p?[p.left,{...p.right,id:mapping[row.id]}]:[row];});
   if(!equal(expected,after.manual?.[key]||[]))return fail('The saved pieces, ordering, timing, contents or unselected layers did not match the split.');
 }
 return {issue:'',ids:ids.map(id=>mapping[id]),mapping};
}
