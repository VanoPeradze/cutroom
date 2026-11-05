from __future__ import annotations

import copy
import socket
import threading
import urllib.request

import pytest

from cutroom import ai_runtime, director, intelligence, story_evidence, story_spans
from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom.projects import ProjectStore
from cutroom.story_budget import POLICY_VERSION, StoryBudgetError
from cutroom.vision import VISION_ANALYSIS_VERSION


@pytest.fixture(autouse=True)
def no_model_transport(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("Extractive integration tests must not call model transport.")

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", forbidden)
    monkeypatch.setattr(intelligence, "open_ollama", forbidden)
    monkeypatch.setattr(ai_runtime, "open_ollama", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def source_fixture():
    rows = [
        ("b1", 0.0, 3.0, "This rejected passage must stay excluded."),
        ("b2", 5.0, 10.0, "Participation is not required."),
        ("b3", 12.0, 17.0, "The effect is cosmetic only."),
        ("b4", 20.0, 25.0, "This optional passage was never selected."),
    ]
    candidates, segments = [], []
    for identifier, start, end, text in rows:
        segment_id = "s" + identifier[1:]
        segments.append({"id": segment_id, "start": start, "end": end, "text": text})
        candidates.append({"id": identifier, "start": start, "end": end,
                           "duration": end - start, "segment_ids": [segment_id], "text": text})
    selection = {
        "keep_beat_ids": ["b2"], "slot_map": [],
        "critic": {"verdict": "revise", "review_verdict": "revise",
                   "issues": ["The generated story roles remain unverified."],
                   "requested_added": ["b3"], "requested_removed": ["b1"],
                   "reviewed_beat_ids": ["b1", "b2"], "unapplied_actions": [],
                   "unresolved_slot_indexes": [1]},
    }
    chapters = [{"id": "c1", "beats": candidates[1:3]},
                {"id": "unused", "beats": [candidates[0], candidates[3]]}]
    plan = {"slots": [{"purpose": purpose, "chapter_ids": ["c1"],
                       "required_context_chapter_ids": ["c1"]}
                      for purpose in ("premise", "result")]}
    brief = {"goal": "short", "duration_mode": "target", "target_duration": 10,
             "allow_extractive_rough_cut": True}
    return selection, candidates, segments, chapters, plan, brief


def generation_failure(reason="planner_no_fit", *, attempts=1):
    return StoryBudgetError("The generated proposal was not approved.", {
        "kind": "story_budget", "reason": reason, "scope": "current_required_selection",
        "semantic_revision": {"attempts": attempts, "verdict": "no_fit"},
        "applied_to_timeline": False,
    })


def rough_cut(fixture, failure=None):
    return intelligence._extractive_rough_cut_decision(
        *fixture, failure if failure is not None else generation_failure(),
    )


def test_rough_cut_has_separate_authority_and_preserves_failed_generation():
    fixture = source_fixture()
    failure = generation_failure()
    before = copy.deepcopy(fixture), copy.deepcopy(failure.diagnostic)

    decision = rough_cut(fixture, failure)

    assert decision["editorial_authority"] == "extractive_rough_cut"
    assert decision["semantic_review_status"] == "not_model_reviewed"
    assert decision["generative_approved"] is False
    assert decision["review_required"] is True
    assert decision["title"] == "EXTRACTIVE ROUGH CUT"
    assert "story_requirements" not in decision
    assert not decision.get("semantic_mapping_verified")
    assert director._semantic_mapping_is_verified(decision) is False
    requirements = decision["extractive_requirements"]
    assert requirements["failed_generation_diagnostic"] == failure.diagnostic
    assert requirements["original_critic"] == fixture[0]["critic"]
    assert requirements["original_critic"]["verdict"] == "revise"
    assert requirements["original_critic"]["issues"]
    assert (fixture, failure.diagnostic) == before


def test_rough_cut_retains_only_current_source_and_critic_additions_without_topup():
    fixture = source_fixture()

    decision = rough_cut(fixture)

    assert decision["story_beat_ids"] == ["b2", "b3"]
    assert decision["keep_ids"] == ["s2", "s3"]
    assert decision["extractive_requirements"]["fixed_beat_ids"] == ["b2", "b3"]
    assert decision["extractive_requirements"]["critic_requested_beat_ids"] == ["b3"]
    assert decision["rejected_beat_ids"] == ["b1"]
    assert decision["rejected_story_ranges"] == [{"start": 0.0, "end": 3.0, "beat_id": "b1"}]
    assert decision["story_ranges"] == [
        {"start": 5.0, "end": 10.0, "beat_id": "b2"},
        {"start": 12.0, "end": 17.0, "beat_id": "b3"},
    ]
    assert "Participation is not required." in decision["summary"]
    assert "The effect is cosmetic only." in decision["summary"]
    assert "rejected passage" not in decision["summary"]
    assert "optional passage" not in decision["summary"]


@pytest.mark.parametrize("reason", ["invalid_source_evidence", "invalid_source_selection",
                                   "required_source_missing", "allowed_source_below_target_minimum",
                                   "semantic_revision_failed", "semantic_revision_context_limit"])
def test_ineligible_generation_failures_do_not_enable_rough_authority(reason):
    assert rough_cut(source_fixture(), generation_failure(reason)) is None


@pytest.mark.parametrize("attempts", [0, 2, True, "1", None])
def test_fallback_requires_one_actual_generation_attempt(attempts):
    assert rough_cut(source_fixture(), generation_failure(attempts=attempts)) is None


@pytest.mark.parametrize("opt_in", [False, None, 1, "true"])
def test_rough_cut_requires_explicit_boolean_opt_in(opt_in):
    fixture = source_fixture()
    fixture[-1]["allow_extractive_rough_cut"] = opt_in

    assert rough_cut(fixture) is None


def test_missing_opt_in_cannot_enable_rough_cut():
    fixture = source_fixture()
    fixture[-1].pop("allow_extractive_rough_cut")

    assert rough_cut(fixture) is None


def test_explicit_opt_in_preserves_custom_instruction_without_claiming_coverage():
    fixture = source_fixture()
    instruction = "Keep the explanation of the disputed claim."
    fixture[-1]["instruction"] = instruction

    decision = rough_cut(fixture)

    assert fixture[-1]["instruction"] == instruction
    assert decision["extractive_requirements"]["instruction_coverage"] == "unverified"
    assert decision["review_required"] is True
    assert decision["generative_approved"] is False


@pytest.mark.parametrize("field,value", [
    ("requested_added", ["unknown"]), ("requested_removed", ["unknown"]),
    ("requested_added", ["b3", "b3"]), ("requested_removed", "b1"),
    ("requested_added", [{}]),
])
@pytest.mark.parametrize("authority", [None, "proposal", "final"])
def test_malformed_or_unknown_critic_scope_cannot_enable_fallback(field, value, authority):
    fixture = source_fixture()
    if authority is not None:
        fixture[0]["critic"].update(action_authority=authority, accepted_added=[], accepted_removed=[])
    if authority == "final":
        field = field.replace("requested_", "accepted_")
    fixture[0]["critic"][field] = value

    assert rough_cut(fixture) is None


def test_incomplete_source_unit_cannot_enable_rough_cut():
    fixture = source_fixture()
    fixture[1][1]["start"] += .1

    assert rough_cut(fixture) is None


def test_required_context_outside_fixed_selection_is_not_silently_added():
    fixture = source_fixture()
    fixture[4]["slots"][0]["required_context_chapter_ids"] = ["unused"]

    with pytest.raises(StoryBudgetError) as caught:
        rough_cut(fixture)

    assert caught.value.diagnostic["reason"] == "extractive_required_context_missing"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert fixture[0]["keep_beat_ids"] == ["b2"]


@pytest.mark.parametrize("field,identifier", [("required_context_beat_ids", "b4"),
                                             ("required_context_beat_ids", "b1"),
                                             ("required_context_segment_ids", "s4"),
                                             ("required_context_segment_ids", "s1")])
def test_explicit_source_prerequisite_cannot_expand_fixed_scope(field, identifier):
    fixture = source_fixture()
    fixture[0][field] = [identifier]

    with pytest.raises(StoryBudgetError) as caught:
        rough_cut(fixture)

    assert caught.value.diagnostic["reason"] == "extractive_required_context_missing"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert fixture[0]["keep_beat_ids"] == ["b2"]


@pytest.mark.parametrize("field", ["required_context_beat_ids", "required_context_segment_ids"])
def test_unknown_prerequisite_cannot_enable_rough_cut(field):
    fixture = source_fixture()
    fixture[0][field] = ["unknown"]

    assert rough_cut(fixture) is None


@pytest.mark.parametrize("slots", [None, [], [{}], ["premise"]])
def test_invalid_plan_cannot_enable_rough_cut(slots):
    fixture = source_fixture()
    fixture[4]["slots"] = slots

    assert rough_cut(fixture) is None


@pytest.mark.parametrize("target,reason", [(8, "extractive_source_exceeds_target"),
                                          (20, "allowed_source_below_target_minimum")])
def test_fixed_source_duration_failure_provides_actionable_unchanged_scope(target, reason):
    fixture = source_fixture()
    fixture[-1]["target_duration"] = target

    with pytest.raises(StoryBudgetError) as caught:
        rough_cut(fixture)

    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == reason
    assert diagnostic["scope"] == "current_critic_allowed_source"
    assert diagnostic["required_policy_minimum_seconds"] == pytest.approx(10)
    assert diagnostic["available_complete_source_upper_bound_seconds"] == pytest.approx(10)
    interval = diagnostic["current_source_target_interval"]
    assert interval["scope"] == "unchanged_current_source_selection"
    assert interval["minimum_seconds"] == pytest.approx(10)
    assert interval["maximum_seconds"] == pytest.approx(11.111)
    assert interval["semantic_fit_verified"] is False
    assert interval["requires_frame_validation"] is True
    assert diagnostic["failed_generation_diagnostic"]["reason"] == "planner_no_fit"
    assert diagnostic["applied_to_timeline"] is False


def test_incomplete_word_timing_locks_entire_negated_utterance():
    fixture = source_fixture()
    fixture[2][1]["words"] = [{"word": "Participation", "start": 5.0, "end": 5.5}]

    decision = rough_cut(fixture)
    proof = decision["extractive_requirements"]["source_span_constraints"]

    assert proof["policy_version"] == story_spans.SOURCE_SPAN_POLICY_VERSION
    assert proof["verification_scope"] == "source_retention_only"
    assert proof["required_minimum_ranges"] == [{"start": 5.0, "end": 10.0},
                                                {"start": 12.0, "end": 17.0}]
    assert proof["utterances"][0]["text"] == "Participation is not required."


def stub_hierarchical_inputs(monkeypatch, fixture):
    selection, candidates, segments, chapters, plan, brief = fixture
    chapter_rows = copy.deepcopy(chapters)
    for chapter in chapter_rows:
        chapter.update(start=min(row["start"] for row in chapter["beats"]),
                       end=max(row["end"] for row in chapter["beats"]),
                       beat_ids=[row["id"] for row in chapter["beats"]])
        chapter["duration"] = chapter["end"] - chapter["start"]
    monkeypatch.setattr(intelligence, "_ready_story_model_status", lambda *_args: {
        "selected_model": "synthetic-model", "using_fallback": False,
    })
    monkeypatch.setattr(intelligence, "_model_selection_details", lambda *_args: {"model": "synthetic-model"})
    monkeypatch.setattr(intelligence, "build_story_chapters", lambda *_args, **_kwargs: copy.deepcopy(chapter_rows))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [
        {"id": row["id"], "summary_source": "model"} for row in chapter_rows
    ])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: copy.deepcopy(plan))
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (
        copy.deepcopy(selection), copy.deepcopy(candidates),
    ))
    monkeypatch.setattr(intelligence, "_critic_story_selection", lambda *_args: copy.deepcopy(selection))

    class Settings:
        ai = {"performance_mode": "balanced", "cloud_connection": {"mode": "local"}}

    return lambda: intelligence.hierarchical_story_edit(
        candidates, segments, Settings(), brief,
    )


