from __future__ import annotations

import shutil
import subprocess

import pytest

from cutroom import output_review


def test_text_that_covers_captions_in_the_same_area_is_named():
    captions = [{"start": 0.0, "end": 3.0, "text": "Hello there"}, {"start": 3.0, "end": 6.0, "text": "Next line"}]
    clash = output_review._overlap_check(captions, [
        {"start": 1.0, "end": 4.0, "position": "bottom", "template": "lower_third", "text": "Dana"},
    ], "auto")
    assert clash["status"] == "warn" and clash["times"] == [1.0, 3.0]
    clear = output_review._overlap_check(captions, [
        {"start": 1.0, "end": 4.0, "position": "bottom", "template": "callout", "text": "Look left"},
        {"start": 1.0, "end": 2.0, "position": "center", "text": "Title"},
    ], "auto")
    assert clear["status"] == "pass"
    # Two authored overlays in the same place also collide; captions alone never do.
    assert output_review._overlap_check([], [
        {"start": 0.0, "end": 2.0, "position": "top", "text": "A"},
        {"start": 1.0, "end": 3.0, "position": "top", "template": "highlight", "text": "B"},
    ], "auto")["status"] == "warn"
    assert output_review._overlap_check(captions, [], "auto")["status"] == "pass"


def test_very_long_caption_lines_are_counted():
    lines = [{"start": 0.0, "end": 2.0, "text": "short"}, {"start": 5.0, "end": 9.0, "text": "word " * 20}]
    check = output_review._caption_length_check(lines)
    assert check["status"] == "warn" and check["count"] == 1 and "5.0 s" in check["detail"]


def test_review_of_a_real_file_finds_black_picture_and_measures_audio(tmp_path):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg runtime is not installed")
    video = tmp_path / "gap.mp4"
    graph = ("color=gray:s=160x90:r=30:d=1.5[a];color=black:s=160x90:r=30:d=1.5[b];color=gray:s=160x90:r=30:d=1.5[c];"
             "[a][b][c]concat=n=3:v=1:a=0[v]")
    subprocess.run([ffmpeg, "-v", "error", "-y", "-filter_complex", graph, "-f", "lavfi", "-i", "sine=frequency=440:duration=4.5",
                    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(video)],
                   check=True, capture_output=True, timeout=30)
    review = output_review.review_export(ffmpeg, video, duration=4.5, has_audio=True, ceiling_dbtp=-1.0, target_lufs=None,
                                         caption_lines=[], text_clips=[])
    checks = {row["id"]: row for row in review["checks"]}
    assert checks["true_peak"]["status"] == "pass" and checks["true_peak"]["true_peak_dbtp"] < -10
    assert checks["loudness"]["status"] == "info"
    black = checks["black_video"]
    assert black["status"] == "warn" and black["ranges"][0]["start"] == pytest.approx(1.5, abs=0.3)
    assert review["warnings"] == 1 and review["seconds"] >= 0
    # Normalized exports are compared with the target the user set.
    louder = output_review.review_export(ffmpeg, video, duration=4.5, has_audio=True, ceiling_dbtp=-1.0, target_lufs=-16.0,
                                         caption_lines=[], text_clips=[])
    assert {row["id"]: row for row in louder["checks"]}["loudness"]["status"] == "warn"


def test_empty_timeline_gaps_are_named_exactly():
    assert output_review._gap_check([])["status"] == "pass"
    assert output_review._gap_check([(2.0, 2.5)])["status"] == "pass", "a short gap is not flagged"
    check = output_review._gap_check([(1.5, 2.0), (4.0, 6.0)])
    assert check["status"] == "warn" and check["ranges"] == [{"start": 4.0, "end": 6.0}] and "4.0–6.0 s" in check["detail"]
