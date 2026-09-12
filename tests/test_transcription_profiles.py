from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import transcription
from cutroom import transcription_worker
from cutroom.jobs import JobCancelled
from cutroom.transcription import (
    _model_for_request,
    _resolve_language_evidence,
    _split_oversized_segments,
    transcript_quality_report,
)


class DummySettings:
    ai = {
        "whisper_model": "base",
        "whisper_models": {"lite":"base","balanced":"small","quality":"turbo"},
        "hebrew_whisper_model":"ivrit-ai/whisper-large-v3-turbo-ct2",
        "whisper_device": "auto",
        "whisper_compute_type": "auto",
    }


def test_hebrew_quality_uses_specialized_model_while_balanced_stays_light():
    settings = DummySettings()
    assert _model_for_request(settings, "quality", "he", "cpu") == "ivrit-ai/whisper-large-v3-turbo-ct2"
    assert _model_for_request(settings, "balanced", "he", "cuda") == "small"


def test_balanced_cpu_keeps_light_multilingual_model():
    settings = DummySettings()
    assert _model_for_request(settings, "balanced", "he", "cpu") == "small"
    assert _model_for_request(settings, "lite", "he", "cpu") == "base"


def _language_unit(language: str, probability: float, text: str) -> dict:
    return {
        "language": language,
        "language_probability": probability,
        "text": text,
        "segments": [{"start": 0.0, "end": 8.0, "text": text}],
    }


def test_language_consensus_uses_multiple_windows_and_reports_evidence():
    english = _language_unit("en", 0.94, "welcome to this short intro")
    hebrew_one = _language_unit("he", 0.91, "אני רוצה להסביר עכשיו איך עורכים סרטון בצורה טובה")
    hebrew_two = _language_unit("he", 0.96, "זה החלק החשוב של הסרטון וגם הסיבה שאנחנו כאן")

    resolved = _resolve_language_evidence(english, None, [english, hebrew_one, hebrew_two])

    assert resolved["language"] == "he"
    assert resolved["detected_language"] == "he"
    assert 0.62 <= resolved["language_probability"] < 0.96
    assert resolved["detected_language_probability"] == resolved["language_probability"]
    assert resolved["language_detection"]["source"] == "script_assisted"
    assert resolved["language_detection"]["observations"] == 3
    assert resolved["language_detection"]["agreeing_observations"] == 2
    assert resolved["language_detection"]["runner_up"] == "en"
    assert resolved["language_detection"]["ambiguous"] is False
    report = transcript_quality_report({
        **resolved,
        "duration": 16.0,
        "segments": [{"start": 0.0, "end": 8.0, "text": hebrew_one["text"], "avg_logprob": -0.2}],
        "text": hebrew_one["text"],
    })
    assert report["detected_language"] == "he"
    assert report["detected_language_probability"] == resolved["language_probability"]
    assert report["language_detection"]["source"] == "script_assisted"


def test_conflicting_windows_lower_auto_language_confidence():
    english = _language_unit("en", 0.98, "this is a complete sentence with clear English speech")
    french = _language_unit("fr", 0.98, "voici une phrase complete avec une parole francaise claire")

    resolved = _resolve_language_evidence(english, None, [english, french])

    assert resolved["language"] in {"en", "fr"}
    assert resolved["language_probability"] < 0.62
    assert resolved["language_detection"]["ambiguous"] is True
    assert "low_language_confidence" in transcript_quality_report({
        **resolved,
        "duration": 16.0,
        "segments": [
            {"start": 0.0, "end": 8.0, "text": english["text"], "avg_logprob": -0.2},
            {"start": 8.0, "end": 16.0, "text": french["text"], "avg_logprob": -0.2},
        ],
        "text": f"{english['text']} {french['text']}",
    })["reasons"]


