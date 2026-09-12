from __future__ import annotations

from typing import Any

from cutroom.director import _select_audio_highlight_ranges
from cutroom.utils import range_duration


def _profile(
    duration: float,
    events: list[tuple[float, float, float, float]],
    *,
    step: float = 2.0,
) -> dict[str, Any]:
    """Build a compact waveform with explicit evidence-backed highlight events."""

    waveform: list[dict[str, float]] = []
    cursor = 0.0
    while cursor < duration:
        end = min(duration, cursor + step)
        rms, peak = -56.0, -42.0
        for event_start, event_end, event_rms, event_peak in events:
            if end > event_start and cursor < event_end:
                rms = max(rms, event_rms)
                peak = max(peak, event_peak)
        waveform.append({
            "start": round(cursor, 3),
            "end": round(end, 3),
            "rms_dbfs": rms,
            "peak_dbfs": peak,
        })
        cursor = end
    return {"waveform": waveform}


def _signature(ranges: list[dict[str, float]]) -> tuple[tuple[float, float], ...]:
    return tuple((round(float(item["start"]), 3), round(float(item["end"]), 3)) for item in ranges)


def _assert_valid_ranges(ranges: list[dict[str, float]], duration: float) -> None:
    assert ranges
    assert ranges == sorted(ranges, key=lambda item: float(item["start"]))
    for index, item in enumerate(ranges):
        start, end = float(item["start"]), float(item["end"])
        assert 0.0 <= start < end <= duration
        if index:
            assert float(ranges[index - 1]["end"]) <= start


def test_same_selection_seed_is_exactly_deterministic() -> None:
    duration = 720.0
    events = []
    for bucket in range(6):
        bucket_start = bucket * 120.0
        # Two equally strong choices per bucket exercise seeded tie-breaking.
        events.extend([
            (bucket_start + 26.0, bucket_start + 44.0, -8.0, -2.0),
            (bucket_start + 76.0, bucket_start + 94.0, -8.0, -2.0),
        ])
    profile = _profile(duration, events)

    first = _select_audio_highlight_ranges(
        profile, duration, 60.0, [], selection_seed=1201,
    )
    repeated = _select_audio_highlight_ranges(
        profile, duration, 60.0, [], selection_seed=1201,
    )

    assert _signature(first) == _signature(repeated)
    _assert_valid_ranges(first, duration)
    assert 54.0 <= range_duration(first) <= 60.05


def test_different_selection_seeds_choose_different_near_ties() -> None:
    duration = 720.0
    events = []
    for bucket in range(6):
        bucket_start = bucket * 120.0
        events.extend([
            (bucket_start + 26.0, bucket_start + 44.0, -8.0, -2.0),
            (bucket_start + 76.0, bucket_start + 94.0, -8.0, -2.0),
        ])
    profile = _profile(duration, events)

    first = _select_audio_highlight_ranges(
        profile, duration, 60.0, [], selection_seed=1201,
    )
    alternate = _select_audio_highlight_ranges(
        profile, duration, 60.0, [], selection_seed=1202,
    )

    assert _signature(first) != _signature(alternate)
    assert 54.0 <= range_duration(alternate) <= 60.05
    _assert_valid_ranges(alternate, duration)


def test_seeded_selection_preserves_quality_and_coverage_despite_one_hotspot() -> None:
    duration = 900.0
    target = 90.0
    distributed = [
        (35.0, 53.0, -12.0, -4.0),
        (135.0, 153.0, -12.0, -4.0),
        (235.0, 253.0, -12.0, -4.0),
        (335.0, 353.0, -12.0, -4.0),
        (535.0, 553.0, -12.0, -4.0),
        (635.0, 653.0, -12.0, -4.0),
        (735.0, 753.0, -12.0, -4.0),
        (835.0, 853.0, -12.0, -4.0),
    ]
    hotspot = (390.0, 470.0, -2.0, -0.2)
    evidence = [*distributed, hotspot]
    ranges = _select_audio_highlight_ranges(
        _profile(duration, evidence), duration, target, [], selection_seed=4103,
    )

    _assert_valid_ranges(ranges, duration)
    assert target * 0.90 <= range_duration(ranges) <= target + 0.05

    buckets = [
        min(8, int((((float(item["start"]) + float(item["end"])) / 2.0) / duration) * 9))
        for item in ranges
    ]
    assert len(set(buckets)) >= 6
    assert max(buckets.count(bucket) for bucket in set(buckets)) <= 2
    assert any(bucket <= 1 for bucket in buckets)
    assert any(bucket >= 7 for bucket in buckets)

    # Variation may choose among strong moments, but it may not manufacture a
    # highlight from the quiet baseline merely to make two seeds look different.
    for item in ranges:
        start, end = float(item["start"]), float(item["end"])
        assert any(end > event_start and start < event_end for event_start, event_end, *_ in evidence)


