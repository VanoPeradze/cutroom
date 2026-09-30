# CUTROOM on Windows, macOS and Linux

CUTROOM is a free, MIT-licensed, local-first video editor for editable YouTube, Shorts and Reels cuts. The application runs on your computer; your browser is its interface. Manual editing, captions and export need no AI account or models. Local AI and compatible cloud AI are optional.

## Choose your installation

| Platform | Available path | Validation and limits |
| --- | --- | --- |
| Windows | [Combined beta ZIP](https://cutroom-studio.expo.app/#download): `windows/START CUTROOM.bat`. A source checkout uses `run_windows.bat`. | Existing Windows beta setup; fresh-computer and broad hardware QA remain ongoing. |
| macOS | The same ZIP: `mac/START CUTROOM.command`. | Targets macOS 15+ on Apple Silicon and Intel; macOS 15 automated validation passes on both architectures. Manual installation and Safari QA remain needed. |
| Linux | [Repository source](https://github.com/VanoPeradze/cutroom): `setup_linux.sh` and `run_linux.sh`. | Development path only; no Linux folder, native Linux installer or verified end-to-end Linux QA in this beta. |

The download contains only **windows** and **mac**. It ships source code and launchers, not bundled Python/FFmpeg runtimes or model weights. First setup needs internet to download dependencies. The Mac launcher is not a signed/notarized `.app`. A Linux source checkout is a separate installation path.

## Windows beta

1. Download the beta and extract the **entire** ZIP into a writable local folder. Do not run it inside the archive or extract over your existing installation.
2. Open **windows** and double-click **START CUTROOM.bat**. Keep **App** and **START HERE.html** beside the launcher. If extensions are hidden, the launcher may appear as **START CUTROOM**.
3. Let setup finish, then keep its console open while editing. Open `http://127.0.0.1:8765` if the browser does not open automatically.
4. Start with **Manual edit**, import a short recording, export it and watch the MP4 outside CUTROOM.

Setup accepts an existing Python 3.11/3.12 or downloads a private Python runtime, then installs the Python dependencies. FFmpeg and FFprobe are required; setup can attempt installation through Windows Package Manager. It may also attempt to install/start Ollama, but manual editing does not require it. Dependencies and local AI models are not bundled. See [Windows setup and troubleshooting](TEST_ON_ANOTHER_PC.md) for download behavior and diagnostics.

For a GitHub source checkout, run **`run_windows.bat` from the repository root**. Do not rearrange an existing working installation to match the ZIP: its runtime paths and Python environment can depend on its current folder. The combined download preserves the approved Windows application and launchers; refreshed package guidance does not require existing Windows users to reinstall.

## macOS beta

1. Use **macOS 15 or newer**, on **Apple Silicon or Intel**. Download and fully extract the same beta ZIP to a writable folder you can keep.
2. Open **mac**, then double-click **START CUTROOM.command**. Keep **App** and **START HERE.html** beside it.
3. Read the setup summary. Installation/repair of dependencies happens only after you approve the prompt.
4. Keep Terminal open while editing. If needed, open `http://127.0.0.1:8765` after the server starts.
5. Try a short manual project first, then review the exported MP4 and saved project after restart.

Setup reuses a compatible **native Python 3.11/3.12** and FFmpeg/FFprobe when available. If required tools are missing or incompatible, it uses an existing **Homebrew** installation to offer Python 3.12 and **ffmpeg@7**. Homebrew is needed for that installation path, not when all compatible tools already exist. If Homebrew is missing, follow the [official installation guide](https://docs.brew.sh/Installation), then launch CUTROOM again; Homebrew may require Apple's Command Line Tools. CUTROOM does not install Homebrew for you.

The Mac FFmpeg checks require libass subtitles, libx264, AAC and the command options used by this beta. Mac Python dependencies use their own compatibility constraints. Local transcription currently runs on the **CPU**; Apple GPU transcription is not implemented. Local Story AI requires a separate [Ollama installation](https://ollama.com/download/mac) and your chosen model.

This is an unsigned source launcher. If Finder/macOS blocks it, record the message and consult **START HERE.html**; do not disable Gatekeeper or remove quarantine globally. Direct Finder launch and security prompts still require manual Mac beta testing. See [Mac setup, recovery and validation details](MAC_BETA.md).

## Linux source-based development path

Linux users can try the repository scripts; this is not a packaged Linux release or a claim that every distribution is supported.

Before setup, install these using your distribution's supported tools:

- **Python 3.11 or 3.12**, including working `venv` and `pip` support.
- **FFmpeg and FFprobe**, available on `PATH`. For MP4 export, FFmpeg needs libx264 and AAC; burned captions require its `subtitles` filter/libass. Use a build compatible with the application's FFmpeg options; the Linux preflight checks executable availability, not all rendering capabilities.
- **Bash**, a writable local folder and internet for Python dependency downloads. Ollama and AI model downloads are optional.

Clone or download the [repository source](https://github.com/VanoPeradze/cutroom), extract it if necessary, and open a terminal in the repository root. Then run:

```sh
chmod +x setup_linux.sh run_linux.sh
bash setup_linux.sh
bash run_linux.sh
```

Setup creates `.venv` and downloads `requirements.txt` dependencies; it does not install system Python or FFmpeg for you. The executable permissions are necessary because `run_linux.sh` calls **`./setup_linux.sh`** if setup or runtime repair is needed. Keep the terminal open. The editor normally opens at **http://127.0.0.1:8765**; open that address yourself if your browser does not start. Stop the server with **Control-C** when finished.

Try import, preview, manual cuts, captions, MP4 export and reopening a saved project before relying on the installation. Report your distribution/version, architecture, Python/FFmpeg versions, browser and exact error. The Ubuntu repository-checks workflow tests documentation, frontend regressions and website helpers; it does **not** verify the Linux backend installation or real video workflow.

For development checks, see [contributor setup](CONTRIBUTING.md). Do not reuse Windows/Mac virtual environments or runtime executables on Linux.

## AI, storage and the first edit

Keep the launcher/terminal open: closing the browser alone does not stop the local server. Projects and working media are stored locally, under **App/data** in the Windows/Mac download or **data** in a source checkout by default. Keep originals separately and test a deliberate migration before retiring an old installation.

Start with a short recording and **Manual edit**. Imported SRT/VTT captions and text layers work without AI. Local transcription/Story AI use separate model downloads and your computer's resources. Cloud AI uses your own compatible provider account and sends selected audio/transcript context after consent; provider quotas and charges are separate. See [AI connections and privacy](AI_CONNECTIONS.md) and [model requirements](MODELS.md).

## Validation and current limits

The [successful master Mac validation on September 30, 2026](https://github.com/VanoPeradze/cutroom/actions/runs/36674994899) ran at **`cb052b5764b89205e2537292a7beb0fba5b38b3d`**, on macOS 15 Apple Silicon and Intel. Its workflow covers regression tests, a verified candidate package and synthetic editing/export/transcription smoke tests. This is automated evidence, not a manual clean-Mac installation report or proof that every public ZIP byte was tested.

Still needing manual beta QA:

- Download/extraction, Finder launch and Gatekeeper behavior on real Macs; Safari upload, preview, timeline and export/download behavior.
- Local Ollama discovery/inference and optional compatible cloud integrations on Mac.
- Transcription accuracy, sync, memory use and processing speed on representative real footage and recording lengths.
- Linux installation, preview, editing, captions and export on actual distributions/hardware.

A known shared-editor edge case with **sub-frame differences between A/B source end times** can reject adding extra media to an existing cut. It is separate from Mac setup; reinstalling the runtime will not fix it. Review edits and exported duration carefully, especially with two recordings.

Automated and synthetic checks do not prove AI editorial quality or production readiness. See [beta status](BETA_STATUS.md), [quality limits](QUALITY_AND_LIMITS.md) and the [user guide](USER_GUIDE_EN.md). To report a problem, include your OS/architecture, build, browser, exact steps and a short redacted error excerpt in a [reproducible issue](https://github.com/VanoPeradze/cutroom/issues/new/choose).
