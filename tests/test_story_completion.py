from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence


class Settings:
    ai = {"enabled": True, "editor_model": "fixture-model", "editor_fallback_models": []}


def test_short_beats_split_only_after_complete_source_sentences():
    segments = [
        {"id": "s1", "start": 0, "end": 10.4, "text": "A synthetic sentence continues"},
        {"id": "s2", "start": 10.4, "end": 15.3, "text": "until its complete ending."},
        {"id": "s3", "start": 15.5, "end": 17.3, "text": "Another complete sentence."},
        {"id": "s4", "start": 18.2, "end": 24.6, "text": "A final complete sentence."},
    ]
    original = copy.deepcopy(segments)
    default = intelligence.build_story_beats(segments, "en")
    short = intelligence.build_story_beats(segments, "en", target_seconds=20)

    assert len(default) == 1
    # Every complete ASR boundary is now selectable, not just a half-target group.
    assert [row["segment_ids"] for row in short] == [["s1", "s2"], ["s3"], ["s4"]]
    assert [(row["start"], row["end"]) for row in short] == [(0, 15.3), (15.5, 17.3), (18.2, 24.6)]
    assert segments == original


def test_target_aware_beats_do_not_cut_an_unfinished_sentence_to_fill_budget():
    segments = [{"id": f"s{i}", "start": i * 5, "end": (i + 1) * 5,
                 "text": "an unfinished synthetic continuation"} for i in range(7)]
    beats = intelligence.build_story_beats(segments, "en", target_seconds=20)
    assert len(beats) == 1
    assert beats[0]["segment_ids"] == [f"s{i}" for i in range(7)]


def test_unbounded_unpunctuated_short_input_fails_before_any_model_call():
    segments = [{"id": f"s{i}", "start": i * 5, "end": (i + 1) * 5,
                 "text": "an unfinished synthetic continuation"} for i in range(24)]
    with pytest.raises(intelligence.StoryPlanningError, match="90 seconds.*sentence boundary"):
        intelligence.build_story_beats(segments, "en", target_seconds=20)
    assert len(intelligence.build_story_beats(segments, "en")) == 4


@pytest.mark.parametrize("goal,expected_count", [("short", 4), ("podcast", 1)])
def test_only_short_planning_uses_target_aware_sentence_choices(monkeypatch, goal, expected_count):
    segments = [{"id": f"s{i}", "start": i * 6, "end": i * 6 + 5,
                 "text": "A complete synthetic sentence."} for i in range(4)]
    monkeypatch.setattr(intelligence, "hierarchical_story_edit", lambda *_args, **_kwargs: ({}, {}))
    editorial, _ = intelligence.plan_edit(segments, Settings(), {
        "goal": goal, "target_duration": 20, "language": "en",
    })
    assert len(editorial["story_beats"]) == expected_count


def test_coarse_beat_cache_identity_cannot_alias_target_aware_beat_ids(monkeypatch):
    segments = [{"id": f"s{i}", "start": i * 6, "end": i * 6 + 5,
                 "text": "A complete synthetic sentence."} for i in range(4)]
    brief = {"goal": "short", "target_duration": 20}
    current = intelligence.story_cache_fingerprint(segments, brief, "fixture-model")
    with monkeypatch.context() as legacy:
        legacy.setattr(intelligence, "STORY_CACHE_PIPELINE", "hierarchical-story-2026-09-06.full-chapter-input")
        previous = intelligence.story_cache_fingerprint(segments, brief, "fixture-model")
    assert current != previous
    coarse = intelligence.build_story_beats(segments, "en")
    short = intelligence.build_story_beats(segments, "en", target_seconds=20)
    # Geometry-changing projections must not retain the coarse unit's identity.
    assert coarse[0]["id"] != short[0]["id"]
    assert coarse[0]["end"] != short[0]["end"]


def context_selection():
    beats = [
        {"id": "context", "start": 0, "end": 25, "segment_ids": ["s1"], "text": "Complete context."},
        {"id": "result", "start": 30, "end": 38, "segment_ids": ["s2"], "text": "A complete result."},
        {"id": "unselected", "start": 42, "end": 44, "segment_ids": ["s3"], "text": "An unrelated line."},
    ]
    selection = {
        "keep_beat_ids": ["context", "result"],
        "slot_map": [{"slot_index": 0, "beat_ids": ["result"]}],
        "critic": {"verdict": "revise", "selection_before": ["result"],
                   "post_review_beat_ids": ["context", "result"],
                   "requested_added": ["context"], "requested_removed": []},
    }
    return selection, beats


