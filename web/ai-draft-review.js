// A saved proposal is not the current edit. Only the host's guarded Apply can
// change the project; this viewer auditions original A passages, not a render.
let activeReview = null;
let reviewNumber = 0;
const finite = value => typeof value === "number" && Number.isFinite(value);
const count = value => Number.isSafeInteger(value) && value >= 0;
const counts = value => value && count(value.A) && count(value.B);

export function formatAiReviewTime(value) {
  if (!finite(value) || value < 0 || !Number.isSafeInteger(Math.round(value * 1000))) return "Unavailable";
  const ms = Math.round(value * 1000), seconds = Math.floor(ms / 1000), pad = n => String(n).padStart(2, "0");
  return `${seconds >= 3600 ? pad(Math.floor(seconds / 3600)) + ":" : ""}${pad(Math.floor(seconds / 60) % 60)}:${pad(seconds % 60)}.${String(ms % 1000).padStart(3, "0")}`;
}

export function aiReviewProposalIssue(proposal, expected) {
  if (!expected || typeof expected.projectId !== "string" || !expected.projectId || !count(expected.revision)
    || typeof expected.originId !== "string" || !expected.originId || !proposal || typeof proposal !== "object" || proposal.project_id !== expected.projectId || proposal.revision !== expected.revision
    || proposal.origin_id !== expected.originId || typeof proposal.proposal_id !== "string" || !proposal.proposal_id.trim()) return "The review response does not match this saved draft. Close and open a fresh review.";
  if (typeof proposal.apply_allowed !== "boolean" || typeof proposal.apply_issue !== "string"
    || (proposal.apply_allowed && proposal.apply_issue) || (!proposal.apply_allowed && !proposal.apply_issue.trim())) return "The draft's application readiness could not be confirmed.";
  const current = proposal.current, next = proposal.proposed, impact = proposal.impact;
  if (!current || !finite(current.duration) || current.duration < 0 || !counts(current.source_clip_counts) || !count(current.media_count) || !count(current.text_count)) return "The current timeline summary is invalid. Close and review again.";
  if (!next || next.source_slot !== "A" || !finite(next.source_duration) || next.source_duration <= 0
    || !finite(next.output_duration) || next.output_duration <= 0 || ![next.title, next.summary, next.engine].every(value => typeof value === "string")
    || !Array.isArray(next.ranges) || !next.ranges.length) return "The saved source proposal is invalid. Your current edit has not changed.";
  for (const range of next.ranges) {
    if (!range || !finite(range.start) || !finite(range.end) || range.start < 0 || range.end <= range.start || range.end > next.source_duration + 1e-8) return "A proposed passage falls outside the original source. Close and review again.";
  }
  if (impact !== null && (!impact || !finite(impact.duration) || impact.duration < 0 || !counts(impact.source_clip_counts)
    || typeof impact.media_preserved !== "boolean" || typeof impact.text_preserved !== "boolean")) return "The prospective timeline summary is invalid. Your edit has not changed.";
  if (proposal.apply_allowed && !impact) return "The result of applying this draft could not be verified.";
  if (proposal.apply_allowed && (!impact.media_preserved || !impact.text_preserved)) return "Existing media or custom text would change. This review cannot safely apply that replacement.";
  if (!Array.isArray(proposal.warnings) || !proposal.warnings.every(value => typeof value === "string")) return "The draft's review warnings are invalid.";
  const request = proposal.request;
  if (!request || ![request.instruction, request.style].every(value => typeof value === "string")
    || !(request.duration_mode === null || typeof request.duration_mode === "string")
    || !(request.target_duration === null || finite(request.target_duration) && request.target_duration >= 0)) return "The saved request could not be confirmed.";
  return "";
}

export class AiDraftReview {
  constructor(options) {
    this.options = options;
    this.closed = false;
    this.applying = false;
    this.previewed = false;
    this.rangeIndex = 0;
    this.playRequest = 0;
    this.abort = new AbortController();
  }

  node(tag, className = "", text = "") {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  }

  button(text, marker, className = "button ghost compact") {
    const button = this.node("button", className, text);
    button.type = "button"; button.setAttribute(marker, "");
    return button;
  }

