"""Local media assets and non-destructive, edit-clock overlay clips."""
from __future__ import annotations

import array
import copy
import json
import math
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from .media import VIDEO_EXTENSIONS, run_command
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
    "media_add": {"asset_id", *CLIP_FIELDS},
    "media_append": {"asset_id", "source_start", "source_end"},
    "media_insert": {"asset_id", "source_start", "source_end", "start"},
    "media_update": {"clip_id", *CLIP_FIELDS},
    "media_remove": {"clip_id"},
    "media_duplicate": {"clip_id", "start"},
    "media_split": {"clip_id", "time"},
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
    root = project_dir.resolve()
    assets_root = (root / "media" / "assets").resolve()
    candidate = (root / relative.replace("\\", "/")).resolve()
    if root not in assets_root.parents or assets_root not in candidate.parents:
        raise FileNotFoundError("Invalid asset path")
    return candidate


def probe_asset(path: Path, kind: str, settings, *, cancel_check=None, include_codecs=False) -> dict[str, Any]:
    result = run_command([
        settings.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams",
        "-print_format", "json", str(path),
    ], timeout=30, **({"cancel_check": cancel_check} if cancel_check is not None else {}))
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
                 "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0",
                 "-frames:v", "1", "-an", "-vf", "scale=320:-2", "-threads", "1",
                 str(folder / "thumbnail.jpg")], timeout=60, cancel_check=context.check_cancelled)


def _probe_prepared_asset(path: Path, kind: str, original: dict[str, Any], settings, context) -> dict[str, Any]:
    metadata = probe_asset(path, kind, settings, cancel_check=context.check_cancelled, include_codecs=True)
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
        run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-threads", str(max(1, int(settings.raw.get("ffmpeg_threads", 4)))), "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-vf", "scale=-2:'min(720,ih)',format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(preview)], timeout=max(180, asset["duration"] * 4), cancel_check=context.check_cancelled)
    else:
        args = [settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source), "-map_metadata", "-1"]
        args += ["-frames:v", "1", "-vf", "scale='min(4096,iw)':-1", str(preview)] if kind == "image" else ["-vn", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(preview)]
        run_command(args, timeout=max(90, asset["duration"] * 2), cancel_check=context.check_cancelled)
    if kind in {"video", "image"}:
        context.update(0.65, "Creating media thumbnail")
        run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", str(preview), "-frames:v", "1", "-vf", "scale=320:-2", str(folder / "thumbnail.jpg")], timeout=60, cancel_check=context.check_cancelled)
    waveform: list[float] = []
    if asset["has_audio"]:
        context.update(0.8, "Building audio waveform")
        result = run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-i", str(preview), "-vn", "-af", "aformat=channel_layouts=mono,aeval=abs(val(0))", "-ac", "1", "-ar", "100", "-f", "s16le", "pipe:1"], text=False, timeout=max(60, asset["duration"]), cancel_check=context.check_cancelled)
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
    "preparation_identity", "preview_path", "thumbnail_path", "preview_mode",
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


def prepare_asset(context, project_id: str, asset_id: str, store, settings) -> dict[str, Any]:
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
                source = native_io_path(safe_asset_path(normal_project_dir, initial["path"]))
                cache = PreparationCache(project_dir, folder, context.check_cancelled,
                                         lambda path, kind: _probe_prepared_asset(path, kind, initial, settings, context))
                if initial.get("kind") not in {"video", "image", "audio"}:
                    raise MediaLibraryError("Invalid media type")
                context.update(0.08, "Checking prepared media")
                key, identity = source_identity(source, initial, settings, context.check_cancelled)
                original_preview = None
                if initial["kind"] == "video" and identity["file"]["size"] > DIRECT_VIDEO_PREVIEW_BYTES:
                    metadata = probe_asset(source, "video", settings, cancel_check=context.check_cancelled, include_codecs=True)
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
                    assert_source_unchanged(source, identity, context.check_cancelled, content=False)
                    context.commit()
                    current.update(updates, status="ready")
                saved = store.update(project_id, complete)
                owned = None
                try:
                    cache.cleanup(saved)
                except (OSError, PreparationCacheError):
                    # A valid current generation remains usable. A later retry
                    # applies the explicit eight-generation bound before work.
                    pass
                return {"project_id": project_id, "asset_id": asset_id, "preparation_reused": reused}
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


