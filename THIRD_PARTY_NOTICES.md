# Third-party notices

CUTROOM AI is distributed under the MIT License. It can interoperate with the following separately licensed open-source projects and models:

- FFmpeg and FFprobe — media decoding, analysis and rendering. Burned captions use FFmpeg's ASS/libass filter when enabled. FFmpeg builds may use LGPL or GPL terms depending on enabled components.
- Flask, Werkzeug and Waitress — local web server components.
- NumPy — audio synchronization and signal processing.
- faster-whisper and CTranslate2 — local Whisper inference.
- Silero VAD — speech activity detection through faster-whisper; MIT licensed upstream.
- OpenCV — optional local face and embedded-camera detection.
- Ollama — local model runtime.
- Qwen-family models — optional editorial reasoning through Ollama; model-specific license terms apply to the model selected by the user.
- OpenAI Whisper model weights — transcription; review the model card and license before redistribution.
- uv by Astral — checksum-verified Windows bootstrap and private Python runtime management; dual-licensed under MIT or Apache-2.0.

CUTROOM does not bundle Python, uv, FFmpeg, Ollama or model weights inside this source ZIP. Setup scripts obtain them from their respective distributors. Redistributors are responsible for preserving applicable notices and complying with the licenses of the exact binaries and models they ship.

## ivrit.ai Hebrew Whisper Large v3 Turbo CT2

- Purpose: optional enhanced Hebrew transcription in CUTROOM Quality mode / suitable GPU-assisted runs.
- Runtime model: `ivrit-ai/whisper-large-v3-turbo-ct2`.
- License: Apache License 2.0 according to the upstream model card.
- Model weights are not bundled in the CUTROOM ZIP; faster-whisper downloads them on first use when selected.

See [the model inventory](docs/MODELS.md) for configured tags and upstream sources. The MIT-licensed CUTROOM source is included in this private beta; this does not relicense third-party tools or weights.
