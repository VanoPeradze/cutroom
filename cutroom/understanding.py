"""A saved "video map": who speaks when, sound events, topics and shot rhythm.

Everything here is measured locally with FFmpeg and NumPy. No model is
downloaded and this map is not sent to cloud Story providers. These are estimates, so
every part carries its method and confidence. Story receives them only as
advisory background, never as proof that something happened.

- Speakers: per-utterance voice fingerprints (log band energies) clustered
  with k-means; a single speaker is assumed unless clusters separate clearly.
- Sound events: laughter (bursty voiced energy at 3-7 Hz), applause (loud,
  noise-like, sustained) and music (tonal, steady, without speech), plus
  explicit transcript markers such as "haha", "חחח" or "[laughter]".
- Topics: lexical shifts between neighbouring transcript blocks.
- Visual rhythm: shot changes per minute and stable faces, from analysis
  that already exists.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .utils import normalize_text

VIDEO_MAP_VERSION = "video-map-2026-11-23.v2"
SAMPLE_RATE = 8000
FRAME = 256  # 32 ms at 8 kHz
MAX_DECODE_SECONDS = 4 * 3600
MAX_SPEAKERS = 4
MIN_SPEAKER_SILHOUETTE = 0.22
MIN_SPEAKER_SHARE = 0.08
_BANDS = 18

_TRANSCRIPT_LAUGHTER = re.compile(
    r"(?:\b(?:ha){2,}h?\b|\bhehe+\b|\blol\b|\blmao\b|ח{3,}|\[(?:laugh|laughter|laughs|צחוק)[^\]]*\]|\((?:laugh|laughs|laughter|צוחק|צוחקת|צחוק)[^)]*\))",
    re.IGNORECASE,
)
_TRANSCRIPT_APPLAUSE = re.compile(r"\[(?:applause|מחיאות כפיים)[^\]]*\]|\((?:applause|מחיאות כפיים)[^)]*\)", re.IGNORECASE)
_TRANSCRIPT_MUSIC = re.compile(r"\[(?:music|מוזיקה)[^\]]*\]|\((?:music|מוזיקה)[^)]*\)|♪", re.IGNORECASE)

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at", "for", "with", "is", "are", "was", "were",
    "be", "been", "it", "this", "that", "these", "those", "i", "you", "he", "she", "we", "they", "me", "my", "your",
    "so", "like", "just", "um", "uh", "yeah", "ok", "okay", "not", "no", "yes", "do", "did", "have", "has", "had",
    "what", "there", "here", "if", "then", "about", "can", "will", "would", "know", "really", "get", "got", "all",
    "את", "של", "על", "זה", "זאת", "אני", "אתה", "את", "הוא", "היא", "אנחנו", "הם", "הן", "לא", "כן", "גם", "אבל",
    "או", "עם", "מה", "אם", "כי", "יש", "אין", "היה", "הייתה", "אז", "כאילו", "ממש", "בעצם", "פה", "שם", "עוד",
    "כל", "רק", "אה", "אמ", "טוב", "יאללה", "וזה", "שזה", "לי", "לך", "לו", "לה", "לנו", "להם", "אותו", "אותה",
}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def decode_mono(path: Path, settings: Any, duration: float, *, cancel_check: Callable[[], None] | None = None) -> np.ndarray | None:
    """Decode a bounded, local 8 kHz mono PCM stream, or return no evidence."""
    from .jobs import JobCancelled
    from .media import run_command

    if not math.isfinite(duration) or duration < 1 or duration > MAX_DECODE_SECONDS:
        return None
    try:
        result = run_command(
            [settings.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
             "-protocol_whitelist", "file,pipe", "-i", str(path.absolute()),
             "-t", f"{duration:.6f}", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
             "-f", "s16le", "pipe:1"],
            text=False, timeout=max(120, duration * 0.5), cancel_check=cancel_check,
        )
    except JobCancelled:
        raise
    except Exception:  # noqa: BLE001 - a missing map must never stop the edit
        return None
    pcm = result.stdout or b""
    if len(pcm) % 2 or not 2 * SAMPLE_RATE <= len(pcm) <= 2 * math.ceil(duration * SAMPLE_RATE):
        return None
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    samples *= 1.0 / 32768.0
    return samples


def _frames(samples: np.ndarray) -> np.ndarray:
    count = samples.size // FRAME
    if count <= 0:
        return np.zeros((0, FRAME), dtype=np.float32)
    return samples[: count * FRAME].reshape(count, FRAME)


def _power_spectra(frames: np.ndarray) -> np.ndarray:
    if not len(frames):
        return np.zeros((0, FRAME // 2 + 1), dtype=np.float32)
    window = np.hanning(FRAME).astype(np.float32)
    return (np.abs(np.fft.rfft(frames * window, axis=1)) ** 2).astype(np.float32) + 1e-10


def _band_edges() -> np.ndarray:
    frequencies = np.geomspace(90.0, 3800.0, _BANDS + 1)
    return np.clip(np.round(frequencies / (SAMPLE_RATE / FRAME)).astype(int), 1, FRAME // 2)


def _voice_vector(samples: np.ndarray) -> np.ndarray | None:
    frames = _frames(samples)
    if len(frames) < 8:
        return None
    energy = np.sqrt(np.mean(frames * frames, axis=1))
    voiced = frames[energy >= np.quantile(energy, 0.4)]
    spectra = _power_spectra(voiced)
    edges = _band_edges()
    bands = np.stack([spectra[:, edges[i]:max(edges[i] + 1, edges[i + 1])].sum(axis=1) for i in range(_BANDS)], axis=1)
    logs = np.log(bands + 1e-9)
    logs -= logs.mean(axis=1, keepdims=True)  # loudness-independent timbre
    bins = np.arange(spectra.shape[1], dtype=np.float32)
    centroid = (spectra * bins).sum(axis=1) / spectra.sum(axis=1)
    return np.concatenate([logs.mean(axis=0), logs.std(axis=0), [centroid.mean() / spectra.shape[1]]])


def _kmeans(points: np.ndarray, k: int, *, iterations: int = 40) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(17)
    centers = [points[int(rng.integers(len(points)))]]
    for _ in range(1, k):
        distance = np.min([np.sum((points - center) ** 2, axis=1) for center in centers], axis=0)
        total = float(distance.sum())
        index = int(rng.choice(len(points), p=distance / total)) if total > 0 else int(rng.integers(len(points)))
        centers.append(points[index])
    centroids = np.array(centers)
    labels = np.zeros(len(points), dtype=int)
    for _ in range(iterations):
        labels = np.argmin(((points[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2), axis=1)
        updated = np.array([points[labels == i].mean(axis=0) if np.any(labels == i) else centroids[i] for i in range(k)])
        if np.allclose(updated, centroids):
            break
        centroids = updated
    return labels, centroids


def _silhouette(points: np.ndarray, labels: np.ndarray) -> float:
    unique = np.unique(labels)
    if len(unique) < 2:
        return 0.0
    squares = (points * points).sum(axis=1)
    distances = np.sqrt(np.maximum(squares[:, None] + squares[None, :] - 2.0 * points @ points.T, 0.0))
    scores = []
    for index, label in enumerate(labels):
        same = labels == label
        same[index] = False
        if not np.any(same):
            scores.append(0.0)
            continue
        inside = distances[index, same].mean()
        outside = min(distances[index, labels == other].mean() for other in unique if other != label)
        scores.append((outside - inside) / max(inside, outside, 1e-9))
    return float(np.mean(scores))


def estimate_speakers(samples: np.ndarray | None, segments: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in segments if isinstance(row, dict) and _number(row.get("end")) - _number(row.get("start")) >= 0.6]
    if samples is None or len(rows) < 6:
        return {"available": False, "reason": "not_enough_speech", "count": 0, "segment_speakers": {}, "turns": []}
    vectors, kept = [], []
    for row in rows[:1500]:
        start = int(_number(row.get("start")) * SAMPLE_RATE)
        end = int(_number(row.get("end")) * SAMPLE_RATE)
        vector = _voice_vector(samples[max(0, start):min(samples.size, end)])
        if vector is not None:
            vectors.append(vector)
            kept.append(row)
    if len(kept) < 6:
        return {"available": False, "reason": "not_enough_speech", "count": 0, "segment_speakers": {}, "turns": []}
    points = np.array(vectors)
    points = (points - points.mean(axis=0)) / (points.std(axis=0) + 1e-6)
    durations = np.array([_number(row["end"]) - _number(row["start"]) for row in kept])
    best_labels, best_score = np.zeros(len(kept), dtype=int), 0.0
    for k in range(2, min(MAX_SPEAKERS, len(kept) // 3) + 1):
        labels, _ = _kmeans(points, k)
        shares = np.array([durations[labels == i].sum() for i in range(k)]) / durations.sum()
        if shares.min() < MIN_SPEAKER_SHARE:
            continue
        score = _silhouette(points, labels)
        if score > best_score + 0.03:
            best_labels, best_score = labels, score
    if best_score < MIN_SPEAKER_SILHOUETTE:
        best_labels = np.zeros(len(kept), dtype=int)
    # Name speakers by first appearance: the opener is "S1".
    order = {label: f"S{rank + 1}" for rank, label in enumerate(dict.fromkeys(best_labels.tolist()))}
    segment_speakers = {str(row.get("id")): order[int(label)] for row, label in zip(kept, best_labels)}
    turns: list[dict[str, Any]] = []
    for row, label in zip(kept, best_labels):
        speaker = order[int(label)]
        start, end = round(_number(row["start"]), 2), round(_number(row["end"]), 2)
        if turns and turns[-1]["speaker"] == speaker and start - turns[-1]["end"] <= 2.5:
            turns[-1]["end"] = end
        else:
            turns.append({"start": start, "end": end, "speaker": speaker})
    count = len(set(order.values()))
    return {"available": True, "method": "voice_timbre_clustering", "estimated": True, "count": count,
            "confidence": round(best_score, 3) if count > 1 else None,
            "segment_speakers": segment_speakers, "turns": turns}


def _speech_mask(times: np.ndarray, segments: list[dict[str, Any]]) -> np.ndarray:
    mask = np.zeros(times.size, dtype=bool)
    for row in segments:
        start, end = _number(row.get("start")), _number(row.get("end"))
        if end > start:
            mask |= (times >= start) & (times < end)
    return mask


def _runs(flags: np.ndarray, times: np.ndarray, hop: float, minimum: float, maximum: float | None = None, gap: float = 0.6) -> list[tuple[float, float]]:
    runs: list[list[float]] = []
    for flag, time in zip(flags, times):
        if not flag:
            continue
        if runs and time - runs[-1][1] <= gap:
            runs[-1][1] = time + hop
        else:
            runs.append([time, time + hop])
    return [(round(float(a), 2), round(float(b), 2)) for a, b in runs if b - a >= minimum and (maximum is None or b - a <= maximum)]


def detect_sound_events(samples: np.ndarray | None, segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in segments:
        text = str(row.get("text") or "")
        for pattern, kind in ((_TRANSCRIPT_LAUGHTER, "laughter"), (_TRANSCRIPT_APPLAUSE, "applause"), (_TRANSCRIPT_MUSIC, "music")):
            if pattern.search(text):
                events.append({"type": kind, "start": round(_number(row.get("start")), 2), "end": round(_number(row.get("end")), 2),
                               "source": "transcript", "confidence": "high"})
    if samples is not None and samples.size >= SAMPLE_RATE * 2:
        frames = _frames(samples)
        rms = np.sqrt(np.mean(frames * frames, axis=1)) + 1e-9
        level = 20 * np.log10(rms)
        spectra = _power_spectra(frames)
        flatness = np.exp(np.mean(np.log(spectra), axis=1)) / np.mean(spectra, axis=1)
        frame_seconds = FRAME / SAMPLE_RATE
        per_window = int(round(1.0 / frame_seconds))  # ~1 s windows
        hop = per_window // 2
        floor = float(np.quantile(level, 0.10))
        starts = np.arange(0, len(frames) - per_window + 1, hop)
        if starts.size:
            times = starts * frame_seconds
            speech = _speech_mask(times + 0.5, segments)
            win_level = np.array([level[s:s + per_window].mean() for s in starts])
            win_flat = np.array([flatness[s:s + per_window].mean() for s in starts])
            win_steady = np.array([level[s:s + per_window].std() for s in starts])
            modulation = np.zeros(starts.size)
            for index, start in enumerate(starts):
                envelope = rms[start:start + per_window * 2] if start + per_window * 2 <= len(rms) else rms[start:start + per_window]
                envelope = envelope - envelope.mean()
                if envelope.size < 16 or not np.any(envelope):
                    continue
                spectrum = np.abs(np.fft.rfft(envelope)) ** 2
                freqs = np.fft.rfftfreq(envelope.size, frame_seconds)
                band = spectrum[(freqs >= 3.0) & (freqs <= 7.0)].sum()
                total = spectrum[(freqs >= 0.5) & (freqs <= 12.0)].sum()
                modulation[index] = band / total if total > 0 else 0.0
            loud = win_level > floor + 12.0
            applause = loud & (win_flat > 0.30) & (win_steady < 6.0) & ~speech
            music = loud & (win_flat < 0.10) & (win_steady < 4.0) & ~speech
            laughter = loud & (modulation > 0.55) & (win_flat >= 0.08) & (win_flat <= 0.40) & (win_steady >= 3.0)
            step = hop * frame_seconds
            for kind, flags, minimum, maximum in (("applause", applause, 1.5, None), ("music", music, 5.0, None),
                                                  ("laughter", laughter, 0.8, 8.0)):
                for start, end in _runs(flags, times, step, minimum, maximum):
                    events.append({"type": kind, "start": start, "end": end, "source": "audio", "confidence": "estimated"})
    events.sort(key=lambda row: (row["start"], row["type"]))
    merged: list[dict[str, Any]] = []
    for event in events:
        previous = merged[-1] if merged else None
        if previous and previous["type"] == event["type"] and event["start"] <= previous["end"] + 0.5:
            previous["end"] = max(previous["end"], event["end"])
            if event["confidence"] == "high":
                previous["confidence"], previous["source"] = "high", "transcript"
        else:
            merged.append(dict(event))
    return merged[:400]


def _keywords(texts: list[str]) -> Counter:
    words = Counter()
    for text in texts:
        for token in normalize_text(text).split():
            if len(token) >= 3 and token not in _STOPWORDS and not token.isdigit():
                words[token] += 1
    return words


def segment_topics(segments: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    rows = sorted((row for row in segments if str(row.get("text") or "").strip()), key=lambda row: _number(row.get("start")))
    if len(rows) < 8 or duration < 90:
        return [{"start": 0.0, "end": round(duration, 2), "keywords": [w for w, _ in _keywords([str(r.get("text")) for r in rows]).most_common(3)]}] if rows else []
    bags = [_keywords([str(row.get("text"))]) for row in rows]
    block = 5
    depths: list[tuple[float, int]] = []
    for index in range(block, len(rows) - block + 1):
        left, right = Counter(), Counter()
        for bag in bags[index - block:index]:
            left.update(bag)
        for bag in bags[index:index + block]:
            right.update(bag)
        shared = sum(left[w] * right[w] for w in left.keys() & right.keys())
        norm = math.sqrt(sum(v * v for v in left.values())) * math.sqrt(sum(v * v for v in right.values()))
        depths.append((shared / norm if norm else 0.0, index))
    if not depths:
        return []
    values = np.array([value for value, _ in depths])
    threshold = float(values.mean() - 0.5 * values.std())
    max_topics = max(1, min(12, int(duration // 60)))
    min_gap = max(45.0, duration / (max_topics * 2))
    boundaries: list[int] = []
    for value, index in sorted(depths):
        if value > threshold or len(boundaries) >= max_topics - 1:
            break
        start = _number(rows[index].get("start"))
        if all(abs(start - _number(rows[other].get("start"))) >= min_gap for other in boundaries) and start >= min_gap and duration - start >= min_gap:
            boundaries.append(index)
    cuts = [0, *sorted(boundaries), len(rows)]
    totals = _keywords([str(row.get("text")) for row in rows])
    topics = []
    for left, right in zip(cuts, cuts[1:]):
        chunk = rows[left:right]
        local = _keywords([str(row.get("text")) for row in chunk])
        ranked = sorted(local, key=lambda word: (local[word] * math.log(1 + sum(totals.values()) / (1 + totals[word])), local[word]), reverse=True)
        topics.append({"start": round(0.0 if left == 0 else _number(chunk[0].get("start")), 2),
                       "end": round(duration if right == len(rows) else _number(rows[right].get("start")), 2),
                       "keywords": ranked[:3]})
    return topics


def visual_rhythm(scenes: list[Any], vision: dict[str, Any] | None, duration: float) -> dict[str, Any]:
    cuts = [value for value in scenes or [] if isinstance(value, (int, float)) and 0 < float(value) < duration]
    clusters = [row for row in (vision or {}).get("face_clusters") or [] if isinstance(row, dict) and _number(row.get("coverage")) >= 0.25]
    return {
        "shot_changes": len(cuts),
        "shots_per_minute": round(len(cuts) / (duration / 60.0), 2) if duration > 0 else None,
        "stable_faces": len(clusters) if (vision or {}).get("available") else None,
        "face_coverage": round(max((_number(row.get("coverage")) for row in clusters), default=0.0), 3) if clusters else None,
    }


def build_video_map(
    *,
    segments: list[dict[str, Any]],
    duration: float,
    samples: np.ndarray | None,
    scenes: list[Any] | None = None,
    vision: dict[str, Any] | None = None,
    audio_reason: str | None = None,
) -> dict[str, Any]:
    speakers = estimate_speakers(samples, segments)
    if samples is None and audio_reason:
        speakers = {**speakers, "reason": audio_reason}
    events = detect_sound_events(samples, segments)
    topics = segment_topics(segments, duration)
    visual = visual_rhythm(scenes or [], vision, duration)
    counts = Counter(event["type"] for event in events)
    return {
        "version": VIDEO_MAP_VERSION,
        "available": True,
        "duration": round(duration, 2),
        "speakers": speakers,
        "events": events,
        "event_counts": dict(counts),
        "topics": topics,
        "visual": visual,
    }


def story_context(video_map: dict[str, Any] | None) -> dict[str, Any] | None:
    """A compact, advisory version of the map for Story prompts."""
    if not isinstance(video_map, dict) or not video_map.get("available"):
        return None
    speakers = video_map.get("speakers") or {}
    compact = {
        "authority": "advisory_only",
        "use": (
            "Locally measured estimates of who speaks when, sound events and topic shifts. Use them to keep a "
            "speaker's turn, a laugh or a reaction together and to understand the structure. They may be wrong "
            "and never replace the transcript, its timing or the user's instruction."
        ),
        "speaker_count": speakers.get("count") if speakers.get("available") else None,
        "speaker_turns": (speakers.get("turns") or [])[:160] if speakers.get("count", 0) > 1 else [],
        "events": [{key: event[key] for key in ("type", "start", "end", "confidence")} for event in (video_map.get("events") or [])[:80]],
        "topics": (video_map.get("topics") or [])[:12],
        "visual": video_map.get("visual"),
    }
    return compact
