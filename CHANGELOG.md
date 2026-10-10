# Changelog

## 1.1 Beta - 2026-10-10 - Gameplay Shorts are built from what happens on screen

- **Shorts from game recordings now show the action instead of the game's plot.** In a gameplay recording most of the speech is usually the game itself: cutscenes, mission radio and companions. The Story model treated that dialogue as the content, so a "Strong Commentary" Short of a 27-minute The Division 2 session became a 3-minute retelling of the mission story, made mostly of cutscenes, radio lines and even an ad; the one fight in it was there by accident, inside 51 seconds of radio dialogue.
- When Gameplay vision shows a game recording, a Short in any style except **Stream Story** and **Chill Story** is now built from **gameplay moments**: the stretches with the most on-screen action and excitement in the sound. Cutscenes, menus, maps and loading screens are pushed out however loud they are, each moment gets a little context before and after, boundaries never cut a spoken phrase in half, and pauses inside a fight are no longer trimmed into jump cuts. The best moments fill the target in chronological order.
- On the same recording the default Smart Short (60 s) now keeps three firefights: the train station, the street fight and the truck ambush. The 180-second Strong Commentary Short keeps eight moments (176 s), each mostly gameplay, instead of cutscenes and radio dialogue. The Story planner is skipped for these edits, so the draft is ready in seconds once the recording has been analyzed.
- The draft summary lists the moments it chose and says that cutscenes, menus and loading screens were left out.
- *Automatic* Gameplay vision now also runs for **CUTROOM Smart**, the default Short style, so a game recording is recognized without picking a streamer style first.
- A few seconds of skipped speech no longer block a long edit. A 2-hour Counter-Strike 2 recording with Hebrew commentary was refused because one 30-second stretch of laughter produced almost no transcript (18.7 s of 2,633 s of detected speech). Transcription now refuses only when the gap is at least 3% of the detected speech (and at least 15 s, as before); smaller gaps finish the edit and name the time range to review. On that recording the Strong Commentary Short now keeps nine gameplay moments with the players' reactions.

## 1.1 Beta - 2026-10-09 - Transcription, captions and stability

- A recording whose audio is slightly shorter than its video is no longer rejected as incompletely transcribed. Failed transcriptions keep local diagnostics that name the affected audio ranges.
- Setup now confirms the media and sources before the editing choices and optional AI settings.
- Live preview captions follow the same phrase boundaries and silences as the exported video.
- Gameplay vision follows the selected screen source and its synchronization, including screen B with audio from A.
- Windows speech setup excludes PyAV 19, which breaks faster-whisper 1.2.1, runs a real decoder check, and registers the CUDA libraries that Store Python could not find.
- Camera and setup controls, toasts and the inspector chevron no longer overflow narrow panels. The Mac download is now byte-identical whichever system builds it.

## 1.1 Beta - 2026-10-08 - Setup uses Python 3.12

- New tagline: **Hours of footage. Minutes to a great clip.** It replaces "Your footage. Your next cut." on the home screen and the old taglines in the README banner, guides and download text.
- Fixed first-time setup on computers without Python 3.12. Since 21 September CUTROOM's numpy requirement has needed Python 3.12, but Windows setup still picked Python 3.11 first and downloaded a private Python 3.11 when none was installed, so installing the Python packages failed. Windows, Mac and Linux setup now use Python 3.12 only. Windows downloads a private Python 3.12 when the computer has none, and an existing CUTROOM environment built with Python 3.11 is rebuilt with 3.12 the next time setup or repair runs.
- The private Python that Windows setup downloads now stays inside the CUTROOM folder. It no longer adds a `python3.12.exe` shortcut to the user's `.local\bin` folder.
- The Windows launchers start their helper scripts by explicit path, so they also work on computers where the `NoDefaultCurrentDirectoryInExePath` security setting stops Windows from running scripts by name from the current folder.

## 1.1 Beta - 2026-10-07 - Layout fixes and new screenshots

- Fixed layout and overlap problems found by an automated sweep of every screen from 1920x1080 down to 1024x700, in night and day mode:
  - **Media:** the library no longer cuts off the Images tab or the search box, and narrow libraries stack each card's thumbnail above its name.
  - **Editor at 900-1099px:** keeps three columns instead of squeezing the preview to a 164px strip.
  - **Layout:** composition tiles no longer break labels one word per line.
  - **Output:** the frame-rate buttons read 24, 25, 30, 50 and 60 without a cut-off "60 FPS".
  - **Export dialog:** shows its three facts in equal columns.
- More fixes:
  - **Project overview up to 1100px:** the top bar keeps the project name on one line instead of drawing it over the step bar and buttons, and the review notes beside the video are no longer one word per line.
  - **Reel option details:** now readable (they were 8px).
  - **"Build my first cut" bar:** no longer hangs below the window edge.
  - **Narrow preview:** the preview-mode menu no longer slides under the play button.
- Timeline caption blocks show whole words with an ellipsis instead of unreadable fragments, and drop the redundant "Cc" prefix.
- New screenshots for the guides, README and website use original synthetic gameplay footage instead of third-party games. The website adds a Gameplay vision highlight, aligns the start-card tags and stacks the download buttons on phones.

## 1.1 Beta - 2026-10-05 - Gameplay vision and an optional 9B model

