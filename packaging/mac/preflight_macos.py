"""Mac overlay checks; never installs packages or downloads AI models."""
from __future__ import annotations

import argparse
import importlib
import os
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
REQUIRED_MODULES = ("flask", "waitress", "numpy", "cv2", "faster_whisper", "cutroom")


def _capture(command: str, *arguments: str) -> str:
    result = subprocess.run(
        [command, *arguments], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"exited with code {result.returncode}: {result.stdout[-1200:].strip()}")
    return result.stdout


def _capabilities(output: str) -> set[str]:
    return {fields[1] for line in output.splitlines() if len(fields := line.split()) >= 2}


def check_system() -> list[str]:
    failures: list[str] = []
    ffmpeg = os.environ.get("CUTROOM_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = os.environ.get("CUTROOM_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
    for label, command in (("FFmpeg", ffmpeg), ("FFprobe", ffprobe)):
        try:
            _capture(command, "-version")
            if label == "FFmpeg":
                filters = _capabilities(_capture(command, "-hide_banner", "-filters"))
                encoders = _capabilities(_capture(command, "-hide_banner", "-encoders"))
                if "subtitles" not in filters:
                    failures.append(f"FFmpeg at {command} lacks libass subtitles; install ffmpeg-full.")
                for encoder in ("libx264", "aac"):
                    if encoder not in encoders:
                        failures.append(f"FFmpeg at {command} lacks the {encoder} encoder.")
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            failures.append(f"{label} at {command}: {exc}")
    return failures


def check_python(*, imports: bool = True) -> list[str]:
    failures: list[str] = []
    if not (3, 11) <= sys.version_info[:2] < (3, 13):
        failures.append("Use Python 3.11 or 3.12 for this Mac beta.")
    expected = os.environ.get("CUTROOM_MAC_ARCH")
    if expected and platform.machine() != expected:
        failures.append(f"Python architecture {platform.machine()} does not match this Mac ({expected}).")
    if imports:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        for name in REQUIRED_MODULES:
            try:
                importlib.import_module(name)
            except Exception as exc:
                failures.append(f"Python module {name}: {type(exc).__name__}: {exc}")
    return failures


def launch_application() -> int:
    """Run the original server in this process, preserving Finder error output."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    result = 0
    try:
        runpy.run_path(str(ROOT / "server.py"), run_name="__main__")
    except KeyboardInterrupt:
        return 130
    except SystemExit as exc:
        result = exc.code if isinstance(exc.code, int) else (1 if exc.code else 0)
        if exc.code and not isinstance(exc.code, int):
            print(exc.code, file=sys.stderr)
    except Exception:
        traceback.print_exc()
        result = 1
    if result and os.environ.get("CUTROOM_FINDER_LAUNCH") == "1" and sys.stdin.isatty():
        print(f"\nCUTROOM stopped (code {result}). The details are above.", file=sys.stderr)
        print("For help, open START HERE.html beside the launcher.", file=sys.stderr)
        try:
            input("\nPress Return to close this window. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--system-only", action="store_true")
    group.add_argument("--python-only", action="store_true")
    group.add_argument("--launch", action="store_true", help="Run the original server in this process.")
    args = parser.parse_args(argv)
    if args.launch:
        return launch_application()
    failures = [] if args.system_only else check_python(imports=args.python_only)
    if not args.python_only:
        failures.extend(check_system())
    if not args.system_only and not args.python_only:
        try:
            shared = runpy.run_path(str(ROOT / "scripts" / "preflight.py"))
            if shared["main"]():
                failures.append("The application runtime check failed; details are above.")
        except Exception as exc:
            failures.append(f"Application runtime: {type(exc).__name__}: {exc}")
    if failures:
        print("CUTROOM Mac preflight failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("CUTROOM Mac preflight passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
