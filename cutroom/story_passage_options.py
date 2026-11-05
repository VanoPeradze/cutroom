"""Bounded mechanical options over whole existing source units.

An option is a chronological source selection whose RAW playback fits the
requested numeric band. It is not a story, an ASR correction, a semantic pass,
or a promise that the frame-quantized export will retain every boundary.
"""
from __future__ import annotations

import copy
import math
import heapq
import itertools
import re
from collections import Counter
from typing import Any, Callable

from .cache_keys import stable_fingerprint
from .instruction_contract import explicit_source_continuity_requested, effective_duration_bounds
from .story_budget import BUDGET_TOLERANCE_SECONDS, StoryPlanningError
from .story_candidates import MAX_SOURCE_SEGMENTS, _complete_boundary, source_identity_rows
from .passage_quality import SourcePhraseIndex, QUALITY_POLICY, source_review_prior, source_review_identity, validate_source_review


PASSAGE_OPTIONS_POLICY = "whole-source-window-options-2026-10-21-v6.source-quality-retrieval"
MAX_ORDERED_UNITS = 20
MAX_RETAINED_RUNS = 3
MAX_ORDERED_PATTERNS = 65000
MAX_RANKED_OPTIONS = 64
MAX_ENVELOPE_ALTERNATIVES = 4
MAX_CANDIDATES = 48
MAX_OPTIONS = 128
MAX_WINDOWS = MAX_CANDIDATES * (MAX_CANDIDATES + 1) // 2
SEARCH_SCOPE = "consecutive raw-band only; disjoint/pause-fit unsearched"
_EPSILON = 1e-9


def _patterns(count, ordered):
    for runs in range(1, (MAX_RETAINED_RUNS if ordered else 1) + 1):
        for endpoints in itertools.combinations(range(count + 1), 2 * runs):
            yield [list(range(endpoints[i], endpoints[i + 1])) for i in range(0, len(endpoints), 2)]


def _lexical_priority(runs, candidates):
    """A bounded retrieval ranking, explicitly not semantic approval."""
    stop = set("the a an and or but it its is are was were be been to for of in on at that this those they their i you we he she have has had do does did not no so as with from by me my our your them there then than how what why when will can could would should some all one זה את של על עם לא הוא היא אני אתה הם גם אז או אבל כי מה לי יש כל היה שזה ואת".split())
    sets = [{t for t in re.findall(r"[^\W\d_]+", " ".join(candidates[i]["text"] for i in run).casefold())
             if len(t) > 1 and t not in stop} for run in runs]
    shared = sum(1 for token in set().union(*sets) if sum(token in values for values in sets) > 1)
    total = sum(len(values) for values in sets) or 1
    return shared / total


def _keep_ranked(heap, item, maximum):
    if len(heap) < maximum:
        heapq.heappush(heap, item)
    elif item[0] > heap[0][0]:
        heapq.heapreplace(heap, item)


def _keep_diverse_envelope(reservoir, item, positions, maximum):
    """Retain one retrieval leader and different interiors, in constant space.

    Global start/end diversity cannot recover an interior discarded here. A
    bounded online reservoir is approximate recall, never semantic approval.
    """
    pool = [*reservoir, item]
    if len(pool) <= maximum:
        reservoir.append(item)
        return
    masks = {row[1]["id"]: sum(1 << positions[v] for v in row[1]["beat_ids"]) for row in pool}
    chosen = [max(pool, key=lambda row: row[0])]
    pool.remove(chosen[0])
    while pool and len(chosen) < maximum:
        def priority(row):
            mask = masks[row[1]["id"]]
            similarity = max((mask & masks[old[1]["id"]]).bit_count() /
                             (mask | masks[old[1]["id"]]).bit_count() for old in chosen)
            return -similarity, row[0]
        winner = max(pool, key=priority)
        chosen.append(winner)
        pool.remove(winner)
    reservoir[:] = chosen


