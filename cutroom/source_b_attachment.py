"""Admission rules for adding an original B to a saved single-source edit."""
from __future__ import annotations

from typing import Any

from .sequence import materialize_sequence
from .source_tracks import SourceTrackError


def _uses_embedded_layout(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    if (state.get("embedded_camera") or state.get("manual_embedded_camera")
            or state.get("embedded_layout_confirmed")):
        return True
    if any(state.get(key) == "embedded_stack" for key in ("layout", "settings_layout", "draft_layout")):
        return True
    for key in ("camera_plan", "ai_camera_plan", "camera_overrides", "manual_camera_overrides"):
        rows = state.get(key)
        if isinstance(rows, list) and any(isinstance(row, dict) and
               ("embedded_stack" in (row.get("camera"), row.get("layout"))) for row in rows):
            return True
    return any(_uses_embedded_layout(state.get(key)) for key in
               ("draft", "settings", "manual", "sequence", "manual_sequence", "isolated_render_state"))


def reviewed_a_generation(project: dict[str, Any]) -> str:
    settings = project.get("settings") or {}
    sources = project.get("sources") or {}
    a = sources.get("A")
    if (settings.get("workflow") != "manual" or not isinstance(project.get("draft"), dict)
            or not isinstance(a, dict) or not isinstance(a.get("generation"), str) or not a["generation"]):
        raise SourceTrackError("Open a saved manual edit with its main recording before adding Source B.")
    if sources.get("B") is not None:
        raise SourceTrackError("Source B already exists. This action does not replace it.")
    manual = project.get("manual") or {}
    history = manual.get("_history") or {}
    if not isinstance(history, dict) or any(not isinstance(history.get(key, []), list) for key in ("undo", "redo")):
        raise SourceTrackError("Review this project's saved edit history before adding Source B.")
    if _uses_embedded_layout(project) or any(
        _uses_embedded_layout(entry.get(side))
        for key in ("undo", "redo") for entry in history.get(key, ())
        if isinstance(entry, dict) and entry.get("kind") in {"timeline", "source_review"}
        for side in ("before", "after")
    ):
        raise SourceTrackError("This edit or its Undo history uses a camera embedded in A. Use a separate two-recording project to keep that layout and history intact.")
    mixer = manual.get("source_mixer") or {}
    if str(mixer.get("audio_slot") or settings.get("audio_source") or "A").upper() != "A":
        raise SourceTrackError("Keep narration on Source A before adding a second recording.")
    editable, _ = materialize_sequence(project)
    plan = editable["manual"]["sequence"]["camera_plan"]
    screen = str(mixer.get("screen_slot") or "A").upper()
    if any(row["camera"] not in ({"A", "screen"} if screen == "A" else {"A"}) for row in plan):
        raise SourceTrackError("Keep the current view on Source A before adding a second recording.")
    return a["generation"]
