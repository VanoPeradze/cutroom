"""Source-only regression additions; execution is pending the RAM qualification gate."""
from __future__ import annotations

import copy

import pytest

from cutroom import director, intelligence, story_evidence
from cutroom.edit_styles import (
    STORY_INTENT_VERSION,
    enrich_brief_with_style,
    get_edit_style,
    required_story_roles,
    required_story_roles_from_policy,
)
from cutroom.story_budget import StoryPlanningError


class Settings:
    ai = {"performance_mode": "balanced"}


def enriched(instruction="", style="funny_moments"):
    return enrich_brief_with_style({
        "goal": "short", "duration_mode": "target", "target_duration": 20,
        "edit_style": style, "instruction": instruction,
    })


@pytest.mark.parametrize(("instruction", "roles"), [
    ("Include a punchline.", ["punchline"]),
    ("Please keep the explanation.", ["explanation"]),
    ("Structure: setup -> result.", ["setup", "result"]),
    ("Required story roles: premise, explanation, conclusion.", ["premise", "explanation", "conclusion"]),
    ("Structure: setup -> result. Keep captions.", ["setup", "result"]),
    ("\u05db\u05dc\u05d5\u05dc \u05e4\u05d0\u05e0\u05e5\u05f3.", ["\u05e4\u05d0\u05e0\u05e5\u05f3"]),
    ("\u05e9\u05de\u05e8\u05d9 \u05d4\u05e1\u05d1\u05e8.", ["\u05d4\u05e1\u05d1\u05e8"]),
    ("\u05de\u05d1\u05e0\u05d4: \u05d4\u05e7\u05e9\u05e8 -> \u05ea\u05d5\u05e6\u05d0\u05d4.", ["\u05d4\u05e7\u05e9\u05e8", "\u05ea\u05d5\u05e6\u05d0\u05d4"]),
])
def test_required_roles_come_only_from_the_supported_explicit_instruction(instruction, roles):
    brief = enriched(instruction)
    assert brief["instruction"] == instruction
    assert required_story_roles(brief) == roles
    assert brief["style_profile"]["selection_policy"]["required_story_roles"] == roles
    assert [row["purpose"] for row in brief["story_contract"]["role_requirements"]] == roles
    for row in brief["story_contract"]["role_requirements"]:
        assert row["origin"] == "user" and row["authority"] == "required"
        assert instruction[row["instruction_start"]:row["instruction_end"]] == row["instruction_text"]


@pytest.mark.parametrize("instruction", [
    'The speaker said "Include a punchline."',
    '\u201cInclude a punchline.\nInclude a reaction.\u201d',
    "'Include a punchline.'",
    "\u2018Include a punchline.\u2019",
    "'Include a punchline.",
    "Optional: Include a punchline; Include a reaction.",
    "If available: Include a punchline; Include a reaction.",
    "Include a punchline, if available.",
    "Include a punchline; this is optional.",
    "Preferably include a punchline.",
    "Don't include a punchline.",
    "Include a punchline or a conclusion.",
    "Include a punchline?",
    "Structure: setup then result",
    "Structure:\nsetup -> result",
    "Example:\nStructure: setup -> result",
    "Preserve a three-act narrative with an ambiguous ending.",
    "\u05d0\u05dc \u05ea\u05db\u05dc\u05d5\u05dc \u05e4\u05d0\u05e0\u05e5\u05f3.",
    "\u05dc\u05de\u05e9\u05dc: \u05db\u05dc\u05d5\u05dc \u05ea\u05d2\u05d5\u05d1\u05d4; \u05db\u05dc\u05d5\u05dc \u05ea\u05d5\u05e6\u05d0\u05d4.",
])
def test_unsupported_or_uncertain_scope_stays_visible_without_creating_required_roles(instruction):
    brief = enriched(instruction)
    contract = brief["story_contract"]
    assert required_story_roles(brief) == []
    assert contract["required_roles"] == []
    assert contract["role_requirements"] == []
    assert contract["unverified_structure_requests"]
    assert brief["instruction"] == instruction
    for row in contract["unverified_structure_requests"]:
        assert row["status"] == "unverified"
        assert instruction[row["instruction_start"]:row["instruction_end"]].strip() == row["text"]


