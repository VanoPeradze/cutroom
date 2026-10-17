"""Clip ancestry survives edits without linking duplicated caption instances."""
from __future__ import annotations

import copy

import pytest

from cutroom.sequence import materialize_sequence, prepare_sequence_edit
from cutroom.source_tracks import SourceTrackError, _validate_clip, prepare_source_track_edit, source_track_clips


def project(*, sequence: bool = True) -> dict:
    value = {
        "sources": {"A": {"duration": 20, "has_audio": True}, "B": None},
        "settings": {"fps": 30},
        "manual": {"source_tracks": {"A": [
            {"id": "a", "start": 0, "end": 4, "source_start": 2, "caption_origin": "original-a"},
            {"id": "b", "start": 4, "end": 8, "source_start": 10, "caption_origin": "original-b"},
        ], "B": []}},
        "draft": {
            "keep_ranges": [{"start": 0, "end": 8}],
            "camera_plan": [{"start": 0, "end": 8, "camera": "A"}],
        },
    }
    if sequence:
        value["manual"]["sequence"] = {
            "version": 1, "duration": 8,
            "camera_plan": [{"start": 0, "end": 8, "camera": "A"}],
        }
    return value


def test_existing_clips_do_not_gain_provenance_on_read():
    value = project()
    for clip in value["manual"]["source_tracks"]["A"]:
        clip.pop("caption_origin")
    before = copy.deepcopy(value)
    assert source_track_clips(value, "A") == before["manual"]["source_tracks"]["A"]
    assert value == before
    assert "caption_origin" not in _validate_clip(value, "A", before["manual"]["source_tracks"]["A"][0])


@pytest.mark.parametrize("origin", [None, False, 42, "", "   ", "x" * 129])
def test_invalid_caption_origin_is_rejected(origin):
    value = project()
    clip = {**value["manual"]["source_tracks"]["A"][0], "caption_origin": origin}
    with pytest.raises(SourceTrackError, match="caption origin"):
        _validate_clip(value, "A", clip)


def test_caption_origin_accepts_the_clip_id_length_limit():
    value = project()
    clip = {**value["manual"]["source_tracks"]["A"][0], "caption_origin": "x" * 128}
    assert _validate_clip(value, "A", clip)["caption_origin"] == "x" * 128


def test_legacy_sequence_materialization_preserves_origin_despite_new_ids():
    value = project(sequence=False)
    before = copy.deepcopy(value)
    materialized, _ = materialize_sequence(value)
    clips = materialized["manual"]["source_tracks"]["A"]
    assert [clip["id"] for clip in clips] == ["A:sequence:0:0", "A:sequence:0:1"]
    assert [clip["caption_origin"] for clip in clips] == ["original-a", "original-b"]
    assert value == before


def test_source_track_split_preserves_origin_in_both_halves():
    value = project(sequence=False)
    tracks = prepare_source_track_edit(value, {"action": "track_split", "slot": "A", "time": 2})
    clips = tracks["A"]
    assert [clip["caption_origin"] for clip in clips] == ["original-a", "original-a", "original-b"]
    assert clips[0]["id"] == "a" and clips[1]["id"] != "a"


@pytest.mark.parametrize("action,payload", [
    ("sequence_split", {"slot": "A", "time": 2}),
    ("sequence_split_all", {"time": 2}),
    ("sequence_trim_edge", {"slot": "A", "start": 0, "end": 4, "edge": "start", "time": 2}),
    ("sequence_move_range", {"slot": "A", "start": 1, "end": 3, "to": 6, "mode": "overwrite"}),
])
def test_sequence_splits_trims_and_partial_moves_keep_origin(action, payload):
    value = project()
    before = copy.deepcopy(value)
    result = prepare_sequence_edit(value, {"action": action, **payload})
    descendants = [clip for clip in result["source_tracks"]["A"] if clip["source_start"] < 6]
    assert descendants and all(clip["caption_origin"] == "original-a" for clip in descendants)
    assert any(clip["id"] != "a" for clip in descendants)
    assert value == before


@pytest.mark.parametrize("action,payload", [
    ("sequence_duplicate", {"slot": "A", "clip_id": "a", "start": 8}),
    ("sequence_duplicate_range", {"start": 1, "end": 3, "to": 8}),
])
def test_duplicates_receive_independent_caption_origins(action, payload):
    value = project()
    before = copy.deepcopy(value)
    result = prepare_sequence_edit(value, {"action": action, **payload})
    original = next(clip for clip in result["source_tracks"]["A"] if clip["id"] == "a")
    copied = [clip for clip in result["source_tracks"]["A"] if clip["start"] >= 8]
    assert original["caption_origin"] == "original-a"
    assert copied and all(clip["caption_origin"] == clip["id"] for clip in copied)
    assert all(clip["caption_origin"] not in {"original-a", "original-b"} for clip in copied)
    assert value == before


@pytest.mark.parametrize("action", ["sequence_insert", "sequence_insert_linked"])
def test_inserted_source_uses_its_new_clip_identity_as_origin(action):
    value = project()
    result = prepare_sequence_edit(value, {
        "action": action, "slot": "A", "start": 8, "source_start": 16, "source_end": 18,
    })
    inserted = next(clip for clip in result["source_tracks"]["A"] if clip["start"] == 8)
    assert inserted.get("caption_origin", inserted["id"]) == inserted["id"]
    assert inserted["id"] not in {"a", "b", "original-a", "original-b"}
