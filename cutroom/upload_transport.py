"""App-specific Waitress admission, before its full-request TEMP buffering.

No global patches: each CUTROOM listener owns its channel and parser classes.
Other WSGI hosts still receive Flask admission before multipart parsing, but
their pre-WSGI buffering policy is outside the application's control.
"""
from __future__ import annotations

import json
import re
from http import HTTPStatus
from typing import Any

from .upload_storage import TOKEN_RE, UploadStorage, UploadStorageError, is_storage_full

IMPORT_PATH = re.compile(r"/api/projects/([^/]+)/(?:sources/([^/]+)|assets)\Z")
CHUNK_PATH = re.compile(r"/api/projects/([^/]+)/uploads/([^/]+)\Z")
PREFLIGHT_PATH = re.compile(r"/api/projects/([^/]+)/uploads/preflight\Z")
# Legacy multipart remains bounded before Waitress buffers a complete body.
# This is a transport ceiling, not the video asset's configured file-size limit.
LEGACY_ASSET_UPLOAD_BYTES = 2 * 1024**3
MULTIPART_ALLOWANCE_BYTES = 1024**2


class StorageHTTPError:
    def __init__(self, error: UploadStorageError):
        self.error = error

    def to_response(self, _ident: str):
        return (f"{self.error.status} {HTTPStatus(self.error.status).phrase}",
                [("Content-Type", "application/json"), ("Cache-Control", "no-store"),
                 ("X-Content-Type-Options", "nosniff")],
                json.dumps(self.error.public()).encode("utf-8"))


