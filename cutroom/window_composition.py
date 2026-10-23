"""Automatic bounded ordered source compositions; every proposal is unreviewed.

This search omits whole canonical rows between ranges, never edits text, repeats
source, or infers coherent meaning. Source-span/run-count/beam budgets describe
SEARCH coverage, not user instructions or proof of source/editorial suitability.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, field, replace
import math
from typing import Any, Callable

from .edit_windows import (CanonicalSource, EditWindowError, build_edit_window,
                           compile_selected_spans, _identity)
from .instruction_contract import assert_instruction_contract, effective_duration_bounds, single_output_requested
from .window_evidence import (WindowEvidenceRequest, WindowSourceState, check_source_state,
                              prepare_window_planner_preview, validate_bound_source)
from .window_retrieval import (EPSILON, WindowRetrievalPolicy, WindowRetrievalRequest, _spread,
                               prepare_window_retrieval_preview, retrieve_windows, build_speech_unit_index,
                               sample_entry_groups, retrieval_policy_record, ENTRY_GROUP_SAMPLING, speech_entry_coverage)
from .window_search import ResumableSearchRequest, discover_page

COMPOSITION_POLICY = "bounded-ordered-whole-row-compositions-v1"
PREFIX_SAMPLING_POLICY = "source-entry-exact-prefix-families-necessary-extension-bounds-v3"


@dataclass(frozen=True)
class WindowCompositionPolicy:
    windows: WindowRetrievalPolicy = field(default_factory=lambda: WindowRetrievalPolicy(
        max_source_starts=128, max_pairs=2048, max_endpoints_per_start=16))
    max_ranges: int = 3
    beam_size: int = 64
    successors_per_state: int = 32
    max_transitions: int = 4096
    max_source_span: float = 180.
    shortlist_size: int = 8

    def __post_init__(self):
        if not isinstance(self.windows, WindowRetrievalPolicy) or self.windows.max_pairs > 2048:
            raise EditWindowError("Composition component pool supports at most 2048 windows")
        for name, maximum in (("max_ranges", 3), ("beam_size", 128), ("successors_per_state", 64),
                              ("max_transitions", 16384), ("shortlist_size", 16)):
            if type(getattr(self, name)) is not int or not 1 <= getattr(self, name) <= maximum:
                raise EditWindowError(name + " exceeds bounded composition policy")
        if (isinstance(self.max_source_span, bool) or not isinstance(self.max_source_span, (int, float))
                or not math.isfinite(self.max_source_span) or not 0 < self.max_source_span <= 600):
            raise EditWindowError("Invalid source context span limit")


@dataclass(frozen=True)
class WindowCompositionRequest:
    source: CanonicalSource
    state: WindowSourceState
    policy: WindowCompositionPolicy = field(default_factory=WindowCompositionPolicy)
    search: ResumableSearchRequest | None = None

    def __post_init__(self):
        if (not isinstance(self.source, CanonicalSource) or not isinstance(self.state, WindowSourceState)
                or self.source.descriptor != self.state.descriptor or not isinstance(self.policy, WindowCompositionPolicy)
                or (self.search is not None and not isinstance(self.search,ResumableSearchRequest))):
            raise EditWindowError("Composition requires immutable canonical source/state/policy")


@dataclass(frozen=True)
class SourceComposition:
    ranges: tuple[tuple[int, int], ...]
    duration: float


def composition_policy_record(policy):
    record = asdict(policy)
    record["windows"] = retrieval_policy_record(policy.windows)
    return record


def validate_composition_source(segments, request, read_current, cancel_check=None):
    if not isinstance(request, WindowCompositionRequest):
        raise EditWindowError("Automatic composition requires an immutable request")
    validate_bound_source(segments, request.source, request.state, read_current, cancel_check)


def prune_impossible_extensions(source, states, components, upper, max_span, cancel_check=None):
    """Necessary bounds in the indexed domain, not proof of a feasible finish.

    Two suffix minima can belong to different components. Keeping that case is
    intentional; only proven impossible continuations are removed. Existing
    output candidates are outside this frontier and are never removed here.
    """
    rows = source.rows
    def check(i):
        if i % 64 == 0 and cancel_check: cancel_check()
    firsts = [c.first for c in components]
    if any(a>b for a,b in zip(firsts,firsts[1:])):
        raise EditWindowError("Extension bounds require a source-ordered component index")
    times = [rows[c.first].start for c in components]
    durations, ends = [float("inf")]*(len(components)+1), [float("inf")]*(len(components)+1)
    for i in range(len(components)-1,-1,-1):
        check(i)
        durations[i] = min(durations[i+1],components[i].duration)
        ends[i] = min(ends[i+1],rows[components[i].last].end)
    retained = []
    for i,state in enumerate(states):
        check(i)
        first,last = state.ranges[0][0],state.ranges[-1][1]
        future = max(bisect_right(firsts,last+1),bisect_right(times,rows[last].end))
        if (state.duration+durations[future] <= upper+EPSILON
                and ends[future]-rows[first].start <= max_span):
            retained.append(state)
    if cancel_check: cancel_check()
    return retained


def search_compositions(source, bounds, policy, cancel_check=None, *, units=None):
    """Bounded breadth by run count; no combinatorial exhaustive-search claim.

    Components/continuous windows use the existing bounded source index. Beam
    and successor sampling span their indexed domains instead of first-N cuts.
    Only positive time omissions containing at least one whole row are searched;
    adjacent/gap-only cuts and equivalent touching-range segmentations are not.
    """
    def check():
        if cancel_check:
            cancel_check()
    if units is not None and not policy.windows.speech_units:
        raise EditWindowError("Speech-unit index requires explicit speech-unit policy")
    unit_args = {"units":units} if policy.windows.speech_units else {}
    continuous = retrieve_windows(source, bounds, policy.windows, cancel_check, **unit_args)
    component_bounds = {**bounds, "minimum_seconds": 0., "origin": "component_index_not_output_duration"}
    components = retrieve_windows(source, component_bounds, policy.windows, cancel_check, **unit_args)
    lower, upper, rows = bounds["minimum_seconds"], bounds["maximum_seconds"], source.rows
    found = {((c.first, c.last),): SourceComposition(((c.first, c.last),), c.duration) for c in continuous.candidates}
    minimum_piece = min((c.duration for c in components.candidates), default=float("inf"))
    states = [SourceComposition(((c.first, c.last),), c.duration) for c in components.candidates
              if c.duration + minimum_piece <= upper + EPSILON and c.duration <= policy.max_source_span]
    stages, used, pruned, unsampled, pending, impossible = [], 0, 0, 0, 0, 0
    for depth in range(2, policy.max_ranges + 1):
        check()
        if not states:
            break
        remaining = policy.max_transitions - used
        if remaining <= 0:
            stages.append({"ranges": depth, "pending_states": len(states), "budget_blocked": True})
            pending += len(states)
            break
        input_count = len(states)
        if units:
            states = prune_impossible_extensions(source,states,components.candidates,upper,policy.max_source_span,cancel_check)
            impossible += input_count-len(states)
            if not states:
                stages.append({"ranges":depth,"input_states":input_count,"extension_frontier_states":0,
                    "impossible_extension_prefixes_pruned":input_count,"beam_states":0,"beam_pruned":0,
                    "eligible_links_in_beam":0,"attempted_links":0,"unattempted_links_in_beam":0,
                    "eligible_entry_groups":0,"beam_entry_groups":0,"eligible_prefix_families":0,
                    "beam_prefix_families":0,"sampling":PREFIX_SAMPLING_POLICY,"successor_sampling":ENTRY_GROUP_SAMPLING})
                break
        level_budget = max(1, remaining // (policy.max_ranges - depth + 1))
        ordered = sorted(states, key=(lambda s:s.ranges) if units else (lambda s:(s.duration,s.ranges)))
        positions = (sample_entry_groups(ordered,min(policy.beam_size,level_budget),lambda s:s.ranges[0][0],cancel_check,
                                        prefix_key=lambda s:s.ranges[:-1])
                     if units else _spread(len(ordered), min(policy.beam_size, level_budget)))
        beam = [ordered[i] for i in positions]
        dropped = len(states) - len(beam)
        pruned += dropped
        per_state = min(policy.successors_per_state, level_budget // len(beam))
        next_states, links, attempts = [], 0, 0
        for state in beam:
            check()
            first, previous = state.ranges[0][0], state.ranges[-1][1]
            eligible = []
            for i, c in enumerate(components.candidates):
                if i % 64 == 0:
                    check()
                if (c.first > previous + 1 and rows[c.first].start > rows[previous].end
                        and rows[c.last].end - rows[first].start <= policy.max_source_span
                        and state.duration + c.duration <= upper + EPSILON):
                    eligible.append(c)
            links += len(eligible)
            successors = (sample_entry_groups(eligible,per_state,lambda c:c.first,cancel_check)
                          if units else _spread(len(eligible), per_state))
            for i in successors:
                check()
                c = eligible[i]
                new = SourceComposition((*state.ranges, (c.first, c.last)), state.duration + c.duration)
                attempts += 1
                if new.duration >= lower - EPSILON:
                    found[new.ranges] = new
                if new.duration + minimum_piece <= upper + EPSILON:
                    next_states.append(new)
        used += attempts
        unsampled += links - attempts
        stages.append({"ranges": depth, "input_states": input_count, "beam_states": len(beam),
                       "beam_pruned": dropped, "eligible_links_in_beam": links, "attempted_links": attempts,
                       "unattempted_links_in_beam": links - attempts})
        if units:
            stages[-1].update(eligible_entry_groups=len({s.ranges[0][0] for s in states}),
                              beam_entry_groups=len({s.ranges[0][0] for s in beam}),
                              eligible_prefix_families=len({(s.ranges[0][0],s.ranges[:-1]) for s in states}),
                              beam_prefix_families=len({(s.ranges[0][0],s.ranges[:-1]) for s in beam}),
                              extension_frontier_states=len(states),impossible_extension_prefixes_pruned=input_count-len(states),
                              sampling=PREFIX_SAMPLING_POLICY,successor_sampling=ENTRY_GROUP_SAMPLING)
        states = next_states
    candidates = tuple(found[key] for key in sorted(found))
    receipt = {"component_feasible_pairs": components.feasible_pairs, "components_retrieved": len(components.candidates),
               "component_domain_exhausted": len(components.candidates) == components.feasible_pairs,
               "continuous_feasible_pairs": continuous.feasible_pairs, "continuous_retrieved": len(continuous.candidates),
               "continuous_domain_exhausted": len(continuous.candidates) == continuous.feasible_pairs,
               "source_rows_scanned": len(rows), "attempted_transitions": used, "beam_pruned_states": pruned,
               "unattempted_links_in_examined_beams": unsampled, "budget_blocked_pending_states": pending,
               "stages": stages, "numeric_compositions_visited": len(candidates),
               "multi_range_compositions_visited": sum(len(c.ranges) > 1 for c in candidates),
               "configured_composition_domain_exhausted": (len(components.candidates) == components.feasible_pairs
                    and len(continuous.candidates) == continuous.feasible_pairs and pruned == 0 and unsampled == 0 and pending == 0),
               "pool_fingerprint": _identity("composition-pool", [COMPOSITION_POLICY, source.fingerprint, bounds,
                    composition_policy_record(policy), components.fingerprint, continuous.fingerprint, [c.ranges for c in candidates]]
                    + ([ENTRY_GROUP_SAMPLING,PREFIX_SAMPLING_POLICY] if units else []))}
    if units:
        receipt.update(speech_units=units.report(),numeric_domain="speech_unit_entry_exit_hints_not_all_ASR_pairs",
                       entry_sampling_policy=ENTRY_GROUP_SAMPLING,prefix_sampling_policy=PREFIX_SAMPLING_POLICY,
                       impossible_extension_prefixes_pruned=impossible,
                       extension_bounds="necessary_only_in_indexed_components_not_completion_proof")
    return candidates, receipt


def _overlap(a, b):
    intersection = sum(max(0, min(y, q) - max(x, p) + 1) for x, y in a.ranges for p, q in b.ranges)
    return intersection / (sum(y-x+1 for x,y in a.ranges) + sum(y-x+1 for x,y in b.ranges) - intersection)


def rank_compositions(source, candidates, policy, cancel_check=None):
    """Explore different run counts/memberships, never assess coherent meaning."""
    if not candidates:
        return ()
    rows, prefix = source.rows, [0]
    for row in rows:
        prefix.append(prefix[-1] + len(row.text))
    costs = [(sum(b-a+1 for a,b in c.ranges), sum(prefix[b+1]-prefix[a] for a,b in c.ranges)) for c in candidates]
    centers = [(rows[c.ranges[0][0]].start + rows[c.ranges[-1][1]].end)/2 for c in candidates]
    middle = (rows[0].start + rows[-1].end)/2
    overlaps, distances, selected, picked = [0.] * len(candidates), [float("inf")] * len(candidates), [], set()
    refs, chars = policy.windows.max_view_row_references, policy.windows.max_view_text_characters
    forms = sorted({len(c.ranges) for c in candidates})
    turn = 0
    while len(selected) < policy.shortlist_size:
        if cancel_check:
            cancel_check()
        available = [i for i,c in enumerate(candidates) if i not in picked and costs[i][0] <= refs and costs[i][1] <= chars]
        if not available:
            break
        form = forms[turn % len(forms)]
        turn += 1
        category = [i for i in available if len(candidates[i].ranges) == form]
        if not category:
            category = available
        chosen = min(category, key=(lambda i: (overlaps[i], -distances[i], candidates[i].ranges)) if selected else
                     (lambda i: (abs(centers[i]-middle), candidates[i].ranges)))
        selected.append(candidates[chosen]);picked.add(chosen)
        refs -= costs[chosen][0];chars -= costs[chosen][1]
        for i,c in enumerate(candidates):
            if i % 64 == 0 and cancel_check:
                cancel_check()
            overlaps[i] = max(overlaps[i], _overlap(c, candidates[chosen]))
            distances[i] = min(distances[i], abs(centers[i]-centers[chosen]))
    return tuple(selected)


def _candidate_id(source, candidate):
    return _identity("source-composition", [COMPOSITION_POLICY, source.fingerprint, candidate.ranges])


def prepare_window_composition_preview(segments, beats, brief, original_brief, request, read_current, cancel_check=None):
    validate_composition_source(segments, request, read_current, cancel_check)
    source, policy = request.source, request.policy
    bounds = effective_duration_bounds(brief, source.descriptor.asset_duration)
    contract = assert_instruction_contract(brief)
    no_cuts = contract["selection_controls"]["source_continuity"] == "required"
    units = build_speech_unit_index(source,beats,cancel_check) if policy.windows.speech_units else None
    if (no_cuts or policy.max_ranges == 1) and request.search is None:
        r = WindowRetrievalRequest(source, request.state, replace(policy.windows, shortlist_size=policy.shortlist_size))
        result = prepare_window_retrieval_preview(segments, beats, brief, original_brief, r, read_current, cancel_check)
        by_id = {row.id:i for i,row in enumerate(source.rows)}
        ranked = tuple(SourceComposition(((by_id[v["row_ids"][0]], by_id[v["row_ids"][-1]]),),
                          v["source_end"]-v["source_start"]) for v in result["views"])
        candidates = ranked
        receipt = {"multi_range_search": "disabled_by_explicit_no_cuts" if no_cuts else "disabled_by_range_count_limit",
                   "multi_range_compositions_visited": 0, "candidate_index_scope": "continuous_shortlist_only",
                   "configured_composition_domain_exhausted": False, "continuous_retrieval": result["retrieval"]}
    else:
        if request.search is not None:
            from .window_evidence import build_canonical_evidence_index
            index=build_canonical_evidence_index(source,beats)
            # Bind all authoritative inputs, not only the visible row text.
            identity=[asdict(request.state),index.fingerprint,original_brief,brief,contract,
                      composition_policy_record(policy)]
            page=discover_page(source,bounds,policy,request.search,identity,cancel_check,
                               units=units,no_cuts=no_cuts)
            candidates=tuple(SourceComposition(tuple(tuple(p) for p in c['ranges']),c['duration']) for c in page['candidates'])
            receipt={"resumable_search":{k:v for k,v in page.items() if k!='candidates'},
                     "candidate_index_scope":"pending_numeric_page_only",
                     "configured_composition_domain_exhausted":(page['indexed_domain_exhausted'] and
                         page['component_index_complete'] and page['continuous_index_complete']),
                     "component_domain_exhausted":page['component_index_complete'],
                     "continuous_domain_exhausted":page['continuous_index_complete']}
        else:
            candidates, receipt = search_compositions(source, bounds, policy, cancel_check, **({"units":units} if units else {}))
        ranked = rank_compositions(source, candidates, policy, cancel_check)
        # One reference table for all ALTERNATIVES; no global selected plan.
        unique = dict.fromkeys(pair for c in ranked for pair in c.ranges)
        windows = tuple(build_edit_window(source, source.rows[a].id, source.rows[b].id) for a,b in unique)
        if windows:
            result = prepare_window_planner_preview(segments, beats, brief, original_brief,
                WindowEvidenceRequest(source, request.state, windows), read_current, cancel_check)
        else:
            # Reuse the existing canonical boundary even for an empty/blocked
            # search; do not invent a selection to make the bridge nonempty.
            from .window_evidence import build_canonical_evidence_index
            index = build_canonical_evidence_index(source, beats)
            result = {"source_fingerprint": source.fingerprint, "source_descriptor": asdict(source.descriptor),
                      "project_source_state": asdict(request.state), "canonical_evidence_fingerprint": index.fingerprint,
                      "canonical_ownership": [{"segment_id": s, "beat_id": b} for s,b in index.ownership],
                      "canonical_evidence": index.catalog(), "views": [], "selected_evidence": [], "selection": None,
                      "original_request": original_brief, "instruction_contract": contract, "editorial_status": "not_assessed"}
    by_pair = {(v["row_ids"][0],v["row_ids"][-1]):v for v in result["views"]}
    proposals = []
    for position, candidate in enumerate(ranked, 1):
        if cancel_check:
            cancel_check()
        views = [by_pair[(source.rows[a].id,source.rows[b].id)] for a,b in candidate.ranges]
        windows = [build_edit_window(source, source.rows[a].id, source.rows[b].id) for a,b in candidate.ranges]
        plan = compile_selected_spans(source, windows, brief=brief)
        omissions = [{"source_start": left.source_end, "source_end": right.source_start,
                      "first_omitted_row_id": source.rows[b+1].id, "last_omitted_row_id": source.rows[c-1].id,
                      "omitted_row_count": c-b-1, "meaning_and_join_review": "pending"}
                     for (a,b),(c,d),left,right in zip(candidate.ranges,candidate.ranges[1:],windows,windows[1:])]
        proposals.append({"candidate_id": _candidate_id(source,candidate), "rank": position,
                          "window_ids": [w.id for w in windows], "clip_map": plan.clip_map(), "raw_seconds": plan.duration,
                          "candidate_evidence_ids": [ref for v in views for ref in v["evidence_ids"]],
                          "omitted_source": omissions, "context_and_join_review": "pending"})
        if units:
            by_start = {a:i for i,(a,b) in enumerate(units.units)}
            by_end = {b:i for i,(a,b) in enumerate(units.units)}
            hints = dict(units.boundary_hints)
            proposals[-1]["speech_unit_boundary_refs"] = [{"first_unit":by_start[a],"last_unit":by_end[b],
                "entry_hints":list(hints.get(a-1,("recording_start_unverified",) if a==0 else ())),
                "exit_hints":list(hints[b]),"semantic_status":"unverified"} for a,b in candidate.ranges]
    if units:
        receipt.update(speech_units=units.report(),numeric_domain="speech_unit_entry_exit_hints_not_all_ASR_pairs")
        if policy.windows.defer_recovery_only_starts:
            receipt["entry_boundary_coverage"] = speech_entry_coverage(source, units, policy.windows, cancel_check)
    receipt.update(policy=COMPOSITION_POLICY, bounds=bounds, budget=composition_policy_record(policy),
                   single_output_requested=single_output_requested(brief), source_continuity=contract["selection_controls"]["source_continuity"],
                   domain="ordered_whole_ASR_ranges_with_at_least_one_omitted_row_between_ranges",
                   all_legal_edits_exhausted=False, semantic_assessment="not_performed", shortlisted=len(proposals),
                   unshortlisted_unreviewed=max(0,len(candidates)-len(ranked)),
                   status="unreviewed_proposals" if proposals else "materialization_budget_blocked" if candidates else "no_numeric_fit_in_configured_search_only")
    if request.search is not None:
        # Empty incomplete pages are NOT evidence of semantic or global no-fit.
        receipt['status']=receipt['resumable_search']['search_status']
    result.update(status="automatic_source_composition_preview_only", composition=receipt, ranked_compositions=proposals,
                  candidate_index=[{"candidate_id":_candidate_id(source,c),"ranges":[[a,b] for a,b in c.ranges],"raw_seconds":c.duration} for c in candidates],
                  cache_reuse="not_implemented_no_story_cache_read_or_write")
    result["cache_key"] = _identity("window-composition-preview", [COMPOSITION_POLICY, source.fingerprint,
        result["canonical_evidence_fingerprint"], asdict(request.state), original_brief, brief, receipt,
        [p["candidate_id"] for p in proposals]])
    check_source_state(request.state, read_current, cancel_check)
    return result
