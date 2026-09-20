# Private testing on another Windows PC

This is a beta test build of CUTROOM AI 5.6.1. It runs on the receiving PC and opens in a browser. The tester does not need Codex, a ChatGPT account or a development environment. Local AI and manual editing do not need an API key; optional Groq cloud AI does. This ZIP requires first-run setup; it is not an offline, self-contained executable. A successful installation on a clean PC has not been verified by these instructions.

## First run

1. Copy the supplied test ZIP to the other PC and use **Extract All**. Open the extracted folder that contains `run_windows.bat`. Do not run files inside the ZIP or extract over an existing CUTROOM installation.
2. Use a writable local folder owned by your Windows user, with enough free space for dependencies, models, input copies, previews and exports. Keep the folder in the same location after setup; its Python environment and saved runtime paths are tied to that PC and location.
3. Connect to the internet and double-click **run_windows.bat**. Keep its console window open. The launcher checks the included installer files, performs first-time setup, checks the runtime, then starts CUTROOM.
4. Allow setup time to finish. It can download Python, Python packages, FFmpeg and Ollama. An external installer or your PC's policies may require administrator approval; CUTROOM's script does not grant or arrange those permissions. If an installer is blocked, record the error rather than disabling security controls.
5. The browser should open at **http://127.0.0.1:8765**. If it does not, open that address manually after the console says CUTROOM is running. Keep the default local host setting for this private test.
6. Begin with a short, non-sensitive recording and **Lite**, **720p**, **Fast** output. After the first successful export, try the checklist below. Later launches use the same `run_windows.bat` and normally reuse the environment. Save transcript corrections and finish or stop jobs before closing the server console.

The browser is the interface; the console hosts the application. Closing only the browser does not stop the server. Starting the launcher again reopens an existing matching instance. If it reports that another CUTROOM version or data folder owns the port, close that other instance first.

## Dependencies and downloads

- **Python:** setup accepts an existing Python 3.11 or 3.12. Otherwise it downloads a private Python 3.11 using a version-pinned, SHA-256-checked `uv` bootstrap, then creates `.venv`. Python packages are downloaded with pip. The ZIP does not include this runtime.
- **FFmpeg and FFprobe:** both are required. Setup reuses detected executables or attempts installation through Windows Package Manager (`winget`, package `Gyan.FFmpeg`). If they cannot be found and winget is unavailable or its installation fails, setup stops. Have the PC owner install FFmpeg/FFprobe and make them available on PATH, then run the launcher again.
- **Ollama:** setup tries to install it through winget (`Ollama.Ollama`) if missing, and starts an installed local service. Failure to install or start Ollama does not itself prevent CUTROOM from opening. Default YouTube dead-air cleanup can work without a Story AI language model; semantic Short/Reel and Podcast editing require a ready local engine and compatible model. Use **Retry AI** after resolving an engine problem.
- **AI models:** none are bundled. The supplied configuration has `download_models_on_setup: false`. Use **AI connection → On my computer** to inspect readiness and explicitly download speech and Story models before a first AI job. Downloads are cancellable; shared partial cache files may remain for reuse. Lite/Balanced/Quality use Base/Small/Turbo speech models respectively, with language-specific choices; Story weights can require several GB. Downloading a model does not select the project's performance profile. The existing transcription path may still fetch a missing selected speech model on first use. Stay online until required files are available. Manual editing needs neither model type, and optional Groq processing does not need local speech/Story weights for those cloud requests. [AI choices and privacy](AI_CONNECTIONS.md).
- **Offline and hardware limits:** editing can use locally installed dependencies and cached models afterward. A first run or a missing model still needs internet. CPU execution is available but can be slow; GPU availability and driver/native-library compatibility vary. Setup's architecture-specific bootstrap choices are not a guarantee that every dependency works on ARM64 or 32-bit Windows.

Setup creates local `.venv`, may create `.tools`, and records `.setup-complete` and `.runtime-paths.cmd`. Projects, copied footage, analysis, logs and exports are stored under `data` by default. Ollama and speech model caches may also live outside the extracted folder. Do not send these generated folders back as a replacement test package.

## Workflow checklist

