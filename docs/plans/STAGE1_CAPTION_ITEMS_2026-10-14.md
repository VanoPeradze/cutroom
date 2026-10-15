# Stage 1 — automatic captions as timeline items (2026-10-14)

Base: `master` at `05852dc`. Branch `claude/stage1-caption-items-20261014`.
State: **local source only**. Not built into a ZIP, not installed, not published.
Hardware/software: Windows 10 22H2, Python 3.11.9 (repo `.venv`), Node 24.16.0, FFmpeg 7.1.1 (gyan.dev full), Chromium 155 (Playwright). Isolated fixture server on port 8766 with a temporary data directory; port 8765 had no listener and was not used. Only synthetic media and text were used.

## What was wrong (Stage 0, item 1 and 1b)

The Captions lane drew transcript segments but nothing could select them: clicks only moved the playhead. Correcting a line overwrote the transcription itself and dropped its word timing when the word count changed.

## What changed

**One source of caption items.** `cutroom/caption_items.py` derives automatic caption items from the transcript and the edit, and `render.project_caption_items()` places them on the editor clock (timeline and preview) or the export clock (frame-snapped cuts). The same items produce the timeline blocks, the preview overlay, the burned ASS captions and the SRT file.

**Two edit layers. The transcription is never rewritten:**

| Layer | Stored in | Applies to | Survives a new AI draft |
|---|---|---|---|
| Fix what was said | `manual.caption_corrections[segment_id] = {original, text}` | every use of that speech, the transcript list, and the AI director's reading | Yes. If a new transcription changes that segment, the fix is kept but not applied, and the segment is reported in `caption_corrections_stale` (no UI yet) |
| This caption only | `manual.caption_overrides[item_id]` with `text`, `start_delta`/`end_delta`, `hidden`, `style`/`position`/`scale` | one item | Per edit; items that no longer exist keep their stored change unused |

Timing changes are stored as offsets from the speech, so a retimed caption moves with its clip.

**Stable item IDs.** An item is named by the speech it shows: `s12:w0` means segment `s12` from its first transcribed word; `s12:w4` is a part that starts at word 4 (after a cut inside the segment); `t<seconds>` is used when a segment has no word timing; `~1`, `~2` mark the same speech used again, in edit order. Pieces that continue each other in both the edit and the recording are joined, so splitting a clip or changing a layout neither splits a caption nor renames the ones after it.

**Edits and history.** New actions `caption_update` (text with scope `source` or `item`, start/end, style, position, scale), `caption_visibility` and `caption_reset`, plus `transcript_text` now writing the correction layer. Each is one undo step (`kind: "captions"`). The API requires the displayed `expected_revision` and rejects unknown fields.

**Editor.**
- Captions lane: click selects (no playhead jump), drag moves, edges trim (in whole frames; minimum 0.1 s), double-click or Enter opens the text, Delete/Backspace hides, Esc deselects. Blade and range tools do not cut captions. Overlapping captions stack in rows; hidden captions stay visible as dashed “Hidden” blocks; edited captions show ✎.
- Captions panel: a “Selected caption” inspector with the text, a choice between “What was said” and “Only this caption”, start/end, style, position, size (empty = project setting), Hide/Show, Reset, Previous/Next. Enter saves, Shift+Enter adds a line, Esc reverts.
- Preview: draws the same item and line split as the export, outlines the selected caption, and clicking the caption on the video selects it. Full-source inspection keeps showing the transcript.
- Safety: with a caption selected, Delete hides that caption and never removes an older footage range. Export and rebuild ask you to save or discard unsaved caption text first.

**Export.**
- Burned and SRT captions come from the items: hidden ones are left out, per-caption style uses its own ASS style, and estimated word timing is never coloured by word highlight.
- Long lines now wrap (`WrapStyle: 0`). Before, a long line without word timing ran off both edges of the frame while the preview wrapped it.
- The render fingerprint includes the caption layers only once they exist, so earlier exports are not marked out of date.

