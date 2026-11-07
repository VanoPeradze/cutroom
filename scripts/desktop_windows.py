"""CUTROOM's no-install Windows desktop-window launcher.

The editor and renderer remain local. The installed Chrome runtime supplies the
window; this is deliberately not advertised as a native rewritten editor.
Closing the window never kills an export or another CUTROOM instance.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def find_chrome(environment: dict[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        directory = env.get(key)
        if directory:
            candidate = Path(directory) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if candidate.is_file():
                return candidate
    raise RuntimeError("Google Chrome is not installed. No software was installed or downloaded. Use run_windows.bat for the browser version.")


def load_saved_paths(root: Path = ROOT) -> None:
    # Never execute the generated batch file or accept shell commands from it.
    from scripts.windows_runtime import restore_runtime_paths

    path = root / ".runtime-paths.cmd"
    if not path.is_file():
        return
    text = path.read_text(encoding="ascii")
    match = re.search(r'^\s*set\s+"CUTROOM_RUNTIME_PATHS_B64=([A-Za-z0-9+/=]+)"\s*$', text, re.MULTILINE | re.IGNORECASE)
    if match:
        os.environ["CUTROOM_RUNTIME_PATHS_B64"] = match.group(1)
        restore_runtime_paths()


def chrome_arguments(chrome: Path, url: str, profile: Path) -> list[str]:
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Desktop mode accepts only the verified local CUTROOM address.")
    if parsed.path not in ("", "/"):
        raise ValueError("Unexpected desktop application path.")
    return [str(chrome), f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check", "--disable-background-mode", "--window-size=1440,960"]


def launch_backend(python: Path, root: Path, log_path: Path):
    environment = os.environ.copy()
    environment.update(CUTROOM_NO_BROWSER="1", PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log:
        return subprocess.Popen(
            [str(python), str(root / "scripts" / "windows_runtime.py"), "server"],
            cwd=str(root), env=environment, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


def wait_for_backend(probe, process, *, timeout: float = 45.0, clock=time.monotonic, sleep=time.sleep) -> None:
    deadline = clock() + timeout
    while clock() < deadline:
        owner = probe()
        if owner == "match":
            return
        if owner in ("different_instance", "different_version"):
            raise RuntimeError("Another CUTROOM data folder or version is already open on this port. Close that instance before opening this folder. Nothing was stopped.")
        if process.poll() is not None:
            raise RuntimeError("The local engine stopped during startup. See data/logs/desktop-engine.log. No setup or installation was attempted.")
        sleep(0.25)
    # Do not terminate a process on a readiness timeout: it may be completing
    # startup or an owned operation. A later launch can safely reconnect.
    raise RuntimeError("The local engine is still starting. Try this launcher again, or inspect data/logs/desktop-engine.log. No processes were terminated.")


def show_error(message: str) -> None:
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "CUTROOM Desktop", 0x10)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open CUTROOM in a separate desktop window using installed Chrome.")
    parser.add_argument("--check", action="store_true", help="Validate local prerequisites without starting an engine or window.")
    arguments = parser.parse_args(argv)
    if os.name != "nt":
        raise RuntimeError("This desktop launcher currently supports Windows only.")
    python = ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file() or not (ROOT / ".setup-complete").is_file():
        raise RuntimeError("CUTROOM's existing runtime is not ready. Complete the normal setup first. Desktop mode does not install dependencies.")
    chrome = find_chrome()
    load_saved_paths()
    from cutroom import __version__
    from cutroom.config import load_settings
    from server import _cutroom_instance_id, _http_server_url, _is_loopback_host, _probe_existing_cutroom_server

    settings = load_settings()
    host = str(settings.raw.get("host", "127.0.0.1")).strip()
    if not _is_loopback_host(host):
        raise RuntimeError("Desktop mode refuses non-local server addresses.")
    port = int(settings.raw["port"])
    instance = _cutroom_instance_id(settings)
    url = _http_server_url(host, port)
    # A dedicated profile never changes the user's normal browser profile.
    profile = Path(os.environ.get("LOCALAPPDATA", str(settings.cache_dir))) / "CUTROOM" / "Desktop" / "Chrome" / instance
    command = chrome_arguments(chrome, url, profile)
    if arguments.check:
        print(json.dumps({"ready": True, "mode": "Chrome desktop window", "version": __version__, "engine_root": str(ROOT), "project_data": str(settings.data_dir), "browser_runtime": str(chrome), "address": url, "installs_required": False}, ensure_ascii=False, indent=2))
        return 0
    probe = lambda: _probe_existing_cutroom_server(host, port, instance)
    owner = probe()
    if owner in ("different_instance", "different_version"):
        raise RuntimeError("Another CUTROOM folder or version is open. Close it before launching this folder. Your projects were not moved or changed.")
    if owner != "match":
        process = launch_backend(python, ROOT, settings.data_dir / "logs" / "desktop-engine.log")
        wait_for_backend(probe, process)
    subprocess.Popen(command, cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        show_error(str(exc))
        raise SystemExit(1)
