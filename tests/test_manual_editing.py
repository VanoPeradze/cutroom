from __future__ import annotations

import pytest

from cutroom.config import load_settings
from cutroom.editing import ManualEditError, apply_manual_edit, strip_private_edit_history
from server import create_app


def project() -> dict:
    return {
        "id": "project_012345abcdef",
        "sources": {"A": {"duration": 20.0}, "B": None},
        "analysis": {
            "transcript": {
                "text": "hello world",
                "segments": [
                    {"id": "s0", "start": 0.0, "end": 2.0, "text": "hello"},
                    {"id": "s1", "start": 2.0, "end": 4.0, "text": "world"},
                ],
            },
            "segments": [
                {"id": "s0", "start": 0.0, "end": 2.0, "text": "hello"},
                {"id": "s1", "start": 2.0, "end": 4.0, "text": "world"},
            ],
            "story_hierarchy": {"outline": {}},
        },
        "draft": {
            "cuts": [{"start": 8.0, "end": 10.0}],
            "keep_ranges": [{"start": 0.0, "end": 8.0}, {"start": 10.0, "end": 20.0}],
            "camera_plan": [
                {"start": 0.0, "end": 8.0, "camera": "A"},
                {"start": 10.0, "end": 20.0, "camera": "B"},
            ],
            "output_duration": 18.0,
            "removed_duration": 2.0,
        },
        "manual": {"cuts": []},
    }


def test_delete_restore_undo_and_redo_are_reflected_in_render_ranges():
    value = project()
    apply_manual_edit(value, {"action": "delete_range", "start": 2.0, "end": 4.0})
    assert value["draft"]["cuts"] == [
        {"start": 2.0, "end": 4.0},
        {"start": 8.0, "end": 10.0},
    ]
    assert value["draft"]["output_duration"] == 16.0
    assert value["manual"]["cuts"] == [{"start": 2.0, "end": 4.0}]

    apply_manual_edit(value, {"action": "restore_range", "start": 2.0, "end": 4.0})
    assert value["draft"]["cuts"] == [{"start": 8.0, "end": 10.0}]
    assert value["draft"]["output_duration"] == 18.0

    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["output_duration"] == 16.0
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 1}

    apply_manual_edit(value, {"action": "redo"})
    assert value["draft"]["output_duration"] == 18.0


def test_restoring_inside_a_cut_splits_the_remaining_cut():
    value = project()
    apply_manual_edit(value, {"action": "restore_range", "start": 8.5, "end": 9.5})
    assert value["draft"]["cuts"] == [
        {"start": 8.0, "end": 8.5},
        {"start": 9.5, "end": 10.0},
    ]
    assert any(item["camera"] == "A" and item["start"] == 8.5 for item in value["draft"]["camera_plan"])


def test_restored_footage_is_durable_and_later_delete_undo_redo_preserve_intent():
    from cutroom.editing import apply_timeline_overrides

    value = project()
    apply_manual_edit(value, {"action": "restore_range", "start": 8.0, "end": 10.0})
    assert value["manual"]["keeps"] == [{"start": 8.0, "end": 10.0}]
    ai_cuts = [{"start": 6.0, "end": 12.0}]
    assert apply_timeline_overrides(ai_cuts, value["manual"]) == [
        {"start": 6.0, "end": 8.0}, {"start": 10.0, "end": 12.0},
    ]

    apply_manual_edit(value, {"action": "delete_range", "start": 8.5, "end": 9.5})
    assert apply_timeline_overrides(ai_cuts, value["manual"]) == [
        {"start": 6.0, "end": 8.0}, {"start": 8.5, "end": 9.5}, {"start": 10.0, "end": 12.0},
    ]
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"]["keeps"] == [{"start": 8.0, "end": 10.0}]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["keeps"] == [
        {"start": 8.0, "end": 8.5}, {"start": 9.5, "end": 10.0},
    ]


