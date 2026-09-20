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


def connected_compatible(settings, *, base_url="https://api.vendor.com/v1"):
    store = cloud_ai.ConnectionStore(settings)
    store.update({
        "mode": "own",
        "provider": "openai-compatible",
        "base_url": base_url,
        "model": "vendor/chat-model",
        "transcript_model": "vendor/whisper-model",
        "api_key": "test-compatible-not-a-real-key",
        "consent": True,
        "endpoint_consent": base_url,
    })
    return store, store.job_settings(settings)


def test_connection_is_opt_in_and_never_persists_credentials(settings):
    store = cloud_ai.ConnectionStore(settings)
    assert store.public()["mode"] == "local"
    with pytest.raises(ValueError, match="Confirm"):
        store.update({"mode": "free", "api_key": "test-unconfirmed-key"})
    assert not store.path.exists()
    store, job = connected(settings)
    assert "test-secret" not in json.dumps(store.public())
    assert "test-secret" not in store.path.read_text()
    assert "cloud_connection" not in settings.ai
    store.update({"mode": "local", "clear_key": True})
    assert job.ai["cloud_connection"]["api_key"] == "test-secret-not-a-real-key"
    assert not store.public()["has_key"]
    assert not cloud_ai.ConnectionStore(settings).public()["has_key"]


def test_compatible_connection_persists_only_canonical_nonsecret_preferences(settings):
    store, job = connected_compatible(settings, base_url="https://API.VENDOR.com:443/v1/")
    public = store.public()
    assert public == {
        "mode": "own",
        "provider": "openai-compatible",
        "model": "vendor/chat-model",
        "transcript_model": "vendor/whisper-model",
        "base_url": "https://api.vendor.com/v1",
        "has_key": True,
        "configured": True,
        "key_storage": "session",
        "provider_label": "OpenAI-compatible",
    }
    saved = json.loads(store.path.read_text(encoding="utf-8"))
    assert saved == {key: public[key] for key in ("mode", "provider", "model", "transcript_model", "base_url")}
    assert "test-compatible" not in store.path.read_text(encoding="utf-8")
    assert job.ai["cloud_connection"]["api_key"] == "test-compatible-not-a-real-key"


def test_key_is_scoped_to_mode_provider_and_endpoint_and_old_job_snapshot_is_immutable(settings, monkeypatch):
    monkeypatch.setenv("CUTROOM_GROQ_API_KEY", "test-groq-environment-key")
    store, first_job = connected_compatible(settings)
    first_snapshot = copy.deepcopy(first_job.ai["cloud_connection"])

    changed = store.update({
        "mode": "own",
        "provider": "openai-compatible",
        "base_url": "https://second.vendor.com/openai/v1",
        "model": "vendor/chat-model",
        "transcript_model": "vendor/whisper-model",
        "consent": True,
        "endpoint_consent": "https://second.vendor.com/openai/v1",
    })
    assert not changed["has_key"]
    with pytest.raises(cloud_ai.CloudAIError, match="API key"):
        cloud_ai.require_connection(store.job_settings(settings))
    assert first_job.ai["cloud_connection"] == first_snapshot

    # Switching back does not revive either the prior in-memory key or the Groq
    # environment key after the destination changed.
    groq = store.update({"mode": "free", "provider": "groq", "model": cloud_ai.DEFAULT_MODEL, "consent": True})
    assert not groq["has_key"]
    with pytest.raises(cloud_ai.CloudAIError, match="API key"):
        cloud_ai.require_connection(store.job_settings(settings))


def test_restart_keeps_compatible_preferences_but_never_a_secret_or_groq_environment_key(settings, monkeypatch):
    monkeypatch.setenv("CUTROOM_GROQ_API_KEY", "test-groq-environment-key")
    store, _ = connected_compatible(settings)
    reopened = cloud_ai.ConnectionStore(settings)
    assert reopened.public()["provider"] == "openai-compatible"
    assert reopened.public()["base_url"] == "https://api.vendor.com/v1"
    assert not reopened.public()["has_key"]
    assert not reopened.public()["configured"]


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
    {"mode": "free", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://api.vendor.com/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "http://api.vendor.com/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "http://api.vendor.com/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://user:pass@api.vendor.com/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://user:pass@api.vendor.com/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1?target=elsewhere", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://api.vendor.com/v1?target=elsewhere"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://127.0.0.1/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://127.0.0.1/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1", "model": "chat", "transcript_model": "bad model", "consent": True, "endpoint_consent": "https://api.vendor.com/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://api.vendor.com/v1"},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": True},
    {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/v1", "model": "chat", "transcript_model": "whisper", "consent": True, "endpoint_consent": "https://other.vendor.com/v1"},
    {"mode": []}, {"provider": []}, {"clear_key": "true"},
])
def test_connection_validation_is_atomic(settings, payload):
    store = cloud_ai.ConnectionStore(settings)
    with pytest.raises((ValueError, TypeError)):
        store.update(payload)
    assert store.public()["mode"] == "local"
    assert not store.path.exists()


