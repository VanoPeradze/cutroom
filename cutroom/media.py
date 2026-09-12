from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .utils import clamp

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts", ".mpg", ".mpeg"}
BROWSER_CONTAINERS = {"mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"}
BROWSER_VIDEO_CODECS = {"h264", "vp8", "vp9", "av1"}
BROWSER_AUDIO_CODECS = {"aac", "mp3", "opus", "vorbis"}


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.communicate(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            return
        try:
            process.communicate(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass


def run_command(
    args: list[str],
    *,
    timeout: int | float | None = None,
    check: bool = True,
    text: bool = True,
    cancel_check: Callable[[], None] | None = None,
) -> subprocess.CompletedProcess:
    """Run a bounded media command, optionally with cooperative cancellation.

    The no-callback path deliberately retains ``subprocess.run`` compatibility for
    callers and test hooks. Long preparation jobs opt into the Popen path so a
    cancelled job terminates FFmpeg instead of waiting for an entire transcode.
    """

    if cancel_check is None:
        return subprocess.run(args, capture_output=True, text=text, timeout=timeout, check=check)
    cancel_check()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        creationflags=creationflags,
    )
    started = time.monotonic()
    stdout: str | bytes | None = "" if text else b""
    stderr: str | bytes | None = "" if text else b""
    try:
        while True:
            cancel_check()
            if timeout is not None:
                remaining = float(timeout) - (time.monotonic() - started)
                if remaining <= 0.0:
                    raise subprocess.TimeoutExpired(args, timeout, output=stdout, stderr=stderr)
                wait_seconds = min(0.15, remaining)
            else:
                wait_seconds = 0.15
            try:
                stdout, stderr = process.communicate(timeout=wait_seconds)
                break
            except subprocess.TimeoutExpired as pending:
                # communicate() keeps its internal buffers between retries. These
                # snapshots make a final timeout exception useful to diagnostics.
                if pending.output is not None:
                    stdout = pending.output
                if pending.stderr is not None:
                    stderr = pending.stderr
        result = subprocess.CompletedProcess(args, int(process.returncode or 0), stdout, stderr)
        if check and result.returncode:
            raise subprocess.CalledProcessError(
                result.returncode,
                args,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result
    finally:
        _stop_process(process)


def probe_media(path: Path, settings: Settings) -> dict[str, Any]:
    command = [
        settings.ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)
    ]
    result = run_command(command, timeout=45)
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if not video:
        raise ValueError("The file does not contain a video stream")
    duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid media duration")
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    if width <= 0 or height <= 0:
        raise ValueError("Invalid video dimensions")
    rotation = 0
    tags = video.get("tags") or {}
    if "rotate" in tags:
        try:
            rotation = int(tags["rotate"]) % 360
        except (TypeError, ValueError):
            pass
    for data in video.get("side_data_list") or []:
        if "rotation" in data:
            try:
                rotation = int(data["rotation"]) % 360
            except (TypeError, ValueError):
                pass
    if rotation in {90, 270}:
        width, height = height, width
    format_name = payload.get("format", {}).get("format_name", "")
    video_codec = video.get("codec_name", "unknown")
    audio_codec = audio.get("codec_name") if audio else None
    try:
        video_duration = float(video.get("duration") or duration)
    except (TypeError, ValueError):
        video_duration = duration
    try:
        audio_duration = float(audio.get("duration") or duration) if audio else None
    except (TypeError, ValueError):
        audio_duration = duration if audio else None
    browser_ready = video_codec in BROWSER_VIDEO_CODECS and (not audio_codec or audio_codec in BROWSER_AUDIO_CODECS)
    return {
        "duration": round(duration, 3),
        "video_duration": round(video_duration, 3),
        "audio_duration": round(audio_duration, 3) if audio_duration is not None else None,
        "width": width,
        "height": height,
        "rotation": rotation,
        "fps": parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate")),
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "has_audio": bool(audio),
        "format": format_name,
        "size": path.stat().st_size,
        "browser_ready": browser_ready and path.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"},
        "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    }


def parse_rate(value: str | None) -> float:
    if not value or value == "0/0":
        return 0.0
    try:
        if "/" in value:
            numerator, denominator = value.split("/", 1)
            return round(float(numerator) / float(denominator), 3) if float(denominator) else 0.0
        return round(float(value), 3)
    except (ValueError, ZeroDivisionError):
        return 0.0


def create_proxy(
    source: Path,
    target: Path,
    settings: Settings,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.parent / f".{target.stem}-{uuid.uuid4().hex}.partial.mp4"
    height = int(settings.raw.get("proxy_height", 720))
    crf = int(settings.raw.get("proxy_crf", 27))
    threads = max(1, int(settings.raw.get("ffmpeg_threads", 4)))
    command = [
        settings.ffmpeg, "-hide_banner", "-y", "-threads", str(threads), "-i", str(source),
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", f"scale=-2:'min({height},ih)':flags=lanczos,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(temp),
    ]
    if progress:
        progress(0.05, "Creating preview proxy")
    try:
        run_command(command, timeout=None, cancel_check=cancel_check)
        if cancel_check:
            cancel_check()
        temp.replace(target)
        if progress:
            progress(1.0, "Preview ready")
        return target
    finally:
        temp.unlink(missing_ok=True)


def extract_thumbnails(
    source: Path,
    output_dir: Path,
    duration: float,
    settings: Settings,
    count: int = 24,
    cancel_check: Callable[[], None] | None = None,
) -> list[str]:
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    count = max(6, min(48, int(count)))
    duration_value = float(duration)
    if not math.isfinite(duration_value) or duration_value <= 0.0:
        raise ValueError("Invalid thumbnail source duration")
    fps = count / max(duration_value, 0.1)
    staging = output_dir.parent / f".{output_dir.name}-{uuid.uuid4().hex}.partial"
    backup = output_dir.parent / f".{output_dir.name}-{uuid.uuid4().hex}.backup"
    staging.mkdir(parents=True, exist_ok=False)
    pattern = staging / "thumb-%03d.jpg"
    command = [
        settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vf", f"fps={fps:.8f},scale=240:-2:flags=fast_bilinear",
        "-frames:v", str(count), "-q:v", "5", str(pattern),
    ]
    installed = False
    try:
        run_command(command, timeout=None, cancel_check=cancel_check)
        if cancel_check:
            cancel_check()
        generated = sorted(staging.glob("thumb-*.jpg"))
        if not generated:
            raise RuntimeError("FFmpeg did not generate timeline thumbnails")
        if output_dir.exists():
            output_dir.replace(backup)
        try:
            staging.replace(output_dir)
            installed = True
        except BaseException:
            if backup.exists() and not output_dir.exists():
                backup.replace(output_dir)
            raise
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        return [path.name for path in sorted(output_dir.glob("thumb-*.jpg"))]
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        if not installed and backup.exists() and not output_dir.exists():
            backup.replace(output_dir)
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)


def detect_silences(source: Path, settings: Settings, noise_db: float = -38, min_duration: float = 0.45) -> list[dict[str, float]]:
    command = [
        settings.ffmpeg, "-hide_banner", "-i", str(source),
        "-af", f"silencedetect=noise={noise_db}dB:d={min_duration}", "-f", "null", "-",
    ]
    result = run_command(command, check=False, timeout=None)
    text = (result.stderr or "") + "\n" + (result.stdout or "")
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", text)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", text)]
    ranges: list[dict[str, float]] = []
    for index, start in enumerate(starts):
        if index < len(ends) and ends[index] > start:
            ranges.append({"start": round(start, 3), "end": round(ends[index], 3)})
    return ranges


