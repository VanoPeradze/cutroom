from __future__ import annotations

import copy
import json
import os
import math
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .config import Settings
from .jobs import JobCancelled
from .utils import atomic_write_json, normalize_text

_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_MODEL_LOCK = threading.Lock()


class TranscriptionIncomplete(RuntimeError):
    """A failed decode retains its accounting, never a successful partial story."""

    def __init__(self, message: str, coverage: dict[str, Any]):
        super().__init__(message)
        self.coverage = copy.deepcopy(coverage)


def _finite_number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _merged_time_ranges(rows: Any, duration: float) -> list[dict[str, float]]:
    intervals = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        start = max(0.0, _finite_number(row.get("start")))
        end = max(start, _finite_number(row.get("end")))
        if duration > 0.0:
            start, end = min(duration, start), min(duration, end)
        if end > start:
            intervals.append((start, end))
    merged: list[dict[str, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1]["end"] + 0.001:
            merged[-1]["end"] = max(end, merged[-1]["end"])
        else:
            merged.append({"start": start, "end": end})
    return merged


def _coverage_from_chunks(source_duration: float, chunks: list[dict[str, Any]], expected: int, source: str) -> dict[str, Any]:
    analyzed_ranges = _merged_time_ranges([
        {"start": row["start"], "end": row.get("analyzed_end", row["start"])}
        for row in chunks
    ], source_duration)
    completed = sum(row.get("status") == "complete" for row in chunks)
    failed = sum(row.get("status") == "failed" for row in chunks)
    return {
        "version": 1,
        "source": source,
        "source_duration": round(source_duration, 3),
        "complete": completed == expected and failed == 0,
        "expected_chunks": expected,
        "completed_chunks": completed,
        "failed_chunks": failed,
        "incomplete_chunks": sum(row.get("status") == "incomplete" for row in chunks),
        "pending_chunks": max(0, expected - len(chunks)),
        "analyzed_ranges": analyzed_ranges,
        "chunks": copy.deepcopy(chunks),
    }

_LANGUAGE_ALIASES = {
    "iw": "he",
    "heb": "he",
    "eng": "en",
    "ara": "ar",
    "fra": "fr",
    "fre": "fr",
    "spa": "es",
    "rus": "ru",
}
_HEBREW_FUNCTION_WORDS = {
    "אבל", "אז", "איך", "אם", "אני", "אנחנו", "את", "אתה", "אתם", "גם",
    "הוא", "היא", "היה", "זה", "זאת", "יש", "כי", "כן", "לא", "מה", "מי",
    "עכשיו", "על", "עם", "פה", "רוצה", "של", "שם", "צריך",
}


def _clamp_probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return max(0.0, min(1.0, number))


def _language_code(value: Any) -> str:
    code = str(value or "unknown").strip().lower().replace("_", "-")
    code = code.split("-", 1)[0]
    return _LANGUAGE_ALIASES.get(code, code or "unknown")


def _script_profile(text: str) -> dict[str, Any]:
    """Return conservative script evidence without pretending script is language.

    Hebrew is the useful special case here: Whisper can occasionally label clear
    Hebrew text as a Latin-script language when the opening window is quiet. The
    script signal is only allowed to correct that contradiction after enough real
    letters are present. Yiddish is deliberately protected because it shares the
    same alphabet and cannot be distinguished from Hebrew by script alone.
    """

    letters = [character for character in str(text or "") if character.isalpha()]
    hebrew_letters = [character for character in letters if "\u0590" <= character <= "\u05ff"]
    total = len(letters)
    hebrew = len(hebrew_letters)
    ratio = hebrew / total if total else 0.0
    tokens = {
        token.strip(".,!?;:'\"()[]{}<>־–—…").lower()
        for token in str(text or "").split()
    }
    markers = len(tokens.intersection(_HEBREW_FUNCTION_WORDS))
    confidence = 0.0
    if hebrew >= 8 and ratio >= 0.64:
        count_strength = min(1.0, max(0.0, (hebrew - 8) / 40.0))
        marker_strength = min(1.0, markers / 3.0)
        confidence = min(0.94, 0.66 + 0.20 * ratio + 0.07 * count_strength + 0.03 * marker_strength)
    return {
        "letters": total,
        "hebrew_letters": hebrew,
        "hebrew_ratio": round(ratio, 4),
        "hebrew_markers": markers,
        "hebrew_confidence": round(confidence, 4),
    }


def _language_observation(decoded: dict[str, Any]) -> dict[str, Any] | None:
    text = str(decoded.get("text") or "").strip()
    profile = _script_profile(text)
    letters = int(profile["letters"])
    if not text or letters <= 0:
        return None

    raw_language = _language_code(decoded.get("language"))
    raw_probability = _clamp_probability(decoded.get("language_probability"))
    language = raw_language
    probability = raw_probability
    method = "whisper"
    hebrew_confidence = float(profile["hebrew_confidence"])
    hebrew_ratio = float(profile["hebrew_ratio"])
    hebrew_letters = int(profile["hebrew_letters"])
    shared_hebrew_script = hebrew_letters >= 2 and hebrew_ratio >= 0.78
    if raw_language == "yi":
        # Hebrew and Yiddish share an alphabet, and common tokens such as "איך"
        # and "אז" occur in both languages. Script/word-list evidence must never
        # relabel a real Yiddish result as Hebrew. A weak Yiddish guess remains
        # Yiddish but is explicitly low-confidence so the user can decide.
        if shared_hebrew_script and raw_probability < 0.80:
            probability = min(raw_probability, 0.61)
            method = "shared_script_ambiguous"
    elif hebrew_confidence > 0.0:
        if raw_language == "he":
            # The transcript alphabet independently supports Whisper's label.
            probability = max(raw_probability, hebrew_confidence)
            method = "whisper+script"
        elif raw_language in {"", "auto", "unknown"} or hebrew_ratio >= 0.78:
            # A transcript made almost entirely of Hebrew letters cannot be an
            # English/French/etc. result, even if the short opening-window label
            # was confident. Use the script confidence, never that contradictory
            # raw confidence, so the correction stays honest.
            language = "he"
            probability = hebrew_confidence
            method = "script"
    elif shared_hebrew_script and raw_language not in {"he", "", "auto", "unknown"}:
        # A very short Hebrew-script phrase is strong contradictory evidence but
        # not enough text to choose Hebrew over Yiddish safely. Do not leave an
        # impossible English/French/etc. label at high confidence; keep the raw
        # label only as a low-confidence prompt for explicit user selection.
        probability = min(raw_probability, 0.61)
        method = "script_conflict"

    if language in {"", "auto", "unknown"}:
        return None
    segments = [item for item in decoded.get("segments", []) if isinstance(item, dict)]
    speech_seconds = sum(
        max(0.0, float(item.get("end", 0.0) or 0.0) - float(item.get("start", 0.0) or 0.0))
        for item in segments
    )
    # Square-root scaling stops one verbose/hallucinated chunk from overwhelming
    # several shorter windows while still giving a real sentence more weight than
    # a one-word fragment.
    evidence_weight = math.sqrt(max(1.0, min(180.0, float(letters))))
    evidence_weight *= 0.70 + 0.30 * min(1.0, speech_seconds / 8.0)
    if letters < 4:
        evidence_weight *= 0.25
    return {
        "language": language,
        "probability": probability,
        "weight": max(0.05, evidence_weight),
        "raw_language": raw_language,
        "raw_probability": raw_probability,
        "method": method,
    }


def _resolve_language_evidence(
    result: dict[str, Any],
    requested_language: str | None,
    decoded_units: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve language from multiple bounded windows and retain honest metadata."""

    units = decoded_units if decoded_units is not None else [result]
    observations = [
        observation
        for unit in units
        if isinstance(unit, dict)
        for observation in [_language_observation(unit)]
        if observation is not None
    ]
    scores: dict[str, float] = defaultdict(float)
    confidence_sum: dict[str, float] = defaultdict(float)
    confidence_weight: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    for observation in observations:
        language = str(observation["language"])
        probability = float(observation["probability"])
        weight = float(observation["weight"])
        scores[language] += weight * (0.20 + 0.80 * probability)
        confidence_sum[language] += probability * weight
        confidence_weight[language] += weight
        counts[language] += 1

    ranked = sorted(scores, key=lambda item: (-scores[item], item))
    detected_language = ranked[0] if ranked else _language_code(result.get("language"))
    if detected_language in {"", "auto"}:
        detected_language = "unknown"
    top_score = scores.get(detected_language, 0.0)
    total_score = sum(scores.values())
    runner_up = ranked[1] if len(ranked) > 1 else None
    runner_score = scores.get(runner_up, 0.0) if runner_up else 0.0
    vote_share = top_score / total_score if total_score > 0.0 else 0.0
    margin = (top_score - runner_score) / total_score if total_score > 0.0 else 0.0
    mean_probability = (
        confidence_sum[detected_language] / confidence_weight[detected_language]
        if confidence_weight.get(detected_language, 0.0) > 0.0
        else 0.0
    )
    if len(ranked) <= 1:
        detected_probability = mean_probability
    else:
        # High per-window confidence is not enough when independent windows
        # disagree. Lowering the aggregate confidence lets the existing quality
        # gate request a stronger pass instead of locking the wrong language.
        detected_probability = mean_probability * (0.55 + 0.45 * vote_share) * (0.80 + 0.20 * margin)
    detected_probability = _clamp_probability(detected_probability)

    explicit_language = _language_code(requested_language) if requested_language else "auto"
    is_explicit = explicit_language not in {"", "auto", "unknown"}
    ambiguous = bool(
        not is_explicit
        and (
            not observations
            or detected_language == "unknown"
            or detected_probability < 0.62
            or (len(ranked) > 1 and vote_share < 0.58)
        )
    )
    if ambiguous:
        # `language_probability` is the stable UI/backend confidence contract.
        # Never expose an ambiguous consensus above the quality gate merely
        # because individual windows were overconfident.
        detected_probability = min(detected_probability, 0.6199)
    final_language = explicit_language if is_explicit else detected_language
    final_probability = 1.0 if is_explicit else detected_probability
    script_assisted = sum(
        1
        for item in observations
        if item["method"] in {"script", "whisper+script", "shared_script_ambiguous", "script_conflict"}
    )
    source = "explicit" if is_explicit else (
        "none" if not observations else (
            "script_assisted" if script_assisted else ("consensus" if len(observations) > 1 else "whisper")
        )
    )
    vote_summary = {
        language: round(scores[language] / total_score, 4)
        for language in ranked[:5]
        if total_score > 0.0
    }
    raw_ranked: dict[str, float] = defaultdict(float)
    for observation in observations:
        raw_ranked[str(observation["raw_language"])] += float(observation["weight"])
    raw_language = max(raw_ranked, key=raw_ranked.get) if raw_ranked else _language_code(result.get("language"))

    resolved = dict(result)
    resolved.update({
        "language": final_language,
        "language_probability": round(final_probability, 4),
        "detected_language": detected_language,
        "detected_language_probability": round(detected_probability, 4),
        "language_detection": {
            "source": source,
            "requested_language": explicit_language if is_explicit else "auto",
            "raw_language": raw_language,
            "observations": len(observations),
            "agreeing_observations": counts.get(detected_language, 0),
            "vote_share": round(vote_share, 4),
            "runner_up": runner_up,
            "votes": vote_summary,
            "script_assisted_observations": script_assisted,
            "ambiguous": ambiguous,
        },
    })
    return resolved


def _split_oversized_segments(segments: list[dict[str, Any]], max_seconds: float = 30.0) -> list[dict[str, Any]]:
    """Split long Whisper segments when real word timestamps make that safe."""
    output: list[dict[str, Any]] = []
    for segment in segments:
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        words = [
            item for item in (segment.get("words") or [])
            if isinstance(item, dict) and float(item.get("end", 0.0)) > float(item.get("start", 0.0))
        ]
        if end - start <= max_seconds or len(words) < 2:
            output.append(dict(segment))
            continue
        chunk: list[dict[str, Any]] = []
        chunk_start = float(words[0]["start"])
        for word in words:
            word_end = float(word["end"])
            if chunk and word_end - chunk_start > max_seconds:
                text = " ".join(str(item.get("word") or "").strip() for item in chunk).strip()
                output.append({
                    **segment,
                    "start": round(float(chunk[0]["start"]), 3),
                    "end": round(float(chunk[-1]["end"]), 3),
                    "text": text,
                    "normalized": normalize_text(text),
                    "words": chunk,
                })
                chunk = []
                chunk_start = float(word["start"])
            chunk.append(word)
        if chunk:
            text = " ".join(str(item.get("word") or "").strip() for item in chunk).strip()
            output.append({
                **segment,
                "start": round(float(chunk[0]["start"]), 3),
                "end": round(float(chunk[-1]["end"]), 3),
                "text": text,
                "normalized": normalize_text(text),
                "words": chunk,
            })
    for index, segment in enumerate(output, start=1):
        segment["id"] = f"s{index:04d}"
    return output


def _cuda_has_capacity(settings: Settings, mode: str | None = None) -> bool:
    """Avoid taking CUDA when another application has consumed its safe headroom.

    CTranslate2 only reports whether a CUDA device exists. On a creator machine a
    game, renderer or 3D tool may already own most VRAM; starting Whisper there can
    block inside native code instead of returning a useful out-of-memory error.
    When nvidia-smi is unavailable we keep the prior hardware-only behaviour.
    """

    thresholds = settings.ai.get("whisper_cuda_min_free_mb", {})
    defaults = {"lite": 2048.0, "balanced": 4096.0, "quality": 6144.0}
    if isinstance(thresholds, dict):
        try:
            minimum_free_mb = float(thresholds.get(str(mode or "balanced"), defaults.get(str(mode), 4096.0)))
        except (TypeError, ValueError):
            minimum_free_mb = defaults.get(str(mode), 4096.0)
    else:
        try:
            minimum_free_mb = float(thresholds)
        except (TypeError, ValueError):
            minimum_free_mb = defaults.get(str(mode), 4096.0)
    if minimum_free_mb <= 0:
        return True
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        probe = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=2.0,
            check=False,
            creationflags=creationflags,
        )
        free_values = [
            float(line.strip().split()[0])
            for line in probe.stdout.splitlines()
            if line.strip() and line.strip().split()[0].replace(".", "", 1).isdigit()
        ]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return True
    return not free_values or max(free_values) >= minimum_free_mb


def _resolve_device(settings: Settings, mode: str | None = None) -> tuple[str, str]:
    configured_device = str(settings.ai.get("whisper_device", "auto"))
    configured_compute = str(settings.ai.get("whisper_compute_type", "auto"))
    if configured_device != "auto":
        compute = configured_compute if configured_compute != "auto" else ("float16" if configured_device == "cuda" else "int8")
        return configured_device, compute
    try:
        import ctranslate2

        cuda_count = int(ctranslate2.get_cuda_device_count())
    except Exception:
        cuda_count = 0
    if cuda_count > 0 and _cuda_has_capacity(settings, mode):
        return "cuda", "float16" if configured_compute == "auto" else configured_compute
    return "cpu", "int8" if configured_compute == "auto" else configured_compute


def cuda_available(settings: Settings | None = None) -> bool:
    if settings is not None:
        configured = str(settings.ai.get("whisper_device", "auto"))
        if configured == "cpu":
            return False
        if configured not in {"auto", "cuda"}:
            return False
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:
        return False


def _load_model(settings: Settings, device: str | None = None, compute: str | None = None, model_name: str | None = None) -> tuple[Any, str, str, str]:
    model_name = str(model_name or settings.ai.get("whisper_model", "base"))
    if device is None or compute is None:
        device, compute = _resolve_device(settings)
    key = (model_name, device, compute)
    with _MODEL_LOCK:
        if key not in _MODEL_CACHE:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:
                raise RuntimeError("faster-whisper is not installed. Run setup again or install requirements-ai.txt") from exc
            _MODEL_CACHE[key] = WhisperModel(model_name, device=device, compute_type=compute)
    return _MODEL_CACHE[key], model_name, device, compute


def _model_for_request(settings: Settings, mode: str, requested_language: str | None, device: str) -> str:
    model_map = settings.ai.get("whisper_models", {})
    default = str(model_map.get(mode) or settings.ai.get("whisper_model", "base"))
    hebrew_model = str(settings.ai.get("hebrew_whisper_model") or "").strip()
    if requested_language == "he" and hebrew_model:
        # Keep the heavyweight Hebrew-specific model for explicit Quality mode.
        # Balanced Small/CUDA with language locked to Hebrew is substantially
        # lighter and is the automatic recovery path for weak Base transcripts.
        if mode == "quality":
            return hebrew_model
    return default


def _stop_process(process: subprocess.Popen[Any]) -> None:
    """Stop a child process without leaving a decoder behind after cancellation."""

    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        pass
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except OSError:
            pass
        try:
            process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            pass


def _extract_audio_chunk(
    media_path: Path,
    target: Path,
    settings: Settings,
    start: float,
    duration: float,
    cancel_check: Callable[[], None] | None = None,
) -> Path:
    """Extract one bounded PCM unit and terminate FFmpeg promptly on cancellation."""

    if duration <= 0:
        raise ValueError("Audio chunk duration must be positive")
    if cancel_check:
        cancel_check()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    command = [
        settings.ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-ss", f"{max(0.0, float(start)):.3f}",
        "-i", str(media_path),
        "-t", f"{float(duration):.3f}",
        "-map", "0:a:0",
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(target),
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    stderr = ""
    try:
        while True:
            if cancel_check:
                cancel_check()
            try:
                _, stderr = process.communicate(timeout=0.20)
                break
            except subprocess.TimeoutExpired:
                continue
        if cancel_check:
            cancel_check()
        if process.returncode != 0:
            raise RuntimeError((stderr or "FFmpeg could not extract an audio chunk")[-2000:])
        # A WAV header without decoded samples is not useful input for Whisper.
        if not target.is_file() or target.stat().st_size <= 44:
            raise RuntimeError("FFmpeg produced an empty audio chunk")
        return target
    except BaseException:
        _stop_process(process)
        target.unlink(missing_ok=True)
        raise
    finally:
        _stop_process(process)


def _decode_with_model(
    model: Any,
    media_path: Path,
    model_name: str,
    device: str,
    compute: str,
    requested_language: str | None,
    mode: str,
    progress: Callable[[float, str], None] | None,
    cancel_check: Callable[[], None] | None,
) -> dict[str, Any]:
    """Decode one bounded media unit with cooperative checks between segments."""

    if cancel_check:
        cancel_check()
    segments_iter, info = model.transcribe(
        str(media_path),
        language=requested_language,
        beam_size=1 if mode == "lite" else (3 if mode == "balanced" else 5),
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 350, "speech_pad_ms": 180},
        word_timestamps=mode != "lite",
        # Long recordings are split before this call. Quality mode can still use
        # prior text within each bounded unit without making cancellation wait for
        # an unbounded VAD region.
        condition_on_previous_text=mode == "quality",
    )
    if cancel_check:
        cancel_check()
    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    iterator = iter(segments_iter)
    total_duration = max(0.001, float(getattr(info, "duration", 0.0) or 0.0))
    last_reported = 0.08
    index = 0
    try:
        while True:
            if cancel_check:
                cancel_check()
            try:
                segment = next(iterator)
            except StopIteration:
                break
            if cancel_check:
                cancel_check()
            segment_words: list[dict[str, Any]] = []
            for word in segment.words or []:
                item = {
                    "start": round(float(word.start), 3),
                    "end": round(float(word.end), 3),
                    "word": str(word.word).strip(),
                    "probability": round(float(getattr(word, "probability", 0.0) or 0.0), 4),
                }
                if item["word"] and item["end"] > item["start"]:
                    segment_words.append(item)
                    words.append(item)
            text = str(segment.text or "").strip()
            if not text:
                continue
            segments.append({
                "id": f"s{index + 1:04d}",
                "start": round(float(segment.start), 3),
                "end": round(float(segment.end), 3),
                "text": text,
                "normalized": normalize_text(text),
                "words": segment_words,
                "avg_logprob": round(float(getattr(segment, "avg_logprob", 0.0) or 0.0), 4),
                "no_speech_prob": round(float(getattr(segment, "no_speech_prob", 0.0) or 0.0), 4),
            })
            index += 1
            decoded = min(0.96, 0.08 + 0.88 * max(0.0, float(segment.end)) / total_duration)
            if progress and (decoded - last_reported >= 0.01 or decoded >= 0.959):
                progress(decoded, f"Transcribing with {model_name} · {min(100, round(float(segment.end) / total_duration * 100))}%")
                last_reported = decoded
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            close()
    # Exhausting the decoder verifies the audio it actually opened, including
    # quiet endings. Transcript timestamps cannot establish this coverage.
    decoded_duration = max(0.0, _finite_number(getattr(info, "duration", None)))
    unit_evidence: dict[str, Any] = {
        "start": 0.0,
        "end": round(decoded_duration, 3),
        "analyzed_end": round(decoded_duration, 3),
        "status": "complete" if decoded_duration > 0 else "incomplete",
        "transcript_seconds": round(sum(
            row["end"] - row["start"] for row in _merged_time_ranges(segments, decoded_duration)
        ), 3),
    }
    vad_duration = _finite_number(getattr(info, "duration_after_vad", None), -1.0)
    if 0.0 <= vad_duration <= decoded_duration + 0.5:
        # Faster-Whisper's Silero VAD runs before ASR. Preserve the measured
        # amount of speech, never turn amplitude or missing text into speech.
        unit_evidence["vad_speech_seconds"] = round(min(decoded_duration, vad_duration), 3)
        unit_evidence["vad_source"] = "faster_whisper_silero"
    return {
        "language": getattr(info, "language", requested_language or "unknown"),
        "language_probability": round(float(getattr(info, "language_probability", 0.0) or 0.0), 4),
        "duration": round(total_duration, 3),
        "model": model_name,
        "device": device,
        "compute_type": compute,
        "segments": segments,
        "words": words,
        "text": " ".join(segment["text"] for segment in segments),
        "coverage": _coverage_from_chunks(decoded_duration, [unit_evidence], 1, "decoder_exhaustion"),
    }


def _chunk_policy(settings: Settings, device: str, source_duration: float) -> tuple[bool, float]:
    """Return whether to bound decoding and the maximum audio seconds per unit."""

    try:
        configured_seconds = float(settings.ai.get("whisper_chunk_seconds", 30.0))
    except (TypeError, ValueError):
        configured_seconds = 30.0
    chunk_seconds = max(10.0, min(60.0, configured_seconds))
    if device == "cpu":
        chunk_seconds = min(chunk_seconds, 24.0)
    try:
        configured_threshold = float(settings.ai.get("whisper_chunk_threshold_seconds", 90.0))
    except (TypeError, ValueError):
        configured_threshold = 90.0
    threshold = max(chunk_seconds, configured_threshold)
    return bool(source_duration > threshold), chunk_seconds


def _transcribe_chunked(
    model: Any,
    media_path: Path,
    settings: Settings,
    model_name: str,
    device: str,
    compute: str,
    requested_language: str | None,
    mode: str,
    source_duration: float,
    chunk_seconds: float,
    progress: Callable[[float, str], None] | None,
    cancel_check: Callable[[], None] | None,
) -> dict[str, Any]:
    """Transcribe long media as short, disposable PCM units.

    Faster Whisper does not expose an interrupt for a currently decoding generator
    step. Bounding every step to a small audio file keeps that unavoidable wait
    short, while the shared model remains loaded exactly once.
    """

    segments: list[dict[str, Any]] = []
    words: list[dict[str, Any]] = []
    decoded_units: list[dict[str, Any]] = []
    processed_chunks: list[dict[str, Any]] = []
    total_chunks = max(1, int(math.ceil(source_duration / chunk_seconds)))
    temp_parent = settings.cache_dir if settings.cache_dir.is_dir() else None
    with tempfile.TemporaryDirectory(prefix="cutroom-whisper-", dir=str(temp_parent) if temp_parent else None) as temp_name:
        temp_dir = Path(temp_name)
        chunk_index = 0
        chunk_start = 0.0
        while chunk_start < source_duration - 0.001:
            if cancel_check:
                cancel_check()
            unit_duration = min(chunk_seconds, source_duration - chunk_start)
            target = temp_dir / f"chunk-{chunk_index:05d}.wav"
            if progress:
                start_progress = 0.08 + 0.88 * (chunk_start / source_duration)
                progress(start_progress, f"Preparing transcription unit {chunk_index + 1}/{total_chunks}")
            def unit_progress(value: float, message: str) -> None:
                if not progress:
                    return
                local = max(0.0, min(1.0, float(value)))
                absolute = chunk_start + unit_duration * local
                mapped = min(0.96, 0.08 + 0.88 * absolute / source_duration)
                progress(mapped, f"{message} · unit {chunk_index + 1}/{total_chunks}")

            try:
                _extract_audio_chunk(media_path, target, settings, chunk_start, unit_duration, cancel_check)
                decoded = _decode_with_model(
                    model,
                    target,
                    model_name,
                    device,
                    compute,
                    requested_language,
                    mode,
                    unit_progress,
                    cancel_check,
                )
            except JobCancelled:
                raise
            except Exception as exc:
                processed_chunks.append({
                    "start": round(chunk_start, 3),
                    "end": round(chunk_start + unit_duration, 3),
                    "analyzed_end": round(chunk_start, 3),
                    "status": "failed",
                    "error": str(exc),
                })
                coverage = _coverage_from_chunks(source_duration, processed_chunks, total_chunks, "chunked_decoder_exhaustion")
                raise TranscriptionIncomplete(
                    f"Transcription unit {chunk_index + 1}/{total_chunks} failed: {exc}", coverage,
                ) from exc
            finally:
                # Do not retain tens of megabytes of extracted PCM while a long
                # recording continues through later units.
                target.unlink(missing_ok=True)
            if cancel_check:
                cancel_check()
            decoded_duration = max(0.0, _finite_number(decoded.get("duration")))
            analyzed_end = chunk_start + min(unit_duration, decoded_duration)
            chunk_evidence: dict[str, Any] = {
                "start": round(chunk_start, 3),
                "end": round(chunk_start + unit_duration, 3),
                "analyzed_end": round(analyzed_end, 3),
                "status": "complete" if (
                    decoded_duration >= unit_duration - 0.5
                    and (decoded.get("coverage") or {}).get("complete") is not False
                ) else "incomplete",
            }
            decoded_chunks = (decoded.get("coverage") or {}).get("chunks", [])
            if decoded_chunks and decoded_chunks[0].get("vad_speech_seconds") is not None:
                chunk_evidence["vad_speech_seconds"] = min(unit_duration, decoded_chunks[0]["vad_speech_seconds"])
                chunk_evidence["vad_source"] = decoded_chunks[0].get("vad_source")
            chunk_evidence["transcript_seconds"] = round(sum(
                row["end"] - row["start"] for row in _merged_time_ranges(decoded.get("segments"), unit_duration)
            ), 3)
            processed_chunks.append(chunk_evidence)
            for item in decoded.get("segments", []):
                segment = dict(item)
                segment["start"] = round(min(source_duration, chunk_start + float(item.get("start", 0.0))), 3)
                segment["end"] = round(min(source_duration, chunk_start + float(item.get("end", 0.0))), 3)
                segment["words"] = [
                    {
                        **word,
                        "start": round(min(source_duration, chunk_start + float(word.get("start", 0.0))), 3),
                        "end": round(min(source_duration, chunk_start + float(word.get("end", 0.0))), 3),
                    }
                    for word in item.get("words", [])
                ]
                if segment["end"] > segment["start"]:
                    segments.append(segment)
            for item in decoded.get("words", []):
                word = {
                    **item,
                    "start": round(min(source_duration, chunk_start + float(item.get("start", 0.0))), 3),
                    "end": round(min(source_duration, chunk_start + float(item.get("end", 0.0))), 3),
                }
                if word["end"] > word["start"]:
                    words.append(word)

            decoded_units.append(decoded)

            chunk_start += unit_duration
            chunk_index += 1
            if progress:
                completed = min(0.96, 0.08 + 0.88 * chunk_start / source_duration)
                progress(completed, f"Transcribed unit {chunk_index}/{total_chunks}")

    return {
        # Language is finalized after oversized segments are normalized so the
        # same evidence resolver handles one-window and multi-window recordings.
        "language": requested_language or "unknown",
        "language_probability": 0.0,
        "duration": round(source_duration, 3),
        "model": model_name,
        "device": device,
        "compute_type": compute,
        "segments": segments,
        "words": words,
        "text": " ".join(str(segment.get("text") or "").strip() for segment in segments).strip(),
        "chunked": True,
        "chunk_seconds": round(chunk_seconds, 3),
        "_decoded_language_units": decoded_units,
        "coverage": _coverage_from_chunks(source_duration, processed_chunks, total_chunks, "chunked_decoder_exhaustion"),
    }


def _transcribe_once(
    media_path: Path,
    settings: Settings,
    model_name: str,
    device: str,
    compute: str,
    requested_language: str | None,
    mode: str,
    progress: Callable[[float, str], None] | None,
    cancel_check: Callable[[], None] | None = None,
    source_duration: float = 0.0,
) -> dict[str, Any]:
    if cancel_check:
        cancel_check()
    model, model_name, device, compute = _load_model(settings, device, compute, model_name)
    if cancel_check:
        cancel_check()
    if progress:
        progress(0.08, f"Transcribing with {model_name}")
    should_chunk, chunk_seconds = _chunk_policy(settings, device, float(source_duration or 0.0))
    if requested_language is None and float(source_duration or 0.0) > max(36.0, chunk_seconds * 1.5):
        # Whisper's single-file language probe is biased toward the opening
        # window. For automatic language selection, independently decode several
        # bounded windows once a recording is long enough to contain a silent
        # intro or language-changing pre-roll.
        should_chunk = True
    if should_chunk:
        result = _transcribe_chunked(
            model,
            media_path,
            settings,
            model_name,
            device,
            compute,
            requested_language,
            mode,
            float(source_duration),
            chunk_seconds,
            progress,
            cancel_check,
        )
    else:
        result = _decode_with_model(
            model,
            media_path,
            model_name,
            device,
            compute,
            requested_language,
            mode,
            progress,
            cancel_check,
        )
        if source_duration > 0.0 and isinstance(result.get("coverage"), dict):
            chunks = result["coverage"].get("chunks", [])
            if chunks:
                chunks[0]["end"] = round(source_duration, 3)
                if _finite_number(chunks[0].get("analyzed_end")) < source_duration - 0.5:
                    chunks[0]["status"] = "incomplete"
                result["coverage"] = _coverage_from_chunks(source_duration, chunks, 1, "decoder_exhaustion")
                result["duration"] = round(source_duration, 3)
    decoded_language_units = result.pop("_decoded_language_units", None)
    result["segments"] = _split_oversized_segments(list(result.get("segments") or []))
    result["text"] = " ".join(str(segment.get("text") or "").strip() for segment in result["segments"]).strip()
    return _resolve_language_evidence(result, requested_language, decoded_language_units)


def _transcribe_in_process(
    media_path: Path,
    settings: Settings,
    language: str | None = None,
    progress: Callable[[float, str], None] | None = None,
    performance_mode: str = "auto",
    duration: float = 0.0,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    requested_language = None if not language or language == "auto" else _language_code(language)
    if os.environ.get("CUTROOM_FAKE_TRANSCRIPT"):
        fake = _fake_transcript(media_path)
        return _resolve_language_evidence(fake, requested_language)
    configured_device = str(settings.ai.get("whisper_device", "auto"))
    mode = str(performance_mode or settings.ai.get("performance_mode", "auto"))
    if mode not in {"auto", "lite", "balanced", "quality"}:
        mode = "auto"
    requested_mode = mode
    has_cuda = cuda_available(settings)
    if mode == "auto":
        # Keep CPU-only machines on the light path. A CUDA machine can run the
        # balanced multilingual model efficiently even for long recordings; using
        # Base/CPU solely because the source is long sacrifices both speed and the
        # transcript quality that semantic editing depends on.
        mode = "balanced" if has_cuda else "lite"

    preferred_device, preferred_compute = _resolve_device(settings, mode)
    requested_model = _model_for_request(settings, mode, requested_language, preferred_device)
    resource_fallback = bool(
        configured_device == "auto"
        and has_cuda
        and preferred_device == "cpu"
    )
    try:
        cpu_lite_threshold = float(settings.ai.get("whisper_cpu_lite_threshold_seconds", 600.0))
    except (TypeError, ValueError):
        cpu_lite_threshold = 600.0
    if requested_mode == "auto" and resource_fallback and float(duration or 0.0) >= max(60.0, cpu_lite_threshold):
        # A long Small/Turbo decode on CPU can be slower and heavier than useful.
        # Base/INT8 is the predictable fallback when CUDA lacks safe headroom.
        mode = "lite"
    attempts: list[tuple[str, str]] = [(preferred_device, preferred_compute)]
    if configured_device == "auto" and preferred_device != "cpu":
        attempts.append(("cpu", "int8"))

    errors: list[str] = []
    failed_coverage: dict[str, Any] | None = None
    for device, compute in attempts:
        attempt_mode = mode
        attempt_resource_fallback = resource_fallback
        if (
            device == "cpu"
            and requested_mode == "auto"
            and configured_device == "auto"
            and has_cuda
            and float(duration or 0.0) >= max(60.0, cpu_lite_threshold)
        ):
            attempt_mode = "lite"
            attempt_resource_fallback = True
        model_name_requested = _model_for_request(settings, attempt_mode, requested_language, device)
        try:
            if cancel_check:
                cancel_check()
            if progress:
                progress(0.02, f"Loading transcription model on {device}")
            result = _transcribe_once(
                media_path, settings, model_name_requested, device, compute,
                requested_language, attempt_mode, progress, cancel_check, duration,
            )

            # Auto-language keeps a one-pass fast path. If Quality mode discovers
            # Hebrew, try the Hebrew-specific CTranslate2 model. Keep the completed
            # generic pass until the refinement passes the same quality gate used
            # by the story planner: a larger model can also return empty or weak
            # speech on noisy recordings.
            detected = str(result.get("language") or "unknown")
            hebrew_model = str(settings.ai.get("hebrew_whisper_model") or "").strip()
            should_refine_hebrew = (
                requested_language is None
                and detected == "he"
                and hebrew_model
                and model_name_requested != hebrew_model
                and attempt_mode == "quality"
            )
            if should_refine_hebrew:
                if progress:
                    progress(0.48, "Refining Hebrew transcription")
                auto_detected_language = str(result.get("detected_language") or detected or "he")
                auto_detected_probability = _clamp_probability(
                    result.get("detected_language_probability", result.get("language_probability"))
                )
                auto_detection = (
                    copy.deepcopy(result.get("language_detection"))
                    if isinstance(result.get("language_detection"), dict)
                    else {}
                )
                try:
                    refined = _transcribe_once(
                        media_path, settings, hebrew_model, device, compute,
                        "he", attempt_mode, progress, cancel_check, duration,
                    )
                    refined["language"] = "he"
                    # The second pass is intentionally language-locked; its 1.0
                    # reflects the internal request, not a fresh independent
                    # detection. Preserve the confidence from the automatic pass
                    # so the UI never turns refinement into false certainty.
                    refined["language_probability"] = round(auto_detected_probability, 4)
                    refined["detected_language"] = auto_detected_language
                    refined["detected_language_probability"] = round(auto_detected_probability, 4)
                    detection = auto_detection
                    detection["source"] = "auto_refined"
                    detection["requested_language"] = "auto"
                    detection["refined_language"] = "he"
                    detection["ambiguous"] = bool(
                        detection.get("ambiguous") is True or auto_detected_probability < 0.62
                    )
                    refined["language_detection"] = detection
                    refined_quality = transcript_quality_report(refined)
                    if (
                        transcript_quality_report(result)["usable_for_story"]
                        and not refined_quality["usable_for_story"]
                    ):
                        result["hebrew_refine_warning"] = (
                            "Hebrew refinement failed the speech quality check; kept the usable original transcript: "
                            + ", ".join(refined_quality["reasons"])
                        )
                    else:
                        refined["hebrew_refined"] = True
                        result = refined
                except JobCancelled:
                    raise
                except Exception as refine_exc:
                    # The generic transcript is still useful; a first-use model
                    # download failure must not discard completed work.
                    result["hebrew_refine_warning"] = str(refine_exc)

            if progress:
                progress(1.0, "Transcription ready")
            result["performance_mode"] = attempt_mode
            result["requested_performance_mode"] = requested_mode
            result["requested_model"] = requested_model
            result["requested_device"] = configured_device
            result["requested_compute_type"] = str(settings.ai.get("whisper_compute_type", "auto"))
            result["execution"] = {
                "requested_mode": requested_mode,
                "actual_mode": attempt_mode,
                "requested_model": requested_model,
                "actual_model": result.get("model", model_name_requested),
                "requested_device": configured_device,
                "actual_device": result.get("device", device),
                "actual_compute_type": result.get("compute_type", compute),
                "prior_attempt_errors": list(errors),
            }
            if attempt_resource_fallback:
                result["resource_fallback"] = "cuda_headroom"
            elif errors:
                result["resource_fallback"] = "device_error"
            if result.get("resource_fallback"):
                result["execution"]["fallback_reason"] = result["resource_fallback"]
            return result
        except JobCancelled:
            raise
        except Exception as exc:
            errors.append(f"{device}/{compute}: {exc}")
            if isinstance(exc, TranscriptionIncomplete):
                failed_coverage = exc.coverage
            with _MODEL_LOCK:
                _MODEL_CACHE.pop((model_name_requested, device, compute), None)
    message = "Transcription failed. " + " | ".join(errors)
    if failed_coverage is not None:
        raise TranscriptionIncomplete(message, failed_coverage)
    raise RuntimeError(message)


class TranscriptionWorkerStalled(RuntimeError):
    """Raised when native Whisper inference stops reporting bounded progress."""


def _worker_settings_payload(settings: Settings, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "raw": copy.deepcopy(raw if raw is not None else settings.raw),
        "root": str(settings.root),
        "data_dir": str(settings.data_dir),
        "projects_dir": str(settings.projects_dir),
        "exports_dir": str(settings.exports_dir),
        "cache_dir": str(settings.cache_dir),
        "ffmpeg": str(settings.ffmpeg),
        "ffprobe": str(settings.ffprobe),
    }


def _read_worker_progress(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_transcription_worker(
    media_path: Path,
    settings: Settings,
    language: str | None,
    progress: Callable[[float, str], None] | None,
    performance_mode: str,
    duration: float,
    cancel_check: Callable[[], None] | None,
    *,
    raw_override: dict[str, Any] | None = None,
    progress_floor: float = 0.0,
) -> dict[str, Any]:
    """Run Faster-Whisper outside the server so cancellation can preempt native code."""

    ai = (raw_override or settings.raw).get("ai", {})
    try:
        stall_seconds = max(10.0, float(ai.get("whisper_worker_stall_seconds", 120.0)))
    except (TypeError, ValueError):
        stall_seconds = 120.0
    try:
        load_timeout = max(stall_seconds, float(ai.get("whisper_worker_model_load_timeout_seconds", 900.0)))
    except (TypeError, ValueError):
        load_timeout = 900.0

    temp_parent = settings.cache_dir if settings.cache_dir.is_dir() else None
    with tempfile.TemporaryDirectory(
        prefix="cutroom-transcription-job-",
        dir=str(temp_parent) if temp_parent else None,
    ) as temp_name:
        temp_dir = Path(temp_name)
        request_path = temp_dir / "request.json"
        result_path = temp_dir / "result.json"
        progress_path = temp_dir / "progress.json"
        stderr_path = temp_dir / "worker-stderr.log"
        atomic_write_json(request_path, {
            "media_path": str(media_path),
            "settings": _worker_settings_payload(settings, raw_override),
            "language": language,
            "performance_mode": performance_mode,
            "duration": float(duration or 0.0),
        })
        command = [
            sys.executable,
            "-m",
            "cutroom.transcription_worker",
            str(request_path),
            str(result_path),
            str(progress_path),
        ]
        environment = os.environ.copy()
        environment["CUTROOM_TRANSCRIPTION_WORKER"] = "1"
        environment["PYTHONUTF8"] = "1"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        process: subprocess.Popen[Any] | None = None
        try:
            with stderr_path.open("w", encoding="utf-8") as stderr_handle:
                process = subprocess.Popen(
                    command,
                    cwd=str(settings.root),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=stderr_handle,
                    env=environment,
                    creationflags=creationflags,
                )
                started = time.monotonic()
                last_progress_at = started
                last_marker: tuple[int, int] | None = None
                model_ready = False
                while process.poll() is None:
                    if cancel_check:
                        cancel_check()
                    try:
                        stat = progress_path.stat()
                        marker = (stat.st_mtime_ns, stat.st_size)
                    except OSError:
                        marker = None
                    if marker is not None and marker != last_marker:
                        payload = _read_worker_progress(progress_path)
                        if payload is not None:
                            worker_value = max(0.0, min(1.0, float(payload.get("progress", 0.0) or 0.0)))
                            value = max(max(0.0, min(1.0, float(progress_floor))), worker_value)
                            message = str(payload.get("message") or "Transcribing")
                            last_marker = marker
                            last_progress_at = time.monotonic()
                            model_ready = model_ready or worker_value >= 0.079
                            if progress:
                                progress(value, message)
                    now = time.monotonic()
                    allowed_idle = stall_seconds if model_ready else load_timeout
                    if now - last_progress_at > allowed_idle:
                        stage = "decode" if model_ready else "model loading"
                        raise TranscriptionWorkerStalled(
                            f"Whisper {stage} stopped responding for {round(allowed_idle)} seconds"
                        )
                    time.sleep(0.10)
                returncode = int(process.returncode or 0)

            envelope: dict[str, Any] | None = None
            try:
                decoded = json.loads(result_path.read_text(encoding="utf-8"))
                if isinstance(decoded, dict):
                    envelope = decoded
            except (FileNotFoundError, OSError, ValueError, TypeError):
                envelope = None
            if returncode == 0 and envelope and envelope.get("ok") is True and isinstance(envelope.get("result"), dict):
                return envelope["result"]
            error = str((envelope or {}).get("error") or "Transcription worker exited unexpectedly")
            try:
                stderr_tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:].strip()
            except OSError:
                stderr_tail = ""
            if stderr_tail:
                error = f"{error} | {stderr_tail}"
            if isinstance((envelope or {}).get("coverage"), dict):
                raise TranscriptionIncomplete(error, envelope["coverage"])
            raise RuntimeError(error)
        except BaseException:
            if process is not None:
                _stop_process(process)
            raise
        finally:
            if process is not None:
                _stop_process(process)


def _transcribe_isolated(
    media_path: Path,
    settings: Settings,
    language: str | None,
    progress: Callable[[float, str], None] | None,
    performance_mode: str,
    duration: float,
    cancel_check: Callable[[], None] | None,
) -> dict[str, Any]:
    try:
        return _run_transcription_worker(
            media_path,
            settings,
            language,
            progress,
            performance_mode,
            duration,
            cancel_check,
        )
    except TranscriptionWorkerStalled as exc:
        configured_device = str(settings.ai.get("whisper_device", "auto"))
        if configured_device != "auto":
            raise
        fallback_raw = copy.deepcopy(settings.raw)
        fallback_ai = fallback_raw.setdefault("ai", {})
        fallback_ai["whisper_device"] = "cpu"
        fallback_ai["whisper_compute_type"] = "int8"
        fallback_mode = "lite" if performance_mode == "auto" else performance_mode
        if progress:
            progress(0.08, f"Whisper worker stalled; retrying {fallback_mode} transcription on CPU")
        result = _run_transcription_worker(
            media_path,
            settings,
            language,
            progress,
            fallback_mode,
            duration,
            cancel_check,
            raw_override=fallback_raw,
            progress_floor=0.08,
        )
        result["requested_performance_mode"] = performance_mode
        result["requested_device"] = configured_device
        original_mode = performance_mode
        if original_mode == "auto":
            original_mode = "balanced" if cuda_available(settings) else "lite"
        original_language = None if not language or language == "auto" else _language_code(language)
        result["requested_model"] = _model_for_request(settings, original_mode, original_language, configured_device)
        result["requested_compute_type"] = str(settings.ai.get("whisper_compute_type", "auto"))
        result["resource_fallback"] = "worker_stall"
        execution = result.setdefault("execution", {})
        execution.update({
            "requested_mode": performance_mode,
            "requested_device": configured_device,
            "requested_model": result["requested_model"],
            "fallback_reason": "worker_stall",
            "fallback_detail": str(exc),
        })
        return result


def transcribe(
    media_path: Path,
    settings: Settings,
    language: str | None = None,
    progress: Callable[[float, str], None] | None = None,
    performance_mode: str = "auto",
    duration: float = 0.0,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    from .cloud_ai import enabled, transcribe_cloud
    if enabled(settings):
        return transcribe_cloud(media_path, settings, language, progress, duration, cancel_check)
    isolate = bool(settings.ai.get("whisper_isolate_process", True))
    can_isolate = all(hasattr(settings, name) for name in ("raw", "root", "data_dir", "cache_dir"))
    if (
        isolate
        and can_isolate
        and cancel_check is not None
        and not os.environ.get("CUTROOM_TRANSCRIPTION_WORKER")
        and not os.environ.get("CUTROOM_FAKE_TRANSCRIPT")
    ):
        return _transcribe_isolated(
            media_path,
            settings,
            language,
            progress,
            performance_mode,
            duration,
            cancel_check,
        )
    return _transcribe_in_process(
        media_path,
        settings,
        language,
        progress,
        performance_mode,
        duration,
        cancel_check,
    )


def _transcript_coverage_report(transcript: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Separate processed audio from recognized speech and expose missing evidence."""
    duration = max(0.0, _finite_number(transcript.get("duration")))
    raw = transcript.get("coverage")
    coverage = copy.deepcopy(raw) if isinstance(raw, dict) else {}
    source_duration = _finite_number(coverage.get("source_duration"))
    if source_duration > 0.0:
        duration = source_duration
    analyzed = _merged_time_ranges(coverage.get("analyzed_ranges"), duration)
    mapped_to_timeline = "timeline_offset" in coverage or "timeline_offset" in transcript
    timeline_offset = _finite_number(coverage.get("timeline_offset", transcript.get("timeline_offset")))
    recognized = _merged_time_ranges([
        {"start": _finite_number(row.get("start")) - timeline_offset, "end": _finite_number(row.get("end")) - timeline_offset}
        for row in segments
    ], duration)
    analyzed_seconds = sum(row["end"] - row["start"] for row in analyzed)
    recognized_seconds = sum(row["end"] - row["start"] for row in recognized)
    chunks = [row for row in coverage.get("chunks", []) if isinstance(row, dict)]
    expected = max(0, int(_finite_number(coverage.get("expected_chunks"))))
    completed = max(0, int(_finite_number(coverage.get("completed_chunks"))))
    failed = max(0, int(_finite_number(coverage.get("failed_chunks"))))
    incomplete = max(0, int(_finite_number(coverage.get("incomplete_chunks"))))
    counts_consistent = expected > 0 and completed == expected and not failed and not incomplete
    if chunks:
        counts_consistent = counts_consistent and len(chunks) == expected and all(row.get("status") == "complete" for row in chunks)
    missing_seconds = max(0.0, duration - analyzed_seconds)
    verified = bool(
        coverage.get("complete") is True and counts_consistent and duration > 0.0
        and missing_seconds <= max(0.5, duration * 0.0001)
    )
    explicitly_incomplete = bool(coverage and (
        coverage.get("complete") is False or failed or incomplete
        or (coverage.get("complete") is True and not verified)
        or (expected > 0 and completed < expected)
        or (analyzed and missing_seconds > max(0.5, duration * 0.0001))
        or any(row.get("status") in {"failed", "incomplete", "pending"} for row in chunks)
    ))
    status = "complete" if verified else ("incomplete" if explicitly_incomplete else "unverified")
    warnings: list[str] = []
    if not verified and not explicitly_incomplete and duration >= 120.0:
        # A long quiet ending is legitimate. This asks for completion evidence,
        # without treating that ending itself as proof of missing speech.
        transcript_extent = recognized[-1]["end"] - recognized[0]["start"] if recognized else 0.0
        if transcript_extent < duration * 0.5:
            warnings.append("unverified_transcript_coverage")

    vad_seconds = 0.0
    vad_analyzed_seconds = 0.0
    mismatch_chunks: list[dict[str, float]] = []
    for chunk in chunks:
        if chunk.get("vad_source") != "faster_whisper_silero" or chunk.get("status") != "complete":
            continue
        start = max(0.0, _finite_number(chunk.get("start")))
        end = min(duration, _finite_number(chunk.get("analyzed_end")))
        unit_duration = max(0.0, end - start)
        detected = _finite_number(chunk.get("vad_speech_seconds"), -1.0)
        if detected < 0.0 or detected > unit_duration + 0.5:
            continue
        detected = min(unit_duration, detected)
        vad_seconds += detected
        vad_analyzed_seconds += unit_duration
        observed = _finite_number(chunk.get("transcript_seconds"), -1.0)
        if observed < 0.0:
            if mapped_to_timeline:
                # Mapping may deliberately clip source speech outside the edit
                # timeline. Missing source-local ASR evidence stays unknown.
                continue
            observed = sum(max(0.0, min(end, row["end"]) - max(start, row["start"])) for row in recognized)
        # VAD includes padding and can react to game/music audio. Require a
        # substantial disagreement; this is a recovery signal, not an assertion
        # that all VAD-positive audio contains intelligible conversation.
        if detected >= 12.0 and observed < detected * 0.20:
            mismatch_chunks.append({"start": start, "end": end, "vad_seconds": detected, "transcript_seconds": observed})
    mismatch_seconds = sum(row["vad_seconds"] - row["transcript_seconds"] for row in mismatch_chunks)
    return {
        **coverage,
        "source_duration": round(duration, 3),
        "timestamp_frame": "source",
        "status": status,
        "complete": verified,
        "analyzed_ranges": analyzed,
        "analyzed_seconds": round(analyzed_seconds, 3),
        "analyzed_ratio": round(min(1.0, analyzed_seconds / duration), 6) if duration else None,
        "unverified_seconds": round(missing_seconds, 3),
        "transcript_first_second": round(recognized[0]["start"], 3) if recognized else None,
        "transcript_last_second": round(recognized[-1]["end"], 3) if recognized else None,
        "transcript_seconds": round(recognized_seconds, 3),
        "vad_source": "faster_whisper_silero" if vad_analyzed_seconds else None,
        "vad_analyzed_seconds": round(vad_analyzed_seconds, 3),
        "vad_speech_seconds": round(vad_seconds, 3) if vad_analyzed_seconds else None,
        "vad_mismatch_chunks": mismatch_chunks,
        "suspected_uncovered_speech": mismatch_seconds >= 15.0,
        "warnings": warnings,
    }


def transcript_quality_report(transcript: dict[str, Any] | None) -> dict[str, Any]:
    """Return a conservative semantic-ASR quality signal.

    Missing confidence metadata is treated as unknown rather than bad so imported
    transcripts and test fixtures remain usable. The gate is deliberately aimed at
    obvious failures such as the low-confidence, very long hallucinated segments
    produced by a weak model on long Hebrew recordings.
    """

    transcript = transcript if isinstance(transcript, dict) else {}
    segments = [item for item in transcript.get("segments", []) if isinstance(item, dict)]
    text = str(transcript.get("text") or "").strip()
    probabilities = [
        probability for item in segments
        for probability in [_finite_number(item.get("avg_logprob"), float("nan"))]
        if math.isfinite(probability)
    ]
    mean_logprob = sum(probabilities) / len(probabilities) if probabilities else None
    durations = [max(0.0, _finite_number(item.get("end")) - _finite_number(item.get("start"))) for item in segments]
    longest_segment = max(durations, default=0.0)
    language_probability = transcript.get("language_probability")
    try:
        language_probability = float(language_probability) if language_probability is not None else None
    except (TypeError, ValueError):
        language_probability = None
    if language_probability is not None:
        language_probability = (
            max(0.0, min(1.0, language_probability))
            if math.isfinite(language_probability)
            else None
        )
    detected_language_probability = transcript.get("detected_language_probability")
    try:
        detected_language_probability = (
            float(detected_language_probability)
            if detected_language_probability is not None
            else language_probability
        )
    except (TypeError, ValueError):
        detected_language_probability = None
    if detected_language_probability is not None:
        detected_language_probability = (
            max(0.0, min(1.0, detected_language_probability))
            if math.isfinite(detected_language_probability)
            else None
        )
    language_detection = (
        copy.deepcopy(transcript.get("language_detection"))
        if isinstance(transcript.get("language_detection"), dict)
        else {}
    )
    reasons: list[str] = []
    coverage = _transcript_coverage_report(transcript, segments)
    transcript_duration = max(0.0, _finite_number(transcript.get("duration")))
    speech_seconds = float(coverage["transcript_seconds"])
    speech_ratio = min(1.0, speech_seconds / transcript_duration) if transcript_duration > 0.0 else 0.0
    # A clean sentence can be a complete eight-second Reel. Treating every short
    # transcript as unusable rejected valid short clips; sparse speech is only a
    # semantic problem when the recording itself is substantially longer.
    sparse_long_recording = transcript_duration > 60.0 and speech_ratio < 0.01 and coverage["status"] != "complete"
    # Character counts vary sharply between writing systems. A short string in
    # Japanese can be a full sentence; only pair this hint with tiny speech time.
    short_unverified_text = (
        len(text) < 40 and speech_seconds < 3.0 and transcript_duration > 30.0
        and coverage["status"] != "complete"
    )
    if not text or not segments or short_unverified_text or sparse_long_recording:
        reasons.append("too_little_speech")
    if coverage["status"] == "incomplete":
        reasons.append("incomplete_transcription")
    if coverage["suspected_uncovered_speech"]:
        reasons.append("uncovered_detected_speech")
    if language_probability is not None and language_probability < 0.62:
        reasons.append("low_language_confidence")
    if (
        language_detection.get("ambiguous") is True
        and str(language_detection.get("source") or "") != "explicit"
        and "low_language_confidence" not in reasons
    ):
        reasons.append("ambiguous_language_evidence")
    if mean_logprob is not None and mean_logprob < -0.92:
        reasons.append("low_transcript_confidence")
    if longest_segment > 90.0:
        reasons.append("implausibly_long_segment")
    return {
        "usable_for_story": not reasons,
        "reasons": reasons,
        "segment_count": len(segments),
        "text_characters": len(text),
        "language": str(transcript.get("language") or "unknown"),
        "language_probability": language_probability,
        "detected_language": str(transcript.get("detected_language") or transcript.get("language") or "unknown"),
        "detected_language_probability": detected_language_probability,
        "language_detection": language_detection,
        "mean_logprob": round(mean_logprob, 4) if mean_logprob is not None else None,
        "longest_segment": round(longest_segment, 3),
        "speech_seconds": round(speech_seconds, 3),
        "speech_ratio": round(speech_ratio, 6),
        "coverage": coverage,
        "coverage_status": coverage["status"],
        "warnings": coverage["warnings"],
    }


def _fake_transcript(media_path: Path) -> dict[str, Any]:
    duration = 12.0
    sidecar = media_path.with_suffix(media_path.suffix + ".transcript.txt")
    text = sidecar.read_text(encoding="utf-8") if sidecar.exists() else (
        "Welcome to Cutroom. Um, today we are going to explain the workflow. "
        "Today we are going to explain the workflow clearly. This is the useful part. "
        "The final result should be concise and easy to publish."
    )
    chunks = [chunk.strip() for chunk in text.replace("?", ".").replace("!", ".").split(".") if chunk.strip()]
    step = duration / max(1, len(chunks))
    segments = []
    words = []
    for index, chunk in enumerate(chunks):
        start, end = index * step, (index + 1) * step
        tokens = chunk.split()
        word_step = (end - start) / max(1, len(tokens))
        segment_words = []
        for word_index, token in enumerate(tokens):
            word = {"start": round(start + word_index * word_step, 3), "end": round(start + (word_index + 1) * word_step, 3), "word": token, "probability": 0.99}
            words.append(word)
            segment_words.append(word)
        segments.append({"id": f"s{index + 1:04d}", "start": round(start, 3), "end": round(end, 3), "text": chunk, "normalized": normalize_text(chunk), "words": segment_words, "avg_logprob": -0.1, "no_speech_prob": 0.01})
    return {"language": "en", "language_probability": 0.99, "duration": duration, "model": "fake", "device": "cpu", "compute_type": "fake", "segments": segments, "words": words, "text": text}
