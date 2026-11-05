"""Whole-recording prompt and canonical retrieval acceptance; no model/network.

Synthetic HE/EN text establishes context accounting and exact attribution only.
It does not establish ASR or editorial quality on the supplied recording.
"""
from __future__ import annotations

import copy
import json

import pytest

from cutroom import intelligence
from cutroom.story_evidence import build_story_evidence_catalog


class Settings:
    ai = {"performance_mode": "balanced", "ollama_url": "http://127.0.0.1:11434"}


def test_story_policy_invalidates_old_decisions_without_repeating_asr(monkeypatch, tmp_path):
    from cutroom import cache_keys
    from types import SimpleNamespace

    source = tmp_path / "source.mp4"
    source.write_bytes(b"canonical-fixture-original")
    project = {"language": "auto", "sources": {"A": {"generation": "same-source",
               "relative_path": "media/source-A.mp4", "duration": 3600, "size": source.stat().st_size}, "B": None}}
    settings = SimpleNamespace(raw={}, ai={"performance_mode": "balanced"})
    brief = {"goal": "podcast", "performance_mode": "balanced", "spoken_language": "auto"}
    current = cache_keys.build_analysis_cache_fingerprints(project, settings, brief, {"A": source, "B": None})
    monkeypatch.setattr(cache_keys, "STORY_INPUT_POLICY", "full-chapter-input-v1")
    old = cache_keys.build_analysis_cache_fingerprints(project, settings, brief, {"A": source, "B": None})
    assert old["story"] != current["story"]
    assert {key: value for key, value in old.items() if key != "story"} == {
        key: value for key, value in current.items() if key != "story"}


def source_fixture(language="en"):
    segments, chapters, summaries = [], [], []
    for chapter_number in range(1, 21):
        chapter_id = f"chapter-{chapter_number:03d}"
        beats = []
        # Small edge chapters let precision retrieve complete first/tail units
        # while the unselected middle still exceeds the old global context cap.
        count = 1 if chapter_number in {1, 20} else 7
        for local in range(count):
            index = len(segments)
            segment_id, beat_id = f"segment-{index:04d}", f"beat-{index:04d}"
            if language == "he":
                body = "זהו מקור בדיקה סינתטי. הדובר מסביר תנאי חשוב ואינו טוען שהניסוי הצליח. " * 10
                end = "המסקנה נשארת מסויגת ולא הוכחה הצלחה."
            else:
                body = "This synthetic source preserves the qualification and does not claim that the experiment succeeded. " * 10
                end = "The final conclusion remains qualified; success was not established."
            text = f"BEGIN_{segment_id}. {body} END_{segment_id}. {end}"
            start = float(index * 25)
            segment = {"id": segment_id, "start": start, "end": start + 20.0,
                       "text": text, "words": [], "word_timing_complete": False}
            segments.append(segment)
            beats.append({"id": beat_id, "start": start, "end": start + 20.0,
                          "duration": 20.0, "text": text, "segment_ids": [segment_id]})
        chapters.append({"id": chapter_id, "start": beats[0]["start"], "end": beats[-1]["end"],
                         "duration": beats[-1]["end"] - beats[0]["start"], "beats": beats})
        summaries.append({"id": chapter_id, "start": beats[0]["start"], "end": beats[-1]["end"],
                          "title": f"Synthetic chapter {chapter_number}",
                          "summary": f"Unverified interpretation of {chapter_id}; full source remains canonical.",
                          "role": "development", "key_points": ["An interpretation requires source validation."],
                          "key_beat_ids": [beats[-1]["id"]], "depends_on": [], "unresolved_questions": []})
    roles = ["setup", "result"] if language == "en" else ["הקשר", "תוצאה"]
    instruction = "Structure: setup -> result." if language == "en" else "מבנה: הקשר -> תוצאה."
    brief = {"goal": "podcast", "duration_mode": "target", "target_duration": 60,
             "performance_mode": "balanced", "instruction": instruction,
             "spoken_language": language, "source_order": "chronological"}
    outline = {"premise": "Synthetic fixture for source attribution.", "audience_takeaway": "Keep qualifications.",
               "story_arc": [{"chapter_id": row["id"], "function": "development", "why_it_matters": "Source context."}
                             for row in chapters],
               "must_keep_chapter_ids": [chapters[0]["id"], chapters[-1]["id"]], "optional_chapter_ids": [],
               "dependency_pairs": [{"before": chapters[0]["id"], "after": chapters[-1]["id"], "reason": "Retain the setup."}]}
    plan = {"narrative": "Original setup and qualified conclusion in chronology.",
            "slots": [{"purpose": roles[0], "chapter_ids": [chapters[0]["id"]], "desired_seconds": 20,
                       "reason": "Retain original setup.", "required_context_chapter_ids": []},
                      {"purpose": roles[1], "chapter_ids": [chapters[-1]["id"]], "desired_seconds": 20,
                       "reason": "Retain the qualified source ending.", "required_context_chapter_ids": [chapters[0]["id"]]}]}
    return chapters, summaries, segments, brief, outline, plan


