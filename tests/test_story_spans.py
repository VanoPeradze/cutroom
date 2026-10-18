from __future__ import annotations

import copy

import pytest

from cutroom.story_budget import compact_story_pauses_to_target, story_duration_cost
from cutroom.story_spans import (
    SOURCE_SPAN_POLICY_VERSION, SOURCE_SPAN_SUMMARY_SOURCE, build_source_span_constraints,
    validate_source_span_constraints, whole_utterance_story_summary,
)


def fixture():
    segments = [
        {"id": "s0", "start": 0., "end": 4., "text": "It is not safe.", "words": [
            {"word": "It", "start": .1, "end": .3}, {"word": "is", "start": .4, "end": .6},
            {"word": "not", "start": 2., "end": 2.3}, {"word": "safe.", "start": 3.2, "end": 3.8}]},
        {"id": "s1", "start": 4., "end": 8., "text": "We must wait for the test.", "words": [
            {"word": "We", "start": 4.1, "end": 4.4}, {"word": "must", "start": 4.5, "end": 4.8},
            {"word": "wait", "start": 5., "end": 5.4}, {"word": "for", "start": 5.5, "end": 5.8},
            {"word": "the", "start": 6., "end": 6.2}, {"word": "test.", "start": 7., "end": 7.8}]},
        {"id": "s2", "start": 10., "end": 12., "text": "The test failed."},
    ]
    candidates = [
        {"id": "b0", "start": 0., "end": 8., "segment_ids": ["s0", "s1"],
         "text": "It is not safe. We must wait for the test."},
        {"id": "b1", "start": 10., "end": 12., "segment_ids": ["s2"], "text": "The test failed."},
    ]
    return candidates, segments


def build(candidates, segments, **kwargs):
    return build_source_span_constraints(candidates, segments, selected_beat_ids=["b0", "b1"], **kwargs)


def validate(proof, candidates, segments, **kwargs):
    return validate_source_span_constraints(proof, candidates, segments,
                                            selected_beat_ids=["b0", "b1"], **kwargs)


def test_constraints_bind_all_utterances_and_exact_shared_pause_policy_without_mutation():
    candidates, segments = fixture()
    before = copy.deepcopy((candidates, segments))

    proof = build(candidates, segments)

    ranges = [{"start": 0., "end": 8.}, {"start": 10., "end": 12.}]
    cost = story_duration_cost(ranges, segments, 12.)
    expected = compact_story_pauses_to_target(ranges, segments, 12., cost["minimum_safe_seconds"])
    assert proof["policy_version"] == SOURCE_SPAN_POLICY_VERSION
    assert proof["verification_scope"] == "source_retention_only"
    assert proof["segment_ids"] == ["s0", "s1", "s2"]
    assert proof["required_minimum_ranges"] == expected
    assert "semantic_mapping_verified" not in proof
    assert validate(proof, candidates, segments, keep_ranges=expected) == proof
    assert (candidates, segments) == before


def test_whole_utterance_summary_keeps_negation_prerequisites_and_conclusion():
    candidates, segments = fixture()
    proof = build(candidates, segments)
    proof["model_summary"] = "Invented successful outcome"

    summary = whole_utterance_story_summary(proof)

    assert SOURCE_SPAN_SUMMARY_SOURCE == "canonical_retained_source_utterances"
    assert summary == "Retained source utterances:\n\u201cIt is not safe.\u201d\n\u201cWe must wait for the test.\u201d\n\u201cThe test failed.\u201d"
    assert "Invented" not in summary


@pytest.mark.parametrize("keep", [
    [{"start": 0., "end": 1.}, {"start": 2.4, "end": 8.}, {"start": 10., "end": 12.}],
    [{"start": 0., "end": 4.}, {"start": 10., "end": 12.}],
    [{"start": 0., "end": 8.}],
    [{"start": 0., "end": 1.95}, {"start": 2., "end": 8.}, {"start": 10., "end": 12.}],
])
def test_omitting_negation_utterance_prerequisite_utterance_conclusion_or_handle_fails(keep):
    candidates, segments = fixture()
    proof = build(candidates, segments)

    with pytest.raises(ValueError, match="mandatory whole-utterance"):
        validate(proof, candidates, segments, keep_ranges=keep)


