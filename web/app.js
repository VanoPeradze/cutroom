import { initSourceFrameReview, projectFrameStep } from "./source-frame.js?v=20261119-frame1";
import { planTranscriptSections, captureSectionIntent, navigateSection as navigateTranscriptSection } from "./transcript-sections.js?v=20261117-transcript-sections1";
import { createBatchProtocol, captureTranscriptBuffers, matchingCapturedBuffers, retainedDraftViews } from "./transcript-batch.js?v=20261117-transcript-batch1";
import { planPublicBatch, verifyPublicBatch, classifySavedBatch } from "./transcript-batch-receipt.js?v=20261117-transcript-batch1";
import { editingPositionIdentity, createEditingPositionStore } from "./editing-position.js?v=20261117-editing-context1";
import { audioSourceRange, planAudioSourcePlacement, verifyAudioSourcePlacement, readAudioSourceMarks, saveAudioSourceMarks, clearAudioSourceMarks } from "./audio-source.js?v=20261117-audio-source1";
import { initAudioSourceReview } from "./audio-source-review.js?v=20261117-audio-source1-sourcedrag1";
import { initPreviewRepairController } from "./preview-repair.js?v=20261116-preview-repair2";
import { initTrackLevelControls } from "./track-level-controls.js?v=20261116-track-levels2-mixer1";
import { initProjectCopyController } from "./project-copy.js?v=20261116-project-copy2";
import { layerTrackLevels, planLayerTrackAudio, verifyLayerTrackAudio, layerTrackSoundSummaries, layerTrackState, layerTrackRanks, layerTrackUpdateIssue, layerMutationIssue, layerAssetMutationIssue, createLayerMutationPlanner, planLayerTrackMove, planLibraryTrackPlacement, createLibraryPlacementPlanner } from "./layer-tracks.js?v=20261116-track-levels2-opacity1";
import { initLayerTrackManager } from "./layer-track-manager.js?v=20261116-track-levels2";
import { planLayerGroupMove, planLayerGroupRemove, planLayerGroupDuplicate, verifyLayerGroupDuplicate } from "./layer-selection.js?v=20261116-track-levels2";
import { planLayerGroupFrame, verifyLayerGroupFrame } from "./layer-group-frame.js?v=20261117-match-frame3";
import { planLayerGroupRelocate, verifyLayerGroupRelocate } from "./layer-group-tracks.js?v=20261116-track-levels2";
import { applyTranslations, dictionaries } from "./i18n.js?v=1.2-beta";
import { TimelineView, formatTime, editableClips, timelineDuration, sequenceBlocks, sequenceGaps, sequenceGapClosureIssue, rippleMoveStart } from "./timeline.js?v=20261117-editing-context1-markers1-precision1";
import { MediaStudio, libraryInsertReadiness, libraryAssetUsage, readLibraryShotMarks } from "./media-studio.js?v=20261117-audio-source1-mixer1-roll1-slide1-take1-ow1-sourceview1-opacity1-ripplechapter1-matchseam1-sourcedrag1-frame1-handoff1";
import { initMediaFrameEditor } from "./viewer-transform.js?v=20261116-transform2";
import { initTimelineMediaDrop } from "./timeline-media-drop.js?v=20261117-editing-context1-sourcedrag1";
import { StabilizationStudio } from "./stabilization-studio.js?v=1.2-beta";
import { ChromaStudio } from "./chroma-studio.js?v=20261116-layer-locks4";
import { ChromaPreview } from "./chroma-preview.js?v=1.2-beta";
import { SourceReview } from "./source-review.js?v=20261117-editing-context1";
import { initWorkspace } from "./workspace.js?v=20261116-workspace2-console1-firstrecording1";
import { initRangeAudition } from "./range-audition.js?v=20261117-range2";
import { initReviewMarkers, reviewMarkerRows } from "./review-markers.js?v=20261117-1";
import {planTrackOverwrite, describeTrackOverwrite, verifyTrackOverwrite} from "./track-overwrite.js?v=20261118-tracklift1";
import {initTrackLift,planTrackLift,verifyTrackLift} from "./track-lift.js?v=20261118-lift1";
import {initClipOpacity,planClipOpacity,verifyClipOpacity} from "./clip-opacity.js?v=20261118-opacity1";
import {initMarkedLayers,planMarkedLayers} from "./mark-selection.js?v=20261118-markrange1";
import {planGroupSplit,groupSplitFrame,verifyGroupSplit} from "./group-split.js?v=20261118-split1";
import {planGroupJoin,verifyGroupJoin} from "./group-join.js?v=20261118-join1-titleclock1";
import {takeContext, planTake, verifyTake, initTakeReplacement} from "./replace-take.js?v=20261118-take1";
import { rollPair, planRoll, verifyRoll, initRollingEdit } from "./rolling-edit.js?v=20261118-slide1";
import { makeExportRangePlan, sameExportRangePlan, exportFrameTime, exportRangeLabel } from "./range-export.js?v=20261117-1";
import { initColorMotion } from "./color-motion.js?v=20261122-color1";
import { initFirstRecordingGuide } from "./first-recording-guide.js?v=20261117-firstrecording1";
import { KEYBOARD_PROFILES, resolveEditorShortcut, isEditorTransportSpace, shortcutRows } from "./keyboard.js?v=20261116-slip1-markers1-markrange1";
import { AudioThresholdView } from "./audio-meter.js?v=20261112-workbench1";
import { initWelcome, workflowSettings, cloudProviderName } from "./welcome.js?v=20261119-manual-entry1";
import { initTranscriptionEngine } from "./transcription-engine.js?v=20261111";
import { initLocalModels } from "./local-models.js?v=1.2-beta";
import { trackClips, trackAt, hasSourceTracks, SourceTimelineClock } from "./source-tracks.js?v=1.2-beta";
import { initTrackProtection } from "./track-protection.js?v=1.2-beta";
import { TextStudio } from "./text-studio.js?v=20261116-caption-preview3";
import { initNumericScrub } from "./numeric-scrub.js?v=20261116-move2";
import { ReelProposalReview, supportsReelReview } from "./reel-proposals.js?v=20261022";
import { ClipBoard } from "./clip-board.js?v=20261122-clips11-kit2";
import { AiDraftReview } from "./ai-draft-review.js?v=20261116-ai-review2";
import { CaptionAlternatives } from "./caption-alternatives.js?v=20261023";
import { initCaptionPreview, captionPreviewIssue } from "./caption-preview.js?v=20261116-caption-preview3";
import { reviewEditingRequest } from "./request-review.js?v=20261116-settings1";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const state = {
  project: null,
  editingPositions: null,
  audioSourcePlacement: null,
  audioSourceFences: new Map(),
  audioSourceNotice: null,
  matchFramePending: null,
  matchFrameFences: new Map(),
  groupSplitFences: new Map(), groupSplitPending: null,
  aiDraftNotice: null,
  aiDraftReview: null,
  projects: [],
  projectCopies: null,
  previewRepairs: null,
  previewRepairContexts: new Map(),
  previewRepairNotices: new Map(),
  locale: "en",
  dictionary: null,
  activeJob: null,
  activeUploads: new Map(),
  uploadStorage: new Map(),
  analysisSnapshot: null,
  directorOutcome: null,
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
  directorRequestPending: false,
  editorDirectorSession: null,
  manualSelection: null,
  editTarget: "edit",
  keyboardProfile: "cutroom",
  markIn: null,
  trimClip: null,
  transcriptBuffers: new Map(),
  transcriptActive: null,
  transcriptAnchor: null,
  transcriptSaving: false,
  transcriptBatches: new Map(),
  transcriptReviewBuffers: new WeakSet(),
  transcriptRecoveryActive: null,
  captionSelection: null,
  captionDirty: false,
  captionAlternativesUI: null,
  manualTranscriptionControls: renderManualTranscription,
  captionPreview: null,
  captionPreviewResult: null,
  captionStatus: "",
  retainedResumePending: null,
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
  if (sequence.error || !sequence.sequence || !sequence.source_tracks) {
    // Keep an opaque/invalid timeline openable without inventing legacy clips.
    return { ...project, __sequenceView: true, __timelineUnavailable: true,
      manual: { ...project.manual, sequence: { version: 1, duration: 0, camera_plan: [] },
        source_tracks: { A: [], B: [] }, media_clips: [], text_clips: [] },
      draft: { ...project.draft, keep_ranges: [], cuts: [], camera_plan: [], output_duration: 0, edit_points: [] } };
  }
  return { ...project, __sequenceView: true,
    manual: { ...project.manual, sequence: sequence.sequence, source_tracks: sequence.source_tracks },
    draft: { ...project.draft, keep_ranges: sequence.duration > 0 ? [{start:0,end:sequence.duration}] : [], cuts: [],
      camera_plan: sequence.sequence.camera_plan, output_duration: sequence.duration, edit_points: [] } };
}

function playbackProject() {
  const view = editorProject();
  if (view?.__timelineUnavailable) return view;
  if ((!state.project?.editor_sequence && !retainedEditStatus()) || !previewUsesSourceTime()) return view;
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
    "sourceSlotA", "sourceSlotB", "sourceInputA", "sourceInputB", "cancelUploadA", "cancelUploadB", "audioCalibration", "audioMeterCanvas", "recommendedThreshold", "useRecommendedThreshold", "silenceThreshold", "silenceThresholdOut", "preSilenceMin", "preSilenceMinOut", "preSilenceKeep", "preSilenceKeepOut", "audioCutEstimate", "audioProfileSummary", "editStyleChoices", "editStyleNote", "styleRecommendation", "sourceContext", "goalChoices", "goalExplainer", "goalExplainerTitle", "goalExplainerText", "durationGroup", "targetDuration", "durationMode", "durationOutput", "paceChoices", "paceNote",
    "directorInstruction", "directorInstructionCounter", "uploadStorageInfo", "directorOutcomeNotice", "instructionResults", "instructionResultsTitle", "instructionResultsSummary", "instructionResultsList", "allowExtractiveRoughCut", "readiness", "generateButton", "jobMessage", "jobProgress", "cancelJobButton", "analysisError", "analysisErrorTitle", "analysisErrorMessage", "retryDirectorButton", "backFromErrorButton", "draftTitle", "draftSummary", "draftEngineBadge",
    "reelCandidates", "reelCandidatesTitle", "reelCandidateList", "draftWarning", "draftWarningText", "reviewSpeechSettings", "gameplayMoments",
    "beforeDuration", "afterDuration", "decisionCount", "decisionList", "retainedEditPreview", "previewStage", "previewA", "previewB", "previewPaneA", "previewPaneB", "previewPlay", "playButton",
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
    "captionItemEditor", "captionItemMeta", "captionItemClose", "captionItemText", "captionItemSourceHelp", "captionItemStart", "captionItemEnd",
    "captionItemStyle", "captionItemPosition", "captionItemScale", "captionItemHide", "captionItemReset", "captionItemSave", "captionItemStatus",
    "captionItemPrevious", "captionItemNext",
    "keyboardProfile", "keyboardHelpProfile", "keyboardHelp", "keyboardDialog", "keyboardDescription", "keyboardLimitations", "keyboardShortcutList", "clipTrimForm", "clipTrimIn", "clipTrimOut", "clipTrimTitle", "clipTrimApply", "clipTrimStatus", "timelineTarget", "timelineTargetField", "trackReset", "trackHelp", "clipSourceIn", "clipSourceField", "clipMove",
    "qualitySelect", "fpsSelect", "fpsHelp", "exportFpsSelect", "exportFpsHelp", "exportFrameRateField", "exportScopeField", "exportScope", "exportScopeLabel", "exportScopeHelp", "autoReframe", "effectsToggle", "captionsToggle", "burnCaptionsToggle", "studioBurnCaptionsToggle", "captionControlStatus", "captionPreviewStatus", "captionLanguageStatus",
    "captionStyleSelect", "captionPositionSelect", "captionScale", "captionScaleOut", "captionWordsPerLine", "captionWordsPerLineOut", "spokenLanguageSelect", "performanceModeSelect", "visualAiSelect", "audioPresetChoices", "audioPresetNote",
    "silenceAction", "silenceMin", "silenceMinOut", "silenceKeep", "silenceKeepOut", "maxRemoveRatio", "maxRemoveOut",
    "quietAction", "quietGain", "quietGainOut", "loudAction", "loudGain", "loudGainOut", "normalizeAudio",
    "modelStatus", "modelButton", "retryAIButton", "setupRuntimeDock", "studioRuntimeDock", "draftRebuildNotice", "draftRebuildTitle", "draftRebuildText", "rebuildDraftButton", "exportDialog", "closeExportDialog", "exportSummary", "exportReview",
    "activeJobBar", "activeJobLabel", "activeJobDetail", "globalCancelJobButton", "exportTitle", "exportDescription", "exportProgress", "exportActions", "cancelExport", "cancelExportJobButton", "confirmExport", "downloadExport", "downloadExportCaptions", "toastRegion", "cameraBadge",
    "sourceInsertForm", "sourceInsertTitle", "sourceInsertIn", "sourceInsertOut", "sourceInsertAt", "sourceInsertStatus", "sourceInsertCancel", "sourceInsertSlot", "sourceInsertMode", "sourceInsertZone", "sourceInsertApply", "clipDuplicate", "editorMoreButton", "editorMoreTools", "emptyTimeline", "emptyTimelineAdd",
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
  const { transcriptBatchToken = null, ...requestOptions } = options;
  const method=String(options.method || "GET").toUpperCase();
  if(!["GET","HEAD","OPTIONS"].includes(method)) {
    const target=String(path).match(/^\/api\/projects\/([^/?]+)(?:[/?]|$)/)?.[1];
    if(target && !/\/copies(?:[?]|$)/.test(String(path)) && projectCopySourceBusy(decodeURIComponent(target)))
      throw new ApiError("Finish or cancel this project copy before changing its saved source.",409,"project_copy_active");
    if (target && state.transcriptBatches?.size && transcriptBatchIssue(decodeURIComponent(target))) {
      const batch = transcriptBatchOwner(decodeURIComponent(target)), saved = batch?.protocol?.snapshot();
      const own = transcriptBatchToken === batch && saved?.pending && saved.status === "submitting"
        && method === "POST" && String(path) === `/api/projects/${encodeURIComponent(batch.projectId)}/manual/edit`
        && options.body === saved.binding.body;
      if (!own) throw new ApiError("Check the transcript batch outcome before changing this saved project.", 409, "transcript_batch_pending");
    }
    if(target && previewRepairBusy(decodeURIComponent(target)))
      throw new ApiError("Finish or cancel the preview verification before changing this saved project.",409,"preview_repair_active");
  }
  const response = await fetch(path, {
    ...requestOptions,
    headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = typeof payload === "object" ? payload.message || payload.error : payload;
    const code = typeof payload === "object" ? payload.error : null;
    if(code==="project_copy_active")void recoverProjectCopies();
    throw new ApiError(message || `HTTP ${response.status}`, response.status, code, payload);
  }
  return payload;
}

// Workspace geometry is presentation-only. Refuse an explicit layout change
// while a gesture or its save owns coordinates; never poll/cancel from onResize.
function workspaceResizeIssue() {
  const timeline=state.timeline, source=state.sourceReview?.timeline;
  if(timeline?.gesture || timeline?.scrubbing || timeline?.libraryDragActive || source?.gesture || source?.scrubbing
    || document.documentElement?.classList?.contains?.("numeric-scrubbing"))return "Finish or cancel the current drag before resizing the workspace.";
  if(state.mediaStudio?.frameEditorState?.dragging || state.embeddedEditor?.dragging)return "Finish or cancel the viewer frame adjustment before resizing the workspace.";
  if(state.manualEditBusy || timeline?.editPending || state.sourceReview?.busy || state.mediaStudio?.frameEditor?.pending
    || state.mediaStudio?.frameEditorState?.pending)return "Wait for the current edit to finish before resizing the workspace.";
  if(timeline?.mediaSelectionPending || timeline?.mediaSourceOpening)return "Wait for the selected clip or source preview to open before resizing the workspace.";
  return "";
}

// Preview repair is maintenance of an owned imported asset, not a timeline edit.
// The transport retains uncertain requests; only an explicit user action submits.
function initializePreviewRepairs() {
  if(state.previewRepairs || typeof initPreviewRepairController!=="function")return state.previewRepairs;
  state.previewRepairs=initPreviewRepairController({api,prepare:preparePreviewRepair,admit:admitPreviewRepair,
    changed:previewRepairChanged,settled:settlePreviewRepair,storage:localStorage});
  return state.previewRepairs;
}
function previewRepairSettling(projectId=state.project?.id) {
  return [...state.previewRepairContexts.values()].find(context=>context.projectId===projectId && context.settling) || null;
}
function previewRepairBusy(projectId=state.project?.id) {
  return Boolean(previewRepairSettling(projectId) || state.previewRepairs?.active?.(projectId)?.some(entry=>entry.status!=="preparing"));
}
function previewRepairStable(value) {
  if(Array.isArray(value))return value.map(previewRepairStable);
  if(value && typeof value==="object")return Object.fromEntries(Object.keys(value).sort().map(key=>[key,previewRepairStable(value[key])]));
  return value;
}
function previewRepairContentIdentity(project,assetId) {
  if(!project?.id || !project.assets?.[assetId])return null;
  const copy={...project,assets:{...project.assets}};
  // These are revision-bound public projections, not authored content.
  for(const key of ["revision","updated_at","caption_preview","timeline_bindings","ai_draft_review","retained_edit","project_copy"])delete copy[key];
  copy.assets[assetId]={...copy.assets[assetId]};
  for(const key of ["url","thumbnail_url","waveform","preview_version"])delete copy.assets[assetId][key];
  return JSON.stringify(previewRepairStable(copy));
}
function previewRepairIssue(assetId) {
  const project=state.project,asset=project?.assets?.[assetId];
  if(!project?.id || asset?.id!==assetId || asset.status!=="ready")return "Choose a ready imported file to verify its prepared preview.";
  if(!/^[0-9a-f]{24}$/.test(asset.preview_version || ""))return "Reload this project in the current CUTROOM version before checking prepared previews.";
  const previous=state.previewRepairs?.forAsset?.(project.id,assetId);
  if(previous?.status==="rejected" && previous.error_code==="revision_conflict" && previous.expected_revision===project.revision)
    return "Reopen this project to review its newer saved revision before verifying again. Save or discard local drafts first; nothing is replayed.";
  if(projectCopySourceBusy() || projectCopyFileBusy())return "Finish or cancel the project copy before checking previews.";
  if(savedLayerTrackIssue())return savedLayerTrackIssue();
  if(previewRepairSettling())return "Wait for the verified preview to refresh.";
  if(state.activeJob || state.activeUploads.size || state.jobStartLocks.size || state.manualEditBusy || state.retainedResumePending
    || state.mediaStudio?.uploading || state.mediaStudio?.placing || state.mediaStudio?.importQueue?.running || state.stabilizationStudio?.uploading
    || state.sourceSyncPending || state.sourceMixerSavePending || state.transcriptSaving || state.captionContextSave)
    return "Wait for the current save, import or processing to finish before checking this preview.";
  if(workspaceResizeIssue() || state.mediaStudio?.frameEditor?.active || state.mediaStudio?.shotReview?.pending)
    return "Finish or cancel the current gesture, frame or source placement before checking this preview.";
  const explicit=explicitPendingDraft();if(explicit)return explicit.detail;
  if(pendingTranscriptBuffers().length)return "Save or discard the transcript changes before checking this preview. Your text is still here.";
  return "";
}
async function preparePreviewRepair(projectId,assetId,operationToken) {
  if(state.project?.id!==projectId)throw new Error("Open the source project before checking its preview.");
  const viewToken=state.projectViewToken,pane=layerGroupDuplicateContext();
  const current=()=>{
    const operation=state.previewRepairs?.forAsset?.(projectId,assetId);
    return state.project?.id===projectId && state.projectViewToken===viewToken && layerGroupDuplicateContext()===pane
      && operation?.operation_token===operationToken && operation.status==="preparing" && !operation.cancel_requested;
  };
  if(!current())throw new Error("This preview verification was cancelled or replaced before preparation.");
  let issue=previewRepairIssue(assetId);
  if(issue){const explicit=explicitPendingDraft();if(explicit)revealPendingSave(explicit);throw new Error(issue);}
  if(!(await flushCurrentProjectSaves()) || !current())throw new Error("The project view or save state changed. Review the current asset before trying again.");
  issue=previewRepairIssue(assetId);if(issue)throw new Error(issue);
  if(projectSaveStatus().kind!=="saved")throw new Error("Resolve the current save state before checking this preview.");
  const project=state.project,asset=project.assets[assetId];
  if(!Number.isInteger(project.revision) || project.revision<1)throw new Error("Reload the saved project before checking previews.");
  const context={projectId,assetId,operationToken,viewToken,pane,revision:project.revision,
    content:previewRepairContentIdentity(project,assetId),previewVersion:asset.preview_version,
    media:state.mediaStudio?.capturePreviewRepair?.(assetId)};
  state.previewRepairContexts.set(operationToken,context);
  state.previewRepairNotices.delete(`${projectId}:${assetId}`);
  // Pause in place once. pauseAllMedia hides independent frames, so immediately
  // restore the same paused scene without a seek or a media-node rebuild.
  pauseAllMedia();updateMediaPreview();
  return {project_id:projectId,asset_id:assetId,expected_revision:project.revision,operation_token:operationToken,context};
}
function admitPreviewRepair(binding,context) {
  const operation=state.previewRepairs?.forAsset?.(binding.project_id,binding.asset_id);
  return Boolean(operation?.operation_token===binding.operation_token && operation.status==="preparing" && !operation.cancel_requested
    && context && state.previewRepairContexts.get(binding.operation_token)===context
    && state.project?.id===binding.project_id && state.projectViewToken===context.viewToken
    && layerGroupDuplicateContext()===context.pane && state.project.revision===binding.expected_revision
    && !previewRepairIssue(binding.asset_id) && projectSaveStatus().kind==="saved"
    && previewRepairContentIdentity(state.project,binding.asset_id)===context.content);
}
function previewRepairChanged(entry) {
  if(state.project?.id!==entry?.project_id)return;
  state.mediaStudio?.updatePreviewRepairControls?.();
  renderReadiness();renderManualControls();
}
async function settlePreviewRepair(entry,localContext) {
  // A late earlier operation remains a server fence, never a player-adoption owner.
  if(entry?.earlier_request) {
    const previous=state.previewRepairContexts.get(entry.operation_token);
    if(previous?.projectId===entry.project_id && previous.assetId===entry.asset_id
      && previous.operationToken===entry.operation_token)state.previewRepairContexts.delete(entry.operation_token);
    return;
  }
  const context=localContext || state.previewRepairContexts.get(entry.operation_token);
  const key=`${entry.project_id}:${entry.asset_id}`;
  const owned=()=>Boolean(context && context.projectId===entry.project_id && context.assetId===entry.asset_id
    && context.operationToken===entry.operation_token && state.previewRepairContexts.get(entry.operation_token)===context
    && state.previewRepairs?.forAsset?.(entry.project_id,entry.asset_id)?.operation_token===entry.operation_token);
  try {
    if(entry.status!=="completed" || !owned())return;
    // Recovered jobs remain visible but never restore a prior browser's audition.
    if(!context || state.project?.id!==entry.project_id || state.projectViewToken!==context.viewToken)return;
    context.settling=true;renderReadiness();
    const payload=await api(`/api/projects/${encodeURIComponent(entry.project_id)}`),latest=payload?.project,result=entry.result;
    if(!owned() || state.project?.id!==entry.project_id || state.projectViewToken!==context.viewToken)return;
    const current=state.project,asset=latest?.assets?.[entry.asset_id];
    const valid=result?.project_id===entry.project_id && result.asset_id===entry.asset_id
      && result.before_preview_version===context.previewVersion && result.after_preview_version===asset?.preview_version
      && /^[0-9a-f]{24}$/.test(result.after_preview_version || "") && latest?.id===entry.project_id
      && Number.isInteger(latest.revision) && latest.revision>=current.revision && latest.revision>=context.revision
      && [context.previewVersion,result.after_preview_version].includes(current.assets?.[entry.asset_id]?.preview_version)
      && previewRepairContentIdentity(current,entry.asset_id)===context.content
      && previewRepairContentIdentity(latest,entry.asset_id)===context.content
      && !hasUnsavedProjectWork();
    if(!valid){state.previewRepairNotices.set(key,"Verification finished, but this edit changed. Reload the project to use the confirmed preview; nothing was replayed.");return;}
    // The entire authored scene was pinned above. Adopt only this maintenance
    // snapshot, never renderDraft, clear selection, seek, reopen or autoplay.
    state.project=latest;rememberProjectRevision(latest);
    state.mediaStudio?.acceptPreviewRepair?.(context.media,result);
    if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
    updateMediaPreview();renderCaptionItemPreview();
    state.previewRepairNotices.set(key,result.preparation_reused
      ? "Prepared preview verified. The original and edit are unchanged. Playback stays paused."
      : "Prepared preview repaired from the verified original. The edit and source marks are unchanged. Playback stays paused.");
  } catch(error) {
    if(owned())state.previewRepairNotices.set(key,"Verification finished, but the current project could not be refreshed. Check status or reopen it; the request was not repeated.");
  } finally {
    if(context?.projectId===entry.project_id && context.assetId===entry.asset_id && context.operationToken===entry.operation_token
      && state.previewRepairContexts.get(entry.operation_token)===context)state.previewRepairContexts.delete(entry.operation_token);
    if(state.project?.id===entry.project_id){state.mediaStudio?.updatePreviewRepairControls?.();renderReadiness();renderManualControls();}
  }
}

// Asset usage is local navigation only. Do not reuse selection paths which may
// flush a caption/text autosave: browsing a file must never submit an edit.
function mediaUsageNavigationIssue() {
  if(!state.project?.id || !state.timeline || !state.studio.open)return "Open this project in Studio to navigate its saved clips.";
  if(typeof state.project.id!=="string" || !Number.isInteger(state.project.revision) || state.project.revision<1)return "Reopen this project to review a valid saved revision before navigating.";
  if(retainedEditStatus())return "Resume the retained edit before navigating its saved timeline clips.";
  if(!state.project.draft || Array.isArray(state.project.draft) || typeof state.project.draft!=="object")return "Open a valid saved edit before navigating its clips.";
  const modelIssue=savedLayerTrackIssue();if(modelIssue)return modelIssue;
  if(foregroundBusy() || state.transcriptSaving || state.captionContextSave || state.manualEditBusy)return "Wait for the current save or processing to finish before navigating to a clip.";
  const gesture=workspaceResizeIssue();if(gesture)return gesture;
  if(state.mediaStudio?.frameEditor?.active || state.sourceReview?.busy || state.mediaStudio?.shotReview?.pending)
    return "Finish or cancel the current frame or source placement before navigating to a clip.";
  const saved=projectSaveStatus();
  if(saved.kind!=="saved" || hasUnsavedProjectWork())return saved.detail || "Save or discard pending changes before navigating. Nothing is saved by this action.";
  return "";
}

function openMediaAssetUses(assetId,origin,context) {
  const project=state.project;
  if(!project?.id || context?.projectId!==project.id || context.viewToken!==state.projectViewToken || !project.assets?.[assetId])return false;
  const usage=libraryAssetUsage(project);
  if(usage.issue || !usage.counts.get(assetId)){toast(usage.issue || "This imported file has no saved timeline clips.");return false;}
  return state.timeline?.navigation?.openAsset?.(assetId,origin)===true;
}

function revealMediaPoolAsset(assetId,context) {
  const project=state.project;
  if(!project?.id || context?.projectId!==project.id || context.viewToken!==state.projectViewToken || !project.assets?.[assetId])return false;
  if(libraryAssetUsage(project).issue)return false;
  const rows=project.manual?.media_clips;
  if(!Array.isArray(rows) || rows.filter(row=>row?.id===context.clipId && row.asset_id===assetId).length!==1
    || state.mediaStudio?.selected!==context.clipId || state.timeline?.mediaSelection!==context.clipId || selectedLayerGroupIds().length)return false;
  const issue=mediaUsageNavigationIssue();if(issue){toast(issue);return false;}
  const pool=document.getElementById("studioShelfMedia");
  if(typeof pool?.mediaPoolNavigation?.revealAsset!=="function")return false;
  elements.advancedPanel?.workbenchController?.setMediaPoolVisible(true,false);
  return pool.mediaPoolNavigation.revealAsset(assetId)===true;
}

function selectMediaAssetOccurrence(request) {
  const project=state.project,viewToken=state.projectViewToken,revision=project?.revision;
  const current=()=>state.project===project && state.projectViewToken===viewToken && project?.revision===revision
    && typeof request?.isCurrent==="function" && request.isCurrent()===true;
  if(!project?.id || request?.projectId!==project.id || request.revision!==project.revision || !current())return false;
  const issue=mediaUsageNavigationIssue();if(issue){toast(issue);return false;}
  const usage=libraryAssetUsage(project),rows=project.manual?.media_clips;
  if(usage.issue || !Array.isArray(rows) || !usage.counts.get(request.assetId))return false;
  const matches=rows.filter(row=>row.id===request.clipId && row.asset_id===request.assetId),clip=matches[0],duration=editorDuration();
  if(matches.length!==1 || !clip || ![clip.start,clip.end,duration].every(Number.isFinite)
    || clip.start<0 || clip.end<=clip.start || clip.end>duration || !current())return false;
  // The clean-state guard above makes the entire adoption synchronous: no
  // flush(), API call or deferred completion can save or hijack another view.
  state.timeline.cancelPendingCut?.();beginInspectorSelection();pauseAllMedia();
  if(state.textStudio?.selected){state.textStudio.selected=null;state.textStudio.render(true);}
  clearCaptionInspectorSelection();state.manualSelection=null;state.markIn=null;
  state.timeline.clearSelection(false);state.timeline.mediaSelection=clip.id;
  state.mediaStudio?.select(clip.id);
  elements.advancedPanel?.workbenchController?.setPane("inspector",{restoreScroll:false});
  selectAdvancedTab("media");
  seekSourcePreview(clip.start);
  state.timeline.revealMedia?.(clip.id);state.timeline.followPlayhead?.();state.timeline.scheduleDraw?.();
  renderManualControls();
  return true;
}

function initializeMediaStudio() {
  if (typeof MediaStudio === "undefined") return;
  const panel = document.getElementById("studioPanelMedia");
  const tab = document.createElement("button");
  tab.id = "studioTabMedia"; tab.type = "button"; tab.dataset.tab = "media";
  tab.setAttribute("role", "tab"); tab.setAttribute("aria-selected", "false"); tab.setAttribute("aria-controls", "studioPanelMedia"); tab.tabIndex = -1;
  tab.innerHTML = '<svg class="ui-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4m10 0h4M3 15h4m10 0h4"/></svg><span>Media</span><small>Clips & images</small>';
  elements.advancedPanel.querySelector(".advanced-tabs").prepend(tab);
  // bindEvents already ran before this dynamically created tab.
  tab.addEventListener("click", () => selectAdvancedTab("media"));
  tab.addEventListener("keydown", handleStudioTabKeydown);
  initializePreviewRepairs();
  state.mediaStudio = new MediaStudio(panel, elements.previewStage, {
    libraryRoot: document.getElementById("studioShelfMedia"), saveStateChanged: renderProjectSaveState,
    usage: {issue:mediaUsageNavigationIssue,find:openMediaAssetUses,reveal:revealMediaPoolAsset},
    audioSource: {
      create: typeof initAudioSourceReview==="function" ? initAudioSourceReview : null, issue: audioSourceNavigationIssue, place: placeAudioSource,
      range: (...args) => audioSourceRange(...args), plan: (...args) => planAudioSourcePlacement(...args),
      readMarks: (project,id) => readAudioSourceMarks(project,id,audioSourceStorage()),
      saveMarks: (project,id,range) => saveAudioSourceMarks(project,id,range,audioSourceStorage()),
      clearMarks: (project,id) => clearAudioSourceMarks(project,id,audioSourceStorage()),
      pauseProgram: audio => { pauseAllMedia(audio);updateMediaPreview(); },
    },
    previewRepair: {
      entry: assetId => state.previewRepairs?.forAsset?.(state.project?.id,assetId),
      issue: previewRepairIssue, notice: assetId => state.previewRepairNotices.get(`${state.project?.id}:${assetId}`) || "",
      start: assetId => state.previewRepairs?.start?.(state.project?.id,assetId),
      check: assetId => state.previewRepairs?.check?.(state.project?.id,assetId),
      cancel: assetId => state.previewRepairs?.cancel?.(state.project?.id,assetId),
      busy: () => Boolean(previewRepairSettling() || state.previewRepairs?.active?.(state.project?.id)?.length),
      reveal: () => elements.advancedPanel?.workbenchController?.setMediaPoolVisible(true,false),
    },
    sourceFrames: initSourceFrameReview,
    sourceMonitor: {
      open: () => {
        if(!openStudioTab("media"))return false;
        closePrimarySourceReview();
        // Reviewing an original is a navigation intent, not a group edit.
        if(selectedLayerGroupIds().length){state.timeline?.setMediaSelection?.([],null);renderManualControls();}
        return true;
      },
      token: () => state.projectViewToken,
      visible: () => state.studio.open && !panel.hidden && !panel.inert
        && document.getElementById("studioInspector")?.dataset.workbenchPane!=="ai",
      issue: sourceMonitorIssue,
      poolIssue: () => (audioSourceNavigationIssue() || '')
        .replace(/reviewing (?:imported )?audio/g, 'opening the source').replace(/Opening audio/g, 'Opening the source')
        .replace(/before adding source shots/g, 'before opening the source'),
      pauseProgram: source => pauseAllMedia(source),
      placed: (clip,project) => {
        if(state.project?.id!==project.id || state.project.revision!==project.revision)return;
        state.timeline?.clearSelection();state.markIn=null;
        clearCaptionInspectorSelection();
        if(state.timeline){state.timeline.mediaSelection=clip.id;state.timeline.revealMedia?.(clip.id);}
        seekSourcePreview(clip.end);renderManualControls();
      },
    },
    selected: id => { if(id)closePrimarySourceReview(); if(id && selectedLayerGroupIds().length){state.timeline.mediaSelection=id;renderManualControls();} },
    reviewSource: slot => { void openSourceReview({slot}); },
    chromaPreview: video => new ChromaPreview(video),
    project: () => state.project, audioPanel: document.getElementById("studioPanelAudio"), audioSlot: () => sourceMixerSettings().audioSlot, api, edit: applyManualEdit, pause: pauseAllMedia,
    time: previewTimelineTime, duration: editorDuration, flushSettings: flushProjectSaves, splitIssue: layerSplitIssue,
    duplicatePreview: layerDuplicatePlan, duplicate: duplicateTimelineLayer,
    movePreview: layerMovePlan, move: moveTimelineLayer,
    createClipOpacity: typeof initClipOpacity==="function"?(root,paint)=>initClipOpacity(root,{snapshot:clipOpacitySnapshot,commit:commitClipOpacity,paint}):null,
    createTakeReplacement: typeof initTakeReplacement==="function" ? root=>initTakeReplacement(root,{snapshot:rollingSnapshot,commit:commitTakeReplacement,
      marks:(p,a)=>a.kind==="audio"?readAudioSourceMarks(p,a.id,audioSourceStorage()):readLibraryShotMarks(p,a.id)}) : null,
    createRollCut: typeof initRollingEdit==="function" ? (root,slide=false)=>initRollingEdit(root,{snapshot:rollingSnapshot,commit:commitRollingCut},slide) : null,
    stackPreview: layerStackPlan, stack: stackTimelineLayer,
    overwritePreview: typeof planTrackOverwrite==="function"?planTrackOverwrite:null,
    describeOverwrite: typeof describeTrackOverwrite==="function"?describeTrackOverwrite:null,
    overwriteIssue: ()=>previewUsesSourceTime() || state.preview.playing ? "Pause Edited video before overwriting a destination track." : "",
    placementPlanner: () => createLibraryPlacementPlanner(editorProject()),
    trackState: project => layerTrackState(project), placementPreview: (assetId,time,options) => planLibraryTrackPlacement(editorProject(),assetId,time,options),
    mutationIssue: layerEditProtectionIssue, mutationPlanner: layerProtectionPlanner, assetMutationIssue: layerAssetProtectionIssue,
    trackOrder: project => layerTrackRanks(project), trackPatchIssue: layerTrackPatchIssue, manageTracks: openLayerTrackManager,
    createTrackLevels: typeof initTrackLevelControls === "function" ? initTrackLevelControls : null,
    viewToken: () => state.projectViewToken, singleSelectedClip: () => selectedLayerGroupIds().length ? null : state.timeline?.mediaSelection,
    trackLevels: (project,model) => layerTrackLevels(project,model), trackSoundSummaries: (project,levels,model) => layerTrackSoundSummaries(project,levels,model),
    trackLevelPlan: (id,patch) => planLayerTrackAudio(state.project,id,patch), trackLevelIssue: trackLevelIssue,
    createFrameEditor: typeof initMediaFrameEditor === "function" ? initMediaFrameEditor : null,
    framePreview: layerFramePlan, frameEdit: frameTimelineLayer, prepareFrameEdit,
    sourceMode: previewUsesSourceTime, playing: () => state.preview.playing,
    sourceMatchBlocked: () => {
      const queue=state.saveQueues.get(state.project?.id);
      return state.captionDirty || state.captionContextSave ? "Save or discard the caption text before opening a source."
        : state.manualEditBusy || state.transcriptSaving || state.textStudio?.dirty?.() || state.textStudio?.pending?.size
          || state.textStudio?.saving || queue?.pending || queue?.inFlight ? "Wait for the current changes to finish before opening the source." : "";
    },
    viewerVisible: () => state.studio.open && !elements.resultPanel.hidden,
    frameBusy: () => {
      const queue=state.saveQueues.get(state.project?.id);
      return Boolean(state.transcriptSaving || state.captionContextSave || state.textStudio?.dirty?.()
        || state.textStudio?.pending?.size || state.textStudio?.saving || queue?.pending || queue?.inFlight);
    },
    enabledPreview: layerEnabledPlan, setEnabled: setTimelineLayerEnabled,
    slipPreview: layerSlipPlan, slip: slipTimelineLayer, frame: () => 1 / ([24,25,30,50,60].includes(Number(state.project?.settings?.fps)) ? Number(state.project.settings.fps) : 30),
    trimPreview: layerTrimPlan, trim: trimTimelineLayer, trimBusy: () => state.manualEditBusy || state.transcriptSaving || foregroundBusy(),
    uploadFile: uploadMediaAsset,
    prepareEmptyImport: importIntoEmptyManualEditor,
    cancelImport: cancelActiveJob,
    busy: () => Boolean(previewRepairBusy() || trackLevelUnfinished() || retainedEditStatus() || state.activeJob || state.activeUploads.size || state.jobStartLocks.size || state.stabilizationStudio?.uploading
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
  if (typeof initFirstRecordingGuide === "function") state.firstRecordingGuide = initFirstRecordingGuide(document.getElementById("firstRecordingGuide"), {
    snapshot: () => ({project:state.project, open:state.studio.open, view:state.projectViewToken, retained:Boolean(retainedEditStatus()),
      busy:Boolean(foregroundBusy() || state.manualEditBusy || state.mediaStudio.uploading || state.mediaStudio.importQueue?.running)}),
    importFiles:files => state.mediaStudio.uploadFiles(files), notice:() => state.mediaStudio.status?.textContent,
  });
  initializeLayerGroupControls(panel);
  initializeLayerTrackControls(panel);
  state.stabilizationStudio = new StabilizationStudio(panel, {...state.mediaStudio.options, flush: () => state.mediaStudio.flush()});
  state.stabilizationStudio.node.id = "stabilizationTool";
  document.getElementById("openStabilizationStudio")?.addEventListener("click", openStabilizationTools);
  initializeChromaStudio();
  const speed = document.createElement("div"); speed.className = "picture-speed"; speed.dataset.editorShortcuts = "off";
  speed.innerHTML = '<label>Picture speed <select aria-label="Picture speed"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1">1×</option><option value="1.5">1.5×</option><option value="2">2×</option><option value="4">4×</option></select><span></span></label><p>Picture only: keeps clip length and speech timing. May lose lip sync or hold the last source frame. Select A or B to choose which picture changes.</p>';
  elements.clipTrimForm.after(speed); state.pictureSpeed = speed;
  speed.querySelector("select").addEventListener("change", async event => {
    const clip = state.pictureSpeedClip; if (!clip || foregroundBusy()) return;
    pauseAllMedia();
    await runUiAction(() => applyManualEdit("sequence_speed", {slot:clip.slot,clip_id:clip.id,speed:Number(event.target.value)}), "Changing picture speed");
  });
}

function initializeChromaStudio() {
  if (typeof ChromaStudio === "undefined") return;
  const root = document.getElementById("chromaStudio");
  if (!root) return;
  state.chromaStudio = new ChromaStudio(root, {
    autoPreview: true, assetMutationIssue: layerAssetProtectionIssue,
    project: () => state.project, edit: applyManualEdit, pause: pauseAllMedia, saveStateChanged: renderProjectSaveState,
    busy: () => Boolean(retainedEditStatus()) || foregroundBusy() || state.manualEditBusy,
    translate: (key, fallback) => state.dictionary?.[key] || fallback, api,
    sourceTime: slot => elements[`preview${slot}`]?.currentTime || 0,
    selectedTarget: () => state.project?.manual?.media_clips?.find(clip => clip.id === state.timeline?.mediaSelection)?.asset_id || state.trimClip?.slot,
    openMedia: () => openStudioTab("media"),
    frame: async ({projectId, slot, time, revision}, signal) => {
      const query = new URLSearchParams({time:String(time), revision:String(revision)});
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/chroma-preview/${slot}?${query}`, {signal});
      if (!response.ok) {
        let message = `Frame preview failed (HTTP ${response.status}).`;
        try { const payload = await response.json(); message = payload.message || message; } catch (_error) {}
        throw new Error(message);
      }
      if (!response.headers.get("content-type")?.includes("image/png")) throw new Error("The frame preview did not return a PNG image.");
      return response.blob();
    },
  });
}

function colorMotionOutputTime() {
  return state.project ? sourceToOutputTime(previewPlaybackTime()) : 0;
}

function initColorMotionPanel() {
  const root = document.getElementById("colorMotionRoot");
  if (typeof initColorMotion !== "function" || !root || state.colorMotion) return;
  const summary = document.querySelector("#colorMotionSection > summary");
  if (summary) summary.textContent = uiCopy("צבע ותנועה", "Color & motion");
  state.colorMotion = initColorMotion(root, {
    getProject: () => {
      // Include unsaved edits so a re-render never snaps sliders back.
      const queue = state.project ? state.saveQueues.get(state.project.id) : null;
      return applyPatchToProject(state.project, mergePatchValues(queue?.inFlightPatch || {}, queue?.pending || {}));
    },
    save: (manual) => schedulePatch({ manual }),
    uploadLut: async (file) => {
      const query = new URLSearchParams({ name: file.name.replace(/\.cube$/i, "") });
      const payload = await api(`/api/projects/${encodeURIComponent(state.project.id)}/luts?${query}`, {
        method: "POST", body: file, headers: { "Content-Type": "text/plain" },
      });
      return payload.lut;
    },
    outputTime: colorMotionOutputTime,
    seek: (time) => { pauseAllMedia(); seekPreview(outputToSourceTime(time)); },
    stage: elements.previewStage,
    copy: uiCopy,
    toast,
  });
}

function updateMediaPreview() {
  updateChromaPlayback();
  updateTextPreview();
  state.colorMotion?.sync(colorMotionOutputTime());
  if (!state.mediaStudio || !state.project?.draft) return;
  const project = playbackProject(), time = previewPlaybackTime(), sourceMode = previewUsesSourceTime();
  const mixer = sourceMixerSettings(), slot = mixer.audioSlot || "A", source = project.sources?.[slot];
  const point = previewUsesIndependentTracks() ? trackAt(project,slot,time,mixer.syncOffset)
    : {sourceTime:time-(slot === "B" ? mixer.syncOffset : 0)};
  state.mediaStudio.sync(sourceMode ? time : sourceToOutputTime(time),state.preview.playing && !state.rangeAudition?.preparing,
    {sourceMode,point,url:source ? sourceMediaUrl(source) : null,hasAudio:source?.has_audio});
  if (!sourceMode) { elements.previewA.muted = true; elements.previewB.muted = true; }
}

function updateChromaPlayback() {
  if (typeof ChromaPreview === "undefined") return;
  state.chromaPlayers ||= new Map();
  const project = playbackProject();
  for (const slot of ["A", "B"]) {
    const video=elements[`preview${slot}`]; if (!video?.parentElement) continue;
    // Embedded camera B is a second view of A, not a separate source.
    const target=slot === "B" && !project?.sources?.B ? "A" : slot;
    const settings=previewUsesSourceTime() ? null : project?.manual?.chroma_key?.[target];
    if (settings?.enabled || state.chromaPlayers.has(slot)) {
      if (!state.chromaPlayers.has(slot)) state.chromaPlayers.set(slot,new ChromaPreview(video));
      state.chromaPlayers.get(slot).update(settings,project?.assets?.[settings?.background_asset_id]?.url);
    }
  }
}

function initializeTextStudio() {
  if (typeof TextStudio === "undefined") return;
  const root = document.getElementById("textStudio");
  if (!root) return;
  state.textStudio = new TextStudio(root, elements.previewStage, {
    libraryRoot: document.getElementById("studioShelfCaptions"), saveStateChanged: renderProjectSaveState,
    project: () => state.project, edit: applyManualEdit, time: previewTimelineTime, duration: editorDuration,
    frame: () => 1 / ([24,25,30,50,60].includes(Number(state.project?.settings?.fps)) ? Number(state.project.settings.fps) : 30),
    duplicatePreview: layerDuplicatePlan, duplicate: duplicateTimelineLayer,
    movePreview: layerMovePlan, move: moveTimelineLayer,
    enabledPreview: layerEnabledPlan, setEnabled: setTimelineLayerEnabled,
    trimPreview: layerTrimPlan, trim: trimTimelineLayer, trimBusy: () => state.manualEditBusy || state.transcriptSaving || foregroundBusy(),
    busy: () => Boolean(retainedEditStatus()) || foregroundBusy(), preview: updateTextPreview, dimensions: previewExportDimensions,
    mutationIssue: layerEditProtectionIssue, mutationPlanner: layerProtectionPlanner,
    trackOrder: project => layerTrackRanks(project), trackPatchIssue: layerTrackPatchIssue,
    seek: time => { pauseAllMedia(); if (previewUsesSourceTime()) setPreviewMode("edit"); seekSourcePreview(time); },
    selected: id => { if (state.timeline) { if (id) state.timeline.clearSelection(); state.timeline.mediaSelection = id; state.timeline.scheduleDraw(); if (id && !state.timeline.gesture) state.timeline.revealMedia(id); } },
    selectionRemoved: id => { if (state.timeline?.mediaSelection === id) { state.timeline.mediaSelection = null; state.timeline.clearSelection(); state.timeline.scheduleDraw(); } },
  });
}

function updateTextPreview() {
  if (!state.textStudio) return;
  state.textStudio.sync(previewTimelineTime(), previewUsesSourceTime());
  if (state.timeline && state.project) {
    const project = editorProject();
    state.timeline.project = { ...project, manual: { ...project.manual, text_clips: state.textStudio.clips(false) } };
    state.timeline.scheduleDraw();
  }
}

function savedLayerTrackIssue() {
  return typeof layerTrackState==="function" ? layerTrackState(state.project).issue : "";
}

// Locks protect editing, not navigation, audition or the rendered appearance.
function layerEditProtectionIssue(action, detail = {}) {
  if (typeof layerMutationIssue === "function") return layerMutationIssue(state.project, action, detail);
  return state.project?.manual?.layer_tracks?.version >= 2 ? "Track protection is unavailable. Reload before editing." : "";
}

function layerProtectionPlanner() {
  return typeof createLayerMutationPlanner === "function" ? createLayerMutationPlanner(state.project) : layerEditProtectionIssue;
}

function layerAssetProtectionIssue(assetId) {
  if (typeof layerAssetMutationIssue === "function") return layerAssetMutationIssue(state.project, assetId);
  return state.project?.manual?.layer_tracks?.version >= 2 ? "Track protection is unavailable. Reload before editing this asset." : "";
}

function requireCompatibleLayerTracks() {
  const issue=savedLayerTrackIssue();if(issue){toast(issue);return false;}return true;
}

function renderLayerTrackExportIssue(button, issue) {
  if (!button) return;
  if (issue) {
    if (!button.layerTrackIssueTitle) button.layerTrackIssueTitle={before:button.title||"",applied:issue};
    button.layerTrackIssueTitle.applied=issue;button.title=issue;
  } else if (button.layerTrackIssueTitle) {
    if(button.title===button.layerTrackIssueTitle.applied)button.title=button.layerTrackIssueTitle.before;
    delete button.layerTrackIssueTitle;
  }
}

function layerTrackPatchIssue(clipId, patch) {
  const issue=savedLayerTrackIssue();if(issue)return issue;
  if (!state.project?.manual || !Object.hasOwn(state.project.manual, "layer_tracks")) return "";
  return layerTrackUpdateIssue(state.project, [{clip_id:clipId,...patch}]);
}

function layerTrackMovePlan(clipId, start, trackId) {
  const explicit=explicitPendingDraft();
  if(explicit)return {issue:explicit.detail,patch:null};
  if(state.captionContextSave)return {issue:"Wait for the caption text to finish saving.",patch:null};
  return planLayerTrackMove(state.project,clipId,start,trackId);
}

function trackLevelUnfinished() {
  return Boolean(state.mediaStudio?.trackLevelGesture || state.mediaStudio?.trackLevels?.hasDraft?.());
}

// Readiness excludes this control's own local number/gesture so the user can
// correct or cancel it. Structural operations use explicitPendingDraft instead.
function trackLevelIssue({posting=false,model=null}={}) {
  const project=state.project,studio=state.mediaStudio;model ||= layerTrackState(project);
  if(retainedEditStatus())return retainedEditIssue();
  if(!project?.draft || typeof project.draft!=="object" || Array.isArray(project.draft))return "Open a saved edit before changing track levels.";
  if(model.issue)return model.issue;
  if(!model.enabled)return "Enable editable tracks before setting named track levels.";
  const explicit=explicitPendingDraft();if(explicit && explicit.target!=="track-level")return explicit.detail;
  if(state.captionContextSave || state.transcriptSaving || pendingTranscriptBuffers().length || state.textStudio?.dirty?.() || state.textStudio?.saving)
    return "Save or discard the other unfinished inspector changes before changing track levels.";
  if(state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive || state.timeline?.editPending
    || state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening || studio?.frameEditorState?.dragging || state.embeddedEditor?.dragging)
    return "Finish or cancel the current edit gesture before changing track levels.";
  const queue=state.saveQueues.get(project.id);
  if(foregroundBusy() || !posting && studio?.saving || queue?.pending || queue?.inFlight || state.sourceMixerSavePending || state.chromaStudio?.saving)
    return "Wait for the current save, copy or processing to finish before changing track levels.";
  return "";
}

function layerTrackUnlockRequested(action, detail={}) {
  return action==="layer_track_lock" && detail.locked===false
    && Array.isArray(state.project?.manual?.layer_tracks?.tracks)
    && state.project.manual.layer_tracks.tracks.some(track=>track.id===detail.track_id && track.locked===true);
}

function layerTrackActionIssue({allowUnlock=false}={}) {
  if(!state.project?.draft)return "Open an edit before organizing tracks.";
  const model=layerTrackState(state.project);if(model.issue)return model.issue;
  const explicit=explicitPendingDraft();if(explicit && !allowUnlock)return explicit.detail;
  if(state.captionContextSave)return "Wait for the caption text to finish saving.";
  if(state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive
    || state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening
    || state.mediaStudio?.frameEditorState?.dragging || state.embeddedEditor?.dragging)
    return "Finish or cancel the current gesture or selection before changing tracks.";
  return "";
}

function trackLockIssue(trackId, locked) {
  const unlocking=layerTrackUnlockRequested("layer_track_lock",{track_id:trackId,locked});
  const issue=layerTrackActionIssue({allowUnlock:unlocking}) || layerEditProtectionIssue("layer_track_lock",{track_id:trackId,locked});
  if(issue)return issue;
  if(state.manualEditBusy || foregroundBusy() || state.transcriptSaving || state.timeline?.editPending
    || state.mediaStudio?.saving || state.textStudio?.saving || state.chromaStudio?.saving
    || !unlocking && (state.mediaStudio?.pending?.size || state.textStudio?.pending?.size))
    return "Wait for the current changes to finish before changing track protection.";
  return "";
}

// Paint-only readiness for one synchronous header pass. Never use this receipt
// to authorize a click: trackLockIssue and editLayerTrack recheck current state.
function trackHeaderReadiness(project) {
  const saved=state.project,viewToken=state.projectViewToken,revision=saved?.revision;
  const result=(lockIssue,unlockIssue=lockIssue)=>({project,lockIssue,unlockIssue});
  const stale=()=>result("The timeline changed. Wait for it to refresh before changing track protection.");
  const current=()=>Boolean(saved && project && state.project===saved && state.projectViewToken===viewToken
    && saved.revision===revision && state.timeline?.project===project && project.id===saved.id
    && project.revision===revision && project.manual?.layer_tracks===saved.manual?.layer_tracks);
  if(!current())return stale();
  if(!saved.draft)return result("Open an edit before organizing tracks.");
  if(typeof layerTrackState!=="function")return result("Track protection is unavailable. Reload before editing.");
  const model=layerTrackState(saved);
  if(model.issue)return result(model.issue);
  const explicit=explicitPendingDraft();
  const common=state.captionContextSave ? "Wait for the caption text to finish saving."
    : state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive
      || state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening
      || state.mediaStudio?.frameEditorState?.dragging || state.embeddedEditor?.dragging
      ? "Finish or cancel the current gesture or selection before changing tracks." : "";
  const unavailable=typeof layerMutationIssue!=="function" && saved.manual?.layer_tracks?.version>=2
    ? "Track protection is unavailable. Reload before editing." : "";
  // A validated track model has no per-row lock mutation constraint. Unlock is
  // chosen only for a saved locked row by Timeline's independently parsed model.
  const busy=state.manualEditBusy || foregroundBusy() || state.transcriptSaving || state.timeline?.editPending
    || state.mediaStudio?.saving || state.textStudio?.saving || state.chromaStudio?.saving;
  const wait="Wait for the current changes to finish before changing track protection.";
  const unlockIssue=common || unavailable || (busy ? wait : "");
  const lockIssue=explicit?.detail || common || unavailable
    || (busy || state.mediaStudio?.pending?.size || state.textStudio?.pending?.size ? wait : "");
  return current() ? result(lockIssue,unlockIssue) : stale();
}

function renderLayerTrackControls() { state.layerTrackManager?.sync?.(); state.mediaStudio?.syncTrackLevels?.(); }

function initializeLayerTrackControls(panel) {
  if(typeof initLayerTrackManager!=="function")return;
  const root=document.createElement("section");root.className="layer-track-manager";
  root.dataset.editorShortcuts="off";
  const inspector=panel.querySelector(".media-inspector");if(inspector)inspector.before(root);else panel.append(root);
  state.layerTrackManager=initLayerTrackManager(root,{
    snapshot:()=>({project:state.project,selectedClipId:selectedLayerGroupIds().length?null:state.timeline?.mediaSelection,
      issue:layerTrackActionIssue(),busy:Boolean(state.manualEditBusy || foregroundBusy() || state.transcriptSaving
        || state.timeline?.editPending || state.mediaStudio?.saving || state.textStudio?.saving
        || state.mediaStudio?.pending?.size || state.textStudio?.pending?.size)}),
    action:editLayerTrack,planMove:layerTrackMovePlan,lockIssue:trackLockIssue,
  });
}

async function openLayerTrackManager(trackId) {
  const request=beginInspectorSelection();
  if(!await prepareInspectorSelection(request) || !inspectorSelectionCurrent(request))return false;
  if(!openStudioTab("media"))return false;
  closePrimarySourceReview();state.mediaStudio?.closeSourceMonitor?.();
  state.layerTrackManager?.sync?.();state.layerTrackManager?.reveal?.(trackId);return true;
}

async function editLayerTrack(action, detail={}) {
  const allowed=["layer_tracks_enable","layer_track_add","layer_track_rename","layer_track_reorder","layer_track_remove","layer_track_lock","layer_move"];
  if(!allowed.includes(action))return null;
  const unlocking=layerTrackUnlockRequested(action,detail);
  const issue=layerTrackActionIssue({allowUnlock:unlocking}) || layerEditProtectionIssue(action,detail);if(issue){toast(issue);return null;}
  if(unlocking && (state.mediaStudio?.saving || state.textStudio?.saving || state.chromaStudio?.saving))return null;
  if(state.manualEditBusy || foregroundBusy() || state.transcriptSaving)return null;
  if(action==="layer_move" && selectedLayerGroupIds().length){toast("Select one clip before assigning a track. Group moves keep their existing tracks.");return null;}
  const projectId=state.project.id,viewToken=state.projectViewToken;
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken;
  return applyManualEdit(action,detail,{strictRevision:true,isCurrent:current,admissionCurrent:current});
}

function editLayerAction(action, detail) {
  if(action==="layers_match_frame")return matchTimelineLayerGroup(detail.clip_ids,detail.reference_id);
  if(action==="layer_move" || action==="layer_track_lock")return editLayerTrack(action,detail);
  if(action==="layers_move")return moveTimelineLayerGroup(detail.clip_ids,detail.delta);
  if(action==="layers_relocate")return relocateTimelineLayerGroup(detail.clip_ids,detail.anchor_id,detail.delta,detail.track_id,{timelineRequest:state.timeline?.mediaGroupRelocationPending});
  if(action==="layers_remove")return removeTimelineLayerGroup(detail.clip_ids);
  if(action==="layers_duplicate")return duplicateTimelineLayerGroup(detail.clip_ids,detail.start);
  if(groupBlocksAction(action)){toast(groupSelectionIssue());return null;}
  if (action === "media_split") return splitTimelineLayer(detail.clip_id, detail.time);
  if (action === "media_trim") return trimTimelineLayer(detail.clip_id, detail.edge, detail.time);
  if (action === "media_slip") return slipTimelineLayer(detail.clip_id, detail.source_start);
  if (action === "media_duplicate") return duplicateTimelineLayer(detail.clip_id, detail.start);
  if (action === "media_move") return moveTimelineLayer(detail.clip_id, detail.start);
  if (String(detail.clip_id).startsWith("text_")) return state.textStudio?.action(action.replace("media_", "text_"), detail);
  return runUiAction(() => applyManualEdit(action,detail), "Editing media");
}

function layerSplitTime(time) {
  const fps = Number(state.project?.settings?.fps), rate = [24, 25, 30, 50, 60].includes(fps) ? fps : 30;
  return Number.isFinite(time) ? Math.round(time * rate) / rate : time;
}

function layerSplitIssue(clipId, time) {
  const protection=layerEditProtectionIssue(String(clipId).startsWith("text_")?"text_split":"media_split",{clip_id:clipId,time});if(protection)return protection;
  if (state.captionDirty || state.captionContextSave) return "Save or discard the caption text before splitting a clip.";
  const project = state.project, text = String(clipId).startsWith("text_"), key = text ? "text_clips" : "media_clips";
  const rows = project?.manual?.[key] || [], clip = rows.find(row => row.id === clipId);
  if (!project?.draft || !clip) return "The selected clip is no longer available. Select it again before splitting.";
  time = layerSplitTime(time);
  if (!Number.isFinite(time) || time - clip.start < .08 - 1e-9 || clip.end - time < .08 - 1e-9) return "Move the playhead inside the selected clip, leaving at least 0.08 seconds on each side.";
  if (rows.length >= (text ? 2000 : 200)) return `Splitting would exceed the ${text ? "2000 text" : "200 media"} clip limit.`;
  if (text) return clip.template==="chapter" ? "A Chapter title has a built-in fade. Splitting it would restart the fade; choose a static template to split." : "";
  const asset = project.assets?.[clip.asset_id];
  if (!asset || asset.status !== "ready") return "The selected media is not ready. Prepare it before splitting.";
  if (asset.kind !== "audio" && (clip.motion || "none") !== "none") return "Splitting this pan/zoom clip would restart its motion. Turn off motion or keep the occurrence intact.";
  if (time - clip.start < Number(clip.fade_in || 0) - 1e-9 || clip.end - time < Number(clip.fade_out || 0) - 1e-9) return "The split point is inside a media audio fade. Choose a point outside the fade.";
  return "";
}

// Audio-source navigation never flushes drafts. Its one explicit Add uses the
// existing media_add action, but has a strict whole-passage receipt of its own.
function audioSourceStorage() {
  try { return localStorage; } catch { return null; }
}
function clearAudioSourceNotice() {
  const notice=state.audioSourceNotice;
  if(notice && state.mediaStudio?.status?.textContent===notice.message)state.mediaStudio.status.textContent='';
  state.audioSourceNotice=null;
}
function showAudioSourceNotice(message,projectId,viewToken,owner) {
  if(state.project?.id!==projectId || state.projectViewToken!==viewToken)return;
  state.audioSourceNotice={message,projectId,viewToken};
  if(state.mediaStudio?.status)state.mediaStudio.status.textContent=message;
  if(state.mediaStudio?.shotReview!==owner || !owner.open)toast(message);
}
function audioSourceNavigationIssue(owner=null) {
  const project=state.project,media=state.mediaStudio,timeline=state.timeline;
  const own=Boolean(owner && owner===media?.shotReview && state.audioSourcePlacement?.owner===owner
    && state.audioSourcePlacement.projectId===project?.id && state.audioSourcePlacement.viewToken===state.projectViewToken);
  const fence=state.audioSourceFences.get(project?.id);
  if(fence?.viewToken===state.projectViewToken)return fence.message;
  if(!project?.id || !Number.isInteger(project.revision) || project.revision<1 || !timeline || !state.studio.open
    || !project.draft || typeof project.draft!=="object" || Array.isArray(project.draft))return "Open a saved edit in Studio before reviewing imported audio.";
  if(!project.sources?.A || !Number.isFinite(project.sources.A.duration) || project.sources.A.duration<=0)return "Open or resume a saved edit with its original Source A before reviewing imported audio.";
  if(previewUsesSourceTime())return "Switch Program to Edited before reviewing imported audio. Source audition has its own clock.";
  const model=savedLayerTrackIssue();if(model)return model;
  const source=sourceMonitorIssue();if(source)return source;
  if(previewRepairBusy() || projectCopySourceBusy() || state.activeJob || state.activeUploads.size || state.jobStartLocks.size
    || media?.uploading || media?.placing || media?.importQueue?.running || state.stabilizationStudio?.uploading
    || (!own && (state.manualEditBusy || state.manualEditPromise || state.audioSourcePlacement)))return "Wait for the current save, import or processing before reviewing audio.";
  const sourceTimeline=state.sourceReview?.timeline;
  if(timeline.gesture || timeline.scrubbing || timeline.libraryDragActive || timeline.editPending || timeline.mediaSelectionPending || timeline.mediaSourceOpening
    || sourceTimeline?.gesture || sourceTimeline?.scrubbing || state.sourceReview?.busy || media?.frameEditor?.active
    || media?.frameEditorState?.dragging || state.embeddedEditor?.dragging || document.documentElement?.classList?.contains?.("numeric-scrubbing")
    || (media?.shotReview?.pending && media.shotReview!==owner))return "Finish or cancel the current gesture or source placement before reviewing audio.";
  if(!own){const saved=projectSaveStatus();if(saved.kind!=="saved" || hasUnsavedProjectWork())return saved.detail || "Save or discard pending changes first. Opening audio never saves them.";}
  return "";
}
function refreshAudioSourceSnapshot() {
  // Do not hydrate/seek: audio placement leaves the saved edit clock unchanged.
  state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
  if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
  updateMediaPreview();renderManualControls();renderLayerTrackControls();
}
function scheduleAudioSourceReveal({owner,projectId,viewToken,revision,clipId,at,pane,viewport,trackId}) {
  const timeline=state.timeline;let cancelled=false;
  const cancel=()=>{cancelled=true;},events=['pointerdown','keydown','wheel','input','change','focusin'];
  for(const event of events)document.addEventListener?.(event,cancel,true);
  requestAnimationFrame(()=>{
    for(const event of events)document.removeEventListener?.(event,cancel,true);
    // The controller has settled by this frame, so its pending-operation guard
    // no longer owns admission. Keep only this accepted result's UI identity.
    if(!cancelled && state.timeline===timeline && state.project?.id===projectId && state.projectViewToken===viewToken
      && state.project.revision===revision && state.mediaStudio?.shotReview===owner && owner.open
      && timeline?.mediaSelection===clipId && state.mediaStudio.selected===clipId && previewTimelineTime()===at
      && (state.mediaStudio.destinationTrackId||'')===trackId && layerGroupDuplicateContext()===pane
      && layerGroupDuplicateViewport()===viewport)timeline?.revealMedia?.(clipId);
  });
}
async function placeAudioSource(plan,context={},owner=null) {
  const refused=message=>({status:"refused",message});
  const project=state.project,projectId=project?.id,viewToken=state.projectViewToken;
  if(state.audioSourcePlacement)return refused("Wait for the current audio placement to finish. It will not be repeated.");
  if(!owner || state.mediaStudio?.shotReview!==owner || !owner.open || typeof context.isCurrent!=="function" || typeof context.admissionCurrent!=="function")return refused("Open the audio source again before adding a passage.");
  const issue=audioSourceNavigationIssue(owner);if(issue)return refused(issue);
  const at=previewTimelineTime();
  const fresh=planAudioSourcePlacement(project,plan?.assetId,at,plan,
    Object.hasOwn(plan||{},"trackId")?{trackId:plan.trackId}:{});
  if(fresh.issue || JSON.stringify(fresh)!==JSON.stringify(plan))return refused(fresh.issue || "The passage or destination changed. Review it before adding.");
  if(!context.isCurrent() || !context.admissionCurrent() || state.project!==project || state.projectViewToken!==viewToken)return refused("The source view changed before adding. Nothing was submitted.");
  const intent=structuredClone(fresh),before=structuredClone(project),pane=layerGroupDuplicateContext(),viewport=layerGroupDuplicateViewport();
  const token={owner,projectId,viewToken};
  const owned=()=>state.project?.id===projectId && state.projectViewToken===viewToken && state.mediaStudio?.shotReview===owner
    && owner.open && previewTimelineTime()===at && (state.mediaStudio.destinationTrackId||'')===(intent.trackId||'')
    && layerGroupDuplicateContext()===pane && context.isCurrent();
  let finish;const promise=new Promise(resolve=>{finish=resolve;});
  state.audioSourcePlacement=token;state.manualEditBusy=true;state.manualEditPromise=promise;
  let submitted=false,confirmed=false,savedResult=null;
  try {
    // These synchronous UI updates may notify other owners. Recheck the exact
    // intent afterward, immediately before the sole POST. There is no flush.
    pauseAllMedia();updateMediaPreview();renderReadiness();renderManualControls();
    const finalIssue=audioSourceNavigationIssue(owner),admitted=context.admissionCurrent();
    if(finalIssue || !owned() || !admitted || state.project!==project || state.projectViewToken!==viewToken
      || JSON.stringify(state.project)!==JSON.stringify(before) || JSON.stringify(plan)!==JSON.stringify(intent))return refused(finalIssue || "The source view changed before adding. Nothing was submitted.");
    state.timeline?.cancelPendingCut?.();
    submitted=true;
    const payload=await api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`,{
      method:"POST",body:JSON.stringify({action:"media_add",...intent.payload,expected_revision:intent.revision}),
    });
    const receipt=verifyAudioSourcePlacement(before,payload?.project,intent);
    if(receipt.issue)throw new Error(`The saved audio result could not be verified. ${receipt.issue}`);
    confirmed=true;
    savedResult={status:"saved",projectId,revision:payload.project.revision,clipId:receipt.clipId,message:"Selected audio added. The edited playhead and existing layers stayed in place."};
    rememberProjectRevision(payload.project);
    if(state.project===project && state.projectViewToken===viewToken && JSON.stringify(state.project)===JSON.stringify(before)){
      const select=owned();
      state.project=payload.project;
      if(select){
        state.timeline?.clearSelection();state.manualSelection=null;state.trimClip=null;state.markIn=null;clearCaptionInspectorSelection();
        if(state.timeline)state.timeline.mediaSelection=receipt.clipId;
        if(state.mediaStudio)state.mediaStudio.selected=receipt.clipId;
        if(state.textStudio)state.textStudio.selected=null;
      }
      refreshAudioSourceSnapshot();
      if(select){
        scheduleAudioSourceReveal({owner,projectId,viewToken,revision:payload.project.revision,clipId:receipt.clipId,
          at,pane,viewport,trackId:intent.trackId||''});
      }
    }
    return savedResult;
  } catch(error) {
    // A 4xx rejection is known not to admit this edit. Lost responses, server
    // failures and unverified receipts are not permission to repeat the POST.
    const rejected=Number(error?.status)>=400 && Number(error?.status)<500;
    const uncertain=submitted && !confirmed && !rejected;
    if(uncertain || Number(error?.status)===409){
      const message=uncertain ? "The audio placement result is unconfirmed. Reopen this project to inspect the saved edit before adding again; the request was not repeated."
        : "The project changed or is busy. Reopen it to review the saved edit before adding again; nothing was repeated.";
      state.audioSourceFences.set(projectId,{viewToken,message});
      showAudioSourceNotice(message,projectId,viewToken,owner);
      return {status:uncertain?"unknown":"refused",message};
    }
    if(confirmed){
      state.audioSourceFences.set(projectId,{viewToken,message:"The audio was saved, but its view could not refresh. Reopen this project before adding again."});
      showAudioSourceNotice("The audio was saved, but its view could not refresh. Reopen this project before adding again.",projectId,viewToken,owner);
      return {...savedResult,message:"The audio was saved. Reopen this project to review it; the view could not refresh."};
    }
    return refused(error?.message || "Audio could not be added. The request was not repeated.");
  } finally {
    if(state.audioSourcePlacement===token){state.audioSourcePlacement=null;state.manualEditBusy=false;}
    if(state.manualEditPromise===promise)state.manualEditPromise=null;
    finish();renderReadiness();renderManualControls();renderProjectSaveState();
  }
}

function sourceMonitorIssue() {
  const recovery=retainedEditIssue();if(recovery)return recovery;
  const explicit=explicitPendingDraft();
  if(explicit)return explicit.detail;
  if(pendingTranscriptBuffers().length)return "Save or discard the recorded-speech text before adding source shots.";
  const queue=state.saveQueues.get(state.project?.id);
  if(state.transcriptSaving || state.captionContextSave || state.textStudio?.dirty?.() || state.textStudio?.pending?.size
    || state.textStudio?.saving || state.mediaStudio?.pending?.size || state.mediaStudio?.saving
    || state.sourceMixerSavePending || state.sourceSyncPending || liveEmbeddedCameraRequest()
    || queue?.pending || queue?.inFlight)return "Wait for the current changes to finish before using source controls.";
  return "";
}

function openTimelineSource(id, time) {
  const studio=state.mediaStudio,plan=studio?.sourceMatchPlan(id,time);
  if(!plan || plan.issue){if(plan?.issue && studio?.status)studio.status.textContent=plan.issue;return false;}
  // A timeline double-click navigates to its clicked edit point; the inspector's
  // separate source command does not move the current edit cursor.
  pauseAllMedia();seekSourcePreview(time);
  return studio.openSourceAt(id,time);
}

function layerFramePlan(clipId, geometry) {
  const protection=layerEditProtectionIssue("media_transform",{clip_id:clipId,...geometry});if(protection)return {issue:protection,patch:null};
  const blocked=issue=>({issue,patch:null}),project=state.project;
  if(project?.editor_sequence?.error)return blocked(project.editor_sequence.error);
  if(state.captionDirty || state.captionContextSave)return blocked("Save or discard the caption text before framing a clip.");
  const clip=project?.manual?.media_clips?.find(row=>row.id===clipId),asset=project?.assets?.[clip?.asset_id];
  if(!project?.draft || !clip)return blocked("The selected media clip is no longer available. Select it again.");
  if(!asset || asset.status!=="ready" || !["video","image"].includes(asset.kind))return blocked("Viewer framing is available for ready imported video and images only.");
  const keys=["x","y","w","h"];
  if(!geometry || typeof geometry!=="object" || Array.isArray(geometry) || Object.keys(geometry).length!==4
    || Object.keys(geometry).some(key=>!keys.includes(key)) || keys.some(key=>typeof geometry[key]!=="number" || !Number.isFinite(geometry[key])))return blocked("Choose a finite position and size for the frame.");
  if(keys.some(key=>geometry[key]<(["w","h"].includes(key) ? .01 : 0) || geometry[key]>1))return blocked("Keep the frame inside the canvas, at least 1% wide and high.");
  const patch=Object.fromEntries(keys.map(key=>[key,Math.round(geometry[key]*1e9)/1e9]));
  if(keys.some(key=>patch[key]<(["w","h"].includes(key) ? .01 : 0) || patch[key]>1)
    || patch.x+patch.w>1+1e-8 || patch.y+patch.h>1+1e-8)return blocked("Keep the frame inside the canvas, at least 1% wide and high.");
  if(keys.some(key=>!Number.isFinite(clip[key])))return blocked("The saved frame is invalid. Reload the project before changing it.");
  return {issue:"",patch:keys.every(key=>Math.abs(patch[key]-clip[key])<=1e-9)?{}:patch};
}

function frameTimelineLayer(clipId, geometry) {
  return applyManualEdit("media_transform",{clip_id:clipId,...geometry});
}

async function prepareFrameEdit(clipId) {
  const projectId=state.project?.id;
  if(!projectId || foregroundBusy() || state.transcriptSaving || state.captionDirty || state.captionContextSave)return false;
  pauseAllMedia();
  if(state.textStudio && await state.textStudio.flush()===false)return false;
  if(state.project?.id!==projectId || state.mediaStudio?.selected!==clipId || foregroundBusy())return false;
  if(state.mediaStudio && await state.mediaStudio.flush()===false)return false;
  await flushProjectSaves(projectId);
  return state.project?.id===projectId && state.mediaStudio?.selected===clipId && !foregroundBusy()
    && !state.transcriptSaving && !state.captionDirty && !state.captionContextSave;
}

function layerEnabledPlan(clipId, enabled) {
  const protection=layerEditProtectionIssue(String(clipId).startsWith("text_")?"text_set_enabled":"media_set_enabled",{clip_id:clipId,enabled});if(protection)return {issue:protection,patch:null};
  const blocked = issue => ({issue, patch:null}), project = state.project;
  if (typeof enabled !== "boolean") return blocked("Choose whether this occurrence is enabled.");
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before changing clip availability.");
  const text=String(clipId).startsWith("text_"),clip=project?.manual?.[text?"text_clips":"media_clips"]?.find(row=>row.id===clipId);
  if (!project?.draft || !clip) return blocked("The selected media/text clip is no longer available. Select it again.");
  if (clip.enabled !== undefined && typeof clip.enabled !== "boolean") return blocked("The saved clip availability is invalid. Reload the project before changing it.");
  if (enabled && !text) {
    const asset=project.assets?.[clip.asset_id];
    if (!asset || asset.status!=="ready" || !["video","audio","image"].includes(asset.kind)) return blocked("The selected media is not ready. Prepare it before enabling.");
  }
  return {issue:"",patch:(clip.enabled!==false)===enabled ? {} : {enabled}};
}

function setTimelineLayerEnabled(clipId, enabled) {
  return applyManualEdit(String(clipId).startsWith("text_") ? "text_set_enabled" : "media_set_enabled", {clip_id:clipId,enabled});
}

function layerStackPlan(clipId, position) {
  const blocked = issue => ({issue, patch:null}), project = state.project;
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before changing visual stacking.");
  if(project?.manual && Object.hasOwn(project.manual,"layer_tracks"))return blocked("Saved tracks now control visual priority. Use Tracks to move the clip or reorder its whole track.");
  if (!["backward","forward","back","front"].includes(position)) return blocked("Choose backward, forward, back or front for visual stacking.");
  const rows = project?.manual?.media_clips || [], assets = project?.assets || {};
  if (!project?.draft || !rows.some(row=>row.id===clipId)) return blocked("The selected imported visual clip is no longer available. Select it again.");
  if (new Set(rows.map(row=>row.id)).size !== rows.length) return blocked("Timeline media identifiers must be unique before changing visual stacking.");
  if (rows.some(row=>!assets[row.asset_id] || !["video","image","audio"].includes(assets[row.asset_id].kind) || assets[row.asset_id].status!=="ready"))
    return blocked("Timeline media is missing or not ready. Prepare it before changing visual stacking.");
  const visuals = rows.filter(row=>["video","image"].includes(assets[row.asset_id].kind)), index = visuals.findIndex(row=>row.id===clipId);
  if (index<0) return blocked("Visual stacking is only for imported video and images, not audio or text.");
  const target = {backward:Math.max(0,index-1),forward:Math.min(visuals.length-1,index+1),back:0,front:visuals.length-1}[position];
  return {issue:"", patch:target===index ? {} : {position}, rank:index+1, count:visuals.length, destination:target+1};
}

function stackTimelineLayer(clipId, position) {
  return applyManualEdit("media_reorder", {clip_id:clipId, position});
}

function selectedLayerGroupIds() {
  const ids=state.timeline?.selectedMediaIds?.();
  return Array.isArray(ids) && ids.length>1 ? ids : [];
}

function layerGroupMovePlan(ids, delta) {
  const protection=layerEditProtectionIssue("layers_move",{clip_ids:ids,delta});if(protection)return {issue:protection,delta:null,patches:null};
  if(state.captionDirty || state.captionContextSave)return {issue:"Save or discard the caption text before moving selected clips.",delta:null,patches:null};
  const plan=planLayerGroupMove(state.project,ids,delta);
  if(!plan.issue && state.project?.manual && Object.hasOwn(state.project.manual,"layer_tracks")){
    const issue=layerTrackUpdateIssue(state.project,plan.patches||[]);if(issue)return {issue,delta:null,patches:null};
  }
  return plan;
}

function previewLayerGroup(patches) {
  // Destination-track ghosts belong to the timeline only. Never paint a time
  // override with the old stacking order and imply it is the proposed result.
  if(patches?.some(row=>Object.hasOwn(row,"track_id"))){pauseAllMedia();patches=null;}
  if(patches && state.preview.playing)pauseAllMedia();
  state.mediaStudio?.previewGroup?.(patches?.filter(row=>!row.clip_id.startsWith("text_")) || null);
  state.textStudio?.previewGroup?.(patches?.filter(row=>row.clip_id.startsWith("text_")) || null);
  updateMediaPreview();
  state.timeline?.scheduleDraw?.();
}

function layerGroupRelocatePlan(ids, anchorId, delta, trackId) {
  const blocked=issue=>({issue,delta:null,patches:null});
  const recovery=retainedEditIssue();if(recovery)return blocked(recovery);
  const explicit=explicitPendingDraft();if(explicit)return blocked(explicit.detail);
  if(state.captionContextSave)return blocked("Wait for the caption text to finish saving before moving tracks.");
  if(state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening || state.timeline?.trackLockPending
    || state.mediaStudio?.frameEditor?.active)return blocked("Finish the current selection, source or frame operation before moving tracks.");
  return planLayerGroupRelocate(state.project,ids,anchorId,trackId,delta);
}

function layerGroupRelocationOwned(request, ids, anchorId, delta, trackId) {
  return Boolean(request && state.timeline?.mediaGroupRelocationPending===request && state.timeline?.editPending
    && request.projectId===state.project?.id && request.anchorId===anchorId && request.trackId===trackId && request.delta===delta
    && Array.isArray(request.ids) && Array.isArray(ids) && JSON.stringify([...request.ids].sort())===JSON.stringify([...ids].sort()));
}

function layerGroupRelocateIssue(ids, anchorId, delta, trackId, {timelineRequest=null}={}) {
  const ownPending=layerGroupRelocationOwned(timelineRequest,ids,anchorId,delta,trackId);
  if(foregroundBusy() || state.manualEditBusy || state.transcriptSaving || state.timeline?.editPending && !ownPending)
    return "Wait for the current save or preparation to finish.";
  if(state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive)
    return "Finish or cancel the current timeline gesture first.";
  return layerGroupRelocatePlan(ids,anchorId,delta,trackId).issue;
}

function ownGroupRelocateFocus(owner) {
  if(!owner || document.activeElement!==owner)return ()=>{};
  const projectId=state.project?.id,token=state.projectViewToken,context=layerGroupDuplicateContext(),
    members=JSON.stringify([...selectedLayerGroupIds()].sort()),primary=state.timeline?.mediaSelection;
  let moved=false;
  const interaction=()=>{moved=true;},focus=e=>{if(e.target!==owner && e.target!==document.body)moved=true;};
  document.addEventListener("pointerdown",interaction,true);document.addEventListener("keydown",interaction,true);
  document.addEventListener("focusin",focus,true);window.addEventListener("blur",interaction);
  return success=>requestAnimationFrame(()=>{
    document.removeEventListener?.("pointerdown",interaction,true);document.removeEventListener?.("keydown",interaction,true);
    document.removeEventListener?.("focusin",focus,true);window.removeEventListener?.("blur",interaction);
    if(!success || moved || state.project?.id!==projectId || state.projectViewToken!==token || layerGroupDuplicateContext()!==context
      || JSON.stringify([...selectedLayerGroupIds()].sort())!==members || state.timeline?.mediaSelection!==primary
      || document.activeElement!==document.body || owner.isConnected===false || owner.getClientRects && !owner.getClientRects().length)return;
    const target=owner.disabled?state.layerGroupPanel?.querySelector("[data-group-track]"):owner;
    if(target && !target.disabled && !target.hidden && target.isConnected!==false && (!target.getClientRects || target.getClientRects().length))target.focus({preventScroll:true});
  });
}

async function relocateTimelineLayerGroup(ids, anchorId, delta, trackId, {focusOwner=null,timelineRequest=null}={}) {
  const issue=layerGroupRelocateIssue(ids,anchorId,delta,trackId,{timelineRequest});
  if(issue){toast(issue);return null;}
  const signature=JSON.stringify([...ids].sort()),primary=state.timeline?.mediaSelection;
  if(signature!==JSON.stringify([...selectedLayerGroupIds()].sort()) || !ids.includes(primary)){
    toast("Select the same clips again before moving them between tracks.");return null;
  }
  const plan=layerGroupRelocatePlan(ids,anchorId,delta,trackId);if(!plan.patches?.length)return state.project;
  const projectId=state.project.id,token=state.projectViewToken,context=layerGroupDuplicateContext();
  const current=()=>state.project?.id===projectId && state.projectViewToken===token
    && state.timeline?.mediaSelection===primary && JSON.stringify([...selectedLayerGroupIds()].sort())===signature
    && layerGroupDuplicateContext()===context && (!timelineRequest || state.timeline?.mediaGroupRelocationPending===timelineRequest);
  const admission=()=>current() && !state.timeline?.gesture && !state.timeline?.scrubbing && !state.timeline?.libraryDragActive;
  const finish=ownGroupRelocateFocus(focusOwner);let result=null;
  pauseAllMedia();
  try {result=await applyManualEdit("layers_relocate",{clip_ids:[...ids],anchor_id:anchorId,track_id:trackId,delta:plan.delta},
    {strictRevision:true,isCurrent:current,admissionCurrent:admission});return result;}
  finally {finish(Boolean(result && current() && state.project.revision===result.revision));}
}

function renderLayerGroupTrackControls(node, ids) {
  const box=node.querySelector("[data-group-track-controls]");if(!box)return;
  const select=box.querySelector("[data-group-track]"),button=box.querySelector("[data-group-relocate]"),status=box.querySelector("[data-group-track-status]"),
    label=box.querySelector("[data-group-track-label]"),model=layerTrackState(state.project),primary=state.timeline?.mediaSelection;
  const media=state.project?.manual?.media_clips,text=state.project?.manual?.text_clips,
    rows=[...(Array.isArray(media)?media:[]),...(Array.isArray(text)?text:[])].filter(row=>row && ids.includes(row.id)),
    anchor=rows.find(row=>row.id===primary),tracks=model.tracks||[],track=tracks.find(row=>row.id===anchor?.track_id),
    same=rows.length===ids.length && track && rows.every(row=>tracks.find(t=>t.id===row.track_id)?.kind===track.kind);
  const unavailable=model.issue || (!model.enabled?"Enable editable tracks to move a group between tracks. Time moves still work.":!same?"A mixed selection moves in time only. Select only picture, audio or text clips to move across tracks.":"");
  select.hidden=button.hidden=label.hidden=Boolean(unavailable);
  if(unavailable){status.textContent=unavailable;select.disabled=button.disabled=true;return;}
  const identity=JSON.stringify([state.project?.id,state.projectViewToken,[...ids].sort(),primary]);
  if(node.groupTrackContext!==identity){node.groupTrackContext=identity;node.groupTrackChoice=anchor.track_id;}
  const compatible=tracks.filter(row=>row.kind===track.kind),choice=node.groupTrackChoice,
    signature=JSON.stringify([compatible,choice]);
  if(node.groupTrackOptions!==signature){
    const options=compatible.slice().reverse().map(row=>{const option=document.createElement("option");option.value=row.id;option.textContent=row.name+(row.locked?" (locked)":"");option.disabled=Boolean(row.locked);return option;});
    if(!compatible.some(row=>row.id===choice)){const missing=document.createElement("option");missing.value=choice;missing.textContent="Destination no longer available";missing.disabled=true;options.unshift(missing);}
    select.replaceChildren(...options);node.groupTrackOptions=signature;
  }
  select.value=choice;
  const name=String(primary?.startsWith("text_") ? anchor.text || "Text clip" : state.project?.assets?.[anchor.asset_id]?.name || (track.kind==="audio"?"Audio clip":"Picture clip"));
  label.textContent=`Destination for ${name.slice(0,80)}`;
  select.title=`Move ${name.slice(0,80)} to this track; the other selected clips keep their relative track spacing.`;
  const issue=layerGroupRelocateIssue(ids,primary,0,choice),plan=layerGroupRelocatePlan(ids,primary,0,choice),
    busy=foregroundBusy() || state.manualEditBusy || state.transcriptSaving || state.timeline?.editPending || state.timeline?.gesture || state.timeline?.mediaSelectionPending;
  select.disabled=Boolean(busy);button.disabled=Boolean(issue || !plan.patches?.length);
  button.title=issue || (!plan.patches?.length?"Choose another destination track.":"Move all selected clips by the same track offset in one Undo step. Timing and source clocks stay unchanged.");
  status.textContent=issue || (!plan.patches?.length?"Choose a destination for the primary selected clip; the group keeps its track spacing.":"Ready to move the group. Track spacing and timing stay fixed; Program remains saved until Apply. No tracks are created. Destination track gain and mute apply to moved sound.");
}

function layerGroupRemovePlan(ids) {
  const protection=layerEditProtectionIssue("layers_remove",{clip_ids:ids});if(protection)return {issue:protection,clip_ids:null};
  const explicit=explicitPendingDraft();
  if(explicit)return {issue:explicit.detail,clip_ids:null};
  if(state.captionContextSave)return {issue:"Wait for the caption text to finish saving before removing selected clips.",clip_ids:null};
  if(state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive
    || state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening)
    return {issue:"Finish or cancel the current timeline gesture or selection before removing clips.",clip_ids:null};
  return planLayerGroupRemove(state.project,ids);
}

function layerGroupRemoveIssue(ids) {
  if(foregroundBusy() || state.transcriptSaving)return "Wait for the current save or preparation to finish.";
  return layerGroupRemovePlan(ids).issue;
}

function layerGroupDuplicatePlan(ids, start) {
  const blocked=issue=>({issue,start:null,delta:null,copies:null});
  const recovery=retainedEditIssue();if(recovery)return blocked(recovery);
  const explicit=explicitPendingDraft();if(explicit)return blocked(explicit.detail);
  if(state.captionContextSave)return blocked("Wait for the caption text to finish saving before duplicating selected clips.");
  if(state.timeline?.gesture || state.timeline?.scrubbing || state.timeline?.libraryDragActive
    || state.timeline?.mediaSelectionPending || state.timeline?.mediaSourceOpening || state.timeline?.trackLockPending)
    return blocked("Finish or cancel the current timeline gesture or selection before duplicating clips.");
  const protection=layerEditProtectionIssue("layers_duplicate",{clip_ids:ids,start});if(protection)return blocked(protection);
  return planLayerGroupDuplicate(state.project,ids,layerSplitTime(start));
}

function layerGroupDuplicateIssue(ids, start) {
  if(foregroundBusy() || state.manualEditBusy || state.transcriptSaving || state.timeline?.editPending)return "Wait for the current save, selection or preparation to finish.";
  return layerGroupDuplicatePlan(ids,start).issue;
}

function layerGroupDuplicateContext() {
  return JSON.stringify([state.studio.open,state.preview.mode,elements.advancedPanel?.dataset?.aiRequestContext,
    document.querySelector(".advanced-tabs button.active")?.dataset?.tab,
    document.getElementById("studioInspector")?.dataset?.workbenchPane]);
}

function layerGroupDuplicateViewport() {
  const scroll=state.timeline?.scroll;
  return JSON.stringify([scroll?.scrollTop,scroll?.scrollLeft,scroll?.clientHeight,scroll?.clientWidth,state.timeline?.zoom,state.timeline?.playhead]);
}

function ownGroupDuplicateFocus(owner) {
  if(!owner || document.activeElement!==owner)return ()=>{};
  const projectId=state.project?.id,viewToken=state.projectViewToken,context=layerGroupDuplicateContext();
  let moved=false;
  const interacted=()=>{moved=true;};
  const focused=event=>{if(event.target!==owner && event.target!==document.body)moved=true;};
  document.addEventListener("pointerdown",interacted,true);document.addEventListener("keydown",interacted,true);
  document.addEventListener("focusin",focused,true);window.addEventListener("blur",interacted);
  return success=>requestAnimationFrame(()=>{
    document.removeEventListener?.("pointerdown",interacted,true);document.removeEventListener?.("keydown",interacted,true);
    document.removeEventListener?.("focusin",focused,true);window.removeEventListener?.("blur",interacted);
    if(!success || moved || state.project?.id!==projectId || state.projectViewToken!==viewToken || layerGroupDuplicateContext()!==context
      || owner.isConnected===false || owner.hidden || owner.disabled || owner.getClientRects && !owner.getClientRects().length
      || document.activeElement!==document.body)return;
    owner.focus({preventScroll:true});
  });
}

async function duplicateTimelineLayerGroup(ids, start=previewTimelineTime(), {focusOwner=null}={}) {
  const at=layerSplitTime(start),issue=layerGroupDuplicateIssue(ids,at);
  if(issue){toast(issue);return null;}
  const projectId=state.project.id,viewToken=state.projectViewToken,signature=JSON.stringify([...ids].sort()),primary=state.timeline?.mediaSelection,context=layerGroupDuplicateContext();
  const finishFocus=ownGroupDuplicateFocus(focusOwner);let result=null;
  pauseAllMedia();
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken
    && JSON.stringify([...selectedLayerGroupIds()].sort())===signature && state.timeline?.mediaSelection===primary && layerGroupDuplicateContext()===context;
  try {result=await applyManualEdit("layers_duplicate",{clip_ids:[...ids],start:at},{strictRevision:true,isCurrent:current,admissionCurrent:current});return result;}
  finally {finishFocus(Boolean(result && state.project?.id===projectId && state.project.revision===result.revision
    && selectedLayerGroupIds().length===ids.length && !selectedLayerGroupIds().some(id=>ids.includes(id))));}
}

function groupSplitIssue(own=null){return layerStructureIssue(own,"split");}
// Split and join share a revision-bound admission ticket and uncertain-result fence.
function layerStructureIssue(own,verb){
  const p=state.project,t=state.timeline,media=state.mediaStudio,gerund=verb==="join"?"joining":"splitting";
  const mine=own && state.groupSplitPending===own && own.project===p && own.view===state.projectViewToken;
  const fence=state.groupSplitFences.get(p?.id);if(fence?.view===state.projectViewToken)return fence.message;
  if(!p?.id||!t||!state.studio.open||t.project?.id!==p.id||t.project.revision!==p.revision)return "Open this saved edit in Studio first.";
  if(previewUsesSourceTime()||state.preview.playing||activeEditTarget()!=="edit")return "Pause Edited video and choose the whole-edit target to "+verb+" these layers.";
  if(document.querySelector("dialog[open]")||t.gesture||t.scrubbing||t.libraryDragActive||t.editPending||t.mediaSelectionPending||t.mediaSourceOpening||t.trackLockPending||
    state.sourceReview?.busy||media?.shotReview?.pending||media?.frameEditor?.active||state.embeddedEditor?.dragging||document.documentElement.classList.contains("numeric-scrubbing"))return "Finish the current dialog, selection or timeline gesture before "+gerund+".";
  if(rangeInputPending("timeline")||rangeInputPending("layout"))return "Apply or close the typed range before "+gerund+".";
  const unfinished=sourceMonitorIssue();if(unfinished)return unfinished;
  if(previewRepairBusy()||projectCopySourceBusy()||state.activeJob||state.activeUploads.size||state.jobStartLocks.size||media?.uploading||media?.placing||media?.importQueue?.running||state.stabilizationStudio?.uploading||state.chromaStudio?.saving||state.matchFramePending||(!mine&&(foregroundBusy()||state.manualEditBusy||state.manualEditPromise||state.groupSplitPending)))return "Wait for the current save, import or preparation.";
  if(!mine){const s=projectSaveStatus();if(s.kind!=="saved"||hasUnsavedProjectWork())return s.detail||"Finish pending changes before "+gerund+". Nothing will be implicitly saved.";}
  return "";
}

function groupSplitAvailability(ids,time){
  const issue=groupSplitIssue();if(issue)return {issue};
  return planGroupSplit(state.project,ids,groupSplitFrame(state.project,time));
}

function groupJoinAvailability(ids){const issue=layerStructureIssue(null,"join");return issue?{issue}:planGroupJoin(state.project,ids);}
function splitTimelineLayerGroup(ids,time=previewTimelineTime()){return saveSelectedStructure("split",ids,time);}
function joinTimelineLayerPair(ids){return saveSelectedStructure("join",ids);}
async function saveSelectedStructure(verb,ids,time){
  const joining=verb==="join",name=joining?"join":"group split";
  const plan=joining?groupJoinAvailability(ids):groupSplitAvailability(ids,time);if(plan.issue){toast(plan.issue);return null;}
  const project=state.project,view=state.projectViewToken,timeline=state.timeline,primary=timeline.mediaSelection;
  const selected=JSON.stringify([...ids].sort()),pane=layerGroupDuplicateContext(),cursor=timeline.playhead,before=structuredClone(project),raw=JSON.stringify(before);
  const sameView=()=>state.project?.id===project.id&&state.projectViewToken===view&&state.timeline===timeline;
  const ownsSelection=()=>sameView()&&!state.preview.playing&&!previewUsesSourceTime()&&activeEditTarget()==="edit"&&timeline.mediaSelection===primary&&JSON.stringify([...selectedLayerGroupIds()].sort())===selected&&layerGroupDuplicateContext()===pane&&(joining?timeline.playhead===cursor:groupSplitFrame(project,timeline.playhead)===plan.frame);
  if(!ownsSelection()||!ids.includes(primary))return null;
  const token={project,view};let resolve,submitted=false,result=null;const promise=new Promise(r=>{resolve=r;});
  state.groupSplitPending=token;state.manualEditBusy=true;state.manualEditPromise=promise;
  const fence=message=>{if(sameView()){state.groupSplitFences.set(project.id,{view,message});toast(message);}};
  try{
    renderReadiness();renderManualControls();timeline.cancelPendingCut?.();
    const issue=layerStructureIssue(token,verb);
    if(issue||!ownsSelection()||state.project!==project||JSON.stringify(project)!==raw){if(issue)toast(issue);return null;}
    submitted=true;
    const fields=joining?{action:"layers_join",clip_ids:[...ids]}:{action:"layers_split",clip_ids:[...ids],frame:plan.frame};
    const payload=await api(`/api/projects/${encodeURIComponent(project.id)}/manual/edit`,{method:"POST",
      body:JSON.stringify({...fields,expected_revision:before.revision})});
    const receipt=joining?verifyGroupJoin(before,payload?.project,ids):verifyGroupSplit(before,payload?.project,ids,plan.frame,payload?.created);
    if(receipt.issue)throw new Error(receipt.issue);
    result=payload.project;rememberProjectRevision(result);
    if(!sameView())return result;
    if(state.project!==project||JSON.stringify(project)!==raw||sourceMonitorIssue()){fence("The "+name+" was saved. Reopen this project to review it; newer work was left untouched.");return result;}
    const keep=ownsSelection();state.project=result;
    timeline.project=editorProject();
    if(keep && joining){
      // The returned left occurrence already owns the saved, combined clip. Set the
      // native selection without calling selection flows that flush, seek or reveal.
      const text=receipt.left.startsWith("text_");timeline.setMediaSelection([receipt.left],receipt.left);
      if(state.mediaStudio)state.mediaStudio.selected=text?null:receipt.left;
      if(state.textStudio)state.textStudio.selected=text?receipt.left:null;
      if(text)selectAdvancedTab("transcript");
      toast("Joined the matching clips. Other edits are unchanged. One Undo restores just this cut.");
    }else if(keep){timeline.setMediaSelection(receipt.ids,receipt.mapping[primary]);toast("Split "+ids.length+" selected clips. The right-hand pieces are selected. One Undo rejoins them.");}
    else if(joining && timeline.selectedMediaIds?.().includes(receipt.right)){
      // A newer selection wins, but it cannot keep an occurrence that no longer exists.
      const remaining=timeline.selectedMediaIds().filter(id=>id!==receipt.right);timeline.setMediaSelection(remaining,remaining.includes(timeline.mediaSelection)?timeline.mediaSelection:remaining.at(-1));
      if(state.mediaStudio?.selected===receipt.right)state.mediaStudio.selected=null;
      if(state.textStudio?.selected===receipt.right)state.textStudio.selected=null;
    }
    state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
    timeline.scheduleDraw?.();updateMediaPreview();renderManualControls();return result;
  }catch(error){
    if(submitted&&(!(Number(error?.status)>=400&&Number(error?.status)<500)||Number(error?.status)===409)){
      fence(result?"The "+name+" was saved, but its view could not refresh. Reopen this project before editing again.":"The "+name+" could not be confirmed. Reopen this project to check the saved edit; the request was not repeated.");
    }else if(sameView())toast(error?.message||(joining?"The clips could not be joined.":"The selected clips could not be split."));
    return result;
  }finally{
    if(state.groupSplitPending===token){state.groupSplitPending=null;state.manualEditBusy=false;}
    if(state.manualEditPromise===promise)state.manualEditPromise=null;
    resolve();renderReadiness();renderManualControls();renderProjectSaveState();
  }
}

function groupSelectionIssue() { return "Several clips are selected. Move, split, duplicate or remove them together, or select one clip before trimming."; }

function groupBlocksAction(action) {
  return selectedLayerGroupIds().length>1 && (/^(media_|text_|sequence_|track_)/.test(action)
    || ["layer_move","split","delete_range","restore_range","trim_clip","set_camera_layout"].includes(action));
}

async function selectTimelineLayers(ids, primary) {
  if(!Array.isArray(ids) || ids.length>200 || ids.some(id=>typeof id!=="string") || new Set(ids).size!==ids.length)return false;
  if(ids.length===1)return selectTimelineMedia(ids[0]);
  const request=beginInspectorSelection();
  pauseAllMedia();
  if(!await prepareInspectorSelection(request)){restoreInspectorSelection(request);return false;}
  if(ids.length>1){const plan=planLayerGroupRemove(state.project,ids);if(plan.issue){toast(plan.issue);return false;}}
  if(state.textStudio?.selected && await state.textStudio.select(null)===false)return false;
  if(!inspectorSelectionCurrent(request) || state.manualEditBusy || foregroundBusy())return false;
  closePrimarySourceReview();
  state.mediaStudio?.select(null);
  clearCaptionInspectorSelection();
  state.manualSelection=null;state.trimClip=null;state.markIn=null;
  state.timeline?.clearSelection();
  state.timeline?.setMediaSelection?.(ids,ids.includes(primary)?primary:ids.at(-1));
  renderManualControls();
  if(ids.length>1){selectAdvancedTab("media");state.layerGroupPanel?.scrollIntoView({block:"start",inline:"nearest"});}
  return true;
}

// Match only saved framing. Reference choice is local; no preview or save queue.
function matchFrameIssue(owner=null) {
  const project=state.project,media=state.mediaStudio,timeline=state.timeline;
  const own=Boolean(owner && state.matchFramePending===owner && owner.project===project && owner.viewToken===state.projectViewToken);
  const fence=state.matchFrameFences.get(project?.id);
  if(fence?.viewToken===state.projectViewToken)return fence.message;
  if(!project?.id || !Number.isInteger(project.revision) || project.revision<1 || !project.draft || !timeline || !state.studio.open)
    return "Open a saved edit in Studio before matching framing.";
  const unfinished=sourceMonitorIssue();if(unfinished)return unfinished;
  if(previewRepairBusy() || projectCopySourceBusy() || state.activeJob || state.activeUploads.size || state.jobStartLocks.size
    || media?.uploading || media?.placing || media?.importQueue?.running || state.stabilizationStudio?.uploading
    || state.chromaStudio?.saving || (!own && (state.manualEditBusy || state.manualEditPromise || state.matchFramePending)))
    return "Wait for the current save, import or processing before matching framing.";
  if(timeline.gesture || timeline.scrubbing || timeline.libraryDragActive || timeline.editPending || timeline.mediaSelectionPending
    || timeline.mediaSourceOpening || timeline.trackLockPending || state.sourceReview?.busy || state.sourceReview?.timeline?.gesture
    || state.sourceReview?.timeline?.scrubbing || media?.shotReview?.pending || media?.frameEditor?.active
    || media?.frameEditorState?.dragging || state.embeddedEditor?.dragging || document.documentElement?.classList?.contains?.("numeric-scrubbing"))
    return "Finish or cancel the current gesture or source placement before matching framing.";
  if(!own){const saved=projectSaveStatus();if(saved.kind!=="saved" || hasUnsavedProjectWork())return saved.detail || "Save or discard unfinished changes. Match framing never saves them implicitly.";}
  return "";
}

function matchFrameNotice(message,projectId,viewToken) {
  if(state.project?.id!==projectId || state.projectViewToken!==viewToken)return;
  if(state.layerGroupPanel)state.layerGroupPanel.groupFrameNotice={message,projectId,viewToken};
  toast(message);
}

function renderLayerGroupFrameControls(node,ids) {
  const project=state.project,control=node.querySelector('[data-group-frame-controls]');if(!control)return;
  const select=control.querySelector('[data-group-frame-reference]'),button=control.querySelector('[data-group-frame-apply]');
  const context=JSON.stringify([project?.id,state.projectViewToken,[...ids].sort()]);
  if(node.groupFrameContext!==context){
    node.groupFrameContext=context;node.groupFrameCache=null;node.groupFrameNotice=null;
    const rows=project?.manual?.media_clips;
    const choices=Array.isArray(rows)?rows.filter(row=>ids.includes(row?.id) && ['image','video'].includes(project?.assets?.[row.asset_id]?.kind)):[];
    node.groupFrameReference=choices.some(row=>row.id===state.timeline?.mediaSelection)?state.timeline.mediaSelection:choices[0]?.id || '';
  }
  const memo=node.groupFrameCache;
  if(!memo || memo.project!==project || memo.revision!==project?.revision || memo.manual!==project?.manual || memo.assets!==project?.assets
    || memo.reference!==node.groupFrameReference || memo.context!==context){
    const plan=planLayerGroupFrame(project,ids,node.groupFrameReference);
    node.groupFrameCache={project,revision:project?.revision,manual:project?.manual,assets:project?.assets,reference:node.groupFrameReference,context,plan};
    const tracks=project?.manual?.layer_tracks?.tracks, names=new Map((Array.isArray(tracks)?tracks:[]).map(track=>[track.id,track.name]));
    const rows=project?.manual?.media_clips,options=[];
    for(const row of Array.isArray(rows)?rows:[]){
      if(!ids.includes(row?.id) || !['image','video'].includes(project?.assets?.[row.asset_id]?.kind))continue;
      const option=document.createElement('option');option.value=row.id;
      option.textContent=`${project.assets[row.asset_id].name || 'Imported visual'} | ${formatTime(row.start,true)} | ${names.get(row.track_id) || 'Automatic track'} | #${options.length+1} (${row.id.slice(-6)})`;
      options.push(option);
    }
    select.replaceChildren(...options);select.value=node.groupFrameReference;
  }
  const plan=node.groupFrameCache.plan,readiness=matchFrameIssue(),issue=readiness || plan.issue;
  const changed=plan.changedIds?.length || 0,notice=node.groupFrameNotice;
  select.disabled=Boolean(readiness || !select.options.length);
  button.textContent=`Apply to ${Math.max(0,ids.length-1)} other clips`;
  button.disabled=Boolean(issue || !changed);button.title=issue || (changed ? 'Match saved position, size and Fill / Fit in one Undo. The reference stays unchanged.' : 'All targets already use this framing.');
  const frame=plan.frame,summary=control.querySelector('[data-group-frame-summary]');
  summary.textContent=frame?`Saved reference: X ${frame.x*100}%, Y ${frame.y*100}%, width ${frame.w*100}%, height ${frame.h*100}%; ${frame.fit==='contain'?'Fit':'Fill'}.`:'Select only imported image or video clips to match their saved framing.';
  const message=issue || (notice?.projectId===project?.id && notice.viewToken===state.projectViewToken?notice.message:'')
    || (changed?`${changed} of ${ids.length-1} targets will change. The reference, timing, motion, sound and tracks stay unchanged.`:'All targets already use this framing. Nothing will be saved.');
  const status=control.querySelector('[data-group-frame-status]');if(status.textContent!==message)status.textContent=message;
}

function ownMatchFrameFocus(owner,current) {
  if(!owner || document.activeElement!==owner)return ()=>{};
  let moved=false;
  const cancel=()=>{moved=true;},focus=event=>{if(event.target!==owner && event.target!==document.body)moved=true;};
  for(const type of ['pointerdown','keydown','wheel'])document.addEventListener(type,cancel,true);
  document.addEventListener('focusin',focus,true);window.addEventListener('blur',cancel);
  return restore=>requestAnimationFrame(()=>{
    for(const type of ['pointerdown','keydown','wheel'])document.removeEventListener(type,cancel,true);
    document.removeEventListener('focusin',focus,true);window.removeEventListener('blur',cancel);
    if(!restore || moved || !current() || document.activeElement!==document.body)return;
    let target=owner.disabled?state.layerGroupPanel?.querySelector('[data-group-frame-reference]'):owner;
    // An unconfirmed result fences both edit controls. Keep keyboard users at
    // this existing disclosure instead of returning them to the page root.
    if(target?.disabled)target=state.layerGroupPanel?.querySelector('[data-group-frame-controls] > summary');
    if(target && target.isConnected!==false && !target.hidden && !target.disabled && (!target.getClientRects || target.getClientRects().length))target.focus({preventScroll:true});
  });
}

async function matchTimelineLayerGroup(ids,referenceId,{focusOwner=null}={}) {
  const issue=matchFrameIssue();if(issue){toast(issue);return null;}
  const project=state.project,viewToken=state.projectViewToken,plan=planLayerGroupFrame(project,ids,referenceId);
  if(plan.issue){toast(plan.issue);return null;}
  if(!plan.changedIds.length)return project;
  const projectId=project.id,before=structuredClone(project),raw=JSON.stringify(before),intent={clip_ids:[...ids],reference_id:referenceId};
  const signature=JSON.stringify([...ids].sort()),primary=state.timeline?.mediaSelection,context=layerGroupDuplicateContext(),panel=state.layerGroupPanel;
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken
    && JSON.stringify([...selectedLayerGroupIds()].sort())===signature && state.timeline?.mediaSelection===primary
    && layerGroupDuplicateContext()===context && (!panel || state.layerGroupPanel===panel && panel.groupFrameReference===referenceId);
  if(!current())return null;
  let submitted=false,confirmed=false,result=null;
  const focusCurrent=()=>current() && !sourceMonitorIssue() && (state.project===project?JSON.stringify(state.project)===raw:confirmed && state.project===result);
  const finishFocus=ownMatchFrameFocus(focusOwner,focusCurrent),token={project,viewToken};
  let finish;const promise=new Promise(resolve=>{finish=resolve;});
  state.matchFramePending=token;state.manualEditBusy=true;state.manualEditPromise=promise;
  try {
    pauseAllMedia();updateMediaPreview();renderReadiness();renderManualControls();
    const finalIssue=matchFrameIssue(token),fresh=planLayerGroupFrame(state.project,ids,referenceId);
    if(finalIssue || !current() || state.project!==project || JSON.stringify(state.project)!==raw || JSON.stringify(fresh)!==JSON.stringify(plan)){
      if(finalIssue)toast(finalIssue);return null;
    }
    state.timeline?.cancelPendingCut?.();
    // Cancelling an armed cut notifies tool state synchronously. It cannot grant
    // permission to submit a different selection or newly unfinished edit.
    const commitIssue=matchFrameIssue(token);
    if(commitIssue || !current() || state.project!==project || JSON.stringify(state.project)!==raw){if(commitIssue)toast(commitIssue);return null;}
    submitted=true;
    const payload=await api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`,{
      method:'POST',body:JSON.stringify({action:'layers_match_frame',...intent,expected_revision:before.revision}),
    });
    const receipt=verifyLayerGroupFrame(before,payload?.project,intent.clip_ids,intent.reference_id);
    if(receipt.issue)throw new Error(`The framing result could not be verified. ${receipt.issue}`);
    confirmed=true;result=payload.project;rememberProjectRevision(result);
    if(state.project===project && state.projectViewToken===viewToken && JSON.stringify(state.project)===raw && !sourceMonitorIssue()){
      state.project=result;
      // No selection, reveal, seek or full draft rebuild: only saved geometry changed.
      state.mediaStudio?.render();state.chromaStudio?.render();
      if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
      updateMediaPreview();renderManualControls();
      if(current() && panel)panel.groupFrameNotice={projectId,viewToken,message:`Framing matched on ${plan.changedIds.length} clips. One Undo restores every target.`};
    } else if(state.project?.id===projectId && state.projectViewToken===viewToken){
      const message='Framing was saved. Reopen this project to review it; newer local work was left untouched.';
      state.matchFrameFences.set(projectId,{viewToken,message});matchFrameNotice(message,projectId,viewToken);
    }
    return result;
  } catch(error) {
    const rejected=Number(error?.status)>=400 && Number(error?.status)<500;
    if(confirmed || submitted && (!rejected || Number(error?.status)===409)){
      const message=confirmed?'Framing was saved, but its view could not refresh. Reopen this project before matching again.'
        : rejected?'The project changed or is busy. Reopen it to review the saved framing; nothing was repeated.'
        :'The framing result is unconfirmed. Reopen this project to inspect the saved edit before matching again; the request was not repeated.';
      state.matchFrameFences.set(projectId,{viewToken,message});matchFrameNotice(message,projectId,viewToken);
    } else if(state.project?.id===projectId && state.projectViewToken===viewToken)toast(error?.message || 'Framing could not be matched.');
    return confirmed?result:null;
  } finally {
    if(state.matchFramePending===token){state.matchFramePending=null;state.manualEditBusy=false;}
    if(state.manualEditPromise===promise)state.manualEditPromise=null;
    finish();renderReadiness();renderManualControls();renderProjectSaveState();finishFocus(true);
  }
}

function initializeLayerGroupControls(panel) {
  const node=document.createElement("section");node.className="layer-group-controls";node.hidden=true;
  node.setAttribute("aria-labelledby","layerGroupTitle");
  node.innerHTML='<h4 id="layerGroupTitle">Selected clips</h4><p id="layerGroupRange"></p><div class="layer-group-actions"><button type="button" data-group-move="playhead">Move selection to playhead</button><button type="button" data-group-move="-1" aria-label="Move selected clips one frame earlier">−1 frame</button><button type="button" data-group-move="1" aria-label="Move selected clips one frame later">+1 frame</button><button type="button" data-group-split="playhead" aria-describedby="layerGroupSplitHint">Split at playhead</button><button type="button" data-group-duplicate aria-describedby="layerGroupDuplicateHelp">Duplicate at playhead</button><button type="button" data-group-remove aria-describedby="layerGroupRemoveHelp">Remove selected clips</button><button type="button" data-group-clear>Clear selection</button></div><p id="layerGroupSplitHint" data-group-split-hint></p><div data-group-join-tools hidden><button type="button" data-group-join aria-describedby="layerGroupJoinHint">Join matching clips</button><p id="layerGroupJoinHint" data-group-join-hint></p></div><div class="layer-group-track-controls" data-group-track-controls data-editor-shortcuts="off"><label><span data-group-track-label>Anchor destination track</span><select data-group-track aria-label="Primary selected clip destination track"></select></label><button type="button" data-group-relocate aria-describedby="layerGroupTrackStatus">Move group to track</button><p id="layerGroupTrackStatus" data-group-track-status role="status" aria-live="polite"></p></div><details class="layer-group-frame-controls" data-group-frame-controls data-editor-shortcuts="off"><summary>Match framing</summary><label>Use framing from<select data-group-frame-reference aria-label="Saved framing reference"></select></label><p data-group-frame-summary></p><button type="button" data-group-frame-apply aria-describedby="layerGroupFrameHelp">Apply framing</button><p data-group-frame-status role="status" aria-live="polite"></p><small id="layerGroupFrameHelp">Copy only saved position, size and Fill / Fit. The reference stays unchanged. Every target must be unlocked; a locked reference can be read. Timing, motion, sound, tracks and original files stay unchanged.</small></details><p id="layerGroupStatus" role="status" aria-live="polite"></p><small id="layerGroupDuplicateHelp">Duplicate places the earliest selected clip at the playhead and keeps all relative timing. Copies use automatic unlocked tracks; the whole group must fit. Originals and edit duration stay unchanged. One Undo removes all copies.</small><small id="layerGroupRemoveHelp">Move or remove whole selected occurrences without ripple. Other clips, edit duration and original files stay unchanged; one Undo restores all removed clips. Ctrl/Cmd-click or use Timeline Index checkboxes to change this temporary selection. Source A/B and automatic captions are separate.</small>';
  node.addEventListener("click",event=>{const button=event.target.closest("button");if(!button || button.disabled)return;
    if(button.hasAttribute("data-group-frame-apply")){void matchTimelineLayerGroup(selectedLayerGroupIds(),node.groupFrameReference,{focusOwner:event.detail===0?button:null});return;}
    if(button.hasAttribute("data-group-relocate")){void relocateTimelineLayerGroup(selectedLayerGroupIds(),state.timeline?.mediaSelection,0,node.groupTrackChoice,{focusOwner:button});return;}
    if(button.hasAttribute("data-group-clear")){void selectTimelineLayers([],null);return;}
    if(button.hasAttribute("data-group-remove")){void removeTimelineLayerGroup(selectedLayerGroupIds(),{focusOwner:button});return;}
    if(button.hasAttribute("data-group-split")){void splitTimelineLayerGroup(selectedLayerGroupIds());return;}
    if(button.hasAttribute("data-group-join")){void joinTimelineLayerPair(selectedLayerGroupIds());return;}
    if(button.hasAttribute("data-group-duplicate")){void duplicateTimelineLayerGroup(selectedLayerGroupIds(),undefined,{focusOwner:button});return;}
    if(button.dataset.groupMove){const ids=selectedLayerGroupIds(),delta=layerGroupMoveDelta(button.dataset.groupMove);void moveTimelineLayerGroup(ids,delta);}
  });
  node.querySelector("[data-group-track]").addEventListener("change",event=>{node.groupTrackChoice=event.target.value;renderLayerGroupTrackControls(node,selectedLayerGroupIds());});
  node.querySelector("[data-group-frame-reference]").addEventListener("change",event=>{node.groupFrameReference=event.target.value;node.groupFrameCache=null;node.groupFrameNotice=null;renderLayerGroupFrameControls(node,selectedLayerGroupIds());});
  panel.prepend(node);state.layerGroupPanel=node;
}

function layerGroupMoveDelta(kind,time) {
  const ids=selectedLayerGroupIds(),rows=[...(state.project?.manual?.media_clips||[]),...(state.project?.manual?.text_clips||[])].filter(row=>ids.includes(row.id));
  if(rows.length!==ids.length || ids.length<2)return NaN;
  const start=Math.min(...rows.map(row=>row.start));
  if(kind==="playhead")return layerSplitTime(Number.isFinite(time)?time:previewTimelineTime())-start;
  if(kind==="-1" || kind==="1")return Number(kind)/(Number(state.project?.settings?.fps)||30);
  return NaN;
}

function renderLayerGroupRemoveAvailability(ids=selectedLayerGroupIds()) {
  const button=elements.manualDelete;if(!button || ids.length<2)return;
  const issue=layerGroupRemoveIssue(ids);
  button.disabled=Boolean(issue || state.timeline?.editPending);
  button.textContent=`Remove ${ids.length} selected clips`;
  button.title=issue || (state.timeline?.editPending ? "Wait for the current timeline edit." : "Remove selected occurrences without ripple. Other clips, edit duration and original files stay unchanged; one Undo restores all.");
  button.setAttribute("aria-describedby","layerGroupRemoveHelp");
}

function renderLayerGroupControls(time) {
  renderLayerGroupRemoveAvailability();
  if(selectedLayerGroupIds().length)renderDuplicateAvailability(time);
  const node=state.layerGroupPanel;if(!node)return;
  const ids=selectedLayerGroupIds();node.hidden=ids.length<2;if(node.hidden){node.groupSignature=null;node.groupTrackContext=null;node.groupFrameContext=null;node.groupFrameCache=null;return;}
  renderLayerGroupTrackControls(node,ids);
  renderLayerGroupFrameControls(node,ids);
  if(!Number.isFinite(time))time=Number(state.timeline?.playhead)||0;
  const rows=[...(state.project?.manual?.media_clips||[]),...(state.project?.manual?.text_clips||[])].filter(row=>ids.includes(row.id));
  node.querySelector("#layerGroupTitle").textContent=`${ids.length} clips selected`;
  node.querySelector("#layerGroupRange").textContent=rows.length===ids.length?`${formatTime(Math.min(...rows.map(row=>row.start)),true)} – ${formatTime(Math.max(...rows.map(row=>row.end)),true)}`:"Selection changed. Select the clips again.";
  const busy=foregroundBusy() || state.transcriptSaving || state.timeline?.mediaSelectionPending || state.timeline?.editPending;
  const issue=layerGroupMovePlan(ids,0).issue;
  for(const button of node.querySelectorAll("[data-group-move]")){
    const plan=layerGroupMovePlan(ids,layerGroupMoveDelta(button.dataset.groupMove,time));
    button.disabled=Boolean(busy || plan.issue || !plan.patches?.length);
    button.title=busy?"Wait for the current selection or save.":plan.issue || (!plan.patches?.length?"The selection is already here.":"Move all selected clips by the same time shift, without ripple or changing their source content.");
  }
  const split=node.querySelector("[data-group-split]"),hint=node.querySelector("[data-group-split-hint]");
  if(split && hint){const plan=groupSplitAvailability(ids,time);split.disabled=!!plan.issue;split.textContent=`Split ${ids.length} clips at playhead`;
    const message=plan.issue || `Split every selected clip on frame ${plan.frame}. Other layers stay intact. One Undo rejoins all pieces.`;split.title=message;if(hint.textContent!==message)hint.textContent=message;}
  const pair=node.querySelector("[data-group-join-tools]");if(pair){pair.hidden=ids.length!==2;if(!pair.hidden){
    const plan=groupJoinAvailability(ids),button=pair.querySelector("[data-group-join]"),hint=pair.querySelector("[data-group-join-hint]");
    const message=plan.issue||`Remove the cut at frame ${plan.frame}. The left clip continues through the right; other edits and the playhead stay in place.`;
    button.disabled=!!plan.issue;button.title=message;if(hint.textContent!==message)hint.textContent=message;}}
  const remove=node.querySelector("[data-group-remove]"),removeIssue=layerGroupRemoveIssue(ids);
  remove.textContent=`Remove ${ids.length} selected clips`;
  remove.disabled=Boolean(busy || removeIssue);
  remove.title=removeIssue || "Remove only these occurrences, without ripple. Edit duration, other clips and original files stay unchanged. One Undo restores all.";
  const duplicate=node.querySelector("[data-group-duplicate]"),copyIssue=layerGroupDuplicateIssue(ids,time);
  duplicate.textContent=`Duplicate ${ids.length} clips at playhead`;
  duplicate.disabled=Boolean(copyIssue);
  duplicate.title=copyIssue || "Copy the whole arrangement at the playhead, preserving relative timing. Automatic unlocked tracks; no ripple or duration change. One Undo removes all copies.";
  node.querySelector("[data-group-clear]").disabled=Boolean(busy);
  const status=node.querySelector("#layerGroupStatus"),message=busy?"Saving or selecting…":explicitPendingDraft()?.detail || ((!issue || !removeIssue || !copyIssue) ? "Move, split, duplicate or remove this selection. Copying reads locked originals and uses unlocked tracks; other edits respect protection." : issue || removeIssue || copyIssue);
  if(status.textContent!==message)status.textContent=message;
}

function moveTimelineLayerGroup(ids,delta) {
  if(!Array.isArray(ids)){toast("Select the clips again before moving them together.");return null;}
  const projectId=state.project?.id,viewToken=state.projectViewToken,signature=JSON.stringify([...ids].sort());
  return applyManualEdit("layers_move",{clip_ids:[...ids],delta},{isCurrent:()=>state.project?.id===projectId && state.projectViewToken===viewToken && JSON.stringify([...selectedLayerGroupIds()].sort())===signature});
}

async function removeTimelineLayerGroup(ids, {focusOwner=null} = {}) {
  const issue=layerGroupRemoveIssue(ids);
  if(issue){toast(issue);return null;}
  const projectId=state.project?.id,viewToken=state.projectViewToken,signature=JSON.stringify([...ids].sort());
  const ownedFocus=Boolean(focusOwner && document.activeElement===focusOwner);
  const result=await applyManualEdit("layers_remove",{clip_ids:[...ids]},{isCurrent:()=>state.project?.id===projectId
    && state.projectViewToken===viewToken && JSON.stringify([...selectedLayerGroupIds()].sort())===signature});
  if(result && ownedFocus && state.project?.id===projectId && state.projectViewToken===viewToken
    && state.project.revision===result.revision && state.layerGroupPanel?.hidden
    && (document.activeElement===focusOwner || document.activeElement===document.body))elements.timelineCanvas?.focus({preventScroll:true});
  return result;
}

function layerMovePlan(clipId, start) {
  const protection=layerEditProtectionIssue(String(clipId).startsWith("text_")?"text_move":"media_move",{clip_id:clipId,start});if(protection)return {issue:protection,patch:null};
  const blocked = issue => ({issue, patch:null}), project = state.project;
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before moving a clip.");
  const text = String(clipId).startsWith("text_"), rows = project?.manual?.[text ? "text_clips" : "media_clips"] || [];
  const clip = rows.find(row=>row.id===clipId), duration = Number(project?.editor_sequence?.duration ?? project?.draft?.output_duration);
  if (!project?.draft || !clip) return blocked("The selected media/text clip is no longer available. Select it again before moving.");
  if (!Number.isFinite(start) || start < 0) return blocked("Move the whole clip inside the edited timeline. Its length and source content will not be changed.");
  const precision = text ? 1e6 : 1e9, length = Number(clip.end)-Number(clip.start);
  start = Math.round(start*precision)/precision;
  const end = Math.round((start+length)*precision)/precision;
  if (!Number.isFinite(length) || !Number.isFinite(end) || !Number.isFinite(duration) || length < .08-1e-9 || end > duration+1e-9)
    return blocked("Move the whole clip inside the edited timeline. Its length and source content will not be changed.");
  if (text) {
    const events = [...rows.filter(row=>row.id!==clipId).flatMap(row=>[[row.start,1],[row.end,-1]]),[start,1],[end,-1]].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    let count=0;
    for (const [,change] of events) if ((count+=change)>16) return blocked("At most 16 custom text clips may overlap, including disabled clips. Choose another position.");
  } else {
    const asset=project.assets?.[clip.asset_id];
    if (!asset || asset.status!=="ready") return blocked("The selected media is not ready. Prepare it before moving.");
  }
  const collision=layerTrackPatchIssue(clipId,{start,end});if(collision)return blocked(collision);
  return {issue:"", patch:Math.abs(start-clip.start)<=1e-9 ? {} : {start,end}};
}

function moveTimelineLayer(clipId, start) {
  return applyManualEdit(String(clipId).startsWith("text_") ? "text_move" : "media_move", {clip_id:clipId,start});
}

function layerDuplicatePlan(clipId, start) {
  const blocked = issue => ({issue, patch:null});
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before duplicating a clip.");
  const project = state.project, text = String(clipId).startsWith("text_"), rows = project?.manual?.[text ? "text_clips" : "media_clips"] || [];
  const clip = rows.find(row => row.id === clipId), duration = Number(project?.editor_sequence?.duration ?? project?.draft?.output_duration);
  if (!project?.draft || !clip) return blocked("The selected media/text clip is no longer available. Select it again before duplicating.");
  start = layerSplitTime(start);
  const length = Number(clip.end) - Number(clip.start), end = Math.round((start + length) * (text ? 1e6 : 1e9)) / (text ? 1e6 : 1e9);
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(length) || !Number.isFinite(duration) || start < 0 || end > duration + 1e-9 || length < .08 - 1e-9) return blocked("The whole copy must fit inside the edited timeline. Move the playhead earlier; the clip will not be shortened or the edit extended.");
  if (rows.length >= (text ? 2000 : 200)) return blocked(`Duplicating would exceed the ${text ? "2000 text" : "200 media"} clip limit.`);
  if (text) {
    const events = [...rows.flatMap(row => [[row.start,1],[row.end,-1]]),[start,1],[end,-1]].sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
    let count = 0;
    for (const [,change] of events) if ((count += change) > 16) return blocked("At most 16 custom text clips may overlap, including disabled clips. Choose another copy destination.");
  } else {
    const asset = project.assets?.[clip.asset_id];
    if (!asset || asset.status !== "ready") return blocked("The selected media is not ready. Prepare it before duplicating.");
  }
  return {issue:"", patch:{start,end}};
}

function duplicateTimelineLayer(clipId, start = previewTimelineTime()) {
  return applyManualEdit(String(clipId).startsWith("text_") ? "text_duplicate" : "media_duplicate", {clip_id:clipId, start:layerSplitTime(start)});
}

function duplicateTimelineSelection(start = previewTimelineTime(), {focusOwner=null}={}) {
  if(selectedLayerGroupIds().length)return duplicateTimelineLayerGroup(selectedLayerGroupIds(),start,{focusOwner});
  if (state.timeline?.captionSelection) { toast("Automatic captions follow speech. Duplicate a custom title/caption or imported media instead."); return null; }
  const id = state.timeline?.mediaSelection;
  if (!id) return null;
  if (![...(state.project?.manual?.media_clips || []), ...(state.project?.manual?.text_clips || [])].some(row=>row.id===id)) {
    state.timeline.mediaSelection = null; state.timeline.clearSelection(); toast("The selected clip is no longer available. Select it again before duplicating."); return null;
  }
  return duplicateTimelineLayer(id,start);
}

function renderDuplicateAvailability(time) {
  const button = elements.clipDuplicate; if (!button) return;
  if(selectedLayerGroupIds().length){
    const ids=selectedLayerGroupIds();
    if(!Number.isFinite(time))time=Number.isFinite(state.timeline?.playhead)?state.timeline.playhead:Number(state.preview.editCursor)||0;
    const issue=layerGroupDuplicateIssue(ids,time);
    button.textContent=`Duplicate ${ids.length} clips at playhead`;button.disabled=Boolean(issue);
    button.title=issue || "Copy the whole selection at the playhead with its relative timing. Automatic unlocked tracks; no ripple, shortening or duration change. One Undo removes all copies.";
    button.setAttribute("aria-describedby","layerGroupDuplicateHelp");return;
  }
  button.removeAttribute("aria-describedby");
  const layer = state.timeline?.mediaSelection, caption = state.timeline?.captionSelection;
  if (!layer && !caption) { button.textContent = "Duplicate clip"; button.title = "Duplicate source footage in the selected A/B scope."; return; }
  if (!Number.isFinite(time)) time = Number.isFinite(state.timeline?.playhead) ? state.timeline.playhead
    : state.preview.editCursorProject === state.project?.id ? Number(state.preview.editCursor) || 0 : 0;
  const plan = caption ? {issue:"Automatic captions follow speech. Duplicate custom text or imported media instead."} : layerDuplicatePlan(layer,time);
  button.textContent = "Duplicate at playhead";
  button.disabled = !state.project?.draft || foregroundBusy() || state.manualEditBusy || state.transcriptSaving || Boolean(plan.issue);
  button.title = plan.issue || `Copy the whole selected occurrence at ${formatTime(plan.patch.start,true)}. Other layers and edit duration stay fixed; the new copy is selected. One Undo removes only the copy.`;
}

function trackLiftSnapshot(own=false) {
  const p=state.project,t=state.timeline,media=state.mediaStudio;
  let issue="";
  if(!state.studio.open||!p?.draft||!t||t.project?.id!==p.id||t.project.revision!==p.revision||!p.editor_sequence||p.editor_sequence.error)
    issue="Open a saved edit with named visual tracks first.";
  else if(document.getElementById("studioPanelTimeline")?.hidden||document.getElementById("editClipTools")?.hidden||document.getElementById("studioInspector")?.dataset.workbenchPane==="ai")
    issue="Return to Edit > Clip to lift the reviewed timeline range.";
  else if(previewUsesSourceTime()||state.preview.playing||activeEditTarget()!=="edit")issue="Pause Edited video and select the whole edit, not a source A/B track.";
  else if(rangeInputPending("timeline"))
    issue="Press Select range to apply the typed In and Out, or close the range editor to use the previous marks.";
  else if(selectedLayerGroupIds().length>1||t.gesture||t.scrubbing||t.editPending||t.mediaSelectionPending||t.mediaSourceOpening||t.libraryDragActive
    ||media?.frameEditor?.active||state.embeddedEditor?.dragging||document.querySelector("dialog[open]"))issue="Finish the current multi-selection, gesture or dialog first.";
  else if(state.transcriptSaving||state.chromaStudio?.saving||projectCopySourceBusy()||previewRepairBusy()||state.activeJob
    ||state.activeUploads.size||state.jobStartLocks.size||media?.importQueue?.running||media?.placing)issue="Wait for the current save, import or processing before lifting.";
  else if(sourceMonitorIssue()||(!own&&(foregroundBusy()||projectSaveStatus().kind!=="saved"||hasUnsavedProjectWork())))issue="Save or discard unfinished changes before lifting this range.";
  return {project:p,view:state.projectViewToken,range:state.manualSelection,issue};
}
async function commitTrackLift(owner,detail,owns){
  const current=(own=false)=>{const s=trackLiftSnapshot(own);return owns()&&!s.issue&&s.project?.id===owner.id&&s.project.revision===owner.revision
    &&s.view===owner.view&&s.range?.start===owner.range.start&&s.range?.end===owner.range.end&&detail.track_id===owner.track;};
  if(!current()||planTrackLift(state.project,detail).issue)return null;
  return applyManualEdit("media_track_lift",detail,{strictRevision:true,isCurrent:()=>current(true),admissionCurrent:()=>current(true)});
}
function rollingSnapshot(own=false) {
  const project=state.project, tl=state.timeline, media=state.mediaStudio, view=state.projectViewToken;
  const selected=tl?.mediaSelection===media?.selected && !selectedLayerGroupIds().length ? media?.selected : null;
  let issue="";
  if(!state.studio.open || !project?.draft || !tl || tl.project?.id!==project.id || tl.project.revision!==project.revision || !selected)
    issue="Select one imported clip on the saved timeline.";
  else if(previewUsesSourceTime() || state.preview.playing)issue="Pause Edited video before changing this clip.";
  else if(tl.gesture || tl.scrubbing || tl.editPending || tl.mediaSelectionPending || tl.mediaSourceOpening || tl.libraryDragActive
    || media?.frameEditor?.active || state.embeddedEditor?.dragging || document.querySelector("dialog[open]"))issue="Finish the current gesture or dialog before changing this clip.";
  else if(state.transcriptSaving || state.chromaStudio?.saving || projectCopySourceBusy() || previewRepairBusy() || state.activeJob
    || state.activeUploads.size || state.jobStartLocks.size || media?.importQueue?.running || media?.placing)issue="Wait for the active save, import or processing to finish.";
  else if((!own && (foregroundBusy() || projectSaveStatus().kind!=="saved" || hasUnsavedProjectWork())) || sourceMonitorIssue())
    issue="Save or discard unfinished changes before changing this clip.";
  return {project,view,selected,time:tl?.playhead,issue};
}
function clipOpacitySnapshot(own=false){
  const s=rollingSnapshot(own);
  if(!s.issue&&(document.getElementById("studioPanelMedia")?.hidden||document.getElementById("studioInspector")?.dataset.workbenchPane==="ai"))
    s.issue="Return to the selected occurrence in Media to compare or apply opacity.";
  return s;
}
async function commitClipOpacity(owner,detail,owns){
  const current=(own=false)=>{const s=clipOpacitySnapshot(own);return owns()&&!s.issue&&s.project?.id===owner.id&&s.project.revision===owner.revision&&s.selected===owner.selected&&s.view===owner.view;};
  if(!current()||detail.clip_id!==owner.selected)return null;
  const plan=planClipOpacity(state.project,owner.selected,detail.opacity_percent);if(plan.issue)return null;if(plan.noop)return state.project;
  return applyManualEdit("media_set_opacity",detail,{strictRevision:true,isCurrent:()=>current(true),admissionCurrent:()=>current(true)});
}
async function commitTakeReplacement(owner,detail) {
  const current=(own=false)=>{const s=rollingSnapshot(own);return !s.issue && s.project?.id===owner.id && s.view===owner.view
    && s.project.revision===owner.revision && s.selected===owner.selected;};
  if(!current() || planTake(state.project,takeContext(state.project,owner.selected),detail).issue)return false;
  return applyManualEdit("media_replace_take",detail,{strictRevision:true,isCurrent:()=>current(true),admissionCurrent:()=>current(true)});
}
async function commitRollingCut(owner,detail,mode) {
  const current=(own=false)=>{const s=rollingSnapshot(own);return !s.issue && s.project?.id===owner.id && s.view===owner.view
    && s.project.revision===owner.revision && s.selected===owner.selected
    && (mode!=="playhead" || Math.round(s.time*(s.project.settings?.fps??30))===detail.frame);};
  if(!current())return false;
  const pair=rollPair(state.project,owner.selected,owner.edge),plan=planRoll(pair,detail.frame);
  if(plan.issue || plan.detail.left_id!==detail.left_id || plan.detail.clip_id!==detail.clip_id || plan.detail.right_id!==detail.right_id)return false;
  return applyManualEdit(owner.edge==="slide"?"media_slide":"media_roll",detail,{strictRevision:true,isCurrent:()=>current(true),admissionCurrent:()=>current(true)});
}

function layerSlipPlan(clipId, sourceStart) {
  const protection=layerEditProtectionIssue("media_slip",{clip_id:clipId,source_start:sourceStart});if(protection)return {issue:protection,patch:null};
  const blocked = issue => ({issue, patch:null}), project = state.project;
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before slipping media.");
  const clip = project?.manual?.media_clips?.find(row => row.id === clipId), asset = project?.assets?.[clip?.asset_id];
  if (!project?.draft || !clip) return blocked("Slip supports imported video/audio occurrences only. Select one from the media timeline.");
  if (!asset || asset.status !== "ready") return blocked("The selected media is not ready. Prepare it before slipping.");
  if (!["video", "audio"].includes(asset.kind)) return blocked("Slip changes source content inside imported video or audio, not still images or text.");
  if (!Number.isFinite(sourceStart) || sourceStart < 0) return blocked("Choose a finite Source in at or after the beginning of the source.");
  sourceStart = Math.round(sourceStart * 1e9) / 1e9;
  const delta = sourceStart - Number(clip.source_start || 0), length = clip.end - clip.start;
  if (Math.abs(delta) <= 1e-9) return {issue:"", patch:{}};
  if (sourceStart > 4 * 3600 || sourceStart + length > Number(asset.duration) + 1e-8) return blocked("The complete occurrence must fit inside the available source footage. Its timeline duration will not be shortened.");
  const patch = {source_start:sourceStart};
  if (asset.kind === "video") {
    const pictureStart = Math.round((Number(clip.video_source_start ?? clip.source_start ?? 0) + delta * Number(clip.speed || 1)) * 1e9) / 1e9;
    if (pictureStart < 0) return blocked("No earlier picture frames are available here. The independent picture clock cannot be clamped.");
    if (pictureStart > 4 * 3600 * 4) return blocked("The independent picture clock exceeds the supported source-time limit.");
    patch.video_source_start = pictureStart;
  }
  return {issue:"", patch};
}

function slipTimelineLayer(clipId, sourceStart) {
  return applyManualEdit("media_slip", {clip_id:clipId, source_start:sourceStart});
}

function layerTrimPlan(clipId, edge, time) {
  const protection=layerEditProtectionIssue(String(clipId).startsWith("text_")?"text_trim":"media_trim",{clip_id:clipId,edge,time});if(protection)return {issue:protection,patch:null};
  const blocked = issue => ({ issue, patch: null });
  if (state.captionDirty || state.captionContextSave) return blocked("Save or discard the caption text before trimming a clip.");
  if (!["start", "end"].includes(edge)) return blocked("Choose the start or end edge.");
  const project = state.project, text = String(clipId).startsWith("text_"), rows = project?.manual?.[text ? "text_clips" : "media_clips"] || [];
  const clip = rows.find(row => row.id === clipId), duration = Number(project?.editor_sequence?.duration ?? project?.draft?.output_duration);
  if (!project?.draft || !clip) return blocked("The selected clip is no longer available. Select it again before trimming.");
  time = layerSplitTime(time);
  if (!Number.isFinite(time) || !Number.isFinite(duration) || time < 0 || time > duration + 1e-9) return blocked("Choose a trim point inside the edited timeline.");
  const delta = time - clip[edge], start = edge === "start" ? time : clip.start, end = edge === "end" ? time : clip.end;
  if (Math.abs(delta) <= 1e-9) return { issue: "", patch: {} };
  if (end - start < .08 - 1e-9) return blocked("Keep at least 0.08 seconds in the selected clip.");
  const patch = { [edge]: time };
  const collision=layerTrackPatchIssue(clipId,{start,end});if(collision)return blocked(collision);
  if (text) {
    const events = rows.flatMap(row => [[row.id === clipId ? start : row.start, 1], [row.id === clipId ? end : row.end, -1]])
      .sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let count = 0;
    for (const [, change] of events) if ((count += change) > 16) return blocked("At most 16 custom text clips may overlap, including disabled clips. Choose a different edge.");
    return { issue: "", patch };
  }
  const asset = project.assets?.[clip.asset_id];
  if (!asset || asset.status !== "ready") return blocked("The selected media is not ready. Prepare it before trimming.");
  if (asset.kind !== "audio" && (clip.motion || "none") !== "none") return blocked("Trimming this pan/zoom clip would change its motion phase. Turn off motion or keep its edges intact.");
  const fadeIn = Number(clip.fade_in || 0), fadeOut = Number(clip.fade_out || 0), shortening = edge === "start" ? delta > 0 : delta < 0;
  const fade = edge === "start" ? "fade_in" : "fade_out";
  if (shortening) {
    if (time - clip.start < fadeIn - 1e-9 || clip.end - time < fadeOut - 1e-9) return blocked("The trim point is inside a media audio fade. Choose a point outside the fade.");
    patch[fade] = 0;
  } else if (Number(clip[fade] || 0) > 1e-9) return blocked("Extending this faded edge would move its original audio envelope. Remove that edge's fade first or keep the edge intact.");
  if (asset.kind !== "image") {
    const sourceStart = Math.round((Number(clip.source_start || 0) + (edge === "start" ? delta : 0)) * 1e9) / 1e9;
    if (sourceStart < 0) return blocked("No earlier source footage is available at this trim point.");
    if (sourceStart + end - start > Number(asset.duration) + 1e-8) return blocked("The trim point exceeds the available source footage.");
    if (edge === "start") patch.source_start = Math.round(sourceStart * 1e9) / 1e9;
    if (asset.kind === "video" && edge === "start") {
      const pictureStart = Math.round((Number(clip.video_source_start ?? clip.source_start ?? 0) + delta * Number(clip.speed || 1)) * 1e9) / 1e9;
      if (pictureStart < 0) return blocked("No earlier picture frames are available here. The independent picture clock cannot be clamped.");
      if (pictureStart > 4 * 3600 * 4) return blocked("The independent picture clock exceeds the supported source-time limit.");
      patch.video_source_start = pictureStart;
    }
  }
  return { issue: "", patch };
}

function trimTimelineLayer(clipId, edge, time = previewTimelineTime()) {
  return applyManualEdit(String(clipId).startsWith("text_") ? "text_trim" : "media_trim", { clip_id: clipId, edge, time: layerSplitTime(time) });
}

function trimTimelineSelection(edge, time = previewTimelineTime()) {
  if(selectedLayerGroupIds().length){toast(groupSelectionIssue());return null;}
  if (state.timeline?.captionSelection) { toast("Automatic captions follow speech. Use their caption timing controls, not clip-edge trimming."); return null; }
  const id = state.timeline?.mediaSelection;
  if (!id) return null;
  const clip = [...(state.project?.manual?.media_clips || []), ...(state.project?.manual?.text_clips || [])].find(row => row.id === id);
  if (!clip) { state.timeline.mediaSelection = null; state.timeline.clearSelection(); toast("The selected clip is no longer available. Select it again before trimming."); return null; }
  if (typeof state.timeline.onMediaAction === "function") return state.timeline.onMediaAction("media_trim", { clip_id: id, edge, time: layerSplitTime(time) });
  return trimTimelineLayer(id, edge, time);
}

function renderSplitAvailability(time) {
  if (!elements.manualSplit) return;
  const ids=selectedLayerGroupIds();if(ids.length){const plan=groupSplitAvailability(ids,Number.isFinite(time)?time:state.timeline?.playhead);
    elements.manualSplit.disabled=!!plan.issue;elements.manualSplit.title=plan.issue || `Split ${ids.length} selected clips at the playhead in one Undo step.`;return;}
  // Availability must read the displayed cursor, not create/start a playback
  // clock during a render. Playback publishes its mapped cursor explicitly.
  if (!Number.isFinite(time)) time = Number.isFinite(state.timeline?.playhead) ? state.timeline.playhead
    : state.preview.editCursorProject === state.project?.id ? Number(state.preview.editCursor) || 0 : 0;
  const layer = state.timeline?.mediaSelection, caption = state.timeline?.captionSelection;
  const issue = layer ? layerSplitIssue(layer, time)
    : caption ? "Automatic captions follow speech. Split a media clip or a custom text caption instead."
    : state.captionDirty || state.captionContextSave ? "Save or discard the caption text before splitting footage." : "";
  const sourceLocked = !layer && Boolean(state.trackProtection?.lockedNames(activeEditTarget())?.length);
  elements.manualSplit.disabled = !state.project?.draft || foregroundBusy() || state.manualEditBusy || state.transcriptSaving || Boolean(issue) || sourceLocked
    || (!layer && state.project?.editor_sequence && !state.timeline?.canSplitAt?.(time));
  elements.manualSplit.title = issue || (sourceLocked ? "The selected source scope is locked. Unlock it in Edit > Track protection."
    : layer ? "Split the selected media or custom text clip at the playhead. Other layers and edit duration stay unchanged. One Undo restores it." : "Split source footage at the playhead in the chosen A/B scope.");
}

function splitTimelineLayer(clipId, time) {
  return applyManualEdit(String(clipId).startsWith("text_") ? "text_split" : "media_split", { clip_id: clipId, time: layerSplitTime(time) });
}

function splitTimelineSelection(time = previewTimelineTime()) {
  const ids=selectedLayerGroupIds();if(ids.length)return splitTimelineLayerGroup(ids,time);
  // A stale layer selection must never fall through and split A/B underneath.
  if (state.timeline?.mediaSelection) {
    const id = state.timeline.mediaSelection, clip = [...(state.project?.manual?.media_clips || []), ...(state.project?.manual?.text_clips || [])].find(row => row.id === id);
    if (!clip) { state.timeline.mediaSelection = null; state.timeline.clearSelection(); toast("The selected clip is no longer available. Select it again before splitting."); return null; }
    time = layerSplitTime(time);
    if (!Number.isFinite(time) || time - clip.start < .08 - 1e-9 || clip.end - time < .08 - 1e-9) { toast("Move the playhead inside the selected clip, leaving at least 0.08 seconds on each side."); return null; }
    if (typeof state.timeline.onMediaAction === "function") return state.timeline.onMediaAction("media_split", { clip_id: id, time });
    return splitTimelineLayer(id, time);
  }
  if (state.timeline?.captionSelection) { toast("Automatic captions follow speech and cannot be split with the clip tool. Use a custom text caption for independently editable pieces."); return null; }
  return handleTimelineEdit({ action: "split", time });
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

// Browser-local navigation only. Never restore project data, drafts, selection,
// tools, source review, focus or playback. Unknown identity opens normally.
function initializeEditingPositions() {
  if(state.editingPositions || typeof createEditingPositionStore!=="function")return;
  let storage=null;try{storage=window.localStorage;}catch{}
  const local=state.editingPositions={store:createEditingPositionStore(storage),epoch:0,loading:null,applying:false,timer:null};
  const input=event=>{
    if(event.type==="focusin" && (event.target===document.body || local.libraryFocus?.target===event.target
      && local.libraryFocus.owner===local.loading && local.loading?.returnPosition
      && local.libraryFocus.projectId===local.loading.projectId && local.epoch===local.loading.epoch))return;
    local.epoch+=1;requestEditingPositionCapture();
  };
  for(const name of ["pointerdown","keydown","wheel","focusin"])document.addEventListener(name,input,true);
  window.addEventListener("resize",input);
  for(const name of ["pointerup","keyup"])document.addEventListener(name,requestEditingPositionCapture,true);
  state.timeline?.scroll?.addEventListener("scroll",requestEditingPositionCapture);
  window.addEventListener("pagehide",()=>captureEditingPosition());
}
function invalidateEditingPositionReturn() {
  const local=state.editingPositions;
  if(local?.loading && !local.applying && !local.loading.installing)local.epoch+=1;
}
function editingPositionReady({sourceMode=false}={}) {
  const timeline=state.timeline;
  if(!state.project?.sources?.A || !state.studio.open || !timeline || state.preview.playing
    || !sourceMode && previewUsesSourceTime() || retainedEditStatus() || foregroundBusy()
    || state.recoveringJobs?.has(state.project.id) || workspaceResizeIssue()
    || projectSaveStatus().kind!=="saved" || hasUnsavedProjectWork()
    || state.sourceReview?.isOpen || state.mediaStudio?.shotReview?.open
    || state.sourceInsertSession || timeline.zoomFocusPending || timeline.editPending
    || document.getElementById("studioInspector")?.dataset.workbenchPane==="ai")return false;
  return ![...document.querySelectorAll("dialog[open]")].some(node=>node!==elements.projectsDialog);
}
function captureEditingPosition(owner=null) {
  const local=state.editingPositions;
  if(!local || local.applying || local.loading && local.loading!==owner || !editingPositionReady())return false;
  const viewport=state.timeline.captureEditingViewport?.();if(!viewport)return false;
  const pane=document.querySelector('.advanced-tabs [aria-selected="true"]')?.dataset.tab;
  return local.store.write(state.system?.instance_id,state.project,{cursor:previewTimelineTime(),viewport,pane});
}
function requestEditingPositionCapture() {
  const local=state.editingPositions;
  if(!local || local.loading || local.applying || state.preview.playing)return;
  if(local.timer!==null)clearTimeout(local.timer);
  local.timer=setTimeout(()=>{local.timer=null;captureEditingPosition();},350);
}
async function restoreEditingPosition(owner, project) {
  const local=state.editingPositions;
  if(!local || !owner || local.loading!==owner || !owner.returnPosition || !editingPositionReady({sourceMode:true}))return false;
  const instance=state.system?.instance_id,position=local.store.read(instance,project);
  if(!position)return false;
  const view=state.projectViewToken,revision=project.revision,identity=editingPositionIdentity(project);
  const current=()=>local.loading===owner && local.epoch===owner.epoch && state.project===project
    && state.projectViewToken===view && project.revision===revision && state.system?.instance_id===instance
    && editingPositionIdentity(project)===identity && editingPositionReady({sourceMode:true});
  // Hydration's final setProject and the visible workspace must both finish first.
  await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
  if(!current() || !state.timeline.editingViewportPlan?.(position.viewport))return false;
  local.applying=true;
  try {
    // Do not reveal/focus a pane or rewrite global workspace display preferences.
    selectAdvancedTab(position.pane,{reveal:false});
    state.preview.mode="edit";
    renderPreviewAvailability();
    seekPreview(position.cursor);
    if(!state.timeline.restoreEditingViewport(position.viewport))return false;
    updateZoomLabel();
    toast("Returned to your editing position. This browser only.");
    return true;
  } catch {return false;} finally {local.applying=false;}
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
  renderDirectorInstruction();
  renderUploadStorage();
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
  return Promise.resolve()
    .then(action)
    .catch((error) => {
      console.error("CUTROOM action failed", error);
      const prefix = context ? `${context}: ` : "";
      toast(`${prefix}${error?.message || uiCopy("הפעולה נכשלה", "The action failed")}`);
      return false;
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
  return null;
}

const DIRECTOR_INSTRUCTION_LIMIT = 8000;

function renderDirectorInstruction() {
  if (!elements.directorInstruction) return;
  const hebrew = state.locale === "he";
  const count = String(elements.directorInstruction.value || "").length;
  elements.directorInstruction.maxLength = DIRECTOR_INSTRUCTION_LIMIT;
  elements.directorInstruction.placeholder = hebrew
    ? "לדוגמה: לשמור את ההסבר על המחיר ואת ההסתייגות שמגיעה אחריו."
    : "Example: keep the pricing explanation and the qualification that follows it.";
  elements.directorInstruction.setAttribute("aria-invalid", String(count > DIRECTOR_INSTRUCTION_LIMIT));
  if (elements.directorInstructionCounter) {
    elements.directorInstructionCounter.textContent = `${count.toLocaleString("en-US")} / 8,000 ${hebrew ? "תווים" : "characters"}`;
    elements.directorInstructionCounter.setAttribute("dir", "auto");
  }
}

function storagePlanText(plan) {
  if (!Array.isArray(plan?.filesystems)) return "";
  return plan.filesystems.map((filesystem) => {
    const roles = (filesystem.roles || []).map((role) => role === "data" ? "Project data" : role === "temporary" ? "Temporary files" : role).join(" + ");
    const locations=Array.isArray(filesystem.locations)?filesystem.locations.join(" · "):filesystem.location||filesystem.filesystem||"filesystem";
    return `${roles} (${locations}): ${formatBytes(filesystem.disk_free_bytes)} free; ${formatBytes(filesystem.reserved_bytes||0)} reserved by other imports; ${formatBytes(filesystem.required_bytes)} estimated work + ${formatBytes(filesystem.reserve_bytes??plan.reserve_bytes??0)} safety reserve; ${formatBytes(filesystem.available_bytes)} available after reserve.`;
  }).join("\n");
}

function storagePlanSummary(plan) {
  if (!Array.isArray(plan?.filesystems)) return "";
  return plan.filesystems.map((filesystem) => {
    const locations = Array.isArray(filesystem.locations) ? filesystem.locations.join(" · ") : filesystem.location || filesystem.filesystem || "disk";
    return `${locations} · ${formatBytes(filesystem.disk_free_bytes)} free, ${formatBytes(filesystem.available_bytes)} usable after the safety margin`;
  }).join("; ");
}

function rememberUploadStorage(upload, plan) {
  if (!plan) return;
  upload.storagePlan = plan;
  state.uploadStorage.set(uploadStateKey(upload.projectId, upload.slot || "media"), {
    projectId: upload.projectId, label: upload.slot || "Media", plan,
  });
  renderUploadStorage();
}

function renderUploadStorage() {
  if (!elements.uploadStorageInfo) return;
  const entries = [...state.uploadStorage.values()].filter((entry) => entry.projectId === state.project?.id);
  // One readable line per volume; the full reserve arithmetic stays in the tooltip.
  elements.uploadStorageInfo.textContent = entries.map((entry) => `${entry.label}: ${storagePlanSummary(entry.plan)}`).join("\n");
  elements.uploadStorageInfo.title = entries.map((entry) => `${entry.label}: ${storagePlanText(entry.plan)}`).join("\n");
  elements.uploadStorageInfo.hidden = !elements.uploadStorageInfo.textContent;
}

function uploadStatusText(upload) {
  if (upload.cancelRequested) return t("cancelling");
  if (upload.phase === "checking") return "Checking storage";
  if (upload.phase === "importing") return "Checking / importing";
  return `Sending ${Math.round(Math.max(0, Math.min(1, Number(upload.progress) || 0)) * 100)}%`;
}

function uploadFailureMessage(error, file) {
  const payload = error?.payload || {};
  if (Number(error?.status) === 413 || error?.code === "file_too_large") {
    const limit = Number(payload.max_upload_bytes);
    return Number.isFinite(limit) && limit > 0
      ? t("fileTooLarge").replace("{file}", formatBytes(file.size)).replace("{limit}", formatBytes(limit))
      : error.message || "The file exceeds this import limit.";
  }
  if (Number(error?.status) === 507 || error?.code === "insufficient_storage") {
    const free = Number(payload.disk_free_bytes);
    const message = Number.isFinite(free)
      ? t("notEnoughDisk").replace("{file}", formatBytes(file.size)).replace("{free}", formatBytes(free))
      : String(error.message || "Insufficient storage for this import.");
    return [message, storagePlanText(payload.storage_plan)].filter(Boolean).join("\n");
  }
  return error?.message || String(error);
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
  initNumericScrub({ document, window, canEdit: () => !foregroundBusy() && !state.manualEditBusy,
    context: () => [state.project?.id, state.project?.revision, state.mediaStudio?.selected, state.textStudio?.selected, state.trimClip?.id].join('|'),
    onCommit: field => {
      if (field.dataset.media || field.dataset.mix) void state.mediaStudio?.flush();
      else if (field.dataset.text) void state.textStudio?.flush();
      else if (/^embedded(?:Camera[XYWH]|Content[XY])$/.test(field.id)) void flushEmbeddedCameraSave();
    } });
  const localModels = initLocalModels({ document, api, busy: foregroundBusy,
    changed: async () => { state.runtimeGeneration += 1; await loadSystem(); },
  });
  state.transcription = initTranscriptionEngine({ document, api, busy: foregroundBusy, pause: pauseAllMedia,
    changed: async () => { state.runtimeGeneration += 1; await loadSystem(); },
  });
  state.welcome = initWelcome({ document, api,
    models: localModels, transcription: state.transcription,
    createProject: (options) => runUiAction(() => createProject(options)), goHome,
    pause: pauseAllMedia, busy: foregroundBusy, recovery: retainedEditStatus,
    changed: async (connection) => {
      state.system = { ...(state.system || {}), ai_connection: connection };
      state.runtimeGeneration += 1;
      await loadSystem();
    },
  });
  initWorkspace({ document, window, resizeIssue: workspaceResizeIssue, translate: (key, fallback) => state.dictionary?.[key] ?? fallback, onResize: () => state.timeline?.scheduleDraw(), openShortcuts: () => { renderKeyboardHelp(); elements.keyboardDialog.showModal(); } });
  initializeMediaStudio();
  initializeTextStudio();
  // Presentation reads the real project/edit clock, never the source-player label.
  elements.advancedPanel.outputReviewSnapshot = outputReviewSnapshot;
  const outputShelf = document.getElementById("studioShelfOutput");
  const aspectField = document.getElementById("outputAspectField");
  if (outputShelf && aspectField) outputShelf.appendChild(aspectField);
  state.trackProtection = initTrackProtection({ document, getProject: () => state.project,
    busy: () => state.manualEditBusy || foregroundBusy(),
    change: (slot, locked) => applyManualEdit("set_track_lock", { slot, locked }) });
  state.timeline = new TimelineView(elements.timelineCanvas, elements.timelineScroll,
    (time) => { pauseAllMedia(); seekSourcePreview(time); }, setManualSelection, handleTimelineEdit,
    { onToolStateChange: () => { renderTimelineToolStatus(); renderLayerGroupControls(); renderLayerTrackControls(); state.rangeAudition?.sync(); state.mediaStudio?.clipOpacity?.refresh(); state.markedLayers?.sync(); }, canEdit: canEditTimeline,
      onLayoutSelect: openTimelineLayout, getTrackClips: trackClips, getAudioSlot: () => sourceMixerSettings().audioSlot,
      onTargetChange: (target) => setEditTarget(target, true),
      rangeDeleteIssue: rangeDeletePreviewIssue,
      onMediaSelect: id => { void selectTimelineMedia(id); },
      onAssetOccurrenceSelect: selectMediaAssetOccurrence, assetOccurrenceIssue: mediaUsageNavigationIssue,
      onMediaSelectionChange: selectTimelineLayers,
      mediaGroupMovePreview: layerGroupMovePlan,
      mediaGroupRelocatePreview: layerGroupRelocatePlan,
      mediaGroupRemoveIssue: layerGroupRemoveIssue,
      mediaGroupDuplicateIssue: layerGroupDuplicateIssue,
      onMediaGroupPreview: previewLayerGroup,
      onMediaEdit: (id, patch) => { const studio = id.startsWith("text_") ? state.textStudio : state.mediaStudio; studio?.queueClip(id,patch); return studio?.flush(); },
      onMediaPreview: (id, patch) => (id.startsWith("text_") ? state.textStudio : state.mediaStudio)?.previewClip(id,patch),
      onMediaAction: editLayerAction,
      mediaSplitIssue: layerSplitIssue,
      mediaTrimPreview: layerTrimPlan,
      mediaSlipPreview: layerSlipPlan,
      mediaMovePreview: layerMovePlan,
      mediaTrackMovePreview: layerTrackMovePlan, onTrackManage: openLayerTrackManager, trackLockIssue, trackHeaderReadiness,
      mediaSourceIssue: (id,time) => state.mediaStudio?.sourceMatchPlan(id,time)?.issue || (state.mediaStudio ? "" : "Source review is unavailable."),
      onMediaSourceOpen: openTimelineSource,
      onCaptionSelect: id => { void selectCaptionItem(id, { reveal: false }); },
      onCaptionEdit: (id, times) => runCaptionAction("caption_update", { caption_id: id, ...times }),
      onCaptionAction: (action, detail) => runCaptionAction(action, detail),
      onCaptionOpen: id => { void selectCaptionItem(id, { seek: true, focus: true }); } });
  if (typeof initTimelineMediaDrop === "function") {
    state.timeline.libraryDrop = initTimelineMediaDrop(state.timeline, {
      place: (assetId, time, options, context) => state.mediaStudio?.place(assetId, time, options, context),
      sourceSelection: assetId => state.mediaStudio?.dragSelection(assetId),
      sourceRoot: () => state.mediaStudio?.root,
      placementPreview: (assetId,time,options) => state.mediaStudio?.placementPreview(assetId,time,options) ?? {issue:"Media is not ready for placement."},
      insertionIssue: (assetId, time, options) => state.mediaStudio?.insertionIssue(assetId, time, options) ?? "Media is not ready for insertion.",
      canPlace: () => !foregroundBusy() && !state.mediaStudio?.importQueue?.running,
    });
  }
  if (typeof initRangeAudition === "function") {
    state.rangeAudition = initRangeAudition(state.timeline.navigation?.bar, {
      snapshot: rangeAuditionSnapshot, seek: t => seekPreview(t, undefined, true), play: playPreview, pause: pauseAllMedia,
      isPlaying: () => state.preview.playing, format: formatSourceTime, ready: rangeAuditionMediaReady, notice: toast,
    });
  }
  if(typeof initMarkedLayers==="function")state.markedLayers=initMarkedLayers(state.timeline.navigation?.bar,{
    snapshot:markedLayerSnapshot,mark:markReviewedLayers,notify:toast,focus:()=>elements.timelineCanvas?.focus({preventScroll:true})});
  if (typeof initReviewMarkers === "function") state.timeline.reviewMarkers = initReviewMarkers(state.timeline.navigation?.bar,
    document.getElementById("timelineMarkersDialog"), {snapshot:reviewMarkerSnapshot,write:writeReviewMarker,
      pause:pauseAllMedia,seek:t=>seekPreview(t),notify:toast});
  initializeEditingPositions();
  initializeKeyboardProfile();
  state.audioMeter = new AudioThresholdView(elements.audioMeterCanvas);
  elements.audioMeterCanvas.addEventListener("cutroom-audio-seek", (event) => {
    const time = Number(event.detail?.time);
    if (Number.isFinite(time)) seekPreview(time);
  });
  await Promise.allSettled([loadProjects(), loadSystem(), recoverProjectCopies()]);
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
  if(typeof initTrackLift==="function")state.trackLift=initTrackLift(document.getElementById("trackLift"),{snapshot:trackLiftSnapshot,commit:commitTrackLift});
  document.getElementById("applyAiDraftButton")?.addEventListener("click", openAiDraftConfirmation);
  elements.newProjectButton.addEventListener("click", () => state.welcome?.startWorkflow("manual"));
  document.getElementById("homeViewAllProjects")?.addEventListener("click", () => elements.projectsButton.click());
  elements.dialogNewProject.addEventListener("click", () => { elements.projectsDialog.close(); return state.welcome?.startWorkflow("manual"); });
  elements.homeButton.addEventListener("click", () => runUiAction(goHome));
  elements.projectsButton.addEventListener("click", openProjectsDialog);
  elements.projectName.addEventListener("input", () => {
    schedulePatch({ name: elements.projectName.value });
  });
  elements.directorInstruction.addEventListener("input", () => {
    renderDirectorInstruction();
    renderReadiness();
    scheduleSettingsPatch({ requiresRebuild: true, reason: "brief" });
  });
  elements.sourceContext?.addEventListener("input", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "source context" });
  });
  elements.allowExtractiveRoughCut?.addEventListener("change", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "rough-cut fallback" });
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
    const settings = applyGoalMode(button.dataset.value, true);
    renderEditStyleChoices();
    scheduleSettingsPatch({ requiresRebuild: true, reason: "goal", settings });
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
    const audio_cleanup = applyAudioPreset(button.dataset.value);
    scheduleSettingsPatch({ requiresRebuild: true, reason: "audio", settings: { audio_cleanup } });
  });
  elements.spokenLanguageSelect.addEventListener("change", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "language" });
    renderLanguageDetectionStatus();
  });
  elements.performanceModeSelect.addEventListener("change", () => {
    scheduleSettingsPatch({ requiresRebuild: true, reason: "performance" });
    // The Story model depends on the mode: refresh a running local engine's
    // status so an optional upgrade shows now, not after the next AI run.
    const connection = state.system?.ai_connection;
    if (state.system?.runtime?.state === "ready" && (!connection?.mode || connection.mode === "local")) prepareLocalAI().catch(() => {});
  });
  elements.visualAiSelect?.addEventListener("change", () => scheduleSettingsPatch({ requiresRebuild: true, reason: "visual_ai" }));
  [[elements.silenceAction, "silence_action"], [elements.quietAction, "quiet_action"], [elements.loudAction, "loud_action"], [elements.normalizeAudio, "normalize"]].forEach(([control, field]) => control.addEventListener("change", () => {
    setAudioPresetCustom(); updateAudioOutputs(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio", settings: { audio_cleanup: { [field]: currentAudioSettings()[field] } } });
  }));
  [[elements.silenceMin, "silence_min_seconds"], [elements.silenceKeep, "silence_keep_seconds"], [elements.maxRemoveRatio, "max_remove_ratio"], [elements.quietGain, "quiet_gain_db"], [elements.loudGain, "loud_gain_db"]].forEach(([control, field]) => {
    control.addEventListener("input", updateAudioOutputs);
    control.addEventListener("change", () => { setAudioPresetCustom(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio", settings: { audio_cleanup: { [field]: currentAudioSettings()[field] } } }); });
  });
  [[elements.silenceThreshold, "silence_threshold_dbfs"], [elements.preSilenceMin, "silence_min_seconds"], [elements.preSilenceKeep, "silence_keep_seconds"]].forEach(([control, field]) => {
    control.addEventListener("input", () => { syncPreAudioControls(control.id); renderAudioCalibration(); });
    control.addEventListener("change", () => { syncPreAudioControls(control.id); setAudioPresetCustom(); scheduleSettingsPatch({ requiresRebuild: true, reason: "audio", settings: { audio_cleanup: { [field]: currentAudioSettings()[field] } } }); });
  });
  elements.useRecommendedThreshold.addEventListener("click", () => {
    const profile = preAudioProfile();
    const recommended = Number(profile?.summary?.recommended_silence_threshold_dbfs ?? profile?.summary?.silence_threshold_dbfs);
    if (!Number.isFinite(recommended)) return;
    elements.silenceThreshold.value = Math.round(recommended);
    syncPreAudioControls("silenceThreshold");
    renderAudioCalibration();
    scheduleSettingsPatch({ requiresRebuild: true, reason: "audio", settings: { audio_cleanup: { silence_threshold_dbfs: Number(elements.silenceThreshold.value) } } });
  });
  elements.durationMode.addEventListener("change", () => scheduleSettingsPatch({ requiresRebuild: true, reason: "duration intent" }));
  elements.targetDuration.addEventListener("input", () => updateDurationControl(Number(elements.targetDuration.value)));
  elements.targetDuration.addEventListener("change", () => scheduleSettingsPatch({ requiresRebuild: true, reason: "duration" }));
  $$(".quick-values button").forEach((button) => button.addEventListener("click", () => chooseDurationPreset(Number(button.dataset.seconds))));

  elements.generateButton.addEventListener("click", () => runUiAction(startDirectorAction));
  document.addEventListener("workbench-ai-context", () => {
    if(document.getElementById("studioInspector")?.dataset.workbenchPane==="ai"){state.mediaStudio?.closeSourceMonitor?.();closePrimarySourceReview();closeSourceInsert();}
    renderReadiness();
  });
  elements.cancelJobButton.addEventListener("click", cancelActiveJob);
  elements.globalCancelJobButton.addEventListener("click", cancelActiveJob);
  elements.retryDirectorButton.addEventListener("click", generateDraft);
  elements.backFromErrorButton.addEventListener("click", () => state.project?.draft ? showResult() : showSetup());
  elements.backToBriefButton.addEventListener("click", showSetup);
  $$("[data-open-studio-tab]").forEach((button) => {
    button.addEventListener("click", () => openStudioTab(button.dataset.openStudioTab));
  });
  elements.reviewSpeechSettings.addEventListener("click", openSpeechReviewSettings);
  document.getElementById("streamerLayoutReview")?.addEventListener("click", reviewStreamerLayout);
  document.getElementById("streamerLayoutDismiss")?.addEventListener("click", () => {
    try { localStorage.setItem(streamerTipKey(), "dismissed"); } catch { /* the tip simply returns next time */ }
    renderStreamerLayoutTip();
  });
  document.getElementById("reviewDurationSettings")?.addEventListener("click", () => {
    if (foregroundBusy() || state.manualEditBusy) return;
    showSetup();
    elements.editStyleChoices?.querySelector('button[aria-checked="true"]')?.focus();
    elements.durationGroup?.scrollIntoView({block:"nearest"});
  });
  $$(".refine-grid button").forEach((button) => button.addEventListener("click", () => refineDraft(button.dataset.command)));
  elements.reelCandidateList.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-candidate-id]");
    if (!button || button.disabled) return;
    if (supportsReelReview(state.project)) {
      const projectId = state.project.id;
      if (!(await flushCurrentProjectSaves()) || state.project?.id !== projectId || foregroundBusy() || state.draftDirtyReasons.size) return;
      pauseAllMedia();
      const project = state.project;
      const revision = project.revision;
      const review = new ReelProposalReview({
        project, candidateId: button.dataset.candidateId, api, copy: uiCopy, formatTime,
        sourceUrl: sourceMediaUrl(project.sources.A),
        isCurrent: () => state.project?.id === projectId && state.project.revision === revision && !foregroundBusy() && !state.draftDirtyReasons.size,
        apply: proposal => applyManualEdit(proposal.kind === "unverified_source_candidate" ? "apply_review_candidate" : "apply_reel_candidate", {candidate_id: proposal.candidate_id, proposal_id: proposal.proposal_id}),
      });
      await review.open();
      return;
    }
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

  initColorMotionPanel();

  elements.advancedButton.addEventListener("click", toggleAdvanced);
  elements.closeAdvanced.addEventListener("click", () => setAdvanced(false));
  $$('[data-edit-tool]').forEach(button => button.addEventListener('click', () => selectEditTool(button.dataset.editTool)));
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
  [[elements.resolutionSelect, "resolution"], [elements.qualitySelect, "quality"], [elements.fpsSelect, "fps"], [elements.autoReframe, "auto_reframe"], [elements.effectsToggle, "editorial_effects"], [elements.captionsToggle, "captions"]].forEach(([control, field]) => control.addEventListener("change", () => {
    // Output preferences never stage or round the selected source clip crop.
    if (control === elements.fpsSelect) updateFrameRateControls(elements.fpsSelect.value);
    const requiresRebuild = control === elements.autoReframe;
    scheduleSettingsPatch({ requiresRebuild, reason: requiresRebuild ? "framing" : "output", settings: { [field]: currentSettings()[field] } });
    if (control === elements.captionsToggle) renderCaptionControls();
  }));
  elements.exportFpsSelect.addEventListener("change", () => {
    if (foregroundBusy()) return;
    updateFrameRateControls(elements.exportFpsSelect.value);
    refreshExportScope();
    scheduleSettingsPatch({ requiresRebuild: false, reason: "output", settings: { fps: selectedFrameRate() } });
  });
  elements.audioCalibration.addEventListener("toggle", () => {
    if (elements.audioCalibration.open) state.audioMeter?.draw();
  });
  elements.layoutSelect.addEventListener("change", () => {
    syncSecondaryPreview(previewPlaybackTime());
    scheduleSettingsPatch({ requiresRebuild: true, reason: "framing", settings: { layout: elements.layoutSelect.value } });
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
  elements.transcriptEditForm.addEventListener("submit", submitTranscriptText);
  initializeTranscriptSections();
  elements.transcriptDiscard.addEventListener("click", discardTranscriptBuffer);
  elements.transcriptPrevious.addEventListener("click", () => moveTranscriptLine(-1));
  elements.transcriptNext.addEventListener("click", () => moveTranscriptLine(1));
  elements.transcriptSaveAll.addEventListener("click", event => activateTranscriptSaveAll({ focusOwner: event.detail === 0 ? event.currentTarget : null }));
  bindCaptionItemEvents();
  elements.transcriptRemove.addEventListener("click", () => { if(!selectedTranscriptRecoveryDraft())runManualRangeEdit("delete_range", "edit"); });
  elements.transcriptRestore.addEventListener("click", () => { if(!selectedTranscriptRecoveryDraft())runManualRangeEdit("restore_range", "edit"); });
  elements.clipTrimForm.addEventListener("submit", applySelectedClipTrim);
  $$('[data-timeline-tool]').forEach((button) => button.addEventListener("click", () => {
    setTimelineTool(button.dataset.timelineTool);
  }));
  elements.cancelTimelineCut.addEventListener("click", () => { state.timeline?.cancelPendingCut(); elements.timelineCanvas.focus(); });
  elements.timelineSnap.addEventListener("click", () => { state.timeline?.setSnapping(!state.timeline.snapping); elements.timelineCanvas.focus(); });
  elements.manualClear.addEventListener("click", () => { if(selectedLayerGroupIds().length){void selectTimelineLayers([],null);return;} state.markIn = null; state.timeline?.clearSelection(); elements.timelineCanvas.focus(); });
  elements.manualRange.addEventListener("click", () => {
    openStudioTab("timeline");
    selectEditTool("clip");
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
  elements.saveState?.addEventListener("click", () => { void activateSaveStatus(); });
  window.addEventListener("beforeunload", (event) => {
    if (hasUnsavedProjectWork()) { event.preventDefault(); event.returnValue = ""; }
  });
  elements.burnCaptionsToggle.addEventListener("change", () => {
    setCaptionBurnEnabled(elements.burnCaptionsToggle.checked, true);
    scheduleSettingsPatch({ reason: "captions", settings: { burn_captions: captionBurnEnabled() } });
  });
  elements.studioBurnCaptionsToggle.addEventListener("change", () => {
    setCaptionBurnEnabled(elements.studioBurnCaptionsToggle.checked, true);
    scheduleSettingsPatch({ reason: "captions", settings: { burn_captions: captionBurnEnabled() } });
  });
  [[elements.captionStyleSelect, "caption_style"], [elements.captionPositionSelect, "caption_position"]].forEach(([control, field]) => control.addEventListener("change", () => {
    renderCaptionControls();
    scheduleSettingsPatch({ reason: "captions", settings: { [field]: currentSettings()[field] } });
  }));
  [[elements.captionScale, "caption_scale"], [elements.captionWordsPerLine, "caption_words_per_line"]].forEach(([control, field]) => {
    control.addEventListener("input", renderCaptionControls);
    control.addEventListener("change", () => scheduleSettingsPatch({ reason: "captions", settings: { [field]: currentSettings()[field] } }));
  });
  elements.manualRestore.addEventListener("click", () => runManualRangeEdit("restore_range"));
  elements.editorMoreButton.addEventListener("click", () => {
    if (!openStudioTab("timeline")) return;
    selectEditTool("clip");
    elements.editorMoreTools.open = true;
    elements.editorMoreTools.scrollIntoView({ block: "nearest" });
    elements.editorMoreTools.querySelector("summary").focus();
  });
  elements.sourceInsertForm.addEventListener("submit", insertSourceFootage);
  elements.emptyTimelineAdd.addEventListener("click", () => {
    if(retainedEditStatus()){runUiAction(resumeRetainedEdit);return;}
    if (!state.project?.draft && state.project?.settings?.workflow === "manual") {
      if (state.project.sources?.A) runUiAction(openManualDraft);
      else if (state.mediaStudio?.chooseFiles) state.mediaStudio.chooseFiles();
      else elements.sourceInputA.click();
    } else openSourceReview();
  });
  document.getElementById("reviewSourceButton").addEventListener("click", openSourceReview);
  for (const id of ["reviewLayoutCoverage", "reviewExportLayout"]) {
    document.getElementById(id)?.addEventListener("click", reviewSourceTiming);
  }
  document.getElementById("reviewSharedSourceTiming")?.addEventListener("click", () => {
    if (sourceMixerControlBusy()) return;
    openStudioTab("framing");
    const details = document.getElementById("sharedSourceTimingDetails"); if (details) details.open = true;
    elements.sourceSyncOffset?.scrollIntoView({block:"center"});
  });
  document.getElementById("reviewIndependentSourceTiming")?.addEventListener("click", () => {
    if (sourceMixerControlBusy()) return;
    setEditTarget("B"); openSourceReview();
  });
  document.getElementById("closeTimelineGaps").addEventListener("click", () => {
    const slot = activeEditTarget();
    applyManualEdit("sequence_close_gaps", slot === "edit" ? {} : {slot});
  });
  elements.sourceInsertSlot.addEventListener("change", () => {
    const slot = elements.sourceInsertSlot.value;
    elements.sourceInsertIn.value = "00:00.000";
    elements.sourceInsertOut.value = formatSourceTime(Math.min(5, Number(state.project?.sources?.[slot]?.duration || 0)));
    if (state.sourceInsertSession) state.sourceInsertSession.sourceOut = elements.sourceInsertOut.value;
    renderSourceInsert();
  });
  for (const control of [elements.sourceInsertIn, elements.sourceInsertOut, elements.sourceInsertAt]) control.addEventListener("input", renderSourceInsert);
  elements.sourceInsertMode.addEventListener("change", renderSourceInsert);
  elements.sourceInsertZone.addEventListener("change", renderSourceInsert);
  elements.sourceInsertCancel.addEventListener("click", () => { if (!state.sourceInsertSession?.busy) closeSourceInsert(); });
  elements.clipDuplicate.addEventListener("click", async event => {
    if (state.timeline?.mediaSelection || state.timeline?.captionSelection) return duplicateTimelineSelection(undefined,{focusOwner:event?.currentTarget});
    const clip = selectedTimelineClip();
    if (!clip || !state.project?.editor_sequence) return;
    const projectId = state.project.id;
    const updated = activeEditTarget() === "edit"
      ? await applyManualEdit("sequence_duplicate_range", { start: clip.start, end: clip.end, to: clip.end })
      : await applyManualEdit("sequence_duplicate", { slot: activeEditTarget(), clip_id: clip.id, start: clip.end });
    if (updated && state.project?.id === projectId) { state.timeline.selectRange(clip.end, clip.end + clip.end - clip.start); seekSourcePreview(clip.end); }
  });
  elements.manualDelete.setAttribute("aria-describedby", "timelineRangeImpactDetails");
  elements.manualDelete.addEventListener("click", () => runManualRangeEdit("delete_range"));
  elements.manualSplit.addEventListener("click", () => splitTimelineSelection());
  elements.timelineTarget.addEventListener("change", () => setEditTarget(elements.timelineTarget.value));
  elements.trackReset.addEventListener("click", () => {
    const sequence = Boolean(state.project?.editor_sequence);
    const target = activeEditTarget();
    const message = sequence
      ? "Reset timeline edits to the current draft? You can undo this."
      : `Reset changes to track ${target}? You can undo this.`;
    if (!confirm(message)) return;
    if (sequence) applyManualEdit("sequence_reset");
    else if (target !== "edit") applyManualEdit("track_reset", { slot: target });
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
  document.getElementById("clipBoardButton")?.addEventListener("click", openClipBoard);
  elements.resultRenderButton.addEventListener("click", openExportDialog);
  elements.closeExportDialog.addEventListener("click", () => elements.exportDialog.close());
  elements.cancelExport.addEventListener("click", () => elements.exportDialog.close());
  document.getElementById("reviewOutputSettings")?.addEventListener("click", reviewOutputSettings);
  elements.cancelExportJobButton.addEventListener("click", cancelActiveJob);
  elements.confirmExport.addEventListener("click", startExport);
  elements.exportScope?.addEventListener("change", () => refreshExportScope({ choose:true }));
  elements.modelButton.addEventListener("click", installModel);
  document.getElementById?.("modelUpgradeButton")?.addEventListener("click", () => document.getElementById("homeModelsButton")?.click());
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
  const request = ++projectLibrary.listRequest;
  const payload = await api("/api/projects");
  if (request !== projectLibrary.listRequest) return;
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
  state.transcription?.setStatus(state.system?.transcription_engine);
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
  renderRecentProjects();
  window.scrollTo({ top: 0 });
}

// Start creates a project before a recording is chosen. Leaving it untouched
// would add an empty "In setup" row to Home every time, so it is discarded.
const DEFAULT_MANUAL_KEYS = new Set(["cuts", "keep_ranges", "camera_plan", "camera_overrides", "source_mixer", "crop"]);
function untouchedProject(project) {
  if (!project || project.settings?.workflow === "manual" || project.draft || project.name_auto || (project.exports || []).length) return false;
  if (!["", "new project", "untitled project"].includes(String(project.name || "").trim().toLowerCase())) return false;
  if (Object.values(project.sources || {}).some(Boolean) || Object.keys(project.assets || {}).length) return false;
  if (String(project.settings?.instruction || "").trim()) return false;
  return Object.entries(project.manual || {}).every(([key, value]) =>
    DEFAULT_MANUAL_KEYS.has(key) && (!Array.isArray(value) || value.length === 0));
}

async function discardUntouchedProject(nextProjectId = null) {
  const project = state.project;
  if (!project || project.id === nextProjectId || !untouchedProject(project) || foregroundBusy()) return;
  try {
    await api(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
    state.projects = state.projects.filter((item) => item.id !== project.id);
    if (localStorage.getItem(lastProjectStorageKey()) === project.id) localStorage.removeItem(lastProjectStorageKey());
    state.project = null;
  } catch {
    // Keeping an empty project is harmless; never block navigation on it.
  }
}

async function goHome() {
  pauseAllMedia();
  const viewToken=state.projectViewToken;
  if (!(await flushCurrentProjectSaves())) return false;
  if(state.projectViewToken!==viewToken)return false;
  captureEditingPosition();
  await discardUntouchedProject();
  if(state.projectViewToken!==viewToken)return false;
  state.projectViewToken += 1;
  showWelcome();
  return true;
}

function showWorkspace() {
  document.body.classList.remove("welcome-mode");
  elements.welcomeView.hidden = true;
  elements.workspaceView.hidden = false;
  elements.projectHead.hidden = false;
  elements.renderButton.disabled = !state.project?.draft || Boolean(state.project?.editor_sequence?.error) || foregroundBusy() || exportRequiresDraftRebuild();
}

async function createProject({ workflow = "short" } = {}) {
  pauseAllMedia();
  if (!(await flushCurrentProjectSaves())) return false;
  await discardUntouchedProject();
  const initialSettings = workflowSettings(workflow);
  const payload = await api("/api/projects", { method: "POST", body: JSON.stringify({ name: "New project", initial_settings: initialSettings }) });
  state.projects.unshift(payload.project);
  await openProject(payload.project.id);
  if (state.project?.id === payload.project.id) window.scrollTo({ top: 0 });
  toast(t("projectCreated"), "success");
  return state.project?.id===payload.project.id ? state.project : false;
}

function retainedEditStatus(project = state.project) {
  if (!project || (project.draft && typeof project.draft === "object" && !Array.isArray(project.draft))) return null;
  const manual=project.manual;
  const evidence=Boolean(manual && (typeof manual!=="object" || Array.isArray(manual)
    || ["sequence","layer_tracks"].some(key=>Object.hasOwn(manual,key))
    || ["source_tracks","media_clips","text_clips","cuts","keeps","keep_ranges"].some(key=>
      Array.isArray(manual[key]) ? manual[key].length : manual[key] && (typeof manual[key]!=="object" || Object.keys(manual[key]).length))));
  const raw=project.retained_edit;
  if(raw==null && !evidence)return null;
  const unavailable="The saved timeline needs a compatible recovery check. Reload this project; no full recording will be substituted.";
  const result={available:false,issue:unavailable,duration:null,source_a_clips:0,media_clips:0,text_clips:0,track_count:0};
  if(!raw || typeof raw!=="object" || Array.isArray(raw) || typeof raw.available!=="boolean" || typeof raw.issue!=="string")return result;
  if(Number.isFinite(raw.duration) && raw.duration>=0 && raw.duration<=86400)result.duration=raw.duration;
  const keys=["source_a_clips","media_clips","text_clips","track_count"];
  if(keys.some(key=>!Number.isInteger(raw[key]) || raw[key]<0))return result;
  for(const key of keys)result[key]=raw[key];
  if(raw.available && (project.draft!=null || result.duration===null || raw.issue))return result;
  result.available=raw.available;
  result.issue=raw.available ? "" : raw.issue || unavailable;
  return result;
}

function retainedEditIssue() {
  const recovery=retainedEditStatus();
  return recovery ? recovery.issue || "Resume the saved timeline before editing, importing or generating AI." : "";
}

function requireResumedEdit() {
  const issue=retainedEditIssue();if(!issue)return true;
  toast(issue);return false;
}

function retainedEditView() {
  return JSON.stringify([state.studio.open,Boolean(elements.setupPanel?.hidden),
    document.getElementById("studioInspector")?.dataset.workbenchPane,
    document.querySelector('.advanced-tabs [aria-selected="true"]')?.dataset.tab]);
}

async function resumeRetainedEdit() {
  const recovery=retainedEditStatus();
  if(!recovery || state.retainedResumePending || foregroundBusy())return false;
  if(!recovery.available){toast(recovery.issue);return false;}
  const projectId=state.project.id,viewToken=state.projectViewToken,view=retainedEditView();
  const identity=JSON.stringify([state.project.sources,state.project.manual]);
  const time=Number(state.timeline?.playhead)||0;
  const request={projectId,viewToken};state.retainedResumePending=request;
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken;
  const sameView=()=>current() && retainedEditView()===view;
  let lock=null;
  pauseAllMedia();renderReadiness();
  try {
    if(!(await flushCurrentProjectSaves()) || !sameView())return false;
    const latest=retainedEditStatus();
    if(!latest?.available || identity!==JSON.stringify([state.project.sources,state.project.manual])){
      toast(latest?.issue || "The saved timeline or source changed. Review the current recovery notice and try again.");return false;
    }
    lock=acquireJobStartLock("retained_resume",projectId);if(!lock)return false;
    const revision=state.project.revision;
    const preservedKeys=["sources","manual","settings","assets","analysis","pre_analysis","name","language"];
    const preserved=JSON.stringify(preservedKeys.map(key=>state.project[key]));
    const result=await api(`/api/projects/${encodeURIComponent(projectId)}/retained-edit/resume`,{
      method:"POST",body:JSON.stringify({expected_revision:revision})});
    if(!current())return false;
    const accepted=result.project;
    if(accepted?.id!==projectId || !accepted.draft || typeof accepted.draft!=="object" || Array.isArray(accepted.draft)
      || !Number.isInteger(accepted.revision) || accepted.revision<=revision
      || preserved!==JSON.stringify(preservedKeys.map(key=>accepted[key])))throw new Error("The Resume response did not preserve the reviewed state. Reload the project to verify it.");
    if(accepted.revision<state.project.revision){toast("A newer project state is already open. The older Resume response was not applied here.");return false;}
    const reveal=sameView();state.project=result.project;rememberProjectRevision(result.project);
    if(reveal){
      state.preview.mode="edit";hydrateProject();setAdvanced(true);
      seekSourcePreview(Math.max(0,Math.min(Number(result.project.editor_sequence?.duration)||0,time)));
      toast("Saved timeline resumed. No AI ran and no old analysis or history was recreated.","success");
    }else{
      loadDraftRebuildState(result.project);state.timeline?.setProject(editorProject());
      state.mediaStudio?.render();state.textStudio?.render();renderReadiness();updateStudioStatus();
    }
    return true;
  } catch(error) {
    if(!current())return false;
    if(error?.status===409){
      try{
        const result=await api(`/api/projects/${encodeURIComponent(projectId)}`);
        if(!current())return false;
        if(result.project?.id===projectId && result.project.revision>=state.project.revision){
          const reveal=sameView();state.project=result.project;rememberProjectRevision(result.project);
          if(reveal)hydrateProject();else{state.timeline?.setProject(editorProject());renderReadiness();updateStudioStatus();}
        }
      }catch(_refreshError){/* Keep the retained edit intact; never retry activation. */}
      if(current())toast("The project changed or is busy. The latest available state is shown; review it before trying Resume again.");
    }else if(current())toast(`Could not confirm Resume. Reload the project before retrying: ${error.message}`);
    return false;
  } finally {
    if(state.retainedResumePending===request)state.retainedResumePending=null;
    if(lock)releaseJobStartLock(lock);else renderReadiness();
  }
}

async function openManualDraft() {
  if(retainedEditStatus())return resumeRetainedEdit();
  if (!state.project || foregroundBusy()) return;
  if (!state.project.sources?.A) { showEmptyManualEditor(); return; }
  if (state.project.draft) { setAdvanced(true); return; }
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

async function openProject(projectId, { skipFlush = false, returnPosition = false } = {}) {
  const copying=projectCopyForSource(projectId);
  if(copying){openProjectCopyOperation(copying);return null;}
  const local=state.editingPositions,owner=local ? {epoch:local.epoch,projectId,returnPosition,installing:false} : null;
  captureEditingPosition();
  if(local){local.loading=owner;if(local.timer!==null)clearTimeout(local.timer);local.timer=null;}
  const previousView=state.projectViewToken,previousProject=state.project?.id;
  try {
  pauseAllMedia();
  if (!skipFlush && !(await flushCurrentProjectSaves())) return null;
  if(previousView!==state.projectViewToken || previousProject!==state.project?.id || local && local.loading!==owner)return null;
  captureEditingPosition(owner);
  await discardUntouchedProject(projectId);
  if(previousView!==state.projectViewToken || local && local.loading!==owner)return null;
  const viewToken = ++state.projectViewToken;
  if (state.studio.open) setAdvanced(false);
  try {
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (viewToken !== state.projectViewToken) return null;
    const copy=observeProjectCopy(payload.project);
    if(payload.project?.project_copy!=null && !copy)throw new Error("This project's copy state could not be verified. Keep the source closed and check copy status before editing.");
    if(copyOperationActive(copy)){openProjectCopyOperation(copy);return null;}
    state.project = payload.project;
    if(state.audioSourceNotice)clearAudioSourceNotice();
    rememberProjectRevision(state.project);
    localStorage.setItem(lastProjectStorageKey(), projectId);
    localStorage.removeItem("cutroom-last-project");
    showWorkspace();
    if(owner)owner.installing=true;
    try{hydrateProject();}finally{if(owner)owner.installing=false;}
    const recovery=recoverActiveJobs(projectId, viewToken).catch((error) => {console.warn("Could not restore active jobs",error);return false;});
    if(returnPosition && await recovery===true)await restoreEditingPosition(owner,state.project);
    if(viewToken!==state.projectViewToken || state.project?.id!==projectId)return null;
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
  } finally {
    if(local?.loading===owner)local.loading=null;
  }
}

async function importIntoEmptyManualEditor(file, {shouldContinue = () => true} = {}) {
  if(retainedEditStatus())throw new Error(retainedEditIssue());
  const projectId = state.project?.id;
  if (!projectId || state.project.settings?.workflow !== "manual" || state.project.draft) return false;
  if (!shouldContinue()) return true;
  if (state.project.sources?.A) {
    await openManualDraft();
    // A file picked for an existing recording becomes additional media only
    // after a timeline exists, never an accidental replacement of that source.
    return state.project?.id !== projectId || !state.project.draft;
  }
  if (!String(file.type || "").startsWith("video/") && !/\.(mp4|mov|mkv|webm|avi|m4v|mpg|mpeg|mts|m2ts|ts|wmv|flv)$/i.test(file.name || "")) {
    throw new Error("Start with a video recording. You can add audio, images and more video after the first import.");
  }
  const imported = await uploadSource("A", file, {prepareInForeground:true, shouldContinue});
  // Assets cannot be admitted while the first recording is still preparing.
  // Wait through the existing cancellable job path before advancing a batch.
  if (imported?.preparation_deferred && shouldContinue()) {
    throw new Error("The recording is saved, but preview preparation was deferred. Wait for preparation or retry it before importing the remaining files.");
  }
  if (imported?.job && shouldContinue() && state.project?.id === projectId) {
    await pollJob(imported.job.id, {projectId, silent:true, refreshAudio:true, slot:"A"});
  }
  return true;
}

function showEmptyManualEditor() {
  if (!state.project || state.project.draft || (state.project.settings?.workflow !== "manual" && !retainedEditStatus())) return false;
  pauseAllMedia();
  setStep(3);
  elements.setupPanel.hidden = true;
  elements.analysisPanel.hidden = true;
  elements.resultPanel.hidden = false;
  setupPreviewSources();
  state.mediaStudio?.render();
  state.textStudio?.render();
  renderDirectorOutcomeNotice();
  renderReelCandidates();
  state.timeline?.setProject(editorProject());
  renderManualControls();
  setAdvanced(true);
  selectAdvancedTab("timeline");
  elements.advancedPanel?.workbenchController?.setMediaPoolVisible(true, false);
  updateStudioStatus();
  return true;
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
  elements.projectName.value = projectLabel(state.project);
  renderSources();
  hydrateSettings();
  if (state.project.draft) showResult();
  else if (!showEmptyManualEditor()) showSetup();
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
  const savedDuration=Number(settings.target_duration ?? 60);
  const validDuration=Number.isFinite(savedDuration) && savedDuration>=8 && savedDuration<=86400 ? savedDuration : 60;
  elements.targetDuration.min=8;
  elements.targetDuration.step="any";
  elements.targetDuration.max = Math.max(15, validDuration, Math.ceil(Math.min(600, state.project.sources?.A?.duration || 180)));
  elements.durationMode.value = settings.duration_mode || "style";
  updateDurationControl(validDuration);
  if (elements.durationGroup) elements.durationGroup.dataset.longform = "false";
  syncLongformDuration(settings.goal || "short");
  elements.directorInstruction.value = settings.instruction || "";
  if (elements.sourceContext) elements.sourceContext.value = settings.source_context || "";
  renderDirectorInstruction();
  if (elements.allowExtractiveRoughCut) elements.allowExtractiveRoughCut.checked = settings.allow_extractive_rough_cut === true;
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
  state.colorMotion?.render();
  elements.captionsToggle.checked = Boolean(settings.captions);
  setCaptionBurnEnabled(settings.burn_captions !== false, false);
  elements.captionStyleSelect.value = optionExists(elements.captionStyleSelect, settings.caption_style) ? settings.caption_style : CAPTION_DEFAULTS.style;
  elements.captionPositionSelect.value = optionExists(elements.captionPositionSelect, settings.caption_position) ? settings.caption_position : CAPTION_DEFAULTS.position;
  elements.captionScale.value = clampInteger(settings.caption_scale, 75, 150, CAPTION_DEFAULTS.scale);
  elements.captionWordsPerLine.value = clampInteger(settings.caption_words_per_line, 2, 12, CAPTION_DEFAULTS.words);
  elements.spokenLanguageSelect.value = optionExists(elements.spokenLanguageSelect, settings.spoken_language) ? settings.spoken_language : "auto";
  elements.performanceModeSelect.value = optionExists(elements.performanceModeSelect, settings.performance_mode) ? settings.performance_mode : "auto";
  if (elements.visualAiSelect) elements.visualAiSelect.value = optionExists(elements.visualAiSelect, settings.visual_ai) ? settings.visual_ai : "auto";
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
  if (elements.previewCaption && !elements.previewCaption.hasAttribute?.("data-caption-cue")) {
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
  renderEditStyleNote(normalized);
  if (elements.durationGroup) elements.durationGroup.hidden = ["youtube", "clean"].includes(normalized) && !longformGameplaySelected(normalized);
  syncLongformDuration(normalized);
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
  const audio_cleanup = applyAudioPreset(defaults.audio);
  elements.autoReframe.checked = defaults.reframe;
  elements.effectsToggle.checked = !["youtube", "clean"].includes(normalized);
  if (normalized === "short" && !elements.burnCaptionsToggle.dataset.touched) setCaptionBurnEnabled(true);
  if (normalized === "youtube" && !elements.burnCaptionsToggle.dataset.touched) setCaptionBurnEnabled(false);
  return { goal: normalized, aspect: defaults.aspect, layout: defaults.layout, pace: defaults.pace,
    audio_cleanup, auto_reframe: defaults.reframe, editorial_effects: elements.effectsToggle.checked,
    ...(["short", "youtube"].includes(normalized) && !elements.burnCaptionsToggle.dataset.touched ? { burn_captions: captionBurnEnabled() } : {}) };
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
  const families = styleFamilies();
  if (styles.length) {
    const fragment = document.createDocumentFragment();
    if (families.length) {
      // Five families; each card stands for its variants. Families that do not
      // fit the chosen goal are hidden unless the saved style lives there.
      const goal = currentGoalValue();
      const activeFamily = familyForStyle(selected);
      for (const family of families) {
        const isActive = family.id === activeFamily?.id;
        if (!isActive && Array.isArray(family.goals) && !family.goals.includes(goal)) continue;
        const value = isActive ? selected : family.default_style;
        fragment.append(renderStyleCard(editStyleById(value), { value, family, active: isActive }));
      }
      if (activeFamily && (activeFamily.variants || []).length > 1) fragment.append(renderStyleVariants(activeFamily));
    } else {
      for (const style of styles) fragment.append(renderStyleCard(style, { value: style.id }));
    }
    elements.editStyleChoices.replaceChildren(fragment);
  }
  const activeFamilyId = familyForStyle(selected)?.id;
  $$(`button[data-value]`, elements.editStyleChoices).forEach((button) => {
    const active = button.dataset.variant === "true" || !button.dataset.family
      ? button.dataset.value === selected
      : button.dataset.family === activeFamilyId;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
    button.tabIndex = active ? 0 : -1;
  });
  renderEditStyleNote();
  renderStyleRecommendation();
}

function styleFamilies() {
  return Array.isArray(state.system?.style_families) ? state.system.style_families : [];
}

function familyForStyle(styleId) {
  return styleFamilies().find((family) => (family.variants || []).some((variant) => variant.style === styleId)) || null;
}

function currentGoalValue() {
  return elements.goalChoices?.querySelector("button.active")?.dataset.value || state.project?.settings?.goal || "short";
}

function renderStyleCard(style, { value, family = null, active = false } = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "edit-style-card";
  button.dataset.value = value;
  button.dataset.category = style?.category || "general";
  if (family) button.dataset.family = family.id;
  button.setAttribute("role", "radio");
  const copy = document.createElement("span");
  const title = document.createElement("strong");
  const description = document.createElement("small");
  const badge = document.createElement("b");
  title.textContent = localizedStyleValue(family?.name || style?.name);
  description.textContent = localizedStyleValue(family?.description || style?.description);
  badge.textContent = localizedStyleValue(family?.badge || style?.badge);
  copy.append(title, description);
  if (!family) {
    const metadata = document.createElement("em");
    const pace = String(style.defaults?.pace || "balanced");
    metadata.textContent = `${pace[0].toUpperCase()}${pace.slice(1)} pacing`;
    copy.append(metadata);
  }
  const structure = (active || !family) ? style?.selection_policy?.story_structure : null;
  if (Array.isArray(structure) && structure.length) {
    const flow = document.createElement("small");
    flow.className = "style-story-flow";
    flow.textContent = structure.join(" → ");
    copy.append(flow);
  }
  button.append(copy, badge);
  return button;
}

function renderStyleVariants(family) {
  const row = document.createElement("div");
  row.className = "edit-style-variants";
  row.setAttribute("role", "radiogroup");
  row.setAttribute("aria-label", uiCopy("טעם", "Flavor"));
  const label = document.createElement("span");
  label.className = "edit-style-variants-label";
  label.textContent = uiCopy("טעם:", "Flavor:");
  row.append(label);
  for (const variant of family.variants) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "edit-style-variant";
    chip.dataset.value = variant.style;
    chip.dataset.variant = "true";
    chip.setAttribute("role", "radio");
    chip.textContent = localizedStyleValue(variant.label);
    chip.title = localizedStyleValue(editStyleById(variant.style)?.description);
    row.append(chip);
  }
  return row;
}

// Read-only advice from saved analysis: shown only when it differs from the
// current choice, and applied only when the user clicks it.
const styleRecommendationCache = new Map();
async function renderStyleRecommendation() {
  const host = elements.styleRecommendation;
  if (!host) return;
  const project = state.project;
  const hasEvidence = Boolean(project?.analysis?.segments?.length || project?.analysis?.visual_moments?.available);
  if (!project?.id || !hasEvidence) { host.hidden = true; return; }
  const goal = currentGoalValue();
  const key = `${project.id}:${project.revision}:${goal}`;
  let recommendation = styleRecommendationCache.get(key);
  if (recommendation === undefined) {
    styleRecommendationCache.set(key, null);
    try {
      const payload = await api(`/api/projects/${encodeURIComponent(project.id)}/style-recommendation?goal=${encodeURIComponent(goal)}`);
      recommendation = payload?.recommendation || null;
    } catch (_error) {
      recommendation = null;
    }
    styleRecommendationCache.set(key, recommendation);
  }
  const selected = state.selectedEditStyle || project.settings?.edit_style || "smart";
  if (!recommendation || recommendation.confidence === "low" || recommendation.style === selected || currentGoalValue() !== goal) {
    host.hidden = true;
    return;
  }
  const family = familyForStyle(recommendation.style);
  const variant = family && family.variants.length > 1 ? family.variants.find((item) => item.style === recommendation.style) : null;
  const label = [localizedStyleValue(family?.name), localizedStyleValue(variant?.label)].filter(Boolean).join(" · ")
    || localizedStyleValue(recommendation.name);
  const text = document.createElement("span");
  text.textContent = `${uiCopy("מומלץ לתוכן הזה:", "Suggested for this content:")} ${label}. ${localizedStyleValue(recommendation.reason)}`;
  const apply = document.createElement("button");
  apply.type = "button";
  apply.className = "style-recommendation-apply";
  apply.textContent = uiCopy("להחיל", "Use it");
  apply.addEventListener("click", () => chooseEditStyle(recommendation.style));
  host.replaceChildren(text, apply);
  host.hidden = false;
}

// Gameplay YouTube condenses a long recording: its length is minutes, not Short seconds.
const LONGFORM_PRESETS = Object.freeze([300, 480, 600, 900]);
function longformGameplaySelected(goal = elements.goalChoices?.querySelector("button.active")?.dataset.value || state.project?.settings?.goal) {
  return goal === "youtube" && (state.selectedEditStyle || state.project?.settings?.edit_style) === "gameplay_youtube";
}

function syncLongformDuration(goal) {
  if (!elements.targetDuration || !elements.durationGroup) return;
  const longform = longformGameplaySelected(goal);
  if (["youtube", "clean"].includes(goal)) elements.durationGroup.hidden = !longform;
  const buttons = $$(".quick-values button", elements.durationGroup);
  const wasLongform = elements.durationGroup.dataset.longform === "true";
  if (!longform && !wasLongform) return;
  elements.durationGroup.dataset.longform = String(longform);
  const sourceDuration = Number(state.project?.sources?.A?.duration || 0);
  if (longform) {
    if (!wasLongform) elements.targetDuration.dataset.shortMax = elements.targetDuration.max;
    elements.targetDuration.min = 60;
    elements.targetDuration.max = Math.max(120, Math.ceil(Math.min(3600, sourceDuration || 3600)));
    buttons.forEach((button, index) => {
      if (!button.dataset.shortSeconds) { button.dataset.shortSeconds = button.dataset.seconds; button.dataset.shortLabel = button.textContent; }
      const seconds = LONGFORM_PRESETS[index];
      button.hidden = seconds == null;
      if (seconds != null) { button.dataset.seconds = String(seconds); button.textContent = `${seconds / 60}m`; }
    });
    updateDurationControl(Number(elements.targetDuration.value) < 120 ? Math.min(600, Number(elements.targetDuration.max)) : Number(elements.targetDuration.value));
  } else {
    elements.targetDuration.min = 8;
    if (elements.targetDuration.dataset.shortMax) elements.targetDuration.max = elements.targetDuration.dataset.shortMax;
    buttons.forEach((button) => {
      if (button.dataset.shortSeconds) { button.dataset.seconds = button.dataset.shortSeconds; button.textContent = button.dataset.shortLabel; }
      button.hidden = false;
    });
    updateDurationControl(Number(elements.targetDuration.value));
  }
  if (typeof renderDurationPresets === "function") renderDurationPresets();
}

function renderEditStyleNote(goal = elements.goalChoices?.querySelector("button.active")?.dataset.value || state.project?.settings?.goal || "short") {
  syncLongformDuration(goal);
  const selected = state.selectedEditStyle || state.project?.settings?.edit_style || "smart";
  const style = editStyleById(selected);
  if (elements.editStyleNote) {
    const description = localizedStyleValue(style?.description);
    const evidence = uiCopy(
      "כל סגנון משנה את בחירת הרגעים והקצב. היעד, פורמט הפלט והאורך שבחרתם נשמרים. פריסת מסך + מצלמה לעולם לא מופעלת בלי אישור מפורש.",
      "Each style changes moment selection and pacing. Your goal, output format and duration stay selected. Screen + camera layout is never enabled without explicit confirmation.",
    );
    const goalNote = selected === "clean_vod" && goal === "short" ? t("cleanVodShortNote") : "";
    elements.editStyleNote.textContent = [goalNote, description, evidence].filter(Boolean).join(" ");
  }
}

function chooseEditStyle(styleId) {
  const settings = applyEditStyle(styleId, true);
  scheduleSettingsPatch({ requiresRebuild: true, reason: "edit_style", settings });
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
    return { edit_style: state.selectedEditStyle };
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
  if (defaults.caption_style && optionExists(elements.captionStyleSelect, defaults.caption_style)) elements.captionStyleSelect.value = defaults.caption_style;
  if (elements.burnCaptionsToggle) setCaptionBurnEnabled(defaults.burn_captions !== false);
  if (optionExists(elements.performanceModeSelect, defaults.performance_mode)) elements.performanceModeSelect.value = defaults.performance_mode;
  const audio_cleanup = defaults.audio_cleanup ? audioPresetSettings(defaults.audio_cleanup) : null;
  if (audio_cleanup) {
    hydrateAudioSettings(audio_cleanup);
    hydratePreAudioControls({ ...(reconcileProjectSnapshot(state.project)?.settings?.audio_cleanup || {}), ...audio_cleanup });
  }
  renderEditStyleChoices();
  renderAudioCalibration();
  if (announce) toast(uiCopy("סגנון העריכה הוחל. אפשר לשנות כל הגדרה לפני היצירה.", "Edit style applied. You can still tune every setting before generation."), "success");
  return { edit_style: state.selectedEditStyle, pace: defaults.pace || "balanced",
    ...(longformGameplaySelected(goal) ? { target_duration: Number(elements.targetDuration.value) } : {}),
    auto_reframe: elements.autoReframe.checked, editorial_effects: elements.effectsToggle.checked,
    captions: elements.captionsToggle.checked, burn_captions: captionBurnEnabled(),
    ...(optionExists(elements.layoutSelect, defaults.layout) ? { layout: defaults.layout } : {}),
    ...(optionExists(elements.performanceModeSelect, defaults.performance_mode) ? { performance_mode: defaults.performance_mode } : {}),
    ...(defaults.caption_style && optionExists(elements.captionStyleSelect, defaults.caption_style) ? { caption_style: defaults.caption_style } : {}),
    ...(audio_cleanup ? { audio_cleanup } : {}) };
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

function audioPresetSettings(audio = {}) {
  const preset = Object.hasOwn(AUDIO_PRESETS, audio.preset) ? audio.preset : "clean";
  // Presets define only these controls. Automatic threshold and custom target
  // loudness survive unless the chosen style explicitly supplies those fields.
  return { ...AUDIO_PRESETS[preset], ...audio, preset };
}

function applyAudioPreset(name) {
  const settings = audioPresetSettings({ preset: name });
  hydrateAudioSettings(settings);
  return settings;
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
  renderDurationPresets();
}

function durationPresetIssue(value, busy = Boolean(foregroundBusy() || state.directorRequestPending || state.requestReviewBusy)) {
  if (busy) return "Wait for the current request to finish.";
  const min = Number(elements.targetDuration.min || 8);
  const max = Number(elements.targetDuration.max || 180);
  if (!Number.isFinite(value) || value < min || value > max) return `Available request length: ${min} to ${max} seconds.`;
  return "";
}

function renderDurationPresets(busy = Boolean(foregroundBusy() || state.directorRequestPending || state.requestReviewBusy)) {
  $$(".quick-values button").forEach((button) => {
    const seconds = Number(button.dataset.seconds);
    const issue = durationPresetIssue(seconds, busy);
    button.disabled = Boolean(issue);
    button.title = issue || `Request ${seconds} seconds`;
    button.classList.toggle("active", seconds === Number(elements.targetDuration.value));
  });
}

function chooseDurationPreset(value) {
  // Recheck the native button's bounds/busy state at dispatch as well. A labeled
  // preset must never save a different clamped duration after a project change.
  if (durationPresetIssue(value)) { renderDurationPresets(); return false; }
  updateDurationControl(value);
  scheduleSettingsPatch({ requiresRebuild: true, reason: "duration" });
  return true;
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
    if (upload?.phase === "sending") uploadProgress.setAttribute("aria-valuenow", String(Math.round(uploadValue * 100)));
    else uploadProgress.removeAttribute("aria-valuenow");
    uploadProgress.setAttribute("aria-valuetext", upload ? uploadStatusText(upload) : "");
    $("span", uploadProgress).style.transform = `scaleX(${uploadValue})`;
    $("b", uploadProgress).textContent = upload ? uploadStatusText(upload) : "";
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
  renderUploadStorage();
  renderAudioCalibration();
  renderSourceMixer();
  if (state.project?.draft) {
    renderCameraDetection();
    renderDraftWarning();
  }
}

function editorAiRequestContext() {
  return Boolean(state.studio.open && document.getElementById("advancedPanel")?.dataset.aiRequestContext === "editor");
}

async function startDirectorAction() {
  if(retainedEditStatus())return resumeRetainedEdit();
  if (!editorAiRequestContext() && state.project?.settings?.workflow === "manual") return openManualDraft();
  return generateDraft();
}

function renderEditorAiRequest() {
  if (!editorAiRequestContext()) return;
  const recovery=retainedEditStatus();
  const title=elements.generateButton?.querySelector('[data-i18n="makeEdit"]');
  const note=elements.generateButton?.querySelector('[data-i18n="oneDraft"]');
  if(title)title.textContent=recovery ? "Resume retained edit" : "Review AI request";
  if(note)note.textContent=recovery ? "Keep the saved timeline · No AI processing" : state.project?.draft ? "Generate a separate proposal · Apply only after review" : "Check the request before generation";
  const status=document.getElementById("workbenchAIRequestStatus");
  if(status){
    const settings=state.project?.settings || {};
    const goal={short:"Short / Reel",youtube:"YouTube",podcast:"Conversation",clean:"Full clean-up"}[settings.goal] || settings.goal || "Short / Reel";
    const message=recovery ? (recovery.issue || "Resume the retained timeline before requesting AI. Existing layers and settings stay; unavailable old analysis and history are not recreated.") : `Source A · ${goal} · ${settings.edit_style || "smart"}. `
      +(state.project?.draft ? "Current edit stays in use; review source-cut proposals before Apply. " : "Generation makes the first draft. ")
      +"Uses configured AI; model setup or provider charges may apply.";
    if(status.textContent!==message)status.textContent=message;
  }
}

function directorRenderState(project) {
  return aiDraftStamp({sources:project?.sources,settings:project?.settings,manual:project?.manual,draft:project?.draft,analysis:project?.analysis,name:project?.name});
}

function beginEditorDirectorSession(projectId,viewToken) {
  if(!editorAiRequestContext() || !state.project?.draft)return null;
  const session={projectId,viewToken,renderState:directorRenderState(state.project)};
  state.editorDirectorSession=session;
  return session;
}

function keepEditorAfterDirector(project) {
  const session=state.editorDirectorSession;
  if(!session || !state.studio.open || state.project?.id!==session.projectId || project?.id!==session.projectId
    || state.projectViewToken!==session.viewToken || directorRenderState(project)!==session.renderState)return false;
  // An isolated proposal changes revision/provenance, not playback content. Do
  // not tear down decoded players or reset the selected occurrence/playhead.
  state.project=project;
  rememberProjectRevision(project);
  loadDraftRebuildState(project);
  state.timeline?.setProject(editorProject());
  renderAiDraftNotice();
  renderDirectorOutcomeNotice();
  renderReadiness();
  return true;
}

function renderReadiness() {
  state.manualTranscriptionControls?.();
  renderLayerTrackControls();
  renderPreviewAvailability();
  renderProjectSaveState();
  state.chromaStudio?.render();
  renderProjectSaveState();
  state.mediaStudio?.updateImportAvailability?.();
  state.mediaStudio?.syncSourceMonitor?.();
  state.sourceReview?.sync?.();
  state.timeline?.rangeImpact?.refresh();
  state.timeline?.navigation?.sync?.();
  state.textStudio?.updateTrimAvailability?.();
  state.textStudio?.updateDuplicateAvailability?.();
  state.textStudio?.updateMoveAvailability?.();
  state.textStudio?.updateEnabledAvailability?.();
  state.textStudio?.updateProtectionAvailability?.();
  renderAiDraftNotice();
  if (!elements.readiness) return;
  const source = state.project?.sources?.A;
  const ready = Boolean(source);
  const audioSlot = sourceMixerSettings().audioSlot;
  const selectedAudioSource = state.project?.sources?.[audioSlot];
  const audioMeasured = state.project?.settings?.workflow === "manual" || !selectedAudioSource?.has_audio || Boolean(preAudioProfile());
  const instructionValid = String(elements.directorInstruction?.value || "").length <= DIRECTOR_INSTRUCTION_LIMIT;
  const recovery=retainedEditStatus();
  const manualReady = state.project?.settings?.workflow === "manual" && !editorAiRequestContext();
  const trackIssue=retainedEditIssue() || savedLayerTrackIssue();
  const directorReady = recovery ? recovery.available : !trackIssue && (manualReady || (ready && audioMeasured && instructionValid));
  const busy = Boolean(foregroundBusy() || state.retainedResumePending || state.directorRequestPending || state.requestReviewBusy);
  elements.readiness.classList.toggle("ready", directorReady && !busy);
  elements.fpsSelect.disabled = busy;
  elements.exportFpsSelect.disabled = busy;
  const readinessMessage = recovery ? (busy ? "Resuming or saving changes. Please wait." : recovery.issue || "Ready to resume the saved timeline. No AI processing.") : trackIssue || (busy ? "Working — please wait." : !ready ? t("waitingForVideo") : !audioMeasured ? t("measuringAudio") : !instructionValid ? "Shorten the director instruction to 8,000 characters." : editorAiRequestContext() ? "Ready to review a new AI request" : t("ready"));
  const readinessText = $("p", elements.readiness);
  if (readinessText.textContent !== readinessMessage) readinessText.textContent = readinessMessage;
  elements.generateButton.disabled = !directorReady || busy;
  for(const control of [elements.directorInstruction,elements.targetDuration,elements.durationMode,elements.allowExtractiveRoughCut]){
    if(control)control.disabled=busy || Boolean(recovery);
  }
  renderDurationPresets(busy);
  state.welcome?.updateProject(state.project);
  renderEditorAiRequest();
  const renderDisabled = !state.project?.draft || !hasTimelineFootage() || busy || exportRequiresDraftRebuild();
  [elements.renderButton, elements.resultRenderButton, elements.studioRenderButton].forEach((button) => {
    if (button) button.disabled = renderDisabled;
    renderLayerTrackExportIssue(button,trackIssue);
  });
  if (elements.confirmExport && !elements.exportActions.hidden) elements.confirmExport.disabled = busy;
  renderDraftActions();
  renderManualControls();
  renderActiveJobBar();
  renderModelStatus();
}

function uploadStartBlocked(projectId, slot) {
  if(projectCopyFileBusy())return true;
  if(state.retainedResumePending?.projectId===projectId)return true;
  if (activeUploadForSlot(slot, projectId)) return true;
  if (state.activeJob || state.manualEditBusy || state.sourceSyncPending || state.sourceMixerSavePending) return true;
  return [...state.jobStartLocks].some((key) => !String(key).startsWith("upload:"));
}

async function uploadSource(slot, file, {prepareInForeground = false, shouldContinue = () => true} = {}) {
  const validationError = validateUploadFile(file);
  if (validationError) {
    toast(validationError);
    elements[`sourceInput${slot}`].value = "";
    return;
  }
  if (!state.project) await createProject();
  if (!state.project) return;
  const projectId = state.project.id;
  const viewToken = state.projectViewToken;
  if (!(await flushCurrentProjectSaves())) return;
  if (state.project?.id !== projectId || state.projectViewToken !== viewToken || !shouldContinue()) return;
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
    purpose: "source",
    fileName: file.name,
    phase: "checking",
    progress: 0,
    cancelRequested: false,
    cancelConfirmed: false,
    cancelPromise: null,
    cancelError: null,
    xhr: null,
  };
  const uploadKey = uploadStateKey(projectId, slot);
  let imported = null;
  state.activeUploads.set(uploadKey, uploadState);
  const container = elements[`sourceSlot${slot}`];
  const progress = $(".source-upload", container);
  const bar = $("span", progress);
  const label = $("b", progress);
  progress.hidden = false;
  container.setAttribute("aria-busy", "true");
  progress.setAttribute("aria-valuenow", "0");
  bar.style.transform = "scaleX(0)";
  label.textContent = uploadStatusText(uploadState);
  renderReadiness();
  try {
    const payload = await uploadWithProgress(`/api/projects/${encodeURIComponent(projectId)}/sources/${slot}`, file, uploadToken, (value) => {
      if (state.activeUploads.get(uploadKey) !== uploadState) return;
      uploadState.progress = Math.max(0, Math.min(1, Number(value) || 0));
      if (state.project?.id === projectId) {
        bar.style.transform = `scaleX(${value})`;
        label.textContent = uploadStatusText(uploadState);
        progress.setAttribute("aria-valuetext", uploadStatusText(uploadState));
        if (uploadState.phase === "sending") progress.setAttribute("aria-valuenow", String(Math.round(uploadState.progress * 100)));
        else progress.removeAttribute("aria-valuenow");
      }
      renderActiveJobBar();
    }, (xhr) => {
      uploadState.xhr = xhr;
      if (uploadState.cancelRequested) xhr.abort();
    }, uploadState);
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
    if (uploadState.cancelRequested) {
      await uploadState.cancelPromise;
      return;
    }
    rememberProjectRevision(authoritativeProject);
    if (!authoritativeProject?.draft) clearDraftRebuild(projectId);
    if (state.project?.id === projectId) {
      state.project = reconcileProjectSnapshot(authoritativeProject);
      renderSources();
      hydrateSettings();
      if (state.project.settings?.workflow === "manual") {
        if (state.project.draft) showResult(); else showEmptyManualEditor();
      }
    }
    if (payload.job) {
      if (!prepareInForeground) monitorBackgroundJob(payload.job.id, { refreshAudio: true, projectId, slot });
    } else if (payload.preparation_deferred) {
      // The footage is already durable; retry only the lightweight background
      // preparation after the request/worker admission burst has settled.
      window.setTimeout(() => retrySourcePreparation(projectId, slot).catch(() => {}), 1200);
    }
    loadProjects().catch(() => {});
    loadSystem().catch(() => {});
    toast(`Ready: ${slot} · ${file.name}`, "success");
    imported = payload;
  } catch (error) {
    if (error?.name === "AbortError") {
      if (uploadState.cancelRequested) await uploadState.cancelPromise;
      else toast(t("localUploadInterrupted"));
    }
    else toast(`${t("uploadFailed")}: ${uploadFailureMessage(error, file)}`);
  } finally {
    const currentAttempt = state.activeUploads.get(uploadKey) === uploadState;
    if (currentAttempt) state.activeUploads.delete(uploadKey);
    if (currentAttempt && state.project?.id === projectId) {
      progress.hidden = true;
      container.removeAttribute("aria-busy");
      progress.setAttribute("aria-valuenow", "0");
    }
    if (currentAttempt) elements[`sourceInput${slot}`].value = "";
    renderReadiness();
  }
  if (state.project?.id === projectId) {
    renderSources();
    renderSourceMixer();
  }
  return imported;
}

function uploadAbortError() {
  const error = new Error(t("uploadCancelled"));
  error.name = "AbortError";
  return error;
}

function sendUploadChunk(url, chunk, offset, upload, onProgress, onRequest) {
  return new Promise((resolve, reject) => {
    if (upload.cancelRequested) { reject(uploadAbortError()); return; }
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.responseType = "json";
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    xhr.setRequestHeader("X-Cutroom-Upload-Token", upload.uploadToken);
    xhr.setRequestHeader("X-Cutroom-Upload-Offset", String(offset));
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && !upload.cancelRequested) onProgress(offset + Math.min(chunk.size, event.loaded));
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response);
      else reject(new ApiError(xhr.response?.message || `HTTP ${xhr.status}`, xhr.status, xhr.response?.error, xhr.response));
    });
    xhr.addEventListener("error", () => reject(new Error(t("localUploadInterrupted"))));
    xhr.addEventListener("abort", () => reject(uploadAbortError()));
    onRequest?.(xhr);
    if (upload.cancelRequested) { reject(uploadAbortError()); return; }
    xhr.send(chunk);
  });
}

async function uploadWithProgress(url, file, uploadToken, onProgress, onRequest = null, upload = null) {
  if(projectCopyFileBusy())throw new Error("Wait for the active project copy before importing media. Other saved edits remain available.");
  const route = url.match(/^\/api\/projects\/([^/]+)\/(?:sources\/([AB])|assets)$/);
  if (!route) throw new Error("Unsupported import destination");
  upload ||= { projectId: decodeURIComponent(route[1]), slot: route[2] || null, uploadToken, purpose: route[2] ? "source" : "asset" };
  const validationError = validateUploadFile(file);
  if (validationError) throw new Error(validationError);
  const notify = (phase, progress = upload.progress || 0) => {
    upload.phase = phase;
    upload.progress = Math.max(0, Math.min(1, progress));
    onProgress?.(upload.progress, upload);
  };
  let admitted = false;
  let committed = false;
  try {
    notify("checking", 0);
    const preflight = await api(`/api/projects/${route[1]}/uploads/preflight`, {
      method: "POST", body: JSON.stringify({ purpose: upload.purpose, slot: upload.slot || undefined,
        filename: file.name, size_bytes: file.size, upload_token: uploadToken }),
    });
    admitted = true;
    rememberUploadStorage(upload, preflight.storage_plan);
    if (preflight.upload_token !== uploadToken || !preflight.upload_url || !preflight.cancel_url) throw new Error("The import reservation did not match this upload attempt.");
    upload.cancelUrl = preflight.cancel_url;
    if (upload.cancelRequested) {
      // A stop may precede the admission reply. Release this reservation before
      // returning, without allowing the next chunk or finalization to start.
      await api(upload.cancelUrl, { method: "POST", body: "{}" });
      upload.cancelConfirmed = true;
      throw uploadAbortError();
    }
    const chunkSize = Number(preflight.chunk_size_bytes);
    if (!Number.isSafeInteger(chunkSize) || chunkSize <= 0) throw new Error("The import chunk size is invalid.");
    notify("sending", 0);
    for (let offset = 0; offset < file.size;) {
      if (upload.cancelRequested) throw uploadAbortError();
      const chunk = file.slice(offset, Math.min(file.size, offset + chunkSize));
      const result = await sendUploadChunk(preflight.upload_url, chunk, offset, upload,
        (sent) => notify("sending", sent / Math.max(1, file.size)), onRequest);
      const received = Number(result?.received_bytes);
      if (received !== offset + chunk.size) throw new Error("The server did not confirm the complete upload chunk.");
      offset = received;
      notify("sending", offset / Math.max(1, file.size));
    }
    if (upload.cancelRequested) throw uploadAbortError();
    notify("importing", 1);
    const result = await api(url, { method: "POST", body: "{}", headers: {
      "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": uploadToken,
    } });
    committed = true;
    if (upload.cancelRequested && upload.purpose === "asset") return { ...result, import_stop_too_late: true };
    if (upload.cancelRequested) throw uploadAbortError();
    return result;
  } catch (error) {
    rememberUploadStorage(upload, error?.payload?.storage_plan);
    if (admitted && !committed && upload.cancelUrl) {
      await api(upload.cancelUrl, { method: "POST", body: "{}" }).catch(() => {});
    }
    if (upload.cancelRequested) throw uploadAbortError();
    throw error;
  }
}

async function uploadMediaAsset(file, projectId, onStatus) {
  const uploadToken = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const upload = { projectId, purpose: "asset", uploadToken, fileName: file.name, progress: 0, phase: "checking", cancelRequested: false,
    cancelUrl: `/api/projects/${encodeURIComponent(projectId)}/uploads/${encodeURIComponent(uploadToken)}/cancel` };
  const key = `${projectId}:asset:${uploadToken}`;
  state.activeUploads.set(key, upload);
  const report = () => {
    if (state.project?.id === projectId) onStatus?.(uploadStatusText(upload), storagePlanText(upload.storagePlan));
    renderActiveJobBar();
  };
  renderReadiness();
  try {
    return await uploadWithProgress(`/api/projects/${encodeURIComponent(projectId)}/assets`, file, uploadToken, report,
      (xhr) => { upload.xhr = xhr; }, upload);
  } catch (error) {
    if (upload.cancelRequested) await upload.cancelPromise;
    report();
    if (error?.name === "AbortError") throw error;
    const formatted = new Error(uploadFailureMessage(error, file));
    formatted.cause = error;
    throw formatted;
  } finally {
    if (state.activeUploads.get(key) === upload) state.activeUploads.delete(key);
    renderReadiness();
  }
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
    upload.purpose === "asset" ? upload.cancelUrl
      : `/api/projects/${encodeURIComponent(upload.projectId)}/sources/${encodeURIComponent(upload.slot)}/uploads/${encodeURIComponent(upload.uploadToken)}/cancel`,
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
  if (upload.cancelConfirmed && upload.purpose !== "asset") toast(t("uploadCancelled"), "success", 2600);
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
    duration_mode: elements.durationMode?.value || "style",
    instruction: elements.directorInstruction.value.trim(),
    ...(elements.sourceContext ? { source_context: elements.sourceContext.value.trim() } : {}),
    output_count: state.project?.settings?.output_count ?? 1,
    source_continuity: state.project?.settings?.source_continuity || "unspecified",
    allow_extractive_rough_cut: elements.allowExtractiveRoughCut?.checked === true,
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
    ...(elements.visualAiSelect ? { visual_ai: elements.visualAiSelect.value } : {}),
    audio_cleanup: currentAudioSettings(),
  };
}

function scheduleSettingsPatch({ requiresRebuild = false, reason = "settings", settings = null } = {}) {
  // Reasons describe rebuild impact, not field ownership. Scalar request
  // controls have one unambiguous field; grouped/output/audio callers supply
  // their explicit patch. Never reconstruct a save from every hidden control.
  const requestFields = {
    "brief": () => ({ instruction: String(elements.directorInstruction.value || "").trim() }),
    "source context": () => ({ source_context: String(elements.sourceContext?.value || "").trim() }),
    "duration": () => ({ target_duration: Number(elements.targetDuration.value) }),
    "duration intent": () => ({ duration_mode: elements.durationMode.value }),
    "rough-cut fallback": () => ({ allow_extractive_rough_cut: elements.allowExtractiveRoughCut?.checked === true }),
    "pace": () => ({ pace: $("button.active", elements.paceChoices)?.dataset.value || "balanced" }),
    "language": () => ({ spoken_language: elements.spokenLanguageSelect.value }),
    "performance": () => ({ performance_mode: elements.performanceModeSelect.value }),
    "visual_ai": () => ({ visual_ai: elements.visualAiSelect.value }),
  };
  const patch = settings ?? requestFields[reason]?.();
  if (!isPlainObject(patch) || !Object.keys(patch).length) {
    console.error("Settings save rejected: no explicit fields were supplied.");
    return false;
  }
  if (requiresRebuild && state.project?.draft) markDraftRebuild(reason);
  schedulePatch({ settings: patch });
  return true;
}

function directorRequestSettings() {
  const controls=currentSettings();
  const saved=reconcileProjectSnapshot(state.project)?.settings || {};
  // Save flush precedes this snapshot. Explicitly changed request fields are in
  // saved settings now; unedited slider clamps and rounded audio UI are not.
  return Object.fromEntries(Object.entries(controls).map(([key,value])=>[key,
    Object.hasOwn(saved,key) && saved[key]!==undefined ? JSON.parse(JSON.stringify(saved[key])) : value]));
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

// Settings, inspector autosaves and explicit effect/caption drafts share one
// truthful indicator. Persisted AI preferences are not unsaved edit changes.
function pendingChromaDrafts() {
  const tool=state.chromaStudio;
  if(!state.project?.id || tool?.projectId!==state.project.id)return [];
  return tool.pendingDrafts?.() || [...(tool.drafts?.keys?.() || [])].filter(slot=>tool.dirty?.(slot)).map(slot=>({slot,label:slot,issue:""}));
}

function explicitPendingDraft() {
  if(state.captionDirty)return {target:"caption",detail:"Save the caption changes or press Escape in the caption text before leaving. Your text is still here."};
  const rows=pendingChromaDrafts();
  if(rows.length)return {target:"chroma",slot:rows[0].slot,detail:rows[0].issue || `Chroma Key has unapplied changes for ${rows.length} video${rows.length===1 ? "" : "s"}. Apply or Discard changes in Effects before leaving. Saved playback and export are unchanged.`};
  if(typeof trackLevelUnfinished==="function" && trackLevelUnfinished())return {target:"track-level",detail:state.mediaStudio?.trackLevelGesture
    ? "Finish or cancel the track level adjustment before continuing. Its preview has not been saved."
    : "Finish the track gain value or press Escape in Track levels. The typed value is still here and has not been saved."};
  return null;
}

function projectSaveStatus() {
  const id=state.project?.id;
  const batch=state.transcriptBatches?.get(id), batchStatus=batch?.protocol?.snapshot();
  if(batch && (batch.loading || batchStatus?.pending || batchStatus?.canCheck || batch.savedReload > state.project?.revision))return {kind:batchStatus?.pending || batch.loading ? "saving" : "error",label:batchStatus?.pending || batch.loading ? "Transcript save pending" : "Check transcript save",detail:transcriptBatchStatus(batch),target:"transcript",actionable:!batchStatus?.pending && !batch.loading};
  const settling=previewRepairSettling(id);
  const repairing=state.previewRepairs?.active?.(id)?.find(entry=>entry.status!=="preparing") || (settling ? {status:"running",asset_id:settling.assetId} : null);
  if(repairing)return {kind:"saving",label:repairing.status==="unknown" ? "Check preview repair" : "Verifying preview",detail:"Imported preview maintenance is in progress. Open its Media pool status to check or cancel; the original and timeline are not replaced.",target:"preview-repair",assetId:repairing.asset_id,actionable:true};
  const copying=projectCopyForSource(id);
  if(copying && copying.status!=="preparing")return {kind:"saving",label:copying.status==="unknown" ? "Checking copy" : "Copying saved project",detail:copyStatusText(copying),target:"copy",actionable:true};
  if(!id)return {kind:"saved",label:"Saved",detail:"No project changes are pending.",actionable:false};
  const queue=state.saveQueues.get(id), explicit=explicitPendingDraft(), media=state.mediaStudio, text=state.textStudio;
  const transcript=[...state.transcriptBuffers.values()].some(row=>row.projectId===id);
  const error=queue?.error ? {target:"settings",detail:`Settings were not saved: ${queue.error}. Activate to retry this queued save.`}
    : media?.projectId===id && media.saveError ? {target:media.saveErrorTarget==="track-level"?"track-level":"media",detail:media.saveError}
    : text?.projectId===id && text.saveError ? {target:"text",detail:text.saveError}
    : state.chromaStudio?.projectId===id && state.chromaStudio.saveError ? {target:"chroma",slot:pendingChromaDrafts()[0]?.slot,detail:state.chromaStudio.saveError}
    : state.embeddedEditor?.projectId===id && state.embeddedEditor.error ? {target:"framing",detail:"Camera framing was not saved. Review the retained layout and Retry save in Framing."} : null;
  const saving=Boolean(queue?.inFlight || state.manualEditBusy || state.manualEditPromise || state.captionContextSave
    || state.transcriptSaving || media?.saving || text?.saving || state.chromaStudio?.saving
    || state.sourceMixerSavePending || state.sourceSyncPending || state.embeddedEditor?.saving || (liveEmbeddedCameraRequest() && !state.embeddedEditor.error));
  if(error)return {kind:"error",label:"Save failed",...error,detail:error.detail+(explicit ? ` ${explicit.detail}` : ""),actionable:!saving};
  if(explicit)return {kind:"unsaved",label:"Unsaved changes",...explicit,detail:(saving ? "Other changes are saving. " : "")+explicit.detail,actionable:!saving};
  if(saving)return {kind:"saving",label:"Saving…",detail:"Saving project changes. Keep this page open until saving finishes.",actionable:false};
  if(queue?.pending || queue?.timer)return {kind:"saving",label:"Saving…",detail:"Project settings are queued to save.",actionable:false};
  if(text?.pending?.size)return {kind:"unsaved",label:"Unsaved changes",detail:"Text changes are not saved yet. Open the text inspector to review or retry them.",target:"text",actionable:true};
  if(media?.pending?.size)return {kind:"saving",label:"Saving…",detail:"Media or mixer changes are queued to save.",actionable:false};
  if(transcript)return {kind:"unsaved",label:"Unsaved changes",detail:"Transcript changes are not saved yet. Open the transcript to Save or Discard them.",target:"transcript",actionable:true};
  if(state.embeddedEditor?.projectId===id && state.embeddedEditor.dirty)return {kind:"unsaved",label:"Unsaved changes",detail:"Camera framing changes are not saved yet. Review them in Framing.",target:"framing",actionable:true};
  return {kind:"saved",label:"Saved",detail:"All current project changes are saved. Unapplied AI proposals remain separate from the edit.",actionable:false};
}

function renderProjectSaveState() {
  state.trackLift?.sync();state.mediaStudio?.clipOpacity?.refresh();
  // Local drafts and save transitions can change header readiness while paused.
  // Use the existing coalesced draw, never a polling loop or saved-state change.
  state.timeline?.scheduleDraw?.();
  state.markedLayers?.sync();
  state.mediaStudio?.updatePreviewRepairControls?.();
  state.mediaStudio?.updateMediaUsageAvailability?.();
  state.mediaStudio?.updateAudioSourceAvailability?.();
  state.transcriptSectionsUI?.refresh?.();
  renderLayerTrackControls();
  if(selectedLayerGroupIds().length)renderLayerGroupControls();
  if(state.sourceInsertSession && !elements.sourceInsertForm?.hidden)renderSourceInsert();
  const node=elements.saveState;
  if(!node)return;
  const status=projectSaveStatus();
  if(node.textContent!==status.label)node.textContent=status.label;
  if(node.dataset)node.dataset.saveState=status.kind;
  node.title=status.detail; node.disabled=!status.actionable;
  node.setAttribute?.("aria-label",`${status.label}. ${status.detail}`);
}

function revealPendingSave(status) {
  if(!status)return;
  // The project picker must not obscure the draft that blocked navigation.
  if(elements.projectsDialog?.open)elements.projectsDialog.close();
  if(elements.exportDialog?.open && !state.activeJob)elements.exportDialog.close();
  if(status.target==="track-level") {
    openStudioTab("audio");state.mediaStudio?.trackLevels?.focusDraft?.();
  } else if(status.target==="chroma") {
    openStudioTab("timeline"); selectEditTool("effects");
    const tool=state.chromaStudio;
    if(tool && status.slot) {tool.source.value=status.slot;tool.source.onchange();}
    tool?.node?.scrollIntoView?.({block:"nearest"});
    (tool?.apply?.disabled ? tool?.discard : tool?.apply)?.focus?.();
  } else if(status.target==="caption" || status.target==="transcript" || status.target==="text") {
    const recoveryOwner=status.target==="transcript" && transcriptBatchIssue() ? transcriptBatchOwner() : null;
    if(recoveryOwner) {
      if(!openStudioTab("transcript",{transcriptRecoveryOwner:recoveryOwner}))return;
    } else openStudioTab("transcript");
    if(status.target==="transcript") {
      const buffers=pendingTranscriptBuffers();
      const buffer=buffers.find(row=>String(row.id)===state.transcriptActive?.id) || buffers[0];
      if(buffer) {
        // Reveal the unsaved buffer, not an unrelated clean line. This is editor
        // navigation only: do not seek the timeline or save/discard any text.
        if(transcriptDraftReview(buffer))state.transcriptRecoveryActive={projectId:state.project.id,key:`${state.project.id}:${buffer.id}`};
        else {state.transcriptRecoveryActive=null;state.transcriptActive={projectId:state.project.id,id:String(buffer.id)};}
        renderTranscriptDetail();
      }
    }
    const node=status.target==="caption" ? elements.captionItemEditor : status.target==="text" ? state.textStudio?.inspector : elements.transcriptEditForm;
    let disclosure=node?.closest?.("details");
    while(disclosure) {disclosure.open=true;disclosure=disclosure.parentElement?.closest?.("details");}
    node?.scrollIntoView?.({block:"nearest"});
    if(status.target==="caption")elements.captionItemText?.focus?.();
    else if(status.target==="transcript")elements.transcriptEditText?.focus?.();
    else if(status.target==="text")state.textStudio?.root?.querySelector?.(".text-recovery [data-retry], [data-text=\"text\"]")?.focus?.();
  } else if(status.target==="media")openStudioTab("media");
  else if(status.target==="framing")openStudioTab("framing");
}

async function activateSaveStatus() {
  const status=projectSaveStatus(); if(!status.actionable)return;
  if(status.target==="copy"){openProjectCopyOperation(projectCopyForSource(state.project?.id));return;}
  if(status.target==="preview-repair"){openStudioTab("media");state.mediaStudio?.revealPreviewRepair?.(status.assetId);return;}
  if(status.target==="settings") {
    try{await flushProjectSaves(state.project.id);}catch(error){toast(`Save failed: ${error.message}`);}
    renderProjectSaveState(); return;
  }
  revealPendingSave(status);
}

function requireResolvedExplicitDrafts() {
  const pending=explicitPendingDraft();
  if(!pending)return true;
  toast(pending.detail);revealPendingSave(pending);renderProjectSaveState();return false;
}

function hasUnsavedProjectWork() {
  return Boolean(state.transcriptBatches?.size && transcriptBatchIssue() || trackLevelUnfinished() || state.captionDirty || state.captionContextSave || state.transcriptBuffers.size || state.transcriptSaving
    || pendingChromaDrafts().length || state.chromaStudio?.saving || state.mediaStudio?.pending?.size || state.mediaStudio?.saving
    || state.textStudio?.dirty?.() || state.manualEditBusy || state.manualEditPromise || state.sourceMixerSavePending || state.sourceSyncPending
    || liveEmbeddedCameraRequest() || (state.project?.id && state.embeddedEditor?.projectId===state.project.id && state.embeddedEditor.dirty)
    || [...state.saveQueues.values()].some(queue=>queue.pending || queue.timer || queue.inFlight));
}

function setSaveState(projectId, _value) {
  if(state.project?.id===projectId)renderProjectSaveState();
}

function schedulePatch(patch, { delay = 420 } = {}) {
  if(state.transcriptBatches?.size && transcriptBatchIssue()){toast(transcriptBatchIssue());renderReadiness();return Promise.resolve(null);}
  if(patch && Object.hasOwn(patch,"manual") && !requireResumedEdit())return Promise.resolve(null);
  const projectId = state.project?.id;
  if (!projectId) return Promise.resolve(null);
  const queue = saveQueueFor(projectId, state.project?.revision);
  queue.pending = mergePatchValues(queue.pending || {}, patch || {});
  queue.error = null;
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

  queue.error = null;
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
  renderProjectSaveState();
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
    queue.error = null;
    loadProjects().catch(() => {});
  } catch (error) {
    queue.pending = mergePatchValues(patch, queue.pending || {});
    queue.error = error.message || "The save request failed.";
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
    renderProjectSaveState();
    // Accepted snapshots carry a new saved subtitle scene. Refresh paused captions
    // without seeking/rebuilding the viewer or disturbing another project's view.
    if (state.project?.id === projectId && state.captionPreview) updatePreviewCaption(previewPlaybackTime());
  }
  if (retryAfterConflict) return flushProjectSaves(projectId);
  return queue.pending ? flushProjectSaves(projectId) : null;
}

function isRevisionConflict(error) {
  return Number(error?.status) === 409 && error?.code === "revision_conflict";
}

async function flushCurrentProjectSaves() {
  const projectId=state.project?.id, viewToken=state.projectViewToken;
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken;
  if(!requireResolvedExplicitDrafts())return false;
  try {
    if(state.textStudio && !(await state.textStudio.flush()))return false;
    if(!current() || !requireResolvedExplicitDrafts())return false;
    if(state.mediaStudio && !(await state.mediaStudio.flush()))return false;
    if(!current() || !requireResolvedExplicitDrafts())return false;
    if(!projectId)return true;
    if(!(await saveTranscriptBuffers(true)) || !current())return false;
    if(state.manualEditPromise)await state.manualEditPromise;
    if(!current() || !requireResolvedExplicitDrafts())return false;
    if(state.sourceMixerSavePending)await state.sourceMixerSaveTail;
    if(!current())return false;
    await flushPendingSourceSync(projectId);
    if(!current())return false;
    if(!(await flushEmbeddedCameraSave(projectId)) || !current())return false;
    await flushProjectSaves(projectId);
    return current() && requireResolvedExplicitDrafts();
  } catch(error) {
    toast(`${uiCopy("השמירה נכשלה", "Save failed")}: ${error.message}`);return false;
  } finally { renderProjectSaveState(); }
}

function foregroundBusy({ transcriptRecoveryOwner = null } = {}) {
  const owner = transcriptRecoveryOwner, snapshot = owner?.protocol?.snapshot();
  const recovery = Boolean(owner && state.transcriptBatches?.get(state.project?.id) === owner
    && !owner.loading && !state.transcriptSaving && !snapshot?.pending
    && (snapshot?.canCheck || owner.savedReload > state.project?.revision));
  return Boolean(!recovery && state.transcriptBatches?.size && transcriptBatchIssue()) || previewRepairBusy() || projectCopySourceBusy() || Boolean(state.activeJob || state.activeUploads.size || state.mediaStudio?.uploading || state.stabilizationStudio?.uploading || state.manualEditBusy || state.sourceSyncPending || state.sourceMixerSavePending) || state.jobStartLocks.size > 0;
}

function projectHasForegroundWork(projectId) {
  if (!projectId) return false;
  if(previewRepairBusy(projectId) || projectCopySourceBusy(projectId))return true;
  if(state.retainedResumePending?.projectId===projectId)return true;
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
  if (kind === "manual_transcript") return uiCopy("תמלול מקומי", "Local transcription");
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
    message: uploads.map((upload) => `${upload.slot || "Media"}: ${uploadStatusText(upload)} · ${upload.fileName}`).join(" + "),
  } : null;
  const snapshot = job || uploadSnapshot || state.activeJobSnapshot;
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
  if (foregroundBusy() || projectCopyFileBusy() || state.jobStartLocks.has(key)) return null;
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

async function reconcileDirectorOutcome(projectId, error, { cancelled = false, viewToken = state.projectViewToken } = {}) {
  if (state.project?.id !== projectId || state.projectViewToken !== viewToken) return false;
  try {
    const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken || !latest?.project) return false;
    if(Number(latest.project.revision)<Number(state.project.revision))return false;
    state.project = reconcileProjectSnapshot(latest.project);
    rememberProjectRevision(state.project);
  } catch (_refreshError) {
    // The in-memory Draft is still authoritative enough to render if a refresh
    // races with a short local-server restart.
  }
  if (state.project?.id !== projectId || state.projectViewToken !== viewToken) return false;
  if (state.project?.draft) {
    if (!cancelled) state.directorOutcome = directorOutcomeDescription(error);
    if(!keepEditorAfterDirector(state.project))hydrateProject();
    if (!cancelled) toast(`${state.directorOutcome.title}: ${state.directorOutcome.message}`, "info", 6500);
    return true;
  }
  if (cancelled) showSetup();
  else showAnalysisError(error);
  return false;
}

async function generateDraft() {
  if(!requireResumedEdit())return false;
  if(!requireCompatibleLayerTracks())return false;
  if(state.directorRequestPending || state.requestReviewBusy || foregroundBusy() || !state.project)return false;
  if(!requireResolvedExplicitDrafts())return false;
  const projectId=state.project.id,viewToken=state.projectViewToken;
  const preserveCurrentEdit=Boolean(state.project.draft && (state.project.manual?.sequence || editorAiRequestContext()));
  state.directorRequestPending=true;
  renderReadiness();
  try { return await generateDraftRequest(projectId,viewToken,preserveCurrentEdit); }
  finally { state.directorRequestPending=false;renderReadiness(); }
}

async function generateDraftRequest(projectId,viewToken,preserveCurrentEdit=false) {
  if(!requireResumedEdit())return false;
  if(!requireCompatibleLayerTracks())return false;
  if (String(elements.directorInstruction?.value || "").length > DIRECTOR_INSTRUCTION_LIMIT) {
    renderDirectorInstruction();
    toast("Shorten the director instruction to 8,000 characters.");
    elements.directorInstruction?.focus();
    return;
  }
  if (!(await flushCurrentProjectSaves()) || state.project?.id!==projectId || state.projectViewToken!==viewToken) return false;
  if(state.cancelBeforeStart){state.cancelBeforeStart=false;return false;}
  if (!requireSavedTranscript() || !requireResolvedExplicitDrafts() || !requireCompatibleLayerTracks()) return false;
  if (!state.project?.sources?.A) {
    toast(t("waitingForVideo"));
    return;
  }
  if (liveEmbeddedCameraRequest()
    && (!(await flushEmbeddedCameraSave(projectId)) || state.project?.id !== projectId || state.projectViewToken !== viewToken)) return;
  if(state.requestReviewBusy || foregroundBusy())return;
  state.requestReviewBusy=true;
  let reviewed, reviewedRevision;
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if(state.project?.id!==projectId || state.projectViewToken!==viewToken)return;
    const revision=state.project.revision, originalSettings=JSON.stringify(directorRequestSettings());
    reviewedRevision=revision;
    pauseAllMedia();
    reviewed=await reviewEditingRequest({settings:directorRequestSettings(),styles:state.system?.edit_styles||[],projectId,revision,preserveCurrentEdit,
      isCurrent:()=>state.project?.id===projectId&&state.projectViewToken===viewToken&&state.project.revision===revision&&JSON.stringify(directorRequestSettings())===originalSettings,
      check:settings=>api(`/api/projects/${encodeURIComponent(projectId)}/director/request-review`,{method:"POST",body:JSON.stringify(settings)})});
  } catch(error){
    if(error.message==="Cancelled" && !state.activeJob)state.cancelBeforeStart=false;
    toast(error.message);return;
  }
  finally{state.requestReviewBusy=false;}
  if(!reviewed || state.project?.id!==projectId || state.projectViewToken!==viewToken)return;
  if(!requireResolvedExplicitDrafts() || !requireSavedTranscript())return false;
  const lock = acquireJobStartLock("director", projectId);
  if (!lock) {
    toast(t("directorBusy"));
    return;
  }
  const session=beginEditorDirectorSession(projectId,viewToken);
  pauseAllMedia();
  showAnalysis({keepEditor:Boolean(session)});
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken) throw new Error("Cancelled");
    if(state.project.revision!==reviewedRevision)throw new Error("The project changed after request review. Review again; the current edit was kept.");
    if(!requireResolvedExplicitDrafts() || !requireSavedTranscript() || !requireCompatibleLayerTracks())throw new Error("Resolve pending changes and review the request again.");
    const settings = reviewed;
    await ensureStoryAIReady(settings.goal);
    assertJobStartNotCancelled();
    if (state.project?.id !== projectId || state.projectViewToken !== viewToken) throw new Error("Cancelled");
    if(state.project.revision!==reviewedRevision)throw new Error("The project changed after request review. Review again; the current edit was kept.");
    if(!requireResolvedExplicitDrafts() || !requireSavedTranscript() || !requireCompatibleLayerTracks())throw new Error("Resolve pending changes and review the request again.");
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/director`, {
      method: "POST", headers: {"X-Cutroom-Reviewed-Revision": String(reviewedRevision), ...(preserveCurrentEdit ? {"X-Cutroom-Preserve-Edit":"1"} : {})},
      body: JSON.stringify(settings),
    });
    await pollJob(payload.job.id, { director: true, projectId });
  } catch (error) {
    if (state.project?.id === projectId && state.projectViewToken === viewToken) {
      await reconcileDirectorOutcome(projectId, error, { cancelled: error.message === "Cancelled" });
    }
  } finally {
    if (!state.activeJob) state.cancelBeforeStart = false;
    if(session && state.editorDirectorSession===session){
      state.editorDirectorSession=null;if(state.project?.id===projectId && state.projectViewToken===viewToken)elements.analysisPanel.hidden=true;
    }
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
  if(!requireCompatibleLayerTracks())return false;
  if(state.directorRequestPending || state.requestReviewBusy || foregroundBusy() || !state.project?.draft)return false;
  if(!requireResolvedExplicitDrafts() || !requireSavedTranscript())return false;
  if (state.draftDirtyReasons.size) { toast(t("rebuildBeforeRefine")); return; }
  if (command === "new_variation" && !canVaryDraft()) return;
  const projectId=state.project.id,viewToken=state.projectViewToken;
  const preserveCurrentEdit=Boolean(state.project.manual?.sequence || editorAiRequestContext());
  state.directorRequestPending=true;
  renderReadiness();
  let lock=null,session=null;
  try {
    if(!(await flushCurrentProjectSaves()) || state.project?.id!==projectId || state.projectViewToken!==viewToken)return false;
    if(!requireResolvedExplicitDrafts() || !requireSavedTranscript() || !requireCompatibleLayerTracks())return false;
    assertJobStartNotCancelled();
    const revision=state.project.revision;
    lock=acquireJobStartLock("director",projectId);
    if(!lock){toast(t("directorBusy"));return false;}
    session=beginEditorDirectorSession(projectId,viewToken);
    pauseAllMedia();
    showAnalysis({keepEditor:Boolean(session)});
    const previousCut=cutSelectionSignature(state.project.draft);
    assertJobStartNotCancelled();
    if(command==="new_variation")await ensureStoryAIReady("short");
    assertJobStartNotCancelled();
    if(state.project?.id!==projectId || state.projectViewToken!==viewToken || state.project.revision!==revision)throw new Error("The project changed. Review the current edit and retry.");
    if(!requireResolvedExplicitDrafts() || !requireSavedTranscript())throw new Error("Resolve pending changes and retry.");
    const payload=await api(`/api/projects/${encodeURIComponent(projectId)}/director/refine`, {
      method:"POST",headers:{"X-Cutroom-Reviewed-Revision":String(revision),...(preserveCurrentEdit ? {"X-Cutroom-Preserve-Edit":"1"} : {})},body:JSON.stringify({command})});
    const job=await pollJob(payload.job.id,{director:true,projectId,announceReady:command!=="new_variation"});
    if(command==="new_variation" && state.project?.id===projectId && state.projectViewToken===viewToken){
      const candidate=job?.result?.proposal_only ? job.result.draft : state.project.draft;
      const changed=job?.result?.variation_changed!==false && previousCut!==cutSelectionSignature(candidate);
      toast(t(changed ? "anotherCutReady" : "anotherCutUnchanged"),changed ? "success" : "info",4000);
    }
  } catch(error){
    if(state.project?.id===projectId && state.projectViewToken===viewToken)await reconcileDirectorOutcome(projectId,error,{cancelled:error.message==="Cancelled"});
  } finally {
    if(!state.activeJob)state.cancelBeforeStart=false;
    if(session && state.editorDirectorSession===session){state.editorDirectorSession=null;if(state.project?.id===projectId && state.projectViewToken===viewToken)elements.analysisPanel.hidden=true;}
    state.directorRequestPending=false;
    if(lock)releaseJobStartLock(lock);else renderReadiness();
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
  elements.renderButton.disabled = !state.project?.draft || Boolean(state.project?.editor_sequence?.error) || foregroundBusy() || exportRequiresDraftRebuild();
  renderReadiness();
  renderReelCandidates();
}

function showAnalysis({keepEditor=false}={}) {
  state.analysisSnapshot = null;
  state.directorOutcome = null;
  const sourceContext = document.getElementById("analysisSources");
  if (sourceContext) sourceContext.textContent = Object.entries(state.project?.sources || {}).filter(([, source]) => source).map(([slot, source]) => `${slot} · ${source.name || "Recording"}\n${formatTime(source.duration || 0)}`).join("\n\n");
  pauseAllMedia();
  if (state.studio.open && !keepEditor) setAdvanced(false);
  if(!keepEditor)setStep(2);
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
  if(keepEditor)return;
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

function directorOutcomeDescription(error) {
  const job = error?.job || (error?.status && typeof error.status === "string" ? error : null);
  const failure = job?.failure || error?.failure || error?.payload?.failure || {};
  const outcome = failure.outcome || "technical_error";
  const message = typeof error === "string" ? error : error?.message || job?.error || job?.message || "";
  const detail = String(message || "").trim() ? friendlyDirectorError(message) : "";
  const descriptions = {
    editorial_no_fit: { title: "No suitable story found", message: `${detail || "Story review finished without a suitable cut for this brief."} Review the source or adjust the brief and target length.` },
    constraint_conflict: { title: "The brief has conflicting requirements", message: `${detail || "The requested requirements could not be satisfied together."} Review the instruction and requested length, then try again.` },
    invalid_model_output: { title: "Story AI returned an unusable response", message: "The response could not be validated. Completed transcript and context work may be reused when you retry." },
    technical_error: { title: "The edit stopped before completion", message: friendlyDirectorError(message) },
  };
  const description = descriptions[outcome] || descriptions.technical_error;
  const issues = failure.instruction_contract?.issues || failure.instruction_contract?.conflicts || [];
  const reasons = issues.map((issue) => String(issue.reason || issue.message || "").trim()).filter(Boolean);
  return { ...description, outcome, job, projectId: job?.project_id || state.project?.id, contract: failure.instruction_contract,
    message: [description.message, ...reasons].join(" ") };
}

function showAnalysisError(error) {
  const description = directorOutcomeDescription(error);
  const snapshot = description.job || state.analysisSnapshot;
  // A terminal outcome keeps the last observed stage. Re-entering showAnalysis
  // here would reset progress and falsely restart the transcription indicator.
  pauseAllMedia();
  setStep(2);
  elements.setupPanel.hidden = true;
  elements.resultPanel.hidden = true;
  elements.analysisPanel.hidden = false;
  if (snapshot) updateJobUI({ ...snapshot, status: snapshot.status || "failed" });
  $$(".analysis-checks li").forEach((item) => item.classList.remove("active"));
  const message = typeof error === "string" ? error : error?.message || description.job?.error || "";
  const transcriptProblem = /transcript quality is too low|too little usable speech|language confidence|very long hallucinated segment|needs reliable speech/i.test(String(message || ""));
  elements.analysisPanel.classList.add("failed");
  elements.analysisPanel.dataset.outcome = description.outcome;
  elements.jobMessage.textContent = description.title;
  elements.analysisErrorTitle.textContent = transcriptProblem
    ? uiCopy("הסגנון הזה צריך דיבור ברור", "This style needs clear speech")
    : description.title;
  elements.analysisErrorMessage.textContent = description.message;
  elements.analysisError.hidden = false;
  elements.cancelJobButton.hidden = true;
  renderReelCandidates();
  toast(`${description.title}: ${description.message}`, description.outcome === "technical_error" ? "error" : "info");
}

function showResult() {
  if (!state.project?.draft) return showSetup();
  pauseAllMedia();
  setStep(3);
  elements.setupPanel.hidden = true;
  elements.analysisPanel.hidden = true;
  elements.resultPanel.hidden = false;
  elements.renderButton.disabled = Boolean(state.project?.editor_sequence?.error) || foregroundBusy() || exportRequiresDraftRebuild();
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

async function refreshProjectAfterDirector(projectId, attempts = 3, viewToken = state.projectViewToken) {
  let lastError = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (!payload?.project?.draft) throw new Error("Director completed but the Draft is not available yet");
      if(state.project?.id!==projectId || state.projectViewToken!==viewToken)return payload.project;
      // A late job refresh cannot replace a newer edit or queued settings.
      if(Number(payload.project.revision)<Number(state.project.revision))return state.project;
      const project=reconcileProjectSnapshot(payload.project);
      rememberProjectRevision(project);
      if(!keepEditorAfterDirector(project)){state.project=project;hydrateProject();}
      loadProjects().catch(() => {});
      return payload.project;
    } catch (error) {
      lastError = error;
      if (attempt + 1 < attempts) await new Promise((resolve) => window.setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
  throw lastError || new Error("Could not refresh the completed Draft");
}

function aiDraftStamp(draft) {
  const sort = value => Array.isArray(value) ? value.map(sort) : value && typeof value === "object"
    ? Object.fromEntries(Object.keys(value).sort().map(key => [key, sort(value[key])])) : value;
  return JSON.stringify(sort(draft));
}

function rememberDirectorResult(job) {
  const result = job?.result, project = state.project;
  if (!project?.id || !result || job?.project_id !== project.id || result.project_id !== project.id) return false;
  const isolated=result.proposal_only===true && typeof result.proposal_origin_id==="string" && result.proposal_origin_id===project.ai_draft_review?.origin_id
    && project.ai_draft_review?.isolated===true && project.ai_draft_review.available===true;
  const preserved = isolated || result.applied_to_timeline === false && result.timeline_preserved === true && result.variation_changed !== false
    && project?.manual?.sequence && result.draft && aiDraftStamp(result.draft) === aiDraftStamp(project.draft);
  state.aiDraftNotice = preserved ? {projectId:project.id, draftStamp:aiDraftStamp(result.draft)} : null;
  renderAiDraftNotice();
  return Boolean(preserved);
}

function currentAiDraftNotice() {
  const project=state.project, saved=project?.ai_draft_review;
  // An authoritative unavailable result wins over old job receipts, including
  // after Apply followed by another manual edit and a fresh page load.
  if(saved?.version===1)return saved.available && typeof saved.origin_id==="string" && (project?.manual?.sequence || saved.isolated===true)
    ? {projectId:project.id,originId:saved.origin_id,pending:saved.pending===true,legacy:saved.legacy===true} : null;
  const notice = state.aiDraftNotice;
  return notice && notice.projectId === project?.id && project?.manual?.sequence
    && notice.draftStamp === aiDraftStamp(project.draft) ? notice : null;
}

function aiDraftReviewIssue() {
  const queue=state.saveQueues.get(state.project?.id);
  if(state.draftDirtyReasons.size)return "Save or rebuild the pending AI preferences before reviewing a draft.";
  if(state.captionDirty || state.captionContextSave || [...state.transcriptBuffers.values()].some(row=>row.projectId===state.project?.id))
    return "Save or discard the pending caption/transcript text before reviewing a draft.";
  if(state.project?.id && state.chromaStudio?.projectId===state.project.id && (state.chromaStudio.saving
    || [...(state.chromaStudio.drafts?.keys?.() || [])].some(slot=>state.chromaStudio.dirty?.(slot))))
    return "Apply or discard the pending Chroma Key settings before reviewing a draft.";
  if(state.embeddedEditor.projectId===state.project?.id && state.embeddedEditor.dirty)
    return "Save or discard the pending camera layout before reviewing a draft.";
  if(foregroundBusy() || state.transcriptSaving || state.mediaStudio?.pending?.size || state.mediaStudio?.saving
    || state.textStudio?.dirty?.() || queue?.pending || queue?.inFlight || liveEmbeddedCameraRequest())
    return "Wait for the current changes to finish before reviewing a draft.";
  return "";
}

function directorCompletionNotice(job, preserved = false) {
  const isolated=job?.result?.proposal_only===true && typeof job.result.proposal_origin_id==="string" && job.result.proposal_origin_id===state.project?.ai_draft_review?.origin_id
    && state.project?.ai_draft_review?.isolated===true && state.project.ai_draft_review.available===true;
  if(job?.result?.proposal_only===true && !isolated)return {
    message:"The earlier AI run finished. The current edit is unchanged; review the latest saved proposal.",kind:"info"};
  const draft = isolated ? job.result.draft : state.project?.draft;
  const current = Boolean(state.project?.id && job?.project_id === state.project.id
    && job?.result?.project_id === state.project.id && job.result.draft
    && aiDraftStamp(job.result.draft) === aiDraftStamp(draft));
  const basicCleanup = current && (draft.engine === "deterministic_story_fallback"
    || (draft.quality_review?.warnings || []).some(warning => warning?.type === "story_ai_fallback"));
  const extractive = current && (draft.editorial_authority === "extractive_rough_cut"
    || draft.engine === "chronological_extractive_rough_cut"
    || (draft.quality_review?.warnings || []).some(warning => warning?.type === "extractive_rough_cut"));
  const transcriptFallback = current && (isolated ? job.result.warnings || [] : state.project?.analysis?.warnings || []).some(warning => warning?.type === "transcript_fallback");
  const fallbackWarning = extractive ? t("extractiveRoughCutReady") : transcriptFallback ? t("speechStyleFallbackReady") : current && draft.engine === "audio_visual_highlights" ? t("audioHighlightsReady")
    : basicCleanup ? t("basicCleanupReady") : "";
  const review = draft?.duration_review;
  const targetShortfall = current && review?.duration_mode === "target" && review.shortfall === true;
  const overTarget = current && review?.exceeds_target === true;
  const storyIncomplete = current && review?.target_feasibility?.status === "limited";
  const number = value => Number.isFinite(Number(value)) ? Math.round(Number(value)*10)/10 : 0;
  const targetWarning = (overTarget ? t("durationOverTarget") : targetShortfall ? t("durationTargetLimitedReady") : storyIncomplete ? t("durationStoryIncompleteReady") : "")
    .replace(/\{(selected|requested)\}/g,(_match,key)=>String(number(review?.[`${key}_seconds`])));
  const warning = [fallbackWarning,targetWarning].filter(Boolean).join(" ");
  return {message:[preserved ? t("aiDraftKept") : warning ? "" : t("draftReady"), warning].filter(Boolean).join(" "),
    kind:preserved || warning ? "info" : "success"};
}

// A facecam inside the recording is the standard gaming Short layout: camera on
// top, game below. The detection is easy to miss in Layout, so the draft offers
// it once; the frame is still checked and confirmed in Layout.
function streamerTipKey() { return `cutroom-streamer-tip-${state.project?.id || ""}`; }
function renderStreamerLayoutTip() {
  const tip = document.getElementById("streamerLayoutTip"); if (!tip) return;
  let dismissed = false;
  try { dismissed = localStorage.getItem(streamerTipKey()) === "dismissed"; } catch { dismissed = false; }
  const draft = state.project?.draft;
  tip.hidden = dismissed || !draft || draft.aspect !== "9:16" || !embeddedCameraCandidate() || embeddedCameraIsActive();
}

function reviewStreamerLayout() {
  if (foregroundBusy() || state.manualEditBusy) return;
  openStudioTab("framing");
  if (elements.embeddedCameraEditor) elements.embeddedCameraEditor.open = true;
  (elements.embeddedCameraEditor || elements.cameraDetection)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderAiDraftNotice() {
  renderDurationReview();
  renderStreamerLayoutTip();
  const notice = document.getElementById("aiDraftNotice"); if (!notice) return;
  const saved=currentAiDraftNotice();
  notice.hidden = !saved;
  const text = notice.querySelector("p");
  if(text)text.textContent = saved?.originId
    ? uiCopy("ציר הזמן הנוכחי נשמר. אפשר לבדוק את טיוטת ה-AI לפני החלתה.", "Your current timeline is kept. Inspect the saved AI draft and its actual impact before applying it.") : t("aiDraftKept");
  const button = document.getElementById("applyAiDraftButton");
  if(button){
    button.textContent=uiCopy("בדיקת טיוטת AI",saved?.legacy ? "Review saved draft" : "Review AI draft");
    const issue=aiDraftReviewIssue();button.disabled=Boolean(issue || !saved?.originId);button.title=issue || (!saved?.originId ? "Reload the app to review this saved draft." : "Inspect original passages and the exact effect of applying this saved draft.");
  }
  const host = state.studio.open ? elements.advancedPanel?.querySelector(".advanced-content") : elements.resultPanel;
  if (!notice.hidden && host && notice.parentElement !== host) host.insertBefore(notice, host.firstChild);
}

async function openAiDraftConfirmation() {
  const notice=currentAiDraftNotice(),issue=aiDraftReviewIssue();
  if(!notice?.originId || state.aiDraftReview)return false;
  if(issue){toast(issue,"info");return false;}
  const projectId=state.project.id,revision=state.project.revision,viewToken=state.projectViewToken,originId=notice.originId;
  const sourceUrl=sourceMediaUrl(state.project.sources?.A);
  if(!sourceUrl)return false;
  // Opening/keeping is read-only: pending drafts are never silently flushed.
  pauseAllMedia();
  const isCurrent=()=>state.aiDraftReview===review && state.project?.id===projectId && state.project.revision===revision && state.projectViewToken===viewToken
    && currentAiDraftNotice()?.originId===originId && !state.draftDirtyReasons.size;
  const review=new AiDraftReview({projectId,revision,originId,sourceUrl,api,isCurrent,
    apply:async proposal=>{
      if(!isCurrent() || aiDraftReviewIssue() || proposal?.origin_id!==originId || proposal?.revision!==revision
        || proposal?.project_id!==projectId || proposal?.apply_allowed!==true)return null;
      const updated=await applyManualEdit("apply_ai_draft",{proposal_id:proposal.proposal_id},{isCurrent});
      if(updated && state.project?.id===projectId){state.aiDraftNotice=null;renderAiDraftNotice();toast(t("aiDraftApplied"),"success");}
      return updated;
    },
    onClose:()=>{if(state.aiDraftReview===review)state.aiDraftReview=null;},
  });
  state.aiDraftReview=review;
  return review.open();
}

async function recoverActiveJobs(projectId, viewToken) {
  if (!projectId || state.recoveringJobs.has(projectId)) return false;
  state.recoveringJobs.add(projectId);
  const recoveryLock = `recover:${projectId}`;
  state.jobStartLocks.add(recoveryLock);
  renderReadiness();
  try {
    let payload;
    try {
      payload = await api(`/api/projects/${encodeURIComponent(projectId)}/jobs/active`);
    } catch (error) {
      if ([404, 405].includes(Number(error?.status))) return false;
      throw error;
    }
    if (viewToken !== state.projectViewToken || state.project?.id !== projectId) return false;
    const jobs = Array.isArray(payload?.jobs) ? payload.jobs : payload?.job ? [payload.job] : [];
    const recent = Array.isArray(payload?.recent) ? payload.recent : jobs;
    initializePreviewRepairs()?.observe?.(recent);
    const interrupted = recent.find((job) => job?.status === "interrupted" && !state.reportedInterruptedJobs.has(job.id));
    if (interrupted) {
      state.reportedInterruptedJobs.add(interrupted.id);
      toast(uiCopy(
        "עבודה קודמת נעצרה כשהאפליקציה נסגרה. אפשר להפעיל אותה שוב בבטחה.",
        "A previous job stopped when CUTROOM closed. You can start it again safely.",
      ));
    }
    let recoveryStarted=false;
    const active = jobs.filter((job) => ["queued", "running"].includes(job?.status));
    for (const job of active.filter((item) => item.kind === "prepare_source")) {
      const slot = String(job.dedupe_key || "A").split(":", 1)[0].toUpperCase();
      monitorBackgroundJob(job.id, { refreshAudio: true, projectId, slot }).catch(() => {});
    }
    const foreground = active.find((job) => ["director", "refine", "render", "manual_transcript"].includes(job.kind));
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
          recoveryStarted=true;
          retrySourcePreparation(projectId, slot, latestPreparation.id).catch(() => {});
        }
      }
      const latestDirector = recent
        .filter((job) => ["director", "refine"].includes(job?.kind))
        .sort((left, right) => Date.parse(right.created_at || 0) - Date.parse(left.created_at || 0))[0];
      if (latestDirector?.status === "completed" && state.project?.draft) rememberDirectorResult(latestDirector);
      if (latestDirector?.status === "completed" && !state.project?.draft) {
        try {
          recoveryStarted=true;
          await refreshProjectAfterDirector(projectId);
          const preserved = rememberDirectorResult(latestDirector);
          const notice = directorCompletionNotice(latestDirector, preserved);
          toast(notice.message, notice.kind);
        } catch (error) {
          showAnalysisError(error);
        }
      } else if (["failed", "interrupted"].includes(latestDirector?.status) && !state.reportedFailedJobs.has(latestDirector.id)) {
        state.reportedFailedJobs.add(latestDirector.id);
        if (state.project?.draft) {
          state.directorOutcome = directorOutcomeDescription(latestDirector);
          renderDirectorOutcomeNotice();
          renderInstructionResults();
        } else showAnalysisError(latestDirector);
      }
      return !recoveryStarted && Array.isArray(payload?.jobs) && jobs.length===0;
    }
    if (foregroundBusy()) return;
    if (foreground.kind === "manual_transcript") {
      monitorManualTranscription(foreground, projectId, viewToken).catch(() => {});
      return;
    }
    if (foreground.kind === "render") {
      resumeExportJob(foreground).catch((error) => toast(`${t("exportFailed")}: ${friendlyRenderError(error.message)}`));
      return;
    }
    showAnalysis();
    pollJob(foreground.id, { director: true, projectId, resumed: true }).catch(async (error) => {
      if (state.project?.id !== projectId) return;
      await reconcileDirectorOutcome(projectId, error, { cancelled: error.message === "Cancelled" });
    });
  } finally {
    state.jobStartLocks.delete(recoveryLock);
    state.recoveringJobs.delete(projectId);
    renderReadiness();
  }
}

async function pollJob(jobId, options = {}) {
  const directorViewToken=options.viewToken ?? state.projectViewToken;
  const blocking = !options.background;
  if (blocking) {
    setActiveJob(jobId, { projectId: options.projectId || null, kind: options.kind || (options.modelInstall ? "model_install" : options.director ? "director" : "job") });
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
      if (options.kind === "manual_transcript") renderActiveJobBar(job);
      else if (!options.silent) updateJobUI(job);
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
            if (state.project?.id === job.project_id && state.projectViewToken===directorViewToken) await refreshProjectAfterDirector(job.project_id,3,directorViewToken);
            else loadProjects().catch(() => {});
          } catch (error) {
            reject(error);
            return true;
          }
          const currentView=state.project?.id===job.project_id && state.projectViewToken===directorViewToken;
          const preserved = currentView && rememberDirectorResult(job);
          if (currentView && options.announceReady !== false) {
            const notice = directorCompletionNotice(job, preserved);
            toast(notice.message, notice.kind);
          }
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
        const error = new Error(job.error || (job.status === "interrupted" ? "Job interrupted by restart" : "Job failed"));
        if (options.director && job.project_id && state.project?.id === job.project_id) {
          try {
            const payload = await api(`/api/projects/${encodeURIComponent(job.project_id)}`);
            if (state.project?.id === job.project_id && state.projectViewToken===directorViewToken) {
              state.project = reconcileProjectSnapshot(payload.project);
              rememberProjectRevision(state.project);
              if(!keepEditorAfterDirector(state.project))hydrateProject();
              const shelf = state.project.analysis?.review_candidates;
              if (shelf?.revision === state.project.revision && shelf.items?.length) {
                error.message = uiCopy("לא אושרה עריכה אוטומטית. זמינות הצעות מקור לסקירה; העריכה הקיימת נשמרה.", "No automatic edit was approved. Source proposals are available for review; your current edit was kept.");
              }
            }
          } catch (refreshError) { console.warn("Source proposal refresh failed", refreshError); }
        }
        error.job = job;
        error.failure = job.failure;
        finishWithError(error);
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
  state.analysisSnapshot = job;
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
    item.classList.toggle("active", !cancelling && !["completed", "failed", "cancelled", "interrupted"].includes(job.status)
      && (job.kind === "model_install" ? index === 0 : value >= threshold && value < nextThreshold));
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
  state.mediaStudio?.stopImports?.({cancelCurrent:false});
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
  renderLayerTrackControls();
  state.mediaStudio?.render();
  state.stabilizationStudio?.render();
  state.chromaStudio?.render();
  state.textStudio?.render();
  renderAiDraftNotice();
  const draft = editorProject().draft;
  const savedProposal=Boolean(currentAiDraftNotice());
  elements.draftTitle.textContent = savedProposal ? uiCopy("ציר הזמן הערוך הנוכחי", "Current edited timeline") : draft.title || state.project.name;
  elements.draftSummary.textContent = savedProposal ? uiCopy("הצגה וייצוא משתמשים בציר הזמן הנוכחי. טיוטת ה-AI זמינה לבדיקה בנפרד.", "Preview and export use your current timeline. The saved AI proposal is available to review separately.") : draft.summary || "";
  renderDirectorOutcomeNotice();
  renderInstructionResults();
  const hierarchy = state.project.analysis?.story_hierarchy;
  const engineLabel = draft.engine === "ollama_hierarchical_story"
    ? `Story AI · ${hierarchy?.model || state.system?.models?.editor_model || "local model"}`
    : draft.engine === "deterministic_story_fallback"
      ? uiCopy("עריכת גיבוי בטוחה", "Safe fallback edit")
      : draft.engine === "audio_visual_highlights"
        ? uiCopy("היילייטים מסאונד ותמונה", "Audio + visual highlights")
        : draft.engine === "audio_cleanup" ? uiCopy("ניקוי סאונד מקומי", "Local audio cleanup") : String(draft.engine || "Local edit").replaceAll("_", " ");
  const styleLabel = localizedStyleValue(editStyleById(draft.edit_style)?.name);
  elements.draftEngineBadge.textContent = savedProposal ? uiCopy("ציר זמן ידני", "Manual timeline") : styleLabel && draft.edit_style !== "smart" ? `${styleLabel} · ${engineLabel}` : engineLabel;
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
  renderCaptionInspector();
  renderCameraDetection();
  renderSourceMixer();
  seekPreview(firstKeptTime());
}

function renderDirectorOutcomeNotice() {
  if (!elements.directorOutcomeNotice) return;
  const outcome = state.directorOutcome;
  const visible = outcome && outcome.projectId === state.project?.id;
  elements.directorOutcomeNotice.hidden = !visible;
  elements.directorOutcomeNotice.textContent = visible
    ? `${outcome.title}. ${outcome.message} Your existing edit was kept.` : "";
  if (outcome) elements.directorOutcomeNotice.dataset.outcome = outcome.outcome;
  const host = state.studio.open ? elements.advancedPanel?.querySelector(".advanced-content") : elements.resultPanel;
  if (visible && host && elements.directorOutcomeNotice.parentElement !== host) {
    host.insertBefore(elements.directorOutcomeNotice, host.firstChild);
  }
}

function renderInstructionResults() {
  if (!elements.instructionResults || !elements.instructionResultsList) return;
  const contract = (state.directorOutcome?.projectId === state.project?.id ? state.directorOutcome.contract : null) || state.project?.draft?.instruction_contract
    || state.project?.analysis?.instruction_contract || state.project?.analysis?.story_hierarchy?.instruction_contract;
  const requirements = Array.isArray(contract?.requirements) ? contract.requirements : [];
  elements.instructionResults.hidden = !requirements.length;
  elements.instructionResultsList.replaceChildren();
  if (!requirements.length) return;
  const hebrew = state.locale === "he";
  elements.instructionResultsTitle.textContent = hebrew ? "בדיקת הוראות הבימוי" : "Director instruction check";
  elements.instructionResultsSummary.textContent = hebrew
    ? "המצב מוצג לכל בקשה בנפרד. בקשות שלא אומתו דורשות בדיקה שלך."
    : "Each requirement has its own result. Unverified requests need your review.";
  if (contract.verification_scope === "proposed_director_draft") {
    elements.instructionResultsSummary.textContent += hebrew
      ? " הבדיקה מתייחסת לטיוטת הבימוי המוצעת. אם שמרת שינויים ידניים, יש לבדוק את ציר הזמן הנוכחי."
      : " Scope: proposed Director draft. Review the current timeline if you kept manual changes.";
  }
  const labels = hebrew
    ? { fulfilled: "מולא", not_fulfilled: "לא מולא", unverified: "לא אומת" }
    : { fulfilled: "Fulfilled", not_fulfilled: "Not fulfilled", unverified: "Unverified" };
  for (const requirement of requirements) {
    const item = document.createElement("li");
    const status = ["fulfilled", "not_fulfilled", "unverified"].includes(requirement.status) ? requirement.status : "unverified";
    item.dataset.status = status;
    item.dir = "auto";
    const label = document.createElement("b");
    label.textContent = labels[status];
    const text = document.createElement("p");
    text.dir = "auto";
    text.textContent = String(requirement.text || requirement.kind || requirement.id || "");
    const reason = document.createElement("small");
    reason.dir = "auto";
    reason.textContent = String(requirement.reason || "");
    item.append(label, text, reason);
    elements.instructionResultsList.append(item);
  }
}

function renderReelCandidates() {
  if (!elements.reelCandidates || !elements.reelCandidateList) return;
  const draft = state.project?.draft;
  const shelf = state.project?.analysis?.review_candidates;
  const needsReview = shelf?.revision === state.project?.revision && Array.isArray(shelf?.items) ? shelf.items : [];
  const reviewRedo = !draft && Number(state.project?.manual?.history?.redo_count || 0) > 0;
  if (!state.reelCandidateHome) state.reelCandidateHome = {parent: elements.reelCandidates.parentNode, next: elements.reelCandidates.nextSibling};
  if ((needsReview.length || reviewRedo) && (!draft || !elements.analysisPanel.hidden)) {
    const host = !elements.analysisPanel.hidden && !elements.analysisError.hidden ? elements.analysisError : elements.setupPanel;
    host.append(elements.reelCandidates);
  } else if (elements.reelCandidates.parentNode !== state.reelCandidateHome.parent) {
    state.reelCandidateHome.parent.insertBefore(elements.reelCandidates, state.reelCandidateHome.next);
  }
  const candidates = [...(Array.isArray(draft?.reel_candidates) ? draft.reel_candidates : []), ...needsReview];
  elements.reelCandidates.hidden = needsReview.length || reviewRedo ? false : candidates.length < 2;
  elements.reelCandidateList.replaceChildren();
  if (reviewRedo) {
    elements.reelCandidatesTitle.textContent = uiCopy("היסטוריית עריכה", "Edit history");
    const redo = document.createElement("button");
    redo.type = "button"; redo.className = "button ghost compact";
    redo.textContent = uiCopy("החזר את בחירת הסקירה", "Redo reviewed selection");
    redo.disabled = state.manualEditBusy || foregroundBusy();
    redo.addEventListener("click", () => applyManualEdit("redo"));
    elements.reelCandidateList.append(redo);
  }
  if (!candidates.length || (!needsReview.length && candidates.length < 2)) return;
  elements.reelCandidatesTitle.textContent = needsReview.length ? uiCopy("הצעות מקור — נדרשת סקירה", "Source proposals — review required") : uiCopy("כמה עריכות מאותו ניתוח", "Several edits from one analysis");
  const labels = {
    director_pick: uiCopy("בחירת ה־Director", "Director's pick"),
    focused_moment: uiCopy("רגע ממוקד", "Focused moment"),
    alternate_highlight: uiCopy("היילייט חלופי", "Alternate highlight"),
    intense_moment: uiCopy("הרגע הכי עוצמתי", "Most intense moment"),
    action_moment: uiCopy("האקשן הכי חזק במשחק", "Best gameplay action"),
  };
  const energyLabels = {
    high: uiCopy("אנרגיה גבוהה", "High energy"),
    medium: uiCopy("אנרגיה בינונית", "Medium energy"),
    low: uiCopy("אנרגיה נמוכה", "Low energy"),
  };
  // Measured against this recording: loudness, activity and spoken reactions.
  const signalText = (signals) => {
    if (!signals || !energyLabels[signals.energy]) return "";
    const reactions = Number(signals.reactions || 0);
    const action = Number(signals.visual?.action);
    // Gameplay vision: how much visible action the local model saw (0-100).
    const visual = Number.isFinite(action) && action >= 50 ? ` · ${uiCopy("אקשן על המסך", "On-screen action")} ${Math.round(action)}` : "";
    return ` · ${energyLabels[signals.energy]}${reactions ? ` · ${reactions} ${uiCopy("תגובות", reactions === 1 ? "reaction" : "reactions")}` : ""}${visual}`;
  };
  const activeId = String(draft?.active_reel_candidate || "director_pick");
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
    strong.textContent = candidate.kind === "unverified_source_candidate" ? uiCopy("הצעה לא מאומתת", "Unverified proposal") : labels[candidate.kind] || uiCopy("חלופת Reel", "Reel option");
    const meta = document.createElement("small");
    meta.textContent = `${formatTime(Number(candidate.output_duration || 0))}${signalText(candidate.signals)}`;
    if (candidate.signals) meta.title = candidate.signals.visual
      ? uiCopy("נמדד מול ההקלטה הזו: עוצמת קול, תגובות מדוברות ומה שנראה על המסך.", "Measured against this recording: loudness, spoken reactions and what was seen on screen.")
      : uiCopy("נמדד מול ההקלטה הזו: עוצמת קול, פעילות ותגובות מדוברות.", "Measured against this recording: loudness, activity and spoken reactions.");
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
    if (!active && supportsReelReview(state.project)) button.textContent = uiCopy("סקור לפני החלה", "Review before applying");
    elements.reelCandidateList.append(card);
  }
  renderDraftActions();
}

function renderDraftActions() {
  const draft = state.project?.draft;
  const dirty = state.draftDirtyReasons.size > 0;
  const trackIssue=savedLayerTrackIssue();
  const disabled = !draft || foregroundBusy() || state.directorRequestPending || state.requestReviewBusy || dirty || Boolean(trackIssue);
  $$("[data-open-studio-tab]").forEach((button) => { button.disabled = !draft || foregroundBusy(); });
  $$(".refine-grid button").forEach((button) => {
    button.hidden = button.dataset.command === "new_variation" && !canVaryDraft();
    button.disabled = disabled;
    button.title = trackIssue || (dirty ? t("rebuildBeforeRefine") : "");
  });
  $$("button[data-candidate-id]", elements.reelCandidateList || document).forEach((button) => {
    const shelf = state.project?.analysis?.review_candidates;
    const sourceProposal = Boolean(shelf && shelf.revision === state.project?.revision && shelf.items?.some(item => item.id === button.dataset.candidateId));
    button.disabled = Boolean(trackIssue) || (sourceProposal ? foregroundBusy() || dirty : disabled) || button.dataset.candidateId === String(draft?.active_reel_candidate || "director_pick");
    button.title = trackIssue || (dirty ? t("rebuildBeforeRefine") : "");
  });
}

function canVaryDraft() {
  return state.project?.draft?.goal === "short" && (state.project.settings?.goal || "short") === "short";
}

function renderDurationReview() {
  const node = document.getElementById("durationReview"); if (!node) return;
  const draft = state.project?.draft, review = draft?.duration_review;
  const assessedLimit = review?.target_feasibility?.status === "limited";
  node.hidden = !review || !assessedLimit && !["style_moment_limit","limited_selection","source_shorter","over_target"].includes(review.reason);
  if (node.hidden) return;
  const number = value => Number.isFinite(Number(value)) ? Math.round(Number(value)*10)/10 : 0;
  const replacements = {selected:number(review.selected_seconds), requested:number(review.requested_seconds),
    available:number(review.available_source_seconds), limit:number(review.style_moment_limit),
    supported:number(review.target_feasibility?.supported_seconds ?? review.selected_seconds)};
  const key = review.reason === "over_target" ? "durationOverTarget" : review.reason === "style_moment_limit" ? "durationStyleLimit" : review.reason === "source_shorter" ? "durationSourceLimit" : "durationEvidenceLimit";
  const summaryKey = review.duration_mode === "target" ? "durationDraftTargetSummary"
    : review.duration_is_ceiling || review.duration_mode === "style" ? "durationDraftMaximumSummary" : "durationDraftSummary";
  // Each step that changed the length, so a short draft shows where time went.
  const chain = (Array.isArray(review.chain) ? review.chain : []).filter(row => row && Number.isFinite(Number(row.seconds)))
    .map(row => `${t(`durationStage_${row.stage}`) || row.stage} ${number(row.seconds)}s${row.passages ? ` (${row.passages})` : ""}`);
  const assessment = assessedLimit && review.target_feasibility.scope === "current_selection" ? ` ${t("durationAssessmentLimit")}` : "";
  const message = t(summaryKey) + " " + t(key) + assessment + (chain.length > 2 ? ` ${t("durationChain")} ${chain.join(" → ")}.` : "");
  const text = node.querySelector("p");
  if (text) text.textContent = message.replace(/\{(selected|requested|available|limit|supported)\}/g,(_match,key)=>String(replacements[key]));
  const summary = node.querySelector(".duration-review-summary");
  if (summary) summary.textContent = t(summaryKey).replace(/\{(selected|requested)\}/g,(_match,key)=>String(replacements[key]));
  const button = document.getElementById("reviewDurationSettings");
  if (button) { button.textContent=t("reviewDurationSettings"); button.disabled=foregroundBusy() || state.manualEditBusy; }
  const host = state.studio.open ? elements.advancedPanel?.querySelector(".advanced-content") : elements.resultPanel;
  if (host && node.parentElement !== host) host.insertBefore(node, host.firstChild);
}

function renderDraftWarning() {
  if (!elements.draftWarning) return;
  const engine = state.project?.draft?.engine;
  const audioHighlights = engine === "audio_visual_highlights";
  const fallback = engine === "deterministic_story_fallback";
  const extractive = engine === "chronological_extractive_rough_cut"
    || state.project?.draft?.editorial_authority === "extractive_rough_cut";
  const limitedHighlights = (state.project?.analysis?.warnings || []).some((warning) => warning.type === "limited_highlight_evidence");
  const transcriptFallback = (state.project?.analysis?.warnings || []).some((warning) => warning.type === "transcript_fallback");
  const cameraWarnings = embeddedCameraDetection()?.available === true ? [] : (state.project?.analysis?.warnings || [])
    .filter((warning) => warning?.type === "camera_detection")
    .map((warning) => warning.message).filter((message) => typeof message === "string" && message);
  const reviewWarnings = (state.project?.draft?.quality_review?.warnings || [])
    .map((warning) => warning?.message).filter((message) => typeof message === "string" && message);
  elements.draftWarning.hidden = !audioHighlights && !fallback && !extractive && !limitedHighlights && !transcriptFallback && !cameraWarnings.length && !reviewWarnings.length;
  elements.draftWarningText.textContent = [
    extractive ? t("extractiveRoughCutWarning") : transcriptFallback ? t("transcriptFallbackActionable") : audioHighlights ? t("audioHighlightWarning") : fallback ? t("storyFallbackWarning") : "",
    limitedHighlights ? t("limitedHighlightWarning") : "",
    ...cameraWarnings,
    ...reviewWarnings,
  ].filter(Boolean).join(" ");
}

function openSpeechReviewSettings() {
  if (!openStudioTab("transcript")) return;
  const language = elements.spokenLanguageSelect;
  const disclosure = language?.closest("details"); if (disclosure) disclosure.open = true;
  language?.focus(); language?.scrollIntoView({block:"nearest"});
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
    else if (decision.type === "visual_ai") value = `${decision.count || 0} ${t("visualMomentsWatched")}`;
    else value = `${decision.count || 0} ${t("occurrences")}`;
    item.innerHTML = `<i></i><strong></strong><span></span>`;
    $("strong", item).textContent = label;
    $("span", item).textContent = value;
    elements.decisionList.append(item);
  }
  renderGameplayMoments();
  renderDraftChapters();
}

// YouTube chapters proposed by the long-form gameplay draft. Times are mapped
// from each chapter's source start through the draft's current kept ranges.
function draftChapterLines() {
  const draft = state.project?.draft;
  const chapters = Array.isArray(draft?.chapters) ? draft.chapters : [];
  const keep = Array.isArray(draft?.keep_ranges) ? draft.keep_ranges : [];
  if (chapters.length < 3 || !keep.length) return [];
  const outputTime = (sourceTime) => {
    let elapsed = 0;
    for (const range of keep) {
      const start = Number(range.start), end = Number(range.end);
      if (sourceTime <= start) break;
      elapsed += Math.min(sourceTime, end) - start;
    }
    return elapsed;
  };
  const clock = (seconds) => {
    const whole = Math.max(0, Math.floor(seconds + 1e-6));
    const hours = Math.floor(whole / 3600), minutes = Math.floor(whole / 60) % 60, rest = String(whole % 60).padStart(2, "0");
    return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
  };
  const lines = [];
  for (const [index, chapter] of chapters.entries()) {
    const time = index === 0 ? 0 : outputTime(Number(chapter.source_start));
    if (index && time - (lines.at(-1)?.time ?? 0) < 10) continue;
    lines.push({ time, label: `${clock(time)} ${String(chapter.title || `Part ${index + 1}`).trim()}` });
  }
  return lines.length >= 3 ? lines : [];
}

function renderDraftChapters() {
  let section = document.getElementById("draftChapters");
  const lines = draftChapterLines();
  if (!lines.length) { if (section) section.hidden = true; return; }
  if (!section) {
    section = document.createElement("section");
    section.id = "draftChapters";
    section.className = "draft-chapters";
    const head = document.createElement("div");
    head.className = "draft-chapters-head";
    const title = document.createElement("strong");
    title.textContent = "YouTube chapters";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "button ghost compact";
    copy.textContent = "Copy";
    copy.addEventListener("click", async () => {
      const text = draftChapterLines().map(line => line.label).join("\n");
      try { await navigator.clipboard.writeText(text); toast("Chapters copied. Paste them into the YouTube description.", "success", 2800); }
      catch { toast("Copy was blocked by the browser. Select the chapter text and copy it."); }
    });
    head.append(title, copy);
    const list = document.createElement("ol");
    const note = document.createElement("small");
    note.textContent = "Suggested from the draft's kept stretches. Rename them, and check the times again after editing.";
    section.append(head, list, note);
    elements.decisionList.after(section);
  }
  section.hidden = false;
  const list = section.querySelector("ol");
  list.replaceChildren(...lines.map(line => { const item = document.createElement("li"); item.dir = "auto"; item.textContent = line.label; return item; }));
  // Long-form extras: the strongest instant as a cold-open teaser idea, and
  // how many punch-in zooms the export adds at the loudest moments.
  let extra = section.querySelector(".draft-longform-extras");
  if (!extra) { extra = document.createElement("p"); extra.className = "draft-longform-extras"; list.after(extra); }
  const draft = state.project?.draft || {};
  const notes = [];
  const cold = draft.cold_open;
  if (cold && Number.isFinite(Number(cold.source_start))) {
    notes.push(`Cold open idea: the strongest moment, ${formatTime(Number(cold.source_start))}–${formatTime(Number(cold.source_end))} in the recording. Place a copy before 0:00 as a teaser.`);
  }
  const punches = Array.isArray(draft.punch_ins) ? draft.punch_ins.length : 0;
  if (punches && !state.project?.manual?.sequence) notes.push(`Export adds ${punches} short punch-in zoom${punches === 1 ? "" : "s"} at the loudest moments.`);
  extra.textContent = notes.join(" ");
  extra.hidden = !notes.length;
}

// The gameplay moments a draft kept, with their on-screen evidence. A moment
// the model misread (a camera feed or replay read as a fight) can be marked as
// not live play; the next Rebuild leaves it out. Weak evidence is named.
function renderGameplayMoments() {
  const section = elements.gameplayMoments;
  if (!section) return;
  const moments = Array.isArray(state.project?.draft?.gameplay_moments) ? state.project.draft.gameplay_moments : [];
  section.replaceChildren();
  section.hidden = !moments.length;
  if (!moments.length) return;
  const overrides = state.project?.manual?.visual_overrides || [];
  const heading = document.createElement("strong");
  heading.textContent = t("gameplayMomentsTitle");
  section.append(heading);
  for (const moment of moments) {
    const marked = overrides.find(row => row.start <= moment.start + .001 && row.end >= moment.end - .001 && row.screen !== "gameplay");
    const row = document.createElement("div");
    row.className = "gameplay-moment";
    row.dataset.uncertain = String(Boolean(moment.uncertain));
    const seek = document.createElement("button");
    seek.type = "button"; seek.className = "gameplay-moment-seek";
    seek.textContent = `${formatTime(moment.start)}–${formatTime(moment.end)}${moment.event ? ` · ${moment.event}` : ""}`;
    seek.addEventListener("click", () => {
      const time = sourceToEditorTime(Number(moment.start));
      if (time != null) { pauseAllMedia(); seekSourcePreview(time + .05); }
    });
    row.append(seek);
    if (moment.uncertain && !marked) {
      const badge = document.createElement("span");
      badge.className = "gameplay-moment-uncertain"; badge.textContent = t("gameplayMomentUncertain");
      row.append(badge);
    }
    const action = document.createElement("button");
    action.type = "button"; action.className = "gameplay-moment-mark";
    action.textContent = marked ? t("gameplayMomentUnmark") : t("gameplayMomentNotLive");
    action.title = marked ? t("gameplayMomentMarkedHelp") : t("gameplayMomentNotLiveHelp");
    action.disabled = foregroundBusy() || state.manualEditBusy;
    action.addEventListener("click", () => runUiAction(async () => {
      const result = await applyManualEdit("visual_override", { start: moment.start, end: moment.end, screen: marked ? "" : "cutscene" });
      if (result) markDraftRebuild("visual");
    }, t("gameplayMomentsTitle")));
    row.append(action);
    section.append(row);
  }
  if (state.draftDirtyReasons.has("visual")) {
    const rebuild = document.createElement("button");
    rebuild.type = "button"; rebuild.className = "button primary compact gameplay-moments-rebuild";
    rebuild.textContent = uiCopy("בנה Draft מחדש", "Rebuild Draft");
    rebuild.disabled = foregroundBusy() || state.manualEditBusy;
    rebuild.addEventListener("click", rebuildDraftFromStudio);
    section.append(rebuild);
  }
}

function sourceMixerSettings() {
  const stored = state.project?.manual?.source_mixer || {};
  const desired = state.project && state.sourceMixerDesired?.projectId === state.project.id ? state.sourceMixerDesired.payload : null;
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
  const screenFit=state.project?.sources?.B && ["auto","cover","contain"].includes(raw.screen_fit)?raw.screen_fit:"auto";
  const pipScale=Number(raw.pip_scale??.34),pipX=Number(raw.pip_x??1),pipY=Number(raw.pip_y??1);
  const pipConfigured=["pip_scale","pip_x","pip_y"].some(key=>Object.hasOwn(raw,key));
  return { screenSlot, cameraSlot, firstSlot, primaryRole, audioSlot, syncOffset, hasManualSync, defaultLayout, defaultLayoutExplicit, stackFit,screenFit,pipScale,pipX,pipY,pipConfigured };
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
  return Boolean(retainedEditStatus() ||
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
  if(slot===mixer.screenSlot && mixer.screenFit==="contain")return{x:.5,y:.5,zoom:1};
  const primarySlot = mixer.primaryRole === "camera" ? mixer.cameraSlot : mixer.screenSlot;
  const fitted = layout === "auto" || layout === "side_by_side"
    || (layout === "stacked" && mixer.stackFit !== "cover")
    || (layout === "pip" && slot !== primarySlot);
  // Export's fit filter keeps the complete frame centred, without applying
  // crop/zoom. Keep stored framing intact, but do not preview a crop that will
  // disappear from the rendered video when Fit entire source is selected.
  if (fitted && !(slot===mixer.screenSlot && mixer.screenFit==="cover") && !(state.project?.editor_sequence && override) && !clipCrop) return { x: .5, y: .5, zoom: 1 };
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
  video.style.objectFit = slot===mixer.screenSlot && ["cover","contain"].includes(mixer.screenFit) ? mixer.screenFit
    : editedClipCrop(slot,time) || (state.project?.editor_sequence && override) ? "cover" : "";
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

function creatorPipGeometry(width,height,mixer=sourceMixerSettings()) {
  let w=Math.max(160,Math.floor(width*.34/2)*2),h=Math.max(90,Math.floor(height*.28/2)*2),x=width-w-32,y=height-h-32;
  if(mixer.pipConfigured){
    const slot=mixer.primaryRole==="screen"?mixer.cameraSlot:mixer.screenSlot,source=state.project?.sources?.[slot]||{};
    let sw=Number(source.width),sh=Number(source.height);
    if(Number(source.rotation||0)%180)[sw,sh]=[sh,sw];
    if(!(sw>0&&sh>0))return null;
    const ratio=sw/sh;w=Math.max(2,Math.floor(width*mixer.pipScale/2)*2);h=Math.max(2,Math.floor(w/ratio/2)*2);
    if(h>height){h=Math.floor(height/2)*2;w=Math.max(2,Math.floor(h*ratio/2)*2);}
    x=Math.round((width-w)*mixer.pipX);y=Math.round((height-h)*mixer.pipY);
  }
  return{width:w,height:h,x,y};
}
function applyPreviewPipGeometry(container) {
  if (!container) return;
  const [width,height]=previewExportDimensions(),rect=creatorPipGeometry(width,height);
  if(!rect)return;
  container.style.setProperty("--pip-width",`${100*rect.width/width}%`);
  container.style.setProperty("--pip-height",`${100*rect.height/height}%`);
  container.style.setProperty("--pip-right",`${100*(width-rect.width-rect.x)/width}%`);
  container.style.setProperty("--pip-bottom",`${100*(height-rect.height-rect.y)/height}%`);
}

function renderCreatorLayout(mixer,busy,hasTwoSources) {
  const form=document.getElementById("creatorLayoutForm");if(!form)return;
  form.hidden=!hasTwoSources;
  if(!form.dataset.bound){
    form.dataset.bound="true";
    form.addEventListener("input",()=>form.dataset.dirty="true");
    form.addEventListener("submit",event=>{
      event.preventDefault();if(sourceMixerControlBusy())return;
      const values={screen_fit:document.getElementById("creatorScreenFit").value};
      if (!document.getElementById("creatorInsetControls")?.hidden) Object.assign(values, {
        pip_scale:Number(document.getElementById("creatorPipScale").value)/100,
        pip_x:Number(document.getElementById("creatorPipX").value)/100,pip_y:Number(document.getElementById("creatorPipY").value)/100});
      if(!form.reportValidity())return;
      const projectId=state.project?.id;
      void saveSourceMixer(values).then(saved=>{if(saved&&state.project?.id===projectId){form.dataset.dirty="";renderSourceMixer();}})
        .catch(error=>toast(error.message));
    });
  }
  const key=`${state.project?.id}`;
  if(form.dataset.project!==key){form.dataset.project=key;form.dataset.dirty="";}
  if(form.dataset.dirty!=="true"){
    for(const[id,value]of [["creatorScreenFit",mixer.screenFit],["creatorPipScale",mixer.pipScale*100],["creatorPipX",mixer.pipX*100],["creatorPipY",mixer.pipY*100]])document.getElementById(id).value=value;
  }
  form.querySelectorAll("input,select,button").forEach(node=>node.disabled=busy);
  const inset = document.getElementById("creatorInsetControls");
  if (inset) {
    inset.hidden = (state.sourceMixerPreviewLayout || state.sourceMixerLayout) !== "pip";
    inset.querySelectorAll?.("input").forEach(node=>node.disabled=busy || inset.hidden);
  }
  document.getElementById("creatorLayoutStatus").textContent=mixer.screenFit==="contain"?uiCopy("תמונת המסך נשמרת בשלמותה; זום שמור אינו מוחל עליה.","Full gameplay frame preserved; stored screen zoom is ignored."):uiCopy("מסגור ידני · ניתן לביטול", "Manual framing · Undo available");
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
  elements.sourceCompositionMode.textContent = `${labels[selectedLayout] || selectedLayout} · layout example`;
  elements.sourceCompositionMode.title = "Original-source layout example. The edit shows B only where B footage is mapped on its timeline.";
  elements.firstSlotName.textContent = uiCopy(
    `${mixer.firstSlot} למעלה ב־Stack · ${mixer.firstSlot} משמאל ב־Split`,
    `${mixer.firstSlot} on top in Stack · ${mixer.firstSlot} on the left in Split`,
  );
}

function renderSourceMixer() {
  renderProjectSaveState();
  if (!elements.sourceMixer || !state.project) return;
  renderRangeEditors();
  const sourceA = state.project.sources?.A;
  const sourceB = state.project.sources?.B;
  const hasTwoSources = Boolean(sourceA && sourceB);
  placeSourceMixer(Boolean(sourceA));
  const mixer = sourceMixerSettings();
  const busy = sourceMixerControlBusy();
  renderSourceIdentity(mixer, busy);
  renderCreatorLayout(mixer,busy,hasTwoSources);
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
        : uiCopy("הקלטה אחת", "One recording");
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
  elements.sourceSyncStatus.textContent = sourceSyncDescription(mixer);
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
    elements.sourceSyncStatus.textContent += " B uses independent clips. Adjust existing B clips on the timeline; the offset field does not move them.";
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
  renderSourceBCoverage(mixer);
}

function sourceSyncDescription(mixer = sourceMixerSettings()) {
  if (mixer.hasManualSync) return `Manual offset: ${mixer.syncOffset.toFixed(2)}s. Check a shared moment in both recordings.`;
  const sync = state.project?.analysis?.sync || {};
  const method = String(sync.method || "").toLowerCase();
  const unconfirmed = sync.reliable === false || sync.status === "unconfirmed";
  const prefix = unconfirmed ? "Sync unconfirmed: " : "";
  if (method === "source_tracks") return `${prefix}Independent B clip placement. Clip positions set the alignment; no automatic audio match was measured for this placement. Review the alignment before export.`;
  if (method === "manual") return `${prefix}Manual source placement: ${mixer.syncOffset.toFixed(2)}s. Check a shared moment in both recordings.`;
  const confidence = Number(sync.confidence);
  const audioMethod = !method || method === "audio_cross_correlation";
  const confirmed = audioMethod && !unconfirmed
    && (sync.reliable === true || sync.status === "confirmed" || (Number.isFinite(confidence) && confidence >= .18));
  if (confirmed) return `Automatic audio match: ${mixer.syncOffset.toFixed(2)}s. Review the alignment before export.`;
  return `Sync unconfirmed: ${mixer.syncOffset.toFixed(2)}s is not a verified shared start. ${sync.warning || "Compare the same sound or visual event in both recordings before placing B."}`;
}

function sourceBEditCoverage(project, mixer, selection = null) {
  const limit = Number(project?.sources?.B?.video_duration) > 0
    ? Number(project.sources.B.video_duration) : Math.max(0, Number(project?.sources?.B?.duration) || 0);
  const ranges = Array.isArray(selection) ? selection : selection ? [selection] : project?.draft?.keep_ranges || [{ start: 0, end: Number(project?.sources?.A?.duration) || 0 }];
  const union = values => {
    const merged = [];
    for (const range of values.filter(item => Number.isFinite(item.start) && Number.isFinite(item.end) && item.end > item.start).sort((a, b) => a.start - b.start)) {
      const previous = merged.at(-1);
      if (previous && range.start <= previous.end) previous.end = Math.max(previous.end, range.end);
      else merged.push({ start: range.start, end: range.end });
    }
    return merged;
  };
  const scope = union(ranges.map(range => ({ start: Number(range.start), end: Number(range.end) })));
  const clips = trackClips(project, "B", mixer.syncOffset);
  const mapped = union(clips.map(clip => Object.hasOwn(clip, "video_speed") && limit > 0
    // Explicit picture retiming holds its final frame through the clip end,
    // matching the render contract without changing the audio clock.
    ? { start: Number(clip.start), end: Number(clip.end) }
    : {
      start: Math.max(Number(clip.start), Number(clip.start) - Number(clip.source_start)),
      end: Math.min(Number(clip.end), Number(clip.start) + limit - Number(clip.source_start)),
    }));
  const duration = scope.reduce((total, range) => total + range.end - range.start, 0);
  const covered = scope.reduce((total, range) => total + mapped.reduce((sum, clip) => sum + Math.max(0, Math.min(range.end, clip.end) - Math.max(range.start, clip.start)), 0), 0);
  return { duration, covered, full: duration > 0 && covered >= duration - .001, clips: clips.length };
}

function reviewSourceTiming() {
  if (sourceMixerControlBusy()) return;
  if (elements.exportDialog?.open) elements.exportDialog.close();
  openStudioTab("framing");
  document.getElementById("sourceTimingStep")?.scrollIntoView({block:"center"});
}

function renderSourceBCoverage(mixer = sourceMixerSettings(), preview = null) {
  const target = elements.sourceBCoverage;
  if (!target) return;
  const layoutAlert = document.getElementById?.("layoutCoverageAlert");
  if (layoutAlert) layoutAlert.hidden = true;
  if (!state.project?.sources?.B) {
    target.textContent = "";
    for (const id of ["sourceBCoverageNotice", "sourceBReviewPlacement"]) {
      const control = document.getElementById?.(id);
      if (control) control.hidden = true;
    }
    return;
  }
  const original = sourceBCoverage(state.project.sources, mixer.syncOffset);
  const originalText = original.end > original.start
    ? `At this offset, original B covers ${formatSourceTime(original.start)}-${formatSourceTime(original.end)} on source A's clock.`
    : "At this offset, the original recordings have no overlapping time.";
  const project = editorProject();
  const coverage = sourceBEditCoverage(project, mixer, state.manualSelection);
  const scope = state.manualSelection ? "the selection" : "this edit";
  const hasEdit = Boolean(state.project.draft);
  let text = originalText;
  if (hasEdit) {
    text = !coverage.covered
      ? `No B footage is mapped into ${scope}. A CAMERA or split layout cannot add missing footage. ${originalText}`
      : coverage.full
        ? `B has footage throughout ${scope}. ${originalText}`
        : `B covers ${coverage.covered.toFixed(2)} of ${coverage.duration.toFixed(2)} seconds in ${scope}. Gaps in B's picture use the available A footage. ${originalText}`;
    if (!coverage.full) text += " Review Original footage for B and place only a matching section using Insert a copy by time; existing B clips can be moved or trimmed on the timeline.";
  }
  if (preview?.requiresB && !preview.available) text = `B has no mapped frame at the playhead; preview uses ${preview.fallback === "gap" ? "an empty frame" : "source A"}. ${text}`;
  const warning = hasEdit ? !coverage.full : !original.full;
  // Only require B during ranges whose saved layout actually uses it. A gap
  // during an intentional screen-only section is not a failed split layout.
  const needsB = camera => ["B", "stacked", "side_by_side", "pip"].includes(camera)
    || (camera === "camera" && mixer.cameraSlot === "B") || (camera === "screen" && mixer.screenSlot === "B");
  // The preview alert describes export readiness for the whole edit, even
  // when the timing tools below are inspecting a fully covered selection.
  const scopeRanges = project?.draft?.keep_ranges || [];
  const requestedRanges = (project?.draft?.camera_plan || []).filter(row => needsB(row.camera)).flatMap(row => scopeRanges
    .map(range => ({start:Math.max(Number(row.start), Number(range.start)), end:Math.min(Number(row.end), Number(range.end))}))
    .filter(range => range.end > range.start));
  const layoutCoverage = sourceBEditCoverage(project, mixer, requestedRanges);
  if (layoutAlert && hasEdit && layoutCoverage.duration > 0 && !layoutCoverage.full) {
    layoutAlert.hidden = false;
    const message = document.getElementById("layoutCoverageAlertText");
    if (message) message.textContent = `Requested layout needs B, but only ${layoutCoverage.covered.toFixed(2)} of ${layoutCoverage.duration.toFixed(2)} required edit seconds have mapped B footage. Export automatically uses mapped A picture where it safely covers missing B, and reports the substitution. The B/split layout is absent there. If no safe replacement exists, review source timing.`;
  }
  const busy = sourceMixerControlBusy();
  const shared = document.getElementById("reviewSharedSourceTiming"); if (shared) shared.disabled = busy;
  const independent = document.getElementById("reviewIndependentSourceTiming"); if (independent) independent.disabled = busy || !hasEdit;
  const readiness = document.getElementById("sourceTimingReadiness");
  if (readiness) readiness.textContent = hasEdit
    ? "For independent narration, choose its range and position on the edit timeline; select its audio in step 1. Nothing is looped or frozen."
    : "Independent footage is placed after a draft or manual edit exists. Choosing a layout does not synchronize unrelated recordings.";
  if (target.textContent !== text) target.textContent = text;
  target.dataset.warning = String(warning || Boolean(preview?.requiresB && !preview.available));
  let notice = document.getElementById?.("sourceBCoverageNotice");
  if (!notice && typeof elements.sourceMixerHelp?.after === "function") {
    notice = document.createElement("p"); notice.id = "sourceBCoverageNotice";
    notice.className = "source-range-status";
    elements.sourceMixerHelp.after(notice);
  }
  if (notice) {
    const syncText = sourceSyncDescription(mixer);
    const unconfirmed = syncText.startsWith("Sync unconfirmed:");
    notice.hidden = Boolean(layoutAlert && !layoutAlert.hidden) || (!warning && !unconfirmed);
    notice.textContent = `${warning ? text : ""}${warning && unconfirmed ? " " : ""}${unconfirmed ? syncText : ""}`;
  }
  let review = document.getElementById?.("sourceBReviewPlacement");
  if (!review && state.project.editor_sequence && typeof target.after === "function") {
    review = document.createElement("button");
    review.id = "sourceBReviewPlacement"; review.type = "button"; review.className = "button ghost compact";
    review.textContent = "Review B placement";
    review.addEventListener("click", () => { if (sourceMixerControlBusy()) return; setEditTarget("B"); openSourceReview(); });
    (notice || target).after(review);
  }
  if (review) {
    review.hidden = Boolean(independent) || !state.project.editor_sequence || coverage.full || !hasEdit;
    review.disabled = sourceMixerControlBusy();
  }
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

const setupControlHomes = new Map();
function placeSetupControls() {
  const inSetup = !state.project?.draft;
  for (const [id, dockId] of [["aspectSelect", "setupFormatDock"], ["spokenLanguageSelect", "setupOptionsDock"],
    ["performanceModeSelect", "setupOptionsDock"], ["visualAiSelect", "setupOptionsDock"]]) {
    const control = document.getElementById(id)?.closest("label");
    const dock = document.getElementById(dockId);
    if (!control || !dock) continue;
    if (!setupControlHomes.has(id)) {
      const anchor = document.createComment(`Original home of ${id}`);
      control.before(anchor);
      setupControlHomes.set(id, anchor);
    }
    const anchor = setupControlHomes.get(id);
    if (inSetup) {
      if (control.parentElement !== dock) dock.appendChild(control);
    } else if (control.previousSibling !== anchor) {
      anchor.after(control);
    }
  }
}

function placeSourceMixer(hasSource) {
  placeSetupControls();
  const showBeforeDirector = Boolean(hasSource && !state.project?.draft);
  if (showBeforeDirector && elements.setupSourceMixerDock) {
    if (elements.sourceMixer.parentElement !== elements.setupSourceMixerDock) {
      elements.setupSourceMixerDock.appendChild(elements.sourceMixer);
    }
    elements.setupSourceMixerDock.hidden = false;
    return;
  }
  const layoutHome = elements.studioPanelFraming;
  if (layoutHome && elements.sourceMixer.parentElement !== layoutHome) {
    // Keep one instance of the actual layout controls in the right inspector.
    layoutHome.appendChild(elements.sourceMixer);
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
  for (const key of ["default_layout", "sync_offset", "stack_fit", "screen_fit", "pip_scale", "pip_x", "pip_y"]) {
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
  const saved = await saveSourceMixer({ primary_role: "screen", first_slot: mixer.cameraSlot, stack_fit: "cover", screen_fit: "cover", default_layout: "stacked" }, { silent: true });
  if (!saved || state.project?.id !== projectId) return;
  state.sourceMixerLayout = "stacked";
  applyFramingPreview();
  if (state.project.draft) await applySourceLayout("all", { immediate: true });
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

function embeddedCameraDetection() {
  const preparedVision = state.project?.pre_analysis?.vision?.A;
  const sourceGeneration = String(state.project?.sources?.A?.generation || "");
  const detectorVersion = String(state.system?.vision_analysis_version || EMBEDDED_CAMERA_DETECTOR_VERSION);
  const preparedVisionIsCurrent = sourceGeneration
    && preparedVision
    && preparedVision.version === detectorVersion
    && String(preparedVision.source_generation || "") === sourceGeneration;
  // A successful Director pass is authoritative, including a genuine negative.
  // A failed pass must not mask a successful current-source preparation retry.
  const analyzedVision = state.project?.analysis?.vision;
  const analyzedVisionIsCurrent = analyzedVision?.version === detectorVersion;
  if (analyzedVisionIsCurrent && analyzedVision.available === true) return analyzedVision;
  if (preparedVisionIsCurrent && preparedVision.available === true) return preparedVision;
  return analyzedVisionIsCurrent ? analyzedVision : preparedVisionIsCurrent ? preparedVision : null;
}

function cameraDetectionUnavailableHelp(detection) {
  const explanation = uiCopy(
    "זיהוי המצלמה האוטומטי לא הצליח לבדוק אם קיימת מצלמה בהקלטה.",
    "Automatic camera detection could not run. It did not confirm whether a camera is present.",
  );
  const recovery = detection?.reason === "video_decode_failed"
    ? uiCopy("לא ניתן היה לקרוא את פריימי הווידאו שנדגמו. בדוק שהסרטון המקורי מתנגן ונסה שוב, או סמן את אזור המצלמה ידנית.",
      "The sampled video frames could not be read. Check that the source video plays, then retry detection or mark the camera area manually.")
    : ["opencv_not_installed", "opencv_detector_unavailable"].includes(detection?.reason)
      ? uiCopy("הפעל שוב את התקנת CUTROOM כדי לתקן את רכיב הזיהוי ונסה שוב, או סמן את אזור המצלמה ידנית.",
        "Run CUTROOM setup to repair the detector and retry, or mark the camera area manually.")
      : uiCopy("בדוק את הסרטון המקורי ואת רכיב הזיהוי לפני ניסיון נוסף, או סמן את אזור המצלמה ידנית.",
        "Check the source video and detector before retrying, or mark the camera area manually.");
  return `${explanation} ${recovery}`;
}

function embeddedCameraCandidate() {
  if (state.project?.sources?.B) return null;
  const manual = normalizedEmbeddedGeometry(state.project?.manual?.embedded_camera);
  if (manual) return { ...manual, candidate_source: "manual", manual: true, requires_confirmation: true };
  const vision = embeddedCameraDetection();
  if (vision?.available !== true) return null;
  const candidate = normalizedEmbeddedGeometry(vision?.embedded_camera);
  if (!candidate) return null;
  // Older detectors produced false positives in gameplay HUDs. Only the
  // confirmation-only detector may offer this layout to the user.
  const detectorVersion = String(state.system?.vision_analysis_version || EMBEDDED_CAMERA_DETECTOR_VERSION);
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
  renderProjectSaveState();
  const editor = state.embeddedEditor;
  const active = embeddedCameraIsActive();
  const detection = embeddedCameraDetection();
  if (elements.embeddedCameraState) {
    elements.embeddedCameraState.classList.toggle("active", active && !editor.dirty);
    elements.embeddedCameraState.textContent = editor.error ? "Save failed — retry"
      : editor.dirty ? "Saving…"
      : active ? "Saved"
      : embeddedCameraCandidate()?.candidate_source === "vision" ? "Review camera area"
      : detection && detection.available !== true ? "Automatic detection unavailable"
      : "Mark your camera";
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
    elements.embeddedCameraEditor.open = candidate?.candidate_source === "vision" && !embeddedCameraIsActive();
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
  const detection = embeddedCameraDetection();
  elements.embeddedCameraHelp.textContent = candidate?.candidate_source === "vision"
    ? "Check that the suggested area contains your camera. Moving the frame previews and saves your camera layout automatically."
    : detection && detection.available !== true
      ? cameraDetectionUnavailableHelp(detection)
    : detection?.available === true && !candidate
      ? "Automatic detection found no camera area in the sampled frames. If your recording includes a camera, mark its area manually."
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
  if (!sourceA) {
    for (const video of [elements.previewA, elements.previewB]) {
      video.pause(); video.removeAttribute("src"); video.dataset.url = ""; video.load();
    }
    clearCaptionPreview();
    elements.previewCaption.hidden = true;
    elements.previewCaption.textContent = "";
    state.preview.mode = "edit";
    updatePreviewUI(0);
    return;
  }
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

function renderPreviewAvailability() {
  const recovery=retainedEditStatus();
  const empty=Boolean((recovery || state.project?.editor_sequence) && !previewUsesSourceTime() && !hasTimelineFootage());
  renderRetainedPreview();
  for(const button of [elements.playButton,elements.previewPlay,elements.restartPreview]){
    if(!button)continue;
    if(empty){
      if(!button.dataset.emptyEdit)button.emptyEditTitle=button.getAttribute?.("title") ?? null;
      button.disabled=true;button.dataset.emptyEdit="true";
      button.title=retainedEditIssue() || savedLayerTrackIssue() || "The edited timeline is empty. Add footage or a layer, Undo, or choose Full source to review the original.";
    }else if(button.dataset.emptyEdit){
      button.disabled=false;delete button.dataset.emptyEdit;
      if(button.emptyEditTitle==null)button.removeAttribute("title");else button.setAttribute("title",button.emptyEditTitle);
      delete button.emptyEditTitle;
    }
    const repairing=previewRepairBusy();
    if(repairing){
      if(!button.dataset.previewRepair){button.previewRepairTitle=button.getAttribute?.("title") ?? null;button.previewRepairDisabled=button.disabled;}
      button.dataset.previewRepair="true";button.disabled=true;
      button.title="Preview verification is in progress. Playback stays paused; check or cancel it in the Media pool.";
    }else if(button.dataset.previewRepair){
      delete button.dataset.previewRepair;
      if(!empty){button.disabled=Boolean(button.previewRepairDisabled);if(button.previewRepairTitle==null)button.removeAttribute("title");else button.setAttribute("title",button.previewRepairTitle);}
      delete button.previewRepairDisabled;delete button.previewRepairTitle;
    }
  }
  state.rangeAudition?.sync();
  state.timeline?.reviewMarkers?.sync();
  state.mediaStudio?.rollCut?.refresh();
}

// The timeline range is in edit time, never a source/occurrence selection.
// Do not rescan clip lists every frame. Native Play validates the saved model.
function reviewMarkerSnapshot() {
  const p=state.project, tl=state.timeline, seq=p?.editor_sequence;
  const editor=Boolean(state.studio.open && !elements.resultPanel?.hidden && p?.sources?.A && p.draft && seq?.sequence && !seq.error
    && tl?.project?.id===p.id && tl.project.revision===p.revision);
  return {id:p?.id,view:state.projectViewToken,revision:p?.revision,fps:p?.settings?.fps??30,duration:seq?.duration,
    time:tl?.playhead??0,registry:p?.review_markers,editor,editMode:editor&&!previewUsesSourceTime(),
    busy:editor&&Boolean(foregroundBusy() || state.manualEditBusy || state.transcriptSaving || tl?.gesture || tl?.editPending || tl?.mediaSelectionPending)};
}

async function writeReviewMarker(owner,body) {
  const matches=()=>{const s=reviewMarkerSnapshot();return s.editor&&s.editMode&&!s.busy&&s.id===owner.id
    &&s.view===owner.view&&s.revision===owner.revision&&s.fps===owner.fps&&s.duration===owner.duration;};
  if(!matches()||!requireResolvedExplicitDrafts()||!requireSavedTranscript())throw new Error("Finish pending edits and review the marker position again.");
  await flushProjectSaves(owner.id);
  if(!matches())throw new Error("The edit changed before saving. Reopen the marker panel.");
  const receipt=await api(`/api/projects/${encodeURIComponent(owner.id)}/review-markers`,{method:"POST",body:JSON.stringify(body)});
  if(!matches()||receipt?.project_id!==owner.id||receipt.previous_revision!==owner.revision||receipt.revision!==owner.revision+1
      ||!receipt.review_markers||reviewMarkerRows(receipt.review_markers)===null)return false;
  // The narrow receipt advanced this exact reviewed revision. Do not hydrate the editor:
  // setProject would clear marks/selected clips and disrupt the native program transport.
  state.project={...state.project,revision:receipt.revision,review_markers:receipt.review_markers};
  rememberProjectRevision(state.project);state.timeline.project=editorProject();state.timeline.scheduleDraw();
  state.rangeAudition?.sync();return true;
}

function markedLayerSnapshot(){
  const p=state.project,t=state.timeline,ids=t?.selectedMediaIds?.()||[];let issue="";
  if(ids.length){
    if(!state.studio.open||!p?.draft||!p.editor_sequence||p.editor_sequence.error||t.project?.id!==p.id||t.project.revision!==p.revision)
      issue="Open the current saved edit before marking layers.";
    else if(previewUsesSourceTime()||state.preview.playing||activeEditTarget()!=="edit")issue="Pause Edited video and use the whole-edit target before marking selected layers.";
    else if(document.querySelector("dialog[open]")||t.gesture||t.scrubbing||t.editPending||t.mediaSelectionPending||t.mediaSourceOpening||t.libraryDragActive
      ||state.mediaStudio?.frameEditor?.active||state.embeddedEditor?.dragging)issue="Finish the current selection, dialog or gesture first.";
    else if(rangeInputPending("timeline")||rangeInputPending("layout"))issue="Apply or close the typed range before replacing the marks.";
    else if(state.transcriptSaving||foregroundBusy()||sourceMonitorIssue()||projectSaveStatus().kind!=="saved"||hasUnsavedProjectWork())issue="Finish pending project changes before replacing the marked range.";
  }
  return {project:p,view:state.projectViewToken,ids,profile:state.keyboardProfile,issue};
}
function markReviewedLayers(owner,plan){
  const live=markedLayerSnapshot();if(live.issue||live.view!==owner.view||live.project?.id!==owner.project?.id||live.project?.revision!==owner.project?.revision)return false;
  const current=planMarkedLayers(live.project,live.ids);if(current.issue||current.token!==plan.token)return false;
  // Use the same native range target as I/O and the Range form: remove old
  // layer/automatic-caption targets but do not seek, play, save or rebuild.
  const {start,end}=current.range,range=state.timeline.selectRange(start,end);
  if(range?.start!==start||range?.end!==end||state.manualSelection?.start!==start||state.manualSelection?.end!==end)return false;
  state.markIn=null;state.rangeAudition?.sync();return true;
}
function rangeAuditionSnapshot() {
  const p = state.project, seq = p?.editor_sequence, tl = state.timeline, r = state.manualSelection;
  const available = Boolean(state.studio.open && !elements.resultPanel?.hidden && p?.sources?.A && p.draft
    && seq?.sequence && seq.source_tracks && !seq.error && tl?.project?.id === p.id && tl.project.revision === p.revision);
  const matches = r && tl?.selection?.start === r.start && tl?.selection?.end === r.end;
  return { editor: available, id: p?.id, revision: p?.revision, view: state.projectViewToken,
    duration: seq?.duration, start: matches ? r.start : null, end: matches ? r.end : null,
    editMode: !previewUsesSourceTime(), occurrence: Boolean(tl?.mediaSelection || tl?.captionSelection),
    busy: available && Boolean(elements.playButton?.disabled || tl?.gesture || tl?.editPending
      || tl?.mediaSelectionPending || state.transcriptSaving || foregroundBusy()),
    dirtyRange: rangeInputPending("timeline") || rangeInputPending("layout") };
}

// A long-GOP browser seek may take longer than the normal 120 ms drift window.
// At loop In, wait for the actual active sources/layers to have current data before
// starting their shared clock. Re-seeking them every frame can starve both decoders and sound.
function rangeAuditionMediaReady() {
  const nodes = [elements.previewA, elements.previewB].filter(el => el?.src && (!el.hidden || !el.muted));
  for (const item of state.mediaStudio?.players?.values() || []) nodes.push(item.element);
  for (const el of nodes) {
    if (!el) return null;
    if (el.tagName === "IMG") {
      if (!el.complete) return false;
      if (!el.naturalWidth) return null;
    } else {
      if (!["AUDIO", "VIDEO"].includes(el.tagName) || el.error || !Number.isInteger(el.readyState)) return null;
      if (el.seeking || el.readyState < 2) return false;
    }
  }
  return true; // A genuine empty gap needs no decoder.
}

function togglePreview() {
  if (!state.project?.sources?.A || foregroundBusy() || elements.resultPanel.hidden) return;
  if (previewUsesIndependentTracks() ? !state.preview.playing : elements.previewA.paused) playPreview(); else pausePreview();
}

async function playPreview() {
  state.mediaStudio?.pauseSourceMonitor?.();
  state.sourceReview?.pausePreview?.();
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

function pauseAllMedia(except = null) {
  state.rangeAudition?.clear();
  state.mediaStudio?.pause();
  state.preview.playRequest += 1;
  state.preview.clock?.pause();
  if (state.preview.frame != null) cancelAnimationFrame(state.preview.frame);
  state.preview.frame = null;
  document.querySelectorAll("video, audio").forEach((media) => {
    if(media===except)return;
    try { media.pause(); } catch (_error) { /* A detached preview should not block navigation. */ }
  });
  setPreviewPlaying(false);
}

function releaseMediaHandles() {
  state.chromaPlayers?.forEach(player => player.dispose()); state.chromaPlayers?.clear();
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
  if(playing){state.mediaStudio?.pauseSourceMonitor?.();state.sourceReview?.pausePreview?.();}
  const transportChanged=state.preview.playing!==playing;
  state.preview.playing = playing;
  if(transportChanged){state.trackLift?.sync();state.mediaStudio?.clipOpacity?.refresh();state.markedLayers?.sync();}
  if(!playing)requestEditingPositionCapture();
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
  if(!state.preview.playing)requestEditingPositionCapture();
  const mapped = editTime ?? (previewUsesSourceTime() && state.project?.editor_sequence ? previewSourceToEditTime(time) : time);
  if (mapped == null) return;
  state.preview.editCursor = Math.max(0, Math.min(editorDuration(), Number(mapped) || 0));
  state.preview.editCursorProject = state.project?.id;
  state.timeline?.setPlayhead?.(state.preview.editCursor);
  state.mediaStudio?.rollCut?.refresh();
  if (state.project?.editor_sequence && elements.studioPanelFraming?.hidden === false && !state.framingDraft && !state.manualEditBusy) {
    const slot = elements.cropSourceSelect?.value || "A", scope = framingScope(slot);
    const key = `${state.project.id}:${slot}:${scope?.start}:${scope?.end}`;
    if (state.framingScopeKey !== key) loadCropControls(slot, false);
  }
  renderSplitAvailability(state.preview.editCursor);
  renderDuplicateAvailability(state.preview.editCursor);
  renderLayerGroupControls(state.preview.editCursor);
  state.mediaStudio?.updateLibraryAvailability?.(state.preview.editCursor);
  state.mediaStudio?.syncSourceMonitor?.();
  state.sourceReview?.sync?.();
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
  const loopTarget = state.rangeAudition?.next(time);
  if (loopTarget === false) { pauseAllMedia(); return; }
  if (loopTarget && typeof loopTarget === "object") {
    time = clock.seek(loopTarget.at);
    if (loopTarget.hold) { state.preview.frame = requestAnimationFrame(tickIndependentPreview); return; }
  }
  if (Number.isFinite(loopTarget)) {
    // Use the ordinary seek path to update both source players, sound, overlays,
    // captions and playhead, including a loop whose Out is the end of the edit.
    seekPreview(loopTarget, undefined, true);
    if (state.preview.playing) state.preview.frame = requestAnimationFrame(tickIndependentPreview);
    return;
  }
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
  const retimed = Object.hasOwn(point.clip, "video_speed") || point.clip.video_source_start != null;
  // A speed-1 picture sharing the audible source clock can use the container's
  // native end-of-picture hold while its longer audio continues. Pausing that
  // player at the last picture would also pause the selected source audio.
  const nativeAudioClock = !video.muted && speed === 1 && Math.abs(rawPictureTime - point.sourceTime) < .000001;
  const pictureTime = retimed && !nativeAudioClock ? Math.max(0, Math.min(rawPictureTime, limit > 0 ? Math.max(0,limit-.04) : rawPictureTime)) : point.sourceTime;
  video.playbackRate = speed;
  if (forceSeek || changedClip || Math.abs(video.currentTime - pictureTime) > .12) {
    try { video.currentTime = pictureTime; } catch { /* loadedmetadata/timeupdate can retry. */ }
  }
  if (retimed && !nativeAudioClock && limit > 0 && rawPictureTime >= limit-.035) {
    if (state.preview[pendingKey]) state.preview[pendingKey].cancelled = true;
    video.pause();
    return;
  }
  if (!state.preview.playing || state.rangeAudition?.preparing) { if (!video.paused) video.pause(); return; }
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
  const sourceAAvailable = !independent || Boolean(pointA && sourceAVideoDuration > 0
    && (Object.hasOwn(pointA.clip, "video_speed") || pointA.sourceTime < sourceAVideoDuration));
  const offset = mixer.syncOffset;
  const sourceBTime = independent ? pointB?.sourceTime : globalTime - offset;
  const sourceBVideoDuration = Number(sourceB?.video_duration);
  const sourceBDuration = Number.isFinite(sourceBVideoDuration) && sourceBVideoDuration > 0
    ? sourceBVideoDuration : Number(sourceB?.duration || 0);
  const sourceBAvailable = Boolean(sourceB && (!independent || pointB) && sourceBTime >= 0 && sourceBDuration > 0
    && (independent && Object.hasOwn(pointB.clip, "video_speed") || sourceBTime < sourceBDuration));
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
  const missingB = Boolean(sourceB && requiresB && !sourceBAvailable);
  const libraryPicture = camera === "gap" && state.preview.mode !== "source" && state.mediaStudio?.videoAt?.(globalTime);
  elements.cameraBadge.textContent = missingB && camera === "A" ? "A · B unavailable" : camera === "gap" ? libraryPicture ? "VIDEO" : "GAP" : cameraLabels[camera] || singleSlot;
  elements.cameraBadge.dataset.missingSource = missingB ? "B" : "";
  elements.cameraBadge.title = libraryPicture ? "Added project video on the edit timeline." : missingB ? "Source B has no mapped footage at this playhead. Check B coverage and source alignment before export." : "";
  const coverageKey = `${project.id}:${requiresB}:${sourceBAvailable}:${camera}`;
  if (state.preview.bCoverageKey !== coverageKey) {
    state.preview.bCoverageKey = coverageKey;
    renderSourceBCoverage(mixer, { requiresB, available: sourceBAvailable, fallback: camera });
  }
  // With one recording and no composition, the "A" label only covers the video.
  elements.cameraBadge.hidden = !state.project?.sources?.B && !cameraLabels[camera] && camera !== "gap";

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

function seekPreview(time, editTime, rangeWrap = false) {
  if (!rangeWrap) state.rangeAudition?.clear();
  invalidateEditingPositionReturn();
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
  state.markedLayers?.sync();state.trackLift?.sync();state.mediaStudio?.clipOpacity?.refresh();
  state.mediaStudio?.updateAudioSourceAvailability?.();
  renderPreviewAvailability();
  seekSourcePreview(editTime);
  state.transcriptSectionsUI?.refresh?.();
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
  const recovery=retainedEditStatus();if(recovery?.duration!==null && recovery)return recovery.duration;
  const project = editorProject();
  if (state.project?.editor_sequence) return Number(state.project.editor_sequence.duration) || 0;
  return Number(project?.draft?.output_duration || project?.sources?.A?.duration || 0);
}

function hasTimelineFootage() {
  if(retainedEditStatus())return false;
  if(savedLayerTrackIssue())return false;
  if (!state.project?.editor_sequence) return Boolean(state.project?.draft);
  const project = editorProject();
  // Bypassing an occurrence does not empty the edit. Picture visibility is a
  // separate question: retained audio/text and disabled layers remain editable.
  return ["A", "B"].some((slot) => trackClips(project, slot).length > 0)
    || Boolean(project?.manual?.media_clips?.length || project?.manual?.text_clips?.length);
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

function renderRetainedPreview() {
  const recovery=retainedEditStatus(), blocked=Boolean(recovery && !previewUsesSourceTime());
  if(elements.retainedEditPreview){
    elements.retainedEditPreview.hidden=!blocked;
    if(blocked)elements.retainedEditPreview.textContent=`Saved timeline awaiting resume${recovery.duration===null ? "" : ` · ${formatTime(recovery.duration)}`}. ${recovery.issue || "Your saved arrangement is retained. Use Resume retained edit to continue."}`;
  }
  if(blocked){
    if(elements.previewTime)elements.previewTime.textContent=recovery.duration===null ? "Saved timeline" : `Saved ${formatTime(recovery.duration)}`;
    if(elements.previewModeHint)elements.previewModeHint.textContent="Resume for edited playback, or choose Full source to review the original.";
    if(elements.previewSeek){elements.previewSeek.disabled=true;elements.previewSeek.dataset.retainedEdit="true";}
  }else if(elements.previewSeek?.dataset.retainedEdit){elements.previewSeek.disabled=false;delete elements.previewSeek.dataset.retainedEdit;}
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
  if (elements.previewModeHint && Object.values(state.project?.manual?.chroma_key || {}).some(settings => settings?.enabled)) {
    elements.previewModeHint.textContent += ` ${t(sourceMode ? "chromaOriginalPlayback" : "chromaLivePlayback")}`;
  }
  updatePreviewCaption(time);
  state.colorMotion?.sync(sourceToOutputTime(time));
  renderRetainedPreview();
}

function captionPreviewChunk(segment, sourceTime, wordsPerCaption) {
  const words = Array.isArray(segment?.words) ? segment.words : [];
  const chunks = [[]];
  for (const word of words) {
    if (!String(word?.word || "").trim() || !(Number(word.end) > Number(word.start))) continue;
    const chunk = chunks.at(-1);
    // Match burned/SRT captions: a long pause starts another phrase, and each
    // phrase is visible only between its first and last spoken word.
    if (chunk.length && (Number(word.start) - Number(chunk.at(-1).end) > 0.75 || chunk.length >= wordsPerCaption)) chunks.push([]);
    chunks.at(-1).push(word);
  }
  return chunks.find(chunk => chunk.length && sourceTime >= Number(chunk[0].start) && sourceTime < Number(chunk.at(-1).end)) || [];
}

function captionPreviewText(segment, sourceTime, wordsPerCaption) {
  if (!segment || sourceTime < Number(segment.start) || sourceTime >= Number(segment.end)) return "";
  if (Array.isArray(segment.words) && segment.words.length) {
    return captionPreviewChunk(segment, sourceTime, wordsPerCaption).map(word => String(word.word).trim()).join(" ").trim();
  }
  // Without word timings the export shows the whole segment. Inventing timed
  // subphrases here would promise a different result from the rendered video.
  return String(segment.text || "").trim();
}

// Automatic captions are timeline items from the server (editor_captions): the
// items the export burns and writes to SRT, with the user's edits applied.
function captionItems() {
  return Array.isArray(state.project?.editor_captions) ? state.project.editor_captions : [];
}

function selectedCaptionItem() {
  return captionItems().find(item => item.id === state.captionSelection) || null;
}

async function selectCaptionItem(id, { seek = false, focus = false, reveal = true } = {}) {
  const next = id || null;
  const request = beginInspectorSelection();
  if (!(await prepareInspectorSelection(request))) { restoreInspectorSelection(request); return false; }
  if (next && state.textStudio?.selected && await state.textStudio.select(null) === false) { restoreInspectorSelection(request); return false; }
  if (!inspectorSelectionCurrent(request) || state.captionDirty) { restoreInspectorSelection(request); return false; }
  if (next) state.mediaStudio?.select(null);
  state.captionSelection = next;
  state.captionDirty = false;
  state.captionStatus = "";
  state.timeline?.selectCaption?.(next, false);
  const item = selectedCaptionItem();
  if (item) {
    pauseAllMedia();
    state.timeline?.clearSelection();
    selectAdvancedTab("transcript");
    // Timeline pointerdown already computed its gesture time. Revealing a
    // partially offscreen caption there would change scrollLeft mid-gesture.
    if (reveal) state.timeline?.revealCaption?.(item.id);
    const time = previewTimelineTime();
    if (seek || time < item.start || time >= item.end) seekSourcePreview(item.start + Math.min(.02, (item.end - item.start) / 2));
  }
  renderCaptionInspector();
  if (item) elements.captionItemEditor?.scrollIntoView({block:"nearest", inline:"nearest"});
  if (item && focus) { elements.captionItemText?.focus(); elements.captionItemText?.select(); }
  updatePreviewCaption(previewPlaybackTime());
  return true;
}

function renderCaptionInspector() {
  renderProjectSaveState();
  const editor = elements.captionItemEditor;
  if (!editor) return;
  const items = captionItems(), item = selectedCaptionItem();
  if (state.captionSelection && !item) { state.captionSelection = null; state.captionDirty = false; state.captionStatus = ""; }
  // Typing/discarding changes only the saved-preview explanation, never its pixels.
  if (state.captionPreview) renderCaptionPreviewStatus(state.captionPreviewResult);
  editor.hidden = !item;
  if (!item) return;
  const uses = items.filter(entry => entry.segment_id === item.segment_id).length;
  const notes = [item.hidden && "Hidden", item.corrected && "Transcript fixed", item.local_text && "Own text",
    item.timing_changed && "Retimed", (item.style || item.position || item.scale) && "Own style", uses > 1 && `Speech used ${uses}×`].filter(Boolean);
  elements.captionItemMeta.textContent = `${formatTime(item.start, true)} – ${formatTime(item.end, true)}${notes.length ? ` · ${notes.join(" · ")}` : ""}`;
  if (!state.captionDirty) {
    elements.captionItemText.value = item.text;
    const scope = item.local_text ? "item" : "source";
    editor.querySelectorAll('input[name="captionItemScope"]').forEach(input => { input.checked = input.value === scope; });
    elements.captionItemStart.value = Number(item.start).toFixed(2);
    elements.captionItemEnd.value = Number(item.end).toFixed(2);
    elements.captionItemStyle.value = item.style || "";
    elements.captionItemPosition.value = item.position || "";
    elements.captionItemScale.value = item.scale ?? "";
  }
  elements.captionItemSourceHelp.textContent = uses > 1
    ? `Fixes the transcript in all ${uses} places this speech is used.`
    : "Fixes the transcript; a new AI draft keeps the fix.";
  const busy = foregroundBusy() || state.manualEditBusy || state.transcriptSaving;
  const index = items.indexOf(item);
  const changed = item.local_text || item.timing_changed || item.hidden || item.style || item.position || item.scale;
  elements.captionItemHide.textContent = item.hidden ? "Show caption" : "Hide caption";
  elements.captionItemHide.disabled = busy;
  elements.captionItemReset.disabled = busy || !changed;
  elements.captionItemReset.title = "Remove this caption's own text, timing, style and visibility. Transcript fixes stay.";
  elements.captionItemSave.disabled = busy || !state.captionDirty;
  elements.captionItemPrevious.disabled = index <= 0;
  elements.captionItemNext.disabled = index < 0 || index >= items.length - 1;
  elements.captionItemStatus.textContent = state.captionStatus || (state.captionDirty ? "Unsaved changes. Save or press Escape before editing another timeline item." : "");
}

async function runCaptionAction(action, detail, {saveDraft = false} = {}) {
  if (state.captionDirty && !saveDraft) { state.captionStatus = "Save or discard the caption text before changing its timeline item."; renderCaptionInspector(); return null; }
  const projectId = state.project?.id, captionId = state.captionSelection, bufferRevision = state.captionBufferRevision || 0;
  state.captionStatus = "Saving…";
  renderCaptionInspector();
  const result = await applyManualEdit(action, detail);
  if (projectId !== state.project?.id || captionId !== state.captionSelection) return result;
  const sameBuffer = bufferRevision === (state.captionBufferRevision || 0);
  state.captionStatus = result && sameBuffer ? "Saved" : state.captionDirty ? "Unsaved changes" : "";
  if (result && sameBuffer) state.captionDirty = false;
  renderCaptionInspector();
  return result;
}

async function saveCaptionItem() {
  const item = selectedCaptionItem();
  if (!item) return null;
  const fail = (message) => { state.captionStatus = message; renderCaptionInspector(); return null; };
  const text = elements.captionItemText.value.trim();
  if (!text) return fail("Caption text cannot be empty. Use Hide caption to remove it.");
  const scope = elements.captionItemEditor.querySelector('input[name="captionItemScope"]:checked')?.value || "source";
  const detail = { caption_id: item.id };
  if (text !== item.text || (scope === "source" && item.local_text)) Object.assign(detail, { text, scope });
  const start = Number(elements.captionItemStart.value), end = Number(elements.captionItemEnd.value);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return fail("Enter the start and end in seconds.");
  if (Math.abs(start - item.start) > .004 || Math.abs(end - item.end) > .004) Object.assign(detail, { start, end });
  for (const [key, element] of [["style", elements.captionItemStyle], ["position", elements.captionItemPosition]]) {
    if (element.value !== (item[key] || "")) detail[key] = element.value;
  }
  const scaleText = String(elements.captionItemScale.value ?? "").trim();
  if (scaleText && !Number.isFinite(Number(scaleText))) return fail("Size is a percentage from 75 to 150.");
  const scale = scaleText ? Math.round(Number(scaleText)) : "";
  if (scale !== (item.scale ?? "")) detail.scale = scale;
  if (Object.keys(detail).length === 1) { state.captionDirty = false; renderCaptionInspector(); return null; }
  return runCaptionAction("caption_update", detail, {saveDraft:true});
}

function moveCaptionSelection(step) {
  const items = captionItems(), index = items.findIndex(item => item.id === state.captionSelection);
  const next = items[index + step];
  if (next) void selectCaptionItem(next.id, { seek: true });
}

function bindCaptionItemEvents() {
  ensureCaptionPreview();
  const editor = elements.captionItemEditor;
  if (!editor) return;
  const markDirty = () => { state.captionBufferRevision = (state.captionBufferRevision || 0) + 1; state.captionDirty = true; state.captionStatus = ""; renderCaptionInspector(); };
  editor.addEventListener("input", markDirty);
  editor.addEventListener("change", markDirty);
  editor.addEventListener("submit", (event) => { event.preventDefault(); void saveCaptionItem(); });
  elements.captionItemText.addEventListener("keydown", (event) => {
    if (event.isComposing) return;
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void saveCaptionItem(); }
    else if (event.key === "Escape" && state.captionDirty) {
      event.preventDefault(); event.stopPropagation();
      state.captionDirty = false; state.captionStatus = ""; renderCaptionInspector();
    }
  });
  elements.captionItemClose.addEventListener("click", () => { void selectCaptionItem(null); });
  elements.captionItemHide.addEventListener("click", () => {
    const item = selectedCaptionItem();
    if (item) void runCaptionAction("caption_visibility", { caption_id: item.id, hidden: !item.hidden });
  });
  elements.captionItemReset.addEventListener("click", () => {
    const item = selectedCaptionItem();
    if (!item) return;
    state.captionDirty = false;
    void runCaptionAction("caption_reset", { caption_id: item.id });
  });
  elements.captionItemPrevious.addEventListener("click", () => moveCaptionSelection(-1));
  elements.captionItemNext.addEventListener("click", () => moveCaptionSelection(1));
  // The caption on the video is the same item: clicking it selects it for editing.
  const selectFromPreview = (event) => {
    // Canonical cue nodes own their per-item events; do not double-select the reused primary.
    if (elements.previewCaption?.hasAttribute?.("data-caption-cue")) return;
    const id = elements.previewCaption?.dataset.captionId;
    if (!id) return;
    event.stopPropagation();
    if (event.type === "click") void selectCaptionItem(id, { focus: true });
  };
  elements.previewCaption?.addEventListener("pointerdown", selectFromPreview);
  elements.previewCaption?.addEventListener("click", selectFromPreview);
}

// One caption line at a time, split exactly as the export splits it: by
// pauses, words per caption and at most two lines of about 42 characters.
const MAX_CAPTION_CHARACTERS = 84;
function captionCharacterParts(text) {
  const parts = [];
  for (const word of String(text || "").split(/\s+/).filter(Boolean)) {
    if (parts.length && parts.at(-1).length + 1 + word.length <= MAX_CAPTION_CHARACTERS) parts[parts.length - 1] += ` ${word}`;
    else parts.push(word);
  }
  return parts.length ? parts : [String(text || "")];
}

function captionItemLine(item, time, wordsPerCaption) {
  const words = Array.isArray(item.words) ? item.words : [];
  if (!words.length) {
    if (time < item.start || time >= item.end) return null;
    // Without word timing, each part's time is its share of the characters.
    const parts = captionCharacterParts(item.text), total = parts.reduce((sum, part) => sum + part.length, 0) || 1;
    let cursor = item.start;
    for (const [index, part] of parts.entries()) {
      const end = index === parts.length - 1 ? item.end : cursor + (item.end - item.start) * part.length / total;
      if (time >= cursor && time < end) return { text: part, words: [] };
      cursor = end;
    }
    return null;
  }
  const chunks = [[]];
  for (const word of words) {
    const chunk = chunks.at(-1);
    const length = chunk.reduce((sum, entry) => sum + entry[2].length + 1, 0) + word[2].length;
    if (chunk.length && (word[0] - chunk.at(-1)[1] > 0.75 || chunk.length >= wordsPerCaption || length > MAX_CAPTION_CHARACTERS)) chunks.push([]);
    chunks.at(-1).push(word);
  }
  for (const [index, chunk] of chunks.entries()) {
    let start = chunk[0][0], end = chunk.at(-1)[1];
    // A moved caption edge keeps the caption on screen until that edge.
    if (item.timing_changed && index === 0) start = item.start;
    if (item.timing_changed && index === chunks.length - 1) end = item.end;
    if (time >= start && time < end) return { text: chunk.map(word => word[2]).join(" "), words: chunk };
  }
  return null;
}

function ensureCaptionPreview() {
  if (!state.captionPreview && typeof initCaptionPreview === "function" && elements.previewStage && elements.previewCaption) {
    state.captionPreview = initCaptionPreview(elements.previewStage, elements.previewCaption, {
      select: (id) => { void selectCaptionItem(id, { focus: true }); },
    });
  }
  return state.captionPreview;
}

function clearCaptionPreview() {
  state.captionPreview?.clear();
  state.captionPreviewResult = null;
  if (elements.captionPreviewStatus) {
    elements.captionPreviewStatus.hidden = true;
    elements.captionPreviewStatus.textContent = "";
    delete elements.captionPreviewStatus.dataset.state;
  }
}

function captionPreviewSettingsMatch(scene) {
  const queue = state.saveQueues.get(state.project?.id);
  const sceneFields = ["caption_style", "caption_position", "caption_scale", "caption_words_per_line", "aspect", "resolution", "fps"];
  // Reconciled project settings may already include a later queued patch. They
  // cannot certify that the scene from the earlier response includes that intent.
  for (const patch of [queue?.pending, queue?.inFlightPatch]) {
    if (patch?.settings && sceneFields.some(key => Object.hasOwn(patch.settings, key))) return false;
  }
  const settings = captionSettingsFromControls(), saved = scene?.settings;
  if (!saved || saved.caption_style !== settings.style || saved.caption_position !== settings.position
      || saved.caption_scale !== settings.scale || saved.caption_words_per_line !== settings.words) return false;
  // A changed output frame/fps also needs its newly accepted scene, not hidden stale geometry.
  for (const [key, control] of [["aspect", elements.aspectSelect], ["resolution", elements.resolutionSelect], ["fps", elements.fpsSelect]]) {
    const value = state.project?.settings?.[key];
    if (control?.value && value !== undefined && String(control.value) !== String(value)) return false;
  }
  return true;
}

function renderCaptionPreviewStatus(result) {
  const node = elements.captionPreviewStatus;
  if (!node) return;
  let message = "", kind = "saved";
  if (captionBurnEnabled() && state.project?.draft && !previewUsesSourceTime()) {
    if (!result?.available) {
      message = result?.issue || "Caption preview is unavailable for this edit. Review the saved project before exporting.";
      kind = "unavailable";
    } else if (state.captionDirty) {
      message = "Showing the saved subtitle plan. Save or discard the caption text before it appears in this preview.";
      kind = "pending";
    } else if (!captionPreviewSettingsMatch(state.project.caption_preview)) {
      message = "Showing saved subtitle settings while your changes save. Unsaved caption text is not included.";
      kind = "pending";
    } else {
      message = result.collisionApproximate
        ? "All active subtitles are shown. Overlapping subtitle placement is approximate in the browser; export uses its subtitle renderer."
        : "Subtitle timing, size and layer order follow the saved export plan. Browser font shaping and wrapping remain approximate.";
    }
  }
  if (node.textContent !== message) node.textContent = message;
  node.hidden = !message;
  node.dataset.state = kind;
}

function renderCaptionItemPreview(time) {
  const controller = ensureCaptionPreview();
  if (controller) {
    const result = controller.render(state.project?.caption_preview, time, {
      projectId: state.project?.id, revision: state.project?.revision,
      selectedId: state.captionSelection, enabled: captionBurnEnabled() && Boolean(state.project?.draft),
    });
    state.captionPreviewResult = result;
    renderCaptionPreviewStatus(result);
    return;
  }
  // Isolated legacy hosts retain their previous single-cue preview. Current browser hosts
  // always use the versioned scene; missing/malformed scenes never fall back to this path.
  const caption = elements.previewCaption, settings = captionSettingsFromControls();
  const active = captionItems().filter(item => !item.hidden && time >= item.start && time < item.end);
  const item = active.at(-1);
  const style = item?.style || settings.style, position = item?.position || settings.position, scale = item?.scale || settings.scale;
  const limit = style === "highlight" ? Math.min(settings.words, HIGHLIGHT_WORDS_PER_CAPTION) : settings.words;
  const line = item ? captionItemLine(item, time, limit) : null;
  caption.dataset.captionStyle = style;
  caption.dataset.captionPosition = position;
  caption.dataset.captionLayout = cameraAt(time);
  caption.style.setProperty("--caption-preview-scale", String(scale / 100));
  caption.classList.toggle("caption-selected", Boolean(line && item.id === state.captionSelection));
  if (line) caption.dataset.captionId = item.id; else delete caption.dataset.captionId;
  const text = line?.text || "";
  // Estimated word timing (a corrected text with a new word count) is never coloured.
  const activeWord = style === "highlight" && line?.words.length && !item.estimated_words && !RTL_CHARACTERS.test(text)
    ? Math.max(0, line.words.findLastIndex(word => time >= word[0])) : -1;
  if (activeWord >= 0) {
    caption.replaceChildren(...line.words.flatMap((word, index) => {
      const span = document.createElement("span");
      span.textContent = word[2];
      if (index === activeWord) span.className = "caption-active-word";
      return index ? [" ", span] : [span];
    }));
  } else {
    caption.textContent = text;
  }
  caption.hidden = !text;
}

function updatePreviewCaption(sourceTime) {
  const project = playbackProject();
  if (!elements.previewCaption) return;
  if (!previewUsesSourceTime() && (ensureCaptionPreview() || captionBurnEnabled() && Array.isArray(state.project?.editor_captions))) {
    renderCaptionItemPreview(sourceToOutputTime(sourceTime));
    return;
  }
  // Full-source inspection plays the original recording, outside the edit.
  // Release every canonical cue and restore the primary node before legacy source rendering.
  clearCaptionPreview();
  delete elements.previewCaption.dataset.captionId;
  elements.previewCaption.classList.remove("caption-selected");
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
  const highlight = captionSettings.style === "highlight";
  const wordsPerCaption = highlight ? Math.min(captionSettings.words, HIGHLIGHT_WORDS_PER_CAPTION) : captionSettings.words;
  const text = captionPreviewText(segment, transcriptTime, wordsPerCaption);
  elements.previewCaption.dataset.captionStyle = captionSettings.style;
  elements.previewCaption.dataset.captionPosition = captionSettings.position;
  elements.previewCaption.dataset.captionLayout = cameraAt(sourceTime);
  elements.previewCaption.style.setProperty("--caption-preview-scale", String(captionSettings.scale / 100));
  const active = highlight && !RTL_CHARACTERS.test(text) ? captionActiveWord(segment, transcriptTime, wordsPerCaption) : -1;
  if (active >= 0) {
    elements.previewCaption.replaceChildren(...text.split(" ").flatMap((word, index) => {
      const span = document.createElement("span");
      span.textContent = word;
      if (index === active) span.className = "caption-active-word";
      return index ? [" ", span] : [span];
    }));
  } else {
    elements.previewCaption.textContent = text;
  }
  elements.previewCaption.hidden = !text;
}

// Word highlight shows a few words at a time and colours the one being spoken,
// matching the export. Right-to-left lines stay plain, as they do in the export.
const HIGHLIGHT_WORDS_PER_CAPTION = 4;
const RTL_CHARACTERS = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
function captionActiveWord(segment, sourceTime, wordsPerCaption) {
  const chunk = captionPreviewChunk(segment, sourceTime, wordsPerCaption);
  // Export holds the current highlight until the next word starts, including
  // short pauses within a phrase. A long pause has no active caption.
  return chunk.findLastIndex(word => sourceTime >= Number(word.start));
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

function openStudioTab(tab, { transcriptRecoveryOwner = null } = {}) {
  if (!["timeline", "framing", "transcript", "audio", "media", "settings"].includes(tab)) return false;
  if (!state.project?.draft && state.project?.settings?.workflow !== "manual" && !retainedEditStatus()) { toast(t("studioNeedsDraft")); return false; }
  const recoveryOwner = tab === "transcript" ? transcriptRecoveryOwner : null;
  const project = state.project, viewToken = state.projectViewToken;
  const current = () => !recoveryOwner || state.project === project && state.projectViewToken === viewToken
    && transcriptBatchOwner() === recoveryOwner && !foregroundBusy({ transcriptRecoveryOwner: recoveryOwner });
  if (foregroundBusy({ transcriptRecoveryOwner: recoveryOwner })) { toast(t("directorBusy")); return false; }
  pauseAllMedia();
  // Only the already-owned, read-only recovery reveal may ignore its own fence.
  // Synchronous display callbacks must not continue into a newer project/view.
  if (!current()) return false;
  setAdvanced(true);
  if (!current()) return false;
  selectAdvancedTab(tab);
  if (!current()) return false;
  $(`.advanced-tabs button[data-tab="${tab}"]`)?.focus();
  return current();
}

function openStabilizationTools() {
  const tool = state.stabilizationStudio;
  if (!tool || !openStudioTab("media")) return false;
  const slot = elements.cropSourceSelect?.value;
  if (state.project?.sources?.[slot]) tool.source.value = slot;
  tool.node.open = true;
  tool.render();
  tool.node.scrollIntoView({block:"nearest",inline:"nearest"});
  tool.source.focus({preventScroll:true});
  return true;
}

function setAdvanced(open) {
  if(!open)captureEditingPosition();
  const nextOpen = Boolean(open);
  if(!nextOpen){state.mediaStudio?.closeSourceMonitor?.();closePrimarySourceReview();closeSourceInsert();elements.advancedPanel?.workbenchController?.leaveEditor?.();}
  if (nextOpen === state.studio.open) return;
  if (nextOpen && !state.project?.draft && state.project?.settings?.workflow !== "manual" && !retainedEditStatus()) {
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
    state.firstRecordingGuide?.sync();
    renderAiDraftNotice();
    renderDirectorOutcomeNotice();
    updatePreviewUI(previewPlaybackTime());
    dockRuntimeStatus();
    elements.advancedButton.setAttribute("aria-expanded", "true");
    state.timeline.setProject(editorProject());
    state.rangeAudition?.sync();
    if(!retainedEditStatus())applyFramingPreview();
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
  state.firstRecordingGuide?.sync();
  renderAiDraftNotice();
  renderDirectorOutcomeNotice();
  updatePreviewUI(previewPlaybackTime());
  dockRuntimeStatus();
  state.sourceMixerPreviewLayout = null;
  syncSecondaryPreview(previewPlaybackTime());
  elements.advancedButton.setAttribute("aria-expanded", "false");
  window.scrollTo({ top: state.studio.scrollY, behavior: "auto" });
}

// These controls change only the next analysis, not the saved timeline or
// current render settings. Goal/style/layout/audio changes can also change
// output behavior, so unknown or mixed changes retain the rebuild safeguard.
function exportRequiresDraftRebuild() {
  const draftOnly = new Set(["brief", "rough-cut fallback", "pace", "language",
    "performance", "visual_ai", "duration intent", "duration"]);
  return [...state.draftDirtyReasons].some((reason) => !draftOnly.has(reason));
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
  if (dirty && !exportRequiresDraftRebuild()) {
    elements.draftRebuildTitle.textContent = "AI preferences pending";
    elements.draftRebuildText.textContent = "Your current edit can still be exported. Rebuild only to apply these preferences to a new AI draft.";
  }
  elements.rebuildDraftButton.textContent = uiCopy("בנה Draft מחדש", "Rebuild Draft");
  $$('[data-rebuild-chip]').forEach((chip) => { chip.textContent = uiCopy("דורש Rebuild", "Rebuild Draft"); });
  updateStudioStatus();
  renderDraftActions();
  renderGameplayMoments();
}

async function rebuildDraftFromStudio() {
  if (!state.project?.draft || !state.draftDirtyReasons.size) return;
  pauseAllMedia();
  if(state.studio.open)elements.advancedPanel?.workbenchController?.setPane("ai");
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
  const recovery=retainedEditStatus();
  if(recovery){elements.studioDraftStatus.textContent=`Saved timeline${recovery.duration===null ? "" : ` · ${formatTime(recovery.duration)}`} · Resume required`;return;}
  const draft = editorProject()?.draft;
  if (!draft) {
    elements.studioDraftStatus.textContent = state.project?.settings?.workflow === "manual"
      ? "Empty timeline · Import a video to begin" : "";
    return;
  }
  const selected = elements.aspectSelect?.value || state.project?.settings?.aspect || draft.aspect;
  const aspect = selected === "source" ? sourceAspect() : (selected || "");
  const dirty = state.draftDirtyReasons.size ? ` · ${uiCopy("נדרש Rebuild", "Rebuild required")}` : "";
  const status = dirty && !exportRequiresDraftRebuild() ? " \u00b7 AI preferences pending" : dirty;
  elements.studioDraftStatus.textContent = `${formatTime(draft.output_duration || 0)} · ${aspect}${status}`;
}

function selectEditTool(tool) {
  const effects = tool === "effects";
  document.getElementById("editClipTools").hidden = effects;
  document.getElementById("editVideoEffects").hidden = !effects;
  $$('[data-edit-tool]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.editTool === tool)));
  if (effects) followChromaSelection();
  elements.advancedPanel?.workspaceController?.setEditEffects(effects);
  document.getElementById('studioInspector').scrollTop = 0;
  if (window.matchMedia?.("(max-width: 899px), (max-height: 600px)").matches) {
    document.getElementById(effects ? 'editVideoEffects' : 'editClipTools').scrollIntoView({block:'start', inline:'nearest'});
  }
}

function followChromaSelection() {
  const tool = state.chromaStudio, selected = tool?.options.selectedTarget?.();
  if (selected && tool.validSource(selected) && tool.source.value !== selected && !tool.saving) {
    tool.source.value = selected; tool.source.onchange();
  }
}

function selectAdvancedTab(tab, {reveal=true} = {}) {
  invalidateEditingPositionReturn();
  if(tab!=="media")state.mediaStudio?.closeSourceMonitor?.();
  if(tab!=="media")closePrimarySourceReview();
  if(tab!=="timeline")closeSourceInsert();
  // The project library is a stable left anchor. Existing context libraries
  // move, with their handlers intact, beside their tools in the right pane.
  for (const [libraryId,panelId] of [["studioShelfCaptions","studioPanelTranscript"],["studioShelfOutput","studioPanelSettings"]]) {
    const library = document.getElementById(libraryId), panel = document.getElementById(panelId);
    if (library?.parentElement && panel && library.parentElement !== panel) { library.classList.add("studio-context-library"); panel.prepend(library); }
  }
  document.querySelectorAll("[data-shelf]").forEach(shelf => { shelf.hidden = shelf.id === "studioShelfMedia" ? false : !shelf.dataset.shelf.split(" ").includes(tab); });
  elements.advancedPanel?.workspaceController?.setWorkspace(tab);
  if(reveal)elements.advancedPanel?.workspaceController?.showInspector();
  if (tab === "audio") state.mediaStudio?.openMixer();
  if (tab === "framing") {
    loadCropControls(elements.cropSourceSelect?.value || "A", false);
  }
  if (tab === "timeline" && !document.getElementById("editVideoEffects")?.hidden) followChromaSelection();
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
  if(reveal)$(`.advanced-tabs button[data-tab="${tab}"]`)?.scrollIntoView({block:"nearest", inline:"nearest"});
  requestAnimationFrame(() => state.timeline?.scheduleDraw?.());
  // Compact layouts have a single page scroller. Edit should reveal the
  // timeline; other tabs reveal their tools. Desktop keeps its player still.
  if (reveal && window.matchMedia?.("(max-width: 899px), (max-height: 600px)").matches) {
    const target = tab === "timeline" && document.getElementById("editVideoEffects")?.hidden ? document.getElementById("studioTimelineDock") : activePanel;
    target?.scrollIntoView({ block: "start", inline: "nearest", behavior: "instant" });
  } else if (reveal && activePanel?.parentElement) {
    activePanel.parentElement.scrollTop = 0;
  }
  requestEditingPositionCapture();
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

// Cues are views over saved clip crops, not a second timing or speaker track.
function podcastFramingCues(project) {
  if (!project?.editor_sequence) return [];
  const rows = trackClips(project, "A").filter(row => row.crop &&
    [row.start,row.end,row.crop.x,row.crop.y,row.crop.zoom].every(Number.isFinite) &&
    row.end > row.start && (row.crop.x !== .5 || row.crop.y !== .5 || row.crop.zoom !== 1)).sort((a,b) => a.start-b.start);
  const cues = [];
  for (const row of rows) {
    const previous = cues[cues.length-1], crop = row.crop;
    const sourceRef = row.source_ref || "primary:A";
    const sourceEnd = Number(row.source_start) + row.end-row.start;
    if (previous && Math.abs(previous.end-row.start) < 1e-6 && previous.sourceRef === sourceRef &&
      Math.abs(previous.sourceEnd-Number(row.source_start)) < 1e-6 &&
      ["x","y","zoom"].every(key => previous.crop[key] === crop[key])) {
      previous.end = row.end; previous.sourceEnd = sourceEnd;
    } else cues.push({start:row.start,end:row.end,crop:{...crop},sourceRef,sourceEnd});
  }
  return cues;
}

function renderPodcastFramingCues(panel) {
  const host = document.getElementById("podcastFramingCues");
  if (!host) return;
  host.replaceChildren();
  const projectId = state.project?.id, revision = state.project?.revision;
  const sourceGeneration = state.project?.sources?.A?.generation;
  const cues = podcastFramingCues(editorProject());
  document.getElementById("podcastFramingCuesHelp").textContent = uiCopy(
    "בחר טווח שמור כדי לשנות את המסגור או לאפס לשניהם. לטווח חדש השתמש בכלי טווח בטיימליין. אלה אינם זמני דיבור מזוהים.",
    "Select a saved range to change its framing or reset to Both. Use timeline Range for a new interval. These are not detected speaker times.");
  for (const cue of cues) {
    const button = document.createElement("button"); button.type = "button";
    button.dataset.podcastCue = `${cue.start}:${cue.end}`;
    const focus = cue.crop.x === .5 && cue.crop.zoom > 1 && cue.crop.y === 0 ? uiCopy("מיקוד עליון", "Top focus")
      : cue.crop.x === .5 && cue.crop.zoom > 1 && cue.crop.y === 1 ? uiCopy("מיקוד תחתון", "Bottom focus") : uiCopy("מסגור מותאם", "Custom crop");
    button.textContent = `${formatSourceTime(cue.start)}–${formatSourceTime(cue.end)} · ${focus}`;
    button.disabled = state.manualEditBusy || foregroundBusy();
    button.addEventListener("click", () => {
      if (state.manualEditBusy || foregroundBusy()) return;
      if (state.project?.id !== projectId || state.project?.revision !== revision || state.project?.sources?.A?.generation !== sourceGeneration) {
        toast(uiCopy("העריכה השתנתה. בחר שוב טווח עדכני.", "The edit changed. Select the current range again.")); return;
      }
      setManualSelection({start:cue.start,end:cue.end});
      seekPreview(cue.start + Math.min(.04,(cue.end-cue.start)/2));
      syncSecondaryPreview(previewPlaybackTime());
    });
    host.append(button);
  }
  host.hidden = !cues.length;
}

function podcastFramingSourceSupported(project) {
  const source = project?.sources?.A;
  const ratio = Number(source?.width) / Number(source?.height);
  return Boolean(source?.generation && !project.sources?.B && Number.isFinite(ratio)
    && ratio > 0 && ratio < 1 && Number(source.rotation || 0) === 0);
}

function renderPodcastFraming() {
  const panel = document.getElementById("podcastFraming");
  if (!panel) return;
  // This tool only crops an already stacked portrait recording. Separate
  // screen/camera feeds use source timing and layout, not participant crops.
  panel.hidden = !podcastFramingSourceSupported(state.project);
  if (panel.hidden) return;
  const confirm = document.getElementById("podcastStackedClean");
  if (!panel.dataset.bound) {
    panel.dataset.bound = "true";
    confirm.addEventListener("change", renderPodcastFraming);
    document.getElementById("podcastPanelSplit").addEventListener("input", renderPodcastFraming);
    elements.aspectSelect?.addEventListener("change", renderPodcastFraming);
    panel.querySelectorAll("[data-podcast-focus]").forEach(button => button.addEventListener("click", () => void applyPodcastFraming(button.dataset.podcastFocus).catch(error => toast(error.message))));
  }
  renderPodcastFramingCues(panel);
  const source = state.project?.sources?.A;
  const key = `${state.project?.id}:${source?.generation}`;
  if (panel.dataset.sourceKey !== key) { panel.dataset.sourceKey = key; confirm.checked = false; document.getElementById("podcastPanelSplit").value = "50"; }
  document.getElementById("podcastFramingTitle").textContent = uiCopy("מסגור פודקאסט ידני", "Manual podcast framing");
  document.getElementById("podcastFramingHelp").textContent = uiCopy("בחירת משתתף לטווח המסומן. אין כאן זיהוי של הדובר. כתוביות נפרדות נשארות בגודלן.", "Choose a participant for the selected range. No speaker detection. Separate captions keep their size.");
  document.getElementById("podcastStackedCleanLabel").textContent = uiCopy("אני מאשר את החלונות המוערמים ואת קו ההפרדה שסומן, ללא כתוביות צרובות במקור.", "I confirm the stacked panels, marked divider and absence of burned-in captions.");
  document.getElementById("podcastPanelSplitLabel").textContent = uiCopy("החלון העליון מסתיים בגובה", "Upper panel ends at");
  document.getElementById("podcastPanelSplitValue").textContent = `${Number(document.getElementById("podcastPanelSplit").value).toFixed(1)}%`;
  const range = state.manualSelection;
  const ratio = Number(source?.width) / Number(source?.height);
  const aspect = elements.aspectSelect?.value || state.project?.settings?.aspect;
  const outputRatio = aspect === "source" ? ratio : ({"9:16":9/16,"16:9":16/9,"1:1":1,"4:5":4/5})[aspect];
  let reason = !state.project?.editor_sequence || !range ? uiCopy("סמן טווח בטיימליין הערוך.", "Select a range in the edited timeline.")
    : previewUsesSourceTime() ? uiCopy("עבור לתצוגת הסרטון הערוך.", "Switch the preview to Edited video.")
    : state.project.sources?.B || activeEditTarget() === "B" ? uiCopy("הפקדים מיועדים לקובץ A יחיד עם חלונות מוערמים.", "These controls require one stacked source A, not separate feeds.")
    : !source?.generation || !Number.isFinite(ratio) || !(ratio > 0 && ratio < 1) || Number(source.rotation || 0) !== 0 ? uiCopy("נדרש מקור אנכי ישר עם גרסה מזוהה.", "An upright versioned portrait source is required.")
    : !outputRatio || Math.abs(outputRatio / ratio - 1) > .005 ? uiCopy("בחר יחס פלט אנכי זהה למקור; אין התאמה אוטומטית ליחס אחר.", "Choose source-matching portrait output; other aspect ratios are unsupported.")
    : source.has_burned_captions ? uiCopy("יש כתוביות צרובות במקור. השתמש במקור נקי.", "This source has burned-in captions. Use clean footage.")
    : state.project.manual?.track_locks?.A ? uiCopy("מסלול A נעול.", "Source A is locked.")
    : !confirm.checked ? uiCopy("אשר את מבנה החלונות ואת היעדר הכתוביות הצרובות.", "Confirm the panel layout and absence of burned-in captions.") : "";
  const busy = state.manualEditBusy || foregroundBusy();
  panel.querySelectorAll("[data-podcast-focus]").forEach(button => {
    button.textContent = ({both:uiCopy("שניהם", "Both"),top:uiCopy("משתתף עליון", "Top participant"),bottom:uiCopy("משתתף תחתון", "Bottom participant")})[button.dataset.podcastFocus];
    button.disabled = Boolean(reason) || busy;
  });
  document.getElementById("podcastFramingStatus").textContent = reason || `${formatSourceTime(range.start)}–${formatSourceTime(range.end)} · ${uiCopy("מסגור ידני בלבד · ניתן לביטול", "manual range framing · Undo available")}`;
}

async function applyPodcastFraming(focus) {
  if (!state.manualSelection || !state.project?.sources?.A || state.manualEditBusy || foregroundBusy()) return;
  if (state.captionDirty || pendingTranscriptBuffers().length) { toast(uiCopy("שמור או בטל שינויי כתוביות תחילה.", "Save or discard pending caption text first.")); return; }
  const range = {...state.manualSelection}, projectId = state.project.id;
  const updated = await applyManualEdit("sequence_podcast_frame", {slot:"A", ...range, focus,
    panel_split: Number(document.getElementById("podcastPanelSplit").value) / 100,
    source_generation: state.project.sources.A.generation,
    confirmed_stacked_clean: document.getElementById("podcastStackedClean").checked});
  if (!updated || state.project?.id !== projectId) return;
  loadCropControls("A", false);
  seekPreview(range.start + Math.min(.04, (range.end-range.start)/2));
  syncSecondaryPreview(previewPlaybackTime());
  renderPodcastFraming();
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
  renderPodcastFraming();
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
  const detection = embeddedCameraDetection();
  const unavailable = detection && detection.available !== true;
  const sourceA = state.project?.sources?.A;
  const hasB = Boolean(state.project?.sources?.B);
  elements.cameraDetection.hidden = !sourceA || hasB || embeddedCameraIsActive();
  if (!sourceA || hasB) return;
  const title = $("b", elements.cameraDetection);
  const help = $("p", elements.cameraDetection);
  const active = embeddedCameraIsActive();
  title.textContent = unavailable && !active && !candidate
    ? uiCopy("זיהוי מצלמה אוטומטי אינו זמין", "Automatic camera detection unavailable")
    : active
    ? uiCopy("מצלמה פנימית פעילה", "Embedded camera active")
    : candidate
      ? uiCopy("נמצא אזור מצלמה אפשרי", "Possible camera area found")
      : uiCopy("המצלמה לא זוהתה אוטומטית", "Camera was not detected automatically");
  help.textContent = unavailable && !active && !candidate
    ? cameraDetectionUnavailableHelp(detection)
    : active
    ? uiCopy("אפשר לשנות את המסגרת ידנית ב־Source Mixer. השינוי יופיע מיד בעריכה.", "Adjust the frame manually in Source Mixer; the edit updates immediately.")
    : candidate
      ? uiCopy("בדקו את המסגרת לפני אישור. המערכת לעולם לא תשכפל את המקור בלי בחירה שלכם.", "Check the frame before confirming. CUTROOM never duplicates the source without your choice.")
      : uiCopy("זה לא חוסם את העריכה: פתחו את Source Mixer וסמנו את חלון המצלמה ידנית.", "This does not block editing: use Source Mixer to mark the camera window manually.");
  elements.useEmbeddedCamera.textContent = candidate
    ? active ? uiCopy("שמור שוב", "Save again") : uiCopy("בדוק והשתמש", "Review and use")
    : uiCopy("סמן ידנית", "Mark manually");
  renderStreamerLayoutTip();
}

function setManualSelection(selection, context = {}) {
  const start = Number(selection?.start);
  const end = Number(selection?.end);
  state.manualSelection = Number.isFinite(start) && Number.isFinite(end) && end - start >= (state.project?.editor_sequence ? 1 / 60 - 1e-6 : .03) ? { start: Math.min(start, end), end: Math.max(start, end) } : null;
  state.captionAlternativesUI?.render();
  state.transcriptSectionsUI?.refresh?.();
  if (state.project?.sources?.B) hydrateSourceMixerLayout();
  renderManualControls();
  renderSourceMixer();
  highlightTranscriptSelection();
  if (state.project?.editor_sequence && elements.cropX && elements.cropSourceSelect) loadCropControls(elements.cropSourceSelect.value, false);
  if (state.studio.open && ["clip","move","locked"].includes(context.kind)
    && state.manualSelection && selectedTimelineClip()) void revealSourceClipInspector();
}

function beginInspectorSelection() {
  state.inspectorSelectionEpoch = (state.inspectorSelectionEpoch || 0) + 1;
  return { epoch:state.inspectorSelectionEpoch, projectId:state.project?.id };
}

function canEditTimeline() {
  return !trackLevelUnfinished() && !retainedEditStatus() && !savedLayerTrackIssue() && !foregroundBusy() && !state.transcriptSaving && !state.manualEditBusy
    && !state.captionDirty && !state.captionContextSave && !state.textStudio?.dirty();
}

function inspectorSelectionCurrent(request) {
  return request.epoch === state.inspectorSelectionEpoch && request.projectId === state.project?.id;
}

async function prepareInspectorSelection(request) {
  if(trackLevelUnfinished()){revealPendingSave(explicitPendingDraft());return false;}
  if (foregroundBusy()) return false;
  if (state.captionDirty && selectedCaptionItem()) {
    if (!state.captionContextSave) {
      const save = Promise.resolve().then(() => saveCaptionItem());
      state.captionContextSave = save;
      void save.finally(() => { if (state.captionContextSave === save) state.captionContextSave = null; }).catch(() => {});
    }
    try { await state.captionContextSave; } catch { return false; }
    // Validation/API failures leave the user's caption draft intact. A null
    // result can also mean a valid unchanged draft, so inspect dirty state.
    if (state.captionDirty) return false;
  }
  if ((state.textStudio?.dirty?.() || state.textStudio?.pending?.size || state.textStudio?.saving)
    && await state.textStudio.flush() === false) return false;
  if ((state.mediaStudio?.pending?.size || state.mediaStudio?.saving)
    && await state.mediaStudio.flush() === false) return false;
  return inspectorSelectionCurrent(request) && !state.captionDirty;
}

function restoreInspectorSelection(request) {
  if (!inspectorSelectionCurrent(request) || !state.timeline) return;
  state.timeline.cancelGesture?.();
  const caption = selectedCaptionItem();
  const media = state.textStudio?.selected || state.mediaStudio?.selected;
  if (!caption && !media) return;
  state.manualSelection = null;
  state.timeline.clearSelection(false);
  if (caption) state.timeline.selectCaption?.(caption.id, false);
  else { state.timeline.selectCaption?.(null, false); state.timeline.mediaSelection = media; }
  state.timeline.scheduleDraw?.();
  renderManualControls();
}

function clearCaptionInspectorSelection() {
  state.captionSelection = null; state.captionDirty = false; state.captionStatus = "";
  state.timeline?.selectCaption?.(null, false);
  renderCaptionInspector();
}

async function selectTimelineMedia(id) {
  const request = beginInspectorSelection();
  pauseAllMedia();
  if (!(await prepareInspectorSelection(request))) { restoreInspectorSelection(request); return false; }
  const text = state.project?.manual?.text_clips?.find(clip => clip.id === id);
  const media = state.project?.manual?.media_clips?.find(clip => clip.id === id);
  if (!text && !media) return false;
  if (text) {
    if (await state.textStudio?.select(id) === false || !inspectorSelectionCurrent(request) || state.captionDirty) { restoreInspectorSelection(request); return false; }
    state.mediaStudio?.select(null);
  } else {
    if (state.textStudio?.selected && await state.textStudio.select(null) === false) { restoreInspectorSelection(request); return false; }
    if (!inspectorSelectionCurrent(request) || state.captionDirty) { restoreInspectorSelection(request); return false; }
    state.mediaStudio?.select(id);
  }
  clearCaptionInspectorSelection();
  state.timeline?.clearSelection();
  if (state.timeline) state.timeline.mediaSelection = id;
  selectAdvancedTab(text ? "transcript" : "media");
  if (text) state.textStudio?.inspector?.scrollIntoView({block:"nearest", inline:"nearest"});
  else {
    const root = state.mediaStudio?.root;
    const asset = state.project?.assets?.[media.asset_id];
    // This edits only the selected clip's volume_db/fades. The Audio tab's
    // Original/Music/Voiceover/Effects strips intentionally remain group gains.
    if (asset?.kind === "audio") {
      const audio = root?.querySelector(".media-clip-audio"); if (audio) audio.open = true;
    }
    const inspector = root?.querySelector(".media-inspector");
    if (inspector) {
      // A tall, partly visible inspector otherwise keeps the previous clip's
      // scroll position and hides the new filename. Only explicit selection
      // reveals its top; routine saves/renders never reset the user's scroll.
      const key = JSON.stringify([state.project.id, id]);
      const newSelection = inspector.dataset.revealedClip !== key;
      inspector.dataset.revealedClip = key;
      inspector.scrollIntoView({block:newSelection ? "start" : "nearest", inline:"nearest"});
    }
  }
  state.timeline?.scheduleDraw?.();
  return true;
}

async function revealSourceClipInspector() {
  const request = beginInspectorSelection();
  if (!(await prepareInspectorSelection(request))) { restoreInspectorSelection(request); return false; }
  if (state.textStudio?.selected && await state.textStudio.select(null) === false) { restoreInspectorSelection(request); return false; }
  if (!inspectorSelectionCurrent(request) || state.captionDirty || !selectedTimelineClip()) { restoreInspectorSelection(request); return false; }
  state.mediaStudio?.select(null);
  clearCaptionInspectorSelection();
  if (state.timeline) state.timeline.mediaSelection = null;
  selectAdvancedTab("timeline");
  selectEditTool("clip");
  elements.clipTrimForm?.scrollIntoView({block:"nearest", inline:"nearest"});
  return true;
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

function closePrimarySourceReview({force=true,restoreFocus=false}={}) {
  state.primarySourceOpenEpoch=(state.primarySourceOpenEpoch || 0)+1;
  state.sourceReview?.close?.({force,restoreFocus});
}

async function openSourceReview(options = {}) {
  if(!requireResumedEdit())return false;
  if (!state.project?.editor_sequence || foregroundBusy() || state.manualEditBusy) return false;
  const projectId=state.project.id,viewToken=state.projectViewToken;
  const epoch=state.primarySourceOpenEpoch=(state.primarySourceOpenEpoch || 0)+1;
  const opener=document.activeElement;
  pauseAllMedia();
  if(!await flushCurrentProjectSaves())return false;
  if(state.project?.id!==projectId || state.projectViewToken!==viewToken || state.primarySourceOpenEpoch!==epoch
    || foregroundBusy() || state.manualEditBusy || !state.project?.editor_sequence)return false;
  const issue=sourceMonitorIssue();if(issue){toast(issue);return false;}
  if(!openStudioTab("media"))return false;
  state.mediaStudio?.closeSourceMonitor?.();
  if(selectedLayerGroupIds().length){state.timeline?.setMediaSelection?.([],null);renderManualControls();}
  const root=document.getElementById("studioPanelMedia");
  state.sourceReview ??= new SourceReview({
    getProject:()=>state.project,applyEdit:applyManualEdit,mediaUrl:sourceMediaUrl,pause:pauseAllMedia,exactInsert:openSourceInsert,
    dock:{root,token:()=>state.projectViewToken,
      visible:()=>state.studio.open && !root.hidden && !root.inert
        && document.getElementById("studioInspector")?.dataset.workbenchPane!=="ai",
      busy:()=>foregroundBusy() || state.manualEditBusy,issue:sourceMonitorIssue,
      pauseProgram:video=>pauseAllMedia(video),
      focusTarget:slot=>[...(document.querySelectorAll(".source-library-card") || [])].find(card=>card.querySelector("b")?.textContent===slot)
        || elements.manualRestore,
      closed:()=>{state.primarySourceOpenEpoch=(state.primarySourceOpenEpoch || 0)+1;},
    },
  });
  return state.sourceReview.open(activeEditTarget(),{slot:options?.slot,opener});
}

function formatSourcePlacementTime(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) && Math.abs(seconds * 1000 - Math.round(seconds * 1000)) > 1e-6
    ? String(Number(seconds.toFixed(9))) : formatSourceTime(seconds);
}

function sourceInsertIdentity() {
  const p = state.project;
  return JSON.stringify([p?.id, p?.sources, p?.editor_sequence, p?.settings?.fps, p?.manual?.track_locks,
    p?.manual?.media_clips, p?.manual?.text_clips, p?.manual?.layer_tracks, p?.assets,
    p?.draft?.audio_plan, p?.caption_alternative_status, p?.editor_captions, p?.manual?.caption_overrides,
    p?.manual?.caption_dormant_overrides, p?.manual?.source_mixer]);
}

function closeSourceInsert() {
  if(elements.sourceInsertForm)elements.sourceInsertForm.hidden=true;
  state.sourceInsertSession=null;
}

function openSourceInsert(placement = {}) {
  if(!requireResumedEdit())return false;
  if (!state.project?.editor_sequence || foregroundBusy() || state.manualEditBusy || state.sourceInsertSession?.busy) return false;
  if (placement.projectId && placement.projectId !== state.project.id) return false;
  const selection = state.manualSelection ? {...state.manualSelection} : null;
  if (!openStudioTab("timeline")) return false;
  selectEditTool("clip");
  if (placement.scope) setEditTarget(placement.scope === "edit" ? "edit" : placement.slot);
  const target = activeEditTarget();
  const slot = target === "edit" ? (state.project.sources[placement.slot] ? placement.slot : transcriptSourceSlot()) : target;
  const form = elements.sourceInsertForm;
  form.dataset.projectId = state.project.id;
  form.dataset.target = target;
  elements.sourceInsertSlot.value = slot;
  elements.sourceInsertSlot.disabled = target !== "edit";
  elements.sourceInsertSlot.querySelector('option[value="B"]').disabled = !state.project.sources.B;
  elements.sourceInsertTitle.textContent = "Place source footage";
  elements.sourceInsertIn.value = formatSourcePlacementTime(placement.source_start ?? 0);
  elements.sourceInsertOut.value = formatSourcePlacementTime(placement.source_end ?? Math.min(5, Number(state.project.sources[slot]?.duration || 0)));
  elements.sourceInsertAt.value = formatSourcePlacementTime(previewTimelineTime());
  elements.sourceInsertMode.value = "insert";
  elements.sourceInsertZone.value = "playhead";
  const zone = selection && selection.start >= 0 && selection.end <= editorDuration() + 1e-6 && selection.end - selection.start >= minimumEditLength() - 1e-6 ? selection : null;
  state.sourceInsertSession = {identity:sourceInsertIdentity(), viewToken:state.projectViewToken, revision:state.project.revision, zone, busy:false, useZone:false};
  const zoneOption = elements.sourceInsertZone.querySelector('option[value="selection"]');
  zoneOption.disabled = !zone;
  zoneOption.textContent = zone ? `Selected edit range (${formatSourceTime(zone.start)} - ${formatSourceTime(zone.end)})` : "Select a timeline range first";
  form.hidden = false;
  renderSourceInsert();
  pauseAllMedia();
  elements.sourceInsertIn.focus();
  form.scrollIntoView({ block: "nearest" });
  return true;
}

function sourceInsertPlan() {
  const form = elements.sourceInsertForm, session = state.sourceInsertSession;
  const slot = elements.sourceInsertSlot.value, mode = elements.sourceInsertMode.value;
  const issue=sourceMonitorIssue();if(issue)throw new Error(issue);
  if (!session || form.dataset.projectId !== state.project?.id || form.dataset.target !== activeEditTarget()
    || session.viewToken !== state.projectViewToken || session.revision !== state.project.revision
    || session.identity !== sourceInsertIdentity()) throw new Error("The edit or source changed. Cancel and review the current version before placing footage.");
  if (!["insert", "insert_all", "overwrite"].includes(mode)) throw new Error("Choose an insertion policy or Overwrite.");
  if (mode === "insert_all" && form.dataset.target !== "edit") throw new Error("Choose Together (A+B) before using all-layer insertion. This source-only scope was not widened.");
  const sourceDuration = Number(state.project.sources?.[slot]?.duration);
  const sourceStart = parseSourceTime(elements.sourceInsertIn.value, 9);
  const useZone = elements.sourceInsertZone.value === "selection";
  if (useZone && !session.zone) throw new Error("Select a timeline range before using it for placement.");
  const start = useZone ? session.zone.start : parseSourceTime(elements.sourceInsertAt.value, 9);
  let sourceEnd = useZone ? sourceStart + session.zone.end - session.zone.start : parseSourceTime(elements.sourceInsertOut.value, 9);
  if (![start, sourceStart, sourceEnd, sourceDuration].every(Number.isFinite) || start < 0 || sourceStart < 0
    || sourceEnd - sourceStart < minimumEditLength() - 1e-9 || sourceEnd > sourceDuration + (useZone ? 1e-9 : .0005) || start + sourceEnd - sourceStart > 86400) {
    throw new Error(useZone ? "Not enough source footage from this In point to fill the selected edit range. Choose an earlier In point or a shorter range."
      : `Choose source times between 0 and ${formatSourceTime(sourceDuration)} and a valid edit position.`);
  }
  // Keep millisecond-rounded full-media endpoints usable without extending media.
  sourceEnd = Math.min(sourceDuration, sourceEnd);
  const length = sourceEnd - sourceStart;
  if (mode === "overwrite" && start + length > editorDuration() + 1e-6) throw new Error("Overwrite must fit inside the edit. Choose Insert to extend it.");
  const affected = form.dataset.target === "edit" ? ["A", "B"] : [slot];
  const locked = affected.filter(name => state.project.manual?.track_locks?.[name] === true);
  if (locked.length) throw new Error(`Track ${locked.join(" + ")} is locked. Unlock it before placing footage.`);
  if (mode === "insert_all") {
    const issue = savedLayerTrackIssue() || layerEditProtectionIssue("sequence_insert_all",{slot,start,source_start:sourceStart,source_end:sourceEnd}) || libraryInsertReadiness(editorProject(), start, length, 0);
    if (issue) throw new Error(issue);
  }
  return {slot, mode, start, sourceStart, sourceEnd, length, target:form.dataset.target, useZone};
}

function renderSourceInsert() {
  const form = elements.sourceInsertForm, session = state.sourceInsertSession;
  if (!form || form.hidden || !session) return;
  const useZone = elements.sourceInsertZone.value === "selection" && Boolean(session.zone);
  if (useZone && !session.useZone) {
    session.sourceOut = elements.sourceInsertOut.value;
    session.editAt = elements.sourceInsertAt.value;
  } else if (!useZone && session.useZone) {
    elements.sourceInsertOut.value = session.sourceOut;
    elements.sourceInsertAt.value = session.editAt;
  }
  session.useZone = useZone;
  if (useZone) {
    elements.sourceInsertAt.value = formatSourcePlacementTime(session.zone.start);
    const start = parseSourceTime(elements.sourceInsertIn.value, 9);
    elements.sourceInsertOut.value = Number.isFinite(start) ? formatSourcePlacementTime(start + session.zone.end - session.zone.start) : "";
  }
  const busy = session.busy || state.manualEditBusy || foregroundBusy();
  for (const node of [elements.sourceInsertIn,elements.sourceInsertMode,elements.sourceInsertZone,elements.sourceInsertCancel]) node.disabled = Boolean(busy);
  elements.sourceInsertSlot.disabled = Boolean(busy) || form.dataset.target !== "edit";
  elements.sourceInsertOut.disabled = elements.sourceInsertAt.disabled = Boolean(busy) || useZone;
  const allOption = elements.sourceInsertMode.querySelector('option[value="insert_all"]');
  if (allOption) {
    allOption.disabled = form.dataset.target !== "edit";
    allOption.title = allOption.disabled ? "Choose Together (A+B) to ripple all layers." : "Opens time across both source lanes, framing and supported imported media/text.";
  }
  elements.sourceInsertApply.textContent = elements.sourceInsertMode.value === "overwrite" ? "Overwrite footage"
    : elements.sourceInsertMode.value === "insert_all" ? "Insert and ripple all layers" : "Insert footage";
  elements.sourceInsertApply.disabled = Boolean(busy);
  if (busy) { elements.sourceInsertStatus.textContent = "Placing footage. Please wait for confirmation."; return; }
  try {
    const plan = sourceInsertPlan();
    const scope = plan.target === "edit" ? "Together (A+B)" : `Source ${plan.slot} only`;
    const effect = plan.mode === "overwrite"
      ? (plan.target === "edit" ? "Replaces A/B footage and framing only in this range." : "Replaces only this source; other-source clips and framing stay unchanged.") + " Later clips, added media/audio and titles stay at their existing times."
      : (plan.target === "edit" ? "Inserts this source, leaving the other source empty here, and shifts both source tracks and framing." : "Inserts on this source only; the other source stays still.") + " Added media/audio and titles keep their existing times.";
    if (plan.mode === "insert_all") {
      const audioSlot = sourceMixerSettings().audioSlot;
      const audio = `Source audio stays routed to ${audioSlot}. ` + (audioSlot !== plan.slot
        ? `Inserting ${plan.slot} picture does not switch its sound; the new interval may be silent. ` : "Selecting this picture does not change mix or gain. ");
      elements.sourceInsertStatus.textContent = `All layers: +${plan.length.toFixed(3)} s at ${formatSourceTime(plan.start)}. Inserts Source ${plan.slot} only; the other source is empty here. Opens time in A/B, framing, imported video/audio/images and custom text: crossing layers split, later parts move together. ${plan.useZone ? "The selected range supplies the inserted length; it is not replaced. " : ""}${audio}One Undo restores the previous edit. Originals stay unchanged.`;
    } else {
      elements.sourceInsertStatus.textContent = `${scope}: ${plan.length.toFixed(3)} s at ${formatSourceTime(plan.start)}. ${effect} ${plan.useZone ? "The edit range determines Source Out; playback speed is unchanged. " : ""}Audio routing is unchanged. Undo is available.`;
    }
  } catch (error) {
    elements.sourceInsertApply.disabled = true;
    elements.sourceInsertStatus.textContent = error.message;
  }
}

async function insertSourceFootage(event) {
  event.preventDefault();
  const form = elements.sourceInsertForm, session = state.sourceInsertSession;
  if (form.hidden || !session || session.busy || state.manualEditBusy || foregroundBusy()) return;
  if (form.dataset.target !== activeEditTarget()) { form.hidden = true; return; }
  if (form.dataset.projectId !== state.project?.id) { form.hidden = true; return; }
  let plan;
  try { plan = sourceInsertPlan(); }
  catch (error) { elements.sourceInsertStatus.textContent = error.message; return; }
  const {slot,mode,start,sourceStart,sourceEnd,length,target} = plan;
  const current=()=>session===state.sourceInsertSession && !form.hidden && form.dataset.projectId===state.project?.id
    && session.viewToken===state.projectViewToken && form.dataset.target===activeEditTarget();

  pauseAllMedia();
  session.busy = true;
  renderSourceInsert();
  const fieldIdentity=()=>JSON.stringify([elements.sourceInsertMode.value,elements.sourceInsertSlot.value,
    elements.sourceInsertZone.value,elements.sourceInsertIn.value,elements.sourceInsertOut.value,elements.sourceInsertAt.value]);
  const reviewedFields=fieldIdentity();
  const admitted=()=>current() && !sourceMonitorIssue() && session.identity===sourceInsertIdentity()
    && session.revision===state.project.revision && reviewedFields===fieldIdentity();
  let updated;
  try {
    const action = mode === "insert_all" ? "sequence_insert_all" : mode === "overwrite" ? "sequence_overwrite" : target === "edit" ? "sequence_insert_linked" : "sequence_insert";
    const detail = {slot,start,source_start:sourceStart,source_end:sourceEnd,
      ...(mode === "overwrite" ? {scope:target === "edit" ? "edit" : "source"} : {})};
    updated = await applyManualEdit(action, detail, {strictRevision:true,isCurrent:current,admissionCurrent:admitted});
  } catch {
    // A transport failure cannot establish whether the edit was committed.
    updated = null;
  } finally {
    session.busy = false;
    if (current()) renderSourceInsert();
  }
  if (!current()) return;
  if (!updated || updated.id !== form.dataset.projectId || updated.revision!==state.project.revision) { elements.sourceInsertStatus.textContent = "Placement was not confirmed. Review the timeline before trying again."; return; }
  closeSourceInsert();
  setEditTarget(target);
  state.timeline.selectRange(start, start + length);
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
  if (previousTarget !== state.editTarget && elements.sourceInsertForm) closeSourceInsert();
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
function parseSourceTime(raw, precision = 6) {
  const value = String(raw ?? "").trim();
  if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d{1,9})?$/.test(value) || (value.split(".")[1] || "").length > precision) return NaN;
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
  state.trackLift?.sync();
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
    ["Playback & navigation", ["toggle_play", "stop", "play_forward", "frame_back", "frame_forward", "previous_edit", "next_edit", "jump_start", "jump_end", "review_marker"]],
    ["Tools & cuts", ["tool_select", "tool_range", "tool_blade", "tool_remove_between", "split", "delete_selection", "restore_selection"]],
    ["Selection & trimming", ["mark_in", "mark_out", "select_clip", "mark_selected_layers", "clear_selection", "trim_start", "trim_end"]],
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
  elements.timelineCutStatus.hidden = !["remove_between", "move", "slip"].includes(timeline.tool);
  elements.timelineCutStatus.dataset.tool = timeline.tool;
  elements.cancelTimelineCut.hidden = timeline.cutAnchor == null;
  if (elements.timelineSnap) {
    elements.timelineSnap.textContent = `Snap: ${timeline.snapping ? "on" : "off"}`;
    elements.timelineSnap.setAttribute("aria-pressed", String(Boolean(timeline.snapping)));
  }
  const help = {
    slip: "Slip video/audio: right = later source, left = earlier. Clip timing stays fixed. Esc cancels; Undo restores.",
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
  if (state.captionDirty || state.captionContextSave) { toast("Save or discard the caption text before editing footage."); return null; }
  const target = edit.target || activeEditTarget();
  const locked = state.trackProtection?.lockedNames(edit.slot || target) || [];
  if (locked.length) { toast(`Track ${locked.join(" + ")} is locked. Unlock it in Edit → Track protection.`); return null; }
  if (edit.action === "sequence_trim_edge") {
    const projectId = state.project?.id;
    const {action,...detail} = edit;
    const updated = await applyManualEdit(action,detail);
    if (state.project?.id !== projectId || activeEditTarget() !== target) return updated;
    if (updated) {
      const start = edit.edge === "start" ? (!edit.slot && edit.time > edit.start ? edit.start : edit.time) : edit.start;
      const end = edit.edge === "end" ? edit.time : edit.end-(!edit.slot ? Math.max(0,edit.time-edit.start) : 0);
      state.timeline?.selectRange(start,end); seekSourcePreview(start);
    } else if (state.manualSelection) {
      // A failed request leaves the saved selection available for a retry.
      // A revision conflict clears it; never restore stale clip coordinates.
      state.timeline?.selectRange(state.manualSelection.start,state.manualSelection.end);
    } else state.timeline?.clearSelection();
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
  if(action==="mark_selected_layers"){if(!event.repeat&&state.markedLayers?.apply(true)){event.preventDefault();event.stopPropagation?.();}return;}
  if(action==="review_marker"){if(!event.repeat && state.timeline?.reviewMarkers?.open()){event.preventDefault();event.stopPropagation?.();}return;}
  if(selectedLayerGroupIds().length && (["trim_start","trim_end","split","delete_selection","restore_selection","clear_selection"].includes(action)
    || event.target===elements.timelineCanvas && ["Delete","Backspace"].includes(event.key))){
    event.preventDefault();event.stopPropagation?.();
    if(!event.repeat){
      if(action==="clear_selection"){if(!state.timeline?.cancelGesture?.())void selectTimelineLayers([],null);}
      else if(action==="delete_selection")void removeTimelineLayerGroup(selectedLayerGroupIds());
      else if(action==="split")void splitTimelineSelection();
      else toast(groupSelectionIssue());
    }
    return;
  }
  if (["trim_start", "trim_end"].includes(action) && (state.timeline?.mediaSelection || state.timeline?.captionSelection)) {
    event.preventDefault(); event.stopPropagation?.();
    if (!event.repeat && !foregroundBusy() && !state.transcriptSaving) void trimTimelineSelection(action === "trim_start" ? "start" : "end");
    return;
  }
  if (action === "split" && (state.timeline?.mediaSelection || state.timeline?.captionSelection)) {
    // Eligible editor focus uses the same selected layer as the toolbar.
    // The keymap still excludes native buttons, inputs, links and dialogs.
    event.preventDefault(); event.stopPropagation?.();
    if (!event.repeat && !foregroundBusy() && !state.transcriptSaving) void splitTimelineSelection();
    return;
  }
  const selectedCaption = event.target === elements.timelineCanvas && state.timeline?.captionSelection ? selectedCaptionItem() : null;
  if (selectedCaption && (["delete_selection", "restore_selection", "split", "clear_selection"].includes(action)
    || [event.key, event.code].some(key => ["Delete", "Del", "Backspace", "Enter"].includes(key)))) {
    // A caption is not footage. Its Delete hides that caption and can never
    // remove an older range selection underneath it.
    event.preventDefault();
    event.stopPropagation?.();
    if (event.repeat || foregroundBusy() || state.transcriptSaving) return;
    if (action === "clear_selection") void selectCaptionItem(null);
    else if (event.key === "Enter") void selectCaptionItem(selectedCaption.id, { focus: true });
    else if ((action === "delete_selection" || ["Delete", "Del", "Backspace"].includes(event.key)) && !selectedCaption.hidden) {
      void runCaptionAction("caption_visibility", { caption_id: selectedCaption.id, hidden: true });
    }
    return;
  }
  const selectedMedia = event.target === elements.timelineCanvas && state.timeline?.mediaSelection
    ? [...(state.project.manual?.media_clips || []), ...(state.project.manual?.text_clips || [])].find(item => item.id === state.timeline.mediaSelection) : null;
  if (event.target === elements.timelineCanvas && state.timeline?.mediaSelection && !selectedMedia
    && (["delete_selection", "split", "clear_selection"].includes(action)
      || [event.key, event.code].some(key => ["Delete", "Del", "Backspace"].includes(key)))) {
    // A removed or replaced layer must never redirect its next shortcut to
    // an older footage selection underneath it.
    event.preventDefault();
    event.stopPropagation?.();
    state.timeline.mediaSelection = null;
    state.timeline.clearSelection();
    return;
  }
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
      void state.textStudio?.select(null);
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
  if (action === "split") { splitTimelineSelection(time); return; }
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
    const direction=action === "frame_back" ? -1 : 1;
    if(state.project?.editor_sequence && !previewUsesSourceTime()) {
      const target=projectFrameStep(time,direction,Number(state.project.settings?.fps)||30,editorDuration());
      if(target!==null)seekSourcePreview(target);
    } else {
      // Legacy Original A playback is a time nudge, not verified frame review.
      const fps=Number(state.project.sources?.A?.fps)||30,step=direction/Math.max(1,Math.min(240,fps));
      if(previewUsesSourceTime()&&state.project?.editor_sequence)seekPreview(previewPlaybackTime()+step);
      else seekSourcePreview(time+step);
      toast("Original preview time nudge. Use Source frame controls for decoded original frames.");
    }
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
    elements.clipTrimStatus.textContent = together ? "Drag either white edge of the selected clip to trim A+B together. These fields select times; Move to start moves the linked cut. Undo restores changes."
      : target === "edit" ? "Non-destructive · undoable" : "Move to start closes the old position and inserts on this track only. The other source stays still. Undo restores the move.";
  }
  state.trimClip = { ...clip, key, projectId: state.project.id, ...(["A","B"].includes(target) ? {slot:target} : {}) };
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
  state.markedLayers?.sync();
  state.firstRecordingGuide?.sync();
  renderSourceInsert();
  renderPodcastFraming();
  if (!elements.manualSelectionLabel) return;
  const selection = state.manualSelection;
  const recovery=retainedEditStatus();
  const available = Boolean(state.project?.draft) && !recovery;
  const busy = state.manualEditBusy || foregroundBusy() || Boolean(state.retainedResumePending);
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
    elements.trackReset.disabled = !available || busy || (sequence ? !state.project.editor_sequence.active : !Object.hasOwn(state.project?.manual?.source_tracks || {}, target));
    elements.trackReset.textContent = sequence ? "Reset to draft" : `Reset ${target} track`;
  }
  if (elements.trackHelp) {
    elements.trackHelp.hidden = !independent;
    elements.trackHelp.textContent = sequence ? (target === "edit" ? "Together: Cut out removes this time across sources, added media and text. Later layers shift together; one Undo restores the edit." : `Editing ${target} only · the other track stays still · removal leaves a gap`)
      : target === "edit" ? "Entire edit: removes time from the final video. Click A or B below to edit only that source."
      : `Editing ${target} only · gaps do not shift the other source · Move clips into empty space · darkened sections are excluded by EDIT.`;
  }
  renderRangeEditors();
  state.rangeAudition?.sync();
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
    const gapIssue = layerEditProtectionIssue("sequence_close_gaps",target === "edit" ? {} : {slot:target}) || sequenceGapClosureIssue(editorProject(),gaps,target === "edit" ? null : target);
    gapButton.hidden = !gaps.length;
    gapButton.disabled = !available || busy || Boolean(gapIssue);
    gapButton.textContent = `Close gaps (${gaps.length})`;
    gapButton.title = gapIssue || (target === "edit" ? "Remove time empty on every layer. Later sources, added media/audio and text move together. Spanning clips stay intact. One Undo restores all layers." : `Close empty spaces on ${target} only. The other track and added layers stay still. Undo available.`);
  }
  elements.manualDelete.setAttribute("aria-describedby", "timelineRangeImpactDetails");
  elements.manualDelete.textContent = target === "edit" ? "Remove from video" : `Remove from ${target}`;
  elements.manualSplit.textContent = uiCopy("פצל", "Split");
  elements.manualRestore.disabled = !available || (!sequence && !rangeState.canRestore) || busy || rangeInputPending("timeline");
  const deleteIssue = selection ? rangeDeleteIssue(selection.start, selection.end, target) : "";
  elements.manualDelete.disabled = !available || !rangeState.canRemove || busy || rangeInputPending("timeline") || Boolean(deleteIssue);
  if (elements.manualClear) elements.manualClear.disabled = !selection || busy;
  elements.manualRestore.title = sequence ? "See all original footage, preview removed sections, and restore or remove a selection" : target === "edit" ? "Return selected source footage that was excluded from the edit" : `Fill gaps in ${target} using its original alignment; the other track stays still`;
  elements.manualDelete.title = deleteIssue || (target === "edit" ? "Cut out this time across sources, added media and text. Later layers shift together. Original files stay in the media pool; one Undo restores the edit." : `Remove only ${target} in this range; other tracks and added layers stay still`);
  const splitLayer = state.timeline?.mediaSelection;
  renderSplitAvailability();
  elements.manualUndo.disabled = !available || history.undo < 1 || busy;
  elements.manualRedo.disabled = !available || history.redo < 1 || busy;
  if (elements.transcriptRemove) elements.transcriptRemove.disabled = state.transcriptRecoveryActive?.projectId === state.project?.id || !available || !manualRangeState("edit").canRemove || busy || Boolean(selection && rangeDeleteIssue(selection.start, selection.end, "edit"));
  if (elements.transcriptRestore) elements.transcriptRestore.disabled = state.transcriptRecoveryActive?.projectId === state.project?.id || !available || !manualRangeState("edit").canRestore || busy;
  if (sequence && elements.transcriptRemove) elements.transcriptRemove.textContent = "Remove from video";
  const emptyManual = !available && state.project?.settings?.workflow === "manual";
  if (elements.emptyTimeline) {
    elements.emptyTimeline.hidden = !recovery && !emptyManual && (!sequence || hasTimelineFootage());
    const title=elements.emptyTimeline.querySelector("h3");if(title)title.textContent=recovery ? "Your saved timeline is still here" : "Your timeline is empty";
    if(recovery){elements.emptyTimeline.dataset.retainedEdit="true";elements.emptyTimeline.dataset.retainedState=busy?"pending":recovery.available?"ready":"blocked";}
    else{delete elements.emptyTimeline.dataset.retainedEdit;delete elements.emptyTimeline.dataset.retainedState;}
    const help = elements.emptyTimeline.querySelector("p");
    if(help && recovery)help.textContent=`${recovery.duration===null ? "Saved edit" : `${formatTime(recovery.duration)} saved timeline`} · ${recovery.source_a_clips} A clips · ${recovery.media_clips} media · ${recovery.text_clips} text · ${recovery.track_count} named tracks. ${recovery.issue || "Resume keeps these saved mappings, layers, effects and settings."} Empty B placement stays empty. Unavailable old analysis, automatic captions and history are not recreated. No AI runs.`;
    else if (help) help.textContent = emptyManual
      ? "Import a video to start editing immediately. No AI account or draft generation is needed. Then add more video, audio or images from the media pool."
      : "Your original recordings are safe. Add footage or Undo to bring your edit back.";
  }
  if (elements.emptyTimelineAdd) {
    elements.emptyTimelineAdd.disabled = busy || Boolean(recovery && !recovery.available);
    elements.emptyTimelineAdd.title=recovery ? (busy?"Wait for the current operation.":recovery.issue || "Activate the saved timeline without rebuilding its clips or settings.") : "";
    elements.emptyTimelineAdd.textContent = recovery ? (state.retainedResumePending?"Resuming saved edit...":"Resume retained edit") : emptyManual ? (state.project.sources?.A ? "Open recording in timeline" : "Import video") : "Add source footage";
  }
  if (elements.clipDuplicate) elements.clipDuplicate.disabled = !sequence || !selectedTimelineClip() || busy;
  renderClipTrim();
  state.trackProtection?.render();
  const locked = state.trackProtection?.lockedNames(target) || [];
  if (locked.length) {
    for (const control of [elements.manualDelete,elements.manualSplit,elements.clipDuplicate,elements.trackReset,gapButton,
      elements.clipTrimIn,elements.clipTrimOut,elements.clipTrimApply,elements.clipSourceIn,elements.clipMove]) if (control && !(control === elements.manualSplit && splitLayer)) control.disabled = true;
    elements.timelineSelectionHint.textContent = `${locked.join(" + ")} locked · Unlock in Edit → Track protection. Playback is unchanged.`;
  }
  if (state.timeline?.tool === "slip") elements.timelineSelectionHint.textContent = "Slip imported video/audio content only. Fixed clip position and duration; left = earlier, right = later.";
  renderDuplicateAvailability();
  if(selectedLayerGroupIds().length){
    for(const control of [elements.trackReset,elements.manualRestore,
      elements.clipTrimIn,elements.clipTrimOut,elements.clipTrimApply,elements.clipSourceIn,elements.clipMove,gapButton])if(control)control.disabled=true;
    const ids=selectedLayerGroupIds();
    renderLayerGroupRemoveAvailability(ids);
    elements.manualSelectionLabel.textContent=`${ids.length} clips selected. Move, split, duplicate or remove together; select one for other edits.`;
    if(elements.manualClear)elements.manualClear.disabled=busy;
  }
  renderLayerGroupControls();
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
  if(selectedLayerGroupIds().length){if(action==="delete_range")return removeTimelineLayerGroup(selectedLayerGroupIds());toast(groupSelectionIssue());return null;}
  if (state.project?.editor_sequence && action === "restore_range") return openSourceReview();
  if (!state.manualSelection) return;
  const rangeState = manualRangeState(target);
  if (!rangeState.valid || (action === "delete_range" && !rangeState.canRemove) || (action === "restore_range" && !rangeState.canRestore)) return;
  return applyManualEdit(target === "edit" ? (state.project?.editor_sequence && action === "delete_range" ? "sequence_ripple_delete" : action) : action === "delete_range" ? "track_remove_range" : "track_restore_range", { ...state.manualSelection, ...(target !== "edit" ? { slot: target } : {}) });
}

// Preview and every native Together range-removal entry point share this gate.
// The server additionally verifies private caption lineage and commits atomically.
function rangeDeleteIssue(start, end, target = "edit") {
  const project = state.project;
  if (target !== "edit" || !project?.editor_sequence) return "";
  const protection=layerEditProtectionIssue("sequence_ripple_delete",{start,end});if(protection)return protection;
  const duration = Number(project.editor_sequence.duration);
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(duration)
      || start < 0 || end > duration + 1e-9 || end <= start) return "Choose a range inside the edited timeline.";
  const manual = project.manual || {};
  if (!manual.media_clips?.length && !manual.text_clips?.length) return ""; // Existing source-only behavior.
  if (project.draft?.audio_plan?.length) return "A timed audio plan is present. Mixed-layer Cut out is not supported for this plan.";
  if (project.caption_alternative_status?.active_id && project.caption_alternative_status.active_id !== "original") return "An alternative caption version is active. Switch back to original captions before mixed-layer Cut out.";
  if (Object.keys(manual.caption_dormant_overrides || {}).length) return "Some caption edits have uncertain ownership. Resolve them before mixed-layer Cut out.";
  const captions = new Map((project.editor_captions || []).map(row => [row.id, row]));
  for (const [id, edit] of Object.entries(manual.caption_overrides || {})) {
    const row = captions.get(id);
    if (!row) return "An edited automatic caption's owner is unavailable. Resolve it before mixed-layer Cut out.";
    if (!edit || ["start_delta", "end_delta"].some(key => Number(edit[key] || 0) !== 0)) return "An edited automatic caption has custom timing. Reset its timing before mixed-layer Cut out.";
    if (row.start < end - 1e-9 && row.end > start + 1e-9) return "The range overlaps a manually edited automatic caption. Resolve that edit or choose another range.";
  }
  const tracks = project.editor_sequence.source_tracks || manual.source_tracks;
  for (const slot of ["A", "B"]) if (manual.track_locks?.[slot] && (!tracks?.[slot] || tracks[slot].some(row => row.end > start + 1e-9))) return `Source ${slot} is locked. Unlock it before removing its time.`;
  for (const key of ["media_clips", "text_clips"]) {
    const rows = manual[key] || [];
    let remaining = 0;
    for (const row of rows) {
      if (row.end <= start + 1e-9 || row.start >= end - 1e-9) { remaining++; continue; }
      const pieces = [];
      if (row.start < start - 1e-9) pieces.push([row.start, start]);
      if (row.end > end + 1e-9) pieces.push([end, row.end]);
      remaining += pieces.length;
      if (!pieces.length) continue; // Whole occurrences need no effect approximation.
      if (key === "text_clips" && row.template === "chapter") return "Cut out would change the fade of a partially retained Chapter title. Remove the whole title in the range, or choose a range outside it.";
      if (pieces.some(([a, b]) => b - a < .08 - 1e-9)) return "Cut out would leave a media or text piece shorter than 0.08 seconds. Choose a clip boundary or move farther from its edge.";
      if (key === "media_clips") {
        const asset = project.assets?.[row.asset_id];
        if (!asset || asset.status !== "ready") return "A partially retained media asset is not ready. Prepare it before Cut out.";
        if (asset.kind !== "audio" && (row.motion || "none") !== "none") return "Cut out would restart a partially retained pan/zoom animation. Select the whole occurrence or choose a range outside it.";
        for (const boundary of pieces.flat()) if (boundary > row.start + 1e-9 && boundary < row.end - 1e-9
            && (boundary - row.start < Number(row.fade_in || 0) - 1e-9 || row.end - boundary < Number(row.fade_out || 0) - 1e-9)) return "A cut edge is inside a media audio fade. Choose boundaries outside the fade or remove the whole occurrence.";
      }
    }
    if (remaining > (key === "media_clips" ? 200 : 2000)) return `Cut out would exceed the ${key === "media_clips" ? "200 media" : "2000 text"} clip limit. Choose boundaries that need fewer splits.`;
  }
  return "";
}

function rangeDeletePreviewIssue(start, end, target = "edit") {
  if (!state.project?.draft) return "Open an edit before choosing a range.";
  if (state.manualEditBusy || foregroundBusy()) return "Wait for the current save or preparation to finish.";
  if (!Number.isFinite(start) || !Number.isFinite(end) || end - start < minimumEditLength() - 1e-6) return "Keep at least one output frame in the selected range.";
  if (rangeInputPending("timeline")) return "Finish entering the range before Cut out.";
  const locked = state.trackProtection?.lockedNames(target) || [];
  if (locked.length) return `${locked.join(" + ")} locked. Unlock in Edit > Track protection before Cut out.`;
  return rangeDeleteIssue(start, end, target);
}

function timelineEditIdentity(project, action, detail = {}) {
  if(action==="layers_duplicate" || action==="layers_relocate")return {selection:JSON.stringify({tracks:project?.manual?.layer_tracks,media:project?.manual?.media_clips,
    text:project?.manual?.text_clips,assets:project?.assets,sources:project?.sources,settings:project?.settings,
    duration:project?.editor_sequence?.duration??project?.draft?.output_duration})};
  if(project?.manual && Object.hasOwn(project.manual,"layer_tracks") && /^(media_|text_|layers_)/.test(action))return {selection:JSON.stringify({tracks:project.manual.layer_tracks,media:project.manual.media_clips,text:project.manual.text_clips,assets:project.assets,duration:project?.editor_sequence?.duration??project?.draft?.output_duration})};
  if(action==="layer_move" || action==="layer_tracks_enable" || action.startsWith("layer_track_"))return {selection:JSON.stringify({revision:project?.revision,tracks:project?.manual?.layer_tracks,media:project?.manual?.media_clips,text:project?.manual?.text_clips,assets:project?.assets,duration:project?.editor_sequence?.duration??project?.draft?.output_duration})};
  if(action==="layers_move" || action==="layers_remove")return {selection:JSON.stringify({ids:detail.clip_ids,
    clips:[...(project?.manual?.media_clips||[]),...(project?.manual?.text_clips||[])].filter(row=>detail.clip_ids?.includes(row.id)),
    assets:(project?.manual?.media_clips||[]).filter(row=>detail.clip_ids?.includes(row.id)).map(row=>project.assets?.[row.asset_id]),
    text:project?.manual?.text_clips,duration:project?.editor_sequence?.duration??project?.draft?.output_duration})};
  if (action === "media_reorder") return { selection: JSON.stringify({
    clips: project?.manual?.media_clips,
    assets: (project?.manual?.media_clips || []).map(row=>project?.assets?.[row.asset_id]),
    duration: project?.editor_sequence?.duration ?? project?.draft?.output_duration,
  }) };
  if (["media_split", "text_split", "media_trim", "text_trim", "media_slip", "media_duplicate", "text_duplicate", "media_move", "text_move", "media_set_enabled", "text_set_enabled", "media_transform"].includes(action)) {
    const key = action.startsWith("text_") ? "text_clips" : "media_clips", clip = project?.manual?.[key]?.find(row => row.id === detail.clip_id);
    const identity = { selection: JSON.stringify({ clip, asset: clip?.asset_id ? project?.assets?.[clip.asset_id] : null, duration: project?.editor_sequence?.duration ?? project?.draft?.output_duration }) };
    if(action==="media_transform")identity.output=JSON.stringify([project?.settings?.aspect,project?.settings?.resolution,project?.settings?.fps]);
    return identity;
  }
  if (action === "sequence_ripple_delete") return { selection: JSON.stringify({
    sequence: project?.editor_sequence, media: project?.manual?.media_clips, text: project?.manual?.text_clips,
    captions: project?.editor_captions, overrides: project?.manual?.caption_overrides,
  }) };
  const bindings = project?.timeline_bindings;
  if (bindings?.version !== 1 || !["sequence_split", "sequence_trim", "sequence_speed"].includes(action)
    || !Array.isArray(bindings.id_actions) || !bindings.id_actions.includes(action)) return null;
  if (bindings.revision !== project.revision) throw new Error("The edit changed. Select the clip again and retry.");
  const track = bindings.tracks?.find(row => row.legacy_slot === detail.slot);
  if (!track?.can_edit_by_id) return null; // Legacy unversioned media keeps its slot API.
  const clips = bindings.clips?.filter(row => row.collection === "primary" && row.track_id === track.id) || [];
  if (action !== "sequence_split" && !clips.some(row => row.id === detail.clip_id)) {
    throw new Error("The clip changed. Select it again and retry.");
  }
  return { fields: { track_id: track.id, source_ref: track.source_ref }, selection: JSON.stringify(clips) };
}

async function applyManualEdit(action, detail = {}, { isCurrent = () => true, strictRevision = false, admissionCurrent = isCurrent } = {}) {
  if(action==="layers_match_frame")return matchTimelineLayerGroup(detail.clip_ids,detail.reference_id);
  if(action==="layers_split")return splitTimelineLayerGroup(detail.clip_ids,detail.frame/state.project?.settings?.fps);
  if(action==="layers_join")return joinTimelineLayerPair(detail.clip_ids);
  if(!requireResumedEdit())return null;
  if(action!=="layer_track_audio" && trackLevelUnfinished()){const draft=explicitPendingDraft();toast(draft.detail);revealPendingSave(draft);return null;}
  if(groupBlocksAction(action)){toast(groupSelectionIssue());return null;}
  const savedTrackIssue=savedLayerTrackIssue();if(savedTrackIssue){toast(savedTrackIssue);return null;}
  if(state.project?.manual && Object.hasOwn(state.project.manual,"layer_tracks") && /^(media_|text_|layers_|layer_)/.test(action))strictRevision=true;
  if (state.project?.editor_sequence?.error) {
    toast(state.project.editor_sequence.error);
    return null;
  }
  if (state.project?.editor_sequence) {
    action = ({ track_move: "sequence_move", track_split: "sequence_split", track_remove_range: "sequence_remove_range", track_trim: "sequence_trim", set_camera_layout: "sequence_layout", track_reset: "sequence_reset" })[action] || action;
    if (action === "sequence_reset") detail = {};
  }
  const protection=layerEditProtectionIssue(action,detail);if(protection){toast(protection);return null;}
  const trackAudio=action==="layer_track_audio";
  if(trackAudio){
    const {track_id,...patch}=detail,plan=planLayerTrackAudio(state.project,track_id,patch),issue=trackLevelIssue({posting:true}) || plan.issue;
    if(issue){toast(issue);return null;}if(!Object.keys(plan.patch||{}).length)return state.project;
    detail={track_id,...plan.patch};strictRevision=true;
  }
  const trackMove=action==="layer_move", trackAction=action==="layer_tracks_enable" || !trackAudio && action.startsWith("layer_track_"), unlocking=layerTrackUnlockRequested(action,detail);
  if(trackMove || trackAction){const issue=layerTrackActionIssue({allowUnlock:unlocking});if(issue){toast(issue);return null;}}
  const trackOverwrite = action === "media_track_overwrite", trackLift = action === "media_track_lift", layerOpacity = action === "media_set_opacity";
  const replaceTake = action === "media_replace_take";
  const layerRoll = action === "media_roll" || action === "media_slide";
  const layerSplit = action === "media_split" || action === "text_split";
  const layerTrim = action === "media_trim" || action === "text_trim", layerSlip = action === "media_slip", layerDuplicate = action === "media_duplicate" || action === "text_duplicate", layerMove = action === "media_move" || action === "text_move", layerReorder = action === "media_reorder", layerEnabled = action === "media_set_enabled" || action === "text_set_enabled", layerFrame = action === "media_transform", groupMove = action === "layers_move", groupRemove = action === "layers_remove", groupDuplicate = action === "layers_duplicate", groupRelocate = action === "layers_relocate", layerStructural = trackOverwrite || trackLift || layerOpacity || replaceTake || layerRoll || trackMove || trackAction || groupMove || groupRemove || groupDuplicate || groupRelocate || layerSplit || layerTrim || layerSlip || layerDuplicate || layerMove || layerReorder || layerEnabled || layerFrame;
  if(trackMove){const plan=layerTrackMovePlan(detail.clip_id,detail.start,detail.track_id);if(plan.issue){toast(plan.issue);return null;}if(!Object.keys(plan.patch||{}).length)return state.project;detail={clip_id:detail.clip_id,start:plan.patch.start,track_id:plan.patch.track_id};}
  if (layerSplit || layerTrim) detail = { ...detail, time: layerSplitTime(detail.time) };
  if (["apply_reel_candidate", "apply_review_candidate", "apply_ai_draft"].includes(action) && state.draftDirtyReasons.size) {
    toast(t("rebuildBeforeRefine"));
    return null;
  }
  const projectLevelAction = action === "set_source_mixer" || action === "set_embedded_camera" || action === "apply_review_candidate"
    || (action === "redo" && Number(state.project?.manual?.history?.redo_count || 0) > 0);
  if ((!state.project?.draft && !projectLevelAction) || state.manualEditBusy || foregroundBusy() || !isCurrent()) return null;
  if (action === "sequence_ripple_delete") {
    const issue = rangeDeleteIssue(detail.start, detail.end, "edit");
    if (issue) { toast(issue); return null; }
  }
  if (layerSplit) {
    const issue = layerSplitIssue(detail.clip_id, detail.time);
    if (issue) { toast(issue); return null; }
  }
  if (layerTrim) {
    const plan = layerTrimPlan(detail.clip_id, detail.edge, detail.time);
    if (plan.issue) { toast(plan.issue); return null; }
    if (!Object.keys(plan.patch || {}).length) return state.project;
  }
  if (layerSlip) {
    const plan = layerSlipPlan(detail.clip_id, detail.source_start);
    if (plan.issue) { toast(plan.issue); return null; }
    if (!Object.keys(plan.patch || {}).length) return state.project;
    detail = {...detail, source_start:plan.patch.source_start};
  }
  if(groupRelocate){const plan=layerGroupRelocatePlan(detail.clip_ids,detail.anchor_id,detail.delta,detail.track_id);if(plan.issue){toast(plan.issue);return null;}if(!plan.patches?.length)return state.project;strictRevision=true;}
  if(groupMove){const plan=layerGroupMovePlan(detail.clip_ids,detail.delta);if(plan.issue){toast(plan.issue);return null;}if(!plan.patches?.length)return state.project;}
  if(groupRemove){const plan=layerGroupRemovePlan(detail.clip_ids);if(plan.issue){toast(plan.issue);return null;}}
  if(groupDuplicate){const plan=layerGroupDuplicatePlan(detail.clip_ids,detail.start);if(plan.issue){toast(plan.issue);return null;}detail={clip_ids:[...detail.clip_ids],start:plan.start};strictRevision=true;}
  if (layerMove) {
    const plan = layerMovePlan(detail.clip_id,detail.start);
    if (plan.issue) { toast(plan.issue); return null; }
    if (!Object.keys(plan.patch || {}).length) return state.project;
    detail={...detail,start:plan.patch.start};
  }
  if (layerFrame) {
    const plan=layerFramePlan(detail.clip_id,Object.fromEntries(Object.entries(detail).filter(([key])=>key!=="clip_id")));
    if(plan.issue){toast(plan.issue);return null;}
    if(!Object.keys(plan.patch||{}).length)return state.project;
    detail={clip_id:detail.clip_id,...plan.patch};
  }
  if (layerEnabled) {
    const plan = layerEnabledPlan(detail.clip_id,detail.enabled);
    if (plan.issue) { toast(plan.issue); return null; }
    if (!Object.keys(plan.patch || {}).length) return state.project;
  }
  if (layerReorder) {
    const plan = layerStackPlan(detail.clip_id,detail.position);
    if (plan.issue) { toast(plan.issue); return null; }
    if (!Object.keys(plan.patch || {}).length) return state.project;
  }
  if (layerDuplicate) {
    const original = state.project?.manual?.[action.startsWith("text_") ? "text_clips" : "media_clips"]?.find(row=>row.id===detail.clip_id);
    const plan = layerDuplicatePlan(detail.clip_id, detail.start === undefined ? original?.start : detail.start);
    if (plan.issue) { toast(plan.issue); return null; }
    detail = {...detail, start:plan.patch.start};
  }
  const splitKey = action.startsWith("text_") || trackMove && String(detail.clip_id).startsWith("text_") ? "text_clips" : "media_clips";
  const splitIds = layerSplit || layerDuplicate ? new Set((state.project?.manual?.[splitKey] || []).map(row => row.id)) : null;
  let displayedIdentity;
  try { displayedIdentity = timelineEditIdentity(state.project, action, detail); }
  catch (error) { toast(error.message); return null; }
  const displayedProjectId = state.project.id;
  const groupPrimary = groupMove || groupDuplicate || groupRelocate ? state.timeline?.mediaSelection : null;
  const groupCopyViewport=groupDuplicate || groupRelocate?layerGroupDuplicateViewport():null;
  // Unlock is protection-only recovery. Do not force a protected local buffer
  // through a save it cannot pass; keep it for the user's explicit retry/discard.
  if (unlocking && (state.mediaStudio?.saving || state.textStudio?.saving || state.chromaStudio?.saving)) return null;
  if (!unlocking && (!action.startsWith("text_") || layerStructural) && state.textStudio && !(await state.textStudio.flush())) return null;
  if (state.project?.id !== displayedProjectId || state.manualEditBusy || foregroundBusy() || !isCurrent()) return null;
  if (!unlocking && (action === "undo" || action === "redo" || action === "sequence_ripple_delete" || layerStructural) && state.mediaStudio && !(await state.mediaStudio.flush())) return null;
  if (state.project?.id !== displayedProjectId || state.manualEditBusy || foregroundBusy() || !isCurrent()) return null;
  state.timeline?.cancelPendingCut?.();
  const projectId = state.project.id, editViewToken = state.projectViewToken;
  let preservedSelection = state.manualSelection ? { ...state.manualSelection } : null;
  let preservedTime = previewTimelineTime();
  // Mixer and layer adjustments do not change the main playback clock. Keep
  // auditioning while their automatic saves run, without reloading the video.
  const liveMediaAction = trackAudio || action === "media_update" || action === "set_audio_mixer" || action === "set_track_lock" || action === "layer_track_lock" || (action.startsWith("text_") && !layerStructural)
    || action.startsWith("caption_");
  let finishManualEdit;
  const manualEditPromise = new Promise((resolve) => { finishManualEdit = resolve; });
  state.manualEditPromise = manualEditPromise;
  state.manualEditBusy = true;
  if (!liveMediaAction) pausePreview();
  renderReadiness();
  renderManualControls();
  renderSourceMixer();
  let splitResult = null;
  try {
    await flushProjectSaves(projectId);
    if (state.project?.id !== projectId || !isCurrent()) return null;
    const currentIdentity = timelineEditIdentity(state.project, action, detail);
    if (JSON.stringify(currentIdentity) !== JSON.stringify(displayedIdentity)) {
      state.timeline?.clearSelection();
      if(groupMove)state.timeline?.setMediaSelection?.([],null);
      throw new Error("The edit or source changed while saving. Select the clip again and retry.");
    }
    if (action === "sequence_ripple_delete") {
      const issue = rangeDeleteIssue(detail.start, detail.end, "edit");
      if (issue) throw new Error(issue);
    }
    if (layerSplit) {
      const issue = layerSplitIssue(detail.clip_id, detail.time);
      if (issue) throw new Error(issue);
    }
    if (layerTrim) {
      const plan = layerTrimPlan(detail.clip_id, detail.edge, detail.time);
      if (plan.issue) throw new Error(plan.issue);
    }
    if (layerSlip) {
      const plan = layerSlipPlan(detail.clip_id, detail.source_start);
      if (plan.issue) throw new Error(plan.issue);
    }
    if(groupRelocate){const plan=layerGroupRelocatePlan(detail.clip_ids,detail.anchor_id,detail.delta,detail.track_id);if(plan.issue)throw new Error(plan.issue);}
    if(groupMove){const plan=layerGroupMovePlan(detail.clip_ids,detail.delta);if(plan.issue)throw new Error(plan.issue);}
    if(groupRemove){const plan=layerGroupRemovePlan(detail.clip_ids);if(plan.issue)throw new Error(plan.issue);}
    if(groupDuplicate){const plan=layerGroupDuplicatePlan(detail.clip_ids,detail.start);if(plan.issue)throw new Error(plan.issue);}
    if (layerMove) {
      const plan=layerMovePlan(detail.clip_id,detail.start);
      if (plan.issue) throw new Error(plan.issue);
    }
    if (layerFrame) {
      const plan=layerFramePlan(detail.clip_id,Object.fromEntries(Object.entries(detail).filter(([key])=>key!=="clip_id")));
      if(plan.issue)throw new Error(plan.issue);
    }
    if (layerEnabled) {
      const plan = layerEnabledPlan(detail.clip_id,detail.enabled);
      if (plan.issue) throw new Error(plan.issue);
    }
    if (layerReorder) {
      const plan = layerStackPlan(detail.clip_id,detail.position);
      if (plan.issue) throw new Error(plan.issue);
    }
    if (layerDuplicate) {
      const plan = layerDuplicatePlan(detail.clip_id, detail.start);
      if (plan.issue) throw new Error(plan.issue);
    }
    if(trackAudio){const {track_id,...patch}=detail,plan=planLayerTrackAudio(state.project,track_id,patch);if(plan.issue)throw new Error(plan.issue);}
    if(trackMove || trackAction){const issue=layerTrackActionIssue({allowUnlock:unlocking});if(issue)throw new Error(issue);}
    if(trackMove){const plan=layerTrackMovePlan(detail.clip_id,detail.start,detail.track_id);if(plan.issue)throw new Error(plan.issue);}
    const protection=layerEditProtectionIssue(action,detail);if(protection)throw new Error(protection);
    if(!admissionCurrent())return null;
    const expectedRevision = saveQueueFor(projectId, state.project?.revision).revision;
    const submit = (revision) => api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`, {
      method: "POST",
      body: JSON.stringify({ action, ...detail, ...displayedIdentity?.fields, expected_revision: revision }),
    });
    const copyBefore=groupDuplicate?JSON.parse(JSON.stringify(state.project)):null;
    const relocateBefore=groupRelocate?JSON.parse(JSON.stringify(state.project)):null;
    if(replaceTake){
      const issue=planTake(state.project,takeContext(state.project,detail.clip_id),detail).issue;
      if(issue || expectedRevision!==state.project.revision)throw new Error(issue||"The edit changed before replacing this take.");
    }
    if(trackOverwrite){
      const issue=planTrackOverwrite(state.project,detail).issue;
      if(issue || expectedRevision!==state.project.revision)throw new Error(issue||"The chosen track changed before the overwrite.");
    }
    if(trackLift){
      const issue=planTrackLift(state.project,detail).issue;
      if(issue||expectedRevision!==state.project.revision)throw new Error(issue||"The reviewed range or chosen track changed before the lift.");
    }
    if(layerOpacity){const plan=planClipOpacity(state.project,detail.clip_id,detail.opacity_percent);
      if(plan.issue||plan.noop||expectedRevision!==state.project.revision)throw new Error(plan.issue||"The occurrence changed before saving opacity.");}
    const opacityBefore=layerOpacity?structuredClone(state.project):null;
    const overwriteBefore=trackOverwrite||trackLift?structuredClone(state.project):null;
    const takeBefore=replaceTake?structuredClone(state.project):null;
    if(layerRoll && expectedRevision!==state.project.revision)throw new Error("The cut changed before saving. Review the current edit.");
    const rollBefore=layerRoll?structuredClone(state.project):null;
    const trackAudioBefore=trackAudio?structuredClone(state.project):null;
    let payload;
    try {
      payload = await submit(expectedRevision);
    } catch (error) {
      const sourceConflict = Number(error?.status) === 409 && error?.code === "source_binding_conflict";
      if(((action==="apply_ai_draft" && detail.proposal_id) || ["set_chroma_key","reset_chroma_key"].includes(action)) && Number(error?.status)===409
        && (isRevisionConflict(error) || sourceConflict || ["stale_ai_draft_proposal","invalid_ai_draft_proposal"].includes(error?.code))){
        // Refresh history/current edit after a refused proposal, but never replay
        // the reviewed decision against a different revision or source.
        if(state.project?.id!==projectId || state.projectViewToken!==editViewToken)return null;
        const latest=await api(`/api/projects/${encodeURIComponent(projectId)}`);
        if(state.project?.id!==projectId || state.projectViewToken!==editViewToken)return null;
        if(!latest?.project || latest.project.id!==projectId)throw error;
        if(Number(latest.project.revision)<Number(state.project.revision))throw new Error(action==="apply_ai_draft" ? "A newer project version is already loaded. Open a fresh AI draft review; nothing was reapplied." : "A newer project version is already loaded. Review the current Chroma Key settings; nothing was reapplied.");
        state.project=latest.project;
        hydrateProject();
        state.timeline?.clearSelection();state.markIn=null;
        if(state.project.draft)seekSourcePreview(preservedTime);
        throw new Error(action==="apply_ai_draft" ? "The project or source changed. The latest saved version is loaded. Open a fresh AI draft review; the proposal was not reapplied." : "The project or source changed. The latest saved version is loaded. Your unapplied Chroma Key settings are kept; review them before trying again.");
      }
      if (detail.proposal_id || detail.review_fingerprint || (!isRevisionConflict(error) && !sourceConflict) || state.project?.id !== projectId || action === "transcript_text") throw error;
      if((strictRevision && state.projectViewToken!==editViewToken) || (groupRemove && (state.projectViewToken!==editViewToken || !isCurrent())))return null;
      const latest = await api(`/api/projects/${encodeURIComponent(projectId)}`);
      if (state.project?.id !== projectId || (strictRevision && state.projectViewToken!==editViewToken) || (groupRemove && (state.projectViewToken!==editViewToken || !isCurrent()))) return null;
      if (!latest?.project || (!latest.project.draft && !projectLevelAction)) throw error;
      if((strictRevision || groupRemove) && (latest.project.id!==projectId || Number(latest.project.revision)<Number(state.project.revision)))throw error;
      state.project = latest.project;
      rememberProjectRevision(state.project);
      if (action === "media_insert" || layerStructural || strictRevision) {
        if(groupDuplicate || groupRelocate || trackAudio || layerRoll || replaceTake || trackOverwrite || trackLift || layerOpacity){
          // A refused group action still refreshes saved data, but a newer pane,
          // selection or viewing clock owns navigation after the POST began.
          state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
          if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
          updateMediaPreview();renderManualControls();renderLayerTrackControls();
          if(layerOpacity)throw new Error("The edit changed elsewhere. The latest opacity is loaded; no change was repeated. Review this occurrence again.");
          if(trackLift)throw new Error("The edit changed elsewhere. The latest track is loaded; no lift was repeated. Review the current range and track.");
          if(trackOverwrite)throw new Error("The edit changed elsewhere. The latest track is loaded; no overwrite was repeated. Review the new destination.");
          if(replaceTake)throw new Error("The edit changed elsewhere. The latest take is loaded; the replacement was not repeated.");
          if(layerRoll)throw new Error("The cut changed elsewhere. The latest edit is loaded; the edit was not repeated.");
          if(trackAudio)throw new Error("The track mix changed elsewhere. The latest saved mix is loaded; the change was not repeated. Review the level and try again.");
          throw new Error(groupRelocate ? "The edit changed elsewhere. The latest saved version is loaded; the track move was not repeated. Review the destination before trying again." : "The edit changed elsewhere. The latest saved version is loaded; the copy was not repeated. Review the copy destination before trying again.");
        }
        renderDraft();
        state.timeline?.clearSelection();
        if(groupMove)state.timeline?.setMediaSelection?.([],null);
        if(groupMove || groupRemove || strictRevision)seekSourcePreview(preservedTime);
        throw new Error(layerStructural ? `The clip changed elsewhere. The latest version is loaded; review the ${groupRemove ? "selected clips before removing them" : groupMove ? "selection placement" : groupDuplicate ? "copy destination" : trackMove || trackAction ? "track layout" : layerFrame ? "frame geometry" : layerEnabled ? "clip availability" : layerReorder ? "visual order" : layerMove ? "placement" : layerDuplicate ? "copy destination" : layerSlip ? "source point" : layerTrim ? "trim point" : "split point"} and retry.` : strictRevision ? "The edit changed elsewhere. The latest version is loaded; review the source destination and retry." : "The edit changed elsewhere. The latest version is loaded; review the insertion point and retry.");
      }
      if (!isCurrent()) return null;
      if (action.startsWith("sequence_") || action.startsWith("text_")) {
        renderDraft();
        state.timeline?.clearSelection();
        throw new Error("The edit changed elsewhere. The latest version is loaded; select the clip again and retry.");
      }
      payload = await submit(saveQueueFor(projectId, state.project.revision).revision);
    }
    if (!payload?.project) throw new Error("Manual edit did not return an updated project");
    if((groupRemove || strictRevision) && (payload.project.id!==projectId || !Number.isInteger(payload.project.revision)))throw new Error("The edit returned an invalid project. Reload before editing again.");
    if(groupRemove && state.project?.id===projectId && state.projectViewToken===editViewToken
      && payload.project.revision<Number(state.project.revision))throw new Error("A newer saved edit is already loaded. Review the current selection; the older removal response was not substituted.");
    if(trackAudio){const {track_id,...patch}=detail,issue=verifyLayerTrackAudio(trackAudioBefore,payload.project,track_id,patch);if(issue)throw new Error(`The track level response could not be verified. Reload before retrying. ${issue}`);}
    if(layerOpacity){const issue=verifyClipOpacity(opacityBefore,payload.project,detail);if(issue)throw new Error("Saved opacity could not be verified. Reopen the edit before repeating it. "+issue);}
    if(trackLift){const issue=verifyTrackLift(overwriteBefore,payload.project,detail);if(issue)throw new Error("The saved lift could not be verified. Reopen the edit before repeating it. "+issue);}
    if(trackOverwrite){const issue=verifyTrackOverwrite(overwriteBefore,payload.project,detail);if(issue)throw new Error("The saved overwrite could not be verified. Reopen the edit before trying again. "+issue);}
    if(replaceTake){const issue=verifyTake(takeBefore,payload.project,detail);if(issue)throw new Error("Replacement could not be verified. Reopen the edit before repeating it. "+issue);}
    if(layerRoll){const issue=verifyRoll(rollBefore,payload.project,detail);if(issue)throw new Error("The cut edit response could not be verified. Reopen the edit before trying again. "+issue);}
    const relocationReceipt=groupRelocate?verifyLayerGroupRelocate(relocateBefore,payload.project,detail.clip_ids,detail.anchor_id,detail.track_id,detail.delta):null;
    if(relocationReceipt?.issue)throw new Error(`The track move response could not be verified. Reload to review the saved edit; do not repeat it yet. ${relocationReceipt.issue}`);
    const copyReceipt=groupDuplicate?verifyLayerGroupDuplicate(copyBefore,payload.project,detail.clip_ids,detail.start,payload.created):null;
    if(copyReceipt?.issue)throw new Error(`The copy response could not be verified. Reload to review the saved edit; do not repeat Duplicate yet. ${copyReceipt.issue}`);
    rememberProjectRevision(payload.project);
    if (state.project?.id !== projectId || (strictRevision && state.projectViewToken!==editViewToken) || (!strictRevision && !isCurrent())) return payload.project;
    if(strictRevision){
      // A nonmodal source card can be closed after the request was admitted.
      // Accept its completed save in the same view without reviving the card or
      // overwriting newer local state/navigation. Other views remain untouched.
      if(Number(payload.project.revision)<Number(state.project.revision))return payload.project;
      preservedTime=previewTimelineTime();
      if(!isCurrent())preservedSelection=null;
    }
    if (["set_chroma_key","reset_chroma_key"].includes(action) && Number(payload.project.revision)<Number(state.project.revision)) return payload.project;
    state.project = payload.project;
    if (action === "set_track_lock") {
      state.chromaStudio?.render();
      state.timeline?.cancelGesture?.();
      if (state.timeline) { state.timeline.project = editorProject(); state.timeline.scheduleDraw(); }
      state.trackProtection?.render();
      return state.project;
    }
    if (layerFrame || layerRoll || replaceTake || trackOverwrite || trackLift || layerOpacity) {
      // A lift may remove the previously highlighted occurrence. Do not leave
      // a dead selectable clip, or change a newer selection/Program position.
      if(trackLift && state.timeline?.mediaSelection && ![...(state.project.manual?.media_clips||[]),...(state.project.manual?.text_clips||[])].some(c=>c.id===state.timeline.mediaSelection)){
        state.timeline.setMediaSelection?.([],null);
      }
      // Preserve occurrence identity and transport. Replacement changes only
      // the chosen URL; MediaStudio.sync retires its previous A/V decoders.
      // Update in place: a full draft rebuild briefly exposes cursor 0 and
      // re-reveals the inspector, interrupting direct viewer adjustments.
      state.mediaStudio?.render();
      state.chromaStudio?.render();
      if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
      updateMediaPreview();
      renderManualControls();
      return state.project;
    }
    if(groupRelocate){
      // Membership and timing were verified together. Keep newer navigation,
      // selection, Program clock and local focus instead of rebuilding the view.
      state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
      if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
      if(isCurrent()){
        state.timeline?.setMediaSelection?.(detail.clip_ids,groupPrimary);
        const timeline=state.timeline,revision=payload.project.revision,context=layerGroupDuplicateContext(),members=JSON.stringify([...detail.clip_ids].sort());
        requestAnimationFrame(()=>{
          if(state.timeline===timeline && state.project?.id===projectId && state.projectViewToken===editViewToken
            && state.project.revision===revision && timeline?.mediaSelection===groupPrimary
            && JSON.stringify([...selectedLayerGroupIds()].sort())===members && layerGroupDuplicateContext()===context
            && layerGroupDuplicateViewport()===groupCopyViewport)timeline?.revealMedia?.(groupPrimary);
        });
      }
      updateMediaPreview();renderManualControls();renderLayerTrackControls();return state.project;
    }
    if(groupDuplicate){
      // The copies are new occurrences, not a new navigation request. Refresh the
      // saved scene in place and never reopen a pane or seek after a late reply.
      state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
      if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
      if(isCurrent()){
        state.timeline?.clearSelection();state.manualSelection=null;state.trimClip=null;state.markIn=null;
        const primary=copyReceipt.mapping[groupPrimary] || copyReceipt.clip_ids[0];
        state.timeline?.setMediaSelection?.(copyReceipt.clip_ids,primary);
        const timeline=state.timeline,revision=payload.project.revision,context=layerGroupDuplicateContext(),members=JSON.stringify([...copyReceipt.clip_ids].sort());
        requestAnimationFrame(()=>{
          // New lanes need the scheduled canvas-height update before scrolling.
          // This callback owns neither a newer view nor later scroll/selection.
          if(state.timeline===timeline && state.project?.id===projectId && state.projectViewToken===editViewToken
            && state.project.revision===revision && timeline?.mediaSelection===primary
            && JSON.stringify([...selectedLayerGroupIds()].sort())===members && layerGroupDuplicateContext()===context
            && layerGroupDuplicateViewport()===groupCopyViewport)timeline?.revealMedia?.(primary);
        });
      }
      updateMediaPreview();renderManualControls();renderLayerTrackControls();return state.project;
    }
    if(groupRemove){
      previewLayerGroup(null);
      state.timeline?.setMediaSelection?.([],null);state.timeline?.clearSelection();
      state.manualSelection=null;state.trimClip=null;state.markIn=null;
      renderDraft();seekSourcePreview(preservedTime);renderManualControls();return state.project;
    }
    if(groupMove){
      previewLayerGroup(null);renderDraft();
      state.timeline?.clearSelection();state.timeline?.setMediaSelection?.(detail.clip_ids,groupPrimary);
      seekSourcePreview(preservedTime);renderManualControls();return state.project;
    }
    if(trackAction || trackMove){
      // Track membership/order never changes sequence duration or source media.
      // Refresh in place so a completed save cannot reopen a pane, reset the
      // Program clock or discard a newer inspector/navigation choice.
      if(action==="layer_track_lock")state.timeline?.cancelGesture?.();
      state.mediaStudio?.render();state.textStudio?.render();state.chromaStudio?.render();
      if(state.timeline){state.timeline.project=editorProject();state.timeline.scheduleDraw?.();}
      updateMediaPreview();renderManualControls();renderLayerTrackControls();
      if(trackMove && isCurrent() && state.timeline?.mediaSelection===detail.clip_id)state.timeline.revealMedia?.(detail.clip_id);
      return state.project;
    }
    if (layerStructural) {
      renderDraft();
      const resultClip = trackMove || layerTrim || layerSlip || layerMove || layerReorder || layerEnabled || layerFrame ? state.project.manual?.[splitKey]?.find(row => row.id === detail.clip_id)
        : (state.project.manual?.[splitKey] || []).filter(row => !splitIds.has(row.id) && Math.abs(row.start - (layerDuplicate ? detail.start : detail.time)) < 1e-6).at(-1);
      state.timeline?.clearSelection();
      if (resultClip) splitResult = { id: resultClip.id, projectId, revision: state.project.revision };
      seekSourcePreview(trackMove || layerTrim || layerSlip || layerMove || layerReorder || layerEnabled || layerFrame ? preservedTime : layerDuplicate ? detail.start : detail.time);
      renderManualControls();
      return state.project;
    }
    if (liveMediaAction) {
      state.mediaStudio?.render();
      state.chromaStudio?.render();
      state.textStudio?.render();
      if (state.timeline) { state.timeline.project = editorProject(); state.timeline.scheduleDraw(); }
      updateMediaPreview();
      if (action.startsWith("caption_")) {
        if (detail.scope === "source" || action === "caption_alternative") renderTranscript();
        renderCaptionInspector();
        updatePreviewCaption(previewPlaybackTime());
      }
      return state.project;
    }
    const refreshSavedEdit = () => {
      elements.projectName.value = projectLabel(state.project);
      hydrateSettings();
      if (state.project.draft) {
        if (action === "apply_review_candidate" || (action === "redo" && elements.resultPanel.hidden)) showResult();
        else renderDraft();
      }
      else {
        showSetup();
        renderSources();
        renderSourceMixer();
      }
      if (action === "sequence_ripple_delete" || action === "sequence_close_gaps") {
        state.timeline?.clearSelection();
        state.markIn = null;
        seekSourcePreview(Math.min(action === "sequence_close_gaps" ? preservedTime : Number(detail.start), editorDuration()));
      } else if (action === "undo" || action === "redo" || action === "apply_ai_draft") {
        // History can restore different clip boundaries. Old selection bounds
        // must not turn the restored clip into a stale movable range.
        state.timeline?.clearSelection();
        state.markIn = null;
        seekSourcePreview(preservedTime);
      } else {
        if (preservedSelection) state.timeline.selectRange(preservedSelection.start, preservedSelection.end);
        else setManualSelection(null);
        seekSourcePreview(preservedTime);
      }
      renderManualControls();
      return state.project;
    };
    // History restores the saved cursor after rebuilding panels. Coalesce only
    // this synchronous paint so frame mode sees the final state, not cursor 0.
    return (action==="undo" || action==="redo") && state.mediaStudio?.deferFrameSync
      ? state.mediaStudio.deferFrameSync(refreshSavedEdit) : refreshSavedEdit();
  } catch (error) {
    toast(`${uiCopy("התיקון הידני נכשל", "Manual correction failed")}: ${error.message}`);
    return null;
  } finally {
    state.manualEditBusy = false;
    state.textStudio?.render();
    renderCaptionInspector();
    finishManualEdit();
    if (state.manualEditPromise === manualEditPromise) state.manualEditPromise = null;
    renderReadiness();
    renderManualControls();
    renderSourceMixer();
    renderReelCandidates();
    // This is the verified result of our saved edit, not a new navigation
    // request. The public Index correctly remains blocked while Blade waits
    // for this promise; use the existing inspector-selection transaction.
    if (splitResult && state.project?.id === splitResult.projectId && state.project.revision === splitResult.revision) {
      try {
        if (await selectTimelineMedia(splitResult.id)) {
          state.timeline?.revealMedia?.(splitResult.id);
          renderManualControls();
        }
      } catch (error) {
        toast(layerFrame ? "The framing was saved. Select the clip to reopen the inspector." : layerEnabled ? "The clip availability was saved. Select the clip to reopen the inspector." : layerReorder ? "The visual order was saved. Select the clip to reopen the inspector." : layerMove ? "The move was saved. Select the clip to reopen the inspector." : layerDuplicate ? "The copy was saved. Select the new occurrence to reopen the inspector." : layerSlip ? "The slip was saved. Select the clip to reopen the inspector." : layerTrim ? "The trim was saved. Select the clip to reopen the inspector." : "The split was saved. Select its right-hand piece to reopen the inspector.");
      }
    }
  }
}

// Saved Transcript sections are navigation only. Never reuse edit/flush paths.
function initializeTranscriptSections() {
  const root = document.getElementById("transcriptSections"), choice = document.getElementById("transcriptSectionChoice"),
    go = document.getElementById("transcriptSectionGo"), status = document.getElementById("transcriptSectionsStatus");
  if (!root || !choice || !go || !status || typeof planTranscriptSections !== "function") return;
  const ui = { root, choice, go, status, project: null, view: null, segmentId: null, plan: null, key: "", notice: "" };
  state.transcriptSectionsUI = ui;
  ui.refresh = () => renderTranscriptSectionsReadiness(ui);
  choice.addEventListener("change", () => {
    if (!transcriptSectionsDOMCurrent(ui)) return;
    ui.key = ui.plan?.sections?.some(section => section.key === choice.value) ? choice.value : "";
    ui.notice = ""; ui.refresh();
  });
  go.addEventListener("click", () => goToTranscriptSection(ui));
  // Native select/button keyboard events must not invoke global transport.
  root.addEventListener("keydown", event => event.stopPropagation());
}

function transcriptSectionNavigationIssue() {
  if (!state.project?.id || !state.timeline || !state.studio.open) return "Open this saved edit in Studio first.";
  if (selectedTranscriptRecoveryDraft()) return "Retained drafts are for Copy or Discard, not timeline navigation.";
  const recovery = transcriptBatchIssue(); if (recovery) return recovery;
  if (pendingTranscriptBuffers().some(buffer => transcriptDraftReview(buffer)))
    return "Copy or Discard the retained transcript drafts before going to a saved section.";
  // The existing batch admission inventory permits ordinary Transcript buffers,
  // but excludes all other explicit drafts, queues, processing and gestures.
  const pending = transcriptBatchOtherIssue();
  if (pending) return pending.replace("before saving transcript changes", "before going to a timeline section");
  const gesture = workspaceResizeIssue(); if (gesture) return gesture;
  if (state.timeline.sourceReview || state.timeline.zoomFocusPending || state.timeline.afterDraw
    || state.editingPositions?.loading || state.editingPositions?.applying)
    return "Finish the current timeline navigation before going to this section.";
  if (document.querySelector("dialog[open]")) return "Close the current dialog before going to this section.";
  if (state.preview.mode !== "edit") return "Choose Edited video in the Program preview mode control to go to this section.";
  return "";
}

function transcriptSectionRangeNote() {
  const range = state.manualSelection;
  return range && Number.isFinite(range.start) && Number.isFinite(range.end) && range.end > range.start
    ? `Selected range remains ${formatTime(range.start, true)} - ${formatTime(range.end, true)}.`
    : "Timeline selection is unchanged.";
}

function renderTranscriptSectionsReadiness(ui = state.transcriptSectionsUI) {
  if (!ui || state.transcriptSectionsUI !== ui || ui.root.hidden) return;
  const section = ui.plan?.sections?.find(row => row.key === ui.key);
  const stale = ui.project !== state.project || ui.view !== state.projectViewToken
    || ui.segmentId !== String(selectedTranscriptSegment()?.id);
  const issue = stale ? "Choose this saved transcript line again to review its current sections."
    : !ui.plan?.ok || !ui.plan.sections.length ? ui.plan?.issue || "No saved section is available."
    : transcriptSectionNavigationIssue();
  ui.choice.disabled = stale || !ui.plan?.ok || !ui.plan.sections.length;
  ui.go.disabled = Boolean(issue || !section);
  ui.go.title = issue || (!section ? "Choose one saved timeline section first." : "Pause and move the playhead only; timeline selection stays unchanged.");
  const detail = section ? `Section ${section.ordinal}: edit ${section.start.toFixed(6)} - ${section.end.toFixed(6)} s; Source ${ui.plan.sourceSlot} ${section.sourceStart.toFixed(6)} - ${section.sourceEnd.toFixed(6)} s${section.partial ? "; partial line" : ""}.`
    : "Choose a saved section, then use Go to section.";
  ui.status.textContent = `${issue || ui.notice || detail} ${transcriptSectionRangeNote()}`;
  ui.status.title = section ? `Canonical clip ${section.clipId}; exact edited interval ${section.start} - ${section.end}; exact source interval ${section.sourceStart} - ${section.sourceEnd}.` : "";
}

function renderTranscriptSections() {
  const ui = state.transcriptSectionsUI;
  if (!ui) return;
  const segment = selectedTranscriptSegment();
  const hidden = !segment || Boolean(selectedTranscriptRecoveryDraft());
  ui.root.hidden = hidden;
  if (hidden) { ui.project = null; ui.plan = null; ui.key = ""; ui.notice = ""; return; }
  const plan = planTranscriptSections(state.project, segment.id);
  const same = ui.project === state.project && ui.view === state.projectViewToken && ui.segmentId === String(segment.id)
    && ui.plan?.ok === plan.ok && ui.plan?.identity === plan.identity && ui.plan?.code === plan.code;
  if (!same) {
    ui.key = plan.ok && plan.sections.length === 1 ? plan.sections[0].key : "";
    ui.notice = ""; ui.choice.replaceChildren();
    const placeholder = document.createElement("option"); placeholder.value = "";
    placeholder.textContent = plan.ok && plan.sections.length ? "Choose a section" : "No saved section available";
    ui.choice.append(placeholder);
    for (const section of plan.sections) {
      const option = document.createElement("option"); option.value = section.key;
      option.textContent = `${section.ordinal}. Edit ${formatTime(section.start, true)} - ${formatTime(section.end, true)} | Source ${plan.sourceSlot} ${formatTime(section.sourceStart, true)} - ${formatTime(section.sourceEnd, true)}${section.partial ? " | partial line" : ""}`;
      ui.choice.append(option);
    }
    ui.choice.value = ui.key;
  }
  ui.project = state.project; ui.view = state.projectViewToken; ui.segmentId = String(segment.id); ui.plan = plan;
  ui.refresh();
}

function transcriptSectionsDOMCurrent(ui) {
  return Boolean(ui && state.transcriptSectionsUI === ui && ui.root.isConnected && !ui.root.hidden
    && !ui.root.closest("[hidden], [inert]") && ui.root.getClientRects().length > 0
    && document.querySelector('.advanced-tabs [aria-selected="true"]')?.dataset.tab === "transcript"
    && document.getElementById("transcriptSections") === ui.root
    && document.getElementById("transcriptSectionChoice") === ui.choice
    && document.getElementById("transcriptSectionGo") === ui.go
    && document.getElementById("transcriptSectionsStatus") === ui.status
    && [ui.choice, ui.go, ui.status].every(node => node.isConnected && ui.root.contains(node)));
}

function goToTranscriptSection(ui = state.transcriptSectionsUI) {
  if (!transcriptSectionsDOMCurrent(ui)) return false;
  const context = { project: ui.project, view: ui.view, segmentId: ui.segmentId,
    key: ui.key, plan: ui.plan, range: JSON.stringify(state.manualSelection),
    playhead: state.timeline?.playhead, inspectorEpoch: state.inspectorSelectionEpoch,
    filter: elements.transcriptFilter?.value, query: elements.transcriptSearch?.value,
    pane: document.querySelector('.advanced-tabs [aria-selected="true"]')?.dataset.tab };
  let expectedPlayhead = context.playhead;
  const snapshot = () => ({ project: state.project, viewToken: state.projectViewToken,
    segmentId: selectedTranscriptSegment()?.id, mode: state.preview.mode });
  const current = () => transcriptSectionsDOMCurrent(ui)
    && ui.project === context.project && ui.view === context.view && ui.segmentId === context.segmentId
    && ui.plan === context.plan && ui.key === context.key && ui.choice.value === context.key
    && state.inspectorSelectionEpoch === context.inspectorEpoch && JSON.stringify(state.manualSelection) === context.range
    && state.timeline?.playhead === expectedPlayhead
    && elements.transcriptFilter?.value === context.filter && elements.transcriptSearch?.value === context.query
    && document.querySelector('.advanced-tabs [aria-selected="true"]')?.dataset.tab === context.pane;
  const intent = captureSectionIntent({ project: context.project, viewToken: context.view,
    segmentId: context.segmentId }, context.plan, context.key);
  const ok = navigateTranscriptSection(intent, { snapshot, current, issue: transcriptSectionNavigationIssue,
    cancelCut: () => state.timeline?.cancelPendingCut?.(), pause: pauseAllMedia,
    seek: time => { expectedPlayhead = time; seekSourcePreview(time); } });
  if (current() && state.project === context.project && state.projectViewToken === context.view) {
    ui.notice = ok ? "Playhead moved to the saved section. Playback is paused."
      : "Section navigation was not admitted; no newer view or choice was replaced.";
    ui.refresh();
  }
  return ok;
}

function submitTranscriptText(event) {
  event.preventDefault();
  // Native Enter in the added navigation region is never a Save-text intent.
  if (state.transcriptSectionsUI?.root.contains(document.activeElement)) return false;
  return saveTranscriptBuffers(false);
}


// The batch owner outlives its pane. Recovery never goes through Open's save flush.
function transcriptBatchOwner(projectId = state.project?.id) {
  return state.transcriptBatches?.get(projectId) || null;
}

function transcriptBatchIssue(projectId = state.project?.id) {
  const owner = transcriptBatchOwner(projectId), status = owner?.protocol?.snapshot();
  if (owner?.savedReload && state.project?.id === projectId && state.project.revision < owner.savedReload)
    return "These transcript changes are saved in a newer version. Explicitly load that version before another saved edit.";
  if (owner?.loading) return "Loading the newer saved transcript. Every draft is retained.";
  if (status?.pending) return "Saving or checking the reviewed transcript changes. Please wait.";
  if (status?.canCheck) return status.issue || "Check the transcript save outcome before making another saved edit.";
  return "";
}

function transcriptBatchOtherIssue(owner = null) {
  const project = state.project, media = state.mediaStudio, text = state.textStudio, timeline = state.timeline;
  const own = Boolean(owner && transcriptBatchOwner(project?.id) === owner);
  if (!project?.id || !Number.isSafeInteger(project.revision) || project.revision < 1) return "Open a saved project first.";
  const explicit = explicitPendingDraft();
  if (explicit) return explicit.detail;
  const trackIssue = savedLayerTrackIssue(); if (trackIssue) return trackIssue;
  const retained = retainedEditIssue(); if (retained) return retained;
  const queue = state.saveQueues.get(project.id);
  if ((!own && (state.transcriptSaving || transcriptBatchIssue())) || state.manualEditBusy || state.manualEditPromise
    || state.captionContextSave || previewRepairBusy() || projectCopySourceBusy() || state.activeJob
    || state.activeUploads.size || state.jobStartLocks.size || media?.uploading || media?.placing
    || media?.importQueue?.running || media?.pending?.size || media?.saving || media?.saveError
    || text?.dirty?.() || text?.pending?.size || text?.saving || text?.saveError
    || state.chromaStudio?.saving || state.stabilizationStudio?.uploading
    || state.sourceMixerSavePending || state.sourceSyncPending || liveEmbeddedCameraRequest()
    || state.embeddedEditor?.dirty || state.embeddedEditor?.saving || queue?.pending || queue?.inFlight || queue?.timer || queue?.error)
    return "Finish or retry the other pending save or processing before saving transcript changes.";
  if (timeline?.gesture || timeline?.scrubbing || timeline?.editPending || timeline?.libraryDragActive
    || timeline?.mediaSelectionPending || timeline?.mediaSourceOpening || timeline?.trackLockPending
    || state.sourceReview?.busy || state.sourceReview?.timeline?.gesture || state.sourceReview?.timeline?.scrubbing
    || media?.shotReview?.pending || media?.frameEditor?.active || media?.frameEditorState?.dragging
    || state.embeddedEditor?.dragging || document.documentElement?.classList?.contains?.("numeric-scrubbing"))
    return "Finish or cancel the current editing gesture first.";
  return "";
}

function transcriptBufferProvenance(project = state.project) {
  const transcript = project?.analysis?.transcript;
  if (!transcript || typeof transcript !== "object" || !Array.isArray(transcript.segments)) return null;
  const metadata = { ...transcript }; delete metadata.text; delete metadata.segments;
  return JSON.stringify({ sources: project.sources, metadata,
    audio_source: project.analysis.audio_source, audio_timeline_offset: project.analysis.audio_timeline_offset });
}

function transcriptDraftReview(buffer) {
  if (!buffer || buffer.projectId !== state.project?.id) return null;
  const rows = state.project?.analysis?.transcript?.segments;
  const matches = Array.isArray(rows) ? rows.filter((row, index) => row && typeof row === "object"
    && String(Object.hasOwn(row, "id") ? row.id : index) === String(buffer.id)) : [];
  const provenance = transcriptBufferProvenance();
  const verified = provenance !== null && typeof buffer.provenance === "string" && buffer.provenance === provenance;
  const current = verified && matches.length === 1 ? matches[0] : null;
  const same = current && current.start === buffer.start && current.end === buffer.end;
  if (!state.transcriptReviewBuffers?.has(buffer) && same && current.text === buffer.base) return null;
  return retainedDraftViews([buffer], state.project, { provenanceVerified: verified })[0];
}

function selectedTranscriptRecoveryDraft() {
  const selected = state.transcriptRecoveryActive;
  if (selected?.projectId !== state.project?.id) return null;
  const buffer = state.transcriptBuffers.get(selected.key);
  return buffer && transcriptDraftReview(buffer) ? buffer : null;
}

function selectTranscriptRecoveryDraft(key) {
  const buffer = state.transcriptBuffers.get(key);
  if (state.transcriptSaving || !transcriptDraftReview(buffer)) return false;
  state.transcriptRecoveryActive = { projectId: state.project.id, key };
  renderTranscriptDetail(); renderManualControls();
  return true;
}

function transcriptBatchStatus(owner = transcriptBatchOwner()) {
  const snapshot = owner?.protocol?.snapshot();
  if (owner?.loading) return "Loading the newer version. Every retained draft will remain available for copying or Discard.";
  if (snapshot?.pending) return snapshot.status === "submitting"
    ? `Saving ${owner.captured.length} lines together...` : "Checking saved changes. No save is being repeated.";
  if (snapshot?.canCheck) return `${owner.loadFailed ? owner.notice : snapshot.issue} Text is temporarily held until this save is resolved; you can still copy it.`;
  return owner?.notice || "";
}

function ownTranscriptBatchFocus(node, current) {
  if (!node || document.activeElement !== node) return () => {};
  let moved = false;
  const cancel = () => { moved = true; };
  const focus = event => { if (event.target !== node && event.target !== document.body) moved = true; };
  for (const type of ["pointerdown", "keydown", "wheel"]) document.addEventListener(type, cancel, true);
  document.addEventListener("focusin", focus, true); window.addEventListener("blur", cancel);
  return () => requestAnimationFrame(() => {
    for (const type of ["pointerdown", "keydown", "wheel"]) document.removeEventListener(type, cancel, true);
    document.removeEventListener("focusin", focus, true); window.removeEventListener("blur", cancel);
    if (moved || !current() || document.activeElement !== document.body) return;
    const target = !node.disabled && !node.hidden ? node : elements.transcriptEditText;
    if (target?.isConnected !== false && target && !target.disabled && !target.hidden
      && (!target.getClientRects || target.getClientRects().length)) target.focus({ preventScroll: true });
  });
}

function acceptTranscriptBatch(owner, response, outcome) {
  const project = response?.project;
  owner.notice = outcome === "unchanged" ? "The saved text was already the same. No Undo step was added."
    : outcome === "saved-now" ? "These changes are saved now. No additional save was sent."
    : `Saved ${owner.captured.length} lines together. One Undo restores them.`;
  const newer = state.project?.id === owner.projectId && Number(state.project.revision) > project.revision;
  if (!newer) {
    for (const key of matchingCapturedBuffers(owner.captured, state.transcriptBuffers)) state.transcriptBuffers.delete(key);
  } else {
    for (const item of owner.captured) if (state.transcriptBuffers.get(item.key) === item.identity)
      state.transcriptReviewBuffers.add(item.identity);
    owner.notice = "The batch was saved, but a newer version is already open. Retained text is review-only; copy or Discard it.";
  }
  rememberProjectRevision(project);
  const operation = owner.operation || owner;
  const direct = verifyPublicBatch(owner.before, owner.plan, response, { captionPreviewIssue });
  if (["changed", "unchanged"].includes(direct.outcome) && state.project === operation.project
    && state.projectViewToken === operation.viewToken && JSON.stringify(state.project) === operation.raw && !explicitPendingDraft()) {
    state.project = project;
    owner.installedProject = project; owner.installedRaw = JSON.stringify(project);
    if (state.timeline) { state.timeline.project = editorProject(); state.timeline.scheduleDraw?.(); }
    updatePreviewCaption(previewPlaybackTime());
    renderTranscript(); renderManualControls();
  } else if (state.project?.id === owner.projectId) {
    if (state.project.revision < project.revision) {
      owner.savedReload = project.revision;
      owner.notice = "These changes are saved now. Load the newer saved version explicitly; no new save will be sent.";
    }
    renderTranscriptDetail(false);
  }
}

async function runTranscriptBatchOperation(owner, action, focusOwner = null) {
  if (!owner || state.transcriptSaving || owner.loading) return false;
  const projectId = state.project?.id, viewToken = state.projectViewToken, pane = layerGroupDuplicateContext();
  const selected = JSON.stringify([state.transcriptActive, state.transcriptRecoveryActive]);
  const operation = { project: state.project, viewToken, raw: JSON.stringify(state.project) };
  owner.operation = operation; owner.installedProject = null; owner.installedRaw = null;
  const current = () => state.project?.id === projectId && state.projectViewToken === viewToken
    && layerGroupDuplicateContext() === pane && JSON.stringify([state.transcriptActive, state.transcriptRecoveryActive]) === selected
    && !explicitPendingDraft() && (state.project === operation.project && JSON.stringify(state.project) === operation.raw
      || state.project === owner.installedProject && JSON.stringify(state.project) === owner.installedRaw);
  const finishFocus = ownTranscriptBatchFocus(focusOwner, current);
  state.transcriptSaving = true;
  try {
    renderTranscriptDetail(false); renderReadiness();
    return await owner.protocol[action]();
  } finally {
    state.transcriptSaving = false;
    if (state.project?.id === projectId) { renderTranscriptDetail(); renderReadiness(); }
    finishFocus();
  }
}

async function saveTranscriptBatch({ focusOwner = null } = {}) {
  if (transcriptBatchIssue()) {
    const message = transcriptBatchIssue(); toast(message);
    revealPendingSave({ target: "transcript", detail: message }); return false;
  }
  const buffers = pendingTranscriptBuffers();
  if (!buffers.length) return true;
  if (!state.project?.draft) { toast("Open a saved edit before correcting transcript captions."); return false; }
  const issue = transcriptBatchOtherIssue();
  if (issue) { toast(issue); return false; }
  const retained = buffers.find(buffer => transcriptDraftReview(buffer));
  if (retained) {
    selectTranscriptRecoveryDraft(`${retained.projectId}:${retained.id}`);
    toast("Copy or Discard every retained draft before saving a new reviewed batch."); return false;
  }
  let plan;
  try {
    plan = planPublicBatch(state.project, buffers.map(item => ({ segment_id: String(item.id), base_text: item.base,
      start: item.start, end: item.end, text: item.text })));
  } catch (error) { toast(error.message); return false; }
  const project = state.project, viewToken = state.projectViewToken;
  const owner = { project, projectId: project.id, viewToken, before: plan.before, plan,
    raw: JSON.stringify(project), captured: captureTranscriptBuffers(buffers), notice: "", loading: false, protocol: null };
  const bufferCurrent = () => owner.captured.length === matchingCapturedBuffers(owner.captured, state.transcriptBuffers).length;
  const admission = () => transcriptBatchOwner(owner.projectId) === owner && state.project === owner.operation?.project
    && state.projectViewToken === owner.operation?.viewToken && JSON.stringify(state.project) === owner.raw && bufferCurrent()
    && !transcriptBatchOtherIssue(owner);
  owner.protocol = createBatchProtocol({ binding: plan.binding,
    post: (projectId, body) => api(`/api/projects/${encodeURIComponent(projectId)}/manual/edit`,
      { method: "POST", body, transcriptBatchToken: owner }),
    read: projectId => api(`/api/projects/${encodeURIComponent(projectId)}`),
    verify: (_binding, response) => verifyPublicBatch(owner.before, plan, response, { captionPreviewIssue }),
    classify: (_binding, response) => classifySavedBatch(owner.before, plan, response,
      { captionPreviewIssue, minimumRevision: state.project?.id === owner.projectId ? state.project.revision : owner.before.revision }),
    unchanged: bufferCurrent,
    admit: () => {
      if (!admission()) return false;
      if (plan.changed.length) { pauseAllMedia(); updatePreviewCaption(previewPlaybackTime()); }
      return admission();
    },
    accepted: (response, outcome) => acceptTranscriptBatch(owner, response, outcome),
    changed: () => { if (state.project?.id === owner.projectId) { renderTranscriptDetail(false); renderProjectSaveState(); } },
  });
  // Reserve the project owner before any reentrant render/await can submit twice.
  state.transcriptBatches.set(owner.projectId, owner);
  return runTranscriptBatchOperation(owner, "submit", focusOwner);
}

async function loadNewerTranscriptVersion(owner, { focusOwner = null } = {}) {
  if (transcriptBatchOwner() !== owner || (!owner.protocol.snapshot().canLoadNewer && !owner.savedReload) || state.transcriptSaving) return false;
  const issue = transcriptBatchOtherIssue(owner);
  if (issue) { toast(issue); return false; }
  const project = state.project, viewToken = state.projectViewToken, raw = JSON.stringify(project);
  const pane = layerGroupDuplicateContext(), selected = JSON.stringify([state.transcriptActive, state.transcriptRecoveryActive]);
  let cursor = null;
  const minimumRevision = Math.max(project.revision, owner.savedReload || owner.protocol.snapshot().reviewRevision);
  let moved = false;
  let focusScheduled = false;
  const cancel = () => { moved = true; };
  const focus = event => { if (event.target !== focusOwner && event.target !== document.body) moved = true; };
  const cleanup = () => {
    for (const type of ["pointerdown", "keydown", "wheel"]) document.removeEventListener(type, cancel, true);
    document.removeEventListener("focusin", focus, true); window.removeEventListener("blur", cancel);
  };
  for (const type of ["pointerdown", "keydown", "wheel"]) document.addEventListener(type, cancel, true);
  document.addEventListener("focusin", focus, true); window.addEventListener("blur", cancel);
  const current = () => !moved && state.project === project && state.projectViewToken === viewToken
    && JSON.stringify(project) === raw && transcriptBatchOwner() === owner && layerGroupDuplicateContext() === pane
    && JSON.stringify([state.transcriptActive, state.transcriptRecoveryActive]) === selected
    && (cursor === null || Object.is(previewPlaybackTime(), cursor));
  owner.loading = true; state.transcriptSaving = true;
  try {
    renderTranscriptDetail(false); renderReadiness();
    if (!current() || transcriptBatchOtherIssue(owner)) return false;
    pauseAllMedia(); cursor = previewPlaybackTime();
    if (!current() || transcriptBatchOtherIssue(owner)) return false;
    const response = await api(`/api/projects/${encodeURIComponent(owner.projectId)}`);
    const assessed = classifySavedBatch(owner.before, owner.plan, response, { captionPreviewIssue, minimumRevision });
    const valid = assessed.reviewable === true || assessed.outcome === "saved-now";
    if (!valid || response?.project?.revision < minimumRevision) throw new Error("The newer saved version could not be verified. Your drafts are retained; Check saved changes again.");
    if (!current() || transcriptBatchOtherIssue(owner)) return false;
    // Preserve all current buffer objects, including newer typing, before any
    // transcript/analysis identity is replaced. No partial cleanup or rebase.
    const next = response.project;
    for (const buffer of pendingTranscriptBuffers()) state.transcriptReviewBuffers.add(buffer);
    state.project = next; const loadedView = ++state.projectViewToken;
    state.transcriptRecoveryActive = null;
    rememberProjectRevision(next); hydrateProject();
    const installed = () => state.project === next && state.projectViewToken === loadedView && transcriptBatchOwner(next.id) === owner;
    if (!installed()) return false;
    if (!owner.savedReload) owner.protocol.acceptNewerLoad(next);
    if (!installed()) return false;
    owner.savedReload = null; owner.loadFailed = false;
    const retained = pendingTranscriptBuffers()[0];
    if (retained) state.transcriptRecoveryActive = { projectId: next.id, key: `${next.id}:${retained.id}` };
    owner.notice = "The newer version is loaded. Copy retained drafts, Discard them, then explicitly edit the current saved lines.";
    renderTranscript();
    if (focusOwner && !moved && installed()) {
      focusScheduled = true;
      requestAnimationFrame(() => {
        try {
          if (moved || state.project !== next || state.projectViewToken !== loadedView || document.activeElement !== document.body) return;
          const textarea = elements.transcriptEditText;
          const target = !textarea.disabled && textarea.getClientRects().length ? textarea : elements.transcriptSearch;
          if (target && !target.disabled && target.isConnected !== false && target.getClientRects().length) target.focus({ preventScroll: true });
        } finally { cleanup(); }
      });
    }
    return true;
  } catch (error) {
    owner.notice = owner.savedReload ? "The newer saved version could not be loaded. Your text is retained; retry Load newer version when ready." : error.message;
    owner.loadFailed = true;
    if (state.project?.id === owner.projectId) toast(error.message);
    return false;
  } finally {
    owner.loading = false; state.transcriptSaving = false;
    if (!focusScheduled) cleanup();
    if (state.project?.id === owner.projectId) { renderTranscriptDetail(); renderReadiness(); }
  }
}

async function activateTranscriptSaveAll({ focusOwner = null } = {}) {
  const owner = transcriptBatchOwner(), snapshot = owner?.protocol?.snapshot();
  if (owner?.loading || snapshot?.pending || state.transcriptSaving) return false;
  if (owner?.savedReload || snapshot?.canLoadNewer && !owner.loadFailed) return loadNewerTranscriptVersion(owner, { focusOwner });
  if (snapshot?.canRetry) return runTranscriptBatchOperation(owner, "retrySame", focusOwner);
  if (snapshot?.canCheck) { owner.loadFailed = false; return runTranscriptBatchOperation(owner, "check", focusOwner); }
  return saveTranscriptBatch({ focusOwner });
}

function renderTranscriptRecoveryRows() {
  let count = 0;
  for (const buffer of pendingTranscriptBuffers()) {
    const view = transcriptDraftReview(buffer); if (!view) continue;
    count++;
    const row = document.createElement("div"); row.className = "transcript-row transcript-retained-draft";
    row.dataset.retainedDraft = view.key;
    const button = document.createElement("button"); button.type = "button"; button.className = "transcript-seek";
    const time = document.createElement("time"), text = document.createElement("span"), label = document.createElement("b");
    time.textContent = "Draft"; text.className = "transcript-text";
    text.textContent = `Retained draft ${String(buffer.id)}: ${buffer.text}`; text.setAttribute("dir", "auto");
    label.textContent = "Review only"; button.append(time, text, label);
    button.title = view.kind === "orphan" ? "Original line no longer available or its provenance cannot be verified. Copy or Discard only."
      : "Draft retained from an earlier saved version. Copy or Discard before editing the current saved line.";
    button.setAttribute("aria-label", `${button.title} ${buffer.text}`);
    button.addEventListener("click", () => selectTranscriptRecoveryDraft(view.key));
    row.append(button); elements.transcriptList.append(row);
  }
  return count;
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
  if(state.transcriptBatches?.size && transcriptBatchIssue()){toast(transcriptBatchIssue());revealPendingSave({target:"transcript"});return false;}
  if (state.captionDirty && selectedCaptionItem()) {
    toast("Save or discard your caption changes before rebuilding or exporting.");
    openStudioTab("transcript");
    return false;
  }
  if (!pendingTranscriptBuffers().length) return true;
  toast("Save or discard your transcript changes before rebuilding or exporting.");
  openStudioTab("transcript");
  return false;
}

function selectedTranscriptSegment() {
  if (selectedTranscriptRecoveryDraft()) return null;
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
  const buffer = state.transcriptBuffers.get(transcriptBufferKey(segment.id));
  if (transcriptDraftReview(buffer)) { selectTranscriptRecoveryDraft(transcriptBufferKey(segment.id)); return; }
  state.transcriptRecoveryActive = null;
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
  if (!segment || state.transcriptSaving || transcriptBatchIssue()) return;
  const key = transcriptBufferKey(segment.id);
  if (transcriptDraftReview(state.transcriptBuffers.get(key))) return;
  const previous = state.transcriptBuffers.get(key);
  const text = elements.transcriptEditText.value;
  if (text === String(segment.text || "")) state.transcriptBuffers.delete(key);
  else state.transcriptBuffers.set(key, { projectId: state.project.id, id: segment.id, base: previous?.base ?? String(segment.text || ""), text, start: Number(segment.start), end: Number(segment.end), provenance: previous?.provenance ?? transcriptBufferProvenance() });
  renderTranscriptDetail(false);
}

function discardTranscriptBuffer() {
  if (state.transcriptSaving || transcriptBatchIssue()) return;
  const retained = selectedTranscriptRecoveryDraft();
  if (retained) {
    if (state.transcriptSaving) return;
    state.transcriptBuffers.delete(`${retained.projectId}:${retained.id}`);
    state.transcriptRecoveryActive = null;
    renderTranscript(); renderManualControls(); return;
  }
  const segment = selectedTranscriptSegment();
  if (!segment || state.transcriptSaving) return;
  state.transcriptBuffers.delete(transcriptBufferKey(segment.id));
  renderTranscriptDetail();
}

async function saveTranscriptBuffers(all = true) {
  if (all) return saveTranscriptBatch();
  if (transcriptBatchIssue() || selectedTranscriptRecoveryDraft()) return false;
  const segment = selectedTranscriptSegment();
  const buffers = pendingTranscriptBuffers().filter((item) => all || String(item.id) === String(segment?.id));
  if (!buffers.length) return true;
  if (buffers.some(item => transcriptDraftReview(item))) return false;
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
  renderProjectSaveState();
  state.transcriptSectionsUI && renderTranscriptSections();
  if (!elements.transcriptEditForm) return;
  const segment = selectedTranscriptSegment(), retained = selectedTranscriptRecoveryDraft();
  const owner = transcriptBatchOwner(), snapshot = owner?.protocol?.snapshot();
  const needsLoad = Boolean(owner?.savedReload && state.project?.revision < owner.savedReload);
  const recovery = Boolean(owner?.loading || snapshot?.pending || snapshot?.canCheck || needsLoad);
  const visible = Boolean(segment || retained || recovery);
  elements.transcriptEditForm.hidden = !visible;
  elements.advancedPanel?.classList.toggle("transcript-editing", visible);
  if (!visible) return;
  const buffer = retained || (segment && state.transcriptBuffers.get(transcriptBufferKey(segment.id)));
  const review = buffer && transcriptDraftReview(buffer);
  // Uncertain immutable batches remain copyable, but cannot be superseded by
  // typing or Discard before Check/Retry/Load resolves their saved outcome.
  const busy = Boolean(state.transcriptSaving || owner?.loading || snapshot?.pending || state.manualEditBusy
    || previewRepairBusy() || projectCopySourceBusy() || state.activeJob || state.activeUploads.size
    || state.mediaStudio?.uploading || state.stabilizationStudio?.uploading
    || state.sourceSyncPending || state.sourceMixerSavePending || state.jobStartLocks.size);
  if (replaceText) elements.transcriptEditText.value = buffer?.text ?? String(segment?.text || "");
  elements.transcriptEditText.disabled = busy || (!segment && !retained);
  elements.transcriptEditText.readOnly = Boolean(review) || recovery;
  elements.transcriptEditTime.textContent = retained
    ? `Retained draft ${String(retained.id)} | original ${retained.start} - ${retained.end}`
    : segment ? transcriptMappingLabel(segment, transcriptTimelineMapping(segment.start, segment.end)) : "Transcript save recovery";
  const quality = state.project?.analysis?.transcript_quality;
  const flagged = !retained && segment && Array.isArray(quality?.review_segments) && quality.review_segments.some(item =>
    item && String(item.segment_id) === String(segment.id));
  let reviewNote = elements.transcriptEditForm.querySelector(".transcript-line-review");
  if (!reviewNote && flagged) {
    reviewNote = document.createElement("p"); reviewNote.className = "transcript-line-review"; reviewNote.id = "transcriptLineReview";
    elements.transcriptEditForm.insertBefore(reviewNote, elements.transcriptEditText);
  }
  if (reviewNote) {
    reviewNote.hidden = !flagged;
    reviewNote.textContent = flagged ? "Original AI confidence was low for this line. Listen and check names or mixed-language words. Saving text does not recheck the audio." : "";
  }
  const buffers = pendingTranscriptBuffers(), count = buffers.length, unresolved = buffers.some(item => transcriptDraftReview(item));
  const status = transcriptBatchStatus(owner);
  elements.transcriptEditStatus.textContent = recovery ? status
    : review ? (review.kind === "orphan" ? "Retained draft: the original line or its provenance cannot be verified. Copy your text, then Discard it and choose a current saved line to edit."
      : "Retained draft from an earlier saved version. Copy your text, Discard it, then edit the current saved line.")
    : count ? `Unsaved | ${count} changed line${count === 1 ? "" : "s"}`
    : status || "Saved | captions updated without rebuilding";
  elements.transcriptSave.disabled = busy || recovery || Boolean(review) || !buffer || !buffer.text.trim();
  elements.transcriptDiscard.disabled = busy || recovery || !buffer;
  elements.transcriptSaveAll.textContent = needsLoad || snapshot?.canLoadNewer && !owner.loadFailed ? "Load newer version"
    : snapshot?.canRetry ? "Retry same save" : snapshot?.canCheck ? "Check saved changes" : "Save all changes";
  elements.transcriptSaveAll.disabled = busy || (!recovery && (!count || unresolved));
  elements.transcriptSaveAll.title = recovery ? status : unresolved ? "Copy or Discard retained drafts before saving a new batch."
    : "Save every reviewed transcript line together in one Undo step.";
  const segments = state.project?.analysis?.transcript?.segments || [], index = segments.indexOf(segment);
  elements.transcriptPrevious.disabled = busy || Boolean(retained) || index <= 0;
  elements.transcriptNext.disabled = busy || Boolean(retained) || index < 0 || index >= segments.length - 1;
}

function moveTranscriptLine(direction) {
  if (selectedTranscriptRecoveryDraft()) return;
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

function transcriptionProvenance(transcript) {
  if (!transcript) return "";
  const execution = transcript.execution || {};
  const parts = value => Number.isSafeInteger(Number(value)) && Number(value) >= 0 ? Number(value) : null;
  const attempt = execution.cloud_attempt;
  const messages = [];
  if (execution.transcription_fallback === "cloudflare_to_cached_local" || attempt?.provider === "cloudflare") {
    const count = parts(attempt?.uploaded_parts);
    messages.push(`Cloudflare was attempted${count == null ? "" : ` (${count} upload attempt${count === 1 ? "" : "s"})`}; this transcript completed with cached local speech. Uploaded audio and possible provider charges were not undone.`);
  } else if (execution.provider === "cloudflare") {
    const count = parts(execution.uploaded_parts);
    messages.push(`Transcribed by Cloudflare${count == null ? "" : ` (${count} upload attempt${count === 1 ? "" : "s"})`}. Audio was sent to the selected provider account; provider retention and billing terms apply.`);
  }
  const model = execution.actual_model || transcript.model;
  const device = execution.actual_device || transcript.device;
  if (execution.actual_transcription_engine === "local" || device === "cpu" || device === "cuda") {
    messages.push(`Local speech model: ${model || "not recorded"}; device: ${device || "not recorded"}.`);
    if (execution.requested_model && execution.requested_model !== model) messages.push(`Requested model: ${execution.requested_model}.`);
    if (["large_model_cuda_headroom", "cuda_headroom"].includes(execution.fallback_reason)) messages.push("GPU memory headroom was insufficient or unverified; local CPU fallback was used.");
    if (["device_error", "worker_stall"].includes(execution.fallback_reason)) messages.push("A local device/runtime failure triggered the recorded fallback.");
    if (execution.resource_warnings?.includes("cpu_memory_unverified")) messages.push("Available CPU memory could not be verified.");
    if (execution.resource_warnings?.includes("large_model_cpu_may_be_slow")) messages.push("Large-model CPU processing can be slow; hardware performance is not certified.");
  }
  return messages.join(" ");
}

function manualTranscriptionView(projectId = state.project?.id, viewToken = state.projectViewToken) {
  return () => state.project?.id === projectId && state.projectViewToken === viewToken;
}

function manualTranscriptionReason(project) {
  if (project?.draft?.engine !== "manual" || project.analysis?.engine !== "manual") return "";
  const selected = String(project.manual?.source_mixer?.audio_slot || project.settings?.audio_source || "A").toUpperCase();
  if (["A", "B"].includes(selected) && !project.sources?.[selected]?.has_audio) return uiCopy("אין שמע במקור שנבחר לתמלול.", "The selected source has no audio to transcribe.");
  if (selected === "B") return uiCopy("תמלול בעריכה ידנית תומך כרגע בשמע ממקור A בלבד.", "Manual transcription currently supports source A audio, not source B.");
  if (project.caption_alternatives?.length || project.manual?.caption_alternative || project.analysis?.review_candidates
      || ["caption_corrections", "caption_overrides", "caption_dormant_overrides"].some(key => Object.keys(project.manual?.[key] || {}).length))
    return uiCopy("יש בפרויקט עבודת כתוביות שמורה. התמלול לא יחליף אותה.", "This edit has saved caption work. Transcription will not replace it.");
  return "";
}

function renderManualTranscription() {
  const panel = document.getElementById("manualTranscription");
  if (!panel) return;
  const project = state.project, transcript = project?.analysis?.transcript;
  panel.hidden = project?.draft?.engine !== "manual" || project?.analysis?.engine !== "manual"
    || !transcript || Boolean(transcript.segments?.length || transcript.words?.length || transcript.text);
  if (panel.hidden) return;
  const language = document.getElementById("manualTranscriptionLanguage");
  const action = document.getElementById("manualTranscriptionStart");
  const status = document.getElementById("manualTranscriptionStatus");
  const owner = `${project.id}:${state.projectViewToken}`;
  if (panel.dataset.owner !== owner) {
    panel.dataset.owner = owner;
    const wanted = project.settings?.spoken_language || "auto";
    language.value = Array.from(language.options).some(option => option.value === wanted) ? wanted : "auto";
  }
  document.getElementById("manualTranscriptionTitle").textContent = uiCopy("תמלול", "Transcribe audio");
  document.getElementById("manualTranscriptionHelp").textContent = uiCopy(
    "תמלול מקומי של השמע ממקור A. העריכה והגדרות הייצוא נשארות כפי שהן.",
    "Create an editable transcript from source A audio. Your timeline and export settings stay as they are.");
  document.getElementById("manualTranscriptionLanguageLabel").textContent = uiCopy("שפת הדיבור", "Spoken language");
  const busy = foregroundBusy(), reason = manualTranscriptionReason(project);
  action.textContent = uiCopy("תמלל מקומית", "Transcribe locally");
  action.disabled = Boolean(reason || busy);
  language.disabled = action.disabled;
  action.onclick = () => startManualTranscription(language.value);
  const notice = state.manualTranscriptionNotice;
  const text = reason || (notice?.owner === owner ? notice.text : "");
  if (status.textContent !== text) status.textContent = text;
}

function setManualTranscriptionNotice(projectId, viewToken, text) {
  if (!manualTranscriptionView(projectId, viewToken)()) return;
  state.manualTranscriptionNotice = { owner: `${projectId}:${viewToken}`, text };
  renderManualTranscription();
}

async function monitorManualTranscription(job, projectId, viewToken) {
  const current = manualTranscriptionView(projectId, viewToken);
  try {
    const completed = await pollJob(job.id, { projectId, kind: "manual_transcript", silent: true });
    if (!current()) return;
    if (completed.result?.reason === "no_speech") {
      setManualTranscriptionNotice(projectId, viewToken, uiCopy("לא זוהה דיבור. העריכה לא השתנתה.", "No speech was detected. Your edit was not changed."));
      return;
    }
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
    if (!current()) return;
    if (completed.result?.saved !== true || !Number.isSafeInteger(completed.result.revision) || payload.project?.id !== projectId
        || payload.project.revision < completed.result.revision || !payload.project.analysis?.transcript?.segments?.length)
      throw new Error(uiCopy("לא ניתן לאמת את שמירת התמלול. יש לפתוח מחדש את הפרויקט.", "Could not verify the saved transcript. Reopen this project to check."));
    const panel = document.getElementById("manualTranscription");
    const returnFocus = panel?.contains(document.activeElement);
    state.project = reconcileProjectSnapshot(payload.project);
    rememberProjectRevision(state.project);
    if (state.timeline) { state.timeline.project = editorProject(); state.timeline.scheduleDraw?.(); }
    renderTranscript();
    renderCaptionControls();
    renderCaptionInspector();
    updatePreviewCaption(previewPlaybackTime());
    const section = document.getElementById("transcriptSection");
    if (section && returnFocus) { section.open = true; section.querySelector("summary")?.focus({ preventScroll: true }); }
    toast(uiCopy("התמלול המקומי מוכן לעריכה.", "Local transcript ready to edit."), "success");
  } catch (error) {
    if (!current()) return;
    const message = error.message === "Cancelled"
      ? uiCopy("התמלול בוטל. העריכה נשמרה.", "Transcription cancelled. The edit was kept.")
      : error.message;
    setManualTranscriptionNotice(projectId, viewToken, message);
  }
}

async function startManualTranscription(language) {
  const projectId = state.project?.id, viewToken = state.projectViewToken;
  const current = manualTranscriptionView(projectId, viewToken);
  const hasPendingText = () => state.captionDirty || state.transcriptSaving
    || [...state.transcriptBuffers.values()].some(row => row.projectId === projectId);
  if (!projectId || foregroundBusy() || state.manualEditBusy || state.project.draft?.engine !== "manual" || manualTranscriptionReason(state.project)) return;
  if (hasPendingText()) {
    setManualTranscriptionNotice(projectId, viewToken, uiCopy("יש לשמור או לבטל שינויי טקסט לפני התמלול.", "Save or discard pending text changes before transcribing."));
    return;
  }
  if (!(await flushCurrentProjectSaves()) || !current() || hasPendingText()) return;
  const lock = acquireJobStartLock("manual_transcript", projectId);
  if (!lock) return;
  try {
    assertJobStartNotCancelled();
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/manual-transcript`, {
      method: "POST", body: JSON.stringify({ language, expected_revision: state.project.revision }),
    });
    if (!current()) return;
    if (payload.job?.kind !== "manual_transcript" || !payload.job.id) throw new Error("No local transcription job was confirmed.");
    setManualTranscriptionNotice(projectId, viewToken, uiCopy("מתמללים מקומית…", "Transcribing locally…"));
    await monitorManualTranscription(payload.job, projectId, viewToken);
  } catch (error) {
    setManualTranscriptionNotice(projectId, viewToken, error.message);
  } finally { releaseJobStartLock(lock); }
}

function renderTranscript() {
  if (!elements.transcriptList) return;
  state.manualTranscriptionControls?.();
  if (!state.captionAlternativesUI && document.getElementById("captionAlternatives")) {
    state.captionAlternativesUI = new CaptionAlternatives({
      root: document.getElementById("captionAlternatives"), getProject: () => state.project,
      getSelection: () => state.manualSelection ? {...state.manualSelection} : null,
      copy: uiCopy, api, formatTime, sourceUrl: sourceMediaUrl,
      beforeReview: async () => {
        if (foregroundBusy() || state.manualEditBusy || state.transcriptSaving) throw new Error(uiCopy("יש להמתין לסיום הפעולה הנוכחית.", "Wait for the current operation to finish."));
        if (state.captionDirty || [...state.transcriptBuffers.values()].some(row => row.projectId === state.project?.id)) throw new Error(uiCopy("יש לשמור או לבטל שינויי טקסט לפני סקירת גרסה.", "Save or discard pending text changes before reviewing another version."));
        return flushCurrentProjectSaves();
      },
      acceptProject: project => { state.project = project; rememberProjectRevision(project); renderTranscript(); },
      apply: (proposal, isCurrent) => applyManualEdit("caption_alternative", {
        alternative_id: proposal.id, review_fingerprint: proposal.review_fingerprint,
      }, {isCurrent}),
    });
  }
  state.captionAlternativesUI?.render();
  const query = elements.transcriptSearch.value.trim().toLowerCase();
  const transcript = state.project?.analysis?.transcript;
  const provenance = document.getElementById("transcriptionProvenance");
  if (provenance) {
    provenance.textContent = transcriptionProvenance(transcript);
    provenance.hidden = !provenance.textContent;
  }
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
  const retainedCount = renderTranscriptRecoveryRows();
  elements.transcriptList.scrollTop = previousScroll;
  if (elements.transcriptResults) elements.transcriptResults.textContent = `${visible} of ${segments.length} lines${retainedCount ? ` | ${retainedCount} retained draft${retainedCount === 1 ? "" : "s"}` : ""}`;
  highlightTranscriptSelection();
  renderTranscriptDetail();
}

function rangeMostlyRemoved(start, end) {
  const duration = Number(end) - Number(start);
  const removed = (state.project?.draft?.cuts || []).reduce((sum, range) => sum + Math.max(0, Math.min(Number(end), Number(range.end)) - Math.max(Number(start), Number(range.start))), 0);
  return duration > 0 && removed >= duration * .5;
}

const projectLibrary = { initialized: false, listRequest: 0, rename: null, deletion: null, copy: null, lastCopyBusy: false };

function initProjectLibrary() {
  if (projectLibrary.initialized) return;
  const ids = ["projectCopyDialog","projectCopyForm","projectCopyName","projectCopySource","projectCopyProgress","projectCopyStatus","projectCopyError","projectCopyNavigation","projectCopyCreate","projectCopyCancel","projectCopyCheck","projectCopyRetry","projectCopyOpen","projectCopyBack","cancelProjectCopy","closeProjectCopy",
    "closeProjectsDialog", "projectSearch", "projectSort", "projectLibrarySummary",
    "projectRenameDialog", "projectRenameForm", "projectRenameInput", "projectRenameError", "closeProjectRename", "cancelProjectRename", "saveProjectRename",
    "projectDeleteDialog", "projectDeleteName", "projectDeleteError", "closeProjectDelete", "cancelProjectDelete", "confirmProjectDelete"];
  for (const id of ids) elements[id] = document.getElementById(id);
  if (!elements.projectRenameDialog || !elements.projectDeleteDialog) return;
  projectLibrary.initialized = true;
  initializeProjectCopies();bindProjectCopyDialog();
  elements.closeProjectsDialog.addEventListener("click", () => elements.projectsDialog.close());
  elements.projectSearch.addEventListener("input", renderProjectDialog);
  elements.projectSort.addEventListener("change", renderProjectDialog);
  elements.projectRenameForm.addEventListener("submit", (event) => { event.preventDefault(); runUiAction(saveProjectName); });
  elements.confirmProjectDelete.addEventListener("click", () => runUiAction(confirmProjectDeletion));
  for (const [kind, dialog, closeIds] of [
    ["rename", elements.projectRenameDialog, ["closeProjectRename", "cancelProjectRename"]],
    ["deletion", elements.projectDeleteDialog, ["closeProjectDelete", "cancelProjectDelete"]],
  ]) {
    for (const id of closeIds) elements[id].addEventListener("click", () => { if (!projectLibrary[kind]?.pending) dialog.close(); });
    dialog.addEventListener("cancel", (event) => { if (projectLibrary[kind]?.pending) event.preventDefault(); });
    dialog.addEventListener("close", () => {
      const action = projectLibrary[kind];
      projectLibrary[kind] = null;
      if (action) restoreProjectLibraryFocus(action.origin);
    });
  }
}

function projectLibraryFocus() {
  const focused = document.activeElement;
  const row = focused?.closest?.("[data-project-id]");
  if (!row) return null;
  return { id: row.dataset.projectId, action: focused.dataset.projectAction || "open", inDialog: Boolean(row.closest("#dialogProjects")) };
}

function restoreProjectLibraryFocus(origin) {
  if (!origin || elements.projectRenameDialog?.open || elements.projectDeleteDialog?.open || elements.projectCopyDialog?.open) return;
  const container = origin.inDialog ? elements.dialogProjects : elements.recentList;
  if (origin.inDialog && !elements.projectsDialog.open) return;
  if (!origin.inDialog && elements.welcomeView.hidden) return;
  const row = [...container.children].find((item) => item.dataset.projectId === origin.id);
  const control = row?.querySelector(`[data-project-action="${origin.action}"]`);
  const target=control || container.querySelector('[data-project-action="open"]') || (origin.inDialog ? elements.projectSearch : elements.projectsButton);
  const local=state.editingPositions,owner=local?.loading;
  // A library refresh may replace and refocus the very Open action we are awaiting.
  // This synchronous focus repair is not a newer user intent; no other focus is exempt.
  const owned=Boolean(target && target===control && origin.action==="open" && owner?.returnPosition
    && owner.projectId===origin.id && owner.epoch===local.epoch);
  const prior=local?.libraryFocus;
  if(owned)local.libraryFocus={owner,target,projectId:origin.id};
  try{target?.focus();}finally{if(owned)local.libraryFocus=prior;}
}

function projectLibraryBusy(projectId) {
  return copyOperationActive(state.projectCopies?.forSource?.(projectId)) || projectHasForegroundWork(projectId) || (state.project?.id === projectId && Boolean(state.mediaStudio?.uploading || state.stabilizationStudio?.uploading || state.manualEditBusy || state.transcriptSaving));
}

function projectLibraryRows(query = "", order = "recent") {
  const needle = String(query).trim().toLocaleLowerCase("en");
  const rows = state.projects.filter((project) => projectLabel(project).toLocaleLowerCase("en").includes(needle));
  return rows.sort((a, b) => order === "name"
    ? String(a.name || "").localeCompare(String(b.name || ""), "en", { numeric: true, sensitivity: "base" })
    : String(order === "oldest" ? a.created_at || a.updated_at || "" : b.updated_at || "")
      .localeCompare(String(order === "oldest" ? b.created_at || b.updated_at || "" : a.updated_at || "")));
}

// List summaries identify retained data, not whether recovery validation will pass.
function projectLibraryStateLabel(project) {
  return project.has_draft ? "Edit ready" : project.has_retained_edit ? "Saved timeline · Resume required"
    : project.workflow === "manual" ? "Empty timeline" : "In setup";
}

function projectLibraryDuration(project) {
  if (project.has_retained_edit && !project.has_draft) {
    const duration = project.retained_duration;
    return typeof duration === "number" && Number.isFinite(duration) && duration >= 0 && duration <= 86400 ? duration : null;
  }
  const duration = Number(project.sources?.A?.duration);
  return Number.isFinite(duration) && duration > 0 ? duration : null;
}

function projectLibraryCard(project, inDialog = false) {
  const row = document.createElement(inDialog ? "div" : "article");
  row.className = inDialog ? "dialog-project-row" : "recent-project-card";
  row.dataset.projectId = project.id;
  row.classList.toggle("is-current", state.project?.id === project.id);
  const button = document.createElement("button");
  button.className = inDialog ? "dialog-project" : "recent-project";
  button.type = "button";
  button.dataset.projectAction = "open";
  button.setAttribute("aria-label", `Open project: ${projectLabel(project)}`);
  button.innerHTML = `<span><strong dir="auto"></strong><small></small></span><b class="project-open-label">Open editor</b>`;
  $("strong", button).textContent = projectLabel(project);
  $("small", button).textContent = `${projectLibraryStateLabel(project)} · ${formatDate(project.updated_at)}`;
  if (!inDialog) decorateHomeProject(button, project);
  if (state.project?.id === project.id) {
    const current = document.createElement("small");
    current.className = "project-current-label";
    current.textContent = "Current project";
    $("span", button).append(current);
  }
  if (inDialog) button.addEventListener("click", () => runUiAction(async () => {
    // A save failure keeps the library available instead of dismissing it.
    const opened = await openProject(project.id,{returnPosition:true});
    if (opened) elements.projectsDialog.close();
  }));
  else button.addEventListener("click", () => runUiAction(() => openProject(project.id,{returnPosition:true})));
  const actions = document.createElement("div");
  actions.className = "project-card-actions";
  const rename = document.createElement("button");
  rename.className = "project-rename button ghost compact";
  rename.type = "button";
  rename.dataset.projectAction = "rename";
  rename.textContent = "Rename";
  rename.setAttribute("aria-label", `Rename project: ${projectLabel(project)}`);
  rename.addEventListener("click", () => openProjectRename(project));
  const remove = document.createElement("button");
  remove.className = "project-delete dialog-project-delete button ghost compact";
  remove.type = "button";
  remove.dataset.projectAction = "delete";
  remove.textContent = "Delete";
  remove.setAttribute("aria-label", `Delete project: ${projectLabel(project)}`);
  remove.addEventListener("click", () => runUiAction(() => deleteProject(project)));
  const copy=document.createElement("button");
  copy.className="project-copy button ghost compact";copy.type="button";copy.dataset.projectAction="copy";
  copy.textContent=projectCopyLatestForSource(project.id) ? "Copy details" : "Save a copy";
  copy.setAttribute("aria-label",`Save an independent copy of project: ${projectLabel(project)}`);
  copy.addEventListener("click",()=>openProjectCopy(project));
  const copying=projectCopyForSource(project.id);
  for(const control of [rename,remove]){control.disabled=Boolean(copying);if(copying)control.title="Finish or cancel this project copy before changing its source.";}
  const copyDetail=projectCopyMetadata(project);
  if(copyDetail)$("small",button).textContent+=` | ${copyDetail}`;
  actions.append(copy, rename, remove);
  row.append(button, actions);
  return row;
}

// Projects that kept the default name show their draft title or recording.
function projectLabel(project) {
  return String(project?.display_name || project?.name || "Untitled project");
}

// Home library rows follow the studio design: a source frame, the kind of edit
// and its length. The whole row still opens the project.
const PROJECT_KINDS = { manual: "Manual edit", youtube: "YouTube", short: "Short / Reel" };
function decorateHomeProject(button, project) {
  if (typeof button.prepend !== "function" || typeof button.insertBefore !== "function") return;
  const thumb = document.createElement("span");
  thumb.className = "project-thumb";
  thumb.setAttribute("aria-hidden", "true");
  if (project.thumbnail_url) {
    const image = document.createElement("img");
    image.src = project.thumbnail_url; image.alt = ""; image.loading = "lazy"; image.decoding = "async";
    thumb.append(image);
  }
  const kind = document.createElement("span");
  kind.className = "project-kind";
  kind.dataset.kind = project.workflow || "manual";
  kind.textContent = PROJECT_KINDS[project.workflow] || "Edit";
  const length = document.createElement("span");
  length.className = "project-length";
  const duration = projectLibraryDuration(project);
  length.textContent = duration == null ? "--:--" : formatTime(duration);
  button.prepend(thumb);
  button.insertBefore(kind, $(".project-open-label", button));
  button.insertBefore(length, $(".project-open-label", button));
}

function renderRecentProjects() {
  initProjectLibrary();
  const focus = projectLibraryFocus();
  elements.recentList.innerHTML = "";
  const projects = projectLibraryRows().slice(0, 6);
  elements.recentProjects.hidden = projects.length === 0;
  elements.recentCount.textContent = String(state.projects.length);
  for (const project of projects) elements.recentList.append(projectLibraryCard(project));
  if (focus && !focus.inDialog) restoreProjectLibraryFocus(focus);
}

function openProjectsDialog() {
  initProjectLibrary();
  renderProjectDialog();
  if (!elements.projectsDialog.open) elements.projectsDialog.showModal();
  loadProjects().catch((error) => toast(`Could not refresh projects: ${error.message}`));
}

function renderProjectDialog() {
  if (!elements.dialogProjects) return;
  initProjectLibrary();
  const focus = projectLibraryFocus();
  elements.dialogProjects.innerHTML = "";
  const projects = projectLibraryRows(elements.projectSearch?.value, elements.projectSort?.value);
  if (elements.projectLibrarySummary) elements.projectLibrarySummary.textContent = projects.length === state.projects.length
    ? `${projects.length} project${projects.length === 1 ? "" : "s"}` : `${projects.length} of ${state.projects.length} projects`;
  if (!projects.length) {
    const empty = document.createElement("p");
    empty.className = "project-library-empty";
    empty.textContent = state.projects.length ? "No matching projects. Try another name or clear the search." : "Your projects will appear here. Create a project to get started.";
    elements.dialogProjects.append(empty);
  }
  for (const project of projects) elements.dialogProjects.append(projectLibraryCard(project, true));
  if (focus?.inDialog) restoreProjectLibraryFocus(focus);
}

function setProjectActionError(kind, message = "") {
  const node = kind === "rename" ? elements.projectRenameError : elements.projectDeleteError;
  node.textContent = message;
  node.hidden = !message;
}

function setProjectActionPending(kind, pending) {
  if (projectLibrary[kind]) projectLibrary[kind].pending = pending;
  const controls = kind === "rename" ? ["projectRenameInput", "saveProjectRename", "cancelProjectRename", "closeProjectRename"]
    : ["confirmProjectDelete", "cancelProjectDelete", "closeProjectDelete"];
  for (const id of controls) elements[id].disabled = pending;
  const button = kind === "rename" ? elements.saveProjectRename : elements.confirmProjectDelete;
  button.textContent = kind === "rename" ? pending ? "Saving…" : "Save name" : pending ? "Deleting…" : "Delete project permanently";
}

function openProjectRename(project) {
  if (!project?.id) return;
  initProjectLibrary();
  if (projectLibraryBusy(project.id)) { toast("Wait for this project's import or active job before renaming it."); return; }
  projectLibrary.rename = { project, origin: projectLibraryFocus(), pending: false };
  elements.projectRenameInput.value = projectLabel(state.project?.id === project.id ? state.project : project);
  setProjectActionError("rename");
  setProjectActionPending("rename", false);
  elements.projectRenameDialog.showModal();
  elements.projectRenameInput.focus();
  elements.projectRenameInput.select();
}

async function saveProjectName() {
  const action = projectLibrary.rename;
  if (!action || action.pending) return;
  const projectId = action.project.id;
  const name = elements.projectRenameInput.value.trim();
  if (!name || name.length > 120) { setProjectActionError("rename", "Enter a project name between 1 and 120 characters."); elements.projectRenameInput.focus(); return; }
  setProjectActionError("rename");
  setProjectActionPending("rename", true);
  try {
    if (projectLibraryBusy(projectId)) throw new Error("Wait for this project's import or active job, then try again.");
    if (state.project?.id === projectId && !(await flushCurrentProjectSaves())) throw new Error("Your current edit could not be saved. Resolve the save error, then try again.");
    await flushProjectSaves(projectId);
    const [latest, work] = await Promise.all([
      api(`/api/projects/${encodeURIComponent(projectId)}`),
      api(`/api/projects/${encodeURIComponent(projectId)}/jobs/active`),
    ]);
    if (work.jobs?.length || projectLibraryBusy(projectId)) throw new Error("This project has active work. Wait for it to finish, then try again.");
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}`, { method: "PATCH", body: JSON.stringify({ name, expected_revision: latest.project.revision }) });
    const saved = payload.project;
    rememberProjectRevision(saved);
    if (state.project?.id === projectId) {
      state.project = reconcileProjectSnapshot(saved);
      elements.projectName.value = state.project.name;
      setSaveState(projectId, t("saved"));
    }
    // Invalidate older list requests so a late response cannot undo this name.
    projectLibrary.listRequest += 1;
    state.projects = state.projects.map((project) => project.id === projectId ? { ...project, name: saved.name, updated_at: saved.updated_at } : project);
    renderRecentProjects();
    renderProjectDialog();
    elements.projectRenameDialog.close();
    toast("Project renamed", "success");
  } catch (error) {
    setProjectActionError("rename", isRevisionConflict(error)
      ? "This project changed while you were renaming it. Your name is kept; select Save name to try again."
      : error.message || "The project could not be renamed. Try again.");
  } finally { setProjectActionPending("rename", false); }
}

async function deleteProject(project) {
  if (!project?.id) return;
  initProjectLibrary();
  if (projectLibraryBusy(project.id)) {
    toast("Wait for this project's import or active job before deleting it.");
    return;
  }
  projectLibrary.deletion = { project, origin: projectLibraryFocus(), pending: false };
  elements.projectDeleteName.textContent = projectLabel(state.project?.id === project.id ? state.project : project);
  setProjectActionError("deletion");
  setProjectActionPending("deletion", false);
  elements.projectDeleteDialog.showModal();
  elements.cancelProjectDelete.focus();
}

async function confirmProjectDeletion() {
  const action = projectLibrary.deletion;
  if (!action || action.pending) return;
  const project = action.project;
  let releasedMedia = false;
  setProjectActionError("deletion");
  setProjectActionPending("deletion", true);
  try {
    if (projectLibraryBusy(project.id)) throw new Error("Wait for this project's import or active job, then try again.");
    const deletingCurrent = state.project?.id === project.id;
    if (deletingCurrent && !(await flushCurrentProjectSaves())) throw new Error("Your current edit could not be saved. Resolve the save error, then try again.");
    await flushProjectSaves(project.id);
    const work = await api(`/api/projects/${encodeURIComponent(project.id)}/jobs/active`);
    if (work.jobs?.length || projectLibraryBusy(project.id)) throw new Error("This project still has active work. Wait for it to finish or stop it in the editor, then try again.");
    if (deletingCurrent && state.project?.id === project.id) {
      releaseMediaHandles();
      releasedMedia = true;
      await new Promise((resolve) => window.setTimeout(resolve, 150));
    }
    await api(`/api/projects/${encodeURIComponent(project.id)}`, { method: "DELETE" });
    const queue = state.saveQueues.get(project.id);
    if (queue?.timer) clearTimeout(queue.timer);
    state.saveQueues.delete(project.id);
    localStorage.removeItem(`cutroom-draft-dirty:${project.id}`);
    projectLibrary.listRequest += 1;
    state.projects = state.projects.filter((item) => item.id !== project.id);
    clearRememberedProject(project.id);
    if (state.project?.id === project.id) {
      state.project = null;
      state.projectViewToken += 1;
      action.origin = { id: project.id, action: "open", inDialog: false };
      elements.projectsDialog.close();
      showWelcome();
    }
    renderRecentProjects();
    renderProjectDialog();
    elements.projectDeleteDialog.close();
    toast("Project deleted", "success");
  } catch (error) {
    if (releasedMedia && state.project?.id === project.id) renderDraft();
    setProjectActionError("deletion", error.message || "The project could not be deleted. Try again.");
  } finally { setProjectActionPending("deletion", false); }
}

// Independent copies use only the saved server snapshot. This host never sends
// project content, recreates a lost request under another key, or opens a result.
function copyOperationActive(entry) {
  return Boolean(entry && ["preparing","submitting","unknown","queued","running","publishing"].includes(entry.status));
}
function projectCopyForSource(projectId) {
  if(!projectId)return null;
  const local=state.projectCopies?.forSource?.(projectId);
  if(copyOperationActive(local))return local;
  const remote=state.project?.id===projectId ? state.project.project_copy : null;
  if(remote) {
    const known=state.projectCopies?.get?.(remote.operation_token);
    if(known)return copyOperationActive(known) ? known : null;
    if(copyOperationActive(remote))return remote;
  }
  return null;
}
function projectCopyLatestForSource(projectId) {
  return projectCopyForSource(projectId) || state.projectCopies?.forSource?.(projectId) || null;
}
function projectCopySourceBusy(projectId=state.project?.id) {
  const entry=projectCopyForSource(projectId);
  return Boolean(entry && entry.status!=="preparing");
}
function projectCopyFileBusy() {
  return Boolean(state.projectCopies?.active?.().some(entry=>entry.status!=="preparing"));
}
function initializeProjectCopies() {
  if(state.projectCopies || typeof initProjectCopyController!=="function")return state.projectCopies;
  state.projectCopies=initProjectCopyController({api,prepare:prepareSavedProjectCopy,
    changed:projectCopyChanged,completed:()=>{
      // A late library response must not remove the newly committed branch.
      projectLibrary.listRequest+=1;
      loadProjects().catch(error=>toast(`Copy created, but the library could not refresh: ${error.message}`));
    },storage:localStorage});
  return state.projectCopies;
}
async function recoverProjectCopies() {
  const controller=initializeProjectCopies();
  if(!controller)return;
  try{await controller.recover();}
  catch(error){console.warn("Could not check project copies",error);}
}
function observeProjectCopy(project) {
  if(!project?.project_copy)return null;
  const controller=initializeProjectCopies();
  if(!controller)return null;
  try{return controller.observe(project.project_copy);}
  catch(error){toast(`Copy status could not be verified: ${error.message}`);return null;}
}
function copyExplicitDraft() {
  const pending=explicitPendingDraft();
  if(pending)return pending;
  if(pendingTranscriptBuffers().length)return {target:"transcript",detail:"Save or discard your transcript changes before copying. They are still here and are not part of the saved project."};
  return null;
}
function projectCopyAdmissionBusy(projectId) {
  return Boolean(previewRepairBusy(projectId) || activeUploadsForProject(projectId).length || state.activeJobMeta?.projectId===projectId
    || state.retainedResumePending?.projectId===projectId
    || [...state.jobStartLocks].some(key=>String(key).endsWith(`:${projectId}`))
    || (state.project?.id===projectId && (state.mediaStudio?.uploading || state.stabilizationStudio?.uploading)));
}
function projectCopyGestureActive() {
  const timeline=state.timeline,source=state.sourceReview?.timeline;
  return Boolean(state.mediaStudio?.trackLevelGesture || timeline?.gesture || timeline?.scrubbing || timeline?.libraryDragActive || source?.gesture || source?.scrubbing
    || state.mediaStudio?.frameEditorState?.dragging || state.embeddedEditor?.dragging
    || document.documentElement?.classList?.contains?.("numeric-scrubbing"));
}
function revealCopyDraft(pending) {
  const action=projectLibrary.copy;
  if(action){action.noRestore=true;action.noContain=true;}
  if(elements.projectCopyDialog?.open)elements.projectCopyDialog.close();
  toast(pending.detail);revealPendingSave(pending);renderProjectSaveState();
}
async function prepareSavedProjectCopy(projectId,{cancelled=()=>false}={}) {
  const sourceWasCurrent=state.project?.id===projectId,view=state.projectViewToken;
  const current=()=>!cancelled() && (sourceWasCurrent
    ? state.project?.id===projectId && state.projectViewToken===view : state.project?.id!==projectId);
  if(projectLibrary.rename?.pending || projectLibrary.deletion?.pending)throw new Error("Finish the current project action before copying.");
  if(projectCopyAdmissionBusy(projectId))throw new Error("Finish this project's import or processing before copying.");
  if(sourceWasCurrent) {
    const explicit=copyExplicitDraft();
    if(explicit){revealCopyDraft(explicit);throw new Error(explicit.detail);}
    if(projectCopyGestureActive())throw new Error("Finish or cancel the current drag before copying.");
    if(!(await flushCurrentProjectSaves()) || !current())throw new Error("The current edit was not saved for this copy. Resolve its save state, then try again.");
    const remaining=copyExplicitDraft();
    if(remaining){revealCopyDraft(remaining);throw new Error(remaining.detail);}
    if(projectSaveStatus().kind!=="saved")throw new Error("Some project changes are still unsaved. Resolve them before copying.");
  }
  if(!sourceWasCurrent) {
    const queue=state.saveQueues.get(projectId);
    if(queue?.pending || queue?.inFlight || queue?.timer || queue?.error)throw new Error("This project has unresolved saved changes in this window. Open it and resolve the save state before copying.");
  }
  if(!current())throw new Error("The project view changed before copying. Start again from Projects.");
  const latest=await api(`/api/projects/${encodeURIComponent(projectId)}`);
  if(!current())throw new Error("The project view changed before copying. Start again from Projects.");
  if(latest?.project?.id!==projectId || !Number.isInteger(latest.project.revision) || latest.project.revision<1)throw new Error("The saved source revision could not be verified.");
  if(latest.project.project_copy) {
    observeProjectCopy(latest.project);
    throw new Error("This project already has a copy operation. Open its copy details.");
  }
  return {revision:latest.project.revision};
}
function projectCopyEntry() {
  const action=projectLibrary.copy;
  return action ? state.projectCopies?.get?.(action.token) || (action.started ? state.projectCopies?.forSource?.(action.project.id) : null) : null;
}
function copyDialogHoldsSource(entry=projectCopyEntry()) {
  return !projectLibrary.copy?.noContain && copyOperationActive(entry) && state.project?.id===entry.source_project_id
    && elements.workspaceView?.hidden===false && elements.welcomeView?.hidden===true;
}
function copyBytes(value) {
  const bytes=Number(value)||0;
  return bytes>=1024**3 ? `${(bytes/1024**3).toFixed(2)} GB` : bytes>=1024**2 ? `${(bytes/1024**2).toFixed(1)} MB` : `${Math.max(0,Math.round(bytes/1024))} KB`;
}
function copyStatusText(entry) {
  if(!entry)return "Only saved content is copied. Current queued edits are saved first; explicit local drafts must be resolved.";
  if(entry.status==="preparing")return "Saving queued changes and checking the saved project. No copy has been admitted yet.";
  if(entry.status==="submitting")return "Requesting an independent copy. The result has not been confirmed yet.";
  if(entry.status==="unknown")return entry.known ? "The copy was admitted, but its current status is not confirmed. Check status; the source remains protected until a verified result." : "Copy status is not confirmed. Check status or retry this same request; do not start another copy. The source remains protected.";
  if(entry.status==="completed")return "Independent copy ready. Your original stays separate. Choose Open copy when you are ready.";
  if(entry.status==="cancelled")return "Copy cancelled before publication. No new copy was created; your original is unchanged.";
  if(entry.status==="failed" || entry.status==="interrupted")return "The copy was not completed. Your original is unchanged. Choose Save another copy to review a new request.";
  if(entry.cancel_requested)return "Cancellation requested. Waiting for the confirmed result; a copy already committed may still complete.";
  if(entry.status==="publishing")return "Finalizing the independent copy. Waiting for its confirmed completion.";
  return `${entry.status==="queued" ? "Copy queued" : "Copying saved media"}${entry.total_bytes>0 ? `: ${copyBytes(entry.copied_bytes)} of ${copyBytes(entry.total_bytes)}` : ". Checking required storage and files."}`;
}
function renderProjectCopyDialog() {
  const action=projectLibrary.copy;if(!action || !elements.projectCopyDialog)return;
  const entry=projectCopyEntry(),held=copyDialogHoldsSource(entry),active=copyOperationActive(entry);
  elements.projectCopyName.disabled=Boolean(entry);
  elements.projectCopySource.textContent=`Source: ${projectLabel(action.project)}`;
  elements.projectCopyStatus.textContent=copyStatusText(entry);
  const error=action.error || entry?.error || "";
  elements.projectCopyError.textContent=error;elements.projectCopyError.hidden=!error;
  const progress=elements.projectCopyProgress;
  progress.hidden=!entry?.known || !active || entry.status==="unknown";
  if(!progress.hidden)progress.value=Number.isFinite(entry.progress) ? Math.max(0,Math.min(1,entry.progress)) : 0;
  elements.projectCopyCreate.hidden=active;elements.projectCopyCreate.disabled=Boolean(action.starting);
  elements.projectCopyCreate.textContent=entry ? "Save another copy" : "Create copy";
  elements.projectCopyCancel.hidden=!active;
  elements.projectCopyCancel.disabled=!entry?.canCancel || Boolean(entry.cancel_requested);
  elements.projectCopyCancel.textContent=entry?.cancel_requested ? "Cancellation requested" : "Cancel copy";
  elements.projectCopyCheck.hidden=entry?.status!=="unknown";
  elements.projectCopyCheck.disabled=Boolean(entry?.pending);
  elements.projectCopyRetry.hidden=!entry?.canRetry;
  elements.projectCopyRetry.disabled=Boolean(entry?.pending);
  elements.projectCopyOpen.hidden=entry?.status!=="completed";
  elements.projectCopyOpen.disabled=Boolean(action.opening);
  elements.projectCopyBack.hidden=!held;
  elements.closeProjectCopy.disabled=held;
  elements.cancelProjectCopy.hidden=held;
  elements.cancelProjectCopy.textContent=entry ? "Close" : "Cancel";
  elements.projectCopyNavigation.textContent=held
    ? "This source editor stays protected while copying. Back to Projects lets you edit another project without cancelling; imports and processing wait. Completion never opens the copy automatically."
    : active ? "Closing these details does not cancel the copy. Its source card shows progress in Projects. Other projects can be edited; imports and processing wait until this copy finishes."
      : "You choose when to open the copy. Saved media needs additional disk space; active imports or processing must finish first.";
}
function projectCopyMetadata(project) {
  const entry=projectCopyLatestForSource(project.id);
  if(!entry)return "";
  if(entry.status==="completed")return `Copy ready: ${entry.name}`;
  if(entry.status==="cancelled")return "Copy cancelled";
  if(["failed","interrupted"].includes(entry.status))return "Copy needs attention";
  return entry.status==="unknown" ? "Copy status unconfirmed" : entry.cancel_requested ? "Copy cancellation pending" : "Copying saved project";
}
function refreshProjectCopyRows() {
  for(const container of [elements.recentList,elements.dialogProjects]) {
    for(const row of container?.children || []) {
      const project=state.projects.find(item=>item.id===row.dataset?.projectId);if(!project)continue;
      const entry=projectCopyLatestForSource(project.id),button=row.querySelector?.('[data-project-action="copy"]');
      if(button){button.textContent=entry ? "Copy details" : "Save a copy";button.title=entry ? copyStatusText(entry) : "Create an independent copy of this saved project";}
      for(const kind of ["rename","delete"]){const control=row.querySelector?.(`[data-project-action="${kind}"]`);if(control){control.disabled=copyOperationActive(entry);control.title=control.disabled ? "Finish or cancel this project copy before changing its source." : "";}}
      const summary=row.querySelector?.("small");
      if(summary)summary.textContent=`${projectLibraryStateLabel(project)} | ${formatDate(project.updated_at)}${entry ? ` | ${projectCopyMetadata(project)}` : ""}`;
    }
  }
}
function projectCopyChanged(entry) {
  const action=projectLibrary.copy;
  if(action?.project.id===entry?.source_project_id && !action.token && action.started)action.token=entry.operation_token;
  refreshProjectCopyRows();renderProjectCopyDialog();
  const busy=projectCopySourceBusy();
  if(projectLibrary.lastCopyBusy!==busy) {
    projectLibrary.lastCopyBusy=busy;
    renderReadiness();
  }
  else renderProjectSaveState();
  const sourceOperation=projectCopyForSource(state.project?.id);
  if(sourceOperation && sourceOperation.status!=="preparing"
    && elements.workspaceView?.hidden===false && elements.welcomeView?.hidden===true
    && (!elements.projectCopyDialog?.open || projectCopyEntry()?.operation_token!==sourceOperation.operation_token))openProjectCopyOperation(sourceOperation);
}
function openProjectCopyOperation(entry) {
  if(!entry)return;
  initProjectLibrary();
  const project=state.projects.find(item=>item.id===entry.source_project_id)
    || (state.project?.id===entry.source_project_id ? state.project : {id:entry.source_project_id,name:"Saved project"});
  projectLibrary.copy={project,origin:projectLibraryFocus(),token:entry.operation_token,started:true};
  elements.projectCopyName.value=entry.name || "";
  renderProjectCopyDialog();
  if(!elements.projectCopyDialog.open)elements.projectCopyDialog.showModal();
  elements.projectCopyStatus.focus();
}
function openProjectCopy(project,{fresh=false}={}) {
  if(!project?.id)return;
  initProjectLibrary();
  if(!initializeProjectCopies()){toast("Project copying is unavailable in this build.");return;}
  const active=projectCopyForSource(project.id);
  if(active){openProjectCopyOperation(active);return;}
  const previous=projectCopyLatestForSource(project.id);
  if(previous && !fresh){openProjectCopyOperation(previous);return;}
  if(projectLibrary.rename?.pending || projectLibrary.deletion?.pending || projectCopyAdmissionBusy(project.id)) {
    toast("Finish this project's import, processing or project action before copying.");return;
  }
  if(state.project?.id===project.id) {
    const draft=copyExplicitDraft();if(draft){revealCopyDraft(draft);return;}
  }
  projectLibrary.copy={project,origin:projectLibraryFocus(),token:null,started:false,error:""};
  elements.projectCopyName.value=Array.from(`${projectLabel(project)} copy`).slice(0,120).join("");
  renderProjectCopyDialog();
  if(!elements.projectCopyDialog.open)elements.projectCopyDialog.showModal();
  elements.projectCopyName.focus();elements.projectCopyName.select();
}
async function createSavedProjectCopy() {
  const action=projectLibrary.copy;
  if(!action || action.starting)return;
  const previous=projectCopyEntry();
  if(previous && !copyOperationActive(previous)){openProjectCopy(action.project,{fresh:true});return;}
  if(action.started)return;
  const name=elements.projectCopyName.value.trim();
  if(!name || Array.from(name).length>120){action.error="Enter a name between 1 and 120 characters.";renderProjectCopyDialog();elements.projectCopyName.focus();return;}
  action.starting=true;action.started=true;action.error="";renderProjectCopyDialog();
  elements.projectCopyStatus.focus();
  try {await state.projectCopies.start(action.project.id,name);}
  catch(error){if(projectLibrary.copy===action){action.error=error.message || "The copy could not start.";action.started=false;}}
  finally {if(projectLibrary.copy===action){action.starting=false;renderProjectCopyDialog();}}
}
async function projectCopyRequest(kind) {
  const action=projectLibrary.copy,entry=projectCopyEntry();if(!action || !entry)return;
  action.error="";
  elements.projectCopyStatus.focus();
  try {await state.projectCopies[kind](entry.operation_token);}
  catch(error){if(projectLibrary.copy===action)action.error=error.message || "The copy status could not be confirmed.";}
  if(projectLibrary.copy===action)renderProjectCopyDialog();
}
function closeProjectCopyDialog() {
  if(copyDialogHoldsSource()){renderProjectCopyDialog();return;}
  elements.projectCopyDialog.close();
}
function leaveCopyForProjects() {
  const action=projectLibrary.copy;if(!action || !copyDialogHoldsSource())return;
  // Explicit navigation only. Keep current buffers/project/last-project intact;
  // opening another project still follows normal save/discard navigation guards.
  showWelcome();
  if(elements.projectsDialog?.open)elements.projectsDialog.close();
  action.origin={id:action.project.id,action:"copy",inDialog:false};
  elements.projectCopyDialog.close();
}
async function openSavedProjectCopy() {
  const action=projectLibrary.copy,entry=projectCopyEntry();
  if(!action || action.opening || entry?.status!=="completed" || !entry.copy_project_id)return;
  action.opening=true;action.noRestore=true;renderProjectCopyDialog();
  elements.projectCopyDialog.close();
  try {const opened=await openProject(entry.copy_project_id);if(opened && elements.projectsDialog?.open)elements.projectsDialog.close();}
  catch(error){toast(error.status===404 ? "This copy is no longer available. Its original was not changed." : error.message);}
}
function bindProjectCopyDialog() {
  if(!elements.projectCopyDialog)return;
  elements.projectCopyForm.addEventListener("submit",event=>{event.preventDefault();void createSavedProjectCopy();});
  for(const id of ["closeProjectCopy","cancelProjectCopy"])elements[id].addEventListener("click",closeProjectCopyDialog);
  for(const [id,kind] of [["projectCopyCancel","cancel"],["projectCopyCheck","check"],["projectCopyRetry","retry"]])elements[id].addEventListener("click",()=>{void projectCopyRequest(kind);});
  elements.projectCopyBack.addEventListener("click",leaveCopyForProjects);
  elements.projectCopyOpen.addEventListener("click",()=>{void openSavedProjectCopy();});
  elements.projectCopyDialog.addEventListener("cancel",event=>{if(copyDialogHoldsSource())event.preventDefault();});
  elements.projectCopyDialog.addEventListener("close",()=>{
    const action=projectLibrary.copy;
    // Browser/native Close cannot reveal the protected source while active.
    if(copyDialogHoldsSource()){elements.projectCopyDialog.showModal();elements.projectCopyStatus.focus();return;}
    projectLibrary.copy=null;
    if(action && !action.noRestore)restoreProjectLibraryFocus(action.origin);
  });
}

function formatDate(value) {
  try { return new Intl.DateTimeFormat(state.locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
  catch { return value || ""; }
}

function currentExportRangePlan() {
  const fps = Number(state.project?.settings?.fps ?? 30);
  // Source clips also have a numeric selection. Only an explicit In/Out/range gesture
  // is a marked export; merely inspecting one clip must not offer a delivery scope.
  if (!state.timeline?.selectionIsRange || Number(elements.exportFpsSelect?.value ?? fps) !== fps) return null;
  return makeExportRangePlan(rangeAuditionSnapshot(), fps);
}

function changedExportRangeMessage() {
  return uiCopy("טווח העריכה או קצב הפריימים השתנו. פתחו מחדש את חלון הייצוא ובדקו את הסימון.",
    "The edit, marks or frame rate changed. Reopen Export and review the range.");
}

function refreshExportScope({ reset=false, choose=false, progress=false }={}) {
  const control = elements.exportScope;
  if (!control || typeof makeExportRangePlan !== "function") return;
  if (reset) { control.value = "whole"; state.markedExportIntent = null; }
  elements.exportScopeField.hidden = progress;
  if (progress) return;
  const plan = currentExportRangePlan(), selected = control.value === "selection";
  const whole = control.querySelector('option[value="whole"]'), marked = control.querySelector('option[value="selection"]');
  elements.exportScopeLabel.textContent = uiCopy("טווח ייצוא", "Export range");
  whole.textContent = uiCopy("כל ציר הזמן", "Entire timeline");
  marked.textContent = uiCopy("הטווח המסומן", "Marked range");
  // Keep an invalidated choice selected; never silently fall back to a full export.
  marked.disabled = !plan && !selected;
  if (choose) state.markedExportIntent = selected ? plan : null;
  const valid = selected && sameExportRangePlan(state.markedExportIntent, plan);
  let help;
  if (valid) help = exportRangeLabel(plan.range) + " · " + uiCopy("נקודת הסיום אינה נכללת.", "Out is exclusive.");
  else if (selected) help = changedExportRangeMessage();
  else if (plan) help = uiCopy("ייצוא מלא. אפשר לבחור במקום זאת את הטווח המסומן.", "Exports the whole edit. Choose Marked range to export only your selection.");
  else help = uiCopy("ייצוא מלא. כדי לייצא חלק, סמנו טווח בתצוגת הווידאו הערוך.", "Exports the whole edit. For an excerpt, mark a range in the edited timeline first.");
  elements.exportScopeHelp.textContent = help;
  const cell = elements.exportSummary?.lastElementChild;
  if (cell) {
    const label = cell.querySelector("small"), value = cell.querySelector("b");
    label.textContent = selected ? marked.textContent : "Timeline duration";
    value.textContent = valid ? exportFrameTime(plan.range.end_frame-plan.range.start_frame,plan.range.fps)
      : selected ? "?" : formatTime(editorProject().draft.output_duration, true);
  }
}

function showExportSubtitles(record, previous=false) {
  const link = elements.downloadExportCaptions;
  if (!link) return;
  link.hidden = !(record?.captions_url && record?.captions_name);
  if (link.hidden) { link.removeAttribute?.("href"); link.removeAttribute?.("download"); return; }
  link.href = record.captions_url;
  link.download = record.captions_name;
  link.textContent = previous
    ? (record.range ? "Previous range subtitles (.srt)" : "Previous export subtitles (.srt)")
    : (record.range ? "Download range subtitles (.srt)" : "Download subtitles (.srt)");
}

function outputReviewSnapshot() {
  const project = editorProject();
  const aspect = elements.aspectSelect?.value || state.project?.settings?.aspect || "9:16";
  const source = state.project?.sources?.A;
  const sourceWidth = Math.trunc(Number(source?.width)), sourceHeight = Math.trunc(Number(source?.height));
  const sourceKnown = Number.isFinite(sourceWidth) && sourceWidth > 0 && Number.isFinite(sourceHeight) && sourceHeight > 0;
  // The same sizing function used by the composited viewer matches render._dimensions.
  // Missing source metadata must not masquerade as a landscape output preset.
  const dimensions = aspect === "source" && !sourceKnown ? null : previewExportDimensions();
  const duration = Number(project?.draft?.output_duration);
  const hasEdit = Boolean(project?.draft && !project.__timelineUnavailable && Number.isFinite(duration) && duration >= 0);
  return {
    dimensions,
    size: dimensions ? `${dimensions[0]} × ${dimensions[1]}` : "Source dimensions unavailable",
    aspect: aspect === "source" ? "Source A proportions" : aspect,
    fps: selectedFrameRate(),
    duration: hasEdit ? duration : null,
    length: hasEdit ? formatTime(duration, true) : "No editable timeline",
  };
}

function reviewOutputSettings() {
  if (foregroundBusy() || !state.project) return;
  elements.exportDialog.close();
  setAdvanced(true);
  selectAdvancedTab("settings");
  const panel = document.getElementById("studioPanelSettings");
  panel?.scrollIntoView({ block: "nearest", inline: "nearest" });
  document.querySelector('#studioShelfOutput [role="radio"][aria-checked="true"]')?.focus({ preventScroll: true });
}

function openExportDialog({ progress = false, requiredRangePlan = null } = {}) {
  showExportLayoutWarning(null);
  const previousStorageInfo=document.getElementById("exportStorageInfo");
  if(previousStorageInfo){previousStorageInfo.textContent="";previousStorageInfo.hidden=true;}
  if (state.project?.editor_sequence?.error) {
    toast(state.project.editor_sequence.error);
    return;
  }
  if (!progress && (!requireResolvedExplicitDrafts() || !requireSavedTranscript())) return;
  if (!state.project?.draft) return;
  const trackIssue=savedLayerTrackIssue();
  if (!progress && trackIssue) { toast(trackIssue); return; }
  if (!progress && !hasTimelineFootage()) { toast("Add footage to the timeline before exporting."); openSourceReview(); return; }
  pauseAllMedia();
  if (!progress && exportRequiresDraftRebuild()) {
    toast(uiCopy("יש לבנות מחדש את ה־Draft לפני הייצוא", "Rebuild the Draft before exporting these editorial changes"));
    if (state.studio.open) selectAdvancedTab("settings");
    return;
  }
  const settings = state.project.settings;
  if (requiredRangePlan) {
    if (progress || !clipRangeExportSupported()) return;
    updateFrameRateControls(settings.fps ?? 30);
    if (!sameExportRangePlan(requiredRangePlan, currentExportRangePlan())) {
      toast(changedExportRangeMessage());
      return;
    }
  }
  const draft = editorProject().draft;
  elements.exportSummary.innerHTML = "";
  const output = outputReviewSnapshot();
  const values = [
    [output.aspect, t("aspect")],
    [output.size, "Output pixels"],
    [output.length, "Timeline duration"],
  ];
  const outputSettings = document.getElementById("reviewOutputSettings");
  if (outputSettings) outputSettings.hidden = progress;
  for (const [value, label] of values) {
    const node = document.createElement("div"); node.innerHTML = `<b></b><small></small>`; $("b", node).textContent = value; $("small", node).textContent = label; elements.exportSummary.append(node);
  }
  elements.exportProgress.hidden = !progress;
  elements.exportActions.hidden = progress;
  elements.exportTitle.textContent = progress ? "Exporting your video" : t("readyToExport");
  elements.exportDescription.textContent = progress ? "You can stop this export at any time. Your edit stays saved."
    : state.draftDirtyReasons.size
      ? "Export your current edit. Pending AI preferences are not applied; rebuild only if you want a new AI draft."
      : t("exportHelp");
  if (!requiredRangePlan) updateFrameRateControls(settings.fps ?? 30);
  elements.exportFrameRateField.hidden = progress;
  elements.exportSummary.hidden = progress;
  if (requiredRangePlan) {
    elements.exportScope.value = "selection";
    state.markedExportIntent = requiredRangePlan;
    refreshExportScope();
  } else {
    refreshExportScope({reset:true, progress});
  }
  // The backend keeps exports newest-first so the default download must never
  // silently point to an older render after a project has multiple exports.
  const latestExport = !progress && Array.isArray(state.project.exports) ? state.project.exports[0] : null;
  showExportSubtitles(latestExport, true);
  if (latestExport?.layout_fallback) showExportLayoutWarning(latestExport.layout_fallback, "Previous export: ");
  if (latestExport?.url && latestExport?.name) {
    elements.downloadExport.href = latestExport.url;
    elements.downloadExport.download = latestExport.name;
    elements.downloadExport.textContent = latestExport.range ? `Download previous marked range (${latestExport.fps || 30} FPS)` : `Download previous export (${latestExport.fps || 30} FPS)`;
    elements.downloadExport.hidden = false;
  } else {
    elements.downloadExport.hidden = true;
  }
  elements.confirmExport.disabled = foregroundBusy();
  renderExportReview(progress ? null : latestExport?.review, latestExport?.range ? "Checks of the previous marked range" : "Checks of the previous export");
  if (!elements.exportDialog.open) elements.exportDialog.showModal();
}

// Clips board: read-only moment ranking. A chosen clip becomes an ordinary
// timeline range selection; existing selection, export and guard paths own the rest.
let clipBoard = null;

function clipBoardAspect() {
  const selected = String(state.project?.settings?.aspect || "16:9");
  const [width, height] = (selected === "source" ? sourceAspect() : selected).split(":").map(Number);
  return width > 0 && height > 0 ? width / height : 16 / 9;
}

// Card stills follow the confirmed camera-on-top stack used by vertical export.
function clipStillLayout() {
  if (!embeddedCameraIsActive()) return null;
  const camera = embeddedCameraCandidate();
  const content = camera && embeddedContentRectangle(camera);
  if (!camera || !content) return null;
  return { split: .30, camera: { x: camera.x, y: camera.y, w: camera.w, h: camera.h }, content, focus: camera.content_focus || { x: .5, y: .5 } };
}

function clipTimelineRange(clip) {
  const start = Number(clip?.start), end = Number(clip?.end);
  if (!state.project?.draft || !Number.isFinite(start) || !Number.isFinite(end) || end <= start) return null;
  const project = editorProject();
  if (project?.__timelineUnavailable) return null;
  if (!hasSourceTracks(project)) return { start, end };
  const pieces = [];
  for (const item of trackClips(project, "A")) {
    const sourceStart = Number(item.source_start), sourceEnd = sourceStart + Number(item.end) - Number(item.start);
    const left = Math.max(start, sourceStart), right = Math.min(end, sourceEnd);
    if (right > left) pieces.push({ start: Number(item.start) + left - sourceStart, end: Number(item.start) + right - sourceStart });
  }
  pieces.sort((a, b) => a.start - b.start || a.end - b.end);
  const merged = [];
  for (const piece of pieces) {
    const last = merged.at(-1);
    if (last && piece.start <= last.end + 1e-3) last.end = Math.max(last.end, piece.end);
    else merged.push({ ...piece });
  }
  // Only one continuous span of the edit that holds (nearly) the whole moment.
  if (merged.length !== 1 || merged[0].end - merged[0].start < (end - start) * .95) return null;
  return merged[0];
}

// Marked-range export is a separate capability; without it Export would mean the whole edit.
function clipRangeExportSupported() {
  return typeof currentExportRangePlan === "function" && typeof refreshExportScope === "function" && Boolean(elements.exportScope);
}

async function openClipFromBoard(clip, range, { exportAfter = false } = {}) {
  if (!state.project || !state.timeline) return;
  if (!state.studio.open) setAdvanced(true);
  if (!state.studio.open) return;
  const current = clipTimelineRange(clip);
  if (!current || Math.abs(current.start - range.start) > 1e-3 || Math.abs(current.end - range.end) > 1e-3) {
    toast("The edit changed. Open Clips again to choose this moment.");
    return;
  }
  if (hasSourceTracks(editorProject()) && !state.project.editor_sequence) setEditTarget("edit");
  state.timeline.selectRange(range.start, range.end);
  state.timeline.zoomToSelection?.();
  updateZoomLabel();
  seekSourcePreview(range.start);
  if (!exportAfter) {
    toast(`Clip ${clip.rank} is selected on the timeline. Trim, frame or caption it, then export the marked range.`, "success", 4200);
    return;
  }
  // A Clip can only hand off its exact reviewed range, never a generic whole edit.
  const fps = Number(state.project.settings?.fps ?? 30);
  const requiredRangePlan = clipRangeExportSupported() && state.timeline.selectionIsRange
    ? makeExportRangePlan(rangeAuditionSnapshot(), fps) : null;
  if (!requiredRangePlan || Math.abs(requiredRangePlan.inTime - range.start) > 1e-3
      || Math.abs(requiredRangePlan.outTime - range.end) > 1e-3) {
    toast(uiCopy("לא ניתן לסמן את הקליפ הזה לייצוא. בדקו את הטווח בציר הזמן הערוך.",
      "This clip could not be marked for export. Check the selection in the edited timeline."));
    return;
  }
  openExportDialog({ requiredRangePlan });
}

function placeClipFromBoard(clip) {
  if (!state.project?.sources?.A) return false;
  if (!state.studio.open) setAdvanced(true);
  const opened = state.studio.open && openSourceInsert({ projectId: state.project.id, slot: "A", scope: "edit", source_start: Number(clip.start), source_end: Number(clip.end) });
  if (!opened) toast("Footage cannot be placed right now. Finish the current task, then try again.");
  return opened;
}

// Export several Clips board moments, one marked-range render at a time. Each
// render uses the same server checks as Export; finishing one advances the
// project revision, which the next range is pinned to.
function clipBatchSupported() {
  return Boolean(state.project?.editor_sequence && !state.project.editor_sequence.error && clipRangeExportSupported());
}

async function exportClipBatch(clips, { onProgress = () => {}, isStopped = () => false } = {}) {
  const projectId = state.project?.id;
  const results = [];
  if (!projectId || !clipBatchSupported()) throw new Error("Batch export needs an edited timeline. Open the editor first.");
  if (!(await flushCurrentProjectSaves()) || state.project?.id !== projectId) throw new Error("Save your current edit before exporting clips.");
  const issue = savedLayerTrackIssue()
    || (!hasTimelineFootage() ? "Add footage to the timeline before exporting." : "")
    || (exportRequiresDraftRebuild() ? t("rebuildBeforeRefine") : "");
  if (issue) throw new Error(issue);
  if (!requireResolvedExplicitDrafts() || !requireSavedTranscript()) throw new Error("Resolve the pending text or caption changes before exporting.");
  pauseAllMedia();
  for (const [index, clip] of clips.entries()) {
    if (isStopped() || state.project?.id !== projectId) break;
    const range = clipTimelineRange(clip);
    if (!range) { results.push({ clip, error: "This moment is no longer in the edit." }); continue; }
    const fps = Number(state.project.settings?.fps ?? 30);
    const body = { range: { start_frame: Math.floor(range.start * fps + .5), end_frame: Math.floor(range.end * fps + .5), fps, expected_revision: state.project.revision } };
    const lock = acquireJobStartLock("render", projectId);
    if (!lock) { results.push({ clip, error: "Another job is already running." }); break; }
    let jobId = null;
    try {
      onProgress({ index, total: clips.length, clip, progress: 0 });
      const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/render`, { method: "POST", body: JSON.stringify(body) });
      jobId = payload.job.id;
      setActiveJob(jobId, { projectId, kind: "render" });
      let job = payload.job;
      while (!["completed", "failed", "interrupted", "cancelled"].includes(job.status)) {
        await new Promise(resolve => setTimeout(resolve, 800));
        if (isStopped() && !job.cancel_requested) {
          await api(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: "{}" }).catch(() => {});
        }
        job = (await api(`/api/jobs/${encodeURIComponent(jobId)}`)).job;
        onProgress({ index, total: clips.length, clip, progress: Number(job.progress) || 0 });
      }
      clearActiveJob(jobId);
      if (job.status !== "completed") {
        results.push({ clip, error: job.status === "cancelled" ? "Stopped." : friendlyRenderError(job.error || "Render failed") });
        if (job.status === "cancelled") break;
        continue;
      }
      await completeExportJob(job, projectId);
      results.push({ clip, url: job.result?.url, name: job.result?.export?.name });
    } catch (error) {
      if (jobId) clearActiveJob(jobId);
      results.push({ clip, error: friendlyRenderError(error.message) });
      if (["range_changed", "job_conflict", "insufficient_storage"].includes(error?.code)) break;
    } finally {
      releaseJobStartLock(lock);
    }
  }
  return results;
}

async function openClipBoard() {
  if (!state.project?.sources?.A) { toast("Add a main recording before looking for clips."); return; }
  if (!(await flushCurrentProjectSaves())) return;
  pauseAllMedia();
  clipBoard ||= new ClipBoard({
    api, notify: message => toast(message),
    getProject: () => state.project,
    mediaUrl: project => sourceMediaUrl(project.sources.A),
    outputAspect: clipBoardAspect,
    stillLayout: clipStillLayout,
    canExport: clipRangeExportSupported,
    canBatch: clipBatchSupported,
    exportBatch: exportClipBatch,
    timelineRange: clipTimelineRange,
    openClip: openClipFromBoard,
    canPlace: () => Boolean(state.project?.editor_sequence && !state.project.editor_sequence.error),
    placeClip: placeClipFromBoard,
    postingKit: (clip, useAi) => api(`/api/projects/${state.project.id}/posting-kit`, {
      method: "POST",
      body: JSON.stringify({ start: clip.start, end: clip.end, use_ai: Boolean(useAi), goal: state.project?.settings?.goal === "youtube" ? "youtube" : "short" }),
    }).then(result => result.kit),
    pauseEditor: () => pauseAllMedia(),
    onClose: ({ handedOff }) => { if (!handedOff && !document.querySelector("dialog[open]")) document.getElementById("clipBoardButton")?.focus({ preventScroll: true }); },
  });
  await clipBoard.open();
}

function showExportLayoutWarning(fallback, prefix = "") {
  const target = document.getElementById("exportLayoutWarning");
  if (!target) return;
  const warning = typeof fallback?.warning === "string" ? fallback.warning : "";
  target.textContent = warning ? `${prefix}${warning}` : "";
  target.hidden = !warning;
}

// The bounded check run after each export: advice, never a block.
function renderExportReview(review, title) {
  const list = elements.exportReview;
  if (!list) return;
  const checks = Array.isArray(review?.checks) ? review.checks.filter(check => check?.detail && check.status !== "skipped") : [];
  const heading = document.createElement("li");
  heading.className = "export-review-title"; heading.textContent = title;
  list.replaceChildren(heading, ...checks.map(check => {
    const item = document.createElement("li");
    item.dataset.status = check.status;
    item.textContent = `${check.status === "warn" ? "⚠" : check.status === "pass" ? "✓" : "·"} ${check.detail}`;
    return item;
  }));
  list.hidden = !checks.length;
}

async function startExport() {
  const selected = elements.exportScope?.value === "selection";
  const intent = selected ? state.markedExportIntent : null;
  const rangeMatches = () => (elements.exportScope?.value === "selection") === selected
    && (!selected || (typeof sameExportRangePlan === "function" && sameExportRangePlan(intent,currentExportRangePlan())));
  if (!rangeMatches()) { refreshExportScope(); toast(changedExportRangeMessage()); return; }
  const projectId=state.project?.id,viewToken=state.projectViewToken;
  const current=()=>state.project?.id===projectId && state.projectViewToken===viewToken;
  const trackIssue=savedLayerTrackIssue();if(trackIssue){toast(trackIssue);return;}
  if(!requireResolvedExplicitDrafts())return;
  if (state.textStudio && !(await state.textStudio.flush())) return;
  if(!current() || !requireResolvedExplicitDrafts())return;
  if (state.mediaStudio && !(await state.mediaStudio.flush())) return;
  if(!current() || !requireResolvedExplicitDrafts())return;
  if (!requireSavedTranscript()) return;
  if (!state.project?.draft) return;
  const savedTrackIssue=savedLayerTrackIssue();if(savedTrackIssue){toast(savedTrackIssue);return;}
  if (!hasTimelineFootage()) { toast("Add footage to the timeline before exporting."); return; }
  if (exportRequiresDraftRebuild()) { toast(t("rebuildBeforeRefine")); return; }
  pauseAllMedia();
  const reviewLayout = document.getElementById("reviewExportLayout"); if (reviewLayout) reviewLayout.hidden = true;
  if (liveEmbeddedCameraRequest() && (!(await flushEmbeddedCameraSave(projectId)) || state.project?.id !== projectId)) return;
  if(!current() || !requireResolvedExplicitDrafts())return;
  const lock = acquireJobStartLock("render", projectId);
  if (!lock) { toast(uiCopy("כבר מתבצעת עבודה", "Another job is already running")); return; }
  showExportLayoutWarning(null);
  elements.exportActions.hidden = true;
  elements.exportProgress.hidden = false;
  const outputSettings = document.getElementById("reviewOutputSettings");
  if (outputSettings) outputSettings.hidden = true;
  elements.exportFrameRateField.hidden = true;
  if (elements.exportScopeField) elements.exportScopeField.hidden = true;
  elements.exportTitle.textContent = selected ? "Exporting your marked range" : "Exporting your video";
  elements.exportDescription.textContent = "You can stop this export at any time. Your edit stays saved.";
  const storageInfo=document.getElementById("exportStorageInfo");if(storageInfo){storageInfo.textContent="Checking export and project working space…";storageInfo.hidden=false;}
  elements.downloadExport.hidden = true;
  showExportSubtitles(null);
  try {
    await flushProjectSaves(projectId);
    assertJobStartNotCancelled();
    if (!current()) throw new Error("Cancelled");
    if(!requireResolvedExplicitDrafts() || !requireSavedTranscript())return;
    const latestTrackIssue=savedLayerTrackIssue();if(latestTrackIssue)throw new Error(latestTrackIssue);
    if (exportRequiresDraftRebuild()) throw new Error("The draft settings changed. Rebuild before exporting these changes.");
    // The controls above save their exact fields before export. The backend
    // uses the accepted project settings, not stale/rounded hidden form values.
    if (!rangeMatches()) throw new Error(changedExportRangeMessage());
    const body = selected ? {range:intent.range} : {};
    const payload = await api(`/api/projects/${encodeURIComponent(projectId)}/render`, { method: "POST", body: JSON.stringify(body) });
    if (state.project?.id === projectId) showExportLayoutWarning(payload.layout_fallback);
    if(storageInfo){const estimate=payload.storage_estimate;
      storageInfo.textContent=estimate?storagePlanText({filesystems:estimate.volumes.map(row=>({...row,required_bytes:row.working_bytes,disk_free_bytes:row.free_bytes,reserved_bytes:0,available_bytes:Math.max(0,row.free_bytes-row.reserve_bytes)}))}):"";
      storageInfo.hidden=!storageInfo.textContent;
    }
    setActiveJob(payload.job.id, { projectId, kind: "render" });
    const job = await pollExportJob(payload.job.id, projectId);
    await completeExportJob(job, projectId);
  } catch (error) {
    if (state.project?.id === projectId) {
      showExportLayoutWarning(null);
      if (reviewLayout) reviewLayout.hidden = error.payload?.error !== "layout_coverage_incomplete";
      if(storageInfo){storageInfo.textContent=storagePlanText(error.payload?.storage_plan);storageInfo.hidden=!storageInfo.textContent;}
      elements.exportActions.hidden = false;
      elements.exportProgress.hidden = true;
      if (outputSettings) outputSettings.hidden = false;
      elements.exportFrameRateField.hidden = false;
      refreshExportScope();
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
  if (value.includes("Cannot inspect configured FFmpeg") || /(?:ENOENT|FileNotFoundError).*ffmpeg/i.test(value)) {
    return uiCopy(
      "FFmpeg אינו זמין לייצוא. העריכה נשמרה. בדקו את הוראות ההתקנה, הפעילו מחדש את CUTROOM ונסו שוב.",
      "FFmpeg is unavailable for export. Your edit is saved. Check the installation guide, restart CUTROOM, then try again.",
    );
  }

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
      elements.exportSummary.hidden = false;
      refreshExportScope({reset:true});
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
      const range = result.export.range;
      elements.exportTitle.textContent = range ? "Your marked range is ready" : "Your video is ready";
      elements.exportDescription.textContent = range ? `${exportRangeLabel(range)} · ${range.fps} FPS. Your full timeline is unchanged.` : `Exported at ${result.export.fps || state.project.settings?.fps || 30} FPS. Download the finished video below.`;
      showExportLayoutWarning(result.export.layout_fallback);
      elements.downloadExport.href = result.url;
      elements.downloadExport.download = result.export.name;
      showExportSubtitles(result.export);
      elements.downloadExport.textContent = range ? `Download marked range (${range.fps} FPS)` : `Download video (${result.export.fps || state.project.settings?.fps || 30} FPS)`;
      elements.downloadExport.hidden = false;
      renderExportReview(result.export.review, "Checks of this video");
    }
  }
  const projectPayload = await api(`/api/projects/${encodeURIComponent(projectId)}`);
  rememberProjectRevision(projectPayload.project);
  if (projectIsVisible && state.project?.id === projectId) {
    const previous = state.project, next = projectPayload.project, tl = state.timeline;
    state.project = next;
    // Saving a completed delivery advances the document revision but changes no edits.
    // Adopt that exact one-revision export commit without clearing marks, selection,
    // gestures or the playhead; never advance the timeline past an unreviewed edit.
    if (tl?.project?.id === projectId && tl.project.revision === previous.revision
        && Number.isInteger(previous.revision) && next.revision === previous.revision + 1
        && result?.export?.id && next.exports?.[0]?.id === result.export.id) {
      tl.project = editorProject(next);
      state.rangeAudition?.sync();
    }
  } else toast(uiCopy("הייצוא של הפרויקט האחר הסתיים", "The other project's export is ready"), "success", 3600);
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
  const selection = models?.story_ai_selection;
  const fallback = selection?.using_fallback === true;
  const installed = Boolean(models?.story_ai_ready);
  const engineAvailable = runtime?.state !== "disabled" && (typeof models?.ollama?.available === "boolean" ? models.ollama.available : Boolean(runtime?.available));
  const ready = engineAvailable && installed;
  const preparing = Boolean(state.aiPreparePromise);
  const installing = Boolean(state.modelInstallPending || state.modelInstallJob);
  const starting = preparing || ["idle", "checking", "starting"].includes(runtime?.state);
  let title = ready ? fallback ? "Story AI ready with a fallback model" : "Story AI ready" : engineAvailable ? "One-time AI setup" : "Local AI needs attention";
  const actualModel = selection?.selected_model || models?.selected_story_model || "Installed model";
  const fallbackDetail = selection?.message || (selection?.fallback_reason === "requested_model_missing"
    ? `${selection.requested_model || "The requested model"} is not installed. Using the installed fallback; download the requested model only if you choose to.`
    : `Using an installed fallback for ${selection?.requested_model || "the requested model"}.`);
  let detail = ready ? `${actualModel} · ${fallback ? fallbackDetail : "Runs on this computer"}`
    : engineAvailable ? `${models?.recommended_story_model || "A Story AI model"} is needed. Download only with your confirmation; it can require several GB.`
      : (runtime?.available ? "The local AI engine is no longer responding. Use Retry AI to restart it." : runtime?.message) || state.system?.error || "Checking the local AI engine…";
  if (starting) { title = "Preparing local AI…"; detail = "Starting the local engine. Your footage stays on this computer."; }
  if (runtime?.state === "disabled" && !preparing) title = "Local AI is disabled";
  if (installing) { title = "Downloading Story AI…"; detail = "One-time model setup. You can stop this download using Stop process."; }
  if (starting && !preparing && state.runtimeRefreshAttempts >= 20) detail = "The engine is taking longer than expected. Use Retry AI to check again.";
  elements.modelStatus.className = `model-status ${ready && !fallback && !preparing && !installing ? "ready" : "partial"}`;
  elements.modelStatus.dataset.state = installing ? "installing" : starting ? "starting" : ready ? fallback ? "fallback-model" : "ready" : engineAvailable ? "missing-model" : "missing-engine";
  $("b", elements.modelStatus).textContent = title;
  $("small", elements.modelStatus).textContent = detail;
  elements.modelButton.hidden = !engineAvailable || (installed && !(fallback && selection?.requested_model_installed === false)) || preparing || installing;
  elements.modelButton.textContent = fallback ? "Download requested model" : "Download model…";
  // The larger Story model is optional. Quality and a roomy GPU in Auto offer
  // it; the download itself still happens in AI connection with confirmation.
  const upgrade = document.getElementById?.("modelUpgradeButton");
  if (upgrade) {
    const suggested = ready && !fallback && !preparing && !installing ? selection?.upgrade_model : null;
    upgrade.hidden = !suggested;
    if (suggested) {
      const qualityMode = selection?.upgrade_reason === "quality_mode";
      upgrade.textContent = `Optional: get ${suggested}`;
      upgrade.title = qualityMode
        ? `Quality works with ${actualModel}. ${suggested} is an optional, larger download for stronger drafts. Opens AI connection; nothing downloads without your confirmation.`
        : `Your GPU can run ${suggested}. It writes stronger drafts than ${actualModel}. Opens AI connection; the download needs your confirmation.`;
      $("small", elements.modelStatus).textContent = qualityMode
        ? `${actualModel} · Runs on this computer · ${suggested} is an optional upgrade`
        : `${actualModel} · Runs on this computer · ${suggested} fits your GPU for stronger drafts`;
    }
  }
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
          story_ai_selection: payload.story_ai || null,
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
