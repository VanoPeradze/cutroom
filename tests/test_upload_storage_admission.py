from __future__ import annotations

import copy
import errno
import io
import http.client
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import server
from cutroom import upload_storage as storage_module
from cutroom.config import load_settings
from cutroom.upload_storage import CHUNK_BYTES, RESERVE_BYTES, UploadStorage, UploadStorageError

GiB = 1024**3


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    settings.raw["host"] = "127.0.0.1"
    settings.raw["ai"]["enabled"] = False
    application = server.create_app(settings)
    application.config.update(TESTING=True)
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=26 * GiB))
    monkeypatch.setattr(storage_module, "filesystem_id", lambda _path: "same-volume")
    jobs = application.extensions["cutroom_jobs"]
    monkeypatch.setattr(jobs, "submit", lambda *_args, **_kwargs: SimpleNamespace(public=lambda: {"id": "synthetic-preparation"}))
    yield application
    application.extensions["cutroom_upload_storage"].close()
    jobs.shutdown(wait=True, cancel_pending=True)


def project(app):
    return app.extensions["cutroom_store"].create("Synthetic storage admission")


def preflight(client, pid, *, size=12, slot="A", purpose="source", token=None, filename=None):
    return client.post(f"/api/projects/{pid}/uploads/preflight", json={
        "purpose": purpose, "slot": slot, "filename": filename or ("clip.mp4" if purpose == "source" else "music.wav"),
        "size_bytes": size, **({"upload_token": token} if token else {}),
    })


def transfer(client, receipt, body=b"new-original"):
    return client.put(receipt["upload_url"], data=body, content_type="application/octet-stream",
                      headers={"X-Cutroom-Upload-Offset": "0"})


def complete(client, pid, receipt, slot="A", purpose="source"):
    return client.post(f"/api/projects/{pid}/" + (f"sources/{slot}" if purpose == "source" else "assets"),
                       headers={"X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": receipt["upload_token"]})


def probe(path, _settings, *, original_filename=None):
    return {"duration": 12.0, "width": 1280, "height": 720, "fps": 30.0, "has_audio": False,
            "size": path.stat().st_size, "browser_ready": True, "mime": "video/mp4"}


def test_chunked_mp4_probe_uses_logical_name_without_renaming_owned_staging(app, monkeypatch):
    from cutroom import media

    client = app.test_client()
    pid = project(app)["id"]
    ticket = preflight(client, pid, filename="full-episode.mp4").get_json()
    assert transfer(client, ticket).status_code == 200
    staged = app.extensions["cutroom_upload_storage"].get(pid, ticket["upload_token"]).path
    assert staged.suffix == ""
    staged_identity = staged.stat().st_ino
    observed = []
    payload = {"format": {"duration": "12", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
               "streams": [{"codec_type": "video", "codec_name": "h264", "width": 1280,
                            "height": 720, "duration": "12", "avg_frame_rate": "30/1"},
                           {"codec_type": "audio", "codec_name": "aac", "duration": "12"}]}
    monkeypatch.setattr(media, "run_command", lambda *_args, **_kwargs: SimpleNamespace(stdout=json.dumps(payload)))

    def observe(path, settings, *, original_filename=None):
        observed.append((path, original_filename, path.read_bytes(), path.stat().st_ino))
        return media.probe_media(path, settings, original_filename=original_filename)

    monkeypatch.setattr(server, "probe_media", observe)
    response = complete(client, pid, ticket)
    assert response.status_code == 201, response.get_json()
    assert observed == [(staged, "full-episode.mp4", b"new-original", staged_identity)]
    source = response.get_json()["source"]
    assert source["browser_ready"] is True and source["mime"] == "video/mp4"
    original = app.extensions["cutroom_store"].project_dir(pid) / "media/source-A.mp4"
    assert original.read_bytes() == b"new-original"
    assert original.stat().st_ino == staged_identity
    assert not staged.exists()


def test_15_gib_preflight_on_26_gib_reserves_one_original_and_bounded_transport(app):
    client = app.test_client()
    pid = project(app)["id"]
    response = preflight(client, pid, size=15 * GiB)
    assert response.status_code == 201, response.get_json()
    data = response.get_json()
    assert data["disk_free_bytes"] == 26 * GiB
    rows = data["storage_plan"]["filesystems"]
    assert len(rows) == 1
    assert rows[0]["roles"] == ["data", "temporary"]
    assert rows[0]["required_bytes"] == 15 * GiB + CHUNK_BYTES
    assert not list(app.extensions["cutroom_store"].project_dir(pid).glob("media/.incoming-*"))
    assert client.post(data["cancel_url"]).status_code in {200, 202}


def test_data_and_temp_are_budgeted_separately_with_fresh_failure_facts(app, monkeypatch):
    manager = app.extensions["cutroom_upload_storage"]
    monkeypatch.setattr(storage_module, "filesystem_id", lambda path: "temp-volume" if Path(path) == manager.temp_dir else "data-volume")
    free = {"data-volume": 26 * GiB, "temp-volume": RESERVE_BYTES + CHUNK_BYTES - 1}
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda path: SimpleNamespace(free=free[storage_module.filesystem_id(Path(path))]))
    client = app.test_client()
    pid = project(app)["id"]
    failed = preflight(client, pid, size=15 * GiB)
    assert failed.status_code == 507
    facts = failed.get_json()
    assert facts["disk_free_bytes"] == 26 * GiB
    temporary = next(row for row in facts["storage_plan"]["filesystems"] if "temporary" in row["roles"])
    assert temporary["disk_free_bytes"] == RESERVE_BYTES + CHUNK_BYTES - 1
    assert temporary["required_bytes"] == CHUNK_BYTES
    free["temp-volume"] = 2 * GiB
    assert preflight(client, pid, size=15 * GiB).status_code == 201


