import { layerTrackState } from './layer-tracks.js?v=20261116-track-levels2';

const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const equal = (a,b) => a===b || Boolean(record(a)||Array.isArray(a)) && Boolean(record(b)||Array.isArray(b)) && Array.isArray(a)===Array.isArray(b) && Object.keys(a).length===Object.keys(b).length && Object.keys(a).every(key=>Object.hasOwn(b,key)&&equal(a[key],b[key]));
const mediaId = /^media_[0-9a-f]{32}$/;
const finite = (value,low,high) => typeof value==='number' && Number.isFinite(value) && value>=low && value<=high;
const fail = issue => ({issue,frame:null,patches:null,changedIds:null});
function publicHistoryCounts(manual) {
    if(!record(manual))return null;
    if(!Object.hasOwn(manual,'history'))return {undo_count:0,redo_count:0};
    const value=manual.history;
    return record(value)&&Object.keys(value).length===2&&['undo_count','redo_count'].every(key=>Object.hasOwn(value,key)&&Number.isInteger(value[key])&&value[key]>=0&&value[key]<=20)?value:null;
}

function frameOf(row) {
  if(!['x','y','w','h'].every(key=>finite(row[key],(key==='w'||key==='h')?.01:0,1)) || row.x+row.w>1+1e-8 || row.y+row.h>1+1e-8)return null;
  const fit=Object.hasOwn(row,'fit')?row.fit:'cover';
  return ['cover','contain'].includes(fit)?{x:row.x,y:row.y,w:row.w,h:row.h,fit}:null;
}
function selectedRowIssue(row,asset,duration) {
  if(!record(asset)||asset.status!=='ready'||!['image','video'].includes(asset.kind))return 'Choose ready imported images or videos only.';
  const bounds={start:[0,duration],end:[0,duration],source_start:[0,14400],speed:[.25,4],volume_db:[-60,12],fade_in:[0,duration],fade_out:[0,duration]};
  if(Object.entries(bounds).some(([key,[low,high]])=>!finite(row[key],low,high)))return 'A selected visual has invalid saved timing, sound or source values.';
  // Validate detached values only; never write rounded clocks or defaults back.
  const rounded=key=>Math.round(row[key]*1e9)/1e9,length=rounded('end')-rounded('start');
  if(length<.08-1e-9 || asset.kind!=='video'&&rounded('speed')!==1 || rounded('fade_in')+rounded('fade_out')>length+1e-8)return 'A selected visual has invalid saved duration, speed or fades.';
  if(asset.kind==='video'&&(!finite(asset.duration,0,14400)||rounded('source_start')+length>asset.duration+1e-8 || Object.hasOwn(row,'video_source_start')&&!finite(row.video_source_start,0,57600)))return 'A selected video has an invalid saved source clock.';
  if(['muted','audio_enabled'].some(key=>typeof row[key]!=='boolean') || Object.hasOwn(row,'enabled')&&typeof row.enabled!=='boolean' || !['music','effects','voice'].includes(row.role) || !['none','zoom_in','pan'].includes(row.motion))return 'A selected visual has invalid saved playback controls.';
  return frameOf(row)?'':'A selected visual has invalid saved framing.';
}

export function planLayerGroupFrame(project,ids,referenceId) {
  if(!record(project)||!record(project.draft)||!record(project.manual)||project.editor_sequence?.error)return fail('Open a valid saved edit before matching framing.');
  if(!publicHistoryCounts(project.manual))return fail('The saved Undo history counts are invalid. Reopen a compatible saved edit before matching framing.');
  if(!Array.isArray(ids)||ids.length<2||ids.length>200||ids.some(id=>typeof id!=='string'||!mediaId.test(id))||new Set(ids).size!==ids.length)return fail('Select 2 to 200 distinct imported visuals.');
  if(typeof referenceId!=='string'||!ids.includes(referenceId))return fail('Choose a saved reference from this selection.');
  const state=layerTrackState(project);if(state.issue)return fail(state.issue);
  const duration=project.editor_sequence?.duration??project.manual.sequence?.duration??project.draft.output_duration;
  if(!finite(duration,0,86400))return fail('The edited duration is unavailable.');
  for(const [key,prefix,limit] of [['media_clips','media',200],['text_clips','text',2000]]) {
    const rows=Object.hasOwn(project.manual,key)?project.manual[key]:[];
    if(!Array.isArray(rows)||rows.length>limit||rows.some(row=>!record(row)||typeof row.id!=='string'||!(new RegExp(`^${prefix}_[0-9a-f]{32}$`)).test(row.id))||new Set(rows.map(row=>row.id)).size!==rows.length)return fail('The saved layer identities or list are invalid.');
  }
  const rows=project.manual.media_clips||[],wanted=new Set(ids),byId=new Map(rows.map(row=>[row.id,row])),tracks=new Map(state.tracks.map(track=>[track.id,track]));
  if(ids.some(id=>!byId.has(id)))return fail('A selected visual is no longer available. Select the group again.');
  for(const id of ids) {
    const row=byId.get(id),issue=selectedRowIssue(row,project.assets?.[row.asset_id],duration);if(issue)return fail(issue);
    if(id!==referenceId&&tracks.get(row.track_id)?.locked)return fail('Unlock every target track before matching framing. The reference may stay locked.');
  }
  const frame=frameOf(byId.get(referenceId)),patches=[];
  for(const row of rows) {
    if(!wanted.has(row.id)||row.id===referenceId)continue;
    const own=frameOf(row),patch={clip_id:row.id};
    for(const key of ['x','y','w','h'])if(row[key]!==frame[key])patch[key]=frame[key];
    if(own.fit!==frame.fit)patch.fit=frame.fit;
    if(Object.keys(patch).length>1)patches.push(patch);
  }
  return {issue:'',frame,patches,changedIds:patches.map(row=>row.clip_id)};
}

