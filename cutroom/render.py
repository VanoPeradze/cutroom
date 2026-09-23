from __future__ import annotations

import json
import math
import os
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .config import Settings
from .captions import build_ass, build_srt, normalize_caption_settings
from .composition import select_embedded_candidate
from .effects import compile_automatic_effects
from .frame_rates import project_export_fps, with_export_options
from .cache_keys import stable_fingerprint
from .jobs import JobCancelled, JobContext
from .media import probe_media
from .media_render import append_media_graph, library_input_args, library_clips, library_has_audio, master_gain_db
from .projects import ProjectStore
from .source_tracks import has_sequence, has_source_tracks, source_track_clips, timeline_duration
from .utils import new_id, now_iso, sanitize_filename

ASPECT_DIMENSIONS = {
    "9:16": {"720": (720, 1280), "1080": (1080, 1920), "1440": (1440, 2560), "2160": (2160, 3840)},
    "16:9": {"720": (1280, 720), "1080": (1920, 1080), "1440": (2560, 1440), "2160": (3840, 2160)},
    "1:1": {"720": (720, 720), "1080": (1080, 1080), "1440": (1440, 1440), "2160": (2160, 2160)},
    "4:5": {"720": (720, 900), "1080": (1080, 1350), "1440": (1440, 1800), "2160": (2160, 2700)},
}

CAMERA_LAYOUTS = {"A", "B", "screen", "camera", "stacked", "side_by_side", "pip", "embedded_stack"}


class InsufficientStorageError(RuntimeError):
    """Structured render-capacity failure suitable for an HTTP 507 mapping."""

    code = "insufficient_storage"
    status_code = 507
    status = 507

    def __init__(self, *, required_bytes: int, free_bytes: int, location: Path):
        self.required_bytes = max(0, int(required_bytes))
        self.free_bytes = max(0, int(free_bytes))
        self.location = str(location)
        self.message = (
            "There is not enough free disk space to render this edit "
            f"(need about {self.required_bytes} bytes, {self.free_bytes} bytes available)."
        )
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "required_bytes": self.required_bytes,
            "required_free_bytes": self.required_bytes,
            "disk_free_bytes": self.free_bytes,
            "shortfall_bytes": max(0, self.required_bytes - self.free_bytes),
            "location": self.location,
        }


