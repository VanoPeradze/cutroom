"""Resume completed negative trials in one exact, bounded canonical search domain.

The caller must fingerprint the original brief, style/config, model, schemas,
pipeline and plan in ``identity``. Complete canonical unit objects and ordered
windows are also included in the key here. Only hashes of that input are saved.
Negative diagnostics remain scoped to a window; DOMAIN_EXHAUSTED means all
supplied windows were visited, never that a story was accepted or that the whole
recording has no editorial fit. The caller must revalidate diagnostic semantics.
"""
from __future__ import annotations

import copy
import json
import math
import os
import threading
import uuid
from enum import Enum
from pathlib import Path
from typing import Any

from .cache_keys import stable_fingerprint
from .story_budget import StoryPlanningError
from .utils import atomic_write_json

CHECKPOINT_VERSION = "canonical-window-search-v1"
MAX_SOURCE_UNITS = 48
MAX_WINDOWS = 48
MAX_SCOPE_BYTES = 4096
MAX_STATE_BYTES = 256 * 1024
_MAX_INPUT_BYTES = 8 * 1024 * 1024
_NEGATIVE_OUTCOMES = frozenset({"no_fit", "budget_miss"})
_PRIVATE_SCOPE_KEYS = frozenset({
    "api_key", "access_token", "refresh_token", "authorization", "password", "secret",
    "credentials", "config", "settings", "instruction", "original_brief", "source_text",
    "text", "transcript", "source_units", "segments", "words",
})


class SearchStatus(str, Enum):
    INCOMPLETE = "incomplete"
    DOMAIN_EXHAUSTED = "domain_exhausted"


class StorySearchCheckpointError(StoryPlanningError):
    def __init__(self, message: str, *, reason: str = "invalid_story_search_checkpoint"):
        super().__init__(message, {"outcome": "technical_error", "reason": reason,
                                  "applied_to_timeline": False})


class CheckpointBusy(StorySearchCheckpointError):
    def __init__(self):
        super().__init__("The exact story search checkpoint already has an owner; no lock was removed.",
                         reason="story_search_checkpoint_busy")


class CheckpointOwnershipError(StorySearchCheckpointError):
    def __init__(self):
        super().__init__("The checkpoint is not owned by this active process and thread.",
                         reason="story_search_checkpoint_ownership")


def _json_copy(value: Any, *, maximum: int, private_scope: bool = False) -> Any:
    def validate(item: Any, depth: int = 0) -> None:
        if depth > 16:
            raise StorySearchCheckpointError("Checkpoint JSON nesting exceeds its bound.")
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float) and math.isfinite(item):
            return
        if isinstance(item, list):
            for child in item:
                validate(child, depth + 1)
            return
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            for key, child in item.items():
                if private_scope and key.casefold().replace("-", "_") in _PRIVATE_SCOPE_KEYS:
                    raise StorySearchCheckpointError("Raw source, config and credentials are not checkpoint scope.")
                validate(child, depth + 1)
            return
        raise StorySearchCheckpointError("Checkpoint inputs must be finite JSON values with string object keys.")

    validate(value)
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False,
                                separators=(",", ":"))
        if len(serialized.encode("utf-8")) > maximum:
            raise StorySearchCheckpointError("Checkpoint JSON exceeds its byte bound.")
        return json.loads(serialized)
    except (TypeError, ValueError, OverflowError, UnicodeError) as exc:
        raise StorySearchCheckpointError("Checkpoint JSON is invalid.") from exc


def _identifier(value: Any) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 160:
        raise StorySearchCheckpointError("A bounded canonical source identifier is required.")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("Duplicate JSON key")
        output[key] = value
    return output


