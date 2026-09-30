"""The combined download must preserve every byte of the approved Windows package."""
import json
import stat
import zipfile
from pathlib import Path

import pytest

from scripts import build_test_package as legacy
from scripts import build_universal_package as combined


@pytest.fixture
def package_source(tmp_path, monkeypatch):
    root = tmp_path / "source"
    for name in (*legacy.ROOT_FILES, *legacy.SUPPORT_FILES, *legacy.DOC_FILES, *legacy.IMAGE_FILES, *legacy.PACKAGING_FILES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source", encoding="utf-8")
    for name in legacy.SOURCE_TREES:
        (root / name).mkdir(exist_ok=True)
    (root / "cutroom/__init__.py").write_text('__version__ = "1.1-beta"\n__version_label__ = "1.1 Beta"')
    (root / "cutroom/config.py").write_text('DEFAULTS = {"ai": {}}')
    baseline_zip = legacy.build_package(root, tmp_path / "baseline", build_id="frozen")
    with zipfile.ZipFile(baseline_zip) as archive:
        manifest_hash = combined.sha(archive.read("App/TEST_BUILD.json"))
    baseline = {"bytes": baseline_zip.stat().st_size, "sha256": combined.sha(baseline_zip.read_bytes()),
                "manifest_sha256": manifest_hash, "url": "https://example.invalid/frozen.zip"}
    monkeypatch.setattr(combined, "_baseline", lambda: baseline)
    for name in combined.MAC_OVERLAY:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"#!/bin/bash\r\nexit 0\r\n" if name.endswith((".sh", ".command")) else b"Mac-only addition")
    return root, baseline_zip, tmp_path / "out"


def build(fixture, **kwargs):
    return combined.build_package(*fixture, build_id="test", **kwargs)


def rewrite(archive, target, change):
    with zipfile.ZipFile(archive) as bundle:
        files = {info.filename: (info, bundle.read(info.filename)) for info in bundle.infolist()}
    change(files)
    with zipfile.ZipFile(target, "w") as bundle:
        for name, (info, data) in files.items():
            bundle.writestr(info, data)
    return target


def test_two_folders_and_exact_windows_preservation(package_source):
    archive = build(package_source)
    manifest = combined.verify_package(archive)
    assert manifest["mac_manual_install_verified"] is False
    assert manifest["windows_files_unchanged"] is True
    with zipfile.ZipFile(archive) as output, zipfile.ZipFile(package_source[1]) as old:
        assert {name.split("/")[0] for name in output.namelist()} == {"windows", "mac"}
        for name in old.namelist():
            assert output.read("windows/" + name) == old.read(name)
        for source, name in combined.MAC_OVERLAY.items():
            assert name in output.namelist()
            if name.endswith((".sh", ".command")):
                assert b"\r" not in output.read(name)
                assert stat.S_IMODE(output.getinfo(name).external_attr >> 16) == 0o755
    assert archive.with_suffix(".zip.sha256").read_text().split()[0] == combined.sha(archive.read_bytes())


def test_refuses_wrong_windows_archive(package_source):
    root, baseline, out = package_source
    baseline.write_bytes(b"different Windows build")
    with pytest.raises(ValueError, match="approved Windows"):
        build(package_source)


def test_changed_shared_source_requires_an_intentional_baseline_update(package_source):
    (package_source[0] / "server.py").write_text("new application source")
    with pytest.raises(ValueError, match="Application source changed"):
        build(package_source)


def test_missing_mac_input_or_existing_output_fail_closed(package_source):
    archive = build(package_source)
    with pytest.raises(FileExistsError):
        build(package_source)
    (package_source[0] / "packaging/mac/run_macos.sh").unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        combined.build_package(*package_source, build_id="missing")
    combined.verify_package(archive)


@pytest.mark.parametrize("target", ["windows/App/server.py", "mac/App/server.py", "mac/START CUTROOM.command"])
def test_tampering_is_rejected(package_source, tmp_path, target):
    archive = build(package_source)
    def change(files):
        info, data = files[target]
        files[target] = (info, b"changed")
    with pytest.raises(ValueError, match="checksum"):
        combined.verify_package(rewrite(archive, tmp_path / "bad.zip", change))


def test_new_self_consistent_manifest_cannot_change_windows(package_source, tmp_path):
    archive = build(package_source)
    def change(files):
        name = "windows/App/server.py"
        files[name] = (files[name][0], b"changed")
        info, data = files[combined.MANIFEST]
        manifest = json.loads(data)
        manifest["files"][name] = combined.sha(b"changed")
        files[combined.MANIFEST] = (info, json.dumps(manifest).encode())
    with pytest.raises(ValueError, match="Windows file changed"):
        combined.verify_package(rewrite(archive, tmp_path / "bad.zip", change))


def test_missing_executable_permissions_rejected(package_source, tmp_path):
    archive = build(package_source)
    def change(files):
        files["mac/START CUTROOM.command"][0].external_attr = 0o100644 << 16
    with pytest.raises(ValueError, match="executable permissions"):
        combined.verify_package(rewrite(archive, tmp_path / "bad.zip", change))


@pytest.mark.parametrize("target", ["mac/START CUTROOM.command", "windows/App/server.py"])
@pytest.mark.parametrize("special_mode", [0o4000, 0o2000, 0o1000])
def test_special_permission_bits_rejected(package_source, tmp_path, target, special_mode):
    archive = build(package_source)
    def change(files):
        info = files[target][0]
        info.external_attr |= special_mode << 16
    with pytest.raises(ValueError, match="special permission"):
        combined.verify_package(rewrite(archive, tmp_path / "bad-mode.zip", change))


@pytest.mark.parametrize("raw_name", ["mac/App/preflight_macos.py\x00ignored", "mac/App\\preflight_macos.py"])
def test_raw_archive_names_cannot_hide_behind_zipfile_normalization(package_source, tmp_path, raw_name):
    archive = build(package_source)
    def change(files):
        # Assign after constructing ZipInfo so the writer preserves malformed
        # names that ZipInfo normalizes/truncates when the archive is read.
        files["mac/App/preflight_macos.py"][0].filename = raw_name
    with pytest.raises(ValueError, match="normalized|truncated|Unsafe archive path"):
        combined.verify_package(rewrite(archive, tmp_path / "bad-raw-name.zip", change))


@pytest.mark.parametrize("name", ["windows/../escape", "MAC/App/evil.py", "other/file", "/escape", "mac/App/server.py/child"])
def test_invalid_paths_and_extra_roots_rejected(package_source, tmp_path, name):
    archive = build(package_source)
    def change(files):
        files[name] = (zipfile.ZipInfo(name), b"extra")
    with pytest.raises(ValueError):
        combined.verify_package(rewrite(archive, tmp_path / "bad.zip", change))


def test_linked_mac_input_rejected(package_source, monkeypatch):
    from scripts import build_test_package
    original = build_test_package._is_link
    monkeypatch.setattr(build_test_package, "_is_link", lambda path: path.name == "run_macos.sh" or original(path))
    with pytest.raises(ValueError, match="linked"):
        build(package_source)
