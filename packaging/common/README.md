# CUTROOM 1.1 Beta — Windows, macOS and Linux source

CUTROOM is a free, MIT-licensed video editor for YouTube, Shorts and Reels. It runs on your computer and opens its editing interface in your browser. Import footage, trim and move clips, add media and captions, mix audio, and export MP4 video. Manual editing needs no AI account or models.

## Start from this download

Extract the entire ZIP into a writable folder. It contains **windows** and **mac**; each folder has a launcher, **START HERE.html**, and **App**. Keep them together. This README lives inside App; [open your platform's offline startup guide](../START%20HERE.html).

| Platform | Launcher and prerequisites | Beta status |
| --- | --- | --- |
| **Windows** | Open **windows**, then double-click **START CUTROOM.bat**. Setup accepts Python 3.11/3.12 or can download a private runtime; FFmpeg/FFprobe are required and setup can attempt installation through Windows Package Manager. | Windows beta. First setup needs internet; clean-computer and broad hardware QA remain ongoing. |
| **macOS** | Open **mac**, then double-click **START CUTROOM.command**. Requires macOS 15+ on Apple Silicon or Intel, native Python 3.11/3.12 and compatible FFmpeg/FFprobe. Setup can offer Python 3.12 and **ffmpeg@7** through an existing Homebrew installation after approval. | Source launcher, not a signed/notarized `.app`. macOS 15 automated checks passed on both architectures; Finder/Gatekeeper and Safari manual QA remain needed. |
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

## What this documentation revision changes

This package refreshes the Windows/Mac **README**, the **Mac beta guide** and their **build manifests**. Application code, launchers, setup scripts, dependencies and runtime behavior remain byte-identical to the approved combined beta. Some inherited guides describe the earlier release's packaging; this revision does not establish new platform or AI validation.

Known limits include a shared-editor edge where sub-frame differences between A/B source end times can reject adding extra media. Reinstalling the runtime does not fix it. Added media/text fit within the existing edit and do not automatically ripple with source changes. AI accuracy, source sync and performance on representative real footage still need review. Passing synthetic tests does not establish professional editorial quality.

Mac Finder/Gatekeeper, Safari, real Ollama/cloud integration, real-footage transcription and long-project performance still require manual Mac QA. Linux source operation has not received end-to-end Linux QA. [Detailed beta status](docs/BETA_STATUS.md) · [Quality limits](docs/QUALITY_AND_LIMITS.md) · [Platform installation guide](https://github.com/VanoPeradze/cutroom/blob/master/docs/PLATFORMS.md).

Report your OS/version, architecture, build ID, browser, exact steps and a short redacted error excerpt in a [reproducible issue](https://github.com/VanoPeradze/cutroom/issues/new/choose). Do not include API keys, private footage or your entire App folder.

**עברית:** הורידו וחלצו את כל החבילה. ב־Windows פתחו `windows/START CUTROOM.bat`; ב־Mac פתחו `mac/START CUTROOM.command`. השאירו את חלון ההפעלה פתוח. Linux זמין דרך קוד המקור ב־GitHub בלבד, ללא חבילת Linux מאומתת. התחילו בעריכה ידנית של סרטון קצר ובדקו את היצוא. [מדריך המשתמש בעברית](docs/USER_GUIDE_HE.md).
