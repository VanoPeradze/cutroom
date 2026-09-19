from __future__ import annotations

import io
import json
import shutil
import socket
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom.config import load_settings
from cutroom.jobs import Job, JobAdmissionError, JobCancelled, JobContext, JobManager
from cutroom.media import run_command
from cutroom.projects import ProjectStore


@pytest.fixture()
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    settings.raw["host"] = "127.0.0.1"
    settings.raw["job_workers"] = 2
    application = server.create_app(settings)
    application.config.update(TESTING=True)
    yield application
    application.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def _source(slot: str, *, generation: str = "generation-1", has_audio: bool = True) -> dict[str, object]:
    return {
        "slot": slot,
        "name": f"source-{slot}.mp4",
        "generation": generation,
        "relative_path": f"media/source-{slot}.mp4",
        "duration": 12.0,
        "width": 1280,
        "height": 720,
        "has_audio": has_audio,
        "browser_ready": True,
        "preview_relative_path": None,
        "preparation": "queued",
    }


def _probe(path: Path, _settings) -> dict[str, object]:
    return {
        "duration": 12.0,
        "width": 1280,
        "height": 720,
        "rotation": 0,
        "fps": 30.0,
        "video_codec": "h264",
        "audio_codec": "aac",
        "has_audio": True,
        "format": "mp4",
        "size": path.stat().st_size,
        "browser_ready": True,
        "mime": "video/mp4",
    }


class _QueuedJob:
    id = "job_test"
    kind = "prepare_source"
    project_id = None
    dedupe_key = "default"
    status = "queued"

    def public(self) -> dict[str, object]:
        return {"id": self.id, "kind": self.kind, "status": self.status, "progress": 0.0}


@pytest.mark.parametrize("draft_goal,settings_goal", [("youtube", "youtube"), ("short", "youtube"), ("youtube", "short")])
def test_new_variation_requires_an_existing_short_draft(app, monkeypatch, draft_goal, settings_goal):
    store = app.extensions["cutroom_store"]
    project = store.create("variation validation")
    project["sources"]["A"] = _source("A")
    project["settings"]["goal"] = settings_goal
    project["draft"] = {"goal": draft_goal, "keep_ranges": [{"start": 0, "end": 8}]}
    store.save(project)

    def unexpected_submit(*_args, **_kwargs):
        raise AssertionError("An invalid variation must not start background work")

    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", unexpected_submit)
    response = app.test_client().post(
        f"/api/projects/{project['id']}/director/refine", json={"command": "new_variation"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_variation"


def test_new_variation_accepts_an_existing_short_draft(app, monkeypatch):
    store = app.extensions["cutroom_store"]
    project = store.create("short variation")
    project["sources"]["A"] = _source("A")
    project["draft"] = {"goal": "short", "keep_ranges": [{"start": 0, "end": 8}]}
    store.save(project)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())
    response = app.test_client().post(
        f"/api/projects/{project['id']}/director/refine", json={"command": "new_variation"},
    )
    assert response.status_code == 202


@pytest.mark.parametrize("browser_ready", [True, False])
def test_missing_preview_only_falls_back_to_a_playable_original(app, browser_ready):
    store = app.extensions["cutroom_store"]
    project = store.create("preview recovery")
    source = _source("A")
    source.update(browser_ready=browser_ready, preview_relative_path="cache/missing-proxy.mp4")
    project["sources"]["A"] = source
    store.save(project)
    (store.project_dir(project["id"]) / "media" / "source-A.mp4").write_bytes(b"original video")
    response = app.test_client().get(f"/api/projects/{project['id']}/media/A")
    if browser_ready:
        assert response.status_code == 200
        assert response.data == b"original video"
    else:
        assert response.status_code == 404
    response.close()


def test_media_prefers_existing_proxy_and_supports_range_requests(app):
    store = app.extensions["cutroom_store"]
    project = store.create("preview range")
    source = _source("A")
    source["preview_relative_path"] = "cache/proxy-A.mp4"
    project["sources"]["A"] = source
    store.save(project)
    directory = store.project_dir(project["id"])
    (directory / "media" / "source-A.mp4").write_bytes(b"original video")
    (directory / "cache" / "proxy-A.mp4").write_bytes(b"playable proxy")
    response = app.test_client().get(
        f"/api/projects/{project['id']}/media/A", headers={"Range": "bytes=0-3"},
    )
    assert response.status_code == 206
    assert response.data == b"play"
    response.close()


def test_instance_identity_endpoint_is_small_and_does_not_run_dependency_probes(
    app, monkeypatch: pytest.MonkeyPatch
):
    def unexpected_probe(*_args, **_kwargs):
        raise AssertionError("The identity endpoint must not run dependency probes")

    monkeypatch.setattr(server, "_command_ok", unexpected_probe)
    monkeypatch.setattr(server, "_ollama_status", unexpected_probe)
    monkeypatch.setattr(server, "available_encoders", unexpected_probe)

    response = app.test_client().get("/api/instance")

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.data) < server.INSTANCE_RESPONSE_LIMIT
    assert response.get_json() == {
        "service": "cutroom",
        "protocol": server.INSTANCE_PROTOCOL_VERSION,
        "instance_id": server._cutroom_instance_id(app.extensions["cutroom_settings"]),
        "version": server.__version__,
    }


def test_system_endpoint_publishes_the_embedded_camera_detector_contract(
    app, monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(server, "available_encoders", lambda _settings: [])
    monkeypatch.setattr(server, "_model_status", lambda _settings: {})

    response = app.test_client().get("/api/system")

    assert response.status_code == 200
    assert response.get_json()["vision_analysis_version"] == server.VISION_ANALYSIS_VERSION


def test_settings_and_manual_patch_reject_values_that_would_crash_later(app):
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "validation"}).get_json()["project"]
    endpoint = f"/api/projects/{project['id']}"

    invalid_settings = [
        {"goal": "invented"},
        {"resolution": "99999"},
        {"performance_mode": "infinite"},
        {"spoken_language": "../../model"},
        {"caption_style": "viral-shell"},
        {"caption_position": "outside"},
        {"caption_scale": 40},
        {"caption_scale": 100.5},
        {"caption_words_per_line": 0},
        {"caption_words_per_line": 4.5},
        {"audio_cleanup": {"normalize": "yes"}},
        {"audio_cleanup": {"silence_min_seconds": "soon"}},
        {"audio_cleanup": {"target_lufs": 12}},
    ]
    for settings in invalid_settings:
        response = client.patch(endpoint, json={"settings": settings})
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_field"

    malformed_manual = [
        {"cuts": [{"start": 3, "end": 1}]},
        {"keep_ranges": [{"start": "zero", "end": 1}]},
        {"camera_plan": [{"start": 0, "end": 1, "camera": "shell"}]},
        {"crop": {"A": {"zoom": 99}}},
        {"crop": {"../../outside": {"x": 0.5}}},
    ]
    for manual in malformed_manual:
        response = client.patch(endpoint, json={"manual": manual})
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_field"

    source_aspect = client.patch(endpoint, json={"settings": {"aspect": "source"}})
    assert source_aspect.status_code == 200
    assert source_aspect.get_json()["project"]["settings"]["aspect"] == "source"

    caption_controls = client.patch(endpoint, json={"settings": {
        "caption_style": "boxed",
        "caption_position": "top",
        "caption_scale": 125,
        "caption_words_per_line": 4,
    }})
    assert caption_controls.status_code == 200
    saved_caption_settings = caption_controls.get_json()["project"]["settings"]
    assert {
        key: saved_caption_settings[key]
        for key in ("caption_style", "caption_position", "caption_scale", "caption_words_per_line")
    } == {
        "caption_style": "boxed",
        "caption_position": "top",
        "caption_scale": 125,
        "caption_words_per_line": 4,
    }


