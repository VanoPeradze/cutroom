"""Measured waveform preparation is local, source-specific, and survives reopening."""
from __future__ import annotations

import io
import math
import shutil
import subprocess
import threading
import wave
from pathlib import Path

import numpy as np
import pytest

import server
from cutroom.audio import analyze_audio
from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom.media_library import prepare_asset, probe_asset
from cutroom.projects import ProjectStore


@pytest.fixture
def waveform_app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings()
    settings.raw["ai"]["enabled"] = False
    if not shutil.which(settings.ffmpeg) or not shutil.which(settings.ffprobe):
        pytest.skip("FFmpeg and ffprobe are required for synthetic waveform coverage")
    # Keep the fixture focused on actual audio decoding, not camera detection or thumbnails.
    monkeypatch.setattr(server, "analyze_faces_and_embedded_camera", lambda *_args, **_kwargs: {"available": False})
    monkeypatch.setattr(server, "extract_thumbnails", lambda *_args, **_kwargs: [])
    app = server.create_app(settings)
    app.config["TESTING"] = True
    yield app
    app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def wav_bytes(level: float, seconds: float = 1.2) -> bytes:
    rate = 8000
    times = np.arange(round(rate * seconds), dtype=np.float32) / rate
    # A quiet opening and ending make the waveform shape observable, not just nonempty.
    samples = level * np.sin(2 * math.pi * 440 * times)
    samples[(times < .2) | (times >= .8)] = 0
    pcm = np.clip(samples * 32767, -32768, 32767).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    return output.getvalue()


def seed_source(app, project_id: str, slot: str, level: float | None, generation: str = "waveform-generation"):
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    directory = store.project_dir(project_id) / "media"
    source = directory / f"source-{slot}.mp4"
    command = [settings.ffmpeg, "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=10:d=1.2"]
    if level is not None:
        audio = directory / f"audio-{slot}.wav"
        audio.write_bytes(wav_bytes(level))
        command += ["-i", str(audio), "-c:a", "aac"]
    command += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    metadata = server.probe_media(source, settings)
    store.update(project_id, lambda value: value["sources"].update({slot: {
        **metadata, "name": source.name, "generation": generation,
        "relative_path": source.relative_to(store.project_dir(project_id)).as_posix(),
        "preparation": "queued",
    }}))
    return source


def prepare_source(app, project_id: str, slot: str, generation: str = "waveform-generation"):
    context = JobContext(Job(f"job_waveform_{slot}", "prepare_source", project_id), threading.Lock())
    return server._prepare_source(context, project_id, slot, generation,
                                  app.extensions["cutroom_store"], app.extensions["cutroom_settings"])


def test_source_a_b_waveforms_are_measured_on_native_clocks_and_survive_reopen(waveform_app):
    app = waveform_app
    store = app.extensions["cutroom_store"]
    project_id = store.create("Local A/B waveforms")["id"]
    seed_source(app, project_id, "A", .15)
    seed_source(app, project_id, "B", .6)
    store.update(project_id, lambda value: value["manual"]["source_mixer"].update(sync_offset=2))
    for slot in ("A", "B"):
        assert prepare_source(app, project_id, slot)["audio_profile_ready"]
    saved = store.load(project_id)
    profiles = saved["pre_analysis"]["audio"]
    for slot in ("A", "B"):
        profile = profiles[slot]
        assert profile["available"] and 1 <= len(profile["waveform"]) <= 900
        assert profile["waveform"][0]["start"] == 0  # B is not shifted by global sync.
        assert all(0 <= row["start"] < row["end"] <= saved["sources"][slot]["duration"] for row in profile["waveform"])
        assert max(row["peak_dbfs"] for row in profile["waveform"]) > -25
    assert profiles["B"]["summary"]["peak_dbfs"] > profiles["A"]["summary"]["peak_dbfs"] + 8
    public = app.test_client().get(f"/api/projects/{project_id}").get_json()["project"]
    assert public["pre_analysis"]["audio"] == profiles
    assert public["analysis"] is None  # Manual editing can use upload-time profiles without AI.
    reopened = ProjectStore(app.extensions["cutroom_settings"]).load(project_id)
    assert reopened["pre_analysis"]["audio"] == profiles


