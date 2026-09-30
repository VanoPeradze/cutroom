"""Portable smoke safety checks; actual Mac installation runs only in macOS CI."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("macos_smoke", ROOT / "scripts" / "smoke_macos.py")
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def archive(tmp_path, extra=None):
    path = tmp_path / "package.zip"
    files = {f"mac/App/{name}": b"test" for name in (
        "server.py", "config.json", "setup_macos.sh", "run_macos.sh", "preflight_macos.py")}
    files["mac/START CUTROOM.command"] = b"#!/bin/bash\n"
    files["windows/private.txt"] = b"DO NOT EXTRACT"
    if extra:
        files.update(extra)
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in files.items():
            item = zipfile.ZipInfo(name)
            # ZipInfo normalizes backslashes on Windows; preserve adversarial input.
            item.filename = name
            item.create_system = 3
            item.external_attr = (stat.S_IFREG | (0o755 if name.endswith((".sh", ".command")) else 0o644)) << 16
            bundle.writestr(item, data)
    return path


def test_smoke_extracts_only_mac_into_fresh_unicode_folder(tmp_path):
    destination = tmp_path / "new extraction שלום"
    app = smoke.extract_mac(archive(tmp_path), destination)
    assert app == destination / "mac" / "App"
    assert (app / "server.py").read_bytes() == b"test"
    assert not (destination / "windows").exists()
    if sys.platform != "win32":
        assert (app / "run_macos.sh").stat().st_mode & stat.S_IXUSR


@pytest.mark.parametrize("unsafe", ["mac/../escape", "mac/App/../../escape", "mac/App\\escape", "mac/App/C:escape", "mac/App/./escape"])
def test_smoke_rejects_unsafe_entries_before_extraction(tmp_path, unsafe):
    destination = tmp_path / "new"
    with pytest.raises(ValueError, match="Unsafe Mac archive"):
        smoke.extract_mac(archive(tmp_path, {unsafe: b"bad"}), destination)
    assert not destination.exists()


def test_smoke_refuses_to_overwrite_existing_extraction(tmp_path):
    destination = tmp_path / "existing"
    target = destination / "mac" / "App" / "server.py"
    target.parent.mkdir(parents=True)
    target.write_text("existing user source", encoding="utf-8")
    with pytest.raises(FileExistsError):
        smoke.extract_mac(archive(tmp_path), destination)
    assert target.read_text(encoding="utf-8") == "existing user source"


def test_smoke_uses_temporary_data_and_drops_inherited_runtime_and_cloud_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", "/real/user/projects")
    monkeypatch.setenv("CUTROOM_PORT", "8765")
    monkeypatch.setenv("CUTROOM_FAKE_TRANSCRIPT", "fake")
    monkeypatch.setenv("OPENAI_API_KEY", "not-a-real-key")
    monkeypatch.setenv("PYTHONPATH", "/other/app")
    env = smoke.isolated_environment(tmp_path)
    assert Path(env["CUTROOM_DATA_DIR"]).is_relative_to(tmp_path)
    assert env["CUTROOM_NO_BROWSER"] == "1"
    assert not {"CUTROOM_PORT", "CUTROOM_FAKE_TRANSCRIPT", "OPENAI_API_KEY", "PYTHONPATH"} & env.keys()
    assert Path(env["HF_HOME"]).is_relative_to(tmp_path)


def test_smoke_never_installs_on_a_simulated_mac(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="must run on macOS"):
        smoke.install_and_check(tmp_path / "missing.zip")


def test_server_identity_is_verified_before_any_project_requests(monkeypatch):
    seen = []
    def response(base, path):
        seen.append(path)
        return {"service": "cutroom", "instance_id": "somebody-elses-projects"}
    monkeypatch.setattr(smoke, "request_json", response)
    with pytest.raises(RuntimeError, match="another server"):
        smoke.wait_for_own_server(SimpleNamespace(poll=lambda: None), "http://127.0.0.1:54321", "our-test-data")
    assert seen == ["/api/instance"]


def test_server_exit_is_reported_without_using_existing_server(monkeypatch):
    monkeypatch.setattr(smoke, "request_json", lambda *args: pytest.fail("Do not call an unrelated service"))
    with pytest.raises(RuntimeError, match="exited before startup"):
        smoke.wait_for_own_server(SimpleNamespace(poll=lambda: 1, returncode=1), "http://127.0.0.1:54321", "ours")
