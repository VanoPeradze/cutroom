"""Persistent editing protection; locks never change playback or rendering."""
from __future__ import annotations

from typing import Any

from .source_tracks import SourceTrackError, has_sequence, source_sync_offset, source_track_clips


class TrackLockedError(SourceTrackError):
    """A proposed change would modify a currently protected source track."""


def locked_tracks(project: dict[str, Any]) -> tuple[str, ...]:
    locks = (project.get("manual") or {}).get("track_locks") or {}
    return tuple(slot for slot in ("A", "B") if isinstance(locks, dict) and locks.get(slot) is True)


def require_tracks_unlocked(project: dict[str, Any], slots: tuple[str, ...] = ("A", "B")) -> None:
    for slot in locked_tracks(project):
        if slot in slots:
            raise TrackLockedError(f"Track {slot} is locked. Unlock it before changing its clips.")


def _source_identity(source: Any) -> Any:
    mutable = {"preview_relative_path", "thumbnail_names", "preparation", "preparation_error", "audio_profile_ready", "embedded_camera_detected"}
    return {key: value for key, value in source.items() if key not in mutable} if isinstance(source, dict) else source


def _lane_data(container: Any, slot: str) -> Any:
    return container.get(slot) if isinstance(container, dict) else container


def validate_locked_track_changes(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Check the old lock state, even when the candidate also removes a lock.

    Compare clips on their actual clock. A first sequence edit materializes
    virtual clips on both lanes, so compare both projections at that boundary.
    Existing sequences and legacy source tracks retain their clip identities.
    Shared layout and output settings are deliberately outside lane protection.
    """
    slots = locked_tracks(before)
    if not slots:
        return
    old_manual, new_manual = before.get("manual") or {}, after.get("manual") or {}
    old_sequence, new_sequence = has_sequence(before), has_sequence(after)
    old_view, new_view = before, after
    if old_sequence != new_sequence:
        from .sequence import materialize_sequence
        try:
            old_view, _ = materialize_sequence(before)
            new_view, _ = materialize_sequence(after)
        except SourceTrackError:
            require_tracks_unlocked(before)
    for slot in slots:
        changed = False
        old_source, new_source = (before.get("sources") or {}).get(slot), (after.get("sources") or {}).get(slot)
        # Preparing a proxy or refreshing thumbnails is safe; replacing media
        # or changing its duration/stream properties is not.
        changed |= _source_identity(old_source) != _source_identity(new_source)
        changed |= bool(before.get("draft")) != bool(after.get("draft"))
        changed |= source_track_clips(old_view, slot) != source_track_clips(new_view, slot)
        if old_sequence == new_sequence:
            # Preserve even malformed legacy rows that the safe read projection
            # omits. They cannot be silently replaced while their lane is locked.
            changed |= _lane_data(old_manual.get("source_tracks"), slot) != _lane_data(new_manual.get("source_tracks"), slot)
        changed |= _lane_data(old_manual.get("crop"), slot) != _lane_data(new_manual.get("crop"), slot)
        changed |= _lane_data(old_manual.get("chroma_key"), slot) != _lane_data(new_manual.get("chroma_key"), slot)
        if slot == "A":
            changed |= old_manual.get("embedded_camera") != new_manual.get("embedded_camera")
        if slot == "B":
            changed |= source_sync_offset(before) != source_sync_offset(after)
        # Legacy cuts and restore intent remain meaningful when the edit has
        # not yet been materialized, and must not be patched around a lock.
        for key in ("cuts", "keeps", "keep_ranges"):
            changed |= (old_manual.get(key) or []) != (new_manual.get(key) or [])
        if not old_sequence and not new_sequence:
            for key in ("cuts", "keep_ranges", "edit_points"):
                changed |= ((before.get("draft") or {}).get(key) or []) != ((after.get("draft") or {}).get(key) or [])
        if slot not in (new_manual.get("track_locks") or {}):
            changed = True
        if changed:
            require_tracks_unlocked(before, (slot,))
