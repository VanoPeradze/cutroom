"""Saved AI proposal identity and exact, byte-preserving review transactions.

Synthetic saved drafts and stub source bytes are deliberately not AI quality or
playback evidence. Native/encoded acceptance is recorded separately.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
import pytest
from cutroom import director
from cutroom.ai_draft_proposals import ai_draft_review_status, record_ai_draft_proposal
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.sequence import editor_sequence_snapshot
from server import _public_project
from test_reel_proposals import api as base_api
from test_director_rebuild_cache import semantic_project


@pytest.fixture
def api(base_api):
    app, client, store, pid, media = base_api
    def prepare(p):
        p["manual"] = {"cuts": [], "keeps": [], "camera_overrides": [], "track_locks": {"A": False, "B": False}, "crop": {"A": {"zoom": 1.1, "x": .1, "y": .2}}, "source_mixer": {"audio_slot": "A"}}
        p["draft"] = {"engine": "synthetic_ai_review", "title": "Current original draft", "source_duration": 20., "output_duration": 20., "keep_ranges": [{"start": 0., "end": 20.}], "cuts": [], "camera_plan": [{"start": 0., "end": 20., "camera": "A"}]}
        apply_manual_edit(p, {"action": "sequence_split_all", "time": 10.})
        p["settings"].update(instruction="Keep the original meaning.", edit_style="smart", duration_mode="target", target_duration=12)
        p["draft"].update(title="Synthetic proposed selection", summary="Unverified fixture, not AI quality evidence.", output_duration=12., keep_ranges=[{"start": 2., "end": 8.}, {"start": 12., "end": 18.}], cuts=[{"start": 0., "end": 2.}, {"start": 8., "end": 12.}, {"start": 18., "end": 20.}])
        record_ai_draft_proposal(p)
    store.update(pid, prepare)
    return base_api


def review(api, **overrides):
    _, client, store, pid, _ = api
    current = store.load(pid)
    return client.post(f"/api/projects/{pid}/ai-draft-proposal", json={"origin_id": ai_draft_review_status(current).get("origin_id"), "expected_revision": current["revision"], **overrides})


def post(api, action, **fields):
    _, client, store, pid, _ = api
    return client.post(f"/api/projects/{pid}/manual/edit", json={"action": action, "expected_revision": store.load(pid)["revision"], **fields})


def apply(api, proposal, **fields):
    return post(api, "apply_ai_draft", proposal_id=proposal["proposal_id"], expected_revision=proposal["revision"], **fields)


def test_review_is_read_only_and_compares_actual_reset_not_nominal_candidate(api):
    _, client, store, pid, media = api
    before = store.state_path(pid).read_bytes(); original = media.read_bytes()
    response = review(api)
    assert response.status_code == 200, response.get_json()
    proposal = response.get_json()["proposal"]
    assert proposal["current"] == {"duration": 20., "source_clip_counts": {"A": 2, "B": 0}, "media_count": 0, "text_count": 0}
    assert proposal["impact"] == {"duration": 12., "source_clip_counts": {"A": 2, "B": 0}, "media_preserved": True, "text_preserved": True}
    assert proposal["apply_allowed"] is True and proposal["apply_issue"] == ""
    assert proposal["status"] == "needs_user_review" and proposal["semantic_approval"] is False
    assert proposal["proposed"]["source_slot"] == "A"
    assert "source B" in proposal["warnings"][0]
    assert review(api).get_json() == response.get_json()
    assert store.state_path(pid).read_bytes() == before and media.read_bytes() == original
    public = client.get(f"/api/projects/{pid}").get_json()["project"]
    assert public["ai_draft_review"]["pending"] is True and "_ai_draft_proposal" not in public


def test_apply_undo_redo_reopen_and_later_edit_do_not_resurrect_consumed_proposal(api):
    app, _, store, pid, media = api
    before = store.load(pid); original = media.read_bytes(); proposal = review(api).get_json()["proposal"]
    response = apply(api, proposal)
    assert response.status_code == 200, response.get_json()
    applied = store.load(pid)
    assert not response.get_json()["project"]["ai_draft_review"]["available"]
    assert "sequence" not in applied["manual"]
    assert applied["manual"]["ai_draft_applied"] == proposal["origin_id"]
    assert editor_sequence_snapshot(applied)["duration"] == 12
    for key in ("settings", "analysis", "assets", "sources", "_ai_draft_proposal"): assert applied.get(key) == before.get(key)
    for key in ("crop", "source_mixer", "track_locks"): assert applied["manual"][key] == before["manual"][key]
    assert post(api, "undo").status_code == 200
    undone = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert ai_draft_review_status(undone)["available"]
    assert editor_sequence_snapshot(undone) == editor_sequence_snapshot(before)
    assert "ai_draft_applied" not in undone["manual"]
    assert post(api, "redo").status_code == 200
    assert post(api, "sequence_split_all", time=1.).status_code == 200
    reopened = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert "sequence" in reopened["manual"] and not ai_draft_review_status(reopened)["available"]
    assert media.read_bytes() == original


def test_generation_identity_is_durable_without_jobs_and_keeps_actual_generation_request(api):
    _, _, store, pid, _ = api
    before = store.load(pid); origin = ai_draft_review_status(before)["origin_id"]
    store.update(pid, lambda p: p["settings"].update(instruction="Later preferences, not generation request."))
    proposal = review(api).get_json()["proposal"]
    assert proposal["origin_id"] == origin
    assert proposal["request"]["instruction"] == "Keep the original meaning."
    assert ai_draft_review_status(store.load(pid))["pending"]


def test_legacy_draft_is_labeled_saved_not_new_and_becomes_consumed(api):
    _, _, store, pid, _ = api
    store.update(pid, lambda p: (p.pop("_ai_draft_proposal"), None)[1])
    status = ai_draft_review_status(store.load(pid))
    assert status["available"] and status["legacy"] and not status["pending"]
    proposal = review(api).get_json()["proposal"]
    assert "not recorded" in proposal["request"]["instruction"]
    assert apply(api, proposal).status_code == 200
    assert post(api, "sequence_split_all", time=1.).status_code == 200
    assert not ai_draft_review_status(store.load(pid))["available"]


@pytest.mark.parametrize("change", ["title", "range", "source", "bad-marker"])
def test_changed_provenance_fails_closed_without_legacy_downgrade(api, change):
    _, _, store, pid, _ = api
    def mutate(p):
        if change == "title": p["draft"]["title"] = "Different draft"
        elif change == "range": p["draft"]["keep_ranges"][0]["start"] = 3
        elif change == "source": p["sources"]["A"]["generation"] = "replaced"
        else: p["_ai_draft_proposal"] = {"version": 1}
    store.update(pid, mutate)
    before = store.state_path(pid).read_bytes()
    assert not ai_draft_review_status(store.load(pid))["available"]
    assert review(api, origin_id="old").status_code == 409
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("bad", [None, True, 0, "1", -1])
def test_review_requires_positive_pinned_revision(api, bad):
    _, _, store, pid, _ = api; before = store.state_path(pid).read_bytes()
    assert review(api, expected_revision=bad).status_code == 400
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("fields", [{}, {"proposal_id": "bad"}, {"proposal_id": "a"*64, "expected_revision": None}, {"proposal_id": "a"*64, "start": 0}])
def test_apply_requires_exact_review_without_incidental_edits(api, fields):
    _, _, store, pid, _ = api; before = store.state_path(pid).read_bytes()
    assert post(api, "apply_ai_draft", **fields).status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_revision_and_media_identity_staleness_never_applies(api):
    _, _, store, pid, media = api; proposal = review(api).get_json()["proposal"]
    store.update(pid, lambda p: p["settings"].update(instruction="Changed after review"))
    before = store.state_path(pid).read_bytes()
    assert apply(api, proposal).status_code == 409
    assert store.state_path(pid).read_bytes() == before
    response = post(api, "apply_ai_draft", proposal_id=proposal["proposal_id"])
    assert response.status_code == 409 and response.get_json()["error"] == "stale_ai_draft_proposal"
    proposal = review(api).get_json()["proposal"]
    media.write_bytes(b"Different original bytes; deliberate test-only replacement")
    assert apply(api, proposal).status_code == 409
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("layer", ["text", "media"])
def test_long_retained_layer_blocks_actual_reset_but_allows_read_only_inspection(api, layer):
    _, _, store, pid, _ = api
    if layer == "text":
        assert post(api, "text_add", kind="title", start=15., end=19., text="Keep this title").status_code == 200
    else:
        aid = "asset_"+"a"*32
        def asset(p):
            p.setdefault("assets", {})[aid] = {"id": aid, "kind": "image", "status": "ready", "path": f"media/assets/{aid}/original.png", "width": 100, "height": 100}
        path = store.project_dir(pid)/f"media/assets/{aid}/original.png"
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"identity only")
        store.update(pid, asset)
        assert post(api, "media_add", asset_id=aid, start=15., end=19.).status_code == 200
    before = store.state_path(pid).read_bytes()
    response = review(api); assert response.status_code == 200, response.get_json()
    proposal = response.get_json()["proposal"]
    assert not proposal["apply_allowed"] and proposal["apply_issue"]
    assert apply(api, proposal).status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_unexpected_draft_impact_error_stays_private_and_blocks_apply(api, monkeypatch):
    from cutroom import editing

    _, _, store, pid, _ = api
    previous = store.state_path(pid).read_bytes()
    diagnostic = "Internal draft impact fixture (never client-facing)"
    actual_edit = editing.apply_manual_edit

    def broken(project, payload, **kwargs):
        if kwargs.get("apply_isolated_proposal") and payload.get("action") == "sequence_reset":
            raise ValueError(diagnostic)
        return actual_edit(project, payload, **kwargs)

    monkeypatch.setattr(editing, "apply_manual_edit", broken)
    response = review(api)
    assert response.status_code == 200
    proposal = response.get_json()["proposal"]
    assert proposal["apply_allowed"] is False and proposal["impact"] is None
    assert "Keep the current edit" in proposal["apply_issue"]
    assert diagnostic not in response.get_data(as_text=True)
    denied = apply(api, proposal)
    assert denied.status_code == 400 and diagnostic not in denied.get_data(as_text=True)
    assert store.state_path(pid).read_bytes() == previous


def test_source_lock_and_missing_file_preserve_everything(api):
    _, _, store, pid, media = api
    store.update(pid, lambda p: p["manual"]["track_locks"].update(A=True))
    before = store.state_path(pid).read_bytes()
    proposal = review(api).get_json()["proposal"]
    assert not proposal["apply_allowed"] and "lock" in proposal["apply_issue"].lower()
    assert apply(api, proposal).status_code == 400
    media.rename(media.with_suffix('.missing'))
    assert review(api).status_code == 409
    assert store.state_path(pid).read_bytes() == before


def test_concurrent_double_apply_commits_at_most_once(api):
    _, _, store, pid, _ = api
    proposal = review(api).get_json()["proposal"]
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(lambda _: apply(api, proposal).status_code, range(2)))
    assert sorted(results) == [200, 409]
    assert store.load(pid)["manual"]["history"]["undo_count"] == 2


def test_actual_director_commit_records_new_identity_preserves_history_and_undo(semantic_project):
    store, settings, pid, _, context = semantic_project
    store.update(pid, lambda p: apply_manual_edit(p, {"action": "sequence_split_all", "time": 10.}))
    before = store.load(pid)
    result = director.analyze_project(context(), pid, store, settings, {"edit_style": "competitive_clutch"})
    saved = store.load(pid)
    status = ai_draft_review_status(saved)
    assert result["timeline_preserved"] and status["available"] and status["pending"] and not status["legacy"]
    assert saved["manual"] == before["manual"]
    assert saved["_ai_draft_proposal"]["request"]["style"] == "competitive_clutch"
    assert _public_project(saved)["ai_draft_review"] == status
    store.update(pid, lambda p: apply_manual_edit(p, {"action": "sequence_reset"}, apply_isolated_proposal=True))
    assert not ai_draft_review_status(store.load(pid))["available"]
    store.update(pid, lambda p: apply_manual_edit(p, {"action": "undo"}))
    assert ai_draft_review_status(store.load(pid))["origin_id"] == status["origin_id"]


@pytest.mark.parametrize("engine", ["manual", "manual_source_review", ""])
def test_user_selected_sources_never_acquire_ai_provenance(api, engine):
    _, _, store, pid, _ = api
    def mutate(p): p.pop("_ai_draft_proposal", None); p["draft"]["engine"] = engine
    store.update(pid, mutate)
    assert not ai_draft_review_status(store.load(pid))["available"]


def test_busy_job_blocks_read_and_apply_without_writes(api, monkeypatch):
    app, _, store, pid, _ = api; proposal = review(api).get_json()["proposal"]
    before = store.state_path(pid).read_bytes()
    with monkeypatch.context() as context:
        context.setattr(app.extensions["cutroom_jobs"], "active", lambda **_: [object()])
        assert review(api).get_json()["error"] == "project_busy"
        assert apply(api, proposal).get_json()["error"] == "project_busy"
    assert store.state_path(pid).read_bytes() == before


def test_chroma_background_dependency_is_pinned_even_without_occurrence(api):
    _, _, store, pid, _ = api; aid = "asset_"+"b"*32
    path = store.project_dir(pid)/f"media/assets/{aid}/original.png"
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"identity only")
    def configure(p):
        p.setdefault("assets", {})[aid] = {"id": aid, "kind": "image", "status": "ready", "path": f"media/assets/{aid}/original.png", "width": 100, "height": 100}
        p["manual"]["chroma_key"] = {"A": {"enabled": True, "background_mode": "solid", "background_asset_id": aid}}
    store.update(pid, configure)
    proposal = review(api).get_json()["proposal"]; before = store.state_path(pid).read_bytes()
    path.write_bytes(b"replaced background identity only")
    assert apply(api, proposal).status_code == 409
    assert store.state_path(pid).read_bytes() == before


def test_in_bounds_retained_text_is_exact_in_review_apply_and_undo(api):
    _, _, store, pid, _ = api
    assert post(api, "text_add", kind="title", start=1., end=4., text="Exact retained title").status_code == 200
    before = store.load(pid); proposal = review(api).get_json()["proposal"]
    assert proposal["current"]["text_count"] == 1 and proposal["impact"]["text_preserved"]
    assert apply(api, proposal).status_code == 200
    assert store.load(pid)["manual"]["text_clips"] == before["manual"]["text_clips"]
    assert post(api,"undo").status_code == 200
    assert store.load(pid)["manual"]["text_clips"] == before["manual"]["text_clips"]
    assert ai_draft_review_status(store.load(pid))["available"]


@pytest.mark.parametrize("action,fields", [("sequence_split_all", {"time": 1.}), ("text_add", {"kind": "title", "start": 0., "end": 2., "text": "New title"})])
def test_ordinary_edit_then_undo_preserves_pending_generation_identity(api, action, fields):
    _, _, store, pid, _ = api; before = ai_draft_review_status(store.load(pid))
    assert post(api, action, **fields).status_code == 200
    assert ai_draft_review_status(store.load(pid)) == before
    assert post(api, "undo").status_code == 200
    assert ai_draft_review_status(store.load(pid)) == before


def test_new_generation_after_apply_has_new_pending_identity(api):
    _, _, store, pid, _ = api; proposal = review(api).get_json()["proposal"]
    assert apply(api, proposal).status_code == 200
    assert post(api, "sequence_split_all", time=1.).status_code == 200
    store.update(pid, record_ai_draft_proposal)
    status = ai_draft_review_status(store.load(pid))
    assert status["available"] and status["origin_id"] != proposal["origin_id"]
    assert review(api).get_json()["proposal"]["apply_allowed"]


@pytest.mark.parametrize("bad", [True, "1", -1, float("inf"), None])
def test_invalid_passages_never_offer_apply_or_mutate(api, bad):
    _, _, store, pid, _ = api
    # Pure helper exercises non-JSON/nonfinite input without corrupting store.
    from cutroom.ai_draft_proposals import ai_draft_proposal
    from cutroom.editing import ManualEditError
    p = store.load(pid); p.pop("_ai_draft_proposal"); p["draft"]["keep_ranges"][0]["start"] = bad
    before = copy.deepcopy(p); origin = ai_draft_review_status(p).get("origin_id")
    with pytest.raises(ManualEditError): ai_draft_proposal(p, origin, {})
    assert p == before


def test_two_source_review_counts_real_restored_tracks_not_just_candidate_ranges(api):
    _, _, store, pid, media = api
    def configure(p):
        p["sources"]["B"] = {**p["sources"]["A"], "generation": "fixture-B"}
        p["manual"]["source_tracks"]["B"] = [{"id": "B:"+"b"*32, "start": 0., "end": 20., "source_start": 0.}]
        p["manual"]["sequence"]["base_source_tracks"] = {"A": [{"id": "A:"+"a"*32,"start":0.,"end":20.,"source_start":0.}], "B": []}
        record_ai_draft_proposal(p)
    store.update(pid, configure)
    response = review(api); assert response.status_code == 200, response.get_json()
    proposal = response.get_json()["proposal"]
    assert proposal["current"]["source_clip_counts"]["B"] == 1
    assert proposal["impact"]["source_clip_counts"]["B"] == 0
    assert apply(api, proposal).status_code == 200
    assert store.load(pid)["manual"]["source_tracks"]["B"] == []
    assert post(api,"undo").status_code == 200
    assert len(store.load(pid)["manual"]["source_tracks"]["B"]) == 1
