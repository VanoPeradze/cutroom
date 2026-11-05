"""Negative trial receipts are exact-domain hints, never cached edit approval."""
from __future__ import annotations

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from cutroom import story_search_checkpoint as checkpoint_module
from cutroom.story_search_checkpoint import (
    CHECKPOINT_VERSION, MAX_SCOPE_BYTES, MAX_STATE_BYTES, CheckpointBusy,
    CheckpointOwnershipError, SearchStatus, StorySearchCheckpoint, StorySearchCheckpointError,
)


def units(language="en", count=3):
    text = "Keep the original meaning and complete utterances."
    if language == "he":
        text = "שמור על משמעות הדיבור המקורית ועל משפטים שלמים."
    return [{"id": f"b{index}", "start": index * 30.0, "end": index * 30.0 + 25,
             "text": f"{text} {index}", "segment_ids": [f"s{index}"],
             "segments": [{"id": f"s{index}", "start": index * 30.0,
                           "end": index * 30.0 + 25, "text": f"{text} {index}"}]}
            for index in range(count)]


def identity():
    # In integration these are root-derived exact payload/config/source hashes.
    return {name: f"fingerprint-{name}" for name in
            ("brief", "style", "config", "model", "schema", "pipeline", "plan", "global_source")}


def cursor(tmp_path, *, source=None, key=None, windows=None):
    source = units() if source is None else source
    windows = [["b0", "b1"], ["b1", "b2"]] if windows is None else windows
    return StorySearchCheckpoint(tmp_path, identity() if key is None else key, source, windows)


def refusal(window):
    return {"trial": {"candidate_beat_ids": window, "verdict": "no_fit",
                      "precision": {"attempts": 1, "verdict": "no_fit",
                                    "reason": "The answer is incomplete.", "missing_purposes": ["result"]}}}


def budget_miss(window):
    return {"trial": {"candidate_beat_ids": window, "verdict": "provisional_budget_miss",
                      "proposal_budget": {"target_seconds": 60, "minimum_safe_seconds": 78,
                                          "approved_seconds": 78, "feasible": False}}}


@pytest.mark.parametrize("language", ["en", "he"])
def test_resume_preserves_exact_negative_scope_and_pending_tail(tmp_path, language):
    source = units(language)
    before = copy.deepcopy(source)
    first, last = ["b0", "b1"], ["b1", "b2"]
    with cursor(tmp_path, source=source) as search:
        assert search.status is SearchStatus.INCOMPLETE
        record = search.record(first, "no_fit", scope=refusal(first))
        assert search.completed(first) == record
        assert search.pending_windows() == [last]
        assert search.path == tmp_path / "story-window-search" / f"{search.fingerprint}.json"
    with cursor(tmp_path, source=source) as search:
        assert search.completed(first)["scope"] == refusal(first)
        search.record(last, "budget_miss", scope=budget_miss(last))
        assert search.status is SearchStatus.DOMAIN_EXHAUSTED
        assert not search.pending_windows()
        assert all(search.completed(window)["outcome"] in {"no_fit", "budget_miss"}
                   for window in (first, last))
    assert source == before


@pytest.mark.parametrize("field", list(identity()))
def test_all_caller_identity_changes_invalidate_resume(tmp_path, field):
    original = cursor(tmp_path)
    with original as search:
        search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
    changed = identity()
    changed[field] += "-changed"
    with cursor(tmp_path, key=changed) as search:
        assert search.fingerprint != original.fingerprint
        assert search.completed(["b0", "b1"]) is None


@pytest.mark.parametrize("field,value", [("text", "Changed canonical qualification."),
                                         ("start", .2), ("end", 24.5),
                                         ("segment_ids", ["different-source-id"])])
def test_full_canonical_evidence_is_part_of_key(tmp_path, field, value):
    original = cursor(tmp_path)
    source = units()
    source[0][field] = value
    assert cursor(tmp_path, source=source).fingerprint != original.fingerprint


def test_exact_unit_ids_and_ordered_domain_are_part_of_key(tmp_path):
    original = cursor(tmp_path)
    source = units()
    source[0]["id"] = "different"
    assert cursor(tmp_path, source=source, windows=[["different", "b1"], ["b1", "b2"]]).fingerprint != original.fingerprint
    assert cursor(tmp_path, windows=[["b1", "b2"], ["b0", "b1"]]).fingerprint != original.fingerprint


def test_raw_source_and_identity_are_not_written(tmp_path):
    key = identity()
    key["private_config"] = {"credential": "do-not-persist", "brief": "private exact brief"}
    with cursor(tmp_path, key=key) as search:
        search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
        saved = search.path.read_text(encoding="utf-8")
    assert "do-not-persist" not in saved and "private exact brief" not in saved
    assert units()[0]["text"] not in saved and "segments" not in saved


@pytest.mark.parametrize("outcome", ["accepted", "fit", "provisional_fit", "pending", "cancelled", "in_progress", None])
def test_no_positive_or_incomplete_trial_can_be_recorded(tmp_path, outcome):
    with cursor(tmp_path) as search:
        with pytest.raises(StorySearchCheckpointError):
            search.record(["b0", "b1"], outcome, scope={})
        assert search.completed(["b0", "b1"]) is None