def test_concurrent_preflights_cannot_both_reserve_the_same_free_space(app):
    pids = [project(app)["id"], project(app)["id"]]
    barrier = threading.Barrier(2)
    def reserve(pid):
        with app.test_client() as client:
            barrier.wait()
            return preflight(client, pid, size=15 * GiB).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(reserve, pids)) == [201, 507]


def test_reserved_remaining_bytes_credit_bytes_already_on_disk(app, monkeypatch):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    pid = project(app)["id"]
    receipt = preflight(client, pid, size=15 * GiB).get_json()
    ticket = manager.get(pid, receipt["upload_token"])
    # Model a ten-GiB prefix without creating a large synthetic file.
    ticket.received = 10 * GiB
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=16 * GiB))
    facts = manager.require(9 * GiB)
    row = facts["storage_plan"]["filesystems"][0]
    assert row["reserved_bytes"] == 5 * GiB + CHUNK_BYTES
    assert row["required_bytes"] == 9 * GiB + CHUNK_BYTES
    manager.require(5 * GiB, exclude=ticket)


@pytest.mark.parametrize("slot", ["A", "B"])
def test_chunk_source_finalize_renames_original_without_copying_and_keeps_rollback(app, monkeypatch, slot):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    root = store.project_dir(pid)
    old_path = root / "media" / f"source-{slot}.mp4"
    old_path.write_bytes(b"old-original")
    store.update(pid, lambda p: p["sources"].update({slot: {"slot": slot, "name": "old.mp4", "relative_path": f"media/source-{slot}.mp4", **probe(old_path, None)}}))
    monkeypatch.setattr(server, "probe_media", probe)
    monkeypatch.setattr(server, "copy_upload", lambda *_args: pytest.fail("completed raw import must not copy its original"))
    receipt = preflight(client, pid, slot=slot).get_json()
    assert transfer(client, receipt).status_code == 200
    staged = app.extensions["cutroom_upload_storage"].get(pid, receipt["upload_token"]).path
    identity = staged.stat().st_ino
    response = complete(client, pid, receipt, slot)
    assert response.status_code == 201, response.get_json()
    assert old_path.read_bytes() == b"new-original"
    assert old_path.stat().st_ino == identity
    assert not staged.exists()
    cancelled = client.post(f"/api/projects/{pid}/sources/{slot}/uploads/{receipt['upload_token']}/cancel")
    assert cancelled.status_code in {200, 202}, cancelled.get_json()
    assert old_path.read_bytes() == b"old-original"
    assert not list((root / "media").glob(".incoming-*"))


