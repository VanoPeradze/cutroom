"""A Clips-board export is a marked range of the composed edit, never one raw source."""
import copy
import shutil
import subprocess
import threading

from cutroom.config import DEFAULTS, Settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.render import render_project
from test_media_render import media  # noqa: F401  (fixture)


def _rgb(ffmpeg, path, time, x, y, width, height):
    data = subprocess.check_output([ffmpeg, "-v", "error", "-ss", f"{time:.3f}", "-i", str(path), "-an",
                                    "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"], timeout=20)
    assert len(data) == width * height * 3
    offset = (y * width + x) * 3
    return tuple(data[offset:offset + 3])


def _project(media, tmp_path):
    raw = copy.deepcopy(DEFAULTS)
    raw["render"].update(prefer_hardware=False, min_free_mb=0)
    data = tmp_path / "data"
    folders = [data / name for name in ("projects", "exports", "cache")]
    for folder in folders:
        folder.mkdir(parents=True)
    settings = Settings(raw, tmp_path, data, *folders, media[1], media[2])
    store = ProjectStore(settings)
    p = store.create("Screen and camera clips")
    root = store.project_dir(p["id"])
    shutil.copyfile(media[3], root / "media" / "screen.mp4")  # red, green, blue seconds
    subprocess.run([media[1], "-v", "error", "-y", "-f", "lavfi", "-i", "color=yellow:s=160x90:r=30:d=3",
                    "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=48000:duration=3",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-t", "3",
                    str(root / "media" / "camera.mp4")], check=True, capture_output=True, timeout=20)
    source = {"duration": 3., "width": 160, "height": 90, "has_audio": True}
    p["sources"] = {"A": {**source, "relative_path": "media/screen.mp4"},
                    "B": {**source, "relative_path": "media/camera.mp4"}}
    p["settings"].update(fps=30, aspect="9:16", resolution="720", quality="fast", captions=False,
                         burn_captions=False, editorial_effects=False, layout="auto")
    p["draft"] = {"source_duration": 3., "output_duration": 3., "keep_ranges": [{"start": 0., "end": 3.}],
                  "cuts": [], "camera_plan": [{"start": 0., "end": 3., "camera": "stacked"}],
                  "audio_policy": {"normalize": False}}
    p["analysis"] = {"transcript": {"segments": []}}
    p["manual"] = {"source_mixer": {"screen_slot": "A", "camera_slot": "B", "primary_role": "screen",
                                    "audio_slot": "B", "first_slot": "B", "stack_fit": "cover",
                                    "default_layout": "stacked", "sync_offset": 0.},
                   "source_tracks": {"A": [{"id": "A:main", "start": 0., "end": 3., "source_start": 0.}],
                                     "B": [{"id": "B:main", "start": 0., "end": 3., "source_start": 0.}]}}
    store.save(p)
    return store, settings, p["id"]


def test_marked_clip_keeps_the_stacked_screen_and_camera_layout(media, tmp_path):
    store, settings, pid = _project(media, tmp_path)
    revision = store.load(pid)["revision"]
    # A Clips-board moment from 1.0 s to 2.5 s: the green, then blue part of the screen.
    options = {"_force_software": True, "quality": "fast", "_require_layout_coverage": True,
               "range": {"start_frame": 30, "end_frame": 75, "fps": 30, "expected_revision": revision}}
    record = render_project(JobContext(Job("clip-layout", "render", pid), threading.Lock()),
                            pid, store, settings, options)["export"]
    output = settings.exports_dir / record["name"]
    probe = subprocess.check_output([media[2], "-v", "error", "-select_streams", "v:0", "-show_entries",
                                     "stream=width,height", "-of", "csv=p=0", str(output)], text=True).strip()
    width, height = map(int, probe.split(","))
    assert width < height  # vertical short
    top = _rgb(media[1], output, .3, width // 2, int(height * .12), width, height)
    bottom = _rgb(media[1], output, .3, width // 2, int(height * .7), width, height)
    late = _rgb(media[1], output, 1.2, width // 2, int(height * .7), width, height)
    yellow = lambda c: c[0] > 180 and c[1] > 180 and c[2] < 90
    assert yellow(top), top                                   # camera (B) panel on top
    assert bottom[1] > 180 and bottom[0] < 90 and bottom[2] < 90, bottom  # screen (A) green below
    assert late[2] > 180 and late[0] < 90 and late[1] < 90, late          # then blue, still stacked


def test_layout_coverage_is_checked_only_inside_the_marked_clip(media, tmp_path):
    import pytest
    from cutroom.render import LayoutCoverageError, require_layout_coverage
    store, settings, pid = _project(media, tmp_path)
    p = store.load(pid)
    # Both recordings stop after 1.5 s of a 3 s stacked edit: the whole edit
    # cannot be exported as arranged, but a clip inside 0-1.5 s can.
    for slot in ("A", "B"):
        p["manual"]["source_tracks"][slot] = [{"id": f"{slot}:main", "start": 0., "end": 1.5, "source_start": 0.}]
    p["manual"]["sequence"] = {"version": 1, "duration": 3.,
                               "camera_plan": [{"start": 0., "end": 3., "camera": "stacked"}]}
    store.save(p)
    p = store.load(pid)
    with pytest.raises(LayoutCoverageError):
        require_layout_coverage(p)
    inside = {"range": {"start_frame": 0, "end_frame": 30, "fps": 30, "expected_revision": p["revision"]}}
    crossing = {"range": {"start_frame": 30, "end_frame": 60, "fps": 30, "expected_revision": p["revision"]}}
    assert require_layout_coverage(p, inside) is None
    with pytest.raises(LayoutCoverageError):
        require_layout_coverage(p, crossing)
    record = render_project(JobContext(Job("clip-inside", "render", pid), threading.Lock()), pid, store, settings,
                            {"_force_software": True, "quality": "fast", "_require_layout_coverage": True, **inside})["export"]
    assert record["range"] == {"start_frame": 0, "end_frame": 30, "fps": 30}


def test_range_drains_use_a_discarded_output_not_in_graph_nullsinks():
    # FFmpeg 7.0/7.1 abort ("Assertion best_input >= 0") when both range
    # drains are nullsinks on a two-source layout.
    from cutroom.range_export import ExportRange

    scope = ExportRange(30, 75, 30)
    graph, maps = scope.mapped_graph("[x]null[vout];[y]anull[aout]", ["-map", "[vout]", "-map", "[aout]"], trim_audio=True)
    assert maps == ["-map", "[vrange]", "-map", "[arange]"]
    assert "nullsink" not in graph
    assert scope.drain_output_args(graph) == ["-map", "[vrangedrain]", "-map", "[arangedrain]", "-f", "null", "-"]
    single, _ = scope.mapped_graph("[x]null[vout]", ["-map", "[vout]"], trim_audio=True)
    assert scope.drain_output_args(single) == []
