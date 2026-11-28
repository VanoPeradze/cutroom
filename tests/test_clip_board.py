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


def test_content_scores_explain_hook_completeness_and_clarity():
    from cutroom.clip_board import _content_scores

    strong = [{"start": 10.0, "end": 13.0, "text": "Did you know 90% of creators skip this?"},
              {"start": 13.5, "end": 18.0, "text": "Here is the fix."}]
    scores = _content_scores(9.5, 19.0, strong)
    assert scores["hook"]["score"] >= 90
    assert "question" in scores["hook"]["note"] and "number" in scores["hook"]["note"] and "viewer" in scores["hook"]["note"]
    assert scores["complete"] == {"score": 100, "note": "starts and ends on whole sentences"}
    assert scores["clarity"]["score"] == 100

    rough = [{"start": 5.0, "end": 9.0, "text": "and um so like the uh thing"},
             {"start": 9.5, "end": 14.0, "text": "we were going to"}]
    weak = _content_scores(7.0, 12.0, rough)
    assert weak["hook"]["note"] == "a plain first line" and weak["hook"]["score"] == 30
    assert weak["complete"]["note"] == "starts and ends mid-sentence"
    assert weak["clarity"]["score"] < 80 and "filler" in weak["clarity"]["note"]
    assert _content_scores(0, 5, []) is None


def test_board_clips_carry_content_scores_only_with_a_transcript():
    segments = [{"start": 104.0, "end": 108.0, "text": "No way, did you see that!"}]
    assert build_clip_board(_project(segments=segments), length=30, count=1)["clips"][0]["content"]["hook"]["score"] > 30
    assert build_clip_board(_project(), length=30, count=1)["clips"][0]["content"] is None


def _edited(project):
    # The edit shows source A 100-130 s (the loud part) at 0-30 s, then A 10-40 s at 30-60 s.
    project["draft"] = {"source_duration": 300.0, "keep_ranges": [{"start": 0.0, "end": 300.0}], "cuts": [],
                        "camera_plan": [{"start": 0.0, "end": 300.0, "camera": "A"}]}
    project["settings"] = {"fps": 30}
    project["manual"] = {"sequence": {"version": 1, "duration": 60.0,
                                      "camera_plan": [{"start": 0.0, "end": 60.0, "camera": "stacked"}]},
                         "source_tracks": {"A": [{"id": "A:loud", "start": 0.0, "end": 30.0, "source_start": 100.0},
                                                 {"id": "A:calm", "start": 30.0, "end": 60.0, "source_start": 10.0}]}}
    return project


def test_edit_scope_ranks_moments_on_the_edit_clock():
    segments = [{"start": 104.0, "end": 108.0, "text": "No way, did you see that!"}]
    project = _edited(_project(segments=segments))
    before = copy.deepcopy(project)
    board = build_clip_board(project, length=15, count=3, scope="edit")
    assert project == before
    assert board["available"] and board["scope"] == "edit" and board["source_clock"] == "edit"
    assert board["source_duration"] == pytest.approx(60.0)
    top = board["clips"][0]
    assert top["clock"] == "edit" and 0.0 <= top["start"] < top["end"] <= 30.0
    assert top["hook"] == "No way, did you see that!"
    # Source-A seconds of the same moment, for the posting kit and thumbnails.
    assert 100.0 <= top["source_start"] < top["source_end"] <= 130.0
    assert 100.0 <= top["source_peak"] <= 130.0
    assert all(clip["end"] <= 60.0 + 1e-6 for clip in board["clips"])
    # The default scope is unchanged: moments across the whole recording.
    assert build_clip_board(project, length=15, count=3)["source_clock"] == "A"


def test_edit_scope_needs_an_edit_and_a_known_scope():
    assert build_clip_board(_project(), length=15, scope="edit")["reason"] == "no_edit"
    with pytest.raises(ClipBoardError):
        build_clip_board(_project(), length=15, scope="timeline")
