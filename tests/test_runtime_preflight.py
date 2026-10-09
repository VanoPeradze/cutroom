"""Startup must verify actual speech decoding, not only successful imports."""
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
