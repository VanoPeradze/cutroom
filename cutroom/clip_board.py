"""Read-only Clips board: ranked short moments across one source recording.

The board reuses analysis that is already saved with the project (the audio
level profile, an optional transcript and optional gameplay-vision windows). It
never runs a model, decodes media, renders or saves the project. Scores are
measured signals relative to this recording, not a prediction of views.
"""
from __future__ import annotations

import math
from typing import Any

from .director import (
    _REACTION_CUE,
    _energy_levels,
    _finite_number,
    _moment_signals,
    _snap_window_to_speech,
)
from .visual_moments import VisualTimeline, apply_visual_overrides

CLIP_LENGTHS = (15, 30, 45, 60)
DEFAULT_LENGTH = 30
DEFAULT_COUNT = 12
MAX_COUNT = 24
MAX_HEAT_POINTS = 240
MIN_GAP_SECONDS = 2.0
HOOK_CHARS = 160
EXCERPT_CHARS = 320


class ClipBoardError(ValueError):
    """The request cannot produce a board (bad input, not missing analysis)."""


def _waveform(project: dict[str, Any]) -> list[dict[str, Any]]:
    profile = ((project.get("pre_analysis") or {}).get("audio") or {}).get("A") or {}
    rows = profile.get("waveform") if isinstance(profile, dict) else None
    return [row for row in rows or [] if isinstance(row, dict)]


