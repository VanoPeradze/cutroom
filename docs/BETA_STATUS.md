# Beta status and limitations

**An exploratory Windows beta for feedback from creators and editors. Not a production release, security certification or promise of professional-quality automatic edits.** Public access to a download does not change those quality boundaries.

## Project management and custom text — 2026-09-28

- All 1,539 Python regressions and 516 frontend checks passed. Python includes frontend wrappers, so these totals overlap. Coverage includes project focus and revision conflicts, confirmed deletion, original-file preservation, subtitle parsing, text autosave, timeline bounds and export behavior. Tests used synthetic projects; no paid AI calls or user recordings were used.
- An isolated browser project verified rename/search/delete cancellation, bilingual SRT import and replacement, immediate text edits, independent text dragging, Undo, reload persistence, source/edit preview switching and Space playback. Welcome, project dialogs and captions were checked at 390 pixels without page-level horizontal overflow. Stale layer selection is cleared so a second Delete cannot target a previously selected footage range.
- The lobby and Projects expose Open editor, Rename and confirmed permanent Delete; Projects also searches and sorts names. Deleting refuses active work without cancelling it. The confirmation explains which imported copies, project files and CUTROOM exports are removed, and that original files outside CUTROOM remain untouched.
- Custom titles/captions preview immediately, save after typing pauses and have editable timeline layers. UTF-8 SRT/VTT import is limited to 1 MiB and 2,000 cues; project text is limited to 2,000 items, 1,000 characters each and 16 simultaneous items. Imports keep text/timing, using CUTROOM's style presets instead of file-specific formatting.
- Custom text uses edited-video time and always burns into the MP4, independently of AI subtitle burning. Optional SRT combines AI and custom captions, excluding titles. Text does not automatically ripple with A/B; shortening that would leave a layer past the new end is rejected. Same-position text can overlap, and three positions/style presets do not provide a full motion-graphics or professional NLE toolset.
- App and website surfaces and controls are softer, with decorative diagonal arrows removed. This source validation does not certify a clean-PC installation, long-project performance or AI quality. The website release manifest identifies the actual downloadable build; source changes alone do not establish that its archive or deployment has been updated.

## Editor precision and track protection — 2026-09-28

- All 1,492 Python regressions and 481 frontend checks passed. Python coverage includes frontend wrappers, so these totals are not independent scenarios. This includes 43 new backend protection checks. Repository link and diff-whitespace checks passed.
- An isolated synthetic two-source browser project verified Snap-on extension into a gap, the bounded saved edge, Undo/Redo and reselection with the restored duration, Space play/pause, and Original footage review. Toolbar layouts at 390 and 768 pixels had no page-level horizontal overflow. No real AI calls, model downloads or user footage were used.
- Snap is optional and starts off. It aligns trims/ranges and source reorder starts; added-media moves can align either edge. Added media remains on its independent clock during A/B reordering. Frame readouts use integer output FPS, not source/drop-frame timecode or a guarantee of frame-exact browser decoding.
- A/B edit locks persist when reopening and stay outside Undo/Redo. Browser checks verified protected pointer/keyboard edits, editing and undoing on the other source, toggling protection without stopping playback, and read-only Original footage on a locked scope. No browser warnings/errors were observed; the new protection controls introduced no page-level horizontal overflow at 390 pixels.
- Synthetic FFmpeg smoke exports passed at 60 FPS in 16:9 and 9:16. Locks leave the rendering graph and render-input fingerprint unchanged. This is not a long-4K benchmark or a clean-machine installation test.
- Website checks passed (24; two file-symlink cases skipped on Windows). The public editor image is an actual capture of the current synthetic project, not a mockup.
- This increment is prepared for the source ZIP and matching website download. The website release manifest identifies the exact downloadable archive; [the editor roadmap](EDITOR_ROADMAP.md) describes remaining gaps and subsequent verification gates. Packaging or deployment failure must be reported, not treated as a release.

## Media, mixing and quality update — 2026-09-23

- All 1,410 Python regressions and 420 frontend checks passed in this update. Synthetic FFmpeg checks cover added video/images/audio, fades, mixer buses, picture-only speed, cancellation and QHD/4K output dimensions. AI/provider responses were mocked; no billable requests or model downloads were used.
- An isolated browser project verified image/audio import, visible media lanes, waveforms, autosaved volume and fades, continuous mixer playback and scrollable timeline bounds. Failed/cancelled imports expose Retry; imports release editing controls when finished.
- Added media currently fits inside the existing edit. Main-timeline changes and AI rebuilds that would strand those clips are rejected without deleting them. Picture speed keeps duration and original speech timing, so it can lose lip sync or hold the final picture. Solo is preview-only; export normalization/limiting may change final loudness.
- Local bilingual recovery is bounded and flags low-confidence lines for human review. These tests do not demonstrate a measured improvement on real Hebrew/English recordings. Clean-PC setup, long 4K sessions and multilingual accuracy still need real-user validation.
- The public archive is named `CUTROOM-1.1-Beta.zip`; its internal manifest retains a unique build ID and checksums. Models, runtimes and private projects remain excluded.

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

Default YouTube cleanup is chronological, not a full narrative rewrite. Styles are pacing/selection presets, not creator replicas or reliable visual gameplay-event detectors. Camera proposals need confirmation. There are two main sources plus bounded media/text layers, not unlimited NLE tracks. Those added layers do not automatically ripple with source edits. Source-only edits may intentionally leave gaps or change synchronization. Lower-rate footage exported at 60 FPS repeats frames.

Keep backups and use copies, not urgent client deliveries. Review the exported file. Do not expose the server publicly. This is not a frozen offline executable: allowed dependency versions can change between installations.

Start with a few editors across different PCs, including CPU-only and NVIDIA systems. Separate installation problems from editing and AI-quality feedback. Use the [feedback form](BETA_FEEDBACK.md), measure correction time and fix repeatable blockers before expanding.

Older validation notes describe historical checks, not certification of this build. This document and the current package manifest are the beta entry points.
