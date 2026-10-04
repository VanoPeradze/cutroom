# CUTROOM editor roadmap

Research date: 27 September 2026; implementation status updated 28 September. Baseline inspected: `d0c215f`; delivered additions include precision snapping, persistent A/B protection, project management and custom text/caption layers. The six rounds below separate implemented scope from remaining work. This is a staged development plan, not a claim of feature parity with DaVinci Resolve or Adobe Premiere. Each completed increment needs its own verification and publication on GitHub, in the downloadable ZIP and on Expo.

## Direction and evidence

Prioritize an editor that makes the result of an action predictable: what is selected, which clock is shown, which tracks move, and what Undo will restore. Learn the interaction principles without copying another application's complete interface or shortcut semantics.

Blackmagic's official [Editor’s Guide to DaVinci Resolve 20](https://documents.blackmagicdesign.com/UserManuals/DaVinci-Resolve-20-Editors-Guide.pdf), Lesson 2, printed pages 93–94, teaches ripple trimming through its consequences for later clips and track participation. Its [training curriculum](https://www.blackmagicdesign.com/ca/products/davinciresolve/training) progresses from a rough cut through trimming, replacement, audio, and delivery. The PDF's indexed relevant excerpts were consulted; the web reader could not load the entire 51.6 MB document.

Adobe documents [snapping](https://helpx.adobe.com/premiere/desktop/edit-projects/change-clip-sequence/snap-clips.html) to clips, markers, and the playhead with a visible alignment guide. Its [Source and Program Monitor model](https://helpx.adobe.com/premiere/desktop/get-started/source-and-program-monitor-adjustments/about-source-monitor-and-program-monitor.html) distinguishes preparing original material from reviewing the assembled sequence. These support the first priorities below; CUTROOM's delivery order is our judgment based on its existing architecture.

## Existing foundation and remaining gaps

| Area | Evidence in CUTROOM | Remaining work |
| --- | --- | --- |
| Timeline precision | [timeline.js](../web/timeline.js) has selection, split, range moves, zoom, frame-bounded edge trims, and optional snapping. The current increment adds visible Snap controls, named alignment guides, cross-track/media targets and bounded trim feedback. | Maintain the precision checks below as new commands are introduced; fractional-rate and drop-frame support remain separate work. |
| Editing semantics | [sequence.py](../cutroom/sequence.py) supports linked ripple operations, duplicate, source insertion/restoration, gap closure, framing, and picture speed. Together shortening ripples A/B and layout; source-only shortening leaves a gap. | Explicit roll/slip/slide operations and consistent participation across every layer. Existing ripple support must not be described as missing. |
| Track model | [source-tracks.js](../web/source-tracks.js) maps two A/B source lanes onto an independent edit clock. The current increment adds persistent protection for those two lanes. [media-studio.js](../web/media-studio.js) adds media, waveforms, fades, placement, and role-based audio mixing. | Shared ripple participation across source and added-media layers, then user-managed tracks. Added media currently uses a separate clip array. [media_library.py](../cutroom/media_library.py) rejects sequence shortening that would strand added clips beyond the new end, rather than rippling those clips. |
| Text and captions | [text-studio.js](../web/text-studio.js) provides typed titles/captions, immediate preview, autosave, movable/trimmable text layers and SRT/VTT import. [text_clips.py](../cutroom/text_clips.py) validates edit-clock timing and bounds; custom text burns into MP4 and caption-kind text can join optional SRT output. | Shared ripple participation, richer typography and graphics remain separate work. Text stays at its edit time during source reordering, and shortening past a text item is rejected. Imported text does not replace the AI transcript. |
| Project library | Lobby and Projects offer Open editor, Rename and explicit permanent Delete; the dialog adds search and sorting. Revision checks, busy-job guards and error recovery protect existing work. | Project management does not add source bins, relinking, cloud storage or unlimited tracks. Permanent deletion has no undo. |
| Source review | [source-review.js](../web/source-review.js) separately previews original footage, shows kept/removed regions, restores missing material, and offers deliberate copy insertion. | Fast source-to-sequence assembly, persistent source marks, and media organization beyond the existing library. |
| Recovery | [editing.py](../cutroom/editing.py) already stores bounded undo/redo snapshots; [server.py](../server.py) checks revisions and [projects.py](../cutroom/projects.py) serializes updates and saves atomically. | Preserve these guarantees as commands span more tracks. Project concurrency locks are not user-facing track locks. |
| Playback and export | [media.py](../cutroom/media.py) prepares cancellable compatibility proxies; source preparation uses them when originals are not browser-ready. [render.py](../cutroom/render.py) exports original source media. | Optional performance proxies for already-compatible large files, visible proxy status, and measured long-project performance. |

The [editing guide](INDEPENDENT_TRACKS.md) remains the behavior contract. [keyboard.js](../web/keyboard.js) explicitly provides subsets of other editors' keymaps; reverse/multispeed J/K/L and full clipboard editing are not implemented. Keep those limitations visible.

## Round 1 — precise snapping and trim feedback

Implemented in the current increment; the gate below must be satisfied before calling the release complete. The existing engine remains in place and Snap defaults to **off**.

- Move Snap into the always-visible timeline toolbar. Include the pre-drag playhead, A/B boundaries, and added media/audio boundaries as appropriate targets. Freeze the playhead reference during a gesture.
- Apply snapping to trims and media gestures, including both ends of media moves. Preserve leading-edge behavior for ripple reorders, translating affected-lane targets into the position after origin removal. Exclude visual timeline padding as a target.
- Show a guide that identifies the target, output-clock frame time as `HH:MM:SS:FF`, and the actual bounded trim position. Alt bypasses magnetic alignment; Escape cancels the gesture.
- Keep source bounds, neighbor collisions, active target, project identity, and revision conflict protection authoritative. Do not migrate projects or add dependencies for this increment.

Gate: deterministic tests at 24/25/30/50/60 FPS and several zoom levels; nearest-target ties and pixel thresholds; both media edges; self-target exclusion; ripple target remapping; frozen playhead; source limits; Snap off/Alt; Escape/pointer cancellation; project or target changes during asynchronous commits. Browser checks must compare the visible guide and released position, verify one undoable edit, and confirm source-review timing remains independent. Frame labels alone do not prove exact decoding or fractional-rate support.

## Round 2 — track control and participation

Define the command contract before adding more lanes. [Premiere Track Lock](https://helpx.adobe.com/premiere/desktop/edit-projects/change-clip-sequence/track-lock-to-prevent-changes.html) prevents clip changes while retaining preview/export; [Sync Lock](https://helpx.adobe.com/premiere/desktop/edit-projects/change-clip-sequence/sync-lock-to-prevent-changes.html) concerns participation in time-shifting operations. CUTROOM must distinguish editing target, linked selection, edit protection, and ripple participation.

Current scope: **Edit → Track protection** locks A or B after a draft exists. A protected lane keeps playing and exporting, with its audio unchanged. The other source can still be edited independently. Lock choices persist with the project, outside Undo/Redo; changing a lock neither consumes an undo step nor clears redo. Together edits and history entries that would change a protected lane are rejected atomically. Protected framing, picture speed and source timing are guarded as well. Unlock protected sources before draft generation/refinement, reset operations affecting them, or source replacement/removal. Shared layout, mixer and added-media edits remain independent.

Current gate: exercise pointer, keyboard and API mutation routes, locked-lane history rejection, editing and undoing the unlocked lane, save/reopen, stale revisions and legacy projects. Rejected operations must leave project, revision and history unchanged. Confirm that protection does not mute or hide preview/export and that independent layout, mixer and added-media work remains usable.

Still pending in this round: visible ripple-participation controls for A/B, added-media and custom-text layers, with a shared transaction that plans all affected clips, layouts, captions and audio before committing. Specify fixed music, spanning overlays, gaps and locked clips. Each mixed-layer ripple must commit completely or leave state unchanged. Retain the existing rejection of shortening that would strand added media or text until its replacement is implemented and tested. Stable track IDs, ordering and arbitrary user-created lanes come afterward, with a versioned migration; A/B locks and text layers do not complete that work.

## Round 3 — explicit trim modes

Add one mode per delivery with named controls and numeric feedback. Adobe's [ripple](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-ripple-edits.html) changes downstream timing; [roll](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-rolling-edits.html) moves a shared cut while preserving combined length; [slip](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-slip-edits.html) changes the source interval while retaining timeline placement; [slide](https://helpx.adobe.com/premiere/desktop/edit-projects/trim-clips/perform-slide-edits.html) moves a clip and compensates in its neighbors.

Start with roll, then slip, then slide. Add outgoing/incoming frame previews where they help judge the cut. Preserve existing Together/source-only behavior as explicitly named behavior. Picture-speed controls are not a substitute for slip or synchronized A/V time-stretch.

Gate: source handles and neighbor constraints bound every operation; roll/slide preserve the intended total duration; slip preserves placement and duration. Verify captions/audio against the chosen source mapping, locks from round 2, one-step undo, and real exported boundary frames. Introduce rational timebase support separately before advertising 23.976/29.97/drop-frame accuracy.

## Round 4 — source assembly and organization

Build on Original footage: remembered source In/Out marks, explicit Insert/Overwrite at the sequence playhead, and Match frame back to the original. Label source time and sequence time independently. Offer a docked source/program arrangement on large screens and a clear switcher on small screens. Add searchable names and bins after clip identity and relinking rules are stable.

Gate: repeated use of the same source never confuses marks; Insert shifts only declared participants; Overwrite affects only its declared interval; restoration still avoids unintended duplicates. Test reordered footage, negative/positive A/B sync offsets, empty edits, keyboard focus, and save/reopen.

## Round 5 — measured playback and performance

Extend the existing proxy pipeline with optional performance proxies, regeneration, cancellation, and visible original/proxy status. Adobe's [proxy workflow](https://helpx.adobe.com/in/premiere/desktop/organize-media/ingest-proxy-workflow/ingest-and-proxy-workflow.html) separates lightweight editing copies from full-resolution finishing. Keep that separation explicit and preserve original-based export.

Gate: record startup, seek latency, dropped frames, memory, and A/V drift on a documented machine and repeatable long/reordered 1080p/4K fixtures. Compare original/proxy frame positions and exports; exercise missing proxies, cancellation, interrupted preparation, and relinking. Set performance targets from the baseline rather than promising unsupported throughput. Advanced color, keyframes, transitions, sample-level audio, multicam, and interchange should each receive a later scoped plan.

## Round 6 — release qualification

Apply this gate to every completed increment, including intermediate work in rounds 1–5. Each needs targeted frontend tests, relevant backend sequence/media/API tests, and a short manual keyboard/pointer walkthrough. Timing changes also require real FFmpeg fixtures covering picture, sound, captions, and gaps, extending existing `test_gapless_timeline.py`, `test_sequence_render.py`, and linked-edit tests. Recheck persistence and stale-revision failures when state contracts change.

Keep manual editing usable without AI or model downloads. Reuse synthetic or permitted local footage. Update the English/Hebrew guides and shortcut notes with the delivered behavior. A passed test suite is not evidence of professional parity, long-project performance or a clean-machine installation.

Publication is complete only when all three destinations agree on the verified increment:

1. **GitHub:** commit the reviewed source and release metadata, pass the required PR checks, and merge through the protected branch workflow.
2. **Windows ZIP:** build the same application source through the allowlist packager and privacy scanner, verify the manifest/checksum, and check the extracted launcher, help, source and guide links. Preserve earlier archives and record the new build identity. Document any clean-machine or real-footage validation still outstanding.
3. **Expo:** update the approved download metadata, checksum, relevant guides/screenshots and visible release information, supply the new ZIP locally, deploy the website, and verify the live download and assets.

These are separate operations in the [publishing workflow](PUBLISHING.md), but all are required for each completed, verified increment. Report an unfinished destination explicitly; source publication alone does not complete a release.