- Added **Gameplay vision**. The local Story model looks at sampled 8-second windows, four frames each, and reports what is on screen: firing, enemies, explosions, damage, a downed player or fast movement, and whether it is gameplay, a cutscene, a menu or map, a loading screen or a full-screen webcam. Qwen3.5 Story models accept images, so nothing extra is downloaded.
- The evidence reaches every selection path. The Story model gets an `on_screen` note per beat, because in gameplay the dialogue is often a game character. Segment selection favours visible action and pushes menus and loading screens down, and no-speech highlights blend it with audio. Reel options add **Best gameplay action** when it differs from the most intense moment, and cards show the on-screen action level.
- *Automatic* runs for streamer styles on an NVIDIA GPU or Apple Silicon. *On for every Short* also runs on CPU with fewer windows, and *Off* never runs. Frames never leave the computer and the pass never runs with cloud AI. Results are cached per source and model, and a failed pass leaves the draft to speech and sound. On an RTX 4070 Ti Super, 120 windows of a 27-minute 1080p60 recording took about 2 minutes.
- The 9B Story model is now optional everywhere. Without it, Quality runs on 4B as a normal setup instead of reporting a missing-model fallback, recommends 4B rather than 9B when no model is installed, and offers 9B as **Optional: get qwen3.5:9b**. AI connection labels it **Story · Quality (optional)**.

## 1.1 Beta - 2026-10-05 - Cleaner Shorts and studio polish

- Short drafts no longer open on a single misheard word: isolated, low-confidence one- or two-word blips (such as a word Whisper "hears" at 0:00 of a gameplay recording) are dropped from the transcript, and isolated pieces under a second are removed from Shorts.
- Added the **Word highlight** caption style, the default for new Shorts: up to four words at a time with the spoken word coloured, placed at about two thirds of the height in vertical video. Hebrew and Arabic lines stay plain short phrases because the subtitle renderer loses their word order once colours split the text.
- Reel options now include **Most intense moment**, the strongest continuous stretch of action and spoken reactions, and show measured energy relative to the recording instead of a fixed score.
- When a facecam is found inside a vertical Short's recording, the draft offers the streamer layout (camera on top, game below); the frame is still confirmed in Layout.
- Home lists projects in aligned rows with a type chip and a real name (from the recording, then the AI title; typed names are kept). An untouched new project is discarded when you leave it.
- Edit opens with its clip tools visible, the Media shelf has a clear empty state, Captions show style and position first (fixing squeezed style buttons), the default timeline fits the captions lane, and collapsible inspector sections show a chevron.
- The 1.1 Beta Windows and Mac downloads include this update and the studio layout below.

## 1.1 Beta - 2026-10-04 - Studio layout

- Rebuilt the editor in the studio layout: one top bar with Undo/Redo, How to edit, Help and Export; a monitor header over the video with 16:9/9:16; centered transport with the timecode; and an icon timeline toolbar. Track headers beside the timeline lock and mute through the existing Edit and mixer controls.
- Gave each workspace a library and a focused panel: Media search and filters, the Audio track mixer, Captions import and style buttons, Layout composition tiles, and Output presets with grouped resolution, frame-rate and quality buttons. Every new control drives the original one, so projects, settings and shortcuts are unchanged. The playhead is now cyan.
- Simplified Home: three start cards, recent projects with a source frame, kind and length, and a folded "AI is optional" banner. The Director screen shows the source footage and, once the rate is meaningful, the estimated time left.
- Auto mode uses the stronger models only when they are already installed and the GPU has room: Whisper Turbo (or the Hebrew Turbo model) for transcription and the 9B Story model for drafts. When the 9B model would fit but is missing, the status offers **Better drafts**; the download still needs your confirmation.
- Story AI no longer reloads the local model between passes: contexts snap to 8K/16K/32K and do not shrink within one job.
- Redesigned the README and website in the studio style. The downloads received this layout with the 2026-10-05 update.

## 1.1 Beta - 2026-10-03 - Preview-first workspace

- Reserved the upper workspace for the video and bounded contextual tools, with a full-width timeline and one ordered navigation row. Oversized legacy display preferences fall back without changing projects.
- Put clip framing first in Layout, selected Media properties before the library, and caption import, AI style and transcript in separate disclosures. Verified landscape and portrait previews with tools and timeline open at desktop and narrow sizes.

- Added vertical numeric scrubbing and focused-field wheel adjustment, with native steps/limits, Shift fine control, cancellation and one committed edit per gesture. Typing, keyboard input and normal panel scrolling remain available.

- Ordered workspaces as Media, Edit, Layout, Audio, Captions and Output, with matching RTL and keyboard navigation.
- Moved Green screen into Edit → Effects, separate from clip controls. Key color/defaults precede background; fine-tuning and exact-frame inspection expand when needed. Layout retains composition and framing.
- Kept contextual tools independently scrollable beside the preview. Single-source camera setup stays folded unless a detected camera needs review.


## 1.1 Beta - 2026-10-02 - Green-screen playback and layer order

