# Stage 4 — graphics templates and a bounded export check (2026-10-14)

Branch `claude/stage4-graphics-20261014`, stacked on Stage 3.
State: **local source only**. Not built, installed or published.
Hardware/software: Windows 10 22H2, Python 3.11.9, Node 24.16.0, FFmpeg 7.1.1, Chromium 155 (Playwright). Isolated fixture on port 8766, synthetic media only.

## Graphics templates

Text clips have a **Template**: Plain text (unchanged default), **Lower third** (name with a smaller role line, bottom-left on a box), **Chapter card** (a centred title with an optional label above it, faded in and out), **Callout** (a short boxed note at the top-left with an accent bar) and **Highlight** (text in the accent colour at the chosen position).

- **Data.** `template` and the optional `subtext` (second line, at most 200 characters) are stored on the text clip. Plain clips keep their old exact shape, so earlier projects and exports are unchanged. Templates are a finite list; unknown values are rejected.
- **Same layout in preview and export.** The export draws each template with fixed ASS anchors (`cutroom/captions.py`, `_text_template`), and the preview uses the same positions in CSS (`web/text-studio.css`). Lower thirds and callouts always sit on a box in both.
- **Safety.** Every word comes from the user, and the user's text is escaped, so `{\pos(...)}` typed as text stays text. Nothing is generated, looked up or invented. The AI does not fill names, numbers or facts into graphics.
- **Inspector.** Choosing a template shows the "Second line" field only where it is used, and hides Position for the templates with a fixed place. The clip list names the template.

## Bounded export check

After each export, `cutroom/output_review.py` runs a quick local check and stores it with the export (`export.review`). The export dialog shows it, labelled either "Checks of this video" or "Checks of the previous export".

| Check | How | Status |
|---|---|---|
| True peak | `ebur128` over the export's audio | pass when ≤ −1 dBTP (+0.1 dB) |
| Loudness | Same pass | Compared with the normalization target plus Master when normalization is on, else shown for information |
| Black picture | 4 frames per second at 160 px, `blackdetect` for 1 s or longer | warn with times |
| Text over captions | Time and screen area of authored text and burned caption lines | warn with times |
| Long caption lines | Lines over 84 characters (three or more lines on a vertical frame) | warn with count |

Each pass has a time budget of 20–120 s, scaled at 25% of the export length. A check that runs out of time is skipped. A failed check never fails, blocks or changes the export.

## Verified

- Export frame with all four templates (720×1280): layouts as designed, Hebrew second line rendered.
- Browser (fixture):
  - Adding text and switching to Lower third showed "Second line" and hid Position right away. Callout and Chapter showed the right fields.
  - The clip saved with `template` and `subtext`, and the preview drew the boxed lower third bottom-left, the same place as the export.
- Real export check on the fixture (0.6 s): true peak −12.4 dBTP (pass), black picture (pass), and two warnings. The lower third covered captions at 0–3 s, and 5 caption lines were long. Both are real in that synthetic project.
- Tests:
  - `tests/test_text_templates.py`: finite set, backward compatibility, escaping, anchors, boxed style, FFmpeg render.
  - `tests/test_output_review.py`: overlap and length rules, a real file with a black gap, loudness against target.
  - `tests/test_audio_ceiling.py`: the stored check agrees with an independent measurement.
  - The full Python suite and 617 Node tests.

## Known limits and next decisions

1. Template look is fixed: one font (Arial), one accent colour and box style. There is no brand kit or per-project colour yet.
2. The overlap check knows screen areas (top, centre, bottom, lower third), not exact pixel boxes. Captions in the "auto" position count as bottom, including the social highlight style that sits at about two thirds of the height.
3. The black check samples 4 frames per second, so black shorter than about a quarter second is not seen.
4. There is no AI-suggested chapter card. If added later, it should only propose titles quoted from the transcript, for the user to accept.
5. Merging needs the release step (a newly pinned Windows baseline for macOS CI), as for Stages 1–3.
