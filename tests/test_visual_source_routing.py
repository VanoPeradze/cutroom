import copy
import threading
from pathlib import Path

import pytest

from cutroom import director
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.visual_moments import VisualTimeline
from cutroom.transcription import _coverage_from_chunks


@pytest.mark.parametrize("mixer,has_b,expected", [
    ({}, True, "A"),
    ({"screen_slot": "B", "camera_slot": "A"}, True, "B"),
    ({"screen_slot": "B"}, True, "B"),
    ({"screen_slot": "B", "camera_slot": "B"}, True, "A"),
    ({"screen_slot": "B", "camera_slot": "A"}, False, "A"),
])
def test_visual_source_honors_valid_screen_roles(mixer, has_b, expected):
    project = {"sources": {"A": {"duration": 60}, "B": {"duration": 80} if has_b else None},
               "manual": {"source_mixer": mixer}}
    assert director._analysis_screen_slot(project) == expected


def test_visual_evidence_is_mapped_clipped_and_cached_for_its_role_and_sync(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    monkeypatch.setattr(director, "resolve_visual_pass", lambda *_a, **_kw: {
        "run": True, "model": "local-test-model", "budget": 8,
    })
    monkeypatch.setattr(director, "accelerated_inference_available", lambda *_: False)
    calls = []

    def observe(path, duration, _settings, model, **kwargs):
        calls.append((path, duration))
        return {"available": True, "windows": [
            {"start": a, "end": b, "screen": "gameplay", "score": .8, "event": "visible action"}
            for a, b in [(0, 8), (40, 56), (70, 80)]
        ]}

    monkeypatch.setattr(director, "analyze_visual_moments", observe)
    context = JobContext(Job("job_visual_routes", "director", "project_test"), threading.Lock())

    def resolve(cache=None, slot="B", offset=12):
        return director._resolve_visual_moments(
            context, settings, {}, cache, "same-source-fingerprint", Path(f"source-{slot}.mp4"), 80, {},
            source_slot=slot, timeline_offset=offset, timeline_duration=60,
        )

    visual, plan, computed, warning = resolve()
    assert computed and warning is None and plan["source_slot"] == "B"
    assert calls == [(Path("source-B.mp4"), 80)]
    assert [(x["start"], x["end"]) for x in visual["windows"]] == [(12, 20), (52, 60)]
    assert visual["windows"][0]["source_start"] == 0
    assert visual["timestamp_frame"] == "timeline"
    timeline = VisualTimeline(visual)
    assert timeline.evidence(0, 10) is None
    assert timeline.evidence(12, 20)["action"] == .8
    cache = {"visual_moments": copy.deepcopy(visual)}
    reused, _, computed, _ = resolve(cache)
    assert not computed and reused == visual and len(calls) == 1
    shifted, _, computed, _ = resolve(cache, offset=-5)
    assert computed and len(calls) == 2
    assert shifted["windows"][0]["start"] == 0 and shifted["windows"][0]["end"] == 3
    assert shifted["cache_key"] != visual["cache_key"]
    changed_role, _, computed, _ = resolve(cache, slot="A", offset=0)
    assert computed and calls[-1][0] == Path("source-A.mp4")
    assert changed_role["cache_key"] != visual["cache_key"]
    assert cache["visual_moments"] == visual


def test_director_syncs_screen_b_before_visual_analysis_even_when_audio_is_a(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("Visual routing regression")
    for slot, duration in [("A", 90), ("B", 80)]:
        media = store.project_dir(project["id"]) / "media" / f"source-{slot}.mp4"
        media.write_bytes(b"isolated mock media")
        project["sources"][slot] = {"relative_path": f"media/source-{slot}.mp4", "duration": duration,
                                    "audio_duration": duration, "has_audio": True, "width": 320, "height": 180}
    project["manual"]["source_mixer"].update(screen_slot="B", camera_slot="A", audio_slot="A")
    project["settings"].update(goal="short", spoken_language="en", performance_mode="quality", aspect="16:9", auto_reframe=False)
    store.save(project)
    events = []

    def sync(*_a, **_kw):
        events.append("sync")
        return {"offset": 10, "confidence": 1, "method": "cross_correlation"}

    monkeypatch.setattr(director, "synchronize_sources", sync)
    monkeypatch.setattr(director, "cuda_available", lambda *_: False)
    monkeypatch.setattr(director, "transcribe", lambda *_a, **_kw: {
        "duration": 90, "language": "en", "language_probability": 1,
        "text": "A complete spoken sentence with enough useful context for the edit.",
        "segments": [{"start": 5, "end": 12, "text": "A complete spoken sentence with enough useful context for the edit.", "avg_logprob": -.2}],
        "coverage": _coverage_from_chunks(90, [{"start": 0, "end": 90, "analyzed_end": 90,
                                              "status": "complete"}], 1, "decoder_exhaustion"),
    })
    monkeypatch.setattr(director, "analyze_audio", lambda *_a, **_kw: {
        "available": True, "duration": 90, "ranges": {}, "summary": {},
        "waveform": [{"start": 20, "end": 25, "rms_dbfs": -20, "peak_dbfs": -10}],
    })
    monkeypatch.setattr(director, "detect_scenes", lambda *_a, **_kw: [])

    class ReachedVisualAnalysis(Exception):
        pass

    def check_route(_context, _settings, _brief, _cache, _fingerprint, path, duration, sound, **kwargs):
        events.append("visual")
        assert path.name == "source-B.mp4" and duration == 80
        assert kwargs == {"source_slot": "B", "timeline_offset": 10, "timeline_duration": 90}
        assert sound["waveform"][0]["start"] == 10 and sound["waveform"][0]["end"] == 15
        raise ReachedVisualAnalysis

    monkeypatch.setattr(director, "_resolve_visual_moments", check_route)
    context = JobContext(Job("job_visual_order", "director", project["id"]), threading.Lock())
    with pytest.raises(ReachedVisualAnalysis):
        director.analyze_project(context, project["id"], store, settings)
    assert events == ["sync", "visual"]
