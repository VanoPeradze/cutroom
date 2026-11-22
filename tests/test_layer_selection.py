"""A temporary media/text selection translates in one atomic history operation."""
from __future__ import annotations

import copy
import hashlib

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.layer_selection import prepare_layer_selection_edit
from cutroom.projects import ProjectStore
from test_media_append import content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, post

MEDIA = "media_" + "2" * 32
TEXT = "text_" + "2" * 32
IDS = [MEDIA, "media_" + "3" * 32, "media_" + "4" * 32, TEXT, "text_" + "3" * 32]


@pytest.mark.parametrize("delta", [-2., 1.123456789, 1 / 24, 7.])
@pytest.mark.parametrize("locked", [False, True])
def test_atomic_mixed_move_preserves_all_other_content_one_history_and_exact_reopen(unlocked, delta, locked):
    app, _, store, pid = unlocked
    def prepare(p):
        mixed_layers(p)
        p["manual"]["track_locks"] = {"A": locked, "B": locked}
        p["manual"]["media_clips"][1].update(enabled=False, motion="pan")
        p["manual"]["text_clips"][1]["enabled"] = False
    store.update(pid, prepare)
    before = store.load(pid)
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid) / "media").rglob("*") if p.is_file()}
    response = post(unlocked, "layers_move", clip_ids=IDS, delta=delta)
    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    for key, precision in (("media_clips", 9), ("text_clips", 6)):
        expected = copy.deepcopy(before["manual"][key])
        for row in expected:
            if row["id"] in IDS:
                row.update(start=round(row["start"] + delta, precision), end=round(row["end"] + delta, precision))
        assert after["manual"][key] == expected
    for key, value in before["manual"].items():
        if key not in ("media_clips", "text_clips", "history", "_history"):
            assert after["manual"][key] == value
    for key in ("sources", "assets", "analysis", "settings"):
        assert after[key] == before[key]
    assert after["manual"]["sequence"]["duration"] == 15.
    assert after["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert after["revision"] == before["revision"] + 1
    assert post(unlocked, "undo").status_code == 200
    assert content(store.load(pid)) == content(before)
    assert post(unlocked, "redo").status_code == 200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid)) == content(after)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes} == hashes


@pytest.mark.parametrize("ids", [None, [], [MEDIA], [MEDIA, MEDIA], [MEDIA, "A"], [MEDIA, "automatic_caption"], [MEDIA, "text_" + "f" * 32], [MEDIA, 4], [MEDIA, {}], "both", [MEDIA] * 201])
def test_invalid_membership_never_changes_state(unlocked, ids):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "layers_move", clip_ids=ids, delta=1.)
    assert response.status_code == 400, response.get_json()
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("delta", [None, True, "1", {}, -3., 7.000001, 604801, -604801])
def test_invalid_or_out_of_room_delta_is_atomic_without_individual_clamping(unlocked, delta):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "layers_move", clip_ids=IDS, delta=delta)
    assert response.status_code == 400, response.get_json()
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("delta", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_direct_call_is_atomic(unlocked, delta):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "layers_move", "clip_ids": IDS, "delta": delta})
    assert value == before


@pytest.mark.parametrize("extra", [{"start": 1.}, {"source_start": 2.}, {"enabled": False}, {"clip_id": MEDIA}])
def test_unknown_payload_fields_cannot_change_content(unlocked, extra):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "layers_move", clip_ids=IDS, delta=1., **extra)
    assert response.status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_noop_preserves_raw_bytes_revision_redo_and_validates_members(unlocked):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    assert post(unlocked, "layers_move", clip_ids=IDS, delta=1.).status_code == 200
    assert post(unlocked, "undo").status_code == 200
    before = store.state_path(pid).read_bytes()
    revision = store.load(pid)["revision"]
    for delta in (0., 1e-12):
        response = post(unlocked, "layers_move", clip_ids=IDS, delta=delta)
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["project"]["revision"] == revision
        assert store.state_path(pid).read_bytes() == before
        assert store.load(pid)["manual"]["history"]["redo_count"] == 1
    assert post(unlocked, "layers_move", clip_ids=[MEDIA, "text_" + "f" * 32], delta=0.).status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_revision_required_and_stale_refused_even_for_noop(unlocked):
    _, client, store, pid = unlocked
    store.update(pid, mixed_layers)
    revision = store.load(pid)["revision"]
    store.update(pid, lambda p: p.update(name="Concurrent update"))
    before = store.state_path(pid).read_bytes()
    endpoint = f"/api/projects/{pid}/manual/edit"
    assert client.post(endpoint, json={"action": "layers_move", "clip_ids": IDS, "delta": 1.}).status_code == 400
    for delta in (0., 1.):
        response = post(unlocked, "layers_move", clip_ids=IDS, delta=delta, expected_revision=revision)
        assert response.status_code == 409
        assert store.state_path(pid).read_bytes() == before


