from __future__ import annotations

import copy
from pathlib import Path

import pytest

from cutroom.composition import FACE_LAYOUT_VERSION
from cutroom.director import (
    _bounded_cuts,
    _camera_plan,
    _camera_plan_for_layout,
    _build_reel_candidates,
    _cut_candidates,
    _effective_brief,
    _effective_embedded_candidate,
    _explicit_source_layout,
    _prepared_vision_is_reusable,
    _safe_automatic_sync,
)
from cutroom.intelligence import enrich_segments
from cutroom.utils import range_duration, invert_ranges


def _segments():
    return enrich_segments([
        {"id": "s1", "start": 0, "end": 2, "text": "Um today we begin", "words": [{"start": 0, "end": .2, "word": "Um"}, {"start": .5, "end": .8, "word": "today"}], "avg_logprob": -.1},
        {"id": "s2", "start": 2, "end": 6, "text": "Today we begin with the complete explanation.", "words": [], "avg_logprob": -.1},
        {"id": "s3", "start": 6, "end": 10, "text": "This is the important useful answer.", "words": [], "avg_logprob": -.1},
    ], "en")


def test_prepared_vision_reuse_requires_generation_and_enough_samples():
    profile = {
        "version": FACE_LAYOUT_VERSION,
        "source_generation": "source-generation",
        "sample_count": 12,
    }
    assert _prepared_vision_is_reusable(profile, "source-generation", 12) is True
    assert _prepared_vision_is_reusable(profile, "source-generation", 20) is False
    assert _prepared_vision_is_reusable(profile, "", 12) is False
    assert _prepared_vision_is_reusable({**profile, "source_generation": ""}, "", 12) is False
    assert _prepared_vision_is_reusable({**profile, "sample_count": "invalid"}, "source-generation", 12) is False


def test_bounded_cuts_respect_balanced_limit_for_long_form():
    segments = _segments()
    candidates = _cut_candidates(segments, {"remove_ids": ["s1", "s2"]}, [{"start": 10, "end": 16}], "balanced")
    cuts, _ = _bounded_cuts(candidates, 20, "balanced", "clean", 20, [])
    assert range_duration(cuts) <= 20 * .34 + .1
    assert range_duration(invert_ranges(cuts, 20)) >= 20 * .66 - .1


def test_manual_cuts_are_preserved():
    cuts, counts = _bounded_cuts([], 10, "gentle", "clean", 10, [{"start": 3, "end": 4}])
    assert cuts == [{"start": 3.0, "end": 4.0}]
    assert counts["manual"] == 1


def test_camera_plan_avoids_excessive_switches():
    plan = _camera_plan([{"start": 0, "end": 30}], True, "auto", "balanced", [2, 7, 9, 14, 18, 22, 28])
    assert plan[0]["camera"] == "screen"
    assert {item["camera"] for item in plan} <= {"screen", "camera"}
    assert len(plan) <= 5
    assert all(item["end"] > item["start"] for item in plan)


def test_cached_low_confidence_sync_is_neutralized_but_manual_sync_is_not():
    automatic = _safe_automatic_sync({"offset": 18.0, "confidence": 0.02, "method": "audio_cross_correlation"})
    manual = _safe_automatic_sync({"offset": 1.25, "confidence": 1.0, "method": "manual"})

    assert automatic["offset"] == 0.0
    assert automatic["measured_offset"] == 18.0
    assert automatic["reliable"] is False
    assert manual["offset"] == 1.25


