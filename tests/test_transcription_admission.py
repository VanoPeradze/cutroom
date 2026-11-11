"""Synthetic concurrency tests: no media, cloud request or inference is run."""
import threading
import time
import pytest

from cutroom.config import load_settings
from server import create_app


@pytest.mark.parametrize("route",["director","director/refine"])
def test_local_save_cannot_race_cloud_snapshot_into_later_admission(tmp_path, monkeypatch, route):
    monkeypatch.setenv("CUTROOM_DATA_DIR",str(tmp_path/"data"))
    monkeypatch.setenv("CUTROOM_CF_ACCOUNT_ID","a"*32)
    monkeypatch.setenv("CUTROOM_CF_API_TOKEN","fake-test-token")
    app=create_app(load_settings())
    connections=app.extensions["cutroom_connections"]
    store=app.extensions["cutroom_store"]
    info=connections.transcription.public()
    connections.transcription.update({"engine":"cloud","consent":True,"consent_scope":info["consent_scope"]})
    project=store.create("Synthetic gate test")
    store.update(project["id"],lambda row:row["sources"].update({"A":{"relative_path":"media/never-opened.mp4","duration":2,"has_audio":True}}))
    store.update(project["id"],lambda row:row.update(draft={"goal":"youtube","keep_ranges":[{"start":0,"end":2}]}))
    snapshot_taken, release_snapshot, job_running, release_job= [threading.Event() for _ in range(4)]
    original=connections.job_settings
    calls=[]
    def snapshot(settings):
        selected=original(settings)
        snapshot_taken.set()
        assert release_snapshot.wait(5)
        return selected
    def fake_analyze(context,project_id,store,settings,*args,**kwargs):
        calls.append(settings.ai["transcription_engine"])
        job_running.set()
        assert release_job.wait(5)
        return {}
    monkeypatch.setattr(connections,"job_settings",snapshot)
    monkeypatch.setattr("server.analyze_project",fake_analyze)
    monkeypatch.setattr("server.refine_project",fake_analyze)
    results={}
    def start():
        with app.test_client() as client: results["job"]=client.post(f'/api/projects/{project["id"]}/{route}',json={"goal":"youtube"} if route=="director" else {"command":"shorter"})
    def select_local():
        with app.test_client() as client: results["local"]=client.post('/api/transcription/engine',json={"engine":"local"})
    job_thread=threading.Thread(target=start)
    local_thread=threading.Thread(target=select_local)
    try:
        job_thread.start(); assert snapshot_taken.wait(3)
        local_thread.start(); time.sleep(.05)
        assert "local" not in results, "Local must not be acknowledged while an older cloud admission owns the gate"
        release_snapshot.set(); job_thread.join(3)
        assert job_running.wait(3)
        local_thread.join(3)
        assert results["job"].status_code==202
        assert results["local"].status_code==409
        assert calls==["cloud"]
        assert connections.transcription.public()["engine"]=="cloud"
    finally:
        release_snapshot.set(); release_job.set()
        job_thread.join(5)
        if local_thread.ident: local_thread.join(5)
        app.extensions["cutroom_jobs"].shutdown(wait=True,cancel_pending=True)
    # After the active job ends, a successful Local save governs future jobs.
    with app.test_client() as client:
        assert client.post('/api/transcription/engine',json={"engine":"local"}).status_code==200
    assert connections.job_settings(app.extensions["cutroom_settings"]).ai["transcription_engine"]=="local"
