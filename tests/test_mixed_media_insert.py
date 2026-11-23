"""Atomic mixed-layer insert: retain every old media second and its source clock."""
from __future__ import annotations

import copy
import hashlib

import pytest

from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.render import project_caption_items
from test_media_append import ASSET, append_project, content, library_api  # noqa: F401
from test_media_insert import unlocked, insert  # noqa: F401
from test_media_render import media  # noqa: F401

VIDEO, AUDIO, IMAGE = ("asset_" + letter * 32 for letter in "def")


def media_row(identifier, asset, start, end, **extra):
    return {"id": "media_" + identifier * 32, "asset_id": asset, "start": start, "end": end,
            "source_start": 1., "speed": 1., "volume_db": -3., "muted": False, "role": "voice",
            "fade_in": .2, "fade_out": .3, "x": .1, "y": .1, "w": .5, "h": .5,
            "fit": "contain", "motion": "none", "audio_enabled": True, **extra}


def text_row(identifier, start, end, **extra):
    return {"id": "text_" + identifier * 32, "kind": "title", "start": start, "end": end,
            "text": "Original title שלום", "style": "boxed", "position": "bottom", "scale": 125,
            "template": "lower_third", "subtext": "Unchanged second line", **extra}


def mixed_layers(value):
    for asset_id, kind in ((VIDEO, "video"), (AUDIO, "audio"), (IMAGE, "image")):
        value["assets"][asset_id] = {**value["assets"][ASSET], "id": asset_id, "kind": kind,
                                     "duration": 20., "has_audio": kind != "image"}
    value["manual"]["media_clips"] = [
        media_row("1", VIDEO, 0., 1., fade_in=.1, fade_out=.1),
        media_row("2", VIDEO, 4., 6., speed=1.5, video_source_start=2.25),
        media_row("3", AUDIO, 3., 7., role="music", source_start=2., volume_db=-6.),
        media_row("4", IMAGE, 2., 8., audio_enabled=False, source_start=0., fade_in=0., fade_out=0.),
        media_row("5", VIDEO, 8., 9., fade_in=.1, fade_out=.1),
    ]
    value["manual"]["text_clips"] = [text_row("1", 0., 1.), text_row("2", 4., 7.),
                                          text_row("3", 4.5, 5.5, kind="caption"), text_row("4", 8., 9.)]
    return value


def post(api, action, **fields):
    _, client, store, pid = api
    return client.post(f"/api/projects/{pid}/manual/edit", json={
        "action": action, "expected_revision": store.load(pid)["revision"], **fields})


def test_one_insert_splits_every_crossing_layer_and_preserves_order_clocks_fades_and_originals(unlocked):
    _, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    before = store.load(pid)
    captions = project_caption_items(before, aligned=False)
    media_paths = [p for p in (store.project_dir(pid) / "media").rglob("*") if p.is_file()]
    original_hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in media_paths}
    response = insert(unlocked)
    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    assert after["manual"]["sequence"]["duration"] == 16.25
    rows = after["manual"]["media_clips"]
    assert len(rows) == 9  # Five existing + three split rights + inserted video.
    assert len({row["id"] for row in rows}) == 9
    assert rows[0] == before["manual"]["media_clips"][0]
    assert rows[-2] == {**before["manual"]["media_clips"][-1], "start": 9.25, "end": 10.25}
    cursor = 1
    for old in before["manual"]["media_clips"][1:4]:
        left, right = rows[cursor:cursor + 2]
        cursor += 2
        assert left["id"] == old["id"] and right["id"] != old["id"]
        assert (left["start"], left["end"], right["start"], right["end"]) == (old["start"], 5., 6.25, old["end"] + 1.25)
        assert (left["end"] - left["start"] + right["end"] - right["start"]) == old["end"] - old["start"]
        assert left["source_start"] == old["source_start"]
        kind = before["assets"][old["asset_id"]]["kind"]
        consumed = 5. - old["start"]
        assert right["source_start"] == old["source_start"] + (0 if kind == "image" else consumed)
        if kind == "video":
            assert right["video_source_start"] == old["video_source_start"] + consumed * old["speed"]
        assert (left["fade_in"], left["fade_out"], right["fade_in"], right["fade_out"]) == (old["fade_in"], 0, 0, old["fade_out"])
        for key in ("asset_id", "speed", "volume_db", "muted", "role", "audio_enabled", "x", "y", "w", "h", "fit", "motion"):
            assert left[key] == right[key] == old[key]
    assert (rows[-1]["asset_id"], rows[-1]["start"], rows[-1]["end"], rows[-1]["source_start"]) == (ASSET, 5., 6.25, .25)
    texts = after["manual"]["text_clips"]
    assert len(texts) == 6 and len({r["id"] for r in texts}) == 6
    assert texts[0] == before["manual"]["text_clips"][0]
    for old, left, right in [(before["manual"]["text_clips"][1], texts[1], texts[2]),
                             (before["manual"]["text_clips"][2], texts[3], texts[4])]:
        assert left == {**old, "end": 5.}
        assert right == {**old, "id": right["id"], "start": 6.25, "end": old["end"] + 1.25}
    assert texts[-1] == {**before["manual"]["text_clips"][-1], "start": 9.25, "end": 10.25}
    assert project_caption_items(after, aligned=False) == captions
    for key in ("sources", "assets", "analysis"):
        assert after[key] == before[key]
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in media_paths} == original_hashes
    assert after["manual"]["history"] == {"undo_count": 1, "redo_count": 0}


