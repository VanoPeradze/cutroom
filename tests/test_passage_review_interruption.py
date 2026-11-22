"""Synthetic model failures exercise the actual Director, review and edit path."""
from array import array
import copy
from hashlib import sha256
import json
import shutil
import subprocess
import threading
import time

import pytest

from cutroom import director, intelligence as story, render, review_candidates
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom.projects import ProjectStore
from cutroom.story_budget import framed_story_duration
from tests.portable_support.source_fixture import source_fixture, understanding_reply
from test_reel_proposals import api


def source_and_brief(language):
    fixture = source_fixture(language)
    duration = fixture["segments"][-1]["end"] + .1
    brief = {**fixture["brief"], "spoken_language": language, "performance_mode": "balanced",
             "visual_ai": "off", "aspect": "source", "auto_reframe": False, "fps": 30,
             "captions": False, "burn_captions": False, "editorial_effects": False,
             "allow_extractive_rough_cut": False}
    transcript, _ = director._normalize_transcript({
        "language": language, "language_probability": .99, "duration": duration,
        "segments": fixture["segments"],
    }, language, duration)
    return transcript, brief, duration


def model_failure(monkeypatch, error, *, at_nomination=None):
    calls = []
    ready = {"selected_model": "fixture:4b", "ready": True}

    def respond(_settings, payload, *_args):
        data = json.loads(payload["messages"][-1]["content"])
        if "passage_candidates" not in data:
            calls.append("understanding")
            return understanding_reply(payload)
        calls.append("nomination")
        if at_nomination is not None:
            at_nomination()
        raise error

    def no_live_model(*_a, **_kw):
        pytest.fail("Unexpected live model access")

    monkeypatch.setattr(story, "open_ollama", no_live_model)
    monkeypatch.setattr("cutroom.story_search_identity.local_story_model_identity", lambda *_: None)
    monkeypatch.setattr(story, "_ready_story_model_status", lambda *_: dict(ready))
    monkeypatch.setattr("server.story_ai_status", lambda *_: dict(ready))
    monkeypatch.setattr(story, "_call_ollama_story_pass", respond)
    return calls


@pytest.fixture
def first_pass(api, monkeypatch):
    app, client, store, pid, media = api
    settings = app.extensions["cutroom_settings"]
    settings.ai["cloud_connection"] = {"mode": "local"}
    transcript, brief, duration = source_and_brief("en")

    def attach(p):
        p["draft"], p["analysis"] = None, None
        p["manual"]["cuts"] = []
        p["sources"]["A"].update(duration=duration, width=160, height=90, has_audio=True)
        p["settings"].update(brief)

    store.update(pid, attach)
    monkeypatch.setattr(director, "_transcribe_safely", lambda *_a, **_kw: (copy.deepcopy(transcript), None))
    monkeypatch.setattr(director, "analyze_audio", lambda *_a, **_kw: {"available": False, "ranges": {}, "summary": {}})
    monkeypatch.setattr(director, "_resolve_visual_moments", lambda *_a, **_kw: ({}, {}, False, None))
    return client, store, pid, media, settings


def failed_job(client, pid):
    response = client.post(f"/api/projects/{pid}/director", json={})
    assert response.status_code == 202, response.get_json()
    job_id = response.get_json()["job"]["id"]
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").get_json()["job"]
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(.03)
    pytest.fail("Synthetic Director job did not terminate")


def preview_and_apply(client, store, pid):
    before = store.load(pid)
    state = store.state_path(pid)
    snapshot = state.read_bytes()
    public = client.get(f"/api/projects/{pid}").get_json()
    public = public.get("project", public)
    shelf = public["analysis"]["review_candidates"]
    assert shelf["revision"] == before["revision"] and shelf["semantic_approval"] is False
    previews = []
    for row in shelf["items"]:
        response = client.post(f"/api/projects/{pid}/reel-proposal",
                               json={"candidate_id": row["id"], "expected_revision": before["revision"]})
        assert response.status_code == 200, response.get_json()
        proposal = response.get_json()["proposal"]
        assert proposal["ranges"] == row["ranges"]
        assert proposal["output_duration"] == row["output_duration"]
        assert proposal["kind"] == "unverified_source_candidate" and proposal["semantic_approval"] is False
        previews.append(proposal)
    assert previews and state.read_bytes() == snapshot
    preview = previews[0]
    assert 45 <= preview["output_duration"] <= 60
    response = client.post(f"/api/projects/{pid}/manual/edit", json={
        "action": "apply_review_candidate", "candidate_id": preview["candidate_id"],
        "proposal_id": preview["proposal_id"], "expected_revision": preview["revision"],
    })
    assert response.status_code == 200, response.get_json()
    return preview


