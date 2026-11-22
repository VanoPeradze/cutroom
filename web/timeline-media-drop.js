import { formatFrameTime, timelineDuration, timelineLayerTrackState } from "./timeline.js?v=20261117-editing-context1";

export const LIBRARY_DRAG_TYPE = "application/x-cutroom-asset";
const MIN_CLIP = .08;

export function libraryDragIdentity(project, assetId) {
  const asset = project?.assets?.[assetId];
  if (!project?.id || typeof assetId !== "string" || !asset || asset.status !== "ready"
    || !["video", "audio", "image"].includes(asset.kind)) return null;
  return JSON.stringify([project.id, assetId, asset.kind, asset.url, asset.generation,
    asset.duration, asset.width, asset.height, asset.has_audio]);
}

// Saved track membership is a drag intent, not a preference that can silently
// fall back to automatic assignment after a rename, migration or replacement.
function libraryTrackIdentity(project) {
  const manual = project?.manual || {};
  return JSON.stringify([Object.hasOwn(manual, "layer_tracks"), manual.layer_tracks,
    ...[manual.media_clips, manual.text_clips].map(rows => Array.isArray(rows)
      ? rows.map(clip => clip && [clip.id, clip.track_id, clip.start, clip.end, clip.enabled]) : rows), timelineDuration(project)]);
}

// Legacy placement keeps its original Overlay/Add/Append/Insert policy.
// Persisted-track placement requires an explicit compatible row and the host's
// canonical final-arrangement planner. Automatic remains a keyboard choice.
export function libraryDropPlacement(project, assetId, requestedTime,
  { insert = false, insertionIssue, trackId, placementPreview, sourceStart, sourceEnd } = {}) {
  const asset = project?.assets?.[assetId], duration = timelineDuration(project);
  if (!project?.draft || !project?.manual?.sequence || !(duration > 0)) return { error: "Import a first video and open the edit timeline before placing media." };
  if (!libraryDragIdentity(project, assetId)) return { error: "Choose a ready imported asset from this project." };
  if (!Number.isFinite(requestedTime) || requestedTime < 0) return { error: "Choose a position on the timeline." };
  const marked = sourceStart !== undefined || sourceEnd !== undefined;
  if (marked && (asset.kind === "image" || ![sourceStart, sourceEnd].every(Number.isFinite)
    || sourceStart < 0 || sourceEnd > asset.duration || sourceEnd - sourceStart < MIN_CLIP - 1e-9))
    return { error: "Choose valid source In / Out for this exact media file before dragging." };
  const source = marked ? { sourceStart, sourceEnd } : {};
  const available = marked ? Math.round((sourceEnd - sourceStart) * 1e9) / 1e9 : asset.kind === "image" ? 5 : Number(asset.duration);
  if (!Number.isFinite(available) || available < MIN_CLIP) return { error: "This media is too short to place on the timeline." };
  const append = requestedTime > duration - MIN_CLIP + 1e-9;
  if (append && asset.kind !== "video") return { error: "Place audio or images inside the edit. Append a video first to extend it." };
  insert = Boolean(insert && !append);
  if (insert && asset.kind !== "video") return { error: "Only video can insert time. Release Shift to add audio or overlay an image." };
  const start = append ? duration : requestedTime;
  const end = append || insert ? start + available : Math.min(duration, start + available);
  const label = append ? "Append video" : insert ? "Insert video" : asset.kind === "audio" ? "Add audio" : `Overlay ${asset.kind}`;
  const base = { assetId, kind: asset.kind, append, ...(insert ? { insert: true } : {}), start, end, label, ...source };
  const state = timelineLayerTrackState(project);
  if (state.enabled) {
    if (!state.valid) return { error: "The saved track model is incompatible. Review Tracks before placing media." };
    const track = state.tracks.find(row => row.id === trackId);
    if (!track) return { error: "Drop onto a compatible saved track. Use Destination track in Media for Automatic placement." };
    const kind = asset.kind === "audio" ? "audio" : "visual";
    if (track.kind !== kind) return { error: `Choose a ${kind} track for this ${asset.kind}. A/B and custom text are separate.` };
    if (typeof placementPreview !== "function") return { error: "Track placement is unavailable here. Reload the editor before placing media." };
    let plan;
    try { plan = placementPreview(assetId, start, { append, insert, trackId, ...source }); } catch { /* Fail closed. */ }
    if (!plan || typeof plan.issue !== "string") return { error: "The destination could not be verified. Drag again after checking Tracks." };
    if (plan.issue) return { error: plan.issue };
    if (plan.trackId !== trackId || !Number.isFinite(plan.start) || !Number.isFinite(plan.end)
      || Math.abs(plan.start - start) > 1e-8 || Math.abs(plan.end - end) > 1e-8 || plan.end - plan.start < MIN_CLIP - 1e-9)
      return { error: "The destination could not be verified. Drag again after checking Tracks." };
    return { ...base, start: plan.start, end: plan.end, trackId, trackName: track.name, label: `${label} on ${track.name}` };
  }
  if (trackId !== undefined) return { error: "Enable editable tracks before choosing a destination track." };
  // Automatic/legacy rows still share native admission (clip limits, append
  // readiness and saved-data guards). A green ghost must not promise an edit
  // that the same host planner already knows it will refuse on drop.
  if (typeof placementPreview === "function") {
    let plan;
    try { plan = placementPreview(assetId, start, { append, insert, ...source }); } catch { /* Fail closed. */ }
    if (!plan || typeof plan.issue !== "string") return { error: "The placement could not be verified. Drag again after reviewing Media." };
    if (plan.issue) return { error: plan.issue };
    if (!Number.isFinite(plan.start) || !Number.isFinite(plan.end) || plan.trackId !== undefined
      || Math.abs(plan.start - start) > 1e-8 || Math.abs(plan.end - end) > 1e-8)
      return { error: "The placement could not be verified. Drag again after reviewing Media." };
  }
  if (insert) {
    if (typeof insertionIssue !== "function") return { error: "Insert is unavailable here. Release Shift for Overlay, or review source In / Out." };
    let issue;
    try { issue = insertionIssue(assetId, requestedTime, source); } catch { issue = null; }
    if (typeof issue !== "string") return { error: "Insert readiness could not be confirmed. Review source In / Out before inserting." };
    if (issue) return { error: issue };
  }
  return base;
}

