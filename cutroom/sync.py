from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .config import Settings
from .media import run_command


MIN_AUTOMATIC_SYNC_CONFIDENCE = 0.18
MIN_AUTOMATIC_SYNC_CORRELATION = 0.60
MIN_AUTOMATIC_SYNC_OVERLAP_SECONDS = 10.0
SYNC_SAMPLE_HZ = 100
SYNC_AUDIO_WINDOW_SECONDS = 240


def _audio_envelope(
    path: Path,
    settings: Settings,
    max_seconds: int = SYNC_AUDIO_WINDOW_SECONDS,
    sample_rate: int = 8000,
    envelope_hz: int = SYNC_SAMPLE_HZ,
    cancel_check: Callable[[], None] | None = None,
) -> np.ndarray:
    command = [
        settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-t", str(max_seconds), "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "f32le", "pipe:1",
    ]
    result = run_command(command, check=True, text=False, cancel_check=cancel_check)
    audio = np.frombuffer(result.stdout, dtype=np.float32)
    if audio.size < sample_rate:
        raise ValueError("Not enough audio to synchronize")
    if not np.all(np.isfinite(audio)):
        raise ValueError("Source audio contains invalid samples; automatic sync is unavailable")
    block = max(1, sample_rate // envelope_hz)
    audio = audio[: (audio.size // block) * block]
    envelope = np.sqrt(np.mean(np.square(audio.reshape(-1, block)), axis=1) + 1e-12)
    envelope = envelope - np.median(envelope)
    scale = np.std(envelope)
    return envelope / scale if scale > 1e-8 else envelope


def _fft_correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    size = 1 << int(np.ceil(np.log2(a.size + b.size - 1)))
    spectrum = np.fft.rfft(a, size) * np.conj(np.fft.rfft(b, size))
    correlation = np.fft.irfft(spectrum, size)
    return np.concatenate((correlation[-(b.size - 1):], correlation[:a.size])) if b.size > 1 else correlation[:a.size]


def _overlap_correlations(
    a: np.ndarray, b: np.ndarray, lags: np.ndarray, correlation: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Pearson correlation for the samples actually shared at each lag.

    Different recording lengths must not discard the end of A. Raw correlation
    also rewards long overlaps and can give arbitrary peaks for silent audio.
    Prefix sums make per-lag centering and normalization inexpensive.
    """

    start_a = np.maximum(lags, 0)
    start_b = np.maximum(-lags, 0)
    overlap = np.minimum(a.size - start_a, b.size - start_b)
    sum_a = np.concatenate(([0.0], np.cumsum(a, dtype=np.float64)))
    sum_b = np.concatenate(([0.0], np.cumsum(b, dtype=np.float64)))
    squares_a = np.concatenate(([0.0], np.cumsum(a * a, dtype=np.float64)))
    squares_b = np.concatenate(([0.0], np.cumsum(b * b, dtype=np.float64)))
    total_a = sum_a[start_a + overlap] - sum_a[start_a]
    total_b = sum_b[start_b + overlap] - sum_b[start_b]
    variance_a = squares_a[start_a + overlap] - squares_a[start_a] - total_a * total_a / overlap
    variance_b = squares_b[start_b + overlap] - squares_b[start_b] - total_b * total_b / overlap
    denominator = np.sqrt(np.maximum(variance_a, 0.0) * np.maximum(variance_b, 0.0))
    normalized = np.zeros(lags.size, dtype=np.float64)
    usable = (overlap >= 2) & (denominator > 1e-8)
    normalized[usable] = (correlation[usable] - total_a[usable] * total_b[usable] / overlap[usable]) / denominator[usable]
    return np.clip(normalized, -1.0, 1.0), overlap


def synchronize_sources(
    source_a: Path,
    source_b: Path,
    settings: Settings,
    max_offset_seconds: float = 30.0,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    try:
        max_offset_seconds = float(max_offset_seconds)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Automatic sync search offset must be a finite nonnegative number") from exc
    if not math.isfinite(max_offset_seconds) or max_offset_seconds < 0:
        raise ValueError("Automatic sync search offset must be a finite nonnegative number")
    if cancel_check:
        cancel_check()
    if progress:
        progress(0.1, "Reading source A audio")
    a = _audio_envelope(source_a, settings, cancel_check=cancel_check)
    if cancel_check:
        cancel_check()
    if progress:
        progress(0.35, "Reading source B audio")
    b = _audio_envelope(source_b, settings, cancel_check=cancel_check)
    if cancel_check:
        cancel_check()
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a.ndim != 1 or b.ndim != 1 or min(a.size, b.size) < 2:
        raise ValueError("Not enough audio to synchronize")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("Source audio contains invalid samples; automatic sync is unavailable")
    if progress:
        progress(0.65, "Matching waveforms")
    correlation = _fft_correlation(a, b)
    if cancel_check:
        cancel_check()
    lags = np.arange(-(b.size - 1), a.size)
    # Bound before conversion so a finite but very large caller value cannot
    # overflow, or allocate a search larger than the extracted audio.
    max_lag = int(min(max_offset_seconds, max(a.size, b.size) / SYNC_SAMPLE_HZ) * SYNC_SAMPLE_HZ)
    valid = (lags >= -max_lag) & (lags <= max_lag)
    valid_corr = correlation[valid]
    valid_lags = lags[valid]
    normalized, overlap = _overlap_correlations(a, b, valid_lags, valid_corr)
    enough_overlap = overlap >= int(MIN_AUTOMATIC_SYNC_OVERLAP_SECONDS * SYNC_SAMPLE_HZ)
    eligible = normalized.copy()
    eligible[~enough_overlap] = -np.inf
    # Keep the raw peak only as a diagnostic if no useful overlap/variation is
    # available. It must never promote silence or a tiny overlap to a match.
    usable_peak = bool(np.any(enough_overlap & (normalized > 0.0)))
    best_index = int(np.argmax(eligible if usable_peak else valid_corr))
    lag = int(valid_lags[best_index])
    peak = max(0.0, float(normalized[best_index])) if usable_peak else 0.0
    # Neighbouring envelope samples describe the same peak. Repeated distant
    # peaks (music beats, tones, ramps) do not establish a unique alignment.
    alternatives = enough_overlap & (np.abs(valid_lags - lag) > SYNC_SAMPLE_HZ)
    runner_up = max(0.0, float(np.max(normalized[alternatives]))) if np.any(alternatives) else 0.0
    uniqueness = max(0.0, (peak - runner_up) / max(1.0 - runner_up, 1e-9))
    if max_lag > 0 and not np.any(alternatives):
        # Too little audio to distinguish this peak from competing alignments.
        uniqueness = 0.0
    confidence = min(1.0, peak * uniqueness)
    # Positive offset means source B starts later on the shared timeline. Weak
    # correlations are common when screen capture and camera files contain
    # unrelated audio. Applying that lag can move B entirely off the A timeline,
    # so keep the measurement for diagnostics but use the safe zero offset.
    measured_offset = round(lag / SYNC_SAMPLE_HZ, 3)
    reliable = peak >= MIN_AUTOMATIC_SYNC_CORRELATION and confidence >= MIN_AUTOMATIC_SYNC_CONFIDENCE
    offset = measured_offset if reliable else 0.0
    if progress:
        progress(1.0, "Sources synchronized from matching audio" if reliable else "Automatic sync unconfirmed; check source alignment")
    result = {
        "offset": offset,
        "confidence": round(confidence, 3),
        "method": "audio_cross_correlation",
        "sample_hz": SYNC_SAMPLE_HZ,
        "reliable": reliable,
        "status": "confirmed" if reliable else "unconfirmed",
        "correlation": round(peak, 3),
        "overlap_seconds": round(int(overlap[best_index]) / SYNC_SAMPLE_HZ, 3),
        "search_scope": {
            "source_a_seconds": round(a.size / SYNC_SAMPLE_HZ, 3),
            "source_b_seconds": round(b.size / SYNC_SAMPLE_HZ, 3),
            "audio_window_seconds": SYNC_AUDIO_WINDOW_SECONDS,
            "max_offset_seconds": max_offset_seconds,
            "searched_offset_seconds": [int(valid_lags[0]) / SYNC_SAMPLE_HZ, int(valid_lags[-1]) / SYNC_SAMPLE_HZ],
        },
    }
    if not reliable:
        result["measured_offset"] = measured_offset
        result["warning"] = (
            "Automatic audio sync could not confirm a shared recording. The zero offset is unconfirmed; "
            "check the source start times and set a manual offset if needed. Only the first 240 seconds "
            "of each file were checked within the reported offset search range."
        )
    return result
