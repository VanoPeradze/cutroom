"""The combined download must preserve every byte of the approved Windows package."""
import io
import json
import stat
import sys
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


@pytest.mark.parametrize("response_kind", ["approved", "corrupt", "oversized", "insecure_redirect"])
def test_baseline_download_identifies_builder_without_relaxing_verification(package_source, tmp_path, monkeypatch, response_kind):
    approved = package_source[1].read_bytes()
    data = {"corrupt": b"x" + approved[1:], "oversized": approved + b"x"}.get(response_kind, approved)
    response = io.BytesIO(data)
    response.url = "http://example.invalid/frozen.zip" if response_kind == "insecure_redirect" else combined._baseline()["url"]
    def fetch(request, timeout):
        assert request.full_url == combined._baseline()["url"]
        assert request.get_header("User-agent").startswith("CUTROOM-release-builder/")
        assert timeout == 60
        return response
    monkeypatch.setattr(combined.urllib.request, "urlopen", fetch)
    destination = tmp_path / "download.zip"
    if response_kind == "approved":
        combined.download_baseline(destination)
        assert destination.read_bytes() == approved
    else:
        with pytest.raises(ValueError, match="checksum|HTTPS"):
            combined.download_baseline(destination)
        assert not destination.exists()


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


def test_mac_overlay_payload_is_identical_from_crlf_and_lf_checkouts(package_source):
    root, baseline, out = package_source
    content = "#!/bin/bash\n# UTF-8: caf\u00e9\nexit 0\n".encode("utf-8")
    for source in combined.MAC_OVERLAY:
        (root / source).write_bytes(content.replace(b"\n", b"\r\n"))
    crlf = combined.build_package(root, baseline, out, build_id="crlf")
    for source in combined.MAC_OVERLAY:
        (root / source).write_bytes(content)
    lf = combined.build_package(root, baseline, out, build_id="lf")
    with zipfile.ZipFile(crlf) as first, zipfile.ZipFile(lf) as second, zipfile.ZipFile(baseline) as windows:
        assert first.namelist() == second.namelist()
        for name in first.namelist():
            if name != combined.MANIFEST:
                assert first.read(name) == second.read(name), name
                assert first.getinfo(name).external_attr == second.getinfo(name).external_attr
        for name in combined.MAC_OVERLAY.values():
            assert first.read(name) == content
        for name in windows.namelist():
            assert first.read("windows/" + name) == windows.read(name)
    assert combined.verify_package(crlf)["files"] == combined.verify_package(lf)["files"]


def test_refuses_wrong_windows_archive(package_source):
    root, baseline, out = package_source
    baseline.write_bytes(b"different Windows build")
    with pytest.raises(ValueError, match="approved Windows"):
        build(package_source)


def test_changed_shared_source_requires_an_intentional_baseline_update(package_source):
    (package_source[0] / "server.py").write_text("new application source")
    with pytest.raises(ValueError, match="Application source changed"):
        build(package_source)


