from __future__ import annotations

import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("test_package_builder", ROOT / "scripts/build_test_package.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "source"
    for name in (*builder.ROOT_FILES, *builder.DOC_FILES, *builder.IMAGE_FILES, *builder.PACKAGING_FILES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source", encoding="utf-8")
    for name, suffixes in builder.SOURCE_TREES.items():
        (root / name).mkdir(exist_ok=True)
        (root / name / ("fixture" + sorted(suffixes)[0])).write_text("source", encoding="utf-8")
    (root / "cutroom/__init__.py").write_text(
        '__version__ = "1.1-beta"\n__version_label__ = "1.1 Beta"', encoding="utf-8"
    )
    (root / "cutroom/config.py").write_text(
        'DEFAULTS: dict = {"ai": {}, "render": {}}', encoding="utf-8"
    )
    return root


def test_only_source_is_packaged_and_configuration_is_fresh(source):
    private = [
        "config.json", ".runtime-paths.cmd", ".setup-complete", ".verified",
        "validation-report.json", "data/projects/test.json", "data/logs/test.log",
        ".venv/private.py", ".tools/private.py", ".git/config", "dist/old.zip",
        "web/video.mp4", "tests/__pycache__/test.py", "scripts/.env",
        "docs/images/private.png", "packaging/windows/private.txt",
    ]
    for name in private:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("PRIVATE_SENTINEL", encoding="utf-8")
    payload = builder.collect_payload(source)
    assert not any(b"PRIVATE_SENTINEL" in data for data in payload.values())
    assert not (set(private) - {"config.json"}) & payload.keys()
    config = json.loads(payload["config.json"])
    assert config["host"] == "127.0.0.1"
    assert config["data_dir"] == "data"
    assert config["ai"]["ollama_url"] == "http://127.0.0.1:11434"
    assert config["ai"]["download_models_on_setup"] is False


def test_archive_hashes_inventory_and_first_run_files(source, tmp_path):
    target = builder.build_package(source, tmp_path / "out", build_id="unit")
    manifest = builder.verify_package(target)
    assert target.name == "CUTROOM-1.1-beta-unit.zip"
    assert manifest["app_version"] == "1.1-beta"
    assert manifest["app_version_label"] == "1.1 Beta"
    assert manifest["kind"] == "public-source-beta"
    assert manifest["clean_machine_install_verified"] is False
    assert manifest["layout"] == builder.WINDOWS_LAYOUT
    assert manifest["archive_root"] == ""
    assert manifest["source_directory"] == "App"
    assert manifest["launcher"] == "START CUTROOM.bat"
    assert manifest["help"] == "START HERE.html"
    assert "App/START_TESTING.txt" in manifest["files"]
    assert "App/LICENSE" in manifest["files"]
    assert "App/run_windows.bat" in manifest["files"]
    assert "App/PUBLISH.bat" in manifest["files"]
    assert {"App/" + name for name in builder.IMAGE_FILES} <= manifest["files"].keys()
    with zipfile.ZipFile(target) as bundle:
        assert {name.split("/")[0] for name in bundle.namelist()} == {"START CUTROOM.bat", "START HERE.html", "App"}
        assert "App/TEST_BUILD.json" in bundle.namelist()
        for name, data in builder.collect_payload(source).items():
            assert bundle.read("App/" + name) == data
        for name in builder.PACKAGING_FILES:
            assert bundle.read(Path(name).name) == (source / name).read_bytes()
    assert target.with_suffix(".zip.sha256").read_text().split()[0] == builder.hashlib.sha256(target.read_bytes()).hexdigest()


def test_existing_package_is_not_overwritten(source, tmp_path):
    target = builder.build_package(source, tmp_path / "out", build_id="unit")
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        builder.build_package(source, tmp_path / "out", build_id="unit")
    assert target.read_bytes() == original


@pytest.mark.parametrize("build_id", ["../escape", "x/y", "C:\\other"])
def test_unsafe_build_identifiers(source, tmp_path, build_id):
    with pytest.raises(ValueError, match="Unsafe build"):
        builder.build_package(source, tmp_path / "out", build_id=build_id)


def test_missing_required_input_fails_closed(source):
    (source / "LICENSE").unlink()
    with pytest.raises((OSError, ValueError)):
        builder.collect_payload(source)


def test_missing_showcase_capture_fails_closed(source):
    (source / builder.IMAGE_FILES[0]).unlink()
    with pytest.raises((OSError, ValueError)):
        builder.collect_payload(source)


def test_reviewed_showcase_images_remain_binary(source):
    sample = b"\x89PNG\r\n\x1a\n\x00\xff\x80synthetic-test"
    (source / builder.IMAGE_FILES[0]).write_bytes(sample)
    assert builder.collect_payload(source)[builder.IMAGE_FILES[0]] == sample


def test_linked_source_tree_is_rejected(source, monkeypatch):
    real = builder._is_link
    monkeypatch.setattr(builder, "_is_link", lambda path: path == source / "web" or real(path))
    with pytest.raises(ValueError, match="linked"):
        builder.collect_payload(source)


@pytest.mark.parametrize("mode", ["changed", "extra", "traversal"])
def test_modified_or_unsafe_archive_is_rejected(source, tmp_path, mode):
    target = builder.build_package(source, tmp_path / "out", build_id="unit")
    with zipfile.ZipFile(target) as bundle:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    if mode == "changed":
        files["App/server.py"] = b"changed"
    elif mode == "extra":
        files["extra.txt"] = b"extra"
    else:
        files["App/../escape.txt"] = b"extra"
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    with pytest.raises(ValueError):
        builder.verify_package(bad)


def test_extracted_source_can_rebuild_its_windows_envelope(source, tmp_path):
    archive = builder.build_package(source, tmp_path / "out", build_id="first")
    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(archive) as bundle:
        bundle.extractall(extracted)
    rebuilt = builder.build_package(extracted / "App", tmp_path / "out", build_id="rebuilt")
    assert builder.verify_package(rebuilt)["files"] == builder.verify_package(archive)["files"]


def test_legacy_flat_source_package_remains_verifiable(tmp_path):
    prefix = "CUTROOM-1.1-beta-legacy"
    files = {"server.py": b"source", "LICENSE": b"MIT License"}
    manifest = {
        "build_id": prefix,
        "files": {name: builder.hashlib.sha256(data).hexdigest() for name, data in files.items()},
    }
    archive = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(prefix + "/" + name, data)
        bundle.writestr(prefix + "/TEST_BUILD.json", json.dumps(manifest))
    assert builder.verify_package(archive) == manifest


@pytest.mark.parametrize("mode", ["missing-help", "extra-root", "wrong-source-directory", "missing-source-asset",
                                  "changed-launcher", "unsafe-manifest-path", "duplicate-case", "file-directory"])
def test_windows_envelope_rejects_inconsistent_structure(source, tmp_path, mode):
    archive = builder.build_package(source, tmp_path / "out", build_id="unit")
    with zipfile.ZipFile(archive) as bundle:
        files = {name: bundle.read(name) for name in bundle.namelist()}
    manifest_name = "App/TEST_BUILD.json"
    manifest = json.loads(files[manifest_name])
    if mode == "missing-help":
        del files["START HERE.html"]
        del manifest["files"]["START HERE.html"]
    elif mode == "extra-root":
        files["README.md"] = b"unexpected root clutter"
        manifest["files"]["README.md"] = builder.hashlib.sha256(files["README.md"]).hexdigest()
    elif mode == "wrong-source-directory":
        manifest["source_directory"] = "Other"
    elif mode == "missing-source-asset":
        name = "App/" + builder.PACKAGING_FILES[0]
        del files[name]
        del manifest["files"][name]
    elif mode == "changed-launcher":
        files["START CUTROOM.bat"] = b"unexpected command"
        manifest["files"]["START CUTROOM.bat"] = builder.hashlib.sha256(files["START CUTROOM.bat"]).hexdigest()
    elif mode == "unsafe-manifest-path":
        manifest["files"]["../outside.txt"] = "0" * 64
    elif mode == "duplicate-case":
        files["app/server.py"] = files["App/server.py"]
    else:
        files["App"] = b"not a directory"
    files[manifest_name] = json.dumps(manifest).encode()
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    with pytest.raises(ValueError):
        builder.verify_package(bad)


@pytest.mark.parametrize("mode", ["missing", "wrong-build-id", "sibling-prefix", "unsafe-inventory", "wrong-archive-root"])
def test_legacy_manifest_paths_fail_closed(tmp_path, mode):
    prefix = "CUTROOM-1.1-beta-legacy"
    manifest = {"build_id": prefix, "files": {"server.py": builder.hashlib.sha256(b"source").hexdigest()}}
    files = {prefix + "/server.py": b"source"}
    if mode == "wrong-build-id":
        manifest["build_id"] = "CUTROOM-another"
    elif mode == "sibling-prefix":
        files[prefix + "-other/private.txt"] = b"unexpected"
    elif mode == "unsafe-inventory":
        manifest["files"]["../outside.txt"] = "0" * 64
    elif mode == "wrong-archive-root":
        manifest["archive_root"] = "CUTROOM-another"
    if mode != "missing":
        files[prefix + "/TEST_BUILD.json"] = json.dumps(manifest).encode()
    archive = tmp_path / "bad-legacy.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    with pytest.raises(ValueError):
        builder.verify_package(archive)


def test_real_payload_has_no_setup_markers_or_user_paths():
    payload = builder.collect_payload(ROOT)
    assert not any(name.startswith(("data/", ".venv/", ".tools/")) for name in payload)
    assert ".setup-complete" not in payload
    assert ".runtime-paths.cmd" not in payload
    for name in ("README.md", "README_HE.md", "config.json"):
        assert b"C:\\Users\\" not in payload[name]
