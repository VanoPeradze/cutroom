"""Canonicalize a neutral proposal's temporal witness, never its interpretation.

The model must already have selected every exact quotation. This helper can only
move one selected quotation into the temporal-anchor field. Strict source,
duration and semantic review remain the caller's responsibility.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from .story_evidence import build_story_evidence_catalog


NEUTRAL_WITNESS_POLICY = "neutral-selected-witness-2026-10-21-v1"
_PURPOSE = "self_contained_passage"
_EPSILON = .001


def adapt_neutral_temporal_witness(
    result: Any, catalog: Any, candidates: Any, segments: Any,
    chapters: Any, plan: Any, brief: Any, *, eligible: bool,
) -> tuple[Any, dict[str, Any] | None]:
    """Return a detached proposal and provenance only when its anchor changes.

    ``eligible`` is supplied by the caller after checking explicit user roles,
    ordering and single-idea intent. Local guards additionally require a Short,
    one exact neutral purpose and no required context. Invalid proposals/source
    are left unchanged for the existing strict decoder; no refusal is adapted.
    """
    proposal = copy.deepcopy(result)
    if eligible is not True or not isinstance(brief, dict) or brief.get("goal") != "short":
        return proposal, None
    if (not isinstance(plan, dict) or not isinstance(plan.get("slots"), list)
            or len(plan["slots"]) != 1 or not isinstance(plan["slots"][0], dict)):
        return proposal, None
    slot = plan["slots"][0]
    if slot.get("purpose") != _PURPOSE or slot.get("required_context_chapter_ids") != []:
        return proposal, None
    if (not isinstance(result, dict)
            or set(result) != {"verdict", "role_selections", "highlight_beat_ids", "title", "summary"}
            or result.get("verdict") != "fit"
            or not isinstance(result.get("title"), str) or not isinstance(result.get("summary"), str)):
        return proposal, None
    roles = result.get("role_selections")
    if not isinstance(roles, dict) or set(roles) != {_PURPOSE}:
        return proposal, None
    role = roles[_PURPOSE]
    if (not isinstance(role, dict)
            or set(role) != {"primary_anchor_choice", "additional_primary_evidence_choices", "context_evidence_choices_by_chapter"}
            or role["context_evidence_choices_by_chapter"] != {}):
        return proposal, None
    anchor, additional = role["primary_anchor_choice"], role["additional_primary_evidence_choices"]
    if not isinstance(anchor, str) or not isinstance(additional, list):
        return proposal, None
    choices = [anchor, *additional]
    if any(not isinstance(choice, str) for choice in choices) or len(choices) != len(set(choices)):
        return proposal, None
    try:
        # Rebuild through the existing authoritative quotation/ownership rules.
        # A stale or forged supplied catalog must never authorize an adaptation.
        if catalog != build_story_evidence_catalog(candidates, segments):
            return proposal, None
        by_choice = {f"{row['text']} [{row['id']}]": row for row in catalog}
        if len(by_choice) != len(catalog) or any(choice not in by_choice for choice in choices):
            return proposal, None
        by_beat = {row["id"]: row for row in candidates}
        chapter_ids, owners = set(), {}
        for chapter in chapters:
            identifier = chapter["id"]
            if not isinstance(identifier, str) or identifier in chapter_ids:
                return proposal, None
            chapter_ids.add(identifier)
            for beat in chapter["beats"]:
                if beat["id"] in owners:
                    return proposal, None
                owners[beat["id"]] = identifier
        primary = slot["chapter_ids"]
        if (not isinstance(primary, list) or not primary
                or any(not isinstance(value, str) or value not in chapter_ids for value in primary)
                or len(primary) != len(set(primary))):
            return proposal, None
        selected_beats = {by_choice[choice]["beat_id"] for choice in choices}
        if any(owners.get(identifier) not in primary for identifier in selected_beats):
            return proposal, None
        highlights = result["highlight_beat_ids"]
        if (not isinstance(highlights, list) or any(not isinstance(value, str) for value in highlights)
                or len(highlights) != len(set(highlights)) or not set(highlights) <= selected_beats):
            return proposal, None
        final_end = max(float(by_beat[identifier]["end"]) for identifier in selected_beats)
        final_beats = {identifier for identifier in selected_beats
                       if abs(float(by_beat[identifier]["end"]) - final_end) <= _EPSILON}
        if by_choice[anchor]["beat_id"] in final_beats:
            return proposal, None
        new_anchor = max(
            (choice for choice in choices if by_choice[choice]["beat_id"] in final_beats),
            key=lambda choice: (float(by_choice[choice]["end"]), by_choice[choice]["char_end"], by_choice[choice]["id"]),
        )
        identity = json.dumps({"segments": segments, "catalog": catalog, "beats": candidates, "chapters": chapters},
                              ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (KeyError, TypeError, ValueError, OverflowError):
        return proposal, None
    adapted = proposal["role_selections"][_PURPOSE]
    adapted["primary_anchor_choice"] = new_anchor
    adapted["additional_primary_evidence_choices"] = [choice for choice in choices if choice != new_anchor]
    return proposal, {
        "policy_version": NEUTRAL_WITNESS_POLICY,
        "raw_anchor": anchor, "new_anchor": new_anchor,
        "source_fingerprint": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
        "selected_choice_count": len(choices), "source_choices_preserved": True,
        "interpretation_verified": False,
    }
