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

const SOUND_EVENTS = { laughter: "Laughter", applause: "Applause", music: "Music" };

export function reasonLabel(reason) {
  switch (reason?.kind) {
    case "energy": return reason.level === "high" ? "High energy" : "Active sound";
    case "action": return `On-screen action ${Math.round(Number(reason.value) || 0)}`;
    case "reactions": { const count = Math.round(Number(reason.count) || 0); return `${count} ${count === 1 ? "reaction" : "reactions"}`; }
    case "speech": return "Speech";
    case "screen": return SCREENS[reason.value] || "Other screen";
    case "sound_event": return SOUND_EVENTS[reason.type] || "";
    default: return "";
  }
}

export function boardSummary(board) {
  const used = ["sound"];
  if (board?.signals?.transcript) used.push("spoken reactions");
  if (board?.signals?.vision) used.push("on-screen action");
  if (board?.signals?.sound_events) used.push("laughter and applause");
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

// Draw a normalized source region into a canvas rectangle, cover-fit around a focus point.
export function coverCrop(region, sourceWidth, sourceHeight, target, focus = { x: .5, y: .5 }) {
  const sx = region.x * sourceWidth, sy = region.y * sourceHeight;
  const sw = region.w * sourceWidth, sh = region.h * sourceHeight;
  const ratio = target.w / target.h;
  let cw = sw, ch = sw / ratio;
  if (ch > sh) { ch = sh; cw = sh * ratio; }
  const fx = Math.max(0, Math.min(1, Number(focus?.x ?? .5))), fy = Math.max(0, Math.min(1, Number(focus?.y ?? .5)));
  const cx = Math.max(sx, Math.min(sx + sw - cw, sx + fx * sw - cw / 2));
  const cy = Math.max(sy, Math.min(sy + sh - ch, sy + fy * sh - ch / 2));
  return { sx: cx, sy: cy, sw: cw, sh: ch };
}

function drawCover(context, video, region, target, focus) {
  const crop = coverCrop(region, video.videoWidth, video.videoHeight, target, focus);
  context.drawImage(video, crop.sx, crop.sy, crop.sw, crop.sh, target.x, target.y, target.w, target.h);
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
    this.thumbs = [];
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
    close.addEventListener("click", () => { if (!this.batchRunning) this.close(); });
    this.batchButton = this.el("button", "button primary compact clip-batch-button", "Export selected");
    this.batchButton.type = "button";
    this.batchButton.hidden = true;
    this.batchButton.addEventListener("click", () => this.runBatch());
    head.append(titles, this.batchButton, lengths, close);

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
    this.batchPanel = this.el("section", "clip-batch");
    this.batchPanel.setAttribute("aria-live", "polite");
    this.batchPanel.hidden = true;
    this.thumbPanel = this.el("section", "clip-thumbs");
    this.thumbPanel.hidden = true;
    body.append(radar, this.batchPanel, this.status, this.grid, this.thumbPanel, foot);
    dialog.append(head, body);
    dialog.addEventListener("close", () => this.teardown());
    dialog.addEventListener("cancel", (event) => {
      // A running batch keeps the board open; Stop ends it explicitly.
      if (this.batchRunning) { event.preventDefault(); return; }
      this.stopPreview();
    });
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
    this.layout = this.aspect < 1 ? this.options.stillLayout?.() || null : null;
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

  // Full widescreen frames at the three strongest peaks, saved as PNG for a YouTube thumbnail.
  renderThumbs(clips) {
    this.thumbs = [];
    if (!this.thumbPanel) return;
    this.thumbPanel.hidden = !clips.length;
    const row = this.el("div", "clip-thumbs-row");
    for (const clip of clips) {
      const figure = this.el("figure", "clip-thumb");
      const canvas = this.el("canvas");
      canvas.width = 1280; canvas.height = 720;
      canvas.setAttribute("aria-label", `Frame at ${formatClock(clip.peak)}`);
      const caption = this.el("figcaption");
      const save = this.el("button", "button ghost compact", "Save PNG");
      save.type = "button";
      save.addEventListener("click", () => {
        canvas.toBlob(blob => {
          if (!blob) { this.options.notify?.("This frame could not be saved."); return; }
          const link = this.el("a");
          link.href = URL.createObjectURL(blob);
          link.download = `thumbnail-${formatClock(clip.peak).replace(/:/g, "-")}.png`;
          link.click();
          setTimeout(() => URL.revokeObjectURL(link.href), 4000);
        }, "image/png");
      });
      caption.append(this.el("span", null, `Clip ${clip.rank} · ${formatClock(clip.peak)}`), save);
      figure.append(canvas, caption);
      row.append(figure);
      this.thumbs.push({ canvas, node: figure, clip: { peak: clip.peak, start: clip.start }, full: true });
    }
    const head = this.el("div", "clip-radar-head");
    head.append(this.el("span", null, "Thumbnail ideas"), this.el("small", null, "Full frames at the strongest peaks. Add your title in an image editor."));
    this.thumbPanel.replaceChildren(head, row);
  }

  render(board) {
    this.board = board;
    this.cards.clear();
    this.selected = new Set();
    if (this.thumbPanel) this.thumbPanel.hidden = true;
    this.batchSupported = Boolean(this.options.canBatch?.());
    this.syncBatchButton();
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
    this.renderThumbs(clips.slice(0, 3));
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
    if (this.batchSupported && range) {
      const pick = this.el("label", "clip-pick");
      const box = this.el("input");
      box.type = "checkbox";
      box.setAttribute("aria-label", `Select clip ${clip.rank} for export`);
      box.addEventListener("change", () => {
        if (box.checked) this.selected.add(clip.id); else this.selected.delete(clip.id);
        node.classList.toggle("selected", box.checked);
        this.syncBatchButton();
      });
      pick.append(box, this.el("span", null, "Select"));
      meta.append(pick);
    }
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
    if (this.options.postingKit) body.append(this.kitSection(clip));
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

  // Titles, description and hashtags for posting. The basic kit is built from
  // what the recording says; "Write with AI" asks the configured Story AI.
  kitSection(clip) {
    const details = this.el("details", "clip-kit");
    const summary = this.el("summary", null, "Titles, description & hashtags");
    const panel = this.el("div", "clip-kit-panel");
    panel.setAttribute("aria-live", "polite");
    details.append(summary, panel);
    let loaded = false;
    details.addEventListener("toggle", () => {
      if (details.open && !loaded) { loaded = true; this.loadKit(clip, panel, false); }
    });
    return details;
  }

  async loadKit(clip, panel, useAi) {
    panel.replaceChildren(this.el("p", "clip-kit-status", useAi ? "Writing with AI…" : "Reading this moment…"));
    try {
      const kit = await this.options.postingKit(clip, useAi);
      this.renderKit(clip, panel, kit);
    } catch (error) {
      const message = error?.message || "The kit could not be built.";
      if (useAi && panel.dataset.kit) {
        this.renderKit(clip, panel, JSON.parse(panel.dataset.kit));
        panel.prepend(this.el("p", "clip-kit-status warn", message));
      } else {
        panel.replaceChildren(this.el("p", "clip-kit-status warn", message));
      }
    }
  }

  copyButton(label, text, name) {
    const button = this.el("button", "clip-kit-copy", label);
    button.type = "button";
    button.setAttribute("aria-label", `Copy ${name}`);
    button.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        button.textContent = "Copied";
        setTimeout(() => { button.textContent = label; }, 1400);
      } catch {
        this.options.notify?.("Copy was blocked by the browser. Select the text and copy it.");
      }
    });
    return button;
  }

  renderKit(clip, panel, kit) {
    if (!kit.ai) panel.dataset.kit = JSON.stringify(kit);
    const nodes = [];
    const dir = kit.language === "he" ? "rtl" : "auto";
    if (kit.hook) {
      const hook = this.el("div", "clip-kit-row hook");
      const text = this.el("p", null, kit.hook);
      text.dir = dir;
      hook.append(this.el("small", null, "On-screen hook"), text, this.copyButton("Copy", kit.hook, "hook"));
      nodes.push(hook);
    }
    if (kit.titles?.length) {
      const list = this.el("ol", "clip-kit-titles");
      list.setAttribute("aria-label", "Suggested titles");
      for (const title of kit.titles) {
        const item = this.el("li", "clip-kit-row");
        const text = this.el("p", null, title);
        text.dir = dir;
        item.append(text, this.copyButton("Copy", title, "title"));
        list.append(item);
      }
      nodes.push(this.el("small", "clip-kit-label", "Titles"), list);
    }
    if (kit.description) {
      const row = this.el("div", "clip-kit-row");
      const text = this.el("p", "clip-kit-description", kit.description);
      text.dir = dir;
      row.append(text, this.copyButton("Copy", kit.description, "description"));
      nodes.push(this.el("small", "clip-kit-label", "Description"), row);
    }
    if (kit.hashtags?.length) {
      const row = this.el("div", "clip-kit-row");
      const tags = kit.hashtags.join(" ");
      const text = this.el("p", "clip-kit-tags", tags);
      text.dir = dir;
      row.append(text, this.copyButton("Copy", tags, "hashtags"));
      nodes.push(this.el("small", "clip-kit-label", "Hashtags"), row);
    }
    const foot = this.el("div", "clip-kit-foot");
    if (kit.titles?.length || kit.description) {
      const all = [kit.hook, kit.titles?.[0], kit.description, kit.hashtags?.join(" ")].filter(Boolean).join("\n\n");
      foot.append(this.copyButton("Copy all", all, "everything"));
    }
    if (kit.source !== "none") {
      const ai = this.el("button", "button ghost compact clip-kit-ai", kit.ai ? "Write again" : "Write with AI");
      ai.type = "button";
      ai.addEventListener("click", () => this.loadKit(clip, panel, true));
      foot.append(ai);
    }
    nodes.push(foot);
    if (kit.note) nodes.push(this.el("p", "clip-kit-note", kit.note));
    panel.replaceChildren(...nodes);
  }

  queueStills(clips) {
    this.stillQueue = [...clips.map(clip => clip.id), ...this.thumbs];
    this.stillTicket = (this.stillTicket || 0) + 1;
    this.drawNextStill(this.stillTicket);
  }

  drawNextStill(ticket) {
    if (ticket !== this.stillTicket || !this.dialog?.open) return;
    const id = this.stillQueue.shift();
    if (!id) return;
    const card = typeof id === "string" ? this.cards.get(id) : id;
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
      if (ticket === this.stillTicket) {
        if (card.full) {
          try { drawCover(card.canvas.getContext("2d"), video, { x: 0, y: 0, w: 1, h: 1 }, { x: 0, y: 0, w: card.canvas.width, h: card.canvas.height }); } catch { /* unreadable frame */ }
        } else this.paint(card.canvas, video);
      }
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
    const layout = this.layout;
    try {
      if (layout) {
        // Same stack as export: creator camera on top, gameplay below.
        const top = Math.round(canvas.height * layout.split);
        drawCover(context, video, layout.camera, { x: 0, y: 0, w: canvas.width, h: top }, { x: .5, y: .5 });
        drawCover(context, video, layout.content, { x: 0, y: top, w: canvas.width, h: canvas.height - top }, layout.focus);
      } else {
        // Cover-fit, centred. A preview of the moment, not the final framing.
        drawCover(context, video, { x: 0, y: 0, w: 1, h: 1 }, { x: 0, y: 0, w: canvas.width, h: canvas.height }, { x: .5, y: .5 });
      }
    } catch { /* unreadable frame */ }
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
    // With a camera stack, play through the card canvas so the preview keeps that framing.
    this.previewVideo.classList.toggle("composited", Boolean(this.layout));
    if (this.layout) {
      const draw = () => {
        if (this.playing !== card) return;
        if (this.previewVideo.readyState >= 2) this.paint(card.canvas, this.previewVideo);
        this.frame = requestAnimationFrame(draw);
      };
      this.frame = requestAnimationFrame(draw);
    }
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
    if (this.frame) { cancelAnimationFrame(this.frame); this.frame = null; }
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

  syncBatchButton() {
    if (!this.batchButton) return;
    const count = this.selected?.size || 0;
    this.batchButton.hidden = !this.batchSupported || !count;
    this.batchButton.textContent = `Export ${count} ${count === 1 ? "clip" : "clips"}`;
    this.batchButton.disabled = Boolean(this.batchRunning);
  }

  setBusy(busy) {
    this.batchRunning = busy;
    this.dialog.classList.toggle("batch-running", busy);
    this.lengthButtons.forEach(button => { button.disabled = busy; });
    this.grid.querySelectorAll(".clip-actions button, .clip-pick input").forEach(control => { control.disabled = busy; });
    this.syncBatchButton();
  }

  async runBatch() {
    const clips = (this.board?.clips || []).filter(clip => this.selected.has(clip.id));
    if (!clips.length || this.batchRunning) return;
    this.stopPreview();
    this.batchStopped = false;
    this.setBusy(true);
    const line = this.el("p", "clip-batch-line", `Preparing ${clips.length} ${clips.length === 1 ? "clip" : "clips"}…`);
    const bar = this.el("span", "clip-batch-bar");
    const stop = this.el("button", "button ghost compact", "Stop");
    stop.type = "button";
    stop.addEventListener("click", () => { this.batchStopped = true; stop.disabled = true; line.textContent = "Stopping after the current step…"; });
    const row = this.el("div", "clip-batch-row");
    row.append(line, stop);
    this.batchPanel.replaceChildren(row, bar);
    this.batchPanel.hidden = false;
    let results = [];
    try {
      results = await this.options.exportBatch(clips, {
        isStopped: () => this.batchStopped,
        onProgress: ({ index, total, clip, progress }) => {
          const overall = (index + Math.max(0, Math.min(1, progress))) / total;
          bar.style.setProperty("--progress", `${Math.round(overall * 100)}%`);
          if (!this.batchStopped) line.textContent = `Exporting clip ${clip.rank} (${index + 1} of ${total}) · ${Math.round(progress * 100)}%`;
        },
      });
    } catch (error) {
      results = [{ error: error?.message || "Export could not start." }];
    }
    this.setBusy(false);
    this.renderBatchResults(results, clips.length);
  }

  renderBatchResults(results, requested) {
    const done = results.filter(row => row.url);
    const head = this.el("div", "clip-batch-row");
    head.append(this.el("p", "clip-batch-line", done.length === requested
      ? `${done.length} ${done.length === 1 ? "clip is" : "clips are"} ready.`
      : `${done.length} of ${requested} clips exported.`));
    const dismiss = this.el("button", "button ghost compact", "Done");
    dismiss.type = "button";
    dismiss.addEventListener("click", () => { this.batchPanel.hidden = true; });
    head.append(dismiss);
    const list = this.el("ul", "clip-batch-results");
    for (const row of results) {
      const item = this.el("li");
      if (row.url) {
        const link = this.el("a", null, `Clip ${row.clip.rank} · ${formatClock(row.clip.start)}–${formatClock(row.clip.end)}`);
        link.href = row.url;
        if (row.name) link.download = row.name;
        item.append(link);
      } else {
        item.className = "failed";
        item.textContent = `${row.clip ? `Clip ${row.clip.rank}: ` : ""}${row.error || "Not exported."}`;
      }
      list.append(item);
    }
    this.batchPanel.replaceChildren(head, list);
    this.batchPanel.hidden = false;
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
