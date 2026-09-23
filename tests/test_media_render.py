from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import threading
from array import array
from pathlib import Path

import pytest

from cutroom.jobs import Job, JobContext
from cutroom.config import DEFAULTS, Settings
from cutroom.media_render import library_input_args
from cutroom.projects import ProjectStore
from cutroom.render import _dimensions, _render_input_fingerprint, _run_ffmpeg_process, build_filter_graph, render_project
from cutroom.sequence import prepare_sequence_edit
from cutroom.source_tracks import source_track_clips


def project():
    return {
        "sources": {"A": {"duration": 3, "width": 160, "height": 90, "has_audio": True}},
        "settings": {"fps": 30, "editorial_effects": False},
        "manual": {}, "assets": {},
        "draft": {"keep_ranges": [{"start": 0, "end": 3}], "camera_plan": [{"start": 0, "end": 3, "camera": "A"}]},
    }


@pytest.mark.parametrize("resolution,short,long", [("1440", 1440, 2560), ("2160", 2160, 3840)])
@pytest.mark.parametrize("aspect", ["9:16", "16:9", "1:1", "4:5", "source"])
def test_high_resolution_dimensions(resolution, short, long, aspect):
    value = project()
    value["sources"]["A"].update(width=7680, height=4320)
    value["settings"].update(aspect=aspect, resolution=resolution)
    expected = {"9:16": (short, long), "16:9": (long, short), "1:1": (short, short), "4:5": (short, short * 5 // 4), "source": (long, short)}
    assert _dimensions(value) == expected[aspect]


def test_source_resolution_does_not_upscale_or_accept_bad_resolution():
    value = project()
    value["settings"].update(aspect="source", resolution="2160")
    assert _dimensions(value) == (160, 90)
    value["settings"]["resolution"] = "9999"
    with pytest.raises(ValueError, match="resolution"):
        _dimensions(value)


def test_speed_preserves_speech_clock_across_slice_trim_move_and_materialization():
    value = project()
    value["manual"] = prepare_sequence_edit(value, {"action": "sequence_speed", "slot": "A", "clip_id": "A:sequence:0:0", "speed": 2})
    before = copy.deepcopy(value)
    value["manual"] = prepare_sequence_edit(value, {"action": "sequence_split", "slot": "A", "time": 1})
    left, right = source_track_clips(value, "A")
    assert left["video_speed"] == right["video_speed"] == 2
    assert right["source_start"] == 1 and right["video_source_start"] == 2
    value["manual"] = prepare_sequence_edit(value, {"action": "sequence_trim", "slot": "A", "clip_id": right["id"], "start": 1.5, "end": 3, "source_start": 1.5})
    trimmed = source_track_clips(value, "A")[1]
    assert trimmed["source_start"] == 1.5 and trimmed["video_source_start"] == 3
    moved = prepare_sequence_edit(value, {"action": "sequence_place", "slot": "A", "clip_id": trimmed["id"], "start": 4})
    assert moved["source_tracks"]["A"][1]["video_source_start"] == 3
    cropped = prepare_sequence_edit(before, {"action": "sequence_crop", "slot": "A", "start": .5, "end": 1.5, "x": .5, "y": .5, "zoom": 1})
    assert [row["video_source_start"] for row in cropped["source_tracks"]["A"]] == [0, 1, 3]


@pytest.mark.parametrize("speed", [0, .1, 4.01, "nan", True])
def test_picture_speed_rejects_invalid_values(speed):
    with pytest.raises(ValueError):
        prepare_sequence_edit(project(), {"action": "sequence_speed", "slot": "A", "clip_id": "A:sequence:0:0", "speed": speed})


def test_library_and_mixer_are_in_render_fingerprint():
    value = project()
    original = _render_input_fingerprint(value)
    value["manual"]["audio_mixer"] = {"source_db": -6}
    assert _render_input_fingerprint(value) != original
    original = _render_input_fingerprint(value)
    value["assets"] = {"image": {"path": "media/image.png", "kind": "image"}}
    assert _render_input_fingerprint(value) != original


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    root = tmp_path_factory.mktemp("library-render")
    source = root / "source.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=red:s=160x90:r=30:d=1[r];color=lime:s=160x90:r=30:d=1[g];color=blue:s=160x90:r=30:d=1[b];[r][g][b]concat=n=3:v=1:a=0",
                    "-f", "lavfi", "-i", "aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-t", "3", str(source)], check=True, capture_output=True, timeout=20)
    music = root / "music.wav"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "aevalsrc='0.15*sin(2*PI*880*t)':s=48000:d=3", str(music)], check=True, capture_output=True, timeout=10)
    image = root / "image.png"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "color=yellow:s=80x80", "-frames:v", "1", str(image)], check=True, capture_output=True, timeout=10)
    return root, ffmpeg, ffprobe, source, music, image


