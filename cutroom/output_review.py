"""A bounded, local check of every finished export.

It decodes the export's audio once and a small, downscaled sample of its
video, so its cost stays a small fraction of the render. The results are
advice for the person: they never block, change or re-render the export.
"""
from __future__ import annotations

import math
import re
import subprocess
import time
from pathlib import Path
from typing import Any

REVIEW_VERSION = 1
# A caption longer than this wraps to three or more lines on a vertical frame.
LONG_CAPTION_CHARACTERS = 84
# Black longer than this inside an edit is rarely intended.
BLACK_SECONDS = 1.0
# Video sampling rate for the black check, and its time budget.
VIDEO_SAMPLE_FPS = 4
TRUE_PEAK_TOLERANCE_DB = 0.1
LOUDNESS_TOLERANCE_LU = 1.0


def _check(check_id: str, status: str, detail: str, **values: Any) -> dict[str, Any]:
    return {"id": check_id, "status": status, "detail": detail, **values}


def _run(command: list[str], timeout: float) -> str | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout,
                              encoding="utf-8", errors="replace").stderr
    except (OSError, subprocess.TimeoutExpired):
        return None


def _audio_checks(ffmpeg: str, output: Path, ceiling_dbtp: float, target_lufs: float | None, timeout: float) -> list[dict[str, Any]]:
    log = _run([ffmpeg, "-hide_banner", "-nostats", "-i", str(output), "-map", "0:a:0", "-vn",
                "-af", "ebur128=peak=true", "-f", "null", "-"], timeout)
    summary = log[log.rfind("Summary:"):] if log and "Summary:" in log else ""
    loudness = re.search(r"I:\s+(-?[\d.]+) LUFS", summary)
    peak = re.search(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS", summary)
    if not loudness or not peak:
        return [_check("audio_level", "skipped", "The audio could not be measured in time.")]
    integrated, true_peak = float(loudness.group(1)), float(peak.group(1))
    checks = [_check(
        "true_peak", "pass" if true_peak <= ceiling_dbtp + TRUE_PEAK_TOLERANCE_DB else "warn",
        f"True peak {true_peak:.1f} dBTP (ceiling {ceiling_dbtp:.1f})." if true_peak <= ceiling_dbtp + TRUE_PEAK_TOLERANCE_DB
        else f"True peak {true_peak:.1f} dBTP is above the {ceiling_dbtp:.1f} dBTP ceiling; some players may distort.",
        true_peak_dbtp=true_peak)]
    if target_lufs is not None:
        close = abs(integrated - target_lufs) <= LOUDNESS_TOLERANCE_LU
        checks.append(_check(
            "loudness", "pass" if close else "warn",
            f"Loudness {integrated:.1f} LUFS (target {target_lufs:.0f})." if close
            else f"Loudness {integrated:.1f} LUFS is not near the {target_lufs:.0f} LUFS target; Master may be raised or lowered.",
            integrated_lufs=integrated))
    else:
        checks.append(_check("loudness", "info", f"Loudness {integrated:.1f} LUFS (normalization off).", integrated_lufs=integrated))
    return checks


def _black_check(ffmpeg: str, output: Path, duration: float, timeout: float) -> dict[str, Any]:
    # The render has finished, so decoding may use every core (3.5 s instead of
    # 17 s for a 3-minute 1080p export on a 24-thread machine).
    log = _run([ffmpeg, "-hide_banner", "-nostats", "-threads", "0", "-i", str(output), "-an",
                "-vf", f"fps={VIDEO_SAMPLE_FPS},scale=160:-2,blackdetect=d={BLACK_SECONDS}:pix_th=0.08",
                "-f", "null", "-"], timeout)
    if log is None:
        return _check("black_video", "skipped", "The video was too long to sample in the time allowed.")
    stretches = [(float(start), float(end)) for start, end in
                 re.findall(r"black_start:(-?[\d.]+) black_end:(-?[\d.]+)", log)]
    if not stretches:
        return _check("black_video", "pass", "No black stretch of a second or longer.")
    shown = ", ".join(f"{start:.1f}–{end:.1f} s" for start, end in stretches[:4])
    return _check("black_video", "warn", f"Black picture at {shown}. Check for a gap or a missing clip.",
                  ranges=[{"start": start, "end": end} for start, end in stretches[:20]])


def _gap_check(gaps: list[tuple[float, float]]) -> dict[str, Any]:
    """Empty stretches of the timeline itself, known exactly from the edit."""
    long_gaps = [(start, end) for start, end in gaps if end - start >= BLACK_SECONDS]
    if not long_gaps:
        return _check("timeline_gaps", "pass", "No empty gap in the timeline.")
    shown = ", ".join(f"{start:.1f}–{end:.1f} s" for start, end in long_gaps[:4])
    return _check("timeline_gaps", "warn", f"The timeline is empty at {shown}, so the video is black there. Close the gap or add footage.",
                  ranges=[{"start": start, "end": end} for start, end in long_gaps[:20]])


def remaining_picture_gaps(gaps: list[tuple[float, float]], picture_ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Subtract scheduled library picture from otherwise empty source time.

    This is temporal coverage, not proof of opacity or nonblack pixels. The
    independent decoded-black check still inspects the finished composition.
    Audio clips never contribute picture coverage.
    """
    remaining = list(gaps)
    for left, right in picture_ranges:
        if not math.isfinite(left) or not math.isfinite(right) or right <= left:
            continue
        next_gaps = []
        for start, end in remaining:
            if right <= start or left >= end:
                next_gaps.append((start, end))
            else:
                if start < left:
                    next_gaps.append((start, min(end, left)))
                if right < end:
                    next_gaps.append((max(start, right), end))
        remaining = next_gaps
    return remaining


def _area(position: str | None, template: str | None = None) -> str:
    if template == "lower_third":
        return "bottom"
    if template == "callout":
        return "top"
    if template == "chapter":
        return "center"
    return {"top": "top", "center": "center"}.get(str(position or ""), "bottom")


def _overlap_check(caption_lines: list[dict[str, Any]], text_clips: list[dict[str, Any]], caption_position: str) -> dict[str, Any]:
    """Authored text and burned captions that share time and the same part of the frame."""
    shapes = [(float(row["start"]), float(row["end"]), _area(row.get("position") or caption_position), "caption")
              for row in caption_lines]
    shapes += [(float(row["start"]), float(row["end"]), _area(row.get("position"), row.get("template")), "text")
               for row in text_clips]
    clashes: list[float] = []
    shapes.sort()
    for index, (start, end, area, kind) in enumerate(shapes):
        for other_start, other_end, other_area, other_kind in shapes[index + 1:]:
            if other_start >= end:
                break
            if area == other_area and "text" in {kind, other_kind} and min(end, other_end) - other_start > 0.2:
                clashes.append(round(other_start, 1))
    if not clashes:
        return _check("text_overlap", "pass", "Text and captions do not cover each other.")
    times = ", ".join(f"{value:.1f} s" for value in sorted(set(clashes))[:4])
    return _check("text_overlap", "warn", f"Text and captions share the same part of the frame at {times}. Move one of them.",
                  times=sorted(set(clashes))[:20])


def _caption_length_check(caption_lines: list[dict[str, Any]]) -> dict[str, Any]:
    long_lines = [row for row in caption_lines if len(str(row.get("text") or "")) > LONG_CAPTION_CHARACTERS]
    if not long_lines:
        return _check("caption_length", "pass", "Caption lines fit in one or two lines.")
    first = float(long_lines[0]["start"])
    return _check("caption_length", "warn",
                  f"{len(long_lines)} caption line(s) wrap to three or more lines (first at {first:.1f} s). "
                  "Fewer words per caption or a shorter text reads better.", count=len(long_lines))


def review_export(
    ffmpeg: str,
    output: Path,
    *,
    duration: float,
    has_audio: bool,
    ceiling_dbtp: float,
    target_lufs: float | None,
    caption_lines: list[dict[str, Any]],
    text_clips: list[dict[str, Any]],
    caption_position: str = "auto",
    timeline_gaps: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    # Each media pass has its own budget, scaled to the export but bounded.
    budget = max(20.0, min(120.0, duration * 0.25))
    checks: list[dict[str, Any]] = []
    if has_audio:
        checks.extend(_audio_checks(ffmpeg, output, ceiling_dbtp, target_lufs, budget))
    if timeline_gaps is not None:
        checks.append(_gap_check(timeline_gaps))
    checks.append(_black_check(ffmpeg, output, duration, budget))
    checks.append(_overlap_check(caption_lines, text_clips, caption_position))
    if caption_lines:
        checks.append(_caption_length_check(caption_lines))
    return {"version": REVIEW_VERSION, "seconds": round(time.monotonic() - started, 2),
            "warnings": sum(row["status"] == "warn" for row in checks), "checks": checks}