def test_generation_no_fit_preserves_dirty_critic_under_separate_rough_authority(monkeypatch):
    fixture = source_fixture()
    run = stub_hierarchical_inputs(monkeypatch, fixture)
    failure = generation_failure()
    calls = []

    def fail_generation(*_args):
        calls.append("final_review")
        raise failure

    monkeypatch.setattr(intelligence, "_review_story_target_budget", fail_generation)

    decision, hierarchy = run()

    assert calls == ["final_review"]
    assert decision["editorial_authority"] == "extractive_rough_cut"
    assert hierarchy["critic"] == fixture[0]["critic"]
    assert hierarchy["selection"]["semantic_mapping_verified"] is False
    assert hierarchy["selection"]["semantic_review_status"] == "not_model_reviewed"
    assert hierarchy["failed_generation_diagnostic"] == failure.diagnostic
    assert director._semantic_mapping_is_verified(decision) is False


def test_generation_cancellation_is_preserved_without_attempting_fallback(monkeypatch):
    fixture = source_fixture()
    run = stub_hierarchical_inputs(monkeypatch, fixture)
    cancelled = JobCancelled("Synthetic cancellation during the final review")
    fallback_calls = []

    def cancel_generation(*_args):
        raise cancelled

    monkeypatch.setattr(intelligence, "_review_story_target_budget", cancel_generation)
    monkeypatch.setattr(intelligence, "_extractive_rough_cut_decision",
                        lambda *_args: fallback_calls.append(True))

    with pytest.raises(JobCancelled) as caught:
        run()

    assert caught.value is cancelled
    assert fallback_calls == []


