"""Original B attachment does not spend an edit or replace a saved timeline."""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.manual_start import start_manual_draft
from cutroom.render import _effective_audio_slot, render_project
from cutroom.sequence import editor_sequence_snapshot
from cutroom.source_tracks import source_track_clips
from test_media_render import samples, tone_level


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["host"] = "127.0.0.1"
    settings.raw["ai"]["enabled"] = False
    settings.raw["render"].update(prefer_hardware=False, min_free_mb=0)
    application = server.create_app(settings)
    application.config["TESTING"] = True
    jobs = application.extensions["cutroom_jobs"]
    # Exercise real reservation/finalization/storage; defer unrelated review
    # metadata work so each tested attach has exactly one observable commit.
    submitted = []
    def submit(*args, **kwargs):
        submitted.append((args, kwargs))
        return SimpleNamespace(public=lambda: {"id": "synthetic-source-preparation"})
    monkeypatch.setattr(jobs, "submit", submit)
    yield application, settings, submitted
    application.extensions["cutroom_upload_storage"].close()
    jobs.shutdown(wait=True, cancel_pending=True)


def original(path: Path, slot, duration, data=None, *, has_audio=True):
    path.write_bytes(data or (b"local-test-source-" + slot.encode()))
    return {"slot": slot, "duration": duration, "video_duration": duration, "width": 160, "height": 96,
            "name": path.name, "generation": slot * 24, "has_audio": has_audio,
            "relative_path": "media/" + path.name, "video_codec": "h264", "browser_ready": True,
            "preparation": "ready", "fps": 30}


def initial(app, *, mode="16:9", a_bytes=None):
    application = app[0]
    store = application.extensions["cutroom_store"]
    project = store.create("Local A/B fixture", initial_settings={"workflow": "manual", "layout": "A", "aspect": mode})
    directory = store.project_dir(project["id"])
    project["sources"]["A"] = original(directory / "media/source-A.mp4", "A", 4.0, a_bytes)
    start_manual_draft(project)
    project["analysis"]["transcript"] = {"text": "Keep this transcript", "segments": [], "words": []}
    project["settings"].update(resolution="720", quality="fast", burn_captions=False,
                               editorial_effects=False)
    return application.test_client(), store, store.save(project)


def reserve(client, project, data, **extra):
    payload = {"purpose": "source", "slot": "B", "filename": "Camera.mp4",
               "size_bytes": len(data), "attach_b_revision": project["revision"], **extra}
    return client.post(f"/api/projects/{project['id']}/uploads/preflight", json=payload)


def transfer(client, receipt, data):
    response = client.put(receipt["upload_url"], data=data, content_type="application/octet-stream",
                          headers={"X-Cutroom-Upload-Offset": "0"})
    assert response.status_code == 200, response.get_json()


def commit(client, project, receipt, *, intent=True):
    headers = {"X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": receipt["upload_token"]}
    if intent:
        headers["X-Cutroom-Source-Intent"] = "attach-empty-b"
    return client.post(f"/api/projects/{project['id']}/sources/B", headers=headers)


def attach(client, project, data=b"exact B input", *, intent=True):
    pending = reserve(client, project, data)
    assert pending.status_code == 201, pending.get_json()
    receipt = pending.get_json()
    transfer(client, receipt, data)
    response = commit(client, project, receipt, intent=intent)
    assert response.status_code == 201, response.get_json()
    return receipt, response.get_json()


def edit(client, store, project, action, **fields):
    current = store.load(project["id"])
    response = client.post(f"/api/projects/{project['id']}/manual/edit",
                           json={"action": action, "expected_revision": current["revision"], **fields})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["project"]


def geometry(rows):
    return [(r["start"], r["end"], r["source_start"]) for r in rows]


def project_geometry(project, slot):
    return geometry(editor_sequence_snapshot(project)["source_tracks"][slot])


def stub_probe(monkeypatch, video_duration=2.25):
    def probe(path, _settings, *, original_filename=None):
        assert original_filename == "Camera.mp4"
        return {"duration": 3, "video_duration": video_duration, "width": 160, "height": 96,
                "has_audio": True, "fps": 30, "browser_ready": True, "size": path.stat().st_size}
    monkeypatch.setattr(server, "probe_media", probe)


