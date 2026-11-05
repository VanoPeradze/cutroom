// Saved speech versions are proposals. Preview never changes the project.
export function captionSourceTime(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) * 1000));
  return `${Math.floor(value / 60000)}:${((value % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}
export class CaptionAlternatives {
  constructor(options) { this.options = options; this.busy = false; this.message = ""; this.language = "he"; this.generationStatus = null; this.generationKey = ""; this.generationJob = null; }
  text(he, en) { return this.options.copy(he, en); }
  node(tag, text, className) {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  button(text, action) {
    const button = this.node("button", text); button.type = "button";
    button.disabled = this.busy;
    button.addEventListener("click", () => Promise.resolve().then(action).catch(error => this.error(error)));
    return button;
  }
  error(error) { this.message = error?.message || String(error); this.render(); }
  render() {
    const root = this.options.root, project = this.options.getProject();
    if (!root) return;
    root.replaceChildren();
    if (!project?.analysis?.transcript) { root.hidden = true; return; }
    root.hidden = false;
    const status = project.caption_alternative_status || {state: "original"};
    root.append(this.node("h4", this.text("גרסאות כתוביות שמורות", "Saved caption versions")));
    root.append(this.node("p", status.state === "stale" ? status.reason : status.state === "alternative"
      ? this.text(`פעילה: ${status.label} · תמלול שלא אומת`, `Active: ${status.label} · unverified ASR`)
      : this.text("הכתוביות המקוריות פעילות. חלופה תשנה רק כתוביות בעריכה הנוכחית.", "Original captions active. An alternative changes captions only in the current edit.")));
    const controls = this.node("div", null, "caption-version-controls");
    const original = this.button(this.text("סקירת המקור", "Review original"), () => this.open("original"));
    original.dataset.captionReview = "original"; controls.append(original);
    for (const saved of project.caption_alternatives || []) {
      const button = this.button(saved.label, () => this.open(saved.id));
      button.dataset.captionAlternative = saved.id;
      controls.append(button);
    }
    const input = this.node("input"); input.type = "file"; input.accept = ".json,application/json";
    input.hidden = true; input.setAttribute("aria-label", "Load saved source-bound transcript JSON");
    input.addEventListener("change", async () => {
      const file = input.files?.[0]; if (!file) return;
      try {
        if (file.size > 512 * 1024) throw new Error(this.text("הקובץ חייב להיות עד 512 KiB.", "Saved transcripts must be at most 512 KiB."));
        if (!(await this.options.beforeReview())) return;
        const displayed = this.options.getProject();
        const alternative = JSON.parse(await file.text());
        if (this.options.getProject()?.id !== displayed.id || this.options.getProject()?.revision !== displayed.revision) throw new Error("The project changed while reading this file. Load it again.");
        this.busy = true; this.render();
        const payload = await this.options.api(`/api/projects/${encodeURIComponent(displayed.id)}/caption-alternatives`, {
          method: "POST", body: JSON.stringify({alternative, expected_revision: displayed.revision})});
        if (this.options.getProject()?.id !== displayed.id) return;
        if (this.options.getProject()?.revision !== displayed.revision) throw new Error("The project changed while loading. Refresh before reviewing the saved alternative.");
        this.options.acceptProject(payload.project);
        this.message = this.text("החלופה נשמרה לסקירה. הכתוביות עדיין לא הוחלפו.", "Alternative saved for review. Captions have not been switched.");
      } catch (error) { this.message = error.message; }
      finally { this.busy = false; this.render(); }
    });
    const load = this.button(this.text("טעינת חלופה שמורה…", "Load saved alternative…"), () => input.click());
    load.dataset.captionLoad = "true"; controls.append(load, input);
    root.append(controls);
    this.renderGeneration(root, project);
    root.append(this.node("p", this.text("תמלול אוטומטי אינו אימות של המילים שנאמרו. יש להאזין ולבדוק; המקור ועריכת הווידאו נשמרים.", "Automatic transcription is not verified speech. Listen and review; the original transcript and video edit are preserved."), "caption-version-note"));
    const message = this.node("p", this.message); message.setAttribute("role", "status"); root.append(message);
  }
  renderGeneration(root, project) {
    const controls = this.node("div", null, "caption-version-controls");
    const label = this.node("label", this.text("שפת הדיבור: ", "Spoken language: "));
    const select = this.node("select"); select.dataset.captionLanguage = "true";
    select.setAttribute("aria-label", this.text("שפת הדיבור", "Spoken language"));
    for (const [value,title] of [["he","עברית / Hebrew"],["en","English / אנגלית"]]) {
      const option = this.node("option", title); option.value=value; select.append(option);
    }
    select.value=this.language;select.disabled=this.busy;
    select.addEventListener("change",()=>{this.language=select.value;this.generationKey="";this.generationStatus=null;this.render();});label.append(select);controls.append(label);
    const selection=this.options.getSelection?.();
    const start=this.button(selection ? this.text("תמלול חלופי לטווח המסומן", "Generate for selected timeline range") : this.text("יצירת חלופה מקומית לעריכה הזאת", "Generate local alternative for this edit"),()=>this.generate());
    start.dataset.captionGenerate="true";start.disabled=this.busy || !this.generationStatus?.ready;controls.append(start);
    if(this.generationJob){
      const cancel=this.button(this.text("ביטול התמלול", "Cancel transcription"),async()=>{
        await this.options.api(`/api/jobs/${encodeURIComponent(this.generationJob)}/cancel`,{method:"POST",body:"{}"});
        this.message=this.text("נשלחה בקשת ביטול; ממתינים לסיום התהליך המקומי.","Cancellation requested; waiting for the local worker to stop.");this.render();
      });cancel.disabled=false;cancel.dataset.captionGenerateCancel="true";controls.append(cancel);
    }
    root.append(controls);
    root.append(this.node("p",this.text("רצף מקור אחד עד 90 שניות. נשמרת חלופה לבדיקה; המקור אינו מוחלף.","Selected timeline range, up to 90 seconds across up to eight ordered source-A pieces. Outside captions stay unchanged; manual conflicts block Apply.")));
    if(this.generationStatus)root.append(this.node("p",this.generationStatus.message));
    const key=`${project.id}:${project.revision}:${this.language}:${JSON.stringify(selection)}`;
    if(!this.busy && this.generationKey!==key){
      this.generationKey=key;this.generationStatus=null;
      this.options.api(`/api/projects/${encodeURIComponent(project.id)}/caption-generation?language=${this.language}${selection ? `&start=${selection.start}&end=${selection.end}` : ""}`)
        .then(value=>{if(this.generationKey===key){this.generationStatus=value;this.render();}})
        .catch(error=>{if(this.generationKey===key){this.generationStatus={ready:false,message:error.message};this.render();}});
    }
  }
  async generate() {
    if(this.busy || !(await this.options.beforeReview()))return;
    const displayed=this.options.getProject(), language=this.language, selection=this.options.getSelection?.();
    this.busy=true;this.message=this.text("מכינים תמלול מקומי…", "Preparing local transcription…");this.render();
    try{
      const payload=await this.options.api(`/api/projects/${encodeURIComponent(displayed.id)}/caption-generation`,{
        method:"POST",body:JSON.stringify({language,expected_revision:displayed.revision,...(selection ? {selection} : {})})});
      this.generationJob=payload.job.id;this.render();
      let job=payload.job;
      while(["queued","running"].includes(job.status)){
        await new Promise(resolve=>setTimeout(resolve,500));
        job=(await this.options.api(`/api/jobs/${encodeURIComponent(this.generationJob)}`)).job;
        this.message=`${Math.round((job.progress||0)*100)}% · ${job.message}`;this.render();
      }
      if(job.status!=="completed")throw new Error(job.error || job.message || "Transcription stopped; nothing applied.");
      if(this.options.getProject()?.id!==displayed.id)return;
      if(this.options.getProject()?.revision!==displayed.revision)throw new Error("The edit changed. Refresh before reviewing the saved alternative.");
      const refreshed=await this.options.api(`/api/projects/${encodeURIComponent(displayed.id)}`);
      if(this.options.getProject()?.id===displayed.id && this.options.getProject()?.revision===displayed.revision)this.options.acceptProject(refreshed.project);
      this.message=this.text("החלופה נשמרה. יש להאזין ולבחור החלה במפורש; המקור נשאר פעיל.","Alternative saved. Listen and Apply explicitly; original captions remain active.");
    }catch(error){this.message=error.message;}
    finally{this.busy=false;this.generationJob=null;this.generationKey="";this.render();}
  }
  async open(id) {
    if (this.busy || !(await this.options.beforeReview())) return;
    const displayed = this.options.getProject();
    const current = () => this.options.getProject()?.id === displayed.id && this.options.getProject()?.revision === displayed.revision;
    const payload = await this.options.api(`/api/projects/${encodeURIComponent(displayed.id)}/caption-alternatives/${encodeURIComponent(id)}`);
    if (!current() || payload.proposal.revision !== displayed.revision) throw new Error("The edit changed. Open the caption review again.");
    const proposal = payload.proposal;
    const dialog = this.node("dialog", null, "caption-version-dialog");
    dialog.setAttribute("aria-labelledby", "captionVersionReviewTitle");
    const title = this.node("h3", this.text("סקירת גרסת כתוביות", "Review caption version")); title.id = "captionVersionReviewTitle";
    dialog.append(title, this.node("p", `${proposal.label} · ${proposal.duration.toFixed(2)} s · ${this.text("לא אומת בהאזנה", "not verified by listening")}`));
    dialog.append(this.node("p", proposal.ranges.map(r => `${captionSourceTime(r.start)} – ${captionSourceTime(r.end)}`).join(" · ")));
    const notice = this.node("p", this.text("מוצגות שורות מקור סביב העריכה. לחיצה על זמן משמיעה את השורה המקורית; תצוגה זו אינה משנה כתוביות.", "Source lines surrounding the edit are shown. Select a timestamp to hear that source line; this preview does not change captions."));
    dialog.append(notice);
    const video = this.node("video"); video.controls = true; video.preload = "metadata"; video.playsInline = true;
    video.src = this.options.sourceUrl(displayed.sources.A);
    let stopAt = Infinity;
    video.addEventListener("timeupdate", () => { if (video.currentTime >= stopAt) video.pause(); });
    dialog.append(video);
    const columns = this.node("div", null, "caption-version-columns");
    const tooLong = [proposal.original, proposal.alternative].some(rows => rows.length > 200);
    for (const [heading, rows] of [[this.text("תמלול מקורי", "Original transcript"), proposal.original], [this.text("חלופה שלא אומתה", "Unverified alternative"), proposal.alternative]]) {
      const column = this.node("section"); column.append(this.node("h4", heading));
      for (const row of rows.slice(0, 200)) {
        const line = this.node("div", null, "caption-version-row");
        const seek = this.button(`${captionSourceTime(row.start)} – ${captionSourceTime(row.end)}`, async () => {
          stopAt = row.end; video.currentTime = row.start; await video.play();
        });
        const text = this.node("p", row.text); text.dir = "auto";
        line.append(seek, text); column.append(line);
      }
      columns.append(column);
    }
    dialog.append(columns);
    const status = this.node("p", proposal.manual_caption_edits
      ? proposal.blocked_reason || this.text("עריכות כתוביות קיימות נשמרות. יש לבטל אותן לפני החלפת גרסה.", "Existing caption edits are preserved. Undo them before switching versions.")
      : this.text("החלה מפורשת בלבד. לאחר ההחלה אפשר להשתמש ב־Undo בעריכה.", "Apply explicitly; use the editor's Undo to restore the previous captions."));
    status.setAttribute("role", "status"); dialog.append(status);
    if (tooLong) status.textContent = "Preview is limited to 200 lines per version. Trim the edit to review and apply a smaller range.";
    const footer = this.node("footer");
    const close = () => { video.pause(); dialog.close(); };
    const apply = this.button(this.text("החל כתוביות אלה", "Apply these captions"), async () => {
      if (this.busy) return;
      if (!current()) { status.textContent = "The edit changed. Close and review again; nothing was applied."; return; }
      this.busy = true; apply.disabled = true;
      try {
        const updated = await this.options.apply(proposal, current);
        if (!updated) {
          status.textContent = current() ? "Nothing was applied. The edit changed or has pending saves; close and review again." : "The edit changed. Close and review again; nothing was applied.";
          return;
        }
        this.message = this.text("גרסת הכתוביות הוחלה. Undo יחזיר את הגרסה הקודמת.", "Caption version applied. Undo restores the previous version.");
        close();
      } catch (error) { status.textContent = error.message; }
      finally { this.busy = false; apply.disabled = false; this.render(); }
    });
    apply.className = "button primary"; apply.dataset.captionApply = "true";
    apply.disabled = proposal.manual_caption_edits || tooLong;
    const keep = this.button(this.text("שמור את העריכה הנוכחית", "Keep current edit"), close);
    keep.className = "button ghost"; keep.dataset.captionKeep = "true";
    footer.append(keep, apply);
    dialog.append(footer);
    dialog.addEventListener("close", () => { video.pause(); video.removeAttribute("src"); video.load(); dialog.remove(); });
    document.body.append(dialog); dialog.showModal();
  }
}
