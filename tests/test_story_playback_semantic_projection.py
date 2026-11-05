"""Semantic review sees actual playback, not unused pause-fitting possibilities.

These controls establish source bookkeeping and prompt boundaries only. Mocked
semantic verdicts and punctuation never establish real editorial/audio quality.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style
from tests.portable_support.response_fixtures import playback_projection_fixture


SETTINGS = SimpleNamespace(ai={"performance_mode": "balanced"})
ROOT = Path(__file__).resolve().parents[1]
UNUSED_COST_KEYS = {"cost", "duration_cost", "current_cost", "pause_count", "removable_pause_seconds",
                    "minimum_safe_seconds", "protected_speech_seconds", "minimum_framed_seconds"}


@pytest.fixture(autouse=True)
def no_real_inference(monkeypatch):
    monkeypatch.setattr(story, "_call_ollama_story_pass",
                        lambda *_args, **_kwargs: pytest.fail("Unexpected live inference"))


def brief(instruction="Choose one coherent self-contained passage."):
    return {"goal": "short", "target_duration": 60., "duration_mode": "target", "instruction": instruction}


def projection(ranges, segments, instruction="Choose one coherent self-contained passage."):
    return story._story_playback_semantic_projection(ranges, segments, brief(instruction))


def nested_keys(value):
    if isinstance(value, dict):
        return set(value).union(*(nested_keys(row) for row in value.values()))
    if isinstance(value, list):
        return set().union(*(nested_keys(row) for row in value))
    return set()


def fixture(language):
    texts = (["The experiment failed.", "Because it did not get enough readers.",
              "The team did not repeat that approach."] if language == "en" else
             ["הניסוי נכשל.", "כי לא היו לו מספיק קוראים.", "הצוות לא חזר על אותה שיטה."])
    instruction = ("Choose one coherent self-contained passage. Preserve original meaning and necessary context."
                   if language == "en" else "בחר קטע אחד ברור ועצמאי. שמור על המשמעות המקורית ועל ההקשר הדרוש.")
    source = []
    for index, text in enumerate(texts):
        start = float(index * 20)
        left, right = text.rsplit(" ", 1)
        source.append({"id": f"s{index + 1}", "start": start, "end": start + 18., "text": text,
                       "words": [{"word": left, "start": start, "end": start + 5.},
                                 {"word": right, "start": start + 8., "end": start + 18.}],
                       "word_timing_complete": True})
    segments = story.enrich_segments(source, language)
    units = story.build_story_beats(segments, language, target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE, "chapter_ids": [c["id"] for c in chapters],
                       "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    request = enrich_brief_with_style(brief(instruction))
    options = story._passage_options(units, segments, chapters, plan, request)
    option = next(row for row in options["options"] if row["segment_ids"] == ["s1", "s2", "s3"])
    selected = story._decode_passage_option_choice(
        {"verdict": "fit", "candidate_id": option["id"], "semantic_reason": "Mock provisional interpretation only.",
         "refusal_category": "none", "cited_segment_ids": ["s1", "s3"]},
        options, units, segments, chapters, plan, request)
    return {"segments": segments, "units": units, "chapters": chapters,
            "plan": plan, "brief": request, "selection": selected, "option": option}


@pytest.mark.parametrize("language", ["he", "en"])
def test_actual_joins_are_source_gaps_not_optional_word_pause_count(language):
    data = fixture(language)
    before = copy.deepcopy(data)
    value = story._story_playback_semantic_projection(data["option"]["playback_ranges"], data["segments"], data["brief"])
    assert value["playback_ranges"] == data["option"]["playback_ranges"]
    assert value["playback_seconds"] == pytest.approx(54.)
    assert value["actual_source_omission_count"] == 2
    assert [(r["start"], r["end"], r["duration_seconds"]) for r in value["actual_source_omissions"]] == [
        (18., 20., 2.), (38., 40., 2.)]
    assert all(row["overlapping_segment_ids"] == [] for row in value["actual_source_omissions"])
    assert data["option"]["cost"]["pause_count"] == 3  # Three UNUSED within-unit pause possibilities.
    assert not UNUSED_COST_KEYS.intersection(nested_keys(value))
    assert value["semantic_verified"] is False
    assert value["source_continuity_required"] is False
    assert data == before


def test_adjacent_whole_units_do_not_create_an_omission_at_an_analysis_boundary():
    segments = [{"id": "s1", "start": 0., "end": 10., "text": "One statement."},
                {"id": "s2", "start": 10., "end": 20., "text": "The related explanation."}]
    ranges = [{"start": 0., "end": 10.}, {"start": 10., "end": 20.}]
    value = projection(ranges, segments)
    assert value["playback_ranges"] == ranges
    assert value["playback_seconds"] == 20.
    assert value["actual_source_omission_count"] == 0
    assert value["actual_source_omissions"] == []


def test_every_positive_source_gap_including_one_millisecond_remains_visible():
    segments = [{"id": "s1", "start": 0., "end": 10., "text": "First."},
                {"id": "s2", "start": 10.001, "end": 20., "text": "Second."}]
    ranges = [{"start": 0., "end": 10.}, {"start": 10.001, "end": 20.}]
    value = projection(ranges, segments)
    assert value["actual_source_omission_count"] == 1
    gap = value["actual_source_omissions"][0]
    assert gap["start"] == 10. and gap["end"] == 10.001
    assert gap["duration_seconds"] == pytest.approx(.001)
    assert gap["overlapping_segment_ids"] == []


@pytest.mark.parametrize("start,end", [(5., 10.), (6., 8.)])
def test_whole_or_partial_utterance_omission_cannot_be_labelled_transcript_free(start, end):
    segments = [{"id": "s1", "start": 0., "end": 5., "text": "The result."},
                {"id": "s2", "start": 5., "end": 10., "text": "It did not prove the claim."},
                {"id": "s3", "start": 10., "end": 15., "text": "The qualification."}]
    ranges = [{"start": 0., "end": start}, {"start": end, "end": 15.}]
    before = copy.deepcopy((ranges, segments))
    value = projection(ranges, segments)
    assert value["actual_source_omissions"][0]["overlapping_segment_ids"] == ["s2"]
    assert value["actual_source_omissions"][0]["start"] == start
    assert value["actual_source_omissions"][0]["end"] == end
    assert (ranges, segments) == before


@pytest.mark.parametrize("single,uncut", [
    ("Make one video with several related cuts.", "Do not cut within the source passage."),
    ("צור סרטון אחד עם כמה חיתוכים קשורים.", "אל תחתוך בתוך קטע המקור."),
])
def test_one_output_and_explicit_no_cut_remain_distinct_without_rewriting_actual_ranges(single, uncut):
    segments = [{"id": "s1", "start": 0., "end": 18., "text": "First."},
                {"id": "s2", "start": 20., "end": 38., "text": "Second."}]
    ranges = [{"start": 0., "end": 18.}, {"start": 20., "end": 38.}]
    ordinary = projection(ranges, segments, single)
    explicit = projection(ranges, segments, uncut)
    assert ordinary["source_continuity_required"] is False
    assert explicit["source_continuity_required"] is True
    assert ordinary["playback_ranges"] == explicit["playback_ranges"] == ranges
    assert explicit["actual_source_omission_count"] == 1  # Bookkeeping never repairs a no-cut violation.
    assert explicit["semantic_verified"] is False
    continuous = projection([{"start": 0., "end": 38.}], segments, uncut)
    assert continuous["playback_seconds"] == 38.
    assert continuous["actual_source_omissions"] == []


@pytest.mark.parametrize("instruction", [
    "Do not choose one continuous source passage.", "אל תשמור על קטע המקור רציף.",
])
def test_negated_continuity_is_not_promoted_to_a_user_requirement(instruction):
    value = projection([{"start": 0., "end": 10.}],
                       [{"id": "s1", "start": 0., "end": 10., "text": "Do not change this wording."}], instruction)
    assert value["source_continuity_required"] is False


@pytest.mark.parametrize("language", ["he", "en"])
def test_native_critic_prompt_projects_actual_playback_and_keeps_exact_source(monkeypatch, language):
    data = fixture(language)
    before = copy.deepcopy(data)
    calls = []

    def respond(_settings, payload, *_args, **_kwargs):
        calls.append(copy.deepcopy(payload))
        return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [],
                "summary": "Mock review only.", "style_notes": [], "action_evidence": []}

    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    selected = story._critic_story_selection(SETTINGS, data["selection"], data["units"], {}, data["plan"],
        data["brief"], "fixture", segments=data["segments"])
    assert len(calls) == 1
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["actual_playback"] == story._story_playback_semantic_projection(
        data["option"]["playback_ranges"], data["segments"], data["brief"])
    assert payload["actual_playback"]["actual_source_omission_count"] == 2
    assert not UNUSED_COST_KEYS.intersection(nested_keys(payload))
    assert [{k: row[k] for k in ("id", "start", "end", "text")} for row in payload["source_utterances"]] == [
        {k: row[k] for k in ("id", "start", "end", "text")} for row in data["segments"]]
    assert all(row["selected_in_proposal"] for row in payload["source_utterances"])
    assert selected["keep_beat_ids"] == data["selection"]["keep_beat_ids"]
    assert selected["semantic_mapping_verified"] is False
    assert data == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_fixed_final_uses_playback_projection_and_can_still_reject_semantics(monkeypatch, language):
    data = fixture(language)
    selected = copy.deepcopy(data["selection"])
    selected["critic"] = {"verdict": "pass", "review_verdict": "pass", "issues": [], "summary": "Mock review.",
        "action_authority": "proposal", "requested_added": [], "requested_removed": [],
        "selection_before": list(selected["keep_beat_ids"]), "proposed_beat_ids": list(selected["keep_beat_ids"])}
    before = copy.deepcopy((data, selected))
    calls = []

    def refuse(_settings, payload, *_args, **_kwargs):
        calls.append(copy.deepcopy(payload))
        request = json.loads(payload["messages"][1]["content"])
        return {"verdict": "no_fit", "candidate_id": request["fixed_passage_candidate"]["id"],
                "semantic_reason": "The mock final review cannot establish a self-contained ending.",
                "refusal_category": "semantic_rejection", "cited_segment_ids": ["s3"], "critic_action_decisions": []}

    monkeypatch.setattr(story, "_call_ollama_story_pass", refuse)
    with pytest.raises(story.StoryBudgetError) as caught:
        story._review_story_target_budget(SETTINGS, selected, data["units"], data["segments"], data["chapters"],
                                         {}, data["plan"], data["brief"], "fixture")
    assert len(calls) == 1
    request = json.loads(calls[0]["messages"][1]["content"])
    fixed = request["fixed_passage_candidate"]
    assert fixed["id"] == data["option"]["id"]
    assert fixed["segment_ids"] == data["option"]["segment_ids"]
    assert fixed["actual_playback"] == story._story_playback_semantic_projection(
        data["option"]["playback_ranges"], data["segments"], data["brief"])
    assert not UNUSED_COST_KEYS.intersection(nested_keys(request))
    assert request["selected_source_utterances"] == [{k: row[k] for k in ("id", "start", "end", "text")}
                                                      for row in data["segments"]]
    assert selected["passage_option_selection"]["option"]["cost"]["pause_count"] == 3  # Durable private evidence survives.
    assert caught.value.diagnostic["reason"] == "fixed_candidate_semantic_rejection"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert (data, selected) == before


def test_synthetic_eight_optional_pauses_are_not_nine_actual_joins():
    payload,reply=playback_projection_fixture()
    option=payload["fixed_passage_candidate"];before=copy.deepcopy(payload)
    value=story._story_playback_semantic_projection(option["playback_ranges"],payload["selected_source_utterances"],payload["brief"])
    assert option["cost"]["pause_count"]==8 and "8 distinct pauses" in reply["semantic_reason"]
    assert value["actual_source_omission_count"]==9
    assert sum(row["duration_seconds"] for row in value["actual_source_omissions"])==pytest.approx(4.36)
    assert value["playback_seconds"]==pytest.approx(57.19)
    assert all(not row["overlapping_segment_ids"] for row in value["actual_source_omissions"])
    assert option["segment_ids"]==[f"s{index:04}" for index in range(5,22)]
    assert value["source_continuity_required"] is False and value["semantic_verified"] is False
    assert not UNUSED_COST_KEYS.intersection(nested_keys(value)) and payload==before