def detect_scenes(
    source: Path,
    settings: Settings,
    threshold: float = 0.32,
    max_points: int = 180,
    cancel_check: Callable[[], None] | None = None,
) -> list[float]:
    command = [
        settings.ffmpeg, "-hide_banner", "-threads", str(max(1, int(settings.raw.get("ffmpeg_threads", 4)))), "-i", str(source),
        "-an", "-filter:v", f"fps={float(settings.raw.get('scene_analysis_fps', 1.5)):.2f},scale=320:-2:flags=fast_bilinear,select='gt(scene,{clamp(threshold, 0.05, 0.9)})',showinfo",
        "-f", "null", "-",
    ]
    result = run_command(command, check=False, timeout=None, cancel_check=cancel_check)
    points = [float(value) for value in re.findall(r"pts_time:([0-9.]+)", result.stderr or "")]
    deduped: list[float] = []
    for point in points:
        if not deduped or point - deduped[-1] >= 0.35:
            deduped.append(round(point, 3))
    limit = max(0, int(max_points))
    if limit == 0:
        return []
    if len(deduped) <= limit:
        return deduped
    if limit == 1:
        return [deduped[len(deduped) // 2]]
    # Long streams can have thousands of cuts. Keeping only the first N blinded
    # Director to the rest of the recording, so retain a uniform timeline sample
    # that always includes the first and final detected scene.
    indexes = [round(index * (len(deduped) - 1) / (limit - 1)) for index in range(limit)]
    return [deduped[index] for index in indexes]


def extract_waveform(source: Path, target: Path, settings: Settings, width: int = 1800, height: int = 160) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-filter_complex", f"showwavespic=s={width}x{height}:colors=white:scale=sqrt",
        "-frames:v", "1", str(target),
    ]
    run_command(command, timeout=None)
    return target


class UploadTooLargeError(ValueError):
    """Raised when an imported source exceeds CUTROOM's configured per-file limit."""


def copy_upload(file_storage: Any, destination: Path, max_bytes: int) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.partial")
    total = 0
    try:
        with temp.open("wb") as handle:
            while True:
                chunk = file_storage.stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise UploadTooLargeError("File exceeds the configured upload limit")
                handle.write(chunk)
        temp.replace(destination)
        return total
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
