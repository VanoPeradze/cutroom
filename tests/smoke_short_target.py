from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project
import cutroom.director as director


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def fake_transcribe(_path, _settings, language="auto", progress=None, **_kwargs):
    segments = []
    for i in range(24):
        start = i * 5.0
        text = f"Context block {i}. " + ("This is the strongest result and useful explanation." if i in {4,5,15,16} else "Supporting explanation with normal context.")
        segments.append({"id": f"s{i}", "start": start, "end": start + 4.6, "text": text, "words": [], "avg_logprob": -0.1})
    return {"language":"en","language_probability":.99,"model":"fake","device":"cpu","compute_type":"fake","segments":segments,"words":[],"text":" ".join(x["text"] for x in segments)}


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="cutroom-short-target-"))
    try:
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        source = work / "source.mp4"
        run([ffmpeg,"-hide_banner","-loglevel","error","-y","-f","lavfi","-i","testsrc2=size=320x180:rate=24:duration=120","-f","lavfi","-i","sine=frequency=440:sample_rate=16000:duration=120","-c:v","libx264","-preset","ultrafast","-crf","30","-c:a","aac","-shortest",str(source)])
        config = json.loads((ROOT / "config.json").read_text())
        config["data_dir"] = str(work / "data")
        config["ai"]["enabled"] = False
        config["render"]["prefer_hardware"] = False
        cfg = work / "config.json"; cfg.write_text(json.dumps(config))
        settings = load_settings(cfg); store = ProjectStore(settings)
        project = store.create("60 second target")
        media = store.project_dir(project["id"]) / "media" / "source-A.mp4"; shutil.copy2(source, media)
        project["sources"]["A"] = {"slot":"A","name":"source.mp4","relative_path":"media/source-A.mp4", **probe_media(media, settings)}
        project["settings"].update({"goal":"short","target_duration":60,"aspect":"9:16","resolution":"720","quality":"fast","performance_mode":"lite"})
        store.save(project)
        old_transcribe = director.transcribe
        old_plan_edit = director.plan_edit
        director.transcribe = fake_transcribe

        def fake_story_plan(segments, _settings, brief, progress=None, story_cache=None):
            from cutroom.intelligence import enrich_segments
            enriched = enrich_segments(segments, "en")
            if progress:
                progress(0.25, "Understanding chapters")
                progress(0.55, "Building outline")
                progress(0.80, "Selecting story")
                progress(1.0, "Story ready")
            decision = {
                "keep_ids": [item["id"] for item in enriched],
                "remove_ids": [],
                "highlight_ids": ["s4", "s15", "s23"],
                "opening_id": "s4",
                "closing_id": "s23",
                "title": "Test Story AI",
                "summary": "A deliberate full-recording selection for the render contract.",
                "story_ranges": [
                    {"start": 20.0, "end": 40.0, "beat_id": "test-a"},
                    {"start": 70.0, "end": 90.0, "beat_id": "test-b"},
                    {"start": 100.0, "end": 120.0, "beat_id": "test-c"},
                ],
            }
            return {"segments": enriched, "decision": decision, "story_beats": [], "story_hierarchy": {"engine": "test"}}, "test_story_ai"

        director.plan_edit = fake_story_plan
        try:
            result = director.analyze_project(JobContext(Job("d","director",project["id"]), threading.Lock()), project["id"], store, settings)
        finally:
            director.transcribe = old_transcribe
            director.plan_edit = old_plan_edit
        completed = store.load(project["id"])
        output_duration = float(completed["draft"]["output_duration"])
        keep_ranges = completed["draft"]["keep_ranges"]
        assert output_duration <= 60.05, output_duration
        assert output_duration >= 55.0, output_duration
        assert any(float(item["start"]) >= 60.0 for item in keep_ranges), keep_ranges
        rendered = render_project(JobContext(Job("r","render",project["id"]), threading.Lock()), project["id"], store, settings, {"quality":"fast"})
        meta = probe_media(settings.exports_dir / rendered["export"]["name"], settings)
        assert meta["duration"] <= 60.2, meta
        print(json.dumps({"ok":True,"requested":60,"draft_duration":output_duration,"render_duration":meta["duration"],"cuts":len(completed["draft"]["cuts"])}, indent=2))
    finally:
        shutil.rmtree(work, ignore_errors=True)

if __name__ == "__main__":
    main()
