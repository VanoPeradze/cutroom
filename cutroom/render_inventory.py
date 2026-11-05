"""One detached input order for the existing A/B renderer.

Each library occurrence deliberately retains its own input. This is inventory,
not input deduplication or a claim about FFmpeg's peak memory consumption.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .composition import chroma_background_asset, chroma_source, chroma_video_targets, source_chroma_key
from .frame_rates import project_export_fps
from .media_library import safe_asset_path


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return result if math.isfinite(result) else default


def library_clips(project: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows = (project.get("manual") or {}).get("media_clips") or []
    if not isinstance(rows, list) or len(rows) > 200:
        raise ValueError("The media timeline must contain at most 200 clips")
    assets = project.get("assets") or {}
    result = []
    for clip in rows:
        if not isinstance(clip, dict):
            raise ValueError("Invalid library clip")
        asset = assets.get(clip.get("asset_id")) if isinstance(assets, dict) else None
        if not isinstance(asset, dict) or asset.get("kind") not in {"video", "image", "audio"}:
            raise ValueError("A timeline asset is missing; remove its clip or import it again")
        if asset.get("status", "ready") != "ready":
            raise ValueError("Wait until timeline media finishes importing before exporting")
        result.append((clip, asset))
    return result


def audible(clip: dict[str, Any], asset: dict[str, Any]) -> bool:
    return asset["kind"] == "audio" or asset["kind"] == "video" and bool(asset.get("has_audio")) and bool(clip.get("audio_enabled", False))


def library_visual_start(clip: dict[str, Any], asset: dict[str, Any], fps: float) -> float:
    if asset["kind"] != "video":
        return 0.0
    source_start = max(0.0, _number(clip.get("source_start")))
    start = max(0.0, _number(clip.get("video_source_start"), source_start))
    duration = _number(asset.get("duration"))
    return min(start, max(0.0, duration - 1 / fps)) if duration > 0 else start


def _library_seek_start(project: dict[str, Any], clip: dict[str, Any], asset: dict[str, Any], fps: float) -> float:
    # A single occurrence may have different picture and speech clocks. Seek
    # only before both consumed ranges, retaining the fractional trim below.
    # Keyed video resets timestamps before its trim; preserve that path here.
    if asset["kind"] != "video" or source_chroma_key(project, clip.get("asset_id"))["enabled"]:
        return 0.0
    start = library_visual_start(clip, asset, fps)
    if audible(clip, asset):
        start = min(start, max(0.0, _number(clip.get("source_start"))))
    return float(math.floor(start))


def chroma_background_slots(project: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(target, asset) for target in chroma_video_targets(project, used_only=True)
            if (asset := chroma_background_asset(project, target)) is not None]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _project_identity(project: dict[str, Any]) -> str:
    manual = project.get("manual") or {}
    return _digest({"sources": project.get("sources"), "assets": project.get("assets"),
                    "media_clips": manual.get("media_clips"), "chroma_key": manual.get("chroma_key"),
                    "fps": project_export_fps(project)})


@dataclass(frozen=True)
class RenderInput:
    index: int
    category: str
    key: str
    media: dict[str, Any]
    clip: dict[str, Any] | None = None
    target: str | None = None
    occurrence: int | None = None
    loop_duration: float | None = None
    seek_start: float = 0.0

    def label(self, stream: str) -> str:
        if stream not in {"v", "a"}:
            raise ValueError("Invalid render input stream")
        return f"[{self.index}:{stream}]"


@dataclass(frozen=True)
class RenderInputInventory:
    entries: tuple[RenderInput, ...]
    fps: float
    project_identity: str
    integrity: str
    includes_library: bool
    includes_chroma: bool

    def _validate_integrity(self) -> None:
        if (not all(isinstance(entry, RenderInput) and entry.index == index
                    for index, entry in enumerate(self.entries))
                or self.integrity != _inventory_digest(self.entries, self.fps,
                                                      self.includes_library, self.includes_chroma)):
            raise ValueError("The render input inventory no longer matches this project")

    def validate(self, project: dict[str, Any], *, require_library: bool = True,
                 require_chroma: bool = True) -> None:
        self._validate_integrity()
        if ((require_library and not self.includes_library)
                or (require_chroma and not self.includes_chroma)
                or self.fps != project_export_fps(project)
                or self.project_identity != _project_identity(project)):
            raise ValueError("The render input inventory no longer matches this project")

    def inputs(self, category: str) -> tuple[RenderInput, ...]:
        return tuple(entry for entry in self.entries if entry.category == category)

    def source(self, slot: str) -> RenderInput:
        for entry in self.inputs("source"):
            if entry.target == slot:
                return entry
        raise ValueError("The render source input is unavailable")

    def background_labels(self) -> dict[str, str]:
        return {entry.target: entry.label("v") for entry in self.inputs("chroma_background")}

    def needs_source_b(self, graph: str) -> bool:
        # Extras retain the existing B slot even if B has no graph consumer.
        return (any(entry.target == "B" for entry in self.inputs("source"))
                and ("[1:v]" in graph or "[1:a]" in graph
                     or bool(self.inputs("library") or self.inputs("chroma_background"))))

    def input_args(self, project_dir: Path, *, category: str | None = None,
                   include_source_b: bool = True) -> list[str]:
        self._validate_integrity()
        root = project_dir.resolve()
        result: list[str] = []
        for entry in self.entries:
            if category is not None and entry.category != category:
                continue
            if entry.category == "source" and entry.target == "B" and not include_source_b:
                if self.inputs("library") or self.inputs("chroma_background"):
                    raise ValueError("Source B's input slot is required by timeline media")
                continue
            value = (entry.media.get("relative_path") if entry.category == "source"
                     else entry.media.get("path") or entry.media.get("relative_path"))
            if entry.category == "chroma_background":
                path = safe_asset_path(root, value)
                if not path.is_file():
                    raise FileNotFoundError("The chosen Chroma Key background image is missing. Choose another image or reset Chroma Key.")
            else:
                if not isinstance(value, str) or not value:
                    raise ValueError("The timeline asset has no local media path" if entry.category == "library"
                                     else f"Source {entry.target} has no local media path")
                path = (root / value).resolve()
                if not path.is_relative_to(root):
                    raise ValueError("Timeline media must belong to this project")
                if not path.is_file():
                    raise FileNotFoundError(f"Timeline media is missing: {path.name}" if entry.category == "library"
                                            else f"Source {entry.target} media is missing: {path.name}")
            if entry.loop_duration is not None:
                result += ["-loop", "1", "-framerate", str(self.fps), "-t", f"{entry.loop_duration:.9f}"]
            if entry.seek_start > 0:
                result += ["-ss", f"{entry.seek_start:.9f}"]
            if entry.category != "source":
                result += ["-protocol_whitelist", "file,pipe"]
            result += ["-i", str(path)]
        return result

    def demand(self, graph: str, *, include_source_b: bool = True) -> dict[str, Any]:
        """Describe actual input/graph fan-out, without estimating peak RAM."""
        self._validate_integrity()
        streams = {(int(index), stream) for index, stream in re.findall(r"\[(\d+):([va])\]", graph)}
        selected = {entry.index: entry for entry in self.entries
                    if include_source_b or not (entry.category == "source" and entry.target == "B")}
        if any(index not in selected for index, _ in streams):
            raise ValueError("The render graph refers to an unavailable input")
        pixels_per_second = 0.0
        unknown = 0
        for index, stream in streams:
            if stream != "v":
                continue
            entry = selected[index]
            width, height = (_number(entry.media.get(name)) for name in ("width", "height"))
            fps = self.fps if entry.media.get("kind") == "image" else _number(entry.media.get("fps"))
            if min(width, height, fps) <= 0:
                unknown += 1
            else:
                pixels_per_second += width * height * fps
        return {"version": 1, "input_count": len(selected),
                "library_occurrences": len(self.inputs("library")),
                "chroma_background_inputs": len(self.inputs("chroma_background")),
                "video_streams": sum(stream == "v" for _, stream in streams),
                "audio_streams": sum(stream == "a" for _, stream in streams),
                "known_video_pixels_per_second": round(pixels_per_second, 3),
                "video_streams_with_unknown_rate_or_dimensions": unknown,
                "filter_chains": len(graph.split(";\n")) if graph else 0,
                "video_split_outputs": sum(map(int, re.findall(r"\bsplit=(\d+)", graph))),
                "audio_split_outputs": sum(map(int, re.findall(r"\basplit=(\d+)", graph)))}


def _inventory_digest(entries: tuple[RenderInput, ...] | list[RenderInput], fps: float,
                      includes_library: bool, includes_chroma: bool) -> str:
    return _digest({"entries": [asdict(entry) for entry in entries], "fps": fps,
                    "library": includes_library, "chroma": includes_chroma})


def compile_render_inputs(project: dict[str, Any], *, include_library: bool = True,
                          include_chroma: bool = True) -> RenderInputInventory:
    """Compile metadata only; resolving paths and opening media are separate."""
    fps = project_export_fps(project)
    sources = project.get("sources") or {}
    entries = [RenderInput(0, "source", "source:A", copy.deepcopy(sources.get("A") or {}), target="A")]
    if sources.get("B"):
        entries.append(RenderInput(1, "source", "source:B", copy.deepcopy(sources["B"]), target="B"))
    for occurrence, (clip, asset) in enumerate(library_clips(project) if include_library else ()):
        duration = (max(1 / fps, _number(clip.get("end")) - _number(clip.get("start"))) + 2 / fps
                    if asset["kind"] == "image" else None)
        entries.append(RenderInput(len(entries), "library", f"library:{occurrence}", copy.deepcopy(asset),
                                   copy.deepcopy(clip), occurrence=occurrence, loop_duration=duration,
                                   seek_start=_library_seek_start(project, clip, asset, fps)))
    for target, asset in chroma_background_slots(project) if include_chroma else ():
        source = chroma_source(project, target) or {}
        duration = _number(source.get("video_duration"))
        if duration <= 0:
            duration = max(0.0, _number(source.get("duration")))
        entries.append(RenderInput(len(entries), "chroma_background", f"background:{target}",
                                   copy.deepcopy(asset), target=target, loop_duration=duration + 2 / fps))
    return RenderInputInventory(tuple(entries), fps, _project_identity(project),
                                _inventory_digest(entries, fps, include_library, include_chroma),
                                include_library, include_chroma)