@pytest.mark.parametrize("language", ["en", "he"])
@pytest.mark.parametrize("opt_in", [False, True])
def test_interrupted_nomination_keeps_canonical_receipt_but_never_auto_applies(first_pass, monkeypatch, language, opt_in):
    *_, settings = first_pass
    transcript, brief, _ = source_and_brief(language)
    brief["allow_extractive_rough_cut"] = opt_in
    calls = model_failure(monkeypatch, story.StoryAIUnavailableError("Synthetic local disconnect"))
    with pytest.raises(story.StoryAIUnavailableError) as caught:
        story.plan_edit(transcript["segments"], settings, brief)
    diagnostic = caught.value.diagnostic
    assert diagnostic["reason"] == "story_ai_unavailable"
    assert diagnostic["applied_to_timeline"] is False and diagnostic["semantic_result_verified"] is False
    assert diagnostic["source_wide_no_fit_proven"] is False and diagnostic["source_review_only"] is True
    assert diagnostic["passage_options"]["review_candidates"] and calls[-1] == "nomination"


@pytest.mark.parametrize("kind", ["transport", "response-limit", "parse"])
def test_job_offers_read_only_review_then_explicit_apply_history_and_reopen(first_pass, monkeypatch, kind):
    client, store, pid, media, settings = first_pass
    error = {
        "transport": story.StoryAIUnavailableError("Synthetic local disconnect"),
        "response-limit": story.StoryResponseLimitError("Synthetic output limit"),
        "parse": story.StoryPlanningError("Synthetic parse failure", {
            "reason": "passage_verification_unfinished", "outcome": "technical_error",
        }),
    }[kind]
    store.update(pid, lambda p: p["settings"].update(allow_extractive_rough_cut=True))
    before = store.load(pid)
    original = media.read_bytes()
    calls = model_failure(monkeypatch, error)
    job = failed_job(client, pid)
    assert job["status"] == "failed" and job["result"] is None, job
    assert job["failure"]["applied_to_timeline"] is False and calls[-1] == "nomination"
    current = store.load(pid)
    assert current["manual"] == before["manual"] and current["settings"] == before["settings"]
    assert current["draft"] is None
    preview = preview_and_apply(client, store, pid)
    applied = ProjectStore(settings).load(pid)
    assert applied["draft"]["keep_ranges"] == preview["ranges"]
    assert applied["draft"]["status"] == "requires_review"
    assert applied["draft"]["generative_approved"] is False and applied["draft"]["semantic_approval"] is False
    for action, expected in (("undo", None), ("redo", preview["ranges"])):
        current = store.load(pid)
        response = client.post(f"/api/projects/{pid}/manual/edit", json={
            "action": action, "expected_revision": current["revision"],
        })
        assert response.status_code == 200, response.get_json()
        reopened = ProjectStore(settings).load(pid)
        actual = reopened["draft"]["keep_ranges"] if reopened["draft"] else None
        assert actual == expected and media.read_bytes() == original


@pytest.mark.parametrize("mode", ["active-edit", "retained-cut", "new-revision", "same-generation-media"])
def test_interruption_cannot_rebase_onto_existing_or_changed_work(first_pass, monkeypatch, mode):
    _, store, pid, media, settings = first_pass
    if mode in {"active-edit", "retained-cut"}:
        def add_work(p):
            p["manual"]["cuts"] = [{"start": 0., "end": 2.}]
            if mode == "active-edit":
                p["draft"] = {"title": "My original edit", "keep_ranges": [{"start": 2., "end": 8.}]}
        store.update(pid, add_work)
    checkpoints = []
    state = store.state_path(pid)
    def at_nomination():
        if mode == "new-revision":
            store.update(pid, lambda p: p["settings"].update(instruction="A newer instruction."))
        if mode == "same-generation-media":
            media.write_bytes(media.read_bytes() + b"; original changed")
        checkpoints.append(state.read_bytes())
    model_failure(monkeypatch, story.StoryAIUnavailableError("Synthetic local disconnect"), at_nomination=at_nomination)
    ctx = JobContext(Job("changed-work", "director", pid), threading.Lock())
    with pytest.raises(story.StoryAIUnavailableError) as caught:
        director.analyze_project(ctx, pid, store, settings, preserve_current_edit=True)
    assert caught.value.diagnostic.get("review_available") is False
    assert state.read_bytes() == checkpoints[0]
    assert "review_candidates" not in (store.load(pid).get("analysis") or {})


def test_recovery_shelf_omits_unplaceable_geometry_without_hiding_valid_candidate(first_pass):
    from cutroom.story_candidates import source_identity_rows

    _, store, pid, _, _ = first_pass
    segments = [
        {"id": "tiny", "start": 0., "end": .04, "text": "Tiny.", "words": []},
        {"id": "main", "start": 10., "end": 59., "text": "Complete long explanation.", "words": []},
    ]
    current = store.update(pid, lambda p: p.update(analysis={"transcript": {"segments": segments}}))
    identity = review_candidates.media_identity(current, store.project_dir(pid))
    long = {"start": 10., "end": 59.}
    options = {"source_segments": source_identity_rows(segments), "review_candidates": [
        {"segment_ids": ["tiny", "main"], "playback_ranges": [{"start": 0., "end": .04}, long]},
        {"segment_ids": ["main"], "playback_ranges": [long]},
    ]}
    _, request, _ = source_and_brief("en")
    saved = review_candidates.publish_failed_review(
        store, pid, request, options, current["sources"]["A"]["generation"],
        first_pass=(current["revision"], identity),
    )
    rows = saved["analysis"]["review_candidates"]["items"]
    assert [(r["rank"], r["ranges"], r["segment_ids"]) for r in rows] == [(1, [long], ["main"])]
    assert saved["draft"] is None and saved["manual"] == current["manual"]


