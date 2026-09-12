from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project


def run(command):
    subprocess.run(command, check=True, capture_output=True, text=True)


def main():
    root = Path(__file__).resolve().parent.parent
    work = Path(tempfile.mkdtemp(prefix="cutroom-smoke-"))
    try:
        source_a = work / "A.mp4"
        source_b = work / "B.mp4"
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=8",
            "-f", "lavfi", "-i", "sine=frequency=520:sample_rate=48000:duration=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source_a),
        ])
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "smptebars=size=640x360:rate=30:duration=8",
            "-f", "lavfi", "-i", "sine=frequency=520:sample_rate=48000:duration=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source_b),
        ])
        config = json.loads((root / "config.json").read_text(encoding="utf-8"))
        config["data_dir"] = str(work / "data")
        config["render"]["prefer_hardware"] = False
        config_path = work / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        settings = load_settings(config_path)
        store = ProjectStore(settings)
        project = store.create("Two source smoke")
        media_dir = store.project_dir(project["id"]) / "media"
        target_a, target_b = media_dir / "source-A.mp4", media_dir / "source-B.mp4"
        shutil.copy2(source_a, target_a); shutil.copy2(source_b, target_b)
        project["sources"]["A"] = {"slot": "A", "name": "A.mp4", "relative_path": "media/source-A.mp4", **probe_media(target_a, settings)}
        project["sources"]["B"] = {"slot": "B", "name": "B.mp4", "relative_path": "media/source-B.mp4", **probe_media(target_b, settings)}
        project["settings"].update({"aspect": "9:16", "resolution": "720", "quality": "fast", "captions": False})
        project["manual"]["source_mixer"] = {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "B", "sync_offset": 0.0,
        }
        project["analysis"] = {"sync": {"offset": 0.0}, "vision": {"embedded_camera": None}, "transcript": {"segments": []}}
        project["draft"] = {
            "keep_ranges": [{"start": 0, "end": 2.5}, {"start": 3, "end": 5.5}, {"start": 6, "end": 8}],
            "cuts": [{"start": 2.5, "end": 3}, {"start": 5.5, "end": 6}],
            "camera_plan": [
                {"start": 0, "end": 2.5, "camera": "A"},
                {"start": 3, "end": 5.5, "camera": "B"},
                {"start": 6, "end": 8, "camera": "stacked"},
            ],
        }
        store.save(project)
        job = Job("smoke", "render", project["id"])
        context = JobContext(job, threading.Lock())
        result = render_project(context, project["id"], store, settings, {"quality": "fast"})
        output = settings.exports_dir / result["export"]["name"]
        metadata = probe_media(output, settings)
        assert (metadata["width"], metadata["height"]) == (720, 1280), metadata
        assert 6.5 <= metadata["duration"] <= 7.3, metadata
        print(json.dumps({"ok": True, "output": str(output), "metadata": metadata}, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
