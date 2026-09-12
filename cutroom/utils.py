from __future__ import annotations

import json
import math
import os
import re
import tempfile
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any, Iterable


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        # Windows can briefly deny ``os.replace`` while Defender, an indexer or
        # another process is opening the destination.  Progress files are updated
        # frequently, so treating that transient sharing window as a permanent
        # disk failure used to abort an otherwise healthy transcription.  Keep the
        # same atomic replace contract, but give short-lived locks a bounded chance
        # to clear.  Persistent permission problems still propagate to the caller.
        retry_delays = (0.01, 0.02, 0.04, 0.08, 0.12, 0.18, 0.25)
        for attempt in range(len(retry_delays) + 1):
            try:
                os.replace(temp_name, path)
                break
            except PermissionError:
                if attempt >= len(retry_delays):
                    raise
                time.sleep(retry_delays[attempt])
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def sanitize_filename(name: str) -> str:
    base = Path(name or "video").name
    stem = re.sub(r"[^\w. -]+", "_", base, flags=re.UNICODE).strip(" ._")
    return stem[:140] or "video"


def merge_ranges(ranges: Iterable[dict[str, Any] | tuple[float, float]], gap: float = 0.08) -> list[dict[str, float]]:
    normalized: list[tuple[float, float]] = []
    for item in ranges:
        if isinstance(item, dict):
            start, end = float(item.get("start", 0)), float(item.get("end", 0))
        else:
            start, end = float(item[0]), float(item[1])
        if math.isfinite(start) and math.isfinite(end):
            clean_start = max(0.0, start)
            clean_end = max(0.0, end)
            if clean_end > clean_start:
                normalized.append((clean_start, clean_end))
    normalized.sort()
    merged: list[list[float]] = []
    for start, end in normalized:
        if not merged or start > merged[-1][1] + gap:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    output: list[dict[str, float]] = []
    for start, end in merged:
        rounded_start = round(start, 3)
        rounded_end = round(end, 3)
        if rounded_end > rounded_start:
            output.append({"start": rounded_start, "end": rounded_end})
    return output


def invert_ranges(cuts: Iterable[dict[str, Any] | tuple[float, float]], duration: float, min_keep: float = 0.08) -> list[dict[str, float]]:
    duration = max(0.0, float(duration))
    merged = merge_ranges(cuts)
    cursor = 0.0
    keep: list[dict[str, float]] = []
    for cut in merged:
        start = clamp(cut["start"], 0.0, duration)
        end = clamp(cut["end"], 0.0, duration)
        if start > cursor and start - cursor >= min_keep:
            keep.append({"start": round(cursor, 3), "end": round(start, 3)})
        cursor = max(cursor, end)
    if duration > cursor and duration - cursor >= min_keep:
        keep.append({"start": round(cursor, 3), "end": round(duration, 3)})
    return [item for item in keep if item["end"] > item["start"]]


def range_duration(ranges: Iterable[dict[str, Any]]) -> float:
    return round(sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges), 3)


def normalize_text(text: str) -> str:
    value = unicodedata.normalize("NFKC", text or "").lower()
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower().strip() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)
