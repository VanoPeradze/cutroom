"""Bounded upload staging and per-volume admission, independent of Flask.

Waitress buffers a complete HTTP request before WSGI runs. Small raw requests
avoid holding two full temporary copies of a large multipart upload. A ticket
reserves the *remaining* original bytes, and one bounded transport buffer.
"""
from __future__ import annotations

import atexit
import errno
import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO

CHUNK_BYTES = 8 * 1024**2
RESERVE_BYTES = 1024**3
TICKET_TTL_SECONDS = 10 * 60
MAX_TICKETS = 16
TOKEN_RE = re.compile(r"[A-Za-z0-9_-]{16,128}\Z")
JOURNAL_RE = re.compile(r"upload-([0-9a-f]{32})\.json\Z")


def process_alive(pid: int) -> bool:
    """A read-only liveness check; never terminate another process."""
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() != 87  # Only an absent PID proves staleness.
        try:
            code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)  # POSIX signal 0 only checks liveness and permissions.
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def is_storage_full(error: BaseException) -> bool:
    return isinstance(error, OSError) and (
        error.errno in {errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)}
        or getattr(error, "winerror", None) in {39, 112, 1295, 1816}
    )


def filesystem_id(path: Path) -> str:
    """stat follows mount points; Windows volume GUIDs also distinguish mounts."""
    current = path.resolve()
    while not current.exists():
        current = current.parent
    if os.name == "nt":
        import ctypes
        volume = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetVolumePathNameW(str(current), volume, len(volume)):
            guid = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetVolumeNameForVolumeMountPointW(volume.value, guid, len(guid)):
                return guid.value.lower()
            return volume.value.lower()
    return str(current.stat().st_dev)


class UploadStorageError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409, **details: Any):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details

    def public(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, **self.details}


@dataclass
class UploadTicket:
    project_id: str
    token: str
    purpose: str
    slot: str | None
    filename: str
    size: int
    path: Path
    received: int = 0
    updated: float = field(default_factory=time.monotonic)
    busy: bool = False
    cancelled: bool = False
    finalizing: bool = False
    transport_busy: bool = False
    transport_lease: str = ""
    journal_path: Path | None = None