def render(value, media, tmp_path, dimensions=(160, 90)):
    root, ffmpeg, _, source, _, _ = media
    graph, maps, _ = build_filter_graph(value, *dimensions)
    graph_path = tmp_path / "graph.txt"
    graph_path.write_text(graph, encoding="utf-8")
    output = tmp_path / "output.mp4"
    context = JobContext(Job("library-test", "render", "test"), threading.Lock())
    code, error = _run_ffmpeg_process(context, [ffmpeg, "-v", "error", "-y", "-i", str(source), *library_input_args(value, root),
                                               "-filter_complex_script", str(graph_path), *maps, "-c:v", "libx264", "-preset", "ultrafast",
                                               "-c:a", "aac", "-threads", "2", "-t", "3", "-progress", "pipe:1", str(output)], 3)
    assert code == 0, error
    return output


def pixel(ffmpeg, output, time, x=80, y=45):
    data = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(time), "-i", str(output), "-an", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    return tuple(data[(y * 160 + x) * 3:(y * 160 + x) * 3 + 3])


def samples(ffmpeg, output):
    return array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))


def tone_level(data, at, frequency):
    start, size = round(at * 48000), 4800
    window = data[start:start + size]
    return 2 * abs(sum(sample * complex(math.cos(2 * math.pi * frequency * index / 48000), math.sin(2 * math.pi * frequency * index / 48000))
                       for index, sample in enumerate(window))) / size


def test_real_picture_speed_changes_frames_and_keeps_original_speech(media, tmp_path):
    value = project()
    value["manual"] = prepare_sequence_edit(value, {"action": "sequence_speed", "slot": "A", "clip_id": "A:sequence:0:0", "speed": 2})
    output = render(value, media, tmp_path)
    _, ffmpeg, _, _, _, _ = media
    assert pixel(ffmpeg, output, .75)[1] > 200  # Faster picture already reached green.
    assert pixel(ffmpeg, output, 2.75)[2] > 200  # EOF holds the final picture.
    data = samples(ffmpeg, output)
    assert tone_level(data, .7, 440) < .002
    assert tone_level(data, 1.3, 440) > .2  # Speech remains in the original 1..2s window.
    assert tone_level(data, 2.3, 440) < .002


@pytest.mark.parametrize("motion", ["none", "zoom_in", "pan"])
@pytest.mark.parametrize("fit", ["cover", "contain"])
def test_real_image_overlay_respects_position_timing_and_motion(media, tmp_path, motion, fit):
    value = project()
    value["assets"] = {"picture": {"kind": "image", "path": "image.png"}}
    value["manual"]["media_clips"] = [{"asset_id": "picture", "start": 1, "end": 2, "x": .5, "y": 0, "w": .5, "h": .5, "motion": motion, "fit": fit}]
    output = render(value, media, tmp_path)
    _, ffmpeg, _, _, _, _ = media
    during = pixel(ffmpeg, output, 1.5, 120, 20)
    assert during[0] > 200 and during[1] > 200 and during[2] < 30
    assert pixel(ffmpeg, output, .5, 120, 20)[0] > 200
    assert pixel(ffmpeg, output, 2.5, 120, 20)[2] > 200
    assert pixel(ffmpeg, output, 1.5, 20, 20)[1] > 200


