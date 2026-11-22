# Reuse source In / Out marks

Open a ready library video with **In / Out** in the media pool.
Studio shows a contextual **Source monitor** in Media, beside the edited viewer
and timeline, rather than a blocking one-shot dialog. Set Source In and Source
Out, or use the source player's playhead buttons. **Save source marks** remembers
one selection for that imported video. Reopening the same video restores it.
You can preview it, insert it at the displayed edited destination, or append it
through the existing editing actions. Seek the timeline to change the destination.
After a successful Insert or Append, the same source video and In / Out fields
stay open, and the edited playhead advances to the new shot's end. Choose the next
source range and repeat. Each placement remains a separate Undo operation.

Ordinary source playback uses its prepared preview and normal-speed sound,
without the edited framing, effects or mix. Playing source pauses the edited viewer; playing the
edit pauses source. Choosing a timeline occurrence returns to its inspector.
**Close source** or Escape inside the source card closes only that review.
Leaving Media, Studio or the project releases its source playback.

An unrelated saved edit, including Undo, pauses source controls. **Use current
edit** explicitly rechecks the same source and new destination without losing
local marks. Source replacement or a different project view closes the card
instead. Placement pins source, revision and destination before submission;
conflicts load the latest edit without retrying the old shot automatically.
Resolve pending text/effect drafts or saves before adding more shots.

Exact In/Out, Set In/Out, selected playback and placement remain in the main card.
**Source marks & help** contains Jump to In/Out, browser-local Save/Clear marks and
longer guidance. This disclosure does not create a separate editor or save queue.

Saving marks does not add a clip or alter the project, timeline, edit history,
source footage, AI draft, or export. Closing a review or inserting a shot does
not automatically save changed marks. **Clear saved marks** removes that saved
selection and resets the review to the full source; it does not remove timeline
clips. Timeline Undo does not undo browser preferences.

## Review the timeline handoff

The draggable source-selection summary now appears before **Place on timeline**.
The original In / Out fields and source player keep their own source clock;
the destination section uses the edited timeline clock. Enter in a Source In / Out
field confirms the typed selection without implicitly adding a shot. Activate
**Append** or **Insert** explicitly with the mouse, touch, or keyboard.

Each placement action shows its own current reason when unavailable, rather than
requiring a mouse hover. When the native track planner supplies a valid span, its
actual timeline start/end and named track are shown next to that action. Insert
opens time and moves later clips; Append adds after the current edit end. Source
loading, pending frame decoding, invalid marks, busy edits and stale revisions
are not described as ready. **Use current edit** remains beside the destination
when explicit refresh is needed; it does not discard the source marks.

A successful placement shows a separate confirmation using the saved occurrence's
timeline start and end, not a subsequently moved playhead. The confirmation stays
through ordinary seeking and mark changes, and clears on an unrelated saved
revision, Undo/Redo or a new source session. It is not a draggable range and does
not save source marks. Native actions, track protection, history and export remain
unchanged. Readouts show milliseconds for scanning; the original exact source
values are not rounded before submission.

## Drag a selected source passage

Drag a Media pool card or the **Drag selection** range summary in the video or
audio Source monitor onto the timeline. Both use the same placement path:

- An open, valid In / Out selection applies only to its exact project and asset.
  Unsaved marks work while that source is open. A different open source never
  supplies the dragged file's marks, even when filenames match.
- Otherwise, that exact asset's valid browser-saved marks are used. Without
  valid saved marks, the original full-source behavior is kept. Invalid active
  marks are refused, not silently replaced by older marks or the whole file.
- The ghost and live text show the actual timeline start, end and length, plus
  the source interval. Ordinary Overlay / Add remains bounded by the edit end;
  if it shortens the selected interval, the feedback says so. The Audio Source
  button **Add selected audio** still requires its whole selection to fit.
- Shift-drag inserts the selected video duration and shifts later items. A
  tail video drop appends the selected duration. Audio and images cannot extend
  the edit. Saved tracks require a compatible, unlocked destination, with the
  existing overlap and insert protections; no silent rerouting occurs.
- A changed source, selection, project or revision cancels the drag intent.
  Hover and cancellation create no saved edit. A successful placement is one
  Undo, and its exact source offset and duration survive save/reopen.

The new timeline occurrence is selected after a drag, returning to its inspector.
That does not save Source marks; use **Save source marks** before closing a source
if you want them available next time. Existing Insert / Append / Add buttons
remain the keyboard and touch alternatives. Dragging does not add an overwrite
mode: use the existing explicit Track Overwrite controls for that operation.