def test_historical_archive_requires_its_explicit_exact_windows_pin(package_source, tmp_path, monkeypatch):
    archive = build(package_source)
    historical = dict(combined._baseline())
    metadata = tmp_path / "historical-windows.json"
    metadata.write_bytes(legacy._bytes_json(historical))
    monkeypatch.setattr(combined, "_baseline", lambda: {**historical, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="Windows baseline"):
        combined.verify_package(archive)
    assert combined.verify_package(archive, windows_baseline=metadata)["windows_files_unchanged"] is True
    for key in ("sha256", "manifest_sha256"):
        metadata.write_bytes(legacy._bytes_json({**historical, key: "0" * 64}))
        with pytest.raises(ValueError, match="baseline"):
            combined.verify_package(archive, windows_baseline=metadata)


@pytest.mark.parametrize("build_arguments", [["--download-baseline"], ["--windows-zip", "old.zip"]])
def test_historical_pin_cannot_override_new_candidate_construction(monkeypatch, build_arguments):
    monkeypatch.setattr(sys, "argv", ["build_universal_package.py", "--windows-baseline", "old.json", *build_arguments])
    monkeypatch.setattr(combined, "download_baseline", lambda *args: pytest.fail("Do not download a historical candidate"))
    monkeypatch.setattr(combined, "build_package", lambda *args: pytest.fail("Do not build from a historical override"))
    with pytest.raises(SystemExit) as error:
        combined.main()
    assert error.value.code == 2


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


@pytest.fixture
def documentation_source(package_source, monkeypatch):
    root, _, out = package_source
    archive = build(package_source)
    previous = combined.verify_package(archive)
    monkeypatch.setattr(combined, "DOCUMENTATION_BASELINE_MANIFEST_SHA256", combined.sha(legacy._bytes_json(previous)))
    release = root / "website/release.json"
    release.parent.mkdir()
    release.write_bytes(legacy._bytes_json({
        "layout": combined.LAYOUT, "filename": archive.name, "bytes": archive.stat().st_size,
        "sha256": combined.sha(archive.read_bytes()), "build_id": previous["build_id"],
    }))
    readme = root / combined.DOCUMENTATION_SOURCE
    readme.parent.mkdir(parents=True)
    readme.write_text("# Platform README\nWindows, macOS and Linux source; local guide ../START%20HERE.html\n")
    (root / "docs/MAC_BETA.md").write_text("# Mac beta\nProduct files preserved; README and build metadata refreshed.\n")
    return root, archive, out


def refresh(fixture, build_id="updated"):
    return combined.refresh_documentation(*fixture, build_id=build_id)


def test_historical_documentation_refresh_keeps_old_pins_after_product_rebaseline(documentation_source, tmp_path, monkeypatch):
    root, original, out = documentation_source
    historical = dict(combined._baseline())
    metadata = tmp_path / "historical-windows.json"
    metadata.write_bytes(legacy._bytes_json(historical))
    monkeypatch.setattr(combined, "_baseline", lambda: {**historical, "sha256": "0" * 64})
    with pytest.raises(ValueError, match="Windows baseline"):
        combined.refresh_documentation(root, original, out, build_id="historical")
    refreshed = combined.refresh_documentation(root, original, out, build_id="historical", windows_baseline=metadata)
    assert combined.verify_package(refreshed, windows_baseline=metadata)["documentation_revision"] == combined.DOCUMENTATION_REVISION
    with pytest.raises(ValueError, match="Windows baseline"):
        combined.verify_package(refreshed)


def rehash_current_manifests(files):
    """Model an attacker who also updates every current checksum honestly."""
    name = "windows/App/TEST_BUILD.json"
    info, data = files[name]
    manifest = json.loads(data)
    manifest["files"] = {key.removeprefix("windows/"): combined.sha(value)
                         for key, (_, value) in files.items() if key.startswith("windows/") and key != name}
    files[name] = (info, legacy._bytes_json(manifest))
    info, data = files[combined.MANIFEST]
    manifest = json.loads(data)
    manifest["files"] = {key: combined.sha(value) for key, (_, value) in files.items() if key != combined.MANIFEST}
    files[combined.MANIFEST] = (info, legacy._bytes_json(manifest))


def test_documentation_refresh_preserves_exact_inventory_payloads_and_zip_metadata(documentation_source):
    root, original, _ = documentation_source
    archive = refresh(documentation_source)
    manifest = combined.verify_package(archive)
    assert manifest["windows_files_unchanged"] is False
    assert manifest["windows_product_files_unchanged"] is True
    assert manifest["app_version"] == "1.1-beta"
    assert combined.verify_package(original)["windows_files_unchanged"] is True
    metadata = ("date_time", "compress_type", "comment", "extra", "create_system", "create_version",
                "extract_version", "internal_attr", "external_attr", "flag_bits")
    with zipfile.ZipFile(original) as before, zipfile.ZipFile(archive) as after:
        assert before.namelist() == after.namelist()
        changed = {name for name in before.namelist() if before.read(name) != after.read(name)}
        assert changed == set(combined.DOCUMENTATION_PATHS)
        for name in before.namelist():
            assert tuple(getattr(before.getinfo(name), key) for key in metadata) == tuple(getattr(after.getinfo(name), key) for key in metadata)
        assert after.read("windows/App/README.md") == after.read("mac/App/README.md") == (root / combined.DOCUMENTATION_SOURCE).read_bytes()
        assert after.read("mac/App/docs/MAC_BETA.md") == (root / "docs/MAC_BETA.md").read_bytes()
        windows = json.loads(after.read("windows/App/TEST_BUILD.json"))
        assert combined.sha(legacy._bytes_json(windows["baseline_manifest"])) == combined._baseline()["manifest_sha256"]
    assert archive.with_suffix(".zip.sha256").read_text().split()[0] == combined.sha(archive.read_bytes())


@pytest.mark.parametrize("target", [
    "windows/App/server.py", "mac/App/server.py", "windows/START CUTROOM.bat",
    "mac/START CUTROOM.command", "mac/App/preflight_macos.py", "windows/App/config.json",
    "mac/App/config.json", "windows/App/requirements.txt", "windows/App/docs/MODELS.md",
])
def test_refreshed_self_consistent_tampering_outside_allowlist_is_rejected(documentation_source, tmp_path, target):
    archive = refresh(documentation_source)
    def change(files):
        files[target] = (files[target][0], b"changed despite rewritten current manifests")
        rehash_current_manifests(files)
    with pytest.raises(ValueError, match="outside documentation allowlist"):
        combined.verify_package(rewrite(archive, tmp_path / "tampered.zip", change))


@pytest.mark.parametrize("kind", ["windows_baseline", "combined_baseline", "flag", "revision", "allowlist", "version", "inventory"])
def test_documentation_refresh_provenance_flags_version_and_inventory_fail_closed(documentation_source, tmp_path, kind):
    archive = refresh(documentation_source)
    def change(files):
        name = "windows/App/TEST_BUILD.json" if kind == "windows_baseline" else combined.MANIFEST
        info, data = files[name]
        manifest = json.loads(data)
        if kind == "windows_baseline":
            manifest["baseline_manifest"]["files"]["App/server.py"] = combined.sha(b"changed")
        elif kind == "combined_baseline":
            manifest["documentation_baseline_manifest"]["files"]["mac/START CUTROOM.command"] = combined.sha(b"changed")
        elif kind == "flag":
            manifest["windows_files_unchanged"] = True
        elif kind == "revision":
            manifest["documentation_revision"] = "allow-all-files"
        elif kind == "allowlist":
            manifest["documentation_changed_paths"].append("windows/App/server.py")
        elif kind == "version":
            manifest["app_version"] = "9.0"
        else:
            files["windows/App/new.py"] = (zipfile.ZipInfo("windows/App/new.py"), b"new executable")
        files[name] = (info, legacy._bytes_json(manifest))
        rehash_current_manifests(files)
    with pytest.raises(ValueError, match="baseline|flags|metadata|inventory"):
        combined.verify_package(rewrite(archive, tmp_path / "bad-provenance.zip", change))


@pytest.mark.parametrize("kind", ["bytes", "sha256", "build_id"])
def test_documentation_refresh_requires_exact_current_release(documentation_source, kind):
    root, _, out = documentation_source
    path = root / "website/release.json"
    release = json.loads(path.read_bytes())
    release[kind] = {"bytes": 1, "sha256": "0" * 64, "build_id": "CUTROOM-unapproved"}[kind]
    path.write_bytes(legacy._bytes_json(release))
    with pytest.raises(ValueError, match="approved"):
        refresh(documentation_source)
    assert not (out / "CUTROOM-1.1-beta-docs-updated").exists()


def test_documentation_refresh_missing_linked_source_or_existing_output_fail_closed(documentation_source, monkeypatch):
    root, _, _ = documentation_source
    original = legacy._is_link
    monkeypatch.setattr(legacy, "_is_link", lambda path: path == root / combined.DOCUMENTATION_SOURCE or original(path))
    with pytest.raises(ValueError, match="linked"):
        refresh(documentation_source)
    monkeypatch.setattr(legacy, "_is_link", original)
    archive = refresh(documentation_source)
    with pytest.raises(FileExistsError):
        refresh(documentation_source)
    (root / combined.DOCUMENTATION_SOURCE).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        refresh(documentation_source, build_id="missing")
    combined.verify_package(archive)
