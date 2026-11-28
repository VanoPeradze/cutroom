"""Add to Clips and the Manual section of the Clips board, without media or AI."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_manual_clip_frontend_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the frontend harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_manual_clips.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