def test_attaching_parallel_b_preserves_saved_metadata_and_prior_undo_redo(app, monkeypatch):
    stub_probe(monkeypatch)
    client, store, value = initial(app)
    value["manual"]["audio_mixer"] = {"source_db": -2}
    value["manual"]["track_locks"] = {"A": True}
    store.save(value)
    # Attach touches B only; A may stay locked. Before adding B, preserve
    # existing edit and layer as well as both non-empty history stacks.
    edit(client, store, value, "set_track_lock", slot="A", locked=False)
    edit(client, store, value, "sequence_split_all", time=2)
    edit(client, store, value, "sequence_move_range", start=2, end=4, to=0, mode="insert")
    edit(client, store, value, "text_add", kind="title", text="Still in this edit", start=.5, end=1.5)
    edit(client, store, value, "undo")
    edit(client, store, value, "set_track_lock", slot="A", locked=True)
    before = store.load(value["id"])
    assert before["manual"]["history"] == {"undo_count": 2, "redo_count": 1}
    assert project_geometry(before, "A") == [(0, 2, 2), (2, 4, 0)]
    # The reservation, not a potentially dropped request header, owns intent.
    receipt, response = attach(client, before, intent=False)
    after = store.load(value["id"])
    assert after["revision"] == before["revision"] + 1
    for name in ("draft", "analysis", "manual", "settings", "assets", "exports"):
        assert after[name] == before[name], name
    assert after["sources"]["A"] == before["sources"]["A"]
    assert after["sources"]["B"]["parallel_a_generation"] == before["sources"]["A"]["generation"]
    assert after["sources"]["B"]["generation"] == response["source"]["generation"]
    assert (store.project_dir(value["id"]) / after["sources"]["B"]["relative_path"]).read_bytes() == b"exact B input"
    assert project_geometry(after, "B") == [(0, .25, 2), (2, 4, 0)]
    assert geometry(response["project"]["editor_sequence"]["source_tracks"]["B"]) == project_geometry(after, "B")
    assert response["project"]["editor_sequence"]["source_tracks"]["A"] == editor_sequence_snapshot(before)["source_tracks"]["A"]
    args, options = app[2][0]
    assert args[0] == "prepare_source" and args[3:6] == (value["id"], "B", after["sources"]["B"]["generation"])
    assert options["dedupe_key"] == f'B:{after["sources"]["B"]["generation"]}'

    stopped = client.post(receipt["cancel_url"])
    assert stopped.status_code == 202 and stopped.get_json()["too_late"]
    assert stopped.get_json()["generation"] == after["sources"]["B"]["generation"]
    assert store.load(value["id"]) == after
    edit(client, store, value, "redo")
    assert store.load(value["id"])["manual"]["text_clips"][0]["text"] == "Still in this edit"
    edit(client, store, value, "undo")
    edit(client, store, value, "set_track_lock", slot="A", locked=False)
    edit(client, store, value, "undo")  # Undo A's reorder that predates adding B.
    edit(client, store, value, "undo")  # Undo to the pre-sequence edit clock.
    assert project_geometry(store.load(value["id"]), "B") == [(0, 2.25, 0)]
    edit(client, store, value, "redo")
    edit(client, store, value, "redo")
    assert project_geometry(store.load(value["id"]), "B") == [(0, .25, 2), (2, 4, 0)]
    assert store.load(value["id"])["sources"]["B"] == after["sources"]["B"]
    assert reserve(client, store.load(value["id"]), b"not a replacement").status_code == 409


@pytest.mark.parametrize("guard", ["locked", "stale", "embedded_history", "bad_slot", "bad_revision"])
def test_rejected_reservation_writes_no_source_or_history(app, guard):
    client, store, value = initial(app)
    args = {}
    if guard == "locked":
        value["manual"]["track_locks"] = {"B": True}
        value = store.save(value)
    elif guard == "stale":
        args["attach_b_revision"] = value["revision"] - 1
    elif guard == "embedded_history":
        edit(client, store, value, "set_embedded_camera", enabled=True, x=.7, y=.05, w=.25, h=.30)
        edit(client, store, value, "undo")
        value = store.load(value["id"])
    elif guard == "bad_slot":
        args["slot"] = "A"
    elif guard == "bad_revision":
        args["attach_b_revision"] = True
    before = store.load(value["id"])
    rejected = reserve(client, value, b"not persisted", **args)
    assert rejected.status_code == (400 if guard in {"bad_slot", "bad_revision"} else 409), rejected.get_json()
    assert store.load(value["id"]) == before
    assert list((store.project_dir(value["id"]) / "media").iterdir()) == [store.project_dir(value["id"]) / "media/source-A.mp4"]


