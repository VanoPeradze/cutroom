from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import director, render
from cutroom.jobs import Job, JobContext


def _project(
    *,
    a_duration: float = 10.0,
    b_duration: float | None = 10.0,
    a_audio: bool = True,
    b_audio: bool = True,
    b_video: bool = True,
    offset: float = 0.0,
    audio_slot: str = "A",
    camera: str = "stacked",
) -> dict:
    source_b = None
    if b_duration is not None:
        source_b = {
            "duration": b_duration,
            "width": 640 if b_video else 0,
            "height": 360 if b_video else 0,
            "has_audio": b_audio,
        }
    return {
        "id": "project_hardened",
        "name": "hardening",
        "sources": {
            "A": {"duration": a_duration, "width": 640, "height": 360, "has_audio": a_audio},
            "B": source_b,
        },
        "settings": {"aspect": "16:9", "resolution": "720", "quality": "fast", "captions": False, "burn_captions": False},
        "analysis": {"sync": {"offset": offset}, "transcript": {"segments": []}},
        "manual": {
            "crop": {},
            "source_mixer": {
                "screen_slot": "A",
                "camera_slot": "B",
                "primary_role": "screen",
                "audio_slot": audio_slot,
                "sync_offset": offset,
            },
        },
        "draft": {
            "audio_source": audio_slot,
            "keep_ranges": [{"start": 0.0, "end": a_duration}],
            "camera_plan": [{"start": 0.0, "end": a_duration, "camera": camera}],
        },
        "exports": [],
    }


def test_transcription_is_normalized_bounded_and_uses_explicit_language(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        director,
        "transcribe",
        lambda *_args, **_kwargs: {
            "language": "en",
            "language_probability": "not-a-number",
            "duration": 999,
            "segments": [
                {
                    "id": "duplicate",
                    "start": -2,
                    "end": 2,
                    "text": "שלום",
                    "avg_logprob": -0.2,
                    "words": [{"start": -1, "end": 1, "word": "שלום", "probability": 0.9}],
                },
                {"id": "duplicate", "start": 3, "end": 8, "text": "עולם", "words": []},
                {"start": 2, "end": math.nan, "text": "invalid"},
                {"start": 1, "end": 2, "text": ""},
            ],
            "text": "stale raw text",
        },
    )

    transcript, warning = director._transcribe_safely(Path("source.mp4"), None, "he", duration=5.0)

    assert transcript["language"] == "he"
    assert transcript["detected_language"] == "en"
    assert transcript["detected_language_probability"] == 0.0
    assert transcript["language_detection"]["source"] == "explicit"
    assert transcript["duration"] == 5.0
    assert transcript["language_probability"] == 0.0
    assert [(item["start"], item["end"]) for item in transcript["segments"]] == [(0.0, 2.0), (3.0, 5.0)]
    assert len({item["id"] for item in transcript["segments"]}) == 2
    assert transcript["words"] == [{"start": 0.0, "end": 1.0, "word": "שלום", "probability": 0.9}]
    assert transcript["text"] == "שלום עולם"
    assert warning and "normalized" in warning


@pytest.mark.parametrize(
    ("offset", "expected_segments", "expected_words"),
    [
        (2.0, [(2.0, 4.0), (5.0, 6.0)], [(2.25, 3.0)]),
        (-1.0, [(0.0, 1.0), (2.0, 6.0)], []),
    ],
)
def test_source_b_transcript_maps_to_a_timeline_with_clamping(offset, expected_segments, expected_words):
    transcript = {
        "language": "en",
        "duration": 8.0,
        "segments": [
            {"id": "s1", "start": 0.0, "end": 2.0, "text": "first", "words": [{"start": 0.25, "end": 1.0, "word": "first"}]},
            {"id": "s2", "start": 3.0, "end": 7.0, "text": "second", "words": []},
        ],
        "words": [],
        "text": "first second",
    }

    mapped = director._map_transcript_to_timeline(transcript, offset, 6.0)

    assert [(item["start"], item["end"]) for item in mapped["segments"]] == expected_segments
    assert [(item["start"], item["end"]) for item in mapped["words"]] == expected_words
    assert mapped["duration"] == 6.0


def test_source_b_audio_evidence_maps_without_inventing_silence_in_uncovered_gaps():
    profile = {
        "available": True,
        "duration": 4.0,
        "ranges": {"silence": [{"start": 0.0, "end": 1.0, "duration": 1.0}], "clipping": []},
        "waveform": [{"start": 0.0, "end": 0.2, "rms_dbfs": -30.0}],
    }

    mapped = director._map_audio_profile_to_timeline(profile, 2.0, 10.0)

    assert mapped["ranges"]["silence"] == [{"start": 2.0, "end": 3.0, "duration": 1.0}]
    assert mapped["waveform"][0]["start"] == 2.0
    assert all(item["start"] >= 2.0 for items in mapped["ranges"].values() for item in items)


def test_director_audio_source_falls_back_to_a_when_b_has_no_audio_and_to_b_when_a_is_silent():
    value = _project(a_audio=True, b_audio=False, audio_slot="B")
    assert director._analysis_audio_slot(value) == "A"
    value["sources"]["A"]["has_audio"] = False
    value["sources"]["B"]["has_audio"] = True
    assert director._analysis_audio_slot(value) == "B"


