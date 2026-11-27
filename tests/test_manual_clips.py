"""Hand-marked clip ranges: saved with the project, never a render input, and never
exported silently after the edit changed inside them."""
import copy
import json
import subprocess
import threading
import time

import pytest

from cutroom.jobs import Job, JobContext
from cutroom.manual_clips import (LIMIT, ManualClipError, WindowReader, apply_manual_clip, public_view,
                                  require_exportable, saved_rows)
from cutroom.render import _render_input_fingerprint
from server import create_app
from test_media_render import media
from test_track_destination_render import prepared


def project():
    # 40 s recording, 5 s cut out at 10–15 s, so the edit is 35 s long.
    return {"id": "project_112233445566", "revision": 1, "name": "Pod",
            "sources": {"A": {"duration": 40., "width": 160, "height": 90, "has_audio": True}},
            "settings": {"fps": 30}, "manual": {}, "assets": {},
            "draft": {"output_duration": 35., "keep_ranges": [{"start": 0., "end": 10.}, {"start": 15., "end": 40.}],
                      "camera_plan": [{"start": 0., "end": 40., "camera": "A"}]}}


def add(a=60, b=180, fps=30, **extra):
    return {"action": "add", "expected_revision": 1, "start_frame": a, "end_frame": b, "fps": fps, **extra}


def statuses(p):
    return [row["status"] for row in public_view(p)["items"]]


def test_add_rename_remove_sort_and_never_touch_the_edit():
    p = project(); before = copy.deepcopy(p)
    late = apply_manual_clip(p, add(600, 720))
    early = apply_manual_clip(p, add(60, 180, name="  Best   moment "))
    rows = saved_rows(p)
    assert [r["id"] for r in rows] == [early["id"], late["id"]]
    assert (early["name"], late["name"]) == ("Best moment", "Clip 1")
    assert {k: p[k] for k in before} == before
    view = public_view(p)
    assert all("fingerprint" not in item for item in view["items"]) and statuses(p) == ["ready", "ready"]
    apply_manual_clip(p, {"action": "rename", "id": late["id"], "name": "Second", "expected_revision": 1})
    assert saved_rows(p)[1]["name"] == "Second" and saved_rows(p)[1]["fingerprint"] == late["fingerprint"]
    with pytest.raises(ManualClipError):
        apply_manual_clip(p, {"action": "rename", "id": late["id"], "name": "Second", "expected_revision": 1})
    with pytest.raises(ManualClipError) as error:
        apply_manual_clip(p, add(60, 180))
    assert error.value.status == 409
    removed = apply_manual_clip(p, {"action": "remove", "id": early["id"], "expected_revision": 1})
    assert removed["id"] == early["id"] and [r["id"] for r in saved_rows(p)] == [late["id"]]
    with pytest.raises(ManualClipError) as error:
        apply_manual_clip(p, {"action": "remove", "id": early["id"], "expected_revision": 1})
    assert error.value.status == 409


@pytest.mark.parametrize("patch", [{"start_frame": True}, {"start_frame": -1}, {"end_frame": 60}, {"end_frame": 1051},
    {"start_frame": 1.5}, {"fps": 25}, {"fps": 29.97}, {"fps": 60}, {"name": ""}, {"name": "a" * 81}, {"name": "a\x00"},
    {"name": 3}, {"action": "cut"}, {"unexpected": 1}, {"id": "mclip_000000000000"}])
def test_invalid_input_never_creates_a_list(patch):
    p = project()
    with pytest.raises(ManualClipError):
        apply_manual_clip(p, {**add(), **patch})
    assert "manual_clips" not in p


def test_end_of_edit_is_allowed_exactly():
    p = project()
    apply_manual_clip(p, add(1049, 1050))
    assert statuses(p) == ["ready"]


@pytest.mark.parametrize("value", [None, [], {"version": 2, "items": []}, {"version": True, "items": []},
    {"version": 1, "items": [{}]}, {"version": 1, "items": [], "more": 1}])
