# Mixed Hebrew/Latin caption validation

Issue [#123](https://github.com/VanoPeradze/cutroom/issues/123) and its contribution
identified Latin/digit tokens such as `4K` as a libass presentation problem and
suggested Unicode LRI/PDI isolates. This implementation builds on that idea but
isolates adjacent ASCII phrases together. Isolating `4K` and `60fps` separately
reverses their relative visual order inside an RTL sentence.

The change is confined to ASS presentation for paragraphs whose first strong
character is RTL. Source transcripts, caption items, and SRT remain unchanged.
Libass still performs bidi resolution and shaping; production code never
reverses words or characters. Numeric-only runs and accented Latin are preserved.
Camera names, internal punctuation, and simple parenthesized model suffixes
are supported. Arbitrary nested punctuation, non-ASCII Latin phrases, and unusual
pre-authored bidi controls are not covered by the new visual fixtures.

## Required export checks

Run:

```sh
python -m pytest tests/test_caption_bidi_presentation.py tests/test_caption_bidi_render.py tests/test_captions.py
```

The real-render suite requires existing FFmpeg with libass on PATH. Missing
FFmpeg, subtitle support, or font fixtures is a **failure**, not a skip. It uses
pinned, unmodified DejaVu Sans regular and bold fixtures in `tests/fixtures/fonts`
with the complete upstream redistribution license. The font is passed explicitly
via `fontsdir`, never installed into the OS. It works without the `fc-match`
utility or an OS-installed DejaVu font, removing the previous macOS skip path.
The regular and bold files are SHA-256 checked. No network or speech model is used.

Real grayscale frames are compared with independent forced-LTR references that
spell the intended physical visual order. Only test references reverse unpointed
Hebrew; production never reverses words or characters. Caption-ink-normalized
pixel error allows small raster differences without diluting errors into black
background. Negative controls reject both original behavior and per-token
isolation. For natural wrapping, the portrait fixture has a fixed two-row visual
reference: a whole forced-LTR paragraph is not a valid RTL wrapping oracle.

The 35 real-render cases cover:
- 11 mixed Hebrew/Latin phrases and three negative controls.
- Both landscape and portrait in all four styles for `4K 60fps` and
  `Sony A7 IV / H.264`, including a two-row naturally wrapped portrait reference.
- Explicit multiline paragraphs in all four styles.
- Hebrew highlight with real word-timing input: deliberately one plain phrase,
  not unsafe per-word libass colour runs.

Presentation checks independently verify source transcripts/caption items and
SRT stay unchanged, escaping, first-strong paragraph direction, and Hebrew prefixes.
The fixture font is not a change to the product's exported Arial font.

## Real browser companion

With an **existing** Playwright and Chromium installation:

```sh
node scripts/validate_caption_bidi_browser.cjs
```

Optionally set `CUTROOM_CHROMIUM_EXECUTABLE` to the existing browser and
`NODE_PATH` to an existing Playwright installation. The script does not install
or download anything. It aborts all network requests and uses synthetic text.
It extracts the actual `renderCaptionItemPreview` and `updatePreviewCaption`
functions from `web/app.js` and loads the actual preview CSS; dependencies for
project lookup/timing are controlled fixtures rather than a live user project.

Its 250 cases verify logical text preservation, Latin token visual order using
real browser glyph rectangles, four styles, both renderer routes, landscape,
portrait and narrow natural wrapping. Explicit-newline tests require separate
physical rows. LTR active-word spans remain enabled as a control, while Hebrew
highlight remains plain to match export. Results and two screenshots are written
to `validation-work/caption-bidi-browser` (or the CLI output-directory argument).

This exposed a real mismatch: the preview collapsed authored newlines, whereas
ASS emitted a hard line break. `white-space: pre-line` now preserves those breaks
without changing stored text. The multiline browser assertion failed before
that CSS change and passed after it. The standard frontend suite also guards the
CSS/direction contract in `tests/frontend_caption_bidi.test.cjs`.

## Verification limits

The expanded export tests passed on Windows with existing FFmpeg/libass and the
bundled font. The real-browser cases passed on Chromium 149.0.7827.55 on Windows.
Native macOS ARM/Intel execution passed in the
[post-merge validation run](https://github.com/VanoPeradze/cutroom/actions/runs/42982890017)
for merge commit `eec41cf578b7805b1f9c2d493be0cf233b474b91`, following the
[final pre-merge gate](https://github.com/VanoPeradze/cutroom/actions/runs/42980968841).
Both native jobs completed the full Python regression suite with real FFmpeg.
These CI results do not establish real-speech accuracy or manual acceptance.

These are controlled text-rendering checks, not speech-recognition accuracy,
real user-footage validation, or pixel-identical preview/export typography. Browser
and libass have different sizing, fonts, and wrapping algorithms. The matrix
establishes the checked token-order and line-break behavior, not arbitrary nested
punctuation, arbitrary wrapping, Arabic shaping, every browser, or all Unicode.
The browser companion exercises production rendering functions but is not a full
end-to-end editor/navigation test. No audio was uploaded or transcribed.
