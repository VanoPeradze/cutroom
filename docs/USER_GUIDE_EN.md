# Your first edit in CUTROOM

CUTROOM is a free, open-source video editor in beta. It helps turn recordings into an editable draft; you decide what makes the final cut. The app interface is English. [עברית](USER_GUIDE_HE.md)

Start with the short path below. The later sections explain the controls when you need them.

## The quick path

1. Extract the complete ZIP and run **`run_windows.bat`**. Let first-time setup finish and keep the launch window open.
2. Choose **Manual edit** and add a short, non-sensitive recording as source A. This lets you learn the editor without waiting for AI models or inference.
3. Choose **Open manual editor**. Click the timeline ruler to seek. **Space** plays or pauses.
4. Choose **Range**, drag over an unwanted passage and select **Remove from video**. Try **Undo**. Then select **Cut** and click once to split a clip.
5. Open **Output**, confirm the shape and frame rate, then **Export → Start export → Download video**. Watch that downloaded file outside CUTROOM.

Manual mode does not generate a transcript or AI story. When you are comfortable, start a Short/Reel or YouTube project and set up an AI connection.

## 1. Pick the result before adding footage

| Starting point | Initial result | Best first use |
| --- | --- | --- |
| **Short / Reel** | Vertical 9:16, with AI-assisted moment selection | A focused excerpt from a longer recording |
| **YouTube video** | Horizontal 16:9; default cleanup keeps the recording's order | An explanation, gameplay session or longer spoken video |
| **Manual edit** | Horizontal 16:9 with the full main recording | Direct editing without AI models or an account |

These are starting settings, not irreversible decisions. **Output** changes the format later. A YouTube cleanup is not the same as a short highlight reel: preserving useful structure matters more than reaching a tiny target duration.

Rename a project in the top bar. **Projects** and the welcome screen reopen saved work. The save indicator tells you whether changes have finished saving. Avoid editing the same project in multiple tabs.

## 2. Choose where AI runs

Open **AI connection**. Selecting an option is not enough: choose **Use local AI** or **Use this cloud connection** to save it. Switching is unavailable while processing is active.

| Option | What you get | What you need |
| --- | --- | --- |
| **On my computer** | Local transcription and Story planning; no AI-provider fees or content upload to one | Initial model downloads, disk space and enough memory; speed depends on your machine |
| **Online — Free tier** | Groq processes extracted audio and transcript/editing context, reducing local AI work | Your Groq key, internet and remaining account quota; not unlimited or guaranteed free |
| **My own API account** | The same Groq integration under your chosen plan/model | Your key; provider charges may apply. CUTROOM does not buy, upgrade or cap the account |
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

Only **Groq** is supported by this first cloud integration. This is not a general API-key field for other providers. Open the provider's key link in the dialog, enter your own key and confirm the data-sharing notice before saving.

CUTROOM sends selected audio for transcription and transcript/editing context for Story AI. It does not send video frames. This content can include private speech, so use cloud processing only when you may share that material. Video previews and MP4 rendering still run on your computer: cloud AI is not an online render farm or a browser-only installation.

Keys entered in the app last for the current CUTROOM session. Reconnect after restarting. **Forget session key** clears that key and selects local AI. A supplied key is not a successful connection test. Never include keys in screenshots or bug reports.

The Free tier label does not verify your plan or prevent a paid key from incurring charges. A Story edit can make multiple requests. Quota/key/provider errors stop the task rather than silently switching providers or plans. Cancellation cannot undo usage already accepted by the provider. Mocked regression tests do not certify real provider inference. [Privacy and connection details](AI_CONNECTIONS.md)

## 3. Add footage and check the sources

**Source A** is the main recording. **Source B** is optional; A/B are file labels, not fixed camera/screen roles. Add footage you are allowed to edit. Wait for upload and preparation to finish before starting the draft.

**One ordinary recording:** add only A. You do not need to invent a second source.

**Separate camera and screen:** add both files. Check **Screen recording**, **Camera** and **Audio source**. Choose the audio containing the speech you want transcribed and heard in the export. Automatic synchronization is a starting point; listen near both the beginning and end.

