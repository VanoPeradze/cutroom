"""Non-destructive source clips on the existing source-A timeline.

Story keep-ranges still decide which timeline seconds reach the output. Source
tracks decide which local media second occupies each of those seconds. Missing
slots are implicit, while an explicit empty array intentionally means a gap.
"""
from __future__ import annotations

import copy
import math
import uuid
from typing import Any

from .frame_rates import EXPORT_FPS_CHOICES, project_export_fps


MIN_CLIP_SECONDS = 0.08
EPSILON = 1e-9
MAX_TRACK_CLIPS = 200
MAX_SEQUENCE_CLIPS = 500
MAX_SEQUENCE_SECONDS = 24 * 60 * 60
TRACK_ACTIONS = frozenset({
    "track_split", "track_remove_range", "track_restore_range",
    "track_move", "track_trim", "track_reset",
})


class SourceTrackError(ValueError):
    """A source-track operation could not be applied without losing media."""


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def source_sync_offset(project: dict[str, Any]) -> float:
    manual = project.get("manual") or {}
    mixer = manual.get("source_mixer") or {}
    value = mixer.get("sync_offset")
    if value is None:
        value = ((project.get("analysis") or {}).get("sync") or {}).get("offset", 0.0)
    offset = _finite(value)
    return offset if abs(offset) <= 600 else 0.0


def _duration(project: dict[str, Any], slot: str) -> float:
    source = (project.get("sources") or {}).get(slot) or {}
    return max(0.0, _finite(source.get("duration")))


def has_sequence(project: dict[str, Any]) -> bool:
    sequence = (project.get("manual") or {}).get("sequence")
    return isinstance(sequence, dict) and type(sequence.get("version")) is int and sequence["version"] == 1


def timeline_duration(project: dict[str, Any]) -> float:
    if has_sequence(project):
        return max(0.0, min(MAX_SEQUENCE_SECONDS, _finite(project["manual"]["sequence"].get("duration"))))
    return _duration(project, "A")


def minimum_clip_seconds(project: dict[str, Any]) -> float:
    return 1.0 / project_export_fps(project) if has_sequence(project) else MIN_CLIP_SECONDS


def _clip_limit(project: dict[str, Any]) -> int:
    return MAX_SEQUENCE_CLIPS if has_sequence(project) else MAX_TRACK_CLIPS


def has_source_tracks(project: dict[str, Any]) -> bool:
    tracks = (project.get("manual") or {}).get("source_tracks")
    return isinstance(tracks, dict) and any(slot in tracks for slot in ("A", "B"))


def _implicit(project: dict[str, Any], slot: str) -> list[dict[str, Any]]:
    if slot not in {"A", "B"}:
        return []
    duration = _duration(project, slot)
    master = _duration(project, "A")
    offset = source_sync_offset(project) if slot == "B" else 0.0
    start, end = max(0.0, offset), min(master, offset + duration)
    if end - start < MIN_CLIP_SECONDS - EPSILON:
        return []
    return [{"id": f"{slot}:base", "start": start, "end": end, "source_start": max(0.0, -offset)}]


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise SourceTrackError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SourceTrackError(f"{name} must be a finite number") from exc
    if not math.isfinite(number):
        raise SourceTrackError(f"{name} must be a finite number")
    return round(number, 9)


