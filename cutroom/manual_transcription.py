"""First speech transcript for a manual edit, without running the Director."""
from __future__ import annotations

import copy
import math
from pathlib import Path

from .caption_alternatives import EDIT_LAYERS
from .director import _normalize_transcript, _transcription_duration
from .jobs import JobCancelled
from .render import _effective_audio_slot
from .source_tracks import has_sequence, has_source_tracks, source_track_clips
from .transcription import local_cached_fallback_settings, transcribe, transcript_quality_report

LANGUAGES = frozenset({"auto", "he", "en", "ar", "es", "fr", "ru"})
MAX_SECONDS = 4 * 3600


def source_for_manual_transcript(project):
    """Admit only first transcripts for original A audio; cuts stay as saved."""
    draft, analysis = project.get("draft"), project.get("analysis")
    if not isinstance(draft, dict) or draft.get("engine") != "manual" or not isinstance(analysis, dict) or analysis.get("engine") != "manual":
        raise ValueError("Open a manual edit before transcribing its audio.")
    existing = analysis.get("transcript")
    if (not isinstance(existing, dict) or existing.get("segments") != [] or existing.get("words")
            or existing.get("text") or analysis.get("segments")):
        raise ValueError("This edit already has a transcript. Existing lines were not replaced.")
    manual = project.get("manual") or {}
    if (project.get("caption_alternatives") or project.get("_ai_draft_proposal") or analysis.get("review_candidates")
            or manual.get("caption_alternative") or any(manual.get(key) for key in EDIT_LAYERS)):
        raise ValueError("This edit already has caption work or a saved proposal. Nothing was replaced.")
    slot = _effective_audio_slot(project)
    if slot is None:
        raise ValueError("The selected audio source has no sound track to transcribe.")
    if slot != "A":
        raise ValueError("Manual transcription currently supports audio from source A, not the selected source B.")
    if (has_sequence(project) or has_source_tracks(project)) and not source_track_clips(project, "A"):
        raise ValueError("There is no source A audio on this timeline.")
    source = project["sources"]["A"]
    if not source.get("generation"):
        raise ValueError("The original source needs a valid import before it can be transcribed.")
    try:
        duration = _transcription_duration(source, float(source["duration"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        duration = 0
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Manual transcription needs a recording with up to four hours of source audio.")
    return source, duration


def _owned_input(store, project_id, source):
    project_dir = store.project_dir(project_id).resolve()
    relative = source.get("relative_path")
    if not isinstance(relative, str) or not relative:
        raise ValueError("The original source file is unavailable.")
    path = (project_dir / relative).resolve()
    if not path.is_relative_to(project_dir / "media") or not path.is_file():
        raise ValueError("The original source file is unavailable.")
    stat = path.stat()
    return path, (source["generation"], path, stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def _cached_local_settings(settings, language, duration):
    # A caption request is independent of both the Story model and the user's
    # cloud transcription preference. This snapshot never persists credentials,
    # starts setup or downloads a speech model.
    local = copy.deepcopy(settings)
    local.ai.update(transcription_engine="local", cloud_connection={"mode": "local"},
                    whisper_local_files_only=True, whisper_isolate_process=True,
                    whisper_chunk_threshold_seconds=0, download_models_on_setup=False)
    local.ai.pop("cloudflare_connection", None)
    try:
        return local_cached_fallback_settings(local, language, "balanced", duration)
    except RuntimeError as exc:
        raise ValueError("Local transcription needs the installed speech runtime and a cached model for this language. Check Setup > Local models; nothing was downloaded.") from exc


def generate_manual_transcript(context, project_id, store, settings, language, expected_revision):
    context.checkpoint()
    project = store.load(project_id)
    if project["revision"] != expected_revision:
        raise RuntimeError("revision_conflict")
    source, duration = source_for_manual_transcript(project)
    original, identity = _owned_input(store, project_id, source)
    local = _cached_local_settings(settings, language, duration)
    try:
        raw = transcribe(original, local, language=language, performance_mode="balanced", duration=duration,
                         progress=lambda value, message: context.update(.04 + .86 * value, message),
                         cancel_check=context.check_cancelled)
    except JobCancelled:
        raise
    except Exception as exc:
        raise RuntimeError("Local transcription did not finish. Check the source audio and Local models, then retry. Your edit was kept.") from exc
    context.checkpoint()
    coverage = raw.get("coverage") if isinstance(raw, dict) else None
    if not isinstance(coverage, dict) or coverage.get("complete") is not True:
        raise ValueError("Transcription did not cover the full source audio. No partial transcript was saved.")
    transcript, _ = _normalize_transcript(raw, language, duration)
    quality = transcript_quality_report(transcript)
    if "incomplete_transcription" in (quality.get("reasons") or []):
        raise ValueError("Transcription did not cover the full source audio. No partial transcript was saved.")
    if not transcript["segments"]:
        return {"saved": False, "reason": "no_speech", "segment_count": 0}

    def save(current):
        current_source, current_duration = source_for_manual_transcript(current)
        _, current_identity = _owned_input(store, project_id, current_source)
        if current_identity != identity or current_duration != duration:
            raise ValueError("The original recording changed. Transcribe the current source again.")
        # The source-native timestamps flow through existing caption projection,
        # which follows cuts, repeats and trims without changing the timeline.
        current["analysis"].update(transcript=transcript, transcript_quality=quality,
                                   audio_source="A", audio_timeline_offset=0.0)
        context.commit()

    context.checkpoint("Saving the editable transcript")
    saved = store.update(project_id, save, expected_revision=expected_revision)
    context.update(1.0, "Transcript ready")
    return {"saved": True, "segment_count": len(transcript["segments"]), "revision": saved["revision"]}


def captions_out_of_date(project) -> bool:
    """Whether export would refuse captions because they follow another sound."""
    from .render import _validate_caption_timeline
    try:
        _validate_caption_timeline(project)
    except RuntimeError as error:
        return str(error) == "captions_out_of_date"
    return False


def source_for_caption_refresh(project):
    """The routed audio source to transcribe again; the edit itself is never touched."""
    from .render import _sync_offset
    if not isinstance(project.get("draft"), dict):
        raise ValueError("Make an edit before refreshing its captions.")
    if not captions_out_of_date(project):
        raise ValueError("Captions already follow the selected sound.")
    slot = _effective_audio_slot(project)
    if slot is None:
        raise ValueError("The selected audio source has no sound track to transcribe.")
    if (has_sequence(project) or has_source_tracks(project)) and not source_track_clips(project, slot):
        raise ValueError(f"There is no source {slot} audio on this timeline.")
    source = (project.get("sources") or {}).get(slot) or {}
    if not source.get("generation"):
        raise ValueError("The selected source needs a valid import before it can be transcribed.")
    try:
        duration = _transcription_duration(source, float(source["duration"]))
    except (KeyError, TypeError, ValueError, OverflowError):
        duration = 0
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Caption refresh needs a selected sound of up to four hours.")
    # Transcript B timestamps carry the sync offset; caption projection undoes it.
    offset = float(_sync_offset(project)) if slot == "B" else 0.0
    return slot, source, duration, offset


def _shift_transcript(transcript, offset):
    if not offset:
        return transcript
    def moved(row):
        row = {**row}
        for key in ("start", "end"):
            if isinstance(row.get(key), (int, float)):
                row[key] = row[key] + offset
        if isinstance(row.get("words"), list):
            row["words"] = [moved(word) for word in row["words"] if isinstance(word, dict)]
        return row
    return {**transcript, "segments": [moved(row) for row in transcript.get("segments") or [] if isinstance(row, dict)],
            **({"words": [moved(word) for word in transcript["words"] if isinstance(word, dict)]}
               if isinstance(transcript.get("words"), list) else {})}


def refresh_caption_transcript(context, project_id, store, settings, expected_revision):
    """Transcribe the sound the edit plays, so captions match it. Cuts, layout,
    tracks and the timeline stay exactly as saved; only the transcript the
    captions are projected from is replaced."""
    context.checkpoint()
    project = store.load(project_id)
    if project["revision"] != expected_revision:
        raise RuntimeError("revision_conflict")
    slot, source, duration, offset = source_for_caption_refresh(project)
    original, identity = _owned_input(store, project_id, source)
    previous = (project.get("analysis") or {}).get("transcript") or {}
    language = previous.get("language") if previous.get("language") in LANGUAGES else "auto"
    local = _cached_local_settings(settings, language, duration)
    context.update(.02, f"Transcribing the source {slot} sound for captions")
    try:
        raw = transcribe(original, local, language=language, performance_mode="balanced", duration=duration,
                         progress=lambda value, message: context.update(.04 + .86 * value, message),
                         cancel_check=context.check_cancelled)
    except JobCancelled:
        raise
    except Exception as exc:
        raise RuntimeError("Local transcription did not finish. Check the source audio and Local models, then retry. Your edit was kept.") from exc
    context.checkpoint()
    coverage = raw.get("coverage") if isinstance(raw, dict) else None
    if not isinstance(coverage, dict) or coverage.get("complete") is not True:
        raise ValueError("Transcription did not cover the full sound. Nothing was changed.")
    transcript, _ = _normalize_transcript(raw, language, duration)
    quality = transcript_quality_report(transcript)
    if "incomplete_transcription" in (quality.get("reasons") or []):
        raise ValueError("Transcription did not cover the full sound. Nothing was changed.")
    transcript = _shift_transcript(transcript, offset)

    def save(current):
        current_slot, current_source, current_duration, current_offset = source_for_caption_refresh(current)
        _, current_identity = _owned_input(store, project_id, current_source)
        if (current_slot, current_identity, current_duration, current_offset) != (slot, identity, duration, offset):
            raise ValueError("The selected sound changed. Export again to refresh the captions.")
        current.setdefault("analysis", {}).update(transcript=transcript, transcript_quality=quality,
                                                  audio_source=slot, audio_timeline_offset=offset)
        context.commit()

    context.checkpoint("Saving the caption transcript")
    saved = store.update(project_id, save, expected_revision=expected_revision)
    context.update(1.0, "Captions follow the selected sound")
    return {"saved": True, "slot": slot, "segment_count": len(transcript["segments"]), "revision": saved["revision"]}
