from __future__ import annotations

import copy
import threading
from pathlib import Path

import pytest

from cutroom import director
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
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
            "story_beats": [], "story_hierarchy": {"fixture": True},
        }, "ollama_hierarchical_story"

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
        current["analysis"]["story_hierarchy"]["critic"] = {"verdict": "pass", "issues": []}
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
    assert store.load(project_id)["draft"]["duration_review"]["duration_mode"]=="target"
    director.analyze_project(context(),project_id,store,settings)
    assert calls == {"transcribe":1,"plan":2}
