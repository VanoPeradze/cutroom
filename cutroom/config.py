from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULTS: dict[str, Any] = {
    "host": "127.0.0.1",
    "port": 8765,
    "open_browser": True,
    "data_dir": "data",
    "max_upload_gb": 40,
    "job_workers": 1,
    "background_workers": 1,
    "max_pending_jobs": 8,
    "job_retention_seconds": 86400,
    "ffmpeg_threads": 4,
    "proxy_height": 720,
    "proxy_crf": 27,
    "preview_width": 1280,
    "audio_analysis_sample_rate": 8000,
    "audio_analysis_window_seconds": 0.20,
    "scene_analysis_fps": 1.5,
    "vision_samples": {"lite": 12, "balanced": 20, "quality": 32},
    "ai": {
        "enabled": True,
        "ollama_url": "http://127.0.0.1:11434",
        "auto_start_ollama": True,
        "editor_model": "qwen3.5:4b",
        "editor_quality_model": "qwen3.5:9b",
        "editor_lite_model": "qwen3.5:2b",
        "editor_fallback_models": ["qwen3.5:9b", "qwen3:8b"],
        "whisper_model": "base",
        "whisper_models": {"lite": "base", "balanced": "small", "quality": "turbo"},
        "hebrew_whisper_model": "ivrit-ai/whisper-large-v3-turbo-ct2",
        "hebrew_auto_gpu_max_seconds": 3600,
        "performance_mode": "auto",
        "whisper_device": "auto",
        "whisper_compute_type": "auto",
        "whisper_isolate_process": True,
        "whisper_worker_stall_seconds": 120,
        "whisper_worker_model_load_timeout_seconds": 900,
        "whisper_cpu_lite_threshold_seconds": 600,
        "whisper_cuda_min_free_mb": {"lite": 2048, "balanced": 4096, "quality": 6144},
        "download_models_on_setup": False,
        "max_llm_segments": 180,
        "max_story_beats": 72,
    },
    "render": {
        "default_quality": "balanced",
        "prefer_hardware": True,
        "default_resolution": "1080",
        "audio_bitrate": "192k",
    },
}


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _validated_port(value: Any, *, source: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{source} must be an integer between 1 and 65535")
    if isinstance(value, int):
        port = value
    elif isinstance(value, str) and value.strip().isdigit():
        port = int(value.strip())
    else:
        raise ValueError(f"{source} must be an integer between 1 and 65535")
    if not 1 <= port <= 65_535:
        raise ValueError(f"{source} must be between 1 and 65535")
    return port


@dataclass(frozen=True)
class Settings:
    raw: dict[str, Any]
    root: Path
    data_dir: Path
    projects_dir: Path
    exports_dir: Path
    cache_dir: Path
    ffmpeg: str
    ffprobe: str

    @property
    def ai(self) -> dict[str, Any]:
        return self.raw["ai"]

    @property
    def render(self) -> dict[str, Any]:
        return self.raw["render"]


def load_settings(config_path: Path | None = None) -> Settings:
    path = config_path or ROOT / "config.json"
    user: dict[str, Any] = {}
    if path.exists():
        user = json.loads(path.read_text(encoding="utf-8"))
    raw = _deep_merge(DEFAULTS, user)
    environment_port = os.environ.get("CUTROOM_PORT")
    raw["port"] = _validated_port(
        environment_port if environment_port is not None else raw.get("port"),
        source="CUTROOM_PORT" if environment_port is not None else "port",
    )
    data_dir = Path(os.environ.get("CUTROOM_DATA_DIR", raw["data_dir"]))
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir
    projects = data_dir / "projects"
    exports = data_dir / "exports"
    cache = data_dir / "cache"
    for directory in (data_dir, projects, exports, cache):
        directory.mkdir(parents=True, exist_ok=True)
    ffmpeg = os.environ.get("CUTROOM_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = os.environ.get("CUTROOM_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
    return Settings(raw, ROOT, data_dir, projects, exports, cache, ffmpeg, ffprobe)
