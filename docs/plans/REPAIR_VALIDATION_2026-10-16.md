# Caption, AI selection and runtime repair validation (2026-10-16)

Status: **source repair for review; not a release or a promotion approval**.
The repair branch incorporates master `46dd8ed`, including the concurrent merges
of dependency PRs #79 and #80. It preserves the existing published package pins.

## Reproduced behavior and resulting changes

### Caption ownership

Two editing-API regressions failed before the repair:

- With the same speech in two clips, edit the second caption to `Second time`,
  then move that clip before the first occurrence. The edit previously followed
  the occurrence number onto the other clip. It now follows its original clip.
- Trim the edited clip past its first spoken word. The public caption ID changes
  from a first-word anchor to a later-word anchor; text and style previously
  disappeared. The edit now follows the surviving source speech.

Private source/clip anchors remap edits independently of public caption IDs.
Splits preserve ownership, duplicates have independent ownership, and fully
trimmed edits remain dormant until that same clip's speech is restored. Undo and
redo include these layers. A replacement source or transcript cannot inherit a
stale caption's text/style through a subsequent edit. The public API excludes
private provenance; export fingerprints include active caption anchors.

Regressions also cover legacy B-audio sync, locked-track independence, no-ops,
reopening projects and a real FFmpeg export of synthetic caption test media.

### AI selection and review

Reproduced failures included critic-rejected footage returning through required
slot recovery, budget fitting, top-up, a bridge between moments, and the
source-shorter-than-target shortcut. Explicit exclusions now survive those
selection paths. A model-provided opening or closing outside the selected beats
can no longer add footage. Explicit manual restores remain the user's authority.

If pruning removes every usable short passage, analysis now fails while keeping
the existing edit and settings, rather than restoring the whole recording.
Requested settings commit with a successful draft; first-draft context caching
uses the same staged settings when checking input identity.

The final review compares the retained speech with the reviewed selection and
reports added, removed and partially retained segments. Word timing distinguishes
removed silence from removed speech. A prior critic pass does not establish
acceptance after the selection changes or required slots become empty.
Over-target output is labelled `over_target`, rather than `near_target`.

Hierarchical story titles use the neutral `CUTROOM story` fallback, with explicit
unverified provenance. Selected source IDs alone do not validate a generated
claim. Legacy hierarchy-less YouTube/cloud title handling is outside this title
guarantee. Review and selection cache contracts were bumped; ASR/chapter context
can still be reused.

### Speech runtime dependencies

The final requirements replace the versions from merged PRs #79/#80 with:

```text
faster-whisper==1.2.1
av>=18.1.0,<19
ctranslate2==4.8.3; sys_platform == "win32"
```

Released faster-whisper 1.2.1 passes `metadata_errors` to `av.open`, an argument
removed by PyAV 19. The upstream fix is not in that release. The Mac constraint
already requires PyAV below 19. The repair therefore restores that compatible
range rather than relying on an unreleased faster-whisper commit.

Windows CTranslate2 4.8.3 supersedes #79's 4.8.2 and includes a CUDA TopK memory
fix. Its official CPython 3.12 wheel was verified against SHA-256
`b5daf0758d522a422c76e53eb02ce9f42465a9aba938a86b27249fb5db2571b9`.
The existing installed runtime was not replaced.

