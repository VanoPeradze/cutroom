"""Deterministic transcript attribution and source-order checks for story slots.

Fragments identify quotations, not editable sub-beats or semantic entailment.
The caller still has to retain complete passages and review their meaning.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from typing import Any
from urllib.parse import quote


EVIDENCE_POLICY_VERSION = "source-quotes-and-order-2026-10-17-v1"
_FRAGMENT_CHARACTERS = 160
_EPSILON = .001
_CLAUSE_END = re.compile(r"[.!?;,:…。\u061f\u061b\u060c]+[\"'”’)\]]*|\n+")


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty source ID.")
    return value


def _identifiers(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple, set)) or isinstance(value, str):
        raise ValueError(f"{label} must contain source IDs.")
    result = [_identifier(item, label) for item in value]
    if isinstance(value, set):
        result.sort()
    if len(result) != len(set(result)) or (nonempty and not result):
        raise ValueError(f"{label} must contain unique source IDs.")
    return result


def _bounds(row: dict[str, Any], label: str) -> tuple[float, float]:
    try:
        if isinstance(row.get("start"), bool) or isinstance(row.get("end"), bool):
            raise ValueError
        start, end = float(row["start"]), float(row["end"])
    except (TypeError, ValueError, KeyError, OverflowError) as exc:
        raise ValueError(f"{label} needs valid source timestamps.") from exc
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError(f"{label} needs increasing finite source timestamps.")
    return start, end


def _indexed_sources(
    candidates: Any, segments: Any,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not isinstance(candidates, list) or not isinstance(segments, list):
        raise ValueError("Evidence requires canonical source beats and segments.")
    segment_by_id: dict[str, dict[str, Any]] = {}
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Source segments must be objects.")
        identifier = _identifier(segment.get("id"), "Segment")
        if identifier in segment_by_id:
            raise ValueError("Duplicate source segment IDs are ambiguous.")
        segment_by_id[identifier] = segment
    beat_by_id: dict[str, dict[str, Any]] = {}
    owners: dict[str, str] = {}
    for beat in candidates:
        if not isinstance(beat, dict):
            raise ValueError("Source beats must be objects.")
        identifier = _identifier(beat.get("id", beat.get("beat_id")), "Beat")
        if identifier in beat_by_id:
            raise ValueError("Duplicate source beat IDs are ambiguous.")
        identifiers = _identifiers(beat.get("segment_ids"), "Beat segments", nonempty=True)
        for segment_id in identifiers:
            if segment_id not in segment_by_id:
                raise ValueError("A beat references an unknown source segment.")
            if segment_id in owners:
                raise ValueError("A source segment has ambiguous beat ownership.")
            owners[segment_id] = identifier
        beat_by_id[identifier] = beat
    return beat_by_id, segment_by_id


def _fragments(text: str) -> list[tuple[int, int]]:
    """Split exact character intervals without synthesizing words or timing."""
    clauses, start = [], 0
    for boundary in _CLAUSE_END.finditer(text):
        clauses.append((start, boundary.end()))
        start = boundary.end()
    if start < len(text):
        clauses.append((start, len(text)))
    result = []
    for left, right in clauses:
        words = list(re.finditer(r"\S+", text[left:right]))
        if not words:
            continue
        cursor = words[0].start() + left
        finish = cursor
        for word in words:
            word_end = word.end() + left
            if finish > cursor and word_end - cursor > _FRAGMENT_CHARACTERS:
                if re.search(r"\w", text[cursor:finish]):
                    result.append((cursor, finish))
                cursor = word.start() + left
            finish = word_end
        if finish > cursor and re.search(r"\w", text[cursor:finish]):
            result.append((cursor, finish))
    return result


def build_story_evidence_catalog(
    candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    allowed_beat_ids: Any = None,
) -> list[dict[str, Any]]:
    """Return exact, bounded source quotations with stable ownership and offsets.

    ``start``/``end`` always retain the full ASR segment's real timestamps.
    Character offsets are attribution positions, never cut permissions.
    """
    beat_by_id, segment_by_id = _indexed_sources(candidates, segments)
    allowed = set(beat_by_id) if allowed_beat_ids is None else set(
        _identifiers(allowed_beat_ids, "Allowed beats"))
    if not allowed <= set(beat_by_id):
        raise ValueError("Evidence permits an unknown source beat.")
    catalog = []
    eligible = []
    for beat_id in allowed:
        beat = beat_by_id[beat_id]
        start, end = _bounds(beat, "Source beat")
        eligible.append((start, end, beat_id, beat))
    for beat_start, beat_end, beat_id, beat in sorted(eligible):
        source = []
        for segment_id in beat["segment_ids"]:
            segment = segment_by_id[segment_id]
            start, end = _bounds(segment, "Source segment")
            text = segment.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Source evidence requires verbatim transcript text.")
            if start < beat_start - _EPSILON or end > beat_end + _EPSILON:
                raise ValueError("Evidence segment falls outside its owning source beat.")
            source.append((start, end, segment_id, text))
        for start, end, segment_id, text in sorted(source):
            for index, (left, right) in enumerate(_fragments(text), 1):
                catalog.append({
                    "id": f"{quote(beat_id, safe='')}:{quote(segment_id, safe='')}:f{index}",
                    "beat_id": beat_id, "segment_id": segment_id,
                    "text": text[left:right], "start": start, "end": end,
                    "char_start": left, "char_end": right,
                })
    return catalog


def _tokens_with_offsets(text: str) -> list[tuple[str, int, int]]:
    result = []
    for match in re.finditer(r"\w+", text):
        normalized = unicodedata.normalize("NFKC", match.group()).casefold()
        result.extend((token, match.start(), match.end()) for token in re.findall(r"\w+", normalized))
    return result


def _complete_word_spans(segment: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Map by the complete token sequence, never substring-search repeated words."""
    words = segment.get("words")
    if segment.get("word_timing_complete") is False or not isinstance(words, list) or not words:
        return None
    source = _tokens_with_offsets(segment["text"])
    labels, spans, cursor = [], [], 0
    previous_end = float(segment["start"])
    for word in words:
        if not isinstance(word, dict) or not isinstance(word.get("word"), str):
            return None
        tokens = _tokens_with_offsets(word["word"])
        if not tokens:
            return None
        try:
            start, end = _bounds(word, "Source word")
        except ValueError:
            return None
        if (start < float(segment["start"]) - _EPSILON or end > float(segment["end"]) + _EPSILON
                or start < previous_end - _EPSILON):
            return None
        labels.extend(token for token, _, _ in tokens)
        matched = source[cursor:cursor + len(tokens)]
        if [item[0] for item in matched] != [item[0] for item in tokens]:
            return None
        spans.append({"start": start, "end": end,
                      "char_start": matched[0][1], "char_end": matched[-1][2]})
        cursor += len(tokens)
        previous_end = end
    if cursor != len(source) or labels != [token for token, _, _ in source]:
        return None
    return spans


