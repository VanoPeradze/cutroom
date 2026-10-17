from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence, story_evidence


class Settings:
    ai = {"enabled": True, "editor_model": "fixture-model", "editor_fallback_models": [],
          "performance_mode": "balanced", "cloud_connection": {"mode": "local"}}


def unit(identifier, start, end, left_end, right_start):
    segment_id = "s" + identifier[1:]
    segment = {"id": segment_id, "start": start, "end": end, "text": "Alpha beta.",
               "words": [{"word": "Alpha", "start": start, "end": left_end},
                         {"word": "beta.", "start": right_start, "end": end}]}
    beat = {"id": identifier, "start": start, "end": end, "duration": end - start,
            "segment_ids": [segment_id], "text": segment["text"]}
    return beat, segment


def en_fixture():
    pairs = [unit("b1", .59, 2.93, 1.29, 1.63),
             unit("b2", 8.41, 19.64, 13, 14.69),
             unit("b3", 20.34, 29.5, 24, 25.74),
             unit("b4", 35.31, 41.31, 35.79, 39.77)]
    beats, segments = map(list, zip(*pairs))
    slots = [{"purpose": purpose, "chapter_ids": ["c1"], "required_context_chapter_ids": ["c1"]}
             for purpose in ("premise", "setup", "evidence", "result")]
    selected = [row["id"] for row in beats]
    selection = {
        "keep_beat_ids": selected,
        "slot_map": [{"slot_index": i, "purpose": slots[i]["purpose"], "beat_ids": [identifier]}
                     for i, identifier in enumerate(("b2", "b4", "b1", "b1"))],
        "recovered_slot_indexes": [2, 3],
        "critic": {"verdict": "revise", "issues": ["context"], "selection_before": ["b1", "b2", "b4"],
                   "post_review_beat_ids": selected, "requested_added": ["b3"], "requested_removed": []},
    }
    return selection, beats, segments, [{"id": "c1", "beats": beats}], {"slots": slots}


def evidence_ids(beats, segments, identifiers):
    catalog = story_evidence.build_story_evidence_catalog(beats, segments)
    return [row["id"] for identifier in identifiers for row in catalog if row["beat_id"] == identifier]


def slot_proof(index, purpose, primary, context, beats, segments):
    primary_ids = evidence_ids(beats, segments, primary)
    return {"slot_index": index, "purpose": purpose, "primary_beat_ids": list(primary),
            "context_beat_ids": list(context), "primary_evidence_ids": primary_ids,
            "context_evidence_ids": evidence_ids(beats, segments, context),
            "temporal_witness_id": primary_ids[0]}


def proposal(plan, assignments=("b2", "b2", "b3", "b4"), *, beats=None, segments=None):
    if beats is None or segments is None:
        _, beats, segments, _, _ = en_fixture()
    return {"verdict": "fit", "keep_beat_ids": ["b2", "b3", "b4"],
            "released_optional_beat_ids": ["b1"],
            "slot_selections": [slot_proof(i, slot["purpose"], [identifier], ["b2"], beats, segments)
                                for i, (slot, identifier) in enumerate(zip(plan["slots"], assignments))]}


def reviewed_fixture():
    fixture = en_fixture()
    selection, beats, segments, _chapters, plan = fixture
    keep = ["b2", "b3", "b4"]
    proof = story_evidence.validate_story_evidence(
        proposal(plan, beats=beats, segments=segments)["slot_selections"], beats, segments,
        selected_beat_ids=keep,
    )
    selection.update(keep_beat_ids=keep, slot_map=proof["slot_map"],
                     semantic_mapping_verified=True, semantic_review_status="model_reviewed",
                     evidence_policy_version=story_evidence.EVIDENCE_POLICY_VERSION,
                     evidence_proof=proof, recovered_slot_indexes=[])
    selection["critic"].update(verdict="pass", issues=[], selection_before=list(keep),
                              post_review_beat_ids=list(keep), requested_added=[], requested_removed=[])
    return fixture