def test_invalid_canonical_source_failure_is_preserved_without_a_rough_cut(monkeypatch):
    fixture = source_fixture()
    run = stub_hierarchical_inputs(monkeypatch, fixture)
    failure = generation_failure("invalid_source_evidence")

    def fail_source(*_args):
        raise failure

    monkeypatch.setattr(intelligence, "_review_story_target_budget", fail_source)

    with pytest.raises(StoryBudgetError) as caught:
        run()

    assert caught.value is failure


def validate_rough(decision, fixture, *, keep_ranges=None, target=10, duration_mode="target"):
    return director._validate_extractive_selection(
        decision, fixture[2], 25, target,
        selection_policy={"duration_mode": duration_mode}, keep_ranges=keep_ranges, fps=30,
    )


def test_director_validates_rough_source_without_granting_generative_approval():
    fixture = source_fixture()
    decision = rough_cut(fixture)
    before = copy.deepcopy(decision)

    initial = validate_rough(decision, fixture)
    final = validate_rough(decision, fixture, keep_ranges=[{"start": 5, "end": 10},
                                                        {"start": 12, "end": 17}])

    assert initial["reasons"] == final["reasons"] == []
    assert final["scope"] == "current_fixed_source_selection"
    assert final["editorial_authority"] == "extractive_rough_cut"
    assert final["semantic_review_status"] == "not_model_reviewed"
    assert decision == before
    assert director._semantic_mapping_is_verified(decision) is False