// Exact round(float, 9) for the nonnegative unit-interval geometry used by
// Python's detached binding validator. Do not use Math.round(x * 1e9): that
// multiplication can round a near-half value before the actual rounding step.
function bindingFrameNumber(value) {
  const bytes=new ArrayBuffer(8),view=new DataView(bytes);view.setFloat64(0,value,false);
  const bits=view.getBigUint64(0,false),exponent=Number((bits>>52n)&2047n);
  const significand=(bits&((1n<<52n)-1n))+(exponent?1n<<52n:0n);
  const power=(exponent?exponent-1023:1-1023)-52;
  let numerator=significand*1000000000n,denominator=1n;
  if(power>=0)numerator<<=BigInt(power);else denominator<<=BigInt(-power);
  let rounded=numerator/denominator;const remainder=numerator%denominator;
  if(remainder*2n>denominator || remainder*2n===denominator && rounded%2n===1n)rounded++;
  return Number(rounded)/1e9;
}
function expectedFrameBindings(before,expectedRows,changedIds) {
  const binding=structuredClone(before.timeline_bindings);
  if(!record(binding)||!Array.isArray(binding.clips))return binding;
  const changed=new Set(changedIds),rows=new Map(expectedRows.map(row=>[row.id,row]));
  for(const clip of binding.clips) {
    if(clip.collection!=='library'||!changed.has(clip.id))continue;
    const row=rows.get(clip.id);
    if(!record(clip.state))continue; // Exact comparison still rejects any repair.
    for(const key of ['x','y','w','h'])clip.state[key]=bindingFrameNumber(row[key]);
    clip.state.fit=Object.hasOwn(row,'fit')?row.fit:'cover';
  }
  return binding;
}

export function verifyLayerGroupFrame(before,after,ids,referenceId) {
  const plan=planLayerGroupFrame(before,ids,referenceId);if(plan.issue)return {issue:plan.issue};
  const bad=issue=>({issue});
  if(typeof before.id!=='string'||!before.id||!record(after)||after.id!==before.id||!Number.isInteger(before.revision)||before.revision<1||after.revision!==before.revision+(plan.patches.length?1:0))return bad('The framing response has a different project or unexpected revision. Reopen before retrying.');
  if(!plan.patches.length)return equal(before,after)?{issue:''}:bad('A no-op framing response changed saved content.');
  const priorHistory=publicHistoryCounts(before.manual),nextHistory=publicHistoryCounts(after.manual);
  if(!priorHistory||!nextHistory||!Object.hasOwn(after.manual,'history')||nextHistory.undo_count!==Math.min(20,priorHistory.undo_count+1)||nextHistory.redo_count!==0)return bad('The framing response did not confirm one Undo step and cleared Redo history.');
  const state=layerTrackState(after);if(state.issue)return bad(state.issue);
  for(const key of ['timeline_bindings','caption_preview']) {
    if(record(before[key])&&Object.hasOwn(before[key],'revision')) {
      if(before[key].revision!==before.revision||!record(after[key])||after[key].revision!==after.revision)return bad('A public projection belongs to another revision.');
    }
  }
  const patches=new Map(plan.patches.map(({clip_id,...patch})=>[clip_id,patch]));
  const expected=before.manual.media_clips.map(row=>({...row,...patches.get(row.id)}));
  if(!equal(expected,after.manual?.media_clips))return bad('The framing response changed an unexpected occurrence or field.');
  // Exact public-state comparison is narrowed only for known transaction metadata.
  if(Array.isArray(before.timeline_bindings?.clips)) {
    const originals=new Map(before.manual.media_clips.map(row=>[row.id,row]));
    for(const clip of before.timeline_bindings.clips) {
      if(clip.collection!=='library'||!plan.changedIds.includes(clip.id))continue;
      const original=originals.get(clip.id);
      if(!record(clip.state)||['x','y','w','h'].some(key=>clip.state[key]!==bindingFrameNumber(original[key]))||clip.state.fit!==(Object.hasOwn(original,'fit')?original.fit:'cover'))return bad('The saved library binding does not match its original framing. Reopen before matching.');
    }
  }
  const expectedBindings=expectedFrameBindings(before,expected,plan.changedIds);
  const normalize=(project,isBefore=false)=>{
    const copy=structuredClone(project);if(isBefore&&Object.hasOwn(before,'timeline_bindings'))copy.timeline_bindings=expectedBindings;delete copy.revision;delete copy.updated_at;
    for(const key of ['timeline_bindings','caption_preview'])if(record(copy[key])&&Object.hasOwn(before[key]||{},'revision'))delete copy[key].revision;
    if(record(copy.draft)){delete copy.draft.edited_at;delete copy.draft.status;}
    if(record(copy.manual)){delete copy.manual.history;delete copy.manual.media_clips;}
    return copy;
  };
  if(!record(after.draft)||after.draft.status!==before.draft.status&&after.draft.status!=='ready'||!equal(normalize(before,true),normalize(after)))return bad('The framing response changed other saved project content.');
  return {issue:''};
}
