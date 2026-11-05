from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import render
from cutroom.media_render import library_input_args
from cutroom.render_inventory import compile_render_inputs


BACKGROUND = "asset_" + "a" * 32
VIDEO = "asset_" + "b" * 32


def project(*, source_b=False):
    value = {"sources": {"A": {"relative_path": "media/A.mp4", "duration": 3,
                              "width": 320, "height": 180, "fps": 30, "has_audio": True}},
             "settings": {"fps": 30, "editorial_effects": False}, "manual": {}, "assets": {},
             "draft": {"keep_ranges": [{"start": 0, "end": 3}],
                       "camera_plan": [{"start": 0, "end": 3, "camera": "A"}]}}
    if source_b:
        value["sources"]["B"] = dict(value["sources"]["A"], relative_path="media/B.mp4")
    return value


def with_library(value):
    value["assets"][VIDEO] = {"id": VIDEO, "kind": "video", "status": "ready", "duration": 8,
                              "width": 160, "height": 90, "fps": 60, "has_audio": True,
                              "path": f"media/assets/{VIDEO}/original.mp4"}
    value["manual"]["media_clips"] = [
        {"id": "one", "asset_id": VIDEO, "start": 0, "end": 1, "source_start": 2,
         "video_source_start": 3, "speed": 2, "audio_enabled": True, "role": "voice"},
        {"id": "two", "asset_id": VIDEO, "start": 1, "end": 2, "source_start": 4,
         "audio_enabled": True, "role": "effects"},
    ]
    return value


def with_background(value):
    value["assets"][BACKGROUND] = {"id": BACKGROUND, "kind": "image", "status": "ready",
                                   "width": 80, "height": 40,
                                   "path": f"media/assets/{BACKGROUND}/background.png"}
    value["manual"]["chroma_key"] = {"A": {"enabled": True, "background_asset_id": BACKGROUND}}
    return value


def make_input_files(value, root):
    paths = [source["relative_path"] for source in value["sources"].values()]
    paths += [asset["path"] for asset in value["assets"].values()]
    for name in paths:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"path validation only; no decoder is invoked")


def paths(args):
    return [Path(args[index + 1]).name for index, arg in enumerate(args) if arg == "-i"]


def test_compile_is_metadata_only_and_detached(tmp_path):
    value = with_library(project(source_b=True))
    before = copy.deepcopy(value)
    inventory = compile_render_inputs(value)
    assert value == before and list(tmp_path.iterdir()) == []
    assert [entry.index for entry in inventory.entries] == [0, 1, 2, 3]
    assert [entry.key for entry in inventory.entries] == ["source:A", "source:B", "library:0", "library:1"]
    assert inventory.inputs("library")[0].clip == value["manual"]["media_clips"][0]
    value["manual"]["media_clips"][0]["source_start"] = 7
    assert inventory.inputs("library")[0].clip["source_start"] == 2
    with pytest.raises(ValueError, match="no longer matches"):
        inventory.validate(value)


def test_repeated_occurrences_keep_independent_picture_speech_clocks_and_array_order():
    value = with_library(project(source_b=True))
    inventory = compile_render_inputs(value)
    graph, _, _ = render.build_filter_graph(value, 320, 180, None, inventory)
    # Decoded clocks start at the independent input seeks; logical source
    # positions remain unchanged in the detached occurrence metadata.
    assert [entry.seek_start for entry in inventory.inputs("library")] == [2, 4]
    assert "[2:v]trim=start=1.000000000:end=3.033333333" in graph
    assert "[2:a]atrim=start=0.000000000:end=1.000000000" in graph
    assert "[3:a]atrim=start=0.000000000:end=1.000000000" in graph
    assert inventory.inputs("library")[0].clip["video_source_start"] == 3
    assert inventory.inputs("library")[0].clip["source_start"] == 2
    assert inventory.inputs("library")[1].clip["source_start"] == 4
    assert graph.index("[libcomposite0]") < graph.index("[libcomposite1]")
    assert inventory.inputs("library")[0].media is not inventory.inputs("library")[1].media


