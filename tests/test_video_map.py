from __future__ import annotations

import numpy as np

from cutroom.auto_style import recommend_style
from cutroom.clip_board import _events_in, _reasons, _sound_events
from cutroom.understanding import (
    SAMPLE_RATE,
    build_video_map,
    detect_sound_events,
    estimate_speakers,
    segment_topics,
    story_context,
    visual_rhythm,
)

RNG = np.random.default_rng(1)


def _voice(f0: float, formant: float, seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    signal = sum(np.sin(2 * np.pi * f0 * h * t) * np.exp(-((f0 * h - formant) / 500) ** 2) for h in range(1, 25))
    vibrato = 1 + 0.3 * np.sin(2 * np.pi * 4 * t)
    return (0.2 * signal * vibrato / (np.abs(signal).max() + 1e-9) + 0.003 * RNG.standard_normal(t.size)).astype(np.float32)


def _gap(seconds: float) -> np.ndarray:
    return (0.002 * RNG.standard_normal(int(seconds * SAMPLE_RATE))).astype(np.float32)


def _conversation(voices):
    parts, segments, clock = [], [], 0.0
    for index, (f0, formant) in enumerate(voices):
        parts += [_voice(f0, formant, 3.0), _gap(0.5)]
        segments.append({"id": f"s{index}", "start": clock, "end": clock + 3.0, "text": "a few words here"})
        clock += 3.5
    return np.concatenate(parts), segments


def test_two_distinct_voices_are_separated_and_named_by_first_appearance():
    samples, segments = _conversation([(110, 700), (230, 1800)] * 6)
    speakers = estimate_speakers(samples, segments)
    assert speakers["available"] and speakers["count"] == 2 and speakers["estimated"] is True
    labels = [speakers["segment_speakers"][f"s{i}"] for i in range(12)]
    assert labels == ["S1", "S2"] * 6
    assert len(speakers["turns"]) == 12


def test_one_voice_stays_one_speaker():
    samples, segments = _conversation([(110, 700)] * 12)
    assert estimate_speakers(samples, segments)["count"] == 1


def test_speakers_need_audio_and_enough_speech():
    _, segments = _conversation([(110, 700)] * 3)
    assert estimate_speakers(None, segments)["available"] is False
    assert estimate_speakers(np.zeros(SAMPLE_RATE * 20, dtype=np.float32), segments)["available"] is False


def test_sound_events_from_audio_and_transcript_markers():
    t_music = np.arange(SAMPLE_RATE * 8) / SAMPLE_RATE
    music = (0.2 * (np.sin(2 * np.pi * 440 * t_music) + np.sin(2 * np.pi * 554 * t_music) + np.sin(2 * np.pi * 659 * t_music)) / 3).astype(np.float32)
    applause = (0.3 * RNG.standard_normal(SAMPLE_RATE * 4)).astype(np.float32)
    t_laugh = np.arange(SAMPLE_RATE * 3) / SAMPLE_RATE
    laugh = (_voice(250, 1200, 3) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 5 * t_laugh))) * 2
             + 0.02 * RNG.standard_normal(t_laugh.size)).astype(np.float32)
    audio = np.concatenate([_gap(4), applause, _gap(4), music, _gap(4), laugh, _gap(4)])
    events = detect_sound_events(audio, [{"start": 0.0, "end": 1.0, "text": "חחחח איזה קטע"}])
    kinds = [(event["type"], event["source"]) for event in events]
    assert ("laughter", "transcript") in kinds
    found = {event["type"]: event for event in events if event["source"] == "audio"}
    assert set(found) == {"applause", "music", "laughter"}
    assert 3.5 <= found["applause"]["start"] <= 5.0 and found["applause"]["end"] <= 8.5
    assert 11.5 <= found["music"]["start"] <= 13.0
    assert 23.0 <= found["laughter"]["start"] <= 24.5
    assert all(isinstance(event["start"], float) for event in events)


def test_quiet_speech_raises_no_sound_events():
    samples, segments = _conversation([(110, 700), (230, 1800)] * 4)
    assert [event for event in detect_sound_events(samples, segments) if event["type"] != "laughter"] == []


