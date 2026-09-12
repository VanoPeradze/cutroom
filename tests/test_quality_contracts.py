import pytest

from cutroom.director import _bounded_cuts, _assert_transcript_complete, _edit_quality_review
from cutroom.intelligence import StoryPlanningError
from cutroom.utils import range_duration, invert_ranges


def test_first_silence_cannot_turn_ten_minute_youtube_into_one_minute():
    cuts, counts = _bounded_cuts(
        [{"start": 50, "end": 590, "priority": 1, "reason": "silence"}],
        600, "gentle", "youtube", 60, [],
    )
    assert range_duration(invert_ranges(cuts, 600)) == 600
    assert not counts


def test_overlapping_automatic_cuts_use_union_budget():
    cuts, _ = _bounded_cuts(
        [{"start": 0, "end": 10}, {"start": 4, "end": 14}],
        100, "gentle", "youtube", 60, [],
    )
    assert range_duration(cuts) == 14


def test_manual_cuts_can_exceed_automatic_budget():
    cuts, counts = _bounded_cuts([], 600, "gentle", "youtube", 60, [{"start": 50, "end": 590}])
    assert range_duration(cuts) == 540
    assert counts["manual"] == 1


@pytest.mark.parametrize("reason", ["incomplete_transcription", "uncovered_detected_speech"])
def test_proven_missing_speech_cannot_be_silently_replaced_with_highlights(reason):
    with pytest.raises(StoryPlanningError):
        _assert_transcript_complete({"reasons": [reason]})


def test_legacy_unverified_coverage_needs_review_not_invented_failure():
    quality = {"reasons": [], "warnings": ["unverified_transcript_coverage"], "coverage_status": "unverified"}
    _assert_transcript_complete(quality)
    review = _edit_quality_review(quality, None, [], [], 600)
    assert review["needs_review"] is True
    assert review["warnings"][0]["type"] == "transcript_coverage"


def test_failed_critic_and_extractive_recovery_are_visible():
    review = _edit_quality_review({}, {
        "critic": {"verdict": "skipped"}, "summary_recovery": {"extractive_chapter_ids": ["c2"]},
    }, [], [], 100)
    assert review["needs_review"] is True
    assert len(review["warnings"]) == 2


def test_one_coherent_moment_is_reviewable_not_forced_into_random_distribution():
    segments = [{"start": i * 60, "end": i * 60 + 20} for i in range(10)]
    keep = [{"start": 0, "end": 35}]
    review = _edit_quality_review({}, None, segments, keep, 600)
    assert review["warnings"][0]["type"] == "selection_coverage"
    assert review["selected_source_sections"] == [0]
    assert keep == [{"start": 0, "end": 35}]


def test_incomplete_worker_evidence_survives_director_safety_wrapper(monkeypatch):
    from cutroom import director
    from cutroom.transcription import TranscriptionIncomplete, transcript_quality_report
    coverage = {"complete": False, "source_duration": 600, "expected_chunks": 20,
                "completed_chunks": 1, "failed_chunks": 1, "analyzed_ranges": [{"start": 0, "end": 30}]}

    def fail(*args, **kwargs):
        raise TranscriptionIncomplete("chunk failed", coverage)

    monkeypatch.setattr(director, "transcribe", fail)
    transcript, warning = director._transcribe_safely(None, None, "he", duration=600)
    assert transcript["coverage"] == coverage
    assert warning
    with pytest.raises(StoryPlanningError):
        _assert_transcript_complete(transcript_quality_report(transcript))


def test_equivalent_style_moments_are_not_always_broken_toward_source_start():
    from cutroom.director import _select_style_story_ranges
    rows = [{"id": str(i), "start": i * 60.0, "end": i * 60.0 + 10,
             "text": "A complete moment.", "editorial_score": .5} for i in range(10)]
    starts = {
        _select_style_story_ranges(rows, {}, 600, 60, {"max_moments": 1}, rows, selection_seed=seed)[0]["start"]
        for seed in range(10)
    }
    assert len(starts) >= 3
    assert max(starts) > 300
