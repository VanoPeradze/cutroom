"""Large declared video imports use bounded chunks, never giant test bodies.

No FFmpeg, models, preparation workers or multi-GiB files are created here.
Finalize-policy tests mock the already validated ticket boundary explicitly;
the streaming tests exercise real UploadStorage with at most one 8MiB prefix.
"""
from __future__ import annotations

import copy
import io
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom import upload_storage as storage_module
from cutroom.config import load_settings
from cutroom.upload_storage import CHUNK_BYTES, RESERVE_BYTES, UploadStorageError, UploadTicket
from cutroom.upload_transport import LEGACY_ASSET_UPLOAD_BYTES, MULTIPART_ALLOWANCE_BYTES, upload_channel_class

GiB = 1024**3


@pytest.fixture()
def env(tmp_path, monkeypatch, request):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw.update({"host": "127.0.0.1", "max_upload_gb": getattr(request, "param", 40), "job_workers": 1})
    settings.ai.update({"enabled": False, "auto_start_ollama": False, "download_models_on_setup": False})
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=128 * GiB))
    monkeypatch.setattr(storage_module, "filesystem_id", lambda _path: "test-volume")
    app = server.create_app(settings)
    app.config["TESTING"] = True
    store, jobs = app.extensions["cutroom_store"], app.extensions["cutroom_jobs"]
    monkeypatch.setattr(jobs, "submit", lambda *_a, **_k: SimpleNamespace(public=lambda: {"id": "mock-preparation-not-run"}))
    value = SimpleNamespace(app=app, client=app.test_client(), store=store,
                            manager=app.extensions["cutroom_upload_storage"], project=store.create("Large upload policy"))
    yield value
    value.manager.close()
    jobs.shutdown(wait=True, cancel_pending=True)


def preflight(env, size=3 * GiB, filename="large.mp4"):
    return env.client.post(f"/api/projects/{env.project['id']}/uploads/preflight",
                           json={"purpose": "asset", "filename": filename, "size_bytes": size})


class SyntheticReader:
    """Generate a small prefix lazily, recording every bounded storage read."""
    def __init__(self, count, on_first_read=None):
        self.remaining, self.on_first_read = count, on_first_read
        self.requests = []

    def read(self, requested):
        assert 0 < requested <= 1024**2
        self.requests.append(requested)
        count = min(requested, self.remaining, 64 * 1024)
        self.remaining -= count
        if len(self.requests) == 1 and self.on_first_read:
            self.on_first_read()
        return b"x" * count


class NeverRead(io.BytesIO):
    def read(self, *_args, **_kwargs):
        pytest.fail("A rejected giant declaration must not read a WSGI body")

    def readinto(self, *_args, **_kwargs):
        pytest.fail("A rejected giant declaration must not read a WSGI body")


def test_video_over_two_gib_reserves_only_original_and_one_bounded_chunk(env):
    before = copy.deepcopy(env.store.load(env.project["id"]))
    response = preflight(env)
    assert response.status_code == 201, response.get_json()
    receipt = response.get_json()
    assert receipt["size_bytes"] == 3 * GiB
    assert receipt["chunk_size_bytes"] == CHUNK_BYTES
    rows = receipt["storage_plan"]["filesystems"]
    assert len(rows) == 1 and rows[0]["required_bytes"] == 3 * GiB + CHUNK_BYTES
    ticket = env.manager.get(env.project["id"], receipt["upload_token"])
    assert not ticket.path.exists()
    reader = SyntheticReader(CHUNK_BYTES)
    assert env.manager.append(ticket.project_id, ticket.token, 0, CHUNK_BYTES, reader) == CHUNK_BYTES
    assert ticket.path.stat().st_size == CHUNK_BYTES and reader.remaining == 0
    assert len(reader.requests) > 1 and max(reader.requests) <= 1024**2
    assert env.client.post(receipt["cancel_url"]).status_code == 200
    assert not ticket.path.exists() and not env.manager.tickets
    assert env.store.load(ticket.project_id) == before


def test_cancel_large_declared_stream_during_bounded_read_removes_only_own_prefix(env):
    before = copy.deepcopy(env.store.load(env.project["id"]))
    receipt = preflight(env).get_json()
    ticket = env.manager.get(env.project["id"], receipt["upload_token"])
    marker = ticket.path.parent / "unrelated-user-media.mp4"
    marker.write_bytes(b"preserve")
    reader = SyntheticReader(CHUNK_BYTES, lambda: env.manager.cancel(ticket.project_id, ticket.token))
    with pytest.raises(UploadStorageError, match="cancelled"):
        env.manager.append(ticket.project_id, ticket.token, 0, CHUNK_BYTES, reader)
    assert len(reader.requests) == 1 and not ticket.path.exists()
    assert marker.read_bytes() == b"preserve" and not env.manager.tickets
    assert env.store.load(ticket.project_id) == before


