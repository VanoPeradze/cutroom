"""Behavioral browser-state regression checks using the shipped JavaScript."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_workflow_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the frontend workflow harness")
    script = Path(__file__).with_name("frontend_workflows.test.cjs")
    result = subprocess.run(
        [node, "--test", str(script)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
