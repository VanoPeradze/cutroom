"""Whole-program color grade, 3D LUTs and transform keyframes.

Every FFmpeg fragment here is compiled from numbers that were validated and
clamped first, plus a fixed whitelist of looks. Callers never pass filter text.

* ``manual.color``: a look, four sliders and an optional uploaded ``.cube`` LUT.
  It applies to the composed picture (sources, media layers) before captions,
  like a timeline-level grade.
* ``manual.keyframes``: zoom and anchor points on the output clock. The picture
  scales around the anchor exactly like a CSS ``transform-origin`` scale, which
  is how the editor previews it.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

LOOKS = ("none", "warm", "cool", "teal_orange", "vintage", "punchy", "matte", "mono")
SLIDERS = ("exposure", "contrast", "saturation", "temperature")
MAX_KEYFRAMES = 32
MAX_ZOOM = 3.0
MAX_TIME = 604_800.0
LUT_MAX_BYTES = 4_000_000
LUT_MIN_SIZE = 2
LUT_MAX_SIZE = 65
_LUT_ID = re.compile(r"[0-9a-f]{16}")

_LOOK_FILTERS = {
    "warm": "colorbalance=rs=0.05:gs=0.01:bs=-0.06:rm=0.06:bm=-0.06",
    "cool": "colorbalance=rs=-0.04:bs=0.06:rm=-0.05:bm=0.06",
    "teal_orange": "colorbalance=rs=-0.08:gs=0.02:bs=0.10:rh=0.10:gh=0.02:bh=-0.08,eq=saturation=1.1",
    "vintage": "curves=preset=vintage",
    "punchy": "eq=contrast=1.15:saturation=1.3",
    "matte": "curves=all='0/0.08 0.5/0.5 1/0.92'",
    "mono": "hue=s=0",
}


class GradingError(ValueError):
    """The color, LUT or keyframe request is invalid."""


def _number(value: Any, name: str, low: float, high: float, *, strict: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        if strict:
            raise GradingError(f"{name} must be a number.")
        return 0.0 if low <= 0.0 <= high else low
    number = float(value)
    if strict and not low <= number <= high:
        raise GradingError(f"{name} must be between {low:g} and {high:g}.")
    return min(high, max(low, number))


def normalize_color(raw: Any, *, strict: bool = False) -> dict[str, Any]:
    """The saved grade with defaults; ``strict`` rejects instead of clamping."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        if strict:
            raise GradingError("color must be an object.")
        raw = {}
    if strict and set(raw) - {"look", *SLIDERS, "lut_id", "lut_name"}:
        raise GradingError("color contains an unsupported field.")
    look = raw.get("look", "none")
    if look not in LOOKS:
        if strict:
            raise GradingError("color.look is not a supported look.")
        look = "none"
    clean: dict[str, Any] = {"look": look}
    for key in SLIDERS:
        clean[key] = round(_number(raw.get(key, 0.0), f"color.{key}", -1.0, 1.0, strict=strict), 4)
    lut_id = raw.get("lut_id")
    if lut_id is not None and not (isinstance(lut_id, str) and _LUT_ID.fullmatch(lut_id)):
        if strict:
            raise GradingError("color.lut_id is not an uploaded LUT.")
        lut_id = None
    clean["lut_id"] = lut_id
    name = raw.get("lut_name")
    clean["lut_name"] = str(name)[:120] if lut_id and isinstance(name, str) else None
    return clean


def color_is_neutral(color: dict[str, Any]) -> bool:
    return color["look"] == "none" and not color["lut_id"] and all(abs(color[key]) < 1e-4 for key in SLIDERS)


def lut_path(project_dir: Path, color: dict[str, Any]) -> Path | None:
    lut_id = color.get("lut_id")
    if not lut_id or not _LUT_ID.fullmatch(str(lut_id)):
        return None
    path = project_dir / "media" / "luts" / f"{lut_id}.cube"
    return path if path.is_file() else None


