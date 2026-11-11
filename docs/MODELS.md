# Models in CUTROOM

Speech policy updated against code on 2026-11-11; other sections retain their existing validation dates. These are choices, **not models all loaded together or bundled in the ZIP**. A developer's installed models do not transfer to testers.

## Speech

| Model | When used | Role |
| --- | --- | --- |
| Whisper `base` | Lite; Auto on CPU, subject to recovery/resource rules | Light multilingual transcription. |
| Whisper `small` | Non-Hebrew Balanced; Auto with CUDA when a cached large model is not suitable | Heavier multilingual transcription; also used by relevant recovery paths. |
| Whisper `turbo` | General Quality transcription | Faster large-v3 variant through CTranslate2. |
| `ivrit-ai/whisper-large-v3-turbo-ct2` | Hebrew Balanced and Quality; both may refine detected Hebrew; bounded Auto refinement when cached and GPU-safe | Hebrew-specific transcription. |
| Silero VAD | Decoding uses `vad_filter=True` | Speech activity detection, not story selection. |

The installed faster-whisper alias map resolves base/small to `Systran/faster-whisper-base` / `Systran/faster-whisper-small`, and turbo to `mobiuslabsgmbh/faster-whisper-large-v3-turbo`. Dependency updates may change aliases; record actual model metadata for comparisons.

