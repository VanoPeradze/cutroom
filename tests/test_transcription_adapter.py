"""Offline Cloudflare contract tests. Never contact a provider or download a model."""
import copy
import json
import subprocess
import threading
import wave
from pathlib import Path

import pytest

from cutroom import cloud_ai, transcription_adapter as cf
from cutroom.cache_keys import build_analysis_cache_fingerprints
from cutroom.config import load_settings
from cutroom.jobs import JobCancelled


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_CF_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("CUTROOM_CF_API_TOKEN", "fake-test-token")
    return load_settings()


def approved(settings, mode="cloud"):
    store = cloud_ai.ConnectionStore(settings)
    info = store.transcription.public()
    store.transcription.update({"engine": mode, "consent": True, "consent_scope": info["consent_scope"]})
    return store, store.job_settings(settings)


def test_new_install_local_and_legacy_migration(settings):
    assert cf.EngineStore(settings).public()["engine"] == "local"
    (settings.data_dir / "ai-connection.json").write_text(json.dumps({"mode": "free"}))
    assert cf.EngineStore(settings).public()["engine"] == "local"
    # A genuinely pre-upgrade install has no engine preference at all.
    (settings.data_dir / "transcription-engine.json").unlink()
    assert cf.EngineStore(settings).public()["engine"] == "legacy"
    store = cf.EngineStore(settings)
    store.update({"engine": "local"})
    assert cf.EngineStore(settings).public()["engine"] == "local"


def test_consent_scope_snapshot_and_no_saved_secret(settings, monkeypatch):
    store, job = approved(settings)
    public = store.transcription.public()
    assert public["consented"] and public["cloud_ready"]
    assert "fake-test-token" not in json.dumps(public)
    assert "fake-test-token" not in store.transcription.path.read_text()
    assert "a" * 32 not in store.transcription.path.read_text()
    assert cf._connection(job)["api_key"] == "fake-test-token"
    monkeypatch.setenv("CUTROOM_CF_ACCOUNT_ID", "b" * 32)
    assert not store.transcription.public()["consented"]
    with pytest.raises(cf.CloudTranscriptionError, match="Confirm"):
        cf._connection(store.job_settings(settings))
    assert cf._connection(job)["account_id"] == "a" * 32
    with pytest.raises(ValueError, match="Confirm"):
        store.transcription.update({"engine": "cloud", "consent": True, "consent_scope": public["consent_scope"]})


@pytest.mark.parametrize("payload", [
    {"engine": "cloud"}, {"engine": "auto", "consent": True},
    {"engine": "cloud", "consent": "true", "consent_scope": "wrong"},
    {"engine": "nope"}, {"engine": "local", "api_key": "secret"}, [],
])
def test_invalid_consent_or_fields(settings, payload):
    with pytest.raises(ValueError):
        cf.EngineStore(settings).update(payload)


def test_no_credentials_no_upload_and_no_implicit_cloud(settings, monkeypatch):
    monkeypatch.delenv("CUTROOM_CF_API_TOKEN")
    store = cf.EngineStore(settings)
    assert not store.public()["cloud_ready"]
    with pytest.raises(ValueError, match="environment"):
        store.update({"engine": "cloud", "consent": True, "consent_scope": store.public()["consent_scope"]})
    with pytest.raises(cf.CloudTranscriptionError):
        cf.transcribe_cloud_whisper(Path("not-opened.wav"), settings)


def test_disclosure_and_model_changes_invalidate(settings, monkeypatch):
    store, job = approved(settings)
    monkeypatch.setattr(cf, "DISCLOSURE_VERSION", "new-terms")
    assert not store.transcription.public()["consented"]
    with pytest.raises(cf.CloudTranscriptionError, match="Confirm"):
        cf._connection(job)
    job.ai["cloudflare_connection"]["model"] = "@cf/unreviewed/model"
    with pytest.raises(cf.CloudTranscriptionError):
        cf._connection(job)


