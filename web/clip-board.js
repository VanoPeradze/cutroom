/* CUTROOM Clips board. Read-only: ranks moments from saved analysis and hands a
   chosen range to the editor's own selection/export controls. It never edits,
   saves or renders by itself. Strength is relative to one recording. */

export const CLIP_LENGTHS = Object.freeze([15, 30, 45, 60]);

export function formatClock(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "--:--";
  const whole = Math.floor(value + 1e-6);
  const hours = Math.floor(whole / 3600), minutes = Math.floor(whole / 60) % 60, rest = whole % 60;
  const pad = number => String(number).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(rest)}` : `${minutes}:${pad(rest)}`;
}

export function strengthLabel(strength) {
  const value = Math.max(0, Math.min(100, Math.round(Number(strength) || 0)));
  if (value >= 95) return "Top moment";
  if (value >= 80) return `Top ${Math.max(1, 100 - value)}%`;
  if (value >= 55) return "Strong moment";
  return "Quieter moment";
}

const SCREENS = { cutscene: "Cutscene", menu: "Menu", loading: "Loading screen", webcam_only: "Camera only", map: "Map", other: "Other screen" };

export function reasonLabel(reason) {
  switch (reason?.kind) {
    case "energy": return reason.level === "high" ? "High energy" : "Active sound";
    case "action": return `On-screen action ${Math.round(Number(reason.value) || 0)}`;
    case "reactions": { const count = Math.round(Number(reason.count) || 0); return `${count} ${count === 1 ? "reaction" : "reactions"}`; }
    case "speech": return "Speech";
    case "screen": return SCREENS[reason.value] || "Other screen";
    default: return "";
  }
}

export function boardSummary(board) {
  const used = ["sound"];
  if (board?.signals?.transcript) used.push("spoken reactions");
  if (board?.signals?.vision) used.push("on-screen action");
  const list = used.length > 1 ? `${used.slice(0, -1).join(", ")} and ${used.at(-1)}` : used[0];
  return `Ranked by ${list} in this recording.`;
}

export function unavailableMessage(reason) {
  return {
    no_source: "Add a main recording to find clips.",
    no_audio: "This recording has no sound track, so there is nothing to measure yet.",
    audio_profile_missing: "The sound analysis for this recording is not ready. Wait for import to finish, then try again.",
    too_short: "This recording is shorter than the chosen clip length. Choose a shorter length.",
  }[reason] || "Clips are not available for this project yet.";
}

const ICONS = {
  play: '<path d="M8 5.5v13l10.5-6.5z"/>',
  pause: '<path d="M8 5h3v14H8zM13 5h3v14h-3z"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
};
function icon(doc, name, filled = false) {
  const span = doc.createElement("span");
  span.className = "clip-icon";
  span.setAttribute("aria-hidden", "true");
  span.innerHTML = `<svg viewBox="0 0 24 24" ${filled ? 'fill="currentColor" stroke="none"' : 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"'}>${ICONS[name]}</svg>`;
  return span;
}

export class ClipBoard {
  constructor(options) {
    this.options = options;
    this.doc = options.document || document;
    this.length = 30;
    this.cache = new Map();
    this.cards = new Map();
    this.request = 0;
    this.board = null;
    this.playing = null;
    this.stillQueue = [];
  }

