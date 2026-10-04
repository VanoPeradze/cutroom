from __future__ import annotations

import copy
import subprocess
from types import SimpleNamespace

import pytest

from cutroom.composition import normalize_chroma_key, source_chroma_key
from cutroom.effects import _chroma_filters, build_chroma_key_nodes, chroma_key_capability, chroma_key_filter
from cutroom.render import _render_input_fingerprint, build_filter_graph


DEFAULT = {"enabled": False, "color": "#00FF00", "tolerance": 0.12,
           "edge_softness": 0.08, "background_color": "#000000", "background_asset_id": None, "background_mode": "replace"}


def project():
    return {"sources": {"A": {"duration": 1, "width": 320, "height": 180}, "B": None},
            "manual": {}}


def test_legacy_missing_settings_remain_disabled_and_detached():
    value = project()
    original = copy.deepcopy(value)
    result = source_chroma_key(value, "A")
    assert result == DEFAULT and chroma_key_filter(result) == "null"
    result["enabled"] = True
    assert value == original and source_chroma_key(value, "A") == DEFAULT


@pytest.mark.parametrize("field,value", [
    ("enabled", "true"), ("enabled", 1), ("color", "green"),
    ("color", "#00FF00;movie=https://example.invalid"),
    ("background_color", "#000000@0"), ("tolerance", True),
    ("tolerance", "0.12"), ("tolerance", 0), ("tolerance", 1.01),
    ("tolerance", float("nan")), ("edge_softness", -0.1),
    ("edge_softness", float("inf")),
])
def test_invalid_configuration_is_rejected_strictly_and_fails_closed_when_loading(field, value):
    raw = {**DEFAULT, "enabled": True, field: value}
    with pytest.raises(ValueError):
        normalize_chroma_key(raw, strict=True)
    assert normalize_chroma_key(raw) == DEFAULT


def test_strict_configuration_is_canonical_and_only_compiles_validated_numbers_and_colors():
    raw = {**DEFAULT, "enabled": True, "color": "#00ff00", "background_color": "#3344aa",
           "tolerance": 0.2, "edge_softness": 0.1}
    original = copy.deepcopy(raw)
    result = normalize_chroma_key(raw, strict=True)
    assert result == {**raw, "color": "#00FF00", "background_color": "#3344AA"}
    expression = chroma_key_filter(result)
    assert "chromakey=" in expression and "0x00FF00" in expression
    assert raw == original
    with pytest.raises(ValueError):
        normalize_chroma_key({**raw, "filter": "arbitrary"}, strict=True)


def test_effect_cannot_enable_for_missing_or_audio_only_source():
    value = project()
    value["manual"]["chroma_key"] = {"A": {**DEFAULT, "enabled": True}, "B": {**DEFAULT, "enabled": True}}
    assert source_chroma_key(value, "A")["enabled"] is True
    assert source_chroma_key(value, "B") == DEFAULT
    value["sources"]["A"].update(width=0, height=0)
    assert source_chroma_key(value, "A") == DEFAULT


def test_disabled_settings_keep_legacy_render_fingerprint_and_active_changes_invalidate_it():
    value = project()
    original = _render_input_fingerprint(value)
    value["manual"]["chroma_key"] = {"A": {**DEFAULT, "background_color": "#123456"}}
    assert _render_input_fingerprint(value) == original
    value["manual"]["chroma_key"]["A"]["enabled"] = True
    active = _render_input_fingerprint(value)
    assert active != original
    value["manual"]["chroma_key"]["A"]["background_color"] = "#0000FF"
    assert _render_input_fingerprint(value) != active


@pytest.mark.parametrize("keyed,shown", [("A", "B"), ("B", "A")])
def test_unused_source_does_not_add_keying_or_composition_work(keyed, shown):
    value = project()
    value["sources"]["B"] = dict(value["sources"]["A"])
    value["settings"] = {"fps": 30, "editorial_effects": False}
    value["draft"] = {"keep_ranges": [{"start": 0, "end": 1}],
                      "camera_plan": [{"start": 0, "end": 1, "camera": shown}]}
    original = build_filter_graph(value, 320, 180)
    value["manual"]["chroma_key"] = {keyed: {**DEFAULT, "enabled": True}}
    assert build_filter_graph(value, 320, 180) == original


@pytest.mark.parametrize("kwargs", [{"width": 0}, {"height": 181}, {"fps": float("nan")},
                                   {"duration": -1}, {"prefix": "unsafe;movie"}])
def test_shared_preview_export_nodes_reject_invalid_geometry_clock_or_graph_names(kwargs):
    arguments = dict(width=320, height=180, fps=30, duration=2, prefix="test")
    arguments.update(kwargs)
    with pytest.raises(ValueError):
        build_chroma_key_nodes("[0:v]", "[output]", {**DEFAULT, "enabled": True}, **arguments)


def test_capability_is_cached_by_existing_binary_identity_and_gracefully_reports_missing_filter(tmp_path, monkeypatch):
    from cutroom import effects, media
    executable = tmp_path / "existing-ffmpeg.exe"
    executable.write_bytes(b"synthetic capability test marker; never executed")
    monkeypatch.setattr(effects.shutil, "which", lambda _: str(executable))
    calls = []
    names = "chromakey overlay split drawbox format scale crop setsar setpts".split()
    def inspect(args, **kwargs):
        calls.append(args)
        assert args == [str(executable), "-nostdin", "-hide_banner", "-filters"]
        return SimpleNamespace(stdout="\n".join(f" ... {name} V->V" for name in names))
    monkeypatch.setattr(media, "run_command", inspect)
    _chroma_filters.cache_clear()
    settings = SimpleNamespace(ffmpeg=str(executable))
    assert chroma_key_capability(settings)["available"] is True
    assert chroma_key_capability(settings)["available"] is True and len(calls) == 1
    executable.write_bytes(b"binary changed, missing optional filter")
    names.remove("chromakey")
    unavailable = chroma_key_capability(settings)
    assert unavailable["available"] is False and len(calls) == 2
    assert unavailable["mp4_alpha"] is False and unavailable["supports"] == ["solid", "image", "media-layer"]
    _chroma_filters.cache_clear()


def test_capability_inspection_errors_do_not_expose_local_paths(tmp_path, monkeypatch):
    from cutroom import effects, media
    executable = tmp_path / "private-tool-location.exe"
    executable.write_bytes(b"not executed")
    monkeypatch.setattr(effects.shutil, "which", lambda _: str(executable))
    def failed(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args, stderr=str(executable))
    monkeypatch.setattr(media, "run_command", failed)
    _chroma_filters.cache_clear()
    result = chroma_key_capability(SimpleNamespace(ffmpeg=str(executable)))
    assert result["available"] is False and str(executable) not in str(result)
    _chroma_filters.cache_clear()
