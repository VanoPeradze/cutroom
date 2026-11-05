"""Unintegrated source-view/geometry tests, NOT model or editor qualification."""
from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, asdict, replace
import hashlib
import json
from pathlib import Path

import pytest

from cutroom import edit_windows as ew
from cutroom.story_budget import StoryBudgetError
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


def rows():
    return [
        {"id": "a", "start": 0., "end": 15., "text": "I did not approve it.",
         "words": [{"word": "not", "start": 3., "end": 4., "probability": .9}]},
        {"id": "b", "start": 15., "end": 30., "text": "The reason is simple."},
        {"id": "c", "start": 33., "end": 48., "text": "לא אישרתי את השינוי."},
        {"id": "d", "start": 50., "end": 65., "text": "זו המסקנה ולא ההפך."},
    ]


def descriptor(**kwargs):
    return ew.SourceDescriptor("asset-test", "generation-1", "transcript-1", 1000., **kwargs)


def source(data=None, **kwargs):
    return ew.build_canonical_source(rows() if data is None else data, descriptor(**kwargs))


def brief(instruction="", **kwargs):
    return {"goal": "short", "target_duration": 60., "duration_mode": "target",
            "instruction": instruction, **kwargs}


def test_snapshot_detaches_input_and_all_nested_metadata_and_exports():
    data = rows()
    before = copy.deepcopy(data)
    original = source(data)
    assert data == before and original.transcript() == before
    data[0]["text"] = "I approve it."
    data[0]["words"][0]["word"] = "yes"
    exported = original.transcript()
    exported[0]["words"][0]["probability"] = 0
    exported.append(data[0])
    assert original.transcript() == before
    with pytest.raises(FrozenInstanceError):
        original.rows[0].text = "rewritten"
    with pytest.raises(FrozenInstanceError):
        original.descriptor.asset_version = "changed"
    with pytest.raises(FrozenInstanceError):
        original.rows = ()


@pytest.mark.parametrize("change", [
    lambda d: d[1].update(id="a"),
    lambda d: d[0].update(id=""),
    lambda d: d[0].update(text=""),
    lambda d: d[1].update(start=14.99),
    lambda d: d[0].update(start=-1),
    lambda d: d[0].update(end=0),
    lambda d: d[0].update(start=True),
    lambda d: d[0].update(end=float("inf")),
    lambda d: d[0].update(start="0"),
    lambda d: d.reverse(),
    lambda d: d[3].update(end=1001),
    lambda d: d[0]["words"][0].update(probability=float("nan")),
])
def test_invalid_canonical_input_is_rejected_without_repair_or_mutation(change):
    data = rows()
    change(data)
    before = copy.deepcopy(data)
    with pytest.raises(ew.EditWindowError):
        source(data)
    # NaN is unequal to itself; compare serializations of these invalid inputs.
    assert json.dumps(data) == json.dumps(before)


@pytest.mark.parametrize("patch", [
    {"version": 2}, {"version": True}, {"asset_version": ""},
    {"transcript_version": None}, {"asset_id": " "}, {"timebase": "frames"},
    {"asr_origin_seconds": -1}, {"asr_origin_seconds": 1000},
    {"asset_duration": float("inf")}, {"asset_duration": False},
])
def test_source_requires_explicit_supported_identity_and_timebase(patch):
    with pytest.raises(ew.EditWindowError):
        replace(descriptor(), **patch)