def test_busy_job_blocks_group_edit_without_mutation(unlocked, monkeypatch):
    app, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    with monkeypatch.context() as context:
        context.setattr(app.extensions["cutroom_jobs"], "active", lambda **_: [object()])
        response = post(unlocked, "layers_move", clip_ids=IDS, delta=1.)
    assert response.status_code == 409 and response.get_json()["error"] == "project_busy"
    assert store.state_path(pid).read_bytes() == before


def test_validation_failure_does_not_consume_history_in_direct_call(unlocked):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    value["assets"][VIDEO]["status"] = "failed"
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "layers_move", "clip_ids": IDS, "delta": 1.})
    assert value == before


def test_whole_selection_text_overlap_validation_not_sequential_intermediates(unlocked):
    _, _, store, pid = unlocked
    def prepare(p):
        mixed_layers(p)
        # Each original 16-item stack is valid. A sequential left-stack move
        # would temporarily overlap the right stack, but the final move is valid.
        p["manual"]["text_clips"] = [text_row("1", start, start + 1., id=f"text_{i:032x}")
                                            for i in range(32) for start in [1. if i < 16 else 2.]]
    store.update(pid, prepare)
    ids = [row["id"] for row in store.load(pid)["manual"]["text_clips"]]
    assert post(unlocked, "layers_move", clip_ids=ids, delta=1.).status_code == 200
    after = store.load(pid)
    assert [row["start"] for row in after["manual"]["text_clips"]] == [2.] * 16 + [3.] * 16
    assert after["manual"]["history"]["undo_count"] == 1


def test_final_text_overlap_limit_includes_disabled_and_failure_rolls_back_media(unlocked):
    _, _, store, pid = unlocked
    def prepare(p):
        mixed_layers(p)
        p["manual"]["text_clips"] = [text_row("a", 0., 1.)] + [text_row("1", 3., 5., id=f"text_{i:032x}", enabled=False) for i in range(16)]
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "layers_move", clip_ids=[MEDIA, "text_" + "a" * 32], delta=3.)
    assert response.status_code == 400 and "16" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before
    assert post(unlocked, "layers_move", clip_ids=[MEDIA, "text_" + "a" * 32], delta=5.).status_code == 200


@pytest.mark.parametrize("key", ["media_clips", "text_clips"])
def test_duplicate_saved_identity_rejects_before_moving(unlocked, key):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    value["manual"][key].append(copy.deepcopy(value["manual"][key][0]))
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "layers_move", "clip_ids": IDS, "delta": 1.})
    assert value == before


def test_selected_maximum_is_valid_at_media_capacity_without_reordering_or_copy(unlocked):
    _, _, store, pid = unlocked
    def prepare(p):
        mixed_layers(p)
        p["manual"]["media_clips"] = [media_row("1", VIDEO, 1., 2., id=f"media_{i:032x}") for i in range(200)]
        p["manual"]["text_clips"] = []
    store.update(pid, prepare)
    ids = [row["id"] for row in store.load(pid)["manual"]["media_clips"]]
    assert post(unlocked, "layers_move", clip_ids=ids, delta=1.).status_code == 200
    rows = store.load(pid)["manual"]["media_clips"]
    assert len(rows) == 200 and [row["id"] for row in rows] == ids
    assert all(row["start"] == 2. and row["end"] == 3. for row in rows)


