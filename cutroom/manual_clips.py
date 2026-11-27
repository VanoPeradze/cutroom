"""Clip ranges the user marks by hand on the edited timeline, saved with the project.

Saving a range never cuts the timeline, moves the playhead or becomes a render
input. Each range keeps a fingerprint of what the finished edit showed inside
it when it was saved. If a later edit changes that content (a cut before it,
a trim inside it, new text or captions), the range is reported as ``changed``
and must be reviewed before export, instead of silently exporting another
moment.
"""
from __future__ import annotations

import math
import re
from typing import Any

from .cache_keys import stable_fingerprint
from .frame_rates import EXPORT_FPS_CHOICES, project_export_fps
from .sequence import materialize_sequence
from .source_tracks import SourceTrackError
from .utils import new_id

LIMIT = 200
NAME_LIMIT = 80
ID = re.compile(r"mclip_[a-f0-9]{12}\Z")
ROW_KEYS = frozenset(("id", "name", "start_frame", "end_frame", "fps", "fingerprint"))
FINGERPRINT_VERSION = "manual-clip-window-v1"
# Rounding to a microsecond keeps float noise from re-saves out of the identity.
PRECISION = 6


class ManualClipError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def clean_name(value: Any) -> str:
    if not isinstance(value, str):
        raise ManualClipError("A clip name must be text.")
    value = " ".join(value.split())
    if not value or len(value) > NAME_LIMIT or any(ord(c) < 32 for c in value):
        raise ManualClipError(f"Use 1–{NAME_LIMIT} characters for the clip name.")
    return value


def saved_rows(project: dict[str, Any]) -> list[dict[str, Any]]:
    registry = project.get("manual_clips", {"version": 1, "items": []})
    issue = "This saved clip list is not supported. It was left unchanged."
    if (not isinstance(registry, dict) or set(registry) != {"version", "items"}
            or type(registry.get("version")) is not int or registry["version"] != 1):
        raise ManualClipError(issue, 409)
    rows = registry["items"]
    if not isinstance(rows, list) or len(rows) > LIMIT:
        raise ManualClipError(issue, 409)
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or set(row) != ROW_KEYS
                or not isinstance(row["id"], str) or not ID.fullmatch(row["id"]) or row["id"] in seen
                or type(row["fps"]) is not int or row["fps"] not in EXPORT_FPS_CHOICES
                or type(row["start_frame"]) is not int or type(row["end_frame"]) is not int
                or not 0 <= row["start_frame"] < row["end_frame"] <= 1_000_000_000
                or not isinstance(row["fingerprint"], str) or not row["fingerprint"]):
            raise ManualClipError(issue, 409)
        try:
            if clean_name(row["name"]) != row["name"]:
                raise ManualClipError(issue, 409)
        except ManualClipError as error:
            raise ManualClipError(issue, 409) from error
        seen.add(row["id"])
    return rows


def _round(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, PRECISION) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _round(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_round(item) for item in value]
    return value


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _window_rows(rows: Any, start: float, end: float, *, speed_key: str | None = None) -> list[dict[str, Any]]:
    """Timed rows visible inside [start, end), expressed relative to ``start``.

    Only the visible part counts: trimming a clip outside the saved range does
    not change the range. Occurrence IDs are left out because splitting a clip
    in two renews an ID without changing what plays.
    """
    window = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        row_start, row_end = _number(row.get("start")), _number(row.get("end"))
        if row_start is None or row_end is None:
            continue
        left, right = max(start, row_start), min(end, row_end)
        if right <= left + 1e-9:
            continue
        piece = {key: value for key, value in row.items() if key not in {"id", "start", "end", "words", "origins"}}
        piece["start"], piece["end"] = left - start, right - start
        source = _number(row.get("source_start"))
        if source is not None:
            speed = _number(row.get(speed_key)) if speed_key else None
            piece["source_start"] = source + (left - row_start) * (speed if speed and speed > 0 else 1.0)
        window.append(piece)
    window.sort(key=lambda piece: (piece["start"], piece["end"], repr(sorted(piece.items()))))
    return _merge_continuous(window, speed_key)