def test_unknown_saved_formats_fail_closed_without_data_loss(value):
    p = project(); p["manual_clips"] = copy.deepcopy(value)
    with pytest.raises(ManualClipError) as error:
        apply_manual_clip(p, add())
    assert error.value.status == 409 and p["manual_clips"] == value
    assert public_view(p) == {"version": 1, "items": [], "unavailable": True}


def test_capacity_limit():
    p = project(); row = apply_manual_clip(p, add())
    p["manual_clips"]["items"] = [{**row, "id": f"mclip_{i:012x}", "start_frame": i, "end_frame": i + 30} for i in range(LIMIT)]
    with pytest.raises(ManualClipError, match=str(LIMIT)):
        apply_manual_clip(p, add(900, 960))
    apply_manual_clip(p, {"action": "remove", "id": "mclip_000000000000", "expected_revision": 1})
    apply_manual_clip(p, add(900, 960))
    assert len(saved_rows(p)) == LIMIT


def keep(p, ranges):
    p["draft"]["keep_ranges"] = [{"start": a, "end": b} for a, b in ranges]
    p["draft"]["output_duration"] = sum(b - a for a, b in ranges)


def test_edits_inside_or_before_a_range_need_review_and_edits_after_it_do_not():
    p = project()
    first = apply_manual_clip(p, add(60, 180))      # edit 2–6 s
    second = apply_manual_clip(p, add(600, 720))    # edit 20–24 s = recording 25–29 s
    # A trim after both ranges changes nothing they show.
    keep(p, [(0., 10.), (15., 35.)])
    assert statuses(p) == ["ready", "ready"]
    # A cut between them moves the later moment: it must be reviewed, the first stays ready.
    keep(p, [(0., 8.), (15., 40.)])
    assert statuses(p) == ["ready", "changed"]
    with pytest.raises(ManualClipError, match="Review"):
        require_exportable(p, second["id"], {k: second[k] for k in ("start_frame", "end_frame", "fps")})
    assert require_exportable(p, first["id"], {k: first[k] for k in ("start_frame", "end_frame", "fps")})["id"] == first["id"]
    # A trim inside the first range changes it too.
    keep(p, [(0., 3.), (4., 8.), (15., 40.)])
    assert statuses(p)[0] == "changed"
    # Accepting keeps the range as it is now.
    apply_manual_clip(p, {"action": "accept", "id": first["id"], "expected_revision": 1})
    assert statuses(p)[0] == "ready"


def test_text_overlay_inside_a_range_needs_review():
    p = project(); apply_manual_clip(p, add(60, 180)); apply_manual_clip(p, add(600, 720))
    p["manual"]["text_clips"] = [{"id": "text_1", "start": 21., "end": 22., "text": "Wow"}]
    assert statuses(p) == ["ready", "changed"]


def test_ranges_past_a_shortened_edit_are_outside_and_cannot_be_accepted():
    p = project(); row = apply_manual_clip(p, add(600, 720))
    keep(p, [(0., 10.)])
    assert statuses(p) == ["outside"]
    with pytest.raises(ManualClipError, match="after the edit"):
        apply_manual_clip(p, {"action": "accept", "id": row["id"], "expected_revision": 1})


def test_export_must_match_the_saved_range():
    p = project(); row = apply_manual_clip(p, add())
    with pytest.raises(ManualClipError, match="does not match"):
        require_exportable(p, row["id"], {"start_frame": 60, "end_frame": 181, "fps": 30})
    with pytest.raises(ManualClipError):
        require_exportable(p, "nope", {"start_frame": 60, "end_frame": 180, "fps": 30})


def test_fps_change_rejects_new_marks():
    p = project(); apply_manual_clip(p, add())
    p["settings"]["fps"] = 60
    with pytest.raises(ManualClipError, match="frame rate"):
        apply_manual_clip(p, add(60, 180, fps=30))


def test_fingerprint_ignores_occurrence_ids():
    p = project(); reader = WindowReader(p)
    split = copy.deepcopy(p)
    keep(split, [(0., 5.), (5., 10.), (15., 40.)])
    assert WindowReader(split).fingerprint(1., 9.) == reader.fingerprint(1., 9.)


