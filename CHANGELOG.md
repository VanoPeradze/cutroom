# Changelog

## 1.1 Beta — 2026-09-20

- Simplified the Windows download to one launcher, an offline quick-start guide and an App folder. Existing source checkouts and installations retain their original layout.
- Established **1.1 Beta** as the current public release label and `1.1-beta` as its technical version identifier.
- Updated launchers, setup markers, package filenames, source manifests and documentation to use the current version consistently.
- Added a compatible cloud API connection alongside Groq, with explicit destination consent and session keys bound to the selected provider and endpoint.
- Clarified Groq's free-tier quotas and optional provider billing, and added independent provider credit.
- Prevented pending cloud connections from sending after cancellation, and separated analysis caches by provider endpoint and selected models.
- Kept the earlier development record below with its original version numbers. This naming change does not represent a rollback of editing features or removal of legacy project compatibility.

## Historical development notes

The following entries describe earlier development builds and retain their original labels. They are historical records, not the current release version.

### Previously unreleased work

- Made the application interface English-only while keeping multilingual speech, transcript and caption support.
- Reorganized Studio into Cut, Layout, Captions and Output task areas.
- Added real caption controls for burn/SRT output, Clean/Bold/Boxed style, safe position, scale and words per caption, all honored by preview and render.
- Improved offline spoken-language detection with evidence from multiple recording windows, confidence aggregation and conservative Hebrew-script correction.
- Made ambiguous language evidence stay visibly low-confidence, preserved weak Yiddish instead of relabeling it, and kept auto-refinement from reporting false 100% confidence.
- Made project deletion atomic on Windows and released browser media handles first, preventing open source/export files from leaving a half-deleted project.

### Previously unreleased - Stabilization workspace

#### Fixed
- Made A and B independent upload lanes with per-source progress/cancel, while serializing project commits so simultaneous imports cannot overwrite one another.
- Replaced physical A/B Director decisions with semantic `screen`/`camera` roles; swapping the sources now changes the result without invalidating the Storyline.
- Added an explicit first-source control for stacked and split layouts, persisted it through refresh/Undo/Redo, and matched browser preview order to FFmpeg export order.
- Preserved valid routing when replacing source B, invalidated stale sync/crop data, and neutralized unreliable automatic offsets instead of moving footage outside the usable overlap.
- Added a manual embedded-camera rectangle for one-file recordings. It works before or after Draft creation and provides a safe fallback when face detection misses.
- Disabled separate Ollama thinking for structured Qwen Storyline passes; thinking-capable models can no longer exhaust `num_predict` and return an empty `message.content`.
- Checkpointed transcript/audio/vision before Storyline so a late model failure does not discard expensive work on long recordings.
- Kept Director failures on an actionable Retry/Back screen and recovered completed drafts across refresh races instead of falling back to the raw-footage view.
- Blocked traversal-like project IDs from deleting `data/projects` or the entire data directory.
- Made source replacement transactional: failed probes/saves preserve the previous media and all partial files are cleaned.
- Serialized project mutations with optimistic revisions; autosave is isolated per project and ignores stale responses.
- Added bounded, deduplicated, persistent jobs with refresh recovery, restart interruption reporting and safer cancellation.
- Added source/settings/pipeline fingerprints so stale transcript, vision and story caches are not reused.
- Prevented analysis or render results from committing after their source edit changed.
- Drained noisy FFmpeg audio stderr concurrently and bounded render CPU threads/export retention.

#### Added
- Added layout-aware ASS captions that move away from the creator panel in stacked and confirmed embedded-facecam compositions.
- Added a deterministic, geometry-preserving editorial-effects engine with a strict whitelist, bounded strength/count, no raw AI/FFmpeg input, and a one-click off switch.
- Added up to three ranked Reel edits from the same cached Story Beat analysis, with undoable switching and no repeated transcription/model pass.
- Added a per-scene Source Mixer list so every AI layout decision can be inspected, previewed and overridden directly.
- Added an extensible edit-style catalog and one-click Stream Highlights, Funny Moments, Strong Commentary, Stream Story Recap and low-resource Clean VOD presets.
- Added style-aware Story AI guidance, persisted `edit_style` metadata and a public style catalog for the UI.
- Manual Timeline delete/restore/split with Undo/Redo.
- Editable transcript text used by captions and future Director runs.
- Keyboard-accessible upload slots, Studio tabs and Timeline range selection.
- Draft-rebuild state that prevents exporting settings against an old AI draft.
- Behavioral regression tests for backend safety, jobs, frontend races, manual edits, audio deadlocks and storage cleanup.

### 5.6.1 - Project recovery and quiet expected errors

