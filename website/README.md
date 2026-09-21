# CUTROOM website

The public introduction and beta-download website lives at **https://cutroom-studio.expo.app/**.
For Hebrew, use **https://cutroom-studio.expo.app/?lang=he**.

This folder is the maintained website source inside the public [CUTROOM repository](https://github.com/VanoPeradze/cutroom).
It does not run the editor, receive footage, process video, or handle user API keys.
The previous separate website checkout is not needed for future updates.

## What belongs here

- `public/`: the English/Hebrew page, styling, scripts and generated copies of the real product screenshots and user guides.
- `app.json`: the existing Expo website project identity, not a credential.
- `release.json`: the approved Windows beta download's exact filename, size and checksum.
- `prepare-download.mjs`: restores that approved ZIP locally without committing it to Git.
- `prepare-assets.mjs`: copies exactly six canonical repository files into `public/`, entirely offline.

Edit screenshots in `docs/images/{welcome,editor,ai-options}.png`, user guides in
`docs/USER_GUIDE_EN.md` and `docs/USER_GUIDE_HE.md`, and the license in the root `LICENSE`.
Their copies under `public/assets/` and `public/downloads/` are generated and ignored by
Git. The helper checks all source and destination paths before writing, rejects symbolic
links, preserves the exact bytes, and leaves already-matching copies untouched.
The favicon and approved ZIP checksum sidecar remain maintained website files.

The Windows ZIP has three top-level entries: `START CUTROOM.bat`, `START HERE.html`, and `App/`. Windows **Extract All** supplies the enclosing destination folder. Full source and the package manifest are inside `App`; never remove or rename that folder independently of the launcher.

The screenshot in the editor tour uses synthetic test footage.
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

The ZIP is downloaded from the existing public Expo website. If that site is unavailable,
provide the already-approved local archive instead:

```sh
node prepare-download.mjs ../dist/CUTROOM-1.1-beta-20260921-195226.zip
```

An existing ZIP with the wrong checksum is rejected, not overwritten. Review and move it
out of the download folder yourself before retrying. All ZIP files in that folder remain
ignored by Git. Canonical source assets and release checksums are tracked; generated copies are not.

## Change the beta download deliberately

Build and test a clean source-only package with CUTROOM's allowlist packager. Update
`release.json`, the checksum sidecar, visible version/size/download links and `verify.mjs`
together as appropriate for the release. Extract the ZIP and check that
`START CUTROOM.bat`, `START HERE.html`, and `App/` remain together and that the launcher
starts the expected build. Supply the newly approved ZIP locally for its first
website deployment; the live site cannot supply a file that has not been published yet.
Do not silently replace a beta under an existing filename.

Website checks do not prove AI editing quality or a successful installation on another PC.
Expo hosting remains subject to its plan limits and terms; video editing stays local.
