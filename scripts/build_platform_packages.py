"""Project a strictly verified combined release into separate Windows/Mac ZIPs.

No application or launcher bytes change. Windows keeps its original manifest;
Mac receives a root-relative inventory with the combined archive's provenance.
The combined ZIP remains available for existing download URLs.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import stat
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.build_test_package import _bytes_json, verify_package as verify_windows
from scripts.build_universal_package import _read_archive, sha, verify_package as verify_combined

PLATFORMS = {"windows": "Windows", "mac": "Mac"}
MANIFEST = "App/TEST_BUILD.json"


def _projection(archive: Path, platform: str, windows_baseline: Path | None = None):
    if platform not in PLATFORMS:
        raise ValueError("Choose Windows or Mac; Linux is source installation only")
    combined = verify_combined(archive, windows_baseline=windows_baseline)
    prefix = platform + "/"
    with zipfile.ZipFile(archive) as source:
        files = {name.removeprefix(prefix): source.read(name)
                 for name in source.namelist() if name.startswith(prefix)}
        modes = {name.removeprefix(prefix): source.getinfo(name).external_attr
                 for name in source.namelist() if name.startswith(prefix)}
    if platform == "mac":
        metadata = {
            "build_id": combined["build_id"], "app_version": combined["app_version"],
            "app_version_label": combined["app_version_label"],
            "kind": combined["kind"], "created_utc": combined["created_utc"],
            "layout": "mac-app-folder-v1", "archive_root": "", "source_directory": "App",
            "launcher": "START CUTROOM.command", "help": "START HERE.html",
            "target": combined["mac_target"],
            "mac_manual_install_verified": combined["mac_manual_install_verified"],
            "combined_archive_sha256": sha(archive.read_bytes()),
            "combined_manifest_sha256": sha(files[MANIFEST]),
            "windows_baseline_sha256": combined["windows_baseline_sha256"],
            "not_included": combined["not_included"],
            "files": {name: sha(data) for name, data in sorted(files.items()) if name != MANIFEST},
        }
        files[MANIFEST] = _bytes_json(metadata)
    return files, modes


def verify_platform(archive: Path, combined: Path, platform: str, *, windows_baseline: Path | None = None) -> dict:
    expected, modes = _projection(combined, platform, windows_baseline)
    actual = _read_archive(archive)
    if set(actual) != set(expected):
        raise ValueError("Platform archive inventory differs from the verified combined release")
    for name, data in expected.items():
        if actual[name] != data:
            raise ValueError(f"Platform payload differs from the verified combined release: {name}")
    with zipfile.ZipFile(archive) as package:
        if package.testzip() is not None:
            raise ValueError("Platform ZIP is corrupt")
        for name, mode in modes.items():
            if package.getinfo(name).external_attr != mode:
                raise ValueError(f"Platform file permissions changed: {name}")
    if platform == "windows":
        return verify_windows(archive)
    metadata = json.loads(actual[MANIFEST])
    if {name.split('/')[0] for name in actual} != {'App', 'START CUTROOM.command', 'START HERE.html'}:
        raise ValueError("Mac package root must contain its launcher, help and App")
    return metadata


def build_packages(archive: Path, output_dir: Path, *, windows_baseline: Path | None = None) -> dict:
    approved = verify_combined(archive, windows_baseline=windows_baseline)
    output_dir.mkdir(parents=True, exist_ok=True)
    filenames = {key: f"CUTROOM-{approved['app_version_label'].replace(' ', '-')}-{label}.zip"
                 for key, label in PLATFORMS.items()}
    if any((output_dir / name).exists() or (output_dir / (name + '.sha256')).exists() for name in filenames.values()):
        raise FileExistsError("Refusing to overwrite an existing platform package")
    result = {"combined_sha256": sha(archive.read_bytes()), "build_id": approved['build_id'], "platforms": {}}
    with tempfile.TemporaryDirectory(prefix="cutroom-platforms-") as temp:
        staged = []
        for platform, filename in filenames.items():
            files, modes = _projection(archive, platform, windows_baseline)
            target = Path(temp) / filename
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as package:
                for name, data in sorted(files.items()):
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = modes[name]
                    package.writestr(info, data)
            verify_platform(target, archive, platform, windows_baseline=windows_baseline)
            payload = target.read_bytes()
            result['platforms'][platform] = {"filename": filename, "bytes": len(payload), "sha256": sha(payload),
                                              "source_files_changed": False, "native_validation": "not_performed_by_packager"}
            staged.append((filename, payload))
        # Validate both products before creating either final output.
        for filename, payload in staged:
            with (output_dir / filename).open('xb') as stream:
                stream.write(payload)
            with (output_dir / (filename + '.sha256')).open('x', encoding='ascii') as stream:
                stream.write(f'{sha(payload)}  {filename}\n')
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--combined', required=True, type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--windows-baseline', type=Path)
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--platform', choices=tuple(PLATFORMS))
    args = parser.parse_args()
    if args.verify:
        if not args.platform:
            parser.error('--verify requires --platform')
        result = verify_platform(args.verify, args.combined, args.platform, windows_baseline=args.windows_baseline)
        print(f"Verified {args.platform}: {len(result['files'])} inventoried files")
    elif args.output_dir:
        print(json.dumps(build_packages(args.combined, args.output_dir, windows_baseline=args.windows_baseline), indent=2))
    else:
        parser.error('Provide --output-dir or --verify')


if __name__ == '__main__':
    main()
