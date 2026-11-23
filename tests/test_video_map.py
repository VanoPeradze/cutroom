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

def test_decoder_uses_local_path_and_finite_output_bound(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from cutroom import media
    from cutroom.understanding import decode_mono

    path = tmp_path / "synthetic audio.wav"
    callback = lambda: None
    seen = []

    def run(args, **options):
        seen.append((args, options))
        return SimpleNamespace(stdout=b"\x00\x40" * SAMPLE_RATE)

    monkeypatch.setattr(media, "run_command", run)
    samples = decode_mono(path, SimpleNamespace(ffmpeg="ffmpeg"), 1.0, cancel_check=callback)
    assert samples.dtype == np.float32 and samples.shape == (SAMPLE_RATE,)
    assert float(samples[0]) == 0.5
    args, options = seen[0]
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    assert args.index("-protocol_whitelist") < args.index("-i")
    assert args[args.index("-i") + 1] == str(path.absolute())
    assert float(args[args.index("-t") + 1]) == 1
    assert args[-1] == "pipe:1" and options["cancel_check"] is callback and options["text"] is False
    for duration in (0, 0.99999, float("nan"), float("inf"), 4 * 3600 + 1):
        assert decode_mono(path, SimpleNamespace(ffmpeg="ffmpeg"), duration) is None
    assert len(seen) == 1


def test_decoder_rejects_invalid_pcm_and_keeps_cancellation(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import pytest
    from cutroom import media
    from cutroom.jobs import JobCancelled
    from cutroom.understanding import decode_mono

    path = tmp_path / "only a synthetic file name.wav"
    settings = SimpleNamespace(ffmpeg="ffmpeg")
    for output in (b"\x00" * (2 * SAMPLE_RATE + 1), b"\x00\x00" * (SAMPLE_RATE + 1)):
        monkeypatch.setattr(media, "run_command", lambda *args, **kwargs: SimpleNamespace(stdout=output))
        assert decode_mono(path, settings, 1) is None

    def cancel(*args, **kwargs):
        raise JobCancelled("synthetic cancellation")

    monkeypatch.setattr(media, "run_command", cancel)
    with pytest.raises(JobCancelled):
        decode_mono(path, settings, 1)


def test_map_cache_matches_saved_words_markers_and_audio_routing(tmp_path, monkeypatch):
    from cutroom import director

    samples = np.zeros(SAMPLE_RATE * 3, dtype=np.float32)
    monkeypatch.setattr(director, "decode_mono", lambda *args, **kwargs: samples)
    fingerprints = {"source": "src", "transcript": "tr", "scenes": "sc", "vision": "vi"}
    args = {"duration": 5.0, "audio_path": tmp_path / "synthetic.wav",
            "scenes": [], "vision": {}}
    rows = [{"id": "one", "start": 0.0, "end": 2.0, "text": "volcano [laughter]"}]

    def resolve(cache, text, slot="A", shift=0.0):
        return director._resolve_video_map(
            _Context(), None, {"video_map": cache} if cache else None, fingerprints,
            segments=[{**rows[0], "text": text}], audio_slot=slot, audio_offset=shift, **args)

    first = resolve(None, rows[0]["text"])
    assert "volcano" in first["topics"][0]["keywords"] and first["event_counts"]["laughter"] == 1
    corrected = resolve(first, "butterfly laughter")
    assert corrected["cache_key"] != first["cache_key"]
    assert "butterfly" in corrected["topics"][0]["keywords"] and not corrected["event_counts"]
    marker_removed = resolve(first, "volcano laughter")
    assert marker_removed["cache_key"] != first["cache_key"] and not marker_removed["event_counts"]
    offset = resolve(first, rows[0]["text"], slot="B", shift=1.5)
    assert offset["cache_key"] != first["cache_key"] and offset["speakers"]["reason"] == "offset_audio_source"


def test_source_note_and_video_map_are_only_advised_to_local_story():
    from cutroom.director import _attach_video_map_to_local_story, _effective_brief

    project = {"settings": {"edit_style": "talking_clips", "source_context": "Local creator note",
                            "instruction": "Existing reviewed instruction"}}
    video_map = build_video_map(
        segments=[{"id": "line", "text": "Demo local keyword", "start": 0.0, "end": 2.0}],
        duration=3.0, samples=None)
    local = _effective_brief(project, local_story=True)
    assert _attach_video_map_to_local_story(local, video_map, local_story=True)
    assert local["style_profile"]["source_context"]["text"] == "Local creator note"
    assert local["style_profile"]["video_map"]["authority"] == "advisory_only"
    cloud = _effective_brief(project, local_story=False)
    assert not _attach_video_map_to_local_story(cloud, video_map, local_story=False)
    assert "source_context" not in cloud and "source_context" not in cloud["style_profile"]
    assert "video_map" not in cloud["style_profile"]
    assert cloud["instruction"] == project["settings"]["instruction"]
    assert project["settings"]["source_context"] == "Local creator note"

def test_real_local_pcm_stops_at_verified_media_duration(tmp_path):
    import shutil
    import wave
    from types import SimpleNamespace

    import pytest
    from cutroom.understanding import decode_mono

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("Real FFmpeg is not installed")
    path = tmp_path / "synthetic sound.wav"
    with wave.open(str(path), "wb") as sound:
        sound.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        sound.writeframes(b"\x00\x20" * (2 * SAMPLE_RATE))
    samples = decode_mono(path, SimpleNamespace(ffmpeg=ffmpeg), 1.0)
    assert samples.shape == (SAMPLE_RATE,)
    assert np.all(samples == 0.25)
