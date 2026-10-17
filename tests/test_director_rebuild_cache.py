from __future__ import annotations

import copy
import threading
from pathlib import Path

import pytest

from cutroom import director
from cutroom.config import load_settings
from cutroom.edit_styles import get_edit_style
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.story_budget import POLICY_VERSION
from cutroom.vision import VISION_ANALYSIS_VERSION


@pytest.fixture
def semantic_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("Semantic edit")
    project_id = project["id"]
    source = store.project_dir(project_id) / "media" / "source-A.mp4"
    source.write_bytes(b"fixture-source")

    def attach(current):
        current["sources"]["A"] = {
            "slot": "A", "name": "source.mp4", "relative_path": "media/source-A.mp4",
            "duration": 300.0, "width": 1920, "height": 1080,
            "has_audio": True, "size": source.stat().st_size,
        }
        current["settings"].update({
            "goal": "short", "edit_style": "smart", "target_duration": 60.0, "duration_mode": "style",
            "spoken_language": "auto", "auto_reframe": False,
        })

    store.update(project_id, attach)
    segments = [{
        "id": f"s{index}", "start": float(index * 10), "end": float(index * 10 + 8),
        "text": f"This is useful complete explanation number {index} with enough clear speech to understand.",
        "words": [], "avg_logprob": -0.1,
    } for index in range(30)]
    transcript = {
        "language": "en", "language_probability": 0.99, "duration": 300.0,
        "segments": segments, "text": " ".join(row["text"] for row in segments), "words": [],
    }
    calls = {"transcribe": 0, "plan": 0}

    def transcribe(*_args, **_kwargs):
        calls["transcribe"] += 1
        return copy.deepcopy(transcript), None

    def plan(_context, current_segments, *_args, **_kwargs):
        calls["plan"] += 1
        return {
            "segments": [{**row, "editorial_score": 0.8} for row in current_segments],
            "decision": {
                "keep_ids": [row["id"] for row in current_segments],
                "remove_ids": [], "highlight_ids": ["s3", "s22"],
                "story_ranges": [{"start": 30.0, "end": 60.0}, {"start": 220.0, "end": 250.0}],
                "title": "The requested story", "summary": "Two complete selected ideas.",
                "opening_id": "s3", "closing_id": "s24",
            },
            # This fixture exercises rebuild/cache/layout behavior. Dedicated
            # semantic fixtures below provide the primary/context contract.
            "story_beats": [], "story_hierarchy": {"fixture": True},
        }, "deterministic"

    monkeypatch.setattr(director, "_transcribe_safely", transcribe)
    monkeypatch.setattr(director, "_plan_edit_with_cancel", plan)
    monkeypatch.setattr(director, "analyze_audio", lambda *_args, **_kwargs: {
        "available": True, "duration": 300.0, "ranges": {},
        "summary": {"silence_threshold_dbfs": -42.0}, "waveform": [],
    })
    monkeypatch.setattr(director, "detect_scenes", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(director, "analyze_faces_and_embedded_camera", lambda *_args, **_kwargs: {
        "version": VISION_ANALYSIS_VERSION, "focus_safe": False,
    })

    def context():
        return JobContext(Job("fixture_job", "director", project_id), threading.Lock())

    director.analyze_project(context(), project_id, store, settings)
    return store, settings, project_id, calls, context


def test_variation_reuses_first_analysis_and_preserves_unchanged_draft(semantic_project):
    store, settings, project_id, calls, context = semantic_project

    def add_history(current):
        current["manual"]["_history"] = {"undo": [{"action": "fixture"}], "redo": []}
        current["manual"]["history"] = {"undo_count": 1, "redo_count": 0}

    store.update(project_id, add_history)
    before = store.load(project_id)
    result = director.refine_project(context(), project_id, store, settings, "new_variation")
    after = store.load(project_id)

    assert calls == {"transcribe": 1, "plan": 1}
    assert after["language"] == "auto"
    assert after["draft"]["language"] == "en"
    assert result["variation_changed"] is False
    assert after["draft"] == before["draft"]
    assert after["manual"]["_history"] == before["manual"]["_history"]


def test_new_editorial_instruction_replans_without_retranscription(semantic_project):
    store, settings, project_id, calls, context = semantic_project
    store.update(project_id, lambda current: current["settings"].update({"instruction": "Focus on the final explanation"}))

    director.refine_project(context(), project_id, store, settings, "new_variation")

    assert calls == {"transcribe": 1, "plan": 2}


def test_empty_target_pruning_does_not_restore_the_entire_source(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    segment = {"id": "long", "start": 0.0, "end": 300.0, "text": "One uninterrupted explanation."}
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_args, **_kwargs: ({
        "segments": [segment], "decision": {
            "keep_ids": ["long"], "remove_ids": [], "highlight_ids": ["long"],
            "opening_id": "long", "closing_id": "long", "story_ranges": [dict(segment)],
        }, "story_beats": [], "story_hierarchy": {"critic": {"verdict": "pass"}},
    }, "fixture_story"))
    before = store.load(project_id)
    with pytest.raises(director.StoryPlanningError, match="No usable passages remain"):
        director.analyze_project(context(), project_id, store, settings, {
            "instruction": "Keep one complete explanation", "duration_mode": "target", "target_duration": 30,
        })
    assert store.load(project_id) == before


def _required_story_editorial(rows):
    segments = [{"id": identifier, "start": start, "end": end,
                 "text": "A complete synthetic source sentence.", "words": [],
                 "editorial_score": .8}
                for identifier, start, end in rows]
    identifiers = [row["id"] for row in segments]
    return {
        "segments": segments,
        "decision": {
            "keep_ids": identifiers, "remove_ids": [], "highlight_ids": identifiers[:1],
            "opening_id": identifiers[0], "closing_id": identifiers[-1],
            "story_beat_ids": identifiers,
            "story_ranges": [{"start": row["start"], "end": row["end"], "beat_id": row["id"]}
                             for row in segments],
            "story_requirements": {
                "semantic_mapping_verified": True,
                "required_beat_ids": identifiers, "critic_requested_beat_ids": identifiers[1:],
                "unresolved_slot_indexes": [], "unapplied_critic_actions": 0,
                "slot_map": [{"slot_index": 0, "primary_beat_ids": identifiers[:1],
                              "context_beat_ids": identifiers[1:], "beat_ids": identifiers,
                              "role_evidence": "Synthetic primary and context evidence."}],
                "semantic_revision": {"attempts": 0, "verdict": "fit", "policy_version": POLICY_VERSION,
                                      "cost": {"policy_version": POLICY_VERSION}},
            },
        },
        "story_beats": [], "story_hierarchy": {"critic": {"verdict": "pass"}},
    }


def _with_story_roles(editorial, purposes):
    requirements = editorial["decision"]["story_requirements"]
    template = requirements["slot_map"][0]
    requirements["slot_map"] = [{**copy.deepcopy(template), "slot_index": index, "purpose": purpose,
                                 "role_evidence": f"Synthetic explicit source mapping for {purpose}."}
                                for index, purpose in enumerate(purposes)]
    return editorial


@pytest.mark.parametrize("complete", [False, True], ids=["premise_only", "all_roles_one_source_beat"])
def test_required_style_roles_are_independently_mapped_before_commit(semantic_project, monkeypatch, complete):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    roles = get_edit_style("stream_story")["selection_policy"]["story_structure"]
    editorial = _with_story_roles(_required_story_editorial([("source_idea", 0, 6)]),
                                  roles if complete else roles[:1])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "ollama_hierarchical_story"))
    before = store.state_path(project_id).read_bytes()
    patch = {"instruction": "Keep each configured story role", "edit_style": "stream_story",
             "duration_mode": "target", "target_duration": 20}

    if complete:
        result = director.analyze_project(context(), project_id, store, settings, patch)
        assert result["draft"]["keep_ranges"] == [{"start": 0, "end": 6}]
        slots = store.load(project_id)["analysis"]["editorial_cache"]["decision"]["story_requirements"]["slot_map"]
        assert [row["purpose"] for row in slots] == roles
        assert all(row["primary_beat_ids"] == ["source_idea"] for row in slots)
    else:
        with pytest.raises(StoryBudgetError) as failure:
            director.analyze_project(context(), project_id, store, settings, patch)
        assert "missing_required_story_roles" in failure.value.diagnostic["reasons"]
        assert failure.value.diagnostic["missing_required_story_roles"] == roles[1:]
        assert failure.value.diagnostic["applied_to_timeline"] is False
        assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("rows,incomplete", [
    ([("b1", .59, 2.93), ("b2", 8.41, 19.64), ("b3", 20.34, 29.5), ("b4", 35.31, 41.31)],
     [{"start": .59, "end": 2.93}, {"start": 35.31, "end": 41.31}]),
    ([("b1", 0, 15.31), ("b3", 30.69, 39.08)], [{"start": 0, "end": 15.31}]),
], ids=["english_8_34_missing_middle", "hebrew_15_31_missing_result"])
def test_required_story_budget_failure_preserves_edit_settings_and_export(
    semantic_project, monkeypatch, rows, incomplete,
):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    export = settings.exports_dir / "previous-export.mp4"
    export.write_bytes(b"previous encoded export remains authoritative")
    store.update(project_id, lambda current: current["exports"].append({"name": export.name}))
    editorial = _required_story_editorial(rows)
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    monkeypatch.setattr(director, "_select_short_story_ranges", lambda *_a, **_k: copy.deepcopy(incomplete))
    before = store.state_path(project_id).read_bytes()
    old_export = export.read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {
            "instruction": "Preserve the validated complete story", "duration_mode": "target", "target_duration": 20,
        })

    assert failure.value.diagnostic["scope"] == "current_required_selection"
    assert failure.value.diagnostic["required_policy_minimum_seconds"] > 20
    assert failure.value.diagnostic["applied_to_timeline"] is False
    assert store.state_path(project_id).read_bytes() == before
    assert export.read_bytes() == old_export
    assert list(settings.exports_dir.iterdir()) == [export]


