"""Offline regression coverage for opt-in cached Hebrew Auto refinement."""
from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import local_models, transcription
from cutroom.jobs import JobCancelled

HEBREW_MODEL = "ivrit-ai/whisper-large-v3-turbo-ct2"
SPEECH = "\u05d0\u05e0\u05d7\u05e0\u05d5 \u05de\u05e6\u05dc\u05de\u05d9\u05dd \u05d4\u05d9\u05d5\u05dd \u05e1\u05e8\u05d8\u05d5\u05df \u05d7\u05d3\u05e9 \u05e2\u05dd Sony \u05d5\u05de\u05e1\u05d1\u05d9\u05e8\u05d9\u05dd \u05d0\u05d9\u05da \u05dc\u05e2\u05e8\u05d5\u05da \u05d0\u05d5\u05ea\u05d5."


@pytest.fixture
def settings():
    return SimpleNamespace(ai={
        "whisper_model": "base",
        "whisper_models": {"lite": "base", "balanced": "small", "quality": "turbo"},
        "hebrew_whisper_model": HEBREW_MODEL,
        "whisper_device": "auto",
        "whisper_compute_type": "auto",
    })


def result(model="small"):
    return {
        "model": model, "device": "cuda", "compute_type": "float16",
        "language": "he", "language_probability": 0.87,
        "detected_language": "he", "detected_language_probability": 0.87,
        "language_detection": {"source": "consensus", "ambiguous": False},
        "duration": 10.0, "text": SPEECH, "words": [],
        "coverage": {
            "complete": True, "source_duration": 10.0,
            "expected_chunks": 1, "completed_chunks": 1,
            "analyzed_ranges": [{"start": 0.0, "end": 10.0}],
        },
        "segments": [{"start": 1.0, "end": 9.0, "text": SPEECH, "words": [], "avg_logprob": -0.2}],
    }


@pytest.fixture
def gpu(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("CUDA_DEVICE_ORDER", raising=False)
    monkeypatch.delenv("CUTROOM_FAKE_TRANSCRIPT", raising=False)
    monkeypatch.setattr(transcription, "cuda_available", lambda _settings=None: True)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cuda", "float16"))
    monkeypatch.setattr(local_models, "speech_installed", lambda model: model == HEBREW_MODEL)
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="12000\n"))


def run_decode(monkeypatch, settings, original=None, candidate=None, *, mode="auto", duration=10.0, language=None):
    calls = []
    original = result() if original is None else original
    candidate = result(HEBREW_MODEL) if candidate is None else candidate

    def once(*args, **kwargs):
        calls.append((args, kwargs))
        value = original if len(calls) == 1 else candidate
        if isinstance(value, BaseException):
            raise value
        return copy.deepcopy(value)

    monkeypatch.setattr(transcription, "_transcribe_once", once)
    value = transcription._transcribe_in_process(
        Path("synthetic-no-audio.wav"), settings, language=language,
        performance_mode=mode, duration=duration,
    )
    return value, calls


def test_cached_hebrew_refines_auto_even_without_generic_turbo(monkeypatch, settings, gpu):
    value, calls = run_decode(monkeypatch, settings)
    assert [call[0][2] for call in calls] == ["small", HEBREW_MODEL]
    assert calls[1][1]["local_files_only"] is True
    assert value["hebrew_refined"] is True
    assert value["language_probability"] == value["detected_language_probability"] == 0.87
    assert value["language_detection"]["source"] == "auto_refined"
    assert value["requested_performance_mode"] == "auto"


@pytest.mark.parametrize("mode,device,expected", [
    ("lite", "cuda", "base"), ("lite", "cpu", "base"),
    ("auto", "cpu", "small"),
])
def test_lightweight_modes_and_cpu_do_not_refine(monkeypatch, settings, gpu, mode, device, expected):
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: (device, "int8" if device == "cpu" else "float16"))
    value, calls = run_decode(monkeypatch, settings, mode=mode)
    assert len(calls) == 1 and calls[0][0][2] == expected
    assert not value.get("hebrew_refined")