def test_skipped_subframe_occurrence_still_reserves_its_decoder_index(tmp_path):
    value = with_library(project())
    value["manual"]["media_clips"][0]["end"] = .001
    make_input_files(value, tmp_path)
    inventory = compile_render_inputs(value)
    assert paths(inventory.input_args(tmp_path)) == ["A.mp4", "original.mp4", "original.mp4"]
    graph, _, _ = render.build_filter_graph(value, 320, 180, None, inventory)
    assert "[1:v]" not in graph and "[2:v]" in graph


def test_unused_b_is_omitted_only_without_suffix_inputs(tmp_path):
    value = project(source_b=True)
    make_input_files(value, tmp_path)
    inventory = compile_render_inputs(value)
    graph, _, _ = render.build_filter_graph(value, 320, 180, None, inventory)
    assert not inventory.needs_source_b(graph)
    assert paths(inventory.input_args(tmp_path, include_source_b=False)) == ["A.mp4"]
    with_library(value)
    make_input_files(value, tmp_path)
    inventory = compile_render_inputs(value)
    graph, _, _ = render.build_filter_graph(value, 320, 180, None, inventory)
    assert inventory.needs_source_b(graph)
    assert paths(inventory.input_args(tmp_path)) == ["A.mp4", "B.mp4", "original.mp4", "original.mp4"]
    with pytest.raises(ValueError, match="slot is required"):
        inventory.input_args(tmp_path, include_source_b=False)


def test_background_order_and_loop_lengths_remain_target_native_not_occurrence_time(tmp_path):
    value = with_background(with_library(project(source_b=True)))
    value["sources"]["A"]["video_duration"] = 2
    value["manual"]["chroma_key"]["B"] = {"enabled": True, "background_asset_id": BACKGROUND}
    value["manual"]["chroma_key"][VIDEO] = {"enabled": True, "background_asset_id": BACKGROUND}
    make_input_files(value, tmp_path)
    inventory = compile_render_inputs(value)
    assert inventory.background_labels() == {"A": "[4:v]", "B": "[5:v]", VIDEO: "[6:v]"}
    assert [entry.loop_duration for entry in inventory.inputs("chroma_background")] == pytest.approx(
        [2 + 2 / 30, 3 + 2 / 30, 8 + 2 / 30])
    args = inventory.input_args(tmp_path)
    assert paths(args) == ["A.mp4", "B.mp4", "original.mp4", "original.mp4",
                           "background.png", "background.png", "background.png"]
    assert render.chroma_background_input_args(value, tmp_path, inventory) == inventory.input_args(
        tmp_path, category="chroma_background")


def test_library_image_duration_retains_occurrence_length_and_native_fps(tmp_path):
    value = with_background(project())
    value["manual"]["media_clips"] = [{"asset_id": BACKGROUND, "start": .5, "end": 1.5}]
    make_input_files(value, tmp_path)
    inventory = compile_render_inputs(value)
    assert inventory.inputs("library")[0].loop_duration == pytest.approx(1 + 2 / 30)
    assert library_input_args(value, tmp_path) == library_input_args(value, tmp_path, inventory)


def test_demand_counts_used_streams_and_fanout_without_inventing_missing_metadata():
    value = with_library(project(source_b=True))
    inventory = compile_render_inputs(value)
    graph, _, _ = render.build_filter_graph(value, 320, 180, None, inventory)
    report = inventory.demand(graph)
    assert report["input_count"] == 4 and report["library_occurrences"] == 2
    assert report["video_streams"] == 3 and report["audio_streams"] == 3
    assert report["known_video_pixels_per_second"] == 320 * 180 * 30 + 2 * 160 * 90 * 60
    assert report["video_streams_with_unknown_rate_or_dimensions"] == 0
    value["sources"]["A"].pop("fps")
    unknown = compile_render_inputs(value).demand(graph)
    assert unknown["video_streams_with_unknown_rate_or_dimensions"] == 1
    assert unknown["known_video_pixels_per_second"] == 2 * 160 * 90 * 60
    branches = inventory.demand("[0:v]split=4[x][y][z][w];\n[0:a]asplit=3[a][b][c]")
    assert branches["video_split_outputs"] == 4 and branches["audio_split_outputs"] == 3


