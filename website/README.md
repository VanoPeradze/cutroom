# CUTROOM website

The public introduction and beta-download website lives at **https://cutroom-studio.expo.app/**.
For Hebrew, use **https://cutroom-studio.expo.app/?lang=he**.

This folder is the maintained website source inside the public [CUTROOM repository](https://github.com/VanoPeradze/cutroom).
It does not run the editor, receive footage, process video, or handle user API keys.
The previous separate website checkout is not needed for future updates.

## What belongs here

- `public/`: the English/Hebrew page, styling, scripts, real product screenshots and user guides.
- `app.json`: the existing Expo website project identity, not a credential.
- `release.json`: the approved Windows beta download's exact filename, size and checksum.
- `prepare-download.mjs`: restores that approved ZIP locally without committing it to Git.

The Windows ZIP has three top-level entries: `START CUTROOM.bat`, `START HERE.html`, and `App/`. Windows **Extract All** supplies the enclosing destination folder. Full source and the package manifest are inside `App`; never remove or rename that folder independently of the launcher.

The screenshot in the editor tour uses synthetic test footage.
Only `public/` is deployed. Never put recordings, project files, keys or model weights there.

## Publish a website update

GitHub source changes and Expo deployment are separate steps. Review and commit the
intended files, then use a normal non-force Git push to the reviewed branch of the
public CUTROOM repository. The legacy `PUBLISH.bat git` commands still require a
private target and reject this public repository; keep that guard intact. See the
[publishing guide](../docs/PUBLISHING.md) for the source and packaging workflow.

Install Node.js 22 or newer and sign in to the owning Expo account using its official CLI:

```sh
cd website
npx --yes eas-cli@24.7.0 login
npm run deploy
```

`npm run deploy` restores the approved download, checks its size and SHA-256,
runs the small website tests and link checks, then publishes to the existing Expo project.
It does not deploy to the previous host, push source changes to GitHub, purchase a plan,
upload private app data, or change CUTROOM's local editing engine.

No framework build, global CLI installation, or npm dependency installation is required.
Authentication stays in Expo's normal local credential storage, never in this repository.

### Prepare without publishing

```sh
npm run prepare:download
npm test
npm run check
```

The ZIP is downloaded from the existing public Expo website. If that site is unavailable,
provide the already-approved local archive instead:

```sh
node prepare-download.mjs ../dist/CUTROOM-1.1-beta-20260920-135632.zip
```

An existing ZIP with the wrong checksum is rejected, not overwritten. Review and move it
out of the download folder yourself before retrying. All ZIP files in that folder remain
ignored by Git. The source, checksums and approved screenshots are tracked.

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
