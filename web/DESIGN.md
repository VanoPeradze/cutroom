# CUTROOM / The workbench

## Surface

**Operate.** The editor is a precision tool. It uses graphite, quiet cyan controls and restrained violet identity. It is not the public screening-room site: no marketing animation, oversized controls or ornamental background effects.

## Visual system

- Graphite dark surfaces: #17191c, #22252a, #292c31, #34383f.
- Neutral gray light surfaces: #b5b9bf, #b9bec5, #c2c6cb, #cdd0d4. Raised controls remain gray (#d8dade), never white panels.
- Violet marks the primary action and active workspace. Cyan highlights focused controls. Dark mode uses #bca9df for primary actions and #9cbfd0 for control accents; light mode uses #63517f with white button text.
- Source tracks remain distinguishable through muted blue-gray and violet. Sound and text retain semantic colors without neon or glow.
- Geist with Noto Sans Hebrew is shipped locally with both SIL Open Font Licenses. Proportional text and tabular numerals replace decorative monospace. Caption and video pixels are not restyled by the UI theme.

## Design tokens

`tokens.css` loads first and is the only place theme values are defined: surfaces, text, lines, accents, status, type, spacing, motion, timeline canvas colors and toolbar icons, for dark (default) and light. Feature stylesheets read tokens and never redefine them at `:root` or `html[data-theme=light]`. Scoped overrides that belong to one region, such as the darker monitor and timeline wells in light mode, stay beside that region.

New and reworked screens use the design-system scale at the end of `tokens.css`:

- Type: `--fs-12` captions and meta, `--fs-13` controls, `--fs-15` body and inspector values, `--fs-20` panel titles.
- Spacing: the 4px grid, `--space-1` (4px) through `--space-10` (40px).
- Surfaces: `--surface-1` app frame, `--surface-2` panels, `--surface-3` controls and cards, plus `--surface-well` for inputs and lists.
- Text: `--text-1`, `--text-2`, `--text-3`.
- Accent: one `--accent` for primary action, selection and focus, with `--accent-text`, `--accent-soft` and `--on-accent`.

### Edit panel (27 November)

Clip tools are grouped by intent: **Cut** (Split leads on its own row, then Cut out and Duplicate clip), **Selection** (Range, Clear selection, Zoom to selection) and **Footage** (Review original footage or Add to edit, Layout, Reset to draft). Each group is a labelled `role="group"`. The keyboard profile and Shortcuts sit in a quiet footer. `edit-panel.css` loads last and uses only the `tokens.css` scale. Every button keeps its id, label, disabled state and handler. An odd last button spans its row. Compact layouts keep 44px targets.

### Timeline toolbar and command palette (28 November)

- At 1440px and wider (and at least 540px tall) the timeline's tool row and navigation row join into one 44px line: tools, navigation, status, timecode, zoom, more (`timeline-toolbar.css`). Narrower screens keep the two rows. An empty timeline draws a 30-second ruler instead of a crowded one.
- `Ctrl/Cmd+Shift+P` or the Commands button in the top bar opens a palette of every visible, enabled command on the current screen. Choosing one clicks that same button, so handlers, checks and undo are unchanged. `Ctrl/Cmd+K` stays Split.
- Right-click on the timeline selects the clip under the pointer (Select or Move tool only) and opens Split, Duplicate, Remove, Add to edit, Layout, Zoom to selection, Clear selection and Close gaps. Track headers and shelf items list their own buttons. Each item clicks the existing button and is disabled while it is. Shift+right-click and text fields keep the browser menu (`context-menu.js`).
- Tooltips (`tooltips.js`) share one style, appear on hover and on keyboard focus, and show the shortcut of the active keyboard profile (also set as `aria-keyshortcuts`). The control's title stays the text source.
- Accessibility audit (axe-core, WCAG 2.0/2.1 AA, all six screens, both themes): zero violations after darkening two light-theme labels (`--ok-text`, `--cyan-text`). WCAG 2.2 target size: crop sliders get a 24px hit area; the ducking checkbox sits in a 32px clickable label row (`a11y.css`).

### Animated word captions (28 November)

Six word-timed caption styles share one timing model (`WORD_CAPTION_STYLES` in `cutroom/captions.py`) and differ only in how the spoken word looks: Word highlight (yellow), Word pop (yellow, scales in), Word box (dark text on a yellow plate), Neon word (green glow), One word (a single word at a time, scales in) and Key words (yellow active word, numbers and long content words in orange for the whole line). The preview (`caption-styles.css`) uses the same colours as the burned-in ASS. Right-to-left lines stay plain short phrases, as before, because libass loses Hebrew word order once colour overrides split a line. Animations stop under reduced motion.

