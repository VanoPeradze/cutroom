"""Read-only review of existing Reel alternatives; this does not generate AI edits.

The digest is a freshness check, not authorization or a semantic-quality verdict.
Only the normal manual-edit transaction may apply the reviewed alternative.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from typing import Any

from .editing import ManualEditError, apply_manual_edit, apply_source_review_edit
from .review_candidates import checked_source_candidate
from .instruction_contract import assert_instruction_contract, effective_duration_bounds
from .story_budget import StoryBudgetError


def supports_reel_review(project: dict[str, Any]) -> bool:
    manual = project.get("manual") or {}
    return bool((project.get("sources") or {}).get("A")) and not (
        (project.get("sources") or {}).get("B")
        or "source_tracks" in manual or "sequence" in manual
    )


def reel_proposal(project: dict[str, Any], candidate_id: str, media_identity: Any) -> dict[str, Any]:
    """Stage the existing action on a copy, including durable manual overrides.

    Bind the entire persisted project (including transcript/settings/history) and
    caller-checked local media identity. No sidecar, project save or AI flags.
    """
    if not supports_reel_review(project):
        raise ManualEditError("Reel proposal preview currently supports a single primary source without a source-track timeline.")
    candidates = (project.get("draft") or {}).get("reel_candidates") or []
    matches = [item for item in candidates if isinstance(item, dict) and item.get("id") == candidate_id]
    if not matches and isinstance(candidate_id,str) and candidate_id.startswith("review_"):
        try:
            candidate,request=checked_source_candidate(project,candidate_id,media_identity)
            staged=copy.deepcopy(project)
            apply_source_review_edit(staged,candidate,request)
        except (ValueError,KeyError,TypeError) as exc:
            raise ManualEditError(str(exc)) from exc
        binding={"contract":"source-review-proposal-v1","project":project,"media":media_identity,"candidate_id":candidate_id}
        encoded=json.dumps(binding,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
        return {"proposal_id":hashlib.sha256(encoded).hexdigest(),"project_id":project["id"],"revision":project["revision"],
            "candidate_id":candidate_id,"kind":"unverified_source_candidate","ranges":staged["draft"]["keep_ranges"],
            "output_duration":staged["draft"]["output_duration"],"status":"needs_user_review","semantic_approval":False,
            "notice":candidate["notice"],"request":{**request,"style":request.get("edit_style","smart"),"instruction_verification":"recognized_mechanical_controls_only"}}
    if len(matches) != 1:
        raise ManualEditError("Select one available Reel alternative.")
    if candidate_id == str((project.get("draft") or {}).get("active_reel_candidate") or "director_pick"):
        raise ManualEditError("This Reel alternative is already active.")
    cuts = matches[0].get("cuts")
    try:
        duration = float(project["sources"]["A"].get("duration") or 0)
    except (ValueError, TypeError) as error:
        raise ManualEditError("Source duration is unavailable.") from error
    if not math.isfinite(duration) or duration <= 0 or not isinstance(cuts, list) or len(cuts) > 4096:
        raise ManualEditError("The Reel alternative has invalid source ranges.")
    for item in cuts:
        if not isinstance(item, dict):
            raise ManualEditError("The Reel alternative has invalid source ranges.")
        try:
            start, end = item["start"], item["end"]
            valid = (not isinstance(start, bool) and not isinstance(end, bool)
                     and isinstance(start, (int, float)) and isinstance(end, (int, float))
                     and math.isfinite(start) and math.isfinite(end) and 0 <= start < end <= duration)
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ManualEditError("The Reel alternative has invalid source ranges.")
    staged = copy.deepcopy(project)
    apply_manual_edit(staged, {"action": "apply_reel_candidate", "candidate_id": candidate_id})
    ranges = copy.deepcopy(staged["draft"]["keep_ranges"])
    settings = project.get("settings") or {}
    try:
        contract = assert_instruction_contract(settings)
        bounds = effective_duration_bounds(settings, duration)
    except StoryBudgetError as error:
        raise ManualEditError(str(error)) from error
    if contract["selection_controls"]["source_continuity"] == "required" and len(ranges) != 1:
        raise ManualEditError("This alternative contains source cuts that conflict with the explicit no-cuts instruction.")
    if bounds["explicit"]:
        output = staged["draft"]["output_duration"]
        if not bounds["minimum_seconds"] - .05 <= output <= bounds["maximum_seconds"] + .05:
            raise ManualEditError("This alternative conflicts with the explicitly requested duration.")
    binding = {"contract": "reel-review-v1", "instruction_contract": contract["version"],
               "project": project, "media": media_identity, "candidate_id": candidate_id}
    try:
        encoded = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ManualEditError("The project contains invalid review data.") from error
    return {
        "proposal_id": hashlib.sha256(encoded).hexdigest(),
        "project_id": project["id"], "revision": project["revision"],
        "candidate_id": candidate_id, "ranges": ranges,
        "output_duration": staged["draft"]["output_duration"],
        "status": "needs_user_review", "semantic_approval": False,
        "request": {"instruction": settings.get("instruction") or "", "style": settings.get("edit_style") or "smart",
                    "duration_mode": settings.get("duration_mode"), "target_duration": settings.get("target_duration"),
                    "instruction_verification": "recognized_mechanical_controls_only"},
    }