def test_mixed_insert_repeated_undo_redo_and_saved_reopen_are_exact(unlocked):
    app, _, store, pid = unlocked
    store.update(pid, mixed_layers)
    states = [content(store.load(pid))]
    for at in (5., 7.25):
        response = insert(unlocked, start=at)
        assert response.status_code == 200, response.get_json()
        states.append(content(store.load(pid)))
    for expected in (states[1], states[0]):
        assert post(unlocked, "undo").status_code == 200
        assert content(store.load(pid)) == expected
    for expected in states[1:]:
        assert post(unlocked, "redo").status_code == 200
        assert content(store.load(pid)) == expected
    reopened = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert reopened == store.load(pid) and content(reopened) == states[-1]
    assert reopened["manual"]["history"] == {"undo_count": 2, "redo_count": 0}


@pytest.mark.parametrize("at", [0., 4., 6., 15.])
def test_boundary_insert_never_splits_or_restarts_crossing_effects(unlocked, at):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("2", VIDEO, 4., 6., motion="pan", fade_in=1., fade_out=1.)]
        value["manual"]["text_clips"] = [text_row("2", 4., 6.)]
    store.update(pid, prepare)
    before = store.load(pid)
    result = insert(unlocked, start=at)
    assert result.status_code == 200, result.get_json()
    after = store.load(pid)
    offset = 1.25 if at <= 4 else 0
    for key in ("media_clips", "text_clips"):
        old = before["manual"][key][0]
        assert after["manual"][key][0] == {**old, "start": old["start"] + offset, "end": old["end"] + offset}


@pytest.mark.parametrize("change,reason", [
    ({"motion": "pan"}, "animated"), ({"motion": "zoom_in"}, "animated"),
    ({"fade_in": 1.1}, "fade"), ({"fade_out": 1.1}, "fade"),
    ({"start": 4.921}, "shorter"), ({"end": 5.079}, "shorter"),
])
def test_unsupported_media_split_is_atomic_and_never_consumes_history(unlocked, change, reason):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("2", VIDEO, 4., 6., **change)] if not set(change) & {"start", "end"} else [{**media_row("2", VIDEO, 4., 6., fade_in=0., fade_out=0.), **change}]
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    result = insert(unlocked)
    assert result.status_code == 400, result.get_json()
    assert reason in result.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("kind", ["text", "caption"])
