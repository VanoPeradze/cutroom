"""Versioned timeline identity and unavailable-view frontend safety."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_timeline_binding_frontend_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the timeline binding harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_timeline_bindings.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
