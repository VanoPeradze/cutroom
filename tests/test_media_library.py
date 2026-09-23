from __future__ import annotations

import copy
import io
import shutil
import subprocess
import threading

import pytest

from cutroom.config import load_settings
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.media_library import ASSET_ID_RE, MediaLibraryError, prepare_asset, probe_asset, safe_asset_path
from cutroom.jobs import Job, JobCancelled, JobContext
from server import _public_project, _reset_manual_after_source_change, create_app


ASSET = "asset_" + "a" * 32


def project():
    return {
        "id": "project_012345abcdef", "sources": {"A": {"duration": 20}, "B": None},
        "assets": {ASSET: {"id": ASSET, "name": "music.wav", "kind": "audio", "duration": 30, "width": 0, "height": 0, "has_audio": True, "status": "ready", "path": f"media/assets/{ASSET}/original.wav"}},
        "manual": {}, "draft": {"keep_ranges": [{"start": 0, "end": 10}, {"start": 15, "end": 20}], "cuts": [{"start": 10, "end": 15}], "output_duration": 15, "camera_plan": [{"start": 0, "end": 10, "camera": "A"}, {"start": 15, "end": 20, "camera": "A"}]},
    }


def add(value, **kwargs):
    apply_manual_edit(value, {"action": "media_add", "asset_id": ASSET, **kwargs})
    return value["manual"]["media_clips"][-1]


def test_add_uses_edit_duration_and_split_respects_speed_and_undo():
    value = project()
    value["assets"][ASSET]["kind"] = "video"
    clip = add(value, start=3, speed=2)
    assert (clip["start"], clip["end"]) == (3, 15)
    apply_manual_edit(value, {"action": "media_split", "clip_id": clip["id"], "time": 8})
    left, right = value["manual"]["media_clips"]
    assert left["end"] == 8 and right["source_start"] == 5 and right["video_source_start"] == 10
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["media_clips"] == [clip]
    apply_manual_edit(value, {"action": "redo"})
    assert len(value["manual"]["media_clips"]) == 2


@pytest.mark.parametrize("field,bad", [("start", True), ("end", float("nan")), ("speed", 0), ("speed", 5), ("source_start", -1), ("x", .5), ("muted", "false"), ("role", "other"), ("fit", "stretch"), ("motion", "arbitrary"), ("volume_db", 100), ("fade_in", 16)])
def test_bad_media_edits_leave_state_untouched(field, bad):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        add(value, **{field: bad})
    assert value == before


def test_source_bounds_speed_and_noop_preserve_redo():
    value = project()
    clip = add(value, end=10)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "media_update", "clip_id": clip["id"], "speed": 4})
    apply_manual_edit(value, {"action": "media_duplicate", "clip_id": clip["id"], "start": 5})
    apply_manual_edit(value, {"action": "undo"})
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "media_update", "clip_id": clip["id"], "speed": 1})
    assert value == before


def test_video_split_in_held_tail_keeps_picture_and_audio_clocks():
    value = project()
    value["assets"][ASSET].update(kind="video", duration=3)
    clip = add(value, speed=2, end=3)
    apply_manual_edit(value, {"action": "media_split", "clip_id": clip["id"], "time": 2})
    right = value["manual"]["media_clips"][1]
    assert right["source_start"] == 2
    assert right["video_source_start"] == 4


def test_mixer_is_undoable_and_base_deletion_preserves_media_transactionally():
    value = project()
    add(value)
    apply_manual_edit(value, {"action": "set_audio_mixer", "music_db": -12, "ducking": True})
    assert value["manual"]["audio_mixer"]["music_db"] == -12
    apply_manual_edit(value, {"action": "undo"})
    assert "audio_mixer" not in value["manual"]
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Trim, move, or remove"):
        apply_manual_edit(value, {"action": "delete_range", "start": 0, "end": 5})
    assert value == before


def test_sequence_ripple_delete_refuses_to_strand_added_media_without_losing_history():
    value = project()
    clip = add(value, start=12, end=15)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="Trim, move, or remove"):
        apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 0, "end": 5})
    assert value == before
    apply_manual_edit(value, {"action": "media_update", "clip_id": clip["id"], "start": 7, "end": 10})
    apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 0, "end": 5})
    assert value["manual"]["sequence"]["duration"] == 10
    assert value["manual"]["media_clips"][0]["end"] == 10


