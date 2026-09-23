from __future__ import annotations

import copy
import shutil
import subprocess

import pytest

from cutroom.config import load_settings
from cutroom.director import _effective_brief
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.manual_start import start_manual_draft
from cutroom.render import build_filter_graph
from server import _inferred_source_mixer, create_app


def _project(camera_slot: str = "B") -> dict:
    screen_slot = "B" if camera_slot == "A" else "A"
    return {
        "sources": {
            slot: {"duration": 1.0, "width": 160, "height": 90, "has_audio": False}
            for slot in ("A", "B")
        },
        "settings": {"aspect": "9:16", "editorial_effects": False},
        "analysis": {"sync": {"offset": 0.0}},
        "manual": {"cuts": [], "crop": {}, "source_mixer": {
            "screen_slot": screen_slot, "camera_slot": camera_slot,
            "primary_role": "screen", "audio_slot": camera_slot, "first_slot": camera_slot,
            "default_layout": "stacked",
        }},
        "draft": {
            "cuts": [],
            "keep_ranges": [{"start": 0.0, "end": 1.0}],
            "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "stacked"}],
            "output_duration": 1.0,
        },
    }


def _mixer_request(project: dict, **changes) -> dict:
    return {"action": "set_source_mixer", **project["manual"]["source_mixer"], **changes}


def test_creator_cover_is_preserved_by_other_mixer_edits_and_can_be_undone():
    project = _project()
    original = copy.deepcopy(project["manual"]["source_mixer"])
    apply_manual_edit(project, _mixer_request(project, stack_fit="cover"))
    assert project["manual"]["source_mixer"]["stack_fit"] == "cover"
    apply_manual_edit(project, {"action": "undo"})
    assert project["manual"]["source_mixer"] == original
    apply_manual_edit(project, {"action": "redo"})
    assert project["manual"]["source_mixer"]["stack_fit"] == "cover"

    request = _mixer_request(project, audio_slot="A")
    request.pop("stack_fit")
    apply_manual_edit(project, request)
    assert project["manual"]["source_mixer"]["stack_fit"] == "cover"
    assert project["manual"]["source_mixer"]["first_slot"] == "B"

    apply_manual_edit(project, _mixer_request(project, stack_fit="contain"))
    assert project["manual"]["source_mixer"]["stack_fit"] == "contain"
    apply_manual_edit(project, {"action": "undo"})
    assert project["manual"]["source_mixer"]["stack_fit"] == "cover"


@pytest.mark.parametrize("invalid", ["stretch", "cover,pad=1:1", "", None, True])
def test_creator_cover_rejects_invalid_fit_without_changing_source_roles(invalid):
    project = _project()
    original = copy.deepcopy(project["manual"]["source_mixer"])
    with pytest.raises(ManualEditError, match="Stack framing"):
        apply_manual_edit(project, _mixer_request(project, stack_fit=invalid))
    assert project["manual"]["source_mixer"] == original


def test_local_api_accepts_creator_cover_and_preserves_it_on_later_edits(monkeypatch, tmp_path):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    app = create_app(load_settings())
    app.config.update(TESTING=True)
    store = app.extensions["cutroom_store"]
    project = store.create("creator-frame-validation")
    sample = _project("A")
    project.update({key: sample[key] for key in ("sources", "settings", "analysis", "manual", "draft")})
    project = store.save(project)
    client = app.test_client()
    endpoint = f"/api/projects/{project['id']}/manual/edit"

    response = client.post(endpoint, json={
        **_mixer_request(project, stack_fit="cover"), "expected_revision": project["revision"],
    })
    assert response.status_code == 200, response.get_json()
    saved = response.get_json()["project"]
    assert saved["manual"]["source_mixer"]["stack_fit"] == "cover"
    assert saved["manual"]["source_mixer"]["first_slot"] == "A"

    request = _mixer_request(saved, audio_slot="B")
    request.pop("stack_fit")
    response = client.post(endpoint, json={**request, "expected_revision": saved["revision"]})
    assert response.status_code == 200, response.get_json()
    saved = response.get_json()["project"]
    assert saved["manual"]["source_mixer"]["stack_fit"] == "cover"
    assert store.load(project["id"])["manual"]["source_mixer"]["stack_fit"] == "cover"

    rejected = client.post(endpoint, json={
        **_mixer_request(saved, stack_fit="stretch"), "expected_revision": saved["revision"],
    })
    assert rejected.status_code == 400
    assert store.load(project["id"])["revision"] == saved["revision"]


