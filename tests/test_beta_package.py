"""Check the real beta payload, not just a synthetic packaging fixture."""
import posixpath
import re
import os
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cutroom.config import DEFAULTS
from cutroom import __version__, __version_label__
from scripts.build_test_package import build_package, collect_payload, verify_package

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_public_beta_version_is_consistent_across_package_and_setup():
    payload = collect_payload(ROOT)
    assert __version__ == "1.1-beta"
    assert __version_label__ == "1.1 Beta"
    assert f"CUTROOM {__version_label__}" in payload["START_TESTING.txt"].decode("ascii")
    assert "public beta" in payload["START_TESTING.txt"].decode("ascii")
    for name in ("run_windows.bat", "repair_windows.bat", "setup_windows.ps1",
                 "scripts/verify_windows_installer.ps1", "setup_linux.sh", "README.md", "docs/README_HE.md",
                 "docs/START_HERE_HE.txt", "docs/UPGRADE_HE.md", "docs/TEST_ON_ANOTHER_PC.md"):
        text = payload[name].decode("utf-8")
        assert __version_label__ in text, name
        assert "5.6.1" not in text, name
    marker = f"CUTROOM AI {__version_label__} setup completed"
    assert marker in payload["run_windows.bat"].decode("ascii")
    assert marker in payload["setup_linux.sh"].decode("ascii")


def test_beta_entry_documents_and_their_local_links_ship_together():
    payload = collect_payload(ROOT)
    entry_points = ["README.md", "docs/README.md", "docs/README_HE.md", ".github/CONTRIBUTING.md", ".github/SECURITY.md", "docs/BETA_STATUS.md",
                    "docs/BETA_FEEDBACK.md", "docs/MODELS.md", "docs/INDEPENDENT_TRACKS.md",
                    "docs/CONTRIBUTING.md", "docs/PUBLISHING.md", "docs/AI_CONNECTIONS.md",
                    "docs/USER_GUIDE_EN.md", "docs/USER_GUIDE_HE.md", "docs/SHOWCASE_EN.md", "docs/SHOWCASE_HE.md"]
    for name in entry_points:
        content = payload[name].decode("utf-8")
        assert len(content) > 200
        resources = re.findall(r"\]\(([^)]+)\)", content)
        resources += re.findall(r'(?:src|href)="([^"]+)"', content)
        for href in resources:
            target = urlsplit(href)
            if target.scheme or not target.path:
                continue
            local = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(target.path)))
            assert local in payload, (name, local)
    assert "MIT" in payload["README.md"].decode()
    assert "run_windows.bat" in payload["START_TESTING.txt"].decode()
    assert "README.md" in payload["START_TESTING.txt"].decode()
    for name in ("README.md", "docs/README_HE.md", "docs/START_HERE_HE.txt", "START_TESTING.txt"):
        text = payload[name].decode("utf-8").lower()
        for infrastructure_detail in ("127.0.0.1", "localhost", "nvidia", "cuda", "ollama", "ctranslate2"):
            assert infrastructure_detail not in text, (name, infrastructure_detail)


def test_beta_payload_contains_all_local_frontend_modules_and_assets():
    payload = collect_payload(ROOT)
    for name, data in payload.items():
        if not name.startswith("web/"):
            continue
        content = data.decode("utf-8")
        imports = re.findall(r"(?:from\s+|import\s*)['\"](\.[^'\"]+)['\"]", content)
        assets = re.findall(r"(?:src|href)=[\"'](/assets/[^\"']+)[\"']", content)
        for href in imports + assets:
            path = urlsplit(href).path
            local = ("web/" + path.removeprefix("/assets/") if path.startswith("/assets/")
                     else posixpath.normpath(posixpath.join(posixpath.dirname(name), path)))
            assert local in payload, (name, href)


def test_model_guide_covers_all_shipped_model_choices():
    guide = (ROOT / "docs/MODELS.md").read_text(encoding="utf-8")
    ai = DEFAULTS["ai"]
    for model in [ai["editor_model"], ai["editor_lite_model"], ai["editor_quality_model"],
                  ai["hebrew_whisper_model"], *ai["editor_fallback_models"],
                  *ai["whisper_models"].values()]:
        assert model in guide


def test_beta_gitignore_excludes_private_data_and_runtime_files():
    rules = (ROOT / ".gitignore").read_text().splitlines()
    for pattern in ("data/", ".venv/", ".tools/", "dist/", ".runtime-paths.cmd", ".env"):
        assert pattern in rules


@pytest.mark.skipif(os.name != "nt", reason="Runs the read-only Windows installer verifier")
def test_reorganized_real_package_keeps_setup_and_development_requirements(tmp_path):
    archive = build_package(ROOT, tmp_path / "build", build_id="structure-check")
    verify_package(archive)
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(tmp_path / "extracted")
    app = tmp_path / "extracted/App"
    assert (app / "tests/requirements.txt").read_text().splitlines()[0] == "-r ../requirements.txt"
    assert (app / "requirements.txt").is_file()
    assert (app / ".github/SECURITY.md").is_file()
    assert (app / "docs/README.md").is_file()
    completed = subprocess.run(
        ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(app / "scripts/verify_windows_installer.ps1")],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