@pytest.mark.parametrize("keeps,reason", [
    ([{"start": 5, "end": 10}, {"start": 12, "end": 17}, {"start": 20, "end": 25}],
     "unapproved_extractive_source_included"),
    ([{"start": 0, "end": 3}, {"start": 5, "end": 10}, {"start": 12, "end": 17}],
     "rejected_extractive_source_included"),
    ([{"start": 5, "end": 10}, {"start": 5, "end": 10}, {"start": 12, "end": 17}],
     "invalid_source_span_constraints"),
    ([{"start": 12, "end": 17}, {"start": 5, "end": 10}],
     "invalid_source_span_constraints"),
    ([{"start": 5, "end": 5.5}, {"start": 12, "end": 17}],
     "invalid_source_span_constraints"),
])
def test_director_rejects_topup_restored_rejected_source_repeats_and_lost_speech(keeps, reason):
    fixture = source_fixture()
    decision = rough_cut(fixture)

    with pytest.raises(StoryBudgetError) as caught:
        validate_rough(decision, fixture, keep_ranges=keeps, target=20, duration_mode="style")

    assert reason in caught.value.diagnostic["reasons"]
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("fault", ["missing_proof", "changed_utterance", "changed_lock", "fingerprint",
                                   "summary_without_negation", "fixed_optional_growth", "fixed_missing",
                                   "source_timestamp", "source_text", "model_reviewed", "generative_approved"])
