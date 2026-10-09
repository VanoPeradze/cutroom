# Editor and analysis quality handoff — 2026-10-09

## Resulting behavior

- Transcription coverage now uses the selected imported audio stream's finite, positive duration. A longer video/container tail no longer makes fully decoded audio look incomplete. Missing or invalid audio metadata still requires coverage of the container; the last spoken word never defines completion. Timeline and export duration remain based on the video. The source cache fingerprint includes audio duration.
- A rejected transcription retains per-attempt quality, model/device, coverage, and worker failure diagnostics under the project's local `analysis-diagnostics/` directory. Native return code, traceback, stderr tail, and last progress survive temporary-worker cleanup. The existing completeness gate remains strict, and failures do not replace saved analysis, drafts, or manual edits.
- Setup follows media → source confirmation → goal → style/format/length → optional AI settings → readiness → start. Existing format/language/profile/visual-AI controls move between setup and editor without duplicate IDs or lost handlers. Camera controls adapt to their actual container width; compact editor columns and navigation-height calculations prevent overflow.
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
- The reordered setup and responsive controls do not, by themselves, prove that the user's unidentified green-screen case is fixed. Identify the actual project/source and reproduce preview, layer order, persistence, and export for that case.
- Source footage can contain its own baked captions; the default burned-caption position can overlap those pixels. This validation did not change caption positioning or remove source overlays.
- No production app restart, installer/package publication, or website deployment was performed. Source CI and release/clean-install validation are separate checks.