def test_malformed_origin_port_is_rejected_without_server_error(app):
    response = app.test_client().post(
        "/api/projects",
        json={"name": "blocked"},
        headers={"Origin": "http://localhost:not-a-port"},
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "invalid_origin"


def test_blank_project_name_uses_a_visible_default(app):
    response = app.test_client().post("/api/projects", json={"name": "   "})
    assert response.status_code == 201
    assert response.get_json()["project"]["name"] == "Untitled project"


@pytest.mark.parametrize("port", ["1", "43210", "65535"])
def test_cutroom_port_environment_override_accepts_safe_tcp_ports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    port: str,
):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_PORT", port)

    settings = load_settings(tmp_path / "missing-config.json")

    assert settings.raw["port"] == int(port)


@pytest.mark.parametrize("port", ["", "0", "65536", "-1", "8765.5", "not-a-port"])
def test_cutroom_port_environment_override_rejects_invalid_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    port: str,
):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_PORT", port)

    with pytest.raises(ValueError, match="CUTROOM_PORT.*1 and 65535"):
        load_settings(tmp_path / "missing-config.json")


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "example.com", "::"])
def test_create_app_refuses_non_loopback_bind_without_authentication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    host: str,
):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings(tmp_path / "missing-config.json")
    settings.raw["host"] = host

    with pytest.raises(ValueError, match="no remote authentication.*loopback host"):
        server.create_app(settings)


@pytest.mark.parametrize("model", ["--help", "../outside", "/absolute", "team//model"])
def test_model_install_rejects_option_and_path_like_names(app, model: str):
    response = app.test_client().post("/api/models/install", json={"kind": "editor", "model": model})
    assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_model"


def test_source_a_change_clears_all_manual_state_and_private_history(app):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("source A reset")
    project["sources"]["A"] = _source("A")
    project["manual"] = {
        "cuts": [{"start": 1, "end": 2}],
        "keep_ranges": [{"start": 0, "end": 1}],
        "keeps": [{"start": 3, "end": 4}],
        "camera_plan": [{"start": 0, "end": 1, "camera": "A"}],
        "camera_overrides": [{"start": 0, "end": 1, "layout": "screen"}],
        "source_mixer": {"screen_slot": "B", "camera_slot": "A", "primary_role": "camera", "audio_slot": "B", "sync_offset": 1.5, "default_layout": "stacked"},
        "crop": {"A": {"x": 0.2, "y": 0.4, "zoom": 2}, "B": {"x": 0.7}},
        "_history": {"undo": [{"old": True}], "redo": []},
        "history": {"undo_count": 1, "redo_count": 0},
    }
    store.save(project)
    (store.project_dir(project["id"]) / "media" / "source-A.mp4").write_bytes(b"old")

    response = client.delete(f"/api/projects/{project['id']}/sources/A")

    assert response.status_code == 200
    saved = store.load(project["id"])
    assert saved["manual"]["cuts"] == []
    assert saved["manual"]["keep_ranges"] == []
    assert saved["manual"]["keeps"] == []
    assert saved["manual"]["camera_plan"] == []
    assert saved["manual"]["camera_overrides"] == []
    assert saved["manual"]["crop"] == {}
    assert "sync_offset" not in saved["manual"]["source_mixer"]
    assert "default_layout" not in saved["manual"]["source_mixer"]
    assert "_history" not in saved["manual"]
    assert saved["manual"]["history"] == {"undo_count": 0, "redo_count": 0}


def test_source_b_change_preserves_a_cuts_but_resets_b_specific_decisions(app):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("source B reset")
    project["sources"]["A"] = _source("A")
    project["sources"]["B"] = _source("B")
    project["manual"] = {
        "cuts": [{"start": 1, "end": 2}],
        "keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 12}],
        "keeps": [{"start": 3, "end": 4}],
        "camera_plan": [{"start": 0, "end": 12, "camera": "stacked"}],
        "camera_overrides": [{"start": 0, "end": 12, "layout": "stacked"}],
        "source_mixer": {"screen_slot": "B", "camera_slot": "A", "primary_role": "camera", "audio_slot": "B", "sync_offset": -0.4, "default_layout": "pip"},
        "crop": {"A": {"x": 0.2, "y": 0.4, "zoom": 1.5}, "B": {"x": 0.7, "zoom": 2}},
        "_history": {"undo": [{"old": True}], "redo": []},
    }
    store.save(project)
    (store.project_dir(project["id"]) / "media" / "source-B.mp4").write_bytes(b"old")

    response = client.delete(f"/api/projects/{project['id']}/sources/B")

    assert response.status_code == 200
    manual = store.load(project["id"])["manual"]
    assert manual["cuts"] == [{"start": 1, "end": 2}]
    assert manual["keep_ranges"] == [{"start": 0, "end": 1}, {"start": 2, "end": 12}]
    assert manual["keeps"] == [{"start": 3, "end": 4}]
    assert manual["camera_plan"] == []
    assert manual["camera_overrides"] == []
    assert manual["crop"] == {"A": {"x": 0.2, "y": 0.4, "zoom": 1.5}}
    assert manual["source_mixer"] == {"screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A"}
    assert "_history" not in manual