def test_canonical_row_budget_is_explicit_not_silent_first_n():
    with pytest.raises(ew.EditWindowError):
        source([])
    with pytest.raises(ew.EditWindowError):
        source(rows() * (ew.MAX_ROWS // 4 + 1))


@pytest.mark.parametrize("data", [
    [{"id": "x", "start": 0, "end": 1, "text": "Positive row must not collapse."}],
    [{"id": "x", "start": 0, "end": 2, "text": "A complete first row."},
     {"id": "y", "start": 3, "end": 6, "text": "A gap and duration must not change."}],
])
def test_large_origin_cannot_collapse_or_distort_rows_and_bypass_nonrepetition(data):
    desc = ew.SourceDescriptor("precision", "g", "t", 2**53 + 100, 2**53)
    with pytest.raises(ew.EditWindowError, match="precision"):
        ew.build_canonical_source(data, desc)


def test_overlapping_views_do_not_create_alternate_owners_or_rewrite_negation():
    canonical = source()
    before = canonical.transcript()
    first = ew.build_edit_window(canonical, "a", "c")
    second = ew.build_edit_window(canonical, "b", "d")
    assert set(first.row_ids) & set(second.row_ids) == {"b", "c"}
    assert canonical.transcript() == before
    assert len({row.id for row in canonical.rows}) == len(canonical.rows)
    assert [row.text for row in ew.window_rows(canonical, first)] == [r["text"] for r in before[:3]]
    assert "not" in ew.window_rows(canonical, first)[0].text
    assert "לא" in ew.window_rows(canonical, second)[1].text
    assert first.editorial_status == "unreviewed" and first.boundary_evidence == "canonical_asr_rows_only"


@pytest.mark.parametrize("texts", [
    ["We discussed building a", "A separate test failed.", "This is what we learned."],
    ["דיברנו על בניית", "ניסוי נפרד נכשל.", "זו המסקנה שלמדנו."],
])
def test_later_whole_row_entry_can_exclude_truncated_prefix_without_altering_words(texts):
    data = [{"id": str(i), "start": i * 10, "end": (i + 1) * 10, "text": text} for i, text in enumerate(texts)]
    canonical = source(data)
    full = ew.build_edit_window(canonical, "0", "2")
    alternative = ew.build_edit_window(canonical, "1", "2")
    assert full.row_ids == ("0", "1", "2") and alternative.row_ids == ("1", "2")
    assert alternative.context_before == "0" and alternative.context_after is None
    assert alternative.context_role == "reference_only_not_selected"
    assert alternative.source_start == 10
    assert [row.text for row in ew.window_rows(canonical, alternative)] == texts[1:]
    # This supports an alternative; it does not prove standalone grammar/meaning.
    assert alternative.editorial_status == "unreviewed"


def test_window_identity_is_stable_and_source_versions_invalidate_all_views_and_plans():
    canonical = source()
    view = ew.build_edit_window(canonical, "b", "d")
    plan = ew.compile_selected_spans(canonical, [view])
    same = source(copy.deepcopy(rows()))
    assert same.fingerprint == canonical.fingerprint
    assert ew.build_edit_window(same, "b", "d") == view
    ew.validate_plan(same, plan)
    variants = [replace(canonical, descriptor=replace(canonical.descriptor, **patch)) for patch in [
        {"asset_id": "another"}, {"asset_version": "generation-2"}, {"transcript_version": "transcript-2"},
        {"asr_origin_seconds": 120}, {"asset_duration": 2000},
    ]]
    altered = rows()
    altered[0]["words"][0]["probability"] = .8
    variants.append(source(altered))
    for changed in variants:
        assert ew.build_edit_window(changed, "b", "d").id != view.id
        with pytest.raises(ew.EditWindowError, match="Stale"):
            ew.validate_window(changed, view)
        with pytest.raises(ew.EditWindowError, match="Stale"):
            ew.validate_plan(changed, plan)


@pytest.mark.parametrize("patch", [
    {"row_ids": ("a", "c")}, {"source_start": 2}, {"asr_start": 2},
    {"context_after": "invented"}, {"boundary_policy": "word-cut"},
    {"editorial_status": "approved"}, {"version": 9}, {"gaps": ()},
])
def test_tampered_window_cannot_cross_adapter_boundary(patch):
    canonical = source()
    window = ew.build_edit_window(canonical, "a", "c")
    with pytest.raises(ew.EditWindowError):
        ew.compile_selected_spans(canonical, [replace(window, **patch)])


@pytest.mark.parametrize("field,value", [("asr_start", False), ("source_start", False),
                                         ("asr_end", True), ("source_end", True)])
def test_boolean_equivalent_tampering_is_not_equal_canonical_geometry(field, value):
    canonical = source([{"id": "only", "start": 0, "end": 1, "text": "One second."}])
    view = ew.build_edit_window(canonical, "only", "only")
    with pytest.raises(ew.EditWindowError, match="finite number"):
        ew.compile_selected_spans(canonical, [replace(view, **{field: value})])


@pytest.mark.parametrize("patch", [{"start": False}, {"source_start": False}, {"end": True}, {"source_end": True}])
def test_boolean_equivalent_clip_tampering_fails_plan_revalidation(patch):
    canonical = source([{"id": "only", "start": 0, "end": 1, "text": "One second."}])
    plan = ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "only", "only")])
    with pytest.raises(ew.EditWindowError, match="finite number"):
        ew.validate_plan(canonical, replace(plan, clips=(replace(plan.clips[0], **patch),)))
    with pytest.raises(ew.EditWindowError, match="finite number"):
        ew.validate_plan(canonical, replace(plan, duration=True))