@pytest.mark.parametrize("during_shelf", [False, True])
def test_cancellation_never_saves_recovery_shelf(first_pass, monkeypatch, during_shelf):
    _, store, pid, _, settings = first_pass
    ctx = JobContext(Job("cancelled-review", "director", pid), threading.Lock())
    state = store.state_path(pid)
    checkpoints = []
    error = story.StoryAIUnavailableError("Synthetic local disconnect") if during_shelf else JobCancelled("Cancelled")
    model_failure(monkeypatch, error, at_nomination=lambda: checkpoints.append(state.read_bytes()))
    if during_shelf:
        build = review_candidates.build_review_shelf
        def build_then_cancel(*args, **kwargs):
            shelf = build(*args, **kwargs)
            ctx.job.cancel_event.set()
            return shelf
        monkeypatch.setattr(review_candidates, "build_review_shelf", build_then_cancel)
    with pytest.raises(JobCancelled):
        director.analyze_project(ctx, pid, store, settings)
    assert state.read_bytes() == checkpoints[0]
    assert "review_candidates" not in store.load(pid)["analysis"]


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is required for encode")
def test_recovered_selection_exports_exact_source_picture_and_tones(first_pass, monkeypatch):
    client, store, pid, media, settings = first_pass
    settings.render.update(prefer_hardware=False, min_free_mb=0)
    picture = ("color=blue:s=160x90:r=30:d=180.3,"
               "drawbox=c=red:t=fill:enable='lt(mod(t,18),6)',"
               "drawbox=c=lime:t=fill:enable='gte(mod(t,18),6)*lt(mod(t,18),12)'")
    sound = r"aevalsrc=0.12*sin(2*PI*(440+440*floor(mod(t\,18)/6))*t):s=48000:d=180.3"
    subprocess.run([
        settings.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", picture, "-f", "lavfi", "-i", sound,
        "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media),
    ], capture_output=True, check=True, timeout=40)
    store.update(pid, lambda p: p["sources"]["A"].update(size=media.stat().st_size))
    input_digest = sha256(media.read_bytes()).hexdigest()

    model_failure(monkeypatch, story.StoryAIUnavailableError("Synthetic local disconnect"))
    assert failed_job(client, pid)["status"] == "failed"
    assert store.load(pid)["draft"] is None
    preview = preview_and_apply(client, store, pid)

    ctx = JobContext(Job("interrupted-review-render", "render", pid), threading.Lock())
    record = render.render_project(ctx, pid, store, settings, {"quality": "fast"})["export"]
    output = settings.exports_dir / record["name"]
    streams = json.loads(subprocess.check_output([
        settings.ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output),
    ], timeout=10))["streams"]
    video = next(row for row in streams if row["codec_type"] == "video")
    expected = framed_story_duration(preview["ranges"], 30)
    assert (video["width"], video["height"], video["avg_frame_rate"]) == (160, 90, "30/1")
    assert float(video["duration"]) == pytest.approx(expected, abs=1/30)
    assert int(video["nb_frames"]) == pytest.approx(round(expected * 30), abs=1)

    tones, found, cursor = (440, 880, 1320), set(), 0.
    for take in preview["ranges"]:
        length = framed_story_duration([take], 30)
        for at in (.25, length - .25):
            source_time = take["start"] + at
            if not .05 < source_time % 6 < 5.85:
                continue
            color = int(source_time // 6) % 3
            command = [settings.ffmpeg, "-v", "error", "-ss", f"{cursor + at:.6f}", "-i", str(output), "-threads", "1"]
            pixels = subprocess.check_output(command + [
                "-frames:v", "1", "-vf", "crop=2:2", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
            ], timeout=10)
            assert pixels[color] > 150 and all(pixels[i] < 50 for i in range(3) if i != color)
            samples = array("f", subprocess.check_output(command + [
                "-vn", "-t", "0.10", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1",
            ], timeout=10))
            assert len(samples) == 4800
            hz = 10 * sum(a < 0 <= b for a, b in zip(samples, samples[1:]))
            assert hz == pytest.approx(tones[color], abs=20)
            found.add(color)
        cursor += length
    assert found == {0, 1, 2}
    assert sha256(media.read_bytes()).hexdigest() == input_digest
    print(f"Synthetic export: {len(preview['ranges'])} ranges, {video['duration']} s, "
          f"{video['nb_frames']} frames, exact sampled colors/tones.")
