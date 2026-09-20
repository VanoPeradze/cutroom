"""Provider choices invalidate analysis without making credentials part of its cache."""
from types import SimpleNamespace

import pytest

from cutroom.cache_keys import build_analysis_cache_fingerprints


def fingerprints(**overrides):
    connection = {"mode": "own", "provider": "openai-compatible",
                  "base_url": "https://api.example.com/v1", "model": "story-model",
                  "transcript_model": "speech-model", "api_key": "test-first-key"}
    connection.update(overrides)
    settings = SimpleNamespace(ai={"cloud_connection": connection}, raw={})
    return build_analysis_cache_fingerprints({}, settings, {"goal": "short"}, {})


@pytest.mark.parametrize("change", [
    {"base_url": "https://other.example.com/v1"},
    {"transcript_model": "other-speech-model"},
    {"model": "other-story-model"},
    {"provider": "groq"},
])
def test_cloud_destination_and_models_invalidate_transcript_and_story(change):
    before, after = fingerprints(), fingerprints(**change)
    assert before["transcript"] != after["transcript"]
    assert before["story"] != after["story"]
    assert before["source"] == after["source"]


def test_api_key_rotation_is_not_part_of_the_analysis_cache():
    assert fingerprints() == fingerprints(api_key="test-replacement-key")