References: [CTranslate2 4.8.3](https://github.com/OpenNMT/CTranslate2/releases/tag/v4.8.3),
[CUDA fix](https://github.com/OpenNMT/CTranslate2/pull/2104),
[PyAV 19](https://github.com/PyAV-Org/PyAV/releases/tag/v19.0.0),
[unreleased faster-whisper compatibility fix](https://github.com/SYSTRAN/faster-whisper/commit/2ce7f9d7a9fbe315a5804a33bf7224d42e101174).

## Completed local validation

One integrated run on the merged repair source passed **503 tests, zero failures,
errors or skips**, using Python 3.12.14, isolated CTranslate2 4.8.3,
faster-whisper 1.2.1 and PyAV 18.1.0:

- 264 caption, timeline, API, undo/redo and track-lock tests.
- 196 Director, selection, critic, context and cache tests.
- 43 decoder-preflight, Windows CUDA registration and Mac setup tests.

The three related frontend editing/sequence/source-track modules also passed
their 90 Node tests. The repository documentation/link check passed.
An additional 162 offline packaging and editor-release tests passed with zero
failures, errors or skips; these exercise validation logic, not a new install.

The decoder preflight includes actual in-memory WAV decoding. The integrated run
did not call ASR, a story model or a cloud provider.

Separately, the same cached `base` model decoded 5.554 seconds of offline
synthetic English speech under CTranslate2 4.8.1 and 4.8.3. CUDA `float16`, CUDA
`int8_float16`, forced CPU `int8` (actual `int8_float32`) and repeated CUDA
load/unload produced the same 14 words and matching word timestamps, then exited
normally. This checks this Windows CPU/CUDA combination, not long-recording or
Hebrew recognition quality. Automatic device-failure fallback was not exercised.

## Existing HE/EN recordings: cached-input replay

Actual local recordings and saved analysis were available. Evaluation reused
copied saved transcript/audio/vision/story inputs; it did not run fresh models or
encode exports. Original project JSON and in-memory inputs remained unchanged.
Twelve baseline/current variants completed, including these duration results:

| Saved input | Available source | Requested | Selected/final replay duration |
|---|---:|---:|---:|
| English gameplay | 1,638.567 s | 180 s | 180 s |
| English gameplay | 1,638.567 s | 90 s | 90 s |
| Hebrew Stream Story | 7,594.017 s | 180 s | 168.1 s |
| Hebrew Stream Story | 7,594.017 s | 90 s | 70.21 s |

The twelve variants are two inputs, two targets and three replay modes: baseline
cached decision, current cached decision, and current reconstruction from recorded
selection IDs. English has no hierarchy, so its third mode repeats the control.
The 90-second scenarios reuse the recorded 180-second model decision. Baseline
selection functions come from `c62b741` and share current supporting helpers;
this is not a comparison of independently installed historical applications.

Selected ranges match the baseline in these recordings. The English gameplay
route has no story critic and is explicitly `not_reviewed`. The Hebrew final
speech review is `changed`, with one removed speech segment for the 180-second
request and seven for the 90-second request; existing continuity warnings remain.
The duration measurements do not demonstrate a coherent or complete story.
The Hebrew cached critic verdict remains `revise`; its 90-second output also
reports a missing story anchor. These saved cases do not exercise explicit
rejection, empty-selection, over-target or empty-slot guards; synthetic regression
cases cover those failures.

Both source files were accessible for read access (English about 2.08 GB, Hebrew
about 8.71 GB). They were not decoded or fully hashed in this replay. Saved
project JSON hashes and the six implementation-file hashes match the report.

## Acceptance boundaries

- Offline verification of the original v1.2 Windows (298 files), Mac (303 files)
  and combined (602 files) archives passes their pinned checksums, sidecars and
  internal checks. A new combined build using the existing local Windows
  baseline exits with `Application source changed since Windows baseline:
  cutroom/caption_items.py`. The independent editor source-agreement check also
  rejects that file. Ten application files differ from the baseline. No repaired
  candidate archive was produced, and no guard or package pin was changed.
- No human-annotated HE/EN reference corpus was supplied, so WER/CER and missed
  speech accuracy remain unmeasured. Existing coverage flags are not ground truth.
- No fresh end-to-end HE/EN ASR/LLM/vision run or final encoded-output review was
  performed for this repair. Sentence completeness, factual fidelity, setup and
  payoff, transitions and listening quality still require review on the output.
- No fresh Mac installation or native Mac inference was performed locally.
- The published `v1.2-beta-20261015` package still contains source `0a67e3c`, not
  this repair. Existing package verification cannot be reused as validation of
  this changed source. Package source-identity guards must remain intact.
- No release, website deployment or promotion was authorized by this validation.
