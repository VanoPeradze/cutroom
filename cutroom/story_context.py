"""Pure whole-source indexes and exact candidate retrieval for Story AI.

Summary prose is an unverified retrieval aid. These helpers never approve a
story, trim canonical speech, change identifiers, or perform model/network I/O.
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable

from .story_budget import StoryPlanningError

INDEX_POLICY_VERSION = "whole-source-index-2026-10-20-v1"
_EPSILON = .001


class StoryContextError(StoryPlanningError):
    def __init__(self, message: str, *, reason: str = "invalid_story_source_context"):
        super().__init__(message, {"outcome": "technical_error", "reason": reason,
                                  "applied_to_timeline": False})


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StoryContextError(f"{label} needs a nonempty canonical identifier.")
    return value


def _identifiers(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise StoryContextError(f"{label} needs a list of canonical identifiers.")
    output = [_identifier(item, label) for item in value]
    if len(output) != len(set(output)) or (nonempty and not output):
        raise StoryContextError(f"{label} needs unique canonical identifiers.")
    return output


def _bounds(row: dict[str, Any], label: str) -> tuple[float, float]:
    try:
        if isinstance(row.get("start"), bool) or isinstance(row.get("end"), bool):
            raise ValueError
        start, end = float(row["start"]), float(row["end"])
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        raise StoryContextError(f"{label} needs finite source timestamps.") from exc
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise StoryContextError(f"{label} needs increasing finite source timestamps.")
    return start, end


def _duration(row: dict[str, Any], label: str) -> float:
    start, end = _bounds(row, label)
    value = row.get("duration", end - start)
    try:
        if isinstance(value, bool):
            raise ValueError
        duration = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StoryContextError(f"{label} needs a valid source duration.") from exc
    if not math.isfinite(duration) or duration <= 0 or abs(duration - (end - start)) > _EPSILON + 1e-9:
        raise StoryContextError(f"{label} duration differs from its canonical timestamps.")
    return duration


def _chapter_rows(chapters: Any) -> list[dict[str, Any]]:
    if not isinstance(chapters, list):
        raise StoryContextError("Source chapters must be canonical objects.")
    seen_chapters, seen_beats, segment_owners = set(), set(), {}
    output = []
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise StoryContextError("Source chapters must be canonical objects.")
        chapter_id = _identifier(chapter.get("id"), "Chapter")
        if chapter_id in seen_chapters:
            raise StoryContextError("Duplicate chapter identifiers are ambiguous.")
        seen_chapters.add(chapter_id)
        left, right = _bounds(chapter, "Chapter")
        _duration(chapter, "Chapter")
        beats = chapter.get("beats")
        if not isinstance(beats, list) or not beats:
            raise StoryContextError("A source chapter needs complete canonical beats.")
        actual = []
        for beat in beats:
            if not isinstance(beat, dict):
                raise StoryContextError("Source beats must be canonical objects.")
            identifier = _identifier(beat.get("id"), "Beat")
            if identifier in seen_beats:
                raise StoryContextError("A source beat needs one canonical chapter owner.")
            seen_beats.add(identifier)
            actual.append(identifier)
            start, end = _bounds(beat, "Beat")
            _duration(beat, "Beat")
            if start < left - _EPSILON or end > right + _EPSILON:
                raise StoryContextError("A source beat falls outside its canonical chapter.")
            for segment_id in _identifiers(beat.get("segment_ids"), "Beat segments", nonempty=True):
                if segment_id in segment_owners:
                    raise StoryContextError("A source segment needs one canonical beat owner.")
                segment_owners[segment_id] = identifier
        if "beat_ids" in chapter:
            declared = _identifiers(chapter["beat_ids"], "Chapter beats", nonempty=True)
            if declared != actual:
                raise StoryContextError("Chapter beat references differ from canonical ownership/order.")
        output.append(chapter)
    return sorted(output, key=lambda row: (*_bounds(row, "Chapter"), row["id"]))


def _excerpt(text: Any, limit: int) -> str:
    if not isinstance(text, str):
        raise StoryContextError("Chapter interpretation text must be a string.")
    if len(text) <= limit:
        return text
    marker = " [omitted] "
    room = limit - 2 * len(marker)
    # Small caps retain beginning/end explicitly; no canonical text uses this.
    if room < 3:
        marker = " […] "
        room = limit - len(marker)
        left = room // 2
        return text[:left] + marker + text[-(room - left):]
    part = room // 3
    middle = max(part, len(text) // 2 - part // 2)
    return text[:part] + marker + text[middle:middle + part] + marker + text[-(room - 2 * part):]


def _spread(values: list[Any], maximum: int) -> list[Any]:
    if len(values) <= maximum:
        return values
    if maximum == 1:
        return [values[len(values) // 2]]
    return [values[round(index * (len(values) - 1) / (maximum - 1))] for index in range(maximum)]


def build_whole_recording_index(
    chapters: list[dict[str, Any]], summaries: list[dict[str, Any]], *,
    summary_char_limit: int = 320, key_point_char_limit: int | None = None,
    max_key_points: int = 3,
) -> dict[str, Any]:
    """Retain every chapter/beat/source reference; bound only unverified prose.

    The caller budgets its complete request including brief/schema/output reserve.
    It may call again with smaller prose caps; IDs/clock coverage never shrink.
    This index is not source evidence and cannot confer semantic approval.
    """
    if (isinstance(summary_char_limit, bool) or not isinstance(summary_char_limit, int)
            or summary_char_limit < 16):
        raise StoryContextError("Summary excerpt limit must be an integer of at least 16.")
    if key_point_char_limit is None:
        key_point_char_limit = min(96, summary_char_limit)
    if (isinstance(key_point_char_limit, bool) or not isinstance(key_point_char_limit, int)
            or key_point_char_limit < 16 or isinstance(max_key_points, bool)
            or not isinstance(max_key_points, int) or max_key_points < 1):
        raise StoryContextError("Interpretation excerpt controls must be positive bounded integers.")
    ordered = _chapter_rows(chapters)
    if not isinstance(summaries, list):
        raise StoryContextError("Chapter summaries must be an explicitly unverified index.")
    known = {row["id"]: row for row in ordered}
    by_id = {}
    for summary in summaries:
        if not isinstance(summary, dict):
            raise StoryContextError("Chapter summaries must be objects.")
        identifier = _identifier(summary.get("id"), "Summary chapter")
        if identifier in by_id or identifier not in known:
            raise StoryContextError("Summary chapter IDs must be exact and unique.")
        by_id[identifier] = summary
    if set(by_id) != set(known):
        raise StoryContextError("Every canonical chapter needs its corresponding summary index.")
    projected, beat_index = [], []
    for chapter in ordered:
        identifier = chapter["id"]
        summary = by_id[identifier]
        beat_ids = [beat["id"] for beat in chapter["beats"]]
        references = {}
        for field, domain in (("key_beat_ids", set(beat_ids)), ("depends_on", set(known))):
            values = _identifiers(summary.get(field, []), "Summary " + field)
            if not set(values) <= domain:
                raise StoryContextError("Unverified summaries cannot introduce foreign source references.")
            references[field] = list(values)
        text_fields = {}
        for field in ("key_points", "unresolved_questions"):
            values = summary.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise StoryContextError("Chapter interpretation points must be strings.")
            text_fields[field] = [_excerpt(value, key_point_char_limit) for value in _spread(values, max_key_points)]
        projected.append({
            "id": identifier, "start": chapter["start"], "end": chapter["end"],
            "duration": chapter.get("duration", _duration(chapter, "Chapter")),
            "beat_ids": beat_ids,
            "title": _excerpt(summary.get("title", ""), min(120, summary_char_limit)),
            "summary": _excerpt(summary.get("summary", ""), summary_char_limit),
            "role": _excerpt(summary.get("role", "other"), min(80, summary_char_limit)),
            "summary_source": _excerpt(summary.get("summary_source", "unverified"), 80),
            "interpretation_status": "unverified_summary_index", **references, **text_fields,
        })
        for beat in sorted(chapter["beats"], key=lambda row: (*_bounds(row, "Beat"), row["id"])):
            beat_index.append({"id": beat["id"], "chapter_id": identifier,
                               "start": beat["start"], "end": beat["end"],
                               "segment_ids": list(beat["segment_ids"])})
    return {"policy_version": INDEX_POLICY_VERSION, "interpretation_status": "unverified_summary_index",
            "source_evidence_status": "retrieve_complete_canonical_candidates_before_selection",
            "chapters": projected, "source_beat_index": beat_index,
            "coverage": {"chapter_count": len(ordered), "beat_count": len(beat_index),
                         "segment_count": sum(len(row["segment_ids"]) for row in beat_index)}}


def retrieve_candidate_source(
    chapters: list[dict[str, Any]], segments: list[dict[str, Any]], chapter_ids: list[str],
) -> dict[str, Any]:
    """Retrieve all complete canonical units for the selected/context chapters.

    Pass the union of planned primary and required-context chapter IDs. Full source
    wording and ASR word metadata are detached exact copies, never index excerpts.
    """
    ordered = _chapter_rows(chapters)
    wanted = _identifiers(chapter_ids, "Retrieved chapters", nonempty=True)
    if not set(wanted) <= {chapter["id"] for chapter in ordered}:
        raise StoryContextError("Candidate retrieval requested a foreign source chapter.")
    if not isinstance(segments, list):
        raise StoryContextError("Canonical transcript segments must be objects.")
    by_id = {}
    for segment in segments:
        if not isinstance(segment, dict):
            raise StoryContextError("Canonical transcript segments must be objects.")
        identifier = _identifier(segment.get("id"), "Segment")
        if identifier in by_id:
            raise StoryContextError("Duplicate transcript segment identifiers are ambiguous.")
        _bounds(segment, "Segment")
        by_id[identifier] = segment
    # Validate ownership even outside the selected pages; stale source references
    # must not become trustworthy merely because this request did not select them.
    for chapter in ordered:
        for beat in chapter["beats"]:
            start, end = _bounds(beat, "Beat")
            for identifier in beat["segment_ids"]:
                if identifier not in by_id:
                    raise StoryContextError("A source beat refers to an unknown canonical utterance.")
                segment = by_id[identifier]
                left, right = _bounds(segment, "Segment")
                if left < start - _EPSILON or right > end + _EPSILON:
                    raise StoryContextError("A canonical utterance falls outside its owning beat.")
                if not isinstance(segment.get("text"), str) or not segment["text"].strip():
                    raise StoryContextError("Retrieved canonical utterances need verbatim source wording.")
    selected = [chapter for chapter in ordered if chapter["id"] in set(wanted)]
    beats = [beat for chapter in selected for beat in chapter["beats"]]
    needed = {identifier for beat in beats for identifier in beat["segment_ids"]}
    selected_segments = sorted((by_id[value] for value in needed),
                               key=lambda row: (*_bounds(row, "Segment"), row["id"]))
    return {"chapter_ids": [chapter["id"] for chapter in selected],
            "beats": copy.deepcopy(beats), "segments": copy.deepcopy(selected_segments)}


def bounded_source_pages(
    units: list[dict[str, Any]], make_payload: Callable[[list[dict[str, Any]]], Any],
    fits_payload: Callable[[Any], bool],
) -> list[list[dict[str, Any]]]:
    """Group atomic complete units using the caller's full-request budget check.

    No model/network execution occurs here. Each input object occurs exactly once;
    its text/IDs/timing remain unchanged. A too-large single unit fails explicitly.
    """
    if not isinstance(units, list) or any(not isinstance(row, dict) for row in units):
        raise StoryContextError("Source pages require complete canonical source-unit objects.")
    identifiers = [_identifier(row.get("id"), "Source unit") for row in units]
    if len(identifiers) != len(set(identifiers)):
        raise StoryContextError("Source pages require unique canonical source-unit identifiers.")
    pages, current = [], []
    for unit in units:
        candidate = current + [unit]
        if fits_payload(make_payload(copy.deepcopy(candidate))):
            current = candidate
            continue
        if current:
            pages.append(copy.deepcopy(current))
        if not fits_payload(make_payload(copy.deepcopy([unit]))):
            raise StoryContextError("A complete canonical source unit exceeds the local context budget; "
                                    "its wording and instructions were preserved.", reason="story_input_context_limit")
        current = [unit]
    if current:
        pages.append(copy.deepcopy(current))
    return pages


def bounded_contiguous_source_windows(
    units: list[dict[str, Any]], make_payload: Callable[[list[dict[str, Any]]], Any],
    fits_payload: Callable[[Any], bool],
) -> list[list[dict[str, Any]]]:
    """Cover all fitting contiguous subsequences with maximal request windows.

    Contiguous means adjacent units in canonical source-clock order, not proof of
    one idea or permission to select them. The caller must retrieve/validate the
    canonical units first and budget the complete payload plus output reserve.
    All source wording, identifiers and metadata remain detached exact copies.
    """
    if not isinstance(units, list) or any(not isinstance(row, dict) for row in units):
        raise StoryContextError("Source windows require complete canonical source-unit objects.")
    identifiers = [_identifier(row.get("id"), "Source unit") for row in units]
    if len(identifiers) != len(set(identifiers)):
        raise StoryContextError("Source windows require unique canonical source-unit identifiers.")
    ordered = sorted(units, key=lambda row: (*_bounds(row, "Source unit"), row["id"]))

    def fits(start: int, end: int) -> bool:
        return bool(fits_payload(make_payload(copy.deepcopy(ordered[start:end]))))

    # Never skip an oversized unit, even at the tail of a long source.
    for start in range(len(ordered)):
        if not fits(start, start + 1):
            raise StoryContextError("A complete canonical source unit exceeds the local context budget; "
                                    "its wording and instructions were preserved.", reason="story_input_context_limit")
    windows, previous_end = [], -1
    for start in range(len(ordered)):
        furthest = start + 1
        # Payload/schema builders need not have a monotone size function. A
        # failed prefix must not hide a later fitting window from this start.
        for end in range(start + 2, len(ordered) + 1):
            if fits(start, end):
                furthest = end
        if furthest > previous_end:
            windows.append(copy.deepcopy(ordered[start:furthest]))
            previous_end = furthest
    return windows