def leaf_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from leaf_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from leaf_strings(item)


def test_missing_retrieval_context_is_technical_error_not_source_wide_no_fit(monkeypatch):
    chapters, summaries, segments, brief, outline, plan = source_fixture()
    candidates = [*chapters[0]["beats"], *chapters[-1]["beats"]]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    first = candidates[0]["id"]

    def nominate_first_only(_settings, payload, *_args, **_kwargs):
        page_ids = {row["id"] for row in user_content(payload)["candidate_page"]}
        return {"candidate_beat_ids": [first] if first in page_ids else []}

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", nominate_first_only)
    make_precision = lambda _rows: ({"messages": [], "options": {"num_predict": 900}}, [])
    with pytest.raises(intelligence.StoryPlanningError) as caught:
        intelligence._retrieve_story_candidates(Settings(), candidates, chapters, summaries, outline, plan,
                                                brief, "fixture", "balanced", make_precision, None)
    assert {key: caught.value.diagnostic[key] for key in ("outcome", "reason", "applied_to_timeline")} == {
        "outcome": "technical_error", "reason": "story_retrieval_incomplete", "applied_to_timeline": False}
    domain_pages = [page for round_ in caught.value.diagnostic["source_retrieval"]["rounds"]
                    for page in round_["required_domain_pages"]]
    assert domain_pages and all(page["nominated_ids"] == [] for page in domain_pages)
    assert (chapters, summaries, segments, brief, outline, plan) == before


def test_retrieval_cancellation_precedes_model_requests_and_keeps_source(monkeypatch):
    from cutroom.jobs import JobCancelled
    chapters, summaries, segments, brief, outline, plan = source_fixture()
    candidates = [*chapters[0]["beats"], *chapters[-1]["beats"]]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", lambda *_a: pytest.fail("Cancelled retrieval called a model"))
    def cancel():
        raise JobCancelled("owned qualification cancelled")
    with pytest.raises(JobCancelled):
        intelligence._retrieve_story_candidates(Settings(), candidates, chapters, summaries, outline, plan,
                                                brief, "fixture", "balanced", lambda _rows: None, cancel)
    assert (chapters, summaries, segments, brief, outline, plan) == before


def capture_transport(monkeypatch, answer):
    """Exercise the real strict sizing boundary; intercept only local HTTP I/O."""
    captured = []

    class Response:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit):
            return json.dumps({"message": {"content": json.dumps(self.value, ensure_ascii=False)},
                               "done_reason": "stop"}, ensure_ascii=False).encode("utf-8")

    def respond(request, timeout=0):
        payload = json.loads(request.data.decode("utf-8"))
        captured.append(copy.deepcopy(payload))
        return Response(answer(payload) if callable(answer) else copy.deepcopy(answer))

    monkeypatch.setattr(intelligence, "open_ollama", respond)
    return captured


def user_content(payload):
    return json.loads(next(row["content"] for row in payload["messages"] if row["role"] == "user"))


def assert_large_old_catalog(chapters, segments, brief):
    catalog = build_story_evidence_catalog([beat for chapter in chapters for beat in chapter["beats"]], segments)
    old = {"messages": [{"role": "user", "content": json.dumps({"brief": brief, "source_evidence": catalog}, ensure_ascii=False)}],
           "format": {}, "options": {"num_ctx": 32768, "num_predict": 2200}}
    assert intelligence._story_prompt_tokens(old) + 2400 > 32768


