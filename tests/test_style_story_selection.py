from __future__ import annotations

import json

import pytest

from cutroom import director, intelligence
from cutroom.edit_styles import enrich_brief_with_style, get_edit_style
from cutroom.utils import invert_ranges, range_duration


def policy(style_id):
    return get_edit_style(style_id)["selection_policy"]


def test_single_clutch_bridges_action_between_semantic_setup_and_payoff():
    segments = [
        {"id": "setup", "start": 100.0, "end": 106.0},
        {"id": "payoff", "start": 128.0, "end": 135.0},
    ]
    decision = {"story_ranges": [dict(row) for row in segments]}

    selected = director._select_short_story_ranges(
        segments, decision, 300.0, 60.0,
        selection_policy=policy("competitive_clutch"),
    )

    assert selected == [{"start": 100.0, "end": 135.0}]
    candidates = [
        {"start": 106.0, "end": 128.0, "reason": "silence"},
        {"start": 101.0, "end": 104.0, "reason": "low_value"},
    ]
    cleanup = director._style_cleanup_candidates(candidates, selected, policy("competitive_clutch"))
    assert cleanup == []
    # A user's explicit timeline cut still wins over the style's protection.
    cuts, _ = director._short_cleanup_cuts_with_floor(
        invert_ranges(selected, 300.0), cleanup,
        [{"start": 114.0, "end": 116.0}], 300.0, 60.0,
    )
    assert invert_ranges(cuts, 300.0) == [
        {"start": 100.0, "end": 114.0}, {"start": 116.0, "end": 135.0},
    ]


def test_commentary_keeps_neighboring_question_explanation_and_conclusion():
    segments = [
        {"id": "q", "start": 100.0, "end": 104.0, "text": "Why does this work?", "editorial_score": 0.3},
        {"id": "e", "start": 105.0, "end": 118.0, "text": "Let me show the explanation.", "editorial_score": 0.8},
        {"id": "c", "start": 120.0, "end": 124.0, "text": "So the answer is the timing.", "editorial_score": 0.4},
        {"id": "other", "start": 210.0, "end": 218.0, "text": "A separate topic.", "editorial_score": 0.7},
    ]
    beats = [
        {**row, "role_hint": role}
        for row, role in zip(segments, ["hook", "example", "conclusion", None])
    ]
    selected = director._select_short_story_ranges(
        segments, {"highlight_ids": ["e"], "opening_id": "q", "closing_id": "c"},
        300.0, 60.0, selection_policy=policy("stream_commentary"), story_beats=beats,
    )

    assert selected == [{"start": 98.0, "end": 126.0}]
    assert range_duration(selected) < 60.0


@pytest.mark.parametrize("style_id,expected", [
    ("competitive_clutch", [{"start": 34.0, "end": 48.0}]),
    ("reaction_burst", [{"start": 36.0, "end": 48.0}]),
    ("stream_highlights", [
        {"start": 37.0, "end": 47.5},
        {"start": 137.0, "end": 147.5},
        {"start": 237.0, "end": 247.5},
    ]),
])
def test_nonverbal_style_changes_event_count_and_context_without_quiet_padding(style_id, expected):
    waveform = [
        {
            "start": float(second), "end": float(second + 1),
            "rms_dbfs": -8.0 if second // 5 in {8, 28, 48} else -48.0,
            "peak_dbfs": -2.0 if second // 5 in {8, 28, 48} else -38.0,
        }
        for second in range(300)
    ]

    selected = director._select_audio_highlight_ranges(
        {"waveform": waveform}, 300.0, 60.0, pace="dynamic", selection_policy=policy(style_id),
    )

    assert selected == expected
    assert range_duration(selected) < 60.0


def test_short_complete_semantic_story_is_kept_without_unrelated_padding():
    segment = {"id": "complete", "start": 100.0, "end": 116.0}
    for seed in (0, 42):
        selected = director._select_short_story_ranges(
            [segment], {"story_ranges": [segment]}, 300.0, 60.0,
            selection_policy=policy("stream_commentary"), selection_seed=seed, force_variation=True,
        )
        assert selected == [{"start": 100.0, "end": 116.0}]


