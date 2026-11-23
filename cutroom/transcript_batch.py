"""Scratch-only atomic, reviewed original-transcript correction preparation."""
from __future__ import annotations

import copy
import math
from typing import Any

from cutroom.caption_alternatives import status as alternative_status
from cutroom.caption_items import CaptionError, apply_corrections, corrections, segment_key

MAX_ITEMS = 1000
MAX_TEXT = 4000
ITEM_FIELDS = frozenset({"segment_id", "base_text", "start", "end", "text"})


def _time(value: Any) -> bool:
    return type(value) in (int, float) and abs(value) <= 604800 and math.isfinite(value)


def _unicode(value: Any, limit: int) -> bool:
    return isinstance(value, str) and len(value) <= limit and not any(0xD800 <= ord(char) <= 0xDFFF for char in value)


def _validate_history(manual: dict[str, Any]) -> None:
    history = manual.get("_history", {"undo": [], "redo": []})
    if (not isinstance(history, dict) or not {"undo", "redo"} <= history.keys()
            or any(not isinstance(history[key], list) or len(history[key]) > 20
                   or any(not isinstance(entry, dict) for entry in history[key]) for key in ("undo", "redo"))):
        raise CaptionError("Saved edit history is invalid; review the project before saving transcript changes")
    counts = manual.get("history")
    if "history" not in manual:
        if history["undo"] or history["redo"]:
            raise CaptionError("Saved edit history counts are unavailable")
        return
    if (not isinstance(counts, dict) or set(counts) != {"undo_count", "redo_count"}
            or any(type(counts[f"{key}_count"]) is not int or counts[f"{key}_count"] != len(history[key])
                   for key in ("undo", "redo"))):
        raise CaptionError("Saved edit history counts do not match")


def prepare_transcript_batch(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Validate every reviewed source row before constructing a single overlay.

    None means genuine no-op, including stale unrelated overlays. Unselected
    malformed/unknown overlay entries are preserved, not normalized or adopted.
    """
    if not isinstance(payload, dict) or set(payload) != {"action", "items"} or payload.get("action") != "transcript_text_batch":
        raise CaptionError("Transcript batch fields are invalid")
    items = payload.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise CaptionError("Review between 1 and 1000 transcript lines together")
    if alternative_status(project)["active_id"] != "original":
        raise CaptionError("Alternative captions are active. Switch back before correcting the original transcript.")
    analysis = project.get("analysis")
    transcript = analysis.get("transcript") if isinstance(analysis, dict) else None
    segments = transcript.get("segments") if isinstance(transcript, dict) else None
    if not isinstance(segments, list):
        raise CaptionError("The original transcript is unavailable")
    manual = project.get("manual")
    if "manual" in project and not isinstance(manual, dict):
        raise CaptionError("Saved caption state is invalid")
    _validate_history(manual or {})
    raw_fixes = (manual or {}).get("caption_corrections", {})
    if not isinstance(raw_fixes, dict):
        raise CaptionError("Saved transcript corrections are invalid")
    effective, _ = apply_corrections(transcript, corrections(project))
    effective_segments = effective.get("segments", [])
    by_id: dict[str, list[int]] = {}
    for index, segment in enumerate(segments):
        if isinstance(segment, dict):
            by_id.setdefault(segment_key(segment, index), []).append(index)
    reviewed = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != ITEM_FIELDS:
            raise CaptionError("Each transcript correction requires exact reviewed fields")
        key = item["segment_id"]
        if not _unicode(key, 128) or not key or key in seen:
            raise CaptionError("Choose unique transcript segment IDs")
        seen.add(key)
        matches = by_id.get(key, [])
        if len(matches) != 1:
            raise CaptionError("The reviewed transcript identity is missing or ambiguous")
        index = matches[0]
        raw, current = segments[index], effective_segments[index]
        if key in raw_fixes:
            saved_fix = raw_fixes[key]
            if (not isinstance(saved_fix, dict) or set(saved_fix) != {"original", "text"}
                    or not _unicode(saved_fix["original"], 20000) or not _unicode(saved_fix["text"], 20000)):
                raise CaptionError("The selected saved transcript correction is invalid")
        raw_id = raw.get("id", index)
        if type(raw_id) not in (str, int) or isinstance(raw_id, str) and not raw_id:
            raise CaptionError("The saved transcript identity is invalid")
        if not _unicode(raw.get("text"), 20000) or not _unicode(current.get("text"), 20000):
            raise CaptionError("The saved transcript text is invalid")
        if not all(_time(v) for v in (raw.get("start"), raw.get("end"), item["start"], item["end"])):
            raise CaptionError("Transcript times must be finite saved source times")
        if raw["end"] <= raw["start"] or item["start"] != raw["start"] or item["end"] != raw["end"]:
            raise CaptionError("The reviewed transcript timing changed")
        if not _unicode(item["base_text"], 20000) or item["base_text"] != current["text"]:
            raise CaptionError("The reviewed transcript text changed")
        if not _unicode(item["text"], 20000):
            raise CaptionError("Transcript text must be a string")
        text = item["text"].strip()
        if not text or len(text) > MAX_TEXT:
            raise CaptionError("Transcript text must contain between 1 and 4000 characters")
        # Comparing effective stripped text matches the existing singular no-op
        # semantics, while the reviewed base above remains byte-exact.
        reviewed.append((key, raw["text"].strip(), current["text"].strip(), text))
    result = copy.deepcopy(raw_fixes)
    changed = False
    for key, original, current, text in reviewed:
        if text == current:
            continue
        changed = True
        if text == original:
            result.pop(key, None)
        else:
            result[key] = {"original": original, "text": text}
    return result if changed else None
