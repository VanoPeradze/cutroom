"""Critic requests are proposals; one existing final review decides their fate."""
from __future__ import annotations

import copy
import io
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style


PURPOSE = story.SINGLE_PASSAGE_PURPOSE
SETTINGS = SimpleNamespace(ai={"performance_mode": "balanced"})


@pytest.fixture(autouse=True)
def no_real_inference(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Proposal authority tests must not perform real inference")
    monkeypatch.setattr(story, "_call_ollama_story_pass", forbidden)


def fixture(language="en", *, target=20, initial=None):
    texts = (["I missed the bus because I left late.", "The next day I left early and caught the bus.",
              "The weather forecast predicts rain."] if language == "en" else
             ["פספסתי את האוטובוס כי יצאתי מאוחר.", "למחרת יצאתי מוקדם והספקתי לאוטובוס.",
              "תחזית מזג האוויר צופה גשם."])
    instruction = ("Choose one coherent self-contained passage. Preserve meaning and complete sentences." if language == "en" else
                   "בחר קטע אחד ברור ועצמאי. שמור על המשמעות ועל משפטים שלמים.")
    segments = story.enrich_segments([{"id": f"s{i+1}", "start": i*10., "end": (i+1)*10., "text": text}
                                     for i, text in enumerate(texts)], language)
    beats = [{"id": f"b{i+1}", "start": row["start"], "end": row["end"], "duration": 10.,
              "segment_ids": [row["id"]], "text": row["text"]} for i, row in enumerate(segments)]
    chapters = [{"id": "c1", "start": 0., "end": 30., "beats": beats}]
    plan = {"slots": [{"purpose": PURPOSE, "chapter_ids": ["c1"], "required_context_chapter_ids": [],
                       "desired_seconds": target}]}
    brief = enrich_brief_with_style({"goal": "short", "instruction": instruction,
                                    "target_duration": target, "duration_mode": "target"})
    _, catalog = story._precision_story_payload(beats, segments, chapters, [], {}, plan, brief, "fixture", "balanced", target)
    chosen = initial or ["b1", "b2", "b3"]
    choices = [f"{row['text']} [{row['id']}]" for row in catalog if row["beat_id"] in chosen]
    proposal = {"verdict": "fit", "role_selections": {PURPOSE: {
        "primary_anchor_choice": choices[-1], "additional_primary_evidence_choices": choices[:-1],
        "context_evidence_choices_by_chapter": {}}}, "highlight_beat_ids": [],
        "title": "Unverified proposal", "summary": "Unverified interpretation"}
    selection = story._decode_precision_story_selection(proposal, catalog, beats, segments, chapters, plan, brief)
    return {"selection": selection, "catalog": catalog, "beats": beats, "segments": segments,
            "chapters": chapters, "plan": plan, "brief": brief}


def evidence_id(data, beat):
    return next(row["id"] for row in data["catalog"] if row["beat_id"] == beat)


def critic_reply(data, *, action="remove", beat="b1", evidence=True):
    other = "b2" if beat != "b2" else "b1"
    explanation = ("Removing this destroys prerequisite context." if beat == "b1" and action == "remove" else
                   "The source action needs final semantic reconsideration.")
    result = {"verdict": "revise", "add_beat_ids": [beat] if action == "add" else [],
              "remove_beat_ids": [beat] if action == "remove" else [], "issues": [explanation],
              "summary": explanation, "style_notes": []}
    if evidence:
        result["action_evidence"] = [{"action": action, "beat_id": beat,
            "defect_kind": "off_topic" if beat == "b3" and action == "remove" else "missing_context",
            "source_evidence_ids": [evidence_id(data, beat), evidence_id(data, other)],
            "instruction_quote": "", "explanation": explanation}]
    return result


def run_critic(monkeypatch, data, reply):
    monkeypatch.setattr(story, "_call_ollama_story_pass", lambda *_args, **_kwargs: copy.deepcopy(reply))
    return story._critic_story_selection(SETTINGS, data["selection"], data["beats"], {}, data["plan"], data["brief"],
                                         "fixture", segments=data["segments"])


def decision_row(data, *, action="remove", beat="b1", decision="decline"):
    return {"action": action, "beat_id": beat, "decision": decision,
            "source_evidence_ids": [evidence_id(data, beat)],
            "reason": "Decision based on the original complete source and instruction."}


def final_reply(data, selection, keep, decisions):
    choices = [f"{row['text']} [{row['id']}]" for row in data["catalog"] if row["beat_id"] in keep]
    return {"verdict": "fit", "keep_beat_ids": list(keep),
            "released_optional_beat_ids": [identifier for identifier in selection["keep_beat_ids"] if identifier not in keep],
            "role_selections": {PURPOSE: {"primary_anchor_choice": choices[-1],
                "additional_primary_evidence_choices": choices[:-1], "context_evidence_choices": []}},
            "critic_action_decisions": decisions}


def run_review(monkeypatch, data, selection, reply, calls=None):
    calls = [] if calls is None else calls
    def respond(_settings, payload, *_args):
        calls.append(copy.deepcopy(payload))
        if isinstance(reply, Exception):
            raise reply
        return copy.deepcopy(reply)
    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    return story._review_story_target_budget(SETTINGS, selection, data["beats"], data["segments"], data["chapters"],
                                            {}, data["plan"], data["brief"], "fixture")


@pytest.mark.parametrize("language", ["he", "en"])
def test_critic_proposal_does_not_change_original_selection_or_source(monkeypatch, language):
    data = fixture(language)
    original = copy.deepcopy(data)
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    assert data == original
    assert proposal["keep_beat_ids"] == ["b1", "b2", "b3"]
    assert proposal["critic"]["action_authority"] == "proposal"
    assert proposal["critic"]["proposed_beat_ids"] == ["b2", "b3"]
    additions, removals = story._critic_action_sets(proposal["critic"])
    assert not additions and not removals
    assert proposal["semantic_mapping_verified"] is False


@pytest.mark.parametrize("language", ["he", "en"])
def test_final_review_can_decline_contradictory_removal_and_render_original_context(monkeypatch, language):
    data = fixture(language)
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    original = copy.deepcopy((data, proposal))
    calls = []
    final = run_review(monkeypatch, data, proposal,
                       final_reply(data, proposal, ["b1", "b2"], [decision_row(data)]), calls)
    assert (data, proposal) == original
    payload = json.loads(calls[0]["messages"][1]["content"])
    assert {row["id"] for row in payload["source_units"]} == {"b1", "b2", "b3"}
    assert payload["source_evidence"] == data["catalog"]
    assert payload["rejected_beat_ids"] == []
    assert payload["sticky_critic_context_beat_ids"] == []
    assert "Removing this destroys prerequisite context." in json.dumps(payload)
    assert final["critic"]["action_authority"] == "final"
    assert final["critic"]["requested_removed"] == ["b1"]
    assert final["critic"]["accepted_removed"] == []
    assert final["critic"]["unapplied_actions"] == []
    assert any(row["beat_id"] == "b1" for row in final["critic"]["declined_proposals"])
    assert final["semantic_mapping_verified"] is True
    decision = story._story_decision_from_beats(final, data["beats"], data["segments"])
    assert decision and decision["keep_ids"] == ["s1", "s2"]
    assert decision["rejected_beat_ids"] == []


def test_final_prompt_requires_exact_role_coverage_independent_of_action_decisions(monkeypatch):
    data = fixture()
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    calls = []
    run_review(monkeypatch, data, proposal,
               final_reply(data, proposal, ["b1", "b2"], [decision_row(data)]), calls)
    instructions = calls[0]["messages"][0]["content"]
    assert ("Every retained beat must contribute at least one exact source_evidence_choices quotation in "
            "role_selections unless it is accepted sticky critic context.") in instructions
    assert ("A citation in critic_action_decisions alone does not assign that beat to a story role.") in instructions
    assert ("When the only role is self_contained_passage, put a substantive quotation from the latest retained "
            "beat in primary_anchor_choice, and exact supporting quotations from every other retained beat in "
            "additional_primary_evidence_choices.") in instructions
    assert ("Do not invent required context: keep context_evidence_choices=[] when required_context_chapter_ids "
            "is empty.") in instructions
    assert "Do not infer role assignments from a decision reason or rationale." in instructions
    assert "If no coherent fit can be verified, return no_fit" in instructions


@pytest.mark.parametrize("language", ["he", "en"])
def test_final_accepted_off_topic_removal_controls_source_and_render_mapping(monkeypatch, language):
    data = fixture(language)
    proposal = run_critic(monkeypatch, data, critic_reply(data, beat="b3"))
    final = run_review(monkeypatch, data, proposal, final_reply(data, proposal, ["b1", "b2"],
                       [decision_row(data, beat="b3", decision="accept")]))
    assert final["critic"]["accepted_removed"] == ["b3"]
    decision = story._story_decision_from_beats(final, data["beats"], data["segments"])
    assert decision and decision["keep_ids"] == ["s1", "s2"]
    assert decision["rejected_beat_ids"] == ["b3"] and decision["rejected_segment_ids"] == ["s3"]


@pytest.mark.parametrize("language", ["he", "en"])
def test_accepted_removal_cannot_satisfy_target_by_underfilling(monkeypatch, language):
    data = fixture(language, target=30)
    proposal = run_critic(monkeypatch, data, critic_reply(data, beat="b3"))
    original = copy.deepcopy((data, proposal))
    with pytest.raises(story.StoryBudgetError) as error:
        run_review(monkeypatch, data, proposal, final_reply(data, proposal, ["b1", "b2"],
                   [decision_row(data, beat="b3", decision="accept")]))
    assert error.value.diagnostic["reason"] == "target_underfill"
    assert (data, proposal) == original


@pytest.mark.parametrize("language", ["he", "en"])
def test_proposed_context_addition_is_not_sticky_before_final_acceptance(monkeypatch, language):
    data = fixture(language, initial=["b1", "b2"])
    proposal = run_critic(monkeypatch, data, critic_reply(data, action="add", beat="b3"))
    assert proposal["keep_beat_ids"] == ["b1", "b2"]
    assert proposal["critic"]["proposed_beat_ids"] == ["b1", "b2", "b3"]
    final = run_review(monkeypatch, data, proposal, final_reply(data, proposal, ["b1", "b2"],
                       [decision_row(data, action="add", beat="b3", decision="decline")]))
    assert final["critic"]["accepted_added"] == []
    assert final["keep_beat_ids"] == ["b1", "b2"]
    assert final["critic"]["unapplied_actions"] == []


@pytest.mark.parametrize("fault", ["missing_field", "missing_record", "uncertain", "unknown_reference",
                                    "wrong_owner", "duplicate_record", "accept_remove_but_keep", "extra_field"])
def test_final_missing_uncertain_or_inconsistent_action_decisions_cannot_approve(monkeypatch, fault):
    data = fixture()
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    reply = final_reply(data, proposal, ["b1", "b2"], [decision_row(data)])
    row = reply["critic_action_decisions"][0]
    if fault == "missing_field": reply.pop("critic_action_decisions")
    elif fault == "missing_record": reply["critic_action_decisions"] = []
    elif fault == "uncertain": row["decision"] = "uncertain"
    elif fault == "unknown_reference": row["source_evidence_ids"] = ["unknown"]
    elif fault == "wrong_owner": row["source_evidence_ids"] = [evidence_id(data, "b2")]
    elif fault == "duplicate_record": reply["critic_action_decisions"].append(copy.deepcopy(row))
    elif fault == "accept_remove_but_keep": row["decision"] = "accept"
    elif fault == "extra_field": row["confidence"] = 1.
    original = copy.deepcopy((data, proposal))
    with pytest.raises(story.StoryBudgetError):
        run_review(monkeypatch, data, proposal, reply)
    assert (data, proposal) == original
    assert proposal["semantic_mapping_verified"] is False


def test_ungrounded_initial_proposal_cannot_gain_approval_without_final_evidence(monkeypatch):
    data = fixture()
    proposal = run_critic(monkeypatch, data, critic_reply(data, evidence=False))
    assert proposal["keep_beat_ids"] == data["selection"]["keep_beat_ids"]
    assert proposal["critic"]["action_authority"] == "proposal"
    reply = final_reply(data, proposal, ["b1", "b2"], [decision_row(data)])
    reply["critic_action_decisions"][0]["source_evidence_ids"] = []
    with pytest.raises(story.StoryBudgetError):
        run_review(monkeypatch, data, proposal, reply)


def test_final_cannot_accept_removal_of_mandatory_source_context(monkeypatch):
    data = fixture()
    data["selection"]["required_context_beat_ids"] = ["b1"]
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    reply = final_reply(data, proposal, ["b2", "b3"], [decision_row(data, decision="accept")])
    with pytest.raises(story.StoryBudgetError) as error:
        run_review(monkeypatch, data, proposal, reply)
    assert error.value.diagnostic["reason"] in {"invalid_semantic_mapping", "required_source_missing"}


@pytest.mark.parametrize("language,instruction,roles", [
    ("en", "Use structure: result -> context.", ["result", "context"]),
    ("he", "מבנה: תוצאה -> הקשר.", ["תוצאה", "הקשר"]),
])
def test_explicit_role_order_is_not_replaced_by_neutral_proposal_authority(monkeypatch, language, instruction, roles):
    data = fixture(language)
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    # Free-form "Start with the result, then show the context" is documented
    # unverified wording in the partial parser; meaning still needs review.
    # This mechanical regression deliberately uses its supported role grammar.
    data["brief"] = enrich_brief_with_style({"goal": "short", "duration_mode": "target", "target_duration": 20,
                                             "instruction": instruction})
    assert story._configured_story_roles(data["brief"]) == roles
    assert story.required_story_role_orders(data["brief"]) == [roles]
    data["plan"] = {"slots": [{"purpose": purpose, "chapter_ids": ["c1"], "required_context_chapter_ids": []}
                               for purpose in reversed(roles)]}
    calls = []
    with pytest.raises(story.StoryPlanningError) as error:
        run_review(monkeypatch, data, proposal, final_reply(data, proposal, ["b1", "b2"], [decision_row(data)]), calls)
    assert error.value.diagnostic["reason"] == "invalid_explicit_story_roles"
    assert "reversed" in str(error.value)
    assert not calls


def test_explicit_no_cut_request_still_forbids_skipping_middle_source_unit(monkeypatch):
    data = fixture()
    data["brief"] = enrich_brief_with_style({**data["brief"],
        "instruction": "Choose one coherent passage. Keep the source passage continuous with no internal cuts."})
    assert story.explicit_source_continuity_requested(data["brief"])
    proposal = run_critic(monkeypatch, data, critic_reply(data, beat="b2"))
    reply = final_reply(data, proposal, ["b1", "b3"], [decision_row(data, beat="b2", decision="accept")])
    with pytest.raises(story.StoryPlanningError):
        run_review(monkeypatch, data, proposal, reply)


@pytest.mark.parametrize("failure", ["no_fit", "technical"])
def test_final_refusal_or_failure_preserves_originals_without_a_decision(monkeypatch, failure):
    data = fixture()
    proposal = run_critic(monkeypatch, data, critic_reply(data))
    original = copy.deepcopy((data, proposal))
    reply = ({"verdict": "no_fit", "keep_beat_ids": [], "released_optional_beat_ids": [], "role_selections": {},
              "critic_action_decisions": []} if failure == "no_fit" else RuntimeError("Synthetic reviewer failure"))
    with pytest.raises(story.StoryBudgetError):
        run_review(monkeypatch, data, proposal, reply)
    assert (data, proposal) == original
    assert proposal["semantic_mapping_verified"] is False


def test_action_sets_preserve_legacy_contract_but_never_enforce_pending_requests():
    raw = {"requested_added": ["b1"], "requested_removed": ["b2"]}
    added, removed = story._critic_action_sets(raw)
    assert set(added) == {"b1"} and set(removed) == {"b2"}
    added, removed = story._critic_action_sets({**raw, "action_authority": "proposal"})
    assert not added and not removed
    added, removed = story._critic_action_sets({**raw, "action_authority": "final",
                                              "accepted_added": [], "accepted_removed": ["b3"]})
    assert not added and set(removed) == {"b3"}


@pytest.mark.parametrize("streaming", [False, True])
def test_final_transport_rejects_duplicate_nested_action_decision(monkeypatch, streaming):
    from cutroom import cloud_ai

    data = fixture()
    proposal = run_critic(monkeypatch, data, critic_reply(data, beat="b3"))
    reply = final_reply(data, proposal, ["b1", "b2"],
                        [decision_row(data, beat="b3", decision="accept")])
    calls = []
    approved = run_review(monkeypatch, data, proposal, reply, calls)
    assert approved["critic"]["accepted_removed"] == ["b3"]
    request = calls[0]
    original = copy.deepcopy(request)
    assert request["_single_attempt"] is True
    assert request["_reject_duplicate_keys"] is True

    # This is an otherwise valid accepted-removal answer. Last-wins decoding
    # would silently erase its explicit uncertainty and retain only "accept".
    valid_json = json.dumps(reply)
    assert valid_json.count('"decision": "accept"') == 1
    duplicated = valid_json.replace('"decision": "accept"',
                                    '"decision": "uncertain", "decision": "accept"', 1)
    assert json.loads(duplicated)["critic_action_decisions"][0]["decision"] == "accept"
    envelope = {"message": {"content": duplicated}, "done": True, "done_reason": "stop"}
    sent = []

    def respond(http_request, **_kwargs):
        sent.append(json.loads(http_request.data.decode("utf-8")))
        body = json.dumps(envelope).encode("utf-8") + (b"\n" if streaming else b"")
        return io.BytesIO(body)

    monkeypatch.setattr(cloud_ai, "enabled", lambda _settings: False)
    monkeypatch.setattr(story, "open_ollama", respond)
    with pytest.raises(story.StoryPlanningError, match="invalid JSON"):
        story._call_ollama_strict(SETTINGS, request, cancel_check=(lambda: None) if streaming else None)
    assert len(sent) == 1
    assert request == original