# --- API -------------------------------------------------------------------

def test_api_saves_survives_reload_and_is_not_a_render_input(media, tmp_path):
    p, store, settings, _, unchanged = prepared(media, tmp_path)
    client = create_app(settings).test_client(); pid = p["id"]; url = f"/api/projects/{pid}/manual-clips"
    initial = store.load(pid); rev = initial["revision"]
    response = client.post(url, json={**add(0, 30), "expected_revision": rev})
    body = response.get_json()
    assert response.status_code == 200, body
    assert (body["previous_revision"], body["revision"]) == (rev, rev + 1)
    assert body["manual_clips"]["items"][0]["id"] == body["clip_id"]
    stale = client.post(url, json={**add(30, 60), "expected_revision": rev})
    assert stale.status_code == 409
    viewed = create_app(settings).test_client().get(f"/api/projects/{pid}").get_json()["project"]
    assert viewed["manual_clips"] == body["manual_clips"]
    for key in ("manual", "draft", "sources", "assets", "settings"):
        assert store.load(pid)[key] == initial[key]
    assert _render_input_fingerprint(store.load(pid)) == _render_input_fingerprint(initial)
    live = client.get(url).get_json()
    assert live == {"project_id": pid, "revision": rev + 1, "manual_clips": body["manual_clips"]}
    bad = client.post(url, json={**add(0, 9000), "expected_revision": rev + 1})
    assert bad.status_code == 400 and bad.get_json()["error"] == "invalid_clip"
    unchanged()


def test_api_render_rejects_mismatched_or_changed_clips_before_any_job(media, tmp_path):
    p, store, settings, _, unchanged = prepared(media, tmp_path)
    client = create_app(settings).test_client(); pid = p["id"]
    rev = store.load(pid)["revision"]
    clip = client.post(f"/api/projects/{pid}/manual-clips", json={**add(0, 30), "expected_revision": rev}).get_json()
    rev = clip["revision"]; cid = clip["clip_id"]
    def render(body):
        return client.post(f"/api/projects/{pid}/render", json=body)
    no_range = render({"clip": cid})
    assert (no_range.status_code, no_range.get_json()["error"]) == (400, "invalid_export_range")
    wrong = render({"clip": cid, "range": {"start_frame": 0, "end_frame": 31, "fps": 30, "expected_revision": rev}})
    assert (wrong.status_code, wrong.get_json()["error"]) == (409, "clip_changed")
    def trim(project):
        project["manual"]["source_tracks"]["A"][0]["source_start"] = 0.5
    rev = store.update(pid, trim)["revision"]
    changed = render({"clip": cid, "range": {"start_frame": 0, "end_frame": 30, "fps": 30, "expected_revision": rev}})
    assert (changed.status_code, changed.get_json()["error"]) == (409, "clip_changed")
    assert not list(settings.exports_dir.iterdir())
    unchanged()


# --- Acceptance: long recording, two non-contiguous ranges, real MP4s ---------

RAMP = 4  # luma rises 4 levels per recorded second


def long_recording(media, tmp_path):
    from cutroom.projects import ProjectStore
    p, store, settings, _, _ = prepared(media, tmp_path)
    ffmpeg = media[1]
    path = store.project_dir(p["id"]) / "media" / "source.mp4"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    f"color=black:s=160x90:r=30:d=40,format=gray,geq=lum='min(255,16+T*{RAMP})',format=yuv420p",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=40",
                    "-c:v", "libx264", "-preset", "ultrafast", "-g", "30", "-c:a", "aac", "-t", "40", str(path)],
                   check=True, capture_output=True, timeout=60)
    src = p["sources"]["A"]
    p["sources"] = {"A": {**src, "duration": 40., "has_audio": True}}
    p["assets"] = {}; p["manual"] = {}; p["analysis"] = {}
    p["draft"] = {"keep_ranges": [{"start": 0., "end": 10.}, {"start": 15., "end": 40.}],
                  "camera_plan": [{"start": 0., "end": 40., "camera": "A"}]}
    p["settings"].update(fps=30, audio_source="A", captions=False, burn_captions=False, aspect="source")
    settings.raw["ffmpeg_threads"] = 2
    store.save(p)
    return p["id"], ProjectStore(settings), settings