def test_reel_candidates_reuse_story_beats_and_produce_distinct_valid_edits():
    segments = [
        {"id": f"s{i}", "start": i * 20.0, "end": i * 20.0 + 8.0, "text": f"complete moment {i}", "editorial_score": .55 + i * .03}
        for i in range(8)
    ]
    beats = [
        {"id": "b1", "start": 42.0, "end": 50.0, "text": "first strong payoff", "editorial_score": .96, "novelty": .9, "role_hint": "hook"},
        {"id": "b2", "start": 122.0, "end": 130.0, "text": "different late highlight", "editorial_score": .91, "novelty": .9, "role_hint": "conclusion"},
    ]
    project = {"sources": {"A": {"duration": 180.0}, "B": None}, "manual": {"cuts": [], "camera_overrides": []}}
    draft = {
        "goal": "short", "source_duration": 180.0, "target_duration": 30.0,
        "output_duration": 30.0, "keep_ranges": [{"start": 0.0, "end": 30.0}],
        "cuts": [{"start": 30.0, "end": 180.0}],
        "camera_plan": [{"start": 0.0, "end": 30.0, "camera": "A"}],
        "ai_camera_plan": [{"start": 0.0, "end": 30.0, "camera": "A"}],
        "layout": "A", "pace": "dynamic", "summary": "main",
    }

    candidates = _build_reel_candidates(project, draft, segments, beats, [], None)

    assert len(candidates) == 3
    assert candidates[0]["id"] == "director_pick"
    assert len({tuple((row["start"], row["end"]) for row in item["keep_ranges"]) for item in candidates}) == 3
    assert all(8.0 <= item["output_duration"] <= 30.05 for item in candidates)
    assert all(all(row["camera"] == "A" for row in item["camera_plan"]) for item in candidates)


def test_explicit_layout_is_stable():
    plan = _camera_plan([{"start": 0, "end": 4}, {"start": 7, "end": 12}], True, "stacked", "dynamic", [])
    assert all(item["camera"] == "stacked" for item in plan)


def test_explicit_source_mixer_layout_wins_over_style_and_youtube_defaults():
    project = {
        "sources": {"A": {"duration": 20}, "B": {"duration": 20}},
        "settings": {"edit_style": "stream_highlights", "goal": "youtube", "layout": "A"},
        "manual": {"source_mixer": {
            "screen_slot": "B", "camera_slot": "A", "primary_role": "screen", "audio_slot": "A",
            "default_layout": "stacked",
        }},
    }

    assert _explicit_source_layout(project) == "stacked"
    assert _effective_brief(project)["layout"] == "stacked"
    project["manual"]["source_mixer"]["default_layout"] = "auto"
    assert _effective_brief(project)["layout"] == "auto"
    project["manual"]["source_mixer"]["default_layout"] = "screen"
    assert _effective_brief(project)["layout"] == "screen"
    project["manual"]["source_mixer"]["default_layout"] = "camera"
    assert _effective_brief(project)["layout"] == "camera"


def test_missing_explicit_source_layout_uses_streamer_two_source_policy():
    project = {
        "sources": {"A": {"duration": 20}, "B": {"duration": 20}},
        "settings": {"edit_style": "stream_highlights", "goal": "youtube", "layout": "stacked"},
        "manual": {"source_mixer": {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A",
        }},
    }

    assert _explicit_source_layout(project) is None
    assert _effective_brief(project)["layout"] == "pip"


def test_focus_speaker_refinement_updates_the_explicit_semantic_camera_choice(monkeypatch):
    from cutroom import director

    class Context:
        def checkpoint(self):
            return None

    class Store:
        def __init__(self):
            self.project = {
                "sources": {"A": {"duration": 20}, "B": {"duration": 20}},
                "settings": {"target_duration": 60},
                "manual": {"source_mixer": {
                    "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A",
                    "default_layout": "stacked",
                }},
            }

        def load(self, _project_id):
            return copy.deepcopy(self.project)

        def update(self, _project_id, mutate):
            mutate(self.project)
            return copy.deepcopy(self.project)

    captured = {}
    store = Store()

    def fake_analyze(_context, _project_id, received_store, _settings, patch):
        captured["project"] = received_store.load("project")
        captured["patch"] = patch
        return {"ok": True}

    monkeypatch.setattr(director, "analyze_project", fake_analyze)
    assert director.refine_project(Context(), "project", store, object(), "focus_speaker") == {"ok": True}
    assert captured["project"]["manual"]["source_mixer"]["default_layout"] == "camera"
    assert captured["patch"] == {}

    def failed_analyze(*_args, **_kwargs):
        raise RuntimeError("analysis failed")

    monkeypatch.setattr(director, "analyze_project", failed_analyze)
    failed_store = Store()
    with pytest.raises(RuntimeError, match="analysis failed"):
        director.refine_project(Context(), "project", failed_store, object(), "focus_speaker")
    assert failed_store.project["manual"]["source_mixer"]["default_layout"] == "stacked"

    absent_store = Store()
    absent_store.project["manual"]["source_mixer"].pop("default_layout")
    with pytest.raises(RuntimeError, match="analysis failed"):
        director.refine_project(Context(), "project", absent_store, object(), "focus_speaker")
    assert "default_layout" not in absent_store.project["manual"]["source_mixer"]


