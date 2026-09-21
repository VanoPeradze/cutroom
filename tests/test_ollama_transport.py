"""Local transport boundaries, using synthetic sockets only."""
import io
import json
import threading
import time
import urllib.error
import urllib.request
from types import SimpleNamespace

import pytest

from cutroom import ai_runtime, intelligence


@pytest.fixture(autouse=True)
def no_real_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Real network is forbidden")
    monkeypatch.setattr(ai_runtime.socket, "create_connection", forbidden)
    monkeypatch.setattr(ai_runtime.socket, "getaddrinfo", forbidden)


class Socket:
    def __init__(self, body=b"{}", status="200 OK", headers=""):
        self.sent = []
        self.stopped = threading.Event()
        self.stream = io.BytesIO(
            f"HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n{headers}\r\n".encode() + body)

    def setsockopt(self, *args):
        pass

    def settimeout(self, *args):
        pass

    def sendall(self, value):
        self.sent.append(value)

    def makefile(self, *args):
        return self.stream

    def shutdown(self, *args):
        self.stopped.set()

    def close(self):
        pass


@pytest.mark.parametrize("url", [
    "http://api.vendor.com/api/chat", "http://192.168.1.2:11434/api/chat",
    "http://localhost.evil.test/api/chat", "http://2130706433/api/chat",
    "http://user:secret@localhost/api/chat", "http://localhost/api/chat?x=y",
    "http://localhost/api/chat#x", "http://local\nhost/api/chat",
    "http://localhost\\evil.test/api/chat", "http://[::ffff:192.168.1.1]/api/chat",
])
def test_unapproved_destination_never_opens(url):
    with pytest.raises(ValueError):
        with ai_runtime.open_ollama(url):
            pytest.fail("Endpoint accepted")


def test_localhost_is_pinned_and_proxy_environment_ignored(monkeypatch):
    sock = Socket()
    calls = []
    monkeypatch.setenv("http_proxy", "http://proxy.invalid:3128")
    monkeypatch.setenv("no_proxy", "")
    monkeypatch.setattr(ai_runtime.socket, "create_connection", lambda *args: calls.append(args) or sock)
    req = urllib.request.Request("http://localhost:11434/api/chat", data=b'{"synthetic":true}')
    with ai_runtime.open_ollama(req) as response:
        assert ai_runtime.read_ollama_json(response) == {}
    assert len(calls) == 1 and calls[0][0] == ("127.0.0.1", 11434)
    sent = b"".join(sock.sent)
    assert b"Host: localhost:11434" in sent and b'"synthetic":true' in sent
    assert b"proxy.invalid" not in sent


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_cannot_contact_second_destination(monkeypatch, status):
    sock = Socket(status=f"{status} Redirect", headers="Location: http://evil.test/collect\r\n")
    calls = []
    monkeypatch.setattr(ai_runtime.socket, "create_connection", lambda *args: calls.append(args) or sock)
    with pytest.raises(urllib.error.HTTPError):
        with ai_runtime.open_ollama("http://127.0.0.1:11434/api/tags"):
            pytest.fail("Redirect accepted")
    assert len(calls) == 1


def test_total_deadline_interrupts_blocked_body(monkeypatch):
    sock = Socket(body=b"{}")

    class BlockedBody(io.BytesIO):
        def read(self, size=-1):
            assert sock.stopped.wait(1), "Deadline did not interrupt the socket"
            raise OSError("socket shut down")

    sock.stream = BlockedBody(sock.stream.getvalue())
    monkeypatch.setattr(ai_runtime.socket, "create_connection", lambda *args: sock)
    started = time.monotonic()
    with pytest.raises((OSError, TimeoutError)):
        with ai_runtime.open_ollama("http://127.0.0.1:11434/api/chat", timeout=0.03) as response:
            ai_runtime.read_ollama_json(response)
    assert time.monotonic() - started < 1


def test_nonstream_and_stream_responses_have_byte_limits(monkeypatch):
    with pytest.raises(ValueError, match="oversized"):
        ai_runtime.read_ollama_json(io.BytesIO(b" " * 33), limit=32)
    monkeypatch.setattr(intelligence, "OLLAMA_RESPONSE_BYTES", 80)
    line = json.dumps({"message": {"content": "x" * 20}, "done": False}).encode() + b"\n"
    with pytest.raises(intelligence.StoryPlanningError, match="oversized"):
        intelligence._read_ollama_chat_response(io.BytesIO(line * 3), streaming=True, cancel_check=None)
    with pytest.raises(intelligence.StoryPlanningError, match="oversized"):
        intelligence._read_ollama_chat_response(io.BytesIO(b"x" * (256 * 1024 + 1)), streaming=True, cancel_check=None)


def test_slow_consumer_applies_backpressure_and_can_cancel():
    received = []
    filled = threading.Event()

    class Response(io.BytesIO):
        def readline(self, size):
            received.append(True)
            if len(received) >= 9:
                filled.set()
            return b'{"message":{"content":"x"},"done":false}\n'

    class Cancelled(RuntimeError):
        pass

    def cancel():
        assert filled.wait(1)
        assert len(received) == 9  # Eight queued lines and one waiting producer.
        raise Cancelled()

    with pytest.raises(Cancelled):
        intelligence._read_ollama_chat_response(Response(), streaming=True, cancel_check=cancel)


def test_local_chat_paths_reject_remote_configuration():
    settings = SimpleNamespace(ai={"ollama_url": "http://192.168.1.2:11434"})
    assert intelligence._ollama_inventory(settings) == (False, set())
    assert intelligence._call_ollama(settings, {"messages": []}) is None
    with pytest.raises(intelligence.StoryAIUnavailableError, match="loopback"):
        intelligence._call_ollama_strict(settings, {"messages": []})
