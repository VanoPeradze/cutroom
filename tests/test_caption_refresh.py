"""Export refreshes captions built from another sound, without touching the edit."""
from __future__ import annotations

from cutroom import manual_transcription
from cutroom.manual_transcription import captions_out_of_date
from test_manual_transcription import api, finish, fixture_transcript, open_manual  # noqa: F401  (fixture)


def _camera_sound_edit(api):
    _, store, pid, source, *_ = api
    open_manual(api)
    camera = source.with_name("source-B.mp4")
    camera.write_bytes(b"stubbed camera audio")

    def route_camera(p):
        p["sources"]["B"] = {**p["sources"]["A"], "slot": "B", "relative_path": "media/source-B.mp4",
                             "generation": "camera-generation"}
        p["manual"].setdefault("source_mixer", {}).update(audio_slot="B", sync_offset=1.5)
        p["manual"]["source_tracks"] = {"A": [{"id": "A:main", "start": 0., "end": 6., "source_start": 0.}],
                                        "B": [{"id": "B:main", "start": 0., "end": 4.5, "source_start": 0.}]}
        # The transcript still describes the screen recording (source A).
        p["analysis"].update(transcript=fixture_transcript("he"), audio_source="A", audio_timeline_offset=0.)
        p["settings"]["burn_captions"] = True
    store.update(pid, route_camera)
    return camera


def test_refresh_transcribes_the_routed_sound_and_keeps_the_edit(api, monkeypatch):
    client, store, pid, *_ = api
    camera = _camera_sound_edit(api)
    before = store.load(pid)
    assert captions_out_of_date(before)
    heard = []

    def speech(path, local, **kw):
        heard.append((path, kw["language"]))
        return fixture_transcript(kw["language"])
    monkeypatch.setattr(manual_transcription, "transcribe", speech)

    reply = client.post(f"/api/projects/{pid}/caption-refresh", json={"expected_revision": before["revision"]})
    job = finish(api, reply)
    assert job["status"] == "completed", job
    assert heard == [(camera, "he")]
    after = store.load(pid)
    assert not captions_out_of_date(after)
    analysis = after["analysis"]
    assert analysis["audio_source"] == "B" and analysis["audio_timeline_offset"] == 1.5
    # B timestamps carry the sync offset, which caption projection undoes.
    assert [row["start"] for row in analysis["transcript"]["segments"]] == [1.9, 4.5]
    for key in ("sequence", "source_tracks", "source_mixer"):
        assert after["manual"].get(key) == before["manual"].get(key)
    assert after["draft"] == before["draft"]
    # Nothing left to refresh.
    again = client.post(f"/api/projects/{pid}/caption-refresh", json={"expected_revision": after["revision"]})
    assert again.status_code == 409 and again.get_json()["error"] == "caption_refresh_unavailable"


def test_refresh_is_refused_when_captions_already_match(api):
    client, store, pid, *_ = api
    open_manual(api)
    store.update(pid, lambda p: p["analysis"].update(transcript=fixture_transcript("he"), audio_source="A"))
    current = store.load(pid)
    reply = client.post(f"/api/projects/{pid}/caption-refresh", json={"expected_revision": current["revision"]})
    assert reply.status_code == 409
