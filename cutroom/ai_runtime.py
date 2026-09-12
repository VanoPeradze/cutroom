"""Small, local-first Ollama supervisor. Never downloads or warms up a model.

An already running daemon is shared, not owned. Even a daemon started here is
left running when CUTROOM closes, so another local app can keep using it.
"""
from __future__ import annotations

import http.client
import ipaddress
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import Settings

DEFAULT_ENDPOINT = "http://127.0.0.1:11434"
LOG_ROTATE_BYTES = 5 * 1024 * 1024


def resolve_ollama_executable() -> str | None:
    """Use a configured executable, PATH, or standard Windows install paths."""
    override = os.environ.get("CUTROOM_OLLAMA", "").strip().strip('"')
    if override:
        candidate = Path(override).expanduser()
        return str(candidate.resolve()) if candidate.is_file() else shutil.which(override)
    found = shutil.which("ollama")
    if found:
        return found
    candidates: list[Path] = []
    for variable, suffix in (
        ("LOCALAPPDATA", "Programs/Ollama/ollama.exe"),
        ("LOCALAPPDATA", "Microsoft/WinGet/Links/ollama.exe"),
        ("ProgramFiles", "Ollama/ollama.exe"),
        ("ProgramFiles(x86)", "Ollama/ollama.exe"),
    ):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / suffix)
    return next((str(path.resolve()) for path in candidates if path.is_file()), None)


def _endpoint(settings: Settings) -> urllib.parse.SplitResult:
    value = str(settings.ai.get("ollama_url", DEFAULT_ENDPOINT)).strip()
    if any(character.isspace() for character in value):
        raise ValueError("Ollama address must not contain whitespace.")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or port == 0):
            raise ValueError("invalid address")
    except ValueError as exc:
        raise ValueError("Use an HTTP or HTTPS Ollama address without credentials, a query, or a fragment.") from exc
    return parsed


def _loopback(parsed: urllib.parse.SplitResult) -> bool:
    if parsed.hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        return False


def _can_launch(parsed: urllib.parse.SplitResult) -> bool:
    return parsed.scheme == "http" and parsed.path in {"", "/"} and _loopback(parsed)


def ollama_environment(settings: Settings) -> dict[str, str]:
    """Child-only environment, also usable for an explicitly requested model pull."""
    parsed = _endpoint(settings)
    if parsed.path not in {"", "/"}:
        raise ValueError("The Ollama CLI requires a root server address without a path.")
    hostname = parsed.hostname or ""
    hostname = f"[{hostname}]" if ":" in hostname else hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    environment = os.environ.copy()
    environment["OLLAMA_HOST"] = f"{parsed.scheme}://{hostname}:{port}"
    environment["OLLAMA_NO_CLOUD"] = "1"
    environment.setdefault("OLLAMA_KEEP_ALIVE", "2m")
    return environment


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # A different endpoint must not masquerade as our local daemon.
        return None


class AIRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._state_lock = threading.Lock()
        self._ensure_lock = threading.Lock()
        self._background_lock = threading.Lock()
        self._background: threading.Thread | None = None
        self._process: subprocess.Popen | None = None
        self._launch_attempted = False
        self._flight_revision = 0
        self._log_path = settings.data_dir / "logs" / "ollama-runtime.log"
        self._status: dict[str, Any] = {
            "state": "idle", "available": False,
            "message": "Local AI has not been checked yet.",
            "error_code": None, "can_retry": True, "models": [],
        }
        if not settings.ai.get("enabled", True):
            self._set("disabled", "Local AI is disabled in settings.", "disabled", can_retry=False)

    def _set(self, state: str, message: str, error_code: str | None = None,
             *, can_retry: bool = True, models: list[str] | None = None) -> None:
        with self._state_lock:
            self._status.update(state=state, available=state == "ready", message=message,
                                error_code=error_code, can_retry=can_retry,
                                models=list(models or []))

    def snapshot(self) -> dict[str, Any]:
        """Cached state only: safe for frequent UI polling."""
        with self._state_lock:
            result = dict(self._status)
            result["models"] = list(self._status["models"])
        try:
            result["endpoint"] = _endpoint(self.settings).geturl().rstrip("/")
        except ValueError:
            result["endpoint"] = "Invalid Ollama address"
        result["managed"] = self._process is not None and self._process.poll() is None
        result["auto_start"] = bool(self.settings.ai.get("auto_start_ollama", True))
        result["log_path"] = str(self._log_path)
        return result

    def _probe(self, endpoint: urllib.parse.SplitResult, timeout: float) -> list[str] | None:
        try:
            # Ignore proxy environment for an explicitly local address.
            proxy = urllib.request.ProxyHandler({}) if _loopback(endpoint) else urllib.request.ProxyHandler()
            opener = urllib.request.build_opener(proxy, _NoRedirect())
            url = endpoint.geturl().rstrip("/") + "/api/tags"
            with opener.open(url, timeout=max(0.01, timeout)) as response:
                payload = json.loads(response.read(2 * 1024 * 1024))
            if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
                return None
            return [str(model["name"]) for model in payload["models"]
                    if isinstance(model, dict) and model.get("name")]
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
            return None

    def _launch(self) -> bool:
        self._launch_attempted = True
        executable = resolve_ollama_executable()
        if not executable:
            self._set("error", "Ollama is not installed. Install the local AI engine once, then retry.", "not_installed")
            return False
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            # Keep at most one previous launch log. A running daemon's file is never moved.
            if self._log_path.exists() and self._log_path.stat().st_size >= LOG_ROTATE_BYTES:
                self._log_path.replace(self._log_path.with_suffix(".previous.log"))
            options: dict[str, Any] = {
                "stdin": subprocess.DEVNULL, "stderr": subprocess.STDOUT,
                "env": ollama_environment(self.settings), "cwd": str(self.settings.root),
            }
            if os.name == "nt":
                options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            else:
                options["start_new_session"] = True
            with self._log_path.open("ab") as log:
                self._process = subprocess.Popen([executable, "serve"], stdout=log, **options)
            return True
        except (OSError, ValueError, subprocess.SubprocessError):
            self._set("error", "The local AI engine could not start. Check the runtime log, then retry.", "start_failed")
            return False

    def ensure_ready(self, timeout: float = 30, retry: bool = False) -> dict[str, Any]:
        """Probe, optionally start, and wait a bounded time; callers share one launch."""
        timeout = min(120.0, max(0.0, float(timeout)))
        deadline = time.monotonic() + timeout
        observed_revision = self._flight_revision
        if not self._ensure_lock.acquire(timeout=timeout):
            return self.snapshot()
        executed = False
        try:
            # Return the same completed result to overlapping requests, including
            # Retry requests after a failed launch. A later explicit Retry starts
            # a new attempt; a queue of existing waiters must not restart in a loop.
            if self._flight_revision != observed_revision:
                return self.snapshot()
            executed = True
            if not self.settings.ai.get("enabled", True):
                self._set("disabled", "Local AI is disabled in settings.", "disabled", can_retry=False)
                return self.snapshot()
            try:
                endpoint = _endpoint(self.settings)
            except ValueError as exc:
                self._set("error", str(exc), "invalid_endpoint", can_retry=False)
                return self.snapshot()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return self.snapshot()
            previous = self.snapshot()
            self._set("checking", "Checking the local AI engine...")
            models = self._probe(endpoint, min(1.0, remaining))
            if models is not None:
                self._set("ready", "Local AI is ready.", models=models)
                return self.snapshot()
            if not _can_launch(endpoint):
                self._set("error", "The configured AI server is unavailable. CUTROOM can only start a plain HTTP loopback server automatically.", "nonlocal_endpoint")
                return self.snapshot()
            if not self.settings.ai.get("auto_start_ollama", True):
                self._set("error", "The AI engine is unavailable and automatic startup is disabled in settings.", "auto_start_disabled")
                return self.snapshot()
            running = self._process is not None and self._process.poll() is None
            if not running and self._launch_attempted and not retry:
                code = previous.get("error_code") or "process_exited"
                message = previous["message"] if previous["state"] == "error" else "The local AI engine stopped. Retry to start it again."
                self._set("error", message, code)
                return self.snapshot()
            if deadline <= time.monotonic():
                self._set("error", "The AI engine did not become ready in time. Retry to check it again.", "startup_timeout")
                return self.snapshot()
            self._set("starting", "Starting the local AI engine...")
            if not running and not self._launch():
                return self.snapshot()
            while time.monotonic() < deadline:
                models = self._probe(endpoint, min(1.0, max(0.01, deadline - time.monotonic())))
                if models is not None:
                    self._set("ready", "Local AI is ready.", models=models)
                    return self.snapshot()
                if self._process is not None and self._process.poll() is not None:
                    self._set("error", "The local AI engine stopped during startup. Check the runtime log, then retry.", "process_exited")
                    return self.snapshot()
                time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
            self._set("error", "The AI engine is still starting or did not respond in time. Retry to check it again.", "startup_timeout")
            return self.snapshot()
        finally:
            if executed:
                self._flight_revision += 1
            self._ensure_lock.release()

    def start_background(self) -> None:
        """Nonblocking startup check; repeated calls cannot spawn extra workers."""
        with self._background_lock:
            if self._background is not None and self._background.is_alive():
                return
            self._background = threading.Thread(target=self.ensure_ready, name="cutroom-ai-runtime", daemon=True)
            self._background.start()
