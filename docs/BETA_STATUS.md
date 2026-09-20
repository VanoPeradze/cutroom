# Beta status and limitations

**An exploratory Windows beta for feedback from creators and editors. Not a production release, security certification or promise of professional-quality automatic edits.** Public access to a download does not change those quality boundaries.

## Keyboard preset update — 2026-09-20

- All 1,260 Python regressions and 378 frontend checks passed, including new tests for profile focus, per-binding help, snapping, Premiere Extract and reviewing original footage without a selection.
- Browser checks used disposable synthetic footage: selecting Premiere immediately enabled C/S, Pro Tools F7/F8 selected the range/move tools, and closing shortcut help returned focus to the timeline. Shift+R opened Original footage without an edited-timeline selection. No browser console errors were observed.
- These are supported keyboard subsets, not complete emulations of other editors. The help distinguishes adaptations and unassigned actions. No real media, AI inference or clean-PC installation was tested in this pass.

## Simplified Windows download — 2026-09-20

- The ZIP now opens to only `START CUTROOM.bat`, `START HERE.html`, and `App/`. Complete source, guides, tests and license files remain in App; the existing editor and installer are unchanged.
- All 1,260 Python regressions and 10 website tests passed. Windows launcher tests used harmless stubs to check normal/error exit codes, a folder name containing spaces and special characters, and clear help when App is missing. Offline guide links and legacy ZIP verification are covered.
- This layout change does not reorganize an existing installation or migrate its projects. New first-run installation still requires separate clean-PC testing.

## Initial 1.1 Beta validation — 2026-09-20

- 1,238 Python regression tests, 369 frontend tests and 9 website tests passed. The final cloud-transport cleanup also passed 121 focused cloud, cache and publishing checks.
- Real synthetic FFmpeg exports passed for horizontal and vertical output, 60 FPS, two separate sources, and a single recording with an embedded camera. Pixel checks confirmed camera above gameplay in the embedded layout.
- Browser checks covered the updated AI choices, custom endpoint/model fields, destination consent text and a narrow viewport without horizontal overflow. Repository and Windows installer static checks passed.
- Cloud tests use simulated responses and sockets. No real provider key, billable inference or user recording was used; this does not certify every compatible provider or AI editing quality.
- This is still not a clean-PC installation test. The fresh downloadable source ZIP excludes personal data, API keys, installed runtimes and model weights.

## Historical validation record — 2026-09-12

The results below describe that packaging pass, not a continuously updated test counter or certification of the latest source. The website identifies its specific downloadable build; source changes may be newer than that archive.

- All 1,087 Python regression tests and all 324 frontend regression tests passed in this packaging pass, including 16 package/document checks.
- Windows installer scripts passed static verification: files, syntax and bootstrap guards. This is not a fresh-PC installation test.
- Recent isolated browser checks covered linked/independent editing, original-footage restore, gap closing, edge trims, clip moves, saved state and playhead-centered zoom.
- Synthetic FFmpeg tests cover actual rendering, output shape, captions and 30/60 FPS sequence behavior. They do not benchmark real speech/story quality.
- Packaging uses an allowlist and fresh defaults, excluding personal projects, recordings, logs, runtimes and weights. TEST_BUILD.json lists per-file SHA-256 hashes.
- The extracted source package passed isolated HTTP startup, a horizontal YouTube cleanup/export, a vertical embedded-camera export with pixel checks, 70 targeted Python checks and all 324 frontend tests. These reused this PC's existing Python dependencies and FFmpeg; they are not proof of clean-machine setup.

## Still unverified

- Clean Windows first installation without the developer's environment, including external installers/download services.
- Transcription and editorial quality across languages, accents, noise and overlapping speech. No multilingual WER/CER acceptance benchmark is complete.
- Quality on representative editor-owned gameplay, explanations and long-form footage; no blind professional-editor comparison.
- Long/reordered 4K sessions, low-memory machines, non-NVIDIA performance and broad codec/hardware coverage.
- Usability and real time saved for new users.

## Boundaries

Default YouTube cleanup is chronological, not a full narrative rewrite. Styles are pacing/selection presets, not creator replicas or reliable visual gameplay-event detectors. Camera proposals need confirmation. There are two sources, not unlimited NLE tracks. Source-only edits may intentionally leave gaps or change synchronization. Lower-rate footage exported at 60 FPS repeats frames.

Keep backups and use copies, not urgent client deliveries. Review the exported file. Do not expose the server publicly. This is not a frozen offline executable: allowed dependency versions can change between installations.

Start with a few editors across different PCs, including CPU-only and NVIDIA systems. Separate installation problems from editing and AI-quality feedback. Use the [feedback form](BETA_FEEDBACK.md), measure correction time and fix repeatable blockers before expanding.

Older validation notes describe historical checks, not certification of this build. This document and the current package manifest are the beta entry points.
