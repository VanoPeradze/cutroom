from __future__ import annotations

import copy

import pytest

from cutroom.composition import CHROMA_KEY_DEFAULTS
from cutroom.editing import ManualEditError, apply_manual_edit


def project(draft=True):
    return {"sources": {slot: {"duration": 2, "width": 320, "height": 180, "has_audio": True}
                        for slot in ("A", "B")}, "settings": {}, "manual": {},
            "draft": {"keep_ranges": [{"start": 0, "end": 2}], "output_duration": 2} if draft else None}


def change(slot="A", **settings):
    return {"action": "set_chroma_key", "slot": slot, **CHROMA_KEY_DEFAULTS, "enabled": True, **settings}


@pytest.mark.parametrize("draft", [True, False])
def test_chroma_apply_undo_redo_and_reset_preserve_sources_and_draft_clock(draft):
    value = project(draft)
    original_sources = copy.deepcopy(value["sources"])
    original_draft = copy.deepcopy(value["draft"])
    apply_manual_edit(value, change(background_color="#0000ff"))
    assert value["manual"]["chroma_key"]["A"]["background_color"] == "#0000FF"
    assert value["manual"]["history"]["undo_count"] == 1
    apply_manual_edit(value, {"action": "undo"})
    assert "chroma_key" not in value["manual"]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["chroma_key"]["A"]["enabled"] is True
    apply_manual_edit(value, {"action": "reset_chroma_key", "slot": "A"})
    assert value["manual"]["chroma_key"]["A"] == CHROMA_KEY_DEFAULTS
    assert value["sources"] == original_sources
    if draft:
        assert value["draft"]["output_duration"] == original_draft["output_duration"]
        assert value["draft"]["keep_ranges"] == original_draft["keep_ranges"]
    else:
        assert value["draft"] is None


@pytest.mark.parametrize("payload", [change(color="#00FF00;movie=unsafe"), change(tolerance=True),
                                    change(slot="C"), change(filter="arbitrary")])
def test_invalid_chroma_rejected_before_any_state_or_history_mutation(payload):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        apply_manual_edit(value, payload)
    assert value == before


def test_repeated_apply_and_default_reset_do_not_consume_history():
    value = project()
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "reset_chroma_key", "slot": "A"})
    assert value == before
    apply_manual_edit(value, change())
    before = copy.deepcopy(value)
    apply_manual_edit(value, change())
    assert value == before


def test_legacy_solid_payload_without_optional_image_field_still_applies_and_is_a_real_noop():
    value = project()
    legacy = change()
    legacy.pop("background_asset_id")
    apply_manual_edit(value, legacy)
    assert value["manual"]["chroma_key"]["A"]["background_asset_id"] is None
    before = copy.deepcopy(value)
    apply_manual_edit(value, legacy)
    assert value == before
    # Reading an older saved five-setting record must not create a fake Undo
    # entry merely to add the optional null field.
    saved = project()
    saved["manual"]["chroma_key"] = {"A": {key: item for key, item in legacy.items() if key not in {"action", "slot"}}}
    before = copy.deepcopy(saved)
    apply_manual_edit(saved, legacy)
    assert saved == before


def test_lane_lock_blocks_only_its_chroma_and_locked_undo_is_atomic():
    value = project()
    value["manual"]["track_locks"] = {"A": True}
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="locked"):
        apply_manual_edit(value, change())
    assert value == before
    apply_manual_edit(value, change(slot="B"))
    value["manual"]["track_locks"]["B"] = True
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="locked"):
        apply_manual_edit(value, {"action": "undo"})
    assert value == before
