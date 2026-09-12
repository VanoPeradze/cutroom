from __future__ import annotations

import copy

import pytest

from cutroom.config import load_settings
from cutroom.editing import ManualEditError, _editable_clip_ranges, apply_manual_edit, apply_timeline_overrides
from cutroom.render import _render_plan
from cutroom.utils import invert_ranges, range_duration
from server import create_app


def sample_project() -> dict:
    cuts = [{"start": 0.0, "end": 2.0}, {"start": 8.0, "end": 10.0}, {"start": 16.0, "end": 20.0}]
    keeps = [{"start": 2.0, "end": 8.0}, {"start": 10.0, "end": 16.0}]
    plan = [{**keep, "camera": "A"} for keep in keeps]
    return {
        "id": "project_012345abcdef",
        "sources": {"A": {"duration": 20.0, "relative_path": "media/source-A.mp4"}, "B": None},
        "settings": {},
        "manual": {"cuts": [{"start": 0.0, "end": 1.0}], "keeps": [{"start": 3.0, "end": 4.0}]},
        "draft": {
            "cuts": cuts, "keep_ranges": keeps, "camera_plan": plan,
            "ai_camera_plan": copy.deepcopy(plan), "edit_points": [],
            "output_duration": 12.0, "removed_duration": 8.0,
            "active_reel_candidate": "first",
            "reel_candidates": [{
                "id": "first", "cuts": copy.deepcopy(cuts), "keep_ranges": copy.deepcopy(keeps),
                "ai_camera_plan": copy.deepcopy(plan), "camera_plan": copy.deepcopy(plan), "output_duration": 12.0,
            }],
        },
        "analysis": {
            "transcript": {
                "text": "hello world",
                "segments": [{"id": "s0", "start": 2.0, "end": 4.0, "text": "hello world"}],
            },
            "segments": [{"id": "s0", "start": 2.0, "end": 4.0, "text": "hello world"}],
            "story_hierarchy": {"outline": {}}, "editorial_cache": {"stale": True},
        },
    }


def trim(start=2.0, end=8.0, new_start=3.0, new_end=7.0) -> dict:
    return {"action": "trim_clip", "start": start, "end": end, "new_start": new_start, "new_end": new_end}


def test_trim_updates_ranges_export_and_candidates_as_one_undoable_edit():
    value = sample_project()
    original = copy.deepcopy(value)
    apply_manual_edit(value, trim(new_start=4.0))
    assert value["draft"]["keep_ranges"] == [{"start": 4.0, "end": 7.0}, {"start": 10.0, "end": 16.0}]
    assert value["draft"]["output_duration"] == 9.0
    assert value["draft"]["removed_duration"] == 11.0
    assert value["manual"]["cuts"] == [
        {"start": 0.0, "end": 1.0}, {"start": 2.0, "end": 4.0}, {"start": 7.0, "end": 8.0},
    ]
    assert value["manual"]["keeps"] == []
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert value["draft"]["reel_candidates"][0]["keep_ranges"] == value["draft"]["keep_ranges"]
    assert range_duration(_render_plan(value)) == value["draft"]["output_duration"]
    assert value["sources"] == original["sources"]
    assert value["analysis"] == original["analysis"]
    after = copy.deepcopy(value["draft"])

    apply_manual_edit(value, {"action": "undo"})
    for key in ("cuts", "keep_ranges", "camera_plan", "edit_points", "reel_candidates", "output_duration"):
        assert value["draft"][key] == original["draft"][key]
    assert value["manual"]["cuts"] == original["manual"]["cuts"]
    assert value["manual"]["keeps"] == original["manual"]["keeps"]
    apply_manual_edit(value, {"action": "redo"})
    for key in ("cuts", "keep_ranges", "camera_plan", "edit_points", "reel_candidates", "output_duration"):
        assert value["draft"][key] == after[key]


def test_trim_extends_into_removed_gaps_and_preserves_durable_intent():
    value = sample_project()
    apply_manual_edit(value, trim(new_start=1.0, new_end=9.0))
    assert value["draft"]["keep_ranges"] == [{"start": 1.0, "end": 9.0}, {"start": 10.0, "end": 16.0}]
    assert value["manual"]["cuts"] == [{"start": 0.0, "end": 1.0}]
    assert value["manual"]["keeps"] == [
        {"start": 1.0, "end": 2.0}, {"start": 3.0, "end": 4.0}, {"start": 8.0, "end": 9.0},
    ]
    durable = invert_ranges(apply_timeline_overrides(sample_project()["draft"]["cuts"], value["manual"]), 20)
    assert durable == value["draft"]["keep_ranges"]
    assert range_duration(_render_plan(value)) == 14.0


def test_split_clip_identity_is_retained_when_trim_fills_a_whole_gap():
    value = sample_project()
    apply_manual_edit(value, {"action": "split", "time": 5.0})
    apply_manual_edit(value, trim(start=5, new_start=5, new_end=10))
    assert _editable_clip_ranges(value) == [
        {"start": 2.0, "end": 5.0}, {"start": 5.0, "end": 10.0}, {"start": 10.0, "end": 16.0},
    ]
    apply_manual_edit(value, trim(start=5, end=10, new_start=6, new_end=9))
    assert _editable_clip_ranges(value) == [
        {"start": 2.0, "end": 5.0}, {"start": 6.0, "end": 9.0}, {"start": 10.0, "end": 16.0},
    ]