def test_cache_changes_for_engine_account_consent_not_secret(settings):
    store, job = approved(settings)
    def key(s):
        return build_analysis_cache_fingerprints({}, s, {}, {})["transcript"]
    original = key(job)
    clone = copy.deepcopy(job)
    clone.ai["cloudflare_connection"]["api_key"] = "rotated-token"
    assert key(clone) == original
    for field, value in [("account_id", "b"*32), ("consent_scope", "changed"), ("model", "changed")]:
        clone = copy.deepcopy(job)
        clone.ai["cloudflare_connection"][field] = value
        assert key(clone) != original
    clone = copy.deepcopy(job)
    clone.ai["transcription_engine"] = "local"
    assert key(clone) != original
    assert "fake-test-token" not in json.dumps(cf.cache_identity(job))


def response(words=None, text="hello"):
    if words is None:
        words = [{"start": .1, "end": .5, "word": "hello"}]
    return {"text": text, "language": "en", "segments": [{"text": text, "words": words}]}


@pytest.mark.parametrize("value", [
    {}, {"text": "hello"}, {"text": "hello", "segments": []},
    {"text": "", "segments": None}, {"text": "hello", "segments": [{"text": "hello"}]},
    response([{"start": 1, "end": .5, "word": "hi"}]),
    response([{"start": -1, "end": .5, "word": "hi"}]),
    response([{"start": float("nan"), "end": .5, "word": "hi"}]),
    response([{"start": 0, "end": float("inf"), "word": "hi"}]),
    response([{"start": 0, "end": 20, "word": "hi"}]),
    response([{"start": False, "end": .5, "word": "hi"}]),
    response([{"start": 0, "end": .5, "word": ""}]),
    response([{"start": 0, "end": .5, "word": 1}]),
    response([{"start": .2, "end": .5, "word": "a"}, {"start": .1, "end": .2, "word": "b"}]),
])
def test_invalid_timing_never_invented_or_accepted_as_complete(value):
    with pytest.raises(cf.CloudTranscriptionError):
        cf._words(value, 0, 10, 0, 10)


def test_silence_and_ownership():
    assert cf._words({"text": "", "segments": []}, 0, 10, 0, 10) == []
    assert cf._words(response(), 119, 130, 120, 130) == []
    assert cf._words(response(), 120, 130, 120, 130)[0]["start"] == 120.1


def mock_audio(monkeypatch, duration=2, truncated=False):
    from cutroom import media
    def command(args, **kwargs):
        length = float(args[args.index("-t")+1]) if duration is None else duration
        with wave.open(str(args[-1]), "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\0\0" * int(length * 16000))
        if truncated:
            path = Path(args[-1])
            path.write_bytes(path.read_bytes()[:-1000])
    monkeypatch.setattr(media, "run_command", command)


@pytest.mark.parametrize("language,expected", [(None, None), ("auto", None), ("he", "he"), ("en", "en"), ("he-IL", "he")])
def test_transcribe_mocked_audio_language_and_complete_provenance(settings, monkeypatch, language, expected):
    _, job = approved(settings)
    mock_audio(monkeypatch)
    payloads = []
    def post(selected, body, check):
        payloads.append(json.loads(body))
        return response()
    monkeypatch.setattr(cf, "_post", post)
    result = cf.transcribe_cloud_whisper(Path("mock.wav"), job, language=language, duration=2)
    assert payloads[0].get("language") == expected
    assert result["language"] == (expected or "en")
    assert result["words"][0]["word"] == "hello"
    assert result["execution"]["uploaded_parts"] == 1
    assert "fake-test-token" not in json.dumps(result)


@pytest.mark.parametrize("duration,truncated", [(1, False), (2, True)])
def test_audio_integrity_fails_before_upload(settings, monkeypatch, duration, truncated):
    _, job = approved(settings)
    mock_audio(monkeypatch, duration, truncated)
    monkeypatch.setattr(cf, "_post", lambda *a: pytest.fail("must not upload"))
    with pytest.raises(cf.CloudTranscriptionError, match="preparation"):
        cf.transcribe_cloud_whisper(Path("mock.wav"), job, duration=2)