def _keep_ranges(rows: Any) -> list[tuple[float, float]]:
    if not isinstance(rows, list) or not rows:
        raise ValueError("Final evidence requires nonempty source keep ranges.")
    result, previous_end = [], -math.inf
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Final keep ranges must be source intervals.")
        start, end = _bounds(row, "Final keep range")
        if start < previous_end - 1e-9:
            raise ValueError("Final keep ranges must be chronological without overlap or repeats.")
        result.append((start, end))
        previous_end = end
    return result


def _protect_citations(
    references: list[dict[str, Any]], segments: dict[str, dict[str, Any]], rows: Any,
) -> None:
    kept = _keep_ranges(rows)
    word_spans: dict[str, list[dict[str, Any]] | None] = {}
    for reference in references:
        identifier = reference["segment_id"]
        if identifier not in word_spans:
            word_spans[identifier] = _complete_word_spans(segments[identifier])
        words = word_spans[identifier]
        protected = ([word for word in words
                      if word["char_start"] < reference["char_end"]
                      and word["char_end"] > reference["char_start"]]
                     if words is not None else [reference])
        if not protected:
            raise ValueError("A quotation has no provable source speech coverage.")
        for span in protected:
            covered = sum(max(0.0, min(span["end"], end) - max(span["start"], start))
                          for start, end in kept)
            if span["end"] - span["start"] - covered > _EPSILON + 1e-9:
                raise ValueError("Final keep ranges omit cited source speech.")


