from __future__ import annotations

import shutil
import subprocess
import re
from pathlib import Path

import pytest


def test_workspace_controls_in_node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is needed for workspace interaction tests")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("frontend_workspace.test.cjs"))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_video_fullscreen_uses_the_composite_without_expanding_the_editor():
    root = Path(__file__).resolve().parents[1]
    script = (root / "web" / "workspace.js").read_text(encoding="utf-8")
    css = (root / "web" / "workspace.css").read_text(encoding="utf-8")
    assert "await preview.requestFullscreen()" in script
    assert "doc.documentElement.requestFullscreen()" not in script
    assert "videoDialog.appendChild(preview)" in script
    assert "video-expanded .preview-controls" in css
    assert "workspace-expanded" not in css
    assert "workspace-preview-focus" not in css
    assert "grid-column: 2 / -1" in css
    assert 'grid-template-rows: max-content minmax(180px,1fr) 14px var(--workspace-timeline-height)' in css
    # A wrapped mobile header must reserve its content height; an auto track
    # shrinks to the explicit44px minimum and lets buttons cover the preview.
    # Only the workspace's own grid reserves header content. Nested monitor
    # transport intentionally uses a fixed36px row and is a separate layout.
    panel_rules = re.findall(
        r'\.advanced-panel\.studio-workspace(?:\.studio-transcript)?:not\(\[hidden\]\)[^{}]*\{([^{}]*)\}',
        css.split("/* Video-only fullscreen.")[0],
    )
    rows = [row for rule in panel_rules for row in re.findall(r'grid-template-rows:\s*([^;]+)', rule)]
    assert len(rows) >= 2 and all(row.startswith("max-content") for row in rows)


def test_workspace_generated_ids_do_not_collide_with_existing_markup():
    root = Path(__file__).resolve().parents[1]
    script = (root / "web" / "workspace.js").read_text(encoding="utf-8")
    html = (root / "web" / "index.html").read_text(encoding="utf-8")
    generated = re.findall(r'\.id = "([^"]+)"', script) + re.findall(r'button\("([^"]+)"', script)
    existing = set(re.findall(r'\bid="([^"]+)"', html))
    assert len(generated) == len(set(generated))
    assert not existing.intersection(generated)
