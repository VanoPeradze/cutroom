"""Real, tiny CPU-only exports: native/mixed 60 FPS and 30-to-60 duplication."""
from __future__ import annotations

import json
import os
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
from cutroom.render import _expected_output_duration, render_project


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)


def main():
    cases = []
    original_data = os.environ.get("CUTROOM_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory(prefix="cutroom-60fps-") as temporary:
            work = Path(temporary)
            os.environ["CUTROOM_DATA_DIR"] = str(work / "data")
            settings = load_settings()
            settings.raw["render"]["prefer_hardware"] = False
            store = ProjectStore(settings)
            for source_fps in (30, 60):
                project = store.create(f"60 FPS source {source_fps}")
                directory = store.project_dir(project["id"])
                for slot, rate in (("A", source_fps), ("B", 30)):
                    media = directory / "media" / f"source-{slot}.mp4"
                    command = [
                        settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                        "-f", "lavfi", "-i", f"testsrc2=size=320x180:rate={rate}:duration=3",
                    ]
                    if slot == "A":
                        command += ["-f", "lavfi", "-i", "sine=frequency=520:sample_rate=48000:duration=3"]
                    command += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
                    if slot == "A":
                        command += ["-c:a", "aac", "-shortest"]
                    run(command + [str(media)])
                    project["sources"][slot] = {
                        "slot": slot, "name": media.name,
                        "relative_path": f"media/{media.name}", **probe_media(media, settings),
                    }
                project["settings"].update({
                    "fps": 60 if source_fps == 60 else 30,
                    "aspect": "source", "quality": "fast", "captions": True,
                    "burn_captions": True, "editorial_effects": False,
                })
                project["analysis"] = {
                    "audio_source": "A", "sync": {"offset": 0.017},
                    "transcript": {"segments": [{"start": 0.0, "end": 2.0, "text": "Frame accurate captions"}]},
                }
                project["manual"]["source_mixer"].update({"sync_offset": 0.017, "audio_slot": "A"})
                project["draft"] = {
                    "keep_ranges": [{"start": 0.017, "end": 1.05}, {"start": 1.333, "end": 2.517}],
                    "camera_plan": [
                        {"start": 0, "end": 0.55, "camera": "A"},
                        {"start": 0.55, "end": 1.05, "camera": "B"},
                        {"start": 1.333, "end": 2.517, "camera": "stacked"},
                    ],
                    "audio_policy": {"normalize": source_fps == 30, "target_lufs": -16},
                }
                store.save(project)
                context = JobContext(Job(f"smoke-{source_fps}", "render", project["id"]), threading.Lock())
                result = render_project(context, project["id"], store, settings, {"fps": 60})
                output = settings.exports_dir / result["export"]["name"]
                metadata = probe_media(output, settings)
                probe = json.loads(run([
                    settings.ffprobe, "-v", "error", "-select_streams", "v:0",
                    "-count_frames", "-show_streams", "-show_frames",
                    "-show_entries", "stream=avg_frame_rate,r_frame_rate,nb_read_frames,duration:frame=best_effort_timestamp_time",
                    "-of", "json", str(output),
                ]).stdout)
                stream = probe["streams"][0]
                timestamps = [float(frame["best_effort_timestamp_time"]) for frame in probe["frames"]]
                effective = {**project, "settings": {**project["settings"], "fps": 60}}
                duration = _expected_output_duration(effective)
                expected_frames = round(duration * 60)
                assert stream["avg_frame_rate"] == "60/1", stream
                assert stream["r_frame_rate"] == "60/1", stream
                assert int(stream["nb_read_frames"]) == expected_frames, stream
                assert len(timestamps) == expected_frames
                assert all(abs(b - a - 1 / 60) < 0.000002 for a, b in zip(timestamps, timestamps[1:]))
                assert abs(metadata["video_duration"] - duration) < 0.001, metadata
                assert abs(metadata["audio_duration"] - duration) < 0.05, metadata
                assert result["export"]["fps"] == 60
                assert result["export"]["frame_rate_mode"] == "cfr"
                assert result["export"]["captions_burned"]
                assert output.with_suffix(".srt").is_file()
                assert store.load(project["id"])["settings"]["fps"] == project["settings"]["fps"]
                cases.append({"source_fps": source_fps, "fps": 60, "frames": expected_frames, "duration": duration})
    finally:
        if original_data is None:
            os.environ.pop("CUTROOM_DATA_DIR", None)
        else:
            os.environ["CUTROOM_DATA_DIR"] = original_data
    print(json.dumps({"ok": True, "cases": cases}))


if __name__ == "__main__":
    main()