def _segments(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Transcript lines on the source A clock, or nothing.

    A transcript measured from source B, or with a timeline offset, would place
    words at the wrong moments of A, so it is ignored rather than guessed.
    """
    analysis = project.get("analysis") or {}
    slot = str(analysis.get("audio_source") or "A").upper()
    offset = _finite_number(analysis.get("audio_timeline_offset"), 0.0)
    if slot != "A" or abs(offset) > 1e-6:
        return []
    rows = analysis.get("segments") or []
    return [row for row in rows if isinstance(row, dict) and str(row.get("text") or "").strip()]


def _visual(project: dict[str, Any]) -> VisualTimeline | None:
    visual = (project.get("analysis") or {}).get("visual_moments")
    if not isinstance(visual, dict) or not visual.get("available"):
        return None
    if str(visual.get("source_slot") or "A").upper() != "A" or abs(_finite_number(visual.get("timeline_offset"), 0.0)) > 1e-6:
        return None
    timeline = VisualTimeline(apply_visual_overrides(visual, (project.get("manual") or {}).get("visual_overrides")))
    return timeline or None


def _overlaps(start: float, end: float, row: dict[str, Any]) -> bool:
    return _finite_number(row.get("end")) > start and _finite_number(row.get("start")) < end


def _peak_time(start: float, end: float, waveform: list[dict[str, Any]]) -> float:
    best, best_level = (start + end) / 2.0, -math.inf
    for row in waveform:
        if not _overlaps(start, end, row):
            continue
        level = _finite_number(row.get("rms_dbfs"), -120.0) * 0.7 + _finite_number(row.get("peak_dbfs"), -120.0) * 0.3
        if level > best_level:
            row_start = max(start, _finite_number(row.get("start")))
            row_end = min(end, _finite_number(row.get("end")))
            best, best_level = (row_start + row_end) / 2.0, level
    return round(best, 3)


def _clip_text(start: float, end: float, segments: list[dict[str, Any]]) -> tuple[str, str, int]:
    lines = [str(row.get("text") or "").strip() for row in segments if _overlaps(start, end, row)]
    lines = [line for line in lines if line]
    hook = lines[0] if lines else ""
    if len(hook) > HOOK_CHARS:
        hook = hook[:HOOK_CHARS - 1].rstrip() + "…"
    excerpt = " ".join(lines)
    if len(excerpt) > EXCERPT_CHARS:
        excerpt = excerpt[:EXCERPT_CHARS - 1].rstrip() + "…"
    reactions = sum(1 for line in lines if "!" in line or _REACTION_CUE.search(line))
    return hook, excerpt, reactions


def _percentile(score: int, scores: list[int]) -> int:
    if not scores:
        return 0
    below = sum(1 for value in scores if value < score)
    ties = sum(1 for value in scores if value == score)
    return int(round(100.0 * (below + ties / 2.0) / len(scores)))


# Laughter and applause mark moments people reacted to; music alone does not.
SOUND_EVENT_BONUS = {"laughter": 10.0, "applause": 8.0}


def _sound_events(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Saved video-map events on the source A clock, or nothing."""
    analysis = project.get("analysis") or {}
    if str(analysis.get("audio_source") or "A").upper() != "A" or abs(_finite_number(analysis.get("audio_timeline_offset"), 0.0)) > 1e-6:
        return []
    video_map = analysis.get("video_map")
    if not isinstance(video_map, dict) or not video_map.get("available"):
        return []
    return [row for row in video_map.get("events") or []
            if isinstance(row, dict) and row.get("type") in {"laughter", "applause", "music"}
            and _finite_number(row.get("end")) > _finite_number(row.get("start"))]


def _events_in(start: float, end: float, events: list[dict[str, Any]]) -> list[str]:
    return sorted({str(row["type"]) for row in events
                   if _finite_number(row.get("start")) < end and _finite_number(row.get("end")) > start})


def _reasons(signals: dict[str, Any], strength: int, reactions: int, has_speech: bool,
             sound_events: list[str] | None = None) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    if strength >= 75:
        reasons.append({"kind": "energy", "level": "high"})
    elif strength >= 40:
        reasons.append({"kind": "energy", "level": "medium"})
    visual = signals.get("visual") or {}
    action = int(visual.get("action") or 0)
    if action >= 40:
        reasons.append({"kind": "action", "value": action})
    if reactions:
        reasons.append({"kind": "reactions", "count": reactions})
    event = str(visual.get("event") or "").strip()
    if event:
        reasons.append({"kind": "event", "text": event[:140]})
    if visual.get("screen") and visual.get("screen") != "gameplay":
        reasons.append({"kind": "screen", "value": str(visual["screen"])})
    for kind in sound_events or []:
        reasons.append({"kind": "sound_event", "type": kind})
    if has_speech and not reactions:
        reasons.append({"kind": "speech"})
    return reasons


def build_clip_board(project: dict[str, Any], *, length: Any = DEFAULT_LENGTH, count: Any = DEFAULT_COUNT) -> dict[str, Any]:
    """Rank non-overlapping windows of ``length`` seconds across source A."""
    try:
        length = int(length)
        count = int(count)
    except (TypeError, ValueError) as error:
        raise ClipBoardError("Clip length and count must be whole numbers.") from error
    if length not in CLIP_LENGTHS:
        raise ClipBoardError(f"Clip length must be one of {', '.join(map(str, CLIP_LENGTHS))} seconds.")
    if not 1 <= count <= MAX_COUNT:
        raise ClipBoardError(f"Clip count must be between 1 and {MAX_COUNT}.")

    source = (project.get("sources") or {}).get("A")
    base = {
        "project_id": project.get("id"),
        "revision": project.get("revision"),
        "length": length,
        "source_clock": "A",
        "clips": [],
        "heat": [],
        "signals": {"audio": False, "transcript": False, "vision": False},
    }
    if not isinstance(source, dict):
        return {**base, "available": False, "reason": "no_source"}
    duration = _finite_number(source.get("duration"))
    base["source_duration"] = round(duration, 3)
    if duration <= 0:
        return {**base, "available": False, "reason": "no_source"}

    waveform = _waveform(project)
    levels = _energy_levels(waveform) if waveform else None
    if not levels:
        reason = "no_audio" if source.get("has_audio") is False else "audio_profile_missing"
        return {**base, "available": False, "reason": reason}
    segments = _segments(project)
    visual = _visual(project)
    events = _sound_events(project)
    base["signals"] = {"audio": True, "transcript": bool(segments), "vision": bool(visual)}
    if events:
        base["signals"]["sound_events"] = True

    window = float(min(length, duration))
    step = max(1.0, window / 6.0)
    windows: list[tuple[float, float, dict[str, Any]]] = []
    position = 0.0
    while position + window <= duration + 1e-6:
        signals = _moment_signals(position, position + window, waveform, segments, levels, visual)
        bonus = sum(SOUND_EVENT_BONUS.get(kind, 0.0) for kind in _events_in(position, position + window, events))
        if bonus:
            signals = {**signals, "score": min(100.0, float(signals["score"]) + bonus)}
        windows.append((position, position + window, signals))
        position += step
    if not windows:
        return {**base, "available": False, "reason": "too_short"}
    scores = [signals["score"] for _, _, signals in windows]

    stride = max(1, math.ceil(len(windows) / MAX_HEAT_POINTS))
    base["heat"] = [
        {"start": round(start, 3), "end": round(end, 3), "strength": _percentile(signals["score"], scores)}
        for start, end, signals in windows[::stride]
    ]

    chosen: list[tuple[float, float, dict[str, Any]]] = []
    for start, end, signals in sorted(windows, key=lambda row: (-row[2]["score"], row[0])):
        if len(chosen) >= count:
            break
        snapped_start, snapped_end = _snap_window_to_speech(start, end, duration, segments)
        if snapped_end - snapped_start < min(window, 5.0) * 0.6:
            snapped_start, snapped_end = round(start, 3), round(min(duration, end), 3)
        if any(snapped_start < other_end + MIN_GAP_SECONDS and snapped_end > other_start - MIN_GAP_SECONDS for other_start, other_end, _ in chosen):
            continue
        chosen.append((snapped_start, snapped_end, signals))

    clips = []
    for rank, (start, end, signals) in enumerate(chosen, start=1):
        hook, excerpt, reactions = _clip_text(start, end, segments)
        strength = _percentile(signals["score"], scores)
        clips.append({
            "id": f"clip-{length}-{int(round(start * 1000))}",
            "rank": rank,
            "start": start,
            "end": end,
            "duration": round(end - start, 3),
            "peak": _peak_time(start, end, waveform),
            "score": int(signals["score"]),
            "strength": strength,
            "hook": hook,
            "excerpt": excerpt,
            "reasons": _reasons(signals, strength, reactions, bool(excerpt), _events_in(start, end, events)),
        })
    return {**base, "available": True, "reason": None, "clips": clips}
