from __future__ import annotations

import pytest

from cutroom.caption_translation import (LANGUAGES, TranslationUnavailable, build_srt, caption_lines,
                                         srt_time, translate_project_captions)

ITEMS = [
    {"start": 3.0, "end": 4.5, "text": "Second  line"},
    {"start": 0.5, "end": 2.0, "text": "First line"},
    {"start": 5.0, "end": 6.0, "text": "Hidden", "hidden": True},
    {"start": 7.0, "end": 7.0, "text": "Zero length"},
]
READY = lambda settings, effective: {"ready": True, "selected_model": "test-model"}


def test_lines_and_srt_keep_edit_timing():
    lines = caption_lines(ITEMS)
    assert [line["text"] for line in lines] == ["First line", "Second line"]
    assert srt_time(3661.0416) == "01:01:01,042"
    assert build_srt(lines) == "1\n00:00:00,500 --> 00:00:02,000\nFirst line\n\n2\n00:00:03,000 --> 00:00:04,500\nSecond line\n"


def test_translation_replaces_text_only_and_keeps_missing_lines():
    seen = []

    def call(settings, payload, timeout):
        seen.append(payload)
        assert payload["model"] == "test-model" and "Hebrew" in payload["messages"][0]["content"]
        return {"lines": [{"i": 0, "text": "שורה ראשונה"}, {"i": 9, "text": "ignored"}, {"i": "x"}]}

    result = translate_project_captions(object(), ITEMS, "he", status=READY, call=call)
    assert result["translated"] == 1 and result["lines"] == 2
    assert "00:00:00,500 --> 00:00:02,000\nשורה ראשונה" in result["srt"]
    assert "Second line" in result["srt"]
    assert len(seen) == 1


def test_translation_needs_captions_ai_and_a_known_language():
    with pytest.raises(ValueError):
        translate_project_captions(object(), ITEMS, "xx", status=READY, call=lambda *a, **k: {})
    with pytest.raises(TranslationUnavailable):
        translate_project_captions(object(), [], "en", status=READY, call=lambda *a, **k: {})
    with pytest.raises(TranslationUnavailable, match="not ready"):
        translate_project_captions(object(), ITEMS, "en", status=lambda s, e: {"ready": False, "message": "Story AI is not ready"}, call=lambda *a, **k: {})
    with pytest.raises(TranslationUnavailable, match="no usable"):
        translate_project_captions(object(), ITEMS, "en", status=READY, call=lambda *a, **k: {"nope": 1})

    def boom(*args, **kwargs):
        raise OSError("offline")
    with pytest.raises(TranslationUnavailable, match="offline"):
        translate_project_captions(object(), ITEMS, "en", status=READY, call=boom)


def test_batches_long_transcripts():
    items = [{"start": i, "end": i + 0.5, "text": f"line {i}"} for i in range(65)]
    calls = []

    def call(settings, payload, timeout):
        import json
        rows = json.loads(payload["messages"][1]["content"])["lines"]
        calls.append(len(rows))
        return {"lines": [{"i": row["i"], "text": row["text"].upper()} for row in rows]}

    result = translate_project_captions(object(), items, "es", status=READY, call=call)
    assert calls == [30, 30, 5] and result["translated"] == 65 and "LINE 64" in result["srt"]
    assert set(LANGUAGES) >= {"en", "he"}


def test_endpoint_validates_language_and_needs_captions(tmp_path, monkeypatch):
    from cutroom.config import load_settings
    from server import create_app
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    app = create_app(settings)
    app.config.update(TESTING=True)
    client = app.test_client()
    project = client.post("/api/projects", json={"name": "Translate"}).get_json()["project"]
    url = f"/api/projects/{project['id']}/caption-translation"
    assert client.post(url, json={"language": "xx"}).status_code == 400
    assert client.post(url, json={"language": "he", "extra": 1}).status_code == 400
    missing = client.post(url, json={"language": "he"})
    assert missing.status_code == 409 and missing.get_json()["error"] == "translation_unavailable"
