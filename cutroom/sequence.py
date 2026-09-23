"""Versioned edit-clock clips, projected lazily from legacy source-clock drafts."""
from __future__ import annotations

import copy
from typing import Any

from .source_tracks import (
    EPSILON, MAX_SEQUENCE_SECONDS, SourceTrackError, _duration, _finite, _new_id,
    _number, _validated, _shift_video_start, has_sequence, minimum_clip_seconds,
    source_track_clips, timeline_duration,
)

SEQUENCE_ACTION_FIELDS = {
    "sequence_split": {"slot", "time"},
    "sequence_remove_range": {"slot", "start", "end"},
    "sequence_trim": {"slot", "clip_id", "start", "end", "source_start"},
    "sequence_place": {"slot", "clip_id", "start"},
    "sequence_move": {"slot", "clip_id", "start", "mode"},
    "sequence_duplicate": {"slot", "clip_id", "start"},
    "sequence_insert": {"slot", "start", "source_start", "source_end"},
    "sequence_ripple_delete": {"start", "end"},
    "sequence_split_all": {"time"},
    "sequence_move_range": {"start", "end", "to", "mode", "slot"},
    "sequence_duplicate_range": {"start", "end", "to"},
    "sequence_insert_linked": {"slot", "start", "source_start", "source_end"},
    "sequence_layout": {"start", "end", "layout"},
    "sequence_crop": {"slot", "start", "end", "x", "y", "zoom"},
    "sequence_speed": {"slot", "clip_id", "speed"},
    "sequence_source_restore": {"slot", "source_start", "source_end", "scope"},
    "sequence_source_remove": {"slot", "source_start", "source_end", "scope"},
    "sequence_close_gaps": {"slot"},
    "sequence_trim_edge": {"start", "end", "edge", "time", "slot"},
    "sequence_reset": set(),
}
SEQUENCE_ACTIONS = frozenset(SEQUENCE_ACTION_FIELDS)
SEQUENCE_LAYOUTS = {"A", "B", "screen", "camera", "stacked", "side_by_side", "pip", "embedded_stack"}


def _legacy_keeps(project: dict[str, Any]) -> list[tuple[float, float]]:
    draft = project.get("draft") or {}
    duration = _duration(project, "A")
    raw = draft.get("keep_ranges") if "keep_ranges" in draft else draft.get("camera_plan")
    if raw is None:
        raw = [{"start": 0, "end": duration}]
    clips = sorted((max(0.0, _finite(row.get("start"))), min(duration, _finite(row.get("end"))))
                   for row in raw if isinstance(row, dict)) if isinstance(raw, list) else []
    result = []
    cursor = 0.0
    for start, end in clips:
        start = max(cursor, start)
        if end > start + EPSILON:
            result.append((start, end))
            cursor = end
    return result