### One-click cleanup (28 November)

Edit > Cut > Clean up… (also in the command palette) reads the edit's own captions in edit time and lists long pauses (a 0.25 s breath stays), isolated hesitation sounds, optional filler words (unticked: they often carry meaning) and repeated takes (a caption whose opening words the next one repeats). Nothing changes until Remove. The approved places go to the server as one `sequence_ripple_delete_ranges` edit, applied from the end backwards, so it is one Undo step. Edits with imported media or text layers keep using Cut out one range at a time. Captions without trustworthy word timing are ignored.

### Opener and auto zoom (28 November)

- Edit > Cut > Opener… ranks the edit's sentences (numbers, key words, questions, exclamations, talking to the viewer; each result says why) and copies the chosen one to the start as a cold open with `sequence_duplicate_range` (one Undo step; the original stays in place).
- Color & motion > Auto zoom on key words adds a short punch-in (ease in 0.25 s, hold 1 s at 115%, ease out) on numbers, long content words and exclamations, at least 4 s apart, within the 32-keyframe limit and never over existing keyframes. Each punch is four ordinary keyframes the user can delete.

### Sound effects (28 November)

Media shelf > Sound effects lists seven original sounds (whoosh, swipe, pop, click, ding, hit, riser) synthesized by `scripts/generate_sfx.py` with fixed seeds, so they are Cutroom's own and rebuild byte for byte. Play previews; Add imports the sound into the project media through the normal import, where it is placed and mixed like any audio.

### Style packs (28 November)

Edit > Cut > Style pack… asks "How should it feel?" and offers eight packs (Clean, Bold social, Podcast, Gaming, Minimal, Explainer, Cinematic, Vintage). A pack sets the caption style and the colour look together; the energetic ones also add auto zooms on key words. Each part stays editable in its own control. What the video is (content type) stays with the existing edit styles.

## Script view

`Script…` in the Edit panel opens a non-modal panel docked right
(`script-view.js`, `script-view.css`). It shows the edit's captions as
running text in edit time, one paragraph per caption, each in its own
direction. Click a word to jump; drag or Shift+click to select; Delete,
Backspace or Remove selection cuts that span (padded 0.04 s into the
surrounding pauses) through `sequence_ripple_delete_ranges`, one Undo step.
The spoken word is highlighted during playback. Paragraphs with estimated
word timing carry a dotted underline and a tooltip.

Find (Ctrl+F inside the panel) highlights every place a phrase is said;
Enter and Shift+Enter step through them and Remove all cuts them together.
Shared pure helpers live in `transcript-search.js`.

## Type an edit

`Type an edit…` opens a dialog where the user writes what should change, in
English or Hebrew: remove pauses / hesitations / fillers / repeated takes,
cut a time range, delete every use of a phrase, find a phrase or go to a time,
add an opener, zoom on key words. `prompt-edit.js` matches known edit phrases
on this computer (no network, no model) and always shows what will happen
before the Remove / Go / Do it button runs it. Unknown requests say so and
point to the example chips.

## Brand kit

`Brand kit…` (`brand-kit.js`) collects what makes every video look like the
creator's. The brand colour is the project setting `caption_accent`
(`#RRGGBB` or empty): it replaces the spoken-word colour of the word-timed
caption styles and the key-word colour of Key words, both in the burned-in ASS
(`cutroom/captions.py`) and in the preview (`--caption-accent` on the preview
stage). A logo is an imported image added as one image layer for the whole
edit, sized to keep its shape with an even margin in the chosen corner.
Templates keep caption style, position, size, words per caption, brand colour
and colour look, and are stored in this app on this computer.

## Voice cleanup

The Audio mixer's “Clean up voice (export)” sets `audio_mixer.voice_cleanup`.
On export the recorded speech and voiceover buses go through a gentle local
chain (`VOICE_CLEANUP_FILTER` in `cutroom/media_render.py`: high-pass,
FFT noise reduction, light compression, presence EQ) before their faders and
ducking. The preview plays the original sound, and the label says so.

## B-roll ideas

`B-roll ideas…` (`broll.js`) reads the edit's transcript and lists sentences
where a cutaway would help (they point at something, give a number or name
things), at most one every 6 s and never in the first 1.5 s, with what to
show. An imported image or clip whose file name matches what is said is
preselected; Place adds it full frame, without its sound, for about 3 s as one
Undo step. Nothing is searched online.

## Clip content scores

