from __future__ import annotations

import contextlib
import copy
import json

import pytest

from cutroom import cloud_ai, intelligence
from cutroom.story_evidence import build_story_evidence_catalog


ROLES = ("premise", "setup", "evidence", "result")


class Settings:
    ai = {"performance_mode": "balanced"}


def fixture():
    segments = [{"id": f"s{i}", "start": (i - 1) * 5.0, "end": i * 5.0,
                 "text": text} for i, text in enumerate(
        ["The question is clear.", "Here is the setup.", "This experiment tested it.", "The answer is qualified."], 1)]
    beats = [{"id": f"b{i}", "start": row["start"], "end": row["end"], "duration": 5.0,
              "text": row["text"], "segment_ids": [row["id"]]} for i, row in enumerate(segments, 1)]
    chapters = [{"id": f"c{i}", "beats": [beat]} for i, beat in enumerate(beats, 1)]
    plan = {"slots": [{"purpose": role, "chapter_ids": [f"c{i}"], "required_context_chapter_ids": ["c1"]}
                      for i, role in enumerate(ROLES, 1)]}
    brief = {"goal": "short", "target_duration": 20, "performance_mode": "balanced",
             "instruction": "Structure: " + " -> ".join(ROLES),
             "style_profile": {"selection_policy": {"story_structure": list(ROLES)}}}
    catalog = build_story_evidence_catalog(beats, segments)
    choices = list(intelligence._story_evidence_choice_catalog(catalog))
    reply = {"verdict": "fit", "role_selections": {
        role: {"primary_anchor_choice": choice, "additional_primary_evidence_choices": [],
               "context_evidence_choices_by_chapter": {"c1": [choices[0]]}}
        for role, choice in reversed(list(zip(ROLES, choices)))},
        "highlight_beat_ids": ["b3"], "title": "Qualified answer", "summary": "Unverified model wording."}
    return beats, segments, chapters, plan, brief, catalog, reply


def select(monkeypatch, reply, *, mutate=None):
    beats, segments, chapters, plan, brief, catalog, _ = fixture()
    if mutate:
        mutate(plan, brief)
    calls = []

    def respond(_settings, payload, *_args):
        calls.append(copy.deepcopy(payload))
        return copy.deepcopy(reply)

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    result = intelligence._select_story_beats(Settings(), chapters, [], {}, plan, brief, "fixture", segments=segments)
    return result, calls


def test_complete_fit_uses_exact_plan_order_and_remains_provisional(monkeypatch):
    *_, reply = fixture()
    original = copy.deepcopy(reply)
    (selection, _), calls = select(monkeypatch, reply)
    assert reply == original
    assert [row["purpose"] for row in selection["slot_map"]] == list(ROLES)
    assert selection["keep_beat_ids"] == ["b1", "b2", "b3", "b4"]
    assert selection["recovered_slot_indexes"] == []
    assert selection["semantic_mapping_verified"] is False
    assert selection["semantic_review_status"] == "provisional_precision_selection"
    assert selection["summary"] != reply["summary"]
    assert len(calls) == 1
    assert calls[0]["_single_attempt"] is True
    assert calls[0]["_reject_duplicate_keys"] is True
    source = json.loads(calls[0]["messages"][1]["content"])
    assert source["source_utterances"] == [{k: row[k] for k in ("id", "start", "end", "text")} for row in fixture()[1]]
    assert source["source_evidence"] == fixture()[5]


