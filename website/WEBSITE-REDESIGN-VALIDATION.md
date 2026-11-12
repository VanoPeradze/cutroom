# Website redesign validation

## Scope

Website-only redesign on base `eec41cf578b7805b1f9c2d493be0cf233b474b91`. No application code, package bytes, release metadata, retained-download metadata or Expo project identity is changed. The existing archived screenshots are kept with their provenance.

## Checks

- `npm test`: 62 passed, 0 failed, 0 skipped.
- `npm run prepare:download`: all 51 existing current and historical archives restored with the pinned size and SHA-256 checks. They remain Git-ignored.
- `npm run check`: canonical assets, public pages, privacy notice, local assets, anchors, unique IDs, Expo identity, exact downloads and JavaScript syntax passed.
- `git diff --check`: passed.
- Public page release links target only the retained current 1.3 release. No old GitHub release URL was introduced by this redesign.

Desktop/mobile browser and English/Hebrew interaction review remain pending. This record will distinguish automated website checks from actual rendered review; neither qualifies the native application or measures conversion improvement.

## Publication

This is an isolated design branch, not a production deployment. No PR, master change, release or history rewrite is part of this update.
