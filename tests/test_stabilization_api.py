"""A derived stabilization copy must never replace project footage or edits."""
import copy
import shutil
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import server

from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom import stabilization_assets
from cutroom.stabilization import StabilizationError
from cutroom.stabilization import stabilization_capability as real_stabilization_capability
from server import create_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.ai["enabled"] = False
    app = create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    project = store.create("Stabilization copy")
    root = store.project_dir(project["id"])
    source = root / "media" / "source A שלום.mp4"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"original footage")
    project["sources"]["A"] = {
        "name": "source A שלום.mp4", "relative_path": source.relative_to(root).as_posix(),
        "duration": 2, "video_duration": 2, "width": 320, "height": 180,
        "has_audio": True, "preparation": "ready", "generation": "fixture-generation",
    }
    project["draft"] = {"keep_ranges": [{"start": 0, "end": 2}]}
    store.save(project)
    monkeypatch.setattr("server.stabilization_capability", lambda *_args, **_kwargs: {
        "available": True, "engine": "vidstab", "message": "Local stabilization is available."}, raising=False)

    def prepare(context, project_id, asset_id, target_store, _settings):
        asset = target_store.load(project_id)["assets"][asset_id]
        target = target_store.project_dir(project_id) / asset["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"stabilized copy")
        context.checkpoint()
        context.commit()
        target_store.update(project_id, lambda value: value["assets"][asset_id].update(
            status="ready", preview_path=asset["path"]))
        return {"project_id": project_id, "asset_id": asset_id}

    monkeypatch.setattr("server.prepare_stabilized_asset", prepare, raising=False)
    yield app, app.test_client(), store, project["id"], source
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def start(client, store, pid, **extra):
    return client.post(f"/api/projects/{pid}/stabilize", json={
        "slot": "A", "expected_revision": store.load(pid)["revision"], **extra})


def test_stabilization_has_local_capability_check_without_ai(api):
    app, client, *_ = api
    response = client.get("/api/stabilization/capability")
    assert response.status_code == 200
    assert response.get_json()["available"] is True
    assert not app.extensions["cutroom_jobs"].active()


def test_copy_is_a_project_asset_and_original_timeline_and_bytes_stay_unchanged(api):
    app, client, store, pid, source = api
    before = copy.deepcopy(store.load(pid))
    response = start(client, store, pid)
    assert response.status_code == 202, response.get_json()
    asset_id = response.get_json()["asset_id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    after = store.load(pid)
    assert after["sources"] == before["sources"]
    assert after["draft"] == before["draft"]
    assert after["manual"] == before["manual"]
    assert source.read_bytes() == b"original footage"
    public = client.get(f"/api/projects/{pid}").get_json()["project"]["assets"][asset_id]
    assert public["status"] == "ready"
    assert "_stabilization" not in public
    download = client.get(f"/api/projects/{pid}/assets/{asset_id}/download")
    assert download.status_code == 200
    assert download.data == b"stabilized copy"
    assert "attachment" in download.headers["Content-Disposition"]


def test_missing_filter_does_not_create_assets_or_jobs(api, monkeypatch):
    app, client, store, pid, _ = api
    monkeypatch.setattr("server.stabilization_capability", lambda *_args, **_kwargs: {
        "available": False, "engine": "vidstab", "message": "This FFmpeg build lacks vidstab."})
    before = copy.deepcopy(store.load(pid))
    response = start(client, store, pid)
    assert response.status_code == 422
    assert response.get_json()["error"] == "stabilization_unavailable"
    assert store.load(pid) == before
    assert not app.extensions["cutroom_jobs"].active()


@pytest.mark.parametrize("extra", [{"slot": "C"}, {"path": "../private.mp4"}, {"expected_revision": 0}])
def test_invalid_or_path_based_requests_are_rejected_without_side_effects(api, extra):
    _, client, store, pid, _ = api
    before = copy.deepcopy(store.load(pid))
    assert start(client, store, pid, **extra).status_code == 400
    assert store.load(pid) == before


def test_stale_revision_and_active_processing_are_rejected(api):
    app, client, store, pid, _ = api
    assert start(client, store, pid, expected_revision=store.load(pid)["revision"] - 1).status_code == 409
    gate = threading.Event()
    app.extensions["cutroom_jobs"].submit("render", pid, lambda context: gate.wait(5))
    try:
        assert start(client, store, pid).status_code == 409
    finally:
        gate.set()


def test_source_generation_is_pinned_for_a_retryable_copy(api):
    app, client, store, pid, _ = api
    response = start(client, store, pid)
    assert response.status_code == 202
    asset_id = response.get_json()["asset_id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    descriptor = store.load(pid)["assets"][asset_id]["_stabilization"]
    assert descriptor["slot"] == "A"
    assert descriptor["generation"] == "fixture-generation"


def pending_copy(store, pid, source):
    asset_id = "asset_" + "c" * 32
    root = store.project_dir(pid)
    stat = source.stat()
    source_metadata = store.load(pid)["sources"]["A"]
    asset = {
        "id": asset_id, "name": "stabilized.mp4", "kind": "video", "duration": 2,
        "width": 320, "height": 180, "has_audio": True, "status": "failed", "waveform": [],
        "path": f"media/assets/{asset_id}/stabilized.mp4", "stabilized": True,
        "_stabilization": {"slot": "A", "generation": source_metadata["generation"],
                           "relative_path": source_metadata["relative_path"],
                           "fingerprint": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}},
    }
    target = root / asset["path"]
    target.parent.mkdir(parents=True)
    store.update(pid, lambda value: value["assets"].update({asset_id: asset}))
    return asset_id, target


def test_full_copy_download_and_public_marker_never_return_the_small_preview(api):
    _, client, store, pid, source = api
    asset_id, target = pending_copy(store, pid, source)
    target.write_bytes(b"full resolution stabilized copy")
    preview = target.parent / "preview.mp4"
    preview.write_bytes(b"720p editor preview")
    store.update(pid, lambda value: value["assets"][asset_id].update(
        status="ready", preview_path=preview.relative_to(store.project_dir(pid)).as_posix()))
    asset = client.get(f"/api/projects/{pid}").get_json()["project"]["assets"][asset_id]
    assert asset["stabilized"] is True and "_stabilization" not in asset and "path" not in asset
    assert client.get(asset["download_url"]).data == target.read_bytes()
    assert client.get(asset["url"]).data == preview.read_bytes()
    store.update(pid, lambda value: value["assets"][asset_id].update(status="failed"))
    assert client.get(asset["download_url"]).status_code == 404
    assert "download_url" not in client.get(f"/api/projects/{pid}").get_json()["project"]["assets"][asset_id]


def test_failed_stabilization_retry_uses_the_stabilizer_wrapper(api, monkeypatch):
    app, client, store, pid, source = api
    asset_id, _ = pending_copy(store, pid, source)
    calls = []
    original_prepare = server.prepare_stabilized_asset

    def wrapper(*args):
        calls.append(args[2])
        return original_prepare(*args)

    def ordinary_import(*_args):
        pytest.fail("A stabilized asset must retry stabilization, not an unfinished ordinary import")

    monkeypatch.setattr("server.prepare_stabilized_asset", wrapper)
    monkeypatch.setattr("server.prepare_asset", ordinary_import)
    response = client.post(f"/api/projects/{pid}/assets/{asset_id}/prepare")
    assert response.status_code == 202, response.get_json()
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    assert calls == [asset_id]
    assert store.load(pid)["assets"][asset_id]["status"] == "ready"


@pytest.mark.parametrize("failure", ["capability", "generation", "fingerprint"])
def test_unavailable_retry_does_not_requeue_or_change_project(api, monkeypatch, failure):
    app, client, store, pid, source = api
    asset_id, _ = pending_copy(store, pid, source)
    expected_status = 409
    if failure == "capability":
        expected_status = 422
        monkeypatch.setattr("server.stabilization_capability", lambda *_args, **_kwargs: {
            "available": False, "engine": "vidstab", "message": "Stabilization is unavailable."})
    elif failure == "generation":
        store.update(pid, lambda value: value["sources"]["A"].update(generation="new-generation"))
    else:
        source.write_bytes(b"different current footage")
    before = store.load(pid)
    response = client.post(f"/api/projects/{pid}/assets/{asset_id}/prepare")
    assert response.status_code == expected_status, response.get_json()
    assert store.load(pid) == before
    assert not app.extensions["cutroom_jobs"].active()


@pytest.mark.parametrize("guard", ["preparing", "no_video", "disk", "asset_limit"])
def test_start_guards_leave_sources_and_project_untouched(api, monkeypatch, guard):
    app, client, store, pid, _ = api
    status = 400
    if guard == "preparing":
        store.update(pid, lambda value: value["sources"]["A"].update(preparation="queued"))
        status = 409
    elif guard == "no_video":
        store.update(pid, lambda value: value["sources"]["A"].update(width=0, height=0))
    elif guard == "disk":
        monkeypatch.setattr("server.shutil.disk_usage", lambda *_args: SimpleNamespace(free=0))
        status = 507
    else:
        def fill(value):
            for index in range(100):
                asset_id = f"asset_{index:032x}"
                value["assets"][asset_id] = {"id": asset_id, "kind": "image", "status": "ready"}
        store.update(pid, fill)
    before = store.load(pid)
    response = start(client, store, pid)
    assert response.status_code == status, response.get_json()
    assert store.load(pid) == before
    assert not app.extensions["cutroom_jobs"].active()


def stub_stabilization(monkeypatch):
    def stabilize(source, target, settings, progress=None, cancel_check=None):
        for value in (.05, .5, .95, 1):
            if progress:
                progress(value, "Local stabilization")
        target.write_bytes(b"stabilized output")
        return target
    monkeypatch.setattr(stabilization_assets, "stabilize_video", stabilize)
    monkeypatch.setattr(stabilization_assets, "probe_asset", lambda *_args: {
        "kind": "video", "duration": 2, "width": 320, "height": 180, "has_audio": True})


def test_wrapper_prepares_real_asset_fields_with_monotonic_progress(api, monkeypatch):
    app, _, store, pid, source = api
    asset_id, target = pending_copy(store, pid, source)
    before = store.load(pid)
    stub_stabilization(monkeypatch)
    updates = []
    context = JobContext(Job("job_stabilize_test", "prepare_asset", pid), threading.Lock(),
                         on_change_locked=lambda job: updates.append(job.progress))

    def preview(context, project_id, asset_id, store, settings):
        for progress in (.08, .65, .8):
            context.update(progress, "Preparing local preview")
        def complete(value):
            context.commit()
            value["assets"][asset_id].update(status="ready", waveform=[0, 1, 0])
        store.update(project_id, complete)
        return {"project_id": project_id, "asset_id": asset_id}

    monkeypatch.setattr(stabilization_assets, "prepare_asset", preview)
    result = stabilization_assets.prepare_stabilized_asset(context, pid, asset_id, store,
                                                          app.extensions["cutroom_settings"])
    assert result == {"project_id": pid, "asset_id": asset_id}
    after = store.load(pid)
    assert after["assets"][asset_id]["waveform"] == [0, 1, 0]
    assert after["sources"] == before["sources"] and after["draft"] == before["draft"] and after["manual"] == before["manual"]
    assert target.read_bytes() == b"stabilized output" and source.read_bytes() == b"original footage"
    assert updates == sorted(updates) and updates[-1] == 1 and context.committed


@pytest.mark.parametrize("failure", ["probe", "source_changed", "cancelled"])
def test_wrapper_failure_cleans_its_copy_and_preserves_unrelated_media(api, monkeypatch, failure):
    app, _, store, pid, source = api
    asset_id, target = pending_copy(store, pid, source)
    unrelated = target.parent / "keep.txt"
    unrelated.write_bytes(b"unrelated file")
    before = store.load(pid)
    context = JobContext(Job("job_stabilize_fail", "prepare_asset", pid), threading.Lock())

    def stabilize(*_args, **_kwargs):
        target.write_bytes(b"new derived output")
        if failure == "source_changed":
            store.update(pid, lambda value: value["sources"]["A"].update(generation="replacement"))
        if failure == "cancelled":
            context.job.cancel_event.set()
        return target

    def probe(*_args):
        raise RuntimeError("Private decoder path C:/private/recording.mp4")

    monkeypatch.setattr(stabilization_assets, "stabilize_video", stabilize)
    monkeypatch.setattr(stabilization_assets, "probe_asset", probe)
    error_type = JobCancelled if failure == "cancelled" else StabilizationError
    with pytest.raises(error_type) as caught:
        stabilization_assets.prepare_stabilized_asset(context, pid, asset_id, store,
                                                     app.extensions["cutroom_settings"])
    assert "C:/private" not in str(caught.value)
    assert not target.exists() and unrelated.read_bytes() == b"unrelated file"
    assert source.read_bytes() == b"original footage"
    after = store.load(pid)
    assert after["assets"][asset_id]["status"] == ("cancelled" if failure == "cancelled" else "failed")
    assert after["draft"] == before["draft"] and after["manual"] == before["manual"]


def test_wrapper_refuses_to_overwrite_or_delete_an_existing_copy(api):
    app, _, store, pid, source = api
    asset_id, target = pending_copy(store, pid, source)
    target.write_bytes(b"existing independent copy")
    context = JobContext(Job("job_existing_copy", "prepare_asset", pid), threading.Lock())
    with pytest.raises(StabilizationError, match="already exists"):
        stabilization_assets.prepare_stabilized_asset(context, pid, asset_id, store,
                                                     app.extensions["cutroom_settings"])
    assert target.read_bytes() == b"existing independent copy"
    assert source.read_bytes() == b"original footage"


def test_real_synthetic_stabilization_copy_prepares_waveform_and_downloads_original_resolution(api, monkeypatch):
    app, client, store, pid, source = api
    settings = app.extensions["cutroom_settings"]
    if not shutil.which(settings.ffmpeg) or not shutil.which(settings.ffprobe):
        pytest.skip("FFmpeg and ffprobe are unavailable")
    if not real_stabilization_capability(settings)["available"]:
        pytest.skip("The installed FFmpeg lacks optional libvidstab filters")
    subprocess.run([
        settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc2=s=128x96:r=25:d=0.8",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=0.8",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-shortest", str(source),
    ], check=True, capture_output=True, timeout=30)
    metadata = server.probe_media(source, settings)
    store.update(pid, lambda value: value["sources"]["A"].update(metadata))
    before = store.load(pid)
    original = source.read_bytes()
    monkeypatch.setattr(server, "prepare_stabilized_asset", stabilization_assets.prepare_stabilized_asset)
    response = start(client, store, pid)
    assert response.status_code == 202, response.get_json()
    asset_id = response.get_json()["asset_id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    after = store.load(pid)
    asset = after["assets"][asset_id]
    assert asset["status"] == "ready", app.extensions["cutroom_jobs"].latest(pid, "prepare_asset", dedupe_key=asset_id).public()
    assert (asset["width"], asset["height"]) == (128, 96)
    assert asset["waveform"] and max(asset["waveform"]) == 1
    assert source.read_bytes() == original
    assert after["sources"] == before["sources"] and after["draft"] == before["draft"] and after["manual"] == before["manual"]
    downloaded = client.get(f"/api/projects/{pid}/assets/{asset_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.data == (store.project_dir(pid) / asset["path"]).read_bytes()
    assert "attachment" in downloaded.headers["Content-Disposition"]