def test_director_rejects_forged_source_sidecar_or_authority(fault):
    fixture = source_fixture()
    decision = rough_cut(fixture)
    requirements = decision["extractive_requirements"]
    proof = requirements["source_span_constraints"]
    if fault == "missing_proof":
        requirements.pop("source_span_constraints")
    elif fault == "changed_utterance":
        proof["utterances"][0]["text"] = "Participation is required."
    elif fault == "changed_lock":
        proof["required_minimum_ranges"][0]["end"] = 5.5
    elif fault == "fingerprint":
        proof["source_fingerprint"] = "0" * 64
    elif fault == "summary_without_negation":
        decision["summary"] = decision["summary"].replace("not required", "required")
    elif fault == "fixed_optional_growth":
        requirements["fixed_beat_ids"].append("b4")
    elif fault == "fixed_missing":
        requirements["fixed_beat_ids"].remove("b3")
    elif fault == "source_timestamp":
        fixture[2][1]["start"] += .1
    elif fault == "source_text":
        fixture[2][1]["text"] = "Participation is required."
    elif fault == "model_reviewed":
        decision["semantic_review_status"] = "model_reviewed"
    elif fault == "generative_approved":
        decision["generative_approved"] = True

    with pytest.raises(StoryBudgetError) as caught:
        validate_rough(decision, fixture)

    reasons = caught.value.diagnostic["reasons"]
    assert "invalid_source_span_constraints" in reasons or "invalid_extractive_authority" in reasons
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("target,reason", [(8, "insufficient_safe_pause_budget"),
                                          (20, "allowed_source_below_target_minimum")])
def test_director_independently_checks_fixed_source_duration(target, reason):
    fixture = source_fixture()
    decision = rough_cut(fixture)

    with pytest.raises(StoryBudgetError) as caught:
        validate_rough(decision, fixture, target=target)

    assert reason in caught.value.diagnostic["reasons"]
    assert caught.value.diagnostic["current_source_target_interval"]["semantic_fit_verified"] is False


