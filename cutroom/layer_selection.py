"""Atomic placement of a temporary selection of imported media and custom text."""
from __future__ import annotations

import copy
import math
import re
import uuid
from typing import Any

from .layer_tracks import TRACK_ACTION_FIELDS, prepare_layer_track_edit, assign_new_layer_tracks, validate_layer_tracks, validate_locked_layer_changes
from .media_library import MAX_MEDIA_CLIPS, MediaLibraryError, validate_media_clip
from .sequence import editor_sequence_snapshot
from .text_clips import MAX_TEXT_CLIPS, TextClipError, _validate_overlaps, validate_text_clip

LAYER_ACTION_FIELDS = {"layers_join": {"clip_ids"}, "layers_split": {"clip_ids", "frame"}, "layers_match_frame": {"clip_ids", "reference_id"}, "layers_relocate": {"clip_ids", "anchor_id", "track_id", "delta"}, "layers_move": {"clip_ids", "delta"}, "layers_remove": {"clip_ids"}, "layers_duplicate": {"clip_ids", "start"}, **TRACK_ACTION_FIELDS}
MAX_SELECTED_LAYERS = 200
LAYER_ID_RE = re.compile(r"(?:media|text)_[0-9a-f]{32}\Z")


class LayerSelectionError(ValueError):
    pass


class UnchangedLayerSelection(Exception):
    """Return a validated no-op from the locked update without writing a revision."""

    def __init__(self, project: dict[str, Any]):
        super().__init__("Selected layers are already at this position")
        self.project = project