Each Clips card with a transcript also shows Hook, Complete and Clarity
(`content` from `cutroom/clip_board.py::_content_scores`), each 0–100 with the
plain reason: what the first line does, whether the clip starts and ends on
whole sentences, and filler, pace and how much is spoken. They sit beside the
measured sound/energy strength and never replace it.

## J/K/L shuttle

In the CUTROOM, Resolve, Premiere and Final Cut profiles, L plays forward and
each further L doubles the speed to 2× and 4× (`SourceTimelineClock.setRate`,
players and library media follow); J plays backwards by stepping the playhead
(silent), also up to 4×; K stops and returns to 1×. A small badge on the
preview shows the speed. Pro Tools keeps its own L.

## Finish in another editor (EDL / FCPXML)

The Export dialog links to an FCPXML 1.8 file (Final Cut Pro, DaVinci Resolve,
Premiere Pro) and a CMX3600 EDL. Both are built on request from the saved edit
and describe the main edit only: which part of source A or B is seen and heard
when. Layouts that show A and B together put B on the track above A. Layers,
captions, colour, zooms and the audio mix stay in CUTROOM and are named in a note
inside the file, so nothing is silently dropped.

## Supercut (keep only what matches)

In the script's find bar, "Keep only these" keeps each sentence where the
search is said (widened to the sentence by punctuation or a pause, at most 25
words each way) with a little air around it, and removes everything else in
one Undo step. Typed edits understand "keep only the parts about …",
"supercut …" and "השאר רק את …".

## Batch: several recordings at once

Projects → "Process several recordings…" takes many files. Each becomes its
own project (named after the file, with the open project's look and the chosen
goal) and runs import → prepare → transcribe and first edit, one after another
so the computer never does two heavy jobs at once. "Clean up" is the default
because it needs no Story AI. The page keeps the screen awake while it runs and
must stay open; a failure is shown on its row and the queue moves on.

## Long video → shorts

On a wide edit, the Clips board shows "Make shorts copy (9:16)". It saves a
project copy (same cuts, colour, captions and layers; the original is not
changed), names it "… shorts", switches the copy to 9:16 with the existing
output-aspect path, and opens its Clips board so moments can be exported.

## Translated subtitles

The Export dialog's "Subtitles in another language" asks the configured Story
AI to translate the edit's visible caption lines, 30 at a time, into one of 12
languages and downloads a separate .srt with the same timing (Hebrew ↔ English
by default). The project's captions are never changed; a line the AI does not
return keeps its original text, and the status says how many were translated.

## Composition

The application launcher presents three real starting actions as compact rows beside the welcome statement, followed by recent projects and optional AI setup. It is not a second marketing landing page.

The editing workspace retains the established media pool on the left, monitor in the center, inspector on the right, resizable timeline below and all six workspace tabs. Search, four media-type filters and List/Grid view stay together in the pool. Native buttons, inputs, tab roles and handlers are preserved; no simulated controls are introduced.

Inspectors use consistent material, headings, form rhythm and selected state. The workspace rail uses compact horizontal icon-and-label groups on desktop, stacked labels on phones. Existing screen-size adaptation and geometry controllers remain authoritative.

The timeline canvas resolves semantic CSS tokens rather than staying permanently dark. Theme changes redraw the paused timeline without altering any source, waveform, clip coordinates, time, drag state or edit callback.

## Interaction and verification

Hover only changes color/border. Focus is visible and never replaced by hover. Reduced-motion and forced-colors alternatives are explicit. The design introduces no recurring animation, remote assets, telemetry or dependency installation.

Required checks: both themes, desktop and compact layout, all six tabs, real media import/filter/view behavior, editable text and captions, manual edit/undo, output controls, repeated dialog open/close and contrast. Layout and runtime tests use an isolated synthetic project, never the user's working media.

## November 15 editing-workbench increment

A persistent Inspector / AI Director switch keeps the existing AI suggestions beside the timeline across all six workspaces. AI connection and Transcription open the original dialogs; viewing the panel never starts AI or edits the project. Choosing an editing workspace returns to its Inspector. Existing suggestion, review, undo and export guards remain authoritative.

The media pool can be shown or hidden independently from the Inspector. Only its display preference is stored, and hiding a panel preserves the actual player, source nodes, playback position and editing controls. The timeline spans edge to edge with a compact control rail. This is an incremental editing workspace, not feature parity with DaVinci Resolve.

The timeline navigation rail exposes exact project-frame timecode, previous/next edits on the active track and a searchable Timeline Index. The index is derived from real source cuts, video/image/audio layers, custom text and transcript captions. Choosing an item seeks and opens its existing inspector; it does not create an edit, bypass a locked track or start AI. Search and type filters stay local, and long lists are incrementally revealed. Invalid or out-of-range timecodes do not move the playhead. Source Review keeps its separate source clock and controls.