def test_replacing_secondary_recording_preserves_independent_assets_and_layers():
    value = project()
    clip = copy.deepcopy(add(value, start=2, end=5))
    apply_manual_edit(value, {"action": "set_audio_mixer", "music_db": -12})
    mixer = copy.deepcopy(value["manual"]["audio_mixer"])
    assets = copy.deepcopy(value["assets"])
    _reset_manual_after_source_change(value, "B", replacing=True)
    assert value["manual"]["media_clips"] == [clip]
    assert value["manual"]["audio_mixer"] == mixer
    assert value["assets"] == assets


def test_public_metadata_hides_all_internal_asset_paths(tmp_path):
    value = project()
    value["assets"][ASSET].update(preview_path=f"media/assets/{ASSET}/preview.m4a", thumbnail_path=f"media/assets/{ASSET}/thumbnail.jpg")
    asset = _public_project(value)["assets"][ASSET]
    assert not {"path", "preview_path", "thumbnail_path"} & asset.keys()
    assert asset["url"].endswith(f"/{ASSET}/media")
    assert asset["thumbnail_url"].endswith(f"/{ASSET}/thumbnail")
    for path in ("../secret", "media/source-A.mp4", str(tmp_path / "secret")):
        with pytest.raises(FileNotFoundError):
            safe_asset_path(tmp_path / "project", path)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    settings.raw["host"] = "127.0.0.1"
    app = create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    created = store.create("Media test")
    value = project()
    value["id"] = created["id"]
    store.save({**created, **value})
    yield app, app.test_client(), store, value["id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def test_api_requires_revision_and_rejects_unknown_fields(api):
    _, client, store, pid = api
    payload = {"action": "media_add", "asset_id": ASSET}
    assert client.post(f"/api/projects/{pid}/manual/edit", json=payload).status_code == 400
    payload["expected_revision"] = store.load(pid)["revision"]
    result = client.post(f"/api/projects/{pid}/manual/edit", json=payload)
    assert result.status_code == 200, result.get_json()
    assert client.post(f"/api/projects/{pid}/manual/edit", json=payload).status_code == 409
    assert client.post(f"/api/projects/{pid}/manual/edit", json={**payload, "path": "C:/secret"}).status_code == 400


def test_upload_is_project_scoped_and_serves_only_prepared_media(api, monkeypatch):
    app, client, store, pid = api
    def prepare(context, project_id, asset_id, target_store, settings):
        asset = target_store.load(project_id)["assets"][asset_id]
        target_store.update(project_id, lambda value: value["assets"][asset_id].update(status="ready", preview_path=asset["path"]))
        return {"asset_id": asset_id}
    monkeypatch.setattr("server.probe_asset", lambda *args: {"kind": "audio", "duration": 2, "width": 0, "height": 0, "has_audio": True})
    monkeypatch.setattr("server.prepare_asset", prepare)
    response = client.post(f"/api/projects/{pid}/assets", data={"file": (io.BytesIO(b"audio-bytes"), "../sound.wav")})
    assert response.status_code == 202, response.get_json()
    asset = response.get_json()["asset"]
    assert ASSET_ID_RE.fullmatch(asset["id"])
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    assert client.get(asset["url"]).data == b"audio-bytes"
    assert "path" not in client.get(f"/api/projects/{pid}").get_json()["project"]["assets"][asset["id"]]
    assert client.post(f"/api/projects/{pid}/assets", data={"file": (io.BytesIO(b"x"), "unsafe.svg")}).status_code == 400


def test_media_edits_are_rejected_while_a_job_is_active(api):
    app, client, store, pid = api
    gate = threading.Event()
    def job(context):
        gate.wait(5)
    app.extensions["cutroom_jobs"].submit("render", pid, job)
    try:
        response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "media_add", "asset_id": ASSET, "expected_revision": store.load(pid)["revision"]})
        assert response.status_code == 409
        assert response.get_json()["error"] == "project_busy"
    finally:
        gate.set()


def test_queued_import_cancel_marks_asset_and_keeps_project_media(api):
    app, client, store, pid = api
    manager = app.extensions["cutroom_jobs"]
    gate = threading.Event()
    manager.submit("prepare_source", None, lambda context: gate.wait(5))
    store.update(pid, lambda value: value["assets"][ASSET].update(status="preparing"))
    queued = manager.submit("prepare_asset", pid, lambda context: None, dedupe_key=ASSET)
    try:
        response = client.post(f"/api/jobs/{queued.id}/cancel", json={})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["status"] == "cancelled"
        assert store.load(pid)["assets"][ASSET]["status"] == "cancelled"
        assert store.load(pid)["sources"]["A"]["duration"] == 20
    finally:
        gate.set()


