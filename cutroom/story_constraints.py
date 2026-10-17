"""Bounded, optimistic duration proofs for the currently allowed story source.

Chapter membership is deliberately weaker than semantic evidence. A numerical
fit never certifies a story, while an exhaustive optimistic lower bound can
prove that these particular source constraints cannot fit the target.
"""
from __future__ import annotations

import math
import re
from typing import Any, Iterable

from .story_budget import BUDGET_TOLERANCE_SECONDS, segment_speech_ranges, story_duration_cost
from .utils import merge_ranges, normalize_text


MAX_CONSTRAINT_SEARCH_STATES = 512
MAX_FINAL_ENDING_DOMAIN_UNITS = 512
MAX_FINAL_ENDING_SOURCE_SEGMENTS = 8192


def _source_range(row: dict[str, Any]) -> dict[str, float] | None:
    try:
        start, end = float(row["start"]), float(row["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        return None
    return {"start": start, "end": end}


def _complete_unit(
    beat: dict[str, Any], source_range: dict[str, float],
    segments: list[dict[str, Any]], segment_by_id: dict[str, dict[str, Any]],
) -> bool:
    identifiers = beat.get("segment_ids")
    if (not isinstance(identifiers, list) or not identifiers
            or any(not isinstance(value, str) or value not in segment_by_id for value in identifiers)
            or len(identifiers) != len(set(identifiers))
            or not re.search(r"[.!?\u2026\u3002\uff01\uff1f][\"'\u201d\u2019\u00bb)\]]*$",
                             str(beat.get("text") or "").strip())):
        return False
    source = [segment_by_id[value] for value in identifiers]
    overlapping = [row for row in segments if float(row["start"]) < source_range["end"] - .001
                   and float(row["end"]) > source_range["start"] + .001]
    return (
        {str(row["id"]) for row in overlapping} == set(identifiers)
        and normalize_text(str(beat.get("text") or ""))
        == normalize_text(" ".join(str(row.get("text") or "") for row in source))
        and all(float(row["start"]) >= source_range["start"] - .001
                and float(row["end"]) <= source_range["end"] + .001 for row in source)
        and abs(min(float(row["start"]) for row in source) - source_range["start"]) <= .001
        and abs(max(float(row["end"]) for row in source) - source_range["end"]) <= .001
    )


def story_constraint_feasibility(
    candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any], *,
    selected_beat_ids: Iterable[str], sticky_beat_ids: Iterable[str],
    rejected_beat_ids: Iterable[str], target: float,
    protect_action_span: bool = False, eligible_beat_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Diagnose duration constraints without selecting or approving an edit.

Every role requires one primary unit from any of its allowed chapters and one
context unit from EACH required context chapter. One unit may cover multiple
groups. Sticky units are mandatory; rejected/incomplete/ineligible units cannot
supply a group. The search minimizes the UNION of protected speech, omitting
pause handles entirely, so its result is only an optimistic lower bound.

When the bounded search is not exhaustive, only mandatory protected source is
reported as a lower bound. A visited partial solution is never a proof.
"""
    target = float(target)
    if not math.isfinite(target) or target < 0:
        raise ValueError("Story target must be finite and nonnegative.")
    selected, sticky, rejected = set(selected_beat_ids), set(sticky_beat_ids), set(rejected_beat_ids)
    available = None if eligible_beat_ids is None else set(eligible_beat_ids)
    source = [row for row in segments if isinstance(row, dict) and row.get("id") is not None
              and _source_range(row) is not None]
    candidate_ids = [str(row["id"]) for row in candidates
                     if isinstance(row, dict) and row.get("id") is not None]
    segment_ids = [str(row["id"]) for row in source]
    ambiguous_ids = (len(candidate_ids) - len(set(candidate_ids))
                     + len(segment_ids) - len(set(segment_ids)))
    segment_by_id = {str(row["id"]): row for row in source if row.get("id") is not None}
    valid = {str(row["id"]): row for row in candidates
             if isinstance(row, dict) and row.get("id") is not None and _source_range(row) is not None}
    ranges = {identifier: _source_range(row) for identifier, row in valid.items()}
    eligible = {identifier for identifier, row in valid.items()
                if identifier not in rejected and (available is None or identifier in available)
                and _complete_unit(row, ranges[identifier], source, segment_by_id)}
    duration = max([row["end"] for row in ranges.values()] + [float(row["end"]) for row in source] + [0.0])
    current = selected | sticky
    current_cost = story_duration_cost(
        [ranges[value] for value in current if value in ranges], source, duration,
        target=target, protect_action_span=protect_action_span,
    )
    by_chapter: dict[str, set[str]] = {}
    for chapter in chapters:
        by_chapter.setdefault(str(chapter.get("id")), set()).update(
            str(beat.get("id")) for beat in chapter.get("beats", [])
            if isinstance(beat, dict) and str(beat.get("id")) in eligible
        )
    groups: list[frozenset[str]] = []
    for slot in plan.get("slots", []):
        primary: set[str] = set()
        for chapter_id in slot.get("chapter_ids", []):
            primary.update(by_chapter.get(str(chapter_id), set()))
        groups.append(frozenset(primary))
        for chapter_id in dict.fromkeys(slot.get("required_context_chapter_ids", [])):
            groups.append(frozenset(by_chapter.get(str(chapter_id), set())))
    missing = sum(not group for group in groups) + len(sticky - eligible)
    if not groups:
        missing += 1
    required = sticky | {next(iter(group)) for group in groups if len(group) == 1}
    protected: dict[str, list[dict[str, float]]] = {}
    for identifier in eligible:
        passage = ranges[identifier]
        if protect_action_span:
            protected[identifier] = [passage]
        else:
            protected[identifier] = [
                {"start": max(passage["start"], span["start"]),
                 "end": min(passage["end"], span["end"])}
                for segment in source if float(segment["start"]) < passage["end"]
                and float(segment["end"]) > passage["start"]
                for span in segment_speech_ranges(segment)
                if span["start"] < passage["end"] and span["end"] > passage["start"]
            ]

    def lower_bound(identifiers: Iterable[str]) -> float:
        union = merge_ranges([span for identifier in identifiers
                              for span in protected.get(identifier, [])], gap=0.0)
        # Shared source accounting quantizes boundaries to milliseconds. Sum
        # those integer ticks so floating cancellation cannot strengthen proof.
        return sum(round(row["end"] * 1000) - round(row["start"] * 1000)
                   for row in union) / 1000

    mandatory_bound = lower_bound(required)
    best = math.inf
    seen: set[frozenset[str]] = set()
    exhaustive = True
    distinct_groups = list(dict.fromkeys(groups))

    def search(chosen: frozenset[str]) -> None:
        nonlocal best, exhaustive
        if chosen in seen:
            return
        if len(seen) >= MAX_CONSTRAINT_SEARCH_STATES:
            exhaustive = False
            return
        seen.add(chosen)
        cost = lower_bound(chosen)
        if cost >= best:
            return
        remaining = [group for group in distinct_groups if not group.intersection(chosen)]
        if not remaining:
            best = cost
            return
        for identifier in sorted(min(remaining, key=len)):
            search(chosen | {identifier})
            if not exhaustive:
                return

    if not missing and not ambiguous_ids:
        search(frozenset(required))
    else:
        exhaustive = False
    bound = 0.0 if ambiguous_ids else best if exhaustive and math.isfinite(best) else mandatory_bound
    if missing:
        status = "required_source_missing"
    elif ambiguous_ids:
        status = "unverified"
    elif bound > target + BUDGET_TOLERANCE_SECONDS + 1e-9:
        status = "target_infeasible"
    elif (current <= eligible and sticky <= current and current_cost["fits_target"]
          and all(group.intersection(current) for group in groups)):
        status = "duration_fit_but_semantics_unverified"
    else:
        status = "unverified"
    return {
        "status": status, "scope": "allowed_source_constraints", "target_seconds": target,
        "current_required_selection_cost": current_cost,
        "current_required_selection_minimum_seconds": current_cost["minimum_safe_seconds"],
        "optimistic_lower_bound_seconds": bound, "searched_states": len(seen),
        "exhaustive": exhaustive, "missing_group_count": missing,
        "eligible_unit_count": len(eligible), "required_group_count": len(groups),
        "ambiguous_source_id_count": ambiguous_ids,
    }


def story_final_ending_domain(
    candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any], *,
    sticky_beat_ids: Iterable[str], rejected_beat_ids: Iterable[str],
    minimum_target_seconds: float, eligible_beat_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Remove only source endings disproven by optimistic prefix constraints.

    An edit ending in unit E cannot use a unit ending later than E (within the
    source-boundary tolerance). The union of ALL eligible prefix footage is an
    optimistic raw-duration upper bound, not an instruction to select it. An
    ending is impossible if even that union cannot reach the lower duration
    band, if sticky source lies later, or if a required chapter group has no
    prefix unit. Retained endings still require semantic and budget review.

    Malformed/ambiguous source or work above the fixed bounds returns the full
    caller-allowed domain as unverified. Callers must narrow choices only when
    status is verified; this helper never creates evidence or selects roles.
    """
    rejected, sticky = set(rejected_beat_ids), set(sticky_beat_ids)
    supplied = None if eligible_beat_ids is None else set(eligible_beat_ids)
    candidate_rows = candidates if isinstance(candidates, list) else []
    caller_domain = list(dict.fromkeys(
        row["id"] for row in candidate_rows if isinstance(row, dict)
        and isinstance(row.get("id"), str) and row["id"]
        and row["id"] not in rejected and (supplied is None or row["id"] in supplied)
    ))

    def unverified(*, invalid_count: int = 0, bound_exceeded: bool = False) -> dict[str, Any]:
        return {
            "status": "unverified", "allowed_final_beat_ids": list(caller_domain),
            "excluded_final_beat_count": 0, "eligible_unit_count": len(caller_domain),
            "endpoint_proofs": [], "semantic_fit_verified": False,
            "invalid_source_count": invalid_count, "bound_exceeded": bound_exceeded,
        }

    try:
        minimum_target = float(minimum_target_seconds)
    except (TypeError, ValueError):
        return unverified(invalid_count=1)
    if not math.isfinite(minimum_target) or minimum_target < 0:
        return unverified(invalid_count=1)
    if (len(caller_domain) > MAX_FINAL_ENDING_DOMAIN_UNITS
            or not isinstance(segments, list)
            or len(segments) > MAX_FINAL_ENDING_SOURCE_SEGMENTS):
        return unverified(bound_exceeded=True)
    if not isinstance(candidates, list) or not isinstance(chapters, list) or not isinstance(plan, dict):
        return unverified(invalid_count=1)
    candidate_ids = [row.get("id") for row in candidates if isinstance(row, dict)]
    source_ids = [row.get("id") for row in segments if isinstance(row, dict)]
    chapter_ids = [row.get("id") for row in chapters if isinstance(row, dict)]
    for values, rows in ((candidate_ids, candidates), (source_ids, segments), (chapter_ids, chapters)):
        if (len(values) != len(rows)
                or any(not isinstance(value, str) or not value for value in values)
                or len(set(values)) != len(values)):
            return unverified(invalid_count=1)
    if any(_source_range(row) is None or not isinstance(row.get("text"), str) for row in segments):
        return unverified(invalid_count=1)
    source_by_id = {row["id"]: row for row in segments}
    by_id = {row["id"]: row for row in candidates}
    ranges: dict[str, dict[str, float]] = {}
    for identifier in caller_domain:
        source_range = _source_range(by_id[identifier])
        if source_range is None or not _complete_unit(by_id[identifier], source_range, segments, source_by_id):
            return unverified(invalid_count=1)
        ranges[identifier] = source_range
    if not sticky <= set(caller_domain):
        return unverified(invalid_count=len(sticky - set(caller_domain)))
    by_chapter: dict[str, set[str]] = {}
    for chapter in chapters:
        beats = chapter.get("beats")
        if (not isinstance(beats, list)
                or any(not isinstance(beat, dict) or not isinstance(beat.get("id"), str)
                       or not beat["id"] for beat in beats)):
            return unverified(invalid_count=1)
        by_chapter[chapter["id"]] = {beat["id"] for beat in beats if beat["id"] in ranges}
    slots = plan.get("slots")
    if not isinstance(slots, list) or not slots:
        return unverified(invalid_count=1)
    groups: list[set[str]] = []
    for slot in slots:
        if not isinstance(slot, dict):
            return unverified(invalid_count=1)
        primary_chapters = slot.get("chapter_ids")
        context_chapters = slot.get("required_context_chapter_ids", [])
        if (not isinstance(primary_chapters, list) or not primary_chapters
                or not isinstance(context_chapters, list)
                or any(not isinstance(value, str) or not value
                       for value in primary_chapters + context_chapters)):
            return unverified(invalid_count=1)
        groups.append(set().union(*(by_chapter.get(value, set()) for value in primary_chapters)))
        groups.extend(by_chapter.get(value, set()) for value in dict.fromkeys(context_chapters))
    domain = sorted(caller_domain, key=lambda value: (ranges[value]["end"], ranges[value]["start"], value))
    duration = max([row["end"] for row in ranges.values()]
                   + [float(row["end"]) for row in segments] + [0.0])
    allowed, proofs = [], []
    for endpoint in domain:
        end = ranges[endpoint]["end"]
        prefix = {value for value in domain if ranges[value]["end"] <= end + .001 + 1e-9}
        # Only approved_seconds is needed. Empty speech input yields the same
        # exact raw source union and avoids repeatedly inspecting word timings.
        upper = story_duration_cost([ranges[value] for value in prefix], [], duration)["approved_seconds"]
        later_sticky_count = sum(ranges[value]["end"] > end + .001 + 1e-9 for value in sticky)
        missing_group_count = sum(not group.intersection(prefix) for group in groups)
        insufficient = upper + BUDGET_TOLERANCE_SECONDS + 1e-9 < minimum_target
        excluded = insufficient or bool(later_sticky_count or missing_group_count)
        if not excluded:
            allowed.append(endpoint)
        proofs.append({
            "beat_id": endpoint, "latest_end_seconds": end,
            "prefix_approved_seconds": upper, "eligible_prefix_unit_count": len(prefix),
            "excluded": excluded, "insufficient_duration": insufficient,
            "later_sticky_count": later_sticky_count, "missing_group_count": missing_group_count,
        })
    return {
        "status": "verified", "allowed_final_beat_ids": allowed,
        "excluded_final_beat_count": len(domain) - len(allowed),
        "eligible_unit_count": len(domain), "endpoint_proofs": proofs,
        "semantic_fit_verified": False, "invalid_source_count": 0, "bound_exceeded": False,
    }
