"""Independent A/B preview playback without media/AI dependencies."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_source_track_preview_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the preview harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_source_tracks.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