Manual entry opens a saved empty editor. The first video import becomes a full-recording timeline without waiting for AI. Subsequent media retains the existing source In/Out, Append, Insert and Overlay workflows. The current engine is video-first: audio-only or image-only empty projects are not supported, and the interface states that limitation rather than inventing a result.

Imported media can be dragged from its real library card onto the edit timeline. A timecoded preview states exactly whether the operation is an in-edit overlay/add or a video append after the end. Snapping follows the current timeline toggle, with Alt bypass. Hovering or cancelling never creates an edit; successful placement uses the existing undoable media actions and opens the original inspector. Source slots and external files are not drag-placement targets. The card buttons remain the keyboard/touch alternative and source In/Out remains explicit.

Multi-file import uses one visible serial queue. The first selected video initializes an empty manual timeline and the other files enter the media pool, not the edit. Completed imports survive Stop. Queue progress and errors remain readable, while successful completion collapses its disclosure to give the media cards priority. Storage paths/capacity remain available in a native Storage details disclosure rather than taking over the pool.

## November 16 mixed-layer Insert increment

Holding Shift while dragging a ready video inside the timeline performs a true Insert, opening time and moving later clips across tracks. Its preview is a boundary and rightward arrow with the added duration, not an overlay band. Ordinary drag remains Overlay/Add; a video dropped at the tail remains Append. Dragging uses the full video; source In/Out stays an explicit review action, with the same native Insert readiness checks.

Crossing static video, audio, images and user text are split around the inserted shot. The right pieces retain their independent picture/audio source positions, outer fades and compositing order. Unsafe crossings are explained and blocked, including active fades, animated visual motion, tiny retained pieces and guarded caption/timed plans. Track locks and server validation remain authoritative. Insert pins the project revision rather than replaying a stale time after a conflict. A successful operation selects the real inserted occurrence and supports Undo/Redo/reopen; subsequent edits clear obsolete success feedback.

Native browser validation used a synthetic mixed-layer edit, actual mouse/Shift gestures and original inspector controls. It verified 0.5x picture versus normal-speed audio clocks, read-only blocked previews, exact Undo/Redo/reopen and unchanged original-file hashes. Separate engine validation renders pixels/audio before and after insertion. This is a bounded editing increment, not complete professional-editor parity.

## November 16 Together Cut out increment

The existing Together range-removal command closes time across supported mixed layers. Fully contained layer occurrences are removed from the edit, not from the media pool. Crossing static visuals, audio and custom text retain the correct surviving source portions; later content moves earlier. Source-only A/B removal still leaves a gap without moving independent layers. Selecting one media occurrence and pressing Delete still removes only that occurrence.

A read-only Cut out preview lives in the existing navigation row. Its expandable panel describes the actual selected range, duration change and occurrence counts: removed, trimmed, split and moved earlier. A/B scope explicitly states that duration and other layers stay put. The same app readiness policy supplies visible blocked reasons and protects all native action paths; the preview does not invent a second safety policy or replacement Delete button. Playback does not rescan the unchanged preview every frame.

The panel is portaled above the editor's clipped timeline and closes on Escape, outside interaction, project changes or Home. It adds no permanent timeline row and remains bounded in dark/light, compact and RTL layouts. Explicit typed or marked source ranges clear stale layer/caption targeting before notifying the app, so keyboard Delete cannot remain aimed at an old occurrence.

Validation uses actual range entry, toolbar removal, keyboard and two-click Cut out, exact Undo/Redo/reopen, guarded partial effects and unchanged original hashes. This does not add arbitrary source tracks or general mixed-layer ripple for every move, trim or overwrite.

## November 16 selected-layer Split increment

Split targets the selected imported-media or custom-text occurrence instead of silently cutting source A/B beneath it. The main Split command, eligible editor shortcuts, media inspector and Blade share native validation. Source footage retains its existing A/B scope, and automatic speech captions remain unsplittable by the clip tool. Splitting adds no timeline time, does not move other layers and selects the new right occurrence through the original inspector.

Media Blade previews the same output-frame time it will submit. A click commits on release, not on press; Escape, pointer cancellation, a changed project/tool or dragging away does not cut. While saving, repeated clicks cannot dispatch a second split. Hover feedback remains visible when lower media lanes are vertically scrolled and explains blocked motion, fade interiors and too-short pieces. The complete reason is also available in the canvas title. This feedback uses the app's real readiness policy, not a simulated operation.

