from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import numpy as np

from .config import Settings
from .media import run_command


MIN_AUTOMATIC_SYNC_CONFIDENCE = 0.18


def _audio_envelope(
    path: Path,
    settings: Settings,
    max_seconds: int = 240,
    sample_rate: int = 8000,
    envelope_hz: int = 100,
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
    return np.concatenate((correlation[-(b.size - 1):], correlation[:a.size]))


def synchronize_sources(
    source_a: Path,
    source_b: Path,
    settings: Settings,
    max_offset_seconds: float = 30.0,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
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
    size = min(a.size, b.size)
    a, b = a[:size], b[:size]
    if progress:
        progress(0.65, "Matching waveforms")
    correlation = _fft_correlation(a, b)
    if cancel_check:
        cancel_check()
    lags = np.arange(-(b.size - 1), a.size)
    max_lag = int(max_offset_seconds * 100)
    valid = (lags >= -max_lag) & (lags <= max_lag)
    valid_corr = correlation[valid]
    valid_lags = lags[valid]
    best_index = int(np.argmax(valid_corr))
    lag = int(valid_lags[best_index])
    peak = float(valid_corr[best_index])
    baseline = float(np.mean(np.abs(valid_corr)) + 1e-9)
    confidence = min(1.0, max(0.0, (peak / baseline - 1.0) / 12.0))
    # Positive offset means source B starts later on the shared timeline. Weak
    # correlations are common when screen capture and camera files contain
    # unrelated audio. Applying that lag can move B entirely off the A timeline,
    # so keep the measurement for diagnostics but use the safe zero offset.
    measured_offset = round(lag / 100.0, 3)
    reliable = confidence >= MIN_AUTOMATIC_SYNC_CONFIDENCE
    offset = measured_offset if reliable else 0.0
    if progress:
        progress(1.0, "Sources synchronized")
    result = {
        "offset": offset,
        "confidence": round(confidence, 3),
        "method": "audio_cross_correlation",
        "sample_hz": 100,
        "reliable": reliable,
    }
    if not reliable:
        result["measured_offset"] = measured_offset
    return result
