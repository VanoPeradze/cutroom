"""Critic evidence attribution is not a semantic or instruction-entailment oracle."""
from __future__ import annotations

import copy

import pytest

from cutroom.critic_evidence import validate_critic_actions
from cutroom.story_evidence import build_story_evidence_catalog


def fixture(language="en", kind="off_topic", action="remove"):
    texts = (["I missed the bus, not the train.", "The next day I left early and arrived on time.", "The forecast predicts rain."]
             if language == "en" else
             ["פספסתי את האוטובוס, לא את הרכבת.", "למחרת יצאתי מוקדם והגעתי בזמן.", "התחזית צופה גשם."])
    instruction = ("Choose one coherent account. Do not include the unrelated weather aside." if language == "en" else
                   "בחר קטע אחד ברור ועצמאי. אל תכלול את ההערה על מזג האוויר.")
    quote = ("Do not include the unrelated weather aside." if language == "en" else "אל תכלול את ההערה על מזג האוויר.")
    segments = [{"id": f"s{i+1}", "start": i*10., "end": (i+1)*10., "text": text,
                 "words": [{"word": text, "start": i*10., "end": (i+1)*10.}]} for i, text in enumerate(texts)]
    beats = [{"id": f"b{i+1}", "start": row["start"], "end": row["end"], "text": row["text"],
              "segment_ids": [row["id"]]} for i, row in enumerate(segments)]
    catalog = build_story_evidence_catalog(beats, segments)
    target = "b3" if kind in {"off_topic", "explicit_instruction"} else "b1"
    own = next(row["id"] for row in catalog if row["beat_id"] == target)
    other = next(row["id"] for row in catalog if row["beat_id"] == "b2")
    row = {"action": action, "beat_id": target, "defect_kind": kind,
           "source_evidence_ids": [own, other], "instruction_quote": quote if kind == "explicit_instruction" else "",
           "explanation": "A model interpretation requiring semantic review."}
    result = {"verdict": "revise", "add_beat_ids": [target] if action == "add" else [],
              "remove_beat_ids": [target] if action == "remove" else [], "issues": [], "summary": "Unverified review",
              "action_evidence": [row]}
    brief = {"instruction": instruction, "style_profile": {"guidance": "Create a stronger hook and remove weak setup."}}
    return [result, catalog, beats, segments, brief, ["b1", "b2", "b3"]]


@pytest.mark.parametrize("language", ["en", "he"])
@pytest.mark.parametrize("kind", ["off_topic", "meaning_change", "missing_context", "incomplete_thought", "chronology_conflict", "explicit_instruction"])
def test_resolves_exact_quotes_and_complete_utterances_without_certifying_claim(language, kind):
    args = fixture(language, kind)
    original = copy.deepcopy(args)
    records = validate_critic_actions(*args)
    assert args == original
    assert len(records) == 1 and records[0]["interpretation_verified"] is False
    assert len(records[0]["source_fingerprint"]) == 64
    for quote in records[0]["source_evidence"]:
        assert quote == next(row for row in args[1] if row["id"] == quote["id"])
    for utterance in records[0]["source_utterances"]:
        assert utterance == next(row for row in args[3] if row["id"] == utterance["id"])
    if kind == "explicit_instruction":
        evidence = records[0]["instruction_evidence"]
        assert args[4]["instruction"][evidence["char_start"]:evidence["char_end"]] == evidence["quote"]
        assert evidence["scope"] == "verbatim_substring_only"
    records[0]["source_utterances"][0]["words"].clear()
    assert args == original


def test_context_addition_uses_same_evidence_contract():
    args = fixture(kind="missing_context", action="add")
    records = validate_critic_actions(*args)
    assert records[0]["action"] == "add" and records[0]["interpretation_verified"] is False


@pytest.mark.parametrize("kind", ["style", "hook", "repetition_only", "boring"])
def test_style_only_action_class_is_not_authorized(kind):
    args = fixture()
    args[0]["action_evidence"][0]["defect_kind"] = kind
    with pytest.raises(ValueError, match="not style alone"):
        validate_critic_actions(*args)


@pytest.mark.parametrize("fault", ["missing_evidence", "unknown_target", "unknown_reference", "translated_reference",
                                    "duplicate_reference", "duplicate_action", "duplicate_record", "extra_record",
                                    "missing_target_quote", "missing_relation_quote", "add_remove_conflict", "extra_field",
                                    "forged_catalog", "stale_transcript", "no_catalog", "duplicate_ownership"])
