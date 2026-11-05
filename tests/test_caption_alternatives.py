"""Source-bound caption review via the real API/edit/render projection, no AI."""
import copy
import json

import pytest

from cutroom.caption_alternatives import FORMAT, binding, register, review, status
from cutroom.captions import build_ass
from cutroom.config import load_settings
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.manual_start import start_manual_draft
from cutroom.render import project_caption_items
from server import create_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings(); settings.ai["enabled"] = False
    app = create_app(settings); app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    project = store.create("Caption review")
    (store.project_dir(project["id"]) / "media/source-A.mp4").write_bytes(b"identity fixture only")
    project["sources"] = {"A": {"generation": "source-v1", "duration": 8., "relative_path": "media/source-A.mp4", "has_audio": True,
                                  "width": 160, "height": 100, "fps": 30}, "B": None}
    start_manual_draft(project)
    project["analysis"] = {"audio_source": "A", "audio_timeline_offset": 0., "transcript": {"language": "he", "model": "original",
        "segments": [{"id": "s1", "start": 0., "end": 8., "text": "לשנתי טוב.", "words": [
            {"start": 0., "end": 3., "word": "לשנתי"}, {"start": 3., "end": 8., "word": "טוב."}]}]}}
    project = store.save(project)
    yield app, app.test_client(), store, project["id"]
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def saved(project, text="לא ישנתי טוב."):
    words = text.split()
    return {"format": FORMAT, "label": "Alternate · unverified", "binding": binding(project), "source_interval": [0., 8.],
        "transcript": {"language": "he", "model": "saved-local", "segments": [{"id": "s1", "start": 0., "end": 8., "text": text,
            "words": [{"start": 8 * i / len(words), "end": 8 * (i + 1) / len(words), "word": w} for i, w in enumerate(words)]}]}}


def load(api, value=None):
    _, client, store, pid = api
    project = store.load(pid)
    response = client.post(f"/api/projects/{pid}/caption-alternatives", json={
        "alternative": value or saved(project), "expected_revision": project["revision"]})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["project"]["caption_alternatives"][0]["id"]


def proposal(api, key):
    _, client, _, pid = api
    response = client.get(f"/api/projects/{pid}/caption-alternatives/{key}")
    assert response.status_code == 200, response.get_json()
    return response.get_json()["proposal"]


def apply(api, preview):
    _, client, _, pid = api
    return client.post(f"/api/projects/{pid}/manual/edit", json={"action": "caption_alternative", "alternative_id": preview["id"],
        "review_fingerprint": preview["review_fingerprint"], "expected_revision": preview["revision"]})


@pytest.mark.parametrize("alternative", ["לא ישנתי טוב.", "I did not sleep well."])
def test_real_review_apply_undo_redo_preserve_source_and_manual_timeline(api, alternative, tmp_path):
    _, client, store, pid = api
    before = store.load(pid); canonical = copy.deepcopy(before["analysis"]["transcript"])
    key = load(api, saved(before, alternative))
    path = store.state_path(pid); before_preview = path.read_bytes()
    preview = proposal(api, key)
    assert path.read_bytes() == before_preview  # Preview and dismiss are read-only.
    assert preview["original"][0]["text"] == "לשנתי טוב." and preview["alternative"][0]["text"] == alternative
    assert preview["verified_by_listening"] is False and preview["ranges"] == [{"start": 0., "end": 8.}]
    response = apply(api, preview); assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    assert after["analysis"]["transcript"] == canonical and after["sources"] == before["sources"]
    footage_keys = ("source_tracks", "sequence", "cuts", "keeps", "keep_ranges", "camera_overrides", "source_mixer")
    assert {k: after["manual"].get(k) for k in footage_keys} == {k: before["manual"].get(k) for k in footage_keys}
    items = project_caption_items(after)
    assert items[0]["text"] == alternative and items[0]["start"] == 0 and items[0]["end"] == 8
    assert items[0]["segment_id"].startswith("alt:")
    ass = build_ass({}, [], tmp_path / "active.ass", 720, 1280, caption_lines=[{"start": i["start"], "end": i["end"], "text": i["text"]} for i in items]).read_text("utf-8-sig")
    assert alternative in ass
    # Native source IDs/text are unchanged in stored alternatives.
    assert after["caption_alternatives"][key]["transcript"]["segments"][0]["id"] == "s1"
    for action, active in [("undo", "original"), ("redo", key)]:
        result = client.post(f"/api/projects/{pid}/manual/edit", json={"action": action, "expected_revision": store.load(pid)["revision"]})
        assert result.status_code == 200, result.get_json()
        assert status(store.load(pid))["active_id"] == active
    assert store.load(pid)["analysis"]["transcript"] == canonical


