from __future__ import annotations

import math
from pathlib import Path

import pytest

from cutroom.effects import (
    AUTOMATIC_MAX_EFFECTS,
    HARD_MAX_EFFECTS,
    PIPELINE_VERSION,
    SUPPORTED_EFFECTS,
    build_effect_stages,
    build_filter_expression,
    compile_automatic_effects,
    compile_effects,
    normalize_effects,
    plan_automatic_effects,
)
from cutroom.render import build_filter_graph


def test_whitelist_drops_unknown_and_never_passes_raw_ffmpeg():
    raw = [
        {
            "type": "emphasis,drawtext=text=hacked",
            "start": 0,
            "end": 2,
            "strength": 1,
            "filter": "movie=/secret,sendcmd=f=/tmp/input",
        },
        {
            "type": "emphasis",
            "start": 1,
            "end": 3,
            "strength": 0.5,
            "filter": "drawtext=text=also-hacked",
        },
    ]
    compiled = compile_effects(raw, 5)
    assert compiled["effects"] == [
        {"type": "emphasis", "start": 1.0, "end": 3.0, "strength": 0.5}
    ]
    assert compiled["filter_expression"] == (
        "eq=contrast=1.0600:brightness=0.0090:saturation=1.1400:"
        "enable='between(t,1.000,3.000)'"
    )
    serialized = repr(compiled)
    assert "drawtext" not in serialized
    assert "movie=" not in serialized
    assert "sendcmd" not in serialized


def test_normalization_clamps_time_strength_duration_and_hard_count():
    raw = [
        {"type": "emphasis", "start": -50, "end": 50, "strength": 999},
        *[
            {"type": "emphasis", "start": 5 + index * 5, "end": 9 + index * 5, "strength": 0.4}
            for index in range(30)
        ],
    ]
    effects = normalize_effects(raw, 200, max_effects=10_000)
    assert len(effects) <= HARD_MAX_EFFECTS
    assert effects[0] == {"type": "emphasis", "start": 0.0, "end": 4.0, "strength": 1.0}
    assert all(0 <= row["start"] < row["end"] <= 200 for row in effects)
    assert all(row["end"] - row["start"] <= 4.0 for row in effects)
    assert all(0.0 < row["strength"] <= 1.0 for row in effects)


def test_overlap_and_per_type_caps_are_deterministic_independent_of_input_order():
    rows = [
        {"type": "dim", "start": 0.0, "end": 3.0, "strength": 0.5},
        {"type": "emphasis", "start": 0.0, "end": 2.0, "strength": 0.5},
        {"type": "monochrome", "start": 1.0, "end": 5.0, "strength": 0.8},
        {"type": "vignette", "start": 5.0, "end": 7.0, "strength": 0.4},
        {"type": "vignette", "start": 8.0, "end": 10.0, "strength": 0.4},
        {"type": "vignette", "start": 11.0, "end": 13.0, "strength": 0.4},
    ]
    forward = normalize_effects(rows, 20)
    backward = normalize_effects(list(reversed(rows)), 20)
    assert forward == backward
    assert forward[0]["type"] == "emphasis"
    assert sum(row["type"] == "vignette" for row in forward) == 2
    assert all(current["start"] >= previous["end"] for previous, current in zip(forward, forward[1:]))


@pytest.mark.parametrize("duration", [None, 0, -1, math.nan, math.inf, "bad"])
def test_invalid_duration_is_a_safe_noop(duration):
    raw = [{"type": "emphasis", "start": 0, "end": 1, "strength": 0.5}]
    assert normalize_effects(raw, duration) == []
    assert build_filter_expression(raw, duration) is None


def test_malformed_numeric_values_are_ignored_without_leaking_text():
    rows = [
        {"type": "emphasis", "start": "0,drawtext=x", "end": 2, "strength": 0.5},
        {"type": "dim", "start": 0, "end": math.inf, "strength": 0.5},
        {"type": "monochrome", "start": 0, "end": 2, "strength": math.nan},
        {"type": "vignette", "start": True, "end": 2, "strength": 0.5},
    ]
    stages = build_effect_stages(rows, 5)
    assert len(stages) == 1
    assert stages[0]["type"] == "monochrome"
    assert stages[0]["strength"] == 0.85
    assert "drawtext" not in stages[0]["filter"]


