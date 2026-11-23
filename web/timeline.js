// Global output keep ranges deliberately leave excluded material visible.
// Optional independent A/B source clips occupy separate lanes on this clock.
export function timelineDuration(project) {
  const duration = Number(project?.manual?.sequence?.duration ?? project?.sources?.A?.duration);
  return Number.isFinite(duration) ? Math.max(0, duration) : 0;
}

const CAPTION_ROW_HEIGHT = 26;
const MIN_CAPTION_SECONDS = .1;

const TIMELINE_FONT = 'Geist, "Noto Sans Hebrew", "Segoe UI", sans-serif';
// Solid CSS colors only: CanvasRenderingContext2D does not resolve var(...).
// Old paint values remain the fallback for standalone/older hosts and tests.
const TIMELINE_COLOR_TOKENS = [
  "bg", "ruler", "lane", "lane-alt", "grid", "text", "clip", "clip-b",
  "clip-edge", "selected", "label", "wave", "wave-bg", "layout",
  "caption", "caption-edited", "caption-edge", "media-wave", "keep",
  "keep-alt", "keep-selected", "selection-fill", "move-fill", "danger",
  "danger-soft", "danger-fill", "danger-label", "gap-fill", "gap-edge",
  "layout-label", "on-selected",
];

function selectionMinimum(project) { return project?.manual?.sequence || project?.__sourceReview ? 1 / 60 - 1e-9 : .03; }

// The longest prefix of `text` that fits `width`, ending in an ellipsis when cut.
// Short blocks draw nothing rather than unreadable fragments.
export function fitCanvasLabel(ctx, text, width) {
  const value = String(text || "").trim();
  if (!value || width < 14) return "";
  if (ctx.measureText(value).width <= width) return value;
  let low = 0, high = value.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (ctx.measureText(`${value.slice(0, middle).trimEnd()}…`).width <= width) low = middle; else high = middle - 1;
  }
  return low >= 2 ? `${value.slice(0, low).trimEnd()}…` : "";
}

// Disabled occurrences stay editable; this note describes output, not a lock.
function disabledLayerNote(clip) {
  return clip?.enabled === false ? "Disabled in preview and export. " : "";
}

function sequenceFrame(project) {
  const fps = Number(project?.settings?.fps);
  return 1 / ([24, 25, 30, 50, 60].includes(fps) ? fps : 30);
}

// The navigator uses the project's integer output rate, never a source's
// embedded timecode or drop-frame notation. Invalid input must not seek to 0.
export function parseTimelineTimecode(input, fps = 30) {
  fps = [24, 25, 30, 50, 60].includes(Number(fps)) ? Number(fps) : 30;
  const value = String(input ?? "").trim();
  if (!value || !/^\d+(?:\.\d+)?(?::\d+(?:\.\d+)?){0,3}$/.test(value)) return null;
  const parts = value.split(":");
  if (parts.length === 1) return Number.isFinite(Number(value)) ? Number(value) : null;
  if (parts.slice(0, -1).some(part => !/^\d+$/.test(part))) return null;
  const numbers = parts.map(Number);
  if (numbers.some(number => !Number.isFinite(number))) return null;
  if (parts.length === 4) {
    const [hours, minutes, seconds, frames] = numbers;
    if (!/^\d+$/.test(parts[3]) || minutes >= 60 || seconds >= 60 || frames >= fps) return null;
    return hours * 3600 + minutes * 60 + seconds + frames / fps;
  }
  const seconds = numbers.at(-1);
  if (seconds >= 60 || (parts.length === 3 && numbers[1] >= 60)) return null;
  return (parts.length === 3 ? numbers[0] * 3600 + numbers[1] * 60 : numbers[0] * 60) + seconds;
}

// Persistent imported-media/custom-text tracks are opt-in. Read-only consumers
// never materialize legacy rows or pretend an unknown schema is the old model.
export function timelineLayerTrackState(project) {
  const manual=project?.manual || {}, value=manual.layer_tracks;
  if (!Object.hasOwn(manual,"layer_tracks")) {
    const orphan=[manual.media_clips,manual.text_clips].some(rows=>Array.isArray(rows)&&rows.some(clip=>clip && Object.hasOwn(clip,"track_id")));
    return { enabled:orphan, valid:!orphan, tracks:[] };
  }
  const tracks = value?.tracks, ids = new Set();
  const valid = value && !Array.isArray(value) && Object.keys(value).sort().join()===(value.version === 3 ? "protection_version,tracks,version" : "tracks,version")
    && [1, 2, 3].includes(value.version) && (value.version !== 3 || [1, 2].includes(value.protection_version)) && Array.isArray(tracks) && tracks.length<=4096 && tracks.every(track => {
    if (!track || typeof track.id !== "string" || !/^track_[0-9a-f]{32}$/.test(track.id) || ids.has(track.id)
      || (Object.keys(track).sort().join()!==(value.version === 3 && track.kind !== "text" ? "audio,id,kind,locked,name" : value.version >= 2 ? "id,kind,locked,name" : "id,kind,name") || (value.version >= 2 && typeof track.locked !== "boolean"))
      || (value.version === 3 && (value.protection_version === 1 && track.locked || track.kind !== "text" && (!track.audio || Array.isArray(track.audio) || Object.keys(track.audio).sort().join()!=="gain_db,muted" || !Number.isFinite(track.audio.gain_db) || track.audio.gain_db < -60 || track.audio.gain_db > 12 || typeof track.audio.muted !== "boolean"))) || !["visual", "audio", "text"].includes(track.kind) || typeof track.name !== "string"
      || !track.name.trim() || track.name!==track.name.trim() || [...track.name].length > 80) return false;
    ids.add(track.id); return true;
  });
  return { enabled: true, valid: Boolean(valid), tracks: valid ? tracks : [] };
}

function timelineLayerKind(project, clip) {
  if (clip?.id?.startsWith("text_")) return "text";
  const kind = project?.assets?.[clip?.asset_id]?.kind;
  return kind === "audio" ? "audio" : ["video", "image"].includes(kind) ? "visual" : null;
}

// This is an index of existing timeline items, not a second editable model.
// Build it again when a project changes, and resolve keys again on selection.
export function timelineIndexEntries(project, getTrackClips) {
  const duration = timelineDuration(project), entries = [], trackState = timelineLayerTrackState(project),
    trackNames = new Map(trackState.tracks.map(track => [track.id, track.name])),
    lockedTracks = new Set(trackState.tracks.filter(track => track.locked === true).map(track => track.id));
  const add = (clip, detail) => {
    const start = Math.max(0, Number(clip?.start)), end = Math.min(duration, Number(clip?.end));
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    entries.push({ ...detail, start, end, id: clip.id || null,
      key: `${detail.category}:${detail.slot || ""}:${clip.id || `${start}:${end}`}` });
  };
  const tracks = Boolean((project?.sources?.B || project?.manual?.source_tracks?.A || project?.manual?.sequence) && getTrackClips);
  if (!project?.manual?.sequence) {
    for (const clip of editableClips(project)) add(clip, {
      category: "source", slot: "edit", kind: "video", track: "Edit",
      name: project?.sources?.A?.name || "Primary video", locked: false,
    });
  }
  if (tracks) for (const slot of ["A", "B"]) {
    if (!project?.sources?.[slot]) continue;
    for (const clip of getTrackClips(project, slot) || []) add(clip, {
      category: "source", slot, kind: "video", track: `Video ${slot}`,
      name: project.sources[slot].name || `Source ${slot}`, locked: project.manual?.track_locks?.[slot] === true,
    });
  }
  for (const clip of project?.manual?.media_clips || []) {
    const asset = project?.assets?.[clip.asset_id];
    if (!asset || !clip.id) continue;
    add(clip, { category: "media", asset_id: clip.asset_id, kind: asset.kind || "video", name: asset.name || "Media", enabled: clip.enabled !== false, locked: lockedTracks.has(clip.track_id),
      track: trackState.enabled ? trackNames.get(clip.track_id) || "Unassigned track"
        : asset.kind === "audio" ? ({ music: "Music", voice: "Voiceover", effects: "Effects" }[clip.role] || "Audio") : "Visual" });
  }
  for (const clip of project?.manual?.text_clips || []) {
    if (!clip.id) continue;
    add(clip, { category: "media", kind: "text", name: clip.text || "Untitled text", enabled: clip.enabled !== false, locked: lockedTracks.has(clip.track_id), track: trackState.enabled ? trackNames.get(clip.track_id) || "Unassigned track" : clip.kind === "caption" ? "Text caption" : "Title" });
  }
  for (const clip of project?.editor_captions || []) {
    if (!clip.id) continue;
    add(clip, { category: "caption", kind: "caption", name: clip.text || "Empty caption", track: clip.hidden ? "Caption (hidden)" : "Caption" });
  }
  return entries.sort((a, b) => a.start - b.start || a.end - b.end || a.key.localeCompare(b.key));
}

export function adjacentTimelineEdit(clips, playhead, duration, direction) {
  if (!Number.isFinite(duration) || duration <= 0 || ![-1, 1].includes(direction)) return null;
  let result = null;
  const consider = time => {
    if (!Number.isFinite(time) || time < 0 || time > duration) return;
    if (direction < 0 && time < playhead - 1e-6 && (result == null || time > result)) result = time;
    if (direction > 0 && time > playhead + 1e-6 && (result == null || time < result)) result = time;
  };
  consider(0); consider(duration);
  for (const clip of clips) { consider(Number(clip.start)); consider(Number(clip.end)); }
  return result;
}

// Counts only: describe existing occurrences, never decide whether an edit is
// safe or mutate the timeline. The app and server own deletion readiness.
export function timelineRangeDeleteImpact(project, range, target = "edit", getTrackClips) {
  const duration = timelineDuration(project), start = range?.start, end = range?.end;
  if (!project?.manual?.sequence || !project?.draft || !["edit", "A", "B"].includes(target)
    || !range || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > duration || end <= start
    || (target !== "edit" && !project.sources?.[target])) return null;
  const count = (clips, ripple = true) => {
    const result = { removed: 0, trimmed: 0, split: 0, shifted: 0, unchanged: 0, unknown: 0 };
    for (const clip of clips || []) {
      const a = clip?.start, b = clip?.end;
      if (!Number.isFinite(a) || !Number.isFinite(b) || b <= a) { result.unknown++; continue; }
      if (b <= start + 1e-9) result.unchanged++;
      else if (a >= end - 1e-9) result[ripple ? "shifted" : "unchanged"]++;
      else if (a >= start - 1e-9 && b <= end + 1e-9) result.removed++;
      else if (a < start - 1e-9 && b > end + 1e-9) result.split++;
      else result.trimmed++;
    }
    return result;
  };
  const sources = {};
  for (const slot of target === "edit" ? ["A", "B"] : [target]) {
    if (!project.sources?.[slot]) continue;
    const clips = getTrackClips ? getTrackClips(project, slot) : project.editor_sequence?.source_tracks?.[slot] || project.manual.source_tracks?.[slot] || [];
    sources[slot] = count(clips, target === "edit");
  }
  return { target, start, end, removedTime: target === "edit" ? end - start : 0,
    durationBefore: duration, durationAfter: target === "edit" ? duration - (end - start) : duration,
    sources, media: target === "edit" ? count(project.manual.media_clips) : null,
    text: target === "edit" ? count(project.manual.text_clips) : null };
}

export function editableClips(project) {
  const duration = timelineDuration(project);
  const minimum = selectionMinimum(project);
  if (!Number.isFinite(duration) || duration <= 0) return [];
  const points = [...new Set((project?.draft?.edit_points || []).map(Number)
    .filter((time) => Number.isFinite(time) && time > 0 && time < duration))].sort((a, b) => a - b);
  const ranges = (project?.draft?.keep_ranges || [])
    .map((range) => ({ start: Math.max(0, Number(range.start)), end: Math.min(duration, Number(range.end)) }))
    .filter((range) => Number.isFinite(range.start) && Number.isFinite(range.end) && range.end - range.start >= minimum)
    .sort((a, b) => a.start - b.start || a.end - b.end);
  const clips = [];
  let coveredUntil = 0;
  for (const range of ranges) {
    const start = Math.max(range.start, coveredUntil);
    if (range.end - start < minimum) continue;
    const boundaries = [start];
    for (const point of points) {
      if (point >= boundaries[boundaries.length - 1] + minimum && point <= range.end - minimum) boundaries.push(point);
    }
    boundaries.push(range.end);
    for (let index = 0; index < boundaries.length - 1; index++) {
      if (boundaries[index + 1] - boundaries[index] >= minimum) {
        clips.push({ start: boundaries[index], end: boundaries[index + 1], index: clips.length });
      }
    }
    coveredUntil = range.end;
  }
  return clips;
}

// A Together block ends at every A/B cut. Camera-layout boundaries do not
// create extra video cuts, and a completely empty gap is not a draggable clip.
export function sequenceBlocks(project, getTrackClips) {
  const duration = timelineDuration(project), minimum = selectionMinimum(project);
  const edges = new Map();
  for (const slot of ["A", "B"]) {
    if (!project?.sources?.[slot]) continue;
    for (const clip of getTrackClips?.(project, slot) || []) {
      const start = Math.max(0, Number(clip.start)), end = Math.min(duration, Number(clip.end));
      if (!Number.isFinite(start) || !Number.isFinite(end) || end - start < minimum) continue;
      edges.set(start, (edges.get(start) || 0) + 1);
      edges.set(end, (edges.get(end) || 0) - 1);
    }
  }
  const boundaries = [...edges.keys()].sort((a, b) => a - b), blocks = [];
  let active = 0;
  for (let index = 0; index < boundaries.length - 1; index++) {
    const start = boundaries[index], end = boundaries[index + 1];
    active += edges.get(start);
    if (active > 0 && end > start) blocks.push({ start, end, index: blocks.length });
  }
  return blocks;
}

export function sequenceGaps(project, getTrackClips, slot = null) {
  const clips = (slot ? getTrackClips(project, slot) : ["A", "B"].flatMap(s => project?.sources?.[s] ? getTrackClips(project,s) : []))
    .concat(slot ? [] : [...(project?.manual?.media_clips || []), ...(project?.manual?.text_clips || [])])
    .slice().sort((a,b)=>a.start-b.start);
  const gaps = []; let cursor = 0;
  for (const clip of clips) {
    if (clip.start > cursor + 1e-6) gaps.push({start:cursor,end:clip.start});
    cursor = Math.max(cursor,clip.end);
  }
  if (timelineDuration(project) > cursor + 1e-6) gaps.push({start:cursor,end:timelineDuration(project)});
  return gaps;
}

export function sequenceGapClosureIssue(project, gaps, slot = null) {
  if (slot || !gaps.length) return "";
  const activeCaption = project?.caption_alternative_status?.active_id;
  if (activeCaption && activeCaption !== "original") return "An alternative caption version is active. Switch back to original captions before closing gaps together.";
  if (Object.values(project?.manual?.caption_overrides || {}).some(edit => Number(edit?.start_delta || 0) !== 0 || Number(edit?.end_delta || 0) !== 0)) {
    return "A transcript caption has custom timing. Reset that caption's timing before closing gaps together.";
  }
  const layers = [...(project?.manual?.media_clips || []), ...(project?.manual?.text_clips || [])];
  return layers.some(row => gaps.some(gap => row.start < gap.end - 1e-6 && row.end > gap.start + 1e-6))
    ? "This space contains added media or text. Only time empty on every layer can be closed together."
    : "";
}

export function rippleMoveStart(project, start, end, at, slot = null, getTrackClips = null) {
  const length = end-start;
  let maximum = Math.max(0,timelineDuration(project)-length);
  if (slot && getTrackClips) {
    maximum = 0;
    for (const clip of getTrackClips(project,slot)) {
      if (clip.start < start) maximum = Math.max(maximum,Math.min(clip.end,start));
      if (clip.end > end) maximum = Math.max(maximum,clip.end-length);
    }
  }
  return Math.max(0,Math.min(maximum,at));
}

export class TimelineView {
  constructor(canvas, scroll, onSeek, onSelectionChange = null, onEdit = null, options = {}) {
    this.canvas = canvas;
    this.scroll = scroll;
    this.context = canvas.getContext("2d", { alpha: false });
    this.onSeek = onSeek;
    this.onSelectionChange = onSelectionChange;
    this.onEdit = onEdit;
    this.onLayoutSelect = options.onLayoutSelect;
    this.onToolStateChange = options.onToolStateChange;
    this.onTargetChange = options.onTargetChange;
    this.onMediaSelect = options.onMediaSelect;
    this.onAssetOccurrenceSelect = options.onAssetOccurrenceSelect;
    this.assetOccurrenceIssue = options.assetOccurrenceIssue;
    this.onMediaEdit = options.onMediaEdit;
    this.onMediaPreview = options.onMediaPreview;
    this.onMediaAction = options.onMediaAction;
    this.mediaSplitIssue = options.mediaSplitIssue;
    this.mediaTrimPreview = options.mediaTrimPreview;
    this.mediaSlipPreview = options.mediaSlipPreview;
    this.mediaMovePreview = options.mediaMovePreview;
    this.mediaTrackMovePreview = options.mediaTrackMovePreview;
    this.onTrackManage = options.onTrackManage;
    this.trackLockIssue = options.trackLockIssue;
    this.trackHeaderReadiness = options.trackHeaderReadiness;
    this.trackLockPending = null;
    this.mediaTrackMovePending = null;
    this.onMediaSelectionChange = options.onMediaSelectionChange;
    this.mediaGroupMovePreview = options.mediaGroupMovePreview;
    this.mediaGroupRelocatePreview = options.mediaGroupRelocatePreview;
    this.mediaGroupRelocationPending = null;
    this.mediaGroupRemoveIssue = options.mediaGroupRemoveIssue;
    this.mediaGroupDuplicateIssue = options.mediaGroupDuplicateIssue;
    this.mediaGroupRemovalPending = null;
    this.onMediaGroupPreview = options.onMediaGroupPreview;
    this._mediaSelection = null;
    this.mediaSelectionSet = [];
    this.mediaSelectionPending = null;
    this.mediaSourceIssue = options.mediaSourceIssue;
    this.onMediaSourceOpen = options.onMediaSourceOpen;
    this.mediaSourceOpening = null;
    this.onCaptionSelect = options.onCaptionSelect;
    this.onCaptionEdit = options.onCaptionEdit;
    this.onCaptionAction = options.onCaptionAction;
    this.onCaptionOpen = options.onCaptionOpen;
    this.rangeDeleteIssue = options.rangeDeleteIssue;
    this.captionSelection = null;
    this.getTrackClips = options.getTrackClips;
    this.getAudioSlot = options.getAudioSlot;
    this.sourceReview = Boolean(options.sourceReview);
    this.editTarget = "edit";
    this.canEdit = options.canEdit || (() => true);
    this.cutAnchor = null;
    this.editPending = false;
    this.snapping = false;
    this.snapGuide = null;
    this.project = null;
    this.zoom = 1;
    this.zoomFocusPending = false;
    this.playhead = 0;
    this.hoverTime = null;
    this.bladeHover = null;
    this.mediaTrimHover = null;
    this.mediaSlipHover = null;
    this.mediaMoveHover = null;
    this.baseCanvasTitle = canvas.title || "";
    this.images = [];
    this.imageUrls = [];
    this.imageLoadGeneration = 0;
    this.scrubbing = false;
    this.selecting = false;
    this.selectionAnchor = null;
    this.selectionCursor = null;
    this.selection = null;
    this.tool = "select";
    this.gesture = null;
    this.raf = null;
    this.afterDraw = null;
    this.themeColors = Object.create(null);
    this.themeDirty = true;
    this.resizeObserver = new ResizeObserver(() => this.scheduleDraw());
    this.resizeObserver.observe(scroll);
    canvas.addEventListener("pointerdown", (event) => this.pointerDown(event));
    canvas.addEventListener("pointermove", (event) => this.pointerMove(event));
    canvas.addEventListener("pointerup", (event) => this.pointerUp(event));
    canvas.addEventListener("pointercancel", (event) => this.pointerCancel(event));
    canvas.addEventListener("lostpointercapture", (event) => this.pointerCancel(event));
    canvas.addEventListener("pointerleave", () => { if (!this.gesture) { this.hoverTime = null; this.snapGuide = null; this.clearBladeHover(); this.clearMediaTrimHover(); this.clearMediaSlipHover(); this.clearMediaMoveHover(); this.scheduleDraw(); } });
    canvas.addEventListener("keydown", (event) => this.keyDown(event));
    scroll.addEventListener("wheel", (event) => this.handleWheel(event), { passive: false });
    scroll.addEventListener("scroll", () => this.scheduleDraw(), { passive: true });
    canvas.addEventListener("dblclick", (event) => this.doubleClick(event));
    this.observeTheme();
    this.navigation = createTimelineNavigation(this);
    this.rangeImpact = createTimelineRangeImpact(this);
  }

  // A legacy single-ID assignment is always an explicit single selection.
  // Group restoration goes through setMediaSelection, never this setter.
  get mediaSelection() { return this._mediaSelection || null; }
  set mediaSelection(id) {
    this._mediaSelection = id || null;
    this.mediaSelectionSet = id ? [id] : [];
  }

  selectedMediaIds() { return [...(this.mediaSelectionSet || (this.mediaSelection ? [this.mediaSelection] : []))]; }