def test_invalid_actions_never_gain_attribution(fault):
    args = fixture()
    result, catalog, beats, segments, brief, selected = args
    row = result["action_evidence"][0]
    if fault == "missing_evidence": result.pop("action_evidence")
    elif fault == "unknown_target": result["remove_beat_ids"] = ["unknown"]; row["beat_id"] = "unknown"
    elif fault == "unknown_reference": row["source_evidence_ids"][0] = "b9:s9:f1"
    elif fault == "translated_reference": row["source_evidence_ids"][0] = "Translated quote [b3:s3:f1]"
    elif fault == "duplicate_reference": row["source_evidence_ids"].append(row["source_evidence_ids"][0])
    elif fault == "duplicate_action": result["remove_beat_ids"].append("b3")
    elif fault == "duplicate_record": result["action_evidence"].append(copy.deepcopy(row))
    elif fault == "extra_record": result["action_evidence"].append({**copy.deepcopy(row), "action": "add"})
    elif fault == "missing_target_quote": row["source_evidence_ids"] = [row["source_evidence_ids"][1]]
    elif fault == "missing_relation_quote": row["source_evidence_ids"] = row["source_evidence_ids"][:1]
    elif fault == "add_remove_conflict": result["add_beat_ids"] = ["b3"]
    elif fault == "extra_field": row["confidence"] = 1.
    elif fault == "forged_catalog": catalog[0]["text"] = "Invented source quote."
    elif fault == "stale_transcript": segments[0]["text"] = "Different ASR with the same IDs."
    elif fault == "no_catalog": args[1] = []
    elif fault == "duplicate_ownership": beats[1]["segment_ids"].append("s1")
    original = copy.deepcopy(args)
    with pytest.raises(ValueError):
        validate_critic_actions(*args)
    assert args == original


def test_relation_quote_must_belong_to_another_selected_beat():
    args = fixture()
    args[5] = ["b3"]
    with pytest.raises(ValueError, match="another selected"):
        validate_critic_actions(*args)


@pytest.mark.parametrize("fault", ["style_profile_quote", "translated_instruction", "nonempty_noninstruction", "empty_instruction"])
def test_only_verbatim_original_instruction_supplies_instruction_attribution(fault):
    args = fixture(kind="explicit_instruction")
    row = args[0]["action_evidence"][0]
    if fault == "style_profile_quote": row["instruction_quote"] = args[4]["style_profile"]["guidance"]
    elif fault == "translated_instruction": row["instruction_quote"] = "אל תכלול את מזג האוויר."
    elif fault == "nonempty_noninstruction": row["defect_kind"] = "meaning_change"
    else: row["instruction_quote"] = ""
    with pytest.raises(ValueError):
        validate_critic_actions(*args)


@pytest.mark.parametrize("instruction,quote", [
    ('The producer wrote "Remove weather"; discuss that sentence.', 'Remove weather'),
    ('אם אולי תרצה, שקול לשנות את האווירה.', 'שקול לשנות את האווירה'),
])
def test_quoted_or_unrecognized_instruction_is_attributed_not_certified_as_a_hard_requirement(instruction, quote):
    args = fixture(kind="explicit_instruction")
    args[4]["instruction"] = instruction
    args[0]["action_evidence"][0]["instruction_quote"] = quote
    record = validate_critic_actions(*args)[0]
    assert record["instruction_evidence"]["scope"] == "verbatim_substring_only"
    assert record["interpretation_verified"] is False
    assert "hard_constraint_verified" not in record


def test_complete_source_utterance_retains_negation_even_when_cited_fragment_does_not():
    args = fixture(kind="meaning_change")
    record = validate_critic_actions(*args)[0]
    utterance = next(row for row in record["source_utterances"] if row["id"] == "s1")
    assert utterance["text"] == "I missed the bus, not the train."


def test_correct_citation_does_not_validate_an_unsupported_model_translation():
    args = fixture(kind="meaning_change")
    args[0]["action_evidence"][0]["explanation"] = "The speaker said they went to bed, an unsupported interpretation."
    record = validate_critic_actions(*args)[0]
    assert record["interpretation_verified"] is False
    assert record["explanation"] == args[0]["action_evidence"][0]["explanation"]


def test_clean_legacy_pass_with_no_actions_needs_no_catalog_or_new_field():
    result = {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": ""}
    assert validate_critic_actions(result, [], [], [], {}, []) == []
    assert validate_critic_actions({**result, "action_evidence": []}, [], [], [], {}, []) == []


def test_no_action_review_cannot_carry_unrequested_action_evidence():
    args = fixture()
    args[0]["remove_beat_ids"] = []
    with pytest.raises(ValueError, match="not requested"):
        validate_critic_actions(*args)


def test_source_fingerprint_changes_with_word_timing_without_relabeling_source():
    args = fixture()
    original = validate_critic_actions(*args)[0]["source_fingerprint"]
    args[3][0]["words"][0]["start"] = .2
    changed = validate_critic_actions(*args)[0]["source_fingerprint"]
    assert original != changed
