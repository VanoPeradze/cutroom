# Editor and analysis quality handoff â€” 2026-10-09

## Resulting behavior

- Transcription coverage now uses the selected imported audio stream's finite, positive duration. A longer video/container tail no longer makes fully decoded audio look incomplete. Missing or invalid audio metadata still requires coverage of the container; the last spoken word never defines completion. Timeline and export duration remain based on the video. The source cache fingerprint includes audio duration.
- A rejected transcription retains per-attempt quality, model/device, coverage, and worker failure diagnostics under the project's local `analysis-diagnostics/` directory. Native return code, traceback, stderr tail, and last progress survive temporary-worker cleanup. The existing completeness gate remains strict, and failures do not replace saved analysis, drafts, or manual edits.
- Setup follows media â†’ source confirmation â†’ goal â†’ style/format/length â†’ optional AI settings â†’ readiness â†’ start. Existing format/language/profile/visual-AI controls move between setup and editor without duplicate IDs or lost handlers. Camera controls adapt to their actual container width; compact editor columns and navigation-height calculations prevent overflow.
- Visual observations require the complete typed response schema. Non-gameplay screens cannot acquire action scores from flags or nearby gameplay. Sparse observations apply only to sampled spans, with scores discounted by actual coverage. One- and two-window sources can complete successfully. The visual cache version is now `gameplay-vision-v2`.

## Verified locally

- 202 focused Python regressions passed, covering the input-duration contract, worker diagnostics, coverage, bilingual quality, safety gates, cache rebuilds, and visual moments.
- 167 frontend regressions passed. Real Chrome checks covered 42 viewport/tab cases plus open camera controls at desktop and narrow widths, with no browser console errors. Setup settings survived save/reopen and setup/editor transitions. Playback, caption edit/undo/redo, and an actual 18-second 1080p export were exercised.
- A real-audio fixture with 30 seconds of audio inside 45 seconds of video reproduced the previous false incomplete-coverage failure and passed after the fix. Deliberately incomplete decoding remains rejected.
- Fresh local CUDA/float16 validation decoded an entire 1,638.549-second English audio stream: 55/55 native chunks completed, zero failed/incomplete/pending chunks, and no device/model fallback. A separate 180-second Hebrew excerpt completed 6/6 chunks on `ivrit-ai/whisper-large-v3-turbo-ct2`; English used `turbo`. Both passed the unchanged completeness gate and independent full audio decoding. Observed validation times were 23.75s and 5.67s on the test machine, not portable performance promises.
- Actual 720p exports covered native chunk boundaries and the audio tail. The speech-bearing export included source boundaries at 300, 750, and 1080 seconds plus the tail; it produced a 28.533-second H.264/AAC file, passed full decoding, and had seven bounded subtitle cues. Burned captions were visually checked before and after a native chunk boundary and absent in the silent tail.
- Seven original project JSON files matched their pre-validation hashes. Private recordings, transcripts, exported media, diagnostics, and screenshots remain local and are excluded from Git.

## Remaining limits and follow-up

- Complete decoding does not prove word accuracy. The full English result retains 25 confidence-review segments; the Hebrew excerpt retains one. No reference transcript/WER or blind editorial benchmark was created.
- The selected real recordings do not establish the cause of every reported incomplete-processing failure. Their audio/video duration differences were only milliseconds. Match a fresh failed job to its new local diagnostics before attributing its cause.
- The installed local visual model still mislabeled one cinematic sample as gameplay, although it stopped inventing shooting. A dominant-camera controlled sample classified correctly, but the originally reported full-screen-camera interval was not identified. Do not describe visual classification as fully solved.
- The current unidentified reports concern incomplete transcription and full-screen facecam classification. The earlier green-screen task is separate. Identify the actual project/source and original time range before claiming either current case is reproduced or fixed.
- Source footage can contain its own baked captions; the default burned-caption position can overlap those pixels. This validation did not change caption positioning or remove source overlays.
- No production app restart, installer/package publication, or website deployment was performed. Source CI and release/clean-install validation are separate checks.


## Additional local closure validation

Three further defects were fixed locally: visual analysis now follows the selected screen source and synchronization; strict transcription failure messages identify affected original-audio ranges; and live captions now match export phrase boundaries, silence gaps and word-highlight transitions. Coverage gates and source preservation remain unchanged.

The main workspace passed 2,113 Python tests with three skips, followed by 66 relevant checks after the JavaScript caption correction; all 609 frontend tests passed. Actual Hebrew/English browser workflows covered caption edit, save, undo, redo, reopen, playback and CPU export. The 24.5-second and 16.5-second exports fully decoded; preview text or silence matched all 26 checked caption/gap points. These are bounded functional checks, not a human speech-accuracy or AI editorial-quality benchmark.

A fresh extraction of the Windows candidate passed its complete source inventory and checksum checks. Dependencies installed into a new isolated environment using the currently installed official Python 3.13 runtime. Dependency consistency, packaged runtime preflight, real Waitress startup and 68 packaged routing/caption/cache regressions passed. Both real-language editing/export workflows were repeated from the extracted application. This verifies runtime compatibility on the existing Windows machine; it does not claim a clean-machine first installation. The packaged installer still selects Python 3.12, and that bootstrap was not run or bypassed for this check.

The Windows and Mac candidates are local, unpublished review artifacts with identical shared source. Production and historical release baselines and all packaging guards remain intact. Native macOS installation was not tested from Windows. The available native route is the existing macOS 15 Intel/Apple Silicon GitHub workflow, which still requires the new immutable Windows baseline and separately authorized source/release staging before candidate validation. No remote publication or CI dispatch was performed in this closure pass.


## Fresh Windows speech-runtime findings

A clean dependency installation exposed a reproducible failure before speech decoding: PyAV 19 removed the `metadata_errors` argument still used by faster-whisper 1.2.1. The Mac constraints already excluded that version; the common requirements now apply the same compatible PyAV range. Runtime preflight also decodes a short in-memory WAV through the actual Whisper media reader without loading a model, so successful imports alone cannot declare this broken decoder ready.

Official Store Python 3.13 also failed to find the installed CUDA BLAS libraries through PATH. Both CTranslate2 4.8.2 and 4.8.1 reproduced that failure; changing versions alone did not repair it. Explicit Windows DLL-directory registration resolved it. CUDA model loading now registers the known installed Ollama CUDA directories, retains their handles for inference and skips CPU/non-Windows execution. Windows dependencies select the verified CTranslate2 4.8.1 wheel for reproducibility, not as the DLL fix.

After explicit GPU coordination, the two authorized 180-second clips freshly passed CUDA/float16 inference with the registration mechanism in an isolated source copy: English turbo 6/6 chunks in 4.73s; Hebrew ivrit-ai turbo 6/6 in 7.94s. The strict coverage gate passed without fallback. Workers exited and GPU ownership was released immediately afterward; final integration and package work remained CPU-only. These timings exclude preflight waits and are not portable performance or word-accuracy claims. The final registration helper adds validated path checks and deduplication around the same successful mechanism; those are covered by CPU regressions.