  setMediaSelection(ids, primary = null) {
    if (!Array.isArray(ids) || ids.length > 200 || new Set(ids).size !== ids.length) return false;
    const rows = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])];
    if (ids.some(id => typeof id !== "string" || !rows.some(row => row.id === id))) return false;
    this.mediaSelectionSet = [...ids];
    this._mediaSelection = ids.includes(primary) ? primary : ids.at(-1) || null;
    this.scheduleDraw(); this.navigation?.sync?.();
    return true;
  }

  async requestMediaSelection(ids, primary = null) {
    if (!this.onMediaSelectionChange || !Array.isArray(ids) || ids.length > 200
      || this.sourceReview || this.gesture || this.editPending || (this.mediaSelectionPending && ids.length)) return false;
    if (ids.length && !this.canEdit()) return false;
    const request = {projectId:this.project?.id, ids:[...ids], primary};
    this.mediaSelectionPending = request; this.navigation?.sync?.(); this.onToolStateChange?.();
    try {
      // The host flushes current inspectors and sets the trusted selection only
      // after its own project/selection epoch checks. No optimistic replacement.
      const accepted=await this.onMediaSelectionChange([...ids], primary);
      return accepted===true && this.project?.id===request.projectId && this.mediaSelectionPending===request;
    } catch (error) {
      if (this.project?.id === request.projectId && this.mediaSelectionPending === request)
        this.canvas.title = error?.message || "Selection could not change. Resolve the pending edit first.";
      return false;
    } finally {
      if (this.mediaSelectionPending === request) this.mediaSelectionPending = null;
      this.navigation?.sync?.(); this.onToolStateChange?.(); this.scheduleDraw();
    }
  }

  toggleMediaSelection(id) {
    const ids = this.selectedMediaIds(), next = ids.includes(id) ? ids.filter(value => value !== id) : [...ids,id];
    if (next.length > 200) { this.canvas.title = "Select up to 200 imported media and custom text clips."; return Promise.resolve(false); }
    return this.requestMediaSelection(next, next.includes(id) ? id : next.at(-1));
  }

  mediaGroupIdentity(ids) {
    const project=this.project, rows=[...(project?.manual?.media_clips||[]),...(project?.manual?.text_clips||[])];
    return JSON.stringify([project?.id,project?.revision,timelineDuration(project),project?.settings?.fps,project?.manual?.layer_tracks,
      ids.map(id=>{const clip=rows.find(row=>row.id===id),asset=project?.assets?.[clip?.asset_id];
        return [clip,asset && [asset.id,asset.kind,asset.status,asset.path,asset.relative_path,asset.generation,asset.duration,asset.width,asset.height]];})]);
  }

  mediaGroupPlan(ids, delta) {
    const blocked=issue=>({issue,delta,patches:null});
    const protection = Array.isArray(ids) && ids.map(id => this.mediaProtectionIssue(id)).find(Boolean);
    if (protection) return blocked(protection);
    if (this.sourceReview || this.editPending || this.mediaSelectionPending || !this.canEdit()) return blocked("Wait for the current edit to finish.");
    if (!Array.isArray(ids) || ids.length<2 || ids.length>200 || new Set(ids).size!==ids.length || !Number.isFinite(delta)) return blocked("Select 2 to 200 imported media or custom text clips.");
    const rows=[...(this.project?.manual?.media_clips||[]),...(this.project?.manual?.text_clips||[])];
    if (ids.some(id=>!rows.some(row=>row.id===id))) return blocked("A selected layer is no longer available. Select the group again.");
    let plan;try{plan=this.mediaGroupMovePreview?.([...ids],delta);}catch{ /* Fail closed, never fall through to single-item writes. */ }
    if (!plan || typeof plan.issue!=="string") return blocked("Group move readiness could not be confirmed.");
    if (plan.issue) return blocked(plan.issue);
    if (!Number.isFinite(plan.delta) || !Array.isArray(plan.patches) || (plan.patches.length && plan.patches.length!==ids.length)) return blocked("Group move preview is incomplete.");
    const seen=new Set(),duration=timelineDuration(this.project);
    for(const patch of plan.patches){
      const clip=rows.find(row=>row.id===patch?.clip_id),precision=String(patch?.clip_id).startsWith("text_")?1e-6:1e-8;
      if(!clip || !ids.includes(patch.clip_id) || seen.has(patch.clip_id) || Object.keys(patch).sort().join()!=="clip_id,end,start"
        || !Number.isFinite(patch.start) || !Number.isFinite(patch.end) || patch.start<0 || patch.end>duration+1e-9
        || Math.abs((patch.end-patch.start)-(clip.end-clip.start))>precision
        || Math.abs((patch.start-clip.start)-plan.delta)>precision) return blocked("Group move preview does not preserve the selected clips.");
      seen.add(patch.clip_id);
    }
    return plan;
  }

  mediaGroupRelocatePlan(ids, anchorId, delta, trackId) {
    const blocked=issue=>({issue,delta,patches:null});
    if (this.sourceReview || this.editPending || this.mediaSelectionPending || this.trackLockPending || !this.canEdit())
      return blocked("Wait for the current edit to finish.");
    if (!Array.isArray(ids) || ids.length<2 || ids.length>200 || new Set(ids).size!==ids.length
      || ids.some(id=>typeof id!=="string") || !ids.includes(anchorId) || !Number.isFinite(delta))
      return blocked("Select 2 to 200 imported media or custom text clips again.");
    if (typeof this.mediaGroupRelocatePreview!=="function")
      return blocked("Group moves keep their existing tracks in this editor. Select one clip to move it to another track.");
    const state=timelineLayerTrackState(this.project), media=this.project?.manual?.media_clips || [], text=this.project?.manual?.text_clips || [];
    if (!state.enabled || !state.valid) return blocked("Moving a group between tracks requires compatible saved tracks.");
    if (!Array.isArray(media) || !Array.isArray(text)) return blocked("The current layer list could not be verified. Reopen the project.");
    const rows=[...media,...text], clips=ids.map(id=>rows.filter(row=>row?.id===id));
    if (clips.some(matches=>matches.length!==1)) return blocked("A selected layer is no longer available. Select the group again.");
    const selected=clips.map(matches=>matches[0]), anchor=selected.find(clip=>clip.id===anchorId), kind=timelineLayerKind(this.project,anchor);
    if (!kind || selected.some(clip=>timelineLayerKind(this.project,clip)!==kind))
      return blocked("Move between tracks with a selection of only pictures, only audio, or only custom text. Mixed selections can move in time only.");
    const tracks=state.tracks.filter(track=>track.kind===kind), target=tracks.find(track=>track.id===trackId),
      sourceIndex=tracks.findIndex(track=>track.id===anchor.track_id);
    if (!target || sourceIndex<0) return blocked("Choose an existing compatible track row. Source A/B, automatic captions and blank space are not destinations.");
    const offset=tracks.indexOf(target)-sourceIndex, destinations=new Map();
    for (const clip of selected) {
      const index=tracks.findIndex(track=>track.id===clip.track_id), destination=tracks[index+offset];
      if (index<0 || !destination) return blocked("The whole selection must fit on existing compatible tracks, keeping its track spacing.");
      const locked=tracks[index].locked===true ? tracks[index] : destination.locked===true ? destination : null;
      if (locked) return blocked(`Track "${locked.name}" is locked. Unlock it before moving this selection.`);
      destinations.set(clip.id,destination.id);
    }
    let plan;try { plan=this.mediaGroupRelocatePreview([...ids],anchorId,delta,trackId); } catch { /* No single-item or horizontal fallback. */ }
    if (!plan || typeof plan.issue!=="string") return blocked("Group track move readiness could not be confirmed.");
    if (plan.issue) return blocked(plan.issue);
    if (!Number.isFinite(plan.delta) || Math.abs(plan.delta-delta)>1e-9 || !Array.isArray(plan.patches)
      || (plan.patches.length && plan.patches.length!==ids.length) || (!plan.patches.length && (offset!==0 || Math.abs(plan.delta)>1e-9)))
      return blocked("Group track move preview is incomplete.");
    const seen=new Set(), duration=timelineDuration(this.project);
    for (const patch of plan.patches) {
      const clip=selected.find(clip=>clip.id===patch?.clip_id), precision=String(patch?.clip_id).startsWith("text_")?1e-6:1e-8;
      if (!clip || seen.has(patch.clip_id) || Object.keys(patch).sort().join()!=="clip_id,end,start,track_id"
        || patch.track_id!==destinations.get(clip.id) || !Number.isFinite(patch.start) || !Number.isFinite(patch.end)
        || patch.start<0 || patch.end>duration+1e-9 || patch.end<=patch.start
        || Math.abs((patch.end-patch.start)-(clip.end-clip.start))>precision
        || Math.abs((patch.start-clip.start)-plan.delta)>precision
        || (delta===0 && (plan.delta!==0 || patch.start!==clip.start || patch.end!==clip.end)))
        return blocked("Group track move preview does not preserve the selected clips and track spacing.");
      seen.add(patch.clip_id);
    }
    return plan;
  }

  mediaGroupDelta(gesture, event) {
    // A pure vertical move must not acquire a timing edit from nearby magnets.
    // This is the same exact pointer-clock check used by single tracked clips.
    if (gesture.trackId && this.timeFromEvent(event)===gesture.startTime) return 0;
    const head=Math.min(...gesture.clips.map(clip=>clip.start)),tail=Math.max(...gesture.clips.map(clip=>clip.end)),
      offsets=gesture.clips.flatMap(clip=>[clip.start-head,clip.end-head]),
      desired=head+this.timeFromEvent(event)-gesture.startTime,
      start=this.snappedTime(desired,event,offsets);
    return Math.max(-head,Math.min(timelineDuration(this.project)-tail,start-head));
  }

  moveMediaGroup(ids, delta) {
    const plan=this.mediaGroupPlan(ids,delta);
    if(!this.onMediaAction || plan.issue || !plan.patches?.length || Math.abs(plan.delta)<=1e-9)return false;
    this.editPending=true;this.onToolStateChange?.();
    const finish=()=>{this.editPending=false;this.onToolStateChange?.();this.scheduleDraw();};
    try { const result=this.onMediaAction("layers_move",{clip_ids:[...ids],delta:plan.delta});
      if(result?.then)Promise.resolve(result).then(finish,finish);else finish();
    }catch(error){finish();throw error;}
    return true;
  }

  relocateMediaGroup(ids, anchorId, delta, trackId) {
    const plan=this.mediaGroupRelocatePlan(ids,anchorId,delta,trackId);
    if (typeof this.onMediaAction!=="function" || plan.issue || !plan.patches?.length) return false;
    const rows=[...(this.project?.manual?.media_clips||[]),...(this.project?.manual?.text_clips||[])];
    if (plan.patches.every(patch=>{const clip=rows.find(row=>row?.id===patch.clip_id);
      return clip && clip.start===patch.start && clip.end===patch.end && clip.track_id===patch.track_id;})) return false;
    const request={projectId:this.project?.id,project:this.project,ids:[...ids],anchorId,trackId,delta:plan.delta};this.mediaGroupRelocationPending=request;
    this.editPending=true;this.navigation?.sync?.();this.onToolStateChange?.();
    const finish=error=>{
      if (this.mediaGroupRelocationPending!==request) return;
      this.mediaGroupRelocationPending=null;this.editPending=false;
      if (error && this.project===request.project) this.canvas.title=error?.message || "The selected clips were not moved. Review the edit before trying again.";
      this.navigation?.sync?.();this.onToolStateChange?.();this.scheduleDraw();
    };
    try {
      // Only the host may install the strict revision-bound transaction receipt.
      // Keep both the saved project and the original selected primary unchanged.
      const result=this.onMediaAction("layers_relocate",{clip_ids:[...ids],anchor_id:anchorId,track_id:trackId,delta:plan.delta});
      if (result?.then) Promise.resolve(result).then(()=>finish(),finish);else finish();
    } catch (error) { finish(error);return false; }
    return true;
  }

  mediaGroupActionHint() {
    const duplicate = typeof this.mediaGroupDuplicateIssue === "function";
    const remove = typeof this.mediaGroupRemoveIssue === "function";
    const trackMove=typeof this.mediaGroupRelocatePreview==="function"
      ? " Same-kind selections can move between compatible saved tracks, keeping their track spacing; mixed selections move in time only." : "";
    if (duplicate) return `Move or duplicate the selected clips together${remove ? ", or remove them" : ""}. Use Duplicate at playhead to copy the whole arrangement without changing its timing offsets or the timeline duration. Originals stay unchanged. Select one clip for other edits.${trackMove}`;
    return remove
      ? `Move or remove the selected clips together. Removal keeps timeline duration and original media. Select one clip for other edits.${trackMove}`
      : `This selection supports moving together only. Select one layer for other edits.${trackMove}`;
  }

  removeMediaGroup() {
    if (this.sourceReview || this.gesture || this.editPending || this.mediaSelectionPending || this.mediaSourceOpening || !this.canEdit()) return false;
    if (typeof this.mediaGroupRemoveIssue !== "function" || typeof this.onMediaAction !== "function") { this.canvas.title=this.mediaGroupActionHint(); return false; }
    const ids=this.selectedMediaIds(), media=this.project?.manual?.media_clips || [], text=this.project?.manual?.text_clips || [];
    if(!Array.isArray(media) || !Array.isArray(text)){this.canvas.title="The current layer list could not be verified. Reopen the project before removing clips.";return false;}
    const rows=[...media,...text];
    if (ids.length<2 || ids.length>200 || new Set(ids).size!==ids.length || ids.some(id=>typeof id!=="string" || rows.filter(row=>row?.id===id).length!==1)) {
      this.canvas.title="A selected layer is no longer available. Select 2 to 200 imported media or custom text clips again."; return false;
    }
    const protection=ids.map(id=>this.mediaProtectionIssue(id)).find(Boolean);
    if(protection){this.canvas.title=protection;return false;}
    let issue;
    try { issue=this.mediaGroupRemoveIssue([...ids]); } catch { /* A missing readiness result must never become a primary-only Remove. */ }
    if (typeof issue!=="string" || issue) { this.canvas.title=typeof issue==="string" ? issue : "Selection removal readiness could not be confirmed."; return false; }
    const request={projectId:this.project?.id};this.mediaGroupRemovalPending=request;
    this.editPending=true;this.navigation?.sync?.();this.onToolStateChange?.();
    const finish=error=>{
      if(this.mediaGroupRemovalPending!==request)return;
      this.mediaGroupRemovalPending=null;this.editPending=false;
      if(error && this.project?.id===request.projectId)this.canvas.title=error?.message || "The selected clips were not removed. Review the current edit before trying again.";
      this.navigation?.sync?.();this.onToolStateChange?.();this.scheduleDraw();
    };
    try {
      // The host pins revision/membership and owns the saved result. Do not
      // remove clips or clear their temporary selection optimistically here.
      const result=this.onMediaAction("layers_remove",{clip_ids:[...ids]});
      if(result?.then)Promise.resolve(result).then(()=>finish(),finish);else finish();
    } catch(error) { finish(error); return false; }
    return true;
  }

  observeTheme() {
    const doc = this.canvas.ownerDocument || (typeof document !== "undefined" ? document : null);
    const view = doc?.defaultView || (typeof window !== "undefined" ? window : null);
    const Observer = view?.MutationObserver || (typeof MutationObserver !== "undefined" ? MutationObserver : null);
    const repaint = () => { this.themeDirty = true; this.scheduleDraw(); };
    if (doc?.documentElement && typeof Observer === "function") {
      this.themeObserver = new Observer(repaint);
      this.themeObserver.observe(doc.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    }
    // Font arrival changes measured label widths even while playback is paused.
    // Each timeline (including source review) gets one coalesced repaint.
    doc?.fonts?.ready?.then?.(repaint, () => {});
  }

  refreshTheme() {
    if (this.themeColors && !this.themeDirty) return;
    this.themeDirty = false;
    this.themeColors = Object.create(null);
    const doc = this.canvas?.ownerDocument || (typeof document !== "undefined" ? document : null);
    const view = doc?.defaultView || (typeof window !== "undefined" ? window : null);
    if (!this.canvas || typeof view?.getComputedStyle !== "function") return;
    const style = view.getComputedStyle(this.canvas);
    for (const name of TIMELINE_COLOR_TOKENS) {
      const value = style.getPropertyValue(`--timeline-${name}`).trim();
      if (value && (!view.CSS?.supports || view.CSS.supports("color", value))) this.themeColors[name] = value;
    }
  }

  color(name, fallback) {
    this.refreshTheme();
    return this.themeColors[name] || fallback;
  }

  font(size, weight = "") {
    return `${weight ? `${weight} ` : ""}${size}px ${TIMELINE_FONT}`;
  }

  setProject(project) {
    const previousProjectId = this.project?.id, selectedIds = this.selectedMediaIds(), primary = this.mediaSelection;
    this.snapGuide = null;
    this.zoomFocusPending = false;
    this.afterDraw = null;
    this.cancelGesture(false);
    this.cancelPendingCut();
    this.clearBladeHover();
    this.clearMediaTrimHover();
    this.clearMediaSlipHover();
    this.clearMediaMoveHover();
    this.project = project;
    const currentIds = new Set([...(project?.manual?.media_clips || []), ...(project?.manual?.text_clips || [])].map(clip=>clip.id));
    this.setMediaSelection(previousProjectId===project?.id ? selectedIds.filter(id=>currentIds.has(id)) : [], primary);
    if (previousProjectId !== project?.id) {
      this.trackLockPending = null;
      this.mediaSelectionPending = null;
      if(this.mediaTrackMovePending){this.mediaTrackMovePending=null;this.editPending=false;}
      if(this.mediaGroupRemovalPending){this.mediaGroupRemovalPending=null;this.editPending=false;}
      if(this.mediaGroupRelocationPending){this.mediaGroupRelocationPending=null;this.editPending=false;}
      this.images = [];
      this.imageUrls = [];
      this.mediaImages = new Map();
    }
    // A caption keeps its selection across edits while it is still on the timeline.
    if (this.captionSelection && !this.captionItems()?.some(item => item.id === this.captionSelection)) this.selectCaption(null, true);
    if (!this.hasTrackLanes() || (this.editTarget !== "edit" && !project?.sources?.[this.editTarget])) this.setEditTarget("edit");
    this.clearSelection(false);
    const duration = timelineDuration(project);
    this.canvas.setAttribute("aria-valuemax", String(duration));
    this.updateAccessiblePlayhead();
    this.loadImages();
    this.navigation?.refresh();
    this.libraryDrop?.refresh();
    this.rangeImpact?.refresh();
    this.scheduleDraw();
  }

  setTool(tool) {
    if (!["select", "range", "blade", "remove_between", "move", "slip"].includes(tool)) return false;
    this.cancelGesture();
    this.cancelPendingCut();
    this.snapGuide = null;
    this.clearBladeHover();
    this.clearMediaTrimHover();
    this.clearMediaSlipHover();
    this.clearMediaMoveHover();
    this.tool = tool;
    this.canvas.style.cursor = tool === "select" ? "default" : "crosshair";
    this.scheduleDraw();
    this.onToolStateChange?.();
    return true;
  }

  hasTrackLanes() { return Boolean((this.project?.sources?.B || this.project?.manual?.source_tracks?.A || this.project?.manual?.sequence) && this.getTrackClips); }

  setEditTarget(target, notify = true) {
    const next = this.hasTrackLanes() && ["A", "B"].includes(target) && this.project?.sources?.[target] ? target : "edit";
    if (this.editTarget === next) return;
    this.cancelGesture();
    this.cancelPendingCut();
    this.editTarget = next;
    // A selected moment is still the same moment when changing the edit scope.
    // Keep it ready for an A-only, B-only or Together operation.
    if (!this.project?.manual?.sequence) this.clearSelection(false);
    if (notify) this.onTargetChange?.(next);
    this.scheduleDraw();
  }

  targetClips() {
    return this.editTarget === "edit"
      ? this.project?.manual?.sequence ? sequenceBlocks(this.project, this.getTrackClips) : editableClips(this.project)
      : (this.getTrackClips?.(this.project, this.editTarget) || []);
  }

  canNavigate() {
    return Boolean(this.project && !this.editPending && !this.mediaSelectionPending && !this.gesture && this.canEdit());
  }

  seekNavigation(time) {
    if (!this.canNavigate() || !Number.isFinite(time) || time < 0 || time > timelineDuration(this.project)) return false;
    this.cancelPendingCut();
    this.onSeek?.(time);
    return true;
  }

  navigateEdit(direction) {
    const time = adjacentTimelineEdit(this.targetClips(), this.playhead, timelineDuration(this.project), direction);
    return time != null && this.seekNavigation(time);
  }

  selectIndexEntry(key, requestCurrent = () => true) {
    if (!this.canNavigate()) return false;
    const entry = timelineIndexEntries(this.project, this.getTrackClips).find(item => item.key === key);
    if (!entry) return false;
    if (entry.asset_id && typeof this.onAssetOccurrenceSelect === "function") {
      let issue;
      try { issue = this.assetOccurrenceIssue?.() ?? ""; } catch { issue = null; }
      if (typeof issue !== "string" || issue) return false;
      const projectId = this.project.id, revision = this.project.revision;
      const isCurrent = () => requestCurrent() && this.project?.id === projectId && this.project?.revision === revision
        && timelineIndexEntries(this.project, this.getTrackClips).some(row => row.key === key && row.id === entry.id && row.asset_id === entry.asset_id);
      if (!isCurrent()) return false;
      // The host owns clean-state admission, selection and seek. Never perform
      // the legacy optimistic selection before a guarded asset request settles.
      try {
        const result = this.onAssetOccurrenceSelect({ projectId, revision, assetId: entry.asset_id, clipId: entry.id, isCurrent });
        if (result && typeof result.then === "function") return Promise.resolve(result).then(value => value === true && isCurrent(), () => false);
        return result === true && isCurrent();
      } catch { return false; }
    }
    this.cancelPendingCut();
    if (entry.category === "source") {
      this.selectCaption(null, false);
      this.mediaSelection = null;
      this.setEditTarget(entry.slot);
      this.setSelection(entry, false);
      this.onSelectionChange?.(this.selection, { kind: "clip", target: this.editTarget });
    } else {
      this.clearSelection();
      if (entry.category === "caption") {
        this.selectCaption(entry.id, false);
        this.onCaptionSelect?.(entry.id);
      } else {
        this.selectCaption(null, false);
        this.mediaSelection = entry.id;
        this.onMediaSelect?.(entry.id);
      }
    }
    this.onSeek?.(entry.start);
    if (entry.category === "caption") this.revealCaption(entry.id);
    else if (entry.category === "media") this.revealMedia(entry.id);
    else this.scroll.scrollTop = entry.slot === "edit" ? 0 : Math.max(0, this.trackLane(entry.slot).top - 30);
    this.scheduleDraw();
    return true;
  }

  lockedTargets(target = this.editTarget) {
    return ["A", "B"].filter(slot => this.project?.sources?.[slot]
      && this.project?.manual?.track_locks?.[slot] === true && (target === "edit" || target === slot));
  }

  trackLane(slot) {
    if (this.project?.manual?.sequence) { const top = slot === "B" ? 92 : 36; return { top, bottom: top + 48 }; }
    const compact = Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    const top = (compact ? 104 : 178) + (slot === "B" ? 34 : 0);
    return { top, bottom: top + 30 };
  }

  targetAtEvent(event) {
    if (!this.hasTrackLanes()) return null;
    const y = event.clientY - this.canvas.getBoundingClientRect().top;
    for (const slot of ["A", "B"]) {
      if (!this.project?.sources?.[slot]) continue;
      const lane = this.trackLane(slot);
      if (y >= lane.top && y <= lane.bottom) return slot;
    }
    // Sequence mode has real A/B tracks, not a hidden global EDIT lane.
    // Layout/audio/ruler and empty canvas must retain the user's active track.
    if (this.project?.manual?.sequence) return null;
    const compact = Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    if ((y >= (compact ? 72 : 118) && y <= (compact ? 100 : 170)) || this.inLayoutLane(event)) return "edit";
    return null;
  }

  setSnapping(enabled) {
    this.snapping = Boolean(enabled);
    this.snapGuide = null;
    this.scheduleDraw();
    this.onToolStateChange?.();
  }

  cancelPendingCut() {
    if (this.cutAnchor == null) return false;
    this.cutAnchor = null;
    this.onToolStateChange?.();
    this.scheduleDraw();
    return true;
  }

  cutOutAt(time) {
    const duration = timelineDuration(this.project);
    if (this.tool !== "remove_between" || !this.project?.draft || !this.onEdit || this.editPending || !this.canEdit() || this.lockedTargets().length
      || !Number.isFinite(time) || time < 0 || time > duration) return false;
    if (this.cutAnchor == null) {
      this.clearSelection();
      this.cutAnchor = time;
      this.onToolStateChange?.();
      this.scheduleDraw();
      return true;
    }
    const start = Math.min(this.cutAnchor, time), end = Math.max(this.cutAnchor, time);
    // One undoable range edit, never two independent splits. A click on the
    // same point or entirely removed footage must not create empty history.
    const minimum = this.project?.manual?.sequence ? sequenceFrame(this.project) - 1e-9 : .081;
    const closesGap = this.project?.manual?.sequence && this.editTarget === "edit";
    if (end - start < minimum || (!closesGap && !this.targetClips().some((clip) => clip.start < end && clip.end > start))) return false;
    this.cancelPendingCut();
    this.setSelection({ start, end });
    this.editPending = true;
    this.onToolStateChange?.();
    const finish = () => { this.editPending = false; this.onToolStateChange?.(); this.scheduleDraw(); };
    try {
      const result = this.onEdit({ action: "delete_range", start, end, ...(this.editTarget !== "edit" ? { target: this.editTarget } : {}) });
      // The app reports API errors; keep the selection available for a retry.
      if (result?.then) Promise.resolve(result).then(finish, finish);
      else finish();
    } catch (error) { finish(); throw error; }
    return true;
  }

  // Browser-local position only. No seek, selection, focus or edit dispatch.
  // The host owns saved-clock identity and the explicit Open-intent lifetime.
  editingViewportMeasurement() {
    if (this.sourceReview || !this.project?.id || this.project.__timelineUnavailable
      || !Number.isInteger(this.project.revision) || this.project.revision < 1
      || this.gesture || this.scrubbing || this.selecting || this.libraryDragActive || this.editPending
      || this.mediaSelectionPending || this.mediaSourceOpening || this.trackLockPending || this.zoomFocusPending || this.afterDraw != null
      || typeof this.zoom !== "number" || !Number.isFinite(this.zoom) || this.zoom < 1 || this.zoom > 16
      || this.canvas?.isConnected === false || this.scroll?.isConnected === false
      || this.canvas?.parentElement !== this.scroll) return null;
    try {
      const geometry=this.geometry(), state=timelineLayerTrackState(this.project), layout=this.mediaLayout();
      const viewport=this.scroll.clientWidth, viewportHeight=this.scroll.clientHeight;
      if (!state.valid || ![geometry.duration,geometry.width,geometry.px,viewport,viewportHeight,layout.height]
        .every(value=>typeof value === "number" && Number.isFinite(value) && value > 0)
        || geometry.viewport !== viewport || layout.height > 1000000) return null;
      const ids=new Set();
      if (!Array.isArray(layout.rows) || layout.rows.some(row=>{
        if (![row.top,row.bottom,row.height].every(value=>typeof value === "number" && Number.isFinite(value))
          || row.top < 0 || row.height <= 0 || row.bottom !== row.top+row.height || row.bottom > layout.height) return true;
        if (!state.enabled) return Boolean(row.trackId);
        if (typeof row.trackId !== "string" || ids.has(row.trackId)
          || !state.tracks.some(track=>track.id === row.trackId && track.kind === row.type)) return true;
        ids.add(row.trackId);return false;
      }) || state.enabled && ids.size !== state.tracks.length) return null;
      const canvas=this.canvas.getBoundingClientRect(), scroll=this.scroll.getBoundingClientRect();
      const borderX=this.scroll.clientLeft, borderY=this.scroll.clientTop;
      const nativeLeft=this.scroll.scrollLeft, nativeTop=this.scroll.scrollTop;
      if (![canvas.left,canvas.top,canvas.width,canvas.height,scroll.left,scroll.top,borderX,borderY,nativeLeft,nativeTop]
        .every(value=>typeof value === "number" && Number.isFinite(value))
        || Math.abs(canvas.width-geometry.width) > 1 || Math.abs(canvas.height-layout.height) > 1) return null;
      // Use the actual physical axis, including Chromium's negative RTL scroll.
      // No inherited direction, canvas transform or gesture math is changed.
      const left=scroll.left+borderX-canvas.left, top=scroll.top+borderY-canvas.top;
      const maxLeft=Math.max(0,geometry.width-viewport), maxTop=Math.max(0,layout.height-viewportHeight);
      if (left < -1 || left > maxLeft+1 || top < -1 || top > maxTop+1) return null;
      return {project:this.project,revision:this.project.revision,model:this.project.manual?.layer_tracks,
        zoom:this.zoom,geometry,layout,viewportHeight,nativeLeft,nativeTop,
        left:Math.max(0,Math.min(maxLeft,left)),top:Math.max(0,Math.min(maxTop,top)),
        signature:JSON.stringify([layout.height,layout.rows.map(row=>[row.trackId ?? null,row.type,row.top,row.height])])};
    } catch { return null; }
  }

  captureEditingViewport() {
    const measured=this.editingViewportMeasurement();if (!measured) return null;
    const row=measured.layout.rows.find(row=>row.trackId && measured.top>=row.top && measured.top<row.bottom);
    return {zoom:measured.zoom,leftTime:measured.left/measured.geometry.px,
      vertical:row ? {trackId:row.trackId,offset:measured.top-row.top} : null};
  }

  editingViewportPlan(snapshot) {
    const exact=(value,keys)=>value && typeof value === "object" && !Array.isArray(value)
      && Object.keys(value).sort().join() === [...keys].sort().join();
    if (!exact(snapshot,["zoom","leftTime","vertical"])
      || typeof snapshot.zoom !== "number" || !Number.isFinite(snapshot.zoom) || snapshot.zoom<1 || snapshot.zoom>16
      || typeof snapshot.leftTime !== "number" || !Number.isFinite(snapshot.leftTime) || snapshot.leftTime<0) return null;
    const measured=this.editingViewportMeasurement();if (!measured) return null;
    const width=measured.geometry.viewport*snapshot.zoom, px=width/measured.geometry.duration;
    const maxLeft=Math.max(0,width-measured.geometry.viewport);
    if (snapshot.leftTime>maxLeft/px+1e-8) return null;
    let top=0,vertical=null;
    if (snapshot.vertical!==null) {
      if (!exact(snapshot.vertical,["trackId","offset"]) || typeof snapshot.vertical.trackId !== "string"
        || typeof snapshot.vertical.offset !== "number" || !Number.isFinite(snapshot.vertical.offset) || snapshot.vertical.offset<0) return null;
      const row=measured.layout.rows.find(row=>row.trackId === snapshot.vertical.trackId);
      if (!row || snapshot.vertical.offset>=row.height) return null;
      vertical={trackId:row.trackId,offset:snapshot.vertical.offset};top=row.top+snapshot.vertical.offset;
    }
    return {zoom:snapshot.zoom,leftTime:snapshot.leftTime,vertical,width,px,
      left:Math.max(0,Math.min(maxLeft,snapshot.leftTime*px)),
      top:Math.max(0,Math.min(Math.max(0,measured.layout.height-measured.viewportHeight),top)),measured};
  }

  restoreEditingViewport(snapshot) {
    const plan=this.editingViewportPlan(snapshot);if (!plan) return false;
    const previous=plan.measured;
    const owned=()=>this.project===previous.project && this.project?.revision===previous.revision
      && this.project?.manual?.layer_tracks===previous.model;
    const compatible=measured=>measured && owned() && measured.signature===previous.signature
      && measured.geometry.viewport===previous.geometry.viewport && measured.viewportHeight===previous.viewportHeight;
    const rollback=()=>{
      if (!owned()) return;
      this.zoom=previous.zoom;this.zoomFocusPending=false;
      try {this.draw();
        if (owned()) {this.scroll.scrollLeft=previous.nativeLeft;this.scroll.scrollTop=previous.nativeTop;this.draw();}
      } catch { /* Opening remains usable if the renderer is unavailable. */ }
    };
    try {
      this.zoom=plan.zoom;this.zoomFocusPending=false;this.draw();
      let measured=this.editingViewportMeasurement();
      if (!compatible(measured) || Math.abs(measured.geometry.width-plan.width)>1) {rollback();return false;}
      this.scroll.scrollLeft=measured.nativeLeft+plan.left-measured.left;
      this.scroll.scrollTop=measured.nativeTop+plan.top-measured.top;
      measured=this.editingViewportMeasurement();
      // Native scrolling can quantize subpixels, but must not use the wrong axis.
      if (!compatible(measured) || Math.abs(measured.left-plan.left)>1 || Math.abs(measured.top-plan.top)>1) {rollback();return false;}
      // Paint the final viewport without taking the existing RAF/afterDraw slot.
      this.draw();measured=this.editingViewportMeasurement();
      if (!compatible(measured) || Math.abs(measured.left-plan.left)>1 || Math.abs(measured.top-plan.top)>1) {rollback();return false;}
      return true;
    } catch {rollback();return false;}
  }

  setZoom(value) {
    const oldZoom = this.zoom;
    this.zoom = Math.max(1, Math.min(16, Number(value) || 1));
    if (Math.abs(oldZoom - this.zoom) < .001) return;
    this.afterDraw = null;
    // All zoom controls target the playhead, not the mouse or the
    // viewport's old left edge. Apply after canvas sizing, even if playback
    // or pointer events replace this scheduled frame before it is painted.
    this.zoomFocusPending = true;
    this.scheduleDraw();
  }

  fit() {
    this.zoomFocusPending = false;
    this.afterDraw = null;
    this.zoom = 1;
    this.scroll.scrollLeft = 0;
    this.scheduleDraw();
  }

  zoomToSelection() {
    if (!this.selection || !this.project) return false;
    const duration = timelineDuration(this.project);
    const span = this.selection.end - this.selection.start;
    if (!Number.isFinite(duration) || duration <= 0 || span < selectionMinimum(this.project)) return false;
    this.zoomFocusPending = false;
    this.zoom = Math.max(1, Math.min(16, this.geometry().duration / (span * 1.2)));
    const center = (this.selection.start + this.selection.end) / 2;
    this.scheduleDraw(() => {
      const { px, width, viewport } = this.geometry();
      this.scroll.scrollLeft = Math.max(0, Math.min(width - viewport, center * px - viewport / 2));
    });
    return true;
  }

  setPlayhead(time) {
    this.playhead = Math.max(0, Number(time) || 0);
    if (this.selectionCursor != null && Math.abs(this.playhead - this.selectionCursor) > .0001) {
      this.selectionCursor = null;
      this.selectionAnchor = null;
    }
    this.updateAccessiblePlayhead();
    this.followPlayhead();
    this.scheduleDraw();
  }

  updateAccessiblePlayhead() {
    const precise = this.project?.manual?.sequence || this.sourceReview;
    this.canvas.setAttribute("aria-valuenow", String(precise ? this.playhead : Math.round(this.playhead * 10) / 10));
    this.canvas.setAttribute("aria-valuetext", precise ? `${formatFrameTime(this.playhead, 1 / sequenceFrame(this.project))} at ${Math.round(1 / sequenceFrame(this.project))} FPS` : formatTime(this.playhead, true));
  }

  setSelection(selection, notify = true, asRange = false) {
    this.selectionCursor = null;
    const duration = timelineDuration(this.project);
    const rawStart = Number(selection?.start);
    const rawEnd = Number(selection?.end);
    if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd)) return this.clearSelection(notify);
    const start = Math.max(0, Math.min(duration, Math.min(rawStart, rawEnd)));
    const end = Math.max(start, Math.min(duration, Math.max(rawStart, rawEnd)));
    this.selection = end - start >= selectionMinimum(this.project) ? { start, end } : null;
    this.selectionIsRange = Boolean(asRange && this.selection);
    if (notify) this.onSelectionChange?.(this.selection);
    this.scheduleDraw();
    return this.selection;
  }

  selectRange(start, end) {
    this.selectionAnchor = null;
    // An explicit source-time range replaces a previous layer target. In/Out
    // marking and the Range form must not leave Delete aimed at an old layer.
    this.mediaSelection = null;
    this.selectCaption(null, false);
    return this.setSelection({ start, end }, true, true);
  }

  clearSelection(notify = true) {
    this.selection = null;
    this.selectionAnchor = null;
    this.selectionCursor = null;
    if (notify) this.onSelectionChange?.(null);
    this.scheduleDraw();
  }

  followPlayhead() {
    if (this.gesture || this.scrubbing || this.libraryDragActive || !this.project) return;
    const { px } = this.geometry();
    const x = this.playhead * px;
    const left = this.scroll.scrollLeft;
    const width = this.scroll.clientWidth || 1;
    if (x < left + width * .08) this.scroll.scrollLeft = Math.max(0, x - width * .18);
    else if (x > left + width * .88) this.scroll.scrollLeft = Math.max(0, x - width * .72);
  }

  async loadImages() {
    const project = this.project;
    const urls = project?.sources?.A?.thumbnail_urls || project?.analysis?.thumbnail_urls?.A || [];
    const token = project?.id;
    const generation = ++this.imageLoadGeneration;
    if (urls.length !== this.imageUrls.length || urls.some((url, index) => url !== this.imageUrls[index])) this.images = [];
    this.imageUrls = [...urls];

    // Other lanes need not wait for all source A images to finish loading.
    this.mediaImages ||= new Map();
    const mediaImages = this.mediaImages;
    const extraUrls = [...(project?.sources?.B?.thumbnail_urls || []),
      ...Object.values(project?.assets || {}).map(asset => asset.thumbnail_url).filter(Boolean)];
    for (const url of extraUrls) if (!mediaImages.has(url)) {
      mediaImages.set(url, null);
      const image = new Image();
      image.onload = () => {
        if (this.mediaImages !== mediaImages) return;
        mediaImages.set(url, image);
        this.scheduleDraw();
      };
      image.src = url;
    }

    const images = await Promise.all(urls.map((url) => new Promise((resolve) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => resolve(null);
      image.src = url;
    })));
    // A project can be refreshed without changing its ID. Only the most
    // recent request is allowed to replace its visible filmstrip.
    if (this.imageLoadGeneration === generation && this.project?.id === token) {
      this.images = images;
      this.scheduleDraw();
    }
  }

  baseHeight() {
    if (this.project?.manual?.sequence) return this.project.sources?.B ? 230 : 174;
    return (this.sourceReview || this.scroll.closest?.('.studio-timeline-dock') ? 180 : 310) + (this.hasTrackLanes() ? 68 : 0);
  }

  mediaRows() {
    if (this.sourceReview) return [];
    const state = timelineLayerTrackState(this.project);
    if (state.enabled) {
      const clips = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])]
        .filter(clip => clip && Number.isFinite(clip.start) && Number.isFinite(clip.end) && clip.end > clip.start);
      // Higher tracks composite over lower tracks within their own typed band.
      // Text remains above imported pictures; source A/B and automatic captions
      // keep their explicitly separate semantics. Empty tracks are real rows.
      const ordered = ["text", "visual", "audio"].flatMap(kind => state.tracks.filter(track => track.kind === kind).slice().reverse());
      const rows = ordered.map(track => ({trackId:track.id, group:track.id, type:track.kind,
        label:track.name, locked:track.locked === true, clips:clips.filter(clip => clip.track_id === track.id)}));
      const known = new Set(state.tracks.map(track => track.id));
      // Corrupt/unknown membership stays visible for recovery, but is never a
      // target or silently interpreted as a new legacy auto-packed track.
      for (const clip of clips.filter(clip => !known.has(clip.track_id))) rows.push({trackId:null,
        group:`unassigned-${clip.id}`,type:timelineLayerKind(this.project,clip) || "visual",label:"Unassigned track",clips:[clip]});
      let top = this.baseHeight();
      return rows.map(row => {const height=row.type === "visual" ? 60 : row.type === "audio" ? 56 : 44,
        lane={...row,height,top,bottom:top+height};top=lane.bottom;return lane;});
    }
    const rows = [];
    for (const clip of [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])]) {
      const text = clip.id?.startsWith('text_');
      const asset = this.project.assets?.[clip.asset_id]; if (!asset && !text) continue;
      if (!Number.isFinite(clip.start) || !Number.isFinite(clip.end) || clip.end <= clip.start) continue;
      const group = text ? clip.kind : asset.kind === 'audio' ? (clip.role || 'music') : 'visual';
      let row = rows.find(row => row.group === group && row.clips.every(item => item.end <= clip.start || item.start >= clip.end));
      if (!row) { row = {group,type:text ? 'text' : asset.kind === 'audio' ? 'audio' : 'visual',clips:[]}; rows.push(row); }
      row.clips.push(clip);
    }
    let top = this.baseHeight();
    return rows.map(row => {
      const height = row.type === 'visual' ? 60 : row.type === 'audio' ? 56 : 44;
      const kinds = row.type === 'visual' ? new Set(row.clips.map(clip => this.project.assets[clip.asset_id].kind)) : null;
      const label = row.type === 'visual' ? kinds.size === 1 ? [...kinds][0].toUpperCase() : 'VIDEO / IMAGE'
        : ({music:'MUSIC',voice:'VOICEOVER',effects:'EFFECTS',title:'TEXT',caption:'CAPTIONS'}[row.group] || 'TEXT');
      const lane = {...row,label,height,top,bottom:top+height};
      top = lane.bottom;
      return lane;
    });
  }

  mediaLayout() {
    const rows = this.mediaRows();
    const top = rows.at(-1)?.bottom ?? this.baseHeight();
    const items = this.captionItems();
    const enabled = (this.project?.settings?.burn_captions !== false || this.project?.settings?.captions)
      && (items ? items.length : this.project?.analysis?.transcript?.segments?.length);
    // Overlapping captions (a lengthened one, or speech used twice) stack in rows.
    const lines = items ? Math.max(1, ...this.captionPlacement(items).map(entry => entry.row + 1)) : 1;
    const height = 4 + lines * CAPTION_ROW_HEIGHT;
    const caption = enabled ? {top,bottom:top+height,height,label:'CAPTIONS'} : null;
    return {rows,caption,height:caption?.bottom ?? top};
  }

  // Automatic captions from the server: the same items the export burns.
  captionItems() {
    // Source review shows the original recording; edit-clock items do not apply there.
    const items = this.sourceReview ? null : this.project?.editor_captions;
    return Array.isArray(items) ? items : null;
  }

  captionPlacement(items) {
    if (this.captionPlacementCache?.items === items) return this.captionPlacementCache.placement;
    const ends = [];
    const placement = items.map(item => {
      let row = ends.findIndex(end => end <= Number(item.start) + 1e-6);
      if (row < 0) { row = ends.length; ends.push(0); }
      ends[row] = Number(item.end);
      return {item,row};
    });
    this.captionPlacementCache = {items,placement};
    return placement;
  }

  captionAtEvent(event) {
    const items = this.captionItems(), layout = items && this.mediaLayout();
    if (!layout?.caption) return null;
    const y = event.clientY-this.canvas.getBoundingClientRect().top, time=this.timeFromEvent(event), {px}=this.geometry();
    if (y < layout.caption.top || y >= layout.caption.bottom) return null;
    const row = Math.floor((y-layout.caption.top-2)/CAPTION_ROW_HEIGHT);
    const tolerance = 4/Math.max(px,.0001);
    const hit = this.captionPlacement(items).filter(entry => entry.row === row
      && time >= entry.item.start-tolerance && time < entry.item.end+tolerance)
      .sort((a,b) => (a.item.id === this.captionSelection ? -1 : 0) - (b.item.id === this.captionSelection ? -1 : 0))[0];
    if (!hit) return null;
    const {item} = hit, wide = (item.end-item.start)*px >= 18;
    const edge = wide ? (Math.abs(time-item.start)*px < 7 ? 'start' : Math.abs(time-item.end)*px < 7 ? 'end' : null) : null;
    return {item,edge};
  }

  selectCaption(id, notify = false) {
    const next = id || null;
    if (next) this.mediaSelection = null;
    if (this.captionSelection === next) return;
    this.captionSelection = next;
    if (notify) this.onCaptionSelect?.(next);
    this.scheduleDraw();
  }

  revealCaption(id) {
    const item = this.captionItems()?.find(entry => entry.id === id), layout = this.mediaLayout();
    if (!item || !layout.caption) return;
    const {px} = this.geometry(), left = item.start*px, right = item.end*px;
    if (left < this.scroll.scrollLeft || right > this.scroll.scrollLeft + this.scroll.clientWidth)
      this.scroll.scrollLeft = Math.max(0, left - this.scroll.clientWidth/3);
    if (layout.caption.bottom > this.scroll.scrollTop + this.scroll.clientHeight)
      this.scroll.scrollTop = Math.max(0, layout.caption.bottom - this.scroll.clientHeight + 8);
  }

  nativeMediaSource() { return typeof this.mediaSourceIssue === "function" && typeof this.onMediaSourceOpen === "function"; }

  mediaSourceReadiness(clipId, time) {
    if (this.mediaSourceOpening) return "Wait for the source preview to open.";
    if (this.editPending || this.gesture || !this.canEdit()) return "Wait for the current edit to finish.";
    const clip = this.project?.manual?.media_clips?.find(item => item?.id === clipId);
    if (this.sourceReview || !clip || this.project?.assets?.[clip.asset_id]?.kind !== "video")
      return "Choose an imported video in the edited timeline.";
    if (!Number.isFinite(time) || time < clip.start || time >= clip.end) return "Choose a point inside this video occurrence.";
    if (!this.nativeMediaSource()) return "Source preview is unavailable in this editor.";
    try {
      const issue = this.mediaSourceIssue(clipId, time);
      return typeof issue === "string" ? issue : "Source readiness could not be confirmed. Try again after the edit refreshes.";
    } catch { return "Source readiness could not be confirmed. Try again after the edit refreshes."; }
  }

  async openMediaSourceAt(clipId, time) {
    const issue = this.mediaSourceReadiness(clipId, time);
    if (issue) { this.canvas.title = issue; return false; }
    const request = {projectId: this.project.id, clipId, tool: this.tool};
    this.mediaSourceOpening = request;
    const current = () => this.project?.id === request.projectId && this.mediaSelection === clipId && this.tool === request.tool;
    this.canvas.title = "Opening original source...";
    try {
      // Read-only host navigation owns selection, edited seek and source-clock
      // mapping. Do not set editPending: it would block the host's own guard.
      const opened = await this.onMediaSourceOpen(clipId, time);
      if (opened !== true && current()) this.canvas.title = "Source preview did not open. Check the selected clip and try again.";
      return opened === true;
    } catch (error) {
      if (current()) this.canvas.title = error?.message || "Source preview could not open.";
      return false;
    } finally {
      if (this.mediaSourceOpening === request) this.mediaSourceOpening = null;
    }
  }

  doubleClick(event) {
    if (this.onMediaSelectionChange && (event.ctrlKey || event.metaKey || this.mediaSelectionPending || this.selectedMediaIds().length>1)) return;
    if (this.tool === "slip") return; // Preserve Slip's existing no-view-change behavior.
    const caption = this.captionAtEvent(event);
    if (caption) { this.onCaptionOpen?.(caption.item.id); return; }
    if (["select", "move"].includes(this.tool) && !event.altKey && !event.ctrlKey && !event.metaKey && !event.shiftKey
      && !this.sourceReview && this.nativeMediaSource()) {
      const media = this.mediaAtEvent(event);
      if (media && this.project?.assets?.[media.clip.asset_id]?.kind === "video") {
        event.preventDefault(); event.stopPropagation?.();
        void this.openMediaSourceAt(media.clip.id, this.timeFromEvent(event));
        return; // A blocked source match is never silently replaced by Fit.
      }
    }
    if (!["blade", "remove_between"].includes(this.tool)) this.fit();
  }

  mediaRowAtEvent(event) {
    const y = event.clientY-this.canvas.getBoundingClientRect().top;
    return this.mediaRows().find(row => y >= row.top && y < row.bottom) || null;
  }

  mediaAtEvent(event) {
    const time=this.timeFromEvent(event), row=this.mediaRowAtEvent(event);
    const clip = row?.clips.find(clip=>time>=clip.start && time<clip.end);
    return clip ? {clip,row} : null;
  }

  revealMedia(id) {
    const row = this.mediaRows().find(row => row.clips.some(clip => clip.id === id));
    if (!row) return;
    if (row.top < this.scroll.scrollTop) this.scroll.scrollTop = row.top;
    else if (row.bottom > this.scroll.scrollTop + this.scroll.clientHeight)
      this.scroll.scrollTop = Math.max(0, row.bottom - this.scroll.clientHeight + 8);
  }

  drawMedia(ctx, px, width, layout = this.mediaLayout()) {
    const left = this.scroll.scrollLeft || 0, right=left+this.scroll.clientWidth,
      selectedIds = new Set(this.selectedMediaIds()), groupSelected = selectedIds.size>1;
    for (const row of layout.rows) {
      ctx.fillStyle=this.color("lane", '#102027'); ctx.fillRect(0,row.top,width,row.height-4);
      for (const saved of row.clips) {
        const groupPatch=this.gesture?.kind==="media_group" && !this.gesture.relocating ? this.gesture.patches?.find(patch=>patch.clip_id===saved.id) : null;
        const clip=groupPatch ? {...saved,...groupPatch} : this.gesture?.media?.id === saved.id && !this.gesture.nativeTrack ? {...saved,...this.gesture.patch} : saved;
        const selected=selectedIds.has(saved.id);
        const asset=clip.id?.startsWith('text_') ? {kind:'text',name:clip.text} : this.project.assets[clip.asset_id] || {kind:row.type==='audio'?'audio':'video',name:'Unavailable media'}, x=clip.start*px, w=(clip.end-clip.start)*px;
        if (x+w<left || x>right) continue;
        const disabled = clip.enabled === false;
        ctx.fillStyle=disabled ? this.color("lane-alt", "#252b30") : asset.kind==='text' ? (clip.kind==='caption' ? this.color("caption", '#6b5722') : this.color("clip-b", '#4a3fa0')) : asset.kind==='audio' ? (clip.role==='voice' ? this.color("clip-b", '#563c93') : clip.role==='music' ? this.color("clip", '#25458c') : this.color("keep", '#245a4b')) : this.color("clip", '#245553'); ctx.fillRect(x,row.top+1,w,row.height-6);
        const image=this.mediaImages?.get(asset.thumbnail_url);
        ctx.save(); ctx.beginPath(); ctx.rect(x+1,row.top+2,Math.max(0,w-2),row.height-8); ctx.clip();
        if(image) {
          const imageHeight=row.height-8,imageWidth=imageHeight*(Number(image.width)||60)/Math.max(1,Number(image.height)||38);
          ctx.globalAlpha=disabled ? .28 : .7;
          for(let ix=Math.max(x,left); ix<x+w && ix<right;ix+=imageWidth+2) ctx.drawImage(image,ix,row.top+2,imageWidth,imageHeight);
          ctx.globalAlpha=1;
        }
        const waveform=asset.waveform || [];
        if(waveform.length && asset.kind==='audio') {
          ctx.globalAlpha=disabled ? .35 : 1;
          const waveTop=row.top+18,waveBottom=row.bottom-7,mid=(waveTop+waveBottom)/2,maxAmp=(waveBottom-waveTop)/2;
          ctx.strokeStyle=this.color("media-wave", '#86dcc0'); ctx.beginPath();
          for(let ix=Math.max(x,left);ix<Math.min(x+w,right);ix+=3) {
            const source=Number(clip.source_start||0)+(ix/px-clip.start);
            const sourceEnd=Number(clip.source_start||0)+(Math.min(ix+3,x+w,right)/px-clip.start);
            const binDuration=Math.max(.001,Number(asset.duration)||0)/waveform.length;
            const first=Math.max(0,Math.floor(source/binDuration)),last=Math.min(waveform.length-1,Math.ceil(sourceEnd/binDuration)-1);
            // Keep the strongest real sample covered by this pixel bucket;
            // point sampling can hide short transients at Fit/low zoom.
            let value=0;
            for(let bin=first;bin<=last;bin++) value=Math.max(value,Math.abs(Number(waveform[bin])||0));
            const amp=Math.min(maxAmp,value*maxAmp); ctx.moveTo(ix,mid-amp); ctx.lineTo(ix,mid+amp);
          } ctx.stroke();
          ctx.globalAlpha=1;
        }
        ctx.fillStyle='rgba(0,0,0,.75)'; ctx.fillRect(Math.max(x,left),row.top+2,Math.min(w,300),14);
        ctx.fillStyle=this.color("label", '#f0edf5'); ctx.font=this.font(10);
        const nameX=Math.max(x+5,left+(this.headersActive ? 6 : ctx.measureText(row.label).width+22));
        ctx.fillText(`${disabled ? 'Disabled · ' : ''}${asset.kind==='text' ? clip.kind==='title' ? 'Text' : 'Caption' : asset.kind==='audio' ? clip.role || 'music' : asset.kind} · ${asset.name}${Number.isFinite(clip.speed)&&clip.speed!==1 ? ` · ${clip.speed}×` : ''}`,nameX,row.top+12);
        ctx.strokeStyle=this.color("selected", '#d4c84f');ctx.beginPath();
        if(clip.fade_in>0){ctx.moveTo(x,row.bottom-6);ctx.lineTo(x+clip.fade_in*px,row.top+18);}
        if(clip.fade_out>0){ctx.moveTo(x+w-clip.fade_out*px,row.top+18);ctx.lineTo(x+w,row.bottom-6);}ctx.stroke();
        ctx.restore();
        ctx.save(); ctx.setLineDash(disabled && !selected ? [4,3] : []);
        ctx.strokeStyle=selected ? this.color("selected", '#ffe174'):this.color("clip-edge", '#b8a4d1'); ctx.lineWidth=selected ? 2:1; ctx.strokeRect(x+.5,row.top+1.5,Math.max(0,w-1),row.height-7);
        ctx.restore();
        if(selected && !groupSelected){ctx.fillStyle=this.color("selected", '#fff');ctx.fillRect(x,row.top+18,3,row.height-26);ctx.fillRect(x+w-3,row.top+18,3,row.height-26);}
      }
    }
    const drag = this.gesture;
    const ghosts = drag?.kind === "media" && drag.nativeTrack && drag.dragged && !drag.moveIssue && Number.isFinite(drag.patch?.start)
      ? [drag.patch] : drag?.kind==="media_group" && drag.relocating && drag.dragged && !drag.moveIssue ? drag.patches || [] : [];
    for (const patch of ghosts) {
      const row=layout.rows.find(row=>row.trackId===patch.track_id);
      if (!row) continue; // Never invent a row for an incomplete destination.
      const x=patch.start*px,w=(patch.end-patch.start)*px;
      if (x+w<left || x>right) continue;
      ctx.save();ctx.fillStyle=this.color("selection-fill", "rgba(176,153,255,.16)");ctx.fillRect(x,row.top+1,w,row.height-6);
      ctx.strokeStyle=this.color("selected", "#ffe174");ctx.lineWidth=2;ctx.setLineDash([6,3]);ctx.strokeRect(x+.5,row.top+1.5,Math.max(0,w-1),row.height-7);
      ctx.setLineDash([]);ctx.fillStyle=this.color("label", "#f0edf5");ctx.font=this.font(11);
      const label=fitCanvasLabel(ctx,`Move to ${row.label}`,Math.min(w-10,right-Math.max(x,left)-8));
      if(label)ctx.fillText(label,Math.max(x+5,left+5),row.top+17);ctx.restore();
    }
    if(layout.caption && this.captionItems()) this.drawCaptionItems(ctx,px,width,layout.caption,left,right);
    else if(layout.caption) {
      const {top,height}=layout.caption;
      ctx.fillStyle=this.color("lane", '#141d24');ctx.fillRect(0,top,width,height-2);
      for(const caption of this.audioTimelineRanges(this.project.analysis.transcript.segments)) {
        const x=caption.start*px,w=(caption.end-caption.start)*px;
        if(x+w<left || x>right)continue;
        ctx.fillStyle=this.color("caption", '#6b5722');ctx.fillRect(x+1,top+1,Math.max(1,w-2),height-4);ctx.strokeStyle=this.color("caption-edge", '#c9a94a');ctx.strokeRect(x+1.5,top+1.5,Math.max(0,w-3),height-5);
        // The lane header already says Captions: give the block's width to the words.
        const textX=Math.max(x+5,left+this.labelInset(70));
        ctx.font=this.font(11);
        const label=fitCanvasLabel(ctx,caption.text,x+w-5-textX);
        if(label){ctx.save();ctx.beginPath();ctx.rect(x+2,top,Math.max(0,w-4),height-2);ctx.clip();ctx.fillStyle=this.color("label", '#f6eed6');ctx.fillText(label,textX,top+17);ctx.restore();}
      }
    }
  }

  drawCaptionItems(ctx, px, width, lane, left, right) {
    ctx.fillStyle=this.color("lane", '#141d24');ctx.fillRect(0,lane.top,width,lane.height-2);
    for (const {item:saved,row} of this.captionPlacement(this.captionItems())) {
      const item = this.gesture?.kind==='caption' && this.gesture.caption.id===saved.id ? {...saved,...this.gesture.patch} : saved;
      const x=item.start*px, w=Math.max(2,(item.end-item.start)*px), top=lane.top+2+row*CAPTION_ROW_HEIGHT, height=CAPTION_ROW_HEIGHT-2;
      if (x+w<left || x>right) continue;
      const selected = this.captionSelection === item.id, edited = item.corrected || item.local_text || item.timing_changed || item.style || item.position || item.scale;
      ctx.save();
      if (item.hidden) { ctx.fillStyle=this.color("lane-alt", '#252b30'); ctx.setLineDash([4,3]); ctx.strokeStyle=this.color("grid", '#7d878c'); }
      else { ctx.fillStyle=edited ? this.color("caption-edited", '#5d5a24') : this.color("caption", '#6b5722'); ctx.strokeStyle=this.color("caption-edge", '#c9a94a'); }
      ctx.fillRect(x+1,top,Math.max(1,w-2),height);
      ctx.lineWidth=selected ? 2 : 1; if (selected) { ctx.setLineDash([]); ctx.strokeStyle=this.color("selected", '#ffe174'); }
      ctx.strokeRect(x+1.5,top+.5,Math.max(0,w-3),height-1);
      ctx.setLineDash([]);
      if (selected && w >= 18) { ctx.fillStyle=this.color("selected", '#fff'); ctx.fillRect(x+1,top+4,3,height-8); ctx.fillRect(x+w-4,top+4,3,height-8); }
      // The lane header already says Captions: give the block's width to the words.
      ctx.font=this.font(11);
      const textX=Math.max(x+6,left+this.labelInset(70)), label=fitCanvasLabel(ctx,`${item.hidden ? 'Hidden · ' : edited ? '✎ ' : ''}${item.text}`,x+w-6-textX);
      if (label) {
        ctx.beginPath(); ctx.rect(x+2,top,Math.max(0,w-4),height); ctx.clip();
        ctx.direction=item.direction==='rtl' ? 'rtl' : 'ltr'; ctx.textAlign='left';
        ctx.fillStyle=item.hidden ? this.color("text", '#9aa4a9') : this.color("label", '#f6eed6'); ctx.fillText(label,textX,top+height/2+4);
      }
      ctx.restore();
    }
  }

  labelInset(width) { return this.headersActive ? 8 : width; }

  // Studio track headers: an HTML column beside the scrolling canvas, aligned to
  // the lane geometry drawn below. Lock and mute proxy the existing Edit and
  // mixer controls, so each setting keeps one source of truth.
  trackHeaderColumn() {
    if (this.headerColumn !== undefined) return this.headerColumn;
    this.headerColumn = null;
    const element = typeof Element !== "undefined" && this.scroll instanceof Element ? this.scroll : null;
    if (!element || this.sourceReview || !element.closest(".studio-timeline-dock") || !element.parentNode) return null;
    const body = document.createElement("div"), column = document.createElement("div"), rows = document.createElement("div");
    body.className = "timeline-body"; column.className = "timeline-track-headers"; rows.className = "timeline-track-rows";
    column.setAttribute("role", "group"); column.setAttribute("aria-label", "Tracks");
    column.append(rows); element.parentNode.insertBefore(body, element); body.append(column, element);
    element.addEventListener("scroll", () => { rows.style.transform = `translateY(${-element.scrollTop}px)`; }, { passive: true });
    column.addEventListener("click", (event) => {
      const lockButton = event.target.closest?.("button[data-layer-track-lock]");
      if (lockButton) { if (!lockButton.disabled) this.toggleLayerTrackLock(lockButton.dataset.layerTrackLock); return; }
      const trackButton = event.target.closest?.("button[data-manage-track]");
      if (trackButton) { if(!trackButton.disabled)this.onTrackManage?.(trackButton.dataset.manageTrack); return; }
      const button = event.target.closest?.("button[data-proxy]");
      const target = button && document.querySelector(button.dataset.proxy);
      if (target && !target.disabled) { target.click(); this.scheduleDraw(); }
    });
    this.headerColumn = { rows, items: new Map() };
    return this.headerColumn;
  }

  laneGuide(layout, state = timelineLayerTrackState(this.project)) {
    const lanes = [], sequence = Boolean(this.project?.manual?.sequence), twoSources = Boolean(this.project?.sources?.B);
    const video = (slot) => {
      if (!this.project?.sources?.[slot]) return;
      const { top, bottom } = this.trackLane(slot);
      lanes.push({ key: `video-${slot}`, label: `Video ${slot}`, top, height: bottom - top, lock: slot, active: this.editTarget === slot || (sequence && this.editTarget === "edit") });
    };
    if (sequence) {
      video("A"); video("B");
      lanes.push({ key: "layout", label: "Layout", top: twoSources ? 152 : 96, height: 22 });
      lanes.push({ key: "audio", label: "Original", top: twoSources ? 186 : 130, height: 26, mute: "source" });
    } else {
      const shift = this.hasTrackLanes() ? 68 : 0;
      lanes.push({ key: "edit", label: "Edit", top: 72, height: 28, active: this.editTarget === "edit" });
      if (this.hasTrackLanes()) { video("A"); video("B"); }
      lanes.push({ key: "layout", label: "Layout", top: 104 + shift, height: 26 });
      lanes.push({ key: "audio", label: "Original", top: 134 + shift, height: 38, mute: "source" });
    }
    const names = { music: "Music", voice: "Voiceover", effects: "Effects", title: "Text", caption: "Captions" };
    layout.rows.forEach((row, index) => lanes.push({
      key: row.trackId ? `layer-${row.trackId}` : `row-${index}-${row.group}`, label: state.enabled ? row.label
        : row.type === "visual" ? (row.label === "IMAGE" ? "Images" : "Overlay") : names[row.group] || "Text",
      trackId:row.trackId || null, locked:row.locked === true, top: row.top, height: row.height - 4,
      mute: !state.enabled && row.type === "audio" && names[row.group] && row.group !== "title" && row.group !== "caption" ? row.group : null,
    }));
    if (layout.caption) lanes.push({ key: "captions", label: "Captions", top: layout.caption.top, height: layout.caption.height - 2 });
    return lanes;
  }

  // One synchronous paint only. Never retain readiness across a frame or use
  // this result for an action: the click path revalidates independently below.
  layerTrackHeaderPass() {
    const project = this.project, state = timelineLayerTrackState(project);
    const canNavigate = this.canNavigate();
    if (this.trackHeaderReadiness === undefined) return {state, canNavigate, lockIssue:null};
    const canEdit = this.canEdit(), tracks = new Map(state.tracks.map(track => [track.id, track]));
    let host = null;
    try {
      const value = typeof this.trackHeaderReadiness === "function" ? this.trackHeaderReadiness(project) : null;
      if (value && typeof value === "object" && !Array.isArray(value) && typeof value.then !== "function"
        && Object.keys(value).length === 3 && ["project", "lockIssue", "unlockIssue"].every(key => Object.hasOwn(value, key))
        && value.project === project && this.project === project
        && typeof value.lockIssue === "string" && typeof value.unlockIssue === "string") host = value;
    } catch { /* A present malformed batch must not fall back to permissive readiness. */ }
    const localBusy = this.sourceReview || this.trackLockPending || this.editPending || this.gesture
      || this.scrubbing || this.libraryDragActive || this.mediaSelectionPending || this.mediaSourceOpening;
    const supported = typeof this.onMediaAction === "function" && typeof this.trackLockIssue === "function";
    const lockIssue = (trackId, locked) => {
      const track = tracks.get(trackId);
      if (!state.valid || !state.enabled || !track) return "Track protection is unavailable. Reload a compatible edit.";
      const unlocking = track.locked === true && locked === false;
      if (localBusy || (!unlocking && !canEdit)) return "Finish the current action before changing track protection.";
      if (typeof locked !== "boolean" || !supported) return "Track protection is unavailable in this editor.";
      if (!host) return "Track protection readiness could not be confirmed.";
      return unlocking ? host.unlockIssue : host.lockIssue;
    };
    return {state, canNavigate, lockIssue};
  }

  syncTrackHeaders(layout, height) {
    const headers = this.trackHeaderColumn();
    if (!headers) return false;
    const seen = new Set(), pass = this.layerTrackHeaderPass();
    headers.rows.style.height = `${height}px`;
    for (const lane of this.laneGuide(layout, pass.state)) {
      seen.add(lane.key);
      let item = headers.items.get(lane.key);
      if (!item) {
        item = document.createElement("div"); item.className = "track-header";
        const name = document.createElement("span"), actions = document.createElement("span");
        name.className = "track-name"; actions.className = "track-actions";
        item.append(name, actions); headers.rows.append(item); headers.items.set(lane.key, item);
      }
      item.style.top = `${lane.top}px`; item.style.height = `${lane.height}px`;
      item.classList.toggle("active", Boolean(lane.active));
      item.dataset.lane = lane.key.replace(/-.*$/, "");
      item.dataset.trackLocked = String(lane.locked === true);
      const managed = Boolean(lane.trackId && typeof this.onTrackManage === "function");
      if (managed && item.firstChild.tagName !== "BUTTON") { const button=document.createElement("button");button.type="button";button.className="track-name track-manage";item.replaceChild(button,item.firstChild); }
      else if (!managed && item.firstChild.tagName === "BUTTON") { const name=document.createElement("span");name.className="track-name";item.replaceChild(name,item.firstChild); }
      if (item.firstChild.textContent !== lane.label) item.firstChild.textContent = lane.label;
      if(managed){item.firstChild.dataset.manageTrack=lane.trackId;item.firstChild.setAttribute("aria-label",`Manage track ${lane.label}`);
        item.firstChild.title=`${lane.label}${lane.locked ? " (locked)" : ""} - Manage this persistent track`;item.firstChild.disabled=!pass.canNavigate;}
      if (lane.trackId) this.syncLayerLockButton(item.lastChild, lane, pass.lockIssue?.(lane.trackId, lane.locked !== true));
      else this.syncHeaderButton(item.lastChild, "lock", lane.lock ? `#trackLock${lane.lock}` : null, lane.label);
      this.syncHeaderButton(item.lastChild, "mute", lane.mute ? `[data-mute="${lane.mute}"]` : null, lane.label);
    }
    for (const [key, item] of headers.items) if (!seen.has(key)) { item.remove(); headers.items.delete(key); }
    return true;
  }

  layerTrackLockReadiness(trackId, locked) {
    const state = timelineLayerTrackState(this.project);
    const track = state.tracks.find(row => row.id === trackId);
    if (!state.valid || !state.enabled || !track) return "Track protection is unavailable. Reload a compatible edit.";
    // A current Unlock can recover a retained local draft without applying it.
    // Only the authoritative host callback may admit this exceptional path.
    const unlocking = track.locked === true && locked === false;
    if (this.sourceReview || this.trackLockPending || this.editPending || this.gesture || this.scrubbing || this.libraryDragActive || this.mediaSelectionPending || this.mediaSourceOpening || (!unlocking && !this.canEdit())) return "Finish the current action before changing track protection.";
    if (typeof locked !== "boolean" || typeof this.onMediaAction !== "function" || typeof this.trackLockIssue !== "function") return "Track protection is unavailable in this editor.";
    try { const issue = this.trackLockIssue(trackId, locked); return typeof issue === "string" ? issue : "Track protection readiness could not be confirmed."; }
    catch { return "Track protection readiness could not be confirmed."; }
  }

  toggleLayerTrackLock(trackId) {
    const track = timelineLayerTrackState(this.project).tracks.find(row => row.id === trackId), locked = track?.locked !== true;
    const issue = this.layerTrackLockReadiness(trackId, locked);
    if (issue) { this.canvas.title = issue; return false; }
    const request = {projectId:this.project?.id, project:this.project, trackId, locked};
    const doc = this.canvas.ownerDocument, active = doc?.activeElement;
    const origin = active?.dataset?.layerTrackLock === trackId ? active : null;
    let focusOwned = Boolean(origin);
    const noticeFocus = event => {
      if (event.type === "focusin" ? event.target !== origin && event.target !== doc.body
        : event.type === "keydown" ? ![" ", "Enter"].includes(event.key) : true) focusOwned = false;
    };
    if (origin) for (const type of ["focusin", "pointerdown", "keydown"]) doc.addEventListener?.(type, noticeFocus, true);
    const releaseFocus = allowed => {
      if (origin) for (const type of ["focusin", "pointerdown", "keydown"]) doc.removeEventListener?.(type, noticeFocus, true);
      if (allowed && focusOwned && this.project?.id === request.projectId && !this.trackLockPending
        && doc.activeElement === doc.body && origin.isConnected && !origin.disabled && origin.getClientRects?.().length)
        origin.focus?.({preventScroll:true});
    };
    this.trackLockPending = request; this.onToolStateChange?.(); this.scheduleDraw();
    const finish = (result, error) => {
      if (this.trackLockPending !== request) { releaseFocus(false); return; }
      this.trackLockPending = null;
      if (this.project?.id === request.projectId) {
        const saved = timelineLayerTrackState(this.project).tracks.find(row => row.id === trackId);
        const accepted = !error && result?.id === request.projectId && Number.isInteger(result.revision) && result.revision === this.project?.revision
          && timelineLayerTrackState(result).tracks.some(track => track.id === trackId && track.locked === locked) && saved?.locked === locked;
        if (accepted) this.canvas.title = `Track ${locked ? "locked" : "unlocked"}. Protection is kept outside Undo.`;
        else if (this.project === request.project) this.canvas.title = error?.message || "Track protection was not changed. Review the current edit and try again.";
      }
      this.onToolStateChange?.(); this.scheduleDraw();
      // Do not share the replaceable post-draw slot: navigation may clear it.
      // This independent callback always releases the document listeners.
      requestAnimationFrame(() => releaseFocus(true));
    };
    try { Promise.resolve(this.onMediaAction("layer_track_lock", {track_id:trackId, locked})).then(result => finish(result), error => finish(null, error)); }
    catch (error) { finish(null, error); return false; }
    return true;
  }

  syncLayerLockButton(container, lane, paintedIssue = undefined) {
    let button = container.querySelector('[data-kind="lock"]');
    if (typeof this.trackLockIssue !== "function" || typeof this.onMediaAction !== "function") { button?.remove(); return; }
    if (!button) { button = document.createElement("button"); button.type = "button"; button.dataset.kind = "lock"; container.append(button); }
    delete button.dataset.proxy; button.dataset.layerTrackLock = lane.trackId;
    const locked = lane.locked === true, name = `${locked ? "Unlock" : "Lock"} track ${lane.label}`;
    const issue = paintedIssue === undefined ? this.layerTrackLockReadiness(lane.trackId, !locked) : paintedIssue;
    button.setAttribute("aria-pressed", String(locked)); button.setAttribute("aria-label", name);
    button.title = issue || `${name}. Protects saved clips and track order, not global output or mix settings. Kept outside Undo.`;
    button.disabled = Boolean(issue);
  }

  mediaProtectionIssue(clipId) {
    const state = timelineLayerTrackState(this.project);
    if (!state.enabled) return "";
    if (!state.valid) return "Unsupported track protection. Reload a compatible edit before changing clips.";
    const clip = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])].find(row => row?.id === clipId);
    const track = state.tracks.find(row => row.id === clip?.track_id);
    return track?.locked === true ? `Track "${track.name}" is locked. Unlock it before changing its clips.` : "";
  }

  cancelProtectedGesture() {
    const g = this.gesture, ids = g?.kind === "media_group" ? g.ids : g?.media?.id ? [g.media.id] : g?.kind === "media_blade" ? [g.clipId] : [];
    const issue = ids.map(id => this.mediaProtectionIssue(id)).find(Boolean);
    if (!issue) return false;
    this.cancelGesture(); this.canvas.title = issue; this.canvas.style.cursor = "not-allowed"; return true;
  }

  syncHeaderButton(container, kind, selector, label) {
    let button = container.querySelector(`[data-kind="${kind}"]`);
    const target = selector ? document.querySelector(selector) : null;
    if (!target || target.hidden) { button?.remove(); return; }
    if (!button) { button = document.createElement("button"); button.type = "button"; button.dataset.kind = kind; container.append(button); }
    const pressed = target.getAttribute("aria-pressed") === "true";
    const name = `${kind === "lock" ? (pressed ? "Unlock" : "Lock") : (pressed ? "Unmute" : "Mute")} ${label}`;
    button.dataset.proxy = selector;
    button.setAttribute("aria-pressed", String(pressed));
    button.disabled = Boolean(target.disabled);
    if (button.getAttribute("aria-label") !== name) { button.setAttribute("aria-label", name); button.title = name; }
  }

  geometry() {
    const length = timelineDuration(this.project) || 1;
    // A small, clearly bounded tail remains available for deliberate extension,
    // without making a short edit look several seconds longer than it is.
    const duration = this.project?.manual?.sequence ? length + Math.max(1, Math.min(8, length * .08)) : length;
    const viewport = Math.max(1, this.scroll.clientWidth || 520);
    const width = Math.max(viewport, viewport * this.zoom);
    return { duration, viewport, width, px: width / Math.max(duration, .001) };
  }

  scheduleDraw(after = null) {
    // Preserve the latest explicit post-draw focus while coalescing playhead,
    // pointer, resize, and image updates into the already scheduled frame.
    if (after) this.afterDraw = after;
    if (this.raf !== null) return;
    this.raf = requestAnimationFrame(() => {
      this.raf = null;
      this.draw();
      const after = this.afterDraw;
      this.afterDraw = null;
      after?.();
    });
  }

  draw() {
    this.cancelProtectedGesture();
    this.navigation?.sync?.();
    this.reviewMarkers?.sync();
    this.rangeImpact?.sync();
    const ctx = this.context;
    const { duration, width, px, viewport } = this.geometry();
    this.compact = this.sourceReview || Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    const sequence = Boolean(this.project?.manual?.sequence);
    const extra = !sequence && this.hasTrackLanes() ? 68 : 0;
    const mediaLayout = this.mediaLayout(), cssHeight = mediaLayout.height;
    this.headersActive = this.syncTrackHeaders(mediaLayout, cssHeight);
    const dpr = Math.min(1.5, window.devicePixelRatio || 1, Math.sqrt(16000000/Math.max(1,width*cssHeight)));
    this.canvas.style.width = `${width}px`;
    this.canvas.style.height = `${cssHeight}px`;
    const targetWidth = Math.max(1, Math.floor(width * dpr));
    const targetHeight = Math.floor(cssHeight * dpr);
    if (this.canvas.width !== targetWidth) this.canvas.width = targetWidth;
    if (this.canvas.height !== targetHeight) this.canvas.height = targetHeight;
    if (this.zoomFocusPending) {
      const time = Math.max(0, Math.min(timelineDuration(this.project), this.playhead));
      this.scroll.scrollLeft = Math.max(0, Math.min(width - viewport, time * px - viewport / 2));
      this.zoomFocusPending = false;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, cssHeight);
    ctx.fillStyle = this.color("bg", "#10181e");
    ctx.fillRect(0, 0, width, cssHeight);

    this.drawRuler(ctx, duration, width, px);
    if (!sequence) this.drawFilmstrip(ctx, width);
    this.drawLaneBackgrounds(ctx, width);
    if (!sequence) this.drawRanges(ctx, px);
    this.drawTracks(ctx, px);
    if (sequence) this.drawGaps(ctx, px);
    ctx.save(); ctx.translate(0, extra);
    this.drawAudioEvidence(ctx, px);
    this.drawLayouts(ctx, px);
    this.drawWaveform(ctx, px, width);
    ctx.restore();
    this.drawMedia(ctx,px,width,mediaLayout);
    if (this.selection) this.drawSelection(ctx, this.selection, px, cssHeight);
    if (this.cutAnchor != null) this.drawPendingCut(ctx, px, cssHeight);
    if (!this.headersActive) this.drawLabels(ctx,mediaLayout);
    if (this.hoverTime != null) this.drawHover(ctx, this.hoverTime, px, cssHeight);
    this.drawPlayhead(ctx, px, cssHeight);
    if (this.snapGuide) this.drawSnapGuide(ctx, px, cssHeight);
    this.libraryDrop?.draw(ctx, px, width, cssHeight);
  }

  drawRuler(ctx, duration, width, px) {
    ctx.fillStyle = this.color("ruler", "#151e25");
    ctx.fillRect(0, 0, width, 30);
    const ideal = 92 / px;
    const steps = [.25,.5,1,2,5,10,15,30,60,120,300,600];
    const step = steps.find((value) => value >= ideal) || 900;
    ctx.strokeStyle = this.color("grid", "rgba(235,240,242,.16)");
    ctx.fillStyle = this.color("text", "#8da1a6");
    ctx.font = this.font(10);
    for (let time = 0; time <= duration + step; time += step) {
      const x = time * px;
      ctx.beginPath(); ctx.moveTo(x, 20); ctx.lineTo(x, 30); ctx.stroke();
      ctx.fillText(formatTime(time), x + 5, 14);
    }
    this.reviewMarkers?.draw(ctx,px,duration);
  }

  drawFilmstrip(ctx, width) {
    const y = 36, height = this.compact ? 32 : 72;
    ctx.fillStyle = this.color("lane", "#132126");
    ctx.fillRect(0, y, width, height);
    if (!this.images.length) {
      const gradient = ctx.createLinearGradient(0, y, 0, y + height);
      gradient.addColorStop(0, this.color("lane-alt", "#1a2a31")); gradient.addColorStop(1, this.color("bg", "#0d181c"));
      ctx.fillStyle = gradient; ctx.fillRect(0, y, width, height);
      return;
    }
    // At Fit, sample across the entire recording instead of drawing only the
    // first thumbnails and pushing the rest beyond the visible source clock.
    const count = this.sourceReview ? Math.min(this.images.length, Math.max(1, Math.ceil(width / 92))) : this.images.length;
    const visibleImages = this.sourceReview ? Array.from({length:count}, (_,i) => this.images[Math.min(this.images.length-1, Math.floor((i+.5)*this.images.length/count))]) : this.images;
    const tileWidth = this.sourceReview ? width / count : Math.max(92, width / count);
    visibleImages.forEach((image, index) => {
      if (!image) return;
      const x = index * tileWidth;
      const scale = Math.max(tileWidth / image.width, height / image.height);
      const drawWidth = image.width * scale, drawHeight = image.height * scale;
      ctx.save(); ctx.beginPath(); ctx.rect(x, y, tileWidth - 1, height); ctx.clip();
      ctx.drawImage(image, x + (tileWidth - drawWidth) / 2, y + (height - drawHeight) / 2, drawWidth, drawHeight);
      ctx.restore();
    });
    ctx.fillStyle = "rgba(0,0,0,.12)"; ctx.fillRect(0, y, width, height);
  }

  drawLaneBackgrounds(ctx, width) {
    if (this.project?.manual?.sequence) return;
    const lanes = this.compact ? [[72,28],[104,26],[134,38]] : [[118,52],[178,34],[220,74]];
    if (this.hasTrackLanes()) { lanes[1][0] += 68; lanes[2][0] += 68; }
    lanes.forEach(([y,h], index) => {
      ctx.fillStyle = index % 2 ? this.color("lane-alt", "#111f24") : this.color("lane", "#0b171b");
      ctx.fillRect(0, y, width, h);
      ctx.strokeStyle = this.color("grid", "rgba(235,240,242,.07)");
      ctx.beginPath(); ctx.moveTo(0, y + h); ctx.lineTo(width, y + h); ctx.stroke();
    });
  }

  drawTracks(ctx, px) {
    if (!this.hasTrackLanes()) return;
    const viewportLeft = this.scroll.scrollLeft || 0;
    const blocks = this.project?.manual?.sequence && this.editTarget === "edit" ? this.targetClips() : null;
    for (const slot of ["A", "B"]) {
      if (this.project?.manual?.sequence && !this.project.sources?.[slot]) continue;
      const { top, bottom } = this.trackLane(slot);
      const h = bottom - top;
      const active = this.editTarget === slot || (this.project?.manual?.sequence && this.editTarget === "edit");
      ctx.fillStyle = active ? this.color("lane-alt", "#172d36") : this.color("lane", "#101d24");
      ctx.fillRect(0, top, this.geometry().width, bottom - top);
      const sourceClips = this.getTrackClips(this.project, slot);
      // Draw the same independently selectable cuts that hit testing uses.
      // A cut on B must not leave A looking like one unbroken recording.
      let cursor = 0;
      const visibleClips = blocks ? blocks.flatMap((block) => {
        while (cursor < sourceClips.length && sourceClips[cursor].end <= block.start) cursor++;
        const clip = sourceClips[cursor];
        return clip && clip.start <= block.start && clip.end >= block.end
          ? [{ ...clip, start: block.start, end: block.end, source_start: clip.source_start + block.start - clip.start }] : [];
      }) : sourceClips;
      for (const [clipIndex, clip] of visibleClips.entries()) {
        const x = clip.start * px, width = (clip.end - clip.start) * px;
        ctx.fillStyle = slot === "A" ? this.color("clip", "#23616d") : this.color("clip-b", "#5e4580");
        ctx.fillRect(x + 1, top + 2, Math.max(1, width - 2), h - 4);
        const thumbUrls=this.project.sources?.[slot]?.thumbnail_urls || [];
        const frames=slot==='A' ? this.images : thumbUrls.map(url=>this.mediaImages?.get(url));
        if(frames?.some(Boolean)) {
          ctx.save();ctx.beginPath();ctx.rect(x+1,top+2,Math.max(0,width-2),h-4);ctx.clip();ctx.globalAlpha=.85;
          for(let ix=Math.max(x,viewportLeft);ix<x+width && ix<viewportLeft+this.scroll.clientWidth;ix+=64) {
            const sourceTime=clip.source_start+(ix/px-clip.start)*(clip.video_speed||1);
            const index=Math.min(frames.length-1,Math.max(0,Math.floor(sourceTime/Math.max(.001,this.project.sources[slot].duration)*frames.length)));
            if(frames[index])ctx.drawImage(frames[index],ix,top+2,64,h-4);
          }ctx.restore();
        }
        ctx.strokeStyle = active ? this.color("selected", "#d3f4f4") : (slot === "A" ? this.color("clip-edge", "#44b9c6") : this.color("clip-edge", "#ab8bce"));
        ctx.lineWidth = 1; ctx.strokeRect(x + .5, top + 2.5, Math.max(0, width - 1), h - 5);
        if (width > 65) {
          ctx.save(); ctx.beginPath(); ctx.rect(x + 3, top, width - 6, h); ctx.clip();
          ctx.fillStyle = this.color("label", "#eef5f7"); ctx.font = this.font(10);
          const clipNumber = clipIndex + 1;
          const clipLabel = `${slot}${clipNumber} · ${formatTime(clip.source_start, true)} · ${(clip.end - clip.start).toFixed(1)}s${clip.video_speed && clip.video_speed!==1 ? ` · ${clip.video_speed}× picture` : ''}`;
          const labelX = Math.max(x + 8, viewportLeft + this.labelInset(64)), labelY = top + (h > 40 ? 29 : 19);
          // Thumbnails sit behind the label; a dark chip keeps it legible on any frame.
          ctx.fillStyle = "rgba(8,12,16,.72)"; ctx.fillRect(labelX - 4, labelY - 11, ctx.measureText(clipLabel).width + 8, 15);
          ctx.fillStyle = "#eef5f7";
          ctx.fillText(clipLabel, labelX, labelY);
          ctx.restore();
        }
      }
      for (const cut of this.project?.draft?.cuts || []) {
        ctx.fillStyle = "rgba(0,0,0,.55)";
        ctx.fillRect(cut.start * px, top, (cut.end - cut.start) * px, h);
      }
      if (this.gesture?.kind === "move" && [slot, "edit"].includes(this.gesture.target) && this.gesture.moveStart != null) {
        const clip = this.gesture.clip;
        ctx.fillStyle = this.gesture.collision ? this.color("danger-fill", "rgba(255,93,93,.55)") : this.color("move-fill", "rgba(185,244,213,.6)");
        ctx.fillRect(this.gesture.moveStart * px, top, (clip.end - clip.start) * px, h);
        if (this.gesture.target === "edit") {
          const x = this.gesture.moveStart * px;
          ctx.strokeStyle = this.color("selected", "#b9f4d5"); ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        }
      }
    }
  }

  drawAudioEvidence(ctx, px) {
    const ranges = this.project?.analysis?.audio?.ranges || {};
    const y = this.project?.manual?.sequence ? (this.project.sources?.B ? 182 : 126) : this.compact ? 134 : 220, height = this.project?.manual?.sequence ? 32 : this.compact ? 38 : 74;
    for (const item of this.audioTimelineRanges(ranges.silence || [])) {
      const x = Number(item.start) * px;
      const w = Math.max(1, (Number(item.end) - Number(item.start)) * px);
      ctx.fillStyle = "rgba(116,126,132,.12)";
      ctx.fillRect(x, y, w, height);
    }
    for (const item of this.audioTimelineRanges(ranges.clipping || [])) {
      const x = Number(item.start) * px;
      const w = Math.max(2, (Number(item.end) - Number(item.start)) * px);
      ctx.fillStyle = this.color("danger-soft", "rgba(255,83,74,.18)");
      ctx.fillRect(x, y, w, height);
    }
  }

  drawGaps(ctx, px) {
    if (this.gesture?.kind === "move") return;
    const {top,bottom} = this.editLane();
    for (const gap of sequenceGaps(this.project,this.getTrackClips,this.editTarget === "edit" ? null : this.editTarget)) {
      const x=gap.start*px,width=(gap.end-gap.start)*px;
      ctx.fillStyle=this.color("gap-fill", "rgba(210,147,110,.1)");ctx.fillRect(x,top,width,bottom-top);
      ctx.strokeStyle=this.color("gap-edge", "#866c58");ctx.setLineDash([4,4]);ctx.strokeRect(x+.5,top+2,width-1,bottom-top-4);ctx.setLineDash([]);
      if (width>45) {
        ctx.save();ctx.beginPath();ctx.rect(x+3,top,width-6,bottom-top);ctx.clip();
        ctx.fillStyle=this.color("text", "#d3b9a9");ctx.font=this.font(10);
        ctx.fillText(`GAP · ${(gap.end-gap.start).toFixed(1)}s`,x+8,(top+bottom)/2+4);ctx.restore();
      }
    }
  }

  drawRanges(ctx, px) {
    const draft = this.project?.draft;
    const duration = timelineDuration(this.project);
    const y = this.compact ? 76 : 124, height = this.compact ? 22 : 40;
    ctx.fillStyle = this.color("lane-alt", "rgba(141,161,166,.08)");
    ctx.fillRect(0, y, duration * px, height);
    for (const clip of editableClips(this.project)) {
      const x = clip.start * px;
      const width = Math.max(1, (clip.end - clip.start) * px);
      const selected = this.editTarget === "edit" && this.selection && Math.abs(this.selection.start - clip.start) < .015 && Math.abs(this.selection.end - clip.end) < .015;
      ctx.fillStyle = selected ? this.color("keep-selected", "#36834e") : (clip.index % 2 ? this.color("keep-alt", "#235b43") : this.color("keep", "#1e4d3a"));
      ctx.fillRect(x, y, width, height);
      ctx.strokeStyle = selected ? this.color("selected", "#b7f4d2") : this.color("clip-edge", "#45976b");
      ctx.lineWidth = selected ? 2 : 1;
      ctx.strokeRect(x + .5, y + .5, Math.max(0, width - 1), height - 1);
      if (width > 34) {
        ctx.save(); ctx.beginPath(); ctx.rect(x + 3, y, Math.max(0, width - 6), height); ctx.clip();
        ctx.fillStyle = this.color("label", "#d4efdf");
        ctx.font = this.font(10, 600);
        ctx.fillText(this.sourceReview ? `In edit · ${formatTime(clip.end - clip.start, true)}` : width > 100 ? `Clip ${clip.index + 1} · ${formatTime(clip.end - clip.start, true)}` : `${clip.index + 1}`, x + 8, y + (this.compact ? 15 : 24));
        ctx.restore();
      }
    }
    for (const cut of draft?.cuts || []) {
      const x = Number(cut.start) * px;
      const width = Math.max(2, (Number(cut.end) - Number(cut.start)) * px);
      ctx.fillStyle = this.color("danger", "#ff5b49");
      ctx.fillRect(x, y, width, height);
      if (width > 42) {
        ctx.fillStyle = this.color("danger-label", "#170604"); ctx.font = this.font(9, 700);
        ctx.fillText(this.sourceReview ? "REMOVED" : "CUT", x + 6, y + (this.compact ? 17 : 25));
      }
    }
  }

  layoutScenes() {
    const duration = timelineDuration(this.project);
    const plan = this.project?.draft?.camera_plan;
    return (Array.isArray(plan) ? plan : []).filter((item) => item && typeof item === "object").map((item) => ({
      start: Math.max(0, Number(item.start)), end: Math.min(duration, Number(item.end)), camera: String(item.camera || "A"),
    })).filter((item) => Number.isFinite(item.start) && Number.isFinite(item.end) && item.end - item.start >= selectionMinimum(this.project));
  }

  layoutAt(time) {
    // A layout only affects kept footage. Clicking a removed section still
    // selects that gap so it can be restored, never a phantom active scene.
    if (!this.project?.manual?.sequence && !this.clipAt(time)) return null;
    const scenes = this.layoutScenes();
    return scenes.find((item) => time >= item.start && time < item.end)
      || (time === timelineDuration(this.project) ? scenes.find((item) => item.end === time) : null);
  }

  layoutSegments() {
    const kept = [];
    for (const clip of editableClips(this.project)) {
      const previous = kept.at(-1);
      if (previous && Math.abs(previous.end - clip.start) < .001) previous.end = clip.end;
      else kept.push({ start: clip.start, end: clip.end });
    }
    return this.layoutScenes().flatMap((scene) => kept.map((range) => ({
      ...scene, start: Math.max(range.start, scene.start), end: Math.min(range.end, scene.end),
    })).filter((item) => item.end - item.start >= selectionMinimum(this.project)));
  }

  drawLayouts(ctx, px) {
    const y = this.project?.manual?.sequence ? (this.project.sources?.B ? 152 : 96) : this.compact ? 108 : 184;
    const labels = { A: "Source A", B: "Source B", screen: "Screen", camera: "Camera", stacked: "Stacked", embedded_stack: "Stacked", side_by_side: "Side by side", pip: "PiP", auto: "Auto" };
    for (const item of this.layoutSegments()) {
      const x = item.start * px;
      const width = Math.max(1, (item.end - item.start) * px);
      const camera = item.camera;
      ctx.fillStyle = ["A", "screen"].includes(camera) ? this.color("clip", "#44b9c6") : ["B", "camera"].includes(camera) ? this.color("clip-b", "#9676bd") : this.color("layout", "#c9b62c");
      ctx.globalAlpha = .82; ctx.fillRect(x, y, width, 22); ctx.globalAlpha = 1;
      // Clip labels to their own scene, especially on long/zoomed-out sources.
      const labelX = Math.max(x + 6, (this.scroll.scrollLeft || 0) + this.labelInset(70));
      if (width > 38 && labelX < x + width - 12) {
        ctx.save(); ctx.beginPath(); ctx.rect(x + 2, y, Math.max(0, width - 4), 22); ctx.clip();
        ctx.fillStyle = this.color(["A", "screen", "B", "camera"].includes(camera) ? "label" : "layout-label", "#081013"); ctx.font = this.font(9, 700);
        const label = labels[camera] || camera;
        ctx.fillText(label, labelX, y + 14);
        ctx.restore();
      }
    }
  }

  waveformProfile() {
    const project = this.project;
    const requested = String(this.getAudioSlot?.(project) || project?.manual?.source_mixer?.audio_slot || project?.settings?.audio_source || "A").toUpperCase();
    let slot = ["A", "B"].includes(requested) ? requested : "A";
    if (!project?.sources?.[slot] || project.sources[slot].has_audio === false) {
      slot = ["A", "B"].find(key => project?.sources?.[key] && project.sources[key].has_audio !== false) || slot;
    }
    const source = project?.sources?.[slot];
    if (!source || source.has_audio === false) return { slot, profile: null, state: "no-audio", native: true };
    // Upload preparation measures each original source, even in a manual edit
    // that has never run Director. Its timestamps are already source-native.
    const prepared = project?.pre_analysis?.audio?.[slot];
    if (prepared) return { slot, profile: prepared, state: prepared.available === false ? "unavailable" : prepared.waveform?.length ? "ready" : "empty", native: true };
    const analyzed = String(project?.analysis?.audio_source || project?.draft?.audio_source || "A").toUpperCase();
    const legacy = slot === analyzed ? project?.analysis?.audio : null;
    if (legacy) return { slot, profile: legacy, state: legacy.available === false ? "unavailable" : legacy.waveform?.length ? "ready" : "empty", native: false };
    return { slot, profile: null, state: source.preparation_error ? "unavailable" : source.audio_profile_ready === false ? "pending" : "empty", native: true };
  }

  waveformRanges(profile = this.waveformProfile()) {
    const bins = profile.profile?.waveform;
    if (profile.state !== "ready" || !Array.isArray(bins)) return [];
    return this.sourceTimelineRanges(bins, profile.slot, profile.native ? 0 : profile.slot === "B" ? Number(this.project?.analysis?.audio_timeline_offset) || 0 : 0);
  }

  drawWaveform(ctx, px, width) {
    const profile = this.waveformProfile(), bins = this.waveformRanges(profile);
    const y = this.project?.manual?.sequence ? (this.project.sources?.B ? 186 : 130) : this.compact ? 140 : 230, height = this.compact || this.project?.manual?.sequence ? 26 : 54, mid = y + height / 2;
    const left = Math.max(0, this.scroll.scrollLeft || 0), right = Math.min(width, left + (this.scroll.clientWidth || width));
    ctx.fillStyle = this.color("wave-bg", "rgba(47,176,138,.14)");
    ctx.fillRect(0, y, Math.min(width, timelineDuration(this.project) * px), height);
    ctx.strokeStyle = this.color("grid", "rgba(235,243,245,.22)");
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(left, mid); ctx.lineTo(right, mid); ctx.stroke();
    ctx.strokeStyle = this.color("wave", "#3fd09e");
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (bins.length) {
      for (const bin of bins) {
        const start = Number(bin.start), end = Number(bin.end);
        if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start || end * px < left || start * px > right) continue;
        const x = ((start + end) / 2) * px;
        const rmsValue = Number(bin.rms_dbfs), peakValue = Number(bin.peak_dbfs ?? bin.rms_dbfs);
        if (!Number.isFinite(rmsValue) || !Number.isFinite(peakValue)) continue;
        const rms = Math.max(-72, Math.min(0, rmsValue)), peak = Math.max(-72, Math.min(0, peakValue));
        const amp = ((rms + 72) / 72) * height * .42;
        const peakAmp = Math.max(amp, ((peak + 72) / 72) * height * .48);
        const drawBin = position => {
          if (amp > 0) { ctx.moveTo(position, mid - amp); ctx.lineTo(position, mid + amp); }
          if (peakAmp > amp + 1) { ctx.moveTo(position, mid - peakAmp); ctx.lineTo(position, mid - amp); }
        };
        if (x >= left && x <= right) drawBin(x);
        // A zoomed-in measurement occupies its true time span. Do not invent
        // extra samples or leave wide gaps between the existing measured bins.
        if ((end - start) * px > 3) {
          for (let position = Math.ceil(Math.max(start * px, left) / 2) * 2; position < Math.min(end * px, right); position += 2) drawBin(position);
        }
      }
    } else {
      const message = profile.state === "no-audio" ? "Source has no audio" : profile.state === "pending" ? "Measuring source audio\u2026" : profile.state === "unavailable" ? "Source waveform unavailable" : profile.state === "ready" ? "No source audio in this edit" : "No waveform data";
      ctx.fillStyle = this.color("text", "#aebbc0"); ctx.font = this.font(10);
      ctx.fillText(message, left + this.labelInset(74), mid + 3);
    }
    ctx.stroke();
  }

  audioTimelineRanges(ranges) {
    if (!ranges.length || !this.getTrackClips || !this.project?.manual?.source_tracks) return ranges;
    const project = this.project;
    const analyzed = String(project.analysis?.audio_source || project.draft?.audio_source || "A");
    const selected = String(project.manual?.source_mixer?.audio_slot || project.settings?.audio_source || "A");
    if (selected !== analyzed) return [];
    const offset = selected === "B" ? Number(project.analysis?.audio_timeline_offset) || 0 : 0;
    return this.sourceTimelineRanges(ranges, selected, offset);
  }

  sourceTimelineRanges(ranges, slot, offset = 0) {
    if (!ranges.length || !this.getTrackClips || !this.project?.manual?.source_tracks) return ranges;
    const project = this.project, clips = this.getTrackClips(project, slot);
    if (this.audioCacheProject !== project) { this.audioRangeCache = new Map(); this.audioCacheProject = project; }
    // Drag/trim previews can mutate the same project object. Include clip
    // geometry so a repaint cannot reuse data from before the gesture.
    const signature = `${slot}:${offset}:${clips.map(clip => `${clip.start},${clip.end},${clip.source_start}`).join(";")}`;
    const cached = this.audioRangeCache.get(ranges);
    if (cached?.signature === signature) return cached.mapped;
    const mapped = clips.flatMap((clip) => ranges.map((item) => {
      const start = Math.max(Number(item.start) - offset, clip.source_start);
      const end = Math.min(Number(item.end) - offset, clip.source_start + clip.end - clip.start);
      return { ...item, start: clip.start + start - clip.source_start, end: clip.start + end - clip.source_start };
    }).filter((item) => item.end > item.start));
    this.audioRangeCache.set(ranges, { signature, mapped });
    return mapped;
  }

  drawLabels(ctx, layout = this.mediaLayout()) {
    ctx.font = this.font(9, 700);
    const labels = this.compact ? [["EDIT",80],["LAYOUT",123],["AUDIO",144]] : [["EDIT",127],["LAYOUT",199],["AUDIO",232]];
    if (this.sourceReview) labels.splice(0, labels.length, ["SOURCE",80],["AUDIO",144]);
    if (this.project?.manual?.sequence) { labels.splice(0, labels.length, ["LAYOUT",this.project.sources?.B ? 167 : 111],["AUDIO",this.project.sources?.B ? 198 : 142]); }
    else if (this.hasTrackLanes()) { labels[1][1] += 68; labels[2][1] += 68; }
    const viewportLeft = this.scroll.scrollLeft || 0;
    if (this.hasTrackLanes()) for (const slot of ["A", "B"]) {
      if (this.project?.manual?.sequence && !this.project.sources?.[slot]) continue;
      const {top} = this.trackLane(slot), protectedTrack = this.lockedTargets(slot).length > 0;
      const active = this.editTarget === slot || (this.project?.manual?.sequence && this.editTarget === "edit");
      ctx.fillStyle = this.color("ruler", "rgba(8,16,19,.94)"); ctx.fillRect(viewportLeft + 4, top + 4, protectedTrack ? 96 : 52, 21);
      ctx.fillStyle = active ? this.color("selected", "#ffffff") : this.color("text", "#8da1a6");
      ctx.font = this.font(9, 700); ctx.fillText(`VIDEO ${slot}${protectedTrack ? " · LOCKED" : ""}`, viewportLeft + 9, top + 18);
    }
    labels.push(...layout.rows.map(row => [row.label,row.top+13]));
    if (layout.caption) labels.push([layout.caption.label,layout.caption.top+17]);
    ctx.font = this.font(10, 700);
    for (const [label,y] of labels) {
      const width = ctx.measureText(label).width + 12;
      ctx.fillStyle = this.color("ruler", "rgba(9,11,13,.94)"); ctx.fillRect(viewportLeft + 4, y - 11, width, 17);
      ctx.fillStyle = this.color("text", "#aebbc0"); ctx.fillText(label, viewportLeft + 10, y);
    }
  }

  drawPlayhead(ctx, px, height) {
    const x = this.playhead * px;
    ctx.strokeStyle = this.color("selected", "#1bd9ce"); ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    ctx.fillStyle = this.color("selected", "#1bd9ce");
    ctx.beginPath(); ctx.moveTo(x - 6, 0); ctx.lineTo(x + 6, 0); ctx.lineTo(x, 8); ctx.closePath(); ctx.fill();
  }

  drawSelection(ctx, selection, px, height) {
    const x1 = Number(selection.start) * px;
    const x2 = Number(selection.end) * px;
    const width = Math.max(1, x2 - x1);
    const { top, bottom } = this.editLane();
    ctx.fillStyle = this.color("selection-fill", "rgba(68,185,198,.14)");
    ctx.fillRect(x1, this.editTarget === "edit" ? 30 : top, width, this.editTarget === "edit" ? height - 30 : bottom - top);
    ctx.strokeStyle = this.color("selected", "rgba(68,185,198,.94)");
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x1, 30); ctx.lineTo(x1, height);
    ctx.moveTo(x2, 30); ctx.lineTo(x2, height);
    ctx.stroke();
    const trim = this.trimTarget() || this.gesture?.kind === "trim";
    ctx.fillStyle = trim ? this.color("selected", "#e8ffff") : this.color("selected", "#9deaf0");
    ctx.fillRect(x1, top + 3, 5, bottom - top - 6);
    ctx.fillRect(x2 - 5, top + 3, 5, bottom - top - 6);
    if (trim) {
      ctx.fillStyle = this.color("clip", "#23616d");
      for (const x of [x1+2,x2-3]) ctx.fillRect(x,top+12,1,Math.max(4,bottom-top-24));
    }
  }

  drawHover(ctx, time, px, height) {
    const mediaFeedback = this.tool === "slip" ? this.mediaSlipHover
      : this.gesture?.nativeTrim ? this.mediaTrimHover : (this.gesture?.nativeMove || this.gesture?.kind==="media_group") ? this.mediaMoveHover
        : this.tool === "blade" ? this.bladeHover : null;
    if (this.gesture?.kind === "move" && Number.isFinite(this.gesture.moveStart)) time = this.gesture.moveStart;
    if (this.gesture?.kind === "trim" && Number.isFinite(this.gesture.trimTime)) time = this.gesture.trimTime;
    if (mediaFeedback) time = mediaFeedback.time;
    const x = time * px;
    ctx.strokeStyle = this.color("grid", "rgba(255,255,255,.28)"); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, height); ctx.stroke();
    const operation = this.gesture?.kind === "trim" ? `Trim ${this.gesture.edge} · `
      : this.gesture?.kind === "move" ? this.gesture.target === "edit" ? "Move together · " : `Move ${this.gesture.target} · ` : "";
    const stamp = this.project?.manual?.sequence || this.sourceReview ? formatFrameTime(time, 1 / sequenceFrame(this.project)) : formatTime(time, true);
    const label = mediaFeedback ? mediaFeedback.showTime === false ? mediaFeedback.label : `${mediaFeedback.label} · ${stamp}` : `${operation}${stamp}`;
    ctx.font = this.font(10);
    const left = this.scroll.scrollLeft || 0, viewport = this.scroll.clientWidth || this.geometry().viewport;
    const w = Math.min(ctx.measureText(label).width + 12,Math.max(0,viewport-4));
    const labelX = Math.max(left+2, Math.min(left+viewport-w-2, x-w/2));
    const labelY = mediaFeedback ? Math.max(31, (this.scroll.scrollTop || 0) + 4) : 31;
    ctx.save(); ctx.beginPath(); ctx.rect(labelX,labelY,w,20); ctx.clip();
    ctx.fillStyle = this.color("text", "#f4f7f7"); ctx.fillRect(labelX, labelY, w, 20);
    ctx.fillStyle = this.color("bg", "#081013"); ctx.fillText(label, labelX + 6, labelY + 14);
    ctx.restore();
  }

  drawSnapGuide(ctx, px, height) {
    const { time, label } = this.snapGuide, x = time * px;
    ctx.save(); ctx.strokeStyle = this.color("selected", "#a6f1ed"); ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke(); ctx.setLineDash([]);
    const text = `Snap · ${label}`;
    ctx.font = this.font(11);
    const width = ctx.measureText(text).width + 12;
    const left = this.scroll.scrollLeft || 0;
    const labelX = Math.max(left + 2, Math.min(left + this.scroll.clientWidth - width - 2, x + 6));
    ctx.fillStyle = this.color("selected", "#a6f1ed"); ctx.fillRect(labelX, 4, width, 20);
    ctx.fillStyle = this.color("on-selected", "#081013"); ctx.fillText(text, labelX + 6, 18); ctx.restore();
  }

  drawPendingCut(ctx, px, height) {
    const x = this.cutAnchor * px;
    if (this.hoverTime != null) {
      const { top, bottom } = this.editLane();
      ctx.fillStyle = this.color("danger-soft", "rgba(255,123,134,.25)");
      ctx.fillRect(Math.min(x, this.hoverTime * px), top, Math.abs(this.hoverTime * px - x), bottom - top);
    }
    ctx.strokeStyle = this.color("danger", "#ff9aa3");
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, height); ctx.stroke();
    ctx.setLineDash([]);
  }

  timeFromEvent(event) {
    const rect = this.canvas.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
    const { px, duration } = this.geometry();
    return Math.max(0, Math.min(duration, x / Math.max(px, .0001)));
  }

  editLane() {
    if (this.sourceReview) return { top: 72, bottom: 100 };
    if (this.project?.manual?.sequence && this.hasTrackLanes() && this.editTarget === "edit") {
      return { top: this.trackLane("A").top, bottom: this.trackLane(this.project.sources?.B ? "B" : "A").bottom };
    }
    if (this.hasTrackLanes() && this.editTarget !== "edit") return this.trackLane(this.editTarget);
    const compact = Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    return compact ? { top: 72, bottom: 100 } : { top: 118, bottom: 170 };
  }

  inEditLane(event) {
    if (this.project?.manual?.sequence && this.editTarget === "edit") return this.targetAtEvent(event) != null;
    const y = event.clientY - this.canvas.getBoundingClientRect().top;
    const { top, bottom } = this.editLane();
    return y >= top && y <= bottom;
  }

  inLayoutLane(event) {
    if (this.sourceReview) return false;
    if (this.project?.manual?.sequence) {
      const local = event.clientY - this.canvas.getBoundingClientRect().top;
      const top = this.project.sources?.B ? 152 : 96;
      return local >= top && local <= top + 22;
    }
    const y = event.clientY - this.canvas.getBoundingClientRect().top - (this.hasTrackLanes() ? 68 : 0);
    const compact = Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    return compact ? y >= 104 && y <= 130 : y >= 178 && y <= 212;
  }

  inSelectionArea(event) {
    const y = event.clientY - this.canvas.getBoundingClientRect().top;
    const height = this.project?.manual?.sequence ? (this.project.sources?.B ? 230 : 174) : (this.scroll.closest?.(".studio-timeline-dock") ? 180 : 310) + (this.hasTrackLanes() ? 68 : 0);
    return y >= 30 && y <= height;
  }

  selectableRangeAt(time) {
    const kept = this.clipAt(time);
    if (kept) return kept;
    const duration = timelineDuration(this.project);
    if (!this.project?.draft || time < 0 || time > duration) return null;
    const clips = this.targetClips();
    // Removed footage stays selectable, including leading/trailing gaps.
    const start = clips.filter((clip) => clip.end <= time).at(-1)?.end ?? 0;
    const end = clips.find((clip) => clip.start > time)?.start ?? duration;
    return end - start >= selectionMinimum(this.project) ? { start, end } : null;
  }

  clipAt(time) {
    const clips = this.targetClips();
    return clips.find((clip) => time >= clip.start && time < clip.end)
      || (time === timelineDuration(this.project) ? clips.find((clip) => clip.end === time) : null);
  }

  snapPoints() {
    const duration = timelineDuration(this.project), g = this.gesture;
    const moving = g?.kind === "move" ? g.clip : null;
    const ripple = Boolean(moving && this.project?.manual?.sequence);
    const length = moving ? moving.end - moving.start : 0;
    const points = [{time: 0, label: "Start"}, {time: duration, label: "End"}];
    if (ripple && this.editTarget === "edit") points[1].time -= length;
    const addEdges = (clip, label, affected = false) => {
      for (let time of [clip.start, clip.end]) {
        if (moving && affected && time > moving.start && time < moving.end) continue;
        if (ripple && affected && time >= moving.end) time -= length;
        points.push({time, label});
      }
    };
    if (!this.sourceReview && this.hasTrackLanes()) {
      for (const slot of ["A", "B"]) {
        if (!this.project.sources?.[slot]) continue;
        const affected = this.editTarget === "edit" || this.editTarget === slot;
        for (const clip of this.getTrackClips(this.project, slot)) {
          if (affected && (moving || g?.kind === "trim") && clip.start >= g.clip.start && clip.end <= g.clip.end) continue;
          addEdges(clip, `${slot} edit`, affected);
        }
      }
    } else {
      for (const clip of this.targetClips()) {
        if (moving && clip.id === moving.id) continue;
        addEdges(clip, "Edit", true);
      }
    }
    if (!this.sourceReview) for (const clip of this.project?.manual?.media_clips || []) {
      if (clip.id === g?.media?.id || g?.ids?.includes(clip.id) || !this.project.assets?.[clip.asset_id]) continue;
      // Added media currently stays on its own edit clock even in Together
      // moves. Do not advertise a shifted edge that the backend will not move.
      addEdges(clip, this.project.assets[clip.asset_id].kind === "audio" ? "Audio edge" : "Media edge");
    }
    if (!this.sourceReview) for (const clip of this.project?.manual?.text_clips || []) {
      if (clip.id !== g?.media?.id && !g?.ids?.includes(clip.id)) addEdges(clip, clip.kind === 'title' ? 'Text edge' : 'Caption edge');
    }
    // Pointerdown seeks the preview. Keep the user's original yellow marker
    // as the target throughout a drag rather than chasing that seek.
    points.push({time: g?.snapPlayhead ?? this.playhead, label: "Playhead"});
    return points.filter(point => Number.isFinite(point.time) && point.time >= 0 && point.time <= duration);
  }

  snappedTime(time, event, offsets = [0]) {
    this.snapGuide = null;
    if (this.sourceReview) time = Math.max(0, Math.min(timelineDuration(this.project), Math.round(time / sequenceFrame(this.project)) * sequenceFrame(this.project)));
    if (!this.snapping || event.altKey) return time;
    const { px } = this.geometry();
    const threshold = Math.min(.5, 8 / Math.max(px, .0001));
    let nearest = time, distance = threshold;
    for (const point of this.snapPoints()) for (const offset of offsets) {
      const delta = Math.abs(time + offset - point.time);
      if (delta <= distance) { nearest = point.time - offset; distance = delta; this.snapGuide = point; }
    }
    return nearest;
  }

  validateSnap(times) {
    // Source limits, collisions and ripple clamping always win over magnets.
    if (this.snapGuide && !times.some(time => Math.abs(time - this.snapGuide.time) < 1e-6)) this.snapGuide = null;
  }

  selectionEdge(event, time) {
    if (!this.selection || !this.inSelectionArea(event)) return null;
    const { px } = this.geometry();
    const startDistance = Math.abs(time - this.selection.start) * px;
    const endDistance = Math.abs(time - this.selection.end) * px;
    if (Math.min(startDistance, endDistance) > 8) return null;
    return startDistance <= endDistance ? "start" : "end";
  }

  trimTarget() {
    if (this.lockedTargets().length) return null;
    if (!this.project?.manual?.sequence || this.tool !== "select" || !this.selection) return null;
    if ((this.selection.end-this.selection.start)*this.geometry().px < 22) return null; // Zoom in for small clip handles; its body must stay draggable.
    return this.targetClips().find(c=>Math.abs(c.start-this.selection.start)<1e-6 && Math.abs(c.end-this.selection.end)<1e-6) || null;
  }

  trimEdgeAt(event,time) {
    return !event.shiftKey && this.inEditLane(event) && this.trimTarget() ? this.selectionEdge(event,time) : null;
  }

  trimEdgeTime(clip, edge, time) {
    const frame = sequenceFrame(this.project), slots = (this.editTarget === "edit" ? ["A","B"] : [this.editTarget]).filter(s=>this.project.sources?.[s]);
    let minimum = edge === "start" ? 0 : clip.start+frame;
    let maximum = edge === "start" ? clip.end-frame : 86400;
    let touches = false;
    for (const slot of slots) {
      for (const row of this.getTrackClips(this.project,slot)) {
        if (edge === "start") {
          if (row.start <= clip.start && row.end > clip.start) {
            minimum = Math.max(minimum, row.start < clip.start-1e-6 ? clip.start : clip.start-row.source_start);
            touches = true;
          } else if (row.end <= clip.start) minimum = Math.max(minimum,row.end);
        } else {
          if (row.start < clip.end && row.end >= clip.end) {
            maximum = Math.min(maximum, row.end > clip.end+1e-6 ? clip.end : clip.end+Number(this.project.sources[slot].duration)-row.source_start-row.end+row.start);
            touches = true;
          } else if (row.start >= clip.end) maximum = Math.min(maximum,row.start);
        }
      }
    }
    if (minimum > maximum + 1e-9) return clip[edge]; // A preserved 60 FPS cut may be shorter than the current 30 FPS trim minimum.
    return touches ? Math.max(minimum,Math.min(maximum,Math.round(time/frame)*frame)) : clip[edge];
  }

  releasePointer(pointerId) {
    // Capture can disappear after leaving a window or removing the canvas.
    try {
      if (!this.canvas.hasPointerCapture || this.canvas.hasPointerCapture(pointerId)) this.canvas.releasePointerCapture?.(pointerId);
    } catch (_) { /* The gesture is already ended locally. */ }
  }

  cancelGesture(notify = true) {
    this.snapGuide = null;
    this.clearMediaTrimHover();
    this.clearMediaSlipHover();
    this.clearMediaMoveHover();
    if (['media', 'media_slip'].includes(this.gesture?.kind) && !this.gesture.nativeTrack) this.onMediaPreview?.(this.gesture.media.id, null);
    if (this.gesture?.kind==="media_group") this.onMediaGroupPreview?.(null);
    const gesture = this.gesture;
    if (!gesture) return false;
    if (gesture.kind === 'media_blade') {
      this.gesture = null; this.releasePointer(gesture.pointerId); this.clearBladeHover(); this.scheduleDraw(); return true;
    }
    if (['caption','media_group'].includes(gesture.kind)) { this.gesture = null; this.releasePointer(gesture.pointerId); this.scheduleDraw(); return true; }
    this.gesture = null;
    this.scrubbing = false;
    this.selecting = false;
    this.selectionAnchor = null;
    this.selectionCursor = null;
    this.selection = gesture.previousSelection;
    this.selectionIsRange = gesture.previousRangeSelection;
    this.releasePointer(gesture.pointerId);
    if (notify && ["range", "edge", "clip", "layout", "move"].includes(gesture.kind)) this.onSelectionChange?.(this.selection);
    this.scheduleDraw();
    return true;
  }

  pointerCancel(event) {
    if (this.gesture?.pointerId === event.pointerId) this.cancelGesture();
  }

  seekGesture(time) {
    // The preview follows source time, including footage omitted by the draft.
    // Selection snapping must never redirect the playhead to a kept boundary.
    if (this.gesture?.lastSeek === time) return;
    if (this.gesture) this.gesture.lastSeek = time;
    this.onSeek?.(time);
  }

  updatePointerCursor(event, time) {
    this.clearMediaMoveHover();
    const grouped=this.selectedMediaIds();
    if(grouped.length>1){
      const media=this.mediaAtEvent(event);
      if(media && grouped.includes(media.clip.id)){
        const edge=this.mediaEdgeAt(media.clip,time),allowed=["select","move"].includes(this.tool)&&!edge;
        this.canvas.style.cursor=allowed?"grab":"not-allowed";
        this.canvas.title=allowed?`Move ${grouped.length} selected layers together. Timing offsets and content stay fixed; no ripple. Ctrl/Cmd-click toggles selection.`:`Select one layer to trim, split or slip. ${this.mediaGroupActionHint()}`;
        return;
      }
    }
    if (this.tool === "slip") {
      this.clearBladeHover(); this.clearMediaTrimHover();
      const media = this.mediaAtEvent(event), ruler = event.clientY - this.canvas.getBoundingClientRect().top < 30;
      if (!media && ruler) {
        this.clearMediaSlipHover(); this.canvas.style.cursor = "col-resize";
        this.canvas.title = "Seek the edit. Slip changes source content inside an imported video or audio clip.";
        return;
      }
      const issue = media ? this.mediaSlipPlan(media.clip.id, Number(media.clip.source_start || 0)).issue
        : this.captionAtEvent(event) ? "Automatic speech captions cannot be slipped. Choose an imported video or audio clip."
          : "Slip changes only imported video or audio content, not source A/B or empty timeline time.";
      const label = issue ? `Slip blocked: ${issue}` : "Slip source: right = later, left = earlier. Timing stays fixed.";
      this.mediaSlipHover = { time, label, showTime: false };
      this.canvas.title = disabledLayerNote(media?.clip) + label; this.canvas.style.cursor = issue ? "not-allowed" : "ew-resize";
      return;
    }
    this.clearMediaSlipHover();
    if (this.tool === "blade") {
      const media = this.mediaAtEvent(event), caption = !media && this.captionAtEvent(event);
      if (media || caption) {
        const splitTime = this.splitTime(time), issue = media ? this.mediaSplitReadiness(media.clip.id, splitTime)
          : "Automatic speech captions cannot be split. Edit the caption text or timing instead.";
        const kind = media?.row.type === "text" ? media.clip.kind === "caption" ? "text caption" : "title"
          : media?.row.type === "audio" ? "audio" : "media";
        this.bladeHover = { time: splitTime, label: issue ? `Split blocked: ${issue}` : `Split ${kind}` };
        this.canvas.title = disabledLayerNote(media?.clip) + (issue || `Split only this ${kind} at ${formatFrameTime(splitTime, 1 / sequenceFrame(this.project))}. Timeline duration stays unchanged.`);
        this.canvas.style.cursor = issue ? "not-allowed" : "crosshair";
        return;
      }
    }
    this.clearBladeHover();
    this.clearMediaTrimHover();
    const media = this.mediaAtEvent(event);
    if (media && this.tool !== "blade") {
      const edge = this.mediaEdgeAt(media.clip, time);
      this.canvas.style.cursor = edge ? "ew-resize" : this.gesture?.kind === "media" ? "grabbing" : "grab";
      const protection = this.mediaProtectionIssue(media.clip.id) || (edge && this.project?.manual?.layer_tracks?.version >= 2 && !this.nativeMediaTrim() ? "Trim protection is unavailable in this editor." : "");
      if (protection) { this.canvas.title = disabledLayerNote(media.clip) + protection; this.canvas.style.cursor = "not-allowed"; return; }
      if (edge && this.nativeMediaTrim()) this.canvas.title = disabledLayerNote(media.clip) + `Drag to trim this layer's ${edge}. Other layers and timeline duration stay unchanged.`;
      else if (!edge && timelineLayerTrackState(this.project).enabled) {
        const issue=this.mediaTrackPlan(media.clip.id,media.clip.start,media.clip.track_id).issue;
        this.canvas.title=disabledLayerNote(media.clip)+(issue || "Move this clip in time or to another compatible track. Higher tracks cover lower tracks; no ripple.");
        if(issue)this.canvas.style.cursor="not-allowed";
      }
      else if (!edge && this.nativeMediaMove()) {
        const issue = this.mediaMovePlan(media.clip.id, media.clip.start).issue;
        this.canvas.title = disabledLayerNote(media.clip) + (issue || "Move this whole layer. Content, duration and other layers stay unchanged; no ripple.");
        if (issue) this.canvas.style.cursor = "not-allowed";
      } else this.canvas.title = disabledLayerNote(media.clip);
      if (!edge && ["select", "move"].includes(this.tool) && this.nativeMediaSource()
        && this.project?.assets?.[media.clip.asset_id]?.kind === "video")
        this.canvas.title += " Double-click to open the original source at this point.";
      return;
    }
    if (this.inEditLane(event) && this.lockedTargets().length && this.tool !== "range") { this.canvas.style.cursor = "not-allowed"; return; }
    if (this.gesture?.kind === "move") { this.canvas.style.cursor = "grabbing"; return; }
    const hoverTarget = this.project?.manual?.sequence ? this.targetAtEvent(event) : null;
    const lane = this.inEditLane(event);
    const hoveredClip = hoverTarget && !this.project?.manual?.sequence && hoverTarget !== this.editTarget
      ? this.getTrackClips(this.project, hoverTarget).find((clip) => time >= clip.start && time < clip.end)
      : this.clipAt(time);
    const edge = !["blade", "remove_between"].includes(this.tool) ? this.selectionEdge(event, time) : null;
    if (this.gesture?.kind === "trim" || this.trimEdgeAt(event,time)) this.canvas.style.cursor = "ew-resize";
    else if ((this.tool === "move" || (this.project?.manual?.sequence && this.tool === "select" && !event.shiftKey)) && lane) {
      this.canvas.style.cursor = hoveredClip ? "grab" : this.tool === "move" ? "not-allowed" : "text";
    }
    else if (edge || this.gesture?.kind === "edge") this.canvas.style.cursor = "ew-resize";
    else if (this.tool === "blade" && lane) {
      this.canvas.style.cursor = this.canSplitAt(time) ? "crosshair" : "not-allowed";
    } else this.canvas.style.cursor = ["select", "range"].includes(this.tool) && this.inSelectionArea(event) ? "text" : "crosshair";
  }

  canSplitClip(clip, time) {
    if (!clip) return false;
    if (!this.project?.manual?.sequence) return time > clip.start + .03 && time < clip.end - .03;
    const frame = sequenceFrame(this.project) - 1e-9;
    return time - clip.start >= frame && clip.end - time >= frame;
  }

  splitTime(time) {
    const frame = sequenceFrame(this.project);
    return this.project?.manual?.sequence ? Math.round(time / frame) * frame : time;
  }

  clearBladeHover() {
    this.bladeHover = null;
    this.canvas.title = this.baseCanvasTitle;
  }

  clearMediaTrimHover() {
    this.mediaTrimHover = null;
    this.canvas.title = this.baseCanvasTitle;
  }

  clearMediaSlipHover() {
    this.mediaSlipHover = null;
    this.canvas.title = this.baseCanvasTitle;
  }

  clearMediaMoveHover() {
    this.mediaMoveHover = null;
    this.canvas.title = this.baseCanvasTitle;
  }

  mediaTrackPlan(clipId, start, trackId) {
    const protection = this.mediaProtectionIssue(clipId);
    if (protection) return {issue:protection,patch:null};
    const blocked=issue=>({issue,patch:null}), state=timelineLayerTrackState(this.project);
    if(this.sourceReview || this.editPending || !this.canEdit())return blocked("Wait for the current edit to finish.");
    if(!state.enabled || !state.valid || typeof this.mediaTrackMovePreview!=="function")return blocked("Persistent track placement is unavailable. Reopen the edit before moving this clip.");
    const clip=[...(this.project?.manual?.media_clips||[]),...(this.project?.manual?.text_clips||[])].find(row=>row.id===clipId),track=state.tracks.find(row=>row.id===trackId);
    if(!clip || !track)return blocked("Drop on a saved imported-media or custom-text track, not source A/B or automatic captions.");
    if(timelineLayerKind(this.project,clip)!==track.kind)return blocked(`Choose a ${timelineLayerKind(this.project,clip)||"compatible"} track for this clip. Its sound routing will not change.`);
    let plan;try{plan=this.mediaTrackMovePreview(clipId,start,trackId);}catch{/* Never fall through to a legacy or horizontal-only move. */}
    if(!plan || typeof plan.issue!=="string")return blocked("Track placement readiness could not be confirmed.");
    if(plan.issue)return blocked(plan.issue);
    const patch=plan.patch,keys=patch && typeof patch==="object" && !Array.isArray(patch)?Object.keys(patch).sort():null;
    if(!keys || (keys.length && (keys.join()!=="end,start,track_id" || patch.track_id!==trackId
      || !Number.isFinite(patch.start) || !Number.isFinite(patch.end) || patch.start<0 || patch.end>timelineDuration(this.project)+1e-8
      || Math.abs((patch.end-patch.start)-(clip.end-clip.start))>(clipId.startsWith("text_")?1e-6:1e-8))))
      return blocked("Track placement preview does not preserve this clip.");
    return plan;
  }

  moveMediaToTrack(clipId,start,trackId) {
    const plan=this.mediaTrackPlan(clipId,start,trackId);
    if(!this.onMediaAction || plan.issue || !Number.isFinite(plan.patch?.start))return false;
    const clip=[...(this.project?.manual?.media_clips||[]),...(this.project?.manual?.text_clips||[])].find(row=>row.id===clipId);
    if(!clip || (plan.patch.track_id===clip.track_id && Math.abs(plan.patch.start-clip.start)<=1e-9))return false;
    const request={projectId:this.project?.id};this.mediaTrackMovePending=request;this.editPending=true;this.onToolStateChange?.();
    const finish=error=>{if(this.mediaTrackMovePending!==request)return;this.mediaTrackMovePending=null;this.editPending=false;
      if(error && this.project?.id===request.projectId)this.canvas.title=error?.message || "Track placement was not saved. Review the edit and try again.";
      this.onToolStateChange?.();this.scheduleDraw();};
    try{const result=this.onMediaAction("layer_move",{clip_id:clipId,start:plan.patch.start,track_id:plan.patch.track_id});
      if(result?.then)Promise.resolve(result).then(()=>finish(),finish);else finish();}
    catch(error){finish(error);return false;}return true;
  }

  nativeMediaMove() { return typeof this.mediaMovePreview === "function"; }

  mediaMovePlan(clipId, start) {
    const protection = this.mediaProtectionIssue(clipId);
    if (protection) return {issue:protection,patch:null};
    if (this.editPending || !this.canEdit()) return { issue: "Wait for the current edit to finish.", patch: null };
    const clip = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])].find(item => item.id === clipId);
    if (this.sourceReview || !clip) return { issue: "This layer is no longer in the current edit.", patch: null };
    let plan;
    try { plan = this.mediaMovePreview?.(clipId, start); } catch { /* Never fall through to an unguarded legacy move. */ }
    const patch = plan?.patch, keys = patch && typeof patch === "object" && !Array.isArray(patch) ? Object.keys(patch) : null;
    if (!plan || typeof plan.issue !== "string" || (!plan.issue && (!keys || (keys.length && (keys.length !== 2
      || !keys.includes("start") || !keys.includes("end") || !Number.isFinite(patch.start) || !Number.isFinite(patch.end)
      || patch.start < -1e-9 || patch.end > timelineDuration(this.project) + 1e-9
      || Math.abs((patch.end - patch.start) - (clip.end - clip.start)) > 1e-8)))))
      return { issue: "Move readiness could not be confirmed. Try again after the edit refreshes.", patch: null };
    return plan;
  }

  mediaMoveStart(gesture, event) {
    const clip = gesture.media, length = clip.end - clip.start;
    // A purely vertical track gesture has no time intent. Keep the stored
    // fractional start exactly, without a float round-trip or nearby magnet.
    if(gesture.nativeTrack && this.timeFromEvent(event) === gesture.startTime)return clip.start;
    // Retain exact head/tail magnets and the existing full-occurrence bounds.
    // Only placement moves: never round the old duration or alter source clocks.
    return Math.max(0, Math.min(timelineDuration(this.project) - length,
      this.snappedTime(clip.start + this.timeFromEvent(event) - gesture.startTime, event, [0, length])));
  }

  moveMediaAt(clipId, start) {
    const plan = this.mediaMovePlan(clipId, start);
    if (!this.onMediaAction || plan.issue || !Number.isFinite(plan.patch?.start)) return false;
    const clip = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])].find(item => item.id === clipId);
    if (!clip || Math.abs(plan.patch.start - clip.start) <= 1e-9) return false;
    this.editPending = true; this.onToolStateChange?.();
    const finish = () => { this.editPending = false; this.onToolStateChange?.(); this.scheduleDraw(); };
    try {
      const result = this.onMediaAction('media_move', { clip_id: clipId, start: plan.patch.start });
      if (result?.then) Promise.resolve(result).then(finish, finish); else finish();
    } catch (error) { finish(); throw error; }
    return true;
  }

  mediaSlipPlan(clipId, sourceStart) {
    const protection = this.mediaProtectionIssue(clipId);
    if (protection) return {issue:protection,patch:null};
    if (this.editPending || !this.canEdit()) return { issue: "Wait for the current edit to finish.", patch: null };
    const clip = this.project?.manual?.media_clips?.find(item => item.id === clipId), kind = this.project?.assets?.[clip?.asset_id]?.kind;
    if (this.sourceReview || !clip || !["video", "audio"].includes(kind))
      return { issue: "Slip changes source content in imported video or audio only. Images and text have no source timing to slip.", patch: null };
    let plan;
    try { plan = this.mediaSlipPreview?.(clipId, sourceStart); } catch { /* A stale host must never become an approximate move. */ }
    const patch = plan?.patch;
    if (!plan || typeof plan.issue !== "string" || (!plan.issue && (!patch || typeof patch !== "object" || Array.isArray(patch)
      || Object.keys(patch).some(key => !["source_start", "video_source_start"].includes(key))
      || Object.values(patch).some(value => !Number.isFinite(value)))))
      return { issue: "Slip readiness could not be confirmed. Try again after the edit refreshes.", patch: null };
    return plan;
  }

  mediaSlipSourceStart(gesture, event) {
    // A slip moves no timeline boundary: magnets and timeline-end clamps do not
    // apply. Quantize the signed delta, preserving an existing fractional in.
    const delta = (event.clientX - gesture.clientX) / Math.max(gesture.px, .0001);
    const frame = sequenceFrame(this.project);
    return Number(gesture.media.source_start || 0) + Math.round(delta / frame) * frame;
  }

  slipMediaAt(clipId, sourceStart) {
    const plan = this.mediaSlipPlan(clipId, sourceStart);
    if (!this.onMediaAction || plan.issue) return false;
    this.editPending = true; this.onToolStateChange?.();
    const finish = () => { this.editPending = false; this.onToolStateChange?.(); this.scheduleDraw(); };
    try {
      const result = this.onMediaAction('media_slip', { clip_id: clipId, source_start: sourceStart });
      if (result?.then) Promise.resolve(result).then(finish, finish); else finish();
    } catch (error) { finish(); throw error; }
    return true;
  }

  nativeMediaTrim() { return typeof this.mediaTrimPreview === "function"; }

  mediaEdgeAt(clip, time) {
    const px = this.geometry().px;
    if ((clip.end - clip.start) * px < 22) return null;
    return Math.abs(time - clip.start) * px < 8 ? "start" : Math.abs(time - clip.end) * px < 8 ? "end" : null;
  }

  mediaTrimTime(gesture, event) {
    const time = this.snappedTime(gesture.media[gesture.edge] + this.timeFromEvent(event) - gesture.startTime, event);
    // Round only the dragged edge. Source availability and independent picture
    // bounds belong to the canonical host policy, never silent approximations.
    return Math.max(0, Math.min(timelineDuration(this.project), this.splitTime(time)));
  }

  mediaTrimPlan(clipId, edge, time) {
    const protection = this.mediaProtectionIssue(clipId);
    if (protection) return {issue:protection,patch:null};
    if (this.editPending || !this.canEdit()) return { issue: "Wait for the current edit to finish.", patch: null };
    let plan;
    try { if (this.nativeMediaTrim()) plan = this.mediaTrimPreview(clipId, edge, time); } catch { /* Fail closed on stale/unknown readiness. */ }
    if (!plan || typeof plan.issue !== "string" || (!plan.issue && (!plan.patch || typeof plan.patch !== "object" || Array.isArray(plan.patch))))
      return { issue: "Trim readiness could not be confirmed. Try again after the edit refreshes.", patch: null };
    return plan;
  }

  trimMediaAt(clipId, edge, time) {
    const plan = this.mediaTrimPlan(clipId, edge, time);
    if (!this.onMediaAction || plan.issue) return false;
    this.editPending = true; this.onToolStateChange?.();
    const finish = () => { this.editPending = false; this.onToolStateChange?.(); this.scheduleDraw(); };
    try {
      const result = this.onMediaAction('media_trim', { clip_id: clipId, edge, time });
      if (result?.then) Promise.resolve(result).then(finish, finish); else finish();
    } catch (error) { finish(); throw error; }
    return true;
  }

  mediaSplitReadiness(clipId, time) {
    const protection = this.mediaProtectionIssue(clipId);
    if (protection) return protection;
    if (this.project?.manual?.layer_tracks?.version >= 2 && typeof this.mediaSplitIssue !== "function") return "Split protection is unavailable in this editor.";
    if (this.editPending || !this.canEdit()) return "Wait for the current edit to finish.";
    const clip = [...(this.project?.manual?.media_clips || []), ...(this.project?.manual?.text_clips || [])].find(item => item.id === clipId);
    if (!clip) return "This layer is no longer in the current edit.";
    if (!Number.isFinite(time) || time - clip.start < .08 - 1e-9 || clip.end - time < .08 - 1e-9) return "Keep at least 0.08 seconds on each side of the split.";
    if (typeof this.mediaSplitIssue === "function") {
      let issue;
      try { issue = this.mediaSplitIssue(clipId, time); } catch { /* Unknown readiness must not advertise a safe split. */ }
      return typeof issue === "string" ? issue : "Split readiness could not be confirmed. Try again after the edit refreshes.";
    }
    return "";
  }

  splitMediaAt(clipId, time) {
    time = this.splitTime(time);
    if (!this.onMediaAction || this.mediaSplitReadiness(clipId, time)) return false;
    this.editPending = true;
    this.onToolStateChange?.();
    const finish = () => { this.editPending = false; this.onToolStateChange?.(); this.scheduleDraw(); };
    try {
      const result = this.onMediaAction('media_split', { clip_id: clipId, time });
      // The host reports failures. Keep repeated clicks from dispatching a
      // second edit while the first split is saving or refreshing its result.
      if (result?.then) Promise.resolve(result).then(finish, finish);
      else finish();
    } catch (error) { finish(); throw error; }
    return true;
  }

  canSplitAt(time) {
    if (this.lockedTargets().length) return false;
    time = this.splitTime(time);
    if (!this.project?.manual?.sequence || this.editTarget !== "edit") return this.canSplitClip(this.clipAt(time), time);
    // At an existing A cut, B can still run across the playhead (and vice
    // versa). Every crossing clip must split safely: a valid A split cannot
    // justify creating a sub-frame sliver on B. Exact boundaries and gaps do
    // not need another split, matching the backend's atomic Together action.
    const crossing = ["A", "B"].flatMap((slot) => this.project.sources?.[slot]
      ? (this.getTrackClips?.(this.project, slot) || []).filter((clip) => clip.start + 1e-9 < time && time < clip.end - 1e-9)
      : []);
    return crossing.length > 0 && crossing.every((clip) => this.canSplitClip(clip, time));
  }

  pointerDown(event) {
    if (this.trackLockPending) { this.canvas.title = "Wait for track protection to finish saving."; return; }
    if (event.button !== 0 || !this.project || this.gesture || this.editPending || this.mediaSelectionPending || !this.canEdit()) return;
    if (this.reviewMarkers && ["select","move"].includes(this.tool) && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      const y=event.clientY-this.canvas.getBoundingClientRect().top;
      if(y>=16 && y<=28 && this.reviewMarkers.hit(this.timeFromEvent(event),this.geometry().px)) { event.preventDefault(); this.canvas.focus?.({preventScroll:true}); return; }
    }
    event.preventDefault();
    this.canvas.focus?.({ preventScroll: true });
    try { this.canvas.setPointerCapture?.(event.pointerId); } catch (_) { /* A cancelled pointer may no longer be capturable. */ }
    const time = this.timeFromEvent(event);
    this.snapGuide = null;
    const media = this.mediaAtEvent(event);
    if ((event.ctrlKey || event.metaKey) && this.onMediaSelectionChange) {
      this.releasePointer(event.pointerId);
      if(media && ["select","move"].includes(this.tool) && !event.shiftKey) void this.toggleMediaSelection(media.clip.id);
      else this.canvas.title="Ctrl/Cmd-click adds imported media or custom text in Select/Move. Source A/B and automatic captions are not part of this selection.";
      return;
    }
    const ids=this.selectedMediaIds();
    if(media && ids.length>1 && ids.includes(media.clip.id) && !event.shiftKey){
      if(!["select","move"].includes(this.tool)){this.releasePointer(event.pointerId);this.canvas.title=`Select one layer for this tool. ${this.mediaGroupActionHint()}`;return;}
      const rows=[...(this.project.manual?.media_clips||[]),...(this.project.manual?.text_clips||[])];
      this.gesture={kind:"media_group",pointerId:event.pointerId,ids,clips:ids.map(id=>({...rows.find(clip=>clip.id===id)})),
        primary:media.clip.id,originalPrimary:this.mediaSelection,startTime:time,snapPlayhead:this.playhead,clientX:event.clientX,clientY:event.clientY,
        px:this.geometry().px,identity:this.mediaGroupIdentity(ids),trackId:media.row?.trackId,edge:this.mediaEdgeAt(media.clip,time),dragged:false,patches:[],delta:0};
      this.scheduleDraw();return;
    }
    if (media) {
      this.selectCaption(null, true);
      this.mediaSelection=media.clip.id; this.onMediaSelect?.(media.clip.id);
      if (this.tool === "slip") {
        this.hoverTime = time; this.updatePointerCursor(event, time);
        if (this.mediaSlipPlan(media.clip.id, Number(media.clip.source_start || 0)).issue) { this.releasePointer(event.pointerId); this.scheduleDraw(); return; }
        this.gesture = { kind: 'media_slip', pointerId: event.pointerId, media: { ...media.clip }, patch: {},
          clientX: event.clientX, clientY: event.clientY, px: this.geometry().px, dragged: false,
          previousSelection: this.selection ? { ...this.selection } : null, previousRangeSelection: this.selectionIsRange };
        this.scheduleDraw(); return;
      }
      if(this.tool==='blade'){
        this.hoverTime = this.splitTime(time); this.updatePointerCursor(event, time);
        this.gesture = { kind: 'media_blade', pointerId: event.pointerId, clipId: media.clip.id,
          clientX: event.clientX, clientY: event.clientY, dragged: false };
        this.scheduleDraw(); return;
      }
      const edge = this.mediaEdgeAt(media.clip, time);
      const protection = this.mediaProtectionIssue(media.clip.id) || (edge && this.project?.manual?.layer_tracks?.version >= 2 && !this.nativeMediaTrim() ? "Trim protection is unavailable in this editor." : "");
      if (protection) { this.releasePointer(event.pointerId); this.canvas.title = protection; this.canvas.style.cursor = "not-allowed"; this.scheduleDraw(); return; }
      this.gesture={kind:'media',pointerId:event.pointerId,media:{...media.clip},startTime:time,edge,patch:{},snapPlayhead:this.playhead,
        nativeTrim:Boolean(edge && this.nativeMediaTrim()), nativeTrack:Boolean(!edge && timelineLayerTrackState(this.project).enabled),
        nativeMove:Boolean(!edge && this.nativeMediaMove()), identity:this.mediaGroupIdentity([media.clip.id]),px:this.geometry().px,
        clientX:event.clientX,clientY:event.clientY,dragged:false,
        previousSelection:this.selection ? {...this.selection} : null,previousRangeSelection:this.selectionIsRange};this.scheduleDraw();return;
    }
    const caption = this.captionAtEvent(event);
    if (this.tool === "slip" && event.clientY - this.canvas.getBoundingClientRect().top >= 30) {
      if (caption) this.selectCaption(caption.item.id, true);
      this.hoverTime = time; this.updatePointerCursor(event, time);
      this.releasePointer(event.pointerId); this.scheduleDraw(); return;
    }
    if (caption) {
      this.selectCaption(caption.item.id, true);
      // Captions follow speech; Blade and range tools never cut them.
      if (this.tool !== 'select' && this.tool !== 'move') { this.releasePointer(event.pointerId); return; }
      this.gesture={kind:'caption',pointerId:event.pointerId,caption:{...caption.item},edge:caption.edge,startTime:time,patch:{},
        clientX:event.clientX,clientY:event.clientY,dragged:false,snapPlayhead:this.playhead};
      this.canvas.style.cursor = caption.edge ? 'ew-resize' : 'grab';
      this.scheduleDraw(); return;
    }
    this.selectCaption(null, true);
    this.mediaSelection=null;
    this.hoverTime = time;
    const target = this.targetAtEvent(event);
    // Editing scope is an explicit choice. Merely touching B must not turn a
    // Together operation into B-only (or silently change an A-only edit).
    if (target != null && !this.project?.manual?.sequence) this.setEditTarget(target);
    const lane = this.inEditLane(event);
    const selectionArea = this.inSelectionArea(event);
    const edge = !event.shiftKey && !["blade", "remove_between", "move"].includes(this.tool) ? this.selectionEdge(event, time) : null;
    this.selectionCursor = null;
    this.selectionAnchor = null;
    this.gesture = { pointerId: event.pointerId, previousSelection: this.selection ? { ...this.selection } : null, clientX: event.clientX, clientY: event.clientY, startTime: time, snapPlayhead: this.playhead, kind: "scrub" };
    this.gesture.previousRangeSelection = this.selectionIsRange;
    const trimEdge = this.trimEdgeAt(event,time);
    if (lane && this.lockedTargets().length && this.tool !== "range" && !event.shiftKey) {
      this.gesture.kind = "locked";
      this.setSelection(this.selectableRangeAt(time), false);
    } else if (trimEdge) {
      this.gesture.kind = "trim"; this.gesture.edge = trimEdge;
      this.gesture.clip = {...this.trimTarget()}; this.gesture.target = this.editTarget;
    } else if (lane && !event.shiftKey && (this.tool === "move" || (this.project?.manual?.sequence && this.tool === "select")) && (this.editTarget !== "edit" || this.project?.manual?.sequence) && this.clipAt(time)) {
      this.gesture.kind = "move";
      this.gesture.target = this.editTarget;
      this.gesture.rangeMove = Boolean(this.project?.manual?.sequence && this.selectionIsRange && this.selection && time >= this.selection.start && time < this.selection.end);
      this.gesture.clip = this.gesture.rangeMove ? { ...this.selection } : this.clipAt(time);
      this.setSelection(this.gesture.clip, false, this.gesture.rangeMove);
    } else if (edge) {
      this.gesture.kind = "edge";
      this.gesture.edge = edge;
      this.selecting = true;
      this.scrubbing = false;
    } else if (lane && this.tool === "remove_between" && !event.shiftKey) {
      this.gesture.kind = "remove_between";
    } else if (event.shiftKey || (selectionArea && this.tool === "range")) {
      this.gesture.kind = "range";
      this.selecting = true;
      this.scrubbing = false;
      this.selectionAnchor = this.snappedTime(time, event);
      this.selection = null;
    } else if (lane && this.tool === "blade") {
      this.gesture.kind = "blade";
      this.gesture.target = this.editTarget;
      this.gesture.clip = this.clipAt(time);
    } else if (selectionArea && this.tool === "select") {
      const scene = this.inLayoutLane(event) ? this.layoutAt(time) : null;
      this.gesture.kind = scene ? "layout" : "clip";
      this.gesture.layout = scene;
      // Publish only on release. Showing a trim inspector on pointerdown can
      // move the canvas under the pointer halfway through a selection gesture.
      this.setSelection(scene || this.selectableRangeAt(time), false);
    } else {
      this.scrubbing = true;
      this.selecting = false;
    }
    this.seekGesture(time);
    this.updatePointerCursor(event, time);
    this.scheduleDraw();
  }

  pointerMove(event) {
    if (this.cancelProtectedGesture()) return;
    if (this.gesture && this.gesture.pointerId !== event.pointerId) return;
    this.snapGuide = null;
    if (this.gesture?.kind === 'media_slip') {
      const g = this.gesture;
      // Changing zoom/resizing mid-drag changes pointer scale; cancel rather
      // than silently saving a different amount of source content.
      if (Math.abs(this.geometry().px - g.px) > .000001) { this.cancelGesture(); return; }
      if (Math.hypot(event.clientX - g.clientX, event.clientY - g.clientY) > 6) g.dragged = true;
      if (!g.dragged) return;
      const sourceStart = this.mediaSlipSourceStart(g, event), plan = this.mediaSlipPlan(g.media.id, sourceStart);
      g.sourceStart = sourceStart; g.slipIssue = plan.issue; g.patch = plan.issue ? {} : { ...plan.patch };
      const delta = sourceStart - Number(g.media.source_start || 0), signed = `${delta < 0 ? "−" : "+"}${Math.abs(delta).toFixed(3)} s`;
      const picture = Number.isFinite(g.patch.video_source_start) ? ` · Picture in ${g.patch.video_source_start.toFixed(3)} s` : "";
      const label = plan.issue ? `Slip blocked: ${plan.issue}` : `Slip ${signed} · Source in ${sourceStart.toFixed(3)} s${picture} · Timing fixed`;
      this.hoverTime = this.timeFromEvent(event);
      this.mediaSlipHover = { time: this.hoverTime, label, showTime: false };
      this.canvas.title = label; this.canvas.style.cursor = plan.issue ? "not-allowed" : "ew-resize";
      this.onMediaPreview?.(g.media.id, plan.issue ? null : g.patch);
      this.scheduleDraw(); return;
    }
    if (this.gesture?.kind === 'media_blade') {
      const g = this.gesture, time = this.splitTime(this.timeFromEvent(event));
      if (Math.hypot(event.clientX-g.clientX, event.clientY-g.clientY) > 6) g.dragged = true;
      this.hoverTime = time; this.updatePointerCursor(event, time);
      if (g.dragged || this.mediaAtEvent(event)?.clip.id !== g.clipId) {
        this.bladeHover = { time, label: "Split cancelled: click the layer without dragging." };
        this.canvas.title = this.bladeHover.label; this.canvas.style.cursor = "not-allowed";
      }
      this.scheduleDraw(); return;
    }
    if (this.gesture?.kind === 'caption') {
      const g = this.gesture;
      if (Math.hypot(event.clientX-g.clientX,event.clientY-g.clientY) > 6) g.dragged = true;
      if (!g.dragged) return; // A click selects; it never nudges the caption.
      // Whole output frames: a pixel of hand jitter is never a timing change.
      const frame = sequenceFrame(this.project);
      const item = g.caption, delta = Math.round((this.timeFromEvent(event)-g.startTime)/frame)*frame, limit = timelineDuration(this.project);
      let start = Number(item.start), end = Number(item.end);
      if (g.edge === 'start') start = Math.max(0, Math.min(end-MIN_CAPTION_SECONDS, this.snappedTime(start+delta,event)));
      else if (g.edge === 'end') end = Math.max(start+MIN_CAPTION_SECONDS, Math.min(limit, this.snappedTime(end+delta,event)));
      else {
        const length = end-start;
        start = Math.max(0, Math.min(limit-length, this.snappedTime(start+delta,event,[0,length])));
        end = start+length;
      }
      this.validateSnap(g.edge ? [g.edge === 'start' ? start : end] : [start,end]);
      g.patch = {start,end};
      this.canvas.style.cursor = g.edge ? 'ew-resize' : 'grabbing';
      this.scheduleDraw(); return;
    }
    if(this.gesture?.kind==="media_group"){
      const g=this.gesture;
      if(this.mediaGroupIdentity(g.ids)!==g.identity || JSON.stringify(this.selectedMediaIds())!==JSON.stringify(g.ids)
        || this.mediaSelection!==g.originalPrimary || Math.abs(this.geometry().px-g.px)>1e-6 || !this.canEdit()){this.cancelGesture();return;}
      if(Math.hypot(event.clientX-g.clientX,event.clientY-g.clientY)>6)g.dragged=true;
      if(!g.dragged)return;
      const target=this.mediaRowAtEvent(event),rowChanged=Boolean(g.trackId && target?.trackId!==g.trackId),delta=this.mediaGroupDelta(g,event),
        plan=g.edge?{issue:"Select one layer to trim. Group moves use the clip body.",patches:null}:rowChanged
          ?this.mediaGroupRelocatePlan(g.ids,g.primary,delta,target?.trackId):this.mediaGroupPlan(g.ids,delta);
      g.relocating=rowChanged;g.targetTrackId=rowChanged?target?.trackId:null;
      g.delta=Number.isFinite(plan.delta)?plan.delta:delta;g.moveIssue=plan.issue;g.patches=plan.issue?[]:plan.patches;
      this.hoverTime=Math.min(...g.clips.map(clip=>clip.start))+g.delta;
      this.mediaMoveHover={time:this.hoverTime,label:plan.issue?`Move blocked: ${plan.issue}`:g.relocating
        ?`Move ${g.ids.length} layers between tracks - Program remains saved until release`:`Move ${g.ids.length} layers together · No ripple`};
      this.canvas.title=plan.issue || (g.relocating
        ? `Move ${g.ids.length} selected layers between saved tracks. Track spacing, timing offsets and duration stay unchanged. Program preview remains saved until release.`
        : `Move ${g.ids.length} selected layers together. Their offsets, content and timeline duration stay unchanged.`);
      this.canvas.style.cursor=plan.issue?"not-allowed":"grabbing";
      if(plan.issue)this.snapGuide=null;else this.validateSnap(g.patches.flatMap(patch=>[patch.start,patch.end]));
      this.onMediaGroupPreview?.(plan.issue?null:g.patches);this.scheduleDraw();return;
    }
    if(this.gesture?.kind==='media') {
      if(this.gesture.nativeTrack && this.mediaGroupIdentity([this.gesture.media.id])!==this.gesture.identity){this.cancelGesture();return;}
      if ((this.gesture.nativeMove || this.gesture.nativeTrack) && Math.abs(this.geometry().px - this.gesture.px) > .000001) { this.cancelGesture(); return; }
      if (Math.hypot(event.clientX-this.gesture.clientX,event.clientY-this.gesture.clientY)>6) this.gesture.dragged=true;
      if (!this.gesture.dragged) return; // Selecting near a magnet must not edit the media.
      if(this.gesture.nativeTrack){
        const g=this.gesture,start=this.mediaMoveStart(g,event),row=this.mediaRowAtEvent(event),plan=this.mediaTrackPlan(g.media.id,start,row?.trackId);
        g.moveIssue=plan.issue;g.patch=plan.issue?{}:{...plan.patch};g.moveStart=Number.isFinite(g.patch.start)?g.patch.start:g.media.start;
        g.moveTrackId=g.patch.track_id || g.media.track_id;this.hoverTime=start;
        const label=plan.issue?`Move blocked: ${plan.issue}`:`Move to ${row.label} — No ripple`;
        this.mediaMoveHover={time:start,label};this.canvas.title=label;this.canvas.style.cursor=plan.issue?"not-allowed":"grabbing";
        if(plan.issue)this.snapGuide=null;else this.validateSnap([g.patch.start,g.patch.end]);this.scheduleDraw();return;
      }
      if (this.gesture.nativeTrim) {
        const g = this.gesture, time = this.mediaTrimTime(g, event), plan = this.mediaTrimPlan(g.media.id, g.edge, time);
        g.trimTime = time; g.trimIssue = plan.issue; g.patch = plan.issue ? {} : { ...plan.patch };
        this.hoverTime = time;
        this.mediaTrimHover = { time: this.hoverTime, label: plan.issue ? `Trim blocked: ${plan.issue}` : `Trim ${g.edge}` };
        this.canvas.title = plan.issue || `Trim this layer's ${g.edge} to ${formatFrameTime(this.hoverTime, 1 / sequenceFrame(this.project))}. Other layers and timeline duration stay unchanged.`;
        this.canvas.style.cursor = plan.issue ? "not-allowed" : "ew-resize";
        if (plan.issue) this.snapGuide = null; else this.validateSnap([time]);
        // An unsupported edit never paints an approximation as if it were saved.
        this.onMediaPreview?.(g.media.id, plan.issue ? null : g.patch);
        this.scheduleDraw(); return;
      }
      if (this.gesture.nativeMove) {
        const g = this.gesture, start = this.mediaMoveStart(g, event), plan = this.mediaMovePlan(g.media.id, start);
        g.moveIssue = plan.issue; g.patch = plan.issue ? {} : { ...plan.patch };
        g.moveStart = Number.isFinite(g.patch.start) ? g.patch.start : g.media.start;
        this.hoverTime = start;
        const label = plan.issue ? `Move blocked: ${plan.issue}` : "Move layer · Content and duration fixed · No ripple";
        this.mediaMoveHover = { time: start, label };
        this.canvas.title = plan.issue || `Move this layer to ${formatFrameTime(g.moveStart, 1 / sequenceFrame(this.project))}. Content, duration and other layers stay unchanged; no ripple.`;
        this.canvas.style.cursor = plan.issue ? "not-allowed" : "grabbing";
        if (plan.issue) this.snapGuide = null; else this.validateSnap([g.patch.start, g.patch.end]);
        this.onMediaPreview?.(g.media.id, plan.issue ? null : g.patch);
        this.scheduleDraw(); return;
      }
      const g=this.gesture,clip=g.media,delta=this.timeFromEvent(event)-g.startTime,limit=timelineDuration(this.project);
      const asset=this.project.assets?.[clip.asset_id],timed=!clip.id?.startsWith('text_') && asset?.kind!=='image',sourceStart=Number(clip.source_start)||0;
      let patch;
      if(g.edge==='start') {
        const start=Math.max(0,timed ? clip.start-sourceStart : 0,Math.min(clip.end-.08,this.snappedTime(clip.start+delta,event)));
        patch={start};
        if(timed)patch.source_start=sourceStart+start-clip.start;
        if(asset?.kind==='video')patch.video_source_start=Math.max(0,Number(clip.video_source_start ?? sourceStart)+(start-clip.start)*(clip.speed||1));
      }
      else if(g.edge==='end') {
        const available=Number(asset?.duration),maximum=timed ? (Number.isFinite(available) ? Math.min(limit,clip.start+available-sourceStart) : clip.end) : limit;
        patch={end:Math.max(clip.start+.08,Math.min(maximum,this.snappedTime(clip.end+delta,event)))};
      }
      else {const start=Math.max(0,Math.min(limit-(clip.end-clip.start),this.snappedTime(clip.start+delta,event,[0,clip.end-clip.start])));patch={start,end:start+clip.end-clip.start};}
      this.validateSnap(g.edge ? [patch[g.edge]] : [patch.start,patch.end]);
      const length=(patch.end ?? clip.end)-(patch.start ?? clip.start),fadeIn=Number(clip.fade_in)||0,fadeOut=Number(clip.fade_out)||0;
      if(g.edge && fadeIn+fadeOut>length) {
        const scale=length/(fadeIn+fadeOut);patch.fade_in=fadeIn*scale;patch.fade_out=fadeOut*scale;
      }
      g.patch=patch;this.onMediaPreview?.(clip.id,patch);this.scheduleDraw();return;
    }
    const time = this.timeFromEvent(event);
    this.hoverTime = time;
    if (this.gesture && Math.hypot(event.clientX - this.gesture.clientX, event.clientY - this.gesture.clientY) > 6) this.gesture.dragged = true;
    // A click cuts; dragging an existing cut moves that clip even while Blade
    // is selected. Do not silently swallow a user's drag in the cutting tool.
    if (this.project?.manual?.sequence && this.gesture?.kind === "blade" && this.gesture.dragged && this.gesture.clip) {
      this.gesture.kind = "move";
      this.setSelection(this.gesture.clip, false);
    }
    this.updatePointerCursor(event, time);
    if (this.gesture?.kind === "trim") {
      const {clip,edge} = this.gesture;
      this.gesture.trimTime = this.trimEdgeTime(clip,edge,this.snappedTime(time,event));
      this.validateSnap([this.gesture.trimTime]);
      this.setSelection({...clip,[edge]:this.gesture.trimTime},false);
    }
    if (this.gesture?.kind === "move") {
      const clip = this.gesture.clip, duration = this.geometry().duration;
      let maximum = this.project?.manual?.sequence ? duration : duration - (clip.end - clip.start);
      let destination = this.snappedTime(clip.start + time - this.gesture.startTime, event);
      if (this.project?.manual?.sequence) {
        // Pixel distances rarely land on exact frame boundaries. Quantize the
        // drop so a near-end reorder cannot leave a tiny unrenderable sliver.
        const frame = sequenceFrame(this.project);
        destination = Math.round(destination / frame) * frame;
      }
      const start = Math.max(0, Math.min(maximum, destination));
      this.gesture.moveStart = this.project?.manual?.sequence
        ? rippleMoveStart(this.project,clip.start,clip.end,start,this.editTarget === "edit" ? null : this.editTarget,this.getTrackClips)
        : start;
      this.gesture.collision = !this.project?.manual?.sequence && this.targetClips().some((other) => other.id !== clip.id && other.start < start + clip.end - clip.start - .000001 && other.end > start + .000001);
      this.validateSnap(this.gesture.collision ? [] : [this.gesture.moveStart]);
    }
    if (["clip", "layout"].includes(this.gesture?.kind) && Math.abs(event.clientX - this.gesture.clientX) > 3) {
      this.gesture.kind = "range";
      this.selectionAnchor = this.snappedTime(this.gesture.startTime, event);
      this.selecting = true;
    }
    if (this.scrubbing || ["range", "edge", "blade", "remove_between"].includes(this.gesture?.kind)) this.seekGesture(time);
    if (this.gesture?.kind === "range" && this.selectionAnchor != null) {
      this.setSelection({ start: this.selectionAnchor, end: this.snappedTime(time, event) }, false, true);
      this.validateSnap(this.selection ? [this.selection.start, this.selection.end] : []);
    }
    if (this.gesture?.kind === "edge") {
      const previous = this.gesture.previousSelection;
      const snapped = this.snappedTime(time, event);
      const minimum = this.project?.manual?.sequence ? 1 / 60 : .031;
      const next = this.gesture.edge === "start"
        ? { start: Math.min(snapped, previous.end - minimum), end: previous.end }
        : { start: previous.start, end: Math.max(snapped, previous.start + minimum) };
      this.setSelection(next, false, true);
      this.validateSnap(this.selection ? [this.selection[this.gesture.edge]] : []);
    }
    this.scheduleDraw();
  }

  pointerUp(event) {
    const gesture = this.gesture;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if (gesture.kind === "media_group") {
      this.pointerMove(event);if(this.gesture!==gesture)return;
      this.gesture=null;this.releasePointer(event.pointerId);this.snapGuide=null;this.onMediaGroupPreview?.(null);this.clearMediaMoveHover();
      if(gesture.dragged && !gesture.moveIssue && gesture.relocating)
        this.relocateMediaGroup(gesture.ids,gesture.primary,gesture.delta,gesture.targetTrackId);
      else if(gesture.dragged && !gesture.moveIssue && Math.abs(gesture.delta)>1e-9)this.moveMediaGroup(gesture.ids,gesture.delta);
      else if(!gesture.dragged){this.mediaSelection=gesture.primary;this.onMediaSelect?.(gesture.primary);}
      this.scheduleDraw();return;
    }
    if (gesture.kind === 'media_slip') {
      this.pointerMove(event);
      if (this.gesture !== gesture) return;
      this.gesture = null; this.releasePointer(event.pointerId); this.snapGuide = null;
      this.onMediaPreview?.(gesture.media.id, null); this.clearMediaSlipHover();
      const changed = Number.isFinite(gesture.sourceStart) && Math.abs(gesture.sourceStart - Number(gesture.media.source_start || 0)) > 1e-9;
      if (gesture.dragged && changed && !gesture.slipIssue) this.slipMediaAt(gesture.media.id, gesture.sourceStart);
      this.scheduleDraw(); return;
    }
    if (gesture.kind === 'media_blade') {
      this.pointerMove(event);
      const hit = this.mediaAtEvent(event), time = this.splitTime(this.timeFromEvent(event));
      this.gesture = null; this.releasePointer(event.pointerId);
      if (!gesture.dragged && hit?.clip.id === gesture.clipId) this.splitMediaAt(gesture.clipId, time);
      this.updatePointerCursor(event, time); this.scheduleDraw(); return;
    }
    if (gesture.kind === 'caption') {
      this.pointerMove(event);
      this.gesture = null; this.snapGuide = null; this.releasePointer(event.pointerId);
      this.canvas.style.cursor = '';
      const {caption,patch} = gesture;
      if (gesture.dragged && Number.isFinite(patch.start)) {
        const {start,end} = patch;
        if ((Math.abs(start-caption.start) > 1e-4 || Math.abs(end-caption.end) > 1e-4) && this.canEdit() && !this.editPending)
          Promise.resolve(this.onCaptionEdit?.(caption.id,{start,end})).catch(()=>{});
      }
      this.scheduleDraw(); return;
    }
    if(this.gesture?.kind==='media') {
      this.pointerMove(event);
      if (this.gesture !== gesture) return;
      const g=this.gesture;this.gesture=null;this.releasePointer(event.pointerId);if(!g.nativeTrack)this.onMediaPreview?.(g.media.id,null);
      this.snapGuide=null;
      if(g.nativeTrack){
        this.clearMediaMoveHover();
        const changed=g.moveTrackId!==g.media.track_id || (Number.isFinite(g.moveStart)&&Math.abs(g.moveStart-g.media.start)>1e-9);
        if(g.dragged && changed && !g.moveIssue)this.moveMediaToTrack(g.media.id,g.moveStart,g.moveTrackId);
        this.scheduleDraw();return;
      }
      if (g.nativeTrim) {
        this.clearMediaTrimHover();
        const changed = Number.isFinite(g.trimTime) && Math.abs(g.trimTime - g.media[g.edge]) > 1e-9;
        if (g.dragged && changed && !g.trimIssue) this.trimMediaAt(g.media.id, g.edge, g.trimTime);
        this.scheduleDraw(); return;
      }
      if (g.nativeMove) {
        this.clearMediaMoveHover();
        const changed = Number.isFinite(g.moveStart) && Math.abs(g.moveStart - g.media.start) > 1e-9;
        if (g.dragged && changed && !g.moveIssue) this.moveMediaAt(g.media.id, g.moveStart);
        this.scheduleDraw(); return;
      }
      // The server derives the independent picture in-point from source_start.
      // Keep that preview-only value out of the public media_update payload.
      const patch={...g.patch};delete patch.video_source_start;
      const changed=Object.entries(patch).some(([key,value])=>Math.abs(value-Number(g.media[key]||0))>1e-9);
      if(changed && this.canEdit() && !this.editPending)Promise.resolve(this.onMediaEdit?.(g.media.id,patch)).catch(()=>{});
      this.scheduleDraw();return;
    }
    // Some devices coalesce the last pointermove into pointerup. Commit the
    // actual release position instead of leaving the preview one frame behind.
    this.pointerMove(event);
    this.gesture = null;
    this.snapGuide = null;
    this.scrubbing = false;
    this.selecting = false;
    this.selectionAnchor = null;
    this.releasePointer(event.pointerId);
    if (gesture.kind === "trim") {
      if (gesture.dragged && Number.isFinite(gesture.trimTime) && Math.abs(gesture.trimTime-gesture.clip[gesture.edge])>1e-6) {
        this.onEdit?.({action:"sequence_trim_edge",start:gesture.clip.start,end:gesture.clip.end,edge:gesture.edge,time:gesture.trimTime,...(gesture.target !== "edit" ? {slot:gesture.target} : {})});
      } else this.setSelection(gesture.previousSelection,false);
    }
    if (gesture.kind === "move") {
      this.onSelectionChange?.(this.selection, {kind:gesture.kind});
      if (gesture.dragged && !gesture.collision && Number.isFinite(gesture.moveStart) && Math.abs(gesture.moveStart - gesture.clip.start) > .001) {
        this.onEdit?.(gesture.target === "edit" || gesture.rangeMove
          ? { action: "sequence_move_range", start: gesture.clip.start, end: gesture.clip.end, to: gesture.moveStart, ...(gesture.target !== "edit" ? { slot: gesture.target } : {}) }
          : { action: "track_move", slot: gesture.target, clip_id: gesture.clip.id, start: gesture.moveStart });
      }
    }
    if (["range", "edge", "clip", "layout", "locked"].includes(gesture.kind)) this.onSelectionChange?.(this.selection, {kind:gesture.kind});
    if (gesture.kind === "layout" && !gesture.dragged && this.canEdit()) this.onLayoutSelect?.({ ...gesture.layout });
    if (gesture.kind === "remove_between" && !gesture.dragged && this.inEditLane(event)) this.cutOutAt(this.timeFromEvent(event));
    if (gesture.kind === "blade" && !gesture.dragged && this.inEditLane(event) && this.canEdit()) {
      const time = this.splitTime(this.timeFromEvent(event));
      if (this.canSplitAt(time)) this.onEdit?.({ action: "split", time, ...(this.editTarget !== "edit" || this.project?.manual?.sequence ? { target: this.editTarget } : {}) });
    }
    this.scheduleDraw();
  }

  keyDown(event) {
    if (!this.project || event.defaultPrevented || event.isComposing || event.keyCode === 229) return;
    if (event.key === "Escape" && this.cancelGesture()) {
      event.preventDefault();
      event.stopPropagation?.();
      return;
    }
    if (event.key === "Escape" && this.cancelPendingCut()) {
      event.preventDefault(); event.stopPropagation?.(); return;
    }
    if (event.key === "Escape" && this.captionSelection) {
      event.preventDefault(); event.stopPropagation?.(); this.selectCaption(null, true); return;
    }
    if(event.key==="Escape" && (this.selectedMediaIds().length>1 || this.mediaSelectionPending)){
      event.preventDefault();event.stopPropagation?.();void this.requestMediaSelection([],null);return;
    }
    if (!this.canEdit() || this.editPending || this.trackLockPending || this.mediaSelectionPending || event.ctrlKey || event.metaKey || event.altKey) return;
    if(this.selectedMediaIds().length>1 && ["Delete","Backspace","Enter"].includes(event.key)){
      event.preventDefault();event.stopPropagation?.();
      if(event.key==="Enter")this.canvas.title=this.mediaGroupActionHint();
      else if(!event.repeat)this.removeMediaGroup();
      return;
    }
    if (this.captionSelection && ['Delete','Backspace','Enter'].includes(event.key)) {
      event.preventDefault(); event.stopPropagation?.();
      const item = this.captionItems()?.find(entry => entry.id === this.captionSelection);
      if (event.repeat || !item) return;
      if (event.key === 'Enter') this.onCaptionOpen?.(item.id);
      else if (!item.hidden) this.onCaptionAction?.('caption_visibility',{caption_id:item.id,hidden:true});
      return;
    }
    if(this.mediaSelection && ['Delete','Backspace'].includes(event.key)) {
      event.preventDefault();event.stopPropagation?.();
      const protection=this.mediaProtectionIssue(this.mediaSelection);
      if(protection){this.canvas.title=protection;return;}
      if(!event.repeat)this.onMediaAction?.('media_remove',{clip_id:this.mediaSelection});return;
    }
    if (event.key === "Enter" && !event.shiftKey && this.tool === "remove_between") {
      event.preventDefault(); event.stopPropagation?.();
      if (!event.repeat) this.cutOutAt(this.playhead);
      return;
    }
    // The host handles profile navigation in its capture-phase listener. Do
    // not reintroduce NLE arrow meanings into an audio-editor profile here.
    if (this.canvas.dataset?.editorShortcuts === "on" && event.key !== "Escape" && !event.shiftKey) return;
    const duration = timelineDuration(this.project);
    const step = event.altKey ? .1 : Math.max(.25, Math.min(5, duration / 120));
    let next = event.shiftKey && this.selectionCursor != null ? this.selectionCursor : this.playhead;
    if (event.key === "ArrowLeft") next -= step;
    else if (event.key === "ArrowRight") next += step;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = duration;
    else if (event.key === "Escape" && this.selection) {
      event.preventDefault();
      event.stopPropagation?.();
      this.clearSelection(true);
      return;
    } else return;
    event.preventDefault();
    event.stopPropagation?.();
    next = Math.max(0, Math.min(duration, next));
    if (event.shiftKey) {
      this.mediaSelection=null;
      if (this.selectionAnchor == null) this.selectionAnchor = this.selection?.start ?? this.playhead;
      this.setSelection({ start: this.selectionAnchor, end: next }, true);
      this.selectionCursor = next;
      this.onSeek?.(next);
    } else {
      this.selectionAnchor = null;
      this.selectionCursor = null;
      this.onSeek?.(next);
    }
  }

  handleWheel(event) {
    if (event.ctrlKey || event.metaKey || event.altKey) {
      event.preventDefault();
      const factor = event.deltaY < 0 ? 1.18 : 1 / 1.18;
      this.setZoom(this.zoom * factor);
      return;
    }
    if (this.zoom > 1 || event.shiftKey) {
      event.preventDefault();
      this.scroll.scrollLeft += event.deltaX + event.deltaY;
    }
  }
}

