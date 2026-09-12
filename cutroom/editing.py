from __future__ import annotations

import copy
from typing import Any

from .composition import build_manual_embedded_candidate
from .source_tracks import TRACK_ACTIONS, SourceTrackError, prepare_source_track_edit, validate_source_track_sync
from .sequence import SEQUENCE_ACTIONS, prepare_sequence_edit
from .utils import clamp, invert_ranges, merge_ranges, now_iso, range_duration


class ManualEditError(ValueError):
    """Raised when a manual edit request cannot be applied safely."""


HISTORY_LIMIT = 20
MIN_RANGE_SECONDS = 0.08
# Millisecond endpoints such as 0.10 -> 0.18 can subtract to just below 0.08.
# Only compensate for floating-point noise; retain the existing merge policy.
RANGE_EPSILON = 1e-9
CAMERA_OVERRIDE_LAYOUTS = frozenset({"screen", "camera", "stacked", "side_by_side", "pip"})
TWO_SOURCE_LAYOUTS = frozenset({"camera", "stacked", "side_by_side", "pip"})
SOURCE_MIXER_DEFAULT_LAYOUTS = frozenset({"auto", *CAMERA_OVERRIDE_LAYOUTS})


def _duration(project: dict[str, Any]) -> float:
    try:
        return max(0.0, float(project.get("sources", {}).get("A", {}).get("duration", 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _number(payload: dict[str, Any], key: str) -> float:
    try:
        value = float(payload[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ManualEditError(f"{key} must be a number") from exc
    if value != value or value in {float("inf"), float("-inf")}:
        raise ManualEditError(f"{key} must be finite")
    return value


def _requested_range(project: dict[str, Any], payload: dict[str, Any]) -> tuple[float, float]:
    duration = _duration(project)
    start = clamp(_number(payload, "start"), 0.0, duration)
    end = clamp(_number(payload, "end"), 0.0, duration)
    if end < start:
        start, end = end, start
    if end - start < MIN_RANGE_SECONDS - RANGE_EPSILON:
        raise ManualEditError("Select at least 0.08 seconds")
    return round(start, 3), round(end, 3)


def _subtract_range(ranges: list[dict[str, Any]], start: float, end: float) -> list[dict[str, float]]:
    remaining: list[dict[str, float]] = []
    for item in merge_ranges(ranges):
        item_start = float(item["start"])
        item_end = float(item["end"])
        if item_end <= start or item_start >= end:
            remaining.append(item)
            continue
        if item_start < start and start - item_start >= MIN_RANGE_SECONDS - RANGE_EPSILON:
            remaining.append({"start": item_start, "end": start})
        if item_end > end and item_end - end >= MIN_RANGE_SECONDS - RANGE_EPSILON:
            remaining.append({"start": end, "end": item_end})
    return merge_ranges(remaining)


def apply_timeline_overrides(
    automatic_cuts: list[dict[str, Any]], manual: dict[str, Any] | None,
) -> list[dict[str, float]]:
    """Keep explicit restores through rebuilds, then apply explicit deletions."""
    manual = manual if isinstance(manual, dict) else {}
    cuts = merge_ranges(automatic_cuts)
    for keep in merge_ranges(manual.get("keeps") or []):
        cuts = _subtract_range(cuts, float(keep["start"]), float(keep["end"]))
    return merge_ranges([*cuts, *(manual.get("cuts") or [])])


def _camera_plan_for_keep_ranges(
    previous: list[dict[str, Any]],
    keep_ranges: list[dict[str, float]],
) -> list[dict[str, Any]]:
    """Clip the existing camera plan to kept source time, filling restored gaps with A."""
    plan: list[dict[str, Any]] = []
    ordered = sorted(
        (
            item
            for item in previous
            if isinstance(item, dict) and float(item.get("end", 0)) > float(item.get("start", 0))
        ),
        key=lambda item: float(item.get("start", 0)),
    )
    fallback_camera = str(ordered[0].get("camera") or "A") if ordered else "A"
    for keep in keep_ranges:
        keep_start = float(keep["start"])
        keep_end = float(keep["end"])
        cursor = keep_start
        for item in ordered:
            overlap_start = max(keep_start, float(item.get("start", 0)))
            overlap_end = min(keep_end, float(item.get("end", 0)))
            if overlap_end - overlap_start < MIN_RANGE_SECONDS - RANGE_EPSILON:
                continue
            if overlap_start - cursor >= MIN_RANGE_SECONDS - RANGE_EPSILON:
                plan.append({"start": round(cursor, 3), "end": round(overlap_start, 3), "camera": fallback_camera})
            plan.append({
                "start": round(overlap_start, 3),
                "end": round(overlap_end, 3),
                "camera": str(item.get("camera") or "A"),
            })
            cursor = max(cursor, overlap_end)
        if keep_end - cursor >= MIN_RANGE_SECONDS - RANGE_EPSILON:
            plan.append({"start": round(cursor, 3), "end": round(keep_end, 3), "camera": fallback_camera})

    compact: list[dict[str, Any]] = []
    for item in plan:
        if (
            compact
            and compact[-1]["camera"] == item["camera"]
            and abs(float(compact[-1]["end"]) - float(item["start"])) < 0.081
        ):
            compact[-1]["end"] = item["end"]
        else:
            compact.append(item)
    return compact


def _compact_camera_plan(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for raw in sorted(plan, key=lambda item: (float(item.get("start", 0)), float(item.get("end", 0)))):
        try:
            start = round(float(raw["start"]), 3)
            end = round(float(raw["end"]), 3)
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start:
            continue
        item = {"start": start, "end": end, "camera": str(raw.get("camera") or "A")}
        if (
            compact
            and compact[-1]["camera"] == item["camera"]
            and abs(float(compact[-1]["end"]) - start) < 0.002
        ):
            compact[-1]["end"] = end
        else:
            compact.append(item)
    return compact


def _replace_camera_plan_range(
    plan: list[dict[str, Any]],
    start: float,
    end: float,
    camera: str,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for item in plan:
        item_start = float(item.get("start", 0))
        item_end = float(item.get("end", 0))
        if item_end <= start or item_start >= end:
            updated.append(copy.deepcopy(item))
            continue
        overlap_start = max(item_start, start)
        overlap_end = min(item_end, end)
        # A tiny fragment would later be dropped by the renderer. Snap the manual
        # boundary to the neighboring plan edge so source-time coverage is exact.
        if 0 < overlap_start - item_start < MIN_RANGE_SECONDS - RANGE_EPSILON:
            overlap_start = item_start
        if 0 < item_end - overlap_end < MIN_RANGE_SECONDS - RANGE_EPSILON:
            overlap_end = item_end
        if item_start < overlap_start:
            updated.append({"start": item_start, "end": overlap_start, "camera": str(item.get("camera") or "A")})
        if overlap_end > overlap_start:
            updated.append({"start": overlap_start, "end": overlap_end, "camera": camera})
        if item_end > overlap_end:
            updated.append({"start": overlap_end, "end": item_end, "camera": str(item.get("camera") or "A")})
    return _compact_camera_plan(updated)


def _replace_camera_override(
    previous: list[dict[str, Any]],
    start: float,
    end: float,
    layout: str,
) -> list[dict[str, Any]]:
    """Replace one manual override interval; ``auto`` reveals the AI plan again."""
    remaining: list[dict[str, Any]] = []
    for item in previous:
        try:
            item_start = float(item["start"])
            item_end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        item_layout = str(item.get("layout") or "")
        if item_layout not in CAMERA_OVERRIDE_LAYOUTS or item_end <= item_start:
            continue
        if item_end <= start or item_start >= end:
            remaining.append({"start": item_start, "end": item_end, "layout": item_layout})
            continue
        if item_start < start:
            remaining.append({"start": item_start, "end": start, "layout": item_layout})
        if item_end > end:
            remaining.append({"start": end, "end": item_end, "layout": item_layout})
    if layout != "auto":
        remaining.append({"start": start, "end": end, "layout": layout})

    compact: list[dict[str, Any]] = []
    for item in sorted(remaining, key=lambda value: (float(value["start"]), float(value["end"]))):
        normalized = {
            "start": round(float(item["start"]), 3),
            "end": round(float(item["end"]), 3),
            "layout": str(item["layout"]),
        }
        if normalized["end"] - normalized["start"] < MIN_RANGE_SECONDS - RANGE_EPSILON:
            continue
        if (
            compact
            and compact[-1]["layout"] == normalized["layout"]
            and abs(float(compact[-1]["end"]) - float(normalized["start"])) < 0.002
        ):
            compact[-1]["end"] = normalized["end"]
        else:
            compact.append(normalized)
    return compact


def apply_camera_overrides(
    ai_plan: list[dict[str, Any]],
    keep_ranges: list[dict[str, float]],
    overrides: list[dict[str, Any]],
    *,
    has_b: bool,
) -> list[dict[str, Any]]:
    """Overlay durable user layout choices on the Director's source-time plan."""
    plan = _camera_plan_for_keep_ranges(ai_plan, keep_ranges)
    for item in sorted(overrides or [], key=lambda value: float(value.get("start", 0))):
        try:
            start = float(item["start"])
            end = float(item["end"])
        except (KeyError, TypeError, ValueError):
            continue
        layout = str(item.get("layout") or "")
        if layout not in CAMERA_OVERRIDE_LAYOUTS or end - start < MIN_RANGE_SECONDS - RANGE_EPSILON:
            continue
        if layout in TWO_SOURCE_LAYOUTS and not has_b:
            continue
        plan = _replace_camera_plan_range(plan, start, end, layout)
    return plan


def _rebuild_camera_plan(project: dict[str, Any]) -> None:
    draft = project.setdefault("draft", {})
    keep_ranges = list(draft.get("keep_ranges") or [])
    base = draft.get("ai_camera_plan")
    if not isinstance(base, list):
        base = copy.deepcopy(draft.get("camera_plan") or [])
    base = _camera_plan_for_keep_ranges(base, keep_ranges)
    draft["ai_camera_plan"] = base
    overrides = project.setdefault("manual", {}).get("camera_overrides") or []
    draft["camera_plan"] = apply_camera_overrides(
        base,
        keep_ranges,
        overrides if isinstance(overrides, list) else [],
        has_b=bool(project.get("sources", {}).get("B")),
    )


def _timeline_snapshot(project: dict[str, Any]) -> dict[str, Any]:
    draft = project.get("draft") or {}
    manual = project.setdefault("manual", {})
    settings = project.get("settings") if isinstance(project.get("settings"), dict) else {}
    return {
        "cuts": copy.deepcopy(draft.get("cuts") or []),
        "keep_ranges": copy.deepcopy(draft.get("keep_ranges") or []),
        "camera_plan": copy.deepcopy(draft.get("camera_plan") or []),
        "ai_camera_plan": copy.deepcopy(draft.get("ai_camera_plan")) if isinstance(draft.get("ai_camera_plan"), list) else None,
        "edit_points": copy.deepcopy(draft.get("edit_points") or []),
        "output_duration": draft.get("output_duration"),
        "removed_duration": draft.get("removed_duration"),
        "active_reel_candidate": draft.get("active_reel_candidate"),
        "reel_candidates": copy.deepcopy(draft.get("reel_candidates")) if isinstance(draft.get("reel_candidates"), list) else None,
        "manual_cuts": copy.deepcopy(manual.get("cuts") or []),
        "manual_keeps": copy.deepcopy(manual.get("keeps") or []),
        "manual_camera_overrides": copy.deepcopy(manual.get("camera_overrides") or []),
        "manual_source_mixer": copy.deepcopy(manual.get("source_mixer")) if isinstance(manual.get("source_mixer"), dict) else None,
        "manual_source_tracks_present": "source_tracks" in manual,
        "manual_source_tracks": copy.deepcopy(manual.get("source_tracks")),
        "manual_sequence_present": "sequence" in manual,
        "manual_sequence": copy.deepcopy(manual.get("sequence")),
        # Embedded composition changes both project-level intent and the live
        # Draft. Presence flags let Undo restore old projects that legitimately
        # omitted these fields instead of turning absence into an explicit null.
        "manual_embedded_camera_present": "embedded_camera" in manual,
        "manual_embedded_camera": copy.deepcopy(manual.get("embedded_camera")),
        "settings_layout_present": "layout" in settings,
        "settings_layout": copy.deepcopy(settings.get("layout")),
        "draft_layout_present": "layout" in draft,
        "draft_layout": copy.deepcopy(draft.get("layout")),
        "embedded_layout_confirmed_present": "embedded_layout_confirmed" in draft,
        "embedded_layout_confirmed": copy.deepcopy(draft.get("embedded_layout_confirmed")),
    }


def _restore_timeline(project: dict[str, Any], snapshot: dict[str, Any]) -> None:
    draft = project.setdefault("draft", {})
    for key in ("cuts", "keep_ranges", "camera_plan", "edit_points", "output_duration", "removed_duration", "active_reel_candidate"):
        draft[key] = copy.deepcopy(snapshot.get(key))
    manual = project.setdefault("manual", {})
    manual["cuts"] = copy.deepcopy(snapshot.get("manual_cuts") or [])
    manual["keeps"] = copy.deepcopy(snapshot.get("manual_keeps") or [])
    manual["camera_overrides"] = copy.deepcopy(snapshot.get("manual_camera_overrides") or [])
    if isinstance(snapshot.get("manual_source_mixer"), dict):
        manual["source_mixer"] = copy.deepcopy(snapshot["manual_source_mixer"])
    else:
        manual.pop("source_mixer", None)
    if "manual_source_tracks_present" in snapshot:
        if snapshot.get("manual_source_tracks_present"):
            manual["source_tracks"] = copy.deepcopy(snapshot.get("manual_source_tracks"))
        else:
            manual.pop("source_tracks", None)
    if "manual_sequence_present" in snapshot:
        if snapshot.get("manual_sequence_present"):
            manual["sequence"] = copy.deepcopy(snapshot.get("manual_sequence"))
        else:
            manual.pop("sequence", None)
    if "manual_embedded_camera_present" in snapshot:
        if snapshot.get("manual_embedded_camera_present"):
            manual["embedded_camera"] = copy.deepcopy(snapshot.get("manual_embedded_camera"))
        else:
            manual.pop("embedded_camera", None)
    if "settings_layout_present" in snapshot:
        settings = project.setdefault("settings", {})
        if snapshot.get("settings_layout_present"):
            settings["layout"] = copy.deepcopy(snapshot.get("settings_layout"))
        else:
            settings.pop("layout", None)
    if "draft_layout_present" in snapshot:
        if snapshot.get("draft_layout_present"):
            draft["layout"] = copy.deepcopy(snapshot.get("draft_layout"))
        else:
            draft.pop("layout", None)
    if "embedded_layout_confirmed_present" in snapshot:
        if snapshot.get("embedded_layout_confirmed_present"):
            draft["embedded_layout_confirmed"] = copy.deepcopy(snapshot.get("embedded_layout_confirmed"))
        else:
            draft.pop("embedded_layout_confirmed", None)
    if isinstance(snapshot.get("ai_camera_plan"), list):
        draft["ai_camera_plan"] = copy.deepcopy(snapshot["ai_camera_plan"])
    else:
        draft.pop("ai_camera_plan", None)
    if isinstance(snapshot.get("reel_candidates"), list):
        draft["reel_candidates"] = copy.deepcopy(snapshot["reel_candidates"])
    else:
        draft.pop("reel_candidates", None)
    draft["edited_at"] = now_iso()


def _rebuild_timeline(project: dict[str, Any], cuts: list[dict[str, Any]]) -> None:
    draft = project.get("draft")
    if not isinstance(draft, dict):
        raise ManualEditError("Generate a draft before editing the timeline")
    duration = _duration(project)
    if duration <= 0:
        raise ManualEditError("Source duration is unavailable")
    normalized = [
        {"start": max(0.0, float(item["start"])), "end": min(duration, float(item["end"]))}
        for item in merge_ranges(cuts)
        if float(item["start"]) < duration and float(item["end"]) > 0
    ]
    normalized = merge_ranges(normalized)
    keep_ranges = invert_ranges(normalized, duration)
    if not keep_ranges:
        raise ManualEditError("An edit must keep at least 0.08 seconds")
    draft["cuts"] = normalized
    draft["keep_ranges"] = keep_ranges
    _rebuild_camera_plan(project)
    draft["output_duration"] = range_duration(keep_ranges)
    draft["removed_duration"] = round(max(0.0, duration - float(draft["output_duration"])), 3)
    draft["edited_at"] = now_iso()
    draft["status"] = "ready"


def _editable_clip_ranges(project: dict[str, Any]) -> list[dict[str, float]]:
    """Mirror ``editableClips`` in web/timeline.js, then normalize to milliseconds.

    The timeline coalesces near-duplicate splits within 30ms, clamps source
    boundaries, and never shows overlapping or sub-30ms selectable clips. Keep
    identity matching consistent with those displayed handles.
    """
    draft = project.get("draft")
    if not isinstance(draft, dict):
        raise ManualEditError("Generate a draft before editing the timeline")
    duration = _duration(project)
    if duration <= 0 or duration != duration or duration == float("inf"):
        return []
    points: set[float] = set()
    for raw in draft.get("edit_points") or []:
        try:
            point = float(raw)
        except (TypeError, ValueError):
            continue
        if point == point and 0 < point < duration:
            points.add(point)
    ranges: list[tuple[float, float]] = []
    for keep in draft.get("keep_ranges") or []:
        if not isinstance(keep, dict):
            continue
        try:
            start, end = float(keep["start"]), float(keep["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if start != start or end != end:
            continue
        start, end = max(0.0, start), min(duration, end)
        if abs(start) != float("inf") and abs(end) != float("inf") and end - start >= 0.03:
            ranges.append((start, end))
    clips: list[dict[str, float]] = []
    covered_until = 0.0
    ordered_points = sorted(points)
    for raw_start, end in sorted(ranges):
        start = max(raw_start, covered_until)
        if end - start < 0.03:
            continue
        boundaries = [start]
        for point in ordered_points:
            if point >= boundaries[-1] + 0.03 and point <= end - 0.03:
                boundaries.append(point)
        boundaries.append(end)
        clips.extend(
            {"start": round(left, 3), "end": round(right, 3)}
            for left, right in zip(boundaries, boundaries[1:]) if right - left >= 0.03
        )
        covered_until = end
    return clips


def _prepare_clip_trim(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate and stage one trim before touching live state or edit history.

    Clips remain in source order. A handle may reveal removed footage up to a
    neighbouring clip, but cannot cross that clip or secretly move its edges.
    Legacy interval helpers have an 80ms coalescing tolerance; reject precision
    edges they cannot preserve rather than silently accepting a different edit.
    """
    clips = _editable_clip_ranges(project)
    values: dict[str, float] = {}
    for key in ("start", "end", "new_start", "new_end"):
        if isinstance(payload.get(key), bool):
            raise ManualEditError(f"{key} must be a number")
        values[key] = _number(payload, key)
    selected = next((
        index for index, clip in enumerate(clips)
        if abs(clip["start"] - values["start"]) <= 0.001000001
        and abs(clip["end"] - values["end"]) <= 0.001000001
    ), None)
    if selected is None:
        raise ManualEditError("This clip has changed. Select it again before trimming")
    start, end = clips[selected]["start"], clips[selected]["end"]
    duration = _duration(project)
    if values["new_start"] < 0 or values["new_end"] > duration:
        raise ManualEditError("Trim boundaries must stay inside source A")
    new_start, new_end = round(values["new_start"], 3), round(values["new_end"], 3)
    if new_end - new_start < MIN_RANGE_SECONDS - RANGE_EPSILON:
        raise ManualEditError("A trimmed clip must keep at least 0.08 seconds")
    previous_end = clips[selected - 1]["end"] if selected else 0.0
    next_start = clips[selected + 1]["start"] if selected + 1 < len(clips) else duration
    if new_start < previous_end or new_end > next_start:
        raise ManualEditError("Trim boundaries cannot overlap or cross a neighbouring kept clip")
    if new_start == start and new_end == end:
        return None

    expected_clips = copy.deepcopy(clips)
    expected_clips[selected] = {"start": new_start, "end": new_end}
    expected_keeps = merge_ranges(expected_clips, gap=0.0)
    working = copy.deepcopy(project)
    manual = working.setdefault("manual", {})
    draft_cuts = copy.deepcopy(working["draft"].get("cuts") or [])
    removals = [
        (start, min(end, new_start)),
        (max(start, new_end), end),
    ]
    restores = [
        (new_start, min(new_end, start)),
        (max(new_start, end), new_end),
    ]
    for left, right in removals:
        if right <= left:
            continue
        draft_cuts = merge_ranges([*draft_cuts, {"start": left, "end": right}])
        manual["cuts"] = merge_ranges([*(manual.get("cuts") or []), {"start": left, "end": right}])
        manual["keeps"] = _subtract_range(manual.get("keeps") or [], left, right)
        _sync_reel_candidate_ranges(working, left, right, restore=False)
    for left, right in restores:
        if right <= left:
            continue
        draft_cuts = _subtract_range(draft_cuts, left, right)
        manual["cuts"] = _subtract_range(manual.get("cuts") or [], left, right)
        manual["keeps"] = merge_ranges([*(manual.get("keeps") or []), {"start": left, "end": right}])
        _sync_reel_candidate_ranges(working, left, right, restore=True)
    _rebuild_timeline(working, draft_cuts)
    actual_keeps = merge_ranges(working["draft"]["keep_ranges"], gap=0.0)
    plan_keeps = merge_ranges(working["draft"]["camera_plan"], gap=0.0)
    if actual_keeps != expected_keeps or plan_keeps != expected_keeps:
        raise ManualEditError(
            "The exact requested boundaries cannot be preserved with the current timeline precision. "
            "Use at least 0.081 seconds for kept clips and spacing, or join the neighbouring edge"
        )
    # Preserve the identity of touching clips after revealing an entire gap.
    # Drop split points inside the replacement clip so its new handles resolve
    # to one clip on the next request; unrelated splits stay untouched.
    points: set[float] = set()
    for raw in working["draft"].get("edit_points") or []:
        try:
            point = float(raw)
        except (TypeError, ValueError):
            continue
        if point == point and abs(point) != float("inf") and not new_start < point < new_end:
            points.add(round(point, 3))
    points.update((new_start, new_end))
    working["draft"]["edit_points"] = sorted(points)
    return working


def _sync_reel_candidate_ranges(project: dict[str, Any], start: float, end: float, *, restore: bool) -> None:
    """Carry an explicit timeline cut/restore across every ranked Reel option.

    Reel candidates are alternate automatic selections, while manual timeline
    choices are project-wide intent. Keeping the candidate payloads synchronized
    prevents an old manual cut from reappearing when the user switches options.
    The candidate list is part of the timeline snapshot, so Undo/Redo restores
    both the active draft and its alternatives atomically.
    """

    draft = project.get("draft")
    candidates = draft.get("reel_candidates") if isinstance(draft, dict) else None
    if not isinstance(candidates, list):
        return
    duration = _duration(project)
    overrides = project.setdefault("manual", {}).get("camera_overrides") or []
    has_b = bool(project.get("sources", {}).get("B"))
    synchronized: list[dict[str, Any]] = []
    for raw in candidates:
        if not isinstance(raw, dict) or not isinstance(raw.get("cuts"), list):
            continue
        candidate = copy.deepcopy(raw)
        if restore:
            cuts = _subtract_range(candidate["cuts"], start, end)
        else:
            cuts = merge_ranges([*candidate["cuts"], {"start": start, "end": end}])
        cuts = [
            {"start": max(0.0, float(item["start"])), "end": min(duration, float(item["end"]))}
            for item in merge_ranges(cuts)
            if float(item["start"]) < duration and float(item["end"]) > 0
        ]
        keep_ranges = invert_ranges(cuts, duration)
        if not keep_ranges:
            continue
        candidate["cuts"] = cuts
        candidate["keep_ranges"] = keep_ranges
        candidate["output_duration"] = round(range_duration(keep_ranges), 3)
        base_plan = candidate.get("ai_camera_plan")
        if isinstance(base_plan, list):
            candidate["camera_plan"] = apply_camera_overrides(
                base_plan,
                keep_ranges,
                overrides if isinstance(overrides, list) else [],
                has_b=has_b,
            )
        synchronized.append(candidate)
    draft["reel_candidates"] = synchronized


def _history(project: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    manual = project.setdefault("manual", {})
    raw = manual.get("_history")
    if not isinstance(raw, dict):
        raw = {"undo": [], "redo": []}
        manual["_history"] = raw
    for key in ("undo", "redo"):
        if not isinstance(raw.get(key), list):
            raw[key] = []
    return raw  # type: ignore[return-value]


def _set_history_counts(project: dict[str, Any], history: dict[str, list[dict[str, Any]]]) -> None:
    project.setdefault("manual", {})["history"] = {
        "undo_count": len(history["undo"]),
        "redo_count": len(history["redo"]),
    }


def _find_transcript_segment(project: dict[str, Any], segment_id: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    transcript = (project.get("analysis") or {}).get("transcript") or {}
    segments = transcript.get("segments") or []
    for index, segment in enumerate(segments):
        candidate = segment.get("id", index)
        if str(candidate) == str(segment_id):
            return segment, segments
    raise ManualEditError("Transcript segment was not found")


def _set_transcript_text(
    project: dict[str, Any], segment_id: Any, text: str, *, word_snapshot: dict[str, Any] | None = None,
) -> None:
    segment, segments = _find_transcript_segment(project, segment_id)
    segment["text"] = text
    if word_snapshot is not None:
        if word_snapshot.get("present"):
            segment["words"] = copy.deepcopy(word_snapshot.get("words"))
        else:
            segment.pop("words", None)
    else:
        words = segment.get("words")
        tokens = text.split()
        if isinstance(words, list) and len(words) == len(tokens) and all(isinstance(word, dict) for word in words):
            segment["words"] = [{**word, "word": token} for word, token in zip(words, tokens)]
        else:
            # A changed word count has no trustworthy per-word alignment. Use
            # the original segment timing until speech is aligned again.
            segment.pop("words", None)
    transcript = project["analysis"]["transcript"]
    transcript["text"] = " ".join(str(item.get("text") or "").strip() for item in segments).strip()
    for index, enriched in enumerate((project.get("analysis") or {}).get("segments") or []):
        if str(enriched.get("id", index)) == str(segment_id):
            enriched["text"] = text
            if "words" in segment:
                enriched["words"] = copy.deepcopy(segment["words"])
            else:
                enriched.pop("words", None)
    # A future Director run must rebuild semantic decisions from corrected words.
    project["analysis"].pop("story_hierarchy", None)
    project["analysis"].pop("editorial_cache", None)


def _semanticize_legacy_source_layouts(project: dict[str, Any], mixer: dict[str, Any]) -> None:
    """Preserve an old Draft visually while making future role swaps meaningful.

    Drafts created before semantic source roles stored physical ``A``/``B`` in
    camera plans.  Resolve those entries through the *previous* mixer before it
    is changed: the current picture stays identical, but later screen/camera
    swaps can now be applied without rebuilding the Storyline.
    """

    draft = project.get("draft")
    if not isinstance(draft, dict):
        return
    screen_slot = str(mixer.get("screen_slot") or "A").upper()
    camera_slot = str(mixer.get("camera_slot") or ("B" if screen_slot == "A" else "A")).upper()
    if {screen_slot, camera_slot} != {"A", "B"}:
        screen_slot, camera_slot = "A", "B"
    semantic = {screen_slot: "screen", camera_slot: "camera"}

    def convert_plan(plan: Any) -> None:
        if not isinstance(plan, list):
            return
        for item in plan:
            if not isinstance(item, dict):
                continue
            value = str(item.get("camera") or "").upper()
            if value in semantic:
                item["camera"] = semantic[value]

    convert_plan(draft.get("ai_camera_plan"))
    convert_plan(draft.get("camera_plan"))
    candidates = draft.get("reel_candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            convert_plan(candidate.get("ai_camera_plan"))
            convert_plan(candidate.get("camera_plan"))

    manual = project.setdefault("manual", {})
    overrides = manual.get("camera_overrides")
    if isinstance(overrides, list):
        for item in overrides:
            if not isinstance(item, dict):
                continue
            value = str(item.get("layout") or "").upper()
            if value in semantic:
                item["layout"] = semantic[value]

    for container in (draft, project.get("settings")):
        if not isinstance(container, dict):
            continue
        value = str(container.get("layout") or "").upper()
        if value in semantic:
            container["layout"] = semantic[value]


def _set_source_mixer(project: dict[str, Any], payload: dict[str, Any]) -> None:
    """Persist source roles even before a Draft exists.

    Director needs the user's chosen speech/audio source to build the first Draft,
    so this project-level routing decision cannot depend on an existing timeline.
    """

    if not project.get("sources", {}).get("B"):
        raise ManualEditError("Add a second source before assigning source roles")
    screen_slot = str(payload.get("screen_slot") or "").upper()
    camera_slot = str(payload.get("camera_slot") or "").upper()
    primary_role = str(payload.get("primary_role") or "screen").lower()
    audio_slot = str(payload.get("audio_slot") or "A").upper()
    if {screen_slot, camera_slot} != {"A", "B"}:
        raise ManualEditError("Screen and camera must use different sources")
    if primary_role not in {"screen", "camera"}:
        raise ManualEditError("Primary role must be screen or camera")
    sources = project.get("sources", {})
    has_any_audio = any((sources.get(slot) or {}).get("has_audio") for slot in ("A", "B"))
    if audio_slot not in {"A", "B"} or (has_any_audio and not (sources.get(audio_slot) or {}).get("has_audio")):
        raise ManualEditError("Choose a source that contains audio")
    manual = project.setdefault("manual", {})
    previous_mixer = manual.get("source_mixer") if isinstance(manual.get("source_mixer"), dict) else {}
    first_slot = str(payload.get("first_slot", previous_mixer.get("first_slot", "A")) or "").upper()
    if first_slot not in {"A", "B"}:
        raise ManualEditError("First source must be A or B")
    source_mixer = {
        "screen_slot": screen_slot,
        "camera_slot": camera_slot,
        "primary_role": primary_role,
        "audio_slot": audio_slot,
        "first_slot": first_slot,
    }
    if "stack_fit" in payload or "stack_fit" in previous_mixer:
        stack_fit = str(payload.get("stack_fit", previous_mixer.get("stack_fit", "contain")))
        if stack_fit not in {"cover", "contain"}:
            raise ManualEditError("Stack framing must be cover or contain")
        source_mixer["stack_fit"] = stack_fit
    # Absence means the user has not made an explicit framing choice yet. Once
    # present, even ``auto`` is intentional and must survive style changes.
    if "default_layout" in previous_mixer:
        previous_default = str(previous_mixer["default_layout"] or "").strip()
        legacy_default = previous_default.upper()
        if legacy_default in {"A", "B"}:
            previous_screen = str(previous_mixer.get("screen_slot") or "A").upper()
            previous_default = "screen" if legacy_default == previous_screen else "camera"
        if previous_default in SOURCE_MIXER_DEFAULT_LAYOUTS:
            source_mixer["default_layout"] = previous_default
    if "default_layout" in payload:
        if payload["default_layout"] is None:
            source_mixer.pop("default_layout", None)
        else:
            default_layout = str(payload["default_layout"] or "").strip().lower()
            if default_layout not in SOURCE_MIXER_DEFAULT_LAYOUTS:
                raise ManualEditError("Unknown default source layout")
            source_mixer["default_layout"] = default_layout
    if "sync_offset" in previous_mixer:
        source_mixer["sync_offset"] = previous_mixer["sync_offset"]
    if "sync_offset" in payload:
        if payload["sync_offset"] is None:
            source_mixer.pop("sync_offset", None)
        else:
            try:
                sync_offset = float(payload["sync_offset"])
            except (TypeError, ValueError) as exc:
                raise ManualEditError("Sync offset must be a number") from exc
            if sync_offset != sync_offset or abs(sync_offset) > 600:
                raise ManualEditError("Sync offset must be between -600 and 600 seconds")
            # Frame nudges at 29.97/59.94 fps must not accumulate a millisecond
            # rounding error on every save. The UI may still display millis.
            source_mixer["sync_offset"] = round(sync_offset, 9)
    _semanticize_legacy_source_layouts(project, previous_mixer)
    manual["source_mixer"] = source_mixer


def _set_embedded_camera(project: dict[str, Any], payload: dict[str, Any]) -> None:
    """Persist an explicit facecam rectangle for a single combined recording.

    Vision remains only a suggestion. This action is the user's confirmation,
    so it can safely activate ``embedded_stack`` even when face detection found
    nothing. A separate B source uses the Source Mixer instead and is rejected to
    avoid accidentally duplicating source A while hiding real source B footage.
    """

    sources = project.get("sources") if isinstance(project.get("sources"), dict) else {}
    if not isinstance(sources.get("A"), dict):
        raise ManualEditError("Add source A before marking an embedded camera")
    if isinstance(sources.get("B"), dict):
        raise ManualEditError("Remove source B before marking a camera inside source A")
    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise ManualEditError("enabled must be true or false")

    manual = project.setdefault("manual", {})
    if enabled:
        candidate = build_manual_embedded_candidate(
            {key: payload.get(key) for key in ("x", "y", "w", "h")},
            {"x": payload.get("content_x", 0.5), "y": payload.get("content_y", 0.5)},
        )
        if candidate is None:
            raise ManualEditError("Embedded camera rectangle must be a valid normalized x/y/w/h region")
        manual["embedded_camera"] = {
            key: copy.deepcopy(candidate[key])
            for key in ("x", "y", "w", "h", "content_focus", "content_region")
        }
        # This action intentionally applies to the whole edit. Keeping stale
        # per-range source overrides would make a later cut rebuild silently
        # undo that explicit choice.
        manual["camera_overrides"] = []
        project.setdefault("settings", {})["layout"] = "embedded_stack"
    else:
        manual.pop("embedded_camera", None)
        settings = project.setdefault("settings", {})
        if str(settings.get("layout") or "") == "embedded_stack":
            settings["layout"] = "auto"

    draft = project.get("draft")
    if not isinstance(draft, dict):
        return

    camera = "embedded_stack" if enabled else "A"
    keep_ranges = draft.get("keep_ranges") if isinstance(draft.get("keep_ranges"), list) else []
    plan = [
        {
            "start": round(float(item["start"]), 3),
            "end": round(float(item["end"]), 3),
            "camera": camera,
        }
        for item in keep_ranges
        if isinstance(item, dict) and float(item.get("end", 0)) > float(item.get("start", 0))
    ]
    if enabled:
        draft["layout"] = "embedded_stack"
        draft["embedded_layout_confirmed"] = True
        draft["ai_camera_plan"] = copy.deepcopy(plan)
        draft["camera_plan"] = copy.deepcopy(plan)
    else:
        if str(draft.get("layout") or "") == "embedded_stack":
            draft["layout"] = "auto"
        draft["embedded_layout_confirmed"] = False
        for key in ("ai_camera_plan", "camera_plan"):
            previous = draft.get(key)
            if isinstance(previous, list):
                draft[key] = [
                    {**copy.deepcopy(item), "camera": "A"}
                    if isinstance(item, dict) and str(item.get("camera") or "") == "embedded_stack"
                    else copy.deepcopy(item)
                    for item in previous
                ]

    candidates = draft.get("reel_candidates")
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_ranges = candidate.get("keep_ranges")
            if enabled and isinstance(candidate_ranges, list):
                candidate_plan = [
                    {
                        "start": round(float(item["start"]), 3),
                        "end": round(float(item["end"]), 3),
                        "camera": "embedded_stack",
                    }
                    for item in candidate_ranges
                    if isinstance(item, dict) and float(item.get("end", 0)) > float(item.get("start", 0))
                ]
                candidate["ai_camera_plan"] = copy.deepcopy(candidate_plan)
                candidate["camera_plan"] = copy.deepcopy(candidate_plan)
            elif not enabled:
                for key in ("ai_camera_plan", "camera_plan"):
                    previous = candidate.get(key)
                    if isinstance(previous, list):
                        candidate[key] = [
                            {**copy.deepcopy(item), "camera": "A"}
                            if isinstance(item, dict) and str(item.get("camera") or "") == "embedded_stack"
                            else copy.deepcopy(item)
                            for item in previous
                        ]
    draft["edited_at"] = now_iso()
    draft["status"] = "ready"


def _apply_history_entry(project: dict[str, Any], entry: dict[str, Any], side: str) -> None:
    if entry.get("kind") == "timeline":
        _restore_timeline(project, entry[side])
        return
    if entry.get("kind") == "transcript":
        _set_transcript_text(
            project, entry["segment_id"], str(entry[side]),
            word_snapshot=entry.get(f"{side}_words"),
        )
        return
    raise ManualEditError("Edit history is invalid")


def apply_manual_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Apply one bounded, undoable manual correction to an existing draft."""
    if not isinstance(payload, dict):
        raise ManualEditError("Request body must be an object")
    action = str(payload.get("action") or "").strip().lower()
    # Validate independent track operations before creating history or touching
    # the project. Failed edits and genuine no-ops must preserve the whole state.
    try:
        sequence_edit = prepare_sequence_edit(project, payload) if action in SEQUENCE_ACTIONS else None
        tracks = prepare_source_track_edit(project, payload) if action in TRACK_ACTIONS else None
        if action == "set_source_mixer":
            validate_source_track_sync(project, payload)
    except SourceTrackError as exc:
        raise ManualEditError(str(exc)) from exc
    if action in TRACK_ACTIONS and tracks is None:
        return project
    if action in SEQUENCE_ACTIONS and sequence_edit is None:
        return project
    trimmed = _prepare_clip_trim(project, payload) if action == "trim_clip" else None
    if action == "trim_clip" and trimmed is None:
        return project
    history = _history(project)

    if action in {"set_source_mixer", "set_embedded_camera"} and not isinstance(project.get("draft"), dict):
        if action == "set_source_mixer":
            _set_source_mixer(project, payload)
        else:
            _set_embedded_camera(project, payload)
        # There is no timeline snapshot to undo yet; once Director creates a
        # Draft, subsequent routing changes keep the normal undo/redo contract.
        _set_history_counts(project, history)
        return project

    if action in {"undo", "redo"}:
        source_key, target_key = ("undo", "redo") if action == "undo" else ("redo", "undo")
        if not history[source_key]:
            raise ManualEditError(f"Nothing to {action}")
        entry = history[source_key].pop()
        _apply_history_entry(project, entry, "before" if action == "undo" else "after")
        history[target_key].append(entry)
        history[target_key] = history[target_key][-HISTORY_LIMIT:]
        _set_history_counts(project, history)
        return project

    if action == "transcript_text":
        segment_id = payload.get("segment_id")
        segment, _ = _find_transcript_segment(project, segment_id)
        old_text = str(segment.get("text") or "")
        new_text = str(payload.get("text") or "").strip()[:4000]
        if not new_text:
            raise ManualEditError("Transcript text cannot be empty")
        if new_text == old_text:
            _set_history_counts(project, history)
            return project
        entry = {
            "kind": "transcript", "segment_id": segment_id, "before": old_text, "after": new_text,
            "before_words": {"present": "words" in segment, "words": copy.deepcopy(segment.get("words"))},
        }
        _set_transcript_text(project, segment_id, new_text)
        entry["after_words"] = {"present": "words" in segment, "words": copy.deepcopy(segment.get("words"))}
    elif action in SEQUENCE_ACTIONS | TRACK_ACTIONS | {"delete_range", "restore_range", "trim_clip", "split", "set_camera_layout", "set_source_mixer", "set_embedded_camera", "apply_reel_candidate"}:
        if not isinstance(project.get("draft"), dict):
            raise ManualEditError("Generate a draft before editing the timeline")
        before = _timeline_snapshot(project)
        if action in SEQUENCE_ACTIONS:
            manual = project.setdefault("manual", {})
            for key in ("sequence", "source_tracks"):
                if key in sequence_edit:
                    manual[key] = sequence_edit[key]
                else:
                    manual.pop(key, None)
            project["draft"]["edited_at"] = now_iso()
            project["draft"]["status"] = "ready"
        elif action in TRACK_ACTIONS:
            manual = project.setdefault("manual", {})
            if tracks:
                manual["source_tracks"] = tracks
            else:
                manual.pop("source_tracks", None)
            project["draft"]["edited_at"] = now_iso()
            project["draft"]["status"] = "ready"
        elif action == "trim_clip":
            project["draft"] = trimmed["draft"]
            for key in ("cuts", "keeps"):
                if key in trimmed["manual"]:
                    project.setdefault("manual", {})[key] = trimmed["manual"][key]
        elif action == "delete_range":
            start, end = _requested_range(project, payload)
            draft_cuts = merge_ranges([*(project["draft"].get("cuts") or []), {"start": start, "end": end}])
            manual_cuts = merge_ranges([*(project.setdefault("manual", {}).get("cuts") or []), {"start": start, "end": end}])
            _rebuild_timeline(project, draft_cuts)
            project["manual"]["cuts"] = manual_cuts
            project["manual"]["keeps"] = _subtract_range(project["manual"].get("keeps") or [], start, end)
            _sync_reel_candidate_ranges(project, start, end, restore=False)
        elif action == "restore_range":
            start, end = _requested_range(project, payload)
            _rebuild_timeline(project, _subtract_range(project["draft"].get("cuts") or [], start, end))
            project.setdefault("manual", {})["cuts"] = _subtract_range(project["manual"].get("cuts") or [], start, end)
            project["manual"]["keeps"] = merge_ranges([*(project["manual"].get("keeps") or []), {"start": start, "end": end}])
            _sync_reel_candidate_ranges(project, start, end, restore=True)
        elif action == "split":
            time = clamp(_number(payload, "time"), 0.0, _duration(project))
            points = sorted({round(float(item), 3) for item in project["draft"].get("edit_points") or []} | {round(time, 3)})
            project["draft"]["edit_points"] = points
            split_plan: list[dict[str, Any]] = []
            for item in project["draft"].get("camera_plan") or []:
                start, end = float(item.get("start", 0)), float(item.get("end", 0))
                if start + MIN_RANGE_SECONDS - RANGE_EPSILON <= time <= end - MIN_RANGE_SECONDS + RANGE_EPSILON:
                    split_plan.extend([{**item, "end": round(time, 3)}, {**item, "start": round(time, 3)}])
                else:
                    split_plan.append(item)
            project["draft"]["camera_plan"] = split_plan
            project["draft"]["edited_at"] = now_iso()
        elif action == "set_camera_layout":
            layout = str(payload.get("layout") or "").strip().lower()
            if layout not in CAMERA_OVERRIDE_LAYOUTS | {"auto"}:
                raise ManualEditError("Unknown source layout")
            if layout in TWO_SOURCE_LAYOUTS and not project.get("sources", {}).get("B"):
                raise ManualEditError("Add a second source before using this layout")
            start, end = _requested_range(project, payload)
            manual = project.setdefault("manual", {})
            previous = manual.get("camera_overrides") if isinstance(manual.get("camera_overrides"), list) else []
            manual["camera_overrides"] = _replace_camera_override(previous, start, end, layout)
            _rebuild_camera_plan(project)
            project["draft"]["edited_at"] = now_iso()
        elif action == "apply_reel_candidate":
            candidate_id = str(payload.get("candidate_id") or "").strip()
            candidates = project["draft"].get("reel_candidates")
            if not isinstance(candidates, list):
                raise ManualEditError("This draft has no Reel alternatives")
            candidate = next(
                (item for item in candidates if isinstance(item, dict) and str(item.get("id")) == candidate_id),
                None,
            )
            if candidate is None:
                raise ManualEditError("Reel alternative was not found")
            candidate_cuts = candidate.get("cuts")
            candidate_plan = candidate.get("ai_camera_plan")
            if not isinstance(candidate_cuts, list) or not isinstance(candidate_plan, list):
                raise ManualEditError("Reel alternative is invalid")
            _rebuild_timeline(project, apply_timeline_overrides(candidate_cuts, project.get("manual")))
            project["draft"]["ai_camera_plan"] = copy.deepcopy(candidate_plan)
            _rebuild_camera_plan(project)
            project["draft"]["active_reel_candidate"] = candidate_id
            project["draft"]["edited_at"] = now_iso()
        elif action == "set_source_mixer":
            _set_source_mixer(project, payload)
            project["draft"]["edited_at"] = now_iso()
        else:
            _set_embedded_camera(project, payload)
        entry = {"kind": "timeline", "before": before, "after": _timeline_snapshot(project)}
    else:
        raise ManualEditError("Unknown manual edit action")

    history["undo"].append(entry)
    history["undo"] = history["undo"][-HISTORY_LIMIT:]
    history["redo"] = []
    _set_history_counts(project, history)
    return project


def strip_private_edit_history(project: dict[str, Any]) -> None:
    manual = project.get("manual")
    if isinstance(manual, dict):
        manual.pop("_history", None)
