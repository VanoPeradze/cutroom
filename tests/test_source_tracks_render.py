from __future__ import annotations

import copy
import json
import shutil
import subprocess
from array import array

import pytest

from cutroom.render import (
    _caption_transcript, _effective_audio_slot, _frame_aligned_plan,
    _render_input_fingerprint, _render_plan, _validate_caption_timeline, build_filter_graph,
)


def clip(start, end, source_start=0, name="clip"):
    return {"id": name, "start": start, "end": end, "source_start": source_start}


def project(layout="stacked", fps=30):
    return {
        "sources": {slot: {"duration": 4, "width": 160, "height": 100, "has_audio": True} for slot in ("A", "B")},
        "settings": {"fps": fps, "editorial_effects": False},
        "manual": {"source_mixer": {"first_slot": "B", "audio_slot": "A", "stack_fit": "cover"},
                   "source_tracks": {"A": [clip(0, 1, 2), clip(2, 3, 0, "later")], "B": [clip(0, 2)]}},
        "draft": {"keep_ranges": [{"start": 0, "end": 4}], "camera_plan": [{"start": 0, "end": 4, "camera": layout}]},
    }


@pytest.mark.parametrize("layout", ["stacked", "pip", "side_by_side"])
def test_track_availability_resolves_composites_and_black(layout):
    assert _render_plan(project(layout)) == [
        {"start": 0, "end": 1, "camera": layout},
        {"start": 1, "end": 2, "camera": "B"},
        {"start": 2, "end": 3, "camera": "A"},
        {"start": 3, "end": 4, "camera": "black"},
    ]


def test_source_only_layout_falls_back_without_resurrecting_removed_footage():
    assert [row["camera"] for row in _render_plan(project("A"))] == ["A", "B", "A", "black"]
    value = project("B")
    value["manual"]["source_tracks"] = {"A": [], "B": []}
    graph, maps, has_audio = build_filter_graph(value, 160, 100)
    assert _render_plan(value) == [{"start": 0, "end": 4, "camera": "black"}]
    assert "[0:v]" not in graph and "[1:v]" not in graph and "[0:a]" not in graph and "[1:a]" not in graph
    assert "anullsrc" in graph and has_audio


def test_selected_audio_never_falls_back_after_tracks_are_edited():
    value = project()
    value["manual"]["source_tracks"]["A"] = []
    assert _effective_audio_slot(value) == "A"
    value["sources"]["A"]["has_audio"] = False
    assert _effective_audio_slot(value) is None


def test_independent_track_fingerprint_changes_even_when_draft_does_not():
    value = project()
    before = _render_input_fingerprint(value)
    value["manual"]["source_tracks"]["A"][0]["source_start"] = 1
    assert _render_input_fingerprint(value) != before


def test_caption_words_follow_moved_repeated_audio_and_exclude_gap():
    value = project()
    value["analysis"] = {"audio_source": "A", "transcript": {"language": "he", "segments": [
        {"start": 0.1, "end": 0.9, "text": "first", "words": [{"start": 0.1, "end": 0.9, "word": "first"}]},
        {"start": 1.1, "end": 1.9, "text": "removed", "words": [{"start": 1.1, "end": 1.9, "word": "removed"}]},
        {"start": 2.1, "end": 2.9, "text": "moved", "words": [{"start": 2.1, "end": 2.9, "word": "moved"}]},
    ]}}
    original = copy.deepcopy(value)
    result = _caption_transcript(value)
    assert [row["text"] for row in result["segments"]] == ["moved", "first"]
    assert [row["start"] for row in result["segments"]] == pytest.approx([0.1, 2.1])
    assert result["language"] == "he" and value == original


def test_b_captions_undo_analyzed_offset_before_mapping_new_clip():
    value = project()
    value["settings"]["captions"] = True
    value["manual"]["source_mixer"].update({"audio_slot": "B", "sync_offset": 1})
    value["manual"]["source_tracks"]["B"] = [clip(2, 3, 0)]
    value["analysis"] = {"audio_source": "B", "audio_timeline_offset": -0.5,
                         "transcript": {"segments": [{"start": 0.1, "end": 0.4, "text": "hello"}]}}
    _validate_caption_timeline(value)
    assert _caption_transcript(value)["segments"][0]["start"] == pytest.approx(2.6)
    value["analysis"]["audio_source"] = "A"
    with pytest.raises(RuntimeError, match="captions_out_of_date"):
        _validate_caption_timeline(value)


