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
from cutroom.captions import build_ass
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import _caption_ranges, _frame_aligned_plan, render_project


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="cutroom-editorial-stack-"))
    try:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        sources = []
        for name, video_filter, tone in (
            ("screen.mp4", "testsrc2=size=640x360:rate=30:duration=8", "440"),
            ("camera.mp4", "color=c=#501a91:size=640x360:rate=30:duration=8", "660"),
        ):
            target = work / name
            run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", video_filter,
                "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000:duration=8",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(target),
            ])
            sources.append(target)

        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["data_dir"] = str(work / "data")
        config["render"]["prefer_hardware"] = False
        config_path = work / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        settings = load_settings(config_path)
        store = ProjectStore(settings)
        project = store.create("Editorial stack smoke")
        media_dir = store.project_dir(project["id"]) / "media"
        for slot, source in zip(("A", "B"), sources):
            media = media_dir / f"source-{slot}.mp4"
            shutil.copy2(source, media)
            project["sources"][slot] = {
                "slot": slot,
                "name": source.name,
                "relative_path": f"media/source-{slot}.mp4",
                **probe_media(media, settings),
            }
        project["settings"].update({
            "aspect": "9:16", "resolution": "720", "quality": "fast",
            "burn_captions": True, "captions": False, "editorial_effects": True,
        })
        project["manual"]["source_mixer"] = {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen",
            "audio_slot": "A", "sync_offset": 0.0,
        }
        project["analysis"] = {
            "audio_source": "A", "audio_timeline_offset": 0.0,
            "transcript": {"language": "he", "segments": [{
                "id": "s1", "start": 0.4, "end": 3.6, "text": "זה רגע חשוב מאוד",
                "words": [
                    {"start": .4, "end": .9, "word": "זה"},
                    {"start": 1.0, "end": 1.6, "word": "רגע"},
                    {"start": 1.7, "end": 2.4, "word": "חשוב"},
                    {"start": 2.5, "end": 3.2, "word": "מאוד"},
                ],
            }]},
            "story_beats": [{
                "id": "b1", "start": 0.2, "end": 4.0, "role_hint": "hook",
                "editorial_score": .96, "segment_ids": ["s1"], "text": "זה רגע חשוב מאוד",
            }],
        }
        project["draft"] = {
            "goal": "short", "keep_ranges": [{"start": 0.0, "end": 8.0}], "cuts": [],
            "camera_plan": [{"start": 0.0, "end": 8.0, "camera": "stacked"}],
            "ai_camera_plan": [{"start": 0.0, "end": 8.0, "camera": "stacked"}],
            "output_duration": 8.0, "audio_source": "A", "highlight_ids": ["s1"],
        }
        store.save(project)

        layout_ass = work / "layout-aware.ass"
        build_ass(
            project["analysis"]["transcript"],
            _caption_ranges(project),
            layout_ass,
            720,
            1280,
            layout_ranges=_frame_aligned_plan(project),
        )
        assert "\\pos(360," in layout_ass.read_text(encoding="utf-8-sig")

        result = render_project(
            JobContext(Job("editorial-stack", "render", project["id"]), threading.Lock()),
            project["id"], store, settings, {"quality": "fast"},
        )
        output = settings.exports_dir / result["export"]["name"]
        metadata = probe_media(output, settings)
        assert result["export"]["captions_burned"] is True
        assert result["export"]["editorial_effects"]
        assert (metadata["width"], metadata["height"]) == (720, 1280)
        assert 7.8 <= metadata["duration"] <= 8.2
        print(json.dumps({
            "ok": True,
            "duration": metadata["duration"],
            "effects": result["export"]["editorial_effects"],
            "layout_caption": True,
        }, ensure_ascii=False, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
