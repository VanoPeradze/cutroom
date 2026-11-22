"""Occurrence-only trim/extend with retained clocks, envelope and shared history."""
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
@pytest.mark.parametrize("edge", ["start", "end"])
def test_trim_one_occurrence_preserves_other_layers_and_clocks_with_undo_reopen(unlocked, key, index, edge):
    app, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["track_locks"] = {"A": True, "B": True}
    store.update(pid, prepare)
    before = store.load(pid)
    selected = before["manual"][key][index]
    originals = [p for p in (store.project_dir(pid) / "media").rglob("*") if p.is_file()]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    action = "text_trim" if key == "text_clips" else "media_trim"
    response = post(unlocked, action, clip_id=selected["id"], edge=edge, time=5.)
    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    row = after["manual"][key][index]
    assert row["id"] == selected["id"] and row[edge] == 5.
    opposite = "end" if edge == "start" else "start"
    assert row[opposite] == selected[opposite]
    assert len(after["manual"][key]) == len(before["manual"][key])
    assert after["manual"][key][:index] == before["manual"][key][:index]
    assert after["manual"][key][index + 1:] == before["manual"][key][index + 1:]
    if key == "media_clips":
        kind = before["assets"][selected["asset_id"]]["kind"]
        delta = 5. - selected["start"] if edge == "start" and kind != "image" else 0.
        assert row["source_start"] == selected["source_start"] + delta
        assert row["fade_in"] == (0. if edge == "start" else selected["fade_in"])
        assert row["fade_out"] == (0. if edge == "end" else selected["fade_out"])
        if kind == "video":
            assert row["video_source_start"] == selected["video_source_start"] + delta * selected["speed"]
        for field in ("asset_id", "speed", "volume_db", "muted", "role", "x", "y", "w", "h", "fit", "motion", "audio_enabled"):
            assert row[field] == selected[field]
    else:
        for field in ("text", "kind", "style", "scale", "template", "subtext", "position"):
            assert row[field] == selected[field]
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


@pytest.mark.parametrize("asset", [VIDEO, AUDIO, IMAGE, "text"])
@pytest.mark.parametrize("edge,time", [("start", 3.), ("end", 7.)])
def test_unfaded_static_edges_extend_without_moving_the_opposite_edge(unlocked, asset, edge, time):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", asset if asset != "text" else VIDEO, 4., 6., source_start=2., video_source_start=2.25, speed=1.5 if asset == VIDEO else 1.,
            fade_in=.3 if edge == "end" else 0., fade_out=.4 if edge == "start" else 0.)]
        value["manual"]["text_clips"] = [text_row("1", 4., 6.)]
    store.update(pid, prepare)
    key = "text_clips" if asset == "text" else "media_clips"
    action = "text_trim" if asset == "text" else "media_trim"
    old = store.load(pid)["manual"][key][0]
    response = post(unlocked, action, clip_id=old["id"], edge=edge, time=time)
    assert response.status_code == 200, response.get_json()
    row = store.load(pid)["manual"][key][0]
    assert row[edge] == time and row["end" if edge == "start" else "start"] == old["end" if edge == "start" else "start"]
    if asset != "text":
        assert row["source_start"] == old["source_start"] - (1. if edge == "start" and asset != IMAGE else 0.)
        if asset == VIDEO:
            assert row["video_source_start"] == old["video_source_start"] - (1.5 if edge == "start" else 0.)
        assert (row["fade_in"], row["fade_out"]) == (old["fade_in"], old["fade_out"])


@pytest.mark.parametrize("edge,time,patch,reason", [
    ("start", 4.1, {}, "fade"), ("end", 5.9, {}, "fade"),
    ("start", 5.8, {}, "fade"), ("end", 4.1, {}, "fade"),
    ("start", 3., {}, "envelope"), ("end", 7., {}, "envelope"),
    ("start", 5., {"motion": "pan"}, "pan/zoom"), ("end", 5., {"motion": "zoom_in"}, "pan/zoom"),
    ("start", 2., {"fade_in": 0}, "earlier source"),
    ("start", 3., {"fade_in": 0, "video_source_start": .5}, "earlier picture"),
    ("end", 15., {"fade_out": 0}, "media duration"),
    ("start", 5.93, {}, "0.08"), ("end", 4.07, {}, "0.08"),
    ("start", -1., {}, "between"), ("end", 16., {}, "between"),
    (True, 5., {}, "edge"), ([], 5., {}, "edge"), ("middle", 5., {}, "edge"),
])
def test_unsupported_trim_rejects_atomically_not_clamping_or_retiming(unlocked, edge, time, patch, reason):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"][1].update(patch)
        value["assets"][VIDEO]["duration"] = 10.
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = post(unlocked, "media_trim", clip_id="media_" + "2" * 32, edge=edge, time=time)
    assert response.status_code == 400 and reason in response.get_json()["message"], response.get_json()
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("edge,time", [("start", 4.2), ("end", 5.7)])
def test_exact_flat_fade_boundary_preserves_other_outer_fade(unlocked, edge, time):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    response = post(unlocked, "media_trim", clip_id="media_" + "2" * 32, edge=edge, time=time)
    assert response.status_code == 200, response.get_json()
    row = store.load(pid)["manual"]["media_clips"][1]
    assert row[edge] == time
    assert (row["fade_in"], row["fade_out"]) == ((0., .3) if edge == "start" else (.2, 0.))


