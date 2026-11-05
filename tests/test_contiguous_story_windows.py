"""Bounded retrieval windows must cover source tails and page-boundary pairs."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom.intelligence import _story_prompt_tokens
from cutroom.story_context import StoryContextError, bounded_contiguous_source_windows


def units(count=8, *, language="en"):
    wording = "A complete idea with its qualification and original conclusion. "
    if language == "he":
        wording = "רעיון שלם עם ההסתייגות שלו והמסקנה המקורית. "
    return [{"id": f"b{59 + index}", "start": index * 30.0, "end": index * 30.0 + 24,
             "segment_ids": [f"s{index}"], "text": wording * 12 + f"TAIL-{index}.",
             "segments": [{"id": f"s{index}", "start": index * 30.0, "end": index * 30.0 + 24,
                           "text": wording * 12 + f"TAIL-{index}.",
                           "words": [{"word": "original", "start": index * 30.0, "end": index * 30.0 + 1}]}]}
            for index in range(count)]


def identifiers(windows):
    return [[row["id"] for row in window] for window in windows]


def test_overlapping_windows_cover_a_pair_crossing_a_nonoverlapping_page_boundary():
    source = units(4)
    windows = bounded_contiguous_source_windows(source, lambda rows: rows, lambda rows: len(rows) <= 2)
    assert identifiers(windows) == [["b59", "b60"], ["b60", "b61"], ["b61", "b62"]]


def test_late_canonical_pairs_are_considered_without_first_n_bias():
    source = units(8)
    weights = dict(zip([row["id"] for row in source], (40, 40, 26, 28, 40, 40, 28, 30)))
    windows = bounded_contiguous_source_windows(source, lambda rows: rows,
                                                lambda rows: sum(weights[row["id"]] for row in rows) <= 60)
    assert ["b61", "b62"] in identifiers(windows)
    assert ["b65", "b66"] in identifiers(windows)
    assert {row["id"] for window in windows for row in window} == set(weights)
    assert all(sum(weights[row["id"]] for row in window) <= 60 for window in windows)


@pytest.mark.parametrize("language,instruction", [
    ("en", "Choose one coherent passage, about 60 seconds long."),
    ("he", "בחר קטע אחד מעניין ועצמאי, באורך של כדקה."),
])
@pytest.mark.parametrize("context_cap", [8192, 32768])
def test_full_payload_budget_and_exact_canonical_coverage(language, instruction, context_cap):
    source = units(18, language=language)
    original = copy.deepcopy(source)
    brief = {"instruction": instruction, "target_duration": 60, "ordered_role_groups": [["setup", "result"]]}
    captured = []

    def payload(rows):
        value = {"format": {"type": "object"}, "options": {"num_ctx": context_cap, "num_predict": 2400},
                 "messages": [{"role": "user", "content": json.dumps({"brief": brief, "source_units": rows}, ensure_ascii=False)}]}
        captured.append(value)
        return value

    def fits(value):
        return _story_prompt_tokens(value) + 2400 <= context_cap

    windows = bounded_contiguous_source_windows(source, payload, fits)
    positions = {row["id"]: index for index, row in enumerate(source)}
    ranges = [(positions[window[0]["id"]], positions[window[-1]["id"]] + 1) for window in windows]
    assert windows and {row["id"] for window in windows for row in window} == set(positions)
    for window, (start, end) in zip(windows, ranges):
        assert window == source[start:end]
        assert fits(payload(window))
    # Every fitting contiguous subsequence is contained in an emitted window.
    for start in range(len(source)):
        for end in range(start + 1, len(source) + 1):
            if fits(payload(source[start:end])):
                assert any(left <= start and end <= right for left, right in ranges)
    assert all(not (left <= start and end <= right)
               for index, (start, end) in enumerate(ranges) for left, right in ranges[:index])
    assert all(json.loads(row["messages"][0]["content"])["brief"] == brief for row in captured)
    assert source == original


def test_nonmonotone_payload_budget_does_not_hide_a_later_fitting_window():
    source = units(3)
    windows = bounded_contiguous_source_windows(source, lambda rows: rows, lambda rows: len(rows) in {1, 3})
    assert windows == [source]


def test_contained_windows_are_omitted_and_source_is_canonically_sorted():
    source = units(5)
    scrambled = [source[4], source[1], source[3], source[0], source[2]]
    before = copy.deepcopy(scrambled)
    windows = bounded_contiguous_source_windows(scrambled, lambda rows: rows, lambda rows: len(rows) <= 3)
    assert identifiers(windows) == [["b59", "b60", "b61"], ["b60", "b61", "b62"], ["b61", "b62", "b63"]]
    assert scrambled == before
    windows[0][1]["segments"][0]["words"][0]["word"] = "mutated detached copy"
    assert scrambled == before
    assert windows[1][0]["segments"][0]["words"][0]["word"] == "original"


def test_payload_builder_mutation_cannot_change_the_canonical_units_or_windows():
    source = units(3)
    before = copy.deepcopy(source)

    def mutate(rows):
        rows[0]["id"] = "foreign callback mutation"
        rows[0]["segments"][0]["text"] = "rewritten"
        return rows

    windows = bounded_contiguous_source_windows(source, mutate, lambda rows: len(rows) <= 2)
    assert source == before
    assert identifiers(windows) == [["b59", "b60"], ["b60", "b61"]]
    assert windows == [source[:2], source[1:]]


def test_oversized_atomic_tail_raises_instead_of_silently_omitting_it():
    source = units(5)
    before = copy.deepcopy(source)
    with pytest.raises(StoryContextError) as error:
        bounded_contiguous_source_windows(source, lambda rows: rows,
                                          lambda rows: all(row["id"] != "b63" for row in rows))
    assert error.value.diagnostic["reason"] == "story_input_context_limit"
    assert error.value.diagnostic["applied_to_timeline"] is False
    assert source == before


@pytest.mark.parametrize("mutation", ["duplicate", "empty_id", "nan", "negative", "boolean", "reversed"])
def test_invalid_canonical_identity_or_clock_rejects_before_budget_callbacks(mutation):
    source = units(2)
    if mutation == "duplicate":
        source[1]["id"] = source[0]["id"]
    elif mutation == "empty_id":
        source[1]["id"] = " "
    elif mutation == "nan":
        source[1]["end"] = float("nan")
    elif mutation == "negative":
        source[1]["start"] = -1
    elif mutation == "boolean":
        source[1]["start"] = True
    else:
        source[1]["end"] = source[1]["start"]
    with pytest.raises(StoryContextError):
        bounded_contiguous_source_windows(source, lambda _rows: pytest.fail("invalid source must reject first"), lambda _value: True)


def test_empty_source_does_not_fabricate_a_window_or_model_payload():
    assert bounded_contiguous_source_windows([], lambda _rows: pytest.fail("no source payload"), lambda _value: True) == []