def test_manual_camera_override_survives_a_new_ai_plan_without_touching_neighbors():
    from cutroom.editing import apply_camera_overrides

    plan = apply_camera_overrides(
        [{"start": 0, "end": 5, "camera": "A"}, {"start": 5, "end": 10, "camera": "B"}],
        [{"start": 0, "end": 10}],
        [{"start": 3, "end": 7, "layout": "stacked"}],
        has_b=True,
    )

    assert plan == [
        {"start": 0.0, "end": 3.0, "camera": "A"},
        {"start": 3.0, "end": 7.0, "camera": "stacked"},
        {"start": 7.0, "end": 10.0, "camera": "B"},
    ]


def test_single_source_analysis_with_null_sync_can_build_render_graph():
    from cutroom.render import build_filter_graph

    project = {
        "sources": {
            "A": {"duration": 4, "width": 640, "height": 360, "has_audio": True},
            "B": None,
        },
        "settings": {"aspect": "9:16", "resolution": "720"},
        "analysis": {"sync": None, "vision": {}, "transcript": {"segments": []}},
        "manual": {"crop": {}},
        "draft": {
            "keep_ranges": [{"start": 0, "end": 4}],
            "camera_plan": [{"start": 0, "end": 4, "camera": "A"}],
        },
    }
    graph, maps, has_audio = build_filter_graph(project, 720, 1280)
    assert "[vout]" in graph
    assert maps == ["-map", "[vout]", "-map", "[aout]"]
    assert has_audio is True


def test_transcription_failure_degrades_to_safe_fallback(monkeypatch):
    from cutroom import director

    def fail(*args, **kwargs):
        raise RuntimeError("whisper unavailable")

    monkeypatch.setattr(director, "transcribe", fail)
    transcript, warning = director._transcribe_safely(Path("missing.mp4"), None, "auto")
    assert transcript["segments"] == []
    assert transcript["language"] == "unknown"
    assert warning and "whisper unavailable" in warning


def test_short_target_is_a_real_upper_bound_for_long_source():
    from cutroom.director import _enforce_short_target
    segments = []
    cursor = 0.0
    for index in range(120):
        segments.append({
            "id": f"s{index}", "start": cursor, "end": cursor + 5.0,
            "editorial_score": 0.95 if index in {10, 11, 12, 80, 81} else 0.35 + (index % 7) * 0.04,
            "filler_ratio": 0.0, "repeat_score": 0.0, "false_start": False,
        })
        cursor += 5.0
    decision = {
        "keep_ids": [item["id"] for item in segments],
        "highlight_ids": ["s10", "s11", "s80"],
        "opening_id": "s10", "closing_id": "s81",
    }
    cuts, count = _enforce_short_target([], segments, decision, 600.0, 60.0)
    output = range_duration(invert_ranges(cuts, 600.0))
    assert output <= 60.05
    assert output >= 54.0
    assert count > 0


def test_short_bounded_cut_budget_can_remove_more_than_88_percent():
    candidates = [{"start": index * 5.0, "end": index * 5.0 + 5.0, "reason": "low_value", "priority": 1.0} for index in range(110)]
    cuts, _ = _bounded_cuts(candidates, 600.0, "balanced", "short", 60.0, [])
    assert range_duration(cuts) >= 540.0 - 5.0


def test_youtube_camera_plan_can_be_forced_to_source_a():
    plan = _camera_plan([{"start": 0, "end": 30}], True, "A", "balanced", [5, 10, 15])
    assert plan == [{"start": 0, "end": 30, "camera": "A"}]