@pytest.mark.parametrize("edge,time", [("start", 5.92), ("end", 4.08)])
def test_exact_minimum_and_legacy_opposite_endpoint(unlocked, edge, time):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"][1].update(fade_in=0., fade_out=0.)
    store.update(pid, prepare)
    response = post(unlocked, "media_trim", clip_id="media_" + "2" * 32, edge=edge, time=time)
    assert response.status_code == 200, response.get_json()
    row = store.load(pid)["manual"]["media_clips"][1]
    assert row["end"] - row["start"] == pytest.approx(.08)


@pytest.mark.parametrize("asset", [VIDEO, IMAGE, "text"])
def test_noop_does_not_consume_history_even_for_animated_faded_edges(unlocked, asset):
    _, _, store, pid = unlocked
    value = store.load(pid)
    mixed_layers(value)
    row = media_row("1", asset if asset != "text" else VIDEO, 4., 6., motion="pan", fade_in=.5, fade_out=.5)
    value["manual"]["media_clips"] = [row]
    action, selected = ("text_trim", value["manual"]["text_clips"][1]) if asset == "text" else ("media_trim", row)
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": action, "clip_id": selected["id"], "edge": "start", "time": selected["start"]})
    assert value == before


def test_text_extension_overlap_limit_and_invalid_inputs_are_atomic(unlocked):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["text_clips"] = [text_row("1", 2., 3.)] + [text_row("2", 4., 6., id=f"text_{i:032x}") for i in range(16)]
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    for edge, time, reason in [("end", 5., "16"), ("end", 2.01, "0.08"), ("side", 3., "edge"), (False, 3., "edge"), ("start", True, "finite"), ("start", -1., "between")]:
        response = post(unlocked, "text_trim", clip_id="text_" + "1" * 32, edge=edge, time=time)
        assert response.status_code == 400 and reason in response.get_json()["message"], response.get_json()
        assert store.state_path(pid).read_bytes() == before
    assert post(unlocked, "text_trim", clip_id="text_" + "1" * 32, edge="end", time=4.).status_code == 200


@pytest.mark.parametrize("speed", [.25, .5, 1.25, 4.])
def test_trim_picture_hold_remains_independent_of_normal_audio_clock(unlocked, speed):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["assets"][VIDEO]["duration"] = 3.
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 4., 5., source_start=1., video_source_start=8., speed=speed, fade_in=0., fade_out=0.)]
    store.update(pid, prepare)
    assert post(unlocked, "media_trim", clip_id="media_" + "1" * 32, edge="end", time=6.).status_code == 200
    assert post(unlocked, "media_trim", clip_id="media_" + "1" * 32, edge="start", time=4.5).status_code == 200
    row = store.load(pid)["manual"]["media_clips"][0]
    assert row["source_start"] == 1.5 and row["video_source_start"] == 8. + .5 * speed


def test_trim_revision_conflict_cannot_edit_a_changed_occurrence(unlocked):
    _, client, store, pid = unlocked
    store.update(pid, mixed_layers)
    previous_revision = store.load(pid)["revision"]
    store.update(pid, lambda value: value.update(name="Changed elsewhere"))
    before = store.state_path(pid).read_bytes()
    result = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "media_trim", "clip_id": "media_" + "2" * 32, "edge": "start", "time": 5., "expected_revision": previous_revision})
    assert result.status_code == 409 and store.state_path(pid).read_bytes() == before


def render_setup(library_api, media, speed):
    import shutil
    import threading
    from cutroom.jobs import Job, JobContext
    from cutroom.render import render_project
    from test_media_render import project as render_fixture
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
    return store, pid, settings, encoded, hashes, originals


def edit_roundtrip(api, action, **detail):
    app, _, store, pid = api
    before = content(store.load(pid))
    response = post(api, action, **detail)
    assert response.status_code == 200, response.get_json()
    after = content(store.load(pid))
    assert post(api, "undo").status_code == 200
    assert content(store.load(pid)) == before
    assert post(api, "redo").status_code == 200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid)) == after


