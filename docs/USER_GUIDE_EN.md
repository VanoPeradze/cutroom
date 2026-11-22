# Your first edit in CUTROOM

### Roll a cut without moving the rest of the edit

Pause **Edited video** and select an imported clip on a saved visual or audio track. In its Media inspector, open **Roll a shared cut**. Choose its Start (previous neighbor) or End (next neighbor). Check the two filenames, track name and cut timecode, then choose **1 frame earlier**, **1 frame later**, or **Roll to playhead**. One clip gets longer by exactly as much as the other gets shorter. The two outside edges, edit duration and all other tracks stay put. One Undo restores both sides. Attached sound follows the cut without changing playback speed; picture keeps its own speed and source position.

The clips must touch on the same unlocked track. For a legacy edit, choose **Enable editable tracks** separately if you want this workflow. A gap or overlap is not treated as a cut. Missing source handles, pan/zoom motion or a fade at the cut are refused, not silently shortened or frozen. Use the ordinary trims for separate edges. This control does not roll original A/B or text, create a crossfade, or change any source file.

CUTROOM is a free, open-source video editor in beta. It helps turn recordings into an editable draft; you decide what makes the final cut. The app interface is English. [עברית](USER_GUIDE_HE.md)

Start with the short path below. The later sections explain the controls when you need them.

Use **Day / Night** in the top bar to change the app's appearance; your choice is saved in this browser. The video preview keeps its original colors. **Guide** opens searchable help from any screen. While a job is running, its status and **Stop process** stay together below the navigation.

Use the **bottom workspace bar** to switch between Media, Edit, Layout, Audio, Captions and Output. Import or build a draft from Project overview, refine it in these workspaces, then use Export. Audio opens the mixer directly. Edit separates Clip controls from Effects · Green screen, with fine-tuning collapsed until needed. Layout contains composition and framing. Stabilize footage opens its Media tool from Effects. The player and timeline remain available; resize the divider to give your tools more room. Each workspace remembers its width.

**Numeric controls:** drag a number or a slider’s numeric readout up to increase it and down to decrease it. Hold Shift for slower adjustment. Release to apply one change; Escape or losing window focus cancels a drag. The wheel changes only the focused field and groups a short burst into one change. Typing and arrow keys remain available. Controls keep their existing limits, steps and Apply/save behavior.

## The quick path

