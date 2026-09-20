import copy
import json
import threading
from pathlib import Path

import pytest

from cutroom import cloud_ai
from cutroom.config import load_settings
from cutroom.jobs import JobCancelled
from cutroom.intelligence import _call_ollama_strict, story_ai_status
from cutroom.transcription import transcribe, transcript_quality_report
from server import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("CUTROOM_GROQ_API_KEY", raising=False)
    return load_settings()


def connected(settings):
    store = cloud_ai.ConnectionStore(settings)
    store.update({"mode": "free", "api_key": "test-secret-not-a-real-key", "consent": True})
    return store, store.job_settings(settings)


def test_connection_is_opt_in_and_never_persists_credentials(settings):
    store = cloud_ai.ConnectionStore(settings)
    assert store.public()["mode"] == "local"
    with pytest.raises(ValueError, match="Confirm"):
        store.update({"mode": "free", "api_key": "secret"})
    assert not store.path.exists()
    store, job = connected(settings)
    assert "test-secret" not in json.dumps(store.public())
    assert "test-secret" not in store.path.read_text()
    assert "cloud_connection" not in settings.ai
    store.update({"mode": "local", "clear_key": True})
    assert job.ai["cloud_connection"]["api_key"] == "test-secret-not-a-real-key"
    assert not store.public()["has_key"]
    assert not cloud_ai.ConnectionStore(settings).public()["has_key"]


def test_restart_remembers_cloud_without_silently_using_local_models(settings):
    connected(settings)
    reopened = cloud_ai.ConnectionStore(settings)
    assert reopened.public()["mode"] == "free"
    assert not reopened.public()["configured"]
    assert not story_ai_status(reopened.job_settings(settings))["ready"]
    with pytest.raises(cloud_ai.CloudAIError, match="API key"):
        cloud_ai.require_connection(reopened.job_settings(settings))


@pytest.mark.parametrize("payload", [
    {"mode": "remote"}, {"provider": "arbitrary"}, {"model": "\ninvalid"},
    {"mode": "free", "consent": "yes"}, {"api_key": "bad\r\nheader"}, {"api_key": []},
    {"base_url": "https://untrusted.invalid"},
    {"mode": []}, {"provider": []}, {"clear_key": "true"},
])
def test_connection_validation_is_atomic(settings, payload):
    store = cloud_ai.ConnectionStore(settings)
    with pytest.raises((ValueError, TypeError)):
        store.update(payload)
    assert store.public()["mode"] == "local"
    assert not store.path.exists()


def test_cloud_story_bypasses_ollama_and_preserves_schema(settings, monkeypatch):
    _, job = connected(settings)
    seen = []
    monkeypatch.setattr("cutroom.intelligence._ollama_inventory", lambda *_: pytest.fail("Ollama must not run"))
    def request(path, key, body, **kwargs):
        seen.append(json.loads(body))
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"keep_ids":["s1"]}'}}]}
    monkeypatch.setattr(cloud_ai, "_request", request)
    assert story_ai_status(job)["ready"]
    result = _call_ollama_strict(job, {"messages": [{"role": "user", "content": "A transcript"}],
                                     "format": {"type": "object"}, "options": {"num_predict": 700}})
    assert result == {"keep_ids": ["s1"]}
    assert seen[0]["max_completion_tokens"] == 700
    assert seen[0]["response_format"] == {"type": "json_object"}
    assert "schema" in seen[0]["messages"][-1]["content"]
    assert "test-secret" not in json.dumps(seen)


@pytest.mark.parametrize("choice", [
    {"finish_reason": "length", "message": {"content": '{}'}},
    {"finish_reason": "stop", "message": {"content": 'not JSON'}},
    {"finish_reason": "stop", "message": {"content": '[]'}},
])
def test_incomplete_story_response_is_not_success(settings, monkeypatch, choice):
    _, job = connected(settings)
    monkeypatch.setattr(cloud_ai, "_request", lambda *a, **k: {"choices": [choice]})
    with pytest.raises(cloud_ai.CloudAIError, match="complete structured"):
        cloud_ai.chat(job, {"messages": []})


@pytest.mark.parametrize("status", [301, 401, 429, 503])
def test_transport_does_not_retry_follow_redirects_or_echo_errors(monkeypatch, status):
    calls = []
    class Client:
        def __init__(self, host, timeout):
            assert host == "api.groq.com"
        def request(self, method, path, **kwargs): calls.append(path)
        def getresponse(self): return type("Reply", (), {"status": status})()
        def close(self): pass
    monkeypatch.setattr(cloud_ai.http.client, "HTTPSConnection", Client)
    with pytest.raises(cloud_ai.CloudAIError) as error:
        cloud_ai._request("chat/completions", "sensitive-key", b'{}')
    assert len(calls) == 1
    assert "sensitive-key" not in str(error.value)


