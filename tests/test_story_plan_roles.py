from __future__ import annotations

import copy

import pytest

from cutroom import intelligence


ROLES = ("premise", "setup", "evidence", "result")


class Settings:
    ai = {"performance_mode": "balanced"}


def brief(*, with_structure=True):
    value = {"goal": "short", "duration_mode": "target", "target_duration": 20}
    if with_structure:
        value["style_profile"] = {"selection_policy": {"story_structure": list(ROLES)}}
    return value


def plan(roles):
    return {
        "narrative": "One source chapter supplies the complete story.",
        "slots": [
            {"purpose": role, "chapter_ids": ["c1"], "desired_seconds": 5,
             "reason": f"The source supplies the {role}.", "required_context_chapter_ids": []}
            for role in roles
        ],
    }


def capture_plan_call(monkeypatch, reply):
    calls = []

    def respond(_settings, payload, *_args):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(reply)

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    return calls


def test_one_chapter_premise_only_cannot_omit_configured_story_roles(monkeypatch):
    reply = plan(["premise"])
    calls = capture_plan_call(monkeypatch, reply)

    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, brief(), "fixture-model")

    assert len(calls) == 1
    assert reply["slots"] == plan(["premise"])["slots"]


def test_four_configured_roles_can_all_use_the_same_source_chapter(monkeypatch):
    reply = plan(ROLES)
    calls = capture_plan_call(monkeypatch, reply)

    result = intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, brief(), "fixture-model")

    assert len(calls) == 1
    assert [slot["purpose"] for slot in result["slots"]] == list(ROLES)
    assert all(slot["chapter_ids"] == ["c1"] for slot in result["slots"])
    assert len(result["slots"]) == len(reply["slots"])


@pytest.mark.parametrize("roles", [ROLES[:-1], (*ROLES, "premise")], ids=["missing_role", "duplicate_role"])
def test_configured_roles_must_each_appear_exactly_once_without_repair(monkeypatch, roles):
    calls = capture_plan_call(monkeypatch, plan(roles))

    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, brief(), "fixture-model")

    assert len(calls) == 1


def test_low_level_plan_without_a_story_structure_keeps_one_premise_compatibility(monkeypatch):
    calls = capture_plan_call(monkeypatch, plan(["premise"]))

    result = intelligence._build_story_plan(
        Settings(), [{"id": "c1"}], {}, brief(with_structure=False), "fixture-model",
    )

    assert len(calls) == 1
    assert [slot["purpose"] for slot in result["slots"]] == ["premise"]


def test_initial_plan_schema_exposes_the_complete_configured_role_contract(monkeypatch):
    base_schema = copy.deepcopy(intelligence.STORY_PLAN_SCHEMA)
    calls = capture_plan_call(monkeypatch, plan(ROLES))

    intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, brief(), "fixture-model")

    assert len(calls) == 1
    slots = calls[0]["format"]["properties"]["slots"]
    assert slots["minItems"] >= len(ROLES)
    assert set(slots["items"]["properties"]["purpose"]["enum"]) == set(ROLES)
    assert intelligence.STORY_PLAN_SCHEMA == base_schema


def test_review_rejects_an_incomplete_legacy_style_plan_before_a_model_call(monkeypatch):
    segment = {"id": "s1", "start": 0.0, "end": 20.0, "text": "A complete premise."}
    beat = {"id": "b1", "start": 0.0, "end": 20.0, "duration": 20.0,
            "segment_ids": ["s1"], "text": segment["text"]}
    selection = {
        "keep_beat_ids": ["b1"], "semantic_mapping_verified": True,
        "slot_map": [{"slot_index": 0, "purpose": "premise", "primary_beat_ids": ["b1"],
                      "context_beat_ids": [], "beat_ids": ["b1"],
                      "role_evidence": "The full source sentence supplies the premise."}],
        "critic": {},
    }
    original = copy.deepcopy(selection)
    calls = capture_plan_call(monkeypatch, {
        "verdict": "no_fit", "keep_beat_ids": [], "released_optional_beat_ids": [], "slot_selections": [],
    })

    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._review_story_target_budget(
            Settings(), selection, [beat], [segment], [{"id": "c1", "beats": [beat]}], {},
            plan(["premise"]), brief(), "fixture-model",
        )

    assert calls == []
    assert selection == original
