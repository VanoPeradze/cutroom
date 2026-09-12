// Display-only controls. No project edits, media restarts, or playback changes.
const TIMELINE_HEIGHT_KEY = "cutroom-timeline-height-v3";

export function initWorkspace({ document: doc = document, window: win = window, onResize = () => {}, openShortcuts = () => {} } = {}) {
  const panel = doc.getElementById("advancedPanel");
  const actions = panel?.querySelector(".studio-header-actions");
  const preview = doc.getElementById("previewColumn");
  if (!panel || !actions || !preview) return null;
  if (panel.workspaceController) return panel.workspaceController;
  let disposed = false;
  let resizeFrame = null;
  let fullscreenPending = false;
  let fullscreenRequest = 0;
  let startedInStudio = false;
  let fallbackOrigin = null;
  let preferredHeight = null;
  let resizeGesture = null;
  const listeners = [];
  const listen = (target, event, callback, options) => {
    target.addEventListener(event, callback, options);
    listeners.push(() => target.removeEventListener(event, callback, options));
  };
  const create = (tag, className = "", text = "") => {
    const element = doc.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  const button = (id, text) => {
    const element = create("button", "button ghost compact", text);
    element.id = id;
    element.type = "button";
    return element;
  };
  const guideButton = button("workspaceGuide", "How to edit");
  guideButton.setAttribute("aria-haspopup", "dialog");
  guideButton.setAttribute("aria-controls", "workspaceGuideDialog");
  actions.insertBefore(guideButton, actions.firstChild);
  const fullscreenButton = button("previewFullscreen", "Full screen");
  fullscreenButton.classList.add("preview-fullscreen-toggle");
  fullscreenButton.title = "Show only the video, including both sources, captions and playback controls. Escape exits.";
  preview.appendChild(fullscreenButton);
  const status = create("span", "workspace-display-status");
  status.id = "workspaceDisplayStatus";
  status.setAttribute("role", "status");
  status.setAttribute("aria-live", "polite");
  preview.appendChild(status);
  const divider = create("div", "workspace-divider", "Resize video / timeline");
  divider.id = "workspaceDivider";
  divider.tabIndex = 0;
  divider.setAttribute("role", "separator");
  divider.setAttribute("aria-orientation", "horizontal");
  divider.setAttribute("aria-label", "Resize video and timeline");
  divider.setAttribute("data-editor-shortcuts", "off");
  divider.setAttribute("aria-controls", "studioPreviewDock studioTimelineDock");
  divider.title = "Drag up for more timeline or down for more video. Arrow keys resize; double-click resets.";
  panel.appendChild(divider);
  // A modal fallback escapes container-query containing blocks without
  // stretching only one source video or losing captions and playback controls.
  const videoDialog = create("dialog", "video-fullscreen-dialog");
  videoDialog.id = "videoFullscreenDialog";
  videoDialog.setAttribute("aria-label", "Full-screen video preview");
  doc.body.appendChild(videoDialog);
  const heightBounds = () => {
    const height = panel.getBoundingClientRect().height || Math.max(400, (win.innerHeight || 800) - 64);
    const headerHeight = panel.querySelector(".studio-header")?.getBoundingClientRect().height || 44;
    // Includes the ruler, both video lanes, layout/audio, toolbar and the
    // horizontal scrollbar that appears when zoomed in.
    const minimum = 326;
    const maximum = Math.max(minimum, Math.floor(height - headerHeight - 14 - 220));
    return { minimum, maximum, defaultHeight: Math.min(420, Math.max(minimum, Math.round(height * .46))) };
  };
  const applyTimelineHeight = () => {
    const bounds = heightBounds();
    const height = Math.round(Math.min(bounds.maximum, Math.max(bounds.minimum, preferredHeight ?? bounds.defaultHeight)));
    panel.style.setProperty("--workspace-timeline-height", `${height}px`);
    divider.setAttribute("aria-valuemin", String(bounds.minimum));
    divider.setAttribute("aria-valuemax", String(bounds.maximum));
    divider.setAttribute("aria-valuenow", String(height));
    divider.setAttribute("aria-valuetext", `Timeline ${height} pixels tall`);
    return height;
  };
  const scheduleResize = () => {
    if (disposed || resizeFrame !== null) return;
    resizeFrame = win.requestAnimationFrame(() => {
      resizeFrame = null;
      if (!disposed) { applyTimelineHeight(); onResize(); }
    });
  };
  const saveHeight = () => {
    try {
      if (preferredHeight === null) win.localStorage.removeItem(TIMELINE_HEIGHT_KEY);
      else win.localStorage.setItem(TIMELINE_HEIGHT_KEY, String(preferredHeight));
    } catch { /* Private browsers may deny display preference storage. */ }
  };
  const setTimelineHeight = (height, persist = true) => {
    preferredHeight = Number.isFinite(height) ? height : null;
    const applied = applyTimelineHeight();
    if (preferredHeight !== null) preferredHeight = applied;
    if (persist) saveHeight();
    scheduleResize();
    return applied;
  };
  const endResize = (event, cancelled = false) => {
    if (!resizeGesture || (event?.pointerId !== undefined && event.pointerId !== resizeGesture.pointerId)) return;
    const gesture = resizeGesture;
    resizeGesture = null;
    if (cancelled) preferredHeight = gesture.originalPreference;
    if (divider.hasPointerCapture?.(gesture.pointerId)) divider.releasePointerCapture(gesture.pointerId);
    panel.classList.remove("workspace-resizing");
    applyTimelineHeight();
    if (!cancelled) saveHeight();
    scheduleResize();
  };
  listen(divider, "pointerdown", (event) => {
    if (event.button !== 0 || resizeGesture) return;
    event.preventDefault();
    resizeGesture = { pointerId: event.pointerId, y: event.clientY, height: applyTimelineHeight(), originalPreference: preferredHeight };
    divider.setPointerCapture?.(event.pointerId);
    panel.classList.add("workspace-resizing");
  });
  listen(divider, "pointermove", (event) => {
    if (!resizeGesture || event.pointerId !== resizeGesture.pointerId) return;
    event.preventDefault();
    setTimelineHeight(resizeGesture.height + resizeGesture.y - event.clientY, false);
  });
  listen(divider, "pointerup", (event) => endResize(event));
  listen(divider, "pointercancel", (event) => endResize(event, true));
  listen(divider, "lostpointercapture", (event) => endResize(event, true));
  listen(divider, "dblclick", () => setTimelineHeight(null));
  listen(divider, "keydown", (event) => {
    const bounds = heightBounds();
    const step = event.shiftKey ? 64 : 24;
    const next = event.key === "ArrowUp" ? applyTimelineHeight() + step : event.key === "ArrowDown" ? applyTimelineHeight() - step
      : event.key === "Home" ? bounds.minimum : event.key === "End" ? bounds.maximum : null;
    if (next === null) return;
    event.preventDefault();
    event.stopPropagation();
    setTimelineHeight(next);
  });
  const isVideoFullscreen = () => doc.fullscreenElement === preview || Boolean(fallbackOrigin);
  const renderFullscreen = () => {
    const active = isVideoFullscreen();
    preview.classList.toggle("video-expanded", active);
    fullscreenButton.textContent = active ? "Exit full screen" : "Full screen";
    fullscreenButton.setAttribute("aria-label", active ? "Exit video full screen" : "Video full screen");
    fullscreenButton.setAttribute("aria-pressed", String(active));
    fullscreenButton.disabled = fullscreenPending;
    scheduleResize();
  };
  const restoreFallback = () => {
    const origin = fallbackOrigin;
    fallbackOrigin = null;
    if (origin && preview.parentElement === videoDialog) {
      if (origin.next?.parentElement === origin.parent) origin.parent.insertBefore(preview, origin.next);
      else origin.parent.appendChild(preview);
    }
    if (videoDialog.open) videoDialog.close();
  };
  const leaveFullscreen = async () => {
    fullscreenRequest += 1;
    restoreFallback();
    if (doc.fullscreenElement === preview && doc.exitFullscreen) {
      try { await doc.exitFullscreen(); }
      catch { status.textContent = "Use Escape or your browser's full-screen control to exit the video."; }
    }
    fullscreenPending = false;
    if (!disposed) renderFullscreen();
    else preview.classList.remove("video-expanded");
  };
  const showFallback = () => {
    fallbackOrigin = { parent: preview.parentElement, next: preview.nextSibling };
    videoDialog.appendChild(preview);
    try {
      videoDialog.showModal();
      status.textContent = "Video expanded inside this window. Escape returns to editing.";
    } catch {
      restoreFallback();
      status.textContent = "This browser could not open a full-screen video preview.";
    }
  };
  const toggleFullscreen = async () => {
    if (disposed || fullscreenPending) return;
    if (isVideoFullscreen()) { await leaveFullscreen(); return; }
    if (doc.fullscreenElement) {
      status.textContent = "Exit the other full-screen view before expanding this video.";
      return;
    }
    const request = ++fullscreenRequest;
    startedInStudio = !panel.hidden;
    fullscreenPending = true;
    renderFullscreen();
    try {
      if (!preview.requestFullscreen) throw Error("Fullscreen unavailable");
      await preview.requestFullscreen();
      if (disposed || (startedInStudio && panel.hidden) || request !== fullscreenRequest) {
        await leaveFullscreen();
        return;
      }
      status.textContent = "Full-screen video. Escape returns to editing.";
    } catch {
      if (!disposed && !(startedInStudio && panel.hidden) && request === fullscreenRequest) showFallback();
    } finally {
      fullscreenPending = false;
      if (!disposed) {
        renderFullscreen();
        if (isVideoFullscreen()) (doc.getElementById("playButton") || fullscreenButton).focus();
      }
    }
  };
  listen(fullscreenButton, "click", () => { void toggleFullscreen(); });
  listen(doc, "fullscreenchange", () => { if (!disposed) renderFullscreen(); });
  listen(videoDialog, "cancel", (event) => { event.preventDefault(); void leaveFullscreen(); });
  listen(videoDialog, "close", () => { if (fallbackOrigin) { restoreFallback(); renderFullscreen(); } });
  listen(win, "keydown", (event) => {
    if (event.key !== "Escape" || !isVideoFullscreen()) return;
    // Only our video consumes Escape; ordinary editing keys remain untouched.
    event.preventDefault();
    event.stopImmediatePropagation();
    void leaveFullscreen();
  }, true);
  const guide = create("dialog", "sheet-dialog workspace-guide-dialog");
  guide.id = "workspaceGuideDialog";
  guide.setAttribute("aria-labelledby", "workspaceGuideTitle");
  const shell = create("div", "dialog-shell");
  const header = create("header");
  const heading = create("div");
  heading.appendChild(create("p", "eyebrow", "CUTROOM EDITOR GUIDE"));
  const title = create("h2", "", "Your first manual edit");
  title.id = "workspaceGuideTitle";
  heading.appendChild(title);
  const closeGuide = button("workspaceGuideClose", "Close");
  closeGuide.setAttribute("aria-label", "Close editor guide");
  header.append(heading, closeGuide);
  shell.appendChild(header);
  shell.appendChild(create("p", "workspace-guide-intro", "The AI draft is a starting point. Your original footage stays untouched, and manual changes can be undone."));
  const steps = create("ol", "workspace-guide-steps");
  const help = [
    ["Find your moment", "Click the ruler to seek. Space plays or pauses. Edited video shows your cut; Full source lets you inspect the original without changing the edit."],
    ["Remove the part you do not want", "Choose Range, drag over the section, then Remove from video. Together closes the gap on both tracks and keeps them in sync. Undo brings it back."],
    ["Arrange your story", "Cut: click to split. Drag the middle of a clip to reorder: its old position closes and destination footage shifts, without overwriting it. In Select / Move, select a clip and pull its white edges to reveal original footage into a gap. Edges stop at neighboring clips or the media limit. Together shortening closes the gap; A/B-only shortening affects just that source. Close gaps removes existing empty time. Undo restores changes."],
    ["Bring footage back", "Original footage opens the complete recording with kept and removed sections: preview, drag a Range, then Restore to edit or Remove from edit. You can also extend a cut's white edges directly on the timeline. Zoom in if a clip is too small to grab its edges."],
    ["Change the look", "Select a section, open Layout and choose a composition: it saves immediately. Entire edit applies your next choice throughout. In Captions, select a line, edit its text and Save."],
    ["Watch and export", "Drag the video/timeline divider to resize. Full screen shows just the composed video; Escape returns. Output has aspect ratio, resolution and up to 60 FPS at the top. Export creates the file."],
  ];
  for (const [stepTitle, body] of help) {
    const step = create("li");
    step.append(create("h3", "", stepTitle), create("p", "", body));
    steps.appendChild(step);
  }
  shell.appendChild(steps);
  const footer = create("footer", "workspace-guide-footer");
  const advancedHelp = create("details", "workspace-guide-advanced");
  advancedHelp.appendChild(create("summary", "", "Working on sources independently"));
  advancedHelp.appendChild(create("p", "", "Choose A only or B only in the Edit menu to change one source without shifting the other. Removal then leaves a gap. Together is the default for whole-video edits. In Original footage, Restore brings back missing source intervals with the original A/B synchronization; Remove affects all uses of the selected source interval. Reordered clips keep their relative order. Insert a copy by time is available for deliberate duplication. A camera embedded in one file uses crop/layout controls, not a recovered second recording. The editor supports two source tracks, not unlimited layers."));
  shell.appendChild(advancedHelp);
  footer.appendChild(create("p", "", "Original files are never overwritten. Manual changes save automatically and support Undo. Shortcut profiles cover CUTROOM's supported commands."));
  const shortcutsButton = button("workspaceGuideShortcuts", "Keyboard shortcuts");
  footer.appendChild(shortcutsButton);
  shell.appendChild(footer);
  guide.appendChild(shell);
  doc.body.appendChild(guide);
  const openGuide = () => {
    if (disposed || guide.open || isVideoFullscreen()) return;
    guide.showModal();
    closeGuide.focus();
  };
  listen(guideButton, "click", openGuide);
  listen(closeGuide, "click", () => guide.close());
  listen(shortcutsButton, "click", () => { guide.close(); openShortcuts(); });
  listen(guide, "close", () => { if (!disposed && !panel.hidden) guideButton.focus(); });
  listen(win, "resize", scheduleResize);
  const observer = win.MutationObserver ? new win.MutationObserver(() => {
    if (panel.hidden) {
      if (guide.open) guide.close();
      endResize(null, true);
      if (startedInStudio && (isVideoFullscreen() || fullscreenPending)) void leaveFullscreen();
    }
    scheduleResize();
  }) : null;
  observer?.observe(panel, { attributes: true, attributeFilter: ["hidden"] });
  try {
    const saved = win.localStorage.getItem(TIMELINE_HEIGHT_KEY);
    if (saved !== null && Number.isFinite(Number(saved)) && Number(saved) >= 326) preferredHeight = Number(saved);
  } catch { /* Default proportions work without storage. */ }
  applyTimelineHeight();
  renderFullscreen();
  const controller = {
    toggleFullscreen, openGuide, setTimelineHeight,
    destroy() {
      disposed = true;
      endResize(null, true);
      void leaveFullscreen();
      listeners.forEach((remove) => remove());
      observer?.disconnect();
      if (resizeFrame !== null) win.cancelAnimationFrame(resizeFrame);
      guideButton.remove();
      fullscreenButton.remove();
      status.remove();
      divider.remove();
      guide.remove();
      videoDialog.remove();
      preview.classList.remove("video-expanded");
      panel.style.removeProperty("--workspace-timeline-height");
      delete panel.workspaceController;
    },
  };
  panel.workspaceController = controller;
  return controller;
}
