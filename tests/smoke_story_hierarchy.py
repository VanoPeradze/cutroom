from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cutroom import intelligence
from cutroom.config import load_settings


def segment(identifier: str, start: float, end: float, text: str) -> dict:
    return {"id": identifier, "start": start, "end": end, "text": text, "words": [], "avg_logprob": -0.1}


def main() -> None:
    rows = []
    for index in range(180):
        text = f"Supporting context about the topic {index}."
        if index == 8:
            text = "Why this matters is the main problem and opening promise."
        elif index == 88:
            text = "For example this middle demonstration proves the main claim."
        elif index == 170:
            text = "Finally the result and conclusion deliver the payoff."
        rows.append(segment(f"s{index}", index * 6.0, index * 6.0 + 5.2, text))

    settings = load_settings()
    settings.raw["ai"]["enabled"] = True
    settings.raw["ai"]["editor_model"] = "qwen3.5:4b"
    settings.raw["ai"]["editor_fallback_models"] = []
    original_inventory = intelligence._ollama_inventory
    original_call = intelligence._call_ollama_strict
    calls: list[str] = []
    intelligence._ollama_inventory = lambda _settings: (True, {"qwen3.5:4b"})

    def fake_call(_settings, payload, timeout=180):
        system = payload["messages"][0]["content"]
        calls.append(system)
        user = json.loads(payload["messages"][1]["content"])
        if "first pass" in system:
            return {"chapters": [
                {
                    "id": ch["id"], "title": ch["id"], "summary": f"Summary {ch['id']}", "role": "development",
                    "key_points": ["important context"], "key_beat_ids": [ch["beats"][0]["id"]],
                    "depends_on": [], "unresolved_questions": [],
                }
                for ch in user["chapters"]
            ]}
        if "global story analyst" in system:
            chapters = user["chapters"]
            return {
                "premise": "A problem is introduced, demonstrated and resolved.",
                "audience_takeaway": "Understand the proof and result.",
                "story_arc": [
                    {"chapter_id": ch["id"], "function": "development", "why_it_matters": "part of the full arc"}
                    for ch in chapters
                ],
                "must_keep_chapter_ids": [chapters[0]["id"], chapters[len(chapters)//2]["id"], chapters[-1]["id"]],
                "optional_chapter_ids": [], "dependency_pairs": [],
            }
        if "Story Producer" in system:
            arc = user["outline"]["story_arc"]
            ids = [arc[0]["chapter_id"], arc[len(arc)//2]["chapter_id"], arc[-1]["chapter_id"]]
            return {"narrative": "problem to proof to payoff", "slots": [
                {"purpose": "hook", "chapter_ids": [ids[0]], "desired_seconds": 16, "reason": "open", "required_context_chapter_ids": []},
                {"purpose": "proof", "chapter_ids": [ids[1]], "desired_seconds": 26, "reason": "prove", "required_context_chapter_ids": []},
                {"purpose": "ending", "chapter_ids": [ids[2]], "desired_seconds": 16, "reason": "finish", "required_context_chapter_ids": []},
            ]}
        if "precision editor" in system:
            summaries = {item["id"]: item for item in user["chapter_summaries"]}
            selections = []
            chosen = []
            for slot_index, slot in enumerate(user["plan"]["slots"]):
                chapter = summaries[slot["chapter_ids"][0]]
                beat_id = chapter["key_beat_ids"][0]
                selections.append({"slot_index": slot_index, "beat_ids": [beat_id]})
                chosen.append(beat_id)
            return {
                "slot_selections": selections, "highlight_beat_ids": chosen,
                "opening_beat_id": chosen[0], "closing_beat_id": chosen[-1],
                "title": "Hierarchical story", "summary": "A coherent story built across the recording.",
            }
        if "continuity critic" in system:
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": "Continuity is sound."}
        raise AssertionError(system)

    intelligence._call_ollama_strict = fake_call
    try:
        editorial, engine = intelligence.plan_edit(rows, settings, {
            "goal": "short", "target_duration": 60, "language": "en", "performance_mode": "balanced",
        })
    finally:
        intelligence._ollama_inventory = original_inventory
        intelligence._call_ollama_strict = original_call

    hierarchy = editorial["story_hierarchy"]
    starts = [float(item["start"]) for item in editorial["decision"]["story_ranges"]]
    assert engine == "ollama_hierarchical_story"
    assert hierarchy["chapter_count"] >= 6
    assert hierarchy["outline"]["story_arc"]
    assert len(hierarchy["plan"]["slots"]) == 3
    assert hierarchy["critic"]["verdict"] == "pass"
    assert min(starts) < 180
    assert any(value > 400 for value in starts)
    assert any(value > 850 for value in starts)
    assert any("first pass" in item for item in calls)
    assert any("global story analyst" in item for item in calls)
    assert any("Story Producer" in item for item in calls)
    assert any("precision editor" in item for item in calls)
    assert any("continuity critic" in item for item in calls)
    print(json.dumps({
        "ok": True, "engine": engine, "chapters": hierarchy["chapter_count"],
        "story_ranges": editorial["decision"]["story_ranges"], "passes": len(calls),
    }, indent=2))


if __name__ == "__main__":
    main()