def test_second_upload_infers_reversed_screen_and_camera_roles(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()
    project = app.extensions["cutroom_store"].create("inferred roles")

    def probe(path: Path, _settings) -> dict[str, object]:
        is_camera = path.read_bytes() == b"face"
        return {
            **_probe(path, _settings),
            "width": 720 if is_camera else 1920,
            "height": 1280 if is_camera else 1080,
        }

    monkeypatch.setattr(server, "probe_media", probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())
    first = client.post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"face"), "creator-facecam.mp4")},
        content_type="multipart/form-data",
    )
    # A real second source supersedes a previously marked facecam baked into A.
    # The stale single-source layout must not hide the newly uploaded footage.
    marked = app.extensions["cutroom_store"].load(project["id"])
    marked["manual"]["embedded_camera"] = {
        "x": .7, "y": .05, "w": .25, "h": .25,
        "content_focus": {"x": .3, "y": .55},
    }
    marked["settings"]["layout"] = "embedded_stack"
    app.extensions["cutroom_store"].save(marked)
    second = client.post(
        f"/api/projects/{project['id']}/sources/B",
        data={"file": (io.BytesIO(b"wide-screen"), "OBS-gameplay-screen.mp4")},
        content_type="multipart/form-data",
    )

    assert first.status_code == 201
    assert second.status_code == 201
    payload = second.get_json()["project"]
    assert payload["sources"]["A"]["name"] == "creator-facecam.mp4"
    assert payload["sources"]["B"]["name"] == "OBS-gameplay-screen.mp4"
    assert "embedded_camera" not in payload["manual"]
    assert payload["settings"]["layout"] == "auto"
    assert payload["manual"]["source_mixer"] == {
        "screen_slot": "B",
        "camera_slot": "A",
        "primary_role": "screen",
        "audio_slot": "A",
        "first_slot": "A",
    }


