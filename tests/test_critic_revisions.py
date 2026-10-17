from __future__ import annotations

import copy

import pytest

from cutroom import director, intelligence


@pytest.fixture(autouse=True)
def _no_real_story_transport(monkeypatch):
    def forbid(*_args, **_kwargs):
        raise AssertionError("Critic unit tests must stub every model request.")
    monkeypatch.setattr(intelligence, "open_ollama", forbid)


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


def verified_story_fixture(selection, candidates):
    for row in candidates:
        row["text"] = "A complete fixture story idea."
    selection["semantic_mapping_verified"] = True
    selection["semantic_review_status"] = "model_reviewed"
    selection["evidence_policy_version"] = intelligence.EVIDENCE_POLICY_VERSION
    selection["slot_map"] = [{"slot_index": index, "purpose": purpose, "beat_ids": [identifier],
                              "primary_beat_ids": [identifier], "context_beat_ids": [],
                              "role_evidence": "The complete fixture sentence supplies this planned role."}
                             for index, (purpose, identifier) in enumerate((("setup", "b1"), ("result", "b3")))]
    source = [{"id": f"s{index}", "start": beat["start"], "end": beat["end"], "text": beat["text"]}
              for index, beat in enumerate(candidates, 1)]
    catalog = intelligence.build_story_evidence_catalog(candidates, source)
    for row in selection["slot_map"]:
        citation = next(reference["id"] for reference in catalog if reference["beat_id"] == row["primary_beat_ids"][0])
        row.update(primary_evidence_ids=[citation], context_evidence_ids=[], temporal_witness_id=citation)
    proof = intelligence.validate_story_evidence(selection["slot_map"], candidates, source, selected_beat_ids=selection["keep_beat_ids"])
    selection.update(slot_map=proof["slot_map"], evidence_proof=proof)
    return {"slots": [{"purpose": purpose, "chapter_ids": ["c001"], "required_context_chapter_ids": []}
                       for purpose in ("setup", "result")]}


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


def test_rejected_required_slot_is_exposed_without_restoring_its_material(monkeypatch, story):
    selection, candidates = story
    selection["keep_beat_ids"] = ["b1", "b2", "b3"]
    selection["slot_map"] = [{"slot_index": i, "beat_ids": [row["id"]]}
                             for i, row in enumerate(candidates)]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["removed"] == ["b2"]
    assert reviewed["critic"]["unapplied_actions"] == []
    assert reviewed["critic"]["unresolved_slot_indexes"] == [1]
    review = director._edit_quality_review({}, {"critic": reviewed["critic"]}, [], [], 30)
    assert review["needs_review"] is True
    assert all(row["type"] == "story_review" for row in review["warnings"])


def test_effective_nonessential_removal_is_recorded_exactly(monkeypatch, story):
    story[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["removed"] == ["b2"]
    assert reviewed["critic"]["unapplied_actions"] == []
    assert reviewed["critic"]["verdict"] == "revise"


def test_later_budget_fit_preserves_a_requested_context_addition(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(add_beat_ids=["b2"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert reviewed["critic"]["added"] == ["b2"]
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, story[1], {"slots": [{"desired_seconds": 8}] * 2}, 16,
    )
    assert fitted["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert fitted["critic"]["requested_added"] == ["b2"]
    assert fitted["critic"]["added"] == ["b2"]
    assert fitted["critic"]["unapplied_actions"] == []
    assert fitted["budget_fit"]["status"] == "required_material_exceeds_ceiling"


def test_adding_an_existing_selected_beat_is_not_an_applied_repair(monkeypatch, story):
    reviewed = critic(monkeypatch, story, response(add_beat_ids=["b1"]))
    assert reviewed["keep_beat_ids"] == ["b1", "b3"]
    assert reviewed["critic"]["added"] == []
    assert reviewed["critic"]["unapplied_actions"] == [
        {"action": "add", "beat_id": "b1", "reason": "already_selected"},
    ]


def test_later_budget_slot_restoration_keeps_actual_removal(monkeypatch, story):
    story[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    assert reviewed["critic"]["removed"] == ["b2"]
    reviewed["slot_map"] = [{"slot_index": i, "beat_ids": [row["id"]]}
                            for i, row in enumerate(story[1])]
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, story[1], {"slots": [{"desired_seconds": 8}] * 3}, 30,
    )
    assert fitted["keep_beat_ids"] == ["b1", "b3"]
    assert fitted["critic"]["requested_removed"] == ["b2"]
    assert fitted["critic"]["removed"] == ["b2"]
    assert fitted["critic"]["unapplied_actions"] == []
    assert fitted["critic"]["unresolved_slot_indexes"] == [1]


def test_empty_critic_response_requires_bounded_review_before_applying_story(monkeypatch, story):
    selection, candidates = story
    plan = verified_story_fixture(selection, candidates)
    segments = [{"id": f"s{i}", "start": row["start"], "end": row["end"], "text": row["text"]}
                for i, row in enumerate(candidates, 1)]
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"fixture-model"}))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [{"id": "c001"}])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: plan)
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (copy.deepcopy(selection), candidates))
    calls = []
    def respond(_settings, payload, *_args):
        calls.append(payload)
        if "continuity critic" in payload["messages"][0]["content"]:
            return {}
        return {"verdict": "fit", "keep_beat_ids": ["b1", "b3"], "released_optional_beat_ids": [],
                "role_selections": {row["purpose"]: {key: row[key] for key in
                    ("primary_evidence_ids", "context_evidence_ids", "temporal_witness_id")}
                    for row in selection["slot_map"]}}
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    decision, hierarchy = intelligence.hierarchical_story_edit(
        candidates, segments, Settings(), {"goal": "short", "duration_mode": "style", "target_duration": 30},
    )
    assert decision["story_beat_ids"] == ["b1", "b3"]
    assert len(calls) == 2
    assert hierarchy["critic"]["verdict"] == "pass"
    assert hierarchy["critic"]["original_review"]["verdict"] == "skipped"
    review = director._edit_quality_review({}, hierarchy, segments, decision["story_ranges"], 30)
    assert review["needs_review"] is False