@pytest.mark.parametrize("speed", [1., 2.])
def test_real_encoded_trims_preserve_retained_picture_audio_title_and_outer_fades(library_api, media, speed):
    from test_media_render import pixel, samples, tone_level
    import subprocess
    store, pid, settings, encoded, hashes, originals = render_setup(library_api, media, speed)
    baseline, baseline_record = encoded("trim-before")
    actions = [("media_trim", "media_" + digit * 32) for digit in "123"] + [("text_trim", "text_" + "1" * 32)]
    for action, clip_id in actions:
        edit_roundtrip(library_api, action, clip_id=clip_id, edge="start", time=1.)
    head, head_record = encoded("trim-head")
    for action, clip_id in actions:
        edit_roundtrip(library_api, action, clip_id=clip_id, edge="end", time=2.)
    both, record = encoded("trim-both")
    assert store.load(pid)["manual"]["history"]["undo_count"] == 8
    for entry in (baseline_record, head_record, record):
        assert entry["duration"] == pytest.approx(3., abs=1 / 30)
        assert entry["manual_text_count"] == 1
    ffmpeg = media[1]
    def white_text_pixels(path, time):
        rgb = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(time), "-i", str(path), "-an", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
        return sum(min(rgb[i:i + 3]) > 170 and max(rgb[i:i + 3]) - min(rgb[i:i + 3]) < 45 for i in range(0, len(rgb), 3))
    for at in (1.1, 1.3, 1.8):
        for x, y in ((30, 15), (120, 15), (80, 75)):
            old = pixel(ffmpeg, baseline, at, x, y)
            for out in (head, both):
                new = pixel(ffmpeg, out, at, x, y)
                assert max(abs(a - b) for a, b in zip(old, new)) < 24, (speed, at, old, new)
        assert white_text_pixels(both, at) > 10
    assert white_text_pixels(both, .8) == 0 and white_text_pixels(both, 2.2) == 0
    # The yellow still is removed only outside the chosen retained interval.
    for at in (.5, 2.5):
        old, new = pixel(ffmpeg, baseline, at, 120, 15), pixel(ffmpeg, both, at, 120, 15)
        assert old[0] > 150 and old[1] > 150 and old[2] < 50
        assert max(abs(a - b) for a, b in zip(old, new)) > 80
    old_audio, head_audio, new_audio = (samples(ffmpeg, path) for path in (baseline, head, both))
    for at in (1.1, 1.6, 1.8):
        for frequency in (440, 880):
            for audio in (head_audio, new_audio):
                assert tone_level(audio, at, frequency) == pytest.approx(tone_level(old_audio, at, frequency), abs=.008)
    # Head-only trim keeps the original music fade-out, not a rescaled envelope.
    assert tone_level(head_audio, 2.55, 880) == pytest.approx(tone_level(old_audio, 2.55, 880), abs=.008)
    assert tone_level(new_audio, 1.1, 440) > .2 and tone_level(new_audio, 1.1, 880) > .05
    assert tone_level(new_audio, .8, 880) < .003 and tone_level(new_audio, 2.2, 880) < .003
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes
    assert len(store.load(pid)["exports"]) == 3 and all(path.exists() for path in (baseline, head, both))


@pytest.mark.parametrize("speed", [.5, 2.])
def test_real_encoded_safe_extension_matches_the_full_reference(library_api, media, speed):
    from test_media_render import pixel, samples, tone_level
    store, pid, settings, encoded, hashes, originals = render_setup(library_api, media, speed)
    def narrow(value):
        for row in value["manual"]["media_clips"]:
            kind = value["assets"][row["asset_id"]]["kind"]
            row.update(start=1., end=2., fade_in=0., fade_out=0.)
            if kind != "image":
                row["source_start"] = 1.
                if kind == "video": row["video_source_start"] = 1.
        value["manual"]["text_clips"][0].update(start=1., end=2.)
    store.update(pid, narrow)
    def reference(value):
        for row in value["manual"]["media_clips"]:
            kind = value["assets"][row["asset_id"]]["kind"]
            row.update(start=.5, end=2.5)
            if kind != "image":
                row["source_start"] = .5
                if kind == "video": row["video_source_start"] = 1. - .5 * speed
        value["manual"]["text_clips"][0].update(start=.5, end=2.5)
    store.update(pid, reference)
    expected, _ = encoded("extension-reference")
    store.update(pid, narrow)
    for action, clip_id in [("media_trim", "media_" + digit * 32) for digit in "123"] + [("text_trim", "text_" + "1" * 32)]:
        for edge, at in (("start", .5), ("end", 2.5)):
            edit_roundtrip(library_api, action, clip_id=clip_id, edge=edge, time=at)
    output, record = encoded("extension-after")
    assert record["duration"] == pytest.approx(3., abs=1 / 30)
    old_audio, new_audio = samples(media[1], expected), samples(media[1], output)
    for at in (.6, .9, 1.3, 1.8, 2.3):
        for x, y in ((30, 15), (120, 15), (80, 75)):
            old, new = pixel(media[1], expected, at, x, y), pixel(media[1], output, at, x, y)
            assert max(abs(a - b) for a, b in zip(old, new)) < 24, (speed, at, old, new)
        for frequency in (440, 880):
            assert tone_level(new_audio, at, frequency) == pytest.approx(tone_level(old_audio, at, frequency), abs=.008)
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes
    assert len(store.load(pid)["exports"]) == 2 and expected.exists() and output.exists()
