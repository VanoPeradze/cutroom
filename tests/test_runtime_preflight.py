"""Startup must verify the real media capabilities, not only successful imports."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import preflight


def test_preflight_decodes_real_in_memory_wav_without_loading_a_model():
    preflight._check_audio_decoder()


def test_preflight_rejects_incompatible_speech_decoder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(preflight, "_command_ready", lambda _command: True)
    monkeypatch.setattr(preflight, "_check_ffmpeg", lambda _command: None)

    def incompatible():
        raise TypeError("open() got an unexpected keyword argument 'metadata_errors'")

    monkeypatch.setattr(preflight, "_check_audio_decoder", incompatible)
    assert preflight.main() == 1
    error = capsys.readouterr().err
    assert "Speech audio decoder" in error and "metadata_errors" in error
    assert "Traceback" not in error


def test_preflight_rejects_camera_backend_even_when_imports_succeed(tmp_path, monkeypatch, capsys):
    from cutroom import vision

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(preflight, "REQUIRED_MODULES", ())
    monkeypatch.setattr(preflight, "_command_ready", lambda _command: True)
    monkeypatch.setattr(preflight, "_check_ffmpeg", lambda _command: None)
    monkeypatch.setattr(preflight, "_check_audio_decoder", lambda: None)

    def unavailable():
        raise RuntimeError("OpenCV has no CascadeClassifier API")

    monkeypatch.setattr(vision, "check_camera_detector_capability", unavailable)
    assert preflight.main() == 1
    error = capsys.readouterr().err
    assert "Camera detector" in error and "CascadeClassifier" in error
    assert "Traceback" not in error


def _ffmpeg_inventory(monkeypatch, *, filters="subtitles", encoders=("libx264", "aac")):
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        assert kwargs["stdin"] == preflight.subprocess.DEVNULL
        assert kwargs["timeout"] == 15
        assert kwargs["check"] is False
        if arguments[-1] == "-filters":
            return SimpleNamespace(returncode=0, stdout=f" ... {filters} V->V synthetic filter inventory\n")
        assert arguments[-1] == "-encoders"
        return SimpleNamespace(returncode=0, stdout="\n".join(f" V..... {name} synthetic encoder inventory" for name in encoders))

    monkeypatch.setattr(preflight.subprocess, "run", run)
    return calls


def test_preflight_checks_export_codecs_and_shared_executable_probe(monkeypatch):
    from cutroom import ffmpeg_compat

    calls = _ffmpeg_inventory(monkeypatch)
    probes = []
    monkeypatch.setattr(ffmpeg_compat, "export_capabilities", lambda command: probes.append(command))
    preflight._check_ffmpeg("C:/chosen FFmpeg/ffmpeg.exe")
    assert probes == ["C:/chosen FFmpeg/ffmpeg.exe"]
    assert [call[-1] for call in calls] == ["-filters", "-encoders"]
    assert all(call[0] == probes[0] for call in calls)


@pytest.mark.parametrize("filters, encoders, missing", [
    ("scale", ("libx264", "aac"), "libass subtitles filter"),
    ("subtitles", ("aac",), "libx264 encoder"),
    ("subtitles", ("libx264",), "aac encoder"),
])
def test_preflight_rejects_missing_export_codec_despite_startable_ffmpeg(monkeypatch, filters, encoders, missing):
    _ffmpeg_inventory(monkeypatch, filters=filters, encoders=encoders)
    with pytest.raises(RuntimeError, match=missing):
        preflight._check_ffmpeg("ffmpeg")


def test_preflight_rejects_failed_real_graph_probe_despite_available_commands(tmp_path, monkeypatch, capsys):
    from cutroom import ffmpeg_compat, vision

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(preflight, "REQUIRED_MODULES", ())
    monkeypatch.setattr(preflight, "_check_audio_decoder", lambda: None)
    monkeypatch.setattr(vision, "check_camera_detector_capability", lambda: None)
    monkeypatch.setattr(preflight, "_command_ready", lambda _command: True)
    _ffmpeg_inventory(monkeypatch)

    def incompatible(_command):
        raise RuntimeError("FFmpeg file-based graph/CFR probe failed")

    monkeypatch.setattr(ffmpeg_compat, "export_capabilities", incompatible)
    assert preflight.main() == 1
    error = capsys.readouterr().err
    assert "FFmpeg rendering" in error and "file-based graph/CFR probe failed" in error
    assert "Traceback" not in error


def test_windows_setup_checks_export_preflight_before_writing_success_marker():
    setup = (Path(__file__).resolve().parents[1] / "setup_windows.ps1").read_text(encoding="ascii")
    start = setup.index('Write-Step "Checking the completed installation"')
    preflight_call = setup.index('"scripts/preflight.py"', start)
    marker = setup.index('Set-Content -LiteralPath ".setup-complete"', start)
    assert start < preflight_call < marker
    assert ') -FailureMessage "CUTROOM rendering and runtime preflight failed."' in setup[preflight_call:marker]
