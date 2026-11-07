# Reuse source In / Out marks

Open a ready library video with **Review source shot**. Set Source In and Source
Out, or use the source player's playhead buttons. **Save source marks** remembers
one selection for that imported video. Reopening the same video restores it.
You can preview it, insert it at the captured edit playhead, or append it through
the existing editing actions.

Saving marks does not add a clip or alter the project, timeline, edit history,
source footage, AI draft, or export. Closing a review or inserting a shot does
not automatically save changed marks. **Clear saved marks** removes that saved
selection and resets the review to the full source; it does not remove timeline
clips. Timeline Undo does not undo browser preferences.

## Source monitor controls

- **Jump to In** and **Jump to Out** pause the source and move its playhead to the
  selected boundary. They do not move the edit playhead or change the timeline.
- Press **I** or **O** while focused in the source-review dialog to mark the
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
  review dialog.

Preview seeking and Out-boundary timing follow the browser's video events. This
does not provide frame-accurate stepping, reverse playback or export changes.

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

Focused tests: `node --test tests/frontend_library_shot_review.test.cjs`.
Frontend suite: `node --test tests/frontend*.test.cjs`.
The test harness exercises DOM event handlers and storage with a simulated edit
callback. A real-browser and full-application acceptance pass is still required
before release, especially storage persistence, dialog scrolling and native form
validation. No backend API or project schema is changed by this feature.
