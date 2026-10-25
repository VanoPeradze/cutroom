"""Bounded automatic source-window retrieval, not semantic/grammar evaluation.

Continuous whole-ASR windows; opt-in existing speech-boundary references narrow
entry/exit choices without rewriting rows. Alternatives are independently ranked
for membership/time diversity. Noncontiguous compositions live in the companion
composition search; absence here is NOT global no-fit.
No transcript keywords, invented grammar checks, model, cache IO or application.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, field
import hashlib
from typing import Any, Callable

from .edit_windows import (CanonicalSource, EditWindowError, build_edit_window, compile_selected_spans,
                           _identity, _json)
from .instruction_contract import assert_instruction_contract, effective_duration_bounds, single_output_requested
from .window_evidence import (WindowEvidenceRequest, WindowSourceState, build_canonical_evidence_index,
                              check_source_state, prepare_window_planner_preview, validate_bound_source)

RETRIEVAL_POLICY = "bounded-continuous-window-membership-diversity-v1"
SPEECH_UNIT_POLICY = "source-referenced-speech-boundaries-v1"
RECOVERY_ENTRY_POLICY = "defer-recovery-only-starts-v1"
ENTRY_GROUP_SAMPLING = "source-entry-balanced-rank-stratum-centers-v2"
SPEECH_GAP_SECONDS = .7  # Director's phrase-gap scale, not proof of silence/meaning.
EPSILON = 1e-7  # Matches selected-span numeric checks; no frame/word precision claim.


@dataclass(frozen=True)
class WindowRetrievalPolicy:
    max_source_starts: int = 2048
    max_pairs: int = 16384
    max_endpoints_per_start: int = 8
    shortlist_size: int = 16
    max_view_row_references: int = 4096
    max_view_text_characters: int = 250000
    speech_units: bool = False  # Explicit internal opt-in; numeric control stays reproducible.
    defer_recovery_only_starts: bool = False  # Conservative diagnostics; never a semantic verdict.

    def __post_init__(self) -> None:
        if type(self.speech_units) is not bool:
            raise EditWindowError("speech_units must be an explicit boolean")
        if type(self.defer_recovery_only_starts) is not bool or self.defer_recovery_only_starts and not self.speech_units:
            raise EditWindowError("Recovery-entry deferral requires explicit speech-unit policy")
        for name, maximum in (("max_source_starts", 4096), ("max_pairs", 16384),
                              ("max_endpoints_per_start", 64), ("shortlist_size", 32),
                              ("max_view_row_references", 16384), ("max_view_text_characters", 1000000)):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise EditWindowError(name + " exceeds bounded retrieval policy")


@dataclass(frozen=True)
class WindowRetrievalRequest:
    """Internal opt-in with no candidate IDs, nominated ranges or source edits."""
    source: CanonicalSource
    state: WindowSourceState
    policy: WindowRetrievalPolicy = field(default_factory=WindowRetrievalPolicy)

    def __post_init__(self) -> None:
        if (not isinstance(self.source, CanonicalSource) or not isinstance(self.state, WindowSourceState)
                or self.source.descriptor != self.state.descriptor or not isinstance(self.policy, WindowRetrievalPolicy)):
            raise EditWindowError("Automatic retrieval requires immutable canonical source/state/policy")


@dataclass(frozen=True)
class WindowCandidate:
    first: int
    last: int
    duration: float


@dataclass(frozen=True)
class RetrievedWindows:
    candidates: tuple[WindowCandidate, ...]
    feasible_pairs: int
    eligible_starts: int
    sampled_starts: int
    source_rows_scanned: int
    fingerprint: str
    deferred_entry_rows: tuple[int, ...] = ()
    deferred_feasible_pairs: int = 0


@dataclass(frozen=True)
class SpeechUnitIndex:
    source_fingerprint: str
    units: tuple[tuple[int, int], ...]
    starts: tuple[int, ...]
    exits: tuple[int, ...]
    boundary_hints: tuple[tuple[int, tuple[str, ...]], ...]
    fingerprint: str

    def report(self):
        return {"policy": SPEECH_UNIT_POLICY, "fingerprint": self.fingerprint,
                "units": [list(pair) for pair in self.units], "entry_rows": list(self.starts), "exit_rows": list(self.exits),
                "boundary_hints": [{"after_row": row, "hints": list(hints)} for row,hints in self.boundary_hints],
                "canonical_rows_represented": sum(b-a+1 for a,b in self.units),
                "unknown_terminal_tail": self.units[-1][1] not in self.exits,
                "semantic_truth_verified": False, "punctuation_is_a_hint_only": True,
                "timing_gaps_are_untranscribed_not_verified_silence": True}


def retrieval_policy_record(policy):
    record = asdict(policy)
    if not record["defer_recovery_only_starts"]:
        del record["defer_recovery_only_starts"]  # Preserve all prior default cache identities.
    else:
        record["recovery_entry_policy"] = RECOVERY_ENTRY_POLICY
    if not record["speech_units"]:
        del record["speech_units"]  # Prior numeric control's cache identity.
    return record


def _speech_entry_domain(units, policy, cancel_check=None):
    """Keep recovery hints represented; defer them only in the explicit policy.

    An additional gap/speaker/punctuation cue may support a structural boundary,
    but no combination of these cues establishes independent meaning.
    """
    if not policy.defer_recovery_only_starts:
        return units.starts, ()
    hints = dict(units.boundary_hints)
    allowed, deferred = [], []
    for i, first in enumerate(units.starts):
        if i % 64 == 0 and cancel_check:
            cancel_check()
        recovery_only = first > 0 and hints.get(first - 1) == ("existing_entry_recovery_reference_only",)
        (deferred if recovery_only else allowed).append(first)
    return tuple(allowed), tuple(deferred)


def speech_entry_coverage(source, units, policy, cancel_check=None):
    if not policy.speech_units or not isinstance(units, SpeechUnitIndex) or units.source_fingerprint != source.fingerprint:
        raise EditWindowError("Speech-entry coverage requires current source-derived boundaries")
    allowed, deferred = _speech_entry_domain(units, policy, cancel_check)
    sampled = [deferred[i] for i in _spread(len(deferred), 64)]
    return {"policy": RECOVERY_ENTRY_POLICY if policy.defer_recovery_only_starts else "unverified_recovery_hints_allowed",
            "source_fingerprint": source.fingerprint, "boundary_index_fingerprint": units.fingerprint,
            "hint_start_count": len(units.starts), "eligible_hint_start_count": len(allowed),
            "deferred_hint_start_count": len(deferred),
            "deferred_start_row_ids": [source.rows[i].id for i in sampled],
            "deferred_ids_not_listed": len(deferred) - len(sampled),
            "canonical_rows_represented": len(source.rows), "source_rows_removed": 0,
            "deferred_status": "needs_context_review_not_source_no_fit", "semantic_truth_verified": False}


def produce_speech_window_candidates(source, beats, bounds, policy, cancel_check=None):
    """Shared guarded producer for actual previews and diagnostic evaluation.

    Callers cannot replace this with an unguarded all-ASR-pair policy. The source
    index is derived here, never accepted from a model or diagnostic JSON.
    """
    if not isinstance(policy, WindowRetrievalPolicy) or not policy.speech_units:
        raise EditWindowError("Guarded candidate production requires explicit speech units")
    units = build_speech_unit_index(source, beats, cancel_check)
    pool = retrieve_windows(source, bounds, policy, cancel_check, units=units)
    return units, pool


def build_speech_unit_index(source, beats, cancel_check=None):
    """Existing speech-unit references plus measured gap/speaker hints.

    No replacement transcript/owners or grammar oracle. Entry recovery allows
    starting after an unfinished prefix, not using that prefix as a good ending.
    An unresolved recording tail stays represented, outside eligible exits.
    """
    from .story_candidates import (CANDIDATE_POLICY_VERSION, ENTRY_POLICY_VERSION, _complete_boundary,
                                   project_short_source_units, expose_complete_asr_entries)
    data, rows = source.transcript(), source.rows
    def check():
        if cancel_check: cancel_check()
    check()
    projected = beats if all(b.get("candidate_policy") == CANDIDATE_POLICY_VERSION for b in beats) else \
        project_short_source_units(beats, data)
    # Reuse existing recovery once, including no-cuts/role paths whose owners
    # have not exposed entries. These views never change canonical ownership.
    exposed = [b.get("entry_policy") == ENTRY_POLICY_VERSION for b in projected]
    if any(exposed) and not all(exposed):
        raise EditWindowError("Speech-unit entry provenance must be consistent")
    if not any(exposed):
        projected = expose_complete_asr_entries(projected, data)
    positions = {r.id:i for i,r in enumerate(rows)}
    if [row for unit in projected for row in unit.get("segment_ids", [])] != [r.id for r in rows]:
        raise EditWindowError("Speech-unit references must cover unchanged canonical row order exactly once")
    starts, hints = {0}, {}
    def hint(after, value): hints.setdefault(after, set()).add(value)
    previous = None
    for unit in projected:
        check()
        first, last = positions[unit["segment_ids"][0]], positions[unit["segment_ids"][-1]]
        if _complete_boundary(rows[last].text): hint(last,"existing_terminal_punctuation_unverified")
        # Both pieces carry entry_owner_id. Only the suffix after its paired
        # prefix is a recovered entry; an arbitrary parent boundary is not.
        if (first > 0 and unit.get("entry_owner_id") and previous is not None
                and previous.get("entry_owner_id") == unit["entry_owner_id"]):
            hint(first-1,"existing_entry_recovery_reference_only")
        previous = unit
    for i,(left,right) in enumerate(zip(rows, rows[1:])):
        check()
        if right.start-left.end >= SPEECH_GAP_SECONDS-EPSILON:
            starts.add(i+1);hint(i,"ASR_interval_gap_unverified")
        a,b = data[i].get("speaker") or data[i].get("speaker_id"), data[i+1].get("speaker") or data[i+1].get("speaker_id")
        if isinstance(a,str) and a.strip() and isinstance(b,str) and b.strip() and a != b:
            starts.add(i+1);hint(i,"recorded_speaker_change_unverified")
    starts.update(i+1 for i in hints if i+1 < len(rows))
    starts = tuple(sorted(starts))
    exits = tuple(sorted(i for i,values in hints.items() if any(v != "existing_entry_recovery_reference_only" for v in values)))
    units = tuple((a,b-1) for a,b in zip(starts,(*starts[1:],len(rows))))
    evidence = tuple((i,tuple(sorted(values))) for i,values in sorted(hints.items()))
    fingerprint = _identity("speech-unit-index",[SPEECH_UNIT_POLICY,source.fingerprint,units,starts,exits,evidence])
    check()
    return SpeechUnitIndex(source.fingerprint,units,starts,exits,evidence,fingerprint)


def sample_entry_groups(values, maximum, entry_key, cancel_check=None, *, prefix_key=None):
    """Fixed work spread across source entries, then across each group's states.

    Dense short prefixes cannot consume all slots. Within a group, take the
    center of each equal rank stratum instead of repeatedly favoring extreme
    suffixes. Source entry groups still span both recording ends. Not semantic
    ranking: any unsampled suffix, including an extreme, may be the useful one.
    """
    groups = {}
    for i,value in enumerate(values):
        if i % 64 == 0 and cancel_check: cancel_check()
        groups.setdefault(entry_key(value), []).append(i)
    ordered = sorted(groups)
    anchors = [ordered[i] for i in _spread(len(ordered),maximum)]
    quotas = {key:0 for key in anchors}
    remaining = min(maximum,sum(len(groups[key]) for key in anchors))
    while remaining:
        if cancel_check: cancel_check()
        available = [key for key in anchors if quotas[key] < len(groups[key])]
        chosen = [available[i] for i in _spread(len(available),min(remaining,len(available)))]
        for key in chosen: quotas[key] += 1
        remaining -= len(chosen)
    selected = []
    for key in anchors:
        if cancel_check: cancel_check()
        group = groups[key]
        if prefix_key is not None:
            # Preserve earlier exact choices as families. Family density must
            # not decide its share of this source entry's existing quota.
            local = [values[i] for i in group]
            positions = sample_entry_groups(local,quotas[key],prefix_key,cancel_check)
        else:
            positions = _stratum_centers(len(group),quotas[key])
        selected.extend(group[i] for i in positions)
    return selected


def _stratum_centers(count: int, maximum: int) -> list[int]:
    """Fixed-size systematic sample of interior ranks; no content/source hints."""
    take = min(count, maximum)
    return [(2*i+1)*count//(2*take) for i in range(take)] if take else []


def _spread(count: int, maximum: int) -> list[int]:
    """Inclusive deterministic stratification; never cap to the first N starts."""
    take = min(count, maximum)
    if take == 1:
        return [(count - 1) // 2]
    if take == 0:
        return []
    return [i * (count - 1) // (take - 1) for i in range(take)]


def retrieve_windows(source: CanonicalSource, bounds: dict[str, Any], policy: WindowRetrievalPolicy,
                     cancel_check: Callable[[], None] | None = None, *, units: SpeechUnitIndex | None = None) -> RetrievedWindows:
    """Scan all row starts in O(N log N); materialize at most max_pairs records.

    Feasible counts cover the continuous numeric domain only. Work caps sample
    both starts and endpoints across their entire eligible domain, with explicit
    incompleteness. No full row memberships or text copies per pool candidate.
    """
    rows = source.rows
    if policy.speech_units and (not isinstance(units,SpeechUnitIndex) or units.source_fingerprint != source.fingerprint):
        raise EditWindowError("Speech-unit retrieval requires current source-derived unit references")
    starts, deferred = _speech_entry_domain(units, policy, cancel_check) if policy.speech_units else (range(len(rows)), ())
    end_rows = units.exits if policy.speech_units else tuple(range(len(rows)))
    ends = [rows[i].end for i in end_rows]
    lower, upper = bounds["minimum_seconds"], bounds["maximum_seconds"]
    eligible, possible, deferred_possible = [], 0, 0
    for first in deferred:
        if cancel_check:
            cancel_check()
        left = max(bisect_left(end_rows, first), bisect_left(ends, rows[first].start + lower - EPSILON))
        right = bisect_right(ends, rows[first].start + upper + EPSILON)
        deferred_possible += max(0, right - left)
    for first in starts:
        row = rows[first]
        if cancel_check:
            cancel_check()
        left = max(bisect_left(end_rows,first), bisect_left(ends, row.start + lower - EPSILON))
        right = bisect_right(ends, row.start + upper + EPSILON)
        if right > left:
            eligible.append((first, left, right))
            possible += right - left
    anchors = _spread(len(eligible), min(policy.max_source_starts, policy.max_pairs))
    per_start = min(policy.max_endpoints_per_start, policy.max_pairs // max(1, len(anchors)))
    candidates = []
    digest = hashlib.sha256()
    digest.update(_json([RETRIEVAL_POLICY, source.fingerprint, bounds, retrieval_policy_record(policy)]).encode("utf8"))
    if policy.speech_units: digest.update(units.fingerprint.encode("ascii"))
    for index in anchors:
        if cancel_check:
            cancel_check()
        first, left, right = eligible[index]
        for offset in _spread(right - left, per_start):
            if cancel_check:
                cancel_check()
            last = end_rows[left + offset]
            candidate = WindowCandidate(first, last, rows[last].end - rows[first].start)
            candidates.append(candidate)
            digest.update(_json([first, last, candidate.duration]).encode("ascii"))
    return RetrievedWindows(tuple(candidates), possible, len(eligible), len(anchors), len(rows), digest.hexdigest(),
                            tuple(deferred), deferred_possible)


def rank_windows(source: CanonicalSource, pool: RetrievedWindows, size: int,
                 cancel_check: Callable[[], None] | None = None, *,
                 row_reference_budget: int = 16384, text_character_budget: int = 1000000) -> tuple[WindowCandidate, ...]:
    """Greedy membership/time diversity. Priority is NOT editorial quality.

    Seed nearest the source-time center, then minimize maximum canonical-row
    Jaccard overlap with prior choices; use time separation and stable indices
    as ties. O(shortlist_size * pool_size), no word/grammar/semantic claims.
    """
    candidates = pool.candidates
    if not candidates:
        return ()
    if (type(size) is not int or not 1 <= size <= 32 or
            type(row_reference_budget) is not int or not 1 <= row_reference_budget <= 16384 or
            type(text_character_budget) is not int or not 1 <= text_character_budget <= 1000000):
        raise EditWindowError("Invalid shortlist bound")
    rows = source.rows
    chars = [0]
    for row in rows:
        chars.append(chars[-1] + len(row.text))
    costs = [(c.last - c.first + 1, chars[c.last + 1] - chars[c.first]) for c in candidates]
    centers = [(rows[c.first].start + rows[c.last].end) / 2 for c in candidates]
    middle = (rows[0].start + rows[-1].end) / 2
    overlap, distance, picked, chosen = [0.] * len(candidates), [float("inf")] * len(candidates), set(), []
    for _ in range(min(size, len(candidates))):
        if cancel_check:
            cancel_check()
        available = [i for i, (refs, text) in enumerate(costs) if i not in picked
                     and refs <= row_reference_budget and text <= text_character_budget]
        if not available:
            break
        next_index = min(available, key=(lambda i: (overlap[i], -distance[i], candidates[i].first, candidates[i].last))
                         if chosen else (lambda i: (abs(centers[i] - middle), candidates[i].first, candidates[i].last)))
        picked.add(next_index)
        chosen.append(candidates[next_index])
        row_reference_budget -= costs[next_index][0]
        text_character_budget -= costs[next_index][1]
        last = candidates[next_index]
        for i, candidate in enumerate(candidates):
            if i % 64 == 0 and cancel_check:
                cancel_check()
            intersection = max(0, min(last.last, candidate.last) - max(last.first, candidate.first) + 1)
            union = last.last - last.first + candidate.last - candidate.first + 2 - intersection
            overlap[i] = max(overlap[i], intersection / union)
            distance[i] = min(distance[i], abs(centers[i] - centers[next_index]))
    return tuple(chosen)


def validate_retrieval_source(segments, request, read_current, cancel_check=None) -> None:
    if not isinstance(request, WindowRetrievalRequest):
        raise EditWindowError("Automatic retrieval requires an immutable retrieval request")
    validate_bound_source(segments, request.source, request.state, read_current, cancel_check)


def prepare_window_retrieval_preview(segments, beats, brief, original_brief,
                                     request: WindowRetrievalRequest, read_current,
                                     cancel_check=None) -> dict[str, Any]:
    validate_retrieval_source(segments, request, read_current, cancel_check)
    source = request.source
    bounds = effective_duration_bounds(brief, source.descriptor.asset_duration)
    contract = assert_instruction_contract(brief)
    if request.policy.speech_units:
        units, pool = produce_speech_window_candidates(source, beats, bounds, request.policy, cancel_check)
    else:
        units, pool = None, retrieve_windows(source, bounds, request.policy, cancel_check)
    ranked = rank_windows(source, pool, request.policy.shortlist_size, cancel_check,
                          row_reference_budget=request.policy.max_view_row_references,
                          text_character_budget=request.policy.max_view_text_characters)
    windows = tuple(build_edit_window(source, source.rows[c.first].id, source.rows[c.last].id) for c in ranked)
    # Check exact mapped source geometry with the shared numeric/no-cuts adapter.
    # Each alternative is independent, never concatenate the shortlist as a plan.
    for window in windows:
        if cancel_check:
            cancel_check()
        compile_selected_spans(source, [window], brief=brief)
    if windows:
        evidence_request = WindowEvidenceRequest(source, request.state, windows)
        result = prepare_window_planner_preview(segments, beats, brief, original_brief,
                                               evidence_request, read_current, cancel_check)
    else:
        index = build_canonical_evidence_index(source, beats)
        result = {"source_fingerprint": source.fingerprint, "source_descriptor": asdict(source.descriptor),
                  "project_source_state": asdict(request.state), "canonical_evidence_fingerprint": index.fingerprint,
                  "canonical_ownership": [{"segment_id": s, "beat_id": b} for s, b in index.ownership],
                  "canonical_evidence": index.catalog(), "views": [], "selected_evidence": [], "selection": None,
                  "original_request": original_brief, "instruction_contract": contract, "editorial_status": "not_assessed"}
    receipt = {"policy": RETRIEVAL_POLICY, "bounds": bounds, "budget": retrieval_policy_record(request.policy),
               "source_rows_scanned": pool.source_rows_scanned, "eligible_starts": pool.eligible_starts,
               "sampled_starts": pool.sampled_starts, "feasible_continuous_pairs": pool.feasible_pairs,
               "retrieved_pairs": len(pool.candidates), "pool_fingerprint": pool.fingerprint,
               "continuous_domain_exhausted": len(pool.candidates) == pool.feasible_pairs,
               "shortlisted": len(windows), "unshortlisted_unreviewed": len(pool.candidates) - len(windows),
               "view_row_references": sum(len(w.row_ids) for w in windows),
               "view_text_characters": sum(len(source.rows[i].text) for c in ranked for i in range(c.first, c.last + 1)),
               "single_output_requested": single_output_requested(brief),
               "source_continuity": contract["selection_controls"]["source_continuity"],
               "candidate_form": "one_continuous_whole_ASR_window_per_alternative",
               "noncontiguous_composition_search": "not_implemented",
               "ranking_basis": "canonical_membership_and_source_time_diversity_only",
               "semantic_assessment": "not_performed",
               "status": ("unreviewed_candidates" if windows else "materialization_budget_blocked"
                          if pool.candidates else "no_numeric_fit_in_continuous_domain_only")}
    if units:
        receipt.update(speech_units=units.report(), candidate_form="one_continuous_speech_unit_view_range",
                       numeric_domain="speech_unit_entry_exit_hints_only_not_all_ASR_pairs")
        if request.policy.defer_recovery_only_starts:
            receipt["entry_boundary_coverage"] = {**speech_entry_coverage(source, units, request.policy, cancel_check),
                "deferred_numeric_pairs": pool.deferred_feasible_pairs,
                "numeric_pairs_before_deferral": pool.feasible_pairs + pool.deferred_feasible_pairs}
            if not pool.candidates and pool.deferred_feasible_pairs:
                receipt["status"] = "entry_context_review_needed"
    result.update(status="automatic_window_retrieval_preview_only", retrieval=receipt,
                  ranked_candidates=[{"rank": i + 1, "window_id": window.id,
                                      "first_row_id": window.row_ids[0], "last_row_id": window.row_ids[-1],
                                      "raw_seconds": window.source_end - window.source_start}
                                     for i, window in enumerate(windows)],
                  cache_reuse="not_implemented_no_story_cache_read_or_write")
    result["cache_key"] = _identity("window-retrieval-preview", [RETRIEVAL_POLICY, source.fingerprint,
        result["canonical_evidence_fingerprint"], asdict(request.state), original_brief, brief, receipt,
        [w.id for w in windows]])
    check_source_state(request.state, read_current, cancel_check)
    return result
