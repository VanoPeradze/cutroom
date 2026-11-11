from pathlib import Path
from types import SimpleNamespace
import copy
import pytest
from cutroom import transcription as tr
from cutroom import transcription_adapter as adapter
from cutroom import cloud_ai
from cutroom.jobs import JobCancelled


def settings(engine):
    return SimpleNamespace(ai={"transcription_engine": engine, "whisper_isolate_process": False,
        "cloud_connection": {"mode":"own", "api_key":"test-do-not-serialize-story-secret"},
        "cloudflare_connection":{"api_key":"test-do-not-serialize-cf-secret"}})


def result():
    return {"segments":[], "text":"", "model":"local-test"}


@pytest.mark.parametrize("route", ["local", "legacy", "cloud", "auto"])
@pytest.mark.parametrize("old_cloud", [True, False])
def test_route_matrix(monkeypatch, route, old_cloud):
    calls=[]
    monkeypatch.setattr(tr,"local_cached_fallback_settings",lambda selected,*a:selected)
    monkeypatch.setattr(cloud_ai,"enabled",lambda s:old_cloud)
    monkeypatch.setattr(cloud_ai,"transcribe_cloud",lambda *a: calls.append("legacy") or result())
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",lambda *a: calls.append("cloudflare") or result())
    monkeypatch.setattr(tr,"_transcribe_in_process",lambda *a: calls.append("local") or result())
    tr.transcribe(Path("never-opened.wav"),settings(route))
    expected = "cloudflare" if route in {"cloud","auto"} else "legacy" if route=="legacy" and old_cloud else "local"
    assert calls == [expected]


def test_explicit_local_removes_both_credentials_before_worker(monkeypatch):
    original=settings("local")
    original.raw={"ai":original.ai}
    original.root=original.data_dir=original.cache_dir=Path(".")
    original.ai["whisper_isolate_process"]=True
    def worker(path, selected, *args):
        assert selected.ai["cloud_connection"] == {"mode":"local"}
        assert "cloudflare_connection" not in selected.ai
        assert "secret" not in str(selected.raw)
        return result()
    monkeypatch.setattr(tr,"_transcribe_isolated",worker)
    tr.transcribe(Path("never-opened.wav"),original,cancel_check=lambda:None)
    assert original.ai["cloud_connection"]["api_key"].endswith("secret")
    assert original.ai["cloudflare_connection"]["api_key"].endswith("secret")


@pytest.mark.parametrize("route,eligible",[("cloud",True),("auto",False)])
def test_noneligible_failure_never_enters_local(monkeypatch,route,eligible):
    def fail(*args): raise adapter.CloudTranscriptionError("Service error",fallback_allowed=eligible,uploaded_parts=1)
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",fail)
    monkeypatch.setattr(tr,"local_cached_fallback_settings",lambda selected,*a:selected)
    monkeypatch.setattr(tr,"_transcribe_local",lambda *a:pytest.fail("local must not run"))
    with pytest.raises(adapter.CloudTranscriptionError): tr.transcribe(Path("none"),settings(route))


def test_fallback_once_preserves_upload_provenance_and_no_secrets(monkeypatch):
    calls=[]
    def fail(*a): calls.append("cloud"); raise adapter.CloudTranscriptionError("Service unavailable",fallback_allowed=True,uploaded_parts=2)
    def ready(selected,*a):
        calls.append("ready"); clone=copy.deepcopy(selected); clone.ai["whisper_local_files_only"]=True; return clone
    def local(path,selected,*a):
        calls.append("local"); assert selected.ai["whisper_local_files_only"] is True
        assert "secret" not in str(selected.ai); return result()
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",fail)
    monkeypatch.setattr(tr,"local_cached_fallback_settings",ready)
    monkeypatch.setattr(tr,"_transcribe_in_process",local)
    response=tr.transcribe(Path("none"),settings("auto"))
    assert calls==["ready","cloud","ready","local"]
    assert response["execution"]["actual_transcription_engine"]=="local"
    assert response["execution"]["cloud_attempt"]["uploaded_parts"]==2
    assert response["execution"]["cloud_attempt"]["uploads_may_have_occurred"] is True
    assert "secret" not in str(response)


@pytest.mark.parametrize("stage",["before","cloud","after"])
def test_cancel_never_falls_back(monkeypatch,stage):
    calls=[]
    def check():
        if stage=="before" or stage=="after" and calls: raise JobCancelled("Cancelled")
    def cloud(*a):
        calls.append("cloud")
        if stage=="cloud": raise JobCancelled("Cancelled")
        raise adapter.CloudTranscriptionError("Unavailable",fallback_allowed=True,uploaded_parts=1)
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",cloud)
    monkeypatch.setattr(tr,"local_cached_fallback_settings",lambda selected,*a: selected if not calls else pytest.fail("no fallback after cancel"))
    with pytest.raises(JobCancelled): tr.transcribe(Path("none"),settings("auto"),cancel_check=check)


def test_missing_local_cache_surfaces_upload_attempts_without_loading(monkeypatch):
    def cloud(*a): raise adapter.CloudTranscriptionError("Unavailable",fallback_allowed=True,uploaded_parts=2)
    checked=[]
    def ready(selected,*a):
        checked.append(True)
        if len(checked)>1: raise RuntimeError("Download local model explicitly first")
        return selected
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",cloud)
    monkeypatch.setattr(tr,"local_cached_fallback_settings",ready)
    monkeypatch.setattr(tr,"_transcribe_local",lambda *a:pytest.fail("no local execution"))
    with pytest.raises(adapter.CloudTranscriptionError,match="Cloud upload attempts: 2") as exc:
        tr.transcribe(Path("none"),settings("auto"))
    assert exc.value.uploaded_parts==2
    assert exc.value.fallback_allowed is False


def test_local_failure_after_cloud_still_discloses_prior_upload(monkeypatch):
    def cloud(*a): raise adapter.CloudTranscriptionError("Unavailable",fallback_allowed=True,uploaded_parts=1)
    def local(*a): raise RuntimeError("Local inference unavailable")
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",cloud)
    monkeypatch.setattr(tr,"local_cached_fallback_settings",lambda selected,*a:selected)
    monkeypatch.setattr(tr,"_transcribe_local",local)
    with pytest.raises(adapter.CloudTranscriptionError,match="uploads/charges cannot be undone"):
        tr.transcribe(Path("none"),settings("auto"))


def test_auto_missing_cache_prevents_even_first_upload(monkeypatch):
    def ready(*a): raise RuntimeError("Download the local model first")
    monkeypatch.setattr(tr,"local_cached_fallback_settings",ready)
    monkeypatch.setattr(adapter,"transcribe_cloud_whisper",lambda *a:pytest.fail("no upload before fallback readiness"))
    with pytest.raises(adapter.CloudTranscriptionError,match="No audio was sent") as error:
        tr.transcribe(Path("none"),settings("auto"))
    assert error.value.uploaded_parts==0


def test_worker_payload_always_redacts_cloud_settings_even_when_called_directly():
    selected=settings("auto")
    selected.raw={"ai":selected.ai}
    selected.root=selected.data_dir=selected.projects_dir=selected.exports_dir=selected.cache_dir=Path(".")
    selected.ffmpeg="ffmpeg";selected.ffprobe="ffprobe"
    payload=tr._worker_settings_payload(selected)
    assert "secret" not in str(payload)
    assert payload["raw"]["ai"]["transcription_engine"]=="local"
    assert "cloudflare_connection" not in payload["raw"]["ai"]
    assert selected.ai["transcription_engine"]=="auto"