def review(monkeypatch, fixture, reply, calls=None, *, outline=None, **brief_patch):
    selection, beats, segments, chapters, plan = fixture
    def respond(_settings, payload, *_args):
        if calls is not None:
            calls.append(copy.deepcopy(payload))
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    return intelligence._review_story_target_budget(
        Settings(), selection, beats, segments, chapters, outline or {}, plan,
        {"goal": "short", "duration_mode": "target", "target_duration": 20, **brief_patch}, "fixture-model",
    )


def test_one_semantic_revision_reassigns_recovered_slots_before_optional_release(monkeypatch):
    fixture = en_fixture()
    before = copy.deepcopy(fixture)
    calls = []
    revised = review(monkeypatch, fixture, proposal(fixture[-1]), calls)
    assert fixture == before
    assert len(calls) == 1
    assert calls[0]["_single_attempt"] is True
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["current_cost"]["minimum_safe_seconds"] == pytest.approx(21.46)
    assert revised["keep_beat_ids"] == ["b2", "b3", "b4"]
    assert revised["semantic_revision"]["cost"]["minimum_safe_seconds"] == pytest.approx(19.34)
    assert revised["semantic_revision"]["released_optional_beat_ids"] == ["b1"]
    assert all(row["primary_beat_ids"] for row in revised["slot_map"])
    decision = intelligence._story_decision_from_beats(revised, fixture[1], fixture[2])
    assert decision["story_requirements"]["semantic_mapping_verified"] is True
    assert decision["story_requirements"]["required_beat_ids"] == ["b2", "b3", "b4"]
    assert revised["evidence_proof"]["verification_scope"] == "source_attribution_and_order"
    assert revised["evidence_proof"]["catalog_fingerprint"]
    assert decision["story_requirements"]["evidence_proof"] == revised["evidence_proof"]
    assert revised["evidence_policy_version"] == revised["evidence_proof"]["policy_version"]
    assert decision["story_requirements"]["evidence_policy_version"] == revised["evidence_policy_version"]
    assert all(row["source_evidence"] for row in revised["slot_map"])


@pytest.mark.parametrize("fault", ["missing_slot", "duplicate_slot", "unreleased_optional", "wrong_purpose",
                                   "empty_evidence", "unknown_primary", "missing_critic_context", "over_budget"])
def test_invalid_revision_fails_without_a_second_model_call(monkeypatch, fault):
    fixture = en_fixture()
    reply = proposal(fixture[-1])
    if fault == "missing_slot": reply["slot_selections"].pop()
    elif fault == "duplicate_slot": reply["slot_selections"][-1]["slot_index"] = 0
    elif fault == "unreleased_optional": reply["released_optional_beat_ids"] = []
    elif fault == "wrong_purpose": reply["slot_selections"][0]["purpose"] = "different"
    elif fault == "empty_evidence": reply["slot_selections"][0]["primary_evidence_ids"] = []
    elif fault == "unknown_primary": reply["slot_selections"][0]["primary_beat_ids"] = ["unknown"]
    elif fault == "missing_critic_context":
        reply["keep_beat_ids"].remove("b3")
        reply["released_optional_beat_ids"].append("b3")
    elif fault == "over_budget":
        reply["keep_beat_ids"].insert(0, "b1")
        reply["released_optional_beat_ids"] = []
        reply["slot_selections"][2]["primary_beat_ids"] = ["b1", "b3"]
        reply["slot_selections"][2]["primary_evidence_ids"] = evidence_ids(fixture[1], fixture[2], ["b1", "b3"])
    calls = []
    with pytest.raises(intelligence.StoryPlanningError) as caught:
        review(monkeypatch, fixture, reply, calls)
    assert len(calls) == 1
    assert caught.value.diagnostic["required_policy_minimum_seconds"] == pytest.approx(21.46)


