"""Remove one provably continuous through edit without undoing unrelated work."""
from __future__ import annotations
import copy
import math
from .frame_rates import project_export_fps, stored_frame
from .layer_selection import LayerSelectionError, LAYER_ID_RE
from .layer_tracks import validate_layer_tracks, validate_locked_layer_changes
from .media_library import MAX_MEDIA_CLIPS, validate_media_clip
from .sequence import editor_sequence_snapshot
from .text_clips import MAX_TEXT_CLIPS, validate_text_clip, _validate_overlaps


def _ns(value):
    return math.floor(value*1e9+.5)/1e9


def _same_clock(value, expected):
    return type(value) in (int,float) and math.isfinite(value) and abs(value-_ns(expected))<=5.1e-10


def _appearance(row, media):
    ignored={"id","start","end"} | ({"source_start","video_source_start","fade_in","fade_out"} if media else set())
    result={k:v for k,v in row.items() if k not in ignored}
    result["enabled"]=row.get("enabled",True)
    if media:
        result["opacity_percent"]=row.get("opacity_percent",100)
    else:
        result["template"]=row.get("template","plain");result["subtext"]=row.get("subtext","")
    return result


def _plan(project,payload):
    if not isinstance(payload,dict) or payload.get("action")!="layers_join" or set(payload)-{"action","clip_ids","expected_revision"}:
        raise LayerSelectionError("Choose a valid through-edit join")
    ids=payload.get("clip_ids")
    if not isinstance(ids,list) or len(ids)!=2 or any(not isinstance(i,str) or not LAYER_ID_RE.fullmatch(i) for i in ids) or ids[0]==ids[1]:
        raise LayerSelectionError("Select exactly two distinct imported media clips or static titles")
    snapshot=editor_sequence_snapshot(project)
    if not isinstance(project.get("draft"),dict) or not snapshot:
        raise LayerSelectionError("Open a saved edit before joining through an edit")
    duration=snapshot["duration"];fps=project_export_fps(project);model=validate_layer_tracks(project)
    arrays={};seen=set()
    for key,limit,prefix in (("media_clips",MAX_MEDIA_CLIPS,"media_"),("text_clips",MAX_TEXT_CLIPS,"text_")):
        rows=(project.get("manual") or {}).get(key,[])
        if not isinstance(rows,list) or len(rows)>limit:raise LayerSelectionError("Invalid saved layer array")
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get("id"),str) or not row["id"].startswith(prefix) or not LAYER_ID_RE.fullmatch(row["id"]) or row["id"] in seen:
                raise LayerSelectionError("Invalid or ambiguous saved layer identity")
            seen.add(row["id"])
        arrays[key]=rows
    if not set(ids)<=seen:raise LayerSelectionError("A selected clip no longer exists")
    if ids[0].startswith("media_")!=ids[1].startswith("media_"):
        raise LayerSelectionError("Join two media occurrences or two static titles, not mixed kinds")
    media=ids[0].startswith("media_");key="media_clips" if media else "text_clips";rows=arrays[key]
    members=[(n,row) for n,row in enumerate(rows) if row["id"] in ids]
    for _,row in members:
        if any(type(row.get(k)) not in (int,float) or not math.isfinite(row[k]) for k in ("start","end")):
            raise LayerSelectionError("Selected clips have invalid saved timing")
    members.sort(key=lambda pair:pair[1]["start"])
    (li,left),(ri,right)=members
    if ri!=li+1:raise LayerSelectionError("Selected clips must be adjacent in saved stacking order, with the left one first")
    if left["end"]!=right["start"] or not left["start"]<left["end"]<right["end"]:
        raise LayerSelectionError("The two clips must touch exactly without a gap or overlap")
    seam = left["end"]
    if stored_frame(seam, fps) is None:
        # Old single-title Split wrote the frame time to six decimals. Only
        # recognize that exact spelling of a frame for two static titles. Do not
        # widen the media/frame tolerance, round real gaps, or migrate any edge.
        legacy_title_frame = (not media and all(row.get("kind") == "title" and
            row.get("template", "plain") in {"plain", "lower_third", "callout", "highlight"} for row in (left, right))
            and seam == round(round(seam * fps) / fps, 6))
        if not legacy_title_frame:
            raise LayerSelectionError("Join at an exact output-frame seam, not a subframe edge")
    if left.get("track_id")!=right.get("track_id"):
        raise LayerSelectionError("The selected clips must belong to the same saved track")
    if model and any(t["id"]==left.get("track_id") and t.get("locked") for t in model["tracks"]):
        raise LayerSelectionError("Unlock the selected track before joining")
    if media:
        aid=left.get("asset_id")
        if aid!=right.get("asset_id"):raise LayerSelectionError("A through edit requires the same imported source")
        asset=(project.get("assets") or {}).get(aid)
        if not isinstance(asset,dict) or asset.get("id")!=aid or asset.get("kind") not in {"video","audio","image"} or asset.get("status")!="ready":
            raise LayerSelectionError("Both clips need their ready imported source")
        validate_media_clip(project,left,duration);validate_media_clip(project,right,duration)
        if left["motion"]!="none" or right["motion"]!="none":
            raise LayerSelectionError("Joining animated pan/zoom could change its motion; turn it off first")
        if left["fade_out"]!=0 or right["fade_in"]!=0:
            raise LayerSelectionError("A fade faces the edit; joining would remove it")
        elapsed=left["end"]-left["start"]
        if asset["kind"]!="image":
            if not _same_clock(right["source_start"],left["source_start"]+elapsed):
                raise LayerSelectionError("The original sound/source clock is not continuous at the edit")
        elif left["source_start"]!=right["source_start"]:
            raise LayerSelectionError("The still-image source settings differ")
        if asset["kind"]=="video" and not _same_clock(right.get("video_source_start",right["source_start"]),left.get("video_source_start",left["source_start"])+elapsed*left["speed"]):
            raise LayerSelectionError("The independent picture clock is not continuous at the edit")
        if asset["kind"]!="video" and left.get("video_source_start")!=right.get("video_source_start"):
            raise LayerSelectionError("The saved source settings differ")
    else:
        validate_text_clip(left,duration);validate_text_clip(right,duration)
        if left["kind"]!="title" or right["kind"]!="title":
            raise LayerSelectionError("Join static titles only; custom captions keep separate subtitle cues")
        if left.get("template")=="chapter" or right.get("template")=="chapter":
            raise LayerSelectionError("Chapter titles have built-in fades and cannot be joined without changing appearance")
    if _appearance(left,media)!=_appearance(right,media):
        raise LayerSelectionError("The clips differ in appearance, enabled state, opacity, sound or other saved settings")
    joined=copy.deepcopy(left);joined["end"]=right["end"]
    if media:
        joined["fade_out"]=right["fade_out"];validate_media_clip(project,joined,duration)
    else:validate_text_clip(joined,duration)
    new=copy.deepcopy(rows[:li])+[joined]+copy.deepcopy(rows[ri+1:])
    result={key:new}
    _validate_overlaps(new if key=="text_clips" else arrays["text_clips"])
    staged=copy.deepcopy(project);staged["manual"].update(result)
    validate_layer_tracks(staged);validate_locked_layer_changes(project,staged)
    return result,{"clip_id":left["id"],"retired_clip_id":right["id"]}


def prepare_group_join(project,payload):
    return _plan(project,payload)[0]


def group_join_receipt(before,after,payload):
    patch,receipt=_plan(before,payload)
    for key in ("media_clips","text_clips"):
        if (after.get("manual") or {}).get(key,[])!=patch.get(key,(before.get("manual") or {}).get(key,[])):
            raise LayerSelectionError("The joined clip, source clocks or an unrelated occurrence changed unexpectedly")
    return receipt
