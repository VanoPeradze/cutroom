"""Deterministic Director jobs and isolated proposal lifecycle, no inference."""
import copy
import pytest
from cutroom import director
from cutroom.ai_draft_proposals import ai_draft_review_status, ai_draft_proposal
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.sequence import editor_sequence_snapshot
from test_director_rebuild_cache import semantic_project

@pytest.mark.parametrize("sequence", [False, True])
def test_job_keeps_all_render_inputs_then_apply_undo_redo(semantic_project, sequence):
    store, settings, pid, calls, context = semantic_project
    if sequence:
        store.update(pid, lambda p: apply_manual_edit(p, {"action":"sequence_split_all", "time":10.}))
    before = store.load(pid)
    result = director.analyze_project(context(), pid, store, settings,
        {"edit_style":"competitive_clutch", "instruction":"Keep the strongest complete explanation."}, preserve_current_edit=True)
    saved = store.load(pid)
    for key in ("draft", "analysis", "settings", "manual", "name", "sources", "assets"):
        assert saved.get(key) == before.get(key), key
    assert result["proposal_only"] and result["timeline_preserved"] and not result["applied_to_timeline"]
    marker = saved["_ai_draft_proposal"]
    assert marker["version"] == 2 and result["draft"] == marker["candidate"]["draft"]
    assert result["proposal_origin_id"] == marker["id"]
    assert marker["request"]["instruction"] == "Keep the strongest complete explanation."
    assert marker["request"]["style"] == "competitive_clutch"
    status = ai_draft_review_status(saved); assert status["available"] and status["isolated"]
    from server import _public_project
    public = _public_project(saved)
    assert "_ai_draft_proposal" not in public and public["ai_draft_review"] == status
    assert public["draft"] == before["draft"]
    proposal = ai_draft_proposal(saved, status["origin_id"], {})
    assert proposal["apply_allowed"], proposal["apply_issue"]
    assert proposal["proposed"]["title"] == marker["candidate"]["draft"]["title"]
    apply_manual_edit(saved, {"action":"sequence_reset"}, apply_isolated_proposal=True)
    applied = copy.deepcopy(saved)
    assert saved["analysis"] == marker["candidate"]["analysis"]
    for key in ("settings", "name"):
        assert saved[key] == before[key]
    assert not ai_draft_review_status(saved)["available"]
    apply_manual_edit(saved, {"action":"undo"})
    assert saved["draft"] == before["draft"]
    assert saved["analysis"] == before["analysis"]
    assert editor_sequence_snapshot(saved) == editor_sequence_snapshot(before)
    assert ai_draft_review_status(saved)["origin_id"] == status["origin_id"]
    apply_manual_edit(saved, {"action":"redo"})
    assert saved["draft"] == applied["draft"] and saved["analysis"] == applied["analysis"]
    assert not ai_draft_review_status(saved)["available"]

@pytest.mark.parametrize("tamper", ["source", "candidate", "request"])
def test_isolated_tamper_fails_without_mutation(semantic_project, tamper):
    store, settings, pid, _, context = semantic_project
    director.analyze_project(context(), pid, store, settings, preserve_current_edit=True)
    p = store.load(pid)
    if tamper == "source": p["sources"]["A"]["generation"] = "replacement"
    elif tamper == "request": p["_ai_draft_proposal"]["request"]["instruction"] = "altered"
    else: p["_ai_draft_proposal"]["candidate"]["draft"]["title"] = "altered"
    before = copy.deepcopy(p)
    assert not ai_draft_review_status(p)["available"]
    with pytest.raises(ManualEditError): apply_manual_edit(p, {"action":"sequence_reset"}, apply_isolated_proposal=True)
    assert p == before

@pytest.mark.parametrize("command", ["shorter", "keep_more", "more_energy", "fewer_switches"])
def test_active_sequence_refine_never_commits_live_controls(semantic_project, command):
    store, settings, pid, _, context = semantic_project
    store.update(pid, lambda p: apply_manual_edit(p, {"action":"sequence_split_all", "time":10.}))
    before = store.load(pid)
    director.refine_project(context(), pid, store, settings, command)
    after = store.load(pid)
    for key in ("draft", "analysis", "settings", "manual", "name"):
        assert after[key] == before[key]
    assert ai_draft_review_status(after)["isolated"]


def test_routing_mismatch_review_blocks_and_apply_is_atomic(semantic_project):
    from cutroom.ai_draft_proposals import record_isolated_ai_draft
    store, settings, pid, _, _ = semantic_project
    p = store.load(pid)
    candidate = copy.deepcopy(p)
    candidate["analysis"]["audio_source"] = "B"
    candidate["draft"]["audio_source"] = "B"
    record_isolated_ai_draft(p, candidate)
    before = copy.deepcopy(p)
    status = ai_draft_review_status(p)
    review = ai_draft_proposal(p, status["origin_id"], {})
    assert not review["apply_allowed"] and "audio source" in review["apply_issue"]
    with pytest.raises(ManualEditError): apply_manual_edit(p, {"action":"sequence_reset"}, apply_isolated_proposal=True)
    assert p == before


