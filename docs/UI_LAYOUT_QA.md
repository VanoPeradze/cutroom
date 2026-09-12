# Layout QA — 2026-09-05

This is a historical validation log. Later sections supersede earlier interaction descriptions and limitations; viewport measurements and test counts apply only to their recorded revision. See the latest sequence-editing section for the current validation status.

Browser checks used a disposable, local two-source project with synthetic footage and Hebrew/English transcript lines. No user footage, account, model download or AI run was needed. Real browser screenshots and DOM measurements were used; the CSS tests are regression contracts, not a simulation of the complete browser cascade.

| Viewport | Checked states |
| --- | --- |
| 1280 × 720 | Studio Edit; transcript selection; expanded subtitle settings; selected clip and trim form |
| 1024 × 768 | Transcript editor, search/filter widths, saved-text controls, preview transport and timeline |
| 390 × 844 | Source routing; Output controls; multiline Hebrew correction and save/navigation buttons; long bilingual project name; home/recent cards |
| 320 × 568 | Keyboard-help and export dialogs, close/cancel controls, content scrolling |
| 800 × 600 | Preparation header, loaded source cards and controls; short-window workspace |
| 1280 × 600 | Height-only compact layout; Captions-to-Edit navigation; timeline clears the sticky header and following inspector |

Two observed failures drove structural fixes: the timeline had more visible children than declared grid tracks, and the fixed-height compact grid allocated less space than the timeline's content. Desktop now uses a non-shrinking flex stack inside a scrollable dock; compact layouts use max-content tracks. Browser measurements after the compact fix showed zero overlap between the timeline canvas and the following inspector.

Other repairs include a real search/filter grid, expandable transcript controls that are not clipped internally, monitor controls responsive to their own container width, wrapping manual-action controls, constrained native selects, viewport-bounded dialogs and a consistent header/job-bar offset.

Validation: the full automated suite passed (628 tests). The final browser pass loaded asset revision 44.

This is not a guarantee against overlap in every browser, OS font, zoom setting or future panel. Active-job offsets and additional desktop/tablet/short-window dimensions have static regression coverage; not every asynchronous job state was exercised visually in this pass. Repeat the browser checks after adding controls, particularly with a clip selected and subtitle settings expanded.

## Follow-up visual polish — asset revision 46

The later quality pass updated color/contrast and control transitions without changing layout dimensions. Browser screenshots at 1280×720 checked Home, source Layout and bilingual Captions; no overlaps were observed in those screens and no browser errors were recorded. YouTube goal and 16:9 controls stayed selected after changing styles and applying Creator Frame. The older draft correctly retained its original aspect label with a rebuild-required notice. The complete automated suite now passes 755 tests. The smaller viewports in the table above were checked in the earlier structural pass, not repeated for this color-only update.

## Direct selection and composition follow-up — 2026-09-08

The default Select tool now marks footage by dragging on the filmstrip or any linked lane; the ruler still scrubs. Kept and removed sections can both be clicked, selection edges adjust across the whole content area, and Snap defaults off. Selection callbacks are delayed until pointer release so a trim inspector cannot move the canvas midway through a drag. Remove and Add to edit are enabled only when they can change the selected range.

An isolated 12-second two-source browser fixture verified plain filmstrip drag → Remove → Add to edit, restoring the original 10-second edited duration without an AI run. At 1280×720, the standard selection actions and all three timeline lanes fit in the dock. A 390×844 check confirmed no document-level horizontal overflow and the canvas begins after the wrapping action bar, not underneath it.

The Stacked chooser now has a measured 9:16 canvas (202.5×360 CSS pixels in the desktop inspector), with camera/primary panes taking 30%/70% of its inner height. Fit was checked on both chooser videos and both monitor videos: all used contain and identity scale. Fill uses proportional cover; layout labels sit outside the composition. Additional geometry tests cover standard aspects, swapped order and export-sized PiP margins. These synthetic checks do not establish quality on every real recording or promise a full multitrack editor.

The final browser pass (asset revision 55) also verified rapid Fit → Fill → Picture in picture changes: the saved draft, monitor and chooser agreed, including after reload. A final 390×844 check showed a visible, wrapping selection hint and a 390-pixel document width. Validation passed: 823 Python tests and 152 frontend tests. Only the disposable fixture was edited; user projects were not modified.

## Timeline layout ranges and workspace controls — 2026-09-09

The editor now has source-time From/To fields, a clickable Layout lane, Zoom to selection, source identity/role cards, source B frame nudges and an availability warning. Selecting a composition saves to the selected interval; no selection means the entire edit. Unsubmitted layout times block composition changes until Select range is pressed. Source roles, framing, audio and sync remain whole-edit settings, explicitly separated from interval layout choices. Sources A and B are still linked, not independently movable tracks.

Browser checks on the disposable two-source fixture verified 1.250–2.750 seconds → Stacked, and 6.125–8.375 seconds → Camera only, preserving surrounding layouts. Clicking the Layout lane selected the exact 1.250–2.750 block and opened the matching inspector. A one-frame source B adjustment updated its offset and coverage warning. Backend tests verify fractional-frame offsets retain precision through 100 consecutive saves.

At 1280×720 the timeline spans the inspector and monitor columns. Preview focus hides those editing panels temporarily; Full screen expands the workspace while keeping Export and the guide available. The large-preview test measured 946 CSS pixels in height in the expanded browser. At 390×844 the final header reserves 129 pixels, all buttons end before the preview begins, and document width remains 390 pixels. A generated-ID collision and an initially shrinking mobile header were found and corrected during browser testing. Final UI assets: app 59, workspace/styles 58, timeline 56. Final checks: 840 Python tests and 189 frontend tests pass; no browser console errors were recorded.

