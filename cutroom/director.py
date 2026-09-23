from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any, Callable

from .cache_keys import build_analysis_cache_fingerprints, cache_fingerprints_match, stable_fingerprint
from .composition import select_embedded_candidate
from .config import Settings
from .edit_styles import enrich_brief_with_style
from .editing import SOURCE_MIXER_DEFAULT_LAYOUTS, apply_camera_overrides, apply_timeline_overrides
from .audio import analyze_audio, audio_policy, build_audio_actions, constrain_gain_ranges_to_speech, protect_silence_ranges_from_speech
from .intelligence import PACE_LIMITS, StoryPlanningError, build_story_beats, language_from_text, plan_edit
from .jobs import JobCancelled, JobContext
from .media import detect_scenes
from .media_library import validate_media_bounds
from .projects import ProjectStore
from .source_tracks import source_sync_offset
from .sync import MIN_AUTOMATIC_SYNC_CONFIDENCE, synchronize_sources
from .transcription import cuda_available, transcribe, transcript_quality_report
from .cloud_ai import CloudAIError, enabled as cloud_enabled
from .vision import VISION_ANALYSIS_VERSION, analyze_faces_and_embedded_camera, normalized_vision_sample_count
from .utils import clamp, invert_ranges, merge_ranges, range_duration


