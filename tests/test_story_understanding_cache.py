from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence
from cutroom.jobs import JobCancelled
from test_long_source_story_context import source_fixture


def context(tmp_path):
    chapters, summaries, _segments, _brief, outline, plan = source_fixture()
    for row in summaries:
        row["summary_source"] = "model"
    return SimpleNamespace(cache_dir=tmp_path), "a" * 64, chapters, summaries, outline, plan


def test_understanding_survives_later_planning_failure_without_claiming_an_edit(tmp_path):
    settings, fingerprint, chapters, summaries, outline, plan = context(tmp_path)
    before = copy.deepcopy((chapters, summaries, outline, plan))
    intelligence._save_story_understanding(settings, fingerprint, "fixture-model", chapters, summaries, outline, None, plan)
    restored = intelligence._load_story_understanding(settings, fingerprint, "fixture-model", chapters)
    assert restored["chapter_summaries"] == summaries and restored["outline"] == outline
    assert restored["last_proposed_plan"] == plan
    assert restored["authority"] == "unverified_understanding_only_no_edit_or_semantic_approval"
    assert not any(key in restored for key in ("draft", "decision", "generative_approved", "semantic_mapping_verified"))
    assert (chapters, summaries, outline, plan) == before


def test_actual_story_fingerprint_saves_and_restores_the_runtime_checkpoint(tmp_path):
    settings, _synthetic, chapters, summaries, outline, _plan = context(tmp_path)
    _chapters, _summaries, segments, brief, _outline, _plan = source_fixture()
    actual = intelligence.story_cache_fingerprint(segments, brief, "fixture-model")
    assert len(actual) == 32
    intelligence._save_story_understanding(settings, actual, "fixture-model", chapters, summaries, outline, None)
    path = intelligence._story_understanding_path(settings, actual)
    assert path.is_file()
    restored = intelligence._load_story_understanding(settings, actual, "fixture-model", chapters)
    assert restored["cache_fingerprint"] == actual
    assert restored["chapter_summaries"] == summaries and restored["outline"] == outline


@pytest.mark.parametrize("fault", ["source_fingerprint", "model", "pipeline", "foreign_summary_reference", "missing_chapter", "corrupt_json"])
def test_stale_or_invalid_understanding_cannot_bypass_model_passes(tmp_path, fault):
    settings, fingerprint, chapters, summaries, outline, _plan = context(tmp_path)
    intelligence._save_story_understanding(settings, fingerprint, "fixture-model", chapters, summaries, outline, None)
    path = intelligence._story_understanding_path(settings, fingerprint)
    if fault == "source_fingerprint":
        assert intelligence._load_story_understanding(settings, "b" * 64, "fixture-model", chapters) is None
        return
    if fault == "model":
        assert intelligence._load_story_understanding(settings, fingerprint, "other-model", chapters) is None
        return
    data = json.loads(path.read_text())
    if fault == "pipeline":
        data["cache_pipeline"] = "older-story-pipeline"
    elif fault == "foreign_summary_reference":
        data["chapter_summaries"][0]["key_beat_ids"] = ["foreign-beat"]
    elif fault == "missing_chapter":
        data["chapter_summaries"].pop()
    else:
        path.write_text("{broken")
        assert intelligence._load_story_understanding(settings, fingerprint, "fixture-model", chapters) is None
        return
    path.write_text(json.dumps(data))
    assert intelligence._load_story_understanding(settings, fingerprint, "fixture-model", chapters) is None


def test_cancellation_does_not_publish_partial_understanding_or_overwrite_existing(tmp_path):
    settings, fingerprint, chapters, summaries, outline, _plan = context(tmp_path)
    intelligence._save_story_understanding(settings, fingerprint, "fixture-model", chapters, summaries, outline, None)
    path = intelligence._story_understanding_path(settings, fingerprint)
    previous = path.read_bytes()
    changed = copy.deepcopy(outline)
    changed["premise"] = "A cancelled replacement is never published."
    def cancel():
        raise JobCancelled("cancelled before checkpoint")
    with pytest.raises(JobCancelled):
        intelligence._save_story_understanding(settings, fingerprint, "fixture-model", chapters, summaries, changed, cancel)
    assert path.read_bytes() == previous