def test_repeat_apply_does_not_add_history_and_original_can_be_restored(api):
    _, _, store, pid = api
    key = load(api); assert apply(api, proposal(api, key)).status_code == 200
    count = store.load(pid)["manual"]["history"]["undo_count"]
    assert apply(api, proposal(api, key)).status_code == 200
    assert store.load(pid)["manual"]["history"]["undo_count"] == count
    assert apply(api, proposal(api, "original")).status_code == 200
    assert status(store.load(pid))["active_id"] == "original"


def test_stale_preview_revision_and_fingerprint_cannot_replace_manual_work(api):
    _, client, store, pid = api
    key = load(api); preview = proposal(api, key)
    store.update(pid, lambda p: p["settings"].update(caption_style="boxed"))
    before = store.state_path(pid).read_bytes()
    assert apply(api, preview).status_code == 409
    assert store.state_path(pid).read_bytes() == before
    preview["revision"] = store.load(pid)["revision"]; preview["review_fingerprint"] = "wrong"
    assert apply(api, preview).status_code == 400
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("change", ["source", "canonical", "timeline", "saved_text"])
def test_applied_alternative_expires_safely_after_source_or_edit_change(api, change):
    _, _, store, pid = api
    key = load(api); assert apply(api, proposal(api, key)).status_code == 200
    def mutate(p):
        if change == "source": p["sources"]["A"]["generation"] = "replaced"
        elif change == "canonical": p["analysis"]["transcript"]["segments"][0]["text"] = "New canonical transcript"
        elif change == "timeline": apply_manual_edit(p, {"action": "delete_range", "start": 1., "end": 2.})
        else: p["caption_alternatives"][key]["transcript"]["segments"][0]["text"] = "tampered"
    store.update(pid, mutate)
    current = store.load(pid)
    assert status(current)["state"] == "stale" and status(current)["active_id"] == "original"


@pytest.mark.parametrize("layer", ["caption_corrections", "caption_overrides", "caption_dormant_overrides"])
def test_existing_caption_edits_are_not_discarded(api, layer):
    _, _, store, pid = api
    key = load(api)
    store.update(pid, lambda p: p["manual"].update({layer: {"old": {"text": "keep me"}} if layer != "caption_dormant_overrides" else [{"edit": {"text": "keep me"}}]}))
    preview = proposal(api, key); before = store.state_path(pid).read_bytes()
    assert preview["manual_caption_edits"] is True
    response = apply(api, preview); assert response.status_code == 400
    assert response.get_json()["error"] == "invalid_manual_edit"
    assert "preserved" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


def test_active_caption_corrections_use_alternative_namespace_not_canonical(api):
    _, client, store, pid = api
    key = load(api); assert apply(api, proposal(api, key)).status_code == 200
    item = project_caption_items(store.load(pid))[0]
    response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "caption_update", "caption_id": item["id"], "scope": "source", "text": "Explicit reviewed correction.", "expected_revision": store.load(pid)["revision"]})
    assert response.status_code == 200, response.get_json()
    assert project_caption_items(store.load(pid))[0]["text"] == "Explicit reviewed correction."
    assert store.load(pid)["analysis"]["transcript"]["segments"][0]["text"] == "לשנתי טוב."
    assert apply(api, proposal(api, "original")).status_code == 400


def test_import_rejects_wrong_binding_partial_coverage_and_invalid_times(api):
    _, client, store, pid = api
    original = store.load(pid); value = saved(original)
    value["binding"]["source_generation"] = "another-source"
    before = store.state_path(pid).read_bytes()
    assert client.post(f"/api/projects/{pid}/caption-alternatives", json={"alternative": value, "expected_revision": original["revision"]}).status_code == 400
    assert store.state_path(pid).read_bytes() == before
    value = saved(original); value["transcript"]["segments"][0]["words"][0]["start"] = -1
    with pytest.raises(ValueError): register(copy.deepcopy(original), value)
    value = saved(original); value["source_interval"] = [0., 4.]
    row = value["transcript"]["segments"][0]; row.update(end=4., words=[])
    key = register(original, value)
    with pytest.raises(ValueError, match="whole edit"): review(original, key)