@pytest.mark.parametrize("mutation", ["clip", "entry_order", "fps", "unknown_graph_input"])
def test_inventory_corruption_or_unavailable_input_fails_closed(mutation):
    value = with_library(project())
    inventory = compile_render_inputs(value)
    if mutation == "unknown_graph_input":
        with pytest.raises(ValueError, match="unavailable input"):
            inventory.demand("[9:v]null[out]")
        return
    if mutation == "clip":
        inventory.inputs("library")[0].clip["source_start"] = 99
    elif mutation == "entry_order":
        inventory = replace(inventory, entries=tuple(reversed(inventory.entries)))
    else:
        inventory = replace(inventory, fps=60)
    with pytest.raises(ValueError, match="no longer matches"):
        render.build_filter_graph(value, 320, 180, None, inventory)


@pytest.mark.parametrize("omitted", ["library", "chroma"])
def test_full_graph_rejects_helper_inventory_that_omits_user_media(omitted):
    value = with_background(with_library(project()))
    inventory = compile_render_inputs(value, **{f"include_{omitted}": False})
    with pytest.raises(ValueError, match="no longer matches"):
        render.build_filter_graph(value, 320, 180, None, inventory)


@pytest.mark.parametrize("broken", ["missing", "preparing", "too_many"])
def test_existing_asset_and_occurrence_limits_still_apply(broken):
    value = with_library(project())
    if broken == "missing":
        value["assets"].clear()
    elif broken == "preparing":
        value["assets"][VIDEO]["status"] = "preparing"
    else:
        value["manual"]["media_clips"] *= 101
    with pytest.raises(ValueError):
        compile_render_inputs(value)


def test_library_legacy_path_and_chroma_restricted_path_remain_distinct(tmp_path):
    value = with_library(project())
    value["assets"][VIDEO]["path"] = "legacy.mp4"
    (tmp_path / "legacy.mp4").write_bytes(b"not decoded")
    assert paths(library_input_args(value, tmp_path)) == ["legacy.mp4", "legacy.mp4"]
    value["assets"][VIDEO]["path"] = "../outside.mp4"
    with pytest.raises(ValueError, match="belong"):
        library_input_args(value, tmp_path)
    value = with_background(project())
    value["assets"][BACKGROUND]["path"] = "legacy.png"
    with pytest.raises((ValueError, FileNotFoundError)):
        render.chroma_background_input_args(value, tmp_path)


def test_export_compiles_once_and_uses_same_inventory_for_graph_and_command(tmp_path, monkeypatch):
    value = with_background(with_library(project(source_b=True)))
    value.update(id="project_inventory", name="inventory", exports=[])
    make_input_files(value, tmp_path)
    exports = tmp_path / "exports"
    exports.mkdir()
    store = SimpleNamespace(load=lambda _id: copy.deepcopy(value), project_dir=lambda _id: tmp_path)
    settings = SimpleNamespace(ffmpeg="not executed", exports_dir=exports, raw={"ffmpeg_threads": 1}, render={})
    context = SimpleNamespace(check_cancelled=lambda: None, update=lambda *_: None)
    capabilities = SimpleNamespace(executable="not executed", cfr_args=[], graph_file_args=lambda p: ["-filter_complex_script", str(p)])
    monkeypatch.setattr(render, "ensure_render_storage", lambda *_: None)
    monkeypatch.setattr(render, "chroma_key_capability", lambda *_: {"available": True})
    monkeypatch.setattr(render, "export_capabilities", lambda *_: capabilities)
    monkeypatch.setattr(render, "choose_encoder", lambda *_: ("libx264", []))
    observed = []
    compile_inputs = render.compile_render_inputs
    build_graph = render.build_filter_graph

    def compile_once(project):
        inventory = compile_inputs(project)
        observed.append(inventory)
        return inventory

    def graph_with_shared(project, width, height, captions, inventory):
        assert inventory is observed[0]
        return build_graph(project, width, height, captions, inventory)

    def capture(_context, command, _duration):
        assert len(observed) == 1
        assert paths(command) == ["A.mp4", "B.mp4", "original.mp4", "original.mp4", "background.png"]
        raise RuntimeError("captured without spawning FFmpeg")

    monkeypatch.setattr(render, "compile_render_inputs", compile_once)
    monkeypatch.setattr(render, "build_filter_graph", graph_with_shared)
    monkeypatch.setattr(render, "_run_ffmpeg_process", capture)
    with pytest.raises(RuntimeError, match="captured without"):
        render.render_project(context, value["id"], store, settings)
    assert not list((tmp_path / "cache").glob("filter-*"))
    assert list(exports.iterdir()) == []