def test_second_chunk_failure_reports_possible_uploads_without_retry(settings, monkeypatch):
    _, job = approved(settings, "auto")
    mock_audio(monkeypatch, duration=None)
    calls = []
    def post(*args):
        calls.append(1)
        if len(calls) == 2:
            raise cf.CloudTranscriptionError("test safe failure", fallback_allowed=True)
        return response()
    monkeypatch.setattr(cf, "_post", post)
    with pytest.raises(cf.CloudTranscriptionError) as error:
        cf.transcribe_cloud_whisper(Path("mock.wav"), job, duration=130)
    assert error.value.uploaded_parts == 2
    assert error.value.fallback_allowed
    assert len(calls) == 2


@pytest.mark.parametrize("failure", [
    OSError("private path"),
    subprocess.CalledProcessError(1, ["ffmpeg", "private path"]),
    subprocess.TimeoutExpired(["ffmpeg", "private path"], 180),
])
@pytest.mark.parametrize("completed_parts", [0, 1])
def test_extraction_failure_preserves_upload_accounting(settings, monkeypatch, failure, completed_parts):
    from cutroom import media
    _, job = approved(settings)
    mock_audio(monkeypatch, duration=None)
    prepare = media.run_command
    uploads = []
    def command(*args, **kwargs):
        if len(uploads) == completed_parts:
            raise failure
        return prepare(*args, **kwargs)
    def post(*args):
        uploads.append(1)
        return response()
    monkeypatch.setattr(media, "run_command", command)
    monkeypatch.setattr(cf, "_post", post)
    with pytest.raises(cf.CloudTranscriptionError) as error:
        cf.transcribe_cloud_whisper(Path("mock.wav"), job, duration=130)
    assert error.value.uploaded_parts == completed_parts
    assert not error.value.fallback_allowed
    assert len(uploads) == completed_parts
    assert "private path" not in str(error.value)
    assert ("Cloud upload attempts:" in str(error.value)) == bool(completed_parts)


def test_extraction_cancellation_is_not_converted(settings, monkeypatch):
    from cutroom import media
    _, job = approved(settings)
    def command(*args, **kwargs):
        raise JobCancelled("test cancel")
    monkeypatch.setattr(media, "run_command", command)
    monkeypatch.setattr(cf, "_post", lambda *args: pytest.fail("must not upload"))
    with pytest.raises(JobCancelled):
        cf.transcribe_cloud_whisper(Path("mock.wav"), job, duration=130)


def test_cancel_never_converted_to_fallback(settings, monkeypatch):
    _, job = approved(settings, "auto")
    mock_audio(monkeypatch)
    def cancel(*args):
        raise JobCancelled("test cancel")
    monkeypatch.setattr(cf, "_post", cancel)
    with pytest.raises(JobCancelled):
        cf.transcribe_cloud_whisper(Path("mock.wav"), job, duration=2)


@pytest.mark.parametrize("status,fallback", [(301,False),(401,False),(403,False),(413,False),(429,True),(500,True)])
def test_transport_fixed_endpoint_redaction_no_redirect_or_retry(settings, monkeypatch, status, fallback):
    _, job = approved(settings)
    calls = []
    class Client:
        def __init__(self, host, **kwargs):
            assert host == "api.cloudflare.com"
        def request(self, method, path, **kwargs):
            calls.append((method,path))
        def getresponse(self):
            return type("Response", (), {"status": status})()
        def abort(self):
            pass
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", Client)
    with pytest.raises(cf.CloudTranscriptionError) as error:
        cf._post(cf._connection(job), b"{}", lambda: None)
    assert error.value.fallback_allowed is fallback
    assert len(calls) == 1
    assert calls[0][1] == f"/client/v4/accounts/{'a'*32}/ai/run/{cf.MODEL}"
    assert "fake-test-token" not in str(error.value)


def test_transport_cancel_aborts_pending_request(settings, monkeypatch):
    _, job = approved(settings)
    started, aborted = threading.Event(), threading.Event()
    class Client:
        def __init__(self, *args, **kwargs):
            pass
        def request(self, *args, **kwargs):
            started.set()
            aborted.wait(2)
            raise OSError("private remote details")
        def abort(self):
            aborted.set()
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", Client)
    def check():
        if started.is_set():
            raise JobCancelled("cancelled")
    with pytest.raises(JobCancelled):
        cf._post(cf._connection(job), b"{}", check)
    assert aborted.is_set()


