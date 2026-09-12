"""Per-cut framing survives editing and reaches the actual encoded pixels."""
import copy
import json
import shutil
import subprocess

import pytest

from cutroom import render
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.source_tracks import source_track_clips
from test_sequence_editing import edit, project
from test_source_tracks_api import post, track_api


def test_framing_is_local_to_range_and_source_and_survives_split_move_duplicate_reopen():
    value = project()
    original = copy.deepcopy(value)
    crop = {"x": .15, "y": .7, "zoom": 1.3}
    edit(value, "crop", slot="A", start=1, end=3, **crop)
    clips = source_track_clips(value, "A")
    assert [(c["start"], c["end"], c.get("crop")) for c in clips] == [
        (0, 1, None), (1, 3, crop), (3, 4, None), (4, 10, None)]
    assert all("crop" not in c for c in source_track_clips(value, "B"))
    assert "crop" not in value["manual"]
    assert value["sources"] == original["sources"]
    assert all(value["draft"][key] == item for key, item in original["draft"].items())
    edit(value, "split_all", time=2)
    assert [c["crop"] for c in source_track_clips(value, "A") if "crop" in c] == [crop, crop]
    edit(value, "move_range", start=2, end=3, to=6, mode="overwrite")
    moved = next(c for c in source_track_clips(value, "A") if c["start"] == 6)
    assert moved["crop"] == crop
    edit(value, "duplicate", slot="A", clip_id=moved["id"], start=10)
    value = json.loads(json.dumps(value))
    assert source_track_clips(value, "A")[-1]["crop"] == crop
    apply_manual_edit(value, {"action": "undo"})
    assert len([c for c in source_track_clips(value, "A") if "crop" in c]) == 2


@pytest.mark.parametrize("override", [{"x": -1}, {"y": 2}, {"zoom": .5}, {"x": True}, {"zoom": float("nan")}])
def test_invalid_framing_cannot_partially_modify_a_project(override):
    value = project()
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError):
        edit(value, "crop", slot="A", start=0, end=2, **{"x": .5, "y": .5, "zoom": 1, **override})
    assert value == before


def test_api_crop_has_history_and_never_changes_global_source_framing(track_api):
    _, store, project_id = track_api
    original_crop = copy.deepcopy(store.load(project_id)["manual"].get("crop"))
    response = post(track_api, {"action": "sequence_crop", "slot": "B", "start": 2, "end": 4, "x": .9, "y": .5, "zoom": 1})
    assert response.status_code == 200, response.get_json()
    value = store.load(project_id)
    assert source_track_clips(value, "B")[1]["crop"]["x"] == .9
    assert value["manual"].get("crop") == original_crop
    assert post(track_api, {"action": "undo"}).status_code == 200
    assert not any("crop" in c for c in source_track_clips(store.load(project_id), "B"))


def framed_project(fps=30):
    value = project()
    value["sources"] = {"A": {"duration": 2, "width": 200, "height": 100, "has_audio": False}}
    value["settings"] = {"fps": fps, "editorial_effects": False}
    value["draft"] = {"keep_ranges": [{"start": 0, "end": 2}], "camera_plan": [{"start": 0, "end": 2, "camera": "A"}]}
    edit(value, "crop", slot="A", start=0, end=1, x=0, y=.5, zoom=1)
    edit(value, "crop", slot="A", start=1, end=2, x=1, y=.5, zoom=1)
    return value


@pytest.mark.parametrize("layout", ["stacked", "side_by_side", "pip"])
def test_clip_focus_overrides_fit_for_only_the_selected_source(layout):
    value = framed_project()
    value["sources"]["B"] = copy.deepcopy(value["sources"]["A"])
    value["manual"]["source_tracks"]["B"] = [{"id": "b", "start": 0, "end": 2, "source_start": 0}]
    value["manual"]["source_mixer"] = {"stack_fit": "contain", "first_slot": "B"}
    value["manual"]["sequence"]["camera_plan"] = [{"start": 0, "end": 2, "camera": layout}]
    plan = render._frame_aligned_plan(value)
    assert len(plan) == 2, "same-layout shots with different framing cannot be merged"
    graph, _, _ = render.build_filter_graph(value, 320, 320)
    assert "(iw-ow)*0.00000" in graph and "(iw-ow)*1.00000" in graph
    assert "force_original_aspect_ratio=decrease" in graph, "unframed B keeps its fit setting"


def test_embedded_screen_focus_is_per_cut_without_moving_the_camera_window():
    value = framed_project()
    value["manual"]["embedded_camera"] = {"x": 0, "y": 0, "w": 1, "h": .3, "content_focus": {"x": .5, "y": .5}}
    value["draft"].update(layout="embedded_stack", embedded_layout_confirmed=True)
    value["manual"]["sequence"]["camera_plan"] = [{"start": 0, "end": 2, "camera": "embedded_stack"}]
    graph, _, _ = render.build_filter_graph(value, 100, 200)
    assert "(iw-ow)*0.00000" in graph and "(iw-ow)*1.00000" in graph
    assert graph.count("(iw-ow)*0.50000") == 2, "the face panel remains centered in both cuts"


@pytest.mark.parametrize("fps", [30, 60])
def test_actual_export_uses_left_focus_then_right_focus(tmp_path, fps):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is needed for pixel-level framing verification")
    source = tmp_path / "two-colors.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-f", "lavfi", "-i",
                    "color=red:s=100x100:r=30:d=2[left];color=blue:s=100x100:r=30:d=2[right];[left][right]hstack",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True, capture_output=True, timeout=20)
    value = framed_project(fps)
    plan = render._render_plan(value)
    assert [(row["start"], row["end"], row["crop"]["A"]["x"]) for row in plan] == [(0, 1, 0), (1, 2, 1)]
    graph, maps, _ = render.build_filter_graph(value, 100, 100)
    output = tmp_path / "framed.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-i", str(source), "-filter_complex", graph,
                    *maps, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)], check=True, capture_output=True, timeout=30)
    for second, channel in [(.5, 0), (1.5, 2)]:
        result = subprocess.run([ffmpeg, "-v", "error", "-ss", str(second), "-i", str(output), "-frames:v", "1",
                                 "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"],
                                check=True, capture_output=True, timeout=10)
        assert result.stdout[channel] > 200 and result.stdout[2 - channel] < 40
