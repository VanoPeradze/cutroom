from __future__ import annotations

import importlib
import io
import os
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUIRED_MODULES = ("flask", "waitress", "numpy", "cv2", "faster_whisper", "cutroom")


def _command_ready(command: str) -> bool:
    try:
        result = subprocess.run(
            [command, "-version"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _check_audio_decoder() -> None:
    """Exercise Whisper's actual media reader without loading an ASR model."""
    sample = io.BytesIO()
    with wave.open(sample, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(1600 * 2))
    sample.seek(0)
    audio = importlib.import_module("faster_whisper.audio").decode_audio(sample)
    if len(audio) != 1600:
        raise RuntimeError("The speech decoder returned an unexpected audio length")


def main() -> int:
    failures: list[str] = []
    for name in REQUIRED_MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # Native wheels can exist but still fail to load.
            failures.append(f"Python module {name}: {type(exc).__name__}: {exc}")

    try:
        _check_audio_decoder()
    except Exception as exc:
        failures.append(f"Speech audio decoder: {type(exc).__name__}: {exc}")

    try:
        from cutroom.config import load_settings

        settings = load_settings()
        for label, command in (("FFmpeg", settings.ffmpeg), ("FFprobe", settings.ffprobe)):
            if not _command_ready(command):
                failures.append(f"{label} is unavailable at: {command}")

        probe = settings.cache_dir / f".preflight-{os.getpid()}"
        try:
            probe.write_bytes(b"CUTROOM")
        except OSError as exc:
            failures.append(f"CUTROOM data directory is not writable: {exc}")
        finally:
            probe.unlink(missing_ok=True)
    except Exception as exc:
        failures.append(f"CUTROOM configuration: {type(exc).__name__}: {exc}")

    if failures:
        print("CUTROOM runtime preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("CUTROOM runtime preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
