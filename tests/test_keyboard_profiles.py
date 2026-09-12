"""Run the pure shipped shortcut resolver in Node, without a server or media."""

from pathlib import Path
import shutil
import subprocess

import pytest


def test_editor_keyboard_profiles():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the keyboard shortcut harness")
    script = Path(__file__).with_name("frontend_keyboard.test.cjs")
    result = subprocess.run(
        [node, "--test", str(script)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