def test_audio_profile_excludes_decoder_samples_beyond_declared_duration(waveform_app, tmp_path):
    rate = 8000
    times = np.arange(round(rate * 1.4), dtype=np.float32) / rate
    samples = .8 * np.sin(2 * math.pi * 440 * times)
    samples[times < 1.1] = 0
    source = tmp_path / "padded-audio.wav"
    with wave.open(str(source), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes((samples * 32767).astype("<i2").tobytes())
    profile = analyze_audio(source, waveform_app.extensions["cutroom_settings"], 1.1)
    assert all(0 <= row["start"] < row["end"] <= 1.1 for row in profile["waveform"])
    assert profile["waveform"][-1]["end"] == 1.1
    assert profile["summary"]["peak_dbfs"] <= -100
    assert profile["summary"]["integrated_rms_dbfs"] <= -100


@pytest.mark.parametrize("level,has_audio", [(None, False), (0, True)])
def test_source_no_audio_and_silent_audio_have_distinct_measured_states(waveform_app, level, has_audio):
    app = waveform_app
    store = app.extensions["cutroom_store"]
    project_id = store.create("No audio or silence")["id"]
    seed_source(app, project_id, "B", level)
    prepare_source(app, project_id, "B")
    saved = store.load(project_id)
    profile = saved["pre_analysis"]["audio"]["B"]
    assert saved["sources"]["B"]["has_audio"] is has_audio
    assert saved["sources"]["B"]["audio_profile_ready"] is has_audio
    assert profile["available"] is has_audio
    if has_audio:
        assert profile["waveform"] and max(row["peak_dbfs"] for row in profile["waveform"]) <= -100
    else:
        assert profile["waveform"] == []
        assert profile["warning"] == "Source has no audio track"


def test_source_waveform_decode_failure_can_be_retried_without_stale_cache(waveform_app, monkeypatch):
    app = waveform_app
    store = app.extensions["cutroom_store"]
    project_id = store.create("Retry waveform")["id"]
    seed_source(app, project_id, "B", .3)

    def fail(*_args, **_kwargs):
        raise RuntimeError("Synthetic decoder failure")

    monkeypatch.setattr(server, "analyze_audio", fail)
    prepare_source(app, project_id, "B")
    failed = store.load(project_id)["pre_analysis"]["audio"]["B"]
    assert failed["available"] is False and failed["waveform"] == []
    assert "Synthetic decoder failure" in failed["warning"]
    monkeypatch.setattr(server, "analyze_audio", analyze_audio)
    response = app.test_client().post(f"/api/projects/{project_id}/sources/B/prepare")
    assert response.status_code == 202, response.get_json()
    app.extensions["cutroom_jobs"].shutdown(wait=True)
    public = app.test_client().get(f"/api/projects/{project_id}").get_json()["project"]
    recovered = public["pre_analysis"]["audio"]["B"]
    assert recovered["available"] and recovered["waveform"]
    assert "warning" not in recovered
    assert public["sources"]["B"]["audio_profile_ready"] is True


def test_replaced_source_cannot_publish_an_old_generation_waveform(waveform_app, monkeypatch):
    app = waveform_app
    store = app.extensions["cutroom_store"]
    project_id = store.create("Generation-safe waveform")["id"]
    seed_source(app, project_id, "B", .3)

    def replace_while_measuring(*_args, **_kwargs):
        store.update(project_id, lambda value: value["sources"]["B"].update(generation="replacement"))
        return {"available": True, "waveform": [{"start": 0, "end": 1, "peak_dbfs": -6}]}

    monkeypatch.setattr(server, "analyze_audio", replace_while_measuring)
    with pytest.raises(JobCancelled, match="replaced during preparation"):
        prepare_source(app, project_id, "B")
    assert "B" not in store.load(project_id)["pre_analysis"]["audio"]


@pytest.mark.parametrize("name,level", [("music", .2), ("voiceover", .6), ("silent", 0)])
def test_imported_audio_waveforms_have_real_peaks_and_survive_public_projection(waveform_app, name, level):
    app = waveform_app
    store = app.extensions["cutroom_store"]
    settings = app.extensions["cutroom_settings"]
    project_id = store.create("Imported audio waveform")["id"]
    asset_id = "asset_" + "b" * 32
    path = store.project_dir(project_id) / "media" / "assets" / asset_id / f"{name}.wav"
    path.parent.mkdir(parents=True)
    path.write_bytes(wav_bytes(level))
    metadata = probe_asset(path, "audio", settings)
    store.update(project_id, lambda value: value["assets"].update({asset_id: {
        "id": asset_id, "name": path.name, **metadata, "status": "preparing", "waveform": [],
        "path": path.relative_to(store.project_dir(project_id)).as_posix(),
    }}))
    context = JobContext(Job("job_waveform_import", "prepare_asset", project_id), threading.Lock())
    prepare_asset(context, project_id, asset_id, store, settings)
    asset = app.test_client().get(f"/api/projects/{project_id}").get_json()["project"]["assets"][asset_id]
    peaks = asset["waveform"]
    assert asset["status"] == "ready" and 1 <= len(peaks) <= 240
    assert all(0 <= peak <= 1 for peak in peaks)
    if level:
        assert max(peaks) == 1 and min(peaks) < .1
    else:
        assert max(peaks) == 0
    assert ProjectStore(settings).load(project_id)["assets"][asset_id]["waveform"] == peaks