- Missing local projects/files now return HTTP 404 without an `Unhandled error` traceback in the CMD window.
- The remembered project is namespaced by the current CUTROOM data-directory instance, preventing project IDs from another extracted version from leaking into a fresh installation.
- Startup validates the remembered project against `/api/projects` before trying to restore it.
- Background source preparation tolerates a project being removed while a job is finishing.
- API errors now preserve HTTP status/error codes so the UI can distinguish expected 404 recovery from real server failures.

### 5.6.1 - Hierarchical Story AI

#### Added
- Multi-pass semantic Director for Short/Podcast: **Chapters -> chapter summaries -> global outline -> story plan -> exact beat selection -> critic pass**.
- Story slots require their own material (Hook, Context, Proof/Example, Payoff/Ending) instead of accepting a generic list of highlights.
- Global chapter/outline cache: changing 60s to 3m or refining the brief reuses expensive whole-recording understanding and reruns only planning/selection/critic passes.
- Explicit Story AI readiness/status in the server and UI, including the actual selected local model.
- Release smoke test that verifies the full hierarchical pipeline covers early, middle and late material.

#### Changed
- Semantic Short/Podcast editing no longer silently falls back to ranking rules when Qwen is missing. CUTROOM waits for/prepares Story AI or reports that it is unavailable.
- Candidate compaction now preserves chapter boundaries, AI key beats, semantic roles and uniform chapter coverage; editorial score is only a late tie-breaker.
- The critic receives actual candidate text and checks viewer comprehension, setup/payoff dependencies, continuity and repetition before the draft is committed.
- Qwen3.5 4B remains the default to control memory use; the intelligence gain comes from several bounded passes rather than one oversized prompt.

#### Preserved
- Audio-first dB evidence, speech protection, embedded Facecam Reel layout, Hebrew Enhanced transcription path, burned captions, unified Studio, hard Short targets, YouTube cleanup, two-source sync and deadlock-safe rendering.

### 5.5.0 - Story Director, embedded gameplay Reels and stronger Hebrew transcription

#### Added
- Story Beat planning for Shorts: long transcripts are grouped into coherent ideas before the LLM chooses the hook, context, proof/example, payoff and ending.
- Hierarchical long-video context: a bounded set of story beats covers the full recording instead of asking the model to reason over isolated transcript lines.
- A two-hour transcript regression test that requires selected material from early, middle and late source sections.
- Hebrew Enhanced transcription path using `ivrit-ai/whisper-large-v3-turbo-ct2` in Quality mode and on suitable GPU-assisted Balanced runs.
- Quality semantic planning can use Qwen3.5 9B when it is already installed; Auto/Balanced keep Qwen3.5 4B and do not pay the heavier cost.
- Temporal face clustering for one-file screen recordings so a small persistent creator camera is preferred over transient faces inside gameplay/video content.
- Multi-cascade frontal/profile face fallback without adding another neural runtime.
- Real embedded-Reel render smoke test verifying the top panel is the creator camera and the bottom panel is gameplay.

#### Changed
- `embedded_stack` now follows the requested Reel convention: **Facecam on top, gameplay/screen below**.
- The browser preview mirrors the same embedded layout instead of showing the original source twice.
- Vision analysis downscales sampled frames before face detection and remains lazy so the improved detector does not turn every edit into a heavy vision job.
- Story prompts are bounded by performance mode: fewer/shorter beats in Lite, a balanced prompt in Auto/Balanced, and a larger context only in Quality.
- Very long recordings stay on the light transcription path in Auto unless the user explicitly chooses higher quality.

#### Preserved
- Audio-first dB evidence, user silence threshold, speech protection, burned captions, unified Studio, hard Short targets, YouTube audio-cleanup path, two-source sync and deadlock-safe rendering.

### 5.3.0 - Unified Studio Workspace

- Replaced the below-the-page Advanced section with a full Studio workspace that keeps the live preview and editing controls in the same viewport.
- The actual preview player moves into Studio and back to Director, so framing, camera and timeline changes are always visible beside the control that changed them.
- Added a fixed Studio header with draft status, export and return-to-Director actions.
- Timeline, framing, transcript and settings now live in a single tool pane with independent scrolling instead of forcing page-level up/down navigation.
- Framing controls use the main live preview in Studio; the redundant secondary crop preview is hidden while Studio is open.
- Added responsive Studio layouts for desktop, tablet and mobile plus Escape-to-close and scroll-position restoration.

### 5.2.0 - Outcome Director, hard Short targets and Studio timeline

#### Added
- Hard target-duration enforcement for Shorts. A 60-second target now constrains the actual draft and final render rather than acting as a prompt hint.
- Goal-specific Director paths: Short/Reel selects a coherent story; default YouTube keeps structure and performs measured dead-air/audio cleanup.
- Full-recording transcript compaction for the local LLM using opening/closing context, strong passages, neighbors and uniform timeline coverage.
- Automatic embedded screen + facecam stacked composition for eligible one-file vertical Shorts.
- Real measured audio waveform on the Timeline, plus silence/clipping evidence overlays and background thumbnail filmstrip.
- Timeline drag scrubbing, pointer-centered zoom, horizontal pan, playhead follow and fit gesture.
- Outcome explainer in the primary UI and goal-specific defaults. Pace/audio/model controls moved to Studio.

