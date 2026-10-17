"""Display complete cited source excerpts without generating narrative claims.

The input must be a proof returned by ``validate_story_evidence`` for the
retained selection. This module checks that the proof's references agree with
one another; it cannot authenticate transcript text without the source catalog
or establish whether uncited speech changes the meaning of the excerpts.
Editorial completeness and source retention remain the caller's checks.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .story_evidence import EVIDENCE_POLICY_VERSION


SUMMARY_SOURCE = "canonical_cited_source_excerpts"
_REFERENCE_FIELDS = (
    "id", "beat_id", "segment_id", "text", "start", "end", "char_start", "char_end",
)


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Source excerpts need nonempty canonical references.")
    return value


def _identifiers(value: Any, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Source excerpts need canonical reference lists.")
    result = [_identifier(item) for item in value]
    if len(result) != len(set(result)) or (nonempty and not result):
        raise ValueError("Source excerpt references must be unique and complete.")
    return result


def _reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or any(key not in value for key in _REFERENCE_FIELDS):
        raise ValueError("Source excerpts need complete canonical quotation records.")
    result = {key: value[key] for key in _REFERENCE_FIELDS}
    for key in ("id", "beat_id", "segment_id"):
        _identifier(result[key])
    if not isinstance(result["text"], str) or not result["text"].strip():
        raise ValueError("Source excerpts need verbatim quotation text.")
    for key in ("start", "end"):
        number = result[key]
        if (not isinstance(number, (int, float)) or isinstance(number, bool)
                or not math.isfinite(number)):
            raise ValueError("Source excerpts need finite canonical timestamps.")
    if result["start"] < 0 or result["end"] <= result["start"]:
        raise ValueError("Source excerpts need increasing canonical timestamps.")
    for key in ("char_start", "char_end"):
        if not isinstance(result[key], int) or isinstance(result[key], bool):
            raise ValueError("Source excerpts need canonical character offsets.")
    if (result["char_start"] < 0 or result["char_end"] <= result["char_start"]
            or result["char_end"] - result["char_start"] != len(result["text"])):
        raise ValueError("Source excerpt text must preserve its complete character interval.")
    return result


def extractive_story_summary(proof: dict[str, Any]) -> str:
    """Quote every cited primary/context fragment once in source chronology.

    Reference identity, rather than repeated wording, controls deduplication.
    Quotes stay separate and complete, including negations and qualifications;
    no character limit silently removes their endings or later cited context.
    Nothing is read from model summaries, role interpretations, or uncited
    source material. The display does not promote context to primary evidence.
    """
    if (not isinstance(proof, dict)
            or proof.get("policy_version") != EVIDENCE_POLICY_VERSION
            or proof.get("verification_scope") != "source_attribution_and_order"
            or not isinstance(proof.get("catalog_fingerprint"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", proof["catalog_fingerprint"])):
        raise ValueError("Source excerpts require a current canonical evidence proof.")
    slots = proof.get("slot_map")
    witnesses = proof.get("order_evidence")
    if (not isinstance(slots, list) or not slots or not isinstance(witnesses, list)
            or len(witnesses) != len(slots)):
        raise ValueError("Source excerpts require every canonical evidence slot.")

    references: dict[str, dict[str, Any]] = {}
    segment_owners: dict[str, tuple[str, float, float]] = {}
    purposes = set()
    for index, (slot, witness) in enumerate(zip(slots, witnesses)):
        if (not isinstance(slot, dict) or not isinstance(witness, dict)
                or type(slot.get("slot_index")) is not int or slot["slot_index"] != index):
            raise ValueError("Source excerpt slots must preserve canonical indexes.")
        purpose = _identifier(slot.get("purpose"))
        if purpose in purposes:
            raise ValueError("Source excerpt slots must preserve unique story purposes.")
        purposes.add(purpose)
        primary = _identifiers(slot.get("primary_beat_ids"), nonempty=True)
        context = _identifiers(slot.get("context_beat_ids"))
        if slot.get("beat_ids") != list(dict.fromkeys(primary + context)):
            raise ValueError("Source excerpt ownership must match the retained role beats.")
        primary_ids = _identifiers(slot.get("primary_evidence_ids"), nonempty=True)
        context_ids = _identifiers(slot.get("context_evidence_ids"), nonempty=bool(context))
        expected_ids = list(dict.fromkeys(primary_ids + context_ids))
        rows = slot.get("source_evidence")
        if not isinstance(rows, list):
            raise ValueError("Source excerpts require canonical quotation records.")
        quotes = [_reference(row) for row in rows]
        if [row["id"] for row in quotes] != expected_ids:
            raise ValueError("Source excerpts may contain only the slot's cited quotations.")
        local = {row["id"]: row for row in quotes}
        for ids, owners in ((primary_ids, primary), (context_ids, context)):
            if {local[identifier]["beat_id"] for identifier in ids} != set(owners):
                raise ValueError("Source excerpt citations must match their canonical beat owners.")
        witness_id = _identifier(slot.get("temporal_witness_id"))
        if (witness_id not in primary_ids or witness.get("slot_index") != index
                or witness.get("purpose") != purpose
                or witness.get("temporal_witness_id") != witness_id
                or _reference(witness) != local[witness_id]):
            raise ValueError("Source excerpt witnesses must match the cited primary quotations.")
        for row in quotes:
            identifier, segment_id = row["id"], row["segment_id"]
            if identifier in references and references[identifier] != row:
                raise ValueError("A canonical quotation cannot have conflicting source text.")
            owner = (row["beat_id"], row["start"], row["end"])
            if segment_id in segment_owners and segment_owners[segment_id] != owner:
                raise ValueError("A canonical segment cannot have conflicting source ownership.")
            references[identifier] = row
            segment_owners[segment_id] = owner

    ordered = sorted(references.values(), key=lambda row: (
        row["start"], row["end"], row["segment_id"], row["char_start"],
        row["char_end"], row["beat_id"], row["id"],
    ))
    previous_by_segment: dict[str, dict[str, Any]] = {}
    for row in ordered:
        previous = previous_by_segment.get(row["segment_id"])
        if previous is not None and row["char_start"] < previous["char_end"]:
            raise ValueError("Distinct canonical source quotations cannot overlap or alias.")
        previous_by_segment[row["segment_id"]] = row
    return "Source excerpts:\n" + "\n".join(f"\u201c{row['text']}\u201d" for row in ordered)
