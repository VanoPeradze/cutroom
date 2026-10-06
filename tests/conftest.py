from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_real_gameplay_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests never send frames to a real local model.

    Gameplay vision runs automatically for streamer styles on a GPU-class
    device. A developer machine with a GPU and a running Ollama must not turn
    ordinary Director tests into slow, nondeterministic model calls. Tests of
    the pass itself patch these back explicitly.
    """
    from cutroom import director, visual_moments

    monkeypatch.setattr(visual_moments, "accelerated_inference_available", lambda _settings: False)
    monkeypatch.setattr(director, "accelerated_inference_available", lambda _settings: False)
    monkeypatch.setattr(visual_moments, "model_supports_vision", lambda *_args, **_kwargs: False)
