from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import cloud_ai, transcription
from cutroom.jobs import JobCancelled


MIXED_TEXT = "אני מסביר עכשיו איך עובדים עם OpenAI API בתוך הפרויקט שלנו"


def _decoded(*, text=MIXED_TEXT, logprob=-1.1, duration=20.0, language="he"):
    words = [{"start": 1.0, "end": 1.5, "word": "OpenAI", "probability": 0.94}]
    segment = {"id": "s0001", "start": 1.0, "end": 8.0, "text": text,
               "avg_logprob": logprob, "words": words}
    return {"text": text, "language": language, "language_probability": 0.92,
            "duration": duration, "segments": [segment], "words": words,
            "coverage": transcription._coverage_from_chunks(duration, [
                {"start": 0.0, "end": duration, "analyzed_end": duration, "status": "complete"},
            ], 1, "decoder_exhaustion")}


def _retry(monkeypatch, *, mode="balanced", language=None, originals=None, candidates=None, units=1):
    state = transcription._new_quality_recovery()
    calls = []
    originals = originals or [_decoded() for _ in range(units)]
    candidates = candidates or [_decoded(logprob=-0.2) for _ in range(units)]

    def decode(*args, **kwargs):
        calls.append((args, kwargs))
        return copy.deepcopy((candidates if kwargs.get("recovery") else originals).pop(0))

    monkeypatch.setattr(transcription, "_decode_with_model", decode)
    results = [transcription._decode_with_quality_retry(
        object(), Path("speech.wav"), "small", "cpu", "int8", language, mode, None, None,
        state, index * 20.0,
    ) for index in range(units)]
    return results, state, calls


@pytest.mark.parametrize("language", [None, "en", "he"])
def test_first_pass_hints_only_explicit_hebrew_and_always_transcribes(language):
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(kwargs)
            return iter([]), SimpleNamespace(duration=8.0, language=language or "en", language_probability=0.9)

    transcription._decode_with_model(Model(), Path("speech.wav"), "small", "cpu", "int8", language,
                                     "balanced", None, None)
    assert calls[0]["task"] == "transcribe"
    assert bool(calls[0]["initial_prompt"]) is (language == "he")
    if language == "he":
        assert "עברית" in calls[0]["initial_prompt"]
        assert "English" in calls[0]["initial_prompt"]


def test_grounded_auto_retry_retains_language_auto_and_replaces_whole_unit(monkeypatch):
    results, state, calls = _retry(monkeypatch)
    assert len(calls) == 2
    assert calls[1][0][5] is None
    assert calls[1][1] == {"bilingual_hint": True, "recovery": True}
    assert results[0]["text"] == MIXED_TEXT
    assert len(results[0]["segments"]) == 1
    assert results[0]["segments"][0]["avg_logprob"] == -0.2
    assert state["attempted_units"] == state["accepted_units"] == 1
    assert state["retried_audio_seconds"] == 20.0


def test_recovery_decode_is_deterministic_and_does_not_condition_on_previous_text():
    calls = []

    class Model:
        def transcribe(self, _path, **kwargs):
            calls.append(kwargs)
            return iter([]), SimpleNamespace(duration=8.0, language="he", language_probability=0.9)

    transcription._decode_with_model(Model(), Path("speech.wav"), "small", "cpu", "int8", None,
                                     "quality", None, None, bilingual_hint=True, recovery=True)
    assert calls[0]["task"] == "transcribe"
    assert calls[0]["temperature"] == 0.0
    assert calls[0]["beam_size"] == 5
    assert calls[0]["condition_on_previous_text"] is False
    assert calls[0]["language"] is None