def test_api_scope_validation_origin_and_restart(settings):
    from server import create_app
    app = create_app(settings)
    client = app.test_client()
    try:
        info = client.get("/api/transcription/engine").get_json()
        assert info["engine"] == "local" and info["cloud_ready"]
        assert client.post("/api/transcription/engine", json={"engine":"cloud"}).status_code == 400
        assert client.post("/api/transcription/engine", json={"engine":"local"}, headers={"Origin":"https://evil.invalid"}).status_code == 403
        result = client.post("/api/transcription/engine", json={"engine":"auto", "consent":True,"consent_scope":info["consent_scope"]})
        assert result.status_code == 200
        assert result.get_json()["consented"]
        assert cf.EngineStore(settings).public()["engine"] == "auto"
        assert b"fake-test-token" not in result.data
    finally:
        app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)

@pytest.mark.parametrize("mode", [[], {}, None, True])
def test_bad_engine_types_are_input_errors(settings, mode):
    with pytest.raises(ValueError):
        cf.EngineStore(settings).update({"engine": mode})


@pytest.mark.parametrize("data", [b"not json", b"[]", b'{"success":false,"result":{}}', b'{"success":true,"result":null}'])
def test_transport_invalid_response_redacted(settings, monkeypatch, data):
    _, job = approved(settings)
    class Client:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self):
            return type("Response", (), {"status":200, "read":lambda self,n:data})()
        def abort(self): pass
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", Client)
    with pytest.raises(cf.CloudTranscriptionError) as error:
        cf._post(cf._connection(job), b"{}", lambda:None)
    assert error.value.fallback_allowed
    assert "fake-test-token" not in str(error.value)


def test_transport_success_and_response_limit(settings, monkeypatch):
    _, job = approved(settings)
    data = json.dumps({"success":True, "result":response()}).encode()
    class Client:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self):
            return type("Response", (), {"status":200, "read":lambda self,n:data[:n]})()
        def abort(self): pass
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", Client)
    assert cf._post(cf._connection(job), b"{}", lambda:None)["text"] == "hello"
    monkeypatch.setattr(cf, "MAX_RESPONSE", 2)
    with pytest.raises(cf.CloudTranscriptionError, match="oversized"):
        cf._post(cf._connection(job), b"{}", lambda:None)


def test_transport_body_limit_before_network(settings, monkeypatch):
    _, job = approved(settings)
    monkeypatch.setattr(cf, "MAX_BODY", 2)
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", lambda *a,**k:pytest.fail("network forbidden"))
    with pytest.raises(cf.CloudTranscriptionError, match="upload limit"):
        cf._post(cf._connection(job), b"123", lambda:None)


def test_transport_timeout_aborts_without_retry(settings, monkeypatch):
    _, job = approved(settings)
    calls, aborted = [], threading.Event()
    class Client:
        def __init__(self, *a,**k): pass
        def request(self, *a,**k):
            calls.append(1)
            aborted.wait(2)
            raise OSError()
        def abort(self): aborted.set()
    monkeypatch.setattr(cf, "_AbortableHTTPSConnection", Client)
    with pytest.raises(cf.CloudTranscriptionError, match="timed out") as error:
        cf._post(cf._connection(job), b"{}", lambda:None, timeout=.01)
    assert error.value.fallback_allowed
    assert calls == [1] and aborted.is_set()


def test_admission_validation_is_noop_for_local_and_checks_cloud(settings):
    assert cf.require_transcription_connection(settings) is None
    _, job = approved(settings)
    assert cf.require_transcription_connection(job)["model"] == cf.MODEL
    job.ai["cloudflare_connection"]["consent_scope"] = None
    with pytest.raises(cf.CloudTranscriptionError, match="Confirm"):
        cf.require_transcription_connection(job)

