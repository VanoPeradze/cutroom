from __future__ import annotations

import copy

import pytest

from cutroom import director, intelligence


class Settings:
    ai = {"enabled": True, "editor_model": "fixture-model", "editor_fallback_models": []}


@pytest.fixture
def story():
    candidates = [{"id": f"b{i}", "start": float((i - 1) * 10),
                   "end": float((i - 1) * 10 + 8), "segment_ids": [f"s{i}"]}
                  for i in range(1, 4)]
    selection = {"keep_beat_ids": ["b1", "b3"], "highlight_beat_ids": [],
                 "opening_beat_id": "b1", "closing_beat_id": "b3",
                 "slot_map": [{"slot_index": 0, "beat_ids": ["b1"]},
                              {"slot_index": 1, "beat_ids": ["b3"]}]}
    return selection, candidates


def response(**patch):
    return {"verdict": "revise", "add_beat_ids": [], "remove_beat_ids": [],
            "issues": ["continuity"], "summary": "", **patch}


def critic(monkeypatch, story, reply):
    selection, candidates = story
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: reply)
    return intelligence._critic_story_selection(
        Settings(), selection, candidates, {}, {}, {"target_duration": 30}, "fixture-model",
    )


@pytest.mark.parametrize("reply", [
    {}, None, {"verdict": "pass"}, response(verdict="unknown"), response(verdict={}),
    response(add_beat_ids=None), response(remove_beat_ids="b2"),
    response(issues=[{}]), response(summary=None), response(remove_beat_ids=["unknown"]),
    response(add_beat_ids=["b2"], remove_beat_ids=["b2"]),
    response(verdict="pass"), response(verdict="pass", issues=[], remove_beat_ids=["b1"]),
])
def test_malformed_or_contradictory_critic_cannot_become_a_pass(monkeypatch, story, reply):
    with pytest.raises(intelligence.StoryPlanningError):
        critic(monkeypatch, story, reply)


