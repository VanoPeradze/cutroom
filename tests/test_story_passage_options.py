"""Mechanical whole-source options do not establish a semantic fit."""
from __future__ import annotations

import copy

import pytest

import cutroom.story_passage_options as passage
from cutroom.story_budget import StoryPlanningError


def fixture(*, count=3, seconds=20, gap=0, target=60, instruction=None, language="en"):
    texts = (["The editor checks the report.", "AI does not replace every human judgment.",
              "That is why the final decision needs review."] if language == "en" else
             ["העורך בודק את הדיווח.", "המערכת לא מחליפה כל החלטה של אדם.",
              "לכן ההחלטה הסופית דורשת בדיקה."])
    segments, units = [], []
    for index in range(count):
        start = index * (seconds + gap)
        text = texts[index % len(texts)]
        segment = {"id": f"s{index:03}", "start": start, "end": start + seconds,
                   "text": text, "words": [{"start": start, "end": start + seconds,
                                             "word": text}], "word_timing_complete": True}
        segments.append(segment)
        units.append({"id": f"u{index:03}", "start": start, "end": start + seconds,
                      "text": text, "segment_ids": [segment["id"]],
                      "boundary_status": "punctuation_at_asr_boundary"})
    chapters = [{"id": "c1", "beats": units}]
    plan = {"slots": [{"purpose": "self_contained_passage", "chapter_ids": ["c1"],
                       "required_context_chapter_ids": []}]}
    brief = {"goal": "short", "target_duration": target, "duration_mode": "target",
             "instruction": instruction or ("Choose one coherent self-contained passage." if language == "en"
                                             else "בחר קטע אחד עצמאי וברור.")}
    return units, segments, chapters, plan, brief


def enumerate_fixture(values, *, candidates=None, cost=None, cancel=None):
    units, segments, chapters, plan, brief = values
    calls = []

    def native_cost(identifiers):
        calls.append(list(identifiers))
        selected = [row for row in units if row["id"] in identifiers]
        raw = sum(row["end"] - row["start"] for row in selected)
        return {"approved_seconds": raw, "minimum_safe_seconds": raw,
                "fits_target": raw <= brief["target_duration"] + .05,
                "protect_action_span": bool(((brief.get("style_profile") or {}).get("selection_policy") or {}).get("protect_action_span"))}

    result = passage.enumerate_passage_options(candidates if candidates is not None else units,
        segments, chapters, plan, brief, cost or native_cost, cancel)
    return result, calls


@pytest.mark.parametrize("language", ["he", "en"])
def test_complete_whole_source_option_exactly_preserves_words_ids_times_and_negation(language):
    values = fixture(language=language)
    before = copy.deepcopy(values)
    result, calls = enumerate_fixture(values)
    assert values == before
    assert len(result["options"]) == 1
    option = result["options"][0]
    assert option["beat_ids"] == ["u000", "u001", "u002"]
    assert option["segment_ids"] == ["s000", "s001", "s002"]
    assert option["playback_ranges"] == [{"start": 0, "end": 20}, {"start": 20, "end": 40},
                                          {"start": 40, "end": 60}]
    assert option["raw_playable_seconds"] == 60
    assert option["semantic_fit_verified"] is False
    assert option["selection_forced"] is False
    assert option["frame_validation_required"] is True
    assert result["receipt"]["source_segments"] == values[1]
    assert result["receipt"]["candidate_inventory"] == values[0]
    assert result["receipt"]["visited_windows"] == 6
    assert result["receipt"]["search_complete_within_scope"] is True
    assert result["receipt"]["coverage"]["window_outcomes"]["numeric_option"] == 1
    assert calls == [["u000", "u001", "u002"]]
    result["receipt"]["source_segments"][0]["text"] = "mutated returned value"
    assert values == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_no_raw_option_is_numeric_subset_result_not_semantic_no_fit(language):
    values = fixture(seconds=25, target=60, language=language)
    result, calls = enumerate_fixture(values)
    assert result["options"] == []
    assert calls == []
    assert result["receipt"]["visited_windows"] == 6
    assert result["receipt"]["semantic_fit_verified"] is False
    assert "semantic no-fit is not established" in result["receipt"]["empty_result_meaning"]


@pytest.mark.parametrize("one_output,no_cut", [
    ("Make one video with several related cuts.", "Do not cut within the source passage."),
    ("צור סרטון אחד עם כמה חיתוכים קשורים.", "אל תחתוך בתוך קטע המקור."),
])
def test_one_output_keeps_whole_unit_gaps_but_explicit_no_cut_prices_envelope(one_output, no_cut):
    values = fixture(gap=1, instruction=one_output)
    result, _ = enumerate_fixture(values)
    option = result["options"][0]
    assert option["raw_playable_seconds"] == 60
    assert len(option["playback_ranges"]) == 3
    assert option["explicit_source_continuity_requested"] is False
    values[-1]["instruction"] = no_cut
    continuous, calls = enumerate_fixture(values)
    assert continuous["options"] == []  # All three units span62s; no silence is assumed.
    assert calls == []
    values[-1]["target_duration"] = 62
    continuous, _ = enumerate_fixture(values)
    assert continuous["options"][0]["playback_ranges"] == [{"start": 0, "end": 62}]
    assert continuous["options"][0]["raw_playable_seconds"] == 62
    assert continuous["options"][0]["minimum_safe_seconds"] == 62
    assert continuous["options"][0]["cost"]["approved_seconds"] == 60


