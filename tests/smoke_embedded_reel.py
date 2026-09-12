from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cutroom.config import load_settings
from cutroom.composition import FACE_LAYOUT_VERSION
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project


def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, check=True, capture_output=True)


def pixel(ffmpeg: str, path: Path, x: int, y: int) -> tuple[int, int, int]:
    result = run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(path),
        "-vf", f"crop=1:1:{x}:{y},format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-",
    ])
    data = result.stdout[:3]
    return tuple(data) if len(data) == 3 else (0, 0, 0)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="cutroom-embedded-reel-"))
    try:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        source = work / "embedded.mp4"
        # Blue gameplay with a stable red creator-camera box in the top-right.
        subprocess.run([
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:size=640x360:rate=30:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=4",
            "-vf", "drawbox=x=448:y=18:w=160:h=126:color=red:t=fill",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-c:a", "aac", "-shortest", str(source),
        ], check=True)
        config = json.loads((ROOT / "config.json").read_text())
        config["data_dir"] = str(work / "data")
        config["render"]["prefer_hardware"] = False
        cfg = work / "config.json"; cfg.write_text(json.dumps(config))
        settings = load_settings(cfg); store = ProjectStore(settings)
        project = store.create("embedded reel")
        media = store.project_dir(project["id"]) / "media" / "source-A.mp4"; shutil.copy2(source, media)
        project["sources"]["A"] = {"slot":"A","name":"source.mp4","relative_path":"media/source-A.mp4", **probe_media(media, settings)}
        project["settings"].update({"aspect":"9:16","resolution":"720","quality":"fast"})
        # Exercise the manual fallback specifically: the detector found nothing,
        # but the user marked the facecam rectangle inside source A.
        project["analysis"] = {"sync": None, "transcript": {"segments": []}, "vision": {
            "version": FACE_LAYOUT_VERSION, "embedded_camera": None,
        }}
        project["manual"]["embedded_camera"] = {
            "x": .70, "y": .05, "w": .25, "h": .35,
            "content_focus": {"x": .30, "y": .62},
        }
        project["draft"] = {
            "layout": "embedded_stack",
            "embedded_layout_confirmed": True,
            "keep_ranges": [{"start":0.0,"end":4.0}],
            "camera_plan": [{"start":0.0,"end":4.0,"camera":"embedded_stack"}],
            "audio_plan": [], "audio_policy": {}, "output_duration":4.0,
        }
        store.save(project)
        result = render_project(JobContext(Job("r","render",project["id"]), threading.Lock()), project["id"], store, settings, {"quality":"fast"})
        output = settings.exports_dir / result["export"]["name"]
        meta = probe_media(output, settings)
        top = pixel(ffmpeg, output, meta["width"] // 2, int(meta["height"] * .16))
        bottom = pixel(ffmpeg, output, meta["width"] // 2, int(meta["height"] * .72))
        # Red facecam should dominate the upper panel; blue gameplay the lower.
        assert top[0] > top[2] * 1.4, (top, bottom)
        assert bottom[2] > bottom[0] * 1.4, (top, bottom)
        print(json.dumps({"ok": True, "width": meta["width"], "height": meta["height"], "top_rgb": top, "bottom_rgb": bottom}, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
