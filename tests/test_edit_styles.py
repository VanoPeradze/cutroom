from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from cutroom.cache_keys import build_analysis_cache_fingerprints
from cutroom.edit_styles import enrich_brief_with_style, get_edit_style, public_edit_styles


def test_streamer_style_catalog_is_public_and_copy_safe():
    styles = public_edit_styles()
    identifiers = {style["id"] for style in styles}
    assert {
        "smart",
        "stream_highlights",
        "competitive_clutch",
        "reaction_burst",
        "funny_moments",
        "stream_commentary",
        "stream_story",
        "chill_story",
        "clean_vod",
    } <= identifiers
    assert all("guidance" not in style for style in styles)
    assert all("selection_policy" in style and "framing_policy" in style for style in styles)
    assert all(
        style["defaults"]["layout"] == "A"
        for style in styles
        if style["category"] == "streamer"
    )
    assert all(
        style["framing_policy"]["embedded_camera_requires_confirmation"] is True
        and style["framing_policy"]["camera_detection"] == "suggest_only"
        and style["framing_policy"]["allow_single_source_duplication"] is False
        for style in styles
    )
    styles[0]["defaults"]["pace"] = "changed"
    styles[0]["selection_policy"]["weights"]["continuity"] = -1
    assert get_edit_style("smart")["defaults"]["pace"] == "balanced"
    assert get_edit_style("smart")["selection_policy"]["weights"]["continuity"] == 0.35


def test_style_enriches_ai_brief_without_overwriting_user_controls():
    brief = {
        "edit_style": "stream_highlights",
        "goal": "short",
        "pace": "gentle",
        "target_duration": 75,
        "instruction": "Keep the final explanation.",
    }
    enriched = enrich_brief_with_style(brief)
    assert enriched["pace"] == "gentle"
    assert enriched["target_duration"] == 75
    assert enriched["instruction"] == "Keep the final explanation."
    assert enriched["style_profile"]["id"] == "stream_highlights"
    assert "reactions" in enriched["style_profile"]["features"]
    assert enriched["style_profile"]["selection_policy"]["moment_unit"] == "standout_moment"
    assert enriched["style_profile"]["framing_policy"]["embedded_camera_requires_confirmation"] is True
    assert "guidance" in enriched["style_profile"]


@pytest.mark.parametrize(
    ("style_id", "pace", "target", "moment_unit", "audio_preset"),
    [
        ("competitive_clutch", "dynamic", 60, "engagement", "tight"),
        ("reaction_burst", "dynamic", 45, "reveal_and_reaction", "tight"),
        ("chill_story", "gentle", 180, "complete_anecdote", "natural"),
    ],
)
def test_new_streamer_profiles_have_distinct_executable_policies(
    style_id: str,
    pace: str,
    target: int,
    moment_unit: str,
    audio_preset: str,
):
    style = get_edit_style(style_id, strict=True)
    assert style["category"] == "streamer"
    assert style["defaults"]["layout"] == "A"
    assert style["defaults"]["pace"] == pace
    assert style["defaults"]["target_duration"] == target
    assert style["defaults"]["audio_cleanup"]["preset"] == audio_preset
    assert style["selection_policy"]["moment_unit"] == moment_unit
    assert sum(style["selection_policy"]["weights"].values()) == pytest.approx(1.0)
    assert style["framing_policy"]["embedded_camera_requires_confirmation"] is True
    assert style["framing_policy"]["allow_single_source_duplication"] is False


def test_switching_streamer_style_reuses_transcription_but_replans_story(tmp_path: Path):
    class DummySettings:
        raw = {"scene_analysis_fps": 1.5, "vision_samples": {"lite": 12}}
        ai = {
            "whisper_models": {"lite": "base"},
            "whisper_model": "base",
            "hebrew_whisper_model": "hebrew",
            "whisper_device": "auto",
            "whisper_compute_type": "auto",
            "editor_model": "qwen3.5:4b",
            "editor_quality_model": "qwen3.5:9b",
            "editor_lite_model": "qwen3.5:2b",
            "editor_fallback_models": [],
            "max_story_beats": 72,
        }

    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-evidence")
    project = {
        "language": "auto",
        "sources": {"A": {"relative_path": "source.mp4", "size": source.stat().st_size}, "B": None},
    }
    base = {
        "goal": "short", "aspect": "9:16", "layout": "auto", "auto_reframe": True,
        "spoken_language": "auto", "performance_mode": "lite", "target_duration": 60,
    }
    highlight = enrich_brief_with_style({**base, "edit_style": "stream_highlights"})
    comedy = enrich_brief_with_style({**base, "edit_style": "funny_moments"})
    first = build_analysis_cache_fingerprints(project, DummySettings(), highlight, {"A": source, "B": None})
    second = build_analysis_cache_fingerprints(project, DummySettings(), comedy, {"A": source, "B": None})
    assert first["transcript"] == second["transcript"]
    assert first["scenes"] == second["scenes"]
    assert first["vision"] == second["vision"]
    assert first["story"] != second["story"]