- Fixed Media green-screen overlays hiding the background with an opaque rectangle. **Video underneath** retains alpha through placement and motion until compositing over earlier layers.
- Added saved-settings chroma preview in edited playback for A/B and Media video; original footage mode stays original. Exact native-size FFmpeg frame checks remain available and refresh after Apply.
- Ordered the controls as foreground, removed color, background and Apply. Reopening prefers the keyed video; selected video clips carry into Edit Effects. Added green-screen starting settings and a warning for tolerance values that can erase the subject.
- Preserved existing color/image settings, Undo/Redo, per-video persistence and source files. Verified an authorized local recording through browser playback, save/reopen/history and a real 1080p MP4 export; private media is excluded from source and packages.

## 1.1 Beta - 2026-10-01 - Green screen for project videos

- Made **Green screen / Chroma key** visible in Layout, with the selected video's name and preview. No AI/model setup is required.
- Added ready project Media videos alongside main footage A/B. Settings remain independent per video and apply to all timeline uses of an imported video before placement; duplicate filenames do not share settings. Audio and images remain unsupported foreground targets, and preparing/missing video is reported rather than silently selecting another file.
- Kept saved-settings single-frame preview, export, Undo/Redo and per-video Reset aligned. Main playback remains original/unkeyed; solid-color or image replacement remains the supported background.
- Added an explicit length intent: a highlight sequence accumulates distinct eligible passages toward the requested duration; the style maximum preserves a single engagement when chosen. Shortfalls remain visible, with no duplicated footage or arbitrary filler. Older projects retain their style contract until changed.
- Requested portable ASCII stabilization motion data to avoid inconsistent binary-format corrections seen on Windows FFmpeg7.1.1.
- Publication requires current-source Windows/native macOS compatibility checks and exact final-package validation. This entry does not claim manual Mac/Linux installation or real-footage keying quality was tested.

## 1.1 Beta - 2026-10-01 - Trustworthy continuity review

- Empty, incomplete or contradictory Story AI reviews cannot report a continuity pass. Drafts remain editable and clearly require review.
- Continuity repair requests are distinguished from changes actually kept after story-slot and duration safeguards. A no-op or restored passage is not reported as a completed repair.
- An explicit AI rebuild checks older continuity reviews again while retaining reusable transcription and chapter context. Opening a project does not trigger AI or model downloads. These checks do not certify every preset's semantic quality.

## 1.1 Beta - 2026-10-01 - Chroma Key and AI draft controls

- Added per-source A/B **Chroma Key** in Studio's Layout panel. Local FFmpeg replaces the selected color with a solid color or ready image from the Media library before layout/export; images cover the source frame and can crop at the edges. Explicit current-frame PNG inspection uses saved settings; the main player remains Original playback. Background video, B-underlay and transparent MP4 output are not supported. [Guide](docs/CHROMA_KEY.md)
- New AI results keep an existing manual timeline. **Apply new AI draft** asks for confirmation before replacing it; Undo restores the manual edit.
- Single-moment Short/Reel styles respect the moment's duration budget. **Clean VOD** keeps natural, chronological cleanup rather than forcing energetic cuts; selections still need human review.
- Local Story readiness reports requested and selected models, including an installed configured fallback (4B by default) when preferred 9B/2B is missing. This does not download models automatically or establish semantic editing quality.
- Publication requires current-source automated/native macOS checks and exact-package validation. The release manifest identifies the downloadable revision; this entry does not claim those gates have passed or that the new ZIP is public.

## 1.1 Beta - 2026-09-30 - Editor reliability and optional stabilization

- Fixed sub-frame A/B availability boundaries rejecting valid sequence/media edits. Only redundant implicit availability pieces join; explicit cuts, source endpoints, gaps, timing and framing remain intact. Actual FFmpeg synthetic renders verified boundaries at 30/60 FPS.
- Fixed source waveforms in manual projects and Original footage for the correct A/B source without AI analysis. Bounded decoded audio padding to source duration and decoded FFmpeg/FFprobe text as UTF-8 for Unicode media names.
- Added a compact mixer with measured channel peaks/dBFS, pause/seek reset, the selected A/B Original source and saved volume/mute. Solo remains preview-only; export normalization can change final loudness.
- Added opt-in **Media > Stabilize footage**: a separate local MP4 copy using available FFmpeg vidstab filters, with progress, cancellation, retry, download and reuse as extra footage. Originals and the edit stay untouched. It may zoom/crop edges and cannot repair every kind of shake, blur or rolling shutter; no AI or upload is used.
- Local validation passed 1,816 Python regressions (3 Windows skips), 538 frontend checks, Chrome/Windows workflows and synthetic stabilization/boundary renders. Totals overlap because Python includes frontend wrappers. Publication requires current-source macOS 15 Apple Silicon/Intel checks; Finder/Gatekeeper, Safari, native Linux and real-footage/performance checks remain needed.
- The version and filename stay **1.1 Beta** with a new manifest build ID/checksums. Existing users need the new download, extracted separately, with projects backed up before migration. Application behavior changes in both platform folders; earlier documentation-only refresh claims apply to their earlier payloads.

## 1.1 Beta — 2026-09-30 — Mac packaging beta

- Added a combined ZIP with exactly `windows` and `mac` folders. Every Windows file is preserved byte-for-byte from the previous approved download; existing Windows installations need no update.
- Added a separate Mac launcher, explicit-consent dependency setup, native Python discovery, full FFmpeg/subtitle checks, local AI runtime discovery and an offline first-start guide. Shared application and Windows installer code are unchanged.
- Added macOS 15 Apple Silicon and Intel CI for regression tests, fresh ZIP installation in a Unicode/space path, launcher/API checks, real portrait/landscape renders with audio and captions, and a small CPU transcription test.
- Mac local transcription uses the CPU. This source beta is not a signed/notarized Mac app; Finder/Gatekeeper, Safari and real-user performance still need manual testing. No perfect cross-platform behavior or equivalent speed is claimed.
- Updated the website and English/Hebrew guides to explain which folder to use. The legacy Windows-only packager remains available; maintainers use the new combined builder for this download.