This pipeline **transcribes**, not a complete cross-language subtitle translation workflow. Whisper documents language-dependent accuracy; Turbo is not trained for translation. Whisper code and weights use MIT. [Whisper documentation](https://github.com/openai/whisper)

The ivrit.ai model card lists Apache-2.0. faster-whisper and CTranslate2 are inference engines, not extra editorial models. Silero is faster-whisper's small speech detector. [ivrit.ai](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Silero](https://github.com/snakers4/silero-vad)

### Hebrew-first profiles and resource checks (2026-11-11)

**Balanced and Quality use ivrit.ai when Hebrew is selected.** Lite remains Base. With automatic language detection, Balanced starts with multilingual Small and Quality with multilingual Turbo, then may refine detected Hebrew with ivrit.ai. Missing/refused/failed refinement keeps the original transcript and records a warning; the original is not overwritten by an incomplete candidate. Requested and actual model/device, fallback reason, and resource warnings are recorded in `execution` metadata.

**Install the Hebrew model explicitly from Setup > Local models before first use.** Every ivrit.ai load is cache-only, including explicit Quality and refinement. An absent or incomplete cache produces setup instructions, not a hidden model download. The checked model file is 1,617,884,968 bytes (about 1.62 GB decimal); this is not a RAM requirement. Weights are not bundled. Model card license: Apache-2.0. Metadata checked on 2026-11-11 at revision `72ad623a37947395efcc3933132353790e5a12f5`.

Resource checks follow the **actual model**, not the profile name. Large/Turbo/ivrit models require a successful, unambiguous single-GPU measurement of at least 6144 MiB free VRAM (or a higher configured Quality threshold). Unknown, remapped or multiple GPUs use CPU/INT8 instead, with a visible fallback reason, including when CUDA was explicitly configured. A Balanced threshold intended for Small cannot lower the large-model floor. Explicit Balanced/Quality never silently substitute Small for requested Hebrew.

Large-model CPU execution checks available/reclaimable RAM on Windows, macOS and Linux. Known availability below 4096 MiB refuses the operation with instructions to close applications or choose Lite. An unavailable measurement is reported as `cpu_memory_unverified`, not as a passed readiness check. CPU decoding can be much slower. These conservative point-in-time safety floors are **not measured peak requirements or a fit/performance guarantee**; other applications and decode length can change memory use. A CUDA execution error may retry the same model on CPU after the RAM check; cancellation never retries.

Auto keeps its lightweight CPU path. It only upgrades to an already installed large model; if GPU resources fall short, it returns to Small or Base for a long recording rather than loading a large model on CPU. The optional Hebrew second pass requires confident, unambiguous detection (at least 0.62), CUDA, a known duration no longer than `hebrew_auto_gpu_max_seconds` (default 3600 seconds), an installed model, and measured headroom. That optional pass never downloads weights.

An Auto or Balanced refinement candidate must retain recognized English terms, pass the speech-quality gate, have complete and valid source timing, and overlap at least 80% of the original speech duration. All refinements retain the original language-detection confidence. These are safety checks, not proof of lower WER. **Actual Hebrew accuracy, correction time, speed and peak memory have not been measured by these offline routing tests.** Use the [consented transcript evaluation procedure](TRANSCRIPT_EVALUATION.md) before making quality claims.

Cloud-to-local fallback uses a detached settings snapshot with `whisper_local_files_only=True`. Preflight inspects the runtime, the exact local plan's cache and resources without loading a model. Execution checks again, since available memory or cached files can change. No model is downloaded by this fallback. Cloud routing and consent remain a separate choice, not a consequence of choosing a Hebrew model.

## Story planning

| Ollama tag | Default role | Approximate download |
| --- | --- | --- |
| `qwen3.5:4b` | Normal choice / missing-model recommendation | 3.4 GB |
| `qwen3.5:2b` | Preferred in explicit Lite **if installed** | 2.7 GB |
| `qwen3.5:9b` | **Optional upgrade.** Used in Quality when installed, and in Auto when the GPU has room; also fallback | 6.6 GB |
| `qwen3:8b` | Additional installed-model fallback | Depends on tag/quantization; not required. |

These catalog sizes are downloads, not RAM/VRAM requirements. Context and inference need additional memory. Qwen3.5 model cards list Apache-2.0. [Ollama catalog](https://ollama.com/library/qwen3.5), [4B card](https://huggingface.co/Qwen/Qwen3.5-4B), [9B card](https://huggingface.co/Qwen/Qwen3.5-9B)

Selection follows preference order among compatible installed tags. **The 9B model is optional:** without it, Quality runs on 4B as a normal, complete setup (not a "missing model" fallback) and the status offers 9B as an optional upgrade. Lite can use 4B when 2B is missing. Switching mode does not install its preferred model. You do not need every model.

Ollama is the local runtime, not the model. CUTROOM attempts to start it automatically, without downloading or warming models just because the app opens. Semantic drafts need a ready compatible model. Default chronological YouTube cleanup does not require Story AI.

## Gameplay vision

Qwen3.5 Story models also accept images, so **Gameplay vision** uses the Story model you already installed. There is nothing extra to download.

- **What it does:** samples the recording in 8-second windows (Lite 48, Balanced/Auto 120, Quality 200 windows; short recordings are covered completely). Each window becomes one image of four frames. The model answers concrete questions (is a weapon firing, are enemies visible, explosion, damage, downed player, fast movement, and whether the screen is gameplay, a cutscene, a menu/map, loading or a full-screen webcam) plus a short description. CUTROOM computes the action score from those answers.
- **How it is used:** when the windows show a game recording (at least 8 windows, at least 35% gameplay and 60% game screens, under 30% full-screen camera), Shorts in every style except **Stream Story** and **Chill Story** are built from **gameplay moments** without the Story planner. Each 2-second sound bin is scored from its loudness relative to the recording and the nearest window's action; cutscenes, menus and loading screens are scaled down. Peaks grow into moments while the activity lasts, get 2 seconds of context, are snapped to whole spoken phrases (from word timings), and must be mostly gameplay. The strongest moments fill the target in chronological order. On other footage the Story model sees an `on_screen` note for beats with clear evidence (gameplay action, cutscene, menu), and selection favours visible action. No-speech highlights blend it with audio. Reel options gain **Best gameplay action** when it differs from the most intense moment.
- **When it runs:** *Automatic* runs for CUTROOM Smart and the streamer styles on an NVIDIA GPU or Apple Silicon. *On for every Short* runs for any Short on any device; on CPU it uses the Lite window count and can take much longer. *Off* never runs. It never runs with a cloud connection: video frames are never uploaded. A model without image support is skipped.
- **Cost:** on an RTX 4070 Ti Super, 120 windows of a 27-minute 1080p60 recording took about 2 minutes. Results are cached per source and model, and reused by variations and rebuilds.
- **Limits:** a small model is a noisy observer. In testing it mistook an in-game recorded scene for a fight and a full-screen webcam for gameplay. Gaps between sampled windows are inferred from the nearest window. It is evidence for selection, not ground truth; a failure leaves the draft to speech and sound.
- **Correcting it:** gameplay drafts list their moments in **Edit → AI suggestions**. A moment is marked **Uncertain** when no analyzed window covers it, its main screen is not gameplay, or its action evidence is under 0.25. **Not live gameplay** stores a correction in the project (undoable); the next **Rebuild Draft** treats that range as non-interactive. The cached model answers are not changed.

## Camera detection and other processing

OpenCV loads three pretrained Haar classifiers:

- `haarcascade_frontalface_default.xml`
- `haarcascade_frontalface_alt2.xml`
- `haarcascade_profileface.xml`

They propose face/embedded-camera regions from sampled frames. They are not identity recognition, reliable tracking or a video-language model. Confirm proposals manually.

FFmpeg/FFprobe, audio-level analysis, synchronization, timeline edits and most layout logic are rules/signal processing, not additional AI models. No generative-video, music-generation, voice-cloning, dedicated translation or frame-interpolation model is included.

## What is worth changing?

These are **evaluation recommendations, not measured CUTROOM improvements**. The Hebrew Balanced routing change above is a product choice, not an accuracy certification.

1. **Measure the Hebrew-first change.** Compare consented footage and feedback while keeping the Lite alternative and explicit download/resource disclosure.
2. **Compare the supported Story 4B and 9B**, using the same corrected transcript and brief. Score useful moments, coverage, repetition, lost meaning and human correction time. More capacity may help reasoning but cannot recover speech missing from the transcript.
3. **Compare Hebrew Quality (ivrit.ai) against Small** on consented clean/noisy and mixed Hebrew/English recordings. Measure WER/CER plus correction time before claiming language parity. [Evaluation procedure](TRANSCRIPT_EVALUATION.md)
4. **Consider Whisper large-v3 as a quality experiment, not a default swap.** Upstream describes Turbo as a faster large-v3 derivative with an accuracy/speed tradeoff. The benefit on our footage still needs measurement. [Whisper models](https://github.com/openai/whisper#available-models-and-languages)
5. **Do not replace multilingual speech recognition with an English-only model for everybody.** Distil-Whisper large-v3.5 is English-focused, not a Hebrew upgrade. [Model card](https://huggingface.co/distil-whisper/distil-large-v3.5)
6. **Evaluate camera detection separately.** Haar detection is a replacement candidate if beta footage shows systematic misses. Check licensing, CPU cost and false positives, and preserve manual correction.

Speech quality, Story quality, timing and usability are different measurements. Regression tests do not certify them. See [third-party notices](THIRD_PARTY_NOTICES.md).
