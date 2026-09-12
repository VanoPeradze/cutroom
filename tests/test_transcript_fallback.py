from __future__ import annotations

import copy
import threading
from pathlib import Path

import pytest


def _audio_profile(duration: float) -> dict:
    energetic_centers = {45.0, 155.0, 265.0, 375.0, 485.0, 575.0}
    waveform = []
    for second in range(0, int(duration), 5):
        center = second + 2.5
        energetic = any(abs(center - value) < 8.0 for value in energetic_centers)
        waveform.append({
            "start": float(second),
            "end": min(duration, float(second + 5)),
            "rms_dbfs": -8.0 if energetic else -48.0,
            "peak_dbfs": -2.0 if energetic else -35.0,
        })
    return {
        "available": True,
        "duration": duration,
        "summary": {
            "silence_threshold_dbfs": -42.0,
            "recommended_silence_threshold_dbfs": -42.0,
            "noise_floor_dbfs": -48.0,
            "speech_reference_dbfs": -18.0,
            "quiet_threshold_dbfs": -27.0,
            "loud_threshold_dbfs": -13.0,
            "integrated_rms_dbfs": -22.0,
            "peak_dbfs": -2.0,
        },
        "ranges": {
            "silence": [{"start": 80.0, "end": 90.0}],
            "quiet_speech": [],
            "loud_speech": [],
            "clipping": [],
        },
        "waveform": waveform,
    }


def _run_sparse_director(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    goal: str,
    edit_style: str,
    instruction: str = "",
) -> tuple[dict, dict, list, list]:
    from cutroom import director
    from cutroom.config import load_settings
    from cutroom.jobs import Job, JobContext
    from cutroom.projects import ProjectStore

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create("פרויקט בדיקה")
    source = store.project_dir(project["id"]) / "media" / "source-A.mp4"
    source.write_bytes(b"test-source")
    duration = 600.0

    def attach_source(current: dict) -> None:
        current["sources"]["A"] = {
            "slot": "A",
            "name": "source.mp4",
            "relative_path": "media/source-A.mp4",
            "duration": duration,
            "width": 1920,
            "height": 1080,
            "has_audio": True,
            "size": source.stat().st_size,
        }
        current["settings"].update({
            "goal": goal,
            "edit_style": edit_style,
            "target_duration": 60,
            "instruction": instruction,
            "spoken_language": "auto",
            "performance_mode": "auto",
            "auto_reframe": False,
            "captions": True,
            "burn_captions": True,
        })

    store.update(project["id"], attach_source)
    weak_transcript = {
        "language": "fr",
        "language_probability": 0.6284,
        "duration": duration,
        "model": "small",
        "device": "cuda",
        "compute_type": "float16",
        "text": "Fais l 'auration de combat.",
        "segments": [
            {"id": "s1", "start": 472.07, "end": 472.63, "text": "Fais l", "words": [], "avg_logprob": -0.82},
            {"id": "s2", "start": 526.70, "end": 527.46, "text": "auration de combat", "words": [], "avg_logprob": -0.83},
        ],
        "words": [],
    }
    transcription_calls: list[dict] = []

    def weak_asr(*_args, **kwargs):
        transcription_calls.append(dict(kwargs))
        return copy.deepcopy(weak_transcript), None

    planner_calls: list[list] = []

    def forbidden_planner(_context, segments, *_args, **_kwargs):
        planner_calls.append(list(segments))
        raise AssertionError("Story planner must not receive an unusable transcript")

    monkeypatch.setattr(director, "_transcribe_safely", weak_asr)
    monkeypatch.setattr(director, "analyze_audio", lambda *_args, **_kwargs: copy.deepcopy(_audio_profile(duration)))
    monkeypatch.setattr(director, "detect_scenes", lambda *_args, **_kwargs: [45.0, 155.0, 265.0, 375.0, 485.0, 575.0])
    monkeypatch.setattr(director, "cuda_available", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(director, "_plan_edit_with_cancel", forbidden_planner)

    context = JobContext(Job("job_sparse", "director", project["id"]), threading.Lock())
    result = director.analyze_project(context, project["id"], store, settings)
    return result, store.load(project["id"]), transcription_calls, planner_calls


@pytest.mark.parametrize("edit_style", ["smart", "stream_story"])
def test_short_with_sparse_transcript_finishes_with_honest_audio_visual_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    edit_style: str,
):
    result, saved, transcription_calls, planner_calls = _run_sparse_director(
        tmp_path, monkeypatch, goal="short", edit_style=edit_style,
    )

    assert result["engine"] == "audio_visual_highlights"
    assert saved["draft"]["status"] == "ready"
    assert saved["draft"]["partial_ai"] is True
    assert saved["draft"]["edit_style"] == edit_style
    assert 54.0 <= saved["draft"]["output_duration"] <= 60.05
    assert any(float(row["start"]) > 400.0 for row in saved["draft"]["keep_ranges"])
    assert saved["analysis"]["segments"] == []
    assert saved["analysis"]["transcript"]["segments"] == []
    assert saved["analysis"]["transcript"]["words"] == []
    assert saved["analysis"]["transcript"]["text"] == ""
    assert saved["analysis"]["story_hierarchy"] is None
    fallback = next(row for row in saved["analysis"]["warnings"] if row["type"] == "transcript_fallback")
    assert fallback["reasons"] == ["too_little_speech"]
    assert fallback["detected_language"] == "fr"
    assert fallback["fallback"] == "audio_visual_highlights"
    assert len(transcription_calls) == 1
    assert planner_calls == []


def test_clean_with_sparse_transcript_uses_audio_cleanup_without_fake_language(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, saved, transcription_calls, planner_calls = _run_sparse_director(
        tmp_path, monkeypatch, goal="clean", edit_style="smart",
    )

    assert result["engine"] == "audio_cleanup"
    assert saved["draft"]["status"] == "ready"
    assert saved["draft"]["partial_ai"] is True
    assert saved["draft"]["language"] == "he"
    assert "צרפת" not in str(saved["draft"]["summary"])
    assert saved["analysis"]["segments"] == []
    assert saved["analysis"]["transcript"]["text"] == ""
    assert next(row for row in saved["analysis"]["warnings"] if row["type"] == "transcript_fallback")["fallback"] == "audio_cleanup"
    assert len(transcription_calls) == 1
    assert planner_calls == []


def test_youtube_instruction_with_sparse_transcript_preserves_structure_with_audio_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    result, saved, _, planner_calls = _run_sparse_director(
        tmp_path,
        monkeypatch,
        goal="youtube",
        edit_style="smart",
        instruction="פתח בתוצאה ושמור את ההסבר",
    )

    assert result["engine"] == "audio_cleanup"
    assert saved["draft"]["status"] == "ready"
    assert saved["draft"]["partial_ai"] is True
    assert all(row["camera"] == "A" for row in saved["draft"]["camera_plan"])
    assert saved["analysis"]["segments"] == []
    assert not {"retakes", "repetitions", "fillers", "low_value", "story_selection"} & {
        row["type"] for row in saved["draft"]["decisions"]
    }
    assert planner_calls == []


def test_transcript_upgrade_is_real_and_does_not_lock_a_weak_auto_language():
    from cutroom.director import _transcript_upgrade_request

    mode, language = _transcript_upgrade_request(
        "auto",
        "auto",
        {"language": "fr"},
        {"language_probability": 0.6284, "reasons": ["too_little_speech"]},
    )
    assert mode == "quality"
    assert language == "auto"
    assert _transcript_upgrade_request(
        "quality",
        "he",
        {"language": "fr"},
        {"language_probability": 0.99, "reasons": []},
    ) == (None, "he")
