"""The shared, explicit constant-frame-rate export contract."""

from __future__ import annotations

from typing import Any


DEFAULT_EXPORT_FPS = 30
EXPORT_FPS_CHOICES = frozenset({24, 25, 30, 50, 60})


def validate_export_fps(value: Any) -> int:
    """Reject ambiguous, fractional or unbounded frame rates before encoding."""

    if isinstance(value, bool) or not isinstance(value, int) or value not in EXPORT_FPS_CHOICES:
        raise ValueError("fps must be an integer: 24, 25, 30, 50 or 60.")
    return value


def project_export_fps(project: dict[str, Any]) -> int:
    return validate_export_fps((project.get("settings") or {}).get("fps", DEFAULT_EXPORT_FPS))


def with_export_options(project: dict[str, Any], options: dict[str, Any] | None) -> dict[str, Any]:
    """Apply export-only frame rate and resolution without changing the project."""

    if options is None or not ({"fps", "resolution"} & options.keys()):
        return project
    overrides = {}
    if "fps" in options:
        overrides["fps"] = validate_export_fps(options["fps"])
    if "resolution" in options:
        overrides["resolution"] = validate_export_resolution(options["resolution"])
    return {
        **project,
        "settings": {**(project.get("settings") or {}), **overrides},
    }


def validate_export_resolution(value: Any) -> str:
    if not isinstance(value, str) or value not in {"720", "1080", "1440", "2160"}:
        raise ValueError("resolution must be 720, 1080, 1440 or 2160.")
    return value