def test_hebrew_script_corrects_an_incompatible_opening_window_label():
    mislabeled = _language_unit(
        "en",
        0.96,
        "אני רוצה להסביר עכשיו איך עורכים את הסרטון הזה בצורה טובה ומהירה",
    )

    resolved = _resolve_language_evidence(mislabeled, None)

    assert resolved["language"] == "he"
    assert resolved["language_detection"]["raw_language"] == "en"
    assert resolved["language_detection"]["source"] == "script_assisted"
    assert resolved["language_probability"] < 0.96


def test_hebrew_script_does_not_override_a_confident_yiddish_detection():
    yiddish = _language_unit(
        "yi",
        0.92,
        "איך בין דאָ און דאָס איז אַ קלאָרער זאַץ מיט גענוג אותיות",
    )

    resolved = _resolve_language_evidence(yiddish, None)

    assert resolved["language"] == "yi"
    assert resolved["language_detection"]["source"] == "whisper"


def test_weak_yiddish_remains_yiddish_and_is_marked_ambiguous():
    yiddish = _language_unit(
        "yi",
        0.67,
        "איך בין דאָ און אז איך רעד קלאָר אין דעם ווידעא",
    )

    resolved = _resolve_language_evidence(yiddish, None)

    assert resolved["language"] == "yi"
    assert resolved["language_detection"]["raw_language"] == "yi"
    assert resolved["language_probability"] < 0.62
    assert resolved["language_detection"]["ambiguous"] is True


def test_short_hebrew_script_conflict_cannot_remain_high_confidence_english():
    too_short_to_choose_safely = _language_unit("en", 0.96, "זה טוב")

    resolved = _resolve_language_evidence(too_short_to_choose_safely, None)

    assert resolved["language"] == "en"
    assert resolved["language_detection"]["raw_language"] == "en"
    assert resolved["language_probability"] < 0.62
    assert resolved["language_detection"]["ambiguous"] is True


def test_close_multi_window_vote_is_capped_below_the_quality_gate():
    english = _language_unit("en", 0.99, "this is a somewhat longer clear English sentence for evidence")
    french = _language_unit("fr", 0.99, "phrase francaise claire avec parole")

    resolved = _resolve_language_evidence(english, None, [english, french])

    assert 0.55 < resolved["language_detection"]["vote_share"] < 0.58
    assert resolved["language_detection"]["ambiguous"] is True
    assert resolved["language_probability"] < 0.62


def test_quality_report_rejects_external_ambiguous_metadata_even_above_threshold():
    report = transcript_quality_report({
        "language": "en",
        "language_probability": 0.84,
        "detected_language": "en",
        "detected_language_probability": 0.84,
        "language_detection": {"source": "consensus", "ambiguous": True},
        "duration": 8.0,
        "text": "this sentence has enough real speech for every other quality check",
        "segments": [{
            "start": 0.0,
            "end": 8.0,
            "text": "this sentence has enough real speech for every other quality check",
            "avg_logprob": -0.2,
        }],
    })

    assert report["usable_for_story"] is False
    assert report["reasons"] == ["ambiguous_language_evidence"]


def test_explicit_language_stays_authoritative_but_retains_detection():
    detected = _language_unit("en", 0.95, "this recording begins with a clear English sentence")

    resolved = _resolve_language_evidence(detected, "he")

    assert resolved["language"] == "he"
    assert resolved["language_probability"] == 1.0
    assert resolved["detected_language"] == "en"
    assert resolved["detected_language_probability"] == 0.95
    assert resolved["language_detection"]["source"] == "explicit"
    assert resolved["language_detection"]["requested_language"] == "he"