def _definitely_before(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left["segment_id"] == right["segment_id"]:
        return left["char_end"] <= right["char_start"]
    return left["end"] <= right["start"] + 1e-9


def validate_story_evidence(
    slot_map: Any, candidates: list[dict[str, Any]], segments: list[dict[str, Any]], *,
    selected_beat_ids: Any, required_roles: Any = None, rejected_beat_ids: Any = None,
    keep_ranges: Any = None, required_role_orders: Any = None,
) -> dict[str, Any]:
    """Resolve only canonical quotations and reject unsupported source ordering.

    Model prose and model-provided quote/timing objects are discarded. This
    validates attribution and definite chronological inversions; it does not
    establish that a quotation semantically fulfills its assigned story role.
    """
    selected = _identifiers(selected_beat_ids, "Selected beats", nonempty=True)
    rejected = set(_identifiers(rejected_beat_ids, "Rejected beats")) if rejected_beat_ids is not None else set()
    if rejected.intersection(selected):
        raise ValueError("Rejected source material cannot supply selected story evidence.")
    catalog = build_story_evidence_catalog(candidates, segments, allowed_beat_ids=selected)
    by_id = {row["id"]: row for row in catalog}
    beat_by_id, segment_by_id = _indexed_sources(candidates, segments)
    roles = _identifiers(required_roles, "Required roles", nonempty=True) if required_roles is not None else None
    if not isinstance(slot_map, list) or not slot_map:
        raise ValueError("Every story role needs explicit source evidence.")
    clean, indexes = [], set()
    for row in slot_map:
        if not isinstance(row, dict):
            raise ValueError("Story evidence slots must be objects.")
        index = row.get("slot_index")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0 or index in indexes:
            raise ValueError("Story evidence slots need unique nonnegative indexes.")
        purpose = _identifier(row.get("purpose"), "Story purpose")
        primary = _identifiers(row.get("primary_beat_ids"), "Primary beats", nonempty=True)
        context = _identifiers(row.get("context_beat_ids"), "Context beats")
        if not set(primary + context) <= set(selected):
            raise ValueError("Story evidence must belong to selected unrejected beats.")
        evidence = {}
        for kind, beat_ids in (("primary", primary), ("context", context)):
            identifiers = _identifiers(row.get(f"{kind}_evidence_ids"), f"{kind.title()} evidence",
                                       nonempty=bool(beat_ids))
            if any(identifier not in by_id for identifier in identifiers):
                raise ValueError("Story evidence references an unknown or ineligible quotation.")
            if {by_id[identifier]["beat_id"] for identifier in identifiers} != set(beat_ids):
                raise ValueError("Each mapped beat needs its own canonical source quotation.")
            evidence[kind] = identifiers
        witness = _identifier(row.get("temporal_witness_id"), "Temporal witness")
        if witness not in evidence["primary"]:
            raise ValueError("A temporal witness must cite the slot's primary source evidence.")
        identifiers = list(dict.fromkeys(evidence["primary"] + evidence["context"]))
        quotes = [dict(by_id[identifier]) for identifier in identifiers]
        clean.append({
            "slot_index": index, "purpose": purpose,
            "primary_beat_ids": primary, "context_beat_ids": context,
            "beat_ids": list(dict.fromkeys(primary + context)),
            "primary_evidence_ids": evidence["primary"], "context_evidence_ids": evidence["context"],
            "temporal_witness_id": witness, "source_evidence": quotes,
            "role_evidence": "\n".join(reference["text"] for reference in quotes),
        })
        indexes.add(index)
    clean.sort(key=lambda row: row["slot_index"])
    if indexes != set(range(len(clean))):
        raise ValueError("Story evidence slot indexes must be contiguous.")
    purposes = [row["purpose"] for row in clean]
    if roles is not None:
        if required_role_orders is None and purposes != roles:
            raise ValueError("Story evidence must preserve every configured role in order.")
        if not set(roles) <= set(purposes):
            raise ValueError("Story evidence must preserve every configured role.")
    if required_role_orders is not None:
        if not isinstance(required_role_orders, list) or len(required_role_orders) > 64:
            raise ValueError("Invalid required story order groups.")
        for group in required_role_orders:
            if (not isinstance(group, list) or not 2 <= len(group) <= 64
                    or any(not isinstance(role, str) or role not in (roles or []) for role in group)
                    or len(group) != len(set(group))):
                raise ValueError("Invalid required story order group.")
            positions = [purposes.index(role) for role in group]
            if positions != sorted(positions):
                raise ValueError("Story evidence contradicts the explicit required role order.")
    if len({row["purpose"] for row in clean}) != len(clean):
        raise ValueError("Each story purpose must have one explicit evidence slot.")
    witnesses = [by_id[row["temporal_witness_id"]] for row in clean]
    for index, earlier in enumerate(witnesses):
        if any(_definitely_before(later, earlier) for later in witnesses[index + 1:]):
            raise ValueError("Story role evidence is definitely inverted in source order.")
    final_end = max(_bounds(beat_by_id[identifier], "Selected beat")[1] for identifier in selected)
    final_beats = {identifier for identifier in selected
                   if abs(_bounds(beat_by_id[identifier], "Selected beat")[1] - final_end) <= _EPSILON}
    if witnesses[-1]["beat_id"] not in final_beats:
        raise ValueError("The final story role needs primary evidence from the final selected passage.")
    if keep_ranges is not None:
        _protect_citations([reference for row in clean for reference in row["source_evidence"]],
                          segment_by_id, keep_ranges)
    fingerprint = hashlib.sha256(json.dumps(catalog, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "policy_version": EVIDENCE_POLICY_VERSION, "catalog_fingerprint": fingerprint,
        "verification_scope": "source_attribution_and_order",
        "slot_map": clean,
        "order_evidence": [{"slot_index": row["slot_index"], "purpose": row["purpose"],
                            "temporal_witness_id": row["temporal_witness_id"], **dict(witness)}
                           for row, witness in zip(clean, witnesses)],
    }