def _finite_number(value: Any, fallback: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return number if math.isfinite(number) else fallback


def _prepared_vision_is_reusable(
    profile: Any,
    source_generation: str,
    required_samples: int,
) -> bool:
    """Accept upload-time vision only when it represents this source and profile."""

    if (
        not isinstance(profile, dict)
        or not source_generation
        or profile.get("version") != VISION_ANALYSIS_VERSION
        or str(profile.get("source_generation") or "") != source_generation
    ):
        return False
    try:
        sample_count = int(profile.get("sample_count") or 0)
    except (TypeError, ValueError, OverflowError):
        return False
    return sample_count >= required_samples


def _normalize_transcript(
    value: Any,
    requested_language: str | None,
    duration: float,
) -> tuple[dict[str, Any], bool]:
    """Return a bounded transcript shape that downstream editing can trust.

    Whisper normally returns this exact shape, but model wrappers, old plugins and
    interrupted workers can return ``None`` or partially malformed timestamps. A
    bad optional field must not bring down the whole Director or leak NaN into the
    render graph.
    """

    changed = not isinstance(value, dict)
    raw = value if isinstance(value, dict) else {}
    source_duration = max(0.0, _finite_number(duration))
    explicit_language = str(requested_language or "auto").strip().lower()
    raw_language = str(raw.get("language") or "unknown").strip().lower()
    detected_language = str(raw.get("detected_language") or raw_language or "unknown").strip().lower()
    language = explicit_language if explicit_language not in {"", "auto", "unknown"} else raw_language
    if not language:
        language = "unknown"

    segments: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    raw_segments = raw.get("segments")
    if not isinstance(raw_segments, list):
        raw_segments = []
        changed = True
    for raw_segment in raw_segments:
        if not isinstance(raw_segment, dict):
            changed = True
            continue
        start = max(0.0, _finite_number(raw_segment.get("start")))
        end = max(0.0, _finite_number(raw_segment.get("end")))
        if source_duration > 0.0:
            start, end = min(source_duration, start), min(source_duration, end)
        text = str(raw_segment.get("text") or "").strip()
        if not text or end - start < 0.01:
            changed = True
            continue
        identifier = str(raw_segment.get("id") or "").strip()
        if not identifier or identifier in identifiers:
            identifier = f"s{len(segments) + 1:04d}"
            changed = True
        identifiers.add(identifier)
        words: list[dict[str, Any]] = []
        raw_words = raw_segment.get("words")
        if raw_words is not None and not isinstance(raw_words, list):
            changed = True
            raw_words = []
        for raw_word in raw_words or []:
            if not isinstance(raw_word, dict):
                changed = True
                continue
            word_start = max(start, _finite_number(raw_word.get("start"), start))
            word_end = min(end, _finite_number(raw_word.get("end"), word_start))
            word_text = str(raw_word.get("word") or "").strip()
            if not word_text or word_end - word_start < 0.005:
                changed = True
                continue
            word = {
                "start": round(word_start, 3),
                "end": round(word_end, 3),
                "word": word_text,
            }
            probability = raw_word.get("probability")
            if probability is not None:
                probability_value = _finite_number(probability, -1.0)
                if 0.0 <= probability_value <= 1.0:
                    word["probability"] = round(probability_value, 4)
            words.append(word)
        segment = {
            "id": identifier,
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            "normalized": str(raw_segment.get("normalized") or text).strip(),
            "words": words,
        }
        for key in ("avg_logprob", "no_speech_prob"):
            if raw_segment.get(key) is not None:
                number = _finite_number(raw_segment.get(key), math.nan)
                if math.isfinite(number):
                    segment[key] = round(number, 4)
                else:
                    changed = True
        segments.append(segment)
    segments.sort(key=lambda item: (float(item["start"]), float(item["end"])))

    words = [dict(word) for segment in segments for word in segment.get("words", [])]
    language_probability = max(0.0, min(1.0, _finite_number(raw.get("language_probability"), 0.0)))
    detected_language_probability = max(0.0, min(
        1.0,
        _finite_number(raw.get("detected_language_probability"), language_probability),
    ))
    detection = copy.deepcopy(raw.get("language_detection")) if isinstance(raw.get("language_detection"), dict) else {}
    detection.setdefault(
        "source",
        "explicit" if explicit_language not in {"", "auto", "unknown"} else ("whisper" if segments else "none"),
    )
    detection.setdefault(
        "requested_language",
        explicit_language if explicit_language not in {"", "auto", "unknown"} else "auto",
    )
    detection.setdefault("ambiguous", detected_language == "unknown" or detected_language_probability < 0.62)
    normalized = {
        **raw,
        "language": language,
        "language_probability": language_probability,
        "detected_language": detected_language,
        "detected_language_probability": detected_language_probability,
        "language_detection": detection,
        "duration": round(source_duration, 3),
        "segments": segments,
        "words": words,
        "text": " ".join(str(segment["text"]) for segment in segments),
    }
    if normalized["segments"] != raw.get("segments") or normalized["text"] != str(raw.get("text") or "").strip():
        changed = True
    return normalized, changed


def _shift_range_to_timeline(item: dict[str, Any], offset: float, duration: float) -> dict[str, Any] | None:
    start = max(0.0, _finite_number(item.get("start")) + offset)
    end = min(duration, _finite_number(item.get("end")) + offset)
    if end - start < 0.005:
        return None
    shifted = dict(item)
    shifted.update({"start": round(start, 3), "end": round(end, 3)})
    if "duration" in shifted:
        shifted["duration"] = round(end - start, 3)
    return shifted


def _map_transcript_to_timeline(transcript: dict[str, Any], offset: float, duration: float) -> dict[str, Any]:
    """Map source-B-local speech timestamps onto source A's edit timeline."""

    mapped = copy.deepcopy(transcript)
    segments: list[dict[str, Any]] = []
    for segment in transcript.get("segments") or []:
        shifted = _shift_range_to_timeline(segment, offset, duration)
        if shifted is None:
            continue
        shifted_words = []
        for word in segment.get("words") or []:
            shifted_word = _shift_range_to_timeline(word, offset, duration)
            if shifted_word is not None:
                shifted_words.append(shifted_word)
        shifted["words"] = shifted_words
        segments.append(shifted)
    mapped["duration"] = round(max(0.0, duration), 3)
    mapped["segments"] = segments
    mapped["words"] = [dict(word) for segment in segments for word in segment.get("words", [])]
    mapped["text"] = " ".join(str(segment.get("text") or "").strip() for segment in segments).strip()
    mapped["timeline_offset"] = round(offset, 3)
    if isinstance(mapped.get("coverage"), dict):
        # Processing/VAD evidence stays in B-local time. Do not reinterpret a
        # shorter camera recording as a failed transcription of the whole A file.
        mapped["coverage"].update({"timeline_offset": round(offset, 3), "timeline_duration": duration})
    return mapped


def _map_audio_profile_to_timeline(profile: dict[str, Any], offset: float, duration: float) -> dict[str, Any]:
    """Map measured B audio evidence to A without labelling uncovered gaps silent."""

    mapped = copy.deepcopy(profile)
    mapped["duration"] = round(max(0.0, duration), 3)
    mapped["timeline_offset"] = round(offset, 3)
    ranges: dict[str, list[dict[str, Any]]] = {}
    for kind, items in (profile.get("ranges") or {}).items():
        ranges[kind] = [
            shifted
            for item in (items if isinstance(items, list) else [])
            if isinstance(item, dict)
            for shifted in [_shift_range_to_timeline(item, offset, duration)]
            if shifted is not None
        ]
    mapped["ranges"] = ranges
    waveform = []
    for item in profile.get("waveform") or []:
        if not isinstance(item, dict):
            continue
        shifted = _shift_range_to_timeline(item, offset, duration)
        if shifted is not None:
            waveform.append(shifted)
    mapped["waveform"] = waveform
    return mapped


def _analysis_audio_slot(project: dict[str, Any]) -> str:
    """Resolve the real audio source with the same fallback contract as export."""

    sources = project.get("sources") or {}
    raw = (project.get("manual", {}).get("source_mixer") or {}).get("audio_slot")
    requested = str(raw or project.get("settings", {}).get("audio_source") or "A").upper()
    if requested in {"A", "B"} and (sources.get(requested) or {}).get("has_audio"):
        return requested
    if (sources.get("A") or {}).get("has_audio"):
        return "A"
    if (sources.get("B") or {}).get("has_audio"):
        return "B"
    return "A"


def _manual_sync_offset(project: dict[str, Any]) -> float | None:
    value = (project.get("manual", {}).get("source_mixer") or {}).get("sync_offset")
    if value is None:
        return None
    number = _finite_number(value, math.nan)
    return number if math.isfinite(number) and abs(number) <= 600.0 else None


def _safe_automatic_sync(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Neutralize weak automatic matches, including cached results from older releases."""

    if not isinstance(value, dict):
        return value
    result = copy.deepcopy(value)
    if str(result.get("method") or "") == "manual":
        return result
    confidence = _finite_number(result.get("confidence"), 0.0)
    if confidence >= MIN_AUTOMATIC_SYNC_CONFIDENCE:
        result["reliable"] = True
        return result
    measured_offset = _finite_number(result.get("measured_offset"), _finite_number(result.get("offset"), 0.0))
    result["measured_offset"] = round(measured_offset, 3)
    result["offset"] = 0.0
    result["reliable"] = False
    return result



def _transcribe_safely(
    source: Path,
    settings: Settings,
    language: str | None,
    progress: Callable[[float, str], None] | None = None,
    performance_mode: str = "auto",
    duration: float = 0.0,
    cancel_check: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Transcribe when possible and return explicit evidence when it fails.

    Audio-only workflows such as YouTube dead-air cleanup and non-verbal Stream
    Highlights may continue without a transcript. Semantic workflows either retry
    with a genuinely stronger profile or return an explicitly labelled evidence-
    based fallback; they never pretend that a fallback understood missing words.
    """
    try:
        try:
            result = transcribe(
                source, settings, language=language, progress=progress,
                performance_mode=performance_mode, duration=duration,
                cancel_check=cancel_check,
            )
        except TypeError as exc:
            # Keep compatibility with older test hooks/extensions that implement
            # the pre-v5.1 transcription signature.
            if not any(name in str(exc) for name in ("performance_mode", "duration", "cancel_check")):
                raise
            result = transcribe(source, settings, language=language, progress=progress)
        normalized, changed = _normalize_transcript(result, language, duration)
        warning = "Transcription returned incomplete data and was safely normalized." if changed else None
        return normalized, warning
    except (JobCancelled, CloudAIError):
        raise
    except Exception as exc:  # Director must remain usable without transcription.
        fallback, _ = _normalize_transcript({}, language, duration)
        fallback.update({
            "model": "unavailable",
            "device": "none",
            "compute_type": "none",
        })
        if isinstance(getattr(exc, "coverage", None), dict):
            fallback["coverage"] = copy.deepcopy(exc.coverage)
        return fallback, f"{type(exc).__name__}: {exc}"


def _assert_transcript_complete(quality: dict[str, Any]) -> None:
    reasons = set(quality.get("reasons") or [])
    if "incomplete_transcription" in reasons:
        raise StoryPlanningError(
            "Transcription did not finish processing all of the audio. No story was built from partial speech. "
            "Your original footage is safe. Retry transcription with the exact spoken language; "
            "Quality mode keeps the requested model even when it needs to run on CPU."
        )
    if "uncovered_detected_speech" in reasons:
        raise StoryPlanningError(
            "Speech was detected in sections that produced very little transcript. "
            "Choose the exact spoken language and Quality mode, then retry before building the story. "
            "The speech detector is an estimate; background voices or game audio can also need review."
        )


def _edit_quality_review(
    quality: dict[str, Any], hierarchy: dict[str, Any] | None,
    segments: list[dict[str, Any]], keep_ranges: list[dict[str, float]], duration: float,
) -> dict[str, Any]:
    """Expose evidence limitations, never equate a completed job with a good edit."""
    warnings: list[dict[str, str]] = []
    if "unverified_transcript_coverage" in (quality.get("warnings") or []):
        warnings.append({"type": "transcript_coverage", "message":
            "This older transcript has no complete processing record and covers a limited part of the source. "
            "Review the missing sections or run transcription again."})
    if hierarchy:
        recovery = hierarchy.get("summary_recovery") or {}
        critic = hierarchy.get("critic") or {}
        if recovery.get("extractive_chapter_ids"):
            warnings.append({"type": "story_review", "message":
                "Some chapter summaries used transcript excerpts after a model response failed. Review context and the ending."})
        if critic.get("verdict") != "pass":
            warnings.append({"type": "story_review", "message":
                "The automatic continuity check did not give this edit a clear pass. Review it before exporting."})

    def bins(ranges):
        if duration <= 0:
            return []
        return [index for index in range(10) if any(
            float(row.get("end", 0)) > duration * index / 10
            and float(row.get("start", 0)) < duration * (index + 1) / 10 for row in ranges
        )]

    recognized, selected = bins(segments), bins(keep_ranges)
    if duration >= 180 and len(recognized) >= 5 and 0 < len(selected) <= 2:
        warnings.append({"type": "selection_coverage", "message":
            "The selected moments come from a small part of the recording. This can suit one complete story; "
            "review the rest of the source if you wanted a broader summary."})
    return {"needs_review": bool(warnings), "warnings": warnings,
            "recognized_source_sections": recognized, "selected_source_sections": selected,
            "section_count": 10, "source_duration": duration,
            "transcription_coverage": quality.get("coverage_status", "unverified")}


def _transcript_upgrade_request(
    performance_mode: str,
    spoken_language: str,
    transcript: dict[str, Any],
    quality: dict[str, Any],
) -> tuple[str | None, str]:
    """Choose one real ASR upgrade without trusting a weak auto-language guess."""

    requested_mode = str(performance_mode or "auto")
    upgrade_mode = {
        "auto": "quality",      # Auto on CUDA already resolved to Balanced.
        "lite": "balanced",
        "balanced": "quality",
        "quality": None,
    }.get(requested_mode, "quality")
    explicit_language = str(spoken_language or "auto")
    if explicit_language not in {"", "auto", "unknown"}:
        return upgrade_mode, explicit_language
    detected_language = str(transcript.get("language") or "auto")
    language_probability = quality.get("language_probability")
    trusted_detection = (
        detected_language not in {"", "auto", "unknown"}
        and language_probability is not None
        and float(language_probability) >= 0.80
        and "too_little_speech" not in set(quality.get("reasons") or [])
    )
    return upgrade_mode, detected_language if trusted_detection else "auto"


def _clearly_sparse_transcript(quality: dict[str, Any]) -> bool:
    """Identify a long recording where ASR found effectively no speech."""

    return bool(
        "too_little_speech" in set(quality.get("reasons") or [])
        and (
            int(quality.get("segment_count") or 0) == 0
            or float(quality.get("speech_ratio") or 0.0) < 0.01
        )
    )


def _source_path(store: ProjectStore, project: dict[str, Any], slot: str) -> Path:
    source = project.get("sources", {}).get(slot)
    if not source:
        raise ValueError(f"Source {slot} is missing")
    path = store.project_dir(project["id"]) / source["relative_path"]
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _cut_candidates(
    segments: list[dict[str, Any]],
    decision: dict[str, Any],
    silences_or_pace: list[dict[str, float]] | str,
    pace: str | None = None,
) -> list[dict[str, Any]]:
    """Build semantic candidates only from transcript evidence.

    Acoustic silence cuts are produced separately by the audio policy engine.
    This prevents the language model from inventing sound-based cuts.
    """
    legacy_silences = silences_or_pace if isinstance(silences_or_pace, list) else []
    pace = str(pace or silences_or_pace or "balanced")
    by_id = {segment["id"]: segment for segment in segments}
    candidates: list[dict[str, Any]] = []
    for segment_id in decision.get("remove_ids", []):
        segment = by_id.get(segment_id)
        if not segment:
            continue
        filler_ratio = float(segment.get("filler_ratio", 0.0))
        repeat_score = float(segment.get("repeat_score", 0.0))
        false_start = bool(segment.get("false_start"))
        if false_start:
            reason, priority = "retake", 1.10
        elif repeat_score >= 0.70:
            reason, priority = "repetition", 0.95 + repeat_score * 0.25
        elif filler_ratio >= (0.22 if pace != "gentle" else 0.32):
            reason, priority = "filler", 0.82 + filler_ratio * 0.20
        else:
            # Pure semantic low-value cuts are only advisory and low-priority.
            reason, priority = "low_value", 0.30 + (1.0 - float(segment.get("editorial_score", 0.5))) * 0.35
        candidates.append({
            "start": segment["start"], "end": segment["end"], "reason": reason,
            "priority": priority, "segment_ids": [segment_id],
            "evidence": {
                "source": "transcript", "segment_id": segment_id,
                "repeat_score": round(repeat_score, 3),
                "filler_ratio": round(filler_ratio, 3),
                "false_start": false_start,
            },
        })
    if pace in {"balanced", "dynamic"}:
        for segment in segments:
            words = segment.get("words") or []
            if len(words) < 2:
                continue
            first = words[0]
            fillers = {item.strip().lower() for item in segment.get("fillers", [])}
            if first.get("word", "").strip().lower() in fillers:
                next_start = float(words[1]["start"])
                end = min(next_start - 0.03, float(first["end"]) + 0.10)
                if end - float(first["start"]) >= 0.12:
                    candidates.append({
                        "start": first["start"], "end": end, "reason": "filler", "priority": 0.78,
                        "segment_ids": [segment["id"]],
                        "evidence": {"source": "word_timing", "segment_id": segment["id"], "word": first.get("word")},
                    })
    # Backward-compatible helper behavior for older tests/extensions. The v5.1
    # Director itself supplies acoustic cuts from build_audio_actions().
    for silence in legacy_silences:
        start, end = float(silence.get("start", 0)), float(silence.get("end", 0))
        pad = float(PACE_LIMITS.get(pace, PACE_LIMITS["balanced"])["silence_pad"])
        if end - start > pad * 2 + 0.16:
            candidates.append({"start": start + pad, "end": end - pad, "reason": "silence", "priority": 0.9, "segment_ids": [], "evidence": {"source": "legacy_audio"}})
    return candidates


def _bounded_cuts(
    candidates: list[dict[str, Any]],
    duration: float,
    pace: str,
    goal: str,
    target_duration: float,
    manual_cuts: list[dict[str, Any]],
) -> tuple[list[dict[str, float]], dict[str, int]]:
    max_remove_ratio = float(PACE_LIMITS.get(pace, PACE_LIMITS["balanced"])["max_remove"])
    if goal == "short" and duration > target_duration:
        required = 1.0 - target_duration / max(duration, 0.001)
        max_remove_ratio = min(0.985, max(max_remove_ratio, required + 0.005))
    budget = max(0.0, duration * max_remove_ratio)
    selected: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for cut in sorted(candidates, key=lambda item: (float(item.get("priority", 0)), float(item["end"]) - float(item["start"])), reverse=True):
        bounded = {**cut, "start": clamp(float(cut["start"]), 0.0, duration), "end": clamp(float(cut["end"]), 0.0, duration)}
        if bounded["end"] <= bounded["start"]:
            continue
        # The first detected silence is not exempt from the safety budget.
        # Measure the actual union, including merged gaps, rather than counting
        # overlapping candidates twice. Explicit manual cuts remain authoritative.
        proposed = merge_ranges([*selected, bounded], gap=0.12)
        if range_duration(proposed) > budget + 0.001:
            continue
        selected.append(bounded)
        reason = str(cut.get("reason", "other"))
        counts[reason] = counts.get(reason, 0) + 1
    for manual in manual_cuts:
        selected.append({"start": manual.get("start", 0), "end": manual.get("end", 0), "reason": "manual"})
        counts["manual"] = counts.get("manual", 0) + 1
    merged = merge_ranges(selected, gap=0.12)
    return merged, counts


def _short_cleanup_cuts_with_floor(
    story_cuts: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    manual_cuts: list[dict[str, Any]],
    duration: float,
    target_duration: float,
) -> tuple[list[dict[str, float]], dict[str, int]]:
    """Apply cleanup inside a selected Short without making it needlessly short.

    Story selection decides *what* belongs in the Short. Audio/retake cleanup then
    improves those passages, but it is not allowed to eat far below the requested
    duration merely because many repetitive/filler candidates exist. Manual cuts
    remain mandatory because they express an explicit user choice.
    """
    target = max(8.0, min(float(duration), float(target_duration)))
    floor_ratio = 0.92 if target <= 90.0 else 0.94 if target <= 210.0 else 0.95
    target_floor = target * floor_ratio
    selected: list[dict[str, Any]] = [*story_cuts]
    counts: dict[str, int] = {}
    for manual in manual_cuts:
        selected.append({
            "start": manual.get("start", 0),
            "end": manual.get("end", 0),
            "reason": "manual",
        })
        counts["manual"] = counts.get("manual", 0) + 1
    merged = merge_ranges(selected, gap=0.10)
    output = range_duration(invert_ranges(merged, duration))

    ranked = sorted(
        candidates,
        key=lambda item: (
            float(item.get("priority", 0)),
            float(item.get("end", 0)) - float(item.get("start", 0)),
        ),
        reverse=True,
    )
    for cut in ranked:
        candidate = merge_ranges([*merged, cut], gap=0.10)
        new_output = range_duration(invert_ranges(candidate, duration))
        if new_output >= output - 0.02:
            continue
        # If explicit manual edits already pushed the result below the floor, do
        # not make it shorter still. Otherwise keep enough room for a near-target
        # result and let _enforce_short_target do the final semantic trim.
        if output >= target_floor and new_output < target_floor:
            continue
        if output < target_floor:
            break
        merged = candidate
        output = new_output
        reason = str(cut.get("reason", "other"))
        counts[reason] = counts.get(reason, 0) + 1
    return merged, counts


def _enforce_short_target(
    cuts: list[dict[str, float]],
    segments: list[dict[str, Any]],
    decision: dict[str, Any],
    duration: float,
    target_duration: float,
) -> tuple[list[dict[str, float]], int]:
    """Make the requested Short duration a real upper bound.

    Semantic/audio cuts are tried first. If the draft is still too long, remove the
    least valuable remaining transcript segments at real Whisper boundaries. The
    fallback always samples the whole recording; it never satisfies a target by
    truncating the source at the first N seconds.
    """
    target = max(8.0, min(float(duration), float(target_duration)))
    merged = merge_ranges(cuts, gap=0.10)
    output = range_duration(invert_ranges(merged, duration))
    if output <= target + 0.05:
        return merged, 0

    protected = {str(decision.get("opening_id") or ""), str(decision.get("closing_id") or "")}
    protected.discard("")
    protected.update(str(item) for item in (decision.get("highlight_ids") or [])[:2])
    keep_ids = {str(item) for item in (decision.get("keep_ids") or [])}

    # Allocate every non-speech gap to its two neighboring transcript segments.
    # If a segment is rejected for the duration budget, removing its half of each
    # adjacent gap prevents the inverted-looking result where CUTROOM cuts the
    # spoken line but keeps a standalone island of dead/game audio around it.
    ordered_segments = sorted(
        (item for item in segments if float(item.get("end", 0.0)) > float(item.get("start", 0.0))),
        key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0))),
    )
    removal_bounds: dict[str, tuple[float, float]] = {}
    for index, segment in enumerate(ordered_segments):
        start, end = float(segment.get("start", 0.0)), float(segment.get("end", 0.0))
        expanded_start, expanded_end = start, end
        if index > 0:
            previous_end = float(ordered_segments[index - 1].get("end", start))
            if previous_end < start:
                expanded_start = (previous_end + start) / 2.0
        else:
            expanded_start = 0.0
        if index + 1 < len(ordered_segments):
            next_start = float(ordered_segments[index + 1].get("start", end))
            if next_start > end:
                expanded_end = (end + next_start) / 2.0
        else:
            expanded_end = duration
        removal_bounds[str(segment.get("id") or index)] = (
            max(0.0, expanded_start),
            min(float(duration), expanded_end),
        )

    def already_removed(segment: dict[str, Any]) -> bool:
        start, end = float(segment.get("start", 0)), float(segment.get("end", 0))
        if end <= start:
            return True
        covered = sum(max(0.0, min(end, float(cut["end"])) - max(start, float(cut["start"]))) for cut in merged)
        return covered >= (end - start) * 0.80

    candidates: list[tuple[float, dict[str, Any]]] = []
    for segment in segments:
        if already_removed(segment):
            continue
        score = float(segment.get("editorial_score", 0.5))
        filler = float(segment.get("filler_ratio", 0.0))
        repeat = float(segment.get("repeat_score", 0.0))
        removal_value = (1.0 - score) + filler * 0.45 + repeat * 0.35
        if segment.get("id") not in keep_ids:
            removal_value += 0.35
        if segment.get("false_start"):
            removal_value += 0.45
        if str(segment.get("id")) in protected:
            removal_value -= 1.20
        candidates.append((removal_value, segment))

    removed_for_target = 0
    # First pass preserves the hook/top highlights. A second pass may use them only
    # if there is no other way to honor the user's explicit duration request.
    for allow_protected in (False, True):
        for _, segment in sorted(candidates, key=lambda item: item[0], reverse=True):
            if output <= target + 0.05:
                break
            identifier = str(segment.get("id"))
            if not allow_protected and identifier in protected:
                continue
            start, end = removal_bounds.get(
                str(segment.get("id") or ""),
                (float(segment.get("start", 0)), float(segment.get("end", 0))),
            )
            if end - start < 0.10:
                continue
            candidate = merge_ranges([*merged, {"start": start, "end": end}], gap=0.10)
            new_output = range_duration(invert_ranges(candidate, duration))
            if new_output >= output - 0.03:
                continue
            merged = candidate
            output = new_output
            removed_for_target += 1
        if output <= target + 0.05:
            break

    # Never satisfy a Short target by truncating the tail. If transcript-level
    # pruning still leaves too much material, keep distributed windows from the
    # whole recording so the result remains a trailer/summary rather than the first
    # N seconds of the upload.
    if output > target + 0.05:
        distributed_keep = _fallback_short_story_ranges(duration, target, [])
        distributed_cuts = invert_ranges(distributed_keep, duration)
        merged = merge_ranges([*merged, *distributed_cuts], gap=0.10)
        removed_for_target += len(distributed_cuts)
        output = range_duration(invert_ranges(merged, duration))
        # The distributed windows are close to target but may retain tiny gaps.
        if output > target + 0.05:
            keep = invert_ranges(merged, duration)
            # Drop the shortest/least useful complete keep windows first; do not
            # crop the final passage merely because it happens to be last.
            for item in sorted(keep, key=lambda value: float(value["end"]) - float(value["start"])):
                if output <= target + 0.05:
                    break
                merged = merge_ranges([*merged, item], gap=0.10)
                output = range_duration(invert_ranges(merged, duration))
                removed_for_target += 1
    return merged, removed_for_target