## Source monitor controls

- **Jump to In** and **Jump to Out** pause the source and move its playhead to the
  selected boundary. They do not move the edit playhead or change the timeline.
- Press **I** or **O** while focused in the source monitor to mark the
  current source position. Shortcuts do not run while typing in form fields or
  composing text, or with browser/system modifiers. Changed marks pause playback
  and remain unsaved until **Save source marks** is pressed.
- **Play selected shot** starts at In and pauses at Out. The button changes to
  Pause while playing, and Resume after pausing inside the selected range. A
  completed selection does not leave a stale stop boundary on later native
  source playback. There is no automatic loop.
- Controls wait for matching video metadata. Failed previews, stale edits and
  busy edits do not accept new source-review actions. Closing releases the video
  and its event handlers; delayed playback/edit responses cannot update a newer
  source session.

Ordinary preview seeking and Out-boundary timing still follow browser video
events; a prepared proxy may not preserve every original frame. This is distinct
from the original-frame still review below. There is no reverse playback.

## Original-frame steps and timeline frames

The imported-video Source monitor now has **Previous frame** and **Next frame**.
These decode a still from the owned original file, not a nominal-FPS seek on a
proxy. The shown frame number and nine-decimal source time come from a complete
FFprobe decoded-presentation-timestamp index. CFR and variable-frame-rate sources
use the same rule. The first step uses the ordinary player's current time to
locate the original-frame interval; it does not certify the proxy's previous
picture. Further steps use the confirmed original index, never a guessed FPS.

- While decoding, marks, placement and selection dragging wait for the picture.
  The exact same decoded image element is shown before marks become available.
- **Set In at shown frame** uses that picture's start. **Set Out after shown
  frame** uses the following original timestamp, so Out includes the shown frame
  and excludes the next. If the last picture's exclusive end cannot be verified,
  its Out button is unavailable; enter an explicit source Out manually instead.
  An audio/container tail is never substituted for a missing picture endpoint.
- **Return to playback**, Jump to In/Out or Play selected shot leaves still review
  and restores ordinary preview playback. Source stepping never moves the edited
  timeline cursor or saves a project. Existing Save source marks and placement
  preserve these nanosecond-rounded values through their usual paths.
- Left/Right arrows within Source use these same original-frame steps, except in
  text/number fields, native player controls, IME composition or modified keys.
  Held-key repeats do not queue decodes. A changed source, revision, view or
  closed monitor invalidates pending results; it never marks a stale picture.
- In the **Edited** viewer, timeline arrows instead step on the project's output
  frame grid, including rounded 24/25/30/50/60 FPS boundaries. The legacy full
  Original-A viewer still has only a time nudge; its notice explicitly says this
  is not a verified original frame. Exact still review is for imported video in
  the Source monitor, not the original A/B track viewers or audio sources.

The first supported slice is intentionally bounded: videos up to ten minutes,
2 GiB, 16,777,216 pixels and 50,000 indexed pictures. Original indexing and each
still decode have 15-second process timeouts, bounded stdout/stderr, and small
in-memory caches. Ambiguous/missing/out-of-order timestamps, unsupported sources,
unusual non-integer-tick-per-second timebases, contradictory render endpoints,
or limits show an explicit error; ordinary playback and editing remain available.
There are no sidecar files, source writes, proxy rebuilds or new dependencies.
Closing a review discards its result in the client; a server decode already in
progress may finish or reach its bounded timeout.

The editor's existing 0.08-second minimum source range is unchanged. A single
short frame therefore need not be placeable. Export remains at the selected
project CFR: source pictures may repeat or be omitted, and the existing renderer
rounds total duration to its output-frame count. Exact source marks do not promise
one output frame per source picture. Synthetic CFR/VFR tests cover original PTS,
actual still pixels, mark persistence, Undo/Redo, reopen and exported exclusion of
a distinct next source picture; they are not a claim of browser playback accuracy.