Static splits preserve independent picture and audio source clocks and the original outer fades. Pan/zoom that would restart, a cut inside an audio fade and unsupported short pieces stay protected. Main and inspector readiness follow the displayed playhead, including over source gaps or locked A/B tracks when the selected independent layer is otherwise editable. Selecting source footage restores its original split path; native input and toolbar keyboard behavior remains protected.

Validation covers actual main/inspector/keyboard/Blade edits of slow video, audio, image and title, exact Undo/Redo/reopen, real cancellation, unchanged source files and existing AI-panel/Export-dialog behavior. This is a bounded selection-aware editing workflow, not arbitrary-track editor parity or new AI generation.

## November 16 selected-layer Trim increment

Trim start/end targets the selected media or custom-text occurrence, not source footage underneath it. Q/W in supported keyboard profiles and compact inspector buttons use the same one-edge native command. Source A/B keeps its existing scope and ripple behavior when explicitly selected. Independent-layer trimming leaves the edit duration and all other occurrences unchanged, retains the same clip ID and remains one undoable action.

Media edge dragging now previews the canonical native result at the output-frame boundary. It does not locally rescale fades or clamp a negative picture source to the first frame. Only the dragged edge is changed; an existing off-frame opposite endpoint is preserved. Source availability, visual motion, fades and minimum length use the same readiness as the actual command. Blocked drags keep the original geometry instead of painting a false approximation. Escape, cancellation and project/tool changes restore the preview; save-pending guards suppress duplicate dispatch. Ordinary whole-occurrence moves keep their existing behavior.

Static clips can reveal genuinely available earlier/later content within the edit. Independent sound and picture in-points advance correctly for a retained head. A safe cut through a flat region removes only the trimmed edge's fade and keeps the untouched outer fade. Cuts inside a fade, extension that would relocate an existing fade, pan/zoom phase changes and unavailable sound/picture remain explicitly blocked. Existing numeric Start/End fields remain explicit timing edits; the new Trim actions and edge handles are the content-preserving workflow.

Action rows wrap in the existing inspector without a new permanent panel. Disabled media actions are visibly dimmed and retain their complete reason in the title; blocked text Trim actions no longer imply an ongoing wait. Native validation covers slow video, audio, image and custom text, exact history/reopen, actual muted playback into the retained head, unchanged source-only behavior and original-file hashes. This remains a bounded editor increment, not arbitrary-track parity.

## November 16 source Slip increment

An explicit Slip tool changes the source window inside an imported video or audio occurrence, leaving its position and length fixed. Rightward dragging reveals later source; leftward dragging reveals earlier source. It does not borrow Alt, alter the existing keyboard profiles or pretend to support source A/B, still-image or text slipping. The timeline ruler still seeks normally. Source in and the inspector's earlier/later one-frame controls use the same native command.

The gesture rounds only its signed delta to the output frame interval, preserving an existing fractional source in-point and both timeline endpoints. Timeline magnets do not apply because no edit boundary moves. The canonical app preview supplies sound/picture in-points and real bounds. Unsupported proposals restore the original content rather than clamping or falling through to a move. Escape, cancellation, changed project/tool or changed pointer scale cancels; release rechecks readiness and saves once.

The timeline tooltip describes the signed content offset and source/picture in-points with fixed-timing wording rather than suggesting a new placement. Live timeline and viewer previews use the same source-only patch. The compact toolbar uses a distinct fixed-edge, bidirectional icon with the original accessible button name. Motion and fades remain allowed because their timeline phase and envelope do not change. This is Slip for imported media, not a general Slip/Shuffle mode or complete NLE emulation.

## November 16 selected-layer Duplicate increment

Duplicate at playhead reuses the existing main Clip tools command and media/text inspector actions. It targets the selected imported video, audio, image or custom text, not source footage underneath it. The copied occurrence has a new ID, is selected immediately and retains the original source clocks, speed, fades, motion, framing and text/template styling. The destination is on the edit clock, including while Full source is previewed.

Independent-layer duplication is a copy placed inside the current edit: no ripple, overwrite, extension or shortening to fit. The output-frame-aligned start retains the original whole duration. Insufficient room, readiness and capacity limits have disabled-state explanations. Selecting actual source A/B retains the prior source-specific duplicate behavior; automatic speech captions are not silently redirected to source footage.

No new permanent tool, drag modifier or shortcut is added. Existing wrapping action rows carry the explicit label. Blocked custom-text duplication uses a not-allowed cursor rather than implying a save is running. This is occurrence duplication, not another physical copy of the source asset or full clipboard editing.


## November 16: fixed-duration selected-layer Move

