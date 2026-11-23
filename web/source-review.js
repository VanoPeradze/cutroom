import { TimelineView, formatTime } from "./timeline.js?v=20261117-editing-context1";

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

function analysisOffset(analysis, slot) {
  if (slot !== "B") return 0;
  const value=analysis?.audio_timeline_offset;
  if (value == null || (typeof value !== "number" && typeof value !== "string") || (typeof value === "string" && !value.trim())) return NaN;
  return Number(value);
}

export function sourceReviewAudio(project, slot) {
  if (project?.sources?.[slot]?.has_audio === false) return null;
  // Preparation is measured on the original A/B clocks before AI analysis.
  // Prefer it so manual projects and the non-analyzed source have real audio.
  const prepared=project?.pre_analysis?.audio?.[slot];
  if (prepared) return prepared;
  const analysis=project?.analysis || {};
  const audioSlot=String(analysis.audio_source || project?.draft?.audio_source || "A").toUpperCase();
  if (audioSlot!==slot || !analysis.audio) return null;
  const offset=analysisOffset(analysis,slot);
  if (!Number.isFinite(offset)) return null;
  const duration=Number(project.sources[slot].duration);
  const remap=rows=>(rows || []).map(row=>({...row,start:Math.max(0,row.start-offset),end:Math.min(duration,row.end-offset)})).filter(row=>row.end>row.start);
  return {...analysis.audio,waveform:remap(analysis.audio.waveform),ranges:Object.fromEntries(Object.entries(analysis.audio.ranges || {}).map(([key,rows])=>[key,remap(rows)]))};
}

export class SourceReview {
  constructor({getProject, applyEdit, mediaUrl, pause, exactInsert, dock=null}) {
    Object.assign(this, {getProject, applyEdit, mediaUrl, pause, exactInsert, dock});
    this.generation=0;this.playRequest=0;
    this.dialog = document.getElementById("sourceReviewDialog");
    this.nodes = Object.fromEntries([...this.dialog.querySelectorAll("[data-review]")].map(node => [node.dataset.review,node]));
    const n = this.nodes;
    this.timeline = new TimelineView(n.canvas,n.scroll,time => this.seek(time),range => this.select(range),null,{sourceReview:true,canEdit:()=>!this.busy});
    n.close.onclick = () => this.close({restoreFocus:true});
    this.dialog.addEventListener("close", () => { n.video.pause(); this.timeline.cancelGesture(); n.video.removeAttribute("src"); n.video.load(); });
    n.retry.onclick = () => { if (this.loadPreview({ resume: true })) n.canvas.focus(); };
    n.slot.onchange = () => { if(this.dock && this.blocked())return; this.slot=n.slot.value; this.selection=null; if(this.dock)this.sourceIdentity=this.identity(); this.refresh(true); };
    if(n.refresh)n.refresh.onclick=()=>this.adoptCurrent();
    n.scope.onchange = () => this.updateControls();
    n.restore.onclick = () => this.edit("sequence_source_restore");
    n.remove.onclick = () => this.edit("sequence_source_remove");
    n.undo.onclick = () => this.edit("undo");
    n.previous.onclick = () => this.jump(-1);
    n.next.onclick = () => this.jump(1);
    n.fit.onclick = () => this.timeline.fit();
    n.zoomIn.onclick = () => this.timeline.setZoom(this.timeline.zoom*1.5);
    n.zoomOut.onclick = () => this.timeline.setZoom(this.timeline.zoom/1.5);
    n.exact.onclick = () => {
      if (this.busy || (this.dock && this.blocked()) || this.getProject()?.id !== this.projectId || this.protectedSlots().length) return;
      const selection = this.selection ? {source_start:this.selection.start, source_end:this.selection.end} : {};
      const placement = {projectId:this.projectId, slot:this.slot, scope:n.scope.value === "edit" ? "edit" : "source", ...selection};
      this.close(); this.exactInsert(placement);
    };
    n.video.addEventListener("timeupdate", () => { this.timeline.setPlayhead(n.video.currentTime); this.updateQuote(); });
    n.video.addEventListener("loadedmetadata", () => {
      if (!this.isOpen || (this.dock && !this.valid())) return;
      this.seek(this.resumePreviewAt ?? this.selection?.start ?? 0);
      this.resumePreviewAt=null;
      if (this.previewState === "loading" || this.previewState === "error") {
        n.status.textContent="Preview ready. Click a section or drag to select a range.";
      }
      this.previewState="ready"; n.retry.hidden=true;
    });
    n.video.addEventListener("error", () => {
      if (!this.isOpen || (this.dock && !this.valid()) || !n.video.getAttribute("src")) return;
      this.previewState="error"; n.retry.hidden=false;
      n.status.textContent="Preview could not load. Check that the source file is available and CUTROOM is running, then retry. Your edit and selection have not changed.";
    });
    this.keydown=event=>{
      if(event.defaultPrevented || event.isComposing)return;
      if(this.dock && event.key==='Escape'){event.preventDefault();event.stopPropagation();this.close({restoreFocus:true});return;}
      if(event.code!=="Space" || event.target.closest("input,select,button,video"))return;
      event.preventDefault();event.stopPropagation();
      if(!event.repeat){if(n.video.paused)this.playPreview();else this.pausePreview();}
    };
    this.dialog.addEventListener("keydown",this.keydown);
    n.video.addEventListener('ratechange',()=>{
      if(n.video.defaultPlaybackRate!==1)n.video.defaultPlaybackRate=1;
      if(n.video.playbackRate!==1)n.video.playbackRate=1;
    });
    n.video.addEventListener('play',()=>{
      if(this.dock && (!this.isOpen || this.blocked())){this.pausePreview();return;}
      this.dock?.pauseProgram?.(n.video);
    });
  }

