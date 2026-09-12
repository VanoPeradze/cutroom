from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
I18N = (ROOT / "web" / "i18n.js").read_text(encoding="utf-8")


def test_upload_is_a_foreground_operation_with_a_real_abort_path():
    assert "activeUploads: new Map()" in APP
    assert "function uploadStartBlocked(projectId, slot)" in APP
    assert "activeUploadForSlot(slot, projectId)" in APP
    assert "upload.xhr?.abort()" in APP
    assert 'xhr.addEventListener("abort"' in APP
    assert "state.activeJob || state.activeUploads.size" in APP
    assert 'xhr.setRequestHeader("X-Cutroom-Upload-Token", uploadToken)' in APP
    assert "/uploads/${encodeURIComponent(upload.uploadToken)}/cancel" in APP
    assert "requestUploadCancellation(upload)" in APP
    assert "await uploadState.cancelPromise" in APP
    assert "if (uploadState.cancelRequested)" in APP


def test_each_source_upload_has_an_accessible_cancel_control():
    assert 'id="cancelUploadA"' in HTML
    assert 'id="cancelUploadB"' in HTML
    assert HTML.count('data-i18n="stopProcess"') >= 2
    assert 'elements[`cancelUpload${slot}`].addEventListener("click"' in APP


def test_upload_progress_is_scoped_to_the_visible_project():
    assert "activeUploadForSlot(slot)" in APP
    assert "if (state.project?.id === projectId)" in APP
    assert "state.activeUploads.get(uploadKey) === uploadState" in APP
    assert "state.activeUploads.delete(uploadKey)" in APP


def test_upload_status_copy_exists_in_primary_languages():
    assert I18N.count('activeUpload: "') >= 2
    assert I18N.count('uploadCancelled: "') >= 2


def test_render_storage_failure_is_actionable_and_localized():
    assert 'error?.code === "insufficient_storage"' in APP
    assert 't("notEnoughRenderDisk")' in APP
    assert I18N.count('notEnoughRenderDisk: "') >= 2


def test_destructive_source_actions_are_blocked_while_project_work_is_active():
    assert "function projectHasForegroundWork(projectId)" in APP
    assert "if (projectHasForegroundWork(state.project.id))" in APP
    assert "if (projectHasForegroundWork(project.id))" in APP


def test_async_ui_entry_points_report_failures_instead_of_leaking_rejections():
    assert "function runUiAction(action, context = \"\")" in APP
    assert "runUiAction(() => uploadSource(slot, file)" in APP
    assert "runUiAction(() => openProject(project.id))" in APP
    assert "runUiAction(() => deleteProject(project))" in APP


def test_revision_conflicts_refresh_and_retry_without_sticking_the_editor():
    assert "function isRevisionConflict(error)" in APP
    assert "queue.conflictRetries < 2" in APP
    assert "if (retryAfterConflict) return flushProjectSaves(projectId)" in APP
    assert "payload = await submit(expectedRevision)" in APP
    assert "payload = await submit(saveQueueFor(projectId, state.project.revision).revision)" in APP


def test_export_polling_survives_local_server_restarts_and_interrupted_jobs():
    export_poll = APP.split("function pollExportJob", 1)[1].split("function renderModelStatus", 1)[0]
    assert '["failed", "interrupted"].includes(job.status)' in export_poll
    assert "/jobs/active" in export_poll
    assert "consecutivePollFailures >= 4" in export_poll
    assert "Keep waiting: a local server restart" in export_poll
    assert "Math.min(5000" in export_poll


def test_export_results_do_not_leak_into_a_different_open_project():
    completion = APP.split("async function completeExportJob", 1)[1].split("function pollExportJob", 1)[0]
    assert "const projectIsVisible = state.project?.id === projectId" in completion
    assert "if (projectIsVisible)" in completion
    assert "if (projectIsVisible && state.project?.id === projectId)" in completion
    assert "latestExport?.url && latestExport?.name" in APP


def test_primary_preview_pause_always_stops_the_secondary_source():
    assert 'elements.previewA.addEventListener("pause", stopPreviewPlayback)' in APP
    assert 'elements.previewA.addEventListener("ended", stopPreviewPlayback)' in APP
    stopped = APP.split("function stopPreviewPlayback", 1)[1].split("function pauseAllMedia", 1)[0]
    assert "state.preview.playRequest += 1" in stopped
    assert "elements.previewB?.pause()" in stopped
    assert "setPreviewPlaying(false)" in stopped


def test_media_pause_is_centralized_and_invalidates_stale_play_requests():
    pause_all = APP.split("function pauseAllMedia", 1)[1].split("function setPreviewPlaying", 1)[0]
    assert "state.preview.playRequest += 1" in pause_all
    assert 'document.querySelectorAll("video, audio")' in pause_all
    assert "media.pause()" in pause_all
    assert "setPreviewPlaying(false)" in pause_all

    play = APP.split("async function playPreview", 1)[1].split("function pausePreview", 1)[0]
    assert "const playRequest = ++state.preview.playRequest" in play
    assert "playRequest !== state.preview.playRequest || elements.previewA.paused" in play
    assert "syncSecondaryPreview(elements.previewA.currentTime)" in play


def test_jobs_and_view_navigation_pause_every_media_element():
    lifecycle_sections = [
        ("async function goHome", "function showWorkspace"),
        ("async function openProject", "function hydrateProject"),
        ("async function generateDraft", "async function ensureStoryAIReady"),
        ("async function refineDraft", "function showSetup"),
        ("function showSetup", "function showAnalysis"),
        ("function showAnalysis", "function friendlyDirectorError"),
        ("function showResult", "async function monitorBackgroundJob"),
        ("async function rebuildDraftFromStudio", "function updateStudioStatus"),
        ("function openExportDialog", "async function startExport"),
        ("async function startExport", "function friendlyRenderError"),
    ]
    for start, end in lifecycle_sections:
        section = APP.split(start, 1)[1].split(end, 1)[0]
        assert "pauseAllMedia();" in section, start


def test_reel_alternatives_refresh_when_a_job_start_lock_is_released():
    release = APP.split("function releaseJobStartLock", 1)[1].split("function setActiveJob", 1)[0]
    assert "state.jobStartLocks.delete(key)" in release
    assert "renderReelCandidates();" in release
