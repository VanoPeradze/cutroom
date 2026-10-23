"""Actual plan_edit -> precision -> critic -> final -> decision source mapping.

Model replies are deterministic controls, never real editorial-quality evidence.
"""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.story_candidates import (CANDIDATE_POLICY_VERSION, project_short_source_units,
                                      neighboring_source_utterances)
from tests.portable_support.source_fixture import source_fixture


@pytest.fixture(autouse=True)
def forbid_inference(monkeypatch):
    monkeypatch.setattr(story, "_call_ollama_story_pass", lambda *_a, **_k: pytest.fail("Unexpected inference"))


def source(language="en", offset=0.):
    texts = (["The experiment had a clear goal.", "The team prepared the test.",
              "They measured the same outcome.", "The result did not support their assumption.",
              "They changed their approach after the test.", "Another subject begins here.",
              "It concerns a separate task.", "That task needs its own explanation."] if language == "en" else
             ["לניסוי הייתה מטרה ברורה.", "הצוות הכין את הבדיקה.", "הם מדדו את אותה תוצאה.",
              "התוצאה לא תמכה בהנחה שלהם.", "הם שינו את הגישה אחרי הבדיקה.", "כאן מתחיל נושא אחר.",
              "הוא עוסק במשימה נפרדת.", "המשימה הזאת דורשת הסבר משלה."])
    return [{"id": f"s{i}", "start": offset + i * 12., "end": offset + (i + 1) * 12.,
             "text": text, "words": [{"word": text, "start": offset + i * 12., "end": offset + (i + 1) * 12.}]}
            for i, text in enumerate(texts)]


@pytest.mark.parametrize("language", ["en", "he"])
def test_native_product_pipeline_selects_five_sentences_not_their_oversized_parents(monkeypatch, language):
    segments = source(language)
    original = copy.deepcopy(segments)
    instruction = ("Choose one coherent self-contained passage. Preserve its meaning and complete sentences."
                   if language == "en" else "בחר קטע אחד ברור ועצמאי. שמור על המשמעות ועל משפטים שלמים.")
    seen = []
    def summaries(_settings, chapters, *_args):
        assert len([b for c in chapters for b in c["beats"]]) == 8
        return [{"id": c["id"], "summary": "Unverified fixture", "key_points": [], "depends_on": []} for c in chapters]
    def plan(_settings, summaries, _outline, _brief, _model, _progress, _cancel, _segments, chapters):
        return {"slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE,
                           "chapter_ids": [c["id"] for c in chapters],
                           "required_context_chapter_ids": [], "desired_seconds": 60.}]}
    def model(_settings, payload, *_args):
        data = json.loads(payload["messages"][1]["content"])
        seen.append(data)
        if "selected" in data:
            assert len(data["selected"]) == 5
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [],
                    "issues": [], "summary": "Fixture semantic approval", "style_notes": [], "action_evidence": []}
        if "passage_candidates" in data:
            option = next(r for r in data["passage_candidates"] if r["segment_ids"] == [f"s{i}" for i in range(5)])
            assert option["raw_playable_seconds"] == 60.
            from tests.passage_contract_fixture import nominate
            return nominate(option,data)
        if "fixed_passage_candidate" in data:
            return {"verdict": "fit", "candidate_id": data["fixed_passage_candidate"]["id"],
                    "semantic_reason": "Independent fixture review of the same unchanged source", "refusal_category": "none",
                    "cited_segment_ids": ["s0", "s4"], "critic_action_decisions": []}
        evidence = data["source_evidence"]
        wanted = [row for row in evidence if row["segment_id"] in {f"s{i}" for i in range(5)}]
        choices = [f"{row['text']} [{row['id']}]" for row in wanted]
        selected = list(dict.fromkeys(row["beat_id"] for row in wanted))
        role = {"primary_anchor_choice": choices[-1], "additional_primary_evidence_choices": choices[:-1]}
        if "source_units" in data:
            role["context_evidence_choices"] = []
            return {"verdict": "fit", "keep_beat_ids": selected, "released_optional_beat_ids": [],
                    "role_selections": {story.SINGLE_PASSAGE_PURPOSE: role}}
        assert len(data["candidate_beats"]) == 8
        assert all(row["duration_cost"]["approved_seconds"] == 12. for row in data["candidate_beats"])
        role["context_evidence_choices_by_chapter"] = {}
        return {"verdict": "fit", "role_selections": {story.SINGLE_PASSAGE_PURPOSE: role},
                "highlight_beat_ids": [], "title": "Fixture", "summary": "Not an actual model judgment"}
    monkeypatch.setattr(story, "_ready_story_model_status", lambda *_a: {"selected_model": "fixture", "ready": True})
    monkeypatch.setattr(story, "_summarize_story_chapters", summaries)
    monkeypatch.setattr(story, "_build_global_outline", lambda *_a: {})
    monkeypatch.setattr(story, "_build_story_plan", plan)
    monkeypatch.setattr(story, "_call_ollama_story_pass", model)
    editorial, engine = story.plan_edit(segments, SimpleNamespace(ai={"performance_mode": "balanced"}), {
        "goal": "short", "target_duration": 60., "duration_mode": "target", "language": language,
        "instruction": instruction,
        # This fixture tests exact unit->timeline mapping, independently of
        # retrieval ordering. Automated retrieval has separate bounded tests.
        "source_candidate_segment_ids":[f"s{i}" for i in range(5)],
        "source_candidate_origin":"test_source_mapping_control"})
    assert segments == original and len(seen) == 3
    units = editorial["story_beats"]
    assert [u["segment_ids"] for u in units] == [[f"s{i}"] for i in range(8)]
    decision = editorial["decision"]
    assert decision["story_beat_ids"] == [row["id"] for row in units[:5]]
    assert set(decision["remove_ids"]) == {"s5", "s6", "s7"}
    assert editorial["story_hierarchy"]["selection"]["semantic_mapping_verified"]
    assert engine == "ollama_hierarchical_story"
    assert seen[0]["brief"]["instruction"] == instruction
    assert "primary_anchor_choice" not in seen[0]
    assert seen[-1]["fixed_passage_candidate"]["segment_ids"] == [f"s{i}" for i in range(5)]


