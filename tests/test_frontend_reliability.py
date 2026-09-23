from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

from cutroom.composition import FACE_LAYOUT_VERSION


ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
TIMELINE = (ROOT / "web" / "timeline.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
AUDIO_METER = (ROOT / "web" / "audio-meter.js").read_text(encoding="utf-8")


def function_block(source: str, name: str, next_name: str) -> str:
    return source.split(f"function {name}", 1)[1].split(f"function {next_name}", 1)[0]


def test_huemint_palette_is_semantic_accessible_and_canvas_consistent():
    palette = ("#7459a3", "#501a91", "#1bb92a", "#c9b62c", "#44b9c6", "#081013")
    css = CSS.lower()
    canvas_code = f"{TIMELINE}\n{AUDIO_METER}".lower()
    for color in palette:
        assert color in css
    assert 'content="#081013"' in HTML.lower()
    assert "var(--signal-text)" in css
    assert "#44b9c6" in canvas_code
    assert "#c9b62c" in canvas_code

    retired_accents = (
        "#7c8cff",
        "#a8b0ff",
        "#baff63",
        "#69dce1",
        "#73e0e5",
        "#ffc66d",
        "#ffcf67",
        "rgba(124,140,255",
        "rgba(105,220,225",
        "rgba(115,224,229",
        "rgba(187,255,93",
    )
    combined = f"{CSS}\n{TIMELINE}\n{AUDIO_METER}".lower().replace(" ", "")
    for accent in retired_accents:
        assert accent not in combined


def test_autosave_is_scoped_merged_serial_and_revision_aware():
    assert "saveQueues: new Map()" in APP
    assert "function mergePatchValues" in APP
    assert "queue.pending = mergePatchValues(queue.pending || {}, patch || {})" in APP
    assert "queue.inFlight" in APP
    assert "expected_revision: expectedRevision" in APP

    schedule = function_block(APP, "schedulePatch", "flushProjectSaves")
    assert "const projectId = state.project?.id" in schedule
    assert schedule.index("const projectId") < schedule.index("setTimeout")

    flush = function_block(APP, "flushProjectSaves", "flushCurrentProjectSaves")
    assert "state.project?.id === projectId" in flush
    assert "applyPatchToProject(savedProject, queue.pending)" in flush
    assert "queue.pending = mergePatchValues(patch, queue.pending || {})" in flush
    assert "responseRevision < knownRevision" in flush
    assert "!responseIsStale && state.project?.id === projectId" in flush


def test_navigation_flushes_and_ignores_stale_project_responses():
    open_project = function_block(APP, "openProject", "hydrateProject")
    assert "await flushCurrentProjectSaves()" in open_project
    assert "const viewToken = ++state.projectViewToken" in open_project
    assert "viewToken !== state.projectViewToken" in open_project
    assert open_project.index("flushCurrentProjectSaves") < open_project.index("/api/projects/")
    assert "async function goHome()" in APP
    assert "await flushCurrentProjectSaves()" in function_block(APP, "goHome", "showWorkspace")


def test_active_jobs_are_recovered_and_job_starts_are_locked():
    assert "/jobs/active" in APP
    recovery = function_block(APP, "recoverActiveJobs", "pollJob")
    assert 'item.kind === "prepare_source"' in recovery
    assert "retrySourcePreparation(projectId, slot, latestPreparation.id)" in recovery
    assert '["director", "refine", "render"]' in recovery
    assert "resumeExportJob" in recovery
    assert "pollJob(foreground.id" in recovery
    assert "async function retrySourcePreparation" in APP
    assert "/sources/${encodeURIComponent(slot)}/prepare" in APP
    assert '["failed", "interrupted"].includes(job.status)' in APP

    assert "jobStartLocks: new Set()" in APP
    assert "function acquireJobStartLock" in APP
    director = function_block(APP, "generateDraft", "ensureStoryAIReady")
    export = function_block(APP, "startExport", "resumeExportJob")
    assert 'acquireJobStartLock("director", projectId)' in director
    assert 'acquireJobStartLock("render", projectId)' in export
    assert "flushProjectSaves(projectId)" in director
    assert "flushProjectSaves(projectId)" in export


def test_background_preparation_recovery_keeps_project_context_and_valid_audio_state():
    monitor = function_block(APP, "monitorBackgroundJob", "retrySourcePreparation")
    retry = function_block(APP, "retrySourcePreparation", "refreshProjectAfterDirector")
    upload = function_block(APP, "uploadSource", "uploadWithProgress")

    assert "projectId: options.projectId" in monitor
    assert "refreshAudio: Boolean(options.refreshAudio)" in monitor
    assert "state.project.settings?.audio_cleanup || {}" in retry
    assert "source?.generation" in retry
    assert "retriedSourcePreparations.delete(key)" in retry
    assert "payload.preparation_deferred" in upload
    assert "loadProjects().catch" in upload


def test_export_dialog_uses_backend_newest_first_order():
    dialog = function_block(APP, "openExportDialog", "startExport")
    assert "state.project.exports[0]" in dialog
    assert "state.project.exports.at(-1)" not in dialog


def test_upload_slots_and_studio_tabs_have_keyboard_contracts():
    assert HTML.count('class="source-slot') == 2
    assert HTML.count('role="button" tabindex="0" aria-describedby=') == 2
    assert 'slotElement.addEventListener("keydown"' in APP
    assert '["Enter", " "].includes(event.key)' in APP
    assert HTML.count('role="tab"') == 4
    assert HTML.count('role="tabpanel"') == 5
    assert 'id="studioPanelMedia" role="tabpanel" aria-labelledby="studioTabMedia"' in HTML
    media_tab = APP.split("function initializeMediaStudio()", 1)[1].split("\nfunction ", 1)[0]
    assert 'tab.id = "studioTabMedia"' in media_tab
    assert 'tab.setAttribute("role", "tab")' in media_tab
    assert 'tab.setAttribute("aria-controls", "studioPanelMedia")' in media_tab
    assert 'tab.addEventListener("keydown", handleStudioTabKeydown)' in media_tab
    assert "aria-selected" in HTML
    assert "function handleStudioTabKeydown" in APP


def test_rebuild_required_settings_cannot_silently_export_old_draft():
    assert 'id="draftRebuildNotice"' in HTML
    assert HTML.count("data-rebuild-chip") >= 6
    assert "function markDraftRebuild" in APP
    assert "cutroom-draft-dirty:" in APP
    assert "state.draftDirtyReasons.size" in function_block(APP, "openExportDialog", "startExport")
    assert "requiresRebuild" in function_block(APP, "scheduleSettingsPatch", "isPlainObject")
    assert "state.project.settings?.aspect || draft.aspect" in APP


def test_ranked_reels_and_scene_layout_controls_are_real_manual_edits():
    assert 'id="reelCandidates"' in HTML
    assert 'id="sceneLayoutEditor"' in HTML
    assert 'id="effectsToggle"' in HTML
    assert 'applyManualEdit("apply_reel_candidate"' in APP
    assert 'applyManualEdit("set_camera_layout"' in APP
    assert "renderSceneLayoutEditor(true)" in APP
    assert "editorial_effects: elements.effectsToggle.checked" in APP


def test_result_exposes_an_explicit_quality_ranked_cut_variation() -> None:
    assert 'data-command="new_variation"' in HTML
    assert 'data-i18n="anotherCut"' in HTML
    refine = function_block(APP, "refineDraft", "showSetup")
    assert "/director/refine" in refine
    assert 'command === "new_variation"' in refine
    assert 'changed ? "anotherCutReady" : "anotherCutUnchanged"' in refine


def test_manual_corrections_are_discoverable_keyboard_safe_and_atomic():
    for element_id in ("manualRestore", "manualDelete", "manualSplit", "manualUndo", "manualRedo"):
        assert f'id="{element_id}"' in HTML

    class TimelineMarkup(HTMLParser):
        def __init__(self):
            super().__init__()
            self.matches = []

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            if attributes.get("id") == "timelineCanvas":
                self.matches.append((tag, attributes))

    markup = TimelineMarkup()
    markup.feed(HTML)
    assert len(markup.matches) == 1
    tag, attributes = markup.matches[0]
    assert tag == "canvas"
    for name, value in {
        "role": "slider", "tabindex": "0", "aria-label": "Edit timeline",
        "data-editor-shortcuts": "on",
    }.items():
        assert attributes.get(name) == value, f"timelineCanvas requires {name}={value!r}"
    assert "event.shiftKey" in TIMELINE
    assert "keyDown(event)" in TIMELINE
    assert "setSelection(selection" in TIMELINE
    assert "drawSelection" in TIMELINE

    manual = function_block(APP, "applyManualEdit", "beginTranscriptEdit")
    assert "/manual/edit" in manual
    assert "expected_revision" in manual
    assert "state.project?.id !== projectId" in manual
    for action in ("restore_range", "delete_range", "transcript_text", "undo", "redo"):
        assert action in APP
    assert "beginTranscriptEdit" in APP


def test_project_delete_is_exposed_with_confirmation():
    assert "dialog-project-delete" in APP
    delete = function_block(APP, "deleteProject", "formatDate")
    assert "window.confirm" in delete
    assert 'method: "DELETE"' in delete
    assert "flushCurrentProjectSaves" in delete


def test_current_project_delete_releases_windows_media_handles_before_request_and_commits_ui_after_success():
    release = function_block(APP, "releaseMediaHandles", "setPreviewPlaying")
    delete = function_block(APP, "deleteProject", "formatDate")

    assert 'document.querySelectorAll("video, audio")' in release
    assert 'media.removeAttribute("src")' in release
    assert 'media.removeAttribute("poster")' in release
    assert "media.srcObject = null" in release
    assert "media.load()" in release
    assert delete.index("releaseMediaHandles()") < delete.index('method: "DELETE"')
    assert "window.setTimeout(resolve, 150)" in delete
    assert delete.index('method: "DELETE"') < delete.index("state.saveQueues.delete(project.id)")
    assert delete.index('method: "DELETE"') < delete.index("state.projects = state.projects.filter")
    assert "renderDraft()" in delete


def test_edit_styles_apply_real_settings_and_are_not_cosmetic_labels():
    assert 'id="editStyleChoices"' in HTML
    assert 'role="radiogroup"' in HTML
    assert "state.system?.edit_styles" in APP
    assert "function renderEditStyleChoices" in APP

    apply_style = function_block(APP, "applyEditStyle", "hydrateAudioSettings")
    assert "state.selectedEditStyle" in apply_style
    assert "applyGoalMode" not in apply_style
    assert "updateDurationControl" not in apply_style
    assert "setChoiceValue(elements.paceChoices" in apply_style
    assert "hydrateAudioSettings(defaults.audio_cleanup)" in apply_style
    for setting in (
        "layoutSelect",
        "performanceModeSelect",
        "captionsToggle",
        "burnCaptionsToggle",
    ):
        assert setting in apply_style
    for setting in ("aspectSelect", "resolutionSelect", "qualitySelect"):
        assert setting not in apply_style
    assert "edit_style: state.selectedEditStyle" in APP


def test_director_failure_stays_on_an_actionable_error_screen():
    for element_id in ("analysisError", "retryDirectorButton", "backFromErrorButton"):
        assert f'id="{element_id}"' in HTML

    director = function_block(APP, "generateDraft", "ensureStoryAIReady")
    assert "reconcileDirectorOutcome" in director

    reconcile = function_block(APP, "reconcileDirectorOutcome", "generateDraft")
    assert '/api/projects/${encodeURIComponent(projectId)}' in reconcile
    assert "rememberProjectRevision(state.project)" in reconcile
    assert "if (state.project?.draft)" in reconcile
    assert "hydrateProject()" in reconcile
    assert "showAnalysisError(message)" in reconcile

    error_view = function_block(APP, "showAnalysisError", "showResult")
    assert "showAnalysis()" in error_view
    assert 'elements.analysisPanel.classList.add("failed")' in error_view
    assert "elements.analysisError.hidden = false" in error_view
    assert "elements.cancelJobButton.hidden = true" in error_view

    recovery = function_block(APP, "recoverActiveJobs", "pollJob")
    assert "latestDirector" in recovery
    assert ".sort((left, right) => Date.parse(right.created_at || 0)" in recovery
    assert "[...recent].reverse().find" not in recovery
    assert "reconcileDirectorOutcome" in recovery

    friendly = function_block(APP, "friendlyDirectorError", "showAnalysisError")
    assert "omitted one or more chapters" in friendly
    assert "retries only the missing chapter" in friendly
    assert "!state.project?.sources?.A" in friendly
    assert "transcript quality is too low" in friendly
    assert "חומר הגלם נשמר" in friendly


def test_job_polling_recovers_instead_of_declaring_a_false_director_failure():
    polling = function_block(APP, "pollJob", "updateJobUI")
    assert '/api/projects/${encodeURIComponent(options.projectId)}/jobs/active' in polling
    assert "consecutivePollFailures >= 4" in polling
    assert "A temporary local-server interruption is not a failed edit" in polling
    assert "schedule(Math.min(5000" in polling


def test_foreground_jobs_can_be_cancelled_from_every_view_and_during_export():
    for element_id in ("activeJobBar", "globalCancelJobButton", "cancelJobButton", "cancelExportJobButton"):
        assert f'id="{element_id}"' in HTML
    assert "cancelRequestedJobs: new Set()" in APP
    assert "cancelBeforeStart: false" in APP

    request = function_block(APP, "requestJobCancellation", "cancelActiveJob")
    assert '/api/jobs/${encodeURIComponent(jobId)}/cancel' in request
    assert "state.cancelRequestedJobs.add(jobId)" in request
    assert "payload?.job" in request
    assert "cancelFailed" in request

    cancel = function_block(APP, "cancelActiveJob", "renderDraft")
    assert "requestJobCancellation(state.activeJob)" in cancel
    assert "state.cancelBeforeStart = true" in cancel
    assert "recover:" in cancel

    assert "function renderActiveJobBar" in APP
    assert "job?.cancel_requested" in APP
    assert 't("cancelling")' in APP
    export_progress = function_block(APP, "updateExportProgress", "completeExportJob")
    assert "jobCancellationRequested(job)" in export_progress
    assert "renderActiveJobBar(job)" in export_progress


def test_single_source_preview_never_duplicates_without_explicit_confirmation():
    assert "function embeddedLayoutConfirmed" in APP
    confirmation = function_block(APP, "embeddedLayoutConfirmed", "embeddedCameraCandidate")
    assert "embedded_layout_confirmed === true" in confirmation
    assert 'draft?.layout === "embedded_stack"' in confirmation

    candidate = function_block(APP, "embeddedCameraCandidate", "setupPreviewSources")
    assert f'const EMBEDDED_CAMERA_DETECTOR_VERSION = "{FACE_LAYOUT_VERSION}"' in APP
    assert "vision.version !== detectorVersion" in candidate
    assert "candidate.requires_confirmation !== true" in candidate

    sources = function_block(APP, "setupPreviewSources", "togglePreview")
    assert "embedded && embeddedLayoutConfirmed()" in sources
    camera = function_block(APP, "cameraAt", "seekPreview")
    assert 'camera === "embedded_stack" && !embeddedLayoutConfirmed()' in camera
    assert '["B", "stacked", "side_by_side", "pip"]' in camera
    decisions = function_block(APP, "renderDecisions", "embeddedLayoutConfirmed")
    assert 'decision?.type !== "smart_layout" || embeddedLayoutConfirmed()' in decisions


def test_style_cards_expose_pacing_and_preserved_output_copy():
    choices = function_block(APP, "renderEditStyleChoices", "applyEditStyle")
    assert "style.defaults?.pace" in choices
    assert "Your goal, output format and duration stay selected" in choices
    assert "button.dataset.category" in choices
    assert "לעולם לא מופעלת בלי אישור מפורש" in choices


def test_two_source_mixer_exposes_immediate_manual_control():
    for element_id in (
        "sourceMixer", "screenSourceSelect", "cameraSourceSelect", "primaryRoleSelect", "audioSourceSelect",
        "firstSlotSelect", "swapSourceRoles", "sourceSyncOffset", "resetSourceSync", "sourceLayoutChoices", "applyLayoutSelection", "applyLayoutAll", "resetSourceLayout", "cropSourceSelect",
        "sourceCompositionPreview", "sourceCompositionCanvas", "sourceCompositionA", "sourceCompositionB",
    ):
        assert f'id="{element_id}"' in HTML
    for layout in ("auto", "screen", "camera", "stacked", "side_by_side", "pip"):
        assert f'data-layout="{layout}"' in HTML

    mixer = function_block(APP, "renderSourceMixer", "saveSourceMixer")
    assert "camera_overrides" in mixer
    assert "state.manualSelection" in mixer
    assert "elements.applyLayoutSelection.disabled" in mixer
    apply_layout = function_block(APP, "applySourceLayout", "embeddedLayoutConfirmed")
    assert 'applyManualEdit("set_camera_layout"' in apply_layout
    assert 'scope === "selection"' in apply_layout
    assert "const duration = editorDuration()" in apply_layout

    assert 'id="setupSourceMixerDock"' in HTML
    placement = function_block(APP, "placeSourceMixer", "saveSourceMixer")
    assert "hasSource && !state.project?.draft" in placement
    assert "setupSourceMixerDock.appendChild" in placement
    manual = function_block(APP, "applyManualEdit", "beginTranscriptEdit")
    assert 'action === "set_source_mixer"' in manual
    assert "!latest.project.draft && !projectLevelAction" in manual
    bindings = function_block(APP, "bindEvents", "installDropZone")
    assert "Default layout saved for Director" in bindings
    assert "sourceMixerLayoutTouched = true" in bindings
    assert "default_layout: button.dataset.layout" in bindings
    assert "await saveSourceMixer" in bindings


def test_source_mixer_routing_controls_wrap_without_overlapping():
    assert 'class="source-role-pair"' in HTML
    assert 'class="source-routing-grid"' in HTML
    role_pair = HTML.split('<div class="source-role-pair">', 1)[1].split("</div>", 1)[0]
    routing = HTML.split('<div class="source-routing-grid">', 1)[1].split("</div>", 1)[0]
    assert 'id="screenSourceSelect"' in role_pair and 'id="cameraSourceSelect"' in role_pair
    assert 'id="audioSourceSelect"' in routing and 'id="firstSlotSelect"' in routing
    assert ".source-role-grid { display:grid; gap:12px; min-width:0; }" in CSS
    assert "repeat(auto-fit,minmax(min(100%,170px),1fr))" in CSS
    assert ".source-role-grid select { width:100%; min-width:0; max-width:100%;" in CSS
    assert "white-space:normal; overflow-wrap:anywhere;" in CSS


def test_single_combined_source_has_manual_embedded_camera_fallback():
    for element_id in (
        "embeddedCameraEditor", "embeddedCameraVideo", "embeddedCameraRect", "embeddedCameraPresets",
        "embeddedCameraX", "embeddedCameraY", "embeddedCameraW", "embeddedCameraH",
        "embeddedContentX", "embeddedContentY", "saveEmbeddedCamera", "disableEmbeddedCamera",
    ):
        assert f'id="{element_id}"' in HTML

    candidate = function_block(APP, "embeddedCameraCandidate", "embeddedCameraIsActive")
    assert "state.project?.manual?.embedded_camera" in candidate
    assert "state.project?.pre_analysis?.vision?.A" in candidate
    assert "state.system?.vision_analysis_version || EMBEDDED_CAMERA_DETECTOR_VERSION" in candidate
    assert "const preparedVisionIsCurrent = sourceGeneration" in candidate
    assert "preparedVisionIsCurrent" in candidate
    assert "analyzedVisionIsCurrent" in candidate
    assert "analyzedVision?.version === detectorVersion" in candidate
    assert "analyzedVisionIsCurrent" in candidate and "preparedVisionIsCurrent ? preparedVision : null" in candidate
    active = function_block(APP, "embeddedCameraIsActive", "embeddedEditorCandidateKey")
    assert "if (!embeddedCameraCandidate()) return false" in active
    assert "if (state.project?.draft) return embeddedLayoutConfirmed()" in active
    assert 'state.project?.settings?.layout === "embedded_stack"' in active
    editor = function_block(APP, "renderEmbeddedCameraEditor", "bindEmbeddedCameraEditorEvents")
    assert "!source || hasB" in editor
    assert "sourceMediaUrl(source)" in editor
    assert "embeddedCameraIsActive()" in editor
    save = function_block(APP, "saveEmbeddedCameraSelection", "disableEmbeddedCameraSelection")
    assert 'queueEmbeddedCameraSave({ immediate: true })' in save
    save = function_block(APP, "flushEmbeddedCameraSave", "embeddedEditorGeometryFromControls")
    assert 'applyManualEdit("set_embedded_camera"' in save
    assert "enabled: true" in save
    assert "content_x" in save and "content_y" in save
    disable = function_block(APP, "disableEmbeddedCameraSelection", "setupPreviewSources")
    assert 'applyManualEdit("set_embedded_camera", { enabled: false })' in disable
    manual = function_block(APP, "applyManualEdit", "beginTranscriptEdit")
    assert 'action === "set_embedded_camera"' in manual
    assert ".embedded-camera-rect" in CSS


def test_embedded_camera_suggestion_refreshes_before_long_proxy_finishes():
    polling = function_block(APP, "pollJob", "updateJobUI")
    assert "!options.visionRefreshed" in polling
    assert 'Number(job.progress || 0) >= 0.075' in polling
    assert 'String(options.slot).toUpperCase() === "A"' in polling
    assert 'console.warn("Camera detection refresh failed"' in polling
    assert "renderSources()" in polling


def test_two_source_uploads_have_independent_slot_state_progress_and_cancel():
    assert "activeUploads: new Map()" in APP
    assert "activeUpload: null" not in APP
    upload = function_block(APP, "uploadSource", "uploadWithProgress")
    assert "uploadStateKey(projectId, slot)" in upload
    assert "state.activeUploads.set(uploadKey, uploadState)" in upload
    assert "state.activeUploads.get(uploadKey) !== uploadState" in upload
    assert "state.activeUploads.delete(uploadKey)" in upload
    assert 'acquireJobStartLock("upload"' not in upload
    cancel = function_block(APP, "cancelUpload", "requestUploadCancellation")
    assert "activeUploadForSlot(slot)" in cancel
    assert "activeUploadsForProject()" in cancel
    assert "for (const upload of cancellable)" in cancel
    renderer = function_block(APP, "renderSources", "renderReadiness")
    assert "activeUploadForSlot(slot)" in renderer


def test_source_mixer_saves_are_optimistic_serial_and_keep_first_slot():
    payload = function_block(APP, "sourceMixerPayload", "applyOptimisticSourceMixer")
    optimistic = function_block(APP, "applyOptimisticSourceMixer", "persistSourceMixer")
    save = function_block(APP, "saveSourceMixer", "clearPendingSourceSync")
    mixer = function_block(APP, "sourceMixerSettings", "sourceMixerLayoutFromSetting")

    assert "first_slot: elements.firstSlotSelect.value" in payload
    assert "first_slot: payload.first_slot" in optimistic
    assert "sourceMixerSaveSequence" in save
    assert "state.sourceMixerSaveTail.catch" in save
    assert "state.sourceMixerDesired" in save
    assert "applyOptimisticSourceMixer(payload)" in save
    assert "desired.version > version" in save
    assert "firstSlot" in mixer and 'raw.first_slot || ""' in mixer
    assert 'id="firstSlotSelect"' in HTML


def test_pre_director_mixer_has_a_live_generation_versioned_composition_preview():
    preview = function_block(APP, "renderSourceCompositionPreview", "renderSourceMixer")
    media = function_block(APP, "sourceMediaUrl", "renderUploadLimits")
    sources = function_block(APP, "setupPreviewSources", "togglePreview")

    assert "sourceCompositionRoleA" in preview
    assert "sourceCompositionNameB" in preview
    assert "composition-${visualLayout}" in preview
    assert "first-slot-${mixer.firstSlot.toLowerCase()}" in preview
    assert "source?.generation" in media
    assert "generation=${encodeURIComponent(generation)}" in media
    assert "sourceMediaUrl(sourceA)" in sources
    assert "elements.previewA.load()" in sources
    assert ".source-composition-canvas.composition-stacked.first-slot-a" in CSS
    assert ".source-composition-canvas.composition-side_by_side.first-slot-b" in CSS


def test_post_draft_layout_choice_is_immediately_committed_not_preview_only():
    bindings = function_block(APP, "bindEvents", "installDropZone")
    apply_layout = function_block(APP, "applySourceLayout", "embeddedLayoutConfirmed")
    renderer = function_block(APP, "renderSourceMixer", "renderSceneLayoutEditor")

    assert 'await applySourceLayout(state.manualSelection ? "selection" : "all", { immediate: true })' in bindings
    assert "state.sourceMixerPreviewLayout = button.dataset.layout" not in bindings
    assert "state.sourceMixerCommitScope = scope" in apply_layout
    assert "Layout saved immediately" in apply_layout
    assert "Choosing a layout applies and saves it immediately" in renderer
    assert "Preview only" not in renderer


def test_explicit_source_layout_is_separate_from_style_defaults_and_survives_reload():
    hydrate = function_block(APP, "hydrateSettings", "applyGoalMode")
    mixer = function_block(APP, "sourceMixerSettings", "sourceSlotForRole")
    bindings = function_block(APP, "bindEvents", "installDropZone")
    renderer = function_block(APP, "renderSourceMixer", "placeSourceMixer")

    assert "hydrateSourceMixerLayout()" in hydrate
    assert "mixer.defaultLayoutExplicit" in mixer
    assert "const plan = editorProject()?.draft?.camera_plan" in mixer
    assert "defaultLayoutField.hidden = hasSecondSource" in hydrate
    assert "elements.layoutSelect.value = explicitLayout" not in hydrate
    assert 'Object.hasOwn(raw, "default_layout")' in mixer
    assert "default_layout: null" in bindings
    assert "Style default controls the layout again" in bindings
    assert "mixer.defaultLayoutExplicit" in renderer
    assert "Saved AI choice will be used by Director" in renderer


def test_audio_calibration_follows_the_user_selected_audio_source():
    profile = function_block(APP, "preAudioProfile", "hydratePreAudioControls")
    calibration = function_block(APP, "renderAudioCalibration", "setChoiceValue")
    readiness = function_block(APP, "renderReadiness", "uploadSource")

    assert "sourceMixerSettings().audioSlot" in profile
    assert "pre_analysis?.audio?.[slot]" in profile
    assert "analysis?.audio_source" in profile
    assert "sources?.[audioSlot]" in calibration
    assert "!source?.has_audio" in calibration
    assert "sources?.[audioSlot]" in readiness


def test_source_sync_and_manual_edits_flush_before_navigation_or_new_work():
    sync = function_block(APP, "flushPendingSourceSync", "scheduleSourceSyncSave")
    flush = function_block(APP, "flushCurrentProjectSaves", "foregroundBusy")
    manual = function_block(APP, "applyManualEdit", "beginTranscriptEdit")

    assert "sourceSyncPending" in APP
    assert "saveSourceMixer({ sync_offset: pending.value })" in sync
    assert "await state.manualEditPromise" in flush
    assert "await flushPendingSourceSync(projectId)" in flush
    assert "manualEditPromise" in manual
    assert "finishManualEdit()" in manual
    assert "state.manualEditBusy" in function_block(APP, "foregroundBusy", "projectHasForegroundWork")


def test_two_source_preview_uses_roles_and_matches_export_order_in_rtl():
    preview = function_block(APP, "syncSecondaryPreview", "cameraAt")
    assert "sourceMixerSettings()" in preview
    assert "screen-slot-" in preview
    assert "primary-" in preview
    assert "first-slot-" in preview
    assert "--stack-first-share" in preview
    assert "pip-inset-" in preview
    assert "needsBPlayback" in preview
    assert 'mixer.audioSlot === "B"' in preview
    assert "mixer.syncOffset" in preview
    camera = function_block(APP, "cameraAt", "seekPreview")
    assert "sourceMixerPreviewLayout" in camera
    assert "ai_camera_plan" in camera
    assert '[dir="rtl"] .preview-stage.layout-side_by_side' not in CSS
    assert '[dir="rtl"] .preview-stage.layout-pip' not in CSS


def test_stale_caption_export_has_a_localized_rebuild_message():
    assert "function friendlyRenderError" in APP
    assert 'value === "captions_out_of_date"' in APP
    assert "בנו את ה־Draft מחדש" in APP


def test_studio_is_task_oriented_and_caption_controls_are_real_settings():
    for label in ("Edit", "Layout", "Captions", "Output"):
        assert f"<span>{label}</span>" in HTML
    for element_id in (
        "studioBurnCaptionsToggle",
        "captionsToggle",
        "spokenLanguageSelect",
        "captionStyleSelect",
        "captionPositionSelect",
        "captionScale",
        "captionWordsPerLine",
        "captionLanguageStatus",
    ):
        assert f'id="{element_id}"' in HTML

    current = function_block(APP, "currentSettings", "scheduleSettingsPatch")
    for setting in (
        "burn_captions",
        "captions",
        "caption_style",
        "caption_position",
        "caption_scale",
        "caption_words_per_line",
        "spoken_language",
    ):
        assert setting in current
    assert "function renderCaptionControls" in APP
    assert "captionPreviewText" in APP
    assert 'data-caption-style="boxed"' in CSS
    assert 'data-caption-position="center"' in CSS


def test_spoken_language_feedback_uses_backend_confidence_without_changing_ui_locale():
    detection = function_block(APP, "renderLanguageDetectionStatus", "applyGoalMode")
    assert "evidence.language_probability" in detection
    assert "transcript.discarded_quality" in detection
    assert "confidence < 0.62" in detection
    assert "detection.ambiguous === true" in detection
    assert 'requested !== "auto"' in detection
    assert "detection.requested_language" in detection
    assert "languageName(requested)" in detection
    assert "Low confidence" in detection
    assert "Language locked" in detection
    assert "Language selected:" in detection
    assert "Rebuild the draft to apply." in detection
    assert "Auto-detect selected" in detection
    assert "Detected:" in detection
