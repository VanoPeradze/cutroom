"""Actual product coverage is tied to normalized plan, brief and source."""
import copy

from cutroom import intelligence as story
from cutroom.cache_keys import stable_fingerprint
from cutroom.passage_binding import presented_options
from tests.native_shortlist_fixture import capture_native_shortlist


def test_product_coverage_cannot_be_claimed_from_raw_plan_helper():
    actual = capture_native_shortlist()
    options = actual["enumerated"]
    assert options["receipt"]["numeric_option_count"] > 64
    # This longer synthetic source exceeds the twenty-unit ordered-search
    # scope. Consecutive enumeration has its own 128-option bound; do not
    # import a 64-option claim from another source/configuration.
    from cutroom.story_passage_options import MAX_OPTIONS
    assert options["receipt"]["ordered_noncontiguous_enabled"] is False
    assert 64 < len(options["options"]) <= MAX_OPTIONS
    assert len(actual["presented"]) == 1
    assert actual["assessment_receipt"]["screening_shortlist_count"] == 8
    assert all(not option["semantic_fit_verified"] for option in options["options"])
    expected = presented_options(options["options"], [row["id"] for row in actual["candidates"]])
    assert [row["candidate_id"] for row in actual["assessment_receipt"]["screening_shortlist"]] == [row["id"] for row in expected]
    assert [row["id"] for row in actual["presented"]] == [expected[0]["id"]]
    assert "source-quality-retrieval" in options["receipt"]["policy_version"]
    assert "No other candidate text is included" in actual["precision_payload"]["messages"][0]["content"]
    assert not actual["plan"]["slots"][0]["required_context_chapter_ids"]
    raw = actual["raw_understanding_replies"]["03_plan"]
    assert stable_fingerprint("plan", actual["plan"]) != stable_fingerprint("plan", raw)
    # A single output is not an explicit continuity requirement.
    from cutroom.instruction_contract import explicit_source_continuity_requested
    assert not explicit_source_continuity_requested(actual["brief"])
    assert "role_requirements" in actual["plan"]
    assert actual["model_calls"] == 0


def test_context_constrained_helper_pool_is_distinct_from_actual_product_pool():
    actual = capture_native_shortlist()
    assert len(actual["chapters"]) >= 2
    raw = copy.deepcopy(actual["raw_understanding_replies"]["03_plan"])
    context_ids = [chapter["id"] for chapter in actual["chapters"][:2]]
    raw["slots"][0]["required_context_chapter_ids"] = context_ids
    alternate = story._passage_options(actual["candidates"], actual["rows"], actual["chapters"], raw, actual["brief"])
    assert raw["slots"][0]["required_context_chapter_ids"] != actual["plan"]["slots"][0]["required_context_chapter_ids"]
    assert stable_fingerprint("plan", raw) != stable_fingerprint("plan", actual["plan"])
    assert alternate["receipt"]["numeric_option_count"] != actual["enumerated"]["receipt"]["numeric_option_count"]
    assert all(not row["semantic_fit_verified"] for row in alternate["options"])
    # This proves a changed input domain, not entitlement to any shortlist rank.
    assert actual["model_calls"] == 0
