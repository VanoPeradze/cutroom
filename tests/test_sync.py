from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cutroom import sync
from cutroom.sync import _fft_correlation


def test_fft_correlation_finds_known_lag():
    rng = np.random.default_rng(42)
    base = rng.normal(size=800)
    delayed = np.concatenate([np.zeros(35), base[:-35]])
    correlation = _fft_correlation(base, delayed)
    lags = np.arange(-(delayed.size - 1), base.size)
    best = int(lags[int(np.argmax(correlation))])
    assert abs(best + 35) <= 1 or abs(best - 35) <= 1


def _synchronize(monkeypatch, a, b, **kwargs):
    envelopes = iter((a, b))
    monkeypatch.setattr(sync, "_audio_envelope", lambda *_args, **_kwargs: next(envelopes))
    return sync.synchronize_sources(Path("A.mp4"), Path("B.mp4"), SimpleNamespace(ffmpeg="ffmpeg"), **kwargs)


def test_sync_uses_full_extracted_a_when_b_is_shorter(monkeypatch):
    rng = np.random.default_rng(100)
    a = rng.normal(size=6000)
    # B begins 20 seconds into A, and extends beyond the first B-length of A.
    # Truncating both recordings to B's length loses most of this evidence.
    b = 3.0 * a[2000:4500] + 7.0
    result = _synchronize(monkeypatch, a, b)

    assert result["reliable"] is True
    assert result["status"] == "confirmed"
    assert result["offset"] == 20.0
    assert result["correlation"] == 1.0
    assert result["overlap_seconds"] == 25.0
    assert result["search_scope"]["source_a_seconds"] == 60.0
    assert result["search_scope"]["source_b_seconds"] == 25.0
    assert result["search_scope"]["searched_offset_seconds"] == [-24.99, 30.0]
    assert "warning" not in result


def test_sync_finds_negative_offset(monkeypatch):
    rng = np.random.default_rng(101)
    b = rng.normal(size=5000)
    a = b[850:3850] + rng.normal(scale=0.1, size=3000)
    result = _synchronize(monkeypatch, a, b)

    assert result["reliable"] is True
    assert result["offset"] == -8.5


def test_sync_matches_smoothed_audio_energy_with_gain_and_background_noise(monkeypatch):
    rng = np.random.default_rng(106)
    energy = np.convolve(rng.normal(size=8000), np.ones(25) / 25, mode="same")
    a = np.exp(energy * 3)
    b = a[425:5425] * 0.5 + rng.normal(scale=0.02, size=5000)
    result = _synchronize(monkeypatch, a, b)

    assert result["reliable"] is True
    assert result["offset"] == 4.25


@pytest.mark.parametrize("kind", ["silence", "constant", "unrelated", "periodic", "ramp"])
def test_sync_does_not_confirm_missing_or_ambiguous_evidence(monkeypatch, kind):
    rng = np.random.default_rng(102)
    if kind == "silence":
        a, b = np.zeros(5000), np.zeros(4000)
    elif kind == "constant":
        a, b = np.full(5000, 3.0), np.full(4000, 9.0)
    elif kind == "unrelated":
        a, b = rng.normal(size=5000), rng.normal(size=4000)
    elif kind == "periodic":
        a = np.sin(np.arange(5000) * (2 * np.pi / 200))
        b = np.sin((np.arange(4000) + 35) * (2 * np.pi / 200))
    else:
        a, b = np.arange(5000, dtype=float), np.arange(4000, dtype=float)
    progress = []
    result = _synchronize(monkeypatch, a, b, progress=lambda value, message: progress.append((value, message)))

    assert result["reliable"] is False
    assert result["status"] == "unconfirmed"
    assert result["offset"] == 0.0
    assert "unconfirmed" in result["warning"]
    assert "first 240 seconds" in result["warning"]
    assert result["search_scope"]["searched_offset_seconds"] == [-30.0, 30.0]
    assert "unconfirmed" in progress[-1][1]
    assert "Sources synchronized" not in progress[-1][1]


def test_sync_does_not_confirm_a_match_outside_search_scope(monkeypatch):
    rng = np.random.default_rng(103)
    a = rng.normal(size=9000)
    b = a[5000:8000]
    result = _synchronize(monkeypatch, a, b, max_offset_seconds=10.0)

    assert result["reliable"] is False
    assert result["offset"] == 0.0
    assert result["search_scope"]["searched_offset_seconds"] == [-10.0, 10.0]


def test_sync_does_not_confirm_tiny_matching_overlap(monkeypatch):
    rng = np.random.default_rng(104)
    a = rng.normal(size=3000)
    b = rng.normal(size=3000)
    b[:100] = a[-100:]
    result = _synchronize(monkeypatch, a, b)

    assert result["reliable"] is False
    assert result["offset"] == 0.0


def test_sync_needs_enough_audio_to_compare_competing_alignments(monkeypatch):
    periodic = np.sin(np.arange(1000) * (2 * np.pi / 200))
    result = _synchronize(monkeypatch, periodic, periodic.copy())

    assert result["reliable"] is False
    assert result["offset"] == 0.0


@pytest.mark.parametrize("max_offset", [float("nan"), float("inf"), -0.1, "not a number", None])
def test_sync_rejects_invalid_search_offsets_before_reading_audio(monkeypatch, max_offset):
    def unexpected_read(*_args, **_kwargs):
        pytest.fail("invalid search offset must not start extraction")

    monkeypatch.setattr(sync, "_audio_envelope", unexpected_read)
    with pytest.raises(ValueError, match="finite nonnegative"):
        sync.synchronize_sources(Path("A.mp4"), Path("B.mp4"), SimpleNamespace(ffmpeg="ffmpeg"), max_offset_seconds=max_offset)


@pytest.mark.parametrize("invalid", [np.array([]), np.array([0.0]), np.array([0.0, np.nan]), np.array([np.inf, 0.0])])
def test_sync_rejects_invalid_envelopes(monkeypatch, invalid):
    with pytest.raises(ValueError, match="audio"):
        _synchronize(monkeypatch, invalid, np.ones(2000))


def test_zero_offset_search_can_confirm_matching_audio(monkeypatch):
    rng = np.random.default_rng(105)
    a = rng.normal(size=2000)
    result = _synchronize(monkeypatch, a, a.copy(), max_offset_seconds=0.0)

    assert result["reliable"] is True
    assert result["offset"] == 0.0
    assert result["search_scope"]["searched_offset_seconds"] == [0.0, 0.0]


def test_single_sample_fft_correlation_has_no_duplicate_tail():
    np.testing.assert_allclose(_fft_correlation(np.array([1.0, 2.0]), np.array([3.0])), [3.0, 6.0])