def test_infeasible_required_context_reports_its_true_policy_minimum(monkeypatch):
    pairs = [unit("b1", 0, 15.31, 2.64, 3.59), unit("b3", 30.69, 39.08, 31.33, 32.52)]
    beats, segments = map(list, zip(*pairs))
    selection = {"keep_beat_ids": ["b1", "b3"], "slot_map": [{"slot_index": 0, "beat_ids": ["b3"]}],
                 "critic": {"verdict": "revise", "selection_before": ["b3"], "post_review_beat_ids": ["b1", "b3"],
                            "requested_added": ["b1"], "requested_removed": []}}
    plan = {"slots": [{"purpose": "premise", "chapter_ids": ["primary"],
                       "required_context_chapter_ids": ["setup"]}]}
    fixture = (selection, beats, segments, [{"id": "setup", "beats": beats[:1]},
                                          {"id": "primary", "beats": beats[1:]}], plan)
    calls = []
    with pytest.raises(intelligence.StoryPlanningError) as caught:
        review(monkeypatch, fixture, {"verdict": "no_fit", "keep_beat_ids": [],
                                     "released_optional_beat_ids": [], "slot_selections": []}, calls)
    assert len(calls) == 1
    assert caught.value.diagnostic["required_policy_minimum_seconds"] == pytest.approx(21.8)
    assert caught.value.diagnostic["reason"] == "target_infeasible"


def test_verified_full_source_passages_can_fit_by_pauses_without_replanning(monkeypatch):
    fixture = reviewed_fixture()
    calls = []
    revised = review(monkeypatch, fixture, AssertionError("no new call"), calls)
    assert calls == []
    assert revised["keep_beat_ids"] == ["b2", "b3", "b4"]
    assert revised["semantic_revision"]["attempts"] == 0
    assert revised["semantic_revision"]["cost"]["approved_seconds"] > 20
    assert revised["semantic_revision"]["cost"]["fits_target"] is True


def test_issue_only_critic_revision_requires_one_final_semantic_call_despite_valid_proof(monkeypatch):
    fixture = reviewed_fixture()
    fixture[0]["critic"].update(verdict="revise", issues=["The premise is not clear to a new viewer."])
    reply = proposal(fixture[-1])
    reply["released_optional_beat_ids"] = []
    calls = []

    result = review(monkeypatch, fixture, reply, calls)

    assert len(calls) == 1
    assert result["semantic_revision"]["attempts"] == 1
    assert result["semantic_review_status"] == "model_reviewed"
    assert result["critic"]["verdict"] == "pass"
    assert result["critic"]["original_review"]["issues"] == ["The premise is not clear to a new viewer."]


@pytest.mark.parametrize("reply", [{}, TimeoutError("synthetic timeout")])
def test_failed_revision_is_not_a_basic_cleanup_fallback(monkeypatch, reply):
    fixture = en_fixture()
    calls = []
    with pytest.raises(intelligence.StoryPlanningError) as caught:
        review(monkeypatch, fixture, reply, calls)
    assert len(calls) == 1
    assert caught.value.diagnostic["scope"] == "current_required_selection"


def test_revision_cannot_resurrect_an_explicit_critic_rejection(monkeypatch):
    fixture = en_fixture()
    fixture[0]["critic"]["requested_removed"] = ["b1"]
    reply = proposal(fixture[-1])
    reply["keep_beat_ids"].insert(0, "b1")
    reply["released_optional_beat_ids"] = []
    calls = []
    with pytest.raises(intelligence.StoryPlanningError):
        review(monkeypatch, fixture, reply, calls)
    assert len(calls) <= 1


@pytest.mark.parametrize("fault", ["wrong_primary_chapter", "missing_context_chapter", "unrelated_context", "boolean_index",
                                   "unmapped_keep", "duplicate_primary", "partial_source_unit", "unfinished_sentence"])
