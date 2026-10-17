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
    decision["story_ranges"] = decision["story_ranges"][:1]
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
        required_roles = json.loads(payload["messages"][1]["content"])["brief"]["style_profile"]["selection_policy"]["story_structure"]
        return {"narrative": "Complete moment", "slots": [
            {"purpose": role, "chapter_ids": ["chapter"], "desired_seconds": 30}
            for role in required_roles
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


def test_single_moment_prefers_sustained_action_over_louder_three_second_spike():
    from test_highlight_diversity import _profile
    evidence = _profile(360, [(10,13,-5,-1), (100,220,-14,-8)], step=1)
    selected = director._select_audio_highlight_ranges(
        evidence,360,90,selection_policy=policy("competitive_clutch"),
    )
    assert range_duration(selected) == pytest.approx(90, abs=.001)
    assert len(selected) == 1
    assert selected[0]["start"] >= 94 and selected[0]["end"] <= 223


def test_single_moment_sparse_evidence_keeps_short_event_without_padding():
    from test_highlight_diversity import _profile
    evidence = _profile(360, [(10,13,-5,-1)], step=1)
    selected = director._select_audio_highlight_ranges(
        evidence,360,90,selection_policy=policy("competitive_clutch"),
    )
    assert selected == [{"start":4.0,"end":16.0}]


@pytest.mark.parametrize("style,source,selected,reason", [
    ("competitive_clutch",360,12,"style_moment_limit"),
    ("smart",360,12,"limited_selection"),
    ("smart",73.833,73.833,"source_shorter"),
    ("competitive_clutch",360,90,"near_target"),
])
def test_duration_review_explains_style_source_and_evidence_limits(style,source,selected,reason):
    brief = enrich_brief_with_style({"edit_style":style,"goal":"short","target_duration":90})
    review = director._duration_review(brief,source,selected,nonverbal=True)
    assert review["requested_seconds"] == 90
    assert review["selected_seconds"] == selected
    assert review["reason"] == reason
    assert review["duration_is_ceiling"] is True
    assert review["can_try_more_moments"] == (reason == "style_moment_limit")
    assert director._duration_review({"goal":"youtube","target_duration":90},360,300) is None


def target_policy():
    return enrich_brief_with_style({"edit_style":"competitive_clutch","goal":"short","duration_mode":"target"})["style_profile"]["selection_policy"]


def test_target_highlights_accumulate_distinct_action_without_silent_padding():
    from test_highlight_diversity import _profile
    evidence = _profile(360, [(10,13,-5,-1),(100,121,-14,-8),(180,201,-14,-8),(280,301,-14,-8)], step=1)
    selected = director._select_audio_highlight_ranges(evidence,360,90,selection_policy=target_policy())
    assert range_duration(selected) == pytest.approx(90,abs=.001)
    assert len(selected) == 3
    assert selected == sorted(selected,key=lambda row:row["start"])
    assert all(any(row["start"] < b and row["end"] > a for a,b in [(10,13),(100,121),(180,201),(280,301)]) for row in selected)
    assert director._select_audio_highlight_ranges(_profile(360,[(10,13,-5,-1)],step=1),360,90,selection_policy=target_policy()) == [{"start":4.0,"end":16.0}]
    assert director._select_audio_highlight_ranges(_profile(360,[],step=1),360,90,selection_policy=target_policy()) == []
    assert director._select_audio_highlight_ranges({},360,90,selection_policy=target_policy()) == []


def test_target_budget_caps_sustained_activity_and_short_source_without_repetition():
    from test_highlight_diversity import _profile
    for duration,target,events in [(360,90,[(100,220,-12,-4)]),(45,90,[(8,38,-12,-4)]),(360,90,[(10,25,-5,-1),(100,220,-14,-8)])]:
        selected=director._select_audio_highlight_ranges(_profile(duration,events,step=1),duration,target,selection_policy=target_policy())
        assert 0 < range_duration(selected) <= min(duration,target)+.001
        assert all(0<=row["start"]<row["end"]<=duration for row in selected)
        assert all(a["end"]<=b["start"] for a,b in zip(selected,selected[1:]))
        if duration>target: assert range_duration(selected)==pytest.approx(target,abs=.001)


def test_target_speech_retains_complete_selected_passages_and_style_maximum_remains_explicit():
    segments=[{"id":str(i),"start":start,"end":start+30,"text":"A complete relevant idea.","editorial_score":.8} for i,start in enumerate([10,110,210])]
    decision={"story_ranges":[dict(row) for row in segments]}
    sequence=director._select_short_story_ranges(segments,decision,360,90,selection_policy=target_policy())
    assert sequence==[{"start":10.0,"end":40.0},{"start":110.0,"end":140.0},{"start":210.0,"end":240.0}]
    single=director._select_short_story_ranges(segments,decision,360,90,selection_policy=policy("competitive_clutch"))
    assert len(single)==1 and range_duration(single)==30
    budget=director._select_short_story_ranges(segments,decision,360,50,selection_policy=target_policy())
    assert len(budget)==1 and range_duration(budget)==30  # Never split a complete speech passage to fill50.


def test_duration_intent_survives_style_changes_and_keeps_old_projects_explicit():
    target=enrich_brief_with_style({"edit_style":"competitive_clutch","duration_mode":"target","target_duration":90})
    assert target["style_profile"]["selection_policy"]["max_moments"] is None
    assert "Duration intent overrides" in target["style_profile"]["guidance"]
    other=enrich_brief_with_style({**target,"edit_style":"stream_highlights"})
    assert other["duration_mode"]=="target" and other["target_duration"]==90
    old=enrich_brief_with_style({"edit_style":"competitive_clutch","target_duration":90})
    assert old["style_profile"]["selection_policy"]["max_moments"]==1
    review=director._duration_review(target,360,12,nonverbal=True)
    assert review["duration_is_ceiling"] is False and review["reason"]=="limited_selection"


def test_target_mode_tops_up_a_short_planner_selection_with_relevant_complete_beats():
    decision = {}
    planned = [{"start": 10.0, "end": 40.0}]
    candidates = [
        {"start": 12.0, "end": 30.0, "score": 0.9},   # overlaps the planned passage
        {"start": 100.0, "end": 140.0, "score": 0.8},
        {"start": 200.0, "end": 260.0, "score": 0.7},
        {"start": 300.0, "end": 330.0, "score": 0.2},  # below the median: never added
        {"start": 400.0, "end": 410.0, "score": 0.1},
    ]
    result = director._top_up_to_target(planned, candidates, 120.0, decision)
    assert result == [{"start": 10.0, "end": 40.0}, {"start": 100.0, "end": 140.0}]
    assert decision["_selection_trace"] == [
        {"stage": "planner_passages", "seconds": 30.0, "passages": 1},
        {"stage": "relevant_top_up", "seconds": 70.0, "passages": 1},
    ]
    # Already near the target: nothing is added.
    decision = {}
    assert director._top_up_to_target([{"start": 0.0, "end": 110.0}], candidates, 120.0, decision) == [{"start": 0.0, "end": 110.0}]
    assert [row["stage"] for row in decision["_selection_trace"]] == ["planner_passages"]


@pytest.mark.parametrize("mode", ["style", "target"])
def test_duration_review_names_output_above_the_effective_target(mode):
    review = director._duration_review(
        {"goal": "short", "target_duration": 30, "duration_mode": mode}, 300, 90,
    )
    assert review["reason"] == "over_target"
    assert review["exceeds_target"] is True
    assert review["shortfall"] is False


@pytest.mark.parametrize("kept,added,removed,partial", [
    ([{"start": 0, "end": 10}, {"start": 100, "end": 110}], ["other"], [], []),
    ([{"start": 0, "end": 5}], [], [], ["planned"]),
    ([{"start": 100, "end": 110}], ["other"], ["planned"], []),
])
def test_final_speech_changes_cannot_reuse_an_earlier_critic_pass(kept, added, removed, partial):
    segments = [
        {"id": "planned", "start": 0, "end": 10},
        {"id": "other", "start": 100, "end": 110},
    ]
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, segments, kept, 300,
        decision={"story_ranges": [{"start": 0, "end": 10}]},
    )
    assert review["needs_review"] is True
    assert "story_selection_changed" in [row["type"] for row in review["warnings"]]
    assert review["selection_review"] == {
        "status": "changed", "added_segment_ids": added,
        "removed_segment_ids": removed, "partial_segment_ids": partial,
    }


def test_removing_only_a_pause_keeps_the_reviewed_speech_intact():
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}},
        [{"id": "a", "start": 0, "end": 5}, {"id": "b", "start": 15, "end": 20}],
        [{"start": 0, "end": 5}, {"start": 15, "end": 20}], 300,
        decision={"story_ranges": [{"start": 0, "end": 20}]},
    )
    assert review["needs_review"] is False
    assert review["selection_review"]["status"] == "unchanged"


