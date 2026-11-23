"""Direct manual entry keeps the legacy project model and original media intact."""
from __future__ import annotations

import hashlib
import io
import threading
import time

import pytest

import server
from cutroom import render
from cutroom.config import load_settings
from cutroom.jobs import Job, JobAdmissionError, JobContext
from test_backend_hardening import _probe, _QueuedJob
from test_source_tracks_render import media


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.ai["enabled"] = False
    application = server.create_app(settings)
    application.config.update(TESTING=True)
    yield application
    application.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def create(client, workflow="manual"):
    response = client.post("/api/projects", json={"name": "Direct edit", "initial_settings": {
        "workflow": workflow, "goal": "youtube", "aspect": "16:9", "editorial_effects": False,
        "resolution": "720", "fps": 30}})
    assert response.status_code == 201
    return response.get_json()["project"]


def upload(client, project_id, slot="A", *, token=None, content=b"original recording"):
    return client.post(f"/api/projects/{project_id}/sources/{slot}",
                       data={"file": (io.BytesIO(content), "recording.mp4")},
                       content_type="multipart/form-data",
                       headers={"X-Cutroom-Upload-Token": token} if token else {})


@pytest.mark.parametrize("workflow,slot,starts", [("manual", "A", True), ("manual", "B", False), ("ai", "A", False)])
def test_only_first_primary_manual_import_starts_an_edit_atomically(app, monkeypatch, workflow, slot, starts):
    client = app.test_client()
    project = create(client, workflow)
    assert project["draft"] is None and project["sources"] == {"A": None, "B": None}
    assert client.get(f"/api/projects/{project['id']}").get_json()["project"]["revision"] == project["revision"]
    calls = []
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda kind, *a, **k: calls.append(kind) or _QueuedJob())
    response = upload(client, project["id"], slot)
    assert response.status_code == 201
    saved = response.get_json()["project"]
    assert bool(saved["draft"]) == starts
    assert calls == ["prepare_source"], "import must not invoke AI or transcription"
    if starts:
        assert saved["draft"]["engine"] == "manual"
        assert saved["draft"]["keep_ranges"] == [{"start": 0, "end": 12}]
        assert saved["manual"]["history"] == {"undo_count": 0, "redo_count": 0}
        assert saved["editor_sequence"]["duration"] == 12
        assert not saved["editor_sequence"].get("error")
        reopened = client.get(f"/api/projects/{project['id']}").get_json()["project"]
        assert reopened["draft"] == saved["draft"]
        assert reopened["editor_sequence"] == saved["editor_sequence"]


def test_manual_import_keeps_timeline_when_preview_queue_is_full(app, monkeypatch):
    client = app.test_client()
    project = create(client)
    monkeypatch.setattr(server, "probe_media", _probe)
    def no_capacity(*args, **kwargs):
        raise JobAdmissionError("queue full")
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", no_capacity)
    response = upload(client, project["id"])
    assert response.status_code == 201
    result = response.get_json()
    assert result["preparation_deferred"] and result["job"] is None
    assert result["project"]["draft"]["output_duration"] == 12
    assert result["project"]["sources"]["A"]["preparation"] == "failed"


def test_first_manual_import_cancel_removes_matching_timeline_and_allows_clean_retry(app, monkeypatch):
    client = app.test_client()
    project = create(client)
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *a, **k: _QueuedJob())
    token = "manual_first_import_cancel_01"
    assert upload(client, project["id"], token=token).get_json()["project"]["draft"]
    cancelled = client.post(f"/api/projects/{project['id']}/sources/A/uploads/{token}/cancel")
    assert cancelled.status_code == 202 and cancelled.get_json()["removed"]
    saved = client.get(f"/api/projects/{project['id']}").get_json()["project"]
    assert saved["draft"] is None and saved["sources"]["A"] is None
    retry = upload(client, project["id"], token="manual_first_import_retry_02", content=b"retry recording")
    assert retry.status_code == 201 and retry.get_json()["project"]["draft"]["engine"] == "manual"


def test_replacement_does_not_automatically_restart_an_existing_manual_edit(app, monkeypatch):
    client = app.test_client()
    project = create(client)
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *a, **k: _QueuedJob())
    assert upload(client, project["id"]).get_json()["project"]["draft"]
    replacement = upload(client, project["id"], content=b"replacement")
    assert replacement.status_code == 201
    assert replacement.get_json()["project"]["draft"] is None


