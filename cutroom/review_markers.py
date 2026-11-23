"""Bounded, project-owned timeline review notes. These are not clips or render inputs."""
from __future__ import annotations

import math
import re

from .frame_rates import EXPORT_FPS_CHOICES, project_export_fps
from .sequence import editor_sequence_snapshot
from .source_tracks import has_sequence, timeline_duration
from .utils import new_id

COLORS = frozenset(("amber", "teal", "violet", "coral"))
LIMIT = 200
ID = re.compile(r"marker_[a-f0-9]{12}\Z")


class MarkerError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def text(value, *, limit, required):
    if not isinstance(value, str):
        raise MarkerError("Marker names and notes must be text.")
    value = value.strip()
    if (required and not value) or len(value) > limit or any(ord(c) < 32 and c != "\n" for c in value):
        raise MarkerError(f"Use {'1' if required else '0'}–{limit} characters without control codes.")
    if required and "\n" in value:
        raise MarkerError("Keep the marker name on one line.")
    return value


def fields(data):
    color = data["color"]
    if not isinstance(color, str) or color not in COLORS:
        raise MarkerError("Choose an available marker color.")
    return {"label": text(data["label"], limit=80, required=True),
            "note": text(data["note"], limit=320, required=False), "color": color}


def saved_rows(project):
    reg = project.get("review_markers", {"version":1, "items":[]})
    issue = "This marker collection is not supported. The saved notes were left unchanged."
    if not isinstance(reg, dict) or type(reg.get("version")) is not int or reg["version"] != 1 or set(reg) != {"version","items"}:
        raise MarkerError(issue,409)
    rows = reg["items"]
    if not isinstance(rows, list) or len(rows)>LIMIT:
        raise MarkerError(issue,409)
    ids=set()
    for r in rows:
        if (not isinstance(r,dict) or set(r)!={"id","frame","fps","label","note","color"}
                or not isinstance(r["id"],str) or not ID.fullmatch(r["id"]) or r["id"] in ids
                or type(r["frame"]) is not int or not 0<=r["frame"]<=100_000_000
                or type(r["fps"]) is not int or r["fps"] not in EXPORT_FPS_CHOICES):
            raise MarkerError(issue,409)
        try:
            if fields(r) != {key:r[key] for key in ("label","note","color")}:
                raise MarkerError(issue,409)
        except MarkerError as exc:
            raise MarkerError(issue,409) from exc
        ids.add(r["id"])
    return rows


def apply_marker(project, data):
    action = data.get("action")
    allowed = {"add":{"frame","fps","label","note","color"}, "edit":{"id","label","note","color"},
               "move":{"id","frame","fps"}, "remove":{"id"}}
    if not isinstance(action,str) or action not in allowed or set(data)!={"action","expected_revision",*allowed[action]}:
        raise MarkerError("Use one explicit marker action and only its fields.")
    rows = list(saved_rows(project))
    if action=="add" and len(rows)>=LIMIT:
        raise MarkerError("This timeline already has 200 markers. Remove one to add another.",409)
    i=None
    if action!="add":
        key=data["id"]
        if not isinstance(key,str) or not ID.fullmatch(key):
            raise MarkerError("Select a saved marker.")
        i=next((i for i,r in enumerate(rows) if r["id"]==key),None)
        if i is None: raise MarkerError("The selected marker no longer exists.",409)
    loc={}
    if action in ("add","move"):
        frame,fps=data["frame"],data["fps"]
        if type(fps) is not int or fps not in EXPORT_FPS_CHOICES or type(frame) is not int:
            raise MarkerError("Choose a whole output frame at a supported frame rate.")
        if fps!=project_export_fps(project):
            raise MarkerError("The frame rate changed. Review the playhead position again.",409)
        # Modern projects already own an edit clock. Avoid expanding/copying every
        # source and layer just to save a note on a long timeline. Legacy drafts
        # still need their cut-out source ranges projected onto the edited clock.
        duration=(timeline_duration(project) if project.get("draft") and has_sequence(project)
                  else (editor_sequence_snapshot(project) or {}).get("duration",0))
        if not project.get("sources",{}).get("A") or not duration or not 0<=frame<math.floor(duration*fps+.5):
            raise MarkerError("Choose a frame within the saved edited timeline.")
        loc={"frame":frame,"fps":fps}
    if action=="add":
        rows.append({"id":new_id("marker"),**loc,**fields(data)})
    elif action=="edit":
        replacement={**rows[i],**fields(data)}
        if replacement==rows[i]: raise MarkerError("The marker is already saved with those details.",409)
        rows[i]=replacement
    elif action=="move":
        if rows[i]["frame"]*loc["fps"]==loc["frame"]*rows[i]["fps"]:
            raise MarkerError("The marker is already at the playhead.",409)
        rows[i]={**rows[i],**loc}
    else:
        rows.pop(i)
    rows.sort(key=lambda r:(r["frame"]/r["fps"],r["id"]))
    project["review_markers"]={"version":1,"items":rows}
