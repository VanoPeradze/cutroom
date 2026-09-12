from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom.config import load_settings
from cutroom.media import copy_upload
from server import JSON_BODY_LIMIT, create_app


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    settings.raw["host"] = "127.0.0.1"
    application = create_app(settings)
    application.config.update(TESTING=True)
    return application


class _DummyJob:
    def public(self) -> dict[str, object]:
        return {"id": "job_test", "status": "queued", "progress": 0.0}


def _source_record(relative_path: str, name: str = "old.mp4") -> dict[str, object]:
    return {
        "slot": "A",
        "name": name,
        "relative_path": relative_path,
        "duration": 10.0,
        "width": 1280,
        "height": 720,
        "has_audio": False,
        "browser_ready": True,
        "preview_relative_path": "cache/proxy-A.mp4",
        "preparation": "ready",
    }


def _probe_result(size: int) -> dict[str, object]:
    return {
        "duration": 12.0,
        "width": 1920,
        "height": 1080,
        "rotation": 0,
        "fps": 30.0,
        "video_codec": "h264",
        "audio_codec": "aac",
        "has_audio": True,
        "format": "mov,mp4,m4a,3gp,3g2,mj2",
        "size": size,
        "browser_ready": True,
        "mime": "video/mp4",
    }


def test_encoded_dot_project_ids_cannot_delete_data(app):
    client = app.test_client()
    settings = app.extensions["cutroom_settings"]
    data_marker = settings.data_dir / "keep.txt"
    projects_marker = settings.projects_dir / "keep.txt"
    data_marker.write_text("data", encoding="utf-8")
    projects_marker.write_text("projects", encoding="utf-8")

    for project_id in ("%2e", "%2e%2e"):
        response = client.delete(f"/api/projects/{project_id}")
        assert response.status_code == 404
        assert response.get_json()["error"] == "not_found"
        assert data_marker.read_text(encoding="utf-8") == "data"
        assert projects_marker.read_text(encoding="utf-8") == "projects"


def test_delete_requires_project_json_even_for_canonical_id(app):
    client = app.test_client()
    settings = app.extensions["cutroom_settings"]
    directory = settings.projects_dir / "project_deadbeefdead"
    directory.mkdir()
    marker = directory / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    response = client.delete("/api/projects/project_deadbeefdead")

    assert response.status_code == 404
    assert marker.exists()


def test_failed_probe_rolls_back_upload_and_keeps_old_project_state(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("rollback")
    project_root = store.project_dir(project["id"])
    destination = project_root / "media" / "source-A.mp4"
    destination.write_bytes(b"OLD_VALID_MEDIA")
    preview = project_root / "cache" / "proxy-A.mp4"
    preview.write_bytes(b"OLD_PREVIEW")
    project["sources"]["A"] = _source_record("media/source-A.mp4")
    project["analysis"] = {"old": True}
    project["draft"] = {"status": "ready"}
    store.save(project)
    monkeypatch.setattr("server.probe_media", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad media")))

    response = client.post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"NEW_INVALID_MEDIA"), "new.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 422
    assert response.get_json()["error"] == "invalid_media"
    assert destination.read_bytes() == b"OLD_VALID_MEDIA"
    assert preview.read_bytes() == b"OLD_PREVIEW"
    saved = store.load(project["id"])
    assert saved["sources"]["A"]["name"] == "old.mp4"
    assert saved["analysis"] == {"old": True}
    assert saved["draft"] == {"status": "ready"}
    assert not list((project_root / "media").glob(".upload-*"))
    assert not list((project_root / "media").glob("*.partial"))
    assert not list((project_root / "media").glob("*.backup"))


def test_successful_upload_commits_then_removes_superseded_assets(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("replace")
    project_root = store.project_dir(project["id"])
    old_source = project_root / "media" / "source-A.mov"
    old_source.write_bytes(b"OLD_MEDIA")
    old_preview = project_root / "cache" / "proxy-A.mp4"
    old_preview.write_bytes(b"OLD_PREVIEW")
    thumbnails = project_root / "cache" / "thumbnails-A"
    thumbnails.mkdir()
    (thumbnails / "thumb-001.jpg").write_bytes(b"OLD_THUMB")
    project["sources"]["A"] = _source_record("media/source-A.mov", "old.mov")
    store.save(project)
    monkeypatch.setattr("server.probe_media", lambda path, _settings: _probe_result(path.stat().st_size))
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _DummyJob())

    response = client.post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"NEW_VALID_MEDIA"), "new.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    new_source = project_root / "media" / "source-A.mp4"
    assert new_source.read_bytes() == b"NEW_VALID_MEDIA"
    assert not old_source.exists()
    assert not old_preview.exists()
    assert not thumbnails.exists()
    saved = store.load(project["id"])
    assert saved["sources"]["A"]["name"] == "new.mp4"
    assert saved["analysis"] is None
    assert saved["draft"] is None