def materialize_sequence(project: dict[str, Any]) -> tuple[dict[str, Any], float]:
    """Return a detached sequence project and its edit duration; never save it.

    Deterministic virtual IDs are the API's stable selection contract. The
    expected project revision protects them if the underlying draft changes.
    Physical source metadata, original draft ranges, and transcript stay intact.
    """
    if not isinstance(project.get("draft"), dict):
        raise SourceTrackError("Generate a draft before editing clips")
    value = copy.deepcopy(project)
    if has_sequence(value):
        sequence = value["manual"]["sequence"]
        duration = _number(sequence.get("duration"), "sequence duration")
        if duration < 0 or duration > MAX_SEQUENCE_SECONDS:
            raise SourceTrackError("The edit timeline must be between zero and 24 hours")
        tracks = value["manual"].get("source_tracks")
        if not isinstance(tracks, dict) or not isinstance(sequence.get("camera_plan"), list):
            raise SourceTrackError("Sequence data is invalid; reset the sequence to recover the draft")
        for slot in ("A", "B"):
            tracks[slot] = _validated(value, slot, tracks.get(slot, []))
        return value, duration
    keeps = _legacy_keeps(value)
    duration = round(sum(end - start for start, end in keeps), 9)
    if duration <= 0 or duration > MAX_SEQUENCE_SECONDS:
        raise SourceTrackError("The draft must contain a valid edit shorter than 24 hours")
    slots = {slot: source_track_clips(value, slot) for slot in ("A", "B")}
    draft = value["draft"]
    camera_rows = sorted((row for row in draft.get("camera_plan") or [] if isinstance(row, dict)),
                         key=lambda row: (_finite(row.get("start")), _finite(row.get("end"))))
    edges = [_finite(edge, -1) for edge in draft.get("edit_points") or []]
    edges += [_finite(row.get(edge), -1) for row in camera_rows for edge in ("start", "end")]
    edges += [clip[edge] for clips in slots.values() for clip in clips for edge in ("start", "end")]
    tracks: dict[str, list[dict[str, Any]]] = {"A": [], "B": []}
    cameras = []
    cursor = 0.0
    for keep_index, (start, end) in enumerate(keeps):
        boundaries = sorted({start, end, *(point for point in edges if start + EPSILON < point < end - EPSILON)})
        for piece_index, (left, right) in enumerate(zip(boundaries, boundaries[1:])):
            midpoint = (left + right) / 2
            edit_start, edit_end = round(cursor + left - start, 9), round(cursor + right - start, 9)
            for slot, clips in slots.items():
                clip = next((clip for clip in clips if clip["start"] <= midpoint < clip["end"]), None)
                if clip is not None:
                    tracks[slot].append({
                        **clip, **_shift_video_start(clip, left - clip["start"]),
                        "id": f"{slot}:sequence:{keep_index}:{piece_index}",
                        "start": edit_start, "end": edit_end,
                        "source_start": round(clip["source_start"] + left - clip["start"], 9),
                    })
            camera = next((str(row.get("camera") or "A") for row in reversed(camera_rows)
                           if _finite(row.get("start")) <= midpoint < _finite(row.get("end"))), "A")
            camera = camera if camera in SEQUENCE_LAYOUTS else "A"
            cameras.append({"start": edit_start, "end": edit_end, "camera": camera})
        cursor += end - start
    manual = value.setdefault("manual", {})
    manual["sequence"] = {
        "version": 1, "duration": duration, "camera_plan": cameras,
        "base_source_tracks": copy.deepcopy(manual.get("source_tracks")),
    }
    manual["source_tracks"] = tracks
    for slot in ("A", "B"):
        tracks[slot] = _validated(value, slot, tracks[slot])
    return value, duration