def test_new_reel_candidate_respects_durable_restores_even_if_candidate_is_stale():
    value = project()
    apply_manual_edit(value, {"action": "restore_range", "start": 8.0, "end": 10.0})
    value["draft"]["reel_candidates"] = [{
        "id": "fresh", "cuts": [{"start": 6.0, "end": 12.0}],
        "ai_camera_plan": [{"start": 0.0, "end": 20.0, "camera": "A"}],
    }]
    apply_manual_edit(value, {"action": "apply_reel_candidate", "candidate_id": "fresh"})
    assert {"start": 8.0, "end": 10.0} in value["draft"]["keep_ranges"]


@pytest.mark.parametrize("corrected", ["CUTROOM studio", "CUTROOM editing studio"])
def test_transcript_correction_changes_exported_words_and_undo_restores_timing(tmp_path, corrected):
    import copy

    from cutroom.captions import _caption_entries, build_srt

    value = project()
    segment = value["analysis"]["transcript"]["segments"][0]
    segment["text"] = "hello world"
    original_words = [
        {"word": "hello", "start": 0.2, "end": 0.8},
        {"word": "world", "start": 1.0, "end": 1.8},
    ]
    segment["words"] = copy.deepcopy(original_words)
    value["analysis"]["segments"][0] = copy.deepcopy(segment)
    apply_manual_edit(value, {"action": "transcript_text", "segment_id": "s0", "text": corrected})
    transcript = value["analysis"]["transcript"]
    keep = [{"start": 0.0, "end": 2.0}]
    assert _caption_entries(transcript, keep)[0][2] == corrected
    srt = build_srt(transcript, keep, tmp_path / "corrected.srt").read_text(encoding="utf-8")
    assert corrected in srt
    assert "hello" not in srt

    apply_manual_edit(value, {"action": "undo"})
    assert segment["words"] == original_words
    assert _caption_entries(transcript, keep)[0] == (0.2, 1.8, "hello world")
    apply_manual_edit(value, {"action": "redo"})
    assert _caption_entries(transcript, keep)[0][2] == corrected


def test_transcript_correction_updates_captions_source_and_is_undoable():
    value = project()
    apply_manual_edit(value, {"action": "transcript_text", "segment_id": "s1", "text": "CUTROOM"})
    assert value["analysis"]["transcript"]["text"] == "hello CUTROOM"
    assert value["analysis"]["segments"][1]["text"] == "CUTROOM"
    assert "story_hierarchy" not in value["analysis"]

    apply_manual_edit(value, {"action": "undo"})
    assert value["analysis"]["transcript"]["segments"][1]["text"] == "world"


def test_split_adds_a_real_camera_edit_point_without_changing_duration():
    value = project()
    apply_manual_edit(value, {"action": "split", "time": 3.0})
    assert value["draft"]["edit_points"] == [3.0]
    assert value["draft"]["camera_plan"][:2] == [
        {"start": 0.0, "end": 3.0, "camera": "A"},
        {"start": 3.0, "end": 8.0, "camera": "A"},
    ]
    assert value["draft"]["output_duration"] == 18.0


def test_manual_layout_can_target_the_whole_edit_and_is_undoable():
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {"action": "set_camera_layout", "layout": "stacked", "start": 0, "end": 20})

    assert value["draft"]["camera_plan"] == [
        {"start": 0.0, "end": 8.0, "camera": "stacked"},
        {"start": 10.0, "end": 20.0, "camera": "stacked"},
    ]
    assert value["draft"]["ai_camera_plan"][0]["camera"] == "A"
    assert value["manual"]["camera_overrides"] == [{"start": 0.0, "end": 20.0, "layout": "stacked"}]

    apply_manual_edit(value, {"action": "undo"})
    assert [row["camera"] for row in value["draft"]["camera_plan"]] == ["A", "B"]
    assert value["manual"]["camera_overrides"] == []
    apply_manual_edit(value, {"action": "redo"})
    assert all(row["camera"] == "stacked" for row in value["draft"]["camera_plan"])


