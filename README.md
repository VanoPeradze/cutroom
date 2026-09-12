# CUTROOM — free, open-source video editing

Turn a recording into a first cut, then make it yours.

CUTROOM is a local video editor for talking-head videos, screen recordings and gameplay. It helps transcribe footage, build a draft, arrange a camera and screen, add captions and export a video. You can then cut, move, restore and frame the clips yourself.

**Closed beta · Windows-first · MIT licensed.** No subscription, paid API key, account requirement or CUTROOM watermark. Source code is included. Your computer does the processing; third-party tools and models have separate licenses.

This is a feedback build, not a finished replacement for DaVinci Resolve or Premiere. Please use copies of footage, not your only copy of an important project or an urgent client delivery.

## Start here — Windows

1. **Extract the entire ZIP** into a normal, writable folder. Do not run files inside the ZIP.
2. Open that folder and double-click **`run_windows.bat`**.
3. Let first-time setup finish. It downloads or reuses the tools CUTROOM needs. Keep the terminal open while editing.
4. Your browser should open CUTROOM. If it does not, open **http://127.0.0.1:8765** once the server is running.
5. Use the same launcher next time. **Codex, ChatGPT and an IDE are not needed.**

The browser is the interface; the local process behind it must stay running. Closing the terminal stops CUTROOM. Closing just the browser does not necessarily stop it.

**First setup needs internet.** This is a source package with a launcher, not a signed, self-contained installer. Python, FFmpeg, Ollama and model weights are not inside the ZIP. Setup attempts to install missing tools; external installers may ask for approval. Do not disable security software to install it. See [installation help](docs/TEST_ON_ANOTHER_PC.md) if setup fails.

Speech models download when first used. If Story AI needs a model, the app asks you to confirm a separate download, which can be several GB. Once the required tools and chosen models are installed on that PC, processing can run locally without a paid service.

## Make your first edit

Start with a **1–3 minute, non-sensitive clip** before processing a long recording.

1. Create a project and add your recording. Add a second recording if your camera and screen are separate.
2. Choose **YouTube** for horizontal output, or **Short / Reel** for vertical output. Check the shape before building and exporting.
3. Set the spoken language if you know it. Try **Balanced** for a quality check, **Lite** for a lighter first run, or **Quality** for heavier processing, including the Hebrew-specific speech model.
4. Build a draft. Review the transcript and selected moments: AI can miss words, context and good clips.
5. Adjust the result in the editor, then export. Start with **720p / Fast** to check the output before a larger render.

For a camera embedded in one video, review and confirm the camera rectangle. The creator stack puts the camera in the top **30%** and the screen in the remaining **70%**. This crops the existing recording; it cannot recover a separate camera file.

## The editor, without the guesswork

The timeline represents **the edited video**. Each cut is an individual clip; original recordings remain separate.

| I want to… | What to use |
| --- | --- |
| Play, pause or seek | Space; click the timeline ruler to seek. |
| Remove a section | **Range**, drag over it, then **Remove from video**. |
| Split at one point | **Cut**, then click the split point. |
| Reorder a cut | **Select / Move**, then drag. Its old position closes and destination footage shifts. |
| Reveal more original footage | Select a clip and drag its white edge, up to the next clip or media boundary. |
| Restore something removed | **Original footage**: green is kept, red is removed. Preview a range, then **Restore to edit**. |
| Edit one source separately | **A only** or **B only**. **Together** edits both as a pair. |
| Frame just one section | Select it, then **Layout → Clip framing**. |
| Remove empty time | **Close gaps**, when shown. Together only closes time where both sources are empty. |
| Zoom around the playhead | Zoom in/out centers on the yellow playhead, within timeline boundaries. |
| See a larger video | Resize the video/timeline divider, or use the video's **Full screen** control. |

Manual edits save automatically and support Undo. **More tools** holds detailed controls. **How to edit** and shortcut help explain the workspace. Familiar keyboard profiles cover supported CUTROOM actions, not every command from another editor.

Read the [editing guide](docs/INDEPENDENT_TRACKS.md) and [keyboard guide](docs/KEYBOARD_SHORTCUTS.md) for details.

## What to expect from this beta

