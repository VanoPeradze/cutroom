// Global output keep ranges deliberately leave excluded material visible.
// Optional independent A/B source clips occupy separate lanes on this clock.
export function timelineDuration(project) {
  const duration = Number(project?.manual?.sequence?.duration ?? project?.sources?.A?.duration);
  return Number.isFinite(duration) ? Math.max(0, duration) : 0;
}

function selectionMinimum(project) { return project?.manual?.sequence || project?.__sourceReview ? 1 / 60 - 1e-9 : .03; }

function sequenceFrame(project) {
  const fps = Number(project?.settings?.fps);
  return 1 / ([24, 25, 30, 50, 60].includes(fps) ? fps : 30);
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
    .slice().sort((a,b)=>a.start-b.start);
  const gaps = []; let cursor = 0;
  for (const clip of clips) {
    if (clip.start > cursor + 1e-6) gaps.push({start:cursor,end:clip.start});
    cursor = Math.max(cursor,clip.end);
  }
  if (timelineDuration(project) > cursor + 1e-6) gaps.push({start:cursor,end:timelineDuration(project)});
  return gaps;
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
    this.onMediaEdit = options.onMediaEdit;
    this.onMediaPreview = options.onMediaPreview;
    this.onMediaAction = options.onMediaAction;
    this.getTrackClips = options.getTrackClips;
    this.sourceReview = Boolean(options.sourceReview);
    this.editTarget = "edit";
    this.canEdit = options.canEdit || (() => true);
    this.cutAnchor = null;
    this.editPending = false;
    this.snapping = false;
    this.project = null;
    this.zoom = 1;
    this.zoomFocusPending = false;
    this.playhead = 0;
    this.hoverTime = null;
    this.images = [];
    this.scrubbing = false;
    this.selecting = false;
    this.selectionAnchor = null;
    this.selectionCursor = null;
    this.selection = null;
    this.tool = "select";
    this.gesture = null;
    this.raf = null;
    this.resizeObserver = new ResizeObserver(() => this.scheduleDraw());
    this.resizeObserver.observe(scroll);
    canvas.addEventListener("pointerdown", (event) => this.pointerDown(event));
    canvas.addEventListener("pointermove", (event) => this.pointerMove(event));
    canvas.addEventListener("pointerup", (event) => this.pointerUp(event));
    canvas.addEventListener("pointercancel", (event) => this.pointerCancel(event));
    canvas.addEventListener("lostpointercapture", (event) => this.pointerCancel(event));
    canvas.addEventListener("pointerleave", () => { if (!this.gesture) { this.hoverTime = null; this.scheduleDraw(); } });
    canvas.addEventListener("keydown", (event) => this.keyDown(event));
    scroll.addEventListener("wheel", (event) => this.handleWheel(event), { passive: false });
    scroll.addEventListener("scroll", () => this.scheduleDraw(), { passive: true });
    canvas.addEventListener("dblclick", () => { if (!["blade", "remove_between"].includes(this.tool)) this.fit(); });
  }

  setProject(project) {
    this.zoomFocusPending = false;
    this.cancelGesture(false);
    this.cancelPendingCut();
    this.project = project;
    if (!this.hasTrackLanes() || (this.editTarget !== "edit" && !project?.sources?.[this.editTarget])) this.setEditTarget("edit");
    this.clearSelection(false);
    const duration = timelineDuration(project);
    this.canvas.setAttribute("aria-valuemax", String(duration));
    this.updateAccessiblePlayhead();
    this.loadImages();
    this.scheduleDraw();
  }

  setTool(tool) {
    if (!["select", "range", "blade", "remove_between", "move"].includes(tool)) return false;
    this.cancelGesture();
    this.cancelPendingCut();
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
    if (this.tool !== "remove_between" || !this.project?.draft || !this.onEdit || this.editPending || !this.canEdit()
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

  setZoom(value) {
    const oldZoom = this.zoom;
    this.zoom = Math.max(1, Math.min(16, Number(value) || 1));
    if (Math.abs(oldZoom - this.zoom) < .001) return;
    // All zoom controls target the yellow playhead, not the mouse or the
    // viewport's old left edge. Apply after canvas sizing, even if playback
    // or pointer events replace this scheduled frame before it is painted.
    this.zoomFocusPending = true;
    this.scheduleDraw();
  }

  fit() {
    this.zoomFocusPending = false;
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
    this.canvas.setAttribute("aria-valuenow", String(Math.round(this.playhead * 10) / 10));
    this.canvas.setAttribute("aria-valuetext", formatTime(this.playhead, true));
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
    if (this.gesture || this.scrubbing || !this.project) return;
    const { px } = this.geometry();
    const x = this.playhead * px;
    const left = this.scroll.scrollLeft;
    const width = this.scroll.clientWidth || 1;
    if (x < left + width * .08) this.scroll.scrollLeft = Math.max(0, x - width * .18);
    else if (x > left + width * .88) this.scroll.scrollLeft = Math.max(0, x - width * .72);
  }

  async loadImages() {
    const urls = this.project?.sources?.A?.thumbnail_urls || this.project?.analysis?.thumbnail_urls?.A || [];
    const token = this.project?.id;
    const images = await Promise.all(urls.map((url) => new Promise((resolve) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => resolve(null);
      image.src = url;
    })));
    if (this.project?.id === token) {
      this.images = images;
      this.scheduleDraw();
    }
    this.mediaImages ||= new Map();
    const extraUrls = [...(this.project?.sources?.B?.thumbnail_urls || []),
      ...Object.values(this.project?.assets || {}).map(asset => asset.thumbnail_url).filter(Boolean)];
    for (const url of extraUrls) if (!this.mediaImages.has(url)) {
      this.mediaImages.set(url, null);
      const image = new Image(); image.onload = () => { this.mediaImages.set(url,image); this.scheduleDraw(); }; image.src = url;
    }
  }

  baseHeight() {
    if (this.project?.manual?.sequence) return this.project.sources?.B ? 230 : 174;
    return (this.sourceReview || this.scroll.closest?.('.studio-timeline-dock') ? 180 : 310) + (this.hasTrackLanes() ? 68 : 0);
  }

  mediaRows() {
    if (this.sourceReview) return [];
    const rows = [];
    for (const clip of this.project?.manual?.media_clips || []) {
      const asset = this.project.assets?.[clip.asset_id]; if (!asset) continue;
      const group = asset.kind === 'audio' ? (clip.role || 'music') : 'visual';
      let row = rows.find(row => row.group === group && row.clips.every(item => item.end <= clip.start || item.start >= clip.end));
      if (!row) { row = {group,clips:[]}; rows.push(row); }
      row.clips.push(clip);
    }
    return rows.map((row,index)=>({...row,top:this.baseHeight()+index*46,bottom:this.baseHeight()+(index+1)*46}));
  }

  mediaAtEvent(event) {
    const y = event.clientY-this.canvas.getBoundingClientRect().top, time=this.timeFromEvent(event);
    const row = this.mediaRows().find(row=>y>=row.top && y<row.bottom);
    const clip = row?.clips.find(clip=>time>=clip.start && time<clip.end);
    return clip ? {clip,row} : null;
  }

  drawMedia(ctx, px, width) {
    const left = this.scroll.scrollLeft || 0, right=left+this.scroll.clientWidth;
    for (const row of this.mediaRows()) {
      ctx.fillStyle='#102027'; ctx.fillRect(0,row.top,width,42);
      for (const saved of row.clips) {
        const clip=this.gesture?.media?.id === saved.id ? {...saved,...this.gesture.patch} : saved;
        const asset=this.project.assets[clip.asset_id], x=clip.start*px, w=(clip.end-clip.start)*px;
        if (x+w<left || x>right) continue;
        ctx.fillStyle=asset.kind==='audio' ? '#264e44' : '#51436b'; ctx.fillRect(x,row.top+1,w,40);
        const image=this.mediaImages?.get(asset.thumbnail_url);
        ctx.save(); ctx.beginPath(); ctx.rect(x+1,row.top+2,Math.max(0,w-2),38); ctx.clip();
        if(image) { ctx.globalAlpha=.7; for(let ix=Math.max(x,left); ix<x+w && ix<right;ix+=62) ctx.drawImage(image,ix,row.top+2,60,38); ctx.globalAlpha=1; }
        const waveform=asset.waveform || [];
        if(waveform.length && asset.kind==='audio') {
          ctx.strokeStyle='#86dcc0'; ctx.beginPath();
          for(let ix=Math.max(x,left);ix<Math.min(x+w,right);ix+=3) {
            const source=Number(clip.source_start||0)+(ix/px-clip.start);
            const value=Number(waveform[Math.min(waveform.length-1,Math.floor(source/Math.max(.001,asset.duration)*waveform.length))])||0;
            const amp=Math.min(15,Math.abs(value)*15); ctx.moveTo(ix,row.top+25-amp); ctx.lineTo(ix,row.top+25+amp);
          } ctx.stroke();
        }
        ctx.fillStyle='rgba(0,0,0,.75)'; ctx.fillRect(Math.max(x,left),row.top+2,Math.min(w,300),14);
        ctx.fillStyle='#f0edf5'; ctx.font='10px ui-monospace, monospace';
        ctx.fillText(`${asset.kind==='audio' ? clip.role : asset.kind} · ${asset.name}${clip.speed!==1 ? ` · ${clip.speed}×` : ''}`,Math.max(x+5,left+5),row.top+12);
        ctx.strokeStyle='#d4c84f';ctx.beginPath();
        if(clip.fade_in>0){ctx.moveTo(x,row.top+40);ctx.lineTo(x+clip.fade_in*px,row.top+3);}
        if(clip.fade_out>0){ctx.moveTo(x+w-clip.fade_out*px,row.top+3);ctx.lineTo(x+w,row.top+40);}ctx.stroke();
        ctx.restore();
        ctx.strokeStyle=this.mediaSelection===clip.id ? '#ffe174':'#b8a4d1'; ctx.lineWidth=this.mediaSelection===clip.id ? 2:1; ctx.strokeRect(x+.5,row.top+1.5,Math.max(0,w-1),39);
        if(this.mediaSelection===clip.id){ctx.fillStyle='#fff';ctx.fillRect(x,row.top+11,3,20);ctx.fillRect(x+w-3,row.top+11,3,20);}
      }
    }
    if((this.project?.settings?.burn_captions !== false || this.project?.settings?.captions) && this.project?.analysis?.transcript?.segments?.length) {
      const top=this.baseHeight()+this.mediaRows().length*46;
      ctx.fillStyle='#1c2630';ctx.fillRect(0,top,width,28);
      for(const caption of this.audioTimelineRanges(this.project.analysis.transcript.segments)) {
        const x=caption.start*px,w=(caption.end-caption.start)*px;
        if(x+w<left || x>right)continue;
        ctx.fillStyle='#384962';ctx.fillRect(x+1,top+1,Math.max(1,w-2),26);
        ctx.save();ctx.beginPath();ctx.rect(x+2,top,Math.max(0,w-4),28);ctx.clip();ctx.fillStyle='#eef3ff';ctx.font='10px sans-serif';ctx.fillText(`Cc ${caption.text}`,Math.max(x+4,left),top+17);ctx.restore();
      }
    }
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
    if (this.raf) cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame(() => {
      this.raf = null;
      this.draw();
      after?.();
    });
  }

  draw() {
    const ctx = this.context;
    const { duration, width, px, viewport } = this.geometry();
    this.compact = this.sourceReview || Boolean(this.scroll.closest?.(".studio-timeline-dock"));
    const sequence = Boolean(this.project?.manual?.sequence);
    const extra = !sequence && this.hasTrackLanes() ? 68 : 0;
    const cssHeight = this.baseHeight()+this.mediaRows().length*46+((this.project?.settings?.burn_captions !== false || this.project?.settings?.captions) && this.project?.analysis?.transcript?.segments?.length ? 30:0);
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
    ctx.fillStyle = "#081013";
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
    this.drawLabels(ctx);
    this.drawMedia(ctx,px,width);
    if (this.selection) this.drawSelection(ctx, this.selection, px, cssHeight);
    if (this.cutAnchor != null) this.drawPendingCut(ctx, px, cssHeight);
    if (this.hoverTime != null) this.drawHover(ctx, this.hoverTime, px, cssHeight);
    this.drawPlayhead(ctx, px, cssHeight);
  }

  drawRuler(ctx, duration, width, px) {
    ctx.fillStyle = "#0d181c";
    ctx.fillRect(0, 0, width, 30);
    const ideal = 92 / px;
    const steps = [.25,.5,1,2,5,10,15,30,60,120,300,600];
    const step = steps.find((value) => value >= ideal) || 900;
    ctx.strokeStyle = "rgba(235,240,242,.16)";
    ctx.fillStyle = "#8da1a6";
    ctx.font = "10px ui-monospace, SFMono-Regular, Consolas, monospace";
    for (let time = 0; time <= duration + step; time += step) {
      const x = time * px;
      ctx.beginPath(); ctx.moveTo(x, 20); ctx.lineTo(x, 30); ctx.stroke();
      ctx.fillText(formatTime(time), x + 5, 14);
    }
  }

  drawFilmstrip(ctx, width) {
    const y = 36, height = this.compact ? 32 : 72;
    ctx.fillStyle = "#132126";
    ctx.fillRect(0, y, width, height);
    if (!this.images.length) {
      const gradient = ctx.createLinearGradient(0, y, 0, y + height);
      gradient.addColorStop(0, "#1a2a31"); gradient.addColorStop(1, "#0d181c");
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
      ctx.fillStyle = index % 2 ? "#111f24" : "#0b171b";
      ctx.fillRect(0, y, width, h);
      ctx.strokeStyle = "rgba(235,240,242,.07)";
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
      ctx.fillStyle = active ? "#172d36" : "#101d24";
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
        ctx.fillStyle = slot === "A" ? "#23616d" : "#5e4580";
        ctx.fillRect(x + 1, top + 2, Math.max(1, width - 2), h - 4);
        const thumbUrls=this.project.sources?.[slot]?.thumbnail_urls || [];
        const frames=slot==='A' ? this.images : thumbUrls.map(url=>this.mediaImages?.get(url));
        if(frames?.some(Boolean)) {
          ctx.save();ctx.beginPath();ctx.rect(x+1,top+2,Math.max(0,width-2),h-4);ctx.clip();ctx.globalAlpha=.5;
          for(let ix=Math.max(x,viewportLeft);ix<x+width && ix<viewportLeft+this.scroll.clientWidth;ix+=64) {
            const sourceTime=clip.source_start+(ix/px-clip.start)*(clip.video_speed||1);
            const index=Math.min(frames.length-1,Math.max(0,Math.floor(sourceTime/Math.max(.001,this.project.sources[slot].duration)*frames.length)));
            if(frames[index])ctx.drawImage(frames[index],ix,top+2,64,h-4);
          }ctx.restore();
        }
        ctx.strokeStyle = active ? "#d3f4f4" : (slot === "A" ? "#44b9c6" : "#ab8bce");
        ctx.lineWidth = 1; ctx.strokeRect(x + .5, top + 2.5, Math.max(0, width - 1), h - 5);
        if (width > 65) {
          ctx.save(); ctx.beginPath(); ctx.rect(x + 3, top, width - 6, h); ctx.clip();
          ctx.fillStyle = "#eef5f7"; ctx.font = "10px ui-monospace, monospace";
          const clipNumber = clipIndex + 1;
          ctx.fillText(`${slot}${clipNumber} · ${formatTime(clip.source_start, true)} · ${(clip.end - clip.start).toFixed(1)}s${clip.video_speed && clip.video_speed!==1 ? ` · ${clip.video_speed}× picture` : ''}`, Math.max(x + 8, viewportLeft + 64), top + (h > 40 ? 29 : 19));
          ctx.restore();
        }
      }
      for (const cut of this.project?.draft?.cuts || []) {
        ctx.fillStyle = "rgba(0,0,0,.55)";
        ctx.fillRect(cut.start * px, top, (cut.end - cut.start) * px, h);
      }
      if (this.gesture?.kind === "move" && [slot, "edit"].includes(this.gesture.target) && this.gesture.moveStart != null) {
        const clip = this.gesture.clip;
        ctx.fillStyle = this.gesture.collision ? "rgba(255,93,93,.55)" : "rgba(185,244,213,.6)";
        ctx.fillRect(this.gesture.moveStart * px, top, (clip.end - clip.start) * px, h);
        if (this.gesture.target === "edit") {
          const x = this.gesture.moveStart * px;
          ctx.strokeStyle = "#b9f4d5"; ctx.lineWidth = 3;
          ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke();
        }
      }
      ctx.fillStyle = "rgba(8,16,19,.94)"; ctx.fillRect(viewportLeft + 4, top + 4, 52, 21);
      ctx.fillStyle = active ? "#ffffff" : "#8da1a6";
      ctx.font = "700 9px ui-monospace, monospace"; ctx.fillText(`VIDEO ${slot}`, viewportLeft + 9, top + 18);
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
      ctx.fillStyle = "rgba(255,83,74,.18)";
      ctx.fillRect(x, y, w, height);
    }
  }

  drawGaps(ctx, px) {
    if (this.gesture?.kind === "move") return;
    const {top,bottom} = this.editLane();
    for (const gap of sequenceGaps(this.project,this.getTrackClips,this.editTarget === "edit" ? null : this.editTarget)) {
      const x=gap.start*px,width=(gap.end-gap.start)*px;
      ctx.fillStyle="rgba(210,147,110,.1)";ctx.fillRect(x,top,width,bottom-top);
      ctx.strokeStyle="#866c58";ctx.setLineDash([4,4]);ctx.strokeRect(x+.5,top+2,width-1,bottom-top-4);ctx.setLineDash([]);
      if (width>45) {
        ctx.save();ctx.beginPath();ctx.rect(x+3,top,width-6,bottom-top);ctx.clip();
        ctx.fillStyle="#d3b9a9";ctx.font="10px ui-monospace, monospace";
        ctx.fillText(`GAP · ${(gap.end-gap.start).toFixed(1)}s`,x+8,(top+bottom)/2+4);ctx.restore();
      }
    }
  }

  drawRanges(ctx, px) {
    const draft = this.project?.draft;
    const duration = timelineDuration(this.project);
    const y = this.compact ? 76 : 124, height = this.compact ? 22 : 40;
    ctx.fillStyle = "rgba(141,161,166,.08)";
    ctx.fillRect(0, y, duration * px, height);
    for (const clip of editableClips(this.project)) {
      const x = clip.start * px;
      const width = Math.max(1, (clip.end - clip.start) * px);
      const selected = this.editTarget === "edit" && this.selection && Math.abs(this.selection.start - clip.start) < .015 && Math.abs(this.selection.end - clip.end) < .015;
      ctx.fillStyle = selected ? "#36834e" : (clip.index % 2 ? "#235b43" : "#1e4d3a");
      ctx.fillRect(x, y, width, height);
      ctx.strokeStyle = selected ? "#b7f4d2" : "#45976b";
      ctx.lineWidth = selected ? 2 : 1;
      ctx.strokeRect(x + .5, y + .5, Math.max(0, width - 1), height - 1);
      if (width > 34) {
        ctx.save(); ctx.beginPath(); ctx.rect(x + 3, y, Math.max(0, width - 6), height); ctx.clip();
        ctx.fillStyle = "#d4efdf";
        ctx.font = "600 10px ui-monospace, monospace";
        ctx.fillText(this.sourceReview ? `In edit · ${formatTime(clip.end - clip.start, true)}` : width > 100 ? `Clip ${clip.index + 1} · ${formatTime(clip.end - clip.start, true)}` : `${clip.index + 1}`, x + 8, y + (this.compact ? 15 : 24));
        ctx.restore();
      }
    }
    for (const cut of draft?.cuts || []) {
      const x = Number(cut.start) * px;
      const width = Math.max(2, (Number(cut.end) - Number(cut.start)) * px);
      ctx.fillStyle = "#ff5b49";
      ctx.fillRect(x, y, width, height);
      if (width > 42) {
        ctx.fillStyle = "#170604"; ctx.font = "700 9px ui-monospace, monospace";
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
      ctx.fillStyle = ["A", "screen"].includes(camera) ? "#44b9c6" : ["B", "camera"].includes(camera) ? "#9676bd" : "#c9b62c";
      ctx.globalAlpha = .82; ctx.fillRect(x, y, width, 22); ctx.globalAlpha = 1;
      // Clip labels to their own scene, especially on long/zoomed-out sources.
      const labelX = Math.max(x + 6, (this.scroll.scrollLeft || 0) + 70);
      if (width > 38 && labelX < x + width - 12) {
        ctx.save(); ctx.beginPath(); ctx.rect(x + 2, y, Math.max(0, width - 4), 22); ctx.clip();
        ctx.fillStyle = "#081013"; ctx.font = "700 9px ui-monospace, monospace";
        const label = labels[camera] || camera;
        ctx.fillText(label, labelX, y + 14);
        ctx.restore();
      }
    }
  }

  drawWaveform(ctx, px, width) {
    const bins = this.audioTimelineRanges(this.project?.analysis?.audio?.waveform || []);
    const y = this.project?.manual?.sequence ? (this.project.sources?.B ? 186 : 130) : this.compact ? 140 : 230, height = this.compact || this.project?.manual?.sequence ? 26 : 54, mid = y + height / 2;
    ctx.strokeStyle = "rgba(226,235,238,.64)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    if (bins.length) {
      for (const bin of bins) {
        const start = Number(bin.start || 0), end = Number(bin.end || start);
        const x = ((start + end) / 2) * px;
        const rms = Math.max(-72, Math.min(0, Number(bin.rms_dbfs ?? -72)));
        const peak = Math.max(-72, Math.min(0, Number(bin.peak_dbfs ?? rms)));
        const amp = Math.max(2, ((rms + 72) / 72) * height * .42);
        const peakAmp = Math.max(amp, ((peak + 72) / 72) * height * .48);
        ctx.moveTo(x, mid - amp); ctx.lineTo(x, mid + amp);
        if (peakAmp > amp + 3) { ctx.moveTo(x, mid - peakAmp); ctx.lineTo(x, mid - amp - 1); }
      }
    } else {
      ctx.moveTo(0, mid); ctx.lineTo(width, mid);
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
    if (this.audioCacheProject !== project) { this.audioRangeCache = new Map(); this.audioCacheProject = project; }
    const signature = `${selected}:${offset}`;
    const cached = this.audioRangeCache.get(ranges);
    if (cached?.signature === signature) return cached.mapped;
    const mapped = this.getTrackClips(project, selected).flatMap((clip) => ranges.map((item) => {
      const start = Math.max(Number(item.start) - offset, clip.source_start);
      const end = Math.min(Number(item.end) - offset, clip.source_start + clip.end - clip.start);
      return { ...item, start: clip.start + start - clip.source_start, end: clip.start + end - clip.source_start };
    }).filter((item) => item.end > item.start));
    this.audioRangeCache.set(ranges, { signature, mapped });
    return mapped;
  }

  drawLabels(ctx) {
    ctx.font = "700 9px ui-monospace, SFMono-Regular, Consolas, monospace";
    const labels = this.compact ? [["EDIT",80],["LAYOUT",123],["AUDIO",144]] : [["EDIT",127],["LAYOUT",199],["AUDIO",232]];
    if (this.sourceReview) labels.splice(0, labels.length, ["SOURCE",80],["AUDIO",144]);
    if (this.project?.manual?.sequence) { labels.splice(0, labels.length, ["LAYOUT",this.project.sources?.B ? 167 : 111],["AUDIO",this.project.sources?.B ? 198 : 142]); }
    else if (this.hasTrackLanes()) { labels[1][1] += 68; labels[2][1] += 68; }
    const viewportLeft = this.scroll.scrollLeft || 0;
    for (const [label,y] of labels) {
      const width = ctx.measureText(label).width + 12;
      ctx.fillStyle = "rgba(9,11,13,.94)"; ctx.fillRect(viewportLeft + 4, y - 11, width, 17);
      ctx.fillStyle = "#aebbc0"; ctx.fillText(label, viewportLeft + 10, y);
    }
  }

  drawPlayhead(ctx, px, height) {
    const x = this.playhead * px;
    ctx.strokeStyle = "#c9b62c"; ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
    ctx.fillStyle = "#c9b62c";
    ctx.beginPath(); ctx.moveTo(x - 6, 0); ctx.lineTo(x + 6, 0); ctx.lineTo(x, 8); ctx.closePath(); ctx.fill();
  }

  drawSelection(ctx, selection, px, height) {
    const x1 = Number(selection.start) * px;
    const x2 = Number(selection.end) * px;
    const width = Math.max(1, x2 - x1);
    const { top, bottom } = this.editLane();
    ctx.fillStyle = "rgba(68,185,198,.14)";
    ctx.fillRect(x1, this.editTarget === "edit" ? 30 : top, width, this.editTarget === "edit" ? height - 30 : bottom - top);
    ctx.strokeStyle = "rgba(68,185,198,.94)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(x1, 30); ctx.lineTo(x1, height);
    ctx.moveTo(x2, 30); ctx.lineTo(x2, height);
    ctx.stroke();
    const trim = this.trimTarget() || this.gesture?.kind === "trim";
    ctx.fillStyle = trim ? "#e8ffff" : "#9deaf0";
    ctx.fillRect(x1, top + 3, 5, bottom - top - 6);
    ctx.fillRect(x2 - 5, top + 3, 5, bottom - top - 6);
    if (trim) {
      ctx.fillStyle = "#23616d";
      for (const x of [x1+2,x2-3]) ctx.fillRect(x,top+12,1,Math.max(4,bottom-top-24));
    }
  }

  drawHover(ctx, time, px, height) {
    if (this.gesture?.kind === "move" && Number.isFinite(this.gesture.moveStart)) time = this.gesture.moveStart;
    const x = time * px;
    ctx.strokeStyle = "rgba(255,255,255,.28)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, height); ctx.stroke();
    const label = `${this.gesture?.kind === "move" ? this.gesture.target === "edit" ? "Move together · " : `Move ${this.gesture.target} · ` : ""}${formatTime(time, true)}`;
    ctx.font = "10px ui-monospace, monospace";
    const w = ctx.measureText(label).width + 12;
    const labelX = Math.max(2, Math.min(this.geometry().width - w - 2, x - w / 2));
    ctx.fillStyle = "#f4f7f7"; ctx.fillRect(labelX, 31, w, 20);
    ctx.fillStyle = "#081013"; ctx.fillText(label, labelX + 6, 45);
  }

  drawPendingCut(ctx, px, height) {
    const x = this.cutAnchor * px;
    if (this.hoverTime != null) {
      const { top, bottom } = this.editLane();
      ctx.fillStyle = "rgba(255,123,134,.25)";
      ctx.fillRect(Math.min(x, this.hoverTime * px), top, Math.abs(this.hoverTime * px - x), bottom - top);
    }
    ctx.strokeStyle = "#ff9aa3";
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

  snappedTime(time, event) {
    if (this.sourceReview) time = Math.max(0, Math.min(timelineDuration(this.project), Math.round(time / sequenceFrame(this.project)) * sequenceFrame(this.project)));
    if (!this.snapping || event.altKey) return time;
    const { px, duration } = this.geometry();
    const threshold = Math.min(.5, 8 / Math.max(px, .0001));
    const boundaries = [0, duration, ...this.targetClips().flatMap((clip) => [clip.start, clip.end])];
    let nearest = time, distance = threshold;
    for (const boundary of boundaries) {
      const delta = Math.abs(time - boundary);
      if (delta <= distance) { nearest = boundary; distance = delta; }
    }
    return nearest;
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
    if(this.gesture?.kind==='media')this.onMediaPreview?.(this.gesture.media.id,null);
    const gesture = this.gesture;
    if (!gesture) return false;
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

  canSplitAt(time) {
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
    if (event.button !== 0 || !this.project || this.gesture || this.editPending || !this.canEdit()) return;
    event.preventDefault();
    this.canvas.focus?.({ preventScroll: true });
    try { this.canvas.setPointerCapture?.(event.pointerId); } catch (_) { /* A cancelled pointer may no longer be capturable. */ }
    const time = this.timeFromEvent(event);
    const media = this.mediaAtEvent(event);
    if (media) {
      this.mediaSelection=media.clip.id; this.onMediaSelect?.(media.clip.id);
      if(this.tool==='blade'){
        if(time-media.clip.start>=.08-1e-9 && media.clip.end-time>=.08-1e-9)this.onMediaAction?.('media_split',{clip_id:media.clip.id,time});
        this.releasePointer(event.pointerId);return;
      }
      const px=this.geometry().px;
      const edge=(media.clip.end-media.clip.start)*px>=22 ? (Math.abs(time-media.clip.start)*px<8 ? 'start' : Math.abs(time-media.clip.end)*px<8 ? 'end' : null) : null;
      this.gesture={kind:'media',pointerId:event.pointerId,media:{...media.clip},startTime:time,edge,patch:{},
        previousSelection:this.selection ? {...this.selection} : null,previousRangeSelection:this.selectionIsRange};this.scheduleDraw();return;
    }
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
    this.gesture = { pointerId: event.pointerId, previousSelection: this.selection ? { ...this.selection } : null, clientX: event.clientX, clientY: event.clientY, startTime: time, kind: "scrub" };
    this.gesture.previousRangeSelection = this.selectionIsRange;
    const trimEdge = this.trimEdgeAt(event,time);
    if (trimEdge) {
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
    if (this.gesture && this.gesture.pointerId !== event.pointerId) return;
    if(this.gesture?.kind==='media') {
      const g=this.gesture,clip=g.media,delta=this.timeFromEvent(event)-g.startTime,limit=timelineDuration(this.project);
      const asset=this.project.assets?.[clip.asset_id],timed=asset?.kind!=='image',sourceStart=Number(clip.source_start)||0;
      let patch;
      if(g.edge==='start') {
        const start=Math.max(0,timed ? clip.start-sourceStart : 0,Math.min(clip.end-.08,clip.start+delta));
        patch={start};
        if(timed)patch.source_start=sourceStart+start-clip.start;
        if(asset?.kind==='video')patch.video_source_start=Math.max(0,Number(clip.video_source_start ?? sourceStart)+(start-clip.start)*(clip.speed||1));
      }
      else if(g.edge==='end') {
        const available=Number(asset?.duration),maximum=timed ? (Number.isFinite(available) ? Math.min(limit,clip.start+available-sourceStart) : clip.end) : limit;
        patch={end:Math.max(clip.start+.08,Math.min(maximum,clip.end+delta))};
      }
      else {const start=Math.max(0,Math.min(limit-(clip.end-clip.start),clip.start+delta));patch={start,end:start+clip.end-clip.start};}
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
      this.gesture.trimTime = this.trimEdgeTime(clip,edge,time);
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
    }
    if (["clip", "layout"].includes(this.gesture?.kind) && Math.abs(event.clientX - this.gesture.clientX) > 3) {
      this.gesture.kind = "range";
      this.selectionAnchor = this.snappedTime(this.gesture.startTime, event);
      this.selecting = true;
    }
    if (this.scrubbing || ["range", "edge", "blade", "remove_between"].includes(this.gesture?.kind)) this.seekGesture(time);
    if (this.gesture?.kind === "range" && this.selectionAnchor != null) this.setSelection({ start: this.selectionAnchor, end: this.snappedTime(time, event) }, false, true);
    if (this.gesture?.kind === "edge") {
      const previous = this.gesture.previousSelection;
      const snapped = this.snappedTime(time, event);
      const minimum = this.project?.manual?.sequence ? 1 / 60 : .031;
      const next = this.gesture.edge === "start"
        ? { start: Math.min(snapped, previous.end - minimum), end: previous.end }
        : { start: previous.start, end: Math.max(snapped, previous.start + minimum) };
      this.setSelection(next, false, true);
    }
    this.scheduleDraw();
  }

  pointerUp(event) {
    const gesture = this.gesture;
    if (!gesture || gesture.pointerId !== event.pointerId) return;
    if(this.gesture?.kind==='media') {
      this.pointerMove(event);
      const g=this.gesture;this.gesture=null;this.releasePointer(event.pointerId);this.onMediaPreview?.(g.media.id,null);
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
      this.onSelectionChange?.(this.selection);
      if (gesture.dragged && !gesture.collision && Number.isFinite(gesture.moveStart) && Math.abs(gesture.moveStart - gesture.clip.start) > .001) {
        this.onEdit?.(gesture.target === "edit" || gesture.rangeMove
          ? { action: "sequence_move_range", start: gesture.clip.start, end: gesture.clip.end, to: gesture.moveStart, ...(gesture.target !== "edit" ? { slot: gesture.target } : {}) }
          : { action: "track_move", slot: gesture.target, clip_id: gesture.clip.id, start: gesture.moveStart });
      }
    }
    if (["range", "edge", "clip", "layout"].includes(gesture.kind)) this.onSelectionChange?.(this.selection);
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
    if (!this.canEdit() || this.editPending || event.ctrlKey || event.metaKey || event.altKey) return;
    if(this.mediaSelection && ['Delete','Backspace'].includes(event.key)) {
      event.preventDefault();event.stopPropagation?.();
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
