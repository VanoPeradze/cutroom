"""Startup must verify the real media capabilities, not only successful imports."""
from scripts import preflight


def test_preflight_decodes_real_in_memory_wav_without_loading_a_model():
    preflight._check_audio_decoder()


def test_preflight_rejects_incompatible_speech_decoder(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(preflight, "_command_ready", lambda _command: True)

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
    monkeypatch.setattr(preflight, "_check_audio_decoder", lambda: None)

    def unavailable():
        raise RuntimeError("OpenCV has no CascadeClassifier API")

    monkeypatch.setattr(vision, "check_camera_detector_capability", unavailable)
    assert preflight.main() == 1
    error = capsys.readouterr().err
    assert "Camera detector" in error and "CascadeClassifier" in error
    assert "Traceback" not in error