def test_ranked_reel_candidate_can_be_applied_and_undone():
    value = project()
    value["draft"]["active_reel_candidate"] = "director_pick"
    value["draft"]["reel_candidates"] = [
        {
            "id": "director_pick", "cuts": value["draft"]["cuts"],
            "ai_camera_plan": value["draft"]["camera_plan"],
        },
        {
            "id": "reel_2", "cuts": [{"start": 0.0, "end": 5.0}, {"start": 12.0, "end": 20.0}],
            "ai_camera_plan": [{"start": 5.0, "end": 12.0, "camera": "A"}],
        },
    ]

    apply_manual_edit(value, {"action": "apply_reel_candidate", "candidate_id": "reel_2"})

    assert value["draft"]["active_reel_candidate"] == "reel_2"
    assert value["draft"]["keep_ranges"] == [{"start": 5.0, "end": 12.0}]
    assert value["draft"]["output_duration"] == 7.0
    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["active_reel_candidate"] == "director_pick"
    assert value["draft"]["output_duration"] == 18.0


def test_manual_cut_and_restore_stay_consistent_across_reel_candidates_and_history():
    value = project()
    value["draft"]["active_reel_candidate"] = "director_pick"
    value["draft"]["reel_candidates"] = [
        {
            "id": "director_pick", "cuts": value["draft"]["cuts"],
            "keep_ranges": value["draft"]["keep_ranges"],
            "output_duration": value["draft"]["output_duration"],
            "ai_camera_plan": value["draft"]["camera_plan"],
        },
        {
            "id": "reel_2", "cuts": [{"start": 0.0, "end": 5.0}, {"start": 12.0, "end": 20.0}],
            "keep_ranges": [{"start": 5.0, "end": 12.0}], "output_duration": 7.0,
            "ai_camera_plan": [{"start": 5.0, "end": 12.0, "camera": "A"}],
        },
    ]

    apply_manual_edit(value, {"action": "delete_range", "start": 6.0, "end": 7.0})
    assert all(
        any(item["start"] <= 6.0 and item["end"] >= 7.0 for item in candidate["cuts"])
        for candidate in value["draft"]["reel_candidates"]
    )

    apply_manual_edit(value, {"action": "undo"})
    alternate = next(item for item in value["draft"]["reel_candidates"] if item["id"] == "reel_2")
    assert alternate["keep_ranges"] == [{"start": 5.0, "end": 12.0}]

    apply_manual_edit(value, {"action": "redo"})
    apply_manual_edit(value, {"action": "restore_range", "start": 6.0, "end": 7.0})
    apply_manual_edit(value, {"action": "apply_reel_candidate", "candidate_id": "reel_2"})
    assert value["draft"]["keep_ranges"] == [{"start": 5.0, "end": 12.0}]


def test_manual_layout_splits_only_the_selected_kept_source_time():
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {"action": "set_camera_layout", "layout": "pip", "start": 2, "end": 4})

    assert value["draft"]["camera_plan"] == [
        {"start": 0.0, "end": 2.0, "camera": "A"},
        {"start": 2.0, "end": 4.0, "camera": "pip"},
        {"start": 4.0, "end": 8.0, "camera": "A"},
        {"start": 10.0, "end": 20.0, "camera": "B"},
    ]
    assert sum(row["end"] - row["start"] for row in value["draft"]["camera_plan"]) == 18.0

    apply_manual_edit(value, {"action": "set_camera_layout", "layout": "auto", "start": 2, "end": 4})
    assert value["draft"]["camera_plan"] == value["draft"]["ai_camera_plan"]
    assert value["manual"]["camera_overrides"] == []