def test_boolean_equivalent_gap_tampering_fails_window_validation():
    canonical = source([{"id": "x", "start": 0, "end": 1, "text": "Before gap."},
                        {"id": "y", "start": 2, "end": 3, "text": "After gap."}])
    view = ew.build_edit_window(canonical, "x", "y")
    with pytest.raises(ew.EditWindowError, match="finite number"):
        ew.validate_window(canonical, replace(view, gaps=(replace(view.gaps[0], start=True),)))


@pytest.mark.parametrize("first,last", [("a", "unknown"), ("d", "a"), ("a:3.5", "c")])
def test_only_whole_ordered_canonical_boundary_ids_allowed(first, last):
    with pytest.raises(ew.EditWindowError):
        ew.build_edit_window(source(), first, last)


def test_internal_gaps_retained_not_silently_removed_or_classified_as_silence():
    canonical = source(asr_origin_seconds=120.)
    window = ew.build_edit_window(canonical, "a", "c")
    assert (window.asr_start, window.asr_end) == (0, 48)
    assert (window.source_start, window.source_end) == (120, 168)
    assert asdict(window.gaps[0]) == {"left_id": "b", "right_id": "c", "start": 150., "end": 153.,
                                     "status": "untranscribed_unverified"}
    plan = ew.compile_selected_spans(canonical, [window])
    assert plan.duration == 48 and plan.source_at(31) == 151
    assert plan.timeline_at(151) == 31  # The untranscribed source time is retained.


def test_clip_mapping_preserves_original_offsets_and_omitted_intervals():
    canonical = source(asr_origin_seconds=120.)
    views = [ew.build_edit_window(canonical, "a", "b"), ew.build_edit_window(canonical, "d", "d")]
    plan = ew.compile_selected_spans(canonical, views)
    assert plan.duration == plan.clips[-1].end
    assert [(c.start, c.end, c.source_start, c.source_end) for c in plan.clips] == [(0, 30, 120, 150), (30, 45, 170, 185)]
    assert plan.source_at(0) == 120 and plan.source_at(30) == 170
    assert plan.source_at(45) is None and plan.source_at(-1) is None
    assert plan.timeline_at(149) == 29 and plan.timeline_at(150) is None and plan.timeline_at(170) == 30
    for value in (.1, 15, 29.99, 30, 44.99):
        assert plan.timeline_at(plan.source_at(value)) == pytest.approx(value)
    detached = plan.clip_map()
    detached[0]["source_start"] = 0
    assert plan.clip_map()[0]["source_start"] == 120
    assert len({c.id for c in plan.clips}) == 2
    assert plan.validation_scope == "source_geometry_and_numeric_constraints_only"
    assert plan.editorial_status == "not_assessed"
    ew.validate_plan(canonical, plan)
    with pytest.raises(ew.EditWindowError):
        ew.validate_plan(canonical, replace(plan, clips=(replace(plan.clips[0], source_start=0), *plan.clips[1:])))


