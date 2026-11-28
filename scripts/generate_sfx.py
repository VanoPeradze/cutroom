"""Generate Cutroom's original sound effects (web/sfx/*.wav).

Every sound is synthesized here from noise and sine waves with a fixed seed,
so the files are Cutroom's own work, free to use in any video, and can be
rebuilt byte for byte:

    python scripts/generate_sfx.py
"""
from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

RATE = 44_100
OUT = Path(__file__).resolve().parents[1] / "web" / "sfx"


def _env(n: int, attack: float, release: float) -> np.ndarray:
    t = np.linspace(0, 1, n, endpoint=False)
    a = np.clip(t / max(attack, 1e-6), 0, 1)
    r = np.clip((1 - t) / max(release, 1e-6), 0, 1)
    return a * r


def _lowpass(x: np.ndarray, cutoff: np.ndarray) -> np.ndarray:
    """One-pole low-pass with a per-sample cutoff in Hz."""
    out = np.empty_like(x)
    acc = 0.0
    alpha = 1 - np.exp(-2 * np.pi * cutoff / RATE)
    for i, (v, a) in enumerate(zip(x, alpha)):
        acc += a * (v - acc)
        out[i] = acc
    return out


def whoosh(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.7)
    t = np.linspace(0, 1, n, endpoint=False)
    sweep = 300 + 5200 * np.sin(np.pi * t) ** 2
    body = _lowpass(rng.standard_normal(n), sweep) - _lowpass(rng.standard_normal(n), sweep * 0.25) * 0.5
    return body * np.sin(np.pi * t) ** 1.5


def pop(_: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.16)
    t = np.arange(n) / RATE
    freq = 900 * np.exp(-t * 28) + 220
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    return np.sin(phase) * np.exp(-t * 38)


def riser(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 2.0)
    t = np.linspace(0, 1, n, endpoint=False)
    freq = 180 * (2 ** (t * 3))
    tone = np.sin(2 * np.pi * np.cumsum(freq) / RATE) + 0.5 * np.sin(4 * np.pi * np.cumsum(freq) / RATE)
    air = _lowpass(rng.standard_normal(n), 400 + 7000 * t ** 2)
    return (0.6 * tone + 0.8 * air) * (t ** 2) * _env(n, 0.02, 0.03)


def hit(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.9)
    t = np.arange(n) / RATE
    freq = 120 * np.exp(-t * 9) + 42
    thump = np.sin(2 * np.pi * np.cumsum(freq) / RATE) * np.exp(-t * 5.5)
    crack = _lowpass(rng.standard_normal(n), np.full(n, 3500.0)) * np.exp(-t * 60)
    return thump + 0.6 * crack


def click(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.05)
    t = np.arange(n) / RATE
    return (np.sin(2 * np.pi * 2400 * t) * 0.6 + rng.standard_normal(n) * 0.4) * np.exp(-t * 140)


def ding(_: np.random.Generator) -> np.ndarray:
    n = int(RATE * 1.2)
    t = np.arange(n) / RATE
    partials = [(1320, 1.0, 3.2), (2640, 0.35, 5.0), (3960, 0.18, 7.0), (1980, 0.22, 4.0)]
    return sum(a * np.sin(2 * np.pi * f * t) * np.exp(-t * d) for f, a, d in partials) * _env(n, 0.004, 0.02)


def swipe(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.32)
    t = np.linspace(0, 1, n, endpoint=False)
    return _lowpass(rng.standard_normal(n), 1500 + 9000 * t) * np.sin(np.pi * t) ** 0.8


SOUNDS = [
    ("whoosh", "Whoosh", "Transitions and fast moves", whoosh),
    ("swipe", "Swipe", "Quick cuts and slides", swipe),
    ("pop", "Pop", "Text and emoji appearing", pop),
    ("click", "Click", "Buttons, lists, small accents", click),
    ("ding", "Ding", "A point made, a correct answer", ding),
    ("hit", "Hit", "Impact on a key moment", hit),
    ("riser", "Riser", "Build-up before a reveal", riser),
]


def _write(path: Path, samples: np.ndarray) -> None:
    peak = float(np.max(np.abs(samples))) or 1.0
    data = (samples / peak * 0.89 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(data.tobytes())


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    catalog = []
    for index, (key, name, use, make) in enumerate(SOUNDS):
        samples = make(np.random.default_rng(20261128 + index))
        _write(OUT / f"{key}.wav", samples)
        catalog.append({"id": key, "name": name, "use": use, "file": f"{key}.wav",
                        "seconds": round(len(samples) / RATE, 2)})
    (OUT / "catalog.json").write_text(json.dumps({"version": 1, "license": "Original Cutroom sounds, free to use in any video.",
                                                  "sounds": catalog}, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
