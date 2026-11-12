# Website surface

CUTROOM is a free, open-source local video editor. It supports editable cuts, captions, source/layer audio mixing, optional AI drafts and MP4 export. The website explains and distributes it; it does not run the editor or accept recordings.

The maintained static HTML/CSS/JavaScript website is `website/public` in VanoPeradze/cutroom, deployed through its existing Expo Hosting project at https://cutroom-studio.expo.app/. English is the default and `?lang=he` switches to Hebrew/RTL without browser storage. The screening-room redesign uses a graphite and copper opening, a lightweight original animated film-frame field, warm paper sections, locally hosted licensed fonts and a functional workspace tour. See DESIGN.md for the current visual direction and browser review scope.

## Current package identity

The current 11 November 1.3 beta uses exact product source `ba67003726e80e0d394b1927b6b710f191a60157`. Its tag is `v1.3-beta-20261111-hebrew1`. Windows uses `CUTROOM-1.3-Beta-Windows-ba67003.zip`; Mac uses `CUTROOM-1.3-Beta-combined-ba67003.zip` and its `mac/` folder; `SOURCE-ba67003.zip` carries matching source. There is no standalone Mac archive. Public files must remain copies of the frozen, qualified archive bytes, never rebuilds. `release.json` records exact sizes, hashes, native evidence and accepted limits. Preserve previous public downloads and historical mirrors for rollback.

## Current behavior

The updated editor retains source In/Out marks when opening Add source footage. It offers Insert and Overwrite, including optional placement into a captured timeline range. Overwrite replaces the selected source sequence span without changing total sequence duration, respects protected scopes, and supports Undo/Redo. Source selection is not silently discarded. A refreshed editor hierarchy improves workspace navigation, control organization and panel readability. These are CUTROOM implementations inspired by established editing workflows, not imported Kdenlive code.

Existing audio behavior remains: newly added video layers include source sound when available; Media offers include/exclude, clip volume, fade and mute controls. Saved silent overlays retain their setting. Picture speed changes video only; layer sound remains at normal speed from Source in. The compact, expandable AI draft notice retains actual/target duration without covering the preview. Import failures caused by missing FFprobe explain repair and retry, while failed media replacement preserves saved edits.

## Qualification boundaries

This is a source-based beta with disclosed limits. New native validation results must match the new downloads; prior-release checks cannot establish them. Configured hosted-runner setup, real synthetic-media export and automated regression checks are not clean-OS or physical-device acceptance. Process restart is not an OS reboot. Transcription/model inference, Ollama/cloud AI, physical-device installation, Mac Finder/Gatekeeper/Safari and representative English/Hebrew editing and listening still need manual acceptance. Current-app visual acceptance and fresh app captures remain pending. Website browser QA is separate and must not be presented as native application QA.

Linux uses source installation and is not bundled. Mac is an unsigned source launcher. AI is optional; providers and model downloads retain their documented consent and prerequisite requirements.

Windows requires WinGet and Microsoft Visual C++ x64 runtime before first launch. The launcher does not install that Visual C++ prerequisite. The landing page explains the requirements and links to Microsoft's official runtime in both languages. Package-specific setup results belong to the dated release record; they do not establish physical-device or manual acceptance.

## Product imagery

The main workspace screenshots were captured on 19 October 2026 at 1600 × 900 in the actual editor, using an original eight-second STUDIO SESSION title card and procedural audio. Project/export images are dated 15 October; the AI setup image has no recorded capture date. They contain no third-party footage, real person or private user project. The gallery labels them as archival, not proof of the newly packaged interface or AI editing quality. Do not relabel them as new or substitute invented product controls.
