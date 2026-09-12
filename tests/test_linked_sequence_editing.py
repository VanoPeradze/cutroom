"""Whole-edit actions preserve A/B sync, layout, media time and atomic history."""
from __future__ import annotations

import copy
import json
import subprocess
from array import array

import pytest

from cutroom import render
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.sequence import editor_sequence_snapshot, materialize_sequence
from cutroom.source_tracks import source_track_clips, timeline_duration, track_at
from test_sequence_editing import edit, geometry, project
from test_source_tracks_api import post, track_api
from test_source_tracks_render import media


def plan(value):
    return value["manual"]["sequence"]["camera_plan"]


def local_time(value, slot, time):
    clip = track_at(value, slot, time)
    return None if clip is None else clip["source_start"] + time - clip["start"]


def test_ripple_delete_closes_both_tracks_and_layout_and_remaps_speech():
    value = project()
    original = copy.deepcopy(value)
    edit(value, "ripple_delete", start=2, end=5)
    assert timeline_duration(value) == 7
    assert geometry(value) == geometry(value, "B") == [(0, 2, 0), (2, 7, 11)]
    assert plan(value) == [{"start": 0, "end": 2, "camera": "stacked"}, {"start": 2, "end": 7, "camera": "A"}]
    assert render._caption_transcript(value)["segments"] == [{"start": 2, "end": 3, "text": "original speech"}]
    assert render._expected_output_duration(value) == 7
    assert value["sources"] == original["sources"] and value["analysis"] == original["analysis"]
    assert value["draft"]["keep_ranges"] == original["draft"]["keep_ranges"]
    assert value["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    state = copy.deepcopy(value["manual"]["source_tracks"])
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"]
    apply_manual_edit(value, {"action": "redo"})
    assert timeline_duration(value) == 7 and value["manual"]["source_tracks"] == state


def test_all_time_can_be_deleted_reopened_undone_and_repopulated():
    value = project()
    edit(value, "ripple_delete", start=0, end=10)
    snapshot = editor_sequence_snapshot(value)
    assert snapshot["active"] and snapshot["duration"] == 0
    assert snapshot["source_tracks"] == {"A": [], "B": []}
    assert snapshot["sequence"]["camera_plan"] == []
    with pytest.raises(ValueError, match="Add footage"):
        render.build_filter_graph(value, 160, 100)
    before = copy.deepcopy(value)
    edit(value, "split_all", time=0)
    assert value == before
    edit(value, "insert_linked", slot="B", start=0, source_start=13, source_end=16)
    assert timeline_duration(value) == 3
    assert geometry(value) == [] and geometry(value, "B") == [(0, 3, 13)]
    apply_manual_edit(value, {"action": "undo"})
    assert editor_sequence_snapshot(value)["duration"] == 0
    apply_manual_edit(value, {"action": "undo"})
    assert editor_sequence_snapshot(value)["duration"] == 10


def test_empty_render_rejected_before_media_io_or_encoder_probe():
    from types import SimpleNamespace
    value = project()
    edit(value, "ripple_delete", start=0, end=10)
    store = SimpleNamespace(load=lambda _: value)
    with pytest.raises(ValueError, match="Add footage"):
        render.render_project(None, value["id"], store, None)


def test_split_all_splits_only_present_clips_and_boundary_noop_preserves_history():
    value = project()
    edit(value, "remove_range", slot="B", start=0, end=4)
    edit(value, "split_all", time=2)
    assert geometry(value) == [(0, 2, 0), (2, 4, 2), (4, 10, 10)]
    assert geometry(value, "B") == [(4, 10, 10)]
    before = copy.deepcopy(value)
    edit(value, "split_all", time=2)
    edit(value, "split_all", time=4)
    assert value == before
    edit(value, "split_all", time=7)
    assert geometry(value)[-2:] == geometry(value, "B")[-2:] == [(4, 7, 10), (7, 10, 13)]


@pytest.mark.parametrize("start,end,to,expected", [
    (4, 10, 0, [(0, 6, 10), (6, 10, 0)]),
    (0, 4, 6, [(0, 6, 10), (6, 10, 0)]),
    (2, 6, 1, [(0, 1, 0), (1, 3, 2), (3, 5, 10), (5, 6, 1), (6, 10, 12)]),
    (4, 10, 12, [(0, 4, 0), (12, 18, 10)]),
])
def test_move_range_uses_final_destination_and_moves_both_lanes(start, end, to, expected):
    value = project()
    edit(value, "move_range", start=start, end=end, to=to)
    assert geometry(value) == geometry(value, "B") == expected
    assert timeline_duration(value) == max(10 - (end - start), to) + end - start
    assert all(len({clip["id"] for clip in source_track_clips(value, slot)}) == len(source_track_clips(value, slot)) for slot in ("A", "B"))


def test_move_range_keeps_gaps_and_layout_decisions_inside_the_moving_block():
    value = project()
    edit(value, "remove_range", slot="B", start=2, end=3)
    before, _ = materialize_sequence(value)
    edit(value, "move_range", start=1, end=5, to=6)
    for slot in ("A", "B"):
        for old, new in [(0.5, 0.5), (5.5, 1.5), (9.5, 5.5), (1.5, 6.5), (2.5, 7.5), (4.5, 9.5)]:
            assert local_time(value, slot, new) == local_time(before, slot, old)
    assert plan(value) == [
        {"start": 0, "end": 1, "camera": "stacked"}, {"start": 1, "end": 6, "camera": "A"},
        {"start": 6, "end": 9, "camera": "stacked"}, {"start": 9, "end": 10, "camera": "A"},
    ]


def test_duplicate_range_inserts_time_and_repeats_captions_without_touching_media():
    value = project()
    edit(value, "duplicate_range", start=4, end=7, to=0)
    assert geometry(value) == geometry(value, "B") == [(0, 3, 10), (3, 7, 0), (7, 13, 10)]
    assert timeline_duration(value) == 13
    assert [(row["start"], row["end"]) for row in render._caption_transcript(value)["segments"]] == [(0, 2), (7, 9)]
    assert plan(value) == [
        {"start": 0, "end": 3, "camera": "A"}, {"start": 3, "end": 7, "camera": "stacked"}, {"start": 7, "end": 13, "camera": "A"},
    ]


def test_linked_insert_splits_and_shifts_existing_both_tracks_but_adds_only_requested_source():
    value = project()
    edit(value, "insert_linked", slot="B", start=2, source_start=16, source_end=19)
    assert geometry(value) == [(0, 2, 0), (5, 7, 2), (7, 13, 10)]
    assert geometry(value, "B") == [(0, 2, 0), (2, 5, 16), (5, 7, 2), (7, 13, 10)]
    assert timeline_duration(value) == 13
    assert plan(value) == [
        {"start": 0, "end": 2, "camera": "stacked"}, {"start": 2, "end": 5, "camera": "B"},
        {"start": 5, "end": 7, "camera": "stacked"}, {"start": 7, "end": 13, "camera": "A"},
    ]


@pytest.mark.parametrize("action,payload", [
    ("split_all", {"time": -1}), ("split_all", {"time": 11}), ("split_all", {"time": 0.001}),
    ("ripple_delete", {"start": 0.001, "end": 1}),
    ("ripple_delete", {"start": 0, "end": 11}),
    ("move_range", {"start": 4, "end": 10, "to": 86400}),
    ("move_range", {"start": 4, "end": 10, "to": float("inf")}),
    ("duplicate_range", {"start": 0, "end": 4, "to": 9.999}),
    ("insert_linked", {"slot": "B", "start": 1, "source_start": 19, "source_end": 21}),
    ("insert_linked", {"slot": "C", "start": 0, "source_start": 0, "source_end": 1}),
])
def test_invalid_linked_operations_never_drop_fragments_or_change_history(action, payload):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        edit(value, action, **payload)
    assert value == before


@pytest.mark.parametrize("fps", [30, 60])
def test_linked_actions_accept_output_frame_boundaries(fps):
    value = project()
    value["settings"]["fps"] = fps
    edit(value, "split_all", time=1 / fps)
    edit(value, "ripple_delete", start=0, end=1 / fps)
    assert timeline_duration(value) == pytest.approx(10 - 1 / fps)
    assert geometry(value)[0][2] == pytest.approx(1 / fps)
    assert geometry(value) == geometry(value, "B")


def test_linked_noops_preserve_virtual_draft_and_redo():
    value = project()
    before = copy.deepcopy(value)
    edit(value, "move_range", start=2, end=6, to=2)
    edit(value, "split_all", time=4)
    assert value == before
    edit(value, "split_all", time=3)
    apply_manual_edit(value, {"action": "undo"})
    before = copy.deepcopy(value)
    edit(value, "move_range", start=2, end=6, to=2)
    assert value == before and value["manual"]["history"]["redo_count"] == 1


@pytest.mark.parametrize("payload", [
    {"action": "sequence_ripple_delete", "start": 2, "end": 4},
    {"action": "sequence_split_all", "time": 4},
    {"action": "sequence_move_range", "start": 2, "end": 4, "to": 7},
    {"action": "sequence_duplicate_range", "start": 2, "end": 4, "to": 7},
    {"action": "sequence_insert_linked", "slot": "B", "start": 2, "source_start": 3, "source_end": 5},
])
def test_linked_api_revision_protection_and_roundtrip(track_api, payload):
    client, store, project_id = track_api
    original = store.load(project_id)
    missing_revision = client.post(f"/api/projects/{project_id}/manual/edit", json=payload)
    assert missing_revision.status_code == 400
    assert store.load(project_id) == original
    response = post(track_api, payload)
    assert response.status_code == 200, response.get_json()
    saved = store.load(project_id)
    assert saved["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    stale = post(track_api, payload, revision=original["revision"])
    assert stale.status_code == 409
    assert store.load(project_id) == saved
    undo = post(track_api, {"action": "undo"})
    assert undo.status_code == 200 and undo.get_json()["project"]["editor_sequence"]["active"] is False
    redo = post(track_api, {"action": "redo"})
    assert redo.status_code == 200
    assert redo.get_json()["project"]["editor_sequence"]["source_tracks"] == saved["manual"]["source_tracks"]


def test_empty_sequence_is_persisted_and_publicly_reopenable(track_api):
    client, store, project_id = track_api
    response = post(track_api, {"action": "sequence_ripple_delete", "start": 0, "end": 20})
    assert response.status_code == 200, response.get_json()
    public = client.get(f"/api/projects/{project_id}").get_json()["project"]
    assert public["editor_sequence"]["duration"] == 0
    assert "error" not in public["editor_sequence"]
    assert store.load(project_id)["sources"]["A"]["duration"] == 20


@pytest.mark.parametrize("fps", [30, 60])
def test_real_ripple_export_keeps_both_media_clocks_audio_gaps_and_caption_timing(tmp_path, media, fps):
    from test_sequence_render import sequence_project

    ffmpeg, ffprobe, paths = media
    value = sequence_project()
    value["settings"]["fps"] = fps
    edit(value, "ripple_delete", start=1.25, end=4.25)
    assert timeline_duration(value) == 3
    graph, maps, _ = render.build_filter_graph(value, 160, 100)
    script = tmp_path / "linked-ripple-filter.txt"
    script.write_text(graph, encoding="utf-8")
    output = tmp_path / "linked-ripple.mp4"
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
                             "-filter_complex_script", str(script), *maps, "-c:v", "libx264", "-preset", "ultrafast",
                             "-c:a", "aac", "-r", str(fps), "-t", "3", str(output)], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    streams = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))["streams"]
    video = next(stream for stream in streams if stream["codec_type"] == "video")
    assert video["avg_frame_rate"] == f"{fps}/1" and int(video["nb_frames"]) == 3 * fps
    frames = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    def pixel(time, y):
        offset = int(time * fps) * 160 * 100 * 3 + (y * 160 + 80) * 3
        return tuple(frames[offset:offset + 3])
    assert pixel(0.5, 10)[2] > 200 and pixel(0.5, 70)[1] > 200
    assert pixel(1.1, 70)[2] > 200  # The B-only interval survives, without frozen A.
    assert pixel(1.5, 10)[0] > 200 and pixel(1.5, 10)[1] > 200
    assert pixel(1.5, 70)[1] > 200 and pixel(2.5, 70)[1] > 200
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"]))
    for time in (0.4, 1.5, 2.5):
        window = samples[int(time * 48000):int((time + 0.1) * 48000)]
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / 0.1
        assert frequency == pytest.approx(660, abs=15)
    assert max(abs(sample) for sample in samples[int(1.05 * 48000):int(1.15 * 48000)]) < 0.001
    captions = render._caption_transcript(value)["segments"]
    assert [row["start"] for row in captions] == pytest.approx([0.1, 1.25])
    assert [row["end"] for row in captions] == pytest.approx([0.9, 1.9])