def test_budget_fit_retains_critic_context_and_reports_infeasible_whole_passages():
    selection, beats = context_selection()
    fitted = intelligence._fit_story_selection_to_budget(
        selection, beats, {"slots": [{"desired_seconds": 8}]}, 20,
    )
    assert fitted["keep_beat_ids"] == ["context", "result"]
    assert fitted["critic"]["added"] == ["context"]
    assert fitted["critic"]["unapplied_actions"] == []
    assert fitted["budget_fit"]["status"] == "required_material_exceeds_ceiling"
    assert fitted["budget_fit"]["after_duration"] == 33
    assert fitted["budget_fit"]["over_ceiling_seconds"] == pytest.approx(10.6)


def test_critic_sees_actual_passage_durations_before_requesting_context(monkeypatch):
    selection, beats = context_selection()
    selection.pop("critic")
    segments = [{"id": row["segment_ids"][0], **{key: row[key] for key in ("start", "end", "text")}}
                for row in beats]
    captured = {}

    def reply(_settings, payload, *_args):
        captured.update(json.loads(payload["messages"][1]["content"]))
        return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": ""}

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", reply)
    intelligence._critic_story_selection(Settings(), selection, beats, {}, {}, {"target_duration": 20}, "fixture-model",
                                        segments=segments)
    assert [(row["id"], row["end"], row["duration"]) for row in captured["selected"]] == [
        ("context", 25, 25), ("result", 38, 8),
    ]
    assert captured["candidates"][2]["duration"] == 2


def test_completion_contract_includes_whole_critic_context_and_unresolved_slots():
    selection, beats = context_selection()
    # Defend against an older budget fitter dropping a requested context beat.
    selection["keep_beat_ids"] = ["result"]
    selection["slot_map"].append({"slot_index": 1, "beat_ids": []})
    segments = [{"id": f"s{i}"} for i in range(1, 4)]
    decision = intelligence._story_decision_from_beats(selection, beats, segments)
    assert decision["story_beat_ids"] == ["context", "result"]
    assert decision["keep_ids"] == ["s1", "s2"]
    assert decision["story_ranges"] == [
        {"start": 0, "end": 25, "beat_id": "context"},
        {"start": 30, "end": 38, "beat_id": "result"},
    ]
    assert decision["story_requirements"] == {
        "required_beat_ids": ["context", "result"],
        "critic_requested_beat_ids": ["context"],
        "unresolved_slot_indexes": [1],
        "unapplied_critic_actions": 0,
        "semantic_mapping_verified": False,
        "semantic_review_status": None,
        "evidence_policy_version": None,
        "evidence_proof": None,
        "source_span_policy_version": None,
        "source_span_constraints": None,
        "required_context_beat_ids": [],
        "required_context_segment_ids": [],
        "semantic_revision": None,
        "slot_map": selection["slot_map"],
    }


def test_completion_contract_cannot_restore_an_explicitly_rejected_beat():
    selection, beats = context_selection()
    selection["critic"]["requested_removed"] = ["context"]
    decision = intelligence._story_decision_from_beats(
        selection, beats, [{"id": f"s{i}"} for i in range(1, 4)],
    )
    assert decision["story_beat_ids"] == ["result"]
    assert decision["story_requirements"]["critic_requested_beat_ids"] == []
    assert decision["rejected_segment_ids"] == ["s1"]


def test_underfilled_budget_swaps_only_approved_slot_alternatives():
    beats = [{"id": "brief", "start": 0, "end": 3, "text": "A short setup."},
             {"id": "substantive", "start": 10, "end": 27, "text": "A substantive complete setup."},
             {"id": "ending", "start": 35, "end": 38, "text": "A complete ending."},
             {"id": "unapproved", "start": 45, "end": 59, "text": "An unrelated candidate."}]
    selection = {"keep_beat_ids": ["brief", "substantive", "ending"],
                 "slot_map": [{"slot_index": 0, "beat_ids": ["brief", "substantive"]},
                              {"slot_index": 1, "beat_ids": ["ending"]}]}
    fitted = intelligence._fit_story_selection_to_budget(
        selection, beats, {"slots": [{"desired_seconds": 3}, {"desired_seconds": 3}]}, 20,
    )
    assert fitted["keep_beat_ids"] == ["substantive", "ending"]
    assert fitted["budget_fit"]["after_duration"] == 20
    assert all(row["beat_ids"] for row in fitted["slot_map"])


