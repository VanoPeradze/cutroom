"""Lossless independent Split: retain exact content without changing edit time."""
from __future__ import annotations
import copy
import hashlib
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.projects import ProjectStore
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post


@pytest.mark.parametrize("key,index", [("media_clips", 1), ("media_clips", 2), ("media_clips", 3), ("text_clips", 1), ("text_clips", 2)])
def test_selected_split_keeps_duration_other_layers_clocks_and_original_files_and_one_undo(unlocked, key, index):
    app, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["track_locks"] = {"A": True, "B": True}
    store.update(pid, prepare)
    before = store.load(pid)
    selected = before["manual"][key][index]
    originals = [p for p in (store.project_dir(pid) / "media").rglob("*") if p.is_file()]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    action = "text_split" if key == "text_clips" else "media_split"
    response = post(unlocked, action, clip_id=selected["id"], time=5.)
    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    left, right = after["manual"][key][index:index + 2]
    assert (left["id"], left["start"], left["end"], right["start"], right["end"]) == (selected["id"], selected["start"], 5., 5., selected["end"])
    assert right["id"] not in {r["id"] for r in before["manual"][key]}
    assert after["manual"][key][:index] == before["manual"][key][:index]
    assert after["manual"][key][index + 2:] == before["manual"][key][index + 1:]
    if key == "media_clips":
        kind = before["assets"][selected["asset_id"]]["kind"]
        assert left["source_start"] == selected["source_start"]
        assert right["source_start"] == selected["source_start"] + (0 if kind == "image" else 5. - selected["start"])
        assert (left["fade_in"], left["fade_out"], right["fade_in"], right["fade_out"]) == (selected["fade_in"], 0, 0, selected["fade_out"])
        for piece in (left, right):
            for field in ("asset_id", "speed", "volume_db", "muted", "role", "x", "y", "w", "h", "fit", "motion", "audio_enabled"):
                assert piece[field] == selected[field]
        if kind == "video":
            assert left["video_source_start"] == selected["video_source_start"]
            assert right["video_source_start"] == selected["video_source_start"] + (5. - selected["start"]) * selected["speed"]
    else:
        for piece in (left, right):
            for field in ("text", "kind", "style", "scale", "template", "subtext", "position"):
                assert piece[field] == selected[field]
    for field, value in before["manual"].items():
        if field not in (key, "history", "_history"):
            assert after["manual"][field] == value
    for field in ("sources", "assets", "analysis"):
        assert after[field] == before[field]
    assert after["manual"]["sequence"]["duration"] == 15.
    assert after["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert post(unlocked, "undo").status_code == 200
    assert content(store.load(pid)) == content(before)
    assert post(unlocked, "redo").status_code == 200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid)) == content(after)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes


@pytest.mark.parametrize("kind", [VIDEO, IMAGE])
@pytest.mark.parametrize("motion", ["pan", "zoom_in"])
def test_animated_split_is_atomic_instead_of_restarting_motion(unlocked, kind, motion):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", kind, 4., 6., motion=motion)]
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "media_split", clip_id="media_" + "1" * 32, time=5.)
    assert response.status_code == 400 and "pan/zoom" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("at", [4.1, 5.9])
def test_fade_interior_split_is_atomic_instead_of_retiming_envelope(unlocked, at):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "media_split", clip_id="media_" + "2" * 32, time=at)
    assert response.status_code == 400 and "fade" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("bounds,fade", [((4., 6.), 1.), ((4.92, 5.08), .08)])
def test_exact_fade_and_minimum_piece_boundaries_remain_supported(unlocked, bounds, fade):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, *bounds, fade_in=fade, fade_out=fade)]
    store.update(pid, prepare)
    response = post(unlocked, "media_split", clip_id="media_" + "1" * 32, time=5.)
    assert response.status_code == 200, response.get_json()
    left, right = store.load(pid)["manual"]["media_clips"]
    assert (left["fade_in"], left["fade_out"], right["fade_in"], right["fade_out"]) == (fade, 0., 0., fade)


