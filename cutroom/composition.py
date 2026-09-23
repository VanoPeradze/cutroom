"""Safe composition helpers for user-controlled embedded facecam layouts.

The vision detector can only *suggest* that a single video contains an embedded
creator camera.  This module turns either that suggestion or an explicit user
rectangle into a small, trusted data structure.  It deliberately does not make
the editorial decision to enable ``embedded_stack``; every returned candidate
still requires a separate confirmation from the user.
"""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Mapping


FACE_LAYOUT_VERSION = "face-layout-v3"
MANUAL_CANDIDATE_VERSION = "manual-facecam-v1"

# A useful embedded camera must be large enough to survive a vertical render,
# but it may legitimately occupy half of a source (for example, a side-by-side
# screen recording).  Area is therefore a better upper bound than either width
# or height by itself.
MIN_FACE_CAM_DIMENSION = 0.06
MIN_FACE_CAM_AREA = 0.006
MAX_FACE_CAM_AREA = 0.60
_BOUNDARY_EPSILON = 1e-6


def default_reels_stack(project: Mapping[str, Any]) -> bool:
    """Use a two-source Reels stack only before an explicit layout is chosen."""
    settings = project.get("settings") or {}
    mixer = (project.get("manual") or {}).get("source_mixer") or {}
    return bool(
        (project.get("sources") or {}).get("B")
        and str(settings.get("goal") or "short") == "short"
        and str(settings.get("aspect") or "9:16") == "9:16"
        and str(settings.get("layout") or "auto") == "auto"
        and "default_layout" not in mixer
    )


def _finite_number(value: Any) -> float | None:
    """Return a JSON-style finite number, rejecting booleans and strings."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    numeric = float(value)
    return numeric if math.isfinite(numeric) else None


def _rounded(value: float) -> float:
    # Six decimal places are precise enough for source crops while keeping saved
    # project JSON stable across repeated normalization.
    return round(float(value), 6)


def normalize_facecam_rectangle(rectangle: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Validate and normalize an ``x/y/w/h`` rectangle in source-relative units.

    Coordinates are normalized to ``0..1``.  A microscopic floating-point drift
    at a frame edge is clamped, but genuinely out-of-bounds, non-finite, tiny or
    near-full-frame rectangles are rejected by returning ``None``.  The input is
    never mutated and untrusted extra keys are discarded.
    """
    if not isinstance(rectangle, Mapping):
        return None

    values = {key: _finite_number(rectangle.get(key)) for key in ("x", "y", "w", "h")}
    if any(value is None for value in values.values()):
        return None
    x, y, width, height = (float(values[key]) for key in ("x", "y", "w", "h"))

    if width < MIN_FACE_CAM_DIMENSION or height < MIN_FACE_CAM_DIMENSION:
        return None
    area = width * height
    if area < MIN_FACE_CAM_AREA or area > MAX_FACE_CAM_AREA:
        return None

    if x < -_BOUNDARY_EPSILON or y < -_BOUNDARY_EPSILON:
        return None
    if x > 1.0 + _BOUNDARY_EPSILON or y > 1.0 + _BOUNDARY_EPSILON:
        return None
    if x + width > 1.0 + _BOUNDARY_EPSILON or y + height > 1.0 + _BOUNDARY_EPSILON:
        return None

    # Permit only insignificant serialization/rounding drift at the edges.
    x = max(0.0, min(1.0, x))
    y = max(0.0, min(1.0, y))
    width = min(width, 1.0 - x)
    height = min(height, 1.0 - y)
    return {"x": _rounded(x), "y": _rounded(y), "w": _rounded(width), "h": _rounded(height)}


def normalize_content_focus(focus: Mapping[str, Any] | None) -> dict[str, float]:
    """Return a safe content focus point, clamped to the normalized frame.

    Unlike a crop rectangle, a focus point cannot expose pixels outside the
    source: clamping it is safe and gives sliders a forgiving edge.  Missing,
    malformed or non-finite axes independently fall back to the frame centre.
    """
    if not isinstance(focus, Mapping):
        return {"x": 0.5, "y": 0.5}
    x = _finite_number(focus.get("x"))
    y = _finite_number(focus.get("y"))
    return {
        "x": _rounded(max(0.0, min(1.0, x if x is not None else 0.5))),
        "y": _rounded(max(0.0, min(1.0, y if y is not None else 0.5))),
    }


