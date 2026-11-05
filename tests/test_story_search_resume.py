"""Resume selection orchestration; synthetic replies never establish edit quality.

These exercise the real window preparation/checkpoint/precision refusal path.
The model boundary is stubbed. Upstream Director ASR and hierarchical planning
resume require separate integration coverage; they are not executed here.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cutroom import intelligence
from cutroom.jobs import JobCancelled
from cutroom.story_budget import StoryBudgetError, StoryPlanningError
from test_single_passage_window_recovery import refusal, source


NOMINATION = ["b1", "b3", "b5"]  # Cannot be confused with a contiguous window.


class Settings:
    def __init__(self, directory: Path):
        self.cache_dir = directory
        self.ai = {"performance_mode": "balanced", "editor_model": "fixture:model", "max_story_beats": 72}
        self.raw = {"ai": self.ai, "context_policy": "fixture-four-unit-cap"}


def fixture_source(language="en"):
    beats, segments, chapters, summaries, brief, plan = source(language)
    template = segments[-1]["text"].split(". ", 1)[1]
    for index in range(9, 15):
        segment = {"id": f"s{index}", "start": (index - 1) * 10.0, "end": index * 10.0,
                   "text": f"{index}. {template}"}
        segments.append(segment)
        beats.append({"id": f"b{index}", "start": segment["start"], "end": segment["end"],
                      "duration": 10.0, "segment_ids": [segment["id"]], "text": segment["text"]})
    chapters[0].update(end=140.0, duration=140.0, beats=beats)
    summaries[0]["key_beat_ids"] = [row["id"] for row in beats]
    return {"beats": beats, "segments": segments, "chapters": chapters, "summaries": summaries,
            "outline": {}, "brief": brief, "plan": plan, "model": "fixture:model"}


def binding():
    return {"source_generation": "fixture-original-generation", "source_sha256": "a" * 64,
            "model_digest": "sha256:" + "b" * 64}


def install_bounded_context(monkeypatch, nominations):
    def fits(payload, _mode):
        data = json.loads(payload["messages"][1]["content"])
        return len(data.get("candidate_beats", [])) <= 4

    def nominate(_settings, candidates, *_args):
        nominations.append([row["id"] for row in candidates])
        by_id = {row["id"]: row for row in candidates}
        return [copy.deepcopy(by_id[identifier]) for identifier in NOMINATION], {
            "version": 1, "retrieved_candidate_ids": list(NOMINATION),
            "authority": "provisional_index_retrieval_requires_complete_source_validation"}

    monkeypatch.setattr(intelligence, "_story_payload_fits_cap", fits)
    monkeypatch.setattr(intelligence, "_retrieve_story_candidates", nominate)


def record_refusals(monkeypatch, calls, after_reply=None):
    def reply(_settings, payload, *_args):
        data = json.loads(payload["messages"][1]["content"])
        calls.append([row["id"] for row in data["candidate_beats"]])
        if after_reply is not None:
            after_reply()
        return refusal()

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", reply)


def prepare(settings, fixture, identity):
    return intelligence._prepare_story_window_search(
        settings, fixture["chapters"], fixture["summaries"], fixture["outline"], fixture["plan"],
        fixture["brief"], fixture["model"], fixture["segments"], identity,
    )


def select(settings, fixture, identity, cancel_check=None):
    return intelligence._select_story_beats(
        settings, fixture["chapters"], fixture["summaries"], fixture["outline"], fixture["plan"],
        fixture["brief"], fixture["model"], segments=fixture["segments"], cancel_check=cancel_check,
        search_identity=identity,
    )


def prime_eight(settings, fixture, identity, calls):
    prepared = prepare(settings, fixture, identity)
    assert prepared is not None
    windows = [[row["id"] for row in window] for window in prepared["windows"]]
    assert len(windows) == 11
    with pytest.raises(StoryPlanningError) as caught:
        select(settings, fixture, identity)
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "story_window_work_budget_exhausted"
    assert diagnostic["outcome"] == "technical_error" and diagnostic["applied_to_timeline"] is False
    review = diagnostic["source_retrieval"]["canonical_window_review"]
    assert review["planned_window_count"] == 11
    assert review["new_model_calls"] == 8 and review["reused_trials"] == 0
    assert review["search_status"] == "incomplete"
    assert calls == [NOMINATION, *windows[:8]]
    checkpoint = prepared["checkpoint"]
    state = json.loads(checkpoint.path.read_text(encoding="utf-8"))
    assert [row["window_ids"] for row in state["trials"]] == windows[:8]
    assert all(row["outcome"] == "no_fit" for row in state["trials"])
    return checkpoint, windows


@pytest.mark.parametrize("language", ["he", "en"])
def test_identical_resume_reuses_eight_and_calls_only_three_remaining_windows(tmp_path, monkeypatch, language):
    fixture, settings, identity = fixture_source(language), Settings(tmp_path / "cache"), binding()
    before = copy.deepcopy(fixture)
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    checkpoint, windows = prime_eight(settings, fixture, identity, calls)
    assert len(nominations) == 1
    calls.clear()

    def no_renomination(*_args):
        pytest.fail("A matching unfinished window search must not replay index nomination")

    monkeypatch.setattr(intelligence, "_retrieve_story_candidates", no_renomination)
    with pytest.raises(StoryBudgetError) as caught:
        select(settings, fixture, identity)
    diagnostic = caught.value.diagnostic
    review = diagnostic["source_retrieval"]["canonical_window_review"]
    assert calls == windows[8:] and NOMINATION not in calls
    assert review["reused_trials"] == 8 and review["new_model_calls"] == 3
    assert review["planned_window_count"] == len(review["trials"]) == 11
    assert review["search_status"] == "domain_exhausted"
    assert diagnostic["scope"] == "canonical_plan_domain_windows"
    assert diagnostic["outcome"] == "editorial_no_fit" and diagnostic["applied_to_timeline"] is False
    assert diagnostic["source_retrieval"]["resumed_without_index_renomination"] is True
    assert diagnostic.get("semantic_result_verified") is not True
    assert [row["window_ids"] for row in json.loads(checkpoint.path.read_text())["trials"]] == windows
    assert fixture == before


def test_cancellation_at_ninth_window_does_not_persist_its_uncommitted_reply(tmp_path, monkeypatch):
    fixture, settings, identity = fixture_source(), Settings(tmp_path / "cache"), binding()
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    checkpoint, windows = prime_eight(settings, fixture, identity, calls)
    saved = checkpoint.path.read_bytes()
    calls.clear()
    cancelled = [False]
    record_refusals(monkeypatch, calls, after_reply=lambda: cancelled.__setitem__(0, True))

    def cancel_check():
        if cancelled[0]:
            raise JobCancelled("Cancellation after reply, before completed-trial persistence")

    with pytest.raises(JobCancelled):
        select(settings, fixture, identity, cancel_check)
    assert calls == [windows[8]]
    assert checkpoint.path.read_bytes() == saved
    assert len(nominations) == 1
    calls.clear()
    record_refusals(monkeypatch, calls)
    with pytest.raises(StoryBudgetError):
        select(settings, fixture, identity)
    assert calls == windows[8:], "The cancelled ninth reply is retried; no unfinished result is cached"


@pytest.mark.parametrize("changed", ["source_hash", "source_text", "source_time", "model_digest", "model_tag",
                                     "original_instruction", "configuration", "plan"])
def test_changed_binding_restarts_exact_search_without_reusing_stale_refusals(tmp_path, monkeypatch, changed):
    fixture, settings, identity = fixture_source(), Settings(tmp_path / "cache"), binding()
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    old, _ = prime_eight(settings, fixture, identity, calls)
    old_bytes = old.path.read_bytes()
    if changed == "source_hash":
        identity["source_sha256"] = "c" * 64
    elif changed == "source_text":
        fixture["segments"][0]["text"] += " The original qualification remains unverified."
        fixture["beats"][0]["text"] = fixture["segments"][0]["text"]
    elif changed == "source_time":
        fixture["segments"][-1]["start"] += 0.125
        fixture["beats"][-1].update(start=fixture["segments"][-1]["start"], duration=9.875)
    elif changed == "model_digest":
        identity["model_digest"] = "sha256:" + "c" * 64
    elif changed == "model_tag":
        fixture["model"] = "fixture:other-model"
    elif changed == "original_instruction":
        fixture["brief"]["instruction"] += " Preserve the qualification."
    elif changed == "configuration":
        settings.raw["ai"]["max_story_beats"] = 64
    else:
        fixture["plan"]["slots"][0]["desired_seconds"] = 19.0
    calls.clear()
    new, _ = prime_eight(settings, fixture, identity, calls)
    assert new.fingerprint != old.fingerprint and new.path != old.path
    assert len(nominations) == 2
    assert old.path.read_bytes() == old_bytes


def test_forged_positive_checkpoint_cannot_supply_an_accepted_selection(tmp_path, monkeypatch):
    fixture, settings, identity = fixture_source(), Settings(tmp_path / "cache"), binding()
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    checkpoint, _ = prime_eight(settings, fixture, identity, calls)
    state = json.loads(checkpoint.path.read_text(encoding="utf-8"))
    state["trials"][0]["outcome"] = "fit"
    state["trials"][0]["scope"]["trial"].update(verdict="provisional_fit", selected_beat_ids=["b1", "b2"])
    checkpoint.path.write_text(json.dumps(state), encoding="utf-8")
    calls.clear()
    # Invalid positive state is rejected as a cache, never turned into a draft.
    fresh, _ = prime_eight(settings, fixture, identity, calls)
    assert fresh.fingerprint == checkpoint.fingerprint
    assert len(nominations) == 2


def test_positive_claim_disguised_as_negative_is_rechecked_instead_of_reused(tmp_path, monkeypatch):
    fixture, settings, identity = fixture_source(), Settings(tmp_path / "cache"), binding()
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    checkpoint, windows = prime_eight(settings, fixture, identity, calls)
    state = json.loads(checkpoint.path.read_text(encoding="utf-8"))
    state["trials"][0]["scope"]["trial"]["verdict"] = "provisional_fit"
    checkpoint.path.write_text(json.dumps(state), encoding="utf-8")
    calls.clear()
    with pytest.raises(StoryBudgetError) as caught:
        select(settings, fixture, identity)
    review = caught.value.diagnostic["source_retrieval"]["canonical_window_review"]
    assert calls == [windows[0], *windows[8:]]
    assert review["reused_trials"] == 7 and review["new_model_calls"] == 4
    assert review["search_status"] == "domain_exhausted"
    assert len(nominations) == 1
    assert caught.value.diagnostic["applied_to_timeline"] is False


@pytest.mark.parametrize("language", ["he", "en"])
def test_hierarchical_resume_reuses_validated_plan_without_repeating_understanding_or_nomination(
    tmp_path, monkeypatch, language,
):
    from cutroom import story_search_identity

    fixture, settings = fixture_source(language), Settings(tmp_path / "cache")
    # The hierarchical entry enriches this brief. Seed the exact same effective
    # request, rather than a superficially similar raw instruction/cache key.
    fixture["brief"] = intelligence.enrich_brief_with_style(fixture["brief"])
    source_bind = {"project_id": "synthetic-source", "source_generation": "fixture-generation",
                   "source_sha256": "a" * 64}
    immutable_model = {"provider": "ollama", "model": fixture["model"], "digest": "b" * 64}
    identity = {"source": source_bind, "model": immutable_model}
    nominations, calls = [], []
    install_bounded_context(monkeypatch, nominations)
    record_refusals(monkeypatch, calls)
    checkpoint, windows = prime_eight(settings, fixture, identity, calls)
    assert len(nominations) == 1
    calls.clear()
    story_cache = {"chapter_summaries": copy.deepcopy(fixture["summaries"]),
                   "outline": copy.deepcopy(fixture["outline"]),
                   "last_proposed_plan": copy.deepcopy(fixture["plan"])}
    before_cache, before_fixture = copy.deepcopy(story_cache), copy.deepcopy(fixture)

    def forbidden_replay(*_args, **_kwargs):
        pytest.fail("A matching hierarchical continuation must not replay understanding, planning or index nomination")

    for name in ("_build_story_plan", "_summarize_story_chapters", "_build_global_outline", "_retrieve_story_candidates"):
        monkeypatch.setattr(intelligence, name, forbidden_replay)
    monkeypatch.setattr(intelligence, "_ready_story_model_status", lambda *_a, **_k: {
        "selected_model": fixture["model"], "using_fallback": False,
    })
    monkeypatch.setattr(story_search_identity, "local_story_model_identity",
                        lambda _settings, model: copy.deepcopy(immutable_model) if model == fixture["model"] else None)
    monkeypatch.setattr(intelligence, "build_story_chapters", lambda *_a, **_k: copy.deepcopy(fixture["chapters"]))
    # This case isolates continuation orchestration. Cache-shape and source/model
    # identity validation retain their separate real-validator test coverage.
    monkeypatch.setattr(intelligence, "_story_cache_is_reusable", lambda *_a, **_k: True)
    with story_search_identity.story_search_source_context(source_bind):
        with pytest.raises(StoryBudgetError) as caught:
            intelligence.hierarchical_story_edit(
                fixture["beats"], fixture["segments"], settings, fixture["brief"], story_cache=story_cache,
            )

    diagnostic = caught.value.diagnostic
    review = diagnostic["source_retrieval"]["canonical_window_review"]
    assert calls == windows[8:] and NOMINATION not in calls
    assert review["reused_trials"] == 8 and review["new_model_calls"] == 3
    assert review["planned_window_count"] == len(review["trials"]) == 11
    assert review["search_status"] == "domain_exhausted"
    assert diagnostic["scope"] == "canonical_plan_domain_windows"
    assert diagnostic["outcome"] == "editorial_no_fit" and diagnostic["applied_to_timeline"] is False
    assert diagnostic.get("semantic_result_verified") is not True
    assert len(json.loads(checkpoint.path.read_text(encoding="utf-8"))["trials"]) == 11
    assert story_search_identity.current_story_search_source() is None
    assert story_cache == before_cache and fixture == before_fixture
