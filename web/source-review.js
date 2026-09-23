import { TimelineView, formatTime } from "./timeline.js?v=1.1-beta-3";

// Project current edit clips onto the original recording, including copies.
// The original draft's keep mask is intentionally not authoritative anymore.
export function sourceReviewRanges(project, slot) {
  const duration = Number(project?.sources?.[slot]?.duration || 0);
  const keeps = [];
  const clips = project?.editor_sequence?.source_tracks?.[slot] || [];
  const ranges = clips.map(c => ({start: Math.max(0, c.source_start), end: Math.min(duration, c.source_start + c.end - c.start)}))
    .filter(r => r.end > r.start).sort((a,b) => a.start - b.start);
  for (const range of ranges) {
    const last = keeps.at(-1);
    if (last && range.start <= last.end + 1e-6) last.end = Math.max(last.end, range.end);
    else keeps.push({...range});
  }
  const removed = [];
  let cursor = 0;
  for (const range of keeps) {
    if (range.start > cursor + 1e-6) removed.push({start:cursor,end:range.start});
    cursor = range.end;
  }
  if (cursor < duration - 1e-6) removed.push({start:cursor,end:duration});
  return {keeps, removed, duration};
}

export function reviewSelectionStats(ranges, selection) {
  if (!selection) return {kept:0, removed:0};
  const kept = ranges.keeps.reduce((n,r) => n + Math.max(0, Math.min(r.end,selection.end)-Math.max(r.start,selection.start)),0);
  return {kept,removed:Math.max(0,selection.end-selection.start-kept)};
}

export function sourceReviewAudio(project, slot) {
  const analysis=project?.analysis || {};
  const audioSlot=String(analysis.audio_source || project?.draft?.audio_source || "A").toUpperCase();
  if (audioSlot!==slot || !analysis.audio) return null;
  const offset=slot==="B" ? Number(analysis.audio_timeline_offset) : 0;
  if (!Number.isFinite(offset)) return null;
  const duration=Number(project.sources[slot].duration);
  const remap=rows=>(rows || []).map(row=>({...row,start:Math.max(0,row.start-offset),end:Math.min(duration,row.end-offset)})).filter(row=>row.end>row.start);
  return {...analysis.audio,waveform:remap(analysis.audio.waveform),ranges:Object.fromEntries(Object.entries(analysis.audio.ranges || {}).map(([key,rows])=>[key,remap(rows)]))};
}

export class SourceReview {
  constructor({getProject, applyEdit, mediaUrl, pause, exactInsert}) {
    Object.assign(this, {getProject, applyEdit, mediaUrl, pause, exactInsert});
    this.dialog = document.getElementById("sourceReviewDialog");
    this.nodes = Object.fromEntries([...this.dialog.querySelectorAll("[data-review]")].map(node => [node.dataset.review,node]));
    const n = this.nodes;
    this.timeline = new TimelineView(n.canvas,n.scroll,time => this.seek(time),range => this.select(range),null,{sourceReview:true,canEdit:()=>!this.busy});
    n.close.onclick = () => this.dialog.close();
    this.dialog.addEventListener("close", () => { n.video.pause(); this.timeline.cancelGesture(); n.video.removeAttribute("src"); n.video.load(); });
    n.slot.onchange = () => { this.slot=n.slot.value; this.selection=null; this.refresh(true); };
    n.scope.onchange = () => this.updateControls();
    n.restore.onclick = () => this.edit("sequence_source_restore");
    n.remove.onclick = () => this.edit("sequence_source_remove");
    n.undo.onclick = () => this.edit("undo");
    n.previous.onclick = () => this.jump(-1);
    n.next.onclick = () => this.jump(1);
    n.fit.onclick = () => this.timeline.fit();
    n.zoomIn.onclick = () => this.timeline.setZoom(this.timeline.zoom*1.5);
    n.zoomOut.onclick = () => this.timeline.setZoom(this.timeline.zoom/1.5);
    n.exact.onclick = () => { this.dialog.close(); this.exactInsert(); };
    n.video.addEventListener("timeupdate", () => { this.timeline.setPlayhead(n.video.currentTime); this.updateQuote(); });
    n.video.addEventListener("loadedmetadata", () => this.seek(this.selection?.start || 0));
    n.video.addEventListener("error", () => { if (this.dialog.open && n.video.getAttribute("src")) n.status.textContent="This source could not be played. Try closing and reopening the project."; });
    this.dialog.addEventListener("keydown", event => {
      if (event.code !== "Space" || event.target.closest("input,select,button,video")) return;
      event.preventDefault(); event.stopPropagation();
      if (!event.repeat) { if (n.video.paused) n.video.play().catch(()=>{}); else n.video.pause(); }
    });
  }

  open(target="edit") {
    const project=this.getProject();
    if (!project?.editor_sequence) return false;
    this.pause(); this.projectId=project.id; this.selection=null;
    this.nodes.status.textContent="Click a section to preview it. Drag to select your own range. Use the ruler to seek anywhere.";
    this.slot=target === "B" ? "B" : "A";
    this.nodes.scope.value=target === "edit" ? "edit" : "source";
    this.dialog.showModal(); this.refresh(true); this.nodes.canvas.focus();
    return true;
  }

