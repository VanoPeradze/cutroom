from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from cutroom import cache_keys, director, intelligence
from cutroom.jobs import ACTIVE_STATUSES, JobAdmissionError, JobCancelled, JobManager


def wait_for(manager: JobManager, job_id: str, statuses: set[str], timeout: float = 2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job is None or job.status in statuses:
            return job
        time.sleep(0.005)
    return manager.get(job_id)


def test_submit_deduplicates_active_project_kind_and_exposes_recovery_snapshot():
    manager = JobManager(workers=1, background_workers=1)
    release = threading.Event()

    def blocked(context):
        context.update(0.2, "working")
        while not release.wait(0.01):
            context.checkpoint()
        return {"ok": True}

    try:
        first = manager.submit("director", "project-1", blocked)
        assert wait_for(manager, first.id, {"running"}).status == "running"
        duplicate = manager.submit("director", "project-1", blocked)
        assert duplicate.id == first.id
        assert manager.find_active("project-1", "director").id == first.id
        snapshot = manager.recovery_snapshot("project-1")
        assert snapshot[0]["id"] == first.id
        assert snapshot[0]["status"] in ACTIVE_STATUSES
    finally:
        release.set()
        manager.shutdown(wait=True, cancel_pending=True)


def test_admission_is_bounded_and_a_queued_future_cancels_before_user_code():
    manager = JobManager(workers=1, background_workers=1, max_pending=2)
    release = threading.Event()
    mutated = threading.Event()

    def blocked(context):
        while not release.wait(0.01):
            context.checkpoint()

    def must_not_run(_context):
        mutated.set()

    try:
        running = manager.submit("director", "project-1", blocked)
        assert wait_for(manager, running.id, {"running"}).status == "running"
        queued = manager.submit("render", "project-2", must_not_run)
        with pytest.raises(JobAdmissionError) as exc:
            manager.submit("refine", "project-3", must_not_run)
        assert exc.value.code == "job_queue_full"

        assert manager.cancel(queued.id)
        assert wait_for(manager, queued.id, {"cancelled"}).status == "cancelled"
        release.set()
        assert wait_for(manager, running.id, {"completed"}).status == "completed"
        assert not mutated.is_set()
    finally:
        release.set()
        manager.shutdown(wait=True, cancel_pending=True)


def test_successful_commit_wins_over_a_late_cancel_request():
    manager = JobManager(workers=1, background_workers=1)
    committed = threading.Event()
    release = threading.Event()

    def finalizing(context):
        context.commit()
        committed.set()
        release.wait(1.0)
        return {"draft": "saved"}

    try:
        job = manager.submit("director", "project-commit", finalizing)
        assert committed.wait(1.0)
        assert manager.cancel(job.id) is True
        release.set()
        finished = wait_for(manager, job.id, {"completed", "cancelled"})
        assert finished.status == "completed"
        assert finished.result == {"draft": "saved"}
        assert finished.public()["cancel_requested"] is False
    finally:
        release.set()
        manager.shutdown(wait=True, cancel_pending=True)


def test_persisted_running_job_is_minimal_and_becomes_interrupted_on_restart(tmp_path: Path):
    path = tmp_path / "jobs.json"
    release = threading.Event()
    manager = JobManager(
        workers=1,
        background_workers=1,
        persistence_path=path,
        persist_interval=0,
    )

    def blocked(context):
        context.update(0.4, "halfway")
        while not release.wait(0.01):
            context.checkpoint()
        return {"large_or_private": "not persisted"}

    restarted = None
    try:
        job = manager.submit("director", "project-1", blocked)
        assert wait_for(manager, job.id, {"running"}).status == "running"
        payload = json.loads(path.read_text(encoding="utf-8"))
        record = next(item for item in payload["jobs"] if item["id"] == job.id)
        assert record["status"] == "running"
        assert "result" not in record

        restarted = JobManager(
            workers=1,
            background_workers=1,
            persistence_path=path,
            persist_interval=0,
        )
        recovered = restarted.get(job.id)
        assert recovered is not None
        assert recovered.status == "interrupted"
        assert "restarted" in recovered.message.lower()
        assert restarted.recovery_snapshot("project-1")[0]["status"] == "interrupted"
    finally:
        release.set()
        manager.shutdown(wait=True, cancel_pending=True)
        if restarted:
            restarted.shutdown(wait=True, cancel_pending=True)


def test_terminal_records_expire_and_prune():
    manager = JobManager(workers=1, background_workers=1, retention_seconds=60)
    try:
        job = manager.submit("director", "project-1", lambda _context: "done")
        assert wait_for(manager, job.id, {"completed"}).status == "completed"
        with manager.lock:
            manager.jobs[job.id].finished_at = "2000-01-01T00:00:00Z"
            manager.jobs[job.id].updated_at = "2000-01-01T00:00:00Z"
        assert manager.prune() == 1
        assert manager.get(job.id) is None
    finally:
        manager.shutdown(wait=True, cancel_pending=True)


class DummySettings:
    def __init__(self):
        self.raw = {
            "scene_analysis_fps": 1.5,
            "vision_samples": {"lite": 8, "balanced": 16, "quality": 24},
        }
        self.ai = {
            "performance_mode": "auto",
            "whisper_model": "base",
            "whisper_models": {"lite": "base", "balanced": "small", "quality": "turbo"},
            "hebrew_whisper_model": "he-model",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
            "editor_model": "qwen:4b",
            "editor_quality_model": "qwen:9b",
            "editor_lite_model": "qwen:2b",
            "editor_fallback_models": [],
            "max_story_beats": 72,
        }


def test_analysis_fingerprints_reuse_expensive_context_when_only_editorial_brief_changes(tmp_path: Path, monkeypatch):
    source = tmp_path / "source-A.mp4"
    source.write_bytes(b"A" * 2048)
    project = {
        "language": "auto",
        "sources": {
            "A": {"relative_path": "media/source-A.mp4", "size": 2048, "duration": 12.0},
            "B": None,
        },
    }
    settings = DummySettings()
    brief = {
        "goal": "short",
        "spoken_language": "auto",
        "performance_mode": "balanced",
        "instruction": "Keep the explanation",
        "target_duration": 60,
    }

    def fingerprints(current_brief):
        return cache_keys.build_analysis_cache_fingerprints(
            project,
            settings,
            current_brief,
            {"A": source, "B": None},
        )

    baseline = fingerprints(brief)
    changed_language = fingerprints({**brief, "spoken_language": "he"})
    assert changed_language["transcript"] != baseline["transcript"]
    assert changed_language["scenes"] == baseline["scenes"]
    assert changed_language["vision"] == baseline["vision"]
    assert changed_language["story"] != baseline["story"]

    changed_performance = fingerprints({**brief, "performance_mode": "quality"})
    assert changed_performance["transcript"] != baseline["transcript"]
    assert changed_performance["scenes"] == baseline["scenes"]
    assert changed_performance["vision"] != baseline["vision"]
    assert changed_performance["story"] != baseline["story"]

    changed_goal = fingerprints({**brief, "goal": "podcast"})
    assert changed_goal["transcript"] == baseline["transcript"]
    assert changed_goal["scenes"] == baseline["scenes"]
    assert changed_goal["vision"] != baseline["vision"]
    assert changed_goal["story"] != baseline["story"]

    changed_instruction = fingerprints({**brief, "instruction": "Focus only on the demo"})
    assert changed_instruction["transcript"] == baseline["transcript"]
    assert changed_instruction["scenes"] == baseline["scenes"]
    assert changed_instruction["vision"] == baseline["vision"]
    assert changed_instruction["story"] != baseline["story"]

    source.write_bytes(b"B" * 2048)
    changed_source = fingerprints(brief)
    assert changed_source["source"] != baseline["source"]
    assert changed_source["transcript"] != baseline["transcript"]

    monkeypatch.setattr(cache_keys, "ANALYSIS_CACHE_PIPELINE", "next-pipeline")
    changed_pipeline = fingerprints(brief)
    assert changed_pipeline["pipeline"] != baseline["pipeline"]
    assert changed_pipeline["story"] != baseline["story"]


def test_story_cache_fingerprint_covers_transcript_brief_and_model():
    segments = [{"id": "s1", "start": 0, "end": 2, "text": "Opening idea"}]
    brief = {"goal": "short", "language": "en", "performance_mode": "balanced", "instruction": "demo"}
    baseline = intelligence.story_cache_fingerprint(segments, brief, "qwen:4b")
    assert intelligence.story_cache_fingerprint(segments, {**brief, "instruction": "different"}, "qwen:4b") != baseline
    assert intelligence.story_cache_fingerprint([{**segments[0], "text": "Changed"}], brief, "qwen:4b") != baseline
    assert intelligence.story_cache_fingerprint(segments, brief, "qwen:9b") != baseline


def test_story_hierarchy_rejects_fingerprinted_cache_after_brief_change(monkeypatch):
    settings = DummySettings()
    settings.ai.update({"enabled": True, "ollama_url": "http://unused"})
    rows = [
        {"id": f"s{index}", "start": index * 3.0, "end": index * 3.0 + 2.5, "text": f"Idea {index}. Supporting detail."}
        for index in range(18)
    ]
    enriched = intelligence.enrich_segments(rows, "en")
    beats = intelligence.build_story_beats(enriched, "en")
    chapters = intelligence.build_story_chapters(beats, max_chapters=12)
    old_brief = {"goal": "short", "language": "en", "performance_mode": "balanced", "instruction": "old"}
    cache = {
        "cache_fingerprint": intelligence.story_cache_fingerprint(enriched, old_brief, "qwen:4b"),
        "cache_pipeline": intelligence.STORY_CACHE_PIPELINE,
        "model": "qwen:4b",
        "chapter_count": len(chapters),
        "chapters": [{"id": chapter["id"]} for chapter in chapters],
        "chapter_summaries": [
            {
                "id": chapter["id"], "title": chapter["id"], "summary": "cached",
                "role": "development", "key_points": [],
                "key_beat_ids": [chapter["beats"][0]["id"]], "depends_on": [],
                "unresolved_questions": [], "summary_source": "model",
            }
            for chapter in chapters
        ],
        "outline": {
            "premise": "cached", "audience_takeaway": "cached",
            "story_arc": [
                {"chapter_id": chapter["id"], "function": "development", "why_it_matters": "cached"}
                for chapter in chapters
            ],
            "must_keep_chapter_ids": [], "optional_chapter_ids": [], "dependency_pairs": [],
        },
    }
    monkeypatch.setattr(intelligence, "_ollama_inventory", lambda _settings: (True, {"qwen:4b"}))

    class CacheMissObserved(RuntimeError):
        pass

    monkeypatch.setattr(
        intelligence,
        "_summarize_story_chapters",
        lambda *args, **kwargs: (_ for _ in ()).throw(CacheMissObserved()),
    )
    with pytest.raises(CacheMissObserved):
        intelligence.hierarchical_story_edit(
            beats,
            enriched,
            settings,
            {**old_brief, "instruction": "new"},
            story_cache=cache,
        )


def test_transcription_cancellation_is_not_converted_to_a_warning(monkeypatch):
    monkeypatch.setattr(director, "transcribe", lambda *args, **kwargs: (_ for _ in ()).throw(JobCancelled("stop")))
    with pytest.raises(JobCancelled):
        director._transcribe_safely(Path("unused.mp4"), DummySettings(), "en")
