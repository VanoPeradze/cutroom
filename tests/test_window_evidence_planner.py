"""Actual plan_edit boundary: deterministic evidence mapping, no inference/apply.

Synthetic controls and the private cached English comparator establish mapping
only. They cannot establish transcript truth, coherent editing or export quality.
"""
from __future__ import annotations

import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import inspect
import json
from pathlib import Path
import socket
from types import SimpleNamespace
import urllib.request

import pytest

from cutroom import ai_runtime, intelligence as story, window_evidence as bridge
from cutroom.edit_windows import (
    EditWindowError, SourceDescriptor, build_canonical_source, build_edit_window,
)
from cutroom.instruction_contract import effective_duration_bounds
from cutroom.story_budget import StoryBudgetError
from cutroom.story_evidence import build_story_evidence_catalog
from tests.portable_support.source_fixture import source_fixture, source_bytes, source_sha256


@pytest.fixture(autouse=True)
def no_model_or_network(monkeypatch):
    def forbidden(*_a, **_k):
        pytest.fail("Window evidence qualification may not call a model or network")
    for module in (story, ai_runtime):
        monkeypatch.setattr(module, "open_ollama", forbidden)
    for name in ("_call_ollama_story_pass", "_ollama_chat", "hierarchical_story_edit", "story_ai_status"):
        monkeypatch.setattr(story, name, forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def segments(language="en"):
    texts = (["I did not approve the change.", "The test had a clear purpose.",
              "The result contradicted our assumption.", "We revised the plan after the test.",
              "Another topic begins here."] if language == "en" else
             ["לא אישרתי את השינוי.", "לניסוי הייתה מטרה ברורה.",
              "התוצאה סתרה את ההנחה שלנו.", "שינינו את התוכנית בעקבות הניסוי.", "כאן מתחיל נושא אחר."])
    bounds = [(0., 15.), (15., 30.), (33., 48.), (50., 65.), (70., 85.)]
    return [{"id": f"s{i}", "start": a, "end": b, "text": text,
             "words": [{"word": text, "start": a, "end": b, "probability": .9}]}
            for i, ((a, b), text) in enumerate(zip(bounds, texts))]


def brief(language="en", instruction=None, **kw):
    instruction = instruction or ("Make one video. Aim for 45–60 seconds." if language == "en" else
                                  "צור סרטון אחד. כוון ל־45–60 שניות.")
    return {"goal": "short", "target_duration": 60., "duration_mode": "target", "language": language,
            "instruction": instruction, **kw}


def request(data=None, *, selection=(0, 2), origin=120., language="en", descriptor=None):
    data = segments(language) if data is None else data
    desc = descriptor or SourceDescriptor("primary:A", "generation-one", "transcript-one", 1000., origin)
    canonical = build_canonical_source(data, desc)
    views = tuple(build_edit_window(canonical, data[a]["id"], data[b]["id"])
                  for a, b in [(0, 1), (1, 2), (3, 3), (0, 3), (0, 0), (1, 1)])
    state = bridge.WindowSourceState("project_0123456789ab", 7, desc)
    return bridge.WindowEvidenceRequest(canonical, state, views, tuple(views[i].id for i in selection))


def run(req=None, data=None, instruction=None, language="en", reader=None, cache=None, cancel=None):
    data = segments(language) if data is None else data
    req = request(data, language=language) if req is None else req
    return story.plan_edit(data, SimpleNamespace(ai={}), brief(language, instruction), story_cache=cache,
                           cancel_check=cancel, source_window_request=req,
                           source_window_state=reader or (lambda: req.state))


@pytest.mark.parametrize("language", ["en", "he"])
def test_actual_planner_reuses_full_canonical_catalog_and_exact_original_ids(language):
    data = segments(language)
    req = request(data)
    original = copy.deepcopy(data)
    result, engine = run(req, data, language=language)
    effective = story.enrich_brief_with_style(brief(language))
    enriched = story.enrich_segments(data, language)
    beats = story.annotate_story_beats(story.build_story_beats(
        enriched, language, target_seconds=effective_duration_bounds(effective)["maximum_seconds"],
        independent_asr_entries=True), None)
    expected = build_story_evidence_catalog(beats, data)
    assert result["canonical_evidence"] == expected
    assert len({r["id"] for r in expected}) == len(expected)
    assert len(result["canonical_ownership"]) == len(data)
    assert {r["segment_id"] for r in result["canonical_ownership"]} == {r["id"] for r in data}
    # Overlap is represented only by repeated REFERENCES to the same quote ID.
    a, b = result["views"][:2]
    common = set(a["evidence_ids"]) & set(b["evidence_ids"])
    assert common and all(sum(r["id"] == ref for r in expected) == 1 for ref in common)
    assert data == original and result["original_request"] == brief(language)
    assert engine == "source_window_evidence_preview"
    assert result["editorial_status"] == "not_assessed"
    assert result["instruction_contract"]["verification_status"] == "unverified"


@pytest.mark.parametrize("language", ["en", "he"])
def test_selected_scope_does_not_leak_alternative_or_context_evidence_and_maps_offset(language):
    data = segments(language)
    req = request(data)
    result, _ = run(req, data, language=language)
    assert {r["segment_id"] for r in result["canonical_evidence"]} == {"s0", "s1", "s2", "s3", "s4"}
    assert {r["segment_id"] for r in result["selected_evidence"]} == {"s0", "s1", "s3"}
    selected = result["selection"]
    assert selected["row_ids"] == ["s0", "s1", "s3"] and selected["duration"] == 45.
    assert [(c["start"], c["end"], c["source_start"], c["source_end"]) for c in selected["clip_map"]] == [
        (0., 30., 120., 150.), (30., 45., 170., 185.)]
    assert [r["text"] for r in selected["exact_text_by_row"]] == [data[i]["text"] for i in (0, 1, 3)]
    evidence = result["selected_evidence"][0]
    assert (evidence["start"], evidence["end"]) == (0, 15)  # catalog clock is still raw ASR
    assert result["source_descriptor"]["asr_origin_seconds"] == 120
    view = result["views"][0]
    assert view["context_after_evidence_ids"]
    assert not set(view["context_after_evidence_ids"]) & set(view["evidence_ids"])


def test_empty_selection_stays_empty_not_full_evidence_or_a_draft():
    req = request(selection=())
    result, _ = run(req)
    assert result["selection"] is None and result["selected_evidence"] == []
    assert result["canonical_evidence"] and result["views"]
    assert not {"decision", "draft", "keep_ids", "semantic_mapping_verified", "applied_to_timeline"} & set(result)


@pytest.mark.parametrize("selection", [(0, 1), (2, 0)])
def test_overlapping_alternatives_are_allowed_but_selected_overlap_or_reorder_blocks(selection):
    req = request(selection=selection)
    with pytest.raises(EditWindowError, match="repeats, overlaps or reorders"):
        run(req)


@pytest.mark.parametrize("instruction", ["Choose one continuous source passage. Aim for 45–60 seconds.",
                                         "שמור על קטע המקור ללא חיתוכים. כוון ל־45–60 שניות."])
def test_no_cuts_blocks_selected_source_omission_but_retains_gap_inside_single_view(instruction):
    with pytest.raises(EditWindowError, match="no-cuts"):
        run(instruction=instruction)
    req = request(selection=(3,))
    with pytest.raises(EditWindowError, match="numeric"):
        run(req, instruction=instruction)  # Full uncut 65 sec cannot be called 45–60.
    req = replace(req, windows=(*req.windows, build_edit_window(req.source, "s0", "s2")),
                  selected_window_ids=(build_edit_window(req.source, "s0", "s2").id,))
    result, _ = run(req, instruction=instruction)
    assert result["selection"]["duration"] == 48
    assert result["selection"]["clip_map"][0]["source_end"] == 168
    assert result["views"][-1]["gaps"][0]["status"] == "untranscribed_unverified"


@pytest.mark.parametrize("instruction", ["Make exactly 60 seconds.", "צור סרטון של 60 שניות."])
def test_exact_target_is_not_overridden_by_shorter_valid_range_geometry(instruction):
    with pytest.raises(EditWindowError, match="numeric"):
        run(instruction=instruction)


@pytest.mark.parametrize("instruction", ["Choose one continuous source passage. Related cuts are allowed.",
                                         "בחר קטע מקור אחד רציף. אפשר לחתוך בין אמירות קשורות."])
def test_hard_cut_policy_conflicts_still_block_actual_planner(instruction):
    with pytest.raises(StoryBudgetError):
        run(instruction=instruction)


@pytest.mark.parametrize("change", [
    lambda d: d[4].update(text="Unselected source changed."),
    lambda d: d[0]["words"][0].update(probability=.8),
    lambda d: d[0].update(text="I approved the change."),
    lambda d: d.pop(),
])
def test_full_canonical_source_mismatch_blocks_even_when_selected_text_is_unchanged(change):
    data = segments()
    req = request(data)
    change(data)
    with pytest.raises(EditWindowError, match="full canonical"):
        run(req, data)


@pytest.mark.parametrize("state_change", [
    lambda s: replace(s, revision=s.revision+1),
    lambda s: replace(s, project_id="project_abcdef012345"),
    lambda s: replace(s, descriptor=replace(s.descriptor, asset_version="new-generation")),
    lambda s: replace(s, descriptor=replace(s.descriptor, transcript_version="new-transcript")),
])
@pytest.mark.parametrize("when", [1, 3])
def test_stale_project_or_source_blocks_before_work_or_before_return(state_change, when):
    req = request()
    calls = []
    def reader():
        calls.append(1)
        return state_change(req.state) if len(calls) >= when else req.state
    with pytest.raises(EditWindowError, match="changed during"):
        run(req, reader=reader)
    assert len(calls) == when


@pytest.mark.parametrize("when", ["start", "catalog", "last_state_read"])
def test_cancellation_does_not_publish_a_result_or_modify_cache(monkeypatch, when):
    req = request()
    cache = {"original_story": {"semantic_mapping_verified": True}}
    before = copy.deepcopy(cache)
    cancelled = [when == "start"]
    read_calls = []
    def check():
        if cancelled[0]:
            raise InterruptedError("cancelled")
    def reader():
        read_calls.append(1)
        if when == "last_state_read" and len(read_calls) == 3:
            cancelled[0] = True
        return req.state
    if when == "catalog":
        original = bridge.build_story_evidence_catalog
        def catalog(*args):
            result = original(*args)
            cancelled[0] = True
            return result
        monkeypatch.setattr(bridge, "build_story_evidence_catalog", catalog)
    with pytest.raises(InterruptedError):
        run(req, reader=reader, cache=cache, cancel=check)
    assert cache == before


def test_preview_cache_identity_is_namespaced_complete_and_does_not_reuse_semantic_cache():
    data = segments()
    req = request(data)
    cache = {"cache_key": "old-semantic-key", "decision": {"semantic_mapping_verified": True}}
    before = copy.deepcopy(cache)
    first, _ = run(req, data, cache=cache)
    again, _ = run(req, copy.deepcopy(data), cache=cache)
    assert first == again and cache == before
    assert first["cache_key"].startswith("window-planner-preview:")
    assert first["cache_reuse"] == "not_implemented_no_story_cache_read_or_write"
    variants = []
    variants.append(run(replace(req, selected_window_ids=(req.windows[1].id,)), data,
                        instruction="Make one video. Aim for 10–60 seconds.")[0])
    variants.append(run(replace(req, windows=tuple(reversed(req.windows))), data)[0])
    variants.append(run(replace(req, state=replace(req.state, revision=8)), data)[0])
    for desc in [replace(req.source.descriptor, asset_version="new"),
                 replace(req.source.descriptor, transcript_version="new"),
                 replace(req.source.descriptor, asr_origin_seconds=121)]:
        variants.append(run(request(data, descriptor=desc), data)[0])
    changed = copy.deepcopy(data)
    changed[-1]["text"] = "A changed unselected topic remains in the identity."
    variants.append(run(request(changed), changed)[0])
    variants.append(run(req, data, instruction="Make one video. Aim for 45–60 seconds. Preserve the original meaning.")[0])
    assert all(result["cache_key"] != first["cache_key"] for result in variants)
    assert all(result["editorial_status"] == "not_assessed" for result in variants)


def test_exported_catalog_and_views_are_detached_and_resolve_empty_scope_correctly():
    data = segments()
    req = request(data)
    result, _ = run(req, data)
    result["canonical_evidence"][0]["text"] = "altered"
    result["views"][0]["row_ids"].append("fake")
    again, _ = run(req, data)
    assert again["canonical_evidence"][0]["text"] == data[0]["text"]
    assert "fake" not in again["views"][0]["row_ids"]
    beats = story.build_story_beats(data, "en")
    index = bridge.build_canonical_evidence_index(req.source, beats)
    assert bridge.project_evidence(index, ()) == []
    with pytest.raises(EditWindowError, match="Unknown"):
        bridge.project_evidence(index, ("invented",))
    with pytest.raises(FrozenInstanceError):
        index.catalog_json = "[]"


def test_catalog_retains_old_unique_ownership_guard_and_requires_full_source_partition():
    data = segments()
    canonical = request(data).source
    beats = story.build_story_beats(data, "en")
    duplicate = copy.deepcopy(beats[0])
    duplicate["id"] = "another-owner"
    with pytest.raises(ValueError, match="ownership"):
        bridge.build_canonical_evidence_index(canonical, [*beats, duplicate])
    with pytest.raises(EditWindowError, match="complete source ownership"):
        bridge.build_canonical_evidence_index(canonical, beats[:-1])


def test_default_entry_ignores_brief_or_settings_toggle_and_preserves_old_flow(monkeypatch):
    calls = []
    def old_path(beats, enriched, *_args, **_kwargs):
        calls.append((beats, enriched))
        return {"keep_ids": [r["id"] for r in enriched], "remove_ids": []}, {"fixture": "old flow"}
    monkeypatch.setattr(story, "hierarchical_story_edit", old_path)
    monkeypatch.setattr(bridge, "validate_request_source", lambda *_a: pytest.fail("Disabled bridge ran"))
    monkeypatch.setattr(bridge, "prepare_window_planner_preview", lambda *_a: pytest.fail("Disabled bridge ran"))
    req = request()
    data = segments()
    result, engine = story.plan_edit(data, SimpleNamespace(ai={"source_windows_enabled": True}),
        brief(source_window_request=req, source_windows_enabled=True))
    assert len(calls) == 1 and "decision" in result and engine == "ollama_hierarchical_story"
    assert "views" not in result and "canonical_evidence" not in result
    assert inspect.signature(story.plan_edit).parameters["source_window_request"].default is None


def test_actual_project_state_file_is_not_saved_or_given_a_draft(tmp_path, monkeypatch):
    # Read-only current-state provider using a disposable test project file.
    req = request()
    path = tmp_path / "project.json"
    project = {"id": req.state.project_id, "revision": req.state.revision, "draft": {"existing_user_edit": True},
               "source_descriptor": copy.deepcopy(req.source.descriptor.__dict__)}
    path.write_text(json.dumps(project), encoding="utf8")
    before = path.read_bytes()
    def reader():
        d = json.loads(path.read_text(encoding="utf8"))
        return bridge.WindowSourceState(d["id"], d["revision"], SourceDescriptor(**d["source_descriptor"]))
    result, _ = run(req, reader=reader)
    assert path.read_bytes() == before
    assert "draft" not in result and "decision" not in result
    # A write occurring elsewhere is surfaced as stale, never overwritten.
    project["revision"] += 1
    path.write_text(json.dumps(project), encoding="utf8")
    latest = path.read_bytes()
    with pytest.raises(EditWindowError, match="changed during"):
        run(req, reader=reader)
    assert path.read_bytes() == latest


@pytest.mark.parametrize("bad_request", [False, {}, {"enabled": True}])
def test_untrusted_serialized_opt_in_is_rejected(bad_request):
    with pytest.raises(EditWindowError, match="immutable window request"):
        story.plan_edit(segments(), SimpleNamespace(ai={}), brief(), source_window_request=bad_request)


def test_opt_in_requires_fresh_state_reader_and_supported_scope():
    req = request()
    with pytest.raises(EditWindowError, match="reader"):
        story.plan_edit(segments(), SimpleNamespace(ai={}), brief(), source_window_request=req)
    with pytest.raises(ValueError, match="transcript-only Shorts"):
        story.plan_edit(segments(), SimpleNamespace(ai={}), brief(goal="podcast"),
                        source_window_request=req, source_window_state=lambda: req.state)
    with pytest.raises(ValueError, match="transcript-only Shorts"):
        story.plan_edit(segments(), SimpleNamespace(ai={}), brief(), visual_moments={},
                        source_window_request=req, source_window_state=lambda: req.state)


def test_portable_mapping_runs_through_actual_planner_with_unchanged_catalog_ids():
    raw = source_bytes()
    assert hashlib.sha256(raw).hexdigest() == source_sha256()
    data = json.loads(raw)["segments"]
    before = copy.deepcopy(data)
    desc = SourceDescriptor("supplied-english-diagnostic", "saved-receipt-not-media-hash", hashlib.sha256(raw).hexdigest(),
                            3505.002667, 120)
    canonical = build_canonical_source(data, desc)
    views = tuple(build_edit_window(canonical, a, b) for a, b in [
        ("s0004", "s0006"), ("s0012", "s0016"), ("s0025", "s0030"),
        ("s0004", "s0016"), ("s0010", "s0011")])
    req = bridge.WindowEvidenceRequest(canonical, bridge.WindowSourceState("project_0123456789ab", 1, desc),
                                       views, tuple(v.id for v in views[:3]))
    result, engine = run(req, data)
    selected = result["selection"]
    assert engine == "source_window_evidence_preview" and selected["duration"] == pytest.approx(49.25)
    assert len(result["canonical_ownership"]) == len(data) == 44
    assert len(result["canonical_evidence"]) > len(result["selected_evidence"])
    assert [r["text"] for r in selected["exact_text_by_row"]] == [r["text"] for r in data if r["id"] in set(selected["row_ids"])]
    assert [(c["source_start"], c["source_end"]) for c in selected["clip_map"]][0] == pytest.approx((139.42, 155.45))
    for fragment in result["selected_evidence"]:
        row = next(r for r in data if r["id"] == fragment["segment_id"])
        assert fragment["text"] == row["text"][fragment["char_start"]:fragment["char_end"]]
    assert result["editorial_status"] == "not_assessed" and "decision" not in result
    assert data == before and source_bytes() == raw