def test_story_requests_disable_thinking_to_preserve_json_budget(monkeypatch):
    from cutroom import intelligence

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            return json.dumps({"message": {"content": '{"ok": true}'}, "done_reason": "stop"}).encode()

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    result = intelligence._call_ollama_strict(
        DummySettings(),
        {"model": "qwen3.5:4b", "stream": False, "format": "json", "messages": []},
    )
    assert result == {"ok": True}
    assert captured["body"]["think"] is False


def test_cancellable_story_request_streams_and_reassembles_structured_json(monkeypatch):
    from cutroom import intelligence

    captured = {}
    checks = []
    chunks = [
        {"message": {"role": "assistant", "content": "{\"ok\":"}, "done": False},
        {"message": {"role": "assistant", "content": "true}"}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"},
    ]

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __init__(self):
            self.lines = iter([json.dumps(chunk).encode("utf-8") + b"\n" for chunk in chunks])

        def readline(self, limit):
            return next(self.lines, b"")

    def fake_urlopen(request, timeout=0):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    result = intelligence._call_ollama_strict(
        DummySettings(),
        {"model": "qwen3.5:4b", "stream": False, "format": "json", "messages": []},
        cancel_check=lambda: checks.append(True),
    )

    assert result == {"ok": True}
    assert captured["body"]["stream"] is True
    assert len(checks) >= len(chunks) * 2


def test_cancellable_story_request_closes_stream_when_cancelled(monkeypatch):
    from cutroom import intelligence

    class Cancelled(RuntimeError):
        pass

    state = {"chunks": 0, "closed": False}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            state["closed"] = True
            return False

        def __init__(self):
            self.contents = iter(("{", "\"ok\":true}"))

        def readline(self, limit):
            content = next(self.contents, None)
            if content is None:
                return b""
            state["chunks"] += 1
            return json.dumps({"message": {"content": content}, "done": False}).encode("utf-8") + b"\n"

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    def cancel_check():
        if state["chunks"]:
            raise Cancelled("stop now")

    monkeypatch.setattr(intelligence, "open_ollama", lambda *_args, **_kwargs: Response())
    with pytest.raises(Cancelled, match="stop now"):
        intelligence._call_ollama_strict(
            DummySettings(),
            {"model": "qwen3.5:4b", "stream": False, "format": "json", "messages": []},
            cancel_check=cancel_check,
        )

    assert state["chunks"] >= 1
    assert state["closed"] is True


def test_cancellable_story_request_does_not_wait_for_next_stream_chunk(monkeypatch):
    from cutroom import intelligence

    class Cancelled(RuntimeError):
        pass

    state = {"checks": 0, "closed": False}
    released = threading.Event()

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()
            return False

        def readline(self, limit):
            while not state["closed"]:
                released.wait(0.05)
            return b""

        def close(self):
            state["closed"] = True
            released.set()

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    def cancel_check():
        state["checks"] += 1
        if state["checks"] >= 4:
            raise Cancelled("cancel between chunks")

    monkeypatch.setattr(intelligence, "open_ollama", lambda *_args, **_kwargs: Response())
    with pytest.raises(Cancelled, match="between chunks"):
        intelligence._call_ollama_strict(
            DummySettings(),
            {"model": "qwen3.5:4b", "stream": False, "format": "json", "messages": []},
            cancel_check=cancel_check,
        )

    assert state["closed"] is True


def test_empty_thinking_only_response_has_actionable_error(monkeypatch):
    from cutroom import intelligence

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            return json.dumps({
                "message": {"content": "", "thinking": "reasoning consumed the budget"},
                "done_reason": "length",
            }).encode()

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    monkeypatch.setattr(intelligence, "open_ollama", lambda *_args, **_kwargs: Response())
    with pytest.raises(intelligence.StoryPlanningError, match="output budget"):
        intelligence._call_ollama_strict(
            DummySettings(),
            {"model": "qwen3.5:4b", "stream": False, "format": "json", "messages": []},
        )


def test_truncated_story_json_retries_once_with_a_larger_budget(monkeypatch):
    from cutroom import intelligence

    bodies = []
    payloads = [
        {"message": {"content": '{"premise":"cut off'}, "done_reason": "length"},
        {"message": {"content": '{"premise":"complete"}'}, "done_reason": "stop"},
    ]

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, limit):
            return json.dumps(self.payload).encode()

    def fake_urlopen(request, timeout=0):
        bodies.append(json.loads(request.data.decode("utf-8")))
        return Response(payloads[len(bodies) - 1])

    class DummySettings:
        ai = {"ollama_url": "http://127.0.0.1:11434"}

    monkeypatch.setattr(intelligence, "open_ollama", fake_urlopen)
    result = intelligence._call_ollama_strict(
        DummySettings(),
        {
            "model": "qwen3.5:4b", "stream": False, "format": "json",
            "options": {"num_predict": 1200},
            "messages": [{"role": "system", "content": "Return JSON."}],
        },
    )
    assert result == {"premise": "complete"}
    assert len(bodies) == 2
    assert bodies[1]["options"]["num_predict"] == 2400
    assert "Keep the retry concise" in bodies[1]["messages"][0]["content"]


