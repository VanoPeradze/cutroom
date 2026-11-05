from __future__ import annotations

import copy

import pytest

from cutroom import director, intelligence, story_evidence
from cutroom.edit_styles import enrich_brief_with_style, required_story_roles_from_policy
from cutroom.story_budget import StoryPlanningError
from test_precision_contract import fixture as precision_fixture
from test_story_evidence import mapped_fixture
from test_story_intent_separation import Settings, capture_model_reply, plan_reply
from test_director_rebuild_cache import semantic_project


@pytest.mark.parametrize(("instruction", "expected"), [
    ("Structure: setup -> result.", [["setup", "result"]]),
    ("Required story roles: result, setup.", []),
    ("Include a result. Include setup.", []),
    ("\u05de\u05d1\u05e0\u05d4: \u05d4\u05e7\u05e9\u05e8 -> \u05ea\u05d5\u05e6\u05d0\u05d4.", [["\u05d4\u05e7\u05e9\u05e8", "\u05ea\u05d5\u05e6\u05d0\u05d4"]]),
    ("\u05db\u05dc\u05d5\u05dc \u05ea\u05d5\u05e6\u05d0\u05d4. \u05db\u05dc\u05d5\u05dc \u05d4\u05e7\u05e9\u05e8.", []),
])
def test_only_an_explicit_progression_adds_order_constraints(instruction, expected):
    brief = enrich_brief_with_style({"instruction": instruction, "edit_style": "funny_moments"})
    assert brief["story_contract"]["ordered_role_groups"] == expected
    assert brief["style_profile"]["selection_policy"]["required_story_role_orders"] == expected
    assert brief["instruction"] == instruction


@pytest.mark.parametrize("instruction", [
    "Structure: setup -> result.",
    "\u05de\u05d1\u05e0\u05d4: \u05d4\u05e7\u05e9\u05e8 -> \u05ea\u05d5\u05e6\u05d0\u05d4.",
])
def test_reversed_explicit_model_plan_is_rejected_as_invalid_output(instruction):
    brief = enrich_brief_with_style({"instruction": instruction})
    roles = brief["story_contract"]["required_roles"]
    with pytest.raises(StoryPlanningError) as caught:
        intelligence._validate_configured_story_roles(plan_reply(*reversed(roles)), brief)
    assert caught.value.diagnostic["outcome"] == "invalid_model_output"
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("instruction", ["Include a result. Include setup.",
    "\u05db\u05dc\u05d5\u05dc \u05ea\u05d5\u05e6\u05d0\u05d4. \u05db\u05dc\u05d5\u05dc \u05d4\u05e7\u05e9\u05e8."])
def test_independent_role_requests_allow_source_chronology_and_extra_context(instruction):
    brief = enrich_brief_with_style({"instruction": instruction})
    roles = brief["story_contract"]["required_roles"]
    intelligence._validate_configured_story_roles(plan_reply("premise", *reversed(roles)), brief)


def test_one_requested_role_can_use_a_complete_passage_from_multiple_summaries(monkeypatch):
    calls = capture_model_reply(monkeypatch, plan_reply("explanation"))
    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}, {"id": "c2"}], {},
        enrich_brief_with_style({"instruction": "Include an explanation.", "target_duration": 20}), "fixture")
    assert [row["purpose"] for row in result["slots"]] == ["explanation"]
    assert len(calls) == 1
    assert "enum" not in calls[0]["format"]["properties"]["slots"]["items"]["properties"]["purpose"]


def test_precision_contract_keeps_extra_source_supported_plan_roles():
    beats, _segments, chapters, plan, brief, catalog, _reply = precision_fixture()
    brief["instruction"] = "Include a result."
    schema = intelligence._precision_story_contract(catalog, beats, chapters, plan, brief)
    assert schema["anyOf"][0]["properties"]["role_selections"]["required"] == [row["purpose"] for row in plan["slots"]]


@pytest.mark.parametrize("instruction", ["Include result. Include setup.", "Required story roles: result, setup.",
    "Structure: setup -> result."])
def test_director_accepts_coverage_and_partial_order_with_additional_source_roles(instruction):
    beats, segments, _catalog, rows = mapped_fixture()
    proof = story_evidence.validate_story_evidence(rows, beats, segments, selected_beat_ids=[beat["id"] for beat in beats])
    decision = {"story_ranges": [{"beat_id": beat["id"], "start": beat["start"], "end": beat["end"]} for beat in beats],
                "story_requirements": {"evidence_policy_version": story_evidence.EVIDENCE_POLICY_VERSION,
                                       "evidence_proof": copy.deepcopy(proof), "slot_map": copy.deepcopy(proof["slot_map"])}}
    policy = enrich_brief_with_style({"instruction": instruction})["style_profile"]["selection_policy"]
    assert director._verified_source_story_evidence(decision, segments, policy) == proof