def test_revision_checks_source_roles_and_complete_units(monkeypatch, fault):
    fixture = list(en_fixture())
    fixture[3] = [{"id": f"c{i}", "beats": [beat]} for i, beat in enumerate(fixture[1], 1)]
    fixture[4] = {"slots": [{"purpose": "result", "chapter_ids": ["c4"],
                              "required_context_chapter_ids": ["c2", "c3"]}]}
    reply = {"verdict": "fit", "keep_beat_ids": ["b2", "b3", "b4"], "released_optional_beat_ids": ["b1"],
             "slot_selections": [slot_proof(0, "result", ["b4"], ["b2", "b3"], fixture[1], fixture[2])]}
    row = reply["slot_selections"][0]
    if fault == "wrong_primary_chapter": row["primary_beat_ids"] = ["b2"]
    elif fault == "missing_context_chapter": row["context_beat_ids"] = ["b2"]
    elif fault == "unrelated_context": row["context_beat_ids"] = ["b2", "b3", "b4"]
    elif fault == "boolean_index": row["slot_index"] = False
    elif fault == "unmapped_keep": row["primary_beat_ids"] = ["b4"]; row["context_beat_ids"] = ["b3"]
    elif fault == "duplicate_primary": row["primary_beat_ids"] = ["b4", "b4"]
    elif fault == "partial_source_unit": fixture[1][3]["start"] += .1
    elif fault == "unfinished_sentence": fixture[1][3]["text"] = fixture[2][3]["text"] = "An unfinished result"
    calls = []
    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls)
    early_faults = {"partial_source_unit": "invalid_source_evidence", "unfinished_sentence": "required_source_missing"}
    assert len(calls) == (0 if fault in early_faults else 1)
    expected_reason = early_faults.get(fault, "invalid_semantic_mapping")
    assert caught.value.diagnostic["reason"] == expected_reason
    assert caught.value.diagnostic["applied_to_timeline"] is False


def test_distinct_primary_and_every_context_chapter_can_be_verified(monkeypatch):
    fixture = list(en_fixture())
    fixture[3] = [{"id": f"c{i}", "beats": [beat]} for i, beat in enumerate(fixture[1], 1)]
    fixture[4] = {"slots": [{"purpose": "result", "chapter_ids": ["c4"],
                              "required_context_chapter_ids": ["c2", "c3"]}]}
    reply = {"verdict": "fit", "keep_beat_ids": ["b2", "b3", "b4"], "released_optional_beat_ids": ["b1"],
             "slot_selections": [slot_proof(0, "result", ["b4"], ["b2", "b3"], fixture[1], fixture[2])]}
    result = review(monkeypatch, fixture, reply)
    assert set(result["slot_map"][0]["beat_ids"]) == {"b2", "b3", "b4"}
    assert result["slot_map"][0]["primary_beat_ids"] == ["b4"]
    assert result["slot_map"][0]["context_beat_ids"] == ["b2", "b3"]
    assert result["critic"]["verdict"] == "pass"
    assert result["critic"]["selection_changed_after_review"] is False
    assert result["critic"]["original_review"]["verdict"] == "revise"


def test_invalid_roles_below_target_do_not_claim_more_duration_fixes_the_story(monkeypatch):
    fixture = en_fixture()
    reply = proposal(fixture[-1])
    reply["slot_selections"][0]["primary_evidence_ids"] = []
    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, target_duration=40)
    assert caught.value.diagnostic["required_policy_minimum_seconds"] < 40
    assert "longer target alone does not verify" in str(caught.value)
    assert "needs at least" not in str(caught.value)


def test_style_duration_mode_still_requires_explicit_roles(monkeypatch):
    fixture = en_fixture()
    calls = []
    result = review(monkeypatch, fixture, proposal(fixture[-1]), calls, duration_mode="style")
    assert result["semantic_mapping_verified"] is True
    assert len(calls) == 1


def test_revision_preserves_cancellation_during_the_one_request(monkeypatch):
    fixture = en_fixture()
    class Cancelled(RuntimeError):
        pass
    cancellation = Cancelled("cancelled")
    calls = []
    def respond(_settings, _payload, _timeout, cancel_check):
        calls.append(1)
        cancel_check()
    def cancel_check():
        if calls:
            raise cancellation
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    with pytest.raises(Cancelled) as caught:
        intelligence._review_story_target_budget(Settings(), *fixture[:3], fixture[3], {}, fixture[4],
            {"goal": "short", "duration_mode": "target", "target_duration": 20}, "fixture-model", cancel_check)
    assert caught.value is cancellation
    assert len(calls) == 1