def test_cleanup_cannot_commit_a_draft_missing_required_speech(semantic_project, monkeypatch):
    from cutroom.story_budget import StoryBudgetError
    from cutroom.utils import invert_ranges

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("setup", 0, 6), ("ending", 12, 18)])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    monkeypatch.setattr(director, "_short_cleanup_cuts_with_floor", lambda *_a, **_k: (
        invert_ranges([{"start": 12, "end": 18}], 300), {},
    ))
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {
            "instruction": "Keep setup and ending", "duration_mode": "target", "target_duration": 20,
        })

    assert failure.value.diagnostic["required_policy_minimum_seconds"] == 12
    assert "setup" in failure.value.diagnostic["missing_required_beat_ids"]
    assert store.state_path(project_id).read_bytes() == before


def test_initial_budget_failure_does_not_commit_a_draft_or_requested_settings(semantic_project, monkeypatch):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    def reset(current):
        current["draft"] = None
        current["analysis"] = None
    store.update(project_id, reset)
    before = store.load(project_id)
    editorial = _required_story_editorial([("context", 0, 25), ("result", 30, 38)])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))

    with pytest.raises(StoryBudgetError):
        director.analyze_project(context(), project_id, store, settings, {
            "instruction": "Keep the required context", "duration_mode": "target", "target_duration": 20,
        })

    after = store.load(project_id)
    assert after["draft"] is None
    assert after["settings"] == before["settings"]
    assert after["manual"] == before["manual"]
    assert after["exports"] == before["exports"]