def test_topics_split_on_vocabulary_shift():
    rows = []
    for index in range(30):
        topic = "bread flour oven dough yeast" if index < 15 else "camera lens light tripod focus"
        rows.append({"id": f"t{index}", "start": index * 10.0, "end": index * 10.0 + 9.0, "text": f"the {topic} today"})
    topics = segment_topics(rows, 300.0)
    assert len(topics) == 2
    assert 130.0 <= topics[1]["start"] <= 170.0
    assert set(topics[0]["keywords"]) <= {"bread", "flour", "oven", "dough", "yeast", "today"}
    assert topics[0]["start"] == 0.0 and topics[-1]["end"] == 300.0


def test_visual_rhythm_uses_existing_shots_and_faces():
    visual = visual_rhythm([12.0, 30.0, 59.0, 999.0], {"available": True, "face_clusters": [{"coverage": 0.8}, {"coverage": 0.1}]}, 120.0)
    assert visual == {"shot_changes": 3, "shots_per_minute": 1.5, "stable_faces": 1, "face_coverage": 0.8}
    assert visual_rhythm([], {}, 60.0)["stable_faces"] is None


def test_video_map_and_story_context_are_advisory_and_compact():
    samples, segments = _conversation([(110, 700), (230, 1800)] * 6)
    video_map = build_video_map(segments=segments, duration=42.0, samples=samples, scenes=[10.0], vision=None)
    assert video_map["available"] and video_map["speakers"]["count"] == 2
    context = story_context(video_map)
    assert context["authority"] == "advisory_only"
    assert context["speaker_count"] == 2 and len(context["speaker_turns"]) == 12
    assert story_context(None) is None
    no_audio = build_video_map(segments=segments, duration=42.0, samples=None, audio_reason="offset_audio_source")
    assert no_audio["speakers"]["reason"] == "offset_audio_source"
    assert story_context(no_audio)["speaker_count"] is None


def test_clip_board_rewards_laughter_and_names_it():
    project = {"analysis": {"audio_source": "A", "video_map": {"available": True, "events": [
        {"type": "laughter", "start": 10.0, "end": 12.0}, {"type": "speech", "start": 0, "end": 1}]}}}
    events = _sound_events(project)
    assert [event["type"] for event in events] == ["laughter"]
    assert _events_in(0.0, 15.0, events) == ["laughter"] and _events_in(20.0, 30.0, events) == []
    reasons = _reasons({}, 50, 0, True, ["laughter"])
    assert {"kind": "sound_event", "type": "laughter"} in reasons
    shifted = {"analysis": {**project["analysis"], "audio_source": "B", "audio_timeline_offset": 2.0}}
    assert _sound_events(shifted) == []


def test_recommendation_uses_measured_speaker_count():
    segments = [{"start": i * 5.0, "end": i * 5.0 + 5.0, "text": "talk"} for i in range(18)]
    project = {"settings": {"goal": "short"}, "sources": {"A": {"duration": 100.0}},
               "analysis": {"segments": segments, "video_map": {"available": True, "speakers": {"available": True, "count": 2}}}}
    advice = recommend_style(project)
    assert advice["style"] == "talking_clips" and advice["confidence"] == "high"


class _Context:
    class job:
        progress = 0.5

    def update(self, *_args):
        pass

    def check_cancelled(self):
        pass


def test_director_reuses_a_cached_map_and_skips_offset_audio():
    from cutroom.director import _resolve_video_map

    segments = [{"id": f"s{i}", "start": i * 3.0, "end": i * 3.0 + 2.5, "text": "hello there"} for i in range(10)]
    fingerprints = {"source": "src", "transcript": "tr", "scenes": "sc", "vision": "vi"}
    fresh = _resolve_video_map(_Context(), None, None, fingerprints, segments=segments, duration=30.0,
                               audio_path=None, audio_slot="A", audio_offset=0.0, scenes=[], vision={})
    assert fresh["available"] and fresh["speakers"]["reason"] == "no_audio_source" and fresh["cache_key"]
    reused = _resolve_video_map(_Context(), None, {"video_map": {**fresh, "marker": 1}}, fingerprints, segments=segments,
                                duration=30.0, audio_path=None, audio_slot="A", audio_offset=0.0, scenes=[], vision={})
    assert reused.get("marker") == 1
    offset = _resolve_video_map(_Context(), None, None, {**fingerprints, "transcript": "other"}, segments=segments,
                                duration=30.0, audio_path=__file__, audio_slot="B", audio_offset=1.5, scenes=[], vision={})
    assert offset["speakers"]["reason"] == "offset_audio_source"
    assert _resolve_video_map(_Context(), None, None, fingerprints, segments=[], duration=30.0, audio_path=None,
                              audio_slot="A", audio_offset=0.0, scenes=[], vision={}) is None