def test_optional_headroom_material_cannot_hide_a_strictly_feasible_target():
    beats = [{"id": "brief", "start": 0, "end": 2, "text": "A brief setup."},
             {"id": "substantive", "start": 10, "end": 27, "text": "The full setup."},
             {"id": "ending", "start": 35, "end": 38, "text": "The ending."}]
    fitted = intelligence._fit_story_selection_to_budget({
        "keep_beat_ids": [row["id"] for row in beats],
        "slot_map": [{"slot_index": 0, "beat_ids": ["brief", "substantive"]},
                     {"slot_index": 1, "beat_ids": ["ending"]}],
    }, beats, {"slots": [{"desired_seconds": 2}, {"desired_seconds": 3}]}, 20)
    assert fitted["keep_beat_ids"] == ["substantive", "ending"]
    assert fitted["budget_fit"]["after_duration"] == 20


@pytest.mark.parametrize("context_rejected", [False, True])
def test_required_context_is_a_selected_source_obligation_not_an_allowed_chapter(context_rejected):
    beats = [{"id": "setup1", "start": 0, "end": 8, "text": "A complete primary idea."},
             {"id": "setup2", "start": 10, "end": 18, "text": "Another primary idea."},
             {"id": "context", "start": 25, "end": 40, "text": "The complete prerequisite context."}]
    selection = {
        "keep_beat_ids": [row["id"] for row in beats],
        "slot_map": [{"slot_index": 0, "beat_ids": [row["id"] for row in beats]}],
        "critic": {"verdict": "pass", "issues": [], "selection_before": [row["id"] for row in beats],
                   "post_review_beat_ids": [row["id"] for row in beats],
                   "requested_added": [], "requested_removed": ["context"] if context_rejected else []},
    }
    plan = {"slots": [{"chapter_ids": ["primary"], "required_context_chapter_ids": ["prerequisite"],
                       "desired_seconds": 8}]}
    fitted = intelligence._fit_story_selection_to_budget(
        selection, beats, plan, 20,
        [{"id": "primary", "beats": beats[:2]}, {"id": "prerequisite", "beats": beats[2:]}],
    )
    assert ("context" in fitted["keep_beat_ids"]) is not context_rejected
    assert fitted["critic"]["unresolved_slot_indexes"] == ([0] if context_rejected else [])
    if context_rejected:
        assert fitted["critic"]["verdict"] == "revise"


def test_missing_context_cannot_early_return_a_false_pass_with_two_primary_beats():
    selection, beats = context_selection()
    selection["keep_beat_ids"] = ["result", "unselected"]
    selection["slot_map"] = [{"slot_index": 0, "beat_ids": ["result", "unselected"]}]
    selection["critic"] = {"verdict": "pass", "issues": [], "selection_before": ["result", "unselected"],
                           "post_review_beat_ids": ["result", "unselected"],
                           "requested_added": [], "requested_removed": []}
    fitted = intelligence._fit_story_selection_to_budget(selection, beats, {"slots": [
        {"chapter_ids": ["primary"], "required_context_chapter_ids": ["prerequisite"]},
    ]}, 20, [{"id": "primary", "beats": beats[1:]}, {"id": "prerequisite", "beats": beats[:1]}])
    assert "context" not in fitted["keep_beat_ids"]
    assert fitted["critic"]["unresolved_slot_indexes"] == [0]
    assert fitted["critic"]["verdict"] == "revise"