def test_replacing_b_preserves_valid_routing_and_order_but_clears_b_timing(app, monkeypatch: pytest.MonkeyPatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("replace B routing")
    project["sources"]["A"] = {**_source("A"), "name": "camera-A.mp4"}
    project["sources"]["B"] = {**_source("B", generation="old-B"), "name": "screen-B.mp4"}
    project["manual"] = {
        "cuts": [{"start": 1, "end": 2}],
        "keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 12}],
        "camera_plan": [{"start": 0, "end": 12, "camera": "stacked"}],
        "camera_overrides": [{"start": 0, "end": 12, "layout": "stacked"}],
        "source_mixer": {
            "screen_slot": "B", "camera_slot": "A", "primary_role": "camera",
            "audio_slot": "B", "first_slot": "B", "sync_offset": 2.4, "default_layout": "pip",
        },
        "crop": {"A": {"x": 0.2, "y": 0.4, "zoom": 1.5}, "B": {"x": 0.7, "zoom": 2}},
        "_history": {"undo": [{"old": True}], "redo": []},
    }
    store.save(project)
    old_b = store.project_dir(project["id"]) / "media" / "source-B.mp4"
    old_b.write_bytes(b"old B")
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())

    response = client.post(
        f"/api/projects/{project['id']}/sources/B",
        data={"file": (io.BytesIO(b"new B"), "replacement-screen.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    manual = store.load(project["id"])["manual"]
    assert manual["cuts"] == [{"start": 1, "end": 2}]
    assert manual["keep_ranges"] == [{"start": 0, "end": 1}, {"start": 2, "end": 12}]
    assert manual["camera_overrides"] == []
    assert manual["camera_plan"] == []
    assert manual["crop"] == {"A": {"x": 0.2, "y": 0.4, "zoom": 1.5}}
    assert manual["source_mixer"] == {
        "screen_slot": "B", "camera_slot": "A", "primary_role": "camera",
        "audio_slot": "B", "first_slot": "B", "default_layout": "pip",
    }
    assert "_history" not in manual


def test_project_media_rejects_tampered_relative_path(app, tmp_path: Path):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    project = store.create("path containment")
    secret = tmp_path / "secret.mp4"
    secret.write_bytes(b"DO NOT SERVE")
    source = _source("A")
    source["relative_path"] = str(secret)
    project["sources"]["A"] = source
    store.save(project)

    response = client.get(f"/api/projects/{project['id']}/media/A")

    assert response.status_code == 409
    assert response.get_json()["error"] == "corrupt_project"
    assert b"DO NOT SERVE" not in response.data


def test_windows_source_paths_are_normalized_for_cross_platform_projects(app):
    store = app.extensions["cutroom_store"]
    project = store.create("portable paths")
    source = _source("A")
    source["relative_path"] = r"media\source-A.mp4"
    source["preview_relative_path"] = r"cache\proxy-A.mp4"
    project["sources"]["A"] = source
    store.save(project)

    loaded = store.load(project["id"])["sources"]["A"]

    assert loaded["relative_path"] == "media/source-A.mp4"
    assert loaded["preview_relative_path"] == "cache/proxy-A.mp4"


def test_corrupt_or_mismatched_project_state_is_not_exposed_or_listed(app):
    client = app.test_client()
    settings = app.extensions["cutroom_settings"]
    project_id = "project_deadbeefdead"
    directory = settings.projects_dir / project_id
    directory.mkdir()
    (directory / "project.json").write_text(json.dumps({"id": "project_aaaaaaaaaaaa", "name": "wrong"}), encoding="utf-8")

    listed = client.get("/api/projects").get_json()["projects"]
    response = client.get(f"/api/projects/{project_id}")

    assert all(row["id"] != project_id for row in listed)
    assert response.status_code == 409
    assert response.get_json()["error"] == "corrupt_project"


def test_failed_initial_project_save_removes_ghost_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    monkeypatch.setattr("cutroom.projects.atomic_write_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        store.create("must roll back")

    assert list(settings.projects_dir.glob("project_*")) == []


def test_project_delete_reports_success_after_atomic_rename_when_export_is_windows_locked(
    app, monkeypatch: pytest.MonkeyPatch
):
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    project = store.create("locked export deletion")
    export = settings.exports_dir / "locked-export.mp4"
    export.write_bytes(b"video")
    project["exports"] = [{"name": export.name, "relative_path": export.name}]
    store.save(project)
    project_directory = store.project_dir(project["id"])
    original_unlink = Path.unlink

    def windows_locked_unlink(path: Path, *args, **kwargs):
        if path.resolve() == export.resolve():
            raise PermissionError("file is open")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", windows_locked_unlink)

    response = app.test_client().delete(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert response.get_json() == {"ok": True}
    assert not project_directory.exists()
    assert all(item["id"] != project["id"] for item in store.list())
    assert export.exists(), "locked export cleanup is best-effort after project deletion"
    assert project["id"] not in store._project_locks


def test_project_delete_rename_failure_keeps_complete_project_and_exports_retryable(
    app, monkeypatch: pytest.MonkeyPatch
):
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    project = store.create("rename failure")
    export = settings.exports_dir / "rename-failure.mp4"
    export.write_bytes(b"video")
    project["exports"] = [{"name": export.name}]
    store.save(project)
    project_directory = store.project_dir(project["id"])
    original_replace = Path.replace

    def windows_locked_replace(path: Path, target: Path):
        if path.resolve() == project_directory.resolve():
            raise PermissionError("source media is still open")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", windows_locked_replace)

    response = app.test_client().delete(f"/api/projects/{project['id']}")

    assert response.status_code == 409
    assert response.get_json()["error"] == "project_files_busy"
    assert project_directory.is_dir()
    assert store.load(project["id"])["name"] == "rename failure"
    assert export.read_bytes() == b"video"


def test_project_delete_stages_locked_directory_and_next_store_startup_retries_cleanup(
    app, monkeypatch: pytest.MonkeyPatch
):
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    project = store.create("staged cleanup")
    project_directory = store.project_dir(project["id"])
    original_rmtree = shutil.rmtree

    def windows_locked_rmtree(path: Path, *args, **kwargs):
        candidate = Path(path).resolve()
        if candidate.parent == store._deleted_projects_dir and not kwargs.get("ignore_errors", False):
            raise PermissionError("range request is still closing")
        return original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr("cutroom.projects.shutil.rmtree", windows_locked_rmtree)

    response = app.test_client().delete(f"/api/projects/{project['id']}")

    assert response.status_code == 200
    assert not project_directory.exists()
    staged = list(store._deleted_projects_dir.iterdir())
    assert len(staged) == 1 and staged[0].is_dir()

    monkeypatch.setattr("cutroom.projects.shutil.rmtree", original_rmtree)
    ProjectStore(settings)
    assert list(store._deleted_projects_dir.iterdir()) == []


def test_failed_save_does_not_mutate_callers_revision_or_timestamp(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("copy on save")
    candidate = store.load(project["id"])
    original_revision = candidate["revision"]
    original_updated_at = candidate["updated_at"]
    monkeypatch.setattr("cutroom.projects.atomic_write_json", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError, match="disk full"):
        store.save(candidate)

    assert candidate["revision"] == original_revision
    assert candidate["updated_at"] == original_updated_at


def test_concurrent_project_updates_are_serialized_without_lost_writes(app):
    store = app.extensions["cutroom_store"]
    project = store.create("concurrent saves")
    workers = 8
    writes = 64

    def append(index: int) -> None:
        store.update(project["id"], lambda current: current.setdefault("exports", []).append({"id": index}))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(append, range(writes)))

    saved = store.load(project["id"])
    assert sorted(row["id"] for row in saved["exports"]) == list(range(writes))
    assert saved["revision"] == project["revision"] + writes


def test_missing_project_requests_do_not_retain_unbounded_lock_keys(app):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    before = len(store._project_locks)

    for index in range(40):
        project_id = f"project_{index:012x}"
        response = client.get(f"/api/projects/{project_id}")
        assert response.status_code == 404

    assert len(store._project_locks) == before


def test_preparation_failure_and_cancellation_leave_retryable_source_state(app):
    store = app.extensions["cutroom_store"]
    project = store.create("preparation state")
    project["sources"]["A"] = _source("A", generation="failed-generation")
    store.save(project)

    failed_context = JobContext(Job("job_failed", "prepare_source", project["id"]), threading.Lock())
    with pytest.raises(RuntimeError, match="missing or outside"):
        server._prepare_source(failed_context, project["id"], "A", "failed-generation", store, app.extensions["cutroom_settings"])
    failed = store.load(project["id"])["sources"]["A"]
    assert failed["preparation"] == "failed"
    assert "Source media path" in failed["preparation_error"]

    path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    path.write_bytes(b"media")
    current = store.load(project["id"])
    current["sources"]["A"]["generation"] = "cancel-generation"
    current["sources"]["A"]["preparation"] = "queued"
    store.save(current)
    cancelled_job = Job("job_cancelled", "prepare_source", project["id"])
    cancelled_job.cancel_event.set()
    cancelled_context = JobContext(cancelled_job, threading.Lock())
    with pytest.raises(JobCancelled):
        server._prepare_source(cancelled_context, project["id"], "A", "cancel-generation", store, app.extensions["cutroom_settings"])
    cancelled = store.load(project["id"])["sources"]["A"]
    assert cancelled["preparation"] == "cancelled"
    assert "preparation_error" not in cancelled


def test_source_preparation_forwards_cancellation_to_proxy_and_thumbnails(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("preparation cancellation wiring")
    source = _source("A", generation="wired-generation", has_audio=False)
    source["browser_ready"] = False
    project["sources"]["A"] = source
    store.save(project)
    source_path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source_path.write_bytes(b"media")
    callbacks = []

    def fake_proxy(_source_path, target, _settings, progress=None, cancel_check=None):
        assert callable(progress)
        assert callable(cancel_check)
        callbacks.append(cancel_check)
        cancel_check()
        target.write_bytes(b"proxy")
        progress(1.0, "ready")
        return target

    def fake_thumbnails(_source_path, output_dir, _duration, _settings, count=12, cancel_check=None):
        assert count == 12
        assert callable(cancel_check)
        callbacks.append(cancel_check)
        cancel_check()
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "thumb-001.jpg").write_bytes(b"thumb")
        return ["thumb-001.jpg"]

    monkeypatch.setattr(server, "create_proxy", fake_proxy)
    monkeypatch.setattr(server, "extract_thumbnails", fake_thumbnails)
    context = JobContext(Job("job_wired", "prepare_source", project["id"]), threading.Lock())

    result = server._prepare_source(
        context,
        project["id"],
        "A",
        "wired-generation",
        store,
        app.extensions["cutroom_settings"],
    )

    assert len(callbacks) == 2
    assert Path(result["preview"]) == Path("cache/proxy-A.mp4")
    assert result["thumbnails"] == ["thumb-001.jpg"]
    assert context.committed is True
    assert store.load(project["id"])["sources"]["A"]["preparation"] == "ready"


def test_source_a_preparation_persists_generation_bound_embedded_camera_suggestion(
    app, monkeypatch: pytest.MonkeyPatch,
):
    store = app.extensions["cutroom_store"]
    project = store.create("embedded camera pre-analysis")
    generation = "vision-generation"
    project["sources"]["A"] = _source("A", generation=generation, has_audio=False)
    store.save(project)
    source_path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source_path.write_bytes(b"media")
    callbacks = []

    def fake_vision(path, duration, progress=None, samples=24, cancel_check=None):
        assert path == source_path
        assert duration == 12.0
        assert samples >= 10
        assert callable(cancel_check)
        callbacks.append(cancel_check)
        cancel_check()
        if progress:
            progress(1.0, "camera ready")
        return {
            "version": server.VISION_ANALYSIS_VERSION,
            "available": True,
            "focus": {"x": 0.3, "y": 0.5},
            "embedded_camera": {
                "x": 0.718,
                "y": 0.314,
                "w": 0.249,
                "h": 0.249,
                "confidence": 0.86,
                "requires_confirmation": True,
                "auto_safe": False,
            },
        }

    def fake_thumbnails(_path, output_dir, _duration, _settings, count=12, cancel_check=None):
        assert callable(cancel_check)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "thumb-001.jpg").write_bytes(b"thumb")
        return ["thumb-001.jpg"]

    monkeypatch.setattr(server, "analyze_faces_and_embedded_camera", fake_vision)
    monkeypatch.setattr(server, "extract_thumbnails", fake_thumbnails)
    context = JobContext(Job("job_vision", "prepare_source", project["id"]), threading.Lock())

    result = server._prepare_source(
        context,
        project["id"],
        "A",
        generation,
        store,
        app.extensions["cutroom_settings"],
    )

    saved = store.load(project["id"])
    profile = saved["pre_analysis"]["vision"]["A"]
    assert len(callbacks) == 1
    assert profile["version"] == server.VISION_ANALYSIS_VERSION
    assert profile["source_generation"] == generation
    assert profile["sample_count"] == 12
    assert profile["profile"] == "lite"
    assert profile["embedded_camera"]["requires_confirmation"] is True
    assert profile["embedded_camera"]["auto_safe"] is False
    assert saved["sources"]["A"]["embedded_camera_detected"] is True
    assert result["embedded_camera_detected"] is True


def test_source_replacement_during_camera_detection_cannot_publish_stale_pre_analysis(
    app, monkeypatch: pytest.MonkeyPatch,
):
    store = app.extensions["cutroom_store"]
    project = store.create("stale embedded camera pre-analysis")
    old_generation = "old-vision-generation"
    project["sources"]["A"] = _source("A", generation=old_generation, has_audio=False)
    store.save(project)
    source_path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source_path.write_bytes(b"media")

    def replace_source_during_detection(_path, _duration, **_kwargs):
        store.update(
            project["id"],
            lambda current: current["sources"]["A"].update({
                "generation": "new-vision-generation",
                "preparation": "queued",
            }),
        )
        return {
            "version": server.VISION_ANALYSIS_VERSION,
            "available": True,
            "embedded_camera": {
                "x": 0.718, "y": 0.314, "w": 0.249, "h": 0.249,
                "confidence": 0.86,
            },
        }

    monkeypatch.setattr(server, "analyze_faces_and_embedded_camera", replace_source_during_detection)
    context = JobContext(Job("job_stale_vision", "prepare_source", project["id"]), threading.Lock())

    with pytest.raises(JobCancelled, match="replaced during camera detection"):
        server._prepare_source(
            context,
            project["id"],
            "A",
            old_generation,
            store,
            app.extensions["cutroom_settings"],
        )

    saved = store.load(project["id"])
    assert saved["sources"]["A"]["generation"] == "new-vision-generation"
    assert saved["sources"]["A"]["preparation"] == "queued"
    assert saved.get("pre_analysis", {}).get("vision", {}).get("A") is None


def test_source_preparation_reuses_complete_proxy_and_timeline_cache(
    app, monkeypatch: pytest.MonkeyPatch,
):
    store = app.extensions["cutroom_store"]
    project = store.create("cached source preparation")
    generation = "cached-preparation-generation"
    source = _source("A", generation=generation, has_audio=False)
    source.update({
        "browser_ready": False,
        "preview_relative_path": "cache/proxy-A.mp4",
        "thumbnail_names": [f"thumb-{index:03d}.jpg" for index in range(1, 13)],
    })
    project["sources"]["A"] = source
    store.save(project)

    project_dir = store.project_dir(project["id"])
    (project_dir / "media" / "source-A.mp4").write_bytes(b"media")
    (project_dir / "cache" / "proxy-A.mp4").write_bytes(b"proxy")
    thumbnail_dir = project_dir / "cache" / "thumbnails-A"
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    for name in source["thumbnail_names"]:
        (thumbnail_dir / name).write_bytes(b"thumb")

    monkeypatch.setattr(server, "analyze_faces_and_embedded_camera", lambda *_args, **_kwargs: {
        "version": server.VISION_ANALYSIS_VERSION,
        "available": True,
        "embedded_camera": None,
    })
    monkeypatch.setattr(server, "create_proxy", lambda *_args, **_kwargs: pytest.fail("cached proxy was regenerated"))
    monkeypatch.setattr(server, "extract_thumbnails", lambda *_args, **_kwargs: pytest.fail("cached thumbnails were regenerated"))

    context = JobContext(Job("job_cached_assets", "prepare_source", project["id"]), threading.Lock())
    result = server._prepare_source(
        context,
        project["id"],
        "A",
        generation,
        store,
        app.extensions["cutroom_settings"],
    )

    assert result["preview"] == "cache/proxy-A.mp4"
    assert result["thumbnails"] == source["thumbnail_names"]
    saved = store.load(project["id"])["sources"]["A"]
    assert saved["preparation"] == "ready"
    assert saved["preview_relative_path"] == "cache/proxy-A.mp4"


def test_foreground_admission_is_atomic_across_director_and_render(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("foreground gate")
    project["sources"]["A"] = _source("A")
    project["draft"] = {"keep_ranges": [{"start": 0, "end": 1}], "camera_plan": [{"start": 0, "end": 1, "camera": "A"}]}
    store.save(project)
    started = threading.Event()
    release = threading.Event()

    def blocked(_context, *_args, **_kwargs):
        started.set()
        release.wait(2)
        return {"ok": True}

    monkeypatch.setattr(server, "analyze_project", blocked)
    monkeypatch.setattr(server, "render_project", blocked)
    barrier = threading.Barrier(2)

    def request(path: str, body: dict[str, object]):
        with app.test_client() as client:
            barrier.wait(timeout=1)
            return client.post(path, json=body)

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            director = pool.submit(request, f"/api/projects/{project['id']}/director", {"goal": "clean"})
            render = pool.submit(request, f"/api/projects/{project['id']}/render", {})
            first = director.result(timeout=2)
            second = render.result(timeout=2)
        assert sorted([first.status_code, second.status_code]) == [202, 409]
        conflict = first if first.status_code == 409 else second
        assert conflict.get_json()["error"] == "job_conflict"
        assert started.wait(1)
    finally:
        release.set()


def test_render_rejects_insufficient_storage_before_job_admission(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("render disk guard")
    project["sources"]["A"] = _source("A")
    project["draft"] = {
        "keep_ranges": [{"start": 0, "end": 1}],
        "camera_plan": [{"start": 0, "end": 1, "camera": "A"}],
    }
    store.save(project)

    def reject_storage(*_args, **_kwargs):
        raise server.InsufficientStorageError(
            required_bytes=800_000_000,
            free_bytes=120_000_000,
            location=store.project_dir(project["id"]),
        )

    monkeypatch.setattr(server, "ensure_render_storage", reject_storage)
    monkeypatch.setattr(
        app.extensions["cutroom_jobs"],
        "submit",
        lambda *_args, **_kwargs: pytest.fail("render must not be admitted without storage"),
    )

    response = app.test_client().post(f"/api/projects/{project['id']}/render", json={})

    assert response.status_code == 507
    payload = response.get_json()
    assert payload["error"] == "insufficient_storage"
    assert payload["required_free_bytes"] == 800_000_000
    assert payload["disk_free_bytes"] == 120_000_000
    assert payload["shortfall_bytes"] == 680_000_000


def test_render_rejects_stale_caption_timeline_before_job_admission(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("stale caption guard")
    project["sources"]["A"] = _source("A")
    project["draft"] = {
        "keep_ranges": [{"start": 0, "end": 1}],
        "camera_plan": [{"start": 0, "end": 1, "camera": "A"}],
    }
    store.save(project)
    monkeypatch.setattr(
        server,
        "ensure_render_storage",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("captions_out_of_date")),
    )
    monkeypatch.setattr(
        app.extensions["cutroom_jobs"],
        "submit",
        lambda *_args, **_kwargs: pytest.fail("stale captions must not enter the render queue"),
    )

    response = app.test_client().post(f"/api/projects/{project['id']}/render", json={})

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["error"] == "captions_out_of_date"
    assert "Rebuild the Draft" in payload["message"]


def test_director_retries_deduplicate_only_the_exact_same_revision_and_request(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("director identity")
    project["sources"]["A"] = _source("A")
    store.save(project)
    release = threading.Event()

    def blocked(context: JobContext, *_args, **_kwargs):
        while not release.wait(0.01):
            context.checkpoint()
        return {"ok": True}

    monkeypatch.setattr(server, "analyze_project", blocked)
    client = app.test_client()
    try:
        first = client.post(f"/api/projects/{project['id']}/director", json={"goal": "clean", "pace": "balanced"})
        duplicate = client.post(f"/api/projects/{project['id']}/director", json={"goal": "clean", "pace": "balanced"})
        changed = client.post(f"/api/projects/{project['id']}/director", json={"goal": "clean", "pace": "dynamic"})

        assert first.status_code == 202
        assert duplicate.status_code == 202
        assert duplicate.get_json()["job"]["id"] == first.get_json()["job"]["id"]
        assert changed.status_code == 409
        assert changed.get_json()["error"] == "job_conflict"
    finally:
        release.set()


def test_source_cleanup_is_serialized_against_a_concurrent_upload(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("source gate")
    project["sources"]["A"] = _source("A", generation="old")
    store.save(project)
    old_path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    old_path.write_bytes(b"old")
    cleanup_entered = threading.Event()
    release_cleanup = threading.Event()
    original_cleanup = server._cleanup_old_source
    calls = 0
    calls_lock = threading.Lock()

    def blocked_cleanup(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
            call = calls
        if call == 1:
            cleanup_entered.set()
            assert release_cleanup.wait(2)
        return original_cleanup(*args, **kwargs)

    monkeypatch.setattr(server, "_cleanup_old_source", blocked_cleanup)
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())

    def remove():
        with app.test_client() as client:
            return client.delete(f"/api/projects/{project['id']}/sources/A")

    def upload():
        with app.test_client() as client:
            return client.post(
                f"/api/projects/{project['id']}/sources/A",
                data={"file": (io.BytesIO(b"new"), "new.mp4")},
                content_type="multipart/form-data",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        removing = pool.submit(remove)
        assert cleanup_entered.wait(1)
        uploading = pool.submit(upload)
        time.sleep(0.1)
        assert not uploading.done(), "upload must not commit while old-source cleanup is in progress"
        release_cleanup.set()
        assert removing.result(timeout=2).status_code == 200
        assert uploading.result(timeout=2).status_code == 201

    saved = store.load(project["id"])
    assert saved["sources"]["A"]["name"] == "new.mp4"
    assert old_path.read_bytes() == b"new"


def test_project_delete_is_blocked_while_upload_is_writing_staging_data(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("upload deletion gate")
    entered_copy = threading.Event()
    release_copy = threading.Event()

    def blocked_copy(uploaded, destination, _max_bytes):
        destination.write_bytes(uploaded.stream.read())
        entered_copy.set()
        assert release_copy.wait(2)
        return destination.stat().st_size

    monkeypatch.setattr(server, "copy_upload", blocked_copy)
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())

    def upload():
        with app.test_client() as client:
            return client.post(
                f"/api/projects/{project['id']}/sources/A",
                data={"file": (io.BytesIO(b"media"), "source.mp4")},
                content_type="multipart/form-data",
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending_upload = pool.submit(upload)
        assert entered_copy.wait(1)
        deletion = app.test_client().delete(f"/api/projects/{project['id']}")
        assert deletion.status_code == 409
        assert deletion.get_json()["error"] == "project_busy"
        assert store.project_dir(project["id"]).is_dir()
        release_copy.set()
        assert pending_upload.result(timeout=2).status_code == 201


def test_upload_remains_successful_and_retryable_when_preparation_queue_is_full(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("deferred preparation")
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(
        app.extensions["cutroom_jobs"],
        "submit",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(JobAdmissionError("queue full")),
    )

    response = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"valid"), "source.mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["job"] is None
    assert payload["preparation_deferred"] is True
    assert "relative_path" not in payload["source"]
    assert (store.project_dir(project["id"]) / "media" / "source-A.mp4").read_bytes() == b"valid"
    saved = store.load(project["id"])["sources"]["A"]
    assert saved["preparation"] == "failed"
    assert "queue unavailable" in saved["preparation_error"].lower()


def test_client_upload_cancel_during_probe_prevents_commit(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("cancel import during probe")
    old_path = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    old_path.write_bytes(b"original")
    store.update(
        project["id"],
        lambda current: current["sources"].__setitem__(
            "A",
            _source("A", generation="original-generation"),
        ),
    )
    probe_started = threading.Event()
    release_probe = threading.Event()
    token = "upload_cancel_during_probe_01"

    def blocked_probe(path: Path, settings):
        probe_started.set()
        assert release_probe.wait(2)
        return _probe(path, settings)

    monkeypatch.setattr(server, "probe_media", blocked_probe)
    monkeypatch.setattr(
        app.extensions["cutroom_jobs"],
        "submit",
        lambda *_args, **_kwargs: pytest.fail("cancelled upload must not schedule preparation"),
    )

    def upload():
        with app.test_client() as client:
            return client.post(
                f"/api/projects/{project['id']}/sources/A",
                data={"file": (io.BytesIO(b"media"), "source.mp4")},
                content_type="multipart/form-data",
                headers={"X-Cutroom-Upload-Token": token},
            )

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending_upload = pool.submit(upload)
        assert probe_started.wait(1)
        cancelled = app.test_client().post(
            f"/api/projects/{project['id']}/sources/A/uploads/{token}/cancel"
        )
        assert cancelled.status_code == 202
        assert cancelled.get_json() == {
            "active": True,
            "cancelled": True,
            "known_upload": True,
            "removed": False,
            "restored": False,
            "rollback_available": True,
        }
        release_probe.set()
        response = pending_upload.result(timeout=2)

    assert response.status_code == 409
    assert response.get_json()["error"] == "upload_cancelled"
    current = store.load(project["id"])["sources"]["A"]
    assert current["generation"] == "original-generation"
    assert old_path.read_bytes() == b"original"
    assert not list((store.project_dir(project["id"]) / "media").glob(".upload-*"))


def test_late_upload_cancel_never_removes_a_newer_generation(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("generation safe late cancel")
    monkeypatch.setattr(server, "probe_media", _probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: _QueuedJob())
    first_token = "upload_generation_first_01"
    second_token = "upload_generation_second_02"

    first = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"first"), "first.mp4")},
        content_type="multipart/form-data",
        headers={"X-Cutroom-Upload-Token": first_token},
    )
    second = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"second"), "second.mov")},
        content_type="multipart/form-data",
        headers={"X-Cutroom-Upload-Token": second_token},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    second_generation = second.get_json()["source"]["generation"]

    stale_cancel = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A/uploads/{first_token}/cancel"
    )
    assert stale_cancel.status_code == 202
    assert stale_cancel.get_json()["removed"] is False
    current = store.load(project["id"])["sources"]["A"]
    assert current["generation"] == second_generation
    assert (store.project_dir(project["id"]) / current["relative_path"]).read_bytes() == b"second"

    current_cancel = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A/uploads/{second_token}/cancel"
    )
    assert current_cancel.status_code == 202
    assert current_cancel.get_json()["removed"] is True
    assert current_cancel.get_json()["restored"] is True
    restored = store.load(project["id"])["sources"]["A"]
    assert restored["generation"] == first.get_json()["source"]["generation"]
    assert restored["preparation"] == "queued"
    assert (store.project_dir(project["id"]) / restored["relative_path"]).read_bytes() == b"first"
    assert not list((store.project_dir(project["id"]) / "media").glob(".rollback-*"))


def test_upload_cancel_intent_arriving_before_registration_is_honoured(app, monkeypatch: pytest.MonkeyPatch):
    store = app.extensions["cutroom_store"]
    project = store.create("early cancel intent")
    token = "upload_cancel_before_start_01"
    cancelled = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A/uploads/{token}/cancel"
    )
    assert cancelled.status_code == 202
    assert cancelled.get_json()["known_upload"] is False
    monkeypatch.setattr(server, "probe_media", lambda *_args, **_kwargs: pytest.fail("probe must not run"))

    response = app.test_client().post(
        f"/api/projects/{project['id']}/sources/A",
        data={"file": (io.BytesIO(b"media"), "source.mp4")},
        content_type="multipart/form-data",
        headers={"X-Cutroom-Upload-Token": token},
    )
    assert response.status_code == 409
    assert response.get_json()["error"] == "upload_cancelled"
    assert store.load(project["id"])["sources"]["A"] is None


def test_recovery_skips_one_bad_record_without_losing_valid_jobs(tmp_path: Path):
    persistence = tmp_path / "jobs.json"
    persistence.write_text(
        json.dumps({
            "version": 1,
            "jobs": [
                {"id": "broken", "kind": "director", "status": "running"},
                {
                    "id": "job_012345abcdef",
                    "kind": "render",
                    "project_id": "project_012345abcdef",
                    "dedupe_key": "default",
                    "status": "running",
                    "progress": 0.4,
                    "message": "Rendering",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:01Z",
                },
            ],
        }),
        encoding="utf-8",
    )
    manager = JobManager(workers=1, background_workers=1, persistence_path=persistence, retention_seconds=10**9)
    try:
        recovered = manager.get("job_012345abcdef")
        assert recovered is not None
        assert recovered.status == "interrupted"
        rewritten = json.loads(persistence.read_text(encoding="utf-8"))
        assert [row["id"] for row in rewritten["jobs"]] == ["job_012345abcdef"]
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_cancellable_child_process_is_terminated_promptly():
    manager = JobManager(workers=1, background_workers=1)

    def child(context: JobContext):
        run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cancel_check=context.check_cancelled,
        )

    try:
        job = manager.submit("prepare_source", "project_012345abcdef", child)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and manager.get(job.id).status != "running":
            time.sleep(0.01)
        started = time.monotonic()
        assert manager.cancel(job.id) is True
        while time.monotonic() - started < 3 and manager.get(job.id).status != "cancelled":
            time.sleep(0.01)
        assert manager.get(job.id).status == "cancelled"
        assert time.monotonic() - started < 3
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


def test_ollama_install_cancellation_terminates_silent_child(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(server, "resolve_ollama_executable", lambda: "ollama-test")
    real_popen = server.subprocess.Popen
    children: list[server.subprocess.Popen] = []

    def silent_ollama(_command, **kwargs):
        child = real_popen(
            [
                sys.executable,
                "-c",
                "import sys,time; sys.stdout.write('partial'); sys.stdout.flush(); time.sleep(30)",
            ],
            **kwargs,
        )
        children.append(child)
        return child

    monkeypatch.setattr(server.subprocess, "Popen", silent_ollama)
    manager = JobManager(workers=1, background_workers=1)
    try:
        job = manager.submit(
            "model_install",
            None,
            server._install_ollama_model,
            "qwen-test:latest",
            SimpleNamespace(ai={"ollama_url": "http://127.0.0.1:11434"}),
        )
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and (not children or manager.get(job.id).status != "running"):
            time.sleep(0.01)
        assert children

        started = time.monotonic()
        assert manager.cancel(job.id) is True
        while time.monotonic() - started < 3 and manager.get(job.id).status != "cancelled":
            time.sleep(0.01)

        assert manager.get(job.id).status == "cancelled"
        assert children[0].poll() is not None
        assert time.monotonic() - started < 3
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=3)
        manager.shutdown(wait=True, cancel_pending=True)


def test_command_health_timeout_is_reported_as_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        server.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(server.subprocess.TimeoutExpired("ffmpeg", 8)),
    )
    assert server._command_ok(["ffmpeg", "-version"]) is False