def test_layout_selection_never_resurrects_cut_footage():
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {"action": "set_camera_layout", "layout": "side_by_side", "start": 7, "end": 11})

    assert {tuple((row["start"], row["end"])) for row in value["draft"]["camera_plan"]} >= {(7.0, 8.0), (10.0, 11.0)}
    assert not any(row["start"] < 10 and row["end"] > 8 for row in value["draft"]["camera_plan"])
    assert sum(row["end"] - row["start"] for row in value["draft"]["camera_plan"]) == 18.0


def test_source_roles_priority_and_audio_are_manual_and_undoable():
    value = project()
    value["sources"]["A"]["has_audio"] = False
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {
        "action": "set_source_mixer",
        "screen_slot": "B",
        "camera_slot": "A",
        "primary_role": "camera",
        "audio_slot": "B",
        "first_slot": "B",
    })

    assert value["manual"]["source_mixer"] == {
        "screen_slot": "B", "camera_slot": "A", "primary_role": "camera", "audio_slot": "B", "first_slot": "B",
    }
    apply_manual_edit(value, {"action": "undo"})
    assert "source_mixer" not in value["manual"]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["source_mixer"]["audio_slot"] == "B"


def test_legacy_physical_ab_draft_becomes_semantic_when_roles_change():
    value = project()
    value["sources"]["A"]["has_audio"] = True
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}
    value["settings"] = {"layout": "A"}
    value["manual"]["source_mixer"] = {
        "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A",
    }
    value["manual"]["camera_overrides"] = [{"start": 2.0, "end": 4.0, "layout": "B"}]
    value["draft"]["ai_camera_plan"] = [
        {"start": 0.0, "end": 8.0, "camera": "A"},
        {"start": 10.0, "end": 20.0, "camera": "B"},
    ]
    value["draft"]["reel_candidates"] = [{
        "id": "legacy", "camera_plan": [{"start": 0.0, "end": 5.0, "camera": "B"}],
        "ai_camera_plan": [{"start": 0.0, "end": 5.0, "camera": "A"}],
    }]

    apply_manual_edit(value, {
        "action": "set_source_mixer", "screen_slot": "B", "camera_slot": "A",
        "primary_role": "screen", "audio_slot": "A", "first_slot": "B",
    })

    assert [item["camera"] for item in value["draft"]["camera_plan"]] == ["screen", "camera"]
    assert [item["camera"] for item in value["draft"]["ai_camera_plan"]] == ["screen", "camera"]
    assert value["manual"]["camera_overrides"][0]["layout"] == "camera"
    assert value["draft"]["reel_candidates"][0]["camera_plan"][0]["camera"] == "camera"
    assert value["draft"]["reel_candidates"][0]["ai_camera_plan"][0]["camera"] == "screen"
    assert value["settings"]["layout"] == "screen"

    apply_manual_edit(value, {"action": "undo"})
    assert [item["camera"] for item in value["draft"]["camera_plan"]] == ["A", "B"]
    apply_manual_edit(value, {"action": "redo"})
    assert [item["camera"] for item in value["draft"]["camera_plan"]] == ["screen", "camera"]


def test_source_roles_and_speech_audio_can_be_chosen_before_first_draft():
    value = project()
    value["draft"] = None
    value["analysis"] = None
    value["sources"]["A"]["has_audio"] = False
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {
        "action": "set_source_mixer",
        "screen_slot": "A",
        "camera_slot": "B",
        "primary_role": "screen",
        "audio_slot": "B",
        "first_slot": "B",
        "sync_offset": 0.75,
        "default_layout": "stacked",
    })

    assert value["manual"]["source_mixer"] == {
        "screen_slot": "A", "camera_slot": "B", "primary_role": "screen",
        "audio_slot": "B", "first_slot": "B", "sync_offset": 0.75, "default_layout": "stacked",
    }
    assert value["manual"]["history"] == {"undo_count": 0, "redo_count": 0}


