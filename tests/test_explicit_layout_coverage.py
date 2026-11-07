"""Missing B uses available A explicitly; unsafe layout gaps still reject."""
import copy

import pytest

from cutroom.editing import apply_manual_edit
from cutroom.render import LayoutCoverageError, _render_plan, composition_layout_coverage, require_layout_coverage
from test_caption_alternatives import api  # noqa: F401


def project():
    return {
        "settings": {"aspect": "9:16", "fps": 30, "layout": "A", "edit_style": "stream_commentary",
                     "target_duration": 180, "output_count": 1},
        "sources": {"A": {"duration": 2300., "video_duration": 2300., "width": 1920, "height": 1080},
                    "B": {"duration": 158.35, "video_duration": 158.35, "width": 1920, "height": 1080}},
        "draft": {"keep_ranges": [{"start": 245., "end": 425.}],
                  "camera_plan": [{"start": 245., "end": 425., "camera": "stacked"}]},
        "manual": {"source_mixer": {"screen_slot": "A", "camera_slot": "B", "first_slot": "B",
                                    "primary_role": "screen", "default_layout": "stacked", "sync_offset": 0.},
                   "sequence": {"version": 1, "duration": 180., "camera_plan": [{"start": 0., "end": 180., "camera": "stacked"}]},
                   "source_tracks": {"A": [{"id": "a", "start": 0., "end": 180., "source_start": 245.}], "B": []}},
    }


def test_missing_camera_is_reported_before_safe_fallback_erases_requested_layout():
    p = project(); original = copy.deepcopy(p)
    assert {row["camera"] for row in _render_plan(p)} == {"A"}
    report = composition_layout_coverage(p)
    assert report["requested_seconds"] == report["missing_seconds"] == 180.
    assert not report["export_blocked"] and report["fallback_available"] and report["clock"] == "edit"
    assert require_layout_coverage(p)["missing_seconds"] == 180.
    assert p == original


def test_independent_camera_mapping_is_explicit_and_never_repeats_the_short_source():
    p = project()
    result = apply_manual_edit(p, {"action": "sequence_insert", "slot": "B", "start": 0., "source_start": 0., "source_end": 158.35})
    assert result
    report = composition_layout_coverage(p)
    assert report["missing_seconds"] == pytest.approx(21.666667, abs=.04)
    assert not report["export_blocked"] and report["fallback_available"]
    assert p["manual"]["source_tracks"]["B"][0]["source_start"] == 0.
    assert p["settings"]["target_duration"] == 180


def test_explicit_independent_ranges_can_meet_the_split_without_changing_source_offsets():
    p = project(); p["manual"]["sequence"]["duration"] = 4.
    p["manual"]["sequence"]["camera_plan"][0]["end"] = 4.
    p["manual"]["source_tracks"]["A"][0]["end"] = 4.
    apply_manual_edit(p, {"action": "sequence_insert", "slot": "B", "start": 0., "source_start": 0., "source_end": 4.})
    require_layout_coverage(p)
    assert {row["camera"] for row in _render_plan(p)} == {"stacked"}
    assert p["manual"]["source_tracks"]["A"][0]["source_start"] == 245.
    apply_manual_edit(p, {"action": "undo"})
    assert composition_layout_coverage(p)["fallback_available"]
    apply_manual_edit(p, {"action": "redo"})
    require_layout_coverage(p)


def test_synchronized_source_ranges_remain_valid_only_inside_actual_coverage():
    p = project(); p["manual"].pop("sequence"); p["manual"].pop("source_tracks")
    p["draft"]["keep_ranges"] = [{"start": 10., "end": 20.}]
    p["draft"]["camera_plan"] = [{"start": 10., "end": 20., "camera": "stacked"}]
    require_layout_coverage(p)
    p["manual"]["source_mixer"]["sync_offset"] = -155.
    assert composition_layout_coverage(p)["fallback_available"]


@pytest.mark.parametrize("instruction", ["One game explainer, camera above gameplay, three minutes.",
                                         "סרטון הסבר אחד על המשחק, מצלמה מעל המשחק, שלוש דקות."])
