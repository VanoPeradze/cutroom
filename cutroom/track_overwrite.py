"""Three-point, non-ripple source overwrite on exactly one explicit visual track."""
from __future__ import annotations

import math
import uuid

from .frame_rates import project_export_fps, stored_frame
from .media_library import ASSET_ID_RE, MAX_ASSET_SECONDS, MAX_MEDIA_CLIPS, MediaLibraryError, validate_media_clip


def _ns(value):
    return math.floor(value * 1e9 + .5) / 1e9


def prepare_track_overwrite(project, payload, duration):
    manual = project.get("manual") or {}
    model = manual.get("layer_tracks")
    if not isinstance(model, dict):
        raise MediaLibraryError("Enable editable tracks before overwriting one visual track")
    track = next((t for t in model["tracks"] if t["id"] == payload.get("track_id")), None)
    if track is None or track["kind"] != "visual":
        raise MediaLibraryError("Choose one named visual destination track, not Automatic, audio or text")
    if track.get("locked"):
        raise MediaLibraryError("Unlock the destination track before overwriting its clips")
    aid = payload.get("asset_id")
    asset = (project.get("assets") or {}).get(aid) if isinstance(aid, str) and ASSET_ID_RE.fullmatch(aid) else None
    if not isinstance(asset, dict) or asset.get("id") != aid or asset.get("kind") != "video" or asset.get("status") != "ready":
        raise MediaLibraryError("Choose a ready imported video in the Source monitor")
    if type(asset.get("has_audio")) is not bool or type(asset.get("duration")) not in (int,float) or not math.isfinite(asset["duration"]) or not .08 <= asset["duration"] <= MAX_ASSET_SECONDS:
        raise MediaLibraryError("The source video has invalid duration or sound metadata")
    fps, frame = project_export_fps(project), payload.get("frame")
    if type(frame) is not int or not 0 <= frame <= math.ceil(fps * duration):
        raise MediaLibraryError("Choose a valid edit frame for the overwrite")
    marks = [payload.get(k) for k in ("source_start", "source_end")]
    if any(type(v) not in (int,float) or not math.isfinite(v) or not 0 <= v <= asset["duration"] for v in marks):
        raise MediaLibraryError("Choose valid source In and Out inside the original video")
    src, out = map(_ns, marks)
    length = _ns(out - src)
    if length < .08 - 1e-9:
        raise MediaLibraryError("Choose at least 0.08 seconds of source video")
    begin = _ns(frame / fps)
    frames = stored_frame(length, fps)
    end = _ns((frame + frames) / fps) if frames is not None else _ns(begin + length)
    if end > duration + 5.1e-10 or begin >= duration:
        raise MediaLibraryError("The whole marked shot must fit before the edit end; overwrite never extends the timeline")
    if end > duration:
        end = duration  # Only the nanosecond spelling of the actual final frame.
    rows, _ = remove_track_window(project, track["id"], begin, end, duration)
    if len(rows) + 1 > MAX_MEDIA_CLIPS:
        raise MediaLibraryError("This overwrite would exceed the 200 media clip limit; nothing was shortened or removed")
    placed = {"id":"media_" + uuid.uuid4().hex, "asset_id":aid, "track_id":track["id"],
              "start":begin, "end":end, "source_start":src, "video_source_start":src, "speed":1, "volume_db":0,
              "muted":False, "role":"voice", "audio_enabled":asset["has_audio"], "fade_in":0, "fade_out":0,
              "x":0, "y":0, "w":1, "h":1, "fit":"cover", "motion":"none"}
    validate_media_clip(project, placed, duration)
    return {"media_clips":[*rows, placed]}

def remove_track_window(project, track_id, begin, end, duration, *, operation="overwrite"):
    """Retain original ordering and source phases; never move another lane."""
    manual = project.get("manual") or {}
    rows = []; affected = 0
    for row in manual.get("media_clips") or []:
        if row.get("track_id") != track_id or row["end"] <= begin or row["start"] >= end:
            rows.append(row)
            continue
        affected += 1
        original = project["assets"].get(row["asset_id"])
        if not isinstance(original, dict) or original.get("status") != "ready" or original["kind"] not in ("video", "image"):
            raise MediaLibraryError("A destination clip has unavailable original media")
        validate_media_clip(project, row, duration)
        left, right = row["start"] < begin, row["end"] > end
        if not left and not right:
            continue  # Fully covered shapes/fades may disappear as a whole.
        if row["motion"] != "none":
            raise MediaLibraryError(f"A partial {operation} would change a pan/zoom shot's motion. Choose its edge or cover it completely")
        for boundary, remains in ((begin, left), (end, right)):
            if remains and (boundary - row["start"] < row["fade_in"] - 1e-9 or row["end"] - boundary < row["fade_out"] - 1e-9):
                raise MediaLibraryError("A boundary would cut through a destination audio fade; choose another edge")
        if left:
            if begin - row["start"] < .08 - 1e-9:
                raise MediaLibraryError("A retained piece would be shorter than 0.08 seconds")
            piece = {**row, "end":begin, "fade_out":0}
            validate_media_clip(project, piece, duration); rows.append(piece)
        if right:
            if row["end"] - end < .08 - 1e-9:
                raise MediaLibraryError("A retained piece would be shorter than 0.08 seconds")
            piece = {**row, "start":end, "fade_in":0}
            if left:
                piece["id"] = "media_" + uuid.uuid4().hex
            if original["kind"] == "video":
                elapsed = end - row["start"]
                piece["source_start"] = _ns(row["source_start"] + elapsed)
                piece["video_source_start"] = _ns(row.get("video_source_start", row["source_start"]) + elapsed * row["speed"])
            validate_media_clip(project, piece, duration); rows.append(piece)
    return rows, affected