@pytest.mark.parametrize("time", [3., 4., 4.079, 5.921, 6., 7.])
def test_outside_or_tiny_split_does_not_mutate_history(unlocked, time):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.state_path(pid).read_bytes()
    assert post(unlocked, "media_split", clip_id="media_" + "2" * 32, time=time).status_code == 400
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("key,count", [("media_clips", 200), ("text_clips", 2000)])
def test_split_capacity_rejects_atomically_from_a_valid_limit_state(unlocked, key, count):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        if key == "media_clips":
            value["manual"][key] = [media_row("1", VIDEO, 4., 6., id=f"media_{i:032x}") for i in range(count)]
        else:
            from cutroom.text_clips import validated_text_clips
            value["manual"]["sequence"]["duration"] = 200.
            value["manual"][key] = [text_row("1", i * .1, i * .1 + (.8 if i == 0 else .08), id=f"text_{i:032x}") for i in range(count)]
            assert len(validated_text_clips(value)) == 2000
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    action, prefix, at = ("media_split", "media_", 5.) if key == "media_clips" else ("text_split", "text_", .4)
    response = post(unlocked, action, clip_id=prefix + "0" * 32, time=at)
    assert response.status_code == 400 and str(count) in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("speed", [.25, .5, 1.25, 4.])
def test_split_keeps_picture_hold_and_attached_audio_clocks_independent(unlocked, speed):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["assets"][VIDEO]["duration"] = 3.
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 4., 6., video_source_start=8., speed=speed)]
    store.update(pid, prepare)
    response = post(unlocked, "media_split", clip_id="media_" + "1" * 32, time=5.)
    assert response.status_code == 200, response.get_json()
    left, right = store.load(pid)["manual"]["media_clips"]
    assert (left["source_start"], right["source_start"]) == (1., 2.)
    assert (left["video_source_start"], right["video_source_start"]) == (8., 8. + speed)


