"""Bounded, project-local generations for prepared library media.

The original is never copied or modified. A generation becomes visible only
after all its files are validated and its directory is atomically published.
Project metadata is a separate atomic transaction, not a power-loss journal.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .utils import atomic_write_json

PIPELINE_VERSION = 2
CACHE_FORMAT_VERSION = 1
MAX_GENERATIONS = 8
HASH_BLOCK_BYTES = 1024 * 1024
_OWNER = "cutroom_asset_preparation"
_GENERATION = re.compile(r"(?:prepared-|\.preparing-)([0-9a-f]{32})\Z")
_NAMES = {"manifest.json", "preview.mp4", "preview.m4a", "preview.png", "thumbnail.jpg"}


class PreparationCacheError(ValueError):
    pass


class PreparationBusy(PreparationCacheError):
    """Another preparation owns the asset; its state must remain untouched."""


def _generation(path: Path) -> list[int]:
    value = path.stat()
    if not stat.S_ISREG(value.st_mode):
        raise PreparationCacheError("Media preparation requires a regular file")
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def fingerprint(path: Path, check: Callable[[], None], *, durable: bool = False) -> dict[str, Any]:
    """Hash with bounded memory and reject files changed during the read."""
    check()
    before = _generation(path)
    digest = hashlib.sha256()
    with path.open("r+b" if durable else "rb") as handle:
        while block := handle.read(HASH_BLOCK_BYTES):
            check()
            digest.update(block)
        if durable:
            handle.flush()
            os.fsync(handle.fileno())
    check()
    if _generation(path) != before:
        raise PreparationCacheError("Media changed during preparation; retry the import")
    return {"generation": before, "size": before[2], "sha256": digest.hexdigest()}


def pipeline_options(settings) -> dict[str, Any]:
    executable = Path(shutil.which(str(settings.ffmpeg)) or settings.ffmpeg)
    try:
        tool_generation = _generation(executable)
    except OSError:
        tool_generation = None
    return {
        "version": PIPELINE_VERSION,
        "ffmpeg": str(executable), "ffmpeg_generation": tool_generation,
        "threads": max(1, int(settings.raw.get("ffmpeg_threads", 4))),
        "video": {"max_height": 720, "codec": "libx264", "preset": "veryfast", "crf": 27,
                  "pixel_format": "yuv420p", "audio_codec": "aac", "audio_bitrate": "128k"},
        "large_video": {"above_bytes": 2 * 1024**3, "preview": "validated-original-mp4-h264-yuv420p-aac",
                        "waveform": "not-generated", "thumbnail": "first-frame"},
        "audio": {"codec": "aac", "bitrate": "192k"},
        "image": {"max_width": 4096}, "thumbnail": {"width": 320, "format": "jpeg"},
        "waveform": {"sample_rate": 100, "max_points": 240, "format": "s16le-mono-absolute"},
    }


def source_identity(source: Path, asset: dict[str, Any], settings, check: Callable[[], None]) -> tuple[str, dict[str, Any]]:
    identity = {
        "file": fingerprint(source, check), "path": asset["path"],
        "metadata": {key: asset.get(key) for key in ("kind", "duration", "width", "height", "has_audio")},
        "pipeline": pipeline_options(settings),
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), identity


def assert_source_unchanged(source: Path, identity: dict[str, Any], check: Callable[[], None], *, content: bool) -> None:
    check()
    current = fingerprint(source, check) if content else {"generation": _generation(source)}
    expected = identity["file"]
    if any(current[key] != expected[key] for key in current):
        raise PreparationCacheError("Media changed during preparation; retry the import")


@contextmanager
def preparation_lock(folder: Path, check: Callable[[], None]):
    """One cooperative preparation per asset, across threads and app processes.

    The persistent file's one-byte region is locked even when the file is empty.
    The file is never unlinked: removing it would let
    another process lock a different inode while the first still owns its lock.
    """
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / ".preparation.lock"
    if path.is_symlink():
        raise PreparationCacheError("Invalid media preparation lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b") as handle:
        # Windows _locking supports a range beyond EOF. Do not initialize the
        # region before acquiring it: a competing initializer could write into
        # an active owner's byte lock and misreport that owner's preparation.
        acquired = False
        try:
            deadline = time.monotonic() + 600
            while not acquired:
                check()
                handle.seek(0)
                try:
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} and getattr(exc, "winerror", None) not in {33, 36}:
                        raise
                    if time.monotonic() >= deadline:
                        raise PreparationBusy("Media preparation is busy; retry when it finishes") from exc
                    time.sleep(0.05)
            yield
        finally:
            if acquired:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class PreparationCache:
    def __init__(self, project_dir: Path, folder: Path, check: Callable[[], None], probe: Callable[[Path, str], dict[str, Any]]):
        self.project_dir = project_dir.resolve()
        self.folder = folder.resolve()
        assets = (self.project_dir / "media" / "assets").resolve()
        if self.project_dir not in assets.parents or assets not in self.folder.parents:
            raise PreparationCacheError("Invalid media preparation directory")
        self.check, self.probe = check, probe

    def _record(self, directory: Path) -> dict[str, Any] | None:
        match = _GENERATION.fullmatch(directory.name)
        if not match or directory.is_symlink() or directory.resolve().parent != self.folder:
            return None
        manifest = directory / "manifest.json"
        try:
            if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > 64 * 1024:
                return None
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("owner") != _OWNER or data.get("version") != CACHE_FORMAT_VERSION or data.get("token") != match[1]:
                return None
            return data
        except (OSError, ValueError, TypeError):
            return None

    def directories(self) -> list[Path]:
        found = []
        with os.scandir(self.folder) as entries:
            for count, entry in enumerate(entries):
                if count >= 256:
                    raise PreparationCacheError("Media preparation cache needs local review before retrying")
                if _GENERATION.fullmatch(entry.name):
                    found.append(Path(entry.path))
        return found

    def referenced(self, project: dict[str, Any], candidates: list[Path]) -> set[str]:
        prefixes = {p.name: p.relative_to(self.project_dir).as_posix() for p in candidates}
        references: set[str] = set()
        stack: list[Any] = [project]
        for _ in range(200_000):
            if not stack:
                return references
            value = stack.pop()
            if isinstance(value, dict):
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
            elif isinstance(value, str):
                normalized = value.replace("\\", "/")
                references.update(name for name, prefix in prefixes.items() if normalized == prefix or normalized.startswith(prefix + "/"))
        # Unknown/oversized history must pin everything rather than lose files.
        return set(prefixes)

    def remove_owned(self, directory: Path) -> bool:
        """Delete only a validated generation with a closed, fixed file set."""
        if self._record(directory) is None:
            return False
        try:
            entries = list(directory.iterdir())
            if len(entries) > len(_NAMES) or any(p.name not in _NAMES or p.is_symlink() or not p.is_file() for p in entries):
                return False
            # Retain the ownership manifest until every media file is gone.
            for path in entries:
                if path.name != "manifest.json":
                    path.unlink()
            (directory / "manifest.json").unlink()
            directory.rmdir()
            return True
        except OSError:
            return False

    def cleanup(self, project: dict[str, Any]) -> list[Path]:
        candidates = self.directories()
        references = self.referenced(project, candidates)
        for directory in candidates:
            self.check()
            if directory.name not in references:
                self.remove_owned(directory)
        return self.directories()

    def new_stage(self) -> Path:
        if len(self.directories()) >= MAX_GENERATIONS:
            raise PreparationCacheError("Eight media preparation generations are pinned or need cleanup; review them locally before retrying")
        token = uuid.uuid4().hex
        stage = self.folder / (".preparing-" + token)
        stage.mkdir()
        atomic_write_json(stage / "manifest.json", {"owner": _OWNER, "version": CACHE_FORMAT_VERSION, "token": token, "state": "preparing"})
        return stage

    def _preview(self, kind: str, original_preview: str | None) -> tuple[str, set[str]]:
        if original_preview is not None:
            # Only the thumbnail belongs to this generation. The source is
            # referenced, never moved into the cache or deleted by cleanup.
            relative = Path(original_preview)
            source = self.project_dir / relative
            if (kind != "video" or relative.is_absolute() or relative.drive
                    or ".." in relative.parts or source.resolve().parent != self.folder
                    or source.is_symlink() or not source.is_file()):
                raise PreparationCacheError("Invalid original preview path")
            return original_preview, {"thumbnail.jpg"}
        preview = "preview.png" if kind == "image" else "preview.m4a" if kind == "audio" else "preview.mp4"
        return preview, {preview} | ({"thumbnail.jpg"} if kind != "audio" else set())

    def read(self, directory: Path, key: str, kind: str, *, original_preview: str | None = None) -> dict[str, Any] | None:
        record = self._record(directory)
        if record is None or record.get("state") != "complete" or record.get("identity") != key:
            return None
        expected_mode = "original" if original_preview is not None else "prepared"
        if record.get("preview_mode", "prepared") != expected_mode or record.get("original_preview") != original_preview:
            return None
        preview, names = self._preview(kind, original_preview)
        artifacts, waveform = record.get("artifacts"), record.get("waveform")
        if not isinstance(artifacts, dict) or set(artifacts) != names or not isinstance(waveform, list) or len(waveform) > 240:
            return None
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in waveform):
            return None
        for name in names:
            path, expected = directory / name, artifacts[name]
            if path.is_symlink() or not isinstance(expected, dict):
                return None
            try:
                actual = fingerprint(path, self.check)
                if actual["size"] <= 0 or any(actual[k] != expected.get(k) for k in ("size", "sha256")):
                    return None
                metadata = self.probe(path, "image" if name == "thumbnail.jpg" else kind)
                if metadata != expected.get("metadata") or _generation(path) != actual["generation"]:
                    return None
            except (OSError, ValueError, subprocess.SubprocessError):
                return None
        result = {"preview_path": original_preview if original_preview is not None else (directory / preview).relative_to(self.project_dir).as_posix(),
                  "waveform": waveform, "preparation_identity": key, "preparation_pipeline": PIPELINE_VERSION,
                  "preview_mode": expected_mode}
        if kind != "audio":
            result["thumbnail_path"] = (directory / "thumbnail.jpg").relative_to(self.project_dir).as_posix()
        return result

    def publish(self, stage: Path, key: str, kind: str, waveform: list[float], *, original_preview: str | None = None) -> tuple[Path, dict[str, Any]]:
        record = self._record(stage)
        if record is None or record.get("state") != "preparing":
            raise PreparationCacheError("Invalid media preparation ownership")
        preview, names = self._preview(kind, original_preview)
        artifacts = {}
        for name in names:
            path = stage / name
            if path.is_symlink():
                raise PreparationCacheError("Invalid prepared media file")
            value = fingerprint(path, self.check, durable=True)
            if value["size"] <= 0:
                raise PreparationCacheError("Prepared media is empty")
            artifacts[name] = {"size": value["size"], "sha256": value["sha256"],
                               "metadata": self.probe(path, "image" if name == "thumbnail.jpg" else kind)}
            if _generation(path) != value["generation"]:
                raise PreparationCacheError("Prepared media changed during validation")
        record.update(state="complete", identity=key, artifacts=artifacts, waveform=waveform,
                      preview_mode="original" if original_preview is not None else "prepared", original_preview=original_preview)
        atomic_write_json(stage / "manifest.json", record)
        self.check()
        final = self.folder / ("prepared-" + record["token"])
        os.replace(stage, final)
        result = {"preview_path": original_preview if original_preview is not None else (final / preview).relative_to(self.project_dir).as_posix(),
                  "waveform": waveform, "preparation_identity": key, "preparation_pipeline": PIPELINE_VERSION,
                  "preview_mode": "original" if original_preview is not None else "prepared"}
        if kind != "audio":
            result["thumbnail_path"] = (final / "thumbnail.jpg").relative_to(self.project_dir).as_posix()
        return final, result