def test_chunk_library_finalize_renames_one_original_and_cancel_never_deletes_committed_asset(app, monkeypatch):
    client = app.test_client()
    pid = project(app)["id"]
    monkeypatch.setattr(server, "probe_asset", lambda *_args: {"kind": "audio", "duration": 2, "width": 0, "height": 0, "has_audio": True})
    monkeypatch.setattr(server, "copy_upload", lambda *_args: pytest.fail("completed library import must not copy its original"))
    receipt = preflight(client, pid, purpose="asset").get_json()
    assert transfer(client, receipt).status_code == 200
    response = complete(client, pid, receipt, purpose="asset")
    assert response.status_code == 202, response.get_json()
    asset_id = response.get_json()["asset_id"]
    store = app.extensions["cutroom_store"]
    asset = store.load(pid)["assets"][asset_id]
    path = store.project_dir(pid) / asset["path"]
    assert path.read_bytes() == b"new-original"
    assert client.post(receipt["cancel_url"]).status_code in {200, 202}
    assert path.read_bytes() == b"new-original"
    assert asset_id in store.load(pid)["assets"]


def test_cancel_expire_and_project_gate_only_touch_owned_partials(app):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    marker = store.project_dir(pid) / "media" / ".keep-user-file"
    marker.write_bytes(b"preserve")
    receipt = preflight(client, pid, size=24).get_json()
    assert transfer(client, receipt).status_code == 200
    assert client.delete(f"/api/projects/{pid}").status_code == 409
    ticket = manager.get(pid, receipt["upload_token"])
    assert ticket.path.exists()
    assert client.post(receipt["cancel_url"]).status_code in {200, 202}
    assert not ticket.path.exists()
    assert marker.read_bytes() == b"preserve"
    assert preflight(client, pid, token=receipt["upload_token"]).status_code == 409
    receipt = preflight(client, pid).get_json()
    assert transfer(client, receipt).status_code == 200
    ticket = manager.get(pid, receipt["upload_token"])
    ticket.updated -= manager.ttl + 1
    manager.prune()
    assert not ticket.path.exists()
    assert marker.read_bytes() == b"preserve"
    assert not manager.active_for_project(pid)


@pytest.mark.parametrize("purpose", ["source", "asset"])
def test_cancel_can_arrive_before_preflight_without_transferring_any_file(app, purpose):
    client = app.test_client()
    pid = project(app)["id"]
    token = "cancel-before-preflight-test"
    path = f"/api/projects/{pid}/" + (f"sources/A/uploads/{token}/cancel" if purpose == "source" else f"uploads/{token}/cancel")
    assert client.post(path).status_code in {200, 202}
    assert preflight(client, pid, purpose=purpose, token=token).status_code == 409
    assert not app.extensions["cutroom_upload_storage"].tickets


def test_wrong_target_offsets_incomplete_and_replayed_tokens_are_rejected(app, monkeypatch):
    client = app.test_client()
    pid = project(app)["id"]
    receipt = preflight(client, pid, size=24).get_json()
    assert complete(client, pid, receipt).status_code == 409
    assert transfer(client, receipt).status_code == 200
    assert transfer(client, receipt).status_code == 409
    assert complete(client, pid, receipt, "B").status_code == 409
    assert client.post(receipt["cancel_url"]).status_code in {200, 202}
    assert transfer(client, receipt).status_code == 409


@pytest.mark.parametrize("winerror", [None, 112])
def test_disk_exhaustion_during_raw_write_is_507_and_preserves_existing_edit(app, monkeypatch, winerror):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    store.update(pid, lambda value: value.update(draft={"keep_ranges": [{"start": 0, "end": 3}]}))
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid).get_json()
    ticket = app.extensions["cutroom_upload_storage"].get(pid, receipt["upload_token"])
    real_open = Path.open
    def full(path, *args, **kwargs):
        if path == ticket.path:
            error = OSError(errno.ENOSPC if winerror is None else errno.EIO, "synthetic disk exhaustion")
            if winerror is not None:
                error.winerror = winerror
            raise error
        return real_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", full)
    response = transfer(client, receipt)
    assert response.status_code == 507, response.get_json()
    assert response.get_json()["error"] == "insufficient_storage"
    assert response.get_json()["disk_free_bytes"] == 26 * GiB
    assert store.load(pid) == before
    assert not ticket.path.exists()
    assert not app.extensions["cutroom_upload_storage"].tickets


