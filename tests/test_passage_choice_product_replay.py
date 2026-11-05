"""Synthetic full-path source and response replays; no live inference.

Generated HE/EN controls are always available. Private real-source qualification
remains separate and is never replaced by a claim of audio/editorial success.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from tests.passage_contract_fixture import nominate
from tests.portable_support.response_fixtures import response_reader

ROOT = Path(__file__).resolve().parents[1]



def saved(language):
    return response_reader(language)


def native_replay(monkeypatch, language, choose):
    segments, provenance, response = saved(language)
    before = copy.deepcopy(segments)
    calls = []
    def model(_settings, payload, *_args):
        system = payload["messages"][0]["content"]
        data = json.loads(payload["messages"][1]["content"])
        calls.append((copy.deepcopy(payload), data))
        if "first pass" in system: return response("01_summary",payload)
        if "global story analyst" in system: return response("02_outline",payload)
        if "Story Producer" in system: return response("03_plan",payload)
        return choose(payload, data, response)
    monkeypatch.setattr(story, "_ready_story_model_status", lambda *_a: {"selected_model": "qwen3.5:4b", "ready": True})
    monkeypatch.setattr(story, "_call_ollama_story_pass", model)
    def execute():
        return story.plan_edit(segments, SimpleNamespace(ai={"performance_mode": "balanced", "source_quality_assessment":False}), {
            "goal": "short", "target_duration": 60., "duration_mode": "target", "language": language,
            "performance_mode": "balanced", "instruction": provenance["instruction"], "allow_extractive_rough_cut": False})
    return execute, segments, before, calls


@pytest.mark.parametrize("language,outcome,reason", [
    ("en", "invalid_model_output", "invalid_passage_option_output"),
    ("he", "technical_error", "passage_verification_unfinished"),
])
def test_synthetic_bad_responses_never_become_source_unsuitability(monkeypatch, language, outcome, reason):
    def choose(payload, data, response):
        assert "passage_candidates" in data
        assert "primary_anchor_choice" not in json.dumps(payload["format"])
        return response("06_precision" if language == "en" else "04_precision")
    execute, segments, before, calls = native_replay(monkeypatch, language, choose)
    with pytest.raises(story.StoryPlanningError) as failure:
        execute()
    assert failure.value.diagnostic["outcome"] == outcome
    assert failure.value.diagnostic["reason"] == reason
    assert failure.value.diagnostic["source_wide_no_fit_proven"] is False
    assert failure.value.diagnostic["applied_to_timeline"] is False
    assert len(calls) == 4 and segments == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_native_numeric_choice_still_requires_independent_final_meaning_acceptance(monkeypatch, language):
    def choose(_payload, data, _response):
        if "passage_candidates" in data:
            option = data["passage_candidates"][0]
            # The generated HE/EN requests explicitly allow 45–60s.
            # Final independent semantic rejection remains mandatory below.
            assert 45. <= option["raw_playable_seconds"] <= 60.
            assert data["duration_bounds"]["origin"] == "explicit_user_range"
            return nominate(option,data)
        if "selected" in data:
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [],
                "issues": [], "summary": "Fixture proposal only", "style_notes": [], "action_evidence": []}
        option = data["fixed_passage_candidate"]
        assert "primary_anchor_choice" not in json.dumps(_payload["format"])
        return {"verdict": "no_fit", "candidate_id": option["id"],
            "semantic_reason": "The fixture final review cannot establish complete independent context", "refusal_category": "semantic_rejection",
            "cited_segment_ids": [option["segment_ids"][0]], "critic_action_decisions": [],
            "rejection_evidence": [{"kind":"incomplete_thought","source_segment_ids":[option["segment_ids"][0]],"missing_context_segment_ids":[],"join_id":None,"instruction_quote":""}]}
    execute, segments, before, calls = native_replay(monkeypatch, language, choose)
    with pytest.raises(story.StoryBudgetError) as failure:
        execute()
    assert failure.value.diagnostic["reason"] == "fixed_candidate_semantic_rejection"
    assert failure.value.diagnostic["scope"] == "one_fixed_passage_candidate"
    assert failure.value.diagnostic["source_wide_no_fit_proven"] is False
    assert len(calls) == 6 and segments == before


def test_synthetic_legacy_proposals_are_not_promoted_with_extra_source():
    segments, provenance, response = saved("en")
    enriched = story.enrich_segments(segments, "en")
    units = story.build_story_beats(enriched, "en", target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = response("03_plan")
    brief = {"goal": "short", "target_duration": 60., "duration_mode": "target",
             "instruction": provenance["instruction"]}
    from cutroom.edit_styles import enrich_brief_with_style
    brief = enrich_brief_with_style(brief)
    candidates = story._candidate_beats_for_plan(chapters, plan)
    options = story._passage_options(candidates, enriched, chapters, plan, brief)
    catalog = story.build_story_evidence_catalog(units, enriched)
    by_choice = story._story_evidence_choice_catalog(catalog)
    option_memberships = {tuple(o["beat_ids"]) for o in options["options"]}
    for name in ["05_precision", "06_precision"]:
        reply = response(name)
        role = reply["role_selections"][story.SINGLE_PASSAGE_PURPOSE]
        refs = [role["primary_anchor_choice"], *role["additional_primary_evidence_choices"],
                *(value for rows in role["context_evidence_choices_by_chapter"].values() for value in rows)]
        selected = {by_choice[value]["beat_id"] for value in refs}
        ordered = [u["id"] for u in units if u["id"] in selected]
        cost = story._story_selection_cost(ordered, units, enriched, brief)
        assert 20. <= cost["approved_seconds"] < 54.
        assert cost["approved_seconds"] < 54.
        if name == "05_precision":
            assert cost["approved_seconds"] < options["receipt"]["duration_bounds"]["minimum_seconds"]
        assert tuple(ordered) not in option_memberships


@pytest.mark.parametrize("kind", ["foreign_id", "foreign_citation", "refusal", "malformed"])
def test_choice_outcomes_are_distinct_and_never_approve_source(kind):
    from tests.test_story_candidate_product_path import source
    from cutroom.edit_styles import enrich_brief_with_style
    segments = source()
    units = story.build_story_beats(segments, "en", target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE, "chapter_ids": [c["id"] for c in chapters],
                       "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    brief = enrich_brief_with_style({"goal": "short", "target_duration": 60., "duration_mode": "target",
                                     "instruction": "Choose one coherent self-contained passage."})
    options = story._passage_options(units, segments, chapters, plan, brief)
    option = options["options"][0]
    reply = {"verdict": "fit", "candidate_id": option["id"], "semantic_reason": "Unverified", "refusal_category": "none", "cited_segment_ids": [option["segment_ids"][0]]}
    if kind == "foreign_id": reply["candidate_id"] = "invented"
    elif kind == "foreign_citation": reply["cited_segment_ids"] = ["s7"]
    elif kind == "refusal": reply.update(verdict="no_fit", candidate_id=None, semantic_reason="Missing semantic context", refusal_category="semantic_rejection", cited_segment_ids=[])
    else: reply["timestamps"] = [0, 60]
    with pytest.raises(story.StoryPlanningError) as failure:
        story._decode_passage_option_choice(reply, options, units, segments, chapters, plan, brief)
    expected = "editorial_no_fit" if kind == "refusal" else "invalid_model_output"
    assert failure.value.diagnostic["outcome"] == expected
    assert failure.value.diagnostic["source_wide_no_fit_proven"] is False


@pytest.mark.parametrize("language", ["he", "en"])
@pytest.mark.parametrize("final_verdict", ["fit", "no_fit"])
def test_fixed_final_must_independently_adjudicate_critic_proposal(monkeypatch, language, final_verdict):
    # This tests the legacy advisory-action path. Fixed ordered review now emits
    # no edit actions; legacy non-entry source units still use final adjudication.
    original_beats=story.build_story_beats
    monkeypatch.setattr(story,"build_story_beats",lambda *a,**k:original_beats(*a,**{**k,"independent_asr_entries":False}))
    def choose(_payload, data, _response):
        if "passage_candidates" in data:
            option = data["passage_candidates"][0]
            return nominate(option,data)
        if "selected" in data:
            target = data["selected"][0]["id"]
            evidence = next(row["id"] for row in data["source_evidence"] if row["beat_id"] == target)
            return {"verdict": "revise", "add_beat_ids": [], "remove_beat_ids": [target],
                "issues": ["Fixture alleged omission; requires independent review"],
                "summary": "Fixture interpretation, not verified source truth", "style_notes": [],
                "issue_evidence":[{"issue_index":0,"kind":"incomplete_thought","source_segment_ids":data["selected"][0]["segment_ids"][:1],"missing_context_segment_ids":[],"join_id":None,"instruction_quote":""}],
                "action_evidence": [{"action": "remove", "beat_id": target, "defect_kind": "missing_context",
                    "source_evidence_ids": [evidence], "instruction_quote": "",
                    "explanation": "Fixture allegation requiring independent review"}]}
        option = data["fixed_passage_candidate"]
        actions = data["critic_proposals"]["actions"]
        assert len(actions) == 1 and data["critic_proposals"]["action_semantics_verified"] is False
        target = actions[0]["beat_id"]
        ref = next(row["id"] for row in data["source_evidence"] if row["beat_id"] == target)
        return {"verdict": final_verdict, "candidate_id": option["id"],
            "semantic_reason": "Independent synthetic interpretation only", "refusal_category": "none" if final_verdict=="fit" else "semantic_rejection", "cited_segment_ids": [option["segment_ids"][0]],
            "critic_action_decisions": [{"action": "remove", "beat_id": target,
                "decision": "decline" if final_verdict == "fit" else "accept", "source_evidence_ids": [ref],
                "reason": "Fixture review of exact retained target, not automatic acceptance of critic"}],
            "rejection_evidence": [] if final_verdict=="fit" else [{"kind":"incomplete_thought","source_segment_ids":[option["segment_ids"][0]],"missing_context_segment_ids":[],"join_id":None,"instruction_quote":""}]}
    execute, segments, before, calls = native_replay(monkeypatch, language, choose)
    if final_verdict == "fit":
        editorial, _engine = execute()
        selection = editorial["story_hierarchy"]["selection"]
        option = selection["passage_option_selection"]["option"]
        assert selection["keep_beat_ids"] == option["beat_ids"]
        assert selection["semantic_mapping_verified"] is True
        assert editorial["story_hierarchy"]["critic"]["accepted_removed"] == []
    else:
        with pytest.raises(story.StoryBudgetError) as failure:
            execute()
        assert failure.value.diagnostic["reason"] == "fixed_candidate_semantic_rejection"
    assert len(calls) == 6 and segments == before


def test_continuous_candidate_reaches_nomination_with_original_gaps_preserved(monkeypatch):
    from cutroom.edit_styles import enrich_brief_with_style
    segments = [{"id": f"s{i}", "start": i * 20., "end": i * 20. + 18.,
                 "text": f"A complete source statement {i}."} for i in range(3)]
    units = story.build_story_beats(segments, "en", target_seconds=60.)
    chapters = story.build_story_chapters(units)
    brief = enrich_brief_with_style({"goal": "short", "target_duration": 60., "duration_mode": "target",
        "instruction": "Choose one coherent self-contained passage. Keep the selected source passage without internal cuts."})
    plan = {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE, "chapter_ids": [c["id"] for c in chapters],
                       "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    def nominate_continuous(_settings, payload, *_args):
        data = json.loads(payload['messages'][1]['content'])
        option = data['passage_candidates'][0]
        assert option['playback_ranges'] == [{'start':0., 'end':58.}]
        assert option['segment_ids'] == [r['id'] for r in segments]
        return nominate(option, data)
    monkeypatch.setattr(story, "_call_ollama_story_pass", nominate_continuous)
    selection, _ = story._select_story_beats(SimpleNamespace(ai={}), chapters, [], {}, plan, brief, "fixture", segments=segments)
    option = selection['passage_option_selection']['option']
    assert option['continuous_source_playback']['playback_ranges'] == [{'start':0., 'end':58.}]
    assert option['raw_playable_seconds'] == 58.
    assert selection['semantic_mapping_verified'] is False
    assert selection['semantic_review_status'] == 'provisional_precision_selection'


@pytest.mark.parametrize("category,outcome", [("semantic_rejection", "editorial_no_fit"),
                                             ("uncertain", "technical_error"), ("temporal_uncertainty", "technical_error")])
def test_schema_valid_refusal_category_controls_status_not_a_free_text_order_label(category, outcome):
    from tests.test_story_candidate_product_path import source
    from cutroom.edit_styles import enrich_brief_with_style
    segments = source()
    units = story.build_story_beats(segments, "en", target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE, "chapter_ids": [c["id"] for c in chapters],
                       "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    brief = enrich_brief_with_style({"goal": "short", "target_duration": 60., "instruction": "Choose one coherent self-contained passage."})
    options = story._passage_options(units, segments, chapters, plan, brief)
    reply = {"verdict": "no_fit", "candidate_id": None, "refusal_category": category,
             "semantic_reason": "This is the model's unverified reason, not a source-order proof", "cited_segment_ids": []}
    with pytest.raises(story.StoryPlanningError) as error:
        story._decode_passage_option_choice(reply, options, units, segments, chapters, plan, brief)
    assert error.value.diagnostic["outcome"] == outcome
    assert error.value.diagnostic["source_wide_no_fit_proven"] is False
