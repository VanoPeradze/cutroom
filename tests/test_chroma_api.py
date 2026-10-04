"""Chroma changes and frame previews obey project revision/source boundaries."""
import copy
import shutil
import struct
import subprocess
import threading
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom.composition import CHROMA_KEY_DEFAULTS
from cutroom.config import load_settings


def green_png(width=640, height=360, row=None):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress((b"\0" + (row or b"\0\xff\0" * width)) * height)) + chunk(b"IEND", b""))


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.ai["enabled"] = False
    app = server.create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    value = store.create("Synthetic Chroma API")
    root = store.project_dir(value["id"])
    for slot in ("A", "B"):
        source = root / "media" / f"{slot}.mov"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(b"synthetic test source")
        value["sources"][slot] = {"name": source.name, "relative_path": source.relative_to(root).as_posix(),
            "duration": 2, "width": 1280, "height": 720, "has_audio": True, "generation": f"source-{slot}"}
    value["draft"] = {"keep_ranges": [{"start": 0, "end": 2}]}
    store.save(value)
    monkeypatch.setattr(server, "chroma_key_capability", lambda *_: {"available": True, "mp4_alpha": False, "supports": ["solid"]})
    yield app, app.test_client(), store, value["id"], settings
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def apply(client, store, pid, **extra):
    return client.post(f"/api/projects/{pid}/manual/edit", json={"action": "set_chroma_key", "slot": "A",
        **CHROMA_KEY_DEFAULTS, "enabled": True, "expected_revision": store.load(pid)["revision"], **extra})


def frame(client, store, pid, slot="A", **extra):
    return client.get(f"/api/projects/{pid}/chroma-preview/{slot}", query_string={"time": .5, "revision": store.load(pid)["revision"], **extra})


def test_capability_and_atomic_apply_history_are_local_and_source_specific(api):
    app, client, store, pid, _ = api
    before = copy.deepcopy(store.load(pid))
    assert client.get("/api/chroma-key/status").get_json()["available"] is True
    result = apply(client, store, pid, background_color="#0000ff")
    assert result.status_code == 200, result.get_json()
    after = store.load(pid)
    assert after["sources"] == before["sources"]
    assert after["manual"]["chroma_key"]["A"]["background_color"] == "#0000FF"
    assert "B" not in after["manual"]["chroma_key"]
    assert after["manual"]["history"]["undo_count"] == 1
    assert not app.extensions["cutroom_jobs"].active()


def test_missing_filter_never_mutates_project_but_disabling_remains_possible(api, monkeypatch):
    _, client, store, pid, _ = api
    assert apply(client, store, pid).status_code == 200
    before = copy.deepcopy(store.load(pid))
    monkeypatch.setattr(server, "chroma_key_capability", lambda *_: {"available": False})
    assert apply(client, store, pid, color="#FFFFFF").status_code == 409
    assert store.load(pid) == before
    assert apply(client, store, pid, enabled=False).status_code == 200


@pytest.mark.parametrize("extra", [{"slot": "C"}, {"color": "#00ff00;movie=x"}, {"tolerance": True}, {"filter": "arbitrary"}, {"expected_revision": None}])
def test_invalid_edit_is_atomic(api, extra):
    _, client, store, pid, _ = api
    before = copy.deepcopy(store.load(pid))
    assert apply(client, store, pid, **extra).status_code == 400
    assert store.load(pid) == before


def test_stale_locked_and_busy_edits_do_not_change_source_or_settings(api):
    app, client, store, pid, _ = api
    assert apply(client, store, pid, expected_revision=store.load(pid)["revision"] - 1).status_code == 409
    store.update(pid, lambda value: value["manual"].update(track_locks={"A": True}))
    before = copy.deepcopy(store.load(pid))
    assert apply(client, store, pid).status_code == 400
    assert store.load(pid) == before
    assert apply(client, store, pid, slot="B").status_code == 200
    gate = threading.Event()
    app.extensions["cutroom_jobs"].submit("render", pid, lambda _: gate.wait(5))
    try:
        before = copy.deepcopy(store.load(pid))
        assert apply(client, store, pid, slot="B", color="#FFFFFF").status_code == 409
        assert store.load(pid) == before
    finally:
        gate.set()


@pytest.mark.parametrize("slot", ["A", "B"])
def test_replacing_a_source_drops_only_its_key_settings(api, slot):
    _, _, store, pid, _ = api
    value = store.load(pid)
    value["manual"]["chroma_key"] = {key: {**CHROMA_KEY_DEFAULTS, "enabled": True} for key in ("A", "B")}
    other = "B" if slot == "A" else "A"
    expected = copy.deepcopy(value["manual"]["chroma_key"][other])
    server._reset_manual_after_source_change(value, slot, replacing=True)
    assert value["manual"]["chroma_key"] == {other: expected}


@pytest.mark.parametrize("extra", [{"revision": 0}, {"revision": "missing"}, {"revision": "\u00b2"}, {"revision": "9" * 5000}, {"time": "nan"}, {"time": -1}, {"time": 2}, {"path": "private.mp4"}])
def test_frame_request_rejects_stale_invalid_or_path_input_before_ffmpeg(api, monkeypatch, extra):
    _, client, store, pid, _ = api
    monkeypatch.setattr(server.subprocess, "run", lambda *_a, **_k: pytest.fail("invalid request invoked FFmpeg"))
    assert frame(client, store, pid, **extra).status_code in {400, 409}