def test_real_music_ducking_responds_to_source_speech(media, tmp_path):
    value = project()
    value["assets"] = {"music": {"kind": "audio", "path": "music.wav", "has_audio": True}}
    value["manual"].update(media_clips=[{"asset_id": "music", "start": 0, "end": 3, "role": "music"}], audio_mixer={"ducking": True})
    output = render(value, media, tmp_path)
    data = samples(media[1], output)
    assert tone_level(data, .5, 880) > .08
    assert tone_level(data, 1.5, 880) < tone_level(data, .5, 880) * .6
    assert tone_level(data, 1.5, 440) > .2


def test_real_fades_and_mutes_preserve_library_audio_with_silent_source(media, tmp_path):
    value = project()
    value["assets"] = {"music": {"kind": "audio", "path": "music.wav", "has_audio": True}}
    value["manual"].update(media_clips=[{"asset_id": "music", "start": .5, "end": 2.5, "role": "music", "fade_in": .5, "fade_out": .5}],
                           audio_mixer={"source_muted": True, "music_db": -6, "master_db": -6})
    output = render(value, media, tmp_path)
    data = samples(media[1], output)
    assert tone_level(data, .1, 880) < .002
    assert .02 < tone_level(data, 1.3, 880) < .05
    assert tone_level(data, .5, 880) < tone_level(data, 1.3, 880) * .4
    assert tone_level(data, 1.3, 440) < .002
    assert tone_level(data, 2.35, 880) < tone_level(data, 1.3, 880) * .4


def test_real_added_video_speed_and_tail_split_keep_attached_speech_clock(media, tmp_path):
    value = project()
    value["assets"] = {"video": {"kind": "video", "path": "source.mp4", "duration": 3, "has_audio": True}}
    value["manual"].update(media_clips=[
        {"asset_id": "video", "start": 0, "end": 2, "speed": 2, "audio_enabled": True, "role": "voice"},
        {"asset_id": "video", "start": 2, "end": 3, "source_start": 2, "video_source_start": 4, "speed": 2, "audio_enabled": True, "role": "voice"},
    ], audio_mixer={"source_muted": True})
    output = render(value, media, tmp_path)
    assert pixel(media[1], output, .75)[1] > 200
    assert pixel(media[1], output, 2.75)[2] > 200
    data = samples(media[1], output)
    assert tone_level(data, .7, 440) < .002
    assert tone_level(data, 1.3, 440) > .2
    assert tone_level(data, 2.3, 440) < .002


@pytest.mark.parametrize("motion,boundary,sample_x", [("pan", 80, 80), ("zoom_in", 50, 48)])
def test_real_motion_moves_picture_in_preview_direction(media, tmp_path, motion, boundary, sample_x):
    name = f"pattern-{motion}.png"
    subprocess.run([media[1], "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=red:s=160x90,drawbox=x={boundary}:y=0:w={160 - boundary}:h=90:color=lime:t=fill",
                    "-frames:v", "1", str(media[0] / name)], check=True, capture_output=True, timeout=10)
    value = project()
    value["assets"] = {"picture": {"kind": "image", "path": name}}
    value["manual"]["media_clips"] = [{"asset_id": "picture", "start": 0, "end": 3, "motion": motion}]
    output = render(value, media, tmp_path)
    assert pixel(media[1], output, .1, sample_x)[0] > 180
    assert pixel(media[1], output, 2.8, sample_x)[1] > 180


def test_audio_fades_do_not_fade_the_picture():
    value = project()
    value["assets"] = {"video": {"kind": "video", "duration": 3, "has_audio": True}}
    value["manual"]["media_clips"] = [{"asset_id": "video", "start": 0, "end": 3, "audio_enabled": True, "fade_in": .5, "fade_out": .5}]
    graph, _, _ = build_filter_graph(value, 160, 90)
    assert "afade=t=in" in graph and "afade=t=out" in graph
    assert ",fade=" not in graph