@pytest.mark.parametrize("language", ["he", "en"])
@pytest.mark.parametrize("stage", ["outline", "plan"])
def test_large_global_passes_cover_whole_recording_inside_actual_transport_budget(monkeypatch, language, stage):
    fixture = source_fixture(language)
    chapters, summaries, segments, brief, outline, plan = fixture
    before = copy.deepcopy(fixture)
    assert_large_old_catalog(chapters, segments, brief)
    captured = capture_transport(monkeypatch, outline if stage == "outline" else plan)

    if stage == "outline":
        result = intelligence._build_global_outline(Settings(), summaries, brief, "synthetic-local-model",
                                                     chapters=chapters, segments=segments)
        assert result["story_arc"][-1]["chapter_id"] == chapters[-1]["id"]
    else:
        result = intelligence._build_story_plan(Settings(), summaries, outline, brief, "synthetic-local-model",
                                                 chapters=chapters, segments=segments)
        assert [row["purpose"] for row in result["slots"]] == [row["purpose"] for row in plan["slots"]]

    assert fixture == before
    assert len(captured) == 1
    request = captured[0]
    assert request["options"]["num_ctx"] <= 32768
    assert intelligence._story_prompt_fits(request)
    content = user_content(request)
    assert content["brief"] == brief
    if stage == "plan":
        assert content["outline"] == outline
    assert content["source_index"]["interpretation_status"] == "unverified_summary_index"
    available = set(leaf_strings(content["source_index"]))
    assert {row["id"] for row in chapters} <= available
    assert {beat["id"] for chapter in chapters for beat in chapter["beats"]} <= available
    assert {segment["id"] for segment in segments} <= available
    # Tail and every intervening chapter must remain available, not first-N.
    assert len(content["source_index"]["chapters"]) == len(chapters)
    assert len(content["source_index"]["source_beat_index"]) == sum(len(row["beats"]) for row in chapters)
    assert not content.get("source_evidence")


def precision_answer(payload):
    content = user_content(payload)
    choices = intelligence._story_evidence_choice_catalog(content["source_evidence"])
    by_segment = {}
    for choice, row in choices.items():
        by_segment.setdefault(row["segment_id"], []).append(choice)
    utterances = content["source_utterances"]
    first = by_segment[utterances[0]["id"]][0]
    last = by_segment[utterances[-1]["id"]][-1]
    slots = content["plan"]["slots"]
    context_id = slots[-1]["required_context_chapter_ids"][0]
    return {"verdict": "fit", "role_selections": {
        slots[0]["purpose"]: {"primary_anchor_choice": first, "additional_primary_evidence_choices": [],
                              "context_evidence_choices_by_chapter": {}},
        slots[-1]["purpose"]: {"primary_anchor_choice": last, "additional_primary_evidence_choices": [],
                               "context_evidence_choices_by_chapter": {context_id: [first]}}},
        "highlight_beat_ids": [], "title": "Synthetic qualified conclusion", "summary": "Unverified model prose."}


@pytest.mark.parametrize("language", ["he", "en"])
def test_precision_retrieves_exact_first_and_tail_canon_without_global_text_or_evidence_substitution(monkeypatch, language):
    fixture = source_fixture(language)
    chapters, summaries, segments, brief, outline, plan = fixture
    before = copy.deepcopy(fixture)
    expected_beats = [*chapters[0]["beats"], *chapters[-1]["beats"]]
    segment_ids = {identifier for beat in expected_beats for identifier in beat["segment_ids"]}
    expected_utterances = [{key: row[key] for key in ("id", "start", "end", "text")}
                           for row in segments if row["id"] in segment_ids]
    expected_catalog = build_story_evidence_catalog(expected_beats, segments)
    captured = capture_transport(monkeypatch, precision_answer)

    selection, candidates = intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                                             brief, "synthetic-local-model", segments=segments)

    assert fixture == before
    assert len(captured) == 1
    assert intelligence._story_prompt_fits(captured[0])
    content = user_content(captured[0])
    assert content["brief"] == brief and content["plan"] == plan
    assert content["source_utterances"] == expected_utterances
    assert content["source_evidence"] == expected_catalog
    assert candidates == expected_beats
    assert selection["keep_beat_ids"] == [beat["id"] for beat in expected_beats]
    assert selection["semantic_mapping_verified"] is False
    assert selection["semantic_review_status"] == "provisional_precision_selection"
    assert [row["purpose"] for row in selection["slot_map"]] == [row["purpose"] for row in plan["slots"]]


