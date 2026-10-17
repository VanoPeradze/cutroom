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

        def read(self, limit):
            content = '{"ok":' if retry and len(bodies) == 1 else '{"ok": true}'
            return json.dumps({"message": {"content": content}, "done_reason": "stop"}).encode()

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response()

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
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


def test_budget_revision_single_attempt_does_not_retry_malformed_json(monkeypatch):
    bodies = _capture_requests(monkeypatch, retry=True)
    payload = _payload({"brief": {"target_duration": 20}})
    payload["_single_attempt"] = True

    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._call_ollama_strict(Settings(), payload)

    assert len(bodies) == 1
    assert "_single_attempt" not in bodies[0]


def test_explicit_thinking_single_attempt_preserves_its_output_budget_and_input(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    payload = _payload({"brief": {"target_duration": 20}}, output=6144)
    payload.update(think=True, _single_attempt=True)
    original = copy.deepcopy(payload)

    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}

    assert len(bodies) == 1
    assert bodies[0]["think"] is True
    assert bodies[0]["options"]["num_predict"] == 6144
    assert "_single_attempt" not in bodies[0]
    assert payload == original


def test_generic_strict_request_defaults_to_compact_non_thinking_output(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    payload = _payload({"brief": {}})
    original = copy.deepcopy(payload)

    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}

    assert len(bodies) == 1
    assert bodies[0]["think"] is False
    assert payload == original


def test_single_thinking_attempt_exhaustion_fails_without_retry_or_input_mutation(monkeypatch):
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            return json.dumps({"message": {"thinking": "The thinking budget was exhausted.", "content": ""},
                               "done_reason": "length"}).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response()

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    payload = _payload({"brief": {"target_duration": 20}}, output=6144)
    payload.update(think=True, _single_attempt=True)
    original = copy.deepcopy(payload)

    with pytest.raises(intelligence.StoryResponseLimitError, match="output budget"):
        intelligence._call_ollama_strict(Settings(), payload)

    assert len(bodies) == 1
    assert bodies[0]["think"] is True
    assert bodies[0]["options"]["num_predict"] == 6144
    assert payload == original


@pytest.mark.parametrize("last_reason", ["length", "stop"])
def test_truncated_response_classification_preserves_the_existing_two_attempt_limit(monkeypatch, last_reason):
    bodies = []
    responses = [
        {"message": {"content": '{"cut_off":'}, "done_reason": "length"},
        {"message": {"content": '{"still_cut_off":'}, "done_reason": last_reason},
    ]

    class Response:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            return json.dumps(self.body).encode("utf-8")

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response(responses[len(bodies) - 1])

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    payload = _payload({"brief": {"target_duration": 20}})
    original = copy.deepcopy(payload)

    with pytest.raises(intelligence.StoryPlanningError) as caught:
        intelligence._call_ollama_strict(Settings(), payload)

    assert len(bodies) == 2
    assert bodies[0]["options"]["num_predict"] == 1200
    assert bodies[1]["options"]["num_predict"] == 2400
    if last_reason == "length":
        assert isinstance(caught.value, intelligence.StoryResponseLimitError)
    else:
        assert type(caught.value) is intelligence.StoryPlanningError
    assert payload == original


def test_single_thinking_attempt_preserves_cancellation_while_streaming(monkeypatch):
    class Cancelled(RuntimeError):
        pass

    cancellation = Cancelled("The owning job was cancelled.")
    state = {"chunks": 0, "closed": False}
    bodies = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

        def readline(self, limit):
            if state["chunks"]:
                return b""
            state["chunks"] += 1
            return json.dumps({"message": {"thinking": "A partial thought.", "content": ""},
                               "done": False}).encode("utf-8") + b"\n"

        def close(self):
            state["closed"] = True

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response()

    def cancel_check():
        if state["chunks"]:
            raise cancellation

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    payload = _payload({"brief": {"target_duration": 20}}, output=6144)
    payload.update(think=True, _single_attempt=True)
    original = copy.deepcopy(payload)

    with pytest.raises(Cancelled) as caught:
        intelligence._call_ollama_strict(Settings(), payload, cancel_check=cancel_check)

    assert caught.value is cancellation
    assert len(bodies) == 1
    assert bodies[0]["think"] is True
    assert bodies[0]["stream"] is True
    assert bodies[0]["options"]["num_predict"] == 6144
    assert state["closed"] is True
    assert payload == original


