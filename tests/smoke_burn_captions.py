from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="cutroom-caption-smoke-"))
    try:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        source = work / "source.mp4"
        run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=#243041:size=640x360:rate=24:duration=8",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source),
        ])
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["data_dir"] = str(work / "data")
        config["render"]["prefer_hardware"] = False
        cfg = work / "config.json"
        cfg.write_text(json.dumps(config), encoding="utf-8")
        settings = load_settings(cfg)
        store = ProjectStore(settings)
        project = store.create("Hebrew burn caption smoke")
        media = store.project_dir(project["id"]) / "media" / "source-A.mp4"
        shutil.copy2(source, media)
        project["sources"]["A"] = {"slot": "A", "name": "source.mp4", "relative_path": "media/source-A.mp4", **probe_media(media, settings)}
        project["settings"].update({"aspect": "9:16", "resolution": "720", "quality": "fast", "burn_captions": True, "captions": False})
        project["analysis"] = {
            "sync": None, "vision": {},
            "transcript": {"language": "he", "segments": [
                {"id": "s1", "start": 0.2, "end": 1.8, "text": "שלום לכולם", "words": [
                    {"start": .2, "end": .8, "word": "שלום"}, {"start": .9, "end": 1.5, "word": "לכולם"},
                ]},
                {"id": "s2", "start": 4.2, "end": 5.8, "text": "זה החלק החשוב", "words": [
                    {"start": 4.2, "end": 4.6, "word": "זה"}, {"start": 4.7, "end": 5.1, "word": "החלק"}, {"start": 5.2, "end": 5.7, "word": "החשוב"},
                ]},
            ]},
        }
        project["manual"] = {"crop": {}, "cuts": [], "keep_ranges": [], "camera_plan": []}
        project["draft"] = {
            "keep_ranges": [{"start": 0, "end": 2}, {"start": 4, "end": 8}],
            "cuts": [{"start": 2, "end": 4}],
            "camera_plan": [{"start": 0, "end": 2, "camera": "A"}, {"start": 4, "end": 8, "camera": "A"}],
            "output_duration": 6.0,
        }
        store.save(project)
        result = render_project(JobContext(Job("caption-render", "render", project["id"]), threading.Lock()), project["id"], store, settings, {"quality": "fast"})
        output = settings.exports_dir / result["export"]["name"]
        metadata = probe_media(output, settings)
        assert result["export"]["captions_burned"] is True
        assert (metadata["width"], metadata["height"]) == (720, 1280)
        assert 5.8 <= metadata["duration"] <= 6.2
        print(json.dumps({"ok": True, "duration": metadata["duration"], "captions_burned": True, "size": metadata["size"]}, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