  current() {
    if (this.closed) return false;
    try { return this.options.isCurrent() === true; } catch { return false; }
  }

  guard() {
    if (this.closed) return false;
    if (this.current()) return true;
    this.failed = true; this.previewed = false;
    this.video?.pause();
    this.message.textContent = "The project changed. Close this review and open it again before applying.";
    this.updateControls();
    return false;
  }

  async open() {
    if (this.closed) return false;
    if (this.dialog) return this.dialog.open;
    if (activeReview && !activeReview.close()) return false;
    activeReview = this;
    this.returnFocus = document.activeElement;
    this.dialog = this.node("dialog", "sheet-dialog ai-draft-review");
    const titleId = `aiDraftReviewTitle-${++reviewNumber}`;
    this.dialog.setAttribute("aria-labelledby", titleId);
    const shell = this.node("div", "ai-review-shell"), header = this.node("header", "ai-review-header");
    const title = this.node("h2", "", "Review saved AI draft"); title.id = titleId;
    this.closeButton = this.button("×", "data-ai-review-close", "icon-button"); this.closeButton.setAttribute("aria-label", "Close draft review");
    header.append(title, this.closeButton);
    this.message = this.node("p", "ai-review-status", "Loading the saved proposal. Your current timeline remains active.");
    this.message.setAttribute("role", "status"); this.message.setAttribute("aria-live", "polite");
    this.content = this.node("div", "ai-review-content"); this.content.hidden = true;
    this.footer = this.node("footer", "ai-review-footer");
    this.applyHint = this.node("p", "ai-review-apply-hint", "Inspect the source before deciding. Nothing is applied by opening this review.");
    const actions = this.node("div", "ai-review-actions");
    this.keepButton = this.button("Keep current edit", "data-ai-review-keep", "button ghost");
    this.applyButton = this.button("Apply reviewed draft", "data-ai-review-apply", "button primary"); this.applyButton.disabled = true;
    actions.append(this.keepButton, this.applyButton); this.footer.append(this.applyHint, actions);
    shell.append(header, this.message, this.content, this.footer); this.dialog.append(shell); document.body.append(this.dialog);
    this.keepButton.addEventListener("click", () => this.close()); this.closeButton.addEventListener("click", () => this.close());
    this.applyButton.addEventListener("click", () => { void this.apply(); });
    this.dialog.addEventListener("cancel", event => { event.preventDefault(); this.close(); });
    this.dialog.addEventListener("close", () => { if (!this.closed) this.close(); });
    this.dialog.showModal(); this.keepButton.focus();
    try {
      if (!this.guard()) return false;
      const { projectId, revision, originId } = this.options;
      const response = await this.options.api(`/api/projects/${encodeURIComponent(projectId)}/ai-draft-proposal`, {
        method: "POST", signal: this.abort.signal, body: JSON.stringify({expected_revision: revision, origin_id: originId}),
      });
      if (this.closed) return false;
      if (!this.guard()) return false;
      const issue = aiReviewProposalIssue(response?.proposal, this.options);
      if (issue) throw new Error(issue);
      if (typeof this.options.sourceUrl !== "string" || !this.options.sourceUrl.trim()) throw new Error("The original source is unavailable. Your edit has not changed.");
      this.proposal = response.proposal;
      this.renderProposal();
      this.content.hidden = false;
      this.message.textContent = "Your current timeline remains active. This is a saved proposal, not an applied edit.";
      this.video.src = this.options.sourceUrl; this.video.load();
      this.updateControls();
      return true;
    } catch (error) {
      if (!this.closed) { this.failed = true; this.message.textContent = error?.message || "The saved draft could not be reviewed. Your edit has not changed."; this.updateControls(); }
      return false;
    }
  }

  summaryCard(title, duration, sourceCounts, media, text) {
    const card = this.node("section", "ai-review-comparison-card");
    card.append(this.node("h3", "", title), this.node("strong", "ai-review-duration", formatAiReviewTime(duration)));
    if (sourceCounts) card.append(this.node("p", "", `Source A: ${sourceCounts.A} clips · Source B: ${sourceCounts.B} clips`), this.node("p", "", `${media === null ? "Imported media changes" : `${media} imported media`} · ${text === null ? "Custom text changes" : `${text} custom text layers`}`));
    return card;
  }

