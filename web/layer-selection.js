// Temporary imported-media/custom-text selection. No source tracks or persistent groups.
export function planLayerGroupMove(project, clipIds, delta) {
  const blocked = issue => ({issue, delta:null, patches:null});
  if (!project?.draft || project?.editor_sequence?.error) return blocked(project?.editor_sequence?.error || "Open an edit before moving selected clips.");
  if (!Array.isArray(clipIds) || clipIds.length < 2 || clipIds.length > 200 || clipIds.some(id => typeof id !== "string" || !/^(media|text)_[0-9a-f]{32}$/.test(id)) || new Set(clipIds).size !== clipIds.length)
    return blocked("Select between 2 and 200 distinct imported media or custom text clips.");
  if (typeof delta !== "number" || !Number.isFinite(delta) || Math.abs(delta)>604800) return blocked("Choose a finite time shift for the selection.");
  const duration = Number(project.editor_sequence?.duration ?? project.draft.output_duration);
  if (!Number.isFinite(duration) || duration <= 0) return blocked("The edited timeline duration is unavailable. Reload the project.");
  const media = project.manual?.media_clips || [], text = project.manual?.text_clips || [];
  if (!Array.isArray(media) || !Array.isArray(text)) return blocked("The saved layers are invalid. Reload the project.");
  const all = [...media, ...text];
  if (all.some(row => !row || typeof row !== "object" || typeof row.id !== "string") || new Set(all.map(row => row.id)).size !== all.length)
    return blocked("The saved layers contain invalid or duplicate identities. Reload the project.");
  const byId = new Map(all.map(row => [row.id, row])), patches = [];
  for (const id of clipIds) {
    const clip = byId.get(id), isText = id.startsWith("text_");
    if (!clip || !(isText ? text : media).includes(clip)) return blocked("A selected clip is no longer available. Select the clips again.");
    if (![clip.start,clip.end].every(value => typeof value === "number" && Number.isFinite(value)) || clip.end-clip.start < .08-1e-9)
      return blocked("A selected clip has invalid saved timing. Reload the project.");
    if (!isText) {
      const asset=project.assets?.[clip.asset_id];
      if (!asset || asset.status !== "ready" || !["video","audio","image"].includes(asset.kind)) return blocked("Selected media is not ready. Prepare it before moving the selection.");
    }
    const precision=isText?1e6:1e9, start=delta===0?clip.start:Math.round((clip.start+delta)*precision)/precision, end=delta===0?clip.end:Math.round((clip.end+delta)*precision)/precision;
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > duration || end-start < .08-1e-9)
      return blocked("Keep the whole selection inside the edited timeline. No clip will be shortened or individually clamped.");
    patches.push({clip_id:id,start,end});
  }
  const moved=new Map(patches.map(row=>[row.clip_id,row]));
  const events=text.flatMap(row=>{const p=moved.get(row.id)||row;return [[p.start,1],[p.end,-1]];}).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  let count=0;
  for(const [at,change] of events){if(!Number.isFinite(at))return blocked("The saved text timing is invalid. Reload the project.");if((count+=change)>16)return blocked("At most 16 custom text clips may overlap, including disabled clips. Choose another position.");}
  return {issue:"",delta,patches:patches.every(row=>row.start===byId.get(row.clip_id).start&&row.end===byId.get(row.clip_id).end)?[]:patches};
}