def test_auto_hebrew_refinement_preserves_auto_detection_confidence(monkeypatch):
    calls: list[str | None] = []

    def fake_once(*args, **_kwargs):
        requested_language = args[5]
        calls.append(requested_language)
        if requested_language is None:
            return {
                "language": "he",
                "language_probability": 0.87,
                "detected_language": "he",
                "detected_language_probability": 0.87,
                "language_detection": {
                    "source": "script_assisted",
                    "requested_language": "auto",
                    "raw_language": "en",
                    "observations": 2,
                    "ambiguous": False,
                },
                "model": "turbo",
                "segments": [],
                "words": [],
                "text": "",
            }
        return {
            "language": "he",
            "language_probability": 1.0,
            "detected_language": "he",
            "detected_language_probability": 1.0,
            "language_detection": {"source": "explicit", "requested_language": "he", "ambiguous": False},
            "model": "ivrit-ai/whisper-large-v3-turbo-ct2",
            "segments": [],
            "words": [],
            "text": "",
        }

    monkeypatch.setattr(transcription, "cuda_available", lambda _settings=None: False)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args, **_kwargs: ("cpu", "int8"))
    monkeypatch.setattr(transcription, "_transcribe_once", fake_once)

    result = transcription._transcribe_in_process(
        Path("unused.mp4"),
        DummySettings(),
        language="auto",
        performance_mode="quality",
        duration=30.0,
    )

    assert calls == [None, "he"]
    assert result["language"] == "he"
    assert result["language_probability"] == 0.87
    assert result["detected_language_probability"] == 0.87
    assert result["language_detection"]["source"] == "auto_refined"
    assert result["language_detection"]["requested_language"] == "auto"
    assert result["language_detection"]["refined_language"] == "he"


def test_auto_language_without_transcribed_letters_has_zero_confidence():
    resolved = _resolve_language_evidence({
        "language": "en",
        "language_probability": 0.99,
        "text": "",
        "segments": [],
    }, None)

    assert resolved["language"] == "en"
    assert resolved["language_probability"] == 0.0
    assert resolved["language_detection"]["source"] == "none"
    assert resolved["language_detection"]["observations"] == 0
    assert resolved["language_detection"]["ambiguous"] is True


@pytest.mark.parametrize("refined_logprob", [None, -1.2, -0.15])
def test_hebrew_refinement_cannot_replace_usable_speech_with_an_unusable_pass(monkeypatch, refined_logprob):
    original_text = "אני רוצה להסביר עכשיו איך עורכים את הסרטון הזה בצורה ברורה וטובה"
    refined_text = "אני רוצה להסביר עכשיו איך אפשר לערוך את הסרטון הזה בצורה ברורה וטובה"
    calls: list[str] = []

    def fake_once(*args, **_kwargs):
        model_name = args[2]
        calls.append(model_name)
        refining = args[5] == "he"
        text = refined_text if refining else original_text
        logprob = refined_logprob if refining else -0.2
        segments = [] if logprob is None else [{
            "id": "s0001", "start": 0.0, "end": 12.0,
            "text": text, "avg_logprob": logprob, "words": [],
        }]
        return {
            "language": "he",
            "language_probability": 1.0 if refining else 0.87,
            "detected_language": "he",
            "detected_language_probability": 1.0 if refining else 0.87,
            "language_detection": {
                "source": "explicit" if refining else "script_assisted",
                "requested_language": "he" if refining else "auto",
                "ambiguous": False,
            },
            "duration": 12.0,
            "model": model_name,
            "segments": segments,
            "words": [],
            "text": text if segments else "",
        }

    monkeypatch.setattr(transcription, "cuda_available", lambda _settings=None: False)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args, **_kwargs: ("cpu", "int8"))
    monkeypatch.setattr(transcription, "_transcribe_once", fake_once)
    result = transcription._transcribe_in_process(
        Path("unused.mp4"), DummySettings(), language="auto", performance_mode="quality", duration=12.0,
    )

    assert calls == ["turbo", "ivrit-ai/whisper-large-v3-turbo-ct2"]
    assert transcript_quality_report(result)["usable_for_story"] is True
    assert result["language_probability"] == 0.87
    if refined_logprob == -0.15:
        assert result["text"] == refined_text
        assert result["model"] == "ivrit-ai/whisper-large-v3-turbo-ct2"
        assert result["hebrew_refined"] is True
        assert "hebrew_refine_warning" not in result
    else:
        assert result["text"] == original_text
        assert result["model"] == "turbo"
        assert result["language_detection"]["source"] == "script_assisted"
        assert "hebrew_refined" not in result
        expected_reason = "too_little_speech" if refined_logprob is None else "low_transcript_confidence"
        assert expected_reason in result["hebrew_refine_warning"]


