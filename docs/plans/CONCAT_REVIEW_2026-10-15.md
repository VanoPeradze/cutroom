# Concat review: what CUTROOM can learn from it (2026-10-15)

Source reviewed: [jub0t/Concat](https://github.com/jub0t/Concat) at `cda4abc` (15 October 2026), version 0.2.7. Concat is a Rust desktop editor (Slint UI, its own render, speech, vision and export crates) that describes itself as a free CapCut replacement.

## License boundary

Concat is **AGPL-3.0-or-later**, and CUTROOM is MIT. Copying Concat code, or close translations of it, would put CUTROOM under AGPL obligations. Nothing from Concat was copied into CUTROOM. The ideas below are general editing practice and were written independently against CUTROOM's own code and tests.

## Ideas worth taking

| Idea in Concat | Where in Concat | What it would mean in CUTROOM | Status |
|---|---|---|---|
| Captions are cut into readable lines by length, not only by word count | `concat/src/panes/captions.rs` | A caption without word timing used to be one block of any length, and the export check warned about lines over 84 characters. | **Done in 1.2.** Captions over 84 characters split at word boundaries, with time shared by character count (`cutroom/caption_items.py`, `web/app.js`). |
| Captions from a typed script, timed at about 14 characters a second | `captions.rs` (`script_captions`) | Creators who script a voiceover could paste the script and get timed captions to adjust, without transcription. | Candidate. Fits the existing custom-caption layer and the SRT import limits. |
| Model manifest with a pinned SHA-256 per file, its own mirror and an upstream fallback; a download without a digest is refused | `models/manifest.toml`, `scripts/models.py` | CUTROOM's local models come from Ollama and Hugging Face by tag. Pinning a revision and checking a digest would make "the model we tested" reproducible. | Candidate. Needs a decision on hosting mirrors (storage and licences of each model). |
| Local server token: every connection, loopback included, presents a 128-bit token compared in constant time | `concat-server/src/lib.rs` | CUTROOM already rejects foreign Host, Origin and Sec-Fetch headers (`server.py`). A token would also stop other local programs from calling the API. | Candidate for a security pass. Changes the launcher-to-browser handoff, so it needs its own design and tests. |
| A text preset library that includes lower thirds and is filtered by script (Latin, Hebrew, Japanese and others) | `concat/src/presets.rs` | Matches CUTROOM's new templates. | Done in 1.2 in CUTROOM's own form (Lower third, Chapter card, Callout, Highlight). |
| A voice-cleanup chain: an 80 Hz high-pass plus a gentle cut around 300 Hz | `concat-media/src/audio.rs` | A one-click cleanup on the Original channel for room rumble. | Candidate. Small FFmpeg filter, but needs a listening check on real voices. |
| The audio mix is described once as a filter graph and rendered from that description | `concat-media/src/audio.rs` (`mix_graph`) | CUTROOM's preview now follows export normalization (1.2), but the preview still rebuilds the mix in WebAudio. | Partly done. Full parity would need a shared description of the mix that both sides read. |
| Keyframed properties and text-to-speech | `concat-project`, `concat-speech` | Keyframes are a larger feature; TTS adds model, voice and licence questions. | Not planned now. |

## Not a fit

- Concat's native Rust architecture, GPU renderer and Slint UI. Replacing CUTROOM's Flask and browser stack would be a rewrite that the brief rules out without an explicit decision.
- Its contributor licence agreement and trademark terms apply to Concat contributions, not to CUTROOM.

## Recommendation

Next, in order: (1) captions from a typed script, (2) a pinned model manifest for the transcription models, (3) the local API token as part of a security pass. Each is a separate change with its own tests, and none needs Concat code.