The selected media/text inspector has a compact, native Timeline placement disclosure: Move to playhead and explicit one-output-frame earlier/later commands. These are separate from Slip's source-content controls and from Start/End timing fields. Moving preserves the same occurrence identity, whole length, source clocks, effects and style. Other layers and edit duration remain unchanged. A playhead destination is frame-aligned; nudges retain an existing fractional placement rather than reanchoring it.

Existing imported-media/custom-text body dragging uses the same guarded native Move policy. Its exact head/tail magnets, Alt bypass and full-occurrence boundary clamps remain; it never rounds the old duration. Canonical placement-only previews feed the live viewer and timeline, with a no-ripple label or actual blocked reason. Preview restoration, cancel/Escape/lost capture, project/tool changes, pointer-scale changes and pending-save guards prevent accidental or repeated writes. Source A/B dragging, automatic captions, edge Trim, Slip and keyboard profiles retain their distinct existing behavior. No new permanent toolbar tool or modifier gesture is added.
The four media/text Start and End controls accept exact fractional seconds without invalid-step warnings. Their explicitly scoped arrows and vertical scrub still use 0.01-second increments from the existing fractional anchor; misleading browser one-second spinners are hidden only for those controls. These fields remain separate timing edits, not whole-layer Move commands.


## November 16: imported visual stacking

A compact Visual stacking disclosure reorders one selected imported video/image among the project's imported visuals: Send backward, Bring forward, Send to back and Bring to front. Its rank is global, including non-overlapping clips. A step can cross a clip that is absent at the current cursor, so the UI does not promise that every click visibly changes the current frame. This is overlap priority, not timeline track assignment.

Only visual entries are permuted within their existing visual slots. Audio-only entries, timing, source clocks, full duration, effects and the mixer stay intact. Source footage remains below imported visuals; text retains its separate rendering layer. Selection/cursor remain stable, with a single guarded Undoable action and readiness reasons at stack boundaries. No new timeline tool, gesture or shortcut is added.

The browser's custom-text layer is explicitly above all supported imported-media priorities, matching export, but below automatic captions and viewer controls. This corrects the old z-index limit that could let a later visual cover custom text after ten-plus imported occurrences. It does not imply arbitrary cross-type stacking or text reordering.


## November 16: reversible occurrence enablement

The selected imported-media/custom-text inspector includes one explicit **Enabled in preview & export** checkbox. Off suppresses the occurrence's picture and associated sound, or custom text, without deleting it, closing a gap, changing duration or disturbing other occurrences. Audio Mute remains a separate sound-only choice. Automatic transcript captions retain their existing visibility controls; source A/B is not covered by this command.

Disabled items stay in their original timeline lanes, remain editable and keep their snap boundaries and structural protections. A neutral fill, quieter thumbnail/waveform, dashed unselected outline and **Disabled** label communicate output exclusion without making selected handles unusable. The Index retains actionable entries, includes their disabled state in visible/accessible text and permits searching for Disabled. It never confuses a disabled occurrence with an unavailable HTML button.

No new toolbar tool or gesture is introduced. The canonical native action, preview/export filtering, boolean validation, exact Undo and stale-save protection are implemented with the engine/inspector partner. Legacy clips without the new field remain enabled.

Native QA also exposed an existing Index readiness problem: opening it during a load/save could leave its buttons disabled after the editor became ready. Readiness transitions now update the existing rows and status in place, without rebuilding the list, clearing search or moving focus/scroll. This is separate from occurrence enablement; an off clip is still a selectable item.

## November 16: direct viewer framing

The existing Position & size inspector can explicitly open a selected imported video/image's frame in the edited viewer. Drag its body to move, or one of eight inside-the-canvas grips to resize freely. This changes only normalized frame geometry. It does not trim, slip, ripple, reorder, change sound, or restart pan/zoom; Fit/Fill remains a separate content choice. The existing percentage fields remain the precise, single-pointer and keyboard alternative and retain fractional values from viewer gestures.

One pointer release commits one guarded native frame transaction. Preview is transient, not a saved edit; click/no-op, Escape during a gesture, lost pointer capture, changed saved revision, selection, cursor or viewport discard it. Escape again or Done framing closes the mode. Playback, Full source, disabled/inactive/nonvisual occurrences and leaving the edited viewer invalidate the mode. Pending saves block repeat gestures rather than pretending an already-dispatched transaction can be cancelled. A separate frame-preview slot cannot erase pending numeric fields.

The overlay is an editing affordance above the rendered picture/text, not an alteration of compositing priority. A selected picture may still be covered by later visuals. The centre Play overlay is hidden only while framing; the ordinary transport remains available. No new permanent toolbar, modifier gesture, rotation or aspect-lock promise is introduced.

## November 16: original source at the selected picture time

