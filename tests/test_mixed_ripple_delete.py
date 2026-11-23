"""Together time removal across supported independent layers, with one Undo."""
from __future__ import annotations
import copy
import hashlib
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.projects import ProjectStore
from cutroom.render import project_caption_items
from test_media_append import ASSET, append_project, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post
from test_media_render import media  # noqa: F401


def setup_layers(value):
    mixed_layers(value)
    value["manual"]["media_clips"].extend([
        media_row("6", VIDEO, 6., 9., speed=2., video_source_start=2.),
        media_row("7", VIDEO, 5.25, 6.75),
    ])
    value["manual"]["text_clips"][1]["end"] = 9.
    value["manual"]["text_clips"].extend([text_row("5", 6., 9.), text_row("6", 5.25, 6.75)])
    return value


def remove(api, start=5., end=7.):
    return post(api, "sequence_ripple_delete", start=start, end=end)


def test_together_removes_only_selected_time_from_every_layer_preserving_clocks_order_and_originals(unlocked):
    _, _, store, pid = unlocked
    store.update(pid, setup_layers)
    before = store.load(pid)
    originals = [p for p in (store.project_dir(pid) / "media").rglob("*") if p.is_file()]
    hashes = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    response = remove(unlocked)
    assert response.status_code == 200, response.get_json()
    after = store.load(pid)
    assert after["manual"]["sequence"]["duration"] == 13.
    media = after["manual"]["media_clips"]
    assert len(media) == 7 and len({row["id"] for row in media}) == 7
    old = before["manual"]["media_clips"]
    assert media[0] == old[0]
    assert media[1] == {**old[1], "end": 5., "fade_out": 0}
    assert media[2] == {**old[2], "end": 5., "fade_out": 0}
    assert media[3] == {**old[3], "end": 5., "fade_out": 0}
    assert media[4] == {**old[3], "id": media[4]["id"], "start": 5., "end": 6., "fade_in": 0}
    assert media[4]["id"] != old[3]["id"]
    assert media[5] == {**old[4], "start": 6., "end": 7.}
    assert media[6] == {**old[5], "start": 5., "end": 7., "source_start": 2., "video_source_start": 4., "fade_in": 0}
    assert old[6]["id"] not in {row["id"] for row in media}
    texts, old_text = after["manual"]["text_clips"], before["manual"]["text_clips"]
    assert len(texts) == 6 and len({row["id"] for row in texts}) == 6
    assert texts[0] == old_text[0]
    assert texts[1] == {**old_text[1], "end": 5.}
    assert texts[2] == {**old_text[1], "id": texts[2]["id"], "start": 5., "end": 7.}
    assert texts[3] == {**old_text[2], "end": 5.}
    assert texts[4] == {**old_text[3], "start": 6., "end": 7.}
    assert texts[5] == {**old_text[4], "start": 5., "end": 7.}
    assert after["manual"]["history"] == {"undo_count": 1, "redo_count": 0}
    assert project_caption_items(after, aligned=False) == project_caption_items(before, aligned=False)
    for key in ("sources", "assets", "analysis"):
        assert after[key] == before[key]
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes


def test_exact_shared_undo_redo_reopen_and_source_only_delete_are_preserved(unlocked):
    app, _, store, pid = unlocked
    store.update(pid, setup_layers)
    original = content(store.load(pid))
    assert remove(unlocked).status_code == 200
    deleted = content(store.load(pid))
    assert post(unlocked, "undo").status_code == 200
    assert content(store.load(pid)) == original
    assert post(unlocked, "redo").status_code == 200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid)) == deleted
    before = store.load(pid)
    response = post(unlocked, "sequence_remove_range", slot="A", start=3., end=4.)
    assert response.status_code == 200, response.get_json()
    value = store.load(pid)
    assert value["manual"]["media_clips"] == before["manual"]["media_clips"]
    assert value["manual"]["text_clips"] == before["manual"]["text_clips"]
    assert value["manual"]["source_tracks"]["B"] == before["manual"]["source_tracks"]["B"]
    assert value["manual"]["sequence"]["duration"] == 13.


@pytest.mark.parametrize("kind", ["media", "text"])
@pytest.mark.parametrize("side", ["left", "right"])
def test_tiny_retained_fragment_rejects_whole_edit_atomically(unlocked, kind, side):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        bounds = (4.921, 8.) if side == "left" else (4., 7.079)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, *bounds, fade_in=0., fade_out=0.)] if kind == "media" else []
        value["manual"]["text_clips"] = [text_row("1", *bounds)] if kind == "text" else []
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = remove(unlocked)
    assert response.status_code == 400 and "shorter" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


