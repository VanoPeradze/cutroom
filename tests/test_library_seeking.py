"""Metadata/command/graph contracts for per-occurrence library video seeking.

No native decoder, media/model fixture, server or application is started here.
Runtime pixel/sample parity and the late-range latency reproduction belong to
the separately bounded qualification harness; these assertions cannot prove
either. Primary A/B inputs retain their existing source-clock behavior.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from cutroom import render
from cutroom.render_inventory import compile_render_inputs

VIDEO = "asset_" + "a" * 32
BACKGROUND = "asset_" + "b" * 32
AUDIO = "asset_" + "c" * 32
IMAGE = "asset_" + "d" * 32
FPS = 30


def project(*, source_b=False):
    value = {"sources": {"A": {"relative_path": "media/source-A.mp4", "duration": 4,
                               "width": 320, "height": 180, "fps": FPS, "has_audio": True}},
             "settings": {"fps": FPS, "editorial_effects": False},
             "assets": {VIDEO: {"id": VIDEO, "kind": "video", "status": "ready",
                                "duration": 3669.44, "width": 160, "height": 90,
                                "fps": 50, "has_audio": True, "generation": "library-generation",
                                "path": f"media/assets/{VIDEO}/original.mp4"}},
             "manual": {"media_clips": [
                 {"id": "occurrence-one", "asset_id": VIDEO, "start": 1, "end": 3,
                  "source_start": 1800.25, "video_source_start": 1800.25, "speed": 1,
                  "audio_enabled": True, "role": "voice", "muted": False}]},
             "draft": {"keep_ranges": [{"start": 0, "end": 4}],
                       "camera_plan": [{"start": 0, "end": 4, "camera": "A"}]}}
    if source_b:
        value["sources"]["B"] = {**value["sources"]["A"], "relative_path": "media/source-B.mp4"}
    return value


def path_placeholders(value, root):
    # Input-path admission only. These bytes must never be sent to a decoder.
    names = [row["relative_path"] for row in value["sources"].values()]
    names += [row["path"] for row in value["assets"].values()]
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"metadata-only input-path placeholder")


def input_options(arguments):
    chunks, start = [], 0
    for index, option in enumerate(arguments):
        if option == "-i":
            chunks.append(arguments[start:index + 2])
            start = index + 2
    assert start == len(arguments)
    return chunks


def assert_seek(options, expected):
    if expected == 0:
        assert "-ss" not in options
    else:
        assert options.count("-ss") == 1
        offset = options.index("-ss")
        assert offset < options.index("-i")
        assert float(options[offset + 1]) == expected


def graph_for(value, inventory):
    return render.build_filter_graph(value, 320, 180, None, inventory)[0]


def test_fractional_late_range_seeks_its_own_input_and_preserves_local_fades_and_edit_clock(tmp_path):
    value = project(source_b=True)
    clip = value["manual"]["media_clips"][0]
    clip.update(fade_in=.3, fade_out=.4)
    before = copy.deepcopy(value)
    inventory = compile_render_inputs(value)
    path_placeholders(value, tmp_path)
    options = input_options(inventory.input_args(tmp_path))
    assert [entry.seek_start for entry in inventory.inputs("source")] == [0, 0]
    assert_seek(options[0], 0)
    assert_seek(options[1], 0)
    entry = inventory.inputs("library")[0]
    assert entry.index == 2 and entry.seek_start == 1800
    assert_seek(options[entry.index], 1800)
    assert Path(options[entry.index][-1]).name == "original.mp4"
    graph = graph_for(value, inventory)
    assert "[2:v]trim=start=0.250000000:end=2.283333333" in graph
    assert "[2:a]atrim=start=0.250000000:end=2.250000000" in graph
    assert "afade=t=in:st=0:d=0.300000000" in graph
    assert "afade=t=out:st=1.600000000:d=0.400000000" in graph
    assert "adelay=48000S:all=1" in graph
    # Native near-EOF decoding exposed missing/negative PTS on adelay's real
    # silence buffers. Reclock by sample count before any following time trim;
    # doing so only at the end loses the padding and shifts speech earlier.
    delayed_audio = graph.split("adelay=48000S:all=1,", 1)[1].split("[libaudio0]", 1)[0]
    assert delayed_audio.startswith("asetpts=N/48000/TB,apad,atrim=")
    assert "trim=end_frame=60,setpts=N/30/TB" in graph
    assert value == before, "Seeking is transient command metadata, never a saved timeline rewrite"
    assert entry.clip["source_start"] == entry.clip["video_source_start"] == 1800.25


@pytest.mark.parametrize(("audio_start", "picture_start", "enabled", "has_audio", "muted", "seek"), [
    (1000.75, 1800.25, True, True, False, 1000),
    (0, 1800.25, True, True, False, 0),
    (1000.75, 1800.25, True, True, True, 1000),
    (0, 1800.25, False, True, False, 1800),
    (0, 1800.25, True, False, False, 1800),
    (.125, .375, True, True, False, 0),
])
def test_seek_uses_earliest_consumed_clock_without_speeding_speech(audio_start, picture_start, enabled, has_audio, muted, seek):
    value = project()
    clip = value["manual"]["media_clips"][0]
    clip.update(source_start=audio_start, video_source_start=picture_start, speed=2,
                audio_enabled=enabled, muted=muted)
    value["assets"][VIDEO]["has_audio"] = has_audio
    inventory = compile_render_inputs(value)
    entry = inventory.inputs("library")[0]
    assert entry.seek_start == seek
    graph = graph_for(value, inventory)
    picture_residual = picture_start - seek
    assert (f"[{entry.index}:v]trim=start={picture_residual:.9f}:end={picture_residual + 4 + 1 / FPS:.9f},"
            "setpts=(PTS-STARTPTS)/2.000000000") in graph
    if enabled and has_audio:
        audio_residual = audio_start - seek
        assert f"[{entry.index}:a]atrim=start={audio_residual:.9f}:end={audio_residual + 2:.9f},asetpts=PTS-STARTPTS" in graph
        assert "atempo=" not in graph, "Picture speed must not retime attached speech"
    else:
        assert f"[{entry.index}:a]" not in graph


def test_held_picture_is_clamped_before_floor_and_legacy_audio_tail_keeps_padding():
    value = project()
    clip = value["manual"]["media_clips"][0]
    # A renderer-only legacy/defensive case, not an assertion that the API
    # admits a newly created clip whose speech lies beyond the asset duration.
    clip.update(source_start=3670.25, video_source_start=4000, speed=2)
    inventory = compile_render_inputs(value)
    entry = inventory.inputs("library")[0]
    assert entry.seek_start == 3669
    graph = graph_for(value, inventory)
    picture_residual = 3669.44 - 1 / FPS - 3669
    assert f"[1:v]trim=start={picture_residual:.9f}:end={picture_residual + 4 + 1 / FPS:.9f}" in graph
    assert "tpad=stop_mode=clone:" in graph and "trim=end_frame=60" in graph
    assert "[1:a]atrim=start=1.250000000:end=3.250000000" in graph
    assert "apad,atrim=duration=2.000000000" in graph
    assert entry.clip["video_source_start"] == 4000 and entry.clip["source_start"] == 3670.25


def test_repeated_asset_occurrences_keep_independent_seek_positions_and_decoder_indexes(tmp_path):
    value = project(source_b=True)
    first = value["manual"]["media_clips"][0]
    first.update(start=0, end=1)
    second = {**first, "id": "occurrence-two", "start": 1, "end": 2,
              "source_start": 2400.75, "video_source_start": 2401.25}
    value["manual"]["media_clips"].append(second)
    inventory = compile_render_inputs(value)
    assert [(entry.index, entry.seek_start) for entry in inventory.inputs("library")] == [(2, 1800), (3, 2400)]
    path_placeholders(value, tmp_path)
    options = input_options(inventory.input_args(tmp_path))
    assert_seek(options[2], 1800)
    assert_seek(options[3], 2400)
    assert options[2][-1] == options[3][-1], "Repeated occurrences share source bytes, not decoder clocks"
    graph = graph_for(value, inventory)
    assert "[2:v]trim=start=0.250000000" in graph
    assert "[3:v]trim=start=1.250000000" in graph
    assert "[3:a]atrim=start=0.750000000:end=1.750000000" in graph
    assert graph.index("[libcomposite0]") < graph.index("[libcomposite1]")


def test_primary_inputs_audio_only_assets_and_looped_images_do_not_receive_video_seeking(tmp_path):
    value = project(source_b=True)
    value["assets"][AUDIO] = {"id": AUDIO, "kind": "audio", "status": "ready", "duration": 3000,
                              "has_audio": True, "path": f"media/assets/{AUDIO}/original.wav"}
    value["assets"][IMAGE] = {"id": IMAGE, "kind": "image", "status": "ready", "duration": 0,
                              "width": 80, "height": 40, "path": f"media/assets/{IMAGE}/original.png"}
    value["manual"]["media_clips"].extend([
        {"id": "audio", "asset_id": AUDIO, "start": 0, "end": 2, "source_start": 1800.25, "role": "music"},
        {"id": "image", "asset_id": IMAGE, "start": 0, "end": 2},
    ])
    inventory = compile_render_inputs(value)
    path_placeholders(value, tmp_path)
    options = input_options(inventory.input_args(tmp_path))
    for entry in inventory.entries:
        assert_seek(options[entry.index], entry.seek_start)
        if entry.category == "source" or entry.media.get("kind") in {"audio", "image"}:
            assert entry.seek_start == 0
    assert "-loop" in options[4] and "-framerate" in options[4]
    graph = graph_for(value, inventory)
    assert "[3:a]atrim=start=1800.250000000:end=1802.250000000" in graph


def test_keyed_video_and_shared_image_backgrounds_preserve_their_original_pts_clock(tmp_path):
    value = project(source_b=True)
    value["assets"][BACKGROUND] = {"id": BACKGROUND, "kind": "image", "status": "ready",
                                   "width": 80, "height": 40,
                                   "path": f"media/assets/{BACKGROUND}/background.png"}
    value["manual"]["chroma_key"] = {
        VIDEO: {"enabled": True, "background_asset_id": BACKGROUND},
        "A": {"enabled": True, "background_asset_id": BACKGROUND},
    }
    inventory = compile_render_inputs(value)
    path_placeholders(value, tmp_path)
    options = input_options(inventory.input_args(tmp_path))
    for entry in inventory.entries:
        assert entry.seek_start == 0
        assert_seek(options[entry.index], 0)
    assert len(inventory.inputs("chroma_background")) == 2
    for entry in inventory.inputs("chroma_background"):
        assert "-loop" in options[entry.index]
    graph = graph_for(value, inventory)
    assert "trim=start=1800.250000000:end=1802.283333333" in graph
    assert "[2:a]atrim=start=1800.250000000:end=1802.250000000" in graph


@pytest.mark.parametrize("bad_seek", [1801, -1, float("nan")])
def test_modified_seek_metadata_fails_inventory_integrity_before_paths_or_graph_are_used(tmp_path, bad_seek):
    value = project()
    inventory = compile_render_inputs(value)
    entries = list(inventory.entries)
    entries[1] = replace(entries[1], seek_start=bad_seek)
    damaged = replace(inventory, entries=tuple(entries))
    with pytest.raises(ValueError, match="no longer matches"):
        damaged.input_args(tmp_path)
    with pytest.raises(ValueError, match="no longer matches"):
        graph_for(value, damaged)


@pytest.mark.parametrize("change", ["fps", "audio_enabled", "picture_start", "asset_generation", "chroma"])
def test_stale_inventory_is_rejected_after_a_seek_relevant_input_changes(change):
    value = project()
    inventory = compile_render_inputs(value)
    if change == "fps":
        value["settings"]["fps"] = 60
    elif change == "audio_enabled":
        value["manual"]["media_clips"][0]["audio_enabled"] = False
    elif change == "picture_start":
        value["manual"]["media_clips"][0]["video_source_start"] = 1801.25
    elif change == "asset_generation":
        value["assets"][VIDEO]["generation"] = "replacement-generation"
    else:
        value["manual"]["chroma_key"] = {VIDEO: {"enabled": True}}
    with pytest.raises(ValueError, match="no longer matches"):
        graph_for(value, inventory)