def test_manual_sync_offset_is_preserved_until_explicitly_reset():
    value = project()
    value["sources"]["A"]["has_audio"] = True
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}
    base = {
        "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
        "primary_role": "screen", "audio_slot": "A",
    }

    apply_manual_edit(value, {**base, "sync_offset": 1.25})
    assert value["manual"]["source_mixer"]["sync_offset"] == 1.25
    apply_manual_edit(value, {**base, "primary_role": "camera"})
    assert value["manual"]["source_mixer"]["sync_offset"] == 1.25
    apply_manual_edit(value, {**base, "sync_offset": None})
    assert "sync_offset" not in value["manual"]["source_mixer"]


def test_explicit_default_layout_including_auto_survives_other_mixer_changes():
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}
    base = {
        "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
        "primary_role": "screen", "audio_slot": "B",
    }

    apply_manual_edit(value, {**base, "default_layout": "auto"})
    apply_manual_edit(value, {**base, "primary_role": "camera"})

    assert value["manual"]["source_mixer"]["default_layout"] == "auto"
    apply_manual_edit(value, {**base, "default_layout": None})
    assert "default_layout" not in value["manual"]["source_mixer"]


def test_first_slot_is_validated_and_survives_other_source_mixer_changes():
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}
    base = {
        "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
        "primary_role": "screen", "audio_slot": "B",
    }

    apply_manual_edit(value, {**base, "first_slot": "B"})
    apply_manual_edit(value, {**base, "primary_role": "camera"})
    assert value["manual"]["source_mixer"]["first_slot"] == "B"

    with pytest.raises(ManualEditError, match="First source"):
        apply_manual_edit(value, {**base, "first_slot": "C"})


def test_embedded_camera_can_be_marked_before_first_draft():
    value = project()
    value["draft"] = None
    value["settings"] = {"layout": "auto"}

    apply_manual_edit(value, {
        "action": "set_embedded_camera",
        "enabled": True,
        "x": .72,
        "y": .06,
        "w": .24,
        "h": .25,
        "content_x": .32,
        "content_y": .58,
    })

    assert value["manual"]["embedded_camera"] == {
        "x": .72, "y": .06, "w": .24, "h": .25,
        "content_focus": {"x": .32, "y": .58},
        "content_region": {"x": 0.0, "y": 0.0, "w": .72, "h": 1.0},
    }
    assert value["settings"]["layout"] == "embedded_stack"
    assert value["manual"]["history"] == {"undo_count": 0, "redo_count": 0}


def test_embedded_camera_updates_existing_draft_and_is_undoable():
    value = project()
    value["settings"] = {"layout": "auto"}
    value["manual"]["source_mixer"] = {"default_layout": "auto", "audio_slot": "A"}
    value["draft"]["layout"] = "auto"
    value["draft"]["embedded_layout_confirmed"] = False
    value["draft"]["reel_candidates"] = [{
        "id": "reel_2",
        "keep_ranges": [{"start": 2.0, "end": 6.0}],
        "ai_camera_plan": [{"start": 2.0, "end": 6.0, "camera": "A"}],
        "camera_plan": [{"start": 2.0, "end": 6.0, "camera": "A"}],
    }]

    apply_manual_edit(value, {
        "action": "set_embedded_camera", "enabled": True,
        "x": .70, "y": .05, "w": .25, "h": .24,
        "content_x": .30, "content_y": .55,
    })

    assert value["draft"]["layout"] == "embedded_stack"
    assert value["draft"]["embedded_layout_confirmed"] is True
    assert {item["camera"] for item in value["draft"]["camera_plan"]} == {"embedded_stack"}
    assert value["draft"]["reel_candidates"][0]["camera_plan"][0]["camera"] == "embedded_stack"
    assert value["settings"]["layout"] == "embedded_stack"
    assert value["manual"]["source_mixer"] == {"audio_slot": "A"}

    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["layout"] == "auto"
    assert value["draft"]["embedded_layout_confirmed"] is False
    assert "embedded_camera" not in value["manual"]
    assert value["settings"]["layout"] == "auto"
    assert value["manual"]["source_mixer"] == {"default_layout": "auto", "audio_slot": "A"}

    apply_manual_edit(value, {"action": "redo"})
    assert value["draft"]["embedded_layout_confirmed"] is True
    assert value["manual"]["embedded_camera"]["x"] == .70
    assert value["manual"]["source_mixer"] == {"audio_slot": "A"}

    apply_manual_edit(value, {"action": "set_embedded_camera", "enabled": False})
    assert value["settings"]["layout"] == "auto"
    assert value["draft"]["layout"] == "auto"
    assert value["draft"]["embedded_layout_confirmed"] is False
    assert {item["camera"] for item in value["draft"]["camera_plan"]} == {"A"}
    assert "embedded_camera" not in value["manual"]

    apply_manual_edit(value, {"action": "undo"})
    assert value["draft"]["embedded_layout_confirmed"] is True
    assert value["manual"]["embedded_camera"]["x"] == .70