def test_story_endpoints_and_highlights_cannot_inject_unselected_beats(story):
    selection, candidates = story
    selection.update(keep_beat_ids=["b2"], opening_beat_id="b1", closing_beat_id="b3",
                     highlight_beat_ids=["b1", "b2", "b3"])
    segments = [{"id": f"s{i}"} for i in range(1, 4)]

    decision = intelligence._story_decision_from_beats(selection, candidates, segments)

    assert decision["story_beat_ids"] == ["b2"]
    assert decision["opening_id"] == decision["closing_id"] == "s2"
    assert decision["highlight_ids"] == ["s2"]


def test_budget_fit_cannot_substitute_an_unselected_chapter_alternative(story):
    selection, candidates = story
    candidates[0].update(end=20.0)
    candidates[1].update(editorial_score=1.0, text="An unrelated alternative.")
    candidates[2].update(end=40.0)
    chapters = [{"id": "c1", "beats": candidates[:2]}, {"id": "c2", "beats": candidates[2:]}]
    plan = {"slots": [{"chapter_ids": ["c1"], "desired_seconds": 8},
                      {"chapter_ids": ["c2"], "desired_seconds": 8}]}

    fitted = intelligence._fit_story_selection_to_budget(selection, candidates, plan, 16, chapters)

    assert fitted["keep_beat_ids"] == ["b1", "b3"]


def test_critic_removal_of_a_required_slot_is_not_undone_by_budget_fit(monkeypatch, story):
    selection, candidates = story
    selection["keep_beat_ids"] = ["b1", "b2", "b3"]
    selection["slot_map"] = [{"slot_index": i, "beat_ids": [row["id"]]}
                             for i, row in enumerate(candidates)]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, candidates, {"slots": [{"desired_seconds": 8}] * 3}, 30,
    )

    assert fitted["keep_beat_ids"] == ["b1", "b3"]
    assert fitted["critic"]["removed"] == ["b2"]
    assert fitted["critic"]["unresolved_slot_indexes"] == [1]


def test_rejected_segment_provenance_survives_conversion(monkeypatch, story):
    story[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(remove_beat_ids=["b2"]))
    # Conversion must also defend against a stale slot or extension restoring it.
    reviewed["keep_beat_ids"].append("b2")
    decision = intelligence._story_decision_from_beats(
        reviewed, story[1], [{"id": f"s{i}"} for i in range(1, 4)],
    )

    assert decision["story_beat_ids"] == ["b1", "b3"]
    assert decision["rejected_beat_ids"] == ["b2"]
    assert decision["rejected_segment_ids"] == ["s2"]
    assert decision["rejected_story_ranges"] == [{"start": 10.0, "end": 18.0, "beat_id": "b2"}]


def test_removing_every_selected_beat_is_structurally_invalid(monkeypatch, story):
    with pytest.raises(intelligence.StoryPlanningError, match="no.*material|no.*selection"):
        critic(monkeypatch, story, response(remove_beat_ids=["b1", "b3"]))


