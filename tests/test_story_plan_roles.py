from __future__ import annotations

import copy

import pytest

from cutroom import intelligence, story_evidence


ROLES = ("premise", "setup", "evidence", "result")


class Settings:
    ai = {"performance_mode": "balanced"}


def brief(*, with_structure=True):
    value = {"goal": "short", "duration_mode": "target", "target_duration": 20}
    if with_structure:
        value["instruction"] = "Structure: " + " -> ".join(ROLES)
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
    # Required roles are minimum coverage; extra grounded context is permitted.
    assert "enum" not in slots["items"]["properties"]["purpose"]
    assert intelligence.STORY_PLAN_SCHEMA == base_schema


def test_review_rejects_an_incomplete_explicit_user_plan_before_a_model_call(monkeypatch):
    segment = {"id": "s1", "start": 0.0, "end": 20.0, "text": "A complete premise."}
    beat = {"id": "b1", "start": 0.0, "end": 20.0, "duration": 20.0,
            "segment_ids": ["s1"], "text": segment["text"]}
    citations = [row["id"] for row in story_evidence.build_story_evidence_catalog([beat], [segment])]
    selection = {
        "keep_beat_ids": ["b1"], "semantic_mapping_verified": True,
        "slot_map": [{"slot_index": 0, "purpose": "premise", "primary_beat_ids": ["b1"],
                      "context_beat_ids": [], "beat_ids": ["b1"],
                      "primary_evidence_ids": citations, "context_evidence_ids": [],
                      "temporal_witness_id": citations[0]}],
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


@pytest.fixture
def no_story_ai(monkeypatch):
    def unexpected_call(*_args, **_kwargs):
        raise AssertionError("Non-Short source-evidence verification must not call Story AI.")

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", unexpected_call)
    monkeypatch.setattr(intelligence, "open_ollama", unexpected_call)


def podcast_fixture():
    segments = [{"id": f"s{index}", "start": float((index - 1) * 10),
                 "end": float((index - 1) * 10 + 4), "text": f"The source supplies the {role}."}
                for index, role in enumerate(ROLES, 1)]
    beats = [{"id": f"b{index}", "start": segment["start"], "end": segment["end"], "duration": 4.0,
              "segment_ids": [segment["id"]], "text": segment["text"]}
             for index, segment in enumerate(segments, 1)]
    catalog = story_evidence.build_story_evidence_catalog(beats, segments)
    keep = [beat["id"] for beat in beats]
    rows = []
    for index, (role, beat) in enumerate(zip(ROLES, beats)):
        citations = [row["id"] for row in catalog if row["beat_id"] == beat["id"]]
        rows.append({"slot_index": index, "purpose": role, "primary_beat_ids": [beat["id"]],
                     "context_beat_ids": [], "primary_evidence_ids": citations, "context_evidence_ids": [],
                     "temporal_witness_id": citations[0]})
    precision = {"keep_beat_ids": list(keep), "slot_map": rows, "recovered_slot_indexes": []}
    selection = copy.deepcopy(precision)
    selection["critic"] = {"verdict": "pass", "review_verdict": "pass", "reviewed_beat_ids": list(keep),
                           "issues": [], "selection_changed_after_review": False,
                           "requested_added": [], "requested_removed": [], "selection_before": list(keep),
                           "post_review_beat_ids": list(keep)}
    podcast_brief = {**brief(), "goal": "podcast", "target_duration": 120}
    return selection, precision, beats, segments, [{"id": "c1", "beats": beats}], plan(ROLES), podcast_brief


def test_underfilled_podcast_with_original_typed_evidence_and_clean_critic_is_verified_without_ai(no_story_ai):
    fixture = podcast_fixture()
    original = copy.deepcopy(fixture)

    result = intelligence._verify_non_short_story_evidence(*fixture)

    assert fixture == original
    assert result["keep_beat_ids"] == ["b1", "b2", "b3", "b4"]
    assert result["semantic_mapping_verified"] is True
    assert result["semantic_review_status"] == "model_reviewed"
    assert result["evidence_proof"]["verification_scope"] == "source_attribution_and_order"
    assert result["semantic_revision"]["attempts"] == 0
    assert result["semantic_revision"]["duration_policy"] == "existing_non_short_policy"
    assert result["semantic_revision"]["cost"]["approved_seconds"] == 16
    assert result["semantic_revision"]["cost"]["approved_seconds"] < .9 * fixture[-1]["target_duration"]


@pytest.mark.parametrize("patch", [
    {"verdict": "revise", "issues": ["A reference is unclear."]},
    {"verdict": "skipped", "review_verdict": "skipped"},
    {"review_verdict": "revise"},
    {"selection_changed_after_review": True},
])
def test_non_short_evidence_requires_an_actual_clean_unchanged_critic(no_story_ai, patch):
    fixture = podcast_fixture()
    fixture[0]["critic"].update(patch)

    with pytest.raises(intelligence.StoryPlanningError, match="non-Short source evidence"):
        intelligence._verify_non_short_story_evidence(*fixture)


def test_non_short_legacy_free_claims_cannot_replace_original_typed_citations(no_story_ai):
    fixture = podcast_fixture()
    for row in fixture[1]["slot_map"]:
        for key in ("primary_evidence_ids", "context_evidence_ids", "temporal_witness_id"):
            row.pop(key)
        row["role_evidence"] = "The source supports this role."

    with pytest.raises(intelligence.StoryPlanningError, match="non-Short source evidence"):
        intelligence._verify_non_short_story_evidence(*fixture)


def test_non_short_verification_preserves_precision_citations_after_legacy_fitter_rows(no_story_ai):
    fixture = podcast_fixture()
    selection, precision = fixture[:2]
    original_precision = copy.deepcopy(precision)
    selection["slot_map"] = [{"slot_index": row["slot_index"], "purpose": row["purpose"],
                              "beat_ids": list(row["primary_beat_ids"])} for row in precision["slot_map"]]

    result = intelligence._verify_non_short_story_evidence(*fixture)

    assert precision == original_precision
    assert result["keep_beat_ids"] == selection["keep_beat_ids"]
    for actual, original in zip(result["slot_map"], original_precision["slot_map"]):
        assert actual["primary_evidence_ids"] == original["primary_evidence_ids"]
        assert actual["temporal_witness_id"] == original["temporal_witness_id"]
        assert actual["source_evidence"]


@pytest.mark.parametrize("fault", ["reversed_order", "incomplete_source"])
def test_non_short_evidence_rejects_invalid_order_or_incomplete_passages(no_story_ai, fault):
    fixture = podcast_fixture()
    _selection, precision, beats, segments, _chapters, _plan, _brief = fixture
    if fault == "reversed_order":
        first, last = precision["slot_map"][0], precision["slot_map"][-1]
        for key in ("primary_beat_ids", "primary_evidence_ids", "temporal_witness_id"):
            first[key], last[key] = last[key], first[key]
    else:
        beats[-1]["text"] = segments[-1]["text"] = "An unfinished source result"

    with pytest.raises(intelligence.StoryPlanningError, match="non-Short source evidence"):
        intelligence._verify_non_short_story_evidence(*fixture)
