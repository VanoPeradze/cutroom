# Models in CUTROOM

Checked against code/defaults on 2026-09-12. These are choices, **not models all loaded together or bundled in the ZIP**. A developer's installed models do not transfer to testers.

## Speech

| Model | When used | Role |
| --- | --- | --- |
| Whisper `base` | Lite; Auto on CPU, subject to recovery/resource rules | Light multilingual transcription. |
| Whisper `small` | Balanced; Auto with CUDA, subject to memory checks | Heavier multilingual transcription; also used by relevant recovery paths. |
| Whisper `turbo` | General Quality transcription | Faster large-v3 variant through CTranslate2. |
| `ivrit-ai/whisper-large-v3-turbo-ct2` | Quality with Hebrew selected; Quality auto-detection may refine Hebrew | Hebrew-specific transcription. |
| Silero VAD | Decoding uses `vad_filter=True` | Speech activity detection, not story selection. |

The installed faster-whisper alias map resolves base/small to `Systran/faster-whisper-base` / `Systran/faster-whisper-small`, and turbo to `mobiuslabsgmbh/faster-whisper-large-v3-turbo`. Dependency updates may change aliases; record actual model metadata for comparisons.

This pipeline **transcribes**, not a complete cross-language subtitle translation workflow. Whisper documents language-dependent accuracy; Turbo is not trained for translation. Whisper code and weights use MIT. [Whisper documentation](https://github.com/openai/whisper)

The ivrit.ai model card lists Apache-2.0. faster-whisper and CTranslate2 are inference engines, not extra editorial models. Silero is faster-whisper's small speech detector. [ivrit.ai](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2), [faster-whisper](https://github.com/SYSTRAN/faster-whisper), [Silero](https://github.com/snakers4/silero-vad)

## Story planning

| Ollama tag | Default role | Approximate download |
| --- | --- | --- |
| `qwen3.5:4b` | Normal choice / missing-model recommendation | 3.4 GB |
| `qwen3.5:2b` | Preferred in explicit Lite **if installed** | 2.7 GB |
| `qwen3.5:9b` | Preferred in Quality **if installed**; also fallback | 6.6 GB |
| `qwen3:8b` | Additional installed-model fallback | Depends on tag/quantization; not required. |

These catalog sizes are downloads, not RAM/VRAM requirements. Context and inference need additional memory. Qwen3.5 model cards list Apache-2.0. [Ollama catalog](https://ollama.com/library/qwen3.5), [4B card](https://huggingface.co/Qwen/Qwen3.5-4B), [9B card](https://huggingface.co/Qwen/Qwen3.5-9B)

Selection follows preference order among compatible installed tags. Quality can use 4B when 9B is missing; Lite can use 4B when 2B is missing. Switching mode does not install its preferred model. You do not need every model.

Ollama is the local runtime, not the model. CUTROOM attempts to start it automatically, without downloading or warming models just because the app opens. Semantic drafts need a ready compatible model. Default chronological YouTube cleanup does not require Story AI.

Although Qwen3.5 supports images, **CUTROOM currently sends transcript/story data, not full video understanding**. Swapping a tag does not make it recognize gameplay events visually.

## Camera detection and other processing

OpenCV loads three pretrained Haar classifiers:

- `haarcascade_frontalface_default.xml`
- `haarcascade_frontalface_alt2.xml`
- `haarcascade_profileface.xml`

They propose face/embedded-camera regions from sampled frames. They are not identity recognition, reliable tracking or a video-language model. Confirm proposals manually.

FFmpeg/FFprobe, audio-level analysis, synchronization, timeline edits and most layout logic are rules/signal processing, not additional AI models. No generative-video, music-generation, voice-cloning, dedicated translation or frame-interpolation model is included.

## What is worth changing?

These are **evaluation recommendations, not measured CUTROOM improvements**. No models were replaced for this package.

1. **Keep defaults for the first beta.** Get comparable footage and feedback before increasing everyone's memory and download requirements.
2. **Compare the supported Story 4B and 9B**, using the same corrected transcript and brief. Score useful moments, coverage, repetition, lost meaning and human correction time. More capacity may help reasoning but cannot recover speech missing from the transcript.
3. **Compare Hebrew Quality (ivrit.ai) against Small** on consented clean/noisy and mixed Hebrew/English recordings. Measure WER/CER plus correction time before claiming language parity. [Evaluation procedure](TRANSCRIPT_EVALUATION.md)
4. **Consider Whisper large-v3 as a quality experiment, not a default swap.** Upstream describes Turbo as a faster large-v3 derivative with an accuracy/speed tradeoff. The benefit on our footage still needs measurement. [Whisper models](https://github.com/openai/whisper#available-models-and-languages)
5. **Do not replace multilingual speech recognition with an English-only model for everybody.** Distil-Whisper large-v3.5 is English-focused, not a Hebrew upgrade. [Model card](https://huggingface.co/distil-whisper/distil-large-v3.5)
6. **Evaluate camera detection separately.** Haar detection is a replacement candidate if beta footage shows systematic misses. Check licensing, CPU cost and false positives, and preserve manual correction.

Speech quality, Story quality, timing and usability are different measurements. Regression tests do not certify them. See [third-party notices](THIRD_PARTY_NOTICES.md).
