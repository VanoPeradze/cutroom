from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_required_release_files_exist():
    required = [
        "server.py", "config.json", "requirements.txt", "run_windows.bat", "repair_windows.bat",
        "setup_windows.ps1", "verify_windows_installer.ps1",
        "run_linux.sh", "setup_linux.sh", "web/index.html", "web/styles.css", "web/app.js", "web/i18n.js", "web/timeline.js", "web/audio-meter.js",
        "cutroom/director.py", "cutroom/intelligence.py", "cutroom/transcription.py", "cutroom/render.py", "cutroom/audio.py",
        "README_HE.md", "LICENSE", "THIRD_PARTY_NOTICES.md",
    ]
    assert not [item for item in required if not (ROOT / item).is_file()]


def test_html_ids_are_unique_and_javascript_references_exist():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    cache_match = re.search(r"function cacheElements\(\) \{\s*\[\s*(.*?)\s*\]\.forEach\(\(id\)", app, re.S)
    assert cache_match is not None
    references = set(re.findall(r'"([A-Za-z][A-Za-z0-9_-]+)"', cache_match.group(1)))
    assert references <= set(ids)


def test_scroll_is_not_locked():
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    assert "overflow-y: auto" in css
    assert "body {" in css
    assert "overflow: hidden" not in css.split("body {", 1)[1].split("}", 1)[0]


def test_render_button_is_in_topbar():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    topbar = html.split('<header class="topbar">', 1)[1].split("</header>", 1)[0]
    assert 'id="renderButton"' in topbar


def test_director_is_primary_and_advanced_is_hidden():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert 'id="generateButton"' in html
    assert 'id="advancedPanel" hidden' in html
    assert "One main edit plus ranked Reel options from the same analysis" in html


def test_interface_is_english_only_while_spoken_language_remains_selectable():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert '<html lang="en" dir="ltr">' in html
    assert 'id="languageSelect"' not in html
    assert '"languageSelect"' not in app
    assert not re.search(r"[\u0590-\u08ff\u0400-\u04ff]", html)
    assert 'id="spokenLanguageSelect"' in html
    for language in ("Auto-detect", "Hebrew", "English", "Arabic", "Spanish", "French", "Russian"):
        assert language in html


def test_studio_keeps_live_preview_and_tools_in_one_viewport():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert 'id="studioPreviewDock"' in html
    assert 'id="previewColumn"' in html
    assert 'id="resultGrid"' in html
    assert 'id="verdictColumn"' in html
    assert 'id="studioRenderButton"' in html
    assert 'position: fixed' in css.split('/* === CUTROOM 5.3', 1)[1]
    assert 'body.studio-open { overflow: hidden; }' in css
    assert 'elements.studioPreviewDock.appendChild(previewColumn)' in app
    assert 'elements.resultGrid.insertBefore(previewColumn' in app
    advanced = app.split('function setAdvanced(open)', 1)[1].split('function updateStudioStatus', 1)[0]
    assert 'scrollIntoView' not in advanced
    assert 'document.body.classList.add("studio-open")' in advanced
    assert 'document.body.classList.remove("studio-open")' in advanced


def test_windows_installers_are_ascii_crlf_and_parser_safe():
    for name in ("setup_windows.ps1", "verify_windows_installer.ps1", "run_windows.bat", "repair_windows.bat"):
        payload = (ROOT / name).read_bytes()
        assert payload
        assert all(value < 128 for value in payload), f"{name} contains non-ASCII bytes"
        assert b"\r\n" in payload
        assert b"\n" not in payload.replace(b"\r\n", b"")

    setup = (ROOT / "setup_windows.ps1").read_text(encoding="ascii")
    assert "\u2014" not in setup
    assert "\u201c" not in setup
    assert "\u201d" not in setup
    assert _balanced_powershell_delimiters(setup)


