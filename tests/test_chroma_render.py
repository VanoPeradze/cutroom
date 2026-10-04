"""Real, small local FFmpeg coverage for opaque A/B chroma-key exports."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
from array import array

import pytest

from cutroom import composition, effects, render


KEY = {
    "enabled": True,
    "color": "#00FF00",
    "tolerance": 0.12,
    "edge_softness": 0.08,
    "background_color": "#0000FF",
}


def _project(camera="A"):
    return {
        "sources": {
            slot: {"duration": 2, "video_duration": 2, "width": 320,
                   "height": 180, "has_audio": True}
            for slot in ("A", "B")
        },
        "settings": {"fps": 30, "editorial_effects": False},
        "manual": {"source_mixer": {"audio_slot": "A"}},
        "draft": {
            "keep_ranges": [{"start": 0, "end": 2}],
            "camera_plan": [{"start": 0, "end": 2, "camera": camera}],
        },
    }


@pytest.fixture(scope="module")
def chroma_media(tmp_path_factory):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("The existing local FFmpeg runtime is required")
    root = tmp_path_factory.mktemp("chroma")
    paths = []
    for slot, frequency in (("A", 440), ("B", 880)):
        path = root / f"{slot}.mov"
        subprocess.run([
            ffmpeg, "-v", "error", "-y", "-threads", "1",
            "-filter_threads", "1", "-filter_complex_threads", "1",
            "-f", "lavfi", "-i",
            "color=c=0x00FF00:s=320x180:r=30:d=2,"
            "drawbox=x=96:y=50:w=128:h=80:color=red:t=fill",
            "-f", "lavfi", "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration=2",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "pcm_s16le", "-threads", "1", "-t", "2", str(path),
        ], check=True, capture_output=True, timeout=20)
        paths.append(path)
    return ffmpeg, ffprobe, paths


def _render(value, media, root, name):
    ffmpeg, _, paths = media
    before = copy.deepcopy(value)
    graph, maps, has_audio = render.build_filter_graph(value, 320, 180)
    assert value == before
    assert has_audio
    script, output = root / f"{name}.txt", root / f"{name}.mp4"
    script.write_text(graph, encoding="utf-8")
    result = subprocess.run([
        ffmpeg, "-v", "error", "-y", "-threads", "1",
        "-filter_threads", "1", "-filter_complex_threads", "1",
        "-i", str(paths[0]), "-i", str(paths[1]),
        "-filter_complex_script", str(script), *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-threads", "1", "-r", "30", "-t", "2", str(output),
    ], capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return output


def _pixel(ffmpeg, path, time, x=16, y=16):
    data = subprocess.check_output([
        ffmpeg, "-v", "error", "-threads", "1", "-ss", str(time),
        "-i", str(path), "-an", "-frames:v", "1", "-pix_fmt", "rgb24",
        "-threads", "1", "-f", "rawvideo", "pipe:1",
    ], timeout=10)
    offset = (y * 320 + x) * 3
    return tuple(data[offset:offset + 3])


def _samples(ffmpeg, path):
    return array("f", subprocess.check_output([
        ffmpeg, "-v", "error", "-threads", "1", "-i", str(path),
        "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1",
    ], timeout=10))


def _assert_frame_budget(media, path):
    _, ffprobe, _ = media
    metadata = json.loads(subprocess.check_output([
        ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path),
    ], timeout=10))
    video = next(row for row in metadata["streams"] if row["codec_type"] == "video")
    audio = next(row for row in metadata["streams"] if row["codec_type"] == "audio")
    assert video["avg_frame_rate"] == "30/1"
    assert int(video["nb_frames"]) == 60
    assert float(video["duration"]) == pytest.approx(2, abs=1 / 48000)
    assert video["pix_fmt"] == "yuv420p"  # MP4 contains the flattened result.
    assert float(audio["duration"]) == pytest.approx(2, abs=1 / 48000)


def test_disabled_chroma_preserves_the_exact_existing_graph():
    value = _project("stacked")
    before = render.build_filter_graph(value, 320, 180)
    value["manual"]["chroma_key"] = {
        slot: composition.normalize_chroma_key(None) for slot in ("A", "B")
    }
    assert not value["manual"]["chroma_key"]["A"]["enabled"]
    assert effects.chroma_key_filter(value["manual"]["chroma_key"]["A"]) in (None, "", "null")
    assert render.build_filter_graph(value, 320, 180) == before


@pytest.mark.parametrize("slot", ["A", "B"])
def test_real_chroma_replaces_only_selected_video_and_preserves_audio_and_original(
    chroma_media, tmp_path, slot,
):
    ffmpeg, _, paths = chroma_media
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    value = _project(slot)
    baseline = _render(value, chroma_media, tmp_path, "before")
    value["manual"]["chroma_key"] = {slot: dict(KEY)}
    assert composition.source_chroma_key(value, slot)["enabled"] is True
    assert composition.source_chroma_key(value, "B" if slot == "A" else "A")["enabled"] is False
    keyed = _render(value, chroma_media, tmp_path, "keyed")
    for at in (0.2, 1.8):
        original = _pixel(ffmpeg, baseline, at)
        background = _pixel(ffmpeg, keyed, at)
        foreground = _pixel(ffmpeg, keyed, at, 160, 90)
        assert original[1] > 200 and original[0] < 30 and original[2] < 30, original
        assert background[2] > 200 and background[0] < 30 and background[1] < 30, background
        assert foreground[0] > 200 and foreground[1] < 30 and foreground[2] < 30, foreground
    _assert_frame_budget(chroma_media, keyed)
    before_audio, after_audio = _samples(ffmpeg, baseline), _samples(ffmpeg, keyed)
    assert len(before_audio) == len(after_audio)
    assert max(abs(left - right) for left, right in zip(before_audio, after_audio)) < 1e-6
    window = after_audio[24000:28800]
    crossings = sum(left < 0 <= right for left, right in zip(window, window[1:]))
    assert crossings / 0.1 == pytest.approx(440, abs=15)  # A remains selected even when picture B is keyed.
    # Enabling one source must not key the other source after final composition.
    other = _project("B" if slot == "A" else "A")
    other["manual"]["chroma_key"] = {slot: dict(KEY)}
    untouched = _render(other, chroma_media, tmp_path, "other-source")
    untouched_background = _pixel(ffmpeg, untouched, 0.4)
    assert untouched_background[1] > 200 and untouched_background[2] < 30, untouched_background
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == hashes


@pytest.mark.parametrize("key_color", ["#00FF00", "#000000"])
def test_real_chroma_keeps_independent_removed_footage_black(chroma_media, tmp_path, key_color):
    ffmpeg, _, _ = chroma_media
    value = _project()
    value["manual"]["source_tracks"] = {
        "A": [{"id": "A-one", "start": 0, "end": 1, "source_start": 0}],
        "B": [],
    }
    value["manual"]["chroma_key"] = {"A": dict(KEY, color=key_color), "B": dict(KEY)}
    output = _render(value, chroma_media, tmp_path, "gap")
    first = _pixel(ffmpeg, output, 0.4)
    assert first[2 if key_color == "#00FF00" else 1] > 200, first
    assert max(_pixel(ffmpeg, output, 1.6)) < 15  # A/B absence remains an actual gap.
    _assert_frame_budget(chroma_media, output)
    samples = _samples(ffmpeg, output)
    silent = samples[round(1.6 * 48000):round(1.7 * 48000)]
    assert max(abs(sample) for sample in silent) < 0.001