@pytest.mark.parametrize("language", ["en", "he"])
def test_boundaries_are_whole_asr_and_preserve_negation_offset_and_source_identity(language):
    segments = source(language, offset=120.)[:3]
    segments[0]["text"] = "The result did not" if language == "en" else "התוצאה לא"
    segments[1]["text"] = "establish the claim. Another statement remains in this same ASR row." if language == "en" else "הוכיחה את הטענה. אמירה נוספת נשארת באותה יחידת תמלול."
    before = copy.deepcopy(segments)
    units = story.build_story_beats(segments, language, target_seconds=60)
    assert units[0]["segment_ids"] == ["s0", "s1"]
    assert units[0]["start"] == 120. and units[0]["end"] == 144.
    assert units[0]["text"] == " ".join(s["text"] for s in segments[:2])
    assert units[0]["semantic_coherence_verified"] is False
    assert units[0]["context_neighbor_segment_ids"] == ["s2"]
    assert segments == before
    assert units == story.build_story_beats(segments, language, target_seconds=60)
    changed = copy.deepcopy(segments); changed[0]["words"][0]["end"] -= .02
    assert units[0]["id"] != story.build_story_beats(changed, language, target_seconds=60)[0]["id"]
    brief = {"goal": "short", "target_duration": 60}
    assert story.story_cache_fingerprint(segments, brief, "fixture") != story.story_cache_fingerprint(changed, brief, "fixture")


def test_neighbor_context_is_exact_reference_not_parent_playback_or_selected_source():
    segments = source()
    units = story.build_story_beats(segments, "en", target_seconds=60)
    context = neighboring_source_utterances([units[2]], segments)
    assert [r["id"] for r in context] == ["s1", "s3"]
    assert [r["text"] for r in context] == [segments[1]["text"], segments[3]["text"]]
    assert units[2]["segment_ids"] == ["s2"] and units[2]["duration"] == 12.
    assert all(r["authority"].startswith("reference_context_only") for r in context)


def test_word_timing_trust_change_invalidates_source_units_and_editorial_cache():
    segments = source()[:1]
    untrusted = copy.deepcopy(segments)
    untrusted[0]["word_timing_complete"] = False
    before = story.build_story_beats(segments, "en", target_seconds=60)
    after = story.build_story_beats(untrusted, "en", target_seconds=60)
    assert before[0]["id"] != after[0]["id"]
    brief = {"goal": "short", "target_duration": 60}
    assert story.story_cache_fingerprint(segments, brief, "fixture") != story.story_cache_fingerprint(untrusted, brief, "fixture")