- One recording or two synchronized sources, editable clips, per-section layouts and captions.
- Export at **24, 25, 30, 50 or 60 FPS**. Lower-rate footage exported at 60 FPS repeats frames; there is no AI motion interpolation.
- Local transcription and Story AI. Default YouTube cleanup keeps chronological order; it is not a complete long-form narrative rewrite.
- Styles guide pacing and selection. They are not exact copies of a creator's editing and do not reliably recognize gameplay kills, wins or jokes visually.

**Equal quality across languages has not been demonstrated.** Results vary by language, accent, recording and model. A stronger model does not guarantee a good edit. Check captions, cuts, synchronization and the actual exported file.

This is a two-source editor, not an unlimited-track NLE, grading suite or per-clip audio workstation. A/B-only edits can intentionally leave gaps or change synchronization. Embedded-camera detection can be wrong. Fresh-PC installation and long 4K sessions still need real-world testing. See [beta status](docs/BETA_STATUS.md).

## Does it need an NVIDIA GPU?

**No. CPU processing is supported, but can be substantially slower.** Speech recognition uses NVIDIA acceleration when compatible CUDA is available. That speech path does not use AMD/Intel GPUs as CUDA devices. Ollama and video export have separate hardware support and fallback behavior.

For the first tester group, Windows x64, **16 GB RAM or more**, an SSD and space for several GB of models plus footage/cache are sensible starting points — **not measured minimum requirements or speed guarantees**. CPU-only testers are welcome; start with short clips and Lite.

Windows x64 is the main first-run target. Linux scripts are included for technical testers (`bash run_linux.sh`), but this beta is not certified across Linux distributions, macOS, ARM or 32-bit Windows.

## Which AI models are used?

- **Speech:** Whisper `base` (Lite), `small` (Balanced), `turbo` (Quality), through faster-whisper / CTranslate2.
- **Hebrew Quality:** `ivrit-ai/whisper-large-v3-turbo-ct2`.
- **Story:** `qwen3.5:4b` by default; explicit Lite prefers installed `qwen3.5:2b`, Quality prefers installed `qwen3.5:9b`. `qwen3:8b` is another configured fallback.
- **Detection:** Silero VAD for speech activity and three OpenCV Haar classifiers for face/camera proposals.

You do **not** need every model. Mode, availability and hardware affect selection. The [model guide](docs/MODELS.md) lists exact roles, fallback behavior, sources and possible improvements. No models were replaced for this packaging pass.

## Privacy, cost and ownership

With shipped settings, media processing stays on your PC. Downloads contact the software/model distributors, whose tools may have their own network behavior. This beta is **not designed for public internet hosting**. Keep the server and Ollama addresses local.

Projects, copied media, cache and exports live under `data/` in the app folder; model caches may be elsewhere. Keep the app folder in place after setup and back up projects. Never send the whole `data/` folder as a bug report: it can contain recordings and transcripts.

CUTROOM is **free and open source under the [MIT License](LICENSE)**. You may use, study, modify and redistribute the code, including commercially, subject to that license. The source is included in this private beta even while the GitHub repository remains private. No license fee is charged; hardware, electricity, storage and internet remain your responsibility. Tools and weights have [separate notices](THIRD_PARTY_NOTICES.md).

## Help us make it useful

**Did it save time? What was confusing? What did you have to fix?** A poor result is useful feedback too.

Fill in the short [feedback form](docs/BETA_FEEDBACK.md) and send it privately to whoever gave you the ZIP. Include the build name from `TEST_BUILD.json`, settings and steps. Review screenshots/logs for private information first. No account or public issue is required.

## For contributors

Plain JavaScript/CSS lives in `web/`; Python lives in `cutroom/`, with `server.py` as entry point. Defaults in `cutroom/config.py` are overridden by `config.json`. Never commit personal paths, credentials, caches or project data.

After setup:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -o addopts='' -q
node --test tests/frontend*.test.cjs
```

Node is needed for frontend tests, not for running CUTROOM. AI-quality evaluation is separate from regression tests; see [transcript evaluation](docs/TRANSCRIPT_EVALUATION.md).

Build a clean ZIP with `.venv\Scripts\python.exe scripts/build_test_package.py`. It uses an allowlist, fresh default settings and a per-file manifest, and writes a ZIP plus SHA-256 checksum to `dist/`. **Never ZIP the working directory**: it may contain private recordings and installed runtimes. Use `--verify PATH_TO_ZIP` to verify a built archive.
