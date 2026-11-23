import {layerTrackState, planLibraryTrackPlacement} from './layer-tracks.js?v=20261116-track-levels2';

const NS = 1e9;
const finite = n => typeof n === 'number' && Number.isFinite(n);
const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const exact = (x, keys) => object(x) && Object.keys(x).length === keys.length && keys.every(k => Object.hasOwn(x,k));
const canonical = x => Array.isArray(x) ? x.map(canonical) : object(x) ? Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])) : x;
const equal = (a,b) => JSON.stringify(canonical(a)) === JSON.stringify(canonical(b));
const omit = (x,keys) => Object.fromEntries(Object.entries(x||{}).filter(([k])=>!keys.includes(k)));
const validId = s => typeof s === 'string' && s.length > 0 && s.length <= 160;
const fail = issue => ({issue});

export function audioSourceRange(asset, sourceIn, sourceOut) {
  if (!object(asset) || asset.kind !== 'audio' || asset.status !== 'ready' || !finite(asset.duration) || asset.duration < .08 || asset.duration > 14400)
    return fail('Choose ready imported audio with a valid duration.');
  if (![sourceIn,sourceOut].every(finite) || sourceIn < 0 || sourceOut > asset.duration || sourceOut > 14400)
    return fail('Choose source In / Out inside this audio.');
  const a=Math.round(sourceIn*NS), b=Math.round(sourceOut*NS);
  if (b-a < 80000000 || b/NS > asset.duration) return fail('Choose at least 0.08 seconds inside this audio.');
  return {issue:'',source_start:a/NS,source_end:b/NS,length:(b-a)/NS};
}

export function planAudioSourcePlacement(project, assetId, at, range, options={}) {
  if (!validId(project?.id) || !Number.isInteger(project.revision) || project.revision < 0 || !/^asset_[0-9a-f]{32}$/.test(assetId) || project.assets?.[assetId]?.id !== assetId)
    return fail('Reload this project before adding audio.');
  if (!object(options) || Object.keys(options).some(k=>k!=='trackId')) return fail('Choose a valid audio destination.');
  if (project.editor_sequence?.error) return fail('The saved timeline is unavailable.');
  const duration=project.editor_sequence?.duration ?? project.manual?.sequence?.duration ?? project.draft?.output_duration;
  if (!object(project.draft) || !finite(duration) || duration <= 0 || duration > 86400 || !finite(at) || at < 0 || at > duration)
    return fail('Choose a position inside a valid edited timeline.');
  if (!object(project.manual) || ['media_clips','text_clips'].some(key=>Object.hasOwn(project.manual,key) && (!Array.isArray(project.manual[key]) || project.manual[key].some(row=>!object(row))))) return fail('Reload the malformed saved clip list.');
  const selected=audioSourceRange(project.assets[assetId],range?.source_start,range?.source_end);
  if (selected.issue) return selected;
  const start=Math.round(at*NS)/NS, end=(Math.round(start*NS)+Math.round(selected.length*NS))/NS;
  if (end > duration || start > duration) return fail('The whole selected audio passage must fit before the edit end.');
  const admission=planLibraryTrackPlacement(project,assetId,start,{...options,sourceStart:selected.source_start,sourceEnd:selected.source_end});
  if (admission.issue) return fail(admission.issue);
  if (!Object.hasOwn(options,'trackId')) {
    const state=layerTrackState(project);
    if (state.enabled) {
      const rows=project.manual.media_clips || [];
      const available=state.tracks.some(track=>track.kind==='audio' && track.locked!==true
        && (!track.audio || track.audio.gain_db===0 && track.audio.muted===false)
        && !rows.some(row=>row.track_id===track.id && Math.min(row.end,end)-Math.max(row.start,start)>1e-8));
      if (!available && state.tracks.length>=4096) return fail('All 4096 tracks are in use or incompatible. Free an unlocked neutral audio destination before adding this passage.');
    }
  }
  const payload={asset_id:assetId,start,end,source_start:selected.source_start};
  const result={issue:'',projectId:project.id,revision:project.revision,assetId,start,end,source_start:selected.source_start,source_end:selected.source_end,length:selected.length,destinationAudio:{gain_db:0,muted:false},payload};
  if (Object.hasOwn(options,'trackId')) {payload.track_id=options.trackId;result.trackId=options.trackId;result.trackName=admission.trackName;const lane=layerTrackState(project).tracks.find(t=>t.id===options.trackId);if(lane?.audio)result.destinationAudio={...lane.audio};}
  return result;
}

