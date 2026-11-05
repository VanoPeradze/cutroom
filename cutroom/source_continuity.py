"""Verify an explicit continuity constraint on proposed source-time ranges.

This checks the Director draft's source selection only. It does not inspect a
manual sequence, camera/source switches, encoded output or semantic coherence.
"""
from __future__ import annotations

import math
from numbers import Real
from typing import Any, NoReturn

from .instruction_contract import explicit_source_continuity_requested
from .story_budget import StoryPlanningError
from .cache_keys import stable_fingerprint


def continuous_source_playback(candidates, segments, selected_beat_ids):
    """Bind one unchanged source interval, including all inter-utterance audio.

    Analysis-unit boundaries are not playback cuts. The interval is permitted
    only when every canonical utterance overlapping it is retained completely.
    Absence of ASR in a gap is not evidence of silence; that audio is kept too.
    This mechanical binding grants no semantic or transcription approval.
    """
    if (not isinstance(selected_beat_ids, list) or not selected_beat_ids
            or any(not isinstance(v, str) for v in selected_beat_ids)
            or len(selected_beat_ids) != len(set(selected_beat_ids))):
        raise ValueError("Continuous playback needs unique ordered source units.")
    by_id = {row['id']: row for row in candidates}
    if len(by_id) != len(candidates) or any(v not in by_id for v in selected_beat_ids):
        raise ValueError("Continuous playback source identity is ambiguous.")
    selected = [by_id[v] for v in selected_beat_ids]
    previous = -1.
    wanted = []
    for row in selected:
        start, end = row.get('start'), row.get('end')
        ids = row.get('segment_ids')
        if (not _finite_real(start) or not _finite_real(end) or start < previous or end <= start
                or start < 0 or not isinstance(ids, list) or not ids
                or any(not isinstance(v, str) for v in ids)):
            raise ValueError("Continuous playback units must be complete and chronological.")
        wanted.extend(ids)
        previous = end
    if len(wanted) != len(set(wanted)):
        raise ValueError("Continuous playback cannot repeat source utterances.")
    start, end = selected[0]['start'], selected[-1]['end']
    source = []
    for row in segments:
        left, right = row.get('start'), row.get('end')
        if not _finite_real(left) or not _finite_real(right) or left < 0 or right <= left:
            raise ValueError("Continuous playback needs canonical source timestamps.")
        if left < end and right > start:
            if left < start or right > end:
                raise ValueError("Continuous playback clips a canonical utterance.")
            source.append({k: row[k] for k in ('id', 'start', 'end', 'text')})
    if ([row['id'] for row in source] != wanted
            or not source or source[0]['start'] != start or source[-1]['end'] != end):
        raise ValueError("Continuous playback omits intervening canonical speech or changes its boundaries.")
    for unit in selected:
        rows = [r for r in source if r['id'] in unit['segment_ids']]
        if (rows[0]['start'] != unit['start'] or rows[-1]['end'] != unit['end']
                or ' '.join(str(unit.get('text') or '').split()) != ' '.join(' '.join(r['text'] for r in rows).split())):
            raise ValueError("Continuous playback changes canonical source text or ownership.")
    facts = {'policy': 'continuous-source-playback-v1', 'selected_beat_ids': list(selected_beat_ids),
             'source': source, 'playback_ranges': [{'start': start, 'end': end}]}
    return {**facts, 'fingerprint': stable_fingerprint('continuous-source-playback-v1', facts),
            'gap_audio': 'preserved_unverified', 'semantic_verified': False}


def _finite_real(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, Real):
        return False
    try:
        return math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def _conflict(violation: str, range_index: int | None = None) -> NoReturn:
    diagnostic: dict[str, Any] = {
        "kind": "instruction_contract",
        "reason": "explicit_source_continuity_conflict",
        "outcome": "constraint_conflict",
        "applied_to_timeline": False,
        "verification_scope": "proposed_director_draft",
        "mechanical_only": True,
        "violation": violation,
    }
    if range_index is not None:
        diagnostic["range_index"] = range_index
    raise StoryPlanningError(
        "The proposed draft does not preserve the explicitly requested continuous source passage. "
        "No new draft was applied; the existing edit was kept.",
        diagnostic,
    )


def validate_explicit_source_continuity(
    brief: dict[str, Any], source_ranges: list[dict[str, Any]], source_duration: float,
) -> dict[str, Any]:
    """Return mechanical proof or refuse an explicit source-continuity violation.

    Outer trimming is allowed. Multiple ranges are allowed only when each starts
    exactly where the preceding range ends; no sorting, merging, rounding or gap
    tolerance may conceal a source-time omission, repetition or reversal. Saved
    canonical endpoints must agree exactly rather than merely be close.

    One output or one semantic unit does not activate this check. The report
    deliberately makes no claim about the current manual timeline or export.
    """
    proof: dict[str, Any] = {
        "status": "not_requested",
        "verification_scope": "proposed_director_draft",
        "mechanical_only": True,
        "source_continuity_verified": False,
        "semantic_coherence_verified": False,
        "final_export_verified": False,
    }
    if not explicit_source_continuity_requested(brief):
        return proof
    if not _finite_real(source_duration) or source_duration <= 0:
        _conflict("invalid_source_duration")
    if not isinstance(source_ranges, list) or not source_ranges:
        _conflict("missing_source_ranges")

    previous_end: Real | None = None
    first_start: Real | None = None
    for index, row in enumerate(source_ranges):
        if not isinstance(row, dict):
            _conflict("invalid_source_range", index)
        start, end = row.get("start"), row.get("end")
        if not _finite_real(start) or not _finite_real(end):
            _conflict("invalid_source_coordinates", index)
        if start < 0 or start >= end or end > source_duration:
            _conflict("source_range_out_of_bounds", index)
        if previous_end is not None and start != previous_end:
            _conflict("noncontiguous_source_ranges", index)
        if first_start is None:
            first_start = start
        previous_end = end

    proof.update(
        status="fulfilled",
        source_continuity_verified=True,
        verification_basis={
            "kind": "ordered_contiguous_source_time_ranges",
            "checked_range_count": len(source_ranges),
            "source_start": float(first_start),
            "source_end": float(previous_end),
            "source_duration": float(source_duration),
            "outer_trims_allowed": True,
            "adjacency": "exact",
        },
    )
    return proof