def test_chunk_recovery_preserves_source_timing_and_does_not_duplicate_rows(monkeypatch, tmp_path):
    settings = SimpleNamespace(ai={"whisper_chunk_seconds": 20, "whisper_chunk_threshold_seconds": 20},
                               cache_dir=tmp_path)
    calls = []
    model = object()
    monkeypatch.setattr(transcription, "_load_model", lambda *_args: (model, "small", "cpu", "int8"))
    monkeypatch.setattr(transcription, "_extract_audio_chunk", lambda *_args: None)

    def decode(*args, **kwargs):
        calls.append((args[0], kwargs))
        return _decoded(logprob=-0.2 if kwargs.get("recovery") else -1.1)

    monkeypatch.setattr(transcription, "_decode_with_model", decode)
    result = transcription._transcribe_once(Path("speech.wav"), settings, "small", "cpu", "int8", "he",
                                           "balanced", None, source_duration=60.0)
    assert len(calls) == 5
    assert all(call[0] is model for call in calls)
    assert [row["start"] for row in result["segments"]] == [1.0, 21.0, 41.0]
    assert [row["end"] for row in result["segments"]] == [8.0, 28.0, 48.0]
    assert [row["start"] for row in result["words"]] == [1.0, 21.0, 41.0]
    assert [row["start"] for row in result["quality_recovery"]["units"]] == [0.0, 20.0]
    assert result["coverage"]["complete"] is True
    assert result["quality_recovery"]["accepted_units"] == 2


def test_budget_is_shared_between_units_not_reset_for_every_chunk(monkeypatch):
    results, state, calls = _retry(monkeypatch, units=6)
    assert len(calls) == 8
    assert state["attempted_units"] == state["accepted_units"] == 2
    assert state["retried_audio_seconds"] == 40.0
    assert len(state["units"]) == 2
    assert results[-1]["segments"][0]["avg_logprob"] == -1.1


def test_audio_budget_also_limits_two_thirty_second_units(monkeypatch):
    _, state, calls = _retry(monkeypatch, units=2,
                             originals=[_decoded(duration=30) for _ in range(2)],
                             candidates=[_decoded(logprob=-0.2, duration=30)])
    assert len(calls) == 3
    assert state["attempted_units"] == 1
    assert state["retried_audio_seconds"] == 30


@pytest.mark.parametrize("mode,language,original", [
    ("lite", "he", _decoded()),
    ("balanced", "en", _decoded()),
    ("quality", None, _decoded(language="yi")),
    ("balanced", None, _decoded(text="A completely English sentence", language="en")),
    ("balanced", None, _decoded(logprob=-0.2)),
    ("quality", "he", _decoded(duration=31.0)),
])
def test_fast_path_does_not_retry_unrelated_good_or_unbounded_audio(monkeypatch, mode, language, original):
    _, state, calls = _retry(monkeypatch, mode=mode, language=language, originals=[original])
    assert len(calls) == 1
    assert state["attempted_units"] == 0


@pytest.mark.parametrize("change,reason", [
    (lambda row: row.update(text="אני מסביר עכשיו איך עובדים עם אופן איי בתוך הפרויקט שלנו"), "english_terms_not_preserved"),
    (lambda row: row["segments"][0].update(start=-0.2), "invalid_candidate_timing"),
    (lambda row: row["segments"].append(copy.deepcopy(row["segments"][0])), "invalid_candidate_timing"),
    (lambda row: row["segments"][0]["words"][0].update(end=30.0), "invalid_candidate_timing"),
    (lambda row: row.update(duration=18.0), "duration_mismatch"),
    (lambda row: row["segments"][0].update(end=2.0), "speech_timing_not_preserved"),
    (lambda row: row["coverage"].update(complete=False), "incomplete_candidate"),
    (lambda row: row["segments"][0].update(avg_logprob=-1.03), "confidence_not_improved"),
])
def test_recovery_keeps_original_when_safety_or_confidence_check_fails(monkeypatch, change, reason):
    candidate = _decoded(logprob=-0.2)
    change(candidate)
    results, state, _ = _retry(monkeypatch, candidates=[candidate])
    assert results[0]["segments"][0]["avg_logprob"] == -1.1
    assert results[0]["text"] == MIXED_TEXT
    assert state["accepted_units"] == 0
    assert state["units"][0]["reason"] == reason


