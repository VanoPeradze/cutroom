from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import transcription, transcription_worker


TEXT = {
    "he": "זה רגע קצר וברור שמסביר בדיוק מה קרה במשחק הזה עכשיו",
    "en": "This short clear moment explains exactly what happened in this game.",
    "ar": "هذه جملة واضحة تشرح ما حدث في اللعبة وكيف وصلنا إلى هذه النتيجة",
    "ja": "この短い説明ではゲームの中で何が起きたのかをはっきり説明しています。",
}


def _transcript(language="en", duration=3600.0, end=60.0):
    return {
        "language": language,
        "language_probability": 0.99,
        "duration": duration,
        "text": TEXT[language],
        "segments": [{"start": 0.0, "end": end, "text": TEXT[language], "avg_logprob": -0.2}],
    }


def _complete_coverage(duration=3600.0, vad_seconds=None):
    chunk = {"start": 0.0, "end": duration, "analyzed_end": duration, "status": "complete"}
    if vad_seconds is not None:
        chunk.update(vad_source="faster_whisper_silero", vad_speech_seconds=vad_seconds)
    return transcription._coverage_from_chunks(duration, [chunk], 1, "decoder_exhaustion")


@pytest.mark.parametrize("language", TEXT)
def test_unknown_opening_only_transcript_warns_without_claiming_quiet_end_is_missing(language):
    report = transcription.transcript_quality_report(_transcript(language))
    assert report["usable_for_story"] is True
    assert report["coverage_status"] == "unverified"
    assert report["warnings"] == ["unverified_transcript_coverage"]
    assert report["coverage"]["analyzed_seconds"] == 0.0
    assert report["coverage"]["transcript_last_second"] == 60.0


@pytest.mark.parametrize("language", TEXT)
def test_verified_sparse_speech_is_usable_equally_across_languages(language):
    source = _transcript(language, end=5.0)
    source["coverage"] = _complete_coverage(vad_seconds=7.0)
    report = transcription.transcript_quality_report(source)
    assert report["usable_for_story"] is True
    assert report["reasons"] == []
    assert report["warnings"] == []
    assert report["speech_ratio"] < 0.01
    assert report["coverage_status"] == "complete"
    assert report["coverage"]["analyzed_ratio"] == 1.0


@pytest.mark.parametrize("language", ["he", "en"])
@pytest.mark.parametrize("status", ["incomplete", "failed", "pending"])
def test_processed_opening_with_missing_chunks_cannot_pass_as_a_complete_story(language, status):
    source = _transcript(language)
    source["coverage"] = transcription._coverage_from_chunks(3600.0, [
        {"start": 0.0, "end": 60.0, "analyzed_end": 60.0, "status": "complete"},
        {"start": 60.0, "end": 120.0, "analyzed_end": 60.0, "status": status},
    ], 60, "chunked_decoder_exhaustion")
    report = transcription.transcript_quality_report(source)
    assert report["usable_for_story"] is False
    assert report["reasons"] == ["incomplete_transcription"]
    assert report["coverage_status"] == "incomplete"
    assert report["coverage"]["analyzed_seconds"] == 60.0
    assert report["coverage"]["completed_chunks"] == 1
    assert report["coverage"]["pending_chunks"] == 58


def test_completion_flag_cannot_override_gaps_or_failed_accounting():
    source = _transcript()
    source["coverage"] = _complete_coverage()
    source["coverage"]["analyzed_ranges"] = [{"start": 0.0, "end": 30.0}, {"start": 3500.0, "end": 3600.0}]
    report = transcription.transcript_quality_report(source)
    assert report["coverage_status"] == "incomplete"
    assert "incomplete_transcription" in report["reasons"]


@pytest.mark.parametrize("timeline_duration, offset", [(3600.0, 600.0), (10.0, -15.0)])
def test_mapped_camera_audio_keeps_source_coverage_and_pre_mapping_vad_comparison(timeline_duration, offset):
    source = _transcript(duration=30.0, end=24.0)
    source["coverage"] = _complete_coverage(duration=30.0, vad_seconds=24.0)
    source["coverage"]["chunks"][0]["transcript_seconds"] = 24.0
    source["coverage"].update(timeline_offset=offset, timeline_duration=timeline_duration)
    source["duration"] = timeline_duration
    source["timeline_offset"] = offset
    source["segments"][0].update(start=max(0.0, offset), end=min(timeline_duration, offset + 24.0))
    report = transcription.transcript_quality_report(source)
    assert report["coverage_status"] == "complete"
    assert report["coverage"]["source_duration"] == 30.0
    assert report["coverage"]["analyzed_seconds"] == 30.0
    assert report["coverage"]["vad_mismatch_chunks"] == []
    assert report["usable_for_story"] is True