**Camera already inside one recording:** add that combined file only as A. In **Layout**, choose a reference frame, move/resize the camera rectangle, then **Save and use layout**. Do not upload the same file again as B. The confirmed camera fills the top 30%; the remaining screen fills the bottom 70%. This crops one recording into two views—it cannot recover hidden pixels or a separate camera file. A camera that moves during recording needs review.

In **Source setup**, **Source B offset** adjusts sync for the whole edit. Positive values place B later; negative values earlier. The one-frame buttons nudge precisely. Source roles, audio, order and sync are whole-edit settings, even with a short range selected.

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
| **Layout** | Arrange A/B, confirm an embedded camera and frame each clip |
| **Captions** | Correct transcript text, remove/restore passages and style subtitles |
| **Output** | Set shape, resolution, FPS and quality; advanced AI settings are separate |
| **Project overview** | Return to the summary and AI refinement choices |

On larger screens, drag the preview/timeline divider to resize either area; double-click to reset. **Full screen** enlarges the video, not the control panel; **Escape** returns. **How to edit** provides the short in-app workflow. **Help & guide** has searchable explanations: try “models”, “layout”, “captions” or “export”. Optional panels can stay collapsed.

### The three everyday timeline tools

**Select / Move:** click a cut, then drag it to a new place. Clips shift to make room rather than overwriting the destination. Drag a white edge to trim, or reveal more original footage up to the source/neighbor boundary. To move part of a cut, mark it with Range, switch to Select / Move and drag inside the selection.

**Range:** drag over an interval, then **Remove from video**. It can start or end inside a clip; selection is not limited to AI cut points. **Range…** accepts exact times as seconds or `mm:ss.mmm`.

**Cut:** click once to split. This alone removes nothing. **Cut out**, in More editing tools, removes the interval between two clicks; Escape cancels the pending first cut.

Click the ruler to move the yellow playhead. **+ / −** zoom around it; **Fit** shows the full edit. **Zoom to selection** focuses a marked range. **Snap** helps align boundaries; turn it off for freer selection. Undo/Redo reverse manual edits without changing original media.

### Together or one source?

| Edit target | What changes | Gaps |
| --- | --- | --- |
| **Together (A+B)** | Both sources and their layout mapping | Removing closes the interval; moving inserts the paired cut |
| **A only / B only** | Only that track; the other stays still | Removal can leave an intentional gap; movement shifts only that track |

Together helps preserve synchronization. Choose A/B only for deliberately independent timing. **Close gaps** removes empty time in the chosen scope; Together closes only where both tracks are empty. When one source is missing, the other fills the frame; when both are missing, it is black. Audio follows the selected audio source and is silent in its gaps.

### Restore removed footage

Open **Original footage** to see the full recording and its kept/removed regions. Choose A or B, preview a section or drag a range, then **Restore to edit**. **Previous removed / Next removed** help find omissions. Missing material returns near its source neighbors without reordering existing cuts. **Remove from edit** affects uses of that source interval, including copies; check the scope first.

**Insert a copy by time…** deliberately duplicates source footage at an exact edit position. **Duplicate clip** copies the selected cut. **Reset to AI draft** resets manual sequence changes after confirmation; ordinary Undo is safer for one recent change. [Detailed editing behavior](INDEPENDENT_TRACKS.md)

### Familiar keyboard controls

Open **More editing tools → Keys / Shortcuts**. Choose CUTROOM, DaVinci Resolve, Adobe Premiere Pro, Pro Tools or Final Cut Pro. The list shows supported commands, not a full emulation of those editors. Space plays/pauses. Shortcuts stay inactive while typing in caption or form fields. [Full shortcut reference](KEYBOARD_PROFILES.md)

## 7. Arrange and frame the video

Select **where** a layout applies: a timeline range, exact From/To times or **Entire edit**. Then choose **Screen only**, **Camera only**, **Stacked**, **Side by side** or **Picture in picture**. The choice saves immediately. **AI choice** returns that scope to the proposed composition.