@pytest.fixture
def media(tmp_path):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    paths = []
    for slot, frequency in (("A", 440), ("B", 880)):
        path = tmp_path / f"{slot}.mp4"
        video = ("color=red:s=160x100:r=60:d=2[r];color=lime:s=160x100:r=60:d=2[g];[r][g]concat=n=2:v=1:a=0"
                 if slot == "A" else "color=blue:s=160x100:r=60:d=2[b];color=yellow:s=160x100:r=60:d=2[y];[b][y]concat=n=2:v=1:a=0")
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", video,
                        "-f", "lavfi", "-i", f"aevalsrc='0.125*sin(2*PI*if(lt(t,2),{frequency},{frequency * 1.5})*t)':s=48000:d=4",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path)],
                       check=True, capture_output=True, timeout=15)
        paths.append(path)
    return ffmpeg, ffprobe, paths


@pytest.mark.parametrize("fps", [30, 60])
def test_real_ffmpeg_tracks_move_remove_stack_and_audio_gap(tmp_path, media, fps):
    ffmpeg, ffprobe, paths = media
    value = project(fps=fps)
    graph, maps, has_audio = build_filter_graph(value, 160, 100)
    assert has_audio
    script = tmp_path / "graph.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "output.mp4"
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
                            "-filter_complex_script", str(script), *maps, "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", "-r", str(fps), "-t", "4", str(output)], capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    metadata = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    assert video["avg_frame_rate"] == f"{fps}/1" and int(video["nb_frames"]) == 4 * fps
    frames = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])

    def pixel(time, y):
        offset = int(time * fps) * 160 * 100 * 3 + (y * 160 + 80) * 3
        return tuple(frames[offset:offset + 3])

    def color(time, y, channel):
        rgb = pixel(time, y)
        assert rgb[channel] > 200 and all(component < 30 for i, component in enumerate(rgb) if i != channel), rgb

    color(0.5, 10, 2)  # B remains blue in the upper 30%.
    color(0.5, 70, 1)  # A's later green footage moved to the start.
    color(1.5, 70, 2)  # Removing A shows B full-frame.
    color(2.5, 70, 0)  # Removing B leaves A's independently moved red footage.
    assert max(pixel(3.5, 70)) < 15  # Neither track has a clip here.
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))

    def rms(time):
        window = samples[int(time * 48000):int((time + 0.1) * 48000)]
        return (sum(sample * sample for sample in window) / len(window)) ** 0.5

    assert rms(0.4) > 0.02 and rms(2.4) > 0.02
    assert rms(1.4) < 0.001 and rms(3.4) < 0.001  # Never switch to audible B.
    def frequency(time):
        window = samples[int(time * 48000):int((time + 0.1) * 48000)]
        return sum(left < 0 <= right for left, right in zip(window, window[1:])) / 0.1
    assert frequency(0.4) == pytest.approx(660, abs=15)  # Later audio moved with A video.
    assert frequency(2.4) == pytest.approx(440, abs=15)


@pytest.mark.parametrize("empty", [False, True])
def test_real_ffmpeg_moved_b_and_all_empty_tracks_finish(tmp_path, media, empty):
    ffmpeg, _, paths = media
    value = project("B", fps=60)
    value["manual"]["source_mixer"]["audio_slot"] = "B"
    value["manual"]["source_tracks"] = {"A": [], "B": [] if empty else [clip(0, 1, 2)]}
    value["draft"]["keep_ranges"] = [{"start": 0, "end": 1}]
    graph, maps, _ = build_filter_graph(value, 160, 100)
    script = tmp_path / "b-graph.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "b-output.mp4"
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
                             "-filter_complex_script", str(script), *maps, "-c:v", "libx264", "-preset", "ultrafast",
                             "-c:a", "aac", "-r", "60", "-t", "1", str(output)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    pixel = subprocess.check_output([ffmpeg, "-v", "error", "-ss", "0.5", "-i", str(output), "-an",
                                     "-vf", "scale=1:1", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    if empty:
        assert max(pixel) < 15
    else:
        assert pixel[0] > 200 and pixel[1] > 200 and pixel[2] < 30
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
    window = samples[12000:16800]
    if empty:
        assert max(abs(sample) for sample in window) < 0.001
    else:
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / 0.1
        assert frequency == pytest.approx(1320, abs=15)


def test_global_keep_ranges_still_bound_independent_track_export():
    value = project()
    value["draft"]["keep_ranges"] = [{"start": 0.25, "end": 0.75}, {"start": 2.25, "end": 2.75}]
    plan = _frame_aligned_plan(value)
    assert len(plan) == 2
    assert sum(row["_end_frame"] - row["_start_frame"] for row in plan) == 30


def test_subframe_track_gap_does_not_create_an_unrenderable_fragment():
    value = project("A")
    value["manual"]["source_tracks"] = {"A": [clip(0, 1.001, 0), clip(1.012, 4, 1, "right")], "B": []}
    plan = _frame_aligned_plan(value)
    assert plan == [{"start": 0, "end": 4, "camera": "A", "_start_frame": 0, "_end_frame": 120}]
    graph, _, _ = build_filter_graph(value, 160, 100)
    assert "concat=n=2:v=1:a=0[amasterv]" in graph
