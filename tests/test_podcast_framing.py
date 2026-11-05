"""Manual participant crop presets use the real sequence/API/Undo path."""
import copy

import pytest

from test_caption_alternatives import api, saved, load, proposal, apply  # noqa: F401
from cutroom.caption_alternatives import status, _legacy_geometry
from cutroom.render import _frame_aligned_plan, project_caption_items


def portrait(api):
    _, _, store, pid = api
    def prepare(p):
        p["sources"]["A"].update(width=1080, height=1920, rotation=0)
        p["settings"]["aspect"] = "9:16"
    return store.update(pid, prepare)


def frame(api, focus="top", **overrides):
    _, client, store, pid = api
    return client.post(f"/api/projects/{pid}/manual/edit", json={"action": "sequence_podcast_frame", "slot": "A", "start": 2., "end": 6.,
        "focus": focus, "panel_split": .5, "source_generation": "source-v1", "confirmed_stacked_clean": True,
        "expected_revision": store.load(pid)["revision"], **overrides})


@pytest.mark.parametrize("focus,y,zoom", [("both", .5, 1.), ("top", 0., 2.004175), ("bottom", 1., 2.004175)])
def test_real_apply_preview_plan_undo_redo_preserve_source_audio_and_caption_clock(api, focus, y, zoom):
    _, client, store, pid = api
    before = portrait(api); captions = project_caption_items(before)
    response = frame(api, focus); assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    assert after["sources"] == before["sources"] and after["analysis"] == before["analysis"]
    assert after["settings"] == before["settings"]
    rows = after["manual"]["source_tracks"]["A"]
    assert [(r["start"], r["end"], r["source_start"]) for r in rows] == [(0., 2., 0.), (2., 6., 2.), (6., 8., 6.)]
    assert "crop" not in rows[0] and "crop" not in rows[2]
    assert rows[1]["crop"] == {"x": .5, "y": y, "zoom": zoom}
    plan = _frame_aligned_plan(after)
    selected = [r for r in plan if r["start"] == 2. and r["end"] == 6.]
    assert selected and selected[0]["crop"]["A"] == rows[1]["crop"]
    assert [{k:i[k] for k in ("text", "start", "end")} for i in project_caption_items(after)] == [{k:i[k] for k in ("text", "start", "end")} for i in captions]
    for action, expected_crop in [("undo", False), ("redo", True)]:
        result = client.post(f"/api/projects/{pid}/manual/edit", json={"action": action, "expected_revision": store.load(pid)["revision"]})
        assert result.status_code == 200, result.get_json()
        assert any("crop" in r for r in _frame_aligned_plan(store.load(pid))) is expected_crop


def test_visual_crop_keeps_alternative_and_manual_caption_corrections_active(api):
    _, client, store, pid = api
    before = portrait(api); key = load(api, saved(before))
    assert apply(api, proposal(api, key)).status_code == 200
    item = project_caption_items(store.load(pid))[0]
    r = client.post(f"/api/projects/{pid}/manual/edit", json={"action":"caption_update", "caption_id":item["id"], "scope":"source", "text":"Explicit caption edit", "expected_revision":store.load(pid)["revision"]})
    assert r.status_code == 200
    before = store.load(pid)
    assert frame(api).status_code == 200
    after = store.load(pid)
    assert status(after)["active_id"] == key
    assert after["manual"]["caption_corrections"] == before["manual"]["caption_corrections"]
    assert project_caption_items(after)[0]["text"] == "Explicit caption edit"


def test_existing_saved_selection_is_upgraded_only_while_its_source_binding_is_valid(api):
    _, _, store, pid = api
    before = portrait(api); key = load(api, saved(before))
    assert apply(api, proposal(api, key)).status_code == 200
    def legacy(p): p["manual"]["caption_alternative"]["geometry"] = _legacy_geometry(p)
    store.update(pid, legacy)
    assert status(store.load(pid))["active_id"] == key
    assert frame(api).status_code == 200
    assert status(store.load(pid))["active_id"] == key


@pytest.mark.parametrize("focus,panel_height", [("top", 1200), ("bottom", 800)])
def test_marked_unequal_panels_stay_inside_the_selected_source_region(api, focus, panel_height):
    _, _, store, pid = api
    portrait(api)
    def shape(p): p["sources"]["A"].update(width=1000, height=2000); p["settings"]["aspect"]="source"
    store.update(pid, shape)
    assert frame(api, focus, panel_split=.6).status_code == 200
    row = next(r for r in store.load(pid)["manual"]["source_tracks"]["A"] if r["start"]==2)
    assert 2000 / row["crop"]["zoom"] <= panel_height - 1
    assert 1 < row["crop"]["zoom"] <= 3


@pytest.mark.parametrize("problem", ["unconfirmed", "stale_source", "aspect", "landscape", "rotation", "second_source", "burned_captions", "locked", "gap", "layout", "bad_focus", "bad_divider"])
def test_unsupported_assumptions_reject_without_mutation(api, problem):
    _, _, store, pid = api
    portrait(api)
    extra = {}
    def mutate(p):
        if problem == "aspect": p["settings"]["aspect"] = "16:9"
        elif problem == "landscape": p["sources"]["A"].update(width=1920, height=1080)
        elif problem == "rotation": p["sources"]["A"]["rotation"] = 90
        elif problem == "second_source": p["sources"]["B"] = copy.deepcopy(p["sources"]["A"])
        elif problem == "burned_captions": p["sources"]["A"]["has_burned_captions"] = True
        elif problem == "locked": p["manual"]["track_locks"] = {"A":True}
        elif problem == "gap": p["manual"]["source_tracks"] = {"A":[{"id":"A:gap", "start":0., "end":3., "source_start":0.}], "B":[]}
        elif problem == "layout": p["draft"]["camera_plan"] = [{"start":0., "end":8., "camera":"embedded_stack"}]
    store.update(pid, mutate)
    if problem == "unconfirmed": extra["confirmed_stacked_clean"] = False
    if problem == "stale_source": extra["source_generation"] = "old"
    if problem == "bad_focus": extra["focus"] = []
    if problem == "bad_divider": extra["panel_split"] = .2
    before = store.state_path(pid).read_bytes()
    response = frame(api, **extra)
    assert response.status_code == 400, response.get_json()
    assert response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before