## 1.1 Beta — 2026-09-28

- Added Open editor, Rename and confirmed permanent Delete to the lobby and Projects, plus project search and sorting. Renaming keeps the active edit in place; deletion refuses active work without cancelling it and explains that imported copies and CUTROOM exports are removed while original files stay untouched.
- Added custom titles and captions with their own timeline layers, immediate preview and automatic saving after typing pauses. Move or trim them on the edited-video clock, choose Top/Center/Bottom, Clean/Bold/Boxed and size, or import UTF-8 SRT/VTT files up to 1 MiB and 2,000 cues. These tools require no AI account or model.
- Custom text always appears in exported video independently of the AI-caption burn setting. Optional SRT output combines AI and custom captions, excluding titles. Imports do not replace the AI transcript; invalid imports and edits that would shorten the video past a text layer are rejected without losing saved work. Text does not automatically ripple with source edits.
- Softened the app and website with quieter surfaces and controls, and removed decorative diagonal arrows. Existing Day/Night choices remain available.
- Improved precision editing: visible Snap control, playhead/cross-track/media alignment, constrained trim snapping, a named alignment guide and output-frame time readouts. Alt bypasses snapping; existing free scrubbing and default Snap-off behavior remain intact.
- Added persistent A/B locks under **Edit → Track protection**. Lock a finished source while editing the other; footage remains visible and audible in preview and export. Clip changes, Together edits and Undo/Redo that would alter a protected lane are rejected without consuming history.
- Kept protection separate from Undo/Redo: lock choices survive reopening and history navigation. Unlock protected sources before rebuilding/refining the draft or replacing/removing source media. Shared layout, audio mixing and added-media edits remain available; protected clip framing, picture speed and source timing stay guarded.
- Fixed late trim responses changing selection after switching projects or edit targets, and stale selection restoration after a revision conflict.
- Undo/Redo now clears outdated clip selections while retaining the playhead, so the inspector cannot display the old trim range as the restored clip.
- Added a six-round editor roadmap: precision, track control, trim modes, source organization, performance and release qualification. Delivered scope includes precision, A/B protection, project management and custom text; mixed-layer ripple and arbitrary user-created lanes remain planned work. Every completed, verified increment must reach GitHub, a matching downloadable ZIP and the Expo website before publication is considered complete.

## 1.1 Beta — 2026-09-27

- Gave the app and public website a shared editing-room identity: warm paper, charcoal, restrained color and editorial typography, without new fonts, trackers or animation libraries.
- Replaced the lobby's oversized illustrated cards with direct, numbered project choices. Kept AI setup secondary and moved supporting workflow explanations into a keyboard-accessible guide disclosure.
- Clarified the clip inspector and reduced decorative control styling without changing playback, source framing or timeline behavior.
- Fixed low-contrast AI connection and local-model controls in day mode. Refreshed the real product screenshots and improved the website's Hebrew typography and product-tour labels.

## 1.1 Beta — 2026-09-24

- Made new two-source Reels default to a filled 30/70 camera-above-screen stack in upload setup, AI drafts, manual drafts, preview and export. Explicit source order, fit choices and nonvertical layouts remain intact; confirmed embedded-camera layouts use the same proportions.
- Simplified Layout: three primary choices, source routing/fit/sync under Advanced, and optional reference monitors. The embedded camera picker starts folded once configured, with an automatic reopen if saving needs a retry.
- Added a persistent Day/Night switch for the app, including the project lobby, editing controls and Guide. Preview imagery and captions retain their original colors.
- Stabilized the header and working-status banner as a single measured stack. Wrapped navigation no longer overlaps progress or the editor, and starting analysis no longer triggers the old smooth scrolling jump.
- Refreshed the application entrance with an ivory/violet palette, visual project choices and optional AI setup after the primary workflows. Kept the editing workspace dark with clearer selection and panel contrast.
- Redesigned the English/Hebrew product website around a real editor preview, simpler workflow explanations and clearer download guidance, with responsive layouts and keyboard focus indicators.
- This visual refresh does not change playback, timeline geometry, AI providers or saved projects.

## 1.1 Beta — 2026-09-23

