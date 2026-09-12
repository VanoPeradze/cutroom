"""Run the real canvas timeline interaction code against deterministic browser doubles."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_timeline_interaction_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the timeline interaction harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_timeline.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
