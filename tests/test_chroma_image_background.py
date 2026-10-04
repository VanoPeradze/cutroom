"""Bounded local pixel, audio and input-order tests for READY image backgrounds."""
from __future__ import annotations

import copy
import hashlib
import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cutroom import composition, effects, render
from cutroom.config import DEFAULTS, Settings
from cutroom.jobs import Job, JobContext
from cutroom.media_render import library_input_args
from cutroom.projects import ProjectStore
from test_chroma_render import (
    KEY, _assert_frame_budget, _pixel, _project, _samples, chroma_media,
)


BACKGROUND = "asset_" + "a" * 32
SECOND_BACKGROUND = "asset_" + "b" * 32
OVERLAY = "asset_" + "c" * 32


def _asset(asset_id=BACKGROUND, path="background.png", **patch):
    relative = f"media/assets/{asset_id}/{path}" if isinstance(path, str) else path
    return {"id": asset_id, "kind": "image", "status": "ready", "path": relative,
            "width": 400, "height": 100, "has_audio": False, **patch}


def _with_image(slot="A", camera=None):
    value = _project(camera or slot)
    value["assets"] = {BACKGROUND: _asset()}
    value["manual"]["chroma_key"] = {slot: dict(KEY, background_asset_id=BACKGROUND)}
    return value


@pytest.fixture(scope="module")
def image_media(chroma_media):
    ffmpeg, _, paths = chroma_media
    root = paths[0].parent
    background = root / _asset()["path"]
    overlay = root / _asset(OVERLAY, "overlay.png")["path"]
    for path, visual in (
        (background, "color=yellow:s=400x100,drawbox=x=200:y=0:w=200:h=100:color=blue:t=fill"),
        (overlay, "color=magenta:s=40x40"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            ffmpeg, "-v", "error", "-y", "-threads", "1",
            "-filter_threads", "1", "-filter_complex_threads", "1",
            "-f", "lavfi", "-i", visual, "-frames:v", "1",
            "-c:v", "png", "-threads", "1", str(path),
        ], check=True, capture_output=True, timeout=10)
    return chroma_media, root, background, overlay


