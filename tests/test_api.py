from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest

from cutroom.config import load_settings
from server import create_app


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    application = create_app(settings)
    application.config.update(TESTING=True)
    return application


def test_health_and_project_lifecycle(app):
    client = app.test_client()
    health = client.get("/api/health")
    assert health.status_code == 200
    created = client.post("/api/projects", json={"name": "Test edit"})
    assert created.status_code == 201
    project = created.get_json()["project"]
    fetched = client.get(f"/api/projects/{project['id']}")
    assert fetched.status_code == 200
    patched = client.patch(f"/api/projects/{project['id']}", json={"settings": {"aspect": "1:1"}})
    assert patched.get_json()["project"]["settings"]["aspect"] == "1:1"
    missing_prepare = client.post(f"/api/projects/{project['id']}/sources/A/prepare")
    assert missing_prepare.status_code == 404
    assert missing_prepare.get_json()["error"] == "source_required"
    listed = client.get("/api/projects").get_json()["projects"]
    assert any(item["id"] == project["id"] for item in listed)
    assert client.delete(f"/api/projects/{project['id']}").status_code == 200


def test_favicon_is_explicit_and_legacy_path_is_supported(app):
    client = app.test_client()
    index = client.get("/")
    assert index.status_code == 200
    assert b'href="/assets/favicon.svg"' in index.data
    for path in ("/assets/favicon.svg", "/favicon.ico"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.mimetype == "image/svg+xml"


def test_deleting_a_busy_project_does_not_cancel_its_work(app):
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Synthetic busy project"}).get_json()["project"]
    manager = app.extensions["cutroom_jobs"]
    started = threading.Event()
    release = threading.Event()

    def working(context):
        started.set()
        while not release.wait(0.01):
            context.checkpoint()
        return {"ok": True}

    try:
        job = manager.submit("director", project["id"], working)
        assert started.wait(1.0)
        response = client.delete(f"/api/projects/{project['id']}")
        assert response.status_code == 409
        assert response.get_json()["error"] == "project_busy"
        assert manager.get(job.id).status == "running"
        assert manager.get(job.id).public()["cancel_requested"] is False
        assert client.get(f"/api/projects/{project['id']}").status_code == 200
    finally:
        release.set()
        manager.shutdown(wait=True, cancel_pending=True)


def test_project_rename_rejects_stale_revisions_and_preserves_edit(app):
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Synthetic rename"}).get_json()["project"]
    url = f"/api/projects/{project['id']}"
    edited = client.patch(url, json={"settings": {"aspect": "1:1"}, "expected_revision": project["revision"]}).get_json()["project"]
    conflict = client.patch(url, json={"name": "Stale name", "expected_revision": project["revision"]})
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "revision_conflict"
    renamed = client.patch(url, json={"name": "  Clear name  ", "expected_revision": edited["revision"]}).get_json()["project"]
    assert renamed["name"] == "Clear name"
    assert renamed["settings"]["aspect"] == "1:1"
    assert renamed["revision"] == edited["revision"] + 1


def test_cancel_job_api_is_idempotent_and_returns_authoritative_job(app):
    client = app.test_client()
    manager = app.extensions["cutroom_jobs"]
    started = threading.Event()

    def cancellable(context):
        started.set()
        while True:
            context.cancellable_wait(0.05)

    job = manager.submit("director", "cancel-api-project", cancellable)
    assert started.wait(1.0)

    missing = client.post("/api/jobs/job-does-not-exist/cancel", json={})
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "not_found"

    first = client.post(f"/api/jobs/{job.id}/cancel", json={})
    assert first.status_code in {200, 202}
    first_payload = first.get_json()
    assert first_payload["ok"] is True
    assert first_payload["accepted"] is True
    assert first_payload["job"]["id"] == job.id
    assert first_payload["job"]["cancel_requested"] is True

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and manager.get(job.id).status != "cancelled":
        time.sleep(0.01)
    assert manager.get(job.id).status == "cancelled"

    repeated = client.post(f"/api/jobs/{job.id}/cancel", json={})
    assert repeated.status_code == 200
    repeated_payload = repeated.get_json()
    assert repeated_payload["ok"] is True
    assert repeated_payload["accepted"] is False
    assert repeated_payload["status"] == "cancelled"
    assert repeated_payload["job"]["cancel_requested"] is True
