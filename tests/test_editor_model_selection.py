from __future__ import annotations

import pytest

from cutroom import intelligence


class Settings:
    ai = {"enabled": True, "editor_model": "qwen3.5:4b",
          "editor_quality_model": "qwen3.5:9b", "editor_lite_model": "qwen3.5:2b",
          "editor_fallback_models": ["qwen3:8b"], "performance_mode": "auto"}


@pytest.mark.parametrize("mode,requested", [("quality", "qwen3.5:9b"), ("lite", "qwen3.5:2b")])
def test_installed_fallback_is_usable_but_identified_as_different_model(monkeypatch, mode, requested):
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (True, {"qwen3.5:4b"}))
    status = intelligence.story_ai_status(Settings(), {"performance_mode": mode})
    assert status["ready"] is True
    assert status["requested_model"] == requested
    assert status["requested_model_installed"] is False
    assert status["selected_model"] == "qwen3.5:4b"
    assert status["using_fallback"] is True
    assert status["fallback_reason"] == "requested_model_missing"
    assert requested in status["message"] and "qwen3.5:4b" in status["message"]
    assert "not installed" in status["message"]
    assert status["recommended_model"] == requested
    assert intelligence._select_editor_model(Settings(), {"performance_mode": mode}) == "qwen3.5:4b"


def test_requested_installed_model_is_selected_without_fallback(monkeypatch):
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (True, {"qwen3.5:4b", "qwen3.5:9b"}))
    status = intelligence.story_ai_status(Settings(), {"performance_mode": "quality"})
    assert status["requested_model_installed"] is True
    assert status["selected_model"] == "qwen3.5:9b"
    assert status["using_fallback"] is False
    assert status["fallback_reason"] is None


@pytest.mark.parametrize("available,installed,reason", [
    (True, set(), "story_model_missing"),
    (True, {"unconfigured-model:4b"}, "story_model_missing"),
    (False, set(), "ollama_unavailable"),
])
def test_no_available_configured_model_never_sends_request_to_missing_model(monkeypatch, available, installed, reason):
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (available, installed))
    monkeypatch.setattr(intelligence, "_call_ollama", lambda *_: pytest.fail("Missing model must not receive an inference request"))
    with pytest.raises(intelligence.StoryAIUnavailableError):
        intelligence._ollama_chat(Settings(), [{"id": "s1", "start": 0, "end": 8,
                                               "text": "An actual transcript passage."}],
                                  {"goal": "youtube", "performance_mode": "quality"})
    status = intelligence.story_ai_status(Settings(), {"performance_mode": "quality"})
    assert status["ready"] is False
    assert status["selected_model"] is None
    assert status["requested_model"] == "qwen3.5:9b"
    assert status["recommended_model"] == "qwen3.5:9b"
    assert status["reason"] == reason


def test_disabled_ai_has_no_selected_model_even_if_installed(monkeypatch):
    class Disabled:
        ai = {**Settings.ai, "enabled": False}

    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: pytest.fail("Disabled AI must not query Ollama"))
    status = intelligence.story_ai_status(Disabled(), {"performance_mode": "lite"})
    assert status["requested_model"] == "qwen3.5:2b"
    assert status["selected_model"] is None
    assert status["using_fallback"] is False
    assert status["reason"] == "ai_disabled"


@pytest.mark.parametrize("response", [None, {}, {"title": "Done"}, {"keep_ids": ["invented"]},
                                      {"keep_ids": [{}]}, {"remove_ids": ["s1"]}])
def test_missing_or_unusable_model_edit_is_labelled_basic_cleanup(monkeypatch, response):
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (True, {"qwen3.5:4b"}))
    monkeypatch.setattr(intelligence, "_call_ollama", lambda *_args: response)
    editorial, engine = intelligence.plan_edit(
        [{"id": "s1", "start": 0.0, "end": 8.0, "text": "A complete useful explanation.", "avg_logprob": -.1}],
        Settings(), {"goal": "youtube", "performance_mode": "quality", "language": "en"},
    )
    assert engine == "deterministic"
    assert editorial["model_selection"]["selected_model"] == "qwen3.5:4b"
    assert editorial["model_selection"]["using_fallback"] is True
    assert editorial["warnings"][0]["type"] == "story_ai_fallback"
    assert "basic transcript cleanup" in editorial["warnings"][0]["message"]


def test_valid_response_records_exact_model_sent_to_transport(monkeypatch):
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _: (True, {"qwen3.5:4b"}))
    called_models = []

    def respond(_settings, payload):
        called_models.append(payload["model"])
        return {"keep_ids": ["s1"], "remove_ids": [], "highlight_ids": ["s1"]}

    monkeypatch.setattr(intelligence, "_call_ollama", respond)
    editorial, engine = intelligence.plan_edit(
        [{"id": "s1", "start": 0.0, "end": 8.0, "text": "A complete useful explanation.", "avg_logprob": -.1}],
        Settings(), {"goal": "youtube", "performance_mode": "lite", "language": "en"},
    )
    assert engine == "ollama"
    assert called_models == [editorial["model_selection"]["selected_model"]] == ["qwen3.5:4b"]
    assert editorial["warnings"] == []