def test_windows_launcher_checks_setup_marker_environment_and_real_parser():
    launcher = (ROOT / "run_windows.bat").read_text(encoding="ascii")
    verifier = (ROOT / "verify_windows_installer.ps1").read_text(encoding="ascii")
    preflight = (ROOT / "scripts" / "preflight.py").read_text(encoding="utf-8")
    assert 'if not exist ".setup-complete"' in launcher
    assert 'CUTROOM AI 5.6.1 setup completed' in launcher
    assert 'if not exist ".venv\\Scripts\\python.exe"' in launcher
    assert "verify_windows_installer.ps1" in launcher
    assert '"scripts\\preflight.py"' in launcher
    for dependency in ("flask", "waitress", "faster_whisper", "cutroom", "FFmpeg", "FFprobe"):
        assert dependency in preflight
    assert "System.Management.Automation.Language.Parser" in verifier
    assert "setup_windows.ps1" in verifier
    assert "$errors.Count" in verifier
    assert (ROOT / "repair_windows.bat").is_file()


def test_linux_setup_resolves_supported_python_and_verifies_the_runtime_before_success():
    setup = (ROOT / "setup_linux.sh").read_text(encoding="utf-8")
    launcher = (ROOT / "run_linux.sh").read_text(encoding="utf-8")
    assert "python3.12 python3.11 python3" in setup
    assert "command -v ffprobe" in setup
    assert ".venv/bin/python scripts/preflight.py" in setup
    assert setup.index("scripts/preflight.py") < setup.index(".setup-complete")
    assert ".venv/bin/python scripts/preflight.py" in launcher



def _assert_ascii_crlf(path: Path) -> bytes:
    payload = path.read_bytes()
    assert payload
    assert all(byte < 128 for byte in payload), f"{path.name} must remain ASCII-safe for Windows PowerShell 5.1"
    assert b"\r\n" in payload
    assert payload.replace(b"\r\n", b"").find(b"\n") == -1
    return payload


def _balanced_powershell_delimiters(source: str) -> bool:
    pairs = {')': '(', ']': '[', '}': '{'}
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    comment = False
    for character in source:
        if comment:
            if character in "\r\n":
                comment = False
            continue
        if quote is not None:
            if escaped:
                escaped = False
                continue
            if character == '`':
                escaped = True
                continue
            if character == quote:
                quote = None
            continue
        if character == '#':
            comment = True
            continue
        if character in {"'", '"'}:
            quote = character
            continue
        if character in "([{":
            stack.append(character)
        elif character in ")]}":
            if not stack or stack.pop() != pairs[character]:
                return False
    return quote is None and not stack


def test_windows_installer_is_ascii_safe_and_self_validating():
    setup = _assert_ascii_crlf(ROOT / "setup_windows.ps1")
    validator = _assert_ascii_crlf(ROOT / "verify_windows_installer.ps1")
    launcher = _assert_ascii_crlf(ROOT / "run_windows.bat")
    repair = _assert_ascii_crlf(ROOT / "repair_windows.bat")

    setup_text = setup.decode("ascii")
    assert _balanced_powershell_delimiters(setup_text)
    assert _balanced_powershell_delimiters(validator.decode("ascii"))
    assert "System.Management.Automation.Language.Parser" in validator.decode("ascii")
    assert "verify_windows_installer.ps1" in launcher.decode("ascii")
    assert "verify_windows_installer.ps1" in repair.decode("ascii")
    assert b"cuda_v12\\cublas64_12.dll" in launcher
    assert b"%ProgramFiles%\\Ollama" in launcher
    assert b"cuda_v12" in setup
    assert b"cublas64_12.dll" in setup
    assert 'if not exist ".setup-complete"' in launcher.decode("ascii")
    assert r'if not exist ".venv\Scripts\python.exe"' in launcher.decode("ascii")
    assert "Resolve-SystemPython" in setup_text
    assert "uv-x86_64-pc-windows-msvc.zip" in setup_text
    assert "uv-aarch64-pc-windows-msvc.zip" in setup_text
    assert "uv-i686-pc-windows-msvc.zip" in setup_text
    assert "UV_PYTHON_INSTALL_DIR" in setup_text
    assert "UV_SYSTEM_CERTS" in setup_text
    assert '"python", "install"' in setup_text
    assert '"venv", "--clear"' in setup_text
    assert "Gyan.FFmpeg" in setup_text
    assert "Ollama.Ollama" in setup_text
    assert 'UV_PYTHON_PREFERENCE = "only-managed"' not in setup_text
    assert "--managed-python" not in setup_text
    assert 'UV_NATIVE_TLS = "true"' not in setup_text
    assert b"\xe2\x80\x94" not in setup


