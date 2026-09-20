export function workflowSettings(kind) {
  if (!["short", "youtube", "manual"].includes(kind)) throw new Error("Choose a starting point.");
  return { workflow: kind === "manual" ? "manual" : "ai", goal: kind === "short" ? "short" : "youtube",
    aspect: kind === "short" ? "9:16" : "16:9", layout: "auto",
    auto_reframe: kind === "short", editorial_effects: kind !== "manual" };
}

export function cloudProviderName(connection = {}) {
  return connection.provider === "openai-compatible" ? "Your API provider" : "Groq";
}

export function compatibleBaseURL(value) {
  let url;
  try { url = new URL(value.trim()); } catch { throw new Error("Enter your provider's HTTPS API base URL."); }
  if (url.protocol !== "https:" || !url.hostname || url.username || url.password || url.search || url.hash) {
    throw new Error("Use an HTTPS API base URL without credentials, query parameters or a fragment.");
  }
  return url.href.replace(/\/+$/, "");
}

export function initWelcome({ document, api, createProject, goHome, pause, changed, busy, models = null }) {
  const byId = id => document.getElementById(id);
  const dialog = byId("aiConnectionDialog");
  const form = byId("aiConnectionForm");
  const status = byId("connectionStatus");
  let selected = { mode: "local", provider: "groq", model: "openai/gpt-oss-120b", has_key: false, configured: true };
  let creating = false;
  let saving = false;
  let credentialsChanged = false;
  let reviewedDestination = "";
  const mode = () => form.querySelector('input[name="connectionMode"]:checked').value;
  const provider = () => mode() === "own" && byId("cloudProvider").value === "openai-compatible" ? "openai-compatible" : "groq";
  const destination = () => `${mode()}|${provider()}|${provider() === "openai-compatible" ? byId("cloudBaseURL").value.trim() : "groq"}`;
  const keepSessionKey = () => Boolean(selected.has_key && !credentialsChanged && selected.mode === mode()
    && (selected.provider || "groq") === provider()
    && (provider() !== "openai-compatible" || byId("cloudBaseURL").value.trim() === selected.base_url));
  function clearPendingCredentials(changedDestination = false) {
    byId("cloudAPIKey").value = "";
    byId("cloudConsent").checked = false;
    if (changedDestination) credentialsChanged = true;
  }
  const announce = (message, error = false) => {
    status.textContent = message;
    status.dataset.error = String(error);
  };
  function showCloudFields() {
    const cloud = mode() !== "local";
    const custom = cloud && provider() === "openai-compatible";
    let destinationName = "Groq";
    if (custom) {
      try { destinationName = compatibleBaseURL(byId("cloudBaseURL").value); }
      catch { destinationName = "your HTTPS API endpoint"; }
    }
    byId("cloudConnectionFields").hidden = !cloud;
    byId("localConnectionHelp").hidden = cloud;
    byId("localModelsPanel").hidden = cloud;
    byId("cloudProviderField").hidden = mode() !== "own";
    byId("cloudProvider").disabled = mode() !== "own";
    byId("compatibleConnectionFields").hidden = !custom;
    for (const id of ["cloudBaseURL", "cloudTranscriptModel"]) {
      byId(id).required = custom;
      byId(id).disabled = !custom;
    }
    byId("cloudStoryModel").required = cloud;
    byId("cloudStoryModel").disabled = !cloud;
    if (custom) byId("cloudModelSettings").open = true;
    byId("cloudConsent").required = cloud;
    byId("cloudConsent").disabled = !cloud;
    byId("cloudAPIKey").required = cloud && !keepSessionKey();
    byId("cloudAPIKey").disabled = !cloud;
    byId("cloudAPIKey").placeholder = custom ? "Paste the key for this API endpoint" : "Paste your Groq API key";
    byId("cloudProviderLabel").textContent = custom ? "OpenAI-compatible API" : "Groq";
    byId("cloudProviderSummary").textContent = custom ? "Requires compatible chat and timed transcription APIs" : "Cloud transcription + Story AI";
    byId("groqKeyLink").hidden = custom;
    byId("cloudDestinationName").textContent = destinationName;
    byId("cloudProviderHelp").textContent = custom
      ? "Your endpoint must support chat/completions with JSON object output and audio/transcriptions with verbose_json and word timestamps. A chatbot key alone is not enough. Enter both model IDs exactly as your provider documents them. Provider charges and limits apply."
      : `Transcription uses Whisper Large V3 with word timings. ${mode() === "free" ? "Use your own Groq Free account; quotas apply. Selecting Free tier here does not change a paid account or prevent its charges." : "Check model availability, billing and limits in your Groq account."} CUTROOM provides no shared API key or credit. CUTROOM_GROQ_API_KEY is an optional user-managed environment setting.`;
    byId("cloudConsentCopy").textContent = `I agree to send the selected audio, transcript and editing instructions to ${destinationName} when I start AI processing. I have checked this destination, my account's plan and its limits.`;
    byId("forgetCloudKey").hidden = !selected.has_key;
    byId("saveAIConnection").textContent = cloud ? "Use this cloud connection" : "Use local AI";
    reviewedDestination = destination();
    if (!cloud) void models?.refresh();
  }
  function setConnection(value) {
    if (!value) return;
    selected = value;
    models?.setConnection(value);
    const cloud = value.mode !== "local";
    byId("processingBadge").textContent = cloud ? "Cloud AI" : "Local AI";
    byId("aiConnectionButton").textContent = cloud && !value.configured ? "Connect AI" : "AI connection";
    byId("homeConnectionStatus").textContent = cloud ? value.configured ? "Cloud AI selected" : "Cloud key needed" : "Local AI selected";
    const providerName = cloudProviderName(value);
    byId("homeConnectionDetail").textContent = cloud ? `${providerName} handles AI. Your computer still previews and exports the video.` : "Your computer handles AI. Check that the models for your quality profile are downloaded.";
    byId("homePrivacyNote").textContent = cloud
      ? `${providerName} selected for cloud AI${value.configured ? "" : " — reconnect your API key to use AI"}. Audio and transcript text are sent only when you start AI processing. Editing and export remain on this computer.`
      : "Local AI selected. Your footage stays on this computer. Online AI is optional; editing and export still run locally.";
  }
  function openConnection() {
    pause();
    form.querySelector(`input[value="${selected.mode}"]`).checked = true;
    credentialsChanged = false;
    clearPendingCredentials();
    byId("cloudProvider").value = selected.provider || "groq";
    byId("cloudBaseURL").value = selected.provider === "openai-compatible" ? selected.base_url || "" : "";
    byId("cloudTranscriptModel").value = selected.provider === "openai-compatible" ? selected.transcript_model || "" : "";
    byId("cloudStoryModel").value = selected.model;
    announce(selected.has_key ? "A key is available for this saved connection. Leave the key field empty to keep it. Changing mode, provider or endpoint requires a fresh key and consent." : "");
    showCloudFields();
    dialog.showModal();
  }
  function closeConnection() {
    clearPendingCredentials();
    dialog.close();
  }
  dialog.addEventListener("close", () => { clearPendingCredentials(); models?.cancelReview(); });
  form.addEventListener("change", event => {
    if (event.target.name !== "connectionMode" && event.target.id !== "cloudProvider") return;
    const previousProvider = reviewedDestination.split("|")[1];
    if (mode() === "free") byId("cloudProvider").value = "groq";
    clearPendingCredentials(true);
    if (provider() !== previousProvider) {
      byId("cloudStoryModel").value = provider() === "groq" ? "openai/gpt-oss-120b" : "";
      byId("cloudTranscriptModel").value = "";
    }
    models?.cancelReview(); showCloudFields();
    announce(mode() === "local" ? "" : "Enter the key for this connection and review the destination before consenting.");
  });
  byId("cloudBaseURL").addEventListener("input", () => {
    clearPendingCredentials(true); showCloudFields();
    announce("Endpoint changed. Enter its API key and review the destination before consenting.");
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (saving) return;
    if (busy()) { announce("Wait for the active process to finish before changing AI connection.", true); return; }
    saving = true;
    byId("saveAIConnection").disabled = true;
    byId("forgetCloudKey").disabled = true;
    try {
      if (destination() !== reviewedDestination) {
        clearPendingCredentials(true); showCloudFields();
        throw new Error("Connection destination changed. Enter its API key and confirm consent again.");
      }
      const payload = { mode: mode() };
      if (mode() !== "local") {
        Object.assign(payload, {provider: provider(), model: byId("cloudStoryModel").value.trim(),
          consent: byId("cloudConsent").checked, api_key: byId("cloudAPIKey").value.trim()});
        if (provider() === "openai-compatible") {
          payload.base_url = compatibleBaseURL(byId("cloudBaseURL").value);
          payload.transcript_model = byId("cloudTranscriptModel").value.trim();
          if (!payload.transcript_model) throw new Error("Enter a transcription model that supports verbose_json and word timestamps.");
          payload.endpoint_consent = payload.base_url;
        }
        if (!payload.model) throw new Error("Enter the Story model ID for this provider.");
        if (!payload.consent) throw new Error("Confirm the content destination and your provider's billing plan first.");
        if (!payload.api_key && !keepSessionKey()) throw new Error("Enter a fresh API key for this connection.");
      }
      const result = await api("/api/ai/connection", { method: "POST", body: JSON.stringify(payload) });
      byId("cloudAPIKey").value = "";
      setConnection(result.connection);
      await changed(result.connection);
      closeConnection();
    } catch (error) { announce(error.message, true); }
    finally { saving = false; byId("saveAIConnection").disabled = false; byId("forgetCloudKey").disabled = false; }
  });
  byId("forgetCloudKey").addEventListener("click", async () => {
    if (saving) return;
    if (busy()) { announce("Wait for active processing to finish before disconnecting.", true); return; }
    saving = true;
    try {
      const result = await api("/api/ai/connection", { method: "POST", body: JSON.stringify({ mode: "local", clear_key: true }) });
      setConnection(result.connection);
      await changed(result.connection);
      form.querySelector('input[value="local"]').checked = true;
      clearPendingCredentials(true);
      showCloudFields();
      announce(result.connection.has_key ? "Session key cleared. A user-managed environment key is still available." : "Session key removed. Local AI selected.");
    } catch (error) { announce(error.message, true); }
    finally { saving = false; }
  });
  byId("closeAIConnection").addEventListener("click", closeConnection);
  ["aiConnectionButton", "homeConnectionButton"].forEach(id => byId(id).addEventListener("click", openConnection));
  byId("homeModelsButton").addEventListener("click", () => {
    openConnection();
    if (selected.mode !== "local") {
      form.querySelector('input[value="local"]').checked = true;
      showCloudFields();
      announce("Viewing local setup. Downloading does not switch your AI connection; save Local AI to switch.");
    }
  });
  ["welcomeHelpButton", "welcomeTourButton"].forEach(id => byId(id).addEventListener("click", () => {
    pause(); byId("welcomeGuideDialog").showModal();
  }));
  const guideSearch = byId("guideSearch");
  guideSearch.addEventListener("input", () => {
    const query = guideSearch.value.trim().toLowerCase();
    let visible = 0;
    for (const topic of document.querySelectorAll("[data-help-topic]")) {
      const matches = !query || topic.textContent.toLowerCase().includes(query);
      topic.hidden = !matches;
      if (matches) { visible += 1; if (query) topic.open = true; }
    }
    byId("guideEmpty").hidden = visible > 0;
  });
  function chooseService() {
    const target = byId("welcomeServices");
    target.scrollIntoView({ block: "start", behavior: "auto" });
    target.focus({ preventScroll: true });
  }
  byId("changeWorkflowButton").addEventListener("click", async () => { await goHome(); chooseService(); });
  for (const card of document.querySelectorAll("[data-start-workflow]")) {
    card.addEventListener("click", async () => {
      if (creating || busy()) return;
      creating = true;
      const cards = [...document.querySelectorAll("[data-start-workflow]")];
      cards.forEach(item => { item.disabled = true; });
      try {
        await createProject({ workflow: card.dataset.startWorkflow });
        byId("sourceSlotA").focus({ preventScroll: true });
      } finally { creating = false; cards.forEach(item => { item.disabled = false; }); }
    });
  }
  function updateProject(project) {
    const manual = project?.settings?.workflow === "manual";
    const name = manual ? "Manual edit" : project?.settings?.goal === "youtube" ? "YouTube video · 16:9 starting format" : "AI-assisted edit";
    byId("setupIntentCopy").textContent = `${name}. ${manual ? "Add your recordings, then open the editor. No AI account is needed." : "Add your recordings, check the language and choose a style."}`;
    byId("setupPanel").dataset.workflow = manual ? "manual" : "ai";
    byId("setupWorkflowSteps").hidden = manual;
    byId("setupEyebrow").textContent = manual ? "Manual editor" : "AI Director";
    byId("setupInstructions").textContent = manual
      ? "Add your recording and choose the output format. With two recordings, assign the screen, camera and audio before opening the editor."
      : "Add one or two sources. With two, choose the screen, camera and audio before Director starts.";
    const title = byId("generateButton").querySelector('[data-i18n="makeEdit"]');
    if (title) title.textContent = manual ? "Open manual editor" : "Build my first cut";
    const note = byId("generateButton").querySelector('[data-i18n="oneDraft"]');
    if (manual && note) note.textContent = "Full recording · No AI processing";
    byId("setupRuntimeDock").hidden = manual;
  }
  return { setConnection, openConnection, chooseService, updateProject };
}