def test_later_budget_change_cannot_retain_an_earlier_critic_pass(monkeypatch, story):
    selection, candidates = story
    selection["keep_beat_ids"] = ["b1", "b2", "b3"]
    reviewed = critic(monkeypatch, story, response(verdict="pass", issues=[]))
    fitted = intelligence._fit_story_selection_to_budget(
        reviewed, candidates, {"slots": [{"desired_seconds": 8}] * 2}, 16,
    )

    assert fitted["keep_beat_ids"] == ["b1", "b3"]
    assert fitted["critic"]["reviewed_beat_ids"] == ["b1", "b2", "b3"]
    assert fitted["critic"]["final_beat_ids"] == ["b1", "b3"]
    assert fitted["critic"]["selection_changed_after_review"] is True
    assert fitted["critic"]["verdict"] != "pass"


def test_title_falls_back_when_its_selected_material_changes(story):
    selection, candidates = story
    selection.update(title="The original suggested title", title_beat_ids=["b1", "b2", "b3"])

    decision = intelligence._story_decision_from_beats(
        selection, candidates, [{"id": f"s{i}"} for i in range(1, 4)],
    )

    assert decision["title"] == "CUTROOM story"
    assert decision["title_review"]["status"] == "unverified"
    assert decision["title_review"]["reason"] == "selection_changed"


def test_unchanged_title_provenance_does_not_claim_semantic_verification(story):
    selection, candidates = story
    selection.update(title="A suggested title", title_beat_ids=["b1", "b3"])
    decision = intelligence._story_decision_from_beats(
        selection, candidates, [{"id": f"s{i}"} for i in range(1, 4)],
    )

    assert decision["title"] == "CUTROOM story"
    assert decision["title_review"] == {
        "status": "unverified", "reason": "model_suggestion",
        "selected_beat_ids": ["b1", "b3"], "title_beat_ids": ["b1", "b3"],
    }


def test_explicitly_empty_critic_selection_cannot_fall_back_to_rejected_story(monkeypatch, story):
    selection, candidates = story
    segments = [{"id": f"s{i}", "start": row["start"], "end": row["end"]}
                for i, row in enumerate(candidates, 1)]
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"fixture-model"}))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [{"id": "c001"}])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: {"slots": []})
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (copy.deepcopy(selection), candidates))
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass",
                        lambda *_args: response(remove_beat_ids=["b1", "b3"]))

    with pytest.raises(intelligence.StoryPlanningError, match="no selected source material"):
        intelligence.hierarchical_story_edit(
            candidates, segments, Settings(), {"goal": "short", "target_duration": 30},
        )


def test_hierarchy_saves_final_selection_and_the_exact_reviewed_input(monkeypatch, story):
    selection, candidates = story
    plan = verified_story_fixture(selection, candidates)
    segments = [{"id": f"s{i}", "start": row["start"], "end": row["end"], "text": row["text"]}
                for i, row in enumerate(candidates, 1)]
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"fixture-model"}))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [{"id": "c001"}])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: plan)
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (copy.deepcopy(selection), candidates))
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_args: response(verdict="pass", issues=[]))

    decision, hierarchy = intelligence.hierarchical_story_edit(
        candidates, segments, Settings(), {"goal": "short", "duration_mode": "style", "target_duration": 30},
    )

    assert hierarchy["selection"]["keep_beat_ids"] == decision["story_beat_ids"] == ["b1", "b3"]
    assert hierarchy["selection"]["slot_map"] == selection["slot_map"]
    assert hierarchy["critic"]["reviewed_beat_ids"] == hierarchy["critic"]["final_beat_ids"] == ["b1", "b3"]
    assert hierarchy["critic"]["selection_changed_after_review"] is False


def test_an_unresolved_required_slot_invalidates_a_critic_pass_without_id_changes(story):
    selection, _ = story
    selection["slot_map"].append({"slot_index": 2, "beat_ids": ["b2"]})
    selection["critic"] = {"verdict": "pass", "issues": [], "selection_before": ["b1", "b3"],
                           "post_review_beat_ids": ["b1", "b3"],
                           "requested_added": [], "requested_removed": []}

    reconciled = intelligence._reconcile_critic_actions(selection)

    assert reconciled["critic"]["selection_changed_after_review"] is False
    assert reconciled["critic"]["unresolved_slot_indexes"] == [2]
    assert reconciled["critic"]["verdict"] == "revise"
    assert any("slot" in issue for issue in reconciled["critic"]["issues"])


def test_selected_ids_cannot_ground_an_unsupported_generated_title(story):
    selection, candidates = story
    selection.update(title="An unsupported invented claim", title_beat_ids=["b1", "b3"])
    candidates[0]["text"] = "A synthetic setup about an ordinary task."
    candidates[2]["text"] = "The task has a modest result."

    decision = intelligence._story_decision_from_beats(
        selection, candidates, [{"id": f"s{i}"} for i in range(1, 4)],
    )

    assert decision["title"] == "CUTROOM story"
    assert decision["title_review"]["status"] == "unverified"
    assert decision["title_review"]["reason"] == "model_suggestion"