@pytest.mark.parametrize("rejected", [
    {"rejected_segment_ids": ["rejected"]},
    {"rejected_story_ranges": [{"start": 100, "end": 140}]},
])
def test_target_top_up_candidates_exclude_explicit_critic_rejections(rejected):
    segments = [
        {"id": "planned", "start": 0, "end": 30, "editorial_score": .6},
        {"id": "rejected", "start": 100, "end": 140, "editorial_score": .99},
        {"id": "safe", "start": 200, "end": 240, "editorial_score": .8},
    ]
    candidates = director._style_beat_candidates(
        segments, rejected, 300, 120, {}, [dict(row) for row in segments],
    )
    assert [(row["start"], row["end"]) for row in candidates] == [(0, 30), (200, 240)]


def test_a_model_title_remains_explicitly_unverified_after_a_continuity_pass():
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, [{"id": "a", "start": 0, "end": 10}],
        [{"start": 0, "end": 10}], 300,
        decision={"title": "An unverified claim", "story_ranges": [{"start": 0, "end": 10}],
                  "title_review": {"status": "unverified", "reason": "model_suggestion"}},
    )
    assert review["needs_review"] is True
    assert "title_review" in [row["type"] for row in review["warnings"]]
    assert review["title_review"]["status"] == "unverified"