def prepare_layer_selection_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("action") not in LAYER_ACTION_FIELDS:
        raise LayerSelectionError("Choose a supported selected-layer edit")
    if set(payload) - {"action", "expected_revision", *LAYER_ACTION_FIELDS[payload["action"]]}:
        raise LayerSelectionError("Unknown selected-layer edit field")
    if payload["action"] in TRACK_ACTION_FIELDS:
        return prepare_layer_track_edit(project, payload)
    if payload["action"] == "layers_join":
        from .group_join import prepare_group_join
        return prepare_group_join(project, payload)
    if payload["action"] == "layers_split":
        from .group_split import prepare_group_split
        return prepare_group_split(project, payload)
    if payload["action"] == "layers_match_frame":
        return _match_frame(project, payload)
    ids = payload.get("clip_ids")
    if not isinstance(ids, list) or not 2 <= len(ids) <= MAX_SELECTED_LAYERS:
        raise LayerSelectionError("Select between 2 and 200 imported media or custom text clips")
    if any(not isinstance(value, str) or not LAYER_ID_RE.fullmatch(value) for value in ids):
        raise LayerSelectionError("Select imported media or custom text, not source tracks or automatic captions")
    if len(set(ids)) != len(ids):
        raise LayerSelectionError("Selected clip identifiers must be unique")
    removing = payload["action"] == "layers_remove"
    duplicating = payload["action"] == "layers_duplicate"
    delta = 0
    if not removing and not duplicating:
        delta = payload.get("delta")
        try:
            finite = math.isfinite(delta)
        except (TypeError, OverflowError):
            finite = False
        if isinstance(delta, bool) or not isinstance(delta, (int, float)) or not finite or abs(delta) > 604800:
            raise LayerSelectionError("delta must be a finite number between -604800 and 604800 seconds")
    snapshot = editor_sequence_snapshot(project)
    if not isinstance(project.get("draft"), dict) or not snapshot:
        raise LayerSelectionError("Open an edit before editing selected layers")
    duration = snapshot["duration"]
    manual = project.get("manual") or {}
    arrays = {}
    all_ids = set()
    for key, limit, prefix in (("media_clips", MAX_MEDIA_CLIPS, "media_"), ("text_clips", MAX_TEXT_CLIPS, "text_")):
        rows = manual.get(key, [])
        if not isinstance(rows, list) or len(rows) > limit:
            raise LayerSelectionError("The saved timeline layer list is invalid")
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].startswith(prefix) or (removing and not LAYER_ID_RE.fullmatch(row["id"])):
                raise LayerSelectionError("The saved timeline layer identity is invalid")
            if row["id"] in all_ids:
                raise LayerSelectionError("Saved timeline layer identifiers must be unique")
            all_ids.add(row["id"])
        arrays[key] = rows
    selected = set(ids)
    if not selected <= all_ids:
        raise LayerSelectionError("A selected clip no longer exists. Select the layers again")

    if duplicating:
        return _duplicate_layers(project, payload, arrays, selected, duration)

    if removing:
        # Removing occurrences never needs a ready asset or normalizes surviving
        # data. Broken/offline clips must remain removable, just like singular
        # Remove. Array shape and identity are still checked before any change.
        return {key: copy.deepcopy([row for row in rows if row["id"] not in selected])
                for key, rows in arrays.items() if any(row["id"] in selected for row in rows)}

    destinations = None
    if payload["action"] == "layers_relocate":
        model = validate_layer_tracks(project)
        if model is None:
            raise LayerSelectionError("Enable persistent layer tracks before relocating a selection")
        anchor = payload.get("anchor_id")
        if not isinstance(anchor, str) or anchor not in selected:
            raise LayerSelectionError("Choose an anchor from the selected clips")
        members = [row for rows in arrays.values() for row in rows if row["id"] in selected]
        tracks = {track["id"]: track for track in model["tracks"]}
        kinds = {tracks[row["track_id"]]["kind"] for row in members}
        if len(kinds) != 1:
            raise LayerSelectionError("Relocate clips of one track kind at a time")
        kind = next(iter(kinds))
        target = payload.get("track_id")
        if not isinstance(target, str) or target not in tracks or tracks[target]["kind"] != kind:
            raise LayerSelectionError("Choose an existing compatible destination track")
        lanes = [track["id"] for track in model["tracks"] if track["kind"] == kind]
        anchor_row = next(row for row in members if row["id"] == anchor)
        offset = lanes.index(target) - lanes.index(anchor_row["track_id"])
        destinations = {}
        for row in members:
            rank = lanes.index(row["track_id"]) + offset
            if not 0 <= rank < len(lanes):
                raise LayerSelectionError("The whole selection must fit the existing tracks")
            destination = lanes[rank]
            if tracks[row["track_id"]].get("locked", False) or tracks[destination].get("locked", False):
                raise LayerSelectionError("Unlock every selected source and destination track before relocating")
            destinations[row["id"]] = destination

    # Build the entire destination before checking text overlap. Checking one
    # member at a time would reject valid translations past other selected text.
    result = {}
    changed = False
    for key, rows in arrays.items():
        moved = copy.deepcopy(rows)
        for row in moved:
            if destinations is not None and row["id"] in selected:
                row["track_id"] = destinations[row["id"]]
            if row["id"] in selected and delta != 0:
                precision = 6 if key == "text_clips" else 9
                for endpoint in ("start", "end"):
                    value = row.get(endpoint)
                    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                        raise LayerSelectionError("The saved layer timing is invalid")
                    # Match the canonical JavaScript preview, including exact
                    # half steps. Python round() uses a different tie rule.
                    factor = 10 ** precision
                    row[endpoint] = math.floor((value + delta) * factor + .5) / factor
            # Validators check the full candidate without normalizing unrelated
            # source clocks, text, enabled defaults, styles or other raw fields.
            try:
                if key == "media_clips":
                    asset = (project.get("assets") or {}).get(row.get("asset_id"))
                    if not isinstance(asset, dict) or asset.get("kind") not in {"video", "audio", "image"}:
                        raise LayerSelectionError("A saved media layer has no supported imported asset")
                    validate_media_clip(project, row, duration)
                else:
                    validate_text_clip(row, duration)
            except (MediaLibraryError, TextClipError):
                raise
            except (KeyError, TypeError, ValueError, OverflowError) as error:
                raise LayerSelectionError("The saved layer data is invalid. Reload or repair it before moving") from error
        if moved != rows:
            changed = True
            result[key] = moved
    _validate_overlaps(result.get("text_clips", arrays["text_clips"]))
    if destinations is not None:
        staged = copy.deepcopy(project)
        staged["manual"].update(result)
        validate_layer_tracks(staged)
        validate_locked_layer_changes(project, staged)
    return result if changed else None


