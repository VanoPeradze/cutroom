"""Selected-quote witness normalization; no inference or media operations."""
from __future__ import annotations

import copy

import pytest

from cutroom.precision_neutral import adapt_neutral_temporal_witness
from cutroom.story_evidence import build_story_evidence_catalog


PURPOSE = "self_contained_passage"


def fixture(language="en"):
    texts = (["I missed the bus.", "I left earlier the next day.", "I arrived on time."] if language == "en"
             else ["פספסתי את האוטובוס.", "למחרת יצאתי מוקדם יותר.", "הגעתי בזמן."])
    segments = [{"id": f"s{index + 1}", "start": float(index * 10), "end": float((index + 1) * 10),
                 "text": text, "words": [{"word": text, "start": float(index * 10), "end": float((index + 1) * 10)}]}
                for index, text in enumerate(texts)]
    beats = [{"id": f"b{index + 1}", "start": row["start"], "end": row["end"], "duration": 10.,
              "segment_ids": [row["id"]], "text": row["text"]} for index, row in enumerate(segments)]
    catalog = build_story_evidence_catalog(beats, segments)
    choices = [f"{row['text']} [{row['id']}]" for row in catalog]
    result = {"verdict": "fit", "role_selections": {PURPOSE: {
        "primary_anchor_choice": choices[0], "additional_primary_evidence_choices": choices[1:],
        "context_evidence_choices_by_chapter": {}}},
        "highlight_beat_ids": ["b2"], "title": "Original model title", "summary": "Original model summary"}
    chapters = [{"id": "c1", "beats": copy.deepcopy(beats), "beat_ids": [row["id"] for row in beats]}]
    plan = {"slots": [{"purpose": PURPOSE, "chapter_ids": ["c1"], "required_context_chapter_ids": []}]}
    brief = {"goal": "short", "target_duration": 30, "instruction": "Choose one coherent idea."}
    return [result, catalog, beats, segments, chapters, plan, brief]


def selected_choices(result):
    role = result["role_selections"][PURPOSE]
    return [role["primary_anchor_choice"], *role["additional_primary_evidence_choices"]]


@pytest.mark.parametrize("language", ["en", "he"])
def test_moves_only_selected_final_quote_preserves_exact_set_and_all_inputs(language):
    args = fixture(language)
    original = copy.deepcopy(args)
    adapted, provenance = adapt_neutral_temporal_witness(*args, eligible=True)
    assert args == original
    assert provenance["raw_anchor"] == selected_choices(args[0])[0]
    assert provenance["new_anchor"] == selected_choices(args[0])[-1]
    assert provenance["interpretation_verified"] is False
    assert provenance["source_choices_preserved"] is True
    assert len(provenance["source_fingerprint"]) == 64
    assert selected_choices(adapted)[0] == selected_choices(args[0])[-1]
    assert set(selected_choices(adapted)) == set(selected_choices(args[0]))
    assert len(selected_choices(adapted)) == len(selected_choices(args[0]))
    assert {k: adapted[k] for k in adapted if k != "role_selections"} == {k: args[0][k] for k in args[0] if k != "role_selections"}
    adapted["role_selections"][PURPOSE]["additional_primary_evidence_choices"].clear()
    assert args == original  # The returned proposal is detached.


def test_does_not_add_unselected_later_beat_or_quote():
    args = fixture()
    args[0]["role_selections"][PURPOSE]["additional_primary_evidence_choices"].pop()
    adapted, provenance = adapt_neutral_temporal_witness(*args, eligible=True)
    assert provenance["new_anchor"].endswith("[b2:s2:f1]")
    assert all("b3:" not in choice for choice in selected_choices(adapted))


def test_already_valid_anchor_is_an_idempotent_noop():
    args = fixture()
    adapted, _ = adapt_neutral_temporal_witness(*args, eligible=True)
    args[0] = adapted
    again, provenance = adapt_neutral_temporal_witness(*args, eligible=True)
    assert again == adapted and again is not adapted
    assert provenance is None


@pytest.mark.parametrize("case", ["ineligible", "non_short", "explicit_role", "multiple_roles", "required_context",
                                    "no_fit", "unknown_choice", "forged_wording", "duplicate_choice", "duplicate_anchor",
                                    "forged_catalog", "duplicate_ownership", "foreign_chapter", "malformed_role", "foreign_highlight"])
def test_invalid_or_non_neutral_proposals_remain_unchanged(case):
    args = fixture()
    result, catalog, beats, segments, chapters, plan, brief = args
    role = result["role_selections"][PURPOSE]
    eligible = case != "ineligible"
    if case == "non_short": brief["goal"] = "long"
    elif case == "explicit_role": plan["slots"][0]["purpose"] = "result"
    elif case == "multiple_roles": plan["slots"].append(copy.deepcopy(plan["slots"][0]))
    elif case == "required_context": plan["slots"][0]["required_context_chapter_ids"] = ["c1"]
    elif case == "no_fit": args[0] = {"verdict": "no_fit", "reason": "source_order", "missing_purposes": [PURPOSE]}
    elif case == "unknown_choice": role["additional_primary_evidence_choices"][0] = "unknown [b9:s9:f1]"
    elif case == "forged_wording": role["additional_primary_evidence_choices"][0] = "Invented outcome. [b2:s2:f1]"
    elif case == "duplicate_choice": role["additional_primary_evidence_choices"].append(role["additional_primary_evidence_choices"][0])
    elif case == "duplicate_anchor": role["additional_primary_evidence_choices"].append(role["primary_anchor_choice"])
    elif case == "forged_catalog": catalog[0]["text"] = "Forged source."
    elif case == "duplicate_ownership": beats[1]["segment_ids"].append("s1")
    elif case == "foreign_chapter": plan["slots"][0]["chapter_ids"] = ["unknown"]
    elif case == "malformed_role": role["additional_primary_evidence_choices"] = "not a list"
    elif case == "foreign_highlight": result["highlight_beat_ids"] = ["foreign"]
    original = copy.deepcopy(args)
    adapted, provenance = adapt_neutral_temporal_witness(*args, eligible=eligible)
    assert args == original
    assert adapted == args[0] and adapted is not args[0]
    assert provenance is None


@pytest.mark.parametrize("component", ["word_times", "chapter_metadata", "beat_metadata"])
def test_source_fingerprint_binds_complete_source_not_only_quote_labels(component):
    args = fixture()
    _, original = adapt_neutral_temporal_witness(*args, eligible=True)
    if component == "word_times": args[3][0]["words"][0]["start"] = .25
    elif component == "chapter_metadata": args[4][0]["source_generation"] = "alternate-ASR"
    else: args[2][0]["source_generation"] = "alternate-ASR"
    _, changed = adapt_neutral_temporal_witness(*args, eligible=True)
    assert changed["source_fingerprint"] != original["source_fingerprint"]


def test_same_ids_with_changed_source_wording_cannot_reuse_old_choices():
    args = fixture()
    args[3][0]["text"] = "Different transcript with reused IDs."
    args[2][0]["text"] = args[3][0]["text"]
    args[1] = build_story_evidence_catalog(args[2], args[3])
    original = copy.deepcopy(args)
    adapted, provenance = adapt_neutral_temporal_witness(*args, eligible=True)
    assert args == original and adapted == args[0]
    assert provenance is None
