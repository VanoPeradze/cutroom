"""Opt-in cloud AI. No SDK, shared key, automatic retry or provider fallback.

Connection preferences are installation-local; credentials live in memory only
(or in a user-managed environment variable). A job receives an immutable copy.
"""
from __future__ import annotations

import copy
import http.client
import ipaddress
import json
import math
import os
import re
import socket
import ssl
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .utils import atomic_write_json, normalize_text

DEFAULT_MODEL = "openai/gpt-oss-120b"
TRANSCRIPT_MODEL = "whisper-large-v3"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
COMPATIBLE_PROVIDER = "openai-compatible"
MODEL_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")
_ALLOWED_REQUEST_PATHS = frozenset({"chat/completions", "audio/transcriptions"})
_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".home",
    ".lan",
    ".test",
    ".invalid",
    ".example",
)


class CloudAIError(RuntimeError):
    """Safe to display: never includes credentials, request data or remote body."""


def _valid_model_id(value: Any) -> bool:
    return isinstance(value, str) and MODEL_ID_PATTERN.fullmatch(value) is not None


def _normalize_base_url(value: Any) -> str:
    """Validate and canonicalize an explicitly approved OpenAI-compatible root.

    The URL is an API root such as ``https://api.example.com/v1``. CUTROOM adds
    only the two documented OpenAI-compatible paths. Query strings, fragments,
    credentials and ambiguous host spellings are rejected instead of normalized
    because the API key must never be sent to a destination the user did not see.
    """

    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("Enter a valid HTTPS API base URL.")
    if any(ord(character) < 33 or ord(character) == 127 for character in value):
        raise ValueError("The API base URL cannot contain whitespace or control characters.")
    if "\\" in value or "?" in value or "#" in value:
        raise ValueError("The API base URL cannot contain a query, fragment, or backslash.")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Enter a valid HTTPS API base URL.") from exc
    if parsed.scheme.lower() != "https" or not parsed.netloc or not parsed.hostname:
        raise ValueError("The compatible API base URL must use HTTPS.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("The API base URL cannot contain a username or password.")
    if parsed.query or parsed.fragment:
        raise ValueError("The API base URL cannot contain a query or fragment.")

    raw_host = parsed.hostname
    if not raw_host.isascii() or "%" in raw_host or raw_host.endswith("."):
        raise ValueError("Enter an unambiguous public API hostname.")
    host = raw_host.lower()
    if host == "localhost" or host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise ValueError("The compatible API must use a public internet destination.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError("The compatible API must use a public internet destination.")

    path = parsed.path.rstrip("/")
    if path and not path.startswith("/"):
        raise ValueError("Enter a valid HTTPS API base URL.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("Enter a valid HTTPS API port.")
    display_host = f"[{host}]" if ":" in host else host
    authority = display_host if port in {None, 443} else f"{display_host}:{port}"
    return f"https://{authority}{path}"


def _connection_scope(preferences: dict[str, Any]) -> tuple[str, str, str]:
    """Bind an in-memory secret to exactly one provider destination."""

    return (
        str(preferences.get("mode") or "local"),
        str(preferences.get("provider") or "groq"),
        str(preferences.get("base_url") or GROQ_BASE_URL),
    )


def _default_preferences() -> dict[str, str]:
    return {
        "mode": "local",
        "provider": "groq",
        "model": DEFAULT_MODEL,
        "transcript_model": TRANSCRIPT_MODEL,
        "base_url": GROQ_BASE_URL,
    }


class ConnectionStore:
    def __init__(self, settings):
        self.path = settings.data_dir / "ai-connection.json"
        self.lock = threading.RLock()
        self.key = ""
        self.key_scope: tuple[str, str, str] | None = None
        self.preferences = _default_preferences()
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.preferences = self._validate(saved)
        except (OSError, ValueError, TypeError):
            pass
        # An environment key is a Groq-only convenience. If this installation was
        # saved on another destination, changing back to Groq requires a fresh,
        # explicit key instead of silently reviving the old environment secret.
        self._groq_environment_allowed = self.preferences["provider"] == "groq"

    @staticmethod
    def _validate(payload):
        if not isinstance(payload, dict):
            raise ValueError("Choose an AI connection.")
        mode = payload.get("mode", "local")
        provider = payload.get("provider", "groq")
        model = payload.get("model", DEFAULT_MODEL)
        if not isinstance(mode, str) or mode not in {"local", "free", "own"}:
            raise ValueError("Choose Local AI, Groq, or your own compatible API.")
        if not isinstance(provider, str) or provider not in {"groq", COMPATIBLE_PROVIDER}:
            raise ValueError("Choose Groq or an OpenAI-compatible API.")
        if not _valid_model_id(model):
            raise ValueError("Enter a valid chat model ID.")

        if provider == "groq":
            supplied_base = payload.get("base_url", GROQ_BASE_URL)
            if supplied_base != GROQ_BASE_URL:
                raise ValueError("Groq uses its fixed official API endpoint.")
            supplied_transcript = payload.get("transcript_model", TRANSCRIPT_MODEL)
            if supplied_transcript != TRANSCRIPT_MODEL:
                raise ValueError("Groq cloud transcription uses whisper-large-v3.")
            return {
                "mode": mode,
                "provider": "groq",
                "model": model,
                "transcript_model": TRANSCRIPT_MODEL,
                "base_url": GROQ_BASE_URL,
            }

        if mode != "own":
            raise ValueError("An OpenAI-compatible API is available only with Use my own API.")
        if "model" not in payload:
            raise ValueError("Enter a valid chat model ID.")
        if "base_url" not in payload:
            raise ValueError("Enter the HTTPS base URL for your compatible API.")
        if "transcript_model" not in payload or not _valid_model_id(payload.get("transcript_model")):
            raise ValueError("Enter a valid transcription model ID.")
        return {
            "mode": "own",
            "provider": COMPATIBLE_PROVIDER,
            "model": model,
            "transcript_model": payload["transcript_model"],
            "base_url": _normalize_base_url(payload["base_url"]),
        }

    def snapshot(self):
        with self.lock:
            scope = _connection_scope(self.preferences)
            key = self.key if self.key_scope == scope else ""
            if (
                not key
                and self.preferences["provider"] == "groq"
                and self.preferences["mode"] != "local"
                and self._groq_environment_allowed
            ):
                key = os.environ.get("CUTROOM_GROQ_API_KEY", "")
            return {**copy.deepcopy(self.preferences), "api_key": key}

    def public(self):
        snapshot = self.snapshot()
        has_key = bool(snapshot.pop("api_key"))
        label = "Groq" if snapshot["provider"] == "groq" else "OpenAI-compatible"
        return {
            **snapshot,
            "has_key": has_key,
            "configured": snapshot["mode"] == "local" or has_key,
            "key_storage": "session",
            "provider_label": label,
        }

    def update(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("Choose an AI connection.")
        if set(payload) - {
            "mode", "provider", "model", "transcript_model", "base_url", "api_key",
            "consent", "endpoint_consent", "clear_key",
        }:
            raise ValueError("Unknown connection setting.")
        preferences = self._validate(payload)
        key = payload.get("api_key", "")
        if not isinstance(key, str) or len(key) > 512 or (key and not re.fullmatch(r"[!-~]+", key)):
            raise ValueError("Enter a valid API key without whitespace.")
        if preferences["mode"] != "local" and payload.get("consent") is not True:
            raise ValueError("Confirm cloud processing and your provider's billing plan first.")
        if preferences["provider"] == COMPATIBLE_PROVIDER:
            consented_endpoint = payload.get("endpoint_consent")
            try:
                consented_endpoint = _normalize_base_url(consented_endpoint)
            except ValueError as exc:
                raise ValueError("Confirm the exact compatible API endpoint first.") from exc
            if consented_endpoint != preferences["base_url"]:
                raise ValueError("Confirm the exact compatible API endpoint first.")
        if "clear_key" in payload and not isinstance(payload["clear_key"], bool):
            raise ValueError("Invalid clear-key setting.")
        with self.lock:
            previous_scope = _connection_scope(self.preferences)
            next_scope = _connection_scope(preferences)
            destination_changed = next_scope != previous_scope
            # Write only non-secret preferences, before committing in-memory state.
            atomic_write_json(self.path, preferences)
            self.preferences = preferences
            if destination_changed:
                self.key = ""
                self.key_scope = None
                self._groq_environment_allowed = False
            if payload.get("clear_key"):
                self.key = ""
                self.key_scope = None
            elif key:
                self.key = key
                self.key_scope = next_scope
            return self.public()

    def job_settings(self, settings):
        raw = copy.deepcopy(settings.raw)
        raw["ai"]["cloud_connection"] = self.snapshot()
        return replace(settings, raw=raw)


def connection(settings):
    return settings.ai.get("cloud_connection") or {"mode": "local"}


def enabled(settings):
    return connection(settings).get("mode", "local") != "local"


def require_connection(settings):
    selected = connection(settings)
    provider = str(selected.get("provider") or "groq")
    if provider not in {"groq", COMPATIBLE_PROVIDER}:
        raise CloudAIError("The selected cloud AI provider is not supported.")
    if not _valid_model_id(selected.get("model")):
        raise CloudAIError("The selected chat model ID is invalid. Reconnect it in AI connection.")
    if provider == COMPATIBLE_PROVIDER:
        if selected.get("mode") != "own":
            raise CloudAIError("OpenAI-compatible connections require Use my own API.")
        try:
            _normalize_base_url(selected.get("base_url"))
        except ValueError:
            raise CloudAIError("The selected compatible API endpoint is invalid. Reconnect it in AI connection.") from None
        if not _valid_model_id(selected.get("model")) or not _valid_model_id(selected.get("transcript_model")):
            raise CloudAIError("The compatible API model settings are invalid. Reconnect it in AI connection.")
    elif selected.get("base_url", GROQ_BASE_URL) != GROQ_BASE_URL:
        raise CloudAIError("The Groq connection endpoint is invalid. Reconnect it in AI connection.")
    if not selected.get("api_key"):
        label = "Groq" if provider == "groq" else "your compatible provider"
        raise CloudAIError(f"Cloud AI needs the API key for {label}. Open AI connection and reconnect it.")
    key = selected.get("api_key")
    if not isinstance(key, str) or len(key) > 512 or re.fullmatch(r"[!-~]+", key) is None:
        raise CloudAIError("The selected cloud API key is invalid. Reconnect it in AI connection.")
    return selected


def _resolve_public_addresses(host: str, port: int) -> list[str]:
    """Resolve every address and reject the whole endpoint if any is non-public."""

    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise CloudAIError("The compatible API hostname could not be resolved.") from exc
    addresses: list[str] = []
    for answer in answers:
        try:
            address = str(answer[4][0]).split("%", 1)[0]
            parsed = ipaddress.ip_address(address)
        except (IndexError, TypeError, ValueError):
            raise CloudAIError("The compatible API hostname returned an invalid network address.") from None
        if not parsed.is_global:
            raise CloudAIError("The compatible API endpoint resolved to a local or reserved network address.")
        canonical = str(parsed)
        if canonical not in addresses:
            addresses.append(canonical)
    if not addresses:
        raise CloudAIError("The compatible API hostname returned no usable public address.")
    return addresses


class _AbortableHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that cannot resume sending after its caller has stopped."""

    def __init__(self, *args, **kwargs):
        if kwargs.get("context") is None:
            kwargs["context"] = ssl.create_default_context()
        super().__init__(*args, **kwargs)
        self._cutroom_aborted = threading.Event()

    def _ensure_active(self) -> None:
        if self._cutroom_aborted.is_set():
            super().close()
            raise OSError("request aborted")

    def abort(self) -> None:
        """Prevent a pending connection from sending after its caller has stopped."""

        self._cutroom_aborted.set()
        super().close()

    def connect(self) -> None:
        self._ensure_active()
        super().connect()
        self._ensure_active()

    def request(self, *args, **kwargs) -> None:
        self._ensure_active()
        return super().request(*args, **kwargs)

    def send(self, data) -> None:
        # HTTPConnection normally connects and sends inside one method. Split the
        # two steps so cancellation is checked after a blocking TCP/TLS connect
        # and immediately before headers or multipart audio can leave the host.
        self._ensure_active()
        if self.sock is None:
            self.connect()
        self._ensure_active()
        return super().send(data)


class _PinnedHTTPSConnection(_AbortableHTTPSConnection):
    """HTTPS with public DNS resolved once and pinned before credentials are sent."""

    def __init__(self, host: str, port: int, address: str, timeout: int | float):
        super().__init__(host, port=port, timeout=timeout, context=ssl.create_default_context())
        self._cutroom_address = address

    def connect(self) -> None:
        # No CONNECT tunnel or environment proxy is supported. TLS still verifies
        # and sends SNI for the user-approved hostname, not for the pinned IP.
        self._ensure_active()
        raw_socket = socket.create_connection(
            (self._cutroom_address, self.port),
            self.timeout,
            self.source_address,
        )
        tls_socket = None
        try:
            self._ensure_active()
            tls_socket = self._context.wrap_socket(raw_socket, server_hostname=self.host)
            self._ensure_active()
        except BaseException:
            if tls_socket is not None:
                tls_socket.close()
            else:
                raw_socket.close()
            raise
        self.sock = tls_socket


def _compatible_client(selected: dict[str, Any], timeout: int | float) -> tuple[http.client.HTTPSConnection, str]:
    try:
        base_url = _normalize_base_url(selected.get("base_url"))
    except ValueError:
        raise CloudAIError("The selected compatible API endpoint is invalid. Reconnect it in AI connection.") from None
    parsed = urlsplit(base_url)
    host = str(parsed.hostname)
    port = int(parsed.port or 443)
    address = _resolve_public_addresses(host, port)[0]
    return _PinnedHTTPSConnection(host, port, address, timeout), parsed.path.rstrip("/")


def _groq_client(timeout: int | float) -> http.client.HTTPSConnection:
    return _AbortableHTTPSConnection("api.groq.com", timeout=timeout)


def _request(path, key, body, content_type="application/json", cancel_check=None, timeout=180, connection=None):
    """Send one request without redirects, retries, proxies or remote error text.

    The positional signature remains compatible with the original fixed-Groq
    transport and its test hooks. A validated ``connection`` is supplied only for
    the explicit OpenAI-compatible provider.
    """

    if path not in _ALLOWED_REQUEST_PATHS:
        raise CloudAIError("Cloud AI refused an unsupported API operation.")
    if cancel_check:
        cancel_check()
    selected = connection if isinstance(connection, dict) else {"provider": "groq"}
    provider = str(selected.get("provider") or "groq")
    if provider == COMPATIBLE_PROVIDER:
        if selected.get("mode") != "own":
            raise CloudAIError("OpenAI-compatible connections require Use my own API.")
        client, prefix = _compatible_client(selected, timeout)
        request_path = f"{prefix}/{path}" if prefix else f"/{path}"
    elif provider == "groq":
        client = _groq_client(timeout)
        request_path = "/openai/v1/" + path
    else:
        raise CloudAIError("The selected cloud AI provider is not supported.")
    done = threading.Event()
    result = {}

    def send():
        if cancel_check:
            try:
                # Close the small race between the caller's preflight check and
                # the worker actually sending the Authorization header.
                cancel_check()
            except BaseException as error:
                result["error"] = error
                done.set()
                return
        try:
            client.request("POST", request_path, body=body, headers={
                "Authorization": "Bearer " + key, "Content-Type": content_type,
            })
            response = client.getresponse()
            if response.status != 200:
                messages = {
                    401: "The API key was rejected. Check it in AI connection.",
                    403: "Your provider account does not allow this request.",
                    413: "The provider rejected the audio size. No alternate service was used.",
                    429: "Cloud AI reached a rate or quota limit. Wait or check your provider account, then retry. CUTROOM did not switch plans or providers.",
                }
                raise CloudAIError(messages.get(response.status, f"Cloud AI could not complete the request (HTTP {response.status}). Check the selected model and provider status."))
            data = response.read(8 * 1024 * 1024 + 1)
            if len(data) > 8 * 1024 * 1024:
                raise CloudAIError("Cloud AI returned an oversized response.")
            parsed = json.loads(data)
            if not isinstance(parsed, dict):
                raise ValueError("object required")
            result["value"] = parsed
        except CloudAIError as error:
            result["error"] = error
        except Exception:
            result["error"] = CloudAIError("Cloud AI connection failed or returned invalid data. Check your internet connection and retry.")
        finally:
            done.set()

    worker = threading.Thread(target=send, name="cutroom-cloud-request", daemon=True)
    worker.start()
    deadline = time.monotonic() + timeout
    try:
        while not done.wait(.1):
            if cancel_check:
                cancel_check()
            if time.monotonic() >= deadline:
                raise CloudAIError("Cloud AI timed out. No automatic retry was made.")
        if cancel_check:
            cancel_check()
        if "error" in result:
            raise result["error"]
        return result["value"]
    finally:
        abort = getattr(client, "abort", None)
        if callable(abort):
            abort()
        else:
            client.close()


def chat(settings, payload, cancel_check=None, timeout=180):
    selected = require_connection(settings)
    messages = copy.deepcopy(payload.get("messages", []))
    schema = payload.get("format")
    if isinstance(schema, dict):
        messages.append({"role": "system", "content": "Return only JSON matching this schema: " + json.dumps(schema)})
    body = {
        "model": selected["model"], "messages": messages,
        "response_format": {"type": "json_object"},
        "max_completion_tokens": min(8192, max(256, int(payload.get("options", {}).get("num_predict", 4096)))),
    }
    request_options = {"cancel_check": cancel_check, "timeout": timeout}
    if selected.get("provider") == COMPATIBLE_PROVIDER:
        request_options["connection"] = selected
    response = _request("chat/completions", selected["api_key"], json.dumps(body).encode(), **request_options)
    try:
        choice = response["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete response")
        parsed = json.loads(choice["message"]["content"])
        if not isinstance(parsed, dict):
            raise ValueError("object required")
        return parsed
    except (KeyError, IndexError, TypeError, ValueError):
        raise CloudAIError("Cloud AI did not return a complete structured edit. Your footage is unchanged; retry or choose another model.") from None


def _multipart(audio, language, model=TRANSCRIPT_MODEL):
    if not _valid_model_id(model):
        raise CloudAIError("The selected transcription model ID is invalid.")
    boundary = "cutroom-" + uuid.uuid4().hex
    fields = [("model", model), ("response_format", "verbose_json"),
              ("timestamp_granularities[]", "word"), ("timestamp_granularities[]", "segment")]
    if language and language != "auto":
        fields.append(("language", language))
    parts = []
    for name, value in fields:
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="audio.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode(),
                  audio, f"\r\n--{boundary}--\r\n".encode()])
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def transcribe_cloud(media_path: Path, settings, language=None, progress=None, duration=0.0, cancel_check=None):
    from .media import probe_media, run_command
    from .transcription import _coverage_from_chunks, _language_code

    selected = require_connection(settings)
    check = cancel_check or (lambda: None)
    check()
    duration = float(duration or probe_media(media_path, settings).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise CloudAIError("Could not determine the recording duration for cloud transcription.")
    segments, all_words, chunks = [], [], []
    detected = language if language and language != "auto" else None
    count = math.ceil(duration / 300)
    with tempfile.TemporaryDirectory(prefix="cutroom-cloud-", dir=settings.cache_dir) as temp:
        for index in range(count):
            check()
            core_start, core_end = index * 300.0, min(duration, (index + 1) * 300.0)
            start, end = max(0, core_start - 1), min(duration, core_end + 1)
            audio = Path(temp) / "audio.wav"
            run_command([settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start),
                         "-i", str(media_path), "-t", str(end - start), "-vn", "-ac", "1", "-ar", "16000",
                         "-c:a", "pcm_s16le", str(audio)], timeout=180, cancel_check=check)
            actual = float(probe_media(audio, settings).get("duration", 0))
            if actual < end - start - .25:
                raise CloudAIError("Audio preparation ended early. CUTROOM stopped instead of using a partial transcript.")
            if audio.stat().st_size > 24_000_000:
                raise CloudAIError("Prepared audio exceeded the safe cloud upload limit.")
            transcript_model = str(selected.get("transcript_model") or TRANSCRIPT_MODEL)
            body, mime = _multipart(audio.read_bytes(), language, transcript_model)
            if progress:
                progress(index / count, f"Cloud transcription · part {index + 1} of {count}")
            if selected.get("provider") == COMPATIBLE_PROVIDER:
                response = _request(
                    "audio/transcriptions",
                    selected["api_key"],
                    body,
                    mime,
                    check,
                    connection=selected,
                )
            else:
                response = _request("audio/transcriptions", selected["api_key"], body, mime, check)
            check()
            if not detected:
                code = str(response.get("language") or "unknown").lower()
                detected = _language_code({"hebrew": "he", "english": "en", "arabic": "ar", "russian": "ru", "spanish": "es", "french": "fr", "german": "de"}.get(code, code))
            words = []
            remote_words = response.get("words", [])
            if not isinstance(remote_words, list):
                raise CloudAIError("Cloud transcription returned invalid word timings.")
            for raw in remote_words:
                try:
                    left, right = float(raw["start"]) + start, float(raw["end"]) + start
                    text = str(raw["word"]).strip()
                    if not all(math.isfinite(t) for t in (left, right)) or right <= left or not text or left < start - .1 or right > end + .1:
                        raise ValueError()
                    if core_start <= (left + right) / 2 < core_end:
                        words.append({"start": round(max(0, left), 3), "end": round(min(duration, right), 3), "word": text})
                except (KeyError, TypeError, ValueError):
                    raise CloudAIError("Cloud transcription returned invalid word timings.") from None
            if str(response.get("text") or "").strip() and not response.get("words"):
                raise CloudAIError("Cloud transcription omitted word timings. CUTROOM stopped instead of guessing caption positions.")
            # Group real timed words into readable segments. Chunk overlap
            # ownership avoids repeating the same word at each upload boundary.
            words.sort(key=lambda word: (word["start"], word["end"]))
            group = []
            for word in words:
                group.append(word)
                if len(group) >= 18 or word["word"].endswith((".", "!", "?", "。", "？")):
                    segments.append({"start": group[0]["start"], "end": group[-1]["end"], "text": " ".join(w["word"] for w in group), "words": group})
                    group = []
            if group:
                segments.append({"start": group[0]["start"], "end": group[-1]["end"], "text": " ".join(w["word"] for w in group), "words": group})
            all_words.extend(words)
            chunks.append({"start": core_start, "end": core_end, "analyzed_end": core_end, "status": "complete"})
    for index, row in enumerate(segments):
        row.update(id=f"s{index + 1:04d}", normalized=normalize_text(row["text"]))
    if progress:
        progress(1, "Cloud transcript ready for review")
    provider = str(selected.get("provider") or "groq")
    transcript_model = str(selected.get("transcript_model") or TRANSCRIPT_MODEL)
    return {"language": detected or "unknown", "duration": duration, "model": provider + "/" + transcript_model,
            "device": "cloud", "compute_type": "provider", "segments": segments, "words": all_words,
            "text": " ".join(row["text"] for row in segments),
            "coverage": _coverage_from_chunks(duration, chunks, count, "cloud_audio_chunks")}
