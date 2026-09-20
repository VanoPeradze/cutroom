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

## Welcome and connection redesign

The follow-up onboarding pass applies the same hierarchy, disclosure, stable
controls and responsive-layout principles to the entry screen. It uses the
skill's guidance as a reference; it did not run a new skill database search.

The welcome screen now explains CUTROOM before asking for files. Three explicit
starting points separate vertical Shorts, horizontal YouTube edits and full-length
manual editing. A short tour explains the sequence and where to find editing help.
AI accounts and advanced model IDs stay in a dedicated connection dialog rather
than competing with the upload and timeline controls. Privacy copy describes the
selected connection instead of claiming all processing is always local.

`welcome.css` introduces shared ink, violet and cyan surfaces and control styling
without changing the timeline's geometry. Illustrations use lightweight CSS, not
downloaded media, libraries or paid assets. Manual setup hides AI-only style and
runtime preparation controls. Project creation saves the chosen starting format
atomically, and refresh still restores active processing jobs.

Onboarding QA used an isolated synthetic project at the normal desktop viewport,
1024px and 390px widths. The Short, YouTube and Manual starting points were checked
in the browser; a manual two-source timeline opened with AI disabled. The new
connection dialog remained inside the narrow viewport, and Escape closed the
quick tour and returned keyboard focus to its trigger. No browser console errors
were observed in the checked flows. A separate FFmpeg smoke check exported edited
manual footage with audio in 1280×720 and 720×1280 at 60 FPS. These are targeted
checks, not an exhaustive accessibility or real-footage quality audit.

## Local setup and guided onboarding follow-up

The home screen now pairs project choices with a visible setup checklist. The
AI dialog compares local processing, a user's Groq Free account and a user's
own API plan, without implying unlimited free cloud usage. Local model cards
show their purpose, profile, estimated download size and cached installation
status. Downloads require confirmation; progress, cancellation and recovery
stay in the same panel. An explicit engine check is separate from cached status.

The searchable in-app guide covers models, privacy, sources, layouts, transcripts,
captions, timeline editing, shortcuts, export and recovery. English and Hebrew
guides and short showcase pages ship with actual screenshots of the application.
The editor screenshot uses synthetic test footage, not a claimed AI result.

Targeted browser checks covered 1440×1000, 1280×720, 1024×768 and 390×844 viewports,
guide search and its empty state, keyboard dismissal, unsaved cloud selection,
local inventory and creator framing in an isolated synthetic project. No page
horizontal overflow was observed in the checked home/setup views, and no browser
console warnings or errors were observed. A fresh FFmpeg manual-workflow check
exported horizontal and vertical 720p files with audio at 60 FPS.

Automated model tests use simulated network responses and subprocesses. No
multi-gigabyte model download, real cloud inference, clean-PC installation or
real-footage editorial-quality assessment was performed for this follow-up.
