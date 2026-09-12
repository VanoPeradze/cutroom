from __future__ import annotations

import json
import random

import pytest

from cutroom import utils
from cutroom.utils import atomic_write_json, invert_ranges, merge_ranges, range_duration

try:
    from hypothesis import given, strategies as st
except ImportError:  # The release suite still runs a deterministic property sweep.
    given = None
    st = None


def _assert_merge_invariant(raw):
    ranges = [(min(a, b), max(a, b)) for a, b in raw if abs(a - b) > 1e-4]
    merged = merge_ranges(ranges)
    assert all(item["end"] > item["start"] >= 0 for item in merged)
    assert all(merged[index]["end"] + 0.079 < merged[index + 1]["start"] for index in range(len(merged) - 1))


def _assert_duration_invariant(duration, raw):
    cuts = [(min(a, b, duration), min(max(a, b), duration)) for a, b in raw]
    merged = merge_ranges(cuts)
    keep = invert_ranges(merged, duration, min_keep=0)
    assert range_duration(keep) <= duration + 0.01
    assert range_duration(merged) <= duration + 0.01


if given is not None:
    @given(st.lists(st.tuples(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
    ), max_size=40))
    def test_merge_ranges_is_sorted_and_non_overlapping(raw):
        _assert_merge_invariant(raw)


    @given(
        st.floats(min_value=1, max_value=300, allow_nan=False, allow_infinity=False),
        st.lists(st.tuples(
            st.floats(min_value=0, max_value=300, allow_nan=False, allow_infinity=False),
            st.floats(min_value=0, max_value=300, allow_nan=False, allow_infinity=False),
        ), max_size=20),
    )
    def test_keep_plus_cut_never_exceeds_duration(duration, raw):
        _assert_duration_invariant(duration, raw)
else:
    def test_merge_ranges_is_sorted_and_non_overlapping():
        rng = random.Random(20260825)
        for _ in range(10_000):
            raw = [(rng.uniform(0, 100), rng.uniform(0, 100)) for _ in range(rng.randrange(0, 41))]
            _assert_merge_invariant(raw)


    def test_keep_plus_cut_never_exceeds_duration():
        rng = random.Random(50260825)
        for _ in range(10_000):
            duration = rng.uniform(1, 300)
            raw = [(rng.uniform(0, 300), rng.uniform(0, 300)) for _ in range(rng.randrange(0, 21))]
            _assert_duration_invariant(duration, raw)


def test_invert_known_ranges():
    assert invert_ranges([{"start": 2, "end": 4}, {"start": 6, "end": 8}], 10) == [
        {"start": 0.0, "end": 2.0},
        {"start": 4.0, "end": 6.0},
        {"start": 8.0, "end": 10.0},
    ]


def test_negative_range_that_clamps_to_zero_is_removed():
    assert merge_ranges([(-5, -1), (-3, 2)]) == [{"start": 0.0, "end": 2.0}]


def test_invert_ranges_never_returns_zero_length_edges():
    assert invert_ranges([{"start": 0, "end": 10}], 10, min_keep=0) == []
    assert invert_ranges([{"start": 0, "end": 4}], 10, min_keep=0) == [
        {"start": 4.0, "end": 10.0},
    ]


def test_sub_millisecond_ranges_do_not_round_to_zero_length():
    assert merge_ranges([(0.0001, 0.0004)]) == []


def test_atomic_json_write_retries_transient_windows_permission_error(monkeypatch, tmp_path):
    target = tmp_path / "progress.json"
    real_replace = utils.os.replace
    attempts = 0

    def temporarily_locked(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "destination is temporarily locked")
        return real_replace(source, destination)

    monkeypatch.setattr(utils.os, "replace", temporarily_locked)
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    atomic_write_json(target, {"progress": 0.42, "message": "working"})

    assert attempts == 3
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "progress": 0.42,
        "message": "working",
    }
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_json_write_still_reports_persistent_permission_failure(monkeypatch, tmp_path):
    target = tmp_path / "project.json"
    monkeypatch.setattr(
        utils.os,
        "replace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError(5, "denied")),
    )
    monkeypatch.setattr(utils.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError):
        atomic_write_json(target, {"important": True})

    assert not target.exists()
    assert list(tmp_path.glob("*.tmp")) == []
