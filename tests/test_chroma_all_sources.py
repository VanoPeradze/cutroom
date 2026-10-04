"""Real per-video chroma targets, including independent project-library sources."""
from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom.composition import CHROMA_KEY_DEFAULTS, source_chroma_key
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.render import _render_input_fingerprint, build_filter_graph
from test_chroma_api import api, apply, frame, green_png
from test_chroma_editing import project, change

VIDEO = "asset_" + "1" * 32
OTHER = "asset_" + "2" * 32
IMAGE = "asset_" + "3" * 32


def asset(target=VIDEO, **patch):
    return {"id": target, "kind": "video", "status": "ready", "name": "same.mov",
            "path": f"media/assets/{target}/original.mov", "width": 320, "height": 180,
            "duration": 2, "has_audio": True, **patch}


def with_videos():
    value = project()
    value["settings"] = {"fps": 30, "editorial_effects": False}
    value["draft"]["camera_plan"] = [{"start": 0, "end": 2, "camera": "A"}]
    value["assets"] = {VIDEO: asset(), OTHER: asset(OTHER)}
    value["manual"]["media_clips"] = [{"id": "lib1", "asset_id": VIDEO, "start": 0, "end": 2}]
    return value


def test_three_plus_targets_same_filenames_save_undo_reset_and_no_cross_target_copy():
    value = with_videos()
    original = copy.deepcopy(value)
    apply_manual_edit(value, change(slot=VIDEO, background_color="#FFFF00"))
    assert source_chroma_key(value, VIDEO)["background_color"] == "#FFFF00"
    assert not source_chroma_key(value, OTHER)["enabled"]
    assert not source_chroma_key(value, "A")["enabled"]
    assert not source_chroma_key(value, "B")["enabled"]
    saved = copy.deepcopy(value)
    apply_manual_edit(value, change(slot=OTHER, background_color="#00FFFF"))
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["chroma_key"] == saved["manual"]["chroma_key"]
    apply_manual_edit(value, {"action": "redo"})
    assert source_chroma_key(value, OTHER)["background_color"] == "#00FFFF"
    apply_manual_edit(value, {"action": "reset_chroma_key", "slot": VIDEO})
    assert source_chroma_key(value, VIDEO) == CHROMA_KEY_DEFAULTS
    assert source_chroma_key(value, OTHER)["enabled"]
    assert value["sources"] == original["sources"]
    assert value["assets"] == original["assets"]
    assert value["draft"]["keep_ranges"] == original["draft"]["keep_ranges"]


def test_source_replacement_preserves_independent_library_video_key_settings():
    value = with_videos()
    value["manual"]["chroma_key"] = {slot: {**CHROMA_KEY_DEFAULTS, "enabled": True} for slot in ("A", "B", VIDEO, OTHER)}
    before = copy.deepcopy(value["manual"]["chroma_key"])
    server._reset_manual_after_source_change(value, "A", replacing=True)
    assert value["manual"]["chroma_key"] == {target: config for target, config in before.items() if target != "A"}


@pytest.mark.parametrize("patch", [{"status": "preparing"}, {"status": "failed"}, {"kind": "audio"},
    {"kind": "image"}, {"duration": 0}, {"width": 0}, {"id": OTHER}, {"path": "../other.mov"}])
def test_invalid_library_target_rejected_without_mutation(patch):
    value = with_videos()
    value["assets"][VIDEO].update(patch)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, change(slot=VIDEO))
    assert value == before


def test_deleted_target_fails_instead_of_reusing_another_same_filename():
    value = with_videos()
    apply_manual_edit(value, change(slot=VIDEO))
    del value["assets"][VIDEO]
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, change(slot=VIDEO))
    assert value == before
    with pytest.raises(ValueError, match="missing"):
        build_filter_graph(value, 320, 180)


def test_library_target_is_processed_before_clip_trim_and_changes_render_fingerprint():
    value = with_videos()
    before = _render_input_fingerprint(value)
    apply_manual_edit(value, change(slot=VIDEO))
    assert _render_input_fingerprint(value) != before
    graph, _, _ = build_filter_graph(value, 320, 180)
    assert "[2:v]setpts=PTS-STARTPTS,scale=320:180" in graph
    assert "chromakey=" in graph
    assert graph.index("chromakey=") < graph.index("trim=start=0.000000000")


