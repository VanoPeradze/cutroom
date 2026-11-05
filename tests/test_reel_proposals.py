"""Synthetic media/edits exercise real review and manual-edit API transactions."""
import copy
from concurrent.futures import ThreadPoolExecutor

import pytest

from cutroom.config import load_settings
from cutroom.editing import ManualEditError
from cutroom.reel_proposals import reel_proposal
from server import create_app


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.ai["enabled"] = False
    app = create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    project = store.create("Reel review")
    root = store.project_dir(project["id"])
    media = root / "media" / "source A.mp4"
    media.parent.mkdir(parents=True, exist_ok=True)
    media.write_bytes(b"test-only media identity; no playback claim")
    project["sources"] = {"A": {"duration": 20, "relative_path": "media/source A.mp4", "generation": "source-v1"}, "B": None}
    project["analysis"] = {"transcript": {"segments": [{"id": "s0", "start": 0, "end": 20, "text": "Unverified fixture text."}]}}
    project["draft"] = {
        "status": "review", "cuts": [{"start": 8, "end": 10}],
        "keep_ranges": [{"start": 0, "end": 8}, {"start": 10, "end": 20}],
        "output_duration": 18, "removed_duration": 2,
        "camera_plan": [{"start": 0, "end": 20, "camera": "A"}],
        "active_reel_candidate": "director_pick", "editorial_note": "Keep this unverified note",
        "reel_candidates": [{"id": "alternative", "cuts": [{"start": 0, "end": 5}, {"start": 15, "end": 20}],
                             "ai_camera_plan": [{"start": 5, "end": 15, "camera": "A"}]}],
    }
    project["manual"] = {"cuts": [{"start": 7, "end": 8}], "keeps": [], "camera_overrides": [],
                         "source_mixer": {"primary": "A"}, "track_locks": {"A": False, "B": False}}
    store.save(project)
    yield app, app.test_client(), store, project["id"], media
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def review(api, **overrides):
    _, client, store, pid, _ = api
    return client.post(f"/api/projects/{pid}/reel-proposal", json={
        "candidate_id": "alternative", "expected_revision": store.load(pid)["revision"], **overrides})


def apply(api, proposal, **overrides):
    _, client, _, pid, _ = api
    return client.post(f"/api/projects/{pid}/manual/edit", json={
        "action": "apply_reel_candidate", "candidate_id": proposal["candidate_id"],
        "proposal_id": proposal["proposal_id"], "expected_revision": proposal["revision"], **overrides})


def test_preview_is_byte_preserving_and_uses_actual_manual_overrides(api):
    _, _, store, pid, _ = api
    path = store.project_dir(pid) / "project.json"
    before = path.read_bytes()
    response = review(api)
    assert response.status_code == 200, response.get_json()
    proposal = response.get_json()["proposal"]
    assert proposal["ranges"] == [{"start": 5, "end": 7}, {"start": 8, "end": 15}]
    assert proposal["output_duration"] == 9
    assert proposal["status"] == "needs_user_review"
    assert proposal["semantic_approval"] is False
    assert path.read_bytes() == before  # Dismiss has no server-side state to undo.
    assert review(api).get_json() == response.get_json()


def test_review_apply_undo_redo_preserves_manual_and_draft_metadata(api):
    _, client, store, pid, _ = api
    before = store.load(pid)
    proposal = review(api).get_json()["proposal"]
    response = apply(api, proposal)
    assert response.status_code == 200
    applied = store.load(pid)
    assert applied["draft"]["keep_ranges"] == proposal["ranges"]
    assert applied["draft"]["active_reel_candidate"] == "alternative"
    assert applied["analysis"] == before["analysis"]
    assert applied["settings"] == before["settings"]
    assert applied["draft"]["editorial_note"] == before["draft"]["editorial_note"]
    for key in ("cuts", "keeps", "source_mixer", "track_locks"):
        assert applied["manual"][key] == before["manual"][key]
    for action in ("undo", "redo"):
        result = client.post(f"/api/projects/{pid}/manual/edit", json={"action": action, "expected_revision": store.load(pid)["revision"]})
        assert result.status_code == 200
        actual = store.load(pid)
        expected = before if action == "undo" else applied
        for key, value in expected["draft"].items():
            if key != "edited_at":
                assert actual["draft"][key] == value
        for key in ("cuts", "keeps", "source_mixer", "track_locks"):
            assert actual["manual"][key] == before["manual"][key]


@pytest.mark.parametrize("change", ["manual", "source", "transcript", "settings", "candidate"])
def test_changed_project_rejects_old_review_even_with_new_revision(api, change):
    _, _, store, pid, _ = api
    proposal = review(api).get_json()["proposal"]
    project = store.load(pid)
    if change == "manual":
        project["manual"]["cuts"].append({"start": 10, "end": 11})
    elif change == "source":
        project["sources"]["A"]["generation"] = "source-v2"
    elif change == "transcript":
        project["analysis"]["transcript"]["segments"][0]["text"] = "Do not rewrite negation. לא ישנתי"
    elif change == "settings":
        project["settings"]["instruction"] = "One video without cuts; סרטון אחד ללא חיתוכים"
    else:
        project["draft"]["reel_candidates"][0]["cuts"][0]["end"] = 4
    saved = store.save(project)
    before = (store.project_dir(pid) / "project.json").read_bytes()
    response = apply(api, proposal, expected_revision=saved["revision"])
    assert response.status_code == 409
    assert response.get_json()["error"] == "stale_reel_proposal"
    assert (store.project_dir(pid) / "project.json").read_bytes() == before