def test_revision_preserves_full_multisegment_source_evidence(monkeypatch):
    fixture = en_fixture()
    fixture[1][1]["text"] = ("A long complete premise with a middle-only dependency. " * 300).rstrip()
    fixture[2][1]["text"] = fixture[1][1]["text"]
    fixture[1][1]["segment_ids"].append("s2b")
    fixture[2][1]["end"] = 14
    fixture[2].append({"id": "s2b", "start": 14, "end": 19.64, "text": "A second complete sentence."})
    fixture[1][1]["text"] += " A second complete sentence."
    calls = []
    result = review(monkeypatch, fixture, proposal(fixture[-1], beats=fixture[1], segments=fixture[2]),
                    calls, target_duration=40, duration_mode="style")
    payload = json.loads(calls[0]["messages"][1]["content"])
    unit = next(row for row in payload["source_units"] if row["id"] == "b2")
    assert unit["text"] == fixture[1][1]["text"]
    assert unit["segments"] == [{key: row[key] for key in ("id", "start", "end")}
                                for row in (fixture[2][1], fixture[2][-1])]
    assert result["semantic_mapping_verified"] is True


@pytest.mark.parametrize("mode,accepted", [("target", False), ("style", True)])
def test_tiny_but_coherent_selection_cannot_satisfy_target_by_underfilling(monkeypatch, mode, accepted):
    fixture = list(en_fixture())
    fixture[0] = {"keep_beat_ids": ["b1"], "slot_map": [], "critic": {}}
    fixture[4] = {"slots": [{"purpose": "premise", "chapter_ids": ["c1"], "required_context_chapter_ids": []}]}
    reply = {"verdict": "fit", "keep_beat_ids": ["b1"], "released_optional_beat_ids": [],
             "slot_selections": [slot_proof(0, "premise", ["b1"], [], fixture[1], fixture[2])]}
    calls = []
    if accepted:
        assert review(monkeypatch, fixture, reply, calls, duration_mode=mode)["semantic_mapping_verified"] is True
    else:
        with pytest.raises(intelligence.StoryBudgetError) as caught:
            review(monkeypatch, fixture, reply, calls, duration_mode=mode)
        assert caught.value.diagnostic["reason"] == "target_underfill"
        assert "2.34 seconds" in str(caught.value)
    assert len(calls) == 1


def test_planner_and_critic_receive_the_exact_pause_policy_costs(monkeypatch):
    selection, beats, segments, chapters, plan = en_fixture()
    calls = []
    def respond(_settings, payload, *_args):
        calls.append(json.loads(payload["messages"][1]["content"]))
        if "Story Producer" in payload["messages"][0]["content"]:
            return plan
        return {"verdict": "pass", "add_beat_ids": [], "remove_beat_ids": [], "issues": [], "summary": ""}
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    brief = {"goal": "short", "duration_mode": "target", "target_duration": 20}
    intelligence._build_story_plan(Settings(), [{"id": "c1"}], {}, brief, "fixture-model", segments=segments, chapters=chapters)
    intelligence._critic_story_selection(Settings(), selection, beats, {}, plan, brief, "fixture-model", segments=segments)
    assert calls[0]["source_beat_costs"][1]["duration_cost"]["minimum_safe_seconds"] == pytest.approx(9.66)
    assert calls[1]["current_cost"]["minimum_safe_seconds"] == pytest.approx(21.46)
    assert calls[1]["candidates"][2]["duration_cost"]["minimum_safe_seconds"] == pytest.approx(7.54)


def test_real_hierarchy_reviews_critic_addition_before_any_required_beat_pruning(monkeypatch):
    selection, beats, segments, chapters, plan = en_fixture()
    selection = copy.deepcopy(selection)
    selection.pop("critic")
    selection["keep_beat_ids"] = ["b1", "b2", "b4"]
    chapters[0].update(start=.59, end=41.31, duration=40.72, beat_ids=[row["id"] for row in beats])
    monkeypatch.setattr(intelligence, "_ready_story_model_status", lambda *_args: {"selected_model": "fixture-model"})
    monkeypatch.setattr(intelligence, "build_story_chapters", lambda *_args, **_kwargs: chapters)
    monkeypatch.setattr(intelligence, "_summarize_story_chapters", lambda *_args: [{"id": "c1"}])
    monkeypatch.setattr(intelligence, "_build_global_outline", lambda *_args: {})
    monkeypatch.setattr(intelligence, "_build_story_plan", lambda *_args: plan)
    monkeypatch.setattr(intelligence, "_select_story_beats", lambda *_args: (copy.deepcopy(selection), beats))
    monkeypatch.setattr(intelligence, "_fit_story_selection_to_budget", lambda *_args: (_ for _ in ()).throw(AssertionError("required story was pruned")))
    calls = []
    def respond(_settings, payload, *_args):
        calls.append(payload)
        if "continuity critic" in payload["messages"][0]["content"]:
            return {"verdict": "revise", "add_beat_ids": ["b3"], "remove_beat_ids": [], "issues": ["needs premise context"], "summary": ""}
        return proposal(plan, beats=beats, segments=segments)
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", respond)
    decision, hierarchy = intelligence.hierarchical_story_edit(beats, segments, Settings(),
        {"goal": "short", "duration_mode": "target", "target_duration": 20})
    assert len(calls) == 2
    assert calls[1]["_single_attempt"] is True
    assert decision["story_beat_ids"] == ["b2", "b3", "b4"]
    assert hierarchy["critic"]["added"] == ["b3"]
    assert hierarchy["critic"]["unapplied_actions"] == []
    assert hierarchy["critic"]["verdict"] == "pass"
    assert hierarchy["selection"]["semantic_revision"]["attempts"] == 1