def test_windows_bootstrap_uses_v3_path_then_safe_private_fallback():
    setup = (ROOT / "setup_windows.ps1").read_text(encoding="ascii")
    assert '$script:UvVersion = "0.12.5"' in setup
    assert "Resolve-SystemPython" in setup
    assert "Python through py.exe" in setup
    expected_assets = {
        "uv-x86_64-pc-windows-msvc.zip": "4c4d49d8738847d9b71ba319e49a5688c93eac0fe6204b1df24e98528dddf39a",
        "uv-aarch64-pc-windows-msvc.zip": "724279317fee6e5fa8ad1908e4eba2bbe764ef1ece5b3f4597927b62b1fe562a",
        "uv-i686-pc-windows-msvc.zip": "a5993a7c2e75b418e60d5ed733204222330085b14e85269545b084c273c1629b",
    }
    for filename, digest in expected_assets.items():
        assert filename in setup
        assert digest in setup
    assert "Get-FileHash" in setup
    assert r'Join-Path $PSScriptRoot ".tools\python"' in setup
    assert "--managed-python" not in setup
    assert "UV_PYTHON_PREFERENCE" in setup  # explicitly removed from inherited environments
    assert 'Remove-Item Env:UV_PYTHON_PREFERENCE' in setup


def test_windows_launcher_restores_runtime_paths_and_exposes_setup_logs():
    launcher = (ROOT / "run_windows.bat").read_text(encoding="ascii")
    repair = (ROOT / "repair_windows.bat").read_text(encoding="ascii")
    setup = (ROOT / "setup_windows.ps1").read_text(encoding="ascii")
    assert 'if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"' in launcher
    assert 'if exist ".runtime-paths.cmd" call ".runtime-paths.cmd"' in repair
    assert "setup-last-error.txt" in launcher
    assert "setup-windows.log" in launcher
    assert "Write-RuntimePaths" in setup
    assert "Microsoft\\WinGet\\Packages" in setup



def test_missing_projects_are_expected_404s_and_last_project_is_instance_scoped():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    assert '@app.errorhandler(FileNotFoundError)' in server
    handler = server.split('@app.errorhandler(FileNotFoundError)', 1)[1].split('@app.errorhandler(Exception)', 1)[0]
    assert '"error": "not_found"' in handler
    assert '404' in handler
    assert 'app.logger.exception' not in handler
    assert '"instance_id": instance_id' in server
    assert 'hashlib.sha256(str(settings.data_dir.resolve())' in server
    assert 'function lastProjectStorageKey()' in app_js
    assert '`cutroom-last-project:${instance}`' in app_js
    assert 'state.projectsLoaded && !state.projects.some' in app_js
    assert 'error?.status === 404' in app_js
    assert 'localStorage.removeItem("cutroom-last-project")' in app_js


def test_upload_limit_has_explicit_client_side_error():
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    assert "file.size" in app_js and "maxUploadBytes" in app_js
    assert 't("fileTooLarge")' in app_js
    assert 'new Error("Network error")' not in app_js
    assert html.count("data-upload-limit") == 2