@pytest.mark.parametrize("corruption", ["missing", "mismatch", "partial", "malformed", "overlap", "nonfinite"])
def test_uncertain_word_mapping_locks_the_entire_utterance(corruption):
    candidates, segments = fixture()
    segment = segments[0]
    if corruption == "missing":
        segment.pop("words")
    elif corruption == "mismatch":
        segment["words"][2]["word"] = "possibly"
    elif corruption == "partial":
        segment["word_timing_complete"] = False
    elif corruption == "malformed":
        segment["words"][2]["start"] = None
    elif corruption == "nonfinite":
        segment["words"][2]["end"] = float("nan")
    else:
        segment["words"][2]["start"] = .5
    proof = build(candidates, segments)

    assert any(row["start"] <= 0. and row["end"] >= 4. for row in proof["required_minimum_ranges"])
    with pytest.raises(ValueError, match="mandatory whole-utterance"):
        validate(proof, candidates, segments, keep_ranges=[
            {"start": 0., "end": 1.}, {"start": 1.2, "end": 8.}, {"start": 10., "end": 12.}])


@pytest.mark.parametrize("field", ["text", "word_time", "word_flag"])
def test_exact_source_changes_invalidate_existing_proof(field):
    candidates, segments = fixture()
    proof = build(candidates, segments)
    if field == "text":
        segments[0]["text"] = "It is now safe."
        candidates[0]["text"] = "It is now safe. We must wait for the test."
    elif field == "word_time":
        segments[0]["words"][2]["start"] += .01
    else:
        segments[0]["word_timing_complete"] = True

    with pytest.raises(ValueError, match="current exact retained source"):
        validate(proof, candidates, segments)


def test_equivalent_candidate_presentation_whitespace_does_not_change_source_proof():
    candidates, segments = fixture()
    proof = build(candidates, segments)
    candidates[0]["text"] = "  It is not safe.\n\tWe must wait for the test.  "

    assert build(candidates, segments) == proof
    assert validate(proof, candidates, segments) == proof


def test_actual_asr_whitespace_remains_exactly_bound_to_source_proof():
    candidates, segments = fixture()
    proof = build(candidates, segments)
    segments[0]["text"] = "  It is not safe.  "

    # Candidate presentation still normalizes to the same words, but the
    # canonical ASR source itself changed and must invalidate the prior proof.
    assert build(candidates, segments)["source_fingerprint"] != proof["source_fingerprint"]
    with pytest.raises(ValueError, match="current exact retained source"):
        validate(proof, candidates, segments)


@pytest.mark.parametrize("change", [
    lambda candidates, segments: candidates.append(copy.deepcopy(candidates[0])),
    lambda candidates, segments: segments.append(copy.deepcopy(segments[0])),
    lambda candidates, segments: candidates[0].update(segment_ids=["s0", "s0"]),
    lambda candidates, segments: candidates[0].update(segment_ids=["missing"]),
    lambda candidates, segments: candidates[1].update(segment_ids=["s1", "s2"]),
    lambda candidates, segments: candidates[0].update(start=.1),
    lambda candidates, segments: candidates[0].update(segment_ids=["s0"]),
    lambda candidates, segments: candidates[0].update(segment_ids=["s1", "s0"]),
    lambda candidates, segments: candidates[0].update(text="It is safe. We must wait for the test."),
    lambda candidates, segments: segments[0].update(start=float("nan")),
    lambda candidates, segments: segments[0].update(text=None),
    lambda candidates, segments: (segments[1].update(text="We must wait"),
                                 candidates[0].update(text="It is not safe. We must wait")),
])
def test_duplicate_unknown_ambiguous_clipped_incomplete_and_malformed_source_fail(change):
    candidates, segments = fixture()
    change(candidates, segments)

    with pytest.raises(ValueError):
        build(candidates, segments)


def test_unknown_selected_or_rejected_selected_source_fails():
    candidates, segments = fixture()
    with pytest.raises(ValueError, match="unknown selected"):
        build_source_span_constraints(candidates, segments, selected_beat_ids=["missing"])
    with pytest.raises(ValueError, match="Rejected"):
        build(candidates, segments, rejected_beat_ids=["b0"])