  renderProposal() {
    const p = this.proposal, next = p.proposed, impact = p.impact;
    const comparison = this.node("div", "ai-review-comparison"); comparison.setAttribute("data-ai-review-comparison", "");
    comparison.append(this.summaryCard("Current timeline", p.current.duration, p.current.source_clip_counts, p.current.media_count, p.current.text_count));
    comparison.append(this.summaryCard("After applying", impact?.duration, impact?.source_clip_counts, impact?.media_preserved ? p.current.media_count : null, impact?.text_preserved ? p.current.text_count : null));
    this.content.append(comparison);
    if (!p.apply_allowed) {
      const blocked = this.node("p", "ai-review-blocked", p.apply_issue); blocked.setAttribute("data-ai-review-blocked", ""); blocked.setAttribute("role", "alert"); this.content.append(blocked);
    }
    const impactNote = this.node("p", "ai-review-impact", impact
      ? `Applying restores the draft's source edit. ${impact.media_preserved && impact.text_preserved ? `${p.current.media_count} imported media and ${p.current.text_count} custom text layers remain at their existing times.` : "The existing imported media or custom text also changes; inspect the application warning carefully."} Original files stay in place. Undo can restore the current timeline.`
      : "This saved proposal cannot currently replace the source edit. Inspecting it does not retime or remove your existing layers.");
    this.content.append(impactNote);
    const proposalInfo = this.node("section", "ai-review-proposal");
    const heading = this.node("h3", "", next.title || "Saved AI draft"); heading.dir = "auto";
    const summary = this.node("p", "", next.summary); summary.dir = "auto";
    proposalInfo.append(heading, summary, this.node("p", "ai-review-meta", `Engine: ${next.engine || "Not recorded"} · Selected source: ${formatAiReviewTime(next.output_duration)} · ${next.ranges.length} passages`));
    this.content.append(proposalInfo);
    if (p.warnings.length) {
      const warnings = this.node("section", "ai-review-warnings"), list = this.node("ul");
      warnings.append(this.node("h3", "", "Needs review"));
      p.warnings.forEach(text => { const row = this.node("li", "", text); row.dir = "auto"; list.append(row); }); warnings.append(list); this.content.append(warnings);
    }
    const request = this.node("details", "ai-review-request");
    request.append(this.node("summary", "", "Saved request"));
    const instruction = this.node("p", "", p.request.instruction || "No written instruction was saved."); instruction.dir = "auto";
    request.append(instruction, this.node("p", "", `Style: ${p.request.style || "Not recorded"} · Duration: ${p.request.target_duration === null ? "Not specified" : `${p.request.target_duration} s`} (${p.request.duration_mode || "Not recorded"})`)); this.content.append(request);
    const audition = this.node("section", "ai-review-audition");
    audition.append(this.node("h3", "", "Inspect original source passages"), this.node("p", "ai-review-audition-note", "Original source A at normal speed only. This is not the final composite: source B, layers, effects and the edited audio mix are not auditioned here."));
    const layout = this.node("div", "ai-review-audition-layout"), monitor = this.node("div", "ai-review-monitor");
    this.video = this.node("video"); this.video.playsInline = true; this.video.preload = "metadata"; this.video.controls = false; this.video.playbackRate = this.video.defaultPlaybackRate = 1;
    this.video.setAttribute("aria-label", "Original source A passage preview"); this.video.setAttribute("data-ai-review-video", "");
    this.playButton = this.button("Play this passage", "data-ai-review-play"); this.playButton.disabled = true;
    this.sourceStatus = this.node("p", "ai-review-source-status", "Loading original source…"); this.sourceStatus.setAttribute("role", "status");
    monitor.append(this.video, this.playButton, this.sourceStatus);
    const list = this.node("ol", "ai-review-passages"); list.setAttribute("aria-label", "Proposed source passages");
    this.rangeButtons = next.ranges.map((range, index) => {
      const row = this.node("li"), button = this.button(`Passage ${index + 1}: ${formatAiReviewTime(range.start)} – ${formatAiReviewTime(range.end)}`, "data-ai-review-passage", "ai-review-passage");
      button.setAttribute("aria-pressed", String(index === 0)); button.addEventListener("click", () => this.selectRange(index)); row.append(button); list.append(row); return button;
    });
    layout.append(monitor, list); audition.append(layout); this.content.append(audition);
    this.pendingSeek = true;
    this.playButton.addEventListener("click", () => { void this.playRange(); });
    this.video.addEventListener("loadedmetadata", () => this.metadata());
    this.video.addEventListener("durationchange", () => { if (this.video.readyState >= 1) this.metadata(); });
    this.video.addEventListener("play", () => {
      if (this.applying || !this.guard() || !this.metadataReady || this.failed) { this.video.pause(); return; }
      const range = this.proposal.proposed.ranges[this.rangeIndex];
      if (this.video.currentTime < range.start || this.video.currentTime >= range.end) this.seekRange(false);
    });
    this.video.addEventListener("playing", () => {
      if (this.applying || this.video.paused || !this.guard() || this.failed || !this.metadataReady || this.video.readyState < 2 || this.video.seeking) return;
      const range = this.proposal.proposed.ranges[this.rangeIndex];
      if (this.video.currentTime < range.start - .001 || this.video.currentTime >= range.end) return;
      this.previewed = true; this.updateControls(); this.watchFrame();
    });
    this.video.addEventListener("ratechange", () => {
      if (this.closed || this.video.playbackRate === 1) return;
      try { this.video.playbackRate = 1; }
      catch { this.sourceFailure("Normal-speed source playback is unavailable. Close and review again."); }
    });
    this.video.addEventListener("timeupdate", () => this.checkRange());
    this.video.addEventListener("pause", () => this.stopFrameWatch());
    this.video.addEventListener("ended", () => this.stopFrameWatch());
    this.video.addEventListener("error", () => this.sourceFailure("Original source playback failed. Close and review again; your current edit has not changed."));
  }