@pytest.mark.parametrize("style_id", ["competitive_clutch", "reaction_burst", "stream_commentary"])
def test_single_moment_style_does_not_join_distant_semantic_stories(style_id):
    segments = [
        {"id": "other", "start": 30.0, "end": 40.0, "editorial_score": 0.3},
        {"id": "setup", "start": 220.0, "end": 225.0, "editorial_score": 0.8},
        {"id": "payoff", "start": 225.0, "end": 235.0, "editorial_score": 0.9},
    ]
    decision = {
        "story_ranges": [{"start": 30.0, "end": 40.0}, {"start": 220.0, "end": 235.0}],
        "highlight_ids": ["payoff"], "opening_id": "setup", "closing_id": "payoff",
    }
    selected = director._select_short_story_ranges(
        segments, decision, 300.0, 60.0, selection_policy=policy(style_id),
    )
    assert selected == [{"start": 220.0, "end": 235.0}]


def test_highlight_moment_limit_applies_to_semantic_selection():
    segments = [{"id": f"s{i}", "start": float(i * 60), "end": float(i * 60 + 8),
                 "editorial_score": float(i) / 10} for i in range(5)]
    selected = director._select_short_story_ranges(
        segments, {"story_ranges": segments}, 300.0, 60.0,
        selection_policy=policy("stream_highlights"),
    )
    assert selected == [{"start": 120.0, "end": 128.0}, {"start": 180.0, "end": 188.0},
                        {"start": 240.0, "end": 248.0}]


def captured_anchor_structure():
    """Only anonymous IDs/times from a completed local planning result."""
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
        "story_ranges": [
            {"start": 1.73, "end": 16.03, "beat_id": "b0001"},
            {"start": 40.08, "end": 43.26, "beat_id": "b0003"},
        ],
    }
    return segments, decision


def test_commentary_preserves_planned_ending_when_separate_story_parts_fit_budget():
    segments, decision = captured_anchor_structure()
    selected = director._select_short_story_ranges(
        segments, decision, 45.067, 30.0, selection_policy=policy("stream_commentary"),
    )
    assert selected == [{"start": 1.73, "end": 16.03}, {"start": 40.08, "end": 43.26}]
    assert range_duration(selected) == pytest.approx(17.48)
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, segments, selected, 45.067,
        decision=decision, selection_policy=policy("stream_commentary"),
    )
    assert review["needs_review"] is True
    assert [row["type"] for row in review["warnings"]] == ["style_moment_constraint"]


def test_final_review_exposes_planned_ending_lost_to_unavoidable_budget():
    segments, decision = captured_anchor_structure()
    selected = director._select_short_story_ranges(
        segments, decision, 45.067, 15.0, selection_policy=policy("stream_commentary"),
    )
    assert selected == [{"start": 1.73, "end": 16.03}]
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, segments, selected, 45.067,
        decision=decision, selection_policy=policy("stream_commentary"),
    )
    assert review["needs_review"] is True
    assert [row["type"] for row in review["warnings"]] == ["story_anchor_missing"]


def test_final_review_accepts_an_intact_connected_planned_story():
    segments, decision = captured_anchor_structure()
    decision["closing_id"] = "s0004"
    selected = [{"start": 1.73, "end": 16.03}]
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, segments, selected, 45.067,
        decision=decision, selection_policy=policy("stream_commentary"),
    )
    assert review["needs_review"] is False
    assert review["warnings"] == []


@pytest.mark.parametrize("style_id", ["competitive_clutch", "stream_commentary", "funny_moments"])
def test_ai_story_producer_uses_the_selected_style_structure(monkeypatch, style_id):
    class Settings:
        ai = {}

    captured = {}

    def respond(_settings, payload, *_args):
        captured.update(payload)
        return {"narrative": "Complete moment", "slots": [
            {"purpose": "complete moment", "chapter_ids": ["chapter"], "desired_seconds": 30},
        ]}

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    brief = enrich_brief_with_style({"edit_style": style_id, "target_duration": 60})
    intelligence._build_story_plan(Settings(), [{"id": "chapter"}], {}, brief, "fixture")

    system = captured["messages"][0]["content"]
    selected_policy = policy(style_id)
    assert " -> ".join(selected_policy["story_structure"]) in system
    assert f"at most {selected_policy['max_moments']} distinct complete moment(s)" in system
    passed_brief = json.loads(captured["messages"][1]["content"])["brief"]
    assert "Do not invent missing action" in passed_brief["style_profile"]["guidance"]