def test_single_source_auto_layout_never_duplicates_an_embedded_candidate():
    ranges = [{"start": 0, "end": 30}]
    plan, confirmed = _camera_plan_for_layout(
        ranges,
        False,
        "auto",
        "balanced",
        [],
        {"x": .75, "y": .05, "w": .2, "h": .25, "confidence": .95},
    )
    assert plan == [{"start": 0, "end": 30, "camera": "A"}]
    assert confirmed is False


def test_embedded_layout_requires_explicit_choice_and_candidate():
    ranges = [{"start": 0, "end": 30}]
    candidate = {"x": .75, "y": .05, "w": .2, "h": .25, "confidence": .95}
    plan, confirmed = _camera_plan_for_layout(ranges, False, "embedded_stack", "balanced", [], candidate)
    assert plan == [{"start": 0, "end": 30, "camera": "embedded_stack"}]
    assert confirmed is True

    missing_plan, missing_confirmed = _camera_plan_for_layout(
        ranges, False, "embedded_stack", "balanced", [], None,
    )
    assert missing_plan == [{"start": 0, "end": 30, "camera": "A"}]
    assert missing_confirmed is False


def test_embedded_stack_render_uses_content_focus():
    from cutroom.render import build_filter_graph
    project = {
        "sources": {"A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True}, "B": None},
        "settings": {"aspect": "9:16", "resolution": "720"},
        "analysis": {"sync": None, "vision": {"version": FACE_LAYOUT_VERSION, "embedded_camera": {
            "x": .76, "y": .68, "w": .20, "h": .27, "content_focus": {"x": .34, "y": .34}
        }}},
        "manual": {"crop": {}},
        "draft": {
            "layout": "embedded_stack",
            "embedded_layout_confirmed": True,
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "embedded_stack"}],
        },
    }
    graph, _, _ = build_filter_graph(project, 720, 1280)
    assert "vstack=inputs=2" in graph
    assert "(iw-ow)*0.34000" in graph


def _long_story_segments(duration: float = 600.0):
    from cutroom.intelligence import enrich_segments
    rows = []
    step = 5.0
    count = int(duration / step)
    special = {10: "hook", 58: "middle proof", 104: "late payoff"}
    for index in range(count):
        text = special.get(index, f"context point {index}")
        rows.append({
            "id": f"s{index}", "start": index * step, "end": (index + 1) * step,
            "text": text, "words": [], "avg_logprob": -0.1,
        })
    enriched = enrich_segments(rows, "en")
    for index, item in enumerate(enriched):
        item["editorial_score"] = 0.98 if index in special else 0.35 + (index % 9) * 0.025
    return enriched


def test_sixty_second_story_selects_across_entire_source():
    from cutroom.director import _select_short_story_ranges
    segments = _long_story_segments()
    decision = {
        "opening_id": "s10",
        "highlight_ids": ["s10", "s58", "s104"],
        "closing_id": "s104",
        "keep_ids": [item["id"] for item in segments],
    }
    ranges = _select_short_story_ranges(segments, decision, 600.0, 60.0, [])
    assert ranges
    assert min(float(item["start"]) for item in ranges) < 100.0
    assert any(float(item["start"]) > 250.0 for item in ranges)
    assert any(float(item["start"]) > 480.0 for item in ranges)
    assert range_duration(ranges) <= 60.0 * 1.25


def test_three_minute_story_keeps_broader_context_than_sixty_seconds():
    from cutroom.director import _select_short_story_ranges
    segments = _long_story_segments()
    decision = {
        "opening_id": "s10",
        "highlight_ids": ["s10", "s58", "s104"],
        "closing_id": "s104",
        "keep_ids": [item["id"] for item in segments],
    }
    short = _select_short_story_ranges(segments, decision, 600.0, 60.0, [])
    expanded = _select_short_story_ranges(segments, decision, 600.0, 180.0, [])
    assert range_duration(expanded) > range_duration(short) * 1.8
    assert len(expanded) >= len(short)
    assert any(float(item["start"]) > 480.0 for item in expanded)


def test_no_transcript_short_fallback_samples_whole_source_not_head_only():
    from cutroom.director import _fallback_short_story_ranges
    ranges = _fallback_short_story_ranges(600.0, 60.0, [30, 150, 300, 450, 570])
    assert len(ranges) >= 3
    assert any(float(item["start"]) > 400 for item in ranges)
    assert min(float(item["start"]) for item in ranges) > 0.0