@pytest.mark.parametrize("start,end", [(4.921, 6.), (4., 5.079)])
def test_short_custom_text_or_caption_piece_rejects_without_truncating(unlocked, kind, start, end):
    _, _, store, pid = unlocked
    store.update(pid, lambda p: p["manual"].update(text_clips=[text_row("2", start, end, kind="title" if kind == "text" else "caption")]))
    before = store.state_path(pid).read_bytes()
    response = insert(unlocked)
    assert response.status_code == 400 and "shorter" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("key,maximum,prefix", [("media_clips", 199, "media_"), ("text_clips", 2000, "text_")])
def test_all_generated_split_pieces_count_toward_existing_limits(unlocked, key, maximum, prefix):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        if key == "media_clips":
            value["manual"][key] = [{**media_row("a", VIDEO, 4., 6.), "id": prefix + f"{i:032x}"} for i in range(maximum)]
        else:
            # A valid pre-edit text layout: at most 15 short concurrent items,
            # plus one crossing title. Only that title needs an extra piece.
            value["manual"][key] = [{**text_row("a", round((i // 15) * .1, 6), round((i // 15) * .1 + .08, 6)),
                "id": prefix + f"{i:032x}"} for i in range(maximum - 1)] + [text_row("f", 4., 6.)]
            from cutroom.text_clips import validated_text_clips
            assert len(validated_text_clips(value)) == maximum
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = insert(unlocked)
    assert response.status_code == 400 and "clip limit" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


def test_minimum_pieces_and_exact_fade_boundaries_preserve_original_envelope(unlocked):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("2", VIDEO, 4.92, 5.08, fade_in=.08, fade_out=.08)]
        value["manual"]["text_clips"] = [text_row("2", 4.92, 5.08)]
    store.update(pid, prepare)
    response = insert(unlocked)
    assert response.status_code == 200, response.get_json()
    value = store.load(pid)
    left, right = value["manual"]["media_clips"][:2]
    assert left["fade_in"] == right["fade_out"] == .08
    assert left["fade_out"] == right["fade_in"] == 0
    assert (left["start"], left["end"], right["start"], right["end"]) == (4.92, 5., 6.25, 6.33)


def test_legacy_manual_project_materializes_lazily_and_undo_restores_original_schema():
    value = mixed_layers(append_project())
    for key in ("sequence", "source_tracks", "caption_overrides", "caption_override_anchors", "track_locks"):
        value["manual"].pop(key, None)
    value["draft"]["audio_plan"] = []
    before = content(value)
    apply_manual_edit(value, {"action": "media_insert", "asset_id": ASSET, "source_start": .25, "source_end": 1.5, "start": 5.})
    after = content(value)
    assert value["manual"]["sequence"]["duration"] == 16.25
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"] and content(value) == before
    apply_manual_edit(value, {"action": "redo"})
    assert content(value) == after


def test_stale_request_with_mixed_layers_does_not_split_anything(unlocked):
    _, client, store, pid = unlocked
    store.update(pid, mixed_layers)
    stale = store.load(pid)["revision"]
    store.patch(pid, {"name": "Newer edit"})
    before = store.state_path(pid).read_bytes()
    response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "media_insert", "asset_id": ASSET, "start": 5., "expected_revision": stale})
    assert response.status_code == 409 and response.get_json()["error"] == "revision_conflict"
    assert store.state_path(pid).read_bytes() == before


def test_direct_protected_edit_rejection_preserves_caller_object():
    value = mixed_layers(append_project())
    value["manual"]["track_locks"] = {}
    value["draft"]["audio_plan"] = []
    value["manual"]["media_clips"][1]["motion"] = "pan"
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="animated"):
        apply_manual_edit(value, {"action": "media_insert", "asset_id": ASSET, "start": 5.})
    assert value == before