def test_system_exposes_styles_and_project_patch_validates_them(tmp_path: Path, monkeypatch):
    from cutroom.config import load_settings
    from server import create_app

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    app = create_app(settings)
    client = app.test_client()
    system = client.get("/api/system").get_json()
    assert any(style["id"] == "stream_story" for style in system["edit_styles"])

    project = client.post("/api/projects", json={"name": "styles"}).get_json()["project"]
    accepted = client.patch(
        f"/api/projects/{project['id']}",
        json={"settings": {"edit_style": "stream_highlights"}, "expected_revision": project["revision"]},
    )
    assert accepted.status_code == 200
    assert accepted.get_json()["project"]["settings"]["edit_style"] == "stream_highlights"

    rejected = client.patch(
        f"/api/projects/{project['id']}",
        json={"settings": {"edit_style": "not-a-style"}},
    )
    assert rejected.status_code == 400
    assert rejected.get_json()["error"] == "invalid_edit_style"


def test_story_failure_keeps_expensive_context_for_retry(tmp_path: Path, monkeypatch):
    from cutroom import director
    from cutroom.config import load_settings
    from cutroom.intelligence import StoryPlanningError
    from cutroom.jobs import Job, JobContext
    from cutroom.projects import ProjectStore

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("context cache")
    source = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source.write_bytes(b"small-source")

    def attach_source(current):
        current["sources"]["A"] = {
            "slot": "A", "name": "source.mp4", "relative_path": "media/source-A.mp4",
            "duration": 12.0, "width": 640, "height": 360, "has_audio": False,
            "size": source.stat().st_size,
        }
        current["settings"].update({"goal": "short", "auto_reframe": False, "edit_style": "stream_story"})

    store.update(project["id"], attach_source)
    transcript = {
        "language": "en",
        "text": "A clear setup. The useful result. Finally the payoff.",
        "segments": [
            {"id": "s1", "start": 0.0, "end": 4.0, "text": "A clear setup.", "words": [], "avg_logprob": -0.1},
            {"id": "s2", "start": 4.0, "end": 8.0, "text": "The useful result.", "words": [], "avg_logprob": -0.1},
            {"id": "s3", "start": 8.0, "end": 12.0, "text": "Finally the payoff.", "words": [], "avg_logprob": -0.1},
        ],
        "words": [],
    }
    monkeypatch.setattr(director, "_transcribe_safely", lambda *_args, **_kwargs: (transcript, None))
    monkeypatch.setattr(
        director,
        "_plan_edit_with_cancel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StoryPlanningError("model response failed")),
    )
    context = JobContext(Job("job_context", "director", project["id"]), threading.Lock())

    with pytest.raises(StoryPlanningError, match="model response failed"):
        director.analyze_project(context, project["id"], store, settings)

    saved = store.load(project["id"])
    assert saved["draft"] is None
    assert saved["analysis"]["status"] == "context_ready"
    assert saved["analysis"]["engine"] == "context_cache"
    assert saved["analysis"]["transcript"]["text"] == transcript["text"]
    assert saved["analysis"]["cache_fingerprints"]["transcript"]