def _short_segment_value(segment: dict[str, Any], decision: dict[str, Any]) -> float:
    identifier = str(segment.get("id") or "")
    score = float(segment.get("editorial_score", 0.5))
    score -= float(segment.get("filler_ratio", 0.0)) * 0.45
    score -= float(segment.get("repeat_score", 0.0)) * 0.38
    if segment.get("false_start"):
        score -= 0.55
    if identifier == str(decision.get("opening_id") or ""):
        score += 1.10
    if identifier == str(decision.get("closing_id") or ""):
        score += 0.48
    if identifier in {str(item) for item in decision.get("highlight_ids", [])}:
        score += 0.82
    if identifier in {str(item) for item in decision.get("keep_ids", [])}:
        score += 0.25
    return score


SELECTION_STRATEGY_VERSION = "complete-style-moments-v3"


def _selection_unit(selection_seed: Any, *parts: Any) -> float:
    """Return a stable pseudo-random unit value without global RNG state.

    Selection should vary only when the user explicitly asks for another cut.
    Hash-based tie breaking makes a saved Draft reproducible across reloads and
    platforms while still allowing a new variant to choose different near-ties.
    """

    digest = stable_fingerprint(
        "director-selection-choice",
        {"seed": selection_seed if selection_seed is not None else "base", "parts": parts},
    )
    return int(digest[:13], 16) / float(0xFFFFFFFFFFFFF)


