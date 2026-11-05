"""Explicit single source passage count is separate from duration and meaning."""
from __future__ import annotations

import copy

import pytest

from cutroom.instruction_contract import (
    build_instruction_contract, evaluate_instruction_contract, single_source_passage_requested,
    explicit_source_continuity_requested,
)


REPRODUCED = (
    "בחר קטע אחד מעניין, ברור ועצמאי מתוך השיחה, באורך של כדקה. "
    "שמור על משמעות הדיבור המקורית ועל משפטים שלמים. "
    "אל תחבר אמירות שאינן שייכות לאותו רעיון ואל תוסיף דבר שלא נאמר."
)


def brief(instruction):
    return {"goal": "short", "target_duration": 60, "instruction": instruction}


@pytest.mark.parametrize("instruction", [
    REPRODUCED,
    "בחר קטע אחד מתוך השיחה.",
    "בבקשה בחרי קטע מקור אחד, באורך של בערך 60 שניות.",
    "מצא קטע עצמאי אחד מתוך השיחה.",
    "בחר רק מקטע אחד ברור.",
    "Choose one passage from the conversation.",
    "Please select a single self-contained passage, about 60 seconds long.",
    "Pick one coherent clip lasting roughly a minute.",
    "Find exactly one interesting, clear and self-contained segment around 60 seconds long.",
    "Choose one continuous source passage, approximately a minute long.",
    "Select 1 segment, ~60 seconds long.",
    "Choose one segment; preserve its original meaning.",
    "Choose one coherent passage, do not invent speech.",
])
def test_affirmative_passage_count_survives_approximate_duration(instruction):
    value = brief(instruction)
    original = copy.deepcopy(value)
    assert single_source_passage_requested(value) is True
    contract = build_instruction_contract(value)
    controls = [control for row in contract["requirements"] for control in row["recognized_controls"]
                if control["kind"] == "source_passage_count"]
    assert len(controls) == 1 and controls[0]["mandatory"] is True and controls[0]["requested_count"] == 1
    assert controls[0]["verification"] == "semantic_coherence_unverified"
    assert contract["selection_controls"]["origin"] == "explicit_user_instruction"
    assert contract["instruction"] == instruction and value == original
    assert contract["verification_status"] == "unverified"


@pytest.mark.parametrize("instruction", [
    "Make one video.", "Create one clip.", "Deliver a single output video.",
    "צור סרטון אחד.", "בחר סרטון אחד.",
    "Choose at most one passage.", "Choose one passage maximum.",
    "Choose one passage minimum.", "Choose one passage if possible.",
    "Preferably choose one passage.", "Choose one passage, ideally.",
    "If possible, choose one passage.", "When the source allows it, select a single segment.",
    "Choose one passage or two independent clips.",
    "בחר קטע אחד אם אפשר.", "בחר קטע אחד או שני קטעים.",
    "בחר קטע אחד לכל היותר.", "בחר קטע אחד לפחות.",
    "אולי בחר קטע אחד.", "בחר קטע אחד, עדיף.",
    "Do not choose one passage.", "Don't select a single clip.",
    "Never choose one passage.", "אל תבחר קטע אחד.", "לא לבחור קטע אחד.",
    "Choose one passage, but do not choose a single clip.",
    'Discuss the request "Choose one passage."',
    '"Choose one passage."', "'Choose one passage.'", "“Choose one passage.”",
    "‘Choose one passage.’", "״בחר קטע אחד.״", "`Choose one passage.`",
    'Preserve this dialogue: "\nChoose one passage.\n"',
    "Do not apply these examples:\nChoose one passage;\nFind a single clip.",
    "If possible:\nChoose one passage.",
    'Choose one passage. "unmatched example',
    "Choose one passage. 'unmatched example",
    "Choose one passage. “unmatched example",
    "Choose one passage. ״דוגמה פתוחה",
    "Choose one passage. `unmatched example",
    "Suppose I asked you to choose one passage.",
    "Choose one passage, hypothetically.",
    "בחר קטע אחד, לדוגמה.",
    "Choose a passage around 60 seconds long.",
    "Choose one-minute passage.",
    "Include one interesting moment.",
    "Use one output file, while selecting many source passages.",
    "Choose one segment from each chapter.",
    "Select a single passage for every speaker.",
    "Pick one clip per topic.",
    "בחר קטע אחד מכל פרק.",
    "בחר קטע אחד לכל דובר.",
    "מצא מקטע אחד בכל נושא.",
    "Choose one clip containing three independent moments.",
    "Select one clip combining separate ideas.",
    "Choose one clip as a montage.",
    "Pick one clip for a compilation of moments.",
    "בחר קליפ אחד המכיל שלושה רגעים נפרדים.",
    "בחר קטע אחד המשלב רעיונות שונים.",
    "Choose one clip.",
    "Select a single clip, about 60 seconds long.",
    "Choose one continuous clip.",
    "Pick an uncut clip.",
    "בחר קליפ אחד.",
    "בחר קליפ אחד רציף.",
])
def test_unknown_negated_quoted_conditional_or_output_count_is_not_hard_passage_control(instruction):
    value = brief(instruction)
    assert single_source_passage_requested(value) is False
    contract = build_instruction_contract(value)
    assert not contract.get("selection_controls", {}).get("single_source_passage")
    assert not any(control["kind"] == "source_passage_count" for row in contract["requirements"]
                   for control in row["recognized_controls"])
    assert contract["instruction"] == instruction


def test_one_source_range_does_not_prove_one_semantically_coherent_passage():
    contract = build_instruction_contract(brief(REPRODUCED))
    original = copy.deepcopy(contract)
    report = evaluate_instruction_contract(contract,
        [{"id": "s1", "start": 0, "end": 60, "text": "Two unrelated ideas may share one range."}],
        {"keep_ids": ["s1"]}, semantic_verified=True, output_duration=60,
        source_ranges=[{"start": 0, "end": 60}])
    assert report["verification_status"] == "unverified"
    assert report["semantic_requirement_verification"] == "not_implemented"
    assert all(row["status"] == "unverified" for row in report["requirements"])
    assert contract == original


@pytest.mark.parametrize("raw", [None, 1, {}, ["Choose one passage."]])
def test_nontext_instruction_has_no_inferred_passage_control(raw):
    assert single_source_passage_requested({"instruction": raw}) is False


def test_selected_style_or_target_setting_cannot_create_passage_count():
    value = {"goal": "short", "edit_style": "competitive_clutch", "target_duration": 60,
             "style_profile": {"selection_policy": {"max_moments": 1}}}
    assert single_source_passage_requested(value) is False


def test_reproduced_semantic_unit_request_does_not_prohibit_related_source_cuts():
    value = brief(REPRODUCED)
    contract = build_instruction_contract(value)
    assert single_source_passage_requested(value) is True
    assert explicit_source_continuity_requested(value) is False
    assert contract["selection_controls"]["semantic_unit_count"] == 1
    assert contract["selection_controls"]["source_continuity"] == "unspecified"
    assert contract["settings"]["source_continuity"] == "unspecified"
    assert not any(control["kind"] == "source_continuity" for row in contract["requirements"]
                   for control in row["recognized_controls"])