def test_quality_director_refreshes_lite_preanalysis_and_checkpoints_vision_before_story_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from cutroom import director
    from cutroom.config import load_settings
    from cutroom.intelligence import StoryPlanningError
    from cutroom.jobs import Job, JobContext
    from cutroom.projects import ProjectStore
    from cutroom.vision import VISION_ANALYSIS_VERSION

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("quality vision cache")
    source = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source.write_bytes(b"quality-vision-source")
    generation = "quality-source-generation"
    transcript = {
        "language": "en",
        "language_probability": 0.99,
        "duration": 12.0,
        "text": "A clear setup. The useful result. Finally the payoff.",
        "segments": [
            {"id": "s1", "start": 0.0, "end": 4.0, "text": "A clear setup.", "words": [], "avg_logprob": -0.1},
            {"id": "s2", "start": 4.0, "end": 8.0, "text": "The useful result.", "words": [], "avg_logprob": -0.1},
            {"id": "s3", "start": 8.0, "end": 12.0, "text": "Finally the payoff.", "words": [], "avg_logprob": -0.1},
        ],
        "words": [],
    }

    def attach_source(current):
        current["sources"]["A"] = {
            "slot": "A", "name": "source.mp4", "generation": generation,
            "relative_path": "media/source-A.mp4", "duration": 12.0,
            "width": 1920, "height": 1080, "has_audio": False,
            "size": source.stat().st_size,
        }
        current["settings"].update({
            "goal": "short", "target_duration": 12, "auto_reframe": False,
            "performance_mode": "quality", "spoken_language": "en",
        })
        current["pre_analysis"]["vision"]["A"] = {
            "version": VISION_ANALYSIS_VERSION,
            "available": True,
            "embedded_camera": None,
            "source_generation": generation,
            "sample_count": 12,
            "profile": "lite",
        }

    project = store.update(project["id"], attach_source)
    brief = director._effective_brief(project)
    fingerprints = build_analysis_cache_fingerprints(
        project,
        settings,
        brief,
        {"A": source, "B": None},
    )

    def attach_cached_context(current):
        current["analysis"] = {
            "cache_fingerprints": {**fingerprints, "vision": "stale-lite-vision"},
            "audio_source": "A",
            "audio_timeline_offset": 0.0,
            "transcript": transcript,
            "scenes": {"A": [], "B": []},
            "audio": {"available": False, "ranges": {}, "summary": {}},
            "vision": current["pre_analysis"]["vision"]["A"],
            "warnings": [],
        }

    store.update(project["id"], attach_cached_context)
    vision_calls: list[int] = []

    def quality_vision(_path, _duration, **kwargs):
        vision_calls.append(kwargs["samples"])
        return {
            "version": VISION_ANALYSIS_VERSION,
            "available": True,
            "faces": [],
            "focus": {"x": 0.5, "y": 0.5},
            "focus_safe": False,
            "embedded_camera": None,
        }

    monkeypatch.setattr(director, "analyze_faces_and_embedded_camera", quality_vision)
    monkeypatch.setattr(director, "cuda_available", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(
        director,
        "_plan_edit_with_cancel",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(StoryPlanningError("model response failed")),
    )
    context = JobContext(Job("job_quality_vision", "director", project["id"]), threading.Lock())

    with pytest.raises(StoryPlanningError, match="model response failed"):
        director.analyze_project(context, project["id"], store, settings)

    saved = store.load(project["id"])
    assert vision_calls == [32]
    assert saved["analysis"]["status"] == "context_ready"
    assert saved["analysis"]["vision"]["sample_count"] == 32
    assert saved["analysis"]["vision"]["profile"] == "quality"
    assert saved["analysis"]["cache_fingerprints"]["vision"] == fingerprints["vision"]