@pytest.mark.parametrize("change,reason", [({"motion": "pan"}, "pan/zoom"), ({"motion": "zoom_in"}, "pan/zoom"),
                                           ({"fade_in": 1.1}, "fade"), ({"fade_out": 1.1}, "fade")])
def test_partial_effect_phase_change_rejects_without_consuming_history(unlocked, change, reason):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 4., 8., **change)]
        value["manual"]["text_clips"] = []
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = remove(unlocked)
    assert response.status_code == 400 and reason in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


def test_whole_animated_occurrence_can_be_removed_without_deleting_its_asset(unlocked):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 5., 7., motion="pan", fade_in=1., fade_out=1.)]
        value["manual"]["text_clips"] = []
    store.update(pid, prepare)
    asset = copy.deepcopy(store.load(pid)["assets"])
    response = remove(unlocked)
    assert response.status_code == 200, response.get_json()
    value = store.load(pid)
    assert value["manual"]["media_clips"] == [] and value["assets"] == asset
    assert post(unlocked, "undo").status_code == 200
    assert store.load(pid)["manual"]["media_clips"][0]["motion"] == "pan"


@pytest.mark.parametrize("kind", ["audio_plan", "alternative", "dormant", "orphan", "retimed", "overlap", "locked"])
def test_protected_mixed_state_rejects_without_partial_layer_changes(unlocked, kind):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        if kind == "audio_plan": value["draft"]["audio_plan"] = [{"start": 0., "end": 10., "action": "normalize"}]
        if kind == "locked": value["manual"]["track_locks"] = {"A": True}
        if kind == "dormant": value["manual"]["caption_dormant_overrides"] = {"unknown": {"text": "mine"}}
        if kind == "orphan": value["manual"]["caption_overrides"]["unknown"] = {"text": "mine"}
        if kind == "retimed": next(iter(value["manual"]["caption_overrides"].values()))["start_delta"] = .1
        if kind == "overlap":
            caption = project_caption_items(value, aligned=False)[0]
            # The selection overlaps the real reviewed 1..2s caption below.
            assert caption["start"] == 1.
        if kind == "alternative":
            from cutroom.caption_alternatives import FORMAT, binding, register, geometry
            key = register(value, {"format": FORMAT, "binding": binding(value), "source_interval": [0., 20.],
                "transcript": {"segments": [{"id": "s", "start": 0., "end": 20., "text": "Alternate", "words": []}]}})
            value["manual"]["caption_alternative"] = {"id": key, "geometry": geometry(value)}
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = remove(unlocked, 1., 2.) if kind == "overlap" else remove(unlocked)
    assert response.status_code == 400, response.get_json()
    assert store.state_path(pid).read_bytes() == before


def test_empty_edit_with_all_layers_removed_is_reopenable_undoable_and_can_append_again(unlocked):
    app, _, store, pid = unlocked
    def prepare(value):
        setup_layers(value)
        value["manual"].pop("caption_overrides", None)
        value["manual"].pop("caption_override_anchors", None)
    store.update(pid, prepare)
    before = content(store.load(pid))
    response = remove(unlocked, 0., 15.)
    assert response.status_code == 200, response.get_json()
    empty = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    assert empty["manual"]["sequence"]["duration"] == 0
    assert empty["manual"]["source_tracks"] == {"A": [], "B": []}
    assert empty["manual"]["media_clips"] == empty["manual"]["text_clips"] == []
    assert empty["assets"] == before["assets"] and empty["sources"] == before["sources"]
    assert post(unlocked, "media_append", asset_id=ASSET).status_code == 200
    assert store.load(pid)["manual"]["sequence"]["duration"] == 4.
    assert post(unlocked, "undo").status_code == 200
    assert store.load(pid)["manual"]["sequence"]["duration"] == 0
    assert post(unlocked, "undo").status_code == 200
    assert content(store.load(pid)) == before


@pytest.mark.parametrize("speed", [.25, .5, 1.25, 4.])
def test_split_retains_distinct_picture_and_audio_clocks_even_in_picture_hold(unlocked, speed):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 4., 8., speed=speed, video_source_start=25.)]
        value["manual"]["text_clips"] = []
    store.update(pid, prepare)
    response = remove(unlocked)
    assert response.status_code == 200, response.get_json()
    left, right = store.load(pid)["manual"]["media_clips"]
    assert (left["start"], left["end"], right["start"], right["end"]) == (4., 5., 5., 6.)
    assert (left["source_start"], right["source_start"]) == (1., 4.)
    assert (left["video_source_start"], right["video_source_start"]) == (25., 25. + 3 * speed)
    assert right["id"] != left["id"] and right["speed"] == speed


