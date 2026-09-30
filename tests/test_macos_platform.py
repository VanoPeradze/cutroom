"""Portable smoke safety checks; actual Mac installation runs only in macOS CI."""
from __future__ import annotations

import importlib.util
import copy
import errno
import hashlib
import json
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
    monkeypatch.setenv("HF_TOKEN", "not-a-real-model-hub-token")
    monkeypatch.setenv("PYTHONPATH", "/other/app")
    env = smoke.isolated_environment(tmp_path)
    assert Path(env["CUTROOM_DATA_DIR"]).is_relative_to(tmp_path)
    assert env["CUTROOM_NO_BROWSER"] == "1"
    assert not {"CUTROOM_PORT", "CUTROOM_FAKE_TRANSCRIPT", "OPENAI_API_KEY", "HF_TOKEN", "PYTHONPATH"} & env.keys()
    assert Path(env["HF_HOME"]).is_relative_to(tmp_path)


def test_smoke_never_installs_on_a_simulated_mac(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.sys, "platform", "win32")
    with pytest.raises(RuntimeError, match="must run on macOS"):
        smoke.install_and_check(tmp_path / "missing.zip")


@pytest.mark.parametrize("historical", [False, True])
def test_smoke_verifies_selected_pin_before_extraction_or_installation(tmp_path, monkeypatch, historical):
    # This is a verifier contract test. Aborting at verification prevents any
    # installation or claim of actual Mac runtime validation on another OS.
    monkeypatch.setattr(smoke.sys, "platform", "darwin")
    metadata = tmp_path / "historical-windows.json" if historical else None
    archive_path = tmp_path / "release.zip"
    def verify(path, *, windows_baseline=None):
        assert path == archive_path and windows_baseline == metadata
        raise ValueError("stop before extraction")
    monkeypatch.setitem(sys.modules, "build_universal_package", SimpleNamespace(verify_package=verify))
    with pytest.raises(ValueError, match="stop before extraction"):
        smoke.install_and_check(archive_path, windows_baseline=metadata)
    assert not any(tmp_path.iterdir())


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