def test_seeded_selection_uses_variable_event_lengths_and_honors_target() -> None:
    duration = 600.0
    target = 72.0
    shapes = [
        (40.0, 46.0),
        (105.0, 115.0),
        (168.0, 183.0),
        (232.0, 252.0),
        (305.0, 313.0),
        (365.0, 378.0),
        (430.0, 448.0),
        (512.0, 524.0),
    ]
    events = [(start, end, -9.0, -2.0) for start, end in shapes]
    scene_points = sorted(point for start, end in shapes for point in (start, end))

    ranges = _select_audio_highlight_ranges(
        _profile(duration, events, step=1.0),
        duration,
        target,
        scene_points,
        selection_seed=9919,
    )

    _assert_valid_ranges(ranges, duration)
    assert target * 0.90 <= range_duration(ranges) <= target + 0.05
    lengths = [round(float(item["end"]) - float(item["start"]), 1) for item in ranges]
    assert len(set(lengths)) >= 3, f"robotic fixed cadence: {lengths}"
    assert max(lengths) - min(lengths) >= 4.0
    assert all(length >= 3.0 for length in lengths)


def test_new_variation_advances_only_the_draft_variant(monkeypatch) -> None:
    from cutroom import director

    class Context:
        def checkpoint(self) -> None:
            return None

    class Store:
        project = {
            "sources": {"A": {"duration": 600.0}, "B": None},
            "settings": {"target_duration": 60, "pace": "balanced"},
            "draft": {"selection_variant": 4},
            "manual": {},
        }

        def load(self, _project_id: str) -> dict[str, Any]:
            return self.project

    captured: dict[str, Any] = {}

    def fake_analyze(
        _context: Any,
        _project_id: str,
        _store: Any,
        _settings: Any,
        patch: dict[str, Any],
        *,
        selection_variant: int,
    ) -> dict[str, bool]:
        captured["patch"] = patch
        captured["variant"] = selection_variant
        return {"ok": True}

    monkeypatch.setattr(director, "analyze_project", fake_analyze)

    result = director.refine_project(Context(), "project", Store(), object(), "new_variation")

    assert result == {"ok": True}
    assert captured == {"patch": {}, "variant": 5}
    assert Store.project["settings"] == {"target_duration": 60, "pace": "balanced"}


def test_audio_highlight_cadence_responds_to_pace() -> None:
    duration = 900.0
    events = [
        (index * 70.0 + 20.0, index * 70.0 + 38.0, -8.0, -2.0)
        for index in range(12)
    ]
    profile = _profile(duration, events)

    gentle = _select_audio_highlight_ranges(
        profile, duration, 90.0, [], selection_seed=7, pace="gentle",
    )
    balanced = _select_audio_highlight_ranges(
        profile, duration, 90.0, [], selection_seed=7, pace="balanced",
    )
    dynamic = _select_audio_highlight_ranges(
        profile, duration, 90.0, [], selection_seed=7, pace="dynamic",
    )

    assert len(gentle) < len(balanced) < len(dynamic)
    for ranges in (gentle, balanced, dynamic):
        assert 81.0 <= range_duration(ranges) <= 90.05


def test_sparse_adjacent_events_do_not_inflate_into_a_long_quiet_clip() -> None:
    events = [(100.0, 110.0, -8.0, -2.0), (125.0, 135.0, -8.0, -2.0)]
    ranges = _select_audio_highlight_ranges(
        _profile(600.0, events, step=1.0), 600.0, 90.0, [], selection_seed=3,
    )

    _assert_valid_ranges(ranges, 600.0)
    assert len(ranges) == 2
    assert range_duration(ranges) <= 30.05
    assert all(float(item["end"]) - float(item["start"]) <= 15.05 for item in ranges)
    for item in ranges:
        assert any(item["end"] > start and item["start"] < end for start, end, *_ in events)


def test_variation_cannot_discard_semantically_selected_story() -> None:
    from cutroom.director import _select_short_story_ranges

    segments = [
        {"id": f"s{index}", "start": float(index * 10), "end": float(index * 10 + 10),
         "text": "An unrelated high-energy topic." if index < 20 else "The requested topic.",
         "editorial_score": 0.95 if index < 20 else 0.6}
        for index in range(60)
    ]
    approved_story = [{"start": 220.0, "end": 250.0}, {"start": 440.0, "end": 470.0}]
    decision = {"story_ranges": approved_story, "highlight_ids": ["s22", "s44"]}
    assert _select_short_story_ranges(
        segments, decision, 600.0, 60.0, [], selection_seed=2, force_variation=True,
    ) == approved_story
