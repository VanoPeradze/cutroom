from __future__ import annotations

import copy
import json
import socket
from pathlib import Path

import pytest

from cutroom import intelligence
from cutroom.instruction_contract import (
    MAX_INSTRUCTION_CHARACTERS, MAX_REQUIREMENT_ROWS, assert_instruction_contract,
    build_instruction_contract, evaluate_instruction_contract,
)
from cutroom.story_budget import StoryBudgetError


@pytest.fixture(autouse=True)
def no_model_or_network(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Instruction contract tests must not invoke model or network transport.")
    monkeypatch.setattr(intelligence, "open_ollama", forbidden)
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def brief(instruction, **patch):
    return {"goal": "short", "duration_mode": "target", "target_duration": 60,
            "instruction": instruction, **patch}


def source():
    return [{"id": "s1", "start": 0, "end": 4, "text": "Participation is not required."},
            {"id": "s2", "start": 8, "end": 12, "text": "The effect is cosmetic only."}]


@pytest.mark.parametrize("instruction", [
    "Make a 30-second Short about apples; do not include oranges.",
    "\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 30 \u05e9\u05e0\u05d9\u05d5\u05ea; \u05d0\u05dc \u05ea\u05db\u05dc\u05d5\u05dc \u05ea\u05e4\u05d5\u05d6\u05d9\u05dd.",
])
def test_explicit_duration_conflict_blocks_without_changing_request(instruction):
    request = brief(instruction)
    before = copy.deepcopy(request)
    with pytest.raises(StoryBudgetError) as caught:
        assert_instruction_contract(request)
    diagnostic = caught.value.diagnostic
    assert diagnostic["outcome"] == "constraint_conflict"
    assert diagnostic["reason"] == "instruction_duration_conflict"
    assert diagnostic["applied_to_timeline"] is False
    contract = diagnostic["instruction_contract"]
    assert contract["instruction"] == instruction
    assert contract["requirements"][0]["status"] == "not_fulfilled"
    assert contract["requirements"][1]["status"] == "unverified"
    assert request == before


@pytest.mark.parametrize("instruction", [
    "Do not make a 30-second Short.",
    "The speaker says 30 seconds; preserve that qualification.",
    'Discuss the phrase "make it 30 seconds".',
    "Make a 30-second Short if possible.",
    "\u05d0\u05dc \u05ea\u05e2\u05e9\u05d4 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 30 \u05e9\u05e0\u05d9\u05d5\u05ea.",
    "\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 30 \u05e9\u05e0\u05d9\u05d5\u05ea \u05d0\u05dd \u05d0\u05e4\u05e9\u05e8.",
])
def test_numbers_negated_or_quoted_or_qualified_are_not_proven_conflicts(instruction):
    contract = assert_instruction_contract(brief(instruction))
    assert contract["issues"] == []
    assert contract["verification_status"] == "unverified"
    assert contract["instruction"] == instruction


def test_shorter_explicit_duration_is_compatible_with_a_maximum():
    contract = assert_instruction_contract(brief("Make a 30-second Short.", duration_mode="max"))
    assert contract["requirements"][0]["recognized_controls"][0]["requested_seconds"] == 30
    assert contract["issues"] == []


@pytest.mark.parametrize("instruction", [
    "Add background music.",
    "Generate new footage.",
    "Upload it to YouTube.",
    "\u05d4\u05d5\u05e1\u05e3 \u05de\u05d5\u05d6\u05d9\u05e7\u05d4.",
])
def test_explicit_unsupported_mandatory_actions_block(instruction):
    with pytest.raises(StoryBudgetError) as caught:
        assert_instruction_contract(brief(instruction))
    assert caught.value.diagnostic["reason"] == "unsupported_instruction_action"


@pytest.mark.parametrize("instruction", [
    "Don't add music.", "Do not generate new footage.", "Do not upload it to YouTube.",
    "Add music if possible.", 'Discuss "add background music".',
    "\u05d0\u05dc \u05ea\u05d5\u05e1\u05d9\u05e3 \u05de\u05d5\u05d6\u05d9\u05e7\u05d4.",
])
def test_negated_quoted_and_optional_actions_do_not_trigger_unsupported_action(instruction):
    contract = assert_instruction_contract(brief(instruction))
    assert not contract["issues"]
    assert contract["verification_status"] == "unverified"


@pytest.mark.parametrize("instruction", [
    "Make a 30-second Short if the source allows it.",
    "Make a 30-second Short or a 60-second Short.",
    "Make it 30 seconds longer.",
    "Make it 90 seconds at most.",
    "Make it 30 seconds minimum.",
    "Add background music only if I provide a track.",
    "Start with the ending only if it is already first in the source.",
    "Do not do any of the following:\nAdd background music;\nUpload it to YouTube.",
    "If possible:\nMake a 30-second Short.",
    'Preserve this dialogue: "\nAdd background music.\nUpload it to YouTube.\n"',
    "Preserve this dialogue: '\nAdd background music.\nUpload it to YouTube.\n'",
    "\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 30 \u05e9\u05e0\u05d9\u05d5\u05ea,\u05d0\u05dd \u05d4\u05de\u05e7\u05d5\u05e8 \u05de\u05d0\u05e4\u05e9\u05e8.",
    "\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 30 \u05e9\u05e0\u05d9\u05d5\u05ea \u05dc\u05e4\u05d7\u05d5\u05ea.",
    "\u05e6\u05d5\u05e8 \u05e1\u05e8\u05d8\u05d5\u05df \u05e9\u05dc 90 \u05e9\u05e0\u05d9\u05d5\u05ea \u05dc\u05db\u05dc \u05d4\u05d9\u05d5\u05ea\u05e8.",
])
def test_unresolved_conditional_alternative_or_shared_scope_stays_unverified(instruction):
    contract = assert_instruction_contract(brief(instruction))
    assert contract["issues"] == []
    assert contract["verification_status"] == "unverified"
    assert contract["instruction"] == instruction


@pytest.mark.parametrize("instruction", [
    "Open with the result.", "Preserve the result and its qualification.",
    "Do not start with the ending.",
    "\u05e4\u05ea\u05d7 \u05e2\u05dd \u05d4\u05ea\u05d5\u05e6\u05d0\u05d4.",
])
def test_result_first_alone_does_not_prove_a_source_order_conflict(instruction):
    assert assert_instruction_contract(brief(instruction))["issues"] == []


@pytest.mark.parametrize("goal", ["short", "podcast", "youtube", "clean"])
@pytest.mark.parametrize("instruction", [
    "Start with the ending.", "Move the last segment before the first segment.",
    "\u05e4\u05ea\u05d7 \u05e2\u05dd \u05d4\u05e1\u05d5\u05e3.",
])
def test_explicit_last_source_first_conflicts_with_enforced_chronology(instruction, goal):
    with pytest.raises(StoryBudgetError) as caught:
        assert_instruction_contract(brief(instruction, goal=goal))
    assert caught.value.diagnostic["reason"] == "instruction_source_order_conflict"


@pytest.mark.parametrize("instruction", [
    'Focus on "the effect is cosmetic"; exclude participation; keep the negation and qualification.',
    '\u05d4\u05ea\u05de\u05e7\u05d3 \u05d1\u05e0\u05d5\u05e9\u05d0 "cosmetic"; \u05d0\u05dc \u05ea\u05db\u05dc\u05d5\u05dc participation; \u05e9\u05de\u05d5\u05e8 \u05e2\u05dc \u05d4\u05e1\u05ea\u05d9\u05d9\u05d2\u05d5\u05ea.',
])
def test_lexical_candidates_and_story_role_approval_never_prove_custom_semantics(instruction):
    contract = assert_instruction_contract(brief(instruction))
    original = copy.deepcopy(contract)
    report = evaluate_instruction_contract(contract, source(), {"keep_ids": ["s1", "s2"]}, semantic_verified=True)
    assert report["story_semantics_verified"] is True
    assert report["verification_status"] == "unverified"
    assert all(row["status"] == "unverified" and row["source_evidence"] == [] for row in report["requirements"])
    candidate = report["requirements"][0]["candidate_evidence"][0]
    assert candidate["basis"] == "lexical_candidate_not_semantic_proof"
    assert candidate["text"] == "The effect is cosmetic only."
    assert contract == original
    for requirement in report["requirements"]:
        assert instruction[requirement["instruction_start"]:requirement["instruction_end"]] == requirement["text"]


@pytest.mark.parametrize("instruction", [
    "Only use speaker Maria; include the absent moon landing.",
    "\u05e8\u05e7 \u05d4\u05d3\u05d5\u05d1\u05e8 Maria; \u05db\u05dc\u05d5\u05dc \u05d0\u05ea \u05d4\u05e0\u05d7\u05d9\u05ea\u05d4 \u05e2\u05dc \u05d4\u05d9\u05e8\u05d7.",
])
def test_unknown_speaker_and_absent_content_are_unverified(instruction):
    report = evaluate_instruction_contract(assert_instruction_contract(brief(instruction)), source(), {"keep_ids": ["s1"]})
    assert report["verification_status"] == "unverified"
    assert "Speaker identity is unavailable" in report["requirements"][0]["reason"]
    assert all(row["source_evidence"] == [] for row in report["requirements"])


def test_fulfilled_mechanical_requirements_need_final_timeline_evidence():
    contract = assert_instruction_contract(brief("Make a 30-second Short; preserve chronological order.", target_duration=30))
    decision = {"keep_ids": ["s1", "s2"]}
    initial = evaluate_instruction_contract(contract, source(), decision, semantic_verified=True)
    assert initial["verification_status"] == "unverified"
    final = evaluate_instruction_contract(contract, source(), decision, output_duration=30,
                                          source_ranges=[{"start": 0, "end": 4}, {"start": 8, "end": 34}])
    assert final["verification_status"] == "fulfilled"
    assert all(row["source_evidence"] and row["verification_basis"] for row in final["requirements"])
    bad = evaluate_instruction_contract(contract, source(), decision, output_duration=28,
                                        source_ranges=[{"start": 8, "end": 32}, {"start": 0, "end": 4}])
    assert [row["status"] for row in bad["requirements"]] == ["not_fulfilled", "not_fulfilled"]


def test_overlapping_passages_cannot_be_verified_as_chronological():
    contract = assert_instruction_contract(brief("Preserve chronological order."))
    report = evaluate_instruction_contract(contract, source(), {}, source_ranges=[{"start": 0, "end": 10}, {"start": 5, "end": 8}])
    assert report["requirements"][0]["status"] == "not_fulfilled"


def test_inconsistent_final_duration_metadata_cannot_fulfill_a_duration_request():
    contract = assert_instruction_contract(brief("Make a 60-second Short."))
    report = evaluate_instruction_contract(contract, source(), {}, output_duration=60, source_ranges=[{"start": 0, "end": 4}])
    assert report["requirements"][0]["status"] == "unverified"


def test_instruction_limit_is_exact_and_does_not_truncate():
    instruction = "x" * MAX_INSTRUCTION_CHARACTERS
    assert assert_instruction_contract(brief(instruction))["instruction"] == instruction
    with pytest.raises(StoryBudgetError) as caught:
        assert_instruction_contract(brief(instruction + "x"))
    assert caught.value.diagnostic["reason"] == "instruction_too_long"
    assert caught.value.diagnostic["instruction_contract"]["instruction"] == instruction + "x"


def test_changed_instruction_invalidates_story_cache_identity():
    first = brief("Preserve the qualification.")
    second = brief("Exclude the qualification.")
    assert intelligence.story_cache_fingerprint(source(), first, "fixture-model") != intelligence.story_cache_fingerprint(source(), second, "fixture-model")
    assert build_instruction_contract(first)["instruction_fingerprint"] != build_instruction_contract(second)["instruction_fingerprint"]


def test_deterministic_cleanup_cannot_report_custom_semantic_compliance(monkeypatch):
    class Settings:
        ai = {"enabled": False, "performance_mode": "balanced", "editor_model": "fixture-model"}
    monkeypatch.setattr(intelligence, "_ollama_chat", lambda *_args, **_kwargs: None)
    editorial, engine = intelligence.plan_edit(source(), Settings(), brief("Exclude participation.", goal="clean"))
    assert engine == "deterministic"
    assert editorial["instruction_contract"]["verification_status"] == "unverified"
    assert editorial["decision"]["instruction_contract"] == editorial["instruction_contract"]
    assert editorial["instruction_contract"]["story_semantics_verified"] is False
    assert editorial["warnings"][0]["type"] == "ai_disabled"


def test_plan_edit_conflict_preflights_before_model_status(monkeypatch):
    monkeypatch.setattr(intelligence, "story_ai_status", lambda *_args: pytest.fail("No model preflight should run."))
    with pytest.raises(StoryBudgetError, match="30s"):
        intelligence.plan_edit(source(), None, brief("Make a 30-second Short."))


def test_hebrew_context_overflow_preserves_full_instruction():
    instruction = "\u05d0\u05dc \u05ea\u05e1\u05d9\u05e8 \u05d4\u05e1\u05ea\u05d9\u05d9\u05d2\u05d5\u05ea. " * 350
    assert len(instruction) <= MAX_INSTRUCTION_CHARACTERS
    payload = {"options": {"num_ctx": 8192, "num_predict": 2400},
               "messages": [{"role": "user", "content": json.dumps({"brief": brief(instruction)}, ensure_ascii=False)}]}
    with pytest.raises(intelligence.StoryPlanningError, match="context budget"):
        intelligence._fit_story_request_context(payload, "lite")
    assert json.loads(payload["messages"][0]["content"])["brief"]["instruction"] == instruction


def test_many_clauses_are_bounded_with_an_exact_unverified_remainder():
    instruction = ";\n".join(f"Preserve topic {index}." for index in range(200))
    contract = assert_instruction_contract(brief(instruction))
    assert len(contract["requirements"]) == MAX_REQUIREMENT_ROWS
    remainder = contract["requirements"][-1]
    assert remainder["kind"] == "unparsed_remainder" and remainder["status"] == "unverified"
    assert remainder["text"] == instruction[remainder["instruction_start"]:]
    assert "topic 199" in remainder["text"]
    assert contract["instruction"] == instruction


def test_proof_size_is_bounded_independently_of_recording_length():
    contract = assert_instruction_contract(brief('Make a 60-second Short; preserve chronological order; keep "qualified".'))
    segments = [{"id": f"s{i}", "start": i * 2, "end": i * 2 + 1,
                 "text": "qualified " + ("not " * 1000)} for i in range(10000)]
    ranges = [{"start": row["start"], "end": row["end"]} for row in segments]
    report = evaluate_instruction_contract(contract, segments, {}, output_duration=10000, source_ranges=ranges)
    assert len(json.dumps(report, ensure_ascii=False)) < 20000
    assert all(len(row["source_evidence"]) <= 8 and len(row.get("candidate_evidence", [])) <= 8 for row in report["requirements"])
    assert report["requirements"][0]["source_evidence"][0]["text_omitted"] is True
    basis = report["requirements"][1]["verification_basis"]
    assert basis["checked_range_count"] == 10000 and len(basis["source_ranges_excerpt"]) == 8


@pytest.mark.parametrize("error,outcome", [
    (intelligence.StoryPlanningError("Malformed structured response."), "invalid_model_output"),
    (intelligence.StoryPlanningError("Story instructions exceed the context budget."), "technical_error"),
    (intelligence.StoryResponseLimitError("Output ended early."), "technical_error"),
    (intelligence.StoryAIUnavailableError("Model is not available."), "technical_error"),
])
def test_hierarchy_failure_keeps_category_and_exact_request(monkeypatch, error, outcome):
    instruction = "Keep the qualification; do not invent a result."
    def fail(*_args):
        raise error
    monkeypatch.setattr(intelligence, "_ready_story_model_status", fail)
    with pytest.raises(type(error)) as caught:
        intelligence.hierarchical_story_edit([], source(), None, brief(instruction))
    diagnostic = caught.value.diagnostic
    assert diagnostic["outcome"] == outcome
    assert diagnostic["applied_to_timeline"] is False
    assert diagnostic["instruction_contract"]["instruction"] == instruction
    assert diagnostic["instruction_contract"]["verification_status"] == "unverified"


@pytest.mark.parametrize("reason,outcome", [
    ("extractive_source_exceeds_target", "constraint_conflict"),
    ("extractive_required_context_missing", "constraint_conflict"),
    ("allowed_source_below_target_minimum", "constraint_conflict"),
    ("planner_no_fit", "editorial_no_fit"),
])
def test_existing_budget_refusals_without_explicit_outcome_keep_their_category(monkeypatch, reason, outcome):
    error = StoryBudgetError("Synthetic refusal.", {"reason": reason})
    def fail(*_args):
        raise error
    monkeypatch.setattr(intelligence, "_ready_story_model_status", fail)
    with pytest.raises(StoryBudgetError) as caught:
        intelligence.hierarchical_story_edit([], source(), None, brief("Keep context."))
    assert caught.value.diagnostic["outcome"] == outcome
    assert caught.value.diagnostic["reason"] == reason


def test_hebrew_regex_source_is_valid_utf8_not_console_question_marks():
    path = Path(__file__).parents[1] / "cutroom" / "instruction_contract.py"
    text = path.read_text(encoding="utf-8")
    assert sum(0x590 <= ord(char) <= 0x5ff for char in text) > 100
    assert "\ufffd" not in text