@pytest.mark.parametrize("speed", [1., 2.])
def test_real_encoded_split_is_picture_audio_title_equivalent_and_reopenable(library_api, media, speed):
    # Three-second generated red/green/blue footage with a 440 Hz spoken-clock
    # marker, 880 Hz music and a yellow still. No user media or AI is involved.
    import shutil
    import threading
    from cutroom.jobs import Job, JobContext
    from cutroom.render import render_project
    from test_media_render import project as render_fixture, pixel, samples, tone_level

    app, client, store, pid = library_api
    settings = app.extensions["cutroom_settings"]
    settings.raw["render"].update(prefer_hardware=False, min_free_mb=0)
    value = store.load(pid)
    value.update(render_fixture())
    value["sources"]["A"].update(relative_path="media/source.mp4", generation="synthetic-A")
    value["settings"].update(workflow="manual", aspect="source", resolution="1440", quality="fast", burn_captions=False)
    value["draft"].update(engine="manual", output_duration=3., audio_plan=[], cuts=[], edit_points=[], audio_policy={"normalize": False})
    directory = store.project_dir(pid)
    shutil.copyfile(media[3], directory / "media/source.mp4")
    value["assets"] = {}
    originals = [directory / "media/source.mp4"]
    for asset_id, kind, source in ((ASSET, "video", media[3]), (VIDEO, "video", media[3]), (AUDIO, "audio", media[4]), (IMAGE, "image", media[5])):
        relative = f"media/assets/{asset_id}/original{source.suffix}"
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        originals.append(target)
        value["assets"][asset_id] = {"id": asset_id, "name": source.name, "kind": kind, "status": "ready",
            "duration": 0. if kind == "image" else 3., "width": 80 if kind == "image" else 160,
            "height": 80 if kind == "image" else 90, "has_audio": kind != "image", "path": relative, "preview_path": relative}
    value["manual"].update(cuts=[], keeps=[], camera_overrides=[], media_clips=[
        media_row("1", VIDEO, .5, 2.5, source_start=.5, video_source_start=.5, speed=speed,
                  fade_in=.2, fade_out=.2, x=0., y=0., w=.5, h=1., fit="cover", volume_db=0.),
        media_row("2", AUDIO, .25, 2.75, source_start=.25, role="music", volume_db=-6., fade_in=.25, fade_out=.25),
        media_row("3", IMAGE, .25, 2.75, source_start=0., audio_enabled=False, fade_in=0., fade_out=0., x=.5, y=0., w=.5, h=.5),
    ], text_clips=[text_row("1", .75, 2.25, text="Saved title", position="bottom", template="plain", subtext="", scale=75)],
        audio_mixer={"source_muted": True, "ducking": False})
    store.save(value)
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    def encoded(label):
        context = JobContext(Job(label, "render", pid), threading.Lock())
        record = render_project(context, pid, store, settings, {"quality": "fast", "_force_software": True})["export"]
        return settings.exports_dir / record["name"], record
    baseline, baseline_record = encoded("mixed-before")
    before_content = content(store.load(pid))
    for action, clip_id in [("media_split", "media_" + digit * 32) for digit in "123"] + [("text_split", "text_" + "1" * 32)]:
        before_step = content(store.load(pid))
        response = post(library_api, action, clip_id=clip_id, time=1.5)
        assert response.status_code == 200, response.get_json()
        after_step = content(store.load(pid))
        assert post(library_api, "undo").status_code == 200
        assert content(store.load(pid)) == before_step
        assert post(library_api, "redo").status_code == 200
        assert content(ProjectStore(settings).load(pid)) == after_step
    assert store.load(pid)["manual"]["history"]["undo_count"] == 4
    output, record = encoded("mixed-after")
    assert baseline_record["duration"] == pytest.approx(3., abs=1 / 30)
    assert record["duration"] == pytest.approx(3., abs=1 / 30)
    assert baseline_record["manual_text_count"] == 1 and record["manual_text_count"] == 2
    ffmpeg = media[1]
    # Retained image/text pixels and independent picture speed remain identical
    # across the new cut boundary; no animation or source clock restarts.
    for old_time, new_time in ((.6, .6), (.9, .9), (1.3, 1.3), (1.8, 1.8), (2.3, 2.3)):
        for x, y in ((30, 15), (120, 15), (80, 75)):
            old_rgb, new_rgb = pixel(ffmpeg, baseline, old_time, x, y), pixel(ffmpeg, output, new_time, x, y)
            assert max(abs(a - b) for a, b in zip(old_rgb, new_rgb)) < 24, (speed, old_time, new_time, x, y, old_rgb, new_rgb)
    import subprocess
    def white_text_pixels(path, time):
        rgb = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(time), "-i", str(path),
                                       "-an", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
        return sum(min(rgb[i:i + 3]) > 170 and max(rgb[i:i + 3]) - min(rgb[i:i + 3]) < 45
                   for i in range(0, len(rgb), 3))
    assert white_text_pixels(baseline, 1.1) > 10
    assert white_text_pixels(output, 1.1) > 10
    assert white_text_pixels(output, 1.8) > 10
    assert white_text_pixels(output, 2.6) == 0
    old_audio, new_audio = samples(ffmpeg, baseline), samples(ffmpeg, output)
    for old_time, new_time in ((.3, .3), (.6, .6), (1.1, 1.1), (1.6, 1.6), (2.55, 2.55)):
        for frequency in (440, 880):
            assert tone_level(new_audio, new_time, frequency) == pytest.approx(tone_level(old_audio, old_time, frequency), abs=.008)
    assert tone_level(new_audio, 1.1, 440) > .2
    assert tone_level(new_audio, 1.1, 880) > .05
    assert tone_level(new_audio, 2.2, 440) < .003
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes
    assert len(store.load(pid)["exports"]) == 2 and baseline.exists() and output.exists()
