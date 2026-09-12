"""Visual source review must edit the current sequence, not the stale AI mask."""
import copy
import json

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.sequence import editor_sequence_snapshot
from cutroom.source_tracks import timeline_duration
from test_sequence_editing import project, edit, geometry
from test_source_tracks_api import post, track_api


def review(value, action, start, end, slot="A", scope="edit"):
    return edit(value, f"source_{action}", slot=slot, scope=scope, source_start=start, source_end=end)


def test_restore_missing_only_in_original_order_and_both_sources():
    value = project()
    original = copy.deepcopy(value)
    review(value, "restore", 2, 12)
    assert geometry(value) == [(0, 4, 0), (4, 10, 4), (10, 16, 10)]
    assert geometry(value, "B") == geometry(value)
    assert timeline_duration(value) == 16
    before = copy.deepcopy(value)
    review(value, "restore", 2, 12)
    assert value == before, "repeated restore must be a no-op"
    assert all(value["draft"][key] == item for key, item in original["draft"].items())
    assert value["analysis"] == original["analysis"]
    apply_manual_edit(value, {"action": "undo"})
    assert editor_sequence_snapshot(value) == editor_sequence_snapshot(original)
    apply_manual_edit(value, {"action": "redo"})
    assert timeline_duration(value) == 16


@pytest.mark.parametrize("slot", ["A", "B"])
def test_restore_pair_uses_original_sync(slot):
    value = project()
    value["analysis"]["sync"]["offset"] = 2
    review(value, "restore", 4 if slot == "A" else 2, 10 if slot == "A" else 8, slot=slot)
    view = editor_sequence_snapshot(value)
    a = next(c for c in view["source_tracks"]["A"] if c["source_start"] == 4)
    b = next(c for c in view["source_tracks"]["B"] if c["source_start"] == 2)
    assert (a["start"], a["end"]) == (b["start"], b["end"])
    assert timeline_duration(value) == 16


def test_remove_all_copies_is_one_undo_and_preserves_other_framing():
    value = project()
    edit(value, "crop", slot="A", start=4, end=10, x=.9, y=.5, zoom=1)
    edit(value, "duplicate_range", start=0, end=4, to=10)
    before = copy.deepcopy(value)
    review(value, "remove", 1, 3)
    assert timeline_duration(value) == 10
    assert all(not (c[2] < 3 and c[2] + c[1] - c[0] > 1) for c in geometry(value))
    assert next(c for c in value["manual"]["source_tracks"]["A"] if c["source_start"] == 10)["crop"]["x"] == .9
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["source_tracks"] == before["manual"]["source_tracks"]


@pytest.mark.parametrize("slot", ["A", "B"])
def test_source_only_remove_restore_refills_hole_without_changing_other_track(slot):
    value = project()
    before = editor_sequence_snapshot(value)
    review(value, "remove", 1, 3, slot=slot, scope=slot)
    assert timeline_duration(value) == 10
    review(value, "restore", 1, 3, slot=slot, scope=slot)
    assert geometry(value, slot) == [(0, 1, 0), (1, 3, 1), (3, 4, 3), (4, 10, 10)]
    other = "B" if slot == "A" else "A"
    assert value["manual"]["source_tracks"][other] == before["source_tracks"][other]
    assert timeline_duration(value) == 10


def test_restore_empty_edit_and_tail_and_reopen():
    value = project()
    review(value, "remove", 0, 20)
    assert timeline_duration(value) == 0
    review(value, "restore", 16, 20)
    assert geometry(value) == [(0, 4, 16)]
    value = json.loads(json.dumps(value))
    review(value, "restore", 0, 4)
    assert geometry(value) == [(0, 4, 0), (4, 8, 16)]


def test_restore_after_reordering_keeps_existing_relative_order():
    value = project()
    edit(value, "move_range", start=0, end=4, to=6)
    review(value, "restore", 4, 10)
    assert geometry(value) == [(0, 6, 4), (6, 12, 10), (12, 16, 0)]


def test_single_embedded_source_restores_its_layout_without_inventing_b():
    value = project()
    del value["sources"]["B"]
    value["draft"]["layout"] = "embedded_stack"
    for row in value["draft"]["camera_plan"]:
        row["camera"] = "embedded_stack"
    review(value, "restore", 4, 10)
    assert geometry(value, "B") == []
    assert all(row["camera"] == "embedded_stack" for row in value["manual"]["sequence"]["camera_plan"])


def test_empty_independent_track_restores_at_start_not_at_end_of_other_source():
    value = project()
    other = editor_sequence_snapshot(value)["source_tracks"]["B"]
    review(value, "remove", 0, 20, scope="A")
    review(value, "restore", 0, 4, scope="A")
    assert geometry(value) == [(0, 4, 0)]
    assert value["manual"]["source_tracks"]["B"] == other


@pytest.mark.parametrize("bad", [[], {}])
def test_invalid_slot_type_has_a_validation_error(bad):
    with pytest.raises(ManualEditError):
        review(project(), "restore", 4, 10, slot=bad)


@pytest.mark.parametrize("start,end,slot,scope", [(-1,2,"A","edit"),(0,21,"A","edit"),(2,2,"A","edit"),(0,2,"B","A"),(float("nan"),2,"A","edit")])
def test_invalid_review_atomic(start, end, slot, scope):
    value = project()
    original = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        review(value, "restore", start, end, slot, scope)
    assert value == original


@pytest.mark.parametrize("fps", [30,60])
def test_frame_interval_is_restorable(fps):
    value = project()
    value["settings"]["fps"] = fps
    review(value, "remove", 1, 1+1/fps)
    review(value, "restore", 1, 1+1/fps)
    assert timeline_duration(value) == 10


def test_source_review_api_revision_reopen_and_undo(track_api):
    client, store, project_id = track_api
    removed = post(track_api,{"action":"sequence_source_remove","slot":"A","scope":"edit","source_start":2,"source_end":4})
    assert removed.status_code == 200, removed.get_json()
    revision = removed.get_json()["project"]["revision"]
    restored = post(track_api,{"action":"sequence_source_restore","slot":"A","scope":"edit","source_start":2,"source_end":4})
    assert restored.status_code == 200, restored.get_json()
    assert restored.get_json()["project"]["editor_sequence"]["duration"] == 20
    stale = post(track_api,{"action":"sequence_source_remove","slot":"A","scope":"edit","source_start":2,"source_end":4}, revision=revision)
    assert stale.status_code == 409
    undone = post(track_api,{"action":"undo"})
    assert undone.status_code == 200
    assert client.get(f"/api/projects/{project_id}").get_json()["project"]["editor_sequence"]["duration"] == 18