  get isOpen(){return this.dock ? Boolean(this.monitor) : Boolean(this.dialog.open);}
  identity(){return JSON.stringify(this.getProject()?.sources?.[this.slot] || null);}
  valid(){const p=this.getProject();return this.isOpen && p?.id===this.projectId && !!p?.editor_sequence
    && !!p.sources?.[this.slot] && this.dock.token()===this.viewToken && this.identity()===this.sourceIdentity && this.dock.visible()!==false;}
  blocked(){return !this.valid() || this.busy || this.dock.busy?.() || !!this.dock.issue?.() || this.getProject()?.revision!==this.revision;}
  pausePreview(){++this.playRequest;this.nodes.video.pause();}
  playPreview(){
    if(this.dock && this.blocked())return;
    const generation=this.generation,request=++this.playRequest;
    this.dock?.pauseProgram?.(this.nodes.video);
    Promise.resolve(this.nodes.video.play()).then(()=>{
      if(generation!==this.generation){if(!this.isOpen)this.nodes.video.pause();return;}
      if(request!==this.playRequest || !this.isOpen || (this.dock && this.blocked()))this.nodes.video.pause();
    }).catch(()=>{});
  }
  close({force=false,restoreFocus=false}={}){
    if(!this.isOpen || (this.busy && !force))return false;
    if(!this.dock){this.dialog.close();return true;}
    const owned=this.monitor.contains(document.activeElement),opener=this.opener,slot=this.slot;
    ++this.generation;this.pausePreview();this.timeline.cancelGesture();
    this.nodes.video.removeAttribute('src');this.nodes.video.load();
    this.dialog.append(this.shell);this.monitor.remove();this.monitor=null;this.busy=false;
    delete this.dock.root.dataset.primarySourceMonitorOpen;
    this.dock.closed?.();
    if(restoreFocus && owned){const target=opener?.isConnected?opener:this.dock.focusTarget?.(slot);if(target?.isConnected)target.focus();}
    return true;
  }
  sync(){
    if(!this.dock || !this.isOpen)return;
    if(!this.valid()){this.close({force:true});return;}
    if(this.blocked())this.pausePreview();
    this.updateControls();
  }
  adoptCurrent(){
    if(!this.dock || !this.valid() || this.busy || this.dock.busy?.() || this.dock.issue?.())return false;
    this.revision=this.getProject().revision;this.refresh();return true;
  }
  open(target="edit", {slot,opener}={}) {
    const project=this.getProject();
    if (!project?.editor_sequence || (this.dock && (this.busy || this.dock.busy?.() || this.dock.visible()===false))) return false;
    if(this.isOpen)this.close({force:true});
    this.pause(); this.projectId=project.id; this.selection=null;
    this.nodes.status.textContent="Click a section to preview it. Drag to select your own range. Use the ruler to seek anywhere.";
    this.slot=['A','B'].includes(slot)?slot:(target==='B'?'B':'A');
    if(!project.sources?.[this.slot])return false;
    this.nodes.scope.value=target === "edit" ? "edit" : "source";
    if(this.dock){
      this.revision=project.revision;this.viewToken=this.dock.token();this.sourceIdentity=this.identity();++this.generation;
      this.opener=opener||document.activeElement;
      this.shell=this.dialog.querySelector('.source-review-shell');
      const region=document.createElement('section');region.className='source-review-monitor';region.dataset.editorShortcuts='off';region.setAttribute('role','region');region.setAttribute('aria-label',`Original source ${this.slot}`);
      region.addEventListener('keydown',this.keydown);region.append(this.shell);this.dock.root.prepend(region);this.monitor=region;
      this.dock.root.dataset.primarySourceMonitorOpen='true';
    }else this.dialog.showModal();
    this.refresh(true);
    if(this.dock){this.monitor.scrollIntoView({block:'start',inline:'nearest'});this.nodes.canvas.focus({preventScroll:true});}
    else this.nodes.canvas.focus();
    return true;
  }