def test_nonverbal_highlights_follow_measured_audio_energy():
    from cutroom.director import _select_audio_highlight_ranges

    waveform = []
    energetic_centers = {45.0, 155.0, 265.0, 375.0, 485.0, 575.0}
    for second in range(0, 600, 5):
        energetic = any(abs((second + 2.5) - center) < 8.0 for center in energetic_centers)
        waveform.append({
            "start": float(second), "end": float(second + 5),
            "rms_dbfs": -8.0 if energetic else -48.0,
            "peak_dbfs": -2.0 if energetic else -35.0,
        })
    ranges = _select_audio_highlight_ranges({"waveform": waveform}, 600.0, 60.0, [])
    assert 54.0 <= range_duration(ranges) <= 60.05
    assert any(float(item["start"]) < 70.0 for item in ranges)
    assert any(float(item["start"]) > 450.0 for item in ranges)


def test_final_short_contract_keeps_full_recording_coverage_at_60_and_180():
    from cutroom.director import _select_short_story_ranges, _short_cleanup_cuts_with_floor, _enforce_short_target
    from cutroom.utils import invert_ranges, range_duration
    segments = []
    for index in range(120):
        segments.append({
            "id": f"s{index}", "start": index * 5.0, "end": index * 5.0 + 4.6,
            "text": f"point {index}", "editorial_score": .95 if index in {10, 58, 104} else .45 + (index % 7) * .03,
            "filler_ratio": 0.0, "repeat_score": 0.0, "false_start": False,
        })
    decision = {
        "opening_id": "s10", "highlight_ids": ["s10", "s58", "s104"], "closing_id": "s104",
        "keep_ids": [item["id"] for item in segments],
    }
    results = {}
    for target in (60.0, 180.0):
        story = _select_short_story_ranges(segments, decision, 600.0, target, [])
        cuts, _ = _short_cleanup_cuts_with_floor(invert_ranges(story, 600.0), [], [], 600.0, target)
        cuts, _ = _enforce_short_target(cuts, segments, decision, 600.0, target)
        keep = invert_ranges(cuts, 600.0)
        results[target] = keep
        output = range_duration(keep)
        assert target * .90 <= output <= target + .05
        assert any(float(item["start"]) > 250.0 for item in keep)
        assert any(float(item["start"]) > 480.0 for item in keep)
    assert range_duration(results[180.0]) > range_duration(results[60.0]) * 2.5
    assert len(results[180.0]) > len(results[60.0])


def test_target_enforcer_removes_neighboring_gap_with_rejected_speech():
    from cutroom.director import _enforce_short_target
    from cutroom.utils import invert_ranges, range_duration

    segments = [
        {"id": "opening", "start": 0.0, "end": 6.0, "editorial_score": .95, "filler_ratio": 0, "repeat_score": 0},
        {"id": "weak", "start": 8.0, "end": 12.0, "editorial_score": .05, "filler_ratio": 0, "repeat_score": 0},
        {"id": "closing", "start": 16.0, "end": 22.0, "editorial_score": .90, "filler_ratio": 0, "repeat_score": 0},
    ]
    decision = {
        "opening_id": "opening",
        "closing_id": "closing",
        "highlight_ids": [],
        "keep_ids": ["opening", "weak", "closing"],
    }

    cuts, removed = _enforce_short_target(
        [{"start": 22.0, "end": 30.0}], segments, decision, 30.0, 15.0,
    )
    keeps = invert_ranges(cuts, 30.0)

    assert removed == 1
    assert range_duration(keeps) == 15.0
    assert keeps == [{"start": 0.0, "end": 7.0}, {"start": 14.0, "end": 22.0}]
    assert all(
        any(min(float(keep["end"]), float(segment["end"])) > max(float(keep["start"]), float(segment["start"])) for segment in segments)
        for keep in keeps
    )


