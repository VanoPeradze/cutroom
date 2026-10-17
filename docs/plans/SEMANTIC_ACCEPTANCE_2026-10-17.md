# CUTROOM release readiness and semantic acceptance (2026-10-17)

Status: **NO-GO for promoting the current download. PR #89 remains draft.**
This report separates historical release evidence from later source repairs and
from the last bounded local acceptance experiment. Publication is not human QA.

## Claude handoff and published 1.2

No supported Claude/Anthropic conversation or app tool was available. No message
was sent to Claude. The audit used local handoffs, commits, stage reports and
release metadata; the October 9 handoff describes earlier Codex work and is not
Claude's 1.2 acceptance result.

The 1.2 feature commits attribute Claude Opus 5.5 as co-author: caption items
(`4dbaece`), mixer/limiter (`5835aa7`, `e7418f3`), Short length top-up (`090d680`),
gameplay corrections (`cc0617c`), graphics/export checks (`2af2e4d`), performance
(`93f97d7`), long-caption splitting/single audio encoding (`db466eb`) and release
preparation (`75a70fb`, `0a67e3c`, `1af4aaa`). These are documentary attributions.

The [1.2 beta status](../BETA_STATUS.md) records 2,162 Python and 617 frontend
tests passing on Windows, synthetic browser checks and private local AI
experiments. These are historical reported results, not tests rerun by this
audit. Python tests can include frontend wrappers. The later Windows baseline
records setup and synthetic installed-app export at `75a70fb`; `0a67e3c` only
changes an audio test, so the app payload agrees. This is not clean-machine QA.

The same reports explicitly leave story coherence, word-by-word sentence cuts,
editorial quality of top-up, human mixer listening, full-screen facecam
classification, CPU-only/16 GB systems, VFR and native/manual platform coverage
unverified. See [Stage 2](STAGE2_MIXER_2026-10-14.md) and
[Stage 3](STAGE3_AI_RELIABILITY_2026-10-14.md).