#### Changed
- Short removal budget can exceed the old 88% ceiling when the requested target genuinely requires it, while staying close to the requested duration.
- YouTube cleanup can remove a very large proportion of measured dead air without enabling semantic low-value guessing.
- Explicit YouTube instructions can still request conservative semantic cleanup while the default remains audio-only.
- Embedded vertical composition gives screen content more space and biases its crop away from the facecam region.
- Vision sample count follows Lite/Balanced/Quality performance mode.
- Heavy thumbnail generation stays in background source preparation and never blocks the Director.

#### Preserved
- Audio-first evidence, lighter 4B default model, non-blocking source/model jobs, 40GB transport fix and deadlock-safe real FFmpeg render progress.

### 5.1.0 - Audio-first Director and lighter runtime

#### Added
- Deterministic 200 ms audio measurement for RMS, peak, noise floor, silence, quiet speech, loud speech and clipping.
- Natural, Clean and Tight sound-cleanup policies plus advanced controls for silence length, retained pause, maximum removal ratio and speech gain correction.
- Evidence attached to audio-driven edits so CUTROOM can explain why a silence was shortened or a level was changed.
- Separate spoken-language and performance-mode settings.
- Lite/Balanced/Quality transcription profiles and reusable analysis cache for Director refinements.

#### Changed
- CUTROOM is now audio-first: measured sound decides where an edit is safe; transcript/semantic AI decides whether the content should be changed.
- Default semantic model changed from Qwen3.5 9B to Qwen3.5 4B. The 9B model remains an optional fallback/quality choice.
- Lite mode uses Whisper Base on CPU; Balanced uses Small; Quality uses Turbo only when explicitly selected or appropriate.
- Visual analysis runs only when framing/camera decisions need it instead of on every edit.
- Director no longer blocks on filmstrip/waveform generation.
- FFmpeg analysis and CPU rendering use bounded thread counts.
- Automatic UI-language detection now requires stronger script/lexical evidence before switching languages.

#### Preserved
- Two-source editing, audio sync, vertical composition, upload-limit fixes, non-blocking background jobs and deadlock-safe rendering from 5.0.4.

### 5.0.4 - Director unblock and background-job isolation

- Fixed the post-upload proxy preparation job incorrectly disabling **Create my edit**.
- Separated foreground Director/render work from background proxy/model preparation executors.
- Model downloads no longer block the first Director draft; deterministic editing remains available immediately.
- Added a transcription failure fallback so missing/corrupt Whisper or first-use model download errors do not kill the whole edit.
- Reloads the latest project before committing a Director draft so concurrent proxy updates are preserved.
- Empty transcripts skip Ollama entirely instead of waiting on a model that cannot improve the result.
- Added regression tests for background-job starvation, non-blocking model installation and transcription fallback.


### 5.0.3 - large upload transport fix

- Fixed `ERR_CONNECTION_RESET` during large local video imports caused by Waitress retaining its 1 GiB default request-body limit while CUTROOM advertised a 40 GiB per-file limit.
- Waitress now receives the same request-body ceiling as CUTROOM/Flask, including multipart overhead.
- Increased the inactive upload channel timeout to one hour for unusually slow local disks or security scanning.
- `/api/system` now reports the transport request-body ceiling alongside the application upload limit.
- Added a release regression check preventing the hidden 1 GiB transport cap from returning.


### 5.0.3 - render reliability and real progress

- Fixed a real FFmpeg pipe deadlock that could leave long renders stuck at 92%.
- Restored FFmpeg `-progress pipe:1` and `-nostats`, matching the proven v3 progress strategy.
- Drains FFmpeg stdout and stderr concurrently so neither pipe can block the encoder.
- Replaced artificial timer-based render progress with media-time progress reported by FFmpeg.
- Added a distinct finalization phase after encoding before the export is marked complete.
- Added a render heartbeat so a live process does not look frozen when no fresh timestamp has arrived.
- Added regression coverage that writes more than the normal stderr pipe capacity and verifies the renderer still exits.
- Verified two-source 9:16 output, a 30-second stress render, and hardware-encoder failure with CPU fallback.

### 5.0.1 - upload clarity and Director loading polish

- Kept the per-source upload limit at 40 GB and exposed it through `/api/system`.
- Added browser-side size validation before any upload begins.
- Added explicit 413 `file_too_large` responses and fixed the Flask error-handler ordering.
- Added a distinct insufficient-disk-space error instead of mislabeling local import failures as network errors.
- Added the upload limit directly to both source cards.
- Simplified Director progress to a polished loading animation, one fixed headline and four short progress bullets.
- Stopped exposing verbose backend/model messages during Director work.