def test_cancellation_keeps_only_completed_negatives_and_releases_lock(tmp_path):
    class Cancelled(Exception):
        pass
    with pytest.raises(Cancelled):
        with cursor(tmp_path) as search:
            search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
            raise Cancelled()
    with cursor(tmp_path) as resumed:
        assert resumed.completed(["b0", "b1"])["outcome"] == "no_fit"
        assert resumed.pending_windows() == [["b1", "b2"]]
        assert resumed.status is SearchStatus.INCOMPLETE


def test_discard_forces_revalidation_and_is_persistent(tmp_path):
    with cursor(tmp_path) as search:
        search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
        search.record(["b1", "b2"], "budget_miss", scope=budget_miss(["b1", "b2"]))
        assert search.status is SearchStatus.DOMAIN_EXHAUSTED
        assert search.discard(["b0", "b1"]) is True
        assert search.discard(["b0", "b1"]) is False
        assert search.status is SearchStatus.INCOMPLETE
    with cursor(tmp_path) as resumed:
        assert resumed.completed(["b0", "b1"]) is None
        assert resumed.completed(["b1", "b2"])["outcome"] == "budget_miss"


def test_returned_scope_and_input_mutation_cannot_change_owned_record(tmp_path):
    scope = refusal(["b0", "b1"])
    expected = copy.deepcopy(scope)
    with cursor(tmp_path) as search:
        result = search.record(["b0", "b1"], "no_fit", scope=scope)
        scope["trial"]["precision"]["reason"] = "mutated input"
        result["scope"]["trial"]["precision"]["reason"] = "mutated return"
        read = search.completed(["b0", "b1"])
        assert read["scope"] == expected
        read["scope"].clear()
        assert search.completed(["b0", "b1"])["scope"] == expected
        assert search.record(["b0", "b1"], "no_fit", scope=expected)["scope"] == expected
        with pytest.raises(StorySearchCheckpointError):
            search.record(["b0", "b1"], "budget_miss", scope={})


@pytest.mark.parametrize("scope", [{"reason": "x" * MAX_SCOPE_BYTES}, {"secret": "credential"},
                                  {"trial": {"text": "canonical source"}}, {"config": {"api_key": "x"}},
                                  {"duration": float("nan")}, {"value": object()}, {1: "non-string-key"}])
def test_scope_is_bounded_finite_json_without_raw_source_or_credentials(tmp_path, scope):
    with cursor(tmp_path) as search:
        with pytest.raises(StorySearchCheckpointError):
            search.record(["b0", "b1"], "no_fit", scope=scope)
        assert search.status is SearchStatus.INCOMPLETE


def test_atomic_write_failures_do_not_advance_or_forget_trials(tmp_path, monkeypatch):
    with cursor(tmp_path) as search:
        search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
        saved = search.path.read_bytes()
        def fail(*args, **kwargs):
            raise OSError("bounded simulated write failure")
        monkeypatch.setattr(checkpoint_module, "atomic_write_json", fail)
        with pytest.raises(OSError):
            search.record(["b1", "b2"], "budget_miss", scope=budget_miss(["b1", "b2"]))
        with pytest.raises(OSError):
            search.discard(["b0", "b1"])
        assert search.completed(["b0", "b1"]) is not None
        assert search.completed(["b1", "b2"]) is None
        assert search.path.read_bytes() == saved


@pytest.mark.parametrize("change", ["fingerprint", "domain", "version", "positive", "foreign", "duplicate", "scope", "extra"])
def test_stale_or_malformed_state_is_ignored_as_a_whole(tmp_path, change):
    saved_cursor = cursor(tmp_path)
    with saved_cursor as search:
        search.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
        state = json.loads(search.path.read_text(encoding="utf-8"))
    if change in {"fingerprint", "version"}:
        state[change] = "stale"
    elif change == "domain":
        state["domain_fingerprint"] = "foreign"
    elif change == "positive":
        state["trials"][0]["outcome"] = "accepted"
    elif change == "foreign":
        state["trials"][0]["window_ids"] = ["b0"]
    elif change == "duplicate":
        state["trials"].append(copy.deepcopy(state["trials"][0]))
    elif change == "scope":
        state["trials"][0]["scope"] = {"reason": "x" * MAX_SCOPE_BYTES}
    else:
        state["accepted"] = True
    saved_cursor.path.write_text(json.dumps(state), encoding="utf-8")
    with cursor(tmp_path) as resumed:
        assert resumed.completed(["b0", "b1"]) is None
        assert len(resumed.pending_windows()) == 2
        assert resumed.status is SearchStatus.INCOMPLETE


@pytest.mark.parametrize("raw", [b"not-json", b'{"version":1,"version":2}', b'{"x":NaN}',
                                 b"[" * 1100, b" " * (MAX_STATE_BYTES + 1)],
                         ids=["invalid-json", "duplicate-key", "nonfinite", "excessive-depth", "oversized-state"])