def test_mapped_source_without_pre_mapping_speech_measurement_does_not_invent_vad_disagreement():
    source = _transcript(duration=5.0, end=2.0)
    source["coverage"] = _complete_coverage(duration=30.0, vad_seconds=24.0)
    source["timeline_offset"] = -22.0
    report = transcription.transcript_quality_report(source)
    assert report["coverage_status"] == "complete"
    assert report["coverage"]["vad_mismatch_chunks"] == []
    assert report["usable_for_story"] is True


@pytest.mark.parametrize("language", TEXT)
def test_large_independent_vad_disagreement_requests_recovery(language):
    source = _transcript(language, duration=30.0, end=2.0)
    source["coverage"] = _complete_coverage(duration=30.0, vad_seconds=24.0)
    report = transcription.transcript_quality_report(source)
    assert report["coverage_status"] == "complete"
    assert report["usable_for_story"] is False
    assert report["reasons"] == ["uncovered_detected_speech"]
    assert report["coverage"]["vad_speech_seconds"] == 24.0
    assert len(report["coverage"]["vad_mismatch_chunks"]) == 1


@pytest.mark.parametrize("source_name", ["rms", "transcript", "unknown"])
def test_audio_energy_and_transcript_ranges_are_not_independent_speech_evidence(source_name):
    source = _transcript(duration=30.0, end=2.0)
    source["coverage"] = _complete_coverage(duration=30.0, vad_seconds=24.0)
    source["coverage"]["chunks"][0]["vad_source"] = source_name
    report = transcription.transcript_quality_report(source)
    assert report["usable_for_story"] is True
    assert report["coverage"]["vad_speech_seconds"] is None


def test_silent_decoder_exhaustion_retains_coverage_and_measured_vad():
    class Model:
        def transcribe(self, *_args, **_kwargs):
            return iter([]), SimpleNamespace(duration=30.0, duration_after_vad=0.0)

    result = transcription._decode_with_model(Model(), Path("unused.wav"), "turbo", "cpu", "int8", "he", "quality", None, None)
    report = transcription.transcript_quality_report(result)
    assert report["coverage_status"] == "complete"
    assert report["coverage"]["vad_speech_seconds"] == 0.0
    assert report["coverage"]["analyzed_seconds"] == 30.0
    assert report["reasons"][0] == "too_little_speech"


def test_truncated_unbounded_decoder_is_incomplete_even_with_valid_text(monkeypatch):
    class Model:
        def transcribe(self, *_args, **_kwargs):
            segment = SimpleNamespace(start=0.0, end=8.0, text=TEXT["en"], words=[], avg_logprob=-0.2)
            return iter([segment]), SimpleNamespace(duration=8.0, duration_after_vad=8.0, language="en", language_probability=0.99)

    monkeypatch.setattr(transcription, "_load_model", lambda *_args: (Model(), "turbo", "cpu", "int8"))
    result = transcription._transcribe_once(Path("unused.wav"), SimpleNamespace(ai={}), "turbo", "cpu", "int8", "en", "quality", None, source_duration=30.0)
    report = transcription.transcript_quality_report(result)
    assert result["duration"] == 30.0
    assert report["coverage"]["analyzed_seconds"] == 8.0
    assert "incomplete_transcription" in report["reasons"]


def test_failed_chunk_discards_partial_text_but_retains_failed_and_pending_counts(monkeypatch, tmp_path):
    calls = []

    def extract(_source, target, _settings, start, _duration, _cancel_check):
        calls.append(start)
        if start >= 20.0:
            raise RuntimeError("decode fixture failed")
        return target

    monkeypatch.setattr(transcription, "_extract_audio_chunk", extract)
    monkeypatch.setattr(transcription, "_decode_with_model", lambda *_args: {**_transcript(duration=20.0, end=10.0), "coverage": _complete_coverage(20.0)})
    settings = SimpleNamespace(cache_dir=tmp_path)
    with pytest.raises(transcription.TranscriptionIncomplete) as raised:
        transcription._transcribe_chunked(None, Path("unused.wav"), settings, "turbo", "cpu", "int8", "en", "quality", 60.0, 20.0, None, None)
    coverage = raised.value.coverage
    assert calls == [0.0, 20.0]
    assert coverage["complete"] is False
    assert coverage["completed_chunks"] == 1
    assert coverage["failed_chunks"] == 1
    assert coverage["pending_chunks"] == 1
    assert not hasattr(raised.value, "text")