def test_focus_speaker_budget_failure_has_no_early_mutation_or_rollback(semantic_project, monkeypatch):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    source_b = store.project_dir(project_id) / "media/source-B.mp4"
    source_b.write_bytes(b"second fixture source")
    def attach_b(current):
        current["sources"]["B"] = {**current["sources"]["A"], "slot": "B", "relative_path": "media/source-B.mp4"}
    store.update(project_id, attach_b)
    failure = StoryBudgetError("Required story does not fit.", {"required_policy_minimum_seconds": 30})
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (_ for _ in ()).throw(failure))
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as caught:
        director.refine_project(context(), project_id, store, settings, "focus_speaker")

    assert caught.value is failure
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("damage", ["unverified", "missing_primary", "missing_context", "missing_revision_cost",
                                    "extra_revision", "unfit_revision", "stale_revision_policy"])
def test_invalid_semantic_proof_cannot_commit(semantic_project, monkeypatch, damage):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("primary", 0, 4), ("context", 10, 14)])
    requirements = editorial["decision"]["story_requirements"]
    if damage == "unverified":
        requirements["semantic_mapping_verified"] = False
    elif damage == "missing_primary":
        requirements["slot_map"][0]["primary_beat_ids"] = []
    elif damage == "missing_context":
        requirements["slot_map"][0]["context_beat_ids"] = []
    elif damage == "missing_revision_cost":
        requirements["semantic_revision"].pop("cost")
    elif damage == "extra_revision":
        requirements["semantic_revision"]["attempts"] = 2
    elif damage == "unfit_revision":
        requirements["semantic_revision"]["verdict"] = "infeasible"
    else:
        requirements["semantic_revision"]["policy_version"] = "legacy-policy"
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {"instruction": "Require current proof"})

    assert "unverified_semantic_mapping" in failure.value.diagnostic["reasons"]
    assert store.state_path(project_id).read_bytes() == before


def test_verified_story_cache_cannot_reuse_a_legacy_semantic_mapping(semantic_project):
    store, settings, project_id, calls, context = semantic_project
    def legacy(current):
        current["analysis"]["engine"] = "ollama_hierarchical_story"
        current["analysis"]["editorial_cache"]["decision"]["story_requirements"] = {
            "required_beat_ids": ["s3"], "unresolved_slot_indexes": [],
        }
    store.update(project_id, legacy)

    director.analyze_project(context(), project_id, store, settings)

    assert calls == {"transcribe": 1, "plan": 2}


def test_final_guard_rejects_missing_primary_even_when_all_context_survives(semantic_project, monkeypatch):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("primary", 0, 4), ("context", 10, 14)])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    monkeypatch.setattr(director, "_select_short_story_ranges", lambda *_a, **_k: [{"start": 10, "end": 14}])
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {"instruction": "Keep primary and context"})

    assert failure.value.diagnostic["missing_required_beat_ids"] == ["primary"]
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("rejected", [False, True], ids=["unapproved_top_up", "critic_rejection"])
def test_final_guard_rejects_reintroduced_unapproved_footage(semantic_project, monkeypatch, rejected):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("primary", 0, 4), ("context", 10, 14)])
    if rejected:
        editorial["decision"]["rejected_story_ranges"] = [{"start": 20, "end": 22}]
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    monkeypatch.setattr(director, "_select_short_story_ranges", lambda *_a, **_k: [
        {"start": 0, "end": 4}, {"start": 10, "end": 14}, {"start": 20, "end": 22},
    ])
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {"instruction": "Exclude the rejected passage"})

    assert "unapproved_story_material_included" in failure.value.diagnostic["reasons"]
    if rejected:
        assert "rejected_story_material_included" in failure.value.diagnostic["reasons"]
        assert failure.value.diagnostic["rejected_overlap"] == [{"start": 20, "end": 22}]
    assert store.state_path(project_id).read_bytes() == before


def test_explicit_user_restore_remains_authoritative_for_a_verified_story(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("primary", 0, 4), ("context", 10, 14)])
    editorial["decision"]["rejected_story_ranges"] = [{"start": 20, "end": 22}]
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "ollama_hierarchical_story"))
    store.update(project_id, lambda current: current["manual"].update({"keeps": [{"start": 20, "end": 22}]}))

    result = director.analyze_project(context(), project_id, store, settings, {"instruction": "Preserve my restore"})

    assert result["draft"]["keep_ranges"] == [
        {"start": 0, "end": 4}, {"start": 10, "end": 14}, {"start": 20, "end": 22},
    ]
    assert store.load(project_id)["manual"]["keeps"] == [{"start": 20, "end": 22}]


def test_short_source_in_style_mode_still_selects_only_the_approved_story(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("primary", 2, 8)])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "ollama_hierarchical_story"))
    store.update(project_id, lambda current: current["sources"]["A"].update({"duration": 10}))

    result = director.analyze_project(context(), project_id, store, settings, {
        "instruction": "Keep the approved short passage", "duration_mode": "style", "target_duration": 60,
    })

    assert result["draft"]["keep_ranges"] == [{"start": 2, "end": 8}]
    assert result["draft"]["output_duration"] == 6


def test_frame_grid_budget_failure_preserves_the_existing_edit(semantic_project, monkeypatch):
    from cutroom.story_budget import StoryBudgetError

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([
        ("first", .01, 6.69), ("middle", 20.01, 26.69), ("ending", 40.01, 46.69),
    ])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "fixture_story"))
    before = store.state_path(project_id).read_bytes()

    with pytest.raises(StoryBudgetError) as failure:
        director.analyze_project(context(), project_id, store, settings, {
            "instruction": "Account for encoded frames", "duration_mode": "target", "target_duration": 20, "fps": 30,
        })

    diagnostic = failure.value.diagnostic
    assert diagnostic["required_policy_minimum_seconds"] == pytest.approx(20.04)
    assert diagnostic["required_framed_minimum_seconds"] == pytest.approx(20.1)
    assert diagnostic["cost"]["fits_target"] is False
    assert store.state_path(project_id).read_bytes() == before