### 5.0.0 - AI Director recovery release

- Rebased the Windows setup on the Python discovery path that worked in v3.
- Retained a corrected private uv fallback without the incompatible `--managed-python` / `--python-preference` combination.
- Replaced deprecated `UV_NATIVE_TLS` with `UV_SYSTEM_CERTS`.
- Made model installation part of the first Director action instead of blocking initial setup.
- Added automatic Whisper GPU-to-CPU fallback.
- Preserved two-source editing, synchronization, vertical composition, embedded-camera detection and one-draft Director workflow.
- Added regression checks for the exact Windows failure reported in v4.0.4.
- Restricted the runtime to Python 3.11 or 3.12 for the local transcription stack.
- Replaced fragile native-process argument reconstruction with direct PowerShell invocation.
- Set qwen3.5:9b as the recommended local editor model, with smaller installed-model fallbacks.
- Fixed single-source rendering when no two-camera synchronization record exists.
- Added a complete two-source Director-to-render smoke test.

### 4.0.4 - private Python bootstrap hotfix

- Removed the dependency on a system-wide Python installation and on `py.exe` discovery.
- Added a pinned, checksum-verified uv bootstrap for x64, ARM64 and x86 Windows.
- Added a CUTROOM-owned Python 3.11 runtime under `.tools\python`.
- Added a CUTROOM-owned virtual environment built through uv.
- Added runtime path discovery for FFmpeg, FFprobe and Ollama after winget installation.
- Added persistent Windows setup logs and a focused last-error report.
- Added release tests that reject a return to system-Python discovery.

### 4.0.2 - Windows installer parser and recovery hotfix

- Rewrote `setup_windows.ps1` as ASCII-only PowerShell 5.1-compatible source.
- Removed the UTF-8 em dash that Windows PowerShell 5.1 could misdecode as a smart quote.
- Added process PATH refresh after winget installs.
- Added explicit exit-code checks for Python, pip, FFmpeg, FFprobe, and model commands.
- Added partial virtual-environment repair and setup-marker validation.
- Added `repair_windows.bat` for a forced installer rerun.
- Added release checks that reject non-ASCII Windows launcher scripts and incomplete setup guards.
- Added a Windows-native parser self-check before setup begins.

### 4.0.1 — Distribution and render hotfix

- Rebuilt the missing downloadable archive and added post-extraction verification.
- Fixed two-source FFmpeg renders when a shot uses only one source branch.
- Fixed zero-length cut ranges created when fully negative ranges were clamped.
- Fixed release DOM-ID validation and the standalone render smoke import path.
- Raised the minimum Flask and Werkzeug versions used during setup.

### 4.0.0 — AI Director

#### Distribution hotfix

- Fixed two-source FFmpeg renders when a shot uses only one branch of a split source.
- Fixed the release test that validates cached DOM element IDs.
- Fixed the standalone render smoke test import path.
- Added secure minimum versions for Flask and Werkzeug.

#### Product workflow

- Replaced the editor-first landing screen with a three-step Director workflow.
- Added one primary action: generate one applied draft.
- Moved Timeline, framing, transcript and technical settings into an optional Advanced panel.
- Added one-click refinements: shorter, keep more, more energy, fewer switches and focus speaker.
- Kept Render in the sticky top action bar.
- Restored normal document scrolling and explicit scrollbars.

#### Editorial intelligence

- Added faster-whisper transcription with word timestamps and automatic language detection.
- Added local Ollama editorial reasoning with strict segment-ID validation.
- Added deterministic fallback editing when Ollama is missing or fails.
- Added filler, repeated-take, false-start and low-value segment scoring.
- Added pace-specific removal limits and target-duration guardrails.
- Added a compact decision summary instead of a raw list of every cut.
- Added synchronized SRT generation after cuts.

#### Multi-source and framing

- Added audio cross-correlation synchronization for source A and B.
- Added bounded automatic camera plans with minimum shot length and switch caps.
- Added A, B, stacked, side-by-side and picture-in-picture output.
- Added local face focus and embedded-camera candidate detection.
- Added screen + embedded-camera vertical composition.
- Added exact aspect preview, focus position and zoom controls.

#### Performance and reliability

- Import becomes usable after copy and probe; proxy generation runs in the background.
- Scene analysis now samples reduced frames.
- Added lazy AI model loading and hardware-aware Whisper compute selection.
- Added FFmpeg hardware-encoder detection with software fallback.
- Added cancellable jobs and partial-file cleanup.
- Added atomic project persistence and strict public-path handling.

#### Quality gates

- Added unit, property-based, API, caption-retiming and release-structure tests.
- Added a real two-source vertical render smoke test.
- Added clean-release validation and archive verification.
