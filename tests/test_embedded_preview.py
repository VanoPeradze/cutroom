"""Run shipped embedded-composition UI behavior without real user media or AI."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_embedded_preview_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the embedded preview harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_embedded_composition.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
