"""Explicit selection membership is source bookkeeping, not semantic approval."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style


SETTINGS = SimpleNamespace(ai={"performance_mode": "balanced"})
PURPOSE = story.SINGLE_PASSAGE_PURPOSE


@pytest.fixture(autouse=True)
def no_real_inference(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Selection-membership regressions must never call a model")
    monkeypatch.setattr(story, "_call_ollama_story_pass", forbidden)


def fixture(language):
    texts = (["The experiment failed.", "Because it did not get enough readers.", "Another topic begins here."]
             if language == "en" else
             ["הניסוי נכשל.", "כי לא היו לו מספיק קוראים.", "כאן מתחיל נושא אחר."])
    instruction = ("Choose one coherent self-contained passage. Preserve its meaning and necessary context."
                   if language == "en" else
                   "בחר קטע אחד ברור ועצמאי. שמור על המשמעות ועל ההקשר הדרוש.")
    segments = story.enrich_segments([
        {"id": f"s{index}", "start": (index - 1) * 10., "end": index * 10., "text": text}
        for index, text in enumerate(texts, 1)], language)
    units = [{"id": f"b{index}", "start": row["start"], "end": row["end"], "duration": 10.,
              "segment_ids": [row["id"]], "text": row["text"]}
             for index, row in enumerate(segments, 1)]
    chapters = [{"id": "c1", "start": 0., "end": 30., "beats": units}]
    plan = {"slots": [{"purpose": PURPOSE, "chapter_ids": ["c1"], "required_context_chapter_ids": [],
                       "desired_seconds": 20.}]}
    brief = enrich_brief_with_style({"goal": "short", "target_duration": 20., "duration_mode": "target",
                                     "performance_mode": "balanced", "instruction": instruction})
    _, catalog = story._precision_story_payload(units, segments, chapters, [], {}, plan, brief,
                                               "fixture", "balanced", 20.)
    choices = {row["beat_id"]: f"{row['text']} [{row['id']}]" for row in catalog}
    reply = {"verdict": "fit", "role_selections": {PURPOSE: {
        "primary_anchor_choice": choices["b2"], "additional_primary_evidence_choices": [choices["b1"]],
        "context_evidence_choices_by_chapter": {}}}, "highlight_beat_ids": [],
        "title": "Provisional source account", "summary": "Interpretation remains unverified"}
    selection = story._decode_precision_story_selection(reply, catalog, units, segments, chapters, plan, brief)
    return {"units": units, "segments": segments, "chapters": chapters, "plan": plan, "brief": brief,
            "catalog": catalog, "choices": choices, "selection": selection}


def critic_proposal(monkeypatch, data, calls):
    explanation = "The explanation was removed, so the failure lacks necessary context."
    evidence_id = next(row["id"] for row in data["catalog"] if row["beat_id"] == "b2")
    reply = {"verdict": "revise", "add_beat_ids": [], "remove_beat_ids": ["b2"],
             "issues": [explanation], "summary": explanation, "style_notes": [],
             "action_evidence": [{"action": "remove", "beat_id": "b2", "defect_kind": "missing_context",
                 "source_evidence_ids": [evidence_id], "instruction_quote": "", "explanation": explanation}]}
    def respond(_settings, payload, *_args, **_kwargs):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(reply)
    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    return story._critic_story_selection(SETTINGS, data["selection"], data["units"], {}, data["plan"],
                                         data["brief"], "fixture", segments=data["segments"])


def review(monkeypatch, data, proposal, reply, calls):
    def respond(_settings, payload, *_args, **_kwargs):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(reply)
    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    return story._review_story_target_budget(SETTINGS, proposal, data["units"], data["segments"],
        data["chapters"], {}, data["plan"], data["brief"], "fixture")


@pytest.mark.parametrize("language", ["he", "en"])
def test_critic_sees_exact_retained_explanation_membership_without_applying_its_allegation(monkeypatch, language):
    data = fixture(language)
    original = copy.deepcopy(data)
    calls = []
    proposal = critic_proposal(monkeypatch, data, calls)
    assert data == original
    assert len(calls) == 1
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert {row["id"]: row["segment_ids"] for row in payload["selected"]} == {"b1": ["s1"], "b2": ["s2"]}
    utterances = {row["id"]: row for row in payload["source_utterances"]}
    assert {key: row["selected_in_proposal"] for key, row in utterances.items()} == {"s1": True, "s2": True, "s3": False}
    assert utterances["s2"]["text"] == data["segments"][1]["text"]
    assert utterances["s2"]["start"] == 10. and utterances["s2"]["end"] == 20.
    assert proposal["keep_beat_ids"] == ["b1", "b2"]
    assert proposal["critic"]["proposed_beat_ids"] == ["b1"]
    assert proposal["critic"]["action_authority"] == "proposal"
    assert proposal["critic"]["action_attribution_verified"] is True
    assert proposal["critic"]["action_semantics_verified"] is False
    assert proposal["semantic_mapping_verified"] is False


@pytest.mark.parametrize("language", ["he", "en"])
def test_final_review_gets_selected_membership_and_can_independently_decline_false_removal(monkeypatch, language):
    data = fixture(language)
    proposal = critic_proposal(monkeypatch, data, [])
    original = copy.deepcopy((data, proposal))
    calls = []
    evidence_id = next(row["id"] for row in data["catalog"] if row["beat_id"] == "b2")
    reply = {"verdict": "fit", "keep_beat_ids": ["b1", "b2"], "released_optional_beat_ids": [],
        "role_selections": {PURPOSE: {"primary_anchor_choice": data["choices"]["b2"],
            "additional_primary_evidence_choices": [data["choices"]["b1"]], "context_evidence_choices": []}},
        "critic_action_decisions": [{"action": "remove", "beat_id": "b2", "decision": "decline",
            "source_evidence_ids": [evidence_id], "reason": "The original explanation is selected and supplies the causal context."}]}
    final = review(monkeypatch, data, proposal, reply, calls)
    assert (data, proposal) == original
    assert len(calls) == 1
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["critic_proposals"]["authority"] == "advisory_only"
    assert payload["critic_proposals"]["action_semantics_verified"] is False
    assert "The explanation was removed" in payload["critic_proposals"]["issues"][0]
    units = {row["id"]: row for row in payload["source_units"]}
    assert {key: row["selected_in_proposal"] for key, row in units.items()} == {"b1": True, "b2": True, "b3": False}
    assert units["b2"]["segment_ids"] == ["s2"]
    assert units["b2"]["segments"][0]["text"] == data["segments"][1]["text"]
    assert final["keep_beat_ids"] == ["b1", "b2"]
    assert final["critic"]["accepted_removed"] == []
    assert final["critic"]["requested_removed"] == ["b2"]
    assert final["critic"]["action_authority"] == "final"
    assert final["semantic_mapping_verified"] is True  # Mock final review, never an editorial-quality claim.


@pytest.mark.parametrize("language", ["he", "en"])
def test_retained_membership_does_not_bypass_final_no_fit_or_certify_context(monkeypatch, language):
    data = fixture(language)
    proposal = critic_proposal(monkeypatch, data, [])
    original = copy.deepcopy((data, proposal))
    calls = []
    reply = {"verdict": "no_fit", "keep_beat_ids": [], "released_optional_beat_ids": [],
             "role_selections": {}, "critic_action_decisions": []}
    with pytest.raises(story.StoryBudgetError) as caught:
        review(monkeypatch, data, proposal, reply, calls)
    assert len(calls) == 1
    assert caught.value.diagnostic["reason"] == "planner_no_fit"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert (data, proposal) == original
    assert proposal["keep_beat_ids"] == ["b1", "b2"]
    assert proposal["semantic_mapping_verified"] is False
