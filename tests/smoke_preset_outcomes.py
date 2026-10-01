"""Real render contract for preset selection; transcript/model choices are stubs.

This proves source passages, picture/audio clocks and captions reach the output.
It does not measure a model's ability to recognize a real clutch or story.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cutroom import director
from cutroom.config import load_settings
from cutroom.edit_styles import get_edit_style
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project
from cutroom.sequence import editor_sequence_snapshot


def run(command):
    return subprocess.run(command, check=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--director-source", type=Path)
    args = parser.parse_args()
    module = director
    if args.director_source:
        spec = importlib.util.spec_from_file_location("cutroom._preset_baseline_director", args.director_source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    evidence = args.evidence_dir
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    results = []
    with tempfile.TemporaryDirectory(prefix="cr-preset-") as temp:
        work = Path(temp)
        source = work / "source.mp4"
        colors = [(4, 6, "yellow"), (6, 8, "red"), (8, 10, "lime"),
                  (22, 24, "blue"), (24, 26, "magenta"), (26, 28, "cyan")]
        filters = ",".join(f"drawbox=x=0:y=0:w=iw:h=ih:color={color}:t=fill:enable='gte(t,{start})*lt(t,{end})'"
                           for start, end, color in colors)
        run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             "color=c=#222222:size=320x180:rate=30:duration=32", "-f", "lavfi", "-i",
             "aevalsrc=0.18*sin(2*PI*if(lt(t\,16)\,440\,880)*t):s=48000:d=32",
             "-vf", filters, "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source)])
        config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        config["data_dir"] = str(work / "data")
        config["ai"]["enabled"] = False
        config["render"]["prefer_hardware"] = False
        config_path = work / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        settings = load_settings(config_path)
        store = ProjectStore(settings)
        names = {2: "First setup", 3: "First action", 4: "First payoff",
                 11: "Second setup", 12: "Second action", 13: "Second payoff"}
        segments = [{"id": f"s{i}", "start": i * 2.0, "end": i * 2.0 + 1.9,
                     "text": names.get(i, "Background explanation") + ". This fixture contains a complete passage.",
                     "words": [], "avg_logprob": -0.1} for i in range(16)]
        transcript = {"language": "en", "language_probability": .99, "duration": 32.0,
                      "segments": segments, "words": [], "text": " ".join(row["text"] for row in segments)}

        def plan(_context, current_segments, *_args, **_kwargs):
            return {"segments": [{**row, "editorial_score": .8} for row in current_segments],
                    "decision": {"keep_ids": [row["id"] for row in current_segments], "remove_ids": [],
                                 "highlight_ids": ["s4"], "opening_id": "s2", "closing_id": "s4",
                                 "story_ranges": [{"start": 4.0, "end": 10.0}, {"start": 22.0, "end": 28.0}],
                                 "title": "Fixture complete moments", "summary": "Two supplied complete moments."},
                    "story_beats": [], "story_hierarchy": {"fixture": True}}, "fixture_story"

        module._transcribe_safely = lambda *_args, **_kwargs: (copy.deepcopy(transcript), None)
        module._plan_edit_with_cancel = plan
        module.detect_scenes = lambda *_args, **_kwargs: [4, 6, 8, 10, 22, 24, 26, 28]
        for style_id, expected_duration in (("competitive_clutch", 6.0), ("stream_highlights", 12.0)):
            project = store.create(style_id)
            media = store.project_dir(project["id"]) / "media" / "source-A.mp4"
            shutil.copy2(source, media)
            project["sources"]["A"] = {"slot": "A", "name": "safe-synthetic.mp4",
                                       "relative_path": "media/source-A.mp4", **probe_media(media, settings)}
            project["settings"].update({**get_edit_style(style_id)["defaults"], "edit_style": style_id,
                                        "goal": "short", "target_duration": 12, "aspect": "source",
                                        "resolution": "720", "quality": "fast", "fps": 30,
                                        "captions": True, "burn_captions": False, "auto_reframe": False,
                                        "editorial_effects": False})
            store.save(project)
            context = JobContext(Job("d", "director", project["id"]), threading.Lock())
            result = module.analyze_project(context, project["id"], store, settings)
            completed = store.load(project["id"])
            rendered = render_project(JobContext(Job("r", "render", project["id"]), threading.Lock()),
                                      project["id"], store, settings, {"quality": "fast"})
            output = settings.exports_dir / rendered["export"]["name"]
            metadata = probe_media(output, settings)
            frame_colors = []
            frequencies = []
            for index, second in enumerate([1, 3, 5] + ([7, 9, 11] if metadata["duration"] > 8 else [])):
                raw = run([ffmpeg, "-v", "error", "-ss", str(second), "-i", str(output),
                           "-frames:v", "1", "-vf", "crop=2:2:158:88", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
                frame_colors.append(list(raw[:3]))
                if evidence:
                    run([ffmpeg, "-v", "error", "-y", "-ss", str(second), "-i", str(output),
                         "-frames:v", "1", str(evidence / f"{style_id}-{index}.png")])
            for second in [1] + ([7] if metadata["duration"] > 8 else []):
                raw = run([ffmpeg, "-v", "error", "-ss", str(second), "-i", str(output),
                           "-t", "0.5", "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"])
                samples = np.frombuffer(raw, dtype="<f4")
                frequencies.append(round(np.fft.rfftfreq(samples.size, 1 / 48000)[np.argmax(np.abs(np.fft.rfft(samples)))], 1))
            captions = (settings.exports_dir / rendered["export"]["captions_name"]).read_text(encoding="utf-8")
            row = {"style": style_id, "source_duration": 32.0,
                   "draft_duration": completed["draft"]["output_duration"],
                   "editor_duration": editor_sequence_snapshot(completed)["duration"],
                   "render_duration": metadata["duration"], "keep_ranges": completed["draft"]["keep_ranges"],
                   "frame_colors": frame_colors, "audio_hz": frequencies,
                   "first_setup_action_payoff_captions": all(text in captions for text in ("First setup", "First action", "First payoff")),
                   "caption_times": [line for line in captions.splitlines() if " --> " in line],
                   "second_story_captions": "Second setup" in captions,
                   "expected_duration": expected_duration,
                   "applied_to_timeline": result.get("applied_to_timeline")}
            if evidence:
                shutil.copy2(output, evidence / f"{style_id}.mp4")
                (evidence / f"{style_id}.srt").write_text(captions, encoding="utf-8")
            results.append(row)
        report = {"evaluation": "synthetic render contract; transcript and model selection are stubs", "results": results}
        if evidence:
            (evidence / "result.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        for row in results:
            assert abs(row["draft_duration"] - row["expected_duration"]) < .05, row
            assert abs(row["editor_duration"] - row["expected_duration"]) < .05, row
            assert abs(row["render_duration"] - row["expected_duration"]) < .15, row
            assert row["first_setup_action_payoff_captions"], row
            assert row["second_story_captions"] is (row["style"] == "stream_highlights"), row
            expected_times = [f"00:00:{second:02d},000 --> 00:00:{second + 1:02d},900"
                              for second in range(0, int(row["expected_duration"]), 2)]
            assert row["caption_times"] == expected_times, row
            expected_colors = [(255, 255, 0), (255, 0, 0), (0, 255, 0)]
            if row["style"] == "stream_highlights":
                expected_colors += [(0, 0, 255), (255, 0, 255), (0, 255, 255)]
            assert all(max(abs(actual - expected) for actual, expected in zip(color, reference)) < 10
                       for color, reference in zip(row["frame_colors"], expected_colors)), row
            assert row["audio_hz"] == ([440.0] if row["style"] == "competitive_clutch" else [440.0, 880.0]), row


if __name__ == "__main__":
    main()
