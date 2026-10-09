"""Mac overlay checks; never installs packages or downloads AI models."""
from __future__ import annotations

import argparse
import importlib
from importlib.metadata import PackageNotFoundError, version as package_version
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import socket
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


def check_system(*, only_overrides: bool = False) -> list[str]:
    failures: list[str] = []
    ffmpeg = os.environ.get("CUTROOM_FFMPEG") or shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = os.environ.get("CUTROOM_FFPROBE") or shutil.which("ffprobe") or "ffprobe"
    for label, variable, command in (("FFmpeg", "CUTROOM_FFMPEG", ffmpeg), ("FFprobe", "CUTROOM_FFPROBE", ffprobe)):
        if only_overrides and not os.environ.get(variable):
            continue
        try:
            _capture(command, "-version")
            if label == "FFmpeg":
                filters = _capabilities(_capture(command, "-hide_banner", "-filters"))
                encoders = _capabilities(_capture(command, "-hide_banner", "-encoders"))
                if "subtitles" not in filters:
                    failures.append(f"FFmpeg at {command} lacks libass subtitles; install ffmpeg@7.")
                for encoder in ("libx264", "aac"):
                    if encoder not in encoders:
                        failures.append(f"FFmpeg at {command} lacks the {encoder} encoder.")
                # The frozen application uses these options. FFmpeg 9 removed
                # them, so codec support alone cannot establish compatibility.
                help_text = _capture(command, "-hide_banner", "-h", "full")
                options = set(re.findall(r"(?m)^\s*(-[A-Za-z0-9_]+)(?=\s|$)", help_text))
                for option in ("-filter_complex_script", "-vsync"):
                    if option not in options:
                        failures.append(f"FFmpeg at {command} lacks {option}, required by this beta; use ffmpeg@7.")
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            failures.append(f"{label} at {command}: {exc}")
    return failures


def check_python(*, imports: bool = True) -> list[str]:
    failures: list[str] = []
    try:
        av_version = package_version("av")
        parsed = re.match(r"^(\d+)\.(\d+)\.(\d+)(?:$|[.+-])", av_version)
        release = tuple(map(int, parsed.groups())) if parsed else ()
        if not (18, 1, 0) <= release < (19, 0, 0):
            failures.append(f"PyAV {av_version} is incompatible with this beta's transcription; run Mac setup to install av>=18.1.0,<19.")
    except PackageNotFoundError:
        failures.append("PyAV is missing; run Mac setup to install av>=18.1.0,<19.")
    if not (3, 12) <= sys.version_info[:2] < (3, 13):
        failures.append("Use Python 3.12 for this Mac beta.")
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


def reserve_macos_server_sockets(host: str, port: int, startup_error_type: type[Exception]) -> list[socket.socket]:
    """Reserve listening sockets for this Mac launch without changing socket globally."""
    if sys.platform != "darwin":
        raise RuntimeError("The Mac socket adapter requires macOS.")
    candidates: list[socket.socket] = []
    seen = set()
    try:
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise startup_error_type(f"CUTROOM could not resolve its local host {host!r}: {exc}") from exc
        for family, socktype, protocol, _canonical_name, address in addresses:
            identity = (family, tuple(address))
            if identity in seen:
                continue
            seen.add(identity)
            try:
                candidate = socket.socket(family, socktype, protocol)
                candidates.append(candidate)
                # POSIX reuse addresses permits restart after TIME_WAIT; reuse
                # ports would allow competing listeners and is never enabled.
                # https://docs.python.org/3/library/socket.html#socket.create_server
                candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                if family == socket.AF_INET6 and hasattr(socket, "IPV6_V6ONLY"):
                    candidate.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                candidate.bind(address)
                # Claim the listener now. Waitress accepts supplied sockets and
                # calls listen again with its configured backlog during startup.
                candidate.listen(128)
            except OSError as exc:
                raise startup_error_type(
                    f"CUTROOM cannot start because {host}:{port} is already in use or unavailable. "
                    "Close the other program or choose another CUTROOM_PORT."
                ) from exc
        if not candidates:
            raise startup_error_type(f"CUTROOM could not find a local address for {host!r}.")
        return candidates
    except BaseException:
        for candidate in candidates:
            try:
                candidate.close()
            except OSError:
                pass
        raise


def run_macos_server() -> None:
    """Keep the original server main/identity checks and adapt only reservation."""
    if sys.platform != "darwin":
        raise RuntimeError("The Mac launcher requires macOS.")
    server = importlib.import_module("server")
    original_reserve = server._reserve_server_sockets
    try:
        server._reserve_server_sockets = lambda host, port: reserve_macos_server_sockets(
            host, port, server.ServerStartupError,
        )
        try:
            server.main()
        except server.ServerStartupError as error:
            # Match server.py's original command-line startup error formatting.
            print(f"ERROR: {error}", file=sys.stderr)
            raise SystemExit(1) from None
    finally:
        server._reserve_server_sockets = original_reserve


def launch_application() -> int:
    """Run the original server in this process, preserving Finder error output."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    result = 0
    try:
        run_macos_server()
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
    group.add_argument("--overrides-only", action="store_true", help="Validate only explicitly configured FFmpeg/FFprobe paths.")
    group.add_argument("--launch", action="store_true", help="Run the original server in this process.")
    args = parser.parse_args(argv)
    if args.launch:
        return launch_application()
    system_only = args.system_only or args.overrides_only
    failures = [] if system_only else check_python(imports=args.python_only)
    if not args.python_only:
        failures.extend(check_system(only_overrides=args.overrides_only))
    if not system_only and not args.python_only:
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
