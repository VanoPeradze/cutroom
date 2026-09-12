from __future__ import annotations

from types import SimpleNamespace

import pytest

import server
from cutroom.config import load_settings


@pytest.fixture
def runtime_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    calls = []
    runtime = SimpleNamespace(
        snapshot=lambda: {"state": "idle", "available": False, "message": "Not checked yet."},
        ensure_ready=lambda **kw: calls.append(kw) or {
            "state": "ready", "available": True, "message": "Local AI engine ready.",
        },
    )
    monkeypatch.setattr(server, "AIRuntime", lambda _settings: runtime)
    monkeypatch.setattr(server, "story_ai_status", lambda _settings, brief: {
        "ready": True, "selected_model": "installed-fallback:4b", "reason": None,
        "recommended_model": "preferred:4b", "performance_mode": brief.get("performance_mode"),
    })
    application = server.create_app(settings)
    application.config["TESTING"] = True
    yield application, calls, runtime
    application.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def test_prepare_checks_selected_profile_without_creating_jobs(runtime_app):
    app, calls, _runtime = runtime_app
    response = app.test_client().post("/api/runtime/prepare", json={"performance_mode": "lite"})
    assert response.status_code == 200
    assert calls == [{"timeout": 30, "retry": True}]
    assert response.json["story_ai"]["performance_mode"] == "lite"
    assert response.json["story_ai"]["selected_model"] == "installed-fallback:4b"
    assert app.test_client().get("/api/jobs").json["jobs"] == []


@pytest.mark.parametrize("payload", [{"performance_mode": "invalid"}, {"performance_mode": True}, {"model": "secret-download"}])
def test_prepare_rejects_invalid_body_before_starting_engine(runtime_app, payload):
    app, calls, _runtime = runtime_app
    assert app.test_client().post("/api/runtime/prepare", json=payload).status_code == 400
    assert calls == []


def test_prepare_rejects_cross_origin_and_oversized_requests(runtime_app):
    app, calls, _runtime = runtime_app
    client = app.test_client()
    response = client.post("/api/runtime/prepare", json={}, headers={"Origin": "https://untrusted.example"})
    assert response.status_code == 403
    response = client.post("/api/runtime/prepare", data='"' + 'x' * server.JSON_BODY_LIMIT + '"', content_type="application/json")
    assert response.status_code == 413
    assert calls == []


def test_unavailable_engine_is_actionable_and_does_not_queue_download(runtime_app):
    app, _calls, runtime = runtime_app
    runtime.ensure_ready = lambda **_kw: {
        "state": "error", "available": False, "message": "Install Ollama once, then use Retry AI.",
        "error_code": "not_installed",
    }
    response = app.test_client().post("/api/models/install", json={"model": "qwen3.5:4b"})
    assert response.status_code == 409
    assert response.json["error"] == "ai_runtime_unavailable"
    assert response.json["runtime"]["error_code"] == "not_installed"
    assert app.test_client().get("/api/jobs").json["jobs"] == []


def test_runtime_prepare_preserves_a_missing_model_as_separate_setup_step(runtime_app, monkeypatch):
    app, _calls, _runtime = runtime_app
    monkeypatch.setattr(server, "story_ai_status", lambda *_args: {
        "ready": False, "reason": "story_model_missing", "recommended_model": "qwen3.5:4b",
    })
    response = app.test_client().post("/api/runtime/prepare", json={})
    assert response.status_code == 200
    assert response.json["runtime"]["available"] is True
    assert response.json["story_ai"]["ready"] is False
    assert app.test_client().get("/api/jobs").json["jobs"] == []


def test_system_status_is_read_only(runtime_app, monkeypatch):
    app, calls, _runtime = runtime_app
    monkeypatch.setattr(server, "_model_status", lambda _settings: {})
    monkeypatch.setattr(server, "available_encoders", lambda _settings: [])
    response = app.test_client().get("/api/system")
    assert response.status_code == 200
    assert response.json["runtime"]["state"] == "idle"
    assert calls == []


def test_install_uses_discovered_executable_and_configured_endpoint(monkeypatch):
    calls = []
    process = SimpleNamespace(stdout=[], poll=lambda: 0, wait=lambda: 0)
    monkeypatch.setattr(server, "resolve_ollama_executable", lambda: "C:/custom/Ollama/ollama.exe")
    monkeypatch.setattr(server.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)) or process)
    context = SimpleNamespace(
        job=SimpleNamespace(id="test", progress=0),
        check_cancelled=lambda: None, checkpoint=lambda: None, update=lambda *_args: None,
    )
    result = server._install_ollama_model(context, "qwen3.5:4b", SimpleNamespace(ai={"ollama_url": "http://127.0.0.1:11435"}))
    assert result["installed"] is True
    argv, kwargs = calls[0]
    assert argv == ["C:/custom/Ollama/ollama.exe", "pull", "qwen3.5:4b"]
    assert "127.0.0.1:11435" in kwargs["env"]["OLLAMA_HOST"]
    assert kwargs["stdin"] == server.subprocess.DEVNULL
    assert kwargs["encoding"] == "utf-8"