def critic_removed_ending_fixture():
    fixture = en_fixture()
    fixture[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    fixture[0]["critic"].update(selection_before=["b1", "b2", "b3", "b4"],
                                post_review_beat_ids=["b1", "b2", "b3"], requested_added=[], requested_removed=["b4"])
    fixture[0]["slot_map"][1]["role_evidence"] = "An unverified prior claim must not be presented as source fact."
    reply = {"verdict": "fit", "keep_beat_ids": ["b1", "b2", "b3"], "released_optional_beat_ids": [],
             "slot_selections": [slot_proof(index, slot["purpose"], [identifier], [identifier], fixture[1], fixture[2])
                                 for index, (slot, identifier) in enumerate(zip(fixture[-1]["slots"], ("b1", "b2", "b3", "b3")))]}
    return fixture, reply


def test_review_payload_distinguishes_current_ids_critic_removals_and_same_chapter_context(monkeypatch):
    fixture, reply = critic_removed_ending_fixture()
    original_schema = copy.deepcopy(intelligence.STORY_TARGET_REVISION_SCHEMA)
    calls = []
    result = review(monkeypatch, fixture, reply, calls)
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert payload["current_selected_beat_ids"] == ["b1", "b2", "b3"]
    assert payload["critic_already_removed_beat_ids"] == ["b4"]
    assert payload["allowed_optional_release_beat_ids"] == ["b1", "b2", "b3"]
    assert "current_selection" not in payload
    assert "role_evidence" not in json.dumps(payload["provisional_prior_slot_map"])
    for row in payload["slot_requirements"]:
        assert type(row["slot_index"]) is int
        assert row["allowed_primary_beat_ids_by_chapter"] == {"c1": ["b1", "b2", "b3"]}
        assert row["required_context_beat_ids_by_chapter"] == {"c1": ["b1", "b2", "b3"]}
        assert row["same_beat_may_supply_primary_and_context"] is True
    schema = calls[0]["format"]
    assert schema["properties"]["keep_beat_ids"]["items"]["enum"] == ["b1", "b2", "b3"]
    assert schema["properties"]["released_optional_beat_ids"]["items"]["enum"] == ["b1", "b2", "b3"]
    slot_properties = schema["properties"]["slot_selections"]["items"]["properties"]
    assert slot_properties["context_beat_ids"]["items"]["enum"] == ["b1", "b2", "b3"]
    assert slot_properties["context_beat_ids"]["minItems"] == 1
    assert slot_properties["primary_beat_ids"]["minItems"] == 1
    catalog = story_evidence.build_story_evidence_catalog(fixture[1], fixture[2], allowed_beat_ids={"b1", "b2", "b3"})
    known_evidence_ids = [row["id"] for row in catalog]
    for key in ("primary_evidence_ids", "context_evidence_ids"):
        assert slot_properties[key]["items"]["enum"] == known_evidence_ids
    assert slot_properties["temporal_witness_id"]["enum"] == known_evidence_ids
    assert "role_evidence" not in slot_properties
    assert intelligence.STORY_TARGET_REVISION_SCHEMA == original_schema
    assert result["semantic_revision"]["released_optional_beat_ids"] == []
    assert result["semantic_revision"]["cost"]["minimum_safe_seconds"] == pytest.approx(19.32)
    assert result["critic"]["removed"] == ["b4"]
    assert len(calls) == 1


@pytest.mark.parametrize("fault", ["already_removed_release", "same_chapter_context_omitted"])
def test_fresh_revision_ambiguities_remain_validation_errors(monkeypatch, fault):
    fixture, reply = critic_removed_ending_fixture()
    if fault == "already_removed_release":
        reply["released_optional_beat_ids"] = ["b4"]
    else:
        for row in reply["slot_selections"]:
            row["context_beat_ids"] = []
    calls = []
    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls)
    assert caught.value.diagnostic["reason"] == "invalid_semantic_mapping"
    assert len(calls) == 1