@pytest.mark.parametrize("url", [
    "https://api.vendor.com/v1#fragment",
    "https://api.vendor.com/v1?query=1",
    "https://api.vendor.com\\v1",
    "https://api.vendor.com/v1\n",
    "https://[::1]/v1",
    "https://169.254.169.254/v1",
    "https://metadata.google.internal/v1",
])
def test_compatible_url_rejects_ambiguous_or_nonpublic_destinations(url):
    with pytest.raises(ValueError):
        cloud_ai._normalize_base_url(url)


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


def test_compatible_chat_uses_only_selected_endpoint_and_model(settings, monkeypatch):
    _, job = connected_compatible(settings)
    seen = {}

    def request(path, key, body, **kwargs):
        seen.update(path=path, key=key, body=json.loads(body), connection=copy.deepcopy(kwargs.get("connection")))
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"keep_ids":["s1"]}'}}]}

    monkeypatch.setattr(cloud_ai, "_request", request)
    result = cloud_ai.chat(job, {"messages": [{"role": "user", "content": "private"}]})
    assert result == {"keep_ids": ["s1"]}
    assert seen["path"] == "chat/completions"
    assert seen["body"]["model"] == "vendor/chat-model"
    assert seen["connection"]["provider"] == "openai-compatible"
    assert seen["connection"]["base_url"] == "https://api.vendor.com/v1"
    assert seen["key"] == "test-compatible-not-a-real-key"


def test_compatible_status_identifies_provider_without_claiming_provider_certification(settings):
    _, job = connected_compatible(settings)
    status = story_ai_status(job)
    assert status["ready"]
    assert status["provider"] == "openai-compatible"
    assert status["provider_label"] == "OpenAI-compatible"
    assert status["selected_model"] == "vendor/chat-model"


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
    monkeypatch.setattr(cloud_ai, "_AbortableHTTPSConnection", Client)
    with pytest.raises(cloud_ai.CloudAIError) as error:
        cloud_ai._request("chat/completions", "sensitive-key", b'{}')
    assert len(calls) == 1
    assert "sensitive-key" not in str(error.value)


