"""Bounded HE/EN parity; this is not natural-language or model quality proof."""
import copy
from types import SimpleNamespace

import pytest

import server
from cutroom import cache_keys, instruction_contract as contract, intelligence
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.story_budget import StoryBudgetError
from test_media_library import api


def brief(text, **changes):
    return {"goal": "short", "instruction": text, "target_duration": 60., "duration_mode": "style",
            "aspect": "9:16", "edit_style": "funny_moments", "output_count": 1,
            "source_continuity": "unspecified", **changes}


@pytest.mark.parametrize("en,he", [
    ("Make exactly 45 seconds.", "צור בדיוק 45 שניות."),
    ("Make a video of exactly 45 seconds.", "צור סרטון של בדיוק 45 שניות."),
    ("I want exactly 45 seconds.", "אני רוצה בדיוק 45 שניות."),
    ("Duration: exactly 45 seconds.", "משך: בדיוק 45 שניות."),
    ("Make exactly 1.5 minutes.", "צור בדיוק 1.5 דקות."),
])
def test_exact_duration_is_equivalent_and_source_cannot_silently_shrink_it(en, he):
    rows = []
    for text in (en, he):
        expected = 90. if "1.5" in text else 45.
        b = brief(text, target_duration=120. if expected == 90. else 60.); before = copy.deepcopy(b)
        c = contract.assert_instruction_contract(b)
        bounds = contract.effective_duration_bounds(b, source_duration=20.)
        # A shorter available source must not rewrite the explicit request.
        assert bounds["minimum_seconds"] == bounds["maximum_seconds"] == expected
        assert bounds["origin"] == "explicit_user_exact"
        assert c["instruction"] == text and c["verification_status"] == "unverified"
        assert b == before
        rows.append((bounds["minimum_seconds"], bounds["maximum_seconds"], bounds["origin"]))
    assert rows[0] == rows[1]


@pytest.mark.parametrize("en,he", [
    ("Make four videos.", "צור ארבעה סרטונים."),
    ("Create five clips.", "צור חמישה קליפים."),
    ("Make six shorts.", "צור שישה שורטים."),
    ("Create seven videos.", "צור שבעה סרטונים."),
    ("Make eight outputs.", "צור שמונה תוצרים."),
    ("Create nine clips.", "צור תשעה קליפים."),
    ("Make ten videos.", "צור עשרה סרטונים."),
    ("Make four videos.", "צור ארבע סרטונים."),
    ("Make five videos.", "צור חמש סרטונים."),
    ("Make six videos.", "צור שש סרטונים."),
    ("Make seven videos.", "צור שבע סרטונים."),
    ("Make nine videos.", "צור תשע סרטונים."),
    ("Make ten videos.", "צור עשר סרטונים."),
])
def test_unsupported_multiple_outputs_block_equally_before_actual_planner(en, he, monkeypatch):
    monkeypatch.setattr(intelligence, "hierarchical_story_edit", lambda *a, **k: pytest.fail("Unsupported count reached model planner"))
    for text in (en, he):
        b = brief(text); before = copy.deepcopy(b)
        with pytest.raises(StoryBudgetError) as caught:
            intelligence.plan_edit([{"id": "s", "start": 0., "end": 60., "text": "Synthetic unchanged source."}], SimpleNamespace(ai={}), b)
        assert caught.value.diagnostic["reason"] == "unsupported_output_count"
        assert b == before


@pytest.mark.parametrize("text", [
    "Do not make four videos.", "אל תיצור ארבעה סרטונים.",
    "If possible, make six clips.", "אם אפשר צור שישה קליפים.",
    '"Make ten videos."', '"צור עשרה סרטונים."',
    "Make four videos or one video.", "צור ארבעה סרטונים או סרטון אחד.",
    "The speaker said create six clips.", "הדובר אמר צור שישה קליפים.",
    "Make one video from six source clips.", "צור סרטון אחד משישה קטעי מקור.",
])
def test_scoped_counts_are_not_silently_promoted_to_output_requirements(text):
    c = contract.build_instruction_contract(brief(text))
    assert not any(x["code"] == "unsupported_output_count" for x in c["issues"])
    assert c["instruction"] == text