// The disclosure is a read-only impact preview, not a second Delete command.
// A separate readiness callback is required so an older host cannot advertise
// mixed-layer behavior it does not implement. No source-review clock changes.
export function createTimelineRangeImpact(timeline) {
  const doc = timeline.canvas?.ownerDocument, bar = timeline.navigation?.bar;
  if (timeline.sourceReview || !bar || !doc?.createElement || !doc.body || typeof timeline.rangeDeleteIssue !== "function") return null;
  const make = (tag, className, text) => {
    const node = doc.createElement(tag); if (className) node.className = className;
    if (text != null) node.textContent = text; return node;
  };
  const details = make("details", "timeline-range-impact"), summary = make("summary"),
    panel = make("div", "timeline-range-impact-panel"), heading = make("h3"),
    explanation = make("p", "timeline-range-impact-explanation"), issue = make("p", "timeline-range-impact-issue"),
    list = make("ul", "timeline-range-impact-list"), note = make("p", "timeline-range-impact-note");
  details.id = "timelineRangeImpact"; details.hidden = true;
  panel.id = "timelineRangeImpactDetails"; panel.hidden = true; summary.setAttribute("aria-controls", panel.id);
  panel.append(heading, explanation, issue, list, note); details.append(summary); doc.body.append(panel);
  bar.insertBefore(details, bar.querySelector?.(".timeline-timecode-form") || null);
  let lastProject, lastSignature, destroyed = false;
  const setText = (node, text) => { if (node.textContent !== text) node.textContent = text; };
  const position = () => {
    if (typeof bar.getClientRects === "function" && !bar.getClientRects().length) details.open = false;
    panel.hidden = details.hidden || !details.open;
    if (panel.hidden) return;
    // The timeline dock clips its canvas. Portal only this read-only disclosure
    // outside that clip, keeping it anchored above the navigation controls.
    const rect = bar.getBoundingClientRect(), height = doc.defaultView?.innerHeight || 800,
      above = Math.max(0, rect.top - 14), below = Math.max(0, height - rect.bottom - 14), useAbove = above >= 140 || above >= below;
    if (useAbove) { panel.style.top = "auto"; panel.style.bottom = `${Math.max(8, height - rect.top + 6)}px`; }
    else { panel.style.bottom = "auto"; panel.style.top = `${Math.max(8, rect.bottom + 6)}px`; }
    panel.style.maxHeight = `${Math.max(60, Math.min(260, useAbove ? above : below))}px`;
  };
  const sync = (force = false) => {
    if (destroyed) return;
    const p = timeline.project, range = timeline.selection, target = timeline.editTarget,
      signature = [p?.revision, range?.start, range?.end, target, timeline.mediaSelection, timeline.captionSelection,
        Boolean(timeline.editPending), Boolean(timeline.canEdit?.())].join("|");
    if (!force && lastProject === p && lastSignature === signature) { position(); return; }
    if (lastProject?.id !== p?.id) details.open = false;
    lastProject = p; lastSignature = signature;
    const impact = !timeline.mediaSelection && !timeline.captionSelection ? timelineRangeDeleteImpact(p, range, target, timeline.getTrackClips) : null;
    if (!impact) { details.hidden = true; details.open = false; position(); return; }
    let reason;
    try { reason = timeline.rangeDeleteIssue(impact.start, impact.end, impact.target); } catch { reason = null; }
    if (typeof reason !== "string") reason = "Cut out readiness could not be confirmed. Review the current edit before trying again.";
    const fps = Math.round(1 / sequenceFrame(p)), time = value => formatFrameTime(value, fps),
      scope = target === "edit" ? "Together" : `Video ${target} only`;
    details.hidden = false; details.dataset.state = reason ? "blocked" : "preview";
    setText(summary, reason ? "Cut out blocked" : target === "edit" ? `Cut out preview · −${(impact.end - impact.start).toFixed(2)} s` : `Cut out preview · ${target} only`);
    setText(heading, `${scope} · ${time(impact.start)}–${time(impact.end)}`);
    setText(explanation, target === "edit"
      ? `Cut out removes ${time(impact.removedTime)} of edit time. Later footage, framing and added layers move earlier. Duration: ${time(impact.durationBefore)} → ${time(impact.durationAfter)}.`
      : `Cut out removes only ${target} footage in this range and leaves a gap. Timeline duration stays ${time(impact.durationBefore)}. Other sources, added media and text stay at their current times.`);
    setText(issue, reason); issue.hidden = !reason;
    const rows = Object.entries(impact.sources).map(([slot, counts]) => [`Video ${slot}`, counts]);
    if (target === "edit") rows.push(["Imported media / audio", impact.media], ["Custom titles / captions", impact.text]);
    list.replaceChildren();
    for (const [label, counts] of rows) {
      const changes = [["removed", "removed"], ["trimmed", "trimmed"], ["split", "split"], ["shifted", "moved earlier"], ["unknown", "with unreadable timing"]]
        .filter(([key]) => counts[key]).map(([key, word]) => `${counts[key]} ${word}`);
      list.append(make("li", "", `${label}: ${changes.length ? changes.join(", ") : "no changes"}.`));
    }
    setText(note, reason ? "This is a preview, not an edit. Resolve the reason above before cutting out. Original files are unchanged."
      : "Counts refer to timeline occurrences, not files. Cut out is one undoable edit; imported files stay in the Media pool. Automatic captions follow retained source footage. Server checks still apply.");
    summary.title = reason || `${scope}: preview what the existing Cut out command would change. Opening this panel changes nothing.`;
    position();
  };
  const toggle = () => { if (details.open) sync(true); else position(); };
  const keydown = event => {
    if (event.key !== "Escape" || !details.open) return;
    event.preventDefault(); event.stopPropagation(); details.open = false; position(); summary.focus({ preventScroll: true });
  };
  const outside = event => { if (details.open && !details.contains(event.target) && !panel.contains(event.target)) { details.open = false; position(); } };
  details.addEventListener("toggle", toggle); details.addEventListener("keydown", keydown); panel.addEventListener("keydown", keydown);
  doc.addEventListener("pointerdown", outside); doc.defaultView?.addEventListener?.("resize", position);
  const workspace = timeline.scroll?.closest?.(".studio-workspace"), Observer = doc.defaultView?.MutationObserver,
    observer = workspace && typeof Observer === "function" ? new Observer(position) : null;
  observer?.observe(workspace, { attributes: true, attributeFilter: ["hidden", "class"] });
  sync(true);
  return { details, summary, panel, sync, refresh: () => sync(true), destroy() {
    destroyed = true; details.removeEventListener("toggle", toggle); details.removeEventListener("keydown", keydown); panel.removeEventListener("keydown", keydown);
    doc.removeEventListener("pointerdown", outside); doc.defaultView?.removeEventListener?.("resize", position); details.remove(); panel.remove();
    observer?.disconnect();
  } };
}