def test_reproof_can_record_outside_rejections_without_authenticating_their_authority():
    candidates, segments = fixture()
    # Director may reconstruct retained units only; its caller authenticates
    # excluded source IDs against the full canonical domain separately.
    proof = build_source_span_constraints(candidates[:1], segments,
        selected_beat_ids=["b0"], rejected_beat_ids=["b1"])

    assert proof["rejected_beat_ids"] == ["b1"]
    assert proof["verification_scope"] == "source_retention_only"
    assert validate_source_span_constraints(proof, candidates[:1], segments,
        selected_beat_ids=["b0"], rejected_beat_ids=["b1"]) == proof


@pytest.mark.parametrize("change", [
    lambda proof: proof.update(policy_version="old"),
    lambda proof: proof["utterances"][0].update(text="It is safe."),
    lambda proof: proof["required_minimum_ranges"].clear(),
    lambda proof: proof.update(source_fingerprint="0" * 64),
    lambda proof: proof.update(selected_beat_ids=["b0"]),
])
def test_changed_proof_is_rejected(change):
    candidates, segments = fixture()
    proof = build(candidates, segments)
    change(proof)

    with pytest.raises(ValueError, match="current exact retained source"):
        validate(proof, candidates, segments)


@pytest.mark.parametrize("keep", [
    [], [{"start": 10., "end": 12.}, {"start": 0., "end": 8.}],
    [{"start": 0., "end": 8.}, {"start": 0., "end": 8.}, {"start": 10., "end": 12.}],
    [{"start": 0., "end": 8.}, {"start": 7., "end": 12.}],
    [{"start": False, "end": 12.}],
])
def test_timeline_order_repeats_overlap_and_invalid_intervals_fail(keep):
    candidates, segments = fixture()
    with pytest.raises(ValueError):
        validate(build(candidates, segments), candidates, segments, keep_ranges=keep)


def test_retention_validation_leaves_additional_footage_authorization_to_caller():
    candidates, segments = fixture()
    proof = build(candidates, segments)
    # Authorization of the extra source interval is intentionally a caller check.
    assert validate(proof, candidates, segments, keep_ranges=[{"start": 0., "end": 12.}]) == proof


def test_larger_valid_shared_fits_preserve_the_same_minimum_speech_and_handle_locks():
    candidates, segments = fixture()
    proof = build(candidates, segments)
    cost = story_duration_cost(proof["approved_ranges"], segments, 12.)
    for target in [cost["minimum_safe_seconds"], cost["minimum_safe_seconds"] + .013,
                   cost["approved_seconds"] - .05, cost["approved_seconds"]]:
        keep = compact_story_pauses_to_target(proof["approved_ranges"], segments, 12., target)
        assert keep is not None
        assert validate(proof, candidates, segments, keep_ranges=keep) == proof


def test_invalid_word_float_identity_is_stable_and_not_silently_dropped():
    candidates, segments = fixture()
    segments[0]["words"][2]["start"] = float("nan")
    first = build(candidates, segments)
    assert first == build(candidates, segments)
    segments[0]["words"][2]["start"] = float("inf")
    second = build(candidates, segments)
    assert first["required_minimum_ranges"] == second["required_minimum_ranges"]
    assert first["source_fingerprint"] != second["source_fingerprint"]


def test_huge_source_timestamp_is_a_validation_error():
    candidates, segments = fixture()
    segments[0]["start"] = 10 ** 1000
    with pytest.raises(ValueError, match="finite source timestamps"):
        build(candidates, segments)


def test_summary_preserves_long_utterances_and_repeated_source_words_without_truncation():
    text = " ".join(f"measurement{index}" for index in range(100)) + "."
    segments = [{"id": "s0", "start": 0., "end": 8., "text": text},
                {"id": "s1", "start": 8., "end": 10., "text": "No, no, no."},
                {"id": "s2", "start": 10., "end": 12., "text": "No, no, no."}]
    candidates = [{"id": "b0", "start": 0., "end": 12., "segment_ids": ["s0", "s1", "s2"],
                   "text": " ".join(row["text"] for row in segments)}]
    proof = build_source_span_constraints(candidates, segments, selected_beat_ids=["b0"])

    summary = whole_utterance_story_summary(proof)

    assert len(summary) > 500 and summary.count("No, no, no.") == 2
    assert summary == "Retained source utterances:\n" + "\n".join(f"\u201c{row['text']}\u201d" for row in segments)