@pytest.mark.parametrize("camera_slot", ["A", "B"])
@pytest.mark.parametrize("explicit", [False, True])
def test_creator_graph_routes_camera_above_screen_and_fills_30_70_panels(camera_slot, explicit):
    project = _project(camera_slot)
    if explicit:
        project["manual"]["source_mixer"]["stack_fit"] = "cover"
    else:
        project["manual"]["source_mixer"].pop("first_slot")
    graph, _, has_audio = build_filter_graph(project, 360, 640)
    camera_input = "av0" if camera_slot == "A" else "bv0"
    screen_input = "bv0" if camera_slot == "A" else "av0"
    assert has_audio is False
    assert f"[{camera_input}]trim=start_frame=0:end_frame=30,setpts=PTS-STARTPTS,scale=360:192" in graph
    assert f"[{screen_input}]trim=start_frame=0:end_frame=30,setpts=PTS-STARTPTS,scale=360:448" in graph
    assert "[face0][screen0]vstack=inputs=2" in graph
    assert "crop=360:192:" in graph and "crop=360:448:" in graph
    assert "force_original_aspect_ratio=decrease" not in graph
    assert "pad=360:" not in graph

    # An explicit full-frame choice keeps its padding, including saved projects.
    project["manual"]["source_mixer"]["stack_fit"] = "contain"
    legacy, _, _ = build_filter_graph(project, 360, 640)
    assert "pad=360:192:" in legacy and "pad=360:448:" in legacy


@pytest.mark.parametrize("aspect", ["16:9", "1:1", "4:5", "source"])
def test_nonvertical_stack_keeps_full_frames_and_original_order(aspect):
    project = _project()
    project["settings"]["aspect"] = aspect
    project["manual"]["source_mixer"].pop("first_slot")
    graph, _, _ = build_filter_graph(project, 640, 360)
    assert "[screen0][face0]vstack=inputs=2" in graph
    assert "pad=640:108:" in graph and "pad=640:252:" in graph


def test_saved_reordered_camera_primary_stack_keeps_its_manual_choices():
    project = _project()
    project["manual"]["source_mixer"].update(first_slot="A", primary_role="camera", stack_fit="contain")
    apply_manual_edit(project, {"action": "set_source_mixer", "screen_slot": "A", "camera_slot": "B",
                                "primary_role": "camera", "audio_slot": "A"})
    graph, _, _ = build_filter_graph(project, 360, 640)
    assert "[screen0][face0]vstack=inputs=2" in graph
    assert "scale=360:448:force_original_aspect_ratio=decrease" in graph
    assert "pad=360:448:" in graph and "pad=360:192:" in graph


@pytest.mark.parametrize("camera_slot", ["A", "B"])
def test_real_creator_frame_has_red_camera_above_blue_gameplay_without_black_bars(camera_slot):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    project = _project(camera_slot)
    project["manual"]["source_mixer"].pop("first_slot")
    graph, maps, has_audio = build_filter_graph(project, 360, 640)
    assert has_audio is False
    inputs = []
    for slot in ("A", "B"):
        color = "red" if slot == camera_slot else "blue"
        inputs.extend(["-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=30:d=1"])
    completed = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "1",
        *inputs, "-filter_complex", graph, *maps, "-frames:v", "1", "-threads", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert len(completed.stdout) == 360 * 640 * 3

    # Check every row at both edges and across the frame. A contain regression
    # produces black horizontal bands; a role/order regression swaps the colors.
    for y in range(640):
        if 190 <= y <= 193:  # Allow the YUV420 chroma transition at the panel seam.
            continue
        for x in (0, 90, 180, 270, 359):
            offset = (y * 360 + x) * 3
            red, green, blue = completed.stdout[offset:offset + 3]
            if y < 192:
                assert red > 200 and green < 35 and blue < 35, (x, y, red, green, blue)
            else:
                assert blue > 200 and red < 35 and green < 35, (x, y, red, green, blue)


@pytest.mark.parametrize("camera_slot", ["A", "B"])
def test_new_reels_upload_and_manual_start_default_to_camera_above_screen(camera_slot):
    project = _project(camera_slot)
    project["settings"].update(goal="short", layout="auto")
    for slot, source in project["sources"].items():
        source["name"] = "creator-facecam.mp4" if slot == camera_slot else "gameplay-screen.mp4"
    project["manual"]["source_mixer"] = _inferred_source_mixer(project)
    assert project["manual"]["source_mixer"]["first_slot"] == camera_slot
    project["draft"] = None
    start_manual_draft(project)
    assert project["draft"]["layout"] == "stacked"
    assert project["draft"]["camera_plan"] == [{"start": 0.0, "end": 1.0, "camera": "stacked"}]
    graph, _, _ = build_filter_graph(project, 360, 640)
    assert "[face0][screen0]vstack=inputs=2" in graph
    assert "crop=360:192:" in graph and "crop=360:448:" in graph
    assert "pad=360:" not in graph


@pytest.mark.parametrize("explicit_layout", [None, "auto", "screen", "camera", "pip", "side_by_side", "stacked"])
def test_reels_director_and_sequence_default_stack_respect_explicit_mixer_layout(explicit_layout):
    project = _project()
    project["settings"].update(goal="short", layout="auto")
    mixer = project["manual"]["source_mixer"]
    if explicit_layout is None:
        mixer.pop("default_layout")
    else:
        mixer["default_layout"] = explicit_layout
    expected = explicit_layout if explicit_layout is not None else "stacked"
    assert _effective_brief(project)["layout"] == expected
    apply_manual_edit(project, {"action": "sequence_layout", "start": 0, "end": 1, "layout": "auto"})
    # Explicit Auto retains the existing sequence behavior of showing the primary role.
    assert project["manual"]["sequence"]["camera_plan"][0]["camera"] == ("screen" if expected == "auto" else expected)


