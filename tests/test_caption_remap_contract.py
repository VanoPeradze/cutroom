"""Caption ownership stays private and follows editing intent across revisions."""
from __future__ import annotations

import copy

import pytest

from cutroom import render
from cutroom.editing import apply_manual_edit
from server import _public_project
from test_caption_items import legacy_project, sequence_project, word


def _edit_later_repeat(value):
    apply_manual_edit(value, {
        "action": "caption_update", "caption_id": "s1:w0~1", "text": "Saved local text", "scale": 120,
    })


def _change_speech(value, replacement):
    if replacement == "transcript":
        value["analysis"]["transcript"]["segments"][1].update(
            text="Different speech", words=[word(2.1, 2.4, "Different"), word(2.5, 2.9, "speech")],
        )
    else:
        value["sources"]["A"]["sha256"] = "replacement-source"


@pytest.mark.parametrize("replacement", ["transcript", "source"])
@pytest.mark.parametrize("payload", [
    {"action": "caption_update", "style": "boxed"},
    {"action": "caption_visibility", "hidden": True},
    {"action": "caption_update", "start": 4.0, "end": 5.0},
])
def test_editing_replaced_speech_does_not_revive_stale_item_fields(replacement, payload):
    value = sequence_project()
    _edit_later_repeat(value)
    _change_speech(value, replacement)
    natural = render.project_caption_items(value)[2]
    assert not natural["local_text"]
    apply_manual_edit(value, {"caption_id": natural["id"], **payload})
    item = render.project_caption_items(value)[2]
    assert item["text"] == natural["text"]
    assert not item["local_text"] and item["scale"] is None
    if payload["action"] == "caption_visibility":
        assert item["hidden"]


def test_resetting_an_implicit_track_is_a_full_project_noop_with_caption_edits():
    value = legacy_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s0:w0", "text": "Saved words"})
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "track_reset", "slot": "A"})
    assert value == before


def test_independent_sequence_split_on_b_preserves_locked_a_caption_edits():
    value = sequence_project()
    _edit_later_repeat(value)
    apply_manual_edit(value, {"action": "set_track_lock", "slot": "A", "locked": True})
    captions = copy.deepcopy(render.project_caption_items(value))
    apply_manual_edit(value, {"action": "sequence_split", "slot": "B", "time": 0.5})
    assert len(value["manual"]["source_tracks"]["B"]) == 2
    assert render.project_caption_items(value) == captions


def test_independent_track_split_on_b_does_not_materialize_locked_implicit_a():
    value = legacy_project()
    value["sources"]["B"] = {"duration": 10, "has_audio": True}
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s0:w0", "text": "Saved words"})
    apply_manual_edit(value, {"action": "set_track_lock", "slot": "A", "locked": True})
    captions = copy.deepcopy(render.project_caption_items(value))
    assert "source_tracks" not in value["manual"]
    apply_manual_edit(value, {"action": "track_split", "slot": "B", "time": 2})
    assert len(value["manual"]["source_tracks"]["B"]) == 2
    assert "A" not in value["manual"]["source_tracks"]
    assert render.project_caption_items(value) == captions


@pytest.mark.parametrize("source_location", ["analysis", "draft"])
def test_legacy_b_sync_clock_preserves_caption_edit_on_first_sequence_split(source_location):
    value = legacy_project()
    value["sources"]["B"] = {"duration": 10, "has_audio": True}
    value["analysis"].update(audio_source="B", audio_timeline_offset=1, sync={"offset": 1})
    if source_location == "draft":
        value["analysis"].pop("audio_source")
        value["draft"]["audio_source"] = "B"
    value["manual"]["source_mixer"] = {"audio_slot": "B", "sync_offset": 1}
    apply_manual_edit(value, {
        "action": "caption_update", "caption_id": "s0:w2", "text": "Saved B words", "style": "boxed",
    })
    captions = [{key: field for key, field in item.items() if not key.startswith("_")}
                for item in render.project_caption_items(value)]
    apply_manual_edit(value, {"action": "sequence_split", "slot": "B", "time": 2.5})
    assert [{key: field for key, field in item.items() if not key.startswith("_")}
            for item in render.project_caption_items(value)] == captions
    assert render.project_caption_items(value)[1]["text"] == "Saved B words"


def test_dormant_edit_does_not_attach_to_a_duplicate_and_returns_on_reexpansion():
    value = sequence_project()
    _edit_later_repeat(value)
    apply_manual_edit(value, {
        "action": "sequence_trim", "slot": "A", "clip_id": "c", "start": 5, "end": 6, "source_start": 3,
    })
    assert all(item["text"] != "Saved local text" for item in render.project_caption_items(value))
    # A new use of the identical source words is a separate caption owner.
    apply_manual_edit(value, {"action": "sequence_duplicate", "slot": "A", "clip_id": "a", "start": 6})
    assert all(item["text"] != "Saved local text" for item in render.project_caption_items(value))
    apply_manual_edit(value, {
        "action": "sequence_trim", "slot": "A", "clip_id": "c", "start": 4, "end": 6, "source_start": 2,
    })
    items = render.project_caption_items(value)
    saved = [item for item in items if item["text"] == "Saved local text"]
    assert len(saved) == 1 and saved[0]["natural_start"] == 4.1 and saved[0]["scale"] == 120
    assert items[-1]["text"] == "Later words"


def test_caption_anchor_changes_invalidate_an_export_that_would_render_differently():
    value = sequence_project()
    _edit_later_repeat(value)
    stale = copy.deepcopy(value)
    stale["manual"]["caption_override_anchors"]["s1:w0~1"]["speech"] = "unrelated-transcript"
    assert render.project_caption_items(value)[2]["text"] == "Saved local text"
    assert render.project_caption_items(stale)[2]["text"] == "Later words"
    assert render._render_input_fingerprint(value) != render._render_input_fingerprint(stale)


def _all_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value))
    return set()


def test_public_project_omits_provenance_without_mutating_saved_caption_ownership():
    value = sequence_project()
    value["id"] = "caption-contract"
    _edit_later_repeat(value)
    apply_manual_edit(value, {"action": "sequence_split", "slot": "A", "time": 0.5})
    value["manual"]["sequence"]["base_source_tracks"] = copy.deepcopy(value["manual"]["source_tracks"])
    value["manual"]["caption_dormant_overrides"] = [{"anchor": {"speech": "older-speech"}, "edit": {"text": "old"}}]
    before = copy.deepcopy(value)
    public = _public_project(value)
    private_keys = {"_caption_anchor", "caption_override_anchors", "caption_dormant_overrides", "caption_origin"}
    assert not private_keys.intersection(_all_keys(public))
    assert public["editor_captions"][2]["text"] == "Saved local text"
    assert value == before
