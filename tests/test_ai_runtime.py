from __future__ import annotations

import http.client
import io
import json
import threading
import urllib.error
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cutroom import ai_runtime

REAL_RESOLVER = ai_runtime.resolve_ollama_executable


@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(ai={"enabled": True, "ollama_url": "http://127.0.0.1:11434"},
                           root=tmp_path, data_dir=tmp_path / "data")


@pytest.fixture(autouse=True)
def no_real_runtime(monkeypatch):
    monkeypatch.setattr(ai_runtime.subprocess, "Popen", Mock(side_effect=AssertionError("Real launch forbidden")))
    monkeypatch.setattr(ai_runtime.urllib.request, "build_opener", Mock(side_effect=AssertionError("Real network forbidden")))
    monkeypatch.setattr(ai_runtime, "resolve_ollama_executable", lambda: None)


@pytest.fixture
def process(monkeypatch):
    child = Mock()
    child.poll.return_value = None
    launch = Mock(return_value=child)
    monkeypatch.setattr(ai_runtime.subprocess, "Popen", launch)
    monkeypatch.setattr(ai_runtime, "resolve_ollama_executable", lambda: "C:/Ollama/ollama.exe")
    return child, launch


def probe(monkeypatch, runtime, values):
    check = Mock(side_effect=values)
    monkeypatch.setattr(runtime, "_probe", check)
    return check


def test_existing_daemon_is_used_without_start_or_model_inference(settings, monkeypatch):
    runtime = ai_runtime.AIRuntime(settings)
    check = probe(monkeypatch, runtime, [["qwen3.5:4b"]])
    status = runtime.ensure_ready()
    assert status["available"] and status["state"] == "ready"
    assert status["models"] == ["qwen3.5:4b"]
    assert not status["managed"]
    assert check.call_count == 1
    status["models"].clear()
    assert runtime.snapshot()["models"] == ["qwen3.5:4b"]


def test_disabled_ai_never_probes_or_starts(settings):
    settings.ai["enabled"] = False
    runtime = ai_runtime.AIRuntime(settings)
    assert runtime.snapshot()["state"] == "disabled"
    assert runtime.ensure_ready()["error_code"] == "disabled"


def test_auto_start_disabled_still_checks_existing_daemon(settings, monkeypatch):
    settings.ai["auto_start_ollama"] = False
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None, []])
    assert runtime.ensure_ready()["error_code"] == "auto_start_disabled"
    assert runtime.ensure_ready()["available"]


@pytest.mark.parametrize("url", [
    "http://192.168.1.20:11434", "https://127.0.0.1:11434", "http://localhost:11434/ollama",
    "http://localhost.example.com:11434", "http://0.0.0.0:11434", "http://[::]:11434",
])
def test_unavailable_nonlocal_or_nonroot_address_is_never_launched(settings, monkeypatch, url):
    settings.ai["ollama_url"] = url
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None])
    assert runtime.ensure_ready()["error_code"] == "nonlocal_endpoint"


@pytest.mark.parametrize("url", [
    "ftp://localhost:11434", "http://user:secret@localhost:11434", "http://localhost:0",
    "http://localhost:65536", "http://localhost:11434?server=remote", "http://localhost:11434#fragment",
    "http://local\nhost:11434", "http:///api", "not an address",
])
def test_invalid_address_is_never_requested_and_credentials_not_exposed(settings, url):
    settings.ai["ollama_url"] = url
    runtime = ai_runtime.AIRuntime(settings)
    status = runtime.ensure_ready()
    assert status["error_code"] == "invalid_endpoint"
    assert "secret" not in str(status)


@pytest.mark.parametrize("url,host", [
    ("http://127.2.3.4:11435", "http://127.2.3.4:11435"),
    ("http://localhost:11434/", "http://localhost:11434"),
    ("http://[::1]:11435", "http://[::1]:11435"),
    ("http://localhost", "http://localhost:80"),
])
def test_local_launch_is_hidden_and_uses_configured_endpoint(settings, monkeypatch, process, url, host):
    settings.ai["ollama_url"] = url
    monkeypatch.setenv("OLLAMA_HOST", "http://other-server:7777")
    monkeypatch.setenv("OLLAMA_NO_CLOUD", "0")
    monkeypatch.delenv("OLLAMA_KEEP_ALIVE", raising=False)
    child, launch = process
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None, []])
    status = runtime.ensure_ready()
    assert status["available"] and status["managed"]
    args, kwargs = launch.call_args
    assert args[0] == ["C:/Ollama/ollama.exe", "serve"]
    assert kwargs["env"]["OLLAMA_HOST"] == host
    assert kwargs["env"]["OLLAMA_NO_CLOUD"] == "1"
    assert kwargs["env"]["OLLAMA_KEEP_ALIVE"] == "2m"
    assert ai_runtime.os.environ["OLLAMA_HOST"] == "http://other-server:7777"
    assert kwargs["stdin"] == ai_runtime.subprocess.DEVNULL
    assert kwargs["stderr"] == ai_runtime.subprocess.STDOUT
    if ai_runtime.os.name == "nt":
        assert kwargs["creationflags"] & ai_runtime.subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs["start_new_session"]
    assert kwargs["stdout"].name.endswith("ollama-runtime.log")
    child.terminate.assert_not_called()
    child.kill.assert_not_called()