def _image_render(value, media, project_dir, output_dir, name):
    ffmpeg, _, paths = media
    before = copy.deepcopy(value)
    graph, maps, has_audio = render.build_filter_graph(value, 320, 180)
    assert value == before and has_audio
    args = library_input_args(value, project_dir)
    args += render.chroma_background_input_args(value, project_dir)
    script, output = output_dir / f"{name}.txt", output_dir / f"{name}.mp4"
    script.write_text(graph, encoding="utf-8")
    result = subprocess.run([
        ffmpeg, "-v", "error", "-y", "-threads", "1",
        "-filter_threads", "1", "-filter_complex_threads", "1",
        "-i", str(paths[0]), "-threads", "1", "-i", str(paths[1]), *args,
        "-filter_complex_script", str(script), *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "16",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
        "-threads", "1", "-r", "30", "-t", "2", str(output),
    ], capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    return output


def _assert_image_pixels(ffmpeg, path, time=0.2):
    # The 4:1 image must cover the 16:9 source, with no letterbox black at the top.
    left, right = _pixel(ffmpeg, path, time, 16, 16), _pixel(ffmpeg, path, time, 304, 16)
    subject = _pixel(ffmpeg, path, time, 160, 90)
    assert left[0] > 200 and left[1] > 200 and left[2] < 30, left
    assert right[2] > 200 and right[0] < 30 and right[1] < 30, right
    assert subject[0] > 200 and subject[1] < 30 and subject[2] < 30, subject


def test_only_ready_safe_image_metadata_can_be_an_active_background():
    value = _with_image()
    before = copy.deepcopy(value)
    assert composition.chroma_background_asset(value, "A") == value["assets"][BACKGROUND]
    assert composition.chroma_background_asset(value, "B") is None
    assert value == before
    invalid_assets = [
        None, _asset(status="preparing"), _asset(kind="video"), _asset(kind="audio"),
        _asset(width=0), _asset(height=float("nan")), _asset(path=None),
        _asset(id=SECOND_BACKGROUND),
    ]
    for invalid in invalid_assets:
        broken = copy.deepcopy(value)
        broken["assets"] = {} if invalid is None else {BACKGROUND: invalid}
        with pytest.raises(ValueError):
            composition.chroma_background_asset(broken, "A")
    disabled = copy.deepcopy(value)
    disabled["manual"]["chroma_key"]["A"]["enabled"] = False
    disabled["assets"] = {}
    assert composition.chroma_background_asset(disabled, "A") is None


def test_background_input_paths_stay_in_the_project_and_use_only_local_files(tmp_path):
    background = tmp_path / _asset()["path"]
    background.parent.mkdir(parents=True)
    background.write_bytes(b"path validation marker; never decoded")
    value = _with_image()
    args = render.chroma_background_input_args(value, tmp_path)
    assert args[args.index("-i") + 1] == str(background.resolve())
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    outside = tmp_path.parent / "outside-background.png"
    for path in ("../outside-background.png", str(outside.resolve()),
                 "https://example.invalid/image.png", _asset(path="missing.png")["path"]):
        bad = copy.deepcopy(value)
        bad["assets"][BACKGROUND]["path"] = path
        with pytest.raises((ValueError, FileNotFoundError)):
            render.chroma_background_input_args(bad, tmp_path)
    value["manual"]["chroma_key"]["A"]["enabled"] = False
    assert render.chroma_background_input_args(value, tmp_path) == []


def test_active_image_graph_requires_a_validated_background_input_label():
    config = dict(KEY, background_asset_id=BACKGROUND)
    with pytest.raises(ValueError):
        effects.build_chroma_key_nodes("[0:v]", "[result]", config, 320, 180, 30, 2)
    with pytest.raises(ValueError):
        effects.build_chroma_key_nodes("[0:v]", "[result]", config, 320, 180, 30, 2,
                                      background_label="[1:v];movie=https://example.invalid")
    nodes = effects.build_chroma_key_nodes("[0:v]", "[result]", config, 320, 180, 30, 2,
                                          background_label="[1:v]")
    assert any("[1:v]" in node for node in nodes)


def test_image_inputs_follow_library_clips_then_ordered_a_b_and_reserve_b_slot(tmp_path):
    for asset_id, name in ((BACKGROUND, "background.png"), (SECOND_BACKGROUND, "second.png"),
                           (OVERLAY, "overlay.png")):
        path = tmp_path / _asset(asset_id, name)["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"input-order marker; never decoded")
    for has_b in (False, True):
        value = _with_image(camera="stacked")
        if not has_b:
            value["sources"]["B"] = None
        value["assets"].update({
            SECOND_BACKGROUND: _asset(SECOND_BACKGROUND, "second.png"),
            OVERLAY: _asset(OVERLAY, "overlay.png", width=40, height=40),
        })
        value["manual"]["media_clips"] = [{"asset_id": OVERLAY, "start": 0.5, "end": 1.5}]
        value["manual"]["chroma_key"]["B"] = dict(KEY, background_asset_id=SECOND_BACKGROUND)
        args = render.chroma_background_input_args(value, tmp_path)
        paths = [Path(args[index + 1]).name for index, arg in enumerate(args) if arg == "-i"]
        assert paths == (["background.png", "second.png"] if has_b else ["background.png"])
        graph, _, _ = render.build_filter_graph(value, 320, 180)
        first_background = (2 if has_b else 1) + 1  # One existing library input stays ahead.
        assert f"[{first_background}:v]" in graph
        if has_b:
            assert f"[{first_background + 1}:v]" in graph


@pytest.mark.parametrize("slot", ["A", "B"])
def test_real_nonuniform_image_background_and_library_overlay_keep_pixels_audio_and_sources(
    image_media, tmp_path, slot,
):
    media, root, background, overlay = image_media
    ffmpeg, _, sources = media
    originals = {path: hashlib.sha256(path.read_bytes()).hexdigest()
                 for path in [*sources, background, overlay]}
    value = _project(slot)
    value["assets"] = {
        BACKGROUND: _asset(),
        OVERLAY: _asset(OVERLAY, "overlay.png", width=40, height=40),
    }
    value["manual"]["media_clips"] = [{
        "asset_id": OVERLAY, "start": 0.5, "end": 1.5,
        "x": 0, "y": 0.75, "w": 0.125, "h": 40 / 180,
    }]
    baseline = _image_render(value, media, root, tmp_path, "before")
    value["manual"]["chroma_key"] = {slot: dict(KEY, background_asset_id=BACKGROUND)}
    output = _image_render(value, media, root, tmp_path, "image")
    for at in (0.2, 1.8):
        _assert_image_pixels(ffmpeg, output, at)
    overlay_pixel = _pixel(ffmpeg, output, 0.8, 16, 150)
    assert overlay_pixel[0] > 200 and overlay_pixel[2] > 200 and overlay_pixel[1] < 30, overlay_pixel
    _assert_frame_budget(media, output)
    before_audio, after_audio = _samples(ffmpeg, baseline), _samples(ffmpeg, output)
    assert len(before_audio) == len(after_audio)
    assert max(abs(left - right) for left, right in zip(before_audio, after_audio)) < 1e-6
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals} == originals


def test_real_render_project_keeps_unused_existing_b_before_background_image(
    image_media, tmp_path, monkeypatch,
):
    media, _, background, _ = image_media
    ffmpeg, ffprobe, sources = media
    raw = copy.deepcopy(DEFAULTS)
    raw["ffmpeg_threads"] = 1
    raw["ai"]["enabled"] = False
    raw["render"].update(prefer_hardware=False, min_free_mb=0)
    data = tmp_path / "data"
    projects, exports, cache = (data / name for name in ("projects", "exports", "cache"))
    for folder in (projects, exports, cache):
        folder.mkdir(parents=True)
    settings = Settings(raw, tmp_path, data, projects, exports, cache, ffmpeg, ffprobe)
    store = ProjectStore(settings)
    value = store.create("image background input order")
    value.update(_with_image())
    value["settings"].update(aspect="source", resolution="720", quality="fast",
                              captions=False, burn_captions=False)
    directory = store.project_dir(value["id"])
    for slot, source in zip(("A", "B"), sources):
        relative = f"media/{slot}.mov"
        shutil.copyfile(source, directory / relative)
        value["sources"][slot]["relative_path"] = relative
    image_target = directory / _asset()["path"]
    image_target.parent.mkdir(parents=True)
    shutil.copyfile(background, image_target)
    store.save(value)
    captured = []
    original_run = render._run_ffmpeg_process

    def one_thread_run(context, command, duration):
        captured.append(list(command))
        bounded = [command[0], "-filter_threads", "1", "-filter_complex_threads", "1"]
        for argument in command[1:]:
            if argument == "-i":
                bounded += ["-threads", "1"]
            bounded.append(argument)
        return original_run(context, bounded, duration)

    monkeypatch.setattr(render, "_run_ffmpeg_process", one_thread_run)
    context = JobContext(Job("chroma-image-test", "render", value["id"]), threading.Lock())
    result = render.render_project(context, value["id"], store, settings)
    inputs = [Path(captured[0][index + 1]).name
              for index, argument in enumerate(captured[0]) if argument == "-i"]
    assert inputs == ["A.mov", "B.mov", "background.png"]
    output = exports / result["export"]["relative_path"]
    _assert_image_pixels(ffmpeg, output)
    _assert_frame_budget(media, output)
    assert store.load(value["id"])["exports"][0]["id"] == result["export"]["id"]


def test_real_shared_image_nodes_generate_the_same_known_png_preview_pixels(image_media, tmp_path):
    media, _, background, _ = image_media
    ffmpeg, _, sources = media
    nodes = effects.build_chroma_key_nodes(
        "[0:v]", "[preview]", dict(KEY, background_asset_id=BACKGROUND),
        320, 180, 30, 2, prefix="preview", background_label="[1:v]",
    )
    script, output = tmp_path / "preview.txt", tmp_path / "preview.png"
    script.write_text(";\n".join(nodes), encoding="utf-8")
    result = subprocess.run([
        ffmpeg, "-v", "error", "-y", "-threads", "1", "-ss", "0.4",
        "-filter_threads", "1", "-filter_complex_threads", "1",
        "-i", str(sources[0]), "-loop", "1", "-framerate", "30",
        "-threads", "1", "-i", str(background),
        "-filter_complex_script", str(script), "-map", "[preview]", "-an",
        "-frames:v", "1", "-c:v", "png", "-threads", "1", str(output),
    ], capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
    _assert_image_pixels(ffmpeg, output, time=0)
