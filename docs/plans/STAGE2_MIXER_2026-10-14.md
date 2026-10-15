# Stage 2 — mixer: levels you can trust (2026-10-14)

Branch `claude/stage2-mixer-20261014`, stacked on Stage 1 (`claude/stage1-caption-items-20261014`).
State: **local source only**. Not built, installed or published.
Hardware/software: Windows 10 22H2, Python 3.11.9, Node 24.16.0, FFmpeg 7.1.1, Chromium 155 (Playwright). Isolated fixture server on port 8766 with temporary data; port 8765 unused. Synthetic audio only.

## Decision applied (approved: option A)

Loudness normalization stays on when a Director draft asks for it. Channel faders set the **balance** between tracks before normalization, and **Master** sets the final level after it. The panel says this in words, including when a fader cannot change the exported level.

## Baseline measured before the change

Synthetic source: two loud tones (997 Hz + 3001 Hz), −0.1 dBTP, −4.8 LUFS. Export with the current master:

| Case | Integrated loudness | True peak | Sample rate |
|---|---|---|---|
| No normalization, unity | −5.0 LUFS | **+1.5 dBTP** (clips) | 48 kHz |
| No normalization, Original +6 dB | −1.3 LUFS | **+0.3 dBTP** | 48 kHz |
| Normalized −16, unity | −16.0 LUFS | −9.5 dBTP | **96 kHz** |
| Normalized, Master +6 dB | −10.0 LUFS | −8.0 dBTP | **96 kHz** |
| Normalized, Original −12 dB | −16.0 LUFS (fader has no effect, as designed) | −14.1 dBTP | **96 kHz** |

## What changed

- **Export ceiling (`cutroom/render.py`).** Every export now ends with a limiter at 4× oversampling (−2 dBFS before AAC, about −1 dBTP after it) and returns to 48 kHz. Without normalization the limiter is the last node of the filter graph. With normalization it runs in the second pass: `loudnorm` → Master → ceiling.
- **Preview follows the export (`web/media-studio.js`).** Preview chain: channels → mix → loudness normalizer → Master → meter → preview limiter. Under normalization the normalizer measures K-weighted loudness of the summed mix over a 3 s window and moves the gain toward the target (0.8 s smoothing; silence holds the gain). The first second starts from the analyzed level of the recording.
- **Mixer controls.**
  - Faders move in 0.5 dB steps and show a 0 dB tick.
  - Each channel has a typed value (0.1 dB, clamped to −60…+12).
  - Double-clicking a fader resets it to 0 dB. A Reset button appears where the layout has room.
  - The mouse wheel changes a value only while that control is focused (the existing numeric-scrub contract).
- **Wording.** The panel states whether normalization is on, what faders and Master do, and when only one track is playing (that fader is dimmed). The meter note says the meters show sample peaks of the browser mix before the preview limiter, and that the export keeps true peaks under −1 dBTP.
- **Test fixture.** `tests/preview_editor_workspace.py --normalized` adds a Director-style audio policy. `.claude/launch.json` has a `cutroom-fixture-audio` entry (local only).

## Results after the change

| Check | Result |
|---|---|
| Export, no normalization, unity | −6.0 LUFS, **−1.3 dBTP**, 48 kHz |
| Export, no normalization, Original +6 dB | −2.7 LUFS, **−1.7 dBTP**, 48 kHz |
| Export, normalized −16, unity / Master +6 / Original −12 | −16.0 / −10.0 / −16.0 LUFS; −10.1 / −8.0 / −13.9 dBTP; 48 kHz |
| Preview vs export, normalized (Chromium; preview measured at the real output) | unity −15.84 vs −16.0; Original −12 dB −15.84 vs −16.0; Master −6 dB −21.84 vs −22.0. **Within 0.2 LU** (tolerance set at 1 LU) |
| Mixer controls in the browser | Typing −7.5 moved the fader and saved; double-click reset it to 0 and saved |
| Tests | Full Python suite (exit 0) and 617 Node tests. New: `tests/test_audio_ceiling.py` (three real exports: true peak ≤ −1 dBTP at 48 kHz), plus normalization and mixer-row tests in `frontend_media_studio.test.cjs` |

## Known limits and next decisions

1. The preview normalizer has no lookahead. On speech that starts loud after silence, the first word can be up to about a second off level. The steady-state tolerance above was measured only on a steady tone; music and speech were not measured in the browser.
2. Stereo loudness assumes two channels; surround sources are folded to stereo by the browser.
3. The ceiling turns down extremely loud sources by up to about 1.3 dB relative to before. That is intended (no clipping), but it is audible in an A/B comparison.
4. Normalized exports still encode AAC twice (stage file, then the normalization pass). This is a pre-existing quality cost; a single pass would need a two-pass measurement.
5. A listening check by a person was not done.
6. Merging needs the release step: the macOS CI compares app sources with the pinned Windows baseline, so a new staged Windows ZIP has to be built and pinned before this PR (and Stage 1) can pass. That is a deployment to Expo staging, which needs your approval.

## Reproduce

```bash
.venv/Scripts/python.exe -m pytest -q tests/test_audio_ceiling.py
```

```bash
node --test tests/frontend_media_studio.test.cjs
```
