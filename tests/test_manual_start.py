import copy

import pytest

from cutroom.config import load_settings
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.manual_start import start_manual_draft
from cutroom.projects import ProjectStore
from cutroom.sequence import editor_sequence_snapshot
from server import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.ai["enabled"] = False
    return settings


def project(settings):
    value = ProjectStore(settings).create("Manual", initial_settings={"workflow": "manual", "goal": "youtube", "aspect": "16:9"})
    value["sources"]["A"] = {"duration": 12, "width": 640, "height": 360, "has_audio": True, "relative_path": "media/a.mp4"}
    return value


def test_manual_start_keeps_full_recording_and_supports_individual_edits(settings):
    value = project(settings)
    original_sources = copy.deepcopy(value["sources"])
    start_manual_draft(value)
    assert value["draft"]["engine"] == "manual"
    assert value["draft"]["keep_ranges"] == [{"start": 0, "end": 12}]
    assert value["settings"]["aspect"] == "16:9"
    assert value["sources"] == original_sources
    apply_manual_edit(value, {"action": "split", "time": 4})
    assert 4 in value["draft"]["edit_points"]
    apply_manual_edit(value, {"action": "delete_range", "start": 4, "end": 6})
    assert value["draft"]["output_duration"] == 10
    assert not editor_sequence_snapshot(value).get("error")
    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["output_duration"] == 12


def test_manual_start_does_not_replace_existing_edits(settings):
    value = project(settings)
    start_manual_draft(value)
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="already has"):
        start_manual_draft(value)
    assert value == before


def test_manual_start_preserves_confirmed_embedded_camera_without_fake_undo(settings):
    value = project(settings)
    apply_manual_edit(value, {"action": "set_embedded_camera", "enabled": True,
                              "x": .7, "y": .05, "w": .25, "h": .3})
    start_manual_draft(value)
    assert value["draft"]["camera_plan"][0]["camera"] == "embedded_stack"
    assert value["draft"]["embedded_layout_confirmed"]
    assert value["manual"]["history"]["undo_count"] == 0
    apply_manual_edit(value, {"action": "split", "time": 4})
    assert value["manual"]["history"]["undo_count"] == 1


def test_manual_start_preserves_two_source_roles_without_fake_undo(settings):
    value = project(settings)
    value["sources"]["B"] = copy.deepcopy(value["sources"]["A"])
    apply_manual_edit(value, {"action": "set_source_mixer", "screen_slot": "B", "camera_slot": "A",
                              "audio_slot": "A", "default_layout": "stacked", "sync_offset": .5})
    start_manual_draft(value)
    assert value["manual"]["source_mixer"]["screen_slot"] == "B"
    assert value["manual"]["source_mixer"]["sync_offset"] == .5
    assert value["draft"]["camera_plan"][0]["camera"] == "stacked"
    assert value["manual"]["history"]["undo_count"] == 0


def test_manual_start_api_validates_revision_and_works_with_ai_disabled(settings):
    app = create_app(settings)
    client = app.test_client()
    try:
        created = client.post("/api/projects", json={"name": "Manual", "initial_settings": {"workflow": "manual", "goal": "youtube", "aspect": "16:9"}})
        value = created.get_json()["project"]
        assert value["settings"]["workflow"] == "manual"
        store = app.extensions["cutroom_store"]
        value = store.update(value["id"], lambda item: item["sources"].update(A={"duration": 12, "width": 640, "height": 360}))
        url = f'/api/projects/{value["id"]}/manual-draft'
        assert client.post(url, json={}).status_code == 400
        assert client.post(url, json={"expected_revision": value["revision"] - 1}).status_code == 409
        result = client.post(url, json={"expected_revision": value["revision"]})
        assert result.status_code == 200
        assert result.get_json()["project"]["draft"]["output_duration"] == 12
        assert not app.extensions["cutroom_jobs"].active()
        result2 = client.post(url, json={"expected_revision": result.get_json()["project"]["revision"]})
        assert result2.status_code == 400
        invalid = client.post("/api/projects", json={"initial_settings": {"workflow": []}})
        assert invalid.status_code == 400
    finally:
        app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)
