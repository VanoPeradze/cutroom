import shutil
import subprocess

import pytest

from cutroom.render import punch_in_filter


def project(punches, goal="youtube", **settings):
    return {"draft": {"goal": goal, "punch_ins": punches}, "settings": settings, "manual": {}}


def test_filter_preserves_geometry_and_gates_each_window():
    expression = punch_in_filter(project([{"start": 2.0, "end": 3.4}, {"start": 40.0, "end": 41.4}]), 1920, 1080, 30, 60.0)
    assert expression.startswith("zoompan=")
    assert "between(in_time,2.000,3.400)+between(in_time,40.000,41.400)" in expression
    assert ":s=1920x1080:fps=30" in expression and ":d=1" in expression


@pytest.mark.parametrize("punches,goal,settings", [
    ([], "youtube", {}),
    ([{"start": 2, "end": 3}], "short", {}),
    ([{"start": 2, "end": 3}], "youtube", {"punch_ins": False}),
    ([{"start": 5, "end": 2}, {"start": 70, "end": 71}, {"start": 1, "end": 9}, "bad"], "youtube", {}),
])
def test_filter_is_skipped_when_not_applicable(punches, goal, settings):
    assert punch_in_filter(project(punches, goal, **settings), 1280, 720, 30, 60.0) is None


def test_filter_is_skipped_after_manual_sequence_edits():
    edited = project([{"start": 2, "end": 3}])
    edited["manual"] = {"sequence": {"version": 1}}
    assert punch_in_filter(edited, 1280, 720, 30, 60.0) is None


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_keeps_frame_count_and_size(tmp_path):
    expression = punch_in_filter(project([{"start": 1.0, "end": 2.0}]), 320, 180, 30, 4.0)
    output = tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=4",
                    "-vf", f"settb=1/30,setpts=N,{expression}", "-c:v", "libx264", "-preset", "ultrafast", str(output)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                            "-show_entries", "stream=width,height,nb_read_frames", "-of", "csv=p=0", str(output)],
                           check=True, capture_output=True, text=True).stdout.strip()
    assert probe == "320,180,120"
