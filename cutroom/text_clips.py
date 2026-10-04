"""User-authored text on the edited clock; no transcription service is involved."""
from __future__ import annotations

import copy
import html
import math
import re
import uuid
from typing import Any

from .sequence import editor_sequence_snapshot

MAX_TEXT_CLIPS = 2000
MAX_SIMULTANEOUS_TEXT_CLIPS = 16
MAX_TEXT_LENGTH = 1000
MAX_CAPTION_IMPORT_BYTES = 1024 * 1024
TEXT_ID_RE = re.compile(r"text_[0-9a-f]{32}\Z")
TEXT_FIELDS = {"kind", "start", "end", "text", "position", "scale", "style"}
TEXT_ACTION_FIELDS = {
    "text_add": set(TEXT_FIELDS),
    "text_update": {"clip_id", *TEXT_FIELDS},
    "text_remove": {"clip_id"},
    "text_split": {"clip_id", "time"},
    "text_import": {"format", "content", "replace"},
}


class TextClipError(ValueError):
    pass


def _number(value: Any, name: str, low: float, high: float) -> float:
    try:
        finite = math.isfinite(value)
    except (TypeError, OverflowError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise TextClipError(f"{name} must be a finite number")
    if not low <= value <= high:
        raise TextClipError(f"{name} must be between {low:g} and {high:g}")
    return round(float(value), 6)


def _duration(project: dict[str, Any]) -> float:
    snapshot = editor_sequence_snapshot(project)
    if not snapshot:
        raise TextClipError("Create a draft before adding text or captions")
    return float(snapshot["duration"])


def validate_text_clip(row: Any, duration: float) -> dict[str, Any]:
    if not isinstance(row, dict) or set(row) - {"id", *TEXT_FIELDS}:
        raise TextClipError("Invalid text clip fields")
    if not isinstance(row.get("id"), str) or not TEXT_ID_RE.fullmatch(row["id"]):
        raise TextClipError("Invalid text clip id")
    result = {"id": row["id"]}
    for key, options in {"kind": {"title", "caption"}, "position": {"top", "center", "bottom"}, "style": {"clean", "bold", "boxed"}}.items():
        if not isinstance(row.get(key), str) or row[key] not in options:
            raise TextClipError(f"Invalid text {key}")
        result[key] = row[key]
    result["start"] = _number(row.get("start"), "start", 0, duration)
    result["end"] = _number(row.get("end"), "end", 0, duration)
    if result["end"] - result["start"] < .08 - 1e-9:
        raise TextClipError("Text must last at least 0.08 seconds")
    scale = row.get("scale")
    if type(scale) is not int or not 75 <= scale <= 150:
        raise TextClipError("Text scale must be an integer between 75 and 150")
    result["scale"] = scale
    value = row.get("text")
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_TEXT_LENGTH:
        raise TextClipError(f"Text must contain 1 to {MAX_TEXT_LENGTH} characters")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    if any((ord(char) < 32 and char not in "\n\t") or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise TextClipError("Text contains unsupported control characters")
    result["text"] = value.strip()
    return result


def _new_clip(**fields: Any) -> dict[str, Any]:
    kind = fields.get("kind", "caption")
    return {"id": "text_" + uuid.uuid4().hex, "kind": kind, "position": "center" if kind == "title" else "bottom",
            "scale": 100, "style": "bold" if kind == "title" else "clean", **fields}


def _timestamp(value: str, format: str) -> float:
    expression = r"(\d{2,}):([0-5]\d):([0-5]\d),(\d{3})" if format == "srt" else r"(?:(\d{2,}):)?([0-5]\d):([0-5]\d)\.(\d{3})"
    match = re.fullmatch(expression, value)
    if not match:
        raise TextClipError(f"Invalid {format.upper()} timestamp")
    hours, minutes, seconds, millis = match.groups()
    # Bound oversized hour fields before integer conversion.
    if hours and len(hours) > 6:
        raise TextClipError("Caption timestamp is too large")
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000


def parse_caption_file(content: Any, format: Any, duration: float) -> list[dict[str, Any]]:
    """Parse the complete file before mutation; never silently drop broken cues."""
    if format not in ("srt", "vtt"):
        raise TextClipError("Choose an SRT or VTT caption file")
    if not isinstance(content, str):
        raise TextClipError("Caption file content must be text")
    try:
        size = len(content.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise TextClipError("Caption file must contain valid Unicode") from exc
    if size > MAX_CAPTION_IMPORT_BYTES:
        raise TextClipError("Caption files must be no larger than 1 MiB")
    source = content.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n[ \t]*\n", source)
    if format == "vtt":
        header = blocks.pop(0).splitlines()
        if not header or not re.fullmatch(r"WEBVTT(?:[ \t].*)?", header[0]) or any("-->" in line for line in header):
            raise TextClipError("VTT files must begin with a WEBVTT header and a blank line")
    clips = []
    for block in blocks:
        lines = block.splitlines()
        if format == "vtt" and lines and re.match(r"^(?:NOTE(?:[ \t]|$)|STYLE$|REGION$)", lines[0]):
            continue
        if not lines:
            continue
        if "-->" not in lines[0]:
            identifier = lines.pop(0)
            if format == "srt" and not identifier.isdigit():
                raise TextClipError("Each SRT cue must begin with its number or timing")
        if not lines:
            raise TextClipError("Caption cue is missing its timing")
        timing = re.fullmatch(r"\s*(\S+)\s+-->\s+(\S+)(?:[ \t]+(.*))?", lines.pop(0))
        if not timing or format == "srt" and timing.group(3):
            raise TextClipError("Invalid caption cue timing")
        if format == "vtt" and timing.group(3):
            # Position hints are valid VTT, but this editor imports text/timing
            # into its own finite, editable style presets.
            for setting in timing.group(3).split():
                if not re.fullmatch(r"(?:vertical|line|position|size|align|region):[^\s]+", setting):
                    raise TextClipError("Invalid VTT cue setting")
        if any("-->" in line for line in lines):
            raise TextClipError("Separate caption cues with a blank line")
        text = "\n".join(lines)
        # Formatting and voice tags are not imported as executable markup.
        markup = r"</?(?:b|i|u|s|font|ruby|rt|c(?:\.[^ >]+)*|v|lang)(?:\s+[^>]*)?>|<(?:\d{2}:)?\d{2}:\d{2}\.\d{3}>"
        text = html.unescape(re.sub(markup, "", text, flags=re.IGNORECASE))
        clip = _new_clip(kind="caption", start=_timestamp(timing.group(1), format), end=_timestamp(timing.group(2), format), text=text)
        clips.append(validate_text_clip(clip, duration))
        if len(clips) > MAX_TEXT_CLIPS:
            raise TextClipError(f"A caption file can contain at most {MAX_TEXT_CLIPS} cues")
    if not clips:
        raise TextClipError("The caption file contains no usable cues")
    return clips


def prepare_text_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    action = payload["action"]
    if set(payload) - {"action", "expected_revision", *TEXT_ACTION_FIELDS[action]}:
        raise TextClipError("Unknown text edit field")
    duration = _duration(project)
    original = (project.get("manual") or {}).get("text_clips") or []
    clips = copy.deepcopy(original)
    if action == "text_add":
        missing = {"kind", "start", "end", "text"} - payload.keys()
        if missing:
            raise TextClipError(f"Required text field: {sorted(missing)[0]}")
        clips.append(validate_text_clip(_new_clip(**{key: payload[key] for key in TEXT_FIELDS if key in payload}), duration))
    elif action == "text_import":
        replace = payload.get("replace", False)
        if not isinstance(replace, bool):
            raise TextClipError("replace must be true or false")
        imported = parse_caption_file(payload.get("content"), payload.get("format"), duration)
        clips = [row for row in clips if row.get("kind") != "caption"] if replace else clips
        clips.extend(imported)
    else:
        selected = next((row for row in clips if row.get("id") == payload.get("clip_id")), None)
        if selected is None:
            raise TextClipError("The selected text clip no longer exists")
        index = clips.index(selected)
        if action == "text_remove":
            clips.pop(index)
        elif action == "text_update":
            clips[index] = validate_text_clip({**selected, **{key: payload[key] for key in TEXT_FIELDS if key in payload}}, duration)
        elif action == "text_split":
            time = _number(payload.get("time"), "time", selected["start"] + .08, selected["end"] - .08)
            clips[index:index + 1] = [validate_text_clip({**selected, "end": time}, duration), validate_text_clip({**selected, "id": "text_" + uuid.uuid4().hex, "start": time}, duration)]
    if len(clips) > MAX_TEXT_CLIPS:
        raise TextClipError(f"A project can contain at most {MAX_TEXT_CLIPS} text clips")
    _validate_overlaps(clips)
    return None if clips == original else {"text_clips": clips}


def _validate_overlaps(clips: list[dict[str, Any]]) -> None:
    active = 0
    for _, delta in sorted((row[key], delta) for row in clips for key, delta in (("start", 1), ("end", -1))):
        active += delta
        if active > MAX_SIMULTANEOUS_TEXT_CLIPS:
            raise TextClipError(f"At most {MAX_SIMULTANEOUS_TEXT_CLIPS} text clips can appear at the same time")


def validated_text_clips(project: dict[str, Any]) -> list[dict[str, Any]]:
    clips = (project.get("manual") or {}).get("text_clips") or []
    if not isinstance(clips, list) or len(clips) > MAX_TEXT_CLIPS:
        raise TextClipError("Invalid saved text clips")
    if not clips:
        return []
    duration = _duration(project)
    result = [validate_text_clip(row, duration) for row in clips]
    if len({row["id"] for row in result}) != len(result):
        raise TextClipError("Saved text clips contain duplicate identifiers")
    _validate_overlaps(result)
    return result


def validate_text_bounds(project: dict[str, Any]) -> None:
    clips = (project.get("manual") or {}).get("text_clips") or []
    if not clips:
        return
    duration = _duration(project)
    if any(row["end"] > duration + 1e-8 for row in clips):
        raise TextClipError("This edit would shorten the timeline past text or captions. Trim, move, or remove those text clips first.")


def public_text_clips(value: Any) -> list[dict[str, Any]]:
    """Expose only the finite editor contract, never extra saved metadata."""
    if not isinstance(value, list):
        return []
    return [{key: row[key] for key in ("id", *sorted(TEXT_FIELDS)) if key in row}
            for row in value[:MAX_TEXT_CLIPS] if isinstance(row, dict)]