def test_schema_requires_complete_roles_context_domains_and_honest_refusal():
    beats, _, chapters, plan, brief, catalog, reply = fixture()
    schema = intelligence._precision_story_contract(catalog, beats, chapters, plan, brief)
    fit, refusal = schema["anyOf"]
    assert fit["properties"]["verdict"]["enum"] == ["fit"]
    roles = fit["properties"]["role_selections"]
    assert roles["required"] == list(ROLES)
    assert set(roles["properties"]) == set(ROLES)
    assert roles["additionalProperties"] is False
    by_choice = intelligence._story_evidence_choice_catalog(catalog)
    beat_chapters = {beat["id"]: chapter["id"] for chapter in chapters for beat in chapter["beats"]}
    for index, role in enumerate(ROLES, 1):
        properties = roles["properties"][role]["properties"]
        primary = properties["primary_anchor_choice"]["$ref"].split("/")[-1]
        assert set(schema["$defs"][primary]["enum"]) == {
            choice for choice, row in by_choice.items() if beat_chapters[row["beat_id"]] == f"c{index}"}
        contexts = properties["context_evidence_choices_by_chapter"]
        assert contexts["required"] == ["c1"]
        assert contexts["additionalProperties"] is False
        context = contexts["properties"]["c1"]
        assert context["minItems"] == 1 and context["uniqueItems"] is True
        domain = context["items"]["$ref"].split("/")[-1]
        assert schema["$defs"][domain]["enum"] == [reply["role_selections"]["premise"]["primary_anchor_choice"]]
    assert refusal["properties"]["verdict"]["enum"] == ["no_fit"]
    assert set(refusal["required"]) == {"verdict", "reason", "missing_purposes"}
    assert "role_selections" not in refusal["properties"]
    assert refusal["additionalProperties"] is False


@pytest.mark.parametrize("fault", ["missing_role", "unknown_role", "missing_context", "wrong_context", "unknown_choice",
                                  "duplicate_choice", "duplicate_anchor", "legacy_three_rows", "wrong_primary", "unknown_highlight"])
def test_invalid_current_responses_never_recover_or_assign_missing_roles(monkeypatch, fault):
    *_, reply = fixture()
    result = reply["role_selections"]["result"]
    if fault == "missing_role":
        reply["role_selections"].pop("result")
    elif fault == "unknown_role":
        reply["role_selections"]["invented"] = reply["role_selections"].pop("result")
    elif fault == "missing_context":
        result["context_evidence_choices_by_chapter"] = {}
    elif fault == "wrong_context":
        result["context_evidence_choices_by_chapter"]["c1"] = [result["primary_anchor_choice"]]
    elif fault == "unknown_choice":
        result["primary_anchor_choice"] = "Fabricated source [b4:s4:f99]"
    elif fault == "duplicate_choice":
        result["context_evidence_choices_by_chapter"]["c1"] *= 2
    elif fault == "duplicate_anchor":
        result["additional_primary_evidence_choices"] = [result["primary_anchor_choice"]]
    elif fault == "legacy_three_rows":
        reply = {"slot_selections": [{"slot_index": i, "purpose": role, "beat_ids": [f"b{i+1}"]} for i, role in enumerate(ROLES[:-1])],
                 "highlight_beat_ids": [], "opening_beat_id": "b1", "closing_beat_id": "b3", "title": "Legacy", "summary": "Legacy"}
    elif fault == "wrong_primary":
        result["primary_anchor_choice"] = reply["role_selections"]["premise"]["primary_anchor_choice"]
    else:
        reply["highlight_beat_ids"] = ["b99"]
    with pytest.raises(intelligence.StoryPlanningError, match="precision"):
        select(monkeypatch, reply)


@pytest.mark.parametrize("fault", ["duplicate", "unknown", "empty", "missing", "unknown_chapter", "duplicate_context"])
def test_invalid_plan_domains_stop_before_precision_call(monkeypatch, fault):
    beats, segments, chapters, plan, brief, _, _ = fixture()
    if fault == "duplicate":
        plan["slots"][-1]["purpose"] = "premise"
    elif fault == "unknown":
        plan["slots"][-1]["purpose"] = "invented"
    elif fault == "empty":
        plan["slots"][-1]["purpose"] = ""
    elif fault == "missing":
        plan["slots"].pop()
    elif fault == "unknown_chapter":
        plan["slots"][-1]["required_context_chapter_ids"] = ["c99"]
    else:
        plan["slots"][-1]["required_context_chapter_ids"] = ["c1", "c1"]
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_a, **_kw: pytest.fail("Invalid plan reached transport"))
    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._select_story_beats(Settings(), chapters, [], {}, plan, brief, "fixture", segments=segments)


