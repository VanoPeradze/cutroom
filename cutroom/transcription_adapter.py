"""Optional Cloudflare speech adapter. No retries, redirects or saved secrets.

Transport is fixed to Workers AI. Only the reviewed speech model is accepted.
Consent is installation-wide and bound to account, model and disclosure version.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import http.client
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import unicodedata
import wave

from .cloud_ai import CloudAIError, _AbortableHTTPSConnection
from .utils import atomic_write_json, normalize_text

MODEL = "@cf/openai/whisper-large-v3-turbo"
DISCLOSURE_VERSION = "cloudflare-speech-2026-11-11-v1"
PRIVACY_URL = "https://developers.cloudflare.com/workers-ai/platform/data-usage/"
PRICING_URL = "https://developers.cloudflare.com/workers-ai/platform/pricing/"
MODEL_URL = "https://developers.cloudflare.com/workers-ai/models/whisper-large-v3-turbo/"
DISCLOSURE = (
    "Cloudflare receives audio for transcription on all future jobs using this selection. "
    "Cloudflare says it does not train models on Customer Content and normally does not retain "
    "content after processing, with documented safety, security, legal and feature exceptions. "
    "Operational metadata may be retained. Your Cloudflare plan may charge beyond its free allowance. "
    "Local fallback cannot undo an upload or charges. No automatic cloud retry is made. "
    "Only use recordings you are authorized to share. Review provider terms, model license and pricing."
)
MAX_BODY = 12 * 1024 * 1024
MAX_RESPONSE = 8 * 1024 * 1024
CHUNK_SECONDS = 120


class CloudTranscriptionError(CloudAIError):
    def __init__(self, message, *, fallback_allowed=False, uploaded_parts=0):
        super().__init__(message)
        self.fallback_allowed = fallback_allowed
        # Counts attempts: a failed request may already have reached the provider.
        self.uploaded_parts = uploaded_parts

    def __str__(self):
        message = super().__str__()
        if self.uploaded_parts and "Cloud upload attempts:" not in message:
            return (f"{message} Cloud upload attempts: {self.uploaded_parts}; "
                    "uploaded audio and possible charges cannot be undone.")
        return message


def engine(settings):
    value = settings.ai.get("transcription_engine", "legacy")
    if not isinstance(value, str) or value not in {"legacy", "local", "cloud", "auto"}:
        raise CloudTranscriptionError("Choose a supported transcription engine.")
    return value


def _environment(settings):
    config = settings.ai.get("cloudflare_transcription") or {}
    if not isinstance(config, dict):
        raise ValueError("Cloudflare transcription configuration must be an object.")
    model = config.get("model", MODEL)
    if model != MODEL:
        raise ValueError("Only the reviewed Cloudflare Whisper speech model is supported.")
    account = os.environ.get("CUTROOM_CF_ACCOUNT_ID", "")
    token = os.environ.get("CUTROOM_CF_API_TOKEN", "")
    if not re.fullmatch(r"[a-fA-F0-9]{32}", account):
        account = ""
    if not re.fullmatch(r"[!-~]{1,512}", token):
        token = ""
    return {"account_id": account.lower(), "api_key": token, "model": model}


def _scope(selected):
    return hashlib.sha256(json.dumps({
        "account": selected["account_id"], "model": selected["model"],
        "host": "api.cloudflare.com", "disclosure": DISCLOSURE_VERSION,
    }, sort_keys=True).encode()).hexdigest()


class EngineStore:
    def __init__(self, settings):
        self.settings = settings
        self.path = settings.data_dir / "transcription-engine.json"
        self.lock = threading.RLock()
        initial = engine(settings)
        if initial == "legacy":
            # Migrate only an existing cloud opt-in; fresh installations are local.
            initial = "local"
            try:
                old = json.loads((settings.data_dir / "ai-connection.json").read_text(encoding="utf-8"))
                if isinstance(old, dict) and old.get("mode") in {"free", "own"}:
                    initial = "legacy"
            except (OSError, ValueError, TypeError):
                pass
        self.saved = {"engine": initial}
        try:
            saved = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(saved, dict) and isinstance(saved.get("engine"), str) and saved["engine"] in {"legacy", "local", "cloud", "auto"}:
                self.saved = {"engine": saved["engine"], "consent_scope": saved.get("consent_scope")}
            else:
                self.saved = {"engine": "local"}
        except FileNotFoundError:
            # Persist migration once. Otherwise enabling Story AI later then
            # restarting could silently change fresh-install Local to legacy.
            atomic_write_json(self.path, self.saved)
        except (OSError, ValueError, TypeError):
            # A damaged preference must not revive old audio-upload consent.
            self.saved = {"engine": "local"}

    def public(self):
        with self.lock:
            selected = _environment(self.settings)
            scope = _scope(selected)
            ready = bool(selected["account_id"] and selected["api_key"])
            return {
                "engine": self.saved["engine"], "provider": "cloudflare", "model": MODEL,
                "account_id": selected["account_id"], "cloud_ready": ready,
                "message": "Cloudflare credentials available." if ready else "Set CUTROOM_CF_ACCOUNT_ID and CUTROOM_CF_API_TOKEN in the environment, then restart CUTROOM.",
                "consented": ready and self.saved.get("consent_scope") == scope,
                "consent_scope": scope, "disclosure_version": DISCLOSURE_VERSION,
                "disclosure": DISCLOSURE, "privacy_url": PRIVACY_URL,
                "pricing_url": PRICING_URL, "model_url": MODEL_URL,
                "key_storage": "environment", "scope": "installation_future_jobs",
            }

    def update(self, payload):
        if not isinstance(payload, dict) or set(payload) - {"engine", "consent", "consent_scope"}:
            raise ValueError("Unknown transcription setting.")
        mode = payload.get("engine")
        if not isinstance(mode, str) or mode not in {"legacy", "local", "cloud", "auto"}:
            raise ValueError("Choose Local, existing AI connection, Cloudflare, or Cloudflare with local fallback.")
        with self.lock:
            info = self.public()
            saved = {"engine": mode}
            if mode in {"cloud", "auto"}:
                if not info["cloud_ready"]:
                    raise ValueError("Set CUTROOM_CF_ACCOUNT_ID and CUTROOM_CF_API_TOKEN in the environment first.")
                if payload.get("consent") is not True or payload.get("consent_scope") != info["consent_scope"]:
                    raise ValueError("Confirm this Cloudflare account, model, future audio uploads and pricing first.")
                saved["consent_scope"] = info["consent_scope"]
            atomic_write_json(self.path, saved)
            self.saved = saved
            return self.public()

    def snapshot(self):
        with self.lock:
            selected = _environment(self.settings)
            selected["consent_scope"] = self.saved.get("consent_scope")
            selected["disclosure_version"] = DISCLOSURE_VERSION
            return {"transcription_engine": self.saved["engine"], "cloudflare_connection": selected}


def cache_identity(settings):
    selected = settings.ai.get("cloudflare_connection") or {}
    mode = engine(settings)
    result = {"engine": mode, "adapter_version": 1}
    if mode in {"cloud", "auto"}:
        result.update(provider="cloudflare", model=selected.get("model", MODEL),
                      account_identity=hashlib.sha256(str(selected.get("account_id", "")).encode()).hexdigest(),
                      consent_scope=selected.get("consent_scope"), disclosure=DISCLOSURE_VERSION)
    return result


def _connection(settings):
    selected = copy.deepcopy(settings.ai.get("cloudflare_connection") or {})
    if engine(settings) not in {"cloud", "auto"}:
        raise CloudTranscriptionError("Cloudflare transcription was not selected.")
    if (selected.get("model") != MODEL or not re.fullmatch(r"[a-f0-9]{32}", str(selected.get("account_id", "")))
            or not re.fullmatch(r"[!-~]{1,512}", str(selected.get("api_key", "")))):
        raise CloudTranscriptionError("Cloudflare credentials are unavailable. Reconfigure transcription.")
    if selected.get("consent_scope") != _scope(selected) or selected.get("disclosure_version") != DISCLOSURE_VERSION:
        raise CloudTranscriptionError("Confirm the current Cloudflare account, model and privacy disclosure before uploading.")
    return selected


def require_transcription_connection(settings):
    """Validate frozen Cloudflare approval before admitting work; no network I/O."""
    if engine(settings) in {"cloud", "auto"}:
        return _connection(settings)
    return None


def _post(selected, body, check, timeout=120):
    """Exactly one fixed-host request; cancellation aborts the connection."""
    check()
    if len(body) > MAX_BODY:
        raise CloudTranscriptionError("Prepared audio exceeded the encoded upload limit.")
    client = _AbortableHTTPSConnection("api.cloudflare.com", timeout=timeout)
    done, result = threading.Event(), {}

    def send():
        try:
            check()
            client.request("POST", f'/client/v4/accounts/{selected["account_id"]}/ai/run/{MODEL}',
                           body=body, headers={"Authorization": "Bearer " + selected["api_key"],
                                               "Content-Type": "application/json"})
            response = client.getresponse()
            if response.status != 200:
                retryable = response.status == 429 or 500 <= response.status < 600
                raise CloudTranscriptionError(
                    f"Cloudflare transcription failed (HTTP {response.status}). Check account permissions, rate limits and plan. No retry was made.",
                    fallback_allowed=retryable)
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise CloudTranscriptionError("Cloudflare returned an oversized response.", fallback_allowed=True)
            value = json.loads(data)
            if not isinstance(value, dict) or value.get("success") is not True or not isinstance(value.get("result"), dict):
                raise CloudTranscriptionError("Cloudflare did not return a successful transcription.", fallback_allowed=True)
            result["value"] = value["result"]
        except CloudTranscriptionError as error:
            result["error"] = error
        except (OSError, ValueError, TypeError, http.client.HTTPException):
            result["error"] = CloudTranscriptionError("Cloudflare connection failed or returned invalid data. No retry was made.", fallback_allowed=True)
        except BaseException as error:
            # Includes JobCancelled; never convert it to fallback.
            result["error"] = error
        finally:
            done.set()

    threading.Thread(target=send, name="cutroom-cloudflare-request", daemon=True).start()
    deadline = time.monotonic() + timeout
    try:
        while not done.wait(.1):
            check()
            if time.monotonic() >= deadline:
                raise CloudTranscriptionError("Cloudflare timed out. Upload/charges may have occurred; no retry was made.", fallback_allowed=True)
        check()
        if "error" in result:
            raise result["error"]
        return result["value"]
    finally:
        client.abort()


def _words(response, start, end, core_start, core_end):
    """Require genuine word timestamps. Empty text + explicit empty segments is silence."""
    def invalid():
        return CloudTranscriptionError("Cloudflare returned incomplete or invalid word timings. Existing transcripts are unchanged.", fallback_allowed=True)
    if not isinstance(response, dict) or not isinstance(response.get("text"), str):
        raise invalid()
    segments = response.get("segments")
    if not isinstance(segments, list):
        raise invalid()
    info = response.get("transcription_info")
    if isinstance(info, dict) and "duration" in info:
        try:
            reported = float(info["duration"])
            if not math.isfinite(reported) or abs(reported - (end-start)) > .5:
                raise ValueError()
        except (TypeError, ValueError, OverflowError):
            raise invalid() from None
    def content(text):
        return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                       if unicodedata.category(c)[0] in {"L", "N", "M"})
    result, previous, word_count, all_text = [], -1.0, 0, []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get("words"), list):
            raise invalid()
        if str(segment.get("text") or "").strip() and not segment["words"]:
            raise invalid()
        segment_text = []
        for raw in segment["words"]:
            try:
                if not isinstance(raw, dict) or not isinstance(raw.get("word"), str):
                    raise ValueError()
                if isinstance(raw.get("start"), bool) or isinstance(raw.get("end"), bool):
                    raise ValueError()
                left, right = float(raw["start"]), float(raw["end"])
                word = raw["word"].strip()
                if (not all(math.isfinite(t) for t in (left, right)) or left < 0 or right <= left
                        or right > end - start + .1 or left < previous or not word):
                    raise ValueError()
                previous = left
                word_count += 1
                segment_text.append(word)
                all_text.append(word)
                if core_start <= start + (left + right) / 2 < core_end:
                    result.append({"start": round(start + left, 3), "end": round(min(end, start + right), 3), "word": word})
            except (ValueError, TypeError, KeyError, OverflowError):
                raise invalid() from None
        if isinstance(segment.get("text"), str) and content(segment["text"]) != content(" ".join(segment_text)):
            raise invalid()
    if response["text"].strip() and not word_count:
        raise invalid()
    if content(response["text"]) != content(" ".join(all_text)):
        raise invalid()
    return result


def transcribe_cloud_whisper(media_path: Path, settings, language=None, progress=None, duration=0.0, cancel_check=None):
    from .media import probe_media, run_command
    from .transcription import _coverage_from_chunks, _language_code

    selected = _connection(settings)
    check = cancel_check or (lambda: None)
    check()
    requested = _language_code(language) if language and language != "auto" else None
    if language and language != "auto" and (not requested or not re.fullmatch(r"[a-z]{2,3}", requested) or requested == "unknown"):
        raise CloudTranscriptionError("Choose a supported transcription language or Auto.")
    duration = float(duration or probe_media(media_path, settings).get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise CloudTranscriptionError("Could not determine recording duration.")
    words, chunks, attempted = [], [], 0
    detected = requested
    count = math.ceil(duration / CHUNK_SECONDS)
    with tempfile.TemporaryDirectory(prefix="cutroom-cloudflare-", dir=settings.cache_dir) as temp:
        for index in range(count):
            check()
            core_start, core_end = index * CHUNK_SECONDS, min(duration, (index + 1) * CHUNK_SECONDS)
            start, end = max(0, core_start - 1), min(duration, core_end + 1)
            audio = Path(temp) / "audio.wav"
            run_command([settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start),
                         "-i", str(media_path), "-t", str(end-start), "-map", "0:a:0", "-vn", "-ac", "1",
                         "-ar", "16000", "-c:a", "pcm_s16le", str(audio)], timeout=180, cancel_check=check)
            check()
            try:
                with wave.open(str(audio), "rb") as wav:
                    actual = wav.getnframes() / wav.getframerate()
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                        raise ValueError()
                    if not math.isfinite(actual) or abs(actual - (end - start)) > .25:
                        raise ValueError()
                    if wav.getnframes() > int((CHUNK_SECONDS + 3) * 16000):
                        raise ValueError()
                    if len(wav.readframes(wav.getnframes())) != wav.getnframes() * 2:
                        raise ValueError()
                if audio.stat().st_size > (MAX_BODY - 4096) * 3 // 4:
                    raise ValueError()
            except (OSError, EOFError, wave.Error, ValueError):
                raise CloudTranscriptionError("Audio preparation was incomplete or exceeded the upload limit; nothing from this part was sent.", uploaded_parts=attempted) from None
            payload = {"audio": base64.b64encode(audio.read_bytes()).decode("ascii")}
            if requested:
                payload["language"] = requested
            body = json.dumps(payload).encode()
            if len(body) > MAX_BODY:
                raise CloudTranscriptionError("Prepared audio exceeded the encoded upload limit.", uploaded_parts=attempted)
            if progress:
                progress(index / count, f"Cloudflare transcription: part {index+1} of {count}")
            check()
            attempted += 1
            try:
                response = _post(selected, body, check)
                check()
                words.extend(_words(response, start, end, core_start, core_end))
            except CloudTranscriptionError as error:
                error.uploaded_parts = attempted
                raise
            if not detected or detected == "unknown":
                # Workers AI's documented schema nests language under
                # transcription_info; accept flat language for older fixtures.
                info = response.get("transcription_info")
                info = info if isinstance(info, dict) else {}
                code = str(info.get("language") or response.get("language") or "unknown").lower()
                detected = _language_code({"hebrew": "he", "english": "en"}.get(code, code))
            chunks.append({"start": core_start, "end": core_end, "analyzed_end": core_end, "status": "complete"})
    segments = []
    for index in range(0, len(words), 18):
        group = words[index:index+18]
        text = " ".join(w["word"] for w in group)
        segments.append({"id": f"s{len(segments)+1:04d}", "start": group[0]["start"], "end": max(w["end"] for w in group),
                         "text": text, "normalized": normalize_text(text), "words": group})
    check()
    if progress:
        progress(1, "Cloudflare transcript ready for review")
    return {"language": detected or "unknown", "duration": duration, "model": "cloudflare/" + MODEL,
            "device": "cloud", "compute_type": "provider", "segments": segments, "words": words,
            "text": " ".join(row["text"] for row in segments),
            "coverage": _coverage_from_chunks(duration, chunks, count, "cloudflare_audio_chunks"),
            "execution": {"transcription_engine": engine(settings), "provider": "cloudflare", "uploaded_parts": attempted,
                          "provenance": cache_identity(settings)}}
