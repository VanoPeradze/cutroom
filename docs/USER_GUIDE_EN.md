# Your first edit in CUTROOM

CUTROOM is a free, open-source video editor in beta. It helps turn recordings into an editable draft; you decide what makes the final cut. The app interface is English. [עברית](USER_GUIDE_HE.md)

Start with the short path below. The later sections explain the controls when you need them.

Use **Day / Night** in the top bar to change the app's appearance; your choice is saved in this browser. The video preview keeps its original colors. **Guide** opens searchable help from any screen. While a job is running, its status and **Stop process** stay together below the navigation.

## The quick path

1. Extract the entire ZIP, then open **windows** or **mac**. On Windows, double-click **`START CUTROOM.bat`**. On Mac, double-click **`START CUTROOM.command`**. Read and approve the setup prompts, and keep the launch window open. Leave **START HERE.html** (offline help) and **App** (technical files and saved work) beside the launcher. Older Windows packages and GitHub source checkouts still use `run_windows.bat`. Mac users: read the [Mac setup guide](https://github.com/VanoPeradze/cutroom/blob/master/docs/MAC_BETA.md) first; macOS 15+ is required, and first-time dependencies may require Homebrew.
2. Choose **Manual edit** and add a short, non-sensitive recording as source A. This lets you learn the editor without waiting for AI models or inference.
3. Choose **Open manual editor**. Click the timeline ruler to seek. **Space** plays or pauses.
4. Choose **Range**, drag over an unwanted passage and select **Remove from video**. Try **Undo**. Then select **Cut** and click once to split a clip.
5. Open **Output**, confirm the shape and frame rate, then **Export → Start export → Download video**. Watch that downloaded file outside CUTROOM.

Manual mode does not generate a transcript or AI story. Adding library media, typing titles/captions, importing subtitles, mixing audio and exporting work without an API key or AI models. When you are comfortable, start a Short/Reel or YouTube project and set up an AI connection.

## 1. Pick the result before adding footage

| Starting point | Initial result | Best first use |
| --- | --- | --- |
| **Short / Reel** | Vertical 9:16, with AI-assisted moment selection | A focused excerpt from a longer recording |
| **YouTube video** | Horizontal 16:9; default cleanup keeps the recording's order | An explanation, gameplay session or longer spoken video |
| **Manual edit** | Horizontal 16:9 with the full main recording | Direct editing without AI models or an account |

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
- **Story model:** reads the transcript to help summarize and select moments. It cannot recover words that transcription missed, and it is not a visual gameplay-understanding engine.

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
| Quality | Whisper Turbo | 1.63 GB | Qwen3.5 9B | 6.6 GB |
| Quality, Hebrew selected | ivrit.ai Whisper Large V3 Turbo | 1.63 GB | Qwen3.5 9B | 6.6 GB |

These are estimates for model downloads, **not total installation size or memory requirements**. Dependencies, cache overhead, footage, previews and exports take additional space. Story selection can reuse another compatible installed model; a quality label is not proof that a particular model was used. Check the displayed readiness/model information. [Full model details](MODELS.md)

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
- **Edit style:** guides rhythm and moment selection. It does not clone a creator, add licensed assets or guarantee visual gameplay-event detection.
- **Target length:** suggests the desired duration. Sentence boundaries and source coverage can affect the result; check actual duration.
- **Director instruction:** an optional brief, for example “Keep the explanation and its example; remove repeated setup.” It guides editing, not unrestricted video generation.
- **Burn captions into video:** captions become part of the MP4 picture. You can adjust them later.
- **Audio cut line:** audio below the threshold is a possible silence cut, not a command to remove all quiet sound. **Use recommended** starts from measured audio. **Handle silence longer than** sets the minimum quiet duration; **Silence to keep** leaves a breathing pause. Audition quiet speech before making cuts more aggressive.

Choose **Build my first cut** when the readiness message is satisfied. Transcription, story work and preview preparation take different amounts of time. **Stop process** requests cancellation; wait for completion before retrying.

If a job fails, read the explanation and fix that cause. Original recordings are not overwritten. A larger model cannot fix wrong source routing or recover inaudible speech.

## 5. Review the first cut

The overview shows the draft, before/after duration and **What changed**. If **Reel options** appear, compare them; they are candidates, not proof of better storytelling.

**Shorter**, **Keep more**, **More energy**, **Fewer switches**, **Focus speaker** and **Try another cut** ask for draft changes. These are editorial actions, not playback controls. Review the result before fine manual work: AI actions can change the draft. Use **Studio** for precise editing.

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

Click the ruler to move the yellow playhead. **+ / −** zoom around it; **Fit** shows the full edit. **Zoom to selection** focuses a marked range. Undo/Redo reverse manual edits without changing original media.

**Snap** is beside Undo/Redo in the timeline toolbar. Switch it on to align a trim, range or moved clip to the yellow playhead, A/B cuts or added media/audio edges. A cyan guide names the alignment target. **Alt** temporarily bypasses snapping; **Esc** cancels a drag without saving. Snap starts off, and never makes ruler seeking jump to a cut. Reordering source clips aligns the leading edge and closes the old position; added media can align either edge without reordering the base footage. Source limits still apply: snapping cannot reveal frames that do not exist. The timeline hover readout uses **hours:minutes:seconds:frames** at the output frame rate; a trim shows its actual allowed edge, not an unreachable pointer position.

### Together or one source?

| Edit target | What changes | Gaps |
| --- | --- | --- |
| **Together (A+B)** | Both sources and their layout mapping | Removing closes the interval; moving inserts the paired cut |
| **A only / B only** | Only that track; the other stays still | Removal can leave an intentional gap; movement shifts only that track |

Together helps preserve synchronization. Choose A/B only for deliberately independent timing. **Close gaps** removes empty time in the chosen scope; Together closes only where both tracks are empty. When one source is missing, the other fills the frame; when both are missing, it is black. Audio follows the selected audio source and is silent in its gaps.

### Protect a finished source

Open **Edit → Track protection**, then choose **Lock A** or **Lock B**. The control appears after a draft exists. A lock protects that source's cuts, moves, trims, clip framing, picture speed and source timing. It does not mute or hide the footage: preview, audio and export continue normally. Choose **A only / B only** for the other, unlocked source to keep editing it.

Protection is saved with the project and survives reopening. Lock/unlock choices sit outside Undo/Redo and preserve the existing history. A Together edit or an Undo/Redo step that would change a locked lane is rejected without changing the edit or consuming that history step. Unlock the affected source and retry; Undo does not switch a lock off for you.

Unlock all protected sources before rebuilding/refining the draft or replacing/removing source footage, because those operations can reset the shared draft. **Reset to AI draft** also requires unlocking any protected lane it would change. Shared layout, the audio mixer and added media remain editable; per-clip framing on a protected source remains locked. Changing B's sync offset requires B to be unlocked.

These controls protect the existing A/B lanes. Added media does not automatically ripple with them, and arbitrary user-created source tracks are not part of this increment.

### Restore removed footage

Open **Original footage** to see the full recording and its kept/removed regions. Choose A or B, preview a section or drag a range, then **Restore to edit**. **Previous removed / Next removed** help find omissions. Missing material returns near its source neighbors without reordering existing cuts. **Remove from edit** affects uses of that source interval, including copies; check the scope first.

**Insert a copy by time…** deliberately duplicates source footage at an exact edit position. **Duplicate clip** copies the selected cut. **Reset to AI draft** resets manual sequence changes after confirmation; ordinary Undo is safer for one recent change. [Detailed editing behavior](INDEPENDENT_TRACKS.md)

### Familiar keyboard controls

Open **More editing tools → Keys / Shortcuts** and choose a preset. The list shows the commands supported by CUTROOM. Space plays/pauses. Shortcuts stay inactive while typing in caption or form fields. [Full shortcut reference](KEYBOARD_PROFILES.md)

### Add media and mix sound

In **Media & audio**, choose **Add media** to import video, an image or audio into this project's library. Wait for preparation, place the yellow playhead and select **+ Add**. Drag the new clip or its edges in the waveform/timeline lanes; use its inspector for exact start/end, source in, volume and fades. Images can stay still, slowly zoom or pan. **Use clip audio** enables sound from an added video; check its **Audio group**.

The timeline waveform shows measured audio from the selected original A/B source, including manual edits without AI. Imported audio has its own waveform. A silent section, missing audio and a pending/unavailable measurement are different states.

Open **Audio mixer** to balance Original, Voiceover, Music, Effects and Master. Original is the selected A/B audio source; the other channels group media by audio role. Mute and volume affect preview and export; Solo auditions a channel in preview only. Live meters show browser sample peaks and reset on pause/seek. Leave headroom; export normalization can change final loudness. Media layers fit inside the existing edit duration; adding a file does not extend the whole edit or create more main A/B sources.

**Stabilize footage** makes an optional local copy without replacing your original or edit. Support depends on your FFmpeg build, and smoothing may crop edges. [Steps and limits](STABILIZATION.md).

For a selected main A/B clip, **Picture speed** changes only the picture, from 0.25× to 4×. Clip length and speech timing stay in place. It can lose lip sync, and reaching the end of the source can hold the last frame. Check the result before export; this control does not speed up the entire picture-and-sound edit.

## 7. Arrange and frame the video

Select **where** a layout applies: a timeline range, exact From/To times or **Entire edit**. Then choose **Screen only**, **Camera only**, **Stacked**, **Side by side** or **Picture in picture**. The choice saves immediately. **AI choice** returns that scope to the proposed composition.

New two-source Reels default to **Stacked**: camera top 30%, screen bottom 70%, filling both panels without stretching. Saved manual choices stay intact. To restore this composition in an existing project, open **Advanced → Restore 30/70 stack**; it resets order and fit for the whole edit. **First in layout**, **Primary source**, **Swap top / bottom**, audio and sync are also under **Advanced**.

**Fill frame** crops edges to fill the panel. **Fit entire source** keeps the full picture with bars when needed; it does not squeeze the image. In **Clip framing**, choose A/B and adjust horizontal focus, vertical focus and zoom. Check the scope label: changes affect the selected clip/range, or the clip at the playhead—not automatically every cut. Crops follow clips when moved/copied. Full source browsing does not enable per-cut framing edits.

For an embedded camera, open **Camera area in this recording** and drag its rectangle; the picker starts folded once configured. Open **Precise camera position** only when you need numeric controls. **Main screen focus** sets the default screen position; a clip's own framing takes priority. **More layouts** contains side-by-side, picture-in-picture and the style default. A fixed rectangle does not track a moving camera. **Original source preview** and **Source order preview** are optional reference monitors; **Layout by section** lists composition blocks. If saving fails, the camera picker opens and offers **Retry save**; do not close the editor until it shows **Saved**.

## 8. Add text and control captions

### Your own titles and subtitles

Open **Captions → Your text & captions** after creating a draft or opening the manual editor. Place the playhead, then choose **Add text** for a title or **Add caption** for a subtitle. Select the new item and type. Changes preview immediately and save automatically after a short pause in typing; wait for **Saved** before leaving. A failed save keeps your pending text and offers **Retry save** or **Discard unsaved text changes**.

Each item appears on its own timeline layer. Drag the item to move it or drag its edges to change its duration; **Start / End (seconds)** provide exact placement. **Preview at start** seeks to it. Choose **Top**, **Center** or **Bottom**, **Clean**, **Bold** or **Boxed**, and a size from 75% to 150%. Use **Find custom text** to search, **Remove text** to delete an item, and Undo/Redo to reverse saved text edits.

These times refer to the **edited video**, not the original recording. Custom text stays at its edit time when you reorder source footage; it does not automatically ripple with A/B. Text must fit inside the current edit. If shortening the video would leave text past its new end, CUTROOM rejects that edit: first trim, move or remove the affected text.

### Import SRT or VTT

Choose **Import SRT / VTT** and select a UTF-8 `.srt` or `.vtt` file, no larger than **1 MiB (1,048,576 bytes)** and containing at most **2,000 cues**. Its times must already match the edited video and fit its duration. Import keeps text and timing; file-specific fonts, markup and VTT positioning are replaced by CUTROOM's editable style presets.

Imports add to your custom captions by default. Select **Replace my existing custom captions when importing** to replace those captions only; titles and the AI transcript stay in place. Invalid imports leave the existing text unchanged, and Undo reverses a successful import in one step. A project can contain up to 2,000 custom text items, with at most 16 simultaneous items and 1,000 characters per item. Items sharing a position can overlap, so review the picture.

Custom titles and captions are always burned into the exported video. The AI **Burn into video** switch does not hide them. Optional **Export SRT file** combines timed AI and custom captions, excluding titles. To avoid duplicate subtitles, turn off AI burning when you use custom captions instead; importing does not remove the AI transcript or its captions from an enabled SRT export. These text tools require no AI processing or paid account.

### Correct an AI transcript

Search the transcript or filter **All lines / In the edit / Removed**. Click a line to seek; Shift-click selects a passage. **Remove passage / Restore passage** changes footage. Correcting text alone neither removes footage nor generates replacement speech.

Edit **Correct selected line**, then **Save text**. **Save all changes** saves pending line edits; **Discard changes** drops the current unsaved correction. Check Saved/Unsaved before closing the browser—unsaved text buffers are not a backup.

Under **AI subtitle style & speech language**:

- **Burn into video:** permanently render AI captions into the exported picture; custom text remains visible independently.
- **Export SRT file:** create a separate editable subtitle file containing AI and custom captions, without titles.
- **Style / Position / Size:** control appearance; check faces, graphics and platform overlays yourself.
- **Words per caption:** shorter or longer caption chunks, not different transcription.
- **Speech language:** affects AI transcription and can require rebuilding; it is not a translation target.

AI captions follow edited timing and the selected audio source. Manual projects start without transcript text; enabling subtitles does not itself transcribe them. You can still type or import your own captions above.

For mixed Hebrew/English, choose the main spoken language and review names and English terms. Local Balanced/Quality can recheck up to two weak units of at most 30 seconds each, within a 48-second audio budget per local pass, using the loaded model. Lite adds no such retry. Timing, confidence and spelling checks can keep the original instead. This does not translate or use Story AI to rewrite speech. Low-confidence warnings mean “listen and review,” not a measured accuracy score; automatic detection can still be wrong. [Recovery details and limits](QUALITY_AND_LIMITS.md)

## 9. Export and understand rebuilds

Use **16:9 Landscape** or **9:16 Vertical** at the top of the editor for a one-click format change, including manual projects. The preview updates and the format saves automatically for export. No AI or rebuild is needed; your cuts stay intact. Use **Layout → Clip framing** if the subject needs repositioning in the new shape.

Set **Aspect ratio** (9:16, 16:9, 1:1, 4:5 or Source), **Resolution** (720p, 1080p, QHD 1440p or 4K 2160p), **Frame rate** (24/25/30/50/60 FPS) and **Export quality**. Higher settings can increase render time, memory use and size. Higher resolution does not recover missing source detail. 60 FPS preserves high-rate footage when available; lower-rate input repeats frames, not AI-generated motion.

Controls marked **Draft rebuild** change editorial decisions and require **Rebuild Draft**. This is a new draft operation, not a preview refresh: save transcript corrections first and review afterward. Format and subtitle styling do not require rebuilding the story. **Performance mode** controls AI choices, not MP4 encoding quality. **Smart editorial effects** adds bounded emphasis; **Final loudness balance** adjusts exported sound levels.

Choose **Export**, check the summary, then **Start export**. Rendering uses original media rather than preview proxies. **Stop process** cancels export; closing the dialog alone does not. When ready, **Download video** and save the file. Before sharing, watch the start/end, cuts, captions, sync and frame shape outside the app.

## 10. Save, recover and report a problem

Projects live on the computer running CUTROOM, not in a cloud account. Default folders are `data/projects` for projects/imported media, `data/exports` for exports and `data/cache` for caches. Keep backups. Do not delete these folders as a generic fix. Use the confirmed **Delete** action in the lobby or Projects when you intend to remove a project and its imported copies/exports; original files outside CUTROOM remain untouched.

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
| Text prevents shortening the edit | Trim, move or remove the custom text that would be past the new end; text does not ripple automatically |

Report the exact action/error, build name, input length/language and a redacted screenshot with the [feedback form](BETA_FEEDBACK.md). Never include API keys or the entire private `data` folder. The beta is not certified across all PCs, languages or footage; [limitations](BETA_STATUS.md) distinguish automated checks from real-world validation.