  el(tag, className, text) {
    const node = this.doc.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  build() {
    if (this.dialog) return;
    const doc = this.doc;
    const dialog = this.el("dialog", "clip-board");
    dialog.setAttribute("aria-labelledby", "clipBoardTitle");
    const head = this.el("header", "clip-board-head");
    const titles = this.el("div", "clip-board-titles");
    const title = this.el("h2", null, "Clips"); title.id = "clipBoardTitle";
    this.summary = this.el("p", "clip-board-summary", "");
    titles.append(title, this.summary);
    const lengths = this.el("div", "clip-length");
    lengths.setAttribute("role", "group");
    lengths.setAttribute("aria-label", "Clip length");
    this.lengthButtons = CLIP_LENGTHS.map(seconds => {
      const button = this.el("button", null, `${seconds}s`);
      button.type = "button";
      button.dataset.length = String(seconds);
      button.setAttribute("aria-label", `${seconds} second clips`);
      button.addEventListener("click", () => this.setLength(seconds));
      lengths.append(button);
      return button;
    });
    const close = this.el("button", "clip-board-close");
    close.type = "button";
    close.setAttribute("aria-label", "Close clips");
    close.append(icon(doc, "close"));
    close.addEventListener("click", () => this.close());
    head.append(titles, lengths, close);

    const radar = this.el("section", "clip-radar");
    radar.setAttribute("aria-label", "Moment strength across the recording");
    const radarHead = this.el("div", "clip-radar-head");
    radarHead.append(this.el("span", null, "Moment radar"), this.radarLegend = this.el("small", null, ""));
    this.radarTrack = this.el("div", "clip-radar-track");
    this.radarBars = this.el("div", "clip-radar-bars");
    this.radarMarks = this.el("div", "clip-radar-marks");
    this.radarTrack.append(this.radarBars, this.radarMarks);
    const radarScale = this.el("div", "clip-radar-scale");
    this.radarStart = this.el("span", null, "0:00");
    this.radarEnd = this.el("span", null, "");
    radarScale.append(this.radarStart, this.radarEnd);
    radar.append(radarHead, this.radarTrack, radarScale);

    this.status = this.el("div", "clip-board-status");
    this.status.setAttribute("role", "status");
    this.grid = this.el("div", "clip-grid");
    const body = this.el("div", "clip-board-body");
    const foot = this.el("p", "clip-board-foot", "Strength compares moments inside this recording. It is a measured signal, not a prediction of views. Open a clip to trim, frame and caption it in the editor.");
    body.append(radar, this.status, this.grid, foot);
    dialog.append(head, body);
    dialog.addEventListener("close", () => this.teardown());
    dialog.addEventListener("cancel", () => this.stopPreview());
    doc.body.append(dialog);
    this.dialog = dialog;
    this.radar = radar;

    this.stillVideo = this.el("video");
    this.stillVideo.muted = true;
    this.stillVideo.preload = "auto";
    this.stillVideo.playsInline = true;
    this.previewVideo = this.el("video", "clip-preview-video");
    this.previewVideo.playsInline = true;
    this.previewVideo.preload = "auto";
    this.previewVideo.addEventListener("timeupdate", () => this.trackPreview());
    this.previewVideo.addEventListener("ended", () => this.stopPreview());
  }

  async open() {
    const project = this.options.getProject();
    if (!project?.sources?.A) { this.options.notify?.("Add a main recording before looking for clips."); return; }
    this.build();
    this.projectId = project.id;
    this.aspect = this.options.outputAspect?.() || 16 / 9;
    this.dialog.style.setProperty("--clip-aspect", String(this.aspect));
    this.dialog.classList.toggle("vertical", this.aspect < 1);
    const url = this.options.mediaUrl(project);
    if (this.stillVideo.dataset.src !== url) { this.stillVideo.src = url; this.stillVideo.dataset.src = url; }
    if (this.previewVideo.dataset.src !== url) { this.previewVideo.src = url; this.previewVideo.dataset.src = url; }
    this.handingOff = false;
    if (!this.dialog.open) this.dialog.showModal();
    await this.load();
  }

  close() {
    if (this.dialog?.open) this.dialog.close();
  }

  teardown() {
    this.stopPreview();
    this.stillQueue = [];
    this.request += 1;
    const handedOff = Boolean(this.handingOff);
    this.handingOff = false;
    this.options.onClose?.({ handedOff });
  }

  setLength(seconds) {
    if (seconds === this.length) return;
    this.length = seconds;
    this.load();
  }

  async load() {
    const project = this.options.getProject();
    if (!project || project.id !== this.projectId) { this.close(); return; }
    const ticket = ++this.request;
    this.stopPreview();
    this.lengthButtons.forEach(button => button.setAttribute("aria-pressed", String(Number(button.dataset.length) === this.length)));
    const key = `${project.id}:${project.revision}:${this.length}`;
    let board = this.cache.get(key);
    if (!board) {
      this.renderLoading();
      try {
        const payload = await this.options.api(`/api/projects/${encodeURIComponent(project.id)}/clip-board?length=${this.length}`);
        board = payload.board;
        this.cache.set(key, board);
      } catch (error) {
        if (ticket !== this.request) return;
        this.renderError(error?.message || "Clips could not be loaded.");
        return;
      }
    }
    if (ticket !== this.request) return;
    this.render(board);
  }

  renderLoading() {
    this.summary.textContent = "Measuring moments…";
    this.status.textContent = "";
    this.status.hidden = true;
    this.radar.hidden = false;
    this.radarBars.replaceChildren();
    this.radarMarks.replaceChildren();
    this.grid.replaceChildren(...Array.from({ length: 6 }, () => {
      const card = this.el("div", "clip-card skeleton");
      card.setAttribute("aria-hidden", "true");
      card.append(this.el("div", "clip-media"), this.el("div", "clip-skeleton-line"), this.el("div", "clip-skeleton-line short"));
      return card;
    }));
    this.grid.setAttribute("aria-busy", "true");
  }

  renderError(message) {
    this.grid.removeAttribute("aria-busy");
    this.grid.replaceChildren();
    this.radar.hidden = true;
    this.summary.textContent = "";
    this.status.hidden = false;
    this.status.replaceChildren(this.el("p", null, message));
    const retry = this.el("button", "button ghost compact", "Try again");
    retry.type = "button";
    retry.addEventListener("click", () => this.load());
    this.status.append(retry);
  }

  render(board) {
    this.board = board;
    this.cards.clear();
    this.grid.removeAttribute("aria-busy");
    this.grid.replaceChildren();
    if (!board?.available) {
      this.radar.hidden = true;
      this.summary.textContent = "";
      this.status.hidden = false;
      this.status.replaceChildren(this.el("p", null, unavailableMessage(board?.reason)));
      return;
    }
    const clips = Array.isArray(board.clips) ? board.clips : [];
    const source = this.options.getProject()?.sources?.A;
    this.summary.textContent = `${clips.length} ${clips.length === 1 ? "clip" : "clips"} from ${formatClock(board.source_duration)} of footage. ${boardSummary(board)}`;
    if (source?.name) this.summary.title = source.name;
    this.status.hidden = true;
    this.renderRadar(board, clips);
    clips.forEach(clip => this.grid.append(this.card(clip)));
    this.queueStills(clips);
  }

  renderRadar(board, clips) {
    this.radar.hidden = false;
    const duration = Number(board.source_duration) || 1;
    this.radarEnd.textContent = formatClock(duration);
    this.radarLegend.textContent = "Taller means stronger. Numbers mark each clip.";
    const bars = (board.heat || []).map(point => {
      const bar = this.el("i");
      const strength = Math.max(0, Math.min(100, Number(point.strength) || 0));
      bar.style.setProperty("--h", `${Math.max(6, strength)}%`);
      if (strength >= 80) bar.className = "hot";
      return bar;
    });
    this.radarBars.replaceChildren(...bars);
    this.radarMarks.replaceChildren(...clips.map(clip => {
      const mark = this.el("button", "clip-radar-mark", String(clip.rank));
      mark.type = "button";
      mark.style.left = `${(100 * Number(clip.start)) / duration}%`;
      mark.style.width = `${Math.max(0.6, (100 * (Number(clip.end) - Number(clip.start))) / duration)}%`;
      mark.setAttribute("aria-label", `Clip ${clip.rank}, ${formatClock(clip.start)} to ${formatClock(clip.end)}`);
      mark.addEventListener("click", () => {
        const card = this.cards.get(clip.id);
        card?.node.scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        card?.play.focus({ preventScroll: true });
      });
      return mark;
    }));
  }

  card(clip) {
    const doc = this.doc;
    const node = this.el("article", "clip-card");
    node.dataset.clipId = clip.id;
    const range = this.options.timelineRange(clip);
    const media = this.el("div", "clip-media");
    const canvas = this.el("canvas");
    canvas.width = this.aspect < 1 ? 270 : 384;
    canvas.height = this.aspect < 1 ? 480 : Math.round(384 / this.aspect);
    canvas.setAttribute("aria-hidden", "true");
    const rank = this.el("span", "clip-rank", `#${clip.rank}`);
    const length = this.el("span", "clip-length-badge", formatClock(clip.duration));
    const progress = this.el("span", "clip-progress");
    const play = this.el("button", "clip-play");
    play.type = "button";
    play.setAttribute("aria-label", `Preview clip ${clip.rank}`);
    play.append(icon(doc, "play", true));
    play.addEventListener("click", () => this.togglePreview(clip));
    media.append(canvas, rank, length, progress, play);

    const body = this.el("div", "clip-body");
    const meta = this.el("div", "clip-meta");
    const strength = Math.max(0, Math.min(100, Math.round(Number(clip.strength) || 0)));
    const ring = this.el("span", "clip-strength");
    ring.style.setProperty("--strength", String(strength));
    ring.append(this.el("b", null, String(strength)));
    ring.setAttribute("aria-label", `Strength ${strength} of 100 in this recording`);
    const label = this.el("div", "clip-label");
    label.append(this.el("strong", null, strengthLabel(strength)), this.el("small", null, `${formatClock(clip.start)} – ${formatClock(clip.end)}`));
    meta.append(ring, label);
    body.append(meta);

    const event = (clip.reasons || []).find(reason => reason.kind === "event" && reason.text);
    const quote = clip.hook || event?.text || "";
    if (quote) {
      const hook = this.el("p", clip.hook ? "clip-hook" : "clip-hook seen", clip.hook ? `“${clip.hook}”` : quote);
      hook.dir = "auto";
      if (clip.excerpt && clip.excerpt !== clip.hook) hook.title = clip.excerpt;
      body.append(hook);
    }
    const reasons = this.el("ul", "clip-reasons");
    reasons.setAttribute("aria-label", "Why this clip");
    for (const reason of clip.reasons || []) {
      const text = reasonLabel(reason);
      if (text) reasons.append(this.el("li", reason.kind === "energy" && reason.level === "high" ? "strong" : null, text));
    }
    reasons.append(this.el("li", "peak", `Peak ${formatClock(clip.peak)}`));
    body.append(reasons);

    const actions = this.el("div", "clip-actions");
    let openButton = this.el("button", "button primary compact", "Open in editor");
    openButton.type = "button";
    const exportButton = this.el("button", "button ghost compact", "Export clip");
    exportButton.type = "button";
    openButton.addEventListener("click", () => this.handOff(clip, false));
    exportButton.addEventListener("click", () => this.handOff(clip, true));
    actions.append(openButton, exportButton);
    if (this.options.canExport && !this.options.canExport()) exportButton.hidden = true;
    body.append(actions);
    if (!range) {
      const canPlace = Boolean(this.options.canPlace?.());
      exportButton.hidden = true;
      if (canPlace) {
        openButton.textContent = "Place in timeline";
        openButton.replaceWith(openButton = openButton.cloneNode(true));
        openButton.addEventListener("click", () => this.place(clip));
        actions.prepend(openButton);
      } else {
        openButton.disabled = true;
      }
      body.append(this.el("p", "clip-note", canPlace
        ? "This moment is not in your current edit. Place it to review and add it to the timeline. You can Undo."
        : "This moment is not in your current edit. Preview it here, or restore that part of the timeline to open it."));
    }
    node.append(media, body);
    this.cards.set(clip.id, { node, canvas, play, progress, media, clip });
    return node;
  }

  queueStills(clips) {
    this.stillQueue = clips.map(clip => clip.id);
    this.stillTicket = (this.stillTicket || 0) + 1;
    this.drawNextStill(this.stillTicket);
  }

  drawNextStill(ticket) {
    if (ticket !== this.stillTicket || !this.dialog?.open) return;
    const id = this.stillQueue.shift();
    if (!id) return;
    const card = this.cards.get(id);
    if (!card) { this.drawNextStill(ticket); return; }
    const video = this.stillVideo;
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("error", done);
      clearTimeout(timer);
      this.drawNextStill(ticket);
    };
    const onSeeked = () => {
      if (ticket === this.stillTicket) this.paint(card.canvas, video);
      card.node.classList.add("has-still");
      done();
    };
    const timer = setTimeout(done, 4000);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("error", done);
    const seek = () => { try { video.currentTime = Math.max(0, Number(card.clip.peak) || Number(card.clip.start) || 0); } catch { done(); } };
    if (video.readyState >= 1) seek(); else video.addEventListener("loadedmetadata", seek, { once: true });
  }

