"""Explicit duration intervals through the real planner, without inference.

Mocked semantic judgments exercise transport contracts only; they do not prove
editorial quality, accurate speech recognition, or an encoded output.
"""
import copy
import json
import socket
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.instruction_contract import (
    assert_instruction_contract, build_instruction_contract,
    effective_duration_bounds, evaluate_instruction_contract,
)
from cutroom.story_budget import StoryBudgetError
from tests.test_story_candidate_product_path import source


@pytest.fixture(autouse=True)
def no_live_inference_or_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Duration-range regressions must not invoke inference or network transport.")
    monkeypatch.setattr(story, "open_ollama", forbidden)
    monkeypatch.setattr(story, "_call_ollama_story_pass", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def request(instruction="", **patch):
    return {"goal": "short", "target_duration": 60., "duration_mode": "target",
            "instruction": instruction, **patch}


def duration_requirement(report):
    rows = [row for row in report["requirements"] if row["kind"] == "duration_range"]
    assert len(rows) == 1
    return rows[0]


@pytest.mark.parametrize("instruction", [
    "Aim for 45–60 seconds.",
    "כוון ל־45–60 שניות.",
    "Aim for 45-60 seconds.",
    "כוון ל-45-60 שניות.",
    "Aim for 0.75–1 minutes.",
])
def test_explicit_range_replaces_derived_tolerance_and_preserves_original_instruction(instruction):
    brief = request(instruction)
    original = copy.deepcopy(brief)
    contract = assert_instruction_contract(brief)
    bounds = effective_duration_bounds(brief)
    assert bounds["minimum_seconds"] == 45.
    assert bounds["maximum_seconds"] == 60.
    assert bounds["origin"] == "explicit_user_range" and bounds["explicit"] is True
    control, = duration_requirement(contract)["recognized_controls"]
    assert control["mandatory"] is True
    assert control["origin"] == "explicit_user_instruction"
    assert control["text"] in instruction
    assert contract["instruction"] == instruction and brief == original


@pytest.mark.parametrize("instruction", ["Make exactly 60 seconds.", "צור סרטון של 60 שניות."])
def test_explicit_exact_duration_retains_equal_bounds(instruction):
    bounds = effective_duration_bounds(request(instruction), source_duration=120.)
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == (60., 60.)
    assert bounds["origin"] == "explicit_user_exact" and bounds["explicit"] is True


@pytest.mark.parametrize("instruction", ["Make exactly 45 seconds.", "צור סרטון של 45 שניות."])
@pytest.mark.parametrize("mode,target", [("target", 60.), ("max", 40.)])
def test_conflicting_exact_instruction_and_ui_remain_blocking(instruction, mode, target):
    brief = request(instruction, duration_mode=mode, target_duration=target)
    before = copy.deepcopy(brief)
    with pytest.raises(StoryBudgetError) as error:
        effective_duration_bounds(brief)
    assert error.value.diagnostic["reason"] == "instruction_duration_conflict"
    assert error.value.diagnostic["applied_to_timeline"] is False
    assert brief == before


@pytest.mark.parametrize("source_duration", [None, 48., 120.])
def test_plain_target_preserves_existing_short_source_tolerance(source_duration):
    bounds = effective_duration_bounds(request(), source_duration)
    expected_minimum = .9 * min(60., source_duration) if source_duration is not None else 54.
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == (expected_minimum, 60.)
    assert bounds["origin"] == "derived_target" and bounds["explicit"] is False


@pytest.mark.parametrize("source_duration", [None, 30., 120.])
def test_configured_maximum_does_not_invent_a_minimum(source_duration):
    bounds = effective_duration_bounds(request(duration_mode="max"), source_duration)
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == (0., 60.)
    assert bounds["origin"] == "configured_max" and bounds["explicit"] is False


@pytest.mark.parametrize("instruction", ["Aim for 45–60 seconds.", "כוון ל־45–60 שניות."])
@pytest.mark.parametrize("maximum,expected", [(50., (45., 50.)), (75., (45., 60.))])
def test_ui_maximum_intersects_explicit_interval(instruction, maximum, expected):
    bounds = effective_duration_bounds(request(instruction, duration_mode="max", target_duration=maximum))
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == expected
    assert bounds["origin"] == "explicit_user_range"


@pytest.mark.parametrize("instruction", ["Aim for 45–60 seconds.", "כוון ל־45–60 שניות."])
def test_disjoint_ui_maximum_and_interval_fail_without_resolving_precedence(instruction):
    with pytest.raises(StoryBudgetError) as error:
        effective_duration_bounds(request(instruction, duration_mode="max", target_duration=40.))
    assert error.value.diagnostic["reason"] == "instruction_duration_range_conflict"
    assert error.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("instruction", [
    '"Aim for 45–60 seconds."',
    '"כוון ל־45–60 שניות."',
    "Do not aim for 45–60 seconds.",
    "אל תכוון ל־45–60 שניות.",
    "Aim for 45–60 seconds if possible.",
    "כוון ל־45–60 שניות אם אפשר.",
    "Aim for 45–60 seconds or 90 seconds.",
    "כוון ל־45–60 שניות או 90 שניות.",
])
def test_quotes_negation_conditions_and_alternatives_do_not_become_hard_ranges(instruction):
    brief = request(instruction)
    contract = build_instruction_contract(brief)
    assert "duration_range" not in contract
    assert not any(control["mandatory"] for row in contract["requirements"]
                   for control in row["recognized_controls"] if control["kind"] == "duration_range")
    bounds = effective_duration_bounds(brief)
    assert bounds["origin"] == "derived_target" and bounds["explicit"] is False
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == (54., 60.)
    assert contract["instruction"] == instruction


@pytest.mark.parametrize("instruction", ["Aim for 45–60 seconds.", "כוון ל־45–60 שניות."])
@pytest.mark.parametrize("source_duration", [30., 44.9])
def test_short_source_never_shrinks_explicit_minimum(instruction, source_duration):
    bounds = effective_duration_bounds(request(instruction), source_duration)
    assert (bounds["minimum_seconds"], bounds["maximum_seconds"]) == (45., 60.)


@pytest.mark.parametrize("instruction", ["Aim for 60–45 seconds.", "כוון ל־60–45 שניות."])
def test_reversed_hard_interval_is_rejected(instruction):
    with pytest.raises(StoryBudgetError) as error:
        effective_duration_bounds(request(instruction))
    assert error.value.diagnostic["reason"] == "invalid_instruction_duration_range"


@pytest.mark.parametrize("instruction", ["Aim for 45–60 seconds.", "כוון ל־45–60 שניות."])
def test_range_fulfillment_requires_matching_assembled_timeline_geometry(instruction):
    segments = source()[:4]
    original = copy.deepcopy(segments)
    contract = assert_instruction_contract(request(instruction))
    decision = {"keep_ids": [row["id"] for row in segments], "remove_ids": []}
    for ranges in (None, [], [{"start": 0., "end": 36.}]):
        report = evaluate_instruction_contract(contract, segments, decision, semantic_verified=True,
                                               output_duration=48., source_ranges=ranges)
        assert duration_requirement(report)["status"] == "unverified"
    report = evaluate_instruction_contract(contract, segments, decision, semantic_verified=True,
                                           output_duration=48., source_ranges=[{"start": 0., "end": 48.}])
    row = duration_requirement(report)
    assert row["status"] == "fulfilled"
    assert row["verification_basis"] == {"kind": "assembled_timeline_duration", "seconds": 48.}
    assert [ref["segment_id"] for ref in row["source_evidence"]] == [s["id"] for s in segments]
    assert segments == original and duration_requirement(contract)["status"] == "unverified"


@pytest.mark.parametrize("actual", [44., 61.])
def test_final_timeline_outside_explicit_range_is_not_fulfilled(actual):
    segments = source()
    decision = {"keep_ids": [row["id"] for row in segments], "remove_ids": []}
    report = evaluate_instruction_contract(assert_instruction_contract(request("Aim for 45–60 seconds.")),
        segments, decision, semantic_verified=True, output_duration=actual,
        source_ranges=[{"start": 0., "end": actual}])
    assert duration_requirement(report)["status"] == "not_fulfilled"
    assert report["verification_status"] == "not_fulfilled"


def install_product_controls(monkeypatch, segments, observed):
    """Mock only model status/understanding replies; retain real source gates."""
    expected_ids = [row["id"] for row in segments]

    def summaries(_settings, chapters, *_args):
        assert [sid for chapter in chapters for beat in chapter["beats"] for sid in beat["segment_ids"]] == expected_ids
        return [{"id": chapter["id"], "summary": "Synthetic diagnostic only", "key_points": [], "depends_on": []}
                for chapter in chapters]

    def plan(_settings, _summaries, _outline, _brief, _model, _progress, _cancel, _segments, chapters):
        return {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE,
            "chapter_ids": [row["id"] for row in chapters], "required_context_chapter_ids": [], "desired_seconds": 60.}]}

    def model(_settings, payload, *_args):
        data = json.loads(payload["messages"][1]["content"])
        observed.append(copy.deepcopy(data))
        if "passage_candidates" in data:
            option, = [row for row in data["passage_candidates"] if row["segment_ids"] == expected_ids]
            assert option["raw_playable_seconds"] == 48.
            assert data["duration_bounds"]["minimum_seconds"] == 45.
            assert data["duration_bounds"]["maximum_seconds"] == 60.
            from tests.passage_contract_fixture import nominate
            return nominate(option,data)
        if "selected" in data:
            assert len(data["selected"]) == 4
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [],
                "summary": "Synthetic source-continuity control", "style_notes": [], "action_evidence": []}
        assert "fixed_passage_candidate" in data
        option = data["fixed_passage_candidate"]
        assert option["id"] == observed[0]["passage_candidates"][0]["id"]
        assert option["segment_ids"] == expected_ids
        assert option["actual_playback"]["playback_seconds"] == 48.
        assert option["actual_playback"]["actual_source_omission_count"] == 0
        assert [row["id"] for row in data["selected_source_utterances"]] == expected_ids
        return {"verdict": "fit", "candidate_id": option["id"], "refusal_category": "none",
            "semantic_reason": "Independent synthetic review of the same unchanged source",
            "cited_segment_ids": [expected_ids[0], expected_ids[-1]], "critic_action_decisions": []}

    monkeypatch.setattr(story, "_ready_story_model_status", lambda *_a: {"selected_model": "fixture", "ready": True})
    monkeypatch.setattr(story, "_summarize_story_chapters", summaries)
    monkeypatch.setattr(story, "_build_global_outline", lambda *_a: {})
    monkeypatch.setattr(story, "_build_story_plan", plan)
    monkeypatch.setattr(story, "_call_ollama_story_pass", model)