def test_actual_api_rejects_unsafe_layout_before_creating_job_and_preserves_request(api, monkeypatch, instruction):
    _, client, store, pid = api
    p = store.load(pid); example = project()
    p.update(copy.deepcopy(example)); p["id"] = pid
    p["manual"]["source_tracks"]["A"] = []
    p["sources"]["A"].update(relative_path="media/source-A.mp4", generation="a-v1", has_audio=True)
    p["sources"]["B"].update(relative_path="media/source-B.mp4", generation="b-v1", has_audio=True)
    p["settings"]["instruction"] = instruction
    store.save(p)
    before = store.state_path(pid).read_bytes()
    monkeypatch.setattr("server.ensure_render_storage", lambda *a, **k: pytest.fail("Coverage must fail before storage or render job"))
    response = client.post(f"/api/projects/{pid}/render", json={"fps": 60})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "layout_coverage_incomplete"
    assert response.get_json()["layout_coverage"]["missing_seconds"] == 180.
    assert store.state_path(pid).read_bytes() == before
    assert store.load(pid)["settings"]["instruction"] == instruction


def test_actual_api_accepts_safe_automatic_fallback_and_returns_warning_without_editing(api, monkeypatch):
    from cutroom.jobs import Job
    app, client, store, pid = api
    p = store.load(pid); p.update(copy.deepcopy(project())); p["id"] = pid
    store.save(p)
    before = store.state_path(pid).read_bytes()
    submitted = []
    monkeypatch.setattr("server.ensure_render_storage", lambda *a, **k: {"volumes": []})
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *args, **kwargs:
                        submitted.append((args, kwargs)) or Job("test-fallback", "render", pid))
    response = client.post(f"/api/projects/{pid}/render", json={"fps": 60})
    assert response.status_code == 202, response.get_json()
    assert response.get_json()["layout_fallback"]["missing_seconds"] == 180.
    assert response.get_json()["layout_fallback"]["mode"] == "available_A"
    assert len(submitted) == 1
    assert submitted[0][0][-1]["_require_layout_coverage"] is True
    assert store.state_path(pid).read_bytes() == before


def test_actual_api_revalidates_fallback_after_initial_preflight(api, monkeypatch):
    _, client, store, pid = api
    p = store.load(pid); p.update(copy.deepcopy(project())); p["id"] = pid; store.save(p)
    def changed(*args, **kwargs):
        store.update(pid, lambda current: current["manual"]["source_tracks"].update(A=[]))
        return {"volumes": []}
    monkeypatch.setattr("server.ensure_render_storage", changed)
    response = client.post(f"/api/projects/{pid}/render", json={"fps": 30})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "layout_coverage_incomplete"


def test_automatic_layout_fallback_is_reported_but_not_mislabelled_explicit():
    p = project(); p["manual"].pop("sequence"); p["manual"].pop("source_tracks")
    p["manual"]["source_mixer"].pop("default_layout"); p["settings"]["layout"] = "auto"
    report = composition_layout_coverage(p)
    assert report["missing_seconds"] == 180. and not report["explicit_layout"]
    assert not report["export_blocked"]


def test_single_source_role_requires_its_actual_mapped_source_without_blocking_an_intentional_A_tail():
    p = project()
    p["manual"]["sequence"]["camera_plan"] = [{"start": 0., "end": 4., "camera": "stacked"},
                                              {"start": 4., "end": 180., "camera": "A"}]
    apply_manual_edit(p, {"action": "sequence_insert", "slot": "B", "start": 0., "source_start": 0., "source_end": 4.})
    require_layout_coverage(p)
    assert composition_layout_coverage(p)["requested_seconds"] == 4.
    p["manual"].pop("sequence"); p["manual"].pop("source_tracks")
    p["manual"]["source_mixer"].update(screen_slot="B", camera_slot="A", default_layout="screen")
    p["settings"]["layout"] = "screen"
    p["draft"]["camera_plan"][0]["camera"] = "screen"
    assert composition_layout_coverage(p)["fallback_available"]
    p["draft"]["camera_plan"][0]["camera"] = "camera"
    require_layout_coverage(p)