- Recovered preview audio when a browser rejects an already-connected media element. Audio graph failures now retry with a fresh player, then use clearly labelled basic playback if needed, instead of breaking Play/Pause. Fixed double attenuation when the mixer starts after the first Play gesture.
- Fixed preview playback conflicts between the audio mixer and hidden A/B videos. Deliberately stopping a loading player at a gap or held frame no longer stops the entire timeline; genuine playback errors are still reported.
- Added a project media library for extra video, images, music and voiceover, with editable timeline layers, waveforms, image motion and audio fades. Added a mixer for original audio, voiceover, music, effects and master level; Solo is preview-only. These tools need no AI account, and added media fits within the current edit duration.
- Added A/B picture-speed controls that preserve clip length and speech timing. Picture speed can lose lip sync or hold the last source frame; it does not retime the whole picture-and-sound edit.
- Added QHD 1440p and 4K 2160p export options alongside 720p and 1080p. Higher output resolution does not restore missing source detail.
- Added bounded local Hebrew/English recovery with timing and English-term safeguards, plus per-line low-confidence transcript review notes. Lite adds no recovery pass; this change makes no measured accuracy claim and adds no cloud requests.
- Updated English/Hebrew guides and website help with API role requirements, provider compatibility, costs, privacy and current feature limits.
- Simplified the public download name to `CUTROOM-1.1-Beta.zip`; internal manifests retain build provenance. Added scrollable media lanes, live mixer autosave and transactional protection against rebuilds that would discard added media.

## 1.1 Beta — 2026-09-22

- Added one-click 16:9 Landscape and 9:16 Vertical controls at the top of the editor, including manual projects. Format changes preview immediately and save for export without AI, rebuilding, seeking or changing clips.

## 1.1 Beta — 2026-09-21

- Kept explicitly selected embedded-camera layouts through AI drafting, refinement and rebuilds, including higher-quality analysis passes.
- Added immediate camera-frame previews and automatic saving, with visible save status and retry on failure.
- Simplified Layout: common compositions first, with extra layouts and precise camera coordinates in expandable sections.
- Preserved independent clip framing and removed redundant camera-layout confirmation controls once active.
- Replaced the README opening artwork with the maintainer's CUTROOM launch image.

## 1.1 Beta — 2026-09-20

- Tidied the repository root: guides live in docs, community policies in .github, and development helpers beside their tools. Application launch commands and saved-project locations are unchanged.
- Reused the documentation screenshots and guides when preparing the website, instead of keeping duplicate copies in Git.
- Fixed keyboard focus after choosing an editing preset or closing its help panel.
- Added familiar snapping keys, Premiere Extract and timeline-only Pro Tools F7/F8 tool selection.
- Reorganized shortcut help by task, with an in-panel profile selector, per-key adaptation notes and a separate unassigned list.
- Allowed CUTROOM's Shift+R to open Original footage without selecting an unrelated range first.

- Simplified the Windows download to one launcher, an offline quick-start guide and an App folder. Existing source checkouts and installations retain their original layout.
- Established **1.1 Beta** as the current public release label and `1.1-beta` as its technical version identifier.
- Updated launchers, setup markers, package filenames, source manifests and documentation to use the current version consistently.
- Added a compatible cloud API connection alongside Groq, with explicit destination consent and session keys bound to the selected provider and endpoint.
- Clarified Groq's free-tier quotas and optional provider billing, and added independent provider credit.
- Prevented pending cloud connections from sending after cancellation, and separated analysis caches by provider endpoint and selected models.
- Kept the earlier development record below with its original version numbers. This naming change does not represent a rollback of editing features or removal of legacy project compatibility.

## Historical development notes

The following entries describe earlier development builds and retain their original labels. They are historical records, not the current release version.

### Previously unreleased work

- Made the application interface English-only while keeping multilingual speech, transcript and caption support.
- Reorganized Studio into Cut, Layout, Captions and Output task areas.
- Added real caption controls for burn/SRT output, Clean/Bold/Boxed style, safe position, scale and words per caption, all honored by preview and render.
- Improved offline spoken-language detection with evidence from multiple recording windows, confidence aggregation and conservative Hebrew-script correction.
- Made ambiguous language evidence stay visibly low-confidence, preserved weak Yiddish instead of relabeling it, and kept auto-refinement from reporting false 100% confidence.
- Made project deletion atomic on Windows and released browser media handles first, preventing open source/export files from leaving a half-deleted project.

### Previously unreleased - Stabilization workspace

#### Fixed
- Made A and B independent upload lanes with per-source progress/cancel, while serializing project commits so simultaneous imports cannot overwrite one another.
- Replaced physical A/B Director decisions with semantic `screen`/`camera` roles; swapping the sources now changes the result without invalidating the Storyline.
- Added an explicit first-source control for stacked and split layouts, persisted it through refresh/Undo/Redo, and matched browser preview order to FFmpeg export order.
- Preserved valid routing when replacing source B, invalidated stale sync/crop data, and neutralized unreliable automatic offsets instead of moving footage outside the usable overlap.
- Added a manual embedded-camera rectangle for one-file recordings. It works before or after Draft creation and provides a safe fallback when face detection misses.
- Disabled separate Ollama thinking for structured Qwen Storyline passes; thinking-capable models can no longer exhaust `num_predict` and return an empty `message.content`.
- Checkpointed transcript/audio/vision before Storyline so a late model failure does not discard expensive work on long recordings.
- Kept Director failures on an actionable Retry/Back screen and recovered completed drafts across refresh races instead of falling back to the raw-footage view.
- Blocked traversal-like project IDs from deleting `data/projects` or the entire data directory.
- Made source replacement transactional: failed probes/saves preserve the previous media and all partial files are cleaned.
- Serialized project mutations with optimistic revisions; autosave is isolated per project and ignores stale responses.
- Added bounded, deduplicated, persistent jobs with refresh recovery, restart interruption reporting and safer cancellation.
- Added source/settings/pipeline fingerprints so stale transcript, vision and story caches are not reused.
- Prevented analysis or render results from committing after their source edit changed.
- Drained noisy FFmpeg audio stderr concurrently and bounded render CPU threads/export retention.