Mark each item **Pass**, **Fail**, or **Not tested**, and record the source length and elapsed time. Use separate projects for the three source cases.

- [ ] **Single source:** import one video as A. Check preview, waveform and spoken language. Build a YouTube cleanup draft, listen for clipped quiet words and excessive silence cuts, then export. When Story AI is ready, also try a Short/Reel with a 60-second target and check the actual exported duration.
- [ ] **Two separate sources:** import screen and camera recordings as A/B. Confirm screen, camera and audio assignments before Director starts. Check sync near the beginning and end, try Creator frame, and verify camera top 30% / screen bottom 70% plus the chosen audio in preview and export. Record any automatic sync warning; inspect or adjust the available sync controls when needed.
- [ ] **Embedded camera in one recording:** import the combined recording only as A. In **Studio > Layout**, choose a reference frame, move/resize the camera rectangle, and choose **Save and use layout**. Check top 30% camera and bottom 70% screen in preview and export. The lower view should exclude the marked camera; **Main screen focus** should move within the remaining screen region. Check another point in the recording too. Moving cameras need manual review; the rectangle does not track them.
- [ ] **Transcript and captions:** in **Studio > Captions**, search and select a sentence; verify the seek position. Edit its text, navigate away and back, then use **Save text** or **Save all changes**. Test undo/redo and refresh after saving. Check corrected captions in the exported video; enable the optional SRT export and check its text/timing too. Unsaved text buffers are not preserved across closing the browser.
- [ ] **Manual cuts:** use Range to remove a passage, Original footage to restore it, Cut to split, and Select / Move to reorder or trim a clip with its white edge handles. Compare Together with A only / B only. Check Close gaps, per-cut framing, Undo/Redo, yellow-playhead-centered zoom and saved state after reopening. Full source and edited playback should stay separate. Verify the export follows the edited sequence, including reordered/restored clips. See [the editing guide](INDEPENDENT_TRACKS.md).
- [ ] **Cancellation and recovery:** use **Stop process** during a Director run and during an export in a disposable test project. Wait for the job to stop, confirm the UI becomes usable, then retry. Refresh during a later active job and check progress recovery. An existing/shared Ollama service may remain running after cancellation; cancelling the edit is not a request to stop that service.
- [ ] **Export and restart:** play the downloaded MP4 outside CUTROOM. Check start/end, aspect ratio, composition, audio sync, captions and duration against the preview. Confirm saved projects and corrections reopen after a normal server restart. Repeat at the tester's normal browser zoom and window size; record overlapping or unreachable controls.

If a setting is marked **Draft rebuild**, rebuild before exporting. Save pending transcript corrections first. Treat failures as test findings; this checklist describes expected behavior, not completed verification.

## If setup or launch fails

Keep the visible error and the time it occurred. Setup diagnostics are in `data\logs\setup-last-error.txt` and `data\logs\setup-windows.log`; local AI startup diagnostics are in `data\logs\ollama-runtime.log` when created. Runtime errors can also appear in the launcher console. A missing/incomplete installer error occurs before setup: extract the entire original ZIP into a fresh folder and retry.

The launcher attempts repair when its runtime check fails. That check imports the required Python/native modules, runs FFmpeg/FFprobe, and verifies the data cache is writable; it does not prove that a model is installed or that a real edit/export works. A network, package-download, permission or native-library failure still needs its specific cause resolved.

## Bug report

Copy this template and send it privately to the person who supplied the build:

```text
Build / ZIP filename:
Windows version and architecture:
CPU / RAM / GPU and driver (if known):
Browser version / window size / zoom:
New installation or previously installed dependencies:
Internet available? First model download completed?
Source setup: single / separate screen+camera / embedded camera
Source format, resolution, duration and speech language:
Goal / edit style / performance / output settings:
Exact steps to reproduce:
Expected result:
Actual result and exact error:
Time to failure / time to complete:
Reproduces every time? What happened after retry/restart?
Relevant redacted screenshot or log excerpt:
```

Review attachments before sending: logs, console text, screenshots and project files can reveal Windows usernames, local paths, filenames, transcripts, faces or private footage. Share the smallest useful redacted excerpt. Do not attach the entire `data` folder, original media, model caches, or a full browser/network dump unless separately requested and reviewed.