def test_library_preview_uses_selected_asset_local_path_and_saved_settings(api, monkeypatch):
    _, client, store, pid, _ = api
    root = store.project_dir(pid)
    path = root / asset()["path"]
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic video fixture")
    store.update(pid, lambda value: value["assets"].update({VIDEO: asset()}))
    assert apply(client, store, pid, slot=VIDEO, background_color="#00FFFF").status_code == 200
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert str(path) == command[command.index("-i") + 1]
        assert "0x00FFFF" in command[command.index("-filter_complex") + 1]
        Path(command[-1]).write_bytes(green_png(320, 180))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(server.subprocess, "run", run)
    before = copy.deepcopy(store.load(pid))
    assert frame(client, store, pid, slot=VIDEO).status_code == 200
    assert store.load(pid) == before
    path.unlink()
    assert frame(client, store, pid, slot=VIDEO).status_code == 409
    assert len(calls) == 1  # Missing media must not return a previously cached frame.


# Shared synthetic media fixtures; no user recordings or external providers.
from test_chroma_render import chroma_media, _pixel, _samples, _assert_frame_budget
from test_chroma_image_background import image_media, _image_render, _asset, BACKGROUND
import hashlib
import shutil


@pytest.mark.parametrize("background", ["solid", "image"])
def test_real_imported_video_chroma_matches_preview_export_and_preserves_audio(
    image_media, api, tmp_path, background,
):
    media, media_root, image_path, _ = image_media
    ffmpeg, _, sources = media
    imported = media_root / asset()["path"]
    imported.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sources[1], imported)
    originals = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in [*sources, imported, image_path]}
    value = with_videos()
    value["assets"][BACKGROUND] = _asset()
    # The same media is used twice at independent native in-points. An image
    # background must feed both preprocessing branches rather than be consumed.
    value["manual"]["media_clips"] = [
        {"id":"first", "asset_id":VIDEO, "start":0, "end":1, "source_start":.25, "audio_enabled":True, "volume_db":-12},
        {"id":"second", "asset_id":VIDEO, "start":1, "end":2, "source_start":.75, "audio_enabled":True, "volume_db":-12},
    ]
    baseline = _image_render(value, media, media_root, tmp_path, "asset-before-"+background)
    params = dict(background_color="#0000FF", background_asset_id=BACKGROUND if background == "image" else None)
    apply_manual_edit(value, change(slot=VIDEO, **params))
    output = _image_render(value, media, media_root, tmp_path, "asset-after-"+background)
    _assert_frame_budget(media, output)
    before_audio, after_audio = _samples(ffmpeg, baseline), _samples(ffmpeg, output)
    assert len(before_audio) == len(after_audio)
    assert max(abs(left-right) for left,right in zip(before_audio,after_audio)) < 1e-6
    assert not source_chroma_key(value, "A")["enabled"]
    assert not source_chroma_key(value, OTHER)["enabled"]
    _, client, store, pid, _ = api
    project_root = store.project_dir(pid)
    imported_api = project_root / asset()["path"]
    imported_api.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(imported, imported_api)
    background_api = project_root / _asset()["path"]
    background_api.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image_path, background_api)
    store.update(pid, lambda current: current["assets"].update({VIDEO:asset(),BACKGROUND:_asset()}))
    assert apply(client, store, pid, slot=VIDEO, **params).status_code == 200
    response = frame(client, store, pid, slot=VIDEO, time=.45)
    assert response.status_code == 200, response.get_json()
    png = tmp_path / ("asset-preview-"+background+".png")
    png.write_bytes(response.data)
    for x,y in [(16,16),(304,16),(160,90)]:
        preview_pixel = _pixel(ffmpeg, png, 0, x,y)
        for at in (.2,1.2):
            output_pixel = _pixel(ffmpeg, output, at,x,y)
            assert max(abs(a-b) for a,b in zip(preview_pixel,output_pixel)) < 18
    assert _pixel(ffmpeg, output,.2)[1] < 35 if background == "solid" else _pixel(ffmpeg,output,.2)[0] > 200
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == originals


def test_imported_key_reopen_missing_file_edit_atomicity_and_safe_disable(api):
    _, client, store, pid, settings = api
    media = store.project_dir(pid) / asset()["path"]
    media.parent.mkdir(parents=True)
    media.write_bytes(b"local source marker")
    store.update(pid, lambda value: value["assets"].update({VIDEO:asset(),OTHER:asset(OTHER)}))
    assert apply(client, store, pid, slot=VIDEO, tolerance=.31).status_code == 200
    from cutroom.projects import ProjectStore
    reopened = ProjectStore(settings)
    assert reopened.load(pid)["manual"]["chroma_key"][VIDEO]["tolerance"] == .31
    assert not source_chroma_key(reopened.load(pid), OTHER)["enabled"]
    media.unlink()
    before = copy.deepcopy(store.load(pid))
    assert apply(client, store, pid, slot=VIDEO, color="#FFFFFF").status_code == 409
    assert store.load(pid) == before
    assert apply(client, store, pid, slot=VIDEO, enabled=False).status_code == 200
    assert source_chroma_key(store.load(pid), VIDEO)["enabled"] is False
