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
    for name in (*builder.ROOT_FILES, *builder.DOC_FILES, *builder.IMAGE_FILES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("source", encoding="utf-8")
    for name in builder.SOURCE_TREES:
        (root / name).mkdir(exist_ok=True)
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
        "docs/images/private.png",
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
    assert "START_TESTING.txt" in manifest["files"]
    assert "LICENSE" in manifest["files"]
    assert "run_windows.bat" in manifest["files"]
    assert "PUBLISH.bat" in manifest["files"]
    assert set(builder.IMAGE_FILES) <= manifest["files"].keys()
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
    prefix = next(iter(files)).split("/")[0]
    if mode == "changed":
        files[prefix + "/server.py"] = b"changed"
    elif mode == "extra":
        files[prefix + "/extra.txt"] = b"extra"
    else:
        files[prefix + "/../escape.txt"] = b"extra"
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(name, data)
    with pytest.raises(ValueError):
        builder.verify_package(bad)


def test_real_payload_has_no_setup_markers_or_user_paths():
    payload = builder.collect_payload(ROOT)
    assert not any(name.startswith(("data/", ".venv/", ".tools/")) for name in payload)
    assert ".setup-complete" not in payload
    assert ".runtime-paths.cmd" not in payload
    for name in ("README.md", "README_HE.md", "config.json"):
        assert b"C:\\Users\\" not in payload[name]