  paint(canvas, video) {
    const context = canvas.getContext("2d");
    const width = video.videoWidth, height = video.videoHeight;
    if (!context || !width || !height) return;
    // Cover-fit, centred. This is a preview of the moment, not the final framing.
    const scale = Math.max(canvas.width / width, canvas.height / height);
    const drawWidth = width * scale, drawHeight = height * scale;
    try { context.drawImage(video, (canvas.width - drawWidth) / 2, (canvas.height - drawHeight) / 2, drawWidth, drawHeight); } catch { /* unreadable frame */ }
  }

  togglePreview(clip) {
    if (this.playing?.clip.id === clip.id) {
      if (this.previewVideo.paused) this.previewVideo.play().catch(() => {});
      else this.previewVideo.pause();
      this.syncPlayButton();
      return;
    }
    this.stopPreview();
    const card = this.cards.get(clip.id);
    if (!card) return;
    this.options.pauseEditor?.();
    this.playing = card;
    card.node.classList.add("playing");
    card.media.insertBefore(this.previewVideo, card.media.firstChild.nextSibling);
    const start = () => {
      try { this.previewVideo.currentTime = Number(clip.start) || 0; } catch { /* metadata pending */ }
      this.previewVideo.play().catch(() => this.stopPreview());
      this.syncPlayButton();
    };
    if (this.previewVideo.readyState >= 1) start(); else this.previewVideo.addEventListener("loadedmetadata", start, { once: true });
    this.previewVideo.onplay = this.previewVideo.onpause = () => this.syncPlayButton();
  }

