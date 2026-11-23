"""Replace one imported timeline occurrence, not an original, file or edit interval."""
from __future__ import annotations

import math
import re

from .media_library import ASSET_ID_RE, MAX_ASSET_SECONDS, MediaLibraryError, validate_media_clip

_OCCURRENCE = re.compile(r"media_[0-9a-f]{32}\Z")


def prepare_take_replacement(project, payload, duration):
    manual = project.get("manual") or {}
    cid, old_id, new_id = (payload.get(k) for k in ("clip_id", "previous_asset_id", "asset_id"))
    if (not isinstance(cid, str) or not _OCCURRENCE.fullmatch(cid)
            or any(not isinstance(k, str) or not ASSET_ID_RE.fullmatch(k) for k in (old_id, new_id))):
        raise MediaLibraryError("Choose one imported clip and two valid project files")
    rows = manual.get("media_clips") or []
    matches = [row for row in rows if row.get("id") == cid]
    if len(matches) != 1 or matches[0].get("asset_id") != old_id:
        raise MediaLibraryError("The selected clip or its original take changed. Review the current edit")
    clip = matches[0]
    if old_id == new_id:
        raise MediaLibraryError("Choose a different file; use Slip to change the same take")
    model = manual.get("layer_tracks")
    if model and any(t["id"] == clip.get("track_id") and t.get("locked") for t in model["tracks"]):
        raise MediaLibraryError("Unlock this clip's track before replacing its take")
    old, new = (project.get("assets", {}).get(k) for k in (old_id, new_id))
    if any(not isinstance(a, dict) or a.get("id") != i or a.get("status") != "ready"
           for a, i in ((old, old_id), (new, new_id))):
        raise MediaLibraryError("Both project files must be ready before replacing this take")
    kind = old.get("kind")
    if kind not in ("video", "audio", "image") or kind != new.get("kind"):
        raise MediaLibraryError("Choose another file of the same type: video, audio, or still image")
    if any(type(clip.get(k)) not in (int, float) or not math.isfinite(clip[k]) for k in ("start", "end", "speed")):
        raise MediaLibraryError("The selected clip has invalid saved timing. Reopen the current edit")
    if kind == "video":
        keys = manual.get("chroma_key") or {}
        if not isinstance(keys, dict) or any(i in keys and not isinstance(keys[i], dict) for i in (old_id, new_id)):
            raise MediaLibraryError("The saved source effects are invalid. Review the current edit")
        if any((keys.get(i) or {}).get("enabled") for i in (old_id, new_id)):
            raise MediaLibraryError("An active Chroma Key belongs to one of these files, not this clip. Choose unkeyed takes")
        if type(old.get("has_audio")) is not bool or type(new.get("has_audio")) is not bool:
            raise MediaLibraryError("Both videos need known source sound information")
        if clip.get("audio_enabled") and old["has_audio"] != new["has_audio"]:
            raise MediaLibraryError("The take would add or remove source sound. Turn off Include source sound on this clip first")
    if kind != "image" and any(type(a.get("duration")) not in (int, float) or not math.isfinite(a["duration"])
                               or not .08 <= a["duration"] <= MAX_ASSET_SECONDS for a in (old, new)):
        raise MediaLibraryError("Both timed files need valid source durations")
    validate_media_clip(project, clip, duration)
    patch = {"asset_id": new_id}
    if kind == "image":
        if "source_start" in payload or "source_end" in payload:
            raise MediaLibraryError("A still image has no Source In or Out")
    else:
        limit = new["duration"]
        def point(key):
            value = payload.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= limit:
                raise MediaLibraryError("Choose a finite source position inside the new file")
            # Canonicalize once at the API boundary. The old timeline edges, even
            # genuine subframe values, must never be rounded or reassigned here.
            return math.floor(value * 1e9 + .5) / 1e9
        start = point("source_start")
        bound = point("source_end") if "source_end" in payload else limit
        length = clip["end"] - clip["start"]
        if bound <= start or start + length > bound + 1e-8:
            raise MediaLibraryError("The chosen source range is too short for the full clip at normal speed")
        patch["source_start"] = start
        if kind == "video":
            if start + length * clip["speed"] > bound + 1e-8:
                raise MediaLibraryError("The chosen source range is too short for this picture speed; no frozen frames were added")
            patch["video_source_start"] = start
    validate_media_clip(project, {**clip, **patch}, duration)
    return {"media_clips": [{**row, **patch} if row["id"] == cid else row for row in rows]}