def _duplicate_layers(project, payload, arrays, selected, duration):
    """Copy a selection in painter order; never normalize source rows."""
    start = payload.get("start")
    if type(start) not in (int, float) or not math.isfinite(start) or not 0 <= start <= duration:
        raise LayerSelectionError("Choose a finite duplicate start inside the current edit")
    selected_rows = [row for rows in arrays.values() for row in rows if row["id"] in selected]
    for row in selected_rows:
        if not LAYER_ID_RE.fullmatch(row["id"]):
            raise LayerSelectionError("The selected layer identity is invalid")
        for key in ("start", "end"):
            if type(row.get(key)) not in (int, float) or not math.isfinite(row[key]):
                raise LayerSelectionError("The selected layer timing is invalid")
    delta = start - min(row["start"] for row in selected_rows)
    model = (project.get("manual") or {}).get("layer_tracks")
    ranks = {track["id"]:index for index,track in enumerate(model["tracks"])} if model else {}
    result = {}
    allocation_order = {}
    source_track_ids = {}
    for key, rows in arrays.items():
        copies = [row for row in rows if row["id"] in selected]
        maximum = MAX_MEDIA_CLIPS if key == "media_clips" else MAX_TEXT_CLIPS
        if len(rows) + len(copies) > maximum:
            raise LayerSelectionError(f"Duplicating this selection would exceed the {maximum} clip limit")
        if not copies:
            continue
        if model:
            if key == "text_clips":
                copies.sort(key=lambda row:ranks[row["track_id"]])
            else:
                # Keep audio enumeration while ordering visual copies by actual
                # compositing priority, independent of click/saved array order.
                visuals = iter(sorted([row for row in copies if (project.get("assets") or {}).get(row.get("asset_id"),{}).get("kind") != "audio"], key=lambda row:ranks[row["track_id"]]))
                copies = [row if (project.get("assets") or {}).get(row.get("asset_id"),{}).get("kind") == "audio" else next(visuals) for row in copies]
        sorted_sources = list(copies)
        copies = [row for row in rows if row["id"] in selected]
        added = []
        by_source = {}
        for original in copies:
            row = copy.deepcopy(original)
            precision = 9 if key == "media_clips" else 6
            if delta != 0:
                factor = 10 ** precision
                for endpoint in ("start", "end"):
                    row[endpoint] = math.floor((row[endpoint] + delta) * factor + .5) / factor
            try:
                if key == "media_clips":
                    asset = (project.get("assets") or {}).get(row.get("asset_id"))
                    if not isinstance(asset,dict) or asset.get("kind") not in {"video","audio","image"}:
                        raise LayerSelectionError("Choose a supported ready imported asset")
                    validate_media_clip(project, original, duration)
                    validate_media_clip(project, row, duration)
                else:
                    validate_text_clip(original, duration)
                    validate_text_clip(row, duration)
            except (KeyError, TypeError, OverflowError) as exc:
                raise LayerSelectionError("The selected layer data is invalid") from exc
            row["id"] = ("media_" if key == "media_clips" else "text_") + uuid.uuid4().hex
            row.pop("track_id", None)  # Never inherit a locked/occupied destination.
            added.append(row)
            by_source[original["id"]] = row
            source_track_ids[row["id"]] = original.get("track_id")
        allocation_order[key] = [by_source[row["id"]] for row in sorted_sources]
        result[key] = copy.deepcopy(rows) + added
    _validate_overlaps(result.get("text_clips", arrays["text_clips"]))
    if model:
        staged = copy.deepcopy(project)
        staged["manual"].update(result)
        for key, ordered in allocation_order.items():
            staged["manual"][key] = copy.deepcopy(arrays[key]) + ordered
        assign_new_layer_tracks(project, staged, "media_duplicate", source_track_ids=source_track_ids)
        assigned = {row["id"]:row["track_id"] for key in allocation_order for row in staged["manual"][key]}
        for key in allocation_order:
            for row in result[key][len(arrays[key]):]:row["track_id"] = assigned[row["id"]]
        result["layer_tracks"] = staged["manual"]["layer_tracks"]
    return result


def group_duplicate_receipt(before, after, payload):
    """Verify exact raw-order copies inside the store transaction; never persist."""
    selected = set(payload["clip_ids"])
    originals = [row for key in ("media_clips","text_clips") for row in before.get("manual",{}).get(key,[]) if row["id"] in selected]
    delta = payload["start"] - min(row["start"] for row in originals)
    created = []
    seen = {row["id"] for key in ("media_clips","text_clips") for row in before.get("manual",{}).get(key,[])}
    for key, precision in (("media_clips",9),("text_clips",6)):
        old = before.get("manual",{}).get(key,[])
        new = after.get("manual",{}).get(key,[])
        sources = [row for row in old if row["id"] in selected]
        if new[:len(old)] != old or len(new) != len(old)+len(sources):
            raise LayerSelectionError("The copied arrangement could not be verified")
        for source, row in zip(sources,new[len(old):]):
            expected = copy.deepcopy(source)
            if delta != 0:
                for edge in ("start","end"):expected[edge]=math.floor((expected[edge]+delta)*10**precision+.5)/10**precision
            if row["id"] in seen or not LAYER_ID_RE.fullmatch(row["id"]) or {k:v for k,v in row.items() if k not in {"id","track_id"}} != {k:v for k,v in expected.items() if k not in {"id","track_id"}}:
                raise LayerSelectionError("The copied arrangement could not be verified")
            seen.add(row["id"]);created.append({"source_id":source["id"],"clip_id":row["id"]})
    return created