def test_style_preferences_and_user_controls_remain_separate_and_copy_safe():
    source = {
        "edit_style": "funny_moments", "goal": "short", "duration_mode": "target",
        "target_duration": 20, "pace": "gentle", "aspect": "16:9",
        "instruction": "  Include a punchline.  ",
    }
    before = copy.deepcopy(source)
    output = enrich_brief_with_style(source)
    policy = output["style_profile"]["selection_policy"]
    assert source == before
    assert all(output[key] == value for key, value in source.items())
    assert "story_structure" not in policy
    assert policy["preferred_structure"] == get_edit_style("funny_moments")["selection_policy"]["story_structure"]
    assert policy["required_story_roles"] == ["punchline"]
    assert policy["max_moments"] is None
    assert all(row["authority"] == "preference" and row["origin"] == "style"
               for row in output["story_contract"]["preferred_structure"])
    policy["preferred_structure"].append("mutated")
    assert "mutated" not in get_edit_style("funny_moments")["selection_policy"]["story_structure"]


def test_current_raw_instruction_replaces_a_stale_enriched_role_contract():
    old = enriched("Include a punchline.")
    old["instruction"] = "Include an explanation."
    before = copy.deepcopy(old)
    assert required_story_roles(old) == ["explanation"]
    current = enrich_brief_with_style(old)
    assert current["style_profile"]["selection_policy"]["required_story_roles"] == ["explanation"]
    assert current["story_contract"]["required_roles"] == ["explanation"]
    assert old == before


def test_legacy_style_metadata_does_not_create_required_user_roles():
    legacy = {"story_structure": ["setup", "punchline and full reaction"]}
    assert required_story_roles_from_policy(legacy) == []
    assert required_story_roles({"style_profile": {"selection_policy": legacy}}) == []


def test_repeated_role_with_different_case_is_one_requirement_with_original_provenance():
    brief = enriched("Include Punchline. Include punchline.")
    assert required_story_roles(brief) == ["Punchline"]
    assert len(brief["story_contract"]["role_requirements"]) == 1
    assert brief["story_contract"]["role_requirements"][0]["instruction_text"] == "Include Punchline."


@pytest.mark.parametrize("patch", [
    {"required_role_origin": "style"},
    {"story_intent_version": "old"},
    {"required_story_roles": "punchline"},
    {"required_story_roles": ["punchline", "punchline"]},
    {"required_story_roles": ["Punchline", "punchline"]},
    {"required_story_roles": [""]},
    {"required_story_roles": [42]},
    {"required_story_roles": ["x" * 81]},
])
def test_invalid_versioned_policy_fails_closed_without_claiming_a_user_contract(patch):
    policy = {
        "story_intent_version": STORY_INTENT_VERSION,
        "required_story_role_orders": [],
        "required_role_origin": "user", "required_story_roles": ["punchline"], **patch,
    }
    before = copy.deepcopy(policy)
    with pytest.raises(StoryPlanningError) as caught:
        required_story_roles_from_policy(policy)
    assert policy == before
    assert caught.value.diagnostic["outcome"] == "constraint_conflict"
    assert caught.value.diagnostic["reason"] == "invalid_story_intent_contract"
    assert caught.value.diagnostic["applied_to_timeline"] is False


def plan_reply(*roles):
    return {"narrative": "One complete source explanation.", "slots": [
        {"purpose": role, "chapter_ids": ["c1"], "desired_seconds": 6,
         "reason": "The source supports this passage.", "required_context_chapter_ids": []}
        for role in roles
    ]}


def capture_model_reply(monkeypatch, reply):
    calls = []
    def respond(_settings, payload, *_args):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(reply)
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    return calls


