"""Non-ripple roll and slide operations on an explicit imported-media track."""
from __future__ import annotations

import math
import re

from .frame_rates import first_display_frame, project_export_fps, shift_edit_edge
from .media_library import MediaLibraryError, validate_media_clip

_OCCURRENCE = re.compile(r"media_[0-9a-f]{32}\Z")


def prepare_rolling_edit(project, payload, duration):
    """Build a detached patch before the manual edit and undo history are touched."""
    slide = payload.get("action") == "media_slide"
    manual = project.get("manual") or {}
    model = manual.get("layer_tracks")
    if not isinstance(model, dict):
        raise MediaLibraryError("Enable editable tracks before sliding a clip" if slide else "Enable editable tracks before rolling a shared cut")
    keys = ("left_id", "clip_id", "right_id") if slide else ("left_id", "right_id")
    ids = [payload.get(key) for key in keys]
    if any(not isinstance(i, str) or not _OCCURRENCE.fullmatch(i) for i in ids) or len(set(ids)) != len(ids):
        raise MediaLibraryError("Choose distinct imported media occurrences")
    rows = manual.get("media_clips") or []
    chosen = [next((r for r in rows if r["id"] == i), None) for i in ids]
    if any(row is None for row in chosen):
        raise MediaLibraryError("A selected occurrence no longer exists in this edit")
    left, right = chosen[0], chosen[-1]
    middle = chosen[1] if slide else None
    track = next((t for t in model["tracks"] if t["id"] == left.get("track_id")), None)
    if not track or track["kind"] not in ("visual", "audio") or any(row.get("track_id") != track["id"] for row in chosen):
        raise MediaLibraryError("Choose neighbors on the same saved visual or audio track")
    if track.get("locked"):
        raise MediaLibraryError("Unlock this track before adjusting its cuts")
    if any(a["end"] != b["start"] for a, b in zip(chosen, chosen[1:])):
        raise MediaLibraryError("The outgoing end and incoming start must touch exactly, with no gap or overlap")
    frame = payload.get("frame")
    fps = project_export_fps(project)
    if type(frame) is not int or not 0 <= frame <= math.ceil(duration * fps):
        raise MediaLibraryError("Choose an integer output frame inside the edited timeline")
    cut = trailing = round(frame / fps, 9)
    if slide:
        # Translate the whole shot by integral output frames, even when a
        # legacy clip starts between frames. This preserves its source phase
        # and its visible frame count rather than rounding one edge early.
        shift = frame - first_display_frame(middle["start"], fps)
        cut = shift_edit_edge(middle["start"], shift, fps)
        trailing = shift_edit_edge(middle["end"], shift, fps)
    assets = [project["assets"][r["asset_id"]] for r in chosen]
    left_asset, right_asset = assets[0], assets[-1]
    for row, asset in zip(chosen, assets):
        if asset.get("status") != "ready":
            raise MediaLibraryError("All three original assets must be ready before sliding" if slide else "Both original media assets must be ready before rolling")
        if asset["kind"] != "image" and (type(asset.get("duration")) not in (int, float)
                or not math.isfinite(asset["duration"]) or asset["duration"] <= 0):
            raise MediaLibraryError("All timed source durations must be available")
        validate_media_clip(project, row, duration)
    if abs(cut - left["end"]) <= 1e-9:
        return None
    if min(cut - left["start"], right["end"] - trailing) < .08 - 1e-9:
        raise MediaLibraryError("Keep at least 0.08 seconds on each side of the cut")
    if any(r["motion"] != "none" and a["kind"] != "audio" for r, a in ((left, left_asset), (right, right_asset))):
        raise MediaLibraryError("An outside shot has pan/zoom motion; turn off its motion first")
    if left["fade_out"] or right["fade_in"]:
        raise MediaLibraryError("Remove the facing neighbor fades first" if slide else "Remove fades at the shared cut first; a roll cannot move their envelopes")
    if left["fade_in"] > cut - left["start"] + 1e-9 or right["fade_out"] > right["end"] - trailing + 1e-9:
        raise MediaLibraryError("The rolled cut would enter an outer audio fade")
    delta = trailing - right["start"]
    left_patch = {"end": cut}
    right_patch = {"start": trailing}
    if left_asset["kind"] != "image" and left["source_start"] + cut - left["start"] > left_asset["duration"] + 1e-8:
        raise MediaLibraryError("Not enough outgoing source after this cut")
    if left_asset["kind"] == "video" and delta > 0:
        picture_end = left.get("video_source_start", left["source_start"]) + (cut - left["start"]) * left["speed"]
        if picture_end > left_asset["duration"] + 1e-8:
            raise MediaLibraryError("Not enough outgoing picture after this cut; a roll will not add frozen frames")
    if right_asset["kind"] != "image":
        right_patch["source_start"] = round(right["source_start"] + delta, 9)
        if right_patch["source_start"] < 0:
            raise MediaLibraryError("Not enough incoming source before this cut")
    if right_asset["kind"] == "video":
        picture = round(right.get("video_source_start", right["source_start"]) + delta * right["speed"], 9)
        if picture < 0 or picture > 57600:
            raise MediaLibraryError("Not enough incoming picture for this cut")
        # Extending a shot already in a final-frame hold must not invent handles.
        if delta < 0 and right.get("video_source_start", right["source_start"]) > right_asset["duration"] + 1e-8:
            raise MediaLibraryError("The incoming picture starts in a held frame; there is no continuous picture handle")
        right_patch["video_source_start"] = picture
    patches = {left["id"]: left_patch, right["id"]: right_patch}
    if slide:
        patches[middle["id"]] = {"start": cut, "end": trailing}
    for row in chosen:
        validate_media_clip(project, {**row, **patches[row["id"]]}, duration)
    return {"media_clips": [{**row, **patches[row["id"]]} if row["id"] in patches else row for row in rows]}