def test_obviously_bad_semantic_transcript_is_rejected():
    report = transcript_quality_report({
        "language": "he",
        "language_probability": 0.52,
        "text": "טקסט " * 30,
        "segments": [
            {"start": 0.0, "end": 136.7, "text": "טקסט", "avg_logprob": -1.05},
            {"start": 140.0, "end": 145.0, "text": "ניסיון", "avg_logprob": -1.0},
        ],
    })
    assert report["usable_for_story"] is False
    assert "low_language_confidence" in report["reasons"]
    assert "low_transcript_confidence" in report["reasons"]
    assert "implausibly_long_segment" in report["reasons"]


def test_short_clean_transcript_is_valid_for_a_short_clip():
    report = transcript_quality_report({
        "language": "he",
        "language_probability": 1.0,
        "duration": 8.0,
        "text": "זה רגע קצר אבל ברור ומלא",
        "segments": [
            {"start": 0.0, "end": 8.0, "text": "זה רגע קצר אבל ברור ומלא", "avg_logprob": -0.2},
        ],
    })
    assert report["usable_for_story"] is True


def test_sparse_fragments_in_a_long_recording_are_treated_as_effectively_nonverbal():
    report = transcript_quality_report({
        "language": "fr",
        "language_probability": 0.6284,
        "duration": 2307.901,
        "text": "Fais l 'auration de combat.",
        "segments": [
            {"start": 472.07, "end": 472.63, "text": "Fais l", "avg_logprob": -0.82},
            {"start": 726.70, "end": 727.46, "text": "auration de combat", "avg_logprob": -0.83},
        ],
    })
    assert report["usable_for_story"] is False
    assert report["reasons"] == ["too_little_speech"]
    assert report["segment_count"] == 2
    assert report["speech_seconds"] == 1.32
    assert report["speech_ratio"] < 0.001


def test_sparse_game_dialogue_cannot_become_a_storyline_even_when_the_text_is_long():
    report = transcript_quality_report({
        "language": "en",
        "language_probability": 0.99,
        "duration": 2307.933,
        "text": (
            "On your six. Shell! Listen up, soldier. You will call me Gunny. "
            "Shell! Big Mag, down!"
        ),
        "segments": [
            {"start": 175.0, "end": 176.2, "text": "On your six", "avg_logprob": -0.4},
            {"start": 1888.0, "end": 1890.4, "text": "Listen up, soldier", "avg_logprob": -0.5},
            {"start": 2200.0, "end": 2202.1, "text": "Big Mag, down", "avg_logprob": -0.4},
        ],
    })
    assert report["usable_for_story"] is False
    assert report["reasons"] == ["too_little_speech"]
    assert report["speech_ratio"] < 0.01


def test_long_segment_is_split_using_real_word_timestamps():
    words = [
        {"start": float(index * 5), "end": float(index * 5 + 4), "word": f"מילה{index}", "probability": 0.95}
        for index in range(24)
    ]
    rows = _split_oversized_segments([{
        "id": "s0001", "start": 0.0, "end": 119.0, "text": "טקסט ארוך",
        "normalized": "טקסט ארוך", "words": words, "avg_logprob": -0.2, "no_speech_prob": 0.01,
    }])
    assert len(rows) >= 4
    assert [row["id"] for row in rows] == [f"s{index:04d}" for index in range(1, len(rows) + 1)]
    assert all(float(row["end"]) - float(row["start"]) <= 30.0 for row in rows)
    assert all(row["words"] for row in rows)