def upload_channel_class(storage: UploadStorage, max_upload_bytes: int):
    from waitress.channel import HTTPChannel
    from waitress.parser import HTTPRequestParser
    from waitress.task import WSGITask

    class UploadRequestParser(HTTPRequestParser):
        storage_lease = ""
        upload_ticket = None
        upload_lease = ""
        storage_closed = False
        import_request = False
        data_path = None

        def reject(self, error: UploadStorageError) -> None:
            self.error = StorageHTTPError(error)
            self.completed = True
            self.expect_continue = False
            self.connection_close = True

        def parse_header(self, header_plus):
            super().parse_header(header_plus)
            # Ownership is passed only in WSGI environ, never a client header.
            self.headers.pop("X_CUTROOM_STORAGE_LEASE", None)
            self.headers.pop("X_CUTROOM_CHUNK_LEASE", None)
            # Match the exact method/path normalization performed by WSGITask.
            # Werkzeug also merges internal repeated slashes before redirecting.
            # Such a redirect must not bypass admission for its original body.
            path = re.sub(r"/{2,}", "/", self.path)
            prefix = self.adj.url_prefix
            if prefix and path.startswith(prefix + "/"):
                path = path[len(prefix):]
            method = self.command.upper()
            source = IMPORT_PATH.fullmatch(path)
            chunk = CHUNK_PATH.fullmatch(path) if method == "PUT" else None
            preflight = PREFLIGHT_PATH.fullmatch(path) if method == "POST" else None
            if not (source and method == "POST" or chunk or preflight):
                return
            self.import_request = True
            try:
                target = source or chunk or preflight
                self.data_path = storage.target_dir(target[1])
                if source and source[2] is not None and source[2].upper() not in {"A", "B"}:
                    raise UploadStorageError("invalid_slot", "Slot must be A or B.", 400)
                if chunk and not TOKEN_RE.fullmatch(chunk[2]):
                    raise UploadStorageError("invalid_upload_token", "The upload token is invalid.", 400)
                if self.chunked or "CONTENT_LENGTH" not in self.headers:
                    raise UploadStorageError("upload_length_required", "File transfers require a Content-Length header.", 411)
                if chunk:
                    offset = self.headers.get("X_CUTROOM_UPLOAD_OFFSET", "")
                    if not offset.isascii() or not offset.isdigit() or len(offset) > 16:
                        raise UploadStorageError("invalid_upload_offset", "An integer upload offset is required.", 400)
                    self.upload_ticket, self.upload_lease = storage.begin_transport(chunk[1], chunk[2], int(offset), self.content_length)
                elif preflight or self.headers.get("X_CUTROOM_UPLOAD_TRANSPORT") == "chunked-v1":
                    if self.content_length > 1024**2:
                        raise UploadStorageError("request_too_large", "The import metadata request is too large.", 413)
                else:
                    if self.content_length > max_upload_bytes + MULTIPART_ALLOWANCE_BYTES:
                        raise UploadStorageError("file_too_large", "The selected file is larger than the import limit.", 413)
                    if path.endswith("/assets") and self.content_length > LEGACY_ASSET_UPLOAD_BYTES + MULTIPART_ALLOWANCE_BYTES:
                        raise UploadStorageError("chunked_upload_required", "Use chunked import for a media-library file larger than 2 GiB.", 413,
                                                 transport="chunked-v1", max_multipart_bytes=LEGACY_ASSET_UPLOAD_BYTES)
                    self.storage_lease = storage.admit_legacy(self.content_length, before_transport=True, data_path=self.data_path)
            except UploadStorageError as error:
                self.reject(error)

        def received(self, data):
            before = self.body_bytes_received
            try:
                consumed = super().received(data)
                if self.storage_lease:
                    storage.credit_transport(self.storage_lease, self.body_bytes_received - before)
                # Discard any same-packet body following rejected headers; it
                # must not be interpreted as a second, pipelined request.
                return len(data) if self.error else consumed
            except OSError as error:
                if not self.import_request or not is_storage_full(error):
                    raise
                self.reject(storage.storage_error(self.upload_ticket, transport="chunked-v1" if self.upload_ticket else "multipart", data_path=self.data_path))
                if self.upload_ticket is not None:
                    storage.cancel(self.upload_ticket.project_id, self.upload_ticket.token)
                self.close()
                return len(data)

        def close(self):
            if self.storage_closed:
                return
            self.storage_closed = True
            try:
                super().close()
            finally:
                if self.storage_lease:
                    storage.release_legacy(self.storage_lease)
                if self.upload_ticket is not None:
                    storage.end_transport(self.upload_ticket, self.upload_lease)

    class UploadWSGITask(WSGITask):
        def get_environment(self):
            environment = super().get_environment()
            environment["cutroom.upload.storage_lease"] = self.request.storage_lease
            if self.request.upload_ticket is not None:
                environment["cutroom.upload.transport_lease"] = self.request.upload_lease
                # Flask releases this already-read raw input buffer before
                # sending its acknowledgement. The next request can then rely
                # on the exact admitted TEMP budget, including at its boundary.
                environment["cutroom.upload.release_transport"] = self.request.close
            return environment

    class UploadHTTPChannel(HTTPChannel):
        parser_class = UploadRequestParser
        task_class = UploadWSGITask

        def handle_close(self):
            # Upstream closes completed requests after service, but an aborted
            # request that never reached WSGI also owns a buffer and reservation.
            if self.request is not None:
                self.request.close()
                self.request = None
            super().handle_close()

        def cancel(self):
            if self.request is not None:
                self.request.close()
                self.request = None
            for pending in self.requests:
                pending.close()
            super().cancel()

    return UploadHTTPChannel


def create_upload_server(application, **kwargs: Any):
    from waitress.server import BaseWSGIServer, create_server
    server = create_server(application, **kwargs)
    storage = application.extensions["cutroom_upload_storage"]
    limit = int(float(application.extensions["cutroom_settings"].raw.get("max_upload_gb", 40)) * 1024**3)
    channel = upload_channel_class(storage, limit)
    listeners = [server] if isinstance(server, BaseWSGIServer) else list(server.map.values())
    for listener in listeners:
        if isinstance(listener, BaseWSGIServer):
            listener.channel_class = channel
    return server