  refresh(sourceChanged=false) {
    const p=this.getProject(),n=this.nodes;
    if (p?.id !== this.projectId || !p.editor_sequence || !p.sources[this.slot]) { this.close({force:true}); return; }
    this.ranges=sourceReviewRanges(p,this.slot);
    n.slot.value=this.slot;
    this.monitor?.setAttribute('aria-label',`Original source ${this.slot}`);
    n.slot.querySelector('option[value="B"]').disabled=!p.sources.B;
    n.scope.hidden=!p.sources.B;
    const waveform=sourceReviewAudio(p,this.slot);
    this.timeline.setProject({id:`${p.id}:${this.slot}`,__sourceReview:true,settings:p.settings,sources:{A:{...p.sources[this.slot],thumbnail_urls:p.sources[this.slot].thumbnail_urls || p.analysis?.thumbnail_urls?.[this.slot]}},
      analysis:{audio:waveform},draft:{keep_ranges:this.ranges.keeps,cuts:this.ranges.removed,camera_plan:[]}});
    if (sourceChanged) {
      this.loadPreview();
      this.timeline.fit();
      const first=this.ranges.removed[0];
      this.selection=first ? {...first} : null;
    }
    if (this.selection) this.timeline.setSelection(this.selection,false,true);
    this.updateControls();
  }

  loadPreview({ resume = false } = {}) {
    const p=this.getProject(),n=this.nodes;
    if (!this.isOpen || this.busy || p?.id !== this.projectId || !p.sources?.[this.slot]) return false;
    this.resumePreviewAt=resume ? Number(n.video.currentTime ?? this.selection?.start ?? 0) : null;
    this.previewState="loading"; n.retry.hidden=true;
    n.status.textContent="Loading original preview. Your edit stays unchanged.";
    n.video.defaultPlaybackRate=1;n.video.playbackRate=1;
    n.video.src=this.mediaUrl(p.sources[this.slot]); n.video.load();
    return true;
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
    const offset=analysisOffset(p?.analysis,audioSlot);
    const time=n.video.currentTime + offset;
    const segment=audioSlot===this.slot && Number.isFinite(offset) ? p.analysis?.transcript?.segments?.find(s=>time>=s.start&&time<s.end) : null;
    n.quote.textContent=segment?.text || "Preview the original footage here. Your edited preview stays separate.";
  }

  protectedSlots() {
    const project = this.getProject(), scope = this.nodes.scope.value;
    return ['A','B'].filter(slot => project?.sources?.[slot] && project?.manual?.track_locks?.[slot] === true && (scope === 'edit' || slot === this.slot));
  }