def test_detached_clip_geometry_is_accepted_by_existing_native_validator_without_saving():
    from cutroom.source_tracks import _validated
    canonical = source(asr_origin_seconds=120)
    plan = ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "b"),
                                               ew.build_edit_window(canonical, "d", "d")])
    project = {"sources": {"A": {"duration": canonical.descriptor.asset_duration}}, "manual": {}}
    before = copy.deepcopy(project)
    geometry = plan.clip_map()
    validated = _validated(project, "A", geometry)
    assert [(v["start"], v["end"], v["source_start"]) for v in validated] == [(0, 30, 120), (30, 45, 170)]
    assert [v["id"] for v in validated] == [v["id"] for v in geometry]
    assert project == before  # No project, timeline, draft or media IO.


@pytest.mark.parametrize("pairs", [[("a", "b"), ("a", "b")], [("a", "c"), ("b", "d")],
                                   [("d", "d"), ("a", "b")]])
def test_selection_rejects_repeat_overlap_or_reverse_without_silent_sort(pairs):
    canonical = source()
    views = [ew.build_edit_window(canonical, *pair) for pair in pairs]
    with pytest.raises(ew.EditWindowError, match="repeats, overlaps or reorders"):
        ew.compile_selected_spans(canonical, views)


@pytest.mark.parametrize("instruction", ["Make one video. Aim for 45–60 seconds.", "צור סרטון אחד. כוון ל־45–60 שניות."])
def test_one_output_can_have_cuts_with_explicit_duration_range(instruction):
    canonical = source()
    views = [ew.build_edit_window(canonical, "a", "b"), ew.build_edit_window(canonical, "d", "d")]
    request = brief(instruction)
    before = copy.deepcopy(request)
    plan = ew.compile_selected_spans(canonical, views, brief=request)
    assert plan.duration == 45 and len(plan.clips) == 2 and request == before
    assert json.loads(plan.numeric_bounds_json)["origin"] == "explicit_user_range"
    request["instruction"] = "changed"
    assert json.loads(plan.request_json) == before
    assert plan.editorial_status == "not_assessed"


@pytest.mark.parametrize("instruction", ["Choose one continuous source passage.", "שמור על קטע המקור ללא חיתוכים."])
def test_explicit_no_cuts_distinguishes_omission_from_touching_intervals_and_internal_gaps(instruction):
    canonical = source()
    request = brief(instruction, duration_mode="max", target_duration=100)
    with pytest.raises(ew.EditWindowError, match="no-cuts"):
        ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "a"),
                                              ew.build_edit_window(canonical, "c", "c")], brief=request)
    touching = ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "a"),
                                                     ew.build_edit_window(canonical, "b", "b")], brief=request)
    assert touching.duration == 30
    whole = ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "d")], brief=request)
    assert whole.duration == 65  # Both untranscribed gaps retained, not pause-cut.


@pytest.mark.parametrize("instruction", ["Make exactly 60 seconds.", "צור סרטון של 60 שניות."])
def test_exact_target_cannot_be_claimed_satisfied_by_shorter_geometry(instruction):
    canonical = source()
    with pytest.raises(ew.EditWindowError, match="numeric"):
        ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "b")], brief=brief(instruction))
    exact = source([{"id": "only", "start": 0, "end": 60, "text": "Exact geometry only."}])
    plan = ew.compile_selected_spans(exact, [ew.build_edit_window(exact, "only", "only")], brief=brief(instruction))
    assert plan.duration == 60 and plan.editorial_status == "not_assessed"