def test_valid_pass_preserves_story_without_invented_actions(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(verdict="pass", issues=[]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["verdict"] == "pass"
    assert reviewed["critic"]["added"] == reviewed["critic"]["removed"] == []
    assert reviewed["critic"]["unapplied_actions"] == []


def test_removing_an_unselected_candidate_is_a_noop_not_an_applied_repair(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["requested_removed"] == ["b2"]
    assert reviewed["critic"]["removed"] == []
    assert reviewed["critic"]["unapplied_actions"] == [
        {"action": "remove", "beat_id": "b2", "reason": "not_selected"},
    ]


def test_required_story_slot_retained_without_claiming_critic_removal(monkeypatch, story):
    selection, candidates = story
    selection["keep_beat_ids"] = ["b1", "b2", "b3"]
    selection["slot_map"] = [{"slot_index": i, "beat_ids": [row["id"]]}
                             for i, row in enumerate(candidates)]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert reviewed["critic"]["removed"] == []
    assert reviewed["critic"]["unapplied_actions"] == [
        {"action": "remove", "beat_id": "b2", "reason": "retained_in_final_selection"},
    ]
    review = director._edit_quality_review({}, {"critic": reviewed["critic"]}, [], [], 30)
    assert review["needs_review"] is True
    assert all(row["type"] == "story_review" for row in review["warnings"])
    assert any("not applied" in row["message"] for row in review["warnings"])


def test_effective_nonessential_removal_is_recorded_exactly(monkeypatch, story):
    story[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["removed"] == ["b2"]
    assert reviewed["critic"]["unapplied_actions"] == []
    assert reviewed["critic"]["verdict"] == "revise"


def test_later_budget_pruning_reconciles_a_requested_context_addition(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(add_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert reviewed["critic"]["added"] == ["b2"]
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, story[1], {"slots": [{"desired_seconds": 8}] * 2}, 16,
    )
    assert fitted["keep_beat_ids"] == ["b1", "b3"]
    assert fitted["critic"]["requested_added"] == ["b2"]
    assert fitted["critic"]["added"] == []
    assert fitted["critic"]["unapplied_actions"] == [
        {"action": "add", "beat_id": "b2", "reason": "not_kept_in_final_selection"},
    ]


def test_adding_an_existing_selected_beat_is_not_an_applied_repair(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(add_beat_ids=["b1"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["added"] == []
    assert reviewed["critic"]["unapplied_actions"] == [
        {"action": "add", "beat_id": "b1", "reason": "already_selected"},
    ]


def test_later_budget_slot_restoration_reconciles_actual_removal(monkeypatch, story):
    story[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["critic"]["removed"] == ["b2"]
    reviewed["slot_map"] = [{"slot_index": i, "beat_ids": [row["id"]]}
                            for i, row in enumerate(story[1])]
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, story[1], {"slots": [{"desired_seconds": 8}] * 3}, 30,
    )
    assert fitted["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert fitted["critic"]["requested_removed"] == ["b2"]
    assert fitted["critic"]["removed"] == []
    assert fitted["critic"]["unapplied_actions"] == [
        {"action": "remove", "beat_id": "b2", "reason": "retained_in_final_selection"},
    ]


def test_empty_critic_response_keeps_edit_with_review_warning_through_real_pipeline(monkeypatch, story):
    selection, candidates = story
    segments = [{"id": f"s{i}", "start": row["start"], "end": row["end"]}
                for i, row in enumerate(candidates, 1)]
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"fixture-model"}))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [{"id": "c001"}])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: {"slots": []})
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (copy.deepcopy(selection), candidates))
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: {})
    decision, hierarchy = intelligence.hierarchical_story_edit(
        candidates, segments, Settings(), {"goal": "short", "target_duration": 30},
    )
    assert decision["story_beat_ids"] == ["b1", "b3"]
    assert hierarchy["critic"]["verdict"] == "skipped"
    review = director._edit_quality_review({}, hierarchy, segments, decision["story_ranges"], 30)
    assert review["needs_review"] is True
    assert review["warnings"][0]["type"] == "story_review"


def test_budget_fit_does_not_invent_an_unselected_topic_to_fill_a_slot():
    beats = [
        {"id": "setup", "start": 0, "end": 30, "text": "The connected setup.", "editorial_score": .7},
        {"id": "outcome", "start": 100, "end": 120, "text": "The complete related outcome.", "editorial_score": .7},
        {"id": "advert", "start": 200, "end": 225, "text": "A different topic with a perfect duration fit.", "editorial_score": 1.0},
    ]
    plan = {"slots": [
        {"chapter_ids": ["a"], "desired_seconds": 15},
        {"chapter_ids": ["b"], "desired_seconds": 25, "purpose": "payoff"},
    ]}
    selection = {"keep_beat_ids": ["setup", "outcome"], "slot_map": [
        {"slot_index": 0, "beat_ids": ["setup"]},
        {"slot_index": 1, "beat_ids": ["outcome"]},
    ]}
    chapters = [{"id": "a", "beats": beats[:1]}, {"id": "b", "beats": beats[1:]}]
    fitted = intelligence._fit_story_selection_to_budget(selection, beats, plan, 40, chapters)
    assert fitted["keep_beat_ids"] == ["setup", "outcome"]
    assert "advert" not in fitted["keep_beat_ids"]


def test_budget_fit_honors_critic_replacement_instead_of_restoring_rejected_closure():
    beats = [
        {"id": "setup", "start": 0, "end": 20, "text": "Setup with relevant context."},
        {"id": "outcome", "start": 50, "end": 72, "text": "A complete related outcome."},
        {"id": "unrelated", "start": 100, "end": 130, "text": "Unrelated banter."},
    ]
    plan = {"slots": [
        {"chapter_ids": ["a"], "desired_seconds": 20},
        {"chapter_ids": ["b"], "desired_seconds": 30, "purpose": "payoff"},
    ]}
    selection = {"keep_beat_ids": ["setup", "outcome", "unrelated"], "slot_map": [
        {"slot_index": 0, "beat_ids": ["setup"]},
        {"slot_index": 1, "beat_ids": ["unrelated"]},
    ], "critic": {"verdict": "revise", "selection_before": ["setup", "unrelated"],
                   "requested_added": ["outcome"], "requested_removed": ["unrelated"]}}
    chapters = [{"id": "a", "beats": beats[:1]}, {"id": "b", "beats": beats[1:]}]
    fitted = intelligence._fit_story_selection_to_budget(selection, beats, plan, 50, chapters)
    assert fitted["keep_beat_ids"] == ["setup", "outcome"]
    assert fitted["closing_beat_id"] == "outcome"
    assert fitted["critic"]["added"] == ["outcome"]
    assert fitted["critic"]["removed"] == ["unrelated"]
    assert fitted["critic"]["unapplied_actions"] == []


def test_critic_action_schema_keeps_alternatives_and_prose_independent(monkeypatch, story):
    captured = {}
    def respond(_settings, payload, *_args):
        captured.update(payload)
        return response(verdict="pass", issues=[])
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    intelligence._critic_story_selection(Settings(), story[0], story[1], {}, {}, {"target_duration": 30}, "fixture")
    schema = captured["format"]["properties"]
    assert schema["add_beat_ids"]["items"]["enum"] == ["b1", "b2", "b3"]
    assert schema["remove_beat_ids"]["items"]["enum"] == ["b1", "b3"]
    assert "enum" not in schema["issues"]["items"]
    assert "enum" not in intelligence.STORY_CRITIC_SCHEMA["properties"]["add_beat_ids"]["items"]
