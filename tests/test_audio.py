from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np

from cutroom.audio import analyze_audio, audio_policy, build_audio_actions, constrain_gain_ranges_to_speech
from cutroom.config import load_settings


def _write_test_wav(path: Path, rate: int = 8000) -> None:
    parts = []
    parts.append(np.zeros(rate, dtype=np.float32))
    t = np.arange(rate, dtype=np.float32) / rate
    parts.append(0.03 * np.sin(2 * math.pi * 220 * t))
    parts.append(0.55 * np.sin(2 * math.pi * 220 * t))
    parts.append(np.zeros(rate, dtype=np.float32))
    audio = np.concatenate(parts)
    pcm = np.clip(audio * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())


def test_audio_profile_detects_relative_silence_and_levels(tmp_path: Path):
    source = tmp_path / "levels.wav"
    _write_test_wav(source)
    settings = load_settings()
    profile = analyze_audio(source, settings, 4.0)
    assert profile["available"] is True
    assert len(profile["ranges"]["silence"]) >= 2
    assert profile["summary"]["noise_floor_dbfs"] < profile["summary"]["speech_reference_dbfs"]
    assert profile["summary"]["peak_dbfs"] > -8.0


def test_audio_policy_is_bounded():
    policy = audio_policy({"preset": "tight", "max_remove_ratio": 99, "quiet_gain_db": 99, "loud_gain_db": -99})
    assert policy["max_remove_ratio"] == 0.70
    assert policy["quiet_gain_db"] == 10.0
    assert policy["loud_gain_db"] == -10.0


def test_audio_actions_follow_user_policy():
    profile = {
        "summary": {"silence_threshold_dbfs": -48.0},
        "ranges": {
            "silence": [{"start": 1.0, "end": 3.0, "duration": 2.0}],
            "quiet_speech": [{"start": 4.0, "end": 5.0, "duration": 1.0}],
            "loud_speech": [{"start": 6.0, "end": 7.0, "duration": 1.0}],
            "clipping": [],
        },
    }
    cuts, gains, counts = build_audio_actions(profile, {
        "preset": "clean", "silence_min_seconds": .8, "silence_keep_seconds": .4,
        "quiet_gain_db": 4, "loud_gain_db": -3,
    }, 10.0)
    assert cuts and cuts[0]["reason"] == "silence"
    assert any(item["gain_db"] == 4 for item in gains)
    assert any(item["gain_db"] == -3 for item in gains)
    assert counts["quiet_audio"] == 1 and counts["loud_audio"] == 1


def test_gain_ranges_are_constrained_to_transcript_speech():
    profile = {"ranges": {"silence": [], "quiet_speech": [{"start": 1, "end": 2}, {"start": 5, "end": 6}], "loud_speech": [{"start": 7, "end": 8}], "clipping": []}}
    transcript = [{"start": 1.2, "end": 2.3}, {"start": 7.2, "end": 7.8}]
    filtered = constrain_gain_ranges_to_speech(profile, transcript)
    assert len(filtered["ranges"]["quiet_speech"]) == 1
    assert len(filtered["ranges"]["loud_speech"]) == 1


def test_audio_profile_exposes_compact_real_waveform(tmp_path: Path):
    source = tmp_path / "waveform.wav"
    _write_test_wav(source)
    profile = analyze_audio(source, load_settings(), 4.0)
    assert profile["waveform"]
    assert len(profile["waveform"]) <= 900
    assert all("rms_dbfs" in item and "peak_dbfs" in item for item in profile["waveform"])
    assert max(float(item["peak_dbfs"]) for item in profile["waveform"]) > -8.0


def test_manual_db_threshold_changes_detected_silence(tmp_path: Path):
    source = tmp_path / "manual-threshold.wav"
    _write_test_wav(source)
    settings = load_settings()
    strict = analyze_audio(source, settings, 4.0, silence_threshold_dbfs=-50.0)
    aggressive = analyze_audio(source, settings, 4.0, silence_threshold_dbfs=-25.0)
    strict_silence = sum(float(item["duration"]) for item in strict["ranges"]["silence"])
    aggressive_silence = sum(float(item["duration"]) for item in aggressive["ranges"]["silence"])
    assert strict["summary"]["silence_threshold_dbfs"] == -50.0
    assert aggressive["summary"]["silence_threshold_dbfs"] == -25.0
    assert aggressive_silence > strict_silence + 0.5
    assert aggressive["summary"]["recommended_silence_threshold_dbfs"] != -25.0


def test_confirmed_speech_is_protected_from_aggressive_db_cut():
    from cutroom.audio import protect_silence_ranges_from_speech
    profile = {
        "ranges": {
            "silence": [{"start": 1.0, "end": 4.0, "duration": 3.0}],
            "quiet_speech": [], "loud_speech": [], "clipping": [],
        },
        "summary": {"silence_threshold_dbfs": -25.0},
    }
    transcript = [{"start": 2.0, "end": 3.0, "text": "quiet but real speech"}]
    protected = protect_silence_ranges_from_speech(profile, transcript, padding=0.1)
    silence = protected["ranges"]["silence"]
    assert len(silence) == 2
    assert silence[0]["end"] <= 1.9 + 1e-6
    assert silence[1]["start"] >= 3.1 - 1e-6