def test_disk_full_during_atomic_source_save_restores_old_original_and_draft(app, monkeypatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    original = store.project_dir(pid) / "media" / "source-A.mp4"
    original.write_bytes(b"old-original")
    def seed(value):
        value["sources"]["A"] = {"slot": "A", "name": "old.mp4", "relative_path": "media/source-A.mp4", **probe(original, None)}
        value["draft"] = {"keep_ranges": [{"start": 0, "end": 3}]}
    store.update(pid, seed)
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid).get_json()
    assert transfer(client, receipt).status_code == 200
    monkeypatch.setattr(server, "probe_media", probe)
    def fail_after_install(_pid, mutator, **_kwargs):
        mutator(copy.deepcopy(before))
        raise OSError(errno.ENOSPC, "synthetic project save exhaustion")
    monkeypatch.setattr(store, "update", fail_after_install)
    response = complete(client, pid, receipt)
    assert response.status_code == 507, response.get_json()
    assert store.load(pid) == before
    assert original.read_bytes() == b"old-original"
    assert not list(original.parent.glob(".incoming-*"))
    assert not list(original.parent.glob(".upload-*"))
    assert not list(original.parent.glob(".rollback-*"))


def test_legacy_multipart_disk_exhaustion_is_507_with_owned_cleanup(app, monkeypatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    before = copy.deepcopy(store.load(pid))
    def full(_uploaded, path, _limit):
        path.write_bytes(b"partial")
        raise OSError(errno.ENOSPC, "synthetic disk exhaustion")
    monkeypatch.setattr(server, "copy_upload", full)
    response = client.post(f"/api/projects/{pid}/sources/A", data={"file": (io.BytesIO(b"media"), "clip.mp4")})
    assert response.status_code == 507, response.get_json()
    assert store.load(pid) == before
    assert not list((store.project_dir(pid) / "media").glob(".upload-*"))
    assert not app.extensions["cutroom_upload_storage"].legacy


@pytest.mark.parametrize("transport", ["chunked-v1", "multipart"])
def test_final_original_fsync_exhaustion_preserves_existing_edit_and_owned_cleanup(app, monkeypatch, transport):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    store.update(pid, lambda value: value.update(draft={"keep_ranges": [{"start": 0, "end": 3}]}))
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid).get_json() if transport == "chunked-v1" else None
    monkeypatch.setattr(storage_module.os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError(errno.ENOSPC, "synthetic final-original flush exhaustion")))
    if receipt is not None:
        response = transfer(client, receipt)
    else:
        response = client.post(f"/api/projects/{pid}/sources/A", data={"file": (io.BytesIO(b"new-original"), "clip.mp4")})
    assert response.status_code == 507, response.get_json()
    assert store.load(pid) == before
    assert not list((store.project_dir(pid) / "media").glob(".incoming-*"))
    assert not list((store.project_dir(pid) / "media").glob(".upload-*"))
    assert not app.extensions["cutroom_upload_storage"].tickets


def test_waitress_rejects_large_legacy_upload_before_body_allocation(app):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    manager = app.extensions["cutroom_upload_storage"]
    parser = upload_channel_class(manager, 40 * GiB).parser_class(Adjustments(max_request_body_size=41 * GiB))
    header = (f"POST /api/projects/project_123456abcdef/sources/A HTTP/1.1\r\nHost: localhost\r\nContent-Length: {15 * GiB}\r\nContent-Type: multipart/form-data; boundary=test\r\n\r\n").encode()
    assert parser.received(header + b"body-must-not-be-spooled") == len(header + b"body-must-not-be-spooled")
    assert parser.error.error.status == 507
    assert parser.body_bytes_received == 0
    assert len(parser.body_rcv.getbuf()) == 0
    assert not manager.legacy
    parser.close()


@pytest.mark.parametrize("path", [
    "//api/projects/project_123456abcdef/sources/A",
    "/api//projects/project_123456abcdef/sources/A",
    "/api/projects/project_123456abcdef//assets",
])
def test_waitress_slash_normalization_does_not_bypass_prebody_admission(app, path):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    manager = app.extensions["cutroom_upload_storage"]
    parser = upload_channel_class(manager, 40 * GiB).parser_class(Adjustments(max_request_body_size=41 * GiB))
    size = 2 * GiB if path.endswith("/assets") else 15 * GiB
    # For assets, use a fresh free-space snapshot too small for its legacy copies.
    if path.endswith("/assets"):
        with manager.lock:
            manager.legacy["competing-import"] = {"same-volume": 22 * GiB}
    header = f"POST {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {size}\r\n\r\n".encode()
    parser.received(header)
    assert parser.error.error.status == 507
    assert parser.body_bytes_received == 0
    parser.close()