export function readLibraryDrag(raw, origin) {
  if (!origin || typeof raw !== "string" || raw.length > 1024) return null;
  try {
    const data = JSON.parse(raw);
    return data?.version === 1 && data.project_id === origin.project_id && data.asset_id === origin.asset_id ? data : null;
  } catch { return null; }
}

export function initTimelineMediaDrop(timeline, { document: doc = timeline?.canvas?.ownerDocument,
  place, canPlace = () => true, insertionIssue, placementPreview, sourceSelection, sourceRoot } = {}) {
  if (timeline?.libraryDrop) return timeline.libraryDrop;
  const canvas = timeline?.canvas, scroll = timeline?.scroll, dock = scroll?.closest?.(".studio-timeline-dock"),
    library = doc?.querySelector?.(".media-library");
  if (!doc?.createElement || !dock || !library || timeline.sourceReview || typeof place !== "function") return null;
  const feedback = doc.createElement("p"); feedback.className = "timeline-drop-feedback";
  feedback.setAttribute("role", "status"); feedback.setAttribute("aria-live", "polite"); feedback.hidden = true;
  dock.append(feedback);
  const savedCards = new Map(), listeners = [], win = doc.defaultView;
  let origin = null, preview = null, pending = false, hideTimer = null, destroyed = false, feedbackContext = null;
  const listen = (node, name, handler, options) => { node.addEventListener(name, handler, options); listeners.push(() => node.removeEventListener(name, handler, options)); };
  const setFeedback = (text, state = "ready", temporary = false) => {
    feedbackContext = null;
    if (hideTimer != null) { win.clearTimeout(hideTimer); hideTimer = null; }
    feedback.textContent = text; feedback.dataset.state = state; feedback.hidden = !text;
    if (temporary) hideTimer = win.setTimeout(() => { feedback.hidden = true; hideTimer = null; }, 4500);
  };
  const ready = () => !destroyed && !pending && timeline.canNavigate() && canPlace();
  const selection = assetId => {
    if (typeof sourceSelection !== "function") return null;
    try {
      const selected = sourceSelection(assetId);
      if (selected == null) return null;
      if (selected.issue) return { issue: selected.issue };
      if (![selected.sourceStart, selected.sourceEnd].every(Number.isFinite)) throw Error();
      return { sourceStart: selected.sourceStart, sourceEnd: selected.sourceEnd };
    } catch { return { issue: "The source selection could not be verified. Open this source and review In / Out." }; }
  };
  const current = (saved = origin) => Boolean(!destroyed && saved && timeline.project?.id === saved.project_id
    && timeline.project?.revision === saved.revision
    && libraryDragIdentity(timeline.project, saved.asset_id) === saved.identity
    && libraryTrackIdentity(timeline.project) === saved.tracks
    && JSON.stringify(selection(saved.asset_id)) === JSON.stringify(saved.selection));
  const clearPreview = () => {
    preview = null; timeline.snapGuide = null; dock.classList.remove("library-drag-active"); timeline.scheduleDraw();
  };
  const cancel = () => { origin = null; timeline.libraryDragActive = false; clearPreview(); if (!pending) { feedback.dataset.operation = ""; setFeedback(""); } };
  const decorate = () => {
    for (const card of library.querySelectorAll(".media-asset")) {
      const id = card.querySelector("button[data-asset]")?.dataset.asset;
      const enabled = Boolean(id && libraryDragIdentity(timeline.project, id));
      if (!savedCards.has(card)) savedCards.set(card, { draggable: card.getAttribute("draggable"), title: card.getAttribute("title") });
      card.draggable = enabled;
      card.classList.toggle("timeline-draggable", enabled);
      if (enabled) card.title = timelineLayerTrackState(timeline.project).enabled
        ? "Drag onto a compatible saved track. Hold Shift to Insert video and move later clips; drop at the end to Append. Uses active or saved In / Out for video/audio. Use Destination track for keyboard or Automatic placement."
        : timeline.project.assets[id].kind === "video" && typeof insertionIssue === "function"
        ? "Drag to Overlay; hold Shift to Insert and move later clips across tracks. Drop at the end to Append. Uses this source's active or saved In / Out; otherwise the full video."
        : timeline.project.assets[id].kind === "image" ? "Drag inside the edit to overlay this image. Card buttons also support keyboard placement."
        : "Drag onto the timeline to place a copy. Uses this source's active or saved In / Out. Card buttons also support keyboard placement.";
    }
    for (const card of savedCards.keys()) if (!library.contains(card)) savedCards.delete(card);
  };
  const refresh = () => {
    decorate();
    if (origin && !current()) { cancel(); setFeedback("The project or source selection changed. Drag the media again.", "blocked", true); }
    if (feedbackContext && (timeline.project?.id !== feedbackContext.id || timeline.project?.revision !== feedbackContext.revision)) setFeedback("");
  };
  const placement = event => {
    if (!origin || !current()) return { error: "The project or source selection changed. Drag the media again." };
    if (!ready()) return { error: "Finish the current edit or import before placing media." };
    const time = timeline.snappedTime(timeline.splitTime(timeline.timeFromEvent(event)), event);
    const tracked = timelineLayerTrackState(timeline.project).enabled;
    const row = tracked ? timeline.mediaRowAtEvent?.(event) : null;
    const plan = libraryDropPlacement(timeline.project, origin.asset_id, time,
      { insert: Boolean(event.shiftKey), insertionIssue, placementPreview, ...origin.selection, ...(tracked ? { trackId: row?.trackId } : {}) });
    if (!plan.error && tracked) {
      if (!Number.isFinite(row?.top) || !Number.isFinite(row?.bottom) || row.bottom <= row.top)
        return { error: "The destination row could not be verified. Drag again after checking Tracks." };
      plan.row = { top: row.top, bottom: row.bottom };
    }
    return plan;
  };
  const showPlacement = plan => {
    preview = plan.error ? null : plan;
    feedback.dataset.operation = plan.insert ? "insert" : plan.append ? "append" : "add";
    dock.classList.toggle("library-drag-active", Boolean(preview));
    if (plan.error) { timeline.snapGuide = null; setFeedback(plan.error, "blocked"); }
    else {
      const asset = timeline.project.assets[plan.assetId], fps = Number(timeline.project.settings?.fps) || 30;
      const duration = formatFrameTime(plan.end - plan.start, fps);
      const sourceIn = plan.sourceStart ?? 0, sourceOut = sourceIn + plan.end - plan.start;
      const sourceText = asset.kind === "image" ? "" : ` · Source ${sourceIn.toFixed(3)}–${sourceOut.toFixed(3)} s${plan.sourceEnd > sourceOut + 1e-8 ? "; shortened at edit end" : ""}`;
      setFeedback(`${plan.label} at ${formatFrameTime(plan.start, fps)} · ${plan.insert ? `+${duration}; moves later clips across tracks` : duration} · Edit ${formatFrameTime(plan.start, fps)}–${formatFrameTime(plan.end, fps)}${sourceText} · ${asset.name || "Imported media"}`);
    }
    timeline.scheduleDraw();
  };
  listen(doc, "dragstart", event => {
    const sourceHandle = event.target.closest?.("[data-source-drag]"), card = event.target.closest?.(".media-asset");
    const sourceOwner = sourceHandle?.closest?.(".library-source-monitor");
    const studio = sourceRoot?.();
    if (!(card && library.contains(card)) && !(sourceHandle && sourceOwner && studio?.contains(sourceOwner))) return;
    if (event.target.closest?.("button,input,select,textarea,a") || !ready()) { event.preventDefault(); return; }
    const assetId = sourceHandle ? sourceOwner.dataset.sourceAssetId : card.querySelector("button[data-asset]")?.dataset.asset;
    const identity = libraryDragIdentity(timeline.project, assetId), selected = selection(assetId);
    if (sourceHandle && (sourceOwner.dataset.sourceProjectId !== timeline.project?.id || sourceHandle.draggable !== true)
      || selected?.issue) { event.preventDefault(); setFeedback(selected?.issue || "Review a ready source selection before dragging.", "blocked", true); return; }
    if (!identity || !timeline.project?.draft || !timeline.project?.manual?.sequence || !event.dataTransfer) { event.preventDefault(); return; }
    origin = { project_id: timeline.project.id, asset_id: assetId, revision: timeline.project.revision, identity, tracks: libraryTrackIdentity(timeline.project), selection: selected };
    try {
      event.dataTransfer.clearData(); event.dataTransfer.effectAllowed = "copy";
      event.dataTransfer.setData(LIBRARY_DRAG_TYPE, JSON.stringify({ version: 1, project_id: origin.project_id, asset_id: assetId }));
    } catch { event.preventDefault(); cancel(); return; }
    timeline.libraryDragActive = true;
    setFeedback(timelineLayerTrackState(timeline.project).enabled
      ? "Drop onto a compatible saved track. Shift inserts video and moves later clips; drop at the end to Append. Choose Automatic in Media instead of dragging."
      : typeof insertionIssue === "function" && timeline.project.assets[assetId].kind === "video"
      ? "Drop to Overlay. Hold Shift to Insert and move later clips across tracks. Drop at the end to Append. Active or saved In / Out is used; originals unchanged."
      : "Drop inside the edit to place media. Drop a video at the end to append it. Originals stay unchanged.");
  });
  listen(scroll, "dragover", event => {
    event.preventDefault();
    if (!origin) { if (event.dataTransfer) event.dataTransfer.dropEffect = "none"; return; }
    const plan = placement(event);
    if (event.dataTransfer) event.dataTransfer.dropEffect = plan.error ? "none" : "copy";
    showPlacement(plan);
  });
  listen(scroll, "dragleave", event => {
    if (scroll.contains(event.relatedTarget)) return;
    clearPreview(); if (!pending) setFeedback("");
  });
  listen(scroll, "drop", async event => {
    event.preventDefault(); event.stopPropagation();
    if (pending || destroyed) return;
    if (!readLibraryDrag(event.dataTransfer?.getData(LIBRARY_DRAG_TYPE), origin)) {
      cancel(); setFeedback("Drag an imported asset from this Media pool. Import external files first.", "blocked", true); return;
    }
    const plan = placement(event), projectId = timeline.project.id;
    if (plan.error) { cancel(); setFeedback(plan.error, "blocked", true); return; }
    const previousIds = new Set((timeline.project.manual?.media_clips || []).map(clip => clip.id)), dragOrigin = origin;
    origin = null; timeline.libraryDragActive = false; clearPreview(); pending = true; timeline.editPending = true;
    feedback.dataset.operation = plan.insert ? "insert" : plan.append ? "append" : "add";
    timeline.cancelPendingCut(); timeline.onToolStateChange?.();
    setFeedback(`${plan.label}…`, "pending");
    let result;
    try { result = await place(plan.assetId, plan.start, { append: plan.append, ...(plan.insert ? { insert: true } : {}), ...(plan.trackId ? { trackId: plan.trackId } : {}), ...dragOrigin.selection }, { isCurrent: () => current(dragOrigin) }); }
    catch { /* The media controller reports its own edit error. */ }
    finally { pending = false; timeline.editPending = false; timeline.onToolStateChange?.(); timeline.scheduleDraw(); }
    if (destroyed || timeline.project?.id !== projectId) { setFeedback(""); return; }
    // Native placement actions append their own occurrence. A revision
    // retry may also return an earlier occurrence created in another window.
    const clip = result?.id === projectId && result.manual?.media_clips?.filter(item => item.asset_id === plan.assetId && !previousIds.has(item.id)).at(-1);
    if (!clip || plan.trackId && clip.track_id !== plan.trackId || plan.sourceStart !== undefined
      && (![clip.start, clip.end, clip.source_start].every(Number.isFinite)
        || Math.abs(clip.start - plan.start) > 1e-8 || Math.abs(clip.end - plan.end) > 1e-8
        || Math.abs(clip.source_start - plan.sourceStart) > 1e-8 || (clip.speed ?? 1) !== 1
        || clip.video_source_start !== undefined && Math.abs(clip.video_source_start - plan.sourceStart) > 1e-8)) { setFeedback("Placement was not confirmed. Check the timeline and Media panel before retrying.", "blocked", true); return; }
    timeline.selectIndexEntry(`media::${clip.id}`);
    setFeedback(plan.insert ? "Video inserted; all later clips shifted. Undo is available."
      : `${plan.append ? "Video appended" : "Media placed"}. Undo is available.`, "ready", true);
    feedbackContext = { id: timeline.project.id, revision: timeline.project.revision };
  });
  listen(doc, "dragend", () => { if (origin || preview) cancel(); });
  listen(doc, "keydown", event => { if (event.key === "Escape" && origin) cancel(); }, true);
  const Observer = win?.MutationObserver;
  const observer = typeof Observer === "function" ? new Observer(decorate) : null;
  observer?.observe(library, { childList: true, subtree: true });
  const controller = {
    refresh,
    draw(ctx, px, width, height) {
      if (!preview) return;
      const x = preview.start * px, end = Math.min(width, preview.end * px);
      if (preview.insert) {
        // Insert opens time at one boundary. Do not shade the existing clips
        // as though the operation would overlay or replace them.
        const arrow = Math.min(width - 4, x + 36);
        ctx.save(); ctx.strokeStyle = timeline.color("selected", "#bca9df"); ctx.lineWidth = 2; ctx.setLineDash([]);
        ctx.beginPath(); ctx.moveTo(x, 30); ctx.lineTo(x, height); ctx.stroke();
        if (arrow > x + 12) {
          ctx.beginPath(); ctx.moveTo(x + 5, 44); ctx.lineTo(arrow, 44); ctx.lineTo(arrow - 6, 38);
          ctx.moveTo(arrow, 44); ctx.lineTo(arrow - 6, 50); ctx.stroke();
        }
        ctx.restore(); if (!preview.row) return;
      }
      // A tracked placement shades only its chosen row. Insert still marks the
      // global opening of time above, not an overwrite of every existing lane.
      const top = preview.row ? preview.row.top + 1 : 30;
      const bottom = preview.row ? preview.row.bottom - 1 : height;
      ctx.save(); ctx.fillStyle = timeline.color("selection-fill", "rgba(188,169,223,.14)");
      ctx.fillRect(x, top, Math.max(2, end - x), Math.max(0, bottom - top));
      ctx.strokeStyle = timeline.color("selected", "#bca9df"); ctx.lineWidth = 2; ctx.setLineDash([6, 3]);
      ctx.strokeRect(x + 1, top + 1, Math.max(1, end - x - 2), Math.max(0, bottom - top - 3)); ctx.restore();
    },
    destroy() {
      destroyed = true; cancel(); observer?.disconnect(); listeners.forEach(remove => remove());
      if (hideTimer != null) win.clearTimeout(hideTimer);
      for (const [card, saved] of savedCards) {
        for (const [name, value] of Object.entries(saved)) value == null ? card.removeAttribute(name) : card.setAttribute(name, value);
        card.classList.remove("timeline-draggable");
      }
      savedCards.clear(); feedback.remove(); if (timeline.libraryDrop === controller) timeline.libraryDrop = null;
    },
  };
  timeline.libraryDrop = controller; refresh(); return controller;
}
