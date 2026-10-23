"""Mechanical Director regressions, never evidence of model/editorial quality.

The existing fixture supplies synthetic ASR and a stub planner. These cases keep
the actual cleanup, manual overrides, continuity validator and atomic save path.
No source media is decoded and no model or network transport is permitted.
"""
from __future__ import annotations

import copy
import socket
import urllib.request

import pytest

from cutroom import ai_runtime, director, intelligence
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.story_budget import StoryBudgetError, StoryPlanningError
from test_director_rebuild_cache import (  # Shared isolated orchestration fixture.
    _attach_source_proof, _required_story_editorial, semantic_project,
)


NO_CUTS = [
    pytest.param("Keep the selected source passage without internal cuts. Preserve natural pauses.", id="en"),
    pytest.param("\u05e9\u05de\u05d5\u05e8 \u05e2\u05dc \u05e7\u05d8\u05e2 \u05d4\u05de\u05e7\u05d5\u05e8 \u05d1\u05dc\u05d9 \u05d7\u05d9\u05ea\u05d5\u05db\u05d9\u05dd. \u05e9\u05de\u05d5\u05e8 \u05e2\u05dc \u05d4\u05d4\u05e4\u05e1\u05e7\u05d5\u05ea \u05d4\u05d8\u05d1\u05e2\u05d9\u05d5\u05ea.", id="he"),
]
ONE_IDEA = [
    pytest.param("Choose one coherent source passage.", id="en"),
    pytest.param("\u05d1\u05d7\u05e8 \u05e7\u05d8\u05e2 \u05d0\u05d7\u05d3 \u05e2\u05dd \u05e8\u05e2\u05d9\u05d5\u05df \u05d1\u05e8\u05d5\u05e8.", id="he"),
]
SPAN = [{"start": 30.0, "end": 60.0}]


