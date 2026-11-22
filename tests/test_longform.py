import pytest

from cutroom.longform import condense_longform, uses_longform_gameplay
from cutroom.utils import invert_ranges, range_duration
from cutroom.visual_moments import VisualTimeline


def _waveform(duration, loud):
    rows, position = [], 0.0
    while position < duration:
        hot = any(start <= position < end for start, end in loud)
        rows.append({"start": position, "end": position + 1.0, "rms_dbfs": -12.0 if hot else -42.0,
                     "peak_dbfs": -3.0 if hot else -32.0, "speech": 0.0})
        position += 1.0
    return {"waveform": rows}


LOUD = [(60, 140), (400, 470), (900, 1000), (1300, 1360)]


def test_condenses_to_the_ceiling_in_original_order():
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=[], visual=None, pace="balanced")
    keep = invert_ranges(result["cuts"], 1800)
    assert range_duration(keep) <= 300 + 1e-6
    assert result["seconds"] == pytest.approx(range_duration(keep))
    assert keep == sorted(keep, key=lambda row: row["start"])
    # Most of the kept time is inside the loud passages.
    inside = sum(max(0.0, min(row["end"], end) - max(row["start"], start)) for row in keep for start, end in LOUD)
    assert inside / range_duration(keep) > 0.8
    # No stretch is shorter than the minimum continuous length for this pace.
    assert all(row["end"] - row["start"] >= 20 - 1e-6 for row in keep)
    assert result["counts"]["longform_selection"] >= 3


def test_chapters_start_at_zero_and_are_long_enough():
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=[], visual=None)
    chapters = result["chapters"]
    assert len(chapters) >= 3 and chapters[0]["start"] == 0.0
    assert all(b["start"] - a["start"] >= 10 for a, b in zip(chapters, chapters[1:]))
    assert all(chapter["title"] for chapter in chapters)


def test_silent_menus_are_never_kept():
    visual = VisualTimeline({"available": True, "windows": [
        {"start": float(start), "end": float(start + 8), "screen": "menu_or_map", "score": 0.0, "event": "", "flags": []}
        for start in range(400, 470, 8)
    ]})
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=[], visual=visual)
    keep = invert_ranges(result["cuts"], 1800)
    assert not any(row["start"] < 460 and row["end"] > 410 for row in keep)
    assert result["counts"].get("dead_screen")


def test_dead_air_inside_kept_stretches_is_removed():
    candidates = [{"start": 70.0, "end": 72.5, "reason": "silence"}, {"start": 200.0, "end": 205.0, "reason": "silence"}]
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=[], visual=None, audio_candidates=candidates)
    assert any(cut["start"] <= 70.0 and cut["end"] >= 72.5 for cut in result["cuts"])
    assert result["counts"].get("silence") == 1


def test_without_measured_sound_it_declines():
    assert condense_longform(duration=600, target_duration=300, sound_profile={}, segments=[], visual=None) is None


def test_only_the_youtube_gameplay_style_uses_it():
    assert uses_longform_gameplay("youtube", {"edit_style": "gameplay_youtube"})
    assert not uses_longform_gameplay("short", {"edit_style": "gameplay_youtube"})
    assert not uses_longform_gameplay("youtube", {"edit_style": "clean_vod"})


def test_chapter_titles_come_from_what_is_said_without_vision():
    segments = [{"start": 70.0, "end": 74.0, "text": "No way, we actually won that fight!"},
                {"start": 905.0, "end": 909.0, "text": "Where is the last enemy hiding?"}]
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=segments, visual=None)
    titles = [chapter["title"] for chapter in result["chapters"]]
    assert "No way, we actually won that fight!" in titles
    assert "Where is the last enemy hiding?" in titles
    assert all(len(title) <= 48 for title in titles)


def test_punch_ins_sit_inside_the_output_and_are_spaced():
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, LOUD),
                               segments=[], visual=None)
    punches = result["punch_ins"]
    assert 1 <= len(punches) <= 12
    assert all(0.0 <= row["start"] < row["end"] <= result["seconds"] for row in punches)
    assert all(b["start"] - a["start"] >= 30 - 1e-6 for a, b in zip(punches, punches[1:]))
    assert result["cold_open"]["source_end"] - result["cold_open"]["source_start"] == pytest.approx(6.0)


def test_quiet_recording_gets_no_punch_ins():
    result = condense_longform(duration=1800, target_duration=300, sound_profile=_waveform(1800, []),
                               segments=[], visual=None)
    assert result is None or not result.get("punch_ins")
