"""The shipped welcome module, exercised without network or browser storage."""
from pathlib import Path
import shutil
import subprocess

import pytest


def test_frontend_welcome_behaviors():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for welcome behavior checks")
    result = subprocess.run([node, "--test", str(Path(__file__).with_name("frontend_welcome.test.cjs"))],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