@pytest.mark.parametrize("instruction", [
    "Do not choose one continuous source passage.", "אל תשמור על קטע המקור רציף.",
])
def test_negated_no_cut_is_not_reinterpreted_as_continuity(instruction):
    result, _ = enumerate_fixture(fixture(gap=.001, instruction=instruction))
    assert result["options"][0]["raw_playable_seconds"] == 60
    assert result["options"][0]["explicit_source_continuity_requested"] is False


def test_style_protects_action_span_without_inventing_source_continuity():
    values = fixture(gap=1)
    values[-1]["style_profile"] = {"selection_policy": {"protect_action_span": True, "max_moments": 1}}
    result, _ = enumerate_fixture(values)
    assert len(result["options"][0]["playback_ranges"]) == 3
    assert result["options"][0]["cost"]["protect_action_span"] is True
    assert result["options"][0]["explicit_source_continuity_requested"] is False


def test_eligible_domain_hole_cannot_hide_an_omitted_full_source_unit():
    values = fixture(seconds=10, target=20)
    result, calls = enumerate_fixture(values, candidates=[values[0][0], values[0][2]])
    assert result["options"] == []
    assert calls == []
    assert result["receipt"]["coverage"]["window_outcomes"]["eligible_domain_hole"] == 1
    assert result["receipt"]["full_source_unit_ids"] == ["u000", "u001", "u002"]


def test_hole_still_allows_independent_valid_windows_on_either_side():
    values = fixture(count=5, seconds=10, target=20)
    result, _ = enumerate_fixture(values, candidates=[values[0][0], values[0][1], values[0][3], values[0][4]])
    assert [row["beat_ids"] for row in result["options"]] == [["u000", "u001"], ["u003", "u004"]]
    assert result["receipt"]["visited_windows"] == 10


def test_primary_chapters_are_alternatives_while_each_required_context_is_mandatory():
    values = fixture(seconds=10, target=20)
    units, _, chapters, plan, _ = values
    chapters[:] = [{"id": f"c{index + 1}", "beats": [unit]} for index, unit in enumerate(units)]
    plan["slots"][0].update(chapter_ids=["c1", "c3"], required_context_chapter_ids=["c2"])
    result, _ = enumerate_fixture(values)
    assert [row["beat_ids"] for row in result["options"]] == [["u001", "u002"]]
    assert result["options"][0]["chapter_ids"] == ["c2", "c3"]
    assert "u000" not in result["options"][0]["beat_ids"]  # c1 primary was optional.


def test_context_only_latest_unit_is_not_eligible_primary_witness():
    values = fixture(seconds=10, target=20)
    units, _, chapters, plan, _ = values
    chapters[:] = [{"id": "c1", "beats": units[:1]}, {"id": "c2", "beats": units[1:]}]
    plan["slots"][0]["required_context_chapter_ids"] = ["c2"]
    result, _ = enumerate_fixture(values)
    assert result["options"] == []


def test_complete_end_requires_actual_canonical_boundary_not_only_flag():
    values = fixture()
    values[1][-1]["text"] = "This thought is unfinished..."
    values[0][-1]["text"] = values[1][-1]["text"]
    result, calls = enumerate_fixture(values)
    assert result["options"] == []
    assert calls == []
    assert result["receipt"]["coverage"]["window_outcomes"]["incomplete_end_boundary"] == 3


def test_complete_punctuation_does_not_override_explicit_unfinished_unit_status():
    values = fixture()
    values[0][-1]["boundary_status"] = "unfinished_parent_tail"
    result, _ = enumerate_fixture(values)
    assert result["options"] == []


def test_short_source_uses_existing_point_nine_full_source_minimum():
    values = fixture(count=1, seconds=12, target=60)
    result, _ = enumerate_fixture(values)
    assert result["options"][0]["minimum_output_seconds"] == pytest.approx(10.8)
    assert result["options"][0]["raw_playable_seconds"] == 12


@pytest.mark.parametrize("mode", ["max", "style"])
def test_non_target_modes_require_positive_raw_playback_but_not_point_nine_minimum(mode):
    values = fixture(count=2, seconds=5, target=60)
    values[-1]["duration_mode"] = mode
    result, _ = enumerate_fixture(values)
    assert len(result["options"]) == 3
    assert all(row["minimum_output_seconds"] == 0 for row in result["options"])


