from __future__ import annotations

import sys
import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from cutroom.jobs import Job, JobContext
from cutroom.render import _expected_output_duration, _run_ffmpeg_process


def test_ffmpeg_stderr_is_drained_while_process_runs(tmp_path: Path):
    child = tmp_path / "noisy_child.py"
    child.write_text(
        """
import os, sys, time
for index in range(256):
    os.write(2, (\"E\" * 8192).encode())
    if index in (16, 64, 128, 192, 255):
        micros = int((index + 1) / 256 * 10_000_000)
        print(f\"out_time_us={micros}\", flush=True)
print(\"progress=end\", flush=True)
""".strip(),
        encoding="utf-8",
    )
    job = Job("render-regression", "render", "project")
    context = JobContext(job, threading.Lock())
    started = time.monotonic()
    returncode, stderr = _run_ffmpeg_process(context, [sys.executable, str(child)], 10.0)
    elapsed = time.monotonic() - started
    assert returncode == 0
    assert elapsed < 5.0
    assert job.progress >= 0.90
    assert stderr


def test_expected_output_duration_uses_kept_camera_ranges():
    project = {
        "sources": {"A": {"duration": 99.0}},
        "draft": {
            "keep_ranges": [{"start": 0, "end": 3}, {"start": 10, "end": 12}],
            "camera_plan": [{"start": 0, "end": 3, "camera": "A"}, {"start": 10, "end": 12, "camera": "B"}],
        },
    }
    assert _expected_output_duration(project) == 5.0


@pytest.mark.parametrize("video_duration", [None, 3.0])
@pytest.mark.parametrize("layout", ["B", "camera", "screen", "stacked", "side_by_side", "pip"])
def test_render_uses_a_when_a_selected_b_source_has_not_started_or_has_ended(layout, video_duration):
    from cutroom.render import _effective_audio_slot, _render_plan

    project = {
        "sources": {
            "A": {"duration": 10.0, "width": 640, "height": 360},
            "B": {
                "duration": 8.0 if video_duration else 3.0,
                "video_duration": video_duration, "width": 640, "height": 360, "has_audio": True,
            },
        },
        "manual": {"source_mixer": {
            "screen_slot": "B" if layout == "screen" else "A",
            "camera_slot": "A" if layout == "screen" else "B", "sync_offset": 2.0,
        }},
        "draft": {
            "keep_ranges": [{"start": 0.0, "end": 10.0}],
            "camera_plan": [{"start": 0.0, "end": 10.0, "camera": layout}],
        },
    }
    assert _render_plan(project) == [
        {"start": 0.0, "end": 2.0, "camera": "A"},
        {"start": 2.0, "end": 5.0, "camera": layout},
        {"start": 5.0, "end": 10.0, "camera": "A"},
    ]
    assert _expected_output_duration(project) == 10.0
    assert _effective_audio_slot(project) == "B"


@pytest.mark.parametrize("layout", ["B", "stacked"])
def test_real_render_shows_a_instead_of_black_before_and_after_short_b(tmp_path, layout):
    from cutroom.render import build_filter_graph

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    project = {
        "sources": {
            "A": {"duration": 2.0, "width": 160, "height": 90, "has_audio": False},
            "B": {"duration": 1.0, "width": 160, "height": 90, "has_audio": False},
        },
        "settings": {"editorial_effects": False},
        "manual": {"source_mixer": {"sync_offset": 0.5, "first_slot": "B"}},
        "draft": {
            "keep_ranges": [{"start": 0.0, "end": 2.0}],
            "camera_plan": [{"start": 0.0, "end": 2.0, "camera": layout}],
        },
    }
    graph, maps, has_audio = build_filter_graph(project, 160, 90)
    assert not has_audio
    graph_path = tmp_path / "fallback-graph.txt"
    graph_path.write_text(graph, encoding="utf-8")
    result = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=1",
        "-filter_complex_script", str(graph_path), *maps,
        "-vsync", "1", "-r:v", "30", "-t", "2.0",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], check=True, capture_output=True, timeout=15)
    frame_size = 160 * 90 * 3
    assert len(result.stdout) == 60 * frame_size

    def pixel(frame):
        offset = frame * frame_size + (14 * 160 + 80) * 3
        return tuple(result.stdout[offset:offset + 3])

    for frame in (3, 54):
        red, green, blue = pixel(frame)
        assert red > 200 and green < 30 and blue < 30
    red, green, blue = pixel(30)
    assert blue > 200 and red < 30 and green < 30


def test_real_two_source_director_export_completes_after_b_ends():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg runtime is not installed")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("smoke_director_two_source.py"))],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["sync"]["offset"] < 0
    assert payload["render"]["duration"] == pytest.approx(payload["draft"]["output_duration"], abs=1 / 30)
    assert payload["render"]["video_duration"] == pytest.approx(payload["render"]["audio_duration"], abs=1 / 30)
