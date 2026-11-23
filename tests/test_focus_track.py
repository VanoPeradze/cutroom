import shutil
import subprocess

import pytest

from cutroom.render import _cover_track_filter, _focus_track, _track_x_expression
from cutroom.vision import focus_track


def detections(path):
    return [{"time": float(t), "cx": x, "cy": 0.4} for t, x in path]


def test_track_is_smoothed_and_ignores_a_single_misdetection():
    track = focus_track(detections([(0, 0.30), (10, 0.32), (20, 0.95), (30, 0.36), (40, 0.60), (50, 0.62)]))
    assert [row["time"] for row in track] == [0, 10, 20, 30, 40, 50]
    assert track[2]["x"] == pytest.approx(0.36)  # the 0.95 outlier is the median-of-3 loser
    assert all(0.0 <= row["x"] <= 1.0 for row in track)


def test_still_subject_or_too_few_samples_gives_no_track():
    assert focus_track(detections([(0, 0.50), (10, 0.52), (20, 0.51), (30, 0.50)])) == []
    assert focus_track(detections([(0, 0.2), (10, 0.8)])) == []
    assert focus_track([{"time": "x"}, {}]) == []


def project(crop=None, track=None):
    focus = {"x": 0.4, "y": 0.4}
    return {
        "analysis": {"vision": {"focus": focus, "focus_track": track if track is not None else [
            {"time": 0, "x": 0.2}, {"time": 10, "x": 0.5}, {"time": 20, "x": 0.8}]}},
        "manual": {"crop": {"A": dict(focus) if crop is None else crop}},
    }


def test_render_uses_the_track_only_while_the_automatic_focus_is_untouched():
    assert len(_focus_track(project(), "A", None)) == 3
    assert _focus_track(project(), "B", None) == []
    assert _focus_track(project(), "A", {"x": 0.1, "y": 0.5}) == []  # per-clip crop wins
    assert _focus_track(project(crop={"x": 0.7, "y": 0.4}), "A", None) == []  # manual reframe wins
    assert _focus_track(project(crop={"x": 0.4, "y": 0.4, "zoom": 1.5}), "A", None) == []
    assert _focus_track(project(track=[{"time": 0, "x": 0.2}]), "A", None) == []


def test_expression_is_on_the_source_clock():
    expression = _track_x_expression([{"time": 0, "x": 0.2}, {"time": 10, "x": 0.5}, {"time": 20, "x": 0.8}], 12.5)
    assert "(t+12.500000)" in expression and expression.count("if(") == 3


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_pans_inside_one_segment(tmp_path):
    cover = _cover_track_filter(90, 160, (0.5, 0.5, 1.0), [{"time": 0, "x": 0.0}, {"time": 2, "x": 1.0}, {"time": 4, "x": 1.0}], 0.0)
    output = tmp_path / "out.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30:duration=3",
                    "-filter_complex", f"[0:v]setpts=PTS-STARTPTS,{cover}[o]", "-map", "[o]", str(output)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(output)],
                           check=True, capture_output=True, text=True).stdout.strip()
    assert probe == "90,160"