def embedded_content_rectangle(rectangle: Mapping[str, Any] | None) -> dict[str, float] | None:
    """Choose a clear source region that cannot repeat the marked camera below.

    A focus point on the complete recording is not sufficient: a wide camera
    band or a side-by-side recording can still appear in the gameplay panel.
    Choose the largest complete strip outside the camera. Equal-area strips
    prefer the requested content focus, then the stable left/right/top/bottom
    order. The focus controls subsequently pan *inside* this clear region.

    Never trust a stored ``content_region``; it is derived again from validated
    camera geometry so older projects and untrusted payloads behave identically.
    """
    camera = normalize_facecam_rectangle(rectangle)
    if camera is None:
        return None
    x, y, width, height = (camera[key] for key in ("x", "y", "w", "h"))
    regions = [
        {"x": 0.0, "y": 0.0, "w": x, "h": 1.0},
        {"x": x + width, "y": 0.0, "w": 1.0 - x - width, "h": 1.0},
        {"x": 0.0, "y": 0.0, "w": 1.0, "h": y},
        {"x": 0.0, "y": y + height, "w": 1.0, "h": 1.0 - y - height},
    ]
    regions = [region for region in regions if min(region["w"], region["h"]) >= MIN_FACE_CAM_DIMENSION]
    if not regions:
        return None
    focus = normalize_content_focus(rectangle.get("content_focus"))
    region = max(regions, key=lambda item: (
        _rounded(item["w"] * item["h"]),
        -((item["x"] + item["w"] / 2 - focus["x"]) ** 2
          + (item["y"] + item["h"] / 2 - focus["y"]) ** 2),
    ))
    return {key: _rounded(value) for key, value in region.items()}


def build_manual_embedded_candidate(
    rectangle: Mapping[str, Any] | None,
    content_focus: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build a trusted candidate from a rectangle explicitly drawn by the user.

    The result is intentionally *not* enabled or confirmed.  Calling code must
    persist a separate user confirmation before changing the camera plan.
    """
    normalized = normalize_facecam_rectangle(rectangle)
    if normalized is None:
        return None
    requested_focus = content_focus
    if requested_focus is None and isinstance(rectangle, Mapping):
        embedded_focus = rectangle.get("content_focus")
        requested_focus = embedded_focus if isinstance(embedded_focus, Mapping) else None
    focus = normalize_content_focus(requested_focus)
    return {
        **normalized,
        "content_focus": focus,
        "content_region": embedded_content_rectangle({**normalized, "content_focus": focus}),
        "candidate_source": "manual",
        "manual": True,
        "method": "manual_rectangle",
        "detector": MANUAL_CANDIDATE_VERSION,
        "layout_hint": "embedded_stack",
        "requires_confirmation": True,
        "confirmed": False,
        "auto_safe": False,
        "auto_enable": False,
        "enabled": False,
    }


def normalize_vision_embedded_candidate(
    vision: Mapping[str, Any] | None,
    *,
    analysis_version: str | None = None,
) -> dict[str, Any] | None:
    """Validate a candidate produced specifically by the current face-layout detector.

    ``vision`` may be the complete analysis object (with ``embedded_camera``) or
    the embedded candidate itself.  Suggestions from legacy/unknown detectors
    are rejected so they cannot silently opt a project into the new layout path.
    """
    if not isinstance(vision, Mapping):
        return None

    if "embedded_camera" in vision:
        raw = vision.get("embedded_camera")
        envelope_version = vision.get("version")
    else:
        raw = vision
        envelope_version = None
    if not isinstance(raw, Mapping):
        return None

    provenance = analysis_version or envelope_version or raw.get("detector") or raw.get("version")
    if provenance != FACE_LAYOUT_VERSION:
        return None
    normalized = normalize_facecam_rectangle(raw)
    if normalized is None:
        return None

    confidence = _finite_number(raw.get("confidence"))
    safe_confidence = max(0.0, min(0.99, confidence if confidence is not None else 0.0))
    focus = normalize_content_focus(raw.get("content_focus"))
    return {
        **normalized,
        "content_focus": focus,
        "content_region": embedded_content_rectangle({**normalized, "content_focus": focus}),
        "confidence": round(safe_confidence, 3),
        "candidate_source": "vision",
        "manual": False,
        "method": str(raw.get("method") or "temporal_face_cluster")[:80],
        "detector": FACE_LAYOUT_VERSION,
        "layout_hint": "embedded_stack",
        "requires_confirmation": True,
        "confirmed": False,
        "auto_safe": False,
        "auto_enable": False,
        "enabled": False,
    }


def select_embedded_candidate(
    manual_candidate: Mapping[str, Any] | None,
    vision_candidate: Mapping[str, Any] | None,
    *,
    vision_version: str | None = None,
) -> dict[str, Any] | None:
    """Choose the effective suggestion, preferring a valid manual rectangle.

    Invalid manual input is ignored rather than blocking a valid detector
    suggestion.  Returning a candidate does not activate it: both sources are
    normalized with ``requires_confirmation=True`` and ``enabled=False``.
    """
    manual = build_manual_embedded_candidate(manual_candidate)
    if manual is not None:
        return manual
    return normalize_vision_embedded_candidate(vision_candidate, analysis_version=vision_version)


__all__ = [
    "FACE_LAYOUT_VERSION",
    "MANUAL_CANDIDATE_VERSION",
    "MIN_FACE_CAM_DIMENSION",
    "MIN_FACE_CAM_AREA",
    "MAX_FACE_CAM_AREA",
    "normalize_facecam_rectangle",
    "normalize_content_focus",
    "embedded_content_rectangle",
    "build_manual_embedded_candidate",
    "normalize_vision_embedded_candidate",
    "select_embedded_candidate",
]