  updateControls() {
    const n=this.nodes,stats=reviewSelectionStats(this.ranges,this.selection);
    const fps=Number(this.getProject()?.settings?.fps);
    const minimum=1/([24,25,30,50,60].includes(fps)?fps:30)-1e-6;
    const locked=this.protectedSlots();
    n.restore.disabled=this.busy || locked.length>0 || stats.removed<minimum;
    n.remove.disabled=this.busy || locked.length>0 || stats.kept<minimum;
    const history=this.getProject()?.manual?.history || this.getProject()?.manual_history || {};
    n.undo.disabled=this.busy || !(history.undo_count ?? history.undo?.length);
    for (const key of ["slot","scope","exact"]) n[key].disabled=Boolean(this.busy);
    n.exact.disabled ||= locked.length>0;
    const time=this.selection?.start ?? n.video.currentTime;
    n.previous.disabled=!this.ranges.removed.some(r=>r.start<time-1e-6);
    n.next.disabled=!this.ranges.removed.some(r=>r.start>time+1e-6);
    n.selection.textContent=this.selection ? `${formatTime(this.selection.start,true)} – ${formatTime(this.selection.end,true)} · ${stats.kept.toFixed(1)}s in edit · ${stats.removed.toFixed(1)}s removed` : "Click a kept or removed section, or drag to select any range.";
    n.summary.textContent=`Original ${formatTime(this.ranges.duration)} · ${this.ranges.removed.length} removed ${this.ranges.removed.length===1 ? "section" : "sections"}`;
    n.effect.textContent=n.scope.value === "edit" ? (this.getProject()?.sources?.B ? "Restore inserts only missing footage near its source neighbors, with synchronized A/B. Remove cuts all uses of the selection from both tracks and closes the gap." : "Restore inserts only missing footage near its source neighbors. Remove cuts all uses of the selection from this source track and closes the gap.") : `Source ${this.slot} only. Remove leaves a gap; restore fills it when possible, otherwise inserts on this track. Other-source clips stay still.`;
    if (locked.length) n.effect.textContent=`Track ${locked.join(' + ')} is locked. You can preview; unlock in Edit → Track protection before changing this scope.`;
    if(this.dock){
      const stale=this.getProject()?.revision!==this.revision,blocked=this.blocked();
      for(const key of ['restore','remove','undo','exact','slot','scope'])n[key].disabled ||= Boolean(blocked);
      n.close.disabled=Boolean(this.busy);n.video.controls=!blocked;
      if(n.refresh){n.refresh.hidden=!stale;n.refresh.disabled=Boolean(this.busy||this.dock.busy?.()||this.dock.issue?.());}
      if(n.context)n.context.textContent=stale?'The saved edit changed. Use current edit to review updated coverage before changing footage.':this.dock.issue?.()||'Original source picture and sound, without edited effects or mix. Coverage uses normal source clocks, not retimed-picture coverage.';
    }
    this.updateQuote();
  }

  async edit(action) {
    if (this.busy || (this.dock && this.blocked()) || this.getProject()?.id!==this.projectId || (!this.selection && action!=="undo")) return;
    if (action!=="undo" && this.protectedSlots().length) { this.updateControls(); return; }
    const generation=this.generation,revision=this.revision;
    const admission=()=>this.generation===generation && this.valid() && this.getProject()?.revision===revision && !this.dock.issue?.();
    this.busy=true; this.pausePreview(); this.updateControls();
    this.nodes.status.textContent="Updating edit…";
    try {
      const detail=action === "undo" ? {} : {slot:this.slot,scope:this.nodes.scope.value === "edit" ? "edit" : this.slot,source_start:this.selection.start,source_end:this.selection.end};
      const result=await this.applyEdit(action,detail,this.dock?{strictRevision:true,isCurrent:()=>this.generation===generation&&this.valid(),admissionCurrent:admission}:undefined);
      if(this.dock){
        if(this.generation!==generation || !this.valid())return;
        const current=this.getProject();
        if(!result || result.id!==current.id || result.revision!==current.revision || !Number.isInteger(result.revision)){this.nodes.status.textContent='The edit was not confirmed. Use current edit before trying again.';return;}
        this.revision=current.revision;
      }
      this.refresh();
      this.nodes.status.textContent=result ? (action === "undo" ? "Undone." : action === "sequence_source_restore" ? "Footage restored. Already-kept footage was not duplicated." : "Selection removed from the edit. The original is still here.") : "The edit was not confirmed. Check the current project before trying again.";
    } catch (error) {
      if(this.dock && (this.generation!==generation || !this.valid()))return;
      this.nodes.status.textContent="Could not confirm whether the edit changed. Close and reopen the project to check it before trying again.";
    } finally { if(!this.dock || this.generation===generation){this.busy=false;this.updateControls();} }
  }
}
