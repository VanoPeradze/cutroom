"""Prepare a source-pinned stabilization copy as an ordinary local media asset."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .jobs import JobCancelled
from .media_library import ASSET_ID_RE, MediaLibraryError, prepare_asset, probe_asset, safe_asset_path
from .stabilization import StabilizationError, stabilize_video


SOURCE_CHANGED_MESSAGE = "The original source changed or is unavailable. Start a new stabilized copy from the current source."


def pinned_stabilization_source(project_dir: Path, project: dict[str, Any], descriptor: Any) -> Path:
    """Validate the same source generation and file before publishing a copy."""
    if not isinstance(descriptor, dict) or descriptor.get("slot") not in {"A", "B"}:
        raise StabilizationError(SOURCE_CHANGED_MESSAGE)
    source = (project.get("sources") or {}).get(descriptor["slot"]) or {}
    relative = descriptor.get("relative_path")
    if (not isinstance(relative, str) or not relative
            or not descriptor.get("generation")
            or source.get("generation") != descriptor["generation"]
            or source.get("relative_path") != relative):
        raise StabilizationError(SOURCE_CHANGED_MESSAGE)
    root = project_dir.resolve()
    path = (root / relative.replace("\\", "/")).resolve()
    fingerprint = descriptor.get("fingerprint")
    if root not in path.parents or not path.is_file() or not isinstance(fingerprint, dict):
        raise StabilizationError(SOURCE_CHANGED_MESSAGE)
    try:
        stat = path.stat()
    except OSError as exc:
        raise StabilizationError(SOURCE_CHANGED_MESSAGE) from exc
    if fingerprint != {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}:
        raise StabilizationError(SOURCE_CHANGED_MESSAGE)
    return path


class _AssetPreparationContext:
    """Map asset preparation into the final phase and recheck its input at commit."""
    def __init__(self, context, pin_check):
        self.context = context
        self.pin_check = pin_check
        self.progress = .75

    def __getattr__(self, name):
        return getattr(self.context, name)

    def update(self, progress, message):
        self.progress = max(self.progress, .75 + .25 * max(0, min(1, float(progress))))
        self.context.update(self.progress, message)

    def commit(self):
        self.pin_check()
        self.context.commit()


def prepare_stabilized_asset(context, project_id: str, asset_id: str, store, settings) -> dict[str, Any]:
    """Stabilize locally, then build normal preview, thumbnail and measured peaks."""
    generated: list[Path] = []
    try:
        if not ASSET_ID_RE.fullmatch(asset_id):
            raise StabilizationError("This stabilized copy is unavailable; start a new copy.")
        project_dir = store.project_dir(project_id)
        project = store.load(project_id)
        asset = project.get("assets", {}).get(asset_id) or {}
        descriptor = asset.get("_stabilization")
        expected_path = f"media/assets/{asset_id}/stabilized.mp4"
        if asset.get("path") != expected_path:
            raise StabilizationError("This stabilized copy is unavailable; start a new copy.")
        target = safe_asset_path(project_dir, expected_path)

        def pin_check():
            context.check_cancelled()
            return pinned_stabilization_source(project_dir, store.load(project_id), descriptor)

        source = pin_check()
        if any(path.exists() for path in (target, target.parent / "preview.mp4", target.parent / "thumbnail.jpg")):
            # Failed attempts clean their own output. Never overwrite a file that
            # was added independently or a previously completed copy.
            raise StabilizationError("This copy's output already exists. Start a new stabilized copy.")
        stabilize_video(source, target, settings,
                        progress=lambda value, message: context.update(.7 * max(0, min(1, float(value))), message),
                        cancel_check=context.check_cancelled)
        generated.append(target)
        pin_check()
        context.update(.73, "Preparing the stabilized copy for the editor")
        metadata = probe_asset(target, "video", settings)

        def save_metadata(latest):
            pinned_stabilization_source(project_dir, latest, descriptor)
            latest["assets"][asset_id].update(metadata)

        store.update(project_id, save_metadata)
        result = prepare_asset(_AssetPreparationContext(context, pin_check), project_id, asset_id, store, settings)
        context.update(1, "Stabilized copy ready; the original video is unchanged")
        return result
    except Exception as exc:
        if context.committed:
            raise
        cancelled = isinstance(exc, JobCancelled) or context.cancelled
        # These are only the fixed output names belonging to this derived asset;
        # never remove the original source, its folder, or unrelated media.
        for path in generated:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        try:
            store.update(project_id, lambda latest: latest["assets"][asset_id].update(
                status="cancelled" if cancelled else "failed"))
        except Exception:
            pass
        if cancelled:
            raise JobCancelled("Stabilization cancelled; the original video is unchanged.") from exc
        if isinstance(exc, (StabilizationError, MediaLibraryError)):
            raise StabilizationError(str(exc)) from exc
        raise StabilizationError("CUTROOM could not prepare this stabilized copy. Retry it or start a new copy; the original video is unchanged.") from exc