def test_director_analyzes_selected_b_audio_on_a_timeline_and_invalidates_offset_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from cutroom.config import load_settings
    from cutroom.projects import ProjectStore

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("B speech source")
    media = store.project_dir(project["id"]) / "media"
    source_a = media / "source-A.mp4"
    source_b = media / "source-B.mp4"
    source_a.write_bytes(b"a-video")
    source_b.write_bytes(b"b-video")

    def attach_sources(current: dict) -> None:
        current["sources"]["A"] = {
            "slot": "A", "name": "A.mp4", "relative_path": "media/source-A.mp4",
            "duration": 10.0, "width": 640, "height": 360, "has_audio": True, "size": source_a.stat().st_size,
        }
        current["sources"]["B"] = {
            "slot": "B", "name": "B.mp4", "relative_path": "media/source-B.mp4",
            "duration": 6.0, "width": 640, "height": 360, "has_audio": True, "size": source_b.stat().st_size,
        }
        current["manual"]["source_mixer"].update({"audio_slot": "B", "sync_offset": 2.0})
        current["settings"].update({
            "goal": "youtube", "instruction": "", "captions": True, "burn_captions": True,
            "spoken_language": "he", "auto_reframe": False, "target_duration": 10,
        })

    store.update(project["id"], attach_sources)
    analyzed_paths: list[Path] = []
    transcription_paths: list[Path] = []
    sync_calls: list[tuple[Path, Path]] = []
    scene_cancel_callbacks: list[object] = []

    def fake_audio(path, _settings, source_duration, **_kwargs):
        analyzed_paths.append(path)
        assert source_duration == 6.0
        assert callable(_kwargs.get("cancel_check"))
        return {
            "available": True,
            "duration": 6.0,
            "summary": {"silence_threshold_dbfs": -42.0},
            "ranges": {"silence": [{"start": 4.5, "end": 5.5, "duration": 1.0}], "quiet_speech": [], "loud_speech": [], "clipping": []},
            "waveform": [{"start": 0.0, "end": 0.2, "rms_dbfs": -20.0}],
        }

    def fake_transcribe(path, *_args, **_kwargs):
        transcription_paths.append(path)
        return {
            "language": "he", "language_probability": 0.99, "duration": 6.0,
            "segments": [{"id": "s1", "start": 0.5, "end": 2.5, "text": "זה תמלול אמין בעברית", "words": [], "avg_logprob": -0.1}],
            "words": [], "text": "זה תמלול אמין בעברית",
        }

    monkeypatch.setattr(director, "analyze_audio", fake_audio)
    monkeypatch.setattr(director, "transcribe", fake_transcribe)
    def fake_scenes(*_args, **kwargs):
        scene_cancel_callbacks.append(kwargs.get("cancel_check"))
        return []

    monkeypatch.setattr(director, "detect_scenes", fake_scenes)
    def fake_sync(path_a, path_b, *_args, **_kwargs):
        sync_calls.append((path_a, path_b))
        assert callable(_kwargs.get("cancel_check"))
        return {"offset": 0.75, "confidence": 0.9, "method": "audio_cross_correlation"}

    monkeypatch.setattr(director, "synchronize_sources", fake_sync)
    monkeypatch.setattr(director, "cuda_available", lambda *_args, **_kwargs: False)

    context = JobContext(Job("job_b_audio_1", "director", project["id"]), threading.Lock())
    director.analyze_project(context, project["id"], store, settings)
    saved = store.load(project["id"])

    assert analyzed_paths == [source_b]
    assert transcription_paths == [source_b]
    assert sync_calls == []
    assert saved["draft"]["audio_source"] == "B"
    assert saved["analysis"]["audio_source"] == "B"
    assert saved["analysis"]["audio_timeline_offset"] == 2.0
    assert saved["analysis"]["transcript"]["segments"][0]["start"] == 2.5
    assert saved["analysis"]["audio"]["ranges"]["silence"][0]["start"] == 6.5

    # A manual sync correction changes timestamp semantics and must not reuse the
    # transcript/audio context mapped with the previous offset.
    store.update(project["id"], lambda current: current["manual"]["source_mixer"].update({"sync_offset": 3.0}))
    context = JobContext(Job("job_b_audio_2", "director", project["id"]), threading.Lock())
    director.analyze_project(context, project["id"], store, settings)
    saved = store.load(project["id"])
    assert analyzed_paths == [source_b, source_b]
    assert transcription_paths == [source_b, source_b]
    assert sync_calls == []
    assert saved["analysis"]["audio_timeline_offset"] == 3.0
    assert saved["analysis"]["transcript"]["segments"][0]["start"] == 3.5

    # Resetting manual sync to Auto must not reuse the cached manual value.
    store.update(project["id"], lambda current: current["manual"]["source_mixer"].update({"sync_offset": None}))
    context = JobContext(Job("job_b_audio_3", "director", project["id"]), threading.Lock())
    director.analyze_project(context, project["id"], store, settings)
    saved = store.load(project["id"])
    assert sync_calls == [(source_a, source_b)]
    assert len(analyzed_paths) == 3 and len(transcription_paths) == 3
    assert saved["analysis"]["audio_timeline_offset"] == 0.75
    assert saved["analysis"]["transcript"]["segments"][0]["start"] == 1.25
    assert scene_cancel_callbacks and all(callable(callback) for callback in scene_cancel_callbacks)