@pytest.mark.parametrize("text", [
    "Do not make exactly 45 seconds.", "אל תיצור בדיוק 45 שניות.",
    "Make exactly 45 seconds, if possible.", "צור בדיוק 45 שניות אם אפשר.",
    '"Make exactly 45 seconds."', '"צור בדיוק 45 שניות."',
    "Style: exactly 45 seconds.", "סגנון: בדיוק 45 שניות.",
])
def test_exact_word_does_not_override_negation_condition_quotation_or_style_scope(text):
    c = contract.build_instruction_contract(brief(text))
    exact = [x for r in c["requirements"] for x in r["recognized_controls"] if x["kind"] == "duration" and x["mandatory"]]
    assert exact == []
    assert c["instruction"] == text


@pytest.mark.parametrize("text", [
    "Make exactly 60 seconds. Make exactly 45 seconds.", "צור בדיוק 60 שניות. צור בדיוק 45 שניות.",
    "Make exactly 45 seconds. Aim for 50-60 seconds.", "צור בדיוק 45 שניות. כוון ל50-60 שניות.",
])
def test_contradictory_exact_or_ranged_requests_block_in_both_languages(text, monkeypatch):
    monkeypatch.setattr(intelligence, "hierarchical_story_edit", lambda *a, **k: pytest.fail("Contradiction reached model planner"))
    with pytest.raises(StoryBudgetError) as caught:
        intelligence.plan_edit([{"id": "s", "start": 0., "end": 60., "text": "Source."}], SimpleNamespace(ai={}), brief(text))
    assert caught.value.diagnostic["reason"] in {"instruction_duration_conflict", "instruction_duration_range_conflict"}


@pytest.mark.parametrize("text", [
    "Make one video without cuts. Make exactly 45 seconds.", "צור סרטון אחד בלי חיתוכים. צור בדיוק 45 שניות.",
])
def test_style_does_not_weaken_explicit_count_continuity_or_duration(text):
    b = brief(text); enriched = enrich_brief_with_style(b)
    c = contract.assert_instruction_contract(enriched)
    assert c["selection_controls"]["source_continuity"] == "required"
    assert enriched["style_profile"]["selection_policy"]["preserve_source_continuity"] is True
    assert contract.effective_duration_bounds(enriched)["minimum_seconds"] == 45.
    assert enriched["instruction"] == text and c["settings"]["output_count"] == 1


@pytest.mark.parametrize("text", ["Make four videos.", "צור ארבעה סרטונים."])
def test_normal_api_surfaces_unsupported_count_without_ai_or_mutation(api, monkeypatch, text):
    app, client, store, pid = api; before = store.state_path(pid).read_bytes()
    monkeypatch.setattr(server, "story_ai_status", lambda *a, **k: pytest.fail("Count conflict reached AI"))
    b = brief(text)
    review = client.post(f"/api/projects/{pid}/director/request-review", json=b)
    assert review.status_code == 200 and review.get_json()["ready"] is False
    assert any(x["code"] == "unsupported_output_count" for x in review.get_json()["contract"]["issues"])
    generated = client.post(f"/api/projects/{pid}/director", json=b)
    assert generated.status_code == 400
    assert store.state_path(pid).read_bytes() == before
    assert not app.extensions["cutroom_jobs"].active(project_id=pid)


def test_parser_policy_upgrade_invalidates_only_story_cache(monkeypatch):
    current = cache_keys.STORY_INPUT_POLICY
    settings = SimpleNamespace(ai={}, raw={}); b = brief("צור בדיוק 45 שניות.")
    monkeypatch.setattr(cache_keys, "STORY_INPUT_POLICY", "bounded-whole-index-canonical-domain-retrieval-v20.candidate-local-context")
    old = cache_keys.build_analysis_cache_fingerprints({}, settings, b, {})
    monkeypatch.setattr(cache_keys, "STORY_INPUT_POLICY", current)
    new = cache_keys.build_analysis_cache_fingerprints({}, settings, b, {})
    assert old["story"] != new["story"]
    assert all(old[k] == new[k] for k in ("source", "transcript", "scenes", "vision", "pipeline"))
