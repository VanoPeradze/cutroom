from __future__ import annotations

import re
import shutil
import subprocess
import threading

import pytest

from cutroom import render
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore


def loudness(ffmpeg: str, path) -> dict[str, float]:
    output = subprocess.run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                             "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
    summary = output[output.rfind("Summary:"):]
    return {"integrated": float(re.search(r"I:\s+(-?[\d.]+) LUFS", summary).group(1)),
            "true_peak": float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", summary).group(1))}


@pytest.fixture
def hot_source(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg runtime is not installed")
    path = tmp_path / "hot.mov"
    # Two near-full-scale tones: strong peaks between samples, as in loud gameplay.
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=gray:s=160x90:r=30:d=4",
                    "-f", "lavfi", "-i", "aevalsrc='0.7*sin(2*PI*997*t)+0.29*sin(2*PI*3001*t+1)':s=48000:d=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s16le", "-shortest", str(path)],
                   check=True, capture_output=True, timeout=30)
    return ffmpeg, path


@pytest.mark.parametrize(("mixer", "policy"), [
    ({}, None),
    ({"source_db": 6.0}, None),
    ({"master_db": 12.0}, {"normalize": True, "target_lufs": -14.0}),
])
def test_every_export_stays_under_the_true_peak_ceiling_at_48_khz(tmp_path, monkeypatch, hot_source, mixer, policy):
    ffmpeg, source = hot_source
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.render["prefer_hardware"] = False
    store = ProjectStore(settings)
    project = store.create("ceiling")
    target = store.project_dir(project["id"]) / "media" / "A.mov"
    shutil.copyfile(source, target)
    project["sources"]["A"] = {**probe_media(target, settings), "relative_path": "media/A.mov"}
    project["settings"].update({"aspect": "16:9", "resolution": "720", "quality": "fast", "fps": 30,
                                "captions": False, "burn_captions": False})
    project["draft"] = {"keep_ranges": [{"start": 0, "end": 4}], "camera_plan": [{"start": 0, "end": 4, "camera": "A"}],
                        **({"audio_policy": policy} if policy else {})}
    if mixer:
        project.setdefault("manual", {})["audio_mixer"] = mixer
    store.save(project)
    context = JobContext(Job("ceiling", "render", project["id"]), threading.Lock())
    record = render.render_project(context, project["id"], store, settings, {"quality": "fast"})["export"]
    output = settings.exports_dir / record["name"]
    measured = loudness(ffmpeg, output)
    assert measured["true_peak"] <= render.AUDIO_CEILING_DBTP + 0.05
    # The export's own check reaches the same verdict and is stored with it.
    checks = {row["id"]: row for row in record["review"]["checks"]}
    assert checks["true_peak"]["status"] == "pass"
    assert checks["loudness"]["status"] == ("pass" if policy else "info")
    streams = subprocess.run([ffmpeg.replace("ffmpeg", "ffprobe"), "-v", "error", "-select_streams", "a:0",
                              "-show_entries", "stream=sample_rate", "-of", "csv=p=0", str(output)],
                             capture_output=True, text=True).stdout.strip()
    assert streams == "48000"