@pytest.mark.parametrize("language", ["he", "en"])
def test_atomic_oversize_selected_utterance_is_technical_error_without_source_truncation_or_transport(monkeypatch, language):
    chapters, summaries, segments, brief, outline, plan = source_fixture(language)
    selected = chapters[-1]["beats"][0]
    canonical = next(row for row in segments if row["id"] == selected["segment_ids"][0])
    canonical["text"] *= 80
    selected["text"] = canonical["text"]
    # One indivisible requested source unit can supply both roles if its actual
    # content does so; its size must be refused before any retrieval/model call.
    for slot in plan["slots"]:
        slot["chapter_ids"] = [chapters[-1]["id"]]
        slot["required_context_chapter_ids"] = []
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    captured = capture_transport(monkeypatch, lambda _payload: pytest.fail("An indivisible oversized source unit reached a model request"))

    with pytest.raises(intelligence.StoryPlanningError) as caught:
        intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                         brief, "synthetic-local-model", segments=segments)

    assert captured == []
    assert caught.value.diagnostic["outcome"] == "technical_error"
    assert caught.value.diagnostic["reason"] == "story_input_context_limit"
    assert caught.value.diagnostic["applied_to_timeline"] is False
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_bounded_retrieval_considers_every_candidate_and_keeps_the_tail_beyond_old_96_cap(monkeypatch, language):
    chapters, summaries, segments, brief, outline, plan = source_fixture(language)
    plan["slots"][0]["chapter_ids"] = [chapter["id"] for chapter in chapters]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    all_ids = {beat["id"] for chapter in chapters for beat in chapter["beats"]}
    endpoints = [chapters[0]["beats"][0]["id"], chapters[-1]["beats"][0]["id"]]
    visited, retrieval_requests, precision_requests = set(), [], []

    def answer(payload):
        assert intelligence._story_prompt_fits(payload)
        content = user_content(payload)
        if "source_utterances" in content:
            precision_requests.append(copy.deepcopy(content))
            return precision_answer(payload)
        retrieval_requests.append(copy.deepcopy(content))
        present = {row["id"] for row in content["candidate_page"]}
        assert present <= all_ids
        assert present, "A retrieval page must identify its actual source candidates"
        visited.update(present)
        return {"candidate_beat_ids": [identifier for identifier in endpoints if identifier in present]}

    captured = capture_transport(monkeypatch, answer)
    selection, candidates = intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                                             brief, "synthetic-local-model", segments=segments)

    assert retrieval_requests and len(precision_requests) == 1
    assert len(all_ids) > 96 and visited == all_ids
    assert all(request["options"]["num_ctx"] <= 32768 for request in captured)
    assert [row["id"] for row in candidates] == endpoints
    assert selection["keep_beat_ids"] == endpoints
    canonical = [row for row in segments if row["id"] in {identifier for beat in candidates for identifier in beat["segment_ids"]}]
    assert precision_requests[0]["source_utterances"] == [{key: row[key] for key in ("id", "start", "end", "text")} for row in canonical]
    assert precision_requests[0]["source_evidence"] == build_story_evidence_catalog(candidates, segments)
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("language", ["he", "en"])
def test_targeted_retrieval_rescues_a_model_nominated_required_tail_with_complete_canonical_validation(monkeypatch, language):
    chapters, summaries, segments, brief, outline, plan = source_fixture(language)
    plan["slots"][0]["chapter_ids"] = [chapter["id"] for chapter in chapters]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    first_id, tail_id = chapters[0]["beats"][0]["id"], chapters[-1]["beats"][0]["id"]
    all_ids = {beat["id"] for chapter in chapters for beat in chapter["beats"]}
    generic_pages, rescue_pages, precision = [], [], []

    def answer(payload):
        assert intelligence._story_prompt_fits(payload)
        content = user_content(payload)
        if "source_utterances" in content:
            precision.append(copy.deepcopy(content))
            return precision_answer(payload)
        page_ids = {row["id"] for row in content["candidate_page"]}
        assert page_ids <= all_ids
        domain = content.get("required_retrieval_domain")
        if domain is None:
            generic_pages.append(page_ids)
            return {"candidate_beat_ids": [first_id] if first_id in page_ids else []}
        rescue_pages.append(copy.deepcopy(content))
        assert domain == {"purpose": plan["slots"][-1]["purpose"], "kind": "primary", "chapter_ids": [chapters[-1]["id"]]}
        assert page_ids == {tail_id}
        return {"candidate_beat_ids": [tail_id]}

    captured = capture_transport(monkeypatch, answer)
    selection, candidates = intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                                             brief, "synthetic-local-model", segments=segments)

    assert set().union(*generic_pages) == all_ids
    assert rescue_pages and len(precision) == 1
    assert [row["id"] for row in candidates] == [first_id, tail_id]
    assert selection["keep_beat_ids"] == [first_id, tail_id]
    assert selection["semantic_mapping_verified"] is False
    assert selection["semantic_review_status"] == "provisional_precision_selection"
    selected_segments = {identifier for beat in candidates for identifier in beat["segment_ids"]}
    assert precision[0]["source_utterances"] == [{key: row[key] for key in ("id", "start", "end", "text")}
                                                 for row in segments if row["id"] in selected_segments]
    assert precision[0]["source_evidence"] == build_story_evidence_catalog(candidates, segments)
    recorded = [page for round_ in selection["source_retrieval"]["rounds"] for page in round_["required_domain_pages"]]
    assert recorded and all(page["candidate_ids"] == [tail_id] and page["nominated_ids"] == [tail_id] for page in recorded)
    assert all(request["options"]["num_ctx"] <= 32768 for request in captured)
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("missing_kind", ["primary", "required_context"])
def test_empty_targeted_domain_does_not_force_source_or_claim_source_wide_no_fit(monkeypatch, missing_kind):
    chapters, summaries, segments, brief, outline, plan = source_fixture()
    plan["slots"][0]["chapter_ids"] = [chapter["id"] for chapter in chapters]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    first_id, tail_id = chapters[0]["beats"][0]["id"], chapters[-1]["beats"][0]["id"]
    initial_id = first_id if missing_kind == "primary" else tail_id
    target_chapter = chapters[-1]["id"] if missing_kind == "primary" else chapters[0]["id"]
    domains = []

    def answer(payload):
        assert intelligence._story_prompt_fits(payload)
        content = user_content(payload)
        assert "source_utterances" not in content, "An unresolved mandatory domain reached precision"
        page_ids = {row["id"] for row in content["candidate_page"]}
        domain = content.get("required_retrieval_domain")
        if domain is None:
            return {"candidate_beat_ids": [initial_id] if initial_id in page_ids else []}
        domains.append(copy.deepcopy(domain))
        assert domain["kind"] == missing_kind and domain["chapter_ids"] == [target_chapter]
        assert {row["chapter_id"] for row in content["candidate_page"]} == {target_chapter}
        return {"candidate_beat_ids": []}

    capture_transport(monkeypatch, answer)
    with pytest.raises(intelligence.StoryPlanningError) as caught:
        intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                         brief, "synthetic-local-model", segments=segments)

    assert domains
    assert {key: caught.value.diagnostic[key] for key in ("outcome", "reason", "applied_to_timeline")} == {
        "outcome": "technical_error", "reason": "story_retrieval_incomplete", "applied_to_timeline": False}
    rounds = caught.value.diagnostic["source_retrieval"]["rounds"]
    assert rounds and rounds[-1]["chosen_ids"] == [initial_id]
    assert all(page["nominated_ids"] == [] for round_ in rounds for page in round_["required_domain_pages"])
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("cancel_phase", ["generic", "required_domain"])
def test_cancellation_between_retrieval_pages_stops_before_next_request_or_precision(monkeypatch, cancel_phase):
    from cutroom import story_context
    from cutroom.jobs import JobCancelled

    chapters, summaries, segments, brief, outline, plan = source_fixture()
    tail_chapter = chapters[-1]
    extra_segment = copy.deepcopy(segments[-1])
    extra_segment.update(id="segment-tail-extra", start=segments[-1]["end"] + 5,
                         end=segments[-1]["end"] + 25)
    extra_beat = copy.deepcopy(tail_chapter["beats"][0])
    extra_beat.update(id="beat-tail-extra", start=extra_segment["start"], end=extra_segment["end"],
                      segment_ids=[extra_segment["id"]])
    tail_chapter["beats"].append(extra_beat)
    tail_chapter["end"] = extra_beat["end"]
    tail_chapter["duration"] = tail_chapter["end"] - tail_chapter["start"]
    segments.append(extra_segment)
    candidates = [*chapters[0]["beats"], *tail_chapter["beats"]]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    original_pages = story_context.bounded_source_pages

    def one_unit_pages(units, make_payload, fits_payload):
        # Force real page boundaries while retaining the production budget check.
        return original_pages(units, make_payload, lambda payload: len(user_content(payload)["candidate_page"]) <= 1 and fits_payload(payload))

    monkeypatch.setattr(story_context, "bounded_source_pages", one_unit_pages)
    calls, cancelled = [], [False]
    first_id = candidates[0]["id"]

    def answer(_settings, payload, *_args, **_kwargs):
        content = user_content(payload)
        calls.append(copy.deepcopy(content))
        page_ids = [row["id"] for row in content["candidate_page"]]
        domain = content.get("required_retrieval_domain")
        if domain is not None:
            assert domain["kind"] == "primary" and domain["chapter_ids"] == [tail_chapter["id"]]
            cancelled[0] = cancel_phase == "required_domain"
            return {"candidate_beat_ids": [page_ids[0]]}
        cancelled[0] = cancel_phase == "generic"
        return {"candidate_beat_ids": [first_id] if first_id in page_ids else []}

    def cancel_check():
        if cancelled[0]:
            raise JobCancelled("owned retrieval cancelled between pages")

    monkeypatch.setattr(intelligence, "_call_ollama_story_pass", answer)
    with pytest.raises(JobCancelled):
        intelligence._retrieve_story_candidates(Settings(), candidates, chapters, summaries, outline, plan,
                                                brief, "fixture", "balanced",
                                                lambda _rows: pytest.fail("Cancelled pages reached precision"), cancel_check)

    generic = [row for row in calls if row.get("required_retrieval_domain") is None]
    rescue = [row for row in calls if row.get("required_retrieval_domain") is not None]
    assert len(generic) == (1 if cancel_phase == "generic" else len(candidates))
    assert len(rescue) == (0 if cancel_phase == "generic" else 1)
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("fault", ["foreign_id", "duplicate_id"])
def test_retrieval_cannot_add_foreign_source_or_repeat_a_candidate(monkeypatch, fault):
    chapters, summaries, segments, brief, outline, plan = source_fixture()
    plan["slots"][0]["chapter_ids"] = [chapter["id"] for chapter in chapters]
    before = copy.deepcopy((chapters, summaries, segments, brief, outline, plan))
    first_id = chapters[0]["beats"][0]["id"]
    invalid = ["beat-from-another-recording"] if fault == "foreign_id" else [first_id, first_id]

    def answer(payload):
        assert "source_utterances" not in user_content(payload), "An invalid retrieval reply must never reach exact precision"
        return {"candidate_beat_ids": invalid}

    captured = capture_transport(monkeypatch, answer)
    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._select_story_beats(Settings(), chapters, summaries, outline, plan,
                                         brief, "synthetic-local-model", segments=segments)

    assert len(captured) == 1
    assert (chapters, summaries, segments, brief, outline, plan) == before


@pytest.mark.parametrize("fault", ["duplicate_chapter_id", "duplicate_beat_ownership", "foreign_summary_chapter", "foreign_summary_key_beat"])
def test_ambiguous_global_index_never_silently_drops_a_chapter_or_beat(monkeypatch, fault):
    chapters, summaries, segments, brief, outline, _plan = source_fixture()
    if fault == "duplicate_chapter_id":
        chapters[-1]["id"] = chapters[0]["id"]
    elif fault == "duplicate_beat_ownership":
        chapters[-1]["beats"].append(copy.deepcopy(chapters[0]["beats"][0]))
    elif fault == "foreign_summary_chapter":
        summaries[-1]["id"] = "chapter-from-another-recording"
    else:
        summaries[-1]["key_beat_ids"] = [chapters[0]["beats"][0]["id"]]
    before = copy.deepcopy((chapters, summaries, segments, brief))
    captured = capture_transport(monkeypatch, outline)

    with pytest.raises(intelligence.StoryPlanningError):
        intelligence._build_global_outline(Settings(), summaries, brief, "synthetic-local-model",
                                           chapters=chapters, segments=segments)

    assert captured == []
    assert (chapters, summaries, segments, brief) == before
