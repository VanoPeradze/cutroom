"""Context sizing at the strict request boundary, with no local AI calls."""

from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence


class Settings:
    ai = {"ollama_url": "http://127.0.0.1:11434", "performance_mode": "auto"}


def _payload(content, *, mode="auto", context=8192, output=1200):
    return {
        "model": "test-model", "stream": False,
        "_performance_mode": mode, "format": {"type": "object"},
        "options": {"num_ctx": context, "num_predict": output, "temperature": 0.04},
        "messages": [
            {"role": "system", "content": "Use every supplied identifier. Return JSON."},
            {"role": "user", "content": json.dumps(content, ensure_ascii=False)},
        ],
    }


def _capture_requests(monkeypatch, *, retry=False):
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            content = '{"ok":' if retry and len(bodies) == 1 else '{"ok": true}'
            return json.dumps({"message": {"content": content}, "done_reason": "stop"}).encode()

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response()

    monkeypatch.setattr(intelligence.urllib.request, "urlopen", fake_urlopen)
    return bodies


@pytest.mark.parametrize("mode", ["auto", "quality"])
def test_non_lite_context_can_grow_past_16k_without_shortening_the_brief(monkeypatch, mode):
    bodies = _capture_requests(monkeypatch)
    payload = _payload({"brief": {"instruction": "a" * 38000}}, mode=mode)
    original = copy.deepcopy(payload)

    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}

    assert payload == original
    assert bodies[0]["messages"] == original["messages"]
    assert 16384 < bodies[0]["options"]["num_ctx"] <= 32768
    assert intelligence._story_prompt_fits(bodies[0])
    assert "_performance_mode" not in bodies[0]