def test_render_plan_never_resurrects_cut_ranges_or_duplicates_overlaps():
    value = _project(a_duration=6.0)
    value["draft"]["keep_ranges"] = [{"start": 0, "end": 2}, {"start": 4, "end": 6}]
    value["draft"]["camera_plan"] = [
        {"start": -5, "end": 5, "camera": "B"},
        {"start": 1, "end": 4.5, "camera": "stacked"},
        {"start": 2, "end": 3, "camera": "not-a-layout"},
    ]

    plan = render._render_plan(value)

    assert sum(item["end"] - item["start"] for item in plan) == pytest.approx(4.0)
    assert all(item["end"] <= 2.0 or item["start"] >= 4.0 for item in plan)
    assert all(item["camera"] in render.CAMERA_LAYOUTS for item in plan)
    assert render._expected_output_duration(value) == pytest.approx(4.0)


def test_explicit_empty_keep_contract_fails_instead_of_exporting_the_whole_source():
    value = _project()
    value["draft"]["keep_ranges"] = []

    with pytest.raises(ValueError, match="no valid kept ranges"):
        render.build_filter_graph(value, 1280, 720)


def test_shorter_b_positive_offset_is_padded_on_a_timeline_for_video_and_audio():
    value = _project(a_duration=10.0, b_duration=3.0, offset=2.0, audio_slot="B")

    graph, maps, has_audio = render.build_filter_graph(value, 1280, 720)

    assert "color=c=black:s=640x360:r=30:d=10.000000" in graph
    assert "[1:v]setpts=PTS-STARTPTS+2.000000/TB" in graph
    assert "[bcanvas][bshifted]overlay=x=0:y=0:eof_action=pass:shortest=0" in graph
    assert "[bv1]trim=start_frame=60:end_frame=150" in graph
    assert "[av0]trim=start_frame=0:end_frame=60" in graph
    assert "[av2]trim=start_frame=150:end_frame=300" in graph
    assert "[1:a]asetpts=PTS-STARTPTS,adelay=2000:all=1,apad,atrim=duration=10.000000" in graph
    assert "asetpts=N/SR/TB[amaster]" in graph
    assert maps == ["-map", "[vout]", "-map", "[aout]"]
    assert has_audio is True


def test_negative_b_offset_trims_b_once_then_uses_a_timeline_ranges():
    value = _project(a_duration=8.0, b_duration=5.0, offset=-1.0, audio_slot="B", camera="B")

    graph, _, has_audio = render.build_filter_graph(value, 1280, 720)

    assert "[1:v]trim=start=1.000000,setpts=PTS-STARTPTS" in graph
    assert "[bv0]trim=start_frame=0:end_frame=120" in graph
    assert "[av1]trim=start_frame=120:end_frame=240" in graph
    assert "[1:a]atrim=start=1.000000" in graph
    assert has_audio is True


def test_missing_b_audio_falls_back_to_a_audio_without_referencing_b_audio_stream():
    value = _project(b_audio=False, audio_slot="B")

    graph, _, has_audio = render.build_filter_graph(value, 1280, 720)

    assert "[0:a]asetpts=PTS-STARTPTS,apad,atrim=duration=10.000000" in graph
    assert "[1:a]" not in graph
    assert has_audio is True


def test_audio_only_b_can_supply_sound_while_video_layout_safely_falls_back_to_a():
    value = _project(a_audio=False, b_audio=True, b_video=False, audio_slot="B", camera="stacked")

    graph, maps, has_audio = render.build_filter_graph(value, 1280, 720)

    assert "[1:v]" not in graph
    assert "[av0]trim=start_frame=0:end_frame=300" in graph
    assert "[1:a]asetpts=PTS-STARTPTS,adelay=0:all=1" in graph
    assert maps == ["-map", "[vout]", "-map", "[aout]"]
    assert has_audio is True


def test_source_b_gain_plan_is_used_only_for_the_offset_director_analyzed():
    value = _project(offset=0.5, audio_slot="B")
    value["analysis"]["audio_timeline_offset"] = 0.5
    value["draft"]["audio_source"] = "B"
    value["draft"]["audio_plan"] = [{"start": 0.5, "end": 1.5, "gain_db": 6.0}]

    matching_graph, _, _ = render.build_filter_graph(value, 1280, 720)
    assert "volume=1.995262" in matching_graph

    value["manual"]["source_mixer"]["sync_offset"] = 2.0
    stale_graph, _, _ = render.build_filter_graph(value, 1280, 720)
    assert "volume=" not in stale_graph


def test_caption_export_requires_the_audio_source_and_offset_director_analyzed():
    value = _project(offset=0.5, audio_slot="B")
    value["settings"].update({"captions": True, "burn_captions": True})
    value["analysis"].update({
        "audio_source": "B",
        "audio_timeline_offset": 0.5,
        "transcript": {"segments": [{"start": 0.5, "end": 1.5, "text": "caption"}]},
    })
    value["draft"]["audio_source"] = "B"

    render._validate_caption_timeline(value)

    value["manual"]["source_mixer"]["sync_offset"] = 2.0
    with pytest.raises(RuntimeError, match="captions_out_of_date"):
        render._validate_caption_timeline(value)

    value["manual"]["source_mixer"].update({"sync_offset": 0.5, "audio_slot": "A"})
    with pytest.raises(RuntimeError, match="captions_out_of_date"):
        render._validate_caption_timeline(value)


