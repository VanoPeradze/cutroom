from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from .config import Settings
from .transcription import _transcribe_in_process
from .utils import atomic_write_json


def _settings_from_payload(payload: dict[str, Any]) -> Settings:
    return Settings(
        raw=dict(payload["raw"]),
        root=Path(payload["root"]),
        data_dir=Path(payload["data_dir"]),
        projects_dir=Path(payload["projects_dir"]),
        exports_dir=Path(payload["exports_dir"]),
        cache_dir=Path(payload["cache_dir"]),
        ffmpeg=str(payload["ffmpeg"]),
        ffprobe=str(payload["ffprobe"]),
    )


def run(request_path: Path, result_path: Path, progress_path: Path) -> int:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("Transcription worker request must be an object")
        settings_payload = request.get("settings")
        if not isinstance(settings_payload, dict):
            raise ValueError("Transcription worker settings are missing")
        settings = _settings_from_payload(settings_payload)

        def report(value: float, message: str) -> None:
            try:
                atomic_write_json(progress_path, {
                    "progress": max(0.0, min(1.0, float(value))),
                    "message": str(message),
                })
            except OSError:
                # This file is advisory IPC only.  A transient scanner/reader lock
                # must never discard the transcript that Whisper is still building.
                # Later progress reports get another chance, while the final result
                # continues to use a required atomic write below.
                return

        result = _transcribe_in_process(
            Path(str(request["media_path"])),
            settings,
            language=request.get("language"),
            progress=report,
            performance_mode=str(request.get("performance_mode") or "auto"),
            duration=float(request.get("duration") or 0.0),
            cancel_check=None,
        )
        atomic_write_json(result_path, {"ok": True, "result": result})
        return 0
    except BaseException as exc:  # noqa: BLE001 - subprocess boundary
        atomic_write_json(result_path, {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=12),
            **({"coverage": exc.coverage} if isinstance(getattr(exc, "coverage", None), dict) else {}),
        })
        return 1


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) != 3:
        return 2
    return run(Path(values[0]), Path(values[1]), Path(values[2]))


if __name__ == "__main__":
    raise SystemExit(main())
