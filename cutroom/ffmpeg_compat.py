"""Probe file-based export options without models or application imports.

FFmpeg's documented slash syntax loads an option argument from a file:
https://ffmpeg.org/ffmpeg.html#Options
The modern CFR option preserves the legacy ``-vsync 1`` behavior:
https://ffmpeg.org/ffmpeg.html#Advanced-options
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

PROBE_TIMEOUT_SECONDS = 8


class FFmpegCompatibilityError(RuntimeError):
    """The configured binary cannot provide file-based, constant-rate export."""


@dataclass(frozen=True)
class ExportCapabilities:
    executable: str
    graph_file_option: str
    cfr_args: tuple[str, ...]

    def graph_file_args(self, path: Path) -> list[str]:
        return [self.graph_file_option, str(path)]


def _identity(executable: str) -> tuple:
    try:
        path = Path(shutil.which(executable) or executable).resolve(strict=True)
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise OSError("not a regular executable file")
        return (str(path), info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    except (OSError, RuntimeError, ValueError) as error:
        raise FFmpegCompatibilityError(
            f"Cannot inspect configured FFmpeg at {executable!r}; choose an accessible FFmpeg executable."
        ) from error


def _capture(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", timeout=PROBE_TIMEOUT_SECONDS,
            check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise FFmpegCompatibilityError(
            f"FFmpeg export compatibility check could not complete within {PROBE_TIMEOUT_SECONDS}s "
            f"at {command[0]!r} ({type(error).__name__}). Check the configured executable."
        ) from error
    if result.returncode:
        detail = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", result.stdout)[-1200:].strip()
        raise FFmpegCompatibilityError(
            f"FFmpeg export compatibility check failed at {command[0]!r} "
            f"(exit {result.returncode}): {detail or 'no diagnostic output'}. "
            "Use an FFmpeg build supporting filter graph files and constant-frame-rate output."
        )
    return result.stdout


@lru_cache(maxsize=16)
def _probe(identity: tuple) -> ExportCapabilities:
    executable = identity[0]
    help_text = _capture([executable, "-hide_banner", "-h", "full"])
    options = set(re.findall(r"(?m)^\s*(-[A-Za-z0-9_]+)(?=\s|$|\[|:)", help_text))
    if "-filter_complex_script" in options:
        graph_option = "-filter_complex_script"
    elif "-filter_complex" in options:
        # Advertising -filter_complex does not establish slash/file loading.
        # The real one-frame probe below must load the graph from this file.
        graph_option = "-/filter_complex"
    else:
        raise FFmpegCompatibilityError(f"FFmpeg at {executable!r} has no supported complex-filter option.")
    if "-fps_mode" in options:
        cfr = ("-fps_mode:v", "cfr")
    elif "-vsync" in options:
        cfr = ("-vsync", "1")
    else:
        raise FFmpegCompatibilityError(f"FFmpeg at {executable!r} has neither -fps_mode nor -vsync for constant-rate export.")
    capabilities = ExportCapabilities(executable, graph_option, cfr)
    try:
        with tempfile.TemporaryDirectory(prefix="cutroom-ffmpeg-") as directory:
            graph = Path(directory) / "filter graph.txt"
            graph.write_text("color=c=black:s=2x2:r=1:d=1[probe]\n", encoding="utf-8")
            output = _capture([
                executable, "-hide_banner", "-loglevel", "error", "-nostdin",
                *capabilities.graph_file_args(graph), "-map", "[probe]", "-frames:v", "1",
                *cfr, "-r:v", "1", "-threads", "1", "-progress", "pipe:1", "-nostats", "-f", "null", "-",
            ])
            if not re.search(r"(?m)^frame=\s*1\s*$", output) or not re.search(r"(?m)^progress=end\s*$", output):
                raise FFmpegCompatibilityError("FFmpeg did not finish the one-frame graph-file/CFR compatibility probe.")
    except OSError as error:
        raise FFmpegCompatibilityError("Cannot create or remove the temporary FFmpeg compatibility graph file.") from error
    return capabilities


def export_capabilities(executable: str) -> ExportCapabilities:
    """Cached by resolved file identity; replacement or PATH changes require a probe.

At most two bounded subprocesses read help and render one synthetic frame to a
null sink. No user footage is read and no output media is written.
    """
    identity = _identity(executable)
    capabilities = _probe(identity)
    if _identity(executable) != identity:
        raise FFmpegCompatibilityError("Configured FFmpeg changed during its compatibility check; retry with a stable executable.")
    return capabilities
