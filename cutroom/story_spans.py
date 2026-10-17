"""Independent whole-utterance retention constraints for an exact source set.

These constraints do not assign narrative roles or prove semantic coherence.
Callers must resolve explicit cross-unit prerequisites into the selected source
set before building them. Every utterance inside that set is mandatory, whether
or not a fine quotation was chosen as a role's temporal anchor.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable

from .story_budget import POLICY_VERSION, compact_story_pauses_to_target, story_duration_cost
from .utils import normalize_text


SOURCE_SPAN_POLICY_VERSION = "whole-source-utterances-2026-10-18-v1"
SOURCE_SPAN_SUMMARY_SOURCE = "canonical_retained_source_utterances"
_EPSILON = .001
_SENTENCE_END = re.compile(r"[.!?\u2026\u3002\uff01\uff1f][\"'\u201d\u2019\u00bb)\]]*$")


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Source-span constraints need canonical source IDs.")
    return value


def _identifiers(value: Iterable[str], *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        raise ValueError("Source-span constraints need source-ID collections.")
    result = [_identifier(item) for item in value]
    if len(result) != len(set(result)) or (nonempty and not result):
        raise ValueError("Source-span constraints need unique, nonempty source IDs.")
    return sorted(result) if isinstance(value, set) else result


def _bounds(row: Any) -> tuple[float, float]:
    if not isinstance(row, dict):
        raise ValueError("Source-span constraints need canonical source intervals.")
    values = []
    for key in ("start", "end"):
        value = row.get(key)
        try:
            valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value))
            number = float(value) if valid else math.nan
        except (OverflowError, ValueError):
            valid, number = False, math.nan
        if not valid:
            raise ValueError("Source-span constraints need finite source timestamps.")
        values.append(number)
    start, end = values
    if start < 0 or end <= start:
        raise ValueError("Source-span constraints need increasing source intervals.")
    return start, end


def _indexed_source(candidates: Any, segments: Any):
    if not isinstance(candidates, list) or not isinstance(segments, list):
        raise ValueError("Source-span constraints need canonical source units and ASR.")
    segment_by_id, candidate_by_id, owners = {}, {}, {}
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("Canonical ASR segments must be objects.")
        identifier = _identifier(segment.get("id"))
        _bounds(segment)
        if identifier in segment_by_id:
            raise ValueError("Duplicate canonical ASR segment IDs are ambiguous.")
        segment_by_id[identifier] = segment
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("Canonical source units must be objects.")
        identifier = _identifier(candidate.get("id", candidate.get("beat_id")))
        _bounds(candidate)
        if identifier in candidate_by_id:
            raise ValueError("Duplicate canonical source unit IDs are ambiguous.")
        identifiers = _identifiers(candidate.get("segment_ids"), nonempty=True)
        for segment_id in identifiers:
            if segment_id not in segment_by_id:
                raise ValueError("A source unit references an unknown ASR segment.")
            if segment_id in owners:
                raise ValueError("An ASR segment has ambiguous source-unit ownership.")
            owners[segment_id] = identifier
        candidate_by_id[identifier] = candidate
    return candidate_by_id, segment_by_id


def _complete_source_unit(candidate, segment_by_id, all_segments):
    start, end = _bounds(candidate)
    source = [segment_by_id[value] for value in candidate["segment_ids"]]
    ordered = sorted(source, key=lambda row: (*_bounds(row), row["id"]))
    overlapping = [row for row in all_segments
                   if float(row["start"]) < end - 1e-9 and float(row["end"]) > start + 1e-9]
    if ([row["id"] for row in source] != [row["id"] for row in ordered]
            or {row["id"] for row in overlapping} != set(candidate["segment_ids"])
            or abs(ordered[0]["start"] - start) > 1e-9
            or abs(max(row["end"] for row in ordered) - end) > 1e-9
            or any(float(row["start"]) < start or float(row["end"]) > end for row in source)):
        raise ValueError("A retained source unit must contain complete canonical ASR segments.")
    if any(not isinstance(row.get("text"), str) or not row["text"].strip() for row in source):
        raise ValueError("Every retained utterance needs verbatim canonical ASR text.")
    text = " ".join(row["text"] for row in source)
    if (not isinstance(candidate.get("text"), str)
            or normalize_text(candidate["text"]) != normalize_text(text)
            or not _SENTENCE_END.search(text.strip())):
        raise ValueError("A retained source unit must preserve complete source text and ending.")
    return ordered


def _fingerprint_value(value: Any) -> Any:
    """Encode exact source types, including invalid word floats, as valid JSON.

    Nonfinite word times still trigger the budget's full-utterance fallback.
    Their hexadecimal float spelling is retained rather than dropped or emitted
    as the nonstandard JSON NaN/Infinity tokens. Type tags avoid aliasing a
    source object with an encoded float or changing exact numeric identity.
    """
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, float):
        return ["float", value.hex()]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, list):
        return ["list", [_fingerprint_value(item) for item in value]]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return ["dict", [[key, _fingerprint_value(value[key])] for key in sorted(value)]]
    raise ValueError("Canonical source timing must have a stable JSON source identity.")


def build_source_span_constraints(
    candidates: list[dict[str, Any]], segments: list[dict[str, Any]], *,
    selected_beat_ids: Iterable[str], rejected_beat_ids: Iterable[str] = (),
) -> dict[str, Any]:
    """Bind all utterances of complete selected units to the shared pause policy.

    Incomplete/invalid word timing uses the existing budget's whole-utterance
    fallback. No negation parser, new cut permission, inferred prerequisite,
    semantic approval, or change to the fine-quotation evidence proof is added.
    """
    selected = _identifiers(selected_beat_ids, nonempty=True)
    rejected = _identifiers(rejected_beat_ids)
    candidate_by_id, segment_by_id = _indexed_source(candidates, segments)
    if not set(selected) <= set(candidate_by_id):
        raise ValueError("Source-span constraints reference an unknown selected source unit.")
    # Reproof may receive only retained units. Record outside-domain rejection
    # IDs without claiming to authenticate them; the full-domain caller checks
    # exclusion authority separately. The retained set must remain disjoint.
    if set(selected).intersection(rejected):
        raise ValueError("Rejected source units cannot supply retained source spans.")
    selected.sort(key=lambda value: (*_bounds(candidate_by_id[value]), value))
    utterances, approved, exact_source = [], [], []
    for identifier in selected:
        candidate = candidate_by_id[identifier]
        source = _complete_source_unit(candidate, segment_by_id, segments)
        start, end = _bounds(candidate)
        if approved and start < approved[-1]["end"] - 1e-9:
            raise ValueError("Retained source units must be chronological without overlap.")
        approved.append({"start": start, "end": end})
        for segment in source:
            utterances.append({"beat_id": identifier, "segment_id": segment["id"],
                               "start": segment["start"], "end": segment["end"], "text": segment["text"]})
        exact_source.append({
            # Beat text is a derived presentation field. Its normalized source
            # equivalence was checked above; only the actual ASR wording owns
            # the fingerprint, including its exact whitespace and punctuation.
            "unit": {key: candidate[key] for key in ("start", "end", "segment_ids")}
                    | {"text": " ".join(segment["text"] for segment in source)},
            "beat_id": identifier,
            "segments": [{key: segment[key] for key in ("id", "start", "end", "text")}
                         | {"words_present": "words" in segment, "words": segment.get("words"),
                            "word_timing_complete_present": "word_timing_complete" in segment,
                            "word_timing_complete": segment.get("word_timing_complete")}
                         for segment in source],
        })
    duration = max(float(row["end"]) for row in segments)
    cost = story_duration_cost(approved, segments, duration)
    # Ask the existing fitter for its minimum; no second timing/handle policy.
    required = compact_story_pauses_to_target(approved, segments, duration, cost["minimum_safe_seconds"])
    if required is None:
        raise ValueError("The shared source pause policy could not establish retention locks.")
    fingerprint_input = {"policy_version": SOURCE_SPAN_POLICY_VERSION,
                         "budget_policy_version": POLICY_VERSION, "source": exact_source}
    try:
        serialized = json.dumps(_fingerprint_value(fingerprint_input), ensure_ascii=False,
                                sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Canonical source timing must have a stable serializable identity.") from exc
    return {
        "policy_version": SOURCE_SPAN_POLICY_VERSION, "budget_policy_version": POLICY_VERSION,
        "verification_scope": "source_retention_only", "selected_beat_ids": selected,
        "rejected_beat_ids": sorted(rejected), "segment_ids": [row["segment_id"] for row in utterances],
        "utterances": utterances, "approved_ranges": approved, "required_minimum_ranges": required,
        "source_fingerprint": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
    }


def validate_source_span_constraints(
    proof: Any, candidates: list[dict[str, Any]], segments: list[dict[str, Any]], *,
    selected_beat_ids: Iterable[str], rejected_beat_ids: Iterable[str] = (),
    keep_ranges: list[dict[str, float]] | None = None,
) -> dict[str, Any]:
    """Recompute exact source locks and ensure none were omitted downstream.

    Extra footage requires separate caller authorization (including explicit
    manual restores); this retention-only proof does not authorize additions.
    """
    canonical = build_source_span_constraints(candidates, segments,
        selected_beat_ids=selected_beat_ids, rejected_beat_ids=rejected_beat_ids)
    if not isinstance(proof, dict) or proof != canonical:
        raise ValueError("Source-span constraints do not match the current exact retained source.")
    if keep_ranges is not None:
        if not isinstance(keep_ranges, list) or not keep_ranges:
            raise ValueError("Retained source spans require a nonempty chronological timeline.")
        kept, previous_end = [], -math.inf
        for row in keep_ranges:
            start, end = _bounds(row)
            if start < previous_end - 1e-9:
                raise ValueError("Retained source spans cannot be reordered, overlapped or repeated.")
            kept.append((start, end))
            previous_end = end
        for required in canonical["required_minimum_ranges"]:
            covered = sum(max(0.0, min(required["end"], end) - max(required["start"], start))
                          for start, end in kept)
            if required["end"] - required["start"] - covered > _EPSILON + 1e-9:
                raise ValueError("The timeline omits mandatory whole-utterance source speech or handles.")
    return canonical


def whole_utterance_story_summary(proof: dict[str, Any]) -> str:
    """Display every retained ASR utterance verbatim under a separate label.

    Call this with a freshly built/revalidated sidecar. Like the sidecar, this
    display establishes source retention and does not claim narrative meaning.
    """
    if (not isinstance(proof, dict) or proof.get("policy_version") != SOURCE_SPAN_POLICY_VERSION
            or proof.get("budget_policy_version") != POLICY_VERSION
            or proof.get("verification_scope") != "source_retention_only"
            or not isinstance(proof.get("source_fingerprint"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", proof["source_fingerprint"])):
        raise ValueError("Whole-utterance summaries require current source-span constraints.")
    selected = _identifiers(proof.get("selected_beat_ids"), nonempty=True)
    utterances = proof.get("utterances")
    if not isinstance(utterances, list) or not utterances:
        raise ValueError("Whole-utterance summaries require complete canonical ASR records.")
    identifiers, owners, positions, text = [], set(), [], []
    for row in utterances:
        start, end = _bounds(row)
        identifier, owner = _identifier(row.get("segment_id")), _identifier(row.get("beat_id"))
        if owner not in selected or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError("A whole-utterance summary must preserve selected source text and ownership.")
        identifiers.append(identifier)
        owners.add(owner)
        positions.append((start, end, identifier))
        text.append(row["text"])
    if (len(identifiers) != len(set(identifiers)) or identifiers != proof.get("segment_ids")
            or owners != set(selected) or positions != sorted(positions)):
        raise ValueError("Whole-utterance summary records must match unique chronological source segments.")
    return "Retained source utterances:\n" + "\n".join(f"\u201c{value}\u201d" for value in text)