_MEDIA_FRAME_ID = re.compile(r"media_[0-9a-f]{32}\Z")

def _frame_values(row):
    """Return exact saved geometry; cover is only an effective missing-fit default."""
    for key in ("x", "y", "w", "h"):
        v=row.get(key)
        if type(v) not in (int,float) or not (0.01 if key in ("w","h") else 0)<=v<=1 or not math.isfinite(v):
            raise LayerSelectionError("Invalid saved frame geometry")
    if row["x"]+row["w"]>1+1e-8 or row["y"]+row["h"]>1+1e-8:
        raise LayerSelectionError("Frame exceeds canvas")
    fit=row.get("fit","cover")
    if fit not in ("cover","contain"):raise LayerSelectionError("Invalid saved fit")
    return {**{k:row[k] for k in ("x","y","w","h")},"fit":fit}
def _match_frame(project,payload):
    """Stage five-field matching without normalizing clocks or unrelated metadata."""
    if set(payload)-{"action","expected_revision","clip_ids", "reference_id"}:raise LayerSelectionError("Unknown field")
    ids=payload.get("clip_ids");ref=payload.get("reference_id")
    if not isinstance(ids,list) or not 2<=len(ids)<=200 or any(not isinstance(x,str) or not _MEDIA_FRAME_ID.fullmatch(x) for x in ids) or len(set(ids))!=len(ids):raise LayerSelectionError("Choose 2 to 200 distinct visuals")
    if not isinstance(ref,str) or ref not in ids:raise LayerSelectionError("Choose a selected reference")
    model=validate_layer_tracks(project)
    rows=project.get("manual",{}).get("media_clips",[])
    if not isinstance(rows,list) or len(rows)>MAX_MEDIA_CLIPS or any(not isinstance(r,dict) or not isinstance(r.get("id"),str) or not _MEDIA_FRAME_ID.fullmatch(r["id"]) for r in rows) or len({r["id"] for r in rows})!=len(rows):raise LayerSelectionError("Invalid media identifiers")
    texts=project.get("manual",{}).get("text_clips",[])
    if not isinstance(texts,list) or len(texts)>MAX_TEXT_CLIPS or any(not isinstance(r,dict) or not isinstance(r.get("id"),str) or not re.fullmatch(r"text_[0-9a-f]{32}",r["id"]) for r in texts) or len({r["id"] for r in texts})!=len(texts):raise LayerSelectionError("Invalid text identifiers")
    indexed={r["id"]:r for r in rows}
    if any(x not in indexed for x in ids):raise LayerSelectionError("Selected occurrence missing")
    snapshot=editor_sequence_snapshot(project)
    if not snapshot:raise LayerSelectionError("Open a saved timeline")
    tracks={t["id"]:t for t in (model or {}).get("tracks",[])}
    for id in ids:
        row=indexed[id];asset=project.get("assets",{}).get(row.get("asset_id"))
        if not isinstance(asset,dict) or asset.get("status")!="ready" or asset.get("kind") not in ("video","image"):raise LayerSelectionError("Choose ready imported visuals")
        frame=_frame_values(row)
        validate_media_clip(project,{**row,"fit":frame["fit"]},snapshot["duration"])
        if id!=ref and tracks.get(row.get("track_id"),{}).get("locked"):raise LayerSelectionError("Unlock every target")
    # Validation is detached: its nine-decimal normalization must never replace
    # raw source framing or any unowned occurrence fields.
    frame=_frame_values(indexed[ref]);changed=False;result=copy.deepcopy(rows)
    for row in result:
        if row["id"] not in ids or row["id"]==ref or _frame_values(row)==frame:continue
        for key in ("x","y","w","h"):row[key]=frame[key]
        if row.get("fit","cover")!=frame["fit"]:row["fit"]=frame["fit"]
        validate_media_clip(project,{**row,"fit":row.get("fit","cover")},snapshot["duration"])
        changed=True
    staged=copy.deepcopy(project);staged["manual"]["media_clips"]=result
    validate_layer_tracks(staged);validate_locked_layer_changes(project,staged)
    return {"media_clips":result} if changed else None
