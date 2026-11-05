"""Whole-source retrieval aids must never replace canonical selected speech."""
from __future__ import annotations

import copy
import json

import pytest

from cutroom.story_context import (
    StoryContextError, bounded_source_pages, build_whole_recording_index,
    retrieve_candidate_source,
)


def source(count=3, *, language="en"):
    chapters, summaries, segments = [], [], []
    wording = "This is qualified evidence, not an unconditional result. " if language == "en" else "זו עדות עם הסתייגות, ולא תוצאה בלתי מסויגת. "
    for index in range(count):
        start = index * 30.0
        segment_id, beat_id, chapter_id = f"s{index}", f"b{index}", f"c{index}"
        text = wording * 20 + f"FINAL-{index}."
        segment = {"id": segment_id, "start": start, "end": start + 24,
                   "text": text, "words": [{"start": start, "end": start + 1, "word": wording.split()[0]}]}
        segments.append(segment)
        beat = {"id": beat_id, "start": start, "end": start + 24,
                "segment_ids": [segment_id], "text": text, "position": index / max(count, 1)}
        chapters.append({"id": chapter_id, "start": start, "end": start + 24,
                         "duration": 24.0, "beat_ids": [beat_id], "beats": [beat]})
        summaries.append({"id": chapter_id, "title": "unverified title",
                          "summary": f"BEGIN-{index} " + wording * 30 + f" END-{index}",
                          "role": "development", "key_beat_ids": [beat_id], "depends_on": [],
                          "key_points": [f"point-{value} " + wording * 5 for value in range(7)],
                          "unresolved_questions": [], "summary_source": "model"})
    return chapters, summaries, segments


@pytest.mark.parametrize("language", ["en", "he"])
def test_long_index_retains_all_source_references_and_labels_prose_unverified(language):
    chapters, summaries, segments = source(120, language=language)
    before = copy.deepcopy((chapters, summaries, segments))
    index = build_whole_recording_index(chapters, summaries, summary_char_limit=80)
    assert [row["id"] for row in index["chapters"]] == [row["id"] for row in chapters]
    assert [row["id"] for row in index["source_beat_index"]] == [f"b{i}" for i in range(120)]
    assert [row["segment_ids"] for row in index["source_beat_index"]] == [[f"s{i}"] for i in range(120)]
    assert all(row["interpretation_status"] == "unverified_summary_index" for row in index["chapters"])
    assert index["source_evidence_status"] == "retrieve_complete_canonical_candidates_before_selection"
    assert index["coverage"] == {"chapter_count": 120, "beat_count": 120, "segment_count": 120}
    assert all(len(row["summary"]) <= 80 and f"END-{i}" in row["summary"] for i, row in enumerate(index["chapters"]))
    assert all(len(point) <= 80 for row in index["chapters"] for point in row["key_points"])
    assert (chapters, summaries, segments) == before


def test_shrinking_only_interpretation_prose_preserves_clock_and_all_ids():
    chapters, summaries, _ = source(5)
    indexes = [build_whole_recording_index(chapters, summaries, summary_char_limit=limit)
               for limit in (320, 160, 80, 48)]
    assert all(index["source_beat_index"] == indexes[0]["source_beat_index"] for index in indexes)
    assert all([{key: row[key] for key in ("id", "start", "end", "beat_ids", "key_beat_ids", "depends_on")}
                for row in index["chapters"]] ==
               [{key: row[key] for key in ("id", "start", "end", "beat_ids", "key_beat_ids", "depends_on")}
                for row in indexes[0]["chapters"]] for index in indexes)
    assert [len(json.dumps(index, ensure_ascii=False)) for index in indexes] == sorted(
        [len(json.dumps(index, ensure_ascii=False)) for index in indexes], reverse=True)


def test_key_points_span_the_index_instead_of_dropping_the_tail():
    chapters, summaries, _ = source(1)
    index = build_whole_recording_index(chapters, summaries)
    assert [point.split()[0] for point in index["chapters"][0]["key_points"]] == ["point-0", "point-3", "point-6"]


@pytest.mark.parametrize("mutation", ["duplicate_chapter", "duplicate_beat", "duplicate_segment_owner", "foreign_summary",
                                     "missing_summary", "foreign_key_beat", "foreign_dependency", "wrong_beat_list",
                                     "invalid_clock", "out_of_chapter", "invalid_duration"])