def _validate_clip(project: dict[str, Any], slot: str, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise SourceTrackError("Source clips must be objects")
    clip_id = item.get("id")
    if not isinstance(clip_id, str) or not clip_id.strip() or len(clip_id) > 128:
        raise SourceTrackError("Source clips require a valid clip ID")
    start = _number(item.get("start"), "start")
    end = _number(item.get("end"), "end")
    source_start = _number(item.get("source_start"), "source_start")
    if start < 0 or end > timeline_duration(project) + EPSILON:
        raise SourceTrackError("Keep source clips inside the edit timeline" if has_sequence(project) else "Keep source clips inside the source A timeline")
    # Stored media survives a later 60 -> 30 fps export override. The renderer
    # quantizes it to that export grid; a read must never turn it into a gap.
    read_minimum = 1.0 / max(EXPORT_FPS_CHOICES) if has_sequence(project) else MIN_CLIP_SECONDS
    if end - start < read_minimum - EPSILON:
        raise SourceTrackError("Source clips must contain at least one output frame" if has_sequence(project) else "Source clips must be at least 0.08 seconds long")
    if source_start < 0 or source_start + end - start > _duration(project, slot) + EPSILON:
        raise SourceTrackError(f"The clip extends beyond source {slot}'s media")
    result = {"id": clip_id, "start": start, "end": end, "source_start": source_start}
    if "video_speed" in item or "video_source_start" in item:
        speed = _number(item.get("video_speed", 1), "video speed")
        video_start = _number(item.get("video_source_start", source_start), "video source start")
        if not 0.25 <= speed <= 4 or video_start < 0:
            raise SourceTrackError("Picture speed must be between 0.25 and 4 with a nonnegative source start")
        result.update(video_speed=speed, video_source_start=video_start)
    if "crop" in item:
        raw = item["crop"]
        if not isinstance(raw, dict) or set(raw) != {"x", "y", "zoom"}:
            raise SourceTrackError("Clip framing requires x, y and zoom")
        crop = {key: _number(raw[key], f"crop {key}") for key in ("x", "y", "zoom")}
        if not (0 <= crop["x"] <= 1 and 0 <= crop["y"] <= 1 and 1 <= crop["zoom"] <= 3):
            raise SourceTrackError("Clip framing must stay within the supported focus and zoom range")
        result["crop"] = crop
    return result


def _shift_video_start(clip: dict[str, Any], delta: float) -> dict[str, float]:
    """Preserve the independent picture clock when slicing an audio-clock clip."""
    if "video_speed" not in clip and "video_source_start" not in clip:
        return {}
    return {"video_source_start": round(max(0.0, clip.get("video_source_start", clip["source_start"]) + delta * clip.get("video_speed", 1)), 9)}


def _validated(project: dict[str, Any], slot: str, clips: Any) -> list[dict[str, Any]]:
    if not isinstance(clips, list) or len(clips) > _clip_limit(project):
        raise SourceTrackError(f"A source track supports up to {_clip_limit(project)} clips")
    result = sorted((_validate_clip(project, slot, clip) for clip in clips), key=lambda clip: (clip["start"], clip["end"]))
    seen: set[str] = set()
    previous_end = 0.0
    for clip in result:
        if clip["id"] in seen:
            raise SourceTrackError("Source clip IDs must be unique within their track")
        if clip["start"] < previous_end - EPSILON:
            raise SourceTrackError("Source clips cannot overlap on the same track; choose an empty space")
        seen.add(clip["id"])
        previous_end = clip["end"]
    return result


def source_track_clips(project: dict[str, Any], slot: str) -> list[dict[str, Any]]:
    """Return safe detached clips, including the legacy implicit source mapping.

    Corrupt explicit data fails closed: malformed/overlapping clips are omitted,
    never replaced with footage the user may intentionally have removed.
    """
    slot = str(slot).upper()
    if slot not in {"A", "B"} or not _duration(project, slot):
        return []
    tracks = (project.get("manual") or {}).get("source_tracks")
    if not isinstance(tracks, dict) or slot not in tracks:
        return [] if has_sequence(project) else _implicit(project, slot)
    raw = tracks[slot]
    if not isinstance(raw, list) or len(raw) > _clip_limit(project):
        return []
    clips = []
    for item in raw:
        try:
            clips.append(_validate_clip(project, slot, item))
        except SourceTrackError:
            continue
    result = []
    seen: set[str] = set()
    for clip in sorted(clips, key=lambda clip: (clip["start"], clip["end"])):
        if clip["id"] in seen or (result and clip["start"] < result[-1]["end"] - EPSILON):
            continue
        seen.add(clip["id"])
        result.append(clip)
    return result


def track_at(project: dict[str, Any], slot: str, time: float) -> dict[str, Any] | None:
    timestamp = _finite(time, float("nan"))
    return next((clip for clip in source_track_clips(project, slot) if clip["start"] <= timestamp < clip["end"]), None)


def source_track_boundaries(project: dict[str, Any]) -> list[float]:
    return sorted({clip[edge] for slot in ("A", "B") for clip in source_track_clips(project, slot) for edge in ("start", "end")})


def validate_source_track_sync(project: dict[str, Any], payload: dict[str, Any]) -> None:
    """Global B sync cannot silently remap an independently edited B track."""
    tracks = (project.get("manual") or {}).get("source_tracks")
    if "sync_offset" not in payload or not isinstance(tracks, dict) or "B" not in tracks:
        return
    proposed = copy.deepcopy(project)
    mixer = proposed.setdefault("manual", {}).setdefault("source_mixer", {})
    mixer["sync_offset"] = payload["sync_offset"]
    if abs(source_sync_offset(project) - source_sync_offset(proposed)) > EPSILON:
        raise SourceTrackError("Reset source B's track before changing its global sync offset; move its clips to adjust edited timing")


def _new_id(slot: str) -> str:
    return f"{slot}:{uuid.uuid4().hex[:16]}"


def _range(project: dict[str, Any], payload: dict[str, Any]) -> tuple[float, float]:
    start, end = _number(payload.get("start"), "start"), _number(payload.get("end"), "end")
    if start < 0 or end > _duration(project, "A") + EPSILON:
        raise SourceTrackError("Select a range inside the source A timeline")
    if end - start < MIN_CLIP_SECONDS - EPSILON:
        raise SourceTrackError("Select at least 0.08 seconds in timeline order")
    return start, end


def prepare_source_track_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Build and validate a new tracks object without mutating project/history.

    None means a genuine no-op, so it must not consume Undo or clear Redo.
    """
    action = str(payload.get("action") or "").strip().lower()
    if action not in TRACK_ACTIONS:
        raise SourceTrackError("Unknown source track action")
    slot = str(payload.get("slot") or "").upper()
    if slot not in {"A", "B"} or _duration(project, slot) <= 0:
        raise SourceTrackError("Choose an existing source track A or B")
    if not isinstance(project.get("draft"), dict):
        raise SourceTrackError("Generate a draft before editing source tracks")
    raw_tracks = (project.get("manual") or {}).get("source_tracks")
    if raw_tracks is not None and not isinstance(raw_tracks, dict):
        raise SourceTrackError("Source track data is invalid")
    tracks = copy.deepcopy(raw_tracks or {})
    if action == "track_reset":
        if slot not in tracks:
            return None
        tracks.pop(slot)
        return tracks
    current = _validated(project, slot, tracks[slot]) if slot in tracks else _implicit(project, slot)
    updated = copy.deepcopy(current)
    if action == "track_split":
        time = _number(payload.get("time"), "time")
        if time < 0 or time > _duration(project, "A") + EPSILON:
            raise SourceTrackError("Choose a split inside the source A timeline")
        if any(abs(time - clip[edge]) <= EPSILON for clip in current for edge in ("start", "end")):
            return None
        clip = next((clip for clip in updated if clip["start"] < time < clip["end"]), None)
        if clip is None:
            raise SourceTrackError("There is no source clip at the playhead")
        right = {**clip, **_shift_video_start(clip, time - clip["start"]), "id": _new_id(slot), "start": time, "source_start": clip["source_start"] + time - clip["start"]}
        clip["end"] = time
        updated.append(right)
    elif action == "track_remove_range":
        start, end = _range(project, payload)
        updated = []
        for clip in current:
            if clip["end"] <= start or clip["start"] >= end:
                updated.append(clip)
                continue
            if clip["start"] < start:
                updated.append({**clip, "end": start})
            if clip["end"] > end:
                updated.append({**clip, **_shift_video_start(clip, end - clip["start"]), "id": _new_id(slot) if clip["start"] < start else clip["id"], "start": end, "source_start": clip["source_start"] + end - clip["start"]})
    elif action == "track_restore_range":
        start, end = _range(project, payload)
        for base in _implicit(project, slot):
            left, right = max(start, base["start"]), min(end, base["end"])
            cursor = left
            for clip in current:
                if clip["end"] <= cursor or clip["start"] >= right:
                    continue
                if clip["start"] > cursor:
                    updated.append({"id": _new_id(slot), "start": cursor, "end": clip["start"], "source_start": base["source_start"] + cursor - base["start"]})
                cursor = max(cursor, clip["end"])
            if right > cursor:
                updated.append({"id": _new_id(slot), "start": cursor, "end": right, "source_start": base["source_start"] + cursor - base["start"]})
    elif action in {"track_move", "track_trim"}:
        clip = next((clip for clip in updated if clip["id"] == payload.get("clip_id")), None)
        if clip is None:
            raise SourceTrackError("The source clip no longer exists; select it again")
        start = _number(payload.get("start"), "start")
        if action == "track_move":
            clip["end"] = start + clip["end"] - clip["start"]
            clip["start"] = start
        else:
            source_start = _number(payload.get("source_start"), "source_start")
            clip.update(**_shift_video_start(clip, source_start - clip["source_start"]), start=start, end=_number(payload.get("end"), "end"), source_start=source_start)
    normalized = _validated(project, slot, updated)
    if normalized == current:
        return None
    tracks[slot] = normalized
    return tracks
