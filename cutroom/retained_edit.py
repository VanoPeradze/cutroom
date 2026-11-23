"""Explicit activation of a retained edit; never initialize or rebuild its layers."""
import copy
import math
from .utils import now_iso


_INVALID_RETAINED_EDIT = "The retained edit could not be validated. Restore its saved timeline before resuming."
_RETAINED_EDIT_ISSUES = {
    "has_edit": "This project already has an edit. Open it instead.",
    "no_edit": "There is no retained edit to resume.",
    "unsupported": "The retained edit has no supported explicit timeline. No full recording was substituted.",
    "duration": "The retained edit duration is invalid.",
    "source_mapping": "Resume requires the retained A mapping and an explicitly empty B mapping.",
    "source_a_needed": "Prepare the original source A before resuming its retained clips.",
    "camera_plan": "The retained camera plan is invalid.",
    "camera_gap": "The retained camera plan must cover the saved timeline without gaps or overlaps.",
    "camera_duration": "The retained camera plan does not cover the saved duration.",
    "layer_arrays": "The retained layer arrays are invalid.",
    "source_a_unavailable": "The retained source A original is unavailable. Restore it before resuming.",
    "background_unavailable": "A retained Chroma Key background original is unavailable. Restore it before resuming.",
    "import_unavailable": "A retained imported original is unavailable. Restore it before resuming.",
    "original_unavailable": "A retained original is unavailable or has an unsafe path. Restore it before resuming.",
}


class RetainedEditError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(_RETAINED_EDIT_ISSUES.get(reason, _INVALID_RETAINED_EDIT))


def public_retained_edit_issue(error: Exception) -> str:
    if isinstance(error, RetainedEditError):
        return _RETAINED_EDIT_ISSUES.get(error.reason, _INVALID_RETAINED_EDIT)
    return _INVALID_RETAINED_EDIT


def has_retained_edit(project):
    manual = project.get("manual") or {}
    if not isinstance(manual, dict):
        return bool(manual)
    return any(key in manual for key in ("sequence", "layer_tracks")) or any(
        manual.get(key) for key in ("source_tracks", "media_clips", "text_clips", "cuts", "keeps", "keep_ranges"))


