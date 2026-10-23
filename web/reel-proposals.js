// Existing alternatives only. Structural eligibility is not editorial approval.
export function supportsReelReview(project) {
  return Boolean(project?.sources?.A) && !(project.sources.B || "source_tracks" in (project.manual || {}) || "sequence" in (project.manual || {}));
}

let activeReview = null;

// Review ranges use the source clock, including subsecond edit boundaries.
// The general transport formatter intentionally drops that precision.
export function formatReelReviewTime(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0 || !Number.isSafeInteger(Math.round(seconds * 1000))) return "—";
  const milliseconds = Math.round(seconds * 1000);
  const whole = Math.floor(milliseconds / 1000);
  const hours = Math.floor(whole / 3600);
  const pad = value => String(value).padStart(2, "0");
  return `${hours ? pad(hours) + ":" : ""}${pad(Math.floor(whole / 60) % 60)}:${pad(whole % 60)}.${String(milliseconds % 1000).padStart(3, "0")}`;
}

export class ReelProposalReview {
  constructor(options) {
    this.options = options;
    this.closed = false;
    this.applying = false;
    this.previewed = false;
    this.rangeIndex = 0;
    this.abort = new AbortController();
  }

  label(he, en) { return this.options.copy(he, en); }

  async open() {
    activeReview?.close();
    activeReview = this;
    const node = (tag, text, className) => {
      const element = document.createElement(tag);
      if (text) element.textContent = text;
      if (className) element.className = className;
      return element;
    };
    this.dialog = node("dialog", "", "sheet-dialog");
    this.dialog.setAttribute("aria-labelledby", "reelReviewTitle");
    this.dialog.style.maxWidth = "min(720px, 94vw)";
    const shell = node("div", "", "dialog-shell");
    const title = node("h2", this.label("סקירת הצעת עריכה", "Review edit proposal"));
    title.id = "reelReviewTitle";
    this.message = node("p", this.label("טוען הצעה…", "Loading proposal…"));
    this.message.setAttribute("role", "status");
    this.ranges = node("p");
    this.ranges.dir = "ltr";
    this.request = node("p");
    this.request.dir = "auto";
    this.video = node("video");
    this.video.controls = true;
    this.video.playsInline = true;
    this.video.preload = "metadata";
    this.video.style.cssText = "width:100%;max-height:45vh;background:#000";
    this.video.setAttribute("aria-label", this.label("תצוגת טווחי המקור", "Source range preview"));
    this.applyButton = node("button", this.label("החל את ההצעה", "Apply proposal"), "button primary");
    this.applyButton.type = "button";
    this.applyButton.disabled = true;
    this.keepButton = node("button", this.label("השאר את העריכה הנוכחית", "Keep current edit"), "button ghost");
    this.keepButton.type = "button";
    shell.append(title, this.message, this.request, this.ranges, this.video, this.applyButton, this.keepButton);
    this.dialog.append(shell);
    document.body.append(this.dialog);
    this.keepButton.addEventListener("click", () => this.close());
    this.dialog.addEventListener("cancel", event => { event.preventDefault(); if (!this.applying) this.close(); });
    this.dialog.addEventListener("close", () => { if (!this.closed) this.close(); });
    this.applyButton.addEventListener("click", () => this.apply());
    this.video.addEventListener("loadedmetadata", () => this.seekRange());
    this.video.addEventListener("playing", () => {
      if (!this.proposal || this.closed || this.failed) return;
      this.previewed = true;
      this.applyButton.disabled = !this.options.isCurrent();
    });
    this.video.addEventListener("timeupdate", () => {
      if (!this.proposal || this.closed) return;
      const range = this.proposal.ranges[this.rangeIndex];
      if (this.video.currentTime < range.start - 0.1) this.seekRange();
      if (this.video.currentTime >= range.end) {
        if (this.rangeIndex + 1 < this.proposal.ranges.length && !this.video.paused) {
          this.rangeIndex++;
          this.seekRange();
        } else this.video.pause();
      }
    });
    this.video.addEventListener("error", () => {
      this.failed = true;
      this.previewed = false;
      this.applyButton.disabled = true;
      this.message.textContent = this.label("לא ניתן לנגן את המקור. העריכה לא שונתה.", "Source playback failed. Your edit is unchanged.");
    });
    this.dialog.showModal();
    this.keepButton.focus();
    try {
      const {project, candidateId, api} = this.options;
      const payload = await api(`/api/projects/${encodeURIComponent(project.id)}/reel-proposal`, {
        method: "POST", signal: this.abort.signal,
        body: JSON.stringify({candidate_id: candidateId, expected_revision: project.revision}),
      });
      if (this.closed) return;
      if (!this.options.isCurrent()) throw new Error(this.label("הפרויקט השתנה. יש לפתוח סקירה חדשה.", "The project changed. Open a fresh review."));
      const proposal = payload.proposal;
      if (!proposal || proposal.project_id !== project.id || proposal.revision !== project.revision ||
          proposal.candidate_id !== candidateId || !Array.isArray(proposal.ranges) || !proposal.ranges.length) {
        throw new Error("Invalid proposal response");
      }
      this.proposal = proposal;
      const format = formatReelReviewTime;
      const request = proposal.request || {};
      this.request.textContent = this.label("בקשה: ", "Request: ") + (request.instruction || "—") +
        this.label(" | סגנון: ", " | Style: ") + (request.style || "—") +
        this.label(" | הגדרת משך: ", " | Duration setting: ") + `${request.target_duration ?? "—"}s (${request.duration_mode || "—"})`;
      this.ranges.textContent = `${proposal.ranges.map(range => `${format(range.start)}–${format(range.end)}`).join(" · ")} | ${format(proposal.output_duration)}`;
      this.message.textContent = proposal.kind === "unverified_source_candidate" ? this.label(
        "ה־AI לא אימת את התוכן או התמלול. זו הצעה לסקירה מהמקור בלבד. נגנו ובדקו לפני החלה; העריכה הנוכחית תישמר עד שתבחרו להחיל. Undo זמין לאחר החלה.",
        "AI did not verify the content or transcript. This is an unapplied source proposal for review. Play and inspect it before applying; your edit stays unchanged until Apply. Undo remains available.") : this.label(
        "טווחי המקור לאחר העריכות הידניות. לחצו לניגון לפני החלה. זו הצעה לבדיקה; תוכן, תמלול ועיצוב סופי לא אושרו. אפשר לבטל החלה באמצעות Undo.",
        "Source ranges after manual edits. Play before applying. This proposal still needs review of content, transcription and final layout. Apply can be undone.");
      this.video.src = this.options.sourceUrl;
      this.video.load();
    } catch (error) {
      if (!this.closed) this.message.textContent = error.message;
    }
  }

  seekRange() {
    if (this.proposal && !this.closed) this.video.currentTime = this.proposal.ranges[this.rangeIndex].start;
  }

  async apply() {
    if (this.closed || this.applying || this.failed || !this.previewed || !this.proposal) return;
    if (!this.options.isCurrent()) {
      this.applyButton.disabled = true;
      this.message.textContent = this.label("הפרויקט השתנה. יש לפתוח סקירה חדשה.", "The project changed. Open a fresh review.");
      return;
    }
    this.applying = true;
    this.applyButton.disabled = this.keepButton.disabled = true;
    this.video.pause();
    try {
      const updated = await this.options.apply(this.proposal);
      if (updated) this.close();
      else this.message.textContent = this.label("ההצעה לא הוחלה. יש לסגור ולבדוק שוב.", "Proposal was not applied. Close and review again.");
    } catch (error) {
      this.message.textContent = error.message;
    } finally {
      this.applying = false;
      if (!this.closed) {
        this.failed = true;
        this.keepButton.disabled = false;
      }
    }
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.abort.abort();
    this.video.pause();
    this.video.removeAttribute("src");
    this.video.load();
    this.dialog.close();
    this.dialog.remove();
    if (activeReview === this) activeReview = null;
  }
}