@pytest.mark.parametrize("change", ["word", "word_time", "trust", "trust_presence", "instruction", "plan"])
def test_identity_changes_for_source_timing_trust_request_and_plan(change):
    values = fixture()
    before, _ = enumerate_fixture(values)
    mutated = copy.deepcopy(values)
    if change == "word":
        mutated[1][0]["words"][0]["word"] += " exact additional word"
    elif change == "word_time":
        mutated[1][0]["words"][0]["end"] -= .001
    elif change == "trust":
        mutated[1][0]["word_timing_complete"] = False
    elif change == "trust_presence":
        del mutated[1][0]["word_timing_complete"]
    elif change == "instruction":
        mutated[-1]["instruction"] += " Preserve the qualification."
    else:
        mutated[3]["slots"][0]["reason"] = "Different source-supported hypothesis."
    after, _ = enumerate_fixture(mutated)
    assert before["options"][0]["id"] != after["options"][0]["id"]
    if change not in {"instruction", "plan"}:
        assert before["receipt"]["source_fingerprint"] != after["receipt"]["source_fingerprint"]


def test_same_inputs_have_stable_ids_and_detached_results():
    values = fixture()
    first, _ = enumerate_fixture(values)
    second, _ = enumerate_fixture(copy.deepcopy(values))
    assert first == second


@pytest.mark.parametrize("bad", ["text", "time", "segment_ids", "order", "overlap", "chapter_coverage", "source_id"])
def test_forged_reordered_incomplete_or_mixed_source_is_rejected(bad):
    values = fixture()
    units, segments, chapters, _, _ = values
    candidates = copy.deepcopy(units)
    if bad == "text":
        candidates[0]["text"] = "A fabricated assertion."
    elif bad == "time":
        candidates[0]["end"] -= .001
    elif bad == "segment_ids":
        candidates[0]["segment_ids"] = ["s001"]
    elif bad == "order":
        candidates.reverse()
    elif bad == "overlap":
        segments[1]["start"] -= .001
    elif bad == "chapter_coverage":
        chapters[0]["beats"] = units[:2]
    else:
        segments[0]["source_id"], segments[1]["source_id"] = "source-a", "source-b"
    with pytest.raises(StoryPlanningError) as error:
        enumerate_fixture(values, candidates=candidates)
    assert error.value.diagnostic["applied_to_timeline"] is False


def test_candidate_bound_fails_incomplete_without_prefix_or_cost_calls():
    values = fixture(count=49, seconds=1, target=60)
    with pytest.raises(StoryPlanningError) as error:
        enumerate_fixture(values, cost=lambda ids: pytest.fail("cost must not execute"))
    assert error.value.diagnostic["reason"] == "source_passage_candidate_bound"
    assert error.value.diagnostic["search_complete_within_scope"] is False


def test_option_bound_fails_incomplete_instead_of_returning_first128():
    values = fixture(count=20, seconds=1, target=60)
    values[-1]["duration_mode"] = "max"
    with pytest.raises(StoryPlanningError) as error:
        enumerate_fixture(values)
    assert error.value.diagnostic["reason"] == "source_passage_option_bound"
    assert error.value.diagnostic["option_count"] == 129
    assert error.value.diagnostic["outcome"] == "technical_error"
    assert error.value.diagnostic["incomplete"] is True
    assert error.value.diagnostic["search_complete_within_scope"] is False


def test_work_bound_fails_incomplete(monkeypatch):
    monkeypatch.setattr(passage, "MAX_WINDOWS", 2)
    with pytest.raises(StoryPlanningError) as error:
        enumerate_fixture(fixture())
    assert error.value.diagnostic["reason"] == "source_passage_work_bound"
    assert error.value.diagnostic["visited_windows"] == 3


def test_cancellation_propagates_without_partial_result_or_cost_calls():
    visited = 0

    def cancel():
        nonlocal visited
        visited += 1
        if visited == 3:
            raise RuntimeError("cancelled by owner")

    with pytest.raises(RuntimeError, match="cancelled by owner"):
        enumerate_fixture(fixture(), cancel=cancel, cost=lambda ids: pytest.fail("no cost needed before cancel"))


@pytest.mark.parametrize("invalid_cost", [
    {}, {"approved_seconds": 60, "minimum_safe_seconds": 61, "fits_target": True},
    {"approved_seconds": 60, "minimum_safe_seconds": 60, "fits_target": False},
    {"approved_seconds": 59, "minimum_safe_seconds": 59, "fits_target": True},
])
def test_callback_cannot_silently_shorten_or_certify_invalid_cost(invalid_cost):
    with pytest.raises(StoryPlanningError):
        enumerate_fixture(fixture(), cost=lambda ids: invalid_cost)


def test_pause_fit_only_selection_stays_unsearched_even_when_callback_would_shrink_it():
    values = fixture(seconds=25, target=60)
    result, calls = enumerate_fixture(values, cost=lambda ids: pytest.fail("raw over-target windows must not be fitted"))
    assert result["options"] == []
    assert calls == []
    assert "pause-fit unsearched" in result["receipt"]["scope"]