@pytest.mark.parametrize("instruction", [
    "Choose one continuous source passage. Related cuts are allowed.",
    "בחר קטע מקור אחד רציף. אפשר לחתוך בין אמירות קשורות.",
])
def test_conflicting_hard_instructions_still_block(instruction):
    canonical = source()
    with pytest.raises(StoryBudgetError):
        ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "d")], brief=brief(instruction))


def test_style_cannot_erase_range_or_impose_continuity():
    canonical = source()
    request = brief("Make one video. Aim for 45–60 seconds.",
                    style_profile={"selection_policy": {"continuous_source": True, "max_moments": 1}})
    plan = ew.compile_selected_spans(canonical, [ew.build_edit_window(canonical, "a", "b"),
                                               ew.build_edit_window(canonical, "d", "d")], brief=request)
    assert plan.duration == 45


def test_bounded_pages_resume_exactly_without_duplicate_windows_or_false_coverage():
    canonical = source()
    full = ew.enumerate_edit_windows(canonical, maximum_seconds=65)
    assert len(full.windows) == 10 and full.end_reached
    cursor, collected, inspected = None, [], 0
    while True:
        page = ew.enumerate_edit_windows(canonical, maximum_seconds=65, max_windows=2, max_pairs=3, cursor=cursor)
        assert page.inspected_pairs <= 3 and len(page.windows) <= 2
        collected.extend(page.windows)
        inspected += page.inspected_pairs
        if page.end_reached:
            assert page.next_cursor is None
            break
        assert page.next_cursor is not None
        cursor = page.next_cursor
    assert collected == list(full.windows) and len({w.id for w in collected}) == 10
    assert inspected == full.inspected_pairs
    assert any(a.row_ids != b.row_ids and set(a.row_ids) & set(b.row_ids) for a in collected for b in collected)


def test_duration_pruning_and_empty_pages_keep_explicit_resumable_search_state():
    canonical = source()
    page = ew.enumerate_edit_windows(canonical, minimum_seconds=60, maximum_seconds=65, max_pairs=1)
    assert page.windows == () and not page.end_reached and page.next_cursor
    candidates = []
    while not page.end_reached:
        page = ew.enumerate_edit_windows(canonical, minimum_seconds=60, maximum_seconds=65, max_pairs=1, cursor=page.next_cursor)
        candidates.extend(page.windows)
    assert [v.row_ids for v in candidates] == [("a", "b", "c", "d")]
    empty = ew.enumerate_edit_windows(canonical, maximum_seconds=1)
    assert empty.end_reached and not empty.windows and empty.inspected_pairs == 4


def test_cursor_rejects_stale_source_filters_and_invalid_positions():
    canonical = source()
    cursor = ew.enumerate_edit_windows(canonical, max_pairs=1).next_cursor
    for changed, settings in [(source(asr_origin_seconds=1), {}), (canonical, {"minimum_seconds": 20}),
                               (canonical, {"maximum_seconds": 100})]:
        with pytest.raises(ew.EditWindowError, match="cursor"):
            ew.enumerate_edit_windows(changed, cursor=cursor, **settings)
    for changed in [replace(cursor, first=-1), replace(cursor, last=999), replace(cursor, first=True)]:
        with pytest.raises(ew.EditWindowError):
            ew.enumerate_edit_windows(canonical, cursor=changed)


@pytest.mark.parametrize("settings", [{"max_pairs": 10001}, {"max_windows": 513}, {"max_windows": True},
                                      {"minimum_seconds": 20, "maximum_seconds": 10}, {"maximum_seconds": 0}])
def test_enumeration_rejects_unbounded_or_invalid_work_request(settings):
    with pytest.raises(ew.EditWindowError):
        ew.enumerate_edit_windows(source(), **settings)