def test_repeat_apply_and_old_project_revision_cannot_replace_current_edit(api):
    _, _, store, pid, _ = api
    proposal = review(api).get_json()["proposal"]
    assert apply(api, proposal).status_code == 200
    before = (store.project_dir(pid) / "project.json").read_bytes()
    assert apply(api, proposal).status_code == 409
    assert apply(api, proposal, expected_revision=store.load(pid)["revision"]).status_code == 400
    assert (store.project_dir(pid) / "project.json").read_bytes() == before


@pytest.mark.parametrize("change", ["missing", "replaced"])
def test_source_file_changes_fail_without_touching_project(api, change):
    _, _, store, pid, media = api
    proposal = review(api).get_json()["proposal"]
    if change == "missing":
        media.unlink()
    else:
        media.write_bytes(b"different test source")
    before = (store.project_dir(pid) / "project.json").read_bytes()
    assert apply(api, proposal).status_code == 409
    assert (store.project_dir(pid) / "project.json").read_bytes() == before


@pytest.mark.parametrize("case", ["locked", "sequence", "two_sources", "bad_range", "unknown", "duplicate"])
def test_unsupported_or_invalid_preview_is_read_only(api, case):
    _, _, store, pid, _ = api
    project = store.load(pid)
    if case == "locked":
        project["manual"]["track_locks"] = {"A": True}
    elif case == "sequence":
        project["manual"]["source_tracks"] = {"A": []}
    elif case == "two_sources":
        project["sources"]["B"] = copy.deepcopy(project["sources"]["A"])
    elif case == "bad_range":
        project["draft"]["reel_candidates"][0]["cuts"][0]["end"] = 21
    elif case == "duplicate":
        project["draft"]["reel_candidates"].append(copy.deepcopy(project["draft"]["reel_candidates"][0]))
    else:
        project["draft"]["reel_candidates"] = []
    store.save(project)
    before = (store.project_dir(pid) / "project.json").read_bytes()
    assert review(api).status_code == 409
    assert (store.project_dir(pid) / "project.json").read_bytes() == before


def test_busy_review_and_apply_cannot_race_job(api, monkeypatch):
    app, _, store, pid, _ = api
    proposal = review(api).get_json()["proposal"]
    with monkeypatch.context() as context:
        context.setattr(app.extensions["cutroom_jobs"], "active", lambda **_: [object()])
        before = store.load(pid)
        assert review(api).get_json()["error"] == "project_busy"
        assert apply(api, proposal).get_json()["error"] == "project_busy"
        assert store.load(pid) == before


def test_two_accepts_race_one_atomic_revision_transaction(api):
    app, _, store, pid, _ = api
    proposal = review(api).get_json()["proposal"]
    def accept(_):
        with app.test_client() as client:
            return client.post(f"/api/projects/{pid}/manual/edit", json={
                "action": "apply_reel_candidate", "candidate_id": proposal["candidate_id"],
                "expected_revision": proposal["revision"], "proposal_id": proposal["proposal_id"],
            }).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(accept, range(2))) == [200, 409]
    assert store.load(pid)["manual"]["history"]["undo_count"] == 1


@pytest.mark.parametrize("end,allowed", [(2, True), (17, False)])
def test_review_preserves_overlays_or_rejects_out_of_bounds_without_clipping(api, end, allowed):
    _, client, store, pid, _ = api
    response = client.post(f"/api/projects/{pid}/manual/edit", json={
        "action": "text_add", "expected_revision": store.load(pid)["revision"],
        "kind": "title", "start": 0, "end": end, "text": "Keep my manual title", "position": "top", "scale": 100, "style": "clean",
    })
    assert response.status_code == 200, response.get_json()
    saved = store.load(pid)
    response = review(api)
    assert response.status_code == (200 if allowed else 409), response.get_json()
    assert store.load(pid) == saved
    if allowed:
        assert apply(api, response.get_json()["proposal"]).status_code == 200
        assert store.load(pid)["manual"]["text_clips"] == saved["manual"]["text_clips"]


@pytest.mark.parametrize("instruction,allowed", [
    ("Make one video", True), ("צור סרטון אחד", True),
    ("Make one video without cuts", False), ("צור סרטון אחד ללא חיתוכים", False),
    ("Make a video of 8-12 seconds", True), ("צור סרטון בין 8 ל-12 שניות", True),
    ("Make a video of 45-60 seconds", False), ("צור סרטון בין 45 ל-60 שניות", False),
])
def test_existing_instruction_controls_remain_separate_from_style(api, instruction, allowed):
    _, _, store, pid, _ = api
    project = store.load(pid)
    project["settings"].update(instruction=instruction, edit_style="cinematic", target_duration=60, duration_mode="target")
    saved = store.save(project)
    response = review(api)
    assert response.status_code == (200 if allowed else 409), response.get_json()
    assert store.load(pid) == saved
    if allowed:
        assert response.get_json()["proposal"]["request"]["instruction"] == instruction


@pytest.mark.parametrize("instruction", ["Make exactly 10 seconds", "צור 10 שניות"])
def test_exact_duration_and_contiguous_source_mapping(api, instruction):
    _, _, store, pid, _ = api
    project = store.load(pid)
    project["manual"]["cuts"] = []
    project["settings"].update(instruction=instruction, target_duration=10, duration_mode="target")
    store.save(project)
    response = review(api)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["proposal"]["ranges"] == [{"start": 5, "end": 15}]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "5", -1])
def test_non_numeric_or_invalid_source_ranges_rejected(api, value):
    _, _, store, pid, _ = api
    project = store.load(pid)
    project["draft"]["reel_candidates"][0]["cuts"][0]["end"] = value
    before = copy.deepcopy(project)
    with pytest.raises(ManualEditError):
        reel_proposal(project, "alternative", {})
    assert project == before