def test_waitress_credits_buffered_bytes_and_releases_legacy_reservation(app):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    manager = app.extensions["cutroom_upload_storage"]
    parser = upload_channel_class(manager, 40 * GiB).parser_class(Adjustments())
    header = b"POST /api/projects/project_123456abcdef/assets HTTP/1.1\r\nHost: localhost\r\nContent-Length: 32\r\n\r\n"
    parser.received(header)
    assert sum(manager.legacy[parser.storage_lease].values()) == 96
    parser.received(b"a" * 16)
    assert sum(manager.legacy[parser.storage_lease].values()) == 80
    parser.close()
    parser.close()
    assert not manager.legacy


def test_waitress_transport_enospc_returns_json_507_and_releases_only_own_buffer(app, monkeypatch):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    manager = app.extensions["cutroom_upload_storage"]
    parser = upload_channel_class(manager, 40 * GiB).parser_class(Adjustments())
    parser.received(b"POST /api/projects/project_123456abcdef/sources/B HTTP/1.1\r\nHost: localhost\r\nContent-Length: 32\r\n\r\n")
    monkeypatch.setattr(parser.body_rcv.getbuf(), "append", lambda _chunk: (_ for _ in ()).throw(OSError(errno.ENOSPC, "synthetic TEMP full")))
    assert parser.received(b"media") == 5
    status, headers, body = parser.error.to_response("test")
    assert status == "507 Insufficient Storage"
    assert ("Content-Type", "application/json") in headers
    assert b'"error": "insufficient_storage"' in body
    assert not manager.legacy


def test_waitress_admits_only_one_bounded_chunk_per_token(app):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    client = app.test_client()
    pid = project(app)["id"]
    receipt = preflight(client, pid).get_json()
    manager = app.extensions["cutroom_upload_storage"]
    parser_class = upload_channel_class(manager, 40 * GiB).parser_class
    header = (f"PUT {receipt['upload_url']} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 12\r\nX-Cutroom-Upload-Offset: 0\r\n\r\n").encode()
    first, second = parser_class(Adjustments()), parser_class(Adjustments())
    first.received(header)
    assert first.error is None
    second.received(header)
    assert second.error.error.status == 409
    second.close()
    first.close()
    third = parser_class(Adjustments())
    third.received(header)
    assert third.error is None
    third.close()


def test_admission_is_bounded_and_oversized_chunks_are_rejected_before_body(app):
    from cutroom.upload_storage import MAX_TICKETS
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    for _index in range(MAX_TICKETS):
        pid = project(app)["id"]
        assert preflight(client, pid).status_code == 201
    assert preflight(client, project(app)["id"]).status_code == 429
    assert len(manager.tickets) == MAX_TICKETS
    manager.close()


def test_oversized_chunk_and_unknown_target_reject_before_transport(app):
    from waitress.adjustments import Adjustments
    from cutroom.upload_transport import upload_channel_class
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    pid = project(app)["id"]
    receipt = preflight(client, pid, size=2 * CHUNK_BYTES).get_json()
    parser_class = upload_channel_class(manager, 40 * GiB).parser_class
    parser = parser_class(Adjustments())
    parser.received((f"PUT {receipt['upload_url']} HTTP/1.1\r\nHost: localhost\r\nContent-Length: {CHUNK_BYTES + 1}\r\nX-Cutroom-Upload-Offset: 0\r\n\r\n").encode())
    assert parser.error.error.status == 413
    assert parser.body_bytes_received == 0
    parser.close()
    for path, status in (("/api/projects/invalid/sources/A", 404), (f"/api/projects/{pid}/sources/C", 400), (f"/api/projects/{pid}/uploads/short", 400)):
        parser = parser_class(Adjustments())
        method = "PUT" if "/uploads/" in path else "POST"
        parser.received(f"{method} {path} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 16777216\r\n\r\n".encode())
        assert parser.error.error.status == status
        assert parser.body_bytes_received == 0
        parser.close()


