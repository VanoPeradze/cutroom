"""Lightweight repository presentation checks; no network or third-party packages."""
from __future__ import annotations

import ast
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.parse import quote, unquote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ("README.md", ".github/CONTRIBUTING.md", ".github/SECURITY.md")
OVERVIEW_DOCUMENTS = frozenset(DOCUMENTS[1:])
REPOSITORY_BLOB_PATH = "/VanoPeradze/cutroom/blob/"


class Resources(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for key, value in attrs if key in {"src", "href"} and value)


def check_document(name: str) -> None:
    source = ROOT / name
    text = source.read_text(encoding="utf-8")
    parser = Resources()
    parser.feed(text)
    links = parser.links + re.findall(r"\]\(([^\s)]+)\)", text)
    for link in links:
        target = urlsplit(link)
        if not target.path:
            continue
        if target.netloc == "github.com" and target.path.startswith(REPOSITORY_BLOB_PATH):
            revision, separator, path = target.path[len(REPOSITORY_BLOB_PATH):].partition("/")
            if not separator or revision not in {"HEAD", "master"}:
                raise ValueError(f"{name}: repository file link must use HEAD or master: {link!r}")
            local = (ROOT / unquote(path)).resolve()
        elif target.scheme or target.netloc:
            continue
        else:
            # GitHub overview tabs resolve these from the repo root, not .github/.
            if name in OVERVIEW_DOCUMENTS:
                raise ValueError(f"{name}: use an absolute GitHub file URL for overview-safe links: {link!r}")
            local = (source.parent / unquote(target.path)).resolve()
        if not local.is_relative_to(ROOT) or not local.is_file():
            raise ValueError(f"{name}: missing or unsafe local resource {link!r}")
    if name == "README.md":
        if re.search(r"[\u0590-\u05ff]", text):
            raise ValueError("The main README must stay English-only")
        tree = ast.parse((ROOT / "cutroom/__init__.py").read_text(encoding="utf-8"))
        version = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                       and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets))
        version_label = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == "__version_label__" for target in node.targets))
        if version_label != version.removesuffix("-beta") + " Beta":
            raise ValueError("Application beta identifier and display label must agree")
        if f"badge/version-{quote(version_label, safe='')}-" not in text:
            raise ValueError("README version badge must match the application version")
        if "MIT" not in text or "beta" not in text.lower():
            raise ValueError("README must identify the license and beta status")


def main() -> None:
    for name in (*DOCUMENTS, *(path.relative_to(ROOT).as_posix() for path in sorted((ROOT / "docs").rglob("*.md")))):
        check_document(name)
    if (ROOT / "website/README.md").is_file():
        check_document("website/README.md")
    if not (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License"):
        raise ValueError("Expected the project's MIT license")
    ET.parse(ROOT / "docs/images/readme-banner.svg")
    for name in ("bug_report.yml", "feature_request.yml"):
        if not (ROOT / ".github/ISSUE_TEMPLATE" / name).is_file():
            raise ValueError(f"Missing issue template: {name}")
    print("PASS: English README, version, local/GitHub file links, overview-safe community links, brand SVG and license.")


if __name__ == "__main__":
    main()