Technical references: [FFprobe](https://ffmpeg.org/ffprobe.html) and
[FFmpeg select filter](https://ffmpeg.org/ffmpeg-filters.html#select_002c-aselect).
Container-origin normalization follows FFmpeg integer stream-tick rescaling,
verified against independent decoded timestamps and an actual nonzero-origin
export. No interval-seek result or average frame rate is treated as an exact
source index.

## Storage and identity

- Marks are stored only in this browser's local storage for this CUTROOM origin.
  They are not part of project JSON, project backups or exports. A different
  browser, machine, host or port has separate storage. Clearing browser storage
  removes marks; private browsing can discard them on exit.
- Project ID and imported asset ID keep equal filenames and re-imports separate.
  Duration, dimensions, media kind and storage version must also match. Renaming
  an asset, editing the timeline or regenerating its preview URL does not alone
  discard marks. A re-import gets its own asset ID and starts with the full range.
- This identity is not a file-content fingerprint. It cannot detect an external
  file replacement or restored project that reuses the same project/asset IDs
  and identical metadata. Do not overwrite imported files in place. Import
  replacement footage normally, then review and save its own marks.
- Corrupt, stale or out-of-bounds marks are ignored, never applied to the timeline.
  If storage is blocked or full, the current review still works and a failed
  save/clear leaves the current selection unchanged. No silent automatic cleanup
  or cross-project sharing is performed.

This is one reusable browser-local selection per import, not multiple named
subclips, a portable project bin, or automatic placement. Existing insertion
restrictions, lock checks and stale-edit checks remain in force.

## בדיקה ושמירת מקטע מקור

בספריית המדיה פתחו סרטון מוכן דרך **Review source shot**, הגדירו נקודות In ו־Out
ולחצו על **Save source marks**. בפתיחה הבאה של אותו סרטון, הטווח השמור ישוחזר.
אפשר לצפות בו ולהשתמש בפעולות ההוספה הקיימות. השמירה עצמה אינה משנה את העריכה.

**Clear saved marks** מוחק את הסימון השמור ומחזיר את הבחירה למקור המלא, בלי
למחוק קטעים מציר הזמן. השמירה מקומית לדפדפן ולכתובת CUTROOM הנוכחיים בלבד,
ואינה כלולה בגיבוי הפרויקט. ייבוא מחדש מקבל סימון נפרד גם אם שם הקובץ זהה.
אין להחליף ידנית את קובץ המקור בתוך תיקיית הפרויקט; ייבאו מקור חלופי מחדש.

**Jump to In** ו־**Jump to Out** עוצרים את הניגון ומעבירים את הסמן לגבול שבחרתם.
בחלון הבדיקה אפשר להשתמש ב־**I** וב־**O** לסימון, כל עוד אינכם מקלידים בשדה.
**Play selected shot** מנגן את המקטע שנבחר; אפשר לעצור ולהמשיך, והניגון נעצר
ב־Out בלי לולאה אוטומטית. פעולות אלה אינן משנות את ציר הזמן. הדיוק בתצוגה
תלוי באירועי הווידאו של הדפדפן, ואינו ניווט פריים־אחר־פריים.

## Inspiration and verification

The workflow is inspired by source-monitor In / Out zones in the
[Kdenlive Clip Monitor](https://docs.kdenlive.org/en/user_interface/monitors/clip_monitor.html).
No Kdenlive code or assets are included, and this does not claim its Project Bin
subclip feature.

Focused tests: `node --test tests/frontend_library_shot_review.test.cjs tests/frontend_source_monitor*.test.cjs`.
Frontend suite: `node --test tests/frontend*.test.cjs`.
The test harness exercises DOM event handlers and storage with a simulated edit
callback. A real-browser and full-application acceptance pass is still required
before release, especially storage persistence, compact inspector scrolling, native form
validation, repeated assembly and exclusive source/program playback. No backend API or project schema is changed by this feature.

## Overwrite on one visual track

In the video Source monitor, choose a named visual **Destination track**, set Source In/Out, and park the paused **Edited video** playhead. Open **Overwrite on one track**. The preview reports the exact target interval and the counts of whole clips removed, clips trimmed, and shots split around it. **Overwrite this track** fits the marked video and its normal-speed attached sound into that interval without rippling time or changing any other track. Music and captions elsewhere are not removed. Source marks remain available for the next shot. The destination starts on the nearest output frame. The source duration is not lengthened to a whole frame; if Out falls between timeline frames, the next displayed playhead position is the first frame at or after that end.

The shot must fit before the edit end. Overlapping disabled clips also count. A partially covered destination needs enough room for a 0.08-second retained piece and representable pan/fade timing. A fully covered animated or faded clip may be replaced wholly. An unavailable affected original/preview or a locked destination blocks the entire change. The original occurrence ID stays with the left piece when both sides survive; a sole remaining piece keeps that ID. Undo restores the complete previous timeline in one step. This is for imported videos onto explicit visual tracks; it is not the separate original A/B Overwrite command or an audio-only overwrite.