def test_large_video_insufficient_disk_fails_before_any_partial_or_reservation(env, monkeypatch):
    monkeypatch.setattr(storage_module.shutil, "disk_usage",
                        lambda _path: SimpleNamespace(free=3 * GiB + CHUNK_BYTES + RESERVE_BYTES - 1))
    response = preflight(env)
    assert response.status_code == 507, response.get_json()
    assert response.get_json()["storage_plan"]["transport"] == "chunked-v1"
    assert not env.manager.tickets
    assert not list(env.store.project_dir(env.project["id"]).glob("media/.incoming-*"))


@pytest.mark.parametrize("filename,limit", [("image.png", 32 * 1024**2), ("audio.wav", 512 * 1024**2), ("video.mp4", 40 * GiB)])
def test_file_kind_and_configured_limits_remain_exact(env, filename, limit):
    response = preflight(env, limit, filename)
    assert response.status_code == 201, response.get_json()
    assert env.client.post(response.get_json()["cancel_url"]).status_code == 200
    rejected = preflight(env, limit + 1, filename)
    assert rejected.status_code == 413
    assert rejected.get_json()["max_upload_bytes"] == limit
    assert not env.manager.tickets


@pytest.mark.parametrize("env", [1], indirect=True)
def test_smaller_configured_video_limit_is_not_raised(env):
    response = preflight(env, GiB + 1)
    assert response.status_code == 413 and response.get_json()["max_upload_bytes"] == GiB
    assert not env.manager.tickets


@pytest.mark.parametrize("size", [0, -1, True, 3.5, "3221225472", None])
def test_declared_size_must_be_positive_integer_before_storage(env, size):
    response = preflight(env, size)
    assert response.status_code == 400 and response.get_json()["error"] == "invalid_upload_size"
    assert not env.manager.tickets


@pytest.mark.parametrize("filename", [None, "", "   ", "unsupported.exe"])
def test_name_and_file_type_validation_precede_large_reservation(env, filename):
    assert preflight(env, filename=filename).status_code == 400
    assert not env.manager.tickets


def test_oversized_chunk_of_large_declared_video_is_rejected_without_read(env):
    receipt = preflight(env).get_json()
    response = env.client.open(receipt["upload_url"], method="PUT", content_type="application/octet-stream",
        headers={"X-Cutroom-Upload-Offset": "0"},
        environ_overrides={"CONTENT_LENGTH": str(CHUNK_BYTES + 1), "wsgi.input": NeverRead()})
    assert response.status_code == 413
    ticket = env.manager.get(env.project["id"], receipt["upload_token"])
    assert ticket.received == 0 and not ticket.path.exists()


def test_large_legacy_asset_requires_chunked_before_wsgi_body_or_disk_admission(env):
    response = env.client.open(f"/api/projects/{env.project['id']}/assets", method="POST",
        content_type="multipart/form-data; boundary=test",
        environ_overrides={"CONTENT_LENGTH": str(3 * GiB), "wsgi.input": NeverRead()})
    assert response.status_code == 413
    assert response.get_json()["error"] == "chunked_upload_required"
    assert response.get_json()["transport"] == "chunked-v1"
    assert not env.manager.legacy and not env.manager.tickets


def test_chunked_finalize_metadata_keeps_json_bound_without_reading_body(env, monkeypatch):
    receipt = preflight(env).get_json()
    monkeypatch.setattr(env.manager, "begin_finalize", lambda *_args: pytest.fail("Oversized metadata must fail before ticket finalization"))
    response = env.client.open(f"/api/projects/{env.project['id']}/assets", method="POST", content_type="application/json",
        headers={"X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": receipt["upload_token"]},
        environ_overrides={"CONTENT_LENGTH": str(server.JSON_BODY_LIMIT + 1), "wsgi.input": NeverRead()})
    assert response.status_code == 413
    ticket = env.manager.get(env.project["id"], receipt["upload_token"])
    assert ticket.received == 0 and not ticket.finalizing and not ticket.path.exists()


def test_waitress_large_legacy_rejection_happens_before_buffering(env):
    from waitress.adjustments import Adjustments
    parser = upload_channel_class(env.manager, 40 * GiB).parser_class(Adjustments(max_request_body_size=41 * GiB))
    header = (f"POST /api/projects/{env.project['id']}/assets HTTP/1.1\r\nHost: localhost\r\n"
              f"Content-Length: {LEGACY_ASSET_UPLOAD_BYTES + MULTIPART_ALLOWANCE_BYTES + 1}\r\n\r\n").encode()
    try:
        parser.received(header + b"never-buffer-this-body")
        assert parser.error.error.code == "chunked_upload_required"
        assert parser.body_bytes_received == 0 and len(parser.body_rcv.getbuf()) == 0
        assert not env.manager.legacy
    finally:
        parser.close()