def _merge_continuous(window: list[dict[str, Any]], speed_key: str | None) -> list[dict[str, Any]]:
    """Join back-to-back pieces that play on without a jump (a split clip plays the same)."""
    merged: list[dict[str, Any]] = []
    for piece in window:
        prev = merged[-1] if merged else None
        if prev is not None and abs(prev["end"] - piece["start"]) <= 1e-6:
            same = {k: v for k, v in prev.items() if k not in {"start", "end", "source_start"}} == \
                   {k: v for k, v in piece.items() if k not in {"start", "end", "source_start"}}
            if same and ("source_start" in prev) == ("source_start" in piece):
                if "source_start" not in prev:
                    prev["end"] = piece["end"]
                    continue
                speed = _number(prev.get(speed_key)) if speed_key else None
                expected = prev["source_start"] + (prev["end"] - prev["start"]) * (speed if speed and speed > 0 else 1.0)
                if abs(expected - piece["source_start"]) <= 1e-6:
                    prev["end"] = piece["end"]
                    continue
        merged.append(piece)
    return merged


def _timeline(project: dict[str, Any]) -> tuple[dict[str, Any], float]:
    if not isinstance(project.get("draft"), dict):
        raise ManualClipError("Open a saved edit before adding clips.", 409)
    try:
        return materialize_sequence(project)
    except (SourceTrackError, ValueError, KeyError, TypeError) as error:
        raise ManualClipError("The saved timeline is unavailable. Review the edit first.", 409) from error


def _captions(project: dict[str, Any]) -> list[dict[str, Any]]:
    # Imported lazily: the render module is large and only captions need it.
    from .render import project_caption_items
    try:
        rows = project_caption_items(project, aligned=False)
    except Exception:  # A caption problem must not hide the clip list.
        return []
    return [{key: row.get(key) for key in ("start", "end", "text", "hidden") if key in row}
            for row in rows if isinstance(row, dict)]


class WindowReader:
    """Read one project once, then fingerprint any number of edit-clock windows."""

    def __init__(self, project: dict[str, Any]):
        value, duration = _timeline(project)
        manual = value.get("manual") or {}
        self.duration = float(duration)
        self.tracks = manual.get("source_tracks") or {}
        self.camera_plan = (manual.get("sequence") or {}).get("camera_plan")
        self.media = manual.get("media_clips")
        self.text = manual.get("text_clips")
        self._caption_rows: list[dict[str, Any]] | None = None
        self._project = project

    @property
    def caption_rows(self) -> list[dict[str, Any]]:
        if self._caption_rows is None:
            self._caption_rows = _captions(self._project)
        return self._caption_rows

    def fingerprint(self, start: float, end: float) -> str:
        content = {
            "length": end - start,
            "tracks": {slot: _window_rows(self.tracks.get(slot), start, end, speed_key="video_speed")
                       for slot in sorted(self.tracks) if isinstance(self.tracks.get(slot), list)},
            "camera_plan": _window_rows(self.camera_plan, start, end),
            "media": _window_rows(self.media, start, end, speed_key="speed"),
            "text": _window_rows(self.text, start, end),
            "captions": _window_rows(self.caption_rows, start, end),
        }
        return stable_fingerprint(FINGERPRINT_VERSION, _round(content))


def _bounds(row: dict[str, Any]) -> tuple[float, float]:
    return row["start_frame"] / row["fps"], row["end_frame"] / row["fps"]


def clip_status(row: dict[str, Any], reader: WindowReader | None, fps: int) -> str:
    """``ready``, ``changed`` (content differs) or ``outside`` (past the edit's end)."""
    if reader is None:
        return "changed"
    start, end = _bounds(row)
    if end > reader.duration + 0.5 / fps:
        return "outside"
    return "ready" if reader.fingerprint(start, end) == row["fingerprint"] else "changed"


def public_view(project: dict[str, Any]) -> dict[str, Any] | None:
    """The saved list with a live status for each clip; fingerprints stay private."""
    try:
        rows = saved_rows(project)
    except ManualClipError:
        return {"version": 1, "items": [], "unavailable": True}
    if not rows:
        return {"version": 1, "items": []}
    try:
        reader = WindowReader(project)
    except ManualClipError:
        reader = None
    fps = project_export_fps(project)
    return {"version": 1, "items": [
        {**{key: row[key] for key in ("id", "name", "start_frame", "end_frame", "fps")},
         "status": clip_status(row, reader, fps)}
        for row in rows
    ]}


