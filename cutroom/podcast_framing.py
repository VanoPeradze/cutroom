"""Explicit framing of a user-confirmed, clean, stacked two-person file.

These are manual crop presets, not speaker detection or diarization. The first
slice requires source-matching portrait output, so Both really keeps the frame.
"""
from __future__ import annotations

import math
from typing import Any

from .source_tracks import SourceTrackError, source_track_clips


def _covers(rows, start: float, end: float) -> bool:
    cursor = start
    for row in sorted(rows, key=lambda r: float(r["start"])):
        if float(row["end"]) <= cursor:
            continue
        if float(row["start"]) > cursor + 1e-6:
            return False
        cursor = max(cursor, float(row["end"]))
        if cursor >= end - 1e-6:
            return True
    return False


def podcast_crop(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, float]:
    source = (project.get("sources") or {}).get("A") or {}
    if payload.get("slot") != "A" or (project.get("sources") or {}).get("B"):
        raise SourceTrackError("Manual podcast presets support one stacked source A, not separate camera feeds.")
    if not source.get("generation") or payload.get("source_generation") != source["generation"]:
        raise SourceTrackError("The source changed. Review its panels before framing again.")
    if payload.get("confirmed_stacked_clean") is not True:
        raise SourceTrackError("Confirm vertically stacked panels, the marked divider and no captions burned into the source.")
    if source.get("has_burned_captions") is True:
        raise SourceTrackError("This source already has burned-in captions. Keep its full frame or use clean footage.")
    width, height = float(source.get("width") or 0), float(source.get("height") or 0)
    if not all(math.isfinite(n) and n > 0 for n in (width, height)) or width >= height or float(source.get("rotation") or 0) != 0:
        raise SourceTrackError("These presets need an upright portrait source with two equal stacked panels.")
    aspect = (project.get("settings") or {}).get("aspect", "9:16")
    ratios = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1., "4:5": 4 / 5}
    output_ratio = width / height if aspect == "source" else ratios.get(aspect)
    if output_ratio is None or abs(output_ratio / (width / height) - 1) > .005:
        raise SourceTrackError("Choose source-matching portrait output first. These presets do not guess framing for a different aspect ratio.")
    focus = payload.get("focus")
    if not isinstance(focus, str) or focus not in {"both", "top", "bottom"}:
        raise SourceTrackError("Choose Both, top participant or bottom participant.")
    split = payload.get("panel_split")
    if isinstance(split, bool) or not isinstance(split, (int, float)) or not math.isfinite(split) or not .34 <= split <= .66:
        raise SourceTrackError("Mark the upper panel's bottom edge between 34% and 66% of the source height.")
    start, end = float(payload["start"]), float(payload["end"])
    clips = [row for row in source_track_clips(project, "A") if row["start"] < end and row["end"] > start]
    if not _covers(clips, start, end) or any(float(row.get("video_speed", 1)) != 1 or str(row.get("source_ref") or "primary:A").split(":")[:2] != ["primary", "A"] for row in clips):
        raise SourceTrackError("Select continuous source A footage at normal speed, without gaps or other assets.")
    cameras = ((project.get("manual") or {}).get("sequence") or {}).get("camera_plan") or []
    if not _covers([row for row in cameras if row.get("camera") == "A"], start, end):
        raise SourceTrackError("Choose source A only for this range before applying the podcast preset.")
    panel_height = math.floor(height * split) if focus == "top" else height - math.ceil(height * split)
    # Stay two source pixels inside the chosen panel, including YUV420/scale
    # rounding at the divider. Subtitles are added after this picture crop.
    zoom = 1. if focus == "both" else height / max(1., panel_height - 2.)
    if zoom > 3:
        raise SourceTrackError("This marked panel is too small for the supported 3× crop. Keep Both or revise the divider.")
    return {"x": .5, "y": .5 if focus == "both" else 0. if focus == "top" else 1., "zoom": round(zoom, 6)}