def test_embedded_stack_places_facecam_above_gameplay_in_render_graph():
    from cutroom.render import build_filter_graph
    project = {
        "sources": {"A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True}, "B": None},
        "settings": {"aspect": "9:16", "resolution": "720"},
        "analysis": {"sync": None, "vision": {"version": FACE_LAYOUT_VERSION, "embedded_camera": {
            "x": .75, "y": .68, "w": .22, "h": .28,
            "content_focus": {"x": .30, "y": .38}, "facecam_position": "top",
        }}},
        "manual": {"crop": {}},
        "draft": {
            "layout": "embedded_stack",
            "embedded_layout_confirmed": True,
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "embedded_stack"}],
        },
    }
    graph, _, _ = build_filter_graph(project, 720, 1280)
    assert "[face0][content0]vstack=inputs=2" in graph
    assert "content0" in graph and "face0" in graph


def test_legacy_unconfirmed_embedded_draft_renders_source_a_once():
    from cutroom.render import build_filter_graph
    project = {
        "sources": {"A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True}, "B": None},
        "settings": {"aspect": "9:16", "resolution": "720", "layout": "auto"},
        "analysis": {"sync": None, "vision": {"embedded_camera": {
            "x": .2465, "y": .1456, "w": .3111, "h": .3111,
            "content_focus": {"x": .5, "y": .62},
        }}},
        "manual": {"crop": {}},
        # This is the exact unsafe legacy shape: inferred camera plan, no consent.
        "draft": {
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "embedded_stack"}],
        },
    }
    graph, _, _ = build_filter_graph(project, 720, 1280)
    assert "vstack=inputs=2" not in graph
    assert "split=2[amain0][aface0]" not in graph
    assert "[av0]trim=start_frame=0:end_frame=150" in graph


def test_manual_embedded_candidate_beats_trusted_vision_and_survives_youtube_default():
    project = {
        "sources": {"A": {"duration": 5}, "B": None},
        "settings": {"goal": "youtube", "layout": "embedded_stack"},
        "manual": {"embedded_camera": {
            "x": .08, "y": .10, "w": .28, "h": .24,
            "content_focus": {"x": .72, "y": .55},
        }},
    }
    vision = {"version": FACE_LAYOUT_VERSION, "embedded_camera": {
        "x": .70, "y": .05, "w": .22, "h": .24,
        "content_focus": {"x": .30, "y": .50},
    }}

    candidate = _effective_embedded_candidate(project, vision)

    assert candidate is not None
    assert candidate["candidate_source"] == "manual"
    assert candidate["x"] == .08
    assert _effective_brief(project)["layout"] == "embedded_stack"


def test_manual_embedded_rectangle_renders_without_any_vision_detection():
    from cutroom.render import build_filter_graph

    project = {
        "sources": {"A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True}, "B": None},
        "settings": {"aspect": "9:16", "resolution": "720", "layout": "embedded_stack"},
        "analysis": {"sync": None, "vision": {"version": FACE_LAYOUT_VERSION, "embedded_camera": None}},
        "manual": {"crop": {}, "embedded_camera": {
            "x": .72, "y": .06, "w": .24, "h": .24,
            "content_focus": {"x": .32, "y": .58},
        }},
        "draft": {
            "layout": "embedded_stack",
            "embedded_layout_confirmed": True,
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "embedded_stack"}],
        },
    }

    graph, _, _ = build_filter_graph(project, 720, 1280)

    assert "[face0][content0]vstack=inputs=2" in graph
    assert "(iw-ow)*0.32000" in graph


def test_two_source_stack_uses_semantic_camera_top_and_screen_bottom_after_swap():
    from cutroom.render import build_filter_graph

    value = {
        "sources": {
            "A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True},
            "B": {"duration": 5, "width": 1280, "height": 720, "has_audio": True},
        },
        "settings": {"aspect": "9:16", "resolution": "720"},
        "analysis": {"sync": {"offset": 0.0}},
        "manual": {"crop": {}, "source_mixer": {
            "screen_slot": "B", "camera_slot": "A", "primary_role": "screen", "audio_slot": "A",
        }},
        "draft": {
            "audio_source": "A",
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "stacked"}],
        },
    }

    graph, _, _ = build_filter_graph(value, 720, 1280)
    assert "[av0]trim=start_frame=0:end_frame=150" in graph
    assert "[bv0]trim=start_frame=0:end_frame=150" in graph
    assert "[face0][screen0]vstack=inputs=2" in graph
    assert "[av0]trim=start_frame=0:end_frame=150,setpts=PTS-STARTPTS,scale=720:384" in graph
    assert "[bv0]trim=start_frame=0:end_frame=150,setpts=PTS-STARTPTS,scale=720:896" in graph