def test_all_supported_effects_compile_to_bounded_known_filters():
    rows = [
        {"type": effect_type, "start": index * 2.0, "end": index * 2.0 + 1.5}
        for index, effect_type in enumerate(SUPPORTED_EFFECTS)
    ]
    stages = build_effect_stages(rows, 20)
    assert {row["type"] for row in stages} == set(SUPPORTED_EFFECTS)
    assert all("enable='between(t," in row["filter"] for row in stages)
    assert all(";" not in row["filter"] and "[" not in row["filter"] for row in stages)
    assert build_filter_expression(rows, 20) == ",".join(row["filter"] for row in stages)


def _story_project():
    return {
        "draft": {
            "goal": "short",
            "output_duration": 15.0,
            "keep_ranges": [{"start": 0, "end": 5}, {"start": 10, "end": 20}],
            "highlight_ids": ["s-result"],
        },
        "analysis": {
            "story_beats": [
                {
                    "id": "hook",
                    "start": 1,
                    "end": 4,
                    "role_hint": "hook",
                    "editorial_score": 0.8,
                    "segment_ids": ["s-hook"],
                },
                {
                    "id": "removed",
                    "start": 6,
                    "end": 9,
                    "role_hint": "result",
                    "editorial_score": 1.0,
                    "segment_ids": ["s-removed"],
                },
                {
                    "id": "result",
                    "start": 12,
                    "end": 16,
                    "role_hint": "result",
                    "editorial_score": 0.9,
                    "segment_ids": ["s-result"],
                },
                {
                    "id": "ending",
                    "start": 18,
                    "end": 20,
                    "role_hint": "conclusion",
                    "editorial_score": 0.75,
                    "segment_ids": ["s-end"],
                },
            ]
        },
    }


def test_automatic_plan_maps_source_beats_to_final_timeline_and_skips_removed_beats():
    project = _story_project()
    planned = plan_automatic_effects(project)
    assert planned == plan_automatic_effects(project)
    assert 1 <= len(planned) <= AUTOMATIC_MAX_EFFECTS
    assert any(row["type"] == "emphasis" and row["start"] < 5 for row in planned)
    # Source 12..16 maps through the 5-second first keep to final 7..11.
    assert any(row["type"] == "emphasis" and 7 <= row["start"] < row["end"] <= 11 for row in planned)
    assert all(0 <= row["start"] < row["end"] <= 15 for row in planned)
    assert not any(5 <= row["start"] < 7 for row in planned)


def test_automatic_plan_is_tolerant_and_keeps_longform_untouched():
    assert plan_automatic_effects(None) == []
    assert plan_automatic_effects({}) == []
    project = _story_project()
    project["draft"]["goal"] = "youtube"
    assert plan_automatic_effects(project) == []


def test_automatic_compile_returns_versioned_pre_caption_payload():
    compiled = compile_automatic_effects(_story_project(), max_effects=999)
    assert compiled["version"] == PIPELINE_VERSION
    assert compiled["duration"] == 15.0
    assert len(compiled["effects"]) <= AUTOMATIC_MAX_EFFECTS
    assert compiled["filter_expression"] == ",".join(
        row["filter"] for row in compiled["stages"]
    )
    assert all(set(row) == {"type", "start", "end", "strength", "filter"} for row in compiled["stages"])


def test_automatic_compile_tolerates_a_malformed_count_limit():
    compiled = compile_automatic_effects(_story_project(), max_effects="not-a-number")
    assert 1 <= len(compiled["effects"]) <= AUTOMATIC_MAX_EFFECTS


def test_render_inserts_safe_effects_after_composition_and_before_captions(tmp_path: Path):
    project = _story_project()
    project["sources"] = {
        "A": {"duration": 20.0, "has_audio": False, "has_video": True, "width": 1280, "height": 720},
        "B": None,
    }
    project["settings"] = {"editorial_effects": True}
    project["manual"] = {"crop": {}, "source_mixer": {}}
    project["draft"].update({
        "camera_plan": [
            {"start": 0.0, "end": 5.0, "camera": "A"},
            {"start": 10.0, "end": 20.0, "camera": "A"},
        ],
        "audio_source": "A",
    })

    graph, maps, has_audio = build_filter_graph(project, 720, 1280, tmp_path / "captions.ass")

    assert "[vcat]" in graph and "[vbase]" in graph
    assert "eq=contrast=" in graph
    assert graph.index("eq=contrast=") < graph.index("ass=filename=")
    assert maps == ["-map", "[vfinal]"]
    assert has_audio is False

    project["settings"]["editorial_effects"] = False
    disabled_graph, _, _ = build_filter_graph(project, 720, 1280)
    assert "[vbase]" not in disabled_graph
    assert "eq=contrast=" not in disabled_graph
