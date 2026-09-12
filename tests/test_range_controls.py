"""Exercise shipped source-time range and A/B controls without AI or media."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_source_time_range_controls():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the range control harness")
    script = Path(__file__).with_name("frontend_range_controls.test.cjs")
    result = subprocess.run(
        [node, "--test", str(script)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