Files: `cutroom/caption_items.py` (new), `cutroom/captions.py`, `cutroom/render.py`, `cutroom/editing.py`, `cutroom/sequence.py`, `cutroom/director.py`, `server.py`, `web/timeline.js`, `web/app.js`, `web/index.html`, `web/editor-panels.css`, `web/source-review.js`, tests.

## Scenarios and results

| Scenario | Result | Evidence |
|---|---|---|
| Select an automatic caption in the timeline; inspector and preview follow | Pass | Browser (fixture): click on the 1–2 s Hebrew caption opened the inspector with its text and times, and the preview caption was outlined. `frontend_timeline.test.cjs` |
| Fix what was said (English) | Pass | Browser: the caption and the transcript list show the fix; `analysis.transcript` on disk unchanged. `test_caption_items.py` |
| Change only this caption (Hebrew) | Pass | Browser: other uses unchanged; burned frame at 1.5 s shows the new Hebrew text |
| Hide with Delete; no footage removed | Pass | Browser: only `caption_visibility` was sent. Export frame at 2.5 s has no caption |
| Drag a caption +0.5 s; undo; redo | Pass | Browser: 3.0–4.0 → 3.5–4.5; Ctrl+Z restored, Ctrl+Shift+Z re-applied |
| Export parity after edits | Pass | SRT from the fixture export equals the editor's visible items (9 of 9, same times and text). `test_real_export_uses_the_edited_caption_items` renders real media with FFmpeg |
| Save and reopen | Pass | `store.load` returns the layers; the render fingerprint is unchanged after reload |
| Speech used twice; split/move clips | Pass | `test_source_correction_reaches_every_use_and_item_text_only_one`, `test_splitting_a_clip_keeps_caption_identity_and_overrides` |
| Legacy (draft-only) projects and sequence projects | Pass | Unit tests for both clocks; the editor and export items agree |
| Invalid input changes nothing | Pass | Empty text, unknown ID, reversed or out-of-range times, unknown style, size 300, bad scope or `hidden` |
| Changed word count | Pass | Timing is spread over the spoken time and marked estimated; word highlight is not coloured |
| Long Hebrew line burned | Pass after fix | It ran off the frame before the wrap change; after it, four correctly ordered lines |
| 2-hour transcript (synthetic, 15,000 words, 240 cuts) | Measured | 1,200 items in 74 ms; project response 88 ms to build and 778 KiB of caption data |
| Test suites | Pass | Python suite (exit 0) and 615 Node frontend tests |

## Open issue found during testing

In the first browser run, one caption I did not touch (5–6 s) received a 1-pixel move (−0.0087 s) about four seconds after I clicked a different caption. Instrumented replays (pointer events and POST bodies logged) did not reproduce it. Caption drags are now quantized to whole output frames, so a pixel of movement can no longer become an edit. The cause is still unexplained.

## Known limits and next decisions

1. Reordering two uses of the same speech swaps their per-caption changes (`~1` follows edit order).
2. Trimming away the first word of a caption gives it a new name, and its own change stops applying. Undo brings it back. There is no “unmatched edits” list yet; stale source fixes have no UI either.
3. A caption lengthened past its clip keeps showing over the next clip. This is intentional, but the timeline does not warn about it.
4. Position is a preset per caption; there is no dragging on the video yet.
5. Not tested: macOS, keyboard profiles other than the default for Delete/Enter on captions, touch, screen readers, and a real long recording in the browser (only the payload was measured).
6. Next: Stage 2 (mixer), as planned.

## Reproduce

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_caption_items.py tests/test_manual_editing.py tests/test_sequence_render.py
```

```bash
node --test tests/frontend_timeline.test.cjs
```

Browser: start the `cutroom-fixture` launch configuration (port 8766, temporary data), open “UI sample · synthetic footage”, open Captions, and click a block in the Captions lane.