def test_index_rejects_ambiguous_or_foreign_source_identity(mutation):
    chapters, summaries, _ = source()
    if mutation == "duplicate_chapter":
        chapters[1]["id"] = chapters[0]["id"]
    elif mutation == "duplicate_beat":
        chapters[1]["beats"][0]["id"] = chapters[0]["beats"][0]["id"]
    elif mutation == "duplicate_segment_owner":
        chapters[1]["beats"][0]["segment_ids"] = ["s0"]
    elif mutation == "foreign_summary":
        summaries[0]["id"] = "foreign"
    elif mutation == "missing_summary":
        summaries.pop()
    elif mutation == "foreign_key_beat":
        summaries[0]["key_beat_ids"] = ["b1"]
    elif mutation == "foreign_dependency":
        summaries[0]["depends_on"] = ["foreign"]
    elif mutation == "wrong_beat_list":
        chapters[0]["beat_ids"] = ["b1"]
    elif mutation == "invalid_clock":
        chapters[0]["end"] = float("nan")
    elif mutation == "out_of_chapter":
        chapters[0]["beats"][0]["end"] = 25.0
    else:
        chapters[0]["duration"] = 100.0
    with pytest.raises(StoryContextError):
        build_whole_recording_index(chapters, summaries)


def test_selected_and_required_context_retrieval_preserves_complete_original_utterances():
    chapters, summaries, segments = source(4, language="he")
    # The caller supplies the primary/context union, including a later chapter.
    result = retrieve_candidate_source(chapters, segments, ["c3", "c0"])
    assert result["chapter_ids"] == ["c0", "c3"]
    assert result["beats"] == [chapters[0]["beats"][0], chapters[3]["beats"][0]]
    assert result["segments"] == [segments[0], segments[3]]
    assert all("FINAL-" in row["text"] and row["words"] for row in result["segments"])
    result["segments"][0]["words"][0]["word"] = "changed detached copy"
    result["beats"][0]["text"] = "changed detached copy"
    assert segments[0]["words"][0]["word"] != "changed detached copy"
    assert chapters[0]["beats"][0]["text"] != "changed detached copy"
    assert "summary" not in result["segments"][0]


@pytest.mark.parametrize("mutation", ["unknown_chapter", "duplicate_chapter", "duplicate_segment", "missing_segment",
                                     "out_of_beat", "blank_text"])
def test_candidate_retrieval_rejects_stale_or_ambiguous_canonical_source(mutation):
    chapters, _, segments = source(3)
    wanted = ["c1"]
    if mutation == "unknown_chapter":
        wanted = ["foreign"]
    elif mutation == "duplicate_chapter":
        wanted = ["c1", "c1"]
    elif mutation == "duplicate_segment":
        segments.append(copy.deepcopy(segments[0]))
    elif mutation == "missing_segment":
        segments.pop(0)  # Even an unselected stale source reference rejects.
    elif mutation == "out_of_beat":
        segments[0]["end"] = 25
    else:
        segments[0]["text"] = " "
    with pytest.raises(StoryContextError):
        retrieve_candidate_source(chapters, segments, wanted)


@pytest.mark.parametrize("instruction", ["Structure: setup -> result.", "מבנה: הקשר -> תוצאה."])
def test_pages_preserve_every_complete_unit_and_the_exact_instruction(instruction):
    chapters, _, segments = source(7, language="he")
    units = [{**chapter["beats"][0], "segments": [segments[index]]} for index, chapter in enumerate(chapters)]
    original = copy.deepcopy(units)
    controls = {"instruction": instruction, "ordered_role_groups": [["setup", "result"]]}
    captured = []

    def payload(rows):
        result = {"brief": copy.deepcopy(controls), "source_units": rows}
        captured.append(copy.deepcopy(result))
        return result

    pages = bounded_source_pages(units, payload, lambda value: len(value["source_units"]) <= 2)
    assert [row for page in pages for row in page] == original
    assert len(pages) == 4 and [len(page) for page in pages] == [2, 2, 2, 1]
    assert all(row["brief"] == controls for row in captured)
    assert units == original
    pages[0][0]["segments"][0]["text"] = "changed detached copy"
    assert units == original


def test_oversized_atomic_source_raises_typed_context_error_without_truncation():
    chapters, _, segments = source(1)
    units = [{**chapters[0]["beats"][0], "segments": segments}]
    original = copy.deepcopy(units)
    with pytest.raises(StoryContextError) as error:
        bounded_source_pages(units, lambda rows: {"source_units": rows}, lambda _payload: False)
    assert error.value.diagnostic == {"outcome": "technical_error", "reason": "story_input_context_limit",
                                      "applied_to_timeline": False}
    assert units == original


def test_duplicate_page_units_reject_before_building_requests():
    chapters, _, _ = source(1)
    unit = chapters[0]["beats"][0]
    with pytest.raises(StoryContextError):
        bounded_source_pages([unit, unit], lambda _rows: pytest.fail("must reject first"), lambda _payload: True)
