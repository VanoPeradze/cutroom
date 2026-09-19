export function workflowSettings(kind) {
  if (!["short", "youtube", "manual"].includes(kind)) throw new Error("Choose a starting point.");
  return { workflow: kind === "manual" ? "manual" : "ai", goal: kind === "short" ? "short" : "youtube",
    aspect: kind === "short" ? "9:16" : "16:9", layout: "auto",
    auto_reframe: kind === "short", editorial_effects: kind !== "manual" };
}

export function initWelcome({ document, api, createProject, goHome, pause, changed, busy, models = null }) {
  const byId = id => document.getElementById(id);
  const dialog = byId("aiConnectionDialog");
  const form = byId("aiConnectionForm");
  const status = byId("connectionStatus");
  let selected = { mode: "local", model: "openai/gpt-oss-120b", has_key: false, configured: true };
  let creating = false;
  let saving = false;
  const mode = () => form.querySelector('input[name="connectionMode"]:checked').value;
  const announce = (message, error = false) => {
    status.textContent = message;
    status.dataset.error = String(error);
  };
  function showCloudFields() {
    const cloud = mode() !== "local";
    byId("cloudConnectionFields").hidden = !cloud;
    byId("localConnectionHelp").hidden = cloud;
    byId("localModelsPanel").hidden = cloud;
    byId("cloudConsent").required = cloud;
    byId("cloudAPIKey").required = cloud && !selected.has_key;
    byId("forgetCloudKey").hidden = !selected.has_key;
    byId("saveAIConnection").textContent = cloud ? "Use this cloud connection" : "Use local AI";
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
    byId("homeConnectionDetail").textContent = cloud ? "Groq handles AI. Your computer still previews and exports the video." : "Your computer handles AI. Check that the models for your quality profile are downloaded.";
    byId("homePrivacyNote").textContent = cloud
      ? `Groq cloud AI selected${value.configured ? "" : " — reconnect your API key to use AI"}. Audio and transcript text are sent only when you start AI processing. Editing and export remain on this computer.`
      : "Local AI selected. Your footage stays on this computer. Online AI is optional; editing and export still run locally.";
  }
  function openConnection() {
    pause();
    form.querySelector(`input[value="${selected.mode}"]`).checked = true;
    byId("cloudAPIKey").value = "";
    byId("cloudStoryModel").value = selected.model;
    byId("cloudConsent").checked = false;
    announce(selected.has_key ? "A key is connected for this session. Leave the key field empty to keep it." : "");
    showCloudFields();
    dialog.showModal();
  }
  function closeConnection() {
    byId("cloudAPIKey").value = "";
    dialog.close();
  }
  dialog.addEventListener("close", () => { byId("cloudAPIKey").value = ""; models?.cancelReview(); });
  form.addEventListener("change", event => { if (event.target.name === "connectionMode") { models?.cancelReview(); showCloudFields(); announce(""); } });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (saving) return;
    if (busy()) { announce("Wait for the active process to finish before changing AI connection.", true); return; }
    saving = true;
    byId("saveAIConnection").disabled = true;
    byId("forgetCloudKey").disabled = true;
    try {
      const payload = { mode: mode(), provider: "groq", model: byId("cloudStoryModel").value.trim(),
        consent: byId("cloudConsent").checked, api_key: byId("cloudAPIKey").value.trim() };
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
      byId("cloudAPIKey").value = "";
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