def test_changed_transcript_with_user_captions_is_not_silently_remapped(semantic_project):
    from cutroom.ai_draft_proposals import record_isolated_ai_draft
    store, _, pid, _, _ = semantic_project
    p = store.load(pid)
    p["manual"]["caption_corrections"] = {"s1":"My precise wording"}
    candidate = copy.deepcopy(p)
    candidate["analysis"]["transcript"]["segments"][0]["text"] = "Different transcription"
    record_isolated_ai_draft(p, candidate)
    before = copy.deepcopy(p)
    review = ai_draft_proposal(p, ai_draft_review_status(p)["origin_id"], {})
    assert not review["apply_allowed"] and "caption" in review["apply_issue"]
    assert p == before


@pytest.mark.parametrize("sequence", [False, True])
def test_unchanged_variation_keeps_live_inputs_and_existing_candidate(semantic_project, sequence):
    store, settings, pid, _, context = semantic_project
    if sequence: store.update(pid,lambda p:apply_manual_edit(p,{"action":"sequence_split_all","time":10.}))
    director.analyze_project(context(),pid,store,settings,preserve_current_edit=True)
    before=store.load(pid)
    result=director.refine_project(context(),pid,store,settings,"new_variation",preserve_current_edit=True)
    after=store.load(pid)
    assert result["variation_changed"] is False
    assert "proposal_origin_id" not in result
    for key in ("draft","analysis","manual","settings","name","_ai_draft_proposal"):
        assert after.get(key)==before.get(key)


def test_preserve_flag_does_not_change_first_draft_behavior(semantic_project):
    store, settings, pid, _, context=semantic_project
    def reset(p):
        p.pop("draft",None);p.pop("analysis",None);p["manual"]={"cuts":[],"keeps":[],"camera_overrides":[]}
    store.update(pid,reset)
    result=director.analyze_project(context(),pid,store,settings,{"edit_style":"competitive_clutch"},preserve_current_edit=True)
    p=store.load(pid)
    assert not result["proposal_only"] and result["applied_to_timeline"]
    assert "proposal_origin_id" not in result
    assert p["draft"]["edit_style"]=="competitive_clutch"
    assert p["settings"]["edit_style"]=="competitive_clutch"
    assert "_ai_draft_proposal" not in p


def test_failed_protected_generation_retains_existing_candidate_and_state(semantic_project,monkeypatch):
    from cutroom.story_budget import StoryBudgetError
    store, settings, pid, _, context=semantic_project
    director.analyze_project(context(),pid,store,settings,preserve_current_edit=True)
    before=store.state_path(pid).read_bytes()
    def fail(*args,**kwargs):raise StoryBudgetError("Test planner rejection",{})
    monkeypatch.setattr(director,"_plan_edit_with_cancel",fail)
    with pytest.raises(StoryBudgetError):
        director.analyze_project(context(),pid,store,settings,{"instruction":"A different requested story"},preserve_current_edit=True)
    assert store.state_path(pid).read_bytes()==before


def test_plain_reset_never_consumes_candidate_and_later_history_stays_compact(semantic_project):
    store, settings, pid, _, context=semantic_project
    store.update(pid,lambda p:apply_manual_edit(p,{"action":"sequence_split_all","time":10.}))
    director.analyze_project(context(),pid,store,settings,{"edit_style":"competitive_clutch"},preserve_current_edit=True)
    p=store.load(pid);original=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"sequence_reset"})
    assert p["draft"]["engine"]==original["draft"]["engine"]
    assert ai_draft_review_status(p)["available"]
    assert "isolated_render_state" not in p["manual"]["_history"]["undo"][-1]["before"]
    apply_manual_edit(p,{"action":"undo"})
    apply_manual_edit(p,{"action":"sequence_reset"},apply_isolated_proposal=True)
    applied=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"sequence_split_all","time":10.})
    entry=p["manual"]["_history"]["undo"][-1]
    assert "isolated_render_state" not in entry["before"] and "isolated_render_state" not in entry["after"]
    apply_manual_edit(p,{"action":"undo"})
    apply_manual_edit(p,{"action":"undo"})
    assert p["analysis"]==original["analysis"] and p["draft"]["title"]==original["draft"]["title"]
    assert ai_draft_review_status(p)["available"]
    apply_manual_edit(p,{"action":"redo"})
    assert p["analysis"]==applied["analysis"] and p["draft"]==applied["draft"]
    apply_manual_edit(p,{"action":"redo"})
    # A consumed receipt must not break ordinary later Reset.
    apply_manual_edit(p,{"action":"sequence_reset"})
    assert not ai_draft_review_status(p)["available"]
