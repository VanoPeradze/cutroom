# Stage 3 — AI reliability for talk and gameplay (2026-10-14)

Branch `claude/stage3-ai-20261014`, stacked on Stage 2.
State: **local source only**. Not built, installed or published.
Hardware/software: Windows 10 22H2, RTX 4070 Ti SUPER 16 GB, Python 3.11.9, FFmpeg 7.1.1, Ollama with `qwen3.5:4b`, faster-whisper with `ivrit-ai/whisper-large-v3-turbo-ct2` (CUDA float16). Runs used isolated data (`%TEMP%\cr-ai`, port 8769; fixture port 8766). Private recordings were used only locally, through the hard-linked lab copies. No transcript text, frames or descriptions from them are in this repository.

## 1. Why a Short came out half as long (Stage 0, item 3)

**Measured first.** Every Short draft now records its length after each step in `draft.duration_review.chain`:

- the requested length
- planner passages
- relevant top-up
- story selection, or gameplay moments / audio highlights
- after removing pauses
- after removing dead screens
- after trimming to length
- after dropping tiny fragments
- final

When a draft is short, the notice in the editor shows the chain ("Length at each step: requested 180s → …").

**Cause found.** For a 180 s Stream Story request on the 27-minute gameplay lab recording, the chain showed the whole loss in selection: the story planner returned 5 passages (89.8 s), and the style path returned them unchanged. Pause cleanup removed nothing.

**Fix.** Only in "Highlight sequence — aim for this length" mode, after the planner's passages, the director adds the strongest remaining complete story beats with their context. A beat qualifies only if all of these hold:

- its relevance is at or above the median of all candidates
- it does not overlap or touch a chosen passage (1 s margin)
- adding it does not push the edit past the target

It stops at 95% of the target. No passage is repeated and no low-relevance filler is added. "Follow style" mode is unchanged.

**Result on the same recording:** 89.8 s became **171.4 s** (planner 89.8 s, plus 4 beats, gives 173.2 s; 171.4 s after pause cleanup). This measures length, not editorial quality: whether the added beats read well together has not been reviewed by a person.

## 2. Speech detected but not transcribed (Stage 0, item 4)

A 30-second unit whose VAD heard at least 8 s of speech, of which the decode transcribed under 35%, is decoded once more without VAD (same loaded model, deterministic, at most 24 units per recording; Lite mode skips it). The first decode's text is always kept. The retry only adds new segments that fall in its silent stretches and pass these filters:

- not marked as no-speech with low confidence
- average log-probability not below −1.5
- not repeated three or more times

The unit's VAD evidence stays as measured, and the attempt is recorded in `quality_recovery.vad_gap`.

**Honest result on the reproduced case** (2-hour Hebrew lab recording, unit 4800–4830 s: VAD 23.3 s, transcribed 4.6 s):

- The retry ran in 1.7 s. It found 1.0 s more, below the acceptance bar, so the original was kept.
- A 60-second window with context gave 7.2 s (VAD on) and 6.4 s (VAD off) inside that unit.
- The loud part (15–30 s, −23 to −26 dB RMS) produced no text in any mode. It is most likely game audio or music that VAD reacted to.

The Stage 0 note that a decode without VAD "recovered the speech" does not hold up and is corrected here. The existing warning (`minor_uncovered_speech`) still names such ranges for review.

## 3. A camera feed read as a fight (Stage 0, item 5)

**Prompt change tested and rejected.** I asked the same vision model an extra "recorded view" question on known windows of the lab recording:

| Window | Ground truth (frames checked locally) | Wording 1 | Wording 2 (strict) |
|---|---|---|---|
| 537 s, 545 s | Surveillance feed with timestamp overlay | recorded ✔ ✔ | missed ✘ ✘ |
| 100 s, 300 s, 565 s | Live third-person play (webcam box, tutorial pop-ups) | recorded ✘ ✘ ✘ | correct |

The 4B model swings between over- and under-firing, so no prompt change was shipped.

**What shipped: user correction plus "uncertain".**

- Gameplay drafts now list their moments (`draft.gameplay_moments`) in **Edit → AI suggestions**, with the time range and the model's short description. Clicking a row seeks to it.
- A moment is marked **Uncertain** when no analyzed window covers it, its main screen is not gameplay, or its action evidence is under 0.25.
- **Not live gameplay** stores a correction (`manual.visual_overrides`, an undoable project edit, kept on reopen). The next rebuild treats that range as non-interactive. The cached model answers are not changed, and **Undo mark** removes the correction.
- After marking, a **Rebuild Draft** button appears in the same block.
- Browser check on the lab recording (180 s gameplay draft): the moment containing the camera feed (08:59–09:20) was in the draft. After marking it and rebuilding, it was gone, other moments filled the time (two of them correctly marked Uncertain), and the draft was still 180 s.

## Tests

- Python: `test_bilingual_transcription_quality.py` (VAD-gap recovery, rejection of invented or repeated text, budget and Lite, no-VAD parameters), `test_style_story_selection.py` (top-up), `test_director_rebuild_cache.py` (duration chain in a real draft), `test_visual_moments.py` (corrections, uncertain moments, undoable edits).
- Node: the existing 617 frontend tests.

## Not done in Stage 3 (next decisions)

1. A full-screen facecam read as gameplay (Stage 0 item 6) is still not reproduced; it needs a sample recording.
2. Talk flow: the story path's coherence problems from Stage 0 (an opening without its setup, a 1.7 s fragment, an invented title, a failed continuity check) were not re-evaluated against a labelled set. `codex/focused-short-v6-wip` was not compared. This needs a labelled Hebrew/English talking sample and a person's judgment.
3. Sentence cuts mid-way (Stage 0 item 8) were not checked word by word.
4. The top-up was measured for length only.
5. Like Stages 1–2, merging needs a newly pinned Windows baseline for macOS CI (a staging deployment that needs your approval).
