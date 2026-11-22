# Website redesign validation

## Night Drive / production verification

Verified at **2026-11-17 21:04 UTC** after the owner approved publication of the reviewed website. Expo promoted deployment `2fhezil3xl` on the same project to [the canonical website](https://cutroom-studio.expo.app/?lang=he).

- The release export contained only the 152 expected static files: reviewed website assets and unchanged, already-public download packages and guides. No app worktree or unpublished guide was uploaded, no release/tag was changed, and no GitHub source branch was changed.
- Actual canonical HTTP responses for the homepage, privacy page, CSS/JS, three original SVGs, real editor image and both downloadable guides matched the audited local bytes. The real editor image also remains identical to the October 22 production capture.
- Browser verification on the canonical URL passed in English at desktop width (1440) and Hebrew at phone width (390): no page/asset errors, no horizontal overflow, correct direction, playback, alternate cut, shot selection and pinned download links.
- Each of the three public packages was read and SHA-256 verified from **both** its GitHub Release URL and its canonical Expo mirror against the release manifest. Windows: `07b7acecad8ae88e017ddcae03ad2daf04714120a4a734f5a23b304e2b70f51d`; Mac/combined: `5a406f47f7cb24e49f1967fbcd8e06c2cfb51748379e6938f504433b4e4e7b7c`; source: `ac612470059964776266a779e55ae0efb491e23dfbf07ff910da88f44099e35a`.

## Night Drive / local qualification, 17 November 2026

Tested against the main on-disk website, not the public deployment:

- Windows `npm test`: 65 passed, 0 failed, 2 platform-specific skips. `node verify.mjs` validated the public assets, anchors and configured archive checks. The three public JS files passed syntax checks.
- Installed Chromium: 10 width/language combinations (320, 390, 768, 1024 and 1440 pixels; English and Hebrew). Checked play/pause, keyboard seeking, the two edit orders, shot navigation, replay, offscreen stopping, language changes while retaining time/order, system reduced motion, manual pan control, beta links, progressive fallback and real gallery-dialog dismissal. No console/page errors or third-party requests in this run. Desktop/mobile screenshots were inspected; the Hebrew poster tally was repositioned after review.
- No native app or device installation, AI model evaluation, website publication, package preparation, release or Git write action was part of this test.
- The existing `check:assets` reports the **two guide mirrors** out of sync with the locally modified app guides, as it already did before this redesign. The existing mirrors match the pinned public beta's guide text apart from line endings. Do not run a release prep against ahead-of-release docs just to silence that mismatch.

## Previous screening-room validation (12 November 2026)

## Scope

Website-only redesign on base `eec41cf578b7805b1f9c2d493be0cf233b474b91`, reviewed on 12 November 2026. No application code, package bytes, release metadata, retained-download metadata or Expo project identity is changed. The existing archived screenshots are kept with their provenance.

## Automated checks

- Final `npm test` on Linux: **63 passed, 0 failed, 0 skipped**.
- Final Windows test run: 61 passed, 0 failed, 2 platform-specific symlink tests skipped.
- `npm run prepare:download`: all **51** current and historical archives restored with their pinned size and SHA-256 checks. They remain Git-ignored.
- Final `npm run check`: canonical assets, public pages, privacy notice, local assets, anchors, unique IDs, Expo identity, exact downloads and JavaScript syntax passed.
- `git diff --check`: passed.
- Initial remote design commit `12a957517a4bb153f995de6b2c8dcf9eacd501d6` passed [Repository checks](https://github.com/VanoPeradze/cutroom/actions/runs/43148420699).
- Public-page release links target only the retained current 1.3 release. No old GitHub release URL was introduced by this redesign.

## Rendered browser review

The first bounded review used installed Chromium on Windows at 1440 x 1000, 1280 x 900, 390 x 844 and 320 x 740 in both English and Hebrew/RTL. The 144 layout and interaction checks passed after two transient reduced-motion draw-counter flags were diagnosed: canvas draw counts stayed unchanged after the resize/scroll observers settled. Actual desktop and mobile screenshots were visually inspected.

One real defect was found: the active header Download link inherited light text on copper. A targeted active-state rule now preserves dark text, with a regression test. The single final confirmation round passed **80 checks, 0 defects**, with no page errors, console errors or failed asset requests. The header action measured **9.20:1** active contrast and **10.84:1** hover contrast in desktop/mobile English and Hebrew. Final hero captures were visually inspected.

Verified behaviors include:

- No horizontal page overflow across the eight viewport/language combinations.
- Mobile menu, Escape dismissal and language-change focus return.
- Gallery keyboard movement, RTL, Home/End, original-image dialog and Escape focus return.
- Exact Windows and Mac download destinations and visible beta/archival-image disclosures.
- Three synchronized motion controls, pause/resume, offscreen stopping and settled reduced-motion stopping.

Hidden-document pausing is unit-tested and code-reviewed, not browser-runtime verified: the headless browser did not enter a hidden document state. These are browser viewport checks, not physical-phone tests. No native application, clean-install, current-app image, human-listening or AI-quality acceptance is established here. No conversion improvement has been measured.

## Publication

The validation above was completed before production integration. Integration follows the repository's protected-branch PR and required-check workflow; Expo publication is a separate step whose outcome must be verified. No branch-protection, workflow, application-release or archive-byte change is part of this website redesign.

## Purple/cyan palette correction - 12 November 2026

The owner requested the original CUTROOM purple/cyan identity after reviewing the redesign. On base `5f03a05be478acc31b9d8ac845885d015996468d`, the correction changes only site colors, theme-color metadata/cache tags, associated palette tests and design documentation. It preserves page content, product images, download destinations, layout, fonts, motion geometry and scheduling. Cyan identifies primary downloads; violet emphasizes the hero and closing section.

- Windows website tests: **62 passed, 0 failed, 2 platform-specific symlink tests skipped** (64 total).
- Browser QA: **230 checks passed, 0 defects**, in English and Hebrew at 1440 x 1000, 390 x 844 and 320 x 740. Desktop and mobile hero/full-page captures were visually inspected. No page errors, console errors or failed asset requests.
- 114 computed contrast checks passed; the lowest measured foreground/background ratio was **4.82:1**. Active and hover download states, purple/cyan roles, mobile navigation, language and gallery keyboard behavior, pause/resume and reduced motion were covered.
- All **51** local public archives were copied from the existing canonical files and verified against pinned sizes and SHA-256 hashes. No release/tag or application change is included.
- Public-page/asset/anchor/release verification, JavaScript syntax and diff whitespace checks passed.

These checks precede publication and are browser viewport checks, not physical-device or native-app acceptance. Protected-branch integration and public deployment must be verified separately.