// A small DOM companion to the canvas. It calls the same seek/selection paths
// as timeline gestures; it never edits the project, imports media or runs AI.
// Source Review retains its own controls and source clock.
function createTimelineNavigation(timeline) {
  const doc = timeline.canvas.ownerDocument, dock = timeline.scroll.closest?.(".studio-timeline-dock");
  if (timeline.sourceReview || timeline.canvas.id !== "timelineCanvas" || !doc?.createElement || !dock) return null;
  const make = (tag, className, text) => {
    const node = doc.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };
  const button = (text, title) => {
    const node = make("button", "", text); node.type = "button";
    if (title) { node.title = title; node.setAttribute("aria-label", title); }
    return node;
  };
  const bar = make("div", "timeline-navigation"), indexButton = button("Index", "Open timeline index"),
    previous = button("Previous edit", "Go to the previous edit on the active track"),
    next = button("Next edit", "Go to the next edit on the active track"),
    form = make("form", "timeline-timecode-form"), label = make("label", "", "Go to"),
    field = make("input"), go = button("Go", "Go to timeline timecode"), rate = make("span", "timeline-timecode-rate");
  bar.setAttribute("aria-label", "Timeline navigation");
  indexButton.id = "timelineIndexButton"; indexButton.setAttribute("aria-haspopup", "dialog");
  previous.id = "timelinePreviousEdit"; next.id = "timelineNextEdit";
  field.id = "timelineTimecode"; field.type = "text"; field.autocomplete = "off"; field.spellcheck = false; field.dir = "ltr";
  field.setAttribute("aria-label", "Timeline timecode"); field.setAttribute("aria-describedby", "timelineTimecodeHelp");
  label.htmlFor = field.id; go.type = "submit"; rate.id = "timelineTimecodeHelp";
  form.append(label, field, go, rate); bar.append(indexButton, previous, next, form);
  const body = timeline.scroll.closest(".timeline-body") || timeline.scroll;
  dock.insertBefore(bar, body);

  const dialog = make("dialog", "timeline-index-dialog"), header = make("header", "timeline-index-header"),
    heading = make("h2", "", "Timeline index"), close = button("Close", "Close timeline index"),
    description = make("p", "timeline-index-description", "Find a clip and open its existing inspector. Selecting an item does not change the edit."),
    filters = make("div", "timeline-index-filters"), search = make("input"), filter = make("select"),
    status = make("p", "timeline-index-status"), columns = make("div", "timeline-index-columns"),
    list = make("ol", "timeline-index-list"), more = button("Show more clips"), empty = make("p", "timeline-index-empty"),
    assetScopeRow = make("div", "timeline-index-asset-scope"), assetScopeName = make("span"),
    clearAssetScope = button("All timeline items", "Leave this file's uses and restore the previous timeline search");
  dialog.id = "timelineIndexDialog"; heading.id = "timelineIndexTitle"; description.id = "timelineIndexDescription";
  dialog.setAttribute("aria-labelledby", heading.id); dialog.setAttribute("aria-describedby", description.id);
  search.id = "timelineIndexSearch"; search.type = "search"; search.placeholder = "Search names, text or tracks";
  search.setAttribute("aria-label", "Search timeline clips"); search.autocomplete = "off";
  filter.id = "timelineIndexFilter"; filter.setAttribute("aria-label", "Filter timeline item type");
  for (const [value, text] of [["all", "All items"], ["video", "Video"], ["image", "Images"], ["audio", "Audio"], ["text", "Text"], ["caption", "Captions"]]) {
    const option = make("option", "", text); option.value = value; filter.append(option);
  }
  status.setAttribute("aria-live", "polite"); status.setAttribute("role", "status");
  columns.setAttribute("aria-hidden", "true");
  for (const text of ["Clip / text", "Track", "Start", "Duration"]) columns.append(make("span", "", text));
  header.append(heading, close); filters.append(search, filter);
  assetScopeRow.hidden = true; assetScopeName.dir = "auto";
  clearAssetScope.dataset.indexAllAssets = "true";
  assetScopeRow.append(assetScopeName, clearAssetScope);
  dialog.append(header, description, assetScopeRow, filters, status, columns, list, empty, more); doc.body.append(dialog);

  let entries = [], limit = 200, canvasOnClose = false, cachedTarget = null, cachedClips = [], fieldDirty = false, projectId;
  let indexAvailability = null, indexReadyStatus = "", indexItems = [], indexChecks = [], indexRevision = null;
  let assetScope = null, previousFilters = null, returnOrigin = indexButton, skipCloseFocus = false,
    activationToken = 0, indexPending = false, importedMatches = false;
  const scopeKey = () => assetScope ? `${assetScope.projectId}:${assetScope.assetId}` : "";
  const revokeActivation = () => { activationToken++; indexPending = false; };
  const restoreScope = () => {
    assetScope = null;
    if (previousFilters) { search.value = previousFilters.search; filter.value = previousFilters.filter; limit = previousFilters.limit; }
    previousFilters = null; assetScopeRow.hidden = true;
  };
  const scopeIssue = () => assetScope && (assetScope.projectId !== timeline.project?.id || !timeline.project?.assets?.[assetScope.assetId])
    ? "This file is no longer available in the current project. No other file was substituted." : "";
  const fps = () => Math.round(1 / sequenceFrame(timeline.project));
  const resetInput = () => {
    fieldDirty = false; field.setCustomValidity(""); field.removeAttribute("aria-invalid");
    const value = formatFrameTime(timeline.playhead, fps());
    if (field.value !== value) field.value = value;
  };
  const renderIndex = () => {
    const query = search.value.trim().toLocaleLowerCase();
    const scoped = assetScope ? entries.filter(entry => entry.asset_id === assetScope.assetId) : entries;
    const matches = scoped.filter(entry => (filter.value === "all" || entry.kind === filter.value)
      && (!query || `${entry.name} ${entry.track} ${entry.id || ""} ${entry.enabled === false ? "disabled" : ""} ${entry.locked ? "locked" : ""}`.toLocaleLowerCase().includes(query)));
    const available = timeline.canNavigate();
    importedMatches = matches.some(entry => Boolean(entry.asset_id));
    heading.textContent = assetScope ? "Timeline uses" : "Timeline index";
    description.textContent = assetScope
      ? "Saved timeline clips using this exact imported file, including disabled clips. These counts do not describe what is visible or audible. Choose one saved occurrence to select it and seek; opening this list changes nothing."
      : "Find a clip and open its existing inspector. Selecting an item does not change the edit.";
    assetScopeRow.hidden = !assetScope;
    if (assetScope) {
      assetScopeName.textContent = timeline.project?.assets?.[assetScope.assetId]?.name || assetScope.name;
      assetScopeName.title = assetScope.assetId;
    }
    list.replaceChildren(); indexItems = []; indexChecks = [];
    for (const entry of matches.slice(0, limit)) {
      const row = make("li"), item = button(null), name = make("span", "timeline-index-name", entry.name),
        track = make("span", "timeline-index-track", `${entry.track}${entry.locked ? " (locked)" : ""}${entry.enabled === false ? " (disabled)" : ""}`),
        start = make("span", "timeline-index-time", formatFrameTime(entry.start, fps())),
        length = make("span", "timeline-index-time", formatFrameTime(entry.end - entry.start, fps()));
      item.className = "timeline-index-item"; item.dataset.indexKey = entry.key; item.disabled = !available;
      if (entry.asset_id) item.dataset.indexAsset = entry.asset_id;
      if (entry.category === "media") item.dataset.layerEnabled = String(entry.enabled !== false);
      item.title = `${entry.name} · ${track.textContent} · ${start.textContent}${entry.enabled === false ? ". Disabled in preview and export; timing is retained." : ""}`; name.dir = "auto";
      item.indexSavedTitle = item.title;
      item.setAttribute("aria-label", `${entry.name}, ${track.textContent}, starts ${start.textContent}, duration ${length.textContent}`);
      item.append(name, track, start, length);
      if(!assetScope && timeline.onMediaSelectionChange && entry.category==="media"){
        row.className="timeline-index-layer-row";
        const label=make("label","timeline-index-layer-pick"),check=make("input");
        check.type="checkbox";check.dataset.indexLayer=entry.id;
        check.setAttribute("aria-label",`Select ${entry.name} with other clips`);
        label.title=`Select imported media or custom text. ${timeline.mediaGroupActionHint()} Closing the Index retains this selection.`;
        label.append(check);row.append(label);indexChecks.push(check);
      }
      row.append(item); list.append(row); indexItems.push(item);
    }
    indexReadyStatus = `${matches.length} of ${scoped.length} ${assetScope ? "timeline clips" : "items"}${matches.length > limit ? ` · showing ${limit}` : ""}`;
    indexAvailability = available;
    status.textContent = available ? indexReadyStatus : "Finish the current edit before selecting another clip.";
    empty.hidden = matches.length > 0;
    empty.textContent = assetScope
      ? scopeIssue() || (scoped.length ? "No uses match this search. Change the search or type filter." : "This file has no saved timeline clips. It remains available in the Media pool.")
      : entries.length ? "No clips match this search." : "Your timeline is empty. Import a video to start editing.";
    more.hidden = matches.length <= limit;
  };
  const sync = () => {
    const duration = timelineDuration(timeline.project), navigationAvailable = timeline.canNavigate(), available = navigationAvailable && duration > 0;
    let importedIssue = "";
    if (dialog.open && (importedMatches || assetScope)) {
      try { importedIssue = timeline.assetOccurrenceIssue?.() ?? ""; } catch { importedIssue = null; }
      if (typeof importedIssue !== "string") importedIssue = "Occurrence navigation readiness could not be confirmed.";
      if (assetScope && typeof timeline.onAssetOccurrenceSelect !== "function") importedIssue = "This editor cannot safely navigate to this file's uses.";
      importedIssue = scopeIssue() || importedIssue;
    }
    // A dialog opened while loading/saving must recover without closing it.
    // Change readiness in place, never rebuild rows or disturb focus/scroll.
    if (dialog.open && indexAvailability !== navigationAvailable) {
      indexAvailability = navigationAvailable;
      status.textContent = navigationAvailable ? indexReadyStatus : "Finish the current edit before selecting another clip.";
    }
    if (dialog.open) for (const item of indexItems) {
      const reason = item.dataset.indexAsset ? importedIssue : "";
      item.disabled = !navigationAvailable || indexPending || Boolean(reason);
      item.title = reason || item.indexSavedTitle || item.title;
    }
    if(dialog.open && !assetScope && timeline.onMediaSelectionChange){
      const selected=timeline.selectedMediaIds();
      for(const check of indexChecks){const checked=selected.includes(check.dataset.indexLayer);if(check.checked!==checked)check.checked=checked;
        check.disabled=indexPending || !navigationAvailable || (!checked && selected.length>=200);}
      const message=navigationAvailable?`${selected.length ? `${selected.length} selected · ` : ""}${indexReadyStatus}`:"Finish the current edit before selecting another clip.";
      if(status.textContent!==message)status.textContent=message;
    }
    if (dialog.open) {
      const reason = indexPending ? "Selecting the saved occurrence..." : importedIssue
        || (!navigationAvailable ? "Finish the current edit before selecting another clip." : "");
      if (reason) status.textContent = reason;
      else if (!timeline.onMediaSelectionChange || assetScope) status.textContent = indexReadyStatus;
    }
    if (cachedTarget !== timeline.editTarget) { cachedTarget = timeline.editTarget; cachedClips = timeline.targetClips(); }
    indexButton.disabled = !timeline.project;
    field.disabled = go.disabled = !available;
    previous.disabled = !available || adjacentTimelineEdit(cachedClips, timeline.playhead, duration, -1) == null;
    next.disabled = !available || adjacentTimelineEdit(cachedClips, timeline.playhead, duration, 1) == null;
    const rateText = `${fps()} FPS`;
    if (rate.textContent !== rateText) rate.textContent = rateText;
    const help = "Project frame rate. Enter seconds, MM:SS, or HH:MM:SS:FF. No drop-frame notation.";
    if (rate.title !== help) rate.title = help;
    if (field.getAttribute("aria-description") !== help) field.setAttribute("aria-description", rate.title);
    if (doc.activeElement !== field && !fieldDirty) resetInput();
  };
  const refresh = () => {
    entries = timelineIndexEntries(timeline.project, timeline.getTrackClips); cachedTarget = null;
    if (indexPending && indexRevision !== timeline.project?.revision) revokeActivation();
    indexRevision = timeline.project?.revision;
    if (projectId !== timeline.project?.id) {
      if (projectId != null) { revokeActivation(); restoreScope(); if (dialog.open) { skipCloseFocus = true; dialog.close(); } }
      projectId = timeline.project?.id; resetInput();
    }
    if (dialog.open) renderIndex();
    sync();
  };
  const openAsset = (assetId, origin = null) => {
    const project = timeline.project, asset = project?.assets?.[assetId];
    if (!project?.id || typeof assetId !== "string" || !asset || typeof asset !== "object") return false;
    revokeActivation();
    if (!assetScope) previousFilters = { search: search.value, filter: filter.value, limit };
    assetScope = { projectId: project.id, assetId, name: asset.name || "Imported file" };
    returnOrigin = origin || indexButton; canvasOnClose = false; skipCloseFocus = false;
    search.value = ""; filter.value = "all"; limit = 200; projectId = project.id;
    entries = timelineIndexEntries(project, timeline.getTrackClips); indexRevision = project.revision; renderIndex();
    if (!dialog.open) dialog.showModal();
    sync(); search.focus(); return true;
  };
  indexButton.addEventListener("click", () => {
    if (!timeline.project || dialog.open) return;
    revokeActivation(); restoreScope(); returnOrigin = indexButton; skipCloseFocus = false;
    refresh(); limit = 200; renderIndex(); dialog.showModal(); sync(); search.focus();
  });
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", revokeActivation);
  dialog.addEventListener("close", () => {
    if (dialog.open) return; // A queued close event cannot reset a newer opening.
    revokeActivation(); restoreScope();
    const origin = returnOrigin, validOrigin = origin?.isConnected !== false && !origin?.disabled
      && (typeof origin?.getClientRects !== "function" || origin.getClientRects().length);
    if (!skipCloseFocus) (canvasOnClose ? timeline.canvas : validOrigin ? origin : indexButton)?.focus?.({ preventScroll: true });
    canvasOnClose = false; skipCloseFocus = false; returnOrigin = indexButton;
  });
  clearAssetScope.addEventListener("click", () => { revokeActivation(); restoreScope(); renderIndex(); sync(); search.focus(); });
  for (const type of ["pointerdown", "keydown"]) dialog.addEventListener(type, () => {
    if (indexPending) { revokeActivation(); sync(); }
  }, true);
  search.addEventListener("input", () => { revokeActivation(); limit = 200; renderIndex(); sync(); });
  filter.addEventListener("change", () => { revokeActivation(); limit = 200; renderIndex(); sync(); });
  more.addEventListener("click", () => { limit += 200; renderIndex(); sync(); });
  list.addEventListener("change", event => {
    const check=event.target.closest?.("input[data-index-layer]");
    if(!check || check.disabled || !timeline.onMediaSelectionChange)return;
    const focusOwned=doc.activeElement===check, selectedProject=timeline.project?.id, selectedId=check.dataset.indexLayer;
    void timeline.toggleMediaSelection(selectedId).finally(() => {
      sync();
      // Native disabling blurs the checkbox while its guarded selection settles.
      // Restore only that lost focus, never a control the person moved to.
      if(focusOwned && dialog.open && timeline.project?.id===selectedProject
        && (doc.activeElement===doc.body || doc.activeElement===dialog)) {
        const current=indexChecks.find(node=>node.dataset.indexLayer===selectedId);
        if(current && !current.disabled) current.focus({preventScroll:true});
      }
    });
  });
  list.addEventListener("click", async event => {
    const item = event.target.closest?.("button[data-index-key]");
    if (!item || item.disabled) return;
    const token = ++activationToken, key = item.dataset.indexKey, scope = scopeKey(),
      selectedProject = timeline.project?.id, selectedRevision = timeline.project?.revision;
    const current = () => dialog.open && activationToken === token && scopeKey() === scope
      && timeline.project?.id === selectedProject && timeline.project?.revision === selectedRevision;
    const ownedFocus = doc.activeElement === item;
    indexPending = true; sync();
    let accepted = false;
    try {
      const result = timeline.selectIndexEntry(key, current);
      accepted = result && typeof result.then === "function" ? await result : result;
    } catch {}
    if (!current()) { if (activationToken === token) { indexPending = false; sync(); } return; }
    indexPending = false;
    if (accepted === true) { canvasOnClose = true; dialog.close(); }
    else {
      sync();
      if (ownedFocus && (doc.activeElement === doc.body || doc.activeElement === dialog) && item.isConnected !== false && !item.disabled)
        item.focus({ preventScroll: true });
    }
  });
  previous.addEventListener("click", () => timeline.navigateEdit(-1));
  next.addEventListener("click", () => timeline.navigateEdit(1));
  field.addEventListener("input", () => { fieldDirty = true; field.setCustomValidity(""); field.removeAttribute("aria-invalid"); });
  field.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); resetInput(); field.blur(); }
  });
  field.addEventListener("focus", () => field.select());
  form.addEventListener("submit", event => {
    event.preventDefault();
    const time = parseTimelineTimecode(field.value, fps()), duration = timelineDuration(timeline.project);
    const message = time == null ? `Use seconds, MM:SS, or HH:MM:SS:FF at ${fps()} FPS.`
      : time > duration ? `The timeline ends at ${formatFrameTime(duration, fps())}.` : "";
    field.setCustomValidity(message);
    if (message) { field.setAttribute("aria-invalid", "true"); field.reportValidity(); return; }
    if (timeline.seekNavigation(time)) { resetInput(); timeline.canvas.focus({ preventScroll: true }); }
  });
  sync();
  return { refresh, sync, dialog, bar, openAsset };
}

