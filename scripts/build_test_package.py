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
    "run_windows.bat", "repair_windows.bat", "setup_windows.ps1",
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
)
START_TEXT = """CUTROOM - PRIVATE WINDOWS BETA TEST BUILD

Free and open source (MIT). No subscription, paid API key or CUTROOM watermark.
Source included. Third-party tools and models have separate licenses.

1. Extract the entire ZIP first (do not run inside the ZIP).
2. Open the extracted CUTROOM folder and double-click run_windows.bat.
3. Allow the one-time setup to finish; keep its terminal open while using CUTROOM.
4. The browser opens automatically. Default address: http://127.0.0.1:8765

Codex is NOT needed. Use the same launcher for future sessions.
First setup needs internet. It installs/reuses Python, Python packages, FFmpeg
and attempts to install Ollama. Missing FFmpeg requires working winget or a
separate installation. External installers may need administrator approval.
AI models are NOT bundled. Speech models download on first use; a missing Story
model is a separate confirmed download in the app and can require several GB.
Offline use needs the required software/models downloaded on that PC first.

Read docs/TEST_ON_ANOTHER_PC.md for prerequisites, the test checklist and a
bug-report template. Start with short clips, Lite, 720p and Fast export.
Read README.md for editing; docs/BETA_FEEDBACK.md for private feedback.
docs/BETA_STATUS.md explains verified checks and unverified quality/PC support.

This is an experimental source package, not a signed standalone EXE or a
release-readiness guarantee. Clean-machine installation has not been verified.
No original media, projects, logs, installed runtimes or personal config included.
New projects/cache/exports are stored in this extracted folder's data directory.
The server binds only to this PC's loopback address. Do not expose it to the web.
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
    payload = {name: _read_source(root, name) for name in (*ROOT_FILES, *DOC_FILES)}

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