def editor_sequence_snapshot(project: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(project.get("draft"), dict):
        return None
    value, duration = materialize_sequence(project)
    sequence = value["manual"]["sequence"]
    # Internal reset provenance does not belong in the UI projection.
    return {
        "active": has_sequence(project), "duration": duration,
        "sequence": {key: copy.deepcopy(sequence[key]) for key in ("version", "duration", "camera_plan")},
        "source_tracks": copy.deepcopy(value["manual"]["source_tracks"]),
    }


def _validate_range(project: dict[str, Any], payload: dict[str, Any]) -> tuple[float, float]:
    start, end = _number(payload.get("start"), "start"), _number(payload.get("end"), "end")
    if start < 0 or end > timeline_duration(project) + EPSILON:
        raise SourceTrackError("Choose a range inside the edit timeline")
    if end - start < minimum_clip_seconds(project) - EPSILON:
        raise SourceTrackError("Select at least one output frame")
    return start, min(end, timeline_duration(project))


def _automatic_layout(project: dict[str, Any]) -> str:
    """Auto inherits current routing, not stale source-clock AI timestamps.

    Once clips are rearranged, their edit-clock ranges no longer identify the
    original Storyline intervals. An explicit mixer default is authoritative;
    otherwise show the primary semantic role (or the sole source).
    """
    if not (project.get("sources") or {}).get("B"):
        draft = project.get("draft") or {}
        embedded = draft.get("layout") == "embedded_stack" or any(
            isinstance(row, dict) and row.get("camera") == "embedded_stack"
            for row in draft.get("camera_plan") or []
        )
        return "embedded_stack" if embedded else "A"
    mixer = (project.get("manual") or {}).get("source_mixer") or {}
    default = str(mixer.get("default_layout") or "auto")
    if default in SEQUENCE_LAYOUTS - {"embedded_stack"}:
        return default
    return "camera" if mixer.get("primary_role") == "camera" else "screen"


def _insert_at(clips: list[dict[str, Any]], moving: dict[str, Any], slot: str) -> list[dict[str, Any]]:
    """Insert at a final edit-clock position; split/ripple this lane only."""
    start, duration = moving["start"], moving["end"] - moving["start"]
    updated = []
    for clip in clips:
        if clip["end"] <= start:
            updated.append(clip)
        elif clip["start"] >= start:
            updated.append({**clip, "start": clip["start"] + duration, "end": clip["end"] + duration})
        else:
            updated.append({**clip, "end": start})
            updated.append({**clip, **_shift_video_start(clip, start - clip["start"]), "id": _new_id(slot), "start": start + duration,
                            "end": clip["end"] + duration,
                            "source_start": clip["source_start"] + start - clip["start"]})
    return [*updated, moving]


def _slice_rows(rows: list[dict[str, Any]], start: float, end: float, *,
                at: float = 0.0, slot: str | None = None,
                duplicate: bool = False) -> list[dict[str, Any]]:
    """Copy a time window into a new position without losing local-media time.

    Keeping a clip's leftmost piece preserves its selection ID. Other pieces
    receive distinct IDs, including every copied clip in a duplicate operation.
    Positive sub-frame fragments are retained for validation, never discarded.
    """
    result = []
    for row in rows:
        left, right = max(start, row["start"]), min(end, row["end"])
        if right <= left + EPSILON:
            continue
        piece = {**row, "start": round(at + left - start, 9), "end": round(at + right - start, 9)}
        if slot is not None:
            piece.update(_shift_video_start(row, left - row["start"]))
            piece["source_start"] = round(row["source_start"] + left - row["start"], 9)
            if duplicate or left > row["start"] + EPSILON:
                piece["id"] = _new_id(slot)
        result.append(piece)
    return result


def _time_block(manual: dict[str, Any], start: float, end: float, *, duplicate: bool = False) -> dict[str, Any]:
    return {
        "duration": round(end - start, 9),
        "source_tracks": {slot: _slice_rows(manual["source_tracks"][slot], start, end, slot=slot, duplicate=duplicate)
                          for slot in ("A", "B")},
        "camera_plan": _slice_rows(manual["sequence"]["camera_plan"], start, end),
    }


def _without_time(rows: list[dict[str, Any]], start: float, end: float, *,
                  slot: str | None = None) -> list[dict[str, Any]]:
    """Lift a region without moving any surviving footage on the timeline."""
    limit = max([end, *(row["end"] for row in rows)])
    return [*_slice_rows(rows, 0, start, slot=slot),
            *_slice_rows(rows, end, limit, at=end, slot=slot)]


def _overwrite_time(manual: dict[str, Any], start: float, end: float, at: float, slot: str | None = None) -> None:
    """Move only the selected block; overwrite its destination, never ripple."""
    block = _time_block(manual, start, end)
    length = end - start
    sequence = manual["sequence"]
    duration = sequence["duration"]
    if at + length > MAX_SEQUENCE_SECONDS:
        raise SourceTrackError("The edit timeline cannot exceed 24 hours")
    for track_slot in ((slot,) if slot else ("A", "B")):
        remaining = _without_time(manual["source_tracks"][track_slot], start, end, slot=track_slot)
        remaining = _without_time(remaining, at, at + length, slot=track_slot)
        manual["source_tracks"][track_slot] = [*remaining,
            *_slice_rows(block["source_tracks"][track_slot], 0, length, at=at, slot=track_slot)]
    if slot:
        return  # _finish extends the edit and its default layout when needed.
    cameras = _without_time(sequence["camera_plan"], at, at + length)
    if at > duration + EPSILON:
        camera = str((sequence["camera_plan"] or [{}])[-1].get("camera") or "A")
        cameras.append({"start": duration, "end": at, "camera": camera})
    cameras.extend(_slice_rows(block["camera_plan"], 0, length, at=at))
    sequence["camera_plan"] = sorted(cameras, key=lambda row: row["start"])
    sequence["duration"] = round(max(duration, at + length), 9)


def _remove_time(manual: dict[str, Any], start: float, end: float) -> None:
    sequence = manual["sequence"]
    duration = sequence["duration"]
    for slot in ("A", "B"):
        rows = manual["source_tracks"][slot]
        manual["source_tracks"][slot] = [*_slice_rows(rows, 0, start, slot=slot),
                                          *_slice_rows(rows, end, duration, at=start, slot=slot)]
    rows = sequence["camera_plan"]
    sequence["camera_plan"] = [*_slice_rows(rows, 0, start), *_slice_rows(rows, end, duration, at=start)]
    sequence["duration"] = round(duration - (end - start), 9)


def _insert_time(manual: dict[str, Any], block: dict[str, Any], at: float) -> None:
    """Insert a whole time block, rippling both tracks and their layout together."""
    sequence = manual["sequence"]
    duration, length = sequence["duration"], block["duration"]
    new_duration = round(max(duration, at) + length, 9)
    if new_duration > MAX_SEQUENCE_SECONDS:
        raise SourceTrackError("The edit timeline cannot exceed 24 hours")
    for slot in ("A", "B"):
        rows = manual["source_tracks"][slot]
        manual["source_tracks"][slot] = [
            *_slice_rows(rows, 0, min(at, duration), slot=slot),
            *_slice_rows(block["source_tracks"][slot], 0, length, at=at, slot=slot),
            *_slice_rows(rows, at, duration, at=at + length, slot=slot),
        ]
    rows = sequence["camera_plan"]
    gap = []
    if at > duration + EPSILON:
        camera = str((rows or [{}])[-1].get("camera") or "A")
        gap = [{"start": duration, "end": at, "camera": camera}]
    sequence["camera_plan"] = [*_slice_rows(rows, 0, min(at, duration)), *gap,
                               *_slice_rows(block["camera_plan"], 0, length, at=at),
                               *_slice_rows(rows, at, duration, at=at + length)]
    sequence["duration"] = new_duration


def _placement_time(payload: dict[str, Any], key: str = "to") -> float:
    time = _number(payload.get(key), key)
    if time < 0 or time > MAX_SEQUENCE_SECONDS:
        raise SourceTrackError("Place clips between zero and 24 hours")
    return time


def _close_sequence_gaps(value: dict[str, Any], slot: str | None = None) -> dict[str, Any] | None:
    """Close only empty time in the requested scope, in one undoable action."""
    manual, duration = value["manual"], timeline_duration(value)
    clips = manual["source_tracks"][slot] if slot else [clip for rows in manual["source_tracks"].values() for clip in rows]
    gaps, cursor = [], 0.0
    for clip in sorted(clips, key=lambda row: row["start"]):
        if clip["start"] > cursor + EPSILON:
            gaps.append((cursor, clip["start"]))
        cursor = max(cursor, clip["end"])
    if cursor < duration - EPSILON:
        gaps.append((cursor, duration))
    if not gaps:
        return None
    before = copy.deepcopy(manual)
    for start, end in reversed(gaps):
        if slot:
            rows = manual["source_tracks"][slot]
            manual["source_tracks"][slot] = [*_slice_rows(rows, 0, start, slot=slot),
                *_slice_rows(rows, end, duration, at=start, slot=slot)]
        else:
            _remove_time(manual, start, end)
    if slot:
        # Do not shorten another recording. Only genuinely empty output tail
        # can go; its layout rows must shrink with the sequence duration.
        end = max([0.0, *(c["end"] for rows in manual["source_tracks"].values() for c in rows)])
        manual["sequence"]["duration"] = round(end, 9)
        manual["sequence"]["camera_plan"] = _slice_rows(manual["sequence"]["camera_plan"], 0, end)
    _finish(value)
    return manual if manual != before else None


def _ripple_move(value: dict[str, Any], start: float, end: float, at: float, slot: str | None = None) -> dict[str, Any] | None:
    """Lift and insert, closing the origin and pushing destination footage.

    Unlike legacy insert/overwrite, a drop beyond the end is clamped: dragging
    cannot create a new black tail. Existing intentional gaps remain explicit.
    """
    manual, duration = value["manual"], timeline_duration(value)
    length = end - start
    if slot:
        rows = manual["source_tracks"][slot]
        block = _slice_rows(rows, start, end, slot=slot)
        if not block:
            return None
        remaining = [*_slice_rows(rows, 0, start, slot=slot), *_slice_rows(rows, end, duration, at=start, slot=slot)]
        at = min(at, max([0.0, *(row["end"] for row in remaining)]))
        if abs(at - start) <= EPSILON:
            return None
        manual["source_tracks"][slot] = [*_slice_rows(remaining, 0, at, slot=slot),
            *_slice_rows(block, 0, length, at=at, slot=slot),
            *_slice_rows(remaining, at, duration, at=at + length, slot=slot)]
    else:
        at = min(at, max(0.0, duration - length))
        if abs(at - start) <= EPSILON:
            return None
        block = _time_block(manual, start, end)
        if not any(block["source_tracks"].values()):
            return None
        _remove_time(manual, start, end)
        _insert_time(manual, block, at)
    _finish(value)
    return manual


def _trim_sequence_edge(value: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    start, end = _validate_range(value, payload)
    edge, slot = payload.get("edge"), payload.get("slot")
    if edge not in ("start", "end"):
        raise SourceTrackError("Choose the start or end edge")
    if "slot" in payload and (not isinstance(slot, str) or slot not in {"A", "B"} or _duration(value, slot) <= 0):
        raise SourceTrackError("Choose an existing source track A or B")
    time = _placement_time(payload, "time")
    boundary = start if edge == "start" else end
    if abs(time - boundary) <= EPSILON:
        return None
    new_start, new_end = (time, end) if edge == "start" else (start, time)
    if new_end - new_start < minimum_clip_seconds(value) - EPSILON:
        raise SourceTrackError("Keep at least one output frame")
    manual = value["manual"]
    slots = (slot,) if slot else ("A", "B")
    if not any(c["start"] < end and c["end"] > start for s in slots for c in manual["source_tracks"][s]):
        raise SourceTrackError("Select a clip before dragging its edge")
    shortening = time > start if edge == "start" else time < end
    if shortening:
        left, right = (start, time) if edge == "start" else (time, end)
        if slot:
            manual["source_tracks"][slot] = _without_time(manual["source_tracks"][slot], left, right, slot=slot)
        else:
            _remove_time(manual, left, right)
    else:
        left, right = (time, start) if edge == "start" else (end, time)
        extended = False
        for s in slots:
            rows = manual["source_tracks"][s]
            if any(c["start"] < right - EPSILON and c["end"] > left + EPSILON for c in rows):
                raise SourceTrackError("The next clip blocks this edge. Choose one source to adjust it independently.")
            for clip in rows:
                if abs(clip[edge] - boundary) > EPSILON:
                    continue
                if edge == "start":
                    clip.update(_shift_video_start(clip, time - start))
                    clip["source_start"] += time - start
                    clip["start"] = time
                else:
                    clip["end"] = time
                extended = True
        if not extended:
            raise SourceTrackError("No source footage touches this edge")
        if not slot:
            cameras = manual["sequence"]["camera_plan"]
            midpoint = start + EPSILON if edge == "start" else end - EPSILON
            camera = next((r["camera"] for r in cameras if r["start"] <= midpoint < r["end"]), _automatic_layout(value))
            manual["sequence"]["camera_plan"] = sorted([*_without_time(cameras, left, right),
                {"start": left, "end": right, "camera": camera}], key=lambda r: r["start"])
            manual["sequence"]["duration"] = max(timeline_duration(value), new_end)
    _finish(value)  # Checks media bounds and preserves each clip's own framing.
    return manual


def _prepare_linked_edit(value: dict[str, Any], payload: dict[str, Any], action: str) -> dict[str, Any] | None:
    manual, duration = value["manual"], timeline_duration(value)
    if action == "sequence_split_all":
        time = _number(payload.get("time"), "time")
        if time < 0 or time > duration + EPSILON:
            raise SourceTrackError("Choose a split inside the edit timeline")
        changed = False
        for slot in ("A", "B"):
            clips = manual["source_tracks"][slot]
            if any(clip["start"] + EPSILON < time < clip["end"] - EPSILON for clip in clips):
                manual["source_tracks"][slot] = [*_slice_rows(clips, 0, time, slot=slot),
                                                  *_slice_rows(clips, time, duration, at=time, slot=slot)]
                changed = True
        if not changed:
            return None
    elif action == "sequence_insert_linked":
        slot = str(payload.get("slot") or "").upper()
        if slot not in {"A", "B"} or _duration(value, slot) <= 0:
            raise SourceTrackError("Choose an existing source track A or B")
        start, end = _number(payload.get("source_start"), "source_start"), _number(payload.get("source_end"), "source_end")
        if start < 0 or end > _duration(value, slot) + EPSILON:
            raise SourceTrackError(f"The clip extends beyond source {slot}'s media")
        if end - start < minimum_clip_seconds(value) - EPSILON:
            raise SourceTrackError("Select at least one output frame")
        length = round(end - start, 9)
        block = {"duration": length, "source_tracks": {"A": [], "B": []},
                 "camera_plan": [{"start": 0, "end": length, "camera": slot}]}
        block["source_tracks"][slot] = [{"id": _new_id(slot), "start": 0, "end": length, "source_start": start}]
        _insert_time(manual, block, _placement_time(payload, "start"))
    else:
        start, end = _validate_range(value, payload)
        if action == "sequence_ripple_delete":
            _remove_time(manual, start, end)
        else:
            at = _placement_time(payload)
            if action == "sequence_move_range" and payload.get("mode") == "ripple":
                return _ripple_move(value, start, end, at, payload.get("slot"))
            if action == "sequence_move_range" and abs(at - start) <= EPSILON:
                return None
            if action == "sequence_move_range" and payload.get("mode") == "overwrite":
                _overwrite_time(manual, start, end, at, payload.get("slot"))
                _finish(value)
                return manual
            block = _time_block(manual, start, end, duplicate=action == "sequence_duplicate_range")
            if action == "sequence_move_range":
                _remove_time(manual, start, end)
            _insert_time(manual, block, at)
    _finish(value)
    return manual


def _finish(value: dict[str, Any]) -> None:
    manual = value["manual"]
    sequence = manual["sequence"]
    duration = max([timeline_duration(value), *(clip["end"] for clips in manual["source_tracks"].values() for clip in clips)])
    if duration > MAX_SEQUENCE_SECONDS:
        raise SourceTrackError("The edit timeline cannot exceed 24 hours")
    old_duration = timeline_duration(value)
    sequence["duration"] = round(duration, 9)
    for slot in ("A", "B"):
        manual["source_tracks"][slot] = _validated(value, slot, manual["source_tracks"].get(slot, []))
    if duration > old_duration + EPSILON:
        camera = str((sequence.get("camera_plan") or [{}])[-1].get("camera") or "A")
        sequence.setdefault("camera_plan", []).append({"start": old_duration, "end": duration, "camera": camera})


def prepare_sequence_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return staged manual state, or None for a no-op; mutations are atomic."""
    action = str(payload.get("action") or "").strip().lower()
    if action not in SEQUENCE_ACTIONS:
        raise SourceTrackError("Unknown sequence edit action")
    if action in {"sequence_move", "sequence_move_range"} and payload.get("mode", "insert") not in {"insert", "overwrite", "ripple"}:
        raise SourceTrackError("Choose insert, overwrite or ripple move mode")
    if action == "sequence_move_range" and "slot" in payload:
        if payload["slot"] not in {"A", "B"} or _duration(project, payload["slot"]) <= 0:
            raise SourceTrackError("Choose an existing source track A or B")
        if payload.get("mode") not in {"overwrite", "ripple"}:
            raise SourceTrackError("Independent range moves require overwrite or ripple mode")
    if action == "sequence_reset":
        if not has_sequence(project):
            return None
        manual = copy.deepcopy(project.get("manual") or {})
        original_tracks = manual.pop("sequence").get("base_source_tracks")
        if isinstance(original_tracks, dict):
            manual["source_tracks"] = original_tracks
        else:
            manual.pop("source_tracks", None)
        return manual
    value, duration = materialize_sequence(project)
    manual = value["manual"]
    initial_tracks = copy.deepcopy(manual["source_tracks"])
    if action == "sequence_trim_edge":
        return _trim_sequence_edge(value, payload)
    if action == "sequence_close_gaps":
        slot = payload.get("slot")
        if "slot" in payload and (not isinstance(slot, str) or slot not in {"A", "B"} or _duration(value, slot) <= 0):
            raise SourceTrackError("Choose an existing source track A or B")
        return _close_sequence_gaps(value, slot)
    if action in {"sequence_source_restore", "sequence_source_remove"}:
        from .source_review import prepare_source_review
        return prepare_source_review(value, payload)
    if action in {"sequence_ripple_delete", "sequence_split_all", "sequence_move_range", "sequence_duplicate_range", "sequence_insert_linked"}:
        return _prepare_linked_edit(value, payload, action)
    if action == "sequence_layout":
        start, end = _validate_range(value, payload)
        camera = str(payload.get("layout") or "").strip()
        if camera == "auto":
            camera = _automatic_layout(value)
        if camera not in SEQUENCE_LAYOUTS:
            raise SourceTrackError("Unknown source layout")
        if camera in {"B", "camera", "stacked", "side_by_side", "pip"} and not (project.get("sources") or {}).get("B"):
            raise SourceTrackError("Add a second source before using this layout")
        updated = []
        for row in manual["sequence"].get("camera_plan") or []:
            if row["end"] <= start or row["start"] >= end:
                updated.append(row)
            else:
                if row["start"] < start:
                    updated.append({**row, "end": start})
                if row["end"] > end:
                    updated.append({**row, "start": end})
        updated.append({"start": start, "end": end, "camera": camera})
        manual["sequence"]["camera_plan"] = sorted(updated, key=lambda row: (row["start"], row["end"]))
        return manual
    slot = str(payload.get("slot") or "").upper()
    if slot not in {"A", "B"} or _duration(project, slot) <= 0:
        raise SourceTrackError("Choose an existing source track A or B")
    clips = _validated(value, slot, manual["source_tracks"][slot])
    if action == "sequence_move" and payload.get("mode") == "ripple":
        clip = next((clip for clip in clips if clip["id"] == payload.get("clip_id")), None)
        if clip is None:
            raise SourceTrackError("The clip changed; select it again")
        return _ripple_move(value, clip["start"], clip["end"], _placement_time(payload, "start"), slot)
    if action == "sequence_speed":
        speed = _number(payload.get("speed"), "speed")
        if not 0.25 <= speed <= 4:
            raise SourceTrackError("Picture speed must be between 0.25 and 4")
        clip = next((clip for clip in clips if clip["id"] == payload.get("clip_id")), None)
        if clip is None:
            raise SourceTrackError("The clip changed; select it again")
        clip.update(video_speed=speed, video_source_start=clip.get("video_source_start", clip["source_start"]))
    elif action == "sequence_crop":
        start, end = _validate_range(value, payload)
        crop = {key: _number(payload.get(key), key) for key in ("x", "y", "zoom")}
        selected = _slice_rows(clips, start, end, at=start, slot=slot)
        if not selected:
            raise SourceTrackError("Select footage in this source before changing its framing")
        for clip in selected:
            clip["crop"] = crop
        clips = [*_slice_rows(clips, 0, start, slot=slot), *selected,
                 *_slice_rows(clips, end, duration, at=end, slot=slot)]
    elif action == "sequence_split":
        time = _number(payload.get("time"), "time")
        if any(abs(time - clip[edge]) <= EPSILON for clip in clips for edge in ("start", "end")):
            return None
        clip = next((clip for clip in clips if clip["start"] < time < clip["end"]), None)
        if clip is None:
            raise SourceTrackError("There is no source clip at the playhead")
        right = {**clip, **_shift_video_start(clip, time - clip["start"]), "id": _new_id(slot), "start": time, "source_start": clip["source_start"] + time - clip["start"]}
        clip["end"] = time
        clips.append(right)
    elif action == "sequence_remove_range":
        start, end = _validate_range(value, payload)
        updated = []
        for clip in clips:
            if clip["end"] <= start or clip["start"] >= end:
                updated.append(clip)
                continue
            if clip["start"] < start:
                updated.append({**clip, "end": start})
            if clip["end"] > end:
                updated.append({**clip, **_shift_video_start(clip, end - clip["start"]), "id": _new_id(slot) if clip["start"] < start else clip["id"], "start": end,
                                "source_start": clip["source_start"] + end - clip["start"]})
        clips = updated
    else:
        if action == "sequence_insert":
            source_start = _number(payload.get("source_start"), "source_start")
            source_end = _number(payload.get("source_end"), "source_end")
            clip = {"id": _new_id(slot), "source_start": source_start, "start": 0.0, "end": source_end - source_start}
        else:
            clip = next((clip for clip in clips if clip["id"] == payload.get("clip_id")), None)
            if clip is None:
                raise SourceTrackError("The clip changed; select it again")
            if action != "sequence_duplicate":
                clips = [item for item in clips if item["id"] != clip["id"]]
            clip = copy.deepcopy(clip)
            if action == "sequence_duplicate":
                clip["id"] = _new_id(slot)
        start = _number(payload.get("start"), "start")
        if start < 0 or start > MAX_SEQUENCE_SECONDS:
            raise SourceTrackError("Place clips between zero and 24 hours")
        if action == "sequence_trim":
            source_start = _number(payload.get("source_start"), "source_start")
            clip.update(**_shift_video_start(clip, source_start - clip["source_start"]), start=start, end=_number(payload.get("end"), "end"), source_start=source_start)
            clips.append(clip)
        else:
            clip.update(end=start + clip["end"] - clip["start"], start=start)
            overlap = any(item["start"] < clip["end"] - EPSILON and item["end"] > start + EPSILON for item in clips)
            if action == "sequence_move" and payload.get("mode") == "overwrite":
                clips = [*_without_time(clips, start, clip["end"], slot=slot), clip]
            elif overlap and action in {"sequence_move", "sequence_duplicate", "sequence_insert"}:
                clips = _insert_at(clips, clip, slot)
            else:
                clips.append(clip)
    manual["source_tracks"][slot] = clips
    _finish(value)
    if manual["source_tracks"] == initial_tracks:
        return None
    return manual