1. Choose the Windows or Mac download and extract the entire ZIP. Its launcher sits beside **App**. If using the older combined ZIP, open **windows** or **mac** first. On Windows, double-click **`START CUTROOM.bat`**. On Mac, double-click **`START CUTROOM.command`**. Read and approve the setup prompts, and keep the launch window open. Leave **START HERE.html** (offline help) and **App** (technical files and saved work) beside the launcher. Older Windows packages and GitHub source checkouts still use `run_windows.bat`. Mac users: read the [Mac setup guide](https://github.com/VanoPeradze/cutroom/blob/master/docs/MAC_BETA.md) first; macOS 15+ is required, and first-time dependencies may require Homebrew.
2. Choose **Manual edit**. The empty editor opens immediately, with no recording, AI account or generated draft required.
3. Click **Import video** in the empty-timeline panel or **Add media** in the media pool. Choose a short, non-sensitive video. Its full recording appears on the timeline automatically. Click the timeline ruler to seek; **Space** plays or pauses.
4. Choose **Range**, drag over an unwanted passage and select **Remove from video**. Try **Undo**. Then select **Cut** and click once to split a clip.
5. Open **Output**, confirm the shape and frame rate, then **Export → Start export → Download video**. Watch that downloaded file outside CUTROOM.

Empty Manual projects are saved and remain available on Home, including before the first import. The current engine starts with a video recording, stored internally as source A; audio-only or image-only projects are not supported yet. After that first video, **Add media** imports additional video, audio and images without replacing it. Use **Append** or **In / Out** for sequential video shots, or **Overlay** for a picture layer.

**Import a batch:** both the empty-editor import button and **Add media** let you select multiple files. In an empty Manual project, the first selected video starts the timeline even if the picker listed audio or images first. Every other file goes to the media pool in its original relative order. Existing timelines are not replaced or automatically extended by importing a batch. The visible queue prepares one file at a time and shows which files are ready, need attention or were not imported. **Stop import** and **Stop process** stop the remaining queue and cancel active work through the normal cancellation path. Files already committed may remain in the project; completed imports are never rolled back. An error or project switch stops the rest. The queue lives in the current browser tab, so after reloading, select any unimported files again.

**Drag from the media pool:** drag a ready imported video, audio file or image to the displayed timeline time. An ordinary drag inside the existing edit adds an overlay/audio occurrence, not an overwrite or ripple insert. A video dropped at the end appends a new shot and extends the timeline; audio and images need room inside the existing edit. The original **Add**, **Overlay**, **Append** and **In / Out** controls remain available for keyboard/touch use and precise source selection. Original A/B cards and files dragged from outside the app are not part of this drag workflow. Undo removes the new occurrence without deleting its imported file.

**Insert a shot in the middle:** hold **Shift** while dragging a ready video into the existing edit, or choose **In / Out → Insert at edit playhead** for a selected source range. Insert opens time for the shot: crossing A/B footage, static imported video/images, audio and custom titles/captions split at the insertion point and resume afterward; later items move together. Their retained source content, picture speed, framing and outer audio fades stay unchanged. The inserted shot is selected and one **Undo** restores the entire previous edit. At the tail, Shift-drag still means **Append**.

Insertion is refused rather than silently changing an animated crossing (pan/zoom), cutting inside an audio fade, leaving a media/text piece shorter than 0.08 seconds, or exceeding clip/time limits. Choose a boundary or a point outside those effects. Affected locked A/B tracks, timed draft audio plans, active alternative captions and uncertain or crossing edited automatic captions remain protected. This is imported-video insertion, not general mixed-layer ripple support for every source move or overwrite. If the edit changes in another window, review the refreshed insertion point instead of replaying the old placement.

**Split the selected clip:** select an imported video, audio, image or custom title/caption occurrence, place the playhead inside it, then use the main **Split** button, **Split at playhead** in its inspector or the active keyboard profile's Split command. The right piece becomes selected; other layers, source A/B and the edit duration do not move. Native layer splits align to output frames and keep at least 0.08 seconds on each side. One Undo joins the original occurrence again. The Blade tool shows the same readiness and can be cancelled before release. Partial pan/zoom animation and split points inside audio fades are rejected rather than silently restarted or reshaped. Automatic transcript captions follow speech and are not split by this clip command. With no layer selected, source Split keeps its existing A/B scope. Shortcuts remain inactive in protected native controls such as input fields, buttons and dialogs.

**Trim or extend the selected layer:** select an imported video/audio/image or custom title/caption, then use **Trim start / Trim end** in its inspector, the active profile's edge-trim shortcut (Q/W in CUTROOM and Premiere), or drag that clip's timeline edge. Only this occurrence changes. Its opposite edge, other layers and the edit duration stay in place; the same clip remains selected and one Undo restores it. Native edge times align to output frames, retain at least 0.08 seconds and stay within the edit and available source footage. Head trimming advances normal-speed sound and independent picture time correctly. Static, unfaded edges can extend to reveal available footage.

The new Trim commands and edge drags refuse a pan/zoom resize, a new boundary inside an audio fade, extending a faded edge, or extending before the independent picture/audio source starts. They preserve retained content and the opposite outer fade, rather than silently restarting motion, reshaping fades or clamping picture time. A blocked drag previews no changed geometry; Escape cancels without saving. Automatic transcript captions use their own caption timing controls. With no media/text layer selected, the existing source trim scope still applies: Together closes time; A/B-only leaves other layers in place. Numeric Start/End fields remain explicit timing edits with their existing behavior, not these guarded Trim commands. Media Source in uses the separate guarded Slip command below.

**Slide a shot between its neighbors:** With Edited video paused, select a middle imported clip between two touching clips on the same saved, unlocked track. Open **Slide between neighbors** in its inspector. **1 frame earlier/later** moves both cuts together; **Slide start to playhead** places the middle clip’s start at the current output frame. The middle shot keeps its full source, duration, speed, fades and motion. For a pre-existing subframe start, the first visible frame lands on the playhead; the original subframe offset is preserved. One outside shot gets longer as the other gets shorter, without moving later clips. Check the three names before applying. One Undo restores all three. If an outside shot lacks original material or has motion or a fade that would change, the slide is refused rather than trimming it silently.

**Replace a take without moving the cut:** Pause **Edited video**, select one imported timeline clip and open **Replace take in place** in its Media inspector. Choose another project file of the same type. For video or sound, enter **New Source In** or choose **Use saved In / Out** to bound the replacement to that file’s browser-local marks. Picture and ordinary sound start together at the new In; picture runs at the clip’s existing speed. The full duration must fit, without freezing or shortening. **Replace this take** keeps the clip ID, both edit edges, its track, framing, motion, volume and fades. Other uses of either file and source marks are not changed. One Undo restores the old take with its original, potentially different picture and sound clocks. A locked track, a source-sound mismatch with Include source sound enabled, or an active file-level Chroma Key is refused. This does not relink files or replace original A/B footage.

**Slip content without moving the clip:** choose **Slip**, then drag an imported video/audio occurrence right for later source content or left for earlier. The viewer previews the candidate content while the clip stays at the same timeline position and length. Release saves once; Escape restores the original content without saving. In the Media inspector, **Source in (Slip)** sets the exact normal-clock source time; **Earlier 1f / Later 1f** shifts by one output-frame interval. Gesture delta is frame-aligned without rounding the original source in-point. Picture follows its independent speed/offset, while sound stays at normal speed.

Slip preserves clip identity, framing, fade timing and pan/zoom phase because its timeline range does not change; it intentionally chooses different source content. Source bounds and negative independent picture time are refused, never shortened or clamped. One Undo restores it. It supports imported video/audio, not source A/B tracks, still images, custom text or automatic captions. Alt keeps its existing snapping meaning elsewhere; no keyboard profile shortcuts were reassigned. Media **Source in** uses this guarded Slip command; numeric **Start/End** remain separate explicit timing edits.

**Control visual overlap:** select an imported video or image and open **Visual stacking** in its inspector. **Send backward / Bring forward** move it one position; **Send to back / Bring to front** move it to an end of the imported visual stack. The rank is global, including clips at other times, so a step need not change the current frame. This changes only which imported picture covers another: the same clip stays selected and timing, source content, effects, sound, playhead and edit length stay unchanged. Audio-only entries retain their slots. A/B remains below imported pictures; custom text and captions remain above. One Undo restores the order. This is not track reassignment or text-layer reordering.

**Compare without removing a layer:** select an imported video, audio or image, or a custom title/caption, and uncheck **Enabled in preview & export** in its inspector. That occurrence's picture and attached sound, or its custom text, disappear from both preview and export. Disabled custom captions are also omitted from SRT. Timing, source content, sound settings, styling, stacking order and edit length stay unchanged; re-enable it or use Undo to restore it. The timeline and Index label it **Disabled**, but it remains selectable and editable. Split and Duplicate preserve its disabled state. Disabled rows still count toward clip/overlap limits and mixed-edit safety checks. If no picture is enabled at a point, the existing lower layers show, or the frame is black. A saved edit containing only disabled layers can still play and export. This switch does not change A/B sources or automatic transcript captions, which keep their separate controls.

**Open a clip's original source:** with **Edited** selected, put the playhead inside an imported video and choose **Open source at playhead** in its Media inspector. Double-clicking an imported video in Select/Move opens the same source review at the clicked edit position. The source position follows that occurrence's picture speed and independent slipped picture start, not its normal-speed audio clock. Disabled or covered videos can still be inspected. The review shows original source picture and sound, not framing, effects or the edited mix; browser seeking is approximate. Opening and closing do not change the edit, history or remembered In/Out marks. Only explicit mark/save/insert/append actions change their respective selection or edit. Pending changes must finish first. At a held last frame, move earlier or open the file's **In / Out** review instead. Images, audio, text and A/B source review keep their existing behavior.

**Frame directly in the viewer:** select an enabled imported video or image and place the edited playhead inside it. Pause, open **Position & size**, then choose **Edit frame in viewer**. Drag the outlined frame to reposition it, or an edge/corner handle to resize its box. The box stays inside the canvas and at least 1% wide/high; its width and height change independently. Each completed drag is one saved change with Undo. Escape during a drag restores the saved frame without saving; **Done framing** leaves this mode. Starting playback, switching to Full source or selecting another clip exits it.

The existing percentage fields remain the precise and keyboard alternative, now retaining fractional percentages; Arrow Up/Down or scrubbing changes 1%. Framing changes only that occurrence's box, not timing, source in-points, audio, Fit/Fill, motion or layer order. Pan/zoom still runs within its original clip span; higher layers can still cover the selected picture. This is not rotation, perspective or source A/B framing.

**Move a whole layer precisely:** select imported video/audio/image or custom text, open **Timeline placement** in its inspector, then choose **Move to playhead**, **Move 1f earlier** or **Move 1f later**. Move to playhead aligns the destination to an output frame; one-frame moves add one output-frame interval to the existing position without rounding away an older fractional start. The same occurrence stays selected, with its full length, source content, speed, fades, framing and motion/text styling unchanged. Other layers, edit duration and playhead stay put; one Undo restores the move.

Ordinary body dragging uses the same fixed-duration Move action and keeps its existing snapping, Alt bypass and timeline-edge bounds. Preview is temporary, Escape cancels, and release saves once. Invalid/unsupported placement or a custom-text overlap limit shows a reason instead of a false preview. This is placement, not Slip, an edge Trim or a ripple edit. Source A/B moves and numeric Start/End timing edits retain their separate behavior; no new toolbar tool or shortcut was added.

Start/End timing fields accept exact fractional frame positions. Their focused arrow keys and numeric scrubbing still adjust by 0.01 seconds, preserving the fractional origin rather than marking a valid frame position as an invalid number. These fields remain explicit timing edits, not whole-clip Move.

**Duplicate a layer at the playhead:** select an imported video, audio, image, or your own title/caption, put the playhead where the copy should start, then choose **Duplicate at playhead** in Clip tools or its inspector. The entire occurrence is copied with its source content, picture speed, framing, fades, motion and text styling; the new copy is selected. The original, other layers and edit duration stay unchanged. No source file is duplicated or deleted. One Undo removes the copy; Redo and saved reopen preserve it.

The destination aligns to an output frame, while the original duration is retained. If the whole copy will not fit, move the playhead earlier: this command never truncates the copy, ripples later clips or extends the edit. It respects the existing 200-media / 2,000-text limits and maximum of 16 simultaneous custom text clips. Automatic transcript captions cannot be copied this way. With no independent layer selected, **Duplicate clip** keeps the existing A/B source-scope behavior. No new shortcut or drag gesture is assigned.

**Cut out time across the edit:** choose **Together / Whole video**, mark a timeline **Range**, then **Remove from video** (or the two-click **Cut out** tool). The selected time is removed from A/B footage, imported video/audio/images and custom titles/captions. Crossing items retain their before/after pieces with the correct source time; later items move left together. The read-only **Cut out preview** beside timeline navigation shows the duration change and affected occurrences before you act. Original recordings and imported pool files stay saved. One **Undo** restores everything, including a fully emptied timeline.

Partial pan/zoom motion, cuts inside audio fades, retained media/text pieces shorter than 0.08 seconds, clip limits, affected source locks, timed audio plans and ambiguous or overlapping reviewed automatic captions are blocked rather than silently changed. Ordinary automatic captions follow the retained source words. A/B-only removal still leaves a gap and does not move other layers. Deleting a selected imported-media/text occurrence still removes only that occurrence, without closing time. Source Review removal, source moves, edge trims and overwrite keep their separate existing behavior; this is not a universal ripple engine.


Manual mode does not generate a transcript or AI story. Adding library media, typing titles/captions, importing subtitles, mixing audio and exporting work without an API key or AI models. When you are comfortable, start a Short/Reel or YouTube project and set up an AI connection.

## 1. Pick the result before adding footage

| Starting point | Initial result | Best first use |
| --- | --- | --- |
| **Short / Reel** | Vertical 9:16, with AI-assisted moment selection | A focused excerpt from a longer recording |
| **YouTube video** | Horizontal 16:9; default cleanup keeps the recording's order | An explanation, gameplay session or longer spoken video |
| **Manual edit** | Empty horizontal 16:9 editor; first video starts the full-length timeline | Direct editing without AI models or an account |

These are starting settings, not irreversible decisions. **Output** changes the format later. A YouTube cleanup is not the same as a short highlight reel: preserving useful structure matters more than reaching a tiny target duration.

The welcome screen and **Projects** offer **Open editor**, **Rename** and **Delete** beside each project. In Projects, search by name and sort by **Recently edited**, **Name A–Z** or **Oldest first**. Rename opens a name field; choose **Save name** to apply it without reopening the edit. You can also rename in the editor's top bar.

**Delete** opens a confirmation. **Keep project** cancels; **Delete project permanently** removes the project, imported media copies, saved edits, previews and exports stored by CUTROOM. Original files outside CUTROOM are not deleted. There is no undo for project deletion. Wait for an import or active job to finish, or stop the job in the editor first; deleting does not cancel it for you.

The save indicator tells you whether changes have finished saving. Avoid editing the same project in multiple tabs.

## 2. Choose where AI runs

Open **AI connection**. Selecting an option is not enough: choose **Use local AI** or **Use this cloud connection** to save it. Switching is unavailable while processing is active.

| Option | What you get | What you need |
| --- | --- | --- |
| **On my computer** | Local transcription and Story planning; no AI-provider fees or content upload to one | Initial model downloads, disk space and enough memory; speed depends on your machine |
| **Online — Free tier** | Groq processes extracted audio and transcript/editing context, reducing local AI work | Your Groq Free key, internet and remaining quota; free within Free tier quotas |
| **My own API account** | Groq or a compatible public HTTPS provider processes transcription and Story planning | Your endpoint, supported models and API key; provider charges may apply. CUTROOM does not buy, upgrade or cap the account |
| **Manual edit** | Timeline, layout, preview and export without AI processing | Your footage; no AI models or account. No automatic transcript or Story draft |

### Local models: what to download

Local AI has two separate jobs:

- **Speech model:** turns spoken audio into words and timings. Smaller models use fewer resources; larger or language-specific models may help difficult speech but still make mistakes.
- **Story model:** reads the transcript to help summarize and select moments. With **Gameplay vision** it also looks at sampled frames to tell action from menus and cutscenes; that uses the same model, with nothing else to download. It cannot recover words that transcription missed.

Models are not bundled in the ZIP. Downloads require internet; installed files are reused. You do not need every model. Downloading a model does not itself change the project's performance profile or switch your AI connection.

1. Open **AI connection → On my computer**, then **Use local AI** if switching from cloud AI. Reopen the panel for setup.
2. In **Prepare local AI**, use **Refresh status**. If the Story engine is missing, **Get Ollama** opens its official installer page. Install it, return and refresh. If installed but stopped, use **Start local engine**.
3. Choose a transcription model, read its purpose and estimated size, then **Download transcription model → Confirm download**. **Not now** dismisses the confirmation without starting.
4. Repeat with **Download Story model** if your workflow needs Story AI. Only one model download runs at a time.
5. Watch progress in this panel. **Cancel download** requests cancellation; closing the panel does not stop the download. After completion, check the **Downloaded** status and choose the matching project performance profile.

| Local profile | Speech model | Approx. speech download | Preferred Story model | Approx. Story download |
| --- | --- | --- | --- | --- |
| Lite | Whisper Base | 0.15 GB | Qwen3.5 2B | 2.7 GB |
| Balanced | Whisper Small | 0.49 GB | Qwen3.5 4B | 3.4 GB |
| Quality | Whisper Turbo | 1.63 GB | Qwen3.5 4B; 9B optional | 3.4 GB (+6.6 GB optional) |
| Quality, Hebrew selected | ivrit.ai Whisper Large V3 Turbo | 1.63 GB | Qwen3.5 4B; 9B optional | 3.4 GB (+6.6 GB optional) |

These are estimates for model downloads, **not total installation size or memory requirements**. Dependencies, cache overhead, footage, previews and exports take additional space. The 9B Story model is optional: Quality works fully with 4B, and the status offers 9B as an upgrade you may download. If the Lite 2B model is missing, an installed fallback (4B by default) is reported and used. Models are not downloaded automatically; choose an installed model or explicitly download the preferred one. A profile label does not guarantee semantic editing quality. [Full model details](MODELS.md)

The Story runtime is **Ollama**, separate from the model weights. CUTROOM's model-download action does not silently install this application or approve Windows permission prompts. Cancelling can leave reusable partial download files. Do not delete shared model caches as a routine fix. **Downloaded** checks files, not whether your computer has enough memory or whether the model has completed a successful inference.

Default chronological YouTube cleanup can work without a Story model; semantic Short/Reel work needs one. Local transcription still needs its speech model. **Manual edit** needs neither. [Connection help](AI_CONNECTIONS.md) · [Installer troubleshooting](TEST_ON_ANOTHER_PC.md)

### Cloud AI: consent, keys and costs

Choose **Groq** or an **OpenAI-compatible provider** under **My own API account**. For another provider, supply its public HTTPS API base URL and model IDs. Both models must use the same endpoint and account: `/chat/completions` must support JSON object mode, and `/audio/transcriptions` must return `verbose_json` with word timestamps. Chat-only APIs and chat subscriptions are insufficient; local/private-network endpoints are rejected. Enter your own key and confirm the destination and data-sharing notice before saving.

The speech model supplies words and timing; the Story model supplies a structured edit based on that transcript. A stronger chat model cannot recover inaudible or missed words. The current connection cannot split these jobs between different providers.

CUTROOM sends selected audio for transcription and transcript/editing context for Story AI. It does not send video frames. This content can include private speech, so use cloud processing only when you may share that material. Video previews and MP4 rendering still run on your computer: cloud AI is not an online render farm or a browser-only installation.

Keys entered in the app stay in memory for the current CUTROOM session and are bound to the selected provider and base URL. Changing either requires a new key and fresh consent. Reconnect after restarting. **Forget session key** clears that key and selects local AI. A supplied key is not a successful connection test. Never include keys in screenshots or bug reports.

The Free tier label does not verify your plan or prevent a paid key from incurring charges. A Story edit can make multiple requests. Quota/key/provider errors stop the task rather than silently switching providers or plans. Cancellation cannot undo usage already accepted by the provider. Mocked regression tests do not certify real provider inference. [Privacy and connection details](AI_CONNECTIONS.md)

## 3. Add footage and check the sources

**Source A** is the main recording. **Source B** is optional; A/B are file labels, not fixed camera/screen roles. Add footage you are allowed to edit. Wait for upload and preparation to finish before starting the draft.

**One ordinary recording:** add only A. You do not need to invent a second source.

**Separate camera and screen:** add both files. Check **Screen recording**, **Camera** and **Audio source**. Choose the audio containing the speech you want transcribed and heard in the export. Automatic synchronization is a starting point; listen near both the beginning and end.

**Camera already inside one recording:** add that combined file only as A. In **Layout**, choose a reference frame and move/resize the camera rectangle. The video updates immediately and changes save automatically; wait for **Saved**. To accept the suggested rectangle unchanged, choose **Use camera layout** once. Do not upload the same file again as B. The camera fills the top 30%; the remaining screen fills the bottom 70%. This choice carries into the AI draft and rebuilds. It crops one recording into two views—it cannot recover hidden pixels or a separate camera file. A camera that moves during recording needs review.

In **Advanced**, **Source B offset** adjusts sync for the whole edit. Positive values place B later; negative values earlier. The one-frame buttons nudge precisely. Source roles, audio, order and sync are whole-edit settings, even with a short range selected.

## 4. Prepare an AI draft

- **Speech language:** choose the actual spoken language when known. Auto-detect can be wrong with short speech, music or mixed languages. This workflow transcribes speech; it is not a complete translation service.
- **Edit style:** guides rhythm and moment selection. It does not clone a creator or add licensed assets.
- **Gameplay vision** (AI draft settings): *Automatic* lets the local Story model look at sampled frames for CUTROOM Smart and the streamer styles when an NVIDIA GPU or Apple Silicon is available. It favours visible fights and skips menus, maps and loading screens, and adds a **Best gameplay action** Reel option. When the frames show a game recording, a Short (except **Stream Story** and **Chill Story**) is built from **gameplay moments**: the stretches with the most on-screen action and excitement in the sound, without cutscenes, menus or loading screens, and without cutting a spoken phrase in half. The game characters' dialogue is not used as the story, so you get the fights instead of a retelling of the game's plot. The draft summary lists the moments it chose. *On for every Short* also runs on CPU, more slowly. *Off* turns it off. Frames stay on your computer, and it never runs with cloud AI. It is evidence, not a guarantee: review the draft.
- **Target length:** sets the duration budget for a single-moment Short/Reel style. Sentence boundaries and source coverage can shorten the result; check actual duration.
- **Director instruction:** an optional brief, for example “Keep the explanation and its example; remove repeated setup.” It guides editing, not unrestricted video generation.
- **Burn captions into video:** captions become part of the MP4 picture. You can adjust them later.
- **Audio cut line:** audio below the threshold is a possible silence cut, not a command to remove all quiet sound. **Use recommended** starts from measured audio. **Handle silence longer than** sets the minimum quiet duration; **Silence to keep** leaves a breathing pause. Audition quiet speech before making cuts more aggressive.

Choose **Build my first cut** when the readiness message is satisfied. Transcription, story work and preview preparation take different amounts of time. **Stop process** requests cancellation; wait for completion before retrying.

**Clean VOD** keeps natural, chronological cleanup rather than forcing fast highlight cuts. Presets guide the result; review the selected content yourself.

If a job fails, read the explanation and fix that cause. Original recordings are not overwritten. A larger model cannot fix wrong source routing or recover inaudible speech.

## 5. Review the first cut

The overview shows the draft, before/after duration and **What changed**. If **Reel options** appear, compare them; they are candidates, not proof of better storytelling. **Most intense moment** is the strongest continuous stretch of the requested length, measured from loudness, activity and spoken reactions. Each card's energy is relative to the same recording, not a prediction of views. When CUTROOM finds your facecam inside the recording of a vertical Short, the overview offers **Preview streamer layout** (camera on top, game below); confirm the camera frame in Layout before it is used.

**Shorter**, **Keep more**, **More energy**, **Fewer switches**, **Focus speaker** and **Try another cut** ask for draft changes. These are editorial actions, not playback controls. Review the result before fine manual work: AI actions can change the draft. Use **Studio** for precise editing.

When a rebuild keeps your manual timeline, **Review AI draft** opens the saved proposal separately. **Current timeline** describes the active edit; **After applying** is the server-validated result of the existing source-track reset, not merely the candidate's nominal duration. Older drafts without a generation receipt are labelled **Review saved draft**, never “new”. This review remains available after reopening without needing a recent job notification.

Play the proposed original **source A passages** before deciding. This is normal-speed source inspection, not a rendered candidate: source B, manual layers, effects, captions and the edited sound mix are not previewed here. Playback is not approval of AI meaning or transcription quality. **Keep current edit** or Escape closes without saving or discarding the proposal. Pending unsaved text/settings must be resolved first; opening review never silently saves them.

**Apply reviewed draft** performs one undoable source-track reset. Imported media and custom text stay at their existing times; they are not removed or retimed. A shorter result that cannot contain them, a protected source or another existing validation problem blocks Apply and explains why. Current project settings, mixer and crop remain: generation may already have changed some settings, and this review does not reverse those changes. Undo restores the preceding timeline and proposal availability. A consumed proposal does not reappear as new after another edit/reload. If the project or source changes during review, reopen it rather than applying stale information.

**Gameplay moments.** When a Short is built from gameplay moments, **Edit → AI suggestions** lists them under **Gameplay moments in this draft**, each with its time range and the model's short description; click a row to jump to it. **Uncertain** means weak evidence: no analyzed frames cover the moment, its main screen was not read as gameplay, or it shows little action. If a moment is a replay, a camera feed or a cutscene, choose **Not live gameplay** and then **Rebuild Draft**: the next draft leaves that range out and fills the time with other moments. **Undo mark** removes the correction. The mark is saved with the project and can be undone; it does not change the model's stored answers.

## 6. Find your way around Studio

| Area | Purpose |
| --- | --- |
| **Preview** | Watch and seek; compare Edited video with Full source; open video-only Full screen |
| **Timeline** | Select, split, remove, restore, move and trim individual cuts |
| **Media & audio** | Import extra video, images and sound; position media layers and balance the audio mix |
| **Layout** | Arrange A/B, confirm an embedded camera and frame each clip |
| **Captions** | Add custom text/captions, import SRT/VTT, or correct and style an AI transcript |
| **Output** | Set shape, resolution, FPS and quality; advanced AI settings are separate |
| **Project overview** | Return to the summary and AI refinement choices |

On larger screens, drag the preview/timeline divider to resize either area; double-click to reset. **Full screen** enlarges the video, not the control panel; **Escape** returns. **How to edit** provides the short in-app workflow. **Help & guide** has searchable explanations: try “models”, “layout”, “captions” or “export”. Optional panels can stay collapsed.

### The three everyday timeline tools

**Select / Move:** click a cut, then drag it to a new place. Clips shift to make room rather than overwriting the destination. Drag a white edge to trim, or reveal more original footage up to the source/neighbor boundary. To move part of a cut, mark it with Range, switch to Select / Move and drag inside the selection.

**Range:** drag over an interval, then **Remove from video**. It can start or end inside a clip; selection is not limited to AI cut points. **Range…** accepts exact times as seconds or `mm:ss.mmm`.

**Cut:** click once to split. This alone removes nothing. **Cut out**, in More editing tools, removes the interval between two clicks; Escape cancels the pending first cut.

Click the ruler to move the playhead. **+ / −** zoom around it; **Fit** shows the full edit. **Zoom to selection** focuses a marked range. Undo/Redo reverse manual edits without changing original media.

**Snap** is beside Undo/Redo in the timeline toolbar. Switch it on to align a trim, range or moved clip to the playhead, A/B cuts or added media/audio edges. A cyan guide names the alignment target. **Alt** temporarily bypasses snapping; **Esc** cancels a drag without saving. Snap starts off, and never makes ruler seeking jump to a cut. Reordering source clips aligns the leading edge and closes the old position; added media can align either edge without reordering the base footage. Source limits still apply: snapping cannot reveal frames that do not exist. The timeline hover readout uses **hours:minutes:seconds:frames** at the output frame rate; a trim shows its actual allowed edge, not an unreachable pointer position.

### Listen to a cut on repeat

In **Edited video**, mark a range of at least 0.25 seconds, then choose **Loop range** above the timeline. To hear a cut in context, put the start just before it and the end just after it. Playback includes the edited picture, titles and mixed sound, even in the Audio workspace. Click **Loop range** again or press Pause to stop where you are. Ordinary Play then continues normally. This is a preview, not an export range: it does not duplicate footage or change your project. A slow decoder can pause briefly at the loop boundary so picture and sound restart together. Browser seeks are not sample-accurate audio loops.

### Together or one source?

| Edit target | What changes | Gaps |
| --- | --- | --- |
| **Together (A+B)** | Sources and layout; timeline Cut out also includes imported media/text | Timeline removal closes time across supported layers; moving inserts the paired source cut |
| **A only / B only** | Only that track; the other stays still | Removal can leave an intentional gap; movement shifts only that track |

Together helps preserve synchronization. Choose A/B only for deliberately independent timing. **Close gaps** removes empty time in the chosen scope. Together closes only where A/B, added media/audio and custom text are all empty, moving later layers together in one Undo step. A spanning music bed or title keeps its occupied time. A/B-only leaves added layers in place. When one source is missing, the other fills the frame; when both are missing, it is black. Audio follows the selected audio source and is silent in its gaps.

### Protect a finished source

Open **Edit → Track protection**, then choose **Lock A** or **Lock B**. The control appears after a draft exists. A lock protects that source's cuts, moves, trims, clip framing, picture speed and source timing. It does not mute or hide the footage: preview, audio and export continue normally. Choose **A only / B only** for the other, unlocked source to keep editing it.

Protection is saved with the project and survives reopening. Lock/unlock choices sit outside Undo/Redo and preserve the existing history. A Together edit or an Undo/Redo step that would change a locked lane is rejected without changing the edit or consuming that history step. Unlock the affected source and retry; Undo does not switch a lock off for you.

Unlock all protected sources before rebuilding/refining the draft or replacing/removing source footage, because those operations can reset the shared draft. **Reset to AI draft** also requires unlocking any protected lane it would change. Shared layout, the audio mixer and added media remain editable; per-clip framing on a protected source remains locked. Changing B's sync offset requires B to be unlocked.

These controls protect the existing A/B lanes. Imported-video Insert, timeline Together Cut out and Together Close gaps explicitly include supported added layers. Other source-lane commands do not automatically ripple added media. Arbitrary user-created source tracks are not part of this increment.

### Restore removed footage

Open **Original footage** to see the full recording and its kept/removed regions. Choose A or B, preview a section or drag a range, then **Restore to edit**. **Previous removed / Next removed** help find omissions. Missing material returns near its source neighbors without reordering existing cuts. **Remove from edit** affects uses of that source interval, including copies; check the scope first.

**Insert a copy by time…** deliberately duplicates source footage at an exact edit position. **Duplicate clip** copies the selected cut. **Reset to AI draft** resets manual sequence changes after confirmation; ordinary Undo is safer for one recent change. [Detailed editing behavior](INDEPENDENT_TRACKS.md)

### Familiar keyboard controls

Open **More editing tools → Keys / Shortcuts** and choose a preset. The list shows the commands supported by CUTROOM. Space plays/pauses. Shortcuts stay inactive while typing in caption or form fields. [Full shortcut reference](KEYBOARD_PROFILES.md)

### Add media and mix sound

In **Media**, choose **Add media** to import video, an image or audio into this project's library. Wait for preparation, place the playhead and select **+ Overlay**. **Append video** adds footage and sound at the end of the edit instead. Drag the new clip or its edges in the waveform/timeline lanes; use its inspector for exact start/end, source in, volume and fades. Images can stay still, slowly zoom or pan.

**Source monitor:** the media pool's **In / Out**, or **Open source at playhead**, opens real source controls inside Media without covering the timeline. Seek the edited timeline to choose the displayed Insert destination. After Insert/Append, the same source and marks stay open and the destination advances to the new shot's end, so you can assemble more ranges without reopening. Each placement is one Undo. Source and edited playback pause each other; original source sound is not the edited mix. An unrelated edit requires **Use current edit** before another placement. Selecting a timeline occurrence, leaving Media/Studio or **Close source** returns to the regular editor. Pending drafts/saves and stale-source conflicts are guarded, not silently retried. **Save source marks** remembers one selection for that import in this browser; **Clear saved marks** returns to the full source without changing timeline clips. These marks are not stored in the project or its backup. See [source review and saved marks](SOURCE_MARKS.md).

New video overlays include detected source sound by default. Select a clip to check **Include source sound**, **Mute this clip**, volume and **Audio group**; these choices affect preview and export. Existing silent overlays keep their saved choice: enable source sound to hear them, and check clip/group mute. Videos without an audio stream say so. Picture speed changes only the image; source sound stays at normal speed from **Source in**.

The timeline waveform shows measured audio from the selected original A/B source, including manual edits without AI. Imported audio has its own waveform. A silent section, missing audio and a pending/unavailable measurement are different states.

Open **Audio mixer** to balance Original, Voiceover, Music, Effects and Master. Original is the selected A/B audio source; the other channels group media by audio role. Mute and volume affect preview and export; Solo auditions a channel in preview only. Live meters show browser sample peaks and reset on pause/seek. Leave headroom; export normalization can change final loudness. Media layers fit inside the existing edit duration; adding a file does not extend the whole edit or create more main A/B sources.

Faders move in 0.5 dB steps and show a 0 dB mark. Type an exact value in the box under a fader (−60 to +12 dB). Double-click a fader, or use its reset button where the panel shows one, to return to 0 dB. The mouse wheel changes a value only while that control is focused. When the draft normalizes loudness, channel faders set the balance between tracks before normalization and **Master** sets the final level after it; the panel says when a fader cannot change the exported level, for example when only one track is playing. The preview applies the same normalization, so what you hear is close to the export. Every export ends with a limiter that keeps true peaks at or below −1 dBTP, so loud sources no longer clip.

**Stabilize footage** makes an optional local copy without replacing your original or edit. Support depends on your FFmpeg build, and smoothing may crop edges. [Steps and limits](STABILIZATION.md).

For a selected main A/B clip, **Picture speed** changes only the picture, from 0.25× to 4×. Clip length and speech timing stay in place. It can lose lip sync, and reaching the end of the source can hold the last frame. Check the result before export; this control does not speed up the entire picture-and-sound edit.

## 7. Arrange and frame the video

Select **where** a layout applies: a timeline range, exact From/To times or **Entire edit**. Then choose **Screen only**, **Camera only**, **Stacked**, **Side by side** or **Picture in picture**. The choice saves immediately. **AI choice** returns that scope to the proposed composition.

New two-source Reels default to **Stacked**: camera top 30%, screen bottom 70%, filling both panels without stretching. Saved manual choices stay intact. To restore this composition in an existing project, open **Advanced → Restore 30/70 stack**; it resets order and fit for the whole edit. **First in layout**, stack fit and **Swap top / bottom** remain under **Advanced**.

Use the one source workflow in **Layout**: **Sources & narration** chooses screen/camera roles, main content and audio; **Timing & coverage** reviews alignment or opens independent footage placement; **Layout & preview** changes the current composition and range. Layout does not synchronize recordings. For independent camera/narration, review source B and use **Insert a copy by time…** to choose its source In/Out and edit position. When B has no mapped picture but A covers that interval, Export automatically uses A there and reports the substitution in the export dialog and finished-video checks. The requested B/split layout is absent only in those intervals. The saved edit, duration, captions and selected audio do not change; missing B sound is not replaced. If no safe A picture covers the gap, supply footage, explicitly shorten the edit or choose a different layout. Missing media files and other export failures still need attention. **Next AI draft preference** is a separate rebuild preference, not a control for the current edit.

**Fill frame** crops edges to fill the panel. **Fit entire source** keeps the full picture with bars when needed; it does not squeeze the image. In **Clip framing**, choose A/B and adjust horizontal focus, vertical focus and zoom. Check the scope label: changes affect the selected clip/range, or the clip at the playhead—not automatically every cut. Crops follow clips when moved/copied. Full source browsing does not enable per-cut framing edits.

For an embedded camera, open **Camera area in this recording** and drag its rectangle; the picker starts folded once configured. Open **Precise camera position** only when you need numeric controls. **Main screen focus** sets the default screen position; a clip's own framing takes priority. **More layouts** contains side-by-side, picture-in-picture and the style default. A fixed rectangle does not track a moving camera. **Original source preview** and **Source order preview** are optional reference monitors; **Layout by section** lists composition blocks. If saving fails, the camera picker opens and offers **Retry save**; do not close the editor until it shows **Saved**.

Open **Edit > Effects · Green screen**. Choose the foreground video, its key color or green-screen defaults, then the background. Fine-tune edges is optional. For a moving background, keep it as main footage and add the foreground through **Media > Add media**, place it on the timeline and select **Video underneath**. **Use green-screen defaults** starts at 12% tolerance; 100% can erase the whole foreground. **Apply & preview** saves the settings, updates edited playback and generates an exact processed frame. Original footage mode stays unkeyed. A/B and Media also support color/image backgrounds. Each video has independent settings with Undo/Redo and Reset. Browser edges can differ from the exact FFmpeg frame/export. [Steps and limits](CHROMA_KEY.md)

## 8. Add text and control captions

### Your own titles and subtitles

Open **Captions → Your text & captions** after creating a draft or opening the manual editor. Place the playhead, then choose **Add text** for a title or **Add caption** for a subtitle. Select the new item and type. Changes preview immediately and save automatically after a short pause in typing; wait for **Saved** before leaving. A failed save keeps your pending text and offers **Retry save** or **Discard unsaved text changes**.

Each item appears on its own timeline layer. Drag the item to move it or drag its edges to change its duration; **Start / End (seconds)** provide exact placement. **Preview at start** seeks to it. Choose **Top**, **Center** or **Bottom**, **Clean**, **Bold** or **Boxed**, and a size from 75% to 150%. Use **Find custom text** to search, **Remove text** to delete an item, and Undo/Redo to reverse saved text edits.

**Template** gives a text item a ready layout: **Plain text** (the default), **Lower third (name + role)** with a **Second line** under the name, bottom left on a box, **Chapter card** (a centred title with an optional label above it, faded in and out), **Callout** (a short boxed note at the top left) and **Highlight** (text in the accent colour). Templates with a fixed place hide **Position**. The preview and the export draw them in the same place. Every word comes from you: CUTROOM does not fill names, numbers or facts into templates.

These times refer to the **edited video**, not the original recording. Custom text stays at its edit time when you reorder source footage; it follows the explicit imported-video Insert, timeline Together Cut out and Together Close gaps operations above, not other A/B reordering commands. Text must fit inside the current edit. For other shortening commands, if the video would leave text past its new end, CUTROOM rejects that edit: first trim, move or remove the affected text.

### Import SRT or VTT

Choose **Import SRT / VTT** and select a UTF-8 `.srt` or `.vtt` file, no larger than **1 MiB (1,048,576 bytes)** and containing at most **2,000 cues**. Its times must already match the edited video and fit its duration. Import keeps text and timing; file-specific fonts, markup and VTT positioning are replaced by CUTROOM's editable style presets.

Imports add to your custom captions by default. Select **Replace my existing custom captions when importing** to replace those captions only; titles and the AI transcript stay in place. Invalid imports leave the existing text unchanged, and Undo reverses a successful import in one step. A project can contain up to 2,000 custom text items, with at most 16 simultaneous items and 1,000 characters per item. Items sharing a position can overlap, so review the picture.

Enabled custom titles and captions are burned into the exported video. The AI **Burn into video** switch does not hide them. Optional **Export SRT file** combines timed AI and enabled custom captions, excluding titles. To avoid duplicate subtitles, turn off AI burning when you use custom captions instead; importing does not remove the AI transcript or its captions from an enabled SRT export. These text tools require no AI processing or paid account.

### Edit automatic captions on the timeline

Automatic captions appear as blocks in the **Captions** lane. Click a block to select it; the playhead does not move. The preview outlines that caption and **Captions** opens **Selected caption**. You can also click the caption on the video. Drag a block to move it, or drag its edges to trim it (in whole frames, at least 0.1 s). Double-click or press Enter to edit its text; Delete or Backspace hides it; Esc deselects. Blade and range tools do not cut captions.

In **Selected caption**, choose where a text change applies:

- **What was said** fixes the transcript wherever this speech is used, including the transcript list and what the AI reads for the next draft. The original transcription is kept, so the fix survives a rebuild.
- **Only this caption** changes this one caption; the transcript stays as transcribed.

**Start / End (s)**, **Style**, **Position** and **Size (%)** apply to this caption only; leave them empty to follow the project setting. **Hide caption** leaves it out of the preview and export without removing footage; a hidden caption stays on the lane as a dashed **Hidden** block. **Reset caption** returns it to the automatic version. **Previous / Next** step through captions. Enter saves, Shift+Enter adds a line and Esc reverts. Each change is one Undo step, and edited captions show ✎.

A caption longer than about 84 characters (two lines) is split into several captions. When the speech has no word timing, the time of each part is estimated from its length.

Caption-specific text and style changes follow the original clip and its surviving source speech when clips are reordered or trimmed. A caption ID can change after trimming without losing its saved change. If all of that speech is removed, its change remains dormant; restoring that speech in the same clip can restore the change. Replacing the source or transcript does not transfer earlier caption-specific changes to unrelated speech.

### Correct an AI transcript

Search the transcript or filter **All lines / In the edit / Removed**. Click a line to seek; Shift-click selects a passage. **Remove passage / Restore passage** changes footage. Correcting text alone neither removes footage nor generates replacement speech.

Edit **Correct selected line**, then **Save text**. **Save all changes** saves pending line edits; **Discard changes** drops the current unsaved correction. Check Saved/Unsaved before closing the browser—unsaved text buffers are not a backup. A saved line correction is the same fix as **What was said**: the original transcription is kept, and the correction reaches every caption that uses that speech.

Under **AI subtitle style & speech language**:

- **Burn into video:** permanently render AI captions into the exported picture; custom text remains visible independently.
- **Export SRT file:** create a separate editable subtitle file containing AI and custom captions, without titles.
- **Style / Position / Size:** control appearance; check faces, graphics and platform overlays yourself. **Word highlight**, the default for new Shorts, shows up to four words at a time and colours the word being spoken; in vertical video its Auto position sits at about two thirds of the height, above the Shorts/Reels buttons and most game subtitles. Hebrew and Arabic lines show the same short phrases without the per-word colour.
- **Words per caption:** shorter or longer caption chunks, not different transcription.
- **Speech language:** affects AI transcription and can require rebuilding; it is not a translation target.

AI captions follow edited timing and the selected audio source. Manual projects start without transcript text; enabling subtitles does not itself transcribe them. You can still type or import your own captions above.

For mixed Hebrew/English, choose the main spoken language and review names and English terms. Local Balanced/Quality can recheck up to two weak units of at most 30 seconds each, within a 48-second audio budget per local pass, using the loaded model. Lite adds no such retry. Timing, confidence and spelling checks can keep the original instead. This does not translate or use Story AI to rewrite speech. Low-confidence warnings mean “listen and review,” not a measured accuracy score; automatic detection can still be wrong. [Recovery details and limits](QUALITY_AND_LIMITS.md)

### Leave frame-accurate review markers

In **Edited video**, pause at the frame you want to remember. Choose **Markers** above the timeline, or press **M** with the CUTROOM, Resolve, Premiere or Final Cut keyboard profile. Name the marker, optionally add a note and color, and choose **Add marker**. A colored flag appears on the timeline ruler. Click the flag in Select/Move, use the arrows beside **Markers**, or choose a saved entry in the panel to jump to its frame. Buttons and typed fields keep their normal keyboard behavior.

Use **Edit** beside a marker to change its details. To move one, place the playhead at its new frame, open the marker, and choose **Move to playhead**. Removing a note requires **Confirm removal**. Notes are saved with this project and copied independently by **Save a copy**. They do not change clips or their Undo history and never appear in video or subtitles. Markers stay at their absolute timeline time, not attached to footage: shortening the edit keeps outside markers for explicit retiming or deletion. Changing output FPS preserves the saved time and navigates to its nearest available frame on the new grid.

## 9. Export and understand rebuilds

### Export a marked range without cutting your project

In **Edited video**, mark the part to deliver on the timeline (drag a range or enter its In/Out). Open **Export** and change **Export range** from **Entire timeline** to **Marked range**. Check the two timecodes and frame count before **Start export**. Times snap to the nearest output frame; In is included, Out is not. A range can be as short as one output frame. If the edit, marks or FPS changed, reopen Export and review the selection rather than exporting stale frames.

The new MP4 contains the finished picture, visible titles, burned captions and final mix for that interval; it does not trim your project or original media. If enabled, SRT cues crossing a boundary are shortened and retimed from zero. Use **Download range subtitles (.srt)** beside the finished video to save that sidecar. The file name includes the frame interval. **Entire timeline** remains the default every time. An excerpt may still need to process earlier material, and loudness normalization keeps the complete mix as its reference.

Use **16:9 Landscape** or **9:16 Vertical** at the top of the editor for a one-click format change, including manual projects. The preview updates and the format saves automatically for export. No AI or rebuild is needed; your cuts stay intact. Use **Layout → Clip framing** if the subject needs repositioning in the new shape.

Set **Aspect ratio** (9:16, 16:9, 1:1, 4:5 or Source), **Resolution** (720p, 1080p, QHD 1440p or 4K 2160p), **Frame rate** (24/25/30/50/60 FPS) and **Export quality**. Higher settings can increase render time, memory use and size. Higher resolution does not recover missing source detail. 60 FPS preserves high-rate footage when available; lower-rate input repeats frames, not AI-generated motion.

Controls marked **Draft rebuild** change editorial decisions and require **Rebuild Draft**. This is a new draft operation, not a preview refresh: save transcript corrections first and review afterward. Format and subtitle styling do not require rebuilding the story. **Performance mode** controls AI choices, not MP4 encoding quality. **Smart editorial effects** adds bounded emphasis; **Final loudness balance** adjusts exported sound levels.

Choose **Export**, check the summary, then **Start export**. Rendering uses original media rather than preview proxies. **Stop process** cancels export; closing the dialog alone does not. When ready, **Download video** and save the file. Before sharing, watch the start/end, cuts, captions, sync and frame shape outside the app.

After each export CUTROOM runs a quick local check and shows it in the export dialog under **Checks of this video**: true peak (passes at −1 dBTP or lower), loudness against the normalization target, black picture lasting a second or longer, your text over burned captions, and very long caption lines. Warnings name the times. A check that runs out of time is skipped. The checks never block or change the export, and they do not replace watching it.

## 10. Save, recover and report a problem

Projects live on the computer running CUTROOM, not in a cloud account. Default folders are `data/projects` for projects/imported media, `data/exports` for exports and `data/cache` for caches. Keep backups. Do not delete these folders as a generic fix. Use the confirmed **Delete** action in the lobby or Projects when you intend to remove a project and its imported copies/exports; original files outside CUTROOM remain untouched.

The project-header status combines settings saves, media/text autosaves, captions/transcript and unapplied Chroma Key changes. **Saving…** means a save is queued or in progress; **Unsaved changes** means a local change still needs attention; **Save failed** identifies a failed save. Click an actionable status to reach the existing editor or retry a failed settings save. A saved AI preference awaiting a new draft is not an unsaved project change.

Chroma Key changes remain unapplied until **Apply & preview**. They now survive unrelated project saves, including changes on another video. **Discard changes** removes only the selected video's unapplied candidate, with no project write; **Reset this source** is still a different, undoable change to saved settings. If that foreground, replacement image or saved key changed meanwhile, CUTROOM retains the candidate visibly but blocks applying it to the changed source. Discard it and review the current saved settings instead.

Home, New project, opening another project and starting a new Export stay in the current editor while Chroma or caption edits need an explicit decision. Apply/Save or discard them, then navigate again. Existing media/text/settings autosaves still finish before leaving, and failed saves prevent navigation. Failed media autosaves restore the saved values in the viewer and inspector, including a still-focused field; text drafts remain available for Retry or Discard. Browser-close/reload protection includes unapplied drafts and in-flight saves, but these local drafts are **not crash recovery or a disk backup**: ignoring the browser warning, a browser crash or closing the launcher can still lose unapplied work.

Closing the browser does not stop the application. Save text, wait for the save indicator, and finish or cancel jobs before closing the launcher. Model caches can live outside the app folder. [Setup logs and recovery](TEST_ON_ANOTHER_PC.md)

| Problem | Check first |
| --- | --- |
| Model missing | Local readiness and the named download; Manual edit is still an option |
| Cloud quota/key error | Provider account and quota; no automatic paid fallback |
| Bad transcript | Audio source, speech language, source sound; then model choice/manual correction |
| Wrong layout | Source roles, selected scope, output aspect, Fill versus Fit |
| A/B drift or black areas | Sync, source durations and independent-track gaps |
| Track locked / Undo refused | Open Edit → Track protection; unlock the affected lane, or choose the other source for an independent edit |
| Rebuild required | Save text and rebuild after editorial-setting changes |
| Text prevents shortening the edit | Timeline Together Cut out supports mixed layers. For other source-only shortening commands, trim, move or remove text past the new end first |

Report the exact action/error, build name, input length/language and a redacted screenshot with the [feedback form](BETA_FEEDBACK.md). Never include API keys or the entire private `data` folder. The beta is not certified across all PCs, languages or footage; [limitations](BETA_STATUS.md) distinguish automated checks from real-world validation.


### Edit length
Choose **Highlight sequence — aim for this length** to combine distinct relevant passages toward the duration. **Follow style — maximum length** keeps the style’s moment limit: Competitive Clutch keeps one engagement. A target is approximate, never permission to repeat footage or add irrelevant filler. Review shortfall notices and source ranges; audio-only selection identifies activity, not the meaning of a fight. Older projects retain their prior style limit until you change this choice.

In **Highlight sequence — aim for this length**, after the passages the story planner chose, CUTROOM adds the strongest remaining relevant beats with their context. It never repeats a passage, never adds a beat below the median relevance and never passes the target; it stops at about 95% of it. When a draft is still shorter than requested, its notice shows **Length at each step**, from the requested length to the final one, so you can see where time was lost.

### Completed exports and pending AI preferences

Completed MP4 exports and their optional SRT files are kept in CUTROOM storage; making another export no longer removes older deliveries or their history after 20 exports. They remain until you explicitly delete the project or manage its files. Exported copies already removed by an older version are not restored by this change.

Changing only the next AI brief, pace, spoken language, AI quality/vision or target length does not stop you exporting the current edit. The export dialog identifies these preferences as not yet applied. Rebuild only when you want a new AI draft. Goal/style, layout/framing, audio-cleanup and unknown pending changes still require a rebuild because those controls have not yet been separated safely from output settings.


### AI requests without leaving the editor

Open **AI Director** beside the Inspector to use the real Director instruction, length intent and rough-cut fallback controls. These are the same controls as Setup, not a second copy. The brief and length preferences autosave; they do not by themselves run AI or replace your edit. Goal/style and output controls remain in their established settings. Manual projects can use AI too, once source A is available.

**Review AI request** opens the existing deterministic request check. **Keep current edit** or Escape closes it without generation. Only **Generate reviewed request** proceeds to the configured provider and existing progress/Stop flow. The check is not model inference or quality approval; a local model may need preparation and cloud providers may charge according to your configuration. Pending explicit Chroma/caption changes must be resolved first.

An editor request on an existing draft saves a separate candidate; a newer result replaces the earlier unapplied candidate, not the current edit. Its generation does not replace the live draft, analysis, timeline, saved output controls, mixer, crop or name. The paused editor remains available while processing; editing/export are guarded during the job. The saved candidate can be inspected later through **Review AI draft**. Apply adopts the reviewed source-cut draft and analysis in one undoable transaction, while current output settings, mixer, crop, name and imported media/text remain in use. Incompatible routing/caption edits or layers outside the proposed duration block Apply instead of being silently changed. Source audition is not a composited or mixed preview.

The first draft still uses the normal generation workflow. The legacy Setup rebuild of a draft without an independent manual sequence retains its existing direct-rebuild behavior; use the editor AI pane for protected proposals. No actual model quality is implied by these workflow checks.


### Independent settings saves

Changing an output, caption, AI preference or individual audio-cleanup control saves only that setting, in Setup and in the editor. For example, changing export FPS no longer rewrites a hidden automatic silence threshold, custom loudness target or fractional cleanup values. Changing resolution, quality, FPS or caption output also leaves the selected source clip's crop and playhead alone. Caption size accepts every integer percentage from 75% to 150%, including a saved 103%.

Choosing an audio preset still applies its defined audio bundle. Choosing a goal or editing style still applies its documented related defaults; these are deliberate multi-setting choices. Threshold and target loudness remain unchanged unless the chosen style explicitly supplies them. Current rebuild-required and explicit-draft protections still apply.

AI request review also reads the accepted saved settings, including fractional lengths such as 8.125 seconds, without rounding them to the displayed audio controls. Export first finishes accepted saves, then uses saved project preferences rather than overriding them with an older hidden form value. A failed save remains visible and retryable; another window's unrelated saved settings are preserved during a revision retry.


### Arrange or remove a temporary selection

In Select/Move, Ctrl-click (Cmd-click on Mac) imported video, audio, images or custom text to add/remove them from a temporary selection. Timeline Index checkboxes provide the same selection without a pointer modifier. Source A/B footage and automatic speech captions are separate, not included. Disabled occurrences can be selected and moved.

Drag the body of an already selected clip to move all selected clips by one time shift. The Media inspector shows the selected count, **Move selection to playhead**, one-frame earlier/later controls and **Clear selection**. These move whole occurrences, not their source in-points. Their relative timing, audio/picture clocks, fades, motion, text style, stacking order and overall edit duration stay fixed. All selected clips must fit inside the existing edit; text overlap limits still apply. One Undo restores the entire move.

This selection is temporary, not a saved group or linked track. It is cleared when another project is opened. Select one clip before Split, Trim, Slip, Duplicate or editing its individual fields. Escape cancels a live drag without saving. A stale or conflicting move is refused rather than replayed against changed footage.

**Remove selected clips** in the Media inspector, the counted timeline Remove button, or the configured Delete shortcut removes the whole selected occurrences in one operation. This is not a range cut or ripple: other clips, source A/B footage, automatic captions and edit duration stay unchanged. The media-pool assets and original files remain available. One Undo restores every removed clip; Redo and reopen keep the accepted result. Undo restores content, not the temporary selection.

Unavailable and disabled imported occurrences can still be selected for cleanup. Resolve unapplied caption/Chroma drafts and finish or cancel an active gesture first. A changed selection or stale save is refused, never retried against different content. Removing the last independent layers leaves the saved empty edit and its duration; Undo, original-footage recovery or adding existing pool media can rebuild it. Playback/export become available again when the timeline contains a source or layer.


### Review original A/B footage beside the edit

Open an original A/B card in Media, or the existing original-footage recovery action, to review it in the Media inspector without covering the edited viewer and timeline. This is the actual original recording, not a new imported-layer asset. Select a kept/removed source section or drag a source-time range; switch A/B with **View**. Source playback uses original picture and sound at 1×, without the edited effects/mix. Playing either source or edit pauses the other.

**Restore to edit**, **Remove from edit** and **Undo** keep their existing A/B semantics. Check the visible **Together (A+B)** or **This source only** effect before acting. Coverage shows normal source-edit clocks, not exact usage of retimed picture frames. It is not the imported-media Insert/ripple operation; unsupported arrangements still refuse rather than silently altering layers. **Place selected footage...** opens the existing exact Timeline placement form with the actual source, scope and endpoints. Review Insert/Overwrite, destination and their stated effect there before committing.

The source card keeps its player, selected range and zoom after a confirmed local recovery action. An unrelated saved revision requires **Use current edit** before another action; stale actions are refused, not automatically replayed. Explicit unsaved caption/Chroma drafts must be resolved first. **Source navigation & help** holds Previous/Next removed, zoom and transcript context. Done or an unconsumed Escape closes the card without changing the paused edit and returns focus to its opener when appropriate. Choosing another inspector/pane or project releases it. Original files are never changed.


### Make more room for the timeline

On desktop, **Expand timeline** beside Timeline Index temporarily gives the timeline more of the workspace while keeping a usable program viewer and its transport. **Restore layout** returns to your previous proportions. This changes the view only: it does not create tracks, move clips, restart media or save project edits. The existing vertical scrolling still handles arrangements taller than the available screen.

Without a saved height preference, the balanced layout now leaves more room for mixed media and text. Your existing chosen timeline height remains respected within the current window bounds. Drag the video/timeline divider or use its arrow/Home/End keys to choose a normal height; double-click resets to the balanced default. Resizing explicitly while expanded makes that deliberate size your new normal preference. Escape cancels an owned divider drag. Expanding itself never overwrites your saved normal size, and leaving the editor or entering a compact stacked layout exits the temporary expansion.

Finish or cancel an active clip/source/frame/numeric drag, or wait for its edit to finish, before explicitly changing workspace geometry. Ordinary unsaved drafts or an AI/export job alone do not prevent changing the view. This does not introduce a persistent track model or change existing A/B versus imported-layer editing semantics.


### Saved tracks and vertical clip placement

Open **Tracks** in the Media inspector and choose **Enable editable tracks**. Conversion is explicit and undoable: merely opening an older project does not change it. Existing imported video/images, audio and custom text receive compatible saved tracks while retaining their timing, content and overlapping picture/text priority. New projects also use the existing layout until you choose Enable. One Undo immediately after conversion returns to the legacy layout.

These are real persistent tracks. Add a visual, audio or text track, rename it, or move it forward/back within its kind. Empty tracks stay visible and may be removed; occupied tracks must be emptied first. Track order controls overlap priority for imported pictures or custom text. It does not change audio roles, mix, source in-points or timing. Imported visuals remain above the original A/B composition; custom text is a separate layer. A/B source lanes and automatic captions are not converted. Changing source B retains saved layer tracks. Replacing or removing source A keeps its existing full-timeline reset policy, including the dependent layer tracks. Track names are not mute, solo, lock or effects controls.

In Select/Move, drag one imported clip or custom-text occurrence to another compatible track. The ghost shows the actual target. Horizontal and vertical placement save together with one Undo. An occupied interval, incompatible track, fixed source lane or stale revision rejects the whole drop, not just its vertical part. Disabled clips still occupy their intervals. Use the selected clip's **Tracks** assignment for keyboard or precise same-time placement. Selecting a track header opens its management controls.

Pool and Source placement can use Automatic or an explicit compatible track, as described below. Duplicate still chooses a compatible destination automatically. Existing time-placement meanings are unchanged; accepted occurrences can also be moved vertically afterward. Splits keep their existing track. Temporary multi-selection moves time only, not tracks. Trims, numeric timing edits, group moves and insertion must also satisfy saved-track collision rules; unsupported collisions are refused rather than silently moving other clips.

Saved names, memberships, empty tracks and ordering survive Undo/Redo and reopen. A project with an unknown track version or invalid membership is shown with a compatibility error, not silently rendered or rewritten as a legacy project. Use a compatible editor and an intact project copy. An older CUTROOM installation is not certified to understand this model, so do not edit a converted project with an older build. This is a bounded independent-layer track model, not full DaVinci Resolve parity.


### Choose the track while assembling footage

In a project with editable tracks, use **Destination track** in Media or the imported Source monitor before Add, Insert or Append. **Automatic** chooses a compatible track; a named choice means exactly that track. Source In/Out marks and the player stay open for the next shot. Video can extend the edit; audio/images Add only inside its existing length. Insert opens time across supported tracks, while Add overlays without moving other clips.

You can also drag an imported file directly onto a compatible saved visual/audio row. The preview names that row. Occupied or wrong-kind rows refuse rather than placing elsewhere. Hold Shift for video Insert, or drop video at the tail to Append on that row. Ruler, empty space and A/B/title rows are not imported-media destinations. Use Automatic in the chooser if there is no suitable named track yet. Legacy projects retain their original pool-drag behavior until editable tracks are enabled.

The chooser is temporary interface state, not a saved edit. Missing selected tracks remain blocked until you choose another destination or Automatic. Every accepted placement is one Undo; originals are kept. Source A/B recovery, custom-text creation and group vertical placement are not changed.

## Resume a retained timeline after a source reset

If a source change has cleared the current draft but left a supported saved timeline, CUTROOM now offers **Resume retained edit** instead of treating it as an empty project or opening the full recording. The Projects list identifies the retained timeline. Open it to see its validated duration and retained layer counts, or the specific reason it cannot be resumed. This also works for projects originally using AI.

Until you explicitly resume, Edited playback, editing, imports, generation and Export are unavailable. **Full source** remains available for inspecting the original recording; it is not the saved edit. Resume preserves the post-reset sequence, A mapping, imported media, custom text, named tracks, effects, mix settings and remaining history. It does not put B clips back, recover deleted analysis/automatic captions/old AI decisions, or undo the earlier reset. No AI runs.

Resume activates the retained edit without adding a new Undo step. Subsequent edits are undoable normally. Unsupported legacy timelines, incompatible track data or missing required originals are not silently rebuilt or shortened: the saved data stays intact and the recovery notice explains the blocker. A concurrent change requires a fresh explicit attempt rather than replaying Resume automatically.


### Insert original footage and move later layers together

In **Place source footage**, choose **Insert (ripple all layers)** when you want an original A/B shot to open time across your whole arrangement. Choose **Together (A+B)** first. The existing default **Insert (sources only)** still moves only source footage/framing; **Overwrite (keep timing)** is unchanged. Nothing changes merely by choosing a policy.

Review Source In/Out and the edit destination. The all-layer choice inserts the selected original source, leaves the other source empty during that interval, and moves supported imported video, audio, images and custom text together with the source timeline. Crossing clips split without losing their supported content clocks; saved tracks and disabled states remain. One Undo reverses the whole operation. If you use a selected edit range, its start and length define the insertion; the old content is not replaced. The destination must be inside the edit or exactly at its end.

**Picture choice does not switch sound.** Global A/B audio routing and mix stay unchanged. Inserting B while sound is routed to A can leave the inserted interval silent. Review the form's routing note and your source audio controls. Originals are never changed.

Both source lanes must be unlocked. The action refuses crossing motion/fades or very short pieces it cannot preserve, unresolved manual/alternative caption ownership, timed audio plans for middle insertion, and capacity or track conflicts. Choose a safe boundary or resolve the stated blocker rather than expecting the editor to discard content. Stale saves are not automatically replayed. This is explicit whole-arrangement insertion, not a change to Restore/Remove, source-only insertion or per-clip audio policy.


### Protect finished tracks while continuing to edit

Use the **Lock** control beside a saved track name, or its checkbox in **Tracks**, to protect finished picture, music or titles. The clips remain selectable and playable. You can still review their originals, rename the track, export, or duplicate a clip into an unlocked compatible track.

A lock prevents changing, splitting, slipping, moving or removing its saved clips, assigning more clips into that track, removing the track, and reordering other tracks across it. Disabled clips are protected too. A group edit or all-layer ripple that would affect protected content refuses as a whole; it never skips the locked clips and partially shifts your arrangement. Automatic placement chooses an unlocked track. Shared asset effects and regeneration of a protected stabilized original are also blocked.

**Lock state is not an Undo step.** Undo and Redo keep your current protection and refuse if the older edit would change it. Unlock first when you deliberately want that edit reversed. The original A/B lanes still have their own locks. Track locks do not freeze the final picture or global mix/output settings, and they do not make source files immutable.

The first Lock updates the saved track format. Older CUTROOM versions that do not understand protection will refuse that project rather than silently edit through its locks. Unlocking keeps the supported newer format. Keep your normal project backups.

If another edit locks a track while you have unsaved text or an unapplied effect, **Unlock** can recover that track without forcing the draft to save or disappear. Wait for any real save to finish, then unlock and explicitly retry or discard your retained changes.


### Check subtitles against the saved export plan

In Edited view, every active automatic subtitle is now shown in the saved export order, not only the selected line. Selecting a subtitle changes its editing outline, not which overlapping text appears. Font size and placement use the saved output frame; custom text stays above automatic subtitles, matching the existing export layer order.

Chapter text fades follow the edit playhead, including paused seeks and the end of the cue. Seeking back gives the same fade phase rather than restarting an animation. Very short chapter cues retain the export renderer's existing overlapping-fade behavior; their appearance is not redesigned.

The note under **Subtitle output** identifies the saved preview and pending settings. While styling/output changes save, the viewer keeps the last accepted subtitle plan. Unsaved subtitle text is not included. Full source remains an original-recording inspection, separate from this edited preview. An unavailable or incompatible plan is reported instead of silently displaying another project or a guessed caption. At fractional cut boundaries, export-aligned words can differ from the editor line: a uniquely related cue opens that existing line, while a cue without a unique editing target stays visible and read-only with an explanation.

This is not pixel-identical subtitle rendering. Browser font shaping, wrapping and the collision placement of overlapping automatic lines remain approximate. Positioned captions keep their fixed anchors and may overlap. Check a real exported video for final typography and dense text before sharing; no new transcript, AI inference or output rewrite is involved in this preview improvement.

### Reuse a selected arrangement

Select two or more imported video, image, audio or custom-text clips with Ctrl/Cmd-click or the Timeline Index checkboxes. Move the edit playhead, then activate the existing **Duplicate at playhead** button or the same action in the selected-clips panel. The earliest selected clip starts at that output-frame-aligned position; all copies keep their relative timing, source points, speeds, effects, fades, text and enabled state. No clip is shortened and the edit does not ripple or grow.

Named-track projects choose compatible unlocked tracks automatically, adding a track only when necessary. Copied visual/text layers retain their internal stacking order and appear above existing overlapping content. Locked originals can be read and copied without unlocking them. Legacy projects stay legacy. The new occurrences become the selection after the current save succeeds; originals, source files and global mix/settings stay unchanged. One Undo removes the entire copy, including tracks it created.

The whole arrangement must fit and satisfy existing media, text-overlap and track limits. A missing selected asset, unsaved draft or concurrent edit blocks the batch rather than making a partial copy or retrying it elsewhere. This is not a cross-project clipboard, source A/B copy, automatic-caption copy or a new keyboard shortcut. Keyboard users can focus and activate the existing buttons.


### Move a selected group between tracks

Select clips of one kind: pictures/videos, audio, or custom text. Drag a selected clip's body to an existing compatible track. All selected clips move by the same track offset, keeping gaps between their tracks. The clicked clip anchors the destination; your primary selection does not change. You can also choose **Anchor destination track** in the selected-group inspector and click **Move group to track** to change tracks without changing time.

The timeline shows destination ghosts; Program keeps the saved scene until you drop or apply. A pure vertical move keeps exact timing, source content, fades and motion. Locked source/destination tracks, occupied destinations, missing tracks or out-of-bounds members block the entire move. Disabled clips still count as occupied. No tracks are added automatically, and one Undo restores the group. Mixed picture/audio/text groups and projects without editable tracks still move together in time, but not across tracks.


## Save an independent project copy

Choose **Save a copy** from Home or Projects. It preserves the saved edit, captions, AI proposals and independently copied media. The new project starts with fresh Undo/Redo history and no previous exports. Current queued changes must save first; explicit local drafts must be resolved by you. Completion never opens the copy automatically. Use **Open copy** to switch deliberately. While copying, **Back to Projects** lets you work in another project without cancelling. See [Save a copy](PROJECT_COPIES.md) for cancellation, uncertain-response recovery and storage limits.


### Balance a named track

Open Audio > Track levels and choose an imported visual or audio track. Its Level and saved Mute affect all sound-enabled occurrences on that track in preview and export; picture remains visible. Original A/B still uses the existing Original mixer. Track levels are applied before role faders, ducking, normalization and Master. Role Solo is preview-only. Locks protect clip edits and placement, not track or role levels.

Drag the fader to audition, then release to save one change. Escape cancels the audition. Enter an exact -60 to +12 dB value and press Enter to save; invalid/unfinished text stays local until corrected or Escape. Mute does not round or reset Level; 0 dB resets Level only. One Undo restores a saved change. The first nondefault track level upgrades the saved track format; older CUTROOM versions cannot open that upgraded format. Save a copy first if you need a separate older-format branch.

Automatic placement uses a neutral-level destination. Explicit placement/movement adopts the destination track's sound settings. Duplicate preserves effective source-track levels. Empty or image-only tracks can store levels for future sound, but they do not generate audio.

## Repair an imported preview

A ready Media pool card now offers **Verify & repair preview**. It verifies the owned original and repairs only derived playback files when needed, keeping the edit, marks, tracks, mix and history. Playback pauses in place. Missing or unverified originals are refused rather than replaced. A lost response is checked, never automatically replayed. See [preview repair](PREVIEW_REPAIR.md) for cancellation, older bindings and recovery boundaries.


## Find every use of an imported file

Each imported Media pool card now shows its saved timeline clip count. Disabled or locked clips still count; this is not a visible/audible-output count and does not include effect references. The existing search/type controls remain, with an imported-usage filter for files with or without timeline clips. Unknown membership is never labeled unused.

Choose **Find uses** to open Timeline Index for that exact imported file, even when another file has the same name. Browsing or closing the index changes nothing. Choose a row to select that saved occurrence, reveal its inspector and go to its start. Pending drafts, saves or gestures must be resolved first; navigation never saves or discards them. **All timeline items** returns to the ordinary index.

From a single imported clip's inspector, **Reveal in Media pool** clears obstructing local pool filters and focuses its exact file without seeking or changing the clip or Source marks. A zero timeline count does not establish that a file can safely be deleted.

**Overwrite without rippling other tracks:** Open an imported video's **In / Out** review, enter the wanted source range, and choose a named visual **Destination track**. With **Edited video** paused, move the edit playhead to the first frame to replace. Open **Overwrite on one track** and check the interval, affected names and counts before choosing **Overwrite this track**. The marked video and its attached sound replace only that part of that track. Retained material resumes from its original picture and sound clocks, and downstream content, captions, other tracks and total runtime stay put. One Undo restores all trimmed, removed and split pieces. Automatic and locked tracks cannot be overwritten. A partial pan/zoom, cut inside a fade, missing media, tiny remainder, or shot past the end is refused rather than silently reshaped or shortened.

### Find your way around a crowded timeline

The **Tracks** readout counts the first and last visible lanes, including partially visible lanes. Use the up/down arrows next to it to page through track rows without seeking, changing zoom or moving any clip. A mouse wheel over the track names scrolls that same timeline; once you reach its end, the surrounding page can scroll normally. The control disappears when every lane fits.

On a narrow screen, the four editing tools and **Snap** stay in the main row. Open **Controls** for the edit target, original-footage review, clip actions and, on phones, zoom and **Fit**. Tablet widths keep zoom in the main row. Escape or **Close** returns to the toolbar. The commands are the same as on desktop, with the same protection and Undo rules.

### Browse an imported source without touching the cut

In **Media**, choose **Open source** on a prepared video or audio file. It opens the original in one step without seeking the edited timeline or saving a change. **Actions** still holds the other commands; drag from the thumbnail or filename as before. The highlighted button belongs to the exact file, even if two files share a name. Finish pending edits or imports before browsing.

For video, **Focus source** enlarges the same player. On desktop the Media pool and timeline remain available; on a smaller screen the source and its controls get the workspace. Set In and Out or audition the shot at original speed. **Split view** or Escape restores the previous layout without resetting playback or marks. A second Escape or **Close source** closes the review. Audio opens its usual audio review. **Append**, **Insert** and **Overwrite** still change the timeline only when you explicitly choose them.

### Lift a marked range from one visual track

To take out part of one imported picture track **without pulling later clips earlier**, pause **Edited video** and set the timeline target to the whole edit. In **Edit → Clip**, mark the range with **Range** and press **Select range**. Open **Lift range from one track** and choose the named visual track. The preview gives the exact starting and exclusive ending timecodes and tells you which clips would be removed, trimmed, or split. **Lift this range** makes that one edit; **Undo** restores the original pieces.

Only complete project frames inside the marks are lifted. This leaves a hole in the chosen track: lower picture layers, captions, and other audio tracks continue normally. A gap can therefore show another image, a caption over black, or silence, according to the existing edit. The chosen clips' own sound is lifted with their picture. Other tracks, the total duration, and the original media files do not change. An empty range on that track is a no-op. Locked tracks, cuts through an audio fade or a partially retained pan/zoom, and surviving pieces shorter than 0.08 seconds are refused instead of silently altered. This command does not lift original A/B footage, audio-only tracks, or text tracks.

### Blend the picture from one imported clip

Select a video or image occurrence on the timeline. In its **Media** inspector, open **Picture opacity**. At **100%** its picture is unchanged; at **50%** the visible layers underneath show through; at **0%** only its picture disappears. Its own audio, captions, other clips and other uses of the same original are unaffected. Existing transparency is multiplied rather than painted over.

Enter a whole percentage or use the slider. The value is not saved and Program does not change just from typing. With **Edited video** paused inside the enabled clip, hold **Hold to preview** with the pointer, Space or Enter to audition the blend; release to see the saved picture. **Apply opacity** saves this occurrence in one Undo step. **Set 100%** stages the fully opaque value; use Apply to save it. Closing the inspector or selecting another occurrence discards an unapplied entry. Opening the original in Source still shows the original picture. A locked track must be unlocked before editing its clips.

With a transparent still set to **Contain**, only the unused border around the fitted image is black. Transparent holes inside the image show the underlying footage; semi-transparent pixels blend with it. **Cover** crops to the frame instead of adding those bars.

### Mark the exact timeline span of selected layers

Select a saved imported video, image, audio occurrence, or a saved text/title/caption layer on the timeline or in the **Index**. In the navigation row choose **Mark clip range**. In the CUTROOM keyboard profile you can focus the timeline and use **Shift+X** instead. Plain **X** keeps its original meaning: mark the primary clip at the playhead. The new command does not seek, play, flush a draft, write to the project or create an Undo step.

For several selected layers, **Mark N clips** makes one continuous range from the earliest start to the latest end, even if the clips are on different tracks. Gaps between them are included. This is a timeline range, not a playlist or solo: **Loop range** and **Export marked** use the whole composite with the normal frame rules. Selected locked or disabled occurrences can supply bounds without being unlocked or enabled. The marked range replaces the layer selection, so future range operations no longer target the old individual clips. Pause **Edited video** and use the whole-edit target; settle pending edits or typed marks first.

### Split several selected layers on the same frame

Pause **Edited video**, choose the whole edit, and select the saved video, audio, image or text occurrences you want to cut. Place the playhead inside every selected occurrence. Use **Split N clips at playhead** in the group inspector, the main **Split** control, or the Split key for your current keyboard profile (**S** in CUTROOM). The playhead is rounded to the nearest output frame for the cut, not moved. Each left piece keeps its ID; the corresponding right pieces become the new selection. One **Undo** rejoins every pair; **Redo** reapplies the same cuts.

Only the selected occurrences are split. Source A/B, other layers, the mix, total duration and original files stay as they were. Picture and sound retain their separate source positions, so a slipped or speed-adjusted picture does not reset the audio. Original outer audio fades keep their timing. Each piece must be at least 0.08 seconds; a single locked track, a clip outside the common point, a crossing fade, a visual pan/zoom or a Chapter title with its built-in fade blocks the whole command. Choose a different point or deselect the incompatible clip. The command does not silently skip clips. Automatic transcript captions are not independent split targets.

### Rejoin a through edit without undoing newer work

Select **exactly two touching pieces** of the same imported video, audio, still image, or matching static title. In the group inspector, use **Join matching clips**. It removes the shared cut, keeps the left clip's identity and selects the joined occurrence. The playhead does not need to be at the cut. Edits you made afterward, such as changing another layer's opacity, stay as they are. One **Undo** restores only this cut; **Redo** joins the pieces again.

CUTROOM checks both picture and sound source time, even for a muted clip or a separately slipped picture. Both pieces must touch on an output frame, be adjacent in the saved stacking order on the same unlocked track, and keep matching settings. A gap, overlapping material, different take or opacity, facing audio fades, Pan/Zoom motion or a Chapter title blocks the join instead of changing its appearance. Static custom titles must have matching text and styling. Custom caption cues and automatic transcript captions are not merged. This is not a general merge of arbitrary shots and never ripples the rest of the edit.

For a single static title, **Split** stores the exact output-frame boundary. Changing its text or appearance does not move that edge. **Join matching clips** also recognizes the six-decimal frame times saved by older single-title splits, without changing media, rounding a gap, or merging caption cues. A Chapter card has a built-in fade: Split explains and refuses rather than making the title blink at the cut. Choose a static template first if you want separate occurrences. The same protection applies when inserting time through a Chapter or removing only part of it with whole-edit **Cut out**. Insert at the title’s start or end, or choose a removal range that contains the entire title or stays outside it. Moving an intact Chapter in time does not restart its fade.