@pytest.mark.parametrize("decision", ["stop", "stop_during_probe", "revision", "revision_during_probe", "wrong_intent"])
def test_cancel_and_concurrency_do_not_change_the_saved_edit(app, monkeypatch, decision):
    stub_probe(monkeypatch)
    client, store, value = initial(app)
    pid = value["id"]
    data = b"second original"
    response = reserve(client, value, data) if decision != "wrong_intent" else client.post(
        f"/api/projects/{pid}/uploads/preflight", json={"purpose":"source","slot":"B","filename":"Camera.mp4","size_bytes":len(data)})
    assert response.status_code == 201, response.get_json()
    receipt = response.get_json()
    transfer(client, receipt, data)
    before = store.load(pid)
    if decision == "stop":
        assert client.post(receipt["cancel_url"]).get_json()["cancelled"]
    elif decision == "revision":
        before = store.update(pid, lambda p: p.update(name="A different saved version"))
    elif decision in {"revision_during_probe", "stop_during_probe"}:
        probe = server.probe_media
        def race(*args, **kwargs):
            nonlocal before
            if decision == "stop_during_probe":
                with ThreadPoolExecutor(max_workers=1) as pool:
                    stopped = pool.submit(
                        lambda: app[0].test_client().post(receipt["cancel_url"]).get_json()
                    ).result(timeout=5)
                assert stopped["active"] and stopped["cancelled"] and not stopped["removed"]
            else:
                before = store.update(pid, lambda p: p.update(name="Saved during final probe"))
            return probe(*args, **kwargs)
        monkeypatch.setattr(server, "probe_media", race)
    rejected = commit(client, value, receipt)
    assert rejected.status_code == 409, rejected.get_json()
    assert store.load(pid) == before
    assert not list((store.project_dir(pid) / "media").glob("source-B-*.mp4"))
    assert not app[2]


def test_independent_b_empty_lane_is_not_resurrected_by_projection(app, monkeypatch):
    stub_probe(monkeypatch)
    client, store, value = initial(app)
    attach(client, value)
    assert project_geometry(store.load(value["id"]), "B") == [(0, 2.25, 0)]
    edit(client, store, value, "sequence_remove_range", slot="B", start=0, end=4)
    after = store.load(value["id"])
    assert source_track_clips(after, "B") == []
    assert project_geometry(after, "B") == []
    assert project_geometry(after, "A") == [(0, 4, 0)]
    edit(client, store, value, "undo")
    assert project_geometry(store.load(value["id"]), "B") == [(0, 2.25, 0)]
    edit(client, store, value, "redo")
    assert project_geometry(store.load(value["id"]), "B") == []


def test_attach_keeps_existing_locked_media_track_and_title(app, monkeypatch):
    stub_probe(monkeypatch)
    client, store, project = initial(app)
    fixture = store.project_dir(project["id"]) / "media/assets/fixture.png"
    fixture.parent.mkdir(exist_ok=True)
    fixture.write_bytes(b"test-only placeholder; this rollback test does not decode it")
    asset = "asset_" + "a" * 32
    project["assets"][asset] = {"id": asset, "name": "Fixture", "kind": "image",
                                "path": "media/assets/fixture.png", "duration": 1., "status": "ready"}
    store.save(project)
    edit(client, store, project, "media_add", asset_id=asset, start=.5, end=1.5)
    edit(client, store, project, "text_add", kind="title", text="Keep the placed title", start=1, end=2)
    edit(client, store, project, "layer_tracks_enable")
    stored = store.load(project["id"])
    track = stored["manual"]["media_clips"][0]["track_id"]
    edit(client, store, project, "layer_track_lock", track_id=track, locked=True)
    before = store.load(project["id"])
    attach(client, before)
    after = store.load(project["id"])
    assert after["manual"] == before["manual"]
    assert after["assets"] == before["assets"]
    assert [row["track_id"] for row in after["manual"]["media_clips"]] == [track]
    assert after["manual"]["text_clips"][0]["text"] == "Keep the placed title"
    assert next(row for row in after["manual"]["layer_tracks"]["tracks"] if row["id"] == track)["locked"]


@pytest.mark.parametrize("offset,expected", [(.5, [(0,.75,1.5),(2.5,4,0)]), (-.5, [(2,3.75,.5)])])
def test_alignment_is_on_a_original_clock_not_picture_speed_or_edit_time(app, monkeypatch, offset, expected):
    stub_probe(monkeypatch)
    client, store, project = initial(app)
    edit(client, store, project, "sequence_split_all", time=2)
    edit(client, store, project, "sequence_move_range", start=2, end=4, to=0, mode="insert")
    before = store.load(project["id"])
    first = source_track_clips(before, "A")[0]["id"]
    edit(client, store, project, "sequence_speed", slot="A", clip_id=first, speed=2)
    before = store.load(project["id"])
    before["manual"]["source_mixer"]["sync_offset"] = offset
    before = store.save(before)
    attach(client, before)
    assert project_geometry(store.load(before["id"]), "B") == expected