def test_cuda_availability_respects_an_explicit_cpu_setting(monkeypatch):
    class CPUSettings:
        ai = {"whisper_device": "cpu"}

    monkeypatch.setattr(transcription, "cuda_available", transcription.cuda_available)
    assert transcription.cuda_available(CPUSettings()) is False


def test_transcription_cancellation_stops_before_decoding_next_segment(monkeypatch):
    consumed: list[int] = []

    class SegmentIterator:
        def __init__(self):
            self.index = 0

        def __iter__(self):
            return self

        def __next__(self):
            if self.index >= 2:
                raise StopIteration
            self.index += 1
            consumed.append(self.index)
            return SimpleNamespace(
                start=(self.index - 1) * 5.0,
                end=self.index * 5.0,
                text=f"segment {self.index}",
                words=[],
                avg_logprob=-0.3,
                no_speech_prob=0.0,
            )

    class Model:
        def transcribe(self, *_args, **_kwargs):
            return SegmentIterator(), SimpleNamespace(language="en", language_probability=0.99, duration=10.0)

    monkeypatch.setattr(transcription, "_load_model", lambda *_args, **_kwargs: (Model(), "base", "cuda", "float16"))
    cancelled = False

    def progress(value, _message):
        nonlocal cancelled
        if value > 0.08:
            cancelled = True

    def cancel_check():
        if cancelled:
            raise JobCancelled("cancelled")

    with pytest.raises(JobCancelled):
        transcription._transcribe_once(
            Path("unused.mp4"), DummySettings(), "base", "cuda", "float16", None, "lite", progress, cancel_check,
        )
    assert consumed == [1]


def test_lite_uses_cuda_and_does_not_swallow_cancellation(monkeypatch):
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(transcription, "_resolve_device", lambda _settings, _mode=None: ("cuda", "float16"))

    def cancelled(*_args, **_kwargs):
        calls.append((_args[3], _args[4]))
        raise JobCancelled("cancelled")

    monkeypatch.setattr(transcription, "_transcribe_once", cancelled)
    with pytest.raises(JobCancelled):
        transcription.transcribe(Path("unused.mp4"), DummySettings(), performance_mode="lite")
    assert calls == [("cuda", "float16")]


class ChunkSettings:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.ffmpeg = "ffmpeg"
        self.ai = {
            "whisper_model": "base",
            "whisper_chunk_seconds": 20,
            "whisper_chunk_threshold_seconds": 1,
        }


class ChunkModel:
    def __init__(self):
        self.calls: list[Path] = []

    def transcribe(self, path, **_kwargs):
        self.calls.append(Path(path))
        segment = SimpleNamespace(
            start=1.0,
            end=2.0,
            text=f"unit {len(self.calls)}",
            words=[],
            avg_logprob=-0.2,
            no_speech_prob=0.0,
        )
        return iter([segment]), SimpleNamespace(language="en", language_probability=0.98, duration=20.0)


def test_long_transcription_reuses_one_model_and_bounds_each_decode_unit(monkeypatch, tmp_path):
    settings = ChunkSettings(tmp_path)
    model = ChunkModel()
    model_loads: list[int] = []
    extracted: list[tuple[float, float]] = []

    def load_model(*_args, **_kwargs):
        model_loads.append(1)
        return model, "base", "cuda", "float16"

    def extract(_source, target, _settings, start, duration, _cancel_check=None):
        extracted.append((start, duration))
        target.write_bytes(b"RIFF" + b"0" * 80)
        return target

    monkeypatch.setattr(transcription, "_load_model", load_model)
    monkeypatch.setattr(transcription, "_extract_audio_chunk", extract)
    result = transcription._transcribe_once(
        Path("long.mp4"), settings, "base", "cuda", "float16", None, "balanced", None, None, 55.0,
    )

    assert len(model_loads) == 1
    assert len(model.calls) == 3
    assert all(not path.exists() for path in model.calls)
    assert extracted == [(0.0, 20.0), (20.0, 20.0), (40.0, 15.0)]
    assert all(duration <= 20 for _, duration in extracted)
    assert [segment["start"] for segment in result["segments"]] == [1.0, 21.0, 41.0]
    assert [segment["id"] for segment in result["segments"]] == ["s0001", "s0002", "s0003"]
    assert result["chunked"] is True
    assert result["duration"] == 55.0