def test_no_fit_stays_representable_when_no_optional_release_is_allowed(monkeypatch):
    fixture = en_fixture()
    fixture[0]["critic"]["requested_added"] = ["b1", "b2", "b3", "b4"]
    calls = []
    with pytest.raises(intelligence.StoryBudgetError):
        review(monkeypatch, fixture, {"verdict": "no_fit", "keep_beat_ids": [],
                                     "released_optional_beat_ids": [], "slot_selections": []}, calls)
    properties = calls[0]["format"]["properties"]
    assert properties["released_optional_beat_ids"]["maxItems"] == 0
    assert "enum" not in properties["released_optional_beat_ids"]["items"]
    for key in ("keep_beat_ids", "released_optional_beat_ids", "slot_selections"):
        assert properties[key].get("minItems", 0) == 0


def test_final_payload_excludes_rejected_source_text_and_stale_model_claims(monkeypatch):
    fixture, reply = critic_removed_ending_fixture()
    rejected_text = "REJECTED_B4_ONLY: an unsupported dramatic ending."
    stale_claim = "STALE_MODEL_CLAIM_MUST_NOT_BECOME_SOURCE_EVIDENCE"
    fixture[1][3]["text"] = fixture[2][3]["text"] = rejected_text
    fixture[0].update(title=stale_claim, summary=stale_claim)
    fixture[0]["critic"].update(issues=[stale_claim], summary=stale_claim)
    fixture[-1]["narrative"] = stale_claim
    for slot in fixture[-1]["slots"]:
        slot["reason"] = stale_claim
    outline = {"premise": stale_claim, "audience_takeaway": stale_claim,
               "story_arc": [{"chapter_id": "c1", "function": "result", "why_it_matters": stale_claim}]}
    calls = []

    result = review(monkeypatch, fixture, reply, calls, outline=outline)

    assert len(calls) == 1
    sent = json.loads(calls[0]["messages"][1]["content"])
    encoded = json.dumps(sent)
    assert rejected_text not in encoded
    assert stale_claim not in encoded
    assert all(row["id"] != "b4" for row in sent["source_units"])
    assert result["keep_beat_ids"] == ["b1", "b2", "b3"]


def test_old_free_role_evidence_cannot_claim_typed_source_proof(monkeypatch):
    fixture = en_fixture()
    reply = proposal(fixture[-1])
    for row in reply["slot_selections"]:
        for key in ("primary_evidence_ids", "context_evidence_ids", "temporal_witness_id"):
            row.pop(key)
        row["role_evidence"] = "The source says Alpha beta, so this slot is verified."
    calls = []

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls)

    assert len(calls) == 1
    assert caught.value.diagnostic["reason"] == "invalid_semantic_mapping"


@pytest.mark.parametrize("fault", ["unrelated_primary_quote", "missing_context_quote", "unrelated_witness"])
def test_source_citations_must_belong_to_each_assigned_role(monkeypatch, fault):
    fixture = en_fixture()
    reply = proposal(fixture[-1])
    row = reply["slot_selections"][0]
    if fault == "unrelated_primary_quote":
        row["primary_evidence_ids"] = evidence_ids(fixture[1], fixture[2], ["b3"])
    elif fault == "missing_context_quote":
        row["context_evidence_ids"] = []
    else:
        row["temporal_witness_id"] = evidence_ids(fixture[1], fixture[2], ["b3"])[0]
    calls = []

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls)

    assert len(calls) == 1
    assert caught.value.diagnostic["reason"] == "invalid_semantic_mapping"