@pytest.mark.parametrize("mode", ["target", "style"])
def test_complete_27_second_story_fits_20_seconds_without_losing_speech(semantic_project, monkeypatch, mode):
    from cutroom.story_budget import framed_story_duration

    store, settings, project_id, _calls, context = semantic_project
    editorial = _required_story_editorial([("setup", 8.41, 29.5), ("ending", 35.31, 41.31)])
    _with_story_roles(editorial, get_edit_style("stream_story")["selection_policy"]["story_structure"])
    words = [
        [(8.41, 10.48), (10.78, 12.5), (12.68, 13.84), (14.16, 16.46),
         (16.74, 17.44), (18.24, 19.64), (20.34, 21.8), (22.26, 23.18),
         (23.67, 24.45), (25.48, 27.14), (27.36, 29.5)],
        [(35.31, 35.79), (39.55, 40.59), (40.93, 41.31)],
    ]
    for segment, timings in zip(editorial["segments"], words):
        segment["words"] = [{"start": start, "end": end, "word": f"word{index}"}
                            for index, (start, end) in enumerate(timings)]
        segment["text"] = " ".join(row["word"] for row in segment["words"])
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_a, **_k: (copy.deepcopy(editorial), "ollama_hierarchical_story"))

    result = director.analyze_project(context(), project_id, store, settings, {
        "instruction": "Keep the complete setup and ending", "duration_mode": mode,
        "edit_style": "stream_story", "target_duration": 20,
    })

    draft = result["draft"]
    assert draft["output_duration"] == pytest.approx(20, abs=.05)
    assert framed_story_duration(draft["keep_ranges"], 30) <= 20.05
    spoken_seconds = 0.0
    for segment in editorial["segments"]:
        for word in segment["words"]:
            spoken_seconds += word["end"] - word["start"]
            covered = sum(max(0, min(word["end"], row["end"]) - max(word["start"], row["start"]))
                          for row in draft["keep_ranges"])
            assert covered == pytest.approx(word["end"] - word["start"], abs=.001)
    assert spoken_seconds == pytest.approx(18.21)
    assert all(any(max(keep["start"], passage["start"]) < min(keep["end"], passage["end"])
                   for passage in editorial["decision"]["story_ranges"]) for keep in draft["keep_ranges"])


