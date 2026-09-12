from __future__ import annotations

import copy
import json
import shutil
import subprocess
import threading
from array import array
from types import SimpleNamespace

import pytest

from cutroom import render
from cutroom.captions import build_srt
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from test_source_tracks_render import clip, media  # Reuse isolated color/tone fixtures.


def sequence_project():
    return {
        "sources": {slot: {"duration": 4, "width": 160, "height": 100, "has_audio": True} for slot in ("A", "B")},
        "settings": {"fps": 60, "aspect": "source", "resolution": "720", "editorial_effects": True},
        "manual": {
            "sequence": {"version": 1, "duration": 6, "camera_plan": [{"start": 0, "end": 6, "camera": "stacked"}]},
            "source_mixer": {"first_slot": "B", "audio_slot": "A", "stack_fit": "cover"},
            "source_tracks": {"A": [clip(0, 1, 2), clip(2, 3, 0, "earlier"), clip(4, 6, 2, "repeat")],
                              "B": [clip(0, 1.5), clip(4, 5, 2, "later")]},
        },
        # This old AI draft must never mask or truncate the new sequence again.
        "draft": {"keep_ranges": [{"start": 1, "end": 2}], "camera_plan": [{"start": 0, "end": 4, "camera": "A"}]},
        "analysis": {"audio_source": "A", "transcript": {"segments": [
            {"start": 0.1, "end": 0.9, "text": "First", "words": [{"start": 0.1, "end": 0.9, "word": "First"}]},
            {"start": 2.1, "end": 2.9, "text": "Later", "words": [{"start": 2.1, "end": 2.9, "word": "Later"}]},
        ]}},
    }


def test_sequence_plan_uses_its_edit_clock_and_own_layouts():
    value = sequence_project()
    original = copy.deepcopy(value)
    assert render._render_plan(value) == [
        {"start": 0, "end": 1, "camera": "stacked"},
        {"start": 1, "end": 1.5, "camera": "B"},
        {"start": 1.5, "end": 2, "camera": "black"},
        {"start": 2, "end": 3, "camera": "A"},
        {"start": 3, "end": 4, "camera": "black"},
        {"start": 4, "end": 5, "camera": "stacked"},
        {"start": 5, "end": 6, "camera": "A"},
    ]
    assert render._expected_output_duration(value) == 6
    assert render._caption_ranges(value) == [{"start": 0, "end": 6}]
    assert value == original and value["sources"]["A"]["duration"] == 4


def test_sequence_marker_absent_keeps_legacy_source_clock_contract():
    value = sequence_project()
    value["manual"].pop("sequence")
    assert render._expected_output_duration(value) == 1
    assert render._caption_ranges(value) == [{"start": 1, "end": 2}]


def test_sequence_missing_track_data_is_black_not_implicit_footage():
    value = sequence_project()
    value["manual"].pop("source_tracks")
    assert render._render_plan(value) == [{"start": 0, "end": 6, "camera": "black"}]
    graph, _, has_audio = render.build_filter_graph(value, 160, 100)
    assert has_audio and "anullsrc" in graph
    assert "[0:v]" not in graph and "[0:a]" not in graph and "[1:v]" not in graph


def test_sequence_one_frame_clip_is_renderable_and_duration_is_not_source_length():
    value = sequence_project()
    value["manual"]["sequence"] = {"version": 1, "duration": 1 / 60, "camera_plan": []}
    value["manual"]["source_tracks"] = {"A": [clip(0, 1 / 60, 2)], "B": []}
    assert render._expected_output_duration(value) == pytest.approx(1 / 60)
    graph, _, _ = render.build_filter_graph(value, 160, 100)
    assert "trim=end_frame=1" in graph


def test_export_fps_override_does_not_discard_a_valid_short_sequence_clip():
    value = sequence_project()
    value["manual"]["sequence"] = {"version": 1, "duration": 1 / 60, "camera_plan": []}
    value["manual"]["source_tracks"] = {"A": [clip(0, 1 / 60, 2)], "B": []}
    value["settings"]["fps"] = 30
    graph, _, _ = render.build_filter_graph(value, 160, 100)
    assert "[0:v]" in graph  # Frame rounding is allowed; silently dropping the media is not.
    assert render._frame_aligned_plan(value)[0]["camera"] == "A"


