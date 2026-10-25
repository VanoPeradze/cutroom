"""New footage includes native sound; saved silence remains an explicit choice."""
from __future__ import annotations

import copy
import subprocess

import pytest

from cutroom.editing import apply_manual_edit
from cutroom.media_library import prepare_media_edit
from cutroom.projects import ProjectStore
from cutroom.render_inventory import audible
from test_media_library import ASSET, add, api, project
from test_media_render import media, pixel, project as render_project, render, samples, tone_level


@pytest.mark.parametrize("has_audio", [True, False])
def test_added_video_uses_its_native_audio_metadata(has_audio):
    value = project()
    value["assets"][ASSET].update(kind="video", has_audio=has_audio)
    clip = add(value, start=3, end=6)
    assert clip["audio_enabled"] is has_audio
    assert clip["role"] == "voice" and clip["muted"] is False
    assert audible(clip, value["assets"][ASSET]) is has_audio
    assert (clip["start"], clip["end"], clip["source_start"]) == (3, 6, 0)


@pytest.mark.parametrize("role", ["music", "effects"])
def test_new_overlay_respects_explicit_audio_choices(role):
    value = project()
    value["assets"][ASSET].update(kind="video", has_audio=True)
    clip = add(value, audio_enabled=False, muted=True, volume_db=-9, role=role)
    assert (clip["audio_enabled"], clip["muted"], clip["volume_db"], clip["role"]) == (False, True, -9, role)
    apply_manual_edit(value, {"action": "media_update", "clip_id": clip["id"], "source_start": 1, "end": 10, "speed": 2})
    saved = value["manual"]["media_clips"][0]
    assert (saved["audio_enabled"], saved["muted"], saved["volume_db"], saved["role"]) == (False, True, -9, role)
    assert saved["source_start"] == 1 and saved["video_source_start"] == 1


def test_audio_choices_survive_save_reopen_undo_and_redo(api):
    app, client, store, pid = api
    store.update(pid, lambda value: value["assets"][ASSET].update(kind="video", has_audio=True))

    def post(action, **fields):
        response = client.post(f"/api/projects/{pid}/manual/edit", json={
            "action": action, "expected_revision": store.load(pid)["revision"], **fields,
        })
        assert response.status_code == 200, response.get_json()

    # Represents a deliberately silent saved overlay from an older project.
    post("media_add", asset_id=ASSET, start=2, end=5, audio_enabled=False)
    silent = copy.deepcopy(store.load(pid)["manual"]["media_clips"][0])
    post("media_update", clip_id=silent["id"], audio_enabled=True, muted=True,
         volume_db=-6, role="effects", source_start=1, speed=2)
    changed = copy.deepcopy(store.load(pid)["manual"]["media_clips"][0])
    reopened = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert reopened["manual"]["media_clips"][0] == changed
    assert (changed["audio_enabled"], changed["muted"], changed["volume_db"], changed["role"]) == (True, True, -6, "effects")
    assert (changed["source_start"], changed["video_source_start"], changed["speed"]) == (1, 1, 2)
    post("undo")
    assert store.load(pid)["manual"]["media_clips"][0] == silent
    post("redo")
    assert store.load(pid)["manual"]["media_clips"][0] == changed
    # Unrelated additions must not migrate an existing silent overlay.
    post("media_add", asset_id=ASSET, start=6, end=9)
    assert store.load(pid)["manual"]["media_clips"][0] == changed


def test_real_default_overlay_sound_keeps_trim_clock_gain_and_picture_speed(media, tmp_path):
    value = render_project()
    value["assets"] = {"video": {"kind": "video", "path": "source.mp4", "duration": 3, "has_audio": True}}
    value["manual"].update(prepare_media_edit(value, {
        "action": "media_add", "asset_id": "video", "start": .5, "end": 2.5,
        "source_start": .5, "speed": 2, "volume_db": -6,
    }))
    value["manual"]["audio_mixer"] = {"source_muted": True}
    output = render(value, media, tmp_path)
    data = samples(media[1], output)
    assert tone_level(data, .7, 440) < .002
    assert .12 < tone_level(data, 1.3, 440) < .18
    assert tone_level(data, 2.3, 440) < .002
    assert pixel(media[1], output, 1.3)[2] > 200  # Picture is faster, sound stays at1x.


@pytest.mark.parametrize("silence", ["audio_disabled", "clip_muted", "voice_muted", "no_audio_stream"])
def test_real_overlay_silence_choices_are_preserved(media, tmp_path, silence):
    value = render_project()
    path = "source.mp4"
    if silence == "no_audio_stream":
        path = "silent-video.mp4"
        subprocess.run([media[1], "-v", "error", "-y", "-i", str(media[3]), "-map", "0:v:0",
                        "-c:v", "copy", "-an", str(media[0] / path)],
                       check=True, capture_output=True, timeout=10)
    value["assets"] = {"video": {"kind": "video", "path": path, "duration": 3,
                                          "has_audio": silence != "no_audio_stream"}}
    value["manual"].update(prepare_media_edit(value, {
        "action": "media_add", "asset_id": "video", "start": 0, "end": 3,
        **({"audio_enabled": False} if silence == "audio_disabled" else {}),
        **({"muted": True} if silence == "clip_muted" else {}),
    }))
    value["manual"]["audio_mixer"] = {"source_muted": True, "voice_muted": silence == "voice_muted"}
    data = samples(media[1], render(value, media, tmp_path))
    assert tone_level(data, 1.3, 440) < .002
