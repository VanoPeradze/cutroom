# Website surface

CUTROOM is a free, open-source local video editor. It supports editable cuts, captions, a genuine source/layer audio mixer, optional AI drafts and MP4 export. The website explains and distributes it; it does not run the editor or accept recordings.

The maintained static HTML/CSS/JavaScript website is website/public in VanoPeradze/cutroom, deployed through its existing Expo Hosting project at https://cutroom-studio.expo.app/. English is the default and ?lang=he switches to Hebrew/RTL without browser storage.

The current public beta targets exact application source `fe35453119305a33e0890a25e627a4fa47ad353d` at tag `v1.2-beta-20261018`. The original Windows review ZIP is 3,708,965 bytes (SHA-256 `d20f33568ebaeb702717baade8e2a76dda88cb10e81461d61cc48ec96f725aca`). Mac uses the original combined review ZIP, 7,452,329 bytes (SHA-256 `e6973fcace0766e43767e0a14e1833dc35e820b9e5b19895ed57e688ff2ff731`), then its `mac/` folder. There is no separate tested Mac ZIP. Exact names, the source archive and all hashes are in `release.json`; historical mirrors remain available.

This is an authorized beta with disclosed limits. Automated native Apple Silicon and Intel checks passed; transcription/model accuracy, Ollama/cloud AI, physical clean-device installation, Mac Finder/Gatekeeper/Safari and representative English/Hebrew editing and listening acceptance remain pending. Linux uses source installation and is not bundled. Mac is an unsigned source launcher. AI is optional; providers and model downloads retain their documented consent/prerequisite requirements.

A pristine Windows 10 first run without Microsoft Visual C++ x64 runtime failed a native DLL check. The launcher does not install that prerequisite. Conditional setup and startup health passed for the unchanged build in fresh Windows 10 Sandbox after installing WinGet 1.29.380 and Microsoft-signed Visual C++ x64 runtime 14.51.36247.0. Full guest, physical-device, restart and UI acceptance remain pending. The landing page discloses both results beside the downloads and in the Windows setup help, with a separate official Microsoft runtime link that survives language switching.
