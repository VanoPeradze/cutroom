# Website redesign validation

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

This is an isolated design branch, not a production deployment. No PR, master change, release or history rewrite is part of this website update. The existing public site remains unchanged until separately authorized deployment.