@pytest.mark.parametrize("saved", ['not json', '[]', '{"engine": []}', '{"engine": "bad"}'])
def test_damaged_engine_preferences_fail_closed(settings, saved):
    (settings.data_dir / "ai-connection.json").write_text(json.dumps({"mode":"free"}))
    (settings.data_dir / "transcription-engine.json").write_text(saved)
    assert cf.EngineStore(settings).public()["engine"] == "local"


def test_story_cloud_does_not_change_fresh_local_after_restart(settings):
    store = cloud_ai.ConnectionStore(settings)
    store.update({"mode":"free", "consent":True, "api_key":"not-real"})
    assert store.job_settings(settings).ai["transcription_engine"] == "local"
    assert cloud_ai.ConnectionStore(settings).job_settings(settings).ai["transcription_engine"] == "local"


def test_auto_language_uses_documented_nested_info(settings, monkeypatch):
    _, job = approved(settings)
    mock_audio(monkeypatch)
    value = response()
    value.pop("language")
    value["transcription_info"] = {"language":"he", "language_probability":.98, "duration":2}
    monkeypatch.setattr(cf, "_post", lambda *a: value)
    assert cf.transcribe_cloud_whisper(Path("mock.wav"), job, language="auto", duration=2)["language"] == "he"


def test_api_rejects_changes_during_active_job(settings, monkeypatch):
    from server import create_app
    app = create_app(settings)
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(app.extensions["cutroom_jobs"], "active", lambda: ["running"])
            assert app.test_client().post("/api/transcription/engine", json={"engine":"local"}).status_code == 409
    finally:
        app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)

@pytest.mark.parametrize("value", [
    response(text="hello missing words"),
    {"text":"hello", "segments":[{"text":"hello missing", "words":[{"start":.1,"end":.5,"word":"hello"}]}]},
    {**response(), "transcription_info":{"duration":1}},
])
def test_partial_provider_content_not_marked_complete(value):
    with pytest.raises(cf.CloudTranscriptionError):
        cf._words(value, 0, 10, 0, 10)


def test_text_integrity_ignores_case_spacing_and_punctuation():
    assert cf._words(response(text="HELLO!"), 0, 10, 0, 10)[0]["word"] == "hello"

@pytest.mark.parametrize("route",["local","cloud","auto","legacy"])
def test_story_model_change_does_not_retranscribe_audio(settings,route):
    settings.ai["transcription_engine"]=route
    settings.ai["cloud_connection"]={"mode":"own","provider":"groq","model":"chat-one","transcript_model":"speech-one"}
    first=build_analysis_cache_fingerprints({},settings,{}, {})
    settings.ai["cloud_connection"]["model"]="chat-two"
    second=build_analysis_cache_fingerprints({},settings,{}, {})
    assert first["transcript"]==second["transcript"]
    assert first["story"]!=second["story"]


@pytest.mark.parametrize("route",["local","cloud","auto"])
def test_explicit_speech_ignores_entire_story_destination(settings,route):
    settings.ai["transcription_engine"]=route
    first=build_analysis_cache_fingerprints({},settings,{}, {})
    settings.ai["cloud_connection"]={"mode":"own","provider":"openai-compatible","base_url":"https://example.test/v1","model":"chat","transcript_model":"speech"}
    second=build_analysis_cache_fingerprints({},settings,{}, {})
    assert first["transcript"]==second["transcript"]
    assert first["story"]!=second["story"]


def test_legacy_speech_model_change_invalidates_transcript(settings):
    settings.ai["transcription_engine"]="legacy"
    settings.ai["cloud_connection"]={"mode":"own","provider":"groq","model":"chat","transcript_model":"speech-one"}
    first=build_analysis_cache_fingerprints({},settings,{}, {})
    settings.ai["cloud_connection"]["transcript_model"]="speech-two"
    assert first["transcript"]!=build_analysis_cache_fingerprints({},settings,{}, {})["transcript"]


def test_error_discloses_prior_upload_attempts_without_provider_payload():
    error=cf.CloudTranscriptionError("Service unavailable",fallback_allowed=True)
    error.uploaded_parts=2
    assert "Cloud upload attempts: 2" in str(error)
    assert "possible charges cannot be undone" in str(error)