  sourceFailure(message) {
    if (this.closed) return;
    this.failed = true; this.previewed = false; this.metadataReady = false; this.playRequest++;
    this.video?.pause(); if (this.video) this.video.controls = false;
    this.sourceStatus.textContent = message; this.updateControls();
  }

  metadata() {
    if (this.closed || this.failed || !this.proposal || !this.guard()) return;
    const expected = this.proposal.proposed.source_duration, duration = this.video.duration;
    if (!finite(duration) || duration <= 0 || !this.video.videoWidth || !this.video.videoHeight
      || Math.abs(duration - expected) > .05 || this.proposal.proposed.ranges.some(range => range.end > duration + 1e-8)) {
      this.sourceFailure("Original source metadata does not match this review. Close and load a fresh review."); return;
    }
    this.metadataReady = true; this.video.controls = true;
    if (this.pendingSeek) this.seekRange();
    this.updateControls();
  }

  selectRange(index) {
    if (this.closed || this.applying || this.failed || !this.guard() || !Number.isInteger(index) || !this.proposal?.proposed.ranges[index]) return false;
    this.playRequest++; this.video.pause(); this.rangeIndex = index; this.pendingSeek = true;
    this.rangeButtons.forEach((button, i) => button.setAttribute("aria-pressed", String(i === index)));
    if (this.metadataReady) this.seekRange();
    return true;
  }

  seekRange(pause = true) {
    if (this.closed || this.failed || !this.metadataReady || !this.guard()) return false;
    const range = this.proposal.proposed.ranges[this.rangeIndex];
    if (pause) this.video.pause();
    try { this.video.currentTime = range.start; }
    catch { this.sourceFailure("The browser could not seek to this passage. Your current edit has not changed."); return false; }
    this.pendingSeek = false;
    this.sourceStatus.textContent = `Passage ${this.rangeIndex + 1} of ${this.proposal.proposed.ranges.length}: ${formatAiReviewTime(range.start)} – ${formatAiReviewTime(range.end)}. Source preview only; browser seeking is not frame-accurate editing.`;
    return true;
  }