  trackPreview() {
    const card = this.playing;
    if (!card) return;
    const { start, end } = card.clip;
    const time = this.previewVideo.currentTime;
    card.progress.style.setProperty("--progress", `${Math.max(0, Math.min(100, (100 * (time - start)) / Math.max(0.1, end - start)))}%`);
    if (time >= end - 0.04) this.stopPreview();
  }

  syncPlayButton() {
    const card = this.playing;
    if (!card) return;
    const paused = this.previewVideo.paused;
    card.play.replaceChildren(icon(this.doc, paused ? "play" : "pause", true));
    card.play.setAttribute("aria-label", `${paused ? "Resume" : "Pause"} clip ${card.clip.rank}`);
    card.node.classList.toggle("paused", paused);
  }

  stopPreview() {
    const card = this.playing;
    if (!this.previewVideo) return;
    this.previewVideo.pause();
    this.previewVideo.onplay = this.previewVideo.onpause = null;
    this.previewVideo.remove();
    if (!card) return;
    this.playing = null;
    card.node.classList.remove("playing", "paused");
    card.progress.style.removeProperty("--progress");
    card.play.replaceChildren(icon(this.doc, "play", true));
    card.play.setAttribute("aria-label", `Preview clip ${card.clip.rank}`);
  }

  async place(clip) {
    this.stopPreview();
    this.handingOff = true;
    this.close();
    await this.options.placeClip(clip);
  }

  async handOff(clip, exportAfter) {
    this.stopPreview();
    const range = this.options.timelineRange(clip);
    if (!range) return;
    this.handingOff = true;
    this.close();
    await this.options.openClip(clip, range, { exportAfter });
  }
}
