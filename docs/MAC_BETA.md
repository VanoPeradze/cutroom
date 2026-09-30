# CUTROOM 1.1 Beta for Mac

The same free, MIT-licensed editor, with a separate Mac setup and launcher.
The combined download contains exactly two folders: **windows** and **mac**.
The Windows folder preserves the previous Windows package without changing its files.

## Start on a Mac

1. Extract the entire ZIP. Move the extracted folder somewhere you can keep it.
2. Open **mac**, then double-click **START CUTROOM.command**. Keep **App** beside it.
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

Setup reuses a compatible Python 3.11/3.12 and FFmpeg when present. Otherwise it
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

The Mac workflow checks both architectures, dependency setup, the packaged launcher,
local server responses and real synthetic media rendering. See the latest
[Mac validation runs](https://github.com/VanoPeradze/cutroom/actions/workflows/macos.yml)
for actual results. Passing automation is not a claim of a manually verified clean
Mac installation, Safari coverage, or perfect AI output. Those still need Mac beta
testers. Use copies of footage and keep your originals.

Existing Windows installations do not need replacing for this Mac-only update.
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
The legacy Windows-only builder remains unchanged. Updating the Windows application
requires a separate, intentional baseline release; this Mac release does not do so.