#### Added
- Added layout-aware ASS captions that move away from the creator panel in stacked and confirmed embedded-facecam compositions.
- Added a deterministic, geometry-preserving editorial-effects engine with a strict whitelist, bounded strength/count, no raw AI/FFmpeg input, and a one-click off switch.
- Added up to three ranked Reel edits from the same cached Story Beat analysis, with undoable switching and no repeated transcription/model pass.
- Added a per-scene Source Mixer list so every AI layout decision can be inspected, previewed and overridden directly.
- Added an extensible edit-style catalog and one-click Stream Highlights, Funny Moments, Strong Commentary, Stream Story Recap and low-resource Clean VOD presets.
- Added style-aware Story AI guidance, persisted `edit_style` metadata and a public style catalog for the UI.
- Manual Timeline delete/restore/split with Undo/Redo.
- Editable transcript text used by captions and future Director runs.
- Keyboard-accessible upload slots, Studio tabs and Timeline range selection.
- Draft-rebuild state that prevents exporting settings against an old AI draft.
- Behavioral regression tests for backend safety, jobs, frontend races, manual edits, audio deadlocks and storage cleanup.

### 5.6.1 - Project recovery and quiet expected errors

- Missing local projects/files now return HTTP 404 without an `Unhandled error` traceback in the CMD window.
- The remembered project is namespaced by the current CUTROOM data-directory instance, preventing project IDs from another extracted version from leaking into a fresh installation.
- Startup validates the remembered project against `/api/projects` before trying to restore it.
- Background source preparation tolerates a project being removed while a job is finishing.
- API errors now preserve HTTP status/error codes so the UI can distinguish expected 404 recovery from real server failures.

### 5.6.1 - Hierarchical Story AI

#### Added
- Multi-pass semantic Director for Short/Podcast: **Chapters -> chapter summaries -> global outline -> story plan -> exact beat selection -> critic pass**.
- Story slots require their own material (Hook, Context, Proof/Example, Payoff/Ending) instead of accepting a generic list of highlights.
- Global chapter/outline cache: changing 60s to 3m or refining the brief reuses expensive whole-recording understanding and reruns only planning/selection/critic passes.
- Explicit Story AI readiness/status in the server and UI, including the actual selected local model.
- Release smoke test that verifies the full hierarchical pipeline covers early, middle and late material.

#### Changed
- Semantic Short/Podcast editing no longer silently falls back to ranking rules when Qwen is missing. CUTROOM waits for/prepares Story AI or reports that it is unavailable.
- Candidate compaction now preserves chapter boundaries, AI key beats, semantic roles and uniform chapter coverage; editorial score is only a late tie-breaker.
- The critic receives actual candidate text and checks viewer comprehension, setup/payoff dependencies, continuity and repetition before the draft is committed.
- Qwen3.5 4B remains the default to control memory use; the intelligence gain comes from several bounded passes rather than one oversized prompt.

#### Preserved
- Audio-first dB evidence, speech protection, embedded Facecam Reel layout, Hebrew Enhanced transcription path, burned captions, unified Studio, hard Short targets, YouTube cleanup, two-source sync and deadlock-safe rendering.

### 5.5.0 - Story Director, embedded gameplay Reels and stronger Hebrew transcription

#### Added
- Story Beat planning for Shorts: long transcripts are grouped into coherent ideas before the LLM chooses the hook, context, proof/example, payoff and ending.
- Hierarchical long-video context: a bounded set of story beats covers the full recording instead of asking the model to reason over isolated transcript lines.
- A two-hour transcript regression test that requires selected material from early, middle and late source sections.
- Hebrew Enhanced transcription path using `ivrit-ai/whisper-large-v3-turbo-ct2` in Quality mode and on suitable GPU-assisted Balanced runs.
- Quality semantic planning can use Qwen3.5 9B when it is already installed; Auto/Balanced keep Qwen3.5 4B and do not pay the heavier cost.
- Temporal face clustering for one-file screen recordings so a small persistent creator camera is preferred over transient faces inside gameplay/video content.
- Multi-cascade frontal/profile face fallback without adding another neural runtime.
- Real embedded-Reel render smoke test verifying the top panel is the creator camera and the bottom panel is gameplay.

#### Changed
- `embedded_stack` now follows the requested Reel convention: **Facecam on top, gameplay/screen below**.
- The browser preview mirrors the same embedded layout instead of showing the original source twice.
- Vision analysis downscales sampled frames before face detection and remains lazy so the improved detector does not turn every edit into a heavy vision job.
- Story prompts are bounded by performance mode: fewer/shorter beats in Lite, a balanced prompt in Auto/Balanced, and a larger context only in Quality.
- Very long recordings stay on the light transcription path in Auto unless the user explicitly chooses higher quality.

#### Preserved
- Audio-first dB evidence, user silence threshold, speech protection, burned captions, unified Studio, hard Short targets, YouTube audio-cleanup path, two-source sync and deadlock-safe rendering.

### 5.3.0 - Unified Studio Workspace