def _finite_float(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _source_has_video(source: dict[str, Any] | None) -> bool:
    if not isinstance(source, dict):
        return False
    return (
        _finite_float(source.get("duration")) > 0.0
        and _finite_float(source.get("width")) > 0.0
        and _finite_float(source.get("height")) > 0.0
    )


def _source_video_duration(source: dict[str, Any]) -> float:
    video_duration = _finite_float(source.get("video_duration"))
    return video_duration if video_duration > 0 else max(0.0, _finite_float(source.get("duration")))


def _timeline_overlap(start: float, end: float, source_duration: float, offset: float) -> bool:
    """Whether source-local [0,duration] has real samples in an A-timeline range."""

    return max(start, offset) < min(end, offset + max(0.0, source_duration)) - 0.005


def _clean_ranges(rows: Any, duration: float) -> list[dict[str, float]]:
    values: list[dict[str, float]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        start = max(0.0, min(duration, _finite_float(row.get("start"))))
        end = max(0.0, min(duration, _finite_float(row.get("end"))))
        if end - start >= 0.005:
            values.append({"start": start, "end": end})
    values.sort(key=lambda item: (item["start"], item["end"]))
    output: list[dict[str, float]] = []
    for item in values:
        start = item["start"]
        if output and start < output[-1]["end"]:
            start = output[-1]["end"]
        if item["end"] - start >= 0.005:
            output.append({"start": round(start, 6), "end": round(item["end"], 6)})
    return output


def _render_plan(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a bounded, gap-free camera plan inside the authoritative keep ranges.

    Manual editing normally writes a perfect partition. This defensive pass keeps
    corrupted/legacy JSON from resurrecting removed footage, duplicating overlap,
    generating ``split=0``, or desynchronizing captions from rendered duration.
    """

    fps = project_export_fps(project)
    source = (project.get("sources") or {}).get("A") or {}
    if _finite_float(source.get("duration")) <= 0.0:
        raise ValueError("Source A has an invalid duration")
    duration = timeline_duration(project)
    if duration <= 0.0:
        raise ValueError("Add footage to the timeline before exporting")
    draft = project.get("draft") or {}
    sequence = project["manual"]["sequence"] if has_sequence(project) else None
    # A materialized sequence is already an edit clock. The original Story keep
    # mask must not cut it a second time, nor truncate clips moved beyond A's EOF.
    has_keep_contract = sequence is not None or "keep_ranges" in draft
    keeps = [{"start": 0.0, "end": duration}] if sequence is not None else _clean_ranges(draft.get("keep_ranges"), duration)
    plan_owner = sequence if sequence is not None else draft
    raw_plan = plan_owner.get("camera_plan") if isinstance(plan_owner.get("camera_plan"), list) else []
    camera_rows: list[dict[str, Any]] = []
    for row in raw_plan:
        if not isinstance(row, dict):
            continue
        start = max(0.0, min(duration, _finite_float(row.get("start"))))
        end = max(0.0, min(duration, _finite_float(row.get("end"))))
        camera = str(row.get("camera") or "A")
        if camera == "auto" or camera not in CAMERA_LAYOUTS:
            camera = "A"
        if end - start >= 0.005:
            camera_rows.append({"start": start, "end": end, "camera": camera})
    camera_rows.sort(key=lambda item: (item["start"], item["end"]))

    # Legacy drafts sometimes only contain camera_plan; in that case its ranges
    # remain the edit contract. With neither field, preserve all of source A.
    if has_keep_contract and not keeps:
        raise ValueError("The edit has no valid kept ranges. Rebuild the draft before rendering.")
    if not keeps:
        keeps = _clean_ranges(camera_rows, duration)
    if not keeps:
        keeps = [{"start": 0.0, "end": duration}]

    source_b = (project.get("sources") or {}).get("B") or {}
    mixer = _source_mixer(project)
    b_start = math.ceil(_sync_offset(project) * fps - 0.000001) / fps
    b_end = math.floor(
        (_sync_offset(project) + _source_video_duration(source_b)) * fps + 0.000001
    ) / fps
    b_has_video = _source_has_video(source_b)
    independent = has_sequence(project) or has_source_tracks(project)
    track_boundaries: set[float] = set()
    track_video_ranges: dict[str, list[tuple[float, float]]] = {"A": [], "B": []}
    track_crops: dict[str, list[tuple[float, float, dict[str, float]]]] = {"A": [], "B": []}
    if independent:
        for slot in ("A", "B"):
            info = (project.get("sources") or {}).get(slot) or {}
            if not _source_has_video(info):
                continue
            video_duration = _source_video_duration(info)
            for clip in source_track_clips(project, slot):
                start = math.floor(float(clip["start"]) * fps + 0.5) / fps
                real_end = min(float(clip["end"]), float(clip["start"]) + video_duration - float(clip["source_start"]))
                if "video_speed" in clip:
                    real_end = float(clip["end"])
                end = math.floor(real_end * fps + 0.5) / fps
                if end > start:
                    track_boundaries.update((start, end))
                    track_video_ranges[slot].append((start, end))
                    if "crop" in clip:
                        track_crops[slot].append((start, end, clip["crop"]))

    def available(slot: str, time: float) -> bool:
        return any(start <= time < end for start, end in track_video_ranges[slot])

    def needs_b(camera: str) -> bool:
        return (
            camera in {"B", "stacked", "side_by_side", "pip"}
            or (camera == "screen" and mixer["screen_slot"] == "B")
            or (camera == "camera" and mixer["camera_slot"] == "B")
        )

    plan: list[dict[str, Any]] = []
    for keep in keeps:
        boundaries = {float(keep["start"]), float(keep["end"])}
        if independent:
            first_frame = math.floor(float(keep["start"]) * fps + 0.5)
            last_frame = math.floor(float(keep["end"]) * fps + 0.5)
            boundaries.update(boundary for boundary in track_boundaries
                              if keep["start"] < boundary < keep["end"]
                              and first_frame < round(boundary * fps) < last_frame)
        elif b_has_video:
            keep_start_frame = math.floor(float(keep["start"]) * fps + 0.5)
            keep_end_frame = math.floor(float(keep["end"]) * fps + 0.5)
            # A generated B-availability seam can be numerically inside a keep
            # yet land on its first/last output frame. Do not invent a zero-frame
            # fragment which would reject an otherwise valid user's edit.
            boundaries.update(
                boundary for boundary in (b_start, b_end)
                if keep["start"] < boundary < keep["end"]
                and keep_start_frame < round(boundary * fps) < keep_end_frame
            )
        for row in camera_rows:
            if row["end"] <= keep["start"] or row["start"] >= keep["end"]:
                continue
            boundaries.add(max(float(keep["start"]), float(row["start"])))
            boundaries.add(min(float(keep["end"]), float(row["end"])))
        ordered = sorted(boundaries)
        for start, end in zip(ordered, ordered[1:]):
            if end - start < 0.005:
                continue
            midpoint = (start + end) / 2.0
            camera = next(
                (
                    str(row["camera"])
                    for row in reversed(camera_rows)
                    if float(row["start"]) <= midpoint < float(row["end"])
                ),
                "A",
            )
            # A shorter/offset B must not turn part of a camera-only shot black
            # or freeze its last frame. Match the preview by showing A wherever
            # B has no real video; preserve the requested layout inside B.
            if independent:
                present = {slot for slot in ("A", "B") if available(slot, midpoint)}
                desired = mixer.get(f"{camera}_slot", camera)
                if not present:
                    camera = "black"
                elif camera == "embedded_stack":
                    camera = "embedded_stack" if "A" in present else "B"
                elif len(present) == 1 or desired in {"A", "B"} and desired not in present:
                    camera = next(iter(present))
            elif needs_b(camera) and not (b_has_video and b_start <= midpoint < b_end):
                camera = "A"
            item = {"start": round(start, 6), "end": round(end, 6), "camera": camera}
            crops = {slot: crop for slot in ("A", "B") for left, right, crop in track_crops[slot] if left <= midpoint < right}
            if crops:
                item["crop"] = crops
            if plan and plan[-1]["camera"] == camera and plan[-1].get("crop") == item.get("crop") and abs(float(plan[-1]["end"]) - start) < 0.0005:
                plan[-1]["end"] = item["end"]
            else:
                plan.append(item)

    # FFmpeg can render very short intervals, but they are expensive and prone to
    # zero-frame VFR output. Absorb them into a touching neighbour without changing
    # the kept duration.
    for index, item in enumerate(plan):
        if float(item["end"]) - float(item["start"]) >= 0.08:
            continue
        if independent or any(abs(float(item[edge]) - boundary) < 0.0005 for edge in ("start", "end") for boundary in (b_start, b_end)):
            continue
        if index > 0 and abs(float(plan[index - 1]["end"]) - float(item["start"])) < 0.0005:
            item["camera"] = plan[index - 1]["camera"]
        elif index + 1 < len(plan) and abs(float(item["end"]) - float(plan[index + 1]["start"])) < 0.0005:
            item["camera"] = plan[index + 1]["camera"]
    compact: list[dict[str, Any]] = []
    for item in plan:
        if compact and compact[-1]["camera"] == item["camera"] and compact[-1].get("crop") == item.get("crop") and abs(float(compact[-1]["end"]) - float(item["start"])) < 0.0005:
            compact[-1]["end"] = item["end"]
        else:
            compact.append(item)
    if len(compact) > (2000 if has_sequence(project) else 500):
        raise ValueError("The edit contains too many fragments. Merge cuts before rendering.")
    return compact


def _frame_aligned_plan(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Snap every edit boundary once to the shared output frame grid.

    Applying ``fps`` independently to dozens of short fragments lets each
    fragment round its tail up to another frame. The concat filter then pads
    audio to every rounded video fragment and that error accumulates. Snapping
    the authoritative source-timeline boundaries first gives A, B, audio and
    captions the same deterministic contract while retaining every fragment.
    """

    fps = project_export_fps(project)
    plan = _render_plan(project)
    aligned: list[dict[str, Any]] = []
    raw_duration = 0.0
    aligned_frames = 0
    for item in plan:
        raw_start = float(item["start"])
        raw_end = float(item["end"])
        start_frame = int(math.floor(raw_start * fps + 0.5))
        end_frame = int(math.floor(raw_end * fps + 0.5))
        if end_frame <= start_frame:
            raise ValueError(
                "The edit contains a fragment shorter than one output frame. "
                "Merge nearby cuts before rendering."
            )
        aligned.append(
            {
                **item,
                "start": start_frame / fps,
                "end": end_frame / fps,
                "_start_frame": start_frame,
                "_end_frame": end_frame,
            }
        )
        raw_duration += raw_end - raw_start
        aligned_frames += end_frame - start_frame

    aligned_duration = aligned_frames / fps
    quantization_limit = max(0.25, raw_duration * 0.01)
    if abs(aligned_duration - raw_duration) > quantization_limit:
        raise ValueError(
            "The edit contains too many sub-frame cuts. Merge nearby cuts before rendering."
        )
    return aligned


def _caption_ranges(project: dict[str, Any]) -> list[dict[str, float]]:
    """Use the exact normalized kept intervals for burned and sidecar captions."""

    plan = _frame_aligned_plan(project)
    ranges: list[dict[str, float]] = []
    for item in plan:
        value = {"start": float(item["start"]), "end": float(item["end"])}
        if ranges and abs(ranges[-1]["end"] - value["start"]) < 0.0005:
            ranges[-1]["end"] = value["end"]
        else:
            ranges.append(value)
    return ranges


def available_encoders(settings: Settings) -> set[str]:
    try:
        result = subprocess.run([settings.ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=20, check=True)
        return set(re.findall(r"\b(h264_[a-z0-9_]+|libx264)\b", result.stdout))
    except Exception:
        return {"libx264"}


def choose_encoder(settings: Settings, quality: str) -> tuple[str, list[str]]:
    encoders = available_encoders(settings)
    prefer_hardware = bool(settings.render.get("prefer_hardware", True))
    quality = quality if quality in {"fast", "balanced", "quality"} else "balanced"
    if prefer_hardware:
        options = [
            ("h264_nvenc", ["-preset", "p4" if quality == "fast" else "p5", "-cq", "25" if quality == "fast" else "21"]),
            ("h264_qsv", ["-preset", "faster" if quality == "fast" else "medium", "-global_quality", "25" if quality == "fast" else "21"]),
            ("h264_amf", ["-quality", "speed" if quality == "fast" else "balanced", "-qp_i", "23", "-qp_p", "23"]),
            ("h264_videotoolbox", ["-q:v", "60" if quality == "fast" else "75"]),
        ]
        for encoder, arguments in options:
            if encoder in encoders:
                return encoder, arguments
    return _software_encoder(quality)


def _software_encoder(quality: str) -> tuple[str, list[str]]:
    quality = quality if quality in {"fast", "balanced", "quality"} else "balanced"
    preset = {"fast": "veryfast", "balanced": "medium", "quality": "slow"}[quality]
    crf = {"fast": "25", "balanced": "20", "quality": "17"}[quality]
    return "libx264", ["-preset", preset, "-crf", crf]


def _dimensions(project: dict[str, Any]) -> tuple[int, int]:
    settings = project.get("settings", {})
    aspect = str(settings.get("aspect", "9:16"))
    resolution = str(settings.get("resolution", "1080"))
    if resolution not in {"720", "1080", "1440", "2160"}:
        raise ValueError("Choose 720, 1080, 1440 or 2160 resolution")
    if aspect == "source":
        source = project["sources"]["A"]
        width, height = int(_finite_float(source.get("width"))), int(_finite_float(source.get("height")))
        if width <= 0 or height <= 0:
            raise ValueError("Source A has invalid video dimensions")
        max_edge = {"720": 1280, "1080": 1920, "1440": 2560, "2160": 3840}[resolution]
        scale = min(1.0, max_edge / max(width, height))
        return max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2)
    return ASPECT_DIMENSIONS.get(aspect, ASPECT_DIMENSIONS["9:16"]).get(resolution, ASPECT_DIMENSIONS["9:16"]["1080"])


def _focus(project: dict[str, Any], slot: str, override: dict[str, float] | None = None) -> tuple[float, float, float]:
    crop = override if override is not None else project.get("manual", {}).get("crop", {}).get(slot, {})
    x = max(0.0, min(1.0, _finite_float(crop.get("x"), 0.5)))
    y = max(0.0, min(1.0, _finite_float(crop.get("y"), 0.5)))
    zoom = max(1.0, min(3.0, _finite_float(crop.get("zoom"), 1.0)))
    return x, y, zoom


def _cover_filter(width: int, height: int, focus: tuple[float, float, float]) -> str:
    x, y, zoom = focus
    scaled_w = max(width, int(width * zoom))
    scaled_h = max(height, int(height * zoom))
    return (
        f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height}:(iw-ow)*{x:.5f}:(ih-oh)*{y:.5f},setsar=1"
    )


def _fit_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1"
    )


def _clear_region_crop_filter(region: dict[str, float]) -> str:
    """Crop inward to even pixel boundaries so camera-edge pixels cannot leak.

    YUV420 normally rounds crop origins down, which can retain a row/column of
    the embedded camera when the marked border falls on an odd source pixel.
    Keep all four edges strictly inside the selected clear region instead.
    """
    x, y, width, height = (region[key] for key in ("x", "y", "w", "h"))
    left = f"ceil(iw*{x:.6f}/2)*2"
    top = f"ceil(ih*{y:.6f}/2)*2"
    right = f"floor(iw*{min(1.0, x + width):.6f}/2)*2"
    bottom = f"floor(ih*{min(1.0, y + height):.6f}/2)*2"
    return f"crop=w='max(2,{right}-{left})':h='max(2,{bottom}-{top})':x='{left}':y='{top}'"


def _source_mixer(project: dict[str, Any]) -> dict[str, str]:
    raw = project.get("manual", {}).get("source_mixer") or {}
    screen_slot = str(raw.get("screen_slot") or "A").upper()
    camera_slot = str(raw.get("camera_slot") or ("B" if screen_slot == "A" else "A")).upper()
    if {screen_slot, camera_slot} != {"A", "B"}:
        screen_slot, camera_slot = "A", "B"
    primary_role = str(raw.get("primary_role") or "screen").lower()
    if primary_role not in {"screen", "camera"}:
        primary_role = "screen"
    first_slot = str(raw.get("first_slot") or "A").upper()
    if first_slot not in {"A", "B"}:
        first_slot = "A"
    audio_slot = str(raw.get("audio_slot") or project.get("settings", {}).get("audio_source") or "A").upper()
    sources = project.get("sources", {})
    if audio_slot not in {"A", "B"} or not (sources.get(audio_slot) or {}).get("has_audio"):
        audio_slot = "A" if (sources.get("A") or {}).get("has_audio") else "B"
    return {
        "screen_slot": screen_slot,
        "camera_slot": camera_slot,
        "primary_role": primary_role,
        "audio_slot": audio_slot,
        "first_slot": first_slot,
        "stack_fit": "cover" if raw.get("stack_fit") == "cover" else "contain",
    }


def _slot_input(slot: str, index: int) -> str:
    return f"av{index}" if slot == "A" else f"bv{index}"


def _slot_times(slot: str, start: float, end: float, offset: float) -> tuple[float, float]:
    # Source B is aligned and padded onto A's timeline once before per-segment
    # splitting, so both slots use authoritative A-timeline timestamps here.
    return start, end


def _sync_offset(project: dict[str, Any]) -> float:
    manual_value = (project.get("manual", {}).get("source_mixer") or {}).get("sync_offset")
    value = manual_value if manual_value is not None else ((project.get("analysis") or {}).get("sync") or {}).get("offset", 0.0)
    offset = _finite_float(value, 0.0)
    return offset if abs(offset) <= 600 else 0.0


def _effective_audio_slot(project: dict[str, Any]) -> str | None:
    """Return the source that the filter graph can actually put on the timeline."""

    sources = project.get("sources") or {}
    source_a = sources.get("A") or {}
    source_b = sources.get("B") or {}
    if has_sequence(project) or has_source_tracks(project):
        # Removing the selected track is silence, never permission to resurrect
        # its audio from the other source or from an implicit sync mapping.
        raw = (project.get("manual") or {}).get("source_mixer") or {}
        selected = str(raw.get("audio_slot") or (project.get("settings") or {}).get("audio_source") or "A").upper()
        return selected if selected in {"A", "B"} and (sources.get(selected) or {}).get("has_audio") else None
    audio_slot = _source_mixer(project)["audio_slot"]
    source_duration = max(0.0, _finite_float(source_a.get("duration")))
    b_duration = max(0.0, _finite_float(source_b.get("duration")))
    b_overlaps = _timeline_overlap(0.0, source_duration, b_duration, _sync_offset(project))
    if audio_slot == "B" and (not source_b.get("has_audio") or not b_overlaps):
        audio_slot = "A"
    if audio_slot == "A" and not source_a.get("has_audio") and source_b.get("has_audio") and b_overlaps:
        audio_slot = "B"
    audio_source = source_a if audio_slot == "A" else source_b
    return audio_slot if audio_source.get("has_audio") else None


def _segment_nodes(
    index: int,
    item: dict[str, Any],
    width: int,
    height: int,
    project: dict[str, Any],
    has_b: bool,
    b_duration: float,
    offset: float,
) -> tuple[list[str], str]:
    start, end = float(item["start"]), float(item["end"])
    fps = project_export_fps(project)
    start_frame = int(item.get("_start_frame", math.floor(start * fps + 0.5)))
    end_frame = int(item.get("_end_frame", math.floor(end * fps + 0.5)))
    frame_trim = f"trim=start_frame={start_frame}:end_frame={end_frame}"
    camera = str(item.get("camera", "A"))
    mixer = _source_mixer(project)
    if camera == "screen":
        camera = mixer["screen_slot"]
    elif camera == "camera":
        camera = mixer["camera_slot"]
    if camera == "auto":
        camera = "A"
    if camera in {"stacked", "side_by_side", "pip", "B"} and not has_b:
        camera = "A"
    if camera == "B" and (not has_b or not _timeline_overlap(start, end, b_duration, offset)):
        camera = "A"
    a_focus, b_focus = (_focus(project, slot, item.get("crop", {}).get(slot)) for slot in ("A", "B"))
    filters: list[str] = []
    output = f"v{index}"
    if camera == "black":
        return [f"color=c=black:s={width}x{height}:r={fps},trim=end_frame={end_frame - start_frame},setpts=N/{fps}/TB,format=yuv420p[{output}]"], output

    if camera == "embedded_stack":
        draft = project.get("draft") or {}
        embedded_confirmed = bool(
            draft.get("embedded_layout_confirmed") is True
            and str(draft.get("layout") or "") == "embedded_stack"
        )
        manual = project.get("manual") if isinstance(project.get("manual"), dict) else {}
        vision = (project.get("analysis") or {}).get("vision")
        if not isinstance(vision, dict):
            vision = {}
        candidate = select_embedded_candidate(
            manual.get("embedded_camera") if isinstance(manual, dict) else None,
            vision,
            vision_version=str(vision.get("version") or "") or None,
        )
        # Legacy drafts could contain an automatically inferred embedded_stack.
        # Never duplicate a source unless a new draft records the user's explicit
        # Screen + Facecam layout choice.
        if not embedded_confirmed or not candidate:
            camera = "A"
        else:
            # Reels/TikTok convention for a gameplay + facecam recording: creator
            # camera on top, gameplay/screen below. Keep the gameplay panel larger
            # because it carries the visual information while the upper panel keeps
            # the creator readable.
            face_h = max(2, int(height * 0.30) // 2 * 2)
            content_h = height - face_h
            x = max(0.0, min(1.0, float(candidate.get("x", 0.0))))
            y = max(0.0, min(1.0, float(candidate.get("y", 0.0))))
            w = float(candidate["w"])
            h = float(candidate["h"])
            content_focus = item.get("crop", {}).get("A") or candidate.get("content_focus") or {"x": 0.5, "y": 0.5}
            content_crop_focus = (
                max(0.0, min(1.0, float(content_focus.get("x", 0.5)))),
                max(0.0, min(1.0, float(content_focus.get("y", 0.5)))),
                1.0,
            )
            filters.append(f"[av{index}]split=2[amain{index}][aface{index}]")
            filters.append(
                f"[amain{index}]{frame_trim},setpts=PTS-STARTPTS,"
                f"{_clear_region_crop_filter(candidate['content_region'])},"
                f"{_cover_filter(width, content_h, content_crop_focus)}[content{index}]"
            )
            filters.append(
                f"[aface{index}]{frame_trim},setpts=PTS-STARTPTS,"
                f"crop=iw*{w:.6f}:ih*{h:.6f}:iw*{x:.6f}:ih*{y:.6f},{_cover_filter(width, face_h, (0.5, 0.5, 1.0))}[face{index}]"
            )
            # Facecam first => top panel. Gameplay/content second => bottom panel.
            filters.append(f"[face{index}][content{index}]vstack=inputs=2,format=yuv420p[{output}]")

    if camera in {"stacked", "side_by_side", "pip"} and has_b:
        if not _timeline_overlap(start, end, b_duration, offset):
            camera = mixer["screen_slot"] if mixer["screen_slot"] == "A" else "A"
        else:
            screen_slot = mixer["screen_slot"]
            face_slot = mixer["camera_slot"]
            screen_input = _slot_input(screen_slot, index)
            face_input = _slot_input(face_slot, index)
            if camera == "stacked":
                face_ratio = 0.70 if mixer["primary_role"] == "camera" else 0.30
                face_h = max(2, int(height * face_ratio) // 2 * 2)
                screen_h = height - face_h
                face_focus = a_focus if face_slot == "A" else b_focus
                screen_focus = a_focus if screen_slot == "A" else b_focus
                face_filter = _cover_filter(width, face_h, face_focus) if mixer["stack_fit"] == "cover" or face_slot in item.get("crop", {}) else _fit_filter(width, face_h)
                screen_filter = _cover_filter(width, screen_h, screen_focus) if mixer["stack_fit"] == "cover" or screen_slot in item.get("crop", {}) else _fit_filter(width, screen_h)
                filters.append(f"[{face_input}]{frame_trim},setpts=PTS-STARTPTS,{face_filter}[face{index}]")
                filters.append(f"[{screen_input}]{frame_trim},setpts=PTS-STARTPTS,{screen_filter}[screen{index}]")
                first_label, second_label = (
                    (f"face{index}", f"screen{index}")
                    if mixer["first_slot"] == face_slot
                    else (f"screen{index}", f"face{index}")
                )
                filters.append(f"[{first_label}][{second_label}]vstack=inputs=2,format=yuv420p[{output}]")
            elif camera == "side_by_side":
                left_w = width // 2
                right_w = width - left_w
                first_is_screen = mixer["first_slot"] == screen_slot
                screen_w = left_w if first_is_screen else right_w
                face_w = right_w if first_is_screen else left_w
                screen_filter = _cover_filter(screen_w, height, a_focus if screen_slot == "A" else b_focus) if screen_slot in item.get("crop", {}) else _fit_filter(screen_w, height)
                face_filter = _cover_filter(face_w, height, a_focus if face_slot == "A" else b_focus) if face_slot in item.get("crop", {}) else _fit_filter(face_w, height)
                filters.append(f"[{screen_input}]{frame_trim},setpts=PTS-STARTPTS,{screen_filter}[screen{index}]")
                filters.append(f"[{face_input}]{frame_trim},setpts=PTS-STARTPTS,{face_filter}[face{index}]")
                first_label, second_label = (
                    (f"screen{index}", f"face{index}")
                    if first_is_screen
                    else (f"face{index}", f"screen{index}")
                )
                filters.append(f"[{first_label}][{second_label}]hstack=inputs=2,format=yuv420p[{output}]")
            else:
                pip_w = max(160, int(width * 0.34) // 2 * 2)
                pip_h = max(90, int(height * 0.28) // 2 * 2)
                primary_role = mixer["primary_role"]
                base_slot = mixer[f"{primary_role}_slot"]
                inset_slot = mixer["camera_slot" if primary_role == "screen" else "screen_slot"]
                base_input = _slot_input(base_slot, index)
                inset_input = _slot_input(inset_slot, index)
                base_focus = a_focus if base_slot == "A" else b_focus
                filters.append(f"[{base_input}]{frame_trim},setpts=PTS-STARTPTS,{_cover_filter(width, height, base_focus)}[base{index}]")
                inset_filter = _cover_filter(pip_w, pip_h, a_focus if inset_slot == "A" else b_focus) if inset_slot in item.get("crop", {}) else _fit_filter(pip_w, pip_h)
                filters.append(f"[{inset_input}]{frame_trim},setpts=PTS-STARTPTS,{inset_filter}[inset{index}]")
                filters.append(f"[base{index}][inset{index}]overlay=W-w-32:H-h-32:shortest=1,format=yuv420p[{output}]")
    if camera == "A":
        filters.append(f"[av{index}]{frame_trim},setpts=PTS-STARTPTS,{_cover_filter(width, height, a_focus)},format=yuv420p[{output}]")
    elif camera == "B":
        filters.append(f"[bv{index}]{frame_trim},setpts=PTS-STARTPTS,{_cover_filter(width, height, b_focus)},format=yuv420p[{output}]")
    return filters, output



def _segment_audio_filters(project: dict[str, Any], start: float, end: float) -> str:
    draft = project.get("draft") or {}
    chain: list[str] = []
    for action in draft.get("audio_plan") or []:
        try:
            action_start = float(action.get("start", 0))
            action_end = float(action.get("end", 0))
            gain_db = float(action.get("gain_db", 0))
        except (TypeError, ValueError):
            continue
        overlap_start = max(start, action_start)
        overlap_end = min(end, action_end)
        if overlap_end - overlap_start < 0.03 or abs(gain_db) < 0.05:
            continue
        local_start = max(0.0, overlap_start - start)
        local_end = max(local_start, overlap_end - start)
        multiplier = 10 ** (gain_db / 20.0)
        chain.append(f"volume={multiplier:.6f}:enable='between(t,{local_start:.6f},{local_end:.6f})'")
    return ",".join(chain)


def _audio_plan_matches_timeline(project: dict[str, Any], audio_slot: str, offset: float) -> bool:
    """Whether Director gain decisions still describe the selected audio clock."""

    draft = project.get("draft") or {}
    if has_sequence(project) or has_source_tracks(project):
        # Director gain envelopes describe the old clock, not moved clips.
        return False
    if str(draft.get("audio_source") or "A").upper() != audio_slot:
        return False
    if audio_slot != "B":
        return True
    analyzed_value = (project.get("analysis") or {}).get("audio_timeline_offset")
    analyzed_offset = _finite_float(analyzed_value, math.nan)
    return math.isfinite(analyzed_offset) and abs(analyzed_offset - offset) <= 0.001


def _validate_caption_timeline(project: dict[str, Any]) -> None:
    """Block captions whose transcript was mapped against an older audio clock."""

    settings = project.get("settings") or {}
    if not settings.get("captions") and not settings.get("burn_captions"):
        return
    analysis = project.get("analysis") or {}
    transcript = analysis.get("transcript") or {}
    if not isinstance(transcript.get("segments"), list) or not transcript.get("segments"):
        return

    current_slot = _effective_audio_slot(project)
    analyzed_slot = str(
        analysis.get("audio_source")
        or (project.get("draft") or {}).get("audio_source")
        or "A"
    ).upper()
    if current_slot is None or analyzed_slot != current_slot:
        raise RuntimeError("captions_out_of_date")
    if current_slot == "B":
        analyzed_offset = _finite_float(analysis.get("audio_timeline_offset"), math.nan)
        if not math.isfinite(analyzed_offset) or (not (has_sequence(project) or has_source_tracks(project)) and abs(analyzed_offset - _sync_offset(project)) > 0.001):
            raise RuntimeError("captions_out_of_date")


def _caption_transcript(project: dict[str, Any]) -> dict[str, Any]:
    """Project analyzed speech through the selected audio track, without mutation.

    Transcript B timestamps already contain the analyzed sync offset. Undo that
    old mapping first, then follow each clip's source window to its new position.
    Repeated clips repeat their captions; removed audio never leaves stale text.
    """
    analysis = project.get("analysis") or {}
    transcript = analysis.get("transcript") or {}
    if not (has_sequence(project) or has_source_tracks(project)):
        return transcript
    slot = _effective_audio_slot(project)
    analyzed_slot = str(analysis.get("audio_source") or (project.get("draft") or {}).get("audio_source") or "A").upper()
    if slot is None or slot != analyzed_slot:
        return {**transcript, "segments": []}
    offset = _finite_float(analysis.get("audio_timeline_offset")) if slot == "B" else 0.0
    segments: list[dict[str, Any]] = []
    for clip in source_track_clips(project, slot):
        source_start = float(clip["source_start"]) + offset
        source_end = source_start + float(clip["end"]) - float(clip["start"])
        shift = float(clip["start"]) - source_start
        for segment in transcript.get("segments") or []:
            start = max(source_start, _finite_float(segment.get("start")))
            end = min(source_end, _finite_float(segment.get("end")))
            if end <= start:
                continue
            words = segment.get("words") or []
            if words:
                mapped_words = []
                for word in words:
                    left, right = _finite_float(word.get("start")), _finite_float(word.get("end"))
                    if not source_start <= (left + right) / 2 < source_end or right <= left:
                        continue
                    mapped_words.append({**word, "start": max(source_start, left) + shift, "end": min(source_end, right) + shift})
                if not mapped_words:
                    continue
                segments.append({**segment, "start": mapped_words[0]["start"], "end": mapped_words[-1]["end"],
                                 "text": " ".join(str(word.get("word") or "").strip() for word in mapped_words), "words": mapped_words})
            else:
                segments.append({**segment, "start": start + shift, "end": end + shift})
    segments.sort(key=lambda row: (row["start"], row["end"]))
    return {**transcript, "segments": segments}


def _source_track_master(project: dict[str, Any], slot: str, *, audio: bool, output: str) -> list[str]:
    """Assemble one track on the full A clock; gaps are generated, not frozen.

    Bound every piece by output frames (or matching 48 kHz samples) before
    concatenation, avoiding per-clip rounding accumulating at 60 fps.
    """
    fps = project_export_fps(project)
    duration = timeline_duration(project)
    total_frames = int(math.floor(duration * fps + 0.5))
    source = (project.get("sources") or {}).get(slot) or {}
    source_duration = _finite_float(source.get("duration")) if audio else _source_video_duration(source)
    pieces: list[tuple[int, int, float | None, float]] = []
    cursor = 0
    for clip in source_track_clips(project, slot):
        raw_start = float(clip["start"])
        real_end = min(float(clip["end"]), raw_start + source_duration - float(clip["source_start"]))
        speed = float(clip.get("video_speed", 1)) if not audio else 1.0
        picture_clock = not audio and "video_speed" in clip
        if picture_clock:
            real_end = float(clip["end"])
        start = max(cursor, min(total_frames, int(math.floor(raw_start * fps + 0.5))))
        end = min(total_frames, int(math.floor(real_end * fps + 0.5)))
        if end <= start:
            continue
        if start > cursor:
            pieces.append((cursor, start, None, 1.0))
        source_start = max(0.0, float(clip["source_start"]) + start / fps - raw_start)
        if picture_clock:
            source_start = min(max(0.0, source_duration - 1 / fps), max(0.0, float(clip.get("video_source_start", clip["source_start"])) + (start / fps - raw_start) * speed))
        pieces.append((start, end, source_start, speed))
        cursor = end
    if cursor < total_frames:
        pieces.append((cursor, total_frames, None, 1.0))
    real_count = sum(source_start is not None for _, _, source_start, _ in pieces)
    prefix = f"track{slot}{'a' if audio else 'v'}"
    media = "a" if audio else "v"
    index = 0 if slot == "A" else 1
    filters = []
    if real_count:
        labels = "".join(f"[{prefix}in{i}]" for i in range(real_count))
        split = f"{'asplit' if audio else 'split'}={real_count}" if real_count > 1 else ("anull" if audio else "null")
        filters.append(f"[{index}:{media}]{split}{labels}")
    width = max(2, int(_finite_float(source.get("width"), 2)) // 2 * 2)
    height = max(2, int(_finite_float(source.get("height"), 2)) // 2 * 2)
    real_index = 0
    for piece_index, (start, end, source_start, speed) in enumerate(pieces):
        frames = end - start
        length = frames / fps
        label = f"{prefix}piece{piece_index}"
        if audio:
            samples = int(round(length * 48000))
            if source_start is None:
                chain = "anullsrc=r=48000:cl=stereo"
            else:
                chain = (f"[{prefix}in{real_index}]atrim=start={source_start:.9f}:end={source_start + length:.9f},"
                         "asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad")
            filters.append(f"{chain},atrim=end_sample={samples},asetpts=N/48000/TB[{label}]")
        else:
            if source_start is None:
                chain = f"color=c=black:s={width}x{height}:r={fps}"
            else:
                chain = (f"[{prefix}in{real_index}]trim=start={source_start:.9f}:end={source_start + length * speed + 1/fps:.9f},"
                         f"setpts=(PTS-STARTPTS)/{speed:.9f},fps={fps},scale={width}:{height},setsar=1,"
                         f"tpad=stop_mode=clone:stop_duration={length + 2/fps:.9f}")
            filters.append(f"{chain},trim=end_frame={frames},setpts=N/{fps}/TB,format=yuv420p[{label}]")
        if source_start is not None:
            real_index += 1
    concat = "".join(f"[{prefix}piece{i}]" for i in range(len(pieces)))
    filters.append(f"{concat}concat=n={len(pieces)}:v={0 if audio else 1}:a={1 if audio else 0}[{output}]")
    return filters


def _final_audio_filter(project: dict[str, Any]) -> str:
    policy = (project.get("draft") or {}).get("audio_policy") or {}
    if not policy.get("normalize"):
        return "anull"
    try:
        target = max(-24.0, min(-10.0, float(policy.get("target_lufs", -16.0))))
    except (TypeError, ValueError):
        target = -16.0
    result = f"loudnorm=I={target:.1f}:LRA=11:TP=-1.5"
    gain_db = master_gain_db(project)
    if gain_db:
        result += f",volume={gain_db:.6f}dB,alimiter=limit=0.98:level=0:latency=1"
    return result


def _render_effects_payload(project: dict[str, Any]) -> dict[str, Any]:
    # Automatic effects were authored against source-clock Story beats. Their
    # timestamps cannot be reused after arbitrary sequence rearrangement.
    if has_sequence(project) or (project.get("settings") or {}).get("editorial_effects", True) is False:
        return {"effects": [], "filter_expression": None}
    return compile_automatic_effects(project)

def build_filter_graph(project: dict[str, Any], width: int, height: int, caption_ass: Path | None = None) -> tuple[str, list[str], bool]:
    fps = project_export_fps(project)
    draft = project.get("draft") or {}
    plan = _frame_aligned_plan(project)
    source_a = project["sources"]["A"]
    source_b = project["sources"].get("B") or {}
    mixer = _source_mixer(project)
    audio_slot = _effective_audio_slot(project)
    source_duration = timeline_duration(project)
    b_duration = _source_video_duration(source_b)
    offset = _sync_offset(project)
    independent = has_sequence(project) or has_source_tracks(project)
    if independent:
        # Both masters already live on the edit axis, irrespective of their
        # source-local windows or the old global B synchronization offset.
        b_duration, offset = source_duration, 0.0
    b_video_available = _source_has_video(source_b) and _timeline_overlap(0.0, source_duration, b_duration, offset)
    b_video_requested = any(
        str(item.get("camera") or "A") in {"B", "stacked", "side_by_side", "pip"}
        or (str(item.get("camera") or "A") == "screen" and mixer["screen_slot"] == "B")
        or (str(item.get("camera") or "A") == "camera" and mixer["camera_slot"] == "B")
        for item in plan
    )
    # Avoid decoding/compositing B when every kept segment uses A. This matters
    # for long YouTube cleanups and machines with modest RAM/CPU.
    has_b = b_video_available and b_video_requested
    has_audio = audio_slot is not None
    n = len(plan)
    segment_nodes = [
        _segment_nodes(index, item, width, height, project, has_b, b_duration, offset)
        for index, item in enumerate(plan)
    ]
    a_indices = [
        index for index, (nodes, _) in enumerate(segment_nodes)
        if any(f"[av{index}]" in node for node in nodes)
    ]
    b_indices = [
        index for index, (nodes, _) in enumerate(segment_nodes)
        if any(f"[bv{index}]" in node for node in nodes)
    ]
    output_frames = sum(int(item["_end_frame"]) - int(item["_start_frame"]) for item in plan)
    effects_payload = _render_effects_payload(project)
    effect_expression = effects_payload.get("filter_expression")
    finalized_video_label = "vbase" if effect_expression else "vout"
    finalize_video = (
        # Give fps enough EOF runway to emit the final planned frame; trim then
        # enforces the exact frame budget so this padding never leaks out.
        f"tpad=stop_mode=clone:stop_duration={2 / fps:.6f},"
        f"fps={fps},trim=end_frame={output_frames},setpts=N/{fps}/TB"
    )
    filters: list[str] = []
    if independent:
        if a_indices:
            filters.extend(_source_track_master(project, "A", audio=False, output="amasterv"))
        if has_b:
            filters.extend(_source_track_master(project, "B", audio=False, output="bmaster"))
        if has_audio:
            filters.extend(_source_track_master(project, audio_slot, audio=True, output="amaster"))
    else:
        filters.append(
            f"[0:v]setpts=PTS-STARTPTS,fps={fps},"
            f"tpad=stop_mode=clone:stop_duration={source_duration:.6f},"
            f"trim=duration={source_duration:.6f},setpts=N/{fps}/TB,setsar=1[amasterv]"
        )
    if has_b and not independent:
        b_width = max(2, int(_finite_float(source_b.get("width"))) // 2 * 2)
        b_height = max(2, int(_finite_float(source_b.get("height"))) // 2 * 2)
        filters.append(
            f"color=c=black:s={b_width}x{b_height}:r={fps}:d={source_duration:.6f},setsar=1[bcanvas]"
        )
        if offset > 0.0:
            filters.append(
                f"[1:v]setpts=PTS-STARTPTS+{offset:.6f}/TB,setsar=1[bshifted]"
            )
        elif offset < 0.0:
            filters.append(
                f"[1:v]trim=start={abs(offset):.6f},setpts=PTS-STARTPTS,setsar=1[bshifted]"
            )
        else:
            filters.append("[1:v]setpts=PTS-STARTPTS,setsar=1[bshifted]")
        filters.append(
            f"[bcanvas][bshifted]overlay=x=0:y=0:eof_action=pass:shortest=0,"
            f"trim=duration={source_duration:.6f},fps={fps},"
            f"setpts=N/{fps}/TB[bmaster]"
        )
    if has_audio and not independent:
        if audio_slot == "B":
            if offset >= 0:
                delay_ms = max(0, int(round(offset * 1000)))
                filters.append(
                    f"[1:a]asetpts=PTS-STARTPTS,adelay={delay_ms}:all=1,apad,"
                    f"atrim=duration={source_duration:.6f},asetpts=N/SR/TB[amaster]"
                )
            else:
                filters.append(
                    f"[1:a]atrim=start={abs(offset):.6f},asetpts=PTS-STARTPTS,apad,"
                    f"atrim=duration={source_duration:.6f},asetpts=N/SR/TB[amaster]"
                )
        else:
            filters.append(
                f"[0:a]asetpts=PTS-STARTPTS,apad,atrim=duration={source_duration:.6f},"
                "asetpts=N/SR/TB[amaster]"
            )
    if independent:
        if len(a_indices) == 1:
            filters.append(f"[amasterv]null[av{a_indices[0]}]")
        elif a_indices:
            filters.append(f"[amasterv]split={len(a_indices)}" + "".join(f"[av{i}]" for i in a_indices))
        if has_audio:
            filters.append(f"[amaster]asplit={n}" + "".join(f"[aa{i}]" for i in range(n)))
    elif n == 1:
        filters.append("[amasterv]null[av0]")
        if has_audio:
            filters.append("[amaster]anull[aa0]")
    else:
        filters.append(f"[amasterv]split={n}" + "".join(f"[av{i}]" for i in range(n)))
        if has_audio:
            filters.append(f"[amaster]asplit={n}" + "".join(f"[aa{i}]" for i in range(n)))
    if has_b:
        # B's padded canvas is an internal video source. Sending unused branches
        # to nullsink can keep that source running after every external input has
        # reached EOF and crash FFmpeg's scheduler. Route only real consumers.
        if len(b_indices) == 1:
            filters.append(f"[bmaster]null[bv{b_indices[0]}]")
        else:
            filters.append(f"[bmaster]split={len(b_indices)}" + "".join(f"[bv{i}]" for i in b_indices))
    video_nodes: list[str] = []
    audio_nodes: list[str] = []
    for index, item in enumerate(plan):
        segment_filters, video_node = segment_nodes[index]
        # Every output produced by split/asplit must be connected. A camera-only
        # segment intentionally leaves the other video source unused, so consume
        # that branch with nullsink instead of letting FFmpeg reject the graph.
        uses_a = any(f"[av{index}]" in node for node in segment_filters)
        filters.extend(segment_filters)
        if not uses_a and not independent:
            filters.append(f"[av{index}]nullsink")
        video_nodes.append(f"[{video_node}]")
        if has_audio:
            start, end = float(item["start"]), float(item["end"])
            gain_filters = (
                _segment_audio_filters(project, start, end)
                if _audio_plan_matches_timeline(project, audio_slot, offset)
                else ""
            )
            suffix = f",{gain_filters}" if gain_filters else ""
            # AAC packets may carry encoder-delay timestamps even after a
            # PTS-STARTPTS reset.  Rebuilding timestamps from the decoded
            # sample count keeps every concatenated segment monotonic.  This
            # is especially important before loudnorm: a backward audio DTS
            # otherwise makes FFmpeg's -shortest truncate the video too.
            filters.append(
                f"[aa{index}]atrim=start={start:.6f}:end={end:.6f},"
                f"asetpts=N/SR/TB{suffix}[a{index}]"
            )
            audio_nodes.append(f"[a{index}]")
    if has_audio:
        filters.append("".join(value for pair in zip(video_nodes, audio_nodes) for value in pair) + f"concat=n={n}:v=1:a=1[vcat][acat]")
        filters.append(f"[vcat]{finalize_video}[{finalized_video_label}]")
        # Repair any real capture-clock drift once, after the edit has been
        # assembled. Running async resampling inside every fragment interacts
        # badly with concat + loudnorm on FFmpeg 7 and can generate backward
        # DTS values. A single post-concat pass keeps timestamps monotonic.
        audio_runway = output_frames / fps + 2 / fps
        filters.append(
            f"[acat]aresample=async=1:first_pts=0,anull,"
            f"apad,atrim=duration={audio_runway:.6f},asetpts=N/SR/TB[aout]"
        )
    else:
        filters.append("".join(video_nodes) + f"concat=n={n}:v=1:a=0[vcat]")
        filters.append(f"[vcat]{finalize_video}[{finalized_video_label}]")

    if effect_expression:
        filters.append(f"[vbase]{effect_expression}[vout]")

    video_map = "[vout]"
    media_filters, video_map, audio_map = append_media_graph(
        project, width, height, output_frames / fps, video_map, "[aout]" if has_audio else None,
    )
    filters.extend(media_filters)
    has_audio = audio_map is not None
    if caption_ass is not None:
        value = caption_ass.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"{video_map}ass=filename='{value}'[vfinal]")
        video_map = "[vfinal]"
    maps = ["-map", video_map]
    if has_audio:
        maps += ["-map", audio_map]
    return ";\n".join(filters), maps, has_audio


def _expected_output_duration(project: dict[str, Any]) -> float:
    try:
        return sum(max(0.0, float(item["end"]) - float(item["start"])) for item in _frame_aligned_plan(project))
    except (KeyError, TypeError, ValueError):
        return 0.0


def _verify_output_metadata(
    metadata: dict[str, Any],
    *,
    width: int,
    height: int,
    expected_duration: float,
    expected_audio: bool,
    expected_fps: int | None = None,
) -> None:
    """Reject truncated streams, not only a plausible-looking container tail."""

    if int(metadata.get("width") or 0) != width or int(metadata.get("height") or 0) != height:
        raise RuntimeError(
            f"Rendered dimensions verification failed: expected {width}x{height}, "
            f"got {metadata.get('width')}x{metadata.get('height')}"
        )
    if expected_audio and metadata.get("has_audio") is False:
        raise RuntimeError("Rendered audio verification failed: the expected audio stream is missing")
    if expected_fps is not None and abs(_finite_float(metadata.get("fps")) - expected_fps) > 0.001:
        raise RuntimeError(
            f"Rendered frame rate verification failed: expected {expected_fps} FPS, "
            f"got {metadata.get('fps')}"
        )

    tolerance = 0.15
    durations: list[tuple[str, float]] = [
        ("container", _finite_float(metadata.get("duration"))),
        ("video", _finite_float(metadata.get("video_duration"), _finite_float(metadata.get("duration")))),
    ]
    if expected_audio and metadata.get("audio_duration") is not None:
        durations.append(("audio", _finite_float(metadata.get("audio_duration"))))
    for label, actual_duration in durations:
        if expected_duration > 0.0 and abs(actual_duration - expected_duration) > tolerance:
            raise RuntimeError(
                f"Rendered {label} duration verification failed: "
                f"expected {expected_duration:.3f}s, got {actual_duration:.3f}s"
            )


def _parse_bitrate_bps(value: Any, fallback: int = 192_000) -> int:
    """Parse FFmpeg-style bitrates such as ``192k`` without underestimating them."""

    match = re.fullmatch(
        r"\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMgG]?)\s*(?:b(?:it)?(?:/s|ps)?)?\s*",
        str(value or ""),
    )
    if not match:
        return max(0, int(fallback))
    number = float(match.group(1))
    multiplier = {"": 1, "k": 1_000, "m": 1_000_000, "g": 1_000_000_000}[match.group(2).lower()]
    bits_per_second = number * multiplier
    if not math.isfinite(bits_per_second):
        return max(0, int(fallback))
    return max(0, int(math.ceil(bits_per_second)))


def _serialized_size(value: Any, fallback: int = 0) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError, OverflowError):
        return max(0, int(fallback))


def _estimate_render_storage(
    project: dict[str, Any],
    width: int,
    height: int,
    quality: str,
    settings: Settings,
) -> dict[str, Any]:
    """Estimate peak additional disk allocation for one render.

    CUTROOM writes one partial MP4 and renames that same file into place, so the
    estimate deliberately does not count a second full-size final MP4. It does
    include encoding variability/container space, filter and caption files, the
    optional SRT sidecar, and the atomic project-state commit.
    """

    plan = _frame_aligned_plan(project)
    duration = sum(max(0.0, float(item["end"]) - float(item["start"])) for item in plan)
    if not math.isfinite(duration) or duration <= 0.0:
        raise ValueError("The edit has no valid output duration to render")
    if width <= 0 or height <= 0:
        raise ValueError("The render dimensions are invalid")
    quality = quality if quality in {"fast", "balanced", "quality"} else "balanced"

    # Every graph output is normalized to the selected FPS. These bits-per-pixel
    # rates plus the margin below are intentionally above common CRF output rates,
    # including high-motion gameplay, without reserving raw-video-sized space.
    bits_per_pixel = {"fast": 0.13, "balanced": 0.24, "quality": 0.40}[quality]
    fps = project_export_fps(project)
    video_bitrate = max(1_000_000.0, float(width) * float(height) * fps * bits_per_pixel)
    render_config = getattr(settings, "render", {}) or {}
    has_audio = _effective_audio_slot(project) is not None or library_has_audio(project)
    audio_bitrate = _parse_bitrate_bps(render_config.get("audio_bitrate", "192k")) if has_audio else 0
    video_bytes_float = duration * video_bitrate / 8.0
    audio_bytes_float = duration * audio_bitrate / 8.0
    if not math.isfinite(video_bytes_float + audio_bytes_float):
        raise ValueError("The render is too large to estimate safely")
    video_bytes = int(math.ceil(video_bytes_float))
    audio_bytes = int(math.ceil(audio_bytes_float))
    encoded_payload = video_bytes + audio_bytes
    encoding_margin_bytes = max(2 * 1024**2, int(math.ceil(encoded_payload * 0.30)))
    output_bytes = encoded_payload + encoding_margin_bytes

    transcript = _caption_transcript(project)
    segments = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
    transcript_bytes = _serialized_size(transcript, fallback=len(segments) * 256)
    project_settings = project.get("settings") or {}
    ass_bytes = 0
    if project_settings.get("burn_captions") and segments:
        ass_bytes = max(256 * 1024, transcript_bytes * 3 + len(segments) * 256)
    srt_bytes = 0
    if project_settings.get("captions") and segments:
        srt_bytes = max(128 * 1024, transcript_bytes * 2 + len(segments) * 128)

    # Complex layouts generate several filter clauses per fragment. The real
    # files are normally much smaller; this upper allowance also covers filesystem
    # allocation blocks and future small additions to the graph.
    filter_graph_bytes = 256 * 1024 + len(plan) * 16 * 1024
    project_json_bytes = _serialized_size(project, fallback=512 * 1024)
    project_commit_bytes = max(1024**2, project_json_bytes * 2 + 256 * 1024)
    normalize_audio = has_audio and _final_audio_filter(project) != "anull"
    normalization_stage_bytes = output_bytes if normalize_audio else 0
    export_work_bytes = output_bytes + normalization_stage_bytes + srt_bytes
    project_work_bytes = filter_graph_bytes + ass_bytes + project_commit_bytes

    reserve_mb = _finite_float(render_config.get("min_free_mb"), 256.0)
    reserve_bytes = int(min(4096.0, max(0.0, reserve_mb)) * 1024**2)
    return {
        "duration_seconds": duration,
        "width": int(width),
        "height": int(height),
        "quality": quality,
        "frame_rate": fps,
        "has_audio": has_audio,
        "video_bytes": video_bytes,
        "audio_bytes": audio_bytes,
        "encoding_margin_bytes": encoding_margin_bytes,
        "output_bytes": output_bytes,
        "normalization_stage_bytes": normalization_stage_bytes,
        "filter_graph_bytes": filter_graph_bytes,
        "caption_ass_bytes": ass_bytes,
        "caption_srt_bytes": srt_bytes,
        "project_commit_bytes": project_commit_bytes,
        "export_work_bytes": export_work_bytes,
        "project_work_bytes": project_work_bytes,
        "reserve_bytes": reserve_bytes,
    }


def _existing_storage_location(path: Path) -> Path:
    """Return the nearest existing ancestor accepted by ``disk_usage``."""

    candidate = Path(path).resolve(strict=False)
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    if not candidate.exists():
        raise OSError(f"Cannot locate a filesystem for {path}")
    return candidate


def _storage_volume_key(location: Path) -> tuple[Any, ...]:
    resolved = location.resolve(strict=False)
    try:
        device = int(resolved.stat().st_dev)
    except OSError:
        device = -1
    # st_dev distinguishes POSIX mount points; the anchor also prevents Windows
    # runtimes that report a generic device id from merging separate drives.
    return device, os.path.normcase(resolved.anchor or str(resolved))


def _ensure_render_storage(
    project: dict[str, Any],
    settings: Settings,
    project_dir: Path,
    width: int,
    height: int,
    quality: str,
) -> dict[str, Any]:
    """Require enough free space on every volume touched by the render."""

    estimate = _estimate_render_storage(project, width, height, quality, settings)
    volumes: dict[tuple[Any, ...], dict[str, Any]] = {}
    allocations = (
        (Path(settings.exports_dir), int(estimate["export_work_bytes"])),
        (Path(project_dir), int(estimate["project_work_bytes"])),
    )
    for requested_location, working_bytes in allocations:
        location = _existing_storage_location(requested_location)
        key = _storage_volume_key(location)
        item = volumes.setdefault(key, {"location": location, "working_bytes": 0})
        item["working_bytes"] += max(0, working_bytes)

    volume_details: list[dict[str, Any]] = []
    for item in volumes.values():
        location = Path(item["location"])
        free_bytes = max(0, int(shutil.disk_usage(location).free))
        required_bytes = int(item["working_bytes"]) + int(estimate["reserve_bytes"])
        detail = {
            "location": str(location),
            "working_bytes": int(item["working_bytes"]),
            "reserve_bytes": int(estimate["reserve_bytes"]),
            "required_bytes": required_bytes,
            "free_bytes": free_bytes,
        }
        volume_details.append(detail)
        if free_bytes < required_bytes:
            raise InsufficientStorageError(
                required_bytes=required_bytes,
                free_bytes=free_bytes,
                location=location,
            )
    estimate["volumes"] = volume_details
    return estimate


def ensure_render_storage(
    project: dict[str, Any],
    settings: Settings,
    project_dir: Path,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Public preflight used by both HTTP admission and the render worker."""

    options = options or {}
    project = with_export_options(project, options)
    _validate_caption_timeline(project)
    width, height = _dimensions(project)
    quality = str(options.get("quality") or project.get("settings", {}).get("quality", "balanced"))
    return _ensure_render_storage(project, settings, project_dir, width, height, quality)


def _render_input_fingerprint(project: dict[str, Any]) -> str:
    """Identify every project field that can change the rendered pixels/audio."""
    settings = project.get("settings") or {}
    analysis = project.get("analysis") or {}
    manual = project.get("manual") or {}
    return stable_fingerprint(
        "render-input-2026-09-05.fps",
        {
            "sources": project.get("sources"),
            "assets": project.get("assets"),
            "draft": project.get("draft"),
            "settings": {
                key: settings.get(key)
                for key in (
                    "aspect", "resolution", "quality", "fps", "captions", "burn_captions", "editorial_effects",
                    "caption_style", "caption_position", "caption_scale", "caption_words_per_line",
                )
            },
            "manual": {
                "crop": manual.get("crop"),
                "source_mixer": manual.get("source_mixer"),
                "source_tracks": manual.get("source_tracks"),
                "sequence": manual.get("sequence"),
                "camera_overrides": manual.get("camera_overrides"),
                "media_clips": manual.get("media_clips"),
                "audio_mixer": manual.get("audio_mixer"),
            },
            "transcript": analysis.get("transcript") if settings.get("captions") or settings.get("burn_captions") else None,
            "caption_provenance": {
                "audio_source": analysis.get("audio_source"),
                "audio_timeline_offset": analysis.get("audio_timeline_offset"),
            } if settings.get("captions") or settings.get("burn_captions") else None,
            "story_beats": analysis.get("story_beats") if settings.get("editorial_effects", True) is not False else None,
        },
    )


def _parse_progress_seconds(line: str) -> float | None:
    key, sep, value = line.strip().partition("=")
    if not sep or key not in {"out_time_ms", "out_time_us"}:
        return None
    try:
        return max(0.0, int(value) / 1_000_000.0)
    except ValueError:
        return None


def _run_ffmpeg_process(context: JobContext, command: list[str], expected_duration: float) -> tuple[int, str]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=creationflags,
    )
    progress_lines: queue.Queue[str] = queue.Queue()
    stderr_lines: list[str] = []

    def read_stdout() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            progress_lines.put(line)

    def read_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_lines.append(line)
            if len(stderr_lines) > 300:
                del stderr_lines[:100]

    stdout_thread = threading.Thread(target=read_stdout, name="cutroom-ffmpeg-progress", daemon=True)
    stderr_thread = threading.Thread(target=read_stderr, name="cutroom-ffmpeg-stderr", daemon=True)
    stdout_thread.start()
    stderr_thread.start()
    last_seconds = 0.0
    last_heartbeat = time.monotonic()

    try:
        while process.poll() is None:
            if context.job.cancel_event.wait(0.20):
                process.terminate()
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                raise JobCancelled("Render cancelled")

            newest_seconds: float | None = None
            while True:
                try:
                    line = progress_lines.get_nowait()
                except queue.Empty:
                    break
                seconds = _parse_progress_seconds(line)
                if seconds is not None:
                    newest_seconds = seconds

            if newest_seconds is not None:
                last_seconds = max(last_seconds, newest_seconds)
                ratio = min(1.0, last_seconds / expected_duration) if expected_duration > 0 else 0.0
                progress = min(0.95, 0.04 + ratio * 0.91)
                context.update(progress, f"Rendering... {last_seconds:.1f}s / {expected_duration:.1f}s" if expected_duration > 0 else "Rendering...")
                last_heartbeat = time.monotonic()
            elif time.monotonic() - last_heartbeat >= 5.0:
                context.update(context.job.progress, "Rendering... still working")
                last_heartbeat = time.monotonic()

        # Drain any final progress lines after FFmpeg exits.
        while True:
            try:
                line = progress_lines.get_nowait()
            except queue.Empty:
                break
            seconds = _parse_progress_seconds(line)
            if seconds is not None:
                last_seconds = max(last_seconds, seconds)

        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        return int(process.returncode or 0), "".join(stderr_lines)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


class _ScaledProgressContext:
    """Map one FFmpeg phase into a monotonic slice of the render progress."""

    def __init__(self, context: JobContext, start: float, end: float, label: str):
        self.context = context
        self.job = context.job
        self.start = start
        self.end = end
        self.label = label

    def update(self, progress: float, message: str) -> None:
        ratio = max(0.0, min(1.0, (progress - 0.04) / 0.91))
        mapped = self.start + (self.end - self.start) * ratio
        self.context.update(mapped, f"{self.label}: {message}" if self.label else message)


def render_project(context: JobContext, project_id: str, store: ProjectStore, settings: Settings, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    project = store.load(project_id)
    saved_input_fingerprint = _render_input_fingerprint(project)
    project = with_export_options(project, options)
    render_input_fingerprint = _render_input_fingerprint(project)
    fps = project_export_fps(project)
    if not project.get("sources", {}).get("A"):
        raise ValueError("Source A is required")
    if has_sequence(project) and timeline_duration(project) <= 0:
        raise ValueError("Add footage to the timeline before exporting")
    source_a = store.project_dir(project_id) / project["sources"]["A"]["relative_path"]
    if not source_a.is_file():
        raise FileNotFoundError(f"Source A media is missing: {source_a.name}")
    source_b_info = project.get("sources", {}).get("B")
    source_b = store.project_dir(project_id) / source_b_info["relative_path"] if source_b_info else None
    if source_b is not None and not source_b.is_file():
        raise FileNotFoundError(f"Source B media is missing: {source_b.name}")
    media_inputs = library_input_args(project, store.project_dir(project_id))
    width, height = _dimensions(project)
    quality = str(options.get("quality") or project.get("settings", {}).get("quality", "balanced"))
    context.check_cancelled()
    ensure_render_storage(project, settings, store.project_dir(project_id), options)
    encoder, encoder_args = _software_encoder(quality) if options.get("_force_software") else choose_encoder(settings, quality)
    export_id = new_id("export")
    caption_ass: Path | None = None
    transcript = _caption_transcript(project)
    caption_ranges = _caption_ranges(project)
    caption_settings = normalize_caption_settings(project.get("settings"))
    try:
        if project.get("settings", {}).get("burn_captions") and transcript and transcript.get("segments"):
            caption_ass = store.project_dir(project_id) / "cache" / f"captions-{export_id}.ass"
            build_ass(
                transcript,
                caption_ranges,
                caption_ass,
                width,
                height,
                layout_ranges=_frame_aligned_plan(project),
                caption_style=caption_settings["caption_style"],
                caption_position=caption_settings["caption_position"],
                caption_scale=caption_settings["caption_scale"],
                words_per_caption=caption_settings["caption_words_per_line"],
            )
        graph, maps, has_audio = build_filter_graph(project, width, height, caption_ass)
    except BaseException:
        if caption_ass is not None:
            caption_ass.unlink(missing_ok=True)
        raise
    safe_name = sanitize_filename(project.get("name", "cutroom-edit"))
    output = settings.exports_dir / f"{safe_name}-{export_id[-8:]}.mp4"
    partial = output.with_suffix(".partial.mp4")
    normalization_stage = settings.exports_dir / f".{safe_name}-{export_id[-8:]}.render-stage.mp4"
    caption_path: Path | None = None
    output_committed = False
    graph_path = store.project_dir(project_id) / "cache" / f"filter-{export_id}.txt"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        graph_path.write_text(graph, encoding="utf-8")
    except BaseException:
        if caption_ass is not None:
            caption_ass.unlink(missing_ok=True)
        graph_path.unlink(missing_ok=True)
        raise
    expected_duration = _expected_output_duration(project)
    normalization_filter = _final_audio_filter(project) if has_audio else "anull"
    normalize_audio = has_audio and normalization_filter != "anull"
    render_target = normalization_stage if normalize_audio else partial
    command = [settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_a)]
    needs_source_b_input = "[1:v]" in graph or "[1:a]" in graph or bool(library_clips(project))
    if source_b and needs_source_b_input:
        command += ["-i", str(source_b)]
    command += media_inputs
    command += [
        "-filter_complex_script", str(graph_path), *maps,
        "-c:v", encoder, *encoder_args,
        # Emit a real CFR stream with a decodable terminal frame. Passthrough
        # can leave the last packet marked discard in MP4; CFR output is supported
        # by FFmpeg 4.4 and matches the graph's explicit frame contract.
        "-vsync", "1", "-r:v", str(fps),
        "-threads", str(max(1, int(settings.raw.get("ffmpeg_threads", 4)))),
    ]
    if has_audio:
        command += ["-c:a", "aac", "-b:a", str(settings.render.get("audio_bitrate", "192k"))]
    command += [
        "-movflags", "+faststart", "-map_metadata", "-1", "-map_chapters", "-1",
        # Both graph streams are bounded and padded. An explicit edit duration
        # avoids AAC packet boundaries dropping the final planned video frame.
        "-t", f"{expected_duration:.6f}",
        "-progress", "pipe:1", "-nostats", str(render_target),
    ]
    context.update(0.04, f"Rendering with {encoder}")
    process_returncode = None
    try:
        render_context = _ScaledProgressContext(context, 0.04, 0.82, "Rendering") if normalize_audio else context
        process_returncode, stderr = _run_ffmpeg_process(render_context, command, expected_duration)
        if process_returncode != 0:
            if encoder != "libx264" and not options.get("_force_software"):
                render_target.unlink(missing_ok=True)
                context.update(0.04, "Hardware encoder unavailable. Retrying on CPU...")
                return render_project(context, project_id, store, settings, {**options, "quality": quality, "_force_software": True})
            detail = "\n".join(line.strip() for line in (stderr or "").splitlines() if line.strip())[-1600:]
            raise RuntimeError(f"FFmpeg render failed{': ' + detail if detail else ''}")
        if normalize_audio:
            context.check_cancelled()
            context.update(0.83, "Normalizing final audio...")
            normalize_command = [
                settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(normalization_stage),
                "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                "-af", normalization_filter,
                "-c:a", "aac", "-b:a", str(settings.render.get("audio_bitrate", "192k")),
                "-movflags", "+faststart", "-map_metadata", "-1", "-map_chapters", "-1",
                "-t", f"{expected_duration:.6f}",
                "-progress", "pipe:1", "-nostats", str(partial),
            ]
            normalize_context = _ScaledProgressContext(context, 0.83, 0.96, "Audio")
            normalize_returncode, normalize_stderr = _run_ffmpeg_process(
                normalize_context, normalize_command, expected_duration
            )
            if normalize_returncode != 0:
                detail = "\n".join(
                    line.strip() for line in (normalize_stderr or "").splitlines() if line.strip()
                )[-1600:]
                raise RuntimeError(
                    f"FFmpeg audio normalization failed{': ' + detail if detail else ''}"
                )
        context.update(0.97, "Finalizing and verifying output...")
        partial.replace(output)
        metadata = probe_media(output, settings)
        _verify_output_metadata(
            metadata,
            width=width,
            height=height,
            expected_duration=expected_duration,
            expected_audio=has_audio,
            expected_fps=fps,
        )
        record = {
            "id": export_id,
            "name": output.name,
            "relative_path": output.name,
            "created_at": now_iso(),
            "width": metadata["width"],
            "height": metadata["height"],
            "fps": fps,
            "frame_rate_mode": "cfr",
            "duration": metadata["duration"],
            "size": metadata["size"],
            "encoder": encoder,
            "quality": quality,
            "captions_burned": bool(caption_ass),
            "editorial_effects": _render_effects_payload(project).get("effects", []),
            "input_fingerprint": render_input_fingerprint,
        }
        if caption_ass is not None or project.get("settings", {}).get("captions"):
            record["caption_settings"] = caption_settings
        caption_transcript = transcript or {}
        if project.get("settings", {}).get("captions") and caption_transcript.get("segments"):
            caption_path = output.with_suffix(".srt")
            build_srt(
                caption_transcript,
                caption_ranges,
                caption_path,
                words_per_caption=caption_settings["caption_words_per_line"],
            )
            record["captions_name"] = caption_path.name
            record["captions_url"] = f"/api/exports/{caption_path.name}"
        stale_exports: list[dict[str, Any]] = []

        def commit_export(latest: dict[str, Any]) -> None:
            nonlocal stale_exports
            if _render_input_fingerprint(latest) != saved_input_fingerprint:
                raise RuntimeError("project_changed_during_render")
            latest.setdefault("exports", []).insert(0, record)
            stale_exports = list(latest["exports"][20:])
            latest["exports"] = latest["exports"][:20]

        # This is the irreversible boundary: a cancellation racing after the
        # export record is saved must not report "cancelled" while leaving a valid
        # published output behind. commit() performs one final cancellation check.
        context.commit()
        project = store.update(project_id, commit_export)
        output_committed = True
        for stale in stale_exports:
            for key in ("name", "captions_name"):
                name = Path(str(stale.get(key) or "")).name
                if name:
                    try:
                        (settings.exports_dir / name).unlink(missing_ok=True)
                    except OSError:
                        # Retention cleanup is best-effort. A player can briefly
                        # lock an old file on Windows; that must not relabel the
                        # newly committed export as failed.
                        pass
        context.update(1.0, "Export ready")
        return {"project_id": project_id, "export": record, "url": f"/api/exports/{output.name}"}
    finally:
        graph_path.unlink(missing_ok=True)
        if caption_ass is not None:
            caption_ass.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        normalization_stage.unlink(missing_ok=True)
        if not output_committed:
            output.unlink(missing_ok=True)
            if caption_path is not None:
                caption_path.unlink(missing_ok=True)
