# Caption, AI selection and runtime repair validation (2026-10-16)

Status: **source repair for review; not a release or a promotion approval**.
The repair branch incorporates master `46dd8ed`, including the concurrent merges
of dependency PRs #79 and #80. It preserves the existing published package pins.
The initial checks below describe `9250601`; the completion follow-up records
later source changes and validation separately.

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
- The subsequent private 45-second HE/EN ASR/Story and encoded checks described
  below supersede the initial lack of fresh inference. They do not establish
  sentence completeness, factual fidelity, setup/payoff or listening quality.
  Visual AI remained off, and no human editorial acceptance was performed.
- No fresh Mac installation or native Mac inference was performed locally.
- The published `v1.2-beta-20261015` package still contains source `0a67e3c`, not
  this repair. Existing package verification cannot be reused as validation of
  this changed source. Package source-identity guards must remain intact.
- No release, website deployment or promotion was authorized by this validation.

## Grounded target-duration completion follow-up

The first bounded fresh evaluation on `9250601` requested 20-second edits from
two private 45-second excerpts. English produced 6.00 seconds after a genuine
first Story attempt failed the minimum-two-beat gate; Hebrew produced 8.39
seconds. Both outputs required review. Processing 45/45 seconds is decoder
coverage, not proof that ASR recognized all speech. These were existing local
EN/HE Turbo snapshots, CUDA float16 and loopback Qwen3.5:4b, with Hugging Face
offline, cloud mode local and visual AI off. No uploads or model downloads ran.

The new completion repair is committed in `62e841f`:

- English's approved 21.09-second passage was discarded as a whole before the
  target enforcer saw it. Fitting now shortens only internal timestamped speech
  gaps before that filter. It retains every protected word and passage endpoint,
  honors exclusions and avoids action-protected styles. Incomplete timing,
  malformed words and legacy text/word-label mismatches protect the full segment.
- Short targets expose smaller choices at complete source-sentence boundaries.
  Unfinished continuations remain indivisible. A continuation exceeding 90
  seconds without a safe sentence boundary fails explicitly before model calls;
  grouping tokenization remains linear.
- Budget fitting searches a bounded set of the same approved slot alternatives,
  including a replacement that fits 17 + 3 seconds rather than stranding the
  selection at 3 + 3. It checks the actual target even inside planning headroom.
  Critic-requested context is retained as a requirement. Missing primary material
  or any required context marks the slot unresolved and invalidates a critic pass.
- Model-approved material cannot be expanded by an unreviewed median-score top-up
  or by restoring the entire short source. Cache contracts change with the new
  beat identities and selection behavior.
- Saved duration diagnostics identify what the **current selection** supports,
  missing requirements, unresolved slots and unapplied critic actions. Both job
  completion and UI explicitly report a target shortfall or unresolved story,
  including unresolved requirements when the numeric duration is met. A style
  maximum is distinguished from a requested target. No global achievable-maximum
  claim is made.

The frozen code passed **546 integrated Python tests**, with zero failures,
errors or skips, plus **131 related frontend tests**. This includes the earlier
caption/timeline/API/history/lock/runtime modules, new completion regressions and
job reliability. The source was unchanged throughout verification:

| File | SHA-256 |
|---|---|
| `cutroom/director.py` | `27a4cfb030b158d11cb3d37754088641b389017ad43f7842ef0cb443d7b4d492` |
| `cutroom/intelligence.py` | `f0f6a7d73e48944e9ab230607826504fa5910a5c7170bd485acaa3569d3cfe84` |

A deterministic replay of the actual earlier English model decision now retains
all 17.74 seconds of timed speech and fits its 27.09 seconds of approved footage
to **20.000 seconds**, with zero rejected overlap. The old two unresolved slots
still produce `limited`; duration repair does not imply a complete story. The
Hebrew replay retains the critic's 33-second required combination (28.7 seconds
of protected speech) as a planning requirement. It cannot safely fit that
combination to 20 seconds; the resulting 8.39-second selection explicitly reports
the omitted required beat, unapplied addition and insufficient safe pause budget.
Neither replay made model calls or establishes an editorial acceptance pass.

Exactly one further fresh ASR/Story pass per language was then run on independent
copies of the same immutable 45-second excerpts, without retries:

| Fresh check | English | Hebrew |
|---|---:|---:|
| ASR segments / words | 13 / 72 | 8 / 70 |
| Local Story calls | 5 | 5 |
| Draft duration / target | 8.34 / 20 seconds | 15.31 / 20 seconds |
| Critic verdict / feasibility | `revise` / `limited` | `revise` / `limited` |

These results remain **editorial acceptance failures**. In English the reviewed
selection plus critic addition contained 28.73 seconds of source ranges (29.43
seconds with planning bridges), including 19.74 seconds of timed speech. Its
minimum under the 60-millisecond speech-handle policy was 21.46 seconds, so the
remaining pause budget could not preserve those handles. The downstream style filter kept
8.34 seconds; the final diagnostic explicitly names two omitted required beats,
one unapplied critic addition and insufficient safe pause budget. The earlier
27.09-second decision excluded another 2.34-second beat, which is why that exact
replay can safely fit 20 seconds. The new fresh result is not proof that the
entire source cannot yield a better 20-second story.

Hebrew's 23.70 seconds of approved source ranges contained 21.08 seconds of
protected speech, with a 21.80-second minimum under the same handle policy.
It retains 15.31 seconds, reports an omitted required beat and insufficient
safe pause budget, and retains a missing-story-anchor warning. These minima apply
only to the current required selection and policy, not every possible story from
the source. Both completion
messages explicitly say that the current selection supports less than the
requested 20 seconds. No successful-ready wording or full-source restoration
substitutes for these limits. Original metadata/media guards and excerpt hashes
remained unchanged.

The fresh outputs were encoded and fully decoded successfully: English
**8.333333 seconds / 250 frames**, Hebrew **15.300 seconds / 459 frames**, both
H264/AAC at 1280×720 and 30 fps. There were no decode errors or measured partial
ASR-word cuts beyond 25 milliseconds. These fresh selections contained no explicit
critic removals, so their zero rejected overlap is not an exclusion stress test;
the deterministic old English replay and controlled regression provide that
evidence. English passed all four technical export checks. Hebrew retains a
loudness warning at **−19.4 LUFS**, with its other three checks passing. Neither
encoding result establishes speech accuracy, complete context or listening
acceptance. Exactly ten local Story calls ran across the two passes; no retries
or further inference followed the final encodes.

The frozen controlled exclusion/empty-pruning regression was repeated through
the real selection and render APIs. It again encoded **20.000 seconds / 600
frames**, kept 0–10 and 20–30 seconds, and excluded 10–20. Decoded frames and audio
confirmed the source jump; selected-audio correlation was 0.999884 versus
0.031723 for the rejected section. The MP4 was byte-identical to the earlier
probe. A subsequent real pruning error preserved project JSON bytes, export
inventory and the prior MP4 hash. ASR/planner/audio/vision were controlled hooks
in this regression; it is separate from fresh inference.

Private reports and QA frames remain in temporary storage. Some footage contains
private facecam/chat context and must not be reused as marketing material.