def test_single_moment_cannot_bridge_across_explicitly_rejected_speech():
    segments = [{"id": identifier, "start": start, "end": start + 10}
                for identifier, start in [("a", 0), ("rejected", 10), ("c", 20)]]
    decision = {"story_ranges": [segments[0], segments[2]],
                "rejected_story_ranges": [segments[1]]}
    selected = director._select_style_story_ranges(segments, decision, 100, 45, {"max_moments": 1})
    assert selected == [{"start": 0, "end": 10}, {"start": 20, "end": 30}]


@pytest.mark.parametrize("source_duration", [30, 100])
def test_story_shortcuts_and_fallback_never_restore_explicitly_rejected_speech(source_duration):
    segments = [{"id": identifier, "start": start, "end": start + 10}
                for identifier, start in [("a", 0), ("rejected", 10), ("c", 20)]]
    decision = {"opening_id": "a", "closing_id": "c", "keep_ids": ["a", "c"],
                "rejected_segment_ids": ["rejected"]}
    selected = director._select_short_story_ranges(segments, decision, source_duration, 45)
    assert selected
    assert not any(row["start"] < 20 and row["end"] > 10 for row in selected)


def test_removing_a_pause_inside_one_segment_keeps_reviewed_words_intact():
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}},
        [{"id": "a", "start": 0, "end": 10, "words": [
            {"start": 0, "end": 2, "word": "First"}, {"start": 8, "end": 10, "word": "last"},
        ]}], [{"start": 0, "end": 2}, {"start": 8, "end": 10}], 300,
        decision={"story_ranges": [{"start": 0, "end": 10}]},
    )
    assert review["needs_review"] is False
    assert review["selection_review"]["status"] == "unchanged"


def test_neutral_title_does_not_report_a_hidden_model_claim_as_a_problem():
    review = director._edit_quality_review(
        {}, {"critic": {"verdict": "pass"}}, [{"id": "a", "start": 0, "end": 10}],
        [{"start": 0, "end": 10}], 300,
        decision={"title": "CUTROOM story", "story_ranges": [{"start": 0, "end": 10}],
                  "title_review": {"status": "unverified", "reason": "model_suggestion"}},
    )
    assert review["needs_review"] is False
    assert review["title_review"]["status"] == "unverified"