def test_frame_output_is_bounded_cached_and_never_changes_project(api, monkeypatch):
    _, client, store, pid, _ = api
    before = copy.deepcopy(store.load(pid))
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 15
        assert "scale=640:360" in command[command.index("-filter_complex") + 1]
        Path(command[-1]).write_bytes(green_png())
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(server.subprocess, "run", run)
    first = frame(client, store, pid)
    second = frame(client, store, pid)
    assert first.status_code == second.status_code == 200
    assert len(calls) == 1
    assert first.data == second.data
    assert struct.unpack(">II", first.data[16:24]) == (640, 360)
    assert first.headers["Cache-Control"] == "no-store"
    assert first.headers["X-Cutroom-Project-Revision"] == str(before["revision"])
    assert store.load(pid) == before


@pytest.mark.parametrize("mode", ["timeout", "failure", "stale"])
def test_frame_failure_is_actionable_and_removes_temporary_output(api, monkeypatch, mode):
    _, client, store, pid, _ = api
    def run(command, **_kwargs):
        Path(command[-1]).write_bytes(b"partial frame")
        if mode == "timeout":
            raise subprocess.TimeoutExpired(command, 15)
        if mode == "stale":
            store.update(pid, lambda value: value.update(name="new revision"))
        return SimpleNamespace(returncode=1 if mode == "failure" else 0)
    monkeypatch.setattr(server.subprocess, "run", run)
    response = frame(client, store, pid)
    assert response.status_code == {"timeout": 503, "failure": 422, "stale": 409}[mode]
    assert not list((store.project_dir(pid) / "cache" / "chroma-preview").glob("*.png"))


@pytest.mark.parametrize("image_background", [False, True])
def test_real_frame_keys_at_native_geometry_before_downscale_and_preserves_source(api, image_background):
    _, client, store, pid, settings = api
    ffmpeg = shutil.which(settings.ffmpeg)
    if not ffmpeg:
        pytest.skip("Existing local FFmpeg is required")
    source = store.project_dir(pid) / store.load(pid)["sources"]["A"]["relative_path"]
    subprocess.run([ffmpeg, "-v", "error", "-y", "-threads", "1", "-filter_threads", "1",
        "-f", "lavfi", "-i", "color=c=0x00FF00:s=1280x720:r=25:d=2,drawbox=x=480:y=180:w=320:h=360:color=red:t=fill",
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True, timeout=20)
    original = source.read_bytes()
    extra = {}
    if image_background:
        asset_id = "asset_" + "a" * 32
        background = store.project_dir(pid) / "media" / "assets" / asset_id / "original.png"
        background.parent.mkdir(parents=True)
        background.write_bytes(green_png(1280, 720, b"\xff\xff\0" * 640 + b"\0\xff\xff" * 640))
        asset = {"id": asset_id, "kind": "image", "status": "ready", "name": "synthetic yellow-cyan.png", "duration": 0,
                 "width": 1280, "height": 720, "has_audio": False, "path": background.relative_to(store.project_dir(pid)).as_posix()}
        store.update(pid, lambda value: value["assets"].update({asset_id: asset}))
        extra["background_asset_id"] = asset_id
    assert apply(client, store, pid, background_color="#0000FF", **extra).status_code == 200
    response = frame(client, store, pid)
    assert response.status_code == 200, response.get_json()
    assert struct.unpack(">II", response.data[16:24]) == (640, 360)
    decoded = subprocess.run([ffmpeg, "-v", "error", "-threads", "1", "-i", "pipe:0", "-frames:v", "1", "-f", "rawvideo",
        "-pix_fmt", "rgb24", "-threads", "1", "pipe:1"], input=response.data, capture_output=True, timeout=10, check=True).stdout
    def pixel(x, y):
        offset = (y * 640 + x) * 3
        return decoded[offset:offset + 3]
    background, subject = pixel(20, 20), pixel(320, 180)
    if image_background:
        right = pixel(620, 20)
        assert background[0] > 200 and background[1] > 200 and background[2] < 30
        assert right[0] < 30 and right[1] > 200 and right[2] > 200
    else:
        assert background[2] > 200 and background[0] < 30 and background[1] < 30
    assert subject[0] > 200 and subject[1] < 40 and subject[2] < 40
    assert source.read_bytes() == original


def test_existing_six_field_client_remains_compatible_with_optional_image_choice(api):
    _, client, store, pid, _ = api
    settings = {key: value for key, value in CHROMA_KEY_DEFAULTS.items() if key != "background_asset_id"}
    result = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "set_chroma_key", "slot": "A", **settings,
        "enabled": True, "expected_revision": store.load(pid)["revision"]})
    assert result.status_code == 200, result.get_json()
    assert store.load(pid)["manual"]["chroma_key"]["A"]["background_asset_id"] is None


def test_missing_background_file_fails_before_ffmpeg_or_cached_solid_fallback(api, monkeypatch):
    _, client, store, pid, _ = api
    asset_id = "asset_" + "b" * 32
    asset = {"id": asset_id, "kind": "image", "status": "ready", "name": "synthetic missing.png", "duration": 0,
             "width": 320, "height": 180, "has_audio": False, "path": f"media/assets/{asset_id}/original.png"}
    store.update(pid, lambda value: value["assets"].update({asset_id: asset}))
    assert apply(client, store, pid, background_asset_id=asset_id).status_code == 200
    monkeypatch.setattr(server.subprocess, "run", lambda *_a, **_k: pytest.fail("missing image invoked FFmpeg"))
    response = frame(client, store, pid)
    assert response.status_code == 409
    assert response.get_json()["error"] == "chroma_background_unavailable"
    assert apply(client, store, pid, enabled=False, background_asset_id=asset_id).status_code == 200