def test_final_selection_changes_use_a_neutral_title(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    store.update(project_id, lambda current: current["settings"].update({
        "instruction": "A new complete selection", "target_duration": 90,
    }))
    monkeypatch.setattr(director, "_select_short_story_ranges", lambda *_args, **_kwargs: [
        {"start": 30, "end": 60}, {"start": 100, "end": 110}, {"start": 220, "end": 250},
    ])
    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert saved["draft"]["title"] == "CUTROOM story"
    assert saved["draft"]["quality_review"]["title_review"]["reason"] == "final_selection_changed"
    assert saved["draft"]["quality_review"]["selection_review"]["status"] == "changed"


def test_first_draft_context_checkpoint_validates_the_staged_brief(semantic_project):
    store, settings, project_id, _calls, context = semantic_project
    def reset_first_draft(current):
        current["draft"] = None
        current["analysis"] = None
    store.update(project_id, reset_first_draft)
    director.analyze_project(context(), project_id, store, settings, {
        "spoken_language": "en", "target_duration": 90,
        "instruction": "A complete first edit with the requested language",
    })
    saved = store.load(project_id)
    assert saved["draft"] is not None
    assert saved["settings"]["spoken_language"] == "en"
    assert saved["settings"]["target_duration"] == 90
    assert saved["analysis"]["transcript"]["language"] == "en"


def test_saved_commentary_keeps_planned_anchors_with_truthful_review(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    segments = [
        {"id": "s0001", "start": 1.73, "end": 8.63},
        {"id": "s0002", "start": 9.76, "end": 12.39},
        {"id": "s0003", "start": 12.93, "end": 14.03},
        {"id": "s0004", "start": 14.57, "end": 16.03},
        {"id": "s0005", "start": 20.19, "end": 21.47},
        {"id": "s0006", "start": 40.08, "end": 43.26},
    ]
    decision = {
        "keep_ids": ["s0001", "s0002", "s0003", "s0004", "s0006"],
        "remove_ids": ["s0005"], "highlight_ids": ["s0001"],
        "opening_id": "s0001", "closing_id": "s0006",
        "story_beat_ids": ["b0001", "b0003"],
        "story_ranges": [{"start": 1.73, "end": 16.03, "beat_id": "b0001"},
                         {"start": 40.08, "end": 43.26, "beat_id": "b0003"}],
    }
    monkeypatch.setattr(director, "_plan_edit_with_cancel", lambda *_args, **_kwargs: ({
        "segments": copy.deepcopy(segments), "decision": copy.deepcopy(decision),
        "story_beats": [], "story_hierarchy": {"critic": {"verdict": "pass"}},
    }, "fixture_story"))
    store.update(project_id, lambda current: current["settings"].update({
        "edit_style": "stream_commentary", "target_duration": 30.0,
    }))

    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert saved["draft"]["keep_ranges"] == [
        {"start": 1.73, "end": 16.03}, {"start": 40.08, "end": 43.26},
    ]
    assert saved["draft"]["output_duration"] == pytest.approx(17.48)
    assert saved["draft"]["partial_ai"] is True
    assert saved["draft"]["quality_review"]["needs_review"] is True
    assert [row["type"] for row in saved["draft"]["quality_review"]["warnings"]] == ["style_moment_constraint"]

    store.update(project_id, lambda current: current["settings"].update({"target_duration": 15.0}))
    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert saved["draft"]["partial_ai"] is True
    assert "story_anchor_missing" in [row["type"] for row in saved["draft"]["quality_review"]["warnings"]]


def test_corrected_transcript_invalidates_editorial_cache(semantic_project):
    store, settings, project_id, calls, context = semantic_project

    def correct(current):
        # Deliberately retain the old editorial cache: the transcript fingerprint
        # must defend against stale choices even for older clients/imports.
        current["analysis"]["transcript"]["segments"][3]["text"] = "This corrected explanation changes the meaning entirely."

    store.update(project_id, correct)
    director.analyze_project(context(), project_id, store, settings)

    assert calls == {"transcribe": 1, "plan": 2}
    saved = store.load(project_id)
    assert "corrected explanation" in saved["analysis"]["segments"][3]["text"]


@pytest.mark.parametrize("stale_contract", [None, "legacy-unvalidated-critic"])
def test_legacy_critic_pass_cannot_bypass_review_on_explicit_rebuild(semantic_project, stale_contract):
    store, settings, project_id, calls, context = semantic_project

    def legacy(current):
        current["analysis"]["story_hierarchy"] = {"critic": {"verdict": "pass", "issues": []}}
        current["analysis"]["engine"] = "ollama_hierarchical_story"
        current["analysis"]["editorial_cache"].pop("review_contract", None)
        if stale_contract:
            current["analysis"]["editorial_cache"]["review_contract"] = stale_contract

    store.update(project_id, legacy)
    before = store.load(project_id)
    assert before["analysis"]["story_hierarchy"]["critic"]["verdict"] == "pass"
    assert calls == {"transcribe": 1, "plan": 1}  # Opening/loading never starts AI.
    director.analyze_project(context(), project_id, store, settings)
    assert calls == {"transcribe": 1, "plan": 2}  # Rebuild retains ASR, reruns editorial review.
    from cutroom.intelligence import CRITIC_REVIEW_CONTRACT
    assert store.load(project_id)["analysis"]["editorial_cache"]["review_contract"] == CRITIC_REVIEW_CONTRACT


def test_legacy_basic_cleanup_cache_does_not_require_a_story_model(semantic_project):
    store, settings, project_id, calls, context = semantic_project

    def basic_cleanup(current):
        current["analysis"]["story_hierarchy"] = None
        current["analysis"]["engine"] = "deterministic"
        current["analysis"]["editorial_cache"].pop("review_contract", None)

    store.update(project_id, basic_cleanup)
    director.analyze_project(context(), project_id, store, settings)
    assert calls == {"transcribe": 1, "plan": 1}


def test_rebuild_preserves_explicit_restore_after_target_enforcement(semantic_project):
    store, settings, project_id, calls, context = semantic_project
    store.update(project_id, lambda current: current["manual"].update({"keeps": [{"start": 0.0, "end": 8.0}]}))

    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)

    assert saved["draft"]["keep_ranges"][0] == {"start": 0.0, "end": 8.0}
    assert saved["draft"]["output_duration"] == pytest.approx(68.0)
    assert calls == {"transcribe": 1, "plan": 1}
    for candidate in saved["draft"].get("reel_candidates", []):
        assert any(row["start"] == 0.0 and row["end"] >= 8.0 for row in candidate["keep_ranges"])


@pytest.mark.parametrize("empty_b", [False, True])
@pytest.mark.parametrize("audio_slot", ["A", "B"])
def test_rebuild_preserves_independent_tracks_and_their_sync_base(semantic_project, monkeypatch, empty_b, audio_slot):
    from cutroom.editing import apply_manual_edit

    store, settings, project_id, _calls, context = semantic_project
    sync_calls = []

    def attach_and_edit(current):
        # The synthetic fixture's second slot shares its dummy media file. Every
        # media/model operation remains stubbed: this tests only state lifecycle.
        current["sources"]["B"] = {**current["sources"]["A"], "slot": "B", "name": "source-B.mp4"}
        current["analysis"]["sync"] = {"offset": 2.125, "confidence": 1, "method": "fixture"}
        current["manual"]["source_mixer"] = {"audio_slot": audio_slot}
        apply_manual_edit(current, {"action": "track_split", "slot": "A", "time": 45})
        apply_manual_edit(current, {"action": "track_split", "slot": "B", "time": 60})
        if empty_b:
            apply_manual_edit(current, {"action": "track_remove_range", "slot": "B", "start": 0, "end": 300})

    def resync(*_args, **_kwargs):
        sync_calls.append(True)
        return {"offset": 9.0, "confidence": 1.0, "method": "fixture-new"}

    monkeypatch.setattr(director, "synchronize_sources", resync)
    store.update(project_id, attach_and_edit)
    tracks = copy.deepcopy(store.load(project_id)["manual"]["source_tracks"])
    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert saved["manual"]["source_tracks"] == tracks
    assert saved["analysis"]["sync"]["offset"] == 2.125
    assert saved["analysis"]["sync"]["method"] == "source_tracks"
    assert sync_calls == []
    assert "_history" not in saved["manual"]
    assert saved["manual"]["history"] == {"undo_count": 0, "redo_count": 0}

    # Reset deliberately releases the frozen base, so the next Director pass
    # must not reuse the old track-locked sync as if it were a fresh measurement.
    store.update(project_id, lambda current: apply_manual_edit(current, {"action": "track_reset", "slot": "B"}))
    director.analyze_project(context(), project_id, store, settings)
    reset = store.load(project_id)
    assert sync_calls
    assert reset["analysis"]["sync"]["offset"] == 9.0
    assert reset["manual"]["source_tracks"] == {"A": tracks["A"]}


def test_rebuild_preserves_reordered_edit_sequence_beyond_original_source_duration(semantic_project):
    from cutroom.editing import apply_manual_edit
    from cutroom.sequence import editor_sequence_snapshot

    store, settings, project_id, _calls, context = semantic_project

    def rearrange(current):
        clip = editor_sequence_snapshot(current)["source_tracks"]["A"][0]
        apply_manual_edit(current, {"action": "sequence_move", "slot": "A", "clip_id": clip["id"], "start": 320})

    store.update(project_id, rearrange)
    before = store.load(project_id)
    assert before["manual"]["sequence"]["duration"] > before["sources"]["A"]["duration"]
    director.analyze_project(context(), project_id, store, settings)
    after = store.load(project_id)
    assert after["manual"]["sequence"] == before["manual"]["sequence"]
    assert after["manual"]["source_tracks"] == before["manual"]["source_tracks"]
    assert editor_sequence_snapshot(after)["active"] is True


def test_preset_rebuild_reports_preserved_manual_timeline_and_keeps_undo(semantic_project):
    from cutroom.editing import apply_manual_edit
    from cutroom.sequence import editor_sequence_snapshot

    store, settings, project_id, _calls, context = semantic_project
    store.update(project_id, lambda current: apply_manual_edit(
        current, {"action": "sequence_split_all", "time": 10.0},
    ))
    before = store.load(project_id)
    before_timeline = editor_sequence_snapshot(before)
    job_context = context()
    result = director.analyze_project(
        job_context, project_id, store, settings, {"edit_style": "competitive_clutch"},
    )
    after = store.load(project_id)
    assert after["draft"]["edit_style"] == "competitive_clutch"
    assert editor_sequence_snapshot(after) == before_timeline
    assert result["applied_to_timeline"] is False
    assert result["timeline_preserved"] is True
    assert "manual timeline was kept" in result["message"]
    assert job_context.job.message == result["message"]
    assert after["manual"]["_history"] == before["manual"]["_history"]
    assert after["manual"]["history"] == before["manual"]["history"]
    # The explicit application changes the actual editor projection. Undo/redo
    # restore the user's clip boundaries, rather than merely toggling a badge.
    store.update(project_id, lambda current: apply_manual_edit(current, {"action": "sequence_reset"}))
    applied = editor_sequence_snapshot(store.load(project_id))
    assert applied["active"] is False
    assert applied["duration"] == 30.0
    assert applied["duration"] != before_timeline["duration"]
    store.update(project_id, lambda current: apply_manual_edit(current, {"action": "undo"}))
    assert editor_sequence_snapshot(store.load(project_id)) == before_timeline
    store.update(project_id, lambda current: apply_manual_edit(current, {"action": "redo"}))
    assert editor_sequence_snapshot(store.load(project_id)) == applied


def test_preset_without_manual_sequence_is_applied_to_editor_timeline(semantic_project):
    from cutroom.sequence import editor_sequence_snapshot

    store, settings, project_id, _calls, context = semantic_project
    result = director.analyze_project(
        context(), project_id, store, settings, {"edit_style": "competitive_clutch"},
    )
    saved = store.load(project_id)
    assert result["applied_to_timeline"] is True
    assert result["timeline_preserved"] is False
    assert editor_sequence_snapshot(saved)["duration"] == saved["draft"]["output_duration"]
    assert result["message"] == "Your first edit is ready"


def test_clean_vod_keeps_natural_cleanup_controls_and_full_recording(semantic_project, monkeypatch):
    from cutroom.edit_styles import get_edit_style

    store, settings, project_id, _calls, context = semantic_project
    monkeypatch.setattr(director, "analyze_audio", lambda *_args, **_kwargs: {
        "available": True, "duration": 300.0,
        "ranges": {"silence": [{"start": 40.0, "end": 41.0}, {"start": 100.0, "end": 170.0}]},
        "summary": {"silence_threshold_dbfs": -42.0}, "waveform": [],
    })
    style = get_edit_style("clean_vod")
    result = director.analyze_project(
        context(), project_id, store, settings,
        {**style["defaults"], "edit_style": "clean_vod"},
    )
    draft = result["draft"]
    assert draft["audio_policy"]["silence_min_seconds"] == 1.20
    assert draft["audio_policy"]["silence_keep_seconds"] == 0.48
    assert draft["audio_policy"]["max_remove_ratio"] == 0.16
    assert draft["audio_policy"]["normalize"] is False
    assert draft["output_duration"] >= 300.0 * 0.84
    assert any(row["start"] <= 40.0 and row["end"] >= 41.0 for row in draft["keep_ranges"])


def test_unusable_ai_response_warning_and_actual_model_survive_saved_draft_and_cache(semantic_project, monkeypatch):
    from cutroom import intelligence

    store, settings, project_id, _calls, context = semantic_project
    calls = []
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (True, {"qwen3.5:4b"}))
    monkeypatch.setattr(intelligence, "_call_ollama", lambda _settings, payload:
                        calls.append(payload["model"]) or {"title": "Done"})

    def plan(job_context, segments, current_settings, brief, **kwargs):
        return intelligence.plan_edit(segments, current_settings, brief, **kwargs,
                                      cancel_check=job_context.check_cancelled)

    monkeypatch.setattr(director, "_plan_edit_with_cancel", plan)
    job_context = context()
    result = director.analyze_project(job_context, project_id, store, settings, {
        "goal": "youtube", "instruction": "Preserve the explanations.", "captions": True,
        "performance_mode": "lite",
    })
    saved = store.load(project_id)
    assert calls == ["qwen3.5:4b"]
    assert result["engine"] == "deterministic"
    assert result["model_selection"]["selected_model"] == "qwen3.5:4b"
    assert result["model_selection"]["requested_model"] == "qwen3.5:2b"
    assert result["model_selection"]["using_fallback"] is True
    assert result["warnings"][0]["type"] == "story_ai_fallback"
    assert saved["draft"]["model_selection"] == result["model_selection"]
    assert saved["analysis"]["model_selection"] == result["model_selection"]
    assert saved["draft"]["partial_ai"] is True
    assert result["warnings"][0] in saved["draft"]["quality_review"]["warnings"]
    assert "Basic cleanup draft ready" in job_context.job.message
    cached = director.analyze_project(context(), project_id, store, settings)
    assert calls == ["qwen3.5:4b"]
    assert cached["warnings"] == result["warnings"]
    assert cached["model_selection"] == result["model_selection"]