The selected imported-video inspector can open its original source at the edited playhead, using the existing source In / Out review. In Select/Move, a plain double-click on a video occurrence opens the source at that clicked edit point; the host positions the edited cursor there only after readiness validates. The contextual inspector action preserves its existing cursor. Original source timing follows the independent picture in-point and speed, not the normal-speed sound clock. Disabled or covered clips remain inspectable.

This is source navigation, not an edit or a new toolbar mode. Original source playback is normal speed without edited effects or mix. Opening does not change source marks, persist browser marks, insert footage or flush pending edits. Saved marks and ordinary pool In / Out keep their existing behavior. Loading, metadata/identity changes, pending saves, Full source mode, an inactive occurrence or an exhausted picture range have explicit readiness reasons rather than approximate source/A/B fallbacks. Browser seeking is not advertised as frame-accurate stepping.

Double-clicking images, audio, custom text, source lanes or empty space retains the previous Fit behavior. Automatic-caption opening and Blade/Slip/range-tool behavior remain separate. A video source-open failure never silently fits the view. A compact origin note distinguishes the selected original picture point from edited time and the source soundtrack; the native dialog retains keyboard and explicit Close/Keep controls.

## November 16: inspect a saved AI proposal before applying

A preserved AI result is a proposal, not the currently active manual timeline. Its review sheet compares the current timeline with the server-validated result of applying the saved draft. Candidate source selection duration remains separate from that resulting mixed-edit duration. Imported media/custom text preservation, track-lock or bounds blockers, saved request and actual engine warnings are explicit. No frontend estimate invents an application result or silently removes/retimes layers.

The original-source audition is deliberately limited to primary A passages at normal speed. It does not preview source B, the final composite, effects or the edited mix. Passage selection seeks while paused; an explicit play is required before Apply becomes available, without claiming that playback verifies semantics or approves an edit. Keep, Escape and Close release source media without changing or dismissing the saved proposal. Apply uses the reviewed identity and revision through the existing guarded host transaction, only once, with Undo available.

Current/after cards, source monitor and a scrollable passage list share one native dialog. The content scrolls inside a stable header/footer so Keep and Apply remain reachable on compact screens. The review reuses gray surfaces, restrained cyan selection and ordinary focus-visible controls. It adds no permanent editor toolbar mode and never swaps the live edited viewer into an unapplied candidate.


## November 16: truthful save state and protected explicit drafts

The existing project-header save indicator is a compact native recovery button, not a new Save-all command. Saved, Saving, Unsaved changes and Save failed are distinct text states aggregated from the real editing and save queues. Only actionable states receive a chevron/border and keyboard focus; the accessible description explains what remains and where activation will go. Failed queued settings can retry their existing save, while an unapplied effect or caption opens its existing editor without applying it.

Chroma candidates remain local until Apply. Unrelated project revisions no longer erase them; actual source, saved-effect or background conflicts retain the candidate visibly and block unsafe application. Discard changes removes only that local candidate, whereas Reset this source remains a separate saved edit. Home, New, Open and new Export cannot silently abandon explicit Chroma/caption drafts. Browser unload includes pending and in-flight work, without claiming local drafts survive a forced tab close or power loss.

The status never fades to unreadability when nonactionable. It keeps the same real project-name control and is visible in compact layouts: a second medium-width header row and a third narrow-screen row prevent the action group from covering failed/unsaved work. The existing gray surfaces, restrained status colors, keyboard focus and RTL flow are retained. Draft recovery uses the existing inspector and opens a collapsed transcript disclosure rather than introducing another modal or toolbar.

Native fault-injection checks distinguish recovery semantics: text keeps a failed candidate for retry/discard; media restores the saved fields and preview on failure, including a still-focused numeric/range control; settings retain their retry queue. No change to the saved edit model, export compositor or AI generation is implied by this frontend reliability increment.


## November 16: real AI requests alongside the current edit

The AI Director pane now docks the original instruction, length/fallback and request-review action rather than duplicating a form or sending the user back to Setup. Exact DOM nodes, values, listeners, host visibility and focused editing semantics are retained; ordinary Inspector/Overview navigation restores their original homes synchronously. Goal, style, output, source selection and audio remain their existing Setup controls. An explicit context boundary makes Manual projects request AI only from this pane, while Manual entry elsewhere stays manual.

The compact request note names Source A and the saved goal/style. The original instruction counter and autosave are live. Pane edits save only the request field changed, never hidden rounded audio/output defaults. Saved duration is shown exactly, including lengths outside the old slider range. The real deterministic request-check dialog comes before generation; checking is not model inference or editorial approval. A protected request cannot change the current output aspect in that review. Provider setup/download confirmation and possible provider usage remain explicit, and no new automatic model call starts from opening the pane.

