"""Explicit, cancellable local-model downloads; inventory never contacts a server.

The catalog is intentionally bounded. Downloading weights does not execute them,
load a GPU, change project profiles, or send footage to a model host.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from typing import Any

from .config import Settings
from .jobs import JobContext

OLLAMA_INSTALL_URL = "https://ollama.com/download"
_WHISPER_REPOS = {
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    # Keep this alias aligned with the installed faster-whisper downloader.
    "turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "ivrit-ai/whisper-large-v3-turbo-ct2": "ivrit-ai/whisper-large-v3-turbo-ct2",
}
_SPEECH = {
    "base": ("Whisper Base", 0.15, "Smallest download; useful for clear speech and lighter computers."),
    "small": ("Whisper Small", 0.49, "A balanced multilingual starting point; usually more accurate than Base."),
    "turbo": ("Whisper Turbo", 1.63, "Higher-quality multilingual transcription; needs more memory and processing time."),
    "ivrit-ai/whisper-large-v3-turbo-ct2": ("Hebrew · ivrit.ai", 1.63, "Hebrew-focused transcription for Quality mode with the spoken language set to Hebrew."),
}
_STORY = {
    "qwen3.5:2b": ("Story · Lite", 2.7, "Lighter story planning; complex material may need a stronger model."),
    "qwen3.5:4b": ("Story · Balanced", 3.4, "The default local model for organizing a first cut."),
    "qwen3.5:9b": ("Story · Quality", 6.6, "Stronger story planning with higher memory use and longer processing times."),
    "qwen3:8b": ("Story · alternative", 5.2, "Configured fallback for local story planning."),
}
_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]


def _dependency_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def speech_cache_dir() -> Path:
    """Match Hugging Face's normal cache without importing an inference library."""
    explicit = os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
    if explicit:
        return Path(os.path.expandvars(explicit)).expanduser()
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(os.path.expandvars(hf_home)).expanduser() / "hub"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".cache") / "huggingface" / "hub"


def _complete_speech_snapshot(path: Path) -> bool:
    try:
        files = [path / name for name in ("config.json", "model.bin", "tokenizer.json")]
        vocabulary = [path / "vocabulary.json", path / "vocabulary.txt"]
        return all(file.is_file() and file.stat().st_size > 0 for file in files) and any(
            file.is_file() and file.stat().st_size > 0 for file in vocabulary
        )
    except OSError:
        return False


def speech_installed(model: str) -> bool:
    repo = _WHISPER_REPOS.get(model)
    if not repo:
        return False
    directory = speech_cache_dir() / ("models--" + repo.replace("/", "--"))
    try:
        revision = (directory / "refs" / "main").read_text(encoding="utf-8").strip()
        if not re.fullmatch(r"[0-9a-fA-F]{40,64}", revision):
            return False
        return _complete_speech_snapshot(directory / "snapshots" / revision)
    except (OSError, UnicodeError):
        return False


def _story_installed(model: str, runtime: dict[str, Any]) -> bool:
    # A successfully probed engine is authoritative, including a custom store.
    names = {str(item).removesuffix(":latest") for item in runtime.get("models", [])}
    if model.removesuffix(":latest") in names:
        return True
    root = Path(os.environ.get("OLLAMA_MODELS") or Path.home() / ".ollama" / "models")
    name, _, tag = model.partition(":")
    try:
        manifest = root / "manifests" / "registry.ollama.ai" / "library" / name / (tag or "latest")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        layers = data.get("layers", [])
        if not isinstance(layers, list) or not layers:
            return False
        for layer in [data.get("config", {}), *layers]:
            digest = layer.get("digest", "") if isinstance(layer, dict) else ""
            size = layer.get("size") if isinstance(layer, dict) else None
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                return False
            blob = root / "blobs" / digest.replace(":", "-")
            if not blob.is_file() or (isinstance(size, int) and blob.stat().st_size != size):
                return False
        return True
    except (OSError, ValueError, AttributeError):
        return False


def catalog(settings: Settings, runtime: dict[str, Any], *, engine_installed: bool) -> dict[str, Any]:
    speech_ready = _dependency_available("faster_whisper") and _dependency_available("huggingface_hub")
    speech_profiles: dict[str, list[str]] = {}
    for profile, model in settings.ai.get("whisper_models", {}).items():
        speech_profiles.setdefault(str(model), []).append(str(profile))
    hebrew = str(settings.ai.get("hebrew_whisper_model") or "")
    if hebrew:
        speech_profiles.setdefault(hebrew, []).append("quality · Hebrew")
    story_profiles: dict[str, list[str]] = {}
    for profile, field in (("lite", "editor_lite_model"), ("balanced", "editor_model"), ("quality", "editor_quality_model")):
        story_profiles.setdefault(str(settings.ai.get(field) or ""), []).append(profile)
    for model in settings.ai.get("editor_fallback_models", []):
        story_profiles.setdefault(str(model), []).append("fallback")
    rows: list[dict[str, Any]] = []
    for kind, definitions, profiles in (("transcription", _SPEECH, speech_profiles), ("editor", _STORY, story_profiles)):
        for model, (label, estimate, description) in definitions.items():
            if model not in profiles:
                continue
            installed = speech_installed(model) if kind == "transcription" else _story_installed(model, runtime)
            rows.append({
                "kind": kind, "model": model, "label": label, "description": description,
                "profiles": profiles[model], "estimated_download_gb": estimate,
                "requirements": (
                    "Runs on CPU; compatible NVIDIA acceleration is optional. Larger models need more RAM and time."
                    if kind == "transcription" else
                    "Requires Ollama. Runs on CPU or supported GPU; memory needs grow with model and video length."
                ),
                "installed": installed, "status": "installed" if installed else "not_installed",
                "can_download": not installed and (speech_ready if kind == "transcription" else engine_installed),
            })
    unsupported = [model for model in speech_profiles if model not in _SPEECH] + [model for model in story_profiles if model and model not in _STORY]
    return {
        "runtime": {
            "installed": engine_installed, "available": bool(runtime.get("available")),
            "state": runtime.get("state", "idle"),
            "message": runtime.get("message") if engine_installed else "Install Ollama once to use local Story AI. Speech models do not require Ollama.",
            "install_url": OLLAMA_INSTALL_URL,
        },
        "transcription_engine_installed": speech_ready,
        "models": rows,
        "notes": [
            "Download one speech model and one Story model for your preferred profile. You do not need all models.",
            "Sizes are estimates for model files, not total installation size or RAM requirements. Allow extra disk space for caches and videos.",
            "Downloads need internet. Installed local models process footage on your computer; no footage is uploaded by this setup.",
            "Downloading a model does not change your editing profile. Auto mode can choose a lighter model based on your computer.",
            "Cancelling stops CUTROOM's download task; reusable partial cache files may remain.",
            "Status checks read local files and cached engine status only; they do not load or test model inference.",
        ] + (["Some custom configured models are not in the download catalog; manage these with their provider's tools."] if unsupported else []),
    }


