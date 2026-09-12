# Editing together or independently

The timeline is your edited video, not the original recording's clock. Each clip also has a **Source in** position inside its recording. Original media is never overwritten.

## Start here

1. Click the ruler to seek. Space plays or pauses without changing the editing tool or preview mode.
   Zoom in/out centers on the yellow playhead, clamped at timeline boundaries. Fit still shows everything; Zoom to selection still targets the selected range.
2. Choose **Range**, drag over an unwanted section, then **Remove from video**.
3. Choose **Select / Move** to drag one cut. **Cut** clicks split at one point; dragging with Cut also moves a clip, without switching tools.
4. **Undo** reverses manual edits. Changes save automatically.
5. Open **Output** for aspect ratio, resolution, export quality and 24/25/30/50/60 FPS.

To move just part of a clip, select it with **Range**, switch to **Select / Move**, and drag inside the selection. Only that range moves, not its enclosing recording. This works in Together, A only and B only. Clicking outside the range picks a different individual cut.

## Choose the editing scope

| Mode | Remove | Move / duplicate |
| --- | --- | --- |
| Together (A+B), or Whole video with one source | Removes that time from both tracks and their layout plan; closes the gap. | Closes the origin and inserts the selected cut with its paired source and layout; destination footage shifts without being overwritten. Duplicate inserts a copy. |
| A only / B only | Removes only that source and leaves a gap. | Closes the origin and inserts on that track only; the other stays still. |

Together is the default. Switching the mode preserves your selection. Clicking a lane never silently changes the mode. Together sections are divided at every A/B clip boundary; a Blade split can align both sources at the same time.

Dragging or **Move to start** now uses ripple insertion: the origin closes, and destination footage shifts without being overwritten. Drops beyond the end append without adding black time. The destination is a final edit position, after closing the origin. Existing intentional gaps remain until explicitly closed. **Undo** restores the complete move. Legacy API insert and overwrite modes remain supported.

In **Select / Move**, select a clip, then drag a white edge to shorten it or reveal more original footage into a gap. Extension stops at the media boundary or the next clip: it does not stretch/freeze frames or overwrite neighbors. Together shortening removes time from both tracks and their layout; source-only shortening leaves the other source untouched. Crop settings remain attached to clips. Zoom in to access handles on tiny clips.

**Close gaps** appears when the selected scope has empty time. Together removes only intervals where both tracks are empty, keeping synchronization and any footage present on either source. A/B-only closes gaps on that track without shifting the other one. Every operation is a single Undo step. Original recordings and transcripts remain untouched.

## More editing tools

### Frame each cut separately

Select a clip (or a range), open **Layout → Clip framing**, and choose source A or B. Horizontal focus, vertical focus and zoom save only to that section on that source, with Undo. Without a selection, the controls target the clip at the playhead; the displayed time range identifies the scope. Full source mode disables per-cut framing.

Framing follows clips through moves, copies and splits and is applied in both preview and export. An explicit clip crop fills that source's panel, even if the global layout uses Fit. Other clips keep their existing framing. For a camera embedded in one recording, these controls move the screen within the bottom panel without changing the camera window; zoom is unavailable for that layout.

**More tools** opens the inspector, without displacing the timeline.

- **Range…** accepts exact edit times as seconds or mm:ss.mmm.
- **Original footage** opens a large source player and the complete original timeline. Green sections are in the current edit; red sections are removed. Click a section or drag any range, preview it, then **Restore to edit** or **Remove from edit**. Previous/Next removed and zoom help review long recordings. Source and edited playback stay separate.
- Restore inserts only missing portions of the selected recording, near the next source neighbor (or after the preceding one). Existing clips keep their relative order even if you rearranged the story. Together restores the original synchronized A/B mapping and layout; source-only restores just that track, filling a corresponding gap when possible. Remove affects all uses of the selected interval, including copies; Together closes the gap, source-only leaves it. Each action is one Undo step. Original media and transcripts are not rewritten.
- **Insert a copy by time…** remains available inside Original footage for deliberate insertion/duplication with exact Source in / Source out and edit times. This inserts only the chosen source; Together shifts both existing tracks, while source-only shifts only that track.
- **Duplicate clip** copies the selected section. In Together it includes both tracks and layouts.
- **Cut out** removes the interval between two clicks.
- **Keys / Shortcuts** selects a supported keyboard profile. These cover CUTROOM's available actions, not every command from another editor.
- **Reset to AI draft** resets the complete manual sequence after confirmation; it is undoable.

In the Together inspector, Start / End select exact times; use **Remove from video** for removal. **Move to start** uses Start as the final position and preserves the selected section's length. In A-only/B-only, **Apply trim** changes clip boundaries and Source in independently.

An empty timeline is valid and stays empty when reopened. Use Original footage to restore a selection, or Undo to continue. Export is unavailable until some footage exists.

## Layout, captions and playback

Select a section and choose a composition in **Layout**: the choice saves immediately. **Entire edit** clears the range so the next choice applies throughout. **Exact range…** exposes numeric scope controls. Source setup (roles, audio, framing and synchronization) remains a whole-edit setting.

When one source is missing, the other fills the frame. If both are missing, the frame is black. Audio follows the explicitly chosen audio source and is silent in its gaps, without silently switching recordings. Captions follow that source's clip mapping. Caption text corrections save separately from timing edits.

**Edited video** uses the sequence clock; **Full source** browses original footage without changing the edit. Arrow stepping uses output FPS in the edited sequence and source FPS in Full source. A camera embedded in one file uses crop/layout controls; it is not a recovered separate recording.

## Workspace

On larger screens, drag the video/timeline divider to resize either area; double-click resets it. The video-only **Full screen** includes both sources, captions and transport. Escape returns to editing. The fallback is a video-only overlay if native fullscreen is unavailable.

**How to edit** gives a short five-step guide. Advanced source behavior is collapsed under an optional explanation. AI draft settings are below output settings, so optional model setup does not obstruct everyday editing or export.

## Safety and current boundaries

- Manual sequence actions require the current project revision. A conflict loads the latest version and asks for a new selection rather than replaying a destructive action at stale coordinates.
- A/B are two source tracks, not unlimited layers or a per-clip audio mixer.
- New operations require at least one frame at the selected output FPS. Unsupported tiny leftover fragments are rejected atomically, never silently discarded.
- Sequence length can grow, but each clip must use footage that exists in its recording. Linked edits cannot repair incorrectly synchronized input files.
- Synthetic UI and real 30/60 FPS FFmpeg regressions cover linked edits, gaps, captions and audio. These do not certify transcription accuracy, real user satisfaction, or long/reordered 4K performance.
- Everything remains local, free and open source. No service, model or paid dependency was added.

Tests: `node --test tests/frontend_*.test.cjs` and `.venv/Scripts/python.exe -m pytest -o addopts='' -q`.