def test_custom_endpoint_rejects_private_dns_before_secret_is_sent(monkeypatch):
    sent = []
    monkeypatch.setattr(cloud_ai.socket, "getaddrinfo", lambda *a, **k: [
        (cloud_ai.socket.AF_INET, cloud_ai.socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
    ])
    monkeypatch.setattr(cloud_ai._PinnedHTTPSConnection, "request", lambda *a, **k: sent.append((a, k)))
    selected = {
        "mode": "own",
        "provider": "openai-compatible",
        "base_url": "https://api.vendor.com/v1",
    }
    with pytest.raises(cloud_ai.CloudAIError) as error:
        cloud_ai._request("chat/completions", "test-sensitive-compatible-key", b"{}", connection=selected)
    assert not sent
    assert "test-sensitive-compatible-key" not in str(error.value)


def test_custom_https_connection_pins_public_address_and_verifies_original_hostname(monkeypatch):
    calls = []

    class Context:
        def wrap_socket(self, sock, server_hostname):
            calls.append(("tls", sock, server_hostname))
            return "tls-socket"

    monkeypatch.setattr(
        cloud_ai.socket,
        "create_connection",
        lambda address, timeout, source_address: calls.append(("connect", address, timeout, source_address)) or "plain-socket",
    )
    client = cloud_ai._PinnedHTTPSConnection("api.vendor.com", 443, "8.8.8.8", 17)
    client._context = Context()
    client.connect()
    assert calls[0][0] == "connect"
    assert calls[0][1] == ("8.8.8.8", 443)
    assert calls[1] == ("tls", "plain-socket", "api.vendor.com")
    assert client.sock == "tls-socket"


def test_compatible_transport_uses_exact_prefix_without_redirect_or_proxy(monkeypatch):
    calls = []

    class Client:
        def request(self, method, path, **kwargs):
            calls.append((method, path, kwargs["headers"]))

        def getresponse(self):
            return type("Reply", (), {"status": 200, "read": lambda self, limit: b'{"ok":true}'})()

        def close(self):
            calls.append(("close",))

    monkeypatch.setattr(cloud_ai, "_compatible_client", lambda selected, timeout: (Client(), "/private/v1"))
    selected = {"mode": "own", "provider": "openai-compatible", "base_url": "https://api.vendor.com/private/v1"}
    assert cloud_ai._request("chat/completions", "test-transport-key", b"{}", connection=selected) == {"ok": True}
    assert calls[0][0:2] == ("POST", "/private/v1/chat/completions")
    assert calls[0][2]["Authorization"] == "Bearer test-transport-key"
    assert len([call for call in calls if call and call[0] == "POST"]) == 1


def test_custom_cancel_during_tcp_connect_cannot_send_after_return(monkeypatch):
    connecting = threading.Event()
    release_connection = threading.Event()
    raw_closed = threading.Event()
    sent = threading.Event()

    class RawSocket:
        def close(self):
            raw_closed.set()

    class TLSSocket:
        def sendall(self, _data):
            sent.set()

        def close(self):
            raw_closed.set()

    class Context:
        verify_mode = cloud_ai.ssl.CERT_REQUIRED
        check_hostname = True

        def wrap_socket(self, _sock, server_hostname):
            assert server_hostname == "api.vendor.com"
            return TLSSocket()

    def connect(*_args, **_kwargs):
        connecting.set()
        assert release_connection.wait(2)
        return RawSocket()

    def cancel_check():
        if connecting.is_set():
            raise JobCancelled("Cancelled")

    monkeypatch.setattr(cloud_ai, "_resolve_public_addresses", lambda *_: ["8.8.8.8"])
    monkeypatch.setattr(cloud_ai.ssl, "create_default_context", lambda: Context())
    monkeypatch.setattr(cloud_ai.socket, "create_connection", connect)
    selected = {
        "mode": "own",
        "provider": "openai-compatible",
        "base_url": "https://api.vendor.com/v1",
    }
    with pytest.raises(JobCancelled):
        cloud_ai._request(
            "chat/completions",
            "test-cancel-key",
            b"{}",
            cancel_check=cancel_check,
            connection=selected,
        )
    assert not sent.is_set()
    release_connection.set()
    assert raw_closed.wait(2)
    assert not sent.is_set()


def test_groq_cancel_during_tcp_connect_cannot_send_after_return(monkeypatch):
    connecting = threading.Event()
    release_connection = threading.Event()
    socket_closed = threading.Event()
    sent = threading.Event()

    class RawSocket:
        def setsockopt(self, *_args):
            pass

        def close(self):
            socket_closed.set()

    class TLSSocket:
        def sendall(self, _data):
            sent.set()

        def close(self):
            socket_closed.set()

    class Context:
        verify_mode = cloud_ai.ssl.CERT_REQUIRED
        check_hostname = True

        def wrap_socket(self, _sock, server_hostname):
            assert server_hostname == "api.groq.com"
            return TLSSocket()

    def connect(*_args, **_kwargs):
        connecting.set()
        assert release_connection.wait(2)
        return RawSocket()

    def cancel_check():
        if connecting.is_set():
            raise JobCancelled("Cancelled")

    monkeypatch.setattr(cloud_ai.ssl, "create_default_context", lambda: Context())
    monkeypatch.setattr(cloud_ai.socket, "create_connection", connect)
    with pytest.raises(JobCancelled):
        cloud_ai._request(
            "chat/completions",
            "test-groq-cancel-key",
            b"{}",
            cancel_check=cancel_check,
        )
    assert not sent.is_set()
    release_connection.set()
    assert socket_closed.wait(2)
    assert not sent.is_set()


def test_cancel_interrupts_inflight_request(monkeypatch):
    started, closed = threading.Event(), threading.Event()
    class Client:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs):
            started.set()
            closed.wait(2)
        def getresponse(self): raise OSError()
        def close(self): closed.set()
    monkeypatch.setattr(cloud_ai, "_AbortableHTTPSConnection", Client)
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


def test_compatible_transcription_sends_selected_model_and_reports_its_identity(settings, monkeypatch):
    _, job = connected_compatible(settings)
    lengths = []
    requests = []

    def ffmpeg(args, **kwargs):
        lengths.append(float(args[args.index("-t") + 1]))
        Path(args[-1]).write_bytes(b"synthetic audio fixture")

    def request(path, key, body, mime, check, **kwargs):
        requests.append({"path": path, "body": body, "connection": kwargs.get("connection")})
        return {"language": "english", "text": "hello", "words": [{"word": "hello", "start": 0.1, "end": 0.5}]}

    monkeypatch.setattr("cutroom.media.run_command", ffmpeg)
    monkeypatch.setattr("cutroom.media.probe_media", lambda *args: {"duration": lengths[-1]})
    monkeypatch.setattr(cloud_ai, "_request", request)
    result = cloud_ai.transcribe_cloud(Path("private.mp4"), job, duration=2, cancel_check=lambda: None)
    assert result["model"] == "openai-compatible/vendor/whisper-model"
    assert requests[0]["path"] == "audio/transcriptions"
    assert requests[0]["connection"]["base_url"] == "https://api.vendor.com/v1"
    assert b'name="model"\r\n\r\nvendor/whisper-model\r\n' in requests[0]["body"]


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