def test_project_save_failure_restores_previous_media(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("save rollback")
    project_root = store.project_dir(project["id"])
    destination = project_root / "media" / "source-A.mp4"
    destination.write_bytes(b"OLD_MEDIA")
    project["sources"]["A"] = _source_record("media/source-A.mp4")
    store.save(project)
    monkeypatch.setattr("server.probe_media", lambda path, _settings: _probe_result(path.stat().st_size))
    monkeypatch.setattr(store, "_save_unlocked", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("save failed")))

    response = client.post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"NEW_MEDIA"), "new.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 500
    assert destination.read_bytes() == b"OLD_MEDIA"
    saved = store.load(project["id"])
    assert saved["sources"]["A"]["name"] == "old.mp4"
    assert not list((project_root / "media").glob(".upload-*"))
    assert not list((project_root / "media").glob("*.backup"))


def test_copy_upload_removes_unique_partial_on_any_failure(tmp_path: Path):
    class BrokenStream:
        calls = 0

        def read(self, _size: int) -> bytes:
            self.calls += 1
            if self.calls == 1:
                return b"partial bytes"
            raise OSError("simulated interrupted upload")

    destination = tmp_path / "source-A.mp4"
    with pytest.raises(OSError, match="interrupted"):
        copy_upload(SimpleNamespace(stream=BrokenStream()), destination, 1024)

    assert not destination.exists()
    assert not list(tmp_path.iterdir())


def test_json_endpoints_require_small_object_bodies(app):
    client = app.test_client()

    wrong_type = client.post("/api/projects", json=["not", "an", "object"])
    assert wrong_type.status_code == 400
    assert wrong_type.get_json()["error"] == "invalid_json_type"

    wrong_content_type = client.post("/api/projects", data="name=test", content_type="application/x-www-form-urlencoded")
    assert wrong_content_type.status_code == 415
    assert wrong_content_type.get_json()["error"] == "json_required"

    too_large = client.post("/api/projects", data=b" " * (JSON_BODY_LIMIT + 1), content_type="application/json")
    assert too_large.status_code == 413
    assert too_large.get_json()["error"] == "request_too_large"

    bad_settings = client.post("/api/projects", json={"name": "safe", "unexpected": True})
    assert bad_settings.status_code == 400
    assert bad_settings.get_json()["error"] == "unknown_field"


def test_loopback_host_and_same_origin_are_enforced(app):
    client = app.test_client()

    hostile_host = client.get("/api/projects", headers={"Host": "evil.example"})
    assert hostile_host.status_code == 421
    assert hostile_host.get_json()["error"] == "invalid_host"

    hostile_origin = client.post(
        "/api/projects",
        json={"name": "blocked"},
        headers={"Origin": "https://evil.example"},
    )
    assert hostile_origin.status_code == 403
    assert hostile_origin.get_json()["error"] == "invalid_origin"

    allowed = client.post(
        "/api/projects",
        json={"name": "allowed"},
        headers={"Origin": "http://localhost"},
    )
    assert allowed.status_code == 201


def test_project_update_is_revision_checked_transaction(app):
    store = app.extensions["cutroom_store"]
    project = store.create("transaction")
    original_revision = project["revision"]

    updated = store.update(
        project["id"],
        lambda current: current["settings"].update({"pace": "dynamic"}),
        expected_revision=original_revision,
    )
    assert updated["settings"]["pace"] == "dynamic"
    assert updated["revision"] == original_revision + 1

    with pytest.raises(RuntimeError, match="revision_conflict"):
        store.update(
            project["id"],
            lambda current: current["settings"].update({"pace": "gentle"}),
            expected_revision=original_revision,
        )
    assert store.load(project["id"])["settings"]["pace"] == "dynamic"


def test_patch_api_reports_revision_conflict_without_overwriting(app):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("revision api")
    stale_revision = project["revision"]
    store.patch(project["id"], {"name": "newer value"})

    response = client.patch(
        f"/api/projects/{project['id']}",
        json={"name": "stale value", "expected_revision": stale_revision},
    )

    assert response.status_code == 409
    assert response.get_json()["error"] == "revision_conflict"
    assert store.load(project["id"])["name"] == "newer value"


def test_delete_removes_only_explicitly_referenced_exports(app):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    project = store.create("exports")
    video = settings.exports_dir / "owned-video.mp4"
    captions = settings.exports_dir / "owned-video.srt"
    unrelated = settings.exports_dir / "unrelated.mp4"
    video.write_bytes(b"video")
    captions.write_text("captions", encoding="utf-8")
    unrelated.write_bytes(b"keep")
    project["exports"] = [
        {
            "name": video.name,
            "relative_path": video.name,
            "captions_name": captions.name,
        },
        {"name": "../unrelated.mp4"},
    ]
    store.save(project)

    response = client.delete(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert not store.project_dir(project["id"]).exists()
    assert not video.exists()
    assert not captions.exists()
    assert unrelated.read_bytes() == b"keep"