def test_cancellation_has_no_mutation_and_same_cursor_can_resume():
    canonical = source()
    cursor = ew.enumerate_edit_windows(canonical, max_pairs=1).next_cursor
    before = canonical.transcript()
    calls = []
    def cancel():
        calls.append(1)
        if len(calls) == 3:
            raise InterruptedError("cancelled")
    with pytest.raises(InterruptedError):
        ew.enumerate_edit_windows(canonical, cursor=cursor, cancel_check=cancel)
    assert canonical.transcript() == before
    assert ew.enumerate_edit_windows(canonical, cursor=cursor) == ew.enumerate_edit_windows(source(), cursor=cursor)


def test_large_canonical_source_has_bounded_enumeration_work():
    data = [{"id": f"r{i}", "start": i * 2, "end": i * 2 + 1, "text": "לא נמחק. Do not delete."}
            for i in range(2000)]
    canonical = ew.build_canonical_source(data, ew.SourceDescriptor("long", "g", "t", 4000))
    page = ew.enumerate_edit_windows(canonical, max_windows=4, max_pairs=5)
    assert len(page.windows) == 4 and page.inspected_pairs == 4 and not page.end_reached
    assert len(canonical.rows) == 2000 and canonical.rows[-1].id == "r1999"


def test_portable_composition_is_representable_not_retrieved_or_approved():
    raw = source_bytes()
    data = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == source_sha256()
    before = copy.deepcopy(data)
    desc = ew.SourceDescriptor("supplied-english-diagnostic", "saved-diagnostic-receipt-not-media-hash",
                               hashlib.sha256(raw).hexdigest(), 3505.002667, 120)
    canonical = ew.build_canonical_source(data["segments"], desc)
    views = [ew.build_edit_window(canonical, first, last) for first, last in
             [("s0004", "s0006"), ("s0012", "s0016"), ("s0025", "s0030")]]
    plan = ew.compile_selected_spans(canonical, views, brief=brief("Make one video. Aim for 45–60 seconds."))
    assert plan.duration == pytest.approx(49.25)
    for clip, expected in zip(plan.clips, [(139.42, 155.45), (180.51, 193.44), (216., 236.29)]):
        assert (clip.source_start, clip.source_end) == pytest.approx(expected)
    assert [r.id for v in views for r in ew.window_rows(canonical, v)] == [
        "s0004", "s0005", "s0006", "s0012", "s0013", "s0014", "s0015", "s0016",
        "s0025", "s0026", "s0027", "s0028", "s0029", "s0030"]
    assert canonical.transcript() == data["segments"]
    assert plan.editorial_status == "not_assessed" and all(v.editorial_status == "unreviewed" for v in views)
    alternative = ew.build_edit_window(canonical, "s0010", "s0011")
    assert alternative.asr_start == 48 and alternative.asr_end == 60.01
    assert alternative.context_before == "s0009"  # No automatic context deletion approval.
    ew.validate_plan(canonical, plan)


def test_no_existing_production_caller_or_approval_flags():
    assert ew.ENABLED_BY_DEFAULT is False
    root = Path(ew.__file__).parent
    for path in root.glob("*.py"):
        # Later milestones explicitly permit the bridge/retriever to reference these types.
        # Separate planner-entry tests prove default-off and no draft/apply.
        if path.name in {"edit_windows.py", "window_evidence.py", "window_retrieval.py", "window_composition.py", "window_search.py", "window_semantics.py", "director.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {"cutroom.edit_windows", "edit_windows"}
                assert not any(alias.name == "edit_windows" for alias in node.names)
            if isinstance(node, ast.Import):
                assert not any(alias.name == "cutroom.edit_windows" for alias in node.names)
    plan = ew.compile_selected_spans(source(), [ew.build_edit_window(source(), "a", "b")])
    for item in [asdict(plan), *plan.clip_map()]:
        assert not set(item) & {"draft", "applied", "applied_to_timeline", "semantic_mapping_verified", "semantic_verified"}