// Output frame time, not source timecode or drop-frame notation. All supported
// project rates are integer FPS; keep the existing duration formatter intact.
export function formatFrameTime(seconds, fps = 30) {
  fps = [24, 25, 30, 50, 60].includes(Math.round(fps)) ? Math.round(fps) : 30;
  const value = Number(seconds), total = Math.max(0, Math.round((Number.isFinite(value) ? value : 0) * fps));
  const frames = total % fps, whole = Math.floor(total / fps);
  return [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60, frames].map(part => String(part).padStart(2, "0")).join(":");
}

export function formatTime(seconds, withMillis = false) {
  const numeric = Number(seconds);
  const value = Number.isFinite(numeric) ? Math.max(0, numeric) : 0;
  const wholeSeconds = Math.floor(value);
  const hours = Math.floor(wholeSeconds / 3600);
  const minutes = Math.floor((wholeSeconds % 3600) / 60);
  const secs = wholeSeconds % 60;
  const base = `${hours ? `${String(hours).padStart(2,"0")}:` : ""}${String(minutes).padStart(2,"0")}:${String(secs).padStart(2,"0")}`;
  // Subtracting whole seconds can leave 1.2 as 1 + .19999999999999996.
  // Correct floating-point noise only; still truncate rather than round time,
  // and never let that correction carry 59.999 into the next second.
  const tolerance = Math.min(1e-7, Number.EPSILON * Math.max(1, value) * 20);
  const tenths = Math.min(9, Math.floor((value - wholeSeconds) * 10 + tolerance));
  return withMillis ? `${base}.${tenths}` : base;
}