def validate_media_clip(project: dict[str, Any], row: dict[str, Any], duration: float) -> dict[str, Any]:
    asset = (project.get("assets") or {}).get(row.get("asset_id"))
    if not isinstance(asset, dict) or asset.get("status", "ready") != "ready":
        raise MediaLibraryError("Choose a ready media asset")
    result = copy.deepcopy(row)
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
    if action == "media_append":
        return _prepare_video_append(project, payload)
    if action == "media_insert":
        return _prepare_video_insert(project,payload)
    duration = _edit_duration(project)
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
        clip = {"id": "media_" + uuid.uuid4().hex, "asset_id": asset_id, "start": start, "end": min(duration, start + available), "source_start": source_start, "speed": speed, "volume_db": 0, "muted": False, "role": "music", "fade_in": 0, "fade_out": 0, "x": 0, "y": 0, "w": 1, "h": 1, "fit": "cover", "motion": "none", "audio_enabled": asset["kind"] == "audio"}
        clip.update({key: payload[key] for key in CLIP_FIELDS if key in payload})
        clips.append(validate_media_clip(project, clip, duration))
    else:
        clip = next((row for row in clips if row.get("id") == payload.get("clip_id")), None)
        if clip is None:
            raise MediaLibraryError("The selected media clip no longer exists")
        index = clips.index(clip)
        if action == "media_remove":
            clips.pop(index)
        elif action == "media_update":
            candidate = {**clip, **{key: payload[key] for key in CLIP_FIELDS if key in payload}}
            asset = project["assets"][clip["asset_id"]]
            if asset["kind"] == "video" and "source_start" in payload:
                source_start = number(payload["source_start"], "source_start", 0, MAX_ASSET_SECONDS)
                candidate["video_source_start"] = max(0.0, clip.get("video_source_start", clip["source_start"]) + (source_start - clip["source_start"]) * clip["speed"])
            clips[index] = validate_media_clip(project, candidate, duration)
        elif action == "media_duplicate":
            start = number(payload.get("start", clip["start"]), "start", 0, duration)
            duplicate = {**clip, "id": "media_" + uuid.uuid4().hex, "start": start, "end": start + clip["end"] - clip["start"]}
            clips.append(validate_media_clip(project, duplicate, duration))
        elif action == "media_split":
            time = number(payload.get("time"), "time", clip["start"] + .08, clip["end"] - .08)
            left = {**clip, "end": time, "fade_in": min(clip["fade_in"], time - clip["start"]), "fade_out": 0}
            right = {**clip, "id": "media_" + uuid.uuid4().hex, "start": time, "source_start": clip["source_start"] + (time - clip["start"]), "fade_in": 0, "fade_out": min(clip["fade_out"], clip["end"] - time)}
            if project["assets"][clip["asset_id"]]["kind"] == "video":
                right["video_source_start"] = clip.get("video_source_start", clip["source_start"]) + (time - clip["start"]) * clip["speed"]
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


def _prepare_video_insert(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Reuse linked time insertion; move only layers with unambiguous ownership."""
    from .sequence import _insert_time, _finish
    from .caption_alternatives import status as caption_status
    from .render import project_caption_items
    staged=_prepare_video_append(project,payload)  # Existing asset/range/limit validation.
    occurrence=staged["media_clips"][-1]
    length=occurrence["end"]-occurrence["start"]
    value,duration=materialize_sequence(project)
    at=number(payload.get("start"),"Insert playhead",0,duration)
    if abs(at-duration)<1e-9:return staged
    manual=value["manual"]
    if (project.get("draft") or {}).get("audio_plan"):
        raise MediaLibraryError("This draft has a timed audio plan. Insert at the end or use a manual edit until timed audio ripple is supported.")
    if caption_status(project)["active_id"]!="original":
        raise MediaLibraryError("An alternative caption version is active. Undo that selection before inserting inside the edit; append remains available.")
    if manual.get("caption_dormant_overrides"):
        raise MediaLibraryError("Some caption edits have uncertain ownership. Resolve them before inserting inside the edit.")
    overrides=manual.get("caption_overrides") or {}
    if overrides:
        items={row["id"]:row for row in project_caption_items(project,aligned=False)}
        if any(key not in items or items[key]["start"]<at<items[key]["end"] for key in overrides):
            raise MediaLibraryError("A manually edited caption crosses the insertion point. Choose a caption boundary before inserting.")
    layers={}
    for key,label in (("media_clips","media/audio"),("text_clips","text/caption")):
        rows=copy.deepcopy(manual.get(key) or [])
        if any(row["start"]<at-1e-9 and row["end"]>at+1e-9 for row in rows):
            raise MediaLibraryError(f"A {label} clip crosses the playhead. Split that clip at the playhead or choose a boundary before inserting.")
        for row in rows:
            if row["start"]>=at-1e-9:
                row["start"]=round(row["start"]+length,9);row["end"]=round(row["end"]+length,9)
        layers[key]=rows
    block={"duration":length,"source_tracks":{"A":[],"B":[]},"camera_plan":[{"start":0.,"end":length,"camera":"A"}]}
    _insert_time(manual,block,at);_finish(value)
    occurrence.update(start=at,end=round(at+length,9))
    layers["media_clips"].append(occurrence)
    result={"sequence":manual["sequence"],"source_tracks":manual["source_tracks"],"media_clips":layers["media_clips"]}
    if "text_clips" in manual:result["text_clips"]=layers["text_clips"]
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
