from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .vision import VISION_ANALYSIS_VERSION


# Changing the semantics of transcript/scenes/vision/story analysis must change
# this value. It is intentionally independent of the product marketing version.
ANALYSIS_CACHE_PIPELINE = "director-analysis-2026-08-30.1"

_SOURCE_METADATA_KEYS = (
    "relative_path",
    "name",
    "size",
    "duration",
    "width",
    "height",
    "rotation",
    "fps",
    "video_codec",
    "audio_codec",
    "has_audio",
)


def stable_fingerprint(namespace: str, value: Any) -> str:
    payload = json.dumps(
        {"namespace": namespace, "value": value},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]


def _sample_file(path: Path, sample_bytes: int = 64 * 1024) -> dict[str, Any]:
    try:
        stat = path.stat()
        digest = hashlib.blake2b(digest_size=16)
        with path.open("rb") as handle:
            digest.update(handle.read(sample_bytes))
            if stat.st_size > sample_bytes:
                handle.seek(max(0, stat.st_size - sample_bytes))
                digest.update(handle.read(sample_bytes))
        return {
            "exists": True,
            "size": int(stat.st_size),
            "mtime_ns": int(stat.st_mtime_ns),
            "sample": digest.hexdigest(),
        }
    except OSError as exc:
        return {"exists": False, "error": type(exc).__name__}


def source_identity(source: Mapping[str, Any] | None, path: Path | None) -> dict[str, Any] | None:
    if not source:
        return None
    return {
        "metadata": {key: source.get(key) for key in _SOURCE_METADATA_KEYS},
        "file": _sample_file(path) if path is not None else None,
    }


def build_analysis_cache_fingerprints(
    project: Mapping[str, Any],
    settings: Any,
    brief: Mapping[str, Any],
    source_paths: Mapping[str, Path | None],
) -> dict[str, str]:
    """Build conservative cache identities with only ~128 KiB I/O per source.

    The brief is included deliberately: reliability is more important than
    reusing an expensive result after the user changed editorial intent.
    """

    sources = project.get("sources", {}) if isinstance(project.get("sources", {}), Mapping) else {}
    identities = {
        slot: source_identity(sources.get(slot), source_paths.get(slot))
        for slot in ("A", "B")
    }
    raw = getattr(settings, "raw", {}) or {}
    ai = getattr(settings, "ai", {}) or {}
    goal = str(brief.get("goal") or "short")
    aspect = str(brief.get("aspect") or "9:16")
    layout = str(brief.get("layout") or "auto")
    auto_reframe = brief.get("auto_reframe", True) is not False
    context_common = {
        "pipeline": ANALYSIS_CACHE_PIPELINE,
        "sources": identities,
        "project_language": project.get("language"),
        "requested_language": brief.get("spoken_language") or project.get("language") or "auto",
        "performance_mode": brief.get("performance_mode") or ai.get("performance_mode", "auto"),
        "ai_connection": {key: (ai.get("cloud_connection") or {}).get(key) for key in ("mode", "provider", "model")},
    }
    scenes_required = bool(identities.get("B")) and goal != "youtube"
    vision_required = bool(
        (
            goal == "short"
            and aspect in {"9:16", "1:1", "4:5"}
            and (auto_reframe or not identities.get("B"))
        )
        or layout == "embedded_stack"
    )
    story_common = {**context_common, "goal": goal, "brief": dict(brief)}
    source_fp = stable_fingerprint("source", {"pipeline": ANALYSIS_CACHE_PIPELINE, "sources": identities})
    return {
        "pipeline": stable_fingerprint("pipeline", ANALYSIS_CACHE_PIPELINE),
        "source": source_fp,
        "transcript": stable_fingerprint(
            "transcript",
            {
                **context_common,
                "models": ai.get("whisper_models"),
                "default_model": ai.get("whisper_model"),
                "hebrew_model": ai.get("hebrew_whisper_model"),
                "device": ai.get("whisper_device"),
                "compute_type": ai.get("whisper_compute_type"),
                "coverage_policy": "processed-chunks-vad-v1",
            },
        ),
        "scenes": stable_fingerprint(
            "scenes",
            {
                "pipeline": ANALYSIS_CACHE_PIPELINE,
                "sources": identities,
                "required": scenes_required,
                "scene_analysis_fps": raw.get("scene_analysis_fps"),
            },
        ),
        "vision": stable_fingerprint(
            "vision",
            {
                "pipeline": ANALYSIS_CACHE_PIPELINE,
                "detector": VISION_ANALYSIS_VERSION,
                "sources": identities,
                "performance_mode": brief.get("performance_mode") or ai.get("performance_mode", "auto"),
                "required": vision_required,
                "vision_samples": raw.get("vision_samples"),
            },
        ),
        "story": stable_fingerprint(
            "story",
            {
                **story_common,
                "editor_models": {
                    "default": ai.get("editor_model"),
                    "quality": ai.get("editor_quality_model"),
                    "lite": ai.get("editor_lite_model"),
                    "fallback": ai.get("editor_fallback_models"),
                },
                "max_story_beats": ai.get("max_story_beats"),
                "story_input_policy": "full-chapter-input-v1",
            },
        ),
    }


def cache_fingerprints_match(cached: Any, expected: Mapping[str, str], keys: tuple[str, ...]) -> bool:
    return bool(
        isinstance(cached, Mapping)
        and all(cached.get(key) == expected.get(key) for key in keys)
    )
