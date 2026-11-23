"""One atomic edit-frame split of a temporary imported-media/text selection."""
from __future__ import annotations

import copy
import math
import uuid

from .frame_rates import project_export_fps
from .layer_selection import LayerSelectionError, LAYER_ID_RE, MAX_SELECTED_LAYERS
from .layer_tracks import validate_layer_tracks, validate_locked_layer_changes
from .media_library import MAX_MEDIA_CLIPS, validate_media_clip
from .sequence import editor_sequence_snapshot
from .text_clips import MAX_TEXT_CLIPS, validate_text_clip, _validate_overlaps

_ARRAYS = (("media_clips", MAX_MEDIA_CLIPS, "media_"), ("text_clips", MAX_TEXT_CLIPS, "text_"))


def _ns(value):
    return math.floor(value * 1e9 + .5) / 1e9


def _context(project, payload):
    if not isinstance(payload, dict) or payload.get("action") != "layers_split" or set(payload) - {"action","clip_ids","frame","expected_revision"}:
        raise LayerSelectionError("Choose a valid selected-layer split")
    ids = payload.get("clip_ids")
    if not isinstance(ids,list) or not 2 <= len(ids) <= MAX_SELECTED_LAYERS:
        raise LayerSelectionError("Select between 2 and 200 imported media or custom text clips")
    if any(not isinstance(i,str) or not LAYER_ID_RE.fullmatch(i) for i in ids):
        raise LayerSelectionError("Split imported media and custom text, not original A/B or automatic captions")
    if len(set(ids)) != len(ids):
        raise LayerSelectionError("Selected clip identifiers must be unique")
    snapshot = editor_sequence_snapshot(project)
    if not isinstance(project.get("draft"),dict) or not snapshot:
        raise LayerSelectionError("Open a saved edit before splitting selected layers")
    duration, fps, frame = snapshot["duration"], project_export_fps(project), payload.get("frame")
    if type(frame) is not int or not 0 < frame < math.ceil(duration * fps):
        raise LayerSelectionError("Choose an integer playhead frame strictly inside the edit")
    seam = _ns(frame / fps)
    if seam >= duration:
        raise LayerSelectionError("Choose a playhead frame strictly inside the edit")
    model = validate_layer_tracks(project)
    tracks = {t["id"]: t for t in model["tracks"]} if model else {}
    arrays, seen = {}, set()
    for key, maximum, prefix in _ARRAYS:
        rows = (project.get("manual") or {}).get(key, [])
        if not isinstance(rows,list) or len(rows)>maximum:
            raise LayerSelectionError("The saved timeline layer list is invalid")
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not row["id"].startswith(prefix) or not LAYER_ID_RE.fullmatch(row["id"]) or row["id"] in seen:
                raise LayerSelectionError("The saved timeline has invalid or repeated layer identities")
            seen.add(row["id"])
        arrays[key] = rows
    selected = set(ids)
    if not selected <= seen:
        raise LayerSelectionError("A selected clip no longer exists; select the layers again")
    for row in (r for rows in arrays.values() for r in rows if r["id"] in selected):
        if tracks.get(row.get("track_id"),{}).get("locked"):
            raise LayerSelectionError("Unlock every selected track before splitting")
    return arrays, selected, seam, duration, seen


def _pieces(project, row, seam, duration, right_id):
    media = row["id"].startswith("media_")
    if any(type(row.get(k)) not in (int,float) or not math.isfinite(row[k]) for k in ("start","end")):
        raise LayerSelectionError("A selected layer has invalid saved timing")
    before, after = seam - row["start"], row["end"] - seam
    if min(before, after) < .08 - 1e-9:
        raise LayerSelectionError("Every selected clip must cross the playhead with at least 0.08 seconds on each side")
    left, right = copy.deepcopy(row), copy.deepcopy(row)
    left["end"] = right["start"] = seam
    right["id"] = right_id
    if media:
        asset = (project.get("assets") or {}).get(row.get("asset_id"))
        if not isinstance(asset,dict) or asset.get("id") != row.get("asset_id") or asset.get("kind") not in {"video","audio","image"} or asset.get("status") != "ready":
            raise LayerSelectionError("Every selected media clip needs its ready imported source")
        validate_media_clip(project,row,duration)
        if asset["kind"] != "audio" and row["motion"] != "none":
            raise LayerSelectionError("Splitting a selected pan/zoom would restart its motion; turn it off first")
        if before < row["fade_in"] - 1e-9 or after < row["fade_out"] - 1e-9:
            raise LayerSelectionError("The playhead is inside a selected media audio fade")
        left["fade_out"] = right["fade_in"] = 0
        if asset["kind"] != "image":
            right["source_start"] = _ns(row["source_start"] + before)
        if asset["kind"] == "video":
            right["video_source_start"] = _ns(row.get("video_source_start",row["source_start"]) + before * row["speed"])
        validate_media_clip(project,left,duration); validate_media_clip(project,right,duration)
    else:
        validate_text_clip(row,duration)
        if row.get("template") == "chapter":
            raise LayerSelectionError("The Chapter title has a built-in fade; splitting would restart it. Choose a static text template first")
        # Validate without replacing original fields/defaults or rounding the
        # common frame edge to the older text editor's six-decimal precision.
        validate_text_clip(left,duration); validate_text_clip(right,duration)
    return left,right


def prepare_group_split(project, payload):
    arrays, selected, seam, duration, seen = _context(project,payload)
    result = {}
    for key, maximum, prefix in _ARRAYS:
        rows = arrays[key]
        if len(rows) + sum(row["id"] in selected for row in rows) > maximum:
            raise LayerSelectionError(f"Splitting this selection would exceed the {maximum} clip limit")
        if not any(row["id"] in selected for row in rows):
            continue
        new = []
        for row in rows:
            if row["id"] not in selected:
                new.append(copy.deepcopy(row)); continue
            fresh = prefix + uuid.uuid4().hex
            while fresh in seen:
                fresh = prefix + uuid.uuid4().hex
            seen.add(fresh)
            new.extend(_pieces(project,row,seam,duration,fresh))
        result[key] = new
    _validate_overlaps(result.get("text_clips",arrays["text_clips"]))
    staged = copy.deepcopy(project)
    staged["manual"].update(result)
    validate_layer_tracks(staged); validate_locked_layer_changes(project,staged)
    return result


def group_split_receipt(before, after, payload):
    """Verify all left/right pieces inside the transaction; do not persist IDs."""
    arrays, selected, seam, duration, seen = _context(before,payload)
    created = []
    for key, maximum, prefix in _ARRAYS:
        actual = (after.get("manual") or {}).get(key,[])
        expected_count = len(arrays[key]) + sum(row["id"] in selected for row in arrays[key])
        if not isinstance(actual,list) or len(actual)!=expected_count:
            raise LayerSelectionError("The split arrangement could not be verified")
        cursor = 0
        for old in arrays[key]:
            if old["id"] not in selected:
                if actual[cursor]!=old:
                    raise LayerSelectionError("An unselected layer changed while splitting")
                cursor += 1; continue
            left,right = actual[cursor:cursor+2]
            ident = right.get("id") if isinstance(right,dict) else None
            if not isinstance(ident,str) or not ident.startswith(prefix) or not LAYER_ID_RE.fullmatch(ident) or ident in seen:
                raise LayerSelectionError("A right-hand split piece has an invalid or reused identity")
            if (left,right)!=_pieces(before,old,seam,duration,ident):
                raise LayerSelectionError("The split changed source clocks, track membership, appearance or bounds")
            seen.add(ident);created.append({"source_id":old["id"],"clip_id":ident})
            cursor += 2
    return created
