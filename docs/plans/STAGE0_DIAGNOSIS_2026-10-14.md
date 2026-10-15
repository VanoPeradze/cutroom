# Stage 0 — diagnosis and staged plan (2026-10-14)

Base: `master` at `05852dc1d4feeee23a04f5692328eb5bfbe01642` (clean working tree; only untracked local files).
Hardware for every measurement below: Windows 10 22H2, 24 logical CPUs, 31.1 GB RAM, NVIDIA RTX 4070 Ti SUPER 16 GB (driver 617.42), FFmpeg 7.1.1 (gyan.dev full), Ollama 0.34.2 with `qwen3.5:4b`.
All runs used isolated data directories and ports 8766/8769. Port 8765 had no listener and was not used.
Private recordings were used only through hard-linked local copies; nothing private is quoted here.

## 1. System map (verified in code unless marked)

| Stage | Where it runs | Main code |
|---|---|---|
| Import, probe, browser proxy, thumbnails | local Python + FFmpeg | `server.py` (upload), `cutroom/media.py` (`probe_media`, `create_proxy`, `extract_thumbnails`) |
| Transcription | local worker process; CUDA float16 or CPU int8; Silero VAD; chunked 30 s units | `cutroom/transcription.py`, `transcription_worker.py`; models `base/small/turbo`, Hebrew `ivrit-ai/whisper-large-v3-turbo-ct2` |
| Audio analysis | local Python + FFmpeg | `cutroom/audio.py` (`analyze_audio`, waveform bins, silence/loud ranges) |
| Camera/face, gameplay vision | OpenCV Haar (CPU); Ollama VLM on GPU | `cutroom/vision.py`; `cutroom/visual_moments.py` (8 s windows, 4 frames, screen class + action flags) |
| Candidates and planning | Ollama (local) or cloud provider | `cutroom/intelligence.py` (story hierarchy, critic), `cutroom/director.py` (selection, gameplay-moment route, Reel options), `cutroom/edit_styles.py` |
| Timeline model and edits | local Python | `cutroom/sequence.py` (versioned manual sequence), `cutroom/editing.py` (manual edits, undo/redo history), `cutroom/media_library.py` (media/text clips, mixer) |
| Timeline UI | browser canvas | `web/timeline.js` (drawing, hit-testing, gestures), `web/text-studio.js`, `web/media-studio.js` |
| Preview | browser `<video>` + WebAudio (bus gains, live meters before a preview limiter) | `web/app.js`, `web/media-studio.js`, `web/audio-meter.js` |
| Render | FFmpeg filter graph; NVENC when available; captions burned via ASS; optional second `loudnorm` pass | `cutroom/render.py`, `cutroom/media_render.py`, `cutroom/captions.py`, `cutroom/effects.py` |
| Save | atomic JSON write with revision conflict check; frontend schedules settings patches | `cutroom/projects.py` (`save`, `expected_revision`), `web/app.js` |
| Jobs | in-process job manager with cancellation | `cutroom/jobs.py` |
| Tests | 110 `tests/test_*.py` (pytest, includes Node frontend wrappers), 31 `tests/*.cjs` (frontend and browser), `tests/smoke_*.py`; CI: repository checks, audit, CodeQL, native macOS arm64/x64 | `tests/`, `.github/workflows/` |

## 2. Known failures: reported, reproduced, code-only, open

