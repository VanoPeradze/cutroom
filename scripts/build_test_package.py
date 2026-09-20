"""Build a clean source-only beta ZIP; never copy runtime or user configuration."""
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
    ".gitignore", ".gitattributes", "server.py", "requirements.txt", "pytest.ini",
    "run_windows.bat", "repair_windows.bat", "setup_windows.ps1", "PUBLISH.bat",
    "run_linux.sh", "setup_linux.sh", "README.md", "CHANGELOG.md", "LICENSE",
)
# Explicit support files stay in their source locations inside App as well.
SUPPORT_FILES = (
    "scripts/verify_windows_installer.ps1", "tests/requirements.txt",
    ".github/CONTRIBUTING.md", ".github/SECURITY.md",
)
SOURCE_TREES = {
    "cutroom": {".py"}, "web": {".html", ".css", ".js", ".svg"},
    "scripts": {".py"}, "tests": {".py", ".cjs"},
}
DOC_FILES = (
    "docs/README.md", "docs/README_HE.md", "docs/START_HERE_HE.txt",
    "docs/THIRD_PARTY_NOTICES.md", "docs/UPGRADE_HE.md",
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
    "docs/images/readme-banner.svg",
)
PACKAGING_FILES = (
    "packaging/windows/START CUTROOM.bat",
    "packaging/windows/START HERE.html",
)
WINDOWS_LAYOUT = "windows-app-folder-v1"
WINDOWS_LAUNCHER = "START CUTROOM.bat"
WINDOWS_HELP = "START HERE.html"
WINDOWS_SOURCE_DIRECTORY = "App"
START_TEXT = """CUTROOM {version_label}
Your footage. Your edit.

Free and open source (MIT). No subscription. No CUTROOM watermark.

GET STARTED
1. Extract the entire ZIP into a folder.
2. Open it and double-click run_windows.bat.
3. Follow the setup prompts. CUTROOM opens in your browser when ready.

First setup needs internet. Some AI features need an additional download
before first use. Keep the launch window open while editing, and use
the same launcher next time.

Start with a short recording you know well. This is a public beta:
review the draft and exported video before sharing.

Your guide: README.md
Setup help: docs/TEST_ON_ANOTHER_PC.md
Feedback: docs/BETA_FEEDBACK.md

What saved you time? What got in your way?
Report reproducible problems at https://github.com/VanoPeradze/cutroom/issues.
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
    payload = {name: _read_source(root, name)
               for name in (*ROOT_FILES, *SUPPORT_FILES, *DOC_FILES, *IMAGE_FILES, *PACKAGING_FILES)}

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
    version_label = _literal(payload["cutroom/__init__.py"], "__version_label__")
    payload["START_TESTING.txt"] = START_TEXT.format(version_label=version_label).replace("\n", "\r\n").encode("ascii")
    return payload


def _check_archive_path(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise ValueError("Unsafe archive path")
    path = PurePosixPath(name)
    if (path.is_absolute() or "\\" in name or ":" in name or ".." in path.parts
            or "." in name.split("/") or any(ord(char) < 32 for char in name)):
        raise ValueError("Unsafe archive path")
    if name != path.as_posix():
        raise ValueError("Non-canonical archive path")


def verify_package(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len({name.casefold() for name in names}) or not names:
            raise ValueError("Duplicate/empty package entries")
        for name in names:
            _check_archive_path(name)
            mode = bundle.getinfo(name).external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("Linked or non-file archive entry")
        folded_names = {name.casefold() for name in names}
        if any(parent.as_posix().casefold() in folded_names
               for name in names for parent in PurePosixPath(name).parents if parent.as_posix() != "."):
            raise ValueError("Archive path is both a file and a directory")
        manifest_name = WINDOWS_SOURCE_DIRECTORY + "/TEST_BUILD.json"
        envelope = manifest_name in names
        if envelope:
            archive_prefix = ""
        else:
            roots = {name.split("/")[0] for name in names}
            if len(roots) != 1:
                raise ValueError("Legacy package must have one top-level folder")
            prefix = roots.pop()
            if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", prefix):
                raise ValueError("Unsafe package folder")
            archive_prefix = prefix + "/"
            manifest_name = archive_prefix + "TEST_BUILD.json"
        if manifest_name not in names:
            raise ValueError("Missing package manifest")
        manifest = json.loads(bundle.read(manifest_name))
        if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict) or not manifest["files"]:
            raise ValueError("Invalid package manifest")
        if not isinstance(manifest.get("build_id"), str) or not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", manifest["build_id"]):
            raise ValueError("Unsafe manifest build identifier")
        for name, digest in manifest["files"].items():
            _check_archive_path(name)
            if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
                raise ValueError("Invalid manifest checksum")
        expected = {archive_prefix + name for name in manifest["files"]} | {manifest_name}
        if manifest_name in {archive_prefix + name for name in manifest["files"]}:
            raise ValueError("Manifest must not inventory itself")
        if set(names) != expected:
            raise ValueError("Package file inventory mismatch")
        if envelope:
            if any(manifest.get(key) != value for key, value in {
                "layout": WINDOWS_LAYOUT, "archive_root": "",
                "source_directory": WINDOWS_SOURCE_DIRECTORY,
                "launcher": WINDOWS_LAUNCHER, "help": WINDOWS_HELP,
            }.items()):
                raise ValueError("Invalid Windows package layout metadata")
            roots = {name.split("/")[0] for name in names}
            if roots != {WINDOWS_LAUNCHER, WINDOWS_HELP, WINDOWS_SOURCE_DIRECTORY}:
                raise ValueError("Windows package must contain only its launcher, help and App folder")
            required = {WINDOWS_SOURCE_DIRECTORY + "/" + name for name in (
                "server.py", "config.json", "run_windows.bat", "LICENSE", *PACKAGING_FILES,
            )} | {WINDOWS_LAUNCHER, WINDOWS_HELP}
            if not required <= manifest["files"].keys():
                raise ValueError("Windows package is missing required application files")
            for source_name in PACKAGING_FILES:
                if bundle.read(PurePosixPath(source_name).name) != bundle.read(WINDOWS_SOURCE_DIRECTORY + "/" + source_name):
                    raise ValueError("Windows entry point differs from its source asset")
        elif manifest["build_id"] != prefix or manifest.get("archive_root", prefix) != prefix or "layout" in manifest:
            raise ValueError("Invalid legacy package layout metadata")
        for name, digest in manifest["files"].items():
            if hashlib.sha256(bundle.read(archive_prefix + name)).hexdigest() != digest:
                raise ValueError(f"Package checksum mismatch: {name}")
        if bundle.testzip() is not None:
            raise ValueError("ZIP integrity check failed")
        return manifest


def build_package(root: Path, output_dir: Path, *, build_id: str | None = None) -> Path:
    source_payload = collect_payload(root)
    version = _literal(source_payload["cutroom/__init__.py"], "__version__")
    version_label = _literal(source_payload["cutroom/__init__.py"], "__version_label__")
    stamp = build_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = f"CUTROOM-{version}-{stamp}"
    if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", folder):
        raise ValueError("Unsafe build identifier")
    payload = {WINDOWS_SOURCE_DIRECTORY + "/" + name: data for name, data in source_payload.items()}
    payload.update({PurePosixPath(name).name: source_payload[name] for name in PACKAGING_FILES})
    manifest = {
        "build_id": folder, "app_version": version, "app_version_label": version_label,
        "kind": "public-source-beta",
        "layout": WINDOWS_LAYOUT, "archive_root": "",
        "source_directory": WINDOWS_SOURCE_DIRECTORY,
        "launcher": WINDOWS_LAUNCHER, "help": WINDOWS_HELP,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "target": "Windows x64 first-run testing; no bundled runtime",
        "clean_machine_install_verified": False,
        "configuration": "fresh application defaults, loopback only",
        "not_included": ["user media", "projects", "logs", "local config", "runtimes", "models"],
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())},
    }
    payload[WINDOWS_SOURCE_DIRECTORY + "/TEST_BUILD.json"] = _bytes_json(manifest)
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
                info = zipfile.ZipInfo(name)
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
