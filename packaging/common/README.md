# CUTROOM 1.1 Beta — Windows, macOS and Linux source

CUTROOM is a free, MIT-licensed video editor for YouTube, Shorts and Reels. It runs on your computer and opens its editing interface in your browser. Import footage, trim and move clips, add media and captions, mix audio, and export MP4 video. Manual editing needs no AI account or models.

## Start from this download

Extract the entire Windows or Mac ZIP into a writable folder. Its launcher, **START HERE.html**, and **App** are together at the top level. If using the compatible combined ZIP, open its **windows** or **mac** folder first. Keep them together. This README lives inside App; [open your platform's offline startup guide](../START%20HERE.html).

| Platform | Launcher and prerequisites | Beta status |
| --- | --- | --- |
| **Windows** | Double-click **START CUTROOM.bat** beside **App** (inside **windows** for the combined ZIP). Setup uses an existing Python 3.12 or downloads a private one; FFmpeg/FFprobe are required and setup can attempt installation through Windows Package Manager. | Windows beta. First setup needs internet; clean-computer and broad hardware QA remain ongoing. |
| **macOS** | Double-click **START CUTROOM.command** beside **App** (inside **mac** for the combined ZIP). Requires macOS 15+ on Apple Silicon or Intel, native Python 3.12 and compatible FFmpeg/FFprobe. Setup can offer Python 3.12 and **ffmpeg@7** through an existing Homebrew installation after approval. | Source launcher, not a signed/notarized `.app`. Publication requires current-source macOS 15 automation on both architectures; Finder/Gatekeeper and Safari manual QA remain needed. |
| **Linux** | Use the separate [GitHub source](https://github.com/VanoPeradze/cutroom), with its `setup_linux.sh` and `run_linux.sh` scripts. See the [Linux prerequisites and commands](https://github.com/VanoPeradze/cutroom/blob/master/docs/PLATFORMS.md#linux-source-based-development-path). | Development path only. This download has no Linux folder or Linux installer; end-to-end Linux installation/edit/export QA is not verified. |

On Mac, FFmpeg needs libass subtitles, libx264, AAC and the command options used by this beta. `ffmpeg@7` is the documented compatible Homebrew choice. CUTROOM does not install Homebrew; use its [official installation instructions](https://docs.brew.sh/Installation) if needed. Python 3.13+ is not supported by these setup scripts. The Mac launcher checks native architecture and uses separate Python dependency constraints. If macOS blocks the launcher, consult **START HERE.html** and record the message; do not disable Gatekeeper or remove quarantine globally.

The ZIP contains source and launchers, **not** bundled runtimes or model weights. Setup downloads dependencies. Windows setup may also attempt to install/start Ollama, but manual editing does not require it. Keep the console or Terminal open while editing; closing the browser alone does not stop the server. The editor normally opens at **http://127.0.0.1:8765**; open that address yourself if necessary. On Mac, use **Control-C** in Terminal to stop CUTROOM.

## Make the first edit

1. Start with **Manual edit** and a short copy of a recording you know well.
2. Import footage, review the preview, make a few cuts and add text or imported SRT/VTT captions.
3. Export an MP4, watch it outside CUTROOM and reopen the saved project.

[English user guide](docs/USER_GUIDE_EN.md) · [Hebrew user guide](docs/USER_GUIDE_HE.md) · [Keyboard shortcuts](docs/KEYBOARD_SHORTCUTS.md) · [Windows troubleshooting](docs/TEST_ON_ANOTHER_PC.md) · [Mac setup and QA details](https://github.com/VanoPeradze/cutroom/blob/master/docs/MAC_BETA.md)

Projects, working media and exports live in **App/data** by default. Keep originals separately. Back up saved work before updating; extract a new release into a separate folder rather than overwriting an existing installation. Do not copy Windows runtimes or virtual environments into Mac/Linux installations. [Upgrade notes](docs/UPGRADE_HE.md).

## Optional AI and privacy

Local transcription and Story AI need separate models chosen and confirmed in the editor. Mac transcription currently runs on the **CPU**; Apple GPU transcription is not implemented. Local Story AI requires Ollama and a compatible model. No models are bundled, and the Mac setup does not download them automatically.

Cloud AI requires your own compatible provider account, endpoint and API key. Selected audio/transcript context is sent after consent; provider quotas and charges are separate from CUTROOM. Manual editing and export remain local. Review transcripts and AI-selected cuts before sharing. [AI connections and privacy](docs/AI_CONNECTIONS.md) · [Model requirements](docs/MODELS.md).

## What this editor revision changes

This **1.1 Beta** editor update fixes source waveforms in manual/A/B projects, the sub-frame A/B duration rejection and Unicode media-name handling. The mixer has compact faders and live audio meters. **Media > Stabilize footage** can create a separate local MP4 copy when your installed FFmpeg has `vidstabdetect` and `vidstabtransform`; it may zoom/crop edges and never replaces the original or your existing edit. No AI or upload is needed. [Stabilization guide](docs/STABILIZATION.md).

The public version and ZIP filename stay **1.1 Beta**; package manifests identify this revision with a new build ID/checksums. Existing users need the new download to receive the editor changes. Extract it separately and back up projects before migrating saved work; do not overwrite an installed runtime.

Local Windows regression, browser and actual FFmpeg synthetic-media checks passed, including A/B boundary renders at 30/60 FPS. This editor revision requires current-source Apple Silicon/Intel macOS 15 checks before publication; [GitHub Actions](https://github.com/VanoPeradze/cutroom/actions/workflows/macos.yml) records results by commit. Earlier passing runs apply to their earlier payloads. Added media/text still fit within the edit and do not automatically ripple with source changes. AI accuracy, source sync and real-footage performance still need review.

Mac Finder/Gatekeeper, Safari, real Ollama/cloud integration, real-footage transcription and long-project performance still require manual Mac QA. Linux source operation has not received end-to-end Linux QA. [Detailed beta status](docs/BETA_STATUS.md) · [Quality limits](docs/QUALITY_AND_LIMITS.md) · [Platform installation guide](https://github.com/VanoPeradze/cutroom/blob/master/docs/PLATFORMS.md).

Report your OS/version, architecture, build ID, browser, exact steps and a short redacted error excerpt in a [reproducible issue](https://github.com/VanoPeradze/cutroom/issues/new/choose). Do not include API keys, private footage or your entire App folder.

**עברית:** הורידו וחלצו את כל החבילה. ב־Windows פתחו `START CUTROOM.bat`; ב־Mac פתחו `START CUTROOM.command`. השאירו את חלון ההפעלה פתוח. Linux זמין דרך קוד המקור ב־GitHub בלבד, ללא חבילת Linux מאומתת. התחילו בעריכה ידנית של סרטון קצר ובדקו את היצוא. [מדריך המשתמש בעברית](docs/USER_GUIDE_HE.md).