def test_embedded_camera_rejects_untrusted_geometry_and_a_separate_source_b():
    value = project()
    with pytest.raises(ManualEditError, match="enabled"):
        apply_manual_edit(value, {
            "action": "set_embedded_camera", "enabled": 1,
            "x": .7, "y": .05, "w": .25, "h": .25,
        })
    with pytest.raises(ManualEditError, match="valid normalized"):
        apply_manual_edit(value, {
            "action": "set_embedded_camera", "enabled": True,
            "x": .9, "y": .05, "w": .25, "h": .25,
        })

    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}
    with pytest.raises(ManualEditError, match="source B"):
        apply_manual_edit(value, {
            "action": "set_embedded_camera", "enabled": True,
            "x": .7, "y": .05, "w": .25, "h": .25,
        })


@pytest.mark.parametrize("layout", ["auto", "screen", "camera", "stacked", "side_by_side", "pip"])
def test_all_supported_source_mixer_default_layouts_are_persisted(layout):
    value = project()
    value["sources"]["B"] = {"duration": 20.0, "has_audio": True}

    apply_manual_edit(value, {
        "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
        "primary_role": "screen", "audio_slot": "B", "default_layout": layout,
    })

    assert value["manual"]["source_mixer"]["default_layout"] == layout


def test_two_source_layout_and_role_validation_is_strict():
    value = project()
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "set_camera_layout", "layout": "pip", "start": 0, "end": 5})
    value["sources"]["B"] = {"duration": 20.0, "has_audio": False}
    value["sources"]["A"]["has_audio"] = True
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {
            "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "A",
            "primary_role": "screen", "audio_slot": "A",
        })
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {
            "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
            "primary_role": "screen", "audio_slot": "B",
        })
    for invalid_layout in ("A", "B", "embedded_stack", "invented"):
        with pytest.raises(ManualEditError, match="Unknown default source layout"):
            apply_manual_edit(value, {
                "action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
                "primary_role": "screen", "audio_slot": "A", "default_layout": invalid_layout,
            })


def test_invalid_or_destructive_ranges_are_rejected():
    value = project()
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "delete_range", "start": 0.0, "end": 0.01})
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, {"action": "delete_range", "start": 0.0, "end": 20.0})


def test_private_history_is_not_sent_to_the_browser():
    value = project()
    apply_manual_edit(value, {"action": "delete_range", "start": 2.0, "end": 4.0})
    assert "_history" in value["manual"]
    strip_private_edit_history(value)
    assert "_history" not in value["manual"]
    assert value["manual"]["history"]["undo_count"] == 1


