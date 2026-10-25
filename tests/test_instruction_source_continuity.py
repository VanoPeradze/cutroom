"""An editorial unit/output count is not a continuous-source/no-cuts directive."""
from __future__ import annotations

import copy

import pytest

from cutroom.instruction_contract import (
    assert_instruction_contract, build_instruction_contract, evaluate_instruction_contract,
    explicit_source_continuity_requested, single_source_passage_requested,
)
from cutroom.story_budget import StoryBudgetError


def brief(instruction, **settings):
    return {"goal": "short", "target_duration": 60, "instruction": instruction, **settings}


@pytest.mark.parametrize("instruction", [
    "Make one video with several related cuts.",
    "Deliver one Short, about sixty seconds long.",
    "Choose one coherent passage. Related cuts are allowed.",
    "Pick one self-contained segment and preserve whole utterances.",
    "Choose one clip containing three independent moments.",
    "Choose one clip and do not combine unrelated statements.",
    "Create three outputs of 20 seconds each.",
    "Create a 60-second clip, with no invented speech.",
    "בחר קטע אחד מעניין, ברור ועצמאי מתוך השיחה, באורך של כדקה. "
    "שמור על משמעות הדיבור המקורית ועל משפטים שלמים. אל תחבר אמירות שאינן שייכות לאותו רעיון.",
    "צור סרטון אחד עם כמה חיתוכים קשורים.",
    "בחר קטע אחד עצמאי. אפשר לחתוך בין אמירות קשורות.",
    "בחר קטע אחד ושמור על משפטים שלמים.",
    "צור שלושה סרטונים של 20 שניות כל אחד.",
    "Keep the edit coherent and continuous.",
    "Make one continuous video.",
])
def test_output_count_semantic_coherence_and_whole_utterances_do_not_require_source_continuity(instruction):
    value = brief(instruction)
    original = copy.deepcopy(value)
    contract = build_instruction_contract(value)
    assert explicit_source_continuity_requested(value) is False
    assert contract["settings"]["source_continuity"] == "unspecified"
    assert contract["selection_controls"]["source_continuity"] == "unspecified"
    assert contract["selection_controls"]["source_continuity_origin"] == "unspecified"
    assert not any(control["kind"] == "source_continuity" for row in contract["requirements"]
                   for control in row["recognized_controls"])
    assert value == original and contract["instruction"] == instruction


@pytest.mark.parametrize("instruction", [
    "Choose one continuous source passage, about a minute long.",
    "Select a single contiguous passage from the recording.",
    "Use an uncut source segment.",
    "Keep the selected source passage continuous.",
    "Preserve the source passage without any internal cuts.",
    "Do not cut within the source passage.",
    "Don't split the source segment.",
    "Do not add internal cuts inside the source clip.",
    "Choose one continuous clip.",
    "Select a single uncut clip.",
    "בחר קטע אחד רציף מתוך המקור, באורך של כדקה.",
    "בחר קטע מקור אחד רציף.",
    "שמור על קטע המקור ללא חיתוכים.",
    "אל תחתוך בתוך קטע המקור.",
    "אל תבצע חיתוכים בתוך קטע המקור.",
    "בחר קליפ אחד רציף.",
])
def test_actual_explicit_source_continuity_directives_keep_provenance_and_remain_unverified(instruction):
    value = brief(instruction)
    contract = build_instruction_contract(value)
    assert explicit_source_continuity_requested(value) is True
    assert contract["settings"]["source_continuity"] == "required"
    assert contract["selection_controls"]["source_continuity"] == "required"
    assert contract["selection_controls"]["source_continuity_origin"] == "explicit_user_instruction"
    controls = [control for row in contract["requirements"] for control in row["recognized_controls"]
                if control["kind"] == "source_continuity"]
    assert len(controls) == 1
    control = controls[0]
    assert instruction[control["instruction_start"]:control["instruction_end"]] == control["text"]
    assert control["origin"] == "explicit_user_instruction" and control["mandatory"] is True
    assert control["verification"] == "source_continuity_unverified"
    assert contract["verification_status"] == "unverified"


@pytest.mark.parametrize("instruction", [
    "Do not choose one continuous source passage.",
    "Never preserve the source passage continuous.",
    "Choose one continuous source passage if possible.",
    "If needed, do not cut within the source passage.",
    "Do not cut within the source passage, unless necessary.",
    '"Choose one continuous source passage."',
    "‘Do not cut within the source passage.’",
    "If possible:\nChoose one continuous source passage.",
    'Choose one continuous source passage. "unmatched quotation',
    "Choose one contiguous source passage per speaker.",
    "אל תשמור על קטע המקור רציף.",
    "בחר קטע אחד רציף אם אפשר.",
    "אל תחתוך בתוך קטע המקור, אם אפשר.",
    "״בחר קטע מקור אחד רציף.״",
    "בחר קטע מקור אחד רציף מכל פרק.",
    "If possible\nChoose one continuous source passage.",
    "For example\nDo not cut within the source passage.",
    "אם אפשר\nבחר קטע מקור אחד רציף.",
    "Choose one continuous source passage, but not uncut.",
    "בחר קטע מקור אחד רציף, אבל לא ללא חיתוכים.",
])
def test_negation_quotation_conditions_and_distributive_scope_stay_unspecified(instruction):
    value = brief(instruction)
    assert explicit_source_continuity_requested(value) is False
    assert build_instruction_contract(value)["selection_controls"]["source_continuity"] == "unspecified"