def _add_media_layers(store, project_id, *, start=40, end=60, sequence=False, second_source=False):
    from cutroom.editing import apply_manual_edit
    from cutroom.sequence import editor_sequence_snapshot

    def attach(current):
        if second_source:
            current["sources"]["B"] = {**current["sources"]["A"], "slot": "B"}
            current["manual"]["source_mixer"]["default_layout"] = "stacked"
        if sequence:
            clip = editor_sequence_snapshot(current)["source_tracks"]["A"][0]
            apply_manual_edit(current, {"action": "sequence_move", "slot": "A", "clip_id": clip["id"], "start": 320})
        asset_id = "asset_" + "b" * 32
        current["assets"] = {asset_id: {"id": asset_id, "name": "voice.wav", "kind": "audio", "duration": 300,
                                        "has_audio": True, "status": "ready"}}
        apply_manual_edit(current, {"action": "media_add", "asset_id": asset_id, "start": start, "end": end})
        apply_manual_edit(current, {"action": "set_audio_mixer", "music_db": -9, "voice_db": -3, "ducking": True})
    store.update(project_id, attach)


@pytest.mark.parametrize("command", [None, "shorter", "new_variation", "focus_speaker"])
def test_ai_rebuild_rejects_media_overhang_without_changing_any_project_state(semantic_project, monkeypatch, command):
    from cutroom.media_library import MediaLibraryError

    store, settings, project_id, _calls, context = semantic_project
    _add_media_layers(store, project_id, second_source=command == "focus_speaker")
    monkeypatch.setattr(director, "synchronize_sources", lambda *_args, **_kwargs: {"offset": 0, "confidence": 1, "method": "fixture"})
    monkeypatch.setattr(director, "_enforce_short_target", lambda *_args, **_kwargs: ([{"start": 20, "end": 300}], 0))
    before = store.load(project_id)
    job_context = context()
    with pytest.raises(MediaLibraryError, match="Trim, move, or remove"):
        if command:
            director.refine_project(job_context, project_id, store, settings, command)
        else:
            director.analyze_project(job_context, project_id, store, settings)
    assert store.load(project_id) == before
    assert not job_context.committed