class UploadStorage:
    def __init__(self, data_dir: Path, *, projects_dir: Path | None = None, ttl: float = TICKET_TTL_SECONDS):
        self.data_dir = Path(data_dir)
        self.projects_dir = Path(projects_dir) if projects_dir is not None else self.data_dir / "projects"
        self.temp_dir = Path(tempfile.gettempdir())
        self.ttl = ttl
        self.lock = threading.RLock()
        self.tickets: dict[tuple[str, str], UploadTicket] = {}
        self.retired: dict[tuple[str, str], float] = {}
        self.legacy: dict[str, dict[str, int]] = {}
        self._closed = False
        self._timer: threading.Timer | None = None
        self.journal_dir = self.data_dir / "cache" / "upload-staging"
        self.recover_stale()
        atexit.register(self.close)

    def recover_stale(self) -> None:
        """Recover only validated journal-owned partials from a dead process.

        No project scans or .incoming glob deletion: a journal is durable before
        its original can be created. Live owners and malformed records are kept.
        """
        if not self.journal_dir.is_dir() or self.journal_dir.is_symlink():
            return
        liveness: dict[int, bool] = {}
        for index, manifest in enumerate(self.journal_dir.iterdir()):
            if index >= 512:
                break
            match = JOURNAL_RE.fullmatch(manifest.name)
            if not match or manifest.is_symlink():
                continue
            try:
                if not manifest.is_file() or manifest.stat().st_size > 4096:
                    continue
                record = json.loads(manifest.read_text(encoding="utf-8"))
                if not isinstance(record, dict) or record.get("owner") != "cutroom-upload-staging-v1":
                    continue
                pid, project_id = record.get("pid"), record.get("project_id")
                if type(pid) is not int or not 0 < pid < 2**32 or not isinstance(project_id, str):
                    continue
                if not re.fullmatch(r"project_[0-9a-f]{12}", project_id):
                    continue
                if pid not in liveness:
                    liveness[pid] = process_alive(pid)
                if liveness[pid]:
                    continue
                path = self.target_dir(project_id) / f".incoming-{match[1]}"
                root = self.projects_dir.resolve()
                if path.is_symlink() or path.parent.resolve() != root / project_id / "media":
                    continue
                if path.exists() and not path.is_file():
                    continue
                path.unlink(missing_ok=True)
                manifest.unlink(missing_ok=True)
            except (OSError, ValueError):
                logging.getLogger(__name__).warning("Could not recover owned upload partial %s", manifest.name)

    def _journal(self, ticket: UploadTicket, identity: str) -> None:
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        path = self.journal_dir / f"upload-{identity}.json"
        temporary = self.journal_dir / f".journal-{uuid.uuid4().hex}.tmp"
        if path.exists():
            raise UploadStorageError("upload_conflict", "The staging reservation changed. Try importing again.")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump({"owner": "cutroom-upload-staging-v1", "pid": os.getpid(),
                           "project_id": ticket.project_id}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
            ticket.journal_path = path
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def target_dir(self, project_id: str) -> Path:
        if not re.fullmatch(r"project_[0-9a-f]{12}", project_id):
            raise UploadStorageError("not_found", "The project is unavailable.", 404)
        return self.projects_dir / project_id / "media"

    def _volumes(self, data_path: Path | None = None) -> dict[str, tuple[Path, list[str]]]:
        volumes: dict[str, tuple[Path, list[str]]] = {}
        for role, path in (("data", data_path or self.data_dir), ("temporary", self.temp_dir)):
            while not path.exists():
                path = path.parent
            key = filesystem_id(path)
            if key in volumes:
                volumes[key][1].append(role)
            else:
                volumes[key] = (path, [role])
        return volumes

    def _needs(self, size: int, transport: str, data_path: Path | None = None, chunk_buffer_bytes: int = CHUNK_BYTES) -> dict[str, int]:
        needs: dict[str, int] = {}
        for path, amount in ((data_path or self.data_dir, size), (self.temp_dir, chunk_buffer_bytes if transport == "chunked-v1" else size)):
            volume = filesystem_id(path)
            needs[volume] = needs.get(volume, 0) + amount
        return needs

    def plan(self, size: int, transport: str = "chunked-v1", *, exclude: UploadTicket | None = None,
             legacy_id: str | None = None, transport_buffer_bytes: int = 0, data_path: Path | None = None,
             chunk_buffer_bytes: int = CHUNK_BYTES) -> dict[str, Any]:
        with self.lock:
            reserved: dict[str, int] = {}
            for ticket in self.tickets.values():
                if ticket is exclude:
                    continue
                if ticket.cancelled:
                    if ticket.transport_busy:
                        volume = filesystem_id(self.temp_dir)
                        reserved[volume] = reserved.get(volume, 0) + CHUNK_BYTES
                    continue
                for volume, amount in self._needs(max(0, ticket.size - ticket.received), "chunked-v1", ticket.path.parent).items():
                    reserved[volume] = reserved.get(volume, 0) + amount
            for key, needs in self.legacy.items():
                if key != legacy_id:
                    for volume, amount in needs.items():
                        reserved[volume] = reserved.get(volume, 0) + amount
            needs = self._needs(size, transport, data_path, chunk_buffer_bytes)
            temp_volume = filesystem_id(self.temp_dir)
            needs[temp_volume] = needs.get(temp_volume, 0) + transport_buffer_bytes
            rows = []
            data_free = 0
            for volume, (path, roles) in self._volumes(data_path).items():
                free = int(shutil.disk_usage(path).free)
                held = reserved.get(volume, 0)
                rows.append({"roles": roles, "filesystem": volume, "disk_free_bytes": free,
                             "reserved_bytes": held, "required_bytes": needs.get(volume, 0),
                             "location": str(path.resolve()),
                             "locations": [str(Path(target).resolve()) for target in
                                 (data_path or self.data_dir, self.temp_dir) if filesystem_id(Path(target)) == volume],
                             "available_bytes": max(0, free - held - RESERVE_BYTES)})
                if "data" in roles:
                    data_free = free
            return {"disk_free_bytes": data_free, "storage_plan": {
                "transport": transport, "file_bytes": size, "chunk_size_bytes": CHUNK_BYTES,
                "reserve_bytes": RESERVE_BYTES, "filesystems": rows,
                "scope": "transfer_only_processing_checked_after_metadata"}}

    def require(self, size: int, transport: str = "chunked-v1", **kwargs: Any) -> dict[str, Any]:
        facts = self.plan(size, transport, **kwargs)
        if any(row["disk_free_bytes"] < row["reserved_bytes"] + RESERVE_BYTES + row["required_bytes"] for row in facts["storage_plan"]["filesystems"]):
            raise UploadStorageError("insufficient_storage", "There is not enough free space to import this file. Free space on the indicated drive and try again.", 507, **facts)
        return facts

    def storage_error(self, ticket: UploadTicket | None = None, *, transport: str = "chunked-v1", data_path: Path | None = None) -> UploadStorageError:
        return UploadStorageError("insufficient_storage", "The drive ran out of space while importing. Your existing media and edit are unchanged. Free space and try again.", 507,
                                  **self.plan(max(0, ticket.size - ticket.received) if ticket else 0, transport, exclude=ticket, data_path=ticket.path.parent if ticket else data_path))

    def _schedule(self) -> None:
        if self._timer is None and not self._closed:
            self._timer = threading.Timer(min(60, self.ttl), self._expire)
            self._timer.daemon = True
            self._timer.start()

    def _expire(self) -> None:
        with self.lock:
            self._timer = None
            self.prune()
            if self.tickets:
                self._schedule()

    def _remove(self, ticket: UploadTicket) -> None:
        # The path is generated by this instance, never derived from a project record.
        ticket.path.unlink(missing_ok=True)
        if ticket.journal_path is not None:
            ticket.journal_path.unlink(missing_ok=True)
        self.tickets.pop((ticket.project_id, ticket.token), None)
        self.retired[ticket.project_id, ticket.token] = time.monotonic()

    def prune(self) -> None:
        with self.lock:
            now = time.monotonic()
            for key, updated in list(self.retired.items()):
                if now - updated >= self.ttl:
                    self.retired.pop(key, None)
            for ticket in list(self.tickets.values()):
                if not ticket.busy and not ticket.transport_busy and (ticket.cancelled or now - ticket.updated >= self.ttl):
                    self._remove(ticket)

    def admit(self, project_id: str, purpose: str, slot: str | None, filename: str, size: int,
              project_root: Path, token: str | None = None) -> tuple[UploadTicket, dict[str, Any]]:
        with self.lock:
            self.prune()
            token = token or uuid.uuid4().hex
            if not TOKEN_RE.fullmatch(token):
                raise UploadStorageError("invalid_upload_token", "Upload token must contain 16-128 letters, numbers, underscores, or hyphens.", 400)
            if (project_id, token) in self.tickets or (project_id, token) in self.retired:
                raise UploadStorageError("upload_token_reused", "This upload token is already in use. Retry with a new token.")
            if len(self.tickets) >= MAX_TICKETS or len(self.retired) >= 512:
                raise UploadStorageError("too_many_uploads", "Too many imports are pending. Finish or cancel an import and try again.", 429)
            if any(t.project_id == project_id and (purpose == "asset" or t.purpose == "asset" or t.slot == slot) for t in self.tickets.values()):
                raise UploadStorageError("project_busy", "An import is already pending for this project or source.")
            facts = self.require(size, data_path=project_root / "media")
            identity = uuid.uuid4().hex
            path = project_root / "media" / f".incoming-{identity}"
            if path.exists() or path.is_symlink():
                raise UploadStorageError("upload_conflict", "The staging reservation changed. Try importing again.")
            ticket = UploadTicket(project_id, token, purpose, slot, filename, size, path)
            try:
                self._journal(ticket, identity)
            except OSError as error:
                if is_storage_full(error):
                    raise self.storage_error(ticket) from error
                raise
            self.tickets[project_id, token] = ticket
            self._schedule()
            return ticket, facts

    def get(self, project_id: str, token: str) -> UploadTicket:
        with self.lock:
            self.prune()
            ticket = self.tickets.get((project_id, token))
            if ticket is None or ticket.cancelled:
                raise UploadStorageError("upload_expired", "The upload was cancelled or expired. Choose the file again.")
            return ticket

    def active_for_project(self, project_id: str, *, exclude_token: str = "") -> bool:
        with self.lock:
            self.prune()
            return any(t.project_id == project_id and t.token != exclude_token for t in self.tickets.values())

    def append(self, project_id: str, token: str, offset: int, length: int, stream: BinaryIO, *, transport_lease: str = "") -> int:
        with self.lock:
            ticket = self.get(project_id, token)
            own_transport = bool(transport_lease and transport_lease == ticket.transport_lease)
            if ticket.busy or ticket.finalizing or ticket.transport_busy and not own_transport:
                raise UploadStorageError("upload_busy", "This upload already has a request in progress.")
            if offset != ticket.received:
                raise UploadStorageError("upload_offset_mismatch", "The upload offset changed. Retry the file import.", received_bytes=ticket.received)
            if not 0 < length <= CHUNK_BYTES or offset + length > ticket.size:
                raise UploadStorageError("invalid_upload_chunk", "The upload chunk size is invalid.", 413)
            # The admitted Waitress request has already allocated its entire
            # bounded TEMP buffer. Charge it once, at headers, not again here.
            self.require(ticket.size - ticket.received, exclude=ticket, data_path=ticket.path.parent,
                         chunk_buffer_bytes=0 if own_transport else CHUNK_BYTES)
            ticket.busy = True
            ticket.updated = time.monotonic()
        try:
            ticket.path.parent.mkdir(parents=True, exist_ok=True)
            with ticket.path.open("r+b" if ticket.path.exists() else "xb") as handle:
                handle.seek(offset)
                count = 0
                while count < length:
                    if ticket.cancelled:
                        raise UploadStorageError("upload_cancelled", "The upload was cancelled.")
                    chunk = stream.read(min(1024**2, length - count))
                    if not chunk:
                        raise UploadStorageError("upload_incomplete", "The transfer ended before this chunk was complete.", 400)
                    handle.write(chunk)
                    count += len(chunk)
                handle.flush()
                if offset + count == ticket.size:
                    # Publish metadata only after the complete original has
                    # reached the filesystem; interrupted prefixes stay owned.
                    os.fsync(handle.fileno())
            with self.lock:
                ticket.received += count
                ticket.updated = time.monotonic()
                return ticket.received
        except BaseException as error:
            with self.lock:
                ticket.cancelled = True
            if is_storage_full(error):
                raise self.storage_error(ticket) from error
            raise
        finally:
            with self.lock:
                ticket.busy = False
                if ticket.cancelled:
                    self._remove(ticket)

    def begin_transport(self, project_id: str, token: str, offset: int, length: int) -> tuple[UploadTicket, str]:
        with self.lock:
            ticket = self.get(project_id, token)
            if ticket.transport_busy or ticket.busy or ticket.finalizing:
                raise UploadStorageError("upload_busy", "This upload already has a transfer in progress.")
            if offset != ticket.received:
                raise UploadStorageError("upload_offset_mismatch", "The upload offset changed. Retry the file import.", received_bytes=ticket.received)
            if not 0 < length <= CHUNK_BYTES or offset + length > ticket.size:
                raise UploadStorageError("invalid_upload_chunk", "The upload chunk size is invalid.", 413)
            self.require(ticket.size - ticket.received, exclude=ticket, data_path=ticket.path.parent)
            ticket.transport_busy = True
            ticket.transport_lease = uuid.uuid4().hex
            ticket.updated = time.monotonic()
            return ticket, ticket.transport_lease

    def end_transport(self, ticket: UploadTicket, lease: str) -> None:
        with self.lock:
            if ticket.transport_lease != lease:
                return
            ticket.transport_busy = False
            ticket.transport_lease = ""
            if ticket.cancelled and not ticket.busy:
                self._remove(ticket)

    def begin_finalize(self, project_id: str, token: str, purpose: str, slot: str | None) -> UploadTicket:
        with self.lock:
            ticket = self.get(project_id, token)
            if ticket.purpose != purpose or ticket.slot != slot:
                raise UploadStorageError("upload_target_mismatch", "The upload belongs to another import target.")
            if ticket.busy or ticket.finalizing or ticket.transport_busy:
                raise UploadStorageError("upload_busy", "This upload already has a request in progress.")
            if ticket.received != ticket.size or not ticket.path.is_file() or ticket.path.stat().st_size != ticket.size:
                raise UploadStorageError("upload_incomplete", "The file transfer is incomplete.")
            # The original is already present; installation only renames on this volume.
            self.require(0, exclude=ticket, data_path=ticket.path.parent, chunk_buffer_bytes=0)
            ticket.busy = ticket.finalizing = True
            return ticket

    def finish(self, ticket: UploadTicket) -> None:
        with self.lock:
            ticket.busy = False
            self._remove(ticket)

    def cancel(self, project_id: str, token: str) -> bool:
        with self.lock:
            self.prune()
            if not TOKEN_RE.fullmatch(token):
                raise UploadStorageError("invalid_upload_token", "The upload token is invalid.", 400)
            ticket = self.tickets.get((project_id, token))
            if ticket is None:
                if (project_id, token) not in self.retired and len(self.retired) >= 512:
                    raise UploadStorageError("too_many_uploads", "Too many cancelled imports. Try again shortly.", 429)
                self.retired[project_id, token] = time.monotonic()
                return False
            ticket.cancelled = True
            if not ticket.busy and not ticket.transport_busy:
                self._remove(ticket)
            return True

    def admit_legacy(self, size: int, *, before_transport: bool = False, data_path: Path | None = None) -> str:
        with self.lock:
            if len(self.legacy) >= 8:
                raise UploadStorageError("too_many_uploads", "Too many transfers are active. Try again shortly.", 429)
            self.require(size, "multipart", transport_buffer_bytes=size if before_transport else 0, data_path=data_path)
            key = uuid.uuid4().hex
            needs = self._needs(size, "multipart", data_path)
            if before_transport:
                volume = filesystem_id(self.temp_dir)
                needs[volume] = needs.get(volume, 0) + size
            self.legacy[key] = needs
            return key

    def credit_transport(self, key: str, count: int) -> None:
        with self.lock:
            needs = self.legacy.get(key)
            if needs is not None:
                volume = filesystem_id(self.temp_dir)
                needs[volume] = max(0, needs.get(volume, 0) - count)

    def release_legacy(self, key: str) -> None:
        with self.lock:
            self.legacy.pop(key, None)

    def close(self) -> None:
        with self.lock:
            self._closed = True
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            for ticket in list(self.tickets.values()):
                ticket.cancelled = True
                if not ticket.busy and not ticket.transport_busy:
                    self._remove(ticket)
