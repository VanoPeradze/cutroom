# Editing quality: current safeguards and remaining work

Historical engineering notes. For this private beta's readiness and limitations, start with [Beta status](BETA_STATUS.md) and the [current editing guide](INDEPENDENT_TRACKS.md).

This development pass fixes specific correctness and evidence-handling failures. It is not a claim of equal transcription accuracy across languages, professional editorial judgment, or release readiness. No new model was downloaded or benchmarked during implementation.

## What changed

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

## Validation in this pass

- Full Python suite: 755 tests passed. The separately executed frontend workflow suite passed all 61 checks.
- Four real FFmpeg smoke checks passed: two-source export, chronological YouTube cleanup at 1280×720, stacked layout with captions/effects, and embedded-camera output with separately verified top/bottom regions.
- Isolated browser checks at 1280×720 verified that YouTube remains 16:9 after style changes and Creator Frame, and checked the refreshed home, Layout and bilingual Captions screens. No browser errors were recorded in this session. Test footage and transcript text were synthetic; these checks do not measure recognition or editorial quality.
- UI asset revision 46 includes goal-specific generation guidance. Existing distribution ZIPs were not rebuilt in this pass.

## What is still not solved

Default YouTube remains chronological dead-air cleanup, not a full long-form narrative editor. Story AI still depends on the accuracy of the transcript and its chapter summaries. Gaming presets do not semantically recognize every kill, win or joke from video. A skipped/weak critic can leave a reviewable draft, not an automatic editorial guarantee. Automatic speech retries are not a complete targeted segment-repair workflow.

The next acceptance step needs real, consented footage and reference transcripts across languages, devices, source layouts and recording lengths. Use [the offline transcript evaluator](TRANSCRIPT_EVALUATION.md) and human review of relevance, context, complete thoughts, timing, and the exported video. Compare models using the same verified transcript and brief, not just job completion or JSON validity. No cross-language WER/CER results have been measured yet.