def _canonical_thinking_evidence():
    text = "BEGIN " + "canonical source wording " * 100 + " MIDDLE " + "ending source wording " * 60 + " END."
    evidence = [{"id": f"b1:s1:f{index + 1}", "beat_id": "b1", "segment_id": "s1",
                 "text": text[start:start + 150], "start": 0.0, "end": 20.0,
                 "char_start": start, "char_end": min(start + 150, len(text))}
                for index, start in enumerate(range(0, len(text), 150))]
    return {"brief": {"target_duration": 20},
            "source_units": [{"id": "b1", "start": 0.0, "end": 20.0, "segment_ids": ["s1"], "text": text,
                              "segments": [{"id": "s1", "start": 0.0, "end": 20.0, "text": text}]}],
            "source_evidence": evidence}


@pytest.mark.parametrize("mode", ["balanced", "auto"])
def test_6144_thinking_reservation_preserves_complete_canonical_source_at_transport(monkeypatch, mode):
    bodies = _capture_requests(monkeypatch)
    content = _canonical_thinking_evidence()
    payload = _payload(content, mode=mode, output=6144)
    payload.update(think=True, _single_attempt=True)
    original = copy.deepcopy(payload)
    assert intelligence._story_prompt_tokens(payload) + 6144 > 8192

    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}

    assert len(bodies) == 1
    sent = bodies[0]
    assert sent["think"] is True
    assert sent["options"]["num_predict"] == 6144
    assert sent["options"]["num_ctx"] > 8192
    assert intelligence._story_prompt_fits(sent)
    assert json.loads(sent["messages"][1]["content"]) == content
    assert payload == original


def test_lite_rejects_fixed_canonical_evidence_plus_6144_reserve_before_network(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    payload = _payload(_canonical_thinking_evidence(), mode="lite", output=6144)
    payload.update(think=True, _single_attempt=True)
    original = copy.deepcopy(payload)
    assert intelligence._story_prompt_tokens(payload) + 6144 > 8192

    with pytest.raises(intelligence.StoryPlanningError, match="estimated local context budget"):
        intelligence._call_ollama_strict(Settings(), payload)

    assert bodies == []
    assert payload == original


def test_budget_revision_single_attempt_control_is_stripped_before_cloud(monkeypatch):
    from cutroom import cloud_ai
    captured = []
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: True)
    monkeypatch.setattr(cloud_ai, "chat", lambda _settings, payload, **_kwargs: captured.append(payload) or {"ok": True})
    payload = _payload({"brief": {"target_duration": 20}})
    payload["_single_attempt"] = True
    assert intelligence._call_ollama_strict(Settings(), payload) == {"ok": True}
    assert "_single_attempt" not in captured[0]
    assert payload["_single_attempt"] is True


def test_revision_source_units_remain_complete_at_the_transport_boundary(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    text = "BEGIN " + "full source evidence " * 200 + " MIDDLE dependency " + "full source evidence " * 200 + " END."
    unit = {"id": "b1", "start": 0, "end": 15, "segment_ids": ["s1", "s2"], "text": text,
            "segments": [{"id": "s1", "start": 0, "end": 8, "text": text},
                         {"id": "s2", "start": 8, "end": 15, "text": "Complete ending."}]}
    content = {"brief": {"target_duration": 20}, "source_units": [unit],
               "candidates": [{"id": "b1", "text": text}]}
    payload = _payload(content)
    payload["_single_attempt"] = True
    intelligence._call_ollama_strict(Settings(), payload)
    sent = json.loads(bodies[0]["messages"][1]["content"])
    assert sent["source_units"] == [unit]


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


def test_one_story_job_keeps_its_largest_context_so_the_model_is_not_reloaded(monkeypatch):
    bodies = _capture_requests(monkeypatch)
    large = _payload({"brief": {"instruction": "a" * 38000}})
    small = _payload({"brief": {}})
    with intelligence._stable_story_context():
        intelligence._call_ollama_strict(Settings(), small)
        intelligence._call_ollama_strict(Settings(), large)
        intelligence._call_ollama_strict(Settings(), small)
    intelligence._call_ollama_strict(Settings(), small)
    sizes = [body["options"]["num_ctx"] for body in bodies]
    assert sizes == [8192, 32768, 32768, 8192]
    assert set(sizes) <= set(intelligence._STORY_CONTEXT_TIERS)
