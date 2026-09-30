"""Opt-in, local two-pass stabilization of a separate video copy.

This helper never edits a project or replaces its source. Callers choose a new
MP4 target and explicitly decide whether to use that copy in their edit. Motion
compensation and automatic zoom can crop picture edges; they cannot repair blur,
rolling shutter, or every kind of camera movement.
"""
from __future__ import annotations

import math
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Callable

from .jobs import JobCancelled
from .media import _stop_process, parse_rate

MAX_SECONDS = 4 * 3600
MAX_PASS_SECONDS = 4 * 3600
COPY_AUDIO_CODECS = {"aac", "mp3"}


class StabilizationError(ValueError):
    """A safe, actionable stabilization failure for an editor job."""


def _run(args, *, timeout, cancel_check=None, cwd=None, threads=2):
    """Drain both pipes while bounded work remains cooperatively cancellable."""
    if cancel_check:
        cancel_check()
    environment = dict(os.environ)
    environment["OMP_NUM_THREADS"] = str(threads)
    process = subprocess.Popen(
        args, cwd=cwd, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    started = time.monotonic()
    try:
        while True:
            if cancel_check:
                cancel_check()
            remaining = timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                stdout, stderr = process.communicate(timeout=min(.15, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, args, stdout, stderr)
        return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
    finally:
        _stop_process(process)


def stabilization_capability(settings, *, cancel_check=None) -> dict:
    """Check this installed FFmpeg; never install an optional library or model."""
    try:
        result = _run([settings.ffmpeg, "-nostdin", "-hide_banner", "-filters"],
                      timeout=15, cancel_check=cancel_check)
    except (OSError, subprocess.SubprocessError):
        return {"available": False, "engine": "vidstab", "message": "CUTROOM could not inspect the installed FFmpeg."}
    filters = set(re.findall(r"^\s*[.TSC]{3}\s+(vidstabdetect|vidstabtransform)\s+", result.stdout, re.MULTILINE))
    available = filters == {"vidstabdetect", "vidstabtransform"}
    return {
        "available": available, "engine": "vidstab",
        "message": "Local two-pass stabilization is available." if available else
                   "Stabilization needs FFmpeg with the vidstabdetect and vidstabtransform filters. No software was installed.",
    }


def _integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise StabilizationError(f"{name} must be an integer between {low} and {high}")
    return value


def _metadata_number(metadata, field):
    try:
        value = float(metadata.get(field, 0))
    except (TypeError, ValueError, OverflowError) as exc:
        raise StabilizationError("The video metadata is invalid for stabilization.") from exc
    if not math.isfinite(value):
        raise StabilizationError("The video metadata is invalid for stabilization.")
    return value


def probe_media(path, settings, *, cancel_check=None):
    """Inspect a local input with the same protocol and cancellation bounds."""
    result = _run([settings.ffprobe, "-v", "error", "-protocol_whitelist", "file,pipe",
                   "-show_streams", "-show_format", "-of", "json", str(path)],
                  timeout=45, cancel_check=cancel_check)
    payload = json.loads(result.stdout)
    streams = payload.get("streams") or []
    video = next((row for row in streams if row.get("codec_type") == "video"
                  and not (row.get("disposition") or {}).get("attached_pic")), None)
    audio = next((row for row in streams if row.get("codec_type") == "audio"), None)
    if not video:
        raise StabilizationError("The file does not contain a video stream.")
    duration = float((payload.get("format") or {}).get("duration") or video.get("duration") or 0)
    width, height = int(video.get("width") or 0), int(video.get("height") or 0)
    rotation = int((video.get("tags") or {}).get("rotate") or 0) % 360
    for side_data in video.get("side_data_list") or []:
        if "rotation" in side_data:
            rotation = int(side_data["rotation"]) % 360
    if rotation in {90, 270}:
        width, height = height, width
    return {
        "duration": duration, "video_duration": float(video.get("duration") or duration),
        "audio_duration": float((audio or {}).get("duration") or duration) if audio else 0.,
        "video_start_time": float(video.get("start_time") or 0),
        "audio_start_time": float((audio or {}).get("start_time") or 0),
        "width": width, "height": height,
        "fps": parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "nominal_fps": parse_rate(video.get("r_frame_rate") or video.get("avg_frame_rate")),
        "frame_count": int(video["nb_frames"]) if str(video.get("nb_frames", "")).isdigit() else 0,
        "has_audio": bool(audio), "audio_codec": (audio or {}).get("codec_name"),
    }


def stabilize_video(
    source: Path,
    target: Path,
    settings,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    *,
    smoothing: int = 15,
    shakiness: int = 5,
) -> Path:
    """Create a moderate, CPU-stabilized MP4 copy without overwriting any file.

    Smoothing is measured in frames (0–60); shakiness is bounded to 1–10. The
    original video clock is passed through, dimensions remain the same, and AAC
    or MP3 audio is copied. Other audio is explicitly converted to AAC. Each
    pass has a duration-based timeout capped at four hours. A failed/cancelled
    operation cleans its private transform data and partial video.
    """
    smoothing = _integer(smoothing, "smoothing", 0, 60)
    shakiness = _integer(shakiness, "shakiness", 1, 10)
    source = Path(source).resolve()
    requested_target = Path(target)
    if requested_target.is_symlink():
        raise StabilizationError("Choose a new output filename, not an existing link.")
    target = requested_target.resolve()
    if target == source:
        raise StabilizationError("Stabilization makes a copy; it cannot replace the original video.")
    if target.exists():
        raise StabilizationError("Choose a new output filename; an existing file will not be overwritten.")
    if target.suffix.lower() != ".mp4":
        raise StabilizationError("Choose an MP4 filename for the stabilized copy.")
    if not source.is_file():
        raise StabilizationError("The original video is unavailable.")
    if cancel_check:
        cancel_check()
    capability = stabilization_capability(settings, cancel_check=cancel_check)
    if not capability["available"]:
        raise StabilizationError(capability["message"])
    partial = target.parent / f".stabilized-{uuid.uuid4().hex}.partial.mp4"
    created_target = False
    completed = False
    try:
        original = probe_media(source, settings, cancel_check=cancel_check)
        if cancel_check:
            cancel_check()
        duration = _metadata_number(original, "duration")
        if not 0 < duration <= MAX_SECONDS:
            raise StabilizationError("Choose a video between one frame and four hours long.")
        width, height = int(original["width"]), int(original["height"])
        if min(width, height) < 2 or max(width, height) > 16384 or width * height > 64_000_000:
            raise StabilizationError("The video dimensions are unsupported for stabilization.")
        if width % 2 or height % 2:
            raise StabilizationError("Stabilization needs even video dimensions; make an even-sized copy first.")
        try:
            threads = min(4, max(1, int(settings.raw.get("ffmpeg_threads", 2))))
        except (TypeError, ValueError, OverflowError):
            threads = 2
        timeout = min(MAX_PASS_SECONDS, max(120, math.ceil(duration * 8) + 60))
        target.parent.mkdir(parents=True, exist_ok=True)
        # Only these literal ASCII names enter the filter expression. Absolute
        # creator paths (including apostrophes, spaces and Hebrew) stay in argv.
        with tempfile.TemporaryDirectory(prefix="cutroom-stabilize-") as scratch:
            work = Path(scratch)
            common = [settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error",
                      "-threads", str(threads), "-filter_threads", str(threads),
                      "-protocol_whitelist", "file,pipe", "-i", str(source)]
            if progress:
                progress(.05, "Analyzing camera movement")
            _run(common + ["-map", "0:v:0", "-an", "-vf",
                          f"vidstabdetect=result=transforms.trf:shakiness={shakiness}:accuracy=15:show=0",
                          "-fps_mode", "passthrough", "-f", "null", "-"],
                 timeout=timeout, cancel_check=cancel_check, cwd=work, threads=threads)
            if not (work / "transforms.trf").is_file():
                raise StabilizationError("FFmpeg did not produce usable stabilization data.")
            copy_audio = original.get("audio_codec") in COPY_AUDIO_CODECS
            if progress:
                audio_message = "keeping audio unchanged" if copy_audio else "converting audio to AAC"
                if not original.get("has_audio"):
                    audio_message = "no audio in this source"
                progress(.5, f"Stabilizing picture; {audio_message}")
            maxshift = min(64, max(1, int(min(width, height) * .1)))
            expression = (f"vidstabtransform=input=transforms.trf:smoothing={smoothing}:optalgo=gauss:"
                          f"maxshift={maxshift}:maxangle=0.15:crop=black:optzoom=1:interpol=bilinear,format=yuv420p")
            audio = ["-c:a", "copy"] if copy_audio else ["-c:a", "aac", "-b:a", "192k"]
            _run(common + ["-map", "0:v:0", "-map", "0:a:0?", "-map_metadata", "-1", "-map_chapters", "-1",
                          "-vf", expression, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                          "-threads", str(threads), "-fps_mode", "passthrough", "-enc_time_base:v", "filter", *audio,
                          "-movflags", "+faststart", "-n", str(partial)],
                 timeout=timeout, cancel_check=cancel_check, cwd=work, threads=threads)
            if cancel_check:
                cancel_check()
            if progress:
                progress(.95, "Checking stabilized copy")
            output = probe_media(partial, settings, cancel_check=cancel_check)
            fps = _metadata_number(original, "fps") or 25.
            frame_tolerance = max(.002, 1 / fps)
            video_duration = _metadata_number(original, "video_duration") or duration
            nominal_fps = _metadata_number(original, "nominal_fps") or fps
            variable_rate = abs(fps - nominal_fps) > .01
            frame_count = _metadata_number(original, "frame_count")
            if ((output["width"], output["height"]) != (width, height)
                    or abs(_metadata_number(output, "video_duration") - video_duration) > frame_tolerance
                    or abs(_metadata_number(output, "duration") - duration) > max(.05, frame_tolerance)
                    or bool(output.get("has_audio")) != bool(original.get("has_audio"))
                    or (original.get("has_audio") and (
                        abs(_metadata_number(output, "audio_duration") - _metadata_number(original, "audio_duration")) > max(.05, frame_tolerance)
                        or abs((_metadata_number(output, "video_start_time") - _metadata_number(output, "audio_start_time"))
                               - (_metadata_number(original, "video_start_time") - _metadata_number(original, "audio_start_time"))) > frame_tolerance))
                    or (frame_count and _metadata_number(output, "frame_count") != frame_count)
                    # VFR average rate depends on the muxer's final-frame hold.
                    # Validate its frame inventory/span instead of misreading a
                    # harmless average-rate change as resampling of the clock.
                    or (not variable_rate and abs(_metadata_number(output, "fps") - _metadata_number(original, "fps")) > .01)):
                raise StabilizationError("The stabilized copy did not preserve the video clock, dimensions or audio.")
            if cancel_check:
                cancel_check()
            # Same-directory hard linking publishes a complete file atomically
            # and fails if another operation claimed this name in the meantime.
            try:
                os.link(partial, target)
                created_target = True
            except FileExistsError as exc:
                raise StabilizationError("Choose a new output filename; an existing file will not be overwritten.") from exc
        if progress:
            progress(1., "Stabilized copy ready; the original video is unchanged")
        completed = True
        return target
    except (StabilizationError, JobCancelled):
        raise
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        # Keep FFmpeg command/path diagnostics only in the chained traceback.
        raise StabilizationError("CUTROOM could not stabilize this video. The original is unchanged; try another short recording.") from exc
    finally:
        partial.unlink(missing_ok=True)
        if created_target and not completed:
            target.unlink(missing_ok=True)