@pytest.mark.parametrize("reason", ["unsupported_roles", "insufficient_context", "source_order", "target_budget"])
def test_no_fit_needs_no_fabricated_anchors_and_is_not_extractively_eligible(monkeypatch, reason):
    reply = {"verdict": "no_fit", "reason": reason, "missing_purposes": ["result"]}
    with pytest.raises(intelligence.StoryBudgetError) as caught:
        select(monkeypatch, reply)
    failure = caught.value
    assert failure.diagnostic["reason"] == "precision_no_fit"
    assert failure.diagnostic["outcome"] == "editorial_no_fit"
    assert failure.diagnostic["applied_to_timeline"] is False
    assert failure.diagnostic["precision"]["missing_purposes"] == ["result"]
    beats, segments, chapters, plan, brief, _, _ = fixture()
    brief["allow_extractive_rough_cut"] = True
    assert intelligence._extractive_rough_cut_decision({}, beats, segments, chapters, plan, brief, failure) is None


@pytest.mark.parametrize("instruction", [
    "Keep the qualified result; exclude participation.",
    "\u05e9\u05de\u05d5\u05e8 \u05e2\u05dc \u05d4\u05e1\u05ea\u05d9\u05d9\u05d2\u05d5\u05ea; \u05d0\u05dc \u05ea\u05db\u05dc\u05d5\u05dc \u05d4\u05e9\u05ea\u05ea\u05e4\u05d5\u05ea.",
])
def test_precision_receives_exact_bilingual_instruction(monkeypatch, instruction):
    *_, reply = fixture()
    (_, _), calls = select(monkeypatch, reply, mutate=lambda _plan, brief: brief.update(instruction=instruction))
    assert len(calls) == 1
    assert json.loads(calls[0]["messages"][1]["content"])["brief"]["instruction"] == instruction


@pytest.mark.parametrize("language", ["en", "he"])
def test_neutral_two_beat_anchor_contract_keeps_earlier_support_and_rejects_opening_anchor(language):
    """Regression for the actual live EN control: fit was rejected at its early anchor.

    These are mechanical decoder controls, not a simulated semantic acceptance.
    The Hebrew counterpart independently protects exact Unicode source choices.
    """
    texts = (["I missed my bus because I left late.",
              "The next day I left ten minutes earlier and arrived on time."] if language == "en" else
             ["פספסתי את האוטובוס כי יצאתי מאוחר.",
              "למחרת יצאתי עשר דקות מוקדם יותר והגעתי בזמן."])
    segments = [{"id": f"s{i}", "start": (i-1)*10., "end": i*10., "text": text}
                for i, text in enumerate(texts, 1)]
    beats = intelligence.build_story_beats(segments, language, target_seconds=20)
    chapters = intelligence.build_story_chapters(beats, max_chapters=1)
    brief = {"goal": "short", "target_duration": 20, "duration_mode": "target",
             "language": language, "instruction": "Choose one coherent self-contained idea."}
    plan = {"slots": [{"purpose": intelligence.SINGLE_PASSAGE_PURPOSE,
                       "chapter_ids": [chapters[0]["id"]], "required_context_chapter_ids": []}]}
    payload, catalog = intelligence._precision_story_payload(
        beats, segments, chapters, [], {}, plan, brief, "fixture", "balanced", 20)
    choices = list(intelligence._story_evidence_choice_catalog(catalog))
    assert len(beats) == len(choices) == 2
    # The prompt describes the existing validator contract; source and schema remain authoritative.
    assert "latest source end" in payload["messages"][0]["content"]
    assert json.loads(payload["messages"][1]["content"])["source_utterances"] == segments
    role = {"primary_anchor_choice": choices[-1], "additional_primary_evidence_choices": [choices[0]],
            "context_evidence_choices_by_chapter": {}}
    reply = {"verdict": "fit", "role_selections": {intelligence.SINGLE_PASSAGE_PURPOSE: role},
             "highlight_beat_ids": [], "title": "Unverified", "summary": "Unverified"}
    clean = intelligence._decode_precision_story_selection(reply, catalog, beats, segments, chapters, plan, brief)
    assert clean["keep_beat_ids"] == [row["id"] for row in beats]
    assert clean["semantic_mapping_verified"] is False
    assert clean["semantic_review_status"] == "provisional_precision_selection"
    original = copy.deepcopy(reply)
    role.update(primary_anchor_choice=choices[0], additional_primary_evidence_choices=[choices[-1]])
    with pytest.raises(intelligence.StoryPlanningError, match="invalid precision source assignments"):
        intelligence._decode_precision_story_selection(reply, catalog, beats, segments, chapters, plan, brief)
    # A fabricated last-quote cannot repair the early-anchor defect.
    forged = copy.deepcopy(original)
    forged["role_selections"][intelligence.SINGLE_PASSAGE_PURPOSE]["primary_anchor_choice"] = "Invented outcome [b0002:s2:f99]"
    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._decode_precision_story_selection(forged, catalog, beats, segments, chapters, plan, brief)


