"""Non-ripple removal of a frame range from one named visual layer track."""
from __future__ import annotations

import math
from .frame_rates import project_export_fps
from .media_library import MAX_MEDIA_CLIPS, MediaLibraryError
from .track_overwrite import _ns, remove_track_window


def lift_window(project, payload, duration):
    fps = project_export_fps(project)
    first, last = payload.get("start_frame"), payload.get("end_frame")
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise MediaLibraryError("Open a saved edit with a finite positive duration")
    if type(first) is not int or type(last) is not int or not 0 <= first < last <= math.ceil(duration * fps):
        raise MediaLibraryError("Choose increasing integer In and Out frames within the edit")
    start, end = _ns(first / fps), _ns(last / fps)
    if start >= duration or end > duration + 5.1e-10:
        raise MediaLibraryError("The whole marked range must fit inside the edit; lift never changes its length")
    end = min(end, duration)
    if end - start < .08 - 1e-9:
        raise MediaLibraryError("Choose at least 0.08 seconds to lift")
    return start, end


def prepare_track_lift(project, payload, duration):
    model = (project.get("manual") or {}).get("layer_tracks")
    if not isinstance(model, dict):
        raise MediaLibraryError("Enable editable tracks before lifting from one visual track")
    track = next((t for t in model["tracks"] if t["id"] == payload.get("track_id")), None)
    if track is None or track["kind"] != "visual":
        raise MediaLibraryError("Choose one named visual track, not Automatic, audio or text")
    if track.get("locked"):
        raise MediaLibraryError("Unlock the selected track before lifting its clips")
    start, end = lift_window(project, payload, duration)
    rows, count = remove_track_window(project, track["id"], start, end, duration, operation="lift")
    if not count:
        raise MediaLibraryError("No imported visual clips overlap the marked range on this track")
    if len(rows) > MAX_MEDIA_CLIPS:
        raise MediaLibraryError("Splitting this range would exceed the 200 media clip limit")
    return {"media_clips": rows}