// Removing saved occurrences needs identity, not ready media or valid move timing.
// Keep all survivor data untouched; the server is the authoritative transaction.
export function planLayerGroupRemove(project, clipIds) {
  const blocked=issue=>({issue,clip_ids:null});
  if(!project?.draft || project?.editor_sequence?.error)return blocked(project?.editor_sequence?.error || "Open an edit before removing selected clips.");
  if(!Array.isArray(clipIds) || clipIds.length<2 || clipIds.length>200
    || clipIds.some(id=>typeof id!=="string" || !/^(media|text)_[0-9a-f]{32}$/.test(id)) || new Set(clipIds).size!==clipIds.length)
    return blocked("Select between 2 and 200 distinct imported media or custom text clips.");
  const duration=Number(project.editor_sequence?.duration ?? project.draft.output_duration);
  if(!Number.isFinite(duration) || duration<=0)return blocked("The edited timeline duration is unavailable. Reload the project.");
  const known=new Set();
  for(const [key,prefix,limit] of [["media_clips","media_",200],["text_clips","text_",2000]]){
    const rows=project.manual?.[key] ?? [];
    if(!Array.isArray(rows) || rows.length>limit)return blocked("The saved timeline layer list is invalid. Reload the project.");
    for(const row of rows){
      if(!row || typeof row!=="object" || typeof row.id!=="string" || !row.id.startsWith(prefix)
        || !/^(media|text)_[0-9a-f]{32}$/.test(row.id) || known.has(row.id))return blocked("The saved layers contain invalid or duplicate identities. Reload the project.");
      known.add(row.id);
    }
  }
  if(clipIds.some(id=>!known.has(id)))return blocked("A selected clip is no longer available. Select the clips again.");
  return {issue:"",clip_ids:[...clipIds]};
}

