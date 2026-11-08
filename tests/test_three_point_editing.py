"""Non-ripple source placement through model, persistence and encoded output."""
from __future__ import annotations

import copy
import json
import subprocess
from array import array

import pytest

from cutroom import render
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.ffmpeg_compat import export_capabilities
from cutroom.sequence import materialize_sequence
from cutroom.source_tracks import source_track_clips, timeline_duration
from test_sequence_editing import project
from test_source_tracks_api import track_api, post
from test_source_tracks_render import media
from test_all_layer_gap_closure import project as layered_project
from test_caption_items import sequence_project as caption_project


def overwrite(value, **fields):
    return apply_manual_edit(value, {"action": "sequence_overwrite", "slot": "A", "start": 2,
                                     "source_start": 6, "source_end": 9, **fields})


def geometry(value, slot="A"):
    return [(row["start"], row["end"], row["source_start"]) for row in source_track_clips(value, slot)]


def test_independent_overwrite_splits_destination_without_ripple_or_changing_other_source():
    value = project()
    baseline, _ = materialize_sequence(value)
    original = copy.deepcopy(value)
    overwrite(value)
    assert geometry(value) == [(0, 2, 0), (2, 5, 6), (5, 10, 11)]
    assert value["manual"]["source_tracks"]["B"] == baseline["manual"]["source_tracks"]["B"]
    assert value["manual"]["sequence"]["camera_plan"] == baseline["manual"]["sequence"]["camera_plan"]
    assert timeline_duration(value) == 10
    assert value["sources"] == original["sources"] and value["analysis"] == original["analysis"]
    assert value["draft"]["keep_ranges"] == original["draft"]["keep_ranges"]
    ids = [row["id"] for row in source_track_clips(value, "A")]
    assert len(set(ids)) == len(ids)
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}


def test_together_overwrite_changes_only_destination_sources_and_framing():
    value = project()
    overwrite(value, slot="B", scope="edit")
    assert geometry(value, "A") == [(0, 2, 0), (5, 10, 11)]
    assert geometry(value, "B") == [(0, 2, 0), (2, 5, 6), (5, 10, 11)]
    assert value["manual"]["sequence"]["camera_plan"] == [
        {"start": 0, "end": 2, "camera": "stacked"},
        {"start": 2, "end": 5, "camera": "B"},
        {"start": 5, "end": 10, "camera": "A"},
    ]
    assert timeline_duration(value) == 10


def test_overwrite_undo_redo_is_a_single_atomic_history_entry():
    value = project()
    original = copy.deepcopy(value)
    overwrite(value, scope="edit")
    after = copy.deepcopy(value["manual"]["source_tracks"])
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"] and "source_tracks" not in value["manual"]
    assert value["draft"]["keep_ranges"] == original["draft"]["keep_ranges"]
    apply_manual_edit(value, {"action": "redo"})
    assert value["manual"]["source_tracks"] == after
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}


@pytest.mark.parametrize("fields", [
    {"source_start": -1}, {"source_end": 21}, {"source_end": 6}, {"source_end": 6.01},
    {"source_start": float("nan")}, {"source_end": float("inf")}, {"start": -1},
    {"start": 9}, {"start": 86400}, {"scope": "all"}, {"scope": []}, {"slot": "C"},
])
def test_invalid_overwrite_does_not_materialize_or_consume_history(fields):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        overwrite(value, **fields)
    assert value == before


@pytest.mark.parametrize("slot,scope,locked", [("A", "source", "A"), ("A", "edit", "B"), ("B", "edit", "A")])
def test_overwrite_respects_every_affected_lock_atomically(slot, scope, locked):
    value = project()
    value["manual"]["track_locks"] = {locked: True}
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="locked"):
        overwrite(value, slot=slot, scope=scope)
    assert value == before


def test_independent_overwrite_is_allowed_beside_locked_other_lane():
    value = project()
    value["manual"]["track_locks"] = {"B": True}
    overwrite(value, scope="source")
    assert geometry(value) == [(0, 2, 0), (2, 5, 6), (5, 10, 11)]
    assert value["manual"]["track_locks"] == {"B": True}


@pytest.mark.parametrize("fps", [24, 25, 30, 50, 60])
def test_overwrite_accepts_one_output_frame_at_existing_boundary(fps):
    value = project()
    value["settings"]["fps"] = fps
    overwrite(value, start=0, source_start=1, source_end=1 + 1 / fps)
    assert source_track_clips(value, "A")[0]["end"] == pytest.approx(1 / fps)
    assert timeline_duration(value) == 10


def test_overwrite_rejects_unrenderable_surviving_fragment_without_loss():
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        overwrite(value, start=.001)
    assert value == before


def test_source_annotations_follow_new_media_without_editing_original_transcript():
    value = project()
    value["analysis"]["audio_source"] = "A"
    value["analysis"]["transcript"] = {"segments": [
        {"start": 2.1, "end": 2.9, "text": "replaced", "words": [{"start": 2.1, "end": 2.9, "word": "replaced"}]},
        {"start": 6.1, "end": 6.9, "text": "replacement", "words": [{"start": 6.1, "end": 6.9, "word": "replacement"}]},
        {"start": 12.1, "end": 12.9, "text": "later", "words": [{"start": 12.1, "end": 12.9, "word": "later"}]},
    ]}
    before = copy.deepcopy(value["analysis"])
    overwrite(value)
    captions = render._caption_transcript(value)["segments"]
    assert [row["text"] for row in captions] == ["replacement", "later"]
    assert [row["start"] for row in captions] == pytest.approx([2.1, 6.1])
    assert value["analysis"] == before


