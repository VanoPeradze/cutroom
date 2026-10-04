"""Run extra Mac smoke assertions against a disposable real local HTTP server.

Portable execution checks the test itself; only the macOS workflow establishes
Mac compatibility. No user application, project, or running server is used.
"""
from array import array
import math
from pathlib import Path
import shutil
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from smoke_macos import synthetic_project
from smoke_macos_media import extended_render_checks, tone_level


def test_tone_assertion_distinguishes_imported_music_from_original_audio():
    signal = array("f", [.06 * math.sin(2 * math.pi * 1000 * index / 48000) for index in range(24000)])
    assert .059 < tone_level(signal, .3, 1000) < .061
    assert tone_level(signal, .3, 880) < .001


@pytest.mark.skipif(sys.platform == "win32" and not sys.flags.utf8_mode,
                    reason="Use python -X utf8, matching the unchanged Windows launcher")
def test_extended_http_media_smoke(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real FFmpeg required for the portable smoke self-test")
    from cutroom.config import load_settings
    from server import create_app
    from werkzeug.serving import make_server
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "private data שלום"))
    monkeypatch.setenv("CUTROOM_NO_BROWSER", "1")
    settings = load_settings(tmp_path / "no-user-config.json")
    settings.ai.update(enabled=False, auto_start_ollama=False, download_models_on_setup=False)
    settings.raw["render"]["prefer_hardware"] = False
    project_id, store = synthetic_project(settings, tmp_path)
    server = make_server("127.0.0.1", 0, create_app(settings), threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        report = extended_render_checks(settings, f"http://127.0.0.1:{server.server_port}", project_id, store)
        assert report["mixer_gain_and_source_mute"] == "passed"
        assert [item["width"] for item in report["exports"]] == [2560, 3840]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
