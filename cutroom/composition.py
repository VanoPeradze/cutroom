"""Safe composition helpers for user-controlled embedded facecam layouts.

The vision detector can only *suggest* that a single video contains an embedded
creator camera.  This module turns either that suggestion or an explicit user
rectangle into a small, trusted data structure.  It deliberately does not make
the editorial decision to enable ``embedded_stack``; every returned candidate
still requires a separate confirmation from the user.
"""

from __future__ import annotations

import math
import copy
import re
from numbers import Real
from pathlib import PurePosixPath
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

CHROMA_KEY_DEFAULTS = {
    "enabled": False,
    "color": "#00FF00",
    "tolerance": 0.12,
    "edge_softness": 0.08,
    "background_color": "#000000",
    "background_asset_id": None,
    "background_mode": "replace",
}
CHROMA_KEY_OPTIONAL_FIELDS = frozenset({"background_asset_id", "background_mode"})
CHROMA_KEY_ACTION_FIELDS = {
    "set_chroma_key": frozenset({"slot", *CHROMA_KEY_DEFAULTS}),
    "reset_chroma_key": frozenset({"slot"}),
}


def normalize_chroma_key(value: Any = None, *, strict: bool = False) -> dict[str, Any]:
    """Validate solid/image keying controls; old/corrupt data stays off."""
    defaults = dict(CHROMA_KEY_DEFAULTS)
    if value is None:
        return defaults
    try:
        if not isinstance(value, Mapping):
            raise ValueError("Chroma Key settings must be an object.")
        if strict and set(value) - defaults.keys():
            raise ValueError("Unknown Chroma Key setting.")
        result = {**defaults, **{key: value[key] for key in defaults if key in value}}
        if not isinstance(result["enabled"], bool):
            raise ValueError("enabled must be a boolean.")
        if result["background_mode"] not in ("replace", "transparent"):
            raise ValueError("background_mode must be replace or transparent.")
        image_id = result["background_asset_id"]
        if image_id is not None and (not isinstance(image_id, str) or not re.fullmatch(r"asset_[0-9a-f]{32}", image_id)):
            raise ValueError("background_asset_id must identify a project image or be null.")
        for key in ("color", "background_color"):
            color = result[key]
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError(f"{key} must be a six-digit #RRGGBB color.")
            result[key] = color.upper()
        for key, minimum in (("tolerance", 0.01), ("edge_softness", 0.0)):
            number = _finite_number(result[key])
            if number is None or not minimum <= number <= 1.0:
                raise ValueError(f"{key} must be a number between {minimum:g} and 1.")
            result[key] = round(number, 6)
        return result
    except ValueError:
        if strict:
            raise
        return defaults


def chroma_source(project: Mapping[str, Any], target: str) -> dict[str, Any] | None:
    """Resolve A/B or one ready project-local video by stable asset ID.

    Filenames and timeline clip IDs never identify settings: two imports with
    the same name remain separate targets, and every use of one asset shares
    its own source preprocessing. This helper never opens arbitrary media.
    """
    if not isinstance(target, str):
        return None
    if target in {"A", "B"}:
        source = (project.get("sources") or {}).get(target)
    elif re.fullmatch(r"asset_[0-9a-f]{32}", target):
        assets = project.get("assets") or {}
        source = assets.get(target) if isinstance(assets, Mapping) else None
        if (not isinstance(source, Mapping) or source.get("id") != target
                or source.get("kind") != "video" or source.get("status") != "ready"):
            return None
        relative = source.get("path")
        if not isinstance(relative, str) or not relative:
            return None
        path = PurePosixPath(relative.replace("\\", "/"))
        if (path.is_absolute() or ".." in path.parts or len(path.parts) < 4
                or path.parts[:3] != ("media", "assets", target)):
            return None
        source = {**source, "relative_path": relative}
    else:
        return None
    if not isinstance(source, Mapping) or not all(
        (_finite_number(source.get(key)) or 0) > 0 for key in ("duration", "width", "height")
    ):
        return None
    if max(source["width"], source["height"]) > 16384 or source["width"] * source["height"] > 64_000_000:
        return None
    return copy.deepcopy(dict(source))


def chroma_video_source(project: Mapping[str, Any], slot: str) -> bool:
    """Require real video metadata rather than a missing/audio/image target."""
    return chroma_source(project, slot) is not None