class StorySearchCheckpoint:
    """An exclusive, immediate-fail cursor; no stale lock takeover is attempted.

    ``units`` are complete canonical objects in source order. ``windows`` accepts
    exact contiguous ID lists or lists of those unchanged canonical objects. All
    units must occur in the supplied domain. Use only within its context manager
    on the same process/thread. ``scope`` must contain minimal negative diagnostic
    JSON, at most 4 KiB; it must not contain raw source/config/credentials.
    """

    def __init__(self, cache_dir: Path | str, identity: dict[str, Any],
                 units: list[dict[str, Any]], windows: list[list[Any]]):
        clean_identity = _json_copy(identity, maximum=64 * 1024)
        if not isinstance(clean_identity, dict) or not clean_identity:
            raise StorySearchCheckpointError("A complete nonempty search identity is required.")
        if not isinstance(units, list) or not 1 <= len(units) <= MAX_SOURCE_UNITS:
            raise StorySearchCheckpointError("The canonical search needs 1..48 units; none may be truncated.")
        canonical = _json_copy(units, maximum=_MAX_INPUT_BYTES)
        self._units: dict[str, dict[str, Any]] = {}
        self._positions: dict[str, int] = {}
        previous_start = -1.0
        previous_end = -1.0
        for index, unit in enumerate(canonical):
            if not isinstance(unit, dict):
                raise StorySearchCheckpointError("Canonical search units must be objects.")
            unit_id = _identifier(unit.get("id"))
            if unit_id in self._units:
                raise StorySearchCheckpointError("Canonical search unit IDs must be unique.")
            start, end = unit.get("start"), unit.get("end")
            if (isinstance(start, bool) or isinstance(end, bool)
                    or not isinstance(start, (int, float)) or not isinstance(end, (int, float))
                    or not math.isfinite(start) or not math.isfinite(end)
                    or start < 0 or end <= start or start < previous_start or end < previous_end):
                raise StorySearchCheckpointError("Canonical search clocks must be finite and in source order.")
            if not isinstance(unit.get("text"), str) or not unit["text"].strip():
                raise StorySearchCheckpointError("Canonical search units need their full source text.")
            self._units[unit_id] = unit
            self._positions[unit_id] = index
            previous_start, previous_end = start, end
        if not isinstance(windows, list) or not 1 <= len(windows) <= MAX_WINDOWS:
            raise StorySearchCheckpointError("The search needs 1..48 exact windows; none may be truncated.")
        self._windows = tuple(self._window_key(window) for window in windows)
        if len(set(self._windows)) != len(self._windows):
            raise StorySearchCheckpointError("Duplicate search windows are ambiguous.")
        if {identifier for window in self._windows for identifier in window} != set(self._units):
            raise StorySearchCheckpointError("The supplied search windows omit canonical domain units.")
        self._window_set = frozenset(self._windows)
        self._domain_fingerprint = stable_fingerprint(CHECKPOINT_VERSION + ":domain", self._windows)
        self.fingerprint = stable_fingerprint(CHECKPOINT_VERSION,
            {"identity": clean_identity, "units": canonical, "windows": self._windows})
        self.path = Path(cache_dir) / "story-window-search" / (self.fingerprint + ".json")
        self._lock_dir = self.path.with_suffix(".lock")
        self._owner_path: Path | None = None
        self._owner: dict[str, Any] | None = None
        self._active = False
        self._records: dict[tuple[str, ...], dict[str, Any]] = {}

    def _window_key(self, window: Any) -> tuple[str, ...]:
        if not isinstance(window, (list, tuple)) or not window or len(window) > MAX_SOURCE_UNITS:
            raise StorySearchCheckpointError("A window needs a bounded nonempty ordered canonical ID list.")
        ids = []
        for item in window:
            unit_id = _identifier(item.get("id") if isinstance(item, dict) else item)
            if unit_id not in self._units or (isinstance(item, dict) and item != self._units[unit_id]):
                raise StorySearchCheckpointError("A search window contains a foreign or altered canonical unit.")
            ids.append(unit_id)
        positions = [self._positions[identifier] for identifier in ids]
        if positions != list(range(positions[0], positions[0] + len(positions))):
            raise StorySearchCheckpointError("Search windows must preserve contiguous canonical unit order.")
        return tuple(ids)

    def _domain_key(self, window: Any) -> tuple[str, ...]:
        key = self._window_key(window)
        if key not in self._window_set:
            raise StorySearchCheckpointError("That exact window is outside this checkpoint search domain.")
        return key

    def __enter__(self) -> StorySearchCheckpoint:
        if self._active:
            raise CheckpointOwnershipError()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._lock_dir.mkdir()
        except FileExistsError as exc:
            raise CheckpointBusy() from exc
        owner = {"fingerprint": self.fingerprint, "pid": os.getpid(),
                 "thread": threading.get_ident(), "nonce": uuid.uuid4().hex}
        owner_path = self._lock_dir / ("owner-" + owner["nonce"] + ".json")
        marker_created = False
        try:
            with owner_path.open("x", encoding="utf-8") as handle:
                marker_created = True
                json.dump(owner, handle, sort_keys=True)
            self._owner, self._owner_path, self._active = owner, owner_path, True
            self._records = self._load()
            return self
        except BaseException:
            # Remove only our nonce marker and an otherwise empty owned directory.
            if self._active:
                self.close()
            else:
                if marker_created:
                    owner_path.unlink()
                self._lock_dir.rmdir()
            raise

    def _assert_owner(self) -> None:
        if (not self._active or not self._owner or not self._owner_path
                or self._owner["pid"] != os.getpid() or self._owner["thread"] != threading.get_ident()):
            raise CheckpointOwnershipError()
        try:
            if self._owner_path.stat().st_size > 1024:
                raise ValueError("Invalid owner marker")
            with self._owner_path.open("r", encoding="utf-8") as handle:
                owner = json.load(handle, object_pairs_hook=_unique_object)
            if owner != self._owner:
                raise ValueError("Owner changed")
        except (OSError, ValueError, TypeError, UnicodeError) as exc:
            raise CheckpointOwnershipError() from exc

    def _record(self, window: Any, outcome: Any, scope: Any) -> dict[str, Any]:
        key = self._domain_key(window)
        if not isinstance(outcome, str) or outcome not in _NEGATIVE_OUTCOMES:
            raise StorySearchCheckpointError("Only completed no_fit or budget_miss trials may be checkpointed.")
        if not isinstance(scope, dict):
            raise StorySearchCheckpointError("Completed trial scope must be a diagnostic JSON object.")
        clean_scope = _json_copy(scope, maximum=MAX_SCOPE_BYTES, private_scope=True)
        return {"window_ids": list(key), "outcome": outcome, "scope": clean_scope}

    def _load(self) -> dict[tuple[str, ...], dict[str, Any]]:
        try:
            with self.path.open("rb") as handle:
                raw = handle.read(MAX_STATE_BYTES + 1)
            if len(raw) > MAX_STATE_BYTES:
                return {}
            state = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
            if (not isinstance(state, dict)
                    or set(state) != {"version", "fingerprint", "domain_fingerprint", "trials"}
                    or state["version"] != CHECKPOINT_VERSION or state["fingerprint"] != self.fingerprint
                    or state["domain_fingerprint"] != self._domain_fingerprint
                    or not isinstance(state["trials"], list) or len(state["trials"]) > len(self._windows)):
                return {}
            records = {}
            for item in state["trials"]:
                if not isinstance(item, dict) or set(item) != {"window_ids", "outcome", "scope"}:
                    return {}
                record = self._record(item["window_ids"], item["outcome"], item["scope"])
                key = tuple(record["window_ids"])
                if key in records:
                    return {}
                records[key] = record
            return records
        except (OSError, ValueError, TypeError, UnicodeError, RecursionError, StorySearchCheckpointError):
            # A stale, unreadable or malformed cache provides no reusable trial.
            return {}

    def _persist(self, records: dict[tuple[str, ...], dict[str, Any]]) -> None:
        self._assert_owner()
        state = {"version": CHECKPOINT_VERSION, "fingerprint": self.fingerprint,
                 "domain_fingerprint": self._domain_fingerprint,
                 "trials": [records[key] for key in self._windows if key in records]}
        raw = json.dumps(state, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
        if len(raw) > MAX_STATE_BYTES:
            raise StorySearchCheckpointError("The completed checkpoint exceeds its state byte bound.")
        atomic_write_json(self.path, state)

    def completed(self, window_ids: Any) -> dict[str, Any] | None:
        self._assert_owner()
        return copy.deepcopy(self._records.get(self._domain_key(window_ids)))

    def record(self, window_ids: Any, outcome: str, *, scope: dict[str, Any]) -> dict[str, Any]:
        self._assert_owner()
        record = self._record(window_ids, outcome, scope)
        key = tuple(record["window_ids"])
        if key in self._records:
            if self._records[key] != record:
                raise StorySearchCheckpointError("Discard an old trial before replacing its completed scope.")
            return copy.deepcopy(record)
        updated = {**self._records, key: record}
        self._persist(updated)
        self._records = updated
        return copy.deepcopy(record)

    def discard(self, window_ids: Any) -> bool:
        """Forget one cached negative whose semantic scope the caller rejected."""
        self._assert_owner()
        key = self._domain_key(window_ids)
        if key not in self._records:
            return False
        updated = {old_key: value for old_key, value in self._records.items() if old_key != key}
        self._persist(updated)
        self._records = updated
        return True

    def pending_windows(self) -> list[list[str]]:
        self._assert_owner()
        return [list(key) for key in self._windows if key not in self._records]

    @property
    def status(self) -> SearchStatus:
        self._assert_owner()
        return SearchStatus.DOMAIN_EXHAUSTED if len(self._records) == len(self._windows) else SearchStatus.INCOMPLETE

    def close(self) -> None:
        if not self._active:
            return
        self._assert_owner()
        assert self._owner_path is not None
        self._owner_path.unlink()
        self._active = False
        # rmdir never removes a foreign replacement owner or its contents.
        try:
            self._lock_dir.rmdir()
        except OSError as exc:
            raise CheckpointOwnershipError() from exc

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()
