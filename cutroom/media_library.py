"""Local media assets and non-destructive, edit-clock overlay clips."""
from __future__ import annotations

import array
import copy
import json
import math
import re
import stat
import sys
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any

from .media import VIDEO_EXTENSIONS, MediaProbeUnavailableError, run_command
from .jobs import JobCancelled
from .sequence import editor_sequence_snapshot, materialize_sequence
from .source_tracks import MAX_SEQUENCE_SECONDS
from .native_paths import native_io_path
from .working_storage import WorkingStorageError, preparation_bytes, require_working_space
from .asset_preparation import (
    PreparationBusy, PreparationCache, PreparationCacheError, assert_source_unchanged,
    preparation_lock, source_identity,
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
ASSET_ID_RE = re.compile(r"asset_[0-9a-f]{32}\Z")
MAX_ASSETS = 100
MAX_MEDIA_CLIPS = 200
MAX_ASSET_SECONDS = 4 * 3600
# Large originals use a validated direct preview instead of an unbounded proxy
# conversion. This is a preparation policy, not a video upload size limit.
DIRECT_VIDEO_PREVIEW_BYTES = 2 * 1024**3
CLIP_FIELDS = {"start", "end", "source_start", "speed", "volume_db", "muted", "role", "fade_in", "fade_out", "x", "y", "w", "h", "fit", "motion", "audio_enabled"}
AUDIO_MIXER_DEFAULTS = {
    "source_db": 0.0, "music_db": 0.0, "effects_db": 0.0, "voice_db": 0.0, "master_db": 0.0,
    "source_muted": False, "music_muted": False, "effects_muted": False, "voice_muted": False,
    "ducking": False,
}
MEDIA_ACTION_FIELDS = {
    "media_add": {"asset_id", "track_id", *CLIP_FIELDS},
    "media_append": {"asset_id", "source_start", "source_end", "track_id"},
    "media_insert": {"asset_id", "source_start", "source_end", "start", "track_id"},
    "media_update": {"clip_id", *CLIP_FIELDS},
    "media_remove": {"clip_id"},
    "media_duplicate": {"clip_id", "start"},
    "media_split": {"clip_id", "time"},
    "media_trim": {"clip_id", "edge", "time"},
    "media_roll": {"left_id", "right_id", "frame"},
    "media_slide": {"left_id", "clip_id", "right_id", "frame"},
    "media_track_overwrite": {"asset_id", "track_id", "source_start", "source_end", "frame"},
    "media_track_lift": {"track_id", "start_frame", "end_frame"},
    "media_replace_take": {"clip_id", "previous_asset_id", "asset_id", "source_start", "source_end"},
    "media_slip": {"clip_id", "source_start"},
    "media_move": {"clip_id", "start"},
    "media_reorder": {"clip_id", "position"},
    "media_set_enabled": {"clip_id", "enabled"},
    "media_set_opacity": {"clip_id", "opacity_percent"},
    "media_transform": {"clip_id", "x", "y", "w", "h"},
    "set_audio_mixer": set(AUDIO_MIXER_DEFAULTS),
}


class MediaLibraryError(ValueError):
    pass


class LargeVideoPreviewError(MediaLibraryError):
    """A fixed, actionable format limitation safe to expose to the editor."""


def number(value: Any, name: str, low: float, high: float) -> float:
    if isinstance(value, bool):
        raise MediaLibraryError(f"{name} must be a finite number")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MediaLibraryError(f"{name} must be a finite number") from exc
    if not math.isfinite(result) or not low <= result <= high:
        raise MediaLibraryError(f"{name} must be between {low:g} and {high:g}")
    return round(result, 9)


def asset_kind(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    raise MediaLibraryError("Choose a supported video, image (PNG/JPEG/WebP/BMP), or audio file")


def asset_size_limit(kind: str, configured_limit: int) -> int:
    return min(configured_limit, {"image": 32 * 1024**2, "audio": 512 * 1024**2, "video": configured_limit}[kind])


def safe_asset_path(project_dir: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise FileNotFoundError("Asset file is unavailable")
    parts = relative.replace("\\", "/").split("/")
    if (parts[:2] != ["media", "assets"] or len(parts) < 3
            or any(part in ("", ".", "..") or ":" in part or "\0" in part for part in parts[2:])):
        raise FileNotFoundError("Invalid asset path")
    assets_root = project_dir.resolve() / "media" / "assets"
    candidate = assets_root.joinpath(*parts[2:])
    try:
        # Existing or future entries must stay under their lexical asset root;
        # neither the asset root nor an intermediate entry can redirect I/O.
        resolved = candidate.resolve()
        if not resolved.is_relative_to(assets_root) or resolved != candidate:
            raise FileNotFoundError("Invalid asset path")
    except (OSError, RuntimeError) as exc:
        raise FileNotFoundError("Invalid asset path") from exc
    return resolved


def _asset_identity(path: Path, matches_mode) -> tuple[int, int]:
    details = path.lstat()
    if path.resolve(strict=True) != path or not matches_mode(details.st_mode):
        raise MediaLibraryError("The local asset destination changed. Import the file again.")
    return details.st_dev, details.st_ino


class AssetUploadReservation:
    """Own exactly one local upload folder and at most one original, never a subtree."""

    def __init__(self, project_dir: Path, asset_id: str, filename: str):
        if not ASSET_ID_RE.fullmatch(asset_id):
            raise MediaLibraryError("The local asset identifier is invalid.")
        suffix = Path(filename).suffix.lower()
        # Match a supported fixed basename; never pass through an uploaded name.
        original = next((f"original{ext}" for ext in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS
                         if ext == suffix), None)
        if original is None:
            raise MediaLibraryError("Unsupported local asset format.")
        self.relative = f"media/assets/{asset_id}/{original}"
        self.path = safe_asset_path(project_dir, self.relative)
        self.folder = self.path.parent
        asset_root = self.folder.parent
        asset_root.mkdir(parents=True, exist_ok=True)
        expected_root = _asset_identity(asset_root, stat.S_ISDIR)
        try:
            self.folder.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise MediaLibraryError("The local asset destination is already reserved. Import the file again.") from exc
        self._folder_identity = _asset_identity(self.folder, stat.S_ISDIR)
        self._original_identity = None
        if _asset_identity(asset_root, stat.S_ISDIR) != expected_root:
            raise MediaLibraryError("The local asset destination changed. Import the file again.")

    def _require_folder(self) -> None:
        if _asset_identity(self.folder, stat.S_ISDIR) != self._folder_identity:
            raise MediaLibraryError("The local asset destination changed. Import the file again.")

    def new_original_path(self) -> Path:
        self._require_folder()
        if self.path.exists() or self.path.is_symlink():
            raise MediaLibraryError("The local asset destination is no longer empty. Import the file again.")
        return self.path

    def record_original(self) -> None:
        self._require_folder()
        self._original_identity = _asset_identity(self.path, stat.S_ISREG)

    def discard(self) -> None:
        # No recursive cleanup: a replaced folder or unowned file remains intact.
        try:
            self._require_folder()
            if self._original_identity is not None and _asset_identity(self.path, stat.S_ISREG) == self._original_identity:
                self.path.unlink()
            self.folder.rmdir()
        except (OSError, RuntimeError, MediaLibraryError):
            pass


def _picture_end(video, container, duration):
    """End of the primary picture on FFmpeg's container-relative clock, or unknown."""
    def finite(value):
        try:
            result = float(value)
            return result if math.isfinite(result) else None
        except (TypeError, ValueError, OverflowError):
            return None

    stream_start, file_start = finite(video.get("start_time")), finite(container.get("start_time"))
    if stream_start is None or file_start is None:
        return None
    span = finite(video.get("duration"))
    if span is None or span <= 0:
        try:
            span = float(int(video["duration_ts"]) * Fraction(video["time_base"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
            # Matroska/WebM often exposes no stream duration. At a zero origin
            # its track DURATION is unambiguous. Lavf writes an absolute stream-end
            # timestamp even for delayed streams: subtract the FILE start only.
            formats = str(container.get("format_name") or "").split(",")
            tags = video.get("tags") if isinstance(video.get("tags"), dict) else {}
            container_tags = container.get("tags") if isinstance(container.get("tags"), dict) else {}
            muxer = str(container_tags.get("ENCODER") or container_tags.get("encoder") or "")
            stamp = re.fullmatch(r"(\d{2,6}):([0-5]\d):([0-5]\d)(?:\.(\d{1,9}))?", str(tags.get("DURATION") or ""))
            if not (stamp and ("matroska" in formats or "webm" in formats)
                    and (stream_start == file_start == 0 or muxer.startswith("Lavf"))):
                return None
            h, m, s, fraction = stamp.groups()
            file_end = int(h)*3600 + int(m)*60 + int(s) + float("0." + (fraction or "0"))
            span = file_end - stream_start
    end = stream_start - file_start + span
    return round(min(duration, end), 9) if math.isfinite(end) and span > 0 and end > 1e-6 else None


def probe_asset(path: Path, kind: str, settings, *, cancel_check=None, include_codecs=False) -> dict[str, Any]:
    try:
        result = run_command([
            settings.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams",
            "-print_format", "json", str(path.absolute()),
        ], timeout=30, **({"cancel_check": cancel_check} if cancel_check is not None else {}))
    except (FileNotFoundError, PermissionError) as exc:
        raise MediaProbeUnavailableError() from exc
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    video = next((row for row in streams if row.get("codec_type") == "video" and not (row.get("disposition") or {}).get("attached_pic")), None)
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    if kind in {"video", "image"} and not video or kind == "audio" and (not audio or video):
        raise MediaLibraryError("The file does not contain the selected media type")
    width = int((video or {}).get("width") or 0)
    height = int((video or {}).get("height") or 0)
    if kind != "audio" and (min(width, height) <= 0 or max(width, height) > 16384 or width * height > 64_000_000):
        raise MediaLibraryError("Image/video dimensions are invalid or larger than 64 megapixels")
    duration = 0.0 if kind == "image" else number(
        (data.get("format") or {}).get("duration") or (video or audio or {}).get("duration"), "Media duration", 0.08, MAX_ASSET_SECONDS,
    )
    metadata = {"kind": kind, "duration": duration, "width": width, "height": height, "has_audio": bool(audio) and kind != "image"}
    if kind == "video":
        # The container may continue for voice/music after the last picture packet.
        metadata["picture_end"] = _picture_end(video, data.get("format") or {}, duration)
    if include_codecs:
        metadata.update(video_codec=(video or {}).get("codec_name"), audio_codec=(audio or {}).get("codec_name"))
        rotation = ((video or {}).get("tags") or {}).get("rotate", 0)
        for side_data in (video or {}).get("side_data_list") or []:
            if "rotation" in side_data:
                rotation = side_data["rotation"]
        try:
            rotation = float(rotation) % 360
        except (TypeError, ValueError, OverflowError):
            rotation = None
        metadata.update(format=(data.get("format") or {}).get("format_name"),
                        pixel_format=(video or {}).get("pix_fmt"), rotation=rotation,
                        audio_channels=(audio or {}).get("channels"))
    return metadata


def _original_video_preview_compatible(source: Path, metadata: dict[str, Any]) -> bool:
    return (source.suffix.lower() in {".mp4", ".m4v"}
            and metadata.get("format") == "mov,mp4,m4a,3gp,3g2,mj2"
            and metadata.get("video_codec") == "h264"
            and metadata.get("pixel_format") == "yuv420p"
            and metadata.get("rotation") == 0
            and (not metadata.get("has_audio") or
                 metadata.get("audio_codec") == "aac" and metadata.get("audio_channels") in {1, 2}))


def _build_original_thumbnail(context, source: Path, settings, folder: Path) -> None:
    context.update(0.65, "Creating media thumbnail; using original video for preview")
    run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-threads", "1",
                 "-protocol_whitelist", "file,pipe", "-i", str(source.absolute()), "-map", "0:v:0",
                 "-frames:v", "1", "-an", "-vf", "scale=320:-2", "-threads", "1",
                 str(folder / "thumbnail.jpg")], timeout=60, cancel_check=context.check_cancelled)


def _probe_prepared_asset(path: Path, kind: str, original: dict[str, Any], settings, context) -> dict[str, Any]:
    metadata = probe_asset(path, kind, settings, cancel_check=context.check_cancelled, include_codecs=True)
    # A proxy's picture end is not used to seek the original. Keep existing cache manifests compatible.
    metadata.pop("picture_end", None)
    expected_video = "mjpeg" if path.name == "thumbnail.jpg" else "png" if kind == "image" else "h264" if kind == "video" else None
    if metadata["video_codec"] != expected_video or metadata["has_audio"] and metadata["audio_codec"] != "aac":
        raise MediaLibraryError("Prepared media is not browser compatible")
    if path.name != "thumbnail.jpg":
        if metadata["has_audio"] != bool(original["has_audio"]):
            raise MediaLibraryError("Prepared media is missing its expected audio")
        if kind != "image" and abs(metadata["duration"] - float(original["duration"])) > max(0.5, float(original["duration"]) * 0.0001):
            raise MediaLibraryError("Prepared media does not cover the original duration")
    return metadata


def _build_asset_preview(context, source: Path, asset: dict[str, Any], settings, folder: Path) -> list[float]:
    kind = asset["kind"]
    preview = folder / ("preview.png" if kind == "image" else "preview.m4a" if kind == "audio" else "preview.mp4")
    if kind == "video":
        run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-threads", str(max(1, int(settings.raw.get("ffmpeg_threads", 4)))), "-protocol_whitelist", "file,pipe", "-i", str(source.absolute()), "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-vf", "scale=-2:'min(720,ih)',format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(preview)], timeout=max(180, asset["duration"] * 4), cancel_check=context.check_cancelled)
    else:
        args = [settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source.absolute()), "-map_metadata", "-1"]
        args += ["-frames:v", "1", "-vf", "scale='min(4096,iw)':-1", str(preview)] if kind == "image" else ["-vn", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(preview)]
        run_command(args, timeout=max(90, asset["duration"] * 2), cancel_check=context.check_cancelled)
    if kind in {"video", "image"}:
        context.update(0.65, "Creating media thumbnail")
        run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(preview.absolute()), "-frames:v", "1", "-vf", "scale=320:-2", str(folder / "thumbnail.jpg")], timeout=60, cancel_check=context.check_cancelled)
    waveform: list[float] = []
    if asset["has_audio"]:
        context.update(0.8, "Building audio waveform")
        result = run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(preview.absolute()), "-vn", "-af", "aformat=channel_layouts=mono,aeval=abs(val(0))", "-ac", "1", "-ar", "100", "-f", "s16le", "pipe:1"], text=False, timeout=max(60, asset["duration"]), cancel_check=context.check_cancelled)
        samples = array.array("h")
        samples.frombytes(result.stdout)
        if sys.byteorder != "little":
            samples.byteswap()
        step = max(1, math.ceil(len(samples) / 240))
        peaks = [max(abs(value) for value in samples[index:index + step]) / 32768 for index in range(0, len(samples), step)]
        maximum = max(peaks, default=0)
        waveform = [round(value / maximum, 4) if maximum else 0.0 for value in peaks]
    return waveform


