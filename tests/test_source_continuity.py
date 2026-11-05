"""Mechanical proposed-draft continuity is distinct from output/meaning count."""
from __future__ import annotations

import copy
import json
import math

import pytest

from cutroom.source_continuity import validate_explicit_source_continuity
from cutroom.story_budget import StoryPlanningError


def brief(instruction="Choose one continuous source passage."):
    return {"goal": "short", "target_duration": 60, "instruction": instruction}


def assert_conflict(ranges, duration=100):
    with pytest.raises(StoryPlanningError) as caught:
        validate_explicit_source_continuity(brief(), ranges, duration)
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "explicit_source_continuity_conflict"
    assert diagnostic["outcome"] == "constraint_conflict"
    assert diagnostic["applied_to_timeline"] is False
    assert diagnostic["verification_scope"] == "proposed_director_draft"
    assert diagnostic["mechanical_only"] is True
    assert "existing edit was kept" in str(caught.value)
    return diagnostic


@pytest.mark.parametrize("ranges", [
    [{"start": 12, "end": 72}],
    [{"start": 12, "end": 30}, {"start": 30, "end": 72}],
    [{"start": 0.0, "end": 0.25}, {"start": 0.25, "end": 1.5}, {"start": 1.5, "end": 100}],
    [{"start": -0.0, "end": 100.0}],
])
def test_contiguous_source_selection_accepts_outer_trims_and_abutting_splits_without_mutation(ranges):
    request = brief()
    before_ranges, before_request = copy.deepcopy(ranges), copy.deepcopy(request)

    proof = validate_explicit_source_continuity(request, ranges, 100)

    assert proof["status"] == "fulfilled" and proof["source_continuity_verified"] is True
    assert proof["verification_scope"] == "proposed_director_draft" and proof["mechanical_only"] is True
    assert proof["semantic_coherence_verified"] is False and proof["final_export_verified"] is False
    basis = proof["verification_basis"]
    assert basis["kind"] == "ordered_contiguous_source_time_ranges"
    assert basis["checked_range_count"] == len(ranges)
    assert basis["source_start"] == ranges[0]["start"]
    assert basis["source_end"] == ranges[-1]["end"]
    assert basis["source_duration"] == 100
    assert basis["outer_trims_allowed"] is True and basis["adjacency"] == "exact"
    assert ranges == before_ranges and request == before_request


@pytest.mark.parametrize("instruction", [
    "Choose one continuous source passage.",
    "Keep the selected source passage without internal cuts.",
    "Do not cut inside the selected source footage.",
    "בחר קטע מקור אחד רציף.",
])
def test_explicit_continuity_directive_rejects_removed_pause_even_when_source_beats_are_consecutive(instruction):
    ranges = [{"start": 10, "end": 20}, {"start": 21, "end": 30}]
    with pytest.raises(StoryPlanningError) as caught:
        validate_explicit_source_continuity(brief(instruction), ranges, 100)
    assert caught.value.diagnostic["reason"] == "explicit_source_continuity_conflict"


@pytest.mark.parametrize("instruction", [
    "Make one video.",
    "Make one Short.",
    "Deliver a single output video.",
    "Choose one coherent self-contained passage.",
    "Choose one passage from the conversation.",
    "Preserve complete utterances and the original meaning.",
    "",
])
def test_output_or_semantic_unit_count_does_not_require_contiguous_source_or_even_validate_ranges(instruction):
    request = brief(instruction)
    request["style_profile"] = {"selection_policy": {"max_moments": 1}}

    proof = validate_explicit_source_continuity(request, None, object())

    assert proof["status"] == "not_requested"
    assert proof["source_continuity_verified"] is False
    assert proof["semantic_coherence_verified"] is False and proof["final_export_verified"] is False
    assert "verification_basis" not in proof


@pytest.mark.parametrize(("ranges", "duration"), [
    ([{"start": 10, "end": 20}, {"start": 20.001, "end": 30}], 100),
    ([{"start": 10, "end": 20}, {"start": 20.01, "end": 30}], 100),
    ([{"start": 10, "end": 20}, {"start": 19.999, "end": 30}], 100),
    ([{"start": 20, "end": 30}, {"start": 10, "end": 20}], 100),
    ([{"start": 10, "end": 20}, {"start": 10, "end": 20}], 100),
    ([{"start": 10, "end": 20}, {"start": 30, "end": 40}, {"start": 20, "end": 30}], 100),
    ([{"start": 999990, "end": 1000000}, {"start": 1000000.001, "end": 1000010}], 1000100),
    ([{"start": 2**53 - 10, "end": 2**53}, {"start": 2**53 + 1, "end": 2**53 + 10}], 2**53 + 100),
])
def test_no_gap_overlap_repetition_or_reversal_is_hidden_by_normalization_or_relative_tolerance(ranges, duration):
    before = copy.deepcopy(ranges)
    assert_conflict(ranges, duration)
    assert ranges == before


def test_noncanonical_float_endpoints_are_not_rounded_into_an_exact_continuity_claim():
    ranges = [{"start": 0, "end": 0.1 + 0.2}, {"start": 0.3, "end": 1}]
    assert ranges[0]["end"] != ranges[1]["start"]
    assert_conflict(ranges)


@pytest.mark.parametrize("ranges", [
    None, {}, (), "0-10", [], [None], [[0, 1]], [{}], [{"start": 0}], [{"end": 1}],
])
def test_active_continuity_rejects_empty_or_malformed_range_shapes(ranges):
    assert_conflict(ranges)


@pytest.mark.parametrize(("start", "end"), [
    (True, 10), (0, True), (False, 10), (0, False),
    ("0", 10), (0, "10"), (None, 10), (0, None),
    (0j, 10), (0, 10 + 0j),
    (math.nan, 10), (0, math.nan),
    (math.inf, 10), (-math.inf, 10), (0, math.inf), (0, -math.inf),
    (-0.001, 10), (0, 100.001), (10, 10), (11, 10),
    (10**400, 10), (0, 10**400),
])
def test_active_continuity_rejects_non_real_nonfinite_boolean_or_out_of_bounds_coordinates(start, end):
    assert_conflict([{"start": start, "end": end}])


@pytest.mark.parametrize("duration", [None, True, False, "100", {}, 0, -1, math.nan, math.inf, -math.inf, 10**400])
def test_active_continuity_requires_a_finite_positive_real_source_duration(duration):
    diagnostic = assert_conflict([{"start": 0, "end": 1}], duration)
    assert diagnostic["violation"] == "invalid_source_duration"


def test_proof_is_detached_and_contains_no_unchecked_range_metadata_or_semantic_claim():
    ranges = [{"start": 10, "end": 70, "path": "private-path-sentinel",
               "caption_origin": {"text": "private-speech-sentinel"}}]
    proof = validate_explicit_source_continuity(brief(), ranges, 100)
    encoded = json.dumps(proof)
    assert "private-path-sentinel" not in encoded and "private-speech-sentinel" not in encoded
    proof["verification_basis"]["source_start"] = 999
    assert ranges[0]["start"] == 10
    repeated = validate_explicit_source_continuity(brief(), ranges, 100)
    assert repeated["verification_basis"]["source_start"] == 10
    assert repeated["semantic_coherence_verified"] is False and repeated["final_export_verified"] is False


def test_failure_diagnostic_does_not_copy_private_or_arbitrary_input_values():
    diagnostic = assert_conflict([{"start": {"path": "private-path-sentinel"}, "end": 10}])
    assert "private-path-sentinel" not in json.dumps(diagnostic)
    assert diagnostic["range_index"] == 0