def chroma_video_targets(project: Mapping[str, Any], *, used_only: bool = False) -> tuple[str, ...]:
    """Stable inventory; unused library keys do not require export capability."""
    assets = project.get("assets") or {}
    used = {row.get("asset_id") for row in ((project.get("manual") or {}).get("media_clips") or [])
            if isinstance(row, Mapping)} if used_only else None
    return tuple(target for target in ("A", "B", *(assets if isinstance(assets, Mapping) else ()))
                 if (target in {"A", "B"} or used is None or target in used)
                 and chroma_video_source(project, target))


def source_chroma_key(project: Mapping[str, Any], slot: str) -> dict[str, Any]:
    if not chroma_video_source(project, slot):
        return dict(CHROMA_KEY_DEFAULTS)
    manual = project.get("manual") or {}
    values = manual.get("chroma_key") if isinstance(manual, Mapping) else None
    return normalize_chroma_key(values.get(slot) if isinstance(values, Mapping) else None)


def chroma_background_asset(project: Mapping[str, Any], slot: str) -> dict[str, Any] | None:
    """Resolve a ready project image; never silently replace a missing choice."""
    config = source_chroma_key(project, slot)
    asset_id = config["background_asset_id"]
    if not config["enabled"] or config["background_mode"] == "transparent" or asset_id is None:
        return None
    assets = project.get("assets") or {}
    asset = assets.get(asset_id) if isinstance(assets, Mapping) else None
    message = "The chosen Chroma Key background image is unavailable. Choose another ready project image or reset Chroma Key."
    if (not isinstance(asset, Mapping) or asset.get("id") != asset_id
            or asset.get("kind") != "image" or asset.get("status") != "ready"):
        raise ValueError(message)
    width, height = (_finite_number(asset.get(key)) for key in ("width", "height"))
    if (width is None or height is None or min(width, height) <= 0
            or max(width, height) > 16384 or width * height > 64_000_000):
        raise ValueError(message)
    relative = asset.get("path")
    if not isinstance(relative, str) or not relative:
        raise ValueError(message)
    path = PurePosixPath(relative.replace("\\", "/"))
    if (path.is_absolute() or ".." in path.parts or len(path.parts) < 4
            or path.parts[:3] != ("media", "assets", asset_id)):
        raise ValueError(message)
    return copy.deepcopy(dict(asset))


def prepare_chroma_key_edit(project: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Stage one independent source's settings before consuming edit history."""
    action = payload.get("action")
    fields = CHROMA_KEY_ACTION_FIELDS.get(action)
    if fields is None:
        raise ValueError("Unknown Chroma Key action.")
    optional = CHROMA_KEY_OPTIONAL_FIELDS if action == "set_chroma_key" else frozenset()
    if set(payload) - fields - {"action"} or fields - optional - payload.keys():
        raise ValueError("Supply only the required Chroma Key fields.")
    slot = payload.get("slot")
    if not isinstance(slot, str) or not chroma_video_source(project, slot):
        raise ValueError("Choose an existing source or ready project video for Chroma Key.")
    config = normalize_chroma_key({key: payload[key] for key in CHROMA_KEY_DEFAULTS if key in payload}, strict=True) if action == "set_chroma_key" else dict(CHROMA_KEY_DEFAULTS)
    if config["enabled"] and config["background_mode"] == "transparent" and slot in ("A", "B"):
        raise ValueError("To reveal the video underneath, add this foreground video in Media and place it on the timeline. Main A/B sources use a color or image background.")
    manual = project.get("manual") or {}
    values = manual.get("chroma_key") if isinstance(manual, Mapping) else None
    existing = values.get(slot) if isinstance(values, Mapping) else None
    staged = copy.deepcopy(dict(values)) if isinstance(values, Mapping) else {}
    staged[slot] = config
    chroma_background_asset({**project, "manual": {**manual, "chroma_key": staged}}, slot)
    previous = normalize_chroma_key(existing) if isinstance(existing, Mapping) else existing
    if previous == config or existing is None and config == CHROMA_KEY_DEFAULTS:
        return None
    return staged


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
    "CHROMA_KEY_DEFAULTS",
    "CHROMA_KEY_ACTION_FIELDS",
    "CHROMA_KEY_OPTIONAL_FIELDS",
    "normalize_chroma_key",
    "chroma_source",
    "chroma_video_source",
    "chroma_video_targets",
    "source_chroma_key",
    "chroma_background_asset",
    "prepare_chroma_key_edit",
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
