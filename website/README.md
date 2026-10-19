# CUTROOM website

The public introduction and beta-download website lives at **https://cutroom-studio.expo.app/**.
For Hebrew, use **https://cutroom-studio.expo.app/?lang=he**.

This folder is the maintained website source inside the public [CUTROOM repository](https://github.com/VanoPeradze/cutroom).
It does not run the editor, receive footage, process video, or handle user API keys.
The previous separate website checkout is not needed for future updates.

## What belongs here

- `public/`: the English/Hebrew page, styling, scripts and generated copies of the real product screenshots and user guides.
- `app.json`: the existing Expo website project identity, not a credential.
- `release.json`: exact filenames, sizes, checksums and provenance for the Windows, standalone Mac, combined and source ZIPs, their tag-specific GitHub URLs and retained Expo mirrors.
- `prepare-download.mjs`: restores those approved artifacts locally without committing ZIPs to Git. A shared Mac/combined artifact is verified once; conflicting shared metadata is rejected.
- `retained-downloads.json`: historical 1.1 and previous 1.2 archives that remain verified and deployed at their original mirror paths, including on a fresh checkout.
- `prepare-assets.mjs`: copies exactly six canonical repository files into `public/`, entirely offline.

Edit screenshots in `docs/images/{welcome,editor,ai-options}.png`, user guides in
`docs/USER_GUIDE_EN.md` and `docs/USER_GUIDE_HE.md`, and the license in the root `LICENSE`.
Their copies under `public/assets/` and `public/downloads/` are generated and ignored by
Git. The helper checks all source and destination paths before writing, rejects symbolic
links, preserves the exact bytes, and leaves already-matching copies untouched.
The favicon and approved ZIP checksum sidecar remain maintained website files.

The Windows and Mac downloads each have their own platform launcher beside `App/` and `START HERE.html`. The optional combined ZIP has exactly two top-level folders: `windows/` and `mac/`. Each has its platform launcher, `START HERE.html`, and `App/`. Both contain the same approved application source; Mac adds its own setup/help files. Never remove or rename `App` independently of its launcher. The combined builder preserves the complete Windows ZIP selected by `packaging/windows/release-baseline.json`. A product update therefore needs a newly built and reviewed Windows baseline; a documentation refresh changes no application or launcher payload. See the distinct release paths below and [Mac validation](../docs/MAC_BETA.md).

The marketing page uses an original editorial studio design informed by public video-editor website references; see DESIGN.md and PRODUCT.md.
The maintained hero image is `public/assets/studio-edit.png`, refreshed on 19 October 2026. It and the other five `studio-*.png` images are untouched browser captures of the current local editor, using an original eight-second STUDIO SESSION title card and procedural audio in a disposable demonstration project. No third-party footage, real person, private source recording or project data is included. Recapture them whenever the editor's layout changes. The hero is a still image, enlarged on demand. The three canonical documentation screenshots are copied byte-for-byte by prepare-assets.mjs.
Only `public/` is deployed. Never put recordings, project files, keys or model weights there.

## Publish a website update

GitHub source changes and Expo deployment are separate steps. Review and commit the
intended files, then use a normal non-force Git push to the reviewed branch of the
public CUTROOM repository. The legacy `PUBLISH.bat git` commands still require a
private target and reject this public repository; keep that guard intact. See the
[publishing guide](../docs/PUBLISHING.md) for the source and packaging workflow.

The `master` branch is protected. Push a feature branch and open a pull request;
repository checks, dependency audit and CodeQL must pass before merging. Direct
pushes, force pushes and branch deletion are blocked, including for administrators.

Install Node.js 22 or newer and sign in to the owning Expo account using its official CLI:

```sh
cd website
npx --yes eas-cli@24.7.0 login
npm run deploy
```

`npm run deploy` restores the approved download, prepares the canonical assets, checks the ZIP's size and SHA-256,
runs the small website tests and link checks, then publishes to the existing Expo project.
It does not deploy to the previous host, push source changes to GitHub, purchase a plan,
upload private app data, or change CUTROOM's local editing engine.

No framework build, global CLI installation, or npm dependency installation is required.
Authentication stays in Expo's normal local credential storage, never in this repository.

### Prepare without publishing

From a fresh clone, prepare and verify the screenshots, guides and license offline:

```sh
cd website
npm run prepare:assets
npm run check:assets
npm test
```

`npm run check:assets` is read-only and fails if a generated file is missing or stale.
CI runs this offline preparation and verification without downloading the ZIP or deploying.
For the complete website check, also restore the approved download:

```sh
npm run prepare:download
npm run check
```

`npm run check` refreshes canonical assets automatically before checking every public link.

The ZIPs are downloaded from the pinned GitHub Release. Historical Expo URLs remain
available as mirrors, and deployment includes the current verified files under
`public/downloads/`. Never remove them when changing the primary links. If GitHub is unavailable,
provide the already-approved local archive instead:

```sh
node prepare-download.mjs PATH_TO_APPROVED_COMBINED_ZIP
```

The optional local path restores the combined ZIP; restore the Windows, standalone Mac and source files
from their exact local approved archives or listed URLs into `public/downloads/` as needed, then run the normal
checks. Mirror use never bypasses the pinned size/SHA-256 checks.

An existing ZIP with the wrong checksum is rejected, not overwritten. Review and move it
out of the download folder yourself before retrying. All ZIP files in that folder remain
ignored by Git. Canonical source assets and release checksums are tracked; generated copies are not.

## Change the beta download deliberately

### Prepared beta: 19 October 2026

The release uses dated public filenames:

- Windows: `CUTROOM-1.2-Beta-Windows-20261019.zip`
- Mac: `CUTROOM-1.2-Beta-Mac-20261019.zip`
- Optional Windows + Mac: `CUTROOM-1.2-Beta-20261019.zip`
- Exact source: `SOURCE-20261019.zip`

Use tag `v1.2-beta-20261019` for the primary GitHub links. Each file has a matching
`.sha256` sidecar. The standalone Mac archive puts `START CUTROOM.command` beside
`App/`; only the optional combined ZIP requires opening the `mac/` folder first.
Public filenames are byte-identical copies of the qualified review archives and
projection. Do not rebuild them after qualification. Root release metadata must
record the frozen source commit, actual archive hashes and new native results
before publishing. Current local link preparation does not establish publication.

### Previous public beta: 18 October 2026

The `v1.2-beta-20261018` release targets application source
`fe35453119305a33e0890a25e627a4fa47ad353d`. It preserves the original review ZIP names
and bytes. Windows uses `CUTROOM-1.2-Beta-Windows-review-fe35453.zip`; Mac uses
`CUTROOM-1.2-Beta-combined-review-fe35453.zip` and must open its `mac/` folder.
`SOURCE-fe35453.zip` is the matching source archive. There is no separate tested Mac ZIP.

This is an explicitly authorized public beta with accepted limits, not a fully
qualified production release. Native automated Apple Silicon/Intel evidence is
run [39139136807](https://github.com/VanoPeradze/cutroom/actions/runs/39139136807)
at orchestration head `7e18c1c622968985cbcbc33abdb33a185a2b2bd3`, distinct from
the application source. Each architecture passed 69 offline checks, 340 feature
tests and all 50 required cases with zero skips, including fresh App setup, missing-pip
recovery and restart persistence. Transcription and model accuracy, Ollama/cloud AI,
physical clean-device installation, Finder/Gatekeeper/Safari and representative
English/Hebrew editing and listening acceptance remain pending. The beta preparation
gate requires exact native provenance and explicit acceptance of those limits.

A pristine Windows 10 Sandbox first run, after installing WinGet 1.29.380,
private Python 3.12, FFmpeg and Ollama, failed a native DLL check (launcher exit 1,
no health endpoint). Microsoft Visual C++ x64 runtime is a prerequisite that the
launcher does not install. In a separate fresh Windows 10 Sandbox with WinGet
1.29.380 and Microsoft-signed Visual C++ x64 runtime 14.51.36247.0 installed first,
the unchanged launcher completed setup and `/api/health` reported `ok: true`,
FFmpeg/FFprobe available, `1.2-beta` and no models. The runtime installer exited 0
without a reboot; all three checked MSVC DLLs were absent before and present afterward.
The final fresh-guest probe also received the homepage with HTTP 200, confirmed
the default configuration was unchanged and found no model files. This establishes
conditional setup and first HTTP launch, while full guest, physical-device,
restart and UI acceptance remain pending.
The [official Microsoft x64 runtime download](https://aka.ms/vc14/vc_redist.x64.exe)
is linked separately in the English/Hebrew installation help.

Retain historical releases and Expo mirrors, including all three October 18 archives.
The October 18 production deployment is immutable at
`https://cutroom-studio--jph8u884uj.expo.app/`; its identifier is `jph8u884uj`.
The older October 15 deployment `mkiullrc9j` also remains available.
An authorized rollback can use the existing pinned CLI:

```sh
npx --yes eas-cli@24.7.0 deploy:alias --prod --id=jph8u884uj --non-interactive
```

### Release qualification and promotion

An editor update must reach the Windows and Mac payloads from the same frozen,
reviewed source. Use the existing [review-candidate workflow](../packaging/REVIEW_CANDIDATES.md)
and [publishing guide](../docs/PUBLISHING.md), verify manifests and archive inventories,
and run the required native checks against those exact candidate bytes. Keep
historical validation pins intact. Prior-release test results cannot qualify a new
application package.

Update `release.json`, checksum sidecars, visible download links, provenance and
website checks together. Restore all four new archives locally, verify their sizes
and hashes, then run the website checks before the authorized production deployment.
Download the public ZIPs again afterward and compare their bytes, checksums, build
identity and representative application files. A successful deployment alone does
not establish that the downloads contain the new editor.

For a documentation-only archive refresh, use the supported packaging workflow
and its exact existing baseline requirements. Do not substitute another payload
under an existing beta filename. Do not use a documentation refresh for code changes.

Website checks do not prove AI editing quality or a successful installation on
another computer. Expo hosting remains subject to its plan limits and terms;
video editing stays local.

The editor workflow is **Media → Edit → Layout → Audio → Captions → Output**.
Green screen lives in **Edit → Effects · Green screen**; Layout contains picture
composition, sizing and framing. Current screenshots must show this actual workflow.
