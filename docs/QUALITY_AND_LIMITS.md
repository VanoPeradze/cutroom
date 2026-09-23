# Editing quality: current safeguards and remaining work

For CUTROOM 1.1 Beta's readiness and editing controls, see [Beta status](BETA_STATUS.md) and the [user guide](USER_GUIDE_EN.md).

This development pass fixes specific correctness and evidence-handling failures. It is not a claim of equal transcription accuracy across languages, professional editorial judgment, or release readiness. No new model was downloaded or benchmarked during implementation.

## Hebrew/English transcription and local recovery

The speech decoder explicitly transcribes rather than translates. Selected Hebrew uses short Hebrew/English context; automatic language selection adds this context only to a retry after Hebrew script appears in the actual transcript. It does not force every automatic recording into Hebrew. Yiddish detection is protected, and low confidence remains a review signal rather than proof of an error.

Balanced and Quality reuse the loaded local speech model to retry at most two weak units, each no longer than 30 seconds, with a combined 48-second audio budget per local pass. Lite adds no retry. A candidate replaces the whole unit only when confidence improves and checks preserve timing, speech coverage and trusted English terms. Failed or unsafe retries keep the completed original. This adds no cloud request or model download and does not ask Story AI to rewrite speech. Review warnings identify weak segments even when the overall transcript is usable; confidence is not an accuracy percentage.

The budget is shared with the existing auto-Hebrew Quality refinement. Existing full-model refinement, GPU quality upgrade and device-failure fallback remain separate paths; a device fallback starts another bounded pass. The 48 seconds is audio rechecked, not a wall-clock timeout or a cap on all transcription work. There is no glossary interface or guarantee of correct mixed-language recognition. Mocked regression tests cover recovery limits, cancellation, timing, English-term preservation and cloud routing. No real-audio accuracy improvement has been measured.

## Media, sound and output limits

The project library accepts additional video, images and audio. These form layers inside an existing edit; they do not extend its duration automatically or replace the two main A/B sources. Audio waveforms help placement; the mixer controls original sound, music, voiceover, effects and master level. Listen to the exported mix as well as the preview. Adding media and mixing audio require no API or AI model.

A/B **Picture speed** changes picture playback while keeping clip duration and speech timing. Faster picture playback can exhaust the source and hold its last frame; any speed change can break lip sync. This is different from speeding up the entire picture-and-sound edit. QHD 1440p and 4K 2160p exports are available alongside 720p and 1080p; larger frames consume more rendering resources and do not recover detail absent from the original.

## Earlier safeguards

- Changing a style preserves the chosen goal, aspect, duration, resolution and export quality. Creator Frame changes composition without silently turning YouTube into a vertical export. Upload/preparation refreshes preserve pending settings, and generation checks the goal it actually submits.
- The automatic long-form cut budget applies to the first candidate too. Overlapping cuts are measured by their union. Explicit user cuts may still exceed that budget.
- Transcription records processed chunks, source duration and available Faster-Whisper Silero VAD measurements. Proven incomplete processing or substantial detected-speech/recognized-speech disagreement cannot silently become a story made from a partial transcript. VAD is fallible, especially with game audio/background voices.
- A missing legacy processing record remains **unknown**, not proof that a quiet ending is missing speech. Suspicious legacy coverage is shown as a review warning. Complete sparse recordings are not rejected simply because they contain little speech.
- Explicit Balanced/Quality speech profiles keep their model choice during CPU fallbacks. Auto can still choose a lighter profile; requested/actual model, mode and device are recorded. Stronger Story AI models still need to be installed; Quality selects among installed models.
- Chapter understanding now receives complete beat text in size-bounded batches, rather than the first 300–520 characters. Oversized chapters/individual beats are split without dropping text, then summaries are combined under their original IDs. Downstream bounded excerpts retain beginning, middle and ending, with visible omission markers.
- Strict Story AI requests reserve space for their response on every attempt. Context can grow to 32,768 in non-Lite modes; Lite remains capped at 8,192. Permitted evidence excerpts may be shortened without removing IDs or instructions. Requests that still cannot fit fail explicitly. Sizing is a conservative estimate, **not** an exact model tokenizer; larger contexts use more memory.
- Failed continuity checks, extractive summary recovery and concentrated source selection produce visible review notes. Concentration can be correct for one complete moment: the editor does not scatter unrelated clips simply to fill the timeline. Deterministic style tie-breaking no longer always prefers the earliest equal-scoring moment.
- The visual update softens surfaces, uses purple for primary/export actions and reserves green for keep/success signals. Reduced-motion preferences are respected.

Existing saved drafts are not rewritten. Rebuild to use the new analysis rules; changed transcript/story fingerprints invalidate incompatible cached analysis without deleting footage. Save pending text changes before rebuilding.

## Earlier validation record

- Full Python suite: 755 tests passed. The separately executed frontend workflow suite passed all 61 checks.
- Four real FFmpeg smoke checks passed: two-source export, chronological YouTube cleanup at 1280×720, stacked layout with captions/effects, and embedded-camera output with separately verified top/bottom regions.
- Isolated browser checks at 1280×720 verified that YouTube remains 16:9 after style changes and Creator Frame, and checked the refreshed home, Layout and bilingual Captions screens. No browser errors were recorded in this session. Test footage and transcript text were synthetic; these checks do not measure recognition or editorial quality.
- UI asset revision 46 includes goal-specific generation guidance. Existing distribution ZIPs were not rebuilt in this pass.

## What is still not solved

Default YouTube remains chronological dead-air cleanup, not a full long-form narrative editor. Story AI still depends on the accuracy of the transcript and its chapter summaries. Gaming presets do not semantically recognize every kill, win or joke from video. A skipped/weak critic can leave a reviewable draft, not an automatic editorial guarantee. Automatic speech retries are not a complete targeted segment-repair workflow.

The next acceptance step needs real, consented footage and reference transcripts across languages, devices, source layouts and recording lengths. Use [the offline transcript evaluator](TRANSCRIPT_EVALUATION.md) and human review of relevance, context, complete thoughts, timing, and the exported video. Compare models using the same verified transcript and brief, not just job completion or JSON validity. No cross-language WER/CER results have been measured yet.
