from __future__ import annotations

from cutroom.intelligence import enrich_segments, language_from_text, similarity, deterministic_edit


def segment(identifier, start, end, text):
    return {"id": identifier, "start": start, "end": end, "text": text, "words": [], "avg_logprob": -0.1}


def test_language_detection_scripts():
    assert language_from_text("שלום, זה סרטון בעברית") == "he"
    assert language_from_text("هذا فيديو باللغة العربية") == "ar"
    assert language_from_text("Это видео на русском языке") == "ru"
    assert language_from_text("Gracias por ver este vídeo") == "es"
    assert language_from_text("Merci pour cette vidéo") == "fr"


def test_retake_and_filler_detection():
    items = [
        segment("s1", 0, 1.4, "Um today we will explain"),
        segment("s2", 1.5, 4.5, "Today we will explain the complete workflow."),
        segment("s3", 4.6, 8.0, "This is the useful result and the final answer."),
    ]
    enriched = enrich_segments(items, "en")
    assert enriched[0]["filler_ratio"] > 0
    assert enriched[1]["repeat_score"] > 0.45
    assert enriched[0]["editorial_score"] < enriched[2]["editorial_score"]


def test_similarity_handles_repeated_take():
    assert similarity("Today I want to show the result", "Today I want to show the result clearly") > 0.75


def test_short_deterministic_edit_has_valid_ids():
    items = enrich_segments([
        segment("s1", 0, 3, "This opening establishes the problem."),
        segment("s2", 3, 6, "Um, I mean, basically."),
        segment("s3", 6, 10, "The result saves editors several hours."),
        segment("s4", 10, 14, "This closing explains the next step."),
    ], "en")
    result = deterministic_edit(items, {"goal": "short", "pace": "balanced", "target_duration": 10})
    valid = {item["id"] for item in items}
    assert set(result["keep_ids"]) <= valid
    assert set(result["remove_ids"]) <= valid
    assert not (set(result["keep_ids"]) & set(result["remove_ids"]))


def test_empty_transcript_skips_llm(monkeypatch):
    from cutroom import intelligence

    def should_not_run(*args, **kwargs):
        raise AssertionError("LLM should not be called without transcript segments")

    monkeypatch.setattr(intelligence, "_ollama_chat", should_not_run)
    editorial, engine = intelligence.plan_edit([], None, {"language": "en", "pace": "balanced", "goal": "clean"})
    assert engine == "deterministic"
    assert editorial["segments"] == []


def test_long_transcript_compaction_covers_full_recording():
    from cutroom.intelligence import compact_segments_for_llm
    segments = [
        {"id": f"s{i}", "start": i * 3.0, "end": i * 3.0 + 2.5, "text": f"segment {i}", "editorial_score": (i % 17) / 17}
        for i in range(500)
    ]
    compact = compact_segments_for_llm(segments, 120)
    ids = {item["id"] for item in compact}
    assert len(compact) <= 120
    assert "s0" in ids and "s499" in ids
    assert any(200 <= int(item["id"][1:]) <= 300 for item in compact)


def test_story_beats_group_long_transcript_into_context_units():
    from cutroom.intelligence import build_story_beats
    rows = []
    for index in range(80):
        rows.append(segment(f"s{index}", index * 4.0, index * 4.0 + 3.4, f"Idea {index}. This explains one part of the workflow."))
    enriched = enrich_segments(rows, "en")
    beats = build_story_beats(enriched, "en")
    assert 8 <= len(beats) < len(enriched)
    assert beats[0]["start"] == 0
    assert beats[-1]["end"] > 300
    assert all(beat["segment_ids"] for beat in beats)


def test_hebrew_story_cues_raise_hook_and_example_roles():
    from cutroom.intelligence import build_story_beats
    rows = enrich_segments([
        segment("s1", 0, 5, "למה התוצאה הזאת חשובה?"),
        segment("s2", 5, 10, "אני אסביר את הבעיה בצורה ברורה."),
        segment("s3", 10, 15, "לדוגמה תראו כאן מה קורה במשחק."),
        segment("s4", 15, 20, "בסוף זאת המסקנה שלנו."),
    ], "he")
    beats = build_story_beats(rows, "he")
    roles = {beat.get("role_hint") for beat in beats}
    assert roles & {"hook", "example", "conclusion"}


