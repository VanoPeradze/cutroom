from __future__ import annotations

import copy

import pytest

from cutroom.story_budget import story_duration_cost
from cutroom.story_constraints import story_constraint_feasibility


def unit(identifier, start, end, spans=None):
    spans = spans or [(start, end)]
    words = [{"word": f"word{i}", "start": left, "end": right}
             for i, (left, right) in enumerate(spans)]
    segment = {"id": "s" + identifier, "start": start, "end": end,
               "text": " ".join(word["word"] for word in words) + ".", "words": words}
    beat = {"id": identifier, "start": start, "end": end,
            "text": segment["text"], "segment_ids": [segment["id"]]}
    return beat, segment


def diagnose(units, chapter_beats, slots, *, selected=None, sticky=(), rejected=(), **kwargs):
    beats, segments = map(list, zip(*units))
    chapters = [{"id": identifier, "beats": [beat for beat in beats if beat["id"] in identifiers]}
                for identifier, identifiers in chapter_beats.items()]
    return story_constraint_feasibility(
        beats, segments, chapters, {"slots": slots},
        selected_beat_ids=selected if selected is not None else [beat["id"] for beat in beats],
        sticky_beat_ids=sticky, rejected_beat_ids=rejected, target=kwargs.pop("target", 20), **kwargs,
    )


def slot(chapters, context=()):
    return {"chapter_ids": chapters, "required_context_chapter_ids": list(context)}


def test_english_shaped_current_selection_fits_despite_unverified_semantics():
    # Actual numerical boundaries; all text/word labels are synthetic.
    units = [unit("b2", 8.41, 19.64, [
        (8.41, 8.77), (9.24, 10.48), (10.78, 12.5), (12.68, 13.84),
        (14.16, 16.46), (16.74, 17.44), (18.24, 19.64),
    ]), unit("b3", 20.34, 29.5, [
        (20.34, 21.8), (22.26, 23.18), (23.67, 24.45), (25.48, 27.14), (27.36, 29.5),
    ])]
    result = diagnose(units, {"c": ["b2", "b3"]}, [slot(["c"], ["c"]) for _ in range(4)])
    cost = result["current_required_selection_cost"]
    assert cost["approved_seconds"] == 20.39
    assert cost["minimum_safe_seconds"] == 17.2
    assert cost["fits_target"] is True
    assert result["status"] == "duration_fit_but_semantics_unverified"
    assert result["optimistic_lower_bound_seconds"] < 20
    assert result["exhaustive"] is True


def test_unique_primary_and_sticky_source_prove_a_2108_second_lower_bound():
    units = [unit("primary", 0, 12), unit("context", 15, 24.08)]
    result = diagnose(units, {"c": ["primary"]}, [slot(["c"])], sticky=["context"])
    assert result["status"] == "target_infeasible"
    assert result["optimistic_lower_bound_seconds"] == 21.08
    assert result["current_required_selection_minimum_seconds"] == 21.08
    assert result["scope"] == "allowed_source_constraints"


def test_source_union_does_not_double_count_shared_units_or_overlapping_speech():
    # Duplicate source membership and repeated roles are not repeated footage.
    units = [unit("shared", 0, 12)]
    result = diagnose(units, {"a": ["shared"], "b": ["shared"]},
                      [slot(["a"], ["a", "b"]) for _ in range(4)], sticky=["shared"])
    assert result["status"] == "duration_fit_but_semantics_unverified"
    assert result["optimistic_lower_bound_seconds"] == 12
    assert result["required_group_count"] == 12


def test_required_context_is_and_but_primary_chapters_are_or():
    units = [unit("long", 0, 25), unit("short", 30, 33), unit("context", 35, 39)]
    result = diagnose(units, {"a": ["long"], "b": ["short"], "c": ["context"]},
                      [slot(["a", "b"], ["b", "c"])], selected=["short", "context"])
    assert result["status"] == "duration_fit_but_semantics_unverified"
    assert result["optimistic_lower_bound_seconds"] == 7


def test_multigroup_search_can_reuse_an_alternative_without_greedy_overcount():
    units = [unit("shared", 0, 7), unit("left", 10, 14), unit("right", 20, 24)]
    result = diagnose(units, {"a": ["shared", "left"], "b": ["shared", "right"]},
                      [slot(["a"]), slot(["b"])], selected=["shared"], target=7)
    assert result["optimistic_lower_bound_seconds"] == 7
    assert result["exhaustive"] is True
    assert result["status"] == "duration_fit_but_semantics_unverified"


@pytest.mark.parametrize("duplicate", ["candidate", "segment"])
def test_ambiguous_source_ids_cannot_establish_an_infeasibility_proof(duplicate):
    short, first_segment = unit("short", 0, 1)
    long, second_segment = unit("long", 5, 30)
    if duplicate == "candidate":
        short["id"] = long["id"] = "same"
    else:
        first_segment["id"] = second_segment["id"] = "same_segment"
        short["segment_ids"] = long["segment_ids"] = ["same_segment"]
    result = story_constraint_feasibility(
        [short, long], [first_segment, second_segment], [{"id": "c", "beats": [short, long]}],
        {"slots": [slot(["c"])]}, selected_beat_ids=[long["id"]],
        sticky_beat_ids=[], rejected_beat_ids=[], target=20,
    )
    assert result["status"] == "unverified"
    assert result["optimistic_lower_bound_seconds"] == 0
    assert result["exhaustive"] is False
    assert result["ambiguous_source_id_count"] == 1