def test_manual_edit_api_is_revision_checked_and_hides_history(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("manual-api")
    sample = project()
    sample["sources"]["A"]["relative_path"] = "media/source-A.mp4"
    value.update({key: sample[key] for key in ("sources", "analysis", "draft", "manual")})
    value = store.save(value)

    response = app.test_client().post(
        f"/api/projects/{value['id']}/manual/edit",
        json={
            "action": "delete_range",
            "start": 2.0,
            "end": 4.0,
            "expected_revision": value["revision"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["project"]
    assert payload["draft"]["output_duration"] == 16.0
    assert payload["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert "_history" not in payload["manual"]

    conflict = app.test_client().post(
        f"/api/projects/{value['id']}/manual/edit",
        json={"action": "undo", "expected_revision": value["revision"]},
    )
    assert conflict.status_code == 409
    assert conflict.get_json()["error"] == "revision_conflict"


def test_manual_source_routing_api_works_before_director_creates_a_draft(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("pre-director-routing")
    value["sources"] = {
        "A": {"name": "screen.mp4", "duration": 20.0, "has_audio": False, "relative_path": "media/source-A.mp4"},
        "B": {"name": "mic.mp4", "duration": 20.0, "has_audio": True, "relative_path": "media/source-B.mp4"},
    }
    value = store.save(value)

    response = app.test_client().post(
        f"/api/projects/{value['id']}/manual/edit",
        json={
            "action": "set_source_mixer",
            "screen_slot": "A",
            "camera_slot": "B",
            "primary_role": "screen",
            "audio_slot": "B",
            "first_slot": "B",
            "sync_offset": 0.4,
            "default_layout": "stacked",
            "expected_revision": value["revision"],
        },
    )

    assert response.status_code == 200
    project_payload = response.get_json()["project"]
    assert project_payload["draft"] is None
    assert project_payload["manual"]["source_mixer"]["audio_slot"] == "B"
    assert project_payload["manual"]["source_mixer"]["first_slot"] == "B"
    assert project_payload["manual"]["source_mixer"]["sync_offset"] == 0.4
    assert project_payload["manual"]["source_mixer"]["default_layout"] == "stacked"


def test_manual_embedded_camera_action_is_accepted_by_local_api(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("manual-embedded-camera")
    value["sources"]["A"] = {
        "name": "combined.mp4", "duration": 20.0, "has_audio": True,
        "relative_path": "media/source-A.mp4",
    }
    value = store.save(value)

    response = app.test_client().post(
        f"/api/projects/{value['id']}/manual/edit",
        json={
            "action": "set_embedded_camera",
            "enabled": True,
            "x": .72,
            "y": .06,
            "w": .24,
            "h": .25,
            "content_x": .31,
            "content_y": .57,
            "expected_revision": value["revision"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["project"]
    assert payload["draft"] is None
    assert payload["settings"]["layout"] == "embedded_stack"
    assert payload["manual"]["embedded_camera"]["content_focus"] == {"x": .31, "y": .57}


def test_reel_candidate_action_is_accepted_by_the_local_api(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    app = create_app(settings)
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    value = store.create("candidate-api")
    sample = project()
    sample["sources"]["A"]["relative_path"] = "media/source-A.mp4"
    sample["draft"]["reel_candidates"] = [{
        "id": "reel_2",
        "cuts": [{"start": 0.0, "end": 6.0}, {"start": 14.0, "end": 20.0}],
        "ai_camera_plan": [{"start": 6.0, "end": 14.0, "camera": "A"}],
    }]
    value.update({key: sample[key] for key in ("sources", "analysis", "draft", "manual")})
    value = store.save(value)

    response = app.test_client().post(
        f"/api/projects/{value['id']}/manual/edit",
        json={
            "action": "apply_reel_candidate",
            "candidate_id": "reel_2",
            "expected_revision": value["revision"],
        },
    )

    assert response.status_code == 200
    payload = response.get_json()["project"]
    assert payload["draft"]["active_reel_candidate"] == "reel_2"
    assert payload["draft"]["keep_ranges"] == [{"start": 6.0, "end": 14.0}]
