"""Build a clean source-only test ZIP; never copy runtime or user configuration."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import stat
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = (
    ".gitignore", ".gitattributes", "server.py", "requirements.txt", "requirements-dev.txt", "pytest.ini",
    "run_windows.bat", "repair_windows.bat", "setup_windows.ps1", "PUBLISH.bat",
    "verify_windows_installer.ps1", "run_linux.sh", "setup_linux.sh",
    "README.md", "README_HE.md", "START_HERE_HE.txt", "CHANGELOG.md",
    "LICENSE", "THIRD_PARTY_NOTICES.md", "UPGRADE_HE.md",
)
SOURCE_TREES = {
    "cutroom": {".py"}, "web": {".html", ".css", ".js", ".svg"},
    "scripts": {".py"}, "tests": {".py", ".cjs"},
}
DOC_FILES = (
    "docs/KEYBOARD_SHORTCUTS.md", "docs/KEYBOARD_PROFILES.md", "docs/UI_LAYOUT_QA.md",
    "docs/CREATOR_EDITING_RESEARCH.md", "docs/TEST_ON_ANOTHER_PC.md",
    "docs/TRANSCRIPT_EVALUATION.md", "docs/QUALITY_AND_LIMITS.md", "docs/UIUX_SKILL_CSS.md",
    "docs/INDEPENDENT_TRACKS.md", "docs/BETA_FEEDBACK.md", "docs/BETA_STATUS.md", "docs/MODELS.md",
    "docs/CONTRIBUTING.md", "docs/AI_CONNECTIONS.md", "docs/PUBLISHING.md",
    "docs/USER_GUIDE_EN.md", "docs/USER_GUIDE_HE.md", "docs/SHOWCASE_EN.md", "docs/SHOWCASE_HE.md",
)
# Only reviewed, purpose-made app screenshots belong in the tester package.
# Missing captures fail the build rather than silently shipping broken guide links.
IMAGE_FILES = (
    "docs/images/welcome.png", "docs/images/editor.png", "docs/images/ai-options.png",
)
START_TEXT = """CUTROOM
Your footage. Your edit.

Free and open source (MIT). No subscription. No CUTROOM watermark.

GET STARTED
1. Extract the entire ZIP into a folder.
2. Open it and double-click run_windows.bat.
3. Follow the setup prompts. CUTROOM opens in your browser when ready.

First setup needs internet. Some AI features need an additional download
before first use. Keep the launch window open while editing, and use
the same launcher next time.

Start with a short recording you know well. This is a closed beta:
review the draft and exported video before sharing.

Your guide: README.md
Setup help: docs/TEST_ON_ANOTHER_PC.md
Feedback: docs/BETA_FEEDBACK.md