def _diverse_shortlist(ranked, envelopes, candidate_ids, *, maximum=MAX_RANKED_OPTIONS):
    """Keep lexical recall and reserve half the bounded list for source diversity.

    A different start/end preserves possible setup/conclusion context, without
    claiming it supplies either. Up to four alternative interiors per envelope
    prevent the reservoir itself being filled by one family of near duplicates.
    No text classifier, source-specific rule or semantic acceptance is involved.
    """
    ranked = sorted(ranked, key=lambda item: item[0], reverse=True)
    reservoir = {item[1]["id"]: item for item in ranked}
    for heap in envelopes.values():
        reservoir.update((item[1]["id"], item) for item in heap)
    positions = {identifier: index for index, identifier in enumerate(candidate_ids)}
    masks = {identifier: sum(1 << positions[v] for v in item[1]["beat_ids"])
             for identifier, item in reservoir.items()}
    chosen = ranked[:max(1, maximum // 2)]
    chosen_masks = [masks[item[1]["id"]] for item in chosen]
    for item in chosen:
        reservoir.pop(item[1]["id"])
    # Update one maximum similarity per remaining option, rather than rescanning
    # every selected pair at every step. Reservoir <= C(21,2)*4 + 64 options.
    similarity = {identifier: max(((mask & old).bit_count() / (mask | old).bit_count()
                                  for old in chosen_masks), default=0.)
                  for identifier, mask in masks.items() if identifier in reservoir}
    while reservoir and len(chosen) < maximum:
        identifier = max(reservoir, key=lambda key: (-similarity[key], reservoir[key][0]))
        chosen.append(reservoir.pop(identifier))
        mask = masks[identifier]
        for other in reservoir:
            similarity[other] = max(similarity[other],
                (mask & masks[other]).bit_count() / (mask | masks[other]).bit_count())
    return [item[1] for item in chosen]


def _fail(reason: str, *, incomplete: bool = False, **details: Any) -> None:
    raise StoryPlanningError(
        "Source passage options could not be completely established within the supported scope. No selection was applied.",
        {"reason": reason, "outcome": "technical_error", "incomplete": incomplete,
         "scope": SEARCH_SCOPE, "search_complete_within_scope": False,
         "applied_to_timeline": False, **details},
    )


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail("invalid_source_passage_geometry", field=name)
    return float(value)


def _ids(value: Any, name: str, *, nonempty: bool = True) -> list[str]:
    if (not isinstance(value, list) or (nonempty and not value)
            or any(not isinstance(item, str) or not item for item in value)
            or len(value) != len(set(value))):
        _fail("invalid_source_passage_identifiers", field=name)
    return value


def enumerate_passage_options(
    candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any], brief: dict[str, Any],
    cost: Callable[[list[str]], dict[str, Any]], cancel_check: Callable[[], None] | None = None,
    *, source_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Enumerate bounded whole-unit patterns before retrieving a numeric subset.

    The caller supplies a neutral one-purpose plan and its existing native cost
    function. Primary chapters are an allowed domain; required context chapters
    must each be represented. A hole in the supplied domain separates windows;
    it cannot conceal a skipped full-source unit. No source rows are invented,
    sorted, split, merged, retimed, repaired or silently dropped. Small domains
    of complete ASR entries may use up to three ordered runs when edits are
    permitted; the bounded shortlist is never an editorial completeness claim.
    """
    if cancel_check is not None:
        cancel_check()
    if not isinstance(candidates, list) or not candidates:
        _fail("missing_source_passage_candidates")
    if len(candidates) > MAX_CANDIDATES:
        _fail("source_passage_candidate_bound", incomplete=True,
              candidate_count=len(candidates), maximum_candidates=MAX_CANDIDATES)
    if not callable(cost):
        _fail("missing_source_passage_cost")
    if not isinstance(segments, list) or not segments or len(segments) > MAX_SOURCE_SEGMENTS:
        _fail("invalid_source_passage_segments")

    segment_by_id: dict[str, dict[str, Any]] = {}
    previous_end = -1.0
    source_ids = set()
    for row in segments:
        if (not isinstance(row, dict) or not isinstance(row.get("id"), str)
                or not row["id"] or row["id"] in segment_by_id
                or not isinstance(row.get("text"), str) or not row["text"].strip()):
            _fail("invalid_source_passage_segments")
        start, end = _number(row.get("start"), "segment.start"), _number(row.get("end"), "segment.end")
        if start < 0 or end <= start or start < previous_end - _EPSILON:
            _fail("unordered_or_overlapping_source_segments")
        if row.get("source_id") is not None:
            if not isinstance(row["source_id"], str) or not row["source_id"]:
                _fail("invalid_source_passage_identity")
            source_ids.add(row["source_id"])
        segment_by_id[row["id"]] = row
        previous_end = end
    canonical_ids = list(segment_by_id)
    canonical_positions = {identifier: index for index, identifier in enumerate(canonical_ids)}
    if len(source_ids) > 1:
        _fail("multiple_source_passage_identities")

    if not isinstance(chapters, list) or not chapters:
        _fail("missing_full_source_chapters")
    full_units: list[dict[str, Any]] = []
    full_by_id: dict[str, dict[str, Any]] = {}
    chapter_by_unit: dict[str, str] = {}
    chapter_ids: set[str] = set()
    owned_segments: list[str] = []
    for chapter in chapters:
        if (not isinstance(chapter, dict) or not isinstance(chapter.get("id"), str)
                or not chapter["id"] or chapter["id"] in chapter_ids
                or not isinstance(chapter.get("beats"), list) or not chapter["beats"]):
            _fail("invalid_full_source_chapters")
        chapter_ids.add(chapter["id"])
        for unit in chapter["beats"]:
            if (not isinstance(unit, dict) or not isinstance(unit.get("id"), str)
                    or not unit["id"] or unit["id"] in full_by_id):
                _fail("invalid_full_source_units")
            ids = _ids(unit.get("segment_ids"), "unit.segment_ids")
            if any(identifier not in segment_by_id for identifier in ids):
                _fail("unknown_source_passage_segment")
            positions = [canonical_positions[identifier] for identifier in ids]
            if positions != list(range(positions[0], positions[-1] + 1)):
                _fail("nonconsecutive_source_unit_segments")
            source = [segment_by_id[identifier] for identifier in ids]
            unit_start = _number(unit.get("start"), "unit.start")
            unit_end = _number(unit.get("end"), "unit.end")
            if (unit_start != source[0]["start"] or unit_end != source[-1]["end"]
                    or unit.get("text") != " ".join(row["text"] for row in source)):
                _fail("source_passage_unit_rewrites_canonical_source")
            if unit.get("source_id") is not None:
                if not isinstance(unit["source_id"], str) or not unit["source_id"]:
                    _fail("invalid_source_passage_identity")
                source_ids.add(unit["source_id"])
            full_units.append(unit)
            full_by_id[unit["id"]] = unit
            chapter_by_unit[unit["id"]] = chapter["id"]
            owned_segments.extend(ids)
    if len(source_ids) > 1:
        _fail("multiple_source_passage_identities")
    if owned_segments != canonical_ids:
        _fail("full_chapters_do_not_cover_canonical_source_exactly")
    full_positions = {row["id"]: index for index, row in enumerate(full_units)}

    candidate_ids: list[str] = []
    identity_keys = ("id", "start", "end", "text", "segment_ids", "source_id",
                     "candidate_source_fingerprint", "boundary_status")
    for unit in candidates:
        if (not isinstance(unit, dict) or not isinstance(unit.get("id"), str)
                or unit["id"] not in full_by_id or unit["id"] in candidate_ids):
            _fail("unknown_or_duplicate_source_passage_candidate")
        canonical = full_by_id[unit["id"]]
        if any(unit.get(key) != canonical.get(key) for key in identity_keys):
            _fail("source_passage_candidate_rewrites_full_source")
        candidate_ids.append(unit["id"])
    positions = [full_positions[identifier] for identifier in candidate_ids]
    if positions != sorted(positions):
        _fail("unordered_source_passage_candidates")

    if not isinstance(plan, dict) or not isinstance(plan.get("slots"), list) or len(plan["slots"]) != 1:
        _fail("unsupported_source_passage_plan")
    slot = plan["slots"][0]
    if not isinstance(slot, dict) or slot.get("purpose") != "self_contained_passage":
        _fail("unsupported_source_passage_plan")
    primary = set(_ids(slot.get("chapter_ids"), "plan.chapter_ids"))
    required_context = set(_ids(slot.get("required_context_chapter_ids"), "plan.required_context_chapter_ids", nonempty=False))
    if not primary.union(required_context) <= chapter_ids:
        _fail("unknown_source_passage_plan_chapter")
    if any(chapter_by_unit[identifier] not in primary.union(required_context) for identifier in candidate_ids):
        _fail("source_passage_candidate_outside_plan_domain")
    if not isinstance(brief, dict):
        _fail("invalid_source_passage_brief")
    mode = brief.get("duration_mode", "target")
    if mode not in {"target", "max", "style"}:
        _fail("unsupported_source_passage_duration_mode")
    source_end = float(segments[-1]["end"])
    bounds = effective_duration_bounds(brief, source_end)
    target, minimum = bounds["maximum_seconds"], bounds["minimum_seconds"]
    continuity = explicit_source_continuity_requested(brief)
    source_rows = source_identity_rows(segments)
    source_fingerprint = stable_fingerprint(PASSAGE_OPTIONS_POLICY,
                                            {"segments": source_rows, "source_ids": sorted(source_ids)})
    inventory = copy.deepcopy(candidates)
    if source_quality is not None and source_quality.get("source_identity")!=source_review_identity(candidates):
        _fail("stale_source_quality_assessment")
    if source_quality is not None:
        try:
            if validate_source_review(source_quality["units"],candidates,source_quality["model"])!=source_quality:
                _fail("invalid_source_quality_assessment")
        except (ValueError,TypeError,KeyError):
            _fail("invalid_source_quality_assessment")
    identity = stable_fingerprint(PASSAGE_OPTIONS_POLICY, {"source": source_fingerprint, "plan": plan, "brief": brief,
                "units": [{key: copy.deepcopy(row.get(key)) for key in identity_keys} for row in candidates]})
    requested = brief.get("source_candidate_segment_ids")
    if requested is not None:
        requested = _ids(requested, "brief.source_candidate_segment_ids")
        if requested != [r["id"] for r in segments if r["id"] in set(requested)]:
            _fail("invalid_requested_source_candidate")
    options = []
    ranked = []
    envelopes = {}
    ordered = (not continuity and len(candidates) <= MAX_ORDERED_UNITS
               and all(row.get("entry_policy") for row in candidates))
    phrase_index = SourcePhraseIndex(candidates) if ordered else None
    candidate_positions = {identifier:i for i,identifier in enumerate(candidate_ids)}
    visited = 0
    counts: Counter[str] = Counter()
    raw_durations: list[float] = []
    for runs in _patterns(len(candidates), ordered):
        if cancel_check is not None:
            cancel_check()
        visited += 1
        if visited > (MAX_ORDERED_PATTERNS if ordered else MAX_WINDOWS):
            _fail("source_passage_work_bound", incomplete=True, visited_windows=visited)
        indices = [i for run in runs for i in run]
        window = [candidates[i] for i in indices]
        identifiers = [candidate_ids[i] for i in indices]
        if any(positions[run[-1]] - positions[run[0]] != len(run) - 1 for run in runs):
            counts["eligible_domain_hole"] += 1
            continue
        if any(not _complete_boundary(candidates[run[-1]]["text"])
               or candidates[run[-1]].get("boundary_status") == "unfinished_parent_tail" for run in runs):
            counts["incomplete_end_boundary"] += 1
            continue
        represented = {chapter_by_unit[identifier] for identifier in identifiers}
        if (not required_context <= represented or not primary.intersection(represented)
                or chapter_by_unit[identifiers[-1]] not in primary):
            counts["chapter_obligations"] += 1
            continue
        ranges = ([{"start": window[0]["start"], "end": window[-1]["end"]}] if continuity
                  else [{"start": row["start"], "end": row["end"]} for row in window])
        raw = sum(float(row["end"]) - float(row["start"]) for row in ranges)
        raw_durations.append(raw)
        if requested is not None and [sid for row in window for sid in row["segment_ids"]] != requested:
            counts["outside_requested_source_candidate"] += 1
            continue
        if raw <= 0 or raw > target + _EPSILON or raw + BUDGET_TOLERANCE_SECONDS + _EPSILON < minimum:
            counts["outside_raw_duration_band"] += 1
            continue
        callback_cost = cost(list(identifiers))
        if not isinstance(callback_cost, dict):
            _fail("invalid_source_passage_cost")
        callback_min = _number(callback_cost.get("minimum_safe_seconds"), "cost.minimum_safe_seconds")
        callback_raw = _number(callback_cost.get("approved_seconds"), "cost.approved_seconds")
        if (callback_min < 0 or callback_raw <= 0 or callback_min > callback_raw + BUDGET_TOLERANCE_SECONDS
                or callback_cost.get("fits_target") is not True):
            _fail("inconsistent_source_passage_cost")
        if not continuity and abs(callback_raw - raw) > .001 + _EPSILON:
            _fail("source_passage_cost_changes_raw_playback")
        option = {"id": "passage_" + stable_fingerprint(PASSAGE_OPTIONS_POLICY,
                                                       {"identity": identity, "unit_ids": identifiers})[:24],
                  "beat_ids": list(identifiers),
                  "segment_ids": [identifier for row in window for identifier in row["segment_ids"]],
                  "chapter_ids": [chapter for chapter in (row["id"] for row in chapters) if chapter in represented],
                  "playback_ranges": ranges, "source_start": window[0]["start"], "source_end": window[-1]["end"],
                  "raw_playable_seconds": round(raw, 9), "minimum_output_seconds": minimum,
                  "target_seconds": target, "minimum_safe_seconds": raw if continuity else callback_min,
                  "duration_bounds": copy.deepcopy(bounds),
                      "verbatim_instruction": brief.get("instruction", ""),
                  "explicit_source_continuity_requested": continuity,
                  "source_fingerprint": source_fingerprint, "cost": copy.deepcopy(callback_cost),
                  "semantic_fit_verified": False, "selection_forced": False,
                  "ordered_source_group_search": ordered,
                  "source_candidate_origin": brief.get("source_candidate_origin", "automatic_ranked_search"),
                  "selected_source_groups": [[sid for i in run for sid in candidates[i]["segment_ids"]] for run in runs],
                  "context_across_omissions_verified": False,
                  "frame_validation_required": True}
        counts["numeric_option"] += 1
        if ordered:
            quality = phrase_index.measure(indices)
            uncertain, missing_context = source_review_prior(source_quality,candidates,indices,positions)
            quality.update(source_uncertain_fraction=uncertain, advisory_missing_neighbor_count=missing_context)
            option["retrieval_quality"] = quality
            # Repeated wording is not extra semantic evidence. Within an explicit
            # duration range, proximity to its upper bound is not editing quality.
            rank = (-uncertain, -missing_context, -quality["duplicate_fraction"], _lexical_priority(runs, candidates), -len(runs), option["id"])
            item = (rank, option)
            _keep_ranked(ranked, item, MAX_RANKED_OPTIONS)
            envelope = (identifiers[0], identifiers[-1])
            _keep_diverse_envelope(envelopes.setdefault(envelope, []), item,
                                   candidate_positions, MAX_ENVELOPE_ALTERNATIVES)
        else:
            options.append(option)
        if not ordered and len(options) > MAX_OPTIONS:
            _fail("source_passage_option_bound", incomplete=True, visited_windows=visited,
                  option_count=len(options), maximum_options=MAX_OPTIONS)
    if ordered:
        options = _diverse_shortlist(ranked, envelopes, candidate_ids)
    receipt = {"policy_version": PASSAGE_OPTIONS_POLICY, "scope": ("ordered up to3 complete ASR runs; bounded lexical/source-diverse64 numeric options; semantic fit unverified" if ordered else SEARCH_SCOPE),
               "ordered_noncontiguous_enabled": ordered, "maximum_retained_runs": MAX_RETAINED_RUNS if ordered else 1,
               "maximum_ordered_units": MAX_ORDERED_UNITS, "numeric_option_count": counts["numeric_option"],
               "all_numeric_options_presented": counts["numeric_option"] == len(options),
               "ranking_authority": "source repetition prior, lexical/source diversity; never semantic approval",
               "shortlist_policy": {"lexical_slots": MAX_RANKED_OPTIONS // 2,
                                    "maximum_envelope_alternatives": MAX_ENVELOPE_ALTERNATIVES,
                                    "envelope_retention": "one quality-ranked leader plus bounded interior membership diversity",
                                    "envelope_count": len(envelopes),
                                    "retained_numeric_pool_count": len({item[1]["id"] for heap in [ranked, *envelopes.values()] for item in heap}),
                                    "quality_policy": QUALITY_POLICY,
                                    "duration_preference_within_band": None,
                                    "diversity_measure": "whole-source-unit Jaccard; not topic or completeness verification"} if ordered else None,
               "visited_windows": visited, "candidate_count": len(candidates), "option_count": len(options),
               "source_fingerprint": source_fingerprint, "source_end_seconds": source_end,
               "duration_bounds": copy.deepcopy(bounds),
               "source_segments": copy.deepcopy(source_rows), "candidate_inventory": inventory,
               "source_quality": copy.deepcopy(source_quality),
               "full_source_unit_ids": [row["id"] for row in full_units],
               "coverage": {"canonical_segment_count": len(segments), "full_source_unit_count": len(full_units),
                            "eligible_unit_ids": list(candidate_ids), "window_outcomes": dict(counts),
                            "all_consecutive_candidate_windows_visited": True},
               "duration_distribution": {"count": len(raw_durations),
                                         "minimum_raw_seconds": min(raw_durations) if raw_durations else None,
                                         "maximum_raw_seconds": max(raw_durations) if raw_durations else None,
                                         "option_raw_seconds": [row["raw_playable_seconds"] for row in options]},
               "search_complete_within_scope": True, "semantic_fit_verified": False,
               "empty_result_meaning": "no numeric option in this subset; semantic no-fit is not established"}
    return {"options": copy.deepcopy(options), "receipt": receipt}
