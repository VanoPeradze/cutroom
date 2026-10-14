"""Automatic caption items: transcribed speech placed on the edit clock.

An item is one transcript segment's portion inside one contiguous piece of the
edit (a kept range, or a clip of the audio track). Items are derived, never
stored, so the source transcript always stays exactly as it was transcribed.
Two separate layers change what an item shows:

* ``manual.caption_corrections`` fixes the source text of a segment. It applies
  wherever that speech is used and survives a new AI draft. It records the text
  it corrected; after a new transcription replaces that segment it is ignored
  and reported as stale instead of landing on different speech.
* ``manual.caption_overrides`` changes one item: its own text, timing offsets
  from the speech it belongs to (so it moves with its clip), hidden, or its own
  style. An item is identified by the speech it shows, ``<segment>:w<n>`` for a
  portion starting at the segment's n-th transcribed word (``t<seconds>`` without
  word timing), so splitting, moving or trimming other clips does not move an
  edit to different words. Speech used twice adds ``~1``, ``~2`` in edit order.

The same items feed the timeline, the live preview and the exported captions.
"""
from __future__ import annotations

import bisect
import copy
import math
import re
from typing import Any

from .captions import CAPTION_POSITION_CHOICES, CAPTION_SCALE_RANGE, CAPTION_STYLE_CHOICES, HIGHLIGHT_WORDS_PER_CAPTION
from .source_tracks import has_sequence, has_source_tracks, source_track_clips

CAPTION_ACTION_FIELDS: dict[str, set[str]] = {
    "caption_update": {"caption_id", "text", "scope", "start", "end", "style", "position", "scale"},
    "caption_visibility": {"caption_id", "hidden"},
    "caption_reset": {"caption_id"},
}
CAPTION_SCOPES = frozenset({"item", "source"})
MIN_CAPTION_SECONDS = 0.1
MAX_CAPTION_TEXT = 2000
# A pause longer than this starts a new caption line, as in the export.
LINE_PAUSE_SECONDS = 0.75
_RTL = re.compile("[֐-ࣿיִ-﷿ﹰ-﻿]")
_STYLE_KEYS = ("style", "position", "scale")


class CaptionError(ValueError):
    pass


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def segment_key(segment: dict[str, Any], index: int) -> str:
    return str(segment.get("id", index))


def _words(segment: dict[str, Any]) -> list[dict[str, Any]]:
    return [word for word in (segment.get("words") or [])
            if isinstance(word, dict) and str(word.get("word") or "").strip()
            and _finite(word.get("end")) > _finite(word.get("start"))]


def _retext(words: list[dict[str, Any]], text: str) -> list[dict[str, Any]] | None:
    """Word timing for corrected text.

    The same number of words keeps the measured timing. A different number is
    spread over the same spoken time by length and marked ``estimated``, so the
    caption still splits into readable lines; no word is coloured by it.
    """
    tokens = text.split()
    if not words or not tokens:
        return None
    if len(tokens) == len(words):
        return [{**word, "word": token} for word, token in zip(words, tokens)]
    start, end = _finite(words[0].get("start")), _finite(words[-1].get("end"))
    weights = [len(token) + 1 for token in tokens]
    total, cursor, spread = sum(weights), start, []
    for token, weight in zip(tokens, weights):
        span = (end - start) * weight / total
        spread.append({"start": cursor, "end": cursor + span, "word": token, "estimated": True})
        cursor += span
    return spread


def _manual(project: dict[str, Any]) -> dict[str, Any]:
    manual = project.get("manual")
    return manual if isinstance(manual, dict) else {}


def corrections(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = _manual(project).get("caption_corrections")
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)} if isinstance(raw, dict) else {}


