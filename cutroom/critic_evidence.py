"""Bind critic actions to original evidence without certifying interpretation."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .story_evidence import build_story_evidence_catalog
from .cache_keys import stable_fingerprint
from .structured_schema import complete_object_union


CRITIC_ACTION_EVIDENCE_POLICY = "critic-source-action-attribution-2026-10-21-v1"
_DEFECTS = {"off_topic", "missing_context", "meaning_change", "incomplete_thought",
            "chronology_conflict", "explicit_instruction"}
_ROW_KEYS = {"action", "beat_id", "defect_kind", "source_evidence_ids", "instruction_quote", "explanation"}


def review_joins(ranges, segments):
    """Application-owned joins; lack of ASR in a gap is not known silence."""
    result = []
    for left, right in zip(ranges, ranges[1:]):
        if right["start"] <= left["end"]:
            continue
        before = [r for r in segments if r["start"] < left["end"] and r["end"] > left["start"]]
        after = [r for r in segments if r["start"] < right["end"] and r["end"] > right["start"]]
        if not before or not after:
            continue
        a, b = before[-1], after[0]
        omitted = [r for r in segments if r["start"] >= left["end"] and r["end"] <= right["start"]]
        facts = {"left_segment_id": a["id"], "right_segment_id": b["id"],
                 "left_quote": a["text"], "right_quote": b["text"],
                 "omitted_source": [{k:r[k] for k in ("id", "start", "end", "text")} for r in omitted],
                 "source_gap": {"start": left["end"], "end": right["start"]}, "gap_audio_verified": False}
        result.append({"id": "join_" + stable_fingerprint("review-source-join-v1", facts)[:20], **facts})
    return result


def review_evidence_schema(segments, joins, *, indexed=False, selected_segment_ids=None, instruction="", implicit_indices=False):
    selected = set(selected_segment_ids) if selected_segment_ids is not None else {r["id"] for r in segments}
    selected_ids = [r["id"] for r in segments if r["id"] in selected]
    omitted_ids = [r["id"] for r in segments if r["id"] not in selected]
    fields = {"kind": {"enum":["join_context", "missing_context", "meaning_change", "incomplete_thought", "source_text_uncertainty", "explicit_instruction"]},
        "source_segment_ids": {"type":"array", "minItems":1,"maxItems":4,"uniqueItems":True,"items":{"enum":selected_ids}},
        "missing_context_segment_ids":({"type":"array","maxItems":4,"uniqueItems":True,"items":{"enum":omitted_ids}} if omitted_ids else {"type":"array","maxItems":0}),
        "join_id":{"enum":[None,*[r["id"] for r in joins]]}, "instruction_quote":{"type":"string","maxLength":512}}
    if indexed and not implicit_indices: fields["issue_index"]={"type":"integer","minimum":0,"maximum":1}
    if not omitted_ids: fields["kind"]["enum"].remove("missing_context")
    if not joins: fields["kind"]["enum"].remove("join_context")
    if not instruction: fields["kind"]["enum"].remove("explicit_instruction")
    # Discriminated rules match the validator. A verbatim instruction belongs
    # only to an instruction defect; it is never a source quote or paraphrase.
    fields["instruction_quote"]={"type":"string"}
    variants=[]
    for kind in fields["kind"]["enum"]:
        props={"kind":{"const":kind},
            "instruction_quote":{"const":instruction if kind=="explicit_instruction" else ""},
            "join_id":{"const":None},
            "missing_context_segment_ids":{"maxItems":0}}
        if kind=="missing_context":props["missing_context_segment_ids"]={"minItems":1}
        if kind=="join_context":
            for join in joins:
                variants.append({"properties":{**props,"join_id":{"const":join["id"]},
                    "source_segment_ids":{"const":[join["left_segment_id"],join["right_segment_id"]]}}})
        else:variants.append({"properties":props})
    return {"type":"array","maxItems":2 if indexed else 1,"items":complete_object_union({"type":"object","additionalProperties":False,"properties":fields,"required":list(fields),"anyOf":variants})}


def validate_review_evidence(records, segments, selected_segment_ids, joins, instruction, *, issue_count=1, indexed=False):
    """Validate mechanically checkable rejection facts, never semantic entailment."""
    if (type(issue_count) is not int or not 0<=issue_count<=(2 if indexed else 1)
            or not isinstance(records,list) or len(records)!=issue_count):
        raise ValueError("Every blocking issue needs one exact source record.")
    by_id={r["id"]:r for r in segments}; selected=set(selected_segment_ids); by_join={r["id"]:r for r in joins}
    keys={"kind","source_segment_ids","missing_context_segment_ids","join_id","instruction_quote"}|({"issue_index"} if indexed else set())
    seen=set(); output=[]
    for pos,row in enumerate(records):
        if not isinstance(row,dict) or set(row)!=keys: raise ValueError("Review evidence has invalid fields.")
        index=row.get("issue_index",pos)
        if type(index) is not int or not 0<=index<issue_count or index in seen: raise ValueError("Review issue indices are invalid.")
        seen.add(index); refs=_ids(row["source_segment_ids"],"Review quotes",nonempty=True); missing=_ids(row["missing_context_segment_ids"],"Missing context")
        if len(refs)>4 or len(missing)>4: raise ValueError("Review source record exceeds its schema bound.")
        if not set(refs)<=selected or not set(missing)<=set(by_id)-selected: raise ValueError("Review selected/omitted source attribution is false.")
        kind=row["kind"]
        if kind not in {"join_context","missing_context","meaning_change","incomplete_thought","source_text_uncertainty","explicit_instruction"}: raise ValueError("Unknown review defect.")
        if kind=="join_context":
            join=by_join.get(row["join_id"])
            if join is None or refs!=[join["left_segment_id"],join["right_segment_id"]]: raise ValueError("Review join does not connect the cited source segments.")
        elif row["join_id"] is not None: raise ValueError("Only a join issue may claim a playback join.")
        if kind=="missing_context" and not missing: raise ValueError("Missing context must identify an actually omitted prerequisite.")
        if kind!="missing_context" and missing: raise ValueError("Unexpected missing-context evidence.")
        quote=row["instruction_quote"]
        if not isinstance(quote,str) or quote!=(instruction if kind=="explicit_instruction" else "") or (kind=="explicit_instruction" and not instruction): raise ValueError("Review instruction evidence is invalid.")
        output.append({**copy.deepcopy(row),"source_quotes":[{k:by_id[v][k] for k in ("id","start","end","text")} for v in refs+missing],"attribution_verified":True,"semantic_entailment_verified":False})
    return output


def _ids(value: Any, label: str, *, nonempty: bool = False) -> list[str]:
    if (not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(value) != len(set(value)) or (nonempty and not value)):
        raise ValueError(f"{label} must contain unique exact source IDs.")
    return value


def validate_critic_actions(
    result: Any, catalog: Any, candidates: Any, segments: Any, brief: Any, selected: Any,
) -> list[dict[str, Any]]:
    """Resolve actions and verbatim instruction references, never their entailment.

    A clean legacy response with no actions needs no action evidence. Every
    action otherwise requires one complete attributed record. An exact citation
    or instruction substring does not establish the model's semantic claim.
    """
    if not isinstance(result, dict):
        raise ValueError("Critic action review must be an object.")
    additions = _ids(result.get("add_beat_ids"), "Critic additions")
    removals = _ids(result.get("remove_beat_ids"), "Critic removals")
    if set(additions) & set(removals):
        raise ValueError("A critic cannot add and remove the same source beat.")
    expected = {("add", identifier) for identifier in additions} | {("remove", identifier) for identifier in removals}
    records = result.get("action_evidence", [])
    if not isinstance(records, list):
        raise ValueError("Critic action_evidence must be a list.")
    if not expected:
        if records:
            raise ValueError("Critic evidence names an action that was not requested.")
        return []
    if not records:
        raise ValueError("Every critic action requires attributed source evidence.")
    try:
        authoritative = build_story_evidence_catalog(candidates, segments)
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Critic source ownership could not be established.") from exc
    if not authoritative or catalog != authoritative:
        raise ValueError("Critic source catalog is missing, forged or stale.")
    by_id = {row["id"]: row for row in authoritative}
    by_beat = {row["id"]: row for row in candidates}
    by_segment = {row["id"]: row for row in segments}
    selected_ids = set(_ids(selected, "Selected critic source"))
    if not selected_ids <= set(by_beat):
        raise ValueError("Selected critic source contains an unknown beat.")
    if any(identifier not in by_beat for _action, identifier in expected):
        raise ValueError("Critic action names an unknown source beat.")
    try:
        identity = json.dumps({"segments": segments, "catalog": authoritative, "beats": candidates},
                              ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Critic source identity is not finite JSON.") from exc
    fingerprint = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    seen, grounded = set(), []
    for row in records:
        if not isinstance(row, dict) or set(row) != _ROW_KEYS:
            raise ValueError("Critic action evidence needs exactly the contracted fields.")
        action, target, kind = row["action"], row["beat_id"], row["defect_kind"]
        if not isinstance(action, str) or not isinstance(target, str) or (action, target) not in expected:
            raise ValueError("Critic evidence does not match a requested action.")
        if (action, target) in seen:
            raise ValueError("A critic action has duplicate evidence records.")
        if not isinstance(kind, str) or kind not in _DEFECTS:
            raise ValueError("Critic action defect must be a source or explicit-instruction issue, not style alone.")
        references = _ids(row["source_evidence_ids"], "Critic source evidence", nonempty=True)
        if any(identifier not in by_id for identifier in references):
            raise ValueError("Critic evidence contains an unknown or translated source reference.")
        quotes = [by_id[identifier] for identifier in references]
        if not any(quote["beat_id"] == target for quote in quotes):
            raise ValueError("Critic evidence must cite its target source beat.")
        if kind in {"off_topic", "chronology_conflict"} and not any(
                quote["beat_id"] in selected_ids and quote["beat_id"] != target for quote in quotes):
            raise ValueError("A relational critic defect needs evidence from another selected source beat.")
        instruction_quote, explanation = row["instruction_quote"], row["explanation"]
        if not isinstance(instruction_quote, str) or not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("Critic instruction quote and explanation must be explicit strings.")
        instruction_evidence = None
        if kind == "explicit_instruction":
            instruction = brief.get("instruction") if isinstance(brief, dict) else None
            if (not instruction_quote.strip() or not isinstance(instruction, str)
                    or instruction_quote not in instruction):
                raise ValueError("Critic instruction evidence must quote the verbatim original instruction.")
            start = instruction.index(instruction_quote)
            instruction_evidence = {"quote": instruction_quote, "char_start": start,
                                    "char_end": start + len(instruction_quote), "scope": "verbatim_substring_only"}
        elif instruction_quote != "":
            raise ValueError("Only explicit-instruction issues may contain an instruction quotation.")
        source_ids = list(dict.fromkeys(quote["segment_id"] for quote in quotes))
        grounded.append({**copy.deepcopy(row),
                         "source_evidence": copy.deepcopy(quotes),
                         "source_utterances": [copy.deepcopy(by_segment[identifier]) for identifier in source_ids],
                         "instruction_evidence": instruction_evidence,
                         "policy_version": CRITIC_ACTION_EVIDENCE_POLICY,
                         "source_fingerprint": fingerprint,
                         "verification_scope": "source_and_instruction_reference_attribution",
                         "interpretation_verified": False})
        seen.add((action, target))
    if seen != expected:
        raise ValueError("Every requested critic action needs exactly one attributed record.")
    return grounded
