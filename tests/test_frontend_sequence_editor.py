"""Read-only editor projection and sequence action UI regression coverage."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_sequence_editor_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the sequence editor harness")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_sequence_editor.test.cjs"))],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