For an existing edit, generated draft/analysis are retained as an isolated proposal rather than replacing active render inputs. Its existing review sheet auditions original A passages, not a composite preview; only reviewed Apply adopts the candidate, with source/media revision checks and Undo. Current mixed layers, output and mix remain authoritative. A short or incompatible candidate can still be blocked rather than removing or retiming retained layers.

The original progress/error/Stop controls dock in a normal disclosure while the editor remains visible. Its compact single-column checklist preserves actual status labels, and its Stop controls remain reachable at narrow widths. Pending requests block their inputs and repeated dispatch; failure/cancellation recovers the existing pane and decoded preview without a pretend successful job. AI connection and speech setup are secondary disclosures, not another permanent toolbar.

Validation distinguishes real behavior from test fixtures: actual request checks, autosaves, source audition, Apply/Undo and reopen use local generated projects; preparation failure/Stop uses an explicitly intercepted503 with no inference. Separate deterministic pipeline and production-render checks establish isolation, not AI output quality. This is a local integrated-workflow increment, not DaVinci parity or a release.


## November 17: compact editing console

The console refines the existing editor hierarchy instead of replacing its editing engine. Project identity, real save state, history and Export remain primary. Secondary project/setup/help controls move as their exact native nodes into one Workspace disclosure. On compact screens the same Projects and history controls join that menu rather than disappearing. Native dialogs return keyboard focus to the visible menu trigger. No duplicated command, project state or AI request path is introduced.

Media browsing gives filenames and thumbnails precedence. The native usage filter sits in a Filter disclosure, while imported files retain their real placement, source-review, usage and repair commands in contextual Add / review disclosures. Original listeners, readiness explanations and drag identity are preserved. This is presentation and navigation, not a new ingest or editing model.

Fresh editor layouts use a 320px inspector and a timeline default of 38% of available height, bounded between 232px and 360px. Existing user-resized proportions and storage keys remain authoritative. The monitor, timeline coordinate system, compositing planes, transport and export remain native. Graphite and neutral-gray light materials use restrained violet for edit/AI emphasis and cyan for media/navigation; all type assets remain local.

Validation uses isolated synthetic copies, never the main data directory: native Add and exact Undo, original-control identity, six workspaces, AI request-pane access, keyboard/focus, compact layouts and both themes. A separate reviewer checked 1440, 1280, 1024 and 390px widths. This establishes UI behavior and improved working space, not real AI editorial quality, unlimited tracks or DaVinci feature parity. Audio still has a form-heavy first view, and empty-project guidance remains basic; these are recorded follow-up design limitations, not hidden completion claims.


## November 19: direct editing entry and trustworthy delivery

Start an edit and Projects / New now share the existing manual-project creation path and its one-operation lock. Manual is the first recipe; explicit Short / YouTube AI recipes remain available, but opening the editor requires neither a recipe choice nor AI setup. Keyboard focus lands on the visible first-recording Import video control, never the hidden legacy empty-timeline button. Cancelled, busy and refused entry do not steal focus or create another project.

Output reads a host-owned snapshot of the actual editable sequence. Pixel dimensions use the same sizing function as the composited viewer and match the production renderer, including 4:5 short-edge sizing, Source A proportions, no Source upscaling and even-pixel output. Missing Source metadata stays explicitly unavailable. Timeline duration includes sequence gaps and later placements and never comes from the original-source player's clock. The existing frame-rate and output controls remain the only setting owners.

Export has a stable header and action row around a scrolling body. Back to edit preserves the timeline; Change output settings opens the original Output workspace and focuses its selected native preset. It does not start a job, change marks or apply a second set of options. Progress, Stop, previous downloads, marked ranges and validation errors retain their original handlers. Graphite/gray theme, proportional tabular numerals, visible focus and RTL flow are preserved.

When the media pool is narrowed, list-view Open source and Actions receive separate full-width rows using the existing shelf container. The original controls, their DOM order, drag surface, readiness and usage count stay intact. This addresses the clipped Actions label verified in the earlier 1024px synthetic capture without changing placement semantics.

Verification is recorded in validation-work/editor-flow-20261119/QA.md. New production-render tests compare UI facts against encoded portrait Source, 4:3 Source and 4:5 output after import, edit, Undo/Redo and reopen. This is a bounded local workflow increment, not a release or complete Resolve parity. Current interactive visual acceptance remains unverified because browser control was unavailable and native review approval timed out. Earlier screenshots establish the baseline, not proof of this change's rendered appearance.