def test_browser_url_brackets_ipv6_loopback_literal():
    assert server._http_server_url("127.0.0.1", 8765) == "http://127.0.0.1:8765"
    assert server._http_server_url("localhost", 8765) == "http://localhost:8765"
    assert server._http_server_url("::1", 8765) == "http://[::1]:8765"


def test_server_refuses_an_occupied_port_before_scheduling_browser(monkeypatch: pytest.MonkeyPatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    occupied_port = listener.getsockname()[1]
    timer_calls: list[object] = []
    create_calls: list[object] = []
    settings = SimpleNamespace(
        raw={"host": "127.0.0.1", "port": occupied_port, "open_browser": True},
        data_dir=Path.cwd() / "data",
    )
    monkeypatch.delenv("CUTROOM_NO_BROWSER", raising=False)
    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(server, "create_app", lambda _settings: create_calls.append(_settings))
    monkeypatch.setattr(server, "_probe_existing_cutroom_server", lambda *_args, **_kwargs: "unknown")
    monkeypatch.setattr(server.threading, "Timer", lambda *_args, **_kwargs: timer_calls.append(object()))
    try:
        with pytest.raises(server.ServerStartupError, match="already in use"):
            server.main()
    finally:
        listener.close()

    assert timer_calls == []
    assert create_calls == []


def test_server_reuses_the_same_running_cutroom_instance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = SimpleNamespace(
        raw={"host": "127.0.0.1", "port": 8765, "open_browser": True},
        data_dir=tmp_path / "data",
    )
    browser_calls: list[str] = []
    probe_calls: list[tuple[str, int, str]] = []
    create_calls: list[object] = []

    monkeypatch.delenv("CUTROOM_NO_BROWSER", raising=False)
    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(server, "create_app", lambda _settings: create_calls.append(_settings))
    monkeypatch.setattr(
        server,
        "_reserve_server_sockets",
        lambda *_args: (_ for _ in ()).throw(server.ServerStartupError("already in use")),
    )

    def recognize(host: str, port: int, instance_id: str) -> str:
        probe_calls.append((host, port, instance_id))
        return "match"

    monkeypatch.setattr(server, "_probe_existing_cutroom_server", recognize)
    monkeypatch.setattr(server.webbrowser, "open", lambda url: browser_calls.append(url))

    server.main()

    assert probe_calls == [("127.0.0.1", 8765, server._cutroom_instance_id(settings))]
    assert browser_calls == ["http://127.0.0.1:8765"]
    assert create_calls == []


def test_server_reserves_the_port_before_app_creation_and_hands_socket_to_waitress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    import waitress

    events: list[str] = []
    settings = SimpleNamespace(
        raw={"host": "127.0.0.1", "port": 8765, "open_browser": False, "max_upload_gb": 1},
        data_dir=tmp_path / "data",
    )

    class FakeSocket:
        def close(self):
            events.append("close")

    reserved = FakeSocket()
    jobs = SimpleNamespace(
        shutdown=lambda *, wait, cancel_pending: events.append(f"shutdown:{wait}:{cancel_pending}")
    )
    application = SimpleNamespace(
        extensions={
            "cutroom_jobs": jobs,
            "cutroom_ai_runtime": SimpleNamespace(start_background=lambda: events.append("start-ai")),
            "cutroom_connections": SimpleNamespace(public=lambda: {"mode": "local"}),
        },
        config={"MAX_CONTENT_LENGTH": 1024},
    )

    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        server,
        "_reserve_server_sockets",
        lambda *_args: events.append("reserve") or [reserved],
    )
    monkeypatch.setattr(server, "create_app", lambda _settings: events.append("create") or application)

    def fake_serve(app_arg, **kwargs):
        assert app_arg is application
        assert kwargs["sockets"] == [reserved]
        assert "host" not in kwargs
        assert "port" not in kwargs
        events.append("serve")

    monkeypatch.setattr(waitress, "serve", fake_serve)

    server.main()

    assert events == ["reserve", "create", "start-ai", "serve", "close", "shutdown:False:True"]