  refresh(sourceChanged=false) {
    const p=this.getProject(),n=this.nodes;
    if (p?.id !== this.projectId || !p.editor_sequence || !p.sources[this.slot]) { this.dialog.close(); return; }
    this.ranges=sourceReviewRanges(p,this.slot);
    n.slot.value=this.slot;
    n.slot.querySelector('option[value="B"]').disabled=!p.sources.B;
    n.scope.hidden=!p.sources.B;
    const waveform=sourceReviewAudio(p,this.slot);
    this.timeline.setProject({id:`${p.id}:${this.slot}`,__sourceReview:true,settings:p.settings,sources:{A:{...p.sources[this.slot],thumbnail_urls:p.sources[this.slot].thumbnail_urls || p.analysis?.thumbnail_urls?.[this.slot]}},
      analysis:{audio:waveform},draft:{keep_ranges:this.ranges.keeps,cuts:this.ranges.removed,camera_plan:[]}});
    if (sourceChanged) {
      n.video.src=this.mediaUrl(p.sources[this.slot]); n.video.load();
      this.timeline.fit();
      const first=this.ranges.removed[0];
      this.selection=first ? {...first} : null;
    }
    if (this.selection) this.timeline.setSelection(this.selection,false,true);
    this.updateControls();
  }

  select(range) {
    this.selection=range;
    if (range) this.seek(range.start);
    this.updateControls();
  }

  seek(time) {
    this.nodes.video.pause();
    this.nodes.video.currentTime=Math.max(0,Math.min(this.ranges.duration,time));
    this.timeline.setPlayhead(this.nodes.video.currentTime);
    this.updateQuote();
  }

  jump(direction) {
    const time=this.selection?.start ?? this.nodes.video.currentTime;
    const ranges=direction>0 ? this.ranges.removed : [...this.ranges.removed].reverse();
    const next=ranges.find(r=>direction>0 ? r.start>time+1e-6 : r.start<time-1e-6);
    if (next) { this.timeline.selectRange(next.start,next.end); this.timeline.followPlayhead(); }
  }

  updateQuote() {
    const p=this.getProject(),n=this.nodes;
    // Transcript timestamps belong to their audio source, never the other lane.
    const audioSlot=String(p?.analysis?.audio_source || p?.draft?.audio_source || "A").toUpperCase();
    const time=n.video.currentTime + (audioSlot === "B" ? Number(p?.analysis?.audio_timeline_offset) : 0);
    const segment=audioSlot===this.slot ? p.analysis?.transcript?.segments?.find(s=>time>=s.start&&time<s.end) : null;
    n.quote.textContent=segment?.text || "Preview the original footage here. Your edited preview stays separate.";
  }

  updateControls() {
    const n=this.nodes,stats=reviewSelectionStats(this.ranges,this.selection);
    const fps=Number(this.getProject()?.settings?.fps);
    const minimum=1/([24,25,30,50,60].includes(fps)?fps:30)-1e-6;
    n.restore.disabled=this.busy || stats.removed<minimum;
    n.remove.disabled=this.busy || stats.kept<minimum;
    const history=this.getProject()?.manual?.history || this.getProject()?.manual_history || {};
    n.undo.disabled=this.busy || !(history.undo_count ?? history.undo?.length);
    for (const key of ["slot","scope","exact"]) n[key].disabled=Boolean(this.busy);
    const time=this.selection?.start ?? n.video.currentTime;
    n.previous.disabled=!this.ranges.removed.some(r=>r.start<time-1e-6);
    n.next.disabled=!this.ranges.removed.some(r=>r.start>time+1e-6);
    n.selection.textContent=this.selection ? `${formatTime(this.selection.start,true)} – ${formatTime(this.selection.end,true)} · ${stats.kept.toFixed(1)}s in edit · ${stats.removed.toFixed(1)}s removed` : "Click a kept or removed section, or drag to select any range.";
    n.summary.textContent=`Original ${formatTime(this.ranges.duration)} · ${this.ranges.removed.length} removed ${this.ranges.removed.length===1 ? "section" : "sections"}`;
    n.effect.textContent=n.scope.value === "edit" ? "Restore inserts only missing footage near its source neighbors, with synchronized A/B. Remove cuts all uses of the selection from both tracks and closes the gap." : `Source ${this.slot} only. Remove leaves a gap; restore fills it when possible, otherwise inserts on this track. Other-source clips stay still.`;
    this.updateQuote();
  }

  async edit(action) {
    if (this.busy || this.getProject()?.id!==this.projectId || (!this.selection && action!=="undo")) return;
    this.busy=true; this.nodes.video.pause(); this.updateControls();
    this.nodes.status.textContent="Updating edit…";
    try {
      const detail=action === "undo" ? {} : {slot:this.slot,scope:this.nodes.scope.value === "edit" ? "edit" : this.slot,source_start:this.selection.start,source_end:this.selection.end};
      const result=await this.applyEdit(action,detail);
      this.refresh();
      this.nodes.status.textContent=result ? (action === "undo" ? "Undone." : action === "sequence_source_restore" ? "Footage restored. Already-kept footage was not duplicated." : "Selection removed from the edit. The original is still here.") : "The edit was not changed. Select the section again and retry.";
    } finally { this.busy=false; this.updateControls(); }
  }
}