def test_completed_director_decision_cache_expires_but_asr_scenes_and_vision_remain_reusable(monkeypatch, tmp_path):
    from cutroom import cache_keys
    source = tmp_path / "test-source.mp4"
    source.write_bytes(b"source identity fixture; never decoded")
    project = {"sources": {"A": {"name": "test-source.mp4", "size": source.stat().st_size}}}
    settings = SimpleNamespace(ai={}, raw={})
    current = cache_keys.build_analysis_cache_fingerprints(project, settings, {"goal": "short"}, {"A": source})
    with monkeypatch.context() as previous:
        previous.setattr(cache_keys, "STORY_INPUT_POLICY", "bounded-whole-index-canonical-domain-retrieval-v6.explicit-continuity-authority")
        old = cache_keys.build_analysis_cache_fingerprints(project, settings, {"goal": "short"}, {"A": source})
    assert not cache_keys.cache_fingerprints_match(old, current, ("story",))
    assert cache_keys.cache_fingerprints_match(old, current, ("pipeline", "source", "transcript", "scenes", "vision"))


@pytest.mark.parametrize("language,instruction", [
    ("en", "Choose one short with no internal cuts."), ("he", "בחר קטע אחד ללא חיתוכים פנימיים."),
])
def test_explicit_no_cut_still_checks_all_fine_source_units(language, instruction):
    segments = source(language)
    units = story.build_story_beats(segments, language, target_seconds=60)
    chapters = story.build_story_chapters(units)
    from cutroom.edit_styles import enrich_brief_with_style
    brief = enrich_brief_with_style({"goal": "short", "target_duration": 60., "instruction": instruction})
    with pytest.raises(story.StoryPlanningError, match="skips original"):
        story._validate_single_source_passage([units[0]["id"], units[2]["id"]], chapters, brief)


@pytest.mark.parametrize("fault", ["ownership", "overlap", "duplicate", "limit"])
def test_invalid_projection_fails_without_partial_coverage_or_source_repair(fault, monkeypatch):
    segments = source()
    parents = story.build_story_beats(segments, "en")
    if fault == "ownership": parents[0]["segment_ids"].pop()
    elif fault == "overlap": segments[1]["start"] = 1.
    elif fault == "duplicate": segments[1]["id"] = segments[0]["id"]
    else:
        from cutroom import story_candidates
        monkeypatch.setattr(story_candidates, "MAX_SOURCE_SEGMENTS", 2)
    with pytest.raises(story.StoryPlanningError) as error:
        project_short_source_units(parents, segments)
    assert error.value.diagnostic["applied_to_timeline"] is False


def test_unfinished_tail_is_represented_without_claiming_complete_meaning():
    segments = source()[:2]; segments[1]["text"] = "An unfinished continuation..."
    units = story.build_story_beats(segments, "en", target_seconds=60)
    assert [s for u in units for s in u["segment_ids"]] == ["s0", "s1"]
    assert units[-1]["boundary_status"] == "unfinished_parent_tail"
    assert not units[-1]["semantic_coherence_verified"]


@pytest.mark.parametrize("instruction", [
    "Choose one short.", "Choose one video.", "Choose one short, internal cuts are allowed.",
    "בחר סרטון אחד.", "בחר קטע אחד. אפשר לבצע חיתוכים פנימיים.",
])
def test_output_count_alone_never_becomes_a_no_cut_constraint(instruction):
    from cutroom.instruction_contract import explicit_source_continuity_requested
    assert not explicit_source_continuity_requested({"instruction": instruction})


@pytest.mark.parametrize("language", ["en", "he"])
def test_generated_source_reaches_actual_product_projection_unchanged(monkeypatch, language):
    """Generated HE/EN inputs reach the native planner without source rewriting."""
    segments = source_fixture(language)["segments"]
    before = copy.deepcopy(segments)
    calls = []
    class ReachedPlanning(Exception):
        pass
    def inspect(units, enriched, _settings, brief, *_args, **_kwargs):
        calls.append(units)
        assert [sid for u in units for sid in u["segment_ids"]] == [r["id"] for r in segments]
        by_id = {s["id"]: s for s in segments}
        assert len({u["id"] for u in units}) == len(units)
        for u in units:
            rows = [by_id[sid] for sid in u["segment_ids"]]
            assert u["start"] == rows[0]["start"] and u["end"] == rows[-1]["end"]
            assert u["text"] == " ".join(r["text"] for r in rows)
            assert not u["semantic_coherence_verified"]
            assert u["candidate_policy"] == CANDIDATE_POLICY_VERSION
        assert len(units) > len({u["parent_analysis_beat_id"] for u in units})
        # A generated source representation reaches the existing chapter/planner
        # boundary, but this sentinel never pretends a model accepted meaning.
        raise ReachedPlanning
    monkeypatch.setattr(story, "hierarchical_story_edit", inspect)
    with pytest.raises(ReachedPlanning):
        story.plan_edit(segments, SimpleNamespace(ai={}), {"goal": "short", "target_duration": 60., "language": language})
    assert len(calls) == 1 and segments == before
