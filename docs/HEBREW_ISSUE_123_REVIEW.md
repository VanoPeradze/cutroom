# Hebrew transcription and mixed captions: issue 123 review

Local integration verified on 2026-11-10 in the existing Windows CUTROOM project. This is a scoped development change, not a release or an accuracy certification.

## Sources and assessment

- Issue: https://github.com/VanoPeradze/cutroom/issues/123
- Contribution: https://github.com/iddo12/cutroom/tree/global-editor/hebrew-first
- Contribution inspected at 5b3daf72bc20add2073b790e7cd6ebf351e613a8.
- Isolated review baseline: upstream master 0034028304c59b04f2423623a7b29ba4c4a00e46.
- Local project HEAD: 17b0a8755e1d731ee9a00f42734507eac6b32c85, branch codex/ffmpeg9-hotfix-20261019. The worktree already contained extensive changes. Relevant source files matched the reviewed baseline and were backed up before focused edits.

The contribution usefully identifies Hebrew ASR and mixed-script caption problems. Importing it wholesale would override the established lightweight Balanced model policy and contradict two existing model-selection tests. Its added local/cloud selector also needs a unified routing decision: the older cloud-connection path runs first, so selecting local would not necessarily override an existing cloud connection. That selector and cloud integration were not imported.

The reported WER improvement, about 17-27% to 1.5-4.3% over three short windows, is preliminary contributor evidence with an AI-corrected reference. It was not independently reproduced and should not be described as measured CUTROOM quality. A larger consented test set, human-corrected reference, unchanged audio, and recorded model/hardware settings are needed.

## Changes integrated locally

1. Auto may refine confidently detected Hebrew using an already cached ivrit.ai model on CUDA. It requires a known bounded duration, unambiguous language evidence and successful single-GPU memory measurement. Explicit Balanced and Lite remain lightweight.
2. Automatic Quality model loads and Auto refinement pass local_files_only=True to faster-whisper. No new model download is triggered by this upgrade. Explicit Quality retains its existing behavior.
3. Refinement preserves the original until completion, valid timing, at least 80% original speech overlap, English-term retention and the speech-quality checks pass. Cancellation propagates and original detection confidence is retained. Confidence is not a WER estimate.
4. Mixed Hebrew/ASCII ASS presentation isolates a whole phrase, not each token. This fixes adjacent phrases such as 4K 60fps and Sony A7 IV / H.264 while preserving source text and SRT.
5. Added regression tests and updated model/license documentation. The ivrit.ai CT2 card identifies Apache-2.0; CUTROOM remains MIT. No model weights or third-party binaries are bundled by these edits.

Model card: https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2

## Local validation

The identical focused pre-existing suite was run before and after the changes, with the new tests added afterward:

- Before: 195 passed, 7 failed.
- After: 295 passed, the same 7 failed.
- All 100 new tests passed: 60 routing/safety, 26 caption presentation, 14 real libass rendering tests.
- All 884 existing Node frontend tests passed.
- Scoped whitespace checks and Python syntax checks passed.
- Focused review of the routing diff found no high- or medium-priority issues.

The seven pre-existing failures are in test_caption_generation.py. The host's caption-readiness check reports insufficient available physical memory (it requires at least 8 GiB), so generation API tests expecting 202 receive 409 instead. That safety guard was not disabled or weakened. An expanded caption-only run also encountered a related generation-readiness failure in test_selected_caption_ranges.py; it is outside the changed presentation path.

Windows renders used existing FFmpeg 7.1.1, libass 0.17.3-79, FriBidi 1.0.16, HarfBuzz 10.4.0, with ArialMT selected. The real-render oracle rejects the original incorrect ordering and the contribution's per-token reversal, and accepts whole-phrase isolation. No render test was skipped.

The existing local pytest bundle required disabling its missing optional stepwise plugin. Tests used Python 3.12.14, existing dependencies, disabled external plugin autoload, and offline Hugging Face mode. No dependency installation was performed.

Evidence is under validation-work/hebrew-review-20261110:
- baseline-focused.log and after-focused.log
- frontend.log
- caption-render-font.log and caption-windows-comparison.png
- transcription-backup and caption-backup
- integration-manifest.json and local-integration.patch

## Limits and next evaluation

No real audio was transcribed, no speech model was downloaded or run, and no GPU speed, peak VRAM or WER/CER improvement was measured. The full Python suite was not rerun on this Windows host. These controlled single-line caption fixtures do not certify browser preview/export parity, arbitrary wrapping, nested punctuation, accented Latin phrases or Arabic shaping.

Next, evaluate consented Hebrew and mixed Hebrew/English footage using the procedure in TRANSCRIPT_EVALUATION.md. Compare Small, generic Turbo and ivrit.ai with identical audio and a human-corrected reference. Record WER/CER, English/name retention, word timing, latency, peak RAM/VRAM and human correction time. Keep the existing lightweight policies until those measurements justify a broader default change.

No app/service was launched, no cloud transcription was enabled, and no commit, push or publication was made.