@pytest.mark.parametrize("update,duration,device,limit", [
    ({"language": "en"}, 10, "cuda", 3600),
    ({"language_probability": 0.61}, 10, "cuda", 3600),
    ({"language_probability": float("nan")}, 10, "cuda", 3600),
    ({"language_probability": "invalid"}, 10, "cuda", 3600),
    ({"language_detection": {"ambiguous": True}}, 10, "cuda", 3600),
    ({}, 3601, "cuda", 3600),
    ({"duration": 0}, 0, "cuda", 3600),
    ({"duration": -1}, 0, "cuda", 3600),
    ({"duration": float("nan")}, 0, "cuda", 3600),
    ({}, 10, "cpu", 3600),
    ({}, 10, "cuda", 0),
    ({}, 10, "cuda", "invalid"),
    ({}, 10, "cuda", float("inf")),
])
def test_optional_refinement_requires_bounded_confident_gpu_input(settings, gpu, update, duration, device, limit):
    original = result()
    original.update(update)
    settings.ai["hebrew_auto_gpu_max_seconds"] = limit
    assert not transcription._auto_hebrew_refinement_ready(settings, original, device, duration)


def test_decoded_duration_can_supply_initially_unknown_source_length(monkeypatch, settings, gpu):
    value, calls = run_decode(monkeypatch, settings, duration=0)
    assert len(calls) == 2 and value["hebrew_refined"]


def test_uncached_hebrew_model_is_not_requested(monkeypatch, settings, gpu):
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: False)
    value, calls = run_decode(monkeypatch, settings)
    assert len(calls) == 1 and not value.get("hebrew_refined")


@pytest.mark.parametrize("stdout,returncode,expected", [
    ("12000\n", 0, True), ("6144\n", 0, True), ("6143\n", 0, False),
    ("", 0, False), ("N/A\n", 0, False), ("nan\n", 0, False),
    ("inf\n", 0, False), ("12000 MiB\n", 0, False), ("12000\n", 1, False),
    ("1000\n12000\n", 0, False), ("12000\n12000\n", 0, False),
])
def test_optional_gpu_measurement_fails_closed(monkeypatch, settings, gpu, stdout, returncode, expected):
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=stdout, returncode=returncode))
    assert transcription._cuda_has_capacity(settings, "quality", require_measurement=True) is expected


