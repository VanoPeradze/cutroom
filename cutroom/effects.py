"""Bounded editorial effects for CUTROOM's final-video timeline.

The public functions in this module accept only structured effect decisions.
They never accept an FFmpeg fragment from a caller: every filter is assembled
from a small internal whitelist with numeric values that have been checked and
clamped first.  The resulting expression is intended to run after the base edit
has been composed and before captions are burned.

This module deliberately has no renderer or UI dependency.  It is an
integration-ready core, not an implicit change to existing exports.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Mapping


PIPELINE_VERSION = "editorial-effects-v1"
HARD_MAX_EFFECTS = 10
AUTOMATIC_MAX_EFFECTS = 5
AUTOMATIC_MIN_SPACING_SECONDS = 4.0


@dataclass(frozen=True)
class _EffectSpec:
    min_seconds: float
    max_seconds: float
    default_strength: float
    min_strength: float
    max_count: int
    order: int


# These filters preserve duration and geometry and are inexpensive compared with
# reframing, optical flow, blur, or per-frame AI work.  New entries must have a
# deterministic builder in _filter_for_effect; callers cannot extend this map.
_EFFECT_SPECS: dict[str, _EffectSpec] = {
    "emphasis": _EffectSpec(0.35, 4.0, 0.55, 0.10, 6, 0),
    "vignette": _EffectSpec(0.50, 8.0, 0.40, 0.10, 2, 1),
    "monochrome": _EffectSpec(0.50, 8.0, 0.85, 0.15, 2, 2),
    "dim": _EffectSpec(0.50, 6.0, 0.35, 0.10, 2, 3),
}

SUPPORTED_EFFECTS = tuple(_EFFECT_SPECS)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _positive_duration(value: Any) -> float | None:
    duration = _finite_number(value)
    return duration if duration is not None and duration > 0.0 else None


def _effect_rows(raw_effects: Any) -> list[Any]:
    if isinstance(raw_effects, Mapping):
        raw_effects = raw_effects.get("effects")
    return list(raw_effects) if isinstance(raw_effects, (list, tuple)) else []


def _bounded_count(value: Any, hard_limit: int) -> int:
    number = _finite_number(value)
    if number is None:
        return hard_limit
    return min(hard_limit, max(0, int(number)))


def normalize_effects(
    raw_effects: Any,
    duration: Any,
    *,
    max_effects: int = HARD_MAX_EFFECTS,
) -> list[dict[str, Any]]:
    """Validate and canonicalize structured effect decisions.

    Unknown types and malformed rows are ignored.  Times are clamped to the
    final-video duration, strengths and per-type counts are bounded, long effects
    are shortened, and later overlaps are trimmed or dropped.  Returned rows
    contain only ``type``, ``start``, ``end`` and ``strength``.
    """

    final_duration = _positive_duration(duration)
    if final_duration is None:
        return []
    limit = _bounded_count(max_effects, HARD_MAX_EFFECTS)
    if limit == 0:
        return []

    candidates: list[dict[str, Any]] = []
    for row in _effect_rows(raw_effects):
        if not isinstance(row, Mapping):
            continue
        effect_type = row.get("type")
        if not isinstance(effect_type, str):
            continue
        effect_type = effect_type.strip().lower()
        spec = _EFFECT_SPECS.get(effect_type)
        if spec is None:
            continue

        start = _finite_number(row.get("start"))
        end = _finite_number(row.get("end"))
        if start is None or end is None:
            continue
        start = min(final_duration, max(0.0, start))
        end = min(final_duration, max(0.0, end))
        if end <= start:
            continue

        strength = _finite_number(row.get("strength"))
        if strength is None:
            strength = spec.default_strength
        if strength <= 0.0:
            continue
        strength = min(1.0, max(spec.min_strength, strength))

        end = min(end, start + spec.max_seconds)
        if end - start < spec.min_seconds:
            continue
        candidates.append(
            {
                "type": effect_type,
                "start": start,
                "end": end,
                "strength": strength,
            }
        )

    # Input ordering must not alter which of two same-time effects wins.  The
    # small internal order is part of the deterministic policy, not user input.
    candidates.sort(
        key=lambda row: (
            float(row["start"]),
            _EFFECT_SPECS[str(row["type"])].order,
            float(row["end"]),
        )
    )

    accepted: list[dict[str, Any]] = []
    counts = {name: 0 for name in _EFFECT_SPECS}
    last_end = 0.0
    for row in candidates:
        if len(accepted) >= limit:
            break
        effect_type = str(row["type"])
        spec = _EFFECT_SPECS[effect_type]
        if counts[effect_type] >= spec.max_count:
            continue

        start = max(float(row["start"]), last_end if accepted else 0.0)
        end = min(float(row["end"]), start + spec.max_seconds)
        if end - start < spec.min_seconds:
            continue

        canonical = {
            "type": effect_type,
            "start": round(start, 3),
            "end": round(end, 3),
            "strength": round(float(row["strength"]), 4),
        }
        accepted.append(canonical)
        counts[effect_type] += 1
        last_end = end

    return accepted


def _time_gate(start: float, end: float) -> str:
    # Numeric formatting is fixed; no caller-controlled text enters the FFmpeg
    # expression. between() is supported by every filter used below.
    return f"enable='between(t,{start:.3f},{end:.3f})'"


def _filter_for_effect(effect: Mapping[str, Any]) -> str:
    effect_type = str(effect["type"])
    start = float(effect["start"])
    end = float(effect["end"])
    strength = float(effect["strength"])
    gate = _time_gate(start, end)

    if effect_type == "emphasis":
        contrast = 1.0 + 0.12 * strength
        brightness = 0.018 * strength
        saturation = 1.0 + 0.28 * strength
        return (
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}:"
            f"saturation={saturation:.4f}:{gate}"
        )
    if effect_type == "vignette":
        # A bounded divisor produces a subtle-to-moderate vignette without any
        # arbitrary expression supplied by the caller.
        divisor = 4.2 + 1.8 * strength
        return f"vignette=angle=PI/{divisor:.4f}:eval=frame:{gate}"
    if effect_type == "monochrome":
        saturation = max(0.0, 1.0 - strength)
        return f"hue=s={saturation:.4f}:{gate}"
    if effect_type == "dim":
        brightness = -0.10 * strength
        saturation = 1.0 - 0.22 * strength
        return f"eq=brightness={brightness:.4f}:saturation={saturation:.4f}:{gate}"
    raise ValueError("Effect type was not normalized")


def build_effect_stages(
    raw_effects: Any,
    duration: Any,
    *,
    max_effects: int = HARD_MAX_EFFECTS,
) -> list[dict[str, Any]]:
    """Return normalized effects with compiler-generated FFmpeg stages."""

    effects = normalize_effects(raw_effects, duration, max_effects=max_effects)
    return [{**effect, "filter": _filter_for_effect(effect)} for effect in effects]


def build_filter_expression(
    raw_effects: Any,
    duration: Any,
    *,
    max_effects: int = HARD_MAX_EFFECTS,
) -> str | None:
    """Compile a safe comma-separated ``-vf`` expression, or ``None``.

    The expression preserves duration and geometry and is suitable for insertion
    before an ASS/subtitles filter.  Audio is intentionally outside this core.
    """

    stages = build_effect_stages(raw_effects, duration, max_effects=max_effects)
    return ",".join(str(stage["filter"]) for stage in stages) or None


def compile_effects(
    raw_effects: Any,
    duration: Any,
    *,
    max_effects: int = HARD_MAX_EFFECTS,
) -> dict[str, Any]:
    """Return a versioned integration payload for a renderer or preview."""

    final_duration = _positive_duration(duration)
    stages = build_effect_stages(raw_effects, duration, max_effects=max_effects)
    return {
        "version": PIPELINE_VERSION,
        "duration": round(final_duration, 3) if final_duration is not None else 0.0,
        "effects": [
            {key: stage[key] for key in ("type", "start", "end", "strength")}
            for stage in stages
        ],
        "stages": stages,
        "filter_expression": ",".join(str(stage["filter"]) for stage in stages) or None,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _clean_keep_ranges(value: Any) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    for row in value if isinstance(value, (list, tuple)) else []:
        if not isinstance(row, Mapping):
            continue
        start = _finite_number(row.get("start"))
        end = _finite_number(row.get("end"))
        if start is None or end is None:
            continue
        start = max(0.0, start)
        if end <= start:
            continue
        ranges.append({"start": start, "end": end})
    ranges.sort(key=lambda row: (row["start"], row["end"]))

    merged: list[dict[str, float]] = []
    for row in ranges:
        if merged and row["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], row["end"])
        else:
            merged.append(dict(row))
    return merged


def _map_source_interval(
    start: float,
    end: float,
    keep_ranges: list[dict[str, float]],
) -> tuple[float, float] | None:
    if end <= start:
        return None
    if not keep_ranges:
        return start, end

    output_offset = 0.0
    pieces: list[tuple[float, float]] = []
    for keep in keep_ranges:
        overlap_start = max(start, keep["start"])
        overlap_end = min(end, keep["end"])
        if overlap_end > overlap_start:
            mapped_start = output_offset + overlap_start - keep["start"]
            mapped_end = output_offset + overlap_end - keep["start"]
            pieces.append((mapped_start, mapped_end))
        output_offset += keep["end"] - keep["start"]
    if not pieces:
        return None
    # One effect must never cross a hard edit. Prefer the longest surviving
    # piece, with the earliest piece as the deterministic tie-breaker.
    return max(pieces, key=lambda piece: (piece[1] - piece[0], -piece[0]))


_ROLE_ALIASES = {
    "hook": ("emphasis", 0.78, "start", 3.2),
    "opening": ("emphasis", 0.70, "start", 3.0),
    "reveal": ("emphasis", 0.68, "end", 2.9),
    "reaction": ("emphasis", 0.68, "end", 2.9),
    "payoff": ("emphasis", 0.66, "end", 2.9),
    "result": ("emphasis", 0.62, "end", 2.8),
    "highlight": ("emphasis", 0.62, "middle", 2.7),
    "conclusion": ("vignette", 0.36, "end", 2.6),
    "ending": ("vignette", 0.36, "end", 2.6),
    "problem": ("dim", 0.28, "middle", 2.0),
    "warning": ("dim", 0.30, "middle", 2.1),
    "serious": ("dim", 0.26, "middle", 1.9),
}


def _role_rule(value: Any) -> tuple[str, float, str, float] | None:
    if not isinstance(value, str):
        return None
    tokens = [token for token in re.split(r"[^a-z]+", value.lower()) if token]
    return next((_ROLE_ALIASES[token] for token in tokens if token in _ROLE_ALIASES), None)


def _effect_window(
    start: float,
    end: float,
    effect_type: str,
    placement: str,
) -> tuple[float, float] | None:
    spec = _EFFECT_SPECS[effect_type]
    available = end - start
    if available < spec.min_seconds:
        return None
    desired = min(spec.max_seconds, 1.6 if effect_type == "emphasis" else 2.4, available)
    if placement == "start":
        window_start = start
    elif placement == "end":
        window_start = end - desired
    else:
        window_start = start + (available - desired) / 2.0
    return window_start, window_start + desired


def _automatic_context(payload: Any) -> tuple[Mapping[str, Any], Mapping[str, Any], list[Any]]:
    root = _mapping(payload)
    draft = _mapping(root.get("draft")) or root
    analysis = _mapping(root.get("analysis"))
    beats = analysis.get("story_beats")
    if not isinstance(beats, (list, tuple)):
        beats = root.get("story_beats")
    if not isinstance(beats, (list, tuple)):
        beats = draft.get("story_beats")
    return draft, analysis, list(beats) if isinstance(beats, (list, tuple)) else []


def plan_automatic_effects(
    payload: Any,
    *,
    max_effects: int = AUTOMATIC_MAX_EFFECTS,
) -> list[dict[str, Any]]:
    """Derive a sparse deterministic plan from a CUTROOM draft/story beats.

    Story-beat timestamps are source-relative.  When ``keep_ranges`` are
    available they are mapped onto the final concatenated timeline and an effect
    never crosses a removed range.  Missing or unfamiliar data simply yields no
    effects.  Long-form ``youtube``/``clean`` drafts remain untouched by default.
    """

    draft, _analysis, beats = _automatic_context(payload)
    if not beats:
        return []
    goal = str(draft.get("goal") or "").strip().lower()
    if goal in {"youtube", "clean"}:
        return []

    keep_ranges = _clean_keep_ranges(draft.get("keep_ranges"))
    duration = _positive_duration(draft.get("output_duration"))
    if duration is None and keep_ranges:
        duration = sum(row["end"] - row["start"] for row in keep_ranges)
    if duration is None:
        duration = max(
            (_finite_number(row.get("end")) or 0.0 for row in beats if isinstance(row, Mapping)),
            default=0.0,
        )
    if duration <= 0.0:
        return []

    highlight_ids = {
        str(value) for value in draft.get("highlight_ids", [])
    } if isinstance(draft.get("highlight_ids"), (list, tuple, set)) else set()

    candidates: list[dict[str, Any]] = []
    for index, beat in enumerate(beats):
        if not isinstance(beat, Mapping):
            continue
        source_start = _finite_number(beat.get("start"))
        source_end = _finite_number(beat.get("end"))
        if source_start is None or source_end is None:
            continue
        mapped = _map_source_interval(source_start, source_end, keep_ranges)
        if mapped is None:
            continue
        mapped_start, mapped_end = mapped

        score = _finite_number(beat.get("editorial_score"))
        score = min(1.25, max(0.0, score if score is not None else 0.0))
        segment_ids = {
            str(value) for value in beat.get("segment_ids", [])
        } if isinstance(beat.get("segment_ids"), (list, tuple, set)) else set()
        highlighted = bool(segment_ids & highlight_ids)

        rule = _role_rule(beat.get("role_hint") or beat.get("role") or beat.get("purpose"))
        if rule is None:
            if not highlighted and score < 0.82:
                continue
            rule = ("emphasis", 0.42 + min(score, 1.0) * 0.18, "middle", 1.2)
        effect_type, strength, placement, role_priority = rule
        window = _effect_window(mapped_start, mapped_end, effect_type, placement)
        if window is None:
            continue
        start, end = window
        candidates.append(
            {
                "type": effect_type,
                "start": start,
                "end": end,
                "strength": min(1.0, strength + (0.08 if highlighted else 0.0)),
                "_priority": role_priority + score + (0.7 if highlighted else 0.0),
                "_index": index,
            }
        )

    auto_limit = _bounded_count(max_effects, AUTOMATIC_MAX_EFFECTS)
    if auto_limit == 0:
        return []
    selected: list[dict[str, Any]] = []
    for candidate in sorted(
        candidates,
        key=lambda row: (-float(row["_priority"]), float(row["start"]), int(row["_index"])),
    ):
        centre = (float(candidate["start"]) + float(candidate["end"])) / 2.0
        if any(
            abs(centre - (float(row["start"]) + float(row["end"])) / 2.0)
            < AUTOMATIC_MIN_SPACING_SECONDS
            for row in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= auto_limit:
            break

    public_rows = [
        {key: row[key] for key in ("type", "start", "end", "strength")}
        for row in selected
    ]
    return normalize_effects(public_rows, duration, max_effects=auto_limit)


def compile_automatic_effects(
    payload: Any,
    *,
    max_effects: int = AUTOMATIC_MAX_EFFECTS,
) -> dict[str, Any]:
    """Plan and compile automatic effects in one integration-friendly call."""

    draft, _analysis, _beats = _automatic_context(payload)
    keep_ranges = _clean_keep_ranges(draft.get("keep_ranges"))
    duration = _positive_duration(draft.get("output_duration"))
    if duration is None and keep_ranges:
        duration = sum(row["end"] - row["start"] for row in keep_ranges)
    duration = duration or 0.0
    auto_limit = _bounded_count(max_effects, AUTOMATIC_MAX_EFFECTS)
    planned = plan_automatic_effects(payload, max_effects=auto_limit)
    return compile_effects(planned, duration, max_effects=auto_limit)
