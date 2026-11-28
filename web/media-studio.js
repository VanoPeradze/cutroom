// Additional footage and sound are edit-clock layers, not replacement A/B sources.
// Apply alpha to the occurrence wrapper, not to the decoded media element:
// its child may be an existing keyed canvas or a video with independent sound.
export function occurrenceFrameOpacity(clip, audition=null) {
  const raw=Number.isInteger(audition)&&audition>=0&&audition<=100?audition:clip?.opacity_percent;
  return Number.isInteger(raw)&&raw>=0&&raw<100?String(raw/100):'';
}
// A transparent still must see through to lower tracks *inside* its image.
// Only the uncovered letterbox/pillarbox strips are black, as in FFmpeg pad.
export function stillContainMatte(item,asset,clip,motion) {
  const frame=item?.frame,style=frame?.style,data=frame?.dataset;if(!style||!data)return false;
  const element=item.element,gotNative=Number.isFinite(element?.naturalWidth)&&element.naturalWidth>0&&Number.isFinite(element?.naturalHeight)&&element.naturalHeight>0;
  const w=gotNative?element.naturalWidth:asset?.width,h=gotNative?element.naturalHeight:asset?.height;
  if(asset?.kind!=='image'||clip?.fit!=='contain'||!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0){
    if(Object.hasOwn(data,'stillContain')){delete data.stillContain;style.removeProperty?.('--still-picture-aspect');style.removeProperty?.('--still-picture-motion');}
    return false;
  }
  const aspect=String(w/h);if(data.stillContain!==aspect){data.stillContain=aspect;style.setProperty?.('--still-picture-aspect',aspect);}
  if(style.getPropertyValue?.('--still-picture-motion')!==motion)style.setProperty?.('--still-picture-motion',motion);
  return true;
}
export function clipEnvelope(clip, time) {
  const elapsed = time - clip.start, remaining = clip.end - time;
  if (elapsed < 0 || remaining <= 0 || clip.muted || clip.enabled === false) return 0;
  return Math.min(1, clip.fade_in > 0 ? elapsed / clip.fade_in : 1,
    clip.fade_out > 0 ? remaining / clip.fade_out : 1);
}

export function mediaGain(clip, mixer, time, trackLevel = null) {
  const role = clip.role || 'music';
  if (mixer[`${role}_muted`] || trackLevel?.muted) return 0;
  return clipEnvelope(clip, time) * 10 ** ((Number(clip.volume_db || 0) + Number(mixer[`${role}_db`] || 0)) / 20) * 10 ** ((trackLevel?.gain_db ?? 0) / 20);
}

// Export normalizes loudness after the channel faders when the draft asks for
// it (draft.audio_policy), then applies Master. The preview follows with a slow
// gain from loudness measured on the summed mix (K-weighted, 3 s window), so a
// fader changes the balance, not the overall level, exactly as in the export.
export const PREVIEW_LOUDNESS_WINDOW_MS = 3000;
export function previewNormalizationGain(previousDb, measuredLufs, targetLufs, elapsed) {
  if (!Number.isFinite(measuredLufs) || measuredLufs < -70) return previousDb; // Silence holds the gain.
  const desired = Math.max(-30, Math.min(30, targetLufs - measuredLufs));
  return previousDb + (desired - previousDb) * (1 - Math.exp(-Math.max(0, elapsed) / 0.8));
}

export function mixerNormalization(project) {
  const policy = project?.draft?.audio_policy;
  if (!policy?.normalize) return null;
  const target = Number(policy.target_lufs);
  return { target: Number.isFinite(target) ? Math.max(-24, Math.min(-10, target)) : -16 };
}

// The control and saved mixer share one 0.1 dB domain. Pointer precision changes
// travel sensitivity, never the gain curve, audio graph or export values.
export function faderGain(value) {
  return Math.round(Math.max(-60, Math.min(12, Number(value) || 0)) * 10) / 10;
}
export function faderPointerGain(start, delta, travel, fine = false) {
  return faderGain(start + delta / Math.max(1, travel) * 72 * (fine ? .1 : 1));
}

export function visualMotion(clip, time) {
  const progress = Math.max(0, Math.min(1, (time - clip.start) / Math.max(.001, clip.end - clip.start)));
  if (clip.motion === 'zoom_in') return `scale(${1 + .12 * progress})`;
  if (clip.motion === 'pan') return `scale(1.12) translateX(${(.5-progress)*100*.12/1.12}%)`;
  return 'none';
}

// A decimal saved edge can differ from the same displayed rational frame by at most half a nanosecond.
function libraryDisplayInstant(time,fps) {
  const frameTime=Math.round(time*fps)/fps;
  return Number.isFinite(frameTime) && Math.abs(time-frameTime)<=5.1e-10 ? frameTime : null;
}
function libraryArrivals(time,fps,frameTime=libraryDisplayInstant(time,fps)) {
  return edge=>time>=edge || (frameTime!==null && Math.abs(edge-frameTime)<=5.1e-10);
}

export function libraryVideoAt(project, time = null, trackOrder = null) {
  if (time !== null && !Number.isFinite(time)) return null;
  let clips = project?.manual?.media_clips;
  if (!Array.isArray(clips) || trackOrder?.issue) return null;
  if (!Object.hasOwn(project.manual, 'layer_tracks') && clips.some(clip => clip && Object.hasOwn(clip, 'track_id'))) return null;
  if(project?.manual && Object.hasOwn(project.manual,"layer_tracks")){
    if(!trackOrder?.enabled || trackOrder.issue || !trackOrder.visual)return null;
    clips=[...clips].sort((a,b)=>(trackOrder.visual.get(a?.id)??-1)-(trackOrder.visual.get(b?.id)??-1));
  }
  const arrived=libraryArrivals(time,project?.settings?.fps??30);
  for (let index = clips.length - 1; index >= 0; index--) {
    const clip = clips[index], asset = project?.assets?.[clip?.asset_id];
    if (clip?.enabled === false || asset?.kind !== 'video' || asset.status !== 'ready'
      || !Number.isFinite(clip.start) || !Number.isFinite(clip.end) || clip.start < 0 || clip.end <= clip.start) continue;
    if (time === null || (arrived(clip.start) && !arrived(clip.end))) return clip;
  }
  return null;
}

// Library rows show a frame (or a waveform for sound) and the clip length.
function libraryClock(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
}
function libraryThumb(url, kind) {
  const thumb = document.createElement('span'); thumb.className = 'library-thumb'; thumb.dataset.kind = kind || 'video'; thumb.setAttribute('aria-hidden', 'true');
  if (url) { const image = document.createElement('img'); image.src = url; image.alt = ''; image.loading = 'lazy'; thumb.append(image); }
  return thumb;
}

export function libraryShotRange(asset,start,end) {
  const duration=Number(asset?.duration);
  if(asset?.kind!=="video" || asset.status!=="ready" || !Number.isFinite(duration) || duration<=0)throw new Error("Choose a ready project video.");
  if(![start,end].every(n=>typeof n==="number" && Number.isFinite(n)) || start<0 || end>duration+.000001 || end-start<.08-1e-9)throw new Error("Choose source In / Out inside this video, at least 0.08 seconds apart.");
  return{source_start:start,source_end:end};
}

// Public original-content fields only. Preview generations and waveform caches
// may change during verified maintenance; names, kind and clocks may not.
export function libraryPreviewContentIdentity(asset) {
  if(!asset || typeof asset!=="object")return null;
  const copy={...asset};
  for(const key of ["url","thumbnail_url","preview_version","waveform"])delete copy[key];
  return JSON.stringify(Object.fromEntries(Object.keys(copy).sort().map(key=>[key,copy[key]])));
}

// One reusable source selection per imported asset, local to this browser.
// Project/asset IDs isolate equal filenames and re-imports; metadata changes
// invalidate marks. This is not a content hash for externally replaced files.
// These preferences never alter project JSON, timeline history or source media.
export function libraryShotMarkIdentity(project, assetId) {
  const asset=project?.assets?.[assetId];
  if(typeof project?.id!=="string" || !project.id || project.id.length>160
    || typeof assetId!=="string" || !assetId || assetId.length>160 || asset?.id!==assetId) {
    throw new Error("The project video identity is unavailable.");
  }
  libraryShotRange(asset,0,Number(asset.duration));
  if(![asset.width,asset.height].every(n=>Number.isFinite(n)&&n>0))throw new Error("The project video dimensions are unavailable.");
  return JSON.stringify([1,project.id,assetId,Number(asset.duration),asset.width,asset.height,asset.kind]);
}

function libraryShotMarkStorage() {
  try{return globalThis.localStorage || null;}catch{return null;}
}

function libraryShotMarkKey(project,assetId) {
  return `cutroom.library-source-marks.v1:${JSON.stringify([project.id,assetId])}`;
}

export function readLibraryShotMarks(project,assetId,storage=libraryShotMarkStorage()) {
  try {
    const identity=libraryShotMarkIdentity(project,assetId);
    if(!storage)return {state:"unavailable",range:null};
    let raw;
    try{raw=storage.getItem(libraryShotMarkKey(project,assetId));}
    catch{return {state:"unavailable",range:null};}
    if(raw===null)return {state:"empty",range:null};
    if(typeof raw!=="string" || raw.length>2048)return {state:"invalid",range:null};
    const saved=JSON.parse(raw);
    if(saved?.identity!==identity)return {state:"stale",range:null};
    const range=libraryShotRange(project.assets[assetId],saved.source_start,saved.source_end);
    return {state:"saved",range};
  }catch{return {state:"invalid",range:null};}
}

export function saveLibraryShotMarks(project,assetId,range,storage=libraryShotMarkStorage()) {
  const identity=libraryShotMarkIdentity(project,assetId);
  const selected=libraryShotRange(project.assets[assetId],range?.source_start,range?.source_end);
  if(!storage)throw new Error("This browser cannot save source marks. Your selection is still available for this review.");
  try{storage.setItem(libraryShotMarkKey(project,assetId),JSON.stringify({identity,...selected}));}
  catch{throw new Error("Source marks could not be saved in this browser. Your selection is still available for this review.");}
  return selected;
}

export function clearLibraryShotMarks(project,assetId,storage=libraryShotMarkStorage()) {
  libraryShotMarkIdentity(project,assetId);
  if(!storage)throw new Error("This browser cannot clear saved source marks. The current selection is unchanged.");
  try{storage.removeItem(libraryShotMarkKey(project,assetId));}
  catch{throw new Error("Saved source marks could not be cleared. The current selection is unchanged.");}
}

// Read-only navigation to this occurrence's original picture, not its normal-
// speed sound clock, composited appearance, or an underlying A/B source.
export function librarySourceMatch(project, clipId, time) {
  const blocked=issue=>({issue});
  if(project?.editor_sequence?.error)return blocked(project.editor_sequence.error);
  const clip=project?.manual?.media_clips?.find(row=>row?.id===clipId);
  if(!project?.id || !project?.draft || typeof clipId!=="string" || !clip)return blocked("Select an imported video clip to open its source.");
  const asset=project.assets?.[clip.asset_id];
  if(asset?.id!==clip.asset_id || asset?.kind!=="video" || asset.status!=="ready" || typeof asset.url!=="string" || !asset.url)
    return blocked("Source matching is available for ready imported video only.");
  if(![asset.duration,asset.width,asset.height].every(n=>typeof n==="number"&&Number.isFinite(n)&&n>0) || asset.duration<.08)
    return blocked("The source video metadata is unavailable. Prepare the video before reviewing it.");
  const pictureStart=clip.video_source_start??clip.source_start??0,speed=clip.speed??1;
  if(![clip.start,clip.end,pictureStart,speed].every(n=>typeof n==="number"&&Number.isFinite(n))
    || clip.start<0 || clip.end<=clip.start || pictureStart<0 || speed<.25 || speed>4)
    return blocked("This clip's saved picture timing is invalid. Reload the edit before opening its source.");
  if(typeof time!=="number" || !Number.isFinite(time))
    return blocked("Move the edit playhead inside this video clip to open its source.");
  const fps=project.settings?.fps??30, displayed=libraryDisplayInstant(time,fps), arrived=libraryArrivals(time,fps,displayed);
  if(!arrived(clip.start) || arrived(clip.end))
    return blocked("Move the edit playhead inside this video clip to open its source.");
  // An incoming frame starts at its exact saved picture In, not a tiny negative/positive offset.
  // A genuine off-grid edge keeps its real phase, just as in the viewer and renderer.
  const atHead=displayed!==null && Math.abs(clip.start-displayed)<=5.1e-10;
  const sourceTime=atHead ? pictureStart : pictureStart+(time-clip.start)*speed;
  if(!Number.isFinite(sourceTime) || sourceTime>=asset.duration)
    return blocked("The picture is holding at the end of its source. Move earlier in the clip, or use the file's In / Out review.");
  const token=JSON.stringify([project.id,project.revision,clipId,clip.asset_id,clip.start,clip.end,pictureStart,speed,
    asset.url,asset.duration,asset.width,asset.height,fps]);
  return{issue:"",projectId:project.id,clipId,assetId:clip.asset_id,editTime:time,sourceTime,speed,token};
}

// Saved occurrence references, not visibility, audibility, or effect references.
// Never infer an unused file from malformed/ambiguous saved membership.
export function libraryAssetUsage(project) {
  const blocked=()=>({issue:'Saved media usage is unavailable. Reopen a valid saved edit before finding its clips.',counts:new Map()});
  if(!project?.id || !project.assets || typeof project.assets!=='object' || Array.isArray(project.assets))return blocked();
  const manual=project.manual;
  if(Object.hasOwn(project,'manual') && (!manual || typeof manual!=='object' || Array.isArray(manual)))return blocked();
  const rows=manual && Object.hasOwn(manual,'media_clips')?manual.media_clips:[],
    text=manual && Object.hasOwn(manual,'text_clips')?manual.text_clips:[];
  if(!Array.isArray(rows) || !Array.isArray(text))return blocked();
  const counts=new Map(),ids=new Set();
  for(const [id,asset] of Object.entries(project.assets)) {
    if(!id || !asset || asset.id!==id || !['video','audio','image'].includes(asset.kind))return blocked();
    counts.set(id,0);
  }
  for(const clip of [...rows,...text]) {
    if(!clip || typeof clip.id!=='string' || !clip.id || ids.has(clip.id))return blocked();
    ids.add(clip.id);
  }
  for(const clip of rows) {
    if(typeof clip.asset_id!=='string' || !counts.has(clip.asset_id)
      || !Number.isFinite(clip.start) || !Number.isFinite(clip.end) || clip.start<0 || clip.end<=clip.start)return blocked();
    counts.set(clip.asset_id,counts.get(clip.asset_id)+1);
  }
  return {issue:'',counts};
}

export function libraryInsertReadiness(project, at, insertedDuration = 0, reservedMedia = 1) {
  if (![0,1].includes(reservedMedia)) return 'The insertion type is unavailable. Review the operation before inserting.';
  const duration = Number(project?.editor_sequence?.duration ?? project?.draft?.output_duration);
  if (!Number.isFinite(at) || at < 0 || !Number.isFinite(duration) || at > duration) return 'Choose a playhead inside the edited timeline.';
  if (!Number.isFinite(insertedDuration) || insertedDuration < 0 || duration + insertedDuration > 86400) return 'The edit timeline cannot exceed 24 hours.';
  if ((project.manual?.media_clips?.length || 0) + reservedMedia > 200) return 'Insertion would exceed the 200 media clip limit.';
  if (Math.abs(at - duration) < 1e-9) return '';
  if (project?.draft?.audio_plan?.length) return 'A timed audio plan is present. Append remains available; middle insertion is not supported for this plan.';
  if (project?.caption_alternative_status?.active_id && project.caption_alternative_status.active_id !== 'original') return 'An alternative caption version is active. Undo that selection before inserting; append remains available.';
  if (Object.keys(project.manual?.caption_dormant_overrides || {}).length) return 'Some caption edits have uncertain ownership. Resolve them before inserting inside the edit.';
  const captions = new Map((project.editor_captions || []).map(row => [row.id, row]));
  for (const id of Object.keys(project.manual?.caption_overrides || {})) {
    const row = captions.get(id);
    if (!row || row.start < at && row.end > at) return 'A manually edited caption crosses the insertion point or its owner is unavailable. Choose a caption boundary before inserting.';
  }
  const tracks = project.editor_sequence?.source_tracks || project.manual?.source_tracks;
  for (const slot of ['A', 'B']) if (project.manual?.track_locks?.[slot] && (!tracks?.[slot] || tracks[slot].some(row => row.end > at + 1e-9))) return `Source ${slot} is locked. Unlock it before inserting into its time.`;
  for (const key of ['media_clips', 'text_clips']) {
    const rows = project.manual?.[key] || [];
    const crossing = rows.filter(row => row.start < at - 1e-9 && row.end > at + 1e-9);
    if (rows.length + crossing.length + (key === 'media_clips' ? reservedMedia : 0) > (key === 'media_clips' ? 200 : 2000)) return `Insertion would exceed the ${key === 'media_clips' ? '200 media' : '2000 text'} clip limit. Choose a boundary that needs fewer splits.`;
    for (const row of crossing) {
      if (key === 'text_clips' && row.template === 'chapter') return 'A Chapter title crosses the insertion point. Insert at its start or end to preserve the built-in fade.';
      const before = at - row.start, after = row.end - at;
      if (Math.min(before, after) < .08 - 1e-9) return 'Insertion would leave a media or text piece shorter than 0.08 seconds. Choose a clip boundary or move farther from its edge.';
      if (key === 'media_clips') {
        const asset = project.assets?.[row.asset_id];
        if (!asset || asset.status !== 'ready') return 'A crossing media asset is not ready. Prepare it before inserting.';
        if (asset.kind !== 'audio' && (row.motion || 'none') !== 'none') return 'An animated media clip crosses the playhead. Choose its boundary so its motion is not restarted.';
        if (before < Number(row.fade_in || 0) - 1e-9 || after < Number(row.fade_out || 0) - 1e-9) return 'The playhead is inside a media audio fade. Choose a point outside the fade or a clip boundary.';
      }
    }
  }
  return '';
}

// File objects stay in this browser tab. Only the active item reaches the
// existing upload transport; queued files never acquire server reservations.
export function planMediaImports(files, project) {
  const selected = Array.from(files || []);
  if (!selected.length) return {files:[], firstSource:false, note:''};
  if (!project?.id) throw new Error('Open a project before importing media.');
  if (!project.draft && project.settings?.workflow !== 'manual') throw new Error('Open a manual editor or create an edit before importing media.');
  const firstSource = !project.draft && !project.sources?.A;
  if (firstSource) {
    const video = selected.findIndex(file => String(file.type || '').startsWith('video/')
      || /\.(mp4|mov|mkv|webm|avi|m4v|mpg|mpeg|mts|m2ts|ts|wmv|flv)$/i.test(file.name || ''));
    if (video < 0) throw new Error('Start with a video recording. You can add audio, images and more video after the first import.');
    // File pickers may sort by name. Start with the first selected video, then
    // retain the relative order of every other selected file.
    selected.unshift(...selected.splice(video, 1));
  }
  const available = Math.max(0, 100 - Object.keys(project.assets || {}).length);
  if (selected.length - Number(firstSource) > available) throw new Error(`This project has room for ${available} more media files. Choose fewer files; nothing was imported.`);
  return {files:selected, firstSource, note:firstSource
    ? `Starting the timeline with ${selected[0].name}. Other files go to the media pool.`
    : 'Files go to the media pool. Your timeline stays unchanged until you place them.'};
}

export class MediaImportQueue {
  constructor({projectId, files, importFile, currentProjectId, changed = () => {}}) {
    this.projectId = projectId; this.importFile = importFile; this.currentProjectId = currentProjectId; this.changed = changed;
    this.items = files.map(file => ({file, name:String(file.name || 'Media file'), status:'queued', message:''}));
    this.running = false; this.finished = false; this.stopRequested = false; this.reason = '';
  }
  stop(reason = 'Stopped. Completed imports are kept; remaining files were not imported.') {
    if (this.finished) return;
    this.stopRequested = true; this.reason = reason; this.changed(this);
  }
  async run() {
    if (this.running || this.finished) return this;
    this.running = true; this.changed(this);
    try {
      for (const item of this.items) {
        if (this.currentProjectId() !== this.projectId) this.stop('Project changed. Completed imports stay in the original project.');
        if (this.stopRequested) break;
        item.status = 'importing'; this.changed(this);
        let result;
        try { result = await this.importFile(item.file, () => !this.stopRequested && this.currentProjectId() === this.projectId); }
        catch (error) { result = {status:error?.name === 'AbortError' ? 'cancelled' : 'failed', message:error?.message || 'Import failed.'}; }
        item.status = result?.status === 'ready' ? 'ready' : result?.status === 'cancelled' ? 'cancelled' : 'failed';
        item.message = result?.message || (item.status === 'ready' ? 'Ready in this project' : 'Import did not finish. Check the file before trying again.');
        item.file = null; // Release completed browser file handles.
        if (item.status !== 'ready') this.stop(`Stopped at ${item.name}. ${item.message} Completed imports are kept.`);
        else if (result?.stop) this.stop(item.message);
        this.changed(this);
      }
    } finally {
      for (const item of this.items) if (item.status === 'queued') { item.status = 'not_imported'; item.file = null; }
      this.running = false; this.finished = true; this.changed(this);
    }
    return this;
  }
}