def test_missing_executable_requires_retry_but_can_recover(settings, monkeypatch, process):
    child, launch = process
    monkeypatch.setattr(ai_runtime, "resolve_ollama_executable", lambda: None)
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None, None, None, []])
    assert runtime.ensure_ready()["error_code"] == "not_installed"
    monkeypatch.setattr(ai_runtime, "resolve_ollama_executable", lambda: "ollama")
    assert runtime.ensure_ready()["error_code"] == "not_installed"
    launch.assert_not_called()
    assert runtime.ensure_ready(retry=True)["available"]
    assert launch.call_count == 1


def test_start_exception_is_actionable_and_not_repeated(settings, monkeypatch, process):
    _, launch = process
    launch.side_effect = OSError("denied")
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None, None])
    assert runtime.ensure_ready()["error_code"] == "start_failed"
    assert runtime.ensure_ready()["error_code"] == "start_failed"
    assert launch.call_count == 1


def test_exited_child_does_not_cause_automatic_restart_loop(settings, monkeypatch, process):
    child, launch = process
    child.poll.return_value = 1
    runtime = ai_runtime.AIRuntime(settings)
    probe(monkeypatch, runtime, [None, None, None, None, None])
    assert runtime.ensure_ready()["error_code"] == "process_exited"
    assert runtime.ensure_ready()["error_code"] == "process_exited"
    assert launch.call_count == 1
    assert runtime.ensure_ready(retry=True)["error_code"] == "process_exited"
    assert launch.call_count == 2