def test_director_surfaces_explicit_order_conflict_with_the_current_source_proposal():
    beats, segments, _catalog, rows = mapped_fixture()
    proof = story_evidence.validate_story_evidence(rows, beats, segments, selected_beat_ids=[beat["id"] for beat in beats])
    decision = {"story_ranges": [{"beat_id": beat["id"], "start": beat["start"], "end": beat["end"]} for beat in beats],
                "story_requirements": {"evidence_policy_version": story_evidence.EVIDENCE_POLICY_VERSION,
                                       "evidence_proof": copy.deepcopy(proof), "slot_map": copy.deepcopy(proof["slot_map"])}}
    policy = enrich_brief_with_style({"instruction": "Structure: result -> setup."})["style_profile"]["selection_policy"]
    before = copy.deepcopy((decision, segments))
    with pytest.raises(ValueError, match="explicit required role order"):
        director._verified_source_story_evidence(decision, segments, policy)
    assert (decision, segments) == before


@pytest.mark.parametrize("instruction", [
    "Structure: setup -> result. Structure: result -> setup.",
    "\u05de\u05d1\u05e0\u05d4: \u05d4\u05e7\u05e9\u05e8 -> \u05ea\u05d5\u05e6\u05d0\u05d4. \u05de\u05d1\u05e0\u05d4: \u05ea\u05d5\u05e6\u05d0\u05d4 -> \u05d4\u05e7\u05e9\u05e8.",
])
def test_conflicting_user_order_is_surfaced_before_any_model_call(instruction):
    with pytest.raises(StoryPlanningError) as caught:
        enrich_brief_with_style({"instruction": instruction})
    assert caught.value.diagnostic["outcome"] == "constraint_conflict"
    assert caught.value.diagnostic["reason"] == "contradictory_story_role_order"
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("instruction", ["Include a punchline. Captions are optional.",
    "Structure: setup -> result. Optional captions.", "Include a punchline.\nOptional captions: white text.",
    "Structure: setup -> result.\nOptional captions: white text.", "Optional captions: white text.\nInclude a punchline."])
def test_optional_unrelated_controls_do_not_erase_an_explicit_role_request(instruction):
    assert enrich_brief_with_style({"instruction": instruction})["story_contract"]["required_roles"]


def test_order_request_cannot_authorize_inverted_canonical_source_evidence():
    beats, segments, _catalog, rows = mapped_fixture()
    for index, row in enumerate(reversed(rows)):
        row["slot_index"] = index
    with pytest.raises(ValueError, match="inverted"):
        story_evidence.validate_story_evidence(rows, beats, segments, selected_beat_ids=[beat["id"] for beat in beats])


def test_versioned_policy_cannot_drop_order_metadata():
    policy = enrich_brief_with_style({"instruction": "Structure: setup -> result."})["style_profile"]["selection_policy"]
    del policy["required_story_role_orders"]
    with pytest.raises(StoryPlanningError) as caught:
        required_story_roles_from_policy(policy)
    assert caught.value.diagnostic["reason"] == "invalid_story_intent_contract"


@pytest.mark.parametrize("instruction", ["Structure: setup -> result. Structure: result -> setup.",
    "\u05de\u05d1\u05e0\u05d4: \u05d4\u05e7\u05e9\u05e8 -> \u05ea\u05d5\u05e6\u05d0\u05d4. \u05de\u05d1\u05e0\u05d4: \u05ea\u05d5\u05e6\u05d0\u05d4 -> \u05d4\u05e7\u05e9\u05e8."])
def test_order_conflict_preserves_original_and_existing_edit_before_model_work(semantic_project, instruction):
    store, settings, pid, calls, context = semantic_project
    before = store.state_path(pid).read_bytes()
    source = store.project_dir(pid) / "media" / "source-A.mp4"
    source_bytes, called = source.read_bytes(), copy.deepcopy(calls)
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(context(), pid, store, settings, {"instruction": instruction})
    assert caught.value.diagnostic["outcome"] == "constraint_conflict"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert store.state_path(pid).read_bytes() == before and source.read_bytes() == source_bytes
    assert calls == called