def test_waitress_large_video_ticket_admits_only_one_bounded_chunk(env):
    from waitress.adjustments import Adjustments
    receipt = preflight(env).get_json()
    parser = upload_channel_class(env.manager, 40 * GiB).parser_class(Adjustments())
    try:
        parser.received((f"PUT {receipt['upload_url']} HTTP/1.1\r\nHost: localhost\r\n"
            f"Content-Length: {CHUNK_BYTES}\r\nX-Cutroom-Upload-Offset: 0\r\n\r\n").encode())
        assert not parser.error
        assert parser.upload_ticket.size == 3 * GiB and parser.upload_ticket.transport_busy
    finally:
        parser.close()
    assert not env.manager.get(env.project["id"], receipt["upload_token"]).transport_busy


def validated_ticket_stub(env, monkeypatch, filename, size):
    """Isolate final-route file-size policy; this is NOT a large-byte transfer."""
    path = env.store.project_dir(env.project["id"]) / "media/.incoming-policy-test"
    path.write_bytes(b"tiny-policy-fixture")
    ticket = UploadTicket(env.project["id"], "PolicyTicket1234567890", "asset", None, filename, size,
                          path, received=size, busy=True, finalizing=True)
    env.manager.tickets[ticket.project_id, ticket.token] = ticket
    monkeypatch.setattr(env.manager, "begin_finalize", lambda *_args: ticket)
    return ticket


def finalize(env, ticket):
    return env.client.post(f"/api/projects/{env.project['id']}/assets", headers={
        "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": ticket.token})


def test_large_video_finalize_uses_ticket_limit_not_legacy_multipart_limit(env, monkeypatch):
    ticket = validated_ticket_stub(env, monkeypatch, "large.mp4", 3 * GiB)
    monkeypatch.setattr(server, "probe_asset", lambda path, kind, _settings: {
        "kind": kind, "duration": 2, "width": 32, "height": 32, "has_audio": False, "size": path.stat().st_size})
    monkeypatch.setattr(server, "copy_upload", lambda *_args: pytest.fail("Finalization must rename, never recopy"))
    response = finalize(env, ticket)
    assert response.status_code == 202, response.get_json()
    asset = env.store.load(ticket.project_id)["assets"][response.get_json()["asset_id"]]
    assert (env.store.project_dir(ticket.project_id) / asset["path"]).read_bytes() == b"tiny-policy-fixture"
    assert not ticket.path.exists() and not env.manager.tickets


@pytest.mark.parametrize("filename,size", [("image.png", 32 * 1024**2 + 1), ("audio.wav", 512 * 1024**2 + 1), ("video.mp4", 40 * GiB + 1)])
def test_finalize_rechecks_declared_ticket_kind_and_configured_limit(env, monkeypatch, filename, size):
    before = copy.deepcopy(env.store.load(env.project["id"]))
    ticket = validated_ticket_stub(env, monkeypatch, filename, size)
    monkeypatch.setattr(server, "probe_asset", lambda *_args: pytest.fail("Over-limit original must not be probed"))
    response = finalize(env, ticket)
    assert response.status_code == 413 and response.get_json()["error"] == "file_too_large"
    assert env.store.load(ticket.project_id) == before
    assert not ticket.path.exists() and not env.manager.tickets


def test_small_legacy_multipart_video_still_imports(env, monkeypatch):
    monkeypatch.setattr(server, "probe_asset", lambda path, kind, _settings: {
        "kind": kind, "duration": 2, "width": 32, "height": 32, "has_audio": False, "size": path.stat().st_size})
    response = env.client.post(f"/api/projects/{env.project['id']}/assets",
                               data={"file": (io.BytesIO(b"small-video"), "small.mp4")})
    assert response.status_code == 202, response.get_json()
    asset = env.store.load(env.project["id"])["assets"][response.get_json()["asset_id"]]
    assert (env.store.project_dir(env.project["id"]) / asset["path"]).read_bytes() == b"small-video"
    assert not env.manager.legacy


def test_large_chunked_policy_does_not_raise_global_waitress_body_ceiling(env, monkeypatch):
    import waitress.server
    from cutroom.upload_transport import create_upload_server
    calls = []
    def fake_server(_application, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(map={})
    monkeypatch.setattr(waitress.server, "create_server", fake_server)
    create_upload_server(env.app)
    assert "max_request_body_size" not in calls[-1]
    create_upload_server(env.app, max_request_body_size=CHUNK_BYTES)
    assert calls[-1]["max_request_body_size"] == CHUNK_BYTES
