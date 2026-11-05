"""Temporary selectable source units; canonical ASR and timing stay unchanged.

Punctuation at an existing ASR boundary proposes a smaller selection, never
semantic approval. Internal punctuation cannot authorize splitting an ASR row.
"""
from __future__ import annotations

import copy
import math
import re

from .cache_keys import stable_fingerprint
from .story_budget import StoryPlanningError


CANDIDATE_POLICY_VERSION = "whole-asr-source-units-2026-10-21-v1"
ENTRY_POLICY_VERSION = "complete-asr-entry-2026-10-21-v1"
MAX_SOURCE_SEGMENTS = 20000
_END = re.compile(r'''[.!?\u061f\u3002\uff01\uff1f]["'\u201d\u2019\u00bb)\]]*$''')


def _complete_boundary(text):
    tail = text.rstrip().rstrip('"\'\u201d\u2019\u00bb)]')
    return bool(_END.search(text.strip())) and not tail.endswith(("...", "\u2026"))


def source_identity_rows(segments):
    """Exact words and clocks also participate in editorial cache identity."""
    return [{**{key: copy.deepcopy(row.get(key)) for key in ("id", "start", "end", "text", "words")},
             **({"word_timing_complete": copy.deepcopy(row["word_timing_complete"])}
                if "word_timing_complete" in row else {})} for row in segments]


def project_short_source_units(parents, segments):
    """Split within each parent, covering every canonical row once or fail closed.

    Parent analysis ownership is provenance, not mandatory playback. Context
    neighbors are reference-only; selection still needs exact source evidence,
    explicit constraints, and independent semantic review.
    """
    def invalid():
        raise StoryPlanningError("Story source units need an unambiguous complete canonical source; no rows were truncated or repaired.",
            {"reason": "invalid_story_candidate_projection", "outcome": "technical_error", "applied_to_timeline": False})

    if not segments or len(segments) > MAX_SOURCE_SEGMENTS:
        invalid()
    by_id = {}
    previous_end = -1.0
    for row in segments:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or row["id"] in by_id:
            invalid()
        start, end = row.get("start"), row.get("end")
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, end))
                or start < 0 or end <= start or start < previous_end - .001
                or not isinstance(row.get("text"), str) or not row["text"].strip()):
            invalid()
        by_id[row["id"]] = row
        previous_end = end
    canonical_ids = list(by_id)
    parent_ids = [str(row.get("id") or "") for row in parents]
    owned = [identifier for row in parents for identifier in row.get("segment_ids", [])]
    if (not all(parent_ids) or len(set(parent_ids)) != len(parent_ids) or owned != canonical_ids):
        invalid()
    binding = stable_fingerprint(CANDIDATE_POLICY_VERSION, source_identity_rows(segments))
    positions = {identifier: index for index, identifier in enumerate(canonical_ids)}
    output = []
    for parent in parents:
        pending = []

        def emit(complete):
            first, last = pending[0], pending[-1]
            start, end = first["start"], last["end"]
            if start < float(parent["start"]) - .001 or end > float(parent["end"]) + .001:
                invalid()
            ids = [row["id"] for row in pending]
            left, right = positions[ids[0]], positions[ids[-1]]
            unit = {key: copy.deepcopy(parent[key]) for key in
                    ("position", "editorial_score", "novelty") if key in parent}
            unit.update({
                "id": "u_" + stable_fingerprint(CANDIDATE_POLICY_VERSION, {"source": binding,
                    "parent": parent["id"], "segments": ids})[:24],
                "start": start, "end": end, "duration": end - start,
                "position": round(start / max(float(segments[-1]["end"]), 1.0), 4),
                "text": " ".join(row["text"] for row in pending), "segment_ids": ids,
                "parent_analysis_beat_id": parent["id"], "candidate_policy": CANDIDATE_POLICY_VERSION,
                "candidate_source_fingerprint": binding,
                "boundary_status": "punctuation_at_asr_boundary" if complete else "unfinished_parent_tail",
                "semantic_coherence_verified": False,
                "context_neighbor_segment_ids": ([canonical_ids[left - 1]] if left else [])
                    + ([canonical_ids[right + 1]] if right + 1 < len(canonical_ids) else []),
            })
            # Parent role/vision notes concern its whole interval. They must not
            # become claimed observations or semantic roles for a smaller unit.
            output.append(unit)
            pending.clear()

        for identifier in parent["segment_ids"]:
            row = by_id[identifier]
            pending.append(row)
            if _complete_boundary(row["text"]):
                emit(True)
        if pending:
            emit(False)
    return output


def candidate_projection_fields(unit):
    if unit.get("candidate_policy") != CANDIDATE_POLICY_VERSION:
        return {}
    return {key: copy.deepcopy(unit[key]) for key in ("segment_ids", "parent_analysis_beat_id",
        "candidate_policy", "boundary_status", "semantic_coherence_verified", "context_neighbor_segment_ids")}


def expose_complete_asr_entries(units, segments):
    """Expose a whole final ASR sentence after an earlier internal sentence.

    A storage group may contain the tail of one utterance followed by a complete
    new ASR row. Do not force that final row to retain the earlier tail. Prefixes
    remain in the canonical partition, marked unfinished; only semantic review
    can establish that a proposed entry is understandable. Never split a row.
    """
    by_id = {r["id"]: r for r in segments}
    boundary = re.compile(r"(?<!\.)[.!?\u061f](?!\.)[\"'\u201d\u2019)]*\s+")
    result = []
    for unit in units:
        rows = [by_id[v] for v in unit["segment_ids"]]
        split = (len(rows) > 1 and len(rows[-1]["text"].split()) >= 4 and _complete_boundary(rows[-1]["text"])
                 and boundary.search(" ".join(r["text"] for r in rows[:-1]) + " "))
        parts = [rows[:-1], rows[-1:]] if split else [rows]
        for part in parts:
            value = copy.deepcopy(unit)
            if split:
                ids = [r["id"] for r in part]
                value.update(id="u_" + stable_fingerprint(ENTRY_POLICY_VERSION,
                    {"source": unit["candidate_source_fingerprint"], "owner": unit["id"], "segments": ids})[:24],
                    start=part[0]["start"], end=part[-1]["end"],
                    duration=part[-1]["end"]-part[0]["start"], segment_ids=ids,
                    text=" ".join(r["text"] for r in part),
                    boundary_status="punctuation_at_asr_boundary" if _complete_boundary(part[-1]["text"]) else "unfinished_parent_tail")
            value["entry_policy"] = ENTRY_POLICY_VERSION
            if split: value["entry_owner_id"] = unit["id"]
            result.append(value)
    assert [v for u in result for v in u["segment_ids"]] == [r["id"] for r in segments]
    return result


def neighboring_source_utterances(candidates, segments):
    selected = {identifier for unit in candidates for identifier in unit.get("segment_ids", [])}
    neighbors = {identifier for unit in candidates for identifier in unit.get("context_neighbor_segment_ids", [])} - selected
    return [{"id": row["id"], "start": row["start"], "end": row["end"], "text": row["text"],
             "authority": "reference_context_only_not_selected_or_semantically_verified"}
            for row in segments if row["id"] in neighbors]