def test_configured_role_witnesses_cannot_reverse_source_chronology(monkeypatch):
    fixture = en_fixture()
    reply = proposal(fixture[-1], assignments=("b4", "b3", "b2", "b2"))
    calls = []
    style_profile = {"selection_policy": {"story_structure": ["premise", "setup", "evidence", "result"]}}

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls, style_profile=style_profile)

    assert len(calls) == 1
    assert caught.value.diagnostic["reason"] == "invalid_semantic_mapping"


def test_planner_no_fit_does_not_claim_a_fitting_current_selection_is_infeasible(monkeypatch):
    fixture, _ = critic_removed_ending_fixture()
    calls = []

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, {"verdict": "no_fit", "keep_beat_ids": [],
                                     "released_optional_beat_ids": [], "slot_selections": []}, calls)

    assert len(calls) == 1
    assert caught.value.diagnostic["reason"] == "planner_no_fit"
    assert caught.value.diagnostic["required_policy_minimum_seconds"] < 20
    assert "needs at least" not in str(caught.value)


def test_incomplete_sticky_context_fails_before_any_semantic_call(monkeypatch):
    fixture = en_fixture()
    fixture[1][2]["text"] = fixture[2][2]["text"] = "An unfinished required dependency"
    original = copy.deepcopy(fixture[0])
    calls = []

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, {"verdict": "no_fit", "keep_beat_ids": [],
                                     "released_optional_beat_ids": [], "slot_selections": []}, calls)

    assert calls == []
    assert caught.value.diagnostic["reason"] == "required_source_missing"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert fixture[0] == original


@pytest.mark.parametrize("release_explicit", [True, False], ids=["explicit_release", "silent_loss"])
def test_incomplete_optional_passage_requires_an_explicit_release(monkeypatch, release_explicit):
    fixture = en_fixture()
    fixture[1][0]["text"] = fixture[2][0]["text"] = "An optional introduction without a complete ending"
    reply = proposal(fixture[-1], beats=fixture[1], segments=fixture[2])
    if not release_explicit:
        reply["released_optional_beat_ids"] = []
    calls = []

    if release_explicit:
        result = review(monkeypatch, fixture, reply, calls)
        assert result["keep_beat_ids"] == ["b2", "b3", "b4"]
        assert result["semantic_revision"]["released_optional_beat_ids"] == ["b1"]
    else:
        with pytest.raises(intelligence.StoryBudgetError) as caught:
            review(monkeypatch, fixture, reply, calls)
        assert caught.value.diagnostic["reason"] == "invalid_semantic_mapping"
    assert len(calls) == 1
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert "b1" in payload["current_selected_beat_ids"]
    assert "b1" in payload["allowed_optional_release_beat_ids"]
    assert all(row["id"] != "b1" for row in payload["source_units"])


def test_over_budget_proposal_reports_its_own_cost_without_claiming_global_infeasibility(monkeypatch):
    fixture = en_fixture()
    fixture[0]["keep_beat_ids"] = ["b1", "b2", "b3"]
    fixture[0]["critic"].update(selection_before=["b1", "b2", "b3"],
                               post_review_beat_ids=["b1", "b2", "b3"], requested_added=[], requested_removed=[])
    reply = proposal(fixture[-1], assignments=("b1", "b2", "b3", "b4"))
    reply["keep_beat_ids"] = ["b1", "b2", "b3", "b4"]
    reply["released_optional_beat_ids"] = []
    calls = []

    with pytest.raises(intelligence.StoryBudgetError) as caught:
        review(monkeypatch, fixture, reply, calls)

    assert len(calls) == 1
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "required_selection_exceeds_target"
    assert diagnostic["required_policy_minimum_seconds"] == pytest.approx(19.32)
    assert diagnostic["proposed_revision_cost"]["minimum_safe_seconds"] == pytest.approx(21.46)
    assert diagnostic["proposed_revision_cost"]["fits_target"] is False
    assert "Allowed complete source constraints require at least" not in str(caught.value)