export class MediaStudio {
  constructor(root, stage, options) {
    this.root = root; this.stage = stage; this.options = options;
    this.selected = null; this.projectId = null; this.players = new Map(); this.overrides = new Map(); this.groupOverrides = new Map();
    this.pending = new Map(); this.timer = null; this.saving = null; this.uploading = false;
    this.trackLevelOverrides = new Map(); this.trackLevelGesture = null; this.trackLevelOwner = null; this.trackLevelSaving = null;
    this.destinationTrackId = ""; this.destinationControls = new Set();
    this.root.innerHTML = `
      <header class="studio-tool-intro"><div><h3>Media</h3></div><span>Import a file, then add it at the playhead.</span></header>
      <button type="button" class="media-import button primary" data-import>Add media</button><input type="file" accept="video/*,audio/*,image/png,image/jpeg,image/webp" multiple hidden>
      <p class="media-status" role="status" aria-live="polite">Import a file, then add it at the playhead.</p>
      <details class="media-storage-details" hidden><summary>Storage details</summary>
        <p class="media-storage upload-storage-info" hidden dir="auto"></p>
      </details>
      <details class="media-import-queue upload-storage-info" hidden open>
        <summary class="media-import-summary">Import queue</summary>
        <p class="media-import-note"></p><p class="media-import-progress" role="status" aria-live="polite"></p>
        <button type="button" data-stop-import-queue>Stop import</button>
        <ol class="media-import-list" aria-label="Selected import files"></ol>
      </details>
      <p class="media-selection-empty">Select an added clip on the timeline to adjust its timing, position and sound.</p>
      <section class="media-inspector" hidden data-editor-shortcuts="off">
        <h4 class="media-selected-name"></h4><p class="media-help" data-layer-protection hidden></p>
        <label class="layer-enabled-control"><input type="checkbox" data-media-enabled aria-describedby="mediaEnabledNote" disabled> Enabled in preview &amp; export</label>
        <p class="media-help layer-enabled-note" id="mediaEnabledNote" data-media-enabled-note></p>
        <div class="media-audio-choice" data-kind="sound">
          <label class="media-audio-toggle" data-kind="video"><input data-media="audio_enabled" type="checkbox"> Include source sound</label>
          <p class="media-audio-status" role="status"></p>
        </div>
        <div class="media-fields">
          <label>Start (seconds)<input data-media="start" type="number" min="0" step="any" data-scrub-step="0.01" title="Exact seconds; Arrow Up/Down or scrub changes 0.01 s"></label>
          <label>End (seconds)<input data-media="end" type="number" min="0" step="any" data-scrub-step="0.01" title="Exact seconds; Arrow Up/Down or scrub changes 0.01 s"></label>
          <label data-kind="timed">Source in (Slip)<input data-media="source_start" type="number" min="0" step="any" aria-describedby="mediaSlipHelp"></label>
          <label data-kind="video">Picture speed<select data-media="speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select></label>
          <label data-kind="visual">Framing<select data-media="fit"><option value="cover">Fill frame</option><option value="contain">Fit entire image</option></select></label>
          <label data-kind="image">Motion<select data-media="motion"><option value="none">Still</option><option value="zoom_in">Slow zoom</option><option value="pan">Slow pan</option></select></label>
        </div>
        <details class="inspector-section layer-move-controls"><summary>Timeline placement</summary>
          <div class="media-actions" role="group" aria-label="Move the whole selected clip" aria-describedby="mediaMoveHelp"><button type="button" data-move="playhead" disabled>Move to playhead</button><button type="button" data-move="-1" disabled>Move 1f earlier</button><button type="button" data-move="1" disabled>Move 1f later</button></div>
          <p class="media-help" id="mediaMoveHelp">Move preserves length, source content and effects. Other layers stay put. Start/End are separate timing edits; arrows or scrub change them by 0.01 s.</p>
        </details>
        <details class="inspector-section" data-roll-cut><summary>Roll a shared cut</summary>
          <label>Cut to adjust <select data-roll-edge><option value="end">End · next clip</option><option value="start">Start · previous clip</option></select></label>
          <p class="media-help" data-roll-pair dir="auto"></p>
          <div class="media-actions" role="group" aria-label="Roll a shared cut" aria-describedby="rollCutHelp rollCutStatus"><button type="button" data-roll="earlier" disabled>1 frame earlier</button><button type="button" data-roll="later" disabled>1 frame later</button><button type="button" data-roll="playhead" disabled>Roll to playhead</button></div>
          <p class="media-help" id="rollCutStatus" data-roll-status></p>
          <p class="media-help" id="rollCutHelp">Lengthen one clip while shortening its neighbor. Other clips, outside edges and edit length stay fixed. Undo restores both sides.</p>
        </details>
        <details class="inspector-section" data-slide-cut><summary>Slide between neighbors</summary>
          <p class="media-help" data-slide-pair dir="auto"></p>
          <div class="media-actions" role="group" aria-label="Slide the selected clip" aria-describedby="slideClipHelp slideClipStatus"><button type="button" data-slide="earlier" disabled>1 frame earlier</button><button type="button" data-slide="later" disabled>1 frame later</button><button type="button" data-slide="playhead" disabled>Slide start to playhead</button></div>
          <p class="media-help" id="slideClipStatus" data-slide-status></p>
          <p class="media-help" id="slideClipHelp">Move this shot with its full picture, sound and duration. Its two neighbors adjust; the rest of the edit stays put.</p>
        </details>
        <details class="inspector-section take-replacement" data-replace-take><summary>Replace take in place</summary>
          <p class="media-help" data-take-summary dir="auto"></p>
          <label>New project file <select data-take-file aria-describedby="replaceTakeHelp" disabled></select></label>
          <label data-take-timed hidden>New Source In (seconds) <input data-take-in type="number" min="0" step="any" value="0" disabled></label>
          <div class="media-actions"><button type="button" data-take-marks hidden disabled>Use saved In / Out</button><button type="button" data-take-apply aria-describedby="replaceTakeStatus" disabled>Replace this take</button></div>
          <p class="media-help" id="replaceTakeStatus" data-take-status role="status"></p>
          <p class="media-help" id="replaceTakeHelp">Only this occurrence changes source. Its track, cuts, speed, framing, motion and mix stay put. Both source clocks start at the chosen In; one Undo restores the previous take.</p>
        </details>
        <details class="inspector-section media-opacity-controls" data-kind="visual" data-clip-opacity>
          <summary>Picture opacity</summary>
          <div class="media-opacity-body">
            <label>Opacity (%)<input data-opacity-value type="number" min="0" max="100" step="1" inputmode="numeric" aria-describedby="mediaOpacityHelp mediaOpacityStatus"></label>
            <input type="range" min="0" max="100" step="1" value="100" data-opacity-slider aria-label="Picture opacity percentage" aria-describedby="mediaOpacityStatus">
            <div class="media-opacity-actions"><button type="button" data-opacity-preview aria-pressed="false">Hold to preview</button><button type="button" data-opacity-reset>Set 100%</button></div>
            <button type="button" data-opacity-apply disabled>Apply opacity</button>
            <p class="media-help" id="mediaOpacityStatus" data-opacity-status role="status"></p>
            <p class="media-help" id="mediaOpacityHelp">Picture only, for this occurrence. Hold Preview to compare in Program; only Apply saves. Sound and the original file stay unchanged.</p>
          </div>
        </details>
        <details class="inspector-section media-stack-controls" data-kind="visual"><summary>Visual stacking</summary>
          <p class="media-help" data-stack-status aria-live="polite"></p>
          <div class="media-actions" role="group" aria-label="Visual stacking order" aria-describedby="mediaStackHelp"><button type="button" data-stack="backward" disabled>Send backward</button><button type="button" data-stack="forward" disabled>Bring forward</button><button type="button" data-stack="back" disabled>Send to back</button><button type="button" data-stack="front" disabled>Bring to front</button></div>
          <p class="media-help" id="mediaStackHelp">Back to front among all imported video and images, including clips at other times. Changes overlap priority only, not timing or sound. A/B stays below; text and captions stay above.</p>
        </details>
        <div class="media-actions media-slip-actions" data-kind="timed" role="group" aria-label="Slip source content"><button type="button" data-slip="-1" disabled>Earlier 1f</button><button type="button" data-slip="1" disabled>Later 1f</button></div>
        <p class="media-help" data-kind="timed" id="mediaSlipHelp">Source in chooses content inside this fixed clip. Timeline position, length, fades and motion stay unchanged.</p>
        <div class="media-file-navigation">
          <button type="button" data-reveal-media-file disabled>Reveal in Media pool</button>
          <p class="media-help">Find this clip's exact imported file. Pool filters may clear; the edit, playhead and Source review stay unchanged.</p>
        </div>
        <div class="media-source-match" data-kind="video">
          <button type="button" data-match-source aria-describedby="mediaMatchHelp" disabled>Open source at playhead</button>
          <p class="media-help" id="mediaMatchHelp" data-match-source-note>Review this video's original picture position. Its edited effects and sound mix are not included; the edit and saved In / Out marks stay unchanged.</p>
        </div>
        <details class="inspector-section media-clip-audio" data-kind="sound" open><summary>Audio settings</summary><div class="media-fields">
          <label data-kind="sound">Audio group<select data-media="role"><option value="music">Music</option><option value="voice">Voiceover</option><option value="effects">Effects</option></select></label>
          <label data-kind="sound">Clip volume (dB)<input data-media="volume_db" type="range" min="-60" max="12" step="1"><output data-value="volume_db"></output></label>
          <label data-kind="sound">Fade in (seconds)<input data-media="fade_in" type="number" min="0" step="0.1"></label>
          <label data-kind="sound">Fade out (seconds)<input data-media="fade_out" type="number" min="0" step="0.1"></label>
          <label data-kind="sound"><input data-media="muted" type="checkbox"> Mute this clip</label>
        </div></details>
        <details class="media-placement"><summary>Position & size</summary>
          <button type="button" data-transform-viewer aria-pressed="false" aria-describedby="mediaTransformStatus" disabled>Edit frame in viewer</button>
          <p class="media-help" id="mediaTransformStatus" data-transform-status>Move or resize this imported picture's frame. Timing, source content and sound stay unchanged.</p>
          <div class="media-fields">
          <label>Left (%)<input data-media="x" type="number" min="0" max="100" step="any" data-scrub-step="1" title="Exact percentage; Arrow Up/Down or scrub changes 1%"></label>
          <label>Top (%)<input data-media="y" type="number" min="0" max="100" step="any" data-scrub-step="1" title="Exact percentage; Arrow Up/Down or scrub changes 1%"></label>
          <label>Width (%)<input data-media="w" type="number" min="1" max="100" step="any" data-scrub-step="1" title="Exact percentage; Arrow Up/Down or scrub changes 1%"></label>
          <label>Height (%)<input data-media="h" type="number" min="1" max="100" step="any" data-scrub-step="1" title="Exact percentage; Arrow Up/Down or scrub changes 1%"></label>
        </div></details>
        <p class="media-help">Drag the clip or its edges in the timeline. Changes save automatically. Picture speed changes only the image; clip sound stays at normal speed from Source in.</p>
        <div class="media-actions"><button type="button" data-action="split">Split at playhead</button><button type="button" data-action="trim_start" disabled>Trim start</button><button type="button" data-action="trim_end" disabled>Trim end</button><button type="button" data-action="duplicate">Duplicate at playhead</button><button type="button" data-action="remove">Remove</button></div>
      </section>
      <details class="inspector-section media-library-section" open><summary>Project files</summary>
      <div class="media-library" aria-label="Project media"></div>
      </details>
      <details class="audio-mixer" data-editor-shortcuts="off"><summary><span>Audio mixer</span><small class="mixer-summary-level">Paused</small></summary>
        <div class="mixer-body">
        <div class="mixer-master" role="group" aria-label="Master output"></div>
        <div class="mixer-bank-label"><h4>Channels</h4><small>Mute affects export. Solo is preview only.</small></div>
        <div class="mixer-channels" role="group" aria-label="Original, music, voiceover and effects"></div>
        <label class="ducking-choice"><input type="checkbox" data-ducking> Lower music while speech plays</label>
        <label class="ducking-choice" title="Removes rumble and steady background noise, evens out the level and adds clarity. Applied when you export; the preview plays the original sound."><input type="checkbox" data-voice-cleanup> Clean up voice (export)</label>
        <p class="mixer-level-text">Play to monitor the mix.</p>
        <p class="mixer-help mixer-normalization" role="note"></p>
        <details class="mixer-reference"><summary>Fader controls and metering</summary>
        <p class="mixer-help" id="mixerFaderHelp">Shift + drag for precision. Arrow keys: 0.5 dB; Shift + arrow: 0.1 dB. Reset returns a fader to 0 dB.</p>
        <p class="mixer-help mixer-export-note">Meters show live sample peaks of the browser mix, before the preview limiter. The export keeps true peaks under −1 dBTP.</p>
        </details>
        <datalist id="mixerZeroMark"><option value="0" label="0 dB"></option></datalist>
        </div>
      </details>`;
    const mediaStatus = root.querySelector('.media-status');
    this.storageStatus = root.querySelector('.media-storage');
    this.storageDetails = root.querySelector('.media-storage-details');
    this.importButton = root.querySelector('.media-import');
    this.importQueuePanel = root.querySelector('.media-import-queue');
    this.importQueue = null;
    const mixerStatus = options.audioPanel?.querySelector('.mixer-save-status');
    // Both tool panels show the same save/error state; controls remain single.
    this.status = mixerStatus ? {get textContent(){return mediaStatus.textContent;},set textContent(value){mediaStatus.textContent=value;mixerStatus.textContent=value;}} : mediaStatus;
    this.channelMeters = new Map();
    for (const [role, name] of [['source','Original'],['music','Music'],['voice','Voiceover'],['effects','Effects'],['master','Master']]) {
      const row = document.createElement('div'); row.className = 'mixer-channel'; row.dataset.channel = role;
      const label = document.createElement('div'); label.className = 'mixer-fader';
      const heading = document.createElement('span'); heading.className = 'mixer-channel-heading';
      const title = document.createElement('span'); title.textContent = name; title.dataset.channelName = role;
      const range = document.createElement('input'); range.type = 'range'; range.min = '-60'; range.max = '12'; range.step = '0.1'; range.dataset.mix = `${role}_db`; range.setAttribute('aria-label', `${name} volume`);
      range.dataset.mixOrientation = role === 'master' ? 'horizontal' : 'vertical';
      range.setAttribute('aria-orientation', range.dataset.mixOrientation);
      range.setAttribute('aria-describedby', 'mixerFaderHelp');
      range.setAttribute('list', 'mixerZeroMark'); range.title = 'Drag to adjust; hold Shift for precision. Double-click to reset to 0 dB.';
      // A typed value (0.1 dB), the same value the fader and the export use.
      const level = document.createElement('span'); level.className = 'mixer-db';
      const typed = document.createElement('input'); typed.type = 'number'; typed.min = '-60'; typed.max = '12'; typed.step = '0.1'; typed.dataset.mixNumber = `${role}_db`;
      typed.setAttribute('aria-label', `${name} level in dB`); typed.inputMode = 'decimal';
      const unit = document.createElement('span'); unit.textContent = 'dB'; unit.setAttribute('aria-hidden', 'true');
      const reset = document.createElement('button'); reset.type = 'button'; reset.className = 'mixer-reset'; reset.textContent = '0 dB'; reset.dataset.mixReset = `${role}_db`;
      reset.title = 'Reset to 0 dB'; reset.setAttribute('aria-label', `Reset ${name} to 0 dB`);
      level.append(typed,unit);
      const lane = document.createElement('div'); lane.className = 'mixer-fader-lane';
      const scale = document.createElement('div'); scale.className = 'mixer-fader-scale'; scale.setAttribute('aria-hidden', 'true');
      for (const db of [12, 0, -12, -24, -36, -48, -60]) {
        const mark = document.createElement('span'); mark.dataset.db = String(db); mark.textContent = db > 0 ? `+${db}` : String(db);
        mark.style.setProperty('--mark-from-top', `${(12 - db) / 72 * 100}%`);
        mark.style.setProperty('--mark-from-left', `${(db + 60) / 72 * 100}%`);
        scale.append(mark);
      }
      const control = document.createElement('div'); control.className = 'mixer-fader-control';
      const rail = document.createElement('span'); rail.className = 'mixer-fader-rail'; rail.setAttribute('aria-hidden', 'true');
      const travel = document.createElement('span'); travel.className = 'mixer-fader-travel'; travel.setAttribute('aria-hidden', 'true');
      const cap = document.createElement('span'); cap.className = 'mixer-fader-cap';
      const grip = document.createElement('span'); grip.className = 'mixer-fader-grip'; cap.append(grip); travel.append(cap);
      control.append(rail,travel,range); lane.append(scale,control);
      range.addEventListener('pointerdown', event => this.startFaderDrag(event, range));
      range.addEventListener('pointermove', event => this.moveFaderDrag(event));
      range.addEventListener('pointerup', event => this.endFaderDrag(event));
      range.addEventListener('pointercancel', event => this.endFaderDrag(event));
      range.addEventListener('lostpointercapture', event => this.endFaderDrag(event));
      range.addEventListener('keydown', event => this.faderKeydown(event, range));
      heading.append(title,level); label.append(heading,lane); row.append(label);
      const signal = document.createElement('div'); signal.className = 'mixer-signal';
      const meter = document.createElement('meter'); meter.className = role === 'master' ? 'mixer-meter mixer-channel-meter' : 'mixer-channel-meter';
      meter.min = 0; meter.max = 1; meter.high = .95; meter.optimum = .65; meter.value = 0;
      meter.setAttribute('aria-label', `${name} live sample peak`);
      const peak = document.createElement('output'); peak.className = 'mixer-signal-value'; peak.textContent = '-inf dBFS';
      signal.append(meter,peak); row.append(signal);
      const actions = document.createElement('div'); actions.className = 'mixer-channel-actions'; row.append(actions);
      if (role !== 'master') {
        const mute = document.createElement('button'); mute.type = 'button'; mute.textContent = 'M'; mute.title = 'Mute in preview and export'; mute.dataset.mute = role; mute.setAttribute('aria-label', `Mute ${name} in preview and export`); actions.append(mute);
        const solo = document.createElement('button'); solo.type = 'button'; solo.textContent = 'S'; solo.title = 'Solo in preview only'; solo.dataset.solo = role; solo.setAttribute('aria-label', `Solo ${name} in preview only`); actions.append(solo);
      }
      actions.append(reset);
      this.channelMeters.set(role,{row,meter,level:peak});
      root.querySelector(role === 'master' ? '.mixer-master' : '.mixer-channels').append(row);
    }
    root.querySelector('input[type=file]').addEventListener('change', event => { const files = Array.from(event.target.files || []); event.target.value = ''; if (files.length) void this.uploadFiles(files); });
    this.audioRoot = root.querySelector('.audio-mixer');
    if (options.audioPanel) options.audioPanel.append(this.audioRoot);
    if (options.createTrackLevels) {
      const mount = document.createElement('section'); mount.className = 'track-level-mount'; this.audioRoot.after(mount);
      this.trackLevels = options.createTrackLevels(mount, {
        snapshot: () => this.trackLevelSnapshot(), change: (id,patch) => this.queueTrackLevel(id,patch),
        interaction: (id,request) => this.trackLevelInteraction(id,request),
        stateChanged: () => this.options.saveStateChanged?.(),
      });
    }
    const onInput = event => { if (event.target.matches('input[type=range]')) this.change(event.target); };
    const onDoubleClick = event => {
      const fader = event.target.closest?.('[data-mix]');
      if (fader && !this.options.busy()) this.queueMixer({[fader.dataset.mix]: 0});
    };
    const onChange = event => { if(event.target.matches('[data-media-enabled]')) { void this.setOccurrenceEnabled(event.target.checked); return; } if (!event.target.matches('input[type=range],input[type=file]')) this.change(event.target); };
    const onClick = event => {
      const button = event.target.closest('button'); if (!button) return;
      if (button.hasAttribute('data-transform-viewer')) { void this.toggleFrameEditor(); return; }
      if (button.hasAttribute('data-match-source')) { void this.openSourceAt(this.selected); return; }
      if (button.hasAttribute('data-reveal-media-file')) { this.revealSelectedMediaFile(); return; }
      if (button.hasAttribute('data-import')) this.chooseFiles();
      if (button.hasAttribute('data-stop-import-queue')) this.stopImports();
      if (button.dataset.repairPreview) { void this.runPreviewRepair('start',button.dataset.repairPreview,button); return; }
      if (button.dataset.repairCheck) { void this.runPreviewRepair('check',button.dataset.repairCheck,button); return; }
      if (button.dataset.repairCancel) { void this.runPreviewRepair('cancel',button.dataset.repairCancel,button); return; }
      if (button.dataset.retry) this.retry(button.dataset.retry);
      if (button.dataset.asset) this.add(button.dataset.asset);
      if (button.dataset.append) this.append(button.dataset.append);
      if (button.dataset.reviewShot) void this.reviewShot(button.dataset.reviewShot, {browse:button.dataset.poolSource==='video'}).catch(error=>{this.status.textContent=error.message;});
      if (button.dataset.reviewAudio) this.reviewAudio(button.dataset.reviewAudio);
      if (button.dataset.select) this.select(button.dataset.select);
      if (button.dataset.mute) { const key = `${button.dataset.mute}_muted`; this.queueMixer({[key]: !this.mixer()[key]}); }
      if (button.dataset.mixReset && !this.options.busy()) this.queueMixer({[button.dataset.mixReset]: 0});
      if (button.dataset.solo) this.toggleSolo(button.dataset.solo);
      if (button.dataset.slip) void this.nudgeSlip(Number(button.dataset.slip));
      if (button.dataset.move) void this.movePlacement(button.dataset.move);
      if (button.dataset.stack) void this.stackPlacement(button.dataset.stack);
      if (button.dataset.action) this.action(button.dataset.action);
    };
    this.library = root.querySelector('.media-library');
    this.sourceLibrary = options.libraryRoot?.querySelector('.source-library');
    if (options.libraryRoot) {
      for (const selector of ['.media-import','.media-status','.media-storage-details','.media-import-queue','.media-library-section']) options.libraryRoot.append(root.querySelector(selector));
    }
    for (const eventRoot of [root, ...(options.audioPanel ? [this.audioRoot] : []), ...(options.libraryRoot ? [options.libraryRoot] : [])]) {
      eventRoot.addEventListener('input',onInput);
      eventRoot.addEventListener('change',onChange);
      eventRoot.addEventListener('click',onClick);
      eventRoot.addEventListener('dblclick',onDoubleClick);
    }
    if (typeof options.placementPreview === 'function' && typeof options.trackState === 'function') {
      this.poolDestinationControl = this.makeDestinationControl('pool');
      this.library?.prepend?.(this.poolDestinationControl);
    }
    const roll=options.createRollCut?.(root.querySelector('[data-roll-cut]')),slide=options.createRollCut?.(root.querySelector('[data-slide-cut]'),true);
    const take=options.createTakeReplacement?.(root.querySelector('[data-replace-take]'));
    this.rollCut={refresh(){roll?.refresh();slide?.refresh();take?.refresh();}};
    this.clipOpacity=options.createClipOpacity?.(root.querySelector('[data-clip-opacity]'),id=>this.repaintClipOpacity(id));
    this.frameEditor = options.createFrameEditor?.(stage, {
      snapshot: () => this.frameSnapshot(),
      preview: (id,rect) => this.previewFrame(id,rect),
      commit: (id,rect,token) => this.commitFrame(id,rect,token),
      changed: value => { this.frameEditorState=value; this.updateFrameEditorButton(); },
    });
  }
  setFaderVisual(input, db) {
    const control = input.closest?.('.mixer-fader-control');
    const progress = (faderGain(db) + 60) / 72;
    control?.style.setProperty('--fader-from-top', `${(1 - progress) * 100}%`);
    control?.style.setProperty('--fader-from-left', `${progress * 100}%`);
    control?.classList.toggle('at-unity', Math.abs(db) < .05);
  }
  setFaderGain(input, value) {
    const gain = faderGain(value);
    input.value = String(gain);
    this.setFaderVisual(input, gain);
    if (gain !== faderGain(this.mixer()[input.dataset.mix])) this.queueMixer({[input.dataset.mix]: gain});
  }
  startFaderDrag(event, input) {
    if (event.button != null && event.button !== 0) return;
    event.preventDefault();
    if (this.options.busy() || input.disabled) return;
    this.endFaderDrag();
    const horizontal = input.dataset.mixOrientation === 'horizontal', rect = input.getBoundingClientRect();
    const coordinate = horizontal ? event.clientX : event.clientY;
    const travel = Math.max(1, (horizontal ? rect.width : rect.height) - 22);
    const original = faderGain(this.mixer()[input.dataset.mix]);
    const progress = (original + 60) / 72;
    const center = (horizontal ? rect.left : rect.top) + 11 + (horizontal ? progress : 1 - progress) * travel;
    input.focus({preventScroll:true});
    // Grabbing the cap preserves the grab point. A rail click seeks the fader;
    // holding Shift always starts a relative, ten-times-finer adjustment.
    const value = event.shiftKey || Math.abs(coordinate - center) <= 14 ? original
      : faderGain(-60 + (horizontal ? coordinate - rect.left - 11 : rect.bottom - coordinate - 11) / travel * 72);
    this.faderDrag = {input, pointerId:event.pointerId, projectId:this.project()?.id, horizontal, travel,
      original, anchorValue:value, anchor:coordinate, last:coordinate, value, fine:Boolean(event.shiftKey)};
    input.closest('.mixer-fader-control').classList.add('is-dragging');
    try { input.setPointerCapture?.(event.pointerId); }
    catch { this.endFaderDrag(); return; }
    this.setFaderGain(input, value);
  }
  moveFaderDrag(event) {
    const drag = this.faderDrag;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    if (drag.projectId !== this.project()?.id || this.options.busy()) { this.endFaderDrag(); return; }
    const coordinate = drag.horizontal ? event.clientX : event.clientY;
    if (Boolean(event.shiftKey) !== drag.fine) {
      drag.anchor = drag.last; drag.anchorValue = drag.value; drag.fine = Boolean(event.shiftKey);
    }
    drag.value = faderPointerGain(drag.anchorValue, (coordinate - drag.anchor) * (drag.horizontal ? 1 : -1), drag.travel, drag.fine);
    drag.last = coordinate;
    this.setFaderGain(drag.input, drag.value);
  }
  endFaderDrag(event) {
    const drag = this.faderDrag;
    if (!drag || (event && event.pointerId !== drag.pointerId)) return;
    this.faderDrag = null;
    drag.input.closest?.('.mixer-fader-control')?.classList.remove('is-dragging');
    try { if (drag.input.hasPointerCapture?.(drag.pointerId)) drag.input.releasePointerCapture(drag.pointerId); }
    catch { /* The browser may already have revoked capture on focus/navigation. */ }
  }
  faderKeydown(event, input) {
    if (event.key === 'Escape' && this.faderDrag?.input === input) {
      event.preventDefault();
      const {original,projectId} = this.faderDrag;
      this.endFaderDrag();
      if (projectId === this.project()?.id && !this.options.busy() && !input.disabled) this.setFaderGain(input, original);
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const directions = {ArrowUp:1, ArrowRight:1, ArrowDown:-1, ArrowLeft:-1, PageUp:1, PageDown:-1};
    if (!(event.key in directions) && !['Home','End'].includes(event.key)) return;
    event.preventDefault();
    if (this.options.busy() || input.disabled) return;
    const value = faderGain(this.mixer()[input.dataset.mix]);
    this.setFaderGain(input, event.key === 'Home' ? -60 : event.key === 'End' ? 12
      : value + directions[event.key] * (event.shiftKey ? .1 : event.key.startsWith('Page') ? 6 : .5));
  }
  appendAssetUsage(card,asset,usage) {
    card.dataset.libraryAsset=asset.id;card.dataset.librarySearch=String(asset.name || '');card.tabIndex=-1;
    const count=usage.counts.get(asset.id),valid=!usage.issue && Number.isInteger(count);
    card.dataset.mediaUsageValid=String(valid);
    if(valid)card.dataset.mediaUsageCount=String(count);
    const root=document.createElement('div');root.className='media-asset-usage';
    const note=document.createElement('small');note.dataset.mediaUsageSummary='true';
    note.textContent=valid?`${count} timeline ${count===1?'clip':'clips'}`:'Timeline usage unavailable';
    note.title='Saved imported-media occurrences, including disabled clips. This is not a count of audible/visible output or effect references.';
    const button=document.createElement('button');button.type='button';button.dataset.findUses=asset.id;button.textContent='Find uses';
    button.disabled=!valid || count===0 || typeof this.options.usage?.find!=='function';
    button.title=usage.issue || (count===0?'No saved timeline clips reference this imported file. Effect references are not counted.':'Open only this file’s saved clips in Timeline Index. Nothing is selected or changed until you choose a clip.');
    const context={projectId:this.project()?.id,viewToken:this.options.viewToken?.()};
    button.addEventListener('click',()=>{
      if(button.disabled || this.project()?.id!==context.projectId || this.options.viewToken?.()!==context.viewToken)return;
      const current=libraryAssetUsage(this.project());
      if(current.issue || !current.counts.get(asset.id)){this.status.textContent=current.issue || 'This file no longer has a saved timeline clip.';return;}
      this.options.usage?.find?.(asset.id,button,context);
    });
    root.append(note,button);card.append(root);
  }
  updateMediaUsageAvailability() {
    const button=this.root?.querySelector?.('[data-reveal-media-file]');if(!button)return;
    const project=this.project(),rows=project?.manual?.media_clips,clip=Array.isArray(rows)?rows.find(row=>row?.id===this.selected):null,
      asset=project?.assets?.[clip?.asset_id],group=typeof this.options.singleSelectedClip==='function' && this.options.singleSelectedClip()!==this.selected,
      issue=group?'Select one imported clip to reveal its file.':this.options.usage?.issue?.() || '';
    button.disabled=Boolean(!clip || !asset || issue || typeof this.options.usage?.reveal!=='function');
    button.title=issue || (asset?'Reveal this exact imported file, clearing obstructing Media pool filters. No seek, edit or Source reopening.':'Select one imported clip to reveal its file.');
  }
  revealSelectedMediaFile() {
    const project=this.project(),rows=project?.manual?.media_clips,clip=Array.isArray(rows)?rows.find(row=>row?.id===this.selected):null;
    if(!clip || !project.assets?.[clip.asset_id])return false;
    const issue=this.options.usage?.issue?.() || '';
    if(issue){this.status.textContent=issue;return false;}
    return this.options.usage?.reveal?.(clip.asset_id,{projectId:project.id,viewToken:this.options.viewToken?.(),clipId:clip.id})===true;
  }
  openMixer() { if (this.audioRoot) this.audioRoot.open = true; }
  previewFailureKey(assetId) {
    const project=this.project(),asset=project?.assets?.[assetId];
    return JSON.stringify([project?.id,assetId,asset?.preview_version ?? asset?.url]);
  }
  reportPreviewFailure(assetId, url, kind='media') {
    const asset=this.project()?.assets?.[assetId];
    if(asset?.status!=='ready' || (kind==='thumbnail'?asset.thumbnail_url:asset.url)!==url)return;
    this.previewErrors ||= new Map();
    const key=this.previewFailureKey(assetId);
    if(this.previewErrors.has(key))return;
    this.previewErrors.set(key,kind==='thumbnail' ? 'The prepared thumbnail could not load. Verify this preview without replacing its original.'
      : 'The prepared preview could not load. Verify it from the saved original; your timeline has not been changed.');
    this.updatePreviewRepairControls();
  }
  appendPreviewRepair(card,asset) {
    if(!this.options.previewRepair || asset.status!=='ready')return;
    const root=document.createElement('div');root.className='media-preview-repair';root.dataset.editorShortcuts='off';
    const make=(key,label)=>{const button=document.createElement('button');button.type='button';button.dataset[key]=asset.id;
      button.textContent=label;button.setAttribute('aria-label',`${label}: ${asset.name}`);root.append(button);return button;};
    const verify=make('repairPreview','Verify & repair preview'),check=make('repairCheck','Check status'),cancel=make('repairCancel','Cancel verification');
    const status=document.createElement('p');status.className='media-preview-repair-status';status.setAttribute('role','status');
    status.id=`previewRepairStatus-${asset.id}`;root.append(status);card.append(root);
    for(const button of [verify,check,cancel])button.setAttribute('aria-describedby',status.id);
    this.previewRepairCards ||= new Map();this.previewRepairCards.set(asset.id,{root,verify,check,cancel,status});
  }
  updatePreviewRepairControls() {
    const host=this.options.previewRepair;if(!host)return;
    for(const [assetId,nodes] of this.previewRepairCards || []) {
      const entry=host.entry?.(assetId),issue=host.issue?.(assetId)||'',active=entry&&['preparing','queued','running','unknown'].includes(entry.status);
      nodes.verify.textContent=entry?.canRestart?'Verify again':'Verify & repair preview';
      nodes.verify.disabled=Boolean(issue || host.busy?.() && !entry?.canRestart || active && !entry?.canRestart || entry?.pending);
      nodes.verify.title=issue || 'Check the original and prepared preview. Rebuild only when needed; keep the original, timeline, tracks and source marks. Playback pauses.';
      // Rechecking joins the controller's existing GET. Keep a visible Check
      // focusable during background polling instead of hiding it every second.
      const checking=Boolean(active && entry?.pending && !nodes.check.hidden);
      nodes.check.hidden=!(entry?.canCheck || checking);nodes.check.disabled=false;
      nodes.cancel.hidden=!entry?.canCancel;nodes.cancel.disabled=Boolean(entry?.pending);
      let message=host.notice?.(assetId)||'';
      if(active)message=entry.status==='unknown'
        ? `The previous verification outcome is unconfirmed. Check status${entry.canRestart?' or explicitly verify again':''}; no request is repeated automatically.`
        : entry.cancel_requested?'Cancellation requested. Waiting for the confirmed result.':entry.status==='preparing'
          ? 'Saving queued changes before verification. The original and edit are kept.'
          : 'Verifying the original and prepared preview. Repairs use only this verified original; playback remains paused.';
      else if(entry && ['failed','rejected'].includes(entry.status))message=entry.error || entry.message || 'Preview verification did not finish. The saved edit was kept.';
      else if(entry?.status==='cancelled')message='Verification cancelled. No original or timeline content was replaced.';
      else if(entry?.status==='interrupted')message='Verification stopped when CUTROOM closed. Review the current asset and verify again explicitly.';
      else if(!message && entry?.status==='completed')message='Verification completed. Reopen the project if this preview is still unavailable; no original or timeline content was replaced.';
      const playbackError=this.previewErrors?.get(this.previewFailureKey(assetId));
      if(entry?.status==='completed' && playbackError)message='The prepared file was verified, but this browser still reports it unavailable. No repair is repeated automatically. '+playbackError;
      if(entry?.error_code==='revision_conflict')message='The project changed since it was opened. Reopen it to review the current saved edit before verifying again; save or discard local drafts first. Nothing was replayed.';
      if(entry?.earlier_request)message='An earlier verification request is still being reconciled. '+message+' Its result will not reload this view automatically.';
      nodes.status.textContent=message || playbackError || 'Checks the prepared preview only. Originals, edits and source marks are kept.';
      nodes.root.dataset.repairState=entry?.status || (this.previewErrors?.has(this.previewFailureKey(assetId))?'unavailable':'idle');
    }
    this.finishPreviewRepairFocus();
  }
  ownPreviewRepairFocus(button) {
    this.previewRepairFocus?.dispose?.();
    if(document.activeElement!==button)return;
    const owner={button,projectId:this.project()?.id,viewToken:this.options.viewToken?.(),moved:false,frame:null,cancelFrame:null};
    const moved=event=>{if(event.type==='focusin' && (event.target===owner.button || event.target===document.body))return;owner.moved=true;};
    for(const name of ['pointerdown','keydown','focusin'])document.addEventListener?.(name,moved,true);
    owner.dispose=()=>{if(owner.frame!==null){owner.cancelFrame?.(owner.frame);owner.frame=null;}for(const name of ['pointerdown','keydown','focusin'])document.removeEventListener?.(name,moved,true);if(this.previewRepairFocus===owner)this.previewRepairFocus=null;};
    this.previewRepairFocus=owner;
  }
  finishPreviewRepairFocus(deferred=false) {
    const owner=this.previewRepairFocus;if(!owner)return;
    if(owner.moved || owner.projectId!==this.project()?.id || owner.viewToken!==this.options.viewToken?.()
      || owner.button.isConnected===false || owner.button.parentElement?.closest?.('[hidden], [inert]')){owner.dispose();return;}
    let target=owner.button;
    const id=target.dataset.repairPreview || target.dataset.repairCheck || target.dataset.repairCancel;
    const nodes=this.previewRepairCards?.get(id),entry=this.options.previewRepair?.entry?.(id);
    const active=Boolean(entry && ['preparing','queued','running','unknown'].includes(entry.status));
    if((target.hidden || target.disabled) && active && nodes?.check && !nodes.check.hidden && !nodes.check.disabled)target=nodes.check;
    else if(target.hidden)target=nodes?.verify;
    if(!target || target.hidden){owner.dispose();return;}
    if(target.disabled)return;
    // A terminal job emits before its asynchronous snapshot adoption begins.
    // Recheck after that readiness pass; never restore then immediately disable.
    if(!deferred){
      if(owner.frame!==null)return;
      const finish=()=>{owner.frame=null;if(this.previewRepairFocus===owner)this.finishPreviewRepairFocus(true);};
      if(typeof requestAnimationFrame==='function'){owner.cancelFrame=cancelAnimationFrame;owner.frame=requestAnimationFrame(finish);}
      else{owner.cancelFrame=clearTimeout;owner.frame=setTimeout(finish,0);}
      return;
    }
    owner.button=target;
    if(document.activeElement===document.body)target.focus?.({preventScroll:true});
    // Retain only this owned Check handoff until a terminal result or newer
    // interaction. Automatic completion may hide Check and reveal Verify.
    if(active && target===nodes?.check)return;
    owner.dispose();
  }
  async runPreviewRepair(command,assetId,button) {
    const host=this.options.previewRepair;if(!host || button?.disabled)return;
    this.ownPreviewRepairFocus(button);
    try {await host[command]?.(assetId);}
    catch(error){if(this.project()?.assets?.[assetId])this.status.textContent=error.message;}
    finally {this.updatePreviewRepairControls();}
  }
  revealPreviewRepair(assetId) {
    this.options.previewRepair?.reveal?.();
    const nodes=this.previewRepairCards?.get(assetId);if(!nodes)return false;
    this.options.libraryRoot?.mediaPoolNavigation?.revealAsset?.(assetId);
    const target=!nodes.check.hidden&&!nodes.check.disabled?nodes.check:!nodes.cancel.hidden&&!nodes.cancel.disabled?nodes.cancel:nodes.verify;
    nodes.root.scrollIntoView?.({block:'nearest',inline:'nearest'});target.focus?.({preventScroll:true});return true;
  }
  capturePreviewRepair(assetId) {
    const asset=this.project()?.assets?.[assetId];if(!asset)return null;
    return {projectId:this.project().id,viewToken:this.options.viewToken?.(),assetId,identity:libraryPreviewContentIdentity(asset),
      previewVersion:asset.preview_version,error:Boolean(this.previewErrors?.has(this.previewFailureKey(assetId))),
      source:this.shotReview?.captureRepair?.(assetId) || null};
  }
  acceptPreviewRepair(capture,result) {
    const project=this.project(),asset=project?.assets?.[capture?.assetId];
    if(!capture || capture.projectId!==project?.id || capture.viewToken!==this.options.viewToken?.()
      || libraryPreviewContentIdentity(asset)!==capture.identity || result?.project_id!==project.id || result.asset_id!==capture.assetId
      || result.before_preview_version!==capture.previewVersion || result.after_preview_version!==asset.preview_version)return false;
    const reload=capture.previewVersion!==asset.preview_version || capture.error;
    if(reload)for(const clip of project.manual?.media_clips||[])if(clip.asset_id===capture.assetId)
      for(const key of [`v:${clip.id}`,`a:${clip.id}`]){const item=this.players?.get(key);if(item)this.releasePlayer(key,item);}
    this.shotReview?.acceptRepair?.(capture.source,asset,project.revision,reload);
    // Refresh this card in place: never replace the pool or its focused button.
    const card=this.previewRepairCards?.get(capture.assetId)?.root?.parentElement,img=card?.querySelector?.('.library-thumb img');
    if(img && asset.thumbnail_url && (reload || img.getAttribute?.('src')!==asset.thumbnail_url))img.src=asset.thumbnail_url;
    for(const key of this.previewErrors?.keys()||[])if(JSON.parse(key)[0]===project.id && JSON.parse(key)[1]===capture.assetId)this.previewErrors.delete(key);
    return true;
  }
  project() { return this.options.project(); }
  videoAt(time = null) { const project=this.project(); return libraryVideoAt(project, time, this.options.trackOrder?.(project)); }
  clips() {
    const frame=this.frameOverride?.projectId===this.project()?.id ? this.frameOverride : null;
    const protection=(this.overrides.size || this.groupOverrides?.size || frame) ? this.options.mutationPlanner?.() || this.options.mutationIssue : null;
    return (this.project()?.manual?.media_clips || []).map(clip => {
      const patch={...this.overrides.get(clip.id),...this.groupOverrides?.get(clip.id),...(frame?.clipId===clip.id ? frame.rect : null)};
      // Saved playback is read-only. Validate only a real transient edit, not
      // every occurrence on every frame (the model validator scans all rows).
      return Object.keys(patch).length && protection?.("media_remove",{clip_id:clip.id}) ? {...clip} : {...clip,...patch};
    });
  }
  frameSnapshot() {
    const project=this.project(),clip=project?.manual?.media_clips?.find(row=>row.id===this.selected),asset=project?.assets?.[clip?.asset_id];
    const rect=clip ? Object.fromEntries(['x','y','w','h'].map(key=>[key,clip[key]])) : null,time=Number(this.options.time?.());
    const busy=Boolean(this.options.busy()||this.options.trimBusy?.()||this.options.frameBusy?.()||this.options.playing?.()
      ||this.pending?.size||this.saving||this.importing||this.uploading||this.importQueue?.running||this.startingFrameEdit);
    let issue='';
    if(!project?.draft || !clip)issue='Select an imported video or image to frame it.';
    else if(this.options.mutationIssue?.('media_transform',{clip_id:clip.id}))issue=this.options.mutationIssue('media_transform',{clip_id:clip.id});
    else if(this.options.viewerVisible && !this.options.viewerVisible())issue='Open the edited viewer before framing this clip.';
    else if(this.options.sourceMode?.())issue='Switch to Edited video to frame this occurrence.';
    else if(this.options.playing?.())issue='Pause playback before framing this occurrence.';
    else if(!asset || asset.status!=='ready' || !['video','image'].includes(asset.kind))issue='Viewer framing is available for ready imported video and images only.';
    else if(clip.enabled===false)issue='Enable this occurrence before framing it in the viewer.';
    else if(!Number.isFinite(time) || time<clip.start || time>=clip.end)issue='Move the edit playhead inside this clip to frame it.';
    else if(typeof this.options.framePreview!=='function' || typeof this.options.frameEdit!=='function')issue='Viewer framing is unavailable in this editor.';
    else { const plan=this.options.framePreview(clip.id,rect);issue=typeof plan?.issue==='string' && plan.patch && typeof plan.patch==='object' ? plan.issue : plan?.issue || 'Frame readiness could not be confirmed.'; }
    return {projectId:project?.id,clipId:clip?.id,rect,issue,busy,
      token:JSON.stringify([project?.id,project?.revision,clip,asset,time,project?.settings?.aspect,project?.settings?.resolution,project?.settings?.fps])};
  }
  updateFrameEditorButton() {
    if(!this.frameEditor && !this.options.createFrameEditor)return;
    const button=this.root?.querySelector?.('[data-transform-viewer]');if(!button)return;
    const state=this.frameSnapshot(),active=Boolean(this.frameEditor?.active??this.frameEditorState?.active),pending=Boolean(this.frameEditor?.pending??this.frameEditorState?.pending);
    button.textContent=active?'Done framing':'Edit frame in viewer';button.setAttribute('aria-pressed',String(active));
    button.disabled=pending||this.startingFrameEdit||(!active&&(!this.frameEditor||state.busy||Boolean(state.issue)));
    button.title=state.issue|| (state.busy?'Pause playback and wait for current edits to finish.':'Move or resize only the selected picture frame. One Undo restores it.');
    const note=this.root?.querySelector?.('[data-transform-status]');
    if(note)note.textContent=state.issue || (pending?'Saving frame…':active&&this.frameEditorState?.issue ? this.frameEditorState.issue : active?'Drag the frame or its handles. Use the percentage fields for precise or keyboard editing. Escape cancels. Fit/Fill and motion stay unchanged.':'Move or resize this imported picture’s frame. Timing, source content and sound stay unchanged.');
  }
  syncFrameEditor() { if(this.frameSyncDepth)return; this.frameEditor?.sync(); this.updateFrameEditorButton(); }
  deferFrameSync(refresh) {
    this.frameSyncDepth=(this.frameSyncDepth||0)+1;
    try { return refresh(); }
    finally { this.frameSyncDepth--; if(!this.frameSyncDepth)this.syncFrameEditor(); }
  }
  async toggleFrameEditor() {
    if(!this.frameEditor)return false;
    if(this.frameEditor.active){this.frameEditor.close();return true;}
    const id=this.selected,projectId=this.project()?.id;
    const initial=this.frameSnapshot();if(this.startingFrameEdit||initial.busy||initial.issue)return false;
    this.startingFrameEdit=true;this.updateFrameEditorButton();this.options.pause();
    try {
      if(typeof this.options.prepareFrameEdit==='function' && await this.options.prepareFrameEdit(id)===false)return false;
      if(this.project()?.id!==projectId||this.selected!==id)return false;
      this.startingFrameEdit=false;
      const state=this.frameSnapshot();if(state.issue||state.busy)return false;
      return this.frameEditor.open();
    } catch(error) { if(this.project()?.id===projectId)this.status.textContent=error.message;return false; }
    finally { this.startingFrameEdit=false;this.updateFrameEditorButton(); }
  }
  previewFrame(id,rect) {
    if(rect===null){
      if(this.frameOverride?.clipId===id){this.frameOverride=null;this.options.preview();}
      return {issue:'',rect:null};
    }
    const state=this.frameSnapshot();
    if(state.clipId!==id||state.issue||state.busy)return {issue:state.issue||'Wait for current edits to finish.',rect:null};
    const plan=this.options.framePreview(id,rect);
    if(plan?.issue||!plan?.patch)return {issue:plan?.issue||'Frame readiness could not be confirmed.',rect:null};
    const canonical=Object.keys(plan.patch).length?plan.patch:state.rect;
    this.frameOverride={projectId:state.projectId,clipId:id,rect:canonical};this.options.preview();
    return {issue:'',rect:canonical};
  }
  async commitFrame(id,rect,token) {
    const state=this.frameSnapshot(),projectId=state.projectId;
    if(state.clipId!==id||state.token!==token||state.issue||state.busy){this.previewFrame(id,null);return null;}
    try { return await this.options.frameEdit(id,rect); }
    finally { if(this.frameOverride?.projectId===projectId&&this.frameOverride?.clipId===id){this.frameOverride=null;this.options.preview();} }
  }
  mixer() { return {...this.project()?.manual?.audio_mixer,...this.mixerOverride}; }
  trackLevelContext() { return {projectId:this.project()?.id,viewToken:this.options.viewToken?.()}; }
  trackLevelSameContext(owner) {
    const current=this.trackLevelContext(); return owner && owner.projectId===current.projectId && owner.viewToken===current.viewToken;
  }
  trackLevelIdentity() { return JSON.stringify([this.project()?.revision,this.project()?.manual?.layer_tracks]); }
  trackLevelValues(project = this.project(), model = undefined) {
    // Only saved response/model identity invalidates this read cache. Canonical
    // admission never uses it, and sync has already validated its track order.
    const raw=project?.manual?.layer_tracks;
    if(!this.trackLevelCache || this.trackLevelCache.project!==project || this.trackLevelCache.raw!==raw || this.trackLevelCache.revision!==project?.revision)
      this.trackLevelCache={project,raw,revision:project?.revision,levels:this.options.trackLevels?.(project,model) || {}};
    const saved=this.trackLevelCache.levels,gesture=this.trackLevelGesture;
    if(project?.id!==this.project()?.id || !this.trackLevelSameContext(this.trackLevelOwner)
      || !this.trackLevelOverrides?.size && !gesture)return saved;
    // Sparse shadow lookup: a passive audio frame neither clones all lanes nor
    // serializes the model. Admission and pointer ticks still verify full identity.
    const levels=Object.create(saved);
    for(const [id,patch] of this.trackLevelOverrides || [])if(saved[id])levels[id]={...saved[id],...patch};
    if(gesture && this.trackLevelSameContext(gesture) && gesture.model===raw && gesture.revision===project?.revision && levels[gesture.trackId])
      levels[gesture.trackId]={...levels[gesture.trackId],gain_db:gesture.gain_db};
    return levels;
  }
  trackLevelSnapshot() {
    const project=this.project(),model=this.options.trackState?.(project),levels=this.trackLevelValues(project,model);
    const issue=this.options.trackLevelIssue?.({model}) || model?.issue || (!model?.enabled ? 'Enable editable tracks before setting named track levels.' : '');
    const pendingTrackIds=[...(this.pending?.keys?.() || [])].filter(key=>key.startsWith('track_audio:')).map(key=>key.slice(12));
    if(this.trackLevelSaving)pendingTrackIds.push(this.trackLevelSaving);
    return {project,viewToken:this.options.viewToken?.(),tracks:model?.issue?[]:(model?.tracks||[]).filter(row=>row.kind!=='text'),
      selectedClipId:this.options.singleSelectedClip?.() ?? this.selected,levels,pendingTrackIds,
      summariesByTrack:this.options.trackSoundSummaries?.(project,levels,model) || {},busy:false,issue};
  }
  syncTrackLevels() {
    if(this.trackLevelSyncing)return;
    this.trackLevelSyncing=true;
    try {
      const gesture=this.trackLevelGesture;
      if(gesture && (!this.trackLevelSameContext(gesture) || gesture.identity!==this.trackLevelIdentity()))this.trackLevelGesture=null;
      this.trackLevels?.sync?.();
    } finally { this.trackLevelSyncing=false; }
  }
  queueTrackLevel(trackId,patch) {
    const issue=this.options.trackLevelIssue?.();
    const plan=this.options.trackLevelPlan?.(trackId,patch);
    if(issue || !plan || plan.issue || !plan.patch || this.trackLevelGesture) {
      this.status.textContent=issue || plan?.issue || 'Finish or cancel the current track level adjustment.'; return false;
    }
    if(!this.trackLevelSameContext(this.trackLevelOwner)) {
      this.trackLevelOverrides?.clear();this.trackLevelOwner=this.trackLevelContext();
    }
    const key=`track_audio:${trackId}`,desired={...this.trackLevelOverrides.get(trackId),...patch};
    const merged=this.options.trackLevelPlan(trackId,desired);
    if(merged.issue)return false;
    if(!Object.keys(merged.patch).length) {
      this.pending.delete(key);this.trackLevelOverrides.delete(trackId);this.syncTrackLevels();this.options.preview();this.options.saveStateChanged?.();return true;
    }
    this.trackLevelOverrides.set(trackId,merged.patch);this.pending.set(key,merged.patch);
    this.schedule();this.renderMixer();this.options.preview();return true;
  }
  trackLevelInteraction(trackId,request) {
    const validGain=value=>Number.isFinite(value)&&value>=-60&&value<=12;
    if(request?.phase==='begin') {
      if(this.trackLevelGesture || this.pending?.size || this.saving || this.options.trackLevelIssue?.())return null;
      const levels=this.options.trackLevels?.(this.project()),level=levels?.[trackId];if(!level)return null;
      const owner=this.trackLevelContext();if(!owner.projectId)return null;
      const token={...owner,trackId,model:this.project().manual.layer_tracks,revision:this.project().revision,identity:this.trackLevelIdentity(),gain_db:level.gain_db};
      this.trackLevelOwner=owner;this.trackLevelGesture=token;this.options.saveStateChanged?.();return token;
    }
    const token=request?.token;
    if(!token || token!==this.trackLevelGesture || token.trackId!==trackId)return false;
    const current=this.trackLevelSameContext(token)&&token.identity===this.trackLevelIdentity();
    if(request.phase==='cancel' || !current) {
      this.trackLevelGesture=null;this.options.preview();this.options.saveStateChanged?.();return request.phase==='cancel';
    }
    if(!validGain(request.gain_db))return false;
    if(request.phase==='preview') { token.gain_db=request.gain_db;this.options.preview();return true; }
    if(request.phase==='commit') {
      this.trackLevelGesture=null;
      const admitted=this.queueTrackLevel(trackId,{gain_db:request.gain_db});
      this.options.preview();this.options.saveStateChanged?.();return admitted;
    }
    return false;
  }

  chooseFiles() {
    if (this.options.busy() || this.uploading || this.importQueue?.running) return false;
    this.root.querySelector('input[type=file]').click();
    return true;
  }
  updateProtectionAvailability() {
    const clip=this.project()?.manual?.media_clips?.find(row=>row.id===this.selected),asset=this.project()?.assets?.[clip?.asset_id];
    const issue=clip ? this.options.mutationIssue?.('media_remove',{clip_id:clip.id}) || '' : '';
    const hasSound=asset?.kind==='audio'||Boolean(asset?.has_audio),included=asset?.kind==='audio'||Boolean(clip?.audio_enabled);
    for(const input of this.root?.querySelectorAll?.('[data-media], [data-action="remove"]') || []) {
      const key=input.dataset.media,soundBlocked=key==='audio_enabled'?!hasSound:['role','volume_db','fade_in','fade_out','muted'].includes(key)&&(!hasSound||!included);
      input.disabled=Boolean(!clip||issue||this.options.busy()||soundBlocked);
      // Source in owns a live slip-readiness title; do not restore an old lock
      // title over the fresh unlocked one after its next readiness pass.
      if(key==='source_start' && typeof this.options.slipPreview==='function'){if(issue)input.title=issue;continue;}
      if(issue){if(input.layerProtectionTitle===undefined)input.layerProtectionTitle=input.title||'';input.title=issue;}
      else if(input.layerProtectionTitle!==undefined){input.title=input.layerProtectionTitle;delete input.layerProtectionTitle;}
    }
    const note=this.root?.querySelector?.('[data-layer-protection]');if(note){note.hidden=!issue;note.textContent=issue;}
  }
  updateImportAvailability() {
    const project = this.project(), busy = Boolean(this.options.busy() || this.uploading || this.importQueue?.running || this.placing);
    this.updateDestinationControls();
    if (this.importButton) this.importButton.disabled = busy;
    this.updateLibraryAvailability();
    this.updateAudioSourceAvailability();
    this.updatePreviewRepairControls();
    this.updateSplitAvailability();
    this.updateTrimAvailability();
    this.updateDuplicateAvailability();
    this.updateMoveAvailability();
    this.updateStackAvailability();
    this.updateEnabledAvailability();
    this.updateSlipAvailability();
    this.updateSourceMatchAvailability();
    this.updateMediaUsageAvailability();
    this.updateProtectionAvailability();
    this.syncFrameEditor();
  }
  updateLibraryAvailability(time) {
    const project=this.project(),busy=Boolean(this.options.busy()||this.uploading||this.importQueue?.running||this.placing);
    if(!Number.isFinite(time))time=this.options.time?.();
    const planner=this.options.placementPlanner?.();let directIssue;
    // A successful edit/Undo paints cards before manualEditBusy clears. Refresh
    // only availability on the final readiness pass: never rebuild the pool,
    // reset its scroll, remove a drag origin or replace the import receipt.
    for (const button of this.library?.querySelectorAll?.('[data-asset], [data-append], [data-review-shot], [data-retry]') || []) {
      const {asset: add, append, reviewShot, retry} = button.dataset;
      const asset = project?.assets?.[add || append || reviewShot || retry];
      button.disabled = busy || !asset || (retry
        ? !['failed', 'cancelled'].includes(asset.status)
        : !project?.draft || asset.status !== 'ready' || Boolean(append || reviewShot) && asset.kind !== 'video');
      if(reviewShot && button.dataset.poolSource==='video' && !button.disabled){
        if(directIssue===undefined)directIssue=this.options.sourceMonitor?.poolIssue?.() ?? 'Reload the media workspace before browsing sources.';
        const issue=this.poolSourceIssue(reviewShot,directIssue);button.disabled=Boolean(issue);
        button.title=issue||'Review the original without placing it or saving pending edits.';
      }
      if(retry && (asset?._stabilization || asset?.stabilized)){const issue=this.options.assetMutationIssue?.(retry);if(issue){button.disabled=true;button.title=issue;}}
      if ((add || append) && typeof this.options.placementPreview==='function' && !button.disabled) {
        const placementTime=append?this.options.duration():Math.min(time,Math.max(0,this.options.duration()-.1));
        const plan=this.placementPreview(add||append,placementTime,{append:Boolean(append),...this.destinationOptions()},planner);
        button.disabled=Boolean(plan.issue);button.title=plan.issue||(plan.trackName?`Place in ${plan.trackName}.`:'Choose a compatible track automatically.');
      }
    }
  }
  updateAudioSourceAvailability() {
    const buttons=this.library?.querySelectorAll?.('[data-review-audio]') || [];
    const sharedIssue=buttons.length ? this.options.audioSource?.issue?.() || '' : '';
    for(const button of buttons){
      if(!Object.hasOwn(button.dataset||{},'reviewAudio'))continue;
      const issue=this.audioSourceIssue(button.dataset.reviewAudio,null,sharedIssue);
      button.disabled=Boolean(issue);button.title=issue || 'Audition original-speed audio and choose a source passage before adding. Opening does not save or change the edit.';
    }
    if(this.shotReview?.audioSource)this.syncSourceMonitor();
  }
  audioSourceIssue(assetId,owner=null,sharedIssue=undefined) {
    const project=this.project(),asset=project?.assets?.[assetId],audio=this.options.audioSource;
    if(typeof audio?.create!=='function' || typeof audio?.range!=='function' || typeof audio?.plan!=='function' || typeof audio?.place!=='function')return 'Audio source review is unavailable. Reload this CUTROOM version.';
    if(!project?.draft || asset?.id!==assetId || asset.kind!=='audio' || asset.status!=='ready' || typeof asset.url!=='string' || !asset.url)return 'Choose ready imported audio with a prepared preview.';
    const issue=audio.range(asset,0,asset.duration)?.issue;if(issue)return issue;
    if(this.uploading || this.placing || this.importQueue?.running || this.pending?.size || this.saving
      || (this.shotReview?.pending && this.shotReview!==owner))return 'Wait for the current changes or source placement before reviewing audio.';
    return typeof sharedIssue==='string' ? sharedIssue : audio.issue?.(owner) || '';
  }
  sourceMatchPlan(id, time) {
    if(time===undefined && id)time=this.options.time?.();
    const plan=librarySourceMatch(this.project(),id,time);
    if(plan.issue)return plan;
    const blocked=this.options.sourceMatchBlocked?.();
    if(blocked)return{issue:blocked};
    if(this.options.sourceMode?.())return{issue:"Switch the viewer to Edited before opening a clip's source at the playhead."};
    if(this.options.busy() || this.uploading || this.importQueue?.running || this.pending?.size || this.saving || this.importing || this.frameEditor?.pending || this.frameEditorState?.dragging)
      return{issue:"Wait for the current changes to finish before opening the source. No edit is submitted by this action."};
    return plan;
  }
  updateSourceMatchAvailability(time) {
    const button=this.root?.querySelector?.('[data-match-source]');if(!button)return;
    const plan=this.sourceMatchPlan(this.selected,time);
    button.disabled=Boolean(plan.issue);
    button.title=plan.issue||`Open original picture at ${plan.sourceTime.toFixed(3)} s. Disabled or covered clips can still be reviewed; edited effects and sound are not included.`;
    const note=this.root?.querySelector?.('[data-match-source-note]');
    if(note)note.textContent=plan.issue||"Review this video's original picture position. Its edited effects and sound mix are not included; the edit and saved In / Out marks stay unchanged.";
  }
  async openSourceAt(id, time) {
    const plan=this.sourceMatchPlan(id,time);
    if(plan.issue){this.status.textContent=plan.issue;return false;}
    try{return Boolean(await this.reviewShot(plan.assetId,{match:plan}));}
    catch(error){if(this.project()?.id===plan.projectId)this.status.textContent=error.message;return false;}
  }
  updateSplitAvailability(time = this.options.time?.()) {
    const button = this.root?.querySelector?.('[data-action="split"]');
    if (!button || typeof this.options.splitIssue !== 'function') return;
    const issue = this.options.splitIssue(this.selected, time);
    const saving = Boolean(this.pending?.size || this.saving);
    button.disabled = this.options.busy() || saving || Boolean(issue);
    button.title = saving ? 'Wait for the clip changes to finish saving before splitting.' : issue || 'Split this clip at the playhead. Its source content and outside fades stay unchanged; one Undo restores it.';
  }
  updateTrimAvailability(time) {
    if (typeof this.options.trimPreview !== 'function') return;
    if (!Number.isFinite(time) && this.selected) time = this.options.time?.();
    const saving = Boolean(this.pending?.size || this.saving), busy = this.options.trimBusy?.() || this.options.busy();
    for (const edge of ['start', 'end']) {
      const button = this.root?.querySelector?.(`[data-action="trim_${edge}"]`); if (!button) continue;
      const plan = this.options.trimPreview(this.selected, edge, time), issue = plan?.issue || '';
      const unchanged = !plan?.patch || !Object.keys(plan.patch).length;
      button.disabled = busy || saving || Boolean(issue) || unchanged;
      button.title = saving || busy ? 'Wait for the current changes to finish saving before trimming.' : issue || (unchanged ? 'This edge is already at the playhead.' : `Set this clip's ${edge} to the playhead. Only this occurrence changes; edit duration stays the same. One Undo restores it.`);
    }
  }
  updateEnabledAvailability() {
    if(typeof this.options.enabledPreview!=='function')return;
    const input=this.root?.querySelector?.('[data-media-enabled]');if(!input)return;
    const clip=this.clips().find(row=>row.id===this.selected),enabled=clip?.enabled!==false;
    const plan=this.options.enabledPreview(this.selected,!enabled),saving=Boolean(this.pending?.size||this.saving||this.importing||this.changingEnabled);
    const busy=this.options.busy()||this.options.trimBusy?.();
    input.checked=Boolean(clip)&&enabled;
    input.disabled=!clip||busy||saving||Boolean(plan?.issue)||!plan?.patch;
    input.title=busy||saving?'Wait for current changes to finish saving.':plan?.issue||'Enable or disable this occurrence in preview and export. Timing and settings stay unchanged; Undo restores it.';
    const note=this.root?.querySelector?.('[data-media-enabled-note]');
    if(note)note.textContent=enabled?'Included in preview and export. Disable to compare without removing this occurrence.':'Disabled in preview and export. Its timeline position and all edits are retained.';
  }
  async setOccurrenceEnabled(enabled) {
    const id=this.selected,projectId=this.project()?.id;
    if(!id||!projectId||this.changingEnabled||this.importing||this.options.busy()||this.options.trimBusy?.()||typeof this.options.setEnabled!=='function'){this.updateEnabledAvailability();return null;}
    this.changingEnabled=true;this.updateEnabledAvailability();
    try{return await this.options.setEnabled(id,enabled);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;return null;}
    finally{this.changingEnabled=false;this.updateEnabledAvailability();}
  }
  updateStackAvailability() {
    if(typeof this.options.stackPreview!=='function')return;
    const saving=Boolean(this.pending?.size||this.saving||this.importing),busy=this.options.busy()||this.options.trimBusy?.();
    let status=null;
    for(const position of ['backward','forward','back','front']) {
      const button=this.root?.querySelector?.(`[data-stack="${position}"]`);if(!button)continue;
      const plan=this.options.stackPreview(this.selected,position),unchanged=!plan?.patch||!Object.keys(plan.patch).length;
      status=plan;
      button.disabled=busy||saving||Boolean(plan?.issue)||unchanged;
      button.title=busy||saving?'Wait for the current changes to finish saving before changing visual order.':plan?.issue||(unchanged?'Already at this end of the visual stack.':`Place at visual position ${plan.destination} of ${plan.count}, back to front. Timing and sound stay unchanged. One Undo restores the order.`);
    }
    const group=this.root?.querySelector?.('.media-stack-controls');
    if(group){
      const tracked=Boolean(this.project()?.manual && Object.hasOwn(this.project().manual,"layer_tracks"));
      const actions=group.querySelector?.('.media-actions');if(actions)actions.hidden=tracked;
      let manage=group.querySelector?.('[data-manage-tracks]');
      if(!manage && this.options.manageTracks){manage=document.createElement("button");manage.type="button";manage.dataset.manageTracks="";manage.textContent="Manage tracks";manage.addEventListener("click",()=>{const clip=this.project()?.manual?.media_clips?.find(row=>row.id===this.selected);void this.options.manageTracks(clip?.track_id);});group.append(manage);}
      if(manage){manage.hidden=!tracked;manage.disabled=Boolean(busy||saving);}
    }
    const label=this.root?.querySelector?.('[data-stack-status]');
    if(label)label.textContent=status?.issue||(Number.isFinite(status?.rank)?`Visual position ${status.rank} of ${status.count} (back to front).`:'Select an imported video or image.');
  }
  async stackPlacement(position) {
    const id=this.selected,projectId=this.project()?.id;
    if(!id||!projectId||this.importing||this.options.busy()||this.options.trimBusy?.()||typeof this.options.stack!=='function')return null;
    try{return await this.options.stack(id,position);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;return null;}
  }
  moveDestination(mode,time) {
    const clip=this.clips().find(row=>row.id===this.selected);if(!clip)return NaN;
    const configured=Number(this.options.frame?.()),frame=Number.isFinite(configured)&&configured>0 ? configured : 1/30;
    if(mode==='playhead') { if(!Number.isFinite(time))time=this.options.time?.();return Number.isFinite(time)?Math.round(time/frame)*frame:NaN; }
    return ['-1','1'].includes(String(mode)) ? Number(clip.start)+Number(mode)*frame : NaN;
  }
  updateMoveAvailability(time) {
    this.rollCut?.refresh();
    if(typeof this.options.movePreview!=='function')return;
    const saving=Boolean(this.pending?.size||this.saving||this.importing),busy=this.options.busy()||this.options.trimBusy?.();
    for(const mode of ['playhead','-1','1']) {
      const button=this.root?.querySelector?.(`[data-move="${mode}"]`);if(!button)continue;
      const plan=this.options.movePreview(this.selected,this.moveDestination(mode,time)),unchanged=!plan?.patch||!Object.keys(plan.patch).length;
      button.disabled=busy||saving||Boolean(plan?.issue)||unchanged;
      button.title=busy||saving?'Wait for the current changes to finish saving before moving.':plan?.issue||(unchanged?'The clip is already at this position.':`Move the whole clip to ${Number(plan.patch.start).toFixed(3)} s. Source content, length and other layers stay unchanged. One Undo restores it.`);
    }
  }
  async movePlacement(mode) {
    const id=this.selected,projectId=this.project()?.id,start=this.moveDestination(mode);
    if(!id||!projectId||this.importing||this.options.busy()||this.options.trimBusy?.()||typeof this.options.move!=='function')return null;
    try{return await this.options.move(id,start);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;return null;}
  }
  updateDuplicateAvailability(time) {
    if (typeof this.options.duplicatePreview !== 'function') return;
    const button = this.root?.querySelector?.('[data-action="duplicate"]'); if (!button) return;
    if (!Number.isFinite(time) && this.selected) time = this.options.time?.();
    const plan = this.options.duplicatePreview(this.selected,time), saving = Boolean(this.pending?.size || this.saving);
    const busy = this.options.busy() || this.options.trimBusy?.();
    button.disabled = busy || saving || Boolean(plan?.issue) || !plan?.patch;
    button.title = busy || saving ? 'Wait for the current changes to finish saving before duplicating.' : plan?.issue || `Copy the whole occurrence at ${Number(plan?.patch?.start).toFixed(3)} s. Other layers and edit duration stay unchanged; the new copy is selected. One Undo removes it.`;
  }
  slipFrame() {
    const frame = Number(this.options.frame?.());
    return Number.isFinite(frame) && frame > 0 ? frame : 1 / 30;
  }
  updateSlipAvailability() {
    if (typeof this.options.slipPreview !== 'function') return;
    const clip = this.clips().find(row => row.id === this.selected), busy = this.options.busy() || this.options.trimBusy?.();
    const saving = Boolean(this.pending?.size || this.saving);
    for (const direction of [-1, 1]) {
      const button = this.root?.querySelector?.(`[data-slip="${direction}"]`); if (!button) continue;
      const plan = this.options.slipPreview(this.selected, Number(clip?.source_start) + direction * this.slipFrame());
      button.disabled = busy || saving || Boolean(plan?.issue) || !plan?.patch || !Object.keys(plan.patch).length;
      button.title = busy || saving ? 'Wait for the current changes to finish saving before slipping.' : plan?.issue || `${direction < 0 ? 'Earlier' : 'Later'} source content by one output-frame interval. Only content changes; the clip stays in place.`;
    }
    const input = this.root?.querySelector?.('[data-media="source_start"]');
    if (input) {
      const plan = this.options.slipPreview(this.selected, Number(clip?.source_start));
      const protection=this.options.mutationIssue?.('media_slip',{clip_id:this.selected}) || '';
      input.disabled = busy || saving || Boolean(protection || plan?.issue);
      input.title = busy || saving ? 'Wait for the current changes to finish saving before slipping.' : protection || plan?.issue || 'Choose source content without moving or resizing this occurrence.';
    }
  }
  async slipTo(sourceStart, input = null) {
    const id = this.selected, projectId = this.project()?.id, typed = input?.value;
    if (!id || !projectId || this.options.busy() || this.options.trimBusy?.() || typeof this.options.slip !== 'function') return null;
    try { return await this.options.slip(id, sourceStart); }
    catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; return null; }
    finally {
      // Restore a rejected value or show the canonical saved source time without
      // overwriting later typing or a different selected/project inspector.
      if (input && this.project()?.id === projectId && this.selected === id && input.value === typed) {
        const clip = this.clips().find(row => row.id === id); if (clip) input.value = String(clip.source_start);
      }
      this.updateSlipAvailability();
    }
  }
  nudgeSlip(direction) {
    if (![-1, 1].includes(direction)) return null;
    const clip = this.clips().find(row => row.id === this.selected);
    return clip ? this.slipTo(Math.round((Number(clip.source_start) + direction * this.slipFrame()) * 1e9) / 1e9) : null;
  }
  renderImportQueue() {
    const queue = this.importQueue, here = queue?.projectId === this.project()?.id;
    this.updateImportAvailability();
    const panel = this.importQueuePanel;
    if (!panel) return;
    panel.hidden = !queue || !here;
    if (!queue || !here) return;
    const ready = queue.items.filter(item => item.status === 'ready').length;
    const active = queue.items.findIndex(item => item.status === 'importing');
    panel.querySelector('.media-import-summary').textContent = `Import queue · ${ready} / ${queue.items.length} ready`;
    panel.querySelector('.media-import-note').textContent = queue.note || '';
    panel.querySelector('.media-import-progress').textContent = queue.running
      ? queue.stopRequested ? 'Stopping import. Completed files stay in this project.' : `Importing ${Math.max(1, active + 1)} of ${queue.items.length}. Each file is prepared before the next starts.`
      : queue.reason || `${ready} files ready. Place media on the timeline when you choose.`;
    const stop = panel.querySelector('[data-stop-import-queue]');
    stop.hidden = !queue.running; stop.disabled = queue.stopRequested;
    const list = panel.querySelector('.media-import-list'); list.replaceChildren();
    const labels = {queued:'Queued',importing:'Importing',ready:'Ready',failed:'Needs attention',cancelled:'Stopped',not_imported:'Not imported'};
    for (const item of queue.items) {
      const row = document.createElement('li'); row.className = 'media-import-item'; row.dataset.status = item.status;
      row.textContent = `${item.name} · ${labels[item.status]}`; if (item.message) row.title = item.message; list.append(row);
    }
  }
  stopImports({cancelCurrent = true} = {}) {
    const queue = this.importQueue;
    if (!queue?.running || queue.projectId !== this.project()?.id) return false;
    queue.stop();
    if (cancelCurrent) Promise.resolve(this.options.cancelImport?.()).catch(error => { if (queue.projectId === this.project()?.id) this.status.textContent = error.message; });
    return true;
  }
  async uploadFiles(files) {
    if (!files?.length) return null;
    if (this.options.busy() || this.uploading || this.importQueue?.running) { this.status.textContent = 'Wait for the current import or edit to finish before adding more files.'; return null; }
    let plan;
    try { plan = planMediaImports(files, this.project()); }
    catch (error) { this.status.textContent = error.message; return null; }
    const queue = new MediaImportQueue({projectId:this.project().id, files:plan.files,
      currentProjectId:() => this.project()?.id,
      importFile:(file, shouldContinue) => this.upload(file, {shouldContinue}),
      changed:() => this.renderImportQueue()});
    queue.note = plan.note; this.importQueue = queue;
    if (this.importQueuePanel) this.importQueuePanel.open = true;
    await queue.run();
    if (queue.projectId === this.project()?.id) {
      // Collapse a successful receipt once, not on future renders. Users can
      // reopen it, while failed/stopped batches keep their next steps visible.
      if (this.importQueuePanel && !queue.stopRequested && queue.items.every(item => item.status === 'ready')) this.importQueuePanel.open = false;
      this.render();
    }
    return queue;
  }
  async upload(file, {shouldContinue = () => true} = {}) {
    const stopped = () => ({status:'cancelled', message:'Import stopped before the next file was sent.'});
    if (!shouldContinue()) return stopped();
    if (this.options.busy() || this.uploading || !this.project()) return {status:'blocked',message:'Another operation is active. Choose this file again when it finishes.'};
    const projectId = this.project().id;
    if (!this.project().draft) {
      if (!this.options.prepareEmptyImport) return {status:'blocked',message:'Open an edit before importing media.'};
      try {
        const consumed = await this.options.prepareEmptyImport(file, {shouldContinue});
        if (!shouldContinue() || this.project()?.id !== projectId) return stopped();
        if (consumed || !this.project().draft) {
          this.render();
          if (this.project().draft) { this.status.textContent = 'Recording ready in the timeline. Add more video, audio or images here.'; return {status:'ready'}; }
          return {status:'failed',message:'The recording was not added. Check the import message and choose it again.'};
        }
      } catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; return {status:error?.name === 'AbortError' || error.message === 'Cancelled' ? 'cancelled' : 'failed',message:error.message}; }
      if (this.options.busy() || this.project()?.id !== projectId) return stopped();
    }
    this.options.pause(); this.status.textContent = `Checking storage for ${file.name}.`;
    if (this.storageStatus) { this.storageStatus.textContent = ''; this.storageStatus.hidden = true; }
    if (this.storageDetails) this.storageDetails.hidden = true;
    try {
      if (!(await this.flush())) return {status:'failed',message:this.status.textContent || 'Save pending clip changes before importing media.'};
      if (!shouldContinue()) return stopped();
      this.uploading = true;
      this.options.busyChanged?.();
      await this.options.flushSettings(projectId);
      if (this.project()?.id !== projectId || !shouldContinue()) return stopped();
      const result = await this.options.uploadFile(file, projectId, (message, storage) => {
        if (this.project()?.id !== projectId) return;
        this.status.textContent = `${message}: ${file.name}`;
        const info = this.storageStatus || this.root.querySelector('.media-storage');
        if (info) { info.textContent = storage || ''; info.hidden = !storage; }
        if (this.storageDetails) this.storageDetails.hidden = !storage;
      });
      if (this.project()?.id === projectId) this.status.textContent = 'Preparing preview and waveform… Use Stop process to cancel.';
      await this.options.acceptUpload(result, projectId);
      if (this.project()?.id === projectId) { this.render(); this.status.textContent = result.import_stop_too_late
        ? 'Import completed before Stop reached the server. The file remains in Media.'
        : 'Ready. Add the file at the playhead.'; }
      return result.import_stop_too_late ? {status:'ready',stop:true,message:'The current file finished before Stop reached the server and remains in Media. Remaining files were not imported.'} : {status:'ready'};
    } catch (error) {
      if (this.project()?.id === projectId) {
        this.status.textContent = error.message;
        if (this.storageDetails && this.storageStatus?.textContent && error?.name !== 'AbortError' && error.message !== 'Cancelled') this.storageDetails.open = true;
      }
      return {status:error?.name === 'AbortError' || error.message === 'Cancelled' ? 'cancelled' : 'failed',message:error.message};
    } finally {
      this.uploading = false;
      this.options.busyChanged?.();
      // Cards rendered during acceptance still saw uploading=true. Refresh only
      // this project's controls so Review/Append unlock without another action.
      if (this.project()?.id === projectId) this.render();
    }
  }
  destinationOptions() { return this.destinationTrackId ? {trackId:this.destinationTrackId} : {}; }
  makeDestinationControl(scope) {
    const row=document.createElement('label');row.className='media-destination-control';row.dataset.destinationScope=scope;row.dataset.editorShortcuts='off';
    const caption=document.createElement('span');caption.textContent='Destination track';
    const select=document.createElement('select');select.dataset.mediaDestination=scope;select.setAttribute('aria-label',scope==='audioSource'?'Selected audio destination track':scope==='source'?'Source shot destination track':'Media pool destination track');
    const note=document.createElement('small');note.className='media-destination-note';
    row.append(caption,select,note);this.destinationControls.add(row);
    select.addEventListener('change',()=>{
      if(select.disabled)return;
      this.destinationTrackId=select.value;
      this.updateDestinationControls();this.updateImportAvailability();this.syncSourceMonitor();
    });
    return row;
  }
  updateDestinationControls() {
    if(typeof this.options.trackState!=='function')return;
    const state=this.options.trackState(this.project()), selected=this.destinationTrackId||'';
    for(const row of this.destinationControls||[]) {
      const select=row.querySelector('select'),note=row.querySelector('small');
      const choices=state.tracks.filter(track=>track.kind!=='text' && (row.dataset.destinationScope!=='source'||track.kind==='visual') && (row.dataset.destinationScope!=='audioSource'||track.kind==='audio'));
      const missing=selected && !choices.some(track=>track.id===selected);
      const signature=JSON.stringify([choices.map(track=>[track.id,track.name,track.kind]),selected,Boolean(missing)]);
      if(row.destinationSignature!==signature) {
        row.destinationSignature=signature;select.replaceChildren();
        const option=(value,label)=>{const node=document.createElement('option');node.value=value;node.textContent=label;select.append(node);};
        option('','Automatic');
        for(const track of choices)option(track.id,`${track.name} (${track.kind})`);
        if(missing)option(selected,'Unavailable or incompatible selected track');
        select.value=selected;
      }
      row.hidden=!state.enabled&&!state.issue&&!selected;
      select.disabled=Boolean(this.options.busy()||this.uploading||this.importQueue?.running||this.placing||this.shotReview?.pending||state.issue);
      const message=state.issue||(missing?'Choose another destination or Automatic. Nothing will be rerouted.':selected?row.dataset.destinationScope==='audioSource'?'Uses exactly this audio track and its saved gain / mute. Occupied placements are refused; no layers move.':'Uses exactly this track and its saved gain / mute. Occupied placements are refused; Insert opens time.':'Automatic chooses or creates a compatible neutral-level track. This choice is local, not a project change.');
      select.title=message;note.textContent=message;
    }
  }
  placementPreview(assetId,time,options={},planner=null) {
    if(typeof this.options.placementPreview!=='function')return{issue:'Track placement is unavailable. Reload the editor.'};
    const plan=(planner||this.options.placementPreview)(assetId,time,options);
    if(!plan || typeof plan.issue!=='string')return{issue:'Placement could not be verified. Reload the editor.'};
    if(plan.issue)return plan;
    if(options.insert || options.append) {
      const issue=libraryInsertReadiness(this.project(),options.append?plan.start:time,plan.end-plan.start);
      if(issue)return{issue};
    }
    return plan;
  }
  // Resolve only this asset's marks. An invalid active selection never falls
  // through to older saved marks or a different open source's selection.
  dragSelection(assetId) {
    const project=this.project(),asset=project?.assets?.[assetId];
    if(!asset || !['video','audio'].includes(asset.kind))return null;
    try {
      let selected=this.shotReview?.sourceSelection?.(assetId);
      if(selected?.issue)return selected;
      if(selected==null)selected=(asset.kind==='video'?readLibraryShotMarks(project,assetId)
        :this.options.audioSource?.readMarks?.(project,assetId))?.range;
      if(selected==null)return null;
      const range=asset.kind==='video'?libraryShotRange(asset,selected.source_start,selected.source_end)
        :this.options.audioSource?.range?.(asset,selected.source_start,selected.source_end);
      if(!range || range.issue)return {issue:range?.issue||'This audio selection could not be verified.'};
      return {sourceStart:range.source_start,sourceEnd:range.source_end};
    } catch(error) {return {issue:error?.message||'Review source In / Out before dragging.'};}
  }
  insertionIssue(assetId, time, {sourceStart=0,sourceEnd}={}) {
    const project = this.project(), asset = project?.assets?.[assetId];
    if (!project?.draft || asset?.kind !== 'video' || asset.status !== 'ready') return 'Choose a ready video to insert.';
    if (this.options.busy() || this.uploading || this.importQueue?.running) return 'Wait for the current operation before inserting.';
    if (!Number.isFinite(asset.duration) || asset.duration < .08) return 'This video has no usable duration.';
    try {const range=libraryShotRange(asset,sourceStart,sourceEnd??asset.duration);
      return libraryInsertReadiness(project, time, range.source_end-range.source_start);
    } catch(error) {return error.message;}
  }
  async place(assetId, time, {append = false, insert = false, ...destination} = {}, context={}) {
    const project = this.project(), projectId = project?.id, revision = project?.revision;
    const viewToken=this.options.sourceMonitor?.token?.();
    const explicit=Object.hasOwn(destination,'trackId'),marked=Object.hasOwn(destination,'sourceStart')||Object.hasOwn(destination,'sourceEnd');
    const strict=marked||typeof context.isCurrent==='function'||explicit||Boolean(project?.manual && Object.hasOwn(project.manual,'layer_tracks'));
    const sourceIdentity=libraryPreviewContentIdentity(project?.assets?.[assetId]);
    const sourceCurrent=()=>libraryPreviewContentIdentity(this.project()?.assets?.[assetId])===sourceIdentity
      && (typeof context.isCurrent!=='function'||context.isCurrent()===true);
    const blocked = () => this.options.busy() || this.uploading || this.importQueue?.running || this.shotReview?.pending;
    if (!projectId || !project.draft || blocked() || this.placing || typeof assetId !== 'string' || typeof append !== 'boolean' || typeof insert !== 'boolean' || append && insert) return null;
    const valid = () => {
      const current = this.project(), asset = current?.assets?.[assetId];
      if (current?.id !== projectId || !current.draft || blocked() || asset?.status !== 'ready'
        || this.options.sourceMonitor?.token?.()!==viewToken || strict && current.revision!==revision || !sourceCurrent()) return false;
      if(marked) {
        try {
          const range=asset.kind==='video'?libraryShotRange(asset,destination.sourceStart,destination.sourceEnd)
            :asset.kind==='audio'?this.options.audioSource?.range?.(asset,destination.sourceStart,destination.sourceEnd):null;
          if(!range || range.issue)return false;
        } catch {return false;}
      }
      if(typeof this.options.placementPreview==='function') {
        const plan=this.placementPreview(assetId,time,{append,insert,...destination});
        if(plan.issue){this.status.textContent=plan.issue;return false;}
      } else if(explicit)return false;
      if (append) return asset.kind === 'video';
      if (insert) return current.revision === revision && !this.insertionIssue(assetId, time, destination);
      const duration = Number(current.editor_sequence?.duration ?? current.draft.output_duration);
      return ['video','audio','image'].includes(asset.kind) && Number.isFinite(time) && time >= 0 && Number.isFinite(duration) && time <= duration - .08 + 1e-9;
    };
    if (!valid()) return null;
    this.placing = true;
    this.updateImportAvailability();this.syncSourceMonitor();
    this.options.pause();
    try {
      if (!(await this.flush()) || !valid()) return null;
      await this.options.flushSettings(projectId);
      if (!valid()) return null;
      const previousIds = new Set((this.project().manual?.media_clips || []).map(clip => clip.id));
      const stillCurrent = () => this.project()?.id === projectId && this.project()?.revision === revision && this.options.sourceMonitor?.token?.()===viewToken && sourceCurrent();
      const sourcePayload=marked?{source_start:destination.sourceStart,...(append||insert
        ?{source_end:destination.sourceEnd}:{end:Math.min(Number(this.project().editor_sequence?.duration??this.project().draft.output_duration),time+Math.round((destination.sourceEnd-destination.sourceStart)*1e9)/1e9)})}:{};
      const updated = await this.options.edit(append ? 'media_append' : insert ? 'media_insert' : 'media_add',
        {asset_id:assetId, ...(append ? {} : {start:time}), ...sourcePayload, ...(explicit?{track_id:destination.trackId}:{})}, insert||strict ? {isCurrent:stillCurrent,strictRevision:true} : undefined);
      if (insert && !updated && this.project()?.id === projectId) this.status.textContent = 'The edit changed or is busy. Review the insertion point and try again; nothing was inserted.';
      if (!updated || updated.id !== projectId || this.project()?.id !== projectId || this.options.sourceMonitor?.token?.()!==viewToken) return null;
      this.selected = updated.manual?.media_clips?.filter(clip => clip.asset_id === assetId && !previousIds.has(clip.id)).at(-1)?.id || this.selected;
      this.render();
      this.status.textContent = append ? 'Video appended to the timeline. Undo restores the previous edit.' : insert ? 'Video inserted. Crossing clips were split and later items moved together. Undo restores the previous edit.' : 'Media placed on the timeline. Undo removes this occurrence.';
      return updated;
    } catch (error) { if (this.project()?.id === projectId && this.options.sourceMonitor?.token?.()===viewToken) this.status.textContent = error.message; return null; }
    finally { this.placing = false; this.updateImportAvailability(); this.syncSourceMonitor(); }
  }
  async add(assetId) {
    if(typeof this.options.placementPreview==='function')return this.place(assetId,Math.min(this.options.time(),Math.max(0,this.options.duration()-.1)),this.destinationOptions());
    if (this.options.busy()) return;
    this.options.pause();
    try {
      if (!(await this.flush())) return;
      const result = await this.options.edit('media_add', {asset_id:assetId,start:Math.min(this.options.time(), Math.max(0,this.options.duration()-.1))});
      if (result) { this.selected = result.manual?.media_clips?.at(-1)?.id; this.render(); }
    } catch (error) { this.status.textContent = error.message; }
  }
  async append(assetId) {
    if(typeof this.options.placementPreview==='function')return this.place(assetId,this.options.duration(),{append:true,...this.destinationOptions()});
    const project = this.project(), projectId = project?.id, asset = project?.assets?.[assetId];
    if (this.options.busy() || this.uploading || !projectId || !project.draft || asset?.kind !== 'video' || asset.status !== 'ready') return;
    this.options.pause();
    try {
      if (!(await this.flush()) || this.project()?.id !== projectId || this.options.busy() || this.uploading) return;
      const current = this.project(), ready = current?.assets?.[assetId];
      if (!current?.draft || ready?.kind !== 'video' || ready.status !== 'ready') return;
      const result = await this.options.edit('media_append', {asset_id:assetId});
      if (this.project()?.id !== projectId) return;
      if (!result) throw new Error('The edit is busy. Try appending the video again.');
      if (result.id !== projectId) return;
      this.selected = result.manual?.media_clips?.at(-1)?.id; this.render();
    } catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; }
  }
  closeSourceMonitor() { this.sourceReviewRequest=(this.sourceReviewRequest||0)+1;if(this.shotReview?.docked)this.shotReview.close(); }
  pauseSourceMonitor() { this.shotReview?.pauseSource?.(); }
  syncSourceMonitor() { this.shotReview?.syncSource?.(); }
  reviewAudio(assetId) {
    const issue=this.audioSourceIssue(assetId);if(issue){this.status.textContent=issue;return false;}
    const project=this.project(),projectId=project.id,viewToken=this.options.viewToken?.(),monitor=this.options.sourceMonitor,audio=this.options.audioSource;
    const opener=document.activeElement;
    // Opening is read-only navigation: the broad clean-state gate precedes the
    // pane/group transition, and neither this branch nor its controller flushes.
    if(!monitor || monitor.open?.()!==true)return false;
    if(this.project()!==project || this.options.viewToken?.()!==viewToken || this.audioSourceIssue(assetId))return false;
    this.closeSourceMonitor();audio.pauseProgram?.();
    const root=document.createElement('section');root.className='library-source-monitor audio-source-review';root.dataset.sourceAssetId=assetId;root.dataset.sourceProjectId=projectId;root.dataset.editorShortcuts='off';root.setAttribute('role','region');root.setAttribute('aria-label','Audio source review');root.tabIndex=-1;
    const destinationControl=this.makeDestinationControl('audioSource');let controller=null;
    const owner={audioSource:true,docked:true,get open(){return controller?.open ?? true;},get pending(){return Boolean(controller?.pending);},
      close:restore=>controller?.close(restore),pauseSource:()=>controller?.pausePreview(),syncSource:()=>controller?.sync(),
      captureRepair:id=>controller?.captureRepair(id),acceptRepair:(...args)=>controller?.acceptRepair(...args),
      sourceSelection:id=>controller?.sourceSelection?.(id)};
    const owned=()=>this.shotReview===owner && this.project()?.id===projectId && this.options.viewToken?.()===viewToken;
    this.root.prepend(root);this.root.dataset.sourceMonitorOpen='true';this.shotReview=owner;
    const dispose=(_controller,{restoreFocus=false,ownedFocus=false}={})=>{
      const returnFocus=owned() && restoreFocus && ownedFocus;
      this.destinationControls.delete(destinationControl);root.remove();
      if(this.shotReview===owner){this.shotReview=null;delete this.root.dataset.sourceMonitorOpen;}
      if(returnFocus){
        const fallback=[...(this.library?.querySelectorAll?.('[data-review-audio]')||[])].find(node=>node.dataset.reviewAudio===assetId);
        const target=opener?.isConnected&&!opener.disabled?opener:fallback;
        if(target?.isConnected && !target.disabled && !target.closest?.('[hidden],[inert]'))target.focus?.({preventScroll:true});
      }
    };
    try{
      controller=audio.create(root,{
        snapshot:()=>{
          const current=this.project(),asset=current?.assets?.[assetId];
          return {projectId:current?.id,viewToken:this.options.viewToken?.(),revision:current?.revision,assetId,
            sourceIdentity:libraryPreviewContentIdentity(asset),name:asset?.name,url:asset?.url,duration:asset?.duration,
            at:this.options.time?.(),editDuration:this.options.duration?.(),trackId:this.destinationTrackId||'',
            visible:owned() && monitor.visible?.()!==false,issue:this.audioSourceIssue(assetId,owner)};
        },
        range:(a,b)=>audio.range(this.project()?.assets?.[assetId],a,b),
        readMarks:()=>audio.readMarks?.(this.project(),assetId),
        saveMarks:range=>audio.saveMarks?.(this.project(),assetId,range),clearMarks:()=>audio.clearMarks?.(this.project(),assetId),
        destinationControl,plan:range=>audio.plan(this.project(),assetId,this.options.time?.(),range,this.destinationOptions()),
        pauseProgram:element=>audio.pauseProgram?.(element),
        place:(plan,context)=>audio.place(plan,context,owner),closed:dispose,
      });
      if(!controller || typeof controller.sync!=='function' || typeof controller.close!=='function')throw new Error('Audio source controls could not start. Reload the editor.');
      this.updateDestinationControls();controller.sync();root.scrollIntoView?.({block:'start',inline:'nearest'});root.focus?.({preventScroll:true});
      return true;
    }catch(error){controller?.close?.();dispose(null);this.status.textContent=error?.message || 'Audio source review could not open.';return false;}
  }
  poolSourceIssue(assetId, sharedIssue) {
    const project=this.project(),asset=project?.assets?.[assetId],monitor=this.options.sourceMonitor;
    if(!project?.draft||asset?.id!==assetId||asset.kind!=='video'||asset.status!=='ready'||typeof asset.url!=='string'||!asset.url)return 'Choose a ready imported video with an available source preview.';
    if(!monitor||typeof monitor.poolIssue!=='function')return 'Reload the media workspace before browsing sources.';
    if(this.options.busy()||this.uploading||this.importQueue?.running||this.placing||this.pending?.size||this.saving||this.frameEditor?.pending||this.frameEditorState?.dragging||this.shotReview?.pending)return 'Finish the current save or gesture before opening the source.';
    return sharedIssue===undefined?monitor.poolIssue()||'':sharedIssue;
  }
  async reviewShot(assetId, {match=null,browse=false}={}) {
    if(browse){const issue=this.poolSourceIssue(assetId);if(issue){this.status.textContent=issue;return false;}}
    if(this.options.busy() || this.uploading || this.placing || this.shotReview?.pending)return;
    const monitor=this.options.sourceMonitor,viewToken=monitor?.token?.();
    const opener=monitor?document.activeElement:null;
    const request=this.sourceReviewRequest=(this.sourceReviewRequest||0)+1;
    const projectId=this.project()?.id;
    if(match){
      const latest=this.sourceMatchPlan(match.clipId,match.editTime);
      if(latest.issue || latest.token!==match.token || latest.assetId!==assetId)throw new Error(latest.issue||"The clip or source changed. Open the source again from the current edit.");
    }
    this.options.pause();
    // Source matching is navigation only: never flush or submit a pending edit.
    // The legacy In / Out command retains its preflight; direct browsing is read-only.
    if(!match && !browse && !(await this.flush()))return;
    if(this.project()?.id!==projectId || this.options.busy() || this.uploading || request!==this.sourceReviewRequest
      || (monitor && monitor.token?.()!==viewToken))return;
    if(match){
      const latest=this.sourceMatchPlan(match.clipId,match.editTime);
      if(latest.issue || latest.token!==match.token)throw new Error(latest.issue||"The clip or source changed. Open the source again from the current edit.");
      this.frameEditor?.close();
    }
    const project=this.project(),asset=project?.assets?.[assetId];
    let at=match?match.editTime:Number(this.options.time?.()),insertReason=libraryInsertReadiness(project,at);
    if(browse){const issue=this.poolSourceIssue(assetId);if(issue){this.status.textContent=issue;return false;}}
    if(monitor && monitor.open?.()===false)return;
    if(this.project()?.id!==projectId || request!==this.sourceReviewRequest || (monitor && monitor.token?.()!==viewToken))return;
    libraryShotRange(asset,0,Number(asset?.duration));
    const remembered=readLibraryShotMarks(project,assetId);
    let savedRange=remembered.range;
    this.shotReview?.close();
    let closed=false;
    let revision=project.revision;
    const assetIdentity=a=>JSON.stringify([a?.id,a?.url,a?.duration,a?.kind,a?.status,a?.width,a?.height]);
    let identity=assetIdentity(asset);
    const sameSource=()=>{const p=this.project();return p?.id===projectId && !!p.assets?.[assetId]
      && assetIdentity(p.assets[assetId])===identity && (!monitor || monitor.token?.()===viewToken);};
    const mounted=()=>!closed && dialog.open && this.shotReview===dialog;
    const current=()=>mounted() && sameSource() && this.project().revision===revision
      && (Boolean(monitor) || !match || librarySourceMatch(this.project(),match.clipId,match.editTime).token===match.token);
    const make=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};
    const text=(node,value)=>{if(node.textContent!==value)node.textContent=value;};
    const dialog=make(monitor?'section':'dialog');dialog.className=monitor?'library-shot-review library-source-monitor':'library-shot-review';dialog.setAttribute('aria-labelledby','libraryShotTitle');
    if(monitor){dialog.setAttribute('role','region');dialog.dataset.sourceAssetId=assetId;dialog.dataset.sourceProjectId=projectId;dialog.dataset.editorShortcuts='off';dialog.tabIndex=-1;dialog.docked=true;}
    const title=make('h3',monitor?'Source monitor':'Review source shot');title.id='libraryShotTitle';
    const name=make('p',asset.name);name.dir='auto';name.className='library-shot-name';
    const origin=match?make('p',monitor?`Original picture ${match.sourceTime.toFixed(3)} s from edit ${match.editTime.toFixed(3)} s (${match.speed}x). Source sound is 1x.`:`Opening original picture ${match.sourceTime.toFixed(3)} s from edit ${match.editTime.toFixed(3)} s (${match.speed}× picture). Original source sound plays at normal speed, not the edited mix. Effects are not applied; existing In / Out marks are unchanged.`):null;
    if(origin){origin.className='library-shot-match-origin';origin.dataset.shotMatchOrigin='true';origin.setAttribute('role','status');}
    const explanation=make('p','Mark source In / Out, then insert at the edited playhead or append after the edit. Insertion splits supported crossing media, audio and text, then moves later items together. Motion and fade-interior crossings remain blocked. Original file unchanged; Undo is available.');
    const video=make('video');video.controls=true;video.playsInline=true;video.preload='metadata';video.src=asset.url;video.setAttribute('aria-label',`Source preview: ${asset.name}`);
    const form=make('form');form.className='library-shot-range';
    const trackControl=typeof this.options.placementPreview==='function'?this.makeDestinationControl('source'):null;
    const overwriteBox=monitor&&this.options.overwritePreview?make('details'):null;
    let overwrite=null,overwriteStatus=null,overwriteShown=null,overwriteCache=null;
    if(overwriteBox){
      overwriteBox.className='source-track-overwrite';overwriteBox.dataset.trackOverwrite='true';
      const heading=make('summary','Overwrite on one track');overwrite=make('button','Overwrite this track');overwrite.type='submit';overwrite.disabled=true;overwrite.dataset.shotOverwrite='true';
      overwriteStatus=make('p');overwriteStatus.dataset.overwriteStatus='true';overwriteStatus.className='library-shot-insert-help';overwriteStatus.setAttribute('role','status');
      overwriteStatus.id='sourceTrackOverwriteStatus';overwrite.setAttribute('aria-describedby',overwriteStatus.id);
      overwriteBox.append(heading,overwriteStatus,overwrite);
    }
    const fields={},markButtons={},jumpButtons={},listeners=[];let frameReview=null;
    const listen=(target,type,handler)=>{target.addEventListener(type,handler);listeners.push(()=>target.removeEventListener(type,handler));};
    for(const [key,label,value]of [['in','Source In (seconds)',savedRange?.source_start??0],['out','Source Out (seconds)',savedRange?.source_end??asset.duration]]){
      const row=make('label',label),input=make('input');input.type='number';input.required=true;input.min='0';input.max=String(asset.duration);input.step='any';input.dir='ltr';input.value=String(value);input.dataset.shotPoint=key;row.append(input);form.append(row);fields[key]=input;
      const mark=make('button',key==='in'?'Set In at playhead':'Set Out at playhead');mark.type='button';mark.dataset.shotMark=key;
      mark.setAttribute('aria-keyshortcuts',key==='in'?'I':'O');markButtons[key]=mark;
      listen(mark,'click',()=>markAtPlayhead(key));
      const jump=make('button',key==='in'?'Jump to In':'Jump to Out');jump.type='button';jump.dataset.shotJump=key;jumpButtons[key]=jump;
      listen(jump,'click',()=>{
        if(!sourceReady())return;
        try{const selected=range();frameReview?.clear();stopPreview();video.currentTime=key==='in'?selected.source_start:selected.source_end;update();}
        catch(error){status.textContent=error.message;}
      });
      const controls=make('div');controls.className='library-shot-point-actions';controls.dataset.shotPointActions=key;controls.append(mark,jump);form.append(controls);
    }
    const status=make('p','Loading source preview…');status.setAttribute('role','status');status.className='library-shot-status';
    if(monitor){status.dataset.sourceDrag='true';status.title='Drag this selection to the timeline, or use Insert / Append below.';}
    const preview=make('button','Play selected shot');preview.type='button';preview.dataset.shotPreview='true';
    const monitorHelp=make('p','Source monitor shortcuts: I sets In; O sets Out, outside text fields. Jumping or changing marks pauses playback. Ordinary playback follows the browser.'+(monitor&&typeof this.options.sourceFrames==='function'?' Previous / Next frame shows decoded original stills; In starts at that frame and Out includes it.':''));monitorHelp.className='library-shot-insert-help';
    const append=make('button','Append selected shot to end');append.type='submit';append.dataset.shotAppend='true';append.disabled=true;
    const insert=make('button',Number.isFinite(at)?`Insert at edit playhead (${at.toFixed(3)} s)`:'Insert at edit playhead');insert.type='submit';insert.dataset.shotInsert='true';insert.disabled=true;
    const insertHelp=make('p',insertReason||'Insert splits crossing static media/audio/text and moves later A/B footage, framing and layers together. Motion, fade-interior and edited automatic-caption crossings are blocked.');insertHelp.className='library-shot-insert-help';
    const appendHelp=monitor?make('p'):null,receipt=monitor?make('p'):null;
    if(monitor){
      status.id='libraryShotStatus';status.dir='auto';
      for(const [button,note,key]of [[append,appendHelp,'Append'],[insert,insertHelp,'Insert']]){
        note.id=`libraryShot${key}Help`;note.dataset.shotPlacementHelp=key.toLowerCase();note.dir='auto';
        note.setAttribute('aria-live','off');button.setAttribute('aria-describedby',note.id);
      }
      receipt.className='library-source-receipt';receipt.dataset.shotPlacementReceipt='true';receipt.dir='auto';receipt.hidden=true;
      receipt.setAttribute('role','status');receipt.setAttribute('aria-live','polite');receipt.setAttribute('aria-atomic','true');
    }
    let lastPlacement=null;
    const close=make('button',monitor?'Close source':'Keep current edit');close.type='button';close.dataset.shotKeep='true';
    const refresh=monitor?make('button','Use current edit'):null;
    if(refresh){refresh.type='button';refresh.dataset.shotRefresh='true';refresh.hidden=true;}
    const destination=monitor?make('p'):null;
    if(destination){destination.className='library-source-destination';destination.dataset.shotDestination='true';destination.dir='auto';destination.setAttribute('aria-live','off');}
    const saveMarks=make('button','Save source marks');saveMarks.type='button';saveMarks.dataset.shotSaveMarks='true';saveMarks.disabled=true;
    const resetMarks=make('button','Clear saved marks');resetMarks.type='button';resetMarks.dataset.shotResetMarks='true';
    const marksStatus=make('p');marksStatus.className='library-shot-insert-help';marksStatus.dataset.shotMarksStatus='true';marksStatus.setAttribute('role','status');
    const localScope='Stored only in this browser, not inside the project. Saving marks does not change the edit.';
    marksStatus.textContent=remembered.state==='saved'?`Saved source marks restored. ${localScope}`
      : remembered.state==='stale'||remembered.state==='invalid'?`Saved marks do not match this source or are unreadable. Review the full source and save new marks. ${localScope}`
      : remembered.state==='unavailable'?`Browser storage is unavailable; source marks cannot be remembered. Your selection still works for this review.`:localScope;
    let metadata=false,seenMetadata=false,metadataError='',busy=false,selectedPlayback=null,playPending=false,playRequest=0,busyRefreshTimer=null;
    let matchSeekAttempted=false,repairInteraction=0,repairRestore=null;
    listen(dialog,'pointerdown',()=>{repairInteraction++;});listen(dialog,'keydown',()=>{repairInteraction++;});listen(dialog,'input',()=>{repairInteraction++;});
    const hostIssue=()=>monitor?.issue?.()||'';
    const blocked=()=>closed||!dialog.open||busy||this.placing||this.options.busy()||this.uploading||!current()||!!hostIssue();
    const metadataMatches=()=>Number.isFinite(video.duration)&&Math.abs(video.duration-Number(asset.duration))<=.25;
    const range=()=>{
      if(!fields.in.value.trim()||!fields.out.value.trim())throw new Error('Enter both source In and Out before using this selection.');
      return libraryShotRange(asset,Number(fields.in.value),Number(fields.out.value));
    };
    const playbackLabel=()=>{
      const playing=playPending||!video.paused;
      preview.textContent=playing?(selectedPlayback?'Pause selected shot':'Pause source preview'):selectedPlayback?'Resume selected shot':'Play selected shot';
      let valid=true;try{range();}catch{valid=false;}
      // Even an invalid range must leave a playing native preview pausable.
      preview.disabled=blocked()||!metadata||!metadataMatches()||(!valid&&!playing);
    };
    const stopPreview=()=>{++playRequest;playPending=false;selectedPlayback=null;video.pause();playbackLabel();};
    const watchBusy=()=>{
      clearTimeout(busyRefreshTimer);busyRefreshTimer=null;
      if(busy||!current()||!(this.options.busy()||this.uploading))return;
      // The host exposes busy as a getter, not a subscription. Only watch an
      // observed busy period; paused controls must recover without a new load.
      const recheck=()=>{
        busyRefreshTimer=null;if(closed||!dialog.open)return;
        if(current()&&(this.options.busy()||this.uploading))busyRefreshTimer=setTimeout(recheck,250);
        else update();
      };
      busyRefreshTimer=setTimeout(recheck,250);
    };
    const update=()=>{
      if(closed)return;
      if(monitor && (!sameSource() || monitor.visible?.()===false)){dialog.close();return;}
      if(monitor && !busy && current())at=Number(this.options.time?.());
      const unavailable=blocked(),sourceUnavailable=unavailable||!metadata||!metadataMatches()||Boolean(frameReview?.pending);
      if(refresh){refresh.hidden=busy||current();refresh.disabled=busy||this.placing||this.options.busy()||this.uploading||!!hostIssue();}
      if(destination){
        const duration=Number(this.project()?.editor_sequence?.duration??this.project()?.draft?.output_duration);
        destination.textContent=Number.isFinite(at)?`Edited destination: ${at.toFixed(3)} s. Edit end: ${Number.isFinite(duration)?duration.toFixed(3):'?'} s. Seek the timeline to change the destination.`:'Choose a destination on the edited timeline.';
        insert.textContent=Number.isFinite(at)?`Insert at ${at.toFixed(3)} s`:'Insert at edit playhead';
      }
      if(sourceUnavailable&&(!video.paused||playPending||selectedPlayback))stopPreview();
      resetMarks.disabled=unavailable;close.disabled=busy;video.controls=!sourceUnavailable;
      for(const key of ['in','out']){fields[key].disabled=sourceUnavailable;markButtons[key].disabled=sourceUnavailable||(key==='out'&&frameReview?.canMarkOut===false);
        text(markButtons[key],frameReview?.active?(key==='in'?'Set In at shown frame':'Set Out after shown frame'):(key==='in'?'Set In at playhead':'Set Out at playhead'));}
      let valid=false,rangeStatus='',rangeIssue='',appendPlan=null,insertPlan=null;
      try{const selected=range();valid=true;rangeStatus=`${(selected.source_end-selected.source_start).toFixed(3)} s selected · source ${selected.source_start.toFixed(3)}–${selected.source_end.toFixed(3)} · manual shot selection`;}
      catch(error){rangeStatus=rangeIssue=error.message;}
      let appendReason='';
      this.updateDestinationControls();
      if(monitor && valid){
        const selected=range(),length=selected.source_end-selected.source_start;
        insertReason=libraryInsertReadiness(this.project(),at,length);
        appendReason=libraryInsertReadiness(this.project(),Number(this.project()?.editor_sequence?.duration??this.project()?.draft?.output_duration),length);
        append.title=appendReason;
      }
      if(valid && typeof this.options.placementPreview==='function'){
        const selected=range(),sourceOptions={sourceStart:selected.source_start,sourceEnd:selected.source_end,...this.destinationOptions()};
        const planner=this.options.placementPlanner?.();
        appendPlan=this.placementPreview(assetId,at,{append:true,...sourceOptions},planner);
        insertPlan=this.placementPreview(assetId,at,{insert:true,...sourceOptions},planner);
        appendReason=appendReason||appendPlan.issue;insertReason=insertReason||insertPlan.issue;
      }
      append.title=appendReason;insert.title=insertReason;
      if(!monitor && insertReason)insertHelp.textContent=insertReason;
      append.disabled=sourceUnavailable||!valid||!!appendReason;saveMarks.disabled=sourceUnavailable||!valid;insert.disabled=sourceUnavailable||!valid||!!insertReason;
      if(overwriteBox){
        overwriteShown=null;overwrite.disabled=true;
        if(overwriteBox.open){
          const p=this.project(),rate=p?.settings?.fps??30;
          const d=valid?{asset_id:assetId,track_id:this.destinationTrackId||'',frame:Number.isFinite(at)?Math.round(at*rate):null,...range()}:null;
          const key=JSON.stringify([p?.id,p?.revision,d]),hint=this.options.overwriteIssue?.() || '';
          if(!overwriteCache || overwriteCache.p!==p || overwriteCache.key!==key){
            const plan=d?this.options.overwritePreview(p,d):{issue:'Enter valid Source In and Out.'};
            overwriteCache={p,key,plan,description:this.options.describeOverwrite(plan)};
          }
          const c=overwriteCache,issue=sourceUnavailable?(!current()?'Edit changed. Use current edit before overwriting.':busy?'Saving the marked shot.':'Wait for a ready source and a saved edit.'):hint||c.plan.issue;
          overwrite.disabled=!!issue;overwrite.title=issue||'Overwrite the displayed interval on this named track. One Undo restores all affected pieces.';
          text(overwriteStatus,issue||c.description);
          if(!issue)overwriteShown={key,detail:d};
        }
      }
      for(const jump of Object.values(jumpButtons))jump.disabled=sourceUnavailable||!valid;
      let sourceIssue='';
      if(monitor && busy)sourceIssue='Adding the selected source shot. Please wait.';
      else if(!current())sourceIssue=monitor?'The edit changed. Use current edit to review the new destination before adding another shot. Your source marks are kept.':'The edit or source changed. Close and review the current version; nothing was added.';
      else if(hostIssue())sourceIssue=hostIssue();
      else if(busy||this.placing||this.options.busy()||this.uploading)sourceIssue='The edit is busy. Source controls are paused until it finishes.';
      else if(!metadata||!metadataMatches())sourceIssue=metadataError||'Loading source preview…';
      else if(frameReview?.pending)sourceIssue='Wait for the original frame to finish decoding.';
      let summary=sourceIssue||rangeStatus;
      if(monitor){
        status.draggable=!sourceUnavailable&&valid;status.setAttribute('aria-disabled',String(!status.draggable));
        if(status.draggable)summary=`Drag selection · ${summary}`;
        // Explain each actual native command. These notes never admit an edit or
        // turn a guessed destination into a successful placement preview.
        for(const [button,note,reason,plan,kind]of [[append,appendHelp,appendReason,appendPlan,'Append'],[insert,insertHelp,insertReason,insertPlan,'Insert']]){
          const issue=sourceIssue||rangeIssue||reason;
          const span=plan&&!plan.issue&&Number.isFinite(plan.start)&&Number.isFinite(plan.end)&&plan.end>plan.start
            ? `Timeline ${plan.start.toFixed(3)}–${plan.end.toFixed(3)} s${plan.trackName?` on “${plan.trackName}”`:''}. `:'';
          note.dataset.state=button.disabled?'blocked':'ready';button.title=issue;
          text(note,issue?`${kind} unavailable: ${issue}`:span+(kind==='Insert'?'Opens time; later clips move together.':'Adds after the edit end; existing clips stay put.'));
        }
        if(lastPlacement && this.project()?.revision!==lastPlacement.revision){lastPlacement=null;text(receipt,'');receipt.hidden=true;}
      }
      // One final write: a quiet unchanged range must not churn its live region.
      text(status,summary);
      frameReview?.sync();playbackLabel();watchBusy();
    };
    if(overwriteBox)listen(overwriteBox,'toggle',update);
    if(trackControl)listen(trackControl.querySelector('select'),'change',update);
    const sourceReady=()=>{
      if(!blocked()&&metadata&&metadataMatches()&&!frameReview?.pending)return true;
      if(metadata&&!metadataMatches()){metadata=false;metadataError='Preview duration does not match source metadata. Reload the asset before using this selection.';}
      stopPreview();update();return false;
    };
    const checkMetadata=()=>{
      if(closed||!dialog.open)return;
      metadata=metadataMatches();metadataError=metadata?'':'Preview duration does not match source metadata. Reload the asset before using this selection.';
      if(metadata && repairRestore){
        const restore=repairRestore;repairRestore=null;
        if(current() && restore.epoch===repairInteraction && restore.dialog===dialog && Number.isFinite(restore.time)
          && restore.time>=0 && restore.time<video.duration){try{video.currentTime=restore.time;}catch{/* Keep the paused preview without forcing a stale clock. */}}
      }
      if(metadata && current() && match && !matchSeekAttempted){
        matchSeekAttempted=true;
        try{if(match.sourceTime>=video.duration)throw new Error("Source position is outside the loaded video.");video.currentTime=match.sourceTime;origin.textContent=monitor?`Original picture ${match.sourceTime.toFixed(3)} s from edit ${match.editTime.toFixed(3)} s (${match.speed}x). Source sound is 1x.`:`Opened original picture at ${match.sourceTime.toFixed(3)} s from edit ${match.editTime.toFixed(3)} s (${match.speed}× picture). Original source sound plays at normal speed, not the edited mix. Effects are not applied; existing In / Out marks are unchanged.`;}
        catch{origin.textContent="The source opened but the browser could not seek to the requested picture. Use its video controls to navigate; the edit and saved marks are unchanged.";}
      }
      if(!metadata){this.reportPreviewFailure(assetId,video.getAttribute?.('src') || video.src);stopPreview();}update();
    };
    listen(video,'loadedmetadata',()=>{seenMetadata=true;checkMetadata();});
    listen(video,'durationchange',()=>{if(seenMetadata)checkMetadata();});
    listen(video,'emptied',()=>{metadata=false;seenMetadata=false;metadataError='';stopPreview();update();});
    listen(video,'error',()=>{
      if(video.error?.code===1)return;
      metadata=false;metadataError=this.options.previewRepair?`Source preview is unavailable. Use Verify & repair preview for ${asset.name} in the Media pool.`:'Source preview is unavailable. Keep the edit and check this media file.';
      this.reportPreviewFailure(assetId,video.getAttribute?.('src') || video.src);stopPreview();update();
    });
    const checkPlayback=()=>{
      if(!sourceReady())return;
      if(selectedPlayback&&(video.currentTime>=selectedPlayback.source_end||video.currentTime<selectedPlayback.source_start)){
        const end=selectedPlayback.source_end,atEnd=video.currentTime>=end;
        stopPreview();if(atEnd)video.currentTime=Math.min(end,video.duration);
      }
      playbackLabel();
    };
    const claimSourcePlayback=()=>{
      if(!sourceReady())return;
      if(monitor && !video.paused)monitor.pauseProgram?.(video);
      checkPlayback();
    };
    listen(video,'play',claimSourcePlayback);listen(video,'playing',claimSourcePlayback);
    for(const type of ['timeupdate','seeking'])listen(video,type,checkPlayback);
    if(monitor)listen(video,'ratechange',()=>{if(video.playbackRate!==1)video.playbackRate=1;});
    listen(video,'ended',()=>{if(sourceReady()){stopPreview();update();}});
    listen(video,'pause',()=>{if(video.paused){if(playPending)++playRequest;playPending=false;playbackLabel();}});
    const marksChanged=()=>{stopPreview();update();marksStatus.textContent=`Selection changed; use Save source marks to remember it. ${localScope}`;};
    const markAtPlayhead=key=>{
      if(!sourceReady()||!Number.isFinite(video.currentTime))return false;
      const exact=frameReview?.mark(key);if(exact?.issue){status.textContent=exact.issue;return false;}
      fields[key].value=String(exact?exact.value:Math.min(Number(asset.duration),Math.max(0,Math.round(video.currentTime*1000)/1000)));marksChanged();return true;
    };
    listen(fields.in,'input',marksChanged);listen(fields.out,'input',marksChanged);
    if(monitor)for(const input of Object.values(fields))listen(input,'keydown',event=>{
      // Enter confirms the typed range, not the browser's implicit first submit.
      // Explicit keyboard activation of Append / Insert keeps its native path.
      if(event.key==='Enter'&&!event.isComposing&&event.keyCode!==229){event.preventDefault();event.stopPropagation();update();}
    });
    listen(dialog,'keydown',event=>{
      if(monitor && event.key==='Escape' && !event.defaultPrevented){event.preventDefault();event.stopPropagation();if(!busy)dialog.close(true);return;}
      if(event.defaultPrevented||event.repeat||event.isComposing||event.keyCode===229||event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||event.getModifierState?.('AltGraph'))return;
      const target=event.composedPath?.()[0]||event.target;
      if(target?.isContentEditable||target?.closest?.('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"]'))return;
      const key=String(event.key||'').toLowerCase();
      if((key==='i'||key==='o')&&markAtPlayhead(key==='i'?'in':'out')){event.preventDefault();event.stopPropagation();}
    });
    const marksCurrent=()=>{
      if(current())return true;
      update();marksStatus.textContent='The edit or source changed. Close and review the current version; saved marks are unchanged.';return false;
    };
    if(refresh)listen(refresh,'click',()=>{
      if(!mounted() || busy || this.placing || this.options.busy() || this.uploading || hostIssue())return;
      if(!sameSource()){dialog.close();return;}
      stopPreview();revision=this.project().revision;at=Number(this.options.time?.());
      if(origin)origin.textContent='Original source preview. The edit destination has been refreshed; source sound plays at normal speed, not the edited mix. Effects are not applied; In / Out marks are unchanged.';
      update();
    });
    listen(saveMarks,'click',()=>{
      if(!marksCurrent()||!sourceReady()||!form.reportValidity())return;
      try{savedRange=saveLibraryShotMarks(project,assetId,range());marksStatus.textContent=`Source marks saved: ${savedRange.source_start.toFixed(3)}–${savedRange.source_end.toFixed(3)} s. ${localScope}`;}
      catch(error){marksStatus.textContent=error.message;}
    });
    listen(resetMarks,'click',()=>{
      if(!marksCurrent()||blocked())return;
      try{clearLibraryShotMarks(project,assetId);savedRange=null;fields.in.value='0';fields.out.value=String(asset.duration);stopPreview();update();marksStatus.textContent=`Saved marks cleared. Full source selected. ${localScope}`;}
      catch(error){marksStatus.textContent=error.message;}
    });
    listen(preview,'click',async()=>{
      if(!sourceReady())return;
      frameReview?.clear();
      if(playPending||!video.paused){++playRequest;playPending=false;video.pause();playbackLabel();return;}
      let request;
      try{
        const selected=range();
        const resume=selectedPlayback&&video.currentTime>=selected.source_start&&video.currentTime<selected.source_end;
        selectedPlayback=selected;request=++playRequest;playPending=true;
        if(!resume)video.currentTime=selected.source_start;
        if(monitor){monitor.pauseProgram?.(video);video.playbackRate=1;}
        playbackLabel();await video.play();
        if(request!==playRequest)return;
        playPending=false;if(!sourceReady())return;checkPlayback();
      }catch(error){if((request===undefined||request===playRequest)&&!closed){stopPreview();update();status.textContent=`Source preview could not play: ${error.message}`;}}
    });
    listen(form,'submit',async event=>{
      event.preventDefault();
      if(monitor && event.submitter!==append && event.submitter!==insert && (!overwrite||event.submitter!==overwrite))return;
      const overwriting=Boolean(overwrite&&event.submitter===overwrite),shown=overwriteShown;
      if(overwriting&&(!shown||overwrite.disabled||!overwriteBox.open))return;
      if(monitor && !busy && current()){this.options.pause();update();}if(!sourceReady()||!form.reportValidity())return;
      const inserting=event.submitter===insert;
      if(overwriting&&shown.key!==overwriteShown?.key || monitor && (overwriting?overwrite:inserting?insert:append).disabled)return;
      if(inserting && insertReason){status.textContent=insertReason;return;}
      let selected;
      try{selected=range();}catch(error){status.textContent=error.message;return;}
      const start=at,chosenTrack=this.destinationTrackId||"",knownIds=new Set((this.project()?.manual?.media_clips||[]).map(row=>row.id));
      const commitCurrent=()=>current() && (this.destinationTrackId||'')===chosenTrack && (!monitor || monitor.visible?.()!==false)
        && (!overwriting || (overwriteBox.open && !this.options.overwriteIssue?.() && fields.in.value.trim()!=='' && fields.out.value.trim()!==''
          && Number(fields.in.value)===shown.detail.source_start && Number(fields.out.value)===shown.detail.source_end));
      busy=true;dialog.pending=true;stopPreview();update();let failure='';
      try{
        const result=await this.options.edit(overwriting?'media_track_overwrite':inserting?'media_insert':'media_append',overwriting?shown.detail:{asset_id:assetId,...selected,...(inserting?{start}:{}),...(chosenTrack?{track_id:chosenTrack}:{})},{isCurrent:commitCurrent,strictRevision:Boolean(monitor),admissionCurrent:()=>commitCurrent() && (!monitor || Math.abs(Number(this.options.time?.())-start)<1e-8)});
        if(!result)throw new Error(monitor?'The shot was not added. Review the current edit and try again.':`The edit changed or is busy. Close and review again; nothing was ${inserting?'inserted':'appended'}.`);
        if(monitor){
          if(!mounted() || !sameSource() || this.project().revision!==result.revision || result.id!==projectId || monitor.visible?.()===false)return;
          const placed=(result.manual?.media_clips||[]).filter(row=>!knownIds.has(row.id)&&row.asset_id===assetId).at(-1);
          if(!placed)throw new Error('The edit was saved but the new shot could not be identified. Review the timeline before adding another.');
          revision=result.revision;this.selected=placed.id;
          if(Number.isFinite(placed.start)&&Number.isFinite(placed.end)&&placed.end>placed.start){
            lastPlacement={revision:result.revision,clipId:placed.id};
            text(receipt,`${overwriting?'Overwritten':inserting?'Inserted':'Appended'} on timeline: ${placed.start.toFixed(3)}–${placed.end.toFixed(3)} s. Undo restores the previous edit.`);receipt.hidden=false;
          }
          if(origin)origin.textContent='Original source preview. Source sound plays at normal speed, not the edited mix. Effects are not applied; the source marks are unchanged.';
          if(Math.abs(Number(this.options.time?.())-start)<1e-8)monitor.placed?.(placed,result);this.render();
          at=Number(this.options.time?.());
          if(overwriting)failure='Track overwritten. One Undo restores every affected clip; the source marks are unchanged.';
        }else if(!closed && dialog.open && this.project()?.id===projectId && result.id===projectId){this.selected=result.manual?.media_clips?.at(-1)?.id;this.render();dialog.close();}
      }catch(error){failure=error.message;}
      finally{busy=false;dialog.pending=false;update();if(failure&&!closed&&dialog.open)status.textContent=failure;}
    });
    listen(close,'click',()=>{if(!busy)dialog.close(monitor?true:undefined);});
    listen(dialog,'cancel',event=>{if(busy)event.preventDefault();});
    const dispose=(restoreFocus=false)=>{
      const returnFocus=monitor && restoreFocus===true && dialog.contains?.(document.activeElement);
      if(closed)return;closed=true;dialog.open=false;clearTimeout(busyRefreshTimer);busyRefreshTimer=null;
      frameReview?.destroy();for(const remove of listeners)remove();if(trackControl)this.destinationControls.delete(trackControl);stopPreview();video.removeAttribute('src');video.load();dialog.remove();
      if(this.shotReview===dialog){this.shotReview=null;if(monitor)delete this.root.dataset.sourceMonitorOpen;}
      if(returnFocus){
        const fallback=[...(this.library?.querySelectorAll?.('[data-review-shot]')||[])].find(button=>button.dataset.reviewShot===assetId&&!button.disabled);
        const target=opener?.isConnected && !opener.disabled ? opener : fallback;
        target?.focus?.({preventScroll:true});
      }
    };
    dialog.sourceSelection=id=>{
      if(id!==assetId)return null;
      if(!current()||!metadata||!metadataMatches()||frameReview?.pending||monitor?.visible?.()===false)return {issue:'Review the current source and edit before dragging its selection.'};
      try{return range();}catch(error){return {issue:error.message};}
    };
    dialog.captureRepair=id=>id===assetId && mounted() && sameSource()
      ? {dialog,epoch:repairInteraction,time:video.currentTime,identity,revision,reviewed:current()} : null;
    dialog.acceptRepair=(capture,next,nextRevision,reload)=>{
      if(!capture || capture.dialog!==dialog || !mounted() || capture.identity!==identity || capture.revision!==revision
        || this.project()?.id!==projectId || monitor && monitor.token?.()!==viewToken
        || libraryPreviewContentIdentity(next)!==libraryPreviewContentIdentity(asset))return false;
      identity=assetIdentity(next);if(capture.reviewed)revision=nextRevision;stopPreview();
      if(reload){metadata=false;seenMetadata=false;metadataError='';matchSeekAttempted=true;
        repairRestore=capture.epoch===repairInteraction?capture:null;video.src=next.url;video.load();}
      update();return true;
    };
    if(monitor){dialog.close=dispose;dialog.pauseSource=stopPreview;dialog.syncSource=update;
      // Presentation only. Never flush, seek or pause the source being inspected.
      dialog.admitSourceFocus=()=>{if(!mounted()||!sameSource()||busy||this.options.busy()||this.uploading||monitor.visible?.()===false)return false;
        if(this.options.playing?.())this.options.pause();return true;};
    }
    else listen(dialog,'close',dispose);
    const markActions=make('div');markActions.className='library-shot-actions';markActions.append(saveMarks,resetMarks);
    if(!monitor)form.append(markActions,marksStatus);
    const monitorActions=make('div');monitorActions.className='library-shot-actions';monitorActions.append(preview);
    if(monitor)form.append(status);form.append(monitorActions);
    if(!monitor)form.append(monitorHelp);
    if(monitor){
      const placement=make('section'),heading=make('h4','Place on timeline');placement.className='library-source-placement';
      heading.id='librarySourcePlacementTitle';placement.setAttribute('role','group');placement.setAttribute('aria-labelledby',heading.id);
      placement.append(heading,destination,refresh);if(trackControl)placement.append(trackControl);
      const actions=make('div');actions.className='library-source-placement-options';
      // Keep original Append-first submit order; do not clone native actions.
      for(const [button,note]of [[append,appendHelp],[insert,insertHelp]]){
        const choice=make('div');choice.className='library-source-placement-choice';choice.append(button,note);actions.append(choice);
      }
      placement.append(actions);if(overwriteBox)placement.append(overwriteBox);form.append(placement,receipt);
    }else{
      const actions=make('div');actions.className='library-shot-actions';actions.append(close,append,insert);if(trackControl)form.append(trackControl);form.append(actions,insertHelp);
    }
    if(monitor){
      const header=make('header');header.className='library-source-monitor-header';header.append(title,close);
      dialog.append(header,name,...(origin?[origin]:[]),video,form);
      explanation.textContent='Original source picture and normal-speed sound, not the edited effects or mix. Select a timeline clip to return to its inspector. Closing does not save marks.';
      explanation.className='library-shot-insert-help';
      const help=make('details');help.className='library-source-help';
      const summary=make('summary','Source marks & help'),jumps=make('div');jumps.className='library-shot-actions';
      jumps.append(...Object.values(jumpButtons));help.append(summary,jumps,markActions,marksStatus,monitorHelp,explanation);dialog.append(help);
      this.root.prepend(dialog);this.root.dataset.sourceMonitorOpen='true';this.shotReview=dialog;dialog.open=true;
      dialog.scrollIntoView?.({block:'start',inline:'nearest'});dialog.focus?.({preventScroll:true});
    }else{dialog.append(title,name,...(origin?[origin]:[]),explanation,video,form,status);document.body.append(dialog);this.shotReview=dialog;dialog.showModal();}
    if(this.options.previewRepair){
      const repairLink=make('button',`Find Verify & repair preview for ${asset.name}`);repairLink.type='button';repairLink.className='library-preview-repair-link';
      repairLink.hidden=true;listen(video,'error',()=>{if(video.error?.code!==1)repairLink.hidden=false;});
      listen(video,'loadedmetadata',()=>{if(metadata)repairLink.hidden=true;});
      listen(repairLink,'click',()=>this.revealPreviewRepair(assetId));status.after?.(repairLink);
    }
    if(monitor && typeof this.options.sourceFrames==='function')frameReview=this.options.sourceFrames(dialog,video,{
      snapshot:()=>({key:JSON.stringify([projectId,viewToken,this.project()?.revision,assetIdentity(this.project()?.assets?.[assetId])]),projectId,assetId,
        time:video.currentTime,duration:Number(asset.duration),available:current()&&!blocked()&&metadata&&metadataMatches()}),
      pause:()=>{stopPreview();monitor.pauseProgram?.(video);},changed:()=>update(),
      load:(request,context)=>this.options.api(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/frame-step?${new URLSearchParams(request)}`,context),
    });
    update();
    return true;
  }
  select(id) { this.closeSourceMonitor(); this.selected = id; this.render(); this.options.selected?.(id); }
  render(forceInputs = false) {
    const project = this.project();
    if (this.importQueue?.running && this.importQueue.projectId !== project?.id) this.importQueue.stop('Project changed. Completed imports stay in the original project.');
    this.renderImportQueue();
    if (this.projectId !== project?.id && this.storageStatus) { this.storageStatus.textContent = ''; this.storageStatus.hidden = true; if (this.storageDetails) { this.storageDetails.hidden = true; this.storageDetails.open = false; } }
    if (this.projectId !== project?.id) { this.destinationTrackId=""; this.saveError=null; this.frameEditor?.close(); this.frameOverride=null; this.shotReview?.close(); this.endFaderDrag(); this.pause(); this.clearPlayers(); this.pending.clear(); this.overrides.clear(); this.groupOverrides?.clear(); this.saving=null; this.mixerOverride = null; this.trackLevelOverrides?.clear(); this.trackLevelGesture=null; this.trackLevelOwner=null; this.trackLevelSaving=null; this.trackLevelSaveOwner=null; this.selected = null; this.solo = null; clearTimeout(this.timer); this.projectId = project?.id; }
    if(this.previewRepairFocus?.button?.isConnected===false)this.previewRepairFocus.dispose();
    this.previewRepairCards ||= new Map();this.previewRepairCards.clear();
    const library = this.library; library.replaceChildren(...(this.poolDestinationControl?[this.poolDestinationControl]:[]));
    if (this.sourceLibrary) {
      this.sourceLibrary.replaceChildren();
      for (const [slot, source] of Object.entries(project?.sources || {})) {
        if (!source) continue;
        const card = document.createElement('button'); card.type = 'button'; card.className = 'source-library-card'; card.dataset.kind = 'video';
        const thumbs = source.thumbnail_urls || [], thumb = libraryThumb(thumbs[Math.floor(thumbs.length / 3)], 'video');
        const badge = document.createElement('b'); badge.textContent = slot;
        const copy = document.createElement('span'); copy.textContent = source.name || `Source ${slot}`; card.title = `Review source ${slot}: ${copy.textContent}`;
        const detail = document.createElement('small'); detail.dataset.kind = 'video'; detail.textContent = `${slot} · ${libraryClock(source.duration)}`;
        card.append(thumb,badge,copy,detail); card.addEventListener('click', () => this.options.reviewSource?.(slot)); this.sourceLibrary.append(card);
      }
    }
    const usage=libraryAssetUsage(project);
    for (const asset of Object.values(project?.assets || {})) {
      const card = document.createElement('div'); card.className = 'media-asset'; card.dataset.kind = asset.kind;
      const thumb=libraryThumb(asset.thumbnail_url,asset.kind);card.append(thumb);
      const thumbProject=project.id,thumbView=this.options.viewToken?.();
      thumb.querySelector?.('img')?.addEventListener('error',event=>{
        if(this.project()?.id===thumbProject && this.options.viewToken?.()===thumbView)this.reportPreviewFailure(asset.id,event.currentTarget?.getAttribute?.('src'),'thumbnail');
      });
      const title = document.createElement('span'); title.textContent = asset.name; title.title = asset.name; card.append(title);
      const meta = document.createElement('small'); meta.className = 'media-asset-meta'; meta.dataset.kind = asset.kind; meta.textContent = asset.kind === 'image' ? 'Image' : `${asset.kind === 'audio' ? 'Audio' : 'Video'} · ${libraryClock(asset.duration)}`; card.append(meta);
      const button = document.createElement('button'); button.type = 'button'; button.dataset.asset = asset.id;
      button.textContent = asset.status === 'ready' ? asset.kind === 'video' ? '+ Overlay' : '+ Add' : asset.status || 'Preparing'; button.disabled = asset.status !== 'ready'; card.append(button); library.append(card);
      if (asset.kind === 'video') {
        button.title = asset.has_audio ? 'Overlay at the playhead with source sound; change sound in the selected clip' : 'Overlay at the playhead; this file has no audio stream';
        const review=document.createElement('button');review.type='button';review.dataset.reviewShot=asset.id;review.textContent='In / Out';review.title='Review shot and choose source In / Out before inserting';review.disabled=asset.status!=='ready'||!project?.draft||this.options.busy()||this.uploading;card.append(review);
        const append = document.createElement('button'); append.type = 'button'; append.dataset.append = asset.id;
        append.textContent = 'Append'; append.title = 'Add this video and its sound at the end of the edit';
        append.disabled = asset.status !== 'ready' || !project?.draft || this.options.busy() || this.uploading; card.append(append);
      }
      if(asset.kind==='audio'){
        const review=document.createElement('button');review.type='button';review.dataset.reviewAudio=asset.id;review.textContent='In / Out';card.append(review);
      }
      if (['failed','cancelled'].includes(asset.status)) { delete button.dataset.asset; button.dataset.retry=asset.id;button.textContent='Retry';button.disabled=false; }
      this.appendAssetUsage(card,asset,usage);
      this.appendPreviewRepair(card,asset);
      for (const action of card.querySelectorAll('button')) action.setAttribute('aria-label', `${action.textContent}: ${asset.name}`);
      if (asset.stabilized && asset.status === 'ready' && asset.download_url) {
        const download = document.createElement('a'); download.className = 'media-asset-download'; download.href = asset.download_url;
        download.download = asset.name || 'stabilized.mp4'; download.textContent = 'Download copy'; card.append(download);
      }
    }
    if (!Object.keys(project?.assets||{}).length) { const note = document.createElement('p'); note.className = 'media-help media-empty'; note.textContent = 'Add music, voiceover, images or more video with Import. Files stay on this computer.'; library.append(note); }
    this.updateImportAvailability();
    const clip = this.clips().find(item => item.id === this.selected), asset = project?.assets?.[clip?.asset_id];
    this.root.querySelector('.media-inspector').hidden = !clip;
    this.root.querySelector('.media-selection-empty').hidden = Boolean(clip);
    if (clip && asset) {
      this.root.querySelector('.media-selected-name').textContent = asset.name;
      this.syncInspectorInputs(clip, forceInputs);
      this.root.querySelector('[data-value=volume_db]').textContent = `${clip.volume_db || 0} dB`;
      for (const node of this.root.querySelectorAll('.media-inspector [data-kind]')) node.hidden = !({timed:asset.kind !== 'image',visual:asset.kind !== 'audio',sound:asset.kind !== 'image',video:asset.kind === 'video',image:asset.kind === 'image'}[node.dataset.kind]);
      this.root.querySelector('.media-placement').hidden = asset.kind === 'audio';
    }
    this.renderClipAudio();
    this.renderMixer(forceInputs);
    this.updateSplitAvailability();
    this.updateTrimAvailability();
    this.updateDuplicateAvailability();
    this.updateMoveAvailability();
    this.updateStackAvailability();
    this.updateEnabledAvailability();
    this.updateSlipAvailability();
    this.syncFrameEditor();
    this.syncSourceMonitor();
    this.updateProtectionAvailability();
    this.clipOpacity?.refresh();
  }
  repaintClipOpacity(id) {
    const p=this.project(),clip=p?.manual?.media_clips?.find(c=>c.id===id),frame=this.players?.get('v:'+id)?.frame;
    if(clip&&frame)frame.style.opacity=occurrenceFrameOpacity(clip,this.clipOpacity?.previewFor(p,id));
  }
  syncInspectorInputs(clip, forceInputs = false) {
    for (const input of this.root.querySelectorAll('[data-media]')) {
      if (!forceInputs && document.activeElement === input) continue;
      const key = input.dataset.media;
      if (input.type === 'checkbox') input.checked = Boolean(clip[key]);
      else input.value = ['x','y','w','h'].includes(key) ? String(Number((Number(clip[key] ?? (['w','h'].includes(key) ? 1 : 0))*100).toFixed(7))) : clip[key] ?? '';
    }
  }
  renderClipAudio() {
    const clip = this.clips().find(item => item.id === this.selected), asset = this.project()?.assets?.[clip?.asset_id];
    if (!clip || !asset || !this.root) return;
    const hasSound = asset.kind === 'audio' || Boolean(asset.has_audio);
    const included = asset.kind === 'audio' || Boolean(clip.audio_enabled);
    const group = clip.role === 'voice' ? 'Voiceover' : clip.role === 'effects' ? 'Effects' : 'Music';
    const trackLevel=this.trackLevelValues?.()[clip.track_id],tracks=this.project()?.manual?.layer_tracks?.tracks;
    const track=Array.isArray(tracks)?tracks.find(row=>row.id===clip.track_id):null;
    const status = this.root.querySelector('.media-audio-status');
    status.textContent = clip.enabled === false ? 'This occurrence is disabled. Its saved sound settings apply when re-enabled.' : !hasSound ? 'This source file has no audio stream.' : !included
      ? 'Source sound is off for this clip. Enable it above for preview and export.'
      : clip.muted ? 'This clip is muted in preview and export.'
      : trackLevel?.muted ? `Track "${track?.name || 'Selected'}" is muted in preview and export. Picture stays visible; adjust Track levels in Audio.`
      : this.mixer()[`${clip.role || 'music'}_muted`] ? `${group} group is muted. Unmute it in Audio to hear this clip.`
      : `Source sound is on · ${clip.volume_db || 0} dB · ${group} group`;
    if(trackLevel && !trackLevel.muted && trackLevel.gain_db!==0)status.textContent+=` Track level: ${trackLevel.gain_db} dB before role processing.`;
    for (const input of this.root.querySelectorAll('[data-media]')) {
      if (input.dataset.media === 'audio_enabled') input.disabled = !hasSound;
      else if (['role','volume_db','fade_in','fade_out','muted'].includes(input.dataset.media)) input.disabled = !hasSound || !included;
    }
    this.updateProtectionAvailability();
  }
  renderMixer(forceInputs = false) {
    this.syncTrackLevels();
    const mixer = this.mixer();
    const root = this.audioRoot || this.root;
    const sourceName = root.querySelector('[data-channel-name=source]');
    if (sourceName) sourceName.textContent = `Original ${this.options.audioSlot?.() || this.project()?.manual?.source_mixer?.audio_slot || this.project()?.settings?.audio_source || 'A'}`;
    root.querySelector('[data-ducking]').checked=Boolean(mixer.ducking);
    const voiceCleanup=root.querySelector('[data-voice-cleanup]'); if(voiceCleanup)voiceCleanup.checked=mixer.voice_cleanup===true;
    for (const input of root.querySelectorAll('[data-mix]')) {
      const db = Number(mixer[input.dataset.mix]) || 0;
      // Ranges have no unfinished typed draft. Reset/undo while focused must
      // update the native value as well as the bespoke cap and spoken value.
      input.value = db;
      input.setAttribute('aria-valuetext', `${db > 0 ? '+' : ''}${db.toFixed(1)} dB`);
      this.setFaderVisual(input, db);
    }
    for (const input of root.querySelectorAll('[data-mix-number]')) { if (forceInputs || document.activeElement !== input) input.value = (Number(mixer[input.dataset.mixNumber]) || 0).toFixed(1); }
    for (const button of root.querySelectorAll('[data-mix-reset]')) button.disabled = !Number(mixer[button.dataset.mixReset] || 0);
    this.renderNormalization(mixer, root);
    for (const button of root.querySelectorAll('[data-mute]')) button.setAttribute('aria-pressed', String(Boolean(mixer[`${button.dataset.mute}_muted`])));
    for (const button of root.querySelectorAll('[data-solo]')) button.setAttribute('aria-pressed', String(this.solo === button.dataset.solo));
    for (const [role,{row}] of this.channelMeters || []) {
      row.classList.toggle('is-muted',Boolean(mixer[`${role}_muted`]) || Boolean(this.solo && role !== 'master' && this.solo !== role));
    }
    this.renderClipAudio();
  }
  // Which channels carry sound in this edit, so the panel can say what a fader does.
  audibleChannels(mixer = this.mixer()) {
    const project = this.project(), active = new Set(), levels=this.trackLevelValues();
    const slot = this.options.audioSlot?.() || project?.manual?.source_mixer?.audio_slot || project?.settings?.audio_source || 'A';
    if (project?.sources?.[slot]?.has_audio && !mixer.source_muted) active.add('source');
    for (const clip of this.clips()) {
      const asset = project?.assets?.[clip.asset_id], role = clip.role || 'music';
      if (!asset || clip.enabled === false || clip.muted || levels[clip.track_id]?.muted || mixer[`${role}_muted`]) continue;
      if (asset.kind === 'audio' || (asset.has_audio && clip.audio_enabled)) active.add(role);
    }
    return active;
  }
  renderNormalization(mixer, root) {
    const normalization = mixerNormalization(this.project()), active = this.audibleChannels(mixer);
    const note = root.querySelector('.mixer-normalization');
    const names = {source:'Original', music:'Music', voice:'Voiceover', effects:'Effects'};
    const [alone] = active.size === 1 ? [...active] : [];
    if (note) note.textContent = !normalization ? 'Loudness normalization is off. Faders set exported levels directly.'
      : `Loudness normalization is on (${normalization.target} LUFS). Channel faders set the balance between role groups; Master sets the final level.`
        + (alone ? ` ${names[alone]} is the only role group playing, so its fader cannot change the normalized exported level.` : '');
    for (const [role,{row}] of this.channelMeters || []) row.dataset.normalizedAlone = String(Boolean(normalization && role === alone));
  }
  toggleSolo(role) {
    if (!['source','music','voice','effects'].includes(role)) return;
    this.solo = this.solo === role ? null : role;
    this.renderMixer(); this.options.preview();
  }
  change(input) {
    if (this.options.busy()) { this.render(); return; }
    if (input.hasAttribute('data-ducking')) { this.queueMixer({ducking:input.checked}); return; }
    if (input.hasAttribute('data-voice-cleanup')) { this.queueMixer({voice_cleanup:input.checked}); return; }
    if (input.dataset.mix) { this.queueMixer({[input.dataset.mix]:Number(input.value)}); return; }
    if (input.dataset.mixNumber) {
      const value = Number(input.value);
      if (input.value === '' || !Number.isFinite(value)) { this.renderMixer(); return; }
      this.queueMixer({[input.dataset.mixNumber]: Math.round(Math.max(-60, Math.min(12, value)) * 10) / 10});
      return;
    }
    const key = input.dataset.media; if (!key || !this.selected || !input.checkValidity()) return;
    if (key === 'source_start' && typeof this.options.slip === 'function') {
      void this.slipTo(input.value.trim() === '' ? NaN : Number(input.value), input); return;
    }
    let value = input.type === 'checkbox' ? input.checked : ['role','fit','motion'].includes(key) ? input.value : Number(input.value);
    if (['x','y','w','h'].includes(key)) value /= 100;
    this.queueClip(this.selected, {[key]:value});
  }
  queueClip(id, patch) {
    const issue=this.options.mutationIssue?.("media_update",{clip_id:id,...this.pending.get(id),...patch}) || this.options.trackPatchIssue?.(id,{...this.pending.get(id),...patch});
    if(issue){this.render(true);this.status.textContent=issue;return false;}
    this.overrides.set(id, {...this.overrides.get(id),...patch});
    this.pending.set(id, {...this.pending.get(id),...patch}); this.schedule(); this.render(); this.options.preview();
  }
  previewGroup(patches) { this.groupOverrides=new Map((patches||[]).map(({clip_id,start,end})=>[clip_id,{start,end}])); }
  previewClip(id, patch) { if (patch) this.overrides.set(id,patch); else this.overrides.delete(id); this.options.preview(); }
  queueMixer(patch) { this.mixerOverride = {...this.mixerOverride,...patch}; this.pending.set('mixer',{...this.pending.get('mixer'),...patch}); this.schedule(); this.renderMixer(); this.options.preview(); }
  schedule() { this.saveError=null; clearTimeout(this.timer); this.status.textContent = 'Saving…'; this.timer = setTimeout(()=>this.flush(),400); this.options.saveStateChanged?.(); }
  async flush() {
    clearTimeout(this.timer); if (this.saving) return this.saving;
    if(!this.pending.size)return true;
    const projectId = this.project()?.id,viewToken=this.options.viewToken?.();
    const trackCurrent=()=>this.project()?.id===projectId && this.options.viewToken?.()===viewToken;
    const task = Promise.resolve().then(async()=>{
      while (this.pending.size && this.project()?.id === projectId) {
        const [key, patch] = this.pending.entries().next().value; this.pending.delete(key);
        const trackId=key.startsWith('track_audio:')?key.slice(12):null;
        if(trackId && (!trackCurrent() || !this.trackLevelSameContext(this.trackLevelOwner)))return false;
        const trackSaveOwner=trackId?{projectId,viewToken,trackId}:null;
        this.trackLevelSaving=trackId;this.trackLevelSaveOwner=trackSaveOwner;
        try {
          const issue=trackId ? this.options.trackLevelPlan?.(trackId,patch)?.issue : key==='mixer'?'':this.options.mutationIssue?.('media_update',{clip_id:key,...patch});if(issue)throw new Error(issue);
          const result = await this.options.edit(trackId ? 'layer_track_audio' : key === 'mixer' ? 'set_audio_mixer' : 'media_update',trackId ? {track_id:trackId,...patch} : key === 'mixer' ? patch : {clip_id:key,...patch});
          if(trackId && !trackCurrent())return false;
          if (this.project()?.id !== projectId) return false;
          if (!result) throw new Error(trackId ? 'Reload the saved levels before trying again. The request was not automatically repeated.' : 'The edit is busy. Try the change again.');
          if (!this.pending.has(key)) { if(trackId)this.trackLevelOverrides.delete(trackId);else if (key === 'mixer') this.mixerOverride = null; else this.overrides.delete(key); }
        } catch(error) {
          if (this.project()?.id !== projectId || trackId && !trackCurrent()) return false;
          this.pending.clear(); this.overrides.clear(); this.mixerOverride = null; this.trackLevelOverrides?.clear();
          if (this.project()?.id === projectId) { this.saveErrorTarget=trackId?'track-level':'media';this.saveError=this.status.textContent = trackId ? `Track level not confirmed: ${error.message}` : `Not saved: ${error.message} Previous settings restored.`; this.render(true); this.options.preview(); }
          return false;
        } finally { if(this.trackLevelSaveOwner===trackSaveOwner){this.trackLevelSaving=null;this.trackLevelSaveOwner=null;} }
      }
      if (this.project()?.id === projectId) {
        // A brief confirmation; a permanent "Saved" line reads as leftover text.
        this.saveError=null; this.status.textContent = 'Saved'; this.render(); this.options.preview();
        clearTimeout(this.savedTimer);
        this.savedTimer = setTimeout(() => { if (this.status.textContent === 'Saved') this.status.textContent = ''; }, 2000);
      }
      return true;
    }).finally(()=>{
      if(this.saving===task){
        this.saving=null;
        // The last paint occurred while saving. Refresh availability in place,
        // without rebuilding the library or moving the selected inspector.
        this.updateImportAvailability?.();this.syncTrackLevels();
        this.options.saveStateChanged?.();
      }
    });
    this.saving=task;
    this.options.saveStateChanged?.();
    return task;
  }
  async retry(assetId) {
    if(this.options.busy() || this.uploading)return;
    const issue=(this.project()?.assets?.[assetId]?._stabilization || this.project()?.assets?.[assetId]?.stabilized) ? this.options.assetMutationIssue?.(assetId) : "";
    if(issue){this.status.textContent=issue;return;}
    const projectId=this.project().id;this.uploading=true;this.options.busyChanged?.();
    try {const result=await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/assets/${encodeURIComponent(assetId)}/prepare`,{method:'POST',body:'{}'});await this.options.acceptUpload(result,projectId);}
    catch(error){if(this.project()?.id===projectId)this.status.textContent=error.message;}finally{this.uploading=false;this.render();this.options.busyChanged?.();}
  }
  async action(action) {
    if (action === 'duplicate' && typeof this.options.duplicate === 'function') {
      const id = this.selected, projectId = this.project()?.id, time = this.options.time?.();
      if (!id || !projectId || this.options.busy() || this.options.trimBusy?.()) return null;
      try { return await this.options.duplicate(id,time); }
      catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; return null; }
    }
    if (['trim_start', 'trim_end'].includes(action)) {
      const id = this.selected, projectId = this.project()?.id, time = this.options.time?.();
      if (!id || !projectId || this.options.busy() || this.options.trimBusy?.() || typeof this.options.trim !== 'function') return null;
      // Capture the occurrence and cursor before the shared transaction flushes.
      // It owns project/revision checks; never switch targets after an await.
      try { return await this.options.trim(id, action === 'trim_start' ? 'start' : 'end', time); }
      catch (error) { if (this.project()?.id === projectId) this.status.textContent = error.message; return null; }
    }
    if (!this.selected || this.options.busy() || !(await this.flush())) return;
    this.options.pause();
    try { await this.options.edit(`media_${action}`, {clip_id:this.selected,...(action === 'split' ? {time:this.options.time()} : {})}); this.render(); }
    catch(error) { this.status.textContent = error.message; }
  }
  async resumeAudio() {
    try {
      if (!this.context) {
        const Audio = window.AudioContext || window.webkitAudioContext; if (!Audio) return;
        this.context = new Audio(); this.master = this.context.createGain(); this.limiter = this.context.createDynamicsCompressor();
        this.limiter.threshold.value = 20*Math.log10(.98); this.limiter.knee.value = 0; this.limiter.ratio.value = 20;
        this.limiter.attack.value = .005; this.limiter.release.value = .05;
        this.analyser = this.context.createAnalyser(); this.analyser.fftSize = 2048;
        // Meter the actual summed signal before limiting, so clipping/headroom
        // remains visible instead of being hidden by the preview compressor.
        this.master.connect(this.analyser).connect(this.limiter).connect(this.context.destination);
        // Channels -> mix -> loudness normalization (as in export) -> Master.
        this.mixInput = this.context.createGain();
        this.mixInput.channelCount = 2; this.mixInput.channelCountMode = 'explicit'; this.mixInput.channelInterpretation = 'speakers';
        this.normalizer = this.context.createGain();
        this.mixInput.connect(this.normalizer).connect(this.master);
        // ITU-R BS.1770 K-weighting (approximated with Web Audio biquads), per channel.
        const shelf = this.context.createBiquadFilter(); shelf.type = 'highshelf'; shelf.frequency.value = 1681.97; shelf.gain.value = 4;
        const highpass = this.context.createBiquadFilter(); highpass.type = 'highpass'; highpass.frequency.value = 38.13; highpass.Q.value = 20 * Math.log10(.5);
        const split = this.context.createChannelSplitter(2);
        this.loudnessAnalysers = [0, 1].map(channel => { const analyser = this.context.createAnalyser(); analyser.fftSize = 2048; split.connect(analyser, channel); return analyser; });
        this.mixInput.connect(shelf).connect(highpass).connect(split);
      }
      if (this.context.state !== 'running') await this.context.resume();
    } catch { /* Browsers without Web Audio still support attenuation via volume. */ }
  }
  player(key, kind, url, role = 'music') {
    let item = this.players.get(key);
    if (item && (item.url !== url || item.element.tagName.toLowerCase() !== kind)) { this.releasePlayer(key,item); item = null; }
    if (!item) item = this.createPlayer(key,kind,url);
    item.role = role;
    if (kind === 'audio' && this.context && !item.node && !item.basicAudio) {
      // A media element can only acquire one Web Audio source node in its
      // lifetime, even after disconnect(). Never retry a rejected element.
      for (let attempt = 0; attempt < 2; attempt++) {
        try { this.connectAudio(item); break; }
        catch (error) {
          const time = item.element.currentTime;
          this.releasePlayer(key,item);
          item = this.createPlayer(key,kind,url);
          try { item.element.currentTime = time; } catch { /* syncPlayer restores the edit position. */ }
          if (attempt === 1) {
            item.basicAudio = true;
            this.audioFallback = true;
            this.status.textContent = 'Basic audio preview: the audio mixer connection failed. Playback and volume still work; preview boosts, metering and ducking are limited. Reload to retry. Export settings are unchanged.';
            console.warn('CUTROOM audio preview is using basic playback:', error?.name || 'AudioError');
          }
        }
      }
    }
    if (item.analyser && item.busRole !== role) this.routeAudio(item,role);
    return item;
  }
  createPlayer(key,kind,url) {
    const element = document.createElement(kind); element.src = url; element.preload = 'metadata'; element.playsInline = true;
    element.className = kind === 'audio' ? 'media-audio-player' : 'media-overlay-content';
    // After repeated graph failure, keep new audio in basic mode until reload;
    // do not repeat the failed setup at every clip boundary or project switch.
    const item = {element,url,gain:null,node:null,token:0,basicAudio:kind === 'audio' && Boolean(this.audioFallback)};
    if (kind !== 'audio') { item.frame = document.createElement('div'); item.frame.className = 'media-overlay'; item.frame.append(element); this.stage.append(item.frame); }
    else this.root.append(element);
    this.players.set(key,item);
    const projectId=this.project()?.id,viewToken=this.options.viewToken?.(),clipId=/^[av]:/.test(key)?key.slice(2):null;
    const assetId=(this.project()?.manual?.media_clips||[]).find(clip=>clip.id===clipId)?.asset_id;
    if(assetId)element.addEventListener?.('error',()=>{
      if(element.error?.code===1 || this.players.get(key)!==item || this.project()?.id!==projectId || this.options.viewToken?.()!==viewToken)return;
      this.reportPreviewFailure(assetId,url);
    });
    return item;
  }
  connectAudio(item) {
    item.gain = this.context.createGain();
    item.analyser = this.context.createAnalyser(); item.analyser.fftSize = 256;
    item.node = this.context.createMediaElementSource(item.element);
    item.node.connect(item.gain); item.gain.connect(item.analyser); this.routeAudio(item,item.role || 'music');
    // Before the first user gesture, volume may have provided basic attenuation.
    // Once connected, gain nodes own it; keeping both would attenuate twice.
    item.element.volume = 1;
  }
  routeAudio(item,role) {
    this.audioBuses ||= new Map();
    let bus = this.audioBuses.get(role);
    if (!bus) {
      const gain = this.context.createGain(), analyser = this.context.createAnalyser(); analyser.fftSize = 2048;
      gain.connect(analyser); analyser.connect(this.mixInput || this.master);
      bus = {gain,analyser}; this.audioBuses.set(role,bus);
    }
    item.analyser.disconnect(); item.analyser.connect(bus.gain); item.busRole = role;
  }
  syncPlayer(item, time, speed, playing, gain = 0) {
    const element = item.element; element.playbackRate = speed; element.preservesPitch = true;
    if (item.gain) item.gain.gain.value = gain; else element.volume = Math.max(0,Math.min(1,gain*10**(Number(this.mixer().master_db||0)/20)));
    if (Math.abs(element.currentTime-time) > (playing ? .12 : 1e-6)) { try { element.currentTime = Math.max(0,time); this.meterResetUntil = performance.now()+120; } catch {} }
    item.wanted = playing;
    if (!playing) { item.token++; element.pause(); return; }
    if (element.paused && !item.pending) {
      const token = ++item.token; item.pending = true;
      Promise.resolve(element.play()).then(()=>{ if (token !== item.token || !item.wanted) element.pause(); }).catch(()=>{}).finally(()=>{item.pending=false;});
    }
  }
  sync(time, playing, source = {}) {
    const editTime = source.sourceMode ? this.options.time?.() : time;
    this.updateSplitAvailability(editTime);
    this.updateTrimAvailability(editTime);
    this.updateDuplicateAvailability(editTime);
    this.updateMoveAvailability(editTime);
    this.updateSlipAvailability();
    this.updateSourceMatchAvailability(editTime);
    this.syncFrameEditor();
    const project = this.project();
    if(playing||source.sourceMode)this.clipOpacity?.release();
    if(this.clipOpacity?.open){
      const selected=project?.manual?.media_clips?.find(c=>c.id===this.selected);
      const frameState=JSON.stringify([project?.id,project?.revision,this.selected,!!playing,!!source.sourceMode,
        !!selected&&time>=selected.start-5.1e-10&&time<selected.end-5.1e-10]);
      if(this.opacityFrameState!==frameState){this.opacityFrameState=frameState;this.clipOpacity.refresh();}
    }
    if (!project || source.sourceMode) { this.pause(); return; }
    const trackOrder=this.options.trackOrder?.(project);
    if(trackOrder?.issue || (project.manual && Object.hasOwn(project.manual,"layer_tracks") && !trackOrder)){
      for(const [key,item] of this.players)this.releasePlayer(key,item);
      this.status.textContent=trackOrder?.issue||"Saved track ordering is unavailable. Reload a compatible editor.";return;
    }
    const mixer = this.mixer(), active = new Set(), clips = this.clips(), levels=this.trackLevelValues(project,trackOrder);
    let speechRms=0;
    for(const item of this.players.values()) if(item.analyser && ['source','voice'].includes(item.role) && item.wanted) {
      const samples=new Float32Array(256);item.analyser.getFloatTimeDomainData(samples);speechRms+=Math.sqrt(samples.reduce((sum,v)=>sum+v*v,0)/samples.length);
    }
    const desiredDuck=mixer.ducking && speechRms>.025 ? (speechRms/.025)**(1/8-1) : 1;
    const now=performance.now(),elapsed=Math.max(0,Math.min(.2,(now-(this.duckTime||now))/1000));this.duckTime=now;
    this.duckGain=(this.duckGain??1)+(desiredDuck-(this.duckGain??1))*(1-Math.exp(-elapsed/(desiredDuck < (this.duckGain??1) ? .02 : .35)));
    if (this.master) this.master.gain.value = 10 ** (Number(mixer.master_db || 0)/20);
    this.updateNormalizer(playing, mixer);
    const soloGain = role => !this.solo || this.solo === role ? 1 : 0;
    // Saved edit edges have up to nine decimal places; a rational frame seek
    // can be half a nanosecond below its stored edge. A shared cut belongs to
    // the incoming clip on that frame, never to both or to the outgoing one.
    const arrived=libraryArrivals(time,project.settings?.fps??30);
    for (const [index,clip] of clips.entries()) {
      const asset = project.assets?.[clip.asset_id]; if (clip.enabled === false || !asset?.url || asset.status !== 'ready' || !arrived(clip.start) || arrived(clip.end)) continue;
      const clipTime = Math.max(time,clip.start), local = clipTime-clip.start, speed = Number(clip.speed)||1;
      if (asset.kind !== 'audio') {
        const key = `v:${clip.id}`, item = this.player(key,asset.kind === 'image' ? 'img' : 'video',asset.url); active.add(key);
        item.frame.hidden = false; Object.assign(item.frame.style,{left:`${clip.x*100}%`,top:`${clip.y*100}%`,width:`${clip.w*100}%`,height:`${clip.h*100}%`,zIndex:String(3+(trackOrder?.enabled ? trackOrder.visual.get(clip.id) : index))});
        item.frame.style.opacity=occurrenceFrameOpacity(clip,this.clipOpacity?.previewFor(project,clip.id));
        const motion=visualMotion(clip,clipTime),barsOnly=stillContainMatte(item,asset,clip,motion);
        item.frame.style.background=clip.fit==='contain'&&!barsOnly ? '#000':'transparent';
        Object.assign(item.element.style,{objectFit:clip.fit === 'contain' ? 'contain':'cover',transform:motion});
        if (asset.kind === 'video') { item.element.muted = true; const target = Number(clip.video_source_start ?? clip.source_start ?? 0)+local*speed; this.syncPlayer(item,Math.min(target,Math.max(0,Math.min(asset.duration,Number.isFinite(item.element.duration)?item.element.duration:asset.duration)-1e-6)),speed,playing && target < asset.duration,0); }
        if (asset.kind === 'video' && this.options.chromaPreview) {
          const settings=project.manual?.chroma_key?.[clip.asset_id];
          if(settings?.enabled || item.chroma) {
            item.chroma ||= this.options.chromaPreview(item.element);
            item.chroma.update(settings,project.assets?.[settings?.background_asset_id]?.url);
          }
          if(settings?.enabled && settings.background_mode==='transparent')item.frame.style.background='transparent';
        }
      }
      if (asset.kind === 'audio' || (asset.has_audio && clip.audio_enabled)) {
        const key=`a:${clip.id}`, item=this.player(key,'audio',asset.url,clip.role || 'music'); active.add(key);
        const rate = asset.kind === 'video' ? 1 : speed, target=Number(clip.source_start||0)+local*rate;
        item.role=clip.role||'music';
        this.syncPlayer(item,target,rate,playing && target < asset.duration,mediaGain(clip,mixer,clipTime,levels[clip.track_id])*soloGain(item.role)*(item.role==='music' ? this.duckGain:1));
      }
    }
    if (source.url && source.point && source.hasAudio) {
      const key='source', item=this.player(key,'audio',source.url,'source'); active.add(key);
      item.role='source';
      this.syncPlayer(item,source.point.sourceTime,1,playing,(mixer.source_muted ? 0 : 10**(Number(mixer.source_db||0)/20))*soloGain('source'));
    }
    for (const [key,item] of this.players) if (!active.has(key)) this.releasePlayer(key,item);
    this.updateMeters(playing);
  }
  meanSquare(analyser) {
    if (!analyser?.getFloatTimeDomainData) return 0;
    this.signalBuffers ||= new WeakMap();
    let samples = this.signalBuffers.get(analyser);
    if (samples?.length !== analyser.fftSize) { samples = new Float32Array(analyser.fftSize); this.signalBuffers.set(analyser,samples); }
    analyser.getFloatTimeDomainData(samples);
    return samples.reduce((sum,value)=>sum+value*value,0) / samples.length;
  }
  updateNormalizer(playing, mixer) {
    if (!this.normalizer) return;
    const normalization = mixerNormalization(this.project()), now = performance.now();
    const elapsed = Math.max(0, Math.min(.5, (now - (this.normalizerTime ?? now)) / 1000)); this.normalizerTime = now;
    if (!normalization || this.audioFallback) {
      this.normalizerDb = 0; this.loudnessWindow = []; this.normalizer.gain.value = 1; return;
    }
    this.loudnessWindow ||= [];
    if (playing && now >= (this.meterResetUntil || 0)) {
      this.loudnessWindow.push([now, this.meanSquare(this.loudnessAnalysers?.[0]) + this.meanSquare(this.loudnessAnalysers?.[1])]);
    }
    while (this.loudnessWindow.length && now - this.loudnessWindow[0][0] > PREVIEW_LOUDNESS_WINDOW_MS) this.loudnessWindow.shift();
    const covered = this.loudnessWindow.length ? now - this.loudnessWindow[0][0] : 0;
    const energy = this.loudnessWindow.reduce((sum,[,value])=>sum+value,0) / Math.max(1,this.loudnessWindow.length);
    let measured = energy > 0 ? -0.691 + 10 * Math.log10(energy) : -Infinity;
    // Before a second of playback is measured, start from the analyzed level of
    // the recording so the first words are not played at the wrong level.
    const summary = this.project()?.analysis?.audio?.summary;
    if (covered < 1000 && Number.isFinite(Number(summary?.integrated_rms_dbfs)) && !mixer.source_muted) {
      measured = Number(summary.integrated_rms_dbfs) + Number(mixer.source_db || 0) + 2.3;
    }
    if (this.normalizerDb == null) this.normalizerDb = Number.isFinite(measured) && measured >= -70 ? Math.max(-30, Math.min(30, normalization.target - measured)) : 0;
    this.normalizerDb = previewNormalizationGain(this.normalizerDb, measured, normalization.target, playing ? elapsed : 0);
    this.normalizer.gain.value = 10 ** (this.normalizerDb / 20);
  }
  signalPeak(analyser) {
    if (!analyser?.getFloatTimeDomainData) return 0;
    this.signalBuffers ||= new WeakMap();
    let samples = this.signalBuffers.get(analyser);
    const size = analyser.fftSize || 256;
    if (samples?.length !== size) { samples = new Float32Array(size); this.signalBuffers.set(analyser,samples); }
    analyser.getFloatTimeDomainData(samples);
    return samples.reduce((peak,value)=>Math.max(peak,Math.abs(value)),0);
  }
  updateMeters(playing) {
    const ready = Boolean(playing && !this.audioFallback && performance.now() >= (this.meterResetUntil || 0));
    const masterPeak = ready ? this.signalPeak(this.analyser) : 0;
    const value = peak => peak > 0 ? Math.max(0,Math.min(1,(20*Math.log10(peak)+60)/60)) : 0;
    const text = peak => peak > 0 ? `${(20*Math.log10(peak)).toFixed(1)} dBFS` : '-inf dBFS';
    for (const [role,{row,meter,level}] of this.channelMeters || []) {
      const hasPlayer = [...this.players.values()].some(item=>item.role === role && item.wanted && !item.element.paused && Number(item.gain?.gain?.value ?? item.element.volume) > 0);
      const peak = role === 'master' ? masterPeak : ready && hasPlayer ? this.signalPeak(this.audioBuses?.get(role)?.analyser) : 0;
      meter.value = value(peak); level.textContent = text(peak);
      row.classList.toggle('is-clipping',peak >= 1);
      meter.setAttribute('aria-valuetext',text(peak));
    }
    const root = this.audioRoot || this.root;
    const meter = root?.querySelector('.mixer-meter'); if (meter) meter.value = value(masterPeak);
    const state = !playing ? 'Paused · play to monitor' : this.audioFallback ? 'Basic preview · live meters unavailable' : !ready ? 'Seeking · waiting for live audio' : masterPeak >= 1 ? 'Clipping · lower a fader' : this.solo ? `Solo: ${this.solo === 'source' ? 'Original' : this.solo} · preview only` : 'Live browser mix';
    const status = root?.querySelector('.mixer-level-text'); if (status) status.textContent = state;
    const summary = root?.querySelector('.mixer-summary-level'); if (summary) summary.textContent = playing && ready ? text(masterPeak) : playing ? 'Preview' : 'Paused';
  }
  pause() {
    for(const item of this.players.values()){ item.wanted=false; item.token++; item.element.pause?.(); if(item.frame)item.frame.hidden=true; }
    this.meterResetUntil = 0; this.updateMeters(false);
  }
  releasePlayer(key,item) {
    item.chroma?.dispose();
    item.wanted=false; item.token++; item.element.pause?.();
    item.node?.disconnect(); item.gain?.disconnect(); item.analyser?.disconnect();
    item.element.removeAttribute?.('src'); item.element.load?.();
    (item.frame||item.element).remove?.(); this.players.delete(key);
  }
  clearPlayers() { for(const [key,item] of this.players)this.releasePlayer(key,item); }
}
