# UI/UX Pro Max: CUTROOM workspace application

Source: [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill),
including its SKILL.md, quick reference, professional UI rules and local search.
The external skill was read and searched from a temporary development copy;
it is not bundled into CUTROOM or required by end users.

The skill's product-wide recommendation was adapted to the existing plain HTML,
CSS and JavaScript video editor, not used as a reason to replace its stack. The
user's violet, cyan and ink palette remains authoritative. No font CDN,
animation package or paid service was added.

## Decisions

- Keep the technical dark workspace and the validated preview/timeline geometry.
- Use consistent 4/8px spacing roles, 12px minimum explanatory labels and 14px
  card titles. Dense timecode/trim controls remain distinct from body copy.
- Explain the workflow in three compact steps; put the output goal before style.
- Reduce repeated style information: only the selected card exposes its story
  structure. A filled radio shape, visible border and `aria-checked` state work
  together instead of depending on color alone.
- Put silence calibration in a native, initially closed disclosure; preserve
  its controls and expose the advanced options on request.
- Keep frame-rate labels and resource/quality caveats beside both export controls.
- Use stationary hover/press targets with color and elevation feedback, and
  preserve reduced-motion handling and visible keyboard focus.
- Reflow cards and instructions at phone/tablet widths instead of truncating
  essential labels. The Studio preview and timeline are not enlarged or moved
  as part of this visual pass.

The focused progressive-disclosure database query did not yield a verified
match after one retry. That decision uses the skill's explicit built-in
quick-reference rule, not an inferred database recommendation.

## Verification boundary

`tests/test_uiux_skill_css.py` checks layout declarations at 375, 768, 1024 and
1440px, filled/empty selection shapes, stable hover targets, readable FPS help,
native disclosure focus and dark-surface contrast. Existing editor-layout
contracts remain intact. Static rules are not proof of rendered layout or
accessibility compliance; browser QA must separately check real content,
keyboard operation, wrapping, zoom and reduced-motion behavior.

Browser QA used an isolated two-source synthetic project at 375, 768, 1024
and 1440px. Verified goal-before-style order, native audio disclosure and
waveform resizing, one radio tab stop with arrow-key selection/focus retention,
FPS persistence across refresh, and a bounded phone export dialog. The phone
pass caught a horizontally clipped header action and an overlapping sticky
generation button; both now remain reachable without covering the style cards.
No browser errors were recorded. Reduced-motion behavior and contrast have
automated CSS coverage; a screen-reader audit and actual zoom/text-scaling
matrix were not performed.

An export started through the UI produced an actual 1080×1920, 10-second MP4
with 600 frames at 60/1 FPS, verified by FFprobe. Additional FFmpeg tests cover
mixed source rates, A/B stacking, timing, audio and captions. No real user media
or AI inference was used for these checks. These changes do not claim better
transcription or story quality. Existing distribution ZIPs were not rebuilt.
