"""Shared, source-grounded duration accounting for semantic story selections."""
from __future__ import annotations

import copy
import math
from typing import Any

from .utils import merge_ranges, normalize_text, range_duration


POLICY_VERSION = "source-speech-pauses-2026-10-16-v1"
BUDGET_TOLERANCE_SECONDS = .05
SPEECH_HANDLE_SECONDS = .06
MINIMUM_REMOVABLE_PAUSE_SECONDS = .12


class StoryPlanningError(RuntimeError):
    """The Story AI answered, but a safe coherent plan could not be produced."""

    def __init__(self, message: str, diagnostic: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostic = copy.deepcopy(diagnostic or {})


class StoryBudgetError(StoryPlanningError):
    """No complete required story was validated within the requested budget."""

    def __init__(self, message: str, diagnostic: dict[str, Any] | None = None):
        super().__init__(message)
        self.diagnostic = copy.deepcopy(diagnostic or {})


def _finite(value: Any, fallback: float = math.nan) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return fallback
    return result if math.isfinite(result) else fallback


def segment_speech_ranges(segment: dict[str, Any]) -> list[dict[str, float]]:
    """An incomplete word list protects its entire source segment."""
    start, end = float(segment["start"]), float(segment["end"])
    fallback = [{"start": start, "end": end}]
    words = segment.get("words")
    if segment.get("word_timing_complete") is False or not isinstance(words, list) or not words:
        return fallback
    text = normalize_text(str(segment.get("text") or ""))
    labels = normalize_text(" ".join(str(word.get("word") or "")
                                     for word in words if isinstance(word, dict)))
    if text and text != labels:
        return fallback
    speech = []
    previous_end = start
    for word in words:
        if not isinstance(word, dict) or not str(word.get("word") or "").strip():
            return fallback
        left, right = _finite(word.get("start")), _finite(word.get("end"))
        if (not math.isfinite(left) or not math.isfinite(right) or right <= left
                or left < start - .001 or right > end + .001 or left < previous_end - .001):
            return fallback
        speech.append({"start": max(start, left), "end": min(end, right)})
        previous_end = right
    return merge_ranges(speech, gap=0.0)


def _pause_layout(
    ranges: list[dict[str, float]], segments: list[dict[str, Any]], duration: float,
    *, protect_action_span: bool,
) -> tuple[list[dict[str, float]], list[dict[str, float]], list[dict[str, float]]]:
    if not math.isfinite(duration) or duration < 0:
        raise ValueError("Story duration must be finite and nonnegative.")
    for row in ranges:
        left, right = _finite(row.get("start")), _finite(row.get("end"))
        if not math.isfinite(left) or not math.isfinite(right) or left < 0 or right < left or right > duration + .001:
            raise ValueError("Story ranges must remain within the source duration.")
    approved = merge_ranges(ranges, gap=0.0)
    protected, gaps = [], []
    for passage in approved:
        overlapping = [row for row in segments
                       if float(row["start"]) < passage["end"] and float(row["end"]) > passage["start"]]
        spans = merge_ranges([
            {"start": max(passage["start"], span["start"]),
             "end": min(passage["end"], span["end"])}
            for row in overlapping for span in segment_speech_ranges(row)
            if span["start"] < passage["end"] and span["end"] > passage["start"]
        ], gap=0.0) if overlapping else [dict(passage)]
        protected.extend(spans)
        if protect_action_span:
            continue
        # Only internal word-free gaps are eligible. Passage endpoints and all
        # unknown speech remain fixed; a transcript gap never authorizes footage.
        for left, right in zip(spans, spans[1:]):
            start = left["end"] + SPEECH_HANDLE_SECONDS
            end = right["start"] - SPEECH_HANDLE_SECONDS
            if end - start >= MINIMUM_REMOVABLE_PAUSE_SECONDS:
                gaps.append({"start": start, "end": end})
    return approved, merge_ranges(protected, gap=0.0), gaps


def story_duration_cost(
    ranges: list[dict[str, float]], segments: list[dict[str, Any]], duration: float,
    *, target: float | None = None, protect_action_span: bool = False, fps: float | None = None,
) -> dict[str, Any]:
    """Price this exact required selection using the fitter's own pause policy.

    The minimum is a constraint of these source ranges, timing evidence and
    policy. It is never a maximum or a claim about other stories in the source.
    """
    approved, protected, gaps = _pause_layout(
        ranges, segments, duration, protect_action_span=protect_action_span,
    )
    seconds = range_duration(approved)
    minimum_ranges = _subtract_pauses(approved, gaps)
    minimum = range_duration(minimum_ranges)
    removable = max(0.0, seconds - minimum)
    if target is not None and (not math.isfinite(float(target)) or float(target) < 0):
        raise ValueError("Story target must be finite and nonnegative.")
    minimum_framed = None
    frame_grid_encodable = True
    if fps is not None:
        try:
            minimum_framed = framed_story_duration(minimum_ranges, fps)
        except ValueError:
            frame_grid_encodable = False
    fits = minimum <= float(target) + BUDGET_TOLERANCE_SECONDS + 1e-9 if target is not None else None
    if fps is not None and target is not None:
        fits = bool(fits and frame_grid_encodable and minimum_framed <= float(target) + BUDGET_TOLERANCE_SECONDS + 1e-9)
    return {
        "policy_version": POLICY_VERSION, "scope": "current_required_selection",
        "approved_seconds": round(seconds, 3),
        "protected_speech_seconds": round(range_duration(protected), 3),
        "minimum_safe_seconds": round(minimum, 3),
        "removable_pause_seconds": round(removable, 3),
        "target_seconds": float(target) if target is not None else None,
        "fits_target": fits,
        "pause_count": len(gaps), "protect_action_span": protect_action_span,
        "fps": fps, "minimum_framed_seconds": minimum_framed,
        "frame_grid_encodable": frame_grid_encodable,
    }


def _subtract_pauses(approved: list[dict[str, float]], cuts: list[dict[str, float]]) -> list[dict[str, float]]:
    """Subtract exactly; generic inversion intentionally drops tiny editor clips."""
    pauses = merge_ranges(cuts, gap=0.0)
    result = []
    for passage in approved:
        cursor = passage["start"]
        for cut in pauses:
            if cut["end"] <= cursor or cut["start"] >= passage["end"]:
                continue
            if cut["start"] > cursor:
                result.append({"start": cursor, "end": min(cut["start"], passage["end"])})
            cursor = max(cursor, min(cut["end"], passage["end"]))
        if cursor < passage["end"]:
            result.append({"start": cursor, "end": passage["end"]})
    return merge_ranges(result, gap=0.0)


def framed_story_duration(ranges: list[dict[str, float]], fps: float) -> float:
    """Apply the renderer's shared nearest-frame source-boundary contract."""
    if isinstance(fps, bool) or not math.isfinite(float(fps)) or fps <= 0:
        raise ValueError("Story frame rate must be positive and finite.")
    frames = 0
    for row in ranges:
        start = math.floor(float(row["start"]) * fps + .5)
        end = math.floor(float(row["end"]) * fps + .5)
        if end <= start:
            raise ValueError("A required story fragment is shorter than one output frame.")
        frames += end - start
    return round(frames / fps, 6)


def _fit_raw(approved: list[dict[str, float]], gaps: list[dict[str, float]], target: float) -> list[dict[str, float]] | None:
    excess = range_duration(approved) - target
    if excess <= BUDGET_TOLERANCE_SECONDS:
        return approved
    minimum_ranges = _subtract_pauses(approved, gaps)
    if range_duration(minimum_ranges) > target + BUDGET_TOLERANCE_SECONDS + 1e-9:
        return None
    pause_cuts = []
    for gap in sorted(gaps, key=lambda row: (-(row["end"] - row["start"]), row["start"])):
        if excess <= .001:
            break
        remove = min(excess, gap["end"] - gap["start"])
        margin = (gap["end"] - gap["start"] - remove) / 2
        pause_cuts.append({"start": round(gap["start"] + margin, 3),
                           "end": round(gap["end"] - margin, 3)})
        excess -= remove
    fitted = _subtract_pauses(approved, pause_cuts)
    if range_duration(fitted) <= target + BUDGET_TOLERANCE_SECONDS + 1e-9:
        return fitted
    # Millisecond quantization can leave a partial removal just over tolerance.
    # The already-priced full safe gaps remain a complete, validated alternative.
    return minimum_ranges


def compact_story_pauses_to_target(
    ranges: list[dict[str, float]], segments: list[dict[str, Any]], duration: float,
    target: float, *, protect_action_span: bool = False, fps: float | None = None,
) -> list[dict[str, float]] | None:
    """Fit only approved words and safe gaps, including frame rounding if known."""
    if not math.isfinite(float(target)) or float(target) < 0:
        raise ValueError("Story target must be finite and nonnegative.")
    approved, _protected, gaps = _pause_layout(
        ranges, segments, duration, protect_action_span=protect_action_span,
    )
    fitted = _fit_raw(approved, gaps, target)
    if fitted is None or fps is None:
        return fitted
    limit = target + BUDGET_TOLERANCE_SECONDS + 1e-9
    try:
        if framed_story_duration(fitted, fps) <= limit:
            return fitted
        minimum_ranges = _subtract_pauses(approved, gaps)
        if framed_story_duration(minimum_ranges, fps) > limit:
            return None
    except ValueError:
        return None
    # More removal uses the same verified internal gaps. A bounded numerical
    # search leaves the longest fit on the output grid; it never repeats media,
    # changes semantic membership or asks a model to retry.
    best = minimum_ranges
    low, high = range_duration(minimum_ranges), min(target, range_duration(approved))
    for _ in range(16):
        middle = (low + high) / 2
        candidate = _fit_raw(approved, gaps, middle)
        try:
            valid = candidate is not None and framed_story_duration(candidate, fps) <= limit
        except ValueError:
            valid = False
        if valid:
            best, low = candidate, middle
        else:
            high = middle
    return best
