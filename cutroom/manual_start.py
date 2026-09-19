"""Start a non-destructive full-length timeline without running AI."""
import copy
import math

from .editing import CAMERA_OVERRIDE_LAYOUTS, ManualEditError, apply_manual_edit
from .utils import now_iso


def start_manual_draft(project):
    if project.get("draft"):
        raise ManualEditError("This project already has an edit. Open it instead of replacing it.")
    source = (project.get("sources") or {}).get("A") or {}
    duration = float(source.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ManualEditError("Add your main recording before opening the editor.")
    settings = project["settings"]
    plan = [{"start": 0.0, "end": duration, "camera": "A"}]
    project["draft"] = {
        "engine": "manual", "created_at": now_iso(), "status": "ready",
        "title": project.get("name") or "Your edit", "summary": "Your full recording, ready to edit. No AI processing was used.",
        "language": project.get("language", "auto"), "goal": settings.get("goal", "youtube"),
        "aspect": settings.get("aspect", "16:9"), "layout": settings.get("layout", "auto"),
        "pace": settings.get("pace", "balanced"), "source_duration": duration,
        "target_duration": duration, "output_duration": duration, "removed_duration": 0,
        "cuts": [], "keep_ranges": [{"start": 0.0, "end": duration}],
        "camera_plan": plan, "ai_camera_plan": copy.deepcopy(plan), "highlight_ids": [],
        "decisions": [], "audio_plan": [], "audio_source": settings.get("audio_source", "A"),
        "partial_ai": False,
    }
    project["analysis"] = {"segments": [], "transcript": {"segments": [], "words": [], "text": ""},
                           "engine": "manual", "warnings": []}
    settings["captions"] = False
    mixer = copy.deepcopy((project.get("manual") or {}).get("source_mixer") or {})
    if mixer and project.get("sources", {}).get("B"):
        apply_manual_edit(project, {"action": "set_source_mixer", **mixer})
        layout = project["manual"]["source_mixer"].get("default_layout", settings.get("layout", "auto"))
        if layout in CAMERA_OVERRIDE_LAYOUTS:
            apply_manual_edit(project, {"action": "set_camera_layout", "layout": layout,
                                        "start": 0, "end": duration})
    elif (project.get("manual") or {}).get("embedded_camera"):
        embedded = copy.deepcopy(project["manual"]["embedded_camera"])
        focus = embedded.get("content_focus") or {}
        apply_manual_edit(project, {"action": "set_embedded_camera", "enabled": True,
                                    **{key: embedded[key] for key in ("x", "y", "w", "h")},
                                    "content_x": focus.get("x", .5), "content_y": focus.get("y", .5)})
    # These are setup choices, not timeline edits the user needs to undo.
    manual = project.setdefault("manual", {})
    manual.pop("_history", None)
    manual["history"] = {"undo_count": 0, "redo_count": 0}
    return project
