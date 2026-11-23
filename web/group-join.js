// A through edit is an existing cut whose two saved sides already describe
// one continuous performance. Joining is never an arbitrary clip merge.
import {layerTrackState} from './layer-tracks.js?v=20261116-track-levels2-opacity1';

const collections=[['media_clips','media_',200],['text_clips','text_',2000]];
const ident=/^(media|text)_[0-9a-f]{32}$/, finite=Number.isFinite;
const refuse=issue=>({issue}), ns=n=>Math.round(n*1e9)/1e9;
const clockMatches=(value,expected)=>finite(value)&&finite(expected)&&Math.abs(value-ns(expected))<=5.1e-10;
const without=(object,keys)=>Object.fromEntries(Object.entries(object||{}).filter(([k])=>!keys.includes(k)));
function equal(a,b){
 if(a===b)return true;
 if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
 const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]));
}
function history(manual){
 if(!manual||typeof manual!=='object'||Array.isArray(manual))return null;
 if(!Object.hasOwn(manual,'history'))return {undo_count:0,redo_count:0};
 const h=manual.history;return h&&typeof h==='object'&&!Array.isArray(h)&&Object.keys(h).length===2&&['undo_count','redo_count'].every(k=>Object.hasOwn(h,k)&&Number.isInteger(h[k])&&h[k]>=0&&h[k]<=20)?h:null;
}
function retained(row,isMedia){
 const omit=['id','start','end'];if(isMedia)omit.push('source_start','video_source_start','fade_in','fade_out');
 const fields=without(row,omit);fields.enabled=Object.hasOwn(row,'enabled')?row.enabled:true;
 if(isMedia)fields.opacity_percent=Object.hasOwn(row,'opacity_percent')?row.opacity_percent:100;
 else{fields.template=Object.hasOwn(row,'template')?row.template:'plain';fields.subtext=Object.hasOwn(row,'subtext')?row.subtext:'';}
 return fields;
}
export function planGroupJoin(project,ids){
 const fps=project?.settings?.fps,duration=project?.editor_sequence?.duration;
 if(!project?.id||!project.draft||!Number.isInteger(project.revision)||project.revision<1||project.editor_sequence?.error||!finite(duration)||duration<=0||![24,25,30,50,60].includes(fps))return refuse('Open a saved edit with a supported output frame rate.');
 if(!history(project.manual))return refuse('The saved Undo history is invalid. Reopen a compatible edit before joining.');
 if(!Array.isArray(ids)||ids.length!==2||ids[0]===ids[1]||ids.some(s=>typeof s!=='string'||!ident.test(s)))return refuse('Choose exactly two different saved media occurrences or titles.');
 const state=layerTrackState(project);if(state.issue)return refuse(state.issue);
 const selected=new Set(ids),found=[],seen=new Set();
 for(const [key,prefix,limit]of collections){
   const rows=project.manual?.[key]??[];if(!Array.isArray(rows)||rows.length>limit)return refuse('The saved layer collection is invalid.');
   for(let index=0;index<rows.length;index++){
     const row=rows[index];if(!row||typeof row.id!=='string'||!ident.test(row.id)||!row.id.startsWith(prefix)||seen.has(row.id))return refuse('The saved timeline contains an ambiguous occurrence. Reopen before joining.');seen.add(row.id);
     if(selected.has(row.id))found.push({row,index,key});
   }
 }
 if(found.length!==2)return refuse('A selected occurrence is no longer in this saved edit.');
 if(found[0].key!==found[1].key)return refuse('A through edit joins two parts of the same source or two matching static titles, not a mixed selection.');
 if(found.some(({row:r})=>!finite(r.start)||!finite(r.end)||r.start<0||r.end>duration||r.end-r.start<.08-1e-9))return refuse('A selected occurrence has invalid saved bounds.');
 found.sort((a,b)=>a.row.start-b.row.start);const [{row:left,index,key},{row:right,index:ri}]=found,isMedia=key==='media_clips';
 if(left.end!==right.start||right.end<=left.end)return refuse('The pieces must touch exactly, with no gap or overlap.');
 if(ri!==index+1)return refuse('Another saved occurrence sits between these pieces in stacking order. Joining could change the picture.');
 const frame=Math.round(left.end*fps);
 const legacyTitle=!isMedia&&[left,right].every(r=>r.kind==='title'&&['plain','lower_third','callout','highlight'].includes(r.template??'plain'))&&left.end===Math.round(frame/fps*1e6)/1e6;
 if(!Number.isSafeInteger(frame)||Math.abs(left.end-frame/fps)>5.1e-10&&!legacyTitle)return refuse('The cut is not on an output frame. Its timing will not be rounded to make a join.');
 if([left,right].some(r=>Object.hasOwn(r,'enabled')&&typeof r.enabled!=='boolean'))return refuse('A selected occurrence has invalid saved availability.');
 if(left.track_id!==right.track_id)return refuse('The two pieces must be on the same saved track.');
 const track=state.tracks.find(t=>t.id===left.track_id);
 if(track?.locked)return refuse('Unlock '+track.name+' before joining. No cut was removed.');
 const joined={...left,end:right.end};
 if(isMedia){
   if(left.asset_id!==right.asset_id)return refuse('These are different original files; matching names are not enough.');
   const a=project.assets?.[left.asset_id];if(!a||typeof left.asset_id!=='string'||a.id!==left.asset_id||a.status!=='ready'||!['audio','image','video'].includes(a.kind))return refuse('Both pieces need the same ready original.');
   if(left.motion!=='none'||right.motion!=='none')return refuse('Joining a pan or zoom could change its motion. Use static pieces instead.');
   if(![left.fade_in,left.fade_out,right.fade_in,right.fade_out,left.speed,right.speed,left.source_start,right.source_start].every(finite)||left.speed<=0||right.speed<=0)return refuse('A selected clip has invalid saved playback controls.');
   for(const row of [left,right]){
     const len=row.end-row.start;
     if(row.fade_in<0||row.fade_out<0||row.fade_in+row.fade_out>len+1e-8||row.source_start<0||row.speed<.25||row.speed>4||a.kind!=='video'&&row.speed!==1||
       a.kind!=='image'&&(!finite(a.duration)||row.source_start+len>a.duration+1e-8)||
       a.kind==='video'&&Object.hasOwn(row,'video_source_start')&&(!finite(row.video_source_start)||row.video_source_start<0||row.video_source_start>57600))return refuse('A selected piece exceeds its saved media timing or source bounds.');
     if(Object.hasOwn(row,'opacity_percent')&&(a.kind==='audio'||!Number.isInteger(row.opacity_percent)||row.opacity_percent<0||row.opacity_percent>100))return refuse('A selected piece has invalid saved opacity.');
   }
   if(left.fade_out!==0||right.fade_in!==0)return refuse('A fade faces this cut. Joining would remove that sound change.');
   const elapsed=left.end-left.start;
   if(a.kind!=='image'&&!clockMatches(right.source_start,left.source_start+elapsed))return refuse('The original sound/source time is not continuous across this cut.');
   if(a.kind==='image'&&left.source_start!==right.source_start)return refuse('The still-image source settings differ.');
   if(a.kind==='video'&&!clockMatches(right.video_source_start??right.source_start,(left.video_source_start??left.source_start)+elapsed*left.speed))return refuse('The independent picture time is not continuous across this cut.');
   if(a.kind!=='video'&&left.video_source_start!==right.video_source_start)return refuse('The saved source settings differ.');
   joined.fade_out=right.fade_out;
 }else{
   if(left.kind!=='title'||right.kind!=='title')return refuse('Custom captions keep their individual subtitle cues. Join static titles or imported media only.');
   if(left.template==='chapter'||right.template==='chapter')return refuse('Chapter titles have a built-in fade, so this join would change their appearance.');
 }
 if(!equal(retained(left,isMedia),retained(right,isMedia)))return refuse('The halves differ in appearance, sound, enabled state or other saved settings.');
 return {issue:'',left:left.id,right:right.id,key,index,frame,fps,seam:left.end,joined};
}
export function verifyGroupJoin(before,after,ids){
 const p=planGroupJoin(before,ids);if(p.issue)return p;
 if(!after||after.id!==before.id||after.revision!==before.revision+1)return refuse('The saved join belongs to a different project or revision.');
 const a=history(before.manual),b=history(after.manual);
 if(!a||!b||!Object.hasOwn(after.manual,'history')||b.undo_count!==Math.min(20,a.undo_count+1)||b.redo_count!==0)return refuse('The save did not confirm a single Undo step.');
 for(const key of ['name','settings','sources','assets','analysis','editor_sequence','exports','review_markers'])if(!equal(before[key],after[key]))return refuse('Another part of the project changed in the join response.');
 if(!equal(without(before.draft,['edited_at','status']),without(after.draft,['edited_at','status']))||after.draft?.status!==before.draft?.status&&after.draft?.status!=='ready')return refuse('The joined edit changed other draft content.');
 if(!equal(without(before.manual,['history','_history','media_clips','text_clips']),without(after.manual,['history','_history','media_clips','text_clips'])))return refuse('The joined edit changed another track or setting.');
 for(const [key]of collections){
   const old=before.manual[key]||[],expected=key===p.key?[...old.slice(0,p.index),p.joined,...old.slice(p.index+2)]:old;
   if(!equal(expected,after.manual?.[key]||[]))return refuse('The joined occurrence, source clocks, controls or an unrelated clip did not match the displayed edit.');
 }
 return {issue:'',left:p.left,right:p.right,frame:p.frame};
}
