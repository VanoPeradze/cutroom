"""Exercise the shipped local-model setup UI without network or real downloads."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_local_model_behaviors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for local-model UI behavior checks")
    script = Path(__file__).with_name("frontend_local_models.test.cjs")
    result = subprocess.run([node, "--test", str(script)], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
