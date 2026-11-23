import { layerTrackState } from './layer-tracks.js?v=20261116-track-levels2';

const PREFIX = 'cutroom:editing-position:v1:';
const MAX_RECORD = 262144, MAX_TOTAL = 2097152, MAX_RECORDS = 20;
const panes = new Set(['timeline', 'media', 'audio', 'framing', 'transcript', 'settings']);
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const exact = (v, keys) => object(v) && Object.keys(v).length === keys.length && keys.every(k => Object.hasOwn(v, k));
const text = (v, max = 128) => typeof v === 'string' && v.trim().length > 0 && v.length <= max && !/[\u0000-\u001f]/.test(v);
const number = (v, min = 0, max = 86400) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
const bool = v => v === undefined || typeof v === 'boolean';
const pick = (v, keys) => Object.fromEntries(keys.map(k => [k, v[k] ?? null]));
const canonical = value => JSON.stringify(value, function (key, item) {
  return object(item) ? Object.fromEntries(Object.keys(item).sort().map(k => [k, item[k]])) : item;
});
function require(value) { if (!value) throw new Error('Unsupported editing position'); }
function range(row, duration) {
  require(object(row) && number(row.start) && number(row.end) && row.end > row.start && row.end <= duration + 1e-8);
}
function identity(project) {
  require(object(project) && text(project.id) && object(project.draft) && object(project.manual) && object(project.settings));
  const e = project.editor_sequence, manual = project.manual;
  require(exact(e, ['active', 'duration', 'sequence', 'source_tracks']) && typeof e.active === 'boolean' && number(e.duration, Number.MIN_VALUE));
  require(exact(e.sequence, ['version', 'duration', 'camera_plan']) && e.sequence.version === 1 && e.sequence.duration === e.duration);
  require(!Object.hasOwn(manual, 'sequence') || object(manual.sequence) && manual.sequence.version === 1 && manual.sequence.duration === e.duration);
  require(Array.isArray(e.sequence.camera_plan) && e.sequence.camera_plan.length <= 2000);
  let previous = 0;
  for (const row of e.sequence.camera_plan) {
    require(exact(row, ['start', 'end', 'camera'])); range(row, e.duration);
    require(row.start >= previous - 1e-8 && ['A','B','screen','camera','stacked','side_by_side','pip','embedded_stack'].includes(row.camera));
    previous = row.end;
  }
  require(exact(e.source_tracks, ['A', 'B']) && object(project.sources));
  const sources = [], primaryIds = new Set();
  for (const slot of ['A', 'B']) {
    const source = project.sources[slot], rows = e.source_tracks[slot];
    require(Array.isArray(rows) && rows.length <= 500);
    if (source != null) {
      require(object(source) && text(source.generation) && number(source.duration, Number.MIN_VALUE));
      for (const field of ['video_duration','audio_duration']) require(source[field] == null || number(source[field]));
      sources.push([slot, source.generation, source.duration, source.video_duration ?? null, source.audio_duration ?? null]);
    } else require(rows.length === 0);
    let end = 0;
    for (const row of rows) {
      range(row, e.duration);
      require(text(row.id) && !primaryIds.has(row.id) && row.start >= end - 1e-8 && number(row.source_start));
      require(Object.keys(row).every(k => ['id','start','end','source_start','video_speed','video_source_start','crop','caption_origin'].includes(k)));
      require(number(row.video_speed ?? 1, .25, 4) && number(row.video_source_start ?? row.source_start));
      require(row.source_start + row.end - row.start <= source.duration + 1e-8);
      if (row.caption_origin !== undefined) require(text(row.caption_origin));
      if (row.crop !== undefined) require(exact(row.crop, ['x','y','zoom']) && number(row.crop.x,0,1) && number(row.crop.y,0,1) && number(row.crop.zoom,1,3));
      primaryIds.add(row.id); end = row.end;
    }
  }
  const state = layerTrackState(project); require(!state.issue);
  const ids = new Set(), media = [], texts = [], assets = new Map();
  for (const [key, prefix, limit] of [['media_clips','media',200],['text_clips','text',2000]]) {
    const rows = Object.hasOwn(manual,key) ? manual[key] : []; require(Array.isArray(rows) && rows.length <= limit);
    for (const row of rows) {
      range(row,e.duration);
      require(typeof row.id === 'string' && new RegExp(`^${prefix}_[0-9a-f]{32}$`).test(row.id) && !ids.has(row.id) && bool(row.enabled)); ids.add(row.id);
      if (prefix === 'media') {
        const asset = project.assets?.[row.asset_id];
        require(typeof row.asset_id === 'string' && /^asset_[0-9a-f]{32}$/.test(row.asset_id) && object(asset) && ['video','image','audio'].includes(asset.kind) && number(asset.duration));
        require(number(row.source_start) && number(row.speed,.25,4) && number(row.video_source_start ?? row.source_start) && ['voice','music','effects'].includes(row.role));
        assets.set(row.asset_id,[row.asset_id,asset.kind,asset.duration]);
        media.push(pick(row,['id','asset_id','track_id','start','end','source_start','video_source_start','speed','enabled','role']));
      } else {
        require(['title','caption'].includes(row.kind)); texts.push(pick(row,['id','track_id','kind','start','end','enabled']));
      }
    }
  }
  let simultaneous = 0;
  const events = texts.flatMap(row => [[row.start,1],[row.end,-1]]).sort((a,b)=>a[0]-b[0] || a[1]-b[1]);
  for (const [,delta] of events) { simultaneous += delta; require(simultaneous <= 16); }
  const captions = project.editor_captions;
  require(Array.isArray(captions) && captions.length <= 20000);
  const captionIds = new Set();
  const cues = captions.map(row => {
    range(row,e.duration); require(text(row.id,256) && !captionIds.has(row.id) && bool(row.hidden)); captionIds.add(row.id);
    return [row.id,row.start,row.end,row.hidden === true];
  });
  const settings = project.settings, fps = settings.fps ?? 30;
  require([24,25,30,50,60].includes(fps) && bool(settings.burn_captions) && bool(settings.captions));
  const result = canonical({projectId:project.id, sequence:e, sources, fps,
    assets:[...assets.values()].sort((a,b)=>a[0].localeCompare(b[0])), media, texts,
    tracks:state.tracks.map(t=>[t.id,t.kind]), captions:cues,
    captionLayout:[settings.burn_captions !== false, settings.captions === true]});
  require(result.length <= MAX_RECORD / 2);
  return result;
}
export function editingPositionIdentity(project) { try { return identity(project); } catch { return null; } }
function validPosition(project, p) {
  if (!exact(p,['cursor','viewport','pane']) || !number(p.cursor,0,project.editor_sequence.duration) || !panes.has(p.pane)) return false;
  const v=p.viewport, duration=project.editor_sequence.duration;
  const geometry=duration+Math.max(1,Math.min(8,duration*.08));
  if (!exact(v,['zoom','leftTime','vertical']) || !number(v.zoom,1,16) || !number(v.leftTime,0,geometry*(1-1/v.zoom)+1e-8)) return false;
  if (v.vertical !== null && (!exact(v.vertical,['trackId','offset']) || !number(v.vertical.offset,0,60-Number.EPSILON*60)
    || !layerTrackState(project).tracks.some(t=>t.id===v.vertical.trackId))) return false;
  return true;
}
export function createEditingPositionStore(storage) {
  const key = (instance, id) => text(instance) && text(id) ? PREFIX+encodeURIComponent(instance)+':'+encodeURIComponent(id) : null;
  function read(instance, project) {
    try {
      const k=key(instance,project?.id), id=editingPositionIdentity(project); if (!k || !id) return null;
      const raw=storage?.getItem(k); if (typeof raw !== 'string' || raw.length > MAX_RECORD) return null;
      const r=JSON.parse(raw);
      if (!exact(r,['version','instanceId','projectId','identity','position','savedAt']) || r.version!==1 || r.instanceId!==instance || r.projectId!==project.id || r.identity!==id || !number(r.savedAt,0,Number.MAX_SAFE_INTEGER) || !validPosition(project,r.position)) return null;
      return r.position;
    } catch { return null; }
  }
  function write(instance, project, position) {
    try {
      const k=key(instance,project?.id), id=editingPositionIdentity(project);
      if (!k || !id || !storage || !validPosition(project,position)) return false;
      const raw=JSON.stringify({version:1,instanceId:instance,projectId:project.id,identity:id,position,savedAt:Date.now()});
      if (raw.length>MAX_RECORD || !Number.isInteger(storage.length) || storage.length>10000) return false;
      const own=[];
      for (let i=0;i<storage.length;i++) { const name=storage.key(i); if (typeof name==='string' && name.startsWith(PREFIX) && name!==k) {
        const value=storage.getItem(name); let stamp=0; try { stamp=JSON.parse(value)?.savedAt; } catch {}
        own.push({name,size:typeof value==='string'?value.length:0,stamp:number(stamp,0,Number.MAX_SAFE_INTEGER)?stamp:0});
      } }
      own.sort((a,b)=>a.stamp-b.stamp || a.name.localeCompare(b.name));
      let total=raw.length+own.reduce((sum,r)=>sum+r.size,0);
      while (own.length>=MAX_RECORDS || total>MAX_TOTAL) { const oldest=own.shift(); if (!oldest) return false; storage.removeItem(oldest.name); total-=oldest.size; }
      storage.setItem(k,raw); return true;
    } catch { return false; }
  }
  function remove(instance, projectId) { try { const k=key(instance,projectId); if (k) storage?.removeItem(k); } catch {} }
  return {read,write,remove};
}
