import { applyTranslations, dictionaries } from "./i18n.js?v=1.1-beta-1";
import { TimelineView, formatTime, editableClips, timelineDuration, sequenceBlocks, sequenceGaps, rippleMoveStart } from "./timeline.js?v=1.1-beta-3";
import { MediaStudio } from "./media-studio.js?v=1.1-beta-3";
import { SourceReview } from "./source-review.js?v=1.1-beta-3";
import { initWorkspace } from "./workspace.js?v=1.1-beta-1";
import { KEYBOARD_PROFILES, resolveEditorShortcut, isEditorTransportSpace, shortcutRows } from "./keyboard.js?v=1.1-beta-2";
import { AudioThresholdView } from "./audio-meter.js?v=1.1-beta-1";
import { initWelcome, workflowSettings, cloudProviderName } from "./welcome.js?v=1.1-beta-1";
import { initLocalModels } from "./local-models.js?v=1.1-beta-1";
import { trackClips, trackAt, hasSourceTracks, SourceTimelineClock } from "./source-tracks.js?v=1.1-beta-1";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  project: null,
  projects: [],
  locale: "en",
  dictionary: null,
  activeJob: null,
  activeUploads: new Map(),
  backgroundJobs: new Set(),
  modelInstallJob: null,
  modelInstallPending: false,
  aiPreparePromise: null,
  runtimeRefreshTimer: null,
  runtimeRefreshAttempts: 0,
  runtimeGeneration: 0,
  jobTimer: null,
  saveQueues: new Map(),
  projectViewToken: 0,
  jobStartLocks: new Set(),
  activeJobMeta: null,
  activeJobSnapshot: null,
  cancelRequestedJobs: new Set(),
  cancelBeforeStart: false,
  recoveringJobs: new Set(),
  reportedInterruptedJobs: new Set(),
  reportedFailedJobs: new Set(),
  retriedSourcePreparations: new Set(),
  draftDirtyReasons: new Set(),
  selectedEditStyle: "smart",
  manualSelection: null,
  editTarget: "edit",
  keyboardProfile: "cutroom",
  markIn: null,
  trimClip: null,
  transcriptBuffers: new Map(),
  transcriptActive: null,
  transcriptAnchor: null,
  transcriptSaving: false,
  manualEditBusy: false,
  manualEditPromise: null,
  sourceMixerLayout: "auto",
  sourceMixerLayoutTouched: false,
  sourceMixerLayoutRequest: null,
  sourceMixerPreviewLayout: null,
  sourceMixerCommitScope: null,
  sourceMixerSaveTail: Promise.resolve(),
  sourceMixerSavePending: 0,
  sourceMixerSaveSequence: 0,
  sourceMixerDesired: null,
  sourceSyncSaveTimer: null,
  sourceSyncPending: null,
  embeddedEditor: { projectId: null, generation: null, candidateKey: null, dirty: false, dragging: false },
  preview: { playing: false, seeking: false, currentCamera: "A", playRequest: 0, mode: "edit" },
  timeline: null,
  audioMeter: null,
  studio: { open: false, scrollY: 0 },
  system: null,
  welcome: null,
  projectsLoaded: false,
};

const elements = {};

// The server supplies a read-only edit-clock projection. Opening the editor
// never saves a conversion; the first sequence action does so atomically.
function editorProject(project = state.project) {
  const sequence = project?.editor_sequence;
  if (!sequence || project.__sequenceView) return project;
  return { ...project, __sequenceView: true,
    manual: { ...project.manual, sequence: sequence.sequence, source_tracks: sequence.source_tracks },
    draft: { ...project.draft, keep_ranges: sequence.duration > 0 ? [{start:0,end:sequence.duration}] : [], cuts: [],
      camera_plan: sequence.sequence.camera_plan, output_duration: sequence.duration, edit_points: [] } };
}

function playbackProject() {
  if (!state.project?.editor_sequence || !previewUsesSourceTime()) return editorProject();
  const manual = { ...state.project.manual };
  delete manual.sequence; delete manual.source_tracks;
  return { ...state.project, manual };
}

function editorDuration() { return timelineDuration(editorProject()); }

function sourceToEditorTime(time) {
  if (!state.project?.editor_sequence) return time;
  const candidates = trackClips(editorProject(), "A").filter(clip => time >= clip.source_start && time < clip.source_start + clip.end - clip.start);
  const current = candidates.find(clip => state.timeline?.playhead >= clip.start && state.timeline?.playhead < clip.end) || candidates[0];
  return current ? current.start + time - current.source_start : null;
}

function cacheElements() {
  [
    "welcomeView", "workspaceView", "projectHead", "projectName", "saveState", "recentProjects", "recentList", "recentCount",
    "projectsButton", "projectsDialog", "dialogProjects", "dialogNewProject", "newProjectButton", "homeButton",
    "advancedButton", "advancedPanel", "closeAdvanced", "studioPreviewDock", "studioDirectorDock", "studioRenderButton", "studioDraftStatus", "studioPanelFraming", "renderButton", "resultRenderButton", "setupPanel", "setupSourceMixerDock", "analysisPanel", "resultPanel", "resultGrid", "previewColumn", "verdictColumn",
    "sourceSlotA", "sourceSlotB", "sourceInputA", "sourceInputB", "cancelUploadA", "cancelUploadB", "audioCalibration", "audioMeterCanvas", "recommendedThreshold", "useRecommendedThreshold", "silenceThreshold", "silenceThresholdOut", "preSilenceMin", "preSilenceMinOut", "preSilenceKeep", "preSilenceKeepOut", "audioCutEstimate", "audioProfileSummary", "editStyleChoices", "editStyleNote", "goalChoices", "goalExplainer", "goalExplainerTitle", "goalExplainerText", "durationGroup", "targetDuration", "durationOutput", "paceChoices", "paceNote",
    "directorInstruction", "readiness", "generateButton", "jobMessage", "jobProgress", "cancelJobButton", "analysisError", "analysisErrorTitle", "analysisErrorMessage", "retryDirectorButton", "backFromErrorButton", "draftTitle", "draftSummary", "draftEngineBadge",
    "reelCandidates", "reelCandidatesTitle", "reelCandidateList", "draftWarning", "draftWarningText", "reviewSpeechSettings",
    "beforeDuration", "afterDuration", "decisionCount", "decisionList", "previewStage", "previewA", "previewB", "previewPaneA", "previewPaneB", "previewPlay", "playButton",
    "previewTime", "previewSeek", "previewMode", "previewModeHint", "previewCaption", "restartPreview", "backToBriefButton", "timelineCanvas", "timelineScroll", "timelineFit", "timelineZoomOut",
    "timelineZoomIn", "timelineZoomLabel", "timelineZoomSelection", "timelineSnap", "timelineSelectionHint", "timelineCutStatus", "timelineCutHint", "cancelTimelineCut", "manualSelectionLabel", "manualClear", "manualRestore", "manualDelete", "manualSplit", "manualUndo", "manualRedo",
    "cropPreview", "cropVideo", "layoutSelect", "cropSourceSelect", "cropX", "cropY", "cropZoom", "resetCrop", "embeddedCropHelp", "cropScopeStatus",
    "sourceMixer", "sourceMixerTitle", "sourceMixerHelp", "sourceMixerStatus", "sourceMixerEmpty", "sourceMixerBody",
    "embeddedCameraEditor", "embeddedCameraTitle", "embeddedCameraHelp", "embeddedCameraState", "embeddedCameraCanvas", "embeddedCameraVideo", "embeddedCameraRect",
    "embeddedCameraSeek", "embeddedCameraSeekOut",
    "embeddedCameraPresets", "embeddedCameraX", "embeddedCameraY", "embeddedCameraW", "embeddedCameraH", "embeddedCameraXOut", "embeddedCameraYOut", "embeddedCameraWOut", "embeddedCameraHOut",
    "embeddedContentX", "embeddedContentY", "embeddedContentXOut", "embeddedContentYOut", "saveEmbeddedCamera", "disableEmbeddedCamera",
    "screenSourceSelect", "cameraSourceSelect", "primaryRoleSelect", "audioSourceSelect", "firstSlotSelect", "screenSourceName", "cameraSourceName", "firstSlotName", "swapSourceRoles",
    "sourceCompositionPreview", "sourceCompositionCanvas", "sourceCompositionA", "sourceCompositionB", "sourceCompositionRoleA", "sourceCompositionRoleB", "sourceCompositionNameA", "sourceCompositionNameB", "sourceCompositionMode",
    "sourceSyncOffset", "sourceSyncStatus", "resetSourceSync", "sourceLayoutChoices", "applyLayoutSelection", "applyLayoutAll", "resetSourceLayout", "sourceMixerRange", "creatorFramePreset", "stackFitSelect",
    "sceneLayoutEditor", "sceneLayoutList", "sceneLayoutSummary",
    "sourceSetupDisclosure", "sourceIdentityCards", "sourceBEarlier", "sourceBLater", "sourceBCoverage", "swapSourceOrder",
    "layoutScopeBadge", "layoutScopeHelp", "layoutCurrentScene", "layoutWholeEdit", "manualRange", "manualLayout",
    "layoutRangeForm", "layoutRangeStart", "layoutRangeEnd", "layoutRangeSubmit", "layoutRangeStatus",
    "timelineRangeForm", "timelineRangeStart", "timelineRangeEnd", "timelineRangeSubmit", "timelineRangeStatus",
    "cameraDetection", "useEmbeddedCamera", "transcriptSearch", "transcriptList", "transcriptLanguage", "aspectSelect", "quickAspectChoices", "resolutionSelect",
    "transcriptFilter", "transcriptResults", "transcriptRemove", "transcriptRestore", "transcriptEditForm", "transcriptEditText", "transcriptEditTime", "transcriptEditStatus", "transcriptSave", "transcriptDiscard", "transcriptPrevious", "transcriptNext", "transcriptSaveAll",
    "keyboardProfile", "keyboardHelpProfile", "keyboardHelp", "keyboardDialog", "keyboardDescription", "keyboardLimitations", "keyboardShortcutList", "clipTrimForm", "clipTrimIn", "clipTrimOut", "clipTrimTitle", "clipTrimApply", "clipTrimStatus", "timelineTarget", "timelineTargetField", "trackReset", "trackHelp", "clipSourceIn", "clipSourceField", "clipMove",
    "qualitySelect", "fpsSelect", "fpsHelp", "exportFpsSelect", "exportFpsHelp", "exportFrameRateField", "autoReframe", "effectsToggle", "captionsToggle", "burnCaptionsToggle", "studioBurnCaptionsToggle", "captionControlStatus", "captionLanguageStatus",
    "captionStyleSelect", "captionPositionSelect", "captionScale", "captionScaleOut", "captionWordsPerLine", "captionWordsPerLineOut", "spokenLanguageSelect", "performanceModeSelect", "audioPresetChoices", "audioPresetNote",
    "silenceAction", "silenceMin", "silenceMinOut", "silenceKeep", "silenceKeepOut", "maxRemoveRatio", "maxRemoveOut",
    "quietAction", "quietGain", "quietGainOut", "loudAction", "loudGain", "loudGainOut", "normalizeAudio",
    "modelStatus", "modelButton", "retryAIButton", "setupRuntimeDock", "studioRuntimeDock", "draftRebuildNotice", "draftRebuildTitle", "draftRebuildText", "rebuildDraftButton", "exportDialog", "closeExportDialog", "exportSummary",
    "activeJobBar", "activeJobLabel", "activeJobDetail", "globalCancelJobButton", "exportTitle", "exportDescription", "exportProgress", "exportActions", "cancelExport", "cancelExportJobButton", "confirmExport", "downloadExport", "toastRegion", "cameraBadge",
    "sourceInsertForm", "sourceInsertTitle", "sourceInsertIn", "sourceInsertOut", "sourceInsertAt", "sourceInsertStatus", "sourceInsertCancel", "sourceInsertSlot", "clipDuplicate", "editorMoreButton", "editorMoreTools", "emptyTimeline", "emptyTimelineAdd",
  ].forEach((id) => { elements[id] = document.getElementById(id); });
}

function t(key) {
  return state.dictionary?.[key] ?? dictionaries.en[key] ?? key;
}

function uiCopy(hebrew, english) {
  return english;
}

const CAPTION_DEFAULTS = Object.freeze({ style: "bold", position: "auto", scale: 100, words: 9 });
const EMBEDDED_CAMERA_DETECTOR_VERSION = "face-layout-v3";
const LANGUAGE_NAMES = Object.freeze({
  he: "Hebrew", en: "English", ar: "Arabic", es: "Spanish", fr: "French", ru: "Russian",
  yi: "Yiddish", de: "German", it: "Italian", pt: "Portuguese", ja: "Japanese", ko: "Korean", zh: "Chinese",
});

function clampInteger(value, minimum, maximum, fallback) {
  const number = Number(value);
  return Number.isInteger(number) ? Math.max(minimum, Math.min(maximum, number)) : fallback;
}

function languageName(code) {
  const normalized = String(code || "").trim().toLowerCase();
  if (!normalized) return "Unknown";
  if (LANGUAGE_NAMES[normalized]) return LANGUAGE_NAMES[normalized];
  try { return new Intl.DisplayNames(["en"], { type: "language" }).of(normalized) || normalized.toUpperCase(); }
  catch { return normalized.toUpperCase(); }
}

class ApiError extends Error {
  constructor(message, status, code, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = Number(status || 0);
    this.code = code || null;
    this.payload = payload;
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" ? payload.message || payload.error : payload;
    const code = typeof payload === "object" ? payload.error : null;
    throw new ApiError(message || `HTTP ${response.status}`, response.status, code, payload);
  }
  return payload;
}

function initializeMediaStudio() {
  if (typeof MediaStudio === "undefined") return;
  const panel = document.getElementById("studioPanelMedia");
  const tab = document.createElement("button");
  tab.id = "studioTabMedia"; tab.type = "button"; tab.dataset.tab = "media";
  tab.setAttribute("role", "tab"); tab.setAttribute("aria-selected", "false"); tab.setAttribute("aria-controls", "studioPanelMedia"); tab.tabIndex = -1;
  tab.innerHTML = '<span aria-hidden="true">♫</span><span>Media</span><small>Clips & audio</small>';
  elements.advancedPanel.querySelector(".advanced-tabs").append(tab);
  // bindEvents already ran before this dynamically created tab.
  tab.addEventListener("click", () => selectAdvancedTab("media"));
  tab.addEventListener("keydown", handleStudioTabKeydown);
  state.mediaStudio = new MediaStudio(panel, elements.previewStage, {
    project: () => state.project, api, edit: applyManualEdit, pause: pauseAllMedia,
    time: previewTimelineTime, duration: editorDuration, flushSettings: flushProjectSaves,
    busy: () => Boolean(state.activeJob || state.activeUploads.size || state.jobStartLocks.size
      || state.sourceSyncPending || (state.manualEditBusy && !state.mediaStudio?.saving)),
    preview: () => { updateMediaPreview(); state.timeline?.scheduleDraw(); },
    busyChanged: () => { renderReadiness(); renderManualControls(); },
    acceptUpload: async (result, projectId) => {
      if (result.project && state.project?.id === projectId) { state.project = reconcileProjectSnapshot(result.project); rememberProjectRevision(state.project); state.mediaStudio.render(); }
      try {
        if (result.job) await pollJob(result.job.id, {projectId, silent:true});
      } finally {
        // Failed/cancelled preparations must also reveal their Retry action.
        const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
        if (state.project?.id === projectId) { state.project = reconcileProjectSnapshot(latest.project); rememberProjectRevision(state.project); renderDraft(); }
      }
    },
  });
  const speed = document.createElement("div"); speed.className = "picture-speed"; speed.dataset.editorShortcuts = "off";
  speed.innerHTML = '<label>Picture speed <select aria-label="Picture speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select><span></span></label><p>Picture only: keeps clip length and speech timing. May lose lip sync or hold the last source frame. Select A or B to choose which picture changes.</p>';
  elements.clipTrimForm.after(speed); state.pictureSpeed = speed;
  speed.querySelector("select").addEventListener("change", async event => {
    const clip = state.pictureSpeedClip; if (!clip || foregroundBusy()) return;
    pauseAllMedia();
    await runUiAction(() => applyManualEdit("sequence_speed", {slot:clip.slot,clip_id:clip.id,speed:Number(event.target.value)}), "Changing picture speed");
  });
}

function updateMediaPreview() {
  if (!state.mediaStudio || !state.project?.draft) return;
  const project = playbackProject(), time = previewPlaybackTime(), sourceMode = previewUsesSourceTime();
  const mixer = sourceMixerSettings(), slot = mixer.audioSlot || "A", source = project.sources?.[slot];
  const point = previewUsesIndependentTracks() ? trackAt(project,slot,time,mixer.syncOffset)
    : {sourceTime:time-(slot === "B" ? mixer.syncOffset : 0)};
  state.mediaStudio.sync(sourceMode ? time : sourceToOutputTime(time),state.preview.playing,
    {sourceMode,point,url:source ? sourceMediaUrl(source) : null,hasAudio:source?.has_audio});
  if (!sourceMode) { elements.previewA.muted = true; elements.previewB.muted = true; }
}

function renderPictureSpeed() {
  if (!state.pictureSpeed) return;
  const slot = activeEditTarget() === "B" ? "B" : "A";
  const start = state.manualSelection?.start;
  const clip = start != null ? trackAt(editorProject(), slot, start + .0001)?.clip : null;
  state.pictureSpeed.hidden = !clip;
  state.pictureSpeedClip = clip ? {slot,id:clip.id} : null;
  if (clip) { state.pictureSpeed.querySelector("select").value = String(clip.video_speed || 1); state.pictureSpeed.querySelector("span").textContent = `Source ${slot}`; }
}

function lastProjectStorageKey() {
  const instance = String(state.system?.instance_id || "").trim();
  return instance ? `cutroom-last-project:${instance}` : "cutroom-last-project";
}

function clearRememberedProject(projectId = null) {
  const keys = [lastProjectStorageKey(), "cutroom-last-project"];
  for (const key of new Set(keys)) {
    if (!projectId || localStorage.getItem(key) === projectId) localStorage.removeItem(key);
  }
}

function renderAllLocalizedContent() {
  renderReadiness();
  renderActiveJobBar();
  renderUploadLimits();
  renderEditStyleChoices();
  if (elements.audioPresetChoices) updateAudioPresetNote($("button.active", elements.audioPresetChoices)?.dataset.value || "clean");
  if (elements.goalChoices) applyGoalMode($("button.active", elements.goalChoices)?.dataset.value || "short", false);
  if (state.project?.draft) {
    renderDecisions();
    renderTranscript();
  }
  renderModelStatus();
  renderDraftRebuildNotice();
  renderManualControls();
  renderSourceMixer();
}

function toast(message, type = "error", timeout = 4400) {
  const node = document.createElement("div");
  node.className = `toast ${type}`;
  node.textContent = message;
  elements.toastRegion.append(node);
  window.setTimeout(() => node.remove(), timeout);
}

function runUiAction(action, context = "") {
  Promise.resolve()
    .then(action)
    .catch((error) => {
      console.error("CUTROOM action failed", error);
      const prefix = context ? `${context}: ` : "";
      toast(`${prefix}${error?.message || uiCopy("הפעולה נכשלה", "The action failed")}`);
    });
}

function formatBytes(bytes) {
  const value = Math.max(0, Number(bytes) || 0);
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(value >= 10 * 1024 ** 3 ? 0 : 1)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(0)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

function maxUploadBytes() {
  return Number(state.system?.limits?.max_upload_bytes) || 40 * 1024 ** 3;
}

function uploadStateKey(projectId, slot) {
  return `${projectId}:${String(slot || "").toUpperCase()}`;
}

function activeUploadForSlot(slot, projectId = state.project?.id) {
  if (!projectId) return null;
  return state.activeUploads.get(uploadStateKey(projectId, slot)) || null;
}

function activeUploadsForProject(projectId = state.project?.id) {
  if (!projectId) return [];
  return [...state.activeUploads.values()].filter((upload) => upload.projectId === projectId);
}

function sourceMediaUrl(source) {
  const raw = String(source?.url || "");
  if (!raw) return "";
  const generation = String(source?.generation || "").trim();
  if (!generation) return raw;
  const separator = raw.includes("?") ? "&" : "?";
  return `${raw}${separator}generation=${encodeURIComponent(generation)}`;
}

function renderUploadLimits() {
  const label = t("uploadLimit").replace("{size}", formatBytes(maxUploadBytes()));
  $$('[data-upload-limit]').forEach((node) => { node.textContent = label; });
}

function validateUploadFile(file) {
  const limit = maxUploadBytes();
  if (Number(file?.size || 0) > limit) {
    return t("fileTooLarge")
      .replace("{file}", formatBytes(file.size))
      .replace("{limit}", formatBytes(limit));
  }
  const free = Number(state.system?.limits?.disk_free_bytes || 0);
  if (free && Number(file?.size || 0) + 1024 ** 3 > free) {
    return t("notEnoughDisk")
      .replace("{file}", formatBytes(file.size))
      .replace("{free}", formatBytes(free));
  }
  return null;
}

function setStep(step) {
  $$(".director-steps li").forEach((item) => {
    const number = Number(item.dataset.step);
    item.classList.toggle("active", number === step);
    item.classList.toggle("complete", number < step);
  });
}

async function boot() {
  const initialViewToken = state.projectViewToken;
  cacheElements();
  state.dictionary = applyTranslations("en");
  bindEvents();
  const localModels = initLocalModels({ document, api, busy: foregroundBusy,
    changed: async () => { state.runtimeGeneration += 1; await loadSystem(); },
  });
  state.welcome = initWelcome({ document, api,
    models: localModels,
    createProject: (options) => runUiAction(() => createProject(options)), goHome,
    pause: pauseAllMedia, busy: foregroundBusy,
    changed: async (connection) => {
      state.system = { ...(state.system || {}), ai_connection: connection };
      state.runtimeGeneration += 1;
      await loadSystem();
    },
  });
  initWorkspace({ document, window, onResize: () => state.timeline?.scheduleDraw(), openShortcuts: () => { renderKeyboardHelp(); elements.keyboardDialog.showModal(); } });
  initializeMediaStudio();
  state.timeline = new TimelineView(elements.timelineCanvas, elements.timelineScroll,
    (time) => { pauseAllMedia(); seekSourcePreview(time); }, setManualSelection, handleTimelineEdit,
    { onToolStateChange: renderTimelineToolStatus, canEdit: () => !foregroundBusy() && !state.transcriptSaving,
      onLayoutSelect: openTimelineLayout, getTrackClips: trackClips,
      onTargetChange: (target) => setEditTarget(target, true),
      onMediaSelect: id => { pauseAllMedia(); state.mediaStudio?.select(id); selectAdvancedTab("media"); },
      onMediaEdit: (id, patch) => { state.mediaStudio?.queueClip(id,patch); return state.mediaStudio?.flush(); },
      onMediaPreview: (id, patch) => state.mediaStudio?.previewClip(id,patch),
      onMediaAction: (action, detail) => runUiAction(() => applyManualEdit(action,detail), "Editing media") });
  initializeKeyboardProfile();
  state.audioMeter = new AudioThresholdView(elements.audioMeterCanvas);
  elements.audioMeterCanvas.addEventListener("cutroom-audio-seek", (event) => {
    const time = Number(event.detail?.time);
    if (Number.isFinite(time)) seekPreview(time);
  });
  await Promise.allSettled([loadProjects(), loadSystem()]);
  // A slow hardware check must not send someone back home after they have
  // already chosen a workflow or opened a project during startup.
  if (state.projectViewToken !== initialViewToken) return;

  // Older CUTROOM builds stored one global project id for every folder because all
  // releases share 127.0.0.1:8765. Migrate it only when that project actually exists
  // in this installation; otherwise discard it without making a doomed API request.
  const storageKey = lastProjectStorageKey();
  let lastProject = localStorage.getItem(storageKey);
  const legacyProject = localStorage.getItem("cutroom-last-project");
  if (!lastProject && legacyProject && state.projectsLoaded) {
    if (state.projects.some((project) => project.id === legacyProject)) {
      lastProject = legacyProject;
      localStorage.setItem(storageKey, legacyProject);
    }
    localStorage.removeItem("cutroom-last-project");
  }

  if (lastProject) {
    if (state.projectsLoaded && !state.projects.some((project) => project.id === lastProject)) {
      clearRememberedProject(lastProject);
    } else {
      // The welcome page must not hide a render/Director job after a refresh.
      try {
        const recovery = await api(`/api/projects/${encodeURIComponent(lastProject)}/jobs/active`);
        if (state.projectViewToken !== initialViewToken) return;
        if (recovery.jobs?.some(job => ["queued", "running", "cancelling"].includes(job.status))) {
          await openProject(lastProject);
          return;
        }
      } catch (error) { console.warn("Could not check active project work", error); }
    }
  }
  if (state.projectViewToken === initialViewToken) showWelcome();
}

function bindEvents() {
  elements.newProjectButton.addEventListener("click", () => state.welcome?.chooseService());
  elements.dialogNewProject.addEventListener("click", () => runUiAction(async () => { elements.projectsDialog.close(); await goHome(); state.welcome?.chooseService(); }));
  elements.homeButton.addEventListener("click", () => runUiAction(goHome));
  elements.projectsButton.addEventListener("click", openProjectsDialog);
  elements.projectName.addEventListener("input", () => {
    schedulePatch({ name: elements.projectName.value });
  });
  elements.directorInstruction.addEventListener("input", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "brief" });
  });

  for (const slot of ["A", "B"]) {
    const slotElement = elements[`sourceSlot${slot}`];
    const input = elements[`sourceInput${slot}`];
    slotElement.addEventListener("click", (event) => {
      if (event.target.closest(".remove-source")) return;
      if (!state.project?.sources?.[slot]) input.click();
    });
    slotElement.addEventListener("keydown", (event) => {
      if (state.project?.sources?.[slot] || !["Enter", " "].includes(event.key)) return;
      event.preventDefault();
      input.click();
    });
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (file) runUiAction(() => uploadSource(slot, file), t("uploadFailed"));
    });
    elements[`cancelUpload${slot}`].addEventListener("click", (event) => {
      event.stopPropagation();
      cancelUpload(slot);
    });
    slotElement.addEventListener("dragover", (event) => { event.preventDefault(); slotElement.classList.add("dragover"); });
    slotElement.addEventListener("dragleave", () => slotElement.classList.remove("dragover"));
    slotElement.addEventListener("drop", (event) => {
      event.preventDefault(); slotElement.classList.remove("dragover");
      const file = event.dataTransfer.files?.[0];
      if (file) runUiAction(() => uploadSource(slot, file), t("uploadFailed"));
    });
    $(".remove-source", slotElement).addEventListener("click", (event) => {
      event.stopPropagation();
      runUiAction(() => removeSource(slot));
    });
  }

  elements.goalChoices.addEventListener("click", (event) => {
    const button = event.target.closest(".choice");
    if (!button) return;
    setActiveChoice(elements.goalChoices, button);
    applyGoalMode(button.dataset.value, true);
    scheduleSettingsPatch({ requiresRebuild: true, reason: "goal" });
  });
  elements.editStyleChoices.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-value]");
    if (!button || button.dataset.value === state.selectedEditStyle) return;
    chooseEditStyle(button.dataset.value);
  });
  elements.editStyleChoices.addEventListener("keydown", handleEditStyleKeydown);
  elements.paceChoices.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    setActiveChoice(elements.paceChoices, button);
    updatePaceNote(button.dataset.value);
    scheduleSettingsPatch({ requiresRebuild: true, reason: "pace" });
  });
  elements.audioPresetChoices.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    setActiveChoice(elements.audioPresetChoices, button);
    applyAudioPreset(button.dataset.value);
    scheduleSettingsPatch({ requiresRebuild: true, reason: "audio" });
  });
  elements.spokenLanguageSelect.addEventListener("change", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "language" });
    renderLanguageDetectionStatus();
  });
  elements.performanceModeSelect.addEventListener("change", () => scheduleSettingsPatch({ requiresRebuild: true, reason: "performance" }));
  [elements.silenceAction, elements.quietAction, elements.loudAction, elements.normalizeAudio].forEach((control) => control.addEventListener("change", () => {
    setAudioPresetCustom(); updateAudioOutputs(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio" });
  }));
  [elements.silenceMin, elements.silenceKeep, elements.maxRemoveRatio, elements.quietGain, elements.loudGain].forEach((control) => {
    control.addEventListener("input", updateAudioOutputs);
    control.addEventListener("change", () => { setAudioPresetCustom(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio" }); });
  });
  [elements.silenceThreshold, elements.preSilenceMin, elements.preSilenceKeep].forEach((control) => {
    control.addEventListener("input", () => { syncPreAudioControls(control.id); renderAudioCalibration(); });
    control.addEventListener("change", () => { syncPreAudioControls(control.id); setAudioPresetCustom(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio" }); });
  });
  elements.useRecommendedThreshold.addEventListener("click", () => {
    const profile = preAudioProfile();
    const recommended = Number(profile?.summary?.recommended_silence_threshold_dbfs ?? profile?.summary?.silence_threshold_dbfs);
    if (!Number.isFinite(recommended)) return;
    elements.silenceThreshold.value = Math.round(recommended);
    syncPreAudioControls("silenceThreshold");
    renderAudioCalibration();
    scheduleSettingsPatch({ requiresRebuild: true, reason: "audio" });
  });
  elements.targetDuration.addEventListener("input", () => updateDurationControl(Number(elements.targetDuration.value)));
  elements.targetDuration.addEventListener("change", () => scheduleSettingsPatch({ requiresRebuild: true, reason: "duration" }));
  $$(".quick-values button").forEach((button) => button.addEventListener("click", () => {
    updateDurationControl(Number(button.dataset.seconds));
    scheduleSettingsPatch({ requiresRebuild: true, reason: "duration" });
  }));

  elements.generateButton.addEventListener("click", () => state.project?.settings?.workflow === "manual" ? runUiAction(openManualDraft) : generateDraft());
  elements.cancelJobButton.addEventListener("click", cancelActiveJob);
  elements.globalCancelJobButton.addEventListener("click", cancelActiveJob);
  elements.retryDirectorButton.addEventListener("click", generateDraft);
  elements.backFromErrorButton.addEventListener("click", () => state.project?.draft ? showResult() : showSetup());
  elements.backToBriefButton.addEventListener("click", showSetup);
  $$("[data-open-studio-tab]").forEach((button) => {
    button.addEventListener("click", () => openStudioTab(button.dataset.openStudioTab));
  });
  elements.reviewSpeechSettings.addEventListener("click", () => {
    if (openStudioTab("transcript")) elements.spokenLanguageSelect.focus();
  });
  $$(".refine-grid button").forEach((button) => button.addEventListener("click", () => refineDraft(button.dataset.command)));
  elements.reelCandidateList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-candidate-id]");
    if (!button || button.disabled) return;
    const updated = await applyManualEdit("apply_reel_candidate", { candidate_id: button.dataset.candidateId });
    if (updated) toast(uiCopy("חלופת ה־Reel נטענה וניתנת לביטול", "Reel alternative loaded — you can undo it"), "success", 2800);
  });

  elements.previewPlay.addEventListener("click", togglePreview);
  elements.playButton.addEventListener("click", togglePreview);
  elements.restartPreview.addEventListener("click", () => { seekPreview(previewUsesSourceTime() ? 0 : firstKeptTime()); playPreview(); });
  elements.previewMode.addEventListener("change", () => setPreviewMode(elements.previewMode.value));
  elements.previewA.addEventListener("timeupdate", onPreviewTimeUpdate);
  elements.previewA.addEventListener("play", () => setPreviewPlaying(true));
  elements.previewA.addEventListener("pause", stopPreviewPlayback);
  elements.previewA.addEventListener("ended", stopPreviewPlayback);
  elements.previewSeek.addEventListener("input", () => {
    if (!state.project) return;
    pauseAllMedia();
    const duration = previewUsesSourceTime() ? Number(state.project.sources?.A?.duration || 0) : editDuration();
    const targetTime = (Number(elements.previewSeek.value) / 1000) * duration;
    seekPreview(previewUsesSourceTime() ? targetTime : outputToSourceTime(targetTime));
  });

  elements.advancedButton.addEventListener("click", toggleAdvanced);
  elements.closeAdvanced.addEventListener("click", () => setAdvanced(false));
  elements.studioRenderButton.addEventListener("click", openExportDialog);
  $$(".advanced-tabs button").forEach((button) => {
    button.addEventListener("click", () => selectAdvancedTab(button.dataset.tab));
    button.addEventListener("keydown", handleStudioTabKeydown);
  });
  elements.timelineFit.addEventListener("click", () => { state.timeline.fit(); updateZoomLabel(); });
  elements.timelineZoomIn.addEventListener("click", () => { state.timeline.setZoom(state.timeline.zoom * 1.35); updateZoomLabel(); });
  elements.timelineZoomOut.addEventListener("click", () => { state.timeline.setZoom(state.timeline.zoom / 1.35); updateZoomLabel(); });
  elements.timelineZoomSelection.addEventListener("click", () => { state.timeline.zoomToSelection(); updateZoomLabel(); });

  elements.quickAspectChoices.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-output-aspect]");
    if (button) setOutputAspect(button.dataset.outputAspect);
  });
  elements.aspectSelect.addEventListener("change", () => setOutputAspect(elements.aspectSelect.value));
  [elements.resolutionSelect, elements.qualitySelect, elements.fpsSelect, elements.autoReframe, elements.effectsToggle, elements.captionsToggle].forEach((control) => control.addEventListener("change", () => {
    applyFramingPreview();
    if (control === elements.fpsSelect) updateFrameRateControls(elements.fpsSelect.value);
    const requiresRebuild = control === elements.autoReframe;
    scheduleSettingsPatch({ requiresRebuild, reason: requiresRebuild ? "framing" : "output" });
    if (control === elements.captionsToggle) renderCaptionControls();
  }));
  elements.exportFpsSelect.addEventListener("change", () => {
    if (foregroundBusy()) return;
    updateFrameRateControls(elements.exportFpsSelect.value);
    scheduleSettingsPatch({ requiresRebuild: false, reason: "output" });
  });
  elements.audioCalibration.addEventListener("toggle", () => {
    if (elements.audioCalibration.open) state.audioMeter?.draw();
  });
  elements.layoutSelect.addEventListener("change", () => {
    applyFramingPreview();
    scheduleSettingsPatch({ requiresRebuild: true, reason: "framing" });
  });
  [elements.cropX, elements.cropY, elements.cropZoom].forEach((control) => control.addEventListener("input", applyFramingPreview));
  [elements.cropX, elements.cropY, elements.cropZoom].forEach((control) => control.addEventListener("change", saveCrop));
  elements.cropSourceSelect.addEventListener("change", () => loadCropControls(elements.cropSourceSelect.value));
  elements.resetCrop.addEventListener("click", () => {
    elements.cropX.value = 50; elements.cropY.value = 50; elements.cropZoom.value = 100; applyFramingPreview(); saveCrop();
  });
  elements.useEmbeddedCamera.addEventListener("click", () => {
    if (!embeddedCameraCandidate()) {
      if (elements.embeddedCameraEditor) elements.embeddedCameraEditor.open = true;
      elements.embeddedCameraEditor?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    runUiAction(saveEmbeddedCameraSelection, uiCopy("שמירת אזור המצלמה", "Saving camera area"));
  });
  bindEmbeddedCameraEditorEvents();
  elements.transcriptSearch.addEventListener("input", renderTranscript);
  elements.transcriptFilter.addEventListener("change", renderTranscript);
  elements.transcriptEditText.addEventListener("input", bufferTranscriptText);
  elements.transcriptEditForm.addEventListener("submit", (event) => { event.preventDefault(); saveTranscriptBuffers(false); });
  elements.transcriptDiscard.addEventListener("click", discardTranscriptBuffer);
  elements.transcriptPrevious.addEventListener("click", () => moveTranscriptLine(-1));
  elements.transcriptNext.addEventListener("click", () => moveTranscriptLine(1));
  elements.transcriptSaveAll.addEventListener("click", () => saveTranscriptBuffers(true));
  elements.transcriptRemove.addEventListener("click", () => runManualRangeEdit("delete_range", "edit"));
  elements.transcriptRestore.addEventListener("click", () => runManualRangeEdit("restore_range", "edit"));
  elements.clipTrimForm.addEventListener("submit", applySelectedClipTrim);
  $$('[data-timeline-tool]').forEach((button) => button.addEventListener("click", () => {
    setTimelineTool(button.dataset.timelineTool);
  }));
  elements.cancelTimelineCut.addEventListener("click", () => { state.timeline?.cancelPendingCut(); elements.timelineCanvas.focus(); });
  elements.timelineSnap.addEventListener("click", () => { state.timeline?.setSnapping(!state.timeline.snapping); elements.timelineCanvas.focus(); });
  elements.manualClear.addEventListener("click", () => { state.markIn = null; state.timeline?.clearSelection(); elements.timelineCanvas.focus(); });
  elements.manualRange.addEventListener("click", () => {
    openStudioTab("timeline");
    elements.timelineRangeForm.hidden = !elements.timelineRangeForm.hidden;
    elements.manualRange.setAttribute("aria-expanded", String(!elements.timelineRangeForm.hidden));
    renderRangeEditors();
    if (!elements.timelineRangeForm.hidden) elements.timelineRangeStart.focus();
  });
  elements.manualLayout.addEventListener("click", () => openTimelineLayout(state.manualSelection));
  for (const prefix of ["layout", "timeline"]) {
    elements[`${prefix}RangeForm`].addEventListener("submit", (event) => { event.preventDefault(); selectTypedRange(prefix); });
    for (const boundary of ["Start", "End"]) elements[`${prefix}Range${boundary}`].addEventListener("input", () => {
      elements[`${prefix}RangeForm`].dataset.dirty = "true";
      elements[`${prefix}RangeStatus`].textContent = "Press Select range to use these times. Nothing has changed yet.";
      elements[`${prefix}Range${boundary}`].removeAttribute("aria-invalid");
      renderManualControls();
      renderSourceMixer();
    });
  }
  $$('[data-range-point]').forEach((button) => button.addEventListener("click", () => {
    const [prefix, boundary] = button.dataset.rangePoint.split(":");
    elements[`${prefix}Range${boundary === "start" ? "Start" : "End"}`].value = formatSourceTime(previewTimelineTime());
    elements[`${prefix}RangeForm`].dataset.dirty = "true";
    elements[`${prefix}RangeStatus`].textContent = "Press Select range to use these times. Nothing has changed yet.";
    renderManualControls();
    renderSourceMixer();
  }));
  elements.layoutCurrentScene.addEventListener("click", () => {
    const time = previewTimelineTime();
    const scene = editorProject()?.draft?.camera_plan?.find((item) => time >= Number(item.start) && time < Number(item.end));
    if (scene) openTimelineLayout(scene);
    else elements.layoutRangeStatus.textContent = "No layout block here. Select kept footage or add this section back first.";
  });
  elements.layoutWholeEdit.addEventListener("click", () => {
    elements.layoutRangeForm.dataset.selectionKey = "";
    state.markIn = null; state.timeline?.clearSelection();
  });
  bindKeyboardControls();
  window.addEventListener("beforeunload", (event) => {
    if (state.transcriptBuffers.size || liveEmbeddedCameraRequest() || state.mediaStudio?.pending.size) { event.preventDefault(); event.returnValue = ""; }
  });
  elements.burnCaptionsToggle.addEventListener("change", () => {
    setCaptionBurnEnabled(elements.burnCaptionsToggle.checked, true);
    scheduleSettingsPatch({ reason: "captions" });
  });
  elements.studioBurnCaptionsToggle.addEventListener("change", () => {
    setCaptionBurnEnabled(elements.studioBurnCaptionsToggle.checked, true);
    scheduleSettingsPatch({ reason: "captions" });
  });
  [elements.captionStyleSelect, elements.captionPositionSelect].forEach((control) => control.addEventListener("change", () => {
    renderCaptionControls();
    scheduleSettingsPatch({ reason: "captions" });
  }));
  [elements.captionScale, elements.captionWordsPerLine].forEach((control) => {
    control.addEventListener("input", renderCaptionControls);
    control.addEventListener("change", () => scheduleSettingsPatch({ reason: "captions" }));
  });
  elements.manualRestore.addEventListener("click", () => runManualRangeEdit("restore_range"));
  elements.editorMoreButton.addEventListener("click", () => {
    if (!openStudioTab("timeline")) return;
    elements.editorMoreTools.open = true;
    elements.editorMoreTools.scrollIntoView({ block: "nearest" });
    elements.editorMoreTools.querySelector("summary").focus();
  });
  elements.sourceInsertForm.addEventListener("submit", insertSourceFootage);
  elements.emptyTimelineAdd.addEventListener("click", openSourceReview);
  document.getElementById("reviewSourceButton").addEventListener("click", openSourceReview);
  document.getElementById("closeTimelineGaps").addEventListener("click", () => {
    const slot = activeEditTarget();
    applyManualEdit("sequence_close_gaps", slot === "edit" ? {} : {slot});
  });
  elements.sourceInsertSlot.addEventListener("change", () => {
    const slot = elements.sourceInsertSlot.value;
    elements.sourceInsertIn.value = "00:00.000";
    elements.sourceInsertOut.value = formatSourceTime(Math.min(5, Number(state.project?.sources?.[slot]?.duration || 0)));
  });
  elements.sourceInsertCancel.addEventListener("click", () => { elements.sourceInsertForm.hidden = true; });
  elements.clipDuplicate.addEventListener("click", async () => {
    const clip = selectedTimelineClip();
    if (!clip || !state.project?.editor_sequence) return;
    const projectId = state.project.id;
    const updated = activeEditTarget() === "edit"
      ? await applyManualEdit("sequence_duplicate_range", { start: clip.start, end: clip.end, to: clip.end })
      : await applyManualEdit("sequence_duplicate", { slot: activeEditTarget(), clip_id: clip.id, start: clip.end });
    if (updated && state.project?.id === projectId) { state.timeline.selectRange(clip.end, clip.end + clip.end - clip.start); seekSourcePreview(clip.end); }
  });
  elements.manualDelete.addEventListener("click", () => runManualRangeEdit("delete_range"));
  elements.manualSplit.addEventListener("click", () => handleTimelineEdit({ action: "split", time: previewTimelineTime() }));
  elements.timelineTarget.addEventListener("change", () => setEditTarget(elements.timelineTarget.value));
  elements.trackReset.addEventListener("click", () => {
    if (!confirm("Reset all manual timeline changes to the AI draft? You can undo this.")) return;
    if (state.project?.editor_sequence) applyManualEdit("sequence_reset");
    else if (activeEditTarget() !== "edit") applyManualEdit("track_reset", { slot: activeEditTarget() });
  });
  elements.clipMove.addEventListener("click", async () => {
    const clip = state.trimClip, start = Number(elements.clipTrimIn.value);
    if (!clip || clip.projectId !== state.project?.id || !elements.clipTrimIn.value.trim() || !Number.isFinite(start) || start < 0) return;
    if (state.project.editor_sequence && activeEditTarget() === "edit") await handleTimelineEdit({ action: "sequence_move_range", start: clip.start, end: clip.end, to: start });
    else if (clip.id) await handleTimelineEdit({ action: "track_move", slot: activeEditTarget(), clip_id: clip.id, start });
  });
  elements.manualUndo.addEventListener("click", () => applyManualEdit("undo"));
  elements.manualRedo.addEventListener("click", () => applyManualEdit("redo"));
  elements.sourceLayoutChoices.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-layout]");
    if (!button || button.disabled) return;
    state.sourceMixerLayout = button.dataset.layout;
    if (!state.project?.draft) {
      state.sourceMixerLayoutTouched = true;
      state.sourceMixerPreviewLayout = null;
      renderSourceMixer();
      const updated = await saveSourceMixer({ default_layout: button.dataset.layout }, { silent: true });
      if (!updated) {
        hydrateSettings();
        return;
      }
      toast(uiCopy("פריסת ברירת המחדל נשמרה ל־Director", "Default layout saved for Director"), "success", 2200);
    } else {
      state.sourceMixerPreviewLayout = null;
      renderSourceMixer();
      syncSecondaryPreview(previewPlaybackTime());
      await applySourceLayout(state.manualSelection ? "selection" : "all", { immediate: true });
      return;
    }
    renderSourceMixer();
    syncSecondaryPreview(previewPlaybackTime());
  });
  elements.sceneLayoutList.addEventListener("click", (event) => {
    const jump = event.target.closest("button[data-scene-start]");
    if (!jump) return;
    const start = Number(jump.dataset.sceneStart);
    const end = Number(jump.dataset.sceneEnd);
    if (!Number.isFinite(start) || !Number.isFinite(end)) return;
    openTimelineLayout({ start, end });
  });
  elements.sceneLayoutList.addEventListener("change", async (event) => {
    const select = event.target.closest("select[data-scene-start]");
    if (!select || select.disabled) return;
    const start = Number(select.dataset.sceneStart);
    const end = Number(select.dataset.sceneEnd);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end - start < .08) return;
    const layout = select.value;
    pauseAllMedia();
    state.timeline?.selectRange(start, end);
    seekSourcePreview(start);
    state.sourceMixerLayout = layout;
    await applySourceLayout("selection", { immediate: true });
  });
  elements.applyLayoutSelection.addEventListener("click", () => applySourceLayout("selection"));
  elements.applyLayoutAll.addEventListener("click", () => applySourceLayout("all"));
  elements.creatorFramePreset.addEventListener("click", () => runUiAction(applyCreatorFrame));
  elements.stackFitSelect.addEventListener("change", () => saveSourceMixer({ stack_fit: elements.stackFitSelect.value }));
  elements.resetSourceLayout.addEventListener("click", async () => {
    const updated = await saveSourceMixer({ default_layout: null }, { silent: true });
    if (!updated) return;
    state.sourceMixerLayoutTouched = false;
    state.sourceMixerLayout = sourceMixerLayoutFromSetting(elements.layoutSelect.value);
    state.sourceMixerPreviewLayout = null;
    renderSourceMixer();
    syncSecondaryPreview(previewPlaybackTime());
    toast(uiCopy("ברירת הסגנון חזרה לשלוט בפריסה", "Style default controls the layout again"), "success", 2400);
  });
  elements.swapSourceRoles.addEventListener("click", () => {
    const screen = elements.screenSourceSelect.value;
    elements.screenSourceSelect.value = elements.cameraSourceSelect.value;
    elements.cameraSourceSelect.value = screen;
    saveSourceMixer().catch(() => {});
  });
  elements.screenSourceSelect.addEventListener("change", () => {
    elements.cameraSourceSelect.value = elements.screenSourceSelect.value === "A" ? "B" : "A";
    saveSourceMixer().catch(() => {});
  });
  elements.cameraSourceSelect.addEventListener("change", () => {
    elements.screenSourceSelect.value = elements.cameraSourceSelect.value === "A" ? "B" : "A";
    saveSourceMixer().catch(() => {});
  });
  elements.primaryRoleSelect.addEventListener("change", () => saveSourceMixer().catch(() => {}));
  elements.audioSourceSelect.addEventListener("change", () => saveSourceMixer().catch(() => {}));
  elements.firstSlotSelect.addEventListener("change", () => saveSourceMixer().catch(() => {}));
  elements.swapSourceOrder.addEventListener("click", () => {
    elements.firstSlotSelect.value = sourceMixerSettings().firstSlot === "A" ? "B" : "A";
    runUiAction(() => saveSourceMixer());
  });
  elements.sourceBEarlier.addEventListener("click", () => nudgeSourceSync(-1));
  elements.sourceBLater.addEventListener("click", () => nudgeSourceSync(1));
  elements.sourceSyncOffset.addEventListener("input", () => scheduleSourceSyncSave(false));
  elements.sourceSyncOffset.addEventListener("change", () => scheduleSourceSyncSave(true));
  elements.resetSourceSync.addEventListener("click", () => {
    clearPendingSourceSync();
    saveSourceMixer({ sync_offset: null });
  });
  elements.rebuildDraftButton.addEventListener("click", rebuildDraftFromStudio);

  elements.renderButton.addEventListener("click", openExportDialog);
  elements.resultRenderButton.addEventListener("click", openExportDialog);
  elements.closeExportDialog.addEventListener("click", () => elements.exportDialog.close());
  elements.cancelExport.addEventListener("click", () => elements.exportDialog.close());
  elements.cancelExportJobButton.addEventListener("click", cancelActiveJob);
  elements.confirmExport.addEventListener("click", startExport);
  elements.modelButton.addEventListener("click", installModel);
  elements.retryAIButton.addEventListener("click", retryLocalAI);

  document.addEventListener("keydown", handleEditorShortcut, true);
  document.addEventListener("keyup", handleEditorShortcutKeyUp, true);
  window.addEventListener("blur", resetEditorTransportKey);
}

function setActiveChoice(container, button) {
  $$(`button`, container).forEach((item) => {
    const active = item === button;
    item.classList.toggle("active", active);
    item.setAttribute("aria-pressed", String(active));
  });
}

function updatePaceNote(pace) {
  const notes = {
    gentle: "Keeps natural breathing and removes only clear mistakes and pauses.",
    balanced: t("balancedHelp"),
    dynamic: "Tighter cuts, less dead time and a faster rhythm for short-form video.",
  };
  elements.paceNote.textContent = notes[pace] || notes.balanced;
}

async function loadProjects() {
  const payload = await api("/api/projects");
  state.projects = payload.projects || [];
  state.projectsLoaded = true;
  renderRecentProjects();
  renderProjectDialog();
}

async function loadSystem() {
  const runtimeGeneration = state.runtimeGeneration;
  try {
    const payload = await api("/api/system");
    if (runtimeGeneration !== state.runtimeGeneration || state.aiPreparePromise) {
      // A slow snapshot must not replace a newer explicit preparation result.
      const { runtime: _runtime, models: _models, ...general } = payload;
      state.system = { ...(state.system || {}), ...general };
    } else state.system = payload;
  } catch (error) {
    if (runtimeGeneration === state.runtimeGeneration && !state.aiPreparePromise) state.system = { models: null, error: error.message };
  }
  renderModelStatus();
  renderUploadLimits();
  state.welcome?.setConnection(state.system?.ai_connection);
  renderEditStyleChoices();
  scheduleRuntimeRefresh();
}

function scheduleRuntimeRefresh() {
  if (state.runtimeRefreshTimer) clearTimeout(state.runtimeRefreshTimer);
  state.runtimeRefreshTimer = null;
  const starting = ["idle", "checking", "starting"].includes(state.system?.runtime?.state);
  if (!starting) { state.runtimeRefreshAttempts = 0; return; }
  // Startup is finite. After ~30 seconds the explicit Retry control takes over.
  if (state.aiPreparePromise || state.runtimeRefreshAttempts >= 20) return;
  state.runtimeRefreshTimer = setTimeout(() => {
    state.runtimeRefreshTimer = null;
    state.runtimeRefreshAttempts += 1;
    loadSystem();
  }, 1500);
}

function showWelcome() {
  pauseAllMedia();
  document.body.classList.add("welcome-mode");
  elements.welcomeView.hidden = false;
  elements.workspaceView.hidden = true;
  elements.projectHead.hidden = true;
  elements.renderButton.disabled = true;
  setAdvanced(false);
  window.scrollTo({ top: 0 });
}

async function goHome() {
  pauseAllMedia();
  if (!(await flushCurrentProjectSaves())) return;
  state.projectViewToken += 1;
  showWelcome();
}

function showWorkspace() {
  document.body.classList.remove("welcome-mode");
  elements.welcomeView.hidden = true;
  elements.workspaceView.hidden = false;
  elements.projectHead.hidden = false;
  elements.renderButton.disabled = !state.project?.draft || foregroundBusy() || state.draftDirtyReasons.size > 0;
}

async function createProject({ workflow = "short" } = {}) {
  pauseAllMedia();
  if (!(await flushCurrentProjectSaves())) return;
  const initialSettings = workflowSettings(workflow);
  const payload = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: "New project", initial_settings: initialSettings }) });
  state.projects.unshift(payload.project);
  await openProject(payload.project.id);
  if (state.project?.id === payload.project.id) window.scrollTo({ top: 0 });
  toast(t("projectCreated"), "success");
}

async function openManualDraft() {
  if (!state.project?.sources?.A || foregroundBusy()) return;
  pauseAllMedia();
  const projectId = state.project.id;
  if (!(await flushCurrentProjectSaves())) return;
  const lock = acquireJobStartLock("manual_start", projectId);
  if (!lock) return;
  try {
    const result = await api(`/api/projects/${encodeURIComponent(projectId)}/manual-draft`, {
      method: "POST", body: JSON.stringify({ expected_revision: state.project.revision }),
    });
    if (state.project?.id !== projectId) return;
    state.project = result.project;
    rememberProjectRevision(result.project);
    hydrateProject();
    setAdvanced(true);
  } finally { releaseJobStartLock(lock); renderReadiness(); }
}

async function openProject(projectId, { skipFlush = false } = {}) {
  pauseAllMedia();
  if (!skipFlush && !(await flushCurrentProjectSaves())) return null;
  const viewToken = ++state.projectViewToken;
  if (state.studio.open) setAdvanced(false);
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (viewToken !== state.projectViewToken) return null;
    state.project = payload.project;
    rememberProjectRevision(state.project);
    localStorage.setItem(lastProjectStorageKey(), projectId);
    localStorage.removeItem("cutroom-last-project");
    showWorkspace();
    hydrateProject();
    recoverActiveJobs(projectId, viewToken).catch((error) => console.warn("Could not restore active jobs", error));
    return state.project;
  } catch (error) {
    if (error?.status === 404) {
      clearRememberedProject(projectId);
      state.projects = state.projects.filter((project) => project.id !== projectId);
      renderRecentProjects();
      renderProjectDialog();
    }
    throw error;
  }
}

function hydrateProject() {
  if (!state.project) return;
  pauseAllMedia();
  if (state.sourceSyncSaveTimer) clearTimeout(state.sourceSyncSaveTimer);
  state.sourceSyncSaveTimer = null;
  state.sourceSyncPending = null;
  rememberProjectRevision(state.project);
  loadDraftRebuildState(state.project);
  state.sourceMixerPreviewLayout = null;
  state.sourceMixerCommitScope = null;
  state.sourceMixerLayout = "auto";
  state.sourceMixerLayoutTouched = false;
  setManualSelection(null);
  elements.projectName.value = state.project.name || "";
  renderSources();
  hydrateSettings();
  if (state.project.draft) showResult(); else showSetup();
  state.timeline.setProject(editorProject());
  renderManualControls();
  renderSourceMixer();
  loadSystem();
}

function hydrateSettings() {
  const settings = state.project.settings || {};
  state.selectedEditStyle = settings.edit_style || "smart";
  renderEditStyleChoices();
  setChoiceValue(elements.goalChoices, settings.goal || "short");
  applyGoalMode(settings.goal || "short", false);
  setChoiceValue(elements.paceChoices, settings.pace || "balanced");
  updatePaceNote(settings.pace || "balanced");
  elements.targetDuration.max = Math.max(15, Math.ceil(Math.min(600, state.project.sources?.A?.duration || 180)));
  updateDurationControl(Number(settings.target_duration || 60));
  elements.directorInstruction.value = settings.instruction || "";
  const embeddedOption = elements.layoutSelect.querySelector('option[value="embedded_stack"]');
  const hasSecondSource = Boolean(state.project.sources?.B);
  if (embeddedOption) { embeddedOption.disabled = hasSecondSource; embeddedOption.hidden = hasSecondSource; }
  const defaultLayoutField = elements.layoutSelect.closest("label");
  if (defaultLayoutField) defaultLayoutField.hidden = hasSecondSource;
  const savedLayout = hasSecondSource && settings.layout === "embedded_stack" ? "auto" : settings.layout;
  elements.layoutSelect.value = optionExists(elements.layoutSelect, savedLayout) ? savedLayout : "auto";
  if (hasSecondSource) {
    hydrateSourceMixerLayout();
  }
  elements.aspectSelect.value = optionExists(elements.aspectSelect, settings.aspect) ? settings.aspect : "9:16";
  renderQuickAspectChoices();
  elements.resolutionSelect.value = settings.resolution || "1080";
  elements.qualitySelect.value = settings.quality || "balanced";
  updateFrameRateControls(settings.fps ?? 30);
  elements.autoReframe.checked = settings.auto_reframe !== false;
  elements.effectsToggle.checked = settings.editorial_effects !== false;
  elements.captionsToggle.checked = Boolean(settings.captions);
  setCaptionBurnEnabled(settings.burn_captions !== false, false);
  elements.captionStyleSelect.value = optionExists(elements.captionStyleSelect, settings.caption_style) ? settings.caption_style : CAPTION_DEFAULTS.style;
  elements.captionPositionSelect.value = optionExists(elements.captionPositionSelect, settings.caption_position) ? settings.caption_position : CAPTION_DEFAULTS.position;
  elements.captionScale.value = clampInteger(settings.caption_scale, 75, 150, CAPTION_DEFAULTS.scale);
  elements.captionWordsPerLine.value = clampInteger(settings.caption_words_per_line, 2, 12, CAPTION_DEFAULTS.words);
  elements.spokenLanguageSelect.value = optionExists(elements.spokenLanguageSelect, settings.spoken_language) ? settings.spoken_language : "auto";
  elements.performanceModeSelect.value = optionExists(elements.performanceModeSelect, settings.performance_mode) ? settings.performance_mode : "auto";
  renderCaptionControls();
  renderLanguageDetectionStatus();
  hydrateAudioSettings(settings.audio_cleanup || {});
  hydratePreAudioControls(settings.audio_cleanup || {});
  renderAudioCalibration();
  const selectedCropSource = state.project.sources?.[elements.cropSourceSelect.value] ? elements.cropSourceSelect.value : "A";
  elements.cropSourceSelect.value = selectedCropSource;
  elements.cropSourceSelect.querySelector('option[value="B"]').disabled = !state.project.sources?.B;
  loadCropControls(selectedCropSource);
}

function captionBurnEnabled() {
  return Boolean(elements.burnCaptionsToggle?.checked);
}

function setCaptionBurnEnabled(enabled, touched = false) {
  const value = Boolean(enabled);
  if (elements.burnCaptionsToggle) elements.burnCaptionsToggle.checked = value;
  if (elements.studioBurnCaptionsToggle) elements.studioBurnCaptionsToggle.checked = value;
  if (touched) {
    if (elements.burnCaptionsToggle) elements.burnCaptionsToggle.dataset.touched = "1";
    if (elements.studioBurnCaptionsToggle) elements.studioBurnCaptionsToggle.dataset.touched = "1";
  }
  renderCaptionControls();
}

function captionSettingsFromControls() {
  return {
    style: elements.captionStyleSelect?.value || CAPTION_DEFAULTS.style,
    position: elements.captionPositionSelect?.value || CAPTION_DEFAULTS.position,
    scale: clampInteger(elements.captionScale?.value, 75, 150, CAPTION_DEFAULTS.scale),
    words: clampInteger(elements.captionWordsPerLine?.value, 2, 12, CAPTION_DEFAULTS.words),
  };
}

function renderCaptionControls() {
  if (!elements.captionScaleOut || !elements.captionWordsPerLineOut) return;
  const captions = captionSettingsFromControls();
  elements.captionScale.value = captions.scale;
  elements.captionWordsPerLine.value = captions.words;
  elements.captionScaleOut.textContent = `${captions.scale}%`;
  elements.captionWordsPerLineOut.textContent = String(captions.words);
  if (elements.studioBurnCaptionsToggle) elements.studioBurnCaptionsToggle.checked = captionBurnEnabled();
  const burn = captionBurnEnabled();
  const sidecar = Boolean(elements.captionsToggle?.checked);
  if (elements.captionControlStatus) {
    elements.captionControlStatus.textContent = burn && sidecar
      ? "Captions will be burned into the MP4 and exported as SRT."
      : burn
        ? "Captions will be burned into the MP4."
        : sidecar
          ? "The video stays clean; an editable SRT will be exported."
          : "Caption output is disabled. Your transcript is still preserved.";
  }
  if (elements.previewCaption) {
    elements.previewCaption.dataset.captionStyle = captions.style;
    elements.previewCaption.dataset.captionPosition = captions.position;
    elements.previewCaption.style.setProperty("--caption-preview-scale", String(captions.scale / 100));
  }
  updatePreviewCaption(previewPlaybackTime());
}

function renderLanguageDetectionStatus() {
  if (!elements.captionLanguageStatus) return;
  const transcript = state.project?.analysis?.transcript;
  const requested = elements.spokenLanguageSelect?.value || state.project?.settings?.spoken_language || "auto";
  elements.captionLanguageStatus.dataset.state = "waiting";
  elements.captionLanguageStatus.removeAttribute("title");
  if (!transcript?.language) {
    elements.captionLanguageStatus.textContent = requested === "auto"
      ? "Detected after analysis"
      : `Language locked: ${languageName(requested)}`;
    if (requested !== "auto") elements.captionLanguageStatus.dataset.state = "locked";
    return;
  }
  // A rejected transcript is deliberately emptied and its probability reset.
  // Retain the measured language evidence for diagnosis, without presenting the
  // placeholder as a new 0% estimate or claiming reliable speech was found.
  const discarded = transcript.discarded_quality;
  const evidence = discarded || transcript;
  const resolved = languageName(evidence.language || transcript.language);
  const probability = evidence.language_probability == null || evidence.language_probability === ""
    ? NaN : Number(evidence.language_probability);
  const confidence = Number.isFinite(probability) ? Math.max(0, Math.min(1, probability)) : null;
  const percent = confidence === null ? "" : ` · ${Math.round(confidence * 100)}%`;
  const detection = transcript.language_detection || {};
  const rawLanguage = transcript.detected_language || detection.raw_language;
  const rawProbability = transcript.detected_language_probability == null || transcript.detected_language_probability === ""
    ? NaN : Number(transcript.detected_language_probability);
  if (rawLanguage) {
    const rawPercent = Number.isFinite(rawProbability) ? ` (${Math.round(rawProbability * 100)}%)` : "";
    elements.captionLanguageStatus.title = `Raw detection: ${languageName(rawLanguage)}${rawPercent}`;
  }
  const analyzedRequest = String(detection.requested_language || "auto").toLowerCase();
  const explicitSelectionApplied = Boolean(
    requested !== "auto"
    && detection.source === "explicit"
    && analyzedRequest === requested
    && String(transcript.language || "").toLowerCase() === requested
  );
  if (requested !== "auto") {
    elements.captionLanguageStatus.dataset.state = explicitSelectionApplied ? "locked" : "waiting";
    elements.captionLanguageStatus.textContent = explicitSelectionApplied
      ? `Language locked: ${languageName(requested)}`
      : `Language selected: ${languageName(requested)} · Rebuild the draft to apply.`;
  } else if (detection.source === "explicit") {
    elements.captionLanguageStatus.dataset.state = "waiting";
    elements.captionLanguageStatus.textContent = "Auto-detect selected · Rebuild the draft to apply.";
  } else if (discarded) {
    elements.captionLanguageStatus.dataset.state = "low";
    elements.captionLanguageStatus.textContent = `Speech could not be transcribed reliably. Initial language estimate: ${resolved}${percent}. Choose the spoken language and rebuild.`;
  } else if (detection.ambiguous === true || (confidence !== null && confidence < 0.62)) {
    elements.captionLanguageStatus.dataset.state = "low";
    elements.captionLanguageStatus.textContent = `Low confidence: ${resolved}${percent}. Choose a language and rebuild.`;
  } else {
    elements.captionLanguageStatus.dataset.state = "detected";
    elements.captionLanguageStatus.textContent = `Detected: ${resolved}${percent}`;
  }
}

function applyGoalMode(goal, applyDefaults = false) {
  const normalized = ["short", "youtube", "podcast", "clean"].includes(goal) ? goal : "short";
  if (elements.durationGroup) elements.durationGroup.hidden = ["youtube", "clean"].includes(normalized);
  const explainer = {
    short: ["shortModeTitle", "shortModeText"],
    youtube: ["youtubeModeTitle", "youtubeModeText"],
    podcast: ["podcastModeTitle", "podcastModeText"],
    clean: ["cleanModeTitle", "cleanModeText"],
  }[normalized];
  if (elements.goalExplainerTitle) elements.goalExplainerTitle.textContent = t(explainer[0]);
  if (elements.goalExplainerText) elements.goalExplainerText.textContent = t(explainer[1]);
  elements.goalExplainer?.setAttribute("data-goal", normalized);
  const outputNote = elements.generateButton?.querySelector('[data-i18n="oneDraft"]');
  if (outputNote) outputNote.textContent = normalized === "short" ? t("oneDraft")
    : normalized === "youtube" ? "A full-length YouTube cleanup — not a Reel"
    : normalized === "clean" ? "Clean up the recording while preserving its structure"
    : "One conversation clip with context and a complete ending";
  if (!applyDefaults) return;
  const defaults = {
    short: { aspect: "9:16", layout: "auto", pace: "balanced", audio: "clean", reframe: true },
    youtube: { aspect: "16:9", layout: "A", pace: "gentle", audio: "clean", reframe: false },
    podcast: { aspect: "9:16", layout: "auto", pace: "balanced", audio: "clean", reframe: true },
    clean: { aspect: "source", layout: "A", pace: "gentle", audio: "natural", reframe: false },
  }[normalized];
  elements.aspectSelect.value = defaults.aspect;
  elements.layoutSelect.value = defaults.layout;
  setChoiceValue(elements.paceChoices, defaults.pace);
  updatePaceNote(defaults.pace);
  applyAudioPreset(defaults.audio);
  elements.autoReframe.checked = defaults.reframe;
  elements.effectsToggle.checked = !["youtube", "clean"].includes(normalized);
  if (normalized === "short" && !elements.burnCaptionsToggle.dataset.touched) setCaptionBurnEnabled(true);
  if (normalized === "youtube" && !elements.burnCaptionsToggle.dataset.touched) setCaptionBurnEnabled(false);
}

function localizedStyleValue(value) {
  if (typeof value === "string") return value;
  return value?.en || "";
}

function editStyleById(styleId) {
  const styles = Array.isArray(state.system?.edit_styles) ? state.system.edit_styles : [];
  return styles.find((style) => style.id === styleId) || styles.find((style) => style.id === "smart") || null;
}

function renderEditStyleChoices() {
  if (!elements.editStyleChoices) return;
  const styles = Array.isArray(state.system?.edit_styles) ? state.system.edit_styles : [];
  const selected = state.selectedEditStyle || state.project?.settings?.edit_style || "smart";
  if (styles.length) {
    const fragment = document.createDocumentFragment();
    for (const style of styles) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "edit-style-card";
      button.dataset.value = style.id;
      button.dataset.category = style.category || "general";
      button.setAttribute("role", "radio");

      const copy = document.createElement("span");
      const title = document.createElement("strong");
      const description = document.createElement("small");
      const metadata = document.createElement("em");
      const badge = document.createElement("b");
      title.textContent = localizedStyleValue(style.name);
      description.textContent = localizedStyleValue(style.description);
      const pace = String(style.defaults?.pace || "balanced");
      metadata.textContent = `${pace[0].toUpperCase()}${pace.slice(1)} pacing`;
      badge.textContent = localizedStyleValue(style.badge);
      copy.append(title, description, metadata);
      const structure = style.selection_policy?.story_structure;
      if (Array.isArray(structure) && structure.length) {
        const flow = document.createElement("small");
        flow.className = "style-story-flow";
        flow.textContent = structure.join(" → ");
        copy.append(flow);
      }
      button.append(copy, badge);
      fragment.append(button);
    }
    elements.editStyleChoices.replaceChildren(fragment);
  }
  $$(`button[data-value]`, elements.editStyleChoices).forEach((button) => {
    const active = button.dataset.value === selected;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  const style = editStyleById(selected);
  if (elements.editStyleNote) {
    const description = localizedStyleValue(style?.description);
    const evidence = uiCopy(
      "כל סגנון משנה את בחירת הרגעים והקצב. היעד, פורמט הפלט והאורך שבחרתם נשמרים. פריסת מסך + מצלמה לעולם לא מופעלת בלי אישור מפורש.",
      "Each style changes moment selection and pacing. Your goal, output format and duration stay selected. Screen + camera layout is never enabled without explicit confirmation.",
    );
    elements.editStyleNote.textContent = description ? `${description} ${evidence}` : evidence;
  }
}

function chooseEditStyle(styleId) {
  applyEditStyle(styleId, true);
  scheduleSettingsPatch({ requiresRebuild: true, reason: "edit_style" });
  // Rendering replaces cards. Keep focus on the chosen radio, not on the page.
  $$('button[data-value]', elements.editStyleChoices).find((button) => button.dataset.value === styleId)?.focus();
}

function handleEditStyleKeydown(event) {
  if (event.altKey || event.ctrlKey || event.metaKey) return;
  const directions = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
  if (!(event.key in directions) && !["Home", "End"].includes(event.key)) return;
  const buttons = $$('button[data-value]', elements.editStyleChoices).filter((button) => !button.disabled);
  const index = buttons.indexOf(event.target.closest('button[data-value]'));
  if (index < 0 || !buttons.length) return;
  event.preventDefault();
  const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
    : (index + directions[event.key] + buttons.length) % buttons.length;
  if (buttons[next].dataset.value !== state.selectedEditStyle) chooseEditStyle(buttons[next].dataset.value);
}

function applyEditStyle(styleId, announce = false) {
  const style = editStyleById(styleId);
  state.selectedEditStyle = style?.id || "smart";
  const defaults = style?.defaults;
  if (!defaults) {
    renderEditStyleChoices();
    return;
  }

  const goal = $("button.active", elements.goalChoices)?.dataset.value || state.project?.settings?.goal || "short";
  // A style changes editorial choices within the selected output brief.
  // Goal, duration and export format belong to their own explicit controls.
  setChoiceValue(elements.paceChoices, defaults.pace || "balanced");
  updatePaceNote(defaults.pace || "balanced");
  if (optionExists(elements.layoutSelect, defaults.layout)) elements.layoutSelect.value = defaults.layout;
  elements.autoReframe.checked = defaults.auto_reframe !== false;
  elements.effectsToggle.checked = defaults.editorial_effects !== false && !["youtube", "clean"].includes(goal);
  elements.captionsToggle.checked = Boolean(defaults.captions);
  if (elements.burnCaptionsToggle) setCaptionBurnEnabled(defaults.burn_captions !== false);
  if (optionExists(elements.performanceModeSelect, defaults.performance_mode)) elements.performanceModeSelect.value = defaults.performance_mode;
  if (defaults.audio_cleanup) {
    hydrateAudioSettings(defaults.audio_cleanup);
    hydratePreAudioControls(defaults.audio_cleanup);
  }
  renderEditStyleChoices();
  renderAudioCalibration();
  if (announce) toast(uiCopy("סגנון העריכה הוחל. אפשר לשנות כל הגדרה לפני היצירה.", "Edit style applied. You can still tune every setting before generation."), "success");
}

const AUDIO_PRESETS = {
  natural: { silence_action: "shorten", silence_min_seconds: 1.20, silence_keep_seconds: 0.48, max_remove_ratio: 0.16, quiet_action: "boost", quiet_gain_db: 2, loud_action: "lower", loud_gain_db: -2, normalize: false },
  clean: { silence_action: "shorten", silence_min_seconds: 0.75, silence_keep_seconds: 0.30, max_remove_ratio: 0.28, quiet_action: "boost", quiet_gain_db: 3, loud_action: "lower", loud_gain_db: -3, normalize: true },
  tight: { silence_action: "shorten", silence_min_seconds: 0.45, silence_keep_seconds: 0.16, max_remove_ratio: 0.42, quiet_action: "boost", quiet_gain_db: 4, loud_action: "lower", loud_gain_db: -4, normalize: true },
};

function hydrateAudioSettings(audio) {
  const preset = AUDIO_PRESETS[audio.preset] ? audio.preset : "clean";
  const values = { ...AUDIO_PRESETS[preset], ...audio };
  setChoiceValue(elements.audioPresetChoices, preset);
  elements.silenceAction.value = values.silence_action || "shorten";
  elements.silenceMin.value = Number(values.silence_min_seconds ?? .75);
  elements.silenceKeep.value = Number(values.silence_keep_seconds ?? .30);
  elements.maxRemoveRatio.value = Math.round(Number(values.max_remove_ratio ?? .28) * 100);
  elements.quietAction.value = values.quiet_action || "boost";
  elements.quietGain.value = Number(values.quiet_gain_db ?? 3);
  elements.loudAction.value = values.loud_action || "lower";
  elements.loudGain.value = Math.abs(Number(values.loud_gain_db ?? -3));
  elements.normalizeAudio.checked = values.normalize !== false;
  updateAudioPresetNote(preset);
  updateAudioOutputs();
}

function applyAudioPreset(name) {
  const preset = AUDIO_PRESETS[name] || AUDIO_PRESETS.clean;
  hydrateAudioSettings({ preset: name, ...preset });
}

function setAudioPresetCustom() {
  // Keep the visible preset selected as the starting character of the edit, while
  // the exact control values are persisted. No hidden "custom" mode is required.
}

function updateAudioPresetNote(name) {
  const keys = { natural: "audioNaturalHelp", clean: "audioCleanHelp", tight: "audioTightHelp" };
  elements.audioPresetNote.textContent = t(keys[name] || keys.clean);
}

function updateAudioOutputs() {
  elements.silenceMinOut.value = `${Number(elements.silenceMin.value).toFixed(2)}s`;
  elements.silenceKeepOut.value = `${Number(elements.silenceKeep.value).toFixed(2)}s`;
  elements.maxRemoveOut.value = `${Math.round(Number(elements.maxRemoveRatio.value))}%`;
  elements.quietGainOut.value = `+${Number(elements.quietGain.value).toFixed(Number(elements.quietGain.value) % 1 ? 1 : 0)}dB`;
  elements.loudGainOut.value = `−${Number(elements.loudGain.value).toFixed(Number(elements.loudGain.value) % 1 ? 1 : 0)}dB`;
  if (elements.preSilenceMin) elements.preSilenceMin.value = elements.silenceMin.value;
  if (elements.preSilenceKeep) elements.preSilenceKeep.value = elements.silenceKeep.value;
  if (elements.preSilenceMinOut) elements.preSilenceMinOut.value = `${Number(elements.silenceMin.value).toFixed(2)}s`;
  if (elements.preSilenceKeepOut) elements.preSilenceKeepOut.value = `${Number(elements.silenceKeep.value).toFixed(2)}s`;
  if (state.audioMeter) renderAudioCalibration();
}

function currentAudioSettings() {
  const preset = $("button.active", elements.audioPresetChoices)?.dataset.value || "clean";
  return {
    preset,
    silence_action: elements.silenceAction.value,
    silence_min_seconds: Number(elements.silenceMin.value),
    silence_threshold_dbfs: Number(elements.silenceThreshold.value),
    silence_keep_seconds: Number(elements.silenceKeep.value),
    max_remove_ratio: Number(elements.maxRemoveRatio.value) / 100,
    quiet_action: elements.quietAction.value,
    quiet_gain_db: Number(elements.quietGain.value),
    loud_action: elements.loudAction.value,
    loud_gain_db: -Math.abs(Number(elements.loudGain.value)),
    normalize: elements.normalizeAudio.checked,
    target_lufs: -16,
  };
}

function preAudioProfile() {
  const slot = sourceMixerSettings().audioSlot;
  const prepared = state.project?.pre_analysis?.audio?.[slot];
  const analysis = String(state.project?.analysis?.audio_source || "A").toUpperCase() === slot
    ? state.project?.analysis?.audio
    : null;
  return prepared || analysis || null;
}

function hydratePreAudioControls(audio = {}) {
  const profile = preAudioProfile();
  const recommended = Number(profile?.summary?.recommended_silence_threshold_dbfs ?? profile?.summary?.silence_threshold_dbfs ?? -42);
  const threshold = audio.silence_threshold_dbfs == null ? recommended : Number(audio.silence_threshold_dbfs);
  elements.silenceThreshold.value = Math.max(-60, Math.min(-20, Math.round(threshold)));
  elements.preSilenceMin.value = Number(audio.silence_min_seconds ?? elements.silenceMin.value ?? .75);
  elements.preSilenceKeep.value = Number(audio.silence_keep_seconds ?? elements.silenceKeep.value ?? .30);
  syncPreAudioControls("hydrate");
}

function syncPreAudioControls(source = "") {
  if (source === "preSilenceMin" || source === "hydrate") elements.silenceMin.value = elements.preSilenceMin.value;
  if (source === "preSilenceKeep" || source === "hydrate") elements.silenceKeep.value = elements.preSilenceKeep.value;
  if (source === "silenceMin") elements.preSilenceMin.value = elements.silenceMin.value;
  if (source === "silenceKeep") elements.preSilenceKeep.value = elements.silenceKeep.value;
  elements.silenceThresholdOut.value = `−${Math.abs(Math.round(Number(elements.silenceThreshold.value)))} dB`;
  elements.preSilenceMinOut.value = `${Number(elements.preSilenceMin.value).toFixed(2)}s`;
  elements.preSilenceKeepOut.value = `${Number(elements.preSilenceKeep.value).toFixed(2)}s`;
  updateAudioOutputs();
}

function renderAudioCalibration() {
  if (!elements.audioCalibration || !state.audioMeter) return;
  const audioSlot = sourceMixerSettings().audioSlot;
  const source = state.project?.sources?.[audioSlot];
  elements.audioCalibration.hidden = !source?.has_audio;
  if (!source?.has_audio) {
    state.audioMeter.setProfile(null);
    return;
  }
  const profile = preAudioProfile();
  if (!profile?.available || !(profile.waveform || []).length) {
    elements.recommendedThreshold.textContent = "…";
    elements.audioCutEstimate.textContent = t("measuringAudio");
    elements.audioProfileSummary.textContent = t("audioAvailableSoon");
    state.audioMeter.setProfile(null);
    return;
  }
  const recommended = Number(profile.summary?.recommended_silence_threshold_dbfs ?? profile.summary?.silence_threshold_dbfs ?? -42);
  elements.recommendedThreshold.textContent = `${recommended.toFixed(0)} dB`;
  state.audioMeter.setProfile(profile);
  state.audioMeter.setPolicy({
    threshold: Number(elements.silenceThreshold.value),
    minimum: Number(elements.preSilenceMin.value),
    keep: Number(elements.preSilenceKeep.value),
  });
  const estimate = state.audioMeter.estimate();
  elements.audioCutEstimate.textContent = t("audioEstimate")
    .replace("{ranges}", String(estimate.ranges))
    .replace("{seconds}", estimate.removedSeconds.toFixed(1));
  const noise = Number(profile.summary?.noise_floor_dbfs);
  const speech = Number(profile.summary?.speech_reference_dbfs);
  elements.audioProfileSummary.textContent = `${t("noiseFloor")} ${Number.isFinite(noise) ? noise.toFixed(1) : "—"} dB · ${t("speechLevel")} ${Number.isFinite(speech) ? speech.toFixed(1) : "—"} dB`;
}

function setChoiceValue(container, value) {
  $$(`button`, container).forEach((button) => {
    const active = button.dataset.value === value;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function optionExists(select, value) {
  return [...select.options].some((option) => option.value === value);
}

function updateDurationControl(value) {
  const min = Number(elements.targetDuration.min || 15);
  const max = Number(elements.targetDuration.max || 180);
  const clamped = Math.max(min, Math.min(max, Number(value) || 60));
  elements.targetDuration.value = clamped;
  elements.durationOutput.value = clamped >= 120 ? `${Math.round(clamped / 60 * 10) / 10}m` : `${clamped}s`;
  $$(".quick-values button").forEach((button) => button.classList.toggle("active", Number(button.dataset.seconds) === clamped));
}

function renderSources() {
  for (const slot of ["A", "B"]) {
    const source = state.project.sources?.[slot];
    const container = elements[`sourceSlot${slot}`];
    const empty = $(".source-empty", container);
    const loaded = $(".source-loaded", container);
    const video = $("video", loaded);
    const upload = activeUploadForSlot(slot);
    const uploadProgress = $(".source-upload", container);
    const uploadValue = Math.max(0, Math.min(1, Number(upload?.progress || 0)));
    uploadProgress.hidden = !upload;
    uploadProgress.setAttribute("aria-valuenow", String(Math.round(uploadValue * 100)));
    $("span", uploadProgress).style.transform = `scaleX(${uploadValue})`;
    $("b", uploadProgress).textContent = `${Math.round(uploadValue * 100)}%`;
    elements[`cancelUpload${slot}`].disabled = Boolean(upload?.cancelRequested);
    elements[`cancelUpload${slot}`].textContent = upload?.cancelRequested ? t("cancelling") : t("stopProcess");
    if (upload) container.setAttribute("aria-busy", "true"); else container.removeAttribute("aria-busy");
    empty.hidden = Boolean(source);
    loaded.hidden = !source;
    if (source) {
      container.removeAttribute("role");
      container.removeAttribute("tabindex");
      container.removeAttribute("aria-label");
    } else {
      container.setAttribute("role", "button");
      container.tabIndex = 0;
      container.setAttribute("aria-label", slot === "A" ? t("addMain") : t("addSecond"));
    }
    if (source) {
      const mediaUrl = sourceMediaUrl(source);
      if (video.dataset.sourceKey !== mediaUrl) {
        video.src = mediaUrl;
        video.dataset.sourceKey = mediaUrl;
        video.load();
      }
      $(".source-meta strong", loaded).textContent = source.name;
      $(".source-meta small", loaded).textContent = `${source.width}×${source.height} · ${formatTime(source.duration)} · ${String(source.video_codec || "").toUpperCase()}`;
    } else {
      video.removeAttribute("src"); video.dataset.sourceKey = ""; video.load();
    }
  }
  renderReadiness();
  renderAudioCalibration();
  renderSourceMixer();
}

function renderReadiness() {
  if (!elements.readiness) return;
  const source = state.project?.sources?.A;
  const ready = Boolean(source);
  const audioSlot = sourceMixerSettings().audioSlot;
  const selectedAudioSource = state.project?.sources?.[audioSlot];
  const audioMeasured = state.project?.settings?.workflow === "manual" || !selectedAudioSource?.has_audio || Boolean(preAudioProfile());
  const directorReady = ready && audioMeasured;
  const busy = foregroundBusy();
  elements.readiness.classList.toggle("ready", directorReady);
  elements.fpsSelect.disabled = busy;
  elements.exportFpsSelect.disabled = busy;
  $("p", elements.readiness).textContent = !ready ? t("waitingForVideo") : !audioMeasured ? t("measuringAudio") : t("ready");
  elements.generateButton.disabled = !directorReady || busy;
  state.welcome?.updateProject(state.project);
  const renderDisabled = !state.project?.draft || !hasTimelineFootage() || busy || state.draftDirtyReasons.size > 0;
  [elements.renderButton, elements.resultRenderButton, elements.studioRenderButton].forEach((button) => {
    if (button) button.disabled = renderDisabled;
  });
  if (elements.confirmExport && !elements.exportActions.hidden) elements.confirmExport.disabled = busy;
  renderDraftActions();
  renderManualControls();
  renderActiveJobBar();
  renderModelStatus();
}

function uploadStartBlocked(projectId, slot) {
  if (activeUploadForSlot(slot, projectId)) return true;
  if (state.activeJob || state.manualEditBusy || state.sourceSyncPending || state.sourceMixerSavePending) return true;
  return [...state.jobStartLocks].some((key) => !String(key).startsWith("upload:"));
}

async function uploadSource(slot, file) {
  const validationError = validateUploadFile(file);
  if (validationError) {
    toast(validationError);
    elements[`sourceInput${slot}`].value = "";
    return;
  }
  if (!state.project) await createProject();
  if (!state.project) return;
  const projectId = state.project.id;
  if (!(await flushCurrentProjectSaves())) return;
  if (uploadStartBlocked(projectId, slot)) {
    toast(uiCopy("כבר מתבצע תהליך אחר", "Another process is already running"));
    elements[`sourceInput${slot}`].value = "";
    return;
  }
  const uploadToken = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
  const uploadState = {
    projectId,
    slot,
    uploadToken,
    fileName: file.name,
    progress: 0,
    cancelRequested: false,
    cancelConfirmed: false,
    cancelPromise: null,
    cancelError: null,
    xhr: null,
  };
  const uploadKey = uploadStateKey(projectId, slot);
  state.activeUploads.set(uploadKey, uploadState);
  const container = elements[`sourceSlot${slot}`];
  const progress = $(".source-upload", container);
  const bar = $("span", progress);
  const label = $("b", progress);
  progress.hidden = false;
  container.setAttribute("aria-busy", "true");
  progress.setAttribute("aria-valuenow", "0");
  bar.style.transform = "scaleX(0)";
  label.textContent = "0%";
  renderReadiness();
  try {
    const payload = await uploadWithProgress(`/api/projects/${encodeURIComponent(projectId)}/sources/${slot}`, file, uploadToken, (value) => {
      if (state.activeUploads.get(uploadKey) !== uploadState) return;
      uploadState.progress = Math.max(0, Math.min(1, Number(value) || 0));
      const percent = Math.round(value * 100);
      if (state.project?.id === projectId) {
        bar.style.transform = `scaleX(${value})`;
        label.textContent = `${percent}%`;
        progress.setAttribute("aria-valuenow", String(percent));
      }
      renderActiveJobBar();
    }, (xhr) => {
      uploadState.xhr = xhr;
      if (uploadState.cancelRequested) xhr.abort();
    });
    // The upload response and the cancel request can cross on different local
    // server threads. Never publish a successful source/toast after the user has
    // already asked to cancel it; wait for the authoritative cancellation result.
    if (uploadState.cancelRequested) {
      await uploadState.cancelPromise;
      return;
    }
    let authoritativeProject = payload.project;
    try {
      const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (latest?.project) authoritativeProject = latest.project;
    } catch (_error) {
      // The upload response is still a durable fallback. A parallel slot upload
      // will reconcile the project again when it finishes.
    }
    rememberProjectRevision(authoritativeProject);
    if (!authoritativeProject?.draft) clearDraftRebuild(projectId);
    if (state.project?.id === projectId) {
      state.project = reconcileProjectSnapshot(authoritativeProject);
      renderSources();
      hydrateSettings();
    }
    if (payload.job) {
      monitorBackgroundJob(payload.job.id, { refreshAudio: true, projectId, slot });
    } else if (payload.preparation_deferred) {
      // The footage is already durable; retry only the lightweight background
      // preparation after the request/worker admission burst has settled.
      window.setTimeout(() => retrySourcePreparation(projectId, slot).catch(() => {}), 1200);
    }
    loadProjects().catch(() => {});
    loadSystem().catch(() => {});
    toast(`${slot}: ${file.name}`, "success");
  } catch (error) {
    if (error?.name === "AbortError") {
      if (uploadState.cancelRequested) await uploadState.cancelPromise;
      else toast(t("localUploadInterrupted"));
    }
    else toast(`${t("uploadFailed")}: ${error.message}`);
  } finally {
    if (state.activeUploads.get(uploadKey) === uploadState) state.activeUploads.delete(uploadKey);
    if (state.project?.id === projectId) {
      progress.hidden = true;
      container.removeAttribute("aria-busy");
      progress.setAttribute("aria-valuenow", "0");
    }
    elements[`sourceInput${slot}`].value = "";
    renderReadiness();
  }
  if (state.project?.id === projectId) {
    renderSources();
    renderSourceMixer();
  }
}

function uploadWithProgress(url, file, uploadToken, onProgress, onRequest = null) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.responseType = "json";
    xhr.setRequestHeader("X-Cutroom-Upload-Token", uploadToken);
    onRequest?.(xhr);
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response);
        return;
      }
      if (xhr.status === 413 || xhr.response?.error === "file_too_large") {
        reject(new Error(t("fileTooLarge")
          .replace("{file}", formatBytes(file.size))
          .replace("{limit}", formatBytes(maxUploadBytes()))));
        return;
      }
      if (xhr.status === 507 || xhr.response?.error === "insufficient_storage") {
        reject(new Error(t("notEnoughDisk")
          .replace("{file}", formatBytes(file.size))
          .replace("{free}", formatBytes(state.system?.limits?.disk_free_bytes || 0))));
        return;
      }
      reject(new Error(xhr.response?.message || `HTTP ${xhr.status}`));
    });
    xhr.addEventListener("error", () => reject(new Error(t("localUploadInterrupted"))));
    xhr.addEventListener("abort", () => {
      const error = new Error(t("uploadCancelled"));
      error.name = "AbortError";
      reject(error);
    });
    const data = new FormData(); data.append("file", file, file.name); xhr.send(data);
  });
}

function cancelUpload(slot = null) {
  const uploads = slot ? [activeUploadForSlot(slot)].filter(Boolean) : activeUploadsForProject();
  const cancellable = uploads.filter((upload) => !upload.cancelRequested);
  if (!cancellable.length) return false;
  for (const upload of cancellable) {
    upload.cancelRequested = true;
    upload.xhr?.abort();
    upload.cancelPromise = requestUploadCancellation(upload).catch((error) => {
      upload.cancelError = error;
      toast(`${t("cancelFailed")}: ${error.message}`);
      return null;
    });
  }
  renderSources();
  renderActiveJobBar();
  return true;
}

async function requestUploadCancellation(upload) {
  const payload = await api(
    `/api/projects/${encodeURIComponent(upload.projectId)}/sources/${encodeURIComponent(upload.slot)}/uploads/${encodeURIComponent(upload.uploadToken)}/cancel`,
    { method: "POST" },
  );
  upload.cancelConfirmed = Boolean(payload?.cancelled);
  try {
    const latest = await api(`/api/projects/${encodeURIComponent(upload.projectId)}`);
    if (state.project?.id === upload.projectId && latest?.project) {
      state.project = reconcileProjectSnapshot(latest.project);
      rememberProjectRevision(state.project);
      renderSources();
      hydrateSettings();
    }
  } catch (error) {
    if (Number(error?.status) !== 404) console.warn("Upload cancellation reconciliation failed", error);
  }
  loadProjects().catch(() => {});
  toast(t("uploadCancelled"), "success", 2600);
  return payload;
}

async function removeSource(slot) {
  if (!state.project?.sources?.[slot]) return;
  if (projectHasForegroundWork(state.project.id)) {
    toast(uiCopy("עצרו או סיימו את התהליך הפעיל לפני הסרת מקור", "Stop or finish the active process before removing a source"));
    return;
  }
  const confirmed = window.confirm(uiCopy("הסרת המקור תמחק את הניתוח וה־Draft הנוכחי. להמשיך?", "Removing this source clears the current analysis and Draft. Continue?"));
  if (!confirmed || !(await flushCurrentProjectSaves())) return;
  const projectId = state.project.id;
  const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/sources/${slot}`, { method: "DELETE" });
  rememberProjectRevision(payload.project);
  if (state.project?.id === projectId) {
    state.project = payload.project;
    renderSources();
    clearDraftRebuild();
    showSetup();
  }
}

function selectedFrameRate(value = elements.fpsSelect?.value) {
  const fps = Number(value);
  return [24, 25, 30, 50, 60].includes(fps) ? fps : 30;
}

function updateFrameRateControls(value) {
  const fps = selectedFrameRate(value);
  for (const control of [elements.fpsSelect, elements.exportFpsSelect]) {
    if (control) control.value = String(fps);
  }
  const note = fps >= 50
    ? `${fps} FPS keeps high-frame-rate footage smooth and takes more render work. Lower-FPS sources repeat frames; no motion interpolation is applied.`
    : `${fps} FPS uses less render work than 60 FPS. Higher-FPS sources are converted to the selected frame rate.`;
  for (const hint of [elements.fpsHelp, elements.exportFpsHelp]) {
    if (hint) hint.textContent = note;
  }
}

function currentSettings() {
  const goal = $("button.active", elements.goalChoices)?.dataset.value || "short";
  const pace = $("button.active", elements.paceChoices)?.dataset.value || "balanced";
  const captionSettings = captionSettingsFromControls();
  return {
    edit_style: state.selectedEditStyle || "smart",
    goal,
    pace,
    target_duration: Number(elements.targetDuration.value),
    instruction: elements.directorInstruction.value.trim(),
    aspect: elements.aspectSelect.value,
    layout: elements.layoutSelect.value,
    resolution: elements.resolutionSelect.value,
    quality: elements.qualitySelect.value,
    fps: selectedFrameRate(),
    auto_reframe: elements.autoReframe.checked,
    editorial_effects: elements.effectsToggle.checked,
    captions: elements.captionsToggle.checked,
    burn_captions: captionBurnEnabled(),
    caption_style: captionSettings.style,
    caption_position: captionSettings.position,
    caption_scale: captionSettings.scale,
    caption_words_per_line: captionSettings.words,
    spoken_language: elements.spokenLanguageSelect.value,
    performance_mode: elements.performanceModeSelect.value,
    audio_cleanup: currentAudioSettings(),
  };
}

function scheduleSettingsPatch({ requiresRebuild = false, reason = "settings" } = {}) {
  if (requiresRebuild && state.project?.draft) markDraftRebuild(reason);
  schedulePatch({ settings: currentSettings() });
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function mergePatchValues(base, next) {
  if (!isPlainObject(base) || !isPlainObject(next)) return next;
  const merged = { ...base };
  for (const [key, value] of Object.entries(next)) {
    merged[key] = isPlainObject(value) && isPlainObject(merged[key]) ? mergePatchValues(merged[key], value) : value;
  }
  return merged;
}

function applyPatchToProject(project, patch) {
  if (!project || !patch) return project;
  const next = { ...project };
  if (Object.hasOwn(patch, "name")) next.name = String(patch.name || next.name);
  if (isPlainObject(patch.settings)) next.settings = mergePatchValues(next.settings || {}, patch.settings);
  if (isPlainObject(patch.manual)) next.manual = mergePatchValues(next.manual || {}, patch.manual);
  return next;
}

function reconcileProjectSnapshot(project) {
  if (!project?.id) return project;
  const queue = state.saveQueues.get(project.id);
  const current = state.project?.id === project.id ? state.project : null;
  const snapshotRevision = Number(project.revision);
  const currentRevision = Number(current?.revision);
  const base = current && Number.isFinite(snapshotRevision) && Number.isFinite(currentRevision) && snapshotRevision < currentRevision
    ? current : project;
  // Upload/preparation replies may predate a settings save that is queued or
  // already travelling to the server. Keep those edits visible during hydration.
  return applyPatchToProject(applyPatchToProject(base, queue?.inFlightPatch), queue?.pending);
}

function saveQueueFor(projectId, revision = null) {
  let queue = state.saveQueues.get(projectId);
  if (!queue) {
    queue = { projectId, revision: revision != null && Number.isFinite(Number(revision)) ? Number(revision) : null, pending: null, timer: null, inFlight: null, inFlightPatch: null, conflictRetries: 0 };
    state.saveQueues.set(projectId, queue);
  } else if (queue.revision == null && revision != null && Number.isFinite(Number(revision))) {
    queue.revision = Number(revision);
  }
  return queue;
}

function rememberProjectRevision(project) {
  if (!project?.id) return;
  const queue = saveQueueFor(project.id, project.revision);
  const revision = Number(project.revision);
  if (Number.isFinite(revision)) queue.revision = queue.revision == null ? revision : Math.max(queue.revision, revision);
}

function setSaveState(projectId, value) {
  if (state.project?.id === projectId && elements.saveState) elements.saveState.textContent = value;
}

function schedulePatch(patch, { delay = 420 } = {}) {
  const projectId = state.project?.id;
  if (!projectId) return Promise.resolve(null);
  const queue = saveQueueFor(projectId, state.project?.revision);
  queue.pending = mergePatchValues(queue.pending || {}, patch || {});
  if (queue.timer) clearTimeout(queue.timer);
  setSaveState(projectId, "…");
  queue.timer = setTimeout(() => {
    queue.timer = null;
    flushProjectSaves(projectId).catch((error) => toast(error.message));
  }, delay);
  return Promise.resolve(queue.pending);
}

async function flushProjectSaves(projectId) {
  const queue = state.saveQueues.get(projectId);
  if (!queue) return null;
  if (queue.timer) { clearTimeout(queue.timer); queue.timer = null; }
  if (queue.inFlight) {
    await queue.inFlight;
    return queue.pending ? flushProjectSaves(projectId) : null;
  }
  if (!queue.pending) return null;

  const patch = queue.pending;
  queue.pending = null;
  queue.inFlightPatch = patch;
  const expectedRevision = queue.revision;
  const requestBody = { ...patch, expected_revision: expectedRevision };
  const requestPromise = api(`/api/projects/${encodeURIComponent(projectId)}`, {
    method: "PATCH",
    body: JSON.stringify(requestBody),
  });
  queue.inFlight = requestPromise;
  let retryAfterConflict = false;
  try {
    const payload = await requestPromise;
    const savedProject = payload.project;
    if (savedProject) {
      const responseRevision = Number(savedProject.revision);
      const currentRevision = state.project?.id === projectId ? Number(state.project.revision) : NaN;
      const knownRevision = Math.max(
        Number.isFinite(Number(queue.revision)) ? Number(queue.revision) : -1,
        Number.isFinite(currentRevision) ? currentRevision : -1,
      );
      const responseIsStale = Number.isFinite(responseRevision) && responseRevision < knownRevision;
      if (!responseIsStale && Number.isFinite(responseRevision)) queue.revision = responseRevision;
      if (!responseIsStale && state.project?.id === projectId) {
        state.project = applyPatchToProject(savedProject, queue.pending);
        setSaveState(projectId, t("saved"));
      } else if (responseIsStale && state.project?.id === projectId && !queue.pending) {
        setSaveState(projectId, t("saved"));
      }
    }
    queue.conflictRetries = 0;
    loadProjects().catch(() => {});
  } catch (error) {
    queue.pending = mergePatchValues(patch, queue.pending || {});
    setSaveState(projectId, "!");
    if (isRevisionConflict(error) && queue.conflictRetries < 2) {
      queue.conflictRetries += 1;
      const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (!latest?.project) throw error;
      const latestRevision = Number(latest.project.revision);
      if (Number.isFinite(latestRevision)) queue.revision = latestRevision;
      if (state.project?.id === projectId) state.project = applyPatchToProject(latest.project, queue.pending);
      retryAfterConflict = true;
    } else {
      throw error;
    }
  } finally {
    if (queue.inFlight === requestPromise) {
      queue.inFlight = null;
      queue.inFlightPatch = null;
    }
  }
  if (retryAfterConflict) return flushProjectSaves(projectId);
  return queue.pending ? flushProjectSaves(projectId) : null;
}

function isRevisionConflict(error) {
  return Number(error?.status) === 409 && error?.code === "revision_conflict";
}

async function flushCurrentProjectSaves() {
  if (state.mediaStudio && !(await state.mediaStudio.flush())) return false;
  const projectId = state.project?.id;
  if (!projectId) return true;
  try {
    if (!(await saveTranscriptBuffers(true))) return false;
    if (state.manualEditPromise) await state.manualEditPromise;
    if (state.sourceMixerSavePending) await state.sourceMixerSaveTail;
    await flushPendingSourceSync(projectId);
    if (!(await flushEmbeddedCameraSave(projectId))) return false;
    await flushProjectSaves(projectId);
    return true;
  } catch (error) {
    toast(`${uiCopy("השמירה נכשלה", "Save failed")}: ${error.message}`);
    return false;
  }
}

function foregroundBusy() {
  return Boolean(state.activeJob || state.activeUploads.size || state.mediaStudio?.uploading || state.manualEditBusy || state.sourceSyncPending || state.sourceMixerSavePending) || state.jobStartLocks.size > 0;
}

function projectHasForegroundWork(projectId) {
  if (!projectId) return false;
  if (activeUploadsForProject(projectId).length) return true;
  if (state.sourceMixerDesired?.projectId === projectId && state.sourceMixerSavePending) return true;
  if (state.activeJobMeta?.projectId === projectId) return true;
  return [...state.jobStartLocks].some((key) => String(key).endsWith(`:${projectId}`));
}

function pendingForegroundKind() {
  if (activeUploadsForProject().length) return "upload";
  const lock = [...state.jobStartLocks].find((item) => !String(item).startsWith("recover:"));
  return String(lock || "director").split(":", 1)[0];
}

function activeJobKindLabel(kind) {
  if (kind === "upload") return t("activeUpload");
  if (kind === "render") return t("activeExport");
  if (kind === "model_install") return t("activeModel");
  return t("activeDirector");
}

function jobCancellationRequested(job = null) {
  const jobId = job?.id || state.activeJob;
  const uploads = activeUploadsForProject();
  return Boolean(
    (uploads.length && uploads.every((upload) => upload.cancelRequested))
    || state.cancelBeforeStart
    || (jobId && state.cancelRequestedJobs.has(jobId))
    || job?.cancel_requested
    || String(job?.message || "").toLowerCase() === "cancelling"
  );
}

function renderActiveJobBar(job = null) {
  if (!elements.activeJobBar) return;
  if (job && (!state.activeJob || job.id === state.activeJob)) state.activeJobSnapshot = job;
  const uploads = activeUploadsForProject();
  const uploadSnapshot = uploads.length ? {
    progress: uploads.reduce((total, upload) => total + Number(upload.progress || 0), 0) / uploads.length,
    message: `${t("preparing")}: ${uploads.map((upload) => `${upload.slot} · ${upload.fileName}`).join(" + ")}`,
  } : null;
  const snapshot = job || state.activeJobSnapshot || uploadSnapshot;
  const pendingStart = !state.activeJob && [...state.jobStartLocks].some((item) => !String(item).startsWith("recover:"));
  const visible = Boolean(state.activeJob || uploads.length || pendingStart);
  elements.activeJobBar.hidden = !visible;
  if (!visible) return;

  const kind = uploads.length ? "upload" : state.activeJobMeta?.kind || pendingForegroundKind();
  const cancelling = jobCancellationRequested(snapshot);
  const progress = Math.max(0, Math.min(100, Math.round(Number(snapshot?.progress || 0) * 100)));
  elements.activeJobBar.classList.toggle("cancelling", cancelling);
  elements.activeJobLabel.textContent = activeJobKindLabel(kind);
  elements.activeJobDetail.textContent = cancelling
    ? t("cancelling")
    : state.aiPreparePromise && pendingStart ? "Preparing local AI…"
      : snapshot?.message || (progress ? `${progress}%` : t("directorPreparing"));
  for (const button of [elements.globalCancelJobButton, elements.cancelJobButton, elements.cancelExportJobButton]) {
    if (!button) continue;
    button.disabled = cancelling;
    button.textContent = cancelling ? t("cancelling") : t("stopProcess");
  }
}

function acquireJobStartLock(kind, projectId) {
  const key = `${kind}:${projectId}`;
  if (foregroundBusy() || state.jobStartLocks.has(key)) return null;
  state.cancelBeforeStart = false;
  state.jobStartLocks.add(key);
  renderReadiness();
  return key;
}

function assertJobStartNotCancelled() {
  if (state.cancelBeforeStart) throw new Error("Cancelled");
}

function releaseJobStartLock(key) {
  if (key) state.jobStartLocks.delete(key);
  renderReadiness();
  // Reel cards are rendered while the Director start lock is still held, so
  // their buttons are initially disabled. Refresh them once the lock is gone;
  // otherwise alternatives remain unusable until a full page reload.
  renderReelCandidates();
}

function setActiveJob(jobId, meta = null) {
  state.activeJob = jobId || null;
  state.activeJobMeta = jobId ? meta : null;
  state.activeJobSnapshot = null;
  renderReadiness();
  if (jobId && state.cancelBeforeStart) {
    state.cancelBeforeStart = false;
    requestJobCancellation(jobId).catch(() => {});
  }
}

function clearActiveJob(jobId = null) {
  if (jobId && state.activeJob !== jobId) return;
  if (state.activeJob) state.cancelRequestedJobs.delete(state.activeJob);
  state.activeJob = null;
  state.activeJobMeta = null;
  state.activeJobSnapshot = null;
  state.cancelBeforeStart = false;
  renderReadiness();
}

async function reconcileDirectorOutcome(projectId, message, { cancelled = false } = {}) {
  if (state.project?.id !== projectId) return false;
  try {
    const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (state.project?.id !== projectId || !latest?.project) return false;
    state.project = latest.project;
    rememberProjectRevision(state.project);
  } catch (_refreshError) {
    // The in-memory Draft is still authoritative enough to render if a refresh
    // races with a short local-server restart.
  }
  if (state.project?.id !== projectId) return false;
  if (state.project?.draft) {
    hydrateProject();
    return true;
  }
  if (cancelled) showSetup();
  else showAnalysisError(message);
  return false;
}

async function generateDraft() {
  if (state.mediaStudio && !(await state.mediaStudio.flush())) return;
  if (!requireSavedTranscript()) return;
  if (!state.project?.sources?.A) {
    toast(t("waitingForVideo"));
    return;
  }
  const projectId = state.project.id;
  const viewToken = state.projectViewToken;
  if (liveEmbeddedCameraRequest()
    && (!(await flushEmbeddedCameraSave(projectId)) || state.project?.id !== projectId || state.projectViewToken !== viewToken)) return;
  const lock = acquireJobStartLock("director", projectId);
  if (!lock) {
    toast(t("directorBusy"));
    return;
  }
  pauseAllMedia();
  showAnalysis();
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken) throw new Error("Cancelled");
    const settings = currentSettings();
    await ensureStoryAIReady(settings.goal);
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken) throw new Error("Cancelled");
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/director`, { method: "POST", body: JSON.stringify(settings) });
    await pollJob(payload.job.id, { director: true, projectId });
  } catch (error) {
    if (state.project?.id === projectId) {
      await reconcileDirectorOutcome(projectId, error.message, { cancelled: error.message === "Cancelled" });
    }
  } finally {
    if (!state.activeJob) state.cancelBeforeStart = false;
    releaseJobStartLock(lock);
  }
}

async function ensureStoryAIReady(requestedGoal = null) {
  if (state.system?.ai_connection?.mode && state.system.ai_connection.mode !== "local") {
    if (!state.system.ai_connection.configured) throw new Error("Connect your provider API key in AI connection before starting cloud AI.");
    assertJobStartNotCancelled();
    return true;
  }
  const goal = requestedGoal || $("button.active", elements.goalChoices)?.dataset.value || state.project?.settings?.goal || "short";
  if (!["short", "podcast"].includes(goal)) return true;
  const projectId = state.project?.id;
  const viewToken = state.projectViewToken;
  const assertCurrent = () => {
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken) throw new Error("Cancelled");
  };
  assertCurrent();
  elements.jobMessage.textContent = "Preparing local AI…";
  const prepared = await prepareLocalAI();
  assertCurrent();
  if (prepared.story_ai?.ready) return true;
  if (!prepared.runtime?.available) throw new Error(prepared.runtime?.message || "Local AI is unavailable. Use Retry AI to check it again.");
  const target = prepared.story_ai?.recommended_model;
  if (!target) throw new Error("No Story AI model is configured. Check the local AI settings and retry.");
  await downloadStoryModel(target, assertCurrent);
  assertCurrent();
  const verified = await prepareLocalAI();
  assertCurrent();
  if (!verified.story_ai?.ready) throw new Error(verified.runtime?.available
    ? "The Story AI model is not ready yet. Use Retry AI to check the installation."
    : verified.runtime?.message || "Local AI is unavailable. Use Retry AI to check it again.");
  return true;
}

async function refineDraft(command) {
  if (state.mediaStudio && !(await state.mediaStudio.flush())) return;
  if (!requireSavedTranscript()) return;
  if (!state.project?.draft) return;
  if (state.draftDirtyReasons.size) { toast(t("rebuildBeforeRefine")); return; }
  if (command === "new_variation" && !canVaryDraft()) return;
  const projectId = state.project.id;
  if (liveEmbeddedCameraRequest() && (!(await flushEmbeddedCameraSave(projectId)) || state.project?.id !== projectId)) return;
  const lock = acquireJobStartLock("director", projectId);
  if (!lock) { toast(t("directorBusy")); return; }
  pauseAllMedia();
  showAnalysis();
  const previousCut = cutSelectionSignature(state.project.draft);
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if (command === "new_variation") {
      await ensureStoryAIReady("short");
      assertJobStartNotCancelled();
    }
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/director/refine`, { method: "POST", body: JSON.stringify({ command }) });
    const job = await pollJob(payload.job.id, { director: true, projectId, announceReady: command !== "new_variation" });
    if (command === "new_variation" && state.project?.id === projectId) {
      const changed = job?.result?.variation_changed !== false && previousCut !== cutSelectionSignature(state.project.draft);
      toast(t(changed ? "anotherCutReady" : "anotherCutUnchanged"), changed ? "success" : "info", 4000);
    }
  } catch (error) {
    if (error.message !== "Cancelled") toast(`${t("directorFailed")}: ${error.message}`);
    if (state.project?.id === projectId) showResult();
  } finally {
    if (!state.activeJob) state.cancelBeforeStart = false;
    releaseJobStartLock(lock);
  }
}

function cutSelectionSignature(draft) {
  return JSON.stringify((draft?.keep_ranges || []).map((range) => [Number(range.start), Number(range.end)]));
}

function showSetup() {
  pauseAllMedia();
  if (state.studio.open) setAdvanced(false);
  setStep(1);
  elements.setupPanel.hidden = false;
  elements.analysisPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.renderButton.disabled = !state.project?.draft || foregroundBusy() || state.draftDirtyReasons.size > 0;
  renderReadiness();
}

function showAnalysis() {
  pauseAllMedia();
  if (state.studio.open) setAdvanced(false);
  setStep(2);
  elements.setupPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.analysisPanel.hidden = false;
  elements.jobProgress.style.width = "0%";
  elements.jobProgress.parentElement?.setAttribute("aria-valuenow", "0");
  elements.jobMessage.textContent = t("directorPreparing");
  elements.analysisError.hidden = true;
  elements.analysisErrorMessage.textContent = "";
  elements.cancelJobButton.hidden = false;
  elements.cancelJobButton.disabled = false;
  elements.cancelJobButton.textContent = t("stopProcess");
  elements.analysisPanel.classList.remove("failed");
  $$(".analysis-checks li").forEach((item) => item.classList.remove("done", "active"));
  $(".analysis-checks li")?.classList.add("active");
  elements.generateButton.disabled = true;
  const chromeHeight = document.getElementById("appChrome")?.getBoundingClientRect().height || 64;
  const panelTop = window.scrollY + elements.analysisPanel.getBoundingClientRect().top;
  window.scrollTo({ top: Math.max(0, panelTop - chromeHeight - 16), behavior: "instant" });
}

function friendlyDirectorError(message) {
  const clean = String(message || "").replace(/^[A-Za-z]+(?:Error)?:\s*/, "").trim();
  if (/omitted one or more chapters|chapter pass did not return chapter summaries/i.test(clean)) {
    const sourceMissing = !state.project?.sources?.A;
    return uiCopy(
      sourceMissing
        ? "ההרצה הקודמת נעצרה בגלל תשובת פרק חלקית. מנגנון השחזור תוקן, אבל מקור A כבר לא מחובר לפרויקט הזה. הוסיפו שוב את הקובץ המקורי ובנו את ה־Draft."
        : "ההרצה הקודמת נעצרה בגלל תשובת פרק חלקית. מנגנון השחזור תוקן: CUTROOM תנסה שוב רק את הפרק החסר, ובמידת הצורך תמשיך מהתמלול האמיתי שלו. בנו מחדש את ה־Draft.",
      sourceMissing
        ? "The earlier run stopped on an incomplete chapter response. Chapter recovery is fixed, but Source A is no longer attached to this project. Add the original file again, then build the Draft."
        : "The earlier run stopped on an incomplete chapter response. Chapter recovery is fixed: CUTROOM retries only the missing chapter and, if needed, continues from that chapter's real transcript. Rebuild the Draft.",
    );
  }
  if (/transcript quality is too low|too little usable speech|language confidence|very long hallucinated segment|needs reliable speech/i.test(clean)) {
    return uiCopy(
      "לא נמצא מספיק דיבור אמין לסגנון הזה. חומר הגלם נשמר. בחרו את שפת הדיבור המדויקת ונסו מצב איכות, או עברו ל׳היילייטים מהסטרים׳ כדי לבנות Draft מסאונד ומעברים.",
      "This style needs more reliable speech. Your footage is safe. Choose the exact spoken language and Quality mode, or switch to Stream Highlights for an audio-and-visual draft.",
    );
  }
  if (/empty response|output budget|internal thinking/i.test(clean)) {
    const contextSaved = state.project?.analysis?.status === "context_ready";
    return uiCopy(
      contextSaved
        ? "מודל ה־Storyline לא החזיר תשובה מלאה, אבל התמלול והניתוח שכבר הסתיימו נשמרו. אפשר לנסות שוב בלי לעבד את כל הסרטון מחדש."
        : "מודל ה־Storyline לא החזיר תשובה מלאה בהרצה הישנה. ניסיון נוסף יעבד את המקור פעם אחת; מעכשיו CUTROOM שומרת את שלבי הניתוח לפני ה־Storyline כדי שכשל נוסף לא יתחיל מהתחלה.",
      contextSaved
        ? "The Storyline model did not return a complete answer, but completed transcript and context work was saved. You can retry without processing the entire recording again."
        : "The Storyline model returned no complete answer in the earlier run. One retry must process the source again; CUTROOM now checkpoints context before Storyline so another late failure will not restart from zero.",
    );
  }
  return clean || uiCopy("אירעה שגיאה מקומית בזמן בניית העריכה.", "A local error occurred while building the edit.");
}

function showAnalysisError(message) {
  showAnalysis();
  const transcriptProblem = /transcript quality is too low|too little usable speech|language confidence|very long hallucinated segment|needs reliable speech/i.test(String(message || ""));
  elements.analysisPanel.classList.add("failed");
  elements.jobMessage.textContent = uiCopy("העריכה לא הושלמה", "The edit was not completed");
  elements.analysisErrorTitle.textContent = transcriptProblem
    ? uiCopy("הסגנון הזה צריך דיבור ברור", "This style needs clear speech")
    : uiCopy("העריכה נעצרה לפני הסיום", "The edit stopped before completion");
  elements.analysisErrorMessage.textContent = friendlyDirectorError(message);
  elements.analysisError.hidden = false;
  elements.cancelJobButton.hidden = true;
  toast(`${t("directorFailed")}: ${friendlyDirectorError(message)}`);
}

function showResult() {
  if (!state.project?.draft) return showSetup();
  pauseAllMedia();
  setStep(3);
  elements.setupPanel.hidden = true;
  elements.analysisPanel.hidden = true;
  elements.resultPanel.hidden = false;
  elements.renderButton.disabled = foregroundBusy() || state.draftDirtyReasons.size > 0;
  renderDraft();
  setAdvanced(true);
}

async function monitorBackgroundJob(jobId, options = {}) {
  if (state.backgroundJobs.has(jobId)) return null;
  state.backgroundJobs.add(jobId);
  try {
    const job = await pollJob(jobId, {
      silent: true,
      background: true,
      projectId: options.projectId || null,
      refreshAudio: Boolean(options.refreshAudio),
      slot: options.slot || null,
    });
    if (options.refreshSystem) await loadSystem().catch(() => {});
    return job;
  } catch (error) {
    console.warn("CUTROOM background job failed", jobId, error);
    if (options.refreshAudio && options.projectId && options.slot) {
      await retrySourcePreparation(options.projectId, options.slot, jobId);
    } else if (!options.modelInstall) {
      toast(uiCopy("עבודת רקע נכשלה. חומר הגלם נשמר.", "A background job failed. Your footage is safe."));
    }
    return null;
  } finally {
    state.backgroundJobs.delete(jobId);
    if (options.modelInstall && state.modelInstallJob === jobId) state.modelInstallJob = null;
  }
}

async function retrySourcePreparation(projectId, slot, failedJobId = "") {
  let source = state.project?.id === projectId ? state.project.sources?.[slot] : null;
  if (!source) {
    try {
      const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      source = latest?.project?.sources?.[slot] || null;
    } catch (_error) {
      // The retry request below remains authoritative and will surface a useful
      // project/source error if this lookup raced with navigation or deletion.
    }
  }
  const generation = String(source?.generation || "unknown");
  const key = `${projectId}:${slot}:${generation}`;
  if (state.retriedSourcePreparations.has(key)) {
    toast(uiCopy(
      "הכנת חומר הגלם עדיין לא הושלמה. אפשר להעלות אותו מחדש או להפעיל מחדש את CUTROOM ולנסות שוב.",
      "Source preparation still did not complete. Re-import it or restart CUTROOM and retry.",
    ));
    return null;
  }
  state.retriedSourcePreparations.add(key);
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/sources/${encodeURIComponent(slot)}/prepare`, { method: "POST" });
    if (state.project?.id === projectId && payload?.project) {
      state.project = reconcileProjectSnapshot(payload.project);
      rememberProjectRevision(state.project);
      renderSources();
      hydrateAudioSettings(state.project.settings?.audio_cleanup || {});
      renderAudioCalibration();
    }
    toast(uiCopy("CUTROOM מנסה שוב להכין את חומר הגלם.", "CUTROOM is retrying source preparation."));
    if (payload?.job && payload.job.id !== failedJobId) {
      monitorBackgroundJob(payload.job.id, { refreshAudio: true, projectId, slot }).catch(() => {});
    }
    return payload?.job || null;
  } catch (error) {
    // Admission and connection failures are transient. Do not permanently burn
    // the one automatic retry for this source unless a retry was actually queued.
    state.retriedSourcePreparations.delete(key);
    toast(`${uiCopy("הכנת חומר הגלם נכשלה", "Source preparation failed")}: ${error.message}`);
    return null;
  }
}

async function refreshProjectAfterDirector(projectId, attempts = 3) {
  let lastError = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (!payload?.project?.draft) throw new Error("Director completed but the Draft is not available yet");
      rememberProjectRevision(payload.project);
      if (state.project?.id === projectId) {
        state.project = payload.project;
        hydrateProject();
      }
      loadProjects().catch(() => {});
      return payload.project;
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await new Promise((resolve) => window.setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
  throw lastError || new Error("Could not refresh the completed Draft");
}

async function recoverActiveJobs(projectId, viewToken) {
  if (!projectId || state.recoveringJobs.has(projectId)) return;
  state.recoveringJobs.add(projectId);
  const recoveryLock = `recover:${projectId}`;
  state.jobStartLocks.add(recoveryLock);
  renderReadiness();
  try {
    let payload;
    try {
      payload = await api(`/api/projects/${encodeURIComponent(projectId)}/jobs/active`);
    } catch (error) {
      if ([404, 405].includes(Number(error?.status))) return;
      throw error;
    }
    if (viewToken !== state.projectViewToken || state.project?.id !== projectId) return;
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : payload?.job ? [payload.job] : [];
    const recent = Array.isArray(payload?.recent) ? payload.recent : jobs;
    const interrupted = recent.find((job) => job?.status === "interrupted" && !state.reportedInterruptedJobs.has(job.id));
    if (interrupted) {
      state.reportedInterruptedJobs.add(interrupted.id);
      toast(uiCopy(
        "עבודה קודמת נעצרה כשהאפליקציה נסגרה. אפשר להפעיל אותה שוב בבטחה.",
        "A previous job stopped when CUTROOM closed. You can start it again safely.",
      ));
    }
    const active = jobs.filter((job) => ["queued", "running"].includes(job?.status));
    for (const job of active.filter((item) => item.kind === "prepare_source")) {
      const slot = String(job.dedupe_key || "A").split(":", 1)[0].toUpperCase();
      monitorBackgroundJob(job.id, { refreshAudio: true, projectId, slot }).catch(() => {});
    }
    const foreground = active.find((job) => ["director", "refine", "render"].includes(job.kind));
    state.jobStartLocks.delete(recoveryLock);
    renderReadiness();
    if (!foreground) {
      const latestPreparation = recent
        .filter((job) => job?.kind === "prepare_source")
        .sort((left, right) => Date.parse(right.created_at || 0) - Date.parse(left.created_at || 0))[0];
      if (latestPreparation && ["failed", "interrupted"].includes(latestPreparation.status)) {
        const slot = String(latestPreparation.dedupe_key || "A").split(":", 1)[0].toUpperCase();
        const source = state.project?.sources?.[slot];
        if (source && (source.preparation !== "ready" || (slot === "A" && source.has_audio && !source.audio_profile_ready))) {
          retrySourcePreparation(projectId, slot, latestPreparation.id).catch(() => {});
        }
      }
      const latestDirector = recent
        .filter((job) => ["director", "refine"].includes(job?.kind))
        .sort((left, right) => Date.parse(right.created_at || 0) - Date.parse(left.created_at || 0))[0];
      if (latestDirector?.status === "completed" && !state.project?.draft) {
        try {
          await refreshProjectAfterDirector(projectId);
          if (options.announceReady !== false) toast(t("draftReady"), "success");
        } catch (error) {
          showAnalysisError(error.message);
        }
      } else if (["failed", "interrupted"].includes(latestDirector?.status) && !state.project?.draft && !state.reportedFailedJobs.has(latestDirector.id)) {
        state.reportedFailedJobs.add(latestDirector.id);
        showAnalysisError(latestDirector.error || latestDirector.message);
      }
      return;
    }
    if (foregroundBusy()) return;
    if (foreground.kind === "render") {
      resumeExportJob(foreground).catch((error) => toast(`${t("exportFailed")}: ${friendlyRenderError(error.message)}`));
      return;
    }
    showAnalysis();
    pollJob(foreground.id, { director: true, projectId, resumed: true }).catch(async (error) => {
      if (state.project?.id !== projectId) return;
      await reconcileDirectorOutcome(projectId, error.message, { cancelled: error.message === "Cancelled" });
    });
  } finally {
    state.jobStartLocks.delete(recoveryLock);
    state.recoveringJobs.delete(projectId);
    renderReadiness();
  }
}

async function pollJob(jobId, options = {}) {
  const blocking = !options.background;
  if (blocking) {
    setActiveJob(jobId, { projectId: options.projectId || null, kind: options.modelInstall ? "model_install" : options.director ? "director" : "job" });
  }
  return new Promise((resolve, reject) => {
    let consecutivePollFailures = 0;
    let connectionNoticeShown = false;
    const finishWithError = (error) => {
      if (blocking) clearActiveJob(jobId);
      reject(error);
    };
    const handleJob = async (job) => {
      if (!job) return false;
      if (!options.silent) updateJobUI(job);
      if (options.background && options.refreshAudio && !options.audioRefreshed && job.kind === "prepare_source" && Number(job.progress || 0) >= 0.295 && job.project_id) {
        options.audioRefreshed = true;
        try {
          const projectPayload = await api(`/api/projects/${encodeURIComponent(job.project_id)}`);
          if (state.project?.id === job.project_id) {
            state.project = reconcileProjectSnapshot(projectPayload.project);
            rememberProjectRevision(state.project);
            renderSources();
            hydratePreAudioControls(state.project.settings?.audio_cleanup || {});
            renderAudioCalibration();
          }
        } catch (error) {
          if (error?.status !== 404) console.warn("Audio preview refresh failed", error);
        }
      }
      if (
        options.background
        && options.refreshAudio
        && !options.visionRefreshed
        && job.kind === "prepare_source"
        && Number(job.progress || 0) >= 0.075
        && job.project_id
        && (!options.slot || String(options.slot).toUpperCase() === "A")
      ) {
        // Source A camera discovery is saved before proxy generation, which can
        // take minutes for a long recording. Refresh once at that boundary so a
        // baked-in camera suggestion appears while the remaining preparation
        // continues in the background.
        options.visionRefreshed = true;
        try {
          const projectPayload = await api(`/api/projects/${encodeURIComponent(job.project_id)}`);
          if (state.project?.id === job.project_id) {
            state.project = reconcileProjectSnapshot(projectPayload.project);
            rememberProjectRevision(state.project);
            renderSources();
          }
        } catch (error) {
          if (error?.status !== 404) console.warn("Camera detection refresh failed", error);
        }
      }
      if (job.status === "completed") {
        const cancelledModelSetup = options.modelInstall && jobCancellationRequested(job);
        if (blocking) clearActiveJob(jobId);
        // Stop applies to the pending edit too, even when a model finishes in
        // the same instant. Do not let clearActiveJob erase that intention.
        if (cancelledModelSetup) { reject(new Error("Cancelled")); return true; }
        if (job.project_id && options.director) {
          clearDraftRebuild(job.project_id);
          try {
            if (state.project?.id === job.project_id) await refreshProjectAfterDirector(job.project_id);
            else loadProjects().catch(() => {});
          } catch (error) {
            reject(error);
            return true;
          }
          toast(t("draftReady"), "success");
        } else if (job.project_id && job.kind === "prepare_source") {
          try {
            const projectPayload = await api(`/api/projects/${encodeURIComponent(job.project_id)}`);
            if (state.project?.id === job.project_id) {
              state.project = reconcileProjectSnapshot(projectPayload.project);
              rememberProjectRevision(state.project);
              renderSources();
              hydratePreAudioControls(state.project.settings?.audio_cleanup || {});
              renderAudioCalibration();
              state.timeline?.setProject(editorProject());
            }
          } catch (error) {
            if (error?.status !== 404) console.warn("Source refresh failed", error);
          }
        }
        resolve(job);
        return true;
      }
      if (["failed", "interrupted"].includes(job.status)) {
        finishWithError(new Error(job.error || (job.status === "interrupted" ? "Job interrupted by restart" : "Job failed")));
        return true;
      }
      if (job.status === "cancelled") {
        finishWithError(new Error("Cancelled"));
        return true;
      }
      return false;
    };
    const schedule = (delay) => {
      state.jobTimer = setTimeout(tick, delay);
    };
    const tick = async () => {
      try {
        const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
        consecutivePollFailures = 0;
        connectionNoticeShown = false;
        if (await handleJob(payload.job)) return;
        schedule(600);
      } catch (error) {
        consecutivePollFailures += 1;
        if (Number(error?.status) === 404) {
          finishWithError(error);
          return;
        }
        if (options.projectId && consecutivePollFailures >= 4) {
          try {
            const recovery = await api(`/api/projects/${encodeURIComponent(options.projectId)}/jobs/active`);
            const candidates = [
              ...(Array.isArray(recovery?.jobs) ? recovery.jobs : []),
              ...(Array.isArray(recovery?.recent) ? recovery.recent : []),
            ];
            const recovered = candidates
              .filter((job) => job?.id === jobId)
              .sort((left, right) => Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0))[0];
            if (recovered) {
              consecutivePollFailures = 0;
              connectionNoticeShown = false;
              if (await handleJob(recovered)) return;
              schedule(800);
              return;
            }
          } catch (_recoveryError) {
            // A temporary local-server interruption is not a failed edit.
          }
        }
        if (!connectionNoticeShown && consecutivePollFailures >= 4) {
          connectionNoticeShown = true;
          toast(uiCopy(
            "החיבור המקומי נקטע לרגע. CUTROOM ממשיכה לבדוק את העריכה בלי להתחיל אותה מחדש.",
            "The local connection paused. CUTROOM is still checking this edit without restarting it.",
          ));
        }
        schedule(Math.min(5000, 650 * Math.max(1, consecutivePollFailures)));
      }
    };
    tick();
  });
}

function updateJobUI(job) {
  const value = Number(job.progress || 0);
  const progress = Math.round(value * 100);
  const cancelling = jobCancellationRequested(job);
  elements.jobProgress.style.width = `${progress}%`;
  elements.jobProgress.parentElement?.setAttribute("aria-valuenow", String(progress));
  elements.jobMessage.textContent = cancelling
    ? t("cancelling")
    : String(job.message || "").trim() || (job.kind === "model_install"
    ? t("preparingAI")
    : value < .58 ? t("taskListen") : value < .70 ? t("taskStory") : value < .86 ? t("taskSync") : t("taskDraft"));
  const items = $$(".analysis-checks li");
  items.forEach((item, index) => {
    const threshold = Number(item.dataset.threshold);
    const nextThreshold = index + 1 < items.length ? Number(items[index + 1].dataset.threshold) : 1.01;
    item.classList.toggle("done", job.kind !== "model_install" && value >= nextThreshold);
    item.classList.toggle("active", !cancelling && (job.kind === "model_install" ? index === 0 : value >= threshold && value < nextThreshold));
  });
  renderActiveJobBar(job);
}

async function requestJobCancellation(jobId) {
  if (!jobId) return null;
  const alreadyRequested = state.cancelRequestedJobs.has(jobId);
  state.cancelRequestedJobs.add(jobId);
  renderActiveJobBar();
  try {
    const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}" });
    renderActiveJobBar(payload?.job || null);
    if (!alreadyRequested && payload?.accepted !== false) toast(t("cancelAccepted"), "success", 2600);
    return payload;
  } catch (error) {
    if (!alreadyRequested) state.cancelRequestedJobs.delete(jobId);
    renderActiveJobBar();
    toast(`${t("cancelFailed")}: ${error.message}`);
    throw error;
  }
}

async function cancelActiveJob() {
  if (activeUploadsForProject().length) {
    cancelUpload();
    return;
  }
  if (state.activeJob) {
    await requestJobCancellation(state.activeJob).catch(() => {});
    return;
  }
  const pendingStart = [...state.jobStartLocks].some((item) => !String(item).startsWith("recover:"));
  if (!pendingStart) return;
  state.cancelBeforeStart = true;
  renderActiveJobBar();
  toast(t("cancelQueued"), "success", 2600);
}

function renderDraft() {
  state.mediaStudio?.render();
  const draft = editorProject().draft;
  elements.draftTitle.textContent = draft.title || state.project.name;
  elements.draftSummary.textContent = draft.summary || "";
  const hierarchy = state.project.analysis?.story_hierarchy;
  const engineLabel = draft.engine === "ollama_hierarchical_story"
    ? `Story AI · ${hierarchy?.model || state.system?.models?.editor_model || "local model"}`
    : draft.engine === "deterministic_story_fallback"
      ? uiCopy("עריכת גיבוי בטוחה", "Safe fallback edit")
      : draft.engine === "audio_visual_highlights"
        ? uiCopy("היילייטים מסאונד ותמונה", "Audio + visual highlights")
        : draft.engine === "audio_cleanup" ? uiCopy("ניקוי סאונד מקומי", "Local audio cleanup") : String(draft.engine || "Local edit").replaceAll("_", " ");
  const styleLabel = localizedStyleValue(editStyleById(draft.edit_style)?.name);
  elements.draftEngineBadge.textContent = styleLabel && draft.edit_style !== "smart" ? `${styleLabel} · ${engineLabel}` : engineLabel;
  elements.beforeDuration.textContent = formatTime(draft.source_duration);
  elements.afterDuration.textContent = formatTime(draft.output_duration);
  updateStudioStatus();
  const previewAspect = state.project.settings?.aspect || draft.aspect;
  elements.previewStage.dataset.aspect = previewAspect === "source" ? sourceAspect() : previewAspect;
  setupPreviewSources();
  renderDecisions();
  renderDraftWarning();
  renderReelCandidates();
  renderTranscript();
  state.timeline.setProject(editorProject());
  renderCameraDetection();
  renderSourceMixer();
  seekPreview(firstKeptTime());
}

function renderReelCandidates() {
  if (!elements.reelCandidates || !elements.reelCandidateList) return;
  const draft = state.project?.draft;
  const candidates = Array.isArray(draft?.reel_candidates) ? draft.reel_candidates : [];
  elements.reelCandidates.hidden = candidates.length < 2;
  elements.reelCandidateList.replaceChildren();
  if (candidates.length < 2) return;
  elements.reelCandidatesTitle.textContent = uiCopy("כמה עריכות מאותו ניתוח", "Several edits from one analysis");
  const labels = {
    director_pick: uiCopy("בחירת ה־Director", "Director's pick"),
    focused_moment: uiCopy("רגע ממוקד", "Focused moment"),
    alternate_highlight: uiCopy("היילייט חלופי", "Alternate highlight"),
  };
  const activeId = String(draft.active_reel_candidate || "director_pick");
  for (const candidate of candidates) {
    const id = String(candidate.id || "");
    if (!id) continue;
    const active = id === activeId;
    const card = document.createElement("article");
    card.className = `reel-candidate${active ? " active" : ""}`;
    const head = document.createElement("div");
    const rank = document.createElement("i");
    rank.textContent = `0${Number(candidate.rank || 1)}`.slice(-2);
    const title = document.createElement("span");
    const strong = document.createElement("b");
    strong.textContent = labels[candidate.kind] || uiCopy("חלופת Reel", "Reel option");
    const meta = document.createElement("small");
    meta.textContent = `${formatTime(Number(candidate.output_duration || 0))} · ${Number(candidate.score || 0)} ${uiCopy("ציון עריכתי", "editorial score")}`;
    title.append(strong, meta);
    head.append(rank, title);
    const preview = document.createElement("p");
    preview.dir = "auto";
    preview.textContent = String(candidate.preview || uiCopy("חלופה שנבנתה מה־Story Beats שכבר נותחו.", "Built from the Story Beats already analyzed.")).slice(0, 180);
    const button = document.createElement("button");
    button.type = "button";
    button.className = active ? "button ghost compact" : "button primary compact";
    button.dataset.candidateId = id;
    button.disabled = active || state.manualEditBusy || foregroundBusy();
    button.textContent = active ? uiCopy("פעיל עכשיו", "Currently active") : uiCopy("טען עריכה", "Load edit");
    card.append(head, preview, button);
    elements.reelCandidateList.append(card);
  }
  renderDraftActions();
}

function renderDraftActions() {
  const draft = state.project?.draft;
  const dirty = state.draftDirtyReasons.size > 0;
  const disabled = !draft || foregroundBusy() || dirty;
  $$("[data-open-studio-tab]").forEach((button) => { button.disabled = !draft || foregroundBusy(); });
  $$(".refine-grid button").forEach((button) => {
    button.hidden = button.dataset.command === "new_variation" && !canVaryDraft();
    button.disabled = disabled;
    button.title = dirty ? t("rebuildBeforeRefine") : "";
  });
  $$("button[data-candidate-id]", elements.reelCandidateList || document).forEach((button) => {
    button.disabled = disabled || button.dataset.candidateId === String(draft?.active_reel_candidate || "director_pick");
    button.title = dirty ? t("rebuildBeforeRefine") : "";
  });
}

function canVaryDraft() {
  return state.project?.draft?.goal === "short" && (state.project.settings?.goal || "short") === "short";
}

function renderDraftWarning() {
  if (!elements.draftWarning) return;
  const engine = state.project?.draft?.engine;
  const audioHighlights = engine === "audio_visual_highlights";
  const fallback = engine === "deterministic_story_fallback";
  const limitedHighlights = (state.project?.analysis?.warnings || []).some((warning) => warning.type === "limited_highlight_evidence");
  const reviewWarnings = (state.project?.draft?.quality_review?.warnings || [])
    .map((warning) => warning?.message).filter((message) => typeof message === "string" && message);
  elements.draftWarning.hidden = !audioHighlights && !fallback && !limitedHighlights && !reviewWarnings.length;
  elements.draftWarningText.textContent = [
    audioHighlights ? t("audioHighlightWarning") : fallback ? t("storyFallbackWarning") : "",
    limitedHighlights ? t("limitedHighlightWarning") : "",
    ...reviewWarnings,
  ].filter(Boolean).join(" ");
}

function sourceAspect() {
  const source = state.project?.sources?.A;
  if (!source) return "16:9";
  const ratio = source.width / source.height;
  return ratio > 1.2 ? "16:9" : ratio < .8 ? "9:16" : "1:1";
}

function renderDecisions() {
  const decisions = [...(state.project?.draft?.decisions || [])]
    .filter((decision) => decision?.type !== "smart_layout" || embeddedLayoutConfirmed());
  const audioProfile = state.project?.draft?.audio_profile;
  if (audioProfile?.speech_reference_dbfs != null) {
    decisions.unshift({ type: "audio_profile", noise: audioProfile.noise_floor_dbfs, speech: audioProfile.speech_reference_dbfs });
  }
  elements.decisionCount.textContent = String(decisions.length);
  elements.decisionList.innerHTML = "";
  for (const decision of decisions) {
    const item = document.createElement("div");
    item.className = "decision-item";
    const label = decision.type === "story_selection" && state.project?.draft?.engine === "audio_visual_highlights"
      ? t("decision_audio_highlights") : t(`decision_${decision.type}`);
    let value = "";
    if (decision.type === "duration") value = `${formatTime(decision.before)} → ${formatTime(decision.after)}`;
    else if (decision.type === "sync") value = `${Number(decision.offset).toFixed(2)}s`;
    else if (decision.type === "audio_profile") value = `${t("noiseFloor")} ${Number(decision.noise).toFixed(1)} dB · ${t("speechLevel")} ${Number(decision.speech).toFixed(1)} dB`;
    else value = `${decision.count || 0} ${t("occurrences")}`;
    item.innerHTML = `<i></i><strong></strong><span></span>`;
    $("strong", item).textContent = label;
    $("span", item).textContent = value;
    elements.decisionList.append(item);
  }
}

function sourceMixerSettings() {
  const stored = state.project?.manual?.source_mixer || {};
  const desired = state.sourceMixerDesired?.projectId === state.project?.id ? state.sourceMixerDesired.payload : null;
  const raw = desired ? { ...stored, ...desired } : stored;
  if (desired?.default_layout == null && Object.hasOwn(desired || {}, "default_layout")) delete raw.default_layout;
  if (desired?.sync_offset == null && Object.hasOwn(desired || {}, "sync_offset")) delete raw.sync_offset;
  let screenSlot = String(raw.screen_slot || "A").toUpperCase();
  let cameraSlot = String(raw.camera_slot || (screenSlot === "A" ? "B" : "A")).toUpperCase();
  if (new Set([screenSlot, cameraSlot]).size !== 2 || ![screenSlot, cameraSlot].every((slot) => ["A", "B"].includes(slot))) {
    screenSlot = "A"; cameraSlot = "B";
  }
  const vertical = (state.project?.settings?.aspect || "9:16") === "9:16";
  const firstSlot = ["A", "B"].includes(String(raw.first_slot || "").toUpperCase()) ? String(raw.first_slot).toUpperCase() : vertical ? cameraSlot : "A";
  const primaryRole = ["screen", "camera"].includes(raw.primary_role) ? raw.primary_role : "screen";
  let audioSlot = ["A", "B"].includes(String(raw.audio_slot || "").toUpperCase()) ? String(raw.audio_slot).toUpperCase() : "A";
  if (!state.project?.sources?.[audioSlot]?.has_audio) {
    audioSlot = state.project?.sources?.A?.has_audio ? "A" : state.project?.sources?.B?.has_audio ? "B" : "A";
  }
  const automaticOffset = Number(state.project?.analysis?.sync?.offset || 0);
  const manualOffset = raw.sync_offset == null ? NaN : Number(raw.sync_offset);
  const hasManualSync = Number.isFinite(manualOffset) && Math.abs(manualOffset) <= 600;
  const syncOffset = hasManualSync ? manualOffset : Number.isFinite(automaticOffset) ? automaticOffset : 0;
  const allowedLayouts = ["auto", "screen", "camera", "stacked", "side_by_side", "pip"];
  const rawDefaultLayout = String(raw.default_layout || "").toLowerCase();
  const defaultLayoutExplicit = Object.hasOwn(raw, "default_layout") && allowedLayouts.includes(rawDefaultLayout);
  const defaultLayout = defaultLayoutExplicit ? rawDefaultLayout : "auto";
  const stackFit = ["cover", "contain"].includes(raw.stack_fit) ? raw.stack_fit : vertical ? "cover" : "contain";
  return { screenSlot, cameraSlot, firstSlot, primaryRole, audioSlot, syncOffset, hasManualSync, defaultLayout, defaultLayoutExplicit, stackFit };
}

function sourceMixerLayoutFromSetting(layout, mixer = sourceMixerSettings()) {
  if (layout === mixer.screenSlot) return "screen";
  if (layout === mixer.cameraSlot) return "camera";
  const settings = state.project?.settings || {};
  if ((!layout || layout === "auto") && !mixer.defaultLayoutExplicit && state.project?.sources?.B
      && (settings.goal || "short") === "short" && (settings.aspect || "9:16") === "9:16"
      && (settings.layout || "auto") === "auto") return "stacked";
  return ["auto", "screen", "camera", "stacked", "side_by_side", "pip"].includes(layout) ? layout : "auto";
}

function hydrateSourceMixerLayout() {
  const mixer = sourceMixerSettings();
  const pending = state.sourceMixerLayoutRequest;
  if (pending && pending.projectId === state.project?.id) {
    state.sourceMixerLayout = pending.layout;
    return;
  }
  const plan = editorProject()?.draft?.camera_plan;
  if (Array.isArray(plan) && plan.length) {
    const range = state.manualSelection || { start: 0, end: editorDuration() };
    const layouts = new Set(plan.filter((scene) => Number(scene.end) > range.start && Number(scene.start) < range.end)
      .map((scene) => sourceMixerLayoutFromSetting(scene.camera, mixer)));
    // The default is a preference for the next AI build. It must not override
    // the actual draft composition after a layout edit, undo or project reload.
    state.sourceMixerLayout = layouts.size === 1 ? [...layouts][0] : "auto";
    state.sourceMixerLayoutTouched = Boolean(state.project.manual?.camera_overrides?.length);
    return;
  }
  state.sourceMixerLayoutTouched = mixer.defaultLayoutExplicit;
  if (mixer.defaultLayoutExplicit) state.sourceMixerLayout = mixer.defaultLayout;
  else if (!state.project?.draft) state.sourceMixerLayout = sourceMixerLayoutFromSetting(elements.layoutSelect.value, mixer);
}

function sourceSlotForRole(role) {
  const mixer = sourceMixerSettings();
  return role === "camera" ? mixer.cameraSlot : mixer.screenSlot;
}

function sourceMixerControlBusy() {
  return Boolean(
    state.activeJob
    || state.manualEditBusy
    || state.sourceSyncPending
    || (state.sourceMixerLayoutRequest && state.sourceMixerLayoutRequest.projectId === state.project?.id)
    || activeUploadsForProject().length
    || state.jobStartLocks.size,
  );
}

function updateCompositionVideo(video, source) {
  if (!video) return;
  const mediaUrl = sourceMediaUrl(source);
  if (video.dataset.sourceKey === mediaUrl) return;
  if (!mediaUrl) {
    video.removeAttribute("src");
    video.dataset.sourceKey = "";
    video.load();
    return;
  }
  video.src = mediaUrl;
  video.dataset.sourceKey = mediaUrl;
  video.load();
}

function editedClipCrop(slot, time = previewPlaybackTime()) {
  if (!state.project?.editor_sequence || previewUsesSourceTime()) return null;
  return trackAt(editorProject(), slot, time)?.clip?.crop || null;
}

function previewCropForLayout(slot, layout, mixer, override = null, time = previewPlaybackTime()) {
  const clipCrop = editedClipCrop(slot, time);
  const primarySlot = mixer.primaryRole === "camera" ? mixer.cameraSlot : mixer.screenSlot;
  const fitted = layout === "auto" || layout === "side_by_side"
    || (layout === "stacked" && mixer.stackFit !== "cover")
    || (layout === "pip" && slot !== primarySlot);
  // Export's fit filter keeps the complete frame centred, without applying
  // crop/zoom. Keep stored framing intact, but do not preview a crop that will
  // disappear from the rendered video when Fit entire source is selected.
  if (fitted && !(state.project?.editor_sequence && override) && !clipCrop) return { x: .5, y: .5, zoom: 1 };
  const crop = override || clipCrop || state.project?.manual?.crop?.[slot] || {};
  const finite = (value, fallback) => value == null || !Number.isFinite(Number(value)) ? fallback : Number(value);
  return {
    x: Math.max(0, Math.min(1, finite(crop.x, .5))),
    y: Math.max(0, Math.min(1, finite(crop.y, .5))),
    zoom: Math.max(1, Math.min(3, finite(crop.zoom, 1))),
  };
}

function applyCompositionCrop(video, slot, layout, mixer, override = null, time = previewPlaybackTime()) {
  if (!video) return;
  const crop = previewCropForLayout(slot, layout, mixer, override, time);
  video.style.objectFit = editedClipCrop(slot, time) || (state.project?.editor_sequence && override) ? "cover" : "";
  const position = `${crop.x * 100}% ${crop.y * 100}%`;
  video.style.objectPosition = position;
  video.style.transformOrigin = position;
  video.style.transform = `scale(${crop.zoom})`;
}

function previewExportDimensions() {
  // Keep the overlay geometry in output pixels, matching render._dimensions.
  // A constant CSS percentage for the 32px gap changes the actual composition
  // between portrait/landscape and 720p/1080p exports.
  const aspect = elements.aspectSelect?.value || state.project?.settings?.aspect || "9:16";
  const resolution = elements.resolutionSelect?.value || state.project?.settings?.resolution || "1080";
  const dimensions = {
    "9:16": { "720": [720, 1280], "1080": [1080, 1920], "1440": [1440,2560], "2160": [2160,3840] },
    "16:9": { "720": [1280, 720], "1080": [1920, 1080], "1440": [2560,1440], "2160": [3840,2160] },
    "1:1": { "720": [720, 720], "1080": [1080, 1080], "1440": [1440,1440], "2160": [2160,2160] },
    "4:5": { "720": [720, 900], "1080": [1080, 1350], "1440": [1440,1800], "2160": [2160,2700] },
  };
  if (aspect === "source") {
    const width = Math.trunc(Number(state.project?.sources?.A?.width));
    const height = Math.trunc(Number(state.project?.sources?.A?.height));
    if (Number.isFinite(width) && width > 0 && Number.isFinite(height) && height > 0) {
      const scale = Math.min(1, ({"720":1280,"1080":1920,"1440":2560,"2160":3840}[resolution] || 1920) / Math.max(width, height));
      return [Math.max(2, Math.floor(width * scale / 2) * 2), Math.max(2, Math.floor(height * scale / 2) * 2)];
    }
  }
  return dimensions[aspect]?.[resolution] || dimensions["9:16"]["1080"];
}

function applyPreviewPipGeometry(container) {
  if (!container) return;
  const [width, height] = previewExportDimensions();
  const insetWidth = Math.max(160, Math.floor(width * .34 / 2) * 2);
  const insetHeight = Math.max(90, Math.floor(height * .28 / 2) * 2);
  container.style.setProperty("--pip-width", `${100 * insetWidth / width}%`);
  container.style.setProperty("--pip-height", `${100 * insetHeight / height}%`);
  container.style.setProperty("--pip-right", `${3200 / width}%`);
  container.style.setProperty("--pip-bottom", `${3200 / height}%`);
}

function renderSourceCompositionPreview(mixer, cropOverride = null) {
  const canvas = elements.sourceCompositionCanvas;
  if (!canvas) return;
  const sources = state.project?.sources || {};
  updateCompositionVideo(elements.sourceCompositionA, sources.A);
  updateCompositionVideo(elements.sourceCompositionB, sources.B);
  const roleFor = (slot) => slot === mixer.screenSlot ? uiCopy("מסך", "SCREEN") : uiCopy("מצלמה", "CAMERA");
  elements.sourceCompositionRoleA.textContent = `A · ${roleFor("A")}`;
  elements.sourceCompositionRoleB.textContent = `B · ${roleFor("B")}`;
  elements.sourceCompositionNameA.textContent = sources.A?.name || "A";
  elements.sourceCompositionNameB.textContent = sources.B?.name || "B";

  const selectedLayout = state.sourceMixerLayout || "auto";
  const visualLayout = selectedLayout === "auto" ? "auto" : selectedLayout;
  canvas.className = `source-composition-canvas composition-${visualLayout} first-slot-${mixer.firstSlot.toLowerCase()}`;
  const primarySlot = mixer.primaryRole === "camera" ? mixer.cameraSlot : mixer.screenSlot;
  canvas.classList.add(`primary-slot-${primarySlot.toLowerCase()}`);
  const firstShare = mixer.firstSlot === primarySlot ? 70 : 30;
  canvas.style.setProperty("--composition-first-share", `${firstShare}%`);
  canvas.dataset.stackFit = mixer.stackFit;
  // A short, unconstrained landscape box made the Reels stack look flattened.
  // Its canvas must use the output ratio, not the inspector's available width.
  const selectedAspect = elements.aspectSelect?.value || state.project?.settings?.aspect || state.project?.draft?.aspect || "16:9";
  const aspect = selectedAspect === "source" ? sourceAspect() : selectedAspect;
  const ratio = { "9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1, "4:5": 4 / 5 }[aspect] || 16 / 9;
  canvas.dataset.aspect = aspect;
  canvas.style.aspectRatio = aspectCss(aspect);
  canvas.style.setProperty("--composition-ratio", String(ratio));
  applyPreviewPipGeometry(canvas);
  for (const slot of ["A", "B"]) {
    const video = slot === "A" ? elements.sourceCompositionA : elements.sourceCompositionB;
    applyCompositionCrop(video, slot, visualLayout, mixer, cropOverride?.slot === slot ? cropOverride.crop : null);
  }

  const slotA = $('[data-source-preview-slot="A"]', canvas);
  const slotB = $('[data-source-preview-slot="B"]', canvas);
  slotA.hidden = false;
  slotB.hidden = false;
  if (selectedLayout === "screen") (mixer.screenSlot === "A" ? slotB : slotA).hidden = true;
  if (selectedLayout === "camera") (mixer.cameraSlot === "A" ? slotB : slotA).hidden = true;
  const labels = {
    auto: uiCopy("AI · שני המקורות זמינים", "AI · both sources available"),
    screen: uiCopy("מסך בלבד", "Screen only"), camera: uiCopy("מצלמה בלבד", "Camera only"),
    stacked: `${aspect} · ${mixer.firstSlot} on top ${firstShare}% · ${mixer.stackFit === "cover" ? "Fill (crop edges)" : "Fit (allow bars)"}`,
    side_by_side: uiCopy("הראשון משמאל", "First source on the left"),
    pip: uiCopy("המקור הראשי ברקע", "Primary source in the background"),
  };
  elements.sourceCompositionMode.textContent = labels[selectedLayout] || selectedLayout;
  elements.firstSlotName.textContent = uiCopy(
    `${mixer.firstSlot} למעלה ב־Stack · ${mixer.firstSlot} משמאל ב־Split`,
    `${mixer.firstSlot} on top in Stack · ${mixer.firstSlot} on the left in Split`,
  );
}

function renderSourceMixer() {
  if (!elements.sourceMixer || !state.project) return;
  renderRangeEditors();
  const sourceA = state.project.sources?.A;
  const sourceB = state.project.sources?.B;
  const hasTwoSources = Boolean(sourceA && sourceB);
  placeSourceMixer(Boolean(sourceA));
  const mixer = sourceMixerSettings();
  const busy = sourceMixerControlBusy();
  renderSourceIdentity(mixer, busy);
  elements.sourceMixerTitle.textContent = hasTwoSources
    ? uiCopy("שליטה במקורות A/B", "Screen + camera")
    : sourceA
      ? uiCopy("שליטה במקור ובמצלמה", "Your recording")
      : uiCopy("שליטה במקורות", "Source control");
  elements.sourceMixerHelp.textContent = hasTwoSources && state.project.draft
    ? uiCopy("לחיצה על פריסה שומרת אותה מיד לטווח המסומן או לכל העריכה.", "Choosing a layout saves it immediately to the selection or the entire edit.")
    : hasTwoSources
      ? uiCopy("סדרו את המקורות ובחרו פריסה לפני שה־Director מתחיל.", "Arrange the sources and choose a layout before Director starts.")
      : uiCopy("בקובץ אחד אפשר לסמן מצלמה פנימית; בשני קבצים אפשר לשלוט ב־A/B בנפרד.", "With one file, mark a baked-in camera; with two files, control A/B separately.");
  elements.sourceMixerEmpty.hidden = Boolean(sourceA);
  renderEmbeddedCameraEditor();
  elements.sourceMixerBody.hidden = !hasTwoSources;
  if (!hasTwoSources) {
    elements.sourceMixerStatus.textContent = !sourceA
      ? uiCopy("ממתין למקור A", "Waiting for source A")
      : embeddedCameraIsActive()
        ? uiCopy("מצלמה פנימית מאושרת", "Embedded camera confirmed")
        : uiCopy("מקור יחיד — אין שכפול אוטומטי", "One source — no automatic duplication");
    renderSceneLayoutEditor(false);
    return;
  }

  elements.screenSourceSelect.value = mixer.screenSlot;
  elements.cameraSourceSelect.value = mixer.cameraSlot;
  elements.firstSlotSelect.value = mixer.firstSlot;
  elements.primaryRoleSelect.value = mixer.primaryRole;
  elements.audioSourceSelect.value = mixer.audioSlot;
  elements.stackFitSelect.value = mixer.stackFit;
  elements.stackFitSelect.disabled = busy;
  elements.creatorFramePreset.disabled = busy || rangeInputPending("layout");
  if (elements.swapSourceOrder) {
    elements.swapSourceOrder.disabled = busy;
    elements.swapSourceOrder.textContent = state.sourceMixerLayout === "side_by_side" ? "Swap left / right · whole edit" : "Swap top / bottom · whole edit";
  }
  elements.sourceSyncOffset.value = String(Math.round(mixer.syncOffset * 1000) / 1000);
  elements.sourceSyncStatus.textContent = mixer.hasManualSync
    ? uiCopy("תיקון ידני פעיל", "Manual sync override")
    : uiCopy(`אוטומטי: ${mixer.syncOffset.toFixed(2)} שנ׳`, `Automatic: ${mixer.syncOffset.toFixed(2)}s`);
  elements.screenSourceName.textContent = state.project.sources[mixer.screenSlot]?.name || mixer.screenSlot;
  elements.cameraSourceName.textContent = state.project.sources[mixer.cameraSlot]?.name || mixer.cameraSlot;
  for (const control of [elements.screenSourceSelect, elements.cameraSourceSelect]) {
    for (const option of control.options) option.textContent = `${option.value} · ${state.project.sources?.[option.value]?.name || "Source"}`;
  }
  for (const option of elements.firstSlotSelect.options) {
    option.textContent = `${option.value} · ${state.project.sources?.[option.value]?.name || uiCopy("מקור", "Source")}`;
  }
  for (const option of elements.audioSourceSelect.options) {
    const source = state.project.sources?.[option.value];
    option.disabled = !source?.has_audio;
    option.textContent = source?.has_audio
      ? `${option.value} · ${source.name || uiCopy("מקור", "Source")}`
      : `${option.value} · ${uiCopy("ללא קול", "No audio")}`;
  }
  elements.primaryRoleSelect.options[0].textContent = uiCopy("צילום המסך", "Screen recording");
  elements.primaryRoleSelect.options[1].textContent = uiCopy("המצלמה", "Camera");
  renderSourceCompositionPreview(mixer);
  const layoutLabels = {
    auto: state.project.editor_sequence ? "Source defaults" : uiCopy("בחירת AI", "AI choice"), screen: uiCopy("מסך בלבד", "Screen only"),
    camera: uiCopy("מצלמה בלבד", "Camera only"), stacked: uiCopy("אחד מעל השני", "Stacked"),
    side_by_side: uiCopy("זה לצד זה", "Side by side"), pip: uiCopy("חלון על המסך", "Picture in picture"),
  };

  $$('button[data-layout]', elements.sourceLayoutChoices).forEach((button) => {
    const active = button.dataset.layout === state.sourceMixerLayout;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
    button.disabled = busy || rangeInputPending("layout") || Boolean(state.project.draft && state.manualSelection && !layoutRangeEditable());
    const label = $("span", button);
    if (label) label.textContent = layoutLabels[button.dataset.layout] || button.dataset.layout;
  });
  const selection = state.manualSelection;
  elements.applyLayoutSelection.disabled = busy || rangeInputPending("layout") || !state.project.draft || !selection || !layoutRangeEditable();
  elements.applyLayoutAll.disabled = busy || rangeInputPending("layout") || !state.project.draft;
  elements.resetSourceLayout.disabled = busy || !mixer.defaultLayoutExplicit;
  elements.resetSourceLayout.textContent = "Reset next-build layout default";
  elements.swapSourceRoles.disabled = busy;
  [elements.screenSourceSelect, elements.cameraSourceSelect, elements.primaryRoleSelect, elements.audioSourceSelect, elements.firstSlotSelect, elements.sourceSyncOffset]
    .forEach((control) => { control.disabled = busy; });
  elements.resetSourceSync.disabled = busy || !mixer.hasManualSync;
  if (Object.hasOwn(state.project?.manual?.source_tracks || {}, "B")) {
    for (const control of [elements.sourceSyncOffset, elements.resetSourceSync, elements.sourceBEarlier, elements.sourceBLater]) if (control) control.disabled = true;
    elements.sourceSyncStatus.textContent = "B has independent clips. Move B clips on the timeline to adjust their sync without moving A.";
  }
  elements.applyLayoutSelection.textContent = selection
    ? `Apply to ${formatSourceTime(selection.start)}–${formatSourceTime(selection.end)}`
    : uiCopy("החל על הבחירה", "Apply to selection");
  elements.applyLayoutAll.textContent = uiCopy("החל על כל הסרטון", "Apply to entire edit");
  elements.sourceMixerRange.textContent = selection
    ? uiCopy("לחיצה על פריסה תחיל ותשמור אותה מיד בטווח המסומן.", "Choosing a layout applies and saves it immediately to the selected range.")
    : uiCopy("לחיצה על פריסה תחיל ותשמור אותה מיד לכל הסרטון.", "Choosing a layout applies and saves it immediately to the entire edit.");
  if (selection && !layoutRangeEditable()) elements.sourceMixerRange.textContent = `Select at least ${minimumEditLength().toFixed(3)} seconds inside the edit timeline.`;
  const overrideCount = Array.isArray(state.project.manual?.camera_overrides) ? state.project.manual.camera_overrides.length : 0;
  elements.sourceMixerStatus.textContent = state.sourceMixerSavePending
    ? uiCopy("שומר את סדר המקורות…", "Saving source order…")
    : state.sourceMixerCommitScope
      ? state.sourceMixerCommitScope === "selection"
        ? uiCopy("הפריסה נשמרה לטווח המסומן", "Layout saved to the selected range")
        : uiCopy("הפריסה נשמרה לכל העריכה", "Layout saved to the entire edit")
    : !state.project.draft && mixer.defaultLayoutExplicit
    ? state.sourceMixerLayout === "auto"
      ? uiCopy("בחירת AI נשמרה ותשמש את ה־Director", "Saved AI choice will be used by Director")
      : uiCopy("הפריסה הידנית תשמש את ה־Director", "Manual layout will be used by Director")
    : overrideCount
      ? uiCopy(`${overrideCount} החלטות ידניות פעילות`, `${overrideCount} manual layout override${overrideCount === 1 ? "" : "s"}`)
      : mixer.defaultLayoutExplicit
        ? uiCopy("ברירת מחדל ידנית שמורה לבנייה הבאה", "Manual default saved for the next build")
      : uiCopy("שינויי פריסה נשמרים אוטומטית", "Layout changes save automatically");
  renderSceneLayoutEditor(true);
}

function renderSceneLayoutEditor(hasTwoSources) {
  if (!elements.sceneLayoutEditor || !elements.sceneLayoutList) return;
  const plan = editorProject()?.draft?.camera_plan || [];
  const visible = Boolean(hasTwoSources && plan.length);
  elements.sceneLayoutEditor.hidden = !visible;
  elements.sceneLayoutList.replaceChildren();
  if (!visible) return;

  const sequence = Boolean(state.project?.editor_sequence);
  const overrides = !sequence && Array.isArray(state.project?.manual?.camera_overrides) ? state.project.manual.camera_overrides : [];
  const busy = state.manualEditBusy || foregroundBusy();
  const labels = {
    auto: uiCopy("בחירת AI", "AI choice"), screen: uiCopy("מסך בלבד", "Screen only"),
    camera: uiCopy("מצלמה בלבד", "Camera only"), stacked: uiCopy("אחד מעל השני", "Stacked"),
    side_by_side: uiCopy("זה לצד זה", "Side by side"), pip: uiCopy("חלון על המסך", "Picture in picture"),
  };
  const mixer = sourceMixerSettings();
  const fragment = document.createDocumentFragment();
  plan.slice(0, 120).forEach((scene, index) => {
    const start = Number(scene.start);
    const end = Number(scene.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return;
    const midpoint = (start + end) / 2;
    const manual = overrides.find((item) => midpoint >= Number(item.start) && midpoint < Number(item.end));
    const current = sourceMixerLayoutFromSetting(String(scene.camera || "A"), mixer);
    const row = document.createElement("div");
    const selected = state.manualSelection && Math.abs(start - state.manualSelection.start) < .001 && Math.abs(end - state.manualSelection.end) < .001;
    row.className = `scene-layout-row${manual ? " manual" : ""}${selected ? " selected" : ""}`;

    const jump = document.createElement("button");
    jump.type = "button";
    jump.className = "scene-layout-jump";
    jump.dataset.sceneStart = String(start);
    jump.dataset.sceneEnd = String(end);
    jump.setAttribute("aria-pressed", String(Boolean(selected)));
    const number = document.createElement("i");
    number.textContent = String(index + 1).padStart(2, "0");
    const timing = document.createElement("span");
    timing.innerHTML = `<b>${formatSourceTime(start)}–${formatSourceTime(end)}</b><small></small>`;
    $("small", timing).textContent = sequence && state.project.editor_sequence.active ? "Sequence layout" : manual ? uiCopy("בחירה ידנית", "Manual decision") : uiCopy("בחירת AI", "AI decision");
    jump.append(number, timing);

    const select = document.createElement("select");
    select.dataset.sceneStart = String(start);
    select.dataset.sceneEnd = String(end);
    select.setAttribute("aria-label", uiCopy(`פריסה לסצנה ${index + 1}`, `Layout for scene ${index + 1}`));
    for (const value of ["auto", "screen", "camera", "stacked", "side_by_side", "pip"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = sequence && value === "auto" ? "Source defaults" : labels[value];
      select.append(option);
    }
    select.value = manual ? String(manual.layout) : current;
    select.disabled = busy;
    row.append(jump, select);
    fragment.append(row);
  });
  elements.sceneLayoutList.append(fragment);
  const manualCount = overrides.length;
  elements.sceneLayoutSummary.textContent = sequence ? `${plan.length} layout blocks · Edit timeline` : uiCopy(
    `${plan.length} קטעים · ${manualCount} ידניים`,
    `${plan.length} scenes · ${manualCount} manual`,
  );
  if (plan.length > 120) elements.sceneLayoutSummary.textContent += " · first 120 listed; all blocks are on the timeline";
}

function renderSourceIdentity(mixer, busy) {
  if (!elements.sourceIdentityCards) return;
  const sources = state.project?.sources || {};
  const signature = JSON.stringify([sources.A?.name, sources.A?.duration, sources.B?.name, sources.B?.duration, mixer.screenSlot, mixer.audioSlot]);
  if (elements.sourceIdentityCards.dataset.signature !== signature) {
    elements.sourceIdentityCards.dataset.signature = signature;
    elements.sourceIdentityCards.replaceChildren();
    for (const slot of ["A", "B"]) {
      const source = sources[slot];
      if (!source) continue;
      const card = document.createElement("div");
      card.className = "source-identity-card";
      const badge = document.createElement("b"), name = document.createElement("strong"), detail = document.createElement("small");
      badge.textContent = slot;
      name.textContent = source.name || `Source ${slot}`;
      detail.textContent = `${slot === mixer.screenSlot ? "Screen" : "Camera"} · ${formatTime(Number(source.duration || 0))}${slot === mixer.audioSlot && source.has_audio ? " · Audio used" : ""}`;
      card.append(badge, name, detail);
      elements.sourceIdentityCards.append(card);
    }
  }
  for (const control of [elements.sourceBEarlier, elements.sourceBLater]) if (control) control.disabled = busy || !sources.B;
  if (!elements.sourceBCoverage || !sources.B) return;
  if (Object.hasOwn(state.project?.manual?.source_tracks || {}, "B")) {
    elements.sourceBCoverage.textContent = `B uses ${trackClips(state.project, "B").length} independent clips. See the B track for positions and gaps. B audio is silent in gaps when selected.`;
    elements.sourceBCoverage.dataset.warning = "false";
    return;
  }
  const coverage = sourceBCoverage(sources, mixer.syncOffset);
  elements.sourceBCoverage.textContent = coverage.end > coverage.start
    ? `B is available at ${formatSourceTime(coverage.start)}–${formatSourceTime(coverage.end)} on A's timeline.${coverage.full ? "" : " Outside this range, the edit falls back to A; B audio may be silent."}`
    : "B does not overlap A at this offset. Adjust sync; the edit cannot show B here.";
  elements.sourceBCoverage.dataset.warning = String(!coverage.full);
}

function sourceBCoverage(sources, offset) {
  const duration = Math.max(0, Number(sources.A?.duration) || 0);
  const bDuration = Number(sources.B?.video_duration) > 0 ? Number(sources.B.video_duration) : Math.max(0, Number(sources.B?.duration) || 0);
  const start = Math.max(0, Math.min(duration, offset)), end = Math.max(0, Math.min(duration, offset + bDuration));
  return { start, end, full: duration > 0 && start === 0 && end >= duration };
}

function nudgeSourceSync(direction) {
  if (!state.project?.sources?.B || sourceMixerControlBusy()) return;
  const fps = Number(state.project.sources.A?.fps);
  const frame = 1 / (Number.isFinite(fps) && fps > 0 ? fps : 30);
  const offset = Math.max(-600, Math.min(600, sourceMixerSettings().syncOffset + direction * frame));
  // Save the precise frame step; rounding the field to milliseconds must not
  // accumulate a drift on 29.97 / 59.94 fps sources.
  pauseAllMedia();
  runUiAction(() => saveSourceMixer({ sync_offset: offset }));
}

function layoutRangeEditable() {
  const range = state.manualSelection;
  return Boolean(range && range.end - range.start >= minimumEditLength() - 1e-6 && editorProject()?.draft?.keep_ranges?.some((kept) => Number(kept.end) > range.start && Number(kept.start) < range.end));
}

function placeSourceMixer(hasSource) {
  const showBeforeDirector = Boolean(hasSource && !state.project?.draft);
  if (showBeforeDirector && elements.setupSourceMixerDock) {
    if (elements.sourceMixer.parentElement !== elements.setupSourceMixerDock) {
      elements.setupSourceMixerDock.appendChild(elements.sourceMixer);
    }
    elements.setupSourceMixerDock.hidden = false;
    return;
  }
  if (elements.studioPanelFraming && elements.sourceMixer.parentElement !== elements.studioPanelFraming) {
    elements.studioPanelFraming.insertBefore(elements.sourceMixer, $(".framing-layout", elements.studioPanelFraming));
  }
  if (elements.setupSourceMixerDock) elements.setupSourceMixerDock.hidden = true;
}

function sourceMixerPayload(extra = {}) {
  const sources = state.project?.sources || {};
  const hasAnyAudio = Boolean(sources.A?.has_audio || sources.B?.has_audio);
  let audioSlot = elements.audioSourceSelect.value;
  if (hasAnyAudio && !sources[audioSlot]?.has_audio) {
    audioSlot = sources.A?.has_audio ? "A" : "B";
    elements.audioSourceSelect.value = audioSlot;
    toast(uiCopy("מקור הקול הוחזר אוטומטית למקור שיש בו קול", "Audio was kept on a source that contains sound"));
  }
  return {
    screen_slot: elements.screenSourceSelect.value,
    camera_slot: elements.cameraSourceSelect.value,
    primary_role: elements.primaryRoleSelect.value,
    audio_slot: audioSlot,
    first_slot: elements.firstSlotSelect.value,
    ...(sourceMixerSettings().stackFit === "cover" ? { stack_fit: "cover" } : {}),
    ...extra,
  };
}

function applyOptimisticSourceMixer(payload) {
  if (!state.project) return;
  const manual = state.project.manual ||= {};
  const current = manual.source_mixer && typeof manual.source_mixer === "object" ? manual.source_mixer : {};
  const next = {
    ...current,
    screen_slot: payload.screen_slot,
    camera_slot: payload.camera_slot,
    primary_role: payload.primary_role,
    audio_slot: payload.audio_slot,
    first_slot: payload.first_slot,
  };
  for (const key of ["default_layout", "sync_offset", "stack_fit"]) {
    if (!Object.hasOwn(payload, key)) continue;
    if (payload[key] == null) delete next[key];
    else next[key] = payload[key];
  }
  manual.source_mixer = next;
}

async function persistSourceMixer(projectId, payload) {
  await flushProjectSaves(projectId);
  const submit = (revision) => api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`, {
    method: "POST",
    body: JSON.stringify({ action: "set_source_mixer", ...payload, expected_revision: revision }),
  });
  const expectedRevision = saveQueueFor(projectId, state.project?.revision).revision;
  try {
    return await submit(expectedRevision);
  } catch (error) {
    if (!isRevisionConflict(error)) throw error;
    const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!latest?.project) throw error;
    rememberProjectRevision(latest.project);
    return submit(saveQueueFor(projectId, latest.project.revision).revision);
  }
}

function saveSourceMixer(extra = {}, { silent = false } = {}) {
  if (!state.project?.sources?.B || sourceMixerControlBusy()) return Promise.resolve(null);
  const projectId = state.project.id;
  const payload = sourceMixerPayload(extra);
  const version = ++state.sourceMixerSaveSequence;
  state.sourceMixerDesired = { projectId, version, payload };
  state.sourceMixerCommitScope = null;
  applyOptimisticSourceMixer(payload);
  state.sourceMixerSavePending += 1;
  renderSourceMixer();
  syncSecondaryPreview(previewPlaybackTime());
  renderReadiness();

  const task = state.sourceMixerSaveTail.catch(() => null).then(async () => {
    try {
      const response = await persistSourceMixer(projectId, payload);
      if (!response?.project) throw new Error("Source Mixer did not return an updated project");
      rememberProjectRevision(response.project);
      if (state.project?.id === projectId) {
        state.project = response.project;
        const desired = state.sourceMixerDesired;
        if (desired?.projectId === projectId && desired.version > version) {
          applyOptimisticSourceMixer(desired.payload);
        } else if (desired?.projectId === projectId && desired.version === version) {
          state.sourceMixerDesired = null;
        }
        refreshSourceMixerTimeline();
        renderSourceMixer();
        syncSecondaryPreview(previewPlaybackTime());
      }
      if (!silent && version === state.sourceMixerSaveSequence) {
        toast(uiCopy("סדר המקורות נשמר", "Source order saved"), "success", 1800);
      }
      return response.project;
    } catch (error) {
      if (state.sourceMixerDesired?.projectId === projectId && state.sourceMixerDesired.version === version) {
        state.sourceMixerDesired = null;
        try {
          const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
          if (state.project?.id === projectId && latest?.project) {
            state.project = latest.project;
            rememberProjectRevision(state.project);
            refreshSourceMixerTimeline();
          }
        } catch (_refreshError) {
          // A later reload will reconcile if the local server was temporarily unavailable.
        }
      }
      renderSourceMixer();
      toast(`${uiCopy("שמירת סדר המקורות נכשלה", "Saving source order failed")}: ${error.message}`);
      return null;
    } finally {
      state.sourceMixerSavePending = Math.max(0, state.sourceMixerSavePending - 1);
      renderReadiness();
      renderSourceMixer();
    }
  });
  state.sourceMixerSaveTail = task.catch(() => null);
  return task;
}

function refreshSourceMixerTimeline() {
  // Roles and sync replace the project snapshot, but not source A's footage.
  // Keep selection, zoom and thumbnails while refreshing the Layout lane.
  if (!state.timeline || state.timeline.project?.id !== state.project?.id) return;
  state.timeline.project = editorProject();
  state.timeline.scheduleDraw();
}

function clearPendingSourceSync() {
  if (state.sourceSyncSaveTimer) clearTimeout(state.sourceSyncSaveTimer);
  state.sourceSyncSaveTimer = null;
  state.sourceSyncPending = null;
  renderReadiness();
}

async function flushPendingSourceSync(projectId = state.project?.id) {
  const pending = state.sourceSyncPending;
  if (!pending || pending.projectId !== projectId) return null;
  if (state.sourceSyncSaveTimer) clearTimeout(state.sourceSyncSaveTimer);
  state.sourceSyncSaveTimer = null;
  state.sourceSyncPending = null;
  renderReadiness();
  return saveSourceMixer({ sync_offset: pending.value });
}

function scheduleSourceSyncSave(immediate) {
  if (state.sourceSyncSaveTimer) clearTimeout(state.sourceSyncSaveTimer);
  state.sourceSyncSaveTimer = null;
  state.sourceSyncPending = null;
  const value = Number(elements.sourceSyncOffset.value);
  if (!Number.isFinite(value) || Math.abs(value) > 600) {
    renderReadiness();
    return;
  }
  const projectId = state.project?.id;
  if (!projectId) return;
  state.sourceSyncPending = { projectId, value };
  renderReadiness();
  if (immediate) {
    flushPendingSourceSync(projectId).catch((error) => toast(error.message));
    return;
  }
  state.sourceSyncSaveTimer = setTimeout(() => {
    flushPendingSourceSync(projectId).catch((error) => toast(error.message));
  }, 450);
}

async function applySourceLayout(scope, { immediate = false } = {}) {
  if (!state.project?.draft || !state.project.sources?.B) return;
  if (rangeInputPending("layout")) return;
  const duration = editorDuration();
  const range = scope === "selection" ? state.manualSelection : { start: 0, end: duration };
  if (!range || range.end - range.start < minimumEditLength() - 1e-6) return;
  if (scope === "selection" && !layoutRangeEditable()) return;
  const request = { projectId: state.project.id, layout: state.sourceMixerLayout, start: range.start, end: range.end };
  let committed = false;
  state.sourceMixerLayoutRequest = request;
  renderSourceMixer();
  syncSecondaryPreview(previewPlaybackTime());
  try {
    // Fit/Fill and role saves are serialized separately. Await them rather
    // than silently dropping this click because applyManualEdit sees Busy.
    if (state.sourceMixerSavePending) await state.sourceMixerSaveTail;
    if (state.project?.id !== request.projectId || state.sourceMixerLayoutRequest !== request) return;
    const updated = await applyManualEdit("set_camera_layout", {
      layout: request.layout, start: request.start, end: request.end,
    });
    if (!updated || state.project?.id !== request.projectId || state.sourceMixerLayoutRequest !== request) return;
    state.sourceMixerLayout = request.layout;
    committed = true;
    state.sourceMixerPreviewLayout = null;
    state.sourceMixerCommitScope = scope;
    renderSourceMixer();
    syncSecondaryPreview(previewPlaybackTime());
    toast(request.layout === "auto"
      ? state.project?.editor_sequence ? "Source mixer defaults applied to this range" : "AI layout restored for this range"
      : immediate
        ? scope === "selection"
          ? uiCopy("הפריסה נשמרה מיד לטווח המסומן", "Layout saved immediately to the selected range")
          : uiCopy("הפריסה נשמרה מיד לכל העריכה", "Layout saved immediately to the entire edit")
        : uiCopy("הפריסה הידנית הוחלה", "Manual layout applied"), "success", 2600);
  } finally {
    if (state.sourceMixerLayoutRequest === request) {
      state.sourceMixerLayoutRequest = null;
      if (!committed && state.project?.id === request.projectId) hydrateSourceMixerLayout();
      renderSourceMixer();
      if (state.project?.id === request.projectId) syncSecondaryPreview(previewPlaybackTime());
    }
  }
}

async function applyCreatorFrame() {
  if (!state.project?.sources?.B || sourceMixerControlBusy()) return;
  pauseAllMedia();
  const projectId = state.project.id;
  const mixer = sourceMixerSettings();
  const saved = await saveSourceMixer({ primary_role: "screen", first_slot: mixer.cameraSlot, stack_fit: "cover", default_layout: "stacked" }, { silent: true });
  if (!saved || state.project?.id !== projectId) return;
  state.sourceMixerLayout = "stacked";
  applyFramingPreview();
  if (state.project.draft) await applySourceLayout(state.manualSelection ? "selection" : "all", { immediate: true });
  else renderSourceMixer();
}

function embeddedLayoutConfirmed() {
  if (liveEmbeddedCameraRequest()) return true;
  const draft = state.project?.draft;
  return !state.project?.sources?.B && Boolean(embeddedCameraCandidate())
    && draft?.embedded_layout_confirmed === true && draft?.layout === "embedded_stack";
}

function embeddedContentRectangle(candidate) {
  // Keep this deterministic contract aligned with composition.py. The lower
  // panel must never contain the camera rectangle a second time.
  const { x, y, w, h } = candidate;
  const focus = candidate.content_focus || { x: .5, y: .5 };
  const regions = [
    { x: 0, y: 0, w: x, h: 1 }, { x: x + w, y: 0, w: 1 - x - w, h: 1 },
    { x: 0, y: 0, w: 1, h: y }, { x: 0, y: y + h, w: 1, h: 1 - y - h },
  ].filter((region) => region.w >= .06 && region.h >= .06);
  regions.sort((a, b) => {
    const areaDifference = Math.round(b.w * b.h * 1e6) - Math.round(a.w * a.h * 1e6);
    if (areaDifference) return areaDifference;
    const distance = (region) => (focus.x - region.x - region.w / 2) ** 2 + (focus.y - region.y - region.h / 2) ** 2;
    return distance(a) - distance(b);
  });
  const region = regions[0];
  return region ? Object.fromEntries(Object.entries(region).map(([key, value]) => [key, Math.round(value * 1e6) / 1e6])) : null;
}

function normalizedEmbeddedGeometry(raw) {
  if (!raw || typeof raw !== "object") return null;
  const x = Number(raw.x), y = Number(raw.y), w = Number(raw.w), h = Number(raw.h);
  if (![x, y, w, h].every(Number.isFinite)) return null;
  if (w < .06 || h < .06 || w * h < .006 || w * h > .6) return null;
  if (x < 0 || y < 0 || x + w > 1.000001 || y + h > 1.000001) return null;
  const focus = raw.content_focus && typeof raw.content_focus === "object" ? raw.content_focus : {};
  const geometry = {
    ...raw,
    x: Math.max(0, Math.min(1 - w, x)),
    y: Math.max(0, Math.min(1 - h, y)),
    w,
    h,
    content_focus: {
      x: Math.max(0, Math.min(1, Number.isFinite(Number(focus.x)) ? Number(focus.x) : .5)),
      y: Math.max(0, Math.min(1, Number.isFinite(Number(focus.y)) ? Number(focus.y) : .5)),
    },
  };
  geometry.content_region = embeddedContentRectangle(geometry);
  return geometry.content_region ? geometry : null;
}

function embeddedCameraCandidate() {
  if (state.project?.sources?.B) return null;
  const manual = normalizedEmbeddedGeometry(state.project?.manual?.embedded_camera);
  if (manual) return { ...manual, candidate_source: "manual", manual: true, requires_confirmation: true };
  const preparedVision = state.project?.pre_analysis?.vision?.A;
  const sourceGeneration = String(state.project?.sources?.A?.generation || "");
  const detectorVersion = String(state.system?.vision_analysis_version || EMBEDDED_CAMERA_DETECTOR_VERSION);
  const preparedVisionIsCurrent = sourceGeneration
    && preparedVision
    && preparedVision.version === detectorVersion
    && String(preparedVision.source_generation || "") === sourceGeneration;
  // Once Director has authoritative analysis, never resurrect an earlier upload
  // suggestion that the final pass rejected. Before Director, a generation-bound
  // preparation result makes the camera suggestion available immediately.
  const analyzedVision = state.project?.analysis?.vision;
  const analyzedVisionIsCurrent = analyzedVision?.version === detectorVersion;
  const vision = analyzedVisionIsCurrent
    ? analyzedVision
    : preparedVisionIsCurrent ? preparedVision : null;
  const candidate = normalizedEmbeddedGeometry(vision?.embedded_camera);
  if (!candidate) return null;
  // Older detectors produced false positives in gameplay HUDs. Only the
  // confirmation-only detector may offer this layout to the user.
  if (vision.version !== detectorVersion || candidate.detector !== detectorVersion) return null;
  if (candidate.requires_confirmation !== true) return null;
  return { ...candidate, candidate_source: "vision", manual: false };
}

function embeddedCameraIsActive() {
  if (liveEmbeddedCameraRequest()) return true;
  if (!embeddedCameraCandidate()) return false;
  if (state.project?.draft) return embeddedLayoutConfirmed();
  return state.project?.settings?.layout === "embedded_stack";
}

function embeddedEditorCandidateKey(candidate) {
  if (!candidate) return "default";
  return [candidate.candidate_source || candidate.detector || "candidate", candidate.x, candidate.y, candidate.w, candidate.h,
    candidate.content_focus?.x, candidate.content_focus?.y].join(":");
}

function embeddedEditorSourceKey() {
  const source = state.project?.sources?.A;
  return source ? `${source.generation || ""}:${source.url || ""}` : null;
}

function embeddedCameraRequestIsCurrent(request) {
  return Boolean(request && state.project?.sources?.A && !state.project.sources.B
    && request.projectId === state.project.id && request.generation === embeddedEditorSourceKey()
    && request.viewToken === state.projectViewToken);
}

function liveEmbeddedCameraRequest() {
  const request = state.embeddedEditor.pending;
  return embeddedCameraRequestIsCurrent(request) ? request : null;
}

function embeddedCameraPreviewCandidate() {
  return liveEmbeddedCameraRequest()?.geometry || embeddedCameraCandidate();
}

function embeddedEditorBusy() {
  // Keep dragging responsive while this editor's own save is in flight.
  return Boolean(state.activeJob || state.activeUploads.size || state.jobStartLocks.size
    || state.sourceSyncPending || state.sourceMixerSavePending
    || (state.manualEditBusy && !state.embeddedEditor.applying));
}

function resetEmbeddedEditor() {
  clearTimeout(state.embeddedEditor.saveTimer);
  state.embeddedEditor = { projectId: state.project?.id, generation: embeddedEditorSourceKey(),
    viewToken: state.projectViewToken, candidateKey: null, dirty: false, dragging: false };
}

function renderEmbeddedSaveState() {
  const editor = state.embeddedEditor;
  const active = embeddedCameraIsActive();
  if (elements.embeddedCameraState) {
    elements.embeddedCameraState.classList.toggle("active", active && !editor.dirty);
    elements.embeddedCameraState.textContent = editor.error ? "Save failed — retry"
      : editor.dirty ? "Saving…"
      : active ? "Saved"
      : embeddedCameraCandidate()?.candidate_source === "vision" ? "Review camera area" : "Mark your camera";
  }
  if (elements.saveEmbeddedCamera) {
    elements.saveEmbeddedCamera.hidden = !editor.error && (active || editor.dirty);
    elements.saveEmbeddedCamera.textContent = editor.error ? "Retry save" : "Use camera layout";
    elements.saveEmbeddedCamera.disabled = embeddedEditorBusy() || Boolean(editor.saving);
  }
}

function previewEmbeddedCameraSelection() {
  if (!state.project?.sources?.A || !elements.previewA || !elements.previewB) return;
  const sourceUrl = sourceMediaUrl(state.project.sources.A);
  if (liveEmbeddedCameraRequest() && elements.previewB.dataset.url !== sourceUrl) {
    elements.previewB.src = sourceUrl;
    elements.previewB.dataset.url = sourceUrl;
    elements.previewB.load();
  }
  syncSecondaryPreview(previewPlaybackTime());
}

function queueEmbeddedCameraSave({ immediate = false } = {}) {
  if (!state.project?.sources?.A || state.project.sources.B || embeddedEditorBusy()) return null;
  const editor = state.embeddedEditor;
  const geometry = normalizedEmbeddedGeometry(embeddedEditorGeometryFromControls());
  if (!geometry) return null;
  clearTimeout(editor.saveTimer);
  editor.pending = { projectId: state.project.id, generation: embeddedEditorSourceKey(),
    viewToken: state.projectViewToken, geometry };
  editor.dirty = true;
  editor.error = false;
  updateEmbeddedEditorPreview();
  previewEmbeddedCameraSelection();
  if (immediate) return flushEmbeddedCameraSave();
  editor.saveTimer = setTimeout(() => { flushEmbeddedCameraSave(); }, 450);
  return editor.pending;
}

async function flushEmbeddedCameraSave(projectId = state.project?.id) {
  const editor = state.embeddedEditor;
  if (editor.pending?.projectId !== projectId || !liveEmbeddedCameraRequest()) return true;
  clearTimeout(editor.saveTimer);
  editor.saveTimer = null;
  if (editor.saveTask) return editor.saveTask;
  editor.saving = true;
  // Start in a microtask so saveTask exists before applyManualEdit renders.
  editor.saveTask = Promise.resolve().then(async () => {
    while (editor === state.embeddedEditor && liveEmbeddedCameraRequest()) {
      if (state.manualEditPromise) await state.manualEditPromise;
      if (state.sourceMixerSavePending) await state.sourceMixerSaveTail;
      if (state.sourceSyncPending) await flushPendingSourceSync(projectId);
      const request = editor.pending;
      if (editor !== state.embeddedEditor || !embeddedCameraRequestIsCurrent(request)) return true;
      if (foregroundBusy()) throw new Error("Camera layout could not be saved while another operation is running.");
      const geometry = request.geometry;
      editor.applying = true;
      const updated = await applyManualEdit("set_embedded_camera", {
        enabled: true, x: geometry.x, y: geometry.y, w: geometry.w, h: geometry.h,
        content_x: geometry.content_focus.x, content_y: geometry.content_focus.y,
      }, { isCurrent: () => embeddedCameraRequestIsCurrent(request) });
      editor.applying = false;
      if (editor !== state.embeddedEditor || !embeddedCameraRequestIsCurrent(request)) return true;
      if (!updated) throw new Error("Camera layout was not saved.");
      // The reply may represent an older drag position. Keep the newer overlay
      // and controls intact until that exact position has also been saved.
      if (editor.pending === request) {
        editor.pending = null;
        editor.dirty = false;
        editor.candidateKey = embeddedEditorCandidateKey(embeddedCameraCandidate());
      }
    }
    return true;
  }).catch((error) => {
    if (editor === state.embeddedEditor && liveEmbeddedCameraRequest()) {
      editor.error = true;
      toast(`${error.message} Retry save to keep this camera layout.`);
    }
    return false;
  }).finally(() => {
    editor.saving = false;
    editor.applying = false;
    editor.saveTask = null;
    if (editor === state.embeddedEditor) {
      renderEmbeddedCameraEditor();
      previewEmbeddedCameraSelection();
    }
  });
  renderEmbeddedSaveState();
  return editor.saveTask;
}

function embeddedEditorGeometryFromControls() {
  const value = (control, fallback) => {
    const raw = control?.value;
    const parsed = raw == null || raw === "" ? NaN : Number(raw);
    return (Number.isFinite(parsed) ? parsed : fallback) / 100;
  };
  const width = Math.max(.06, Math.min(1, value(elements.embeddedCameraW, 25)));
  const height = Math.max(.06, .006 / width, Math.min(1, .6 / width, value(elements.embeddedCameraH, 30)));
  const x = Math.max(0, Math.min(1 - width, value(elements.embeddedCameraX, 70)));
  const y = Math.max(0, Math.min(1 - height, value(elements.embeddedCameraY, 5)));
  return {
    x, y, w: width, h: height,
    content_focus: {
      x: Math.max(0, Math.min(1, value(elements.embeddedContentX, 50))),
      y: Math.max(0, Math.min(1, value(elements.embeddedContentY, 50))),
    },
  };
}

function writeEmbeddedEditorGeometry(candidate, { dirty = state.embeddedEditor.dirty } = {}) {
  const geometry = normalizedEmbeddedGeometry(candidate) || {
    x: .7, y: .05, w: .25, h: .3, content_focus: { x: .5, y: .55 },
  };
  elements.embeddedCameraW.value = String(Math.round(geometry.w * 100));
  elements.embeddedCameraH.value = String(Math.round(geometry.h * 100));
  elements.embeddedCameraX.value = String(Math.round(Math.min(1 - geometry.w, geometry.x) * 100));
  elements.embeddedCameraY.value = String(Math.round(Math.min(1 - geometry.h, geometry.y) * 100));
  elements.embeddedContentX.value = String(Math.round(Number(geometry.content_focus?.x ?? .5) * 100));
  elements.embeddedContentY.value = String(Math.round(Number(geometry.content_focus?.y ?? .5) * 100));
  state.embeddedEditor.dirty = dirty;
  updateEmbeddedEditorPreview();
}

function updateEmbeddedEditorPreview() {
  if (!elements.embeddedCameraRect) return;
  const geometry = embeddedEditorGeometryFromControls();
  elements.embeddedCameraX.value = String(Math.round(geometry.x * 100));
  elements.embeddedCameraY.value = String(Math.round(geometry.y * 100));
  elements.embeddedCameraW.value = String(Math.round(geometry.w * 100));
  elements.embeddedCameraH.value = String(Math.round(geometry.h * 100));
  elements.embeddedCameraRect.style.left = `${geometry.x * 100}%`;
  elements.embeddedCameraRect.style.top = `${geometry.y * 100}%`;
  elements.embeddedCameraRect.style.width = `${geometry.w * 100}%`;
  elements.embeddedCameraRect.style.height = `${geometry.h * 100}%`;
  for (const [key, value] of [
    ["embeddedCameraXOut", geometry.x], ["embeddedCameraYOut", geometry.y],
    ["embeddedCameraWOut", geometry.w], ["embeddedCameraHOut", geometry.h],
    ["embeddedContentXOut", geometry.content_focus.x], ["embeddedContentYOut", geometry.content_focus.y],
  ]) elements[key].textContent = `${Math.round(value * 100)}%`;
  renderEmbeddedSaveState();
}

function renderEmbeddedCameraEditor() {
  if (!elements.embeddedCameraEditor) return;
  const source = state.project?.sources?.A;
  const hasB = Boolean(state.project?.sources?.B);
  elements.embeddedCameraEditor.hidden = !source || hasB;
  if (!source || hasB) { resetEmbeddedEditor(); return; }

  const candidate = embeddedCameraCandidate();
  const generation = embeddedEditorSourceKey();
  const candidateKey = embeddedEditorCandidateKey(candidate);
  const changedSource = state.embeddedEditor.projectId !== state.project.id || state.embeddedEditor.generation !== generation
    || state.embeddedEditor.viewToken !== state.projectViewToken;
  if (changedSource) {
    resetEmbeddedEditor();
    // Once marked, keep the large source picker out of the way. Do not reopen
    // it on every autosave or playback update, or discard the user's choice.
    elements.embeddedCameraEditor.open = !embeddedCameraIsActive();
  }
  if (state.embeddedEditor.error) elements.embeddedCameraEditor.open = true;
  const changedSuggestion = !state.embeddedEditor.dirty && state.embeddedEditor.candidateKey !== candidateKey;
  if (changedSource || changedSuggestion) {
    state.embeddedEditor.projectId = state.project.id;
    state.embeddedEditor.generation = generation;
    state.embeddedEditor.candidateKey = candidateKey;
    writeEmbeddedEditorGeometry(candidate, { dirty: false });
    if (changedSource && elements.embeddedCameraSeek) elements.embeddedCameraSeek.value = "0";
  } else {
    updateEmbeddedEditorPreview();
  }

  const sourceUrl = sourceMediaUrl(source);
  if (elements.embeddedCameraVideo.dataset.url !== sourceUrl) {
    elements.embeddedCameraVideo.src = sourceUrl;
    elements.embeddedCameraVideo.dataset.url = sourceUrl;
    elements.embeddedCameraVideo.load();
  }
  const sourceWidth = Number(source.width || 16), sourceHeight = Number(source.height || 9);
  if (sourceWidth > 0 && sourceHeight > 0) elements.embeddedCameraCanvas.style.aspectRatio = `${sourceWidth} / ${sourceHeight}`;

  const active = embeddedCameraIsActive();
  renderEmbeddedSaveState();
  elements.embeddedCameraHelp.textContent = candidate?.candidate_source === "vision"
    ? "Check that the suggested area contains your camera. Moving the frame previews and saves your camera layout automatically."
    : "If your recording includes a camera, drag its frame here. The edited preview updates immediately and changes save automatically.";
  const busy = embeddedEditorBusy();
  if (elements.embeddedCameraSeek) {
    elements.embeddedCameraSeek.disabled = busy || !(Number(source.duration) > 0);
    elements.embeddedCameraSeekOut.textContent = formatTime(Number(elements.embeddedCameraVideo.currentTime || 0), true);
  }
  elements.disableEmbeddedCamera.disabled = busy || Boolean(state.embeddedEditor.saving) || !active;
  elements.disableEmbeddedCamera.hidden = !active;
  for (const control of [elements.embeddedCameraX, elements.embeddedCameraY, elements.embeddedCameraW, elements.embeddedCameraH, elements.embeddedContentX, elements.embeddedContentY]) {
    control.disabled = busy;
  }
  for (const button of $$('button[data-embedded-preset]', elements.embeddedCameraPresets)) button.disabled = busy;
}

function bindEmbeddedCameraEditorEvents() {
  const geometryControls = [elements.embeddedCameraX, elements.embeddedCameraY, elements.embeddedCameraW, elements.embeddedCameraH, elements.embeddedContentX, elements.embeddedContentY];
  for (const control of geometryControls) control.addEventListener("input", () => {
    queueEmbeddedCameraSave();
  });
  elements.embeddedCameraPresets.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-embedded-preset]");
    if (!button || button.disabled) return;
    const current = embeddedEditorGeometryFromControls();
    const gap = .04;
    const [vertical, horizontal] = button.dataset.embeddedPreset.split("-");
    current.x = Math.max(0, Math.min(1 - current.w, horizontal === "left" ? gap : 1 - current.w - gap));
    current.y = Math.max(0, Math.min(1 - current.h, vertical === "top" ? gap : 1 - current.h - gap));
    writeEmbeddedEditorGeometry(current, { dirty: true });
    queueEmbeddedCameraSave();
  });
  elements.saveEmbeddedCamera.addEventListener("click", () => runUiAction(saveEmbeddedCameraSelection, uiCopy("שמירת אזור המצלמה", "Saving camera area")));
  elements.disableEmbeddedCamera.addEventListener("click", () => runUiAction(disableEmbeddedCameraSelection, uiCopy("ביטול המצלמה הפנימית", "Disabling embedded camera")));
  elements.embeddedCameraSeek?.addEventListener("input", seekEmbeddedCameraFrame);
  elements.embeddedCameraVideo.addEventListener("loadedmetadata", seekEmbeddedCameraFrame);

  const canvas = elements.embeddedCameraCanvas;
  canvas.addEventListener("pointerdown", (event) => {
    if (embeddedEditorBusy()) return;
    const bounds = canvas.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const geometry = embeddedEditorGeometryFromControls();
    const px = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
    const py = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
    const onRect = Boolean(event.target.closest("#embeddedCameraRect"));
    state.embeddedEditor.dragging = true;
    state.embeddedEditor.resizing = Boolean(event.target.closest("#embeddedCameraRect i"));
    elements.embeddedCameraVideo.pause();
    state.embeddedEditor.dragOffset = onRect
      ? { x: px - geometry.x, y: py - geometry.y }
      : { x: geometry.w / 2, y: geometry.h / 2 };
    canvas.setPointerCapture(event.pointerId);
    state.embeddedEditor.dirty = true;
    moveEmbeddedCameraFromPointer(event);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (state.embeddedEditor.dragging) moveEmbeddedCameraFromPointer(event);
  });
  const stopDragging = (event) => {
    state.embeddedEditor.dragging = false;
    state.embeddedEditor.resizing = false;
    if (canvas.hasPointerCapture?.(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  };
  canvas.addEventListener("pointerup", stopDragging);
  canvas.addEventListener("pointercancel", stopDragging);
  canvas.addEventListener("lostpointercapture", stopDragging);
}

function seekEmbeddedCameraFrame() {
  const video = elements.embeddedCameraVideo;
  const duration = Number(state.project?.sources?.A?.duration || 0);
  const fraction = Math.max(0, Math.min(1, Number(elements.embeddedCameraSeek?.value || 0) / 1000));
  if (!video || !Number.isFinite(duration) || duration <= 0) return;
  const time = Math.min(Math.max(0, duration - .001), fraction * duration);
  video.pause();
  try { video.currentTime = time; } catch { /* loadedmetadata retries the selected frame. */ }
  if (elements.embeddedCameraSeekOut) elements.embeddedCameraSeekOut.textContent = formatTime(time, true);
}

function moveEmbeddedCameraFromPointer(event) {
  const canvas = elements.embeddedCameraCanvas;
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const geometry = embeddedEditorGeometryFromControls();
  const px = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width));
  const py = Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height));
  const offset = state.embeddedEditor.dragOffset || { x: geometry.w / 2, y: geometry.h / 2 };
  if (state.embeddedEditor.resizing) {
    geometry.w = Math.max(.06, .006 / (1 - geometry.y), Math.min(1 - geometry.x, px - geometry.x));
    geometry.h = Math.max(.06, .006 / geometry.w, Math.min(1 - geometry.y, .6 / geometry.w, py - geometry.y));
  } else {
    geometry.x = Math.max(0, Math.min(1 - geometry.w, px - offset.x));
    geometry.y = Math.max(0, Math.min(1 - geometry.h, py - offset.y));
  }
  writeEmbeddedEditorGeometry(geometry, { dirty: true });
  queueEmbeddedCameraSave();
}

async function saveEmbeddedCameraSelection() {
  return queueEmbeddedCameraSave({ immediate: true });
}

async function disableEmbeddedCameraSelection() {
  if (!state.project?.sources?.A || state.project?.sources?.B) return null;
  if (embeddedEditorBusy() || state.embeddedEditor.saving) return null;
  // An explicit disable supersedes any still-debounced camera position.
  resetEmbeddedEditor();
  const updated = await applyManualEdit("set_embedded_camera", { enabled: false });
  if (!updated) return null;
  state.embeddedEditor.dirty = false;
  state.embeddedEditor.candidateKey = null;
  renderEmbeddedCameraEditor();
  toast(uiCopy("המצלמה הפנימית בוטלה; המקור יוצג פעם אחת בלבד", "Embedded camera disabled; the source will appear only once"), "success", 2800);
  return updated;
}

function setupPreviewSources() {
  const sourceA = state.project.sources?.A;
  const sourceB = state.project.sources?.B;
  if (!sourceA) return;
  const sourceAUrl = sourceMediaUrl(sourceA);
  const sourceBUrl = sourceMediaUrl(sourceB);
  if (elements.previewA.dataset.url !== sourceAUrl) {
    elements.previewA.src = sourceAUrl; elements.previewA.dataset.url = sourceAUrl; elements.previewA.load();
  }
  const embedded = embeddedCameraPreviewCandidate();
  if (embedded && embeddedLayoutConfirmed()) {
    if (elements.previewB.dataset.url !== sourceAUrl) {
      elements.previewB.src = sourceAUrl; elements.previewB.dataset.url = sourceAUrl; elements.previewB.load();
    }
  } else if (sourceB) {
    if (elements.previewB.dataset.url !== sourceBUrl) {
      elements.previewB.src = sourceBUrl; elements.previewB.dataset.url = sourceBUrl; elements.previewB.load();
    }
  } else {
    elements.previewB.removeAttribute("src"); elements.previewB.load(); elements.previewB.dataset.url = "";
  }
  const audioSlot = sourceMixerSettings().audioSlot;
  elements.previewA.muted = audioSlot !== "A";
  elements.previewB.muted = audioSlot !== "B";
  elements.cropSourceSelect.querySelector('option[value="B"]').disabled = !sourceB;
  if (!state.project.sources?.[elements.cropSourceSelect.value]) elements.cropSourceSelect.value = "A";
  applyStoredPreviewCrop("A");
  if (sourceB) applyStoredPreviewCrop("B");
  loadCropControls(elements.cropSourceSelect.value);
}

function togglePreview() {
  if (!state.project?.sources?.A || foregroundBusy() || elements.resultPanel.hidden) return;
  if (previewUsesIndependentTracks() ? !state.preview.playing : elements.previewA.paused) playPreview(); else pausePreview();
}

async function playPreview() {
  state.mediaStudio?.resumeAudio();
  const project = playbackProject();
  if (!project?.sources?.A || foregroundBusy() || elements.resultPanel.hidden) return;
  if (!previewUsesSourceTime() && !hasTimelineFootage()) return;
  if (previewUsesIndependentTracks()) {
    if (state.preview.playing) return;
    const clock = independentPreviewClock();
    const current = clock.time();
    const duration = timelineDuration(project);
    if (current >= duration - .001) seekPreview(previewUsesSourceTime() ? 0 : firstKeptTime());
    else if (!previewUsesSourceTime() && inCut(current)) seekPreview(nextKeptTime(current) ?? firstKeptTime());
    state.preview.playRequest += 1;
    clock.play();
    setPreviewPlaying(true);
    tickIndependentPreview();
    return;
  }
  const playRequest = ++state.preview.playRequest;
  const current = elements.previewA.currentTime;
  if (current >= timelineDuration(project) - .001) {
    seekPreview(previewUsesSourceTime() ? 0 : firstKeptTime());
  } else if (!previewUsesSourceTime() && inCut(current)) {
    seekPreview(nextKeptTime(current) ?? firstKeptTime());
  }
  try {
    await elements.previewA.play();
    // A view change or a fast Pause click can happen while play() is awaiting
    // the browser. Never let that stale request start source B afterwards.
    if (playRequest !== state.preview.playRequest || elements.previewA.paused) return;
    syncSecondaryPreview(elements.previewA.currentTime);
  } catch (error) {
    if (playRequest === state.preview.playRequest) toast(error.message);
  }
}

function pausePreview() {
  pauseAllMedia();
}

function stopPreviewPlayback() {
  // An independently edited A clip may pause/end while B (or a gap) continues.
  // Explicit Pause/navigation stops the timeline clock in pauseAllMedia.
  if (previewUsesIndependentTracks() && state.preview.clock?.playing) return;
  state.preview.playRequest += 1;
  elements.previewB?.pause();
  setPreviewPlaying(false);
}

function pauseAllMedia() {
  state.mediaStudio?.pause();
  state.preview.playRequest += 1;
  state.preview.clock?.pause();
  if (state.preview.frame != null) cancelAnimationFrame(state.preview.frame);
  state.preview.frame = null;
  document.querySelectorAll("video, audio").forEach((media) => {
    try { media.pause(); } catch (_error) { /* A detached preview should not block navigation. */ }
  });
  setPreviewPlaying(false);
}

function releaseMediaHandles() {
  state.mediaStudio?.clearPlayers();
  pauseAllMedia();
  document.querySelectorAll("video, audio").forEach((media) => {
    try {
      media.removeAttribute("src");
      media.removeAttribute("poster");
      if ("srcObject" in media) media.srcObject = null;
      delete media.dataset.url;
      media.load();
    } catch (_error) { /* Windows can release the remaining handle when the request closes. */ }
  });
}

function setPreviewPlaying(playing) {
  if (playing && previewUsesIndependentTracks() && !state.preview.clock?.playing) {
    elements.previewA?.pause();
    return;
  }
  state.preview.playing = playing;
  updateMediaPreview();
  elements.previewStage.classList.toggle("playing", playing);
  elements.playButton.textContent = playing ? "❚❚" : "▶";
  elements.previewPlay.querySelector("span").textContent = playing ? "❚❚" : "▶";
  const label = playing ? uiCopy("השהה", "Pause") : uiCopy("נגן", "Play");
  elements.playButton.setAttribute("aria-label", label);
  elements.previewPlay.setAttribute("aria-label", label);
}

function onPreviewTimeUpdate() {
  const project = playbackProject();
  if (!project || state.preview.seeking) return;
  if (previewUsesIndependentTracks()) return;
  let time = elements.previewA.currentTime;
  // A paused seek also emits timeupdate. Never turn an editor click or frame
  // step into an automatic jump, and never skip excluded footage in Source.
  if (!previewUsesSourceTime() && !elements.previewA.paused && inCut(time)) {
    const next = nextKeptTime(time);
    if (next == null) {
      pauseAllMedia();
      time = Number(project.draft?.keep_ranges?.at(-1)?.end || 0);
    } else time = next;
    seekPreview(time);
    return;
  }
  syncSecondaryPreview(time);
  updatePreviewUI(time);
  publishPreviewPlayhead(time);
}

function previewUsesIndependentTracks() {
  const project = playbackProject();
  return Boolean(project?.sources?.A && project?.manual?.source_tracks && hasSourceTracks(project));
}

function independentPreviewClock() {
  const project = playbackProject();
  if (!state.preview.clock || state.preview.clockProject !== project?.id) {
    state.preview.clock?.pause();
    state.preview.clock = new SourceTimelineClock();
    state.preview.clock.seek(project?.manual?.sequence
      ? state.preview.editCursorProject === project.id ? state.preview.editCursor || 0 : 0
      : Number(elements.previewA.currentTime) || 0);
    state.preview.clockProject = project?.id;
  }
  return state.preview.clock;
}

function previewPlaybackTime() {
  return previewUsesIndependentTracks() ? independentPreviewClock().time() : Number(elements.previewA?.currentTime) || 0;
}

function previewSourceToEditTime(time) {
  const anchor = state.preview.sourceAnchor;
  if (anchor?.projectId === state.project?.id && Math.abs(time - anchor.sourceTime) < .00001) return anchor.editTime;
  return sourceToEditorTime(time);
}

function previewTimelineTime() {
  const time = previewPlaybackTime();
  if (!previewUsesSourceTime() || !state.project?.editor_sequence) return time;
  const mapped = previewSourceToEditTime(time);
  return mapped ?? (state.preview.editCursorProject === state.project.id ? state.preview.editCursor || 0 : 0);
}

function publishPreviewPlayhead(time, editTime) {
  const mapped = editTime ?? (previewUsesSourceTime() && state.project?.editor_sequence ? previewSourceToEditTime(time) : time);
  if (mapped == null) return;
  state.preview.editCursor = Math.max(0, Math.min(editorDuration(), Number(mapped) || 0));
  state.preview.editCursorProject = state.project?.id;
  state.timeline?.setPlayhead?.(state.preview.editCursor);
  if (state.project?.editor_sequence && elements.studioPanelFraming?.hidden === false && !state.framingDraft && !state.manualEditBusy) {
    const slot = elements.cropSourceSelect?.value || "A", scope = framingScope(slot);
    const key = `${state.project.id}:${slot}:${scope?.start}:${scope?.end}`;
    if (state.framingScopeKey !== key) loadCropControls(slot, false);
  }
  if (elements.manualSplit && state.project?.editor_sequence) elements.manualSplit.disabled = foregroundBusy() || state.manualEditBusy || state.transcriptSaving || !state.timeline?.canSplitAt?.(state.preview.editCursor);
}

function tickIndependentPreview() {
  const project = playbackProject();
  if (!previewUsesIndependentTracks() || !state.preview.playing || !state.preview.clock?.playing) return;
  if (state.preview.frame != null) cancelAnimationFrame(state.preview.frame);
  state.preview.frame = null;
  const clock = independentPreviewClock();
  const duration = timelineDuration(project);
  const finalTime = previewUsesSourceTime() ? duration : Number(project.draft?.keep_ranges?.at(-1)?.end ?? duration);
  let time = clock.time();
  if (time >= finalTime) {
    pauseAllMedia();
    seekPreview(finalTime);
    return;
  }
  if (!previewUsesSourceTime() && inCut(time)) {
    const next = nextKeptTime(time);
    if (next == null) { pauseAllMedia(); seekPreview(finalTime); return; }
    time = clock.seek(next);
  }
  syncSecondaryPreview(time);
  updatePreviewUI(time);
  publishPreviewPlayhead(time);
  state.preview.frame = requestAnimationFrame(tickIndependentPreview);
}

function syncIndependentMedia(slot, point, needed, forceSeek = false, sourceSlot = slot) {
  const video = slot === "A" ? elements.previewA : elements.previewB;
  const active = Boolean(point && needed && video.src);
  const pendingKey = `pending${slot}`;
  const clipKey = `clip${slot}`;
  if (!active) {
    state.preview[clipKey] = null;
    if (state.preview[pendingKey]) state.preview[pendingKey].cancelled = true;
    if (!video.paused) video.pause();
    return;
  }
  const changedClip = state.preview[clipKey] !== point.clip.id;
  state.preview[clipKey] = point.clip.id;
  const speed = Number(point.clip.video_speed) || 1;
  const rawPictureTime = Number(point.clip.video_source_start ?? point.clip.source_start) + (point.sourceTime-point.clip.source_start)*speed;
  const source = playbackProject()?.sources?.[sourceSlot];
  const limit = Number(source?.video_duration || source?.duration || video.duration);
  const retimed = speed !== 1 || point.clip.video_source_start != null;
  const pictureTime = retimed ? Math.max(0, Math.min(rawPictureTime, limit > 0 ? Math.max(0,limit-.04) : rawPictureTime)) : point.sourceTime;
  video.playbackRate = speed;
  if (forceSeek || changedClip || Math.abs(video.currentTime - pictureTime) > .12) {
    try { video.currentTime = pictureTime; } catch { /* loadedmetadata/timeupdate can retry. */ }
  }
  if (retimed && limit > 0 && rawPictureTime >= limit-.035) {
    if (state.preview[pendingKey]) state.preview[pendingKey].cancelled = true;
    video.pause();
    return;
  }
  if (!state.preview.playing) { if (!video.paused) video.pause(); return; }
  if (!video.paused || state.preview[pendingKey]) return;
  const request = state.preview.playRequest;
  const projectId = state.project?.id;
  const pending = {};
  state.preview[pendingKey] = pending;
  let operation;
  try { operation = video.play(); } catch (error) {
    state.preview[pendingKey] = null;
    pauseAllMedia();
    toast(error.message || "Playback could not start. Press Play to retry.");
    return;
  }
  Promise.resolve(operation).then(() => {
    const current = previewUsesIndependentTracks()
      ? trackAt(playbackProject(), sourceSlot, previewPlaybackTime(), sourceMixerSettings().syncOffset) : null;
    if (request !== state.preview.playRequest || projectId !== state.project?.id || !state.preview.playing || !current || (video.hidden && video.muted)) video.pause();
  }).catch(error => {
    // A gap or held picture can deliberately cancel a still-loading player.
    // That cancellation must not stop the other track or the timeline clock.
    if (error?.name === "AbortError" && pending.cancelled) return;
    if (request === state.preview.playRequest && projectId === state.project?.id && state.preview.playing) {
      pauseAllMedia();
      toast(error.message || "Playback could not start. Press Play to retry.");
    }
  }).finally(() => { if (state.preview[pendingKey] === pending) state.preview[pendingKey] = null; });
}

function embeddedFacePreviewGeometry(candidate, sourceRatio, panelRatio, focus = { x: .5, y: .5 }) {
  // Crop the selected source rectangle, then cover the upper pane, just as
  // FFmpeg does. Percentages make this independent of browser/player size.
  const { x, y, w, h } = candidate;
  const scale = Math.max(1 / (sourceRatio * w), 1 / (panelRatio * h));
  return {
    width: sourceRatio * scale * 100,
    height: scale * panelRatio * 100,
    left: ((1 - sourceRatio * w * scale) * Number(focus.x ?? .5) - x * sourceRatio * scale) * 100,
    top: ((1 - h * scale * panelRatio) * Number(focus.y ?? .5) - y * scale * panelRatio) * 100,
  };
}

function syncSecondaryPreview(globalTime) {
  const project = playbackProject();
  const sourceB = project.sources?.B;
  const requestedCamera = cameraAt(globalTime);
  const mixer = sourceMixerSettings();
  const independent = previewUsesIndependentTracks();
  const pointA = independent ? trackAt(project, "A", globalTime, mixer.syncOffset) : null;
  const embeddedB = !sourceB && requestedCamera === "embedded_stack";
  const pointB = independent ? embeddedB ? pointA : trackAt(project, "B", globalTime, mixer.syncOffset) : null;
  const sourceA = project.sources?.A;
  const sourceAVideoDuration = Number(sourceA?.video_duration) > 0 ? Number(sourceA.video_duration) : Number(sourceA?.duration || 0);
  const sourceAAvailable = !independent || Boolean(pointA && pointA.sourceTime < sourceAVideoDuration);
  const offset = mixer.syncOffset;
  const sourceBTime = independent ? pointB?.sourceTime : globalTime - offset;
  const sourceBVideoDuration = Number(sourceB?.video_duration);
  const sourceBDuration = Number.isFinite(sourceBVideoDuration) && sourceBVideoDuration > 0
    ? sourceBVideoDuration : Number(sourceB?.duration || 0);
  const sourceBAvailable = Boolean(sourceB && (!independent || pointB) && sourceBTime >= 0 && sourceBTime < sourceBDuration);
  const requiresB = ["B", "stacked", "side_by_side", "pip"].includes(requestedCamera)
    || (requestedCamera === "screen" && mixer.screenSlot === "B")
    || (requestedCamera === "camera" && mixer.cameraSlot === "B");
  const camera = independent && !sourceAAvailable && !sourceBAvailable ? "gap"
    : independent && !sourceAAvailable ? "B"
      : requiresB && !sourceBAvailable ? "A" : requestedCamera;
  refreshEmbeddedCropControls(camera);
  const stage = elements.previewStage;
  applyPreviewPipGeometry(stage);
  stage.classList.remove(
    "layout-stacked", "layout-side_by_side", "layout-pip", "layout-embedded_stack",
    "screen-slot-a", "screen-slot-b", "primary-screen", "primary-camera", "pip-inset-a", "pip-inset-b",
    "first-slot-a", "first-slot-b", "primary-slot-a", "primary-slot-b",
  );
  const primarySlot = mixer.primaryRole === "camera" ? mixer.cameraSlot : mixer.screenSlot;
  const firstShare = mixer.firstSlot === primarySlot ? 70 : 30;
  stage.style.setProperty("--stack-first-share", `${firstShare}%`);
  stage.style.setProperty("--stack-fit", mixer.stackFit);
  stage.classList.add(
    `screen-slot-${mixer.screenSlot.toLowerCase()}`,
    `primary-${mixer.primaryRole}`,
    `first-slot-${mixer.firstSlot.toLowerCase()}`,
    `primary-slot-${primarySlot.toLowerCase()}`,
  );
  let showA = true, showB = false;
  const singleSlot = camera === "screen" ? mixer.screenSlot : camera === "camera" ? mixer.cameraSlot : camera;
  if (singleSlot === "B" && sourceB) { showA = false; showB = true; }
  if (camera === "stacked") { showA = true; showB = true; stage.classList.add("layout-stacked"); }
  if (camera === "embedded_stack") { showA = true; showB = true; stage.classList.add("layout-embedded_stack"); }
  if (camera === "side_by_side") { showA = true; showB = true; stage.classList.add("layout-side_by_side"); }
  if (camera === "pip") {
    showA = true; showB = true; stage.classList.add("layout-pip");
    const baseSlot = mixer.primaryRole === "screen" ? mixer.screenSlot : mixer.cameraSlot;
    stage.classList.add(`pip-inset-${baseSlot === "A" ? "b" : "a"}`);
  }
  if (camera === "gap") { showA = false; showB = false; }
  elements.previewA.hidden = !showA;
  elements.previewB.hidden = !showB;
  elements.previewPaneA.hidden = !showA;
  elements.previewPaneB.hidden = !showB;
  const cameraLabels = {
    screen: uiCopy("מסך", "SCREEN"), camera: uiCopy("מצלמה", "CAMERA"), stacked: uiCopy("מעל / מתחת", "STACKED"),
    side_by_side: uiCopy("זה לצד זה", "SPLIT"), pip: "PIP", embedded_stack: uiCopy("מצלמה פנימית", "SCREEN + CAM"),
  };
  elements.cameraBadge.textContent = camera === "gap" ? "GAP" : cameraLabels[camera] || singleSlot;

  if (camera === "embedded_stack") {
    const candidate = embeddedCameraPreviewCandidate();
    if (candidate) {
      const liveCrop = state.framingDraft?.projectId === state.project.id && state.framingDraft.slot === "A"
        && globalTime >= state.framingDraft.scope.start && globalTime < state.framingDraft.scope.end ? state.framingDraft.crop : null;
      const content = liveCrop || editedClipCrop("A", globalTime) || candidate.content_focus || { x: 0.5, y: 0.5 };
      const source = project.sources.A;
      const sourceRatio = Number(source.width) / Number(source.height) || 16 / 9;
      const frameRatio = { "9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1, "4:5": 4 / 5 }[stage.dataset.aspect] || sourceRatio;
      const cameraGeometry = embeddedFacePreviewGeometry(candidate, sourceRatio, frameRatio / .3);
      const contentGeometry = embeddedFacePreviewGeometry(candidate.content_region, sourceRatio, frameRatio / .7, content);
      for (const [video, geometry] of [[elements.previewB, cameraGeometry], [elements.previewA, contentGeometry]]) {
        for (const [key, value] of Object.entries(geometry)) video.style[key] = `${value}%`;
        video.style.objectFit = "fill";
        video.style.transform = "none";
      }
    }
  } else {
    for (const slot of ["A", "B"]) {
      const video = slot === "A" ? elements.previewA : elements.previewB;
      for (const key of ["width", "height", "left", "top", "objectFit"]) video.style[key] = "";
      applyCompositionCrop(video, slot, camera, mixer, null, globalTime);
    }
  }

  const mixerOwnsAudio = Boolean(state.mediaStudio && !previewUsesSourceTime());
  const audioFromB = !mixerOwnsAudio && mixer.audioSlot === "B" && Boolean(sourceB?.has_audio);
  // Embedded B is only a second crop of A, never a second audio track. Refresh
  // mute state here too, since switching projects/layouts can leave stale media.
  elements.previewA.muted = mixerOwnsAudio || audioFromB;
  elements.previewB.muted = mixerOwnsAudio || !audioFromB;
  if (independent) {
    elements.previewA.muted = mixerOwnsAudio || mixer.audioSlot !== "A" || !pointA || !sourceA?.has_audio;
    elements.previewB.muted = mixerOwnsAudio || mixer.audioSlot !== "B" || !pointB || !sourceB?.has_audio;
    syncIndependentMedia("A", pointA, showA || !elements.previewA.muted, state.preview.seeking);
    syncIndependentMedia("B", pointB, showB || !elements.previewB.muted, state.preview.seeking, embeddedB ? "A" : "B");
    state.preview.currentCamera = camera;
    updateMediaPreview();
    return;
  }
  const needsBPlayback = (showB || audioFromB) && Boolean(elements.previewB.src);
  elements.previewA.playbackRate = 1; elements.previewB.playbackRate = 1;
  if (needsBPlayback) {
    const desired = camera === "embedded_stack" ? globalTime : sourceB ? globalTime - offset : globalTime;
    const withinSource = camera === "embedded_stack" || sourceBAvailable;
    if (withinSource && Math.abs(elements.previewB.currentTime - desired) > .16) elements.previewB.currentTime = desired;
    if (withinSource && state.preview.playing && !elements.previewA.paused && elements.previewB.paused) elements.previewB.play().catch(() => {});
    if (elements.previewA.paused && !elements.previewB.paused) elements.previewB.pause();
    if (!withinSource && !elements.previewB.paused) elements.previewB.pause();
  } else if (!elements.previewB.paused) {
    elements.previewB.pause();
  }
  state.preview.currentCamera = camera;
  updateMediaPreview();
}

function cameraAt(time) {
  const project = playbackProject();
  if (liveEmbeddedCameraRequest()) return "embedded_stack";
  const request = state.sourceMixerLayoutRequest;
  const pendingLayout = request?.projectId === state.project?.id && time >= request.start && time < request.end
    ? request.layout : null;
  const previewLayout = pendingLayout || state.sourceMixerPreviewLayout;
  const plan = previewLayout === "auto" ? project?.draft?.ai_camera_plan : project?.draft?.camera_plan;
  const camera = previewLayout && previewLayout !== "auto"
    ? previewLayout
    : plan?.find((item) => time >= Number(item.start) && time < Number(item.end))?.camera
      || (embeddedLayoutConfirmed() ? "embedded_stack" : "A");
  if (camera === "embedded_stack" && !embeddedLayoutConfirmed()) return "A";
  if (["B", "stacked", "side_by_side", "pip"].includes(camera) && !project?.sources?.B) return "A";
  if (camera === "camera" && !project?.sources?.B) return "A";
  return camera;
}

function refreshEmbeddedCropControls(camera) {
  const embedded = camera === "embedded_stack" && !state.project?.sources?.B;
  const sequence = Boolean(state.project?.editor_sequence);
  const disabled = sequence ? Boolean(state.manualEditBusy || foregroundBusy() || previewUsesSourceTime() || !framingScope(elements.cropSourceSelect?.value || "A")) : embedded;
  for (const control of [elements.cropX, elements.cropY, elements.cropZoom, elements.resetCrop]) {
    if (control) control.disabled = disabled || (embedded && control === elements.cropZoom);
  }
  if (elements.cropSourceSelect) elements.cropSourceSelect.disabled = Boolean(state.manualEditBusy || (embedded && !sequence));
  if (elements.embeddedCropHelp && elements.embeddedCropHelp.hidden === embedded) elements.embeddedCropHelp.hidden = !embedded;
  if (elements.embeddedCropHelp && embedded) elements.embeddedCropHelp.textContent = sequence
    ? "These controls move the screen inside this clip's bottom panel. The camera area stays fixed; zoom is unavailable for this layout."
    : "Use the embedded camera and Main screen focus controls above.";
}

function seekPreview(time, editTime) {
  const project = playbackProject();
  if (!project?.sources?.A) return;
  const duration = timelineDuration(project);
  const value = Math.max(0, Math.min(duration, Number(time) || 0));
  if (previewUsesSourceTime() && state.project?.editor_sequence) state.preview.sourceAnchor = Number.isFinite(editTime)
    ? { projectId: state.project.id, sourceTime: value, editTime } : null;
  if (!Number.isFinite(editTime)) state.preview.sourceUnmapped = false;
  state.preview.seeking = true;
  if (previewUsesIndependentTracks()) independentPreviewClock().seek(value);
  else elements.previewA.currentTime = value;
  syncSecondaryPreview(value);
  state.preview.seeking = false;
  updatePreviewUI(value);
  publishPreviewPlayhead(value, editTime);
}

function previewUsesSourceTime() {
  return state.preview.mode === "source";
}

function setPreviewMode(mode) {
  const editTime = previewTimelineTime();
  pauseAllMedia();
  state.preview.mode = mode === "source" ? "source" : "edit";
  seekSourcePreview(editTime);
}

function seekSourcePreview(time) {
  // The timeline always uses the edit clock. Full source is a separate original
  // A auditioner; map an edit click through its clip without switching modes.
  if (!previewUsesSourceTime() || !state.project?.editor_sequence) { seekPreview(time); return; }
  const project = editorProject();
  const editTime = Math.max(0, Math.min(timelineDuration(project), Number(time) || 0));
  const clips = trackClips(project, "A");
  const clip = clips.find(item => editTime >= Number(item.start) && editTime < Number(item.end))
    || (editTime === timelineDuration(project) ? clips.findLast(item => Math.abs(Number(item.end) - editTime) < .00001) : null);
  const sourceTime = clip ? Number(clip.source_start) + editTime - Number(clip.start) : previewPlaybackTime();
  state.preview.sourceUnmapped = !clip;
  seekPreview(sourceTime, editTime);
}

function nextKeptTime(time) {
  const project = playbackProject();
  const range = project?.draft?.keep_ranges?.find((item) => Number(item.end) > time);
  return range ? Math.max(time, Number(range.start)) : null;
}

function editDuration() {
  const project = editorProject();
  if (state.project?.editor_sequence) return Number(state.project.editor_sequence.duration) || 0;
  return Number(project?.draft?.output_duration || project?.sources?.A?.duration || 0);
}

function hasTimelineFootage() {
  if (!state.project?.editor_sequence) return Boolean(state.project?.draft);
  return ["A", "B"].some((slot) => trackClips(editorProject(), slot).length > 0);
}

function sourceToOutputTime(sourceTime) {
  const project = editorProject();
  const ranges = project?.draft?.keep_ranges || [];
  if (!ranges.length) return Math.max(0, Number(sourceTime) || 0);
  let cursor = 0;
  const time = Math.max(0, Number(sourceTime) || 0);
  for (const range of ranges) {
    const start = Number(range.start), end = Number(range.end);
    if (time < start) return cursor;
    if (time <= end) return cursor + Math.max(0, time - start);
    cursor += Math.max(0, end - start);
  }
  return cursor;
}

function outputToSourceTime(outputTime) {
  const project = editorProject();
  const ranges = project?.draft?.keep_ranges || [];
  if (!ranges.length) return Math.max(0, Number(outputTime) || 0);
  let cursor = 0;
  const target = Math.max(0, Number(outputTime) || 0);
  for (const range of ranges) {
    const start = Number(range.start), end = Number(range.end), length = Math.max(0, end - start);
    if (target < cursor + length) return start + Math.max(0, target - cursor);
    cursor += length;
  }
  return Number(ranges.at(-1)?.end || 0);
}

function updatePreviewUI(time) {
  const project = playbackProject();
  const sourceMode = previewUsesSourceTime();
  const duration = sourceMode ? Number(project?.sources?.A?.duration || 0) : editDuration();
  const outputTime = sourceMode ? time : sourceToOutputTime(time);
  elements.previewTime.textContent = `${formatTime(outputTime)} / ${formatTime(duration)}`;
  elements.previewTime.title = `${sourceMode ? "Full source" : "Edited playback"} · ${t("sourceTime")}: ${formatTime(time, true)}`;
  elements.previewSeek.value = duration ? Math.round(outputTime / duration * 1000) : 0;
  elements.previewSeek.setAttribute("aria-label", sourceMode ? "Seek full source" : "Seek edited video");
  if (elements.previewMode) elements.previewMode.value = sourceMode ? "source" : "edit";
  if (elements.previewModeHint) elements.previewModeHint.textContent = sourceMode
    ? state.preview.sourceUnmapped ? "Full source · no Source A clip at the selected edit position; original position unchanged"
      : inCut(time) ? "Full source · excluded footage is included in playback" : "Full source · plays the original recording"
    : inCut(time) ? "Edited cut · inspecting excluded footage; Play skips to a kept section" : "Edited cut · plays kept sections only; seeking does not change this mode";
  updatePreviewCaption(time);
}

function captionPreviewText(segment, sourceTime, wordsPerCaption) {
  if (!segment) return "";
  const timedWords = Array.isArray(segment.words) ? segment.words.filter((word) => String(word?.word || "").trim()) : [];
  if (timedWords.length) {
    let activeIndex = timedWords.findIndex((word) => sourceTime <= Number(word.end));
    if (activeIndex < 0) activeIndex = timedWords.length - 1;
    const chunkStart = Math.floor(activeIndex / wordsPerCaption) * wordsPerCaption;
    return timedWords.slice(chunkStart, chunkStart + wordsPerCaption).map((word) => String(word.word).trim()).join(" ").trim();
  }
  const words = String(segment.text || "").trim().split(/\s+/).filter(Boolean);
  if (words.length <= wordsPerCaption) return words.join(" ");
  const duration = Math.max(0.01, Number(segment.end) - Number(segment.start));
  const progress = Math.max(0, Math.min(0.999, (sourceTime - Number(segment.start)) / duration));
  const chunkCount = Math.ceil(words.length / wordsPerCaption);
  const chunkStart = Math.floor(progress * chunkCount) * wordsPerCaption;
  return words.slice(chunkStart, chunkStart + wordsPerCaption).join(" ");
}

function updatePreviewCaption(sourceTime) {
  const project = playbackProject();
  if (!elements.previewCaption) return;
  const enabled = captionBurnEnabled();
  const segments = project?.analysis?.transcript?.segments || [];
  if (!enabled || !segments.length) { elements.previewCaption.hidden = true; return; }
  let transcriptTime = sourceTime;
  let captionClip = null;
  if (previewUsesIndependentTracks()) {
    const mixer = sourceMixerSettings();
    const analyzedSlot = project.analysis?.audio_source || project.draft?.audio_source || "A";
    const point = trackAt(project, mixer.audioSlot, sourceTime, mixer.syncOffset);
    const analyzedOffset = analyzedSlot === "B" ? Number(project.analysis?.audio_timeline_offset) : 0;
    if (!point || mixer.audioSlot !== analyzedSlot || !Number.isFinite(analyzedOffset)) {
      elements.previewCaption.hidden = true;
      return;
    }
    transcriptTime = point.sourceTime + analyzedOffset;
    captionClip = { start: Number(point.clip.source_start) + analyzedOffset,
      end: Number(point.clip.source_start) + Number(point.clip.end) - Number(point.clip.start) + analyzedOffset };
  }
  let segment = segments.find((item) => transcriptTime >= Number(item.start) && transcriptTime < Number(item.end));
  if (segment && captionClip) {
    if (Array.isArray(segment.words) && segment.words.length) {
      // Export assigns a boundary word by its midpoint, then clips its timing.
      // Do not show words that belong to an adjacent source clip in this pane.
      const words = segment.words.filter(word => Number(word.end) > Number(word.start)
        && (Number(word.start) + Number(word.end)) / 2 >= captionClip.start
        && (Number(word.start) + Number(word.end)) / 2 < captionClip.end)
        .map(word => ({ ...word, start: Math.max(captionClip.start, Number(word.start)), end: Math.min(captionClip.end, Number(word.end)) }));
      segment = words.length ? { ...segment, words, start: words[0].start, end: words.at(-1).end } : null;
    } else {
      // Wordless transcripts are valid; keep their text and use the clipped
      // segment clock, matching the fallback used by burned/SRT captions.
      segment = { ...segment, start: Math.max(captionClip.start, Number(segment.start)), end: Math.min(captionClip.end, Number(segment.end)) };
    }
    if (segment && (transcriptTime < segment.start || transcriptTime >= segment.end)) segment = null;
  }
  const captionSettings = captionSettingsFromControls();
  const text = captionPreviewText(segment, transcriptTime, captionSettings.words);
  elements.previewCaption.dataset.captionStyle = captionSettings.style;
  elements.previewCaption.dataset.captionPosition = captionSettings.position;
  elements.previewCaption.dataset.captionLayout = cameraAt(sourceTime);
  elements.previewCaption.style.setProperty("--caption-preview-scale", String(captionSettings.scale / 100));
  elements.previewCaption.textContent = text;
  elements.previewCaption.hidden = !text;
}

function firstKeptTime() {
  const project = playbackProject();
  return Number(project?.draft?.keep_ranges?.[0]?.start || 0);
}

function inCut(time) {
  const project = playbackProject();
  return Boolean(project?.draft?.cuts?.some((range) => time >= Number(range.start) && time < Number(range.end)));
}

function toggleAdvanced() {
  setAdvanced(elements.advancedPanel.hidden);
}

function openStudioTab(tab) {
  if (!["timeline", "framing", "transcript", "settings"].includes(tab)) return false;
  if (!state.project?.draft) { toast(t("studioNeedsDraft")); return false; }
  if (foregroundBusy()) { toast(t("directorBusy")); return false; }
  pauseAllMedia();
  setAdvanced(true);
  selectAdvancedTab(tab);
  $(`.advanced-tabs button[data-tab="${tab}"]`)?.focus();
  return true;
}

function setAdvanced(open) {
  const nextOpen = Boolean(open);
  if (nextOpen === state.studio.open) return;
  if (nextOpen && !state.project?.draft) {
    toast(t("studioNeedsDraft"));
    return;
  }

  pauseAllMedia();
  const previewColumn = elements.previewColumn;
  const verdictColumn = elements.verdictColumn;
  if (nextOpen) {
    state.studio.scrollY = window.scrollY;
    elements.advancedPanel.hidden = false;
    document.body.classList.add("studio-open");
    if (previewColumn && elements.studioPreviewDock && previewColumn.parentElement !== elements.studioPreviewDock) {
      elements.studioPreviewDock.appendChild(previewColumn);
    }
    if (verdictColumn && elements.studioDirectorDock && verdictColumn.parentElement !== elements.studioDirectorDock) {
      elements.studioDirectorDock.appendChild(verdictColumn);
    }
    if (elements.resultPanel) elements.resultPanel.inert = true;
    state.studio.open = true;
    updatePreviewUI(previewPlaybackTime());
    dockRuntimeStatus();
    elements.advancedButton.setAttribute("aria-expanded", "true");
    state.timeline.setProject(editorProject());
    applyFramingPreview();
    updateStudioStatus();
    requestAnimationFrame(() => state.timeline?.draw());
    return;
  }

  if (verdictColumn && elements.resultGrid && verdictColumn.parentElement !== elements.resultGrid) {
    elements.resultGrid.appendChild(verdictColumn);
  }
  if (previewColumn && elements.resultGrid && previewColumn.parentElement !== elements.resultGrid) {
    elements.resultGrid.insertBefore(previewColumn, verdictColumn || null);
  }
  if (elements.resultPanel) elements.resultPanel.inert = false;
  document.body.classList.remove("studio-open");
  elements.advancedPanel.hidden = true;
  state.studio.open = false;
  updatePreviewUI(previewPlaybackTime());
  dockRuntimeStatus();
  state.sourceMixerPreviewLayout = null;
  syncSecondaryPreview(previewPlaybackTime());
  elements.advancedButton.setAttribute("aria-expanded", "false");
  window.scrollTo({ top: state.studio.scrollY, behavior: "auto" });
}

function markDraftRebuild(reason = "settings") {
  if (!state.project?.draft) return;
  state.draftDirtyReasons.add(reason);
  localStorage.setItem(`cutroom-draft-dirty:${state.project.id}`, JSON.stringify([...state.draftDirtyReasons]));
  renderDraftRebuildNotice();
}

function loadDraftRebuildState(project) {
  state.draftDirtyReasons.clear();
  if (project?.draft) {
    try {
      const reasons = JSON.parse(localStorage.getItem(`cutroom-draft-dirty:${project.id}`) || "[]");
      if (Array.isArray(reasons)) reasons.forEach((reason) => state.draftDirtyReasons.add(String(reason)));
    } catch {
      localStorage.removeItem(`cutroom-draft-dirty:${project.id}`);
    }
  }
  renderDraftRebuildNotice();
}

function clearDraftRebuild(projectId = state.project?.id) {
  if (projectId) localStorage.removeItem(`cutroom-draft-dirty:${projectId}`);
  if (!projectId || state.project?.id === projectId) {
    state.draftDirtyReasons.clear();
    renderDraftRebuildNotice();
  }
}

function renderDraftRebuildNotice() {
  if (!elements.draftRebuildNotice) return;
  const dirty = Boolean(state.project?.draft && state.draftDirtyReasons.size);
  elements.draftRebuildNotice.hidden = !dirty;
  elements.draftRebuildTitle.textContent = uiCopy("נדרשת בנייה מחדש של ה־Draft", "Draft rebuild required");
  elements.draftRebuildText.textContent = uiCopy("שינויי קצב, אודיו, שפה או פריסה יחולו רק לאחר בנייה מחדש.", "Pace, audio, language and layout changes apply only after rebuilding the Draft.");
  elements.rebuildDraftButton.textContent = uiCopy("בנה Draft מחדש", "Rebuild Draft");
  $$('[data-rebuild-chip]').forEach((chip) => { chip.textContent = uiCopy("דורש Rebuild", "Rebuild Draft"); });
  updateStudioStatus();
  renderDraftActions();
}

async function rebuildDraftFromStudio() {
  if (!state.project?.draft || !state.draftDirtyReasons.size) return;
  pauseAllMedia();
  if (state.studio.open) setAdvanced(false);
  await generateDraft();
}

function renderQuickAspectChoices() {
  if (!elements.quickAspectChoices) return;
  const selected = elements.aspectSelect.value;
  const aspect = selected === "source" ? sourceAspect() : selected;
  $$('button[data-output-aspect]', elements.quickAspectChoices).forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.outputAspect === aspect));
  });
}

function setOutputAspect(aspect) {
  if (!state.project) return;
  if (foregroundBusy() || state.manualEditBusy) {
    // The native select changes before its event fires; restore the latest
    // accepted choice, including a queued save, if editing is currently locked.
    elements.aspectSelect.value = reconcileProjectSnapshot(state.project).settings?.aspect || state.project.draft?.aspect || "9:16";
    renderQuickAspectChoices();
    return;
  }
  if (!["16:9", "9:16", "1:1", "4:5", "source"].includes(aspect)) return;
  elements.aspectSelect.value = aspect;
  const previewAspect = aspect === "source" ? sourceAspect() : aspect;
  elements.previewStage.dataset.aspect = previewAspect;
  if (elements.cropPreview) elements.cropPreview.style.aspectRatio = aspectCss(previewAspect);
  // Output-only change: do not stage a crop, seek, rebuild or invoke AI.
  schedulePatch({ settings: { aspect } });
  applyPreviewPipGeometry(elements.previewStage);
  syncSecondaryPreview(previewPlaybackTime());
  renderSourceCompositionPreview(sourceMixerSettings());
  renderQuickAspectChoices();
  updateStudioStatus();
}

function updateStudioStatus() {
  if (!elements.studioDraftStatus) return;
  const draft = editorProject()?.draft;
  if (!draft) { elements.studioDraftStatus.textContent = ""; return; }
  const selected = elements.aspectSelect?.value || state.project?.settings?.aspect || draft.aspect;
  const aspect = selected === "source" ? sourceAspect() : (selected || "");
  const dirty = state.draftDirtyReasons.size ? ` · ${uiCopy("נדרש Rebuild", "Rebuild required")}` : "";
  elements.studioDraftStatus.textContent = `${formatTime(draft.output_duration || 0)} · ${aspect}${dirty}`;
}

function selectAdvancedTab(tab) {
  if (tab === "framing") loadCropControls(elements.cropSourceSelect?.value || "A", false);
  elements.advancedPanel.classList.toggle("studio-transcript", tab === "transcript");
  let activePanel = null;
  $$(".advanced-tabs button").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  $$(".tab-panel").forEach((panel) => {
    const active = panel.dataset.panel === tab;
    panel.classList.toggle("active", active);
    panel.hidden = !active;
    if (active) activePanel = panel;
  });
  if (tab === "timeline") window.setTimeout(() => state.timeline.draw(), 20);
  if (tab === "transcript") renderTranscript();
  requestAnimationFrame(() => state.timeline?.scheduleDraw?.());
  // Compact layouts have a single page scroller. Edit should reveal the
  // timeline; other tabs reveal their tools. Desktop keeps its player still.
  if (window.matchMedia?.("(max-width: 960px), (max-height: 680px)").matches) {
    const target = tab === "timeline" ? document.getElementById("studioTimelineDock") : activePanel;
    target?.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
  } else if (activePanel?.parentElement) {
    activePanel.parentElement.scrollTop = 0;
  }
}

function handleStudioTabKeydown(event) {
  if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
  const tabs = $$(".advanced-tabs [role='tab']");
  const current = tabs.indexOf(event.currentTarget);
  if (current < 0 || !tabs.length) return;
  const rtl = document.documentElement.dir === "rtl";
  let next = current;
  if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else if (event.key === "ArrowRight") next = (current + (rtl ? -1 : 1) + tabs.length) % tabs.length;
  else if (event.key === "ArrowLeft") next = (current + (rtl ? 1 : -1) + tabs.length) % tabs.length;
  else if (event.key === "ArrowDown") next = (current + 1) % tabs.length;
  else if (event.key === "ArrowUp") next = (current - 1 + tabs.length) % tabs.length;
  event.preventDefault();
  selectAdvancedTab(tabs[next].dataset.tab);
  tabs[next].focus();
}

function updateZoomLabel() {
  elements.timelineZoomLabel.textContent = `${Math.round(state.timeline.zoom * 100)}%`;
}

function applyStoredPreviewCrop(slot) {
  const crop = state.project?.manual?.crop?.[slot] || {};
  const video = slot === "B" ? elements.previewB : elements.previewA;
  if (!video) return;
  const x = Number(crop.x ?? .5) * 100;
  const y = Number(crop.y ?? .5) * 100;
  const zoom = Number(crop.zoom ?? 1);
  video.style.objectPosition = `${x}% ${y}%`;
  video.style.transformOrigin = `${x}% ${y}%`;
  video.style.transform = `scale(${zoom})`;
}

function framingScope(slot) {
  if (!state.project?.editor_sequence || previewUsesSourceTime()) return null;
  const clips = trackClips(editorProject(), slot);
  const range = state.manualSelection;
  if (range) return clips.some(clip => clip.start < range.end && clip.end > range.start) ? { ...range } : null;
  const time = Math.min(Number(state.timeline?.playhead ?? state.preview.editCursor ?? 0), editorDuration() - 1e-7);
  const clip = clips.find(clip => clip.start <= time && time < clip.end);
  return clip ? { start: clip.start, end: clip.end } : null;
}

function loadCropControls(slot, preview = true) {
  if (!state.project || !elements.cropSourceSelect) return;
  const selected = state.project.sources?.[slot] ? slot : "A";
  elements.cropSourceSelect.value = selected;
  state.framingDraft = null;
  const scope = framingScope(selected);
  state.framingScopeKey = `${state.project.id}:${selected}:${scope?.start}:${scope?.end}`;
  const clip = scope && trackClips(editorProject(), selected).find(clip => clip.start < scope.end && clip.end > scope.start);
  const embedded = !state.project.sources?.B && cameraAt(Number(state.timeline?.playhead || 0)) === "embedded_stack";
  const crop = clip?.crop || (embedded ? embeddedCameraCandidate()?.content_focus : state.project.manual?.crop?.[selected]) || {};
  elements.cropX.value = Math.round(Number(crop.x ?? .5) * 100);
  elements.cropY.value = Math.round(Number(crop.y ?? .5) * 100);
  elements.cropZoom.value = Math.round(Number(crop.zoom ?? 1) * 100);
  if (elements.cropScopeStatus) elements.cropScopeStatus.textContent = state.project.editor_sequence
    ? scope ? `Source ${selected} · ${formatTime(scope.start, true)}–${formatTime(scope.end, true)} · only this section`
      : "Select a clip in the edited timeline to adjust its framing."
    : "Default framing for this source · build a draft to frame individual clips.";
  if (preview && !state.project.editor_sequence) applyFramingPreview();
  refreshEmbeddedCropControls(embedded ? "embedded_stack" : cameraAt(Number(state.timeline?.playhead || 0)));
}

function applyFramingPreview() {
  if (!elements.cropVideo || !state.project) return;
  const slot = elements.cropSourceSelect?.value || "A";
  const source = state.project.sources?.[slot] || state.project.sources?.A;
  const x = Number(elements.cropX.value ?? 50);
  const y = Number(elements.cropY.value ?? 50);
  const zoom = Number(elements.cropZoom.value || 100) / 100;
  if (state.project.editor_sequence) {
    const scope = framingScope(slot);
    if (!scope || state.manualEditBusy || foregroundBusy()) return;
    if (!state.framingDraft) {
      pausePreview();
      const time = previewPlaybackTime();
      if (time < scope.start || time >= scope.end) seekSourcePreview(scope.start);
    }
    state.framingDraft = { projectId: state.project.id, slot, scope, crop: { x: x / 100, y: y / 100, zoom } };
  }
  const selectedAspect = elements.aspectSelect.value;
  const previewAspect = selectedAspect === "source" ? sourceAspect() : selectedAspect;
  elements.cropPreview.style.aspectRatio = aspectCss(previewAspect);
  if (elements.previewStage) elements.previewStage.dataset.aspect = previewAspect;
  applyPreviewPipGeometry(elements.previewStage);
  elements.cropVideo.style.objectPosition = `${x}% ${y}%`;
  elements.cropVideo.style.transform = `scale(${zoom})`;
  const cropSourceUrl = sourceMediaUrl(source);
  if (cropSourceUrl && elements.cropVideo.dataset.url !== cropSourceUrl) {
    elements.cropVideo.src = cropSourceUrl;
    elements.cropVideo.dataset.url = cropSourceUrl;
    elements.cropVideo.load();
  }
  const preview = slot === "B" ? elements.previewB : elements.previewA;
  // Generic source crop controls cannot overwrite either embedded pane while
  // paused; that composition has its own camera and camera-free content crops.
  const currentTime = previewPlaybackTime();
  const currentCamera = cameraAt(currentTime);
  const mixer = sourceMixerSettings();
  const crop = { x: x / 100, y: y / 100, zoom };
  applyCompositionCrop(preview, slot, currentCamera, mixer, crop);
  renderSourceCompositionPreview(mixer, { slot, crop });
  refreshEmbeddedCropControls(currentCamera);
  if (currentCamera === "embedded_stack") syncSecondaryPreview(currentTime);
}

function aspectCss(aspect) {
  const values = { "9:16": "9 / 16", "16:9": "16 / 9", "1:1": "1", "4:5": "4 / 5" };
  return values[aspect] || "16 / 9";
}

async function saveCrop() {
  if (!state.project) return;
  const slot = elements.cropSourceSelect?.value || "A";
  const crop = {
    x: Number(elements.cropX.value) / 100,
    y: Number(elements.cropY.value) / 100,
    zoom: Number(elements.cropZoom.value) / 100,
  };
  if (state.project.editor_sequence) {
    const draft = state.framingDraft;
    const scope = draft?.projectId === state.project.id && draft.slot === slot ? draft.scope : framingScope(slot);
    state.framingDraft = null;
    if (!scope) { toast("Select a clip in the edited timeline first."); return; }
    const projectId = state.project.id;
    await applyManualEdit("sequence_crop", { slot, ...scope, ...crop });
    if (state.project?.id === projectId) {
      loadCropControls(slot, false);
      syncSecondaryPreview(previewPlaybackTime());
    }
    return;
  }
  state.project.manual ||= {};
  state.project.manual.crop ||= {};
  state.project.manual.crop[slot] = crop;
  schedulePatch({ manual: { crop: { ...(state.project.manual?.crop || {}), [slot]: crop } } });
}

function renderCameraDetection() {
  const candidate = embeddedCameraCandidate();
  const sourceA = state.project?.sources?.A;
  const hasB = Boolean(state.project?.sources?.B);
  elements.cameraDetection.hidden = !sourceA || hasB || embeddedCameraIsActive();
  if (!sourceA || hasB) return;
  const title = $("b", elements.cameraDetection);
  const help = $("p", elements.cameraDetection);
  const active = embeddedCameraIsActive();
  title.textContent = active
    ? uiCopy("מצלמה פנימית פעילה", "Embedded camera active")
    : candidate
      ? uiCopy("נמצא אזור מצלמה אפשרי", "Possible camera area found")
      : uiCopy("המצלמה לא זוהתה אוטומטית", "Camera was not detected automatically");
  help.textContent = active
    ? uiCopy("אפשר לשנות את המסגרת ידנית ב־Source Mixer. השינוי יופיע מיד בעריכה.", "Adjust the frame manually in Source Mixer; the edit updates immediately.")
    : candidate
      ? uiCopy("בדקו את המסגרת לפני אישור. המערכת לעולם לא תשכפל את המקור בלי בחירה שלכם.", "Check the frame before confirming. CUTROOM never duplicates the source without your choice.")
      : uiCopy("זה לא חוסם את העריכה: פתחו את Source Mixer וסמנו את חלון המצלמה ידנית.", "This does not block editing: use Source Mixer to mark the camera window manually.");
  elements.useEmbeddedCamera.textContent = candidate
    ? active ? uiCopy("שמור שוב", "Save again") : uiCopy("בדוק והשתמש", "Review and use")
    : uiCopy("סמן ידנית", "Mark manually");
}

function setManualSelection(selection) {
  const start = Number(selection?.start);
  const end = Number(selection?.end);
  state.manualSelection = Number.isFinite(start) && Number.isFinite(end) && end - start >= (state.project?.editor_sequence ? 1 / 60 - 1e-6 : .03) ? { start: Math.min(start, end), end: Math.max(start, end) } : null;
  if (state.project?.sources?.B) hydrateSourceMixerLayout();
  renderManualControls();
  renderSourceMixer();
  highlightTranscriptSelection();
  if (state.project?.editor_sequence && elements.cropX && elements.cropSourceSelect) loadCropControls(elements.cropSourceSelect.value, false);
}

function activeEditTarget() {
  return ["A", "B"].includes(state.editTarget) && state.project?.sources?.[state.editTarget] ? state.editTarget : "edit";
}

function targetEditableClips(target = activeEditTarget()) {
  if (state.project?.editor_sequence && target === "edit") return sequenceBlocks(editorProject(), trackClips);
  return target === "edit" ? editableClips(editorProject()) : trackClips(editorProject(), target);
}

function selectedTimelineClip() {
  const range = state.manualSelection;
  return range ? targetEditableClips().find((clip) => Math.abs(clip.start - range.start) < .001 && Math.abs(clip.end - range.end) < .001) : null;
}

function openSourceReview() {
  if (!state.project?.editor_sequence || foregroundBusy() || state.manualEditBusy) return false;
  state.sourceReview ??= new SourceReview({getProject:()=>state.project,applyEdit:applyManualEdit,mediaUrl:sourceMediaUrl,pause:pauseAllMedia,exactInsert:openSourceInsert});
  return state.sourceReview.open(activeEditTarget());
}

function openSourceInsert() {
  if (!state.project?.editor_sequence || foregroundBusy() || state.manualEditBusy) return false;
  if (!openStudioTab("timeline")) return false;
  const target = activeEditTarget();
  const slot = target === "edit" ? transcriptSourceSlot() : target;
  state.timeline?.clearSelection();
  const form = elements.sourceInsertForm;
  form.dataset.projectId = state.project.id;
  form.dataset.target = target;
  elements.sourceInsertSlot.value = slot;
  elements.sourceInsertSlot.disabled = target !== "edit";
  elements.sourceInsertSlot.querySelector('option[value="B"]').disabled = !state.project.sources.B;
  elements.sourceInsertTitle.textContent = "Add source footage";
  elements.sourceInsertIn.value = "00:00.000";
  elements.sourceInsertOut.value = formatSourceTime(Math.min(5, Number(state.project.sources[slot]?.duration || 0)));
  elements.sourceInsertAt.value = formatSourceTime(previewTimelineTime());
  elements.sourceInsertStatus.textContent = target === "edit"
    ? "Inserts the chosen source and shifts both tracks together. The other source is empty during the new footage. Original times: seconds or mm:ss.mmm."
    : `Inserts on ${slot} only; the other track stays still. Original times: seconds or mm:ss.mmm.`;
  form.hidden = false;
  pauseAllMedia();
  elements.sourceInsertIn.focus();
  form.scrollIntoView({ block: "nearest" });
  return true;
}

async function insertSourceFootage(event) {
  event.preventDefault();
  const form = elements.sourceInsertForm, slot = elements.sourceInsertSlot.value;
  if (form.dataset.target !== activeEditTarget()) { form.hidden = true; return; }
  if (form.dataset.projectId !== state.project?.id || !state.project?.sources?.[slot]) { form.hidden = true; return; }
  const sourceStart = parseSourceTime(elements.sourceInsertIn.value), sourceEnd = parseSourceTime(elements.sourceInsertOut.value), start = parseSourceTime(elements.sourceInsertAt.value);
  const sourceDuration = Number(state.project.sources[slot].duration);
  if (![start, sourceStart, sourceEnd].every(Number.isFinite) || start < 0 || sourceStart < 0 || sourceEnd - sourceStart < minimumEditLength() - 1e-6 || sourceEnd > sourceDuration + .0005 || start + sourceEnd - sourceStart > 86400) {
    elements.sourceInsertStatus.textContent = `Choose source times between 0 and ${formatSourceTime(sourceDuration)} and a valid edit position.`;
    return;
  }
  const updated = await applyManualEdit(form.dataset.target === "edit" ? "sequence_insert_linked" : "sequence_insert", { slot, start, source_start: sourceStart, source_end: Math.min(sourceDuration, sourceEnd) });
  if (!updated || updated.id !== form.dataset.projectId || state.project?.id !== updated.id) { elements.sourceInsertStatus.textContent = "Footage was not inserted. Check the times and try again."; return; }
  form.hidden = true;
  setEditTarget(form.dataset.target);
  state.timeline.selectRange(start, start + sourceEnd - sourceStart);
  seekSourcePreview(start);
}

function transcriptSourceSlot() {
  const slot = String(state.project?.analysis?.audio_source || state.project?.draft?.audio_source || "A").toUpperCase();
  return slot === "B" && state.project?.sources?.B ? "B" : "A";
}

function minimumEditLength() {
  const fps = Number(state.project?.settings?.fps);
  return state.project?.editor_sequence ? 1 / ([24, 25, 30, 50, 60].includes(fps) ? fps : 30) : .08;
}

function setEditTarget(target, fromTimeline = false) {
  if (foregroundBusy() || state.transcriptSaving) return;
  const previousTarget = activeEditTarget();
  state.editTarget = ["A", "B"].includes(target) && state.project?.sources?.[target] ? target : "edit";
  if (previousTarget !== state.editTarget && elements.sourceInsertForm) elements.sourceInsertForm.hidden = true;
  if (!fromTimeline) state.timeline?.setEditTarget?.(state.editTarget, false);
  if (state.project?.editor_sequence) {
    if (!fromTimeline) renderManualControls();
    return;
  }
  state.markIn = null;
  // The pointer gesture publishes its selection on release. Avoid collapsing
  // the clip form and moving the canvas under the pointer on target change.
  if (fromTimeline) { state.manualSelection = null; return; }
  setManualSelection(null);
}

// Inputs deliberately use source time, matching the ruler even after removals.
// Accept plain seconds or conventional timecode, never silently swap endpoints.
function parseSourceTime(raw) {
  const value = String(raw ?? "").trim();
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d{1,6})?$/.test(value)) return NaN;
  const parts = value.split(":").map(Number);
  if (parts.slice(1).some((part) => part >= 60)) return NaN;
  const seconds = parts.reduce((total, part) => total * 60 + part, 0);
  return Number.isFinite(seconds) ? seconds : NaN;
}

function formatSourceTime(seconds) {
  const value = Number(seconds);
  const millis = Math.round((Number.isFinite(value) ? Math.max(0, value) : 0) * 1000);
  const minutes = Math.floor(millis / 60000);
  return `${String(minutes).padStart(2, "0")}:${String(Math.floor(millis / 1000) % 60).padStart(2, "0")}.${String(millis % 1000).padStart(3, "0")}`;
}

function rangeInputPending(prefix) {
  const form = elements[`${prefix}RangeForm`];
  return Boolean(form && !form.hidden && form.dataset.dirty === "true");
}

function renderRangeEditors() {
  const duration = editorDuration();
  const range = state.manualSelection;
  const key = JSON.stringify([state.project?.id, range?.start, range?.end, duration]);
  const busy = sourceMixerControlBusy() || Boolean(state.transcriptSaving);
  for (const prefix of ["layout", "timeline"]) {
    const form = elements[`${prefix}RangeForm`];
    if (!form) continue;
    if (form.dataset.selectionKey !== key) {
      form.dataset.selectionKey = key;
      form.dataset.dirty = "false";
      elements[`${prefix}RangeStart`].value = formatSourceTime(range?.start ?? 0);
      elements[`${prefix}RangeEnd`].value = formatSourceTime(range?.end ?? duration);
      for (const boundary of ["Start", "End"]) elements[`${prefix}Range${boundary}`].removeAttribute("aria-invalid");
      elements[`${prefix}RangeStatus`].textContent = `${state.project?.editor_sequence ? "Edit" : "Source"} timeline time · seconds or mm:ss.mmm`;
    }
    for (const control of form.querySelectorAll("input, button")) control.disabled = !state.project?.draft || busy;
  }
  if (elements.layoutScopeBadge) {
    elements.layoutScopeBadge.textContent = range ? "Selected range" : "Entire edit";
    elements.layoutScopeHelp.textContent = !state.project?.draft ? "Build a draft to place layouts on the timeline. Before that, choose a default below."
      : range ? `Changes only ${formatSourceTime(range.start)}–${formatSourceTime(range.end)} on the timeline.`
      : "Applies to the whole video.";
  }
  if (elements.layoutWholeEdit) elements.layoutWholeEdit.hidden = !range;
}

function selectTypedRange(prefix) {
  if (!state.project?.draft || sourceMixerControlBusy() || state.transcriptSaving) return false;
  const first = elements[`${prefix}RangeStart`], last = elements[`${prefix}RangeEnd`];
  const status = elements[`${prefix}RangeStatus`];
  const start = parseSourceTime(first.value), end = parseSourceTime(last.value);
  const duration = editorDuration();
  const invalidStart = !Number.isFinite(start) || start < 0 || start >= duration;
  const invalidEnd = !Number.isFinite(end) || end > duration + .000500001 || Math.min(end, duration) - start < minimumEditLength() - 1e-9;
  first.setAttribute("aria-invalid", String(invalidStart));
  last.setAttribute("aria-invalid", String(invalidEnd));
  if (invalidStart || invalidEnd) {
    status.textContent = `Enter times between 00:00.000 and ${formatSourceTime(duration)}. To must be at least ${minimumEditLength().toFixed(3)} seconds after From.`;
    (invalidStart ? first : last).focus();
    return false;
  }
  if (prefix === "layout" && !state.project?.editor_sequence) setEditTarget("edit");
  pauseAllMedia();
  elements[`${prefix}RangeForm`].dataset.dirty = "false";
  state.timeline?.selectRange(start, Math.min(duration, end));
  seekSourcePreview(start);
  status.textContent = "Range selected. Remove footage, add it back, or choose a layout.";
  if (prefix === "timeline" && elements.manualRange && elements.timelineRangeForm) {
    elements.timelineRangeForm.hidden = true;
    elements.manualRange.setAttribute("aria-expanded", "false");
    elements.manualRange.focus();
  }
  return true;
}

function openTimelineLayout(range) {
  if (!state.project?.draft || foregroundBusy()) return false;
  if (!openStudioTab("framing")) return false;
  if (!state.project?.editor_sequence) setEditTarget("edit");
  if (range && Number.isFinite(Number(range.start)) && Number.isFinite(Number(range.end))) {
    state.timeline?.selectRange(Number(range.start), Number(range.end));
    seekSourcePreview(Number(range.start));
  }
  const target = state.project.sources?.B ? elements.layoutRangeForm : elements.embeddedCameraEditor;
  if (target === elements.embeddedCameraEditor && target) target.open = true;
  (target?.closest?.(".layout-range-panel") || target)?.scrollIntoView({ block: "nearest", behavior: "auto" });
  return true;
}

function manualHistoryCounts() {
  const history = state.project?.manual?.history || state.project?.manual_history || {};
  const undo = Number(history.undo_count ?? history.undo?.length ?? 0);
  const redo = Number(history.redo_count ?? history.redo?.length ?? 0);
  return { undo: Math.max(0, undo || 0), redo: Math.max(0, redo || 0) };
}

function initializeKeyboardProfile() {
  let stored;
  try { stored = localStorage.getItem("cutroom-keyboard-profile"); } catch {}
  state.keyboardProfile = KEYBOARD_PROFILES.some((item) => item.id === stored) ? stored : "cutroom";
  for (const control of [elements.keyboardProfile, elements.keyboardHelpProfile]) {
    control.innerHTML = KEYBOARD_PROFILES.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.label)}</option>`).join("");
  }
  renderKeyboardHelp();
}

function focusTimelineForShortcuts() {
  if (!state.studio.open || !state.project?.draft || document.querySelector("dialog[open]")) return;
  if (elements.timelineCanvas?.checkVisibility?.() === false) return;
  elements.timelineCanvas?.focus({ preventScroll: true });
}

function selectKeyboardProfile(value) {
  state.keyboardProfile = KEYBOARD_PROFILES.some((item) => item.id === value) ? value : "cutroom";
  try { localStorage.setItem("cutroom-keyboard-profile", state.keyboardProfile); } catch {}
  renderKeyboardHelp();
}

function bindKeyboardControls() {
  elements.keyboardProfile.addEventListener("change", () => {
    selectKeyboardProfile(elements.keyboardProfile.value);
    focusTimelineForShortcuts();
  });
  elements.keyboardHelpProfile.addEventListener("change", () => selectKeyboardProfile(elements.keyboardHelpProfile.value));
  elements.keyboardHelp.addEventListener("click", () => { renderKeyboardHelp(); elements.keyboardDialog.showModal(); });
  elements.keyboardDialog.addEventListener("close", focusTimelineForShortcuts);
}

function renderKeyboardHelp() {
  const profile = KEYBOARD_PROFILES.find((item) => item.id === state.keyboardProfile) || KEYBOARD_PROFILES[0];
  elements.keyboardProfile.value = elements.keyboardHelpProfile.value = profile.id;
  elements.keyboardDescription.textContent = profile.description;
  elements.keyboardLimitations.textContent = profile.limitations || "CUTROOM's own editing keys. Commands apply to your current Together, A only or B only scope.";
  const rows = shortcutRows(profile.id);
  const groups = [
    ["Playback & navigation", ["toggle_play", "stop", "play_forward", "frame_back", "frame_forward", "previous_edit", "next_edit", "jump_start", "jump_end"]],
    ["Tools & cuts", ["tool_select", "tool_range", "tool_blade", "tool_remove_between", "split", "delete_selection", "restore_selection"]],
    ["Selection & trimming", ["mark_in", "mark_out", "select_clip", "clear_selection", "trim_start", "trim_end"]],
    ["Timeline view", ["toggle_snapping", "zoom_in", "zoom_out", "fit"]],
    ["Undo & redo", ["undo", "redo"]],
  ];
  const renderRow = (row) => `<div class="shortcut-row"><span>${escapeHtml(row.label)}</span><div class="shortcut-bindings">${row.bindings.map((binding) => `<div><kbd>${escapeHtml(binding.keys)}</kbd>${binding.custom ? '<small class="shortcut-adaptation">CUTROOM adaptation</small>' : ''}${binding.note ? `<small>${escapeHtml(binding.note)}</small>` : ''}</div>`).join("")}</div></div>`;
  const mapped = groups.map(([label, actions]) => {
    const entries = actions.map((action) => rows.find((row) => row.action === action)).filter((row) => row?.bound);
    return entries.length ? `<section class="shortcut-group"><h3>${escapeHtml(label)}</h3>${entries.map(renderRow).join("")}</section>` : "";
  }).join("");
  const unassigned = rows.filter((row) => !row.bound);
  elements.keyboardShortcutList.innerHTML = mapped + (unassigned.length ? `<details class="shortcut-unassigned"><summary>Not assigned in this profile (${unassigned.length})</summary><p>These CUTROOM actions have no key in this preset. Unsupported native commands are not substituted with unrelated edits.</p><ul>${unassigned.map((row) => `<li>${escapeHtml(row.label)}</li>`).join("")}</ul></details>` : "");
}

function setTimelineTool(tool) {
  if (foregroundBusy() || state.transcriptSaving || !state.timeline?.setTool(tool)) return;
  renderTimelineToolStatus();
  elements.timelineCanvas.focus({ preventScroll: true });
}

function renderTimelineToolStatus() {
  const timeline = state.timeline;
  if (!timeline || !elements.timelineCutStatus) return;
  $$('[data-timeline-tool]').forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.timelineTool === timeline.tool));
    button.disabled = !state.project?.draft || foregroundBusy() || state.transcriptSaving || timeline.editPending || (button.dataset.timelineTool === "move" && activeEditTarget() === "edit");
  });
  elements.timelineCutStatus.hidden = !["remove_between", "move"].includes(timeline.tool);
  elements.timelineCutStatus.dataset.tool = timeline.tool;
  elements.cancelTimelineCut.hidden = timeline.cutAnchor == null;
  if (elements.timelineSnap) {
    elements.timelineSnap.textContent = `Snap: ${timeline.snapping ? "on" : "off"}`;
    elements.timelineSnap.setAttribute("aria-pressed", String(Boolean(timeline.snapping)));
  }
  const help = {
    select: state.project?.editor_sequence ? "Drag the middle to reorder without leaving a new gap. Select a clip, then drag its white edges to trim or reveal original footage into a gap. Ruler = seek. Undo restores changes." : "Drag across footage to select. Click a kept or removed section to select it. Drag the time ruler to seek.",
    range: "Drag across footage to select a range, then Remove or Add to edit. Drag its edges to adjust.",
    blade: "Click to cut. Each cut is independent; drag it to move. No need to switch tools.",
    move: state.project?.editor_sequence ? "Move this clip: its old position closes and destination clips shift. No footage is overwritten. In A/B-only mode the other source stays still. Undo restores the move." : "Drag a source clip into an empty space on its own track. Red means overlap; overlapping moves are not applied. The other track stays still.",
  };
  elements.timelineCutHint.textContent = help[timeline.tool] || (timeline.editPending ? "Removing the section…"
    : timeline.cutAnchor != null ? `First cut: ${formatTime(timeline.cutAnchor, true)} · Click the second point in the target track to remove between them. Esc cancels.`
    : "Cut out: click two points in the target track. The section between them is removed. Enter marks at the playhead. Undo restores it.");
}

async function handleTimelineEdit(edit) {
  const target = edit.target || activeEditTarget();
  if (edit.action === "sequence_trim_edge") {
    const projectId = state.project?.id;
    const {action,...detail} = edit;
    const updated = await applyManualEdit(action,detail);
    if (updated && state.project?.id === projectId) {
      const start = edit.edge === "start" ? (!edit.slot && edit.time > edit.start ? edit.start : edit.time) : edit.start;
      const end = edit.edge === "end" ? edit.time : edit.end-(!edit.slot ? Math.max(0,edit.time-edit.start) : 0);
      state.timeline?.selectRange(start,end); seekSourcePreview(start);
    } else state.timeline?.selectRange(edit.start,edit.end);
    return updated;
  }
  if (edit.action === "split" && state.project?.editor_sequence) {
    const frame = minimumEditLength();
    edit = { ...edit, time: Math.round(edit.time / frame) * frame };
  }
  if (edit.action === "split" && state.project?.editor_sequence && state.timeline?.canSplitAt && !state.timeline.canSplitAt(edit.time)) return null;
  if (edit.action === "sequence_move_range") {
    const projectId = state.project?.id;
    const to = rippleMoveStart(editorProject(),edit.start,edit.end,edit.to,edit.slot,trackClips);
    const updated = await applyManualEdit("sequence_move_range", { start: edit.start, end: edit.end, to, mode: "ripple", ...(edit.slot ? { slot: edit.slot } : {}) });
    if (updated && state.project?.id === projectId) { state.timeline?.selectRange(to, to + edit.end - edit.start); seekSourcePreview(to); }
    return updated;
  }
  if (edit.action === "track_move") {
    const clip = trackClips(editorProject(), edit.slot).find((item) => item.id === edit.clip_id);
    const projectId = state.project?.id;
    const start = state.project?.editor_sequence && clip ? rippleMoveStart(editorProject(),clip.start,clip.end,edit.start,edit.slot,trackClips) : edit.start;
    const updated = await applyManualEdit("track_move", { slot: edit.slot, clip_id: edit.clip_id, start, ...(state.project?.editor_sequence ? { mode: "ripple" } : {}) });
    if (updated && clip && state.project?.id === projectId) { state.timeline?.selectRange(start, start + clip.end - clip.start); seekSourcePreview(start); }
    return updated;
  }
  if (edit.action === "split") {
    const projectId = state.project?.id;
    const updated = await applyManualEdit(target === "edit" ? (state.project?.editor_sequence ? "sequence_split_all" : "split") : "track_split", { time: edit.time, ...(target !== "edit" ? { slot: target } : {}) });
    if (updated && state.project?.id === projectId && state.project?.editor_sequence && activeEditTarget() === target) {
      const right = targetEditableClips(target).find(clip => Math.abs(clip.start - edit.time) < 1e-6);
      if (right) state.timeline?.selectRange(right.start, right.end);
    }
    return updated;
  }
  if (edit.action === "delete_range") return applyManualEdit(target === "edit" ? (state.project?.editor_sequence ? "sequence_ripple_delete" : "delete_range") : "track_remove_range", { start: edit.start, end: edit.end, ...(target !== "edit" ? { slot: target } : {}) });
  return null;
}

function resetEditorTransportKey() {
  state.preview.spaceHeld = false;
  state.preview.spaceTarget = null;
}

function handleEditorShortcutKeyUp(event) {
  if (![" ", "Spacebar"].includes(event.key) && event.code !== "Space") return;
  const handled = state.preview.spaceHeld;
  const target = state.preview.spaceTarget;
  resetEditorTransportKey();
  // Suppress only the matching editor press. A Space released after focus
  // moves into a text field/dialog must keep that control's native behavior.
  if (!handled || target !== event.target || !state.studio.open || !state.project?.draft
    || document.querySelector("dialog[open]") || !isEditorTransportSpace(event, { keyup: true })) return;
  event.preventDefault();
  event.stopPropagation?.();
}

function handleEditorShortcut(event) {
  if (!state.studio.open || !state.project?.draft || document.querySelector("dialog[open]")) return;
  if (isEditorTransportSpace(event)) {
    event.preventDefault();
    event.stopPropagation?.();
    const held = state.preview.spaceHeld;
    state.preview.spaceHeld = true;
    state.preview.spaceTarget = event.target;
    if (!event.repeat && !held && !foregroundBusy() && !state.transcriptSaving) togglePreview();
    return;
  }
  // Enter has a local, explicit meaning only while the Cut out canvas is
  // focused; elsewhere Pro Tools retains its normal return-to-start binding.
  if (event.target === elements.timelineCanvas && state.timeline?.tool === "remove_between" && event.key === "Enter"
    && !event.ctrlKey && !event.metaKey && !event.altKey && !event.shiftKey) {
    if (!foregroundBusy() && !state.transcriptSaving) state.timeline.keyDown(event);
    return;
  }
  const action = resolveEditorShortcut(event, state.keyboardProfile);
  const selectedMedia = event.target === elements.timelineCanvas && state.timeline?.mediaSelection
    ? (state.project.manual?.media_clips || []).find(item => item.id === state.timeline.mediaSelection) : null;
  if (selectedMedia && (["delete_selection", "split", "clear_selection"].includes(action)
    || [event.key, event.code].some(key => ["Delete", "Del", "Backspace"].includes(key)))) {
    // This capture listener runs before the canvas. Consume media commands here
    // so neither stale base selections nor the canvas's generic Delete fallback run.
    event.preventDefault();
    event.stopPropagation?.();
    if (!action || foregroundBusy() || state.transcriptSaving || event.repeat) return;
    if (action === "clear_selection") {
      state.timeline.cancelGesture?.();
      state.timeline.mediaSelection = null;
      state.mediaStudio?.select(null);
      state.timeline.scheduleDraw?.();
    } else if (action === "delete_selection") {
      state.timeline.onMediaAction?.("media_remove", { clip_id: selectedMedia.id });
    } else {
      const mediaTime = previewTimelineTime();
      if (mediaTime - selectedMedia.start >= .08 - 1e-9 && selectedMedia.end - mediaTime >= .08 - 1e-9) {
        state.timeline.onMediaAction?.("media_split", { clip_id: selectedMedia.id, time: mediaTime });
      }
    }
    return;
  }
  if (!action || foregroundBusy() || state.transcriptSaving) return;
  const selection = state.manualSelection;
  const time = previewTimelineTime();
  const clips = targetEditableClips();
  const clip = clips.find((item) => time >= item.start && time < item.end);
  if (action === "delete_selection" && !selection) return;
  if (action === "restore_selection" && !selection && !state.project?.editor_sequence) return;
  if (action === "split" && (!clip || (state.project?.editor_sequence && state.timeline?.canSplitAt && !state.timeline.canSplitAt(time)))) return;
  if (["trim_start", "trim_end"].includes(action) && (!clip || time - clip.start < minimumEditLength() - 1e-6 || clip.end - time < minimumEditLength() - 1e-6)) return;
  if (action === "undo" && !manualHistoryCounts().undo) return;
  if (action === "redo" && !manualHistoryCounts().redo) return;
  event.preventDefault();
  if (action === "toggle_play") { togglePreview(); return; }
  if (action === "play_forward") {
    elements.previewA.playbackRate = 1;
    elements.previewB.playbackRate = 1;
    if (!state.preview.playing) togglePreview();
    return;
  }
  if (action === "stop") { pauseAllMedia(); return; }
  if (action === "toggle_snapping") { state.timeline?.setSnapping(!state.timeline.snapping); return; }
  if (action.startsWith("tool_")) { setTimelineTool(action.slice(5)); return; }
  if (action === "clear_selection") {
    const gestureCancelled = state.timeline?.cancelGesture();
    const cutCancelled = state.timeline?.cancelPendingCut?.();
    if (!gestureCancelled && !cutCancelled) state.timeline?.clearSelection();
    state.markIn = null;
    return;
  }
  if (action === "mark_in") {
    state.markIn = { projectId: state.project.id, time };
    state.timeline?.clearSelection();
    toast(`In point: ${formatTime(time, true)}. Press O to mark the end.`, "info", 1800);
    return;
  }
  if (action === "mark_out") {
    const start = state.markIn?.projectId === state.project.id ? state.markIn.time : 0;
    state.timeline?.selectRange(Math.min(start, time), Math.max(start, time));
    return;
  }
  if (action === "select_clip") { if (clip) state.timeline?.selectRange(clip.start, clip.end); return; }
  if (action === "split") { handleTimelineEdit({ action: "split", time }); return; }
  if (action === "trim_start" || action === "trim_end") {
    if (state.project?.editor_sequence && activeEditTarget() === "edit") {
      applyManualEdit("sequence_ripple_delete", { start: action === "trim_start" ? clip.start : time, end: action === "trim_start" ? time : clip.end });
      return;
    }
    if (activeEditTarget() !== "edit") {
      applyManualEdit("track_trim", { slot: activeEditTarget(), clip_id: clip.id,
        start: action === "trim_start" ? time : clip.start, end: action === "trim_end" ? time : clip.end,
        source_start: clip.source_start + (action === "trim_start" ? time - clip.start : 0) });
      return;
    }
    applyManualEdit("trim_clip", { start: clip.start, end: clip.end,
      new_start: action === "trim_start" ? time : clip.start,
      new_end: action === "trim_end" ? time : clip.end });
    return;
  }
  if (action === "delete_selection" || action === "restore_selection") {
    runManualRangeEdit(action === "delete_selection" ? "delete_range" : "restore_range"); return;
  }
  if (action === "undo" || action === "redo") { applyManualEdit(action); return; }
  if (action === "fit") { state.timeline.fit(); elements.timelineZoomLabel.textContent = "100%"; return; }
  if (action === "zoom_in" || action === "zoom_out") {
    state.timeline.setZoom(state.timeline.zoom * (action === "zoom_in" ? 1.35 : 1 / 1.35));
    elements.timelineZoomLabel.textContent = `${Math.round(state.timeline.zoom * 100)}%`;
    return;
  }
  pauseAllMedia();
  if (action === "jump_start" || action === "jump_end") {
    seekSourcePreview(action === "jump_start" ? 0 : editorDuration());
    return;
  }
  if (action === "frame_back" || action === "frame_forward") {
    const fps = Number(state.project?.editor_sequence && !previewUsesSourceTime() ? state.project.settings?.fps : state.project.sources?.A?.fps) || 30;
    const step = (action === "frame_back" ? -1 : 1) / Math.max(1, Math.min(240, fps));
    if (previewUsesSourceTime() && state.project?.editor_sequence) seekPreview(previewPlaybackTime() + step);
    else seekSourcePreview(time + step);
  } else if (action === "previous_edit" || action === "next_edit") {
    const boundaries = [...new Set(clips.flatMap((item) => [item.start, item.end]))].sort((a, b) => a - b);
    const next = action === "previous_edit" ? boundaries.filter((value) => value < time - .001).at(-1) : boundaries.find((value) => value > time + .001);
    if (next != null) seekSourcePreview(next);
  }
}

function renderClipTrim() {
  renderPictureSpeed();
  if (!elements.clipTrimForm) return;
  const range = state.manualSelection;
  const target = activeEditTarget();
  const together = Boolean(state.project?.editor_sequence && target === "edit");
  const clip = range && typeof editableClips === "function" ? targetEditableClips().find((item) => Math.abs(item.start - range.start) <= .001 && Math.abs(item.end - range.end) <= .001) : null;
  const key = clip ? `${state.project.id}:${target}:${clip.id || ""}:${clip.start}:${clip.end}:${clip.source_start}` : "";
  if (elements.clipSourceField) elements.clipSourceField.hidden = target === "edit";
  if (elements.clipMove) elements.clipMove.hidden = target === "edit" && !together;
  elements.clipTrimApply.textContent = together ? "Select these times" : "Apply trim";
  elements.clipTrimForm.hidden = !clip;
  elements.advancedPanel?.classList.toggle("has-clip-selection", Boolean(clip));
  if (!clip) { state.trimClip = null; return; }
  if (state.trimClip?.key !== key) {
    elements.clipTrimIn.value = clip.start.toFixed(3);
    elements.clipTrimOut.value = clip.end.toFixed(3);
    if (elements.clipSourceIn) elements.clipSourceIn.value = Number(clip.source_start || 0).toFixed(3);
    elements.clipTrimStatus.textContent = together ? "Move to start closes the old position and inserts this cut on A+B. No footage is overwritten. Undo restores the move."
      : target === "edit" ? "Non-destructive · undoable" : "Move to start closes the old position and inserts on this track only. The other source stays still. Undo restores the move.";
  }
  state.trimClip = { ...clip, key, projectId: state.project.id };
  elements.clipTrimTitle.textContent = together ? `Clip ${clip.index + 1} · linked A/B` : target === "edit" ? `Clip ${clip.index + 1}` : `Source ${target} clip`;
  const busy = state.manualEditBusy || foregroundBusy();
  for (const control of [elements.clipTrimIn, elements.clipTrimOut, elements.clipTrimApply, elements.clipSourceIn, elements.clipMove]) if (control) control.disabled = busy;
}

async function applySelectedClipTrim(event) {
  event.preventDefault();
  const clip = state.trimClip;
  if (!clip || clip.projectId !== state.project?.id) return;
  const start = Number(elements.clipTrimIn.value), end = Number(elements.clipTrimOut.value);
  if (!elements.clipTrimIn.value.trim() || !elements.clipTrimOut.value.trim() || !Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end - start < minimumEditLength() - 1e-6 || end > (state.project.editor_sequence ? 86400 : Number(state.project.sources.A.duration))) {
    elements.clipTrimStatus.textContent = "Enter valid timeline positions and keep at least one frame."; return;
  }
  const target = activeEditTarget();
  const sourceStart = Number(elements.clipSourceIn?.value);
  if (state.project.editor_sequence && target === "edit") {
    if (end > editorDuration() + .0005) { elements.clipTrimStatus.textContent = "Choose selection times within the edit. To move farther, use Move to start."; return; }
    state.timeline.selectRange(start, end);
    seekSourcePreview(start);
    return;
  }
  if (target !== "edit" && (!elements.clipSourceIn?.value.trim() || !Number.isFinite(sourceStart) || sourceStart < 0)) {
    elements.clipTrimStatus.textContent = "Enter a valid Source in time."; return;
  }
  const updated = target === "edit"
    ? await applyManualEdit("trim_clip", { start: clip.start, end: clip.end, new_start: start, new_end: end })
    : await applyManualEdit("track_trim", { slot: target, clip_id: clip.id, start, end, source_start: sourceStart });
  if (!updated || state.project?.id !== clip.projectId) { elements.clipTrimStatus.textContent = "Trim was not applied. Check the boundaries and try again."; return; }
  state.timeline.selectRange(start, end);
  seekSourcePreview(start);
  elements.clipTrimStatus.textContent = "Trim saved · Undo restores the previous boundaries";
}

function renderManualControls() {
  if (!elements.manualSelectionLabel) return;
  const selection = state.manualSelection;
  const available = Boolean(state.project?.draft);
  const busy = state.manualEditBusy || foregroundBusy();
  const target = activeEditTarget();
  const sequence = Boolean(state.project?.editor_sequence);
  const independent = Boolean(sequence || state.project?.sources?.B || state.project?.manual?.source_tracks?.A);
  if (elements.timelineTargetField) elements.timelineTargetField.hidden = !independent;
  if (elements.timelineTarget) {
    const entireOption = elements.timelineTarget.querySelector('option[value="edit"]');
    if (entireOption) { entireOption.hidden = false; entireOption.disabled = false; entireOption.textContent = sequence ? (state.project.sources?.B ? "Together (A+B)" : "Whole video") : "Entire edit"; }
    elements.timelineTarget.value = target;
    elements.timelineTarget.disabled = !available || busy;
    const bOption = elements.timelineTarget.querySelector('option[value="B"]');
    if (bOption) bOption.disabled = !state.project?.sources?.B;
  }
  elements.advancedPanel?.classList.toggle("has-source-tracks", independent);
  if (elements.trackReset) {
    elements.trackReset.hidden = target === "edit" && !sequence;
    elements.trackReset.disabled = busy || (sequence ? !state.project.editor_sequence.active : !Object.hasOwn(state.project?.manual?.source_tracks || {}, target));
    elements.trackReset.textContent = sequence ? "Reset to AI draft" : `Reset ${target} track`;
  }
  if (elements.trackHelp) {
    elements.trackHelp.hidden = !independent;
    elements.trackHelp.textContent = sequence ? (target === "edit" ? "Together: removal closes the gap on both tracks. Undo restores your changes." : `Editing ${target} only · the other track stays still · removal leaves a gap`)
      : target === "edit" ? "Entire edit: removes time from the final video. Click A or B below to edit only that source."
      : `Editing ${target} only · gaps do not shift the other source · Move clips into empty space · darkened sections are excluded by EDIT.`;
  }
  renderRangeEditors();
  if (elements.manualRange) elements.manualRange.disabled = !available || busy;
  if (elements.manualLayout) elements.manualLayout.disabled = !available || busy;
  if (elements.timelineZoomSelection) elements.timelineZoomSelection.disabled = !available || !selection;
  renderTimelineToolStatus();
  const history = manualHistoryCounts();
  const rangeState = manualRangeState();
  elements.timelineSelectionHint.textContent = sequence ? "Middle = reorder · White edges = trim / extend · Close gaps clears empty time" : "Drag footage = select · Ruler = seek";
  elements.manualSelectionLabel.textContent = selection
    ? `${formatTime(selection.start, true)} – ${formatTime(selection.end, true)} · ${(selection.end - selection.start).toFixed(2)} s${rangeState.valid ? " selected" : " · selection too short"}`
    : sequence ? (hasTimelineFootage() ? "Select a clip, or Range to remove a section" : "Your timeline is empty. Add source footage to continue.") : "Drag footage to select · Ruler to seek";
  elements.manualRestore.textContent = sequence ? "Review original footage…" : target === "edit" ? "Add to edit" : `Restore ${target}`;
  const reviewButton = document.getElementById("reviewSourceButton");
  if (reviewButton) reviewButton.disabled = !sequence || !available || busy;
  const gapButton = document.getElementById("closeTimelineGaps");
  if (gapButton) {
    const gaps = sequence ? sequenceGaps(editorProject(),trackClips,target === "edit" ? null : target) : [];
    gapButton.hidden = !gaps.length;
    gapButton.disabled = !available || busy;
    gapButton.textContent = `Close gaps (${gaps.length})`;
    gapButton.title = target === "edit" ? "Remove only time where both A and B are empty. Both tracks and their layout stay synchronized. Undo available." : `Close empty spaces on ${target} only. The other track stays still. Undo available.`;
  }
  elements.manualDelete.textContent = target === "edit" ? "Remove from video" : `Remove from ${target}`;
  elements.manualSplit.textContent = uiCopy("פצל", "Split");
  elements.manualRestore.disabled = !available || (!sequence && !rangeState.canRestore) || busy || rangeInputPending("timeline");
  elements.manualDelete.disabled = !available || !rangeState.canRemove || busy || rangeInputPending("timeline");
  if (elements.manualClear) elements.manualClear.disabled = !selection || busy;
  elements.manualRestore.title = sequence ? "See all original footage, preview removed sections, and restore or remove a selection" : target === "edit" ? "Return selected source footage that was excluded from the edit" : `Fill gaps in ${target} using its original alignment; the other track stays still`;
  elements.manualDelete.title = target === "edit" ? "Remove this time from both tracks and close the gap. Original media is kept." : `Remove only ${target} in this range; the other track stays still`;
  elements.manualSplit.disabled = !available || busy || (sequence && !state.timeline?.canSplitAt?.(previewTimelineTime()));
  elements.manualUndo.disabled = !available || history.undo < 1 || busy;
  elements.manualRedo.disabled = !available || history.redo < 1 || busy;
  if (elements.transcriptRemove) elements.transcriptRemove.disabled = !available || !manualRangeState("edit").canRemove || busy;
  if (elements.transcriptRestore) elements.transcriptRestore.disabled = !available || !manualRangeState("edit").canRestore || busy;
  if (sequence && elements.transcriptRemove) elements.transcriptRemove.textContent = "Remove from video";
  if (elements.emptyTimeline) elements.emptyTimeline.hidden = !sequence || hasTimelineFootage();
  if (elements.emptyTimelineAdd) elements.emptyTimelineAdd.disabled = busy;
  if (elements.clipDuplicate) elements.clipDuplicate.disabled = !sequence || !selectedTimelineClip() || busy;
  renderClipTrim();
  renderTranscriptDetail(false);
}

function manualRangeState(target = activeEditTarget()) {
  const range = state.manualSelection;
  if (!range || !state.project?.draft || range.end - range.start < minimumEditLength() - 1e-6) return { valid: false, canRemove: false, canRestore: false };
  const duration = editorDuration();
  const start = Math.max(0, range.start), end = Math.min(duration, range.end);
  const kept = targetEditableClips(target).reduce((sum, clip) => sum + Math.max(0, Math.min(end, clip.end) - Math.max(start, clip.start)), 0);
  return { valid: end - start >= minimumEditLength() - 1e-6, canRemove: state.project.editor_sequence && target === "edit" ? end - start >= minimumEditLength() - 1e-6 : kept > .001, canRestore: !state.project.editor_sequence && end - start - kept > .001 };
}

function runManualRangeEdit(action, target = activeEditTarget()) {
  if (state.project?.editor_sequence && action === "restore_range") return openSourceReview();
  if (!state.manualSelection) return;
  const rangeState = manualRangeState(target);
  if (!rangeState.valid || (action === "delete_range" && !rangeState.canRemove) || (action === "restore_range" && !rangeState.canRestore)) return;
  return applyManualEdit(target === "edit" ? (state.project?.editor_sequence && action === "delete_range" ? "sequence_ripple_delete" : action) : action === "delete_range" ? "track_remove_range" : "track_restore_range", { ...state.manualSelection, ...(target !== "edit" ? { slot: target } : {}) });
}

async function applyManualEdit(action, detail = {}, { isCurrent = () => true } = {}) {
  if (state.project?.editor_sequence) {
    action = ({ track_move: "sequence_move", track_split: "sequence_split", track_remove_range: "sequence_remove_range", track_trim: "sequence_trim", set_camera_layout: "sequence_layout", track_reset: "sequence_reset" })[action] || action;
    if (action === "sequence_reset") detail = {};
  }
  if (action === "apply_reel_candidate" && state.draftDirtyReasons.size) {
    toast(t("rebuildBeforeRefine"));
    return null;
  }
  const projectLevelAction = action === "set_source_mixer" || action === "set_embedded_camera";
  if ((!state.project?.draft && !projectLevelAction) || state.manualEditBusy || foregroundBusy() || !isCurrent()) return null;
  state.timeline?.cancelPendingCut?.();
  const projectId = state.project.id;
  const preservedSelection = state.manualSelection ? { ...state.manualSelection } : null;
  const preservedTime = previewTimelineTime();
  // Mixer and layer adjustments do not change the main playback clock. Keep
  // auditioning while their automatic saves run, without reloading the video.
  const liveMediaAction = action === "media_update" || action === "set_audio_mixer";
  let finishManualEdit;
  const manualEditPromise = new Promise((resolve) => { finishManualEdit = resolve; });
  state.manualEditPromise = manualEditPromise;
  state.manualEditBusy = true;
  if (!liveMediaAction) pausePreview();
  renderReadiness();
  renderManualControls();
  renderSourceMixer();
  try {
    await flushProjectSaves(projectId);
    if (state.project?.id !== projectId || !isCurrent()) return null;
    const expectedRevision = saveQueueFor(projectId, state.project?.revision).revision;
    const submit = (revision) => api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`, {
      method: "POST",
      body: JSON.stringify({ action, ...detail, expected_revision: revision }),
    });
    let payload;
    try {
      payload = await submit(expectedRevision);
    } catch (error) {
      if (!isRevisionConflict(error) || state.project?.id !== projectId || action === "transcript_text") throw error;
      const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (!latest?.project || (!latest.project.draft && !projectLevelAction)) throw error;
      state.project = latest.project;
      rememberProjectRevision(state.project);
      if (!isCurrent()) return null;
      if (action.startsWith("sequence_")) {
        renderDraft();
        state.timeline?.clearSelection();
        throw new Error("The edit changed elsewhere. The latest version is loaded; select the clip again and retry.");
      }
      payload = await submit(saveQueueFor(projectId, state.project.revision).revision);
    }
    if (!payload?.project) throw new Error("Manual edit did not return an updated project");
    rememberProjectRevision(payload.project);
    if (state.project?.id !== projectId || !isCurrent()) return payload.project;
    state.project = payload.project;
    if (liveMediaAction) {
      state.mediaStudio?.render();
      if (state.timeline) { state.timeline.project = editorProject(); state.timeline.scheduleDraw(); }
      updateMediaPreview();
      return state.project;
    }
    elements.projectName.value = state.project.name || "";
    hydrateSettings();
    if (state.project.draft) renderDraft();
    else {
      renderSources();
      renderSourceMixer();
    }
    if (action === "sequence_ripple_delete" || action === "sequence_close_gaps") {
      state.timeline?.clearSelection();
      state.markIn = null;
      seekSourcePreview(Math.min(action === "sequence_close_gaps" ? preservedTime : Number(detail.start), editorDuration()));
    } else {
      if (preservedSelection) state.timeline.selectRange(preservedSelection.start, preservedSelection.end);
      else setManualSelection(null);
      seekSourcePreview(preservedTime);
    }
    renderManualControls();
    return state.project;
  } catch (error) {
    toast(`${uiCopy("התיקון הידני נכשל", "Manual correction failed")}: ${error.message}`);
    return null;
  } finally {
    state.manualEditBusy = false;
    finishManualEdit();
    if (state.manualEditPromise === manualEditPromise) state.manualEditPromise = null;
    renderReadiness();
    renderManualControls();
    renderSourceMixer();
  }
}

function beginTranscriptEdit(row, segment) {
  selectTranscriptLine(segment);
  elements.transcriptEditText.focus();
}

function transcriptBufferKey(segmentId) { return `${state.project?.id}:${segmentId}`; }

function pendingTranscriptBuffers() {
  return [...state.transcriptBuffers.values()].filter((item) => item.projectId === state.project?.id);
}

function requireSavedTranscript() {
  if (!pendingTranscriptBuffers().length) return true;
  toast("Save or discard your transcript changes before rebuilding or exporting.");
  openStudioTab("transcript");
  return false;
}

function selectedTranscriptSegment() {
  if (state.transcriptActive?.projectId !== state.project?.id) return null;
  return state.project?.analysis?.transcript?.segments?.find((item) => String(item.id) === state.transcriptActive.id) || null;
}

function transcriptTimelineMapping(start, end) {
  start = Number(start); end = Number(end);
  const project = editorProject();
  if (!hasSourceTracks(project)) return { ranges: [{ start, end }], independent: false };
  const analysis = project?.analysis || {};
  const sourceSlot = String(analysis.audio_source || project?.draft?.audio_source || "A").toUpperCase();
  const offset = sourceSlot === "B" ? Number(analysis.audio_timeline_offset) : 0;
  const mixer = sourceMixerSettings();
  const base = { independent: true, sourceSlot, sourceStart: start - offset, sourceEnd: end - offset };
  if (mixer.audioSlot !== sourceSlot || !project?.sources?.[sourceSlot]?.has_audio) {
    return { ...base, ranges: [], reason: "audio_changed" };
  }
  if (!Number.isFinite(offset) || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return { ...base, ranges: [], reason: "unknown_clock" };
  }
  const ranges = [];
  for (const clip of trackClips(project, sourceSlot, mixer.syncOffset)) {
    const sourceStart = Number(clip.source_start) + offset;
    const sourceEnd = sourceStart + Number(clip.end) - Number(clip.start);
    const left = Math.max(start, sourceStart), right = Math.min(end, sourceEnd);
    if (right > left) ranges.push({ start: Number(clip.start) + left - sourceStart, end: Number(clip.start) + right - sourceStart });
  }
  ranges.sort((a, b) => a.start - b.start || a.end - b.end);
  const merged = [];
  for (const range of ranges) {
    const last = merged.at(-1);
    // Only floating-point dust may bridge clips. A real gap can contain other
    // speech/video and must never be included by a transcript Remove action.
    if (last && range.start <= last.end + 1e-7) last.end = Math.max(last.end, range.end);
    else merged.push({ ...range });
  }
  return { ...base, ranges: merged, reason: merged.length ? merged.length > 1 ? "disjoint" : null : "not_on_track" };
}

function transcriptMappingLabel(segment, mapping) {
  if (!mapping.independent) return `${formatTime(segment.start, true)} – ${formatTime(segment.end, true)}`;
  const original = Number.isFinite(mapping.sourceStart) && Number.isFinite(mapping.sourceEnd)
    ? `Source ${mapping.sourceSlot} ${formatTime(mapping.sourceStart, true)} – ${formatTime(mapping.sourceEnd, true)}`
    : `Original transcript ${formatTime(segment.start, true)} – ${formatTime(segment.end, true)}`;
  if (mapping.ranges.length === 1) return `Timeline ${formatTime(mapping.ranges[0].start, true)} – ${formatTime(mapping.ranges[0].end, true)} · ${original}`;
  return `${original} · ${mapping.ranges.length > 1 ? `${mapping.ranges.length} separate timeline sections` : mapping.reason === "audio_changed" ? "Audio source changed" : "Not on the current audio track"}`;
}

function transcriptMappingRemoved(mapping) {
  const duration = mapping.ranges.reduce((sum, range) => sum + range.end - range.start, 0);
  const removed = mapping.ranges.reduce((sum, item) => sum + (editorProject()?.draft?.cuts || []).reduce((cutSum, cut) =>
    cutSum + Math.max(0, Math.min(item.end, Number(cut.end)) - Math.max(item.start, Number(cut.start))), 0), 0);
  return !duration || removed >= duration * .5;
}

function selectTranscriptLine(segment, extend = false) {
  if (state.transcriptSaving) return;
  pauseAllMedia();
  const anchor = extend && state.transcriptAnchor?.projectId === state.project?.id ? state.transcriptAnchor : null;
  state.transcriptActive = { projectId: state.project.id, id: String(segment.id) };
  if (!anchor) state.transcriptAnchor = { projectId: state.project.id, start: Number(segment.start), end: Number(segment.end) };
  const start = Math.min(anchor?.start ?? Number(segment.start), Number(segment.start));
  const end = Math.max(anchor?.end ?? Number(segment.end), Number(segment.end));
  const mapping = transcriptTimelineMapping(start, end);
  if (mapping.independent && !state.project?.editor_sequence) setEditTarget("edit");
  if (mapping.ranges.length === 1) {
    state.timeline?.selectRange(mapping.ranges[0].start, mapping.ranges[0].end);
    const lineMapping = transcriptTimelineMapping(segment.start, segment.end);
    seekSourcePreview(lineMapping.ranges[0]?.start ?? mapping.ranges[0].start);
  } else {
    state.timeline?.clearSelection?.();
    setManualSelection(null);
    toast(mapping.reason === "audio_changed"
      ? "This transcript belongs to a different audio source. Rebuild the Draft to use it for cutting; you can still edit the text."
      : mapping.ranges.length > 1
        ? "This passage is in separate timeline sections. Select one section on the timeline to remove it. You can still edit its text."
        : "This passage is not on the current audio track. Restore its source clip on the timeline to select it. You can still edit the text.");
  }
  renderTranscriptDetail();
  highlightTranscriptSelection();
}

function bufferTranscriptText() {
  const segment = selectedTranscriptSegment();
  if (!segment || state.transcriptSaving) return;
  const key = transcriptBufferKey(segment.id);
  const previous = state.transcriptBuffers.get(key);
  const text = elements.transcriptEditText.value;
  if (text === String(segment.text || "")) state.transcriptBuffers.delete(key);
  else state.transcriptBuffers.set(key, { projectId: state.project.id, id: segment.id, base: previous?.base ?? String(segment.text || ""), text, start: Number(segment.start), end: Number(segment.end) });
  renderTranscriptDetail(false);
}

function discardTranscriptBuffer() {
  const segment = selectedTranscriptSegment();
  if (!segment || state.transcriptSaving) return;
  state.transcriptBuffers.delete(transcriptBufferKey(segment.id));
  renderTranscriptDetail();
}

async function saveTranscriptBuffers(all = true) {
  const segment = selectedTranscriptSegment();
  const buffers = pendingTranscriptBuffers().filter((item) => all || String(item.id) === String(segment?.id));
  if (!buffers.length) return true;
  if (state.transcriptSaving || state.manualEditBusy || foregroundBusy()) return false;
  state.transcriptSaving = true;
  renderTranscriptDetail(false);
  try {
    for (const item of buffers) {
      if (state.project?.id !== item.projectId) return false;
      const current = state.project.analysis?.transcript?.segments?.find((row) => String(row.id) === String(item.id));
      if (!current || String(current.text || "") !== item.base || Number(current.start) !== item.start || Number(current.end) !== item.end) {
        toast("This transcript changed since you started typing. Your text is preserved; copy it before discarding and reviewing the updated line.");
        return false;
      }
      if (!item.text.trim()) { toast("A transcript line cannot be empty. Use Remove passage to cut footage."); return false; }
      const updated = await applyManualEdit("transcript_text", { segment_id: item.id, start: item.start, end: item.end, text: item.text.trim() });
      if (!updated) return false;
      state.transcriptBuffers.delete(`${item.projectId}:${item.id}`);
    }
    return true;
  } finally {
    state.transcriptSaving = false;
    renderTranscript();
  }
}

function renderTranscriptDetail(replaceText = true) {
  if (!elements.transcriptEditForm) return;
  const segment = selectedTranscriptSegment();
  elements.transcriptEditForm.hidden = !segment;
  elements.advancedPanel?.classList.toggle("transcript-editing", Boolean(segment));
  if (!segment) return;
  const buffer = state.transcriptBuffers.get(transcriptBufferKey(segment.id));
  const busy = state.transcriptSaving || state.manualEditBusy || foregroundBusy();
  if (replaceText) elements.transcriptEditText.value = buffer?.text ?? String(segment.text || "");
  elements.transcriptEditText.disabled = busy;
  elements.transcriptEditTime.textContent = transcriptMappingLabel(segment, transcriptTimelineMapping(segment.start, segment.end));
  const quality = state.project?.analysis?.transcript_quality;
  const flagged = Array.isArray(quality?.review_segments) && quality.review_segments.some(item =>
    item && String(item.segment_id) === String(segment.id));
  let reviewNote = elements.transcriptEditForm.querySelector(".transcript-line-review");
  if (!reviewNote && flagged) {
    reviewNote = document.createElement("p");
    reviewNote.className = "transcript-line-review";
    reviewNote.id = "transcriptLineReview";
    elements.transcriptEditForm.insertBefore(reviewNote, elements.transcriptEditText);
  }
  if (reviewNote) {
    reviewNote.hidden = !flagged;
    reviewNote.textContent = flagged
      ? "Original AI confidence was low for this line. Listen and check names or mixed-language words. Saving text does not recheck the audio."
      : "";
  }
  const count = pendingTranscriptBuffers().length;
  elements.transcriptEditStatus.textContent = state.transcriptSaving ? "Saving…" : buffer ? `Unsaved · ${count} changed line${count === 1 ? "" : "s"}` : count ? `Saved · ${count} other unsaved line${count === 1 ? "" : "s"}` : "Saved · captions updated without rebuilding";
  elements.transcriptSave.disabled = busy || !buffer || !buffer.text.trim();
  elements.transcriptDiscard.disabled = busy || !buffer;
  elements.transcriptSaveAll.disabled = busy || !count;
  const segments = state.project.analysis.transcript.segments;
  const index = segments.indexOf(segment);
  elements.transcriptPrevious.disabled = busy || index <= 0;
  elements.transcriptNext.disabled = busy || index >= segments.length - 1;
}

function moveTranscriptLine(direction) {
  const segments = state.project?.analysis?.transcript?.segments || [];
  const index = segments.indexOf(selectedTranscriptSegment());
  const next = segments[index + direction];
  if (next) selectTranscriptLine(next);
}

function highlightTranscriptSelection() {
  if (!elements.transcriptList) return;
  const selection = state.manualSelection;
  $$('.transcript-row', elements.transcriptList).forEach((row) => {
    const ranges = row.dataset.timelineRanges ? JSON.parse(row.dataset.timelineRanges) : [{ start: Number(row.dataset.start), end: Number(row.dataset.end) }];
    const selected = Boolean(selection && ranges.some(range => range.start < selection.end && range.end > selection.start));
    row.classList.toggle("selected", selected);
    $('.transcript-seek', row)?.setAttribute("aria-pressed", String(selected));
  });
}

function renderTranscript() {
  if (!elements.transcriptList) return;
  const query = elements.transcriptSearch.value.trim().toLowerCase();
  const transcript = state.project?.analysis?.transcript;
  const segments = transcript?.segments || [];
  const quality = state.project?.analysis?.transcript_quality;
  const reviewIds = new Set((Array.isArray(quality?.review_segments) ? quality.review_segments : [])
    .filter(item => item && item.segment_id != null).map(item => String(item.segment_id)));
  const markedCount = segments.filter(segment => reviewIds.has(String(segment.id))).length;
  const reportedCount = Number(quality?.review_segment_count);
  const reviewCount = Math.min(segments.length, Math.max(markedCount, Number.isFinite(reportedCount) ? Math.trunc(reportedCount) : 0));
  const transcriptCard = elements.transcriptList.parentElement;
  let qualityNote = transcriptCard?.querySelector(".transcript-quality-note");
  if (!qualityNote && reviewCount > 0 && transcriptCard) {
    qualityNote = document.createElement("p");
    qualityNote.className = "transcript-quality-note";
    qualityNote.setAttribute("role", "status");
    transcriptCard.insertBefore(qualityNote, elements.transcriptList);
  }
  if (qualityNote) {
    qualityNote.hidden = reviewCount === 0;
    qualityNote.textContent = reviewCount > 0
      ? `AI review: ${reviewCount} line${reviewCount === 1 ? " was" : "s were"} flagged. Listen before using captions; confidence is not measured accuracy.${reviewCount > markedCount ? ` Only ${markedCount} ${markedCount === 1 ? "flag has" : "flags have"} line markers; search and filters may hide them.` : ""}`
      : "";
  }
  const previousScroll = elements.transcriptList.scrollTop;
  renderLanguageDetectionStatus();
  elements.transcriptLanguage.textContent = transcript
    ? `${segments.length} line${segments.length === 1 ? "" : "s"} · ${transcript.model || languageName(transcript.language)}`
    : "No transcript yet";
  elements.transcriptList.innerHTML = "";
  let visible = 0;
  for (const segment of segments) {
    if (query && !String(segment.text).toLowerCase().includes(query)) continue;
    const mapping = transcriptTimelineMapping(segment.start, segment.end);
    const removed = mapping.independent ? transcriptMappingRemoved(mapping) : rangeMostlyRemoved(segment.start, segment.end);
    const filter = elements.transcriptFilter?.value || "all";
    if ((filter === "kept" && removed) || (filter === "removed" && !removed)) continue;
    visible += 1;
    const row = document.createElement("div");
    row.className = `transcript-row${removed ? " removed" : ""}`;
    row.dataset.start = String(mapping.ranges[0]?.start ?? segment.start);
    row.dataset.end = String(mapping.ranges.at(-1)?.end ?? segment.end);
    row.dataset.timelineRanges = JSON.stringify(mapping.ranges);
    row.innerHTML = `<button class="transcript-seek" type="button"><time></time><span class="transcript-text"></span><b></b></button><button class="transcript-edit" type="button" aria-label="Edit transcript">✎</button>`;
    const seek = $(".transcript-seek", row);
    $("time", seek).textContent = mapping.independent
      ? mapping.ranges.length === 1 ? `T ${formatTime(mapping.ranges[0].start, true)}`
        : `${mapping.sourceSlot} ${formatTime(Number.isFinite(mapping.sourceStart) ? mapping.sourceStart : segment.start, true)}`
      : formatTime(segment.start, true);
    seek.title = transcriptMappingLabel(segment, mapping);
    $(".transcript-text", seek).textContent = segment.text;
    $(".transcript-text", seek).setAttribute("dir", "auto");
    if (reviewIds.has(String(segment.id))) {
      const badge = document.createElement("small");
      badge.className = "transcript-review-badge";
      badge.textContent = "Review";
      badge.setAttribute("dir", "ltr");
      badge.title = "Original AI confidence was low. Listen and review this line.";
      $(".transcript-text", seek).append(badge);
      seek.title += " · AI review: low confidence";
    }
    $("b", seek).textContent = mapping.independent && !mapping.ranges.length
      ? mapping.reason === "audio_changed" ? "Audio changed" : "Not on track"
      : removed ? "Removed" : "In edit";
    seek.addEventListener("click", (event) => selectTranscriptLine(segment, event.shiftKey));
    $(".transcript-edit", row).setAttribute("aria-label", uiCopy("ערוך תמלול", "Edit transcript"));
    $(".transcript-edit", row).addEventListener("click", () => beginTranscriptEdit(row, segment));
    elements.transcriptList.append(row);
  }
  if (!visible) {
    const empty = document.createElement("p"); empty.className = "transcript-empty";
    empty.textContent = segments.length ? "No matching lines. Try another search or filter." : "Your transcript will appear here after analysis.";
    elements.transcriptList.append(empty);
  }
  elements.transcriptList.scrollTop = previousScroll;
  if (elements.transcriptResults) elements.transcriptResults.textContent = `${visible} of ${segments.length} lines`;
  highlightTranscriptSelection();
  renderTranscriptDetail();
}

function rangeMostlyRemoved(start, end) {
  const duration = Number(end) - Number(start);
  const removed = (state.project?.draft?.cuts || []).reduce((sum, range) => sum + Math.max(0, Math.min(Number(end), Number(range.end)) - Math.max(Number(start), Number(range.start))), 0);
  return duration > 0 && removed >= duration * .5;
}

function renderRecentProjects() {
  elements.recentList.innerHTML = "";
  const projects = state.projects.slice(0, 6);
  elements.recentProjects.hidden = projects.length === 0;
  elements.recentCount.textContent = String(projects.length);
  for (const project of projects) {
    const button = document.createElement("button");
    button.className = "recent-project";
    button.innerHTML = `<strong></strong><small></small>`;
    $("strong", button).textContent = project.name;
    $("small", button).textContent = `${project.has_draft ? "EDIT" : "RAW"} · ${formatDate(project.updated_at)}`;
    button.addEventListener("click", () => runUiAction(() => openProject(project.id)));
    elements.recentList.append(button);
  }
}

function openProjectsDialog() {
  renderProjectDialog();
  elements.projectsDialog.showModal();
}

function renderProjectDialog() {
  if (!elements.dialogProjects) return;
  elements.dialogProjects.innerHTML = "";
  if (!state.projects.length) {
    const empty = document.createElement("p"); empty.textContent = t("noProjects"); elements.dialogProjects.append(empty); return;
  }
  for (const project of state.projects) {
    const row = document.createElement("div");
    row.className = "dialog-project-row";
    const button = document.createElement("button");
    button.className = "dialog-project";
    button.type = "button";
    button.innerHTML = `<span><strong></strong><small></small></span><b></b>`;
    $("strong", button).textContent = project.name;
    $("small", button).textContent = formatDate(project.updated_at);
    $("b", button).textContent = project.has_draft ? "EDIT" : "RAW";
    button.addEventListener("click", () => runUiAction(async () => { elements.projectsDialog.close(); await openProject(project.id); }));
    const remove = document.createElement("button");
    remove.className = "dialog-project-delete icon-button";
    remove.type = "button";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `${uiCopy("מחק פרויקט", "Delete project")}: ${project.name}`);
    remove.addEventListener("click", () => runUiAction(() => deleteProject(project)));
    row.append(button, remove);
    elements.dialogProjects.append(row);
  }
}

async function deleteProject(project) {
  if (!project?.id) return;
  if (projectHasForegroundWork(project.id)) {
    toast(uiCopy("אי אפשר למחוק פרויקט בזמן שמתבצעת בו עבודה", "Wait for the active job before deleting this project"));
    return;
  }
  const confirmed = window.confirm(uiCopy(`למחוק את "${project.name}" ואת קובצי הפרויקט המקומיים?`, `Delete “${project.name}” and its local project files?`));
  if (!confirmed) return;
  const deletingCurrent = state.project?.id === project.id;
  if (deletingCurrent && !(await flushCurrentProjectSaves())) return;
  if (deletingCurrent) {
    releaseMediaHandles();
    await new Promise((resolve) => window.setTimeout(resolve, 150));
  }
  try {
    await api(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
  } catch (error) {
    if (deletingCurrent && state.project?.id === project.id) renderDraft();
    throw error;
  }
  const queue = state.saveQueues.get(project.id);
  if (queue?.timer) clearTimeout(queue.timer);
  state.saveQueues.delete(project.id);
  localStorage.removeItem(`cutroom-draft-dirty:${project.id}`);
  state.projects = state.projects.filter((item) => item.id !== project.id);
  clearRememberedProject(project.id);
  renderRecentProjects();
  renderProjectDialog();
  if (state.project?.id === project.id) {
    state.project = null;
    state.projectViewToken += 1;
    elements.projectsDialog.close();
    showWelcome();
  }
  toast(uiCopy("הפרויקט נמחק", "Project deleted"), "success");
}

function formatDate(value) {
  try { return new Intl.DateTimeFormat(state.locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
  catch { return value || ""; }
}

function openExportDialog({ progress = false } = {}) {
  if (!progress && !requireSavedTranscript()) return;
  if (!state.project?.draft) return;
  if (!progress && !hasTimelineFootage()) { toast("Add footage to the timeline before exporting."); openSourceReview(); return; }
  pauseAllMedia();
  if (!progress && state.draftDirtyReasons.size) {
    toast(uiCopy("יש לבנות מחדש את ה־Draft לפני הייצוא", "Rebuild the Draft before exporting these editorial changes"));
    if (state.studio.open) selectAdvancedTab("settings");
    return;
  }
  const settings = state.project.settings;
  const draft = editorProject().draft;
  elements.exportSummary.innerHTML = "";
  const values = [
    [settings.aspect, t("aspect")],
    [`${settings.resolution || "1080"}p`, t("resolution")],
    [formatTime(draft.output_duration), t("targetLength")],
  ];
  for (const [value, label] of values) {
    const node = document.createElement("div"); node.innerHTML = `<b></b><small></small>`; $("b", node).textContent = value; $("small", node).textContent = label; elements.exportSummary.append(node);
  }
  elements.exportProgress.hidden = !progress;
  elements.exportActions.hidden = progress;
  elements.exportTitle.textContent = progress ? "Exporting your video" : t("readyToExport");
  elements.exportDescription.textContent = progress ? "You can stop this export at any time. Your edit stays saved." : t("exportHelp");
  updateFrameRateControls(settings.fps ?? 30);
  elements.exportFrameRateField.hidden = progress;
  // The backend keeps exports newest-first so the default download must never
  // silently point to an older render after a project has multiple exports.
  const latestExport = !progress && Array.isArray(state.project.exports) ? state.project.exports[0] : null;
  if (latestExport?.url && latestExport?.name) {
    elements.downloadExport.href = latestExport.url;
    elements.downloadExport.download = latestExport.name;
    elements.downloadExport.textContent = `Download previous export (${latestExport.fps || 30} FPS)`;
    elements.downloadExport.hidden = false;
  } else {
    elements.downloadExport.hidden = true;
  }
  elements.confirmExport.disabled = foregroundBusy();
  if (!elements.exportDialog.open) elements.exportDialog.showModal();
}

async function startExport() {
  if (state.mediaStudio && !(await state.mediaStudio.flush())) return;
  if (!requireSavedTranscript()) return;
  if (!state.project?.draft) return;
  if (!hasTimelineFootage()) { toast("Add footage to the timeline before exporting."); return; }
  if (state.draftDirtyReasons.size) { toast(t("rebuildBeforeRefine")); return; }
  pauseAllMedia();
  const projectId = state.project.id;
  if (liveEmbeddedCameraRequest() && (!(await flushEmbeddedCameraSave(projectId)) || state.project?.id !== projectId)) return;
  const lock = acquireJobStartLock("render", projectId);
  if (!lock) { toast(uiCopy("כבר מתבצעת עבודה", "Another job is already running")); return; }
  elements.exportActions.hidden = true;
  elements.exportProgress.hidden = false;
  elements.exportFrameRateField.hidden = true;
  elements.exportTitle.textContent = "Exporting your video";
  elements.exportDescription.textContent = "You can stop this export at any time. Your edit stays saved.";
  elements.downloadExport.hidden = true;
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId) throw new Error("Cancelled");
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/render`, { method: "POST", body: JSON.stringify({ quality: elements.qualitySelect.value, fps: selectedFrameRate() }) });
    setActiveJob(payload.job.id, { projectId, kind: "render" });
    const job = await pollExportJob(payload.job.id, projectId);
    await completeExportJob(job, projectId);
  } catch (error) {
    if (state.project?.id === projectId) {
      elements.exportActions.hidden = false;
      elements.exportProgress.hidden = true;
      elements.exportFrameRateField.hidden = false;
      elements.exportTitle.textContent = error.message === "Cancelled" ? "Export stopped" : "Export needs attention";
      elements.exportDescription.textContent = error.message === "Cancelled" ? "Your edit is saved. Start another export whenever you are ready." : friendlyRenderError(error.message);
    }
    if (error.message !== "Cancelled") {
      const message = error?.code === "insufficient_storage"
        ? t("notEnoughRenderDisk")
          .replace("{required}", formatBytes(error.payload?.required_free_bytes || error.payload?.required_bytes || 0))
          .replace("{free}", formatBytes(error.payload?.disk_free_bytes || 0))
        : `${t("exportFailed")}: ${friendlyRenderError(error.message)}`;
      toast(message);
    }
  } finally {
    if (!state.activeJob) state.cancelBeforeStart = false;
    releaseJobStartLock(lock);
  }
}

function friendlyRenderError(message) {
  const value = String(message || "");
  if (value === "captions_out_of_date" || value.includes("Captions no longer match")) {
    return uiCopy(
      "מקור האודיו או הסנכרון השתנו מאז יצירת הכתוביות. בנו את ה־Draft מחדש ואז ייצאו.",
      "The audio source or sync changed after captions were created. Rebuild the Draft, then export again.",
    );
  }
  return value;
}

async function resumeExportJob(job) {
  const projectId = job.project_id || state.project?.id;
  if (!projectId || foregroundBusy()) return;
  openExportDialog({ progress: true });
  setActiveJob(job.id, { projectId, kind: "render", resumed: true });
  updateExportProgress(job);
  try {
    const completed = await pollExportJob(job.id, projectId);
    await completeExportJob(completed, projectId);
  } catch (error) {
    if (state.project?.id === projectId) {
      elements.exportProgress.hidden = true;
      elements.exportActions.hidden = false;
      elements.exportFrameRateField.hidden = false;
    }
    throw error;
  }
}

function updateExportProgress(job) {
  const percent = Math.round(Number(job?.progress || 0) * 100);
  const cancelling = jobCancellationRequested(job);
  elements.exportProgress.style.setProperty("--progress", `${percent}%`);
  $("b", elements.exportProgress).textContent = `${percent}%`;
  $("small", elements.exportProgress).textContent = cancelling ? t("cancelling") : job?.message || "";
  renderActiveJobBar(job);
}

async function completeExportJob(job, projectId) {
  const result = job?.result;
  const projectIsVisible = state.project?.id === projectId;
  if (projectIsVisible) {
    elements.exportProgress.hidden = true;
    if (result?.url && result?.export?.name) {
      elements.exportTitle.textContent = "Your video is ready";
      elements.exportDescription.textContent = `Exported at ${result.export.fps || state.project.settings?.fps || 30} FPS. Download the finished video below.`;
      elements.downloadExport.href = result.url;
      elements.downloadExport.download = result.export.name;
      elements.downloadExport.textContent = `Download video (${result.export.fps || state.project.settings?.fps || 30} FPS)`;
      elements.downloadExport.hidden = false;
    }
  }
  const projectPayload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  rememberProjectRevision(projectPayload.project);
  if (projectIsVisible && state.project?.id === projectId) state.project = projectPayload.project;
  else toast(uiCopy("הייצוא של הפרויקט האחר הסתיים", "The other project's export is ready"), "success", 3600);
  loadProjects().catch(() => {});
}

function pollExportJob(jobId, projectId = null) {
  return new Promise((resolve, reject) => {
    let consecutivePollFailures = 0;
    let connectionNoticeShown = false;
    const finishWithError = (error) => {
      clearActiveJob(jobId);
      reject(error);
    };
    const handleJob = (job) => {
      if (!job) return false;
      updateExportProgress(job);
      if (job.status === "completed") { clearActiveJob(jobId); resolve(job); return true; }
      if (["failed", "interrupted"].includes(job.status)) {
        finishWithError(new Error(job.error || (job.status === "interrupted" ? "Render interrupted by restart" : "Render failed")));
        return true;
      }
      if (job.status === "cancelled") { finishWithError(new Error("Cancelled")); return true; }
      return false;
    };
    const tick = async () => {
      try {
        const payload = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
        const job = payload.job;
        consecutivePollFailures = 0;
        connectionNoticeShown = false;
        if (handleJob(job)) return;
        setTimeout(tick, 700);
      } catch (error) {
        consecutivePollFailures += 1;
        if (Number(error?.status) === 404) {
          finishWithError(error);
          return;
        }
        if (projectId && consecutivePollFailures >= 4) {
          try {
            const recovery = await api(`/api/projects/${encodeURIComponent(projectId)}/jobs/active`);
            const recovered = [
              ...(Array.isArray(recovery?.jobs) ? recovery.jobs : []),
              ...(Array.isArray(recovery?.recent) ? recovery.recent : []),
            ]
              .filter((item) => item?.id === jobId)
              .sort((left, right) => Date.parse(right.updated_at || 0) - Date.parse(left.updated_at || 0))[0];
            if (recovered) {
              consecutivePollFailures = 0;
              connectionNoticeShown = false;
              if (handleJob(recovered)) return;
              setTimeout(tick, 900);
              return;
            }
          } catch (_recoveryError) {
            // Keep waiting: a local server restart must not be reported as a failed export.
          }
        }
        if (!connectionNoticeShown && consecutivePollFailures >= 4) {
          connectionNoticeShown = true;
          toast(uiCopy(
            "החיבור המקומי נקטע. CUTROOM ממשיכה לבדוק את הייצוא בלי להתחיל מחדש.",
            "The local connection paused. CUTROOM is still checking the export without restarting it.",
          ));
        }
        setTimeout(tick, Math.min(5000, 700 * Math.max(1, consecutivePollFailures)));
      }
    };
    tick();
  });
}

function dockRuntimeStatus() {
  const dock = state.studio.open ? elements.studioRuntimeDock : elements.setupRuntimeDock;
  if (dock && elements.modelStatus && elements.modelStatus.parentElement !== dock) dock.appendChild(elements.modelStatus);
}

function renderModelStatus() {
  if (!elements.modelStatus) return;
  const connection = state.system?.ai_connection;
  if (connection?.mode && connection.mode !== "local") {
    elements.modelStatus.className = `model-status ${connection.configured ? "ready" : "partial"}`;
    elements.modelStatus.dataset.state = "cloud";
    const providerName = cloudProviderName(connection);
    $("b", elements.modelStatus).textContent = connection.configured ? `${providerName} selected for cloud AI` : "Connect your cloud AI account";
    $("small", elements.modelStatus).textContent = connection.configured ? `Audio + transcript sent to ${providerName} when you start AI. Provider quotas and billing apply.` : "Open AI connection to enter your key. Manual editing remains available.";
    elements.modelButton.hidden = true;
    elements.retryAIButton.hidden = true;
    return;
  }
  const models = state.system?.models;
  const runtime = state.system?.runtime;
  const installed = Boolean(models?.story_ai_ready);
  const engineAvailable = runtime?.state !== "disabled" && (typeof models?.ollama?.available === "boolean" ? models.ollama.available : Boolean(runtime?.available));
  const ready = engineAvailable && installed;
  const preparing = Boolean(state.aiPreparePromise);
  const installing = Boolean(state.modelInstallPending || state.modelInstallJob);
  const starting = preparing || ["idle", "checking", "starting"].includes(runtime?.state);
  let title = ready ? "Story AI ready" : engineAvailable ? "One-time AI setup" : "Local AI needs attention";
  let detail = ready ? `${models.selected_story_model || models.editor_model || "Installed model"} · Runs on this computer`
    : engineAvailable ? `${models?.recommended_story_model || "A Story AI model"} is needed. Download only with your confirmation; it can require several GB.`
      : (runtime?.available ? "The local AI engine is no longer responding. Use Retry AI to restart it." : runtime?.message) || state.system?.error || "Checking the local AI engine…";
  if (starting) { title = "Preparing local AI…"; detail = "Starting the local engine. Your footage stays on this computer."; }
  if (runtime?.state === "disabled" && !preparing) title = "Local AI is disabled";
  if (installing) { title = "Downloading Story AI…"; detail = "One-time model setup. You can stop this download using Stop process."; }
  if (starting && !preparing && state.runtimeRefreshAttempts >= 20) detail = "The engine is taking longer than expected. Use Retry AI to check again.";
  elements.modelStatus.className = `model-status ${ready && !preparing && !installing ? "ready" : "partial"}`;
  elements.modelStatus.dataset.state = installing ? "installing" : starting ? "starting" : ready ? "ready" : engineAvailable ? "missing-model" : "missing-engine";
  $("b", elements.modelStatus).textContent = title;
  $("small", elements.modelStatus).textContent = detail;
  elements.modelButton.hidden = !engineAvailable || installed || preparing || installing;
  elements.modelButton.textContent = "Download model…";
  elements.retryAIButton.hidden = runtime?.can_retry === false || (ready && !preparing && !installing);
  elements.retryAIButton.textContent = preparing ? "Preparing…" : "Retry AI";
  for (const button of [elements.modelButton, elements.retryAIButton]) button.disabled = preparing || installing || foregroundBusy();
}

function prepareLocalAI() {
  if (state.aiPreparePromise) return state.aiPreparePromise;
  state.runtimeGeneration += 1;
  if (state.runtimeRefreshTimer) clearTimeout(state.runtimeRefreshTimer);
  state.runtimeRefreshTimer = null;
  state.runtimeRefreshAttempts = 0;
  const selectedMode = elements.performanceModeSelect?.value || state.project?.settings?.performance_mode || "auto";
  const mode = ["auto", "lite", "balanced", "quality"].includes(selectedMode) ? selectedMode : "auto";
  state.aiPreparePromise = Promise.resolve().then(async () => {
    try {
      const payload = await api("/api/runtime/prepare", { method: "POST", body: JSON.stringify({ performance_mode: mode }) });
      state.system = {
        ...(state.system || {}), runtime: payload.runtime, error: null,
        models: {
          ...(state.system?.models || {}),
          ollama: { available: Boolean(payload.story_ai?.ollama_available ?? payload.runtime?.available), models: payload.story_ai?.installed_models || [] },
          story_ai_ready: Boolean(payload.story_ai?.ready),
          selected_story_model: payload.story_ai?.selected_model || null,
          recommended_story_model: payload.story_ai?.recommended_model || null,
        },
      };
      return payload;
    } catch (error) {
      state.system = { ...(state.system || {}), runtime: { state: "error", available: false, message: `Could not prepare local AI: ${error.message}. Use Retry AI to try again.` } };
      throw error;
    } finally {
      state.aiPreparePromise = null;
      state.runtimeGeneration += 1;
      renderModelStatus();
      renderActiveJobBar();
      scheduleRuntimeRefresh();
    }
  });
  renderModelStatus();
  renderActiveJobBar();
  return state.aiPreparePromise;
}

async function retryLocalAI() {
  if (foregroundBusy() || state.aiPreparePromise || state.modelInstallPending || state.modelInstallJob) return;
  try {
    const prepared = await prepareLocalAI();
    if (prepared.story_ai?.ready) toast("Story AI is ready. You can continue editing.", "success");
  } catch (error) { toast(error.message); }
}

async function downloadStoryModel(target, assertCurrent = assertJobStartNotCancelled) {
  if (state.modelInstallPending || state.modelInstallJob) throw new Error("Story AI setup is already in progress.");
  state.modelInstallPending = true;
  try {
    assertCurrent();
    if (!window.confirm(`Download ${target} for local Story AI?\n\nThis is a one-time download that can require several GB of internet data and disk space. It runs on your computer without a subscription. Your footage is not uploaded.\n\nChoose Cancel to keep working without downloading.`)) throw new Error("Cancelled");
    assertCurrent();
    renderModelStatus();
    const payload = await api("/api/models/install", { method: "POST", body: JSON.stringify({ kind: "editor", model: target }) });
    state.modelInstallJob = payload.job.id;
    // pollJob takes ownership before a queued Stop is forwarded to the job.
    await pollJob(payload.job.id, { modelInstall: true });
    assertCurrent();
  } finally {
    state.modelInstallPending = false;
    state.modelInstallJob = null;
    renderModelStatus();
  }
}

async function installModel() {
  if (state.aiPreparePromise || state.modelInstallPending || state.modelInstallJob) return;
  const lock = acquireJobStartLock("model_install", state.project?.id || "runtime");
  if (!lock) return;
  try {
    await ensureStoryAIReady("short");
    toast("Story AI is ready. You can continue editing.", "success");
  } catch (error) {
    if (error.message !== "Cancelled") toast(error.message);
  } finally {
    if (!state.activeJob) state.cancelBeforeStart = false;
    releaseJobStartLock(lock);
    renderModelStatus();
  }
}

boot().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main style="padding:40px;color:white"><h1>CUTROOM could not start</h1><pre>${escapeHtml(error.stack || error.message)}</pre></main>`;
});

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[character]));
}
