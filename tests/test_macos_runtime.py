"""Mac-only listener reservation: restart safely without sharing live ports."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("mac_socket_runtime", ROOT / "packaging/mac/preflight_macos.py")
runtime = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runtime)


class StartupError(RuntimeError):
    pass


def enable_mac(monkeypatch):
    # Override only this module's reference, never the process-wide platform.
    monkeypatch.setattr(runtime, "sys", SimpleNamespace(
        platform="darwin", stderr=sys.stderr, stdin=sys.stdin, path=list(sys.path),
    ))


class FakeSocket:
    def __init__(self, failure=None):
        self.events = []
        self.failure = failure
        self.closed = False

    def event(self, name, *args):
        self.events.append((name, *args))
        if self.failure == name:
            raise OSError(f"{name} failed")
        if self.failure == "interrupt" and name == "bind":
            raise KeyboardInterrupt

    def setsockopt(self, *args):
        self.event("setsockopt", *args)

    def bind(self, address):
        self.event("bind", address)

    def listen(self, backlog):
        self.event("listen", backlog)

    def close(self):
        self.closed = True
        self.events.append(("close",))


def fake_network(monkeypatch, *, failure=None, duplicate=False):
    enable_mac(monkeypatch)
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 8765)),
        (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", 8765, 0, 0)),
    ]
    if duplicate:
        addresses.insert(1, addresses[0])
    created = []

    def create(*args):
        if len(created) == 1 and failure == "create":
            raise OSError("create failed")
        candidate = FakeSocket(failure if created else None)
        created.append(candidate)
        return candidate

    network = SimpleNamespace(
        AF_INET6=socket.AF_INET6, SOCK_STREAM=socket.SOCK_STREAM,
        SOL_SOCKET=socket.SOL_SOCKET, SO_REUSEADDR=socket.SO_REUSEADDR,
        IPPROTO_IPV6=socket.IPPROTO_IPV6, IPV6_V6ONLY=socket.IPV6_V6ONLY,
        getaddrinfo=lambda *args, **kwargs: addresses, socket=create,
    )
    monkeypatch.setattr(runtime, "socket", network)
    return created, network


def test_reservation_reuses_addresses_not_ports_and_listens_before_return(monkeypatch):
    original_factory = socket.socket
    created, _ = fake_network(monkeypatch, duplicate=True)
    result = runtime.reserve_macos_server_sockets("localhost", 8765, StartupError)
    assert result == created and len(created) == 2
    for candidate in created:
        assert candidate.events[0] == ("setsockopt", socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        assert candidate.events[-2][0] == "bind"
        assert candidate.events[-1] == ("listen", 128)
        assert not candidate.closed
    assert ("setsockopt", socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1) in created[1].events
    assert socket.socket is original_factory
    assert all(event[2] != getattr(socket, "SO_REUSEPORT", object())
               for candidate in created for event in candidate.events if event[0] == "setsockopt" and event[1] == socket.SOL_SOCKET)


@pytest.mark.parametrize("failure", ["create", "setsockopt", "bind", "listen"])
def test_any_reservation_failure_closes_current_and_previous_sockets(monkeypatch, failure):
    created, _ = fake_network(monkeypatch, failure=failure)
    with pytest.raises(StartupError, match="already in use or unavailable") as error:
        runtime.reserve_macos_server_sockets("localhost", 8765, StartupError)
    assert isinstance(error.value.__cause__, OSError)
    assert len(created) == (1 if failure == "create" else 2)
    assert all(candidate.closed for candidate in created)


def test_interrupt_during_reservation_closes_sockets(monkeypatch):
    created, _ = fake_network(monkeypatch, failure="interrupt")
    with pytest.raises(KeyboardInterrupt):
        runtime.reserve_macos_server_sockets("localhost", 8765, StartupError)
    assert len(created) == 2 and all(candidate.closed for candidate in created)


@pytest.mark.parametrize("resolve_error", [False, True])
def test_empty_or_failed_resolution_preserves_startup_error_type(monkeypatch, resolve_error):
    created, network = fake_network(monkeypatch)

    def addresses(*args, **kwargs):
        if resolve_error:
            raise socket.gaierror("no address")
        return []

    network.getaddrinfo = addresses
    with pytest.raises(StartupError, match="could not resolve" if resolve_error else "could not find"):
        runtime.reserve_macos_server_sockets("localhost", 8765, StartupError)
    assert not created


def test_non_mac_gate_runs_before_import_or_socket_work(monkeypatch):
    monkeypatch.setattr(runtime, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=lambda name: pytest.fail("must not import server")))
    monkeypatch.setattr(runtime, "socket", SimpleNamespace(getaddrinfo=lambda *args: pytest.fail("must not resolve addresses")))
    with pytest.raises(RuntimeError, match="requires macOS"):
        runtime.run_macos_server()
    with pytest.raises(RuntimeError, match="requires macOS"):
        runtime.reserve_macos_server_sockets("127.0.0.1", 8765, StartupError)


@pytest.mark.parametrize("failure", [None, StartupError("occupied"), KeyboardInterrupt(), ValueError("unexpected")])
def test_server_adapter_restores_only_reservation_on_every_exit(monkeypatch, capsys, failure):
    enable_mac(monkeypatch)
    original_reserve = object()
    original_factory = socket.socket
    called = []
    server = SimpleNamespace(_reserve_server_sockets=original_reserve, ServerStartupError=StartupError)

    def main():
        assert server._reserve_server_sockets is not original_reserve
        assert socket.socket is original_factory
        assert server._reserve_server_sockets("127.0.0.1", 8765) == ["owned"]
        if failure is not None:
            raise failure

    server.main = main
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=lambda name: server if name == "server" else pytest.fail(name)))
    monkeypatch.setattr(runtime, "reserve_macos_server_sockets", lambda *args: called.append(args) or ["owned"])
    if isinstance(failure, StartupError):
        with pytest.raises(SystemExit) as error:
            runtime.run_macos_server()
        assert error.value.code == 1
        assert capsys.readouterr().err == "ERROR: occupied\n"
    elif failure is not None:
        with pytest.raises(type(failure)):
            runtime.run_macos_server()
    else:
        runtime.run_macos_server()
    assert server._reserve_server_sockets is original_reserve
    assert socket.socket is original_factory
    assert called == [("127.0.0.1", 8765, StartupError)]


@pytest.mark.parametrize("owner", ["match", "different_instance", "different_version", "unknown"])
def test_original_server_identity_handling_is_preserved(monkeypatch, tmp_path, capsys, owner):
    import server

    enable_mac(monkeypatch)
    original_reserve = server._reserve_server_sockets
    settings = SimpleNamespace(raw={"host": "127.0.0.1", "port": 8765, "open_browser": False}, data_dir=tmp_path)
    probes = []
    monkeypatch.setattr(runtime, "importlib", SimpleNamespace(import_module=lambda name: server))
    monkeypatch.setattr(server, "load_settings", lambda: settings)
    monkeypatch.setattr(server, "_probe_existing_cutroom_server", lambda *args: probes.append(args) or owner)
    monkeypatch.setattr(server, "create_app", lambda *args: pytest.fail("must not create a competing app"))

    def occupied(*args):
        raise server.ServerStartupError("port occupied")

    monkeypatch.setattr(runtime, "reserve_macos_server_sockets", occupied)
    if owner == "match":
        runtime.run_macos_server()
        assert "already running" in capsys.readouterr().out
    else:
        with pytest.raises(SystemExit) as error:
            runtime.run_macos_server()
        assert error.value.code == 1
        message = capsys.readouterr().err
        assert message.startswith("ERROR: ") and "Traceback" not in message
        assert {"different_instance": "another CUTROOM data folder", "different_version": "different CUTROOM version", "unknown": "port occupied"}[owner] in message
    assert probes == [("127.0.0.1", 8765, server._cutroom_instance_id(settings))]
    assert server._reserve_server_sockets is original_reserve


@pytest.mark.skipif(os.name != "posix", reason="Real reuse-address behavior must never be tested on Windows")
def test_real_posix_socket_restarts_immediately_after_server_active_close(monkeypatch):
    enable_mac(monkeypatch)
    listeners = runtime.reserve_macos_server_sockets("127.0.0.1", 0, StartupError)
    listener = listeners[0]
    port = listener.getsockname()[1]
    listener.settimeout(3)
    peer = socket.create_connection(("127.0.0.1", port), timeout=3)
    accepted = None
    replacement = []
    try:
        accepted, _ = listener.accept()
        accepted.shutdown(socket.SHUT_WR)
        assert peer.recv(1) == b""
        peer.close()
        accepted.close()
        listener.close()
        replacement = runtime.reserve_macos_server_sockets("127.0.0.1", port, StartupError)
        # macOS can reject SO_ACCEPTCONN introspection despite a working socket.
        # A real round trip proves the replacement is listening and usable.
        replacement[0].settimeout(3)
        with socket.create_connection(("127.0.0.1", port), timeout=3) as second_peer:
            second_connection, _ = replacement[0].accept()
            with second_connection:
                second_connection.sendall(b"restarted")
                assert second_peer.recv(9) == b"restarted"
    finally:
        peer.close()
        if accepted is not None:
            accepted.close()
        for candidate in [*listeners, *replacement]:
            candidate.close()


@pytest.mark.skipif(os.name != "posix", reason="Real reuse-address behavior must never be tested on Windows")
def test_real_posix_live_listener_cannot_be_taken_over(monkeypatch):
    enable_mac(monkeypatch)
    listeners = runtime.reserve_macos_server_sockets("127.0.0.1", 0, StartupError)
    listener = listeners[0]
    listener.settimeout(3)
    port = listener.getsockname()[1]
    try:
        with pytest.raises(StartupError, match="already in use"):
            runtime.reserve_macos_server_sockets("127.0.0.1", port, StartupError)
        with socket.create_connection(("127.0.0.1", port), timeout=3) as peer:
            accepted, _ = listener.accept()
            with accepted:
                accepted.sendall(b"original")
                assert peer.recv(8) == b"original"
    finally:
        for candidate in listeners:
            candidate.close()