@pytest.mark.parametrize("kind", ["video", "audio", "image"])
@pytest.mark.parametrize("scope", ["source", "edit"])
def test_overwrite_preserves_overlapping_independent_layers_and_mixer(kind, scope):
    value = layered_project(kind)
    value["manual"]["source_mixer"] = {"audio_slot": "A", "gain_a_db": -3}
    value["manual"]["text_clips"][0].update(start=5, end=7)
    before = copy.deepcopy(value)
    overwrite(value, start=4, source_start=0, source_end=4, scope=scope)
    for key in ("media_clips", "text_clips", "source_mixer"):
        assert value["manual"][key] == before["manual"][key]
    for key in ("sources", "assets", "analysis"):
        assert value[key] == before[key]
    assert timeline_duration(value) == 12
    apply_manual_edit(value, {"action": "undo"})
    for key in ("source_tracks", "sequence", "media_clips", "text_clips", "source_mixer"):
        assert value["manual"][key] == before["manual"][key]


def test_overwrite_does_not_transfer_local_caption_correction_to_replacement_or_other_copy():
    value = caption_project()
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0", "text": "Only original first use"})
    apply_manual_edit(value, {"action": "caption_update", "caption_id": "s1:w0~1", "text": "Only later copy"})
    before = copy.deepcopy(render.project_caption_items(value))
    overwrite(value, start=0, source_start=0, source_end=1, scope="edit")
    assert [row["text"] for row in render.project_caption_items(value)] == ["First words", "First words", "Only later copy"]
    apply_manual_edit(value, {"action": "undo"})
    assert render.project_caption_items(value) == before
    apply_manual_edit(value, {"action": "redo"})
    assert [row["text"] for row in render.project_caption_items(value)] == ["First words", "First words", "Only later copy"]


def test_overwrite_api_persists_reopens_and_rejects_replayed_revision(track_api):
    client, store, project_id = track_api
    before = store.load(project_id)
    request = {"action": "sequence_overwrite", "slot": "B", "scope": "edit", "start": 2, "source_start": 6, "source_end": 9}
    response = post(track_api, request, revision=before["revision"])
    assert response.status_code == 200, response.get_json()
    public = response.get_json()["project"]
    assert public["editor_sequence"]["duration"] == 20
    assert public["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert "_history" not in public["manual"]
    saved = store.load(project_id)
    assert geometry(saved, "B") == [(0, 2, 0), (2, 5, 6), (5, 12, 5)]
    reopened = client.get(f"/api/projects/{project_id}").get_json()["project"]
    assert reopened["editor_sequence"] == public["editor_sequence"]
    conflict = post(track_api, request, revision=before["revision"])
    assert conflict.status_code == 409
    assert store.load(project_id) == saved
    assert post(track_api, {"action": "undo"}).status_code == 200
    assert "sequence" not in store.load(project_id)["manual"]
    assert post(track_api, {"action": "redo"}).status_code == 200
    assert geometry(store.load(project_id), "B") == geometry(saved, "B")


@pytest.mark.parametrize("fps", [30, 60])
def test_encoded_overwrite_has_exact_duration_picture_and_audio_boundaries(tmp_path, media, fps):
    ffmpeg, ffprobe, paths = media
    value = {
        "sources": {slot: {"duration": 4, "width": 160, "height": 100, "has_audio": True} for slot in ("A", "B")},
        "settings": {"fps": fps, "editorial_effects": False},
        "manual": {"source_mixer": {"audio_slot": "A"}},
        "draft": {"keep_ranges": [{"start": 0, "end": 4}], "camera_plan": [{"start": 0, "end": 4, "camera": "A"}]},
    }
    # Replace red/440 Hz from 1-2 with green/660 Hz from source 2-3.
    overwrite(value, start=1, source_start=2, source_end=3, scope="edit")
    assert render._expected_output_duration(value) == 4
    graph, maps, has_audio = render.build_filter_graph(value, 160, 100)
    assert has_audio
    script = tmp_path / "overwrite-graph.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "overwrite.mp4"
    encoded = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
        *export_capabilities(ffmpeg).graph_file_args(script), *maps,
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-r", str(fps), str(output)], capture_output=True, timeout=25)
    assert encoded.returncode == 0, encoded.stderr.decode(errors="replace")
    metadata = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))
    video = next(row for row in metadata["streams"] if row["codec_type"] == "video")
    assert int(video["nb_frames"]) == 4 * fps
    assert float(video["duration"]) == pytest.approx(4, abs=1 / fps)
    frames = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    for frame, channel in [(fps - 1, 0), (fps, 1), (2 * fps - 1, 1), (3 * fps, 1)]:
        offset = frame * 160 * 100 * 3 + (50 * 160 + 80) * 3
        rgb = frames[offset:offset + 3]
        assert rgb[channel] > 200 and all(c < 35 for i, c in enumerate(rgb) if i != channel), (frame, rgb)
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
    for time, expected in [(.4, 440), (1.4, 660), (2.4, 660), (3.4, 660)]:
        window = samples[int(time * 48000):int((time + .1) * 48000)]
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / .1
        assert frequency == pytest.approx(expected, abs=15)