def _filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return f"'{value}'"


def color_filter(color: dict[str, Any], lut: Path | None = None) -> str | None:
    """A comma-separated chain, or ``None`` when the grade changes nothing."""
    color = normalize_color(color)
    stages: list[str] = []
    if lut is not None and color["lut_id"]:
        stages.append(f"lut3d=file={_filter_path(lut)}:interp=tetrahedral")
    if color["look"] != "none":
        stages.append(_LOOK_FILTERS[color["look"]])
    exposure, contrast, saturation = color["exposure"], color["contrast"], color["saturation"]
    if abs(exposure) > 1e-4 or abs(contrast) > 1e-4 or abs(saturation) > 1e-4:
        stages.append(
            f"eq=brightness={0.15 * exposure:.4f}:contrast={1.0 + 0.5 * contrast:.4f}"
            f":saturation={1.0 + saturation:.4f}"
        )
    if abs(color["temperature"]) > 1e-4:
        # Lower Kelvin warms the picture in FFmpeg's colortemperature.
        stages.append(f"colortemperature=temperature={6500.0 - 2000.0 * color['temperature']:.1f}")
    return ",".join(stages) or None


def parse_cube(text: Any) -> str:
    """Validate an Adobe/Resolve ``.cube`` 3D LUT and return canonical text."""
    if not isinstance(text, str) or not text.strip():
        raise GradingError("Choose a .cube LUT file.")
    if len(text.encode("utf-8")) > LUT_MAX_BYTES:
        raise GradingError("This LUT is larger than 4 MB. Use a 3D LUT of size 65 or smaller.")
    size = 0
    domain_min, domain_max = [0.0, 0.0, 0.0], [1.0, 1.0, 1.0]
    rows: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        keyword = parts[0].upper()
        if keyword == "TITLE":
            continue
        if keyword == "LUT_1D_SIZE":
            raise GradingError("Only 3D LUTs are supported. This file is a 1D LUT.")
        if keyword == "LUT_3D_SIZE":
            try:
                size = int(parts[1])
            except (IndexError, ValueError) as error:
                raise GradingError("The LUT size line is invalid.") from error
            if not LUT_MIN_SIZE <= size <= LUT_MAX_SIZE:
                raise GradingError("LUT size must be between 2 and 65.")
            continue
        if keyword in {"DOMAIN_MIN", "DOMAIN_MAX"}:
            try:
                values = [float(item) for item in parts[1:4]]
            except ValueError as error:
                raise GradingError("The LUT domain line is invalid.") from error
            if len(values) != 3 or not all(math.isfinite(item) for item in values):
                raise GradingError("The LUT domain line is invalid.")
            if keyword == "DOMAIN_MIN":
                domain_min = values
            else:
                domain_max = values
            continue
        if keyword == "LUT_3D_INPUT_RANGE":
            continue
        try:
            values = [float(item) for item in parts]
        except ValueError as error:
            raise GradingError("The LUT contains an unknown line.") from error
        if len(values) != 3 or not all(math.isfinite(item) and -4.0 <= item <= 4.0 for item in values):
            raise GradingError("Each LUT entry must contain three color values.")
        rows.append(f"{values[0]:.6f} {values[1]:.6f} {values[2]:.6f}")
    if not size:
        raise GradingError("The LUT has no LUT_3D_SIZE line.")
    if len(rows) != size ** 3:
        raise GradingError(f"The LUT should contain {size ** 3} entries but has {len(rows)}.")
    if any(high <= low for low, high in zip(domain_min, domain_max)):
        raise GradingError("The LUT domain is invalid.")
    header = [f"LUT_3D_SIZE {size}"]
    if domain_min != [0.0, 0.0, 0.0] or domain_max != [1.0, 1.0, 1.0]:
        header += ["DOMAIN_MIN " + " ".join(f"{v:.6f}" for v in domain_min),
                   "DOMAIN_MAX " + " ".join(f"{v:.6f}" for v in domain_max)]
    return "\n".join(header + rows) + "\n"