**Creator frame** places the camera top 30% and screen bottom 70%, keeping the selected output shape. **First in layout** means top in stacked or left in split. **Primary source** sets emphasis in relevant layouts. **Swap top / bottom** changes order for the whole edit.

**Fill frame** crops edges to fill the panel. **Fit entire source** keeps the full picture with bars when needed; it does not squeeze the image. In **Clip framing**, choose A/B and adjust horizontal focus, vertical focus and zoom. Check the scope label: changes affect the selected clip/range, or the clip at the playhead—not automatically every cut. Crops follow clips when moved/copied. Full source browsing does not enable per-cut framing edits.

For an embedded camera, use its rectangle and **Main screen focus**. A fixed rectangle does not track a moving camera. **Source order preview** checks routing; **Layout by section** lists existing composition blocks.

## 8. Correct words and control captions

Search the transcript or filter **All lines / In the edit / Removed**. Click a line to seek; Shift-click selects a passage. **Remove passage / Restore passage** changes footage. Correcting text alone neither removes footage nor generates replacement speech.

Edit **Correct selected line**, then **Save text**. **Save all changes** saves pending line edits; **Discard changes** drops the current unsaved correction. Check Saved/Unsaved before closing the browser—unsaved text buffers are not a backup.

Under **Subtitle style & speech language**:

- **Burn into video:** permanently render captions into the exported picture.
- **Export SRT file:** create a separate editable subtitle file beside the video.
- **Style / Position / Size:** control appearance; check faces, graphics and platform overlays yourself.
- **Words per caption:** shorter or longer caption chunks, not different transcription.
- **Speech language:** affects AI transcription and can require rebuilding; it is not a translation target.

Captions follow edited timing and the selected audio source. Manual projects start without transcript text; enabling subtitles does not itself transcribe them.

## 9. Export and understand rebuilds

Set **Aspect ratio** (9:16, 16:9, 1:1, 4:5 or Source), **Resolution** (720p/1080p), **Frame rate** (24/25/30/50/60 FPS) and **Export quality**. Higher settings can increase render time and size. 60 FPS preserves high-rate footage when available; lower-rate input repeats frames, not AI-generated motion.

Controls marked **Draft rebuild** change editorial decisions and require **Rebuild Draft**. This is a new draft operation, not a preview refresh: save transcript corrections first and review afterward. Format and subtitle styling do not require rebuilding the story. **Performance mode** controls AI choices, not MP4 encoding quality. **Smart editorial effects** adds bounded emphasis; **Final loudness balance** adjusts exported sound levels.

Choose **Export**, check the summary, then **Start export**. Rendering uses original media rather than preview proxies. **Stop process** cancels export; closing the dialog alone does not. When ready, **Download video** and save the file. Before sharing, watch the start/end, cuts, captions, sync and frame shape outside the app.

## 10. Save, recover and report a problem

Projects live on the computer running CUTROOM, not in a cloud account. Default folders are `data/projects` for projects/imported media, `data/exports` for exports and `data/cache` for caches. Keep backups. Do not delete these folders as a generic fix. Deleting a project can remove its imported copies and exports; original files outside CUTROOM are separate.

Closing the browser does not stop the application. Save text, wait for the save indicator, and finish or cancel jobs before closing the launcher. Model caches can live outside the app folder. [Setup logs and recovery](TEST_ON_ANOTHER_PC.md)

| Problem | Check first |
| --- | --- |
| Model missing | Local readiness and the named download; Manual edit is still an option |
| Cloud quota/key error | Provider account and quota; no automatic paid fallback |
| Bad transcript | Audio source, speech language, source sound; then model choice/manual correction |
| Wrong layout | Source roles, selected scope, output aspect, Fill versus Fit |
| A/B drift or black areas | Sync, source durations and independent-track gaps |
| Rebuild required | Save text and rebuild after editorial-setting changes |

Report the exact action/error, build name, input length/language and a redacted screenshot with the [feedback form](BETA_FEEDBACK.md). Never include API keys or the entire private `data` folder. The beta is not certified across all PCs, languages or footage; [limitations](BETA_STATUS.md) distinguish automated checks from real-world validation.