def test_director_loader_is_simple_and_animated():
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "web" / "styles.css").read_text(encoding="utf-8")
    assert 't("directorPreparing")' in app_js
    update_job_ui = app_js.split("function updateJobUI", 1)[1].split("async function requestJobCancellation", 1)[0]
    assert 'String(job.message || "").trim()' in update_job_ui
    assert 't("taskStory")' in update_job_ui  # A stage fallback remains for jobs with no detail.
    assert html.count('class="analysis-checks"') == 1
    assert html.count('data-threshold=') == 4
    assert "@keyframes orbit" in css and "@keyframes directorPulse" in css


def test_server_returns_explicit_upload_limit_and_disk_errors():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "RequestEntityTooLarge" in server
    assert server.index("if isinstance(error, RequestEntityTooLarge)") < server.index("if isinstance(error, HTTPException)")
    assert '"error": "file_too_large"' in server
    assert '"error": "insufficient_storage"' in server
    assert 'disk_free_bytes' in server


def test_waitress_transport_limit_matches_cutroom_upload_limit():
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "max_request_body_size=request_body_limit" in server
    assert 'app.config.get("MAX_CONTENT_LENGTH")' in server
    assert "channel_timeout=3600" in server
    assert "transport_request_body_bytes" in server
    # Waitress defaults to 1 GiB; CUTROOM must override it because the product limit is much larger.
    assert "serve(app, host=host, port=port, threads=8, channel_timeout=300)" not in server


def test_background_preparation_does_not_block_director_button():
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    upload_block = app_js.split("async function uploadSource", 1)[1].split("function uploadWithProgress", 1)[0]
    assert 'monitorBackgroundJob(payload.job.id' in upload_block
    assert 'pollJob(payload.job.id' not in upload_block
    assert 'const blocking = !options.background' in app_js
    assert 'if (blocking) {' in app_js


def test_story_model_is_required_before_semantic_director_runs():
    app_js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    intelligence = (ROOT / "cutroom/intelligence.py").read_text(encoding="utf-8")
    generate = app_js.split("async function generateDraft()", 1)[1].split("async function ensureStoryAIReady", 1)[0]
    assert "await ensureStoryAIReady(settings.goal);" in generate
    assert generate.index("await flushProjectSaves(projectId)") < generate.index("const settings = currentSettings()")
    assert '"story_ai_required"' in server
    assert "def story_ai_status" in intelligence
    assert "StoryAIUnavailableError" in intelligence
    assert "deterministic_story" not in intelligence.split("def plan_edit", 1)[1]


def test_job_manager_separates_background_and_foreground_work():
    jobs = (ROOT / "cutroom" / "jobs.py").read_text(encoding="utf-8")
    assert 'BACKGROUND_KINDS = {"prepare_source", "model_install"}' in jobs
    assert 'self.background_executor' in jobs
    assert 'executor = self.background_executor if kind in self.BACKGROUND_KINDS else self.executor' in jobs


def test_director_uses_honest_evidence_fallback_when_transcription_fails():
    director = (ROOT / "cutroom" / "director.py").read_text(encoding="utf-8")
    assert "def _transcribe_safely" in director
    assert "def _clearly_sparse_transcript" in director
    assert 'if goal == "short":' in director
    assert 'elif goal in {"youtube", "clean"}:' in director
    assert '"segments": []' in director
    assert '"type": "transcript_fallback"' in director
    assert '"partial_ai": bool(transcription_warning or nonverbal_highlights or transcript_fallback or quality_review["needs_review"])' in director
    assert "_assert_transcript_complete(transcript_quality)" in director
    assert 'engine = "audio_visual_highlights"' in director


def test_director_commit_preserves_concurrent_source_preparation_updates():
    director = (ROOT / "cutroom" / "director.py").read_text(encoding="utf-8")
    assert "def commit_analysis(latest" in director
    assert 'latest["analysis"] = analysis' in director
    assert 'latest["draft"] = draft' in director
    assert "store.update(project_id, commit_analysis)" in director
    assert "project_changed_during_analysis" in director