def test_invalid_bounded_reads_never_approve_or_exhaust(tmp_path, raw):
    saved_cursor = cursor(tmp_path)
    saved_cursor.path.parent.mkdir(parents=True)
    saved_cursor.path.write_bytes(raw)
    with cursor(tmp_path) as resumed:
        assert resumed.status is SearchStatus.INCOMPLETE
        assert len(resumed.pending_windows()) == 2


@pytest.mark.parametrize("windows", [[["b0", "b2"]], [["b1", "b0"], ["b2"]],
                                    [["b0", "b0"], ["b1", "b2"]], [["foreign"]],
                                    [["b0", "b1"]], [["b0", "b1"], ["b0", "b1"], ["b2"]]])
def test_foreign_reordered_duplicate_or_incomplete_domain_rejected(tmp_path, windows):
    with pytest.raises(StorySearchCheckpointError):
        cursor(tmp_path, windows=windows)


def test_canonical_object_windows_cannot_forge_evidence(tmp_path):
    source = units()
    windows = [copy.deepcopy(source[:2]), copy.deepcopy(source[1:])]
    search = cursor(tmp_path, source=source, windows=windows)
    with search:
        assert search.pending_windows() == [["b0", "b1"], ["b1", "b2"]]
        windows[0][0]["text"] = "forged meaning"
        with pytest.raises(StorySearchCheckpointError):
            search.completed(windows[0])


def test_unit_and_window_bounds_reject_instead_of_silently_capping(tmp_path):
    with pytest.raises(StorySearchCheckpointError):
        cursor(tmp_path, source=units(count=49), windows=[[f"b{n}"] for n in range(49)])
    source = units(count=48)
    with StorySearchCheckpoint(tmp_path, identity(), source, [[row["id"]] for row in source]) as search:
        assert len(search.pending_windows()) == 48
    with pytest.raises(StorySearchCheckpointError):
        StorySearchCheckpoint(tmp_path, identity(), source, [[row["id"]] for row in source] + [["b0", "b1"]])


@pytest.mark.parametrize("change", ["duplicate", "nan", "reverse", "empty_text", "boolean_clock"])
def test_invalid_canonical_identity_is_rejected_before_lock_or_load(tmp_path, change):
    source = units()
    if change == "duplicate":
        source[1]["id"] = "b0"
    elif change == "nan":
        source[0]["end"] = float("nan")
    elif change == "reverse":
        source.reverse()
    elif change == "empty_text":
        source[0]["text"] = " "
    else:
        source[0]["start"] = False
    with pytest.raises(StorySearchCheckpointError):
        cursor(tmp_path, source=source)
    assert not (tmp_path / "story-window-search").exists()


def test_concurrent_ownership_fails_immediately_and_wrong_thread_cannot_mutate_or_close(tmp_path):
    with cursor(tmp_path) as owned:
        def other_thread():
            with pytest.raises(CheckpointBusy):
                with cursor(tmp_path):
                    pass
            with pytest.raises(CheckpointOwnershipError):
                owned.record(["b0", "b1"], "no_fit", scope={})
            with pytest.raises(CheckpointOwnershipError):
                owned.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(other_thread).result(timeout=5)
        owned.record(["b0", "b1"], "no_fit", scope=refusal(["b0", "b1"]))
    with cursor(tmp_path) as resumed:
        assert resumed.completed(["b0", "b1"]) is not None


def test_stale_lock_is_not_deleted_or_taken_over(tmp_path):
    search = cursor(tmp_path)
    lock_dir = search.path.with_suffix(".lock")
    lock_dir.mkdir(parents=True)
    marker = lock_dir / "owner-stale.json"
    marker.write_text('{"pid":0,"nonce":"stale"}', encoding="utf-8")
    with pytest.raises(CheckpointBusy):
        with search:
            pass
    assert marker.read_text(encoding="utf-8") == '{"pid":0,"nonce":"stale"}'


def test_replaced_owner_marker_is_preserved_and_prevents_writes(tmp_path):
    search = cursor(tmp_path).__enter__()
    owner_path = search._owner_path
    assert owner_path is not None
    original = owner_path.read_bytes()
    foreign = b'{"nonce":"foreign-owner"}'
    owner_path.write_bytes(foreign)
    try:
        with pytest.raises(CheckpointOwnershipError):
            search.record(["b0", "b1"], "no_fit", scope={})
        with pytest.raises(CheckpointOwnershipError):
            search.close()
        assert owner_path.read_bytes() == foreign
    finally:
        # Restore only our test-owned nonce, then release normally.
        owner_path.write_bytes(original)
        search.close()


def test_cursor_requires_active_same_owner_context(tmp_path):
    search = cursor(tmp_path)
    with pytest.raises(CheckpointOwnershipError):
        search.pending_windows()
    with search:
        assert search.status is SearchStatus.INCOMPLETE
    with pytest.raises(CheckpointOwnershipError):
        search.completed(["b0", "b1"])
    search.close()
