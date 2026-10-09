import pytest

from cutroom.director import _assert_transcript_complete
from cutroom.intelligence import StoryPlanningError


def failure_message(reason, coverage):
    with pytest.raises(StoryPlanningError) as failure:
        _assert_transcript_complete({"reasons": [reason], "coverage": coverage})
    return str(failure.value)


def test_incomplete_audio_reports_unprocessed_gaps_on_the_source_b_clock():
    message = failure_message("incomplete_transcription", {
        "source_duration": 90, "timeline_offset": 120, "timeline_duration": 300,
        "analyzed_ranges": [{"start": 0, "end": 20}, {"start": 40, "end": 60}],
    })
    assert "No story was built from partial speech" in message
    assert "00:20-00:40, 01:00-01:30" in message
    assert "02:20" not in message
    assert "selected audio file" in message and "before synchronization" in message


def test_vad_review_reports_separate_ranges_without_labeling_intervening_audio_bad():
    message = failure_message("uncovered_detected_speech", {
        "source_duration": 7600,
        "vad_mismatch_chunks": [{"start": 3120, "end": 3150}, {"start": 3660.2, "end": 3690.1}],
    })
    assert "52:00-52:30, 01:01:00-01:01:31" in message
    assert "background voices or game audio" in message


def test_zero_processed_audio_points_to_the_whole_source():
    message = failure_message("incomplete_transcription", {
        "source_duration": 60, "analyzed_ranges": [],
    })
    assert "00:00-01:00" in message


@pytest.mark.parametrize("coverage", [None, {}, {"source_duration": float("nan"), "analyzed_ranges": []},
    {"source_duration": 60, "analyzed_ranges": [{"start": "bad", "end": 40}]},
    {"source_duration": 60, "analyzed_ranges": "unknown"}])
def test_missing_or_invalid_evidence_preserves_the_gate_without_inventing_times(coverage):
    message = failure_message("incomplete_transcription", coverage)
    assert "Transcription did not finish" in message
    assert "Unverified audio in" not in message


def test_many_suspect_ranges_are_bounded_in_the_failure_message():
    message = failure_message("uncovered_detected_speech", {
        "source_duration": 120,
        "vad_mismatch_chunks": [{"start": start, "end": start + 5} for start in [0, 20, 40, 60]],
    })
    assert "00:00-00:05, 00:20-00:25, 00:40-00:45 (+1 more)" in message
    assert "01:00-01:05" not in message


def test_review_hints_never_turn_a_complete_transcript_into_a_gate_failure():
    _assert_transcript_complete({"reasons": [], "coverage": {
        "source_duration": 60, "vad_mismatch_chunks": [{"start": 0, "end": 30}],
    }})
