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
