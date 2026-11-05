"""Completion authority for local story responses; all transport is synthetic."""

from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from cutroom import cloud_ai, intelligence


SETTINGS = SimpleNamespace(ai={"ollama_url": "http://127.0.0.1:11434"})
NO_FIT = {"verdict": "no_fit", "reason": "source_order", "missing_purposes": ["self_contained_passage"]}


@pytest.fixture(autouse=True)
def synthetic_transport_only(monkeypatch):
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: False)

    def forbidden(*_args, **_kwargs):
        pytest.fail("A completion test attempted real local transport")

    monkeypatch.setattr(intelligence, "open_ollama", forbidden)


def payload(*, single_attempt=True):
    return {
        "model": "synthetic-model", "stream": False, "format": {"type": "object"},
        "options": {"num_ctx": 8192, "num_predict": 1200, "temperature": 0.04},
        "messages": [{"role": "user", "content": "Return the synthetic decision."}],
        "_single_attempt": single_attempt, "_reject_duplicate_keys": True,
    }


def envelope(decision, reason="stop"):
    return {"message": {"content": json.dumps(decision)}, "done": True, "done_reason": reason}


def install_responses(monkeypatch, bodies, *, streaming):
    pending = iter(bodies)
    sent = []

    def respond(request, **_kwargs):
        sent.append(json.loads(request.data.decode("utf-8")))
        body = next(pending)
        if streaming:
            chunks = body if isinstance(body, list) else [body]
            data = b"".join(json.dumps(chunk).encode("utf-8") + b"\n" for chunk in chunks)
        else:
            data = json.dumps(body).encode("utf-8")
        return io.BytesIO(data)

    monkeypatch.setattr(intelligence, "open_ollama", respond)
    return sent


def call(request, *, streaming):
    return intelligence._call_ollama_strict(
        SETTINGS, request, cancel_check=(lambda: None) if streaming else None,
    )


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("decision", [{"verdict": "fit"}, NO_FIT])
def test_completed_stop_preserves_decision_and_input(monkeypatch, streaming, decision):
    sent = install_responses(monkeypatch, [envelope(decision)], streaming=streaming)
    request = payload()
    original = copy.deepcopy(request)
    assert call(request, streaming=streaming) == decision
    assert len(sent) == 1
    assert request == original
    assert not any(key.startswith("_") for key in sent[0])


@pytest.mark.parametrize("decision", [{"verdict": "fit"}, NO_FIT, None])
def test_stream_eof_without_done_is_technical_failure_even_with_valid_json(monkeypatch, decision):
    chunks = [] if decision is None else [{"message": {"content": json.dumps(decision)}, "done": False}]
    sent = install_responses(monkeypatch, [chunks], streaming=True)
    with pytest.raises(intelligence.StoryAIUnavailableError, match="before completion"):
        call(payload(single_attempt=False), streaming=True)
    assert len(sent) == 1  # Transport failure does not trigger a generation retry.


@pytest.mark.parametrize("decision", [{"verdict": "fit"}, NO_FIT])
def test_nonstream_explicit_incomplete_rejects_valid_json_without_retry(monkeypatch, decision):
    body = {**envelope(decision), "done": False}
    sent = install_responses(monkeypatch, [body], streaming=False)
    with pytest.raises(intelligence.StoryAIUnavailableError, match="before completion"):
        call(payload(single_attempt=False), streaming=False)
    assert len(sent) == 1


def test_nonstream_legacy_envelope_without_done_remains_compatible(monkeypatch):
    body = envelope(NO_FIT)
    body.pop("done")
    sent = install_responses(monkeypatch, [body], streaming=False)
    assert call(payload(), streaming=False) == NO_FIT
    assert len(sent) == 1


@pytest.mark.parametrize("streaming", [False, True])
def test_explicit_error_is_technical_failure_and_never_accepts_json(monkeypatch, streaming):
    error = {"error": "synthetic generation failure", **envelope(NO_FIT)}
    body = [{"message": {"content": json.dumps(NO_FIT)}, "done": False}, {"error": "synthetic failure"}] if streaming else error
    sent = install_responses(monkeypatch, [body], streaming=streaming)
    with pytest.raises(intelligence.StoryAIUnavailableError, match="generation error"):
        call(payload(single_attempt=False), streaming=streaming)
    assert len(sent) == 1


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("decision", [{"verdict": "fit"}, NO_FIT])
def test_single_attempt_rejects_complete_json_at_length_without_retry(monkeypatch, streaming, decision):
    sent = install_responses(monkeypatch, [envelope(decision, "length")], streaming=streaming)
    request = payload()
    original = copy.deepcopy(request)
    with pytest.raises(intelligence.StoryResponseLimitError, match="output budget"):
        call(request, streaming=streaming)
    assert len(sent) == 1
    assert request == original


@pytest.mark.parametrize("streaming", [False, True])
def test_length_uses_only_existing_bounded_retry_before_accepting_stop(monkeypatch, streaming):
    success = {"verdict": "fit", "source": "synthetic-complete-decision"}
    sent = install_responses(monkeypatch, [envelope(NO_FIT, "length"), envelope(success)], streaming=streaming)
    request = payload(single_attempt=False)
    original = copy.deepcopy(request)
    assert call(request, streaming=streaming) == success
    assert len(sent) == 2
    assert sent[0]["options"]["num_predict"] == 1200
    assert sent[1]["options"]["num_predict"] == 2400
    assert request == original


@pytest.mark.parametrize("streaming", [False, True])
def test_both_length_responses_fail_after_two_attempts(monkeypatch, streaming):
    sent = install_responses(monkeypatch, [envelope(NO_FIT, "length")] * 2, streaming=streaming)
    with pytest.raises(intelligence.StoryResponseLimitError, match="output budget"):
        call(payload(single_attempt=False), streaming=streaming)
    assert len(sent) == 2
