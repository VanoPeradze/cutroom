"""Combine the frozen product payload, with an explicit documentation-only refresh."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_test_package import _bytes_json, _check_archive_path, _read_source
from scripts.build_test_package import verify_package as verify_windows_package

LAYOUT = "windows-mac-folders-v1"
MANIFEST = "mac/App/TEST_BUILD.json"
BASELINE = ROOT / "packaging/windows/release-baseline.json"
MAC_OVERLAY = {
    "packaging/mac/START CUTROOM.command": "mac/START CUTROOM.command",
    "packaging/mac/START HERE.html": "mac/START HERE.html",
    "packaging/mac/setup_macos.sh": "mac/App/setup_macos.sh",
    "packaging/mac/run_macos.sh": "mac/App/run_macos.sh",
    "packaging/mac/preflight_macos.py": "mac/App/preflight_macos.py",
    "packaging/mac/constraints-macos.txt": "mac/App/constraints-macos.txt",
    "docs/MAC_BETA.md": "mac/App/docs/MAC_BETA.md",
}
MAX_EXPANDED = 64 * 1024 * 1024
DOCUMENTATION_REVISION = "platform-guidance-v1"
DOCUMENTATION_SOURCE = "packaging/common/README.md"
DOCUMENTATION_PATHS = (
    "windows/App/README.md", "mac/App/README.md",
    "windows/App/TEST_BUILD.json", MANIFEST, "mac/App/docs/MAC_BETA.md",
)
# Manifest from the approved 20b03ae9... combined ZIP. This independently pins
# Mac-only launchers too; a self-consistent replacement manifest is insufficient.
DOCUMENTATION_BASELINE_MANIFEST_SHA256 = "0ec93a2ebc679122e2a9dd953fa9f1a1729df0f13616acfff11a23bd4371d67f"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _baseline() -> dict:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _read_archive(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as bundle:
        infos = bundle.infolist()
        names = [info.filename for info in infos]
        if not names or len(names) != len({name.casefold() for name in names}):
            raise ValueError("Duplicate or empty archive")
        if sum(info.file_size for info in infos) > MAX_EXPANDED:
            raise ValueError("Unexpectedly large source archive")
        for info in infos:
            if info.orig_filename != info.filename:
                raise ValueError("Archive filename was normalized or truncated")
            _check_archive_path(info.filename)
            mode = info.external_attr >> 16
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("Archive must contain only regular files")
            if stat.S_IMODE(mode) & 0o7000:
                raise ValueError("Archive entries must not have special permission bits")
        folded = {name.casefold() for name in names}
        if any("/".join(name.split("/")[:i]).casefold() in folded
               for name in names for i in range(1, len(name.split("/")))):
            raise ValueError("Archive file/directory collision")
        return {name: bundle.read(name) for name in names}


def _verify_frozen_windows(files: dict[str, bytes], baseline: dict) -> dict:
    manifest_bytes = files.get("App/TEST_BUILD.json", b"")
    if sha(manifest_bytes) != baseline["manifest_sha256"]:
        raise ValueError("Windows baseline manifest changed")
    manifest = json.loads(manifest_bytes)
    if set(files) != set(manifest["files"]) | {"App/TEST_BUILD.json"}:
        raise ValueError("Windows baseline file inventory changed")
    for name, digest in manifest["files"].items():
        if sha(files[name]) != digest:
            raise ValueError(f"Windows file changed: {name}")
    return manifest


def _verify_documentation_windows(files: dict[str, bytes], baseline: dict) -> dict:
    current = json.loads(files["App/TEST_BUILD.json"])
    original = current.get("baseline_manifest")
    if not isinstance(original, dict) or sha(_bytes_json(original)) != baseline["manifest_sha256"]:
        raise ValueError("Documentation revision changed the pinned Windows baseline manifest")
    if (current.get("documentation_revision") != DOCUMENTATION_REVISION
            or current.get("windows_baseline_sha256") != baseline["sha256"]):
        raise ValueError("Invalid Windows documentation revision provenance")
    if (not isinstance(current.get("files"), dict)
            or set(current["files"]) != set(original["files"])
            or set(files) != set(original["files"]) | {"App/TEST_BUILD.json"}):
        raise ValueError("Windows documentation revision changed the file inventory")
    allowed_metadata = {"baseline_manifest", "documentation_revision", "windows_baseline_sha256"}
    if set(current) != set(original) | allowed_metadata:
        raise ValueError("Windows documentation revision changed manifest metadata")
    for key, value in original.items():
        if key not in {"files", "build_id", "created_utc"} and current.get(key) != value:
            raise ValueError(f"Windows documentation revision changed metadata: {key}")
    for name, digest in original["files"].items():
        actual = sha(files[name])
        if name != "App/README.md" and actual != digest:
            raise ValueError(f"Windows file changed outside README: {name}")
        if current["files"][name] != actual:
            raise ValueError(f"Windows documentation checksum mismatch: {name}")
    return current


def _verify_documentation_revision(files: dict[str, bytes], manifest: dict, windows: dict[str, bytes], baseline: dict) -> None:
    if (manifest.get("documentation_revision") != DOCUMENTATION_REVISION
            or manifest.get("documentation_changed_paths") != list(DOCUMENTATION_PATHS)
            or manifest.get("windows_files_unchanged") is not False
            or manifest.get("windows_product_files_unchanged") is not True):
        raise ValueError("Invalid documentation revision flags or allowlist")
    original = manifest.get("documentation_baseline_manifest")
    if not isinstance(original, dict) or sha(_bytes_json(original)) != DOCUMENTATION_BASELINE_MANIFEST_SHA256:
        raise ValueError("Documentation revision changed the pinned combined baseline manifest")
    if set(files) != set(original["files"]) | {MANIFEST}:
        raise ValueError("Documentation revision changed the combined inventory")
    for name, digest in original["files"].items():
        if name not in DOCUMENTATION_PATHS and sha(files[name]) != digest:
            raise ValueError(f"Combined file changed outside documentation allowlist: {name}")
    added_metadata = {"documentation_revision", "documentation_changed_paths", "documentation_baseline_manifest", "windows_product_files_unchanged"}
    if set(manifest) != set(original) | added_metadata:
        raise ValueError("Documentation revision changed combined metadata")
    for key, value in original.items():
        if key not in {"files", "build_id", "created_utc", "windows_files_unchanged"} and manifest.get(key) != value:
            raise ValueError(f"Documentation revision changed combined metadata: {key}")
    current_windows = _verify_documentation_windows(windows, baseline)
    if (current_windows["build_id"] != manifest["build_id"]
            or current_windows["created_utc"] != manifest["created_utc"]
            or not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", manifest["build_id"])):
        raise ValueError("Documentation revision build metadata mismatch")


def verify_package(archive: Path) -> dict:
    files = _read_archive(archive)
    if {name.split("/")[0] for name in files} != {"windows", "mac"}:
        raise ValueError("Combined ZIP must contain exactly windows/ and mac/")
    if MANIFEST not in files:
        raise ValueError("Missing combined package manifest")
    manifest = json.loads(files[MANIFEST])
    if manifest.get("layout") != LAYOUT or not isinstance(manifest.get("files"), dict):
        raise ValueError("Invalid combined package manifest")
    if set(files) != set(manifest["files"]) | {MANIFEST} or MANIFEST in manifest["files"]:
        raise ValueError("Combined package inventory mismatch")
    for name, digest in manifest["files"].items():
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest) or sha(files[name]) != digest:
            raise ValueError(f"Combined checksum mismatch: {name}")
    baseline = _baseline()
    if manifest.get("windows_baseline_sha256") != baseline["sha256"]:
        raise ValueError("Unexpected Windows baseline")
    windows = {name.removeprefix("windows/"): data for name, data in files.items() if name.startswith("windows/")}
    if "documentation_revision" in manifest:
        _verify_documentation_revision(files, manifest, windows, baseline)
    else:
        _verify_frozen_windows(windows, baseline)
    expected_mac = {"mac/" + name for name in windows if name.startswith("App/") and name != "App/TEST_BUILD.json"}
    expected_mac |= set(MAC_OVERLAY.values()) | {MANIFEST}
    if {name for name in files if name.startswith("mac/")} != expected_mac:
        raise ValueError("Unexpected Mac package contents")
    for name, data in windows.items():
        if name.startswith("App/") and name != "App/TEST_BUILD.json" and files["mac/" + name] != data:
            raise ValueError(f"Shared application source differs: {name}")
    with zipfile.ZipFile(archive) as bundle:
        for name in MAC_OVERLAY.values():
            if name.endswith((".sh", ".command")):
                if not files[name].startswith(b"#!/bin/bash\n") or b"\r" in files[name]:
                    raise ValueError("Mac launchers must have LF shebangs")
                if stat.S_IMODE(bundle.getinfo(name).external_attr >> 16) != 0o755:
                    raise ValueError("Mac launcher executable permissions are missing")
    return manifest


def refresh_documentation(root: Path, archive: Path, output_dir: Path, *, build_id: str | None = None) -> Path:
    """Refresh only reviewed documentation in the exact currently approved ZIP."""
    root = root.resolve()
    release = json.loads(_read_source(root, "website/release.json"))
    data = archive.read_bytes()
    if (release.get("layout") != LAYOUT or release.get("filename") != "CUTROOM-1.1-Beta.zip"
            or len(data) != release.get("bytes") or sha(data) != release.get("sha256")):
        raise ValueError("Documentation input is not the exact approved combined release")
    previous = verify_package(archive)
    if previous["build_id"] != release.get("build_id"):
        raise ValueError("Documentation input build ID does not match the approved release")
    original = previous.get("documentation_baseline_manifest", previous)
    if sha(_bytes_json(original)) != DOCUMENTATION_BASELINE_MANIFEST_SHA256:
        raise ValueError("Documentation input does not match the pinned combined baseline manifest")
    files = _read_archive(archive)
    readme = _read_source(root, DOCUMENTATION_SOURCE)
    mac_guide = _read_source(root, "docs/MAC_BETA.md")
    readme.decode("utf-8")
    mac_guide.decode("utf-8")
    stamp = build_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    identifier = f"CUTROOM-{previous['app_version']}-docs-{stamp}"
    if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", identifier):
        raise ValueError("Unsafe documentation build identifier")
    created = datetime.now(timezone.utc).isoformat()
    windows = json.loads(files["windows/App/TEST_BUILD.json"])
    baseline_manifest = windows.get("baseline_manifest", windows)
    windows = dict(baseline_manifest)
    windows.update(build_id=identifier, created_utc=created,
                   documentation_revision=DOCUMENTATION_REVISION,
                   windows_baseline_sha256=_baseline()["sha256"], baseline_manifest=baseline_manifest,
                   files={**baseline_manifest["files"], "App/README.md": sha(readme)})
    files["windows/App/README.md"] = files["mac/App/README.md"] = readme
    files["mac/App/docs/MAC_BETA.md"] = mac_guide
    files["windows/App/TEST_BUILD.json"] = _bytes_json(windows)
    manifest = dict(original)
    manifest.update(build_id=identifier, created_utc=created,
                    documentation_revision=DOCUMENTATION_REVISION,
                    documentation_changed_paths=list(DOCUMENTATION_PATHS),
                    documentation_baseline_manifest=original,
                    windows_files_unchanged=False, windows_product_files_unchanged=True,
                    files={name: sha(content) for name, content in sorted(files.items()) if name != MANIFEST})
    files[MANIFEST] = _bytes_json(manifest)
    target = output_dir / identifier / "CUTROOM-1.1-Beta.zip"
    checksum = target.with_suffix(".zip.sha256")
    if target.exists() or checksum.exists():
        raise FileExistsError("Refusing to overwrite an existing documentation package")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cutroom-docs-") as scratch:
        staged = Path(scratch) / target.name
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(staged, "w") as output:
            output.comment = source.comment
            for info in source.infolist():
                output.writestr(info, files[info.filename])
        verify_package(staged)
        refreshed = staged.read_bytes()
        with target.open("xb") as handle:
            handle.write(refreshed)
        with checksum.open("x", encoding="ascii") as handle:
            handle.write(f"{sha(refreshed)}  {target.name}\n")
    return target


def build_package(root: Path, windows_zip: Path, output_dir: Path, *, build_id: str | None = None) -> Path:
    baseline = _baseline()
    if windows_zip.stat().st_size != baseline["bytes"] or sha(windows_zip.read_bytes()) != baseline["sha256"]:
        raise ValueError("Input is not the approved Windows ZIP")
    verify_windows_package(windows_zip)
    windows = _read_archive(windows_zip)
    original = _verify_frozen_windows(windows, baseline)
    # A future app change needs a deliberate baseline update, never silently
    # publishing an older application under newly changed repository sources.
    for name, data in windows.items():
        relative = name.removeprefix("App/")
        if name.startswith("App/") and (relative in {"server.py", "requirements.txt"}
                                        or relative.startswith(("cutroom/", "web/"))):
            current = _read_source(root.resolve(), relative)
            if current.replace(b"\r\n", b"\n") != data.replace(b"\r\n", b"\n"):
                raise ValueError(f"Application source changed since Windows baseline: {relative}")
    files = {"windows/" + name: data for name, data in windows.items()}
    files.update({"mac/" + name: data for name, data in windows.items() if name.startswith("App/") and name != "App/TEST_BUILD.json"})
    for source, destination in MAC_OVERLAY.items():
        if destination in files:
            raise ValueError("Mac overlay must not replace shared source")
        data = _read_source(root.resolve(), source)
        files[destination] = data.replace(b"\r\n", b"\n") if destination.endswith((".sh", ".command")) else data
    stamp = build_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    identifier = f"CUTROOM-{original['app_version']}-mac-{stamp}"
    if not re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", identifier):
        raise ValueError("Unsafe build identifier")
    manifest = {
        "build_id": identifier, "app_version": original["app_version"],
        "app_version_label": original["app_version_label"], "layout": LAYOUT,
        "kind": "public-source-beta", "created_utc": datetime.now(timezone.utc).isoformat(),
        "windows_baseline_sha256": baseline["sha256"],
        "windows_files_unchanged": True, "mac_manual_install_verified": False,
        "mac_target": "macOS 15+, Apple Silicon and Intel; CPU transcription; unnotarized source launcher",
        "not_included": ["user media", "projects", "logs", "local config", "runtimes", "models"],
        "files": {name: sha(data) for name, data in sorted(files.items())},
    }
    files[MANIFEST] = _bytes_json(manifest)
    archive_dir = output_dir / identifier
    archive_dir.mkdir(parents=True, exist_ok=True)
    target = archive_dir / "CUTROOM-1.1-Beta.zip"
    checksum = target.with_suffix(".zip.sha256")
    if target.exists() or checksum.exists():
        raise FileExistsError("Refusing to overwrite an existing package")
    with tempfile.TemporaryDirectory(prefix="cutroom-combined-") as scratch:
        staged = Path(scratch) / target.name
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100755 if name.endswith((".sh", ".command")) else 0o100644) << 16
                bundle.writestr(info, data)
        verify_package(staged)
        data = staged.read_bytes()
        with target.open("xb") as handle:
            handle.write(data)
        with checksum.open("x", encoding="ascii") as handle:
            handle.write(f"{sha(data)}  {target.name}\n")
    return target


def download_baseline(destination: Path) -> None:
    baseline = _baseline()
    if not baseline["url"].startswith("https://"):
        raise ValueError("Baseline download requires HTTPS")
    request = urllib.request.Request(baseline["url"], headers={
        "User-Agent": "CUTROOM-release-builder/1.1 (+https://github.com/VanoPeradze/cutroom)",
    })
    with urllib.request.urlopen(request, timeout=60) as response:
        if not response.url.startswith("https://"):
            raise ValueError("Baseline redirected away from HTTPS")
        data = response.read(baseline["bytes"] + 1)
    if len(data) != baseline["bytes"] or sha(data) != baseline["sha256"]:
        raise ValueError("Downloaded Windows baseline failed checksum verification")
    with destination.open("xb") as handle:
        handle.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--windows-zip", type=Path)
    parser.add_argument("--download-baseline", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--refresh-docs", type=Path, metavar="APPROVED_COMBINED_ZIP")
    args = parser.parse_args()
    if args.refresh_docs:
        if args.verify or args.windows_zip or args.download_baseline:
            parser.error("--refresh-docs cannot be combined with other actions")
        print(refresh_documentation(ROOT, args.refresh_docs, args.output_dir))
    elif args.verify:
        manifest = verify_package(args.verify)
        preservation = "product unchanged; reviewed documentation refreshed" if "documentation_revision" in manifest else "Windows unchanged"
        print(f"Verified {manifest['build_id']}: {preservation}, identical shared app, two OS folders")
    elif args.windows_zip and not args.download_baseline:
        print(build_package(ROOT, args.windows_zip, args.output_dir))
    elif args.download_baseline and not args.windows_zip:
        with tempfile.TemporaryDirectory(prefix="cutroom-windows-baseline-") as scratch:
            path = Path(scratch) / "windows.zip"
            download_baseline(path)
            print(build_package(ROOT, path, args.output_dir))
    else:
        parser.error("Choose --windows-zip, --download-baseline, --refresh-docs or --verify")


if __name__ == "__main__":
    main()
