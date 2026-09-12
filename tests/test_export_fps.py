from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import render
from cutroom.director import _effective_brief
from cutroom.config import load_settings
from cutroom.frame_rates import project_export_fps, validate_export_fps, with_export_options
from server import create_app


def _project(fps=30):
    return {
        "sources": {
            "A": {"duration": 4, "width": 320, "height": 180, "has_audio": True},
            "B": {"duration": 2, "width": 320, "height": 180, "has_audio": False},
        },
        "settings": {"fps": fps, "aspect": "source", "editorial_effects": False},
        "manual": {"source_mixer": {"sync_offset": 0.017, "audio_slot": "A"}},
        "draft": {
            "keep_ranges": [{"start": 0.017, "end": 1.019}, {"start": 2.05, "end": 3.067}],
            "camera_plan": [{"start": 0, "end": 4, "camera": "stacked"}],
        },
    }


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_supported_export_rates_drive_every_video_branch_and_frame_grid(fps):
    project = _project(fps)
    graph, _, has_audio = render.build_filter_graph(project, 320, 180)
    plan = render._frame_aligned_plan(project)
    assert has_audio
    assert f"fps={fps}," in graph
    assert f"setpts=N/{fps}/TB" in graph
    assert f":r={fps}:d=" in graph
    assert all(item["start"] * fps == pytest.approx(item["_start_frame"]) for item in plan)
    assert all(item["end"] * fps == pytest.approx(item["_end_frame"]) for item in plan)
    assert render._expected_output_duration(project) == pytest.approx(
        sum(item["_end_frame"] - item["_start_frame"] for item in plan) / fps
    )
    if fps != 30:
        assert "fps=30," not in graph
        assert ":r=30:d=" not in graph


@pytest.mark.parametrize("bad", [None, True, False, "60", 60.0, 59.94, 0, -60, 120, {}, []])
def test_invalid_export_rates_are_rejected_before_graph_or_encoder(bad):
    with pytest.raises(ValueError, match="fps must be an integer"):
        validate_export_fps(bad)
    with pytest.raises(ValueError, match="fps must be an integer"):
        render.build_filter_graph(_project(bad), 320, 180)


def test_legacy_fps_defaults_to_30_and_export_override_is_non_mutating():
    project = _project()
    project["settings"].pop("fps")
    before = copy.deepcopy(project)
    assert project_export_fps(project) == 30
    effective = with_export_options(project, {"fps": 60})
    assert project_export_fps(effective) == 60
    assert project == before
    assert render._render_input_fingerprint(project) != render._render_input_fingerprint(effective)


def test_frame_rate_does_not_change_story_brief_or_its_cache_inputs():
    project = _project(30)
    before = _effective_brief(project)
    project["settings"]["fps"] = 60
    assert _effective_brief(project) == before
    assert "fps" not in before


def test_storage_estimate_accounts_for_60_fps_encoding_cost():
    project = _project()
    settings = SimpleNamespace(render={"audio_bitrate": "192k", "min_free_mb": 0})
    standard = render._estimate_render_storage(project, 1920, 1080, "quality", settings)
    project["settings"]["fps"] = 60
    high = render._estimate_render_storage(project, 1920, 1080, "quality", settings)
    assert high["frame_rate"] == 60
    assert high["video_bytes"] > 1.9 * standard["video_bytes"]


@pytest.mark.parametrize("observed", [None, 0, 30, 59.94])
def test_render_verification_rejects_missing_or_wrong_frame_rate(observed):
    metadata = {"width": 320, "height": 180, "duration": 2, "fps": observed}
    with pytest.raises(RuntimeError, match="frame rate verification failed"):
        render._verify_output_metadata(
            metadata, width=320, height=180, expected_duration=2, expected_audio=False, expected_fps=60,
        )


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    return app


def test_project_fps_is_persisted_and_available_to_render_admission(app):
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Frame rate"}).get_json()["project"]
    assert project["settings"]["fps"] == 30
    path = f"/api/projects/{project['id']}"
    patched = client.patch(path, json={"settings": {"fps": 60}})
    assert patched.status_code == 200
    assert client.get(path).get_json()["project"]["settings"]["fps"] == 60
    # A valid render override reaches the normal draft guard, rather than being
    # silently ignored or rejected as an unknown field.
    response = client.post(path + "/render", json={"fps": 50})
    assert response.status_code == 400
    assert response.get_json()["error"] == "draft_required"


def test_saved_frame_rate_change_keeps_existing_draft_and_analysis(app):
    store = app.extensions["cutroom_store"]
    project = store.create("Existing edit")
    project["draft"] = {"keep_ranges": [{"start": 0, "end": 2}]}
    project["analysis"] = {"transcript": {"segments": [{"start": 0, "end": 1, "text": "Kept"}]}}
    store.save(project)
    response = app.test_client().patch(
        f"/api/projects/{project['id']}", json={"settings": {"fps": 60}},
    )
    assert response.status_code == 200
    saved = store.load(project["id"])
    assert saved["draft"] == project["draft"]
    assert saved["analysis"] == project["analysis"]


@pytest.mark.parametrize("bad", [None, True, "60", 60.5, 120])
def test_api_rejects_invalid_saved_and_one_off_frame_rates(app, bad):
    client = app.test_client()
    project = client.post("/api/projects", json={}).get_json()["project"]
    path = f"/api/projects/{project['id']}"
    for response in (
        client.patch(path, json={"settings": {"fps": bad}}),
        client.post(path + "/render", json={"fps": bad}),
    ):
        assert response.status_code == 400
        assert response.get_json()["error"] == "invalid_field"
    assert client.get(path).get_json()["project"]["settings"]["fps"] == 30


def test_real_60_fps_export_is_cfr_with_exact_edit_duration():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg runtime is not installed")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("smoke_60fps.py"))],
        capture_output=True, text=True, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"]
    assert len(payload["cases"]) == 2
    assert all(case["fps"] == 60 and case["frames"] > 0 for case in payload["cases"])
