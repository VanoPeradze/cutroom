"""Review a saved Director draft without replacing the current manual timeline.

The provenance marker and review digest identify saved data, not approval of AI
meaning or authorization. Only the normal guarded reset transaction applies it.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid
from typing import Any


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _draft_signature(project: dict[str, Any]) -> str:
    # Manual edits update these two bookkeeping fields without replacing the
    # saved Director proposal. All actual proposal content stays fingerprinted.
    draft = project.get("draft") or {}
    content = {key: value for key, value in draft.items() if key not in {"edited_at", "status"}}
    # Existing Undo normalizes these optional fields. Missing and its exact
    # historical default are equivalent, but real content changes are not.
    for key in ("cuts", "keep_ranges", "camera_plan", "edit_points"):
        content[key] = content.get(key) or []
    for key in ("output_duration", "removed_duration", "active_reel_candidate"):
        content.setdefault(key, None)
    for key in ("ai_camera_plan", "reel_candidates"):
        if content.get(key) is None:
            content.pop(key, None)
    return _digest(content)


def _saved_request(project: dict[str, Any]) -> dict[str, Any]:
    settings = project.get("settings") or {}
    return {"instruction": str(settings.get("instruction") or ""),
            "style": str(settings.get("edit_style") or "smart"),
            "duration_mode": settings.get("duration_mode"), "target_duration": settings.get("target_duration")}


def record_ai_draft_proposal(project: dict[str, Any]) -> None:
    """Called only by the actual Director commit, never by a read/preview route."""
    if not isinstance((project.get("manual") or {}).get("sequence"), dict):
        project.pop("_ai_draft_proposal", None)
        return
    project["_ai_draft_proposal"] = {
        "version": 1, "id": uuid.uuid4().hex,
        "draft_signature": _draft_signature(project),
        "source_signature": _digest(project.get("sources") or {}),
        "request": _saved_request(project),
    }


def record_isolated_ai_draft(project: dict[str, Any], candidate: dict[str, Any]) -> None:
    """Store a proposal, never replace render inputs of an active sequence."""
    content = {key: copy.deepcopy(candidate.get(key)) for key in ("draft", "analysis")}
    request = {**_saved_request(candidate), "settings": copy.deepcopy(candidate.get("settings") or {}),
               "source_mixer": copy.deepcopy((candidate.get("manual") or {}).get("source_mixer") or {})}
    project["_ai_draft_proposal"] = {
        "version": 2, "id": uuid.uuid4().hex,
        "source_signature": _digest(project.get("sources") or {}),
        "candidate": content, "candidate_signature": _digest({"candidate": content, "request": request}),
        "request": request,
    }


def isolated_candidate(project: dict[str, Any]) -> dict[str, Any] | None:
    marker = project.get("_ai_draft_proposal") or {}
    if not isinstance(marker, dict):
        raise ValueError("The saved candidate marker is invalid.")
    if marker.get("version") != 2:
        return None
    candidate = marker.get("candidate")
    if (not isinstance(candidate, dict) or not isinstance(candidate.get("draft"), dict)
            or not isinstance(candidate.get("analysis"), dict)
            or marker.get("candidate_signature") != _digest({"candidate": candidate, "request": marker.get("request")})
            or marker.get("source_signature") != _digest(project.get("sources") or {})):
        raise ValueError("The saved candidate or its source changed. Generate a fresh proposal.")
    return copy.deepcopy(candidate)


def candidate_project(project: dict[str, Any]) -> dict[str, Any]:
    staged = copy.deepcopy(project)
    candidate = isolated_candidate(project)
    if candidate is not None:
        old_analysis = project.get("analysis") or {}
        manual = project.get("manual") or {}
        if any(manual.get(key) for key in ("caption_corrections", "caption_overrides", "caption_dormant_overrides", "caption_alternative")):
            keys = ("transcript", "audio_source", "audio_timeline_offset")
            if any(old_analysis.get(key) != candidate["analysis"].get(key) for key in keys):
                raise ValueError("The proposal changes transcript timing with saved caption edits. Keep the current edit; this application cannot safely remap those captions.")
        staged.update(candidate)
        # Apply retains the user's current routing. Never reinterpret a proposed
        # transcript against a different source/clock or implicit audio fallback.
        from .render import _effective_audio_slot, _validate_caption_timeline
        if _effective_audio_slot(staged) != _effective_audio_slot(project):
            raise ValueError("The proposal requires different audio routing. Keep the current edit and review source routing first.")
        analyzed = str(candidate["analysis"].get("audio_source") or candidate["draft"].get("audio_source") or "A").upper()
        selected = _effective_audio_slot(project)
        if selected is not None and analyzed != selected:
            raise ValueError("The proposal analyzes a different audio source from the current edit. Review source routing first.")
        _validate_caption_timeline(staged)
    return staged


def ai_draft_review_status(project: dict[str, Any]) -> dict[str, Any]:
    """Public, small and deterministic; no recent-job lookup or history writes."""
    unavailable = {"version": 1, "available": False}
    manual = project.get("manual") or {}
    try:
        candidate = isolated_candidate(project)
    except (TypeError, ValueError, OverflowError):
        return {**unavailable, "reason": "The saved candidate or its source changed."}
    draft = candidate["draft"] if candidate else project.get("draft")
    if (not candidate and not isinstance(manual.get("sequence"), dict)) or not isinstance(draft, dict):
        return unavailable
    if not isinstance(draft.get("engine"), str) or (not draft["engine"] or draft["engine"].startswith("manual")):
        return unavailable
    try:
        signature = _draft_signature(project)
        marker = project.get("_ai_draft_proposal")
        if marker is not None:
            if (not isinstance(marker, dict) or marker.get("version") not in {1, 2}
                    or not isinstance(marker.get("id"), str) or not marker["id"]
                    or (marker.get("version") == 1 and marker.get("draft_signature") != signature)
                    or marker.get("source_signature") != _digest(project.get("sources") or {})):
                return {**unavailable, "reason": "The saved proposal or its source changed."}
            origin_id, pending, legacy = marker["id"], True, False
        else:
            # Older saved projects have no generation receipt. Offer the saved
            # draft honestly, never call it a newly generated/unapplied result.
            origin_id, pending, legacy = "legacy-" + signature, False, True
        if manual.get("ai_draft_applied") == origin_id:
            return unavailable
        return {"version": 1, "available": True, "origin_id": origin_id,
                "pending": pending, "legacy": legacy, "isolated": bool(candidate)}
    except (TypeError, ValueError, OverflowError):
        return {**unavailable, "reason": "The saved proposal contains invalid data."}


def mark_ai_draft_applied(project: dict[str, Any]) -> None:
    """Record only a successful reset's origin, inside its normal Undo entry."""
    if (project.get("_ai_draft_proposal") or {}).get("version") == 2:
        return
    state = ai_draft_review_status(project)
    if state.get("available"):
        project.setdefault("manual", {})["ai_draft_applied"] = state["origin_id"]


