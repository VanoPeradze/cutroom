from __future__ import annotations

import ast
import http.client
import io
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from waitress.adjustments import Adjustments

import server
from cutroom.config import load_settings
from cutroom.upload_transport import upload_channel_class


class RequestSecurityTests(unittest.TestCase):
    """Synthetic, bounded transport checks; no real user data or cloud requests."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="cutroom-request-security-")
        self.environment = patch.dict(os.environ, {
            "CUTROOM_DATA_DIR": str(Path(self.temporary.name) / "data"),
            "CUTROOM_NO_BROWSER": "1",
        })
        self.environment.start()
        settings = load_settings()
        settings.raw["ai"]["enabled"] = False
        self.app = server.create_app(settings)
        self.app.config.update(TESTING=True)

    def tearDown(self):
        self.app.extensions["cutroom_upload_storage"].close()
        self.app.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)
        self.environment.stop()
        self.temporary.cleanup()

    def parser_for(self, **kwargs):
        storage = self.app.extensions["cutroom_upload_storage"]
        return upload_channel_class(storage, 40 * 1024**3).parser_class(
            Adjustments(max_request_body_size=40 * 1024**3 + 32 * 1024**2, **kwargs)
        )

    @staticmethod
    def status(parser):
        return parser.error.to_response("security-test")[0].split()[0] if parser.error else None

    def test_non_import_body_rejected_before_transport_spooling(self):
        for path in ["/api/projects", "/api/transcription/engine",
                     "/api/projects/project_000000000000/director/request-review",
                     "/api//projects", "/nonexistent", "/assets/app.js"]:
            for method in ["POST", "GET"]:
                with self.subTest(path=path, method=method):
                    parser = self.parser_for()
                    try:
                        header = (f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
                                  f"Content-Length: {server.JSON_BODY_LIMIT + 1}\r\n\r\n").encode()
                        packet = header + b"synthetic-body-must-not-be-spooled"
                        self.assertEqual(parser.received(packet), len(packet))
                        self.assertEqual(self.status(parser), "413")
                        self.assertEqual(parser.body_bytes_received, 0)
                        self.assertEqual(len(parser.body_rcv.getbuf()), 0)
                    finally:
                        parser.close()

    def test_cross_site_post_rejected_before_body_or_storage_lookup(self):
        for path in ["/api/projects", "/api/projects/project_000000000000/sources/A",
                     "/api/projects/project_000000000000/assets", "/nonexistent"]:
            with self.subTest(path=path):
                parser = self.parser_for()
                try:
                    header = (f"POST {path} HTTP/1.1\r\nHost: localhost\r\n"
                              "Sec-Fetch-Site: cross-site\r\nOrigin: https://untrusted.invalid\r\n"
                              "Content-Length: 32\r\n\r\n").encode()
                    parser.received(header)
                    self.assertEqual(self.status(parser), "403")
                    self.assertEqual(parser.body_bytes_received, 0)
                    self.assertFalse(self.app.extensions["cutroom_upload_storage"].legacy)
                finally:
                    parser.close()

    def test_chunked_non_import_cannot_escape_transport_limit(self):
        parser = self.parser_for(inbuf_overflow=4 * 1024**2)
        try:
            parser.received(b"POST /api/projects HTTP/1.1\r\nHost: localhost\r\nTransfer-Encoding: chunked\r\n\r\n")
            self.assertIsNone(parser.error)
            # Two bounded synthetic chunks, not an exhaustion attempt.
            chunk = b"a" * (600 * 1024)
            packet = f"{len(chunk):x}\r\n".encode() + chunk + b"\r\n"
            parser.received(packet)
            self.assertIsNone(parser.error)
            parser.received(packet)
            self.assertEqual(self.status(parser), "413")
        finally:
            parser.close()

    def test_request_limit_does_not_mutate_shared_waitress_adjustments(self):
        storage = self.app.extensions["cutroom_upload_storage"]
        shared = Adjustments(max_request_body_size=40 * 1024**3)
        parser = upload_channel_class(storage, 40 * 1024**3).parser_class(shared)
        try:
            parser.received(b"POST /api/projects HTTP/1.1\r\nHost: localhost\r\nContent-Length: 2\r\n\r\n")
            self.assertIsNone(parser.error)
            self.assertEqual(shared.max_request_body_size, 40 * 1024**3)
            self.assertLessEqual(parser.adj.max_request_body_size, server.JSON_BODY_LIMIT + 1)
        finally:
            parser.close()

    def test_caption_import_keeps_larger_bounded_transport_allowance(self):
        limit = server.MAX_CAPTION_IMPORT_BYTES * 6 + 4096
        for size, expected in [(server.JSON_BODY_LIMIT + 1, None), (limit, None), (limit + 1, "413")]:
            with self.subTest(size=size):
                parser = self.parser_for()
                try:
                    parser.received(("POST /api/projects/project_000000000000/manual/edit HTTP/1.1\r\n"
                                     f"Host: localhost\r\nContent-Length: {size}\r\n\r\n").encode())
                    self.assertEqual(self.status(parser), expected)
                    self.assertEqual(parser.body_bytes_received, 0)
                finally:
                    parser.close()

    def test_all_json_handlers_reject_large_bodies_before_reading(self):
        class NeverRead(io.BytesIO):
            def read(self, *args):
                raise AssertionError("Oversized JSON must be rejected before reading")
            def readinto(self, *args):
                raise AssertionError("Oversized JSON must be rejected before reading")

        for path in ["/api/transcription/engine", "/api/projects/project_000000000000/director/request-review"]:
            with self.subTest(path=path):
                response = self.app.test_client().post(path, content_type="application/json", environ_overrides={
                    "CONTENT_LENGTH": str(server.JSON_BODY_LIMIT + 1), "wsgi.input": NeverRead(),
                })
                self.assertEqual(response.status_code, 413)

    def test_legitimate_large_media_still_uses_storage_admission(self):
        project = self.app.extensions["cutroom_store"].create("Synthetic admission fixture")
        parser = self.parser_for()
        try:
            parser.received((f"POST /api/projects/{project['id']}/sources/A HTTP/1.1\r\n"
                             f"Host: localhost\r\nContent-Length: {2 * 1024**2}\r\n\r\n").encode())
            self.assertIsNone(parser.error)
            self.assertTrue(parser.storage_lease)
            self.assertGreater(parser.adj.max_request_body_size, 2 * 1024**2)
            self.assertEqual(parser.body_bytes_received, 0)
        finally:
            parser.close()
        self.assertFalse(self.app.extensions["cutroom_upload_storage"].legacy)

    def test_live_waitress_rejects_before_body_and_accepts_normal_json(self):
        from waitress import wasyncore
        from cutroom.upload_transport import create_upload_server

        listener = create_upload_server(self.app, host="127.0.0.1", port=0, threads=1,
                                        asyncore_loop_timeout=.02,
                                        max_request_body_size=40 * 1024**3)
        worker = threading.Thread(target=listener.run, daemon=True)
        worker.start()
        try:
            for route, headers, expected in [
                ("/api/projects", {"Content-Length": "2147483648"}, 413),
                ("/api/projects", {"Content-Length": "32", "Sec-Fetch-Site": "cross-site"}, 403),
            ]:
                connection = http.client.HTTPConnection("127.0.0.1", listener.effective_port, timeout=3)
                try:
                    connection.putrequest("POST", route)
                    for name, value in headers.items():
                        connection.putheader(name, value)
                    connection.endheaders()  # Deliberately no body sent or allocated.
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                finally:
                    connection.close()
            connection = http.client.HTTPConnection("127.0.0.1", listener.effective_port, timeout=3)
            try:
                connection.request("POST", "/api/projects", body=b'{"name":"Synthetic audit project"}',
                                   headers={"Content-Type": "application/json"})
                response = connection.getresponse()
                self.assertEqual(response.status, 201)
                response.read()
            finally:
                connection.close()
        finally:
            listener.task_dispatcher.shutdown()
            wasyncore.close_all(listener._map)
            worker.join(timeout=3)
        self.assertFalse(worker.is_alive())

    def test_json_handler_registry_covers_all_json_readers(self):
        tree = ast.parse(Path(server.__file__).read_text(encoding="utf-8"))
        json_handlers = {node.name for node in ast.walk(tree)
                         if isinstance(node, ast.FunctionDef) and node.decorator_list
                         and any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                                 and call.func.id == "_json_object" for call in ast.walk(node))}
        covered = server.JSON_BODY_ENDPOINTS | {"save_ai_connection", "manual_draft"}
        self.assertEqual(json_handlers - covered, set())


if __name__ == "__main__":
    unittest.main()