def test_no_audio_in_either_source_builds_a_video_only_export_graph():
    value = _project(a_audio=False, b_audio=False, audio_slot="B")

    graph, maps, has_audio = render.build_filter_graph(value, 1280, 720)

    assert "concat=n=1:v=1:a=0[vcat]" in graph
    assert "trim=end_frame=300,setpts=N/30/TB[vout]" in graph
    assert maps == ["-map", "[vout]"]
    assert has_audio is False


def test_source_b_is_not_decoded_when_every_rendered_segment_uses_a():
    value = _project(audio_slot="A", camera="A")

    graph, _, _ = render.build_filter_graph(value, 1280, 720)

    assert "[1:v]" not in graph
    assert "bcanvas" not in graph
    assert "[amasterv]null[av0]" in graph


@pytest.mark.parametrize("offset", [0.4, -0.4])
def test_real_ffmpeg_keeps_a_duration_with_shorter_offset_b(tmp_path: Path, offset: float):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    source_a = tmp_path / "A.mp4"
    source_b = tmp_path / "B.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=24:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source_a),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "smptebars=size=320x180:rate=24:duration=1",
            "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=1",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(source_b),
        ],
        check=True,
        capture_output=True,
    )
    value = _project(a_duration=2.0, b_duration=1.0, offset=offset, audio_slot="B", camera="stacked")
    graph, maps, _ = render.build_filter_graph(value, 320, 180)
    graph_path = tmp_path / f"graph-{offset}.txt"
    graph_path.write_text(graph, encoding="utf-8")
    output = tmp_path / f"output-{offset}.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source_a), "-i", str(source_b),
            "-filter_complex_script", str(graph_path), *maps,
            "-c:v", "libx264", "-preset", "ultrafast", "-vsync", "1", "-r:v", "30",
            "-c:a", "aac", "-t", "2.0", str(output),
        ],
        check=True,
        capture_output=True,
    )
    payload = json.loads(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert float(payload["format"]["duration"]) == pytest.approx(2.0, abs=0.15)
    assert {stream["codec_type"] for stream in payload["streams"]} == {"video", "audio"}
    assert all(float(stream["duration"]) == pytest.approx(2.0, abs=0.15) for stream in payload["streams"])


def test_real_ffmpeg_normalized_offset_audio_has_monotonic_full_timeline(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    source_a = tmp_path / "equal-A.mp4"
    source_b = tmp_path / "equal-B.mp4"
    for path, video, frequency in (
        (source_a, "testsrc2=size=320x180:rate=30:duration=2", 440),
        (source_b, "smptebars=size=180x320:rate=30:duration=2", 660),
    ):
        subprocess.run(
            [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", video,
                "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=2",
                "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-shortest", str(path),
            ],
            check=True,
            capture_output=True,
        )

    value = _project(a_duration=2.0, b_duration=2.0, offset=0.25, audio_slot="B", camera="stacked")
    value["draft"]["audio_policy"] = {"normalize": True, "target_lufs": -16.0}
    graph, maps, _ = render.build_filter_graph(value, 360, 640)
    graph_path = tmp_path / "normalized-offset-graph.txt"
    graph_path.write_text(graph, encoding="utf-8")
    output = tmp_path / "normalized-offset.mp4"
    completed = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "warning", "-y",
            "-i", str(source_a), "-i", str(source_b),
            "-filter_complex_script", str(graph_path), *maps,
            "-c:v", "libx264", "-preset", "ultrafast", "-vsync", "1", "-r:v", "30",
            "-c:a", "aac", "-t", "2.0", str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    stderr = completed.stderr.lower()
    assert "non monotonically increasing" not in stderr
    assert "queue input is backward" not in stderr
    payload = json.loads(
        subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,duration:format=duration", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    assert float(payload["format"]["duration"]) == pytest.approx(2.0, abs=0.15)
    assert {stream["codec_type"] for stream in payload["streams"]} == {"video", "audio"}
    assert all(float(stream["duration"]) == pytest.approx(2.0, abs=0.15) for stream in payload["streams"])


def test_many_short_ranges_keep_exact_frame_duration_and_last_segment(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    source = tmp_path / "short-ranges-source.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i",
            "color=c=blue:s=160x90:r=30:d=10,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='gte(t,9.7)'",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(source),
        ],
        check=True,
        capture_output=True,
    )
    ranges = [
        {"start": index * 0.16, "end": index * 0.16 + 0.08}
        for index in range(62)
    ]
    value = _project(a_duration=10.0, b_duration=None, a_audio=False, camera="A")
    value["draft"]["keep_ranges"] = ranges
    value["draft"]["camera_plan"] = [{"start": 0.0, "end": 10.0, "camera": "A"}]
    graph, maps, has_audio = render.build_filter_graph(value, 160, 90)
    assert has_audio is False
    graph_path = tmp_path / "short-ranges-graph.txt"
    graph_path.write_text(graph, encoding="utf-8")
    output = tmp_path / "short-ranges-output.mp4"
    subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
            "-filter_complex_script", str(graph_path), *maps,
            "-c:v", "libx264", "-preset", "ultrafast", "-vsync", "1", "-r:v", "30",
            "-t", f"{148 / 30:.6f}", str(output),
        ],
        check=True,
        capture_output=True,
    )
    payload = json.loads(
        subprocess.run(
            [
                ffprobe, "-v", "error", "-count_frames",
                "-show_entries", "stream=duration,nb_frames,nb_read_frames:format=duration",
                "-of", "json", str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    expected = render._expected_output_duration(value)
    assert expected == pytest.approx(148 / 30)
    assert float(payload["format"]["duration"]) == pytest.approx(expected, abs=1 / 30)
    assert int(payload["streams"][0]["nb_frames"]) == 148
    assert int(payload["streams"][0]["nb_read_frames"]) == 148

    last_pixel = subprocess.run(
        [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-sseof", "-0.05", "-i", str(output),
            "-vf", "scale=1:1", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert len(last_pixel) == 3
    assert last_pixel[0] > last_pixel[2] + 80


def test_fragment_budget_rejects_pathological_camera_plan():
    value = _project(a_duration=60.0, b_duration=60.0)
    value["draft"]["keep_ranges"] = [{"start": 0.0, "end": 60.0}]
    value["draft"]["camera_plan"] = [
        {"start": index * 0.1, "end": index * 0.1 + 0.1, "camera": "A" if index % 2 else "B"}
        for index in range(501)
    ]

    with pytest.raises(ValueError, match="too many fragments"):
        render._render_plan(value)


def test_output_verifier_rejects_a_short_audio_stream_even_when_container_is_full():
    metadata = {
        "width": 720,
        "height": 1280,
        "duration": 4.0,
        "video_duration": 4.0,
        "has_audio": True,
        "audio_duration": 3.1,
    }

    with pytest.raises(RuntimeError, match="audio duration verification failed"):
        render._verify_output_metadata(
            metadata,
            width=720,
            height=1280,
            expected_duration=4.0,
            expected_audio=True,
        )


def test_output_verifier_allows_only_fixed_mux_and_frame_rounding():
    render._verify_output_metadata(
        {
            "width": 720,
            "height": 1280,
            "duration": 3.967,
            "video_duration": 3.967,
            "has_audio": True,
            "audio_duration": 4.021,
        },
        width=720,
        height=1280,
        expected_duration=4.0,
        expected_audio=True,
    )

    with pytest.raises(RuntimeError, match="container duration verification failed"):
        render._verify_output_metadata(
            {
                "width": 720,
                "height": 1280,
                "duration": 4.2,
                "video_duration": 4.2,
                "has_audio": False,
                "audio_duration": None,
            },
            width=720,
            height=1280,
            expected_duration=4.0,
            expected_audio=False,
        )


class _MemoryStore:
    def __init__(self, root: Path, project: dict):
        self.root = root
        self.project = copy.deepcopy(project)

    def project_dir(self, _project_id: str) -> Path:
        return self.root

    def load(self, _project_id: str) -> dict:
        return copy.deepcopy(self.project)

    def update(self, _project_id: str, mutator, expected_revision=None) -> dict:
        value = copy.deepcopy(self.project)
        replacement = mutator(value)
        self.project = copy.deepcopy(value if replacement is None else replacement)
        return copy.deepcopy(self.project)


def _fake_render_fixture(tmp_path: Path, *, captions: bool = False) -> tuple[dict, _MemoryStore, SimpleNamespace]:
    root = tmp_path / "project"
    exports = tmp_path / "exports"
    (root / "media").mkdir(parents=True)
    exports.mkdir()
    (root / "media" / "source-A.mp4").write_bytes(b"source")
    value = _project(a_duration=1.0, b_duration=None, a_audio=False, b_audio=False, camera="A")
    value["sources"]["A"].update({"relative_path": "media/source-A.mp4"})
    value["settings"].update({"captions": captions})
    value["analysis"] = {"transcript": {"segments": [], "text": ""}}
    settings = SimpleNamespace(
        exports_dir=exports,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        raw={"ffmpeg_threads": 2, "render": {"prefer_hardware": True}},
        render={"prefer_hardware": True, "audio_bitrate": "128k"},
    )
    return value, _MemoryStore(root, value), settings


def test_render_storage_estimate_scales_with_duration_resolution_and_quality():
    settings = SimpleNamespace(render={"audio_bitrate": "192k", "min_free_mb": 0})
    value = _project(a_duration=60.0, b_duration=None, camera="A")

    fast_720 = render._estimate_render_storage(value, 1280, 720, "fast", settings)
    quality_720 = render._estimate_render_storage(value, 1280, 720, "quality", settings)
    quality_1080 = render._estimate_render_storage(value, 1920, 1080, "quality", settings)
    long_value = _project(a_duration=120.0, b_duration=None, camera="A")
    long_quality_1080 = render._estimate_render_storage(long_value, 1920, 1080, "quality", settings)

    assert quality_720["output_bytes"] > fast_720["output_bytes"]
    assert quality_1080["output_bytes"] > quality_720["output_bytes"]
    assert long_quality_1080["output_bytes"] > quality_1080["output_bytes"] * 1.9
    raw_video_bytes = 1920 * 1080 * 3 * 30 * 60
    assert quality_1080["output_bytes"] < raw_video_bytes // 10


def test_render_storage_estimate_accounts_for_every_written_sidecar_and_intermediate():
    settings = SimpleNamespace(render={"audio_bitrate": "128kbps", "min_free_mb": 64})
    value = _project(a_duration=15.0, b_duration=None, camera="A")
    value["draft"]["audio_policy"] = {"normalize": True, "target_lufs": -16.0}
    value["settings"].update({"captions": True, "burn_captions": True})
    value["analysis"]["transcript"] = {
        "segments": [{"start": 0.0, "end": 2.0, "text": "caption text"}],
        "text": "caption text",
    }

    estimate = render._estimate_render_storage(value, 1280, 720, "balanced", settings)

    assert estimate["audio_bytes"] > 0
    assert estimate["caption_ass_bytes"] > 0
    assert estimate["caption_srt_bytes"] > 0
    assert estimate["filter_graph_bytes"] > 0
    assert estimate["project_commit_bytes"] > 0
    assert estimate["normalization_stage_bytes"] == estimate["output_bytes"]
    assert estimate["export_work_bytes"] == (
        estimate["output_bytes"]
        + estimate["normalization_stage_bytes"]
        + estimate["caption_srt_bytes"]
    )
    assert estimate["project_work_bytes"] == (
        estimate["filter_graph_bytes"]
        + estimate["caption_ass_bytes"]
        + estimate["project_commit_bytes"]
    )
    assert estimate["reserve_bytes"] == 64 * 1024**2


def test_render_disk_guard_aggregates_same_volume_and_keeps_one_reserve(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    value, store, settings = _fake_render_fixture(tmp_path)
    settings.render["min_free_mb"] = 32
    checks: list[Path] = []

    def enough_space(path):
        checks.append(Path(path))
        return SimpleNamespace(total=10**12, used=0, free=10**12)

    monkeypatch.setattr(render.shutil, "disk_usage", enough_space)
    estimate = render._ensure_render_storage(value, settings, store.root, 320, 240, "fast")

    assert len(checks) == 1
    assert len(estimate["volumes"]) == 1
    volume = estimate["volumes"][0]
    assert volume["working_bytes"] == estimate["export_work_bytes"] + estimate["project_work_bytes"]
    assert volume["required_bytes"] == volume["working_bytes"] + 32 * 1024**2


def test_render_rejects_insufficient_disk_before_encoder_or_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    value, store, settings = _fake_render_fixture(tmp_path)
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(
        render.shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=4096, used=3072, free=1024),
    )

    def must_not_start(*_args, **_kwargs):
        raise AssertionError("render work started before the disk-space guard")

    monkeypatch.setattr(render, "choose_encoder", must_not_start)
    monkeypatch.setattr(render, "new_id", must_not_start)
    context = JobContext(Job("job_no_space", "render", value["id"]), threading.Lock())

    with pytest.raises(render.InsufficientStorageError) as caught:
        render.render_project(context, value["id"], store, settings)

    error = caught.value
    payload = error.as_dict()
    assert error.status_code == 507
    assert error.status == 507
    assert payload["error"] == "insufficient_storage"
    assert payload["required_bytes"] == error.required_bytes
    assert payload["disk_free_bytes"] == 1024
    assert payload["shortfall_bytes"] == error.required_bytes - 1024
    assert error.required_bytes > error.free_bytes
    assert list(settings.exports_dir.iterdir()) == []
    assert not (store.root / "cache").exists()


@pytest.mark.parametrize("fps", [30, 60])
def test_hardware_failure_retries_cpu_without_mutating_global_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fps):
    value, store, settings = _fake_render_fixture(tmp_path)
    commands: list[list[str]] = []
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("h264_nvenc", ["-preset", "p4"]))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(render, "probe_media", lambda path, _settings: {"width": 320, "height": 240, "duration": 1.0, "fps": fps, "size": path.stat().st_size})

    def fake_run(_context, command, _expected):
        commands.append(command)
        Path(command[-1]).write_bytes(b"rendered")
        return (1, "GPU unavailable") if "h264_nvenc" in command else (0, "")

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_hardware", "render", value["id"]), threading.Lock())

    result = render.render_project(context, value["id"], store, settings, {"fps": fps})

    assert len(commands) == 2
    assert "h264_nvenc" in commands[0] and "libx264" in commands[1]
    assert all(command[command.index("-r:v") + 1] == str(fps) for command in commands)
    assert result["export"]["fps"] == fps
    assert settings.raw["render"]["prefer_hardware"] is True
    assert result["export"]["encoder"] == "libx264"
    assert not list(settings.exports_dir.glob("*.partial.mp4"))


def test_loudness_normalization_runs_as_bounded_audio_only_second_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    value, store, settings = _fake_render_fixture(tmp_path)
    value["draft"]["audio_policy"] = {"normalize": True, "target_lufs": -16.0}
    store.project = copy.deepcopy(value)
    commands: list[list[str]] = []
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", ["-preset", "veryfast"]))
    monkeypatch.setattr(
        render,
        "build_filter_graph",
        lambda *_args: ("anull", ["-map", "[vout]", "-map", "[aout]"], True),
    )
    monkeypatch.setattr(
        render,
        "probe_media",
        lambda path, _settings: {
            "width": 320,
            "height": 240,
            "duration": 1.0,
            "video_duration": 1.0,
            "audio_duration": 1.0,
            "has_audio": True,
            "fps": 30,
            "size": path.stat().st_size,
        },
    )

    def fake_run(_context, command, _expected):
        commands.append(command)
        Path(command[-1]).write_bytes(b"rendered")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_two_pass", "render", value["id"]), threading.Lock())

    result = render.render_project(context, value["id"], store, settings)

    assert len(commands) == 2
    assert commands[0][-1].endswith(".render-stage.mp4")
    assert commands[1][commands[1].index("-c:v") + 1] == "copy"
    assert commands[1][commands[1].index("-af") + 1].startswith("loudnorm=I=-16.0")
    assert result["export"]["duration"] == 1.0
    assert not list(settings.exports_dir.glob("*.render-stage.mp4"))
    assert not list(settings.exports_dir.glob("*.partial.mp4"))


def test_cpu_ffmpeg_failure_cleans_partial_output_and_reports_bounded_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    value, store, settings = _fake_render_fixture(tmp_path)
    settings.raw["render"]["prefer_hardware"] = False
    settings.render["prefer_hardware"] = False
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))

    def fake_run(_context, command, _expected):
        Path(command[-1]).write_bytes(b"partial")
        return 1, "E" * 5000

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_failure", "render", value["id"]), threading.Lock())

    with pytest.raises(RuntimeError, match="FFmpeg render failed") as caught:
        render.render_project(context, value["id"], store, settings)

    assert len(str(caught.value)) < 1700
    assert list(settings.exports_dir.iterdir()) == []


def test_empty_transcript_does_not_create_or_advertise_empty_sidecar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    value, store, settings = _fake_render_fixture(tmp_path, captions=True)
    commands: list[list[str]] = []
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(render, "probe_media", lambda path, _settings: {"width": 320, "height": 240, "duration": 1.0, "fps": 30, "size": path.stat().st_size})

    def fake_run(_context, command, _expected):
        commands.append(command)
        Path(command[-1]).write_bytes(b"rendered")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_captions", "render", value["id"]), threading.Lock())

    result = render.render_project(context, value["id"], store, settings)

    assert "captions_name" not in result["export"]
    assert not list(settings.exports_dir.glob("*.srt"))
    thread_index = commands[0].index("-threads")
    assert commands[0][thread_index + 1] == "2"
    assert commands[0][commands[0].index("-vsync") + 1] == "1"
    assert commands[0][commands[0].index("-r:v") + 1] == "30"
    assert commands[0][commands[0].index("-t") + 1] == "1.000000"
    assert "-shortest" not in commands[0]


def test_late_cancellation_after_export_commit_keeps_success_authoritative(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    value, store, settings = _fake_render_fixture(tmp_path)
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(render, "probe_media", lambda path, _settings: {"width": 320, "height": 240, "duration": 1.0, "fps": 30, "size": path.stat().st_size})

    def fake_run(_context, command, _expected):
        Path(command[-1]).write_bytes(b"rendered")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_late_cancel", "render", value["id"]), threading.Lock())
    original_update = store.update

    def cancel_after_update(project_id, mutator, expected_revision=None):
        assert context.committed is True
        saved = original_update(project_id, mutator, expected_revision)
        context.job.cancel_event.set()
        return saved

    store.update = cancel_after_update

    result = render.render_project(context, value["id"], store, settings)

    assert context.committed is True
    assert context.job.cancel_event.is_set()
    assert store.project["exports"][0]["id"] == result["export"]["id"]
    assert (settings.exports_dir / result["export"]["name"]).is_file()


def test_locked_stale_export_cleanup_cannot_fail_a_new_committed_export(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    value, store, settings = _fake_render_fixture(tmp_path)
    value["exports"] = [{"name": f"old-{index}.mp4"} for index in range(19)] + [{"name": "locked.mp4"}]
    store.project = copy.deepcopy(value)
    (settings.exports_dir / "locked.mp4").mkdir()
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(render, "probe_media", lambda path, _settings: {"width": 320, "height": 240, "duration": 1.0, "fps": 30, "size": path.stat().st_size})

    def fake_run(_context, command, _expected):
        Path(command[-1]).write_bytes(b"rendered")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_locked_retention", "render", value["id"]), threading.Lock())

    result = render.render_project(context, value["id"], store, settings)

    assert result["export"]["id"] == store.project["exports"][0]["id"]
    assert (settings.exports_dir / "locked.mp4").is_dir()


def test_cancellable_media_runner_terminates_a_long_process_quickly(tmp_path: Path):
    from cutroom.jobs import JobCancelled
    from cutroom.media import run_command

    child = tmp_path / "long_process.py"
    child.write_text("import time\nwhile True:\n    time.sleep(1)\n", encoding="utf-8")
    checks = 0

    def cancel() -> None:
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise JobCancelled("cancel media process")

    started = time.monotonic()
    with pytest.raises(JobCancelled):
        run_command([sys.executable, str(child)], cancel_check=cancel)

    assert time.monotonic() - started < 2.5
    assert checks >= 3


def test_audio_analysis_cancels_while_ffmpeg_stdout_is_blocked(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from cutroom import audio
    from cutroom.jobs import JobCancelled

    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []

    def blocked_popen(*_args, **kwargs):
        process = real_popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"),
        )
        processes.append(process)
        return process

    monkeypatch.setattr(audio.subprocess, "Popen", blocked_popen)
    settings = SimpleNamespace(
        ffmpeg="unused",
        raw={"audio_analysis_sample_rate": 8000, "audio_analysis_window_seconds": 0.20},
    )
    checks = 0

    def cancel() -> None:
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise JobCancelled("cancel blocked audio decode")

    started = time.monotonic()
    with pytest.raises(JobCancelled):
        audio.analyze_audio(tmp_path / "source.mp4", settings, 60.0, cancel_check=cancel)

    assert time.monotonic() - started < 2.5
    assert processes and processes[0].poll() is not None


def test_scene_detection_forwards_cancellation_into_ffmpeg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from cutroom import media
    from cutroom.jobs import JobCancelled

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    settings = SimpleNamespace(ffmpeg="ffmpeg", raw={"ffmpeg_threads": 2, "scene_analysis_fps": 1.5})

    def cancel() -> None:
        raise JobCancelled("cancel scenes")

    def fake_run(_command, **kwargs):
        assert kwargs.get("cancel_check") is cancel
        kwargs["cancel_check"]()

    monkeypatch.setattr(media, "run_command", fake_run)

    with pytest.raises(JobCancelled):
        media.detect_scenes(source, settings, cancel_check=cancel)


def test_scene_detection_stratifies_more_than_max_points_across_full_timeline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from cutroom import media

    source = tmp_path / "long-source.mp4"
    source.write_bytes(b"source")
    settings = SimpleNamespace(
        ffmpeg="ffmpeg",
        raw={"ffmpeg_threads": 2, "scene_analysis_fps": 1.5},
    )
    parsed_points = [float(index * 10) for index in range(600)]
    stderr = "\n".join(
        f"[Parsed_showinfo_3] n:{index} pts_time:{point:.3f}"
        for index, point in enumerate(parsed_points)
    )

    monkeypatch.setattr(
        media,
        "run_command",
        lambda *_args, **_kwargs: SimpleNamespace(stderr=stderr),
    )

    points = media.detect_scenes(source, settings, max_points=180)

    assert len(points) == 180
    assert points == sorted(points)
    assert points[0] == parsed_points[0]
    assert points[-1] == parsed_points[-1]
    assert points != parsed_points[:180]
    timeline_end = parsed_points[-1]
    assert any(point <= timeline_end * 0.10 for point in points)
    assert any(abs(point - timeline_end * 0.50) <= 20.0 for point in points)
    assert any(point >= timeline_end * 0.90 for point in points)


def test_source_sync_forwards_cancellation_to_audio_extraction(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from cutroom import sync
    from cutroom.jobs import JobCancelled

    source_a = tmp_path / "A.mp4"
    source_b = tmp_path / "B.mp4"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    settings = SimpleNamespace(ffmpeg="ffmpeg")
    calls = 0

    def cancel() -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise JobCancelled("cancel sync")

    def fake_run(_command, **kwargs):
        assert kwargs.get("cancel_check") is cancel
        kwargs["cancel_check"]()

    monkeypatch.setattr(sync, "run_command", fake_run)

    with pytest.raises(JobCancelled):
        sync.synchronize_sources(source_a, source_b, settings, cancel_check=cancel)

    assert calls >= 2


def test_low_confidence_source_sync_keeps_b_on_the_a_timeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    import numpy as np

    from cutroom import sync

    source_a = tmp_path / "A.mp4"
    source_b = tmp_path / "B.mp4"
    source_a.write_bytes(b"a")
    source_b.write_bytes(b"b")
    settings = SimpleNamespace(ffmpeg="ffmpeg")
    envelope = np.ones(100, dtype=np.float32)
    correlation = np.ones(199, dtype=np.float64)
    # lags are -99..99, therefore index 129 represents a misleading +0.30s.
    correlation[129] = 1.01
    monkeypatch.setattr(sync, "_audio_envelope", lambda *_args, **_kwargs: envelope)
    monkeypatch.setattr(sync, "_fft_correlation", lambda *_args, **_kwargs: correlation)

    result = sync.synchronize_sources(source_a, source_b, settings)

    assert result["confidence"] < sync.MIN_AUTOMATIC_SYNC_CONFIDENCE
    assert result["measured_offset"] == 0.3
    assert result["offset"] == 0.0
    assert result["reliable"] is False


def test_cancelled_proxy_keeps_previous_preview_and_removes_partial(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from cutroom import media
    from cutroom.jobs import JobCancelled

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    target = tmp_path / "proxy.mp4"
    target.write_bytes(b"previous-preview")
    settings = SimpleNamespace(ffmpeg="ffmpeg", raw={"proxy_height": 360, "proxy_crf": 28, "ffmpeg_threads": 2})

    def cancel() -> None:
        raise JobCancelled("cancel proxy")

    def fake_run(command, **kwargs):
        Path(command[-1]).write_bytes(b"unfinished")
        kwargs["cancel_check"]()

    monkeypatch.setattr(media, "run_command", fake_run)

    with pytest.raises(JobCancelled):
        media.create_proxy(source, target, settings, cancel_check=cancel)

    assert target.read_bytes() == b"previous-preview"
    assert not list(tmp_path.glob(".proxy-*.partial.mp4"))


def test_cancelled_thumbnail_generation_is_transactional_and_cleans_staging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    from cutroom import media
    from cutroom.jobs import JobCancelled

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    output_dir = tmp_path / "thumbs"
    output_dir.mkdir()
    (output_dir / "thumb-001.jpg").write_bytes(b"previous-thumbnail")
    settings = SimpleNamespace(ffmpeg="ffmpeg")

    def cancel() -> None:
        raise JobCancelled("cancel thumbnails")

    def fake_run(command, **kwargs):
        Path(str(command[-1]).replace("%03d", "001")).write_bytes(b"unfinished")
        kwargs["cancel_check"]()

    monkeypatch.setattr(media, "run_command", fake_run)

    with pytest.raises(JobCancelled):
        media.extract_thumbnails(source, output_dir, 10.0, settings, cancel_check=cancel)

    assert (output_dir / "thumb-001.jpg").read_bytes() == b"previous-thumbnail"
    assert not list(tmp_path.glob(".thumbs-*.partial"))
    assert not list(tmp_path.glob(".thumbs-*.backup"))