  async playRange() {
    if (this.closed || this.applying || this.failed || !this.metadataReady || !this.guard()) return false;
    const token = ++this.playRequest;
    if (!this.seekRange()) return false;
    try { await this.video.play(); return !this.closed && token === this.playRequest; }
    catch (error) {
      if (!this.closed && token === this.playRequest) this.sourceStatus.textContent = error?.message || "Playback did not start. Use the video controls to try again.";
      return false;
    }
  }

  checkRange() {
    if (this.closed || this.failed || !this.proposal || !this.metadataReady || this.video.paused) return;
    if (!this.guard()) return;
    const range = this.proposal.proposed.ranges[this.rangeIndex];
    if (this.video.currentTime >= range.end) this.video.pause();
    else if (this.video.currentTime < range.start - .001) this.seekRange(false);
  }

  watchFrame() {
    if (this.frameCallback != null || this.closed || this.failed || this.video.paused || !this.video.requestVideoFrameCallback) return;
    this.frameCallback = this.video.requestVideoFrameCallback(() => { this.frameCallback = null; this.checkRange(); this.watchFrame(); });
  }

  stopFrameWatch() {
    if (this.frameCallback != null) this.video?.cancelVideoFrameCallback?.(this.frameCallback);
    this.frameCallback = null;
  }

  updateControls() {
    if (this.closed) return;
    const allowed = Boolean(this.proposal?.apply_allowed && this.previewed && this.metadataReady && !this.failed && this.current());
    this.applyButton.disabled = this.applying || !allowed;
    if (this.video) this.video.controls = Boolean(this.metadataReady && !this.failed && !this.applying && this.current());
    this.keepButton.disabled = this.closeButton.disabled = this.applying;
    if (this.playButton) this.playButton.disabled = this.applying || this.failed || !this.metadataReady || !this.current();
    this.rangeButtons?.forEach(button => { button.disabled = this.applying || this.failed || !this.current(); });
    this.applyButton.title = this.applying ? "Waiting for the saved result."
      : this.failed || !this.current() ? "Close and open a fresh review."
      : this.proposal && !this.proposal.apply_allowed ? this.proposal.apply_issue
      : !this.previewed ? "Play an original source passage before applying. Playback is not semantic approval."
      : "Apply exactly this reviewed proposal. Undo remains available.";
    this.applyHint.textContent = this.applying ? "Applying the reviewed source edit. Do not close until the result is known."
      : !this.proposal ? "Inspect the source before deciding. Nothing is applied by opening this review."
      : !this.proposal.apply_allowed ? "Application is blocked. You can inspect the saved source passages or keep editing."
      : !this.previewed ? "Play a source passage before Apply. Playback does not verify its content, transcript or final composition."
      : "Source playback is not editorial approval. Apply only if you want this source edit; Undo remains available.";
  }

  async apply() {
    if (this.closed || this.applying || this.failed || !this.proposal?.apply_allowed || !this.previewed || !this.metadataReady || !this.guard()) return false;
    this.applying = true; this.playRequest++; this.video.pause(); this.updateControls();
    this.message.textContent = "Applying the reviewed draft…";
    try {
      const updated = await this.options.apply(this.proposal);
      if (updated && updated.id === this.options.projectId && Number.isSafeInteger(updated.revision) && updated.revision > this.options.revision) { this.applying = false; this.close(); return true; }
      this.failed = true; this.message.textContent = "The proposal was not applied. Close and review the current project again.";
    } catch (error) { this.failed = true; this.message.textContent = error?.message || "The proposal could not be applied. Close and review again."; }
    finally { this.applying = false; if (!this.closed) this.updateControls(); }
    return false;
  }

  close() {
    if (this.closed) return true;
    if (this.applying) return false;
    this.closed = true; this.playRequest++; this.abort.abort(); this.stopFrameWatch();
    if (this.video) { this.video.pause(); this.video.removeAttribute("src"); this.video.load(); }
    this.dialog?.close(); this.dialog?.remove();
    if (activeReview === this) activeReview = null;
    const origin = this.returnFocus;
    if (origin?.isConnected && !origin.disabled && (!origin.getClientRects || origin.getClientRects().length)) origin.focus({preventScroll:true});
    try { this.options.onClose?.(); } catch { /* Closing a read-only viewer must still release its media. */ }
    return true;
  }
}