def test_auto_language_uses_multiple_windows_before_the_normal_chunk_threshold(monkeypatch, tmp_path):
    settings = ChunkSettings(tmp_path)
    settings.ai["whisper_chunk_threshold_seconds"] = 90
    model = ChunkModel()
    extracted: list[float] = []

    monkeypatch.setattr(
        transcription,
        "_load_model",
        lambda *_args, **_kwargs: (model, "base", "cuda", "float16"),
    )

    def extract(_source, target, _settings, start, _duration, _cancel_check=None):
        extracted.append(start)
        target.write_bytes(b"RIFF" + b"0" * 80)
        return target

    monkeypatch.setattr(transcription, "_extract_audio_chunk", extract)
    automatic = transcription._transcribe_once(
        Path("medium.mp4"), settings, "base", "cuda", "float16", None, "balanced", None, None, 50.0,
    )

    assert extracted == [0.0, 20.0, 40.0]
    assert automatic["chunked"] is True
    assert automatic["language_detection"]["observations"] == 3

    model.calls.clear()
    extracted.clear()
    explicit = transcription._transcribe_once(
        Path("medium.mp4"), settings, "base", "cuda", "float16", "en", "balanced", None, None, 50.0,
    )

    assert extracted == []
    assert model.calls == [Path("medium.mp4")]
    assert explicit["language"] == "en"
    assert explicit["language_detection"]["source"] == "explicit"


def test_long_transcription_cancels_before_extracting_the_next_unit(monkeypatch, tmp_path):
    settings = ChunkSettings(tmp_path)
    model = ChunkModel()
    extracted: list[float] = []
    cancelled = False

    monkeypatch.setattr(
        transcription,
        "_load_model",
        lambda *_args, **_kwargs: (model, "base", "cuda", "float16"),
    )

    def extract(_source, target, _settings, start, _duration, _cancel_check=None):
        extracted.append(start)
        target.write_bytes(b"RIFF" + b"0" * 80)
        return target

    def progress(_value, message):
        nonlocal cancelled
        if message == "Transcribed unit 1/3":
            cancelled = True

    def cancel_check():
        if cancelled:
            raise JobCancelled("cancelled")

    monkeypatch.setattr(transcription, "_extract_audio_chunk", extract)
    with pytest.raises(JobCancelled):
        transcription._transcribe_once(
            Path("long.mp4"), settings, "base", "cuda", "float16", None, "balanced", progress, cancel_check, 55.0,
        )
    assert extracted == [0.0]
    assert len(model.calls) == 1


def test_audio_chunk_extraction_terminates_ffmpeg_when_cancelled(monkeypatch, tmp_path):
    settings = ChunkSettings(tmp_path)

    class HangingProcess:
        def __init__(self):
            self.returncode = None
            self.terminated = False

        def poll(self):
            return self.returncode

        def communicate(self, timeout=None):
            raise transcription.subprocess.TimeoutExpired("ffmpeg", timeout)

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    process = HangingProcess()
    monkeypatch.setattr(transcription.subprocess, "Popen", lambda *_args, **_kwargs: process)
    checks = 0

    def cancel_check():
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise JobCancelled("cancelled")

    target = tmp_path / "chunk.wav"
    with pytest.raises(JobCancelled):
        transcription._extract_audio_chunk(
            Path("long.mp4"), target, settings, 0.0, 20.0, cancel_check,
        )
    assert process.terminated is True
    assert not target.exists()