def test_precision_refusal_stops_hierarchy_before_critic_final_or_decision(monkeypatch):
    beats, segments, chapters, plan, brief, _, _ = fixture()
    brief["allow_extractive_rough_cut"] = True
    monkeypatch.setattr(intelligence, "_ready_story_model_status", lambda *_a: {"selected_model": "fixture"})
    monkeypatch.setattr(intelligence, "build_story_chapters", lambda *_a, **_kw: chapters)
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_a: [])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_a: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_a: plan)
    calls = []
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_a: calls.append(1) or {
        "verdict": "no_fit", "reason": "unsupported_roles", "missing_purposes": ["result"]})
    for name in ("_critic_story_selection", "_review_story_target_budget", "_story_decision_from_beats", "_extractive_rough_cut_decision"):
        monkeypatch.setattr(intelligence, name, lambda *_a, **_kw: pytest.fail("Precision refusal reached a later stage"))
    before = copy.deepcopy((beats, segments, brief))
    with pytest.raises(intelligence.StoryBudgetError) as caught:
        intelligence.hierarchical_story_edit(beats, segments, Settings(), brief)
    assert caught.value.diagnostic["reason"] == "precision_no_fit"
    assert calls == [1]
    assert (beats, segments, brief) == before


@pytest.mark.parametrize("patch", [{"reason": []}, {"reason": {}}, {"reason": 1}, {"missing_purposes": ["invented"]},
                                 {"missing_purposes": ["result", "result"]}, {"role_selections": {}}])
def test_malformed_no_fit_is_a_controlled_planning_failure(monkeypatch, patch):
    reply = {"verdict": "no_fit", "reason": "unsupported_roles", "missing_purposes": ["result"], **patch}
    with pytest.raises(intelligence.StoryPlanningError, match="invalid precision refusal") as caught:
        select(monkeypatch, reply)
    assert not isinstance(caught.value, intelligence.StoryBudgetError)


def test_absent_canonical_domain_exposes_only_no_fit_without_fake_choices():
    beats, _, chapters, plan, brief, _, _ = fixture()
    schema = intelligence._precision_story_contract([], beats, chapters, plan, brief)
    assert len(schema["anyOf"]) == 1
    assert schema["anyOf"][0]["properties"]["verdict"]["enum"] == ["no_fit"]
    assert schema["$defs"] == {}


def test_same_unit_provisional_roles_still_require_critic_and_final_semantic_review(monkeypatch):
    beats, segments, chapters, plan, brief, catalog, _ = fixture()
    beats, segments, chapters = beats[:1], segments[:1], chapters[:1]
    for slot in plan["slots"]:
        slot["chapter_ids"] = ["c1"]
    brief["allow_extractive_rough_cut"] = False
    choice = list(intelligence._story_evidence_choice_catalog(catalog))[0]
    reply = {"verdict": "fit", "role_selections": {role: {"primary_anchor_choice": choice,
        "additional_primary_evidence_choices": [], "context_evidence_choices_by_chapter": {"c1": [choice]}}
        for role in ROLES}, "highlight_beat_ids": [], "title": "Synthetic", "summary": "Unverified"}
    monkeypatch.setattr(intelligence, "_ready_story_model_status", lambda *_a: {"selected_model": "fixture"})
    monkeypatch.setattr(intelligence, "build_story_chapters", lambda *_a, **_kw: chapters)
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_a: [])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_a: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_a: plan)
    stages = []
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_a: stages.append("precision") or copy.deepcopy(reply))

    def critic(_settings, selection, *_args):
        stages.append("critic")
        assert selection["keep_beat_ids"] == ["b1"]
        assert len(selection["slot_map"]) == len(ROLES)
        assert selection["semantic_mapping_verified"] is False
        assert selection["semantic_review_status"] == "provisional_precision_selection"
        return {**selection, "critic": {"verdict": "pass"}}

    def final(_settings, selection, *_args):
        stages.append("final")
        assert selection["semantic_mapping_verified"] is False
        raise intelligence.StoryBudgetError("Synthetic semantic refusal", {"reason": "planner_no_fit",
            "semantic_revision": {"attempts": 1}})

    monkeypatch.setattr(intelligence, "_critic_story_selection", critic)
    monkeypatch.setattr(intelligence, "_review_story_target_budget", final)
    monkeypatch.setattr(intelligence, "_story_decision_from_beats", lambda *_a: pytest.fail("Refused semantic review produced a decision"))
    original = copy.deepcopy((beats, segments, brief, plan, reply))
    with pytest.raises(intelligence.StoryBudgetError, match="Synthetic semantic refusal"):
        intelligence.hierarchical_story_edit(beats, segments, Settings(), brief)
    assert stages == ["precision", "critic", "final"]
    assert (beats, segments, brief, plan, reply) == original