- Replaced the below-the-page Advanced section with a full Studio workspace that keeps the live preview and editing controls in the same viewport.
- The actual preview player moves into Studio and back to Director, so framing, camera and timeline changes are always visible beside the control that changed them.
- Added a fixed Studio header with draft status, export and return-to-Director actions.
- Timeline, framing, transcript and settings now live in a single tool pane with independent scrolling instead of forcing page-level up/down navigation.
- Framing controls use the main live preview in Studio; the redundant secondary crop preview is hidden while Studio is open.
- Added responsive Studio layouts for desktop, tablet and mobile plus Escape-to-close and scroll-position restoration.

### 5.2.0 - Outcome Director, hard Short targets and Studio timeline

#### Added
- Hard target-duration enforcement for Shorts. A 60-second target now constrains the actual draft and final render rather than acting as a prompt hint.
- Goal-specific Director paths: Short/Reel selects a coherent story; default YouTube keeps structure and performs measured dead-air/audio cleanup.
- Full-recording transcript compaction for the local LLM using opening/closing context, strong passages, neighbors and uniform timeline coverage.
- Automatic embedded screen + facecam stacked composition for eligible one-file vertical Shorts.
- Real measured audio waveform on the Timeline, plus silence/clipping evidence overlays and background thumbnail filmstrip.
- Timeline drag scrubbing, pointer-centered zoom, horizontal pan, playhead follow and fit gesture.
- Outcome explainer in the primary UI and goal-specific defaults. Pace/audio/model controls moved to Studio.

#### Changed
- Short removal budget can exceed the old 88% ceiling when the requested target genuinely requires it, while staying close to the requested duration.
- YouTube cleanup can remove a very large proportion of measured dead air without enabling semantic low-value guessing.
- Explicit YouTube instructions can still request conservative semantic cleanup while the default remains audio-only.
- Embedded vertical composition gives screen content more space and biases its crop away from the facecam region.
- Vision sample count follows Lite/Balanced/Quality performance mode.
- Heavy thumbnail generation stays in background source preparation and never blocks the Director.

#### Preserved
- Audio-first evidence, lighter 4B default model, non-blocking source/model jobs, 40GB transport fix and deadlock-safe real FFmpeg render progress.

### 5.1.0 - Audio-first Director and lighter runtime

#### Added
- Deterministic 200 ms audio measurement for RMS, peak, noise floor, silence, quiet speech, loud speech and clipping.
- Natural, Clean and Tight sound-cleanup policies plus advanced controls for silence length, retained pause, maximum removal ratio and speech gain correction.
- Evidence attached to audio-driven edits so CUTROOM can explain why a silence was shortened or a level was changed.
- Separate spoken-language and performance-mode settings.
- Lite/Balanced/Quality transcription profiles and reusable analysis cache for Director refinements.

#### Changed
- CUTROOM is now audio-first: measured sound decides where an edit is safe; transcript/semantic AI decides whether the content should be changed.
- Default semantic model changed from Qwen3.5 9B to Qwen3.5 4B. The 9B model remains an optional fallback/quality choice.
- Lite mode uses Whisper Base on CPU; Balanced uses Small; Quality uses Turbo only when explicitly selected or appropriate.
- Visual analysis runs only when framing/camera decisions need it instead of on every edit.
- Director no longer blocks on filmstrip/waveform generation.
- FFmpeg analysis and CPU rendering use bounded thread counts.
- Automatic UI-language detection now requires stronger script/lexical evidence before switching languages.

#### Preserved
- Two-source editing, audio sync, vertical composition, upload-limit fixes, non-blocking background jobs and deadlock-safe rendering from 5.0.4.

### 5.0.4 - Director unblock and background-job isolation

- Fixed the post-upload proxy preparation job incorrectly disabling **Create my edit**.
- Separated foreground Director/render work from background proxy/model preparation executors.
- Model downloads no longer block the first Director draft; deterministic editing remains available immediately.
- Added a transcription failure fallback so missing/corrupt Whisper or first-use model download errors do not kill the whole edit.
- Reloads the latest project before committing a Director draft so concurrent proxy updates are preserved.
- Empty transcripts skip Ollama entirely instead of waiting on a model that cannot improve the result.
- Added regression tests for background-job starvation, non-blocking model installation and transcription fallback.


### 5.0.3 - large upload transport fix

- Fixed `ERR_CONNECTION_RESET` during large local video imports caused by Waitress retaining its 1 GiB default request-body limit while CUTROOM advertised a 40 GiB per-file limit.
- Waitress now receives the same request-body ceiling as CUTROOM/Flask, including multipart overhead.
- Increased the inactive upload channel timeout to one hour for unusually slow local disks or security scanning.
- `/api/system` now reports the transport request-body ceiling alongside the application upload limit.
- Added a release regression check preventing the hidden 1 GiB transport cap from returning.


### 5.0.3 - render reliability and real progress

- Fixed a real FFmpeg pipe deadlock that could leave long renders stuck at 92%.
- Restored FFmpeg `-progress pipe:1` and `-nostats`, matching the proven v3 progress strategy.
- Drains FFmpeg stdout and stderr concurrently so neither pipe can block the encoder.
- Replaced artificial timer-based render progress with media-time progress reported by FFmpeg.
- Added a distinct finalization phase after encoding before the export is marked complete.
- Added a render heartbeat so a live process does not look frozen when no fresh timestamp has arrived.
- Added regression coverage that writes more than the normal stderr pipe capacity and verifies the renderer still exits.
- Verified two-source 9:16 output, a 30-second stress render, and hardware-encoder failure with CPU fallback.

