# CUTROOM qualification summary

Status: **NO-GO for promoting the current public download. PR #89 remains draft.**
Source tests, package identity, native installation and human editorial acceptance
are separate requirements. Publication alone does not establish quality.

## Published 1.2 release

The current public prerelease is
[v1.2-beta-20261015](https://github.com/VanoPeradze/cutroom/releases/tag/v1.2-beta-20261015),
published 15 October 2026 at 15:14:11 UTC. The landing page still selects these
assets. Their identities were rechecked on 18 October:

| Archive | Bytes | SHA-256 |
| --- | ---: | --- |
| Windows | 3,581,242 | `41c76f17aa30ae425692dcb6b013b374d2a67d1d25b732c61cf9dd0bf5be94f3` |
| Mac | 3,592,637 | `5c7be082218fe28e57748460aeaeb0e6740ecda40d509bfe5ad3d98bf059be22` |
| Combined | 7,195,525 | `17857919c2315cfe01db2e6c6695220cc8949c7759cf66860672e4df5ea3811b` |

Those packages contain earlier source. New source or candidate checks do not
qualify the existing public downloads.

The historical [1.2 beta status](../BETA_STATUS.md) records caption-item editing,
mixer/limiter, Short length top-up, gameplay labels, text and export changes,
with 2,162 Python and 617 frontend checks and synthetic browser coverage. Those
reported checks do not establish representative human listening or native Mac
acceptance.

## Source changes under review

- Retain complete canonical ASR utterances, negations, qualifications and speech
  handles. Summaries quote retained source verbatim. Attribution and retention
  do not prove semantic understanding or repair inaccurate transcription.
- Require explicit source evidence for every planned role and required context
  chapter. Reject incomplete assignments and duplicate JSON keys without
  heuristic recovery. Precision refusal preserves the existing edit and cannot
  enter extractive fallback. Later semantic review remains mandatory.
- Offer a default-off Short-only extractive rough cut after an eligible later
  review failure with critic-qualified fixed source. It remains visibly marked
  `not_model_reviewed`, `generative_approved=false` and `requires_review`.
  It cannot restore excluded footage, repeat, pad or slow footage to force a fit.
- Correct the caption ownership documentation: saved changes follow surviving
  source speech in the original clip across trimming and reordering.
- Harden Windows stabilization publication at long temporary paths while
  preserving atomic no-overwrite publication, cancellation and owned cleanup.
- Align three stale required-test references with the current, stricter critic
  contracts. Keep all 50 requirements, selectors and report validation intact;
  check required names against their selected test sources to prevent drift.

## Validation

| Check | Recorded outcome |
| --- | --- |
| Final frozen source regression | 2,729 Python passes, two expected Windows platform skips; 623 frontend passes |
| Earlier precision and compatibility regressions | 468 passed |
| Earlier standalone hierarchical smoke | Passed with simulated model responses and real source/duration validators |
| Offline candidate identity | Final source, Windows and combined archives verified; unpublished review only |
| Earlier Windows runtime | Cached-dependency setup, manual editing, captioned export and restart passed; setup and launchers unchanged in final pair; not clean-PC acceptance |
| Windows stabilization path regressions | Four native cases passed in the final full suite; all 36 stabilization cases retained across two modules |
| Previous required extracted-feature gate | 330 passed, one failed, zero skipped |
| Intermediate extracted-feature gate | 344 tests passed; report gate failed on three stale required-test references, corrected in the final source |
| Final matching extracted-feature gate | 340 passed, all 50 required cases validated, zero skipped, deselected or expected failures |

The final review source is `fe35453119305a33e0890a25e627a4fa47ad353d`.
Its [explicit provenance record](../../packaging/review-candidates/fe35453.json)
pins all 389 source files and the exact Windows and combined ZIPs. The complete
suite collected 2,731 cases across 128 Python test modules, without deselections
or expected failures. Frontend and focused counts overlap this suite.

The four native Windows regressions retain the original fixture, test bodies
and assertions in a separate full-suite module. Nine portable path cases remain
in the shared feature selection, keeping Windows-only skips out of the native
Mac feature gate. This organization does not establish native Mac execution.

The previous extracted-feature failure was a reproducible Windows filesystem
boundary: valid stabilized output could not be published when the generated
temporary path reached 260 UTF-16 units. The final gate passed with the original
geometry and unchanged selectors/report validation. This was Windows execution
of the combined ZIP's extracted Mac App; it does not establish native macOS
acceptance. Shortening the test path was not used to obtain a pass.

Package checks verify exact source and manifest identities, the complete payload
inventory, fresh defaults, privacy exclusions, permissions and platform overlays.
The independent review gate does not replace the approved native release gate or
make private local archives available to CI. Public and historical release pins
remain unchanged.

The regression counts overlap and must not be added together. Simulated provider
responses, source retention and a successful synthetic render do not establish
fresh generative editing quality.

## Remaining release gates

1. Complete exact-candidate native Mac Apple Silicon/Intel setup, restart,
   export and transcription checks. Existing native CI still selects an older
   approved baseline; source-only passes are not current-package acceptance.
2. Resolve the separate CI-only `tiny.en` download approval. No new model
   download is authorized by source validation or Git synchronization.
3. Obtain fresh accepted Hebrew generative planning under unchanged source,
   exclusion, order and duration rules before claiming that capability.
   Extractive rough-cut review is a separate, narrower result.
4. Complete clean-device Windows and physical Mac/browser acceptance, plus
   representative speech, caption, mixer and timeline listening/editing review.
   Follow [the manual protocol](../../packaging/REVIEW_ACCEPTANCE.md).

Private recordings, transcripts, project details and raw diagnostic evidence are
not published in this summary. No release, archive upload, approved-pin update
or preview/production deployment is part of this qualification update.