def test_audio_first_release_contract():
    config = (ROOT / "config.json").read_text(encoding="utf-8")
    director = (ROOT / "cutroom/director.py").read_text(encoding="utf-8")
    audio = (ROOT / "cutroom/audio.py").read_text(encoding="utf-8")
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert '"editor_model": "qwen3.5:4b"' in config
    assert '"job_workers": 1' in config
    assert '"ffmpeg_threads": 4' in config
    assert director.index("analyze_audio(") < director.index("plan_edit(")
    assert "audio_policy" in director and "audio_plan" in director
    assert 'id="audioPresetChoices"' in html
    assert 'id="spokenLanguageSelect"' in html
    assert 'id="performanceModeSelect"' in html
    assert "currentAudioSettings" in app
    assert "noise_floor_dbfs" in audio and "quiet_speech" in audio and "loud_speech" in audio


def test_language_autodetection_requires_real_evidence():
    source = (ROOT / "web/i18n.js").read_text(encoding="utf-8")
    assert "total < 4" in source
    assert "amount / Math.max(1,total) < 0.64" in source
    assert "amount < 12" in source
    assert 'element.dir = "auto"' in source


def test_transcription_profiles_are_bounded():
    config = (ROOT / "config.json").read_text(encoding="utf-8")
    transcription = (ROOT / "cutroom/transcription.py").read_text(encoding="utf-8")
    assert '"lite": "base"' in config
    assert '"balanced": "small"' in config
    assert '"quality": "turbo"' in config
    assert 'mode == "lite"' in transcription
    assert "preferred_device, preferred_compute = _resolve_device(settings, mode)" in transcription
    assert '"whisper_isolate_process": true' in config
    assert "_run_transcription_worker" in transcription
    assert 'attempts.append(("cpu", "int8"))' in transcription


def test_v52_outcome_first_ui_and_timeline_contract():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    timeline = (ROOT / "web/timeline.js").read_text(encoding="utf-8")
    advanced = html.split('id="advancedPanel"', 1)[1] if 'id="advancedPanel"' in html else ""
    assert 'data-value="short"' in html and 'data-value="youtube"' in html
    assert 'id="goalExplainer"' in html and 'id="durationGroup"' in html
    assert 'id="paceChoices"' in advanced and 'id="audioPresetChoices"' in advanced
    assert 'elements.durationGroup.hidden = ["youtube", "clean"].includes(normalized)' in app
    assert 'youtube: { aspect: "16:9", layout: "A"' in app
    assert 'short: { aspect: "9:16", layout: "auto"' in app
    assert 'analysis?.audio?.waveform' in timeline
    assert 'handleWheel(event)' in timeline and 'followPlayhead()' in timeline
    assert 'this.scrubbing = true' in timeline


def test_v52_goal_specific_director_contract():
    director = (ROOT / "cutroom/director.py").read_text(encoding="utf-8")
    intelligence = (ROOT / "cutroom/intelligence.py").read_text(encoding="utf-8")
    vision = (ROOT / "cutroom/vision.py").read_text(encoding="utf-8")
    assert 'def _enforce_short_target' in director
    assert 'youtube_cleanup_only' in director
    assert '"max_remove_ratio": max(float(policy.get("max_remove_ratio", 0.28)), 0.92)' in director
    assert 'camera": "embedded_stack"' in director
    assert 'def compact_segments_for_llm' in intelligence
    assert 'position": round(float(item.get("start", 0))' in intelligence
    assert '"layout_hint": "embedded_stack"' in vision
    assert '"content_focus"' in vision