The in-app How to edit guide explains pointer tools, source-time versus edited playback, layout scope, workspace modes and keyboard profiles. Existing interval merging can still absorb an exactly 80 ms restoration inside a larger removed interval; use at least 81 ms for that edge case. This pass does not claim a full multitrack NLE or every browser/display combination.

## Independent A/B tracks — 2026-09-09

This supersedes the linked-track limitation above. Two uploaded sources now have independent source clips on the original A timeline: target selection, split, non-ripple remove/restore, gap-only drag moves, numeric move/trim/slip, reset and Undo/Redo. The global EDIT lane still controls export duration. Preview uses a separate clock; selected audio, captions and waveform follow their own source mapping. B synchronization is frozen after B edits; rebuilds preserve tracks and source replacement invalidates only the appropriate edits. See [Independent tracks](INDEPENDENT_TRACKS.md) for instructions and limits.

Browser checks used only the disposable synthetic two-source fixture, never user projects:

- Removed B at 1–3 seconds, moved its first clip to 1.5–2.5 numerically, then dragged it back into the leading gap. A and the 10-second global output stayed unchanged.
- Removed A at 1.5–2.5, observed B-only playback with A paused and selected-A audio silent; explicit Pause stopped both videos. No console errors in the final run.
- Exported the edited fixture through the actual UI at 1080p/60 FPS; the UI reached “Your video is ready.” Separate FFmpeg tests verify independent moved video/audio, black/silent gaps, 30/70 Stacked and exact 30/60 FPS frame counts.
- Reload retained edits. Trimmed A to 0–1 and moved it to 1.5–2.5. The first transcript line then selected timeline 1.5–2.5 while media A sought to local time 0. Wordless captions stayed visible.
- At 1280×720 the source lanes are reachable in the scrolling timeline dock. At 390×844 the header ended at y=193 and the preview began there; document width remained 390, with wrapping controls and no header/preview overlap. Expanded-editor mode remained available.

Final automated checks: 930 Python tests and 214 frontend tests passed. API integration tests were added after browser testing exposed a missing action-field allowlist; implicit clip IDs were aligned between JavaScript and Python. All runtime changes remain local with no new dependencies. Long reordered HD/4K exports may still buffer substantial decoded footage; the short synthetic fixtures do not establish professional-scale memory/performance guarantees. The timeline is bounded by A's duration and baked-in camera views remain crop/layout controls, not separately recovered recordings.

## Direct clip editing and video-only fullscreen — integration revision, 2026-09-09

This revision supersedes the gap-only movement, fixed A-duration limit and expanded-editor workspace modes described above. Select drags individual clips on their own tracks; an occupied destination inserts/ripples destination clips on that track only, leaving the origin gap. Range or Shift-drag selects intervals for partial removal. Blade splits an individual clip. More contains Add source, Duplicate clip and advanced controls. Sequence duration can grow beyond the original recording length, while each clip's Source in and duration must remain within that recording.

The default monitor is larger, with one draggable video/timeline divider instead of View presets, Inspector toggles or whole-editor fullscreen. The preview's Full screen button targets the composite video wrapper, including A/B, captions and transport; native-fullscreen failure falls back to a video-only modal. Escape exits this video view without also clearing the editing selection. Clip properties move to the inspector, and less common timeline actions are under More. The in-app guide and [independent-track instructions](INDEPENDENT_TRACKS.md) describe these interaction changes.

Current validation used disposable synthetic fixtures only; original user projects were not modified:

- Browser: dragged A's second cut onto occupied A footage. The destination was split/inserted, B stayed unchanged, and Source in stayed at 6 seconds. Numeric placement at 13 seconds extended the edit to 19 seconds while the original recording remained 12 seconds long. Reload retained the sequence.
- Browser: inserted B source footage 2–3 seconds at edit time 20, then duplicated it at 21. The editor and export dialog agreed on a 22-second sequence. The source-in fields remained recording-relative. Export was not started through the UI in this pass.
- Browser: choosing Full source, clicking a clip and pressing Space retained Full source and the active Select tool. Space paused both media elements. Native fullscreen contained only the composed video, captions and transport; Escape restored the editor. A/B playback used their different local source timestamps.
- Browser: the one-file embedded-camera fixture retained its 30% top camera / 70% bottom content split after moving a clip to 13–19. Both cropped views played local time 6 together, with the secondary view muted. No fictitious editable B track was created.
- Geometry: at 1920×1080 the normal portrait monitor was about 469 pixels high and the timeline dock 427 pixels high; native video fullscreen was 968 pixels high. At 1280×720 the monitor retained its aspect ratio and the timeline scrolls to remaining lanes. At 390×844 there was no document-level horizontal overflow; transport and timeline tools wrap without covering the video or canvas. Less common actions close More after invocation, and clip properties stay in the inspector.
- Automated coverage includes actual FFmpeg sequence exports at 30/60 FPS, reordered and repeated footage beyond source duration, missing-source gaps, retimed audio, burned captions/SRT, revision conflicts, Undo/Redo, persistence, lifecycle changes, fullscreen fallback, keyboard focus and pointer hitboxes. The full Python suite passed 978 tests and the frontend suite passed 256 tests (the Python suite includes wrappers that also run frontend tests). Final UI cache revision: 66. The final narrow-screen pass confirmed visible Undo/Redo, a 0.5625 portrait aspect ratio, a 390-pixel document width, and canvas beginning below the toolbar. No browser console errors were recorded in the embedded-source pass.

Remaining boundaries include two source tracks, no overlapping layers within one track, no linked multitrack ripple or per-clip audio mixer, real-source duration limits for each clip and unproven long-form HD/4K memory behavior. A baked-in camera remains a crop/layout view, not an independently recovered source recording.
