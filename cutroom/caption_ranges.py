"""Exact selected edit/source mapping for bounded caption proposals."""
import math
from .caption_alternatives import binding, geometry

def selected_scope(project, selection):
    from .caption_items import _pieces
    from .render import caption_context
    from .source_tracks import source_track_clips
    binding(project)
    if not isinstance(selection,dict) or set(selection)!={"start","end"}:
        raise ValueError("Choose an explicit edited-timeline start and end.")
    start,end=selection["start"],selection["end"]
    if any(isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) for n in (start,end)) or not 0<=start<end or end-start>90:
        raise ValueError("Select at most 90 seconds in the edited timeline.")
    context=caption_context(project,aligned=False)
    if project.get("sources",{}).get("B") or context["slot"]!="A" or context["offset"]!=0:
        raise ValueError("Selected captions support only original source A audio, without source B or sync offsets.")
    clips=source_track_clips(project,"A")
    if any(str(c.get("source_ref") or "primary:A")!="primary:A" or float(c.get("video_speed",1))!=1 for c in clips if c["start"]<end and c["end"]>start):
        raise ValueError("Selected captions do not support library-source substitutions or speed changes.")
    pieces=[];cursor=start
    for a,b,c,d,*_ in _pieces(project,context["slot"],context["offset"],context["keeps"]):
        left,right=max(a,start),min(b,end)
        if right<=left:continue
        if abs(left-cursor)>1e-6:raise ValueError("The selected timeline contains an audio gap.")
        source_left=c+left-a;source_right=c+right-a
        if pieces and source_left<pieces[-1][3]-1e-6:raise ValueError("Repeated or reversed source ranges are not supported for selected captions.")
        pieces.append([left,right,source_left,source_right]);cursor=right
    if abs(cursor-end)>1e-6 or not pieces:raise ValueError("The selected range is outside the available edited speech.")
    if len(pieces)>8:raise ValueError("Select at most eight continuous source pieces for one caption generation.")
    return {"kind":"selected_range","timeline_range":[start,end],"pieces":pieces,"geometry":geometry(project)}

def conflicts(project, scope):
    """Conservatively block overlap, retain independently edited outside captions."""
    from .render import project_caption_items
    manual=project.get("manual") or {};start,end=scope["timeline_range"]
    source_ranges=[p[2:] for p in scope["pieces"]]
    fixes=manual.get("caption_corrections") or {}
    for i,row in enumerate((project.get("analysis") or {}).get("transcript",{}).get("segments",[])):
        if str(row.get("id",i)) in fixes and any(row["start"]<b and row["end"]>a for a,b in source_ranges):return True
    edits=manual.get("caption_overrides") or {}
    if manual.get("caption_dormant_overrides"):return True
    if edits:
        items={row["id"]:row for row in project_caption_items(project,aligned=False)}
        if any(key not in items or items[key]["start"]<end and items[key]["end"]>start for key in edits):return True
    return False
