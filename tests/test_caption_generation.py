"""Actual generation API/jobs/registry contracts, mocked speech recognition only."""
import copy
import time
import threading
from pathlib import Path
import pytest
from test_caption_alternatives import api  # noqa:F401
from cutroom import caption_generation as generation
from cutroom.caption_alternatives import review

@pytest.fixture
def backend(api, monkeypatch, tmp_path):
    model=tmp_path/"cached-model";model.mkdir()
    monkeypatch.setattr(generation,"cached_model",lambda *_:model)
    monkeypatch.setattr(generation.importlib.util,"find_spec",lambda _:object())
    def extract(source,target,*args):target.write_bytes(b"local diagnostic");return target
    monkeypatch.setattr(generation,"_extract_audio_chunk",extract)
    monkeypatch.setattr(generation,"transcribe",lambda *a,**kw:{"language":kw["language"],"model":"cached","segments":[{"id":"s1","start":0.,"end":8.,"text":"Exact unverified ASR.","words":[]}]})
    from cutroom.sequence import materialize_sequence
    _,_,store,pid=api
    store.update(pid,lambda project:materialize_sequence(project)[0])
    return api

def start(api,language="he",revision=None):
    _,client,store,pid=api
    return client.post(f"/api/projects/{pid}/caption-generation",json={"language":language,"expected_revision":revision or store.load(pid)["revision"]})
def finish(api,response):
    assert response.status_code==202,response.get_json()
    _,client,_,_=api;key=response.get_json()["job"]["id"];until=time.monotonic()+3
    while time.monotonic()<until:
        job=client.get(f"/api/jobs/{key}").get_json()["job"]
        if job["status"] not in {"queued","running"}:return job
        time.sleep(.01)
    raise AssertionError("bounded mocked job did not stop")

@pytest.mark.parametrize("language",["he","en"])
def test_api_generates_reviewable_alternative_without_apply(backend,language):
    _,client,store,pid=backend;before=store.load(pid)
    job=finish(backend,start(backend,language));assert job["status"]=="completed",job
    after=store.load(pid)
    assert after["analysis"]==before["analysis"] and after["manual"]==before["manual"]
    assert after["sources"]==before["sources"] and after["settings"]==before["settings"]
    assert job["result"]["applied"] is False
    key=job["result"]["alternative_id"];proposal=review(after,key)
    assert proposal["alternative"][0]["text"]=="Exact unverified ASR."
    assert proposal["verified_by_listening"] is False

@pytest.mark.parametrize("language",["auto","fr",None])
def test_explicit_hebrew_or_english_required(backend,language):
    response=start(backend,language);assert response.status_code==409

def test_stale_request_rejected_before_job(backend):
    _,_,store,pid=backend;rev=store.load(pid)["revision"];store.update(pid,lambda p:p.update(name="manual change"))
    assert start(backend,revision=rev).status_code==409

def test_cancellation_commits_no_alternative(backend,monkeypatch):
    entered=threading.Event()
    def waiting(*a,**kw):
        entered.set()
        while True:kw["cancel_check"]();time.sleep(.005)
    monkeypatch.setattr(generation,"transcribe",waiting)
    response=start(backend);assert response.status_code==202;assert entered.wait(2)
    _,client,store,pid=backend;before=store.state_path(pid).read_bytes();key=response.get_json()["job"]["id"]
    assert client.post(f"/api/jobs/{key}/cancel",json={}).status_code in {200,202}
    assert finish(backend,response)["status"]=="cancelled"
    assert store.state_path(pid).read_bytes()==before

def test_concurrent_manual_change_preserved_when_generation_finishes(backend,monkeypatch):
    entered=threading.Event();release=threading.Event();original=generation.transcribe
    def waiting(*a,**kw):entered.set();assert release.wait(2);return original(*a,**kw)
    monkeypatch.setattr(generation,"transcribe",waiting)
    response=start(backend);assert entered.wait(2)
    _,_,store,pid=backend;store.update(pid,lambda p:p.update(name="Keep manual edit"));before=store.state_path(pid).read_bytes();release.set()
    job=finish(backend,response);assert job["status"]=="failed" and "revision_conflict" in job["error"]
    assert store.state_path(pid).read_bytes()==before

def test_readiness_missing_cached_backend_is_actionable(backend,monkeypatch):
    monkeypatch.setattr(generation,"cached_model",lambda *_:None)
    _,client,_,pid=backend
    state=client.get(f"/api/projects/{pid}/caption-generation?language=en").get_json()
    assert state["ready"] is False and "never downloads" in state["message"]
    assert start(backend).status_code==409

def test_large_edit_and_source_substitution_are_explicitly_unsupported(backend,monkeypatch):
    _,_,store,pid=backend;p=store.load(pid);p["manual"]["source_tracks"]["A"][0]["source_ref"]="asset:other"
    with pytest.raises(ValueError,match="substitutions"):generation.source_interval(p)
    # Keep the fixture's paired source/track identities intact. Lower only the
    # numerical budget to exercise the guard on a valid, fully mapped edit.
    p=store.load(pid)
    monkeypatch.setattr(generation,"MAX_SECONDS",4.)
    with pytest.raises(ValueError,match="90 seconds"):generation.source_interval(p)

def test_nonzero_source_time_offset_is_preserved(backend,monkeypatch):
    _,_,store,pid=backend
    def shift(p):
        p["sources"]["A"]["duration"]=100
        p["manual"]["source_tracks"]["A"][0]["source_start"]=40
    store.update(pid,shift)
    job=finish(backend,start(backend));assert job["status"]=="completed",job
    item=store.load(pid)["caption_alternatives"][job["result"]["alternative_id"]]
    assert item["source_interval"]==[40.,48.] and item["transcript"]["segments"][0]["start"]==40.

def test_low_memory_readiness_prevents_inference(backend,monkeypatch):
    monkeypatch.setattr(generation,"available_memory",lambda:7*1024**3)
    _,client,_,pid=backend
    result=client.get(f"/api/projects/{pid}/caption-generation?language=he").get_json()
    assert result["ready"] is False and "8 GiB" in result["message"]
    assert start(backend).status_code==409

def test_registry_cap_prevents_wasted_generation(backend):
    _,client,store,pid=backend
    store.update(pid,lambda p:p.update(caption_alternatives={"one":{},"two":{},"three":{}}))
    result=client.get(f"/api/projects/{pid}/caption-generation?language=en").get_json()
    assert result["ready"] is False and "three" in result["message"]
    assert start(backend).status_code==409
