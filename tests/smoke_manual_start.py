"""Tiny real exports from the no-AI onboarding path; no models or user media."""
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cutroom.config import load_settings
from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.manual_start import start_manual_draft
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project


def main():
    previous = os.environ.get("CUTROOM_DATA_DIR")
    cases = []
    try:
        with tempfile.TemporaryDirectory(prefix="cutroom-manual-export-") as work:
            os.environ["CUTROOM_DATA_DIR"] = str(Path(work) / "data")
            settings = load_settings()
            settings.ai["enabled"] = False
            settings.raw["render"]["prefer_hardware"] = False
            store = ProjectStore(settings)
            for aspect, size in [("16:9", (1280, 720)), ("9:16", (720, 1280))]:
                project = store.create("Manual export test", initial_settings={"workflow": "manual", "aspect": aspect,
                    "goal": "youtube" if aspect == "16:9" else "short", "fps": 60, "resolution": "720",
                    "quality": "fast", "editorial_effects": False})
                media = store.project_dir(project["id"]) / "media" / "source-A.mp4"
                subprocess.run([settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "testsrc2=size=320x180:rate=30:duration=3", "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(media)],
                    check=True, capture_output=True, timeout=30)
                project["sources"]["A"] = {"slot": "A", "name": media.name, "relative_path": "media/source-A.mp4",
                                            **probe_media(media, settings)}
                start_manual_draft(project)
                apply_manual_edit(project, {"action": "split", "time": 1})
                apply_manual_edit(project, {"action": "delete_range", "start": 1, "end": 2})
                store.save(project)
                result = render_project(JobContext(Job("manual-smoke", "render", project["id"]), threading.Lock()),
                                        project["id"], store, settings, {})
                metadata = probe_media(settings.exports_dir / result["export"]["name"], settings)
                assert (metadata["width"], metadata["height"]) == size, metadata
                assert abs(metadata["duration"] - 2) < .05, metadata
                assert abs(metadata["fps"] - 60) < .001, metadata
                assert metadata["has_audio"]
                cases.append({"aspect": aspect, "size": size, "duration": metadata["duration"], "fps": metadata["fps"]})
    finally:
        if previous is None:
            os.environ.pop("CUTROOM_DATA_DIR", None)
        else:
            os.environ["CUTROOM_DATA_DIR"] = previous
    print(json.dumps({"ok": True, "cases": cases}))


if __name__ == "__main__":
    main()
