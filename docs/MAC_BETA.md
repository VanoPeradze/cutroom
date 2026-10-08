# CUTROOM 1.1 Beta for Mac

The same free, MIT-licensed editor, with a separate Mac setup and launcher.
The separate Mac ZIP contains **START CUTROOM.command**, **START HERE.html**, and **App**. The compatible combined download still contains exactly two folders: **windows** and **mac**.
The current **1.1 Beta editor revision** updates the shared application in both
folders: source waveforms, the A/B duration boundary fix, live mixer meters,
Unicode media-name handling and optional local stabilization. It has a new build
ID/checksums; it is not a documentation-only refresh.

## Start on a Mac

1. Extract the entire ZIP. Move the extracted folder somewhere you can keep it.
2. Double-click **START CUTROOM.command** beside **App**. In the combined ZIP, open **mac** first. Keep **App** beside it.
3. Read the setup summary before agreeing to dependency installation. First setup requires internet.
4. Keep the Terminal window open. The editor opens in your browser when ready.
5. Start with **Edit it yourself** and a short recording. AI is optional.

The Mac beta targets **macOS 15 or newer**, on **Apple Silicon or Intel**. Its
automated test matrix uses macOS 15 on both architectures. Other OS versions are
not claimed as tested. This is a source distribution, not a signed/notarized Mac
application or an App Store download. A downloaded launcher may require a security
review by macOS; do not disable Gatekeeper or remove quarantine globally. If it
cannot be opened, use **START HERE.html** and report the exact message.

## First-time requirements

Setup reuses a compatible Python 3.12 and FFmpeg when present. Otherwise it
offers to install Python 3.12 and **ffmpeg@7** through an existing Homebrew
installation, then installs the Python dependencies inside this copy's **App/.venv**.
This maintained FFmpeg 7 build includes subtitle support and the command-line
options used by CUTROOM. Newer major versions are not automatically compatible.
It is installed side-by-side without replacing your system's FFmpeg.
Mac-only Python constraints also keep PyAV below version 19, whose
[audio API changes](https://github.com/PyAV-Org/PyAV/releases/tag/v19.0.0)
are incompatible with the current transcription engine. These constraints do not
change the Windows package or the shared application requirements.
Nothing installs until you confirm the setup prompt.

If Homebrew is missing, follow the official [Homebrew installation guide](https://docs.brew.sh/Installation),
then run the CUTROOM launcher again. Homebrew may need Apple's Command Line Tools.
CUTROOM does not run a downloaded Homebrew installer or request administrator rights
on your behalf. Already-working setups do not repeat network installation on launch.

If setup was interrupted before its Python package installer (`pip`) was ready,
the Mac launcher can now restore it automatically after you approve setup. If
recovery fails, it stops with instructions for rebuilding only **App/.venv**;
your projects are not removed. Do not rename or delete **App/data**.

The Mac launcher also handles quick restarts on the same local port. Its Mac-only
socket setup allows recently closed connections to finish without blocking a new
launch; it still refuses a port owned by a different running application.

## AI choices and performance

- **Manual editing:** no AI model or AI account is needed.
- **Local transcription:** runs on the CPU in this beta. Apple GPU transcription is
  not implemented; long recordings can be slower. Try a short clip first.
- **Local Story AI:** install the Mac version of [Ollama](https://ollama.com/download/mac),
  then use the editor's AI connection screen to download a model you choose. The
  launcher can discover the normal application installation. No models are bundled
  or downloaded automatically during setup.
- **Your API:** optional, with the same compatible-provider requirements as Windows.
  Selected content is sent only to your chosen provider after consent. Provider
  quotas and costs are separate from CUTROOM.

The shared application source is identical in both folders, but that does not mean
equal speed on different hardware. Export, audio, Hebrew captions, and AI results
still need review on your own footage.

## What testing does and does not prove

Earlier passing Mac runs cover their recorded release payloads. **Publication
of this editor revision requires current-source macOS 15 Apple Silicon and Intel
automated checks.** Local Windows tests, browser checks and actual synthetic
FFmpeg renders passed; they do not establish Mac compatibility. Check the run
and source commit before treating a Mac result as evidence for a downloaded build.

The Mac workflow checks both architectures, dependency setup, the packaged launcher,
and real synthetic media rendering. It exercises source uploads, a camera-above-screen
stack, 60 fps, 1440p/4K exports, imported images/music/B-roll, subtitles and titles,
audio gain, project persistence after restart, and transcription in its separate
worker. It also checks repeat launches with pip/model downloads disabled; this is
not a firewall-based offline test. The previous published ZIP and new candidate
are tested separately. See the latest
[Mac validation runs](https://github.com/VanoPeradze/cutroom/actions/workflows/macos.yml)
for actual results. Passing automation is not a claim of a manually verified clean
Mac installation, Safari coverage, or perfect AI output. Those still need Mac beta
testers. Use copies of footage and keep your originals.

The earlier shared-editor sub-frame A/B duration rejection is fixed in this
revision. Source-end boundaries were verified with actual 30/60 FPS synthetic
renders on Windows; Mac verification remains part of the candidate checks.
Manual A/B waveforms no longer require AI analysis, and the mixer displays live
browser sample peaks. Those meters do not certify export loudness.

**Media > Stabilize footage** can create a separate local MP4 copy when this
installation's FFmpeg has both vidstab filters. It may zoom/crop edges; it does
not replace originals or the edit, and needs no AI or upload. Mac stabilization
still needs native testing. [Stabilization details](STABILIZATION.md).

Existing users need the new download to receive these shared-editor changes.
Extract it separately and back up projects before migrating saved work.
Do not move Windows virtual environments, downloaded executables or model caches
into the Mac folder. Keep your previous installation and its projects until you
have verified any deliberate migration.

## Report a problem

Include your macOS version, Apple Silicon/Intel, the operation that failed, and
the error message. Avoid personal footage, API keys and complete private logs.
[Report a reproducible issue](https://github.com/VanoPeradze/cutroom/issues/new/choose).

## Developers

Build the combined package with `python scripts/build_universal_package.py --download-baseline`.
The Windows baseline is pinned by archive size, SHA-256 and its internal manifest;
an unavailable or changed baseline fails the build. An offline build can instead
use `--windows-zip PATH`. Use `--verify PATH` to check the final package.
The legacy Windows-only builder remains available. This editor update uses a new,
intentionally built and approved Windows baseline; the combined builder preserves
that baseline while adding the Mac overlay. Package manifests identify the exact
build rather than relying on the unchanged public 1.1 Beta filename.
