// Explicit, installation-level model downloads. Opening this panel never downloads.
export function modelSize(value) {
  return Number.isFinite(Number(value)) && Number(value) > 0 ? `About ${Number(value).toFixed(2).replace(/0$/, "")} GB` : "Size varies";
}

export function initLocalModels({document, api, changed = async () => {}, busy = () => false, schedule = setTimeout, unschedule = clearTimeout}) {
  const el = id => document.getElementById(id);
  const host = el("localModelCards");
  if (!host) return null;
  let catalog = null, review = null, active = null, timer = null, submitting = false, failures = 0, generation = 0, connectionMode = "local", cancellingId = null;
  const choices = {};
  const live = message => { el("localModelsStatus").textContent = message; };
  const make = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  const running = job => ["queued", "running", "cancelling"].includes(job?.status);
  function cancelReview() { review = null; el("modelDownloadConfirm").hidden = true; }
  function updateSummary() {
    if (!catalog) return;
    const installed = catalog.models.filter(model => model.installed);
    const both = ["editor", "transcription"].every(kind => installed.some(model => model.kind === kind));
    el("homeLocalStatus").textContent = active ? "Model download in progress" : both ? "Local models found" : "Local setup needs attention";
    el("homeLocalDetail").textContent = active ? "Open model setup to see progress or cancel. You can keep editing manually."
      : both ? "Check your selected quality profile before starting AI. Manual editing is always available."
      : "Download a transcription model and a Story model, or choose cloud AI. Manual editing needs neither.";
  }
  function renderJob() {
    const visible = Boolean(active);
    el("localDownloadJob").hidden = !visible;
    if (!visible) return;
    el("localDownloadLabel").textContent = active.message || "Preparing model download…";
    const progress = Number(active.progress);
    el("localDownloadProgress").value = Number.isFinite(progress) ? Math.max(0, Math.min(1, progress)) : 0;
    const cancelling = active.cancel_requested || active.status === "cancelling" || cancellingId === active.id;
    el("cancelLocalDownload").disabled = Boolean(cancelling);
    el("cancelLocalDownload").textContent = cancelling ? "Cancelling…" : "Cancel download";
  }
  function render() {
    if (!catalog) return;
    const runtime = catalog.runtime || {};
    el("localRuntimeTitle").textContent = runtime.available ? "Story engine available at last check" : runtime.installed ? "Story engine is installed" : "Install the Story engine first";
    el("localRuntimeDetail").textContent = runtime.message || "Story AI uses Ollama. Transcription uses a separate model. Neither is needed for manual editing.";
    el("localRuntimeInstall").hidden = Boolean(runtime.installed || runtime.available);
    el("startLocalEngine").hidden = !runtime.installed && !runtime.available;
    el("startLocalEngine").textContent = runtime.available ? "Check local engine" : "Start local engine";
    host.replaceChildren();
    for (const [kind, title, purpose] of [
      ["transcription", "1. Transcription", "Turns speech into editable text and timed captions. Does not translate your recording."],
      ["editor", "2. Story AI", "Helps understand the transcript and plan the draft. Required for AI Shorts and conversation clips."],
    ]) {
      const models = catalog.models.filter(model => model.kind === kind);
      const card = make("section", "", "local-model-card");
      card.append(make("h4", title), make("p", purpose));
      const label = make("label", "Choose a model");
      const select = make("select"); select.setAttribute("aria-label", `${title} model`);
      for (const model of models) {
        const option = make("option", `${model.label || model.model}${model.installed ? " · Downloaded" : ""}`);
        option.value = model.model; select.append(option);
      }
      const selected = models.find(model => model.model === choices[kind]) || models.find(model => model.profiles?.includes("balanced")) || models[0];
      if (selected) { choices[kind] = selected.model; select.value = selected.model; }
      const description = make("p", "", "model-description");
      const facts = make("p", "", "model-facts");
      const download = make("button", "", "button ghost"); download.type = "button";
      const fill = () => {
        const model = models.find(item => item.model === select.value);
        if (!model) { download.disabled = true; description.textContent = "No configured model is available."; return; }
        choices[kind] = model.model;
        description.textContent = `${model.description || ""} ${model.requirements || ""}`.trim();
        facts.textContent = `${modelSize(model.estimated_download_gb)} download · ${model.installed ? "Downloaded" : model.status === "unknown" ? "Status not verified" : "Not downloaded"} · Used by: ${(model.profiles || []).join(", ") || "configured profile"}`;
        download.textContent = model.installed ? "Downloaded" : `Download ${kind === "editor" ? "Story" : "transcription"} model`;
        download.disabled = model.installed || model.can_download === false || Boolean(active) || submitting;
      };
      select.addEventListener("change", () => { cancelReview(); fill(); });
      download.addEventListener("click", () => {
        if (submitting || active) return;
        if (busy()) { live("Finish or cancel active processing before downloading models."); return; }
        const candidate = models.find(item => item.model === select.value);
        if (!candidate || candidate.installed || candidate.can_download === false) return;
        review = candidate;
        el("modelDownloadSummary").textContent = `Download ${review.label || review.model}? ${modelSize(review.estimated_download_gb)} of internet data and at least that much free disk space are needed; actual size can vary. No footage is uploaded. Downloading does not change your project's quality profile.`;
        el("modelDownloadConfirm").hidden = false;
        el("confirmModelDownload").focus();
      });
      label.append(select); card.append(label, description, facts, download); host.append(card); fill();
    }
    renderJob(); updateSummary();
  }
  async function refresh() {
    const token = ++generation;
    el("refreshLocalModels").disabled = true;
    try {
      const result = await api("/api/models/local");
      if (token !== generation) return;
      catalog = result;
      active = (result.jobs || []).find(running) || null;
      const recent = (result.jobs || [])[0];
      live(active ? "The download continues if you close this window."
        : ["failed", "interrupted"].includes(recent?.status) ? `The previous download did not finish. ${recent.error || recent.message || "Choose the model to retry when ready."}`
        : recent?.status === "cancelled" ? "The previous download was cancelled. Cached files may be reused if you choose to download again."
        : "Nothing downloads until you choose a model and confirm.");
      render();
      if (active && timer === null) timer = schedule(poll, 1500);
      return true;
    } catch (error) {
      if (token === generation) live(`Could not check local setup. ${error.message} Use Refresh to try again.`);
      return false;
    }
    finally { if (token === generation) el("refreshLocalModels").disabled = false; }
  }
  async function poll() {
    timer = null;
    if (!active) return;
    const jobId = active.id;
    try {
      const response = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      if (active?.id !== jobId) return;
      active = response.job; failures = 0;
      if (!running(active)) {
        const terminal = active;
        active = null;
        render();
        const refreshed = await refresh();
        const outcome = terminal.status === "completed" ? "Download complete. Choose the matching quality profile in your project."
          : terminal.status === "cancelled" ? "Download cancelled. A later download may reuse cached files."
          : `Download did not finish. ${terminal.error || terminal.message || "Refresh and try again."}`;
        live(`${outcome}${refreshed === false ? " Could not refresh model inventory. Use Refresh to check the current status." : ""}`);
        await changed();
        return;
      }
      renderJob(); updateSummary();
    } catch (error) {
      failures += 1;
      live(`Progress check failed. ${error.message}${failures >= 3 ? " Open model setup or press Refresh to reconnect." : " Reconnecting…"}`);
    }
    if (active && failures < 3 && timer === null) timer = schedule(poll, 1500);
  }
  el("confirmModelDownload").addEventListener("click", async () => {
    if (!review || submitting || active) return;
    const available = catalog?.models.find(model => model.kind === review.kind && model.model === review.model);
    if (!available || available.installed || available.can_download === false) {
      cancelReview(); live("This model is already downloaded or is not available to download. Refresh local setup for its current status."); return;
    }
    if (busy()) { live("Finish active processing before downloading."); return; }
    const requested = review; submitting = true;
    el("confirmModelDownload").disabled = true;
    try {
      const result = await api("/api/models/install", {method: "POST", body: JSON.stringify({kind: requested.kind, model: requested.model})});
      active = result.job; failures = 0; cancelReview();
      live("Download started. Closing this window does not cancel it.");
      render();
      if (timer !== null) unschedule(timer);
      timer = schedule(poll, 1000);
    } catch (error) { live(error.message); }
    finally { submitting = false; el("confirmModelDownload").disabled = false; render(); }
  });
  el("dismissModelDownload").addEventListener("click", cancelReview);
  el("cancelLocalDownload").addEventListener("click", async () => {
    if (!active || active.cancel_requested || active.status === "cancelling" || cancellingId) return;
    const jobId = active.id; cancellingId = jobId; renderJob();
    try {
      const result = await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method: "POST", body: "{}"});
      if (active?.id !== jobId) return;
      active = result.job || {...active, cancel_requested: true}; renderJob();
      if (timer === null) timer = schedule(poll, 500);
    } catch (error) { live(error.message); }
    finally { if (cancellingId === jobId) cancellingId = null; renderJob(); }
  });
  el("startLocalEngine").addEventListener("click", async () => {
    if (connectionMode !== "local") { live("Save On my computer as your AI connection first, then start its engine."); return; }
    if (busy()) { live("Finish active processing before starting the local engine."); return; }
    el("startLocalEngine").disabled = true;
    try {
      await api("/api/runtime/prepare", {method: "POST", body: "{}"});
      await refresh(); await changed();
    } catch (error) { live(error.message); }
    finally { el("startLocalEngine").disabled = false; }
  });
  el("refreshLocalModels").addEventListener("click", () => { failures = 0; void refresh(); });
  return {refresh, cancelReview, setConnection(value) { connectionMode = value.mode; }, get active() { return active; }};
}
