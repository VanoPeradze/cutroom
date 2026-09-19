"""Opt-in cloud AI. No SDK, shared key, automatic retry or provider fallback.

Connection preferences are installation-local; credentials live in memory only
(or in a user-managed environment variable). A job receives an immutable copy.
"""
from __future__ import annotations

import copy
import http.client
import json
import math
import os
import re
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from .utils import atomic_write_json, normalize_text

DEFAULT_MODEL = "openai/gpt-oss-120b"
TRANSCRIPT_MODEL = "whisper-large-v3"


class CloudAIError(RuntimeError):
    """Safe to display: never includes credentials, request data or remote body."""


class ConnectionStore:
    def __init__(self, settings):
        self.path = settings.data_dir / "ai-connection.json"
        self.lock = threading.RLock()
        self.key = ""
        self.preferences = {"mode": "local", "provider": "groq", "model": DEFAULT_MODEL}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            self.preferences = self._validate(saved)
        except (OSError, ValueError, TypeError):
            pass

    @staticmethod
    def _validate(payload):
        if not isinstance(payload, dict):
            raise ValueError("Choose an AI connection.")
        mode = payload.get("mode", "local")
        model = payload.get("model", DEFAULT_MODEL)
        if not isinstance(mode, str) or mode not in {"local", "free", "own"} or payload.get("provider", "groq") != "groq":
            raise ValueError("Choose Local AI or a supported Groq connection.")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
            raise ValueError("Enter a valid Groq model ID.")
        return {"mode": mode, "provider": "groq", "model": model}

    def snapshot(self):
        with self.lock:
            return {**self.preferences, "api_key": self.key or os.environ.get("CUTROOM_GROQ_API_KEY", "")}

    def public(self):
        snapshot = self.snapshot()
        has_key = bool(snapshot.pop("api_key"))
        return {**snapshot, "has_key": has_key, "configured": snapshot["mode"] == "local" or has_key,
                "key_storage": "session", "transcript_model": TRANSCRIPT_MODEL}

    def update(self, payload):
        if set(payload) - {"mode", "provider", "model", "api_key", "consent", "clear_key"}:
            raise ValueError("Unknown connection setting.")
        preferences = self._validate(payload)
        key = payload.get("api_key", "")
        if not isinstance(key, str) or len(key) > 512 or (key and not re.fullmatch(r"[!-~]+", key)):
            raise ValueError("Enter a valid API key without whitespace.")
        if preferences["mode"] != "local" and payload.get("consent") is not True:
            raise ValueError("Confirm cloud processing and your provider's billing plan first.")
        if "clear_key" in payload and not isinstance(payload["clear_key"], bool):
            raise ValueError("Invalid clear-key setting.")
        with self.lock:
            # Write only non-secret preferences, before committing in-memory state.
            atomic_write_json(self.path, preferences)
            self.preferences = preferences
            if payload.get("clear_key"):
                self.key = ""
            elif key:
                self.key = key
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
    if not selected.get("api_key"):
        raise CloudAIError("Cloud AI needs your Groq API key. Open AI connection and connect your account.")
    return selected


def _request(path, key, body, content_type="application/json", cancel_check=None, timeout=180):
    """Fixed HTTPS destination; redirects and remote error bodies are never followed."""
    if cancel_check:
        cancel_check()
    client = http.client.HTTPSConnection("api.groq.com", timeout=timeout)
    done = threading.Event()
    result = {}

    def send():
        try:
            client.request("POST", "/openai/v1/" + path, body=body, headers={
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
    response = _request("chat/completions", selected["api_key"], json.dumps(body).encode(), cancel_check=cancel_check, timeout=timeout)
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


def _multipart(audio, language):
    boundary = "cutroom-" + uuid.uuid4().hex
    fields = [("model", TRANSCRIPT_MODEL), ("response_format", "verbose_json"),
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
            body, mime = _multipart(audio.read_bytes(), language)
            if progress:
                progress(index / count, f"Cloud transcription · part {index + 1} of {count}")
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
    return {"language": detected or "unknown", "duration": duration, "model": "groq/" + TRANSCRIPT_MODEL,
            "device": "cloud", "compute_type": "provider", "segments": segments, "words": all_words,
            "text": " ".join(row["text"] for row in segments),
            "coverage": _coverage_from_chunks(duration, chunks, count, "cloud_audio_chunks")}
