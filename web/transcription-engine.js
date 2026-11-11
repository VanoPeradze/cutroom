export function processingSummary(transcription = {}, story = {}) {
  const mode = transcription.engine || "local";
  const legacyCloud = mode === "legacy" && story.mode && story.mode !== "local";
  const provider = story.provider === "openai-compatible" ? "your API provider" : "Groq";
  const speech = mode === "cloud" ? "Cloudflare" : mode === "auto" ? "Cloudflare, then cached local fallback" : legacyCloud ? provider : "this computer";
  const storyLabel = story.mode && story.mode !== "local" ? provider : "this computer";
  return { speech, story: storyLabel, cloudSpeech: mode === "cloud" || mode === "auto" || Boolean(legacyCloud),
    note: `Transcription: ${speech}. Story AI: ${storyLabel}. Video preview and export stay local. Cloud selections send their content only when you start processing; provider limits and charges apply.` };
}

export function initTranscriptionEngine({ document, api, busy, pause, changed }) {
  const byId = id => document.getElementById(id);
  const dialog = byId("transcriptionDialog"), select = byId("transcriptionEngine");
  const consent = byId("transcriptionConsent"), status = byId("transcriptionStatus");
  let selected = {engine: "local"}, story = {}, saving = false, refreshing = false, generation = 0, reviewedScope = "";
  const isCloud = () => ["cloud", "auto"].includes(select.value);
  const announce = (message, error = false) => { status.textContent = message; status.dataset.error = String(error); };
  function summary() {
    const info = processingSummary(selected, story);
    const text = (id, value) => { const element = byId(id); if (element) element.textContent = value; };
    text("processingBadge", info.cloudSpeech || story.mode && story.mode !== "local" ? "Mixed / cloud AI" : "Local AI");
    text("homeConnectionStatus", `Transcription: ${info.speech}`);
    text("homeConnectionDetail", `Story AI: ${info.story}. These choices are independent; editing and export stay local.`);
    text("homePrivacyNote", info.note);
    text("transcriptionCurrent", `Current transcription: ${info.speech}.`);
    text("transcriptionLegacyDestination", `Follows the saved Story AI connection (${info.story}). A cloud connection requires its own existing key and consent. Selecting local transcription here overrides that connection for audio only, not Story AI text.`);
  }
  function controls() {
    const locked = saving || refreshing;
    select.disabled = locked;
    consent.disabled = locked || !isCloud();
    byId("saveTranscription").disabled = locked || isCloud() && (!selected.cloud_ready || !consent.checked);
    byId("refreshTranscription").disabled = locked;
    byId("closeTranscription").disabled = saving;
    byId("cancelTranscription").disabled = saving;
  }
  function renderChoice() {
    byId("transcriptionCloudFields").hidden = !isCloud();
    byId("transcriptionLocalNote").hidden = !["local", "auto"].includes(select.value);
    byId("transcriptionLegacyNote").hidden = select.value !== "legacy";
    byId("transcriptionFallbackNote").hidden = select.value !== "auto";
    byId("transcriptionLocalHeading").textContent = select.value === "auto" ? "Cached local fallback requirements" : "Local means no audio upload.";
    byId("transcriptionAccount").textContent = selected.account_id || "Not configured";
    byId("transcriptionModel").textContent = selected.model || "@cf/openai/whisper-large-v3-turbo";
    byId("transcriptionDisclosure").textContent = selected.disclosure || "Load the current privacy and billing disclosure before enabling Cloudflare.";
    byId("transcriptionCloudReadiness").textContent = selected.cloud_ready
      ? "Credentials are available in this CUTROOM process. Review the account and model; provider compatibility has not been live-tested in this build."
      : "Cloudflare is unavailable. Set CUTROOM_CF_ACCOUNT_ID and CUTROOM_CF_API_TOKEN in your own launch environment, restart CUTROOM, then refresh. Do not paste keys into projects or this page.";
    controls();
  }
  function setStatus(value) {
    if (!value || !["local", "legacy", "cloud", "auto"].includes(value.engine)) return;
    const destinationChanged = selected.consent_scope !== value.consent_scope;
    selected = value;
    if (destinationChanged) consent.checked = false;
    summary();
    if (dialog.open && !saving) {
      if (destinationChanged && reviewedScope) announce("The Cloudflare destination changed. Review the account and consent again.", true);
      reviewedScope = selected.consent_scope || "";
      renderChoice();
    }
  }
  async function refresh() {
    if (saving) return;
    const ticket = ++generation;
    refreshing = true; controls();
    try {
      const value = await api("/api/transcription/engine");
      if (ticket !== generation) return;
      setStatus(value);
      select.value = selected.engine;
      reviewedScope = selected.consent_scope || "";
      consent.checked = false;
      announce("Settings refreshed. Nothing was enabled or uploaded.");
    } catch (error) {
      if (ticket === generation) { selected = {...selected, cloud_ready: false}; announce(error.message, true); }
    } finally {
      if (ticket === generation) { refreshing = false; renderChoice(); }
    }
  }
  function open() {
    pause();
    select.value = selected.engine;
    consent.checked = false;
    reviewedScope = "";
    announce(""); renderChoice();
    dialog.showModal();
    void refresh();
  }
  function close() {
    if (saving) return;
    generation += 1; refreshing = false; consent.checked = false; reviewedScope = "";
    dialog.close();
  }
  dialog.addEventListener("cancel", event => { if (saving) event.preventDefault(); });
  dialog.addEventListener("close", () => { generation += 1; refreshing = false; consent.checked = false; reviewedScope = ""; });
  select.addEventListener("change", () => { consent.checked = false; announce("Not saved. This choice takes effect only after Save."); renderChoice(); });
  consent.addEventListener("change", controls);
  byId("refreshTranscription").addEventListener("click", () => { void refresh(); });
  byId("transcriptionButton").addEventListener("click", open);
  byId("closeTranscription").addEventListener("click", close);
  byId("cancelTranscription").addEventListener("click", close);
  byId("transcriptionForm").addEventListener("submit", async event => {
    event.preventDefault();
    if (saving || refreshing) return;
    if (busy()) { announce("Wait for active processing to finish before changing transcription.", true); return; }
    if (isCloud() && (!selected.cloud_ready || !consent.checked || !reviewedScope || reviewedScope !== selected.consent_scope)) {
      announce("Refresh, review this Cloudflare destination and confirm future uploads and possible charges first.", true); return;
    }
    const payload = {engine: select.value};
    if (isCloud()) Object.assign(payload, {consent: true, consent_scope: reviewedScope});
    saving = true; controls(); announce("Saving transcription choice…");
    try {
      const value = await api("/api/transcription/engine", {method: "POST", body: JSON.stringify(payload)});
      setStatus(value);
      await changed(value);
      saving = false;
      close();
    } catch (error) { announce(error.message, true); }
    finally { saving = false; consent.checked = false; controls(); }
  });
  return {setStatus, setStoryConnection(value) { story = value || {}; summary(); }, open, refresh};
}
