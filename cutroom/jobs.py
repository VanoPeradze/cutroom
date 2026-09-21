from __future__ import annotations

import json
import math
import threading
import time
import traceback
from collections import defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from .utils import atomic_write_json, new_id, now_iso


ACTIVE_STATUSES = frozenset({"queued", "running"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


class JobCancelled(RuntimeError):
    pass


class JobAdmissionError(RuntimeError):
    """Raised when accepting more work would exceed a configured queue bound."""

    def __init__(self, message: str, *, code: str = "job_queue_full", active_job_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.active_job_id = active_job_id


@dataclass
class Job:
    id: str
    kind: str
    project_id: str | None
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued"
    result: Any = None
    error: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    dedupe_key: str = "default"
    started_at: str | None = None
    finished_at: str | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "project_id": self.project_id,
            "dedupe_key": self.dedupe_key,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message,
            # Failed jobs retain internal diagnostics, including tracebacks, but
            # the polling API exposes only the user-facing error message.
            "result": None if self.status == "failed" else self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            # Keep the lifecycle status stable while cooperative work winds down,
            # but let clients acknowledge a cancellation request immediately.
            "cancel_requested": self.cancel_event.is_set() or self.status == "cancelled",
        }

    def persistence_record(self) -> dict[str, Any]:
        """Return the deliberately small, non-sensitive restart record."""

        return {
            "id": self.id,
            "kind": self.kind,
            "project_id": self.project_id,
            "dedupe_key": self.dedupe_key,
            "status": self.status,
            "progress": round(self.progress, 3),
            "message": self.message[:240],
            "error": self.error[:500] if self.error else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @classmethod
    def from_persistence_record(cls, record: dict[str, Any]) -> Job:
        job_id = str(record["id"])
        kind = str(record["kind"])
        if not job_id.startswith("job_") or len(job_id) > 80 or not kind or len(kind) > 80:
            raise ValueError("Invalid persisted job identity")
        try:
            progress = float(record.get("progress") or 0.0)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("Invalid persisted job progress") from exc
        if not math.isfinite(progress):
            progress = 0.0
        project_id = str(record["project_id"]) if record.get("project_id") is not None else None
        if project_id is not None and len(project_id) > 80:
            raise ValueError("Invalid persisted project identity")
        return cls(
            id=job_id,
            kind=kind,
            project_id=project_id,
            status=str(record.get("status") or "interrupted"),
            progress=max(0.0, min(1.0, progress)),
            message=str(record.get("message") or "")[:240],
            error=str(record["error"])[:500] if record.get("error") else None,
            created_at=str(record.get("created_at") or now_iso()),
            updated_at=str(record.get("updated_at") or now_iso()),
            dedupe_key=str(record.get("dedupe_key") or "default"),
            started_at=str(record["started_at"]) if record.get("started_at") else None,
            finished_at=str(record["finished_at"]) if record.get("finished_at") else None,
        )


class JobContext:
    def __init__(
        self,
        job: Job,
        lock: threading.Lock,
        on_change_locked: Callable[[Job], None] | None = None,
    ):
        self.job = job
        self.lock = lock
        self._on_change_locked = on_change_locked
        self._committed = False

    @property
    def cancelled(self) -> bool:
        return self.job.cancel_event.is_set() and not self._committed

    @property
    def committed(self) -> bool:
        return self._committed

    def commit(self) -> None:
        """Declare the final mutation boundary after one last cancellation check.

        Once a Draft or export is committed, a cancellation racing in a few
        milliseconds later must not relabel successful work as cancelled.
        """

        with self.lock:
            if self.job.cancel_event.is_set():
                raise JobCancelled("Job cancelled")
            self._committed = True

    def update(self, progress: float, message: str) -> None:
        # Checking before the update prevents cancelled work from presenting fresh
        # progress and then continuing into a filesystem/database mutation.
        self.check_cancelled()
        with self.lock:
            if self.job.cancel_event.is_set() and not self._committed:
                raise JobCancelled("Job cancelled")
            try:
                normalized_progress = float(progress)
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError("Job progress must be a finite number") from exc
            if not math.isfinite(normalized_progress):
                raise ValueError("Job progress must be a finite number")
            self.job.progress = max(0.0, min(1.0, normalized_progress))
            self.job.message = str(message)[:1000]
            self.job.updated_at = now_iso()
            if self._on_change_locked:
                self._on_change_locked(self.job)
        self.check_cancelled()

    def checkpoint(self, message: str | None = None) -> None:
        """Cheap cooperative cancellation point for use before mutations."""

        self.check_cancelled()
        if message is not None:
            with self.lock:
                if self.job.cancel_event.is_set() and not self._committed:
                    raise JobCancelled("Job cancelled")
                self.job.message = str(message)[:1000]
                self.job.updated_at = now_iso()
                if self._on_change_locked:
                    self._on_change_locked(self.job)
        self.check_cancelled()

    def cancellable_wait(self, seconds: float, interval: float = 0.1) -> None:
        """Wait without making cancellation unresponsive."""

        deadline = time.monotonic() + max(0.0, float(seconds))
        while True:
            self.check_cancelled()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            self.job.cancel_event.wait(min(max(0.01, float(interval)), remaining))

    def check_cancelled(self) -> None:
        if self.job.cancel_event.is_set() and not self._committed:
            raise JobCancelled("Job cancelled")


class JobManager:
    BACKGROUND_KINDS = {"prepare_source", "model_install"}

    def __init__(
        self,
        workers: int = 2,
        background_workers: int = 2,
        *,
        max_pending: int = 64,
        per_key_limit: int = 1,
        retention_seconds: float = 24 * 60 * 60,
        max_records: int = 512,
        persistence_path: str | Path | None = None,
        persist_interval: float = 0.5,
    ):
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(workers)), thread_name_prefix="cutroom-foreground")
        self.background_executor = ThreadPoolExecutor(
            max_workers=max(1, int(background_workers)),
            thread_name_prefix="cutroom-background",
        )
        self.max_pending = max(1, int(max_pending))
        self.per_key_limit = max(1, int(per_key_limit))
        self.retention_seconds = max(0.0, float(retention_seconds))
        self.max_records = max(self.max_pending, int(max_records))
        self.persistence_path = Path(persistence_path) if persistence_path else None
        self.persist_interval = max(0.0, float(persist_interval))
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self._futures: dict[str, Future[Any]] = {}
        self._active_by_key: dict[tuple[str | None, str, str], set[str]] = defaultdict(set)
        self._last_persist_monotonic = 0.0
        self.persistence_error: str | None = None
        self._load_persisted_jobs()

    @staticmethod
    def _key(kind: str, project_id: str | None, dedupe_key: str | None) -> tuple[str | None, str, str]:
        return project_id, str(kind), str(dedupe_key or "default")

    @staticmethod
    def _timestamp_epoch(value: str | None) -> float:
        if not value:
            return 0.0
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            return 0.0

    def _load_persisted_jobs(self) -> None:
        if not self.persistence_path or not self.persistence_path.is_file():
            return
        repaired = False
        try:
            payload = json.loads(self.persistence_path.read_text(encoding="utf-8"))
            records = payload.get("jobs", []) if isinstance(payload, dict) else []
            for raw in records:
                if not isinstance(raw, dict):
                    repaired = True
                    continue
                try:
                    job = Job.from_persistence_record(raw)
                except (KeyError, TypeError, ValueError, OverflowError):
                    repaired = True
                    continue
                if job.status in ACTIVE_STATUSES:
                    job.status = "interrupted"
                    job.message = "Interrupted when CUTROOM restarted"
                    job.error = "The application restarted before this job completed."
                    job.updated_at = now_iso()
                    job.finished_at = job.updated_at
                    repaired = True
                elif job.status not in TERMINAL_STATUSES:
                    repaired = True
                    continue
                self.jobs[job.id] = job
            if self._prune_locked():
                repaired = True
            if repaired:
                self._persist_locked(force=True)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # A broken recovery record must never prevent the editor from opening.
            self.persistence_error = f"{type(exc).__name__}: {exc}"

    def _persist_locked(self, *, force: bool = False) -> None:
        if not self.persistence_path:
            return
        now = time.monotonic()
        if not force and now - self._last_persist_monotonic < self.persist_interval:
            return
        payload = {
            "version": 1,
            "updated_at": now_iso(),
            "jobs": [job.persistence_record() for job in self.jobs.values()],
        }
        try:
            atomic_write_json(self.persistence_path, payload)
            self._last_persist_monotonic = now
            self.persistence_error = None
        except (OSError, TypeError, ValueError) as exc:
            # Persistence is recovery assistance, not a reason to fail real work.
            self.persistence_error = f"{type(exc).__name__}: {exc}"

    def _job_changed_locked(self, _job: Job) -> None:
        self._persist_locked(force=False)

    def _remove_active_locked(self, job: Job) -> None:
        key = self._key(job.kind, job.project_id, job.dedupe_key)
        ids = self._active_by_key.get(key)
        if ids is not None:
            ids.discard(job.id)
            if not ids:
                self._active_by_key.pop(key, None)

    def _remove_record_locked(self, job_id: str) -> None:
        job = self.jobs.pop(job_id, None)
        self._futures.pop(job_id, None)
        if job:
            self._remove_active_locked(job)

    def _mark_terminal_locked(self, job: Job, status: str, message: str) -> None:
        job.status = status
        job.message = message
        job.updated_at = now_iso()
        job.finished_at = job.updated_at
        self._remove_active_locked(job)
        self._futures.pop(job.id, None)
        self._prune_locked()
        self._persist_locked(force=True)

    def _prune_locked(self) -> int:
        now = time.time()
        expired = [
            job.id
            for job in self.jobs.values()
            if job.status in TERMINAL_STATUSES
            and now - self._timestamp_epoch(job.finished_at or job.updated_at) > self.retention_seconds
        ]
        for job_id in expired:
            self._remove_record_locked(job_id)

        overflow = max(0, len(self.jobs) - self.max_records)
        if overflow:
            terminal = sorted(
                (job for job in self.jobs.values() if job.status in TERMINAL_STATUSES),
                key=lambda item: (self._timestamp_epoch(item.finished_at or item.updated_at), item.id),
            )
            for job in terminal[:overflow]:
                self._remove_record_locked(job.id)
                expired.append(job.id)
        return len(expired)

    def submit(
        self,
        kind: str,
        project_id: str | None,
        function: Callable[..., Any],
        *args: Any,
        dedupe_key: str | None = None,
        deduplicate: bool = True,
        **kwargs: Any,
    ) -> Job:
        normalized_kind = str(kind)
        normalized_project_id = str(project_id) if project_id is not None else None
        normalized_key = str(dedupe_key or "default")
        if not normalized_kind or len(normalized_kind) > 80:
            raise ValueError("Job kind must be a short non-empty string")
        if normalized_project_id is not None and len(normalized_project_id) > 80:
            raise ValueError("Project id is too long")
        if len(normalized_key) > 240:
            raise ValueError("Job deduplication key is too long")
        kind = normalized_kind
        project_id = normalized_project_id
        key = self._key(kind, project_id, normalized_key)
        executor = self.background_executor if kind in self.BACKGROUND_KINDS else self.executor
        with self.lock:
            self._prune_locked()
            active = [
                self.jobs[job_id]
                for job_id in self._active_by_key.get(key, set())
                if job_id in self.jobs and self.jobs[job_id].status in ACTIVE_STATUSES
            ]
            if deduplicate and active:
                return max(active, key=lambda item: (self._timestamp_epoch(item.created_at), item.id))
            pending_count = sum(job.status in ACTIVE_STATUSES for job in self.jobs.values())
            if pending_count >= self.max_pending:
                raise JobAdmissionError(
                    f"CUTROOM already has {pending_count} active jobs; try again after one finishes.",
                    code="job_queue_full",
                )
            if len(active) >= self.per_key_limit:
                active_job = max(active, key=lambda item: (self._timestamp_epoch(item.created_at), item.id))
                raise JobAdmissionError(
                    f"A {kind} job is already active for this project.",
                    code="job_conflict",
                    active_job_id=active_job.id,
                )

            job = Job(new_id("job"), kind, project_id, dedupe_key=normalized_key)
            self.jobs[job.id] = job
            self._active_by_key[key].add(job.id)
            try:
                # The manager lock is intentionally held until the Future is saved.
                # _run takes the same lock before user code, closing the cancellation
                # race between executor.submit() and the caller receiving the Job.
                future = executor.submit(self._run, job, function, args, kwargs)
            except Exception:
                self._remove_record_locked(job.id)
                raise
            self._futures[job.id] = future
            self._persist_locked(force=True)
            return job

    def _run(self, job: Job, function: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        context = JobContext(job, self.lock, self._job_changed_locked)
        with self.lock:
            if job.cancel_event.is_set():
                self._mark_terminal_locked(job, "cancelled", "Cancelled")
                return
            job.status = "running"
            job.started_at = now_iso()
            job.updated_at = job.started_at
            job.message = "Running"
            self._persist_locked(force=True)
        try:
            context.checkpoint()
            result = function(context, *args, **kwargs)
            context.checkpoint()
            with self.lock:
                if context.committed:
                    job.cancel_event.clear()
                job.progress = 1.0
                job.result = result
                self._mark_terminal_locked(job, "completed", "Completed")
        except JobCancelled:
            with self.lock:
                self._mark_terminal_locked(job, "cancelled", "Cancelled")
        except Exception as exc:  # noqa: BLE001 - job boundary
            with self.lock:
                job.error = f"{type(exc).__name__}: {exc}"
                job.result = {"traceback": traceback.format_exc(limit=8)}
                self._mark_terminal_locked(job, "failed", "Failed")

    def get(self, job_id: str) -> Job | None:
        with self.lock:
            removed = self._prune_locked()
            if removed:
                self._persist_locked(force=True)
            return self.jobs.get(job_id)

    def list(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
        statuses: Iterable[str] | None = None,
        dedupe_key: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        allowed = set(statuses) if statuses is not None else None
        with self.lock:
            removed = self._prune_locked()
            if removed:
                self._persist_locked(force=True)
            rows = [
                job
                for job in self.jobs.values()
                if (project_id is None or job.project_id == project_id)
                and (kind is None or job.kind == kind)
                and (allowed is None or job.status in allowed)
                and (dedupe_key is None or job.dedupe_key == str(dedupe_key))
            ]
            rows.sort(
                key=lambda item: (
                    self._timestamp_epoch(item.updated_at),
                    self._timestamp_epoch(item.created_at),
                    item.id,
                ),
                reverse=True,
            )
            return rows[: max(1, min(500, int(limit)))]

    def active(self, *, project_id: str | None = None, kind: str | None = None, limit: int = 100) -> list[Job]:
        return self.list(project_id=project_id, kind=kind, statuses=ACTIVE_STATUSES, limit=limit)

    def find_active(self, project_id: str | None, kind: str, dedupe_key: str | None = None) -> Job | None:
        rows = self.list(
            project_id=project_id,
            kind=kind,
            statuses=ACTIVE_STATUSES,
            dedupe_key=str(dedupe_key or "default"),
            limit=1,
        )
        return rows[0] if rows else None

    def latest(self, project_id: str | None, kind: str, dedupe_key: str | None = None) -> Job | None:
        rows = self.list(project_id=project_id, kind=kind, dedupe_key=dedupe_key, limit=1)
        return rows[0] if rows else None

    def recovery_snapshot(self, project_id: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        """Recent jobs a refreshed browser can use to resume polling or reconcile."""

        return [job.public() for job in self.list(project_id=project_id, limit=limit)]

    def cancel(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if not job or job.status in TERMINAL_STATUSES:
                return False
            job.cancel_event.set()
            future = self._futures.get(job_id)
            if job.status == "queued" and future is not None and future.cancel():
                self._mark_terminal_locked(job, "cancelled", "Cancelled")
                return True
            job.message = "Cancelling"
            job.updated_at = now_iso()
            self._persist_locked(force=True)
            return True

    def cancel_active(
        self,
        *,
        project_id: str | None = None,
        kind: str | None = None,
        dedupe_key: str | None = None,
    ) -> list[str]:
        rows = self.list(
            project_id=project_id,
            kind=kind,
            statuses=ACTIVE_STATUSES,
            dedupe_key=dedupe_key,
            limit=self.max_pending,
        )
        return [job.id for job in rows if self.cancel(job.id)]

    def cancel_project(self, project_id: str) -> list[str]:
        return self.cancel_active(project_id=project_id)

    def prune(self) -> int:
        with self.lock:
            removed = self._prune_locked()
            if removed:
                self._persist_locked(force=True)
            return removed

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        if cancel_pending:
            for job in self.active(limit=self.max_pending):
                self.cancel(job.id)
        self.executor.shutdown(wait=wait, cancel_futures=cancel_pending)
        self.background_executor.shutdown(wait=wait, cancel_futures=cancel_pending)