@pytest.mark.parametrize("restriction", ["rejected", "ineligible", "incomplete", "missing_sticky"])
def test_unavailable_required_source_is_not_solved_by_a_longer_target(restriction):
    units = [unit("required", 0, 3)]
    kwargs = {}
    if restriction == "rejected":
        kwargs["rejected"] = ["required"]
    elif restriction == "ineligible":
        kwargs["eligible_beat_ids"] = []
    elif restriction == "incomplete":
        units[0][0]["text"] = "A clipped sentence"
    else:
        kwargs["sticky"] = ["absent"]
    result = diagnose(units, {"c": ["required"]}, [slot(["c"])], target=1000, **kwargs)
    assert result["status"] == "required_source_missing"
    assert result["missing_group_count"] > 0


def test_search_exhaustion_uses_mandatory_bound_not_best_visited_solution(monkeypatch):
    import cutroom.story_constraints as constraints
    monkeypatch.setattr(constraints, "MAX_CONSTRAINT_SEARCH_STATES", 2)
    units = [unit("a_long", 0, 25), unit("z_short", 30, 31)]
    result = diagnose(units, {"c": ["a_long", "z_short"]}, [slot(["c"])], selected=["a_long"])
    assert result["exhaustive"] is False
    assert result["searched_states"] == 2
    assert result["optimistic_lower_bound_seconds"] == 0
    assert result["status"] == "unverified"


def test_nonexhaustive_mandatory_source_alone_can_still_prove_infeasibility(monkeypatch):
    import cutroom.story_constraints as constraints
    monkeypatch.setattr(constraints, "MAX_CONSTRAINT_SEARCH_STATES", 1)
    units = [unit("mandatory", 0, 21), unit("a", 30, 31), unit("b", 35, 36)]
    result = diagnose(units, {"c": ["a", "b"]}, [slot(["c"])], sticky=["mandatory"])
    assert result["exhaustive"] is False
    assert result["optimistic_lower_bound_seconds"] == 21
    assert result["status"] == "target_infeasible"


def test_protected_speech_lower_bound_omits_handles_and_action_protects_full_span():
    units = [unit("required", 0, 25, [(0, 1), (24, 25)])]
    normal = diagnose(units, {"c": ["required"]}, [slot(["c"])])
    action = diagnose(units, {"c": ["required"]}, [slot(["c"])], protect_action_span=True)
    assert normal["optimistic_lower_bound_seconds"] == 2
    assert normal["current_required_selection_minimum_seconds"] == 2.12
    assert normal["status"] == "duration_fit_but_semantics_unverified"
    assert action["optimistic_lower_bound_seconds"] == 25
    assert action["status"] == "target_infeasible"


def test_incomplete_word_timing_protects_the_whole_source_segment():
    units = [unit("required", 0, 21, [(0, 1), (20, 21)])]
    units[0][1]["words"].pop()
    result = diagnose(units, {"c": ["required"]}, [slot(["c"])])
    assert result["optimistic_lower_bound_seconds"] == 21
    assert result["status"] == "target_infeasible"


def test_overlapping_complete_units_use_union_not_standalone_minimum_sum():
    _, a = unit("a", 0, 6, [(0, 1), (5, 6)])
    _, b = unit("b", 6, 12, [(6, 7), (11, 12)])
    beat_a = {"id": "a", "start": 0, "end": 12, "segment_ids": [a["id"], b["id"]],
              "text": a["text"] + " " + b["text"]}
    beat_b = {"id": "b", "start": 6, "end": 12, "segment_ids": [b["id"]], "text": b["text"]}
    result = story_constraint_feasibility(
        [beat_a, beat_b], [a, b], [{"id": "c", "beats": [beat_a, beat_b]}],
        {"slots": [slot(["c"])]}, selected_beat_ids=["a", "b"],
        sticky_beat_ids=["a", "b"], rejected_beat_ids=[], target=5,
    )
    assert result["optimistic_lower_bound_seconds"] == 4
    assert result["current_required_selection_cost"] == story_duration_cost(
        [{"start": 0, "end": 12}, {"start": 6, "end": 12}], [a, b], 12, target=5)
    assert result["status"] == "duration_fit_but_semantics_unverified"


@pytest.mark.parametrize("seconds,expected", [(20.05, "duration_fit_but_semantics_unverified"),
                                             (20.051, "target_infeasible")])
def test_duration_proof_respects_shared_50ms_tolerance(seconds, expected):
    result = diagnose([unit("required", 0, seconds)], {"c": ["required"]}, [slot(["c"])])
    assert result["status"] == expected


def test_diagnostic_is_numeric_and_does_not_mutate_source():
    # Build the fixture without retaining or returning transcript content.
    beat, segment = unit("private", 0, 3)
    arguments = ([beat], [segment], [{"id": "chapter", "beats": [beat]}], {"slots": [slot(["chapter"])]})
    before = copy.deepcopy(arguments)
    result = story_constraint_feasibility(*arguments, selected_beat_ids=["private"],
                                         sticky_beat_ids=[], rejected_beat_ids=[], target=20)
    assert arguments == before
    assert "word" not in str(result)
    assert "private" not in str(result)