def test_silent_later_chunks_count_as_analyzed_without_extending_speech(monkeypatch, tmp_path):
    calls = []

    def decode(*_args):
        calls.append(1)
        source = _transcript(duration=20.0, end=5.0)
        if len(calls) > 1:
            source.update(text="", segments=[])
        source["coverage"] = _complete_coverage(20.0, vad_seconds=5.0 if len(calls) == 1 else 0.0)
        return source

    monkeypatch.setattr(transcription, "_extract_audio_chunk", lambda _source, target, *_args: target)
    monkeypatch.setattr(transcription, "_decode_with_model", decode)
    result = transcription._transcribe_chunked(None, Path("unused.wav"), SimpleNamespace(cache_dir=tmp_path), "turbo", "cpu", "int8", "en", "quality", 60.0, 20.0, None, None)
    result["language_probability"] = 0.99
    report = transcription.transcript_quality_report(result)
    assert result["coverage"]["completed_chunks"] == 3
    assert report["coverage_status"] == "complete"
    assert report["coverage"]["analyzed_seconds"] == 60.0
    assert report["coverage"]["transcript_last_second"] == 5.0
    assert report["usable_for_story"] is True


def _settings():
    ai = {
        "whisper_device": "auto", "whisper_compute_type": "auto",
        "whisper_models": {"lite": "base", "balanced": "small", "quality": "turbo"},
        "hebrew_whisper_model": "local-hebrew-quality", "whisper_cpu_lite_threshold_seconds": 600,
    }
    return SimpleNamespace(ai=ai, raw={"ai": ai})


@pytest.mark.parametrize("language, expected_model", [("he", "local-hebrew-quality"), ("en", "turbo")])
@pytest.mark.parametrize("fallback", ["headroom", "decode_error"])
def test_explicit_quality_keeps_requested_model_on_cpu(monkeypatch, language, expected_model, fallback):
    calls = []
    monkeypatch.setattr(transcription, "cuda_available", lambda *_args: True)
    preferred = ("cpu", "int8") if fallback == "headroom" else ("cuda", "float16")
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: preferred)

    def once(_path, _settings, model, device, compute, _language, mode, *_args):
        calls.append((model, device, mode))
        if device == "cuda":
            raise RuntimeError("fixture CUDA failure")
        return {**_transcript(language), "model": model, "device": device, "compute_type": compute}

    monkeypatch.setattr(transcription, "_transcribe_once", once)
    result = transcription._transcribe_in_process(Path("unused.wav"), _settings(), language, performance_mode="quality", duration=3600.0)
    assert calls[-1] == (expected_model, "cpu", "quality")
    assert result["model"] == result["requested_model"] == expected_model
    assert result["performance_mode"] == result["requested_performance_mode"] == "quality"
    assert result["requested_device"] == "auto"
    assert result["execution"]["actual_device"] == "cpu"
    assert result["resource_fallback"] == ("cuda_headroom" if fallback == "headroom" else "device_error")


@pytest.mark.parametrize("mode, model", [("quality", "turbo"), ("balanced", "small"), ("lite", "base")])
def test_worker_stall_keeps_explicit_mode_and_records_actual_cpu_fallback(monkeypatch, mode, model):
    calls = []

    def worker(*args, **kwargs):
        calls.append((args[4], copy.deepcopy(kwargs)))
        if len(calls) == 1:
            raise transcription.TranscriptionWorkerStalled("fixture stall")
        return {"model": model, "device": "cpu", "performance_mode": args[4], "execution": {"actual_device": "cpu", "actual_model": model}}

    monkeypatch.setattr(transcription, "_run_transcription_worker", worker)
    result = transcription._transcribe_isolated(Path("unused.wav"), _settings(), "en", None, mode, 3600.0, None)
    assert [call[0] for call in calls] == [mode, mode]
    assert calls[1][1]["raw_override"]["ai"]["whisper_device"] == "cpu"
    assert result["resource_fallback"] == "worker_stall"
    assert result["requested_model"] == model
    assert result["requested_performance_mode"] == mode
    assert result["execution"]["fallback_detail"] == "fixture stall"


def test_worker_failure_envelope_preserves_coverage(monkeypatch, tmp_path):
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(json.dumps({"settings": {"unused": True}, "media_path": "unused.wav"}), encoding="utf-8")
    monkeypatch.setattr(transcription_worker, "_settings_from_payload", lambda _payload: _settings())
    coverage = {"complete": False, "expected_chunks": 3, "completed_chunks": 1, "failed_chunks": 1, "pending_chunks": 1}

    def failed(*_args, **_kwargs):
        raise transcription.TranscriptionIncomplete("fixture failure", coverage)

    monkeypatch.setattr(transcription_worker, "_transcribe_in_process", failed)
    assert transcription_worker.run(request, result, tmp_path / "progress.json") == 1
    envelope = json.loads(result.read_text(encoding="utf-8"))
    assert envelope["ok"] is False
    assert envelope["coverage"] == coverage
    assert "result" not in envelope
