// Persisted imported-layer tracks. A/B and automatic captions are separate systems.
const TRACK_ID = /^track_[0-9a-f]{32}$/;
const CLIP_ID = /^(media|text)_[0-9a-f]{32}$/;
const TRACK_KINDS = new Set(['visual', 'audio', 'text']);
const overlap = (a, b) => Math.min(a.end, b.end) - Math.max(a.start, b.start) > 1e-8;
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const exactKeys = (value, keys) => record(value) && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));

export function layerTrackKind(project, clip) {
  if (typeof clip?.id !== 'string') return null;
  if (clip.id.startsWith('text_')) return 'text';
  const kind = project?.assets?.[clip.asset_id]?.kind;
  return kind === 'audio' ? 'audio' : ['video', 'image'].includes(kind) ? 'visual' : null;
}

export function layerTrackState(project) {
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

// Canonical saved track levels. Old schemas are exactly unity. These are
// linear occurrence factors before the existing role buses, not new routing.
export function layerTrackLevels(project, state = layerTrackState(project)) {
  const levels = {};
  if (state.issue) return levels;
  for (const track of state.tracks) if (track.kind !== 'text')
    levels[track.id] = project?.manual?.layer_tracks?.version === 3 ? {...track.audio} : {gain_db:0, muted:false};
  return levels;
}

export function planLayerTrackAudio(project, trackId, patch) {
  const state = layerTrackState(project), blocked = issue => ({issue, patch:null, level:null});
  if (state.issue) return blocked(state.issue);
  if (!state.enabled) return blocked('Enable editable tracks before setting a named track level.');
  if (!project?.draft || typeof project.draft !== 'object' || Array.isArray(project.draft)) return blocked('Open a saved edit before changing track levels.');
  const track = state.tracks.find(row => row.id === trackId);
  if (!track || !['visual','audio'].includes(track.kind)) return blocked('Choose an existing visual or audio track. Original A/B sound uses its own mixer.');
  const keys = record(patch) ? Object.keys(patch) : [];
  if (!keys.length || keys.some(key => !['gain_db','muted'].includes(key))
    || Object.hasOwn(patch,'gain_db') && (!Number.isFinite(patch.gain_db) || patch.gain_db < -60 || patch.gain_db > 12)
    || Object.hasOwn(patch,'muted') && typeof patch.muted !== 'boolean')
    return blocked('Use a finite gain from -60 to +12 dB and a saved Mute on/off value.');
  const saved = layerTrackLevels(project,state)[trackId], level = {...saved,...patch};
  const changed = Object.fromEntries(keys.filter(key => patch[key] !== saved[key]).map(key => [key,patch[key]]));
  return {issue:'', patch:changed, level, upgrades:Object.keys(changed).length > 0 && project.manual.layer_tracks.version !== 3};
}

// Verify only the intentional mix/schema delta before accepting a live save.
export function verifyLayerTrackAudio(before, after, trackId, patch) {
  const equal=(a,b)=>a===b || a!==null&&b!==null&&typeof a==='object'&&typeof b==='object'
    && Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length
    && Object.keys(a).every(key=>Object.hasOwn(b,key)&&equal(a[key],b[key]));
  const plan=planLayerTrackAudio(before,trackId,patch), state=layerTrackState(after);
  if(plan.issue || state.issue)return plan.issue || state.issue;
  if(after?.id!==before?.id || !Number.isInteger(after?.revision) || !Number.isInteger(before?.revision)
    || after.revision<before.revision || Object.keys(plan.patch).length && after.revision<=before.revision)
    return 'The track level response belongs to a different or stale edit.';
  const old=before.manual.layer_tracks, model=after.manual.layer_tracks, changed=Object.keys(plan.patch).length>0;
  const expected=changed&&old.version!==3 ? {version:3,protection_version:old.version,tracks:old.tracks.map(row=>({...row,locked:row.locked===true,...(row.kind==='text'?{}:{audio:{gain_db:0,muted:false}})}))} : structuredClone(old);
  if(changed)expected.tracks.find(row=>row.id===trackId).audio=plan.level;
  if(!equal(expected,model))return 'The saved track level or protection does not match this change. Reload before retrying.';
  for(const key of ['settings','sources','assets','analysis'])if(!equal(before[key],after[key]))return 'The track mix response unexpectedly changed other project content.';
  const manual=value=>Object.fromEntries(Object.entries(value||{}).filter(([key])=>!['layer_tracks','history','_history'].includes(key)));
  if(!equal(manual(before.manual),manual(after.manual)))return 'The track mix response unexpectedly changed clip placement or content.';
  return '';
}

export function layerTrackSoundSummaries(project, levels = layerTrackLevels(project), state = layerTrackState(project)) {
  const result = {};
  if (state.issue) return result;
  for (const track of state.tracks) if (track.kind !== 'text') result[track.id] = {eligible:0,audible:0,disabled:0,clipMuted:0,roles:[]};
  for (const clip of project?.manual?.media_clips || []) {
    const summary = result[clip.track_id], asset = project.assets?.[clip.asset_id];
    if (!summary || !(asset?.kind === 'audio' || asset?.kind === 'video' && asset.has_audio && clip.audio_enabled)) continue;
    if (clip.enabled === false) { summary.disabled++; continue; }
    summary.eligible++;
    const role = clip.role || 'music'; if (!summary.roles.includes(role)) summary.roles.push(role);
    if (clip.muted) summary.clipMuted++;
    else if (!levels[clip.track_id]?.muted) summary.audible++;
  }
  return result;
}

// Compact occurrence ranks keep visual z-indices below the separate text/caption plane,
// even when a project has many persistent empty tracks. Audio iteration is never sorted.
export function layerTrackRanks(project) {
  const state = layerTrackState(project), visual = new Map(), text = new Map();
  if (state.issue) return {...state, visual, text};
  const media = project?.manual?.media_clips || [], texts = project?.manual?.text_clips || [];
  if (!state.enabled) {
    media.forEach((clip, index) => { if (clip?.id) visual.set(clip.id, index); });
    texts.forEach((clip, index) => { if (clip?.id) text.set(clip.id, index); });
  } else {
    const rank = new Map(state.tracks.map((track, index) => [track.id, index]));
    const ordered = rows => [...rows].sort((a, b) => rank.get(a.track_id) - rank.get(b.track_id));
    ordered(media.filter(clip => layerTrackKind(project, clip) === 'visual')).forEach((clip, index) => visual.set(clip.id, index));
    ordered(texts).forEach((clip, index) => text.set(clip.id, index));
  }
  return {...state, visual, text};
}

export function layerTrackUpdateIssue(project, patches) {
  const state = layerTrackState(project);
  if (state.issue || !state.enabled) return state.issue;
  if (!Array.isArray(patches)) return 'The proposed track placement is unavailable.';
  const protectedIssue = protectedPatchIssue(project, patches, state);
  if (protectedIssue) return protectedIssue;
  const changes = new Map(patches.map(({clip_id, ...patch}) => [clip_id, patch]));
  const manual = {...project.manual};
  for (const key of ['media_clips', 'text_clips']) manual[key] = (manual[key] || []).map(clip => ({...clip, ...changes.get(clip.id)}));
  return layerTrackState({...project, manual}).issue;
}

export function planLayerTrackMove(project, clipId, start, trackId) {
  const blocked = issue => ({issue, patch:null}), state = layerTrackState(project);
  if (state.issue) return blocked(state.issue);
  if (!state.enabled) return blocked('Enable editable tracks before assigning a clip to a track.');
  const text = typeof clipId === 'string' && clipId.startsWith('text_');
  const clip = project?.manual?.[text ? 'text_clips' : 'media_clips']?.find(row => row.id === clipId);
  if (!clip || !project?.draft) return blocked('The selected clip is no longer available. Select it again.');
  const destination = state.tracks.find(track => track.id === trackId);
  if (!destination || destination.kind !== layerTrackKind(project, clip))
    return blocked('Choose a compatible imported visual, audio or custom-text track. A/B and automatic captions are separate.');
  if (!Number.isFinite(start) || start < 0) return blocked('Keep the whole clip inside the edited timeline.');
  const moved = start !== clip.start;
  const precision = text ? 1e6 : 1e9, end = moved ? Math.round((start + clip.end - clip.start) * precision) / precision : clip.end;
  if (end - start < .08 - 1e-9) return blocked('Keep at least 0.08 seconds in the selected clip.');
  if (moved && !text && project.assets?.[clip.asset_id]?.status !== 'ready')
    return blocked('Prepare the selected media before changing its timeline position. Track-only assignment does not require a ready preview.');
  const patch = {start, end, track_id:trackId}, issue = layerTrackUpdateIssue(project, [{clip_id:clipId, ...patch}]);
  if (issue) return blocked(issue);
  return {issue:'', patch:!moved && clip.track_id === trackId ? {} : patch};
}

// Creation placement is different from moving an existing occurrence: Insert
// opens time on every lane before checking the chosen destination. A requested
// lane is an exact intent, never a suggestion to the automatic allocator.
function libraryTrackPlacement(project, assetId, requestedStart, options, state) {
  const blocked = issue => ({issue});
  if (state.issue) return blocked(state.issue);
  const {append = false, insert = false, sourceStart = 0} = options;
  const explicit = Object.hasOwn(options, 'trackId');
  if (typeof append !== 'boolean' || typeof insert !== 'boolean' || append && insert)
    return blocked('Choose Add, Insert or Append for this placement.');
  const asset = project?.assets?.[assetId];
  const duration = project?.editor_sequence?.duration ?? project?.manual?.sequence?.duration ?? project?.draft?.output_duration;
  if (!project?.draft || !Number.isFinite(duration) || duration < 0)
    return blocked('Open a valid edit before placing media.');
  if (!asset || asset.status !== 'ready' || !['video', 'image', 'audio'].includes(asset.kind))
    return blocked('Choose a ready imported media file.');
  if ((append || insert) && asset.kind !== 'video') return blocked('Only video can insert or append time.');
  if ((project.manual?.media_clips?.length || 0) >= 200) return blocked('This edit already contains 200 media clips.');
  if (asset.kind !== 'image' && (!Number.isFinite(asset.duration) || asset.duration < .08))
    return blocked('This media has no usable source duration.');
  const sourceEnd = Object.hasOwn(options, 'sourceEnd') ? options.sourceEnd : (asset.kind === 'image' ? 5 : asset.duration);
  if (!Number.isFinite(sourceStart) || sourceStart < 0 || !Number.isFinite(sourceEnd)
    || sourceEnd <= sourceStart || asset.kind !== 'image' && sourceEnd > asset.duration)
    return blocked('Choose a valid source In / Out range.');
  const length = Math.round((sourceEnd - sourceStart) * 1e9) / 1e9;
  const start = append ? duration : requestedStart;
  if (!Number.isFinite(start) || start < 0 || start > duration || length < .08 - 1e-9)
    return blocked('Choose a position inside the edit and at least 0.08 seconds of media.');
  const end = append || insert ? Math.round((start + length) * 1e9) / 1e9 : Math.min(duration, start + length);
  if (end - start < .08 - 1e-9) return blocked('There is not enough space before the edit end. Append video to extend the edit.');
  if ((append || insert) && duration + length > 86400) return blocked('The edit timeline cannot exceed 24 hours.');
  if (insert) { const issue = mutationIssue(project, 'media_insert', {start}, state); if (issue) return blocked(issue); }
  if (!explicit) return {issue:'', start, end};
  if (!state.enabled) return blocked('Enable editable tracks before choosing a destination track.');
  const track = state.tracks.find(row => row.id === options.trackId);
  if (typeof options.trackId !== 'string' || !track)
    return blocked('The chosen destination track is no longer available. Choose another track or Automatic.');
  if (track.locked === true) return blocked(lockReason(track));
  const kind = asset.kind === 'audio' ? 'audio' : 'visual';
  if (track.kind !== kind) return blocked(`Choose a ${kind} track for this ${asset.kind}. A/B and custom text are separate.`);
  // A successful mixed-layer Insert opens exactly this interval on every lane.
  // Existing motion/fade/caption guards are checked separately by the caller.
  if (!insert && (project.manual?.media_clips || []).some(row => row.track_id === track.id && overlap(row, {start,end})))
    return blocked(`The destination "${track.name}" is occupied at this time, including disabled clips. Choose another track, time or Insert.`);
  return {issue:'', start, end, trackId:track.id, trackName:track.name};
}

// Batch only one synchronous availability paint. Do not retain this planner
// across saves or use it for admission: those paths validate a fresh snapshot.
export function createLibraryPlacementPlanner(project) {
  const state = layerTrackState(project);
  return (assetId, start, options = {}) => libraryTrackPlacement(project, assetId, start, options, state);
}
export function planLibraryTrackPlacement(project, assetId, start, options = {}) {
  return libraryTrackPlacement(project, assetId, start, options, layerTrackState(project));
}


const lockReason = track => `Track "${track.name}" is locked. Unlock it before changing its clips or placement.`;
const layerRows = project => [...(project?.manual?.media_clips || []), ...(project?.manual?.text_clips || [])];
function protectedPatchIssue(project, patches, state) {
  const tracks = new Map(state.tracks.map(track => [track.id, track]));
  const rows = new Map(layerRows(project).map(row => [row.id, row]));
  for (const change of patches) {
    const row = rows.get(change?.clip_id); if (!row) continue;
    const patch = Object.fromEntries(Object.entries(change).filter(([key]) => key !== 'clip_id'));
    const changed = Object.entries(patch).some(([key, value]) => JSON.stringify(row[key]) !== JSON.stringify(value));
    if (!changed) continue;
    const original = tracks.get(row.track_id), destination = tracks.get(patch.track_id ?? row.track_id);
    if (original?.locked) return lockReason(original);
    if (destination?.locked) return lockReason(destination);
  }
  return '';
}

function assetMutationIssue(project, assetId, state) {
  if (state.issue) return state.issue;
  if (!state.enabled) return '';
  const locked = new Map(state.tracks.filter(track => track.locked === true).map(track => [track.id, track]));
  const row = (project.manual.media_clips || []).find(row => {
    if (!locked.has(row.track_id)) return false;
    if (row.asset_id === assetId) return true;
    const key = project.manual.chroma_key?.[row.asset_id];
    return key?.enabled === true && key.background_mode !== 'transparent' && key.background_asset_id === assetId;
  });
  return row ? lockReason(locked.get(row.track_id)) : '';
}

function mutationIssue(project, action, payload, state) {
  if (state.issue || !state.enabled) return state.issue;
  const tracks = state.tracks, byTrack = new Map(tracks.map(track => [track.id, track]));
  const rows = layerRows(project), lockedRows = rows.filter(row => byTrack.get(row.track_id)?.locked === true);
  const deny = row => row ? lockReason(byTrack.get(row.track_id)) : '';
  if (['layer_track_audio','layer_track_lock','layer_track_rename','layer_track_add','layer_tracks_enable'].includes(action)) return '';
  if (action === 'layer_track_remove') return byTrack.get(payload.track_id)?.locked ? lockReason(byTrack.get(payload.track_id)) : '';
  if (action === 'layer_track_reorder') {
    const track = byTrack.get(payload.track_id); if (!track) return '';
    const same = tracks.filter(row => row.kind === track.kind), old = same.indexOf(track);
    const dest = {back:0, front:same.length-1, backward:Math.max(0,old-1), forward:Math.min(same.length-1,old+1)}[payload.position];
    if (dest === undefined || dest === old) return '';
    const protectedTrack = same.slice(Math.min(old,dest),Math.max(old,dest)+1).find(row => row.locked);
    return protectedTrack ? lockReason(protectedTrack) : '';
  }
  if (['set_chroma_key','reset_chroma_key'].includes(action)) return assetMutationIssue(project, payload.slot, state);
  if (['media_add','media_append','media_insert'].includes(action) && Object.hasOwn(payload,'track_id')) {
    const track = byTrack.get(payload.track_id); if (track?.locked) return lockReason(track);
  }
  // Copying is a read of the original; automatic placement must choose an unlocked lane.
  if (['media_duplicate','text_duplicate'].includes(action)) return '';
  if (['media_update','text_update'].includes(action)) return protectedPatchIssue(project,[payload],state);
  if (action === 'layer_move') {
    const row = rows.find(row => row.id === payload.clip_id);
    return row ? protectedPatchIssue(project,[{clip_id:row.id,start:payload.start,track_id:payload.track_id}],state) : '';
  }
  if (['layers_move','layers_remove'].includes(action)) {
    if (action === 'layers_move' && payload.delta === 0) return '';
    return deny(lockedRows.find(row => payload.clip_ids?.includes(row.id)));
  }
  if (/^(media|text)_(remove|split|trim|slip|move|set_enabled|set_opacity|transform)$/.test(action)) {
    const row = lockedRows.find(row => row.id === payload.clip_id);
    if (!row) return '';
    if (action.endsWith('_move') && payload.start === row.start) return '';
    if (action.endsWith('_trim') && ['start','end'].includes(payload.edge) && payload.time === row[payload.edge]) return '';
    if (action === 'media_slip' && payload.source_start === row.source_start) return '';
    if (action.endsWith('_set_enabled') && payload.enabled === (row.enabled !== false)) return '';
    if (action === 'media_transform' && ['x','y','w','h'].every(key => Number.isFinite(payload[key]) && payload[key] === row[key])) return '';
    return deny(row);
  }
  if (action === 'text_import' && payload.replace) return deny(lockedRows.find(row => row.id.startsWith('text_') && row.kind === 'caption'));
  if (['sequence_insert_all','media_insert'].includes(action)) return deny(lockedRows.find(row => row.end > payload.start + 1e-9));
  if (action === 'sequence_ripple_delete' && payload.end > payload.start) return deny(lockedRows.find(row => row.end > payload.start + 1e-9));
  if (action === 'sequence_close_gaps' && !payload.slot) {
    const source = project.editor_sequence?.source_tracks || project.manual.source_tracks || {};
    const occupied = [...rows,...(source.A||[]),...(source.B||[])].sort((a,b)=>a.start-b.start);
    let cursor=0;
    for (const row of occupied) {
      if (row.start > cursor + 1e-9) {
        const protectedRow=lockedRows.find(clip=>clip.end > cursor + 1e-9);
        if(protectedRow)return deny(protectedRow);
      }
      cursor=Math.max(cursor,row.end);
    }
  }
  return '';
}

export function layerAssetMutationIssue(project, assetId) {
  return assetMutationIssue(project, assetId, layerTrackState(project));
}

// Use only during one synchronous readiness/preview pass over this saved snapshot.
// Never retain across saves/renders or use for action admission; the direct helper
// below always validates current state again. This is not a persistent cache.
export function createLayerMutationPlanner(project) {
  const state = layerTrackState(project);
  return (action, payload = {}) => mutationIssue(project, action, payload, state);
}

export function layerMutationIssue(project, action, payload = {}) {
  return mutationIssue(project, action, payload, layerTrackState(project));
}