@pytest.mark.parametrize("sequence", [False, True])
def test_compatible_refinement_preserves_media_and_mixer_on_effective_edit_clock(semantic_project, monkeypatch, sequence):
    store, settings, project_id, _calls, context = semantic_project
    _add_media_layers(store, project_id, start=325 if sequence else 2, end=330 if sequence else 4, sequence=sequence)
    monkeypatch.setattr(director, "_enforce_short_target", lambda *_args, **_kwargs: ([{"start": 20, "end": 300}], 0))
    before = store.load(project_id)
    director.refine_project(context(), project_id, store, settings, "shorter")
    after = store.load(project_id)
    assert after["manual"]["media_clips"] == before["manual"]["media_clips"]
    assert after["manual"]["audio_mixer"] == before["manual"]["audio_mixer"]
    assert after["assets"] == before["assets"]
    assert after["settings"]["pace"] == "dynamic"
    assert after["draft"]["output_duration"] == 20


def test_compatible_focus_refinement_commits_staged_routing_with_media(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project
    _add_media_layers(store, project_id, start=2, end=4, second_source=True)
    monkeypatch.setattr(director, "synchronize_sources", lambda *_args, **_kwargs: {"offset": 0, "confidence": 1, "method": "fixture"})
    monkeypatch.setattr(director, "_enforce_short_target", lambda *_args, **_kwargs: ([{"start": 20, "end": 300}], 0))
    before = store.load(project_id)
    director.refine_project(context(), project_id, store, settings, "focus_speaker")
    after = store.load(project_id)
    assert after["manual"]["source_mixer"]["default_layout"] == "camera"
    assert after["manual"]["media_clips"] == before["manual"]["media_clips"]
    assert after["manual"]["audio_mixer"] == before["manual"]["audio_mixer"]


@pytest.mark.parametrize("command", [None, "shorter", "focus_speaker"])
def test_rebuild_rejects_custom_text_overhang_atomically_without_media(semantic_project, monkeypatch, command):
    from cutroom.editing import apply_manual_edit
    from cutroom.text_clips import TextClipError

    store, settings, project_id, _calls, context = semantic_project
    def attach(current):
        if command == "focus_speaker":
            current["sources"]["B"] = {**current["sources"]["A"], "slot": "B"}
            current["manual"]["source_mixer"]["default_layout"] = "stacked"
        apply_manual_edit(current, {"action": "text_add", "kind": "caption", "start": 30, "end": 40, "text": "Keep this manual caption"})
    store.update(project_id, attach)
    monkeypatch.setattr(director, "synchronize_sources", lambda *_args, **_kwargs: {"offset": 0, "confidence": 1, "method": "fixture"})
    monkeypatch.setattr(director, "_enforce_short_target", lambda *_args, **_kwargs: ([{"start": 20, "end": 300}], 0))
    before = store.load(project_id)
    job_context = context()
    with pytest.raises(TextClipError, match="Trim, move, or remove"):
        if command:
            director.refine_project(job_context, project_id, store, settings, command)
        else:
            director.analyze_project(job_context, project_id, store, settings)
    assert store.load(project_id) == before
    assert not job_context.committed


@pytest.mark.parametrize("candidate_source", ["manual", "prepared"])
def test_prepared_embedded_layout_survives_generation_refinement_and_rebuild(semantic_project, candidate_source):
    from cutroom.editing import apply_manual_edit

    store, settings, project_id, _calls, context = semantic_project
    geometry = {"x": .72, "y": .06, "w": .24, "h": .25}

    def prepare(current):
        current["analysis"] = None
        current["draft"] = None
        current["sources"]["A"]["generation"] = "combined-recording"
        current["settings"].update({"layout": "embedded_stack", "performance_mode": "quality"})
        current["pre_analysis"]["vision"]["A"] = {
            "version": VISION_ANALYSIS_VERSION,
            "source_generation": "combined-recording", "sample_count": 6,
            "embedded_camera": {**geometry, "detector": VISION_ANALYSIS_VERSION},
        }
        if candidate_source == "manual":
            # A stale two-source preference cannot defeat the newer selection.
            current["manual"]["source_mixer"]["default_layout"] = "auto"
            apply_manual_edit(current, {
                "action": "set_embedded_camera", "enabled": True,
                **geometry, "content_x": .31, "content_y": .58,
            })

    store.update(project_id, prepare)
    director.analyze_project(context(), project_id, store, settings)
    first = store.load(project_id)
    assert first["draft"]["layout"] == "embedded_stack"
    assert first["draft"]["embedded_layout_confirmed"] is True
    assert {row["camera"] for row in first["draft"]["camera_plan"]} == {"embedded_stack"}
    assert director._effective_embedded_candidate(first, first["analysis"]["vision"])["x"] == geometry["x"]

    def frame_one_clip(current):
        first_range = current["draft"]["keep_ranges"][0]
        apply_manual_edit(current, {
            "action": "sequence_crop", "slot": "A",
            "start": first_range["start"], "end": first_range["end"],
            "x": .2, "y": .7, "zoom": 1.3,
        })

    store.update(project_id, frame_one_clip)
    framed = copy.deepcopy(store.load(project_id)["manual"]["source_tracks"])
    for command in ("shorter", "new_variation", None):
        if command:
            director.refine_project(context(), project_id, store, settings, command)
        else:
            director.analyze_project(context(), project_id, store, settings)
        saved = store.load(project_id)
        assert saved["settings"]["layout"] == "embedded_stack"
        assert saved["draft"]["layout"] == "embedded_stack"
        assert saved["draft"]["embedded_layout_confirmed"] is True
        assert {row["camera"] for row in saved["draft"]["camera_plan"]} == {"embedded_stack"}
        assert saved["manual"]["source_tracks"] == framed


@pytest.mark.parametrize("case", ["not_selected", "old_generation", "missing_generation", "old_detector", "invalid_geometry"])
def test_preparation_cannot_enable_unselected_or_stale_embedded_layout(semantic_project, case):
    store, settings, project_id, _calls, context = semantic_project

    def prepare(current):
        current["analysis"] = None
        current["draft"] = None
        current["sources"]["A"]["generation"] = "combined-recording"
        current["settings"]["layout"] = "auto" if case == "not_selected" else "embedded_stack"
        current["settings"]["performance_mode"] = "quality"
        profile = {
            "version": VISION_ANALYSIS_VERSION,
            "source_generation": "combined-recording", "sample_count": 6,
            "embedded_camera": {"x": .72, "y": .06, "w": .24, "h": .25},
        }
        if case in {"old_generation", "missing_generation"}:
            profile["source_generation"] = "old-recording" if case == "old_generation" else ""
        elif case == "old_detector":
            profile["version"] = "legacy-detector"
        elif case == "invalid_geometry":
            profile["embedded_camera"]["x"] = .99
        current["pre_analysis"]["vision"]["A"] = profile

    store.update(project_id, prepare)
    director.analyze_project(context(), project_id, store, settings)
    saved = store.load(project_id)
    assert saved["draft"]["embedded_layout_confirmed"] is False
    assert {row["camera"] for row in saved["draft"]["camera_plan"]} == {"A"}


def test_duration_intent_replans_from_cached_context_without_retranscription(semantic_project):
    store, settings, project_id, calls, context = semantic_project
    store.update(project_id,lambda current:current["settings"].update({"duration_mode":"target"}))
    director.analyze_project(context(),project_id,store,settings)
    assert calls == {"transcribe":1,"plan":2}
    review = store.load(project_id)["draft"]["duration_review"]
    assert review["duration_mode"]=="target"
    # Every step that changed the length is recorded, from the request to the final edit.
    stages = [row["stage"] for row in review["chain"]]
    assert stages[0] == "requested" and "story_selection" in stages and stages[-1] == "final"
    assert review["chain"][-1]["seconds"] == store.load(project_id)["draft"]["output_duration"]
    director.analyze_project(context(),project_id,store,settings)
    assert calls == {"transcribe":1,"plan":2}


def test_target_shortfall_is_saved_and_reported_as_needing_review(semantic_project, monkeypatch):
    store, settings, project_id, _calls, context = semantic_project

    def bounded_plan(_context, current_segments, *_args, **_kwargs):
        selected = next(row for row in current_segments if row["id"] == "s3")
        return {
            "segments": [{**row, "editorial_score": .8} for row in current_segments],
            "decision": {
                "keep_ids": ["s3"], "remove_ids": [], "highlight_ids": [],
                "opening_id": "s3", "closing_id": "s3", "title": "CUTROOM story",
                "story_beat_ids": ["approved"],
                "story_ranges": [{"start": selected["start"], "end": selected["end"], "beat_id": "approved"}],
                "story_requirements": {"required_beat_ids": ["approved"], "critic_requested_beat_ids": [],
                                       "unresolved_slot_indexes": [], "unapplied_critic_actions": 0,
                                       "semantic_mapping_verified": True,
                                       "slot_map": [{"slot_index": 0, "primary_beat_ids": ["approved"],
                                                     "context_beat_ids": [], "beat_ids": ["approved"],
                                                     "role_evidence": "One complete approved source sentence."}],
                                       "semantic_revision": {"attempts": 0, "verdict": "fit", "policy_version": POLICY_VERSION,
                                                             "cost": {"policy_version": POLICY_VERSION}}},
            },
            "story_beats": [], "story_hierarchy": {"critic": {"verdict": "pass"}},
        }, "ollama_hierarchical_story"

    monkeypatch.setattr(director, "_plan_edit_with_cancel", bounded_plan)
    store.update(project_id, lambda current: current["settings"].update({
        "target_duration": 20, "duration_mode": "target",
    }))
    result = director.analyze_project(context(), project_id, store, settings)
    draft = store.load(project_id)["draft"]
    assert draft["output_duration"] == 8
    assert draft["duration_review"]["target_feasibility"]["supported_seconds"] == 8
    assert draft["duration_review"]["target_feasibility"]["status"] == "limited"
    assert draft["quality_review"]["needs_review"] is True
    assert "target_feasibility" in [row["type"] for row in draft["quality_review"]["warnings"]]
    assert "8.0s of the requested 20.0s" in result["message"]
    assert "first edit is ready" not in result["message"]