_PREPARATION_BINDING_FIELDS = (
    "status", "path", "kind", "duration", "width", "height", "has_audio",
    "preparation_identity", "preview_path", "thumbnail_path", "preview_mode", "_original_content_proof",
)


class _PreparationStateUnchanged(Exception):
    """Abort a no-op update so it cannot advance the project revision."""


def _record_preparation_failure(store, project_id, asset_id, initial, *, cancelled):
    # Preserve a previously ready binding byte-for-byte on failed refreshes.
    if initial is None or initial.get("status") == "ready":
        return
    status = "cancelled" if cancelled else "failed"

    def failed(project):
        current = project.get("assets", {}).get(asset_id)
        if (not isinstance(current, dict) or current.get("status") == status
                or any(current.get(key) != initial.get(key) for key in _PREPARATION_BINDING_FIELDS)):
            raise _PreparationStateUnchanged()
        current["status"] = status

    try:
        store.update(project_id, failed)
    except Exception:
        # Best-effort status reporting must not replace the original failure.
        pass


def prepare_asset(context, project_id: str, asset_id: str, store, settings, *, repair_binding=None) -> dict[str, Any]:
    initial = None
    lock_acquired = False
    try:
        if not ASSET_ID_RE.fullmatch(asset_id):
            raise MediaLibraryError("Invalid media asset")
        normal_project_dir = store.project_dir(project_id)
        initial = copy.deepcopy(store.load(project_id)["assets"][asset_id])
        folder = native_io_path(safe_asset_path(normal_project_dir, f"media/assets/{asset_id}"))
        project_dir = native_io_path(normal_project_dir)
        with preparation_lock(folder, context.check_cancelled):
            lock_acquired = True
            initial = copy.deepcopy(store.load(project_id)["assets"][asset_id])
            cache = None
            owned = None
            try:
                from .preview_repair import FIELD, original_path, make_proof, admit_proof, PreviewRepairError, preview_version
                if repair_binding is not None and (initial.get("status")!="ready" or any(initial.get(k)!=repair_binding.get(k) for k in _PREPARATION_BINDING_FIELDS)):
                    raise PreviewRepairError("repair_stale","Repair binding changed; nothing was rebuilt")
                source = native_io_path(original_path(normal_project_dir, initial))
                cache = PreparationCache(project_dir, folder, context.check_cancelled,
                                         lambda path, kind: _probe_prepared_asset(path, kind, initial, settings, context))
                if initial.get("kind") not in {"video", "image", "audio"}:
                    raise MediaLibraryError("Invalid media type")
                context.update(0.08, "Checking prepared media")
                key, identity = source_identity(source, initial, settings, context.check_cancelled)
                proof=admit_proof(initial,key,identity) if repair_binding is not None else make_proof(initial,identity)
                measured=probe_asset(source,initial["kind"],settings,cancel_check=context.check_cancelled,
                                         include_codecs=initial["kind"] == "video" and identity["file"]["size"] > DIRECT_VIDEO_PREVIEW_BYTES)
                if any(measured.get(k)!=initial.get(k) for k in ("kind","duration","width","height","has_audio")):
                    if repair_binding is not None:
                        raise PreviewRepairError("original_unverifiable", "Measured original metadata does not match the saved asset; repair refused")
                    raise PreparationCacheError("Original metadata does not match the saved asset")
                original_preview = None
                if initial["kind"] == "video" and identity["file"]["size"] > DIRECT_VIDEO_PREVIEW_BYTES:
                    metadata = measured
                    if any(metadata.get(name) != initial.get(name) for name in ("kind", "duration", "width", "height", "has_audio")):
                        raise PreparationCacheError("Media metadata changed during preparation; retry the import")
                    if not _original_video_preview_compatible(source, metadata):
                        raise LargeVideoPreviewError("For videos larger than 2 GB, import an MP4 copy with H.264 video, standard 8-bit color, AAC mono/stereo audio and no rotation metadata. The original is preserved.")
                    original_preview = initial["path"]
                cache_options = {"original_preview": original_preview} if original_preview is not None else {}
                updates = next((value for directory in cache.directories()
                                if directory.name.startswith("prepared-")
                                and (value := cache.read(directory, key, initial["kind"], **cache_options)) is not None), None)
                reused = updates is not None
                if reused:
                    require_working_space([("prepared media metadata", folder, 1024**2)],
                                          operation="prepared media metadata save")
                if updates is None:
                    cache.cleanup(store.load(project_id))
                    context.check_cancelled()
                    require_working_space([("media preview / thumbnails", folder,
                        preparation_bytes(initial, transcode=original_preview is None))], operation="media preparation")
                    owned = cache.new_stage()
                    context.update(0.12, "Preparing media for the editor")
                    if original_preview is None:
                        waveform = _build_asset_preview(context, source, initial, settings, owned)
                    else:
                        _build_original_thumbnail(context, source, settings, owned)
                        waveform = []
                    assert_source_unchanged(source, identity, context.check_cancelled, content=True)
                    owned, updates = cache.publish(owned, key, initial["kind"], waveform, **cache_options)
                # Validation and cache reuse can both take time. Rehash before
                # binding, then check the same generation again under the lock.
                assert_source_unchanged(source, identity, context.check_cancelled, content=True)
                context.checkpoint()
                def complete(latest):
                    current = latest["assets"][asset_id]
                    if any(current.get(k) != initial.get(k) for k in _PREPARATION_BINDING_FIELDS):
                        raise PreparationCacheError("Media changed during preparation; retry the import")
                    if (native_io_path(safe_asset_path(normal_project_dir, current["path"])) != source
                            or original_preview is not None and native_io_path(normal_project_dir / current["path"]).is_symlink()):
                        raise PreparationCacheError("Media source binding changed during preparation; retry the import")
                    if native_io_path(original_path(normal_project_dir, current)) != source:
                        raise PreviewRepairError("original_unsafe", "Original ownership changed during preparation")
                    assert_source_unchanged(source, identity, context.check_cancelled, content=False)
                    context.commit()
                    if all(current.get(k)==v for k,v in {**updates,FIELD:proof,"status":"ready"}.items()):
                        raise _PreparationStateUnchanged()
                    current.update(updates, status="ready", **{FIELD:proof})
                try:
                    saved = store.update(project_id, complete)
                except _PreparationStateUnchanged:
                    saved = store.load(project_id)
                owned = None
                try:
                    cache.cleanup(saved)
                except (OSError, PreparationCacheError):
                    # A valid current generation remains usable. A later retry
                    # applies the explicit eight-generation bound before work.
                    pass
                return {"project_id": project_id, "asset_id": asset_id, "preparation_reused": reused,
                        "before_preview_version": preview_version(initial),
                        "after_preview_version": preview_version(saved["assets"][asset_id])}
            except Exception as exc:
                cancelled = isinstance(exc, JobCancelled) or context.cancelled
                try:
                    latest = store.load(project_id)
                    if cache is not None and owned is not None and owned.name not in cache.referenced(latest, [owned]):
                        cache.remove_owned(owned)
                except Exception:
                    pass
                _record_preparation_failure(store, project_id, asset_id, initial, cancelled=cancelled)
                raise
    except Exception as exc:
        cancelled = isinstance(exc, JobCancelled) or context.cancelled
        if not lock_acquired and not cancelled and not isinstance(exc, PreparationBusy):
            _record_preparation_failure(store, project_id, asset_id, initial, cancelled=False)
        if isinstance(exc, JobCancelled):
            raise
        if cancelled:
            raise JobCancelled("Job cancelled") from exc
        if repair_binding is not None and isinstance(exc, PreparationCacheError):
            raise
        if isinstance(exc, (LargeVideoPreviewError, WorkingStorageError)):
            raise
        # JobManager exposes str(exc). Keep command/path diagnostics private.
        raise MediaLibraryError("CUTROOM could not prepare this media. Retry the import or choose another file.") from exc