def probe(ffprobe, path):
    data = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-count_frames", "-show_entries",
        "stream=codec_type,nb_read_frames:format=duration", "-of", "json", str(path)]))
    video = next(s for s in data["streams"] if s["codec_type"] == "video")
    return int(video["nb_read_frames"]), float(data["format"]["duration"]), {s["codec_type"] for s in data["streams"]}


def edge_luma(ffmpeg, path):
    buf = subprocess.check_output([ffmpeg, "-v", "error", "-i", str(path), "-an", "-vf", "scale=16:9",
                                   "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"], timeout=30)
    frames = [buf[i:i + 144] for i in range(0, len(buf), 144)]
    mean = lambda frame: sum(frame) / len(frame)
    return mean(frames[0]), mean(frames[-1])


def wait(client, job_id):
    for _ in range(600):
        job = client.get(f"/api/jobs/{job_id}").get_json()["job"]
        if job["status"] in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.1)
    pytest.fail("render did not finish")


def export(client, pid, item):
    revision = client.get(f"/api/projects/{pid}").get_json()["project"]["revision"]
    response = client.post(f"/api/projects/{pid}/render", json={"clip": item["id"], "range": {
        "start_frame": item["start_frame"], "end_frame": item["end_frame"], "fps": item["fps"], "expected_revision": revision}})
    assert response.status_code == 202, response.get_json()
    job = wait(client, response.get_json()["job"]["id"])
    assert job["status"] == "completed", job
    return job


def test_acceptance_long_recording_two_ranges_export_one_then_reopen_and_export_both(media, tmp_path):
    ffmpeg, ffprobe = media[1], media[2]
    pid, store, settings = long_recording(media, tmp_path)
    client = create_app(settings).test_client(); url = f"/api/projects/{pid}/manual-clips"
    loaded = store.load(pid); sources_before = copy.deepcopy(loaded["sources"]); draft_before = copy.deepcopy(loaded["draft"])
    # Edit 2–6 s (recording 2–6 s) and edit 20–23 s (recording 25–28 s, after the cut).
    marks = [(60, 180, "Opening"), (600, 690, "After the cut")]
    revision = loaded["revision"]
    for a, b, name in marks:
        reply = client.post(url, json={**add(a, b, name=name), "expected_revision": revision}).get_json()
        revision = reply["revision"]
    items = reply["manual_clips"]["items"]
    assert [(i["start_frame"], i["end_frame"], i["status"]) for i in items] == [(60, 180, "ready"), (600, 690, "ready")]

    export(client, pid, items[0])
    # The project is still open on the same recording and timeline.
    still = client.get(f"/api/projects/{pid}").get_json()["project"]
    assert still["sources"]["A"]["duration"] == 40. and store.load(pid)["sources"] == sources_before
    assert store.load(pid)["draft"] == draft_before
    assert [i["status"] for i in still["manual_clips"]["items"]] == ["ready", "ready"]

    # Reopen with a fresh app and store, then export both, one after another.
    reopened = create_app(settings).test_client()
    items = reopened.get(f"/api/projects/{pid}").get_json()["project"]["manual_clips"]["items"]
    outputs = [settings.exports_dir / export(reopened, pid, item)["result"]["export"]["name"] for item in items]
    expectations = [(120, 4.0, 2.0, 6.0), (90, 3.0, 25.0, 28.0)]
    for out, (count, seconds, first_s, last_s), (_, _, name) in zip(outputs, expectations, marks):
        assert name in out.name
        frames, duration, kinds = probe(ffprobe, out)
        assert frames == count and kinds == {"video", "audio"}
        assert duration == pytest.approx(seconds, abs=0.05)
        first, last = edge_luma(ffmpeg, out)
        assert first == pytest.approx(16 + first_s * RAMP, abs=3)
        assert last == pytest.approx(16 + (last_s - 1 / 30) * RAMP, abs=3)