export function verifyAudioSourcePlacement(before, after, plan) {
  try {
    const options=Object.hasOwn(plan||{},'trackId')?{trackId:plan.trackId}:{};
    const fresh=planAudioSourcePlacement(before,plan?.assetId,plan?.start,plan,options);
    if (fresh.issue || !equal(fresh,plan)) return fail('The audio placement intent is stale or invalid.');
    if (after?.id!==before.id || !Number.isInteger(after.revision) || after.revision!==before.revision+1) return fail('The audio placement receipt is stale. Reload the edit.');
    const oldState=layerTrackState(before), state=layerTrackState(after);
    if (state.issue || oldState.issue || state.enabled!==oldState.enabled) return fail('The audio placement changed the track model.');
    for (const key of ['name','settings','sources','assets','analysis','editor_sequence','exports']) if (!equal(before[key],after[key])) return fail('The audio placement changed existing project content.');
    if (!equal(omit(before.draft,['edited_at','status']),omit(after.draft,['edited_at','status'])) || after.draft?.status!==before.draft?.status && after.draft?.status!=='ready') return fail('The audio placement changed the saved draft.');
    if (!equal(omit(before.manual,['media_clips','layer_tracks','history','_history']),omit(after.manual,['media_clips','layer_tracks','history','_history']))) return fail('The audio placement changed existing edit controls.');
    const old=before.manual?.media_clips||[], rows=after.manual?.media_clips;
    if (!Array.isArray(rows) || rows.length!==old.length+1 || !old.every((r,i)=>equal(r,rows[i]))) return fail('The audio placement changed existing clips.');
    const row=rows[old.length];
    if (!/^media_[0-9a-f]{32}$/.test(row?.id) || [...old,...(before.manual?.text_clips||[])].some(r=>r.id===row.id)) return fail('The new audio occurrence has an invalid identity.');
    const expected={id:row.id,asset_id:plan.assetId,start:plan.start,end:plan.end,source_start:plan.source_start,speed:1,volume_db:0,muted:false,role:'music',fade_in:0,fade_out:0,x:0,y:0,w:1,h:1,fit:'cover',motion:'none',audio_enabled:true};
    if (state.enabled) {
      const oldModel=before.manual.layer_tracks, model=after.manual.layer_tracks;
      if (!equal(omit(oldModel,['tracks']),omit(model,['tracks'])) || state.tracks.length<oldState.tracks.length || state.tracks.length>oldState.tracks.length+1 || !oldState.tracks.every((r,i)=>equal(r,state.tracks[i]))) return fail('The audio placement changed existing tracks.');
      const lane=state.tracks.find(t=>t.id===row.track_id);
      if (!lane || lane.kind!=='audio' || lane.locked===true || plan.trackId && lane.id!==plan.trackId) return fail('The audio destination does not match the request.');
      if (plan.trackId && state.tracks.length!==oldState.tracks.length) return fail('The explicit destination unexpectedly created a track.');
      if (!plan.trackId && lane.audio && (lane.audio.gain_db!==0 || lane.audio.muted!==false)) return fail('Automatic audio placement must use neutral track levels.');
      if (state.tracks.length>oldState.tracks.length && state.tracks.at(-1).id!==lane.id) return fail('The placement added an unrelated track.');
      expected.track_id=lane.id;
    }
    if (!equal(expected,row)) return fail('The added audio does not match the selected passage and defaults.');
    return {issue:'',clipId:row.id};
  } catch {return fail('The audio placement receipt is invalid. Reload the edit.');}
}

function markIdentity(project,assetId) {
  const asset=project?.assets?.[assetId];
  if (!validId(project?.id) || !validId(assetId) || asset?.id!==assetId || audioSourceRange(asset,0,asset.duration).issue) throw new Error('The project audio identity is unavailable.');
  return JSON.stringify([1,project.id,assetId,'audio',asset.duration]);
}
const markKey=(project,assetId)=>`cutroom.library-audio-source-marks.v1:${JSON.stringify([project.id,assetId])}`;
export function readAudioSourceMarks(project,assetId,storage) {
  try {
    const identity=markIdentity(project,assetId);
    if (!storage) return {state:'unavailable',range:null};
    let raw;try {raw=storage.getItem(markKey(project,assetId));} catch {return {state:'unavailable',range:null};}
    if (raw===null) return {state:'empty',range:null};
    if (typeof raw!=='string' || raw.length>2048) return {state:'invalid',range:null};
    const saved=JSON.parse(raw);
    if (!exact(saved,['identity','source_start','source_end'])) return {state:'invalid',range:null};
    if (saved.identity!==identity) return {state:'stale',range:null};
    const range=audioSourceRange(project.assets[assetId],saved.source_start,saved.source_end);
    return range.issue ? {state:'invalid',range:null} : {state:'saved',range};
  } catch {return {state:'invalid',range:null};}
}
export function saveAudioSourceMarks(project,assetId,range,storage) {
  const identity=markIdentity(project,assetId), selected=audioSourceRange(project.assets[assetId],range?.source_start,range?.source_end);
  if (selected.issue) throw new Error(selected.issue);
  if (!storage) throw new Error('This browser cannot save audio marks.');
  try {storage.setItem(markKey(project,assetId),JSON.stringify({identity,source_start:selected.source_start,source_end:selected.source_end}));} catch {throw new Error('Audio marks could not be saved in this browser.');}
  return selected;
}
export function clearAudioSourceMarks(project,assetId,storage) {
  markIdentity(project,assetId);
  if (!storage) throw new Error('This browser cannot clear audio marks.');
  try {storage.removeItem(markKey(project,assetId));} catch {throw new Error('Audio marks could not be cleared in this browser.');}
}
