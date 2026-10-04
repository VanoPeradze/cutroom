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
from .sequence import editor_sequence_snapshot

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus"}
ASSET_ID_RE = re.compile(r"asset_[0-9a-f]{32}\Z")
MAX_ASSETS = 100
MAX_MEDIA_CLIPS = 200
MAX_ASSET_SECONDS = 4 * 3600
CLIP_FIELDS = {"start", "end", "source_start", "speed", "volume_db", "muted", "role", "fade_in", "fade_out", "x", "y", "w", "h", "fit", "motion", "audio_enabled"}
AUDIO_MIXER_DEFAULTS = {
    "source_db": 0.0, "music_db": 0.0, "effects_db": 0.0, "voice_db": 0.0, "master_db": 0.0,
    "source_muted": False, "music_muted": False, "effects_muted": False, "voice_muted": False,
    "ducking": False,
}
MEDIA_ACTION_FIELDS = {
    "media_add": {"asset_id", *CLIP_FIELDS},
    "media_update": {"clip_id", *CLIP_FIELDS},
    "media_remove": {"clip_id"},
    "media_duplicate": {"clip_id", "start"},
    "media_split": {"clip_id", "time"},
    "set_audio_mixer": set(AUDIO_MIXER_DEFAULTS),
}


class MediaLibraryError(ValueError):
    pass


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
    return min(configured_limit, {"image": 32 * 1024**2, "audio": 512 * 1024**2, "video": 2 * 1024**3}[kind])


def safe_asset_path(project_dir: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise FileNotFoundError("Asset file is unavailable")
    root = project_dir.resolve()
    assets_root = (root / "media" / "assets").resolve()
    candidate = (root / relative.replace("\\", "/")).resolve()
    if root not in assets_root.parents or assets_root not in candidate.parents:
        raise FileNotFoundError("Invalid asset path")
    return candidate


def probe_asset(path: Path, kind: str, settings) -> dict[str, Any]:
    result = run_command([
        settings.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_format", "-show_streams",
        "-print_format", "json", str(path),
    ], timeout=30)
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
    return {"kind": kind, "duration": duration, "width": width, "height": height, "has_audio": bool(audio) and kind != "image"}


def prepare_asset(context, project_id: str, asset_id: str, store, settings) -> dict[str, Any]:
    generated: list[Path] = []
    try:
        project_dir = store.project_dir(project_id)
        asset = store.load(project_id)["assets"][asset_id]
        source = safe_asset_path(project_dir, asset["path"])
        folder = source.parent
        context.update(0.08, "Preparing media for the editor")
        kind = asset["kind"]
        preview = folder / ("preview.png" if kind == "image" else "preview.m4a" if kind == "audio" else "preview.mp4")
        generated.append(preview)
        if kind == "video":
            run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-threads", str(max(1, int(settings.raw.get("ffmpeg_threads", 4)))), "-protocol_whitelist", "file,pipe", "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-vf", "scale=-2:'min(720,ih)',format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(preview)], timeout=max(180, asset["duration"] * 4), cancel_check=context.check_cancelled)
        else:
            args = [settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-protocol_whitelist", "file,pipe", "-i", str(source), "-map_metadata", "-1"]
            args += ["-frames:v", "1", "-vf", "scale='min(4096,iw)':-1", str(preview)] if kind == "image" else ["-vn", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(preview)]
            run_command(args, timeout=max(90, asset["duration"] * 2), cancel_check=context.check_cancelled)
        updates: dict[str, Any] = {"preview_path": preview.relative_to(project_dir).as_posix(), "waveform": []}
        if kind in {"video", "image"}:
            context.update(0.65, "Creating media thumbnail")
            thumbnail = folder / "thumbnail.jpg"
            generated.append(thumbnail)
            run_command([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-i", str(preview), "-frames:v", "1", "-vf", "scale=320:-2", str(thumbnail)], timeout=60, cancel_check=context.check_cancelled)
            updates["thumbnail_path"] = thumbnail.relative_to(project_dir).as_posix()
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
            updates["waveform"] = [round(value / maximum, 4) if maximum else 0.0 for value in peaks]
        context.checkpoint()
        def complete(latest):
            context.commit()
            latest["assets"][asset_id].update(updates, status="ready")
        store.update(project_id, complete)
        return {"project_id": project_id, "asset_id": asset_id}
    except Exception as exc:
        cancelled = isinstance(exc, JobCancelled) or context.cancelled
        for file in generated:
            try:
                file.unlink(missing_ok=True)
            except OSError:
                # Cleanup must not replace the safe public error with a path.
                pass
        try:
            store.update(project_id, lambda latest: latest["assets"][asset_id].update(status="cancelled" if cancelled else "failed"))
        except Exception:
            pass
        if isinstance(exc, JobCancelled):
            raise
        if cancelled:
            raise JobCancelled("Job cancelled") from exc
        # JobManager exposes str(exc) in its public status. Retain command/path
        # diagnostics only in the chained exception's private traceback.
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


def validate_media_bounds(project: dict[str, Any]) -> None:
    """A main-timeline edit must not silently discard independent media."""
    clips = (project.get("manual") or {}).get("media_clips")
    if not clips:
        return
    duration = _edit_duration(project)
    for row in clips:
        if row["end"] > duration + 1e-8:
            raise MediaLibraryError("This edit would shorten the timeline past added media. Trim, move, or remove those media clips first.")