def overrides(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = _manual(project).get("caption_overrides")
    return {str(key): value for key, value in raw.items() if isinstance(value, dict)} if isinstance(raw, dict) else {}


def effective_transcript(project: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The transcript with source corrections applied, and the stale correction keys."""
    return apply_corrections((project.get("analysis") or {}).get("transcript"), corrections(project))


def apply_corrections(transcript: Any, fixes: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """A corrected copy of ``transcript`` and the corrections that no longer match it.

    Without corrections the transcript itself is returned; callers only read it.
    """
    if not fixes:
        return (transcript if isinstance(transcript, dict) else {}), []
    transcript = copy.deepcopy(transcript) if isinstance(transcript, dict) else {}
    used: set[str] = set()
    segments = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        key = segment_key(segment, index)
        fix = fixes.get(key)
        if not fix or str(segment.get("text") or "").strip() != str(fix.get("original") or "").strip():
            continue
        used.add(key)
        text = str(fix.get("text") or "").strip()
        if not text:
            continue
        segment["text"] = text
        if "normalized" in segment:
            segment["normalized"] = text
        words = _retext(_words(segment), text)
        if words is None:
            segment.pop("words", None)
        else:
            segment["words"] = words
    if fixes:
        transcript["text"] = " ".join(str(item.get("text") or "").strip() for item in segments if isinstance(item, dict)).strip()
    return transcript, sorted(set(fixes) - used)


def _pieces(project: dict[str, Any], slot: str | None, offset: float,
            keeps: list[dict[str, Any]] | None) -> list[tuple[float, float, float, float]]:
    """Continuous pieces of speech in the edit: (edit start, edit end, transcript start, transcript end).

    Audio clips place the transcript on the timeline (``slot`` is the analyzed
    track, None when it is not on the timeline); without clips the transcript
    clock is the timeline. ``keeps`` are the kept timeline ranges laid end to
    end; None means the timeline already is the edit. Pieces that continue each
    other in both clocks are joined, so splitting a clip or changing its layout
    never splits a caption or renumbers the ones after it.
    """
    if has_sequence(project) or has_source_tracks(project):
        if slot is None:
            return []
        timeline = []
        for clip in source_track_clips(project, slot):
            start, end = _finite(clip.get("start")), _finite(clip.get("end"))
            if end > start:
                timeline.append((start, end, _finite(clip.get("source_start")) + offset))
    else:
        timeline = [(0.0, math.inf, 0.0)]
    pieces: list[tuple[float, float, float, float]] = []
    if keeps is None:
        pieces = [(start, end, source, source + end - start) for start, end, source in timeline]
    else:
        cursor = 0.0
        for keep in keeps:
            keep_start, keep_end = _finite(keep.get("start")), _finite(keep.get("end"))
            if keep_end <= keep_start:
                continue
            for start, end, source in timeline:
                left, right = max(keep_start, start), min(keep_end, end)
                if right > left:
                    source_left = source + left - start
                    pieces.append((cursor + left - keep_start, cursor + right - keep_start,
                                   source_left, source_left + right - left))
            cursor += keep_end - keep_start
    joined: list[tuple[float, float, float, float]] = []
    for piece in sorted(pieces):
        last = joined[-1] if joined else None
        if last and abs(piece[0] - last[1]) < 1e-6 and abs(piece[2] - last[3]) < 1e-6:
            joined[-1] = (last[0], piece[1], last[2], piece[3])
        else:
            joined.append(piece)
    return joined


def _anchor(original: dict[str, Any] | None, source_start: float, source_end: float, portion_start: float) -> str:
    """Name a portion of a segment by its first transcribed word.

    The uncorrected words are used, so a correction never renames an item.
    """
    for number, word in enumerate(_words(original or {})):
        if source_start <= (_finite(word["start"]) + _finite(word["end"])) / 2 < source_end:
            return f"w{number}"
    return f"t{max(0.0, portion_start - _finite((original or {}).get('start'))):.1f}"


def _natural_items(transcript: dict[str, Any], pieces: list[tuple[float, float, float, float]],
                   originals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw_segments = transcript.get("segments") if isinstance(transcript.get("segments"), list) else []
    # Index by start time so a long recording with many cuts stays fast.
    indexed = sorted((_finite(segment.get("start")), index, segment)
                     for index, segment in enumerate(raw_segments) if isinstance(segment, dict))
    starts = [row[0] for row in indexed]
    longest = max((_finite(row[2].get("end")) - row[0] for row in indexed), default=0.0)
    language = str(transcript.get("language") or "")
    occurrence: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for edit_start, _edit_end, source_start, source_end in pieces:
        shift = edit_start - source_start
        nearby = indexed[bisect.bisect_left(starts, source_start - longest):bisect.bisect_left(starts, source_end)]
        for _, index, segment in sorted(nearby, key=lambda row: row[1]):
            key = segment_key(segment, index)
            text = str(segment.get("text") or "").strip()
            seg_start, seg_end = _finite(segment.get("start")), _finite(segment.get("end"))
            if seg_end <= source_start or seg_start >= source_end or not text:
                continue
            words = _words(segment)
            if words:
                # Same rule as the export: a word belongs to the piece holding its
                # midpoint, and is clipped to that piece.
                kept = [word for word in words
                        if source_start <= (_finite(word["start"]) + _finite(word["end"])) / 2 < source_end]
                if not kept:
                    continue
                mapped = [{"start": max(source_start, _finite(word["start"])) + shift,
                           "end": min(source_end, _finite(word["end"])) + shift,
                           "word": str(word["word"]).strip()} for word in kept]
                start, end = mapped[0]["start"], mapped[-1]["end"]
                portion = (max(source_start, _finite(kept[0]["start"])), min(source_end, _finite(kept[-1]["end"])))
                item_text = " ".join(word["word"] for word in mapped) if len(kept) < len(words) else text
            else:
                portion = (max(source_start, seg_start), min(source_end, seg_end))
                if portion[1] - portion[0] < 0.05:
                    continue
                start, end, mapped, item_text = portion[0] + shift, portion[1] + shift, [], text
            if end <= start:
                continue
            original = originals.get(key)
            base = f"{key}:{_anchor(original, source_start, source_end, portion[0])}"
            number = occurrence.get(base, 0)
            occurrence[base] = number + 1
            items.append({
                "id": base if not number else f"{base}~{number}", "segment_id": key, "occurrence": number,
                "start": start, "end": end, "natural_start": start, "natural_end": end,
                "source_start": portion[0], "source_end": portion[1],
                "text": item_text, "source_text": str((original or {}).get("text") or text).strip(),
                "language": str(segment.get("language") or language),
                "words": mapped,
            })
    return items


def caption_items(project: dict[str, Any], *, slot: str | None, offset: float = 0.0,
                  keeps: list[dict[str, Any]] | None = None, duration: float | None = None,
                  include_hidden: bool = True) -> list[dict[str, Any]]:
    """Automatic captions on the edit clock, with corrections and overrides applied."""
    original = (project.get("analysis") or {}).get("transcript") or {}
    originals = {segment_key(segment, index): segment
                 for index, segment in enumerate(original.get("segments") or []) if isinstance(segment, dict)}
    transcript, stale = effective_transcript(project)
    fixes = corrections(project)
    edits = overrides(project)
    items = _natural_items(transcript, _pieces(project, slot, offset, keeps), originals)
    for item in items:
        item["corrected"] = item["segment_id"] in fixes and item["segment_id"] not in stale
        edit = edits.get(item["id"]) or {}
        item["hidden"] = bool(edit.get("hidden"))
        for key in _STYLE_KEYS:
            item[key] = edit.get(key)
        text = edit.get("text")
        item["local_text"] = isinstance(text, str) and bool(text.strip())
        if item["local_text"]:
            words = _retext(item["words"], text.strip())
            item["text"], item["words"] = text.strip(), words or []
        start_delta, end_delta = _finite(edit.get("start_delta")), _finite(edit.get("end_delta"))
        item["timing_changed"] = bool(start_delta or end_delta)
        if item["timing_changed"]:
            start = max(0.0, item["natural_start"] + start_delta)
            end = item["natural_end"] + end_delta
            if duration is not None:
                end = min(float(duration), end)
            if end - start < MIN_CAPTION_SECONDS:
                end = start + MIN_CAPTION_SECONDS
            item["start"], item["end"] = start, end
            item["words"] = [{**word, "start": max(start, word["start"]), "end": min(end, word["end"])}
                             for word in item["words"] if start <= (word["start"] + word["end"]) / 2 < end]
        if duration is not None and item["end"] > duration:
            # The export ends on a whole frame; nothing is shown after it.
            item["end"] = max(item["start"], float(duration))
            item["words"] = [{**word, "end": min(item["end"], word["end"])}
                             for word in item["words"] if word["start"] < item["end"]]
        item["direction"] = "rtl" if _RTL.search(item["text"]) else "ltr"
        for key in ("start", "end", "natural_start", "natural_end", "source_start", "source_end"):
            item[key] = round(item[key], 6)
        for word in item["words"]:
            word["start"], word["end"] = round(word["start"], 6), round(word["end"], 6)
    items = [item for item in items if item["end"] > item["start"]]
    items.sort(key=lambda item: (item["start"], item["end"], item["id"]))
    return items if include_hidden else [item for item in items if not item["hidden"]]


def caption_lines(items: list[dict[str, Any]], words_per_caption: int, *,
                  default_style: str | None = None) -> list[dict[str, Any]]:
    """Split visible items into timed caption lines, as burned and SRT captions show them.

    Without trustworthy word timing an item is one line for its whole time. A
    moved item edge keeps the caption on screen until that edge. The social
    "highlight" style shows a few words at a time.
    """
    lines: list[dict[str, Any]] = []
    for item in items:
        if item.get("hidden"):
            continue
        style = {key: item.get(key) for key in _STYLE_KEYS}
        limit = max(1, int(words_per_caption))
        if (item.get("style") or default_style) == "highlight":
            limit = min(limit, HIGHLIGHT_WORDS_PER_CAPTION)
        words = item.get("words") or []
        if not words:
            lines.append({"start": item["start"], "end": item["end"], "text": item["text"], "words": [],
                          "item_id": item["id"], **style})
            continue
        chunks: list[list[dict[str, Any]]] = [[]]
        for word in words:
            if chunks[-1] and (word["start"] - chunks[-1][-1]["end"] > LINE_PAUSE_SECONDS or len(chunks[-1]) >= limit):
                chunks.append([])
            chunks[-1].append(word)
        chunks = [chunk for chunk in chunks if chunk]
        for number, chunk in enumerate(chunks):
            start, end = chunk[0]["start"], chunk[-1]["end"]
            if item.get("timing_changed"):
                if number == 0:
                    start = item["start"]
                if number == len(chunks) - 1:
                    end = item["end"]
            if end > start:
                lines.append({"start": start, "end": end, "text": " ".join(word["word"] for word in chunk),
                              "words": chunk, "item_id": item["id"], **style})
    lines.sort(key=lambda line: (line["start"], line["end"]))
    return lines


def _item(project: dict[str, Any], caption_id: Any, items: list[dict[str, Any]]) -> dict[str, Any]:
    target = str(caption_id or "")
    for item in items:
        if item["id"] == target:
            return item
    raise CaptionError("This caption is no longer on the timeline. Select it again.")


def prepare_caption_edit(project: dict[str, Any], payload: dict[str, Any],
                         items: list[dict[str, Any]], duration: float) -> dict[str, Any] | None:
    """Validate one caption action; return the new correction/override layers, or None if unchanged."""
    action = str(payload.get("action") or "")
    item = _item(project, payload.get("caption_id"), items)
    fixes = copy.deepcopy(corrections(project))
    edits = copy.deepcopy(overrides(project))
    edit = dict(edits.get(item["id"]) or {})
    if action == "caption_reset":
        edits.pop(item["id"], None)
    elif action == "caption_visibility":
        hidden = payload.get("hidden")
        if not isinstance(hidden, bool):
            raise CaptionError("hidden must be true or false")
        if hidden:
            edit["hidden"] = True
        else:
            edit.pop("hidden", None)
        edits[item["id"]] = edit
    elif action == "caption_update":
        if "text" in payload:
            text = payload.get("text")
            if not isinstance(text, str) or not text.strip():
                raise CaptionError("Caption text cannot be empty")
            text = text.strip()[:MAX_CAPTION_TEXT]
            scope = str(payload.get("scope") or "item")
            if scope not in CAPTION_SCOPES:
                raise CaptionError("scope must be item or source")
            if scope == "source":
                # A fix to what was said: every use of this speech shows it, and a
                # new AI draft keeps it. The original transcript is not modified.
                original = item["source_text"]
                if text == original:
                    fixes.pop(item["segment_id"], None)
                else:
                    fixes[item["segment_id"]] = {"original": original, "text": text}
                edit.pop("text", None)
            elif text == item["text"] and not item.get("local_text"):
                pass
            else:
                edit["text"] = text
        if "start" in payload or "end" in payload:
            start = _finite(payload.get("start", item["start"]), math.nan)
            end = _finite(payload.get("end", item["end"]), math.nan)
            if not (math.isfinite(start) and math.isfinite(end)):
                raise CaptionError("Caption times must be numbers")
            if start < 0 or end > duration + 1e-6 or end - start < MIN_CAPTION_SECONDS - 1e-9:
                raise CaptionError(f"A caption must be at least {MIN_CAPTION_SECONDS:g} s long and stay inside the timeline")
            start_delta, end_delta = round(start - item["natural_start"], 6), round(end - item["natural_end"], 6)
            for key, value in (("start_delta", start_delta), ("end_delta", end_delta)):
                if abs(value) < 1e-6:
                    edit.pop(key, None)
                else:
                    edit[key] = value
        for key, choices in (("style", CAPTION_STYLE_CHOICES), ("position", CAPTION_POSITION_CHOICES)):
            if key in payload:
                value = payload.get(key)
                if value is None or value == "":
                    edit.pop(key, None)
                elif value in choices:
                    edit[key] = value
                else:
                    raise CaptionError(f"Unknown caption {key}")
        if "scale" in payload:
            value = payload.get("scale")
            if value is None or value == "":
                edit.pop("scale", None)
            elif isinstance(value, int) and not isinstance(value, bool) and CAPTION_SCALE_RANGE[0] <= value <= CAPTION_SCALE_RANGE[1]:
                edit["scale"] = value
            else:
                raise CaptionError(f"Caption size must be {CAPTION_SCALE_RANGE[0]}-{CAPTION_SCALE_RANGE[1]}%")
        edits[item["id"]] = edit
    else:
        raise CaptionError("Unknown caption action")
    edits = {key: value for key, value in edits.items() if value}
    if fixes == corrections(project) and edits == overrides(project):
        return None
    return {"caption_corrections": fixes, "caption_overrides": edits}


def correct_segment_text(project: dict[str, Any], segment_id: Any, text: str) -> dict[str, dict[str, Any]] | None:
    """A source correction from the transcript list (every use of the segment)."""
    original = (project.get("analysis") or {}).get("transcript") or {}
    for index, segment in enumerate(original.get("segments") or []):
        if isinstance(segment, dict) and segment_key(segment, index) == str(segment_id):
            break
    else:
        raise CaptionError("Transcript segment was not found")
    fixes = copy.deepcopy(corrections(project))
    source = str(segment.get("text") or "").strip()
    current = str((fixes.get(str(segment_id)) or {}).get("text") or source).strip()
    if text == current:
        return None
    if text == source:
        fixes.pop(str(segment_id), None)
    else:
        fixes[str(segment_id)] = {"original": source, "text": text}
    return fixes