@pytest.fixture(autouse=True)
def no_real_model_or_transport(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("These synthetic orchestration tests must not start a model or network transport")

    monkeypatch.setattr(intelligence, "open_ollama", forbidden)
    monkeypatch.setattr(ai_runtime, "open_ollama", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(director, "cuda_available", lambda *_args, **_kwargs: False)


def selected_span(monkeypatch):
    """Fix a synthetic planner selection; leave downstream implementation real."""
    policies = []

    def select(*_args, **kwargs):
        policies.append(copy.deepcopy(kwargs["selection_policy"]))
        return copy.deepcopy(SPAN)

    monkeypatch.setattr(director, "_select_short_story_ranges", select)
    # This is within the real fixture's 38..40 second transcript pause.
    monkeypatch.setattr(director, "build_audio_actions", lambda *_args, **_kwargs: (
        [{"start": 38.1, "end": 39.9, "reason": "silence", "priority": 1}], [], {},
    ))
    monkeypatch.setattr(director, "_build_reel_candidates", lambda *_args, **_kwargs: [])
    return policies


def request(instruction):
    return {"instruction": instruction, "target_duration": 30, "duration_mode": "target", "fps": 30}


@pytest.mark.parametrize("instruction", NO_CUTS)
def test_explicit_no_cuts_keeps_source_pauses_and_bypasses_advisory_cleanup(
    semantic_project, monkeypatch, instruction,
):
    store, settings, project_id, _calls, context = semantic_project
    policies = selected_span(monkeypatch)
    source = store.project_dir(project_id) / "media/source-A.mp4"
    original = source.read_bytes()

    def forbidden_cleanup(*_args, **_kwargs):
        pytest.fail("An explicit no-internal-cuts request must bypass advisory cut/target/pause cleanup")

    for name in ("_short_cleanup_cuts_with_floor", "_cut_dead_screens", "_enforce_short_target",
                 "_drop_isolated_micro_keeps", "_compact_story_pauses_to_target"):
        monkeypatch.setattr(director, name, forbidden_cleanup)
    job_context = context()
    result = director.analyze_project(job_context, project_id, store, settings, request(instruction))

    saved = store.load(project_id)
    draft = saved["draft"]
    assert policies and all(policy["preserve_source_continuity"] is True for policy in policies)
    assert draft["keep_ranges"] == SPAN
    assert draft["output_duration"] == pytest.approx(30)
    assert any(row["start"] <= 38 and row["end"] >= 40 for row in draft["keep_ranges"])
    proof = draft["instruction_contract"]["source_continuity_proof"]
    assert proof["status"] == "fulfilled" and proof["source_continuity_verified"] is True
    assert proof["verification_scope"] == "proposed_director_draft"
    assert proof["mechanical_only"] is True
    assert proof["semantic_coherence_verified"] is False and proof["final_export_verified"] is False
    assert draft["generative_approved"] is False
    assert saved["settings"]["instruction"] == instruction
    assert result["instruction_contract"] == draft["instruction_contract"]
    assert job_context.committed is True
    assert source.read_bytes() == original


@pytest.mark.parametrize("instruction", NO_CUTS)
def test_conflicting_manual_cut_refuses_new_draft_and_preserves_saved_state(
    semantic_project, monkeypatch, instruction,
):
    store, settings, project_id, _calls, context = semantic_project
    selected_span(monkeypatch)

    def manual_edit(current):
        current["manual"]["cuts"] = [{"start": 43.0, "end": 45.0}]
        current["manual"]["_history"] = {"undo": [{"action": "saved-cut"}], "redo": [{"action": "saved-redo"}]}
        current["manual"]["history"] = {"undo_count": 1, "redo_count": 1}

    store.update(project_id, manual_edit)
    before = copy.deepcopy(store.load(project_id))
    original_state = store.state_path(project_id).read_bytes()
    source = store.project_dir(project_id) / "media/source-A.mp4"
    original_source = source.read_bytes()
    job_context = context()
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(job_context, project_id, store, settings, request(instruction))

    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "explicit_source_continuity_conflict"
    assert diagnostic["outcome"] == "constraint_conflict"
    assert diagnostic["violation"] == "noncontiguous_source_ranges"
    assert diagnostic["applied_to_timeline"] is False
    assert diagnostic["verification_scope"] == "proposed_director_draft"
    assert job_context.committed is False
    assert store.load(project_id) == before
    assert store.state_path(project_id).read_bytes() == original_state
    assert source.read_bytes() == original_source


@pytest.mark.parametrize("instruction", ONE_IDEA)
def test_one_coherent_idea_does_not_silently_forbid_measured_pause_cuts(
    semantic_project, monkeypatch, instruction,
):
    store, settings, project_id, _calls, context = semantic_project
    policies = selected_span(monkeypatch)
    result = director.analyze_project(context(), project_id, store, settings, request(instruction))

    assert policies and all(policy["preserve_source_continuity"] is False for policy in policies)
    assert result["draft"]["keep_ranges"] == [
        {"start": 30.0, "end": 38.1}, {"start": 39.9, "end": 60.0},
    ]
    assert result["draft"]["output_duration"] == pytest.approx(28.2)
    proof = result["draft"]["instruction_contract"]["source_continuity_proof"]
    assert proof["status"] == "not_requested" and proof["source_continuity_verified"] is False
    assert proof["semantic_coherence_verified"] is False
    assert result["draft"]["generative_approved"] is False


@pytest.mark.parametrize("instruction", NO_CUTS)
def test_discontinuous_proposal_cannot_reach_request_evaluation_or_commit(
    semantic_project, monkeypatch, instruction,
):
    store, settings, project_id, _calls, context = semantic_project
    selected_span(monkeypatch)
    monkeypatch.setattr(director, "_select_short_story_ranges", lambda *_a, **_k: [
        {"start": 30.0, "end": 40.0}, {"start": 50.0, "end": 60.0},
    ])

    def forbidden_evaluation(*_args, **_kwargs):
        pytest.fail("A provably discontinuous proposal must fail before request evidence is evaluated")

    monkeypatch.setattr(director, "evaluate_instruction_contract", forbidden_evaluation)
    original_state = store.state_path(project_id).read_bytes()
    job_context = context()
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(job_context, project_id, store, settings, request(instruction))
    assert caught.value.diagnostic["reason"] == "explicit_source_continuity_conflict"
    assert job_context.committed is False
    assert store.state_path(project_id).read_bytes() == original_state


@pytest.mark.parametrize("instruction", NO_CUTS)
def test_commit_rechecks_geometry_changed_after_the_first_continuity_proof(
    semantic_project, monkeypatch, instruction,
):
    store, settings, project_id, _calls, context = semantic_project
    selected_span(monkeypatch)
    original_validator = director.validate_explicit_source_continuity
    original_evaluate = director.evaluate_instruction_contract
    observed = []

    def audit(brief, ranges, duration):
        observed.append(copy.deepcopy(ranges))
        return original_validator(brief, ranges, duration)

    def downstream_change(*args, **kwargs):
        report = original_evaluate(*args, **kwargs)
        # Simulate a later assembly step altering the same proposed keep list.
        # The save gate must validate the actual new geometry, not its old proof.
        kwargs["source_ranges"][:] = [{"start": 30.0, "end": 38.0}, {"start": 40.0, "end": 60.0}]
        return report

    monkeypatch.setattr(director, "validate_explicit_source_continuity", audit)
    monkeypatch.setattr(director, "evaluate_instruction_contract", downstream_change)
    original_state = store.state_path(project_id).read_bytes()
    job_context = context()
    with pytest.raises(StoryPlanningError) as caught:
        director.analyze_project(job_context, project_id, store, settings, request(instruction))

    assert caught.value.diagnostic["reason"] == "explicit_source_continuity_conflict"
    assert observed == [SPAN, [{"start": 30.0, "end": 38.0}, {"start": 40.0, "end": 60.0}]]
    assert job_context.committed is False
    assert store.state_path(project_id).read_bytes() == original_state


@pytest.mark.parametrize("instruction", NO_CUTS)
def test_explicit_continuity_is_priced_as_whole_source_time_not_only_speech(instruction):
    # This synthetic proof is only a prerequisite for exercising the independent
    # duration gate. A fabricated fixture critic is not a real semantic pass.
    editorial = _required_story_editorial([("one", 30.0, 60.0)])
    segment = editorial["segments"][0]
    segment.update(text="Start. Finish.", words=[
        {"start": 30.0, "end": 35.0, "word": "Start."},
        {"start": 55.0, "end": 60.0, "word": "Finish."},
    ])
    editorial["story_beats"][0].update(copy.deepcopy(segment))
    _attach_source_proof(editorial)
    base_brief = {"goal": "short", "edit_style": "smart", "target_duration": 20, "duration_mode": "target"}
    generic_policy = enrich_brief_with_style({**base_brief, "instruction": "Choose one coherent source passage."})["style_profile"]["selection_policy"]
    continuous_policy = enrich_brief_with_style({**base_brief, "instruction": instruction})["style_profile"]["selection_policy"]
    baseline = director._validate_required_story_selection(
        editorial["decision"], editorial["segments"], 300.0, 20.0,
        selection_policy=generic_policy, hierarchy=editorial["story_hierarchy"], fps=30,
    )
    assert baseline["cost"]["approved_seconds"] == 30
    assert baseline["cost"]["minimum_safe_seconds"] < 20
    assert baseline["cost"]["protect_action_span"] is False
    with pytest.raises(StoryBudgetError) as caught:
        director._validate_required_story_selection(
            editorial["decision"], editorial["segments"], 300.0, 20.0,
            selection_policy=continuous_policy, hierarchy=editorial["story_hierarchy"], fps=30,
        )
    diagnostic = caught.value.diagnostic
    assert diagnostic["cost"]["protect_action_span"] is True
    assert diagnostic["required_policy_minimum_seconds"] == 30
    assert diagnostic["cost"]["removable_pause_seconds"] == 0
    assert diagnostic["reasons"] == ["insufficient_safe_pause_budget"]
    assert diagnostic["outcome"] == "constraint_conflict" and diagnostic["applied_to_timeline"] is False
