"""Scheduled library footage must not be mislabeled as empty A/B time."""
import copy

import pytest

from cutroom import output_review


@pytest.mark.parametrize("coverage,expected", [
    ([(4, 5), (5, 6)], []),
    ([(5, 6), (4, 5), (4, 5)], []),
    ([(4, 4.5), (5.5, 6)], [(4.5, 5.5)]),
    ([], [(4, 6)]),
    ([(0, 4), (6, 8)], [(4, 6)]),
    ([(float("nan"), 6), (4, float("inf")), (6, 4)], [(4, 6)]),
])
def test_library_picture_coverage_preserves_only_actual_unoccupied_time(coverage, expected):
    gaps = [(4, 6)]
    before = copy.deepcopy((gaps, coverage))
    assert output_review.remaining_picture_gaps(gaps, coverage) == expected
    assert (gaps, coverage) == before


def test_structural_coverage_does_not_suppress_actual_black_pixel_review(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(output_review, "_run", lambda command, _timeout: calls.append(command) or "black_start:4 black_end:6")
    result = output_review.review_export(
        "fixture-ffmpeg", tmp_path / "render.mp4", duration=6, has_audio=False,
        ceiling_dbtp=-1, target_lufs=None, caption_lines=[], text_clips=[],
        timeline_gaps=output_review.remaining_picture_gaps([(4, 6)], [(4, 6)]))
    checks = {row["id"]: row for row in result["checks"]}
    assert checks["timeline_gaps"]["status"] == "pass"
    assert checks["black_video"]["status"] == "warn"
    assert any("blackdetect" in str(argument) for command in calls for argument in command)