def test_interrupted_import_is_retryable_on_reload_and_paths_stay_private(api, monkeypatch):
    _, client, store, pid = api
    store.update(pid, lambda value: value["assets"][ASSET].update(status="preparing", private_debug_path="C:/private/location"))
    response = client.get(f"/api/projects/{pid}")
    asset = response.get_json()["project"]["assets"][ASSET]
    assert asset["status"] == "failed"
    assert "private_debug_path" not in asset
    monkeypatch.setattr("server.prepare_asset", lambda *args: {"asset_id": ASSET})
    retry = client.post(f"/api/projects/{pid}/assets/{ASSET}/prepare")
    assert retry.status_code == 202
    assert retry.get_json()["project"]["assets"][ASSET]["status"] == "preparing"


@pytest.mark.parametrize("failure", [
    subprocess.CalledProcessError(1, ["C:/private/ffmpeg.exe", "-i", "C:/private/recording.wav"]),
    subprocess.TimeoutExpired(["C:/private/ffmpeg.exe", "-i", "C:/private/recording.wav"], 90),
    OSError("Cannot access C:/private/recording.wav"),
])
def test_preparation_failure_keeps_command_and_paths_out_of_public_job(api, monkeypatch, failure):
    app, client, store, pid = api
    settings = app.extensions["cutroom_settings"]
    def fail(*_args, **_kwargs):
        raise failure
    monkeypatch.setattr("cutroom.media_library.run_command", fail)
    context = JobContext(Job("job_media_error", "prepare_asset", pid), threading.Lock())
    with pytest.raises(MediaLibraryError) as caught:
        prepare_asset(context, pid, ASSET, store, settings)
    assert caught.value.__cause__ is failure
    assert "C:/private" not in str(caught.value)
    manager = app.extensions["cutroom_jobs"]
    job = manager.submit("prepare_asset", pid, prepare_asset, pid, ASSET, store, settings, dedupe_key=ASSET)
    manager.shutdown(wait=True)
    response = client.get(f"/api/jobs/{job.id}")
    public = response.get_json()["job"]
    assert public["status"] == "failed"
    assert public["result"] is None
    assert "Retry the import" in public["error"]
    assert "C:/private" not in response.get_data(as_text=True)
    assert "ffmpeg.exe" not in response.get_data(as_text=True)
    assert "C:/private" in job.result["traceback"]
    assert store.load(pid)["assets"][ASSET]["status"] == "failed"


def test_preparation_cancellation_is_not_relabelled_as_failure(api, monkeypatch):
    app, _, store, pid = api
    def cancel(*_args, **_kwargs):
        raise JobCancelled("Job cancelled")
    monkeypatch.setattr("cutroom.media_library.run_command", cancel)
    context = JobContext(Job("job_media_cancel", "prepare_asset", pid), threading.Lock())
    with pytest.raises(JobCancelled):
        prepare_asset(context, pid, ASSET, store, app.extensions["cutroom_settings"])
    assert store.load(pid)["assets"][ASSET]["status"] == "cancelled"


@pytest.mark.parametrize("kind,suffix,input_args", [
    ("image", ".png", ["-f", "lavfi", "-i", "color=red:s=64x48", "-frames:v", "1"]),
    ("audio", ".wav", ["-f", "lavfi", "-i", "sine=frequency=440:duration=0.4"]),
    ("video", ".mp4", ["-f", "lavfi", "-i", "color=blue:s=64x48:d=0.4", "-f", "lavfi", "-i", "sine=frequency=440:duration=0.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac"]),
])
def test_real_local_preparation_builds_browser_assets_without_ai(api, kind, suffix, input_args):
    app, _, store, pid = api
    settings = app.extensions["cutroom_settings"]
    if not shutil.which(settings.ffmpeg) or not shutil.which(settings.ffprobe):
        pytest.skip("FFmpeg and ffprobe are unavailable")
    path = store.project_dir(pid) / "media" / "assets" / ASSET / ("original" + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([settings.ffmpeg, "-hide_banner", "-v", "error", "-y", *input_args, str(path)], check=True, capture_output=True, timeout=30)
    metadata = probe_asset(path, kind, settings)
    store.update(pid, lambda value: value["assets"][ASSET].update(metadata, path=path.relative_to(store.project_dir(pid)).as_posix(), status="preparing"))
    context = JobContext(Job("job_media_prepare", "prepare_asset", pid), threading.Lock())
    prepare_asset(context, pid, ASSET, store, settings)
    asset = store.load(pid)["assets"][ASSET]
    assert asset["status"] == "ready"
    assert safe_asset_path(store.project_dir(pid), asset["preview_path"]).is_file()
    if kind != "audio":
        assert safe_asset_path(store.project_dir(pid), asset["thumbnail_path"]).is_file()
    if kind != "image":
        assert asset["waveform"] and max(asset["waveform"]) == 1