def test_generic_source_cancel_during_validation_preserves_the_existing_project(app, monkeypatch):
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    store.update(pid, lambda value: value.update(draft={"keep_ranges": [{"start": 0, "end": 3}]}))
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid).get_json()
    assert transfer(client, receipt).status_code == 200
    entered, release = threading.Event(), threading.Event()
    def blocked(path, settings, *, original_filename=None):
        entered.set()
        assert release.wait(3)
        return probe(path, settings, original_filename=original_filename)
    monkeypatch.setattr(server, "probe_media", blocked)
    def finalize():
        with app.test_client() as worker:
            return complete(worker, pid, receipt)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(finalize)
        try:
            assert entered.wait(2)
            cancelled = client.post(receipt["cancel_url"])
            assert cancelled.status_code in {200, 202}
        finally:
            release.set()
        response = pending.result(timeout=3)
    assert response.status_code == 409, response.get_json()
    assert store.load(pid) == before
    assert not list((store.project_dir(pid) / "media").glob(".upload-*"))
    assert not app.extensions["cutroom_upload_storage"].tickets


def test_import_remains_durable_if_deferred_preparation_status_cannot_be_saved(app, monkeypatch):
    from cutroom.jobs import JobAdmissionError
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    receipt = preflight(client, pid).get_json()
    assert transfer(client, receipt).status_code == 200
    monkeypatch.setattr(server, "probe_media", probe)
    monkeypatch.setattr(app.extensions["cutroom_jobs"], "submit", lambda *_args, **_kwargs: (_ for _ in ()).throw(JobAdmissionError("synthetic queue full")))
    monkeypatch.setattr(server, "_mark_source_preparation", lambda *_args: (_ for _ in ()).throw(OSError(errno.ENOSPC, "synthetic deferred-status full")))
    response = complete(client, pid, receipt)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["preparation_deferred"] is True
    assert (store.project_dir(pid) / "media" / "source-A.mp4").read_bytes() == b"new-original"


def test_opaque_transport_handoff_credits_current_temp_buffer_at_exact_boundary(app, monkeypatch):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    pid = project(app)["id"]
    free = [RESERVE_BYTES + 12 + CHUNK_BYTES]
    monkeypatch.setattr(storage_module.shutil, "disk_usage", lambda _path: SimpleNamespace(free=free[0]))
    receipt = preflight(client, pid).get_json()
    ticket, lease = manager.begin_transport(pid, receipt["upload_token"], 0, 12)
    free[0] -= 12  # Waitress already holds these bytes in its TEMP spool.
    assert manager.append(pid, ticket.token, 0, 12, io.BytesIO(b"new-original"), transport_lease=lease) == 12
    assert ticket.transport_busy  # Held until the actual parser closes its buffer.
    manager.end_transport(ticket, lease)
    free[0] = RESERVE_BYTES + CHUNK_BYTES  # The original now occupies 12 bytes.
    assert manager.begin_finalize(pid, ticket.token, "source", "A") is ticket
    manager.finish(ticket)


def test_interrupted_chunk_cleans_only_owned_prefix_and_preserves_project(app):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid, size=24).get_json()
    ticket = manager.get(pid, receipt["upload_token"])
    with pytest.raises(UploadStorageError, match="before this chunk was complete") as result:
        manager.append(pid, ticket.token, 0, 24, io.BytesIO(b"short"))
    assert result.value.status == 400
    assert not ticket.path.exists()
    assert not manager.tickets
    assert store.load(pid) == before


def test_wrong_size_oversized_chunk_and_invalid_media_never_publish_source(app, monkeypatch):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    before = copy.deepcopy(store.load(pid))
    receipt = preflight(client, pid).get_json()
    assert transfer(client, receipt, b"longer-than-declared").status_code == 413
    assert store.load(pid) == before
    assert transfer(client, receipt).status_code == 200
    monkeypatch.setattr(server, "probe_media", lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("synthetic invalid media")))
    response = complete(client, pid, receipt)
    assert response.status_code == 422, response.get_json()
    assert store.load(pid) == before
    assert not list((store.project_dir(pid) / "media").glob(".incoming-*"))
    assert not list((store.project_dir(pid) / "media").glob(".upload-*"))