// Isolated validation keeps this temporary-selection module usable without imports.
function duplicateTrackState(project) {
const TRACK_ID = /^track_[0-9a-f]{32}$/;
const CLIP_ID = /^(media|text)_[0-9a-f]{32}$/;
const TRACK_KINDS = new Set(['visual', 'audio', 'text']);
const overlap = (a, b) => Math.min(a.end, b.end) - Math.max(a.start, b.start) > 1e-8;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exactKeys = (value, keys) => record(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

function layerTrackKind(project, clip) {
  if (typeof clip?.id !== 'string') return null;
  if (clip.id.startsWith('text_')) return 'text';
  const kind = project?.assets?.[clip.asset_id]?.kind;
  return kind === 'audio' ? 'audio' : ['video', 'image'].includes(kind) ? 'visual' : null;
}

function layerTrackState(project) {
  const manual = project?.manual || {}, present = Object.hasOwn(manual, 'layer_tracks');
  const fail = issue => ({enabled:present, issue, tracks:[]});
  if (!present) {
    for (const key of ['media_clips', 'text_clips']) {
      if (Array.isArray(manual[key]) && manual[key].some(row => record(row) && Object.hasOwn(row, 'track_id')))
        return fail('Layer membership has no saved track model. Reload a compatible project before editing.');
    }
    return {enabled:false, issue:'', tracks:[]};
  }
  const model = manual.layer_tracks;
  if (!record(model) || ![1, 2, 3].includes(model.version)
    || !exactKeys(model, model.version === 3 ? ['version', 'tracks', 'protection_version'] : ['version', 'tracks'])
    || model.version === 3 && ![1, 2].includes(model.protection_version)
    || !Array.isArray(model.tracks) || model.tracks.length > 4096)
    return fail('Unsupported or malformed layer tracks. Open this project in a compatible CUTROOM version.');
  const tracks = new Map();
  for (const track of model.tracks) {
    const keys = ['id', 'kind', 'name', ...(model.version >= 2 ? ['locked'] : []), ...(model.version === 3 && track?.kind !== 'text' ? ['audio'] : [])];
    if (!exactKeys(track, keys) || model.version >= 2 && typeof track.locked !== 'boolean'
      || model.version === 3 && (model.protection_version === 1 && track.locked || track.kind !== 'text'
        && (!exactKeys(track.audio, ['gain_db', 'muted']) || !Number.isFinite(track.audio.gain_db)
          || track.audio.gain_db < -60 || track.audio.gain_db > 12 || typeof track.audio.muted !== 'boolean'))
      || typeof track.id !== 'string' || !TRACK_ID.test(track.id)
      || tracks.has(track.id) || !TRACK_KINDS.has(track.kind) || typeof track.name !== 'string'
      || track.name !== track.name.trim() || !track.name.length || [...track.name].length > 80)
      return fail('The saved track list contains an invalid name, kind or identity. Reload the project.');
    tracks.set(track.id, track);
  }
  const duration = project?.editor_sequence?.duration ?? manual.sequence?.duration ?? project?.draft?.output_duration;
  if (project?.editor_sequence?.error || !Number.isFinite(duration) || duration < 0)
    return fail('The edited duration is unavailable. Reload the project before using tracks.');
  const ids = new Set(), occupied = new Map(), textEvents = [];
  for (const [key, prefix, limit] of [['media_clips', 'media_', 200], ['text_clips', 'text_', 2000]]) {
    const rows = Object.hasOwn(manual, key) ? manual[key] : [];
    if (!Array.isArray(rows) || rows.length > limit) return fail('The saved layer list is invalid. Reload the project.');
    for (const clip of rows) {
      if (!record(clip) || typeof clip.id !== 'string' || !CLIP_ID.test(clip.id) || !clip.id.startsWith(prefix) || ids.has(clip.id))
        return fail('The saved clips contain an invalid or duplicate identity. Reload the project.');
      ids.add(clip.id);
      if (![clip.start, clip.end].every(Number.isFinite) || clip.start < 0 || clip.end <= clip.start || clip.end > duration + 1e-8)
        return fail('A saved clip has invalid timing or extends beyond the edit.');
      const kind = layerTrackKind(project, clip), track = tracks.get(clip.track_id);
      if (!kind) return fail('A clip has no known asset kind. Restore its asset before using tracks.');
      if (!track || track.kind !== kind) return fail('Each clip must belong to an existing compatible track.');
      const lane = occupied.get(track.id) || [];
      if (lane.some(other => overlap(clip, other)))
        return fail(`Clips on “${track.name}” cannot overlap, including disabled clips. Choose an empty destination or another track.`);
      lane.push(clip); occupied.set(track.id, lane);
      if (kind === 'text') textEvents.push([clip.start, 1], [clip.end, -1]);
    }
  }
  let simultaneous = 0;
  for (const [, delta] of textEvents.sort((a, b) => a[0] - b[0] || a[1] - b[1]))
    if ((simultaneous += delta) > 16) return fail('At most 16 custom text clips may overlap, including disabled clips.');
  return {enabled:true, issue:'', tracks:model.tracks};
}


return layerTrackState(project);
}

function duplicateEqual(a,b) {
  if(a===b)return true;
  if(!a || !b || typeof a!=='object' || typeof b!=='object' || Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a);return keys.length===Object.keys(b).length && keys.every(key=>Object.hasOwn(b,key)&&duplicateEqual(a[key],b[key]));
}
function duplicateGroupContext(project,ids,start) {
  if(!project?.draft || typeof project.draft!=='object' || Array.isArray(project.draft))return {issue:'Open a valid saved edit before copying selected clips.'};
  const base=planLayerGroupRemove(project,ids);
  if(base.issue)return {issue:base.issue};
  const duration=project.editor_sequence?.duration ?? project.draft.output_duration;
  if(!Number.isFinite(start)||start<0||start>duration)return {issue:'Choose a finite copy position inside the edit.'};
  const state=duplicateTrackState(project);
  if(state.issue)return {issue:state.issue};
  const media=project.manual?.media_clips||[],text=project.manual?.text_clips||[], selected=new Set(ids);
  const kind=row=>row.id.startsWith('text_')?'text':project.assets?.[row.asset_id]?.kind==='audio'?'audio':'visual';
  const rank=new Map(state.tracks.map((track,index)=>[track.id,index]));
  const selectedMedia=media.filter(row=>selected.has(row.id)),selectedText=text.filter(row=>selected.has(row.id));
  if(media.length+selectedMedia.length>200 || text.length+selectedText.length>2000)return {issue:'Copying this selection would exceed the media or custom text clip limit.'};
  const originals=[...selectedMedia,...selectedText];
  for(const row of originals){
    if(![row.start,row.end].every(Number.isFinite)||row.start<0||row.end>duration||row.end-row.start<.08-1e-9)return {issue:'A selected clip has invalid saved timing. Reload the project.'};
    if(!row.id.startsWith('text_')){
      const asset=project.assets?.[row.asset_id];
      if(!asset||asset.status!=='ready'||!['video','audio','image'].includes(asset.kind))return {issue:'Prepare every selected media file before copying the selection.'};
    }
  }
  const delta=start-Math.min(...originals.map(row=>row.start));
  const copies=originals.map(row=>{const factor=row.id.startsWith('text_')?1e6:1e9;return {source_id:row.id,start:delta===0?row.start:Math.round((row.start+delta)*factor)/factor,end:delta===0?row.end:Math.round((row.end+delta)*factor)/factor};});
  if(copies.some(row=>row.start<0||row.end>duration||row.end-row.start<.08-1e-9))return {issue:'Keep the entire copy inside the edit. No clip will be shortened, clamped or ripple the timeline.'};
  const events=[...text,...copies.filter(row=>row.source_id.startsWith('text_'))].flatMap(row=>[[row.start,1],[row.end,-1]]).sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  let count=0;
  for(const [time,change] of events){if(!Number.isFinite(time))return {issue:'The saved text timing is invalid.'};if((count+=change)>16)return {issue:'At most 16 custom text clips may overlap, including disabled clips.'};}
  // Simulate the server Automatic allocator only for this synchronous plan.
  // New symbolic lanes never become saved IDs and originals, including locks, remain untouched.
  const tracks=state.tracks.map(row=>({...row})),prior=[...media,...text].map(row=>({...row,kind:kind(row)})),lanes=[];
  const overlaps=(a,b)=>Math.min(a.end,b.end)-Math.max(a.start,b.start)>1e-8;
  const allocationOrder=originals.map((_,index)=>index);
  if(state.enabled){
    const visualOrder=allocationOrder.filter(i=>kind(originals[i])==='visual').sort((a,b)=>rank.get(originals[a].track_id)-rank.get(originals[b].track_id));
    const textOrder=allocationOrder.filter(i=>kind(originals[i])==='text').sort((a,b)=>rank.get(originals[a].track_id)-rank.get(originals[b].track_id));
    let visualIndex=0,textIndex=0;
    allocationOrder.forEach((i,at)=>{const type=kind(originals[i]);if(type==='visual')allocationOrder[at]=visualOrder[visualIndex++];else if(type==='text')allocationOrder[at]=textOrder[textIndex++];});
  }
  if(state.enabled)for(const index of allocationOrder){
    const copy=copies[index],type=kind(originals[index]),compatible=tracks.filter(row=>row.kind===type);
    const mixed=project.manual.layer_tracks.version===3 && type!=='text';
    const sourceAudio=mixed ? state.tracks.find(row=>row.id===originals[index].track_id).audio : null;
    const ranks=new Map(compatible.map((row,i)=>[row.id,i]));
    const floor=type==='audio'?0:Math.max(0,...prior.filter(row=>row.kind===type&&overlaps(row,copy)).map(row=>ranks.get(row.track_id)+1));
    let lane=compatible.find((row,i)=>i>=floor&&!row.locked&&(!mixed||duplicateEqual(row.audio,sourceAudio))&&!prior.some(old=>old.track_id===row.id&&overlaps(old,copy)));
    if(!lane){
      if(tracks.length>=4096)return {issue:'No unlocked automatic destination is available within the 4096-track limit.'};
      lane={id:`new:${tracks.length}`,kind:type,locked:false,...(mixed?{audio:{...sourceAudio}}:{})};tracks.push(lane);
    }
    lanes[index]=lane.id;prior.push({...copy,kind:type,track_id:lane.id});
  }
  return {issue:'',start,delta,copies,originals,state,tracks,lanes};
}

export function planLayerGroupDuplicate(project,ids,start) {
  const result=duplicateGroupContext(project,ids,start);
  return result.issue?{issue:result.issue,start:null,delta:null,copies:null}:{issue:'',start:result.start,delta:result.delta,copies:result.copies};
}

// Verify a response-only, transaction-authored mapping. Never guess a new ID by
// asset, timestamp, array tail or resemblance to another copy.
export function verifyLayerGroupDuplicate(before,after,ids,start,created) {
  const blocked=issue=>({issue,clip_ids:null,mapping:null});
  const plan=duplicateGroupContext(before,ids,start);
  if(plan.issue)return blocked(plan.issue);
  if(!before?.id || after?.id!==before.id || !Number.isInteger(before.revision)||!Number.isInteger(after.revision)||before.revision<0||after.revision<=before.revision)return blocked('The copy receipt belongs to a different or stale project. Reload before editing.');
  if(!Array.isArray(created)||created.length!==ids.length)return blocked('The copy receipt is incomplete. Reload before editing.');
  const mapping={},newIds=new Set(),oldIds=new Set([...(before.manual?.media_clips||[]),...(before.manual?.text_clips||[])].map(row=>row.id));
  for(const entry of created){
    if(!entry||typeof entry!=='object'||Array.isArray(entry)||Object.keys(entry).length!==2||!Object.hasOwn(entry,'source_id')||!Object.hasOwn(entry,'clip_id')||!ids.includes(entry.source_id)||Object.hasOwn(mapping,entry.source_id)||typeof entry.clip_id!=='string'||!/^(media|text)_[0-9a-f]{32}$/.test(entry.clip_id)||entry.clip_id.split('_')[0]!==entry.source_id.split('_')[0]||oldIds.has(entry.clip_id)||newIds.has(entry.clip_id))return blocked('The copy receipt contains invalid or repeated clip identities.');
    mapping[entry.source_id]=entry.clip_id;newIds.add(entry.clip_id);
  }
  const state=duplicateTrackState(after);
  if(state.issue||state.enabled!==plan.state.enabled)return blocked(state.issue||'The copy unexpectedly changed the track model.');
  for(const key of ['name','settings','sources','assets','analysis','editor_sequence'])if(!duplicateEqual(before[key],after[key]))return blocked('The copy unexpectedly changed existing project content. Reload before editing.');
  // Structural edits stamp edited_at and make the draft ready. No render
  // field, candidate content or source timing is exempt from verification.
  const draftContent=draft=>Object.fromEntries(Object.entries(draft||{}).filter(([key])=>!['edited_at','status'].includes(key)));
  if(!duplicateEqual(draftContent(before.draft),draftContent(after.draft)) || after.draft?.status!==before.draft?.status && after.draft?.status!=='ready')return blocked('The copy unexpectedly changed the saved draft.');
  const omitLayers=manual=>Object.fromEntries(Object.entries(manual||{}).filter(([key])=>!['media_clips','text_clips','layer_tracks','history','_history'].includes(key)));
  if(!duplicateEqual(omitLayers(before.manual),omitLayers(after.manual)))return blocked('The copy unexpectedly changed existing edit controls.');
  if(state.enabled){
    const old=plan.state.tracks;
    if(after.manual.layer_tracks.version!==before.manual.layer_tracks.version||after.manual.layer_tracks.protection_version!==before.manual.layer_tracks.protection_version||state.tracks.length!==plan.tracks.length||!old.every((row,i)=>duplicateEqual(row,state.tracks[i])))return blocked('The copy changed existing tracks or returned unexpected destinations.');
    for(let i=old.length;i<state.tracks.length;i++)if(state.tracks[i].kind!==plan.tracks[i].kind||state.tracks[i].locked===true||!duplicateEqual(state.tracks[i].audio,plan.tracks[i].audio))return blocked('The new copy destination is incompatible or locked.');
  }
  for(const key of ['media_clips','text_clips']){
    const old=before.manual?.[key]||[],rows=after.manual?.[key] ?? [];
    const expected=plan.copies.filter(row=>row.source_id.startsWith(key==='media_clips'?'media_':'text_'));
    if(!Array.isArray(rows)||rows.length!==old.length+expected.length||!old.every((row,i)=>duplicateEqual(row,rows[i])))return blocked('The copy changed an original occurrence or returned extra clips.');
    for(let i=0;i<expected.length;i++){
      const copy=expected[i],index=plan.copies.indexOf(copy),original=plan.originals[index],row=rows[old.length+i];
      const desired={...original,id:mapping[copy.source_id],start:copy.start,end:copy.end};delete desired.track_id;
      if(state.enabled){const lane=plan.lanes[index];desired.track_id=lane.startsWith('new:')?state.tracks[Number(lane.slice(4))].id:lane;}
      if(!duplicateEqual(desired,row))return blocked('A copied occurrence does not match its original content, timing or destination.');
    }
  }
  return {issue:'',clip_ids:ids.map(id=>mapping[id]),mapping};
}