@pytest.mark.parametrize(
    ("payload", "classification"),
    [
        ({"service": "cutroom", "protocol": 1, "version": server.__version__, "instance_id": "same-instance"}, "match"),
        ({"service": "another-app", "protocol": 1, "version": server.__version__, "instance_id": "same-instance"}, "unknown"),
        ({"service": "cutroom", "protocol": 1, "version": "older", "instance_id": "same-instance"}, "different_version"),
        ({"service": "cutroom", "protocol": 1, "version": server.__version__, "instance_id": "different"}, "different_instance"),
    ],
)
def test_existing_cutroom_probe_requires_matching_identity(
    payload: dict[str, object], classification: str, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(server, "_read_local_json", lambda *_args, **_kwargs: (200, payload))

    assert server._probe_existing_cutroom_server("127.0.0.1", 8765, "same-instance") == classification


def test_existing_cutroom_probe_supports_the_pre_identity_endpoint_server(monkeypatch: pytest.MonkeyPatch):
    calls: list[str] = []

    def read(_host: str, _port: int, path: str, **_kwargs):
        calls.append(path)
        if path == "/api/instance":
            return 404, None
        return 200, {"version": server.__version__, "instance_id": "same-instance"}

    monkeypatch.setattr(server, "_read_local_json", read)

    assert server._probe_existing_cutroom_server("127.0.0.1", 8765, "same-instance") == "match"
    assert calls == ["/api/instance", "/api/system"]
