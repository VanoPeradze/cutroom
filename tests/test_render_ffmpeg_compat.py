from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import render
from cutroom.ffmpeg_compat import ExportCapabilities, FFmpegCompatibilityError


@pytest.fixture
def render_fixture(tmp_path, monkeypatch):
    root = tmp_path / "project עברית with spaces"
    (root / "media").mkdir(parents=True)
    (root / "media" / "A.mp4").write_bytes(b"synthetic source")
    exports = tmp_path / "exports"
    exports.mkdir()
    project = {"id": "project_probe", "name": "compatibility", "sources": {"A": {
        "relative_path": "media/A.mp4", "duration": 1.0, "width": 320, "height": 240, "has_audio": False}},
        "settings": {"fps": 30, "editorial_effects": False}, "manual": {}, "analysis": None,
        "draft": {"keep_ranges": [{"start": 0, "end": 1}], "camera_plan": [{"start": 0, "end": 1, "camera": "A"}]},
        "exports": []}
    store = SimpleNamespace(load=lambda _id: copy.deepcopy(project), project_dir=lambda _id: root)
    settings = SimpleNamespace(ffmpeg="configured ffmpeg", exports_dir=exports,
                               raw={"ffmpeg_threads": 1}, render={"audio_bitrate": "128k"})
    context = SimpleNamespace(check_cancelled=lambda: None, update=lambda *_args: None)
    monkeypatch.setattr(render, "ensure_render_storage", lambda *_args: None)
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    return root, store, settings, context


@pytest.mark.parametrize(("graph_option", "cfr"), [
    ("-filter_complex_script", ("-vsync", "1")),
    ("-filter_complex_script", ("-fps_mode:v", "cfr")),
    ("-/filter_complex", ("-fps_mode:v", "cfr")),
])
def test_render_keeps_large_graph_in_file_and_uses_verified_binary_and_cfr(monkeypatch, render_fixture, graph_option, cfr):
    root, store, settings, context = render_fixture
    capabilities = ExportCapabilities("resolved FFmpeg path.exe", graph_option, cfr)
    monkeypatch.setattr(render, "export_capabilities", lambda executable: capabilities)
    large_graph = "[0:v]" + "null," * 10000 + "null[vout]"
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: (large_graph, ["-map", "[vout]"], False))
    observed = []

    def capture(_context, command, _duration):
        assert isinstance(command, list) and command[0] == capabilities.executable
        graph = Path(command[command.index(graph_option) + 1])
        assert graph.parent == root / "cache" and graph.read_text(encoding="utf-8") == large_graph
        assert large_graph not in command and "-filter_complex" not in command
        assert command[command.index(cfr[0]) + 1] == cfr[1]
        assert command[command.index("-r:v") + 1] == "30"
        assert ("-vsync" in command) != ("-fps_mode:v" in command)
        observed.append(graph)
        raise RuntimeError("captured command without executing FFmpeg")

    monkeypatch.setattr(render, "_run_ffmpeg_process", capture)
    with pytest.raises(RuntimeError, match="captured command"):
        render.render_project(context, "project_probe", store, settings)
    assert observed and not observed[0].exists()
    assert list(settings.exports_dir.iterdir()) == []


def test_incompatible_binary_fails_before_graph_or_caption_artifacts(monkeypatch, render_fixture):
    root, store, settings, context = render_fixture
    monkeypatch.setattr(render, "export_capabilities", lambda _executable: (_ for _ in ()).throw(
        FFmpegCompatibilityError("Unsupported graph-file options")))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: pytest.fail("must fail before graph construction"))
    with pytest.raises(FFmpegCompatibilityError, match="Unsupported graph-file"):
        render.render_project(context, "project_probe", store, settings)
    assert not (root / "cache").exists() and list(settings.exports_dir.iterdir()) == []
