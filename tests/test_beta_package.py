"""Check the real beta payload, not just a synthetic packaging fixture."""
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from cutroom.config import DEFAULTS
from scripts.build_test_package import collect_payload

ROOT = Path(__file__).resolve().parents[1]


def test_beta_entry_documents_and_their_local_links_ship_together():
    payload = collect_payload(ROOT)
    entry_points = ["README.md", "README_HE.md", "docs/BETA_STATUS.md",
                    "docs/BETA_FEEDBACK.md", "docs/MODELS.md", "docs/INDEPENDENT_TRACKS.md"]
    for name in entry_points:
        content = payload[name].decode("utf-8")
        assert len(content) > 200
        for href in re.findall(r"\]\(([^)]+)\)", content):
            target = urlsplit(href)
            if target.scheme or not target.path:
                continue
            local = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(target.path)))
            assert local in payload, (name, local)
    assert "MIT" in payload["README.md"].decode()
    assert "Codex" in payload["START_TESTING.txt"].decode()


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