def test_real_director_settings_use_the_preemptible_transcription_worker(monkeypatch, tmp_path):
    settings = SimpleNamespace(
        ai={"whisper_isolate_process": True},
        raw={"ai": {"whisper_isolate_process": True}},
        root=tmp_path,
        data_dir=tmp_path,
        cache_dir=tmp_path,
    )
    observed = {}

    def isolated(*args, **kwargs):
        observed["cancel_check"] = args[-1]
        return {"text": "isolated", "segments": []}

    monkeypatch.setattr(transcription, "_transcribe_isolated", isolated)
    cancel_check = lambda: None
    result = transcription.transcribe(
        Path("source.mp4"),
        settings,
        performance_mode="balanced",
        duration=1200,
        cancel_check=cancel_check,
    )
    assert result["text"] == "isolated"
    assert observed["cancel_check"] is cancel_check


def test_cancelling_isolated_transcription_terminates_native_worker(monkeypatch, tmp_path):
    class HangingWorker:
        def __init__(self):
            self.returncode = None
            self.terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.terminated = True
            self.returncode = -9

    worker = HangingWorker()
    monkeypatch.setattr(transcription.subprocess, "Popen", lambda *_args, **_kwargs: worker)
    settings = SimpleNamespace(
        ai={"whisper_worker_stall_seconds": 10},
        raw={"ai": {"whisper_worker_stall_seconds": 10}},
        root=tmp_path,
        data_dir=tmp_path,
        projects_dir=tmp_path,
        exports_dir=tmp_path,
        cache_dir=tmp_path,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
    )

    def cancelled():
        raise JobCancelled("cancelled")

    with pytest.raises(JobCancelled):
        transcription._run_transcription_worker(
            Path("source.mp4"), settings, "auto", None, "balanced", 1200, cancelled,
        )
    assert worker.terminated is True


def test_cuda_headroom_check_avoids_a_busy_gpu(monkeypatch):
    settings = SimpleNamespace(ai={
        "whisper_cuda_min_free_mb": {"lite": 2048, "balanced": 4096},
    })
    probe = SimpleNamespace(stdout="2500 MiB\n", returncode=0)
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: probe)
    assert transcription._cuda_has_capacity(settings, "lite") is True
    assert transcription._cuda_has_capacity(settings, "balanced") is False


def test_optional_worker_progress_write_cannot_abort_completed_transcript(monkeypatch, tmp_path):
    request_path = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    progress_path = tmp_path / "progress.json"
    request_path.write_text(
        json.dumps({
            "media_path": str(tmp_path / "source.mp4"),
            "settings": {
                "raw": {"ai": {}},
                "root": str(tmp_path),
                "data_dir": str(tmp_path),
                "projects_dir": str(tmp_path),
                "exports_dir": str(tmp_path),
                "cache_dir": str(tmp_path),
                "ffmpeg": "ffmpeg",
                "ffprobe": "ffprobe",
            },
            "language": "he",
            "performance_mode": "balanced",
            "duration": 12.0,
        }),
        encoding="utf-8",
    )
    real_write = transcription_worker.atomic_write_json

    def write_with_locked_progress(path, payload):
        if path == progress_path:
            raise PermissionError(5, "progress file temporarily locked")
        real_write(path, payload)

    def completed_transcription(*_args, **kwargs):
        kwargs["progress"](0.2, "Transcribing")
        kwargs["progress"](1.0, "Ready")
        return {
            "language": "he",
            "segments": [{"start": 0.0, "end": 2.0, "text": "שלום עולם"}],
            "text": "שלום עולם",
        }

    monkeypatch.setattr(transcription_worker, "atomic_write_json", write_with_locked_progress)
    monkeypatch.setattr(transcription_worker, "_transcribe_in_process", completed_transcription)

    assert transcription_worker.run(request_path, result_path, progress_path) == 0
    envelope = json.loads(result_path.read_text(encoding="utf-8"))
    assert envelope["ok"] is True
    assert envelope["result"]["language"] == "he"