def test_preview_reports_edited_duration_and_maps_output_seek_to_source():
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert "function editDuration()" in app
    edit_duration = app.split("function editDuration()", 1)[1].split("function sourceToOutputTime", 1)[0]
    assert "const project = editorProject()" in edit_duration
    assert "project?.draft?.output_duration" in edit_duration
    assert "function sourceToOutputTime" in app
    assert "function outputToSourceTime" in app
    preview = app.split("function updatePreviewUI(time)", 1)[1].split("function updatePreviewCaption", 1)[0]
    assert "const project = playbackProject()" in preview
    assert "const sourceMode = previewUsesSourceTime()" in preview
    assert 'sourceMode ? Number(project?.sources?.A?.duration || 0) : editDuration()' in preview
    assert 'sourceMode ? time : sourceToOutputTime(time)' in preview
    assert "sourceToOutputTime(time)" in preview
    seek_handler = app.split('elements.previewSeek.addEventListener("input"', 1)[1].split("});", 1)[0]
    assert "outputToSourceTime" in seek_handler


def test_primary_flow_exposes_real_db_cut_line_and_burned_captions():
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    meter = (ROOT / "web/audio-meter.js").read_text(encoding="utf-8")
    assert 'id="audioCalibration"' in html
    assert 'id="audioMeterCanvas"' in html
    assert 'id="silenceThreshold"' in html
    assert 'id="preSilenceMin"' in html
    assert 'id="preSilenceKeep"' in html
    assert 'id="burnCaptionsToggle"' in html
    assert "silence_threshold_dbfs" in app
    assert "cutroom-audio-seek" in meter and "cutroom-audio-seek" in app
    assert "rms_dbfs" in meter and "peak_dbfs" in meter


def test_release_includes_audio_meter_module():
    assert (ROOT / "web/audio-meter.js").is_file()


def test_v55_single_file_reel_and_story_director_contract():
    config = (ROOT / "config.json").read_text(encoding="utf-8")
    vision = (ROOT / "cutroom/vision.py").read_text(encoding="utf-8")
    render = (ROOT / "cutroom/render.py").read_text(encoding="utf-8")
    intelligence = (ROOT / "cutroom/intelligence.py").read_text(encoding="utf-8")
    transcription = (ROOT / "cutroom/transcription.py").read_text(encoding="utf-8")
    css = (ROOT / "web/styles.css").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    assert '"hebrew_whisper_model": "ivrit-ai/whisper-large-v3-turbo-ct2"' in config
    assert '"editor_quality_model": "qwen3.5:9b"' in config
    assert "def build_story_beats" in intelligence
    assert "def build_story_chapters" in intelligence
    assert "def _build_global_outline" in intelligence
    assert "def _build_story_plan" in intelligence
    assert "def _critic_story_selection" in intelligence
    assert "def hierarchical_story_edit" in intelligence
    assert '"story_ranges"' in intelligence
    assert "temporal_face_cluster" in vision
    assert '"facecam_position": "top"' in vision
    assert "[face{index}][content{index}]vstack" in render
    assert ".layout-embedded_stack #previewPaneB" in css
    assert ".preview-pane { position: absolute; inset: 0; overflow: hidden;" in css
    assert 'stage.classList.add("layout-embedded_stack")' in app
    assert "hebrew_refined" in transcription


def test_v56_hierarchical_story_contract():
    intelligence = (ROOT / "cutroom/intelligence.py").read_text(encoding="utf-8")
    director = (ROOT / "cutroom/director.py").read_text(encoding="utf-8")
    server = (ROOT / "server.py").read_text(encoding="utf-8")
    app = (ROOT / "web/app.js").read_text(encoding="utf-8")
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    assert "def _summarize_story_chapters" in intelligence
    assert "def _build_global_outline" in intelligence
    assert "def _build_story_plan" in intelligence
    assert "slot_selections" in intelligence
    assert "def _critic_story_selection" in intelligence
    assert "story_cache" in intelligence
    assert "ollama_hierarchical_story" in intelligence
    assert "StoryAIUnavailableError" in intelligence
    plan_tail = intelligence.split("def plan_edit", 1)[1]
    assert "deterministic_story" not in plan_tail
    assert "story_hierarchy" in director
    assert "story_ai_required" in server
    assert "await ensureStoryAIReady(settings.goal);" in app
    assert 'id="draftEngineBadge"' in html