def test_restart_recovers_only_dead_owner_journal_partials(app, monkeypatch):
    manager = app.extensions["cutroom_upload_storage"]
    client = app.test_client()
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    receipt = preflight(client, pid, size=24).get_json()
    ticket = manager.get(pid, receipt["upload_token"])
    assert ticket.journal_path.is_file()
    assert not ticket.path.exists()  # Ownership is durable before original bytes.
    assert transfer(client, receipt).status_code == 200
    user_file = ticket.path.parent / ".incoming-user-file"
    user_file.write_bytes(b"preserve existing user file")
    malformed = manager.journal_dir / ("upload-" + "e" * 32 + ".json")
    malformed.write_text(json.dumps({"owner": "cutroom-upload-staging-v1", "pid": 1, "project_id": "../../outside"}), encoding="utf-8")
    # A second instance cannot recover a currently live owner's stage.
    live = UploadStorage(manager.data_dir, projects_dir=manager.projects_dir)
    assert ticket.path.read_bytes() == b"new-original"
    live.close()
    monkeypatch.setattr(storage_module, "process_alive", lambda _pid: False)
    recovered = UploadStorage(manager.data_dir, projects_dir=manager.projects_dir)
    try:
        assert not ticket.path.exists()
        assert not ticket.journal_path.exists()
        assert user_file.read_bytes() == b"preserve existing user file"
        assert malformed.exists()
        assert store.load(pid)["sources"]["A"] is None
    finally:
        recovered.close()


def test_live_waitress_raw_and_legacy_import_and_aborted_body_cleanup(app, monkeypatch):
    """Use actual sockets and Waitress TEMP buffering, not Flask's test transport."""
    from waitress import wasyncore
    from cutroom.upload_transport import create_upload_server
    monkeypatch.setattr(server, "probe_media", probe)
    listener = create_upload_server(app, host="127.0.0.1", port=0, threads=2,
                                    asyncore_loop_timeout=.02, inbuf_overflow=8,
                                    channel_timeout=1, cleanup_interval=1)
    worker = threading.Thread(target=listener.run, daemon=True)
    worker.start()
    connection = http.client.HTTPConnection("127.0.0.1", int(listener.effective_port), timeout=4)
    manager = app.extensions["cutroom_upload_storage"]
    store = app.extensions["cutroom_store"]
    pid = project(app)["id"]
    def call(method, path, body=b"", headers=None):
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    try:
        status, receipt = call("POST", f"/api/projects/{pid}/uploads/preflight", json.dumps({
            "purpose": "source", "slot": "A", "filename": "synthetic.mp4", "size_bytes": 12,
        }).encode(), {"Content-Type": "application/json"})
        assert status == 201, receipt
        status, result = call("PUT", receipt["upload_url"], b"new-original", {
            "Content-Type": "application/octet-stream", "X-Cutroom-Upload-Offset": "0",
        })
        assert status == 200, result
        assert result["received_bytes"] == 12
        assert not manager.get(pid, receipt["upload_token"]).transport_busy
        status, result = call("POST", f"/api/projects/{pid}/sources/A", headers={
            "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": receipt["upload_token"],
        })
        assert status == 201, result
        assert (store.project_dir(pid) / "media" / "source-A.mp4").read_bytes() == b"new-original"
        body = b'--test\r\nContent-Disposition: form-data; name="file"; filename="legacy.mp4"\r\nContent-Type: video/mp4\r\n\r\nlegacy-original\r\n--test--\r\n'
        status, result = call("POST", f"/api/projects/{pid}/sources/B", body, {"Content-Type": "multipart/form-data; boundary=test"})
        assert status == 201, result
        assert (store.project_dir(pid) / "media" / "source-B.mp4").read_bytes() == b"legacy-original"
        receipt = preflight(app.test_client(), pid, size=24).get_json()
        ticket = manager.get(pid, receipt["upload_token"])
        interrupted = socket.create_connection(("127.0.0.1", int(listener.effective_port)), timeout=3)
        interrupted.sendall((f"PUT {receipt['upload_url']} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 24\r\nContent-Type: application/octet-stream\r\nX-Cutroom-Upload-Offset: 0\r\n\r\nshort").encode())
        deadline = time.monotonic() + 1
        while not ticket.transport_busy and time.monotonic() < deadline:
            time.sleep(.01)
        assert ticket.transport_busy
        interrupted.close()
        deadline = time.monotonic() + 3
        while ticket.transport_busy and time.monotonic() < deadline:
            time.sleep(.01)
        assert not ticket.transport_busy
        assert ticket.received == 0
        assert not ticket.path.exists()
        assert manager.cancel(pid, ticket.token)
    finally:
        connection.close()
        listener.task_dispatcher.shutdown()
        wasyncore.close_all(listener._map)
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert not manager.legacy