def _frames(project: dict[str, Any], data: dict[str, Any], reader: WindowReader) -> dict[str, int]:
    start, end, fps = data.get("start_frame"), data.get("end_frame"), data.get("fps")
    if type(fps) is not int or fps not in EXPORT_FPS_CHOICES or type(start) is not int or type(end) is not int:
        raise ManualClipError("Mark whole output frames at a supported frame rate.")
    if fps != project_export_fps(project):
        raise ManualClipError("The frame rate changed. Review the In and Out marks again.", 409)
    total = math.floor(reader.duration * fps + 0.5)
    if not 0 <= start < end <= total:
        raise ManualClipError("Mark an In and Out inside the edited timeline.")
    return {"start_frame": start, "end_frame": end, "fps": fps}


def apply_manual_clip(project: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    """Apply one explicit action. Returns the affected row (or the removed one)."""
    action = data.get("action")
    allowed = {"add": {"start_frame", "end_frame", "fps", "name"}, "rename": {"id", "name"},
               "remove": {"id"}, "accept": {"id"}}
    if not isinstance(action, str) or action not in allowed:
        raise ManualClipError("Use one explicit clip action.")
    required = {"action", "expected_revision", *allowed[action]}
    optional = {"name"} if action == "add" else set()
    if not required - optional <= set(data) <= required:
        raise ManualClipError("Use only the fields of this clip action.")
    rows = list(saved_rows(project))
    index = None
    if action != "add":
        key = data["id"]
        if not isinstance(key, str) or not ID.fullmatch(key):
            raise ManualClipError("Select a saved clip.")
        index = next((i for i, row in enumerate(rows) if row["id"] == key), None)
        if index is None:
            raise ManualClipError("This clip is no longer in the list.", 409)
    if action == "add":
        if len(rows) >= LIMIT:
            raise ManualClipError(f"This project already has {LIMIT} saved clips. Remove one to add another.", 409)
        reader = WindowReader(project)
        frames = _frames(project, data, reader)
        if any((row["start_frame"], row["end_frame"], row["fps"]) == (frames["start_frame"], frames["end_frame"], frames["fps"])
               for row in rows):
            raise ManualClipError("This range is already saved in Clips.", 409)
        name = clean_name(data["name"]) if "name" in data else f"Clip {len(rows) + 1}"
        start, end = frames["start_frame"] / frames["fps"], frames["end_frame"] / frames["fps"]
        row = {"id": new_id("mclip"), "name": name, **frames, "fingerprint": reader.fingerprint(start, end)}
        rows.append(row)
    elif action == "rename":
        name = clean_name(data["name"])
        if name == rows[index]["name"]:
            raise ManualClipError("The clip already has this name.", 409)
        row = rows[index] = {**rows[index], "name": name}
    elif action == "accept":
        # The user reviewed the changed range and keeps it as it is now.
        reader = WindowReader(project)
        row = rows[index]
        start, end = _bounds(row)
        if end > reader.duration + 0.5 / row["fps"]:
            raise ManualClipError("This range now ends after the edit. Mark it again on the timeline.", 409)
        row = rows[index] = {**row, "fingerprint": reader.fingerprint(start, end)}
    else:
        row = rows.pop(index)
    rows.sort(key=lambda item: (item["start_frame"] / item["fps"], item["end_frame"] / item["fps"], item["id"]))
    project["manual_clips"] = {"version": 1, "items": rows}
    return row


def require_exportable(project: dict[str, Any], clip_id: Any, export_range: dict[str, Any]) -> dict[str, Any]:
    """A saved clip may export only its own range, and only while its content is unchanged."""
    if not isinstance(clip_id, str) or not ID.fullmatch(clip_id):
        raise ManualClipError("Select a saved clip to export.")
    row = next((item for item in saved_rows(project) if item["id"] == clip_id), None)
    if row is None:
        raise ManualClipError("This clip is no longer in the list.", 409)
    if not isinstance(export_range, dict) or (row["start_frame"], row["end_frame"], row["fps"]) != (
            export_range.get("start_frame"), export_range.get("end_frame"), export_range.get("fps")):
        raise ManualClipError("The export range does not match the saved clip.", 409)
    reader = WindowReader(project)
    status = clip_status(row, reader, row["fps"])
    if status != "ready":
        raise ManualClipError("The edit changed inside this clip. Review it in Clips before exporting.", 409)
    return row