def test_b_does_not_turn_on_audio_if_the_original_edit_is_silent(app, monkeypatch):
    stub_probe(monkeypatch)
    client, store, project = initial(app)
    project["sources"]["A"]["has_audio"] = False
    before = store.save(project)
    attach(client, before)
    value = store.load(project["id"])
    assert _effective_audio_slot(value) is None
    edit(client, store, project, "set_source_mixer", screen_slot="A", camera_slot="B", audio_slot="A")
    assert _effective_audio_slot(store.load(project["id"])) is None
    edit(client, store, project, "set_source_mixer", screen_slot="A", camera_slot="B", audio_slot="B")
    assert _effective_audio_slot(store.load(project["id"])) == "B"


def write_movie(ffmpeg, path, color, other, duration, frequency, *, late_color=None):
    filters = f"color={color}:s=160x96:r=30:d={duration},drawbox=x=80:y=0:w=80:h=96:color={other}:t=fill"
    if late_color:
        filters += f",drawbox=x=80:y=0:w=80:h=96:color={late_color}:t=fill:enable='gte(t,2)'"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", filters,
                    "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
                    "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
                    "-c:a", "aac", "-shortest", str(path)], check=True, capture_output=True, timeout=20)
    return path.read_bytes()


def test_real_portrait_render_keeps_independent_crops_b_gaps_and_a_audio(app, tmp_path):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    a = write_movie(ffmpeg, tmp_path / "game.mp4", "red", "lime", 4, 440)
    b = write_movie(ffmpeg, tmp_path / "camera.mp4", "blue", "yellow", 2.3, 660, late_color="magenta")
    client, store, project = initial(app, mode="9:16", a_bytes=a)
    edit(client, store, project, "sequence_split_all", time=2)
    edit(client, store, project, "sequence_move_range", start=2, end=4, to=0, mode="insert")
    before = store.load(project["id"])
    attach(client, before, b)
    after = store.load(project["id"])
    assert after["manual"] == before["manual"] and after["draft"] == before["draft"]
    assert after["settings"]["aspect"] == "9:16" and after["settings"]["layout"] == "A"
    assert project_geometry(after, "B") == [(0, .3, 2), (2, 4, 0)]
    edit(client, store, project, "sequence_layout", start=0, end=4, layout="stacked")
    edit(client, store, project, "sequence_crop", slot="A", start=0, end=4, x=0, y=.5, zoom=2.5)
    edit(client, store, project, "sequence_crop", slot="B", start=0, end=4, x=1, y=.5, zoom=2.5)
    edit(client, store, project, "sequence_remove_range", slot="B", start=2, end=2.5)
    final = store.load(project["id"])
    assert project_geometry(final, "A") == project_geometry(before, "A")
    assert project_geometry(final, "B") == [(0, .3, 2), (2.5, 4, .5)]
    assert [row["crop"]["x"] for row in source_track_clips(final, "A")] == [0, 0]
    assert [row["crop"]["x"] for row in source_track_clips(final, "B")] == [1, 1]
    result = render_project(JobContext(Job("synthetic-render", "render", project["id"]), threading.Lock()),
                            project["id"], store, app[1], {"_force_software": True, "_require_layout_coverage": True})
    assert len(store.load(project["id"])["exports"]) == 1
    assert result["export"]["id"] == store.load(project["id"])["exports"][0]["id"]
    path, = app[1].exports_dir.glob("*.mp4")
    info = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(path)]))
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (video["width"], video["height"], video["nb_frames"]) == (720, 1280, "120")
    def pixel(time, y):
        raw = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(time), "-i", str(path),
                                       "-vf", f"crop=2:2:360:{y}", "-an", "-frames:v", "1", "-pix_fmt", "rgb24",
                                       "-f", "rawvideo", "pipe:1"])
        return tuple(raw[:3])
    for covered in (.1, 3):
        r,g,b = pixel(covered, 140)
        # At edit time .1 we see B's original 2.1 (magenta), not its
        # beginning (yellow). Edit time 3 shows B's original 1 instead.
        assert r > 180 and ((g < 55 and b > 180) if covered == .1 else (g > 180 and b < 55))
        r,g,b = pixel(covered, 910)
        assert r > 180 and max(g,b) < 55       # Cropped left side of gameplay.
    for missing in (.8, 2.2):
        r,g,b = pixel(missing, 140)
        assert r > 180 and max(g,b) < 55       # Neither repeat nor freeze B.
    pcm = samples(ffmpeg, path)
    for time in (.1, .8, 2.2, 3):
        assert tone_level(pcm, time, 440) > .025
        assert tone_level(pcm, time, 660) < .002
    assert store.load(project["id"])["analysis"] == before["analysis"]