def test_timeout_is_bounded_and_retry_reuses_live_child(settings, monkeypatch, process):
    _, launch = process
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(ai_runtime.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(ai_runtime.time, "sleep", lambda duration: setattr(clock, "now", clock.now + duration))
    runtime = ai_runtime.AIRuntime(settings)
    monkeypatch.setattr(runtime, "_probe", lambda *args: None)
    assert runtime.ensure_ready(timeout=1)["error_code"] == "startup_timeout"
    assert clock.now == 1.0
    assert runtime.ensure_ready(timeout=1, retry=True)["error_code"] == "startup_timeout"
    assert clock.now == 2.0
    assert launch.call_count == 1
    probe(monkeypatch, runtime, [[]])
    assert runtime.ensure_ready(retry=True)["available"]
    assert launch.call_count == 1


def test_simultaneous_callers_share_single_start(settings, monkeypatch, process):
    _, launch = process
    started = threading.Event()
    release = threading.Event()
    calls = 0
    runtime = ai_runtime.AIRuntime(settings)

    def health(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            assert release.wait(2)
            return None
        return []

    monkeypatch.setattr(runtime, "_probe", health)
    outputs = []
    first = threading.Thread(target=lambda: outputs.append(runtime.ensure_ready()))
    second = threading.Thread(target=lambda: outputs.append(runtime.ensure_ready()))
    first.start()
    assert started.wait(2)
    second.start()
    # Snapshot is nonblocking even while the first request is held in the probe.
    assert runtime.snapshot()["state"] == "checking"
    release.set()
    first.join(2)
    second.join(2)
    assert len(outputs) == 2 and all(item["available"] for item in outputs)
    assert launch.call_count == 1


def test_probe_uses_tags_only_no_redirect_and_no_local_proxy(settings, monkeypatch):
    opener = Mock()
    opener.open.return_value = io.BytesIO(json.dumps({"models": [{"name": "qwen3.5:4b"}]}).encode())
    build = Mock(return_value=opener)
    monkeypatch.setattr(ai_runtime.urllib.request, "build_opener", build)
    runtime = ai_runtime.AIRuntime(settings)
    assert runtime.ensure_ready()["models"] == ["qwen3.5:4b"]
    opener.open.assert_called_once_with("http://127.0.0.1:11434/api/tags", timeout=1.0)
    proxy, redirect = build.call_args.args
    assert proxy.proxies == {}
    assert redirect.redirect_request(None, None, 302, "redirect", {}, "http://remote.test") is None


@pytest.mark.parametrize("body", [b"not json", b"{}", b'[]', b'{"models": null}'])
def test_random_http_service_is_not_treated_as_ollama(settings, monkeypatch, body):
    opener = Mock()
    opener.open.return_value = io.BytesIO(body)
    monkeypatch.setattr(ai_runtime.urllib.request, "build_opener", lambda *args: opener)
    runtime = ai_runtime.AIRuntime(settings)
    assert runtime.ensure_ready()["error_code"] == "not_installed"


def test_connection_failure_becomes_actionable_state(settings, monkeypatch):
    opener = Mock()
    opener.open.side_effect = urllib.error.URLError("connection refused")
    monkeypatch.setattr(ai_runtime.urllib.request, "build_opener", lambda *args: opener)
    runtime = ai_runtime.AIRuntime(settings)
    assert runtime.ensure_ready()["error_code"] == "not_installed"


def test_malformed_http_response_becomes_actionable_state(settings, monkeypatch):
    opener = Mock()
    opener.open.side_effect = http.client.BadStatusLine("malformed")
    monkeypatch.setattr(ai_runtime.urllib.request, "build_opener", lambda *args: opener)
    assert ai_runtime.AIRuntime(settings).ensure_ready()["error_code"] == "not_installed"


def test_concurrent_retry_waiters_do_not_repeat_failed_launch(settings, monkeypatch, process):
    child, launch = process
    child.poll.return_value = 1
    started = threading.Event()
    waiting = threading.Event()
    release = threading.Event()
    runtime = ai_runtime.AIRuntime(settings)
    real_lock = threading.Lock()

    class ObservableLock:
        def acquire(self, **kwargs):
            if real_lock.locked():
                waiting.set()
            return real_lock.acquire(**kwargs)

        def release(self):
            real_lock.release()

    runtime._ensure_lock = ObservableLock()
    calls = 0

    def health(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            assert release.wait(2)
        return None

    monkeypatch.setattr(runtime, "_probe", health)
    outputs = []
    threads = [threading.Thread(target=lambda: outputs.append(runtime.ensure_ready(retry=True))) for _ in range(2)]
    threads[0].start()
    assert started.wait(2)
    threads[1].start()
    assert waiting.wait(2)
    release.set()
    for thread in threads:
        thread.join(2)
    assert len(outputs) == 2
    assert all(item["error_code"] == "process_exited" for item in outputs)
    assert launch.call_count == 1
    assert runtime.ensure_ready(retry=True)["error_code"] == "process_exited"
    assert launch.call_count == 2


def test_resolver_prefers_explicit_executable_and_never_falls_back_on_bad_override(tmp_path, monkeypatch):
    executable = tmp_path / "custom ollama.exe"
    executable.touch()
    monkeypatch.setenv("CUTROOM_OLLAMA", str(executable))
    which = Mock(return_value=None)
    monkeypatch.setattr(ai_runtime.shutil, "which", which)
    assert REAL_RESOLVER() == str(executable.resolve())
    which.assert_not_called()
    monkeypatch.setenv("CUTROOM_OLLAMA", str(tmp_path / "missing.exe"))
    assert REAL_RESOLVER() is None


def test_resolver_uses_path_then_standard_windows_install(tmp_path, monkeypatch):
    monkeypatch.delenv("CUTROOM_OLLAMA", raising=False)
    which = Mock(return_value="C:/path/ollama.exe")
    monkeypatch.setattr(ai_runtime.shutil, "which", which)
    assert REAL_RESOLVER() == "C:/path/ollama.exe"
    which.return_value = None
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "programfiles"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "programfiles-x86"))
    executable = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    assert REAL_RESOLVER() == str(executable.resolve())


def test_environment_preserves_user_model_idle_policy(settings, monkeypatch):
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "45s")
    monkeypatch.setenv("OLLAMA_MODELS", "D:/models")
    environment = ai_runtime.ollama_environment(settings)
    assert environment["OLLAMA_KEEP_ALIVE"] == "45s"
    assert environment["OLLAMA_MODELS"] == "D:/models"


def test_log_rotation_keeps_one_previous_launch(settings, monkeypatch, process):
    runtime = ai_runtime.AIRuntime(settings)
    runtime._log_path.parent.mkdir(parents=True)
    runtime._log_path.write_bytes(b"old startup log")
    monkeypatch.setattr(ai_runtime, "LOG_ROTATE_BYTES", 1)
    probe(monkeypatch, runtime, [None, []])
    assert runtime.ensure_ready()["available"]
    assert runtime._log_path.with_suffix(".previous.log").read_bytes() == b"old startup log"


def test_background_start_is_nonblocking_single_flight(settings, monkeypatch):
    thread = Mock()
    thread.is_alive.return_value = True
    factory = Mock(return_value=thread)
    monkeypatch.setattr(ai_runtime.threading, "Thread", factory)
    runtime = ai_runtime.AIRuntime(settings)
    runtime.start_background()
    runtime.start_background()
    assert factory.call_count == 1
    thread.start.assert_called_once()
    assert factory.call_args.kwargs["daemon"] is True