def save_lut(project_dir: Path, text: Any) -> str:
    """Store a validated LUT by content hash and return its id."""
    canonical = parse_cube(text)
    lut_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    directory = project_dir / "media" / "luts"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{lut_id}.cube"
    if not target.is_file():
        temporary = directory / f".{lut_id}.tmp"
        temporary.write_text(canonical, encoding="utf-8", newline="\n")
        temporary.replace(target)
    return lut_id


def normalize_keyframes(raw: Any, *, strict: bool = False) -> list[dict[str, float]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        if strict:
            raise GradingError("keyframes must be an array.")
        return []
    if strict and len(raw) > MAX_KEYFRAMES:
        raise GradingError(f"Use at most {MAX_KEYFRAMES} keyframes.")
    rows: dict[float, dict[str, float]] = {}
    for item in raw:
        if not isinstance(item, dict):
            if strict:
                raise GradingError("Each keyframe must be an object.")
            continue
        if strict and set(item) - {"time", "zoom", "x", "y"}:
            raise GradingError("A keyframe contains an unsupported field.")
        if strict and "time" not in item:
            raise GradingError("Each keyframe needs a time.")
        time = round(_number(item.get("time"), "keyframe.time", 0.0, MAX_TIME, strict=strict), 3)
        zoom = round(_number(item.get("zoom", 1.0), "keyframe.zoom", 1.0, MAX_ZOOM, strict=strict), 4)
        x = round(_number(item.get("x", 0.5), "keyframe.x", 0.0, 1.0, strict=strict), 4)
        y = round(_number(item.get("y", 0.5), "keyframe.y", 0.0, 1.0, strict=strict), 4)
        rows[time] = {"time": time, "zoom": zoom, "x": x, "y": y}
    return [rows[key] for key in sorted(rows)][:MAX_KEYFRAMES]


def _piecewise(points: list[tuple[float, float]], clock: str) -> str:
    """Linear interpolation that holds the first/last value outside the range."""
    if len(points) == 1 or all(abs(value - points[0][1]) < 1e-6 for _, value in points):
        return f"{points[0][1]:.6f}"
    expression = f"{points[-1][1]:.6f}"
    for (t0, v0), (t1, v1) in reversed(list(zip(points, points[1:]))):
        span = max(t1 - t0, 1e-3)
        expression = (f"if(lt({clock},{t1:.3f}),{v0:.6f}+({v1 - v0:.6f})*"
                      f"max(0,{clock}-{t0:.3f})/{span:.3f},{expression})")
    return expression


def keyframe_transform_filter(
    keyframes: Any, width: int, height: int, punch_windows: list[tuple[float, float]] | None = None,
    punch_zoom: float = 1.0,
) -> str | None:
    """Scale-and-crop on the output clock; geometry and duration are preserved.

    The anchor stays fixed on screen while zooming (visible left edge is
    ``(scaled_w - w) * x``), matching ``transform-origin: x y; scale(z)``.
    """
    rows = normalize_keyframes(keyframes)
    if not rows or width <= 0 or height <= 0:
        return None
    if all(row["zoom"] <= 1.0001 for row in rows) and not punch_windows:
        return None
    zoom = _piecewise([(row["time"], row["zoom"]) for row in rows], "t")
    if punch_windows:
        gate = "+".join(f"between(t,{start:.3f},{end:.3f})" for start, end in punch_windows)
        zoom = f"({zoom})*if({gate},{punch_zoom:.3f},1)"
    x = _piecewise([(row["time"], row["x"]) for row in rows], "t")
    y = _piecewise([(row["time"], row["y"]) for row in rows], "t")
    return (f"scale=w='2*trunc({width}*({zoom})/2)':h='2*trunc({height}*({zoom})/2)':eval=frame:flags=bicubic,"
            f"crop={width}:{height}:x='(iw-ow)*({x})':y='(ih-oh)*({y})',setsar=1")