def _finite(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _candidate(project, project_root=None):
    from .sequence import materialize_sequence, SEQUENCE_LAYOUTS
    from .source_tracks import MAX_SEQUENCE_SECONDS, validate_sequence_version
    from .layer_tracks import validate_layer_tracks, _rows
    from .media_library import validate_media_clip
    from .text_clips import validate_text_clip, _validate_overlaps
    if project.get("draft") is not None:
        raise RetainedEditError("has_edit")
    manual = project.get("manual")
    if not isinstance(manual, dict) or not has_retained_edit(project):
        raise RetainedEditError("no_edit")
    validate_sequence_version(project)
    sequence = manual.get("sequence")
    if not isinstance(sequence, dict) or type(sequence.get("version")) is not int or sequence["version"] != 1:
        raise RetainedEditError("unsupported")
    duration = sequence.get("duration")
    if not _finite(duration) or not 0 <= duration <= MAX_SEQUENCE_SECONDS:
        raise RetainedEditError("duration")
    tracks = manual.get("source_tracks")
    if not isinstance(tracks, dict) or set(tracks) - {"A", "B"} or not isinstance(tracks.get("A"), list) or tracks.get("B") != []:
        raise RetainedEditError("source_mapping")
    source = (project.get("sources") or {}).get("A")
    if tracks["A"]:
        if not isinstance(source, dict) or source.get("preparation") not in (None, "ready") or not _finite(source.get("duration")) or source["duration"] <= 0 or not source.get("relative_path"):
            raise RetainedEditError("source_a_needed")
    cameras = sequence.get("camera_plan")
    if not isinstance(cameras, list):
        raise RetainedEditError("camera_plan")
    cursor = 0
    for row in cameras:
        if not isinstance(row, dict) or not _finite(row.get("start")) or not _finite(row.get("end")) or row["start"] < 0 or row["end"] <= row["start"] or row["end"] > duration + 1e-8 or abs(row["start"] - cursor) > 1e-8 or row.get("camera") not in SEQUENCE_LAYOUTS:
            raise RetainedEditError("camera_gap")
        cursor = row["end"]
    if abs(cursor - duration) > 1e-8:
        raise RetainedEditError("camera_duration")
    settings = project.get("settings") or {}
    source_duration = (source or {}).get("duration", 0)
    source_ranges = [{"start": 0.0, "end": source_duration}] if _finite(source_duration) and source_duration > 0 else []
    source_cameras = [{**row, "camera": "A"} for row in source_ranges]
    draft = {"engine": "manual", "created_at": now_iso(), "status": "ready",
             "title": project.get("name") or "Resumed edit",
             "summary": "Resumed the saved timeline. Previous AI analysis and automatic captions were not recovered.",
             "language": project.get("language", "auto"), "goal": settings.get("goal", "youtube"),
             "aspect": settings.get("aspect", "16:9"), "layout": settings.get("layout", "auto"),
             "pace": settings.get("pace", "balanced"), "source_duration": (source or {}).get("duration", 0),
             "target_duration": duration, "output_duration": duration, "removed_duration": 0,
             "cuts": [], "keep_ranges": source_ranges, "camera_plan": source_cameras,
             "ai_camera_plan": [], "highlight_ids": [], "decisions": [], "audio_plan": [],
             "audio_source": (manual.get("source_mixer") or {}).get("audio_slot", settings.get("audio_source", "A")),
             "partial_ai": False}
    candidate = {**project, "draft": draft}
    materialize_sequence(candidate)  # detached validation; normalized mappings are discarded
    validate_layer_tracks(candidate)
    media = manual.get("media_clips", [])
    texts = manual.get("text_clips", [])
    if not isinstance(media, list) or not isinstance(texts, list):
        raise RetainedEditError("layer_arrays")
    _rows(candidate)  # identity, array limits, finite timing and known asset kinds
    for clip in media:
        validate_media_clip(candidate, clip, duration)
    for clip in texts:
        validate_text_clip(clip, duration)
    _validate_overlaps(texts)
    from .render_inventory import chroma_background_slots
    backgrounds = chroma_background_slots(candidate)
    if project_root is not None:
        from pathlib import Path
        from .media_library import safe_asset_path
        root = Path(project_root).resolve()
        try:
            if tracks["A"]:
                relative = source["relative_path"]
                original = (root / relative.replace("\\", "/")).resolve()
                if root not in original.parents or not original.is_file():
                    raise RetainedEditError("source_a_unavailable")
            for _, background in backgrounds:
                if not safe_asset_path(root, background.get("path")).is_file():
                    raise RetainedEditError("background_unavailable")
            for clip in media:
                asset = project["assets"][clip["asset_id"]]
                if not safe_asset_path(root, asset.get("path")).is_file():
                    raise RetainedEditError("import_unavailable")
        except (OSError, RuntimeError) as error:
            raise RetainedEditError("original_unavailable") from error
    return draft


def retained_edit_status(project, project_root=None):
    if isinstance(project.get("draft"), dict) or not has_retained_edit(project):
        return None
    manual = project.get("manual") if isinstance(project.get("manual"), dict) else {}
    def count(value):
        return len(value) if isinstance(value, list) else 0
    tracks = manual.get("source_tracks") if isinstance(manual.get("source_tracks"), dict) else {}
    model = manual.get("layer_tracks") if isinstance(manual.get("layer_tracks"), dict) else {}
    duration = (manual.get("sequence") or {}).get("duration") if isinstance(manual.get("sequence"), dict) else None
    result = {"available": False, "issue": "", "duration": duration if _finite(duration) else None,
              "source_a_clips": count(tracks.get("A")), "media_clips": count(manual.get("media_clips")),
              "text_clips": count(manual.get("text_clips")), "track_count": count(model.get("tracks"))}
    try:
        _candidate(project, project_root)
        result["available"] = True
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        result["issue"] = public_retained_edit_issue(error)
    return result


def resume_retained_edit(project, project_root=None):
    draft = _candidate(project, project_root)
    project["draft"] = draft
    return project
