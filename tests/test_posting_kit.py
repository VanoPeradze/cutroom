import pytest

from cutroom.posting_kit import PostingKitError, PostingKitUnavailable, ai_posting_kit, build_posting_kit


def project(segments, duration=120.0):
    return {
        "sources": {"A": {"duration": duration}},
        "analysis": {"audio_source": "A", "segments": segments},
    }


SEGMENTS = [
    {"start": 10.0, "end": 13.0, "text": "Okay we are pushing the bridge now"},
    {"start": 13.0, "end": 16.0, "text": "No way, that bridge clutch was insane!"},
    {"start": 16.0, "end": 20.0, "text": "The bridge push won us the round"},
    {"start": 60.0, "end": 64.0, "text": "Unrelated later line"},
]


def test_basic_kit_uses_only_lines_inside_the_clip():
    kit = build_posting_kit(project(SEGMENTS), 9.5, 21.0)
    assert kit["source"] == "transcript" and kit["ai"] is False and kit["language"] == "en"
    assert kit["titles"][0] == "No way, that bridge clutch was insane!"
    assert all("Unrelated" not in title for title in kit["titles"])
    assert "Unrelated" not in kit["description"]
    assert "#bridge" in kit["hashtags"] and "#shorts" in kit["hashtags"]
    assert len(kit["titles"]) <= 3 and len(kit["hashtags"]) <= 6


def test_hebrew_clip_is_detected_and_titled_in_hebrew():
    kit = build_posting_kit(project([{"start": 0, "end": 4, "text": "וואו איזה משחק מטורף היה היום"}]), 0, 5)
    assert kit["language"] == "he"
    assert kit["titles"][0].startswith("וואו")
    assert any(tag.startswith("#") and "משחק" in tag for tag in kit["hashtags"])


def test_no_transcript_is_honest_and_offers_no_ai():
    kit = build_posting_kit(project([]), 0, 30)
    assert kit["source"] == "none" and kit["titles"] == [] and "no transcript" in kit["note"]
    with pytest.raises(PostingKitUnavailable):
        ai_posting_kit(object(), project([]), 0, 30, status=lambda *_: {"ready": True}, call=lambda *_a, **_k: {})


def test_transcript_with_offset_or_other_source_is_ignored():
    shifted = project(SEGMENTS)
    shifted["analysis"]["audio_timeline_offset"] = 1.5
    assert build_posting_kit(shifted, 9.5, 21.0)["source"] == "none"


@pytest.mark.parametrize("start,end", [(-1, 10), (10, 10), (20, 5), ("x", 5), (0, 500)])
def test_invalid_ranges_are_rejected(start, end):
    with pytest.raises(PostingKitError):
        build_posting_kit(project(SEGMENTS), start, end)


def test_ai_kit_is_sanitized_and_keeps_basic_fallbacks():
    seen = {}

    def call(settings, payload, timeout):
        seen["payload"] = payload
        return {"titles": ["  \"Bridge clutch!\"  ", "Bridge clutch!", "x" * 200, 7],
                "hook": "Watch this bridge", "description": "", "hashtags": ["#Gaming", "bad tag!", 5, "clutch"]}

    kit = ai_posting_kit(object(), project(SEGMENTS), 9.5, 21.0,
                         status=lambda *_: {"ready": True, "selected_model": "m"}, call=call)
    assert kit["ai"] is True and kit["model"] == "m"
    assert kit["titles"][0] == "Bridge clutch!" and len(kit["titles"]) == 2 and len(kit["titles"][1]) <= 80
    assert kit["hook"] == "Watch this bridge"
    assert kit["description"]  # empty AI description falls back to the transcript excerpt
    assert kit["hashtags"] == ["#Gaming", "#badtag", "#clutch"]
    prompt = seen["payload"]["messages"][1]["content"]
    assert "bridge clutch" in prompt and "Unrelated" not in prompt
    assert seen["payload"]["model"] == "m" and seen["payload"]["format"] == "json"


def test_ai_not_ready_or_empty_answer_is_reported_not_raised_as_crash():
    with pytest.raises(PostingKitUnavailable, match="Connect"):
        ai_posting_kit(object(), project(SEGMENTS), 9.5, 21.0,
                       status=lambda *_: {"ready": False, "message": "Connect Groq"}, call=lambda *a, **k: None)
    with pytest.raises(PostingKitUnavailable):
        ai_posting_kit(object(), project(SEGMENTS), 9.5, 21.0,
                       status=lambda *_: {"ready": True, "selected_model": "m"}, call=lambda *a, **k: {"titles": []})

    def boom(*_a, **_k):
        raise OSError("offline")

    with pytest.raises(PostingKitUnavailable, match="offline"):
        ai_posting_kit(object(), project(SEGMENTS), 9.5, 21.0,
                       status=lambda *_: {"ready": True, "selected_model": "m"}, call=boom)