def _highlight_clip_count(target: float) -> int:
    preferred = 6 if target <= 75.0 else 9 if target <= 210.0 else 12
    # Very short targets still need complete, watchable moments rather than six
    # one-second flashes.
    return max(1, min(preferred, int(max(1.0, target) // 4.0)))


def _varied_highlight_lengths(
    centers: list[float],
    target: float,
    selection_seed: Any,
) -> list[float]:
    """Allocate the target across clips with bounded, deterministic cadence."""

    if not centers:
        return []
    if len(centers) == 1:
        return [target]
    # A 0.65..1.35 weight range is noticeable enough to avoid a robotic cadence,
    # yet bounded enough that every selected event still has useful screen time.
    weights = [
        0.65 + 0.70 * _selection_unit(selection_seed, "length", round(center, 3), index)
        for index, center in enumerate(centers)
    ]
    scale = target / max(0.001, sum(weights))
    lengths = [max(3.0, weight * scale) for weight in weights]
    # The minimum can add a small amount on very short targets. Renormalize, then
    # put floating-point residue on the final clip so the contract stays exact.
    normalizer = target / max(0.001, sum(lengths))
    lengths = [max(0.25, length * normalizer) for length in lengths]
    lengths[-1] += target - sum(lengths)
    return lengths


def _fallback_short_story_ranges(
    duration: float,
    target_duration: float,
    scene_points: list[float] | None = None,
    *,
    selection_seed: Any = None,
) -> list[dict[str, float]]:
    """Spread a no-transcript Short across the whole source instead of truncating the head."""
    target = min(float(duration), max(8.0, float(target_duration)))
    if duration <= target + 0.05:
        return [{"start": 0.0, "end": round(duration, 3)}]
    preferred_count = 4 if target <= 75 else 7 if target <= 210 else 10
    clip_count = max(1, min(preferred_count, int(max(1.0, target) // 4.0)))
    raw_budget = min(duration, target * (1.12 if target <= 90 else 1.07))
    scenes = sorted(float(point) for point in (scene_points or []) if 0 < float(point) < duration)
    centers: list[float] = []
    for index in range(clip_count):
        bucket_start = duration * index / clip_count
        bucket_end = duration * (index + 1) / clip_count
        # Move within the middle half of the bucket. This preserves whole-source
        # coverage while producing a genuinely different fallback variant.
        position = 0.25 + 0.50 * _selection_unit(selection_seed, "fallback-center", index)
        center = bucket_start + (bucket_end - bucket_start) * position
        if scenes:
            nearby = min(scenes, key=lambda point: abs(point - center))
            if abs(nearby - center) <= duration / (clip_count * 2.0):
                center = nearby
        centers.append(center)
    lengths = _varied_highlight_lengths(centers, raw_budget, selection_seed)
    ranges: list[dict[str, float]] = []
    for center, clip_length in zip(centers, lengths):
        start = max(0.0, min(duration - clip_length, center - clip_length / 2))
        end = min(duration, start + clip_length)
        ranges.append({"start": round(start, 3), "end": round(end, 3)})
    return merge_ranges(ranges, gap=0.40)


def _select_audio_highlight_ranges(
    profile: dict[str, Any],
    duration: float,
    target_duration: float,
    scene_points: list[float] | None = None,
    *,
    selection_seed: Any = None,
    pace: str = "balanced",
    selection_policy: dict[str, Any] | None = None,
) -> list[dict[str, float]]:
    """Build a real non-verbal highlight reel from measured audio activity.

    Stream recordings do not always contain commentary. In that case Whisper is
    correct to return no speech, but a Highlights edit can still use real evidence:
    sustained RMS energy, short peaks and timeline diversity. This deliberately
    avoids claiming that Story AI understood words that were never present.
    """
    target = min(float(duration), max(8.0, float(target_duration)))
    if duration <= target + 0.05:
        return [{"start": 0.0, "end": round(duration, 3)}]
    waveform = [
        item for item in (profile.get("waveform") or [])
        if isinstance(item, dict) and float(item.get("end", 0.0)) > float(item.get("start", 0.0))
    ]
    waveform.sort(key=lambda item: (float(item.get("start", 0.0)), float(item.get("end", 0.0))))
    if not waveform:
        return _fallback_short_story_ranges(
            duration, target, scene_points, selection_seed=selection_seed,
        )

    rms_values = sorted(float(item.get("rms_dbfs", -120.0)) for item in waveform)
    peak_values = sorted(float(item.get("peak_dbfs", -120.0)) for item in waveform)

    def percentile(values: list[float], ratio: float) -> float:
        index = min(len(values) - 1, max(0, int(round((len(values) - 1) * ratio))))
        return values[index]

    rms_floor, rms_high = percentile(rms_values, 0.25), percentile(rms_values, 0.90)
    peak_floor, peak_high = percentile(peak_values, 0.25), percentile(peak_values, 0.92)
    rms_span, peak_span = max(6.0, rms_high - rms_floor), max(6.0, peak_high - peak_floor)

    def frame_energy(item: dict[str, Any]) -> float:
        rms = clamp((float(item.get("rms_dbfs", -120.0)) - rms_floor) / rms_span, 0.0, 1.35)
        peak = clamp((float(item.get("peak_dbfs", -120.0)) - peak_floor) / peak_span, 0.0, 1.35)
        return rms * 0.72 + peak * 0.28

    style_limit = (selection_policy or {}).get("max_moments")
    if style_limit:
        before = max(0.0, _finite_number(selection_policy.get("pre_roll_seconds")))
        after = max(0.0, _finite_number(selection_policy.get("post_roll_seconds")))
        threshold = max(0.35, max(frame_energy(row) for row in waveform) * 0.55)
        active = [row for row in waveform if frame_energy(row) >= threshold]
        events = merge_ranges(active, gap=min(2.0, before))
        event_candidates: list[dict[str, float]] = []
        for event in events:
            frames = [row for row in active if row["start"] < event["end"] and row["end"] > event["start"]]
            start, end = max(0.0, event["start"] - before), min(duration, event["end"] + after)
            if end - start > target:
                # Long sustained activity can exceed the user's duration. This
                # is a measured activity window, not a detected complete fight.
                peak = max(frames, key=frame_energy)
                center = (peak["start"] + peak["end"]) / 2.0
                start = max(start, min(end - target, center - target / 2.0))
                end = start + target
            energies = [frame_energy(row) for row in frames]
            score = max(energies) * 0.4 + sum(energies) / len(energies) * 0.6
            event_candidates.append({"start": start, "end": end, "score": score})
        event_keep: list[dict[str, float]] = []
        for event in sorted(event_candidates, key=lambda row: (-row["score"], row["start"])):
            candidate = merge_ranges([*event_keep, event], gap=0.0)
            if range_duration(candidate) > target + 0.05:
                continue
            event_keep = candidate
            if len(event_keep) >= max(1, int(style_limit)):
                break
        if event_keep:
            return event_keep

    clip_count = _highlight_clip_count(target)
    if pace == "dynamic":
        clip_count = min(max(1, int(target // 4.0)), clip_count + 2)
    elif pace == "gentle":
        clip_count = max(1, clip_count - 2)
    if style_limit:
        # Without reliable speech these are audio-backed windows, not identified
        # fights or punchlines. Still honor a style's preference for continuity.
        clip_count = min(clip_count, max(1, int(style_limit)))
    clip_length = target / clip_count
    scored: list[dict[str, float]] = []
    # The waveform is already capped at 900 bins. Scanning all of it avoids the
    # rigid every-Nth-bin lattice that used to create repeated 17.2-second gaps on
    # long recordings.
    for item in waveform:
        center = (float(item["start"]) + float(item["end"])) / 2.0
        left, right = center - clip_length / 2.0, center + clip_length / 2.0
        nearby_frames = [
            frame for frame in waveform
            if float(frame["end"]) > left and float(frame["start"]) < right
        ]
        if not nearby_frames:
            continue
        nearby = [frame_energy(frame) for frame in nearby_frames]
        strongest = sorted(nearby, reverse=True)[:max(1, len(nearby) // 3)]
        sustained = sum(strongest) / len(strongest)
        score = sustained * 0.78 + max(nearby) * 0.22
        strongest_frame = max(nearby_frames, key=frame_energy)
        evidence_center = (float(strongest_frame["start"]) + float(strongest_frame["end"])) / 2.0
        scored.append({"center": evidence_center, "score": score})

    if not scored:
        return _fallback_short_story_ranges(
            duration, target, scene_points, selection_seed=selection_seed,
        )

    score_values = sorted(float(item["score"]) for item in scored)
    best_score = score_values[-1]
    # Diversity is allowed only among credible events. It may not promote a quiet
    # baseline merely to fill an empty part of the timeline.
    quality_floor = max(percentile(score_values, 0.55), best_score - 0.38)
    quality_pool = [item for item in scored if float(item["score"]) >= quality_floor]
    if len(quality_pool) < clip_count:
        quality_floor = max(percentile(score_values, 0.40), best_score - 0.55)
        quality_pool = [item for item in scored if float(item["score"]) >= quality_floor]

    selected: list[dict[str, float]] = []
    represented_buckets: set[int] = set()
    bucket_counts: dict[int, int] = {}
    hard_gap = max(clip_length * 1.25, min(60.0, duration / max(1.0, clip_count * 14.0)))
    preferred_gap = max(clip_length * 2.2, min(120.0, duration / max(1.0, clip_count * 8.0)))
    available_buckets = {
        min(clip_count - 1, int(float(item["center"]) / max(duration, 0.001) * clip_count))
        for item in quality_pool
    }
    coverage_goal = min(len(available_buckets), clip_count, max(1, math.ceil(clip_count * 0.70)))
    bucket_cap = 2 if len(available_buckets) >= max(2, math.ceil(clip_count * 0.55)) else clip_count
    remaining = list(quality_pool)
    while remaining and len(selected) < clip_count:
        coverage_pass = len(represented_buckets) < coverage_goal
        eligible: list[tuple[float, dict[str, float], int]] = []
        for candidate in remaining:
            center = max(clip_length / 2.0, min(duration - clip_length / 2.0, float(candidate["center"])))
            if any(abs(center - float(row["center"])) < hard_gap for row in selected):
                continue
            bucket = min(clip_count - 1, int(center / max(duration, 0.001) * clip_count))
            if bucket_counts.get(bucket, 0) >= bucket_cap:
                continue
            if coverage_pass and bucket in represented_buckets:
                continue
            nearest = (
                min(abs(center - float(row["center"])) for row in selected)
                if selected else preferred_gap
            )
            new_bucket_bonus = 0.26 if bucket not in represented_buckets else 0.0
            distance_bonus = 0.12 * clamp(nearest / max(preferred_gap, 0.001), 0.0, 1.0)
            proximity_penalty = (
                0.46 * (1.0 - nearest / preferred_gap)
                if selected and nearest < preferred_gap else 0.0
            )
            repeat_penalty = 0.30 * bucket_counts.get(bucket, 0)
            # Seeded jitter is deliberately small: it resolves near-ties but never
            # outweighs the evidence-based quality floor.
            tie_break = (_selection_unit(selection_seed, "candidate", round(center, 3)) - 0.5) * 0.10
            dynamic_score = (
                float(candidate["score"])
                + new_bucket_bonus
                + distance_bonus
                - proximity_penalty
                - repeat_penalty
                + tie_break
            )
            eligible.append((dynamic_score, {**candidate, "center": center}, bucket))
        if not eligible:
            # If a strict first coverage pass is impossible because adjacent
            # buckets share one event, keep the quality floor and relax only the
            # one-per-bucket rule.
            if coverage_pass:
                coverage_goal = len(represented_buckets)
                continue
            break
        _, chosen, bucket = max(eligible, key=lambda row: row[0])
        selected.append(chosen)
        represented_buckets.add(bucket)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        remaining = [
            item for item in remaining
            if abs(float(item["center"]) - float(chosen["center"])) >= hard_gap
        ]

    if not selected:
        return _fallback_short_story_ranges(
            duration, target, scene_points, selection_seed=selection_seed,
        )

    selected.sort(key=lambda item: float(item["center"]))
    centers = [float(item["center"]) for item in selected]
    # Sparse events must not expand into a target-length stretch of mostly quiet
    # footage. Give each event a bounded amount of context and its own timeline
    # cell, so adjacent expanded clips cannot overlap and silently lose duration.
    cells = [
        (
            0.0 if index == 0 else (centers[index - 1] + center) / 2.0 + 0.18,
            duration if index == len(centers) - 1 else (center + centers[index + 1]) / 2.0 - 0.18,
        )
        for index, center in enumerate(centers)
    ]
    capacities = [min(right - left, clip_length * 1.5) for left, right in cells]
    budget = min(target, sum(capacities))
    lengths = [
        min(length, capacity)
        for length, capacity in zip(_varied_highlight_lengths(centers, budget, selection_seed), capacities)
    ]
    # Redistribute only into other evidence-backed windows with room remaining.
    for _ in centers:
        remaining_budget = budget - sum(lengths)
        available = [index for index, length in enumerate(lengths) if capacities[index] - length > 0.00001]
        if remaining_budget <= 0.00001 or not available:
            break
        share = remaining_budget / len(available)
        for index in available:
            lengths[index] += min(share, capacities[index] - lengths[index])
    ranges: list[dict[str, float]] = []
    for center, length, (left, right) in zip(centers, lengths, cells):
        start = max(left, min(right - length, center - length / 2.0))
        end = min(right, start + length)
        ranges.append({"start": round(start, 3), "end": round(end, 3)})
    ranges = merge_ranges(ranges, gap=0.35)
    return ranges or _fallback_short_story_ranges(
        duration, target, scene_points, selection_seed=selection_seed,
    )


def _select_style_story_ranges(
    segments: list[dict[str, Any]],
    decision: dict[str, Any],
    duration: float,
    target: float,
    selection_policy: dict[str, Any],
    story_beats: list[dict[str, Any]] | None = None,
    *,
    selection_seed: Any = None,
) -> list[dict[str, float]] | None:
    """Keep complete local passages instead of filling a style with isolated lines.

    Semantic selections remain authoritative. The deterministic path uses actual
    speech boundaries and existing cue hints as bounded context evidence; it does
    not claim to identify a kill, joke or causal relationship from audio energy.
    """
    moment_limit = selection_policy.get("max_moments")
    if not moment_limit:
        return None
    moment_limit = max(1, int(moment_limit))
    semantic = merge_ranges(decision.get("story_ranges") or [], gap=0.75)
    if semantic and range_duration(semantic) <= target + 0.05:
        if moment_limit == 1 and semantic[-1]["end"] - semantic[0]["start"] <= target + 0.05:
            # Preserve the pauses and action between setup and payoff when one
            # continuous story fits. Never bridge distant chapters blindly.
            return [{"start": semantic[0]["start"], "end": semantic[-1]["end"]}]
        return semantic
    if semantic:
        # Let the existing semantic budget handling resolve an oversized plan.
        return None

    ordered = sorted(segments, key=lambda row: (float(row["start"]), float(row["end"])))
    if not ordered:
        return None
    beats = story_beats or build_story_beats(
        ordered, language_from_text(" ".join(str(row.get("text", "")) for row in ordered), "en"),
    )
    beats = sorted(beats, key=lambda row: float(row["start"]))
    before = max(0.0, _finite_number(selection_policy.get("pre_roll_seconds")))
    after = max(0.0, _finite_number(selection_policy.get("post_roll_seconds")))
    candidates: list[dict[str, float]] = []
    for index, beat in enumerate(beats):
        start, end = float(beat["start"]), float(beat["end"])
        # For an explanation or anecdote, include the neighboring question and
        # answer when the cue evidence fits in the same local passage. Stop at a
        # new hook or a prior ending instead of wandering into another story.
        if selection_policy.get("moment_unit") in {"complete_thought", "complete_anecdote"}:
            left, right = index, index
            for previous in (range(index - 1, -1, -1) if beat.get("role_hint") != "hook" else []):
                row = beats[previous]
                gap = float(beats[previous + 1]["start"]) - float(row["end"])
                if gap > max(6.0, before + after) or end - float(row["start"]) > target - before - after or row.get("role_hint") in {"result", "conclusion"}:
                    break
                if row.get("role_hint") == "hook":
                    left = previous
                    break
            for following in (range(index + 1, len(beats)) if beat.get("role_hint") not in {"result", "conclusion"} else []):
                row = beats[following]
                gap = float(row["start"]) - float(beats[following - 1]["end"])
                if gap > max(6.0, before + after) or float(row["end"]) - float(beats[left]["start"]) > target - before - after or row.get("role_hint") == "hook":
                    break
                if row.get("role_hint") in {"result", "conclusion"}:
                    right = following
                    break
            start, end = float(beats[left]["start"]), float(beats[right]["end"])
        start, end = max(0.0, start - before), min(duration, end + after)
        # Context padding may touch another sentence. Keep the whole sentence or
        # reject this candidate; padding must not create a mid-word cut.
        overlapping = [row for row in ordered if float(row["end"]) > start and float(row["start"]) < end]
        if not overlapping:
            continue
        start = min(start, float(overlapping[0]["start"]))
        end = max(end, float(overlapping[-1]["end"]))
        if end - start > target + 0.05:
            # Padding is optional; the complete source beat is not.
            start, end = float(beat["start"]), float(beat["end"])
            overlapping = [row for row in ordered if float(row["end"]) > start and float(row["start"]) < end]
        if not overlapping or end - start > target + 0.05 or end <= start:
            continue
        values = [_short_segment_value(row, decision) for row in overlapping]
        score = max(values) * 0.65 + sum(values) / len(values) * 0.35
        if beat.get("role_hint") in {"result", "conclusion"}:
            score += 0.15
        candidates.append({"start": start, "end": end, "score": score})

    selected: list[dict[str, float]] = []
    for candidate in sorted(candidates, key=lambda row: (
        -round(row["score"], 4),
        -_selection_unit(selection_seed, "style-moment", row["start"], row["end"]),
        row["start"],
    )):
        # Overlapping context is the same moment, not another highlight.
        if any(candidate["start"] < row["end"] and candidate["end"] > row["start"] for row in selected):
            continue
        if range_duration(selected) + candidate["end"] - candidate["start"] > target + 0.05:
            continue
        selected.append({"start": candidate["start"], "end": candidate["end"]})
        if len(selected) >= moment_limit:
            break
    # Do not fill a shorter, complete passage with unrelated low-value lines.
    return merge_ranges(selected, gap=0.0) if selected else None


def _style_cleanup_candidates(
    candidates: list[dict[str, Any]],
    keep_ranges: list[dict[str, float]],
    selection_policy: dict[str, Any],
) -> list[dict[str, Any]]:
    """Keep automatic cleanup from breaking the selected action or story setup."""
    if not selection_policy.get("story_structure"):
        return candidates
    protect_action = bool(selection_policy.get("protect_action_span"))
    return [
        candidate for candidate in candidates
        if not (
            (protect_action or candidate.get("reason") == "low_value")
            and any(float(candidate["start"]) < row["end"] and float(candidate["end"]) > row["start"] for row in keep_ranges)
        )
    ]


def _select_short_story_ranges(
    segments: list[dict[str, Any]],
    decision: dict[str, Any],
    duration: float,
    target_duration: float,
    scene_points: list[float] | None = None,
    *,
    selection_seed: Any = None,
    force_variation: bool = False,
    selection_policy: dict[str, Any] | None = None,
    story_beats: list[dict[str, Any]] | None = None,
) -> list[dict[str, float]]:
    """Select coherent passages from the whole recording for a Short.

    60 s behaves like a trailer/quick explanation: fewer, stronger passages with
    minimal context. A 3 minute target keeps broader local context and more timeline
    coverage. Selection is performed on transcript boundaries and never falls back
    to simply keeping the first N seconds.
    """
    target = min(float(duration), max(8.0, float(target_duration)))
    if duration <= target + 0.05:
        return [{"start": 0.0, "end": round(duration, 3)}]
    if not segments:
        return _fallback_short_story_ranges(
            duration, target, scene_points, selection_seed=selection_seed,
        )
    if selection_policy:
        style_ranges = _select_style_story_ranges(
            segments, decision, duration, target, selection_policy, story_beats,
            selection_seed=selection_seed,
        )
        if style_ranges:
            return style_ranges

    # v5.5 plans long footage at the STORY-BEAT level. When the semantic planner
    # selected coherent beat ranges, honor those ideas first instead of rebuilding
    # the short from isolated high-scoring transcript lines. Audio cleanup and the
    # target enforcer still operate on real Whisper boundaries afterwards.
    semantic_story = merge_ranges(decision.get("story_ranges") or [], gap=0.75)
    if semantic_story:
        # A new seed can vary evidence-equivalent candidates, but cannot discard
        # the semantic planner's selected ideas or the user's story instruction.
        # Until the planner supplies approved alternate beats, preserve these
        # ranges even when an alternate cut was requested.
        semantic_duration = range_duration(semantic_story)
        semantic_ceiling = target * (1.16 if target <= 90.0 else 1.10 if target <= 210.0 else 1.07)
        if target * 0.52 <= semantic_duration <= semantic_ceiling + 0.05:
            return semantic_story

    ordered = sorted(segments, key=lambda item: (float(item.get("start", 0)), float(item.get("end", 0))))
    id_to_index = {str(item.get("id")): index for index, item in enumerate(ordered)}
    # Add a little headroom because dead-air/filler cleanup is applied inside the
    # selected passages afterwards.
    raw_budget = min(duration, target * (1.16 if target <= 90 else 1.10 if target <= 210 else 1.07))
    context_radius = 1 if target <= 90 else 2 if target <= 210 else 3
    bucket_count = 5 if target <= 90 else 8 if target <= 210 else 12

    anchors: list[tuple[int, float, str]] = []
    seen: set[int] = set()

    def add_anchor(identifier: Any, bonus: float, kind: str) -> None:
        index = id_to_index.get(str(identifier or ""))
        if index is None or index in seen:
            return
        seen.add(index)
        anchors.append((index, _short_segment_value(ordered[index], decision) + bonus, kind))

    add_anchor(decision.get("opening_id"), 1.15, "opening")
    for identifier in (decision.get("highlight_ids") or [])[:10]:
        add_anchor(identifier, 0.80, "highlight")
    add_anchor(decision.get("closing_id"), 0.35, "closing")

    # Ensure coverage of the whole source even if the language model only selected
    # a few nearby highlights. The strongest segment in each timeline bucket is a
    # candidate, not an automatic keep.
    for bucket in range(bucket_count):
        start_t = duration * bucket / bucket_count
        end_t = duration * (bucket + 1) / bucket_count
        candidates = [
            (index, item) for index, item in enumerate(ordered)
            if start_t <= (float(item.get("start", 0)) + float(item.get("end", 0))) / 2 < end_t
        ]
        if not candidates:
            continue
        index, item = max(
            candidates,
            key=lambda pair: (
                _short_segment_value(pair[1], decision)
                + (_selection_unit(selection_seed, "coverage", bucket, pair[0]) - 0.5) * 0.05
            ),
        )
        if index not in seen:
            seen.add(index)
            anchors.append((index, _short_segment_value(item, decision) + 0.18, "coverage"))

    # Add globally strong segments as a final source of candidate passages.
    for index in sorted(
        range(len(ordered)),
        key=lambda i: (
            _short_segment_value(ordered[i], decision)
            + (_selection_unit(selection_seed, "strong", i) - 0.5) * 0.05
        ),
        reverse=True,
    )[:max(8, bucket_count * 2)]:
        if index not in seen:
            seen.add(index)
            anchors.append((index, _short_segment_value(ordered[index], decision), "strong"))

    passages: list[dict[str, Any]] = []
    for anchor_index, anchor_score, kind in anchors:
        left = max(0, anchor_index - context_radius)
        right = min(len(ordered) - 1, anchor_index + context_radius)
        included: list[dict[str, Any]] = []
        for index in range(left, right + 1):
            item = ordered[index]
            # Keep context, but don't deliberately pull a clear retake into a
            # passage merely because it sits beside a highlight.
            if index != anchor_index and (item.get("false_start") or float(item.get("repeat_score", 0)) >= 0.90):
                continue
            included.append(item)
        if not included:
            included = [ordered[anchor_index]]
        start = min(float(item["start"]) for item in included)
        end = max(float(item["end"]) for item in included)
        if end - start < 0.25:
            continue
        center = (start + end) / 2
        bucket = min(bucket_count - 1, int((center / max(duration, 0.001)) * bucket_count))
        passages.append({
            "start": start, "end": end, "score": anchor_score,
            "bucket": bucket, "kind": kind, "anchor": anchor_index,
        })

    selected: list[dict[str, Any]] = []
    represented: set[int] = set()
    total = 0.0
    opening = next((item for item in passages if item["kind"] == "opening"), None)
    if opening:
        selected.append(opening)
        represented.add(int(opening["bucket"]))
        total = range_duration(merge_ranges(selected, gap=0.65))

    remaining = [item for item in passages if item is not opening]
    while remaining and total < raw_budget * 0.96:
        def dynamic_score(item: dict[str, Any]) -> float:
            new_bucket = 0.34 if int(item["bucket"]) not in represented else 0.0
            distance_bonus = 0.0
            if selected:
                distance = min(abs((item["start"] + item["end"]) / 2 - (other["start"] + other["end"]) / 2) for other in selected)
                distance_bonus = min(0.28, distance / max(duration, 1.0) * 1.5)
            tie_break = (
                _selection_unit(selection_seed, "passage", int(item["anchor"]), round(float(item["start"]), 3))
                - 0.5
            ) * 0.08
            return float(item["score"]) + new_bucket + distance_bonus + tie_break
        item = max(remaining, key=dynamic_score)
        remaining.remove(item)
        candidate = merge_ranges([*selected, item], gap=0.65)
        candidate_total = range_duration(candidate)
        if selected and candidate_total > raw_budget * 1.08:
            continue
        selected.append(item)
        represented.add(int(item["bucket"]))
        total = candidate_total

    # If sparse transcript anchors did not fill enough of the requested duration,
    # add strong individual segments across unrepresented parts of the recording.
    if total < raw_budget * 0.82:
        selected_indices = {int(item["anchor"]) for item in selected}
        extras = sorted(
            (index for index in range(len(ordered)) if index not in selected_indices),
            key=lambda i: (
                _short_segment_value(ordered[i], decision)
                + (_selection_unit(selection_seed, "extra", i) - 0.5) * 0.05,
                -abs((float(ordered[i]["start"]) / max(duration, 1.0)) - 0.5),
            ),
            reverse=True,
        )
        for index in extras:
            item = ordered[index]
            candidate_item = {"start": float(item["start"]), "end": float(item["end"])}
            candidate = merge_ranges([*selected, candidate_item], gap=0.65)
            candidate_total = range_duration(candidate)
            if candidate_total > raw_budget * 1.08:
                continue
            selected.append({**candidate_item, "anchor": index, "bucket": 0, "score": _short_segment_value(item, decision), "kind": "fill"})
            total = candidate_total
            if total >= raw_budget * 0.92:
                break

    ranges = merge_ranges(selected, gap=0.65)
    return ranges or _fallback_short_story_ranges(
        duration, target, scene_points, selection_seed=selection_seed,
    )

def _camera_plan(keep_ranges: list[dict[str, float]], has_b: bool, layout: str, pace: str, scene_points: list[float]) -> list[dict[str, Any]]:
    if not keep_ranges:
        return []
    if not has_b:
        return [{**item, "camera": "A"} for item in keep_ranges]
    if layout and layout != "auto":
        return [{**item, "camera": layout} for item in keep_ranges]
    minimum_shot = {"gentle": 7.5, "balanced": 5.0, "dynamic": 3.5}.get(pace, 6.5)
    max_switches = {"gentle": 8, "balanced": 14, "dynamic": 22}.get(pace, 14)
    output: list[dict[str, Any]] = []
    # Automatic decisions are semantic, not tied to upload order. A later role
    # correction therefore updates both the current preview and final render.
    camera = "screen"
    last_switch = -999.0
    scene_points = sorted(set(round(float(point), 3) for point in scene_points if float(point) >= 0))
    for keep in keep_ranges:
        start, end = float(keep["start"]), float(keep["end"])
        boundaries = [start]
        last_boundary = start
        for point in scene_points:
            if point - last_boundary >= minimum_shot and end - point >= minimum_shot:
                boundaries.append(point)
                last_boundary = point
        if len(boundaries) - 1 > max_switches:
            candidates = boundaries[1:]
            step = len(candidates) / max_switches
            boundaries = [start] + [candidates[min(len(candidates) - 1, int(index * step))] for index in range(max_switches)]
            boundaries = sorted(set(boundaries))
        boundaries.append(end)
        cursor = boundaries[0]
        for boundary in boundaries[1:]:
            if boundary - cursor < 0.25:
                continue
            output.append({"start": round(cursor, 3), "end": round(boundary, 3), "camera": camera})
            if boundary - last_switch >= minimum_shot:
                camera = "camera" if camera == "screen" else "screen"
                last_switch = boundary
            cursor = boundary
    return output


def _camera_plan_for_layout(
    keep_ranges: list[dict[str, float]],
    has_b: bool,
    requested_layout: str,
    pace: str,
    scene_points: list[float],
    embedded_candidate: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Resolve a camera plan without silently duplicating a single source.

    Embedded Screen + Facecam is deliberately opt-in. Vision may suggest a
    candidate, but only an explicit ``embedded_stack`` layout confirms that the
    source may be split into two panels.
    """
    if requested_layout == "embedded_stack":
        if embedded_candidate:
            return ([{**item, "camera": "embedded_stack"} for item in keep_ranges], True)
        return ([{**item, "camera": "A"} for item in keep_ranges], False)
    return (_camera_plan(keep_ranges, has_b, requested_layout, pace, scene_points), False)


def _effective_embedded_candidate(
    project: dict[str, Any],
    vision: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Resolve the trusted facecam crop, preferring the user's rectangle."""

    manual = project.get("manual") if isinstance(project.get("manual"), dict) else {}
    return select_embedded_candidate(
        manual.get("embedded_camera") if isinstance(manual, dict) else None,
        vision,
        vision_version=str((vision or {}).get("version") or "") or None,
    )


def _reel_candidate_window(
    anchor: dict[str, Any],
    segments: list[dict[str, Any]],
    duration: float,
    target_duration: float,
) -> tuple[float, float]:
    """Build one speech-boundary-aware source window around a strong story beat."""

    target = min(duration, max(8.0, target_duration))
    anchor_start = clamp(_finite_number(anchor.get("start")), 0.0, duration)
    anchor_end = clamp(_finite_number(anchor.get("end"), anchor_start), anchor_start, duration)
    anchor_center = (anchor_start + anchor_end) / 2.0
    role = str(anchor.get("role_hint") or "")
    # Hooks benefit from a little more runway after the beat; conclusions need
    # more setup before them. This only moves a bounded window and never reorders.
    before_ratio = 0.34 if role == "hook" else 0.62 if role == "conclusion" else 0.46
    start = max(0.0, min(duration - target, anchor_center - target * before_ratio))
    end = min(duration, start + target)

    ordered = sorted(
        (item for item in segments if _finite_number(item.get("end")) > _finite_number(item.get("start"))),
        key=lambda item: (_finite_number(item.get("start")), _finite_number(item.get("end"))),
    )
    # Avoid starting or ending in the middle of a sentence. Only snap inward so
    # a candidate never silently exceeds the requested duration.
    starts = [_finite_number(item.get("start")) for item in ordered if start <= _finite_number(item.get("start")) <= start + 3.0]
    ends = [_finite_number(item.get("end")) for item in ordered if end - 3.0 <= _finite_number(item.get("end")) <= end]
    if starts:
        start = min(starts)
    if ends:
        end = max(ends)
    if end - start < 8.0:
        start = max(0.0, min(duration - target, anchor_center - target / 2.0))
        end = min(duration, start + target)
    return round(start, 3), round(end, 3)


def _build_reel_candidates(
    project: dict[str, Any],
    draft: dict[str, Any],
    segments: list[dict[str, Any]],
    story_beats: list[dict[str, Any]],
    scene_points: list[float],
    embedded_candidate: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Create ranked, directly-applicable Reel alternatives from cached analysis.

    This deliberately performs no transcription, model call, frame analysis or
    render. Alternatives are diverse source windows around already-scored story
    beats, with obvious retakes removed and all existing manual cuts respected.
    """

    if str(draft.get("goal") or "") != "short":
        return []
    duration = max(0.0, _finite_number(draft.get("source_duration")))
    target = min(duration, max(8.0, _finite_number(draft.get("target_duration"), 60.0)))
    if duration <= target + 1.0:
        return []

    primary = {
        "id": "director_pick",
        "kind": "director_pick",
        "rank": 1,
        "score": 96,
        "output_duration": round(_finite_number(draft.get("output_duration")), 3),
        "keep_ranges": copy.deepcopy(draft.get("keep_ranges") or []),
        "cuts": copy.deepcopy(draft.get("cuts") or []),
        "ai_camera_plan": copy.deepcopy(draft.get("ai_camera_plan") or draft.get("camera_plan") or []),
        "camera_plan": copy.deepcopy(draft.get("camera_plan") or []),
        "preview": str(draft.get("summary") or "")[:220],
    }
    candidates: list[dict[str, Any]] = [primary]
    signatures = {
        tuple((round(_finite_number(item.get("start")), 2), round(_finite_number(item.get("end")), 2)) for item in primary["keep_ranges"])
    }

    anchors = [item for item in story_beats if isinstance(item, dict)]
    if not anchors:
        anchors = [item for item in segments if isinstance(item, dict)]
    anchors = sorted(
        anchors,
        key=lambda item: (
            _finite_number(item.get("editorial_score"), 0.5)
            + (0.22 if item.get("role_hint") in {"hook", "conclusion"} else 0.0)
            + _finite_number(item.get("novelty")) * 0.08,
            _finite_number(item.get("end")) - _finite_number(item.get("start")),
        ),
        reverse=True,
    )
    has_b = bool((project.get("sources") or {}).get("B"))
    requested_layout = str(draft.get("layout") or "auto")
    pace = str(draft.get("pace") or "balanced")
    overrides = (project.get("manual") or {}).get("camera_overrides") or []
    chosen_centers: list[float] = []

    for anchor in anchors:
        if len(candidates) >= 3:
            break
        start, end = _reel_candidate_window(anchor, segments, duration, target)
        center = (start + end) / 2.0
        if any(abs(center - other) < target * 0.42 for other in chosen_centers):
            continue
        outside = []
        if start > 0.0:
            outside.append({"start": 0.0, "end": start})
        if end < duration:
            outside.append({"start": end, "end": duration})
        cleanup: list[dict[str, float]] = []
        anchor_start = _finite_number(anchor.get("start"))
        anchor_end = _finite_number(anchor.get("end"))
        for item in segments:
            item_start = _finite_number(item.get("start"))
            item_end = _finite_number(item.get("end"))
            if item_end <= start or item_start >= end:
                continue
            if item_start < anchor_end and item_end > anchor_start:
                continue
            obvious_retry = bool(item.get("false_start")) or _finite_number(item.get("repeat_score")) >= 0.88
            empty_filler = _finite_number(item.get("filler_ratio")) >= 0.72 and _finite_number(item.get("editorial_score"), 1.0) < 0.34
            if obvious_retry or empty_filler:
                cleanup.append({"start": max(start, item_start), "end": min(end, item_end)})
        cuts = apply_timeline_overrides(
            merge_ranges([*outside, *cleanup], gap=0.05), project.get("manual"),
        )
        keep_ranges = invert_ranges(cuts, duration)
        output_duration = range_duration(keep_ranges)
        if output_duration < min(8.0, target * 0.55):
            cuts = apply_timeline_overrides(outside, project.get("manual"))
            keep_ranges = invert_ranges(cuts, duration)
            output_duration = range_duration(keep_ranges)
        signature = tuple((round(float(item["start"]), 2), round(float(item["end"]), 2)) for item in keep_ranges)
        if not signature or signature in signatures:
            continue

        ai_plan, _ = _camera_plan_for_layout(
            keep_ranges,
            has_b,
            requested_layout,
            pace,
            scene_points,
            embedded_candidate,
        )
        camera_plan = apply_camera_overrides(
            ai_plan,
            keep_ranges,
            overrides if isinstance(overrides, list) else [],
            has_b=has_b,
        )
        editorial = _finite_number(anchor.get("editorial_score"), 0.5)
        score = min(94, max(70, round(78 + editorial * 13 + (2 if anchor.get("role_hint") else 0))))
        kind = "focused_moment" if len(candidates) == 1 else "alternate_highlight"
        candidates.append({
            "id": f"reel_{len(candidates) + 1}",
            "kind": kind,
            "rank": len(candidates) + 1,
            "score": score,
            "output_duration": round(output_duration, 3),
            "keep_ranges": keep_ranges,
            "cuts": cuts,
            "ai_camera_plan": ai_plan,
            "camera_plan": camera_plan,
            "preview": str(anchor.get("text") or "")[:220],
        })
        signatures.add(signature)
        chosen_centers.append(center)
    return candidates if len(candidates) > 1 else []


def _aggregate_decisions(counts: dict[str, int], before: float, after: float, has_b: bool, sync: dict[str, Any] | None) -> list[dict[str, Any]]:
    labels = {
        "silence": "dead_air",
        "retake": "retakes",
        "repetition": "repetitions",
        "filler": "fillers",
        "low_value": "low_value",
        "manual": "manual",
        "quiet_audio": "quiet_audio",
        "loud_audio": "loud_audio",
        "clipping": "clipping",
        "target_trim": "target_trim",
        "story_selection": "story_selection",
    }
    decisions = [
        {"type": labels.get(reason, reason), "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
        if count
    ][:6]
    decisions.insert(0, {"type": "duration", "before": round(before, 1), "after": round(after, 1)})
    if has_b and sync:
        decisions.append({"type": "sync", "offset": sync.get("offset", 0), "confidence": sync.get("confidence", 0)})
    return decisions[:8]


def _explicit_source_layout(project: dict[str, Any]) -> str | None:
    """Return the user's persisted semantic Source Mixer layout.

    A missing key is deliberately different from an explicit ``auto`` choice:
    only the former allows a goal or style preset to choose the initial layout.
    """

    mixer = (project.get("manual") or {}).get("source_mixer")
    if not isinstance(mixer, dict) or "default_layout" not in mixer:
        return None
    layout = str(mixer.get("default_layout") or "").strip().lower()
    if layout not in SOURCE_MIXER_DEFAULT_LAYOUTS:
        return None
    sources = project.get("sources") or {}
    if layout in {"screen", "camera", "stacked", "side_by_side", "pip"} and not sources.get("B"):
        return "A"
    # Keep single-source choices semantic inside the Draft. Preview and render
    # resolve them against the latest role mapping, so swapping A/B cannot turn a
    # saved "screen" decision into a camera shot (or vice versa).
    return layout


def _effective_brief(project: dict[str, Any]) -> dict[str, Any]:
    brief = enrich_brief_with_style(copy.deepcopy(project.get("settings", {})))
    # Frame rate is an encoder preference, not a story instruction. Changing it
    # must not invalidate expensive speech/story caches or an in-flight draft.
    brief.pop("fps", None)
    goal = str(brief.get("goal", "short"))
    # Product intent supplies safe defaults. An explicit Source Mixer choice is
    # applied last, so changing an edit style can never erase the user's framing.
    if goal == "short":
        brief["aspect"] = "9:16"
    elif goal == "youtube":
        brief["aspect"] = "16:9"
        brief["layout"] = "A"
    # A manual embedded-camera rectangle is an explicit single-source layout
    # choice and must survive YouTube's ordinary source-A default. Merely having
    # a detector suggestion is not enough; only the persisted manual candidate
    # plus the explicit setting activates this path.
    manual_embedded = _effective_embedded_candidate(project, None)
    if (
        manual_embedded is not None
        and not (project.get("sources") or {}).get("B")
        and str((project.get("settings") or {}).get("layout") or "") == "embedded_stack"
    ):
        brief["layout"] = "embedded_stack"
    explicit_layout = _explicit_source_layout(project)
    if explicit_layout is not None:
        brief["layout"] = explicit_layout
    elif (project.get("sources") or {}).get("B"):
        # Streamer presets historically carried physical ``A`` defaults, which
        # silently hid a valid second source. Resolve those defaults through the
        # style's two-source policy and keep the result semantic so role swaps
        # remain meaningful.
        current_layout = str(brief.get("layout") or "auto")
        framing_policy = ((brief.get("style_profile") or {}).get("framing_policy") or {})
        if current_layout in {"A", "B"}:
            current_layout = str(framing_policy.get("second_source_layout") or "auto")
        if current_layout == "A":
            current_layout = "screen"
        elif current_layout == "B":
            current_layout = "camera"
        if current_layout not in SOURCE_MIXER_DEFAULT_LAYOUTS:
            current_layout = "auto"
        brief["layout"] = current_layout
    return brief


def analyze_project(
    context: JobContext,
    project_id: str,
    store: ProjectStore,
    settings: Settings,
    brief_patch: dict[str, Any] | None = None,
    *,
    selection_variant: int = 0,
    source_mixer_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context.checkpoint()
    project = store.load(project_id)
    # Rebuilding a project with independent media must be all-or-nothing: a
    # rejected shorter draft must not leave the refinement's settings applied.
    staged_brief = brief_patch if (project.get("manual") or {}).get("media_clips") else None
    original_settings = copy.deepcopy(project.get("settings") or {})
    if brief_patch:
        context.checkpoint()
        if staged_brief:
            project.setdefault("settings", {}).update(staged_brief)
        else:
            project = store.update(
                project_id,
                lambda current: current.setdefault("settings", {}).update(brief_patch),
            )
    manual_input_fingerprint = stable_fingerprint("director-manual-input", project.get("manual") or {})
    if source_mixer_patch:
        project.setdefault("manual", {}).setdefault("source_mixer", {}).update(source_mixer_patch)

    def proposed_inputs(latest: dict[str, Any]) -> dict[str, Any]:
        if not staged_brief and not source_mixer_patch:
            return latest
        current_settings = latest.get("settings") or {}
        if any(current_settings.get(key) != original_settings.get(key) for key in staged_brief or {}):
            raise RuntimeError("project_changed_during_analysis")
        candidate = copy.deepcopy(latest)
        candidate.setdefault("settings", {}).update(staged_brief or {})
        if source_mixer_patch:
            candidate.setdefault("manual", {}).setdefault("source_mixer", {}).update(source_mixer_patch)
        return candidate
    source_a = _source_path(store, project, "A")
    source_b = _source_path(store, project, "B") if project.get("sources", {}).get("B") else None
    duration = float(project["sources"]["A"]["duration"])
    analysis_audio_slot = _analysis_audio_slot(project)
    analysis_source = source_b if analysis_audio_slot == "B" and source_b is not None else source_a
    analysis_source_info = project.get("sources", {}).get(analysis_audio_slot) or project["sources"]["A"]
    analysis_source_duration = max(0.0, _finite_number(analysis_source_info.get("duration"), duration))
    brief = _effective_brief(project)
    explicit_source_layout = _explicit_source_layout(project)
    pace = str(brief.get("pace", "balanced"))
    goal = str(brief.get("goal", "short"))
    target_duration = clamp(float(brief.get("target_duration", 60)), 8.0, max(8.0, duration))

    performance_mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    spoken_language = str(brief.get("spoken_language") or project.get("language") or "auto")
    policy = audio_policy(brief.get("audio_cleanup"))
    if goal == "youtube":
        # YouTube should preserve content but be decisive about measured dead air.
        # Per-range gain automation is disabled without speech evidence; final
        # normalization remains safe and lightweight.
        policy.update({
            "silence_action": "shorten",
            "silence_min_seconds": min(float(policy.get("silence_min_seconds", 0.75)), 0.65),
            "silence_keep_seconds": min(float(policy.get("silence_keep_seconds", 0.30)), 0.24),
            "max_remove_ratio": max(float(policy.get("max_remove_ratio", 0.28)), 0.92),
            "quiet_action": "keep",
            "loud_action": "keep",
            "normalize": True,
        })
    youtube_cleanup_only = bool(
        goal == "youtube"
        and not str(brief.get("instruction") or "").strip()
    )
    youtube_needs_transcript = bool(brief.get("captions") or brief.get("burn_captions"))
    auto_reframe_enabled = project.get("settings", {}).get("auto_reframe", True) is not False
    need_vision = bool(
        goal == "short"
        and str(brief.get("aspect", "9:16")) in {"9:16", "1:1", "4:5"}
        # With one source, vision is also advisory embedded-camera discovery.
        # It must not disappear merely because a streamer style disables crop
        # auto-reframing. Two-source projects still respect that performance flag.
        and (auto_reframe_enabled or not source_b)
    ) or str(brief.get("layout", "auto")) == "embedded_stack"
    sample_map = settings.raw.get("vision_samples", {}) if isinstance(settings.raw.get("vision_samples", {}), dict) else {}
    vision_mode = performance_mode if performance_mode in {"lite", "balanced", "quality"} else "lite"
    vision_samples = normalized_vision_sample_count(
        sample_map.get(vision_mode),
        8 if vision_mode == "lite" else 14,
    )
    prepared_vision = (((project.get("pre_analysis") or {}).get("vision") or {}).get("A"))
    source_generation = str((project.get("sources", {}).get("A") or {}).get("generation") or "")
    prepared_vision_is_current = _prepared_vision_is_reusable(
        prepared_vision,
        source_generation,
        vision_samples,
    )
    # Selecting the embedded layout accepts the displayed preparation crop. A
    # higher-sample Director pass may refine detection, but must not erase that
    # choice. Only current-source geometry from the trusted detector qualifies.
    accepted_prepared_embedded = (
        select_embedded_candidate(None, prepared_vision)
        if not source_b
        and str(brief.get("layout")) == "embedded_stack"
        and _prepared_vision_is_reusable(prepared_vision, source_generation, 0)
        else None
    )

    def resolve_source_vision() -> dict[str, Any]:
        if prepared_vision_is_current:
            context.checkpoint("Reusing embedded-camera detection")
            return copy.deepcopy(prepared_vision)
        context.update(max(0.50, float(context.job.progress)), "Finding the speaker and framing")
        result = analyze_faces_and_embedded_camera(
            source_a,
            duration,
            progress=lambda value, message: context.update(0.50 + value * 0.07, message),
            samples=vision_samples,
            cancel_check=context.check_cancelled,
        )
        context.checkpoint()
        return {**result, "sample_count": vision_samples, "profile": vision_mode}

    cached_analysis = project.get("analysis") if isinstance(project.get("analysis"), dict) else None
    context.checkpoint()
    cache_brief = copy.deepcopy(brief)
    cache_fingerprints = build_analysis_cache_fingerprints(
        project,
        settings,
        cache_brief,
        {"A": source_a, "B": source_b},
    )
    try:
        normalized_selection_variant = max(0, int(selection_variant))
    except (TypeError, ValueError, OverflowError):
        normalized_selection_variant = 0
    selection_seed = stable_fingerprint(
        "director-selection",
        {
            "strategy": SELECTION_STRATEGY_VERSION,
            "source": cache_fingerprints.get("source"),
            "story": cache_fingerprints.get("story"),
            "variant": normalized_selection_variant,
        },
    )
    cached_fingerprints = cached_analysis.get("cache_fingerprints") if cached_analysis else None
    source_cache_matches = bool(
        cached_analysis
        and cache_fingerprints_match(cached_fingerprints, cache_fingerprints, ("pipeline", "source"))
    )
    sync: dict[str, Any] | None = None
    scenes_b: list[float] = []
    source_b_warning: str | None = None
    manual_sync_offset = _manual_sync_offset(project)
    source_tracks = (project.get("manual") or {}).get("source_tracks")
    if source_b and isinstance(source_tracks, dict) and "B" in source_tracks:
        # Independently edited B clips already have explicit local media times.
        # Re-measuring sync would silently change Restore's default mapping and
        # caption analysis coordinates. Freeze that base until the track resets.
        sync = {"offset": source_sync_offset(project), "confidence": 1.0, "method": "source_tracks"}
    elif source_b and manual_sync_offset is not None:
        sync = {"offset": round(manual_sync_offset, 3), "confidence": 1.0, "method": "manual"}
    elif (
        source_b
        and source_cache_matches
        and isinstance((cached_analysis or {}).get("sync"), dict)
        # Resetting a manual offset to Auto must actually measure again; carrying
        # forward a cached manual value would make the reset button ineffective.
        and str(((cached_analysis or {}).get("sync") or {}).get("method") or "") not in {"manual", "source_tracks"}
    ):
        sync = copy.deepcopy(cached_analysis.get("sync"))
    elif source_b and analysis_audio_slot == "B":
        if project["sources"]["A"].get("has_audio") and (project["sources"].get("B") or {}).get("has_audio"):
            context.update(0.01, "Synchronizing the selected speech source")
            try:
                sync = synchronize_sources(
                    source_a,
                    source_b,
                    settings,
                    progress=lambda value, message: context.update(0.01 + value * 0.02, message),
                    cancel_check=context.check_cancelled,
                )
            except JobCancelled:
                raise
            except Exception as exc:
                source_b_warning = f"Could not auto-sync source B audio: {type(exc).__name__}: {exc}"
        if not sync:
            sync = {"offset": 0.0, "confidence": 0.0, "method": "fallback"}
    sync = _safe_automatic_sync(sync)
    analysis_timeline_offset = _finite_number((sync or {}).get("offset"), 0.0) if analysis_audio_slot == "B" else 0.0
    reusable_context = bool(
        cached_analysis
        and str(cached_analysis.get("audio_source") or "A").upper() == analysis_audio_slot
        and abs(_finite_number(cached_analysis.get("audio_timeline_offset"), 0.0) - analysis_timeline_offset) < 0.0005
        and cached_analysis.get("transcript") is not None
        and cached_analysis.get("scenes") is not None
        and cache_fingerprints_match(
            cached_fingerprints,
            cache_fingerprints,
            ("pipeline", "source", "transcript", "scenes"),
        )
    )
    reusable_vision = bool(
        reusable_context
        and cached_analysis
        and isinstance(cached_analysis.get("vision"), dict)
        and cached_analysis.get("vision", {}).get("version") == VISION_ANALYSIS_VERSION
        and cache_fingerprints_match(cached_fingerprints, cache_fingerprints, ("vision",))
    )
    reusable_story = bool(
        reusable_context
        and cached_analysis
        and cached_analysis.get("story_hierarchy")
        and cache_fingerprints_match(cached_fingerprints, cache_fingerprints, ("story",))
    )
    transcription_warning: str | None = None
    requested_threshold = policy.get("silence_threshold_dbfs")
    if reusable_context:
        context.update(0.05, "Reusing transcript and visual context")
        if source_b_warning is None:
            source_b_warning = next(
                (
                    str(item.get("message"))
                    for item in cached_analysis.get("warnings") or []
                    if isinstance(item, dict) and item.get("type") == "source_b" and item.get("message")
                ),
                None,
            )
        transcript, cached_transcript_changed = _normalize_transcript(
            copy.deepcopy(cached_analysis.get("transcript") or {}),
            spoken_language,
            duration,
        )
        if cached_transcript_changed:
            transcription_warning = "Cached transcription contained incomplete data and was safely normalized."
        scenes_a = list((cached_analysis.get("scenes") or {}).get("A") or [])
        vision = copy.deepcopy(cached_analysis.get("vision") or {})
        if not need_vision:
            vision = {}
        cached_audio = copy.deepcopy(cached_analysis.get("audio") or {"available": False, "ranges": {}, "summary": {}})
        cached_threshold = (cached_audio.get("summary") or {}).get("silence_threshold_dbfs")
        threshold_changed = requested_threshold is not None and (
            cached_threshold is None or abs(float(cached_threshold) - float(requested_threshold)) > 0.15
        )
        if threshold_changed and analysis_source_info.get("has_audio"):
            context.update(0.08, "Applying your silence threshold")
            try:
                threshold_transcript_segments = transcript.get("segments", [])
                if analysis_audio_slot == "B":
                    threshold_transcript_segments = _map_transcript_to_timeline(
                        transcript,
                        -analysis_timeline_offset,
                        analysis_source_duration,
                    ).get("segments", [])
                sound_profile = analyze_audio(
                    analysis_source, settings, analysis_source_duration,
                    progress=lambda value, message: context.update(0.08 + value * 0.13, message),
                    transcript_segments=threshold_transcript_segments,
                    silence_threshold_dbfs=float(requested_threshold),
                    cancel_check=context.check_cancelled,
                )
                if analysis_audio_slot == "B":
                    sound_profile = _map_audio_profile_to_timeline(sound_profile, analysis_timeline_offset, duration)
            except JobCancelled:
                raise
            except Exception as exc:
                sound_profile = cached_audio
                sound_profile["warning"] = f"{type(exc).__name__}: {exc}"
        else:
            sound_profile = cached_audio
    else:
        context.update(0.03, "Measuring sound")
        try:
            sound_profile = analyze_audio(
                analysis_source, settings, analysis_source_duration,
                progress=lambda value, message: context.update(0.03 + value * 0.16, message),
                silence_threshold_dbfs=float(requested_threshold) if requested_threshold is not None else None,
                cancel_check=context.check_cancelled,
            ) if analysis_source_info.get("has_audio") else {"available": False, "ranges": {}, "summary": {}}
            if analysis_audio_slot == "B":
                sound_profile = _map_audio_profile_to_timeline(sound_profile, analysis_timeline_offset, duration)
        except JobCancelled:
            raise
        except Exception as exc:
            sound_profile = {"available": False, "ranges": {}, "summary": {}, "warning": f"{type(exc).__name__}: {exc}"}

        if youtube_cleanup_only and not youtube_needs_transcript:
            # A normal YouTube cleanup does not need a language model at all.
            # Audio evidence is enough to remove dead air while preserving content.
            context.update(0.28, "Keeping the original YouTube structure")
            transcript = {"language": spoken_language if spoken_language != "auto" else "unknown", "segments": [], "words": [], "text": ""}
            scenes_a = []
            vision = resolve_source_vision() if need_vision else {}
        else:
            context.update(0.20, "Understanding speech" if not youtube_cleanup_only else "Transcribing captions without changing the story")
            transcript, transcription_warning = _transcribe_safely(
                analysis_source,
                settings,
                language=spoken_language,
                progress=lambda value, message: context.update(0.20 + value * 0.24, message),
                performance_mode=performance_mode,
                duration=analysis_source_duration,
                cancel_check=context.check_cancelled,
            )
            if analysis_audio_slot == "B":
                transcript = _map_transcript_to_timeline(transcript, analysis_timeline_offset, duration)
            context.checkpoint()
            sound_profile = protect_silence_ranges_from_speech(sound_profile, transcript.get("segments", []))
            sound_profile = constrain_gain_ranges_to_speech(sound_profile, transcript.get("segments", []))
            need_scenes = bool(source_b) and goal != "youtube"
            context.update(0.45, "Checking visual structure")
            scenes_a = detect_scenes(source_a, settings, cancel_check=context.check_cancelled) if need_scenes else []
            context.checkpoint()
            if need_vision:
                vision = resolve_source_vision()
            else:
                vision = {}

    # Vision semantics are versioned independently from transcript/audio caches.
    # Refresh only this cheap sampled analysis when loading a legacy candidate;
    # otherwise old false positives could survive the stricter detector forever.
    if reusable_context and need_vision and not reusable_vision:
        context.update(max(0.45, float(context.job.progress)), "Refreshing speaker and framing detection")
        vision = resolve_source_vision()
    if accepted_prepared_embedded is not None:
        vision = {**vision, "embedded_camera": accepted_prepared_embedded}

    transcript_quality = transcript_quality_report(transcript)
    edit_style = str(brief.get("edit_style") or "smart")
    semantic_transcript_required = goal in {"short", "podcast"} or (goal == "youtube" and not youtube_cleanup_only)
    transcript_upgraded = False
    transcript_fallback: dict[str, Any] | None = None
    nonverbal_highlights = False
    audio_cleanup_fallback = False
    can_degrade_without_semantics = goal in {"short", "youtube", "clean"}
    skip_upgrade_for_sparse_source = can_degrade_without_semantics and _clearly_sparse_transcript(transcript_quality)
    if semantic_transcript_required and not transcript_quality["usable_for_story"] and not skip_upgrade_for_sparse_source:
        upgrade_warning: str | None = None
        upgrade_mode, retry_language = _transcript_upgrade_request(
            performance_mode, spoken_language, transcript, transcript_quality,
        )
        if not cloud_enabled(settings) and cuda_available(settings) and upgrade_mode:
            retry_start = max(0.20 if reusable_context else 0.44, float(context.job.progress))
            retry_span = max(0.005, 0.575 - retry_start)
            context.update(retry_start, "Improving a low-confidence transcript on GPU")
            upgraded, upgrade_warning = _transcribe_safely(
                analysis_source,
                settings,
                language=retry_language,
                progress=lambda value, message: context.update(retry_start + value * retry_span, message),
                performance_mode=upgrade_mode,
                duration=analysis_source_duration,
                cancel_check=context.check_cancelled,
            )
            if analysis_audio_slot == "B":
                upgraded = _map_transcript_to_timeline(upgraded, analysis_timeline_offset, duration)
            upgraded_quality = transcript_quality_report(upgraded)
            if upgraded_quality["usable_for_story"]:
                transcript = upgraded
                transcript_quality = upgraded_quality
                transcript_upgraded = True
                transcription_warning = upgrade_warning or transcription_warning
                sound_profile = protect_silence_ranges_from_speech(sound_profile, transcript.get("segments", []))
                sound_profile = constrain_gain_ranges_to_speech(sound_profile, transcript.get("segments", []))

    _assert_transcript_complete(transcript_quality)
    if not transcript_quality["usable_for_story"] and not (goal == "youtube" and youtube_cleanup_only):
        reasons = list(transcript_quality.get("reasons") or ["unusable_transcript"])
        if goal == "short":
            # A Short can still be selected honestly from measured RMS/peaks and
            # scene changes. This is a usable draft, not a fabricated Storyline.
            nonverbal_highlights = True
            fallback_kind = "audio_visual_highlights"
        elif goal in {"youtube", "clean"}:
            # Preserve chronology and use only defensible audio cleanup when the
            # requested story or cleanup transcript is not trustworthy.
            audio_cleanup_fallback = True
            youtube_cleanup_only = goal == "youtube"
            fallback_kind = "audio_cleanup"
        else:
            detail = f" ({', '.join(reasons)})"
            raise StoryPlanningError(
                "This edit style needs reliable speech before CUTROOM can select a conversation without guessing"
                f"{detail}. Choose the exact spoken language and Quality mode, then retry."
            )

        detected_language = str(transcript.get("detected_language") or transcript.get("language") or "unknown")
        explicit_language = str(spoken_language or "auto")
        fallback_language = (
            explicit_language
            if explicit_language not in {"", "auto", "unknown"}
            else language_from_text(
                f"{project.get('name') or ''} {brief.get('instruction') or ''}",
                "en",
            )
        )
        transcript_fallback = {
            "type": "transcript_fallback",
            "message": (
                "No reliable speech was found. CUTROOM used measured audio and visual evidence without "
                "claiming a Storyline or burning untrusted captions."
            ),
            "reasons": reasons,
            "fallback": fallback_kind,
            "detected_language": detected_language,
            "speech_ratio": transcript_quality.get("speech_ratio"),
            "edit_style": edit_style,
        }
        # Do not let hallucinated words affect cuts, language, captions or exports.
        transcript = {
            **transcript,
            "detected_language": detected_language,
            "language": fallback_language,
            "language_probability": 0.0,
            "segments": [],
            "words": [],
            "text": "",
            "discarded_quality": copy.deepcopy(transcript_quality),
        }

    if nonverbal_highlights and not scenes_a:
        context.update(max(0.55, float(context.job.progress)), "Finding visual cuts for non-verbal highlights")
        try:
            scenes_a = detect_scenes(source_a, settings, cancel_check=context.check_cancelled)
        except JobCancelled:
            raise
        except Exception:
            scenes_a = []
        context.checkpoint()

    language = transcript.get("language")
    if not language or language == "unknown":
        language = language_from_text(transcript.get("text", ""), "en")
    brief["language"] = language
    if (
        vision.get("focus_safe") is True
        and vision.get("focus")
        and project.get("settings", {}).get("auto_reframe", True)
        and _effective_embedded_candidate(project, vision) is None
    ):
        project.setdefault("manual", {}).setdefault("crop", {}).setdefault("A", {}).update(vision["focus"])

    # Persist the expensive reusable context before Story AI starts. If a local
    # model fails or CUTROOM closes during a later pass, retrying can reuse the
    # transcript/audio/vision instead of processing a long recording again.
    if (
        not reusable_context
        or (need_vision and not reusable_vision)
        or transcript_upgraded
    ) and not project.get("draft"):
        context_snapshot = {
            "cache_fingerprints": cache_fingerprints,
            "audio_source": analysis_audio_slot,
            "audio_timeline_offset": round(analysis_timeline_offset, 3),
            "transcript": copy.deepcopy(transcript),
            "transcript_quality": copy.deepcopy(transcript_quality),
            "segments": copy.deepcopy(transcript.get("segments", [])),
            "story_beats": [],
            "story_hierarchy": None,
            "audio": copy.deepcopy(sound_profile),
            "silences": copy.deepcopy(sound_profile.get("ranges", {}).get("silence", [])),
            "scenes": {"A": copy.deepcopy(scenes_a), "B": []},
            "sync": copy.deepcopy(sync),
            "vision": copy.deepcopy(vision),
            "thumbnails": {"A": []},
            "waveform": None,
            "engine": "context_cache",
            "status": "context_ready",
            "warnings": (
                ([{"type": "transcription", "message": transcription_warning}] if transcription_warning else [])
                + ([copy.deepcopy(transcript_fallback)] if transcript_fallback else [])
                + ([{
                    "type": "nonverbal_highlights",
                    "message": "No clear speech was detected; highlights use measured audio activity and visual cuts.",
                }] if nonverbal_highlights and not transcript_fallback else [])
                + ([{"type": "source_b", "message": source_b_warning}] if source_b_warning else [])
            ),
        }

        def commit_context(latest: dict[str, Any]) -> None:
            if latest.get("draft"):
                return
            if stable_fingerprint("director-manual-input", latest.get("manual") or {}) != manual_input_fingerprint:
                raise RuntimeError("project_changed_during_analysis")
            latest_brief = _effective_brief(latest)
            latest_paths: dict[str, Path | None] = {}
            for slot in ("A", "B"):
                latest_source = latest.get("sources", {}).get(slot)
                latest_paths[slot] = (
                    store.project_dir(project_id) / latest_source["relative_path"]
                    if latest_source and latest_source.get("relative_path")
                    else None
                )
            latest_fingerprints = build_analysis_cache_fingerprints(latest, settings, latest_brief, latest_paths)
            if not cache_fingerprints_match(
                latest_fingerprints,
                cache_fingerprints,
                ("pipeline", "source", "transcript", "scenes", "vision"),
            ):
                raise RuntimeError("project_changed_during_analysis")
            latest["analysis"] = copy.deepcopy(context_snapshot)

        context.checkpoint()
        store.update(project_id, commit_context)

    context.update(0.58, "Understanding the story")
    story_beats: list[dict[str, Any]] = []
    story_hierarchy: dict[str, Any] | None = None
    normalized_editorial_transcript, _ = _normalize_transcript(transcript, spoken_language, duration)
    editorial_transcript_fingerprint = stable_fingerprint(
        "director-editorial-transcript", normalized_editorial_transcript["segments"],
    )
    cached_editorial = (cached_analysis or {}).get("editorial_cache")
    reusable_editorial = bool(
        reusable_context
        and not transcript_upgraded
        and isinstance(cached_editorial, dict)
        and isinstance(cached_editorial.get("decision"), dict)
        and isinstance((cached_analysis or {}).get("segments"), list)
        and cached_editorial.get("transcript_fingerprint") == editorial_transcript_fingerprint
        and cache_fingerprints_match(cached_fingerprints, cache_fingerprints, ("story",))
    )
    if goal in {"short", "podcast"} and not transcript.get("segments") and not nonverbal_highlights:
        detail = f" ({transcription_warning})" if transcription_warning else ""
        raise StoryPlanningError("Story AI needs a usable transcript before it can understand and edit the recording." + detail)
    if nonverbal_highlights:
        segments = []
        decision = {
            "keep_ids": [],
            "remove_ids": [],
            "highlight_ids": [],
            "title": "היילייטים מהסטרים" if language == "he" else "Stream highlights",
            "summary": (
                "העריכה נבנתה מרגעי האודיו והמעברים החזקים ביותר, ללא המצאת תמלול."
                if language == "he"
                else "Built from the strongest measured audio moments and visual transitions, without inventing a transcript."
            ),
            "opening_id": None,
            "closing_id": None,
        }
        engine = "audio_visual_highlights"
    elif audio_cleanup_fallback or (goal == "youtube" and youtube_cleanup_only):
        segments = list(transcript.get("segments", []))
        decision = {
            "keep_ids": [item.get("id") for item in segments if item.get("id")],
            "remove_ids": [],
            "highlight_ids": [],
            "title": project.get("name") or "YouTube cleanup",
            "summary": (
                (
                    "לא נמצא דיבור אמין, לכן CUTROOM שמרה על הסדר וניקתה רק שקט שנמדד — ללא Storyline או כתוביות מומצאות."
                    if language == "he"
                    else "No reliable speech was found, so CUTROOM preserved chronology and removed only measured dead air without inventing a Storyline or captions."
                )
                if audio_cleanup_fallback
                else "Kept the original structure and removed only measured dead air."
            ),
            "opening_id": segments[0].get("id") if segments else None,
            "closing_id": segments[-1].get("id") if segments else None,
        }
        engine = "audio_cleanup"
    elif reusable_editorial:
        # A chapter cache only saves summarization: invoking the planner still
        # runs several model passes. An unchanged edit/variation can reuse the
        # complete decision too, provided the brief and corrected transcript
        # both match. Manual timeline choices are applied below to this base.
        context.checkpoint("Reusing the existing story decisions")
        segments = copy.deepcopy(cached_analysis["segments"])
        decision = copy.deepcopy(cached_editorial["decision"])
        story_beats = copy.deepcopy(cached_analysis.get("story_beats") or [])
        story_hierarchy = copy.deepcopy(cached_analysis.get("story_hierarchy"))
        engine = str(cached_analysis.get("engine") or "deterministic")
    else:
        editorial, engine = _plan_edit_with_cancel(
            context,
            transcript.get("segments", []),
            settings,
            brief,
            progress=lambda value, message: context.update(0.58 + value * 0.18, message),
            story_cache=(cached_analysis.get("story_hierarchy") if reusable_story and cached_analysis else None),
        )
        segments = editorial["segments"]
        decision = editorial["decision"]
        story_beats = editorial.get("story_beats", [])
        story_hierarchy = editorial.get("story_hierarchy")

    if source_b:
        if reusable_context and cached_analysis:
            cached_sync = cached_analysis.get("sync") if isinstance(cached_analysis.get("sync"), dict) else None
            if sync is None and cached_sync and not (
                manual_sync_offset is None and str(cached_sync.get("method") or "") in {"manual", "source_tracks"}
            ):
                sync = copy.deepcopy(cached_sync)
            scenes_b = list((cached_analysis.get("scenes") or {}).get("B") or [])
        if not sync:
            context.update(0.77, "Synchronizing both cameras")
            try:
                sync = synchronize_sources(
                    source_a,
                    source_b,
                    settings,
                    progress=lambda value, message: context.update(0.77 + value * 0.08, message),
                    cancel_check=context.check_cancelled,
                )
            except JobCancelled:
                raise
            except Exception as exc:  # fallback remains editable
                sync = {"offset": 0.0, "confidence": 0.0, "method": "fallback", "warning": str(exc)}
                source_b_warning = source_b_warning or f"Could not auto-sync source B: {type(exc).__name__}: {exc}"
            context.checkpoint()
        if not scenes_b:
            try:
                scenes_b = detect_scenes(source_b, settings, cancel_check=context.check_cancelled)
            except JobCancelled:
                raise
            except Exception as exc:
                scenes_b = []
                source_b_warning = source_b_warning or f"Could not analyze source B scenes: {type(exc).__name__}: {exc}"
            context.checkpoint()

    sync = _safe_automatic_sync(sync)

    context.update(0.86, "Building one coherent draft")
    audio_candidates, audio_gain_plan, audio_counts = build_audio_actions(sound_profile, policy, duration)
    if audio_cleanup_fallback or (goal == "youtube" and youtube_cleanup_only):
        candidates = list(audio_candidates)
    else:
        candidates = [*audio_candidates, *_cut_candidates(segments, decision, pace)]
        if goal != "short":
            candidates = [item for item in candidates if item.get("reason") != "low_value"]

    # Shorts are selections from the entire recording, not "the first N seconds".
    # Build a story-shaped set of source passages first, then apply measured audio
    # cleanup and defensible transcript cleanup inside those passages.
    if goal == "short" and duration > target_duration:
        selection_policy = ((brief.get("style_profile") or {}).get("selection_policy") or {})
        story_keep = (
            _select_audio_highlight_ranges(
                sound_profile,
                duration,
                target_duration,
                scenes_a,
                selection_seed=selection_seed,
                pace=pace,
                selection_policy=selection_policy,
            )
            if nonverbal_highlights
            else _select_short_story_ranges(
                segments,
                decision,
                duration,
                target_duration,
                scenes_a,
                selection_seed=selection_seed,
                force_variation=normalized_selection_variant > 0,
                selection_policy=selection_policy,
                story_beats=story_beats,
            )
        )
        story_cuts = invert_ranges(story_keep, duration)
        cuts, counts = _short_cleanup_cuts_with_floor(
            story_cuts,
            _style_cleanup_candidates(candidates, story_keep, selection_policy),
            project.get("manual", {}).get("cuts", []),
            duration,
            target_duration,
        )
        counts["story_selection"] = len(story_keep)
        cuts, target_trim_count = _enforce_short_target(cuts, segments, decision, duration, target_duration)
        if target_trim_count:
            counts["target_trim"] = target_trim_count
    else:
        cuts, counts = _bounded_cuts(
            candidates,
            duration,
            pace,
            goal,
            target_duration,
            project.get("manual", {}).get("cuts", []),
        )

    # Explicit restores/deletes are the final authority, including after the
    # target-duration pass. Rebuilding must not silently undo a user's restore.
    cuts = apply_timeline_overrides(cuts, project.get("manual"))
    for reason in ("quiet_audio", "loud_audio", "clipping"):
        count = int(audio_counts.get(reason, 0))
        if count:
            counts[reason] = counts.get(reason, 0) + count
    keep_ranges = invert_ranges(cuts, duration)
    if not keep_ranges:
        keep_ranges = [{"start": 0.0, "end": duration}]
        cuts = []
    requested_layout = str(brief.get("layout", "auto"))
    embedded_candidate = _effective_embedded_candidate(project, vision)
    embedded_layout_confirmed = False
    editorial_boundaries = [float(item["start"]) for item in segments[1:]]
    camera_plan, embedded_layout_confirmed = _camera_plan_for_layout(
        keep_ranges,
        bool(source_b),
        requested_layout,
        pace,
        scenes_a + editorial_boundaries,
        embedded_candidate,
    )
    ai_camera_plan = copy.deepcopy(camera_plan)
    manual_camera_overrides = project.get("manual", {}).get("camera_overrides") or []
    if isinstance(manual_camera_overrides, list):
        camera_plan = apply_camera_overrides(
            ai_camera_plan,
            keep_ranges,
            manual_camera_overrides,
            has_b=bool(source_b),
        )
    output_duration = range_duration(keep_ranges)
    quality_review = _edit_quality_review(transcript_quality, story_hierarchy, segments, keep_ranges, duration)
    old_keep_ranges = (project.get("draft") or {}).get("keep_ranges") or []
    variation_changed = keep_ranges != old_keep_ranges
    decisions = _aggregate_decisions(counts, duration, output_duration, bool(source_b), sync)
    if any(str(item.get("camera")) == "embedded_stack" for item in camera_plan):
        decisions.append({"type": "smart_layout", "count": 1})
    draft = {
        "engine": engine,
        "created_at": project.get("updated_at"),
        "language": language,
        "title": decision.get("title") or project.get("name"),
        "summary": decision.get("summary"),
        "pace": pace,
        "goal": goal,
        "aspect": brief.get("aspect", "9:16"),
        "layout": requested_layout,
        "embedded_layout_confirmed": embedded_layout_confirmed,
        "target_duration": target_duration,
        "source_duration": duration,
        "output_duration": output_duration,
        "removed_duration": round(max(0.0, duration - output_duration), 3),
        "cuts": cuts,
        "keep_ranges": keep_ranges,
        "ai_camera_plan": ai_camera_plan,
        "camera_plan": camera_plan,
        "highlight_ids": decision.get("highlight_ids", []),
        "decisions": decisions[:9],
        "audio_plan": audio_gain_plan,
        "audio_policy": policy,
        "audio_source": analysis_audio_slot,
        "audio_profile": sound_profile.get("summary", {}),
        "status": "ready",
        "partial_ai": bool(transcription_warning or nonverbal_highlights or transcript_fallback or quality_review["needs_review"]),
        "quality_review": quality_review,
        "edit_style": brief.get("edit_style", "smart"),
        "selection_strategy": SELECTION_STRATEGY_VERSION,
        "selection_variant": normalized_selection_variant,
        "selection_seed": selection_seed,
    }
    reel_candidates = _build_reel_candidates(
        project,
        draft,
        segments,
        story_beats,
        scenes_a + [_finite_number(item.get("start")) for item in segments[1:]],
        embedded_candidate,
    )
    if reel_candidates:
        draft["reel_candidates"] = reel_candidates
        draft["active_reel_candidate"] = "director_pick"
    # Heavy preview assets are no longer generated inside the Director. They are
    # optional presentation data and must never delay the actual edit.
    thumbnails: list[str] = []
    waveform = None
    context.update(0.95, "Saving the edit")
    analysis = {
        "cache_fingerprints": cache_fingerprints,
        "audio_source": analysis_audio_slot,
        "audio_timeline_offset": round(analysis_timeline_offset, 3),
        "transcript": transcript,
        "transcript_quality": transcript_quality,
        "segments": segments,
        "story_beats": story_beats,
        "story_hierarchy": story_hierarchy,
        "editorial_cache": {
            "transcript_fingerprint": editorial_transcript_fingerprint,
            "decision": copy.deepcopy(decision),
        },
        "audio": sound_profile,
        "silences": sound_profile.get("ranges", {}).get("silence", []),
        "scenes": {"A": scenes_a, "B": scenes_b},
        "sync": sync,
        "vision": vision,
        "thumbnails": {"A": thumbnails},
        "waveform": waveform,
        "engine": engine,
        "warnings": (
            ([{"type": "transcription", "message": transcription_warning}] if transcription_warning else [])
            + ([copy.deepcopy(transcript_fallback)] if transcript_fallback else [])
            + ([{
                "type": "nonverbal_highlights",
                "message": "No clear speech was detected; highlights use measured audio activity and visual cuts.",
            }] if nonverbal_highlights and not transcript_fallback else [])
            + ([{"type": "audio", "message": sound_profile.get("warning")}] if sound_profile.get("warning") else [])
            + ([{
                "type": "limited_highlight_evidence",
                "message": (
                    f"Found {output_duration:.0f} seconds of distinct audio-backed highlights for a "
                    f"{target_duration:.0f}-second target. Kept a shorter edit to avoid padding it with quiet footage."
                ),
            }] if nonverbal_highlights and output_duration < target_duration * 0.80 else [])
            + ([{"type": "source_b", "message": source_b_warning}] if source_b_warning else [])
            + quality_review["warnings"]
        ),
    }
    # Source preparation is intentionally concurrent with the Director. Reload the
    # latest project before committing the draft so a finished proxy/preparation
    # update cannot be overwritten by the older project snapshot used for analysis.
    context.checkpoint()

    def commit_analysis(latest: dict[str, Any]) -> None:
        proposed = proposed_inputs(latest)
        latest_brief = _effective_brief(proposed)
        latest_paths: dict[str, Path | None] = {}
        for slot in ("A", "B"):
            latest_source = latest.get("sources", {}).get(slot)
            latest_paths[slot] = (
                store.project_dir(project_id) / latest_source["relative_path"]
                if latest_source and latest_source.get("relative_path")
                else None
            )
        latest_fingerprints = build_analysis_cache_fingerprints(
            proposed,
            settings,
            latest_brief,
            latest_paths,
        )
        manual_changed = stable_fingerprint("director-manual-input", latest.get("manual") or {}) != manual_input_fingerprint
        if manual_changed or not cache_fingerprints_match(
            latest_fingerprints,
            cache_fingerprints,
            ("pipeline", "source", "transcript", "scenes", "vision", "story"),
        ):
            raise RuntimeError("project_changed_during_analysis")
        unchanged_variation = normalized_selection_variant > 0 and not variation_changed
        if not unchanged_variation:
            validate_media_bounds({**proposed, "draft": draft})
        context.commit()
        latest.setdefault("settings", {}).update(staged_brief or {})
        if source_mixer_patch:
            latest.setdefault("manual", {}).setdefault("source_mixer", {}).update(source_mixer_patch)
        latest.setdefault("settings", {})["aspect"] = brief.get("aspect", latest.get("settings", {}).get("aspect", "9:16"))
        if goal == "youtube" and explicit_source_layout is None and not embedded_layout_confirmed:
            latest["settings"]["layout"] = "A"
        latest["analysis"] = analysis
        if unchanged_variation:
            # Keep the user's timeline, export state and Undo history when an
            # alternate request yields exactly the same source selection.
            return
        latest["draft"] = draft
        # A rebuilt Draft supersedes timeline snapshots from the old Draft. Keep
        # durable manual intent, but never let Undo restore an incompatible cut.
        latest_manual = latest.setdefault("manual", {})
        latest_manual.pop("_history", None)
        latest_manual["history"] = {"undo_count": 0, "redo_count": 0}
        if (
            vision.get("focus_safe") is True
            and vision.get("focus")
            and latest.get("settings", {}).get("auto_reframe", True)
            and _effective_embedded_candidate(latest, vision) is None
        ):
            latest.setdefault("manual", {}).setdefault("crop", {}).setdefault("A", {}).update(vision["focus"])
        # The detected language is stored on transcript/draft. Keep the user's
        # requested "auto" input stable, otherwise this write invalidates the
        # transcript/story fingerprints we just saved on the next rebuild.

    # After this boundary a late cancellation must not hide a Draft that was
    # successfully saved. The UI will receive a completed authoritative job.
    saved_project = store.update(project_id, commit_analysis)
    message = "Your first edit is ready"
    if normalized_selection_variant > 0 and not variation_changed:
        message = "No different cut found; your edit was kept"
    context.update(1.0, message)
    result = {"project_id": project_id, "draft": saved_project["draft"], "engine": engine}
    if normalized_selection_variant > 0:
        result["variation_changed"] = variation_changed
    return result


def _plan_edit_with_cancel(
    context: JobContext,
    transcript_segments: list[dict[str, Any]],
    settings: Settings,
    brief: dict[str, Any],
    progress: Callable[[float, str], None],
    story_cache: dict[str, Any] | None,
) -> tuple[dict[str, Any], str]:
    """Pass cancellation into current planners without breaking older hooks."""

    try:
        return plan_edit(
            transcript_segments,
            settings,
            brief,
            progress=progress,
            story_cache=story_cache,
            cancel_check=context.check_cancelled,
        )
    except TypeError as exc:
        if "cancel_check" not in str(exc):
            raise
        return plan_edit(
            transcript_segments,
            settings,
            brief,
            progress=progress,
            story_cache=story_cache,
        )


def refine_project(context: JobContext, project_id: str, store: ProjectStore, settings: Settings, command: str) -> dict[str, Any]:
    context.checkpoint()
    project = store.load(project_id)
    current = project.get("settings", {})
    patch: dict[str, Any] = {}
    selection_variant = 0
    restore_focus_layout = False
    previous_layout_present = False
    previous_layout: Any = None
    staged_mixer: dict[str, Any] | None = None
    if command == "shorter":
        patch["target_duration"] = max(8, round(float(current.get("target_duration", 60)) * 0.78))
        patch["pace"] = "dynamic"
    elif command == "keep_more":
        patch["target_duration"] = min(float(project["sources"]["A"]["duration"]), round(float(current.get("target_duration", 60)) * 1.25))
        patch["pace"] = "gentle"
    elif command == "more_energy":
        patch["pace"] = "dynamic"
    elif command == "fewer_switches":
        patch["pace"] = "gentle"
    elif command == "focus_speaker":
        sources = project.get("sources") or {}
        if sources.get("B"):
            original_mixer = (project.get("manual") or {}).get("source_mixer") or {}
            previous_layout_present = "default_layout" in original_mixer
            previous_layout = original_mixer.get("default_layout")
            # This one-click refinement is a newer explicit framing choice. Keep
            # it in the same source of truth used by Studio and the next rebuild.
            def focus_camera(current_project: dict[str, Any]) -> None:
                current_mixer = current_project.setdefault("manual", {}).setdefault("source_mixer", {})
                current_mixer["default_layout"] = "camera"

            if (project.get("manual") or {}).get("media_clips"):
                staged_mixer = {"default_layout": "camera"}
            else:
                store.update(project_id, focus_camera)
                restore_focus_layout = True
        else:
            patch["layout"] = "A"
    elif command == "new_variation":
        previous_variant = (project.get("draft") or {}).get("selection_variant", 0)
        try:
            selection_variant = max(0, int(previous_variant)) + 1
        except (TypeError, ValueError, OverflowError):
            selection_variant = 1
    else:
        raise ValueError("Unknown refinement command")
    try:
        if command == "new_variation":
            return analyze_project(
                context,
                project_id,
                store,
                settings,
                patch,
                selection_variant=selection_variant,
            )
        if staged_mixer:
            return analyze_project(context, project_id, store, settings, patch, source_mixer_patch=staged_mixer)
        return analyze_project(context, project_id, store, settings, patch)
    except Exception:
        if restore_focus_layout:
            def rollback_focus(current_project: dict[str, Any]) -> None:
                current_mixer = current_project.setdefault("manual", {}).setdefault("source_mixer", {})
                # Do not overwrite a newer explicit user action from another API
                # client if it raced with the failed refinement.
                if current_mixer.get("default_layout") != "camera":
                    return
                if previous_layout_present:
                    current_mixer["default_layout"] = previous_layout
                else:
                    current_mixer.pop("default_layout", None)

            store.update(project_id, rollback_focus)
        raise
