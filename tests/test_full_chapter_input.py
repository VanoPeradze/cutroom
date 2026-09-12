import json

import pytest

from cutroom import intelligence as ai


def chapter(texts):
    beats = [{"id": f"b{i}", "text": text, "position": i / len(texts), "role_hint": None,
              "start": i * 30, "end": (i + 1) * 30, "editorial_score": .5}
             for i, text in enumerate(texts)]
    return {"id": "c1", "position": 0, "start": 0, "duration": len(texts) * 30, "beats": beats}


@pytest.mark.parametrize("language,text", [
    ("en", "The important ending explains the outcome. "),
    ("he", "הסיום החשוב מסביר מה קרה בסוף. "),
    ("ar", "النهاية المهمة تشرح النتيجة. "),
    ("zh", "重要的结尾解释了最终结果。"),
])
def test_batched_chapter_input_preserves_every_character_and_ending(language, text):
    texts = [(text * 180) + f" UNIQUE_END_{i}" for i in range(9)]
    source = chapter(texts)
    batches = ai._chapter_summary_batches([source], {"language": language}, "local", "balanced", 420)
    assert len(batches) > 1
    seen = {row["id"]: "" for row in source["beats"]}
    for batch in batches:
        payload = ai._chapter_summary_payload(batch, {}, "local", "balanced", 420)
        assert ai._story_prompt_fits(payload)
        user = json.loads(payload["messages"][1]["content"])
        for part in user["chapters"]:
            for beat in part["beats"]:
                seen[beat["id"]] += beat["text"]
    assert list(seen.values()) == texts


def test_complete_short_beat_is_not_truncated_at_old_420_character_boundary():
    text = "Opening explanation. " * 30 + "The final answer is forty two."
    payload = ai._chapter_prompt_payload(chapter([text]), 420)
    assert payload["beats"][0]["text"] == text


def test_split_summaries_keep_one_chapter_identity_and_late_evidence(monkeypatch):
    source = chapter(["Clear evidence. " * 600 + f" END_{i}" for i in range(10)])
    seen = []

    def respond(_settings, payload, *_args):
        rows = json.loads(payload["messages"][1]["content"])["chapters"]
        seen.extend(rows)
        return {"chapters": [{
            "id": row["id"], "title": "Result", "summary": row["beats"][-1]["text"][-30:],
            "role": "result", "key_points": [row["beats"][-1]["text"][-30:]],
            "key_beat_ids": [row["beats"][-1]["id"]], "depends_on": [], "unresolved_questions": [],
        } for row in rows]}

    monkeypatch.setattr(ai, "_call_ollama_story_pass", respond)
    settings = type("Settings", (), {"ai": {"performance_mode": "balanced"}})()
    result = ai._summarize_story_chapters(settings, [source], {}, "local")
    assert len(result) == 1
    assert result[0]["id"] == "c1"
    assert result[0]["input_parts"] > 1
    assert "b9" in result[0]["key_beat_ids"]
    assert "END_9" in result[0]["summary"]
    assert len(seen) == result[0]["input_parts"]


def test_bounded_excerpt_labels_omissions_and_retains_payoff():
    result = ai._balanced_excerpt("OPEN " + "middle " * 200 + "PAYOFF", 240)
    assert result.startswith("OPEN") and result.endswith("PAYOFF")
    assert "[…]" in result and len(result) == 240