def test_render_project_commits_library_export_with_unused_b_and_normalization(media, tmp_path):
    raw = copy.deepcopy(DEFAULTS)
    raw["render"].update(prefer_hardware=False, min_free_mb=0)
    data = tmp_path / "data"
    projects, exports, cache = (data / name for name in ("projects", "exports", "cache"))
    for folder in (projects, exports, cache):
        folder.mkdir(parents=True)
    settings = Settings(raw, tmp_path, data, projects, exports, cache, media[1], media[2])
    store = ProjectStore(settings)
    stored = store.create("library smoke")
    stored.update({key: value for key, value in project().items()})
    stored["sources"]["A"]["relative_path"] = "media/source.mp4"
    stored["sources"]["B"] = copy.deepcopy(stored["sources"]["A"])
    stored["settings"].update(aspect="source", resolution="1440", quality="fast", burn_captions=False)
    directory = store.project_dir(stored["id"])
    shutil.copyfile(media[3], directory / "media" / "source.mp4")
    (directory / "media" / "assets").mkdir()
    shutil.copyfile(media[5], directory / "media" / "assets" / "image.png")
    shutil.copyfile(media[4], directory / "media" / "assets" / "music.wav")
    picture_id, music_id = "asset_" + "1" * 32, "asset_" + "2" * 32
    stored["assets"] = {
        picture_id: {"id": picture_id, "kind": "image", "path": "media/assets/image.png"},
        music_id: {"id": music_id, "kind": "audio", "path": "media/assets/music.wav"},
    }
    stored["manual"].update(media_clips=[
        {"asset_id": picture_id, "start": 1, "end": 2, "w": .5, "h": .5},
        {"asset_id": music_id, "start": 0, "end": 3, "role": "music"},
    ], audio_mixer={"ducking": True, "master_db": -3})
    stored["draft"]["audio_policy"] = {"normalize": True}
    store.save(stored)
    context = JobContext(Job("library-commit-test", "render", stored["id"]), threading.Lock())
    result = render_project(context, stored["id"], store, settings)
    record = result["export"]
    assert (record["width"], record["height"]) == (160, 90)
    assert record["duration"] == pytest.approx(3, abs=1 / 30)
    assert store.load(stored["id"])["exports"][0]["id"] == record["id"]
    assert len(list(exports.glob("*.mp4"))) == 1
    assert not list((directory / "cache").glob("filter-*"))


def test_library_paths_cannot_escape_project(media):
    value = project()
    value["assets"] = {"music": {"kind": "audio", "path": "../other/music.wav"}}
    value["manual"]["media_clips"] = [{"asset_id": "music"}]
    with pytest.raises(ValueError, match="belong"):
        library_input_args(value, media[0])


@pytest.mark.parametrize("resolution", ["1440", "2160"])
@pytest.mark.parametrize("aspect", ["9:16", "16:9", "1:1", "4:5", "source"])
def test_real_ffmpeg_high_resolution_all_aspects(media, tmp_path, resolution, aspect):
    value = project()
    value["sources"]["A"].update(width=7680, height=4320, has_audio=False)
    value["settings"].update(aspect=aspect, resolution=resolution)
    value["draft"].update(keep_ranges=[{"start": 0, "end": 2 / 30}], camera_plan=[{"start": 0, "end": 2 / 30, "camera": "A"}])
    dims = _dimensions(value)
    graph, maps, _ = build_filter_graph(value, *dims)
    script = tmp_path / "high-resolution.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "high-resolution.mp4"
    subprocess.run([media[1], "-v", "error", "-y", "-i", str(media[3]), "-filter_complex_script", str(script), *maps,
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-t", str(2 / 30), str(output)], check=True, capture_output=True, timeout=30)
    streams = json.loads(subprocess.check_output([media[2], "-v", "error", "-show_streams", "-of", "json", str(output)]))["streams"]
    assert (streams[0]["width"], streams[0]["height"]) == dims
    assert int(streams[0]["nb_frames"]) == 2