### 5.0.1 - upload clarity and Director loading polish

- Kept the per-source upload limit at 40 GB and exposed it through `/api/system`.
- Added browser-side size validation before any upload begins.
- Added explicit 413 `file_too_large` responses and fixed the Flask error-handler ordering.
- Added a distinct insufficient-disk-space error instead of mislabeling local import failures as network errors.
- Added the upload limit directly to both source cards.
- Simplified Director progress to a polished loading animation, one fixed headline and four short progress bullets.
- Stopped exposing verbose backend/model messages during Director work.

### 5.0.0 - AI Director recovery release

- Rebased the Windows setup on the Python discovery path that worked in v3.
- Retained a corrected private uv fallback without the incompatible `--managed-python` / `--python-preference` combination.
- Replaced deprecated `UV_NATIVE_TLS` with `UV_SYSTEM_CERTS`.
- Made model installation part of the first Director action instead of blocking initial setup.
- Added automatic Whisper GPU-to-CPU fallback.
- Preserved two-source editing, synchronization, vertical composition, embedded-camera detection and one-draft Director workflow.
- Added regression checks for the exact Windows failure reported in v4.0.4.
- Restricted the runtime to Python 3.11 or 3.12 for the local transcription stack.
- Replaced fragile native-process argument reconstruction with direct PowerShell invocation.
- Set qwen3.5:9b as the recommended local editor model, with smaller installed-model fallbacks.
- Fixed single-source rendering when no two-camera synchronization record exists.
- Added a complete two-source Director-to-render smoke test.

### 4.0.4 - private Python bootstrap hotfix

- Removed the dependency on a system-wide Python installation and on `py.exe` discovery.
- Added a pinned, checksum-verified uv bootstrap for x64, ARM64 and x86 Windows.
- Added a CUTROOM-owned Python 3.11 runtime under `.tools\python`.
- Added a CUTROOM-owned virtual environment built through uv.
- Added runtime path discovery for FFmpeg, FFprobe and Ollama after winget installation.
- Added persistent Windows setup logs and a focused last-error report.
- Added release tests that reject a return to system-Python discovery.

### 4.0.2 - Windows installer parser and recovery hotfix

- Rewrote `setup_windows.ps1` as ASCII-only PowerShell 5.1-compatible source.
- Removed the UTF-8 em dash that Windows PowerShell 5.1 could misdecode as a smart quote.
- Added process PATH refresh after winget installs.
- Added explicit exit-code checks for Python, pip, FFmpeg, FFprobe, and model commands.
- Added partial virtual-environment repair and setup-marker validation.
- Added `repair_windows.bat` for a forced installer rerun.
- Added release checks that reject non-ASCII Windows launcher scripts and incomplete setup guards.
- Added a Windows-native parser self-check before setup begins.

### 4.0.1 — Distribution and render hotfix

- Rebuilt the missing downloadable archive and added post-extraction verification.
- Fixed two-source FFmpeg renders when a shot uses only one source branch.
- Fixed zero-length cut ranges created when fully negative ranges were clamped.
- Fixed release DOM-ID validation and the standalone render smoke import path.
- Raised the minimum Flask and Werkzeug versions used during setup.

### 4.0.0 — AI Director

#### Distribution hotfix

- Fixed two-source FFmpeg renders when a shot uses only one branch of a split source.
- Fixed the release test that validates cached DOM element IDs.
- Fixed the standalone render smoke test import path.
- Added secure minimum versions for Flask and Werkzeug.

#### Product workflow

- Replaced the editor-first landing screen with a three-step Director workflow.
- Added one primary action: generate one applied draft.
- Moved Timeline, framing, transcript and technical settings into an optional Advanced panel.
- Added one-click refinements: shorter, keep more, more energy, fewer switches and focus speaker.
- Kept Render in the sticky top action bar.
- Restored normal document scrolling and explicit scrollbars.

#### Editorial intelligence

- Added faster-whisper transcription with word timestamps and automatic language detection.
- Added local Ollama editorial reasoning with strict segment-ID validation.
- Added deterministic fallback editing when Ollama is missing or fails.
- Added filler, repeated-take, false-start and low-value segment scoring.
- Added pace-specific removal limits and target-duration guardrails.
- Added a compact decision summary instead of a raw list of every cut.
- Added synchronized SRT generation after cuts.

#### Multi-source and framing

- Added audio cross-correlation synchronization for source A and B.
- Added bounded automatic camera plans with minimum shot length and switch caps.
- Added A, B, stacked, side-by-side and picture-in-picture output.
- Added local face focus and embedded-camera candidate detection.
- Added screen + embedded-camera vertical composition.
- Added exact aspect preview, focus position and zoom controls.

#### Performance and reliability

- Import becomes usable after copy and probe; proxy generation runs in the background.
- Scene analysis now samples reduced frames.
- Added lazy AI model loading and hardware-aware Whisper compute selection.
- Added FFmpeg hardware-encoder detection with software fallback.
- Added cancellable jobs and partial-file cleanup.
- Added atomic project persistence and strict public-path handling.

#### Quality gates

- Added unit, property-based, API, caption-retiming and release-structure tests.
- Added a real two-source vertical render smoke test.
- Added clean-release validation and archive verification.