@pytest.mark.parametrize("error", [OSError("nvidia-smi missing"), subprocess.TimeoutExpired("nvidia-smi", 2)])
def test_measurement_errors_skip_optional_refinement_without_changing_generic_policy(monkeypatch, settings, gpu, error):
    def fail(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(transcription.subprocess, "run", fail)
    assert not transcription._cuda_has_capacity(settings, "quality", require_measurement=True)
    assert transcription._cuda_has_capacity(settings, "quality")


@pytest.mark.parametrize("variable", ["CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"])
def test_remapped_cuda_devices_skip_optional_refinement(monkeypatch, settings, gpu, variable):
    monkeypatch.setenv(variable, "0")
    assert not transcription._cuda_has_capacity(settings, "quality", require_measurement=True)


@pytest.mark.parametrize("threshold", [0, -1, float("inf"), float("nan")])
def test_disabled_or_nonfinite_threshold_does_not_authorize_optional_refinement(settings, gpu, threshold):
    settings.ai["whisper_cuda_min_free_mb"] = threshold
    assert not transcription._cuda_has_capacity(settings, "quality", require_measurement=True)


@pytest.mark.parametrize("failure", [
    "incomplete", "duration", "empty", "negative_start", "overrun",
    "invalid_word", "shifted_speech", "english", "poor_quality",
])
def test_bad_auto_candidates_keep_completed_original(monkeypatch, settings, gpu, failure):
    candidate = result(HEBREW_MODEL)
    if failure == "incomplete":
        candidate["coverage"]["complete"] = False
    elif failure == "duration":
        candidate["duration"] = 14
    elif failure == "empty":
        candidate["text"], candidate["segments"] = "", []
    elif failure == "negative_start":
        candidate["segments"][0]["start"] = -1
    elif failure == "overrun":
        candidate["segments"][0]["end"] = 14
    elif failure == "invalid_word":
        candidate["segments"][0]["words"] = [{"start": 8, "end": 14, "word": "Sony", "probability": 0.9}]
    elif failure == "shifted_speech":
        candidate["segments"][0]["start"], candidate["segments"][0]["end"] = 6, 10
    elif failure == "english":
        candidate["text"] = candidate["segments"][0]["text"] = SPEECH.replace("Sony", "\u05e1\u05d5\u05e0\u05d9")
    elif failure == "poor_quality":
        candidate["segments"][0]["avg_logprob"] = -1.5
    value, calls = run_decode(monkeypatch, settings, candidate=candidate)
    assert len(calls) == 2
    assert value["model"] == "small" and value["text"] == SPEECH
    assert value.get("hebrew_refine_warning") and not value.get("hebrew_refined")


def test_poor_candidate_does_not_replace_even_a_weak_original(monkeypatch, settings, gpu):
    original, candidate = result(), result(HEBREW_MODEL)
    original["segments"][0]["avg_logprob"] = candidate["segments"][0]["avg_logprob"] = -1.5
    value, _ = run_decode(monkeypatch, settings, original, candidate)
    assert value["model"] == "small" and value.get("hebrew_refine_warning")


def test_refinement_load_error_keeps_completed_original(monkeypatch, settings, gpu):
    value, calls = run_decode(monkeypatch, settings, candidate=RuntimeError("cached model incomplete"))
    assert len(calls) == 2 and value["model"] == "small"
    assert "cached model incomplete" in value["hebrew_refine_warning"]


def test_refinement_cancellation_is_not_swallowed(monkeypatch, settings, gpu):
    with pytest.raises(JobCancelled):
        run_decode(monkeypatch, settings, candidate=JobCancelled("cancelled"))


@pytest.mark.parametrize("language,model", [(None, "turbo"), ("he", HEBREW_MODEL), ("en", "turbo")])
def test_initial_auto_quality_load_is_also_cache_only(monkeypatch, settings, gpu, language, model):
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: True)
    original = result(model)
    original["language"] = "en" if language != "he" else "he"
    value, calls = run_decode(monkeypatch, settings, original=original, language=language)
    assert calls[0][0][2] == model
    assert calls[0][1]["local_files_only"] is True


@pytest.mark.parametrize("mode", ["balanced", "quality"])
def test_explicit_profiles_refinement_requires_cached_hebrew_model(monkeypatch, settings, gpu, mode):
    value, calls = run_decode(monkeypatch, settings, mode=mode)
    assert len(calls) == 2 and value["hebrew_refined"]
    assert "local_files_only" not in calls[0][1]
    assert calls[1][1]["local_files_only"] is True


@pytest.mark.parametrize("requested,configured,expected", [(True, False, True), (False, True, True), (False, False, False)])
def test_loader_passes_offline_flag_to_faster_whisper(monkeypatch, settings, requested, configured, expected):
    calls = []
    def model(name, **kwargs):
        calls.append((name, kwargs))
        return object()
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=model))
    monkeypatch.setattr(transcription, "_MODEL_CACHE", {})
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: True)
    settings.ai["whisper_local_files_only"] = configured
    transcription._load_model(settings, "cpu", "int8", "synthetic-model", local_files_only=requested)
    assert calls[0][1].get("local_files_only", False) is expected


def test_transcribe_once_forwards_cache_only_boundary(monkeypatch, settings):
    calls = []
    def load(*args, **kwargs):
        calls.append(kwargs)
        return object(), "synthetic", "cpu", "int8"
    monkeypatch.setattr(transcription, "_load_model", load)
    monkeypatch.setattr(transcription, "_chunk_policy", lambda *_args: (False, 30))
    monkeypatch.setattr(transcription, "_decode_with_quality_retry", lambda *_args: result())
    transcription._transcribe_once(Path("synthetic.wav"), settings, "synthetic", "cpu", "int8", "he", "quality", None, local_files_only=True)
    assert calls == [{"local_files_only": True}]
