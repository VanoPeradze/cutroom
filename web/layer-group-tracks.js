import { layerTrackState, layerTrackKind, layerTrackUpdateIssue } from './layer-tracks.js?v=20261116-track-levels2';
import { planLayerGroupMove } from './layer-selection.js?v=20261116-track-levels2';

const groupTrackEqual=(a,b)=>a===b||Boolean(a&&b&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(key=>Object.hasOwn(b,key)&&groupTrackEqual(a[key],b[key])));
export function planLayerGroupRelocate(project,ids,anchorId,trackId,delta){
  const blocked=issue=>({issue,delta:null,patches:null});
  if(!project?.draft||typeof project.draft!=='object'||Array.isArray(project.draft))return blocked('Open a valid saved edit before relocating a selection.');
  const state=layerTrackState(project);if(state.issue)return blocked(state.issue);
  if(!state.enabled)return blocked('Enable editable tracks before relocating a selection between tracks.');
  const move=planLayerGroupMove(project,ids,delta);if(move.issue)return blocked(move.issue);
  const rows=[...(project.manual.media_clips||[]),...(project.manual.text_clips||[])],byId=new Map(rows.map(row=>[row.id,row]));
  if(typeof anchorId!=='string'||!ids.includes(anchorId))return blocked('Choose an anchor occurrence from the selected group.');
  const anchor=byId.get(anchorId),kind=layerTrackKind(project,anchor);
  if(ids.some(id=>layerTrackKind(project,byId.get(id))!==kind))return blocked('Relocate one kind of track at a time: imported visuals, audio, or custom text.');
  const lanes=state.tracks.filter(track=>track.kind===kind),rank=new Map(lanes.map((track,index)=>[track.id,index]));
  if(typeof trackId!=='string'||!rank.has(trackId))return blocked('Choose an existing destination track of the same kind.');
  // Existing group movement validates every media occurrence, not just selected
  // ones. Report known unavailable dependencies instead of promising a save.
  for(const row of project.manual.media_clips||[]){
    const asset=project.assets?.[row.asset_id];
    if(!asset||asset.status!=='ready'||!['video','audio','image'].includes(asset.kind))return blocked('Prepare or restore the unavailable media in this edit before relocating the group.');
  }
  const offset=rank.get(trackId)-rank.get(anchor.track_id),timing=new Map(move.patches.map(patch=>[patch.clip_id,patch]));
  const patches=[];
  for(const id of ids){
    const row=byId.get(id),source=lanes[rank.get(row.track_id)],destination=lanes[rank.get(row.track_id)+offset];
    if(!destination)return blocked('The whole group must fit within the existing tracks. No tracks will be created or individually clamped.');
    if(source.locked||destination.locked)return blocked(`Track "${source.locked?source.name:destination.name}" is locked. Unlock the affected source or destination before relocating.`);
    const proposed=timing.get(id)||row;
    patches.push({clip_id:id,start:proposed.start,end:proposed.end,track_id:destination.id});
  }
  const issue=layerTrackUpdateIssue(project,patches);if(issue)return blocked(issue);
  return {issue:'',delta,patches:patches.every(p=>{const row=byId.get(p.clip_id);return row.start===p.start&&row.end===p.end&&row.track_id===p.track_id;})?[]:patches};
}

export function verifyLayerGroupRelocate(before,after,ids,anchorId,trackId,delta){
  const blocked=issue=>({issue}),plan=planLayerGroupRelocate(before,ids,anchorId,trackId,delta);if(plan.issue)return blocked(plan.issue);
  if(!before.id||after?.id!==before.id||!Number.isInteger(before.revision)||before.revision<0||!Number.isInteger(after.revision)||after.revision<before.revision||(plan.patches.length&&after.revision===before.revision))return blocked('The relocation response belongs to a different or stale project. Reload before editing.');
  const state=layerTrackState(after);if(state.issue)return blocked(state.issue);
  const patches=new Map(plan.patches.map(({clip_id,...patch})=>[clip_id,patch]));
  for(const key of ['media_clips','text_clips']){
    const expected=(before.manual?.[key]||[]).map(row=>({...row,...patches.get(row.id)}));
    if(!groupTrackEqual(expected,after.manual?.[key]??[]))return blocked('The relocated occurrences do not match the requested timing and tracks.');
  }
  const controls=manual=>Object.fromEntries(Object.entries(manual||{}).filter(([key])=>!['media_clips','text_clips','history','_history'].includes(key)));
  if(!groupTrackEqual(controls(before.manual),controls(after.manual)))return blocked('Relocation unexpectedly changed another edit control or the track model.');
  for(const key of ['name','settings','sources','assets','analysis','editor_sequence'])if(!groupTrackEqual(before[key],after[key]))return blocked('Relocation unexpectedly changed existing project content.');
  const draft=value=>Object.fromEntries(Object.entries(value||{}).filter(([key])=>!['edited_at','status'].includes(key)));
  if(!after.draft||typeof after.draft!=='object'||Array.isArray(after.draft)||!groupTrackEqual(draft(before.draft),draft(after.draft))||after.draft.status!==before.draft.status&&after.draft.status!=='ready')return blocked('Relocation unexpectedly changed the saved draft.');
  return {issue:''};
}
