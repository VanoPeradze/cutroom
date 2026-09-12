from __future__ import annotations

import copy
import json
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from .captions import DEFAULT_CAPTION_SETTINGS
from .config import Settings
from .frame_rates import DEFAULT_EXPORT_FPS
from .utils import atomic_write_json, new_id, now_iso


PROJECT_ID_RE = re.compile(r"project_[0-9a-f]{12}\Z")


class ProjectStateError(RuntimeError):
    """A canonical project directory contains unreadable or mismatched state."""


class ProjectStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._locks_guard = threading.Lock()
        self._project_locks: dict[str, threading.RLock] = {}
        self._deleted_projects_dir = (self.settings.projects_dir.parent / ".deleted-projects").resolve()
        if self._deleted_projects_dir.parent != self.settings.projects_dir.resolve().parent:
            raise ValueError("Deleted-project staging must remain inside CUTROOM's data directory")
        self._deleted_projects_dir.mkdir(parents=True, exist_ok=True)
        for stale in self._deleted_projects_dir.iterdir():
            if stale.is_dir():
                shutil.rmtree(stale, ignore_errors=True)

    def project_dir(self, project_id: str) -> Path:
        if not isinstance(project_id, str) or not PROJECT_ID_RE.fullmatch(project_id):
            raise FileNotFoundError(project_id)
        root = self.settings.projects_dir.resolve()
        candidate = (root / project_id).resolve()
        if candidate.parent != root:
            raise FileNotFoundError(project_id)
        return candidate

    def state_path(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    def _lock_for(self, project_id: str) -> threading.RLock:
        # Validate before retaining a lock key supplied by an API caller.
        directory = self.project_dir(project_id)
        if not directory.is_dir():
            raise FileNotFoundError(project_id)
        with self._locks_guard:
            return self._project_locks.setdefault(project_id, threading.RLock())

    def create(self, name: str = "Untitled project") -> dict[str, Any]:
        project_id = new_id("project")
        directory = self.project_dir(project_id)
        (directory / "media").mkdir(parents=True)
        (directory / "cache").mkdir(parents=True)
        created = now_iso()
        clean_name = str(name or "").strip()[:120] or "Untitled project"
        project: dict[str, Any] = {
            "id": project_id,
            "name": clean_name,
            "version": 5,
            "revision": 1,
            "created_at": created,
            "updated_at": created,
            "language": "auto",
            "sources": {"A": None, "B": None},
            "settings": {
                "edit_style": "smart",
                "goal": "short",
                "aspect": "9:16",
                "pace": "balanced",
                "target_duration": 60,
                "layout": "auto",
                "audio_source": "A",
                "quality": "balanced",
                "resolution": "1080",
                "fps": DEFAULT_EXPORT_FPS,
                "auto_reframe": True,
                "editorial_effects": True,
                "captions": False,
                "burn_captions": True,
                **DEFAULT_CAPTION_SETTINGS,
                "spoken_language": "auto",
                "performance_mode": "auto",
                "audio_cleanup": {
                    "preset": "clean",
                    "silence_action": "shorten",
                    "silence_min_seconds": 0.75,
                    "silence_threshold_dbfs": None,
                    "silence_keep_seconds": 0.30,
                    "max_remove_ratio": 0.28,
                    "quiet_action": "boost",
                    "quiet_gain_db": 3.0,
                    "loud_action": "lower",
                    "loud_gain_db": -3.0,
                    "normalize": True,
                    "target_lufs": -16.0,
                },
            },
            "pre_analysis": {"audio": {}, "vision": {}},
            "analysis": None,
            "draft": None,
            "manual": {
                "cuts": [],
                "keep_ranges": [],
                "camera_plan": [],
                "camera_overrides": [],
                "source_mixer": {"screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A"},
                "crop": {},
            },
            "exports": [],
        }
        try:
            return self.save(project)
        except Exception:
            # A failed first atomic write must not leave a ghost project folder
            # that can confuse repair/listing code later.
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def list(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        root = self.settings.projects_dir.resolve()
        for state in self.settings.projects_dir.glob("*/project.json"):
            try:
                directory = state.parent
                if not PROJECT_ID_RE.fullmatch(directory.name) or directory.resolve().parent != root:
                    continue
                project = json.loads(state.read_text(encoding="utf-8"))
                if not isinstance(project, dict) or project.get("id") != directory.name:
                    continue
                sources = project.get("sources")
                if not isinstance(sources, dict):
                    continue
                updated_at = project.get("updated_at") if isinstance(project.get("updated_at"), str) else ""
                created_at = project.get("created_at") if isinstance(project.get("created_at"), str) else ""
                projects.append({
                    "id": project["id"],
                    "name": project.get("name") if isinstance(project.get("name"), str) else "Untitled project",
                    "updated_at": updated_at,
                    "created_at": created_at,
                    "sources": {
                        slot: (source and {k: source.get(k) for k in ("name", "duration", "width", "height")})
                        for slot, source in sources.items()
                    },
                    "has_draft": bool(project.get("draft")),
                })
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        return sorted(projects, key=lambda item: item.get("updated_at") or "", reverse=True)

    def load(self, project_id: str) -> dict[str, Any]:
        with self._lock_for(project_id):
            return self._load_unlocked(project_id)

    def _load_unlocked(self, project_id: str) -> dict[str, Any]:
        path = self.state_path(project_id)
        if not path.exists():
            raise FileNotFoundError(project_id)
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ProjectStateError(f"Project {project_id} has unreadable state") from exc
        if not isinstance(project, dict) or project.get("id") != project_id:
            raise ProjectStateError(f"Project {project_id} has mismatched state")
        revision = project.get("revision")
        if revision is not None and (isinstance(revision, bool) or not isinstance(revision, int) or revision < 1):
            raise ProjectStateError(f"Project {project_id} has an invalid revision")
        for key in ("sources", "settings", "pre_analysis", "manual"):
            if key in project and not isinstance(project.get(key), dict):
                raise ProjectStateError(f"Project {project_id} has invalid {key}")
        # Old projects predate subtitle appearance controls. Supplying defaults
        # while loading keeps their rendered look unchanged and gives every API
        # consumer one complete settings contract without a destructive migration.
        project_settings = project.setdefault("settings", {})
        project_settings.setdefault("fps", DEFAULT_EXPORT_FPS)
        for key, value in DEFAULT_CAPTION_SETTINGS.items():
            project_settings.setdefault(key, value)
        for key in ("analysis", "draft"):
            if project.get(key) is not None and not isinstance(project.get(key), dict):
                raise ProjectStateError(f"Project {project_id} has invalid {key}")
        if "exports" in project and not isinstance(project.get("exports"), list):
            raise ProjectStateError(f"Project {project_id} has invalid exports")
        project_root = self.project_dir(project_id).resolve()
        sources = project.get("sources") or {}
        for slot, source in sources.items():
            if source is None:
                continue
            if not isinstance(source, dict):
                raise ProjectStateError(f"Project {project_id} has invalid source {slot}")
            for key in ("relative_path", "preview_relative_path"):
                value = source.get(key)
                # Early/legacy drafts and lightweight test/import records can
                # exist before media is attached. Validate every path that is
                # present without rejecting those metadata-only records.
                if value is None:
                    continue
                if not isinstance(value, str) or not value:
                    raise ProjectStateError(f"Project {project_id} has invalid source path")
                portable = value.replace("\\", "/")
                candidate = (project_root / portable).resolve()
                if project_root not in candidate.parents:
                    raise ProjectStateError(f"Project {project_id} has unsafe source path")
                source[key] = portable
        return project

    def save(self, project: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
        project_id = project["id"]
        with self._lock_for(project_id):
            return self._save_unlocked(project, expected_revision)

    def _save_unlocked(self, project: dict[str, Any], expected_revision: int | None = None) -> dict[str, Any]:
        if not isinstance(project, dict) or not isinstance(project.get("id"), str):
            raise ValueError("Project state requires a canonical project id")
        project_id = project["id"]
        self.project_dir(project_id)
        path = self.state_path(project_id)
        current_revision = 0
        if path.exists():
            current = self._load_unlocked(project_id)
            current_revision = int(current.get("revision", 0))
            if expected_revision is not None and current_revision != int(expected_revision):
                raise RuntimeError("revision_conflict")
        candidate = copy.deepcopy(project)
        candidate["updated_at"] = now_iso()
        candidate["revision"] = current_revision + 1 if path.exists() else max(1, int(candidate.get("revision", 1)))
        atomic_write_json(path, candidate)
        return candidate

    def update(
        self,
        project_id: str,
        mutator: Callable[[dict[str, Any]], dict[str, Any] | None],
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Atomically load, mutate and save one project within this process.

        ``mutator`` may edit the supplied dictionary in place and return ``None``,
        or return a replacement dictionary. The optional revision check is held
        under the same per-project lock as the mutation and atomic JSON replace.
        """
        with self._lock_for(project_id):
            project = self._load_unlocked(project_id)
            current_revision = int(project.get("revision", 0))
            if expected_revision is not None and current_revision != int(expected_revision):
                raise RuntimeError("revision_conflict")
            replacement = mutator(project)
            updated = project if replacement is None else replacement
            if not isinstance(updated, dict) or updated.get("id") != project_id:
                raise ValueError("Project mutator must preserve the canonical project id")
            return self._save_unlocked(updated, current_revision)

    def patch(
        self,
        project_id: str,
        patch: dict[str, Any],
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        def apply(project: dict[str, Any]) -> None:
            if "name" in patch:
                project["name"] = str(patch["name"]).strip()[:120] or project["name"]
            if "language" in patch:
                project["language"] = str(patch["language"])
            if isinstance(patch.get("settings"), dict):
                project.setdefault("settings", {}).update(patch["settings"])
            if isinstance(patch.get("manual"), dict):
                project.setdefault("manual", {}).update(patch["manual"])

        return self.update(project_id, apply, expected_revision=expected_revision)

    def delete(self, project_id: str) -> None:
        with self._lock_for(project_id):
            directory = self.project_dir(project_id)
            project = self._load_unlocked(project_id)
            referenced_exports = self._referenced_export_paths(project)
            tombstone = self._deleted_projects_dir / new_id("deleted")
            # Rename first: on Windows this either leaves the complete project in
            # place when a media handle is still open, or atomically removes it
            # from the active project list before recursive cleanup begins.
            directory.replace(tombstone)
            try:
                shutil.rmtree(tombstone)
            except OSError:
                # A closing browser range request may keep one source handle for
                # a moment. The staged directory is retried on the next startup;
                # the active project namespace is never left half-deleted.
                pass
            for path in referenced_exports:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    # The atomic project rename is the deletion boundary. An
                    # exported MP4 may still be open in another Windows player;
                    # that best-effort retention cleanup must not turn an already
                    # completed project deletion into a misleading retry error.
                    pass
        with self._locks_guard:
            self._project_locks.pop(project_id, None)

    def _referenced_export_paths(self, project: dict[str, Any]) -> set[Path]:
        root = self.settings.exports_dir.resolve()
        paths: set[Path] = set()
        exports = project.get("exports", [])
        if not isinstance(exports, list):
            return paths
        for record in exports:
            if not isinstance(record, dict):
                continue
            for key in ("name", "relative_path", "captions_name"):
                value = record.get(key)
                if not isinstance(value, str) or not value or "/" in value or "\\" in value:
                    continue
                if value in {".", ".."} or Path(value).name != value:
                    continue
                candidate = root / value
                if candidate.parent.resolve() == root:
                    paths.add(candidate)
        return paths