def test_cancel_interrupts_inflight_request(monkeypatch):
    started, closed = threading.Event(), threading.Event()
    class Client:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs):
            started.set()
            closed.wait(2)
        def getresponse(self): raise OSError()
        def close(self): closed.set()
    monkeypatch.setattr(cloud_ai.http.client, "HTTPSConnection", Client)
    def check():
        if started.is_set(): raise JobCancelled("Cancelled")
    with pytest.raises(JobCancelled):
        cloud_ai._request("chat/completions", "test-key", b'{}', cancel_check=check)
    assert closed.is_set()


def test_full_recording_cloud_transcription_and_boundary_ownership(settings, monkeypatch):
    _, job = connected(settings)
    calls = []
    lengths = []
    def ffmpeg(args, **kwargs):
        lengths.append(float(args[args.index("-t") + 1]))
        Path(args[-1]).write_bytes(b"synthetic audio fixture")
    monkeypatch.setattr("cutroom.media.run_command", ffmpeg)
    monkeypatch.setattr("cutroom.media.probe_media", lambda *args: {"duration": lengths[-1]})
    replies = [
        {"language": "hebrew", "text": "שלום סוף", "words": [{"word": "שלום", "start": 4, "end": 5}, {"word": "סוף", "start": 299.5, "end": 300.5}]},
        {"language": "hebrew", "text": "סוף עולם", "words": [{"word": "סוף", "start": .5, "end": 1.5}, {"word": "עולם", "start": 300, "end": 301}]},
    ]
    def request(path, key, body, mime, check):
        calls.append(body)
        return replies.pop(0)
    monkeypatch.setattr(cloud_ai, "_request", request)
    monkeypatch.setattr("cutroom.transcription._transcribe_isolated", lambda *a, **k: pytest.fail("No local model"))
    result = transcribe(Path("private-filename.mp4"), job, duration=600, cancel_check=lambda: None)
    assert result["language"] == "he"
    assert result["coverage"]["complete"]
    assert result["coverage"]["analyzed_ranges"] == [{"start": 0.0, "end": 600.0}]
    assert [w["word"] for w in result["words"]] == ["שלום", "סוף", "עולם"]
    assert result["words"][-1]["end"] == 600
    assert transcript_quality_report(result)["coverage_status"] == "complete"
    assert all(b"private-filename" not in body for body in calls)
    assert not list(job.cache_dir.glob("cutroom-cloud-*"))


def test_cloud_failure_does_not_fall_back_to_local_or_retry(settings, monkeypatch):
    from cutroom.director import _transcribe_safely
    def fail(*a, **k): raise cloud_ai.CloudAIError("Quota reached")
    monkeypatch.setattr("cutroom.director.transcribe", fail)
    with pytest.raises(cloud_ai.CloudAIError, match="Quota"):
        _transcribe_safely(Path("x"), settings, "he")


def test_cloud_cleanup_pass_receives_cancellation_callback(settings, monkeypatch):
    from cutroom.intelligence import plan_edit
    _, job = connected(settings)
    def check(): pass
    def fake_chat(settings, payload, cancel_check=None, **kwargs):
        assert cancel_check is check
        raise JobCancelled("Cancelled cloud cleanup")
    monkeypatch.setattr(cloud_ai, "chat", fake_chat)
    with pytest.raises(JobCancelled):
        plan_edit([{"id": "s1", "start": 0, "end": 3, "text": "A clear explanation."}], job,
                  {"goal": "clean"}, cancel_check=check)


def test_connection_api_is_redacted_validated_and_same_origin(settings):
    app = create_app(settings)
    client = app.test_client()
    try:
        assert client.get("/api/ai/connection").get_json()["connection"]["mode"] == "local"
        assert client.post("/api/ai/connection", json={"mode": "free"}).status_code == 400
        assert client.post("/api/ai/connection", json={"mode": "local"}, headers={"Origin": "https://evil.invalid"}).status_code == 403
        result = client.post("/api/ai/connection", json={"mode": "own", "api_key": "never-echo-this", "consent": True})
        assert result.status_code == 200
        assert b"never-echo-this" not in result.data
        assert result.get_json()["connection"]["has_key"]
        assert client.post("/api/runtime/prepare", json={}).get_json()["runtime"]["state"] == "cloud"
    finally:
        app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)