def test_preparation_does_not_mutate_payload_or_project_or_normalize_raw_fields(unlocked):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    value["manual"]["media_clips"][1]["enabled"] = True
    value["manual"]["text_clips"][1].update(template="plain", subtext="", enabled=True)
    payload = {"action": "layers_move", "clip_ids": [MEDIA, TEXT], "delta": 1.}
    before, before_payload = copy.deepcopy(value), copy.deepcopy(payload)
    prepared = prepare_layer_selection_edit(value, payload)
    assert value == before and payload == before_payload
    for key in ("media_clips", "text_clips"):
        for old, new in zip(value["manual"][key], prepared[key]):
            assert {k: v for k, v in new.items() if k not in ("start", "end")} == {k: v for k, v in old.items() if k not in ("start", "end")}


@pytest.mark.parametrize("broken", ["media_row", "media_list", "text_row", "text_list", "asset_kind", "asset_duration"])
def test_invalid_saved_layer_data_is_rejected_without_consuming_history(unlocked, broken):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    if broken == "media_row": value["manual"]["media_clips"].append(None)
    elif broken == "media_list": value["manual"]["media_clips"] = {}
    elif broken == "text_row": value["manual"]["text_clips"].append(None)
    elif broken == "text_list": value["manual"]["text_clips"] = {}
    elif broken == "asset_kind": value["assets"][VIDEO]["kind"] = "unknown"
    else: value["assets"][VIDEO]["duration"] = None
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "layers_move", "clip_ids": IDS, "delta": 1.})
    assert value == before


@pytest.mark.parametrize("kind,delta,expected", [
    ("text", .0000005, (4.500001, 5.500001)),
    ("text", -.0000005, (4.5, 5.5)),
    ("text", .00000001, (4.5, 5.5)),
    ("text", -.00000001, (4.5, 5.5)),
    ("text", -.0000015, (4.499999, 5.499999)),
    ("media", .0000000005, (4.500000001, 5.500000001)),
    ("media", -.0000000005, (4.5, 5.5)),
])
def test_halfway_and_tiny_moves_match_javascript_preview_exactly(unlocked, kind, delta, expected):
    _, _, store, pid = unlocked
    key = "text_clips" if kind == "text" else "media_clips"
    def prepare(p):
        mixed_layers(p)
        for row in p["manual"][key][:2]:
            row.update(start=4.5, end=5.5)
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    old = store.load(pid)
    ids = [row["id"] for row in old["manual"][key][:2]]
    response = post(unlocked, "layers_move", clip_ids=ids, delta=delta)
    assert response.status_code == 200, response.get_json()
    current = store.load(pid)
    assert [(row["start"], row["end"]) for row in current["manual"][key][:2]] == [expected, expected]
    if expected == (4.5, 5.5):
        assert store.state_path(pid).read_bytes() == before
    else:
        assert current["revision"] == old["revision"] + 1
        assert post(unlocked, "undo").status_code == 200
        assert content(store.load(pid)) == content(old)


@pytest.mark.parametrize("start,end,delta,allowed", [
    (0., 1., -.0000005, True),
    (0., 1., -.0000006, False),
    (14., 15., .0000004, True),
    (14., 15., .0000005, False),
])
def test_halfway_bounds_use_final_canonical_endpoints_without_extra_clamping(unlocked, start, end, delta, allowed):
    _, _, store, pid = unlocked
    def prepare(p):
        mixed_layers(p)
        p["manual"]["text_clips"] = [text_row("1", start, end), text_row("2", start, end)]
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    ids = [row["id"] for row in store.load(pid)["manual"]["text_clips"]]
    response = post(unlocked, "layers_move", clip_ids=ids, delta=delta)
    assert response.status_code == (200 if allowed else 400), response.get_json()
    # The allowed subprecision translations are no-ops, not silent clamps.
    assert store.state_path(pid).read_bytes() == before