def test_offline_checks_disable_package_and_model_downloads_without_mutating_online_environment():
    online = {"PATH": "/test/runtime/bin", "PIP_NO_INDEX": "0", "HF_HUB_OFFLINE": "0"}
    original = dict(online)
    offline = smoke.offline_environment(online)
    assert online == original
    assert offline["PATH"] == online["PATH"]
    assert all(offline[name] == "1" for name in ("PIP_NO_INDEX", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"))


def test_runtime_signature_detects_added_or_reinstalled_packages(tmp_path):
    runtime = tmp_path / ".venv"
    record = runtime / "lib/python3.12/site-packages/example-1.dist-info/RECORD"
    record.parent.mkdir(parents=True)
    record.write_text("example.py,sha256=old,1\n", encoding="utf-8")
    (runtime / "pyvenv.cfg").write_text("version = 3.12\n", encoding="utf-8")
    before = smoke.installed_runtime_signature(tmp_path)
    assert smoke.installed_runtime_signature(tmp_path) == before
    record.write_text("example.py,sha256=new,2\n", encoding="utf-8")
    assert smoke.installed_runtime_signature(tmp_path) != before
    newer = record.parent.parent / "extra-1.dist-info/RECORD"
    newer.parent.mkdir()
    newer.write_text("extra.py,sha256=more,3\n", encoding="utf-8")
    assert len(smoke.installed_runtime_signature(tmp_path)) == len(before) + 1


@pytest.mark.parametrize("change", ["name", "settings", "revision", "export_bytes"])
def test_restart_snapshot_detects_lost_state_or_changed_exports(tmp_path, monkeypatch, change):
    project = {"id": "project1", "name": "Saved name", "revision": 7, "settings": {"pace": "gentle"},
               "manual": {}, "draft": {}, "sources": {}, "exports": [{"name": "test.mp4"}]}
    output = tmp_path / "test.mp4"
    output.write_bytes(b"the original export")
    monkeypatch.setattr(smoke, "request_json", lambda *args: {"project": copy.deepcopy(project)})
    before = smoke.persisted_project_state("http://127.0.0.1:1", "project1", tmp_path)
    if change == "name":
        project["name"] = "Lost name"
    elif change == "settings":
        project["settings"]["pace"] = "dynamic"
    elif change == "revision":
        project["revision"] = 6
    else:
        output.write_bytes(b"changed export")
    assert smoke.persisted_project_state("http://127.0.0.1:1", "project1", tmp_path) != before


def test_in_process_transcript_cannot_pass_as_an_isolated_worker(tmp_path, monkeypatch):
    import cutroom.transcription
    settings = SimpleNamespace(cache_dir=tmp_path, ai={"whisper_isolate_process": True})
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.delenv("CUTROOM_FAKE_TRANSCRIPT", raising=False)
    monkeypatch.delenv("CUTROOM_TRANSCRIPTION_WORKER", raising=False)
    monkeypatch.setattr(smoke, "run", lambda *args, **kwargs: "")
    monkeypatch.setattr(smoke.sys, "addaudithook", lambda observer: None)
    def in_process(*args, **kwargs):
        assert callable(kwargs["cancel_check"])
        return {"segments": [{"text": "The quick brown fox jumps over the lazy dog"}]}
    monkeypatch.setattr(cutroom.transcription, "transcribe", in_process)
    with pytest.raises(AssertionError, match="isolated worker"):
        smoke.real_cpu_transcription(settings, tmp_path)


@pytest.mark.parametrize("returncode,output,accepted", [
    (1, "private/python: No module named pip", True),
    (0, "pip 25.0 from private/site-packages/pip", False),
    (1, "wrong architecture or broken Python", False),
])
def test_missing_pip_fixture_requires_an_actual_missing_module(tmp_path, monkeypatch, returncode, output, accepted):
    calls = []
    env = {"CUTROOM_DATA_DIR": str(tmp_path / "private data")}
    monkeypatch.setattr(smoke, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    def pip_check(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=returncode, stdout="", stderr=output)
    monkeypatch.setattr(smoke.subprocess, "run", pip_check)
    if accepted:
        smoke.prepare_missing_pip_runtime(tmp_path, env=env, cwd=tmp_path)
    else:
        with pytest.raises(AssertionError):
            smoke.prepare_missing_pip_runtime(tmp_path, env=env, cwd=tmp_path)
    assert calls[0][0] == [sys.executable, "-m", "venv", "--without-pip", str(tmp_path / ".venv")]
    assert calls[1][0] == [str(tmp_path / ".venv/bin/python"), "-m", "pip", "--version"]
    assert all(kwargs["env"] is env and kwargs["cwd"] == tmp_path for _, kwargs in calls)


@pytest.mark.parametrize("repair", [False, True])
@pytest.mark.parametrize("historical", [False, True])
def test_missing_pip_cli_option_reaches_archive_install_only(tmp_path, monkeypatch, repair, historical):
    arguments = ["smoke_macos.py", "--archive", str(tmp_path / "release.zip"), "--transcribe"]
    if repair:
        arguments.append("--repair-missing-pip")
    metadata = tmp_path / "historical-windows.json" if historical else None
    if metadata:
        arguments.extend(["--windows-baseline", str(metadata)])
    monkeypatch.setattr(smoke.sys, "argv", arguments)
    calls = []
    def install(archive, **kwargs):
        calls.append((archive, kwargs))
        return {"status": "test stub"}
    monkeypatch.setattr(smoke, "install_and_check", install)
    assert smoke.main() == 0
    assert calls == [((tmp_path / "release.zip").resolve(), {"transcribe": True, "repair_missing_pip": repair,
                                                           "allow_baseline_restart_failure": False,
                                                           "windows_baseline": metadata})]


def test_missing_pip_cli_rejects_worker_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.sys, "argv", ["smoke_macos.py", "--worker-app", str(tmp_path), "--repair-missing-pip"])
    monkeypatch.setattr(smoke, "worker", lambda *args, **kwargs: pytest.fail("Never repair an already selected runtime"))
    with pytest.raises(SystemExit) as error:
        smoke.main()
    assert error.value.code == 2


def test_restart_exception_requires_the_exact_pinned_archive(tmp_path, monkeypatch):
    pin = tmp_path / "baseline.json"
    pin.write_text(json.dumps({"sha256": hashlib.sha256(b"previous release").hexdigest()}), encoding="utf-8")
    monkeypatch.setattr(smoke, "BASELINE_METADATA", pin)
    package = tmp_path / "previous.zip"
    package.write_bytes(b"previous release")
    smoke.verify_restart_baseline(package)
    package.write_bytes(b"new candidate")
    with pytest.raises(ValueError, match="checksum-pinned previous release"):
        smoke.verify_restart_baseline(package)
    # The worker repeats the guard before importing or launching any app code.
    with pytest.raises(ValueError, match="checksum-pinned previous release"):
        smoke.worker(tmp_path / "unopened-app", transcribe=False, baseline_archive=package)


@pytest.mark.parametrize("returncode,message,network_error,accepted", [
    (1, "exact", errno.ECONNREFUSED, True),
    (0, "exact", errno.ECONNREFUSED, False),
    (1, "wrong port", errno.ECONNREFUSED, False),
    (1, "unrelated error", errno.ECONNREFUSED, False),
    (1, "exact", errno.ETIMEDOUT, False),
    (1, "exact", None, False),
])
def test_known_restart_failure_requires_exact_error_and_no_listener(monkeypatch, returncode, message, network_error, accepted):
    port = 54321
    if message == "exact":
        message = (f"ERROR: CUTROOM cannot start because 127.0.0.1:{port} is already in use or unavailable. "
                   "Close the other program or choose another CUTROOM_PORT.")
    class Listener:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def connect(address, timeout):
        assert address == ("127.0.0.1", port) and timeout == 2
        if network_error is not None:
            raise OSError(network_error, "synthetic socket outcome")
        return Listener()
    monkeypatch.setattr(smoke.socket, "create_connection", connect)
    assert smoke.is_known_baseline_restart_failure(smoke.LauncherStartupError(returncode), message, port) is accepted


def test_baseline_restart_option_is_not_a_worker_bypass(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke.sys, "argv", ["smoke_macos.py", "--worker-app", str(tmp_path),
                                          "--allow-baseline-restart-failure"])
    monkeypatch.setattr(smoke, "worker", lambda *args, **kwargs: pytest.fail("Archive pin must be checked first"))
    with pytest.raises(SystemExit) as error:
        smoke.main()
    assert error.value.code == 2