def test_legacy_mixed_delete_materializes_lazily_and_restores_schema_on_undo():
    value = setup_layers(append_project())
    for key in ("sequence", "source_tracks", "caption_overrides", "caption_override_anchors", "track_locks"):
        value["manual"].pop(key, None)
    value["draft"]["audio_plan"] = []
    before = content(value)
    apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 5., "end": 7.})
    after = content(value)
    apply_manual_edit(value, {"action": "undo"})
    assert "sequence" not in value["manual"] and content(value) == before
    apply_manual_edit(value, {"action": "redo"})
    assert content(value) == after


@pytest.mark.parametrize("kind,count", [("media", 101), ("text", 1001)])
def test_split_capacity_is_checked_before_mutation_on_valid_existing_layer_counts(unlocked, kind, count):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = ([media_row("1", VIDEO, 4., 8., id=f"media_{i:032x}") for i in range(count)] if kind == "media" else [])
        value["manual"]["text_clips"] = ([text_row("1", 4., 8., id=f"text_{i:032x}") for i in range(count)] if kind == "text" else [])
    store.update(pid, prepare)
    before = store.state_path(pid).read_bytes()
    response = remove(unlocked)
    assert response.status_code == 400 and "clip limit" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes() == before


def test_exact_minimum_pieces_and_flat_fade_boundaries_are_not_needlessly_blocked(unlocked):
    _, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["media_clips"] = [media_row("1", VIDEO, 4.92, 7.08, fade_in=.08, fade_out=.08)]
        value["manual"]["text_clips"] = [text_row("1", 4.92, 7.08)]
    store.update(pid, prepare)
    response = remove(unlocked)
    assert response.status_code == 200, response.get_json()
    for key in ("media_clips", "text_clips"):
        assert [(r["start"], r["end"]) for r in store.load(pid)["manual"][key]] == [(4.92, 5.), (5., 5.08)]


@pytest.mark.parametrize("bounds", [(-1, 7), (7, 5), (5, 5), (5, 16)])
def test_bad_range_does_not_consume_history_or_partially_rewrite_layers(unlocked, bounds):
    _, _, store, pid = unlocked
    store.update(pid, setup_layers)
    before = store.state_path(pid).read_bytes()
    assert remove(unlocked, *bounds).status_code == 400
    assert store.state_path(pid).read_bytes() == before


def test_stale_revision_returns_conflict_without_replaying_or_partial_layer_change(unlocked):
    _, client, store, pid = unlocked
    store.update(pid, setup_layers)
    before = store.state_path(pid).read_bytes()
    response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "sequence_ripple_delete",
        "start": 5., "end": 7., "expected_revision": store.load(pid)["revision"] - 1})
    assert response.status_code == 409
    assert store.state_path(pid).read_bytes() == before


def test_automatic_captions_follow_only_retained_source_words_and_reopen(unlocked):
    app, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"].pop("caption_overrides", None)
        value["manual"].pop("caption_override_anchors", None)
        value["analysis"]["transcript"]["segments"] = [{"id": "across", "start": 4., "end": 8., "text": "Before removed after",
            "words": [{"word": "Before", "start": 4.1, "end": 4.8}, {"word": "removed", "start": 5.1, "end": 6.8},
                      {"word": "after", "start": 7.1, "end": 7.8}]}]
    store.update(pid, prepare)
    analysis = copy.deepcopy(store.load(pid)["analysis"])
    response = remove(unlocked)
    assert response.status_code == 200, response.get_json()
    value = ProjectStore(app.extensions["cutroom_settings"]).load(pid)
    items = project_caption_items(value, aligned=False)
    assert "removed" not in " ".join(r["text"] for r in items)
    assert "Before" in " ".join(r["text"] for r in items) and "after" in " ".join(r["text"] for r in items)
    assert min(r["start"] for r in items) >= 4.1 - 1e-9 and max(r["end"] for r in items) <= 5.8 + 1e-9
    assert value["analysis"] == analysis


def test_direct_call_protected_motion_does_not_materialize_or_modify_input():
    value = setup_layers(append_project())
    for key in ("sequence", "source_tracks", "caption_overrides", "caption_override_anchors", "track_locks"):
        value["manual"].pop(key, None)
    value["manual"]["media_clips"][3]["motion"] = "zoom_in"
    value["draft"]["audio_plan"] = []
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="pan/zoom"):
        apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 5., "end": 7.})
    assert value == before