@pytest.mark.parametrize("aspect,layout", [("16:9", "auto"), ("source", "auto"), ("9:16", "pip"), ("9:16", "side_by_side")])
def test_reels_director_does_not_override_saved_aspect_or_layout(aspect, layout):
    project = _project()
    project["manual"]["source_mixer"].pop("default_layout")
    project["settings"].update(goal="short", aspect=aspect, layout=layout)
    brief = _effective_brief(project)
    assert brief["aspect"] == aspect
    assert brief["layout"] == layout


@pytest.mark.parametrize("width,height", [(360, 640), (640, 360), (320, 180)])
def test_confirmed_embedded_single_source_uses_the_same_30_70_creator_frame(width, height):
    project = _project()
    project["sources"]["B"] = None
    project["manual"] = {"crop": {}, "embedded_camera": {
        "x": 0.72, "y": 0.06, "w": 0.24, "h": 0.24,
        "content_focus": {"x": 0.32, "y": 0.58},
    }}
    project["draft"].update({
        "layout": "embedded_stack", "embedded_layout_confirmed": True,
        "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "embedded_stack"}],
    })
    graph, _, _ = build_filter_graph(project, width, height)
    face_h = int(height * .30) // 2 * 2
    assert "split=2[amain0][aface0]" in graph
    assert "crop=iw*0.240000:ih*0.240000:iw*0.720000:ih*0.060000" in graph
    assert f"scale={width}:{face_h}:force_original_aspect_ratio=increase" in graph
    assert f"scale={width}:{height - face_h}:force_original_aspect_ratio=increase" in graph
    assert "[face0][content0]vstack=inputs=2" in graph
    assert "pad=360:" not in graph

    project["draft"]["embedded_layout_confirmed"] = False
    unconfirmed, _, _ = build_filter_graph(project, 360, 640)
    assert "vstack=inputs=2" not in unconfirmed


@pytest.mark.parametrize("rectangle,box", [
    ({"x": 0.0, "y": 0.0, "w": 1.0, "h": .3}, "x=0:y=0:w=160:h=27"),
    ({"x": 0.0, "y": 0.0, "w": .5, "h": 1.0}, "x=0:y=0:w=80:h=90"),
    ({"x": .7, "y": .1, "w": .3, "h": .4}, "x=112:y=9:w=48:h=36"),
])
def test_real_embedded_render_never_repeats_marked_camera_in_gameplay(rectangle, box):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    project = _project()
    project["sources"]["B"] = None
    project["manual"] = {"crop": {}, "embedded_camera": {**rectangle, "content_focus": {"x": .5, "y": .5}}}
    project["draft"].update({
        "layout": "embedded_stack", "embedded_layout_confirmed": True,
        "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "embedded_stack"}],
    })
    graph, maps, _ = build_filter_graph(project, 360, 640)
    completed = subprocess.run([
        ffmpeg, "-hide_banner", "-loglevel", "error", "-filter_complex_threads", "1",
        "-f", "lavfi", "-i", f"color=c=blue:s=160x90:r=30:d=1,drawbox={box}:color=red:t=fill",
        "-filter_complex", graph, *maps, "-frames:v", "1", "-threads", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], capture_output=True, timeout=15)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    assert len(completed.stdout) == 360 * 640 * 3
    # Camera is readable at the top; every sampled gameplay row stays blue.
    for y in (10, 80, 170):
        offset = (y * 360 + 180) * 3
        red, green, blue = completed.stdout[offset:offset + 3]
        assert red > 200 and green < 40 and blue < 40, (y, red, green, blue)
    for y in range(196, 636, 8):
        for x in (4, 90, 180, 270, 355):
            offset = (y * 360 + x) * 3
            red, green, blue = completed.stdout[offset:offset + 3]
            assert blue > 190 and red < 60 and green < 40, (x, y, red, green, blue)


def test_narrow_confirmed_camera_crop_is_not_expanded_outside_the_marked_edge():
    project = _project()
    project["sources"]["B"] = None
    project["manual"] = {"crop": {}, "embedded_camera": {"x": .94, "y": .1, "w": .06, "h": .2}}
    project["draft"].update({
        "layout": "embedded_stack", "embedded_layout_confirmed": True,
        "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "embedded_stack"}],
    })
    graph, _, _ = build_filter_graph(project, 360, 640)
    # Validator accepts .06; the renderer used to grow it to .08 and go past x=1.
    assert "crop=iw*0.060000:ih*0.200000:iw*0.940000:ih*0.100000" in graph
