"""Offline schema structure and response-contract checks; no grammar capability claim."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.critic_evidence import review_evidence_schema, validate_review_evidence
from cutroom.structured_schema import complete_object_union
from cutroom.visual_moments import ANSWER_SCHEMA
from tests.test_bound_passage_contract import selected
from tests.passage_contract_fixture import nominate


def matches(value, schema):
    """Small independent oracle for the schema keywords exercised in these cases.

    Deliberately not a general JSON Schema validator or a grammar converter.
    """
    supported = {"anyOf", "type", "const", "enum", "properties", "required", "additionalProperties",
                 "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength", "minimum", "maximum"}
    assert not set(schema) - supported, set(schema) - supported
    if "anyOf" in schema and not any(matches(value, branch) for branch in schema["anyOf"]): return False
    if "const" in schema and value != schema["const"]: return False
    if "enum" in schema and value not in schema["enum"]: return False
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    if "type" in schema and not isinstance(value, types[schema["type"]]): return False
    if isinstance(value, dict):
        props = schema.get("properties", {})
        if not set(schema.get("required", [])) <= set(value): return False
        if schema.get("additionalProperties") is False and set(value) - set(props): return False
        if any(not matches(item, props[name]) for name, item in value.items() if name in props): return False
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")): return False
        if schema.get("uniqueItems") and len({json.dumps(v, sort_keys=True) for v in value}) != len(value): return False
        if "items" in schema and any(not matches(item, schema["items"]) for item in value): return False
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")): return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")): return False
    return True


def audit(schema):
    if isinstance(schema, dict):
        if "anyOf" in schema:
            assert "properties" not in schema and "required" not in schema
            for branch in schema["anyOf"]:
                if "properties" in branch:
                    assert branch["type"] == "object" and branch["additionalProperties"] is False
                    assert set(branch.get("required", [])) <= set(branch["properties"])
                    assert "required" in branch or not branch["properties"]
        for child in schema.values(): audit(child)
    elif isinstance(schema, list):
        for child in schema: audit(child)


def contracts(language, monkeypatch):
    rows, units, chapters, plan, brief, selection, precision = selected(language, monkeypatch)
    # Correct real-language instruction text, independently of old synthetic fixtures.
    brief["instruction"] = ("Make one video. Aim for 45-60 seconds. Preserve the meaning." if language == "en" else
                            "צור סרטון אחד באורך 45–60 שניות. שמור על המשמעות.")
    # Instruction identity is part of the source option. Re-select with that instruction.
    def nominate_only(_settings, payload, *_):
        data = json.loads(payload["messages"][-1]["content"])
        return nominate(data["passage_candidates"][0], data)
    monkeypatch.setattr(story, "_call_ollama_story_pass", nominate_only)
    selection, units = story._select_passage_option(SimpleNamespace(ai={}), units, rows, chapters, plan, brief, "fixture", None)
    captured = []
    def critic(_settings, payload, *_):
        captured.append(payload)
        return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": "Fixture only",
                "style_notes": [], "action_evidence": [], "issue_evidence": []}
    monkeypatch.setattr(story, "_call_ollama_story_pass", critic)
    story._critic_story_selection(SimpleNamespace(ai={}), selection, units, {}, plan, brief, "fixture", segments=rows)
    option = selection["passage_option_selection"]["option"]
    data = {"brief": brief, "source_units": [{**{k: row[k] for k in ("id", "start", "end", "segment_ids")},
        "selected_in_proposal": row["id"] in option["beat_ids"],
        "segments": [item for item in rows if item["id"] in row["segment_ids"]]} for row in units]}
    final, option, proposal = story._fixed_passage_final_request({"messages": [{"role": "system", "content": "fixture"},
        {"role": "user", "content": json.dumps(data)}]}, selection, units, rows, chapters, plan, brief, [], None)
    return rows, option, brief, precision["format"], captured[0]["format"], final["format"], proposal


@pytest.mark.parametrize("language", ["he", "en"])
def test_all_three_emitted_fixed_contracts_have_complete_object_alternatives(language, monkeypatch):
    rows, option, brief, precision, critic, final, _ = contracts(language, monkeypatch)
    for schema in (precision, critic, final):
        audit(schema)
        assert set(schema) == {"anyOf"}
        required = set(schema["anyOf"][0]["required"])
        for branch in schema["anyOf"]:
            assert set(branch["required"]) == required == set(branch["properties"])
    audit(ANSWER_SCHEMA)
    audit(story.GLOBAL_OUTLINE_SCHEMA)


@pytest.mark.parametrize("language", ["he", "en"])
def test_valid_fit_and_no_fit_envelopes_preserve_final_acceptance_and_rejection(language, monkeypatch):
    rows, option, brief, _precision, critic, final, proposal = contracts(language, monkeypatch)
    base = {"candidate_id": option["id"], "semantic_reason": "Fixture only", "cited_segment_ids": [option["segment_ids"][0]],
            "critic_action_decisions": [], "rejection_evidence": []}
    fit = {**base, "verdict": "fit", "refusal_category": "none"}
    assert matches(fit, final)
    assert story._decode_fixed_passage_final(fit, option, proposal, [], rows)["verdict"] == "fit"
    proof = {"kind": "incomplete_thought", "source_segment_ids": [option["segment_ids"][0]],
             "missing_context_segment_ids": [], "join_id": None, "instruction_quote": ""}
    refusal = {**base, "verdict": "no_fit", "refusal_category": "semantic_rejection", "rejection_evidence": [proof]}
    assert matches(refusal, final)
    with pytest.raises(story.StoryBudgetError) as exc:
        story._decode_fixed_passage_final(refusal, option, proposal, [], rows)
    assert exc.value.diagnostic["reason"] == "fixed_candidate_semantic_rejection"
    uncertain = {**base, "verdict": "no_fit", "refusal_category": "uncertain"}
    assert matches(uncertain, final)
    with pytest.raises(story.StoryPlanningError) as exc:
        story._decode_fixed_passage_final(uncertain, option, proposal, [], rows)
    assert exc.value.diagnostic["outcome"] == "technical_error"
    clean = {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": "Fixture",
             "style_notes": [], "action_evidence": [], "issue_evidence": []}
    assert matches(clean, critic)
    assert matches({**clean, "verdict": "revise", "issues": ["Fixture incomplete thought"], "issue_evidence": [proof]}, critic)
    assert not matches({**clean, "verdict": "revise"}, critic)


@pytest.mark.parametrize("kind", ["missing_context", "meaning_change", "explicit_instruction", "join_context"])
@pytest.mark.parametrize("language", ["he", "en"])
def test_nested_evidence_alternatives_keep_bounds_types_and_discriminators(kind, language):
    instruction = "Do not invert the negation." if language == "en" else "אל תהפוך את השלילה."
    rows = [{"id": f"s{i}", "start": float(i), "end": float(i+1), "text": "Exact source"} for i in range(3)]
    joins = [{"id": "join1", "left_segment_id": "s0", "right_segment_id": "s2"}]
    schema = review_evidence_schema(rows, joins, selected_segment_ids=["s0", "s2"], instruction=instruction)
    audit(schema)
    record = {"kind": kind, "source_segment_ids": ["s0", "s2"] if kind == "join_context" else ["s0"],
              "missing_context_segment_ids": ["s1"] if kind == "missing_context" else [],
              "join_id": "join1" if kind == "join_context" else None,
              "instruction_quote": instruction if kind == "explicit_instruction" else ""}
    assert matches([record], schema)
    validate_review_evidence([record], rows, ["s0", "s2"], joins, instruction)
    for field in record:
        bad = dict(record); del bad[field]
        assert not matches([bad], schema)
    assert not matches([{**record, "instruction_quote": "invented source quotation"}], schema)
    assert not matches([{**record, "source_segment_ids": ["foreign"]}], schema)


def test_missing_four_field_recording_is_rejected_without_inventing_defaults(monkeypatch):
    from tests.native_shortlist_fixture import capture_native_shortlist
    actual = capture_native_shortlist()
    request = actual["precision_payload"]
    # Deliberately incomplete synthetic response: retain the exact two-field
    # defect without copying any private model receipt or inventing defaults.
    reply = {"candidate_id": actual["presented"][0]["id"], "reason_evidence": []}
    before = copy.deepcopy(reply)
    schema = request["format"]
    audit(schema)
    assert set(reply) == {"candidate_id", "reason_evidence"} and not matches(reply, schema)
    # Replay at the actual selector decoding boundary with the complete current schema.
    monkeypatch.setattr(story, "_call_ollama_story_pass", lambda *_: copy.deepcopy(reply))
    with pytest.raises(story.StoryPlanningError) as exc:
        story._select_passage_option(SimpleNamespace(ai={"source_quality_assessment":False}), actual["candidates"], actual["rows"], actual["chapters"], actual["plan"], actual["brief"], "fixture", None)
    assert exc.value.diagnostic["reason"] == "invalid_passage_option_output"
    assert reply == before


@pytest.mark.parametrize("language", ["en", "he"])
def test_selector_fit_and_no_fit_schemas_keep_all_six_required_fields(language, monkeypatch):
    rows, units, chapters, plan, brief, selection, payload = selected(language, monkeypatch)
    data = json.loads(payload["messages"][-1]["content"])
    fit = nominate(data["passage_candidates"][0], data)
    assert matches(fit, payload["format"])
    from tests.passage_contract_fixture import refuse
    no_fit = refuse(data['passage_candidates'][0], data)
    assert matches(no_fit, payload["format"])
    assert not matches({**no_fit, 'cited_segment_ids': []}, payload['format'])
    def reject_current(_settings, current_payload, *_):
        current = json.loads(current_payload['messages'][-1]['content'])
        return refuse(current['passage_candidates'][0], current)
    monkeypatch.setattr(story, "_call_ollama_story_pass", reject_current)
    with pytest.raises(story.StoryPlanningError) as exc:
        story._select_passage_option(SimpleNamespace(ai={}), units, rows, chapters, plan, brief, "fixture", None)
    assert exc.value.diagnostic["outcome"] == "editorial_no_fit"
    assert exc.value.diagnostic['semantic_result_verified'] is False
    for response in (fit, no_fit):
        for name in response:
            bad = dict(response); del bad[name]
            assert not matches(bad, payload["format"])
        assert not matches({**response, "invented": True}, payload["format"])


def test_other_emitted_local_schema_families_do_not_mix_object_and_union():
    from tests.native_shortlist_fixture import capture_native_shortlist
    actual = capture_native_shortlist()
    for payload in [*actual["understanding_payloads"], actual["precision_payload"]]: audit(payload["format"])
    audit(ANSWER_SCHEMA)
    catalog = story.build_story_evidence_catalog(actual["candidates"], actual["rows"])
    audit(story._precision_story_contract(catalog, actual["candidates"], actual["chapters"], actual["plan"], actual["brief"]))


@pytest.mark.parametrize("fault", ["unknown_property", "broaden_enum", "conflict_type", "conflict_constant", "root_extra", "unsupported_keyword"])
def test_builder_rejects_unsupported_intersections_instead_of_silently_weakening(fault):
    schema = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string", "enum": ["x", "y"]}},
              "required": ["a"], "anyOf": [{"properties": {"a": {"const": "x"}}}]}
    if fault == "unknown_property": schema["anyOf"][0]["properties"]["other"] = {"type": "string"}
    elif fault == "broaden_enum": schema["anyOf"][0]["properties"]["a"] = {"enum": ["z"]}
    elif fault == "conflict_type": schema["anyOf"][0]["properties"]["a"] = {"type": "integer"}
    elif fault == "conflict_constant": schema["anyOf"][0]["properties"]["a"] = {"const": "z"}
    elif fault == "unsupported_keyword": schema["anyOf"][0]["properties"]["a"] = {"not": {"const": "x"}}
    else: schema["allOf"] = []
    before = copy.deepcopy(schema)
    with pytest.raises(ValueError): complete_object_union(schema)
    assert schema == before