@pytest.mark.parametrize("language", ["en", "he"])
def test_actual_plan_edit_enumerates_selects_and_final_verifies_forty_eight_second_range(monkeypatch, language):
    segments = source(language)[:4]
    original = copy.deepcopy(segments)
    expected_ids = [row["id"] for row in segments]
    instruction = ("Choose one coherent self-contained passage. Aim for 45–60 seconds." if language == "en" else
                   "בחר קטע אחד ברור ועצמאי. כוון ל־45–60 שניות.")
    brief = request(instruction, language=language, allow_extractive_rough_cut=False)
    calls = []
    install_product_controls(monkeypatch, segments, calls)
    editorial, engine = story.plan_edit(segments, SimpleNamespace(ai={"performance_mode": "balanced"}), brief)
    assert engine == "ollama_hierarchical_story" and segments == original
    assert len(calls) == 3
    assert calls[0]["brief"]["instruction"] == instruction
    assert all(row["text"] == original[index]["text"] for index, row in enumerate(editorial["segments"]))
    decision = editorial["decision"]
    assert decision["keep_ids"] == expected_ids and decision["remove_ids"] == []
    assert decision["story_beat_ids"] == [row["id"] for row in editorial["story_beats"]]
    assert sum(row["end"] - row["start"] for row in decision["story_ranges"]) == 48.
    selected = editorial["story_hierarchy"]["selection"]
    assert selected["semantic_mapping_verified"] is True
    assert selected["source_span_constraints"]["segment_ids"] == expected_ids
    assert selected["passage_option_selection"]["option"]["segment_ids"] == expected_ids
    report = evaluate_instruction_contract(assert_instruction_contract(brief), editorial["segments"], decision,
        semantic_verified=True, output_duration=48., source_ranges=decision["story_ranges"])
    assert duration_requirement(report)["status"] == "fulfilled"
    # The mechanical range proof does not silently approve the separate meaning request.
    assert any(row["status"] == "unverified" for row in report["requirements"] if row["kind"] != "duration_range")


@pytest.mark.parametrize("language", ["en", "he"])
def test_forty_eight_second_window_in_longer_source_needs_explicit_range(language):
    segments = story.enrich_segments(source(language), language)
    before = copy.deepcopy(segments)
    units = story.build_story_beats(segments, language, target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE,
                      "chapter_ids": [c["id"] for c in chapters],
                      "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    ordinary = request("Choose one coherent self-contained passage.")
    ranged = request("Choose one coherent self-contained passage. Aim for 45–60 seconds.")
    ids = [u["id"] for u in units[:4]]
    default = story._passage_options(units, segments, chapters, plan, ordinary)
    explicit = story._passage_options(units, segments, chapters, plan, ranged)
    assert not any(o["beat_ids"] == ids for o in default["options"])
    assert any(o["beat_ids"] == ids and o["raw_playable_seconds"] == 48. for o in explicit["options"])
    assert segments == before