The public prerelease is
[v1.2-beta-20261015](https://github.com/VanoPeradze/cutroom/releases/tag/v1.2-beta-20261015),
published **2026-10-15 15:14:11 UTC**, targeting
`0a67e3ce56224aa3e6d12f2179ccbd4b889e9bed`. A read-only GitHub refresh on October 17
still reported the following ZIP identities, agreeing with the previously
verified local cached archives:

| Archive | Bytes | SHA-256 |
|---|---:|---|
| Windows | 3,581,242 | `41c76f17aa30ae425692dcb6b013b374d2a67d1d25b732c61cf9dd0bf5be94f3` |
| Mac | 3,592,637 | `5c7be082218fe28e57748460aeaeb0e6740ecda40d509bfe5ad3d98bf059be22` |
| Combined | 7,195,525 | `17857919c2315cfe01db2e6c6695220cc8949c7759cf66860672e4df5ea3811b` |

Those ZIPs predate main `d855d8f` and the current semantic repair. Their Director,
intelligence and caption code differ from the repaired source; `story_budget.py`
is absent. New source tests do not qualify these downloads. Local
`website/release.json` still contains 1.1 metadata and cannot establish the 1.2
artifact identity. No website or public archive was changed by this investigation.

## Reviewed source changes

Main `d855d8f` includes the caption ownership, rejected-footage, speech-runtime
and target-completion repairs documented in
[the October 16 repair report](REPAIR_VALIDATION_2026-10-16.md).
The local branch `codex/cutroom-semantic-20261017` additionally contains:

- `6be6d2e`: complete role requirements and conservative source-speech budgeting.
- `8d7825f`: canonical source quotations, selected-source ownership, chronological
  role witnesses and identical evidence checks before applying/caching a draft.
- `f32cf86` / `d9f9ce0`: bounded local thinking experiments and an explicit output
  limit diagnostic. Actual 4,096/6,144-token experiments exhausted output without
  returning JSON. Thinking was subsequently disabled again.
- `1bf4c73`: purpose-keyed final quote selection, with conservative allowed-ending
  constraints; all earlier rejection, speech, completeness and duration guards
  retained.
- `b6889a230127d410cf9cdda5d94dbdc193610cd2`: final choices show exact source wording
  plus the canonical reference. Exact dictionary lookup resolves the unchanged
  evidence IDs. No quote normalization, role reassignment or context promotion
  rescues an invalid response. This is the last tested product source revision.

At the final read-only PR refresh, remote PR #89 still pointed to `6be6d2e`.
The subsequent product commits and this report remain local and have not been
pushed. No additional native suites were started while editorial acceptance is
blocked. The PR's existing CI results therefore cover its older remote head.

The deterministic proof establishes **source attribution and order**, not
semantic entailment. Transcript-based editorial review remains a separate gate.
Invalid requests/results preserve the existing draft and exports. No excluded
footage, repeated footage, slowdown, padding or extra unreviewed top-up was added.

## What actually ran

These results cover different source revisions and must not be combined into a
claim that the final source passed a complete regression run.

| Source | Check | Result |
|---|---|---|
| `6be6d2e` | Complete local Python / frontend | 2,345 passed, 2 expected Windows skips / 620 passed |
| `8d7825f` | Complete local Python | 2,436 passed, 3 failed, 2 expected Windows skips |
| Exact `8d7825f` archive | Only those 3 failed selectors under short Temp paths | 3 passed; not a second full-suite run |
| `8d7825f` | Frontend | 620 passed |
| `b6889a2` changes | Six focused mocked Python modules | 200 passed in 1.36 seconds |

The three complete-run failures occurred with Windows paths exceeding the usual
260-character boundary. They passed from an exact frozen archive with a short
pytest Temp path. The full run also recorded five blocked, unclassified loopback
11434 socket attempts; none reached the local model. Do not describe that run as
having zero attempted model transport. The final focused tests stubbed model
paths and retained transport tripwires; no live inference or ASR was used there.

Native [run 39072515453](https://github.com/VanoPeradze/cutroom/actions/runs/39072515453)
on `6be6d2e` passed 2,342 Python tests with five platform skips and 620 frontend
tests on each architecture. Both jobs then failed the Windows baseline source
guard (`cutroom/caption_items.py` changed). Exact-candidate, install/restart and
transcription stages were skipped. This is not native package validation of the
new source.

## Last bounded real-source experiment

Private isolated copies reused the actual cached English/Hebrew ASR and exactly
five earlier real planning responses. English made one fresh final-review
transport; Hebrew stopped at request-context validation before transport.
Changed upstream prompts were **not** rerun, so this is not a fresh complete
pipeline acceptance result. No ASR, paid service, new model or model download was
used. The existing local model was Qwen3.5:4b through Ollama 0.34.2, with thinking
off, at most one transport attempt, 2,400 output tokens and a 240-second timeout.

The last source revision was frozen before either case. Eight critical files
matched the committed revision, allowing only explicitly recorded CRLF/LF
normalization. Original project JSON hashes, source media size/mtime, copied clip
hashes, inherited exports/sidecars and captured-context hashes stayed unchanged.
Private media and transcripts are not included in the repository.

| Case | Actual result | Acceptance |
|---|---|---|
| English, 45-second source, 20-second target | One fresh final call, 8.359 seconds; new 20.000-second timeline, 3 ranges; source/order/word guards pass | Selected story and primary role sets pass independent transcript review as a narrow chronological disagreement. Summary remains defective: it drops the substantive premise and skeptical/refusal context. No audio listening or new final-source encode claimed. |
| Hebrew, 60-second source, 40-second target | Zero final transports: the unchanged 32,768-token estimated request-context guard rejected the larger text-first request; prior edit/export preserved | `semantic_revision_context_limit`; no accepted new edit. Current approved source has a 38.57-second safe minimum, so duration fits. This is request-size failure, not proof of an impossible target. |

In the preceding `1bf4c73` experiment, English encoded and fully decoded at
20.000 seconds / 600 frames, but its sole primary premise citation was vacuous.
Hebrew's model returned role witnesses out of order inside the same ASR segment;
the guard rejected the result. The final English primary set improved, but the
new summary and Hebrew context failures still prevent combined acceptance. The
older successful encode cannot qualify a different source revision.

The earlier 45-second Hebrew case also lacked a complete required source unit;
that is missing source evidence, not a global duration impossibility. The old
English `no_fit` response was likewise not a demonstrated impossibility: its
allowed selection had a 17.20-second safe minimum for a 20-second target.

All five experiment roots and failed outputs are preserved in private Temp
storage. The last is `cutroom-grounded-choices-eval-20261017-b65ac9ae`, containing
`grounded-summary-numeric.json`, source/commit bindings, preservation reports,
and `editorial-release-gate.json`. The 8d full-suite accounting is in
`cutroom-grounded-frozen-qa-20261017-8d7825f/consolidated-evidence-summary.json`.
The final focused command/result record is
`cutroom-verbatim-choices-focused-tests-20261017-a2328e88.log`.

## Exact promotion blockers

1. Hebrew final-review request construction exceeds its supported context cap;
   the earlier smaller format also failed semantic role order. A valid, complete
   fresh bilingual result remains unproven.
2. The English witness-only summary omits meaningful primary/context evidence;
   selected-source attribution alone does not make that summary adequate.
3. The final source has no complete green regression run or matching reviewed
   Windows/combined candidate, and no successful exact-candidate native Mac run.
4. The current public ZIPs contain older code and lack the subsequent repairs.
5. Representative human speech/editorial listening and native/manual checks
   remain outstanding; historical synthetic exports do not substitute for them.

Further live prompt/budget experiments were stopped after this bounded attempt.
No release pins, distributable ZIPs, production website, original projects or
NOVA tabs/servers/files were changed. PR #89 must remain draft until the semantic,
source, package and human acceptance gates are qualified separately.

## Authorized continuation: summary and request repair (`503dbe5`)

The six follow-up commits through `ff8d533` were checked for concurrent remote
changes, credentials and private transcript content, then fast-forward pushed to
PR #89. GitHub confirmed `ff8d533` as its draft head. The earlier local-only
description above records the previous handoff, not the later push state.

Source `503dbe55d45fa4e9dc7e7519219cab3d5204212d` replaces witness-only summaries
with every cited primary/context source excerpt in chronology. The final
conversion revalidates against retained source and rejects a changed or forged
proof, then preserves complete quotes without the old 500-character cutoff.
No model interpretation or rejected source supplies summary text.

The Hebrew request overflow was duplicate representation, rather than missing
model context capacity: the existing estimate, including the same 2,400-token
output reserve, fell from **34,743 to 17,028** under the unchanged 32,768 cap.
Shared scalar schema definitions and a shared chapter/evidence table preserve
the fully expanded schema exactly. Source units, quotations, instructions,
costs, sticky/rejected IDs, targets and feasibility constraints were unchanged.
English fell from 17,166 to 12,233 estimated tokens. No estimator change,
evidence truncation or inference was used for those measurements.

The final eight-module focused run passed **266 tests in 1.48 seconds**, with
zero network attempts and all nine production-file hashes unchanged. Independent
review confirmed schema/domain equivalence for both actual cached requests.

One fresh local final review per cached case then ran on this frozen source:

- English completed in 8.953 seconds, applied a 20.000-second / three-range
  draft, and passed independent transcript/timing review of both the selected
  dialogue and its complete source-excerpt summary. Its new export fully
  decoded at **20.000 seconds / 600 frames**. Source/order/speech and exact
  source-to-commit binding passed. This is still captured upstream planning,
  not a fresh full pipeline or human listening acceptance.
- Hebrew reached the model and returned JSON in 10.078 seconds. The guard
  correctly rejected all four temporal witnesses because they were outside the
  corresponding selected primary quotations. Independent review additionally
  found that its primary result was an unfinished phrase and acknowledgments,
  without a conclusion proposition. A substantive conclusion exists in retained
  source but was uncited; it was not automatically promoted. The prior edit and
  exports stayed unchanged. The context-limit defect is repaired; Hebrew
  semantic acceptance is still blocked.

Evidence is preserved under private Temp root
`cutroom-compact-summary-eval-20261017-d339a09b`, including the complete numeric
source/encode report and separate editorial gate. Measurements are under
`cutroom-request-domain-audit-20261017-1e6f0d7d`; the final focused run is under
`cutroom-shared-choice-final-focused-20261017-61e33ed`.

The next repair addresses redundant primary/anchor selection and makes actual
ASR sentence boundaries explicit, while retaining canonical attribution,
primary/context meaning, chronology and every existing acceptance guard.
The failed Hebrew response remains a failure. No package/pin or production
change is qualified by this intermediate result; PR #89 remains draft.