@pytest.mark.parametrize("raw", ['{"verdict":"fit","verdict":"no_fit"}',
                                  '{"role_selections":{"result":{},"resu\\u006ct":{}}}',
                                  '{"role_selections":{"result":{"c1":[],"c1":[]}}}'])
@pytest.mark.parametrize("streaming", [False, True])
def test_local_precision_duplicate_keys_fail_once_without_internal_wire_flags(monkeypatch, raw, streaming):
    calls = []
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: False)
    monkeypatch.setattr(intelligence, "_fit_story_request_context", lambda *_a: None)
    monkeypatch.setattr(intelligence, "open_ollama", lambda request, **_kw: calls.append(json.loads(request.data)) or contextlib.nullcontext(object()))
    monkeypatch.setattr(intelligence, "_read_ollama_chat_response", lambda *_a, **_kw: {"message": {"content": raw}, "done_reason": "stop"})
    with pytest.raises(intelligence.StoryPlanningError, match="invalid JSON"):
        intelligence._call_ollama_strict(Settings(), {"model": "fixture", "_single_attempt": True,
            "_reject_duplicate_keys": True}, cancel_check=(lambda: None) if streaming else None)
    assert len(calls) == 1
    assert not any(key.startswith("_") for key in calls[0])


@pytest.mark.parametrize("provider", ["groq", "openai-compatible"])
def test_cloud_precision_duplicate_parse_is_opt_in_and_preserves_provider_hooks(monkeypatch, provider):
    selected = {"provider": provider, "model": "fixture", "api_key": "test-synthetic-noncredential"}
    monkeypatch.setattr(cloud_ai, "require_connection", lambda _settings: selected)
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: True)
    calls = []

    def respond(path, key, data, **kwargs):
        calls.append((path, json.loads(data), kwargs))
        return {"choices": [{"finish_reason": "stop", "message": {"content": '{"role":{"result":1,"resu\\u006ct":2}}'}}]}

    monkeypatch.setattr(cloud_ai, "_request", respond)
    with pytest.raises(cloud_ai.CloudAIError, match="complete structured edit"):
        intelligence._call_ollama_strict(Settings(), {"_single_attempt": True, "_reject_duplicate_keys": True})
    assert len(calls) == 1
    assert not any(key.startswith("_") for key in calls[0][1])
    assert ("connection" in calls[0][2]) == (provider == "openai-compatible")
    assert intelligence._call_ollama_strict(Settings(), {}) == {"role": {"result": 2}}


def test_nonprecision_local_retry_policy_and_duplicate_parsing_remain_compatible(monkeypatch):
    calls = []
    replies = iter([{"message": {"content": "{"}, "done_reason": "length"},
                    {"message": {"content": '{"x":1,"x":2}'}, "done_reason": "stop"}])
    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: False)
    monkeypatch.setattr(intelligence, "_fit_story_request_context", lambda *_a: None)
    monkeypatch.setattr(intelligence, "open_ollama", lambda request, **_kw: calls.append(json.loads(request.data)) or contextlib.nullcontext(object()))
    monkeypatch.setattr(intelligence, "_read_ollama_chat_response", lambda *_a, **_kw: next(replies))
    assert intelligence._call_ollama_strict(Settings(), {"model": "fixture"}) == {"x": 2}
    assert len(calls) == 2