@pytest.mark.parametrize("instruction", [
    "Choose one continuous source passage. Related cuts are allowed.",
    "Preserve the source passage without any cuts. Allow internal cuts.",
    "בחר קטע מקור אחד רציף. אפשר לחתוך בין אמירות קשורות.",
    "Choose one continuous source passage, but related cuts are allowed.",
    "בחר קטע מקור אחד רציף, אבל אפשר לחתוך בין אמירות קשורות.",
])
def test_conflicting_explicit_cut_policies_are_surfaced_without_guessing_precedence(instruction):
    value = brief(instruction)
    contract = build_instruction_contract(value)
    assert contract["selection_controls"]["source_continuity"] == "conflict"
    assert contract["verification_status"] == "not_fulfilled"
    assert contract["issues"][0]["code"] == "instruction_source_continuity_conflict"
    with pytest.raises(StoryBudgetError) as error:
        assert_instruction_contract(value)
    assert error.value.diagnostic["reason"] == "instruction_source_continuity_conflict"


def test_style_defaults_cannot_become_user_no_cut_directives():
    value = brief("Choose one interesting self-contained passage, about 60 seconds.",
                  style_profile={"selection_policy": {"max_moments": 1, "continuous_source": True}},
                  source_continuity="unspecified")
    assert single_source_passage_requested(value) is True
    assert explicit_source_continuity_requested(value) is False
    assert build_instruction_contract(value)["selection_controls"]["source_continuity"] == "unspecified"


def test_reviewed_continuity_control_is_explicit_and_separate_from_style_defaults():
    value=brief('Choose one interesting self-contained passage, about 60 seconds.',
                source_continuity='required',style_profile={'selection_policy':{'max_moments':5}})
    assert explicit_source_continuity_requested(value) is True
    contract=build_instruction_contract(value)
    assert contract['selection_controls']['source_continuity']=='required'
    assert contract['selection_controls']['source_continuity_origin']=='explicit_review_control'
    assert contract['instruction']==value['instruction']


def test_even_one_final_range_does_not_prove_semantic_or_continuity_compliance():
    value = brief("Choose one continuous source passage.")
    contract = build_instruction_contract(value)
    report = evaluate_instruction_contract(contract,
        [{"id": "s1", "start": 0, "end": 60, "text": "Machine bookkeeping is not a meaning review."}],
        {"keep_ids": ["s1"]}, semantic_verified=True, output_duration=60,
        source_ranges=[{"start": 0, "end": 60}])
    assert report["verification_status"] == "unverified"
    assert all(row["status"] == "unverified" for row in report["requirements"])
    assert report["instruction"] == value["instruction"]


@pytest.mark.parametrize("instruction", ["Choose one clip.", "Select a single clip, about 60 seconds long.", "בחר קליפ אחד."])
def test_generic_clip_output_count_does_not_infer_one_idea_or_source_continuity(instruction):
    value = brief(instruction)
    contract = build_instruction_contract(value)
    assert single_source_passage_requested(value) is False
    assert explicit_source_continuity_requested(value) is False
    assert contract["selection_controls"].get("semantic_unit_count") is None
    assert contract["selection_controls"]["source_continuity"] == "unspecified"
    assert contract["instruction"] == instruction


@pytest.mark.parametrize("instruction", ["Choose one continuous clip.", "Select a single uncut clip.", "בחר קליפ אחד רציף."])
def test_explicit_clip_continuity_does_not_infer_one_editorial_idea(instruction):
    value = brief(instruction)
    contract = build_instruction_contract(value)
    assert explicit_source_continuity_requested(value) is True
    assert single_source_passage_requested(value) is False
    assert contract["selection_controls"].get("semantic_unit_count") is None
    assert contract["selection_controls"]["source_continuity"] == "required"


def test_explicit_duration_conflict_stays_independent_of_semantic_unit_and_continuity():
    value = brief("Make a 30-second Short. Choose one self-contained clip.",
                  style_profile={"selection_policy": {"max_moments": 3}})
    contract = build_instruction_contract(value)
    assert single_source_passage_requested(value) is True
    assert explicit_source_continuity_requested(value) is False
    assert contract["issues"][0]["code"] == "instruction_duration_conflict"
    with pytest.raises(StoryBudgetError):
        assert_instruction_contract(value)