def test_dense_split_points_match_frontend_clip_identity_and_remain_trimmable():
    value = sample_project()
    # Mirrors editableClips: splits within 30ms of the prior boundary or end
    # are not shown as separate clips, even if old project JSON contains them.
    value["draft"]["edit_points"] = [2.0, 2.01, 5.0, 5.0, 5.01, 7.99, 8.0, float("nan"), 30.0]
    assert _editable_clip_ranges(value) == [
        {"start": 2.0, "end": 5.0}, {"start": 5.0, "end": 8.0}, {"start": 10.0, "end": 16.0},
    ]
    apply_manual_edit(value, trim(start=5, new_start=5, new_end=7))
    assert value["draft"]["keep_ranges"] == [{"start": 2.0, "end": 7.0}, {"start": 10.0, "end": 16.0}]
    assert _editable_clip_ranges(value) == [
        {"start": 2.0, "end": 5.0}, {"start": 5.0, "end": 7.0}, {"start": 10.0, "end": 16.0},
    ]


def test_clip_identity_clamps_deduplicates_overlap_skips_short_ranges_and_rounds():
    value = sample_project()
    value["draft"]["keep_ranges"] = [
        {"start": 6.1234, "end": 25.0}, {"start": -1.0, "end": 3.0},
        {"start": 2.0, "end": 5.0}, {"start": 5.01, "end": 5.02},
        {"start": float("nan"), "end": 10.0},
    ]
    value["draft"]["edit_points"] = [0.0, 3.01, 3.01, -2.0, 20.0, "invalid"]
    assert _editable_clip_ranges(value) == [
        {"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 5.0}, {"start": 6.123, "end": 20.0},
    ]


@pytest.mark.parametrize("payload, message", [
    (trim(start=2.01), "clip has changed"),
    (trim(start=0, end=8), "clip has changed"),
    (trim(new_start=-1), "inside source A"),
    (trim(new_end=21), "inside source A"),
    (trim(new_end=11), "neighbouring kept clip"),
    (trim(start=10, end=16, new_start=7, new_end=15), "neighbouring kept clip"),
    (trim(new_start=7, new_end=3), "at least 0.08"),
    (trim(new_start=3, new_end=3.05), "at least 0.08"),
    (trim(new_start=float("nan")), "must be finite"),
    (trim(new_end=float("inf")), "must be finite"),
    (trim(new_start=True), "must be a number"),
    (trim(new_end=None), "must be a number"),
])
def test_invalid_or_stale_trim_leaves_project_and_history_unchanged(payload, message):
    value = sample_project()
    original = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match=message):
        apply_manual_edit(value, payload)
    assert value == original


def test_trim_rejects_old_unsplit_identity_after_a_split():
    value = sample_project()
    apply_manual_edit(value, {"action": "split", "time": 5.0})
    original = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="clip has changed"):
        apply_manual_edit(value, trim())
    assert value == original
    with pytest.raises(ManualEditError, match="neighbouring kept clip"):
        apply_manual_edit(value, trim(start=5, new_start=4))
    assert value == original


@pytest.mark.parametrize("payload", [trim(new_start=2, new_end=9.95), trim(new_start=3, new_end=3.08)])
def test_precision_edges_are_rejected_atomically_instead_of_changing_other_clips(payload):
    value = sample_project()
    original = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="exact requested boundaries.*0.081"):
        apply_manual_edit(value, payload)
    assert value == original


def test_81ms_clip_is_preserved_and_noop_adds_no_history():
    value = sample_project()
    original = copy.deepcopy(value)
    apply_manual_edit(value, trim(new_start=2, new_end=8))
    assert value == original
    apply_manual_edit(value, trim(start=2.0009, end=8.0009, new_start=3, new_end=3.081))
    assert value["draft"]["keep_ranges"][0] == {"start": 3.0, "end": 3.081}


def api_project(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("trim-api")
    sample = sample_project()
    value.update({key: sample[key] for key in ("sources", "analysis", "draft", "manual")})
    return app, store, store.save(value)


def test_trim_api_whitelist_revision_checks_and_atomic_rejection(monkeypatch, tmp_path):
    app, store, value = api_project(monkeypatch, tmp_path)
    client = app.test_client()
    endpoint = f"/api/projects/{value['id']}/manual/edit"
    rejected = client.post(endpoint, json={**trim(new_end=11), "expected_revision": value["revision"]})
    assert rejected.status_code == 400
    assert store.load(value["id"]) == value
    response = client.post(endpoint, json={**trim(), "expected_revision": value["revision"]})
    assert response.status_code == 200
    result = response.get_json()["project"]
    assert result["draft"]["output_duration"] == 10.0
    assert result["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert "_history" not in result["manual"]
    assert client.post(endpoint, json={**trim(), "expected_revision": value["revision"]}).status_code == 409


def test_transcript_correction_api_is_available_after_story_failure_without_draft(monkeypatch, tmp_path):
    app, store, value = api_project(monkeypatch, tmp_path)
    value["draft"] = None
    value = store.save(value)
    endpoint = f"/api/projects/{value['id']}/manual/edit"
    client = app.test_client()
    response = client.post(endpoint, json={
        "action": "transcript_text", "segment_id": "s0", "text": "corrected transcript",
        "expected_revision": value["revision"],
    })
    assert response.status_code == 200
    result = response.get_json()["project"]
    assert result["draft"] is None
    assert result["analysis"]["transcript"]["text"] == "corrected transcript"
    assert result["analysis"]["segments"][0]["text"] == "corrected transcript"
    assert "story_hierarchy" not in result["analysis"]
    assert "editorial_cache" not in result["analysis"]
    undo = client.post(endpoint, json={"action": "undo", "expected_revision": result["revision"]})
    assert undo.status_code == 200
    assert undo.get_json()["project"]["analysis"]["transcript"]["text"] == "hello world"
    assert undo.get_json()["project"]["draft"] is None