def _boolean(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise MediaLibraryError(f"{name} must be true or false")
    return value


def _edit_duration(project: dict[str, Any]) -> float:
    snapshot = editor_sequence_snapshot(project)
    if not snapshot:
        raise MediaLibraryError("Create a draft before adding timeline media")
    return float(snapshot["duration"])


def validate_clip_opacity(row, asset):
    """An optional occurrence property; sound-only assets never acquire opacity."""
    if "opacity_percent" not in row:
        return 100
    value = row["opacity_percent"]
    if asset.get("kind") not in {"video", "image"}:
        raise MediaLibraryError("Opacity is available only for imported video and image clips")
    if type(value) is not int or not 0 <= value <= 100:
        raise MediaLibraryError("Opacity must be an integer percentage from 0 to 100")
    return value


def validate_media_clip(project: dict[str, Any], row: dict[str, Any], duration: float) -> dict[str, Any]:
    asset = (project.get("assets") or {}).get(row.get("asset_id"))
    if not isinstance(asset, dict) or asset.get("status", "ready") != "ready":
        raise MediaLibraryError("Choose a ready media asset")
    result = copy.deepcopy(row)
    validate_clip_opacity(row, asset)
    if "enabled" in row:
        _boolean(row["enabled"], "enabled")
    for key, bounds in {"start": (0, duration), "end": (0, duration), "source_start": (0, MAX_ASSET_SECONDS), "speed": (0.25, 4), "volume_db": (-60, 12), "fade_in": (0, duration), "fade_out": (0, duration), "x": (0, 1), "y": (0, 1), "w": (0.01, 1), "h": (0.01, 1)}.items():
        result[key] = number(row.get(key), key, *bounds)
    length = result["end"] - result["start"]
    if length < 0.08 - 1e-9:
        raise MediaLibraryError("A media clip must last at least 0.08 seconds")
    if asset["kind"] != "video" and result["speed"] != 1:
        raise MediaLibraryError("Picture speed is available only for video clips")
    if asset["kind"] != "image" and result["source_start"] + length > float(asset["duration"]) + 1e-8:
        raise MediaLibraryError("The clip exceeds the available media duration")
    if asset["kind"] == "video":
        # Audio retains its ordinary clock. Picture can hold the final frame;
        # splitting within that hold preserves the independent picture clock.
        result["video_source_start"] = number(row.get("video_source_start", result["source_start"]), "video_source_start", 0, MAX_ASSET_SECONDS * 4)
    if result["fade_in"] + result["fade_out"] > length + 1e-8:
        raise MediaLibraryError("Audio fades must fit inside the clip")
    if result["x"] + result["w"] > 1 + 1e-8 or result["y"] + result["h"] > 1 + 1e-8:
        raise MediaLibraryError("Position and size must fit inside the frame")
    for key in ("muted", "audio_enabled"):
        result[key] = _boolean(row.get(key), key)
    for key, options in {"role": {"music", "effects", "voice"}, "fit": {"cover", "contain"}, "motion": {"none", "zoom_in", "pan"}}.items():
        if row.get(key) not in options:
            raise MediaLibraryError(f"Invalid {key}")
    return result


def prepare_media_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate a detached edit before the shared history is touched."""
    action = payload["action"]
    if action == "media_reorder" and "layer_tracks" in (project.get("manual") or {}):
        raise MediaLibraryError("Use whole-track ordering for a project with persistent layer tracks")
    if action == "media_append":
        return _prepare_video_append(project, payload)
    if action == "media_insert":
        return _prepare_video_insert(project,payload)
    duration = _edit_duration(project)
    if action == "media_track_lift":
        from .track_lift import prepare_track_lift
        return prepare_track_lift(project, payload, duration)
    if action == "media_track_overwrite":
        from .track_overwrite import prepare_track_overwrite
        return prepare_track_overwrite(project, payload, duration)
    if action == "media_replace_take":
        from .replace_take import prepare_take_replacement
        return prepare_take_replacement(project, payload, duration)
    if action in {"media_roll", "media_slide"}:
        from .rolling_edit import prepare_rolling_edit
        return prepare_rolling_edit(project, payload, duration)
    manual = project.get("manual") or {}
    if action == "set_audio_mixer":
        mixer = {**AUDIO_MIXER_DEFAULTS, **(manual.get("audio_mixer") or {})}
        for key in AUDIO_MIXER_DEFAULTS:
            if key in payload:
                mixer[key] = number(payload[key], key, -60, 12) if key.endswith("_db") else _boolean(payload[key], key)
        return None if mixer == manual.get("audio_mixer") else {"audio_mixer": mixer}
    clips = copy.deepcopy(manual.get("media_clips") or [])
    if action == "media_add":
        asset_id = payload.get("asset_id")
        asset = (project.get("assets") or {}).get(asset_id) if isinstance(asset_id, str) else None
        if not asset:
            raise MediaLibraryError("Choose a media asset from this project")
        start = number(payload.get("start", 0), "start", 0, duration)
        speed = number(payload.get("speed", 1), "speed", .25, 4)
        source_start = number(payload.get("source_start", 0), "source_start", 0, MAX_ASSET_SECONDS)
        available = 5 if asset["kind"] == "image" else float(asset["duration"]) - source_start
        # Newly added footage keeps its attached sound, just like appended
        # footage. Apply this only at creation: saved silent overlays and any
        # explicit audio choice in the request must remain unchanged.
        clip = {"id": "media_" + uuid.uuid4().hex, "asset_id": asset_id,
                "start": start, "end": min(duration, start + available),
                "source_start": source_start, "speed": speed, "volume_db": 0,
                "muted": False, "role": "voice" if asset["kind"] == "video" else "music",
                "fade_in": 0, "fade_out": 0, "x": 0, "y": 0, "w": 1, "h": 1,
                "fit": "cover", "motion": "none",
                "audio_enabled": asset["kind"] == "audio" or
                                 asset["kind"] == "video" and bool(asset.get("has_audio"))}
        clip.update({key: payload[key] for key in CLIP_FIELDS if key in payload})
        clips.append(validate_media_clip(project, clip, duration))
    else:
        clip = next((row for row in clips if row.get("id") == payload.get("clip_id")), None)
        if clip is None:
            raise MediaLibraryError("The selected media clip no longer exists")
        index = clips.index(clip)
        if action == "media_remove":
            clips.pop(index)
        elif action == "media_set_opacity":
            asset = (project.get("assets") or {}).get(clip.get("asset_id"))
            if not isinstance(asset, dict) or asset.get("id") != clip.get("asset_id") or asset.get("kind") not in {"video", "image"} or asset.get("status") != "ready":
                raise MediaLibraryError("Choose a ready imported video or image occurrence")
            opacity = validate_clip_opacity({"opacity_percent": payload.get("opacity_percent")}, asset)
            validate_media_clip(project, clip, duration)
            if opacity == validate_clip_opacity(clip, asset):
                return None
            if opacity == 100:
                clip.pop("opacity_percent", None)
            else:
                clip["opacity_percent"] = opacity
        elif action == "media_set_enabled":
            enabled = _boolean(payload.get("enabled"), "enabled")
            current = _boolean(clip.get("enabled", True), "enabled")
            # Disabling can silence an unavailable occurrence without deleting
            # its data. Re-enabling must satisfy the ordinary media contract.
            if enabled:
                validate_media_clip(project, clip, duration)
            if enabled == current:
                return None
            if enabled:
                clip.pop("enabled", None)
            else:
                clip["enabled"] = False
        elif action == "media_reorder":
            position = payload.get("position")
            if position not in ("backward", "forward", "back", "front"):
                raise MediaLibraryError("Choose backward, forward, back or front for visual stacking")
            # Only permute occupied visual slots. Audio-only rows keep their
            # exact slots; every occurrence keeps its identity/content/clock.
            assets = project.get("assets") or {}
            if any(not isinstance(assets.get(row.get("asset_id")), dict) or
                   assets[row["asset_id"]].get("kind") not in ("video", "image", "audio") for row in clips):
                raise MediaLibraryError("A timeline asset is missing; restore it before changing visual stacking")
            if len({row.get("id") for row in clips}) != len(clips):
                raise MediaLibraryError("Timeline media identifiers must be unique")
            for row in clips:
                validate_media_clip(project, row, duration)
            slots = [i for i, row in enumerate(clips) if assets[row["asset_id"]]["kind"] in ("video", "image")]
            if index not in slots:
                raise MediaLibraryError("Visual stacking is only for imported video and images, not audio or text")
            old = slots.index(index)
            destination = {"backward": max(0, old - 1), "forward": min(len(slots) - 1, old + 1),
                           "back": 0, "front": len(slots) - 1}[position]
            if destination == old:
                return None
            visuals = [clips[i] for i in slots]
            visuals.insert(destination, visuals.pop(old))
            for i, row in zip(slots, visuals):
                clips[i] = row
        elif action == "media_transform":
            asset = (project.get("assets") or {}).get(clip.get("asset_id"))
            if not isinstance(asset, dict) or asset.get("kind") not in ("video", "image"):
                raise MediaLibraryError("Viewer framing is available for imported video and images only")
            if any(isinstance(clip.get(key), bool) or not isinstance(clip.get(key), (int, float))
                   or not math.isfinite(clip[key]) for key in ("x", "y", "w", "h")):
                raise MediaLibraryError("The saved frame geometry is invalid; reload or repair the clip before framing")
            geometry = {key: number(payload.get(key), key, 0.01 if key in ("w", "h") else 0, 1)
                        for key in ("x", "y", "w", "h")}
            checked = validate_media_clip(project, {**clip, **geometry}, duration)
            if all(abs(checked[key] - clip[key]) <= 1e-9 for key in geometry):
                return None
            # This explicit frame action changes only geometry. Validation must
            # not normalize unrelated timing, audio clocks, fades or metadata.
            clip.update({key: checked[key] for key in geometry})
        elif action == "media_move":
            start = number(payload.get("start"), "start", 0, duration)
            candidate = {**clip, "start": start,
                         "end": round(start + clip["end"] - clip["start"], 9)}
            checked = validate_media_clip(project, candidate, duration)
            if abs(start - clip["start"]) <= 1e-9:
                return None
            clips[index] = checked
        elif action == "media_update":
            candidate = {**clip, **{key: payload[key] for key in CLIP_FIELDS if key in payload}}
            asset = project["assets"][clip["asset_id"]]
            if asset["kind"] == "video" and "source_start" in payload:
                source_start = number(payload["source_start"], "source_start", 0, MAX_ASSET_SECONDS)
                candidate["video_source_start"] = round(clip.get("video_source_start", clip["source_start"]) + (source_start - clip["source_start"]) * clip["speed"], 9)
                if candidate["video_source_start"] < 0:
                    raise MediaLibraryError("No earlier picture frames are available here; the independent picture clock cannot be clamped")
            clips[index] = validate_media_clip(project, candidate, duration)
        elif action == "media_duplicate":
            start = number(payload.get("start", clip["start"]), "start", 0, duration)
            duplicate = {**clip, "id": "media_" + uuid.uuid4().hex, "start": start, "end": start + clip["end"] - clip["start"]}
            clips.append(validate_media_clip(project, duplicate, duration))
        elif action == "media_slip":
            checked = validate_media_clip(project, clip, duration)
            kind = project["assets"][clip["asset_id"]]["kind"]
            if kind not in ("video", "audio"):
                raise MediaLibraryError("Slip changes source content inside imported video or audio, not still images or text")
            source_start = number(payload.get("source_start"), "Source in", 0, MAX_ASSET_SECONDS)
            delta = source_start - checked["source_start"]
            if abs(delta) <= 1e-9:
                return None
            candidate = {**checked, "source_start": source_start}
            if kind == "video":
                candidate["video_source_start"] = round(checked["video_source_start"] + delta * checked["speed"], 9)
                if candidate["video_source_start"] < 0:
                    raise MediaLibraryError("No earlier picture frames are available here; the independent picture clock cannot be clamped")
            # Timeline endpoints, envelope and motion phase do not change. This
            # chooses different source content, not a trim, move or speed edit.
            clips[index] = validate_media_clip(project, candidate, duration)
        elif action == "media_trim":
            edge = payload.get("edge")
            if edge not in ("start", "end"):
                raise MediaLibraryError("Choose the start or end edge")
            checked = validate_media_clip(project, clip, duration)
            time = number(payload.get("time"), "time", 0, duration)
            delta = time - checked[edge]
            if abs(delta) <= 1e-9:
                return None
            candidate = {**checked, edge: time}
            if candidate["end"] - candidate["start"] < .08 - 1e-9:
                raise MediaLibraryError("Keep at least 0.08 seconds in the selected clip")
            kind = project["assets"][clip["asset_id"]]["kind"]
            if kind != "audio" and checked["motion"] != "none":
                raise MediaLibraryError("Trimming this pan/zoom clip would change its motion phase. "
                                        "Turn off motion or keep its edges intact; nothing was trimmed.")
            shortening = delta > 0 if edge == "start" else delta < 0
            fade = "fade_in" if edge == "start" else "fade_out"
            if shortening:
                if time - checked["start"] < checked["fade_in"] - 1e-9 or checked["end"] - time < checked["fade_out"] - 1e-9:
                    raise MediaLibraryError("The trim point is inside a media audio fade. "
                                            "Choose a point outside the fade; nothing was trimmed.")
                candidate[fade] = 0
            elif checked[fade] > 1e-9:
                raise MediaLibraryError("Extending this faded edge would move its original audio envelope. "
                                        "Remove that edge's fade first or keep the edge intact; nothing was trimmed.")
            if edge == "start" and kind != "image":
                candidate["source_start"] = round(checked["source_start"] + delta, 9)
                if candidate["source_start"] < 0:
                    raise MediaLibraryError("No earlier source footage is available at this trim point")
                if kind == "video":
                    candidate["video_source_start"] = round(checked["video_source_start"] + delta * checked["speed"], 9)
                    if candidate["video_source_start"] < 0:
                        raise MediaLibraryError("No earlier picture frames are available at this trim point; the independent picture clock cannot be clamped")
            clips[index] = validate_media_clip(project, candidate, duration)
        elif action == "media_split":
            checked = validate_media_clip(project, clip, duration)
            time = number(payload.get("time"), "time", checked["start"] + .08, checked["end"] - .08)
            before, after = time - checked["start"], checked["end"] - time
            kind = project["assets"][clip["asset_id"]]["kind"]
            if kind != "audio" and checked["motion"] != "none":
                raise MediaLibraryError("Splitting this animated pan/zoom clip would restart its motion. "
                                        "Turn off motion or keep the occurrence intact; nothing was split.")
            if before < checked["fade_in"] - 1e-9 or after < checked["fade_out"] - 1e-9:
                raise MediaLibraryError("The split point is inside a media audio fade. "
                                        "Choose a point outside the fade; nothing was split.")
            left = {**checked, "end": time, "fade_out": 0}
            right = {**checked, "id": "media_" + uuid.uuid4().hex, "start": time, "fade_in": 0}
            if kind != "image":
                right["source_start"] = round(checked["source_start"] + before, 9)
            if kind == "video":
                right["video_source_start"] = round(checked["video_source_start"] + before * checked["speed"], 9)
            clips[index:index + 1] = [validate_media_clip(project, left, duration), validate_media_clip(project, right, duration)]
    if len(clips) > MAX_MEDIA_CLIPS:
        raise MediaLibraryError(f"A project can contain at most {MAX_MEDIA_CLIPS} media clips")
    return None if clips == (manual.get("media_clips") or []) else {"media_clips": clips}


def _prepare_video_append(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Extend the edit with independent full-frame footage, keeping v1 A/B intact.

    This is a library occurrence on the edit clock, not a third synchronized
    camera role. Materialization preserves deliberate A/B gaps and history can
    restore an absent sequence exactly. Existing layers retain their clocks.
    """
    asset_id = payload.get("asset_id")
    asset = (project.get("assets") or {}).get(asset_id) if isinstance(asset_id, str) else None
    if not isinstance(asset, dict) or asset.get("kind") != "video" or asset.get("status") != "ready":
        raise MediaLibraryError("Choose a ready project video to append")
    available = number(asset.get("duration"), "Video duration", .08, MAX_ASSET_SECONDS)
    source_start = number(payload.get("source_start", 0), "source_start", 0, available)
    source_end = number(payload.get("source_end", available), "source_end", 0, available)
    length = round(source_end - source_start, 9)
    if length < .08 - 1e-9:
        raise MediaLibraryError("Choose at least 0.08 seconds of video to append")
    value, duration = materialize_sequence(project)
    end = round(duration + length, 9)
    if end > MAX_SEQUENCE_SECONDS:
        raise MediaLibraryError("The edit timeline cannot exceed 24 hours")
    prepared = value["manual"]
    clips = copy.deepcopy(prepared.get("media_clips") or [])
    if len(clips) >= MAX_MEDIA_CLIPS:
        raise MediaLibraryError(f"A project can contain at most {MAX_MEDIA_CLIPS} media clips")
    clip = {"id": "media_" + uuid.uuid4().hex, "asset_id": asset_id,
            "start": duration, "end": end, "source_start": source_start,
            "speed": 1, "volume_db": 0, "muted": False, "role": "voice",
            "fade_in": 0, "fade_out": 0, "x": 0, "y": 0, "w": 1, "h": 1,
            "fit": "cover", "motion": "none", "audio_enabled": bool(asset.get("has_audio"))}
    clips.append(validate_media_clip(value, clip, end))
    sequence = prepared["sequence"]
    sequence["duration"] = end
    # No A/B footage is extended or substituted behind the independent layer.
    # This default layout simply defines the newly added edit-clock interval.
    sequence["camera_plan"].append({"start": duration, "end": end, "camera": "A"})
    return {"sequence": sequence, "source_tracks": prepared["source_tracks"], "media_clips": clips}


def _insert_layer_time(project: dict[str, Any], at: float, length: float,
                       duration: float, *, reserved_media: int = 1) -> dict[str, list[dict[str, Any]]]:
    """Open time through independent layers without changing their content.

    Preserve stacking order and the left selection ID. A crossing occurrence
    resumes after the inserted shot, rather than playing underneath it. Existing
    picture and audio clocks stay independent. Effects whose phase cannot be
    represented by v1 clip fields are refused, not silently restarted.
    """
    from .text_clips import MAX_TEXT_CLIPS, validate_text_clip

    manual = project["manual"]
    layers = {}
    for key in ("media_clips", "text_clips"):
        rows = []
        for original in manual.get(key) or []:
            row = copy.deepcopy(original)
            start, end = row["start"], row["end"]
            if start >= at - 1e-9:
                rows.append({**row, "start": round(start + length, 9),
                             "end": round(end + length, 9)})
            elif end <= at + 1e-9:
                rows.append(row)
            else:
                if key == "text_clips" and row.get("template") == "chapter":
                    raise MediaLibraryError("A Chapter title crosses the insertion point. Insert at its start or end so its built-in fade is not restarted.")
                before, after = round(at - start, 9), round(end - at, 9)
                if min(before, after) < .08 - 1e-9:
                    raise MediaLibraryError(
                        "Insertion would leave a media or text piece shorter than 0.08 seconds. "
                        "Choose a clip boundary or move the playhead farther from its edge.")
                left = {**row, "end": at}
                right = {**row, "id": ("media_" if key == "media_clips" else "text_") + uuid.uuid4().hex,
                         "start": round(at + length, 9), "end": round(end + length, 9)}
                if key == "media_clips":
                    # Validate the old occurrence too: a split cannot repair or
                    # shorten an already-invalid source range by accident.
                    checked = validate_media_clip(project, row, duration)
                    kind = project["assets"][row["asset_id"]]["kind"]
                    if kind != "audio" and checked["motion"] != "none":
                        raise MediaLibraryError(
                            "An animated media clip crosses the playhead. Choose its boundary "
                            "before inserting so its motion is not restarted.")
                    if before < checked["fade_in"] - 1e-9 or after < checked["fade_out"] - 1e-9:
                        raise MediaLibraryError(
                            "The playhead is inside a media audio fade. Choose a point outside "
                            "the fade or a clip boundary before inserting.")
                    left["fade_out"] = 0
                    right["fade_in"] = 0
                    if kind != "image":
                        right["source_start"] = round(checked["source_start"] + before, 9)
                    if kind == "video":
                        right["video_source_start"] = round(checked["video_source_start"] + before * checked["speed"], 9)
                    rows.extend(validate_media_clip(project, piece, duration + length)
                                for piece in (left, right))
                else:
                    validate_text_clip(row, duration)
                    rows.extend(validate_text_clip(piece, duration + length) for piece in (left, right))
        limit = MAX_MEDIA_CLIPS - reserved_media if key == "media_clips" else MAX_TEXT_CLIPS
        if len(rows) > limit:
            label = "media" if key == "media_clips" else "text"
            maximum = MAX_MEDIA_CLIPS if key == "media_clips" else MAX_TEXT_CLIPS
            raise MediaLibraryError(f"Insertion would exceed the {maximum} {label} clip limit. "
                                    "Choose a boundary that needs fewer splits or remove unused clips.")
        layers[key] = rows
    return layers


def remove_layer_time(project: dict[str, Any], start: float, end: float,
                      duration: float) -> dict[str, list[dict[str, Any]]]:
    """Remove one edit-time interval from independent layers, never asset files.

    The first retained piece keeps its occurrence ID; only a second piece needs
    a new ID. No effect is approximated: partial animated motion or fade-phase
    cuts need a richer clip clock and are refused until that exists.
    """
    from .text_clips import MAX_TEXT_CLIPS, validate_text_clip

    manual, length = project["manual"], round(end - start, 9)
    layers = {}
    for key in ("media_clips", "text_clips"):
        if key not in manual:
            continue
        rows = []
        for original in manual.get(key) or []:
            row = copy.deepcopy(original)
            left, right = row["start"], row["end"]
            if right <= start + 1e-9:
                rows.append(row)
                continue
            if left >= end - 1e-9:
                rows.append({**row, "start": round(left - length, 9), "end": round(right - length, 9)})
                continue
            retained = []
            if left < start - 1e-9:
                retained.append((left, start, left))
            if right > end + 1e-9:
                retained.append((end, right, start))
            if not retained:
                continue  # Explicitly selected occurrences leave the timeline only.
            if key == "text_clips" and row.get("template") == "chapter":
                raise MediaLibraryError("Cut out would change the fade of a partially retained Chapter title. Remove the whole title in the range, or choose a range outside it.")
            if any(b - a < .08 - 1e-9 for a, b, _ in retained):
                raise MediaLibraryError(
                    "Range removal would leave a media or text piece shorter than 0.08 seconds. "
                    "Move the range edge to that clip's boundary or keep a longer piece.")
            checked = validate_media_clip(project, row, duration) if key == "media_clips" else validate_text_clip(row, duration)
            kind = project["assets"][row["asset_id"]]["kind"] if key == "media_clips" else None
            if kind is not None and kind != "audio" and checked["motion"] != "none":
                raise MediaLibraryError(
                    "The range would partially cut a media clip with animated pan/zoom motion. "
                    "Choose its boundary or remove the whole occurrence; no layers were changed.")
            for index, (a, b, at) in enumerate(retained):
                offset = round(a - left, 9)
                piece = {**row, "start": round(at, 9), "end": round(at + b - a, 9)}
                if index:
                    piece["id"] = ("media_" if key == "media_clips" else "text_") + uuid.uuid4().hex
                if kind is not None:
                    # A newly exposed edge must lie in the flat portion of the
                    # old envelope. Keeping a clipped fade would retime it.
                    for boundary in (a, b):
                        if left + 1e-9 < boundary < right - 1e-9:
                            if boundary - left < checked["fade_in"] - 1e-9 or right - boundary < checked["fade_out"] - 1e-9:
                                raise MediaLibraryError(
                                    "A range edge cuts inside a media audio fade. Move it outside the fade "
                                    "or to a clip boundary; no layers were changed.")
                    if a > left + 1e-9:
                        piece["fade_in"] = 0
                    if b < right - 1e-9:
                        piece["fade_out"] = 0
                    if kind != "image":
                        piece["source_start"] = round(checked["source_start"] + offset, 9)
                    if kind == "video":
                        piece["video_source_start"] = round(checked["video_source_start"] + offset * checked["speed"], 9)
                    rows.append(validate_media_clip(project, piece, duration - length))
                else:
                    rows.append(validate_text_clip(piece, duration - length))
        limit = MAX_MEDIA_CLIPS if key == "media_clips" else MAX_TEXT_CLIPS
        if len(rows) > limit:
            label = "media" if key == "media_clips" else "text"
            raise MediaLibraryError(f"Range removal would exceed the {limit} {label} clip limit after splitting. "
                                    "Choose clip boundaries or remove whole occurrences instead.")
        layers[key] = rows
    return layers


def validate_middle_insert_policy(project: dict[str, Any], manual: dict[str, Any], at: float) -> None:
    """Shared refusal policy for genuine all-layer middle insertion."""
    from .caption_alternatives import status as caption_status
    from .render import project_caption_items
    if (project.get("draft") or {}).get("audio_plan"):
        raise MediaLibraryError("This draft has a timed audio plan. Insert at the end or use a manual edit until timed audio ripple is supported.")
    if caption_status(project)["active_id"] != "original":
        raise MediaLibraryError("An alternative caption version is active. Undo that selection before inserting inside the edit; append remains available.")
    if manual.get("caption_dormant_overrides"):
        raise MediaLibraryError("Some caption edits have uncertain ownership. Resolve them before inserting inside the edit.")
    overrides = manual.get("caption_overrides") or {}
    if overrides:
        items = {row["id"]: row for row in project_caption_items(project, aligned=False)}
        if any(key not in items or items[key]["start"] < at < items[key]["end"] for key in overrides):
            raise MediaLibraryError("A manually edited caption crosses the insertion point. Choose a caption boundary before inserting.")


def _prepare_video_insert(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Insert footage and ripple supported mixed layers in one shared edit."""
    from .sequence import _insert_time, _finish
    from .caption_alternatives import status as caption_status
    from .render import project_caption_items

    staged = _prepare_video_append(project, payload)  # Asset/range/limit validation.
    occurrence = staged["media_clips"][-1]
    length = round(occurrence["end"] - occurrence["start"], 9)
    value, duration = materialize_sequence(project)
    at = number(payload.get("start"), "Insert playhead", 0, duration)
    if abs(at - duration) < 1e-9:
        return staged
    manual = value["manual"]
    validate_middle_insert_policy(project, manual, at)
    layers = _insert_layer_time(value, at, length, duration)
    block = {"duration": length, "source_tracks": {"A": [], "B": []},
             "camera_plan": [{"start": 0., "end": length, "camera": "A"}]}
    _insert_time(manual, block, at)
    _finish(value)
    occurrence.update(start=at, end=round(at + length, 9))
    layers["media_clips"].append(occurrence)
    result = {"sequence": manual["sequence"], "source_tracks": manual["source_tracks"],
              "media_clips": layers["media_clips"]}
    if "text_clips" in manual:
        result["text_clips"] = layers["text_clips"]
    return result


def validate_media_bounds(project: dict[str, Any]) -> None:
    """A main-timeline edit must not silently discard independent media."""
    clips = (project.get("manual") or {}).get("media_clips")
    if not clips:
        return
    duration = _edit_duration(project)
    for row in clips:
        if row["end"] > duration + 1e-8:
            raise MediaLibraryError("This edit would shorten the timeline past added media. Trim, move, or remove those media clips first.")
