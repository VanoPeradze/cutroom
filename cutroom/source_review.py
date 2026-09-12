"""Source-clock review actions on an independent edit-clock sequence."""
from __future__ import annotations

from typing import Any

from .source_tracks import EPSILON, SourceTrackError, _duration, _number, _new_id, source_track_clips, minimum_clip_seconds
from .sequence import _automatic_layout, _finish, _insert_at, _insert_time, _remove_time, _slice_rows, _without_time


def _union(ranges):
    result = []
    for start, end in sorted(ranges):
        if end <= start + EPSILON:
            continue
        if result and start <= result[-1][1] + EPSILON:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def _missing(start, end, clips):
    cursor = start
    for left, right in _union((c["source_start"], c["source_start"] + c["end"] - c["start"]) for c in clips):
        if left > cursor + EPSILON:
            yield cursor, min(left, end)
        cursor = max(cursor, right)
        if cursor >= end - EPSILON:
            return
    if cursor < end - EPSILON:
        yield cursor, end


def _original_block(value, slot, start, end, linked):
    length = end - start
    block = {"duration": length, "source_tracks": {"A": [], "B": []},
             "camera_plan": [{"start": 0, "end": length, "camera": slot}]}
    block["source_tracks"][slot] = [{"id": _new_id(slot), "start": 0, "end": length, "source_start": start}]
    if not linked:
        return block
    # Only the manual wrapper changes; never copy media/transcript/history for
    # each missing interval in a long recording.
    original = {**value, "manual": {**value["manual"]}}
    manual = original["manual"]
    base = manual.pop("sequence").get("base_source_tracks")
    manual.pop("source_tracks", None)
    if isinstance(base, dict):
        manual["source_tracks"] = base
    # Reconstruct the other recording using its original synchronization, not
    # an assumed equal source time. Unmapped footage stays selected-source only.
    other = "B" if slot == "A" else "A"
    occupied = []
    for clip in source_track_clips(original, slot):
        left, right = max(start, clip["source_start"]), min(end, clip["source_start"] + clip["end"] - clip["start"])
        for available_start, available_end in _missing(left, right, occupied):
            if available_end <= available_start + EPSILON:
                continue
            master_start = clip["start"] + available_start - clip["source_start"]
            master_end = master_start + available_end - available_start
            at = available_start - start
            occupied.append({"start": 0, "end": available_end - available_start, "source_start": available_start})
            block["source_tracks"][other].extend(_slice_rows(source_track_clips(original, other), master_start, master_end, at=at, slot=other, duplicate=True))
            block["camera_plan"] = _without_time(block["camera_plan"], at, at + master_end - master_start)
            # Fill gaps in the old camera plan with the current default layout.
            cameras = [{"start": at, "end": at + master_end - master_start, "camera": _automatic_layout(value)}]
            for row in (original.get("draft") or {}).get("camera_plan") or []:
                pieces = _slice_rows([row], master_start, master_end, at=at)
                for piece in pieces:
                    cameras = _without_time(cameras, piece["start"], piece["end"])
                    cameras.append(piece)
            block["camera_plan"].extend(cameras)
    return block


def prepare_source_review(value: dict[str, Any], payload: dict[str, Any]):
    slot, scope = payload.get("slot"), payload.get("scope")
    if not isinstance(slot, str) or not isinstance(scope, str) or slot not in {"A", "B"} or _duration(value, slot) <= 0 or scope not in {"edit", slot}:
        raise SourceTrackError("Choose an existing source and either Together or that source only")
    start, end = _number(payload.get("source_start"), "source_start"), _number(payload.get("source_end"), "source_end")
    if start < 0 or end > _duration(value, slot) + EPSILON or end - start < minimum_clip_seconds(value) - EPSILON:
        raise SourceTrackError("Select at least one frame inside the original source")
    end = min(end, _duration(value, slot))
    manual = value["manual"]
    clips = manual["source_tracks"][slot]
    linked = scope == "edit"
    if payload["action"] == "sequence_source_remove":
        ranges = _union((c["start"] + max(start, c["source_start"]) - c["source_start"],
                         c["start"] + min(end, c["source_start"] + c["end"] - c["start"]) - c["source_start"]) for c in clips)
        if not ranges:
            return None
        # Descending edit times remove all uses once, including duplicates,
        # without invalidating later positions. The host records one undo step.
        for left, right in reversed(ranges):
            if linked:
                _remove_time(manual, left, right)
            else:
                manual["source_tracks"][slot] = _without_time(manual["source_tracks"][slot], left, right, slot=slot)
    else:
        missing = list(_missing(start, end, clips))
        if not missing:
            return None
        for left, right in missing:
            clips = manual["source_tracks"][slot]
            following = sorted((c for c in clips if c["source_start"] >= right - EPSILON), key=lambda c: (c["source_start"], c["start"]))
            preceding = sorted((c for c in clips if c["source_start"] + c["end"] - c["start"] <= left + EPSILON),
                               key=lambda c: (-(c["source_start"] + c["end"] - c["start"]), c["end"]))
            at = following[0]["start"] if following else preceding[0]["end"] if preceding else 0
            block = _original_block(value, slot, left, right, linked)
            # Source-only removal leaves a hole. Refill that hole when the
            # surrounding source mapping identifies it; do not desync the pair.
            anchor = preceding[0]["end"] + left - (preceding[0]["source_start"] + preceding[0]["end"] - preceding[0]["start"]) if preceding else at - (right - left)
            if not linked and anchor >= 0 and anchor + right - left <= at + EPSILON and not any(c["start"] < anchor + right - left - EPSILON and c["end"] > anchor + EPSILON for c in clips):
                at = anchor
            if linked:
                _insert_time(manual, block, at)
            else:
                moving = {**block["source_tracks"][slot][0], "start": at, "end": at + right - left}
                overlap = any(c["start"] < moving["end"] - EPSILON and c["end"] > at + EPSILON for c in clips)
                manual["source_tracks"][slot] = _insert_at(clips, moving, slot) if overlap else [*clips, moving]
    manual["sequence"]["camera_plan"].sort(key=lambda row: (row["start"], row["end"]))
    _finish(value)
    return manual
