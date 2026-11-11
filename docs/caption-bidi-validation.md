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

## Checks

Run `python -m pytest tests/test_caption_bidi_presentation.py tests/test_caption_bidi_render.py`.
Render tests require existing FFmpeg/libass and a Hebrew-capable font: installed
Arial on Windows, or DejaVu Sans/fontconfig on Linux. They explicitly skip when
prerequisites are missing. No speech models or network services are used.

Real grayscale frames are compared with an independent forced-LTR reference
that spells the intended visual order. That test-only reference uses unpointed
Hebrew, not Arabic. Caption-ink-normalized pixel error allows small subpixel
raster differences without diluting errors into the black background. Negative
controls reject both the original behavior and separate-token isolation.

The 14 real-render tests cover 4K, 4K 60fps, Sony A7 IV, Sony (A7 IV),
Sony A7 IV / H.264, Sony, Canon, H.264, S-Log3, 4K/60fps, (4K), and Swit,
plus three negative controls. Unit checks cover source/SRT preservation,
all four styles, first-strong paragraph direction, escaping, and Hebrew prefixes.

## Verification limits

Linux FFmpeg 7.1.5 with DejaVu Sans was verified in the isolated cloud checkout.
The tests also passed on Windows using the existing FFmpeg and installed Arial.
These controlled single-line fixtures do not establish preview/export parity,
arbitrary wrapping, Arabic visual correctness, or speech-recognition accuracy.
