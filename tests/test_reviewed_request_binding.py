"""Reviewed intent must remain bound across API admission and queued start."""
from types import SimpleNamespace

import pytest

import server
from cutroom import director
from cutroom.story_budget import StoryBudgetError
from test_media_library import api

HEADER = "X-Cutroom-Reviewed-Revision"


@pytest.mark.parametrize("instruction", ["Make one video without cuts.", "צור סרטון אחד בלי חיתוכים."])
def test_concurrent_project_change_rejects_review_before_ai_or_job(api, monkeypatch, instruction):
    app, client, store, pid = api
    brief = {"instruction": instruction, "goal": "short", "source_continuity": "required"}
    reviewed = client.post(f"/api/projects/{pid}/director/request-review", json=brief).get_json()
    assert reviewed["ready"]
    store.update(pid, lambda p: p.update(name="Concurrent saved edit"))
    before = store.state_path(pid).read_bytes()
    monkeypatch.setattr(server, "story_ai_status", lambda *a, **k: pytest.fail("Stale review reached AI readiness"))
    result = client.post(f"/api/projects/{pid}/director", json=brief, headers={HEADER: str(reviewed["revision"])})
    assert result.status_code == 409
    assert result.get_json()["error"] == "request_review_stale"
    assert store.state_path(pid).read_bytes() == before
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)


@pytest.mark.parametrize("value", ["0", "-1", "true", "1.5", "01", "1e2", "9007199254740992"])
def test_invalid_review_revision_never_starts_processing(api, monkeypatch, value):
    app, client, store, pid = api
    before = store.state_path(pid).read_bytes()
    monkeypatch.setattr(server, "story_ai_status", lambda *a, **k: pytest.fail("Invalid header reached AI"))
    result = client.post(f"/api/projects/{pid}/director", json={"goal": "short"}, headers={HEADER: value})
    assert result.status_code == 400
    assert store.state_path(pid).read_bytes() == before
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)


def test_change_between_preflight_and_admission_is_rechecked(api, monkeypatch):
    app, client, store, pid = api
    revision = store.load(pid)["revision"]
    def changed_during_readiness(*args, **kwargs):
        store.update(pid, lambda p: p.update(name="Edit saved while request was preparing"))
        return {"ready": True}
    monkeypatch.setattr(server, "story_ai_status", changed_during_readiness)
    monkeypatch.setattr(server, "analyze_project", lambda *a, **k: pytest.fail("Stale admission reached worker"))
    result = client.post(f"/api/projects/{pid}/director", json={"goal": "short"}, headers={HEADER: str(revision)})
    assert result.status_code == 409
    assert result.get_json()["error"] == "request_review_stale"
    assert store.load(pid)["name"] == "Edit saved while request was preparing"
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)


@pytest.mark.parametrize("bound", [True, False])
def test_valid_review_reaches_worker_without_polluting_settings_and_legacy_stays_compatible(api, monkeypatch, bound):
    app, client, store, pid = api
    revision = store.load(pid)["revision"]
    brief = {"goal": "youtube", "aspect": "16:9", "instruction": "Keep source order."}
    received = []
    def worker(context, project_id, actual_store, settings, patch, **kwargs):
        received.append((project_id, patch, kwargs))
        return {"test": "mechanical mocked worker only"}
    monkeypatch.setattr(server, "analyze_project", worker)
    headers = {HEADER: str(revision)} if bound else {}
    result = client.post(f"/api/projects/{pid}/director", json=brief, headers=headers)
    assert result.status_code == 202, result.get_json()
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    assert received == [(pid, brief, {"expected_project_revision": revision} if bound else {})]
    assert store.load(pid)["revision"] == revision


def test_queue_wait_change_stops_actual_director_before_analysis_and_preserves_edit(api, monkeypatch):
    _, _, store, pid = api
    reviewed_revision = store.load(pid)["revision"]
    store.update(pid, lambda p: p.update(name="Manual edit after enqueue"))
    before = store.state_path(pid).read_bytes()
    monkeypatch.setattr(director, "_source_path", lambda *a, **k: pytest.fail("Stale queued request reached source processing"))
    context = SimpleNamespace(checkpoint=lambda: None)
    with pytest.raises(StoryBudgetError) as caught:
        director.analyze_project(context, pid, store, SimpleNamespace(), {"instruction": "Keep source order."},
                                 expected_project_revision=reviewed_revision)
    assert caught.value.diagnostic["reason"] == "request_review_stale"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert caught.value.diagnostic["completed_edit"] is False
    assert store.state_path(pid).read_bytes() == before
