from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from cutroom import audio


def test_audio_analysis_drains_noisy_ffmpeg_stderr(monkeypatch, tmp_path: Path):
    child = tmp_path / "noisy_audio_decoder.py"
    child.write_text(
        """
import os

for _ in range(256):
    os.write(2, b"decode warning " + b"E" * 8176 + b"\\n")
samples = (b"\\x00\\x10" * 8000)
os.write(1, samples)
""".strip(),
        encoding="utf-8",
    )
    real_popen = subprocess.Popen

    def fake_popen(*_args, **kwargs):
        return real_popen(
            [sys.executable, str(child)],
            stdout=kwargs.get("stdout"),
            stderr=kwargs.get("stderr"),
        )

    monkeypatch.setattr(audio.subprocess, "Popen", fake_popen)
    settings = SimpleNamespace(
        ffmpeg="unused",
        raw={"audio_analysis_sample_rate": 8000, "audio_analysis_window_seconds": 0.20},
    )
    started = time.monotonic()
    result = audio.analyze_audio(tmp_path / "source.mp4", settings, 1.0)

    assert time.monotonic() - started < 5.0
    assert result["available"] is True
    assert result["duration"] == 1.0
