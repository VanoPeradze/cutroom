"""An explicitly selected half-open window of finished output frames. No timeline mutation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .frame_rates import validate_export_fps


class RangeExportError(ValueError):
    def __init__(self, message: str, *, stale: bool = False):
        super().__init__(message)
        self.stale = stale


@dataclass(frozen=True)
class ExportRange:
    start_frame: int
    end_frame: int
    fps: int

    @property
    def start(self) -> float:
        return self.start_frame / self.fps

    @property
    def end(self) -> float:
        return self.end_frame / self.fps

    @property
    def duration(self) -> float:
        return (self.end_frame - self.start_frame) / self.fps

    def public(self) -> dict[str, int]:
        return {"start_frame": self.start_frame, "end_frame": self.end_frame, "fps": self.fps}

    def audio_trim(self) -> str:
        # Every supported integer output FPS divides the canonical 48 kHz mix exactly.
        step = 48_000 // self.fps
        return (f"aresample=48000,atrim=start_sample={self.start_frame * step}:end_sample={self.end_frame * step},"
                "asetpts=N/SR/TB")

    def mapped_graph(self, graph: str, maps: list[str], *, trim_audio: bool) -> tuple[str, list[str]]:
        if len(maps) not in {2, 4} or maps[::2] != ["-map"] * (len(maps) // 2):
            raise ValueError("The finished output streams cannot be identified.")
        result = list(maps)
        # Keep the full timeline clock through compositing, motion, fades and ASS subtitles.
        # Let the finite finished streams drain independently. Otherwise, when
        # both trim filters end inside an early source gap, FFmpeg can stop
        # requesting a split/concat counterpart and never deliver EOF. The
        # drain branches go to a separate null output (see drain_output_args),
        # not to in-graph nullsinks: FFmpeg 7.0/7.1 abort with "Assertion
        # best_input >= 0" when two nullsinks outlive the range outputs on a
        # two-source layout, and each version needs a different single drain.
        paired = trim_audio and len(maps) == 4
        if not trim_audio and len(maps) == 4:
            # A normalized stage must carry ALL unmodified PCM for the second
            # pass. select drains its source to EOF; trim can close the video
            # input early and truncate a shared decoder's final audio packet.
            video = f"{maps[1]}select='between(n,{self.start_frame},{self.end_frame - 1})'"
        else:
            prefix = f"{maps[1]}split=2[vrangedrain][vrangeselect];[vrangeselect]" if paired else maps[1]
            video = f"{prefix}trim=start_frame={self.start_frame}:end_frame={self.end_frame}"
        graph += f";\n{video},settb=1/{self.fps},setpts=N[vrange]"
        result[1] = "[vrange]"
        if paired:
            graph += (f";\n{maps[3]}asplit=2[arangedrain][arangeselect];"
                      f"[arangeselect]{self.audio_trim()}[arange]")
            result[3] = "[arange]"
        return graph, result

    @staticmethod
    def drain_output_args(graph: str) -> list[str]:
        """A discarded second output that consumes the range drain branches."""
        if "[vrangedrain]" not in graph:
            return []
        return ["-map", "[vrangedrain]", "-map", "[arangedrain]", "-f", "null", "-"]

    def rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Cues crossing In/Out retain the visible wording. The public sidecar and output review
        # consume line/clip-level timings, not source-word timings or source transcript edits.
        clipped = []
        for row in rows:
            a, b = max(self.start, float(row["start"])), min(self.end, float(row["end"]))
            if b > a:
                clipped.append({**row, "start": a - self.start, "end": b - self.start})
        return clipped

    def gaps(self, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
        return [(row["start"], row["end"]) for row in self.rows([{"start": a, "end": b} for a, b in gaps])]


def validate_range(spec: Any, *, fps: int, revision: int, total_frames: int) -> ExportRange:
    keys = {"start_frame", "end_frame", "fps", "expected_revision"}
    if not isinstance(spec, dict) or set(spec) != keys or any(type(spec[k]) is not int for k in keys):
        raise RangeExportError("Use integer start_frame, end_frame, fps and expected_revision for a marked export.")
    try:
        validate_export_fps(spec["fps"])
    except ValueError as error:
        raise RangeExportError(str(error)) from error
    if spec["expected_revision"] != revision or spec["fps"] != fps:
        raise RangeExportError("The saved edit or frame rate changed. Review the marked range again.", stale=True)
    start, end = spec["start_frame"], spec["end_frame"]
    if not (0 <= start < end <= total_frames):
        raise RangeExportError("The marked export must contain at least one complete frame within the finished timeline.")
    return ExportRange(start, end, fps)
