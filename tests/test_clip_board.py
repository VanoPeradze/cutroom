import copy

import pytest

from cutroom.clip_board import ClipBoardError, build_clip_board


def _project(duration=300.0, loud=((100.0, 130.0), (200.0, 215.0)), segments=None, visual=None):
    waveform = []
    position = 0.0
    while position < duration:
        hot = any(start <= position < end for start, end in loud)
        waveform.append({"start": position, "end": position + 1.0, "rms_dbfs": -12.0 if hot else -40.0,
                         "peak_dbfs": -3.0 if hot else -30.0, "speech": 0.0})
        position += 1.0
    analysis = {"segments": segments or []}
    if visual:
        analysis["visual_moments"] = visual
    return {"id": "p", "revision": 4, "sources": {"A": {"duration": duration, "has_audio": True}},
            "pre_analysis": {"audio": {"A": {"available": True, "waveform": waveform}}},
            "analysis": analysis, "manual": {}}


def test_ranks_loud_moments_first_without_overlap():
    board = build_clip_board(_project(), length=30, count=6)
    assert board["available"] and board["signals"] == {"audio": True, "transcript": False, "vision": False}
    clips = board["clips"]
    assert 100 <= clips[0]["start"] < 130 or 100 < clips[0]["end"] <= 130
    assert [clip["rank"] for clip in clips] == list(range(1, len(clips) + 1))
    for left in clips:
        for right in clips:
            if left is not right:
                assert left["end"] + 2.0 <= right["start"] or right["end"] + 2.0 <= left["start"]
    assert all(0 <= clip["strength"] <= 100 and clip["duration"] == pytest.approx(clip["end"] - clip["start"]) for clip in clips)
    assert clips[0]["strength"] >= clips[-1]["strength"]
    assert 100 <= clips[0]["peak"] <= 130


def test_is_read_only_and_reports_heat():
    project = _project()
    before = copy.deepcopy(project)
    board = build_clip_board(project, length=15, count=3)
    assert project == before
    assert board["heat"] and all(0 <= point["strength"] <= 100 for point in board["heat"])


def test_transcript_hook_and_reactions_follow_source_a_clock():
    segments = [{"start": 104.0, "end": 108.0, "text": "No way, did you see that!"},
                {"start": 109.0, "end": 112.0, "text": "That was insane"}]
    board = build_clip_board(_project(segments=segments), length=30, count=2)
    top = board["clips"][0]
    assert top["hook"] == "No way, did you see that!"
    assert any(reason["kind"] == "reactions" for reason in top["reasons"])
    shifted = _project(segments=segments)
    shifted["analysis"]["audio_timeline_offset"] = 3.5
    assert build_clip_board(shifted, length=30, count=2)["signals"]["transcript"] is False


def test_unavailable_states_explain_why():
    project = _project()
    project["pre_analysis"] = {}
    assert build_clip_board(project)["reason"] == "audio_profile_missing"
    assert build_clip_board({"id": "p", "sources": {}})["reason"] == "no_source"


@pytest.mark.parametrize("length,count", [(17, 3), (30, 0), (30, 99), ("x", 3)])
def test_rejects_invalid_requests(length, count):
    with pytest.raises(ClipBoardError):
        build_clip_board(_project(), length=length, count=count)
