"""Detached identity for existing A/B lanes and independent library occurrences.

V1 project storage, edit clocks and render input order remain authoritative.
Generation references identify current media, not immutable content snapshots.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from .media_library import ASSET_ID_RE, CLIP_FIELDS, validate_media_clip
from .render_inventory import RenderInputInventory, compile_render_inputs
from .sequence import editor_sequence_snapshot
from .source_tracks import SourceTrackError, _validated, validate_sequence_version


ID_ACTIONS = ("sequence_split", "sequence_trim", "sequence_speed")
_PROJECT_ID = re.compile(r"project_[0-9a-f]{12}\Z")
_GENERATION = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_PRIMARY_FIELDS = frozenset({"start", "end", "source_start", "video_source_start", "video_speed", "crop"})
_LIBRARY_FIELDS = frozenset(CLIP_FIELDS | {"video_source_start"})
_LIBRARY_DEFAULTS = {"speed": 1, "volume_db": 0, "muted": False, "role": "music", "fade_in": 0, "fade_out": 0,
                     "x": 0, "y": 0, "w": 1, "h": 1, "fit": "cover", "motion": "none", "audio_enabled": False}
PUBLIC_BINDING_ERROR = "The saved timeline cannot be addressed safely. Review your clips or restore an earlier edit."


class TimelineBindingError(SourceTrackError):
    pass


def primary_track_binding(project: dict[str, Any], slot: str) -> dict[str, Any]:
    """Identity only: no media lookup or edit-clock materialization."""
    project_id = project.get("id")
    if not isinstance(project_id, str) or not _PROJECT_ID.fullmatch(project_id):
        raise TimelineBindingError("Invalid project identity")
    source = (project.get("sources") or {}).get(slot)
    if slot not in {"A", "B"} or not isinstance(source, dict) or not source:
        raise TimelineBindingError("The primary source is unavailable")
    generation = source.get("generation")
    if generation is not None and generation != "" and (not isinstance(generation, str) or generation == "unversioned" or not _GENERATION.fullmatch(generation)):
        raise TimelineBindingError("Invalid source generation")
    versioned = bool(generation)
    return {"id": f"track:{project_id}:{slot}", "legacy_slot": slot,
            "source_ref": f"primary:{slot}:{generation if versioned else 'unversioned'}",
            "can_edit_by_id": versioned}


def _asset_ref(asset: dict[str, Any]) -> str:
    asset_id = asset.get("id")
    if not isinstance(asset_id, str) or not ASSET_ID_RE.fullmatch(asset_id):
        raise TimelineBindingError("Invalid library source identity")
    return f"asset:{asset_id}"


def _clip_id(clip: dict[str, Any]) -> str:
    value = clip.get("id")
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise TimelineBindingError("Invalid clip identity")
    return value


def build_timeline_bindings(project: dict[str, Any], *, editor_sequence: dict[str, Any] | None = None,
                            input_inventory: RenderInputInventory | None = None) -> dict[str, Any] | None:
    """Public metadata only; supplied snapshots must belong to this response."""
    try:
        return _build(project, editor_sequence, input_inventory)
    except TimelineBindingError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise TimelineBindingError("The timeline identity is invalid") from exc


def _build(project, snapshot, inventory):
    validate_sequence_version(project)
    if not isinstance(project.get("draft"), dict):
        return None
    revision = project.get("revision")
    if type(revision) is not int or revision < 1:
        raise TimelineBindingError("Invalid project revision")
    snapshot = editor_sequence_snapshot(project) if snapshot is None else snapshot
    if not isinstance(snapshot, dict) or "error" in snapshot:
        raise TimelineBindingError("The editor timeline is unavailable")
    # Validate the supplied projected clock without materializing it a second time.
    view = {**project, "manual": {**(project.get("manual") or {}),
                                "sequence": snapshot["sequence"], "source_tracks": snapshot["source_tracks"]}}
    validate_sequence_version(view)
    inventory = compile_render_inputs(project) if inventory is None else inventory
    inventory.validate(project)
    sources, tracks, clips, render_bindings = {}, [], [], []
    by_slot = {}
    for slot in ("A", "B"):
        source = (project.get("sources") or {}).get(slot)
        if not source:
            continue
        track = primary_track_binding(project, slot)
        tracks.append(track)
        by_slot[slot] = track
        descriptor = {"kind": "primary", "legacy_slot": slot,
                      "binding_state": "current_generation" if track["can_edit_by_id"] else "unversioned"}
        if track["can_edit_by_id"]:
            descriptor["generation"] = source["generation"]
        sources[track["source_ref"]] = descriptor
        for clip in _validated(view, slot, snapshot["source_tracks"].get(slot, [])):
            clips.append({"collection": "primary", "track_id": track["id"], "id": clip["id"],
                          "source_ref": track["source_ref"],
                          "state": {key: copy.deepcopy(value) for key, value in clip.items() if key in _PRIMARY_FIELDS}})
    seen_library = set()
    for entry in inventory.entries:
        row = {"category": entry.category, "key": entry.key, "index": entry.index}
        if entry.category == "source":
            row.update(track_id=by_slot[entry.target]["id"], source_ref=by_slot[entry.target]["source_ref"])
        else:
            ref = _asset_ref(entry.media)
            sources[ref] = {"kind": "library", "asset_id": entry.media["id"], "binding_state": "asset_id_only"}
            row["source_ref"] = ref
            if entry.category == "library":
                clip = entry.clip
                if clip.get("asset_id") != entry.media["id"]:
                    raise TimelineBindingError("The library source does not match its clip")
                clip_id = _clip_id(clip)
                if clip_id in seen_library:
                    raise TimelineBindingError("Ambiguous library clip identity")
                seen_library.add(clip_id)
                row["clip_id"] = clip_id
                # Old library rows may omit optional fields. Normalize only on
                # this detached view; field-name whitelists alone would leak
                # unchecked nested data in a corrupt numeric/enum field.
                candidate = {**_LIBRARY_DEFAULTS, "id": clip_id, "asset_id": entry.media["id"],
                             **{key: value for key, value in clip.items() if key in _LIBRARY_FIELDS}}
                safe_clip = validate_media_clip(project, candidate, snapshot["duration"])
                clips.append({"collection": "library", "track_id": None, "id": clip_id, "source_ref": ref,
                              "state": {key: copy.deepcopy(value) for key, value in safe_clip.items() if key in _LIBRARY_FIELDS}})
            elif entry.category == "chroma_background":
                row["target"] = entry.target
            else:
                raise TimelineBindingError("Unsupported input binding")
        render_bindings.append(row)
    return {"version": 1, "revision": revision, "clock": "edit", "selection_scope": "project_revision",
            "id_actions": list(ID_ACTIONS), "sources": sources, "tracks": tracks, "clips": clips,
            "render_bindings": render_bindings}