def test_lite_honors_its_cap_even_when_a_pass_requests_a_larger_context(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    intelligence._call_ollama_strict(Settings(), _payload({"brief": {}}, mode="lite", context=32768))
    assert bodies[0]["options"]["num_ctx"] == 8192


def test_a_missing_output_limit_receives_a_finite_reservation(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    payload = _payload({"brief": {}})
    payload["options"].pop("num_predict")
    intelligence._call_ollama_strict(Settings(), payload)
    assert bodies[0]["options"]["num_predict"] == 1200


def test_an_unbounded_output_setting_is_rejected_before_network(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    with pytest.raises(intelligence.StoryPlanningError, match="finite positive output budget"):
        intelligence._call_ollama_strict(Settings(), _payload({"brief": {}}, output=-1))
    assert bodies == []


@pytest.mark.parametrize("mode", ["lite", "auto", "quality"])
@pytest.mark.parametrize("summary_key", ["chapters", "chapter_summaries"])
def test_large_downstream_evidence_preserves_every_row_id_and_excerpt_region(monkeypatch, caplog, mode, summary_key):
    bodies = _capture_requests(monkeypatch)
    phrase = "English שלום 证明 " * 300
    content = {
        "brief": {"instruction": "PRIVATE_INSTRUCTION: preserve the conclusion.", "goal": "short"},
        "outline": {"must_keep_chapter_ids": ["c001", "c002"]},
        "plan": {"slots": [{"chapter_ids": ["c001"], "required_context_chapter_ids": ["c002"]}]},
        summary_key: [{
            "id": "c001", "summary": "The complete chapter summary stays unchanged.",
            "key_beat_ids": ["b000", "b005"], "depends_on": ["c002"],
            "key_points": [f"BEGIN {phrase} MIDDLE {phrase} END"],
        }],
    }
    for key in ("candidate_beats", "candidates", "selected"):
        content[key] = [
            {"id": f"b{index:03d}", "start": index * 10, "duration": 10,
             "text": f"BEGIN {phrase} MIDDLE {phrase} END"}
            for index in range(6)
        ]
    payload = _payload(content, mode=mode)
    original = copy.deepcopy(payload)

    intelligence._call_ollama_strict(Settings(), payload)

    assert payload == original
    sent = bodies[0]
    assert sent["options"]["num_ctx"] == (8192 if mode == "lite" else 32768)
    assert intelligence._story_prompt_fits(sent)
    reduced = json.loads(sent["messages"][1]["content"])
    for key in ("brief", "outline", "plan"):
        assert reduced[key] == content[key]
    for key in ("candidate_beats", "candidates", "selected"):
        assert len(reduced[key]) == len(content[key])
        for before, after in zip(content[key], reduced[key]):
            assert {key: value for key, value in after.items() if key != "text"} == {
                key: value for key, value in before.items() if key != "text"
            }
            assert len(after["text"]) < len(before["text"])
            assert all(marker in after["text"] for marker in ("BEGIN", "MIDDLE", "END", "[…]"))
    summary = reduced[summary_key][0]
    assert summary["summary"] == content[summary_key][0]["summary"]
    assert summary["id"] == "c001"
    assert summary["key_beat_ids"] == ["b000", "b005"]
    assert summary["depends_on"] == ["c002"]
    assert len(summary["key_points"]) == 1
    assert all(marker in summary["key_points"][0] for marker in ("BEGIN", "MIDDLE", "END"))
    assert "shortened" in caplog.text
    assert "PRIVATE_INSTRUCTION" not in caplog.text


@pytest.mark.parametrize("content", [
    {"brief": {"instruction": "x" * 90000}, "candidate_beats": [{"id": "b001", "text": "Small candidate"}]},
    {"brief": {}, "chapters": [{"id": "c001", "beats": [{"id": "b001", "text": "x" * 90000}]}]},
    {"brief": {}, "candidates": [{"id": f"b{index:04d}-" + "i" * 100, "text": "Short"} for index in range(2000)]},
])
def test_oversized_fixed_content_fails_before_network_without_dropping_evidence(monkeypatch, content):
    bodies = _capture_requests(monkeypatch)
    payload = _payload(content)
    original = copy.deepcopy(payload)
    with pytest.raises(intelligence.StoryPlanningError, match="estimated local context budget"):
        intelligence._call_ollama_strict(Settings(), payload)
    assert bodies == []
    assert payload == original


def test_raw_chapter_inputs_are_never_shortened_when_they_fit(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    content = {"chapters": [{"id": "c001", "beats": [{"id": "b001", "text": "First. " + "middle " * 500 + "Last."}]}]}
    payload = _payload(content)
    intelligence._call_ollama_strict(Settings(), payload)
    assert bodies[0]["messages"] == payload["messages"]


@pytest.mark.parametrize("mode", ["auto", "lite"])
def test_retry_rebudgets_for_larger_output_before_sending(monkeypatch, mode):
    bodies = _capture_requests(monkeypatch, retry=True)
    content = {"brief": {"instruction": "Preserve every ID."}, "selected": [
        {"id": f"b{index:03d}", "text": "BEGIN " + "a" * 180 + " MIDDLE " + "a" * 180 + " END"}
        for index in range(20)
    ]}
    payload = _payload(content, mode=mode, output=1800)
    assert intelligence._story_prompt_fits(payload)

    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}

    assert len(bodies) == 2
    assert bodies[1]["options"]["num_predict"] == 3600
    assert all(intelligence._story_prompt_fits(body) for body in bodies)
    first, retry = [json.loads(body["messages"][1]["content"]) for body in bodies]
    assert first == content
    assert retry["brief"] == content["brief"]
    assert [row["id"] for row in retry["selected"]] == [row["id"] for row in content["selected"]]
    if mode == "auto":
        assert bodies[1]["options"]["num_ctx"] > bodies[0]["options"]["num_ctx"]
        assert retry == content
    else:
        assert bodies[1]["options"]["num_ctx"] == 8192
        assert len(retry["selected"][0]["text"]) < len(content["selected"][0]["text"])
        assert all(marker in retry["selected"][0]["text"] for marker in ("BEGIN", "MIDDLE", "END"))


def test_retry_fails_before_a_second_request_if_fixed_input_and_output_reserve_cannot_fit(monkeypatch):
    bodies = _capture_requests(monkeypatch, retry=True)
    payload = _payload({"brief": {"instruction": "a" * 9000}}, mode="lite", output=1800)
    assert intelligence._story_prompt_fits(payload)
    with pytest.raises(intelligence.StoryPlanningError, match="estimated local context budget"):
        intelligence._call_ollama_strict(Settings(), payload)
    assert len(bodies) == 1