| # | Reported failure | Status | Evidence |
|---|---|---|---|
| 1 | Automatic captions cannot be selected in the timeline | **Reproduced** in the browser on an isolated synthetic project | Clicking an automatic caption only moved the playhead; double-click did nothing; panel and status unchanged. Code: the caption lane is drawn from `analysis.transcript.segments` (`web/timeline.js` 489–502) but `mediaAtEvent` searches only `mediaRows()` = `media_clips` + `text_clips` (397–434). Manual/imported captions are `text_clips` and are selectable. |
| 1b | Caption correction must not change the source transcript | **Code-only finding** | `transcript_text` overwrites `analysis.transcript.segments[].text` in place and drops word timings when the token count changes (`cutroom/editing.py` 619–644, 1022–1037). There is an undo entry, but no separation between a source correction and an edit-time override. Whether a later re-transcription discards corrections is not yet tested. |
| 2 | Faders/routing not reliable | **Reproduced (export)** | Fixture without a Director audio policy: Original −12 dB → RMS −12.00 dB; Master −6 dB → −6.00 dB; mute → silence. Director draft (`audio_policy.normalize`, −16 LUFS): Original −12 dB changed RMS by **0.00 dB**; Master −6 dB → −6.00 dB. Cause: `loudnorm` runs after the role buses and before the master gain (`cutroom/render.py` 830–842), so a bus fader is undone in export while the preview gets quieter. Unity export peaked at **0.0 dBFS** (the limiter is added only when master ≠ 0). Preview-side levels were not measured yet. |
| 3 | Requested duration ends much shorter | **Reproduced (story path, one recording)** | A 180 s Stream Story request on a 27-min gameplay recording produced 83 s (2026-10-10 lab run; same story code on master). On a 2-h speech-heavy recording the same request produced 168 s. The shortfall depends on the material; the duration chain is not yet logged end to end. |
| 4 | Transcription stops (Hebrew/English) | **Partially reproduced** | A 2-h Hebrew recording: one 30 s chunk had 23.3 s detected speech but 4.6 s transcribed; decoding that chunk again without VAD recovered the speech. Before #71 this blocked the whole edit; it now warns with the range. A full stop of transcription was not reproduced. |
| 5 | In-game recorded scene classified as a fight | **Reproduced** | An in-game security-camera playback window was classified `gameplay` with action 0.46 and entered a 180 s gameplay draft. |
| 6 | Full-screen facecam classified as gameplay | **Not reproduced** | In both private recordings, desktop/chat/OBS screens were `other` and menus `menu_or_map`. Needs a sample with a full-screen camera. |
| 7 | Opening/ending without context | **Reproduced (story path)** | 180 s Stream Story on a 2-h Hebrew recording: 8 passages spread over 53 minutes, an opening line without its setup, a 1.7 s fragment, an invented narrative title; the continuity critic did not pass. |
| 8 | Sentences cut mid-way | **Not yet confirmed** | Gameplay route snaps to word phrases (tested). Story-path boundaries use segment edges; mid-sentence cuts were not checked frame/word by word. |

## 3. Data-safety risks found

1. `transcript_text` mutates the source transcript (see 1b).
2. Hard-linked private media under `%TEMP%\cr-ai` (lab copies). Deleting the copies is safe; an in-place write would affect the originals. The app does not write sources in place.
3. Dependabot PR #80 raises `av` to ≥19, which was deliberately excluded because PyAV 19 breaks faster-whisper 1.2.1 (#67). Do not merge it.
4. Export can reach 0 dBFS sample peak at unity master (see 2).
5. A new AI draft does not replace an existing manual timeline: the app keeps it and offers an undoable "Apply new AI draft". This protects work but can look like "the AI did nothing" in an old project.

## 4. Staged plan (one stage at a time)

**Stage 1 — automatic captions as real timeline items (first implementation).**
Design: caption *instances* are derived once on the backend from the transcript × the kept edit ranges, with stable IDs `segment_id` + occurrence; edits are stored as overrides keyed by instance (text, start, end, style, hidden) and source corrections are stored separately keyed by segment, leaving the original transcript intact. One function feeds the timeline, the preview overlay and ASS/SRT export. Frontend: caption lane hit-testing, shared selection (timeline ↔ Captions panel ↔ preview), double-click to edit text, edge drag for timing (one history entry per gesture), overlapping captions reachable, keyboard (Enter/Esc/Delete/arrows), no layout jump. Word highlight is dropped for an instance whose text change breaks word alignment.
Gate: manual and automatic caption selection, text and timing edits, overlaps, panel/preview sync, keyboard, undo/redo and save/reopen work in Hebrew and English; preview, burned captions and SRT agree after trim, move and undo; no lost edits.

**Stage 2 — mixer.** Decide the normalization semantics (see decisions); always apply a true-peak ceiling; add 0 dB mark, typed value, fine step, reset, wheel only on an explicitly active control; label meters as sample peak dBFS and where they tap. Gate: numeric preview-vs-export comparison within a stated tolerance, and a listening check.

**Stage 3 — AI in two flows.** Duration chain recorded end to end; targeted re-decode of VAD-mismatch chunks; user-correctable screen classes with an "uncertain" state saved in the project; recorded-scene detection; story path evaluated against a labelled talk set (Codex's unvalidated `codex/focused-short-v6-wip` is one candidate, compared with the current baseline). Gate: acceptance scenarios for talk and for gameplay without speech; reversible drafts; locks and manual edits preserved.

**Stage 4 — editable graphics templates and bounded output review.** **Stage 5 — performance profiles and packaging.**

## 5. Not tested yet

Mac hardware, CPU-only and 16 GB profiles, preview-side audio levels, VFR sources, competitor comparisons, a public licensed evaluation set, a talking-head Hebrew/English sample.