What saved you time? What got in your way?
Send feedback privately to whoever shared CUTROOM with you.
Please leave out private client footage and personal information.
"""


def _bytes_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def _read_source(root: Path, relative: str) -> bytes:
    path = root / relative
    current = path
    while current != root:
        if _is_link(current):
            raise ValueError(f"Refusing linked package input: {relative}")
        current = current.parent
    if not path.is_file() or not path.resolve().is_relative_to(root):
        raise ValueError(f"Missing/unsafe package input: {relative}")
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError(f"Unexpectedly large source file: {relative}")
    return path.read_bytes()


def _literal(source: bytes, name: str) -> object:
    for node in ast.parse(source).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing source constant: {name}")


def collect_payload(root: Path) -> dict[str, bytes]:
    root = root.resolve()
    payload = {name: _read_source(root, name) for name in (*ROOT_FILES, *DOC_FILES, *IMAGE_FILES)}

    def walk(directory: Path, suffixes: set[str]) -> None:
        if _is_link(directory):
            raise ValueError(f"Refusing linked source directory: {directory.name}")
        for path in sorted(directory.iterdir()):
            if path.name.startswith(".") or path.name == "__pycache__":
                continue
            if _is_link(path):
                raise ValueError(f"Refusing linked source entry: {path.name}")
            if path.is_dir():
                walk(path, suffixes)
            elif path.suffix.lower() in suffixes:
                name = path.relative_to(root).as_posix()
                payload[name] = _read_source(root, name)

    for name, suffixes in SOURCE_TREES.items():
        walk(root / name, suffixes)
    # Read only version-controlled defaults, never config.json from this PC.
    defaults = _literal(payload["cutroom/config.py"], "DEFAULTS")
    if not isinstance(defaults, dict):
        raise ValueError("Invalid default configuration")
    defaults.update(host="127.0.0.1", port=8765, data_dir="data", open_browser=True)
    defaults["ai"].update(ollama_url="http://127.0.0.1:11434", download_models_on_setup=False)
    payload["config.json"] = _bytes_json(defaults)
    payload["START_TESTING.txt"] = START_TEXT.replace("\n", "\r\n").encode("ascii")
    return payload


def verify_package(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or not names:
            raise ValueError("Duplicate/empty package entries")
        roots = {name.split("/")[0] for name in names}
        if len(roots) != 1:
            raise ValueError("Package must have one top-level folder")
        prefix = roots.pop()
        if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", prefix):
            raise ValueError("Unsafe package folder")
        for name in names:
            parts = PurePosixPath(name).parts
            if "\\" in name or ":" in name or ".." in parts or "." in name.split("/"):
                raise ValueError("Unsafe archive path")
            if name != PurePosixPath(name).as_posix() or len(parts) < 2:
                raise ValueError("Non-canonical archive path")
        manifest_name = prefix + "/TEST_BUILD.json"
        manifest = json.loads(bundle.read(manifest_name))
        expected = {prefix + "/" + name for name in manifest["files"]} | {manifest_name}
        if set(names) != expected:
            raise ValueError("Package file inventory mismatch")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(bundle.read(prefix + "/" + name)).hexdigest() != digest:
                raise ValueError(f"Package checksum mismatch: {name}")
        if bundle.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        return manifest


def build_package(root: Path, output_dir: Path, *, build_id: str | None = None) -> Path:
    payload = collect_payload(root)
    version = _literal(payload["cutroom/__init__.py"], "__version__")
    stamp = build_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = f"CUTROOM-{version}-test-{stamp}"
    if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", folder):
        raise ValueError("Unsafe build identifier")
    manifest = {
        "build_id": folder, "app_version": version, "kind": "private-source-test",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "target": "Windows x64 first-run testing; no bundled runtime",
        "clean_machine_install_verified": False,
        "configuration": "fresh application defaults, loopback only",
        "not_included": ["user media", "projects", "logs", "local config", "runtimes", "models"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())},
    }
    payload["TEST_BUILD.json"] = _bytes_json(manifest)
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / (folder + ".zip")
    checksum = target.with_suffix(".zip.sha256")
    if target.exists() or checksum.exists():
        raise FileExistsError(f"Package already exists: {target.name}")
    # Exclusive final creation prevents overwriting an earlier test build.
    with tempfile.TemporaryDirectory(prefix="cutroom-package-") as scratch:
        staging = Path(scratch) / "package.zip"
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(folder + "/" + name)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (0o100755 if name.endswith(".sh") else 0o100644) << 16
                bundle.writestr(info, data)
        verify_package(staging)
        archive_bytes = staging.read_bytes()
        with target.open("xb") as handle:
            handle.write(archive_bytes)
        with checksum.open("x", encoding="ascii") as handle:
            handle.write(f"{hashlib.sha256(archive_bytes).hexdigest()}  {target.name}\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--verify", type=Path, help="Verify an existing archive instead of building")
    args = parser.parse_args()
    if args.verify:
        manifest = verify_package(args.verify)
        print(f"Verified {manifest['build_id']}: {len(manifest['files'])} files")
    else:
        print(build_package(ROOT, args.output_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