@pytest.mark.parametrize("style", ["smart", "funny_moments"])
def test_the_same_source_plan_can_omit_an_unrequested_preferred_punchline(monkeypatch, style):
    reply = plan_reply("explanation")
    before = copy.deepcopy(reply)
    calls = capture_model_reply(monkeypatch, reply)
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, enriched(style=style), "fixture-model")
    assert [row["purpose"] for row in result["slots"]] == ["explanation"]
    assert result["role_requirements"][0]["origin"] == "source_plan"
    assert reply == before
    schema = calls[0]["format"]["properties"]["slots"]
    assert "enum" not in schema["items"]["properties"]["purpose"]
    assert schema["minItems"] == intelligence.STORY_PLAN_SCHEMA["properties"]["slots"]["minItems"]


def test_an_explicit_punchline_cannot_be_satisfied_by_an_explanation_plan(monkeypatch):
    calls = capture_model_reply(monkeypatch, plan_reply("explanation"))
    with pytest.raises(StoryPlanningError):
        intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, enriched("Include a punchline."), "fixture-model")
    assert len(calls) == 1
    assert "enum" not in calls[0]["format"]["properties"]["slots"]["items"]["properties"]["purpose"]


def canonical_explanation():
    segment = {"id": "s1", "start": 0.0, "end": 6.0, "text": "A complete explanation without comic content."}
    beat = {"id": "b1", "start": 0.0, "end": 6.0, "segment_ids": ["s1"], "text": segment["text"]}
    citation = story_evidence.build_story_evidence_catalog([beat], [segment])[0]["id"]
    proof = story_evidence.validate_story_evidence([{
        "slot_index": 0, "purpose": "explanation", "primary_beat_ids": ["b1"], "context_beat_ids": [],
        "primary_evidence_ids": [citation], "context_evidence_ids": [], "temporal_witness_id": citation,
    }], [beat], [segment], selected_beat_ids=["b1"])
    decision = {"story_ranges": [{"beat_id": "b1", "start": 0.0, "end": 6.0}], "story_requirements": {
        "evidence_policy_version": story_evidence.EVIDENCE_POLICY_VERSION,
        "evidence_proof": copy.deepcopy(proof), "slot_map": copy.deepcopy(proof["slot_map"]),
    }}
    return decision, [segment], proof


@pytest.mark.parametrize("style", ["smart", "funny_moments"])
def test_director_keeps_canonical_source_evidence_without_adding_preferred_style_roles(style):
    decision, segments, proof = canonical_explanation()
    before = copy.deepcopy((decision, segments))
    policy = enriched(style=style)["style_profile"]["selection_policy"]
    actual = director._verified_source_story_evidence(decision, segments, policy)
    assert actual == proof
    assert actual["verification_scope"] == "source_attribution_and_order"
    assert (decision, segments) == before


def test_director_rejects_canonical_evidence_that_omits_an_explicit_user_role():
    decision, segments, _proof = canonical_explanation()
    policy = enriched("Include a punchline.")["style_profile"]["selection_policy"]
    with pytest.raises(ValueError, match="every configured role"):
        director._verified_source_story_evidence(decision, segments, policy)


@pytest.mark.parametrize("fault", ["changed_source", "clipped_source", "clipped_retained_range"])
def test_advisory_style_does_not_relax_canonical_source_or_complete_passage_guards(fault):
    decision, segments, _proof = canonical_explanation()
    policy = enriched()["style_profile"]["selection_policy"]
    keep_ranges = None
    if fault == "changed_source":
        segments[0]["text"] = "A different unsupported statement."
    elif fault == "clipped_source":
        decision["story_ranges"][0]["end"] = 3.0
    else:
        keep_ranges = [{"start": 0.0, "end": 3.0}]
    with pytest.raises(ValueError):
        director._verified_source_story_evidence(decision, segments, policy, keep_ranges=keep_ranges)