@pytest.mark.parametrize("speed", [1., 2.])
def test_real_encoded_mixed_insert_keeps_picture_audio_fades_and_text_out_of_inserted_time(library_api, media, speed):
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
    response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "media_insert", "asset_id": ASSET,
        "source_start": 2., "source_end": 3., "start": 1.5, "expected_revision": store.load(pid)["revision"]})
    assert response.status_code == 200, response.get_json()
    inserted = content(store.load(pid))
    # Shared Undo/Redo across a real render and a fresh store read.
    assert post(library_api, "undo").status_code == 200
    assert content(store.load(pid)) == before_content
    assert post(library_api, "redo").status_code == 200
    assert content(ProjectStore(settings).load(pid)) == inserted
    output, record = encoded("mixed-after")
    assert baseline_record["duration"] == pytest.approx(3., abs=1 / 30)
    assert record["duration"] == pytest.approx(4., abs=1 / 30)
    assert baseline_record["manual_text_count"] == 1 and record["manual_text_count"] == 2
    ffmpeg = media[1]
    # Static layer stack survives, but every crossing layer leaves the inserted
    # one-second shot empty. At the right half the picture resumes, never resets.
    for old_time, new_time in ((.9, .9), (1.3, 1.3), (1.8, 2.8), (2.3, 3.3)):
        for x, y in ((30, 15), (120, 15), (80, 75)):
            old_rgb, new_rgb = pixel(ffmpeg, baseline, old_time, x, y), pixel(ffmpeg, output, new_time, x, y)
            assert max(abs(a - b) for a, b in zip(old_rgb, new_rgb)) < 24, (speed, old_time, new_time, x, y, old_rgb, new_rgb)
    for x, y in ((30, 15), (120, 15), (80, 75)):
        color = pixel(ffmpeg, output, 1.9, x, y)
        assert color[2] > 200 and color[0] < 30 and color[1] < 30, color
    import subprocess
    def white_text_pixels(path, time):
        rgb = subprocess.check_output([ffmpeg, "-v", "error", "-ss", str(time), "-i", str(path),
                                       "-an", "-frames:v", "1", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
        return sum(min(rgb[i:i + 3]) > 170 and max(rgb[i:i + 3]) - min(rgb[i:i + 3]) < 45
                   for i in range(0, len(rgb), 3))
    assert white_text_pixels(baseline, 1.1) > 10
    assert white_text_pixels(output, 2.7) > 10
    assert white_text_pixels(output, 1.9) == 0
    old_audio, new_audio = samples(ffmpeg, baseline), samples(ffmpeg, output)
    for old_time, new_time in ((.3, .3), (1.1, 1.1), (1.6, 2.6), (2.55, 3.55)):
        for frequency in (440, 880):
            assert tone_level(new_audio, new_time, frequency) == pytest.approx(tone_level(old_audio, old_time, frequency), abs=.008)
    for frequency in (440, 880):
        assert tone_level(new_audio, 1.8, frequency) < .003
    assert tone_level(new_audio, 2.6, 440) > .2
    assert tone_level(new_audio, 2.6, 880) > .05
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes
    assert len(store.load(pid)["exports"]) == 2 and baseline.exists() and output.exists()


@pytest.mark.parametrize("speed", [.25, .5, 1.25, 4.])
def test_picture_hold_and_attached_speech_keep_independent_clocks_after_mixed_split(unlocked, speed):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["assets"][VIDEO]["duration"] = 3.
        value["manual"]["media_clips"] = [media_row("2", VIDEO, 4., 6., source_start=1., speed=speed,
                                                     video_source_start=8., fade_in=0., fade_out=0.)]
    store.update(pid, prepare)
    response = insert(unlocked)
    assert response.status_code == 200, response.get_json()
    left, right = store.load(pid)["manual"]["media_clips"][:2]
    assert (left["source_start"], right["source_start"]) == (1., 2.)
    assert (left["video_source_start"], right["video_source_start"]) == (8., 8. + speed)
    assert right["audio_enabled"] is True and right["speed"] == speed


@pytest.mark.parametrize("edited", [False, True])
def test_crossing_automatic_caption_follows_source_words_unless_manually_edited(unlocked, edited):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"].pop("caption_overrides", None)
        value["manual"].pop("caption_override_anchors", None)
        value["analysis"]["transcript"]["segments"] = [{"id": "across", "start": 4., "end": 6., "text": "Before after",
            "words": [{"word": "Before", "start": 4.1, "end": 4.8}, {"word": "after", "start": 5.1, "end": 5.8}]}]
        if edited:
            caption = project_caption_items(value, aligned=False)[0]
            value["manual"]["caption_overrides"] = {caption["id"]: {"text": "Reviewed manual wording"}}
            value["manual"]["caption_override_anchors"] = {caption["id"]: copy.deepcopy(caption["_caption_anchor"])}
    store.update(pid, prepare)
    before_bytes = store.state_path(pid).read_bytes()
    analysis = copy.deepcopy(store.load(pid)["analysis"])
    response = insert(unlocked)
    if edited:
        assert response.status_code == 400 and "manually edited caption" in response.get_json()["message"]
        assert store.state_path(pid).read_bytes() == before_bytes
    else:
        assert response.status_code == 200, response.get_json()
        value = store.load(pid)
        items = project_caption_items(value, aligned=False)
        assert [(item["start"], item["end"], item["text"]) for item in items] == [(4.1, 4.8, "Before"), (6.35, 7.05, "after")]
        assert value["analysis"] == analysis

def test_chapter_fades_are_atomic_across_whole_edit_insert_and_cut_out(unlocked):
    """The normal edit API must not restart a retained title's built-in envelope."""
    _, _, store, pid = unlocked
    def seed(value):
        value["manual"]["media_clips"] = []
        value["manual"]["text_clips"] = [text_row("a", 3., 5., template="chapter")]
    store.update(pid, seed)
    source = {"slot":"A", "source_start":0., "source_end":.5}
    library = {"asset_id":ASSET, "source_start":0., "source_end":.5}
    requests = [("sequence_insert_all", dict(start=4., **source)),
                ("media_insert", dict(start=4., **library)),
                ("sequence_ripple_delete", {"start":3.75,"end":4.25}),
                ("sequence_ripple_delete", {"start":2.5,"end":4.}),
                ("sequence_ripple_delete", {"start":4.,"end":5.5})]
    for enabled in (True, False):
        store.update(pid, lambda value: value["manual"]["text_clips"][0].update(enabled=enabled))
        path = store.project_dir(pid) / "project.json"
        before, raw = copy.deepcopy(store.load(pid)), path.read_bytes()
        for action, details in requests:
            result = post(unlocked, action, **details)
            message = str(result.get_json()).lower()
            assert result.status_code == 400 and "chapter" in message and "fade" in message, message
            assert store.load(pid) == before and path.read_bytes() == raw


def test_whole_chapter_may_move_or_be_removed_without_partial_fade_or_extra_undo(unlocked):
    _, _, store, pid = unlocked
    def seed(value):
        value["manual"]["media_clips"] = []
        value["manual"]["text_clips"] = [text_row("a", 3., 5., template="chapter")]
    store.update(pid, seed)
    old = copy.deepcopy(store.load(pid)["manual"]["text_clips"][0])
    for action, details, shift in [
        ("sequence_insert_all", {"slot":"A","start":3.,"source_start":0.,"source_end":.5}, .5),
        ("media_insert", {"asset_id":ASSET,"start":5.,"source_start":0.,"source_end":.5}, 0.),
        ("sequence_ripple_delete", {"start":2.5,"end":3.}, -.5),
        ("sequence_ripple_delete", {"start":5.,"end":5.5}, 0.),
        ("sequence_ripple_delete", {"start":3.,"end":5.}, None),
        ("sequence_ripple_delete", {"start":2.75,"end":5.25}, None),
    ]:
        response = post(unlocked, action, **details)
        assert response.status_code == 200, response.get_json()
        expected = [] if shift is None else [{**old,"start":old["start"]+shift,"end":old["end"]+shift}]
        assert response.get_json()["project"]["manual"]["text_clips"] == expected
        assert post(unlocked, "undo").get_json()["project"]["manual"]["text_clips"] == [old]
        assert post(unlocked, "redo").get_json()["project"]["manual"]["text_clips"] == expected
        assert post(unlocked, "undo").get_json()["project"]["manual"]["text_clips"] == [old]