@pytest.mark.parametrize("exception", [RuntimeError("native decode failed"), JobCancelled("cancelled")])
def test_retry_failure_keeps_completed_audio_and_cancellation_propagates(monkeypatch, exception):
    def decode(*_args, **kwargs):
        if kwargs.get("recovery"):
            raise exception
        return _decoded()

    monkeypatch.setattr(transcription, "_decode_with_model", decode)
    state = transcription._new_quality_recovery()
    args = (None, Path("speech.wav"), "small", "cpu", "int8", "he", "balanced", None, None, state)
    if isinstance(exception, JobCancelled):
        with pytest.raises(JobCancelled):
            transcription._decode_with_quality_retry(*args)
    else:
        result = transcription._decode_with_quality_retry(*args)
        assert result["text"] == MIXED_TEXT
        assert state["units"][0]["reason"] == "retry_failed"


def test_localized_low_confidence_is_visible_even_when_aggregate_story_gate_passes():
    transcript = _decoded(logprob=-0.2)
    transcript["segments"].append({"id": "s0002", "start": 9.0, "end": 10.0,
                                  "text": "מונח", "avg_logprob": -1.2,
                                  "words": [{"word": "מונח", "probability": 0.2}]})
    report = transcription.transcript_quality_report(transcript)
    assert report["usable_for_story"] is True
    assert report["needs_review"] is True
    assert report["warnings"] == ["low_confidence_segments"]
    assert report["review_segment_count"] == 1
    assert report["review_segments"][0]["segment_id"] == "s0002"
    assert report["review_segments"][0]["start"] == 9.0
    assert report["review_segments"][0]["reasons"] == ["low_segment_confidence", "low_word_confidence"]


def test_warning_payload_is_bounded_and_unknown_confidence_is_not_reported_as_bad():
    transcript = _decoded()
    transcript["segments"] = [dict(transcript["segments"][0], id=f"s{i}") for i in range(130)]
    report = transcription.transcript_quality_report(transcript)
    assert report["review_segment_count"] == 130
    assert len(report["review_segments"]) == 100
    unknown = transcription._segment_confidence({"avg_logprob": float("nan"), "words": [
        {"word": "API"}, {"probability": float("inf")}, {"probability": -1},
    ]})
    assert unknown["reasons"] == []
    assert unknown["avg_logprob"] is None
    assert unknown["minimum_word_probability"] is None


def test_enabled_cloud_is_called_once_without_local_recovery(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: True)
    monkeypatch.setattr(cloud_ai, "transcribe_cloud", lambda *args: calls.append(args) or {"text": "cloud"})
    monkeypatch.setattr(transcription, "_transcribe_in_process", lambda *_args: pytest.fail("unexpected local pass"))
    result = transcription.transcribe(Path("speech.wav"), SimpleNamespace(ai={}))
    assert result == {"text": "cloud"}
    assert len(calls) == 1


def test_existing_hebrew_model_refinement_cannot_transliterate_trusted_english(monkeypatch):
    original = _decoded(logprob=-0.2)
    original["model"] = "turbo"
    candidate = _decoded(text="אני מסביר עכשיו איך עובדים עם אופן איי בתוך הפרויקט שלנו", logprob=-0.1)
    responses = iter([original, candidate])
    monkeypatch.setattr(transcription, "cuda_available", lambda _settings: False)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cpu", "int8"))
    monkeypatch.setattr(transcription, "_transcribe_once", lambda *_args, **_kwargs: next(responses))
    settings = SimpleNamespace(ai={"whisper_device": "cpu", "whisper_models": {"quality": "turbo"},
                                   "hebrew_whisper_model": "local-hebrew-model"})
    result = transcription._transcribe_in_process(Path("speech.wav"), settings, performance_mode="quality")
    assert result["text"] == MIXED_TEXT
    assert result["model"] == "turbo"
    assert "English terms" in result["hebrew_refine_warning"]