@pytest.fixture
def rough_project(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("Synthetic rough cut")
    project_id = project["id"]
    source = store.project_dir(project_id) / "media" / "source-A.mp4"
    source.write_bytes(b"synthetic-source")

    def attach(current):
        current["sources"]["A"] = {
            "slot": "A", "name": "synthetic.mp4", "relative_path": "media/source-A.mp4",
            "duration": 25.0, "width": 1920, "height": 1080, "fps": 30,
            "has_audio": True, "size": source.stat().st_size,
        }
        current["settings"].update({"goal": "short", "edit_style": "smart", "target_duration": 10,
                                    "duration_mode": "target", "spoken_language": "en",
                                    "auto_reframe": False, "allow_extractive_rough_cut": True})

    store.update(project_id, attach)
    fixture = source_fixture()
    transcript = {"language": "en", "language_probability": .99, "duration": 25.0,
                  "segments": copy.deepcopy(fixture[2]),
                  "text": " ".join(row["text"] for row in fixture[2]), "words": []}
    calls = {"transcribe": 0, "plan": 0}

    def transcribe(*_args, **_kwargs):
        calls["transcribe"] += 1
        return copy.deepcopy(transcript), None

    def plan(_context, current_segments, _settings, current_brief, **_kwargs):
        calls["plan"] += 1
        selected, candidates, _segments, chapters, story_plan, _brief = copy.deepcopy(fixture)
        decision = intelligence._extractive_rough_cut_decision(
            selected, candidates, current_segments, chapters, story_plan,
            {**current_brief, "allow_extractive_rough_cut": True}, generation_failure(),
        )
        assert decision is not None
        return {"segments": copy.deepcopy(current_segments), "decision": decision,
                "story_beats": candidates, "story_hierarchy": {"critic": selected["critic"]}}, intelligence.EXTRACTIVE_ROUGH_CUT_ENGINE

    monkeypatch.setattr(director, "_transcribe_safely", transcribe)
    monkeypatch.setattr(director, "_plan_edit_with_cancel", plan)
    monkeypatch.setattr(director, "analyze_audio", lambda *_args, **_kwargs: {
        "available": True, "duration": 25.0, "ranges": {},
        "summary": {"silence_threshold_dbfs": -42.0}, "waveform": [],
    })
    monkeypatch.setattr(director, "detect_scenes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(director, "analyze_faces_and_embedded_camera", lambda *_args, **_kwargs: {
        "version": VISION_ANALYSIS_VERSION, "focus_safe": False,
    })
    monkeypatch.setattr(director, "_build_reel_candidates", lambda *_args, **_kwargs: [])

    def context():
        return JobContext(Job("synthetic_rough_job", "director", project_id), threading.Lock())

    def run(patch=None, job_context=None):
        return director.analyze_project(job_context or context(), project_id, store, settings, patch)

    return store, project_id, calls, context, run


def test_saved_rough_cut_is_visibly_review_required_and_never_generative(rough_project):
    store, project_id, _calls, _context, run = rough_project

    result = run()

    draft = store.load(project_id)["draft"]
    assert draft["editorial_authority"] == result["editorial_authority"] == "extractive_rough_cut"
    assert draft["status"] == "requires_review"
    assert draft["review_required"] is True
    assert draft["generative_approved"] is False
    assert draft["semantic_review_status"] == "not_model_reviewed"
    assert draft["title"] == "EXTRACTIVE ROUGH CUT"
    assert draft["keep_ranges"] == [{"start": 5, "end": 10}, {"start": 12, "end": 17}]
    assert "rough cut" in result["message"].lower()
    assert any(row["type"] == "extractive_rough_cut" for row in result["warnings"])
    duration_review = draft["duration_review"]
    assert duration_review["generative_review_status"] == "failed"
    assert duration_review["target_feasibility"]["status"] == "met"
    assert duration_review["target_feasibility"]["scope"] == "current_fixed_source_selection"
    assert duration_review["target_feasibility"]["unresolved_slot_indexes"] == []
    critic = store.load(project_id)["analysis"]["story_hierarchy"]["critic"]
    assert critic["verdict"] == "revise"
    assert critic["unresolved_slot_indexes"] == [1]


def test_rough_editorial_cache_cannot_replace_a_new_generation_attempt(rough_project):
    _store, _project_id, calls, _context, run = rough_project

    run()
    run()

    assert calls == {"transcribe": 1, "plan": 2}


