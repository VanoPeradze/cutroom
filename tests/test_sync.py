from __future__ import annotations

import numpy as np

from cutroom.sync import _fft_correlation


def test_fft_correlation_finds_known_lag():
    rng = np.random.default_rng(42)
    base = rng.normal(size=800)
    delayed = np.concatenate([np.zeros(35), base[:-35]])
    correlation = _fft_correlation(base, delayed)
    lags = np.arange(-(delayed.size - 1), base.size)
    best = int(lags[int(np.argmax(correlation))])
    assert abs(best + 35) <= 1 or abs(best - 35) <= 1
