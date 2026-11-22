"""Explicit editor preservation admission; no inference or application server."""
import pytest
import server
from test_media_library import api

PRESERVE = "X-Cutroom-Preserve-Edit"
REVISION = "X-Cutroom-Reviewed-Revision"

@pytest.mark.parametrize("route", ["director", "director/refine"])
@pytest.mark.parametrize("headers", [{PRESERVE:"0"}, {PRESERVE:"true"}, {PRESERVE:"1"}, {PRESERVE:"1",REVISION:"0"}])
def test_invalid_preservation_admission_never_writes(api, route, headers):
    app, client, store, pid = api
    before = store.state_path(pid).read_bytes()
    response = client.post(f"/api/projects/{pid}/{route}", json={"goal":"youtube"} if route=="director" else {"command":"shorter"}, headers=headers)
    assert response.status_code == 400, response.get_json()
    assert store.state_path(pid).read_bytes() == before
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)

@pytest.mark.parametrize("route", ["director", "director/refine"])
def test_protected_worker_receives_pinned_mode_without_saving_settings(api, monkeypatch, route):
    app, client, store, pid = api
    store.update(pid, lambda p:p.update(draft={"goal":"youtube"}))
    revision = store.load(pid)["revision"]
    received=[]
    def worker(context, project_id, actual_store, settings, request, **kwargs):
        received.append(kwargs)
        return {"test":"mocked admission only"}
    monkeypatch.setattr(server,"analyze_project" if route=="director" else "refine_project",worker)
    before=store.state_path(pid).read_bytes()
    response=client.post(f"/api/projects/{pid}/{route}",json={"goal":"youtube"} if route=="director" else {"command":"shorter"},headers={PRESERVE:"1",REVISION:str(revision)})
    assert response.status_code==202,response.get_json()
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    assert received==[{"preserve_current_edit":True,"expected_project_revision":revision}]
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("route", ["director", "director/refine"])
def test_stale_protected_admission_rejected(api, route):
    app, client, store, pid=api
    store.update(pid,lambda p:p.update(draft={"goal":"youtube"}))
    revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Newer edit"))
    before=store.state_path(pid).read_bytes()
    response=client.post(f"/api/projects/{pid}/{route}",json={"goal":"youtube"} if route=="director" else {"command":"shorter"},headers={PRESERVE:"1",REVISION:str(revision)})
    assert response.status_code==409 and response.get_json()["error"]=="request_review_stale"
    assert store.state_path(pid).read_bytes()==before