def test_story_planner_fallback_selects_across_long_recording():
    from cutroom.intelligence import build_story_beats, deterministic_story_edit
    rows = []
    for index in range(180):
        text = f"supporting context {index}."
        if index == 12:
            text = "Why this matters is the main hook and promise."
        if index == 91:
            text = "For example this middle proof demonstrates the result."
        if index == 168:
            text = "Finally the conclusion explains the payoff."
        rows.append(segment(f"s{index}", index * 4.0, index * 4.0 + 3.5, text))
    enriched = enrich_segments(rows, "en")
    for item in enriched:
        if item["id"] in {"s12", "s91", "s168"}:
            item["editorial_score"] = 0.99
    beats = build_story_beats(enriched, "en")
    decision = deterministic_story_edit(beats, enriched, {"goal": "short", "target_duration": 60, "pace": "balanced"})
    starts = [float(item["start"]) for item in decision["story_ranges"]]
    assert min(starts) < 100
    assert any(start > 300 for start in starts)
    assert any(start > 600 for start in starts)


def test_two_hour_story_budget_can_pull_from_late_source_sections():
    from cutroom.intelligence import build_story_beats, deterministic_story_edit
    rows = []
    for index in range(720):
        start = index * 10.0
        text = f"supporting explanation {index}."
        if index == 30:
            text = "Why this matters is the opening hook and main promise."
        elif index == 360:
            text = "For example this central demonstration proves the main idea."
        elif index == 660:
            text = "Finally the payoff and conclusion explain what the viewer should remember."
        rows.append(segment(f"s{index}", start, start + 8.5, text))
    enriched = enrich_segments(rows, "en")
    for item in enriched:
        if item["id"] in {"s30", "s360", "s660"}:
            item["editorial_score"] = 1.0
    beats = build_story_beats(enriched, "en")
    decision = deterministic_story_edit(beats, enriched, {"goal":"short", "target_duration":60, "pace":"balanced"})
    starts = [float(item["start"]) for item in decision["story_ranges"]]
    assert starts
    assert min(starts) < 600
    assert any(start > 3300 for start in starts)
    assert any(start > 6300 for start in starts)


def test_short_requires_real_story_ai_instead_of_silent_fallback(monkeypatch):
    import pytest
    from cutroom import intelligence

    class Dummy:
        ai = {
            "enabled": True, "editor_model": "qwen3.5:4b", "editor_fallback_models": [],
            "editor_quality_model": "qwen3.5:9b", "editor_lite_model": "qwen3.5:2b",
            "performance_mode": "auto", "max_story_beats": 72,
        }

    rows = [segment("s1", 0, 8, "This is the actual story and result."), segment("s2", 8, 16, "Finally this is the payoff.")]
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, set()))
    with pytest.raises(intelligence.StoryAIUnavailableError):
        intelligence.plan_edit(rows, Dummy(), {"goal": "short", "target_duration": 60, "language": "en"})


