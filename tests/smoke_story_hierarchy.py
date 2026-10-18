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


def mock_source_roles(payload: dict, user: dict, *, final: bool = False) -> tuple[dict, list[str]]:
    """Supply canonical synthetic choices; production validators remain real."""
    schema = payload["format"]
    roles_schema = (schema["properties"]["role_selections"]["anyOf"][0] if final else
                    schema["anyOf"][0]["properties"]["role_selections"])
    choices = intelligence._story_evidence_choice_catalog(user["source_evidence"])
    current = set(user["current_selected_beat_ids"]) if final else None
    roles, keep = {}, set()
    purposes = roles_schema["required"]
    for purpose in purposes:
        properties = roles_schema["properties"][purpose]["properties"]
        domain_ref = properties["additional_primary_evidence_choices"]["items"]["$ref"]
        domain = schema["$defs"][domain_ref.split("/")[-1]]["enum"]
        per_beat = {}
        for choice in domain:
            owner = choices[choice]["beat_id"]
            if current is None or owner in current:
                per_beat.setdefault(owner, choice)
        ordered = sorted(per_beat, key=lambda value: choices[per_beat[value]]["start"])
        # Two complete source units per role make this synthetic 60-second
        # target feasible; the final mock retains that same fixed selection.
        selected = ordered if final else ordered[:2]
        assert len(selected) == 2
        primary = [per_beat[value] for value in selected]
        anchor = primary[-1] if purpose == purposes[-1] else primary[0]
        anchor_ref = properties["primary_anchor_choice"]["$ref"]
        assert anchor in schema["$defs"][anchor_ref.split("/")[-1]]["enum"]
        row = {"primary_anchor_choice": anchor,
               "additional_primary_evidence_choices": [value for value in primary if value != anchor]}
        if final:
            assert user["role_requirements"][purpose]["required_context_chapter_ids"] == []
            row["context_evidence_choices"] = []
        else:
            context = properties["context_evidence_choices_by_chapter"]
            assert context["required"] == [] and context["properties"] == {}
            row["context_evidence_choices_by_chapter"] = {}
        roles[purpose] = row
        keep.update(selected)
    return roles, sorted(keep)


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
        # Keep the original recording chronology and coverage. Short synthetic
        # utterances expose complete units that can fit all three roles under
        # today's whole-source policy; the old 5.2s fixture needed >=79.44s.
        rows.append(segment(f"s{index}", index * 6.0, index * 6.0 + 3.0, text))

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
            roles, chosen = mock_source_roles(payload, user)
            return {
                "verdict": "fit", "role_selections": roles, "highlight_beat_ids": chosen,
                "title": "Hierarchical story", "summary": "A coherent story built across the recording.",
            }
        if "continuity critic" in system:
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": "Continuity is sound."}
        if "final semantic budget editor" in system:
            roles, chosen = mock_source_roles(payload, user, final=True)
            assert set(chosen) == set(user["current_selected_beat_ids"])
            assert user["sticky_critic_context_beat_ids"] == []
            cost = intelligence._story_selection_cost(chosen, user["candidates"], rows,
                                                       {"target_duration": user["target_seconds"]})
            # Assert feasibility with the actual duration policy. No fake cost,
            # repeated unit, padding, target change or source trimming is used.
            assert cost["minimum_safe_seconds"] <= user["target_seconds"]
            assert cost["approved_seconds"] >= user["minimum_target_seconds"]
            return {"verdict": "fit", "keep_beat_ids": chosen,
                    "released_optional_beat_ids": [], "role_selections": roles}
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
    assert any("final semantic budget editor" in item for item in calls)
    print(json.dumps({
        "ok": True, "mocked_model": True, "engine": engine, "chapters": hierarchy["chapter_count"],
        "story_ranges": editorial["decision"]["story_ranges"], "passes": len(calls),
    }, indent=2))


if __name__ == "__main__":
    main()