def ai_draft_proposal(project: dict[str, Any], origin_id: str, media_identity: Any) -> dict[str, Any]:
    """Read-only exact reset impact, including real layer/lock/caption guards."""
    from .editing import ManualEditError, apply_manual_edit
    from .sequence import editor_sequence_snapshot

    state = ai_draft_review_status(project)
    if not state.get("available") or state.get("origin_id") != origin_id:
        raise ManualEditError("This saved AI draft is no longer available for review. Reload the current project.")
    try:
        proposed_project = copy.deepcopy(project)
        proposed_project.update(isolated_candidate(project) or {})
    except (ValueError, RuntimeError) as error:
        raise ManualEditError(str(error)) from error
    draft = proposed_project["draft"]
    source = (project.get("sources") or {}).get("A") or {}
    duration = source.get("duration")
    ranges = draft.get("keep_ranges")
    if (isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration)
            or duration <= 0 or not isinstance(ranges, list) or not 1 <= len(ranges) <= 4096):
        raise ManualEditError("The saved draft has no valid primary-source passages to review.")
    checked_ranges = []
    previous = 0.0
    for row in ranges:
        if not isinstance(row, dict):
            raise ManualEditError("The saved draft has invalid source passages.")
        start, end = row.get("start"), row.get("end")
        if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in (start, end))
                or not 0 <= start < end <= duration or start < previous):
            raise ManualEditError("The saved draft has invalid or overlapping source passages.")
        checked_ranges.append({"start": start, "end": end})
        previous = end
    output = sum(row["end"] - row["start"] for row in checked_ranges)
    declared = draft.get("output_duration")
    if (isinstance(declared, bool) or not isinstance(declared, (int, float)) or not math.isfinite(declared)
            or abs(declared - output) > .05):
        raise ManualEditError("The saved draft duration does not match its source passages. Rebuild before applying it.")
    snapshot = editor_sequence_snapshot(project)
    if not snapshot or snapshot.get("error"):
        raise ManualEditError("The current timeline is unavailable. Restore it before reviewing another draft.")
    counts = lambda view: {slot: len(view["source_tracks"].get(slot) or []) for slot in ("A", "B")}
    manual = project.get("manual") or {}
    current = {"duration": snapshot["duration"], "source_clip_counts": counts(snapshot),
               "media_count": len(manual.get("media_clips") or []), "text_count": len(manual.get("text_clips") or [])}
    staged = copy.deepcopy(project)
    issue, impact = "", None
    try:
        apply_manual_edit(staged, {"action": "sequence_reset"}, apply_isolated_proposal=True)
        proposed_view = editor_sequence_snapshot(staged)
        if not proposed_view or isinstance(staged.get("manual", {}).get("sequence"), dict):
            raise ManualEditError("The saved draft did not produce a replacement timeline.")
        impact = {"duration": proposed_view["duration"], "source_clip_counts": counts(proposed_view),
                  "media_preserved": (staged.get("manual") or {}).get("media_clips") == manual.get("media_clips"),
                  "text_preserved": (staged.get("manual") or {}).get("text_clips") == manual.get("text_clips")}
        if not impact["media_preserved"] or not impact["text_preserved"]:
            raise ManualEditError("The reset would change existing layers. Keep the current edit; this review does not support retiming or removing them.")
    except (ValueError, KeyError, TypeError) as error:
        issue = str(error)
    warnings = [
        "Source inspection plays primary A passages only, not the proposed composite, source B, effects, captions or edited sound mix.",
        "Apply resets source-track timing and layout to the saved draft. Imported media/text retain their existing edit times; they are not removed or retimed.",
        "Current project settings, mixer, crop and name remain in use. Apply adopts the reviewed draft and analysis; it does not adopt proposed settings.",
        "Automatic captions follow the resulting timeline. Source content and transcription still need your review; playback is not AI quality approval.",
    ]
    for warning in (draft.get("quality_review") or {}).get("warnings") or []:
        if isinstance(warning, dict) and isinstance(warning.get("message"), str):
            warnings.append(warning["message"][:2000])
        if len(warnings) >= 20:
            break
    request = copy.deepcopy((project.get("_ai_draft_proposal") or {}).get("request"))
    if not isinstance(request, dict):
        request = {"instruction": "The original generation request was not recorded for this older saved draft.",
                   "style": str(draft.get("edit_style") or "Not recorded"), "duration_mode": None, "target_duration": None}
    binding = {"contract": "saved-ai-draft-review-v1", "project": project, "media": media_identity, "origin_id": origin_id}
    try:
        proposal_id = _digest(binding)
    except (TypeError, ValueError, OverflowError) as error:
        raise ManualEditError("The project contains invalid review data.") from error
    return {
        "proposal_id": proposal_id, "origin_id": origin_id, "project_id": project["id"], "revision": project["revision"],
        "status": "needs_user_review", "semantic_approval": False,
        "apply_allowed": not bool(issue), "apply_issue": issue, "current": current, "impact": impact,
        "proposed": {"title": str(draft.get("title") or "Saved AI draft"), "summary": str(draft.get("summary") or ""),
                     "engine": draft.get("engine"), "output_duration": declared, "ranges": checked_ranges,
                     "source_slot": "A", "source_duration": duration},
        "warnings": warnings,
        "request": request,
    }