def test_hierarchical_story_pipeline_runs_chapters_outline_plan_selection_and_critic(monkeypatch):
    from cutroom import intelligence

    class Dummy:
        ai = {
            "enabled": True, "editor_model": "qwen3.5:4b", "editor_fallback_models": [],
            "editor_quality_model": "qwen3.5:9b", "editor_lite_model": "qwen3.5:2b",
            "performance_mode": "balanced", "max_story_beats": 72,
        }

    rows = []
    for index in range(40):
        text = f"Context idea {index}."
        if index == 2: text = "Why this matters is the opening hook."
        if index == 20: text = "For example this proof demonstrates the main claim."
        if index == 37: text = "Finally this conclusion delivers the payoff."
        rows.append(segment(f"s{index}", index * 8.0, index * 8.0 + 7.2, text))

    calls = []
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"qwen3.5:4b"}))

    def fake_call(_settings, payload, timeout=180):
        system = payload["messages"][0]["content"]
        calls.append(system)
        user = __import__("json").loads(payload["messages"][1]["content"])
        if "first pass" in system:
            return {"chapters": [
                {"id": ch["id"], "title": ch["id"], "summary": f"Summary {ch['id']}", "role": "development",
                 "key_points": ["important point"], "key_beat_ids": [ch["beats"][0]["id"]], "depends_on": [], "unresolved_questions": []}
                for ch in user["chapters"]
            ]}
        if "global story analyst" in system:
            chapters = user["chapters"]
            return {
                "premise": "A problem is explained and proven.", "audience_takeaway": "Understand the result.",
                "story_arc": [{"chapter_id": ch["id"], "function": "development", "why_it_matters": "context"} for ch in chapters],
                "must_keep_chapter_ids": [chapters[0]["id"], chapters[-1]["id"]], "optional_chapter_ids": [], "dependency_pairs": [],
            }
        if "Story Producer" in system:
            arc = user["outline"]["story_arc"]
            ids = [arc[0]["chapter_id"], arc[len(arc)//2]["chapter_id"], arc[-1]["chapter_id"]]
            return {"narrative": "hook to proof to payoff", "slots": [
                {"purpose": "hook", "chapter_ids": [ids[0]], "desired_seconds": 15, "reason": "open", "required_context_chapter_ids": []},
                {"purpose": "proof", "chapter_ids": [ids[1]], "desired_seconds": 25, "reason": "prove", "required_context_chapter_ids": []},
                {"purpose": "ending", "chapter_ids": [ids[2]], "desired_seconds": 15, "reason": "finish", "required_context_chapter_ids": []},
            ]}
        if "precision editor" in system:
            beats = user["candidate_beats"]
            by_chapter = {}
            for beat in beats:
                # Chapter IDs are available through the plan slots; choose one valid beat per slot in order.
                pass
            slots = user["plan"]["slots"]
            selections = []
            chosen = []
            for slot_index, slot in enumerate(slots):
                allowed = set(slot["chapter_ids"] + slot.get("required_context_chapter_ids", []))
                chapter_lookup = {}
                for chapter in user["chapter_summaries"]:
                    chapter_lookup[chapter["id"]] = set(chapter.get("key_beat_ids", []))
                candidate = next((beat["id"] for beat in beats if any(beat["id"] in chapter_lookup.get(ch, set()) for ch in allowed)), None)
                if candidate is None:
                    candidate = beats[min(slot_index, len(beats)-1)]["id"]
                selections.append({"slot_index": slot_index, "beat_ids": [candidate]})
                chosen.append(candidate)
            return {"slot_selections": selections, "highlight_beat_ids": chosen, "opening_beat_id": chosen[0], "closing_beat_id": chosen[-1], "title": "Story", "summary": "Coherent"}
        if "continuity critic" in system:
            return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": "Continuity is sound"}
        raise AssertionError(system)

    monkeypatch.setattr(intelligence, "_call_ollama_strict", fake_call)
    editorial, engine = intelligence.plan_edit(rows, Dummy(), {"goal": "short", "target_duration": 60, "language": "en", "performance_mode": "balanced"})
    assert engine == "ollama_hierarchical_story"
    hierarchy = editorial["story_hierarchy"]
    assert hierarchy["chapter_count"] >= 3
    assert hierarchy["outline"]["story_arc"]
    assert len(hierarchy["plan"]["slots"]) == 3
    assert hierarchy["critic"]["verdict"] == "pass"
    starts = [item["start"] for item in editorial["decision"]["story_ranges"]]
    assert min(starts) < 100
    assert any(value > 120 for value in starts)
    assert any(value > 250 for value in starts)
    assert any("first pass" in call for call in calls)
    assert any("global story analyst" in call for call in calls)
    assert any("Story Producer" in call for call in calls)
    assert any("precision editor" in call for call in calls)
    assert any("continuity critic" in call for call in calls)


def test_chapter_summarization_retries_only_an_omitted_chapter(monkeypatch):
    from cutroom import intelligence

    class Dummy:
        ai = {"performance_mode": "balanced"}

    chapters = [
        {
            "id": f"c{index:03d}", "start": float(index * 10), "end": float(index * 10 + 9),
            "duration": 9.0, "position": index / 3,
            "beats": [{
                "id": f"b{index:04d}", "position": index / 3, "role_hint": "development",
                "text": f"Original transcript for chapter {index}.", "editorial_score": 0.7,
            }],
        }
        for index in range(1, 4)
    ]
    requested_ids = []
    schemas = []

    def fake_call(_settings, payload, timeout=180):
        user = __import__("json").loads(payload["messages"][1]["content"])
        ids = [chapter["id"] for chapter in user["chapters"]]
        requested_ids.append(ids)
        schemas.append(payload["format"])
        returned_ids = [ids[0], ids[2]] if len(ids) == 3 else ids
        return {"chapters": [
            {
                "id": chapter_id, "title": chapter_id, "summary": f"Summary {chapter_id}",
                "role": "development", "key_points": [],
                "key_beat_ids": [f"b{int(chapter_id[1:]):04d}"],
                "depends_on": [], "unresolved_questions": [],
            }
            for chapter_id in returned_ids
        ]}

    monkeypatch.setattr(intelligence, "_call_ollama_strict", fake_call)
    summaries = intelligence._summarize_story_chapters(Dummy(), chapters, {}, "qwen:4b")

    assert requested_ids == [["c001", "c002", "c003"], ["c002"]]
    assert [item["id"] for item in summaries] == ["c001", "c002", "c003"]
    assert [item["summary_source"] for item in summaries] == ["model", "model_retry", "model"]
    assert schemas[0]["properties"]["chapters"]["minItems"] == 3
    assert schemas[0]["properties"]["chapters"]["maxItems"] == 3
    assert schemas[1]["properties"]["chapters"]["items"]["properties"]["id"]["enum"] == ["c002"]


def test_chapter_summarization_uses_only_transcript_for_safe_last_resort(monkeypatch):
    from cutroom import intelligence

    class Dummy:
        ai = {"performance_mode": "balanced"}

    chapters = [{
        "id": "c001", "start": 0.0, "end": 18.0, "duration": 18.0, "position": 0.0,
        "beats": [
            {"id": "b0001", "position": 0.0, "role_hint": "setup", "text": "Exact opening transcript.", "editorial_score": 0.5},
            {"id": "b0002", "position": 0.5, "role_hint": "result", "text": "Exact result transcript.", "editorial_score": 0.9},
        ],
    }]
    monkeypatch.setattr(intelligence, "_call_ollama_strict", lambda *_args, **_kwargs: {"chapters": []})

    summaries = intelligence._summarize_story_chapters(Dummy(), chapters, {}, "qwen:4b")

    assert summaries[0]["summary_source"] == "extractive"
    assert summaries[0]["summary"] == "Exact opening transcript. Exact result transcript."
    assert summaries[0]["key_points"] == ["Exact opening transcript.", "Exact result transcript."]
    assert set(summaries[0]["key_beat_ids"]) <= {"b0001", "b0002"}


def test_chapter_summarization_rejects_foreign_singleton_id(monkeypatch):
    from cutroom import intelligence

    class Dummy:
        ai = {"performance_mode": "balanced"}

    chapters = [{
        "id": "c001", "start": 0.0, "end": 9.0, "duration": 9.0, "position": 0.0,
        "beats": [{
            "id": "b0001", "position": 0.0, "role_hint": "setup",
            "text": "Only the real source transcript may survive.", "editorial_score": 0.8,
        }],
    }]
    calls = 0

    def fake_call(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"chapters": []}
        return {"chapters": [{
            "id": "c999", "title": "Foreign", "summary": "Foreign model text",
            "role": "result", "key_points": [], "key_beat_ids": ["b0001"],
            "depends_on": [], "unresolved_questions": [],
        }]}

    monkeypatch.setattr(intelligence, "_call_ollama_strict", fake_call)
    summaries = intelligence._summarize_story_chapters(Dummy(), chapters, {}, "qwen:4b")

    assert calls == 2
    assert summaries[0]["id"] == "c001"
    assert summaries[0]["summary_source"] == "extractive"
    assert summaries[0]["summary"] == "Only the real source transcript may survive."
    assert "Foreign model text" not in summaries[0]["summary"]


def test_chapter_summary_normalization_keeps_only_typed_local_evidence():
    from cutroom import intelligence

    normalized = intelligence._normalize_chapter_summary(
        {
            "title": {"bad": "title"}, "summary": " Real summary ", "role": ["result"],
            "key_points": [None, {"bad": True}, " real point "],
            "key_beat_ids": [None, {"bad": True}, "b0001", "foreign"],
            "depends_on": [None, {"bad": True}, "c002", "c999"],
            "unresolved_questions": [None, " real question "],
        },
        "c001",
        {"c001", "c002"},
        {"b0001"},
        summary_source="model",
    )

    assert normalized is not None
    assert normalized["title"] == "c001"
    assert normalized["role"] == "other"
    assert normalized["key_points"] == ["real point"]
    assert normalized["key_beat_ids"] == ["b0001"]
    assert normalized["depends_on"] == ["c002"]
    assert normalized["unresolved_questions"] == ["real question"]
    assert intelligence._normalize_chapter_summary(
        {"summary": "No local evidence", "key_beat_ids": ["foreign"]},
        "c001", {"c001"}, {"b0001"}, summary_source="model",
    ) is None


def test_chapter_recovery_honors_cancellation_before_extractive_fallback(monkeypatch):
    import pytest
    from cutroom import intelligence

    class Dummy:
        ai = {"performance_mode": "balanced"}

    class Cancelled(RuntimeError):
        pass

    chapters = [{
        "id": "c001", "start": 0.0, "end": 9.0, "duration": 9.0, "position": 0.0,
        "beats": [{
            "id": "b0001", "position": 0.0, "role_hint": "setup",
            "text": "Cancellation must stop recovery.", "editorial_score": 0.8,
        }],
    }]
    state = {"calls": 0, "cancelled": False}

    def fake_call(*_args, **_kwargs):
        state["calls"] += 1
        if state["calls"] == 2:
            state["cancelled"] = True
        return {"chapters": []}

    def cancel_check():
        if state["cancelled"]:
            raise Cancelled("stop")

    monkeypatch.setattr(intelligence, "_call_ollama_strict", fake_call)
    monkeypatch.setattr(
        intelligence,
        "_extractive_chapter_summary",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback must not run after cancellation")),
    )

    with pytest.raises(Cancelled, match="stop"):
        intelligence._summarize_story_chapters(
            Dummy(), chapters, {}, "qwen:4b", cancel_check=cancel_check,
        )
    assert state["calls"] == 2


def test_chapter_summarization_refuses_to_invent_when_source_text_is_empty(monkeypatch):
    import pytest
    from cutroom import intelligence

    class Dummy:
        ai = {"performance_mode": "balanced"}

    chapters = [{
        "id": "c001", "start": 0.0, "end": 2.0, "duration": 2.0, "position": 0.0,
        "beats": [{"id": "b0001", "position": 0.0, "role_hint": None, "text": "", "editorial_score": 0.0}],
    }]
    monkeypatch.setattr(intelligence, "_call_ollama_strict", lambda *_args, **_kwargs: {"chapters": []})

    with pytest.raises(intelligence.StoryPlanningError, match="no transcript text"):
        intelligence._summarize_story_chapters(Dummy(), chapters, {}, "qwen:4b")


def test_quality_mode_prefers_9b_only_when_already_installed(monkeypatch):
    from cutroom import intelligence
    class Dummy:
        ai = {
            "editor_model":"qwen3.5:4b",
            "editor_quality_model":"qwen3.5:9b",
            "editor_lite_model":"qwen3.5:2b",
            "editor_fallback_models":["qwen3:8b"],
            "performance_mode":"auto",
        }
    monkeypatch.setattr(intelligence, "_installed_models", lambda _settings: {"qwen3.5:4b", "qwen3.5:9b"})
    assert intelligence._select_editor_model(Dummy(), {"performance_mode":"quality"}) == "qwen3.5:9b"
    assert intelligence._select_editor_model(Dummy(), {"performance_mode":"balanced"}) == "qwen3.5:4b"

def test_story_hierarchy_cache_reuses_chapters_and_outline(monkeypatch):
    from cutroom import intelligence

    class Dummy:
        ai = {
            "enabled": True, "editor_model": "qwen3.5:4b", "editor_fallback_models": [],
            "editor_quality_model": "qwen3.5:9b", "editor_lite_model": "qwen3.5:2b",
            "performance_mode": "balanced", "max_story_beats": 72,
        }

    rows = [segment(f"s{i}", i * 10.0, i * 10.0 + 9.0, f"Idea {i}. Supporting context.") for i in range(36)]
    enriched = enrich_segments(rows, "en")
    beats = intelligence.build_story_beats(enriched, "en")
    chapters = intelligence.build_story_chapters(beats, 12)
    summaries = [
        {"id": ch["id"], "title": ch["id"], "summary": "cached", "role": "development", "key_points": [], "key_beat_ids": [ch["beats"][0]["id"]], "depends_on": [], "unresolved_questions": [], "summary_source": "model"}
        for ch in chapters
    ]
    outline = {
        "premise": "cached premise", "audience_takeaway": "cached takeaway",
        "story_arc": [{"chapter_id": ch["id"], "function": "development", "why_it_matters": "cached"} for ch in chapters],
        "must_keep_chapter_ids": [], "optional_chapter_ids": [], "dependency_pairs": [],
    }
    brief = {"goal": "short", "target_duration": 180, "language": "en", "performance_mode": "balanced"}
    cache = {
        "cache_fingerprint": intelligence.story_cache_fingerprint(enriched, brief, "qwen3.5:4b"),
        "cache_pipeline": intelligence.STORY_CACHE_PIPELINE,
        "model": "qwen3.5:4b", "chapter_count": len(chapters),
        "chapters": [{"id": ch["id"]} for ch in chapters],
        "chapter_summaries": summaries, "outline": outline,
    }
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"qwen3.5:4b"}))
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("chapter summaries should be cached")))
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("outline should be cached")))

    def fake_plan(_settings, _summaries, _outline, _brief, _model, progress=None):
        ids = [chapters[0]["id"], chapters[len(chapters)//2]["id"], chapters[-1]["id"]]
        return {"narrative": "cached hierarchy, new target plan", "slots": [
            {"purpose": "hook", "chapter_ids": [ids[0]], "desired_seconds": 15, "reason": "", "required_context_chapter_ids": []},
            {"purpose": "proof", "chapter_ids": [ids[1]], "desired_seconds": 25, "reason": "", "required_context_chapter_ids": []},
            {"purpose": "ending", "chapter_ids": [ids[2]], "desired_seconds": 15, "reason": "", "required_context_chapter_ids": []},
        ]}

    monkeypatch.setattr(intelligence, "_build_story_plan", fake_plan)

    def fake_select(_settings, chapters_arg, summaries_arg, outline_arg, plan, brief, model, progress=None):
        candidates = intelligence._candidate_beats_for_plan(chapters_arg, plan)
        chosen = [candidates[0]["id"], candidates[len(candidates)//2]["id"], candidates[-1]["id"]]
        return {"keep_beat_ids": chosen, "highlight_beat_ids": chosen, "opening_beat_id": chosen[0], "closing_beat_id": chosen[-1], "title": "Cached story", "summary": ""}, candidates

    monkeypatch.setattr(intelligence, "_select_story_beats", fake_select)
    monkeypatch.setattr(intelligence, "_critic_story_selection", lambda _settings, selection, candidates, outline, plan, brief, model, progress=None: {**selection, "critic": {"verdict": "pass"}})

    decision, hierarchy = intelligence.hierarchical_story_edit(beats, enriched, Dummy(), brief, story_cache=cache)
    assert decision["story_ranges"]
    assert hierarchy["outline"]["premise"] == "cached premise"
    assert hierarchy["plan"]["narrative"] == "cached hierarchy, new target plan"


def test_story_cache_rejects_partial_duplicate_foreign_and_malformed_content():
    import copy
    from cutroom import intelligence

    rows = [segment(f"s{i}", i * 10.0, i * 10.0 + 9.0, f"Idea {i}. Supporting context.") for i in range(36)]
    enriched = enrich_segments(rows, "en")
    beats = intelligence.build_story_beats(enriched, "en")
    chapters = intelligence.build_story_chapters(beats, 12)
    brief = {"goal": "short", "target_duration": 180, "language": "en", "performance_mode": "balanced"}
    fingerprint = intelligence.story_cache_fingerprint(enriched, brief, "qwen:4b")
    cache = {
        "cache_fingerprint": fingerprint,
        "cache_pipeline": intelligence.STORY_CACHE_PIPELINE,
        "model": "qwen:4b",
        "chapter_count": len(chapters),
        "chapters": [{"id": chapter["id"]} for chapter in chapters],
        "chapter_summaries": [
            {
                "id": chapter["id"], "title": chapter["id"], "summary": "cached",
                "role": "development", "key_points": [],
                "key_beat_ids": [chapter["beats"][0]["id"]], "depends_on": [],
                "unresolved_questions": [], "summary_source": "model",
            }
            for chapter in chapters
        ],
        "outline": {
            "premise": "cached", "audience_takeaway": "cached",
            "story_arc": [{"chapter_id": chapter["id"], "function": "development", "why_it_matters": "context"} for chapter in chapters],
            "must_keep_chapter_ids": [], "optional_chapter_ids": [], "dependency_pairs": [],
        },
    }
    assert intelligence._story_cache_is_reusable(cache, fingerprint, "qwen:4b", chapters)

    invalid_caches = []
    partial = copy.deepcopy(cache)
    partial["chapter_summaries"].pop()
    invalid_caches.append(partial)
    duplicate = copy.deepcopy(cache)
    duplicate["chapter_summaries"][-1]["id"] = duplicate["chapter_summaries"][0]["id"]
    invalid_caches.append(duplicate)
    foreign = copy.deepcopy(cache)
    foreign["chapter_summaries"][-1]["id"] = "c999"
    invalid_caches.append(foreign)
    malformed = copy.deepcopy(cache)
    malformed["outline"]["story_arc"][0]["chapter_id"] = "c999"
    invalid_caches.append(malformed)
    wrong_pipeline = copy.deepcopy(cache)
    wrong_pipeline["cache_pipeline"] = "legacy"
    invalid_caches.append(wrong_pipeline)

    assert all(
        not intelligence._story_cache_is_reusable(candidate, fingerprint, "qwen:4b", chapters)
        for candidate in invalid_caches
    )


def test_precision_selection_recovers_missing_schema_from_ai_plan(monkeypatch):
    from cutroom import intelligence

    beats = [
        {"id": "b1", "start": 0.0, "end": 10.0, "duration": 10.0, "text": "Opening", "editorial_score": 0.8, "novelty": 0.7, "role_hint": "hook"},
        {"id": "b2", "start": 40.0, "end": 52.0, "duration": 12.0, "text": "Result", "editorial_score": 0.9, "novelty": 0.8, "role_hint": "conclusion"},
    ]
    chapters = [
        {"id": "c1", "beats": [beats[0]]},
        {"id": "c2", "beats": [beats[1]]},
    ]
    summaries = [
        {"id": "c1", "key_beat_ids": ["b1"]},
        {"id": "c2", "key_beat_ids": ["b2"]},
    ]
    plan = {"slots": [
        {"purpose": "hook", "chapter_ids": ["c1"], "required_context_chapter_ids": []},
        {"purpose": "ending", "chapter_ids": ["c2"], "required_context_chapter_ids": []},
    ]}
    monkeypatch.setattr(
        intelligence,
        "_call_ollama_strict",
        lambda *_args, **_kwargs: {"error": "schema drift", "suggestion": "retry"},
    )

    selection, candidates = intelligence._select_story_beats(
        object(), chapters, summaries, {}, plan,
        {"target_duration": 60, "performance_mode": "lite"}, "qwen3.5:4b",
    )

    assert [item["slot_index"] for item in selection["slot_map"]] == [0, 1]
    assert selection["keep_beat_ids"] == ["b1", "b2"]
    assert selection["selection_mode"] == "ai_plan_recovery"
    assert selection["recovered_slot_indexes"] == [0, 1]
    assert candidates == beats


def test_precision_recovery_uses_distinct_beats_for_slots_in_same_chapter(monkeypatch):
    from cutroom import intelligence

    beats = [
        {"id": "b1", "start": 0.0, "end": 8.0, "duration": 8.0, "text": "Setup", "editorial_score": 0.8, "novelty": 0.7, "role_hint": "hook"},
        {"id": "b2", "start": 8.0, "end": 18.0, "duration": 10.0, "text": "Payoff", "editorial_score": 0.9, "novelty": 0.8, "role_hint": "conclusion"},
    ]
    chapters = [{"id": "c1", "beats": beats}]
    summaries = [{"id": "c1", "key_beat_ids": ["b1", "b2"]}]
    plan = {"slots": [
        {"purpose": "setup", "chapter_ids": ["c1"], "required_context_chapter_ids": []},
        {"purpose": "ending", "chapter_ids": ["c1"], "required_context_chapter_ids": []},
    ]}
    monkeypatch.setattr(
        intelligence,
        "_call_ollama_strict",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(intelligence.StoryPlanningError("invalid JSON")),
    )

    selection, _ = intelligence._select_story_beats(
        object(), chapters, summaries, {}, plan,
        {"target_duration": 60, "performance_mode": "lite"}, "qwen3.5:4b",
    )

    assert set(selection["keep_beat_ids"]) == {"b1", "b2"}
    assert selection["selection_mode"] == "ai_plan_recovery"
    assert selection["recovery_reason"] == "invalid JSON"


def test_story_budget_fit_prunes_whole_beats_and_preserves_every_plan_slot():
    from cutroom.intelligence import _fit_story_selection_to_budget

    beats = [
        {"id": "b1", "start": 3.85, "end": 7.48, "duration": 3.63, "editorial_score": .5063, "novelty": 1.0, "role_hint": None, "text": "מה שלומכם חברים"},
        {"id": "b2", "start": 46.38, "end": 67.31, "duration": 20.93, "editorial_score": .4781, "novelty": .9375, "role_hint": None, "text": "ברוכים הבאים לערוץ, היום אדבר על משחק קטן שלא כולם מכירים אבל שווה את הזמן שלכם"},
        {"id": "b3", "start": 69.30, "end": 98.19, "duration": 28.89, "editorial_score": .5096, "novelty": .9636, "role_hint": None, "text": "תקליקו על הכדור. All Hail The Orb הוא משחק קטן ומפתיע; צוברים כוח ופותחים שדרוגים"},
        {"id": "b4", "start": 98.93, "end": 117.92, "duration": 18.99, "editorial_score": .5626, "novelty": .9259, "role_hint": None, "text": "מגייסים מאמינים ואז המשחק משחק את עצמו; הוא רגוע ומצחיק"},
        {"id": "b5", "start": 121.10, "end": 148.15, "duration": 27.05, "editorial_score": .5932, "novelty": .9107, "role_hint": None, "text": "ההתקדמות מספקת ונכנסים לחמש דקות אבל נשארים ארבעים"},
        {"id": "b6", "start": 152.17, "end": 167.04, "duration": 14.87, "editorial_score": .565, "novelty": .9388, "role_hint": None, "text": "אם אתם אוהבים משחקי אינדי קצרים זה משחק ששווה לבדוק"},
    ]
    plan = {"slots": [
        {"purpose": "hook", "desired_seconds": 12, "chapter_ids": ["c1"]},
        {"purpose": "strongest proof/example", "desired_seconds": 35, "chapter_ids": ["c2"], "required_context_chapter_ids": ["c1"]},
        {"purpose": "payoff", "desired_seconds": 13, "chapter_ids": ["c3"], "required_context_chapter_ids": ["c2"]},
    ]}
    chapters = [
        {"id": "c1", "beats": beats[:2]},
        {"id": "c2", "beats": beats[2:4]},
        {"id": "c3", "beats": beats[4:]},
    ]
    selection = {
        "keep_beat_ids": [item["id"] for item in beats],
        "highlight_beat_ids": ["b4", "b5"],
        "opening_beat_id": "b1",
        "closing_beat_id": "b6",
        "slot_map": [
            {"slot_index": 0, "purpose": "hook", "beat_ids": ["b1", "b2"]},
            {"slot_index": 1, "purpose": "strongest proof/example", "beat_ids": ["b3", "b4"]},
            {"slot_index": 2, "purpose": "payoff", "beat_ids": ["b5", "b6"]},
        ],
    }

    fitted = _fit_story_selection_to_budget(selection, beats, plan, 60.0, chapters)

    assert fitted["keep_beat_ids"] == ["b2", "b3", "b6"]
    assert fitted["budget_fit"]["before_duration"] == 115.1
    assert fitted["budget_fit"]["after_duration"] == 64.69
    assert fitted["budget_fit"]["after_duration"] <= fitted["budget_fit"]["ceiling"]
    assert all(row["beat_ids"] for row in fitted["slot_map"])
    assert {row["slot_index"] for row in fitted["slot_map"]} == {0, 1, 2}


def test_story_budget_fit_restores_a_slot_removed_by_the_critic():
    from cutroom.intelligence import _fit_story_selection_to_budget

    beats = [
        {"id": "hook", "start": 0.0, "end": 18.0, "editorial_score": .8, "novelty": .8, "text": "A complete setup with enough substance"},
        {"id": "example", "start": 20.0, "end": 43.0, "editorial_score": .8, "novelty": .8, "text": "The concrete example and the context needed to understand it"},
        {"id": "ending", "start": 45.0, "end": 58.0, "editorial_score": .8, "novelty": .8, "text": "A complete ending"},
    ]
    plan = {"slots": [
        {"purpose": "hook", "desired_seconds": 18},
        {"purpose": "example", "desired_seconds": 23},
        {"purpose": "payoff", "desired_seconds": 13},
    ]}
    selection = {
        "keep_beat_ids": ["hook", "ending"],
        "highlight_beat_ids": [],
        "opening_beat_id": "hook",
        "closing_beat_id": "ending",
        "slot_map": [
            {"slot_index": 0, "purpose": "hook", "beat_ids": ["hook"]},
            {"slot_index": 1, "purpose": "example", "beat_ids": ["example"]},
            {"slot_index": 2, "purpose": "payoff", "beat_ids": ["ending"]},
        ],
    }

    fitted = _fit_story_selection_to_budget(selection, beats, plan, 60.0)

    assert fitted["keep_beat_ids"] == ["hook", "example", "ending"]
    assert all(row["beat_ids"] for row in fitted["slot_map"])


def test_story_beats_never_bridge_a_long_absolute_silence():
    from cutroom.intelligence import build_story_beats

    segments = [
        {"id": "s1", "start": 0.0, "end": 2.0, "text": "Opening line", "editorial_score": .7},
        {"id": "s2", "start": 20.0, "end": 22.0, "text": "New scene", "editorial_score": .8},
    ]

    beats = build_story_beats(segments, "en")

    assert [(item["start"], item["end"]) for item in beats] == [(0.0, 2.0), (20.0, 22.0)]