def test_generative_evidence_cache_requires_independent_whole_utterance_sidecar():
    fixture = source_fixture()
    decision = rough_cut(fixture)
    rough_requirements = decision.pop("extractive_requirements")
    decision.pop("editorial_authority")
    catalog = story_evidence.build_story_evidence_catalog(fixture[1], fixture[2])
    rows = []
    for index, (purpose, identifier) in enumerate((("premise", "b2"), ("result", "b3"))):
        reference = next(row["id"] for row in catalog if row["beat_id"] == identifier)
        rows.append({"slot_index": index, "purpose": purpose, "primary_beat_ids": [identifier],
                     "context_beat_ids": [], "primary_evidence_ids": [reference],
                     "context_evidence_ids": [], "temporal_witness_id": reference})
    proof = story_evidence.validate_story_evidence(
        rows, fixture[1], fixture[2], selected_beat_ids=["b2", "b3"], rejected_beat_ids=["b1"],
    )
    requirements = {
        "required_beat_ids": ["b2", "b3"], "critic_requested_beat_ids": [],
        "semantic_mapping_verified": True, "semantic_review_status": "model_reviewed",
        "slot_map": proof["slot_map"], "evidence_policy_version": story_evidence.EVIDENCE_POLICY_VERSION,
        "evidence_proof": proof,
        "semantic_revision": {"attempts": 1, "verdict": "fit", "policy_version": POLICY_VERSION,
                              "cost": {"policy_version": POLICY_VERSION}},
        "source_span_policy_version": rough_requirements["source_span_policy_version"],
        "source_span_constraints": rough_requirements["source_span_constraints"],
    }
    decision["story_requirements"] = requirements
    assert director._semantic_mapping_is_verified(decision) is True
    assert director._cached_source_story_evidence_is_verified(decision, fixture[2], {}) is True

    requirements.pop("source_span_constraints")

    assert director._cached_source_story_evidence_is_verified(decision, fixture[2], {}) is False


@pytest.mark.parametrize("restore", [{"start": 0, "end": 3}, {"start": 20, "end": 25}])
def test_manual_restore_cannot_expand_rough_source_and_failed_rebuild_is_atomic(rough_project, restore):
    store, project_id, _calls, _context, run = rough_project
    run()
    store.update(project_id, lambda current: current["manual"].update({"keeps": [restore]}))
    before = store.load(project_id)

    with pytest.raises(StoryBudgetError):
        run()

    after = store.load(project_id)
    for key in ("draft", "manual", "settings", "export"):
        assert after.get(key) == before.get(key)


def test_director_refuses_rough_authority_without_current_explicit_opt_in(rough_project):
    store, project_id, _calls, _context, run = rough_project
    run()
    before = store.load(project_id)

    with pytest.raises(StoryBudgetError):
        run({"allow_extractive_rough_cut": False})

    after = store.load(project_id)
    assert after["draft"] == before["draft"]
    assert after["settings"] == before["settings"]


def test_rough_source_is_revalidated_before_timeline_application_and_inside_atomic_commit(rough_project, monkeypatch):
    store, project_id, _calls, context, run = rough_project
    run()
    before = store.load(project_id)
    validate = director._validate_extractive_selection
    validations = []

    def reject_commit(*args, **kwargs):
        validations.append(copy.deepcopy(kwargs.get("keep_ranges")))
        diagnostic = validate(*args, **kwargs)
        if len(validations) == 3:
            raise StoryBudgetError("Synthetic source conflict at atomic commit.", {
                "reason": "synthetic_commit_conflict", "applied_to_timeline": False,
            })
        return diagnostic

    monkeypatch.setattr(director, "_validate_extractive_selection", reject_commit)
    job_context = context()

    with pytest.raises(StoryBudgetError) as caught:
        run(job_context=job_context)

    assert caught.value.diagnostic["reason"] == "synthetic_commit_conflict"
    assert len(validations) == 3
    assert validations[0] is None
    assert validations[1] == validations[2] == [{"start": 5, "end": 10}, {"start": 12, "end": 17}]
    assert job_context.committed is False
    after = store.load(project_id)
    for key in ("draft", "manual", "settings", "export"):
        assert after.get(key) == before.get(key)
