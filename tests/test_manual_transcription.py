"""Exercise the real local API, project store, and caption/render contracts."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest

from cutroom import cloud_ai, director, manual_transcription, media, render, transcription_adapter
from cutroom.config import load_settings
from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from server import create_app


def fixture_transcript(language, seconds=6.):
    rows = [
        {"id": "s1", "start": .4, "end": 1.4, "text": "Removed source line", "words": []},
        {"id": "s2", "start": 3., "end": 4.2, "text": "CUTROOM sounds clear", "words": []},
    ]
    return {
        "language": language, "model": "cached-test-speech", "device": "cpu",
        "duration": seconds, "segments": rows, "text": " ".join(row["text"] for row in rows),
        "coverage": {"version": 1, "complete": True, "source_duration": seconds,
                     "analyzed_ranges": [{"start": 0., "end": seconds}],
                     "expected_chunks": 1, "completed_chunks": 1},
        "execution": {"actual_transcription_engine": "local", "actual_model": "cached-test-speech"},
    }


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    settings = load_settings(tmp_path / "no-user-config.json")
    settings.ai.update(enabled=False, transcription_engine="auto",
                       cloud_connection={"mode": "own", "provider": "test"},
                       cloudflare_connection={"fixture": True})
    settings.render["prefer_hardware"] = False
    settings.raw["ffmpeg_threads"] = 1
    app = create_app(settings)
    app.config["TESTING"] = True
    store = app.extensions["cutroom_store"]
    project = store.create("Synthetic on-demand transcription")
    pid = project["id"]
    source = store.project_dir(pid) / "media" / "source-A.mp4"
    source.write_bytes(b"stubbed audio only; no user media")
    def attach(current):
        current["sources"]["A"] = {
            "slot": "A", "generation": "test-generation", "relative_path": "media/source-A.mp4",
            "duration": 6., "audio_duration": 6., "width": 160, "height": 90, "fps": 30,
            "has_audio": True, "browser_ready": True, "preparation": "ready",
        }
        current["settings"].update(aspect="source", resolution="720", editorial_effects=False,
                                   burn_captions=False, audio_cleanup={"normalize": False})
    store.update(pid, attach)
    calls = []

    def speech(path, local, **kw):
        assert path == source
        assert local.ai["transcription_engine"] == "local"
        assert local.ai["cloud_connection"] == {"mode": "local"}
        assert "cloudflare_connection" not in local.ai
        assert local.ai["whisper_local_files_only"] is True
        assert local.ai["whisper_isolate_process"] is True
        assert local.ai["download_models_on_setup"] is False
        assert local.ai["whisper_chunk_threshold_seconds"] == 0
        assert kw["performance_mode"] == "balanced"
        assert kw["duration"] == 6.
        kw["cancel_check"]()
        calls.append(kw["language"])
        return fixture_transcript(kw["language"])

    def forbidden(*args, **kwargs):
        raise AssertionError("Manual transcription must not run Director or cloud speech")

    monkeypatch.setattr(manual_transcription, "local_cached_fallback_settings", lambda local, *_: local)
    monkeypatch.setattr(manual_transcription, "transcribe", speech)
    monkeypatch.setattr(director, "analyze_project", forbidden)
    monkeypatch.setattr(director, "_plan_edit_with_cancel", forbidden)
    monkeypatch.setattr(cloud_ai, "transcribe_cloud", forbidden)
    monkeypatch.setattr(transcription_adapter, "transcribe_cloud_whisper", forbidden)
    client = app.test_client()
    try:
        yield client, store, pid, source, settings, calls
    finally:
        app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def open_manual(api):
    client, store, pid, *_ = api
    reply = client.post(f"/api/projects/{pid}/manual-draft", json={"expected_revision": store.load(pid)["revision"]})
    assert reply.status_code == 200, reply.get_json()
    return store.load(pid)


def start(api, language="he", revision=None):
    client, store, pid, *_ = api
    return client.post(f"/api/projects/{pid}/manual-transcript", json={
        "language": language, "expected_revision": store.load(pid)["revision"] if revision is None else revision,
    })


def finish(api, reply):
    assert reply.status_code == 202, reply.get_json()
    client, *_ = api
    job_id = reply.get_json()["job"]["id"]
    until = time.monotonic() + 10
    while time.monotonic() < until:
        job = client.get(f"/api/jobs/{job_id}").get_json()["job"]
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.01)
    raise AssertionError("Mocked manual transcript job did not complete")


def saved_edit_without_transcript(api):
    _, store, pid, *_ = api
    open_manual(api)
    return store.update(pid, lambda p: apply_manual_edit(p, {"action": "sequence_ripple_delete", "start": 0., "end": 2.}))


def test_fresh_manual_transcription_keeps_native_sequence_and_enables_caption_editing(api):
    client, store, pid, source, settings, calls = api
    assert start(api).status_code == 409
    before = saved_edit_without_transcript(api)
    assert calls == [] and before["analysis"]["transcript"]["segments"] == []
    assert before["manual"]["history"]["undo_count"] == 1
    original = sha256(source.read_bytes()).hexdigest()
    job = finish(api, start(api, "he"))
    assert job["status"] == "completed", job
    assert calls == ["he"]
    after = store.load(pid)
    assert job["result"] == {"saved": True, "segment_count": 2, "revision": after["revision"]}
    for key in ("draft", "manual", "settings", "sources", "exports", "pre_analysis"):
        assert after[key] == before[key]
    assert after["analysis"]["engine"] == "manual"
    assert after["analysis"]["segments"] == [] and "story_hierarchy" not in after["analysis"]
    assert [row["start"] for row in after["analysis"]["transcript"]["segments"]] == [.4, 3.]
    assert after["analysis"]["audio_source"] == "A" and after["analysis"]["audio_timeline_offset"] == 0.
    assert sha256(source.read_bytes()).hexdigest() == original
    assert settings.ai["transcription_engine"] == "auto" and settings.ai["cloudflare_connection"] == {"fixture": True}
    view = client.get(f"/api/projects/{pid}").get_json()["project"]
    assert len(view["editor_captions"]) == 1
    item = view["editor_captions"][0]
    assert item["start"] == 1. and item["text"] == "CUTROOM sounds clear"
    changed = store.update(pid, lambda p: apply_manual_edit(p, {
        "action": "caption_update", "caption_id": item["id"], "text": "Local caption change", "scope": "item",
    }))
    assert render.project_caption_items(changed, aligned=False)[0]["text"] == "Local caption change"
    undone = store.update(pid, lambda p: apply_manual_edit(p, {"action": "undo"}))
    assert render.project_caption_items(undone, aligned=False)[0]["text"] == item["text"]
    assert undone["manual"]["sequence"] == before["manual"]["sequence"]
    assert start(api).status_code == 409
    assert calls == ["he"]


@pytest.mark.parametrize("condition", ["silent-A", "B", "authored-caption", "saved-alternative", "invalid-language", "stale"])
def test_not_admitted_when_wrong_source_or_existing_caption_work(api, condition):
    _, store, pid, _, _, calls = api
    before = open_manual(api)
    if condition == "silent-A":
        store.update(pid, lambda p: p["sources"]["A"].update(has_audio=False))
    elif condition == "B":
        def choose_b(p):
            p["sources"]["B"] = {**p["sources"]["A"], "slot": "B"}
            p["manual"]["source_mixer"]["audio_slot"] = "B"
        store.update(pid, choose_b)
    elif condition == "authored-caption":
        store.update(pid, lambda p: p["manual"].update(caption_corrections={"s1": {"text": "User text"}}))
    elif condition == "saved-alternative":
        store.update(pid, lambda p: p.update(caption_alternatives={"some-version": {"label": "Fixture"}}))
    elif condition == "stale":
        store.update(pid, lambda p: p.update(name="Newer saved work"))
    unchanged = store.state_path(pid).read_bytes()
    response = start(api, language={"bad": True} if condition == "invalid-language" else "en",
                     revision=before["revision"] if condition == "stale" else None)
    assert response.status_code == (400 if condition == "invalid-language" else 409)
    assert calls == [] and store.state_path(pid).read_bytes() == unchanged


@pytest.mark.parametrize("condition", ["stale-revision", "changed-source-file", "cancelled", "partial", "no-speech", "missing-model"])
def test_worker_never_commits_unverified_or_changed_input(api, monkeypatch, condition):
    client, store, pid, source, _, calls = api
    open_manual(api)
    entered, release = threading.Event(), threading.Event()
    def speech(_path, _settings, **kw):
        entered.set()
        if condition in {"stale-revision", "changed-source-file", "cancelled"}:
            assert release.wait(5)
        kw["cancel_check"]()
        value = fixture_transcript("en")
        if condition == "partial":
            value["coverage"]["complete"] = False
        if condition == "no-speech":
            value.update(segments=[], text="")
        return value
    if condition == "missing-model":
        def no_model(*args):
            raise RuntimeError("missing synthetic fixture")
        monkeypatch.setattr(manual_transcription, "local_cached_fallback_settings", no_model)
    monkeypatch.setattr(manual_transcription, "transcribe", speech)
    response = start(api, "en")
    if condition in {"stale-revision", "changed-source-file", "cancelled"}:
        try:
            assert entered.wait(5)
            if condition == "stale-revision":
                store.update(pid, lambda p: p.update(name="Concurrent retained edit"))
            elif condition == "changed-source-file":
                source.write_bytes(b"changed synthetic original")
            else:
                job_id = response.get_json()["job"]["id"]
                assert client.post(f"/api/jobs/{job_id}/cancel", json={}).status_code in {200, 202}
        finally:
            release.set()
    before = store.state_path(pid).read_bytes()
    job = finish(api, response)
    assert job["status"] == {"cancelled": "cancelled", "no-speech": "completed"}.get(condition, "failed"), job
    if condition == "missing-model":
        assert "nothing was downloaded" in job["error"]
        assert not entered.is_set()
    if condition == "no-speech":
        assert job["result"] == {"saved": False, "reason": "no_speech", "segment_count": 0}
    assert store.state_path(pid).read_bytes() == before
    assert calls == []


def test_source_preparation_does_not_admit_a_transcript_that_cannot_commit(api):
    client, store, pid, _, _, calls = api
    open_manual(api)
    jobs = client.application.extensions["cutroom_jobs"]
    started, release = threading.Event(), threading.Event()

    def preparing(context):
        started.set()
        assert release.wait(5)
        context.checkpoint()

    jobs.submit("prepare_source", pid, preparing)
    try:
        assert started.wait(5)
        before = store.state_path(pid).read_bytes()
        response = start(api)
        assert response.status_code == 409 and response.get_json()["error"] == "project_busy"
        assert calls == [] and store.state_path(pid).read_bytes() == before
    finally:
        release.set()


def test_generated_transcript_exports_srt_and_keeps_prior_download(api):
    client, store, pid, source, settings, _ = api
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Existing FFmpeg and FFprobe required")
    cmd = [settings.ffmpeg, "-hide_banner", "-nostdin", "-v", "error", "-y",
           "-f", "lavfi", "-i", "color=c=blue:s=160x90:r=30:d=6",
           "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=6",
           "-c:v", "libx264", "-threads:v", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    info = media.probe_media(source, settings)
    assert info["duration"] == info["audio_duration"] == 6.
    store.update(pid, lambda p: p["sources"]["A"].update(info))
    saved_edit_without_transcript(api)
    prior = render.render_project(JobContext(Job("prior", "render", pid), threading.Lock()),
                                  pid, store, settings, {"quality": "fast", "_force_software": True})
    output_before = settings.exports_dir / prior["export"]["name"]
    before = sha256(output_before.read_bytes()).hexdigest()
    job = finish(api, start(api, "en"))
    assert job["status"] == "completed", job
    assert store.load(pid)["exports"][0] == prior["export"]
    prior_response = client.get(prior["url"])
    assert prior_response.status_code == 200 and sha256(prior_response.data).hexdigest() == before
    prior_response.close()
    store.update(pid, lambda p: p["settings"].update(captions=True, burn_captions=True))
    final = render.render_project(JobContext(Job("after", "render", pid), threading.Lock()),
                                  pid, store, settings, {"quality": "fast", "_force_software": True})
    result = final["export"]
    assert result["duration"] == 4.0 and result["captions_burned"] is True
    srt = (settings.exports_dir / Path(result["name"]).with_suffix(".srt")).read_text(encoding="utf-8-sig")
    assert "00:00:01,000 --> 00:00:02,200" in srt
    assert "CUTROOM sounds clear" in srt and "Removed source line" not in srt
    assert sha256(output_before.read_bytes()).hexdigest() == before