def test_sequence_disables_source_clock_effects_and_fingerprints_layout(monkeypatch):
    value = sequence_project()
    monkeypatch.setattr(render, "compile_automatic_effects", lambda project: pytest.fail("Source-clock effects must not run"))
    graph, _, _ = render.build_filter_graph(value, 160, 100)
    assert "[vbase]" not in graph
    assert render._render_effects_payload(value) == {"effects": [], "filter_expression": None}
    before = render._render_input_fingerprint(value)
    value["manual"]["sequence"]["camera_plan"][0]["camera"] = "B"
    assert before != render._render_input_fingerprint(value)


def test_sequence_captions_follow_repeat_beyond_physical_source_duration(tmp_path):
    value = sequence_project()
    transcript = render._caption_transcript(value)
    assert [item["text"] for item in transcript["segments"]] == ["Later", "First", "Later"]
    assert [item["start"] for item in transcript["segments"]] == pytest.approx([0.1, 2.1, 4.1])
    target = build_srt(transcript, render._caption_ranges(value), tmp_path / "sequence.srt")
    text = target.read_text(encoding="utf-8")
    assert "00:00:04,100 --> 00:00:04,900\nLater" in text
    estimate = render._estimate_render_storage(value, 160, 100, "fast", SimpleNamespace(render={"min_free_mb": 0}))
    assert estimate["duration_seconds"] == 6


@pytest.mark.parametrize("fps", [30, 60])
def test_real_sequence_export_reorders_extends_and_preserves_audio_gaps(tmp_path, media, fps):
    ffmpeg, ffprobe, paths = media
    value = sequence_project()
    value["settings"]["fps"] = fps
    graph, maps, _ = render.build_filter_graph(value, 160, 100)
    script = tmp_path / "sequence-graph.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "sequence.mp4"
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
                             "-filter_complex_script", str(script), *maps, "-c:v", "libx264", "-preset", "ultrafast",
                             "-c:a", "aac", "-r", str(fps), "-t", "6", str(output)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    metadata = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    assert video["avg_frame_rate"] == f"{fps}/1" and int(video["nb_frames"]) == 6 * fps
    frames = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    def pixel(time, y=70):
        offset = int(time * fps) * 160 * 100 * 3 + (y * 160 + 80) * 3
        return tuple(frames[offset:offset + 3])
    assert pixel(0.5)[1] > 200  # Later green A material comes first.
    assert pixel(0.5, 10)[2] > 200  # B facecam above it.
    assert pixel(1.25)[2] > 200 and max(pixel(1.75)) < 15
    assert pixel(2.5)[0] > 200 and max(pixel(3.5)) < 15
    assert pixel(4.5, 10)[0] > 200 and pixel(4.5, 10)[1] > 200  # Moved yellow B.
    assert pixel(5.5)[1] > 200  # A remains after physical A EOF on the edit clock.
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
    for time, expected in [(0.4, 660), (2.4, 440), (4.4, 660), (5.4, 660)]:
        window = samples[int(time * 48000):int((time + 0.1) * 48000)]
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / 0.1
        assert frequency == pytest.approx(expected, abs=15)
    for time in (1.4, 3.4):
        assert max(abs(sample) for sample in samples[int(time * 48000):int((time + 0.1) * 48000)]) < 0.001


def test_real_render_project_burns_and_exports_remapped_sequence_captions(tmp_path, media, monkeypatch):
    _, _, paths = media
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.render["prefer_hardware"] = False
    store = ProjectStore(settings)
    saved = store.create("Sequence captions")
    value = sequence_project()
    for slot, source in zip(("A", "B"), paths):
        target = store.project_dir(saved["id"]) / "media" / f"{slot}.mp4"
        shutil.copyfile(source, target)
        value["sources"][slot]["relative_path"] = f"media/{slot}.mp4"
    saved.update(value)
    saved["settings"].update({"captions": True, "burn_captions": True, "quality": "fast"})
    store.save(saved)
    captured = []
    original_ass = render.build_ass
    def capture_ass(transcript, *args, **kwargs):
        captured.extend(row["start"] for row in transcript["segments"])
        return original_ass(transcript, *args, **kwargs)
    monkeypatch.setattr(render, "build_ass", capture_ass)
    context = JobContext(Job("sequence-export", "render", saved["id"]), threading.Lock())
    result = render.render_project(context, saved["id"], store, settings, {"quality": "fast"})
    record = result["export"]
    assert record["duration"] == pytest.approx(6, abs=1 / 60)
    assert record["fps"] == 60 and record["captions_burned"]
    assert record["editorial_effects"] == [] and captured == pytest.approx([0.1, 2.1, 4.1])
    assert "00:00:04,100 --> 00:00:04,900\nLater" in (settings.exports_dir / record["captions_name"]).read_text(encoding="utf-8")
    assert store.load(saved["id"])["sources"]["A"]["duration"] == 4