def supported_install(kind: str, model: str) -> bool:
    return model in (_SPEECH if kind == "transcription" else _STORY if kind == "editor" else {})


def install_transcription(context: JobContext, model: str, settings: Settings) -> dict[str, Any]:
    if model not in _WHISPER_REPOS:
        raise ValueError("Choose a speech model from the Local models catalog.")
    context.check_cancelled()
    if speech_installed(model):
        return {"kind": "transcription", "model": model, "installed": True, "already_installed": True}
    if not _dependency_available("huggingface_hub") or not _dependency_available("faster_whisper"):
        raise RuntimeError("Local speech support is not installed. Run CUTROOM setup again, then retry.")
    cache = speech_cache_dir()
    existing = cache
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    needed = int(_SPEECH[model][1] * 1_000_000_000 * 1.2) + 100_000_000
    if shutil.disk_usage(existing).free < needed:
        raise RuntimeError(f"Not enough free space for this speech model. Allow about {needed / 1e9:.1f} GB on the model-cache drive, then retry.")
    environment = os.environ.copy()
    environment.update(PYTHONUNBUFFERED="1", HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1", HF_HUB_DISABLE_XET="1")
    context.update(0.01, f"Connecting to download {model}; no video is uploaded")
    process = subprocess.Popen(
        [sys.executable, "-u", "-m", "cutroom.local_models", "--download", model],
        cwd=str(settings.root), env=environment, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    lines: queue.Queue[str] = queue.Queue(maxsize=128)
    stopped = threading.Event()
    finished = threading.Event()

    def read() -> None:
        try:
            for line in process.stdout or []:
                while not stopped.is_set():
                    try:
                        lines.put(line[:4096], timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            finished.set()

    reader = threading.Thread(target=read, daemon=True, name="cutroom-model-download")
    reader.start()
    error_message = "Model download failed. Check your connection and free disk space, then retry; partial downloads can be reused."
    try:
        while True:
            context.check_cancelled()
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                if process.poll() is not None and finished.is_set():
                    break
                continue
            try:
                event = json.loads(line)
                if event.get("event") == "progress":
                    fraction = float(event.get("fraction", 0))
                    if math.isfinite(fraction):
                        count = max(0, int(event.get("completed", 0)))
                        total = max(0, int(event.get("total", 0)))
                        units = "bytes" if event.get("unit") == "B" else "files"
                        context.update(max(0.01, min(0.95, fraction * 0.95)), f"Downloading {model}: {count:,} / {total:,} {units}")
                elif event.get("event") == "error" and event.get("code") == "disk":
                    error_message = "The model-cache drive ran out of space. Free space there and retry the download."
            except (ValueError, TypeError, AttributeError):
                continue
        context.checkpoint()
        if process.wait() != 0 or not speech_installed(model):
            raise RuntimeError(error_message)
        context.update(1, f"{model} is downloaded and ready for local transcription")
        return {"kind": "transcription", "model": model, "installed": True}
    finally:
        stopped.set()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()


def _download_worker(model: str) -> int:
    """Separate process: cancellation can interrupt blocked network/native I/O."""
    if model not in _WHISPER_REPOS:
        return 2
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm

    class Progress(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = False
            self._last_report = 0.0
            super().__init__(*args, **kwargs)

        def display(self, *args, **kwargs):
            # Never print terminal progress control codes; stdout is a JSON protocol.
            return None

        def update(self, n=1):
            result = super().update(n)
            now = time.monotonic()
            if self.total and (now - self._last_report >= 0.5 or self.n >= self.total):
                self._last_report = now
                print(json.dumps({"event": "progress", "fraction": min(1, self.n / self.total),
                                  "completed": self.n, "total": self.total, "unit": self.unit}), flush=True)
            return result

    try:
        path = snapshot_download(_WHISPER_REPOS[model], allow_patterns=_FILES, token=False, endpoint="https://huggingface.co",
                                 cache_dir=str(speech_cache_dir()), max_workers=2, tqdm_class=Progress)
        if not _complete_speech_snapshot(Path(path)):
            raise ValueError("Incomplete model files")
        print(json.dumps({"event": "complete"}), flush=True)
        return 0
    except Exception as error:
        print(json.dumps({"event": "error", "code": "disk" if isinstance(error, OSError) and error.errno == 28 else "download"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(_download_worker(sys.argv[2]) if len(sys.argv) == 3 and sys.argv[1] == "--download" else 2)
