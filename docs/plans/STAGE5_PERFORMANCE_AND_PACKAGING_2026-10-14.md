# Stage 5 — performance and packaging (2026-10-14)

Branch `claude/stage5-performance-20261014`, stacked on Stage 4.

Machine for every number below: Windows 10 22H2, 24 logical CPUs, 31.1 GB RAM, NVIDIA RTX 4070 Ti SUPER 16 GB. Python 3.11.9 (repo) / 3.12.14 (installed package), FFmpeg 7.1.1, Ollama with `qwen3.5:4b`, faster-whisper with `ivrit-ai/whisper-large-v3-turbo-ct2` (CUDA float16). Private recordings were used only locally, through the lab copies. Nothing was uploaded, published or staged, and port 8765 was not used.

## Measured performance

| Step | Measurement | Result |
|---|---|---|
| Transcription (Hebrew, GPU) | 5-minute slice of the 2-hour lab recording | 6.0 s with the model loaded (0.02× real time); 10.2 s including the first model load. A 2-hour recording takes about 2.5 minutes. |
| Gameplay vision (Ollama) | 10 windows of 8 s, 4 frames each | 0.88 s median per window, 5.3 s for the first (model load); frames 0.19 s, decoded ahead of the model. A fully tiled 27-minute recording takes about 3 minutes; longer ones are sampled within the existing budget. |
| Director (cached analysis) | 180 s draft, 27-minute recording | Stream Story (Story AI): 42 s. Gameplay moments: 3 s. |
| Export, 180 s, 1080p 9:16, burned captions | NVENC vs. CPU | NVENC 43.6 s (4.1× real time) including the export check; CPU x264 153.7 s (1.2×). |
| Export check | Same export | Was 17.6 s (two-thread decode). Now **4.1 s** using all cores. Empty timeline gaps are known exactly from the edit, at no cost. |
| Caption items (Stage 1) | Synthetic 2-hour transcript, 15,000 words, 240 cuts | 74 ms to build after indexing (was 189 ms); 88 ms for the project response, which carries 778 KiB of caption data. |
| Timeline drawing | 1,200 caption items (Node harness, script cost only) | 2.3–2.9 ms per redraw at Fit, 0.8–1.1 ms at 20× zoom; 0.06 ms per click hit-test. |

**Changed in this stage:** the export check now decodes with all cores (the render has already finished) and reports empty timeline gaps exactly from the edit.

## Packaging (local only)

- **Built.** `scripts/build_test_package.py` from this branch (commit `93f97d7`) produced `CUTROOM-1.1-Beta.zip` (3.57 MB). `--verify` passed: 298 files.
- **Installed.** The ZIP was extracted to a short path (`%TEMP%\cr5\pkg`) and `App\setup_windows.ps1` ran without prompts: exit 0 in 46 s, with warm download caches.
- **Launched.**
  - `START CUTROOM.bat` was run with `CUTROOM_PORT=8771` and `CUTROOM_NO_BROWSER=1`.
  - The server answered `/api/instance` and served this branch's assets (`app.js?v=1.1-beta-graphics-3`).
  - It used the private Python 3.12.14 and the data folder inside the test package.
  - It detected NVENC and x264, and the page had no console errors.
  - The test server was then stopped by its PID (verified to be the package's Python).
- **Not done** (each needs your approval as a public step): staging the ZIP on a non-production Expo deploy, pinning `packaging/windows/release-baseline.json` and the combined macOS candidate, macOS CI, merging, building the platform ZIPs, and the production website deploy.

## Status of all stages

| Stage | PR | Local tests | Browser / real data | Built | Installed | Published |
|---|---|---|---|---|---|---|
| 1 Captions as timeline items | #82 | ✔ | ✔ fixture | ✔ (in this ZIP) | ✔ smoke | ✘ |
| 2 Mixer | #83 | ✔ | ✔ fixture | ✔ | ✔ smoke | ✘ |
| 3 AI reliability | #84 | ✔ | ✔ lab | ✔ | ✔ smoke | ✘ |
| 4 Templates and export check | #85 | ✔ | ✔ fixture | ✔ | ✔ smoke | ✘ |
| 5 Performance and packaging | this PR | ✔ | ✔ lab | ✔ | ✔ smoke | ✘ |

GitHub checks: the repository checks, audit and CodeQL pass on #82. The macOS jobs fail by design until a newly pinned Windows baseline includes the new code.

## Known limits and next decisions

1. No measurements yet on a CPU-only or 16 GB machine, on macOS, or with variable-frame-rate sources.
2. The installed test was a smoke test. It did not open a project, run AI or export from the installed copy.
3. The first model load for transcription (~4 s) and vision (~5 s) is paid once per run; keeping models warm between jobs was not explored.
4. Normalized exports still encode audio twice (noted in Stage 2).
5. **Your decision:** approve the staging deploy and pins so the stacked PRs (#82 → #86) can pass macOS CI and be merged, and later the production release.