def test_first_slot_controls_top_and_left_while_primary_controls_stacked_size():
    from cutroom.render import build_filter_graph

    value = {
        "sources": {
            "A": {"duration": 5, "width": 1920, "height": 1080, "has_audio": True},
            "B": {"duration": 5, "width": 1280, "height": 720, "has_audio": True},
        },
        "settings": {"aspect": "9:16", "resolution": "720", "editorial_effects": False},
        "analysis": {"sync": {"offset": 0.0}},
        "manual": {"crop": {}, "source_mixer": {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A",
            "first_slot": "A",
        }},
        "draft": {
            "audio_source": "A",
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "stacked"}],
        },
    }

    a_first, _, _ = build_filter_graph(value, 720, 1280)
    assert "[screen0][face0]vstack=inputs=2" in a_first
    assert "scale=720:896" in a_first  # primary screen stays larger regardless of order
    assert "scale=720:384" in a_first

    value["manual"]["source_mixer"]["first_slot"] = "B"
    b_first, _, _ = build_filter_graph(value, 720, 1280)
    assert "[face0][screen0]vstack=inputs=2" in b_first
    assert "scale=720:896" in b_first

    value["draft"]["camera_plan"][0]["camera"] = "side_by_side"
    b_left, _, _ = build_filter_graph(value, 720, 1280)
    assert "[face0][screen0]hstack=inputs=2" in b_left
    value["manual"]["source_mixer"]["first_slot"] = "A"
    a_left, _, _ = build_filter_graph(value, 720, 1280)
    assert "[screen0][face0]hstack=inputs=2" in a_left


def test_semantic_screen_draft_follows_a_later_source_role_swap():
    from cutroom.render import build_filter_graph

    value = {
        "sources": {
            "A": {"duration": 5, "width": 640, "height": 360, "has_audio": True},
            "B": {"duration": 5, "width": 640, "height": 360, "has_audio": True},
        },
        "settings": {"aspect": "16:9", "resolution": "720"},
        "analysis": {"sync": {"offset": 0.0}},
        "manual": {"crop": {}, "source_mixer": {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A",
            "default_layout": "screen",
        }},
        "draft": {
            "audio_source": "A",
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "screen"}],
        },
    }

    before, _, _ = build_filter_graph(value, 1280, 720)
    assert "[av0]trim=start_frame=0:end_frame=150" in before
    value["manual"]["source_mixer"].update({"screen_slot": "B", "camera_slot": "A"})
    after, _, _ = build_filter_graph(value, 1280, 720)
    assert "[bv0]trim=start_frame=0:end_frame=150" in after


def test_audio_source_b_is_aligned_to_source_a_timeline():
    from cutroom.render import build_filter_graph

    value = {
        "sources": {
            "A": {"duration": 5, "width": 640, "height": 360, "has_audio": True},
            "B": {"duration": 5, "width": 640, "height": 360, "has_audio": True},
        },
        "settings": {"aspect": "16:9", "resolution": "720"},
        "analysis": {"sync": {"offset": 0.5}},
        "manual": {"crop": {}, "source_mixer": {
            "screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "B", "sync_offset": 0.25,
        }},
        "draft": {
            "audio_source": "A",
            "keep_ranges": [{"start": 0, "end": 5}],
            "camera_plan": [{"start": 0, "end": 5, "camera": "A"}],
            "audio_plan": [{"start": 0, "end": 5, "gain_db": 6}],
        },
    }

    graph, _, has_audio = build_filter_graph(value, 1280, 720)
    assert has_audio is True
    assert "[1:a]asetpts=PTS-STARTPTS,adelay=250:all=1,apad,atrim=duration=5.000000" in graph
    assert "[amaster]anull[aa0]" in graph
    assert "volume=" not in graph