def test_two_context_beats_cannot_stand_in_for_a_missing_primary_slot():
    beats = [{"id": "primary", "start": 0, "end": 8, "segment_ids": ["s1"], "text": "The primary idea."},
             {"id": "context1", "start": 12, "end": 16, "segment_ids": ["s2"], "text": "Prerequisite context."},
             {"id": "context2", "start": 20, "end": 24, "segment_ids": ["s3"], "text": "Additional context."}]
    selected = ["context1", "context2"]
    selection = {
        "keep_beat_ids": selected,
        "slot_map": [{"slot_index": 0, "beat_ids": selected}],
        "critic": {"verdict": "pass", "issues": [], "selection_before": selected,
                   "post_review_beat_ids": selected, "requested_added": [], "requested_removed": []},
    }
    fitted = intelligence._fit_story_selection_to_budget(selection, beats, {"slots": [
        {"chapter_ids": ["primary"], "required_context_chapter_ids": ["context"]},
    ]}, 20, [{"id": "primary", "beats": beats[:1]}, {"id": "context", "beats": beats[1:]}])

    assert "primary" not in fitted["keep_beat_ids"]
    assert fitted["critic"]["unresolved_slot_indexes"] == [0]
    assert fitted["critic"]["verdict"] == "revise"
    decision = intelligence._story_decision_from_beats(fitted, beats, [{"id": f"s{i}"} for i in (1, 2, 3)])
    assert decision["story_requirements"]["unresolved_slot_indexes"] == [0]
    assert "primary" not in decision["story_requirements"]["required_beat_ids"]


@pytest.mark.parametrize("slot_count,complete,accepted", [(1, True, True), (1, False, False), (2, True, True)])
def test_one_complete_source_unit_can_be_cited_by_multiple_provisional_roles(monkeypatch, slot_count, complete, accepted):
    from cutroom.story_evidence import build_story_evidence_catalog
    beats = [{"id": f"b{i}", "start": (i - 1) * 12, "end": (i - 1) * 12 + 8,
              "duration": 8, "segment_ids": [f"s{i}"],
              "text": "A complete synthetic idea." if complete else "An unfinished synthetic idea"}
             for i in (1, 2)]
    segments = [{"id": beat["segment_ids"][0], **{k: beat[k] for k in ("start", "end", "text")}} for beat in beats]
    catalog = build_story_evidence_catalog(beats, segments)
    choice = next(f"{row['text']} [{row['id']}]" for row in catalog if row["beat_id"] == "b1")
    plan = {"slots": [{"purpose": f"role{i}", "chapter_ids": ["c1"], "required_context_chapter_ids": [], "desired_seconds": 8}
                      for i in range(slot_count)]}
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: {
        "verdict": "fit", "role_selections": {slot["purpose"]: {
            "primary_anchor_choice": choice, "additional_primary_evidence_choices": [], "context_evidence_choices_by_chapter": {}}
            for slot in plan["slots"]}, "highlight_beat_ids": [], "title": "Synthetic", "summary": "Unverified"})
    args = (Settings(), [{"id": "c1", "beats": beats}], [{"id": "c1"}], {}, plan,
            {"target_duration": 20}, "fixture-model", None, None, segments)
    if accepted:
        selected, _ = intelligence._select_story_beats(*args)
        assert selected["keep_beat_ids"] == ["b1"]
        assert len(selected["slot_map"]) == slot_count
        assert selected["semantic_mapping_verified"] is False
    else:
        with pytest.raises(intelligence.StoryPlanningError, match="invalid precision"):
            intelligence._select_story_beats(*args)


def test_precision_cannot_use_only_context_and_omit_primary_support(monkeypatch):
    from cutroom.story_evidence import build_story_evidence_catalog
    beats = [{"id": "context", "start": 0, "end": 8, "duration": 8, "segment_ids": ["s1"], "text": "Complete context."},
             {"id": "primary", "start": 10, "end": 18, "duration": 8, "segment_ids": ["s2"], "text": "A complete primary idea."}]
    segments = [{"id": beat["segment_ids"][0], **{k: beat[k] for k in ("start", "end", "text")}} for beat in beats]
    row = build_story_evidence_catalog(beats, segments)[0]
    choice = f"{row['text']} [{row['id']}]"
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: {
        "verdict": "fit", "role_selections": {"result": {"primary_anchor_choice": choice,
            "additional_primary_evidence_choices": [], "context_evidence_choices_by_chapter": {"c2": [choice]}}},
        "highlight_beat_ids": [], "title": "Synthetic", "summary": "Unverified"})
    with pytest.raises(intelligence.StoryPlanningError, match="invalid precision"):
        intelligence._select_story_beats(Settings(),
            [{"id": "c1", "beats": beats[1:]}, {"id": "c2", "beats": beats[:1]}],
            [{"id": "c1"}, {"id": "c2"}], {}, {"slots": [
                {"purpose": "result", "chapter_ids": ["c1"], "required_context_chapter_ids": ["c2"]},
            ]}, {"target_duration": 20}, "fixture-model", segments=segments)