@pytest.mark.parametrize("speed", [1., 2.])
def test_real_encoded_mixed_delete_preserves_retained_picture_audio_fades_and_titles(library_api, media, speed):
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
    response = client.post(f"/api/projects/{pid}/manual/edit", json={"action": "sequence_ripple_delete", "start": .75, "end": 1.25, "expected_revision": store.load(pid)["revision"]})
    assert response.status_code == 200, response.get_json()
    deleted = content(store.load(pid))
    # Shared Undo/Redo across a real render and a fresh store read.
    assert post(library_api, "undo").status_code == 200
    assert content(store.load(pid)) == before_content
    assert post(library_api, "redo").status_code == 200
    assert content(ProjectStore(settings).load(pid)) == deleted
    output, record = encoded("mixed-after")
    assert baseline_record["duration"] == pytest.approx(3., abs=1 / 30)
    assert record["duration"] == pytest.approx(2.5, abs=1 / 30)
    assert baseline_record["manual_text_count"] == 1 and record["manual_text_count"] == 1
    ffmpeg = media[1]
    # Retained image/text pixels and independent picture speed remain identical
    # across the collapsed half-second; no animation or source clock restarts.
    for old_time, new_time in ((.6, .6), (1.5, 1.), (1.8, 1.3), (2.3, 1.8)):
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
    assert white_text_pixels(output, 2.1) == 0
    old_audio, new_audio = samples(ffmpeg, baseline), samples(ffmpeg, output)
    for old_time, new_time in ((.3, .3), (.6, .6), (1.4, .9), (1.6, 1.1), (2.55, 2.05)):
        for frequency in (440, 880):
            assert tone_level(new_audio, new_time, frequency) == pytest.approx(tone_level(old_audio, old_time, frequency), abs=.008)
    assert tone_level(new_audio, 1.1, 440) > .2
    assert tone_level(new_audio, 1.1, 880) > .05
    assert tone_level(new_audio, 1.6, 440) < .003
    assert {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals} == hashes
    assert len(store.load(pid)["exports"]) == 2 and baseline.exists() and output.exists()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("edited_count", [1, 2])
def test_cutting_gap_cannot_merge_or_spread_reviewed_caption_edits(legacy, edited_count):
    from test_all_layer_gap_closure import project as gap_project
    value = gap_project()
    if legacy:
        value["manual"].pop("sequence")
        value["sources"]["A"]["duration"] = 12.
        value["draft"]["keep_ranges"] = [{"start": 0., "end": 12.}]
        value["draft"]["camera_plan"] = [{"start": 0., "end": 12., "camera": "A"}]
    value["manual"]["media_clips"][0].update(start=10., end=12.)
    value["analysis"]["transcript"]["segments"] = [{"id": "speech", "start": 0., "end": 4., "text": "Original whole sentence"}]
    items = project_caption_items(value, aligned=False)
    assert len(items) == 2
    for item, text in list(zip(items, ("Reviewed first half", "Reviewed last half")))[:edited_count]:
        apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"], "text": text})
    before = copy.deepcopy(value)
    with pytest.raises(ManualEditError, match="merge or change"):
        apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 4., "end": 8.})
    assert value == before


@pytest.mark.parametrize("legacy", [False, True])
def test_reviewed_caption_outside_range_translates_without_losing_style_or_ancestry(legacy):
    from test_all_layer_gap_closure import project as gap_project
    value = gap_project()
    if legacy:
        value["manual"].pop("sequence")
        value["sources"]["A"]["duration"] = 12.
        value["draft"]["keep_ranges"] = [{"start": 0., "end": 12.}]
        value["draft"]["camera_plan"] = [{"start": 0., "end": 12., "camera": "A"}]
    item = project_caption_items(value, aligned=False)[0]
    apply_manual_edit(value, {"action": "caption_update", "caption_id": item["id"], "text": "Reviewed outside", "scale": 110})
    before = copy.deepcopy(value)
    apply_manual_edit(value, {"action": "sequence_ripple_delete", "start": 0., "end": 2.})
    caption = project_caption_items(value, aligned=False)[0]
    assert (caption["start"], caption["end"], caption["text"], caption["scale"]) == (6.5, 7.5, "Reviewed outside", 110)
    assert caption["_caption_anchor"] == item["_caption_anchor"]
    assert not value["manual"].get("caption_dormant_overrides")
    apply_manual_edit(value, {"action": "undo"})
    assert value["manual"].get("sequence") == before["manual"].get("sequence")
    assert project_caption_items(value, aligned=False)[0]["text"] == "Reviewed outside"