def test_failed_first_manual_timeline_commit_rolls_back_file_and_project(app, monkeypatch):
    client = app.test_client()
    project = create(client)
    store = app.extensions["cutroom_store"]
    before = store.load(project["id"])
    monkeypatch.setattr(server, "probe_media", _probe)
    def fail_start(value):
        raise RuntimeError("synthetic timeline failure")
    monkeypatch.setattr(server, "start_manual_draft", fail_start)
    response = upload(client, project["id"])
    assert response.status_code == 500
    assert store.load(project["id"]) == before
    assert not list((store.project_dir(project["id"]) / "media").glob("*"))


def wait_job(client, result):
    job = result.get("job")
    if not job:
        return
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        current = client.get(f"/api/jobs/{job['id']}").get_json()["job"]
        if current["status"] in {"completed", "failed", "cancelled"}:
            assert current["status"] == "completed", current
            return
        time.sleep(.05)
    pytest.fail("Synthetic media preparation did not complete within 60 seconds")


def chunked_import(client, project_id, path, *, purpose, slot=None):
    content = path.read_bytes()
    token = f"direct_manual_{purpose}_import_01"
    preflight = client.post(f"/api/projects/{project_id}/uploads/preflight", json={
        "purpose": purpose, **({"slot": slot} if slot else {}), "filename": path.name,
        "size_bytes": len(content), "upload_token": token})
    assert preflight.status_code == 201, preflight.get_json()
    admission = preflight.get_json()
    # Multiple real chunks exercise the same transport the browser uses.
    chunk_size = min(admission["chunk_size_bytes"], 4096)
    for offset in range(0, len(content), chunk_size):
        response = client.put(admission["upload_url"], data=content[offset:offset + chunk_size], headers={
            "Content-Type": "application/octet-stream", "X-Cutroom-Upload-Token": token,
            "X-Cutroom-Upload-Offset": str(offset)})
        assert response.status_code == 200, response.get_json()
    endpoint = f"sources/{slot}" if purpose == "source" else "assets"
    response = client.post(f"/api/projects/{project_id}/{endpoint}", json={}, headers={
        "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": token})
    assert response.status_code in {201, 202}, response.get_json()
    result = response.get_json()
    wait_job(client, result)
    return result


def test_real_empty_create_import_edit_additional_clip_reopen_and_export(app, media, monkeypatch):
    client = app.test_client()
    ffmpeg, ffprobe, paths = media
    store = app.extensions["cutroom_store"]
    submitted = []
    submit = app.extensions["cutroom_jobs"].submit
    def tracked_submit(kind, *args, **kwargs):
        submitted.append(kind)
        return submit(kind, *args, **kwargs)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", tracked_submit)
    project = create(client)
    project_id = project["id"]
    original_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    imported = chunked_import(client, project_id, paths[0], purpose="source", slot="A")
    assert imported["project"]["draft"]["engine"] == "manual"
    assert imported["project"]["draft"]["output_duration"] == pytest.approx(4, abs=.05)

    def edit(action, **kwargs):
        current = client.get(f"/api/projects/{project_id}").get_json()["project"]
        result = client.post(f"/api/projects/{project_id}/manual/edit", json={
            "action": action, "expected_revision": current["revision"], **kwargs})
        assert result.status_code == 200, result.get_json()
        return result.get_json()["project"]

    edited = edit("sequence_ripple_delete", start=1, end=2)
    assert edited["editor_sequence"]["duration"] == pytest.approx(3, abs=.05)
    additional = chunked_import(client, project_id, paths[1], purpose="asset")
    edited = edit("media_append", asset_id=additional["asset_id"], source_start=1, source_end=3)
    assert edited["editor_sequence"]["duration"] == pytest.approx(5, abs=.05)
    reopened = client.get(f"/api/projects/{project_id}").get_json()["project"]
    assert reopened["editor_sequence"] == edited["editor_sequence"]
    assert reopened["manual"]["media_clips"] == edited["manual"]["media_clips"]
    assert reopened["manual"]["history"]["undo_count"] == 2
    assert submitted == ["prepare_source", "prepare_asset"]
    assert reopened["analysis"]["engine"] == "manual"

    context = JobContext(Job("direct-manual-export", "render", project_id), threading.Lock())
    exported = render.render_project(context, project_id, store, store.settings, {"quality": "fast", "_force_software": True})
    assert exported["export"]["duration"] == pytest.approx(5, abs=.05)
    assert (store.settings.exports_dir / exported["export"]["name"]).is_file()
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == original_hashes
    saved = store.load(project_id)
    assert hashlib.sha256((store.project_dir(project_id) / saved["sources"]["A"]["relative_path"]).read_bytes()).hexdigest() == original_hashes[0]
    assert hashlib.sha256((store.project_dir(project_id) / saved["assets"][additional["asset_id"]]["path"]).read_bytes()).hexdigest() == original_hashes[1]
