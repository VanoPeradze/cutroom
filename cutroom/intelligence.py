from __future__ import annotations

import contextlib
import copy
import functools
import json
import logging
import math
import queue
import re
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Callable

from .cache_keys import stable_fingerprint
from .ai_runtime import OLLAMA_RESPONSE_BYTES, open_ollama, read_ollama_json
from .config import Settings
from .edit_styles import enrich_brief_with_style, required_story_roles, required_story_role_orders
from .instruction_contract import (assert_instruction_contract, build_instruction_contract,
                                   evaluate_instruction_contract, single_source_passage_requested,
                                   explicit_source_continuity_requested, effective_duration_bounds, single_output_requested)
from .story_budget import StoryBudgetError, StoryPlanningError, story_duration_cost
from .story_constraints import story_constraint_feasibility, story_final_ending_domain
from .story_evidence import EVIDENCE_POLICY_VERSION, build_story_evidence_catalog, validate_story_evidence
from .story_summary import SUMMARY_SOURCE, extractive_story_summary
from .source_continuity import continuous_source_playback
from .story_candidates import (CANDIDATE_POLICY_VERSION, project_short_source_units,
                               source_identity_rows, candidate_projection_fields, neighboring_source_utterances)
from .story_spans import (
    SOURCE_SPAN_POLICY_VERSION, SOURCE_SPAN_SUMMARY_SOURCE, build_source_span_constraints,
    validate_source_span_constraints, whole_utterance_story_summary,
)
from .utils import clamp, merge_ranges, normalize_text, range_duration

STORY_CACHE_PIPELINE = "hierarchical-story-2026-10-23.v30.continuous-playback"
SINGLE_PASSAGE_PURPOSE = "self_contained_passage"
SINGLE_PASSAGE_WINDOW_MAX_UNITS = 48
SINGLE_PASSAGE_WINDOW_MAX_CALLS = 8
SINGLE_PASSAGE_WINDOW_SECONDS = 180
CRITIC_REVIEW_CONTRACT = "critic-review-2026-10-21.v26.complete-object-unions"
EXTRACTIVE_ROUGH_CUT_AUTHORITY = "extractive_rough_cut"
EXTRACTIVE_ROUGH_CUT_ENGINE = "chronological_extractive_rough_cut"


def _critic_action_sets(critic):
    """A new critic requests actions; only final review can authorize them."""
    if critic.get("action_authority") == "proposal":
        return set(), set()
    if critic.get("action_authority") == "final":
        return set(critic.get("accepted_added") or []), set(critic.get("accepted_removed") or [])
    # Legacy plugin/previously accepted fixtures retain their prior meaning.
    # The review-contract version prevents old editorial caches gaining new
    # production authority without rebuilding the review.
    return set(critic.get("requested_added") or []), set(critic.get("requested_removed") or [])

FILLERS: dict[str, set[str]] = {
    "en": {"um", "uh", "erm", "like", "basically", "actually", "literally", "you know", "i mean", "so"},
    "he": {"אמ", "אה", "כאילו", "בעצם", "ממש", "אתה יודע", "זאת אומרת", "אז"},
    "ar": {"يعني", "امم", "آه", "بصراحة", "في الواقع", "طيب"},
    "es": {"eh", "em", "este", "pues", "o sea", "básicamente", "entonces"},
    "fr": {"euh", "ben", "genre", "en fait", "donc", "voilà"},
    "ru": {"эм", "э", "ну", "как бы", "короче", "в общем", "значит"},
}

PACE_LIMITS = {
    "gentle": {"max_remove": 0.18, "min_segment": 0.18, "silence_pad": 0.22},
    "balanced": {"max_remove": 0.34, "min_segment": 0.16, "silence_pad": 0.14},
    "dynamic": {"max_remove": 0.50, "min_segment": 0.12, "silence_pad": 0.08},
}

STORY_CUES: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "hook": ("why", "here's", "the result", "the problem", "watch", "important", "biggest", "secret"),
        "example": ("for example", "for instance", "look at", "here you can see", "let me show"),
        "result": ("the result", "what happened", "this means", "so now", "therefore", "that's why"),
        "conclusion": ("in the end", "finally", "to sum up", "the point is", "so the answer", "that's it"),
    },
    "he": {
        "hook": ("למה", "התוצאה", "הבעיה", "הדבר החשוב", "הכי חשוב", "תראו", "הסוד", "מה שקורה"),
        "example": ("לדוגמה", "למשל", "תראו כאן", "אני אראה", "אפשר לראות", "בואו נראה"),
        "result": ("התוצאה", "מה שקרה", "זה אומר", "ולכן", "בגלל זה", "מכאן"),
        "conclusion": ("בסוף", "לסיכום", "המסקנה", "השורה התחתונה", "אז התשובה", "זה הכל"),
    },
    "ar": {
        "hook": ("لماذا", "النتيجة", "المشكلة", "المهم", "شاهد", "السر"),
        "example": ("مثلا", "على سبيل المثال", "انظر", "سأريك"),
        "result": ("النتيجة", "هذا يعني", "لذلك", "لهذا السبب"),
        "conclusion": ("في النهاية", "باختصار", "الخلاصة", "إذن"),
    },
}


def tokens(text: str) -> list[str]:
    return [token for token in normalize_text(text).split() if token]


def filler_ratio(text: str, language: str) -> tuple[float, list[str]]:
    language = language if language in FILLERS else "en"
    normalized = f" {normalize_text(text)} "
    found: list[str] = []
    for filler in sorted(FILLERS[language], key=len, reverse=True):
        pattern = rf"(?<!\w){re.escape(filler)}(?!\w)"
        matches = re.findall(pattern, normalized)
        found.extend([filler] * len(matches))
    count = max(1, len(tokens(text)))
    return min(1.0, len(found) / count), found


def similarity(a: str, b: str) -> float:
    aa, bb = normalize_text(a), normalize_text(b)
    if not aa or not bb:
        return 0.0
    sequence = SequenceMatcher(None, aa, bb).ratio()
    ta, tb = set(aa.split()), set(bb.split())
    jaccard = len(ta & tb) / max(1, len(ta | tb))
    prefix = 1.0 if " ".join(aa.split()[:5]) == " ".join(bb.split()[:5]) and len(aa.split()) >= 4 else 0.0
    return round(max(sequence, (sequence + jaccard) / 2, prefix * 0.86), 4)


def enrich_segments(segments: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for item in segments:
        segment = dict(item)
        text = str(segment.get("text", ""))
        segment_tokens = tokens(text)
        ratio, fillers = filler_ratio(text, language)
        duration = max(0.001, float(segment["end"]) - float(segment["start"]))
        repeat_score = similarity(previous.get("text", ""), text) if previous else 0.0
        punctuation_complete = bool(re.search(r"[.!?…؟]$", text.strip()))
        false_start = (
            (duration < 2.4 and len(segment_tokens) <= 8 and not punctuation_complete and repeat_score > 0.45)
            or repeat_score >= 0.76
        )
        speech_density = len(segment_tokens) / duration
        confidence = max(0.0, min(1.0, 1.0 + float(segment.get("avg_logprob", -0.2)) / 2.5))
        score = 0.42
        score += min(0.25, speech_density / 16.0)
        score += 0.12 if punctuation_complete else 0.0
        score += 0.13 * confidence
        score -= ratio * 0.55
        score -= repeat_score * 0.44
        score -= 0.38 if false_start else 0.0
        segment.update({
            "filler_ratio": round(ratio, 4),
            "fillers": fillers,
            "repeat_score": repeat_score,
            "false_start": false_start,
            "speech_density": round(speech_density, 3),
            "editorial_score": round(clamp(score, 0.0, 1.0), 4),
        })
        enriched.append(segment)
        previous = segment
    return enriched


def _token_jaccard(a: str, b: str) -> float:
    aa, bb = set(tokens(a)), set(tokens(b))
    if not aa or not bb:
        return 0.0
    return len(aa & bb) / max(1, len(aa | bb))


def _cue_scores(text: str, language: str) -> tuple[float, str | None]:
    lexicon = STORY_CUES.get(language, STORY_CUES["en"])
    normalized = normalize_text(text)
    best_role: str | None = None
    best = 0.0
    for role, phrases in lexicon.items():
        hits = sum(1 for phrase in phrases if normalize_text(phrase) in normalized)
        score = min(1.0, hits * 0.42)
        if score > best:
            best = score
            best_role = role
    # Questions are often useful hooks even without a cue dictionary hit.
    if ("?" in text or "؟" in text) and best < 0.55:
        best = 0.55
        best_role = "hook"
    return best, best_role


def _sentence_ending_complete(text: str) -> bool:
    return bool(re.search(r"[.!?\u2026\u3002\uff01\uff1f][\"'\u201d\u2019\u00bb)\]]*$", text.strip()))


def build_story_beats(
    segments: list[dict[str, Any]], language: str, *, target_seconds: float | None = None,
    independent_asr_entries: bool = False,
    allow_unreviewed_long_spans: bool = False,
) -> list[dict[str, Any]]:
    """Group transcript segments into editorial ideas rather than isolated lines.

    A two-hour source may have thousands of Whisper segments. CUTROOM should reason
    over 15–35 second ideas (beats), then use real segment boundaries for the final
    cuts. Short targets additionally expose smaller complete-sentence choices to
    the planner and critic, rather than trimming an approved idea after review.
    """
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: (float(item.get("start", 0)), float(item.get("end", 0))))
    requested_target = float(target_seconds) if target_seconds is not None else 0.0
    short_beat_seconds = max(4.0, min(28.0, requested_target / 2)) if 0 < requested_target < float("inf") else None
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_words = 0
    for item in ordered:
        if current:
            gap = float(item.get("start", 0)) - float(current[-1].get("end", 0))
            current_duration = float(current[-1]["end"]) - float(current[0]["start"])
            previous_complete = bool(re.search(r"[.!?…؟]$", str(current[-1].get("text", "")).strip()))
            # Whisper/VAD often leaves 1-2 second pauses between lines.  Treat those
            # as part of the same editorial idea unless the current beat already has
            # enough substance.  This keeps long recordings at idea-level context
            # instead of degenerating into one beat per sentence.
            should_break = (
                gap >= 4.0
                or current_duration >= 28.0
                or (gap >= 1.25 and current_duration >= 14.0)
                or (gap >= 2.4 and current_duration >= 8.0)
                or (current_duration >= 16.0 and current_words >= 72 and previous_complete)
                or (short_beat_seconds is not None and current_duration >= short_beat_seconds
                    and _sentence_ending_complete(str(current[-1].get("text", ""))))
            )
            if short_beat_seconds is not None:
                # Even the legacy 28-second cap must not cut a continuation in
                # the middle of a sentence for a Short. An indivisible long
                # sentence is an honest duration constraint for later review.
                should_break = should_break and _sentence_ending_complete(str(current[-1].get("text", "")))
            if should_break:
                groups.append(current)
                current = []
                current_words = 0
        current.append(item)
        current_words += len(tokens(str(item.get("text", ""))))
        if (not allow_unreviewed_long_spans and short_beat_seconds is not None
                and float(current[-1]["end"]) - float(current[0]["start"]) > 90.0
                and not _sentence_ending_complete(str(current[-1].get("text", "")))):
            raise StoryPlanningError("A source passage exceeds 90 seconds without a complete sentence boundary; review the transcript before creating a Short.")
    if current:
        groups.append(current)

    total_duration = max(float(ordered[-1].get("end", 0)), 0.001)
    beats: list[dict[str, Any]] = []
    previous_texts: list[str] = []
    for index, group in enumerate(groups):
        text = " ".join(str(item.get("text", "")).strip() for item in group if str(item.get("text", "")).strip())
        if not text:
            continue
        start = float(group[0]["start"])
        end = float(group[-1]["end"])
        scores = [float(item.get("editorial_score", 0.5)) for item in group]
        cue_score, cue_role = _cue_scores(text, language)
        similarity_to_recent = max((_token_jaccard(text, prior) for prior in previous_texts[-3:]), default=0.0)
        novelty = clamp(1.0 - similarity_to_recent, 0.0, 1.0)
        average = sum(scores) / max(1, len(scores))
        maximum = max(scores) if scores else average
        importance = clamp(average * 0.52 + maximum * 0.22 + cue_score * 0.18 + novelty * 0.08, 0.0, 1.25)
        beat = {
            "id": f"b{index + 1:04d}",
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(max(0.0, end - start), 3),
            "segment_ids": [str(item["id"]) for item in group],
            "text": text,
            "position": round(start / total_duration, 4),
            "editorial_score": round(importance, 4),
            "cue_score": round(cue_score, 4),
            "role_hint": cue_role,
            "novelty": round(novelty, 4),
        }
        beats.append(beat)
        previous_texts.append(text)
    if short_beat_seconds is None:
        return beats
    units = project_short_source_units(beats, ordered)
    if independent_asr_entries:
        from .story_candidates import expose_complete_asr_entries
        units = expose_complete_asr_entries(units, ordered)
    return units


def compact_story_beats(beats: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    limit = max(24, int(limit))
    if len(beats) <= limit:
        return list(beats)
    selected: set[int] = set()
    edge = min(5, max(2, limit // 16))
    selected.update(range(edge))
    selected.update(range(max(0, len(beats) - edge), len(beats)))
    # Preserve role-bearing and globally strong ideas.
    ranked = sorted(
        range(len(beats)),
        key=lambda index: (
            1 if beats[index].get("role_hint") else 0,
            float(beats[index].get("editorial_score", 0.0)),
            float(beats[index].get("novelty", 0.0)),
        ),
        reverse=True,
    )
    for index in ranked[: max(12, limit // 2)]:
        selected.add(index)
    # Then guarantee uniform coverage of the recording.
    slots = max(1, limit - len(selected))
    for slot in range(slots):
        index = min(len(beats) - 1, int(round(slot * (len(beats) - 1) / max(1, slots - 1))))
        selected.add(index)
    if len(selected) > limit:
        priority = sorted(
            selected,
            key=lambda index: (
                index < edge or index >= len(beats) - edge,
                bool(beats[index].get("role_hint")),
                float(beats[index].get("editorial_score", 0.0)),
            ),
            reverse=True,
        )
        selected = set(priority[:limit])
    return [beats[index] for index in sorted(selected)]


def compact_segments_for_llm(segments: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Cover the whole recording instead of truncating the transcript head."""
    limit = max(24, int(limit))
    if len(segments) <= limit:
        return list(segments)
    selected: set[int] = set()
    edge = min(8, max(3, limit // 12))
    selected.update(range(edge))
    selected.update(range(max(0, len(segments) - edge), len(segments)))
    strong_count = max(8, limit // 3)
    ranked = sorted(
        range(len(segments)),
        key=lambda index: (float(segments[index].get("editorial_score", 0.0)), -float(segments[index].get("repeat_score", 0.0))),
        reverse=True,
    )[:strong_count]
    for index in ranked:
        selected.add(index)
        if len(selected) < limit and index > 0:
            selected.add(index - 1)
        if len(selected) < limit and index + 1 < len(segments):
            selected.add(index + 1)
    remaining = max(0, limit - len(selected))
    if remaining:
        step = (len(segments) - 1) / max(1, remaining - 1) if remaining > 1 else len(segments) / 2
        for slot in range(remaining):
            selected.add(min(len(segments) - 1, int(round(slot * step))))
    if len(selected) > limit:
        priority = []
        for index in selected:
            edge_priority = 2 if index < edge or index >= len(segments) - edge else 0
            strength = float(segments[index].get("editorial_score", 0.0))
            priority.append((edge_priority, strength, index))
        selected = {item[2] for item in sorted(priority, reverse=True)[:limit]}
    return [segments[index] for index in sorted(selected)]


class StoryAIUnavailableError(RuntimeError):
    """A semantic edit was requested but the local Story AI is not ready."""

    outcome = "technical_error"

    def __init__(self, message: str):
        super().__init__(message)
        self.diagnostic = {"kind": "story_runtime", "outcome": self.outcome,
                           "reason": "story_ai_unavailable", "applied_to_timeline": False}


class StoryResponseLimitError(StoryPlanningError):
    """The bounded local response ended before a complete JSON answer."""


class _InvalidStorySelectionError(StoryPlanningError):
    """A validated review left no material; do not restore rejected source."""


_STRING_LIST_SCHEMA = {"type": "array", "items": {"type": "string"}}

CHAPTER_SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "role": {"type": "string"},
                    "key_points": _STRING_LIST_SCHEMA,
                    "key_beat_ids": _STRING_LIST_SCHEMA,
                    "depends_on": _STRING_LIST_SCHEMA,
                    "unresolved_questions": _STRING_LIST_SCHEMA,
                },
                "required": ["id", "title", "summary", "role", "key_points", "key_beat_ids", "depends_on", "unresolved_questions"],
            },
        },
    },
    "required": ["chapters"],
}

GLOBAL_OUTLINE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "premise": {"type": "string"},
        "audience_takeaway": {"type": "string"},
        "story_arc": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "chapter_id": {"type": "string"},
                    "function": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                },
                "required": ["chapter_id", "function", "why_it_matters"],
            },
        },
        "must_keep_chapter_ids": _STRING_LIST_SCHEMA,
        "optional_chapter_ids": _STRING_LIST_SCHEMA,
        "dependency_pairs": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"before": {"type": "string"}, "after": {"type": "string"}, "reason": {"type": "string"}},
                "required": ["before", "after", "reason"],
            },
        },
    },
    "required": ["premise", "audience_takeaway", "story_arc", "must_keep_chapter_ids", "optional_chapter_ids", "dependency_pairs"],
}

STORY_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "narrative": {"type": "string"},
        "slots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "purpose": {"type": "string"},
                    "chapter_ids": _STRING_LIST_SCHEMA,
                    "desired_seconds": {"type": "number"},
                    "reason": {"type": "string"},
                    "required_context_chapter_ids": _STRING_LIST_SCHEMA,
                },
                "required": ["purpose", "chapter_ids", "desired_seconds", "reason", "required_context_chapter_ids"],
            },
        },
    },
    "required": ["narrative", "slots"],
}

STORY_SELECTION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "slot_selections": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"slot_index": {"type": "integer"}, "purpose": {"type": "string"},
                               "primary_beat_ids": _STRING_LIST_SCHEMA, "context_beat_ids": _STRING_LIST_SCHEMA,
                               "primary_evidence_ids": _STRING_LIST_SCHEMA, "context_evidence_ids": _STRING_LIST_SCHEMA,
                               "temporal_witness_id": {"type": "string"}},
                "required": ["slot_index", "purpose", "primary_beat_ids", "context_beat_ids",
                             "primary_evidence_ids", "context_evidence_ids", "temporal_witness_id"],
            },
        },
        "highlight_beat_ids": _STRING_LIST_SCHEMA,
        "opening_beat_id": {"type": "string"},
        "closing_beat_id": {"type": "string"},
        "title": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["slot_selections", "highlight_beat_ids", "opening_beat_id", "closing_beat_id", "title", "summary"],
}

STORY_CRITIC_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "revise"]},
        "add_beat_ids": _STRING_LIST_SCHEMA,
        "remove_beat_ids": _STRING_LIST_SCHEMA,
        "issues": _STRING_LIST_SCHEMA,
        "summary": {"type": "string"},
        "style_notes": {"type": "array", "maxItems": 4, "items": {"type": "string", "maxLength": 240}},
        "action_evidence": {"type": "array", "maxItems": 8, "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "action": {"type": "string", "enum": ["add", "remove"]},
                "beat_id": {"type": "string"},
                "defect_kind": {"type": "string", "enum": ["off_topic", "missing_context", "meaning_change",
                    "incomplete_thought", "chronology_conflict", "explicit_instruction"]},
                "source_evidence_ids": {"type": "array", "minItems": 1, "maxItems": 8,
                    "uniqueItems": True, "items": {"type": "string"}},
                "instruction_quote": {"type": "string", "maxLength": 512},
                "explanation": {"type": "string", "maxLength": 400},
            },
            "required": ["action", "beat_id", "defect_kind", "source_evidence_ids", "instruction_quote", "explanation"],
        }},
    },
    "required": ["verdict", "add_beat_ids", "remove_beat_ids", "issues", "summary", "style_notes", "action_evidence"],
}

STORY_TARGET_REVISION_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string", "enum": ["fit", "no_fit"]},
        "keep_beat_ids": _STRING_LIST_SCHEMA,
        "released_optional_beat_ids": _STRING_LIST_SCHEMA,
        "role_selections": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    "required": ["verdict", "keep_beat_ids", "released_optional_beat_ids", "role_selections"],
}


def story_cache_fingerprint(segments: list[dict[str, Any]], brief: dict[str, Any], model: str,
                            visual_key: str | None = None) -> str:
    """Identify the exact transcript, intent, model and pipeline behind a story cache."""

    segment_identity = [
        {
            "id": item.get("id"),
            "start": round(float(item.get("start", 0.0)), 3),
            "end": round(float(item.get("end", 0.0)), 3),
            "text": stable_fingerprint("segment-text", str(item.get("text") or "")),
        }
        for item in segments
    ]
    return stable_fingerprint(
        "story-cache",
        {
            "pipeline": STORY_CACHE_PIPELINE,
            "model": model,
            "segments": segment_identity,
            "candidate_policy": CANDIDATE_POLICY_VERSION,
            "canonical_word_spans": source_identity_rows(segments),
            "brief": dict(brief),
            "language": brief.get("language"),
            "performance_mode": brief.get("performance_mode"),
            "goal": brief.get("goal"),
            "instruction": brief.get("instruction"),
            **({"visual_moments": visual_key} if visual_key else {}),
        },
    )


def _check_cancelled(cancel_check: Callable[[], None] | None) -> None:
    if cancel_check:
        cancel_check()


def _ollama_inventory(settings: Settings) -> tuple[bool, set[str]]:
    try:
        tags_endpoint = str(settings.ai.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/tags"
        with open_ollama(tags_endpoint, timeout=2) as response:
            payload = read_ollama_json(response, 2 * 1024 * 1024)
        models = {
            str(item.get("name", "")).removesuffix(":latest")
            for item in payload.get("models", [])
            if str(item.get("name", "")).strip()
        }
        return True, models
    except Exception:
        return False, set()


def _installed_models(settings: Settings) -> set[str]:
    return _ollama_inventory(settings)[1]


_STORY_GPU_PROBE: dict[float, tuple[float, bool]] = {}


def _auto_story_quality_ready(settings: Settings, model: str) -> bool:
    """Auto prefers the larger Story model only when it is already installed and
    the GPU has room for it, so drafts improve without a download or a slow
    partially offloaded model."""
    from .transcription import _cuda_has_capacity, cuda_available

    if model.strip().removesuffix(":latest") not in _installed_models(settings):
        return False
    try:
        minimum = float(settings.ai.get("editor_quality_min_free_mb", 9216))
    except (TypeError, ValueError):
        minimum = 9216.0
    # Status is polled; probe the GPU at most every 30 seconds.
    cached = _STORY_GPU_PROBE.get(minimum)
    if cached and time.monotonic() - cached[0] < 30:
        return cached[1]
    ready = bool(cuda_available(settings) and _cuda_has_capacity(settings, minimum_free_mb=minimum))
    _STORY_GPU_PROBE[minimum] = (time.monotonic(), ready)
    return ready


def _model_preferences(settings: Settings, brief: dict[str, Any], installed: set[str] | None = None) -> list[str]:
    base = str(settings.ai.get("editor_model", "qwen3.5:4b"))
    fallbacks = [str(item) for item in settings.ai.get("editor_fallback_models", [])]
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    preferred: list[str] = []
    quality_model = str(settings.ai.get("editor_quality_model") or "qwen3.5:9b")
    # The larger Quality Story model is an optional download. Quality uses it
    # when the person installed it; otherwise the default model is the request,
    # not a "missing model" fallback that would look like a broken setup.
    quality_installed = installed is not None and quality_model.strip().removesuffix(":latest") in installed
    if (mode == "quality" and quality_installed) or (mode == "auto" and _auto_story_quality_ready(settings, quality_model)):
        preferred.append(quality_model)
    elif mode == "lite":
        preferred.append(str(settings.ai.get("editor_lite_model") or "qwen3.5:2b"))
    preferred.extend([base, *fallbacks])
    output: list[str] = []
    for model in preferred:
        clean = model.strip().removesuffix(":latest")
        if clean and clean not in output:
            output.append(clean)
    return output


def _select_editor_model(settings: Settings, brief: dict[str, Any]) -> str:
    return str(_ready_story_model_status(settings, brief)["selected_model"])


def story_ai_status(settings: Settings, brief: dict[str, Any] | None = None) -> dict[str, Any]:
    brief = brief or {}
    from .cloud_ai import enabled, connection
    if enabled(settings):
        selected = connection(settings)
        ready = bool(selected.get("api_key")) and settings.ai.get("enabled", True)
        provider = str(selected.get("provider") or "groq")
        provider_label = "Groq" if provider == "groq" else "OpenAI-compatible"
        return {"ready": bool(ready), "provider": provider, "provider_label": provider_label, "ollama_available": False,
                "installed_models": [], "selected_model": selected["model"] if ready else None,
                "recommended_model": selected["model"], "reason": None if ready else "cloud_key_required",
                "requested_model": selected["model"], "requested_model_installed": None,
                "using_fallback": False, "fallback_reason": None,
                "message": (f"Using configured {provider_label} model {selected['model']}." if ready
                            else f"Connect {provider_label} in AI connection before creating a cloud edit.")}
    if not settings.ai.get("enabled", True):
        preferred = _model_preferences(settings, brief)
        requested = preferred[0] if preferred else "qwen3.5:4b"
        return {
            "ready": False, "ollama_available": False, "installed_models": [], "selected_model": None,
            "recommended_model": requested, "requested_model": requested, "requested_model_installed": None,
            "using_fallback": False, "fallback_reason": None, "reason": "ai_disabled",
            "message": "Story AI is disabled. Enable AI or continue with manual editing.",
        }
    available, installed = _ollama_inventory(settings)
    preferred = _model_preferences(settings, brief, installed if available else None)
    requested = preferred[0] if preferred else "qwen3.5:4b"
    selected = next((model for model in preferred if model in installed), None) if available else None
    using_fallback = bool(selected and selected != requested)
    if not available:
        message = "Story AI requires Ollama to be running. Start the local AI engine and retry."
    elif not selected:
        message = (f"Requested model {requested} is not installed. Install a configured model explicitly "
                   "in AI connection, or continue manually.")
    elif using_fallback:
        message = (f"Requested model {requested} is not installed. Using installed {selected} for this edit. "
                   "Review this draft; install the requested model explicitly in AI connection if needed.")
    else:
        message = f"Using installed model {selected}."
    upgrade_model, upgrade_reason = _story_upgrade(settings, brief, available, installed, selected)
    return {
        "upgrade_model": upgrade_model,
        "upgrade_reason": upgrade_reason,
        "ready": bool(available and selected),
        "ollama_available": available,
        "installed_models": sorted(installed),
        "selected_model": selected,
        "requested_model": requested,
        "requested_model_installed": requested in installed if available else None,
        "recommended_model": requested,
        "using_fallback": using_fallback,
        "fallback_reason": "requested_model_missing" if using_fallback else None,
        "message": message,
        "reason": (
            None
            if available and selected
            else "ollama_unavailable"
            if not available
            else "story_model_missing"
        ),
    }


def _story_upgrade(
    settings: Settings, brief: dict[str, Any], available: bool, installed: set[str], selected: str | None,
) -> tuple[str | None, str | None]:
    """Offer the optional larger Story model: in Quality, where the person asked
    for the best drafts, and in Auto when this GPU can run it. A suggestion
    only: downloading still needs the user's confirmation."""
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    quality = str(settings.ai.get("editor_quality_model") or "qwen3.5:9b").strip().removesuffix(":latest")
    if mode not in {"auto", "quality"} or not available or not selected or quality in installed or selected == quality:
        return None, None
    if mode == "quality":
        return quality, "quality_mode"
    from .transcription import _cuda_has_capacity, cuda_available
    try:
        minimum = float(settings.ai.get("editor_quality_min_free_mb", 9216))
    except (TypeError, ValueError):
        minimum = 9216.0
    cached = _STORY_GPU_PROBE.get(minimum)
    if cached and time.monotonic() - cached[0] < 30:
        room = cached[1]
    else:
        room = bool(cuda_available(settings) and _cuda_has_capacity(settings, minimum_free_mb=minimum))
        _STORY_GPU_PROBE[minimum] = (time.monotonic(), room)
    return (quality, "gpu_room") if room else (None, None)


def _ready_story_model_status(settings: Settings, brief: dict[str, Any]) -> dict[str, Any]:
    """Use the same checked selection for status and execution; never guess a model."""
    status = story_ai_status(settings, brief)
    if not status["ready"]:
        raise StoryAIUnavailableError(str(status["message"]))
    return status


def _model_selection_details(status: dict[str, Any]) -> dict[str, Any]:
    return {key: status.get(key) for key in (
        "requested_model", "requested_model_installed", "selected_model", "using_fallback", "fallback_reason", "message", "model_identity",
    )}


def _call_ollama(settings: Settings, payload: dict[str, Any], timeout: int = 180) -> dict[str, Any] | None:
    from .cloud_ai import enabled, chat
    if enabled(settings):
        return chat(settings, payload, timeout=timeout)
    endpoint = str(settings.ai.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/chat"
    clean_payload = dict(payload)
    clean_payload.pop("_performance_mode", None)
    # CUTROOM needs the structured answer, not a separate reasoning trace. On
    # thinking-capable Qwen models the default reasoning pass can consume the
    # entire num_predict budget and leave message.content empty.
    clean_payload.setdefault("think", False)
    request = urllib.request.Request(endpoint, data=json.dumps(clean_payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with open_ollama(request, timeout=timeout) as response:
            body = read_ollama_json(response)
        content = body.get("message", {}).get("content", "{}")
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.URLError):
        return None


def _read_ollama_chat_response(
    response: Any,
    *,
    streaming: bool,
    cancel_check: Callable[[], None] | None,
) -> dict[str, Any]:
    """Read one Ollama chat response while keeping streamed work cancellable."""

    if not streaming:
        return read_ollama_json(response)

    line_queue: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=8)
    stop_reader = threading.Event()

    def enqueue(event, value):
        while not stop_reader.is_set():
            try:
                line_queue.put((event, value), timeout=0.1)
                return
            except queue.Full:
                continue

    def read_lines() -> None:
        try:
            total = 0
            while not stop_reader.is_set():
                raw_line = response.readline(256 * 1024 + 1)
                if not raw_line:
                    break
                total += len(raw_line)
                if len(raw_line) > 256 * 1024 or total > OLLAMA_RESPONSE_BYTES:
                    raise StoryPlanningError("Local AI returned an oversized streamed response.")
                enqueue("line", raw_line)
        except BaseException as exc:  # Re-raised on the owning job thread below.
            enqueue("error", exc)
        else:
            enqueue("done", None)

    reader = threading.Thread(target=read_lines, name="cutroom-ollama-stream", daemon=True)
    reader.start()
    content_parts: list[str] = []
    thinking_parts: list[str] = []
    final: dict[str, Any] = {}
    completed = False
    try:
        while True:
            _check_cancelled(cancel_check)
            try:
                event, payload = line_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            _check_cancelled(cancel_check)
            if event == "done":
                break
            if event == "error":
                raise payload
            raw_line = payload
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
            except (TypeError, json.JSONDecodeError) as exc:
                raise StoryPlanningError("Story AI returned an invalid streamed response.") from exc
            if not isinstance(chunk, dict):
                raise StoryPlanningError("Story AI returned an invalid streamed response.")
            if "error" in chunk:
                raise StoryAIUnavailableError("Story AI reported a generation error.")
            message = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
            if isinstance(message.get("content"), str):
                content_parts.append(message["content"])
            if isinstance(message.get("thinking"), str):
                thinking_parts.append(message["thinking"])
            final.update({key: value for key, value in chunk.items() if key != "message"})
            _check_cancelled(cancel_check)
            if chunk.get("done") is True:
                completed = True
                break
        _check_cancelled(cancel_check)
        if not completed:
            raise StoryAIUnavailableError("Story AI response ended before completion.")
        final["message"] = {
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts),
        }
        return final
    finally:
        stop_reader.set()
        if reader.is_alive():
            try:
                abort = getattr(response, "cutroom_abort", None)
                if abort:
                    abort()
                response.close()
            except OSError:
                pass
            reader.join(timeout=0.5)


# Ollama reloads the model whenever num_ctx changes. A story job sends many
# passes with different prompt sizes, so contexts snap to a few sizes and,
# within one job, never shrink below the largest one already loaded.
_STORY_CONTEXT_TIERS = (8192, 16384, 32768)
_story_context_floor = threading.local()


def _context_tier(needed: int, cap: int) -> int:
    return next((tier for tier in _STORY_CONTEXT_TIERS if needed <= tier <= cap), cap)


@contextlib.contextmanager
def _stable_story_context():
    previous = getattr(_story_context_floor, "value", 0)
    _story_context_floor.value = previous or 1
    try:
        yield
    finally:
        _story_context_floor.value = previous


def _with_stable_story_context(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        with _stable_story_context():
            try:
                return function(*args, **kwargs)
            except (StoryPlanningError, StoryAIUnavailableError) as exc:
                diagnostic = copy.deepcopy(getattr(exc, "diagnostic", {}))
                if isinstance(exc, StoryAIUnavailableError):
                    outcome, reason = "technical_error", "story_ai_unavailable"
                elif isinstance(exc, StoryResponseLimitError):
                    outcome, reason = "technical_error", "story_response_output_limit"
                elif "context budget" in str(exc):
                    outcome, reason = "technical_error", "story_input_context_limit"
                elif diagnostic.get("reason") in {"planner_no_fit", "precision_no_fit"}:
                    outcome, reason = "editorial_no_fit", diagnostic["reason"]
                elif isinstance(exc, StoryBudgetError):
                    outcome, reason = "constraint_conflict", "story_source_constraint"
                else:
                    outcome, reason = "invalid_model_output", "invalid_story_output"
                diagnostic.setdefault("outcome", outcome)
                diagnostic.setdefault("reason", reason)
                diagnostic.setdefault("kind", "story_planning")
                diagnostic.setdefault("applied_to_timeline", False)
                brief = kwargs.get("brief", args[3] if len(args) > 3 else {})
                diagnostic.setdefault("instruction_contract", build_instruction_contract(brief))
                exc.diagnostic = diagnostic
                raise
    return wrapper


def _fit_story_request_context(payload: dict[str, Any], mode: str) -> None:
    """Budget the request conservatively; the estimate is not a tokenizer proof.

    Only downstream evidence excerpts may shrink. Chapter understanding keeps
    every transcript character, and all requests retain their brief and IDs.
    The caller owns this payload copy, including changes made for a retry.
    """
    options = dict(payload.get("options") or {})
    cap = 8192 if mode == "lite" else 32768
    output_budget = int(options.get("num_predict") or 1200)
    if output_budget < 1:
        raise StoryPlanningError("Story AI needs a finite positive output budget to preserve its input context.")
    options["num_predict"] = output_budget
    reserve = max(2400, output_budget)
    estimate = _story_prompt_tokens(payload)
    needed = estimate + reserve
    context = _context_tier(max(1024, int(options.get("num_ctx") or 8192), needed), cap)
    floor = getattr(_story_context_floor, "value", 0)
    if floor:
        context = max(context, min(cap, floor))
        _story_context_floor.value = context
    options["num_ctx"] = context
    payload["options"] = options
    if needed <= context:
        return

    # Gather only named evidence fields. Never recursively shorten arbitrary
    # JSON strings: those can contain instructions, dependencies or identifiers.
    parsed_messages: list[tuple[dict[str, Any], dict[str, Any]]] = []
    excerpts: list[tuple[Any, Any, str]] = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        try:
            content = json.loads(message.get("content") or "")
        except (TypeError, ValueError):
            continue
        if not isinstance(content, dict):
            continue
        chapters = content.get("chapters")
        if isinstance(chapters, list) and any(isinstance(row, dict) and "beats" in row for row in chapters):
            continue
        parsed_messages.append((message, content))
        for field in ("candidate_beats", "candidates", "selected"):
            rows = content.get(field)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and isinstance(row.get("text"), str):
                    excerpts.append((row, "text", row["text"]))
        for field in ("chapter_summaries", "chapters"):
            rows = content.get(field)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict) or "beats" in row or not isinstance(row.get("summary"), str):
                    continue
                points = row.get("key_points")
                if isinstance(points, list):
                    excerpts.extend((points, index, text) for index, text in enumerate(points) if isinstance(text, str))

    limit = max((len(text) for _, _, text in excerpts), default=0)
    while limit > 96:
        limit = max(96, int(limit * 0.7))
        for row, key, original in excerpts:
            row[key] = _balanced_excerpt(original, limit)
        for message, content in parsed_messages:
            message["content"] = json.dumps(content, ensure_ascii=False)
        estimate = _story_prompt_tokens(payload)
        if estimate + reserve <= context:
            logging.getLogger(__name__).warning(
                "Story AI context budget shortened %s evidence excerpts; estimated prompt=%s, context=%s.",
                sum(len(original) > limit for _, _, original in excerpts), estimate, context,
            )
            return

    guidance = "Use Auto or Quality mode, or shorten the editing instruction" if mode == "lite" else "Shorten the editing instruction or reduce the source material"
    raise StoryPlanningError(
        f"Story AI input exceeds the estimated local context budget ({cap} tokens) "
        f"while preserving the editing brief and all supplied identifiers. {guidance} and retry."
    )


def _story_payload_fits_cap(payload: dict[str, Any], mode: str) -> bool:
    cap = 8192 if mode == "lite" else 32768
    reserve = max(2400, int((payload.get("options") or {}).get("num_predict") or 1200))
    return _story_prompt_tokens(payload) + reserve <= cap


def _bounded_global_story_payload(
    payload: dict[str, Any], chapters: list[dict[str, Any]], summaries: list[dict[str, Any]], mode: str,
) -> dict[str, Any]:
    """Global planning uses the whole index; exact retrieval remains canonical.

    Short requests retain their existing full-evidence contract. Long requests
    never trim canonical quotations: they explicitly use a retrieval index with
    every chapter/beat and unchanged source-clock references. Summary prose is
    labelled as unverified and cannot grant final source/semantic approval.
    """
    if _story_payload_fits_cap(payload, mode):
        return payload
    from .story_context import build_whole_recording_index
    original = json.loads(payload["messages"][-1]["content"])
    for limit in (320, 160, 80, 32):
        output = copy.deepcopy(payload)
        content = copy.deepcopy(original)
        index = build_whole_recording_index(chapters, summaries, summary_char_limit=limit,
                                           key_point_char_limit=min(96, limit), max_key_points=3)
        content.pop("source_evidence", None)
        content.pop("chapters", None)  # The complete bounded chapter view lives once under source_index.
        content["source_index"] = index
        content["interpretation_status"] = "unverified_summary_index_requires_canonical_retrieval"
        if isinstance(content.get("source_beat_costs"), list):
            content["source_beat_cost_columns"] = ["beat_id", "minimum_safe_seconds", "approved_seconds", "frame_grid_encodable"]
            content["source_beat_costs"] = [
                [row["id"], row["duration_cost"].get("minimum_safe_seconds"),
                 row["duration_cost"].get("approved_seconds"), row["duration_cost"].get("frame_grid_encodable")]
                for row in content["source_beat_costs"]]
        output["messages"][-1]["content"] = json.dumps(content, ensure_ascii=False)
        output["messages"][0]["content"] += (
            " This bounded global pass uses source_index for WHOLE-recording coverage, including every chapter and beat ID. "
            "It contains retrieval references and explicitly abbreviated unverified interpretations, not authoritative quotations. "
            "Propose chapters only; later exact selection retrieves complete canonical source utterances and must independently "
            "verify every purpose, prerequisite, source ordering and target. Do not force inclusion from every chapter or turn summaries into facts."
        )
        if _story_payload_fits_cap(output, mode):
            return output
    # Intact instructions/identifiers can themselves exceed the cap. Keep that
    # truthful technical failure rather than dropping a tail or omitting IDs.
    _fit_story_request_context(output, mode)
    return output


def _global_source_evidence(chapters, segments):
    try:
        return build_story_evidence_catalog(
            [beat for chapter in (chapters or []) for beat in chapter.get("beats", [])], segments) if segments else []
    except (ValueError, TypeError, KeyError) as error:
        raise StoryPlanningError("Global story context has ambiguous or invalid canonical source ownership.",
            {"outcome": "technical_error", "reason": "invalid_story_source_context", "applied_to_timeline": False}) from error


def _unique_story_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Precision replies cannot silently overwrite a role or context chapter."""
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError("Repeated structured response key", "", 0)
        result[key] = value
    return result


def _call_ollama_strict(
    settings: Settings,
    payload: dict[str, Any],
    timeout: int = 180,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    from .cloud_ai import enabled, chat
    clean_payload = copy.deepcopy(payload)
    single_attempt = clean_payload.pop("_single_attempt", False) is True
    reject_duplicate_keys = clean_payload.pop("_reject_duplicate_keys", False) is True
    if enabled(settings):
        if reject_duplicate_keys:
            clean_payload["_reject_duplicate_keys"] = True
        return chat(settings, clean_payload, cancel_check=cancel_check, timeout=timeout)
    # The hierarchy preflights Ollama/model availability once before the first pass.
    # Do not re-query /api/tags before every pass; that adds latency without adding safety.
    mode = str(clean_payload.pop("_performance_mode", None) or settings.ai.get("performance_mode") or "auto").lower()
    # Keep requests compact by default while preserving explicit controls
    # supplied by another caller. The final story review sets False itself.
    clean_payload.setdefault("think", False)
    # Ollama emits a small NDJSON chunk for each generated token. Streaming only
    # when a job supplies a cancellation callback lets closing this response
    # stop an in-flight generation instead of waiting for its full timeout.
    streaming = cancel_check is not None
    if streaming:
        clean_payload["stream"] = True
    endpoint = str(settings.ai.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/chat"
    last_message: dict[str, Any] = {}
    last_reason = "unknown"
    last_json_error: Exception | None = None
    for attempt in range(1 if single_attempt else 2):
        _check_cancelled(cancel_check)
        _fit_story_request_context(clean_payload, mode)
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(clean_payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with open_ollama(request, timeout=timeout) as response:
                body = _read_ollama_chat_response(
                    response,
                    streaming=streaming,
                    cancel_check=cancel_check,
                )
        except urllib.error.HTTPError as exc:
            raise StoryAIUnavailableError(f"Story AI returned HTTP {exc.code}.") from exc
        except ValueError as exc:
            raise StoryAIUnavailableError("Local AI rejected its endpoint or response. Use a loopback Ollama address.") from exc
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            raise StoryAIUnavailableError(f"Story AI could not complete the request: {exc}") from exc
        if not isinstance(body, dict) or "error" in body:
            raise StoryAIUnavailableError("Story AI reported a generation error.")
        # Older nonstream test/plugin envelopes omit done; an explicit False
        # still proves that the daemon did not complete this response.
        if body.get("done") is False:
            raise StoryAIUnavailableError("Story AI response ended before completion.")
        last_message = body.get("message", {}) if isinstance(body.get("message"), dict) else {}
        last_reason = str(body.get("done_reason") or "unknown")
        content = last_message.get("content")
        # A parseable object at the generation limit is not a completed model
        # decision. Keep the existing bounded retry, or fail a single attempt.
        if content and last_reason != "length":
            try:
                parsed = json.loads(content, object_pairs_hook=_unique_story_object) if reject_duplicate_keys else json.loads(content)
            except (TypeError, json.JSONDecodeError) as exc:
                last_json_error = exc
            else:
                if not isinstance(parsed, dict):
                    raise StoryPlanningError("Story AI returned an invalid structured response.")
                return parsed
        if attempt == 0 and not single_attempt:
            options = dict(clean_payload.get("options") or {})
            current_budget = int(options.get("num_predict") or 1200)
            options["num_predict"] = min(4096, max(2400, current_budget * 2))
            options["temperature"] = min(0.03, float(options.get("temperature") or 0.03))
            clean_payload["options"] = options
            messages = clean_payload.get("messages")
            if isinstance(messages, list) and messages and isinstance(messages[0], dict):
                messages[0]["content"] = str(messages[0].get("content") or "") + (
                    " Keep the retry concise: use short strings while preserving every supplied identifier or object the prompt explicitly requires."
                )
            continue
    _check_cancelled(cancel_check)
    if last_reason == "length":
        raise StoryResponseLimitError(
            "Story AI reached its output budget before returning a complete JSON response."
        ) from last_json_error
    if last_message.get("content"):
        raise StoryPlanningError("Story AI returned invalid JSON." if single_attempt
                                 else "Story AI returned invalid JSON after an automatic retry.") from last_json_error
    model = str(clean_payload.get("model") or "local model")
    thinking_length = len(str(last_message.get("thinking") or ""))
    detail = (
        " The model used its output budget for internal thinking."
        if thinking_length and last_reason == "length"
        else ""
    )
    raise StoryPlanningError(
        f"Story AI returned an empty response from {model} (reason: {last_reason}).{detail}"
    )


def _call_ollama_story_pass(
    settings: Settings,
    payload: dict[str, Any],
    timeout: int,
    cancel_check: Callable[[], None] | None,
) -> dict[str, Any]:
    """Keep older direct test/plugin hooks compatible when no job owns the call."""

    if cancel_check is None:
        return _call_ollama_strict(settings, payload, timeout=timeout)
    return _call_ollama_strict(
        settings,
        payload,
        timeout=timeout,
        cancel_check=cancel_check,
    )


def build_story_chapters(beats: list[dict[str, Any]], max_chapters: int = 12) -> list[dict[str, Any]]:
    """Group idea-level beats into broad chapters that cover the full recording."""
    if not beats:
        return []
    ordered = sorted(beats, key=lambda item: float(item.get("start", 0)))
    total_duration = max(float(ordered[-1].get("end", 0)), 1.0)
    max_chapters = max(4, min(20, int(max_chapters)))
    target_span = max(75.0, total_duration / max_chapters)
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    chapter_start = float(ordered[0].get("start", 0))
    for beat in ordered:
        if current:
            span = float(beat.get("end", 0)) - chapter_start
            previous = current[-1]
            role_break = previous.get("role_hint") == "conclusion" and span >= target_span * 0.55
            if (span >= target_span and len(groups) < max_chapters - 1) or role_break:
                groups.append(current)
                current = []
                chapter_start = float(beat.get("start", 0))
        current.append(beat)
    if current:
        groups.append(current)

    # If cue-driven breaks produced too many chapters, merge the smallest neighbors.
    while len(groups) > max_chapters:
        pair_index = min(
            range(len(groups) - 1),
            key=lambda index: (
                float(groups[index][-1]["end"]) - float(groups[index][0]["start"])
                + float(groups[index + 1][-1]["end"]) - float(groups[index + 1][0]["start"])
            ),
        )
        groups[pair_index : pair_index + 2] = [groups[pair_index] + groups[pair_index + 1]]

    chapters: list[dict[str, Any]] = []
    for index, group in enumerate(groups, start=1):
        start = float(group[0]["start"])
        end = float(group[-1]["end"])
        chapters.append({
            "id": f"c{index:03d}",
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(max(0.0, end - start), 3),
            "position": round(start / total_duration, 4),
            "beat_ids": [str(item["id"]) for item in group],
            "beats": group,
        })
    return chapters


def _on_screen_field(beat: dict[str, Any]) -> dict[str, str]:
    note = str(beat.get("on_screen") or "").strip()
    return {"on_screen": note} if note else {}


def _on_screen_guidance(beats: Any) -> str:
    """Explain the vision notes only to requests that actually contain them."""
    if not any(str(beat.get("on_screen") or "").strip() for beat in beats):
        return ""
    return (
        " Some beats include on_screen: what a local vision pass saw in the video during that beat. "
        "In gameplay the spoken text is often a game character, so use on_screen to know what actually happens. "
        "For highlights prefer beats with gameplay action and avoid menus, maps and loading screens. "
        "Never invent events that neither the text nor on_screen shows."
    )


def annotate_story_beats(beats: list[dict[str, Any]], visual_moments: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Attach a short on-screen note to each beat that the vision pass saw clearly."""
    from .visual_moments import VisualTimeline, on_screen_note

    timeline = VisualTimeline(visual_moments)
    if not timeline:
        return beats
    output = []
    for beat in beats:
        note = on_screen_note(timeline.evidence(float(beat.get("start", 0.0)), float(beat.get("end", 0.0))))
        output.append({**beat, "on_screen": note} if note else beat)
    return output


def _chapter_prompt_payload(chapter: dict[str, Any], text_limit: int) -> dict[str, Any]:
    return {
        "id": chapter["id"],
        "position": chapter["position"],
        "duration": chapter["duration"],
        "beats": [
            {
                "id": beat["id"],
                "position": beat["position"],
                "role_hint": beat.get("role_hint"),
                # Understand the complete thought before selecting a short
                # excerpt. _chapter_summary_batches bounds these requests.
                "text": str(beat.get("text", "")),
                **_on_screen_field(beat),
            }
            for beat in chapter["beats"]
        ],
    }


def _story_prompt_tokens(payload: dict[str, Any]) -> int:
    """Conservative sizing estimate, not a model-specific tokenizer count.

    Non-ASCII UTF-8 bytes receive a larger budget so Hebrew, Arabic and CJK
    do not share English's overly optimistic characters-per-token assumption.
    The margin includes chat framing/schema overhead. No tokenizer download.
    """
    text = json.dumps({"messages": payload.get("messages"), "format": payload.get("format")}, ensure_ascii=False)
    ascii_count = sum(ord(char) < 128 for char in text)
    return (ascii_count + 1) // 2 + len(text.encode("utf-8")) - ascii_count + 384


def _story_prompt_fits(payload: dict[str, Any]) -> bool:
    options = payload.get("options") or {}
    reserve = max(2400, int(options.get("num_predict") or 0))
    return _story_prompt_tokens(payload) + reserve <= int(options.get("num_ctx") or 8192)


def _balanced_excerpt(text: str, limit: int) -> str:
    """Label omissions and preserve the end of an idea, not just its prefix."""
    if len(text) <= limit:
        return text
    marker = " […] "
    room = max(0, limit - len(marker) * 2)
    part = room // 3
    middle = max(part, len(text) // 2 - part // 2)
    return text[:part] + marker + text[middle:middle + part] + marker + text[-(room - 2 * part):]


def _spread_values(values: list[str], limit: int) -> list[str]:
    values = list(dict.fromkeys(values))
    if len(values) <= limit:
        return values
    return [values[round(index * (len(values) - 1) / (limit - 1))] for index in range(limit)]


def _chapter_summary_batches(
    chapters: list[dict[str, Any]], brief: dict[str, Any], model: str, mode: str, text_limit: int,
) -> list[list[dict[str, Any]]]:
    """Split oversized inputs without omitting any chapter, beat or text tail.

    Parts keep the original chapter/beat IDs. Their validated summaries are
    combined after all parts finish, so planning and cache identities stay stable.
    """
    def split(batch: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        payload = _chapter_summary_payload(batch, brief, model, mode, text_limit)
        if _story_prompt_fits(payload):
            return [batch]
        if len(batch) > 1:
            middle = len(batch) // 2
            return split(batch[:middle]) + split(batch[middle:])
        chapter = batch[0]
        beats = chapter["beats"]
        if len(beats) > 1:
            middle = len(beats) // 2
            return split([{**chapter, "beats": beats[:middle]}]) + split([{**chapter, "beats": beats[middle:]}])
        text = str(beats[0].get("text") or "") if beats else ""
        if len(text) <= 256:
            raise StoryPlanningError("Story instructions exceed the local context budget. Shorten the editing instruction and retry.")
        middle = len(text) // 2
        boundary = text.rfind(" ", len(text) // 4, middle + 1)
        if boundary > 0:
            middle = boundary + 1
        return split([{**chapter, "beats": [{**beats[0], "text": text[:middle]}]}]) + split([
            {**chapter, "beats": [{**beats[0], "text": text[middle:]}]},
        ])

    batches: list[list[dict[str, Any]]] = []
    size = 2 if mode == "quality" else 3
    for start in range(0, len(chapters), size):
        batches.extend(split(chapters[start:start + size]))
    return batches


def _chapter_summary_schema(chapter_ids: list[str]) -> dict[str, Any]:
    """Constrain one model pass to exactly the chapters supplied to it."""

    schema = copy.deepcopy(CHAPTER_SUMMARY_SCHEMA)
    rows = schema["properties"]["chapters"]
    rows["minItems"] = len(chapter_ids)
    rows["maxItems"] = len(chapter_ids)
    rows["items"]["properties"]["id"] = {"type": "string", "enum": list(chapter_ids)}
    return schema


def _chapter_summary_payload(
    chapter_batch: list[dict[str, Any]],
    brief: dict[str, Any],
    model: str,
    mode: str,
    text_limit: int,
    *,
    focused_retry: bool = False,
) -> dict[str, Any]:
    chapter_ids = [str(item["id"]) for item in chapter_batch]
    retry_instruction = ""
    if focused_retry:
        retry_instruction = (
            f" This is a focused recovery pass. Return exactly one complete row for chapter {chapter_ids[0]}; "
            "never omit it. If the material is ambiguous, describe that ambiguity using only the supplied transcript."
        )
    return {
        "model": model,
        "stream": False,
        "format": _chapter_summary_schema(chapter_ids),
        "_performance_mode": mode,
        "options": {
            "temperature": 0.03 if focused_retry else 0.05,
            "num_ctx": 12288 if mode == "quality" else 8192,
            "num_predict": 900 if focused_retry else 1500,
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the first pass of CUTROOM Story AI. Summarize each supplied chapter independently. "
                    "Understand what is being explained or happening, what changes, what depends on earlier context, and what payoff or result appears. "
                    "Do not select clips yet. Return JSON only: {chapters:[{id,title,summary,role,key_points,key_beat_ids,depends_on,unresolved_questions}]}. "
                    "role must be one of setup,problem,development,example,turn,result,conclusion,other. Only use supplied chapter and beat IDs."
                    + _on_screen_guidance(beat for chapter in chapter_batch for beat in chapter["beats"])
                    + retry_instruction
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"brief": brief, "chapters": [_chapter_prompt_payload(item, text_limit) for item in chapter_batch]},
                    ensure_ascii=False,
                ),
            },
        ],
    }


def _normalize_chapter_summary(
    row: dict[str, Any],
    chapter_id: str,
    valid_dependency_ids: set[str],
    valid_beat_ids: set[str],
    *,
    summary_source: str,
) -> dict[str, Any] | None:
    raw_summary = row.get("summary")
    summary = raw_summary.strip() if isinstance(raw_summary, str) else ""
    if not summary:
        return None
    raw_role = row.get("role")
    role = raw_role.strip().lower() if isinstance(raw_role, str) else "other"
    if role not in {"setup", "problem", "development", "example", "turn", "result", "conclusion", "other"}:
        role = "other"
    raw_key_beats = row.get("key_beat_ids") if isinstance(row.get("key_beat_ids"), list) else []
    raw_dependencies = row.get("depends_on") if isinstance(row.get("depends_on"), list) else []
    raw_key_points = row.get("key_points") if isinstance(row.get("key_points"), list) else []
    raw_questions = row.get("unresolved_questions") if isinstance(row.get("unresolved_questions"), list) else []
    key_beats = [
        value.strip()
        for value in raw_key_beats
        if isinstance(value, str) and value.strip() in valid_beat_ids
    ][:8]
    if not key_beats:
        return None
    raw_title = row.get("title")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    return {
        "id": chapter_id,
        "title": title[:120] or chapter_id,
        "summary": _balanced_excerpt(summary, 800),
        "role": role,
        "key_points": [value.strip()[:240] for value in raw_key_points if isinstance(value, str) and value.strip()][:8],
        "key_beat_ids": key_beats,
        "depends_on": [
            value.strip()
            for value in raw_dependencies
            if isinstance(value, str) and value.strip() in valid_dependency_ids and value.strip() != chapter_id
        ][:5],
        "unresolved_questions": [
            value.strip()[:240]
            for value in raw_questions
            if isinstance(value, str) and value.strip()
        ][:5],
        "summary_source": summary_source,
    }


def _summaries_from_chapter_result(
    result: dict[str, Any],
    chapter_batch: list[dict[str, Any]],
    beat_ids_by_chapter: dict[str, set[str]],
    *,
    summary_source: str,
) -> dict[str, dict[str, Any]]:
    rows = result.get("chapters")
    if not isinstance(rows, list):
        return {}
    expected_ids = {str(item["id"]) for item in chapter_batch}
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_chapter_id = row.get("id")
        chapter_id = raw_chapter_id.strip() if isinstance(raw_chapter_id, str) else ""
        if chapter_id not in expected_ids or chapter_id in output:
            continue
        normalized = _normalize_chapter_summary(
            row,
            chapter_id,
            expected_ids,
            beat_ids_by_chapter[chapter_id],
            summary_source=summary_source,
        )
        if normalized:
            output[chapter_id] = normalized
    return output


def _extractive_chapter_summary(
    chapter: dict[str, Any],
) -> dict[str, Any]:
    """Recover coverage from verbatim transcript excerpts, never invented prose."""

    usable_beats = [
        beat
        for beat in chapter.get("beats", [])
        if isinstance(beat, dict) and str(beat.get("text") or "").strip()
    ]
    if not usable_beats:
        raise StoryPlanningError(
            f"Story AI could not summarize chapter {chapter.get('id')} and no transcript text was available for safe recovery."
        )
    chapter_id = str(chapter["id"])
    excerpts: list[str] = []
    for index in sorted({0, len(usable_beats) // 2, len(usable_beats) - 1}):
        excerpt = _balanced_excerpt(str(usable_beats[index].get("text") or "").strip(), 240)
        if excerpt and excerpt not in excerpts:
            excerpts.append(excerpt)
    transcript_text = " ".join(str(beat.get("text") or "").strip() for beat in usable_beats).strip()
    hinted_roles = [
        str(beat.get("role_hint"))
        for beat in usable_beats
        if str(beat.get("role_hint") or "") in {"setup", "problem", "development", "example", "turn", "result", "conclusion"}
    ]
    role = Counter(hinted_roles).most_common(1)[0][0] if hinted_roles else "other"
    key_beats = sorted(
        usable_beats,
        key=lambda beat: float(beat.get("editorial_score", 0.0)),
        reverse=True,
    )[: min(3, len(usable_beats))]
    return {
        "id": chapter_id,
        "title": excerpts[0][:120] if excerpts else chapter_id,
        "summary": _balanced_excerpt(transcript_text, 800),
        "role": role,
        "key_points": excerpts,
        "key_beat_ids": [str(beat["id"]) for beat in key_beats],
        "depends_on": [],
        "unresolved_questions": [],
        "summary_source": "extractive",
    }


def _summarize_story_chapters(
    settings: Settings,
    chapters: list[dict[str, Any]],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> list[dict[str, Any]]:
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    text_limit = 300 if mode == "lite" else 520 if mode == "quality" else 420
    summaries: list[dict[str, Any]] = []
    beat_ids_by_chapter = {str(item["id"]): {str(beat["id"]) for beat in item["beats"]} for item in chapters}
    batches = _chapter_summary_batches(chapters, brief, model, mode, text_limit)
    total_batches = len(batches)
    for batch_index, batch in enumerate(batches):
        _check_cancelled(cancel_check)
        if progress:
            progress(0.06 + 0.30 * (batch_index / total_batches), f"Understanding source section {batch_index + 1} of {total_batches}")
        payload = _chapter_summary_payload(batch, brief, model, mode, text_limit)
        try:
            result = _call_ollama_story_pass(
                settings,
                payload,
                240 if mode == "quality" else 180,
                cancel_check,
            )
        except StoryPlanningError:
            # A malformed/empty batch response is recoverable: retry each source
            # chapter independently instead of discarding completed earlier batches.
            result = {}
        _check_cancelled(cancel_check)
        returned = _summaries_from_chapter_result(
            result,
            batch,
            beat_ids_by_chapter,
            summary_source="model",
        )
        missing = [item for item in batch if str(item["id"]) not in returned]
        for missing_index, chapter in enumerate(missing, start=1):
            _check_cancelled(cancel_check)
            if progress:
                progress(
                    0.06 + 0.30 * ((batch_index + 0.75) / total_batches),
                    f"Recovering omitted chapter {missing_index} of {len(missing)}",
                )
            retry_payload = _chapter_summary_payload(
                [chapter], brief, model, mode, text_limit, focused_retry=True,
            )
            try:
                retry_result = _call_ollama_story_pass(
                    settings,
                    retry_payload,
                    240 if mode == "quality" else 180,
                    cancel_check,
                )
            except StoryPlanningError:
                retry_result = {}
            _check_cancelled(cancel_check)
            recovered = _summaries_from_chapter_result(
                retry_result,
                [chapter],
                beat_ids_by_chapter,
                summary_source="model_retry",
            )
            chapter_id = str(chapter["id"])
            if recovered.get(chapter_id):
                returned[chapter_id] = recovered[chapter_id]
            else:
                _check_cancelled(cancel_check)
                returned[chapter_id] = _extractive_chapter_summary(chapter)
            _check_cancelled(cancel_check)
        summaries.extend(returned[str(item["id"])] for item in batch)
    combined = []
    for chapter in chapters:
        parts = [row for row in summaries if row["id"] == str(chapter["id"])]
        if len(parts) == 1:
            combined.append(parts[0])
            continue
        sources = {row["summary_source"] for row in parts}
        row = dict(parts[0])
        row.update({
            "summary": _balanced_excerpt(" ".join(part["summary"] for part in parts), 800),
            "summary_source": "extractive" if "extractive" in sources else "model_retry" if "model_retry" in sources else "model",
            "input_parts": len(parts),
        })
        for field, limit in (("key_points", 8), ("key_beat_ids", 8), ("depends_on", 5), ("unresolved_questions", 5)):
            row[field] = _spread_values([value for part in parts for value in part[field]], limit)
        combined.append(row)
    return combined


def _build_global_outline(
    settings: Settings,
    summaries: list[dict[str, Any]],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    chapters: list[dict[str, Any]] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if progress:
        progress(0.40, "Understanding the whole recording")
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    payload = {
        "model": model,
        "stream": False,
        "format": GLOBAL_OUTLINE_SCHEMA,
        "_performance_mode": mode,
        "options": {"temperature": 0.03, "num_ctx": 16384 if mode == "quality" else 12288, "num_predict": 3200 if mode == "quality" else 2200},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM's global story analyst. Read chapter summaries from the entire recording and reconstruct the real story/topic arc. "
                    "Identify the premise, what the viewer must understand, setup-to-payoff dependencies, turning points, proof/examples and the real conclusion. "
                    "Do not choose exact clips. Return JSON only with keys: premise,audience_takeaway,story_arc,must_keep_chapter_ids,optional_chapter_ids,dependency_pairs. "
                    "story_arc is a list of {chapter_id,function,why_it_matters}. dependency_pairs is a list of {before,after,reason}. "
                    "Use at most one concise story_arc entry per chapter and keep every explanation to one short sentence. Only use supplied chapter IDs."
                    " Chapter summaries are unverified interpretations. The ID-linked source_evidence is authoritative; "
                    "do not turn suggestions into facts or invent action, intentions, attacks, relocation or results absent from the source. "
                    "A conclusion may be an explicit refusal, decision or qualified claim; it need not be a physical event."
                ),
            },
            {"role": "user", "content": json.dumps({"brief": brief, "chapters": summaries,
                "summary_status": "unverified_interpretations",
                "source_evidence": _global_source_evidence(chapters, segments),
            }, ensure_ascii=False)},
        ],
    }
    payload = _bounded_global_story_payload(payload, chapters or [], summaries, mode)
    result = _call_ollama_story_pass(settings, payload, 240, cancel_check)
    valid = {item["id"] for item in summaries}
    arc = []
    seen_arc_ids: set[str] = set()
    for item in result.get("story_arc", []) if isinstance(result.get("story_arc"), list) else []:
        chapter_id = str(item.get("chapter_id")) if isinstance(item, dict) else ""
        if chapter_id in valid and chapter_id not in seen_arc_ids:
            seen_arc_ids.add(chapter_id)
            arc.append({
                "chapter_id": chapter_id,
                "function": str(item.get("function") or "development")[:80],
                "why_it_matters": str(item.get("why_it_matters") or "")[:320],
            })
    if not arc:
        raise StoryPlanningError("Story AI could not build a global outline from the recording.")
    return {
        "premise": str(result.get("premise") or "")[:800],
        "audience_takeaway": str(result.get("audience_takeaway") or "")[:800],
        "story_arc": arc,
        "must_keep_chapter_ids": [str(value) for value in result.get("must_keep_chapter_ids", []) if str(value) in valid],
        "optional_chapter_ids": [str(value) for value in result.get("optional_chapter_ids", []) if str(value) in valid],
        "dependency_pairs": [
            {"before": str(item.get("before")), "after": str(item.get("after")), "reason": str(item.get("reason") or "")[:240]}
            for item in (result.get("dependency_pairs", []) if isinstance(result.get("dependency_pairs"), list) else [])
            if isinstance(item, dict) and str(item.get("before")) in valid and str(item.get("after")) in valid
        ],
    }


def _configured_story_roles(brief: dict[str, Any]) -> list[str]:
    return required_story_roles(brief)


def _validate_configured_story_roles(plan: dict[str, Any], brief: dict[str, Any]) -> None:
    """A source can reuse evidence; explicit user roles cannot be omitted."""
    required = _configured_story_roles(brief)
    if not required:
        return
    counts = Counter(row.get("purpose") for row in plan.get("slots", []) if isinstance(row, dict))
    missing = [role for role in required if not counts[role]]
    duplicated = [role for role in required if counts[role] > 1]
    purposes = [row.get("purpose") for row in plan.get("slots", []) if isinstance(row, dict)]
    positions = {role: index for index, role in enumerate(purposes)}
    inverted = [group for group in required_story_role_orders(brief)
                if all(role in positions for role in group) and [positions[role] for role in group] != sorted(positions[role] for role in group)]
    if missing or duplicated or inverted:
        details = []
        if missing:
            details.append("missing required story roles: " + ", ".join(missing))
        if duplicated:
            details.append("duplicate required story roles: " + ", ".join(duplicated))
        if inverted:
            details.append("explicit story order was reversed")
        raise StoryPlanningError("Story AI returned an incomplete narrative plan (" + "; ".join(details) + "). "
                                 "Every explicitly requested role needs source support, even within one chapter. "
                                 "No new draft was applied; the existing edit was kept.",
                                 {"outcome": "invalid_model_output", "reason": "invalid_explicit_story_roles", "applied_to_timeline": False})


def _local_continuous_plan_requested(brief):
    """One source range is a planning scope, never a proof of one topic."""
    return (single_source_passage_requested(brief)
            or (str(brief.get("goal") or "short") == "short"
                and explicit_source_continuity_requested(brief)
                and (single_output_requested(brief)
                     or (type(brief.get("output_count")) is int and brief["output_count"] == 1))))


def _candidate_local_context_plan(plan, brief):
    """Scope model context nominations to a local candidate, not every option.

    A source-derived chapter suggestion is not a universal user obligation.
    Keep it available as reference; exact candidate context remains subject to
    independent cited-source review. Explicit narrative roles stay unchanged.
    """
    slots = plan.get("slots") or []
    if (not _local_continuous_plan_requested(brief) or not explicit_source_continuity_requested(brief)
            or _configured_story_roles(brief) or len(slots) != 1
            or slots[0].get("purpose") != SINGLE_PASSAGE_PURPOSE):
        return plan
    result = copy.deepcopy(plan)
    slot = result["slots"][0]
    slot["reference_context_chapter_ids"] = list(dict.fromkeys([
        *slot.get("reference_context_chapter_ids", []), *slot.get("required_context_chapter_ids", [])]))
    slot["required_context_chapter_ids"] = []
    result["context_policy"] = {"version":"candidate-local-source-context-v1",
        "scope":"exact_selected_candidate", "model_chapter_nominations":"unverified_reference_only",
        "required_context_basis":"exact_source_referents_and_cited_omitted_utterances",
        "semantic_verified":False}
    return result


def _evidence_bound_passage(option):
    return bool(option.get("ordered_source_group_search") is True
                or option.get("explicit_source_continuity_requested") is True)


def _single_passage_plan_capacity(plan, chapters, segments, brief):
    """Optimistic numeric supply of a proposed domain, never semantic approval.

    Chapter nominations limit subsequent retrieval. A domain that is already
    too short cannot meet the target even if every nominated beat is usable.
    A large domain is only a set of alternatives, not required inclusion.
    """
    if (not _local_continuous_plan_requested(brief)
            or str(brief.get("duration_mode") or "target") != "target" or not chapters):
        return None
    try:
        wanted = {str(value) for row in plan["slots"]
                  for key in ("chapter_ids", "required_context_chapter_ids", "reference_context_chapter_ids") for value in row.get(key, [])}
        by_chapter = {str(row["id"]): row for row in chapters}
        if not wanted or not wanted <= set(by_chapter):
            return None
        intervals = []
        for identifier in wanted:
            beats = by_chapter[identifier].get("beats")
            if not isinstance(beats, list) or not beats:
                return None
            for row in beats:
                start, end = row["start"], row["end"]
                if (any(isinstance(value, bool) or not isinstance(value, (int, float))
                        or not math.isfinite(value) for value in (start, end)) or end <= start or start < 0):
                    return None
                intervals.append((float(start), float(end)))
        all_rows = list(segments or []) + [beat for chapter in chapters for beat in chapter.get("beats", [])]
        source_end = max(float(row["end"]) for row in all_rows)
        bounds = effective_duration_bounds(brief, source_end)
        target = bounds["maximum_seconds"]
        if not math.isfinite(source_end) or not math.isfinite(target) or source_end <= 0 or target <= 0:
            return None
        # Counting overlaps more than once is conservative here: it can miss an
        # impossible proposal but cannot falsely establish an underfill.
        upper = (max(end for _, end in intervals) - min(start for start, _ in intervals)
                 if explicit_source_continuity_requested(brief)
                 else sum(end - start for start, end in intervals))
        return {"scope": "nominated_plan_domain_only", "optimistic_upper_bound_seconds": round(upper, 6),
                "required_target_minimum_seconds": round(bounds["minimum_seconds"], 6),
                "duration_bounds": bounds,
                "nominated_chapter_ids": sorted(wanted), "semantic_fit_verified": False, "selection_forced": False}
    except (KeyError, TypeError, ValueError, OverflowError):
        return None  # Missing geometry cannot prove an impossible domain.


def _build_story_plan(
    settings: Settings,
    summaries: list[dict[str, Any]],
    outline: dict[str, Any],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    segments: list[dict[str, Any]] | None = None,
    chapters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if progress:
        progress(0.56, "Building the narrative")
    target = effective_duration_bounds(brief)["maximum_seconds"]
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    if target <= 75:
        shape = "hook, minimum context, strongest proof/example, payoff, complete ending"
    elif target <= 210:
        shape = "hook, setup, reasoning, one or more examples/proofs, result, conclusion"
    else:
        shape = "representative chronological condensed story with setup, development, proof and conclusion"
    style_profile = brief.get("style_profile") or {}
    selection_policy = style_profile.get("selection_policy") or {}
    required_roles = _configured_story_roles(brief)
    single_passage = _local_continuous_plan_requested(brief)
    if required_roles:
        shape = ", ".join(required_roles)
    shape_guidance = (
        f"The explicit user-requested story roles are: {shape}. "
        if required_roles else
        f"An optional shape suggestion for this length is: {shape}. Omit any suggested role the source does not support. "
    )
    if single_passage and not required_roles:
        shape_guidance = (
            "The user explicitly requests ONE self-contained source passage. Emit exactly ONE slot describing that passage's actual idea. "
            "Choose the best local conversation passage from anywhere in the recording, rather than condensing the whole episode. "
            "Do not create hook/setup/proof/payoff/ending slots or stitch different topics into a new narrative. "
            f"Use the neutral exact purpose {SINGLE_PASSAGE_PURPOSE!r}; a complete local idea need not be an episode conclusion or prove a global theme. "
            "chapter_ids are candidate regions for that one passage, not a requirement to include each region. "
        )
    moment_limit = selection_policy.get("max_moments")
    style_contract = (
        f" Select at most {moment_limit} distinct complete moment(s); retain the context each actual passage needs. "
        "A shorter complete story is preferable to unrelated padding. "
        if moment_limit else ""
    )
    if required_roles:
        style_contract += (
            " Emit exactly one slot for EACH explicitly requested required role using its exact purpose string, even for one chapter. "
            "These are minimum coverage requirements, not an exhaustive role list. Additional source-supported context roles are allowed. "
            "Independent include-role requests do not dictate order; only ordered_role_groups in the brief impose relative order. "
            "The same chapter and complete source unit may support multiple roles when their actual content supplies each role; "
            "later selection must explain that evidence explicitly. Do not omit roles because the source has only one chapter, "
            "and do not invent missing action or outcomes. "
        )
    if single_passage:
        style_contract += (
            " All selected roles and prerequisite context must serve ONE coherent self-contained idea. "
            "Meaning-preserving cuts between related complete source utterances are allowed unless the original instruction explicitly forbids cuts. "
            "One semantic unit does not require consecutive source units. Explicit roles still require their actual source evidence; "
            "return no supported plan rather than joining distant topics to manufacture them. "
            f"The passage allocation must be finite, positive and no more than {target:g} seconds. "
        )
    if explicit_source_continuity_requested(brief):
        style_contract += (
            " The original instruction explicitly requires continuous source footage without internal omissions. "
            "All selected source units must be consecutive, including their intervening source time; "
            "do not shorten internal pauses to meet a conflicting duration. Report that conflict. "
        )
    plan_schema = copy.deepcopy(STORY_PLAN_SCHEMA)
    if required_roles:
        plan_schema["properties"]["slots"]["minItems"] = len(required_roles)
    elif single_passage:
        plan_schema["properties"]["slots"].update(minItems=1, maxItems=1)
        plan_schema["properties"]["slots"]["items"]["properties"]["purpose"] = {
            "type": "string", "enum": [SINGLE_PASSAGE_PURPOSE]}
    source_capacity = _single_passage_plan_capacity(
        {"slots": [{"chapter_ids": [row["id"] for row in chapters or []]}]}, chapters, segments, brief)
    payload = {
        "model": model,
        "stream": False,
        "format": plan_schema,
        "_performance_mode": mode,
        "options": {"temperature": 0.05, "num_ctx": 12288, "num_predict": 1300},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM Story Producer. Turn the global outline into an editorial plan before any exact clips are chosen. "
                    + shape_guidance + "Respect dependencies: never use a payoff that becomes confusing because its setup was removed. "
                    + style_contract +
                    "Use material from anywhere in the recording when it improves the story. Return JSON only with keys narrative,slots. "
                    "Use source_beat_costs to budget complete source passages using minimum_safe_seconds; speech cannot be removed to meet the target. "
                    "slots is a list of {purpose,chapter_ids,desired_seconds,reason,required_context_chapter_ids}. Only use supplied chapter IDs."
                    " Outline and chapter prose are unverified interpretations; source_evidence is authoritative. "
                    "Choose source-supported meanings without inventing unseen events. A result may be a stated refusal, decision or qualified conclusion. "
                    "Task controls and the original user instruction take precedence over style preferences. Preferred style structure is advisory; "
                    "an absent joke, punchline, reaction or other preferred template role must not create a mandatory slot. "
                    "Every actual emitted slot must still be supported by the source and retain its prerequisite context."
                ),
            },
            {"role": "user", "content": json.dumps({
                "brief": brief, "target_seconds": target, "outline": outline, "chapters": summaries,
                "duration_policy": {"mode": str(brief.get("duration_mode") or "target"),
                    "minimum_target_seconds": source_capacity["required_target_minimum_seconds"] if source_capacity else None,
                    "scope": "numeric_target_only_not_semantic_approval"},
                "interpretation_status": "outline_and_summaries_unverified",
                "source_evidence": _global_source_evidence(chapters, segments),
                "source_beat_costs": [{"id": str(beat["id"]), "chapter_id": str(chapter["id"]),
                    "duration_cost": _story_selection_cost([str(beat["id"])], chapter.get("beats", []), segments or [], brief)}
                    for chapter in (chapters or []) for beat in chapter.get("beats", [])],
            }, ensure_ascii=False)},
        ],
    }
    payload = _bounded_global_story_payload(payload, chapters or [], summaries, mode)
    if single_passage:
        payload["_single_attempt"] = True  # At most two physical planning requests, including correction.
    for attempt in range(2 if single_passage else 1):
        _check_cancelled(cancel_check)
        result = _call_ollama_story_pass(settings, payload, 240, cancel_check)
        raw_slots = result.get("slots") if isinstance(result, dict) else None
        issues = []
        capacity = None
        if single_passage:
            if not isinstance(raw_slots, list) or (not required_roles and len(raw_slots) != 1):
                issues.append("Emit exactly one passage slot; a multi-part episode template violates the requested single passage.")
            elif not required_roles and (not isinstance(raw_slots[0], dict) or raw_slots[0].get("purpose") != SINGLE_PASSAGE_PURPOSE):
                issues.append("Use the exact neutral purpose self_contained_passage; the user did not request a conclusion or another narrative role.")
            for row in raw_slots if isinstance(raw_slots, list) else []:
                try:
                    if isinstance(row["desired_seconds"], bool):
                        raise ValueError("boolean allocation")
                    seconds = float(row["desired_seconds"])
                    if not math.isfinite(seconds) or not 0 < seconds <= target:
                        raise ValueError("invalid allocation")
                except (ValueError, TypeError, KeyError):
                    issues.append("Every passage allocation must be a finite positive number within target_seconds.")
                    break
            if not issues:
                capacity = _single_passage_plan_capacity({"slots": raw_slots}, chapters, segments, brief)
                if capacity and capacity["optimistic_upper_bound_seconds"] + .05 < capacity["required_target_minimum_seconds"]:
                    issues.append(
                        "The nominated source domain is too short even if all its material is usable. "
                        "Choose a different supported passage or broader candidate regions from the intact source index. "
                        "Regions are alternatives; do not force unrelated material, pad the output or lower the requested target.")
        if not issues:
            break
        if attempt:
            raise StoryPlanningError("Story AI did not respect the explicit single-passage plan after one correction. No new draft was applied.",
                {"outcome": "invalid_model_output", "reason": "single_passage_plan_conflict", "applied_to_timeline": False,
                 "planning_attempts": 2, "issues": issues})
        # Replan against the intact source index and original request. Never
        # silently delete emitted roles or relabel an unrelated multi-part plan.
        payload = copy.deepcopy(payload)
        content = json.loads(payload["messages"][-1]["content"])
        content["plan_correction"] = {"rejected_slot_count": len(raw_slots) if isinstance(raw_slots, list) else None,
                                      "issues": issues, "instruction": "Replace the invalid proposal with a fresh supported single-passage plan."}
        if capacity is not None:
            content["plan_correction"]["candidate_capacity"] = capacity
        payload["messages"][-1]["content"] = json.dumps(content, ensure_ascii=False)
        if not _story_payload_fits_cap(payload, mode):
            raise StoryPlanningError("Single-passage planning correction exceeds the intact context budget; no source was truncated.",
                {"outcome": "technical_error", "reason": "story_input_context_limit", "applied_to_timeline": False})
    valid = {item["id"] for item in summaries}
    slots: list[dict[str, Any]] = []
    for row in result.get("slots", []) if isinstance(result.get("slots"), list) else []:
        if not isinstance(row, dict):
            continue
        chapter_ids = [str(value) for value in row.get("chapter_ids", []) if str(value) in valid]
        if not chapter_ids:
            continue
        required = [str(value) for value in row.get("required_context_chapter_ids", []) if str(value) in valid]
        try:
            desired = max(2.0, min(target, float(row.get("desired_seconds") or target / 5)))
        except (TypeError, ValueError):
            desired = target / 5
        slots.append({
            "purpose": str(row.get("purpose") or "development")[:80],
            "chapter_ids": chapter_ids,
            "desired_seconds": round(desired, 2),
            "reason": str(row.get("reason") or "")[:320],
            "required_context_chapter_ids": required,
        })
    minimum_slots = 1  # A complete supported passage can come from a multi-chapter source.
    plan = {"narrative": str(result.get("narrative") or "")[:1000], "slots": slots}
    if single_passage:
        plan["passage_constraint"] = {"origin": "explicit_user_instruction",
                                      "semantic_unit_count": 1 if single_source_passage_requested(brief) else None,
                                      "source_range_count": 1 if explicit_source_continuity_requested(brief) else None,
                                      "source_range_origin": ("explicit_review_control" if brief.get("source_continuity") == "required"
                                                              else "explicit_user_instruction") if explicit_source_continuity_requested(brief) else "unspecified",
                                      "continuity": ("explicitly_required" if explicit_source_continuity_requested(brief)
                                                     else "unspecified"),
                                      "semantic_coherence": "requires_independent_source_review"}
    plan["role_requirements"] = [{"purpose": row["purpose"], "origin": "user" if row["purpose"] in required_roles else "source_plan",
                                  "authority": "required", "verification_status": "pending_source_validation"} for row in slots]
    _validate_configured_story_roles(plan, brief)
    if len(slots) < minimum_slots:
        raise StoryPlanningError("Story AI could not build a complete narrative plan.")
    return _candidate_local_context_plan(plan, brief)


def _validate_single_source_passage(keep: list[str], chapters: list[dict[str, Any]], brief: dict[str, Any]) -> None:
    """Only explicit source continuity forbids skipped canonical source units.

    This mechanical continuity check does not establish a coherent meaning,
    accurate ASR, complete context or editorial quality. Those reviews remain.
    """
    if not explicit_source_continuity_requested(brief):
        return
    ordered = sorted((beat for chapter in chapters for beat in chapter.get("beats", [])),
                     key=lambda row: (float(row["start"]), float(row["end"]), str(row["id"])))
    identifiers = [str(row["id"]) for row in ordered]
    selected = set(keep)
    positions = [index for index, identifier in enumerate(identifiers) if identifier in selected]
    if (not positions or len(positions) != len(selected)
            or set(identifiers[positions[0]:positions[-1] + 1]) != selected):
        raise StoryPlanningError("The requested single source passage skips original source units. No new draft was applied.",
            {"outcome": "invalid_model_output", "reason": "single_passage_source_discontinuity",
             "applied_to_timeline": False, "selected_beat_ids": list(keep)})


def _candidate_beats_for_plan(chapters: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    wanted: set[str] = set()
    for slot in plan.get("slots", []):
        wanted.update(str(value) for value in slot.get("chapter_ids", []))
        wanted.update(str(value) for value in slot.get("required_context_chapter_ids", []))
        wanted.update(str(value) for value in slot.get("reference_context_chapter_ids", []))
    candidates: list[dict[str, Any]] = []
    for chapter in chapters:
        if chapter["id"] in wanted:
            candidates.extend(chapter["beats"])
    return candidates


def _story_selection_cost(
    identifiers: list[str], candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    brief: dict[str, Any],
) -> dict[str, Any]:
    valid = {str(row["id"]): row for row in candidates}
    duration = max([float(row.get("end", 0)) for row in segments + candidates] or [0.0])
    ranges = [{"start": float(valid[value]["start"]), "end": float(valid[value]["end"])}
              for value in identifiers if value in valid]
    if explicit_source_continuity_requested(brief) and ranges:
        # Price the actual uninterrupted playback, including untranscribed gaps.
        # Membership/source validation remains independent of this numeric cost.
        ranges = [{"start": min(r["start"] for r in ranges), "end": max(r["end"] for r in ranges)}]
    return story_duration_cost(
        ranges, segments, duration,
        target=effective_duration_bounds(brief, duration)["maximum_seconds"],
        protect_action_span=bool(explicit_source_continuity_requested(brief) or ((brief.get("style_profile") or {}).get("selection_policy") or {}).get("protect_action_span")),
    )


def _source_selection_target_interval(cost: dict[str, Any], source_duration: float, duration_mode: str,
                                      brief: dict[str, Any] | None = None) -> dict[str, Any]:
    """Numeric targets for this unchanged source selection, never story approval."""
    if brief is not None:
        bounds = effective_duration_bounds(brief, source_duration)
        if bounds["explicit"]:
            return {"scope": "unchanged_explicit_duration_request", **bounds,
                    "semantic_fit_verified": False, "requires_frame_validation": True,
                    "request_change_suggested": False}
    upper = min(source_duration, float(cost["approved_seconds"]) / .9) if duration_mode == "target" else None
    return {"scope": "unchanged_current_source_selection", "target_kind": "effective_target",
            "minimum_seconds": round(float(cost["minimum_safe_seconds"]), 3),
            "maximum_seconds": round(upper, 3) if upper is not None else None,
            "semantic_fit_verified": False, "requires_frame_validation": True}


def _explicit_source_context_ids(selection: dict[str, Any], candidates: list[dict[str, Any]],
                                 segments: list[dict[str, Any]]) -> set[str]:
    """Resolve typed source prerequisites without interpreting narrative prose."""
    known_beats, known_segments = {row["id"] for row in candidates}, {row["id"] for row in segments}
    owner = {identifier: row["id"] for row in candidates for identifier in row.get("segment_ids", [])}
    required = set()
    for key, domain in (("required_context_beat_ids", known_beats), ("required_context_segment_ids", known_segments)):
        values = selection.get(key, [])
        if (not isinstance(values, list) or any(not isinstance(value, str) or value not in domain for value in values)
                or len(values) != len(set(values))):
            raise ValueError("Mandatory source prerequisites need exact unique canonical IDs.")
        if key == "required_context_segment_ids":
            if not set(values) <= set(owner):
                raise ValueError("Mandatory source context is outside the retrieved complete source units.")
            required.update(owner[value] for value in values)
        else:
            required.update(values)
    return required


def _validated_story_slot_map(
    rows: Any, keep: list[str], candidates: list[dict[str, Any]], chapters: list[dict[str, Any]],
    plan: dict[str, Any], *, sticky_context: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate role-specific source coverage, never chapter presence alone."""
    slots = plan.get("slots")
    if not isinstance(slots, list) or not slots or not isinstance(rows, list) or len(rows) != len(slots):
        raise ValueError("Every narrative slot needs one explicit source assignment.")
    valid = {str(beat["id"]): beat for beat in candidates}
    beat_chapters = {str(beat["id"]): str(chapter["id"])
                     for chapter in chapters for beat in chapter.get("beats", [])}
    mapped, seen, clean = set(), set(), []
    for row in rows:
        if not isinstance(row, dict) or type(row.get("slot_index")) is not int:
            raise ValueError("A narrative slot has an invalid index.")
        index = row["slot_index"]
        if index in seen or not 0 <= index < len(slots):
            raise ValueError("Narrative slot indexes must be exact and unique.")
        slot = slots[index]
        if row.get("purpose") != str(slot.get("purpose") or ""):
            raise ValueError("A narrative slot changed its planned purpose.")
        for key in ("primary_beat_ids", "context_beat_ids"):
            values = row.get(key)
            if (not isinstance(values, list) or any(not isinstance(value, str) or value not in valid for value in values)
                    or len(values) != len(set(values)) or not set(values) <= set(keep)):
                raise ValueError("Narrative assignments must use unique selected source beat IDs.")
        primary, context = row["primary_beat_ids"], row["context_beat_ids"]
        primary_chapters = {str(value) for value in slot.get("chapter_ids", [])}
        required_chapters = {str(value) for value in slot.get("required_context_chapter_ids", [])}
        if not primary or not all(beat_chapters.get(value) in primary_chapters for value in primary):
            raise ValueError("Context cannot replace a slot's primary story material.")
        if ({beat_chapters.get(value) for value in context} != required_chapters
                or any(beat_chapters.get(value) not in required_chapters for value in context)):
            raise ValueError("Every required context chapter needs its own explicit context assignment.")
        identifiers = sorted(set(primary + context), key=lambda value: float(valid[value]["start"]))
        mapped.update(identifiers)
        seen.add(index)
        clean.append({"slot_index": index, "purpose": row["purpose"], "primary_beat_ids": list(primary),
                      "context_beat_ids": list(context), "beat_ids": identifiers,
                      **{key: copy.deepcopy(row[key]) for key in ("primary_evidence_ids", "context_evidence_ids", "temporal_witness_id")
                         if key in row}})
    if set(keep) != mapped | (sticky_context or set()):
        raise ValueError("Selected source material must have an explicit narrative role or required critic context.")
    return sorted(clean, key=lambda row: row["slot_index"])


def _story_evidence_proof(
    slot_map: list[dict[str, Any]], keep: list[str], candidates: list[dict[str, Any]],
    segments: list[dict[str, Any]], plan: dict[str, Any], brief: dict[str, Any], rejected: set[str] | None = None,
) -> dict[str, Any]:
    return validate_story_evidence(slot_map, candidates, segments, selected_beat_ids=keep,
        required_roles=_configured_story_roles(brief) or None,
        required_role_orders=required_story_role_orders(brief),
        rejected_beat_ids=sorted(rejected or set()))


def _extractive_story_summary(proof: dict[str, Any]) -> str:
    """Display complete cited source excerpts, including qualifying context."""
    return extractive_story_summary(proof)


def _story_units_complete(identifiers: list[str], candidates: list[dict[str, Any]], segments: list[dict[str, Any]]) -> bool:
    valid = {str(row["id"]): row for row in candidates}
    source_by_id = {str(row["id"]): row for row in segments}
    try:
        for identifier in identifiers:
            beat = valid[identifier]
            ids = beat.get("segment_ids")
            if (not isinstance(ids, list) or not ids or len(ids) != len(set(ids))
                    or any(value not in source_by_id for value in ids)):
                return False
            if not _sentence_ending_complete(str(beat.get("text") or "")):
                # An exposed prefix is still conditional on its original
                # following complete ASR entry. It may never end a selection.
                mates = [r for r in candidates if beat.get("entry_owner_id")
                         and r.get("entry_owner_id") == beat["entry_owner_id"] and r["start"] >= beat["end"]]
                if (not mates or mates[0]["id"] not in identifiers
                        or not _sentence_ending_complete(mates[0]["text"])):
                    return False
            source = [source_by_id[value] for value in ids]
            overlapping = [row for row in segments if float(row["start"]) < float(beat["end"]) - .001
                           and float(row["end"]) > float(beat["start"]) + .001]
            if ({str(row["id"]) for row in overlapping} != set(ids)
                    or normalize_text(str(beat.get("text") or "")) != normalize_text(" ".join(str(row.get("text") or "") for row in source))
                    or any(float(row["start"]) < float(beat["start"]) - .001
                           or float(row["end"]) > float(beat["end"]) + .001 for row in source)
                    or abs(min(float(row["start"]) for row in source) - float(beat["start"])) > .001
                    or abs(max(float(row["end"]) for row in source) - float(beat["end"])) > .001):
                return False
    except (ValueError, TypeError, KeyError):
        return False
    return bool(identifiers)


def _verify_non_short_story_evidence(
    selection: dict[str, Any], precision_selection: dict[str, Any], candidates: list[dict[str, Any]],
    segments: list[dict[str, Any]], chapters: list[dict[str, Any]], plan: dict[str, Any], brief: dict[str, Any],
) -> dict[str, Any]:
    """Certify an actual clean critic's original typed precision evidence."""
    output = copy.deepcopy(selection)
    critic = output.get("critic") or {}
    keep = list(output.get("keep_beat_ids") or [])
    added, rejected = _critic_action_sets(critic)
    sticky = added - rejected
    try:
        _validate_configured_story_roles(plan, brief)
        if (critic.get("verdict") != "pass" or critic.get("review_verdict") != "pass"
                or critic.get("issues") or critic.get("unapplied_actions") or critic.get("unresolved_slot_indexes")
                or critic.get("selection_changed_after_review")
                or set(critic.get("reviewed_beat_ids") or []) != set(keep)
                or output.get("unresolved_plan_slot_indexes") or output.get("unresolved_context_slot_indexes")
                or precision_selection.get("recovered_slot_indexes") or precision_selection.get("recovery_reason")
                or not _story_units_complete(keep, candidates, segments)):
            raise ValueError("A clean unchanged model continuity review and complete typed source evidence are required.")
        slots = _validated_story_slot_map(precision_selection.get("slot_map"), keep, candidates, chapters, plan,
                                          sticky_context=sticky)
        proof = _story_evidence_proof(slots, keep, candidates, segments, plan, brief, rejected)
        source_spans = build_source_span_constraints(candidates, segments,
            selected_beat_ids=keep, rejected_beat_ids=sorted(rejected))
    except (ValueError, TypeError, KeyError) as exc:
        raise StoryPlanningError("Story AI did not verify the non-Short source evidence and story order. "
                                 + str(exc) + " No new draft was applied; the existing edit was kept.") from exc
    cost = _story_selection_cost(keep, candidates, segments, brief)
    output.update(slot_map=proof["slot_map"], semantic_mapping_verified=True, semantic_review_status="model_reviewed",
                  evidence_policy_version=EVIDENCE_POLICY_VERSION, evidence_proof=proof,
                  source_span_policy_version=SOURCE_SPAN_POLICY_VERSION, source_span_constraints=source_spans,
                  summary=whole_utterance_story_summary(source_spans), summary_source=SOURCE_SPAN_SUMMARY_SOURCE,
                  semantic_revision={"attempts": 0, "verdict": "fit", "released_optional_beat_ids": [],
                                     "policy_version": cost["policy_version"], "cost": cost,
                                     "duration_policy": "existing_non_short_policy"})
    return _reconcile_critic_actions(output)


def _story_evidence_choice_catalog(catalog: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Expose exact source wording first while retaining an unambiguous reference."""
    choices = {f"{row['text']} [{row['id']}]": row for row in catalog}
    if len(choices) != len(catalog):
        raise ValueError("Canonical source quotations need unique exact choice labels.")
    return choices


def _story_revision_slot_rows(roles: Any, catalog: list[dict[str, Any]],
                              plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Resolve chosen quotes to their canonical owners without assigning roles."""
    slots = plan["slots"]
    purposes = [row["purpose"] for row in slots]
    if not isinstance(roles, dict) or set(roles) != set(purposes):
        raise ValueError("Every planned purpose needs exactly one explicit quotation assignment.")
    by_choice = _story_evidence_choice_catalog(catalog)
    rows = []
    for index, purpose in enumerate(purposes):
        row = roles[purpose]
        if not isinstance(row, dict) or set(row) != {"primary_anchor_choice", "additional_primary_evidence_choices", "context_evidence_choices"}:
            raise ValueError("A story role must contain an explicit primary anchor, additional primary choices and context choices.")
        anchor = row["primary_anchor_choice"]
        if not isinstance(anchor, str) or anchor not in by_choice:
            raise ValueError("The primary anchor must be an exact allowed source quotation choice.")
        owners, identifiers = {}, {}
        for kind in ("primary", "context"):
            values = row["additional_primary_evidence_choices" if kind == "primary" else "context_evidence_choices"]
            if (not isinstance(values, list) or any(not isinstance(value, str) or value not in by_choice for value in values)
                    or len(values) != len(set(values))):
                raise ValueError("Story roles must select unique exact allowed source quotation choices.")
            if kind == "primary":
                if anchor in values:
                    raise ValueError("The primary anchor cannot be repeated among additional primary choices.")
                values = [anchor, *values]
            identifiers[kind] = [by_choice[value]["id"] for value in values]
            owners[kind] = list(dict.fromkeys(by_choice[value]["beat_id"] for value in values))
        rows.append({"slot_index": index, "purpose": purpose,
                     "primary_beat_ids": owners["primary"], "context_beat_ids": owners["context"],
                     "primary_evidence_ids": identifiers["primary"], "context_evidence_ids": identifiers["context"],
                     "temporal_witness_id": by_choice[anchor]["id"]})
    return rows


def _precision_story_contract(
    catalog: list[dict[str, Any]], candidates: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any], brief: dict[str, Any],
) -> dict[str, Any]:
    """Bind every planned purpose and context chapter to exact source choices."""
    slots = plan.get("slots")
    if not isinstance(slots, list) or not slots or any(not isinstance(row, dict) for row in slots):
        raise StoryPlanningError("Precision selection needs an explicit narrative plan.")
    purposes = [row.get("purpose") for row in slots]
    if (any(not isinstance(value, str) or not value.strip() for value in purposes)
            or len(purposes) != len(set(purposes))):
        raise StoryPlanningError("Precision plan purposes must be nonempty and unique.")
    _validate_configured_story_roles(plan, brief)
    configured = _configured_story_roles(brief)
    by_choice = _story_evidence_choice_catalog(catalog)
    identifiers = [str(row["id"]) for row in candidates]
    chapter_ids = [str(row["id"]) for row in chapters]
    if len(identifiers) != len(set(identifiers)) or len(chapter_ids) != len(set(chapter_ids)):
        raise StoryPlanningError("Precision source identifiers must be unique.")
    beat_chapters: dict[str, str] = {}
    for chapter in chapters:
        for beat in chapter.get("beats", []):
            identifier = str(beat["id"])
            if identifier in beat_chapters:
                raise StoryPlanningError("Precision source beats need one canonical chapter owner.")
            beat_chapters[identifier] = str(chapter["id"])
    if any(identifier not in beat_chapters for identifier in identifiers):
        raise StoryPlanningError("Precision source beats need canonical chapter ownership.")
    definitions: dict[str, Any] = {}
    names: dict[tuple[str, ...], str] = {}
    fit_available = True

    def choice_reference(values: list[str]) -> dict[str, Any]:
        nonlocal fit_available
        if not values:
            fit_available = False
            return {"type": "string"}  # The fit branch is omitted without canonical support.
        domain = tuple(values)
        if domain not in names:
            name = f"precision_choices_{len(names)}"
            names[domain] = name
            definitions[name] = {"type": "string", "enum": values}
        return {"$ref": "#/$defs/" + names[domain]}

    roles = {}
    for slot in slots:
        domains = []
        for key in ("chapter_ids", "required_context_chapter_ids"):
            values = slot.get(key)
            if (not isinstance(values, list) or any(not isinstance(value, str) or value not in chapter_ids for value in values)
                    or len(values) != len(set(values)) or (key == "chapter_ids" and not values)):
                raise StoryPlanningError("Precision roles need exact allowed primary and context chapter domains.")
            domains.append(values)
        primary, context = domains
        choices = [choice for choice, row in by_choice.items() if beat_chapters.get(row["beat_id"]) in primary]
        context_properties = {}
        for chapter_id in context:
            values = [choice for choice, row in by_choice.items() if beat_chapters.get(row["beat_id"]) == chapter_id]
            context_properties[chapter_id] = {"type": "array", "minItems": 1, "uniqueItems": True,
                                              "items": choice_reference(values)}
        roles[slot["purpose"]] = {
            "type": "object", "additionalProperties": False,
            "properties": {
                "primary_anchor_choice": choice_reference(choices),
                "additional_primary_evidence_choices": {"type": "array", "uniqueItems": True, "items": choice_reference(choices)},
                "context_evidence_choices_by_chapter": {"type": "object", "additionalProperties": False,
                    "properties": context_properties, "required": list(context),
                    **({"maxProperties": 0} if not context else {})},
            },
            "required": ["primary_anchor_choice", "additional_primary_evidence_choices", "context_evidence_choices_by_chapter"],
        }
    fit = {"type": "object", "additionalProperties": False,
           "properties": {"verdict": {"type": "string", "enum": ["fit"]},
               "role_selections": {"type": "object", "additionalProperties": False, "properties": roles, "required": purposes},
               "highlight_beat_ids": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": identifiers}},
               "title": {"type": "string"}, "summary": {"type": "string"}},
           "required": ["verdict", "role_selections", "highlight_beat_ids", "title", "summary"]}
    refusal = {"type": "object", "additionalProperties": False,
               "properties": {"verdict": {"type": "string", "enum": ["no_fit"]},
                   "reason": {"type": "string", "enum": ["unsupported_roles", "insufficient_context", "source_order", "target_budget"]},
                   "missing_purposes": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": purposes}}},
               "required": ["verdict", "reason", "missing_purposes"]}
    # anyOf and local definitions are already used by the final story grammar.
    return {"anyOf": [fit, refusal] if fit_available else [refusal], "$defs": definitions}


def _precision_story_slot_rows(
    roles: Any, catalog: list[dict[str, Any]], candidates: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any],
) -> list[dict[str, Any]]:
    """Normalize explicit per-chapter choices without assigning missing roles."""
    purposes = [row["purpose"] for row in plan["slots"]]
    if not isinstance(roles, dict) or set(roles) != set(purposes):
        raise ValueError("Every planned purpose needs one explicit precision assignment.")
    by_choice = _story_evidence_choice_catalog(catalog)
    beat_chapters = {str(beat["id"]): str(chapter["id"]) for chapter in chapters for beat in chapter.get("beats", [])}
    normalized = {}
    for slot in plan["slots"]:
        row = roles[slot["purpose"]]
        if not isinstance(row, dict) or set(row) != {"primary_anchor_choice", "additional_primary_evidence_choices", "context_evidence_choices_by_chapter"}:
            raise ValueError("Precision roles need an explicit primary anchor and chapter-keyed context choices.")
        contexts = row["context_evidence_choices_by_chapter"]
        required = slot["required_context_chapter_ids"]
        if not isinstance(contexts, dict) or set(contexts) != set(required):
            raise ValueError("Every required context chapter needs an explicit quotation list.")
        primary = row["additional_primary_evidence_choices"]
        if not isinstance(primary, list):
            raise ValueError("Additional primary choices must be a quotation list.")
        for choice in [row["primary_anchor_choice"], *primary]:
            if (not isinstance(choice, str) or choice not in by_choice
                    or beat_chapters.get(by_choice[choice]["beat_id"]) not in slot["chapter_ids"]):
                raise ValueError("Primary quotations must belong to the planned primary chapters.")
        flattened = []
        for chapter_id in required:
            values = contexts[chapter_id]
            if (not isinstance(values, list) or not values or len(values) != len(set(value for value in values if isinstance(value, str)))
                    or any(not isinstance(value, str) or value not in by_choice
                           or beat_chapters.get(by_choice[value]["beat_id"]) != chapter_id for value in values)):
                raise ValueError("Context quotations must be unique exact choices from their required chapter.")
            flattened.extend(values)
        normalized[slot["purpose"]] = {"primary_anchor_choice": row["primary_anchor_choice"],
            "additional_primary_evidence_choices": primary, "context_evidence_choices": flattened}
    return _story_revision_slot_rows(normalized, catalog, plan)


def _story_target_reasoning_policy(settings: Settings, model: str) -> dict[str, Any]:
    """The bounded final grammar uses compact output for every model."""
    return {"mode": "compact", "think": False, "num_predict": 2400,
            "max_attempts": 1, "timeout_seconds": 240}


def _story_playback_semantic_projection(playback_ranges, segments, brief):
    """Describe only source time actually kept/omitted by this proposed edit.

    Analysis-unit boundaries and possible future pause fits are not edit facts.
    A source gap without an ASR row is still unverified audio, never asserted
    silence. Preserve every positive omission without guessing editorial harm.
    """
    ranges, omissions = [], []
    previous = None
    for row in playback_ranges:
        start, end = row.get("start"), row.get("end")
        if (any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (start, end)) or start < 0 or end <= start
                or previous is not None and start < previous):
            raise StoryPlanningError("Actual playback ranges are invalid; semantic review was not attempted.")
        if previous is not None and start > previous:
            omissions.append({"start": previous, "end": start, "duration_seconds": start - previous,
                "overlapping_segment_ids": [r["id"] for r in segments
                    if r["start"] < start and r["end"] > previous]})
        ranges.append({"start": start, "end": end})
        previous = end
    from .critic_evidence import review_joins
    return {"playback_ranges": ranges, "playback_seconds": sum(r["end"] - r["start"] for r in ranges),
            "joins": review_joins(ranges, segments),
            "actual_source_omissions": omissions, "actual_source_omission_count": len(omissions),
            "source_continuity_required": explicit_source_continuity_requested(brief),
            "gap_audio_activity": "unverified; absence of ASR is not proof of silence",
            "analysis_boundaries_are_cuts": False, "semantic_verified": False}


def _fixed_passage_final_request(payload, selection, candidates, segments, chapters, plan, brief, actions, cancel_check):
    """Reuse final semantic adjudication, without asking it to rebuild times."""
    binding = selection.get("passage_option_selection")
    if not isinstance(binding, dict) or not _fixed_passage_choice_plan(candidates, plan, brief):
        raise StoryPlanningError("The fixed passage binding is invalid for this instruction.")
    options = _passage_options(candidates, segments, chapters, plan, brief, cancel_check,
        source_quality=(binding.get("enumeration") or {}).get("source_quality"))
    option = next((r for r in options["options"] if r["id"] == binding.get("candidate_id")), None)
    if (option is None or option != binding.get("option")
            or selection.get("keep_beat_ids") != option["beat_ids"]):
        raise StoryPlanningError("The fixed passage source identity or membership changed; no final approval was attempted.")
    from .passage_binding import validate_binding, review_source_scope
    try: exact_binding=validate_binding(selection,segments)
    except (ValueError,TypeError,KeyError) as exc:
        raise StoryPlanningError("The selected candidate text binding changed before final review.") from exc
    data = json.loads(payload["messages"][1]["content"])
    catalog = build_story_evidence_catalog(candidates, segments)
    proposal = _passage_option_proposal(option, catalog, chapters, plan)
    decision_properties = {"action": {"type": "string", "enum": ["add", "remove"]},
        "beat_id": {"enum": list(dict.fromkeys(a["beat_id"] for a in actions))},
        "decision": {"type": "string", "enum": ["accept", "decline", "uncertain"]},
        "source_evidence_ids": {"type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"enum": [r["id"] for r in catalog]}}, "reason": {"type": "string"}}
    result = copy.deepcopy(payload)
    result["format"] = {"type": "object", "additionalProperties": False,
        "required": ["verdict", "candidate_id", "semantic_reason", "refusal_category", "cited_segment_ids", "critic_action_decisions"],
        "properties": {"verdict": {"type": "string", "enum": ["fit", "no_fit"]},
            "candidate_id": {"enum": [option["id"]]}, "semantic_reason": {"type": "string","minLength":1},
            "refusal_category": {"enum": ["none", "semantic_rejection", "uncertain", "temporal_uncertainty"]},
            "cited_segment_ids": {"type": "array", "uniqueItems": True, "items": {"enum": [s["id"] for s in segments]}},
            "critic_action_decisions": ({"type": "array", "minItems": len(actions), "maxItems": len(actions),
                "items": {"type": "object", "additionalProperties": False,
                    "properties": decision_properties, "required": list(decision_properties)}} if actions else {"type": "array", "maxItems": 0})}}
    strict = _evidence_bound_passage(option)
    review_segments=review_source_scope(candidates,segments) if strict else segments
    playback = _story_playback_semantic_projection(option["playback_ranges"], review_segments, brief)
    if strict:
        from .critic_evidence import review_evidence_schema
        result["format"]["required"].append("rejection_evidence")
        result["format"]["properties"]["rejection_evidence"] = review_evidence_schema(review_segments, playback["joins"], selected_segment_ids=option["segment_ids"],instruction=brief.get("instruction",""))
        result["format"]["properties"]["cited_segment_ids"]["items"]["enum"]=[r["id"] for r in review_segments]
        result["format"]["anyOf"]=[{"properties":{"verdict":{"const":"fit"},"refusal_category":{"const":"none"},
            "cited_segment_ids":{"minItems":1,"items":{"enum":option["segment_ids"]}},"rejection_evidence":{"maxItems":0}}},
            {"properties":{"verdict":{"const":"no_fit"},"refusal_category":{"const":"semantic_rejection"},
                "rejection_evidence":{"minItems":1},"critic_action_decisions":{"maxItems":0}}},
            {"properties":{"verdict":{"const":"no_fit"},"refusal_category":{"enum":["uncertain","temporal_uncertainty"]},
                "rejection_evidence":{"maxItems":0},"critic_action_decisions":{"maxItems":0}}}]
    result["messages"] = [{"role": "system", "content":
        "You are CUTROOM's final semantic budget editor. Independently assess this EXACT fixed candidate as one coherent, self-contained account. "
        "The application guarantees its original source order, fixed membership and raw duration band. Do not choose timestamps, end anchors, source roles or replacement source. "
        "actual_playback lists the real kept ranges and source omissions. Adjacent source units are not cuts; omitted source time is not known silence. "
        "One output or one coherent account does not require one continuous utterance unless source_continuity_required is true. "
        "Numeric validity does NOT establish meaning, complete thoughts, necessary context or correct ASR. Read exact source wording in its original language and the verbatim user instruction. "
        "Reject broken joins, unsupported claims and context-dependent openings/endings when they prevent a self-contained meaning. Source ASR is not verified audio. "
        "Critic actions remain unverified advisory proposals. Check actual selected membership before accepting an omission allegation; presence alone does not prove sufficient context. "
        "Independently adjudicate every proposal using its exact target source_evidence_ids and explanation. Optional style is not an explicit hard instruction. "
        "For fit every critic action must be declined with grounded reasons: accepting a real source change requires no_fit for this unchanged candidate, not a blind restoration. "
        "For fit cite selected canonical segment IDs supporting your semantic reason. For uncertainty or necessary edits return no_fit and explain the actual meaning/context defect. "
        "Use refusal_category=none for fit, semantic_rejection for a specific meaning/context defect or necessary source edit, uncertain if verification is unfinished, or temporal_uncertainty for an unverified ordering concern. "
        "A source_order label alone is not evidence. No fit for this candidate is not no fit for the whole source."},
        {"role": "user", "content": json.dumps({"brief": data["brief"],
            "fixed_passage_candidate": {"id": option["id"], "segment_ids": option["segment_ids"],
                "source_text": " ".join(s["text"] for s in segments if s["id"] in set(option["segment_ids"])),
                "duration_bounds": option["duration_bounds"],
                "actual_playback": playback},
            "selected_source_utterances": [{k: s[k] for k in ("id", "start", "end", "text")}
                for s in segments if s["id"] in set(option["segment_ids"])],
            "source_units": [{k: r[k] for k in ("id", "start", "end", "segment_ids", "selected_in_proposal", "segments")}
                             for r in data["source_units"]], "source_evidence": catalog,
            "neighboring_source_utterances": data.get("neighboring_source_utterances", []),
            "critic_proposals": data.get("critic_proposals", {"authority": "advisory_only", "actions": []}),
            "explicit_user_constraints": {"verbatim_instruction": brief.get("instruction"),
                "source_continuity_required": explicit_source_continuity_requested(brief), "recognition_is_partial": True},
            "style_preferences": {"authority": "advisory_only", "profile": brief.get("style_profile", {})}}, ensure_ascii=False)}]
    if strict:
        result["messages"][0]["content"] += (" For fit use rejection_evidence=[]. For semantic_rejection supply exactly one rejection_evidence record with exact selected source_segment_ids. "
            "For missing_context identify actual unselected missing_context_segment_ids; for join_context cite the supplied join_id and exactly its left/right segment IDs. "
            "Other defects use join_id=null and missing_context_segment_ids=[]. For explicit_instruction copy the WHOLE verbatim instruction, including negations; every other kind uses instruction_quote=\"\". "
            "Use computed join IDs, never invent or associate timestamps yourself. Do not treat untranscribed time as missing words or known silence. "
            "Cited source quotes establish attribution only; unresolved ASR or interpretation remains uncertain. No independent source edit is authorized.")
    if strict:
        data=json.loads(result["messages"][1]["content"])
        data["fixed_passage_candidate"].pop("source_text",None)
        data["fixed_passage_candidate"]["source_binding_fingerprint"]=exact_binding["fingerprint"]
        data["reference_source_utterances"]=[{k:r[k] for k in ("id","start","end","text")} for r in review_segments if r["id"] not in set(option["segment_ids"])]
        data["reference_scope"]="retrieved candidate domain and explicit context neighbors only; other source prerequisites remain unverified"
        data.pop("neighboring_source_utterances",None)
        if not actions:
            data["source_units"]=[{k:r[k] for k in ("id","start","end","segment_ids","selected_in_proposal")} for r in data["source_units"] if r["selected_in_proposal"]]
            data.pop("source_evidence",None)
        result["messages"][1]["content"]=json.dumps(data,ensure_ascii=False)
        result["messages"][0]["content"] += " selected_source_utterances is the exact fixed candidate. reference_source_utterances is omitted reference only; never attribute its claims to the retained passage."
    if strict:
        from .structured_schema import complete_object_union
        result["format"] = complete_object_union(result["format"])
    return result, option, proposal


def _decode_fixed_passage_final(reply, option, proposal, actions, segments, *, review_segments=None):
    scope = {"scope": "one_fixed_passage_candidate", "candidate_id": option["id"],
             "source_wide_no_fit_proven": False, "applied_to_timeline": False}
    evidence_segments=segments if review_segments is None else review_segments
    fields = {"verdict", "candidate_id", "semantic_reason", "refusal_category", "cited_segment_ids", "critic_action_decisions"}
    if (not isinstance(reply, dict) or set(reply)-{"rejection_evidence"} != fields or reply.get("verdict") not in {"fit", "no_fit"}
            or reply.get("candidate_id") != option["id"] or not isinstance(reply.get("semantic_reason"), str)
            or not reply["semantic_reason"].strip() or not isinstance(reply.get("cited_segment_ids"), list)
            or reply.get("refusal_category") not in {"none", "semantic_rejection", "uncertain", "temporal_uncertainty"}
            or any(not isinstance(v, str) or v not in {s["id"] for s in evidence_segments} for v in reply["cited_segment_ids"])
            or len(reply["cited_segment_ids"]) != len(set(reply["cited_segment_ids"]))
            or not isinstance(reply.get("critic_action_decisions"), list)):
        raise StoryPlanningError("Malformed final fixed-candidate review.",
            {**scope, "reason": "invalid_fixed_candidate_review", "outcome": "invalid_model_output"})
    if _evidence_bound_passage(option):
        from .critic_evidence import review_joins, validate_review_evidence
        try:
            rejection_proof = validate_review_evidence(reply.get("rejection_evidence", []), evidence_segments, option["segment_ids"],
                review_joins(option["playback_ranges"], evidence_segments), option.get("verbatim_instruction", ""), issue_count=(1 if reply["verdict"]=="no_fit" and reply["refusal_category"]=="semantic_rejection" else 0))
        except (ValueError, TypeError, KeyError) as exc:
            raise StoryPlanningError("Final review evidence is invalid; source suitability remains unverified.",
                {**scope,"reason":"final_review_evidence_invalid","outcome":"invalid_model_output","attribution_error":str(exc)}) from exc
        if any(r["kind"] == "source_text_uncertainty" for r in rejection_proof):
            raise StoryPlanningError("Source wording remains unverified; no editorial rejection or approval was established.",
                {**scope,"reason":"source_text_verification_unfinished","outcome":"technical_error","source_text_verified":False})
    if reply["verdict"] == "no_fit":
        if reply["critic_action_decisions"] and _evidence_bound_passage(option):
            raise StoryPlanningError("A fixed no-fit response cannot also approve source edits.",
                {**scope,"reason":"invalid_fixed_candidate_review","outcome":"invalid_model_output"})
        if reply["refusal_category"] in {"uncertain", "temporal_uncertainty"}:
            raise StoryPlanningError("Final passage verification remains unfinished; no source unsuitability was established.",
                {**scope, "reason": "fixed_candidate_verification_unfinished", "outcome": "technical_error",
                 "model_reason": reply["semantic_reason"], "model_refusal_category": reply["refusal_category"], "semantic_result_verified": False})
        if reply["refusal_category"] != "semantic_rejection":
            raise StoryPlanningError("Final refusal omitted a valid category.",
                {**scope, "reason": "invalid_fixed_candidate_review", "outcome": "invalid_model_output"})
        raise StoryBudgetError("The final review did not verify this fixed candidate's meaning/context. Other source candidates remain unproven.",
            {**scope, "reason": "fixed_candidate_semantic_rejection", "outcome": "editorial_no_fit",
             "model_reason": reply["semantic_reason"], "cited_segment_ids": reply["cited_segment_ids"], "semantic_result_verified": False})
    if (reply["refusal_category"] != "none" or not reply["cited_segment_ids"] or not set(reply["cited_segment_ids"]) <= set(option["segment_ids"])
            or any(not isinstance(row, dict) or row.get("decision") != "decline" for row in reply["critic_action_decisions"])):
        raise StoryPlanningError("A fixed candidate cannot be approved using foreign evidence or a necessary source edit.",
            {**scope, "reason": "invalid_fixed_candidate_review", "outcome": "invalid_model_output"})
    role = proposal["role_selections"][SINGLE_PASSAGE_PURPOSE]
    result = {"verdict": "fit", "keep_beat_ids": list(option["beat_ids"]), "released_optional_beat_ids": [],
        "role_selections": {SINGLE_PASSAGE_PURPOSE: {"primary_anchor_choice": role["primary_anchor_choice"],
            "additional_primary_evidence_choices": role["additional_primary_evidence_choices"],
            "context_evidence_choices": list(dict.fromkeys(v for refs in role["context_evidence_choices_by_chapter"].values() for v in refs))}}}
    if actions:
        result["critic_action_decisions"] = copy.deepcopy(reply["critic_action_decisions"])
    elif reply["critic_action_decisions"]:
        raise StoryPlanningError("Final review invented a critic action.",
            {**scope, "reason": "invalid_fixed_candidate_review", "outcome": "invalid_model_output"})
    return result


def _review_story_target_budget(
    settings: Settings, selection: dict[str, Any], candidates: list[dict[str, Any]],
    segments: list[dict[str, Any]], chapters: list[dict[str, Any]], outline: dict[str, Any],
    plan: dict[str, Any], brief: dict[str, Any], model: str,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Allow one semantic revision before any required passage can be dropped."""
    if str(brief.get("goal") or "short") != "short":
        return selection
    _check_cancelled(cancel_check)
    _validate_configured_story_roles(plan, brief)
    purposes = [row.get("purpose") for row in plan.get("slots", []) if isinstance(row, dict)]
    if (not purposes or len(purposes) != len(plan.get("slots", []))
            or any(not isinstance(value, str) or not value.strip() for value in purposes)
            or len(purposes) != len(set(purposes))):
        raise StoryPlanningError("Story AI needs distinct, nonempty planned purposes for explicit source assignments. "
                                 "No new draft was applied; the existing edit was kept.")
    reasoning_policy = _story_target_reasoning_policy(settings, model)
    revision_attempted = False
    output = copy.deepcopy(selection)
    valid = {str(row["id"]): row for row in candidates}
    critic = output.get("critic") or {}
    added, rejected = _critic_action_sets(critic)
    sticky = added - rejected
    proposal_review = critic.get("action_authority") == "proposal"
    proposed_actions = ([{"action":action,"beat_id":identifier}
                         for action,key in [("add","requested_added"),("remove","requested_removed")]
                         for identifier in critic.get(key, [])] if proposal_review else [])
    current = sorted(set(output.get("keep_beat_ids") or []) | sticky,
                     key=lambda value: float(valid.get(value, {}).get("start", 0)))
    cost = _story_selection_cost(current, candidates, segments, brief)
    source_duration = max([float(row.get("end", 0)) for row in segments + candidates] or [0.0])
    bounds = effective_duration_bounds(brief, source_duration)
    target, minimum_target = bounds["maximum_seconds"], bounds["minimum_seconds"]
    feasibility: dict[str, Any] | None = None
    ending_domain: dict[str, Any] | None = None

    def fail(reason: str, detail: str, proposed_cost: dict[str, Any] | None = None,
             *, available_source_upper_bound: float | None = None, outcome: str | None = None) -> None:
        if outcome is None:
            outcome = ("editorial_no_fit" if reason == "planner_no_fit" else
                       "technical_error" if reason.startswith("semantic_revision_") else
                       "invalid_model_output" if reason.startswith("invalid_") else "constraint_conflict")
        diagnostic = {"kind": "story_budget", "scope": "current_required_selection", "target_seconds": target,
                      "required_policy_minimum_seconds": cost["minimum_safe_seconds"], "reason": reason,
                      "outcome": outcome,
                      "policy_version": cost["policy_version"], "applied_to_timeline": False,
                      "approved_seconds": cost["approved_seconds"], "minimum_target_seconds": round(minimum_target, 3)}
        diagnostic["semantic_revision"] = {"attempts": int(revision_attempted),
            "reasoning": {**reasoning_policy, "request_attempted": revision_attempted}}
        diagnostic["current_source_target_interval"] = _source_selection_target_interval(
            cost, source_duration, str(brief.get("duration_mode") or "target"), brief)
        if feasibility is not None:
            diagnostic["constraint_feasibility"] = copy.deepcopy(feasibility)
        if ending_domain is not None:
            diagnostic["final_ending_domain"] = copy.deepcopy(ending_domain)
        if proposed_cost is not None:
            diagnostic["proposed_revision_cost"] = {**copy.deepcopy(proposed_cost), "scope": "proposed_semantic_revision"}
        if available_source_upper_bound is not None:
            diagnostic["scope"] = "current_critic_allowed_source"
            diagnostic["available_complete_source_upper_bound_seconds"] = round(available_source_upper_bound, 3)
        message = ("Story AI completed the review but did not find a verified story fit. "
                   if outcome == "editorial_no_fit" else
                   "Story AI could not complete the single semantic review. "
                   if outcome == "technical_error"
                   else "Story AI returned output that did not pass the required validation. "
                   if outcome == "invalid_model_output"
                   else "Story AI could not validate a coherent story within the requested target. ")
        if reason == "allowed_source_below_target_minimum" and available_source_upper_bound is not None:
            interval = diagnostic["current_source_target_interval"]
            message += (f"The current critic-allowed complete source can supply at most {available_source_upper_bound:.2f} seconds, "
                        f"below the {minimum_target:.2f} seconds required for the {target:g}-second target. "
                        "This bound describes the current critic-allowed source, not the entire recording. "
                        f"For the unchanged selected source, the policy-only effective-target interval is {interval['minimum_seconds']:.2f}–{interval['maximum_seconds']:.2f}s, "
                        "subject to frame validation; this does not establish semantic approval. ")
        elif reason == "target_infeasible" and feasibility is not None:
            message += (f"Allowed complete source constraints require at least {feasibility['optimistic_lower_bound_seconds']:.2f} "
                        f"seconds of protected source material. The current required selection has a policy minimum of "
                        f"{cost['minimum_safe_seconds']:.2f} seconds; the target is {target:g} seconds. ")
        elif proposed_cost is not None and reason == "required_selection_exceeds_target":
            message += (f"The proposed revision needs at least {proposed_cost['minimum_safe_seconds']:.2f} seconds under the "
                        f"speech-and-pause policy; the target is {target:g} seconds. This describes the proposal only. ")
        elif reason == "required_selection_exceeds_target" and not cost["fits_target"]:
            message += (f"The current required selection needs at least {cost['minimum_safe_seconds']:.2f} seconds "
                        f"under the speech-and-pause policy; the target is {target:g} seconds. ")
        message += detail + " No new draft was applied; the existing edit was kept."
        raise StoryBudgetError(message, diagnostic)

    if any(not isinstance(value, str) or value not in valid for value in current):
        fail("invalid_source_selection", "The selected source identifiers are invalid; review the story plan.")
    # Source beats are indivisible. A model can select or release them, but may
    # not price a clipped transcript fragment as a complete semantic unit.
    segment_by_id = {str(row["id"]): row for row in segments}

    def complete_units(identifiers: list[str]) -> bool:
        return _story_units_complete(identifiers, candidates, segments)

    try:
        explicit_context = _explicit_source_context_ids(output, candidates, segments)
        existing_map = _validated_story_slot_map(output.get("slot_map"), current, candidates, chapters, plan,
                                                 sticky_context=sticky)
        existing_proof = _story_evidence_proof(existing_map, current, candidates, segments, plan, brief, rejected)
        existing_map = existing_proof["slot_map"]
        existing_spans = validate_source_span_constraints(
            output.get("source_span_constraints"), candidates, segments,
            selected_beat_ids=current, rejected_beat_ids=sorted(rejected))
        mapping_verified = (output.get("semantic_mapping_verified") is True
                            and output.get("semantic_review_status") == "model_reviewed"
                            and output.get("evidence_policy_version") == EVIDENCE_POLICY_VERSION
                            and output.get("source_span_policy_version") == SOURCE_SPAN_POLICY_VERSION
                            and explicit_context <= set(current)
                            and not output.get("recovered_slot_indexes") and not rejected.intersection(current)
                            and complete_units(current))
    except (ValueError, TypeError, KeyError):
        existing_map, existing_proof, mapping_verified = [], {}, False
    critic_clean = (critic.get("verdict") == "pass" and not critic.get("issues")
                    and not critic.get("unresolved_slot_indexes") and not critic.get("unapplied_actions")
                    and not output.get("unresolved_plan_slot_indexes") and not output.get("unresolved_context_slot_indexes"))
    if mapping_verified and critic_clean and not proposed_actions and cost["fits_target"] and cost["approved_seconds"] + .05 >= minimum_target:
        output.update(keep_beat_ids=current, slot_map=existing_map, semantic_mapping_verified=True,
                      evidence_policy_version=EVIDENCE_POLICY_VERSION, evidence_proof=existing_proof,
                      source_span_policy_version=SOURCE_SPAN_POLICY_VERSION, source_span_constraints=existing_spans,
                      summary=whole_utterance_story_summary(existing_spans), summary_source=SOURCE_SPAN_SUMMARY_SOURCE,
                      semantic_revision={"attempts": 0, "verdict": "fit", "released_optional_beat_ids": [],
                                         "policy_version": cost["policy_version"], "cost": cost,
                                         "reasoning": {**reasoning_policy, "request_attempted": False}},
                      unresolved_plan_slot_indexes=[], unresolved_context_slot_indexes=[])
        return _reconcile_critic_actions(output)
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode") or "auto")
    beat_chapters = {str(beat["id"]): str(chapter["id"])
                     for chapter in chapters for beat in chapter.get("beats", [])}
    known_allowed = sorted(set(valid) - rejected, key=lambda value: float(valid[value]["start"]))
    try:
        catalog = build_story_evidence_catalog(candidates, segments, allowed_beat_ids=known_allowed)
    except (ValueError, TypeError, KeyError):
        fail("invalid_source_evidence", "Source quotation ownership could not be established. Review canonical transcript boundaries before retrying.")
    allowed_ids = ([value for value in known_allowed] if (output.get("passage_option_selection") or {}).get("option", {}).get("ordered_source_group_search")
                   else [value for value in known_allowed if complete_units([value])])
    try:
        explicit_context = _explicit_source_context_ids(output, candidates, segments)
        if not explicit_context <= set(allowed_ids):
            raise ValueError("Mandatory source context is rejected or lacks a complete retrieved source unit.")
    except (ValueError, TypeError, KeyError) as exc:
        fail("required_source_missing", str(exc) + " Required context cannot be restored by changing the duration alone.")
    catalog = [row for row in catalog if row["beat_id"] in allowed_ids]
    try:
        choice_catalog = _story_evidence_choice_catalog(catalog)
    except (ValueError, TypeError, KeyError):
        fail("invalid_source_evidence", "Source quotation choices could not be resolved to unique canonical evidence.")
    feasibility = story_constraint_feasibility(candidates, segments, chapters, plan,
        selected_beat_ids=current, sticky_beat_ids=sticky, rejected_beat_ids=rejected, target=target,
        protect_action_span=bool(explicit_source_continuity_requested(brief) or ((brief.get("style_profile") or {}).get("selection_policy") or {}).get("protect_action_span")),
        eligible_beat_ids=allowed_ids)
    if feasibility["status"] == "required_source_missing":
        fail("required_source_missing", "Required story roles or critic context lack complete eligible source units. A longer target alone cannot restore missing source.")
    ending_domain = story_final_ending_domain(candidates, segments, chapters, plan,
        sticky_beat_ids=sticky, rejected_beat_ids=rejected, minimum_target_seconds=minimum_target,
        eligible_beat_ids=allowed_ids)
    endpoint_proofs = ending_domain.get("endpoint_proofs")
    try:
        verified_underfill_proof = (
            ending_domain.get("status") == "verified" and ending_domain.get("allowed_final_beat_ids") == []
            and isinstance(endpoint_proofs, list) and bool(endpoint_proofs)
            and len(endpoint_proofs) == len(allowed_ids)
            and all(type(ending_domain.get(key)) is int and ending_domain[key] == len(endpoint_proofs)
                    for key in ("eligible_unit_count", "excluded_final_beat_count"))
            and type(ending_domain.get("invalid_source_count")) is int and ending_domain["invalid_source_count"] == 0
            and ending_domain.get("bound_exceeded") is False
            and all(isinstance(row, dict) and isinstance(row.get("beat_id"), str)
                    and row.get("excluded") is True and row.get("insufficient_duration") is True
                    and type(row.get("prefix_approved_seconds")) in (int, float)
                    and math.isfinite(row["prefix_approved_seconds"]) and row["prefix_approved_seconds"] >= 0
                    for row in endpoint_proofs)
            and {row["beat_id"] for row in endpoint_proofs} == set(allowed_ids)
            and math.isfinite(minimum_target) and minimum_target > 0)
    except OverflowError:
        verified_underfill_proof = False
    if verified_underfill_proof:
        available_source_upper_bound = max(row["prefix_approved_seconds"] for row in endpoint_proofs)
        if available_source_upper_bound + .05 + 1e-9 < minimum_target:
            fail("allowed_source_below_target_minimum", "Review the current source selection or choose a shorter target.",
                 available_source_upper_bound=available_source_upper_bound)
    final_ending_ids = (set(ending_domain["allowed_final_beat_ids"])
                        if ending_domain["status"] == "verified" else set(allowed_ids))
    evidence_owners = {row["id"]: row["beat_id"] for row in catalog}
    release_ids = [value for value in current if value not in sticky and value not in rejected]
    evidence_ids_by_chapter = {
        str(chapter["id"]): [row["id"] for row in catalog if beat_chapters.get(row["beat_id"]) == str(chapter["id"])]
        for chapter in chapters
    }
    role_requirements = {slot["purpose"]: {
        "allowed_primary_chapter_ids": list(dict.fromkeys(str(value) for value in slot.get("chapter_ids", []))),
        "required_context_chapter_ids": list(dict.fromkeys(str(value) for value in slot.get("required_context_chapter_ids", []))),
        "same_evidence_may_supply_primary_and_context": True,
    } for slot in plan["slots"]}
    revision_schema = copy.deepcopy(STORY_TARGET_REVISION_SCHEMA)
    choice_definitions: dict[str, dict[str, Any]] = {}
    choice_definition_names: dict[tuple[str, ...], str] = {}

    def choice_reference(values: list[str]) -> dict[str, Any]:
        domain = tuple(values)
        if domain not in choice_definition_names:
            name = f"choice_domain_{len(choice_definitions)}"
            choice_definition_names[domain] = name
            choice_definitions[name] = {"type": "string", "enum": list(values)}
        return {"$ref": "#/$defs/" + choice_definition_names[domain]}

    def restricted_ids(values: list[str]) -> dict[str, Any]:
        return ({"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": list(values)}}
                if values else {"type": "array", "items": {"type": "string"}, "maxItems": 0})

    revision_schema["properties"]["keep_beat_ids"] = restricted_ids(allowed_ids)
    revision_schema["properties"]["released_optional_beat_ids"] = restricted_ids(release_ids)
    for purpose, requirement in role_requirements.items():
        primary_ids = [choice for choice, row in choice_catalog.items()
                       if beat_chapters.get(row["beat_id"]) in requirement["allowed_primary_chapter_ids"]]
        context_ids = [choice for choice, row in choice_catalog.items()
                       if beat_chapters.get(row["beat_id"]) in requirement["required_context_chapter_ids"]]
        primary_schema = {"type": "array", "uniqueItems": True, "items": choice_reference(primary_ids)} if primary_ids else restricted_ids([])
        context_schema = {"type": "array", "uniqueItems": True, "items": choice_reference(context_ids)} if context_ids else restricted_ids([])
        if context_ids:
            context_schema["minItems"] = len(requirement["required_context_chapter_ids"])
        witness_ids = [value for value in primary_ids if purpose != purposes[-1] or choice_catalog[value]["beat_id"] in final_ending_ids]
        revision_schema["properties"]["role_selections"]["properties"][purpose] = {
            "type": "object", "additionalProperties": False,
            "properties": {"primary_anchor_choice": choice_reference(witness_ids or [""]),
                           "additional_primary_evidence_choices": primary_schema, "context_evidence_choices": context_schema},
            "required": ["primary_anchor_choice", "additional_primary_evidence_choices", "context_evidence_choices"],
        }
    complete_roles = revision_schema["properties"]["role_selections"]
    complete_roles["required"] = list(purposes)
    revision_schema["properties"]["role_selections"] = {"anyOf": [
        complete_roles,
        {"type": "object", "additionalProperties": False, "properties": {}, "maxProperties": 0},
    ]}
    revision_schema["$defs"] = choice_definitions
    if proposed_actions:
        revision_schema["properties"]["critic_action_decisions"] = {
            "type":"array", "maxItems":len(proposed_actions), "items":{
                "type":"object", "additionalProperties":False,
                "properties":{
                    "action":{"type":"string","enum":["add","remove"]},
                    "beat_id":{"type":"string","enum":list(dict.fromkeys(row["beat_id"] for row in proposed_actions))},
                    "decision":{"type":"string","enum":["accept","decline","uncertain"]},
                    "source_evidence_ids":{"type":"array","minItems":1,"uniqueItems":True,
                        "items":{"type":"string","enum":[row["id"] for row in catalog]}},
                    "reason":{"type":"string"}},
                "required":["action","beat_id","decision","source_evidence_ids","reason"]}}
        revision_schema["required"].append("critic_action_decisions")
    semantic_brief = ({key:copy.deepcopy(value) for key,value in brief.items() if key not in {"style_profile","edit_style"}}
                      if proposal_review else brief)
    payload = {
        "model": model, "stream": False, "think": False, "format": revision_schema,
        "_performance_mode": mode, "_single_attempt": True, "_reject_duplicate_keys": True,
        "options": {"temperature": .02, "num_ctx": 16384 if mode == "quality" else 12288,
                    "num_predict": reasoning_policy["num_predict"]},
        "messages": [{"role": "system", "content": (
            "You are CUTROOM's final semantic budget editor. This is the single permitted revision. "
            "Return fit only for a coherent, complete story whose exact source cost fits the target using the supplied pause policy. "
            "For fit, assign quotations to EVERY exact purpose key in role_requirements using role_selections. "
            "Select by the meaning of the verbatim wording FIRST, then copy its entire exact choice string including the bracketed canonical reference. "
            "Choose primary_anchor_choice as the explicit PRIMARY source phrase and temporal anchor for that role. "
            "Choose it and any additional_primary_evidence_choices only from source_evidence_choices whose evidence_id belongs to that purpose's allowed_primary_chapter_ids in evidence_ids_by_chapter. "
            "The anchor plus additional primary choices must contain a substantive complete proposition, request or conclusion supporting the role. "
            "Acknowledgments, fillers and unfinished phrases cannot establish a role alone. Background context cannot replace primary support. "
            "Read each complete ASR utterance in source_units.segments and preserve every negation or qualification needed for its meaning in primary plus context choices. "
            "Every selected quotation requires its ENTIRE canonical ASR utterance as mandatory context, including negations and qualifications; source fragments never authorize trimming that utterance. "
            "For EACH chapter in required_context_chapter_ids, choose at least one context_evidence_choice whose evidence_id belongs to that chapter in evidence_ids_by_chapter. "
            "Required context needs explicit quotation choices even when primary and context use the SAME chapter. "
            "The SAME supplied choice may be primary and context when allowed for both; do not repeat the anchor in additional_primary_evidence_choices. "
            "this does not duplicate footage. Use context_evidence_choices=[] ONLY when the required-context table is empty. "
            "The supplied source_units and source_evidence are authoritative. Select the actual source phrases that support each role; "
            "do not invent events, motives, attacks, relocation, participation or other outcomes. A conclusion may be an explicit refusal, decision or qualified claim. "
            "Each exact source_evidence_choices string identifies one canonical quotation and its complete source beat; the server resolves that exact key. "
            "Return complete supplied choice strings for each role, with no bare IDs, rewritten quotations, beat assignments, English proof claims or timestamps. "
            "The server uses primary_anchor_choice as that role's primary temporal witness. Anchors must follow the configured story-role order in source playback; "
            "overlapping evidence within one source unit may support several roles, but a later role cannot point definitely backward. "
            "The final role must cite primary evidence from the final selected passage. Narrow unsupported interpretations to what the source actually says. "
            "Its temporal witness must belong to allowed_final_beat_ids, the endings that remain possible under optimistic numeric prefix constraints. "
            "For target duration mode, complete approved passages must also reach minimum_target_seconds without padding; style mode has no lower quota. "
            "Keep complete supplied source beats; never invent IDs, timestamps, clipped sentences or speech removal. "
            + ("Critic requests are ADVISORY PROPOSALS, not accepted exclusions or required additions. "
               "The full original candidate source is available. Independently assess each proposed action against original source wording and the verbatim user instruction. "
                "Check alleged omissions against selected_in_proposal and exact canonical segment_ids; a retained explanation is not omitted. "
                "Presence does not prove adequate context: distinguish a retained statement from a genuinely absent prerequisite. Critic interpretations remain unverified. "
               "For EACH proposal return exactly one critic_action_decisions row with action,beat_id,decision,source_evidence_ids,reason. "
               "Use exact original evidence IDs, including one belonging to its target; explain why the action improves or harms actual meaning/context or obeys an explicit user requirement. "
               "Do not adopt translations, metaphors interpreted as literal events, unsupported critic summaries or style preferences as facts. "
               "A deletion which causes missing context is not a repair of that defect. Style hooks, clear promises and pacing are advisory unless the original user explicitly requires them. "
               "accept removal means the ID is absent; decline removal retains it if originally selected. accept addition means the ID is kept; decline addition cannot introduce an originally unselected ID. "
               "Missing critic evidence does not authorize a deletion: judge original source independently and provide your own exact evidence and reason. "
               "Any unresolved proposal or semantic uncertainty requires no_fit, not a forced edit. Do not restore or include material just to meet duration. "
               "For no_fit use critic_action_decisions=[]; for fit fully adjudicate every supplied proposal. "
               if proposed_actions else "")
            +
            "Retain all sticky_critic_context_beat_ids and never restore rejected_beat_ids. "
            "Retain every mandatory_context_beat_id; these exact source prerequisites cannot be released or replaced by a paraphrase. "
            "keep_beat_ids must equal the role-mapped IDs plus sticky critic context. "
            "Every retained beat must contribute at least one exact source_evidence_choices quotation in role_selections unless it is accepted sticky critic context. "
            "A citation in critic_action_decisions alone does not assign that beat to a story role. "
            "Do not infer role assignments from a decision reason or rationale. "
            "When the only role is self_contained_passage, put a substantive quotation from the latest retained beat in primary_anchor_choice, "
            "and exact supporting quotations from every other retained beat in additional_primary_evidence_choices. "
            "Do not invent required context: keep context_evidence_choices=[] when required_context_chapter_ids is empty. "
            "released_optional_beat_ids must equal current_selected_beat_ids MINUS keep_beat_ids, exactly. "
            "If every current selected ID is kept, released_optional_beat_ids MUST be []. "
            "NEVER list critic_already_removed_beat_ids as optional releases: the critic already removed them before this request. "
            "Sticky context cannot be released. "
            "Use the provided numeric cost reports instead of recalculating source timings. "
            "If no coherent fit can be verified, return no_fit with empty keep_beat_ids, released_optional_beat_ids and role_selections={}. "
            "Return only the requested JSON schema."
        )}, {"role": "user", "content": json.dumps({
            "brief": semantic_brief, "required_story_roles": _configured_story_roles(brief),
            **({"critic_proposals":{
                "authority":"advisory_only","actions":proposed_actions,
                "action_semantics_verified":False,
                "original_selected_beat_ids":list(critic.get("selection_before") or current),
                "suggested_beat_ids":list(critic.get("proposed_beat_ids") or []),
                "issues":copy.deepcopy(critic.get("issues") or []),"summary":critic.get("summary"),
                "issue_evidence":copy.deepcopy(critic.get("issue_evidence") or []),
                "action_evidence":copy.deepcopy(critic.get("raw_action_evidence") or []),
                "attribution_error":critic.get("action_evidence_error"),
                "style_notes":copy.deepcopy(critic.get("style_notes") or [])},
                "explicit_user_constraints":{"verbatim_instruction":str(brief.get("instruction") or ""),
                    "required_roles":_configured_story_roles(brief),"required_orders":required_story_role_orders(brief),
                    "source_continuity_required":explicit_source_continuity_requested(brief),
                    "mandatory_context_beat_ids":sorted(explicit_context),"recognition_is_partial":True},
                "style_preferences":{"authority":"advisory_only","profile":copy.deepcopy(brief.get("style_profile") or {})}}
               if proposal_review else {}),
            "evidence_policy_version": EVIDENCE_POLICY_VERSION,
            "source_span_policy_version": SOURCE_SPAN_POLICY_VERSION,
            "mandatory_source_context": "Every selected beat retains every complete canonical ASR utterance; only verified internal speech-free gaps may be shortened.",
            "evidence_verification_scope": "source_attribution_and_order",
            "current_selected_beat_ids": list(current), "critic_already_removed_beat_ids": sorted(rejected - set(current)),
            "allowed_optional_release_beat_ids": release_ids,
            "release_rule": "released_optional_beat_ids = current_selected_beat_ids minus keep_beat_ids; already critic-removed IDs are excluded.",
            "role_requirements": role_requirements,
            "evidence_ids_by_chapter": evidence_ids_by_chapter,
            "allowed_final_beat_ids": [value for value in allowed_ids if value in final_ending_ids],
            "current_cost": cost, "target_seconds": target, "minimum_target_seconds": round(minimum_target, 3),
            "constraint_feasibility": feasibility,
            "sticky_critic_context_beat_ids": sorted(sticky),
            "mandatory_context_beat_ids": sorted(explicit_context),
            "rejected_beat_ids": sorted(rejected),
            "incomplete_source_beat_ids": [value for value in known_allowed if value not in allowed_ids],
            "candidates": [{"id": value, "chapter_id": beat_chapters.get(value),
                "start": valid[value]["start"], "end": valid[value]["end"], "segment_ids": valid[value].get("segment_ids", []),
                "duration_cost": _story_selection_cost([value], candidates, segments, brief)}
                for value in allowed_ids],
            "source_evidence": catalog,
            "source_evidence_choices": [{"choice": choice, "evidence_id": row["id"]}
                                        for choice, row in choice_catalog.items()],
            # Fixed context: the context fitter may shorten candidate excerpts,
            # but it must preserve the complete source evidence behind a role.
            "source_units": [{"id": value, "start": row["start"], "end": row["end"],
                              "selected_in_proposal": value in current,
                              "segment_ids": row.get("segment_ids", []),
                              **candidate_projection_fields(row),
                              "segments": [{"id": str(identifier), "start": segment_by_id[str(identifier)]["start"],
                                            "end": segment_by_id[str(identifier)]["end"],
                                            "text": str(segment_by_id[str(identifier)].get("text") or "")}
                                           for identifier in row.get("segment_ids", []) if str(identifier) in segment_by_id]}
                             for value, row in valid.items() if value in allowed_ids],
            "neighboring_source_utterances": neighboring_source_utterances(candidates, segments),
        }, ensure_ascii=False)}],
    }
    cancellation_error: list[BaseException] = []

    def checked_cancel() -> None:
        try:
            _check_cancelled(cancel_check)
        except BaseException as exc:
            cancellation_error.append(exc)
            raise

    fixed_review = None
    if output.get("passage_option_selection") is not None:
        payload, fixed_option, fixed_proposal = _fixed_passage_final_request(
            payload, output, candidates, segments, chapters, plan, brief, proposed_actions, cancel_check)
        fixed_review = (fixed_option, fixed_proposal)
    try:
        revision_attempted = True
        result = _call_ollama_story_pass(settings, payload, 240, checked_cancel if cancel_check else None)
    except Exception as exc:
        from .jobs import JobCancelled
        if cancellation_error or isinstance(exc, JobCancelled):
            raise
        if isinstance(exc, StoryResponseLimitError):
            fail("semantic_revision_output_limit", "The model used its bounded response budget before producing complete JSON. Story approval remains unfinished; the numeric source-cost report is unchanged.")
        if isinstance(exc, StoryPlanningError) and "context budget" in str(exc):
            fail("semantic_revision_context_limit", "Complete source evidence exceeds the supported local context budget. Reduce the source scope before retrying.")
        if isinstance(exc, StoryPlanningError):
            fail("semantic_revision_failed", "The single semantic review returned invalid model output; no story approval was established.",
                 outcome="invalid_model_output")
        fail("semantic_revision_failed", "The single semantic review could not complete because of a technical error; retry after checking the AI connection.",
             outcome="technical_error")
    _check_cancelled(cancel_check)
    if fixed_review is not None:
        output["passage_option_final_review"] = copy.deepcopy(result)
        review_data=json.loads(payload["messages"][1]["content"])
        review_scope=(review_data.get("selected_source_utterances",[])+review_data.get("reference_source_utterances",[])) if _evidence_bound_passage(fixed_review[0]) else None
        if review_scope is not None:
            shown_ids={r["id"] for r in review_scope};review_scope=[r for r in segments if r["id"] in shown_ids]
        result = _decode_fixed_passage_final(result, fixed_review[0], fixed_review[1], proposed_actions, segments,review_segments=review_scope)
    expected_fields = {"verdict", "keep_beat_ids", "released_optional_beat_ids", "role_selections"}
    if proposed_actions:
        expected_fields.add("critic_action_decisions")
    if (not isinstance(result, dict) or result.get("verdict") not in {"fit", "no_fit"}
            or set(result) != expected_fields
            or not isinstance(result.get("role_selections"), dict)):
        fail("invalid_semantic_revision", "The single semantic review did not return a valid verdict.")
    if result["verdict"] == "no_fit":
        if (result["keep_beat_ids"] != [] or result["released_optional_beat_ids"] != [] or result["role_selections"] != {}
                or (proposed_actions and result["critic_action_decisions"] != [])):
            fail("invalid_semantic_revision", "A no-fit response must use the current empty quotation-assignment envelope.")
        if feasibility["status"] == "target_infeasible":
            fail("target_infeasible", "This lower bound applies only to the allowed complete source constraints, not every possible story in the recording.")
        if feasibility["status"] == "required_source_missing":
            fail("required_source_missing", "Required story roles or critic context lack complete eligible source units. A longer target alone cannot restore missing source.")
        fail("planner_no_fit", "The single review did not verify coherent source-grounded roles and order. "
             "Duration feasibility is not semantic verification; a longer target alone does not establish a story.")
    adjudications = []
    accepted_additions, accepted_removals = set(), set()
    try:
        for key in ("keep_beat_ids", "released_optional_beat_ids"):
            values = result.get(key)
            if (not isinstance(values, list) or any(not isinstance(value, str) or value not in valid for value in values)
                    or len(values) != len(set(values))):
                raise ValueError("The revised selection contains invalid or duplicate source identifiers.")
        keep, released = result["keep_beat_ids"], result["released_optional_beat_ids"]
        if proposed_actions:
            expected_actions = {(row["action"],row["beat_id"]) for row in proposed_actions}
            decisions = result["critic_action_decisions"]
            if not isinstance(decisions,list) or len(decisions) != len(expected_actions):
                raise ValueError("Every critic proposal needs exactly one final source-grounded decision.")
            by_evidence_id = {row["id"]:row for row in catalog}
            seen = set()
            original_selected = set(critic.get("selection_before") or current)
            for row in decisions:
                if (not isinstance(row,dict) or set(row) != {"action","beat_id","decision","source_evidence_ids","reason"}
                        or not isinstance(row.get("action"),str) or not isinstance(row.get("beat_id"),str)):
                    raise ValueError("Final critic adjudication has invalid fields.")
                key = (row["action"],row["beat_id"])
                refs = row["source_evidence_ids"]
                if (key not in expected_actions or key in seen or row["decision"] not in {"accept","decline","uncertain"}
                        or not isinstance(refs,list) or not refs or any(not isinstance(v,str) or v not in by_evidence_id for v in refs)
                        or len(refs)!=len(set(refs)) or not any(by_evidence_id[v]["beat_id"]==row["beat_id"] for v in refs)
                        or not isinstance(row["reason"],str) or not row["reason"].strip()):
                    raise ValueError("Final critic decision lacks unique exact target source evidence.")
                if row["decision"] == "uncertain":
                    fail("critic_proposal_uncertain","The final review did not resolve a critic proposal; no edit can be approved.",outcome="editorial_no_fit")
                accept = row["decision"] == "accept"
                target_kept = row["beat_id"] in keep
                if row["action"] == "remove":
                    if (accept and target_kept) or (not accept and row["beat_id"] in original_selected and not target_kept):
                        raise ValueError("Final removal decision contradicts the selected source.")
                    if accept:accepted_removals.add(row["beat_id"])
                else:
                    if (accept and not target_kept) or (not accept and row["beat_id"] not in original_selected and target_kept):
                        raise ValueError("Final addition decision contradicts the selected source.")
                    if accept:accepted_additions.add(row["beat_id"])
                adjudications.append({**copy.deepcopy(row),"source_evidence":[copy.deepcopy(by_evidence_id[v]) for v in refs]})
                seen.add(key)
            rejected = accepted_removals
            sticky = accepted_additions - rejected
        if not keep or rejected.intersection(keep) or not sticky <= set(keep):
            raise ValueError("The revision dropped required critic context or restored rejected material.")
        if not explicit_context <= set(keep):
            raise ValueError("The revision dropped mandatory source prerequisite context.")
        if set(released) != set(current) - set(keep) or sticky.intersection(released):
            raise ValueError("Optional source releases must be explicit and exact.")
        slot_rows = _story_revision_slot_rows(result["role_selections"], catalog, plan)
        slot_map = _validated_story_slot_map(slot_rows, keep, candidates, chapters, plan,
                                              sticky_context=sticky)
        if not complete_units(keep):
            raise ValueError("The revised story must retain complete source passages and sentence boundaries.")
        _validate_single_source_passage(keep, chapters, brief)
        evidence_proof = _story_evidence_proof(slot_map, keep, candidates, segments, plan, brief, rejected)
        slot_map = evidence_proof["slot_map"]
        source_spans = build_source_span_constraints(candidates, segments, selected_beat_ids=keep,
                                                    rejected_beat_ids=sorted(rejected))
    except (ValueError, TypeError, KeyError) as exc:
        fail("invalid_semantic_mapping", str(exc) + " Review the story roles; a longer target alone does not verify them.")
    revised_cost = _story_selection_cost(keep, candidates, segments, brief)
    if not revised_cost["fits_target"]:
        fail("required_selection_exceeds_target", "The single proposed revision still exceeds the target; no draft was applied.", revised_cost)
    if revised_cost["approved_seconds"] + .05 < minimum_target:
        fail("target_underfill", f"The proposed complete source passages cover only {revised_cost['approved_seconds']:.2f} seconds "
             f"and do not reach the {minimum_target:.2f}-second target band. No padding or unreviewed source was added.")
    if evidence_owners.get(slot_map[-1]["temporal_witness_id"]) not in final_ending_ids:
        fail("invalid_semantic_mapping", "The final witness cannot end the story while retaining the required source groups and duration band.")
    keep = sorted(keep, key=lambda value: float(valid[value]["start"]))
    output.update(keep_beat_ids=keep, slot_map=slot_map, semantic_mapping_verified=True,
                  semantic_review_status="model_reviewed",
                  evidence_policy_version=EVIDENCE_POLICY_VERSION, evidence_proof=evidence_proof,
                  source_span_policy_version=SOURCE_SPAN_POLICY_VERSION, source_span_constraints=source_spans,
                  summary=whole_utterance_story_summary(source_spans), summary_source=SOURCE_SPAN_SUMMARY_SOURCE,
                  opening_beat_id=keep[0], closing_beat_id=keep[-1],
                  highlight_beat_ids=[value for value in output.get("highlight_beat_ids", []) if value in keep],
                  recovered_slot_indexes=[], unresolved_plan_slot_indexes=[], unresolved_context_slot_indexes=[],
                  semantic_revision={"attempts": 1, "verdict": "fit", "released_optional_beat_ids": list(released),
                                     "policy_version": revised_cost["policy_version"], "cost": revised_cost,
                                     "final_ending_domain": copy.deepcopy(ending_domain),
                                     "reasoning": {**reasoning_policy, "request_attempted": True}})
    output["critic"] = {**critic, "original_review": copy.deepcopy(critic), "verdict": "pass", "issues": [],
                        "post_review_beat_ids": list(keep), "semantic_revision_verified": True,
                        "summary": "The single model review assigned the story roles; canonical source attribution, role order, required context and budget were validated."}
    if proposal_review:
        output["critic"].update(action_authority="final",accepted_added=sorted(accepted_additions),
            accepted_removed=sorted(accepted_removals),action_decisions=adjudications,
            declined_proposals=[row for row in adjudications if row["decision"]=="decline"])
    return _reconcile_critic_actions(output)


def _fit_story_selection_to_budget(
    selection: dict[str, Any],
    candidates: list[dict[str, Any]],
    plan: dict[str, Any],
    target_duration: float,
    chapters: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Keep a model-authored story selection close to its real time budget.

    The precision model selects whole story beats for narrative slots. A valid
    response can still select every beat in those slots, though, even when their
    combined wall-clock duration is much longer than the requested Short. Passing
    that oversized selection to Director forced the final duration enforcer to cut
    individual transcript lines out of otherwise coherent beats.

    Fit at the same semantic level at which the choice was made: preserve one
    substantive representative beat per planned slot, then add model endpoints and
    highlighted material only while modest cleanup headroom remains. Director can
    still remove measured dead air afterwards.
    """
    valid = {str(item.get("id")): item for item in candidates if item.get("id") is not None}
    accepted_additions, rejected = _critic_action_sets(selection.get("critic") or {})
    critic_required = {
        str(identifier) for identifier in accepted_additions
        if str(identifier) in valid and str(identifier) not in rejected
    }
    selected = [
        str(identifier) for identifier in selection.get("keep_beat_ids", [])
        if str(identifier) in valid and str(identifier) not in rejected
    ]
    selected.extend(critic_required)
    selected = sorted(dict.fromkeys(selected), key=lambda identifier: float(valid[identifier].get("start", 0.0)))
    selection = {**selection, "keep_beat_ids": selected}
    if selected:
        selection.update(opening_beat_id=selected[0], closing_beat_id=selected[-1])
    elif rejected:
        raise _InvalidStorySelectionError("Story critic left no selected source material.")
    target = max(8.0, float(target_duration))
    headroom = 1.12 if target <= 90.0 else 1.08 if target <= 210.0 else 1.05
    ceiling = target * headroom
    slot_rows = selection.get("slot_map", []) if isinstance(selection.get("slot_map"), list) else []
    slot_rows = [item for item in slot_rows if isinstance(item, dict)]
    plan_slots = plan.get("slots", []) if isinstance(plan.get("slots"), list) else []
    beat_to_chapter = {
        str(beat.get("id")): str(chapter.get("id"))
        for chapter in (chapters or [])
        for beat in (chapter.get("beats", []) if isinstance(chapter, dict) else [])
        if isinstance(beat, dict) and beat.get("id") is not None
    }

    def missing_plan_slots(identifiers: list[str] | set[str]) -> list[int]:
        represented = {beat_to_chapter[identifier] for identifier in identifiers if identifier in beat_to_chapter}
        return [index for index, slot in enumerate(plan_slots)
                if (not {str(value) for value in slot.get("required_context_chapter_ids", [])} <= represented
                    or (slot.get("chapter_ids") and not represented.intersection(str(value) for value in slot["chapter_ids"])))]

    if not selected and not slot_rows:
        return _reconcile_critic_actions(selection)

    def selection_duration(identifiers: list[str] | set[str]) -> float:
        ranges = [
            {"start": float(valid[identifier].get("start", 0.0)), "end": float(valid[identifier].get("end", 0.0))}
            for identifier in identifiers
            if identifier in valid
        ]
        # Director joins beat ranges separated by a sub-second breath, so count
        # that bridge here as well instead of understating the eventual draft.
        return range_duration(merge_ranges(ranges, gap=0.75))

    before = selection_duration(selected)
    every_slot_represented = all(
        any(str(identifier) in selected for identifier in row.get("beat_ids", []))
        for row in slot_rows
    )
    if before <= target + 0.05 and every_slot_represented and not missing_plan_slots(selected):
        return _reconcile_critic_actions({**selection, "unresolved_plan_slot_indexes": []})

    highlights = {
        str(identifier) for identifier in selection.get("highlight_beat_ids", [])
        if str(identifier) in valid
    }
    opening = str(selection.get("opening_beat_id") or "")
    closing = str(selection.get("closing_beat_id") or "")
    role_groups = {
        "hook": {"hook"},
        "setup": {"hook", "context"},
        "context": {"hook", "context"},
        "proof": {"example", "result"},
        "example": {"example", "result"},
        "payoff": {"result", "conclusion"},
        "ending": {"result", "conclusion"},
        "conclusion": {"result", "conclusion"},
    }

    # A continuity addition is required context, not an optional highlight. Keep
    # its complete source passage even when the combination is infeasible; the
    # duration stage must expose that limit instead of calling a dropped repair
    # complete or slicing spoken context to make the number fit.
    fitted: set[str] = set(critic_required)
    fitted_slot_map: list[dict[str, Any]] = []
    slot_alternatives: list[tuple[dict[str, Any], list[str]]] = []
    for row in sorted(
        (item for item in slot_rows if isinstance(item, dict)),
        key=lambda item: int(item.get("slot_index", 0)),
    ):
        try:
            slot_index = int(row.get("slot_index"))
        except (TypeError, ValueError):
            continue
        slot = plan_slots[slot_index] if 0 <= slot_index < len(plan_slots) else {}
        model_choices = [
            str(identifier) for identifier in row.get("beat_ids", [])
            if str(identifier) in valid and str(identifier) not in rejected
        ]
        primary_chapters = {str(value) for value in slot.get("chapter_ids", [])}
        primary_choices = [
            identifier for identifier in model_choices
            if primary_chapters and beat_to_chapter.get(identifier) in primary_chapters
        ]
        allowed_chapters = primary_chapters | {str(value) for value in slot.get("required_context_chapter_ids", [])}
        replacements = [str(identifier) for identifier in accepted_additions
                        if str(identifier) in selected and str(identifier) not in rejected
                        and beat_to_chapter.get(str(identifier)) in allowed_chapters]
        choices = primary_choices or model_choices or replacements
        if not choices:
            fitted_slot_map.append({"slot_index": slot_index, "purpose": row.get("purpose"), "beat_ids": []})
            slot_alternatives.append(({"slot_index": slot_index, "purpose": row.get("purpose")}, []))
            continue
        purpose = str(slot.get("purpose") or row.get("purpose") or "").lower()
        expected_roles = next((roles for cue, roles in role_groups.items() if cue in purpose), set())
        desired = max(2.0, float(slot.get("desired_seconds") or target / max(1, len(slot_rows))))

        def slot_value(identifier: str) -> tuple[float, float, float]:
            beat = valid[identifier]
            beat_duration = max(0.0, float(beat.get("end", 0.0)) - float(beat.get("start", 0.0)))
            duration_ratio = beat_duration / max(desired, 1.0)
            duration_fit = min(1.0, duration_ratio) - max(0.0, duration_ratio - 1.0) * 0.22
            expected_words = max(4.0, desired * 1.4)
            substance = min(1.0, len(tokens(str(beat.get("text") or ""))) / expected_words)
            highlight_bonus = 0.06 if identifier in highlights else 0.0
            endpoint_bonus = 0.0
            if identifier == closing and any(cue in purpose for cue in ("payoff", "ending", "conclusion")):
                endpoint_bonus = 0.18
            elif identifier == opening and any(cue in purpose for cue in ("hook", "setup")):
                endpoint_bonus = 0.03
            role_bonus = 0.25 if str(beat.get("role_hint") or "") in expected_roles else 0.0
            quality = float(beat.get("editorial_score", 0.0)) + float(beat.get("novelty", 0.0)) * 0.12
            score = duration_fit * 1.20 + substance * 0.25 + quality * 0.48 + role_bonus + highlight_bonus + endpoint_bonus
            return score, substance, -abs(beat_duration - desired)

        representative = max(choices, key=slot_value)
        slot_alternatives.append((
            {"slot_index": slot_index, "purpose": row.get("purpose")},
            sorted(choices, key=slot_value, reverse=True)[:32],
        ))
        fitted.add(representative)
        fitted_slot_map.append({
            "slot_index": slot_index,
            "purpose": row.get("purpose"),
            "beat_ids": [representative],
        })

    # Selections produced by older extensions may not carry slot_map. Keep their
    # semantic endpoints as a compatibility fallback; normal Story AI selections
    # always choose mandatory slot representatives above.
    if not fitted:
        if selected:
            fitted.add(selected[0])
            fitted.add(selected[-1])

    plan_alternatives: list[list[str]] = []
    required_chapters = {str(value) for slot in plan_slots for value in slot.get("required_context_chapter_ids", [])}
    chapter_obligations = [{chapter_id} for chapter_id in sorted(required_chapters)]
    chapter_obligations.extend({str(value) for value in slot["chapter_ids"]}
                               for slot in plan_slots if slot.get("chapter_ids"))
    for allowed_chapters in chapter_obligations:
        choices = [identifier for identifier in selected if beat_to_chapter.get(identifier) in allowed_chapters]
        plan_alternatives.append(choices)
        if choices and not any(identifier in fitted for identifier in choices):
            fitted.add(max(choices, key=lambda identifier: (
                float(valid[identifier].get("editorial_score", 0.0)),
                float(valid[identifier].get("novelty", 0.0)),
                -float(valid[identifier].get("start", 0.0)),
            )))

    critic_added = {
        str(identifier) for identifier in (selection.get("critic") or {}).get("added", [])
        if str(identifier) in valid
    }

    def extra_value(identifier: str) -> tuple[float, float, float]:
        beat = valid[identifier]
        quality = float(beat.get("editorial_score", 0.0)) + float(beat.get("novelty", 0.0)) * 0.12
        bonus = (
            (0.25 if identifier in highlights else 0.0)
            + (0.40 if identifier in critic_added else 0.0)
            + (0.20 if identifier == closing else 0.0)
            + (0.08 if identifier == opening else 0.0)
        )
        beat_duration = max(0.0, float(beat.get("end", 0.0)) - float(beat.get("start", 0.0)))
        return bonus + quality, -beat_duration, -float(beat.get("start", 0.0))

    for identifier in sorted((item for item in selected if item not in fitted and item not in rejected), key=extra_value, reverse=True):
        proposed = set(fitted)
        proposed.add(identifier)
        if selection_duration(proposed) <= ceiling + 0.05:
            fitted = proposed

    # Greedy representatives can strand most of the budget: a 3s setup plus a
    # 3s ending prevents adding a 17s approved alternative, although replacing
    # the setup yields a complete 20s selection. Search a bounded set of the
    # same slot-approved alternatives before accepting that shortfall.
    search_groups = slot_alternatives + [(None, choices) for choices in plan_alternatives]
    if ((selection_duration(fitted) < target * 0.90 or before > target + 0.05)
            and search_groups and all(choices for _row, choices in search_groups)):
        def budget_value(identifiers: set[str]) -> tuple[float, float, int]:
            duration = selection_duration(identifiers)
            return min(duration, target), -max(0.0, duration - target), -len(identifiers)

        states: list[tuple[set[str], list[dict[str, Any]]]] = [(set(critic_required), [])]
        for slot_row, choices in search_groups:
            expanded: dict[tuple[str, ...], tuple[set[str], list[dict[str, Any]]]] = {}
            for identifiers, rows in states:
                for identifier in choices:
                    proposed = identifiers | {identifier}
                    if selection_duration(proposed) <= target + 0.05:
                        key = tuple(sorted(proposed))
                        expanded.setdefault(key, (proposed, rows + (
                            [{**slot_row, "beat_ids": [identifier]}] if slot_row is not None else []
                        )))
            states = sorted(expanded.values(), key=lambda state: budget_value(state[0]), reverse=True)[:512]
            if not states:
                break
        for identifiers, rows in states:
            for identifier in sorted((item for item in selected if item not in identifiers), key=extra_value, reverse=True):
                proposed = identifiers | {identifier}
                if selection_duration(proposed) <= target + 0.05:
                    identifiers = proposed
            if (selection_duration(fitted) > target + 0.05
                    or budget_value(identifiers) > budget_value(fitted)):
                fitted, fitted_slot_map = identifiers, rows

    fitted_ids = sorted(fitted, key=lambda identifier: float(valid[identifier].get("start", 0.0)))
    if not fitted_ids:
        return _reconcile_critic_actions(selection)
    after = selection_duration(fitted_ids)
    output = dict(selection)
    output["keep_beat_ids"] = fitted_ids
    output["highlight_beat_ids"] = [identifier for identifier in selection.get("highlight_beat_ids", []) if str(identifier) in fitted]
    output["opening_beat_id"] = fitted_ids[0]
    output["closing_beat_id"] = fitted_ids[-1]
    if fitted_slot_map:
        output["slot_map"] = fitted_slot_map
    output["unresolved_plan_slot_indexes"] = missing_plan_slots(fitted)
    output["budget_fit"] = {
        "target_duration": round(target, 3),
        "ceiling": round(ceiling, 3),
        "before_duration": round(before, 3),
        "after_duration": round(after, 3),
        "removed_beat_ids": [identifier for identifier in selected if identifier not in fitted],
        "status": ("required_material_exceeds_ceiling" if after > ceiling + 0.05
                   else "required_material_exceeds_target" if after > target + 0.05 else "within_planning_ceiling"),
        "over_ceiling_seconds": round(max(0.0, after - ceiling), 3),
        "over_target_seconds": round(max(0.0, after - target), 3),
    }
    return _reconcile_critic_actions(output)


def _retrieve_story_candidates(
    settings, candidates, chapters, summaries, outline, plan, brief, model, mode, make_precision, cancel_check,
):
    """Budget retrieval indexes, then admit only complete canonical candidates.

    Every candidate index page is visited. Model nominations are provisional:
    the unchanged precision/source-span/critic contracts see complete utterances
    afterwards. Empty pages are allowed; no chapter is forced into the edit.
    """
    from .story_context import build_whole_recording_index, bounded_source_pages

    if len(candidates) == 1:
        raise StoryPlanningError("An indivisible canonical source candidate exceeds the context budget; no source was truncated.",
                                 {"outcome": "technical_error", "reason": "story_input_context_limit", "applied_to_timeline": False})
    index = build_whole_recording_index(chapters, summaries, summary_char_limit=80,
                                       key_point_char_limit=64, max_key_points=1)
    owners = {row["id"]: row["chapter_id"] for row in index["source_beat_index"]}
    canonical = {str(row["id"]): row for row in candidates}
    remaining = list(candidates)
    receipt = {"version": 1, "whole_recording_chapter_ids": [row["id"] for row in index["chapters"]],
               "initial_candidate_ids": list(canonical), "rounds": [],
               "authority": "provisional_index_retrieval_requires_complete_source_validation"}

    for round_index in range(4):
        _check_cancelled(cancel_check)
        maximum = max(1, 12 // (2 ** round_index))
        units = [{"id": str(row["id"]), "chapter_id": owners[str(row["id"])],
                  "start": row["start"], "end": row["end"], "segment_ids": list(row["segment_ids"]),
                  "excerpt": _balanced_excerpt(str(row.get("text") or ""), 120),
                  "excerpt_status": "abbreviated_retrieval_hint_not_canonical_quotation"} for row in remaining]

        def make_payload(page, required_domain=None):
            ids = [row["id"] for row in page]
            return {
                "model": model, "stream": False, "_single_attempt": True, "_reject_duplicate_keys": True,
                "_performance_mode": mode,
                "options": {"temperature": 0.02, "num_ctx": 8192, "num_predict": 900},
                "format": {"type": "object", "additionalProperties": False,
                           "required": ["candidate_beat_ids"], "properties": {"candidate_beat_ids": {
                               "type": "array", "uniqueItems": True, "maxItems": maximum,
                               "items": {"type": "string", "enum": ids}}}},
                "messages": [{"role": "system", "content":
                    "You are CUTROOM's retrieval planner, not its final editor. Read the whole-recording index and exact plan. "
                    "Nominate the most promising complete source beat IDs from THIS candidate page for later full canonical retrieval. "
                    "Return candidate_beat_ids only; empty is allowed for an irrelevant page. Do not force every chapter into the cut. "
                    "The excerpts and summaries are abbreviated UNVERIFIED hints. They cannot establish facts, roles or a final no-fit. "
                    "Retain candidates for every planned purpose and prerequisite when supported, preserving source chronology. "
                    "Final precision review independently checks full original utterances, exact evidence IDs and timestamps. "
                    f"Choose at most {maximum} complementary candidates; prefer sufficient setup and complete endings, never unrelated filler."},
                    {"role": "user", "content": json.dumps({"brief": brief, "outline": outline, "plan": plan,
                        "source_index": index, "candidate_page": page, "max_candidates": maximum,
                        "required_retrieval_domain": required_domain,
                        "interpretation_status": "unverified_retrieval_hints"}, ensure_ascii=False)}],
            }

        pages = bounded_source_pages(units, make_payload, lambda value: _story_payload_fits_cap(value, mode))
        chosen = set()
        page_receipts = []
        for page in pages:
            _check_cancelled(cancel_check)
            result = _call_ollama_story_pass(settings, make_payload(page), 180, cancel_check)
            ids = result.get("candidate_beat_ids") if isinstance(result, dict) else None
            allowed = {row["id"] for row in page}
            if (not isinstance(result, dict) or set(result) != {"candidate_beat_ids"}
                    or not isinstance(ids, list) or len(ids) > maximum
                    or any(not isinstance(value, str) or value not in allowed for value in ids)
                    or len(ids) != len(set(ids))):
                raise StoryPlanningError("Story retrieval returned invalid or foreign source identifiers. No draft was applied.",
                    {"outcome": "invalid_model_output", "reason": "invalid_story_retrieval", "applied_to_timeline": False})
            chosen.update(ids)
            page_receipts.append({"candidate_ids": [row["id"] for row in page], "nominated_ids": list(ids)})
        nominated_chapters = {owners[identifier] for identifier in chosen}
        missing = []
        for slot in plan["slots"]:
            primary = [str(value) for value in slot.get("chapter_ids", [])]
            if not nominated_chapters.intersection(primary):
                missing.append({"purpose": slot["purpose"], "kind": "primary", "chapter_ids": primary})
            for chapter_id in slot.get("required_context_chapter_ids", []):
                if str(chapter_id) not in nominated_chapters:
                    missing.append({"purpose": slot["purpose"], "kind": "required_context", "chapter_ids": [str(chapter_id)]})
        domain_receipts = []
        for domain in missing:
            _check_cancelled(cancel_check)
            domain_units = [{"id": str(row["id"]), "chapter_id": owners[str(row["id"])],
                             "start": row["start"], "end": row["end"], "segment_ids": list(row["segment_ids"]),
                             "excerpt": _balanced_excerpt(str(row.get("text") or ""), 120),
                             "excerpt_status": "abbreviated_retrieval_hint_not_canonical_quotation"}
                            for row in candidates if owners[str(row["id"])] in domain["chapter_ids"]]
            make_domain = lambda page: make_payload(page, domain)
            domain_pages = bounded_source_pages(domain_units, make_domain, lambda value: _story_payload_fits_cap(value, mode))
            for page in domain_pages:
                _check_cancelled(cancel_check)
                result = _call_ollama_story_pass(settings, make_domain(page), 180, cancel_check)
                ids = result.get("candidate_beat_ids") if isinstance(result, dict) else None
                allowed = {row["id"] for row in page}
                if (not isinstance(result, dict) or set(result) != {"candidate_beat_ids"}
                        or not isinstance(ids, list) or len(ids) > maximum
                        or any(not isinstance(value, str) or value not in allowed for value in ids)
                        or len(ids) != len(set(ids))):
                    raise StoryPlanningError("Required-context retrieval returned invalid source identifiers.",
                        {"outcome": "invalid_model_output", "reason": "invalid_story_retrieval", "applied_to_timeline": False})
                chosen.update(ids)
                domain_receipts.append({"domain": domain, "candidate_ids": [row["id"] for row in page], "nominated_ids": list(ids)})
        selected = [row for row in candidates if str(row["id"]) in chosen]
        receipt["rounds"].append({"maximum_per_page": maximum, "pages": page_receipts,
                                  "required_domain_pages": domain_receipts,
                                  "chosen_ids": [row["id"] for row in selected]})
        if not selected:
            raise StoryPlanningError("Story retrieval nominated no complete source candidates; no edit was applied.",
                {"outcome": "technical_error", "reason": "story_retrieval_empty", "applied_to_timeline": False})
        payload, _ = make_precision(selected)
        if _story_payload_fits_cap(payload, mode):
            retrieved_chapters = {owners[str(row["id"])] for row in selected}
            missing_domains = any(
                not retrieved_chapters.intersection(str(value) for value in slot.get("chapter_ids", []))
                or not {str(value) for value in slot.get("required_context_chapter_ids", [])} <= retrieved_chapters
                for slot in plan["slots"]
            )
            if missing_domains:
                raise StoryPlanningError("Retrieval did not retain candidates for every planned purpose/context domain; source-wide no-fit is unproven.",
                    {"outcome": "technical_error", "reason": "story_retrieval_incomplete", "applied_to_timeline": False,
                     "source_retrieval": receipt})
            receipt["retrieved_candidate_ids"] = [row["id"] for row in selected]
            return selected, receipt
        if len(selected) == 1:
            break
        remaining = selected
    raise StoryPlanningError("Retrieved complete canonical source still exceeds the context budget; no source was truncated.",
                             {"outcome": "technical_error", "reason": "story_input_context_limit", "applied_to_timeline": False,
                              "source_retrieval": receipt})


def _neutral_precision_plan(plan, brief):
    """Only a neutral one-idea Short has a mechanical temporal witness."""
    slots = plan.get("slots")
    return (str(brief.get("goal") or "short") == "short"
            and _local_continuous_plan_requested(brief)
            and not _configured_story_roles(brief) and not required_story_role_orders(brief)
            and isinstance(slots, list) and len(slots) == 1 and isinstance(slots[0], dict)
            and slots[0].get("purpose") == SINGLE_PASSAGE_PURPOSE
            and slots[0].get("required_context_chapter_ids") == [])


def _fixed_passage_choice_plan(candidates, plan, brief):
    """Only neutral, bounded, projected Shorts use fixed numeric options."""
    slots = plan.get("slots")
    return (str(brief.get("goal") or "short") == "short" and (_local_continuous_plan_requested(brief) or single_output_requested(brief))
            and not _configured_story_roles(brief) and not required_story_role_orders(brief)
            and isinstance(slots, list) and len(slots) == 1
            and slots[0].get("purpose") == SINGLE_PASSAGE_PURPOSE
            and 0 < len(candidates) <= SINGLE_PASSAGE_WINDOW_MAX_UNITS
            and all(row.get("candidate_policy") == CANDIDATE_POLICY_VERSION for row in candidates))


def _passage_options(candidates, segments, chapters, plan, brief, cancel_check=None, *, source_quality=None):
    from .story_passage_options import enumerate_passage_options
    result = enumerate_passage_options(candidates, segments, chapters, plan, brief,
        lambda ids: _story_selection_cost(ids, candidates, segments, brief), cancel_check, source_quality=source_quality)
    if explicit_source_continuity_requested(brief):
        supported, unsupported = [], []
        for option in result["options"]:
            try:
                proof = continuous_source_playback(candidates, segments, option["beat_ids"])
                if proof["playback_ranges"] != option["playback_ranges"]:
                    raise ValueError("Continuous option playback differs from canonical source.")
            except (ValueError, TypeError, KeyError):
                unsupported.append(option)
                continue
            option["continuous_source_playback"] = proof
            supported.append(option)
        result["options"] = supported
        result["receipt"].update(native_playback_option_count=len(supported),
            unsupported_continuous_mapping_ids=[r["id"] for r in unsupported],
            native_continuity_scope="One source envelope with all intervening canonical speech and original gap audio preserved")
    return result


def _passage_option_proposal(option, catalog, chapters, plan):
    """Application-owned exact quotations and temporal witness for a fixed set.

    This constructs no semantic verdict: the selector, critic and final review
    must still judge the entire fixed passage against the original instruction.
    """
    selected = set(option["beat_ids"])
    owners = {str(b["id"]): str(c["id"]) for c in chapters for b in c.get("beats", [])}
    slot = plan["slots"][0]
    source = [r for r in catalog if r["beat_id"] in selected]
    primary = [r for r in source if owners[r["beat_id"]] in slot["chapter_ids"]]
    if not primary:
        raise StoryPlanningError("Fixed source option has no allowed primary evidence.")
    final_beat = option["beat_ids"][-1]
    last = [r for r in primary if r["beat_id"] == final_beat]
    if not last:
        raise StoryPlanningError("Fixed source option lacks an eligible final witness.")
    anchor = max(last, key=lambda r: (r["end"], r["char_end"], r["id"]))
    choice = lambda row: f"{row['text']} [{row['id']}]"
    context = {cid: [choice(r) for r in source if owners[r["beat_id"]] == cid]
               for cid in slot["required_context_chapter_ids"]}
    return {"verdict": "fit", "role_selections": {SINGLE_PASSAGE_PURPOSE: {
        "primary_anchor_choice": choice(anchor),
        "additional_primary_evidence_choices": [choice(r) for r in primary if r["id"] != anchor["id"]],
        "context_evidence_choices_by_chapter": context}}, "highlight_beat_ids": [],
        "title": "CUTROOM draft", "summary": ""}


def _decode_passage_option_choice(reply, options, candidates, segments, chapters, plan, brief):
    scope = {"scope": options["receipt"]["scope"], "passage_options": options["receipt"],
             "source_wide_no_fit_proven": False, "applied_to_timeline": False}
    if isinstance(reply, dict) and reply.get("verdict") == "no_fit" and reply.get("reason") == "source_order":
        raise StoryPlanningError("The model reported source-order uncertainty without a source-order proof; no source was declared unsuitable.",
            {**scope, "reason": "model_temporal_refusal_unverified", "outcome": "technical_error", "source_order_evidence_verified": False})
    reason_contract = options["receipt"].get("rationale_contract")
    fields = {"verdict", "candidate_id", "semantic_reason", "refusal_category", "cited_segment_ids"}
    if reason_contract: fields.add("reason_evidence")
    if (not isinstance(reply, dict) or set(reply) != fields or reply.get("verdict") not in {"fit", "no_fit"}
            or not isinstance(reply.get("semantic_reason"), str) or not reply["semantic_reason"].strip()
            or reply.get("refusal_category") not in {"none", "semantic_rejection", "uncertain", "temporal_uncertainty"}
            or not isinstance(reply.get("cited_segment_ids"), list)
            or any(not isinstance(v, str) for v in reply["cited_segment_ids"])
            or len(reply["cited_segment_ids"]) != len(set(reply["cited_segment_ids"]))):
        raise StoryPlanningError("The model returned a malformed fixed-candidate choice.",
            {**scope, "reason": "invalid_passage_option_output", "outcome": "invalid_model_output"})
    if reason_contract and reply["verdict"]=="fit":
        if reply["cited_segment_ids"]!=[] or not isinstance(reply["reason_evidence"],list):
            raise StoryPlanningError("Nomination citations must be derived from exact quote evidence.",
                {**scope,"reason":"invalid_passage_rationale","outcome":"invalid_model_output"})
        reply=copy.deepcopy(reply)
        from .passage_binding import quote_reference
        quoted={quote_reference(r):r["id"] for r in segments}
        reply["cited_segment_ids"]=[quoted.get(r) for r in reply["reason_evidence"] if isinstance(r,str)]
    if reply["verdict"] == "no_fit":
        if reason_contract and reply["reason_evidence"] != []:
            raise StoryPlanningError("An unselected candidate cannot carry selected rationale quotes.",
                {**scope,"reason":"invalid_passage_option_output","outcome":"invalid_model_output"})
        if reply["candidate_id"] is not None or any(v not in {s["id"] for s in segments} for v in reply["cited_segment_ids"]):
            raise StoryPlanningError("Invalid fixed-candidate refusal references.",
                {**scope, "reason": "invalid_passage_option_output", "outcome": "invalid_model_output"})
        if reply["refusal_category"] in {"uncertain", "temporal_uncertainty"}:
            raise StoryPlanningError("The model left passage verification unfinished; its refusal is not evidence that the source is unsuitable.",
                {**scope, "reason": "passage_verification_unfinished", "outcome": "technical_error",
                 "model_refusal_category": reply["refusal_category"], "model_reason": reply["semantic_reason"], "semantic_result_verified": False})
        if reply["refusal_category"] != "semantic_rejection":
            raise StoryPlanningError("A refusal needs an explicit non-fit category.",
                {**scope, "reason": "invalid_passage_option_output", "outcome": "invalid_model_output"})
        refusal_quotes = []
        if reason_contract == "fixed-passage-reason-2026-10-23-v2.refusal-citations":
            selected_ids = set(options["options"][0]["segment_ids"])
            if not reply["cited_segment_ids"] or not set(reply["cited_segment_ids"]) <= selected_ids:
                raise StoryPlanningError("The model's refusal lacks exact selected-source evidence; source suitability remains unverified.",
                    {**scope,"reason":"unattributed_passage_refusal","outcome":"invalid_model_output",
                     "model_reason":reply["semantic_reason"],"semantic_result_verified":False})
            refusal_quotes = [{k:r[k] for k in ("id","start","end","text")} for r in segments
                              if r["id"] in set(reply["cited_segment_ids"])]
        raise StoryBudgetError("The model did not verify meaning/context among these presented fixed candidates; unpresented candidates and other pause-fit edits remain unreviewed.",
            {**scope, "reason": "semantic_candidates_rejected", "outcome": "editorial_no_fit", "semantic_result_verified": False,
             "model_reason": reply["semantic_reason"], "cited_segment_ids": reply["cited_segment_ids"],
             "refusal_source_quotes":refusal_quotes,"refusal_interpretation_verified":False})
    option = next((r for r in options["options"] if r["id"] == reply["candidate_id"]), None)
    if (reply["refusal_category"] != "none" or option is None or not reply["cited_segment_ids"]
            or not set(reply["cited_segment_ids"]) <= set(option["segment_ids"])):
        raise StoryPlanningError("The model chose a foreign candidate or nonselected source evidence.",
            {**scope, "reason": "invalid_passage_option_output", "outcome": "invalid_model_output"})
    from .passage_binding import source_binding, validate_reason_quotes, NOMINATION_REASON
    reason_proof = None
    if reason_contract:
        try:
            if reply["semantic_reason"] != NOMINATION_REASON:
                raise ValueError("Nomination prose cannot assert unverified source interpretation.")
            reason_proof=validate_reason_quotes(reply["reason_evidence"],option,segments,reply["cited_segment_ids"])
        except (ValueError,TypeError,KeyError) as exc:
            raise StoryPlanningError("Candidate rationale is not bound to the exact selected source.",
                {**scope,"reason":"invalid_passage_rationale","outcome":"invalid_model_output","attribution_error":str(exc)}) from exc
    catalog = build_story_evidence_catalog(candidates, segments)
    proposal = _passage_option_proposal(option, catalog, chapters, plan)
    clean = _decode_precision_story_selection(proposal, catalog, candidates, segments, chapters, plan, brief)
    clean["passage_option_selection"] = {"candidate_id": option["id"], "option": copy.deepcopy(option),
        "enumeration": copy.deepcopy(options["receipt"]), "model_reason": reply["semantic_reason"],
        "cited_segment_ids": list(reply["cited_segment_ids"]), "semantic_verified": False,
        "source_binding":source_binding(option,segments),"rationale_proof":reason_proof,
        "model_reason_authority":"unverified_nomination_only"}
    return clean


def _assess_passage_source_quality(settings, candidates, segments, model, mode, cancel_check):
    """One bounded source-reading pass; advisory to retrieval, never approval."""
    from .passage_quality import source_review_schema, validate_source_review
    payload={"model":model,"stream":False,"_single_attempt":True,"_reject_duplicate_keys":True,
        "_performance_mode":mode,"format":source_review_schema(candidates),
        "options":{"temperature":0.,"num_ctx":8192,"num_predict":1800},"messages":[
        {"role":"system","content":"You are CUTROOM's bounded source quality reader. Read each exact ASR source unit in its original language. "
         "Return one record for EVERY supplied unit ID. This is source text assessment, not an edit or final meaning approval. "
         "Use clear if you identify no specific source defect; this does not mean standalone context or correct audio. "
         "Use context with previous/next/both only when the unit needs adjacent source to complete its thought or resolve its opening. "
         "Use uncertain with direction none for specific unclear/broken ASR wording that adjacent context does not resolve. "
         "Clear uses direction none. Cite1-3 source_segment_ids from that SAME unit; explain briefly using its actual words. "
         "Do not translate ambiguous wording into a new claim. Colloquial speech, a repeated refrain, source length or aesthetic preference alone is not a source defect. "
         "Do not choose output times, enforce a story template or replace source words. Unknown audio remains unverified. Return only the required unit-ID object."},
        {"role":"user","content":json.dumps({"source_units_for_quality":[{"id":r["id"],"segment_ids":r["segment_ids"],"text":r["text"],
          "neighbor_source_utterances":neighboring_source_utterances([r],segments)} for r in candidates]},ensure_ascii=False)}]}
    reply=_call_ollama_story_pass(settings,payload,60,cancel_check)
    try:return validate_source_review(reply,candidates,model)
    except (ValueError,TypeError,KeyError) as exc:
        raise StoryPlanningError("The bounded source quality assessment has invalid source attribution; no new draft was applied.",
            {"reason":"invalid_source_quality_assessment","outcome":"invalid_model_output","applied_to_timeline":False}) from exc


def _select_passage_option(settings, candidates, segments, chapters, plan, brief, model, cancel_check):
    source_quality=None
    # Experimental source-reading advice is opt-in until editorial benefit is
    # established. Small/no-cut paths keep their existing bounded route.
    if (8<len(candidates)<=20 and all(r.get("entry_policy") for r in candidates)
            and not explicit_source_continuity_requested(brief)
            and settings.ai.get("source_quality_assessment",False)):
        source_quality=_assess_passage_source_quality(settings,candidates,segments,model,
            str(brief.get("performance_mode") or settings.ai.get("performance_mode","auto")),cancel_check)
    options = _passage_options(candidates, segments, chapters, plan, brief, cancel_check, source_quality=source_quality)
    if not options["options"]:
        if options["receipt"].get("unsupported_continuous_mapping_ids"):
            raise StoryPlanningError("Numerically valid continuous candidates cannot be represented by the current native per-unit playback without cutting their gaps. No model call or edit was made.",
                {"reason": "continuous_passage_mapping_unavailable", "outcome": "technical_error", "passage_options": options["receipt"],
                 "source_wide_no_fit_proven": False, "applied_to_timeline": False})
        raise StoryBudgetError("No complete consecutive candidate in this domain already fits the unchanged raw-duration band; disjoint and pause-fit alternatives were not searched.",
            {"reason": "no_feasible_passage_options", "outcome": "constraint_conflict", "scope": options["receipt"]["scope"],
             "passage_options": options["receipt"], "source_wide_no_fit_proven": False, "applied_to_timeline": False})
    from .passage_binding import presented_options, assessment_options, PASSAGE_REASON_CONTRACT, MAX_PASSAGE_ASSESSMENTS
    retrieved_count = len(options["options"])
    shortlist = presented_options(options["options"], [r["id"] for r in candidates])
    assessment_order = assessment_options(shortlist, [r["id"] for r in candidates])
    receipt = options["receipt"]
    assessments = []
    receipt.update(rationale_contract=PASSAGE_REASON_CONTRACT, retrieved_option_count=retrieved_count,
        review_candidates=[{key:copy.deepcopy(r[key]) for key in ("id","segment_ids","playback_ranges")} for r in shortlist],
        screening_shortlist=[{"candidate_id":r["id"],"segment_ids":list(r["segment_ids"])} for r in shortlist],
        screening_shortlist_count=len(shortlist), maximum_candidate_assessments=MAX_PASSAGE_ASSESSMENTS,
        assessment_order=[r["id"] for r in assessment_order],
        candidate_assessments=assessments, comparison_scope="one exact candidate per request; bounded independent assessments")
    last_rejection = None
    for option in assessment_order:
        _check_cancelled(cancel_check)
        receipt.update(presented_option_count=len(assessments)+1, option_count=1,
            all_numeric_options_presented=receipt["numeric_option_count"]==len(assessments)+1,
            unreviewed_retrieved_option_count=retrieved_count-len(assessments)-1)
        current = {"options":[option], "receipt":copy.deepcopy(receipt)}
        payload = _passage_option_request(settings, current, candidates, segments, brief, model)
        reply = _call_ollama_story_pass(settings, payload, 90, cancel_check)
        row = {"candidate_id":option["id"],"raw_playable_seconds":option["raw_playable_seconds"],
               "semantic_fit_verified":False}
        try:
            clean = _decode_passage_option_choice(reply, current, candidates, segments, chapters, plan, brief)
        except StoryPlanningError as exc:
            row.update(outcome=exc.diagnostic.get("outcome", "technical_error"), reason=exc.diagnostic.get("reason"))
            assessments.append(row)
            if exc.diagnostic.get("reason") != "semantic_candidates_rejected":
                exc.diagnostic["passage_options"] = copy.deepcopy(receipt)
                raise
            # A well-formed candidate-specific semantic refusal leaves other
            # candidates unreviewed. Malformed output/uncertainty never retries.
            row["model_reason"] = exc.diagnostic.get("model_reason")
            row["refusal_source_quotes"] = copy.deepcopy(exc.diagnostic.get("refusal_source_quotes", []))
            row["refusal_interpretation_verified"] = False
            last_rejection = exc
            continue
        row["outcome"] = "provisional_nomination"
        assessments.append(row)
        clean["passage_option_selection"]["enumeration"] = copy.deepcopy(receipt)
        return clean, candidates
    assert last_rejection is not None
    last_rejection.diagnostic["passage_options"] = copy.deepcopy(receipt)
    last_rejection.diagnostic["candidate_assessment_limit_reached"] = len(assessments)==MAX_PASSAGE_ASSESSMENTS
    remaining = retrieved_count-len(assessments)
    last_rejection.diagnostic.update(search_status="incomplete" if remaining else "presented_domain_exhausted",
        reviewed_candidate_count=len(assessments), unreviewed_candidate_count=remaining)
    if remaining:
        raise StoryBudgetError(f"The bounded selection reviewed {len(assessments)} of {retrieved_count} candidates without an accepted edit; "
            f"{remaining} candidates remain unreviewed. This is an incomplete search. The existing edit was kept.",
            last_rejection.diagnostic)
    raise last_rejection


def _passage_option_request(settings, options, candidates, segments, brief, model):
    """One immutable source candidate; neighbors never become selected text."""
    from .passage_binding import quote_schema, NOMINATION_REASON, quote_reference
    by_segment = {r["id"]: r for r in segments}
    segment_ids = list(options["options"][0]["segment_ids"])
    # Nominate on the actual request, not on renderer defaults or generated
    # style guidance. In the saved HE trace a model treated clear_promise and
    # advisory pre/post-roll seconds as mandatory reasons to reject a source.
    review_brief = {key:copy.deepcopy(brief[key]) for key in (
        "instruction", "goal", "output_count", "source_continuity", "target_duration",
        "duration_mode", "language", "spoken_language") if key in brief}
    payload = {"model": model, "stream": False, "_single_attempt": True, "_reject_duplicate_keys": True,
        "_performance_mode": str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto")),
        "options": {"temperature": .02, "num_ctx": 12288, "num_predict": 700},
        "format": {"type": "object", "additionalProperties": False,
            "required": ["verdict", "candidate_id", "semantic_reason", "refusal_category", "cited_segment_ids"], "properties": {
                "verdict": {"type": "string", "enum": ["fit", "no_fit"]},
                "candidate_id": {"enum": [None] + [r["id"] for r in options["options"]]},
                "semantic_reason": {"type": "string","minLength":1},
                "refusal_category": {"enum": ["none", "semantic_rejection", "uncertain", "temporal_uncertainty"]},
                "cited_segment_ids": {"type": "array", "uniqueItems": True, "items": {"type": "string", "enum": segment_ids}}}},
        "messages": [{"role": "system", "content":
            "You are CUTROOM's precision editor. Independently assess this ONE fixed candidate by meaning, complete thought and necessary context. No other candidate text is included. "
            "The application already owns exact source order, immutable words, playback times and hard numeric duration. Do not compute an end anchor, reorder, trim, add or combine candidates. "
            "Judge the WHOLE candidate, not its number of analysis units. Punctuation is not semantic completeness. Reject broken ASR joins and context-dependent openings if their meaning cannot stand alone. "
            "The verbatim user instruction is mandatory; style preferences are advisory. Source ASR is not verified audio. Neighbor context is reference-only, not included footage. "
            "For fit nominate its candidate_id with exact selected source quotations; independent semantic review is still mandatory. "
            "For fit use refusal_category=none. For no_fit use candidate_id=null and category semantic_rejection for a specific meaning/context defect, uncertain if you cannot assess it, or temporal_uncertainty for any unverified timing/order concern. "
            "No fit among these options is not a claim about the whole source or unsearched disjoint/pause-fit edits."},
            {"role": "user", "content": json.dumps({"brief": review_brief,
                "style_preferences": {"id":brief.get("edit_style"),
                    "authority":"advisory_not_rejection_requirements"},
                "passage_candidates": [{"id": r["id"], "segment_ids": r["segment_ids"],
                    "source_groups": r["selected_source_groups"], "raw_playable_seconds": r["raw_playable_seconds"],
                    "playback_ranges": r["playback_ranges"],
                    "source_continuity_required": r["explicit_source_continuity_requested"],
                    "source_text": " ".join(by_segment[sid]["text"] for sid in r["segment_ids"]),
                    "retrieval_quality": r.get("retrieval_quality", {"semantic_quality_verified":False}),
                    } for r in options["options"]],
                "source_utterances": [{k: by_segment[sid][k] for k in ("id", "start", "end", "text")}|{"quote_id":quote_reference(by_segment[sid])} for sid in segment_ids],
                "neighboring_source_utterances": neighboring_source_utterances([r for r in candidates if r["id"] in set(options["options"][0]["beat_ids"])], segments),
                "duration_bounds":options["receipt"]["duration_bounds"],
                "enumeration_scope": options["receipt"]["scope"]}, ensure_ascii=False)}]}
    schema=payload["format"]
    schema["required"].append("reason_evidence")
    schema["properties"]["reason_evidence"]={"type":"array","maxItems":3}
    schema["anyOf"]=[{"properties":{"verdict":{"const":"fit"},"candidate_id":{"const":r["id"]},
        "semantic_reason":{"const":NOMINATION_REASON},"refusal_category":{"const":"none"},
        "cited_segment_ids":{"maxItems":0},
        "reason_evidence":quote_schema(r["segment_ids"],segments)}} for r in options["options"]]+[
        {"properties":{"verdict":{"const":"no_fit"},"candidate_id":{"const":None},
            "refusal_category":{"const":"semantic_rejection"},"cited_segment_ids":{"minItems":1},"reason_evidence":{"maxItems":0}}},
        {"properties":{"verdict":{"const":"no_fit"},"candidate_id":{"const":None},
            "refusal_category":{"enum":["uncertain","temporal_uncertainty"]},"reason_evidence":{"maxItems":0}}}]
    payload["messages"][0]["content"] += (" This is a provisional nomination, not semantic approval. "
        "For fit semantic_reason is the schema's constant notice; reason_evidence names1-3 exact selected quote_id values. The app reconstructs their complete original text. "
        "cited_segment_ids stays empty; the application derives citations from reason_evidence, avoiding two independent citation lists. Do not generate an interpretive rationale about other options. "
        "Each candidate source_text is the complete selected text; global/neighbor utterances are reference-only. "
        "playback_ranges are the actual source intervals: one continuous interval preserves all original audio between utterances, regardless of ASR gaps. ASR boundaries are not cuts. "
        "A semantic rejection must cite at least one selected source_utterance ID and explain its actual original words. Do not translate an ambiguous word into a factual ASR error, invent a missing quote, or impose style hooks/pre-roll/post-roll. Neighbor references may explain an opening, but their words are not selected footage. If a claim cannot be established from this text, use uncertain. "
        "Retrieval quality contains unverified source-reading advice and repeated-phrase counts; neither establishes grammar or meaning. Repetition can be intentional. Judge the actual words. A fit must be independently coherent and stand alone, not merely be the best available alternative. Other candidates remain unreviewed.")
    from .structured_schema import complete_object_union
    payload["format"] = complete_object_union(schema)
    if not _story_payload_fits_cap(payload, payload["_performance_mode"]):
        raise StoryPlanningError("The complete bounded passage choice exceeds its context budget; no options were truncated.",
            {"reason": "passage_options_context_limit", "outcome": "technical_error", "passage_options": options["receipt"], "applied_to_timeline": False})
    return payload


def _precision_story_payload(
    candidates, segments, chapters, summaries, outline, plan, brief, model, mode, target,
):
    """Build the unchanged exact-source precision contract for retrieved candidates."""
    source_catalog = build_story_evidence_catalog(candidates, segments) if segments else []
    candidate_segment_ids = {str(identifier) for beat in candidates for identifier in beat.get("segment_ids", [])}
    precision_schema = _precision_story_contract(source_catalog, candidates, chapters, plan, brief)
    neutral = _neutral_precision_plan(plan, brief)
    if neutral:
        # This grammar selects one account through exact quotations. A second
        # independent beat-ranking list is unnecessary and can contradict those
        # choices. Keep source decoding strict; request no decorative rankings.
        for branch in precision_schema["anyOf"]:
            if branch["properties"]["verdict"].get("enum") == ["fit"]:
                branch["properties"]["highlight_beat_ids"] = {"type": "array", "maxItems": 0}
    payload = {
        "model": model,
        "stream": False,
        "format": precision_schema,
        "_single_attempt": True, "_reject_duplicate_keys": True,
        "_performance_mode": mode,
        "options": {"temperature": 0.04, "num_ctx": 16384 if mode == "quality" else 12288, "num_predict": 1500},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM's precision editor. Source quotes and full ASR utterances are authoritative; outline and summary prose are unverified interpretations. "
                    "Choose fit only if the verbatim source supports EVERY exact planned purpose, complete prerequisite context and chronological role order. "
                    "Return role_selections keyed by every exact plan purpose. For each role choose primary_anchor_choice and additional_primary_evidence_choices "
                    "only from its planned chapter_ids. Copy exact source_evidence_choices strings, including their canonical reference. "
                    "Fill context_evidence_choices_by_chapter for EVERY required_context_chapter_id with at least one exact choice from that chapter; "
                    "use an empty object only when no context chapters are required. The same choice can supply primary and context when both allow it; this does not repeat footage. "
                    "Every quoted fragment requires its ENTIRE canonical ASR utterance, including all negations and qualifications. "
                    "Each candidate beat is an indivisible selectable source unit: citing ANY quotation also retains ALL ASR utterances "
                    "of that owning candidate, not only the quoted utterance. Check the full selected-unit duration costs together "
                    "before returning fit; quotation length is not playable duration and does not authorize a subspan cut. "
                    "Punctuation_at_asr_boundary is a proposed cut boundary, not proof of a complete meaning. "
                    "Parent analysis IDs and neighbor IDs are context/provenance, not automatically selected footage. "
                    "Read neighboring_source_utterances when needed; they are reference-only and cannot supply an unselected prerequisite. "
                    "Reject or choose other complete source when an opening depends on omitted context or ASR contains a broken join; never repair its words. "
                    "primary_anchor_choice is a temporal witness, not an opening or hook. Primary anchors follow planned role order in source playback. "
                    "For the LAST planned purpose, choose primary_anchor_choice from the selected beat with the latest source end, "
                    "including when the plan has only one neutral purpose. Put earlier related supporting quotations in additional_primary_evidence_choices. "
                    "Evidence list order does not reorder footage: the selected complete utterances play in original source chronology. "
                    + ("For the neutral self_contained_passage purpose, semantic support is judged from "
                       "the whole selected account with all complete source utterances, not from the "
                       "temporal anchor quotation alone. The latest-beat anchor still witnesses source "
                       "order and never proves a complete account by itself; retain earlier related "
                       "evidence. An acknowledgment, filler or unfinished phrase alone cannot establish "
                       "a complete account. A conclusion can be an explicit refusal, decision or qualified claim. "
                       "Set highlight_beat_ids to []; the exact quotation assignments alone determine selected source. "
                       if neutral else
                       "An acknowledgment, filler or unfinished phrase alone cannot establish a role. A conclusion can be an explicit refusal, decision or qualified claim. ")
                    +
                    "Do not invent events, outcomes, proof claims or missing endings. If source cannot support a role, its context, source order or target budget, "
                    "return no_fit with reason and missing_purposes, without quotation assignments. A truthful no_fit is preferable to unsupported role assignments. "
                    "For fit return only verdict,role_selections,highlight_beat_ids,title,summary. For no_fit return only verdict,reason,missing_purposes. "
                    + ("The user requests ONE coherent self-contained idea. Meaning-preserving cuts among related complete source utterances are allowed. "
                       "Do not join unrelated topics or manufacture a whole-episode narrative; all purposes and context must serve the same idea. "
                       if single_source_passage_requested(brief) else "")
                    + ("The original instruction explicitly forbids internal source cuts. Choose consecutive complete source units, "
                       "preserving intervening source time and pauses. Return no_fit if that fixed continuous selection conflicts with the target. "
                       if explicit_source_continuity_requested(brief) else "")
                    + ("Candidate beats are storage groupings, not necessarily independent semantic moments; "
                       "one self-contained source account may span multiple related beats in chronology. "
                       "Judge actual semantic continuity from the source utterances, not the number of "
                       "beat IDs; do not assume either coherence or incoherence from grouping alone. "
                       if neutral else "")
                    + _on_screen_guidance(candidates)
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "brief": brief,
                    "target_seconds": target,
                    "minimum_target_seconds": effective_duration_bounds(brief, max([float(row.get("end", 0)) for row in (segments or [])] or [target]))["minimum_seconds"],
                    "duration_bounds": effective_duration_bounds(brief, max([float(row.get("end", 0)) for row in (segments or [])] or [target])),
                    "outline": outline,
                    "plan": plan,
                    "chapter_summaries": summaries,
                    "source_evidence": source_catalog,
                    "source_evidence_choices": list(_story_evidence_choice_catalog(source_catalog)),
                    "source_span_policy_version": SOURCE_SPAN_POLICY_VERSION,
                    "neighboring_source_utterances": neighboring_source_utterances(candidates, segments or []),
                    "source_utterances": [{"id": str(row["id"]), "start": row["start"], "end": row["end"], "text": str(row.get("text") or "")}
                                          for row in (segments or [])
                                          if str(row["id"]) in candidate_segment_ids],
                    **({"whole_candidate_selection_cost": {
                        "beat_ids": [str(row["id"]) for row in candidates],
                        "duration_cost": _story_selection_cost([str(row["id"]) for row in candidates], candidates, segments or [], brief),
                    }} if neutral else {}),
                    "candidate_beats": [
                        # Lexical/question-mark role hints are retrieval heuristics,
                        # not evidence of a planned semantic role. Supplying them as
                        # "role" can conflict with the exact source/anchor contract.
                        {"id": beat["id"], "start": beat["start"], "duration": beat["duration"],
                         "duration_cost": _story_selection_cost([str(beat["id"])], candidates, segments or [], brief),
                          "text": _balanced_excerpt(str(beat.get("text", "")), 520),
                          **candidate_projection_fields(beat), **_on_screen_field(beat)}
                        for beat in candidates
                    ],
                }, ensure_ascii=False),
            },
        ],
    }
    return payload, source_catalog


def _decode_precision_story_selection(result, source_catalog, candidates, segments, chapters, plan, brief, retrieval=None):
    """Use the same strict source/quotation decoder for each bounded precision pass."""
    valid = {str(item["id"]): item for item in candidates}
    purposes = [row["purpose"] for row in plan["slots"]]
    if isinstance(result, dict) and result.get("verdict") == "no_fit":
        missing = result.get("missing_purposes")
        if (set(result) != {"verdict", "reason", "missing_purposes"}
                or not isinstance(result.get("reason"), str)
                or result["reason"] not in {"unsupported_roles", "insufficient_context", "source_order", "target_budget"}
                or not isinstance(missing, list) or any(not isinstance(value, str) or value not in purposes for value in missing)
                or len(missing) != len(set(missing))):
            raise StoryPlanningError("Story AI returned an invalid precision refusal.")
        raise StoryBudgetError("Story AI could not verify a complete story from this selection. No new draft was applied.",
            {"reason": "precision_no_fit", "outcome": "editorial_no_fit", "applied_to_timeline": False,
             "stage": "precision", "scope": "retrieved_candidate_selection",
             "retrieved_candidate_ids": [row["id"] for row in candidates], "precision": {"attempts": 1,
             "verdict": "no_fit", "reason": result["reason"], "missing_purposes": list(missing)}})
    if (not isinstance(result, dict) or result.get("verdict") != "fit"
            or set(result) != {"verdict", "role_selections", "highlight_beat_ids", "title", "summary"}
            or not isinstance(result.get("title"), str) or not isinstance(result.get("summary"), str)):
        raise StoryPlanningError("Story AI did not return a complete precision selection or explicit refusal.")
    try:
        slot_map = _precision_story_slot_rows(result["role_selections"], source_catalog, candidates, chapters, plan)
        keep = sorted({identifier for row in slot_map for key in ("primary_beat_ids", "context_beat_ids") for identifier in row[key]},
                      key=lambda identifier: float(valid[identifier]["start"]))
        slot_map = _validated_story_slot_map(slot_map, keep, candidates, chapters, plan)
        proof = _story_evidence_proof(slot_map, keep, candidates, segments or [], plan, brief)
        _validate_single_source_passage(keep, chapters, brief)
        if not _story_units_complete(keep, candidates, segments or []):
            raise ValueError("Precision selection requires complete canonical source units.")
        highlights = result["highlight_beat_ids"]
        if (not isinstance(highlights, list) or any(not isinstance(value, str) or value not in keep for value in highlights)
                or len(highlights) != len(set(highlights))):
            raise ValueError("Precision highlights must be unique selected source identifiers.")
    except (ValueError, TypeError, KeyError) as exc:
        raise StoryPlanningError("Story AI returned invalid precision source assignments. No new draft was applied.") from exc
    clean = {
        "keep_beat_ids": keep, "slot_map": proof["slot_map"], "highlight_beat_ids": highlights[:8],
        "opening_beat_id": keep[0], "closing_beat_id": keep[-1],
        "title": result["title"].strip()[:120] or "CUTROOM story", "title_beat_ids": list(keep),
        "summary": _extractive_story_summary(proof), "summary_source": SUMMARY_SOURCE,
        "selection_mode": "model", "recovered_slot_indexes": [], "recovery_reason": None,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION, "evidence_proof": proof,
        # Source attribution/order does not establish the model's interpretation.
        "semantic_mapping_verified": False, "semantic_review_status": "provisional_precision_selection",
    }
    if retrieval is not None:
        clean["source_retrieval"] = retrieval
    return clean


def _decode_proposed_precision_story_selection(result, source_catalog, candidates, segments, chapters, plan, brief, retrieval=None):
    """Canonicalize only a neutral temporal pointer before unchanged proof checks."""
    from .precision_neutral import adapt_neutral_temporal_witness
    proposal, provenance = adapt_neutral_temporal_witness(
        result, source_catalog, candidates, segments, chapters, plan, brief,
        eligible=_neutral_precision_plan(plan, brief))
    clean = _decode_precision_story_selection(proposal, source_catalog, candidates, segments, chapters, plan, brief, retrieval)
    if provenance is not None:
        clean["precision_representation_adapter"] = provenance
    return clean


def _single_passage_proposal_budget(selection, candidates, segments, brief):
    """Necessary duration bounds only; never a semantic or editorial approval."""
    duration = max([float(row.get("end", 0)) for row in (segments or [])] or [0.])
    bounds = effective_duration_bounds(brief, duration)
    target, minimum = bounds["maximum_seconds"], bounds["minimum_seconds"]
    cost = _story_selection_cost(selection["keep_beat_ids"], candidates, segments or [], brief)
    return {"minimum_output_seconds": minimum, "target_seconds": target, "duration_bounds": bounds,
            "minimum_safe_seconds": cost["minimum_safe_seconds"], "approved_seconds": cost["approved_seconds"],
            "feasible": cost["fits_target"] is True and cost["approved_seconds"] + .05 >= minimum}


def _prepare_story_window_search(settings, chapters, summaries, outline, plan, brief, model, segments,
                                 search_identity, cancel_check=None):
    """Reconstruct exact canonical window requests without any inference calls."""
    if not search_identity or getattr(settings, "cache_dir", None) is None:
        return None
    if (str(brief.get("goal") or "short") != "short" or not single_source_passage_requested(brief)
            or _configured_story_roles(brief) or len(plan.get("slots", [])) != 1):
        return None
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    target = effective_duration_bounds(brief)["maximum_seconds"]
    candidates = _candidate_beats_for_plan(chapters, plan)
    if not candidates or len(candidates) > SINGLE_PASSAGE_WINDOW_MAX_UNITS:
        return None
    initial, _ = _precision_story_payload(candidates, segments, chapters, summaries, outline, plan, brief, model, mode, target)
    if _story_payload_fits_cap(initial, mode):
        return None
    from .story_context import build_whole_recording_index, retrieve_candidate_source, bounded_contiguous_source_windows
    index = build_whole_recording_index(chapters, summaries, summary_char_limit=160, key_point_char_limit=64, max_key_points=2)
    precision_summaries = [{key: row[key] for key in ("id", "summary", "key_points", "depends_on", "interpretation_status")}
                           for row in index["chapters"]]
    precision_outline = copy.deepcopy(outline)
    for key in ("premise", "audience_takeaway"):
        if isinstance(precision_outline.get(key), str):
            precision_outline[key] = _balanced_excerpt(precision_outline[key], 160)
    for row in precision_outline.get("story_arc") or []:
        if isinstance(row, dict) and isinstance(row.get("why_it_matters"), str):
            row["why_it_matters"] = _balanced_excerpt(row["why_it_matters"], 120)
    precision_outline["interpretation_status"] = "abbreviated_unverified_outline"
    domain = list(dict.fromkeys(str(value) for slot in plan["slots"]
                  for key in ("chapter_ids", "required_context_chapter_ids") for value in slot.get(key, [])))
    canonical = {row["id"]: row for row in retrieve_candidate_source(chapters, segments or [], domain)["beats"]}
    if any(row != canonical.get(row["id"]) for row in candidates):
        raise StoryPlanningError("Canonical continuation source changed.", {"outcome": "technical_error",
             "reason": "invalid_story_source_context", "applied_to_timeline": False})
    started = time.monotonic()
    def make_precision(rows):
        return _precision_story_payload(rows, segments, chapters, precision_summaries, precision_outline,
                                        plan, brief, model, mode, target)
    def make_window(rows):
        _check_cancelled(cancel_check)
        if time.monotonic() - started >= SINGLE_PASSAGE_WINDOW_SECONDS:
            raise StoryPlanningError("Canonical window preparation exceeded its work budget.", {
                "outcome": "technical_error", "reason": "story_window_work_budget_exhausted", "applied_to_timeline": False})
        return make_precision(rows)[0]
    windows = bounded_contiguous_source_windows(candidates, make_window, lambda payload: _story_payload_fits_cap(payload, mode))
    identity = {"version": "canonical-window-search-v2", "binding": search_identity,
                "pipeline": STORY_CACHE_PIPELINE, "source_span_policy": SOURCE_SPAN_POLICY_VERSION,
                "evidence_policy": EVIDENCE_POLICY_VERSION, "model": model,
                "configuration": stable_fingerprint("story-search-config", getattr(settings, "raw", settings.ai)),
                "source": stable_fingerprint("story-search-whole-source", {"segments": segments, "chapters": chapters}),
                "intent": stable_fingerprint("story-search-intent", brief),
                "plan": stable_fingerprint("story-search-plan", plan),
                "requests": [stable_fingerprint("story-search-request", make_window(window)) for window in windows]}
    from .story_search_checkpoint import StorySearchCheckpoint
    checkpoint = StorySearchCheckpoint(settings.cache_dir, identity, candidates, windows)
    return {"checkpoint": checkpoint, "windows": windows, "make_precision": make_precision}


def _cached_story_window_trial(record, window, plan):
    if not isinstance(record, dict) or not isinstance(record.get("scope"), dict):
        return None
    trial = record["scope"].get("trial")
    if not isinstance(trial, dict) or trial.get("candidate_beat_ids") != [row["id"] for row in window]:
        return None
    if record.get("outcome") == "no_fit" and trial.get("verdict") == "no_fit":
        proof = trial.get("precision")
        if (isinstance(proof, dict) and set(proof) == {"attempts", "verdict", "reason", "missing_purposes"}
                and type(proof.get("attempts")) is int and proof["attempts"] == 1 and proof.get("verdict") == "no_fit"
                and proof.get("reason") in {"unsupported_roles", "insufficient_context", "source_order", "target_budget"}
                and isinstance(proof.get("missing_purposes"), list)
                and all(isinstance(value, str) and value in {row["purpose"] for row in plan["slots"]} for value in proof["missing_purposes"])
                and len(proof["missing_purposes"]) == len(set(proof["missing_purposes"]))):
            return copy.deepcopy(trial)
    if (record.get("outcome") == "budget_miss" and trial.get("verdict") == "provisional_budget_miss"
            and isinstance(trial.get("proposal_budget"), dict) and trial["proposal_budget"].get("feasible") is False):
        return copy.deepcopy(trial)
    return None


def _review_canonical_story_windows(settings, planned_candidates, segments, chapters, plan, brief, model, mode,
                                    cancel_check, make_precision, retrieval, first_failure, *, checkpoint=None, windows=None):
    from .story_context import bounded_contiguous_source_windows
    started = time.monotonic()
    review = {"version": "canonical-passage-windows-v2", "authority": "provisional_precision_requires_unchanged_critic_and_target_review",
              "eligible_source_beat_ids": [row["id"] for row in planned_candidates],
              "limits": {"maximum_source_units": SINGLE_PASSAGE_WINDOW_MAX_UNITS,
                         "maximum_model_calls": SINGLE_PASSAGE_WINDOW_MAX_CALLS, "seconds": SINGLE_PASSAGE_WINDOW_SECONDS},
              "trials": [], "new_model_calls": 0, "reused_trials": 0, "search_status": "incomplete"}
    if checkpoint is not None:
        review["checkpoint_fingerprint"] = checkpoint.fingerprint
    def incomplete(reason):
        raise StoryPlanningError("The bounded source-window search is incomplete; no source-wide no-fit or edit was declared.",
            {"outcome": "technical_error", "reason": reason, "scope": "canonical_plan_domain_windows", "applied_to_timeline": False,
             "source_retrieval": {**copy.deepcopy(retrieval), "canonical_window_review": copy.deepcopy(review)}})
    if len(planned_candidates) > SINGLE_PASSAGE_WINDOW_MAX_UNITS:
        incomplete("story_window_work_budget_exhausted")
    def window_payload(rows):
        _check_cancelled(cancel_check)
        if time.monotonic() - started >= SINGLE_PASSAGE_WINDOW_SECONDS:
            incomplete("story_window_work_budget_exhausted")
        return make_precision(rows)[0]
    if windows is None:
        windows = bounded_contiguous_source_windows(planned_candidates, window_payload,
                                                   lambda value: _story_payload_fits_cap(value, mode))
    review["planned_window_count"] = len(windows)
    for window in windows:
        _check_cancelled(cancel_check)
        identifiers = [row["id"] for row in window]
        if checkpoint is not None:
            stored = checkpoint.completed(identifiers)
            reused = _cached_story_window_trial(stored, window, plan)
            if reused is not None:
                review["trials"].append(reused)
                review["reused_trials"] += 1
                continue
            if stored is not None:
                checkpoint.discard(identifiers)
        remaining = SINGLE_PASSAGE_WINDOW_SECONDS - (time.monotonic() - started)
        if review["new_model_calls"] >= SINGLE_PASSAGE_WINDOW_MAX_CALLS or remaining < 1:
            incomplete("story_window_work_budget_exhausted")
        request, catalog = make_precision(window)
        request.update(_single_attempt=True, _reject_duplicate_keys=True)
        review["new_model_calls"] += 1
        reply = _call_ollama_story_pass(settings, request, max(1, int(remaining)), cancel_check)
        trial = {"candidate_beat_ids": identifiers}
        try:
            clean = _decode_proposed_precision_story_selection(reply, catalog, window, segments, chapters, plan, brief)
        except StoryBudgetError as refusal:
            if refusal.diagnostic.get("reason") != "precision_no_fit":
                raise
            trial.update(verdict="no_fit", precision=copy.deepcopy(refusal.diagnostic["precision"]))
            _check_cancelled(cancel_check)
            if checkpoint is not None:
                checkpoint.record(identifiers, "no_fit", scope={"trial": trial})
            review["trials"].append(trial)
            continue
        budget = _single_passage_proposal_budget(clean, window, segments, brief)
        if not budget["feasible"]:
            trial.update(verdict="provisional_budget_miss", proposal_budget=budget)
            _check_cancelled(cancel_check)
            if checkpoint is not None:
                checkpoint.record(identifiers, "budget_miss", scope={"trial": trial})
            review["trials"].append(trial)
            continue
        trial.update(verdict="provisional_fit", selected_beat_ids=list(clean["keep_beat_ids"]))
        review["trials"].append(trial)
        review["search_status"] = "provisional_candidate_requires_review"
        clean["source_retrieval"] = {**copy.deepcopy(retrieval), "canonical_window_review": review}
        return clean, window
    review["search_status"] = "domain_exhausted"
    if any(trial["verdict"] == "provisional_budget_miss" for trial in review["trials"]):
        incomplete("story_window_proposals_unfit")
    diagnostic = copy.deepcopy(first_failure.diagnostic) if first_failure is not None else {
        "reason": "precision_no_fit", "outcome": "editorial_no_fit", "applied_to_timeline": False,
        "semantic_result_verified": False}
    diagnostic.update(scope="canonical_plan_domain_windows", semantic_result_verified=False,
                      source_retrieval={**copy.deepcopy(retrieval), "canonical_window_review": review})
    if (len(plan.get("slots", [])) == 1 and plan["slots"][0].get("purpose") == SINGLE_PASSAGE_PURPOSE
            and not _configured_story_roles(brief) and review["trials"]
            and all((row.get("precision") or {}).get("reason") == "source_order" for row in review["trials"])):
        # A raw refusal label is not an ordering proof. The one neutral role has
        # no relative role ordering; the unchanged decoder still owns all source
        # witnesses. Do not turn these unexplained refusals into a verified
        # claim that suitable source footage does not exist.
        diagnostic.update(reason="precision_semantics_unverified", outcome="technical_error",
                          model_refusal_reason="source_order", source_order_evidence_verified=False)
        raise StoryPlanningError("The plan-domain search finished, but the model did not verify a passage. "
            "Its source-order refusal remains unverified; the existing edit was kept.", diagnostic)
    raise StoryBudgetError("Precision did not verify a passage within this fully reviewed plan domain; no source-wide impossibility was established.", diagnostic)


def _select_story_beats(settings, chapters, summaries, outline, plan, brief, model, progress=None,
                        cancel_check=None, segments=None, *, search_identity=None):
    candidates = _candidate_beats_for_plan(chapters, plan)
    if _fixed_passage_choice_plan(candidates, plan, brief):
        return _select_passage_option(settings, candidates, segments or [], chapters, plan, brief, model, cancel_check)
    prepared = _prepare_story_window_search(settings, chapters, summaries, outline, plan, brief, model,
                                            segments, search_identity, cancel_check)
    if prepared is None:
        return _select_story_beats_initial(settings, chapters, summaries, outline, plan, brief, model, progress, cancel_check, segments)
    from .story_search_checkpoint import CheckpointBusy
    try:
        with prepared["checkpoint"] as checkpoint:
            return _select_story_beats_initial(settings, chapters, summaries, outline, plan, brief, model, progress,
                                               cancel_check, segments, search_checkpoint=checkpoint, prepared_search=prepared)
    except CheckpointBusy as error:
        raise StoryPlanningError("This exact canonical search is already owned by another operation.", {
            "outcome": "technical_error", "reason": "story_window_search_busy", "applied_to_timeline": False}) from error


def _select_story_beats_initial(
    settings: Settings,
    chapters: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    outline: dict[str, Any],
    plan: dict[str, Any],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    segments: list[dict[str, Any]] | None = None,
    *, search_checkpoint=None, prepared_search=None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if progress:
        progress(0.70, "Choosing the exact moments")
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    target = effective_duration_bounds(brief)["maximum_seconds"]
    candidates = _candidate_beats_for_plan(chapters, plan)
    planned_candidates = list(candidates)
    if not candidates:
        raise StoryPlanningError("Story plan did not reference any usable source material.")
    def make_precision(rows):
        return _precision_story_payload(rows, segments, chapters, precision_summaries, precision_outline,
                                        plan, brief, model, mode, target)

    if prepared_search is not None and any(search_checkpoint.completed([row["id"] for row in window])
                                           for window in prepared_search["windows"]):
        return _review_canonical_story_windows(
            settings, planned_candidates, segments, chapters, plan, brief, model, mode, cancel_check,
            prepared_search["make_precision"],
            {"version": 2, "authority": "provisional_index_retrieval_requires_complete_source_validation",
             "resumed_without_index_renomination": True}, None,
            checkpoint=search_checkpoint, windows=prepared_search["windows"])

    precision_summaries, precision_outline = summaries, outline
    payload, source_catalog = make_precision(candidates)
    retrieval = None
    if not _story_payload_fits_cap(payload, mode):
        from .story_context import build_whole_recording_index, retrieve_candidate_source
        index = build_whole_recording_index(chapters, summaries, summary_char_limit=160,
                                           key_point_char_limit=64, max_key_points=2)
        precision_summaries = [{key: row[key] for key in ("id", "summary", "key_points", "depends_on", "interpretation_status")}
                              for row in index["chapters"]]
        precision_outline = copy.deepcopy(outline)
        for key in ("premise", "audience_takeaway"):
            if isinstance(precision_outline.get(key), str):
                precision_outline[key] = _balanced_excerpt(precision_outline[key], 160)
        for row in precision_outline.get("story_arc") or []:
            if isinstance(row, dict) and isinstance(row.get("why_it_matters"), str):
                row["why_it_matters"] = _balanced_excerpt(row["why_it_matters"], 120)
        precision_outline["interpretation_status"] = "abbreviated_unverified_outline"
        planned_chapters = list(dict.fromkeys(str(value) for slot in plan["slots"]
            for key in ("chapter_ids", "required_context_chapter_ids") for value in slot.get(key, [])))
        retrieved = retrieve_candidate_source(chapters, segments or [], planned_chapters)
        canonical_by_id = {row["id"]: row for row in retrieved["beats"]}
        if any(row != canonical_by_id.get(row["id"]) for row in candidates):
            raise StoryPlanningError("Retrieved candidates differ from the unchanged canonical source.",
                {"outcome": "technical_error", "reason": "invalid_story_source_context", "applied_to_timeline": False})
        candidates, retrieval = _retrieve_story_candidates(settings, candidates, chapters, summaries, outline, plan,
                                                          brief, model, mode, make_precision, cancel_check)
        payload, source_catalog = make_precision(candidates)
    if not _story_payload_fits_cap(payload, mode):
        raise StoryPlanningError("Retrieved complete canonical source still exceeds the context budget; no source was truncated.",
                                 {"outcome": "technical_error", "reason": "story_input_context_limit", "applied_to_timeline": False})
    result = _call_ollama_story_pass(settings, payload, 300 if mode == "quality" else 220, cancel_check)
    window_recovery = (retrieval is not None and str(brief.get("goal") or "short") == "short"
                       and single_source_passage_requested(brief) and not _configured_story_roles(brief)
                       and len(plan.get("slots", [])) == 1)
    try:
        clean = _decode_proposed_precision_story_selection(result, source_catalog, candidates, segments, chapters, plan, brief, retrieval)
        budget = _single_passage_proposal_budget(clean, candidates, segments, brief) if window_recovery else None
        if budget is not None and not budget["feasible"]:
            raise StoryBudgetError("The nominated fixed source does not fit the requested duration; alternative source windows still need review.",
                {"reason": "precision_selection_budget", "outcome": "constraint_conflict", "applied_to_timeline": False,
                 "scope": "retrieved_candidate_selection", "proposal_budget": budget})
        return clean, candidates
    except StoryBudgetError as first_failure:
        if first_failure.diagnostic.get("reason") not in {"precision_no_fit", "precision_selection_budget"} or not window_recovery:
            raise
        return _review_canonical_story_windows(
            settings, planned_candidates, segments, chapters, plan, brief, model, mode, cancel_check,
            make_precision, retrieval, first_failure, checkpoint=search_checkpoint,
            windows=prepared_search["windows"] if prepared_search is not None else None)



def _reconcile_critic_actions(selection: dict[str, Any]) -> dict[str, Any]:
    """Record effective revisions after all slot and duration safeguards."""
    critic = selection.get("critic") or {}
    if "selection_before" not in critic:
        return selection  # Older cached/plugin reviews have no action baseline.
    if critic.get("action_authority") == "proposal":
        return {**selection,"critic":{**critic,"added":[],"removed":[],"unapplied_actions":[],
            "final_beat_ids":list(selection.get("keep_beat_ids") or []),
            "selection_changed_after_review":False,"unresolved_slot_indexes":[]}}
    before = set(critic["selection_before"])
    final = set(selection.get("keep_beat_ids") or [])
    accepted_additions, accepted_removals = _critic_action_sets(critic)
    added = [identifier for identifier in sorted(accepted_additions)
             if identifier not in before and identifier in final]
    removed = [identifier for identifier in sorted(accepted_removals)
               if identifier in before and identifier not in final]
    unapplied = [
        {"action": "add", "beat_id": identifier,
         "reason": "already_selected" if identifier in before else "not_kept_in_final_selection"}
        for identifier in sorted(accepted_additions) if identifier not in added
    ] + [
        {"action": "remove", "beat_id": identifier,
         "reason": "not_selected" if identifier not in before else "retained_in_final_selection"}
        for identifier in sorted(accepted_removals) if identifier not in removed
    ]
    unresolved_slots = [int(row.get("slot_index", index))
                        for index, row in enumerate(selection.get("slot_map", []))
                        if isinstance(row, dict) and not any(identifier in final for identifier in row.get("beat_ids", []))]
    unresolved_slots = sorted(set(unresolved_slots) | set(selection.get("unresolved_plan_slot_indexes") or [])
                              | set(selection.get("unresolved_context_slot_indexes") or []))
    post_review = critic.get("post_review_beat_ids", critic.get("selection_before", []))
    changed = set(post_review) != final
    verdict = critic.get("verdict")
    issues = list(critic.get("issues") or [])
    if (changed or unresolved_slots) and verdict == "pass":
        verdict = "revise"
        if changed:
            issues.append("The final selection changed after the continuity check; review it again.")
        if unresolved_slots:
            issues.append("One or more required story slots have no selected material; review the draft again.")
    return {**selection, "critic": {**critic, "added": added, "removed": removed,
                                   "unapplied_actions": unapplied, "verdict": verdict, "issues": issues,
                                   "final_beat_ids": list(selection.get("keep_beat_ids") or []),
                                   "selection_changed_after_review": changed,
                                   "unresolved_slot_indexes": unresolved_slots}}


def _critic_story_selection(
    settings: Settings,
    selection: dict[str, Any],
    candidates: list[dict[str, Any]],
    outline: dict[str, Any],
    plan: dict[str, Any],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if progress:
        progress(0.84, "Checking continuity and context")
    valid = {str(item["id"]): item for item in candidates}
    selected = [identifier for identifier in selection.get("keep_beat_ids", []) if identifier in valid]
    fixed = (selection.get("passage_option_selection") or {}).get("option") or {}
    strict_review = _evidence_bound_passage(fixed)
    exact_binding=None
    if fixed:
        from .passage_binding import validate_binding
        try: exact_binding=validate_binding(selection,segments)
        except (ValueError,TypeError,KeyError) as exc:
            raise _InvalidStorySelectionError("The fixed source text binding changed before critic review.",
                {"reason":"critic_candidate_binding_invalid","outcome":"invalid_model_output","applied_to_timeline":False}) from exc
    from .passage_binding import review_source_scope
    review_segments=review_source_scope(candidates,segments or []) if strict_review else (segments or [])
    actual_playback = _story_playback_semantic_projection(
        fixed["playback_ranges"] if fixed else merge_ranges([
            {"start":valid[v]["start"],"end":valid[v]["end"]} for v in selected],gap=0.), review_segments, brief)
    try:
        source_catalog = build_story_evidence_catalog(candidates, segments or []) if segments else []
    except (ValueError, TypeError, KeyError) as exc:
        raise _InvalidStorySelectionError("Critic source quotation ownership is invalid; no edit was applied.") from exc
    schema = copy.deepcopy(STORY_CRITIC_SCHEMA)
    identifiers = list(valid)
    for key in ("add_beat_ids", "remove_beat_ids"):
        schema["properties"][key] = {"type": "array", "uniqueItems": True, "maxItems": 8,
            "items": {"type": "string", "enum": identifiers}} if identifiers else {"type":"array", "maxItems":0}
    if source_catalog:
        evidence_schema = schema["properties"]["action_evidence"]["items"]["properties"]
        evidence_schema["beat_id"] = {"type": "string", "enum": identifiers}
        evidence_schema["source_evidence_ids"]["items"]["enum"] = [row["id"] for row in source_catalog]
    else:
        # Without canonical speech quotations this critic cannot authorize a
        # source action. Visual-only review needs its own grounded contract.
        schema["properties"]["action_evidence"] = {"type": "array", "maxItems": 0}
        for key in ("add_beat_ids", "remove_beat_ids"):
            schema["properties"][key] = {"type": "array", "maxItems": 0}
    if strict_review:
        from .critic_evidence import review_evidence_schema
        schema["properties"]["issue_evidence"] = review_evidence_schema(review_segments, actual_playback["joins"], indexed=True,
            selected_segment_ids={sid for value in selected for sid in valid[value].get("segment_ids", [])},instruction=brief.get("instruction",""),implicit_indices=True)
        schema["properties"]["action_evidence"] = {"type":"array","maxItems":0}
        schema["required"].append("issue_evidence")
        schema["properties"]["issues"]["maxItems"] = 2
        schema["properties"]["issues"]["items"]["maxLength"] = 300
        for key in ("add_beat_ids", "remove_beat_ids"):
            schema["properties"][key] = {"type": "array", "maxItems": 0}
        schema["anyOf"]=[{"properties":{"verdict":{"const":"pass"},"issues":{"maxItems":0},"issue_evidence":{"maxItems":0}}}]+[
            {"properties":{"verdict":{"const":"revise"},"issues":{"minItems":count,"maxItems":count},
                "issue_evidence":{"minItems":count,"maxItems":count}}} for count in (1,2)]
    semantic_brief = {key: copy.deepcopy(value) for key, value in brief.items()
                      if key not in {"style_profile", "edit_style"}}
    candidate_segment_ids = {str(identifier) for beat in candidates for identifier in beat.get("segment_ids", [])}
    selected_segment_ids = {str(identifier) for value in selected for identifier in valid[value].get("segment_ids", [])}
    selected_rows = [
        {"id": identifier, "start": valid[identifier]["start"], "end": valid[identifier]["end"],
         "segment_ids": list(valid[identifier].get("segment_ids", [])),
         "duration": round(float(valid[identifier]["end"]) - float(valid[identifier]["start"]), 3),
         "text": _balanced_excerpt(str(valid[identifier].get("text", "")), 520), **_on_screen_field(valid[identifier])}
        for identifier in selected
    ]
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    payload = {
        "model": model,
        "stream": False,
        "format": schema,
        "_performance_mode": mode,
        "_reject_duplicate_keys": True,
        "options": {"temperature": 0.03, "num_ctx": 12288, "num_predict": 1500},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM's continuity critic. Audit the proposed edit as if the viewer has never seen the source. "
                    "Original source_utterances and source_evidence are authoritative ASR text, not verified audio. Outline, summaries and your explanations are interpretations. "
                    "Check missing context, actual unrelated topics, changed meaning, incomplete thoughts and source chronology using the original source language. "
                    "selected.segment_ids and source_utterances.selected_in_proposal state what is actually retained. Check them before claiming an explanation was omitted. "
                    "A retained statement may still lack another prerequisite; membership is not proof of coherent context. Neighboring source is reference-only, not automatically retained. "
                    "Do not translate an ambiguous word into a new event or location; quotations, not translated paraphrases, ground a source action. "
                    "The verbatim brief.instruction and explicit_story_obligations outrank advisory style_preferences. Style hooks, clear promises, pace, preferred structure and aesthetic repetition alone "
                    "are recommendations, not mandatory reasons to delete source. Put optional improvements in style_notes, without changing add/remove IDs or creating blocking issues. "
                    "An explicit user instruction can require a hook or removal; for such an action cite the complete original relevant instruction, including negations and qualifications, in instruction_quote. "
                    "Do not infer a hard request from style guidance or a quoted/hypothetical example. Instruction substring attribution alone does not establish its intended meaning. "
                    "Candidate beats are storage groupings, not independent moments or a one-beat-per-output limit. Related complete source utterances may form one idea across beat boundaries. "
                    "Keep prerequisite context before its dependent claim and do not remove setup merely because a tighter edit would look better. Preserve source uncertainty and all negations. "
                    "actual_playback describes real source omissions; analysis-unit boundaries are not cuts. Untranscribed gaps are not verified silence. "
                    "One output or one coherent account does not require one continuous utterance unless source_continuity_required is true. "
                    "For EACH add/remove ID return exactly one action_evidence row naming that same action/beat, a real defect_kind, exact supplied source_evidence_ids and an explanation. "
                    "At least one cited ID must belong to the changed beat; off_topic/chronology_conflict also need a cited different currently selected beat. "
                    "For explicit_instruction include its exact original instruction_quote; for other defects instruction_quote must be empty. Never invent quotations or evidence IDs. "
                    "You may truthfully return revise for unresolved source uncertainty, without inventing a deletion. Return pass only if no blocking semantic issue remains; advisory style_notes may remain. "
                    "Return only " + ",".join(schema["properties"]) + ". verdict is pass or revise."
                    + _on_screen_guidance(valid.values())
                ),
            },
            {"role": "user", "content": json.dumps({
                "brief": semantic_brief, "outline": outline, "plan": plan, "selected": selected_rows,
                "style_preferences": {"authority": "advisory_only", "edit_style": brief.get("edit_style"),
                    "profile": copy.deepcopy(brief.get("style_profile") or {})},
                "explicit_story_obligations": {"roles": _configured_story_roles(brief),
                    "orders": required_story_role_orders(brief),
                    "verbatim_instruction_authoritative": True, "recognition_is_partial": True},
                "source_utterances": [{"id":str(row["id"]), "start":row["start"], "end":row["end"], "text":str(row.get("text") or ""),
                    "selected_in_proposal": str(row["id"]) in selected_segment_ids}
                    for row in (segments or []) if str(row["id"]) in candidate_segment_ids],
                "neighboring_source_utterances": neighboring_source_utterances(candidates, segments or []),
                "source_evidence": source_catalog,
                "review_contract": CRITIC_REVIEW_CONTRACT,
                "actual_playback": actual_playback,
                "candidates": [{"id": identifier, "start": row["start"], "end": row["end"],
                                "duration": round(float(row["end"]) - float(row["start"]), 3),
                                 "text": _balanced_excerpt(str(row.get("text", "")), 300),
                                  "segment_ids": list(row.get("segment_ids", [])), **_on_screen_field(row)}
                               for identifier, row in valid.items()],
            }, ensure_ascii=False)},
        ],
    }
    if strict_review:
        from .structured_schema import complete_object_union
        payload["format"] = complete_object_union(schema)
    if strict_review:
        payload["messages"][0]["content"] += (" This fixed candidate cannot be modified by the critic: add/remove/action_evidence arrays stay empty. "
            "For each blocking issue return one issue_evidence in the same array order, with original selected source_segment_ids. Do not emit issue_index; the app owns indices. "
            "A join_context defect must cite its computed join_id and exactly its supplied left/right segment IDs. "
            "For missing_context, source_segment_ids cites the SELECTED claim that depends on the missing prerequisite; "
            "missing_context_segment_ids cites the actually UNSELECTED prerequisite. These are disjoint source roles. "
            "Other kinds use empty missing context and null join. "
            "Only explicit_instruction copies the WHOLE original instruction; every other kind uses instruction_quote=\"\". Never calculate or assign timestamps to a reason yourself. "
            "If ASR meaning is uncertain use source_text_uncertainty, not an invented event. Source attribution does not establish semantic truth. ")
        data=json.loads(payload["messages"][1]["content"])
        for key in ("outline","plan","candidates","source_evidence","neighboring_source_utterances"):
            data.pop(key,None)
        data["selected"]=[{k:r[k] for k in ("id","start","end","segment_ids","duration")} for r in selected_rows]
        data["source_utterances"]=[{k:r[k] for k in ("id","start","end","text")}|{"selected_in_proposal":True} for r in segments if r["id"] in selected_segment_ids]
        data["reference_source_utterances"]=[{k:r[k] for k in ("id","start","end","text")} for r in review_segments if r["id"] not in selected_segment_ids]
        data["reference_scope"]="retrieved domain and explicit context neighbors only; unseen prerequisites remain unverified"
        data["fixed_passage_candidate"]={"candidate_id":fixed["id"],"source_binding_fingerprint":exact_binding["fingerprint"],"segment_ids":list(fixed["segment_ids"])}
        payload["messages"][1]["content"]=json.dumps(data,ensure_ascii=False)
    result = _call_ollama_story_pass(settings, payload, 220, cancel_check)
    action_requested = isinstance(result, dict) and any(result.get(key) for key in ("add_beat_ids", "remove_beat_ids"))
    def invalid_review(message):
        if action_requested or strict_review:
            raise _InvalidStorySelectionError(message, {"reason":"critic_action_evidence_invalid",
                "outcome":"invalid_model_output", "applied_to_timeline":False, "stage":"critic"})
        raise StoryPlanningError(message)
    required = {"verdict", "add_beat_ids", "remove_beat_ids", "issues", "summary"}
    if not isinstance(result, dict) or not required.issubset(result):
        invalid_review("Story critic returned an incomplete review; no continuity pass was verified.")
    if (not isinstance(result["verdict"], str) or result["verdict"] not in {"pass", "revise"}
            or not isinstance(result["summary"], str)):
        invalid_review("Story critic returned an invalid review verdict or summary.")
    for key in ("add_beat_ids", "remove_beat_ids", "issues"):
        if not isinstance(result[key], list) or any(not isinstance(value, str) for value in result[key]):
            invalid_review("Story critic returned invalid review lists.")
    if any(identifier not in valid for key in ("add_beat_ids", "remove_beat_ids") for identifier in result[key]):
        invalid_review("Story critic requested a change to an unknown story beat.")
    style_notes = result.get("style_notes", [])
    if not isinstance(style_notes, list) or any(not isinstance(value, str) for value in style_notes):
        invalid_review("Story critic returned invalid advisory style notes.")
    additions = list(dict.fromkeys(result["add_beat_ids"]))
    removals = set(result["remove_beat_ids"])
    if set(additions) & removals or (result["verdict"] == "pass" and (
        additions or removals or any(issue.strip() for issue in result["issues"])
    )):
        invalid_review("Story critic returned contradictory changes or unresolved issues with a pass.")
    issue_proof = []
    if strict_review:
        from .critic_evidence import validate_review_evidence
        try:
            if additions or removals or result.get("action_evidence",[]) or (result["verdict"]=="revise" and not result["issues"]):
                raise ValueError("A fixed critic needs attributed issues, not edit actions or an empty refusal.")
            evidence=result.get("issue_evidence",[])
            if not isinstance(evidence,list) or any(not isinstance(row,dict) or "issue_index" in row for row in evidence):
                raise ValueError("Critic issue indices are application-owned.")
            issue_proof = validate_review_evidence([{**row,"issue_index":index} for index,row in enumerate(evidence)], review_segments,
                selected_segment_ids, actual_playback["joins"], brief.get("instruction", ""),
                issue_count=len(result["issues"]), indexed=True)
        except (ValueError,TypeError,KeyError) as exc:
            raise _InvalidStorySelectionError("Critic issue evidence is invalid; source suitability remains unverified.",
                {"reason":"critic_issue_evidence_invalid","outcome":"invalid_model_output","attribution_error":str(exc),"applied_to_timeline":False}) from exc
    from .critic_evidence import validate_critic_actions
    attribution_error = None
    try:
        grounded_actions = validate_critic_actions(result, source_catalog, candidates, segments or [], brief, selected)
    except (ValueError, TypeError, KeyError) as exc:
        # A known-source proposal with missing citations is unverified advice.
        # The existing final review sees the failure and the complete original
        # evidence; it must explicitly adjudicate, rather than apply, it.
        grounded_actions = []
        attribution_error = str(exc)
    proposed = [identifier for identifier in selected if identifier not in removals]
    for identifier in additions:
        if identifier not in proposed:
            proposed.append(identifier)
    proposed = sorted(dict.fromkeys(proposed), key=lambda identifier: float(valid[identifier]["start"]))
    output = dict(selection)
    output["keep_beat_ids"] = list(selected)
    if exact_binding:
        output["passage_option_selection"]={**selection["passage_option_selection"],"source_binding":exact_binding}
    output["critic"] = {
        "verdict": result["verdict"],
        "issues": [str(value)[:320] for value in result.get("issues", []) if str(value).strip()][:8],
        "summary": str(result.get("summary") or "")[:600],
        "style_notes": [value[:240] for value in style_notes][:4],
        "grounded_actions": grounded_actions,
        "issue_evidence": issue_proof,
        "raw_action_evidence": copy.deepcopy(result.get("action_evidence", [])),
        "action_evidence_error": attribution_error,
        "action_grounding_contract": CRITIC_REVIEW_CONTRACT,
        "action_attribution_verified": attribution_error is None,
        "action_semantics_verified": False,
        "action_authority": "proposal",
        "proposed_beat_ids": proposed,
        "selection_before": selected,
        "reviewed_beat_ids": list(selected),
        "post_review_beat_ids": list(selected),
        "review_verdict": result["verdict"],
        "requested_added": additions,
        "requested_removed": sorted(removals),
    }
    return _reconcile_critic_actions(output)


def _extractive_rough_cut_decision(
    selection: dict[str, Any], candidates: list[dict[str, Any]], segments: list[dict[str, Any]],
    chapters: list[dict[str, Any]], plan: dict[str, Any], brief: dict[str, Any], failure: StoryBudgetError,
) -> dict[str, Any] | None:
    """Retain the fixed source after a model failure without claiming story approval."""
    reason = failure.diagnostic.get("reason")
    revision = failure.diagnostic.get("semantic_revision")
    if (brief.get("allow_extractive_rough_cut") is not True or str(brief.get("goal") or "short") != "short"
            or reason not in {"planner_no_fit", "invalid_semantic_mapping", "invalid_semantic_revision",
                              "semantic_revision_output_limit", "required_selection_exceeds_target", "target_underfill"}
            or not isinstance(revision, dict) or type(revision.get("attempts")) is not int or revision["attempts"] != 1):
        return None
    critic = selection.get("critic")
    if not isinstance(critic, dict) or critic.get("verdict") not in {"pass", "revise"}:
        return None
    if any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] for row in candidates):
        return None
    by_id = {row["id"]: row for row in candidates}
    if len(by_id) != len(candidates):
        return None
    action_fields = ["requested_added", "requested_removed"]
    if critic.get("action_authority") == "final":
        action_fields += ["accepted_added", "accepted_removed"]
    raw_fields = [selection.get("keep_beat_ids")] + [critic.get(key) for key in action_fields]
    if any(not isinstance(values, list) or any(not isinstance(value, str) or value not in by_id for value in values)
           or len(values) != len(set(values)) for values in raw_fields):
        return None
    accepted_additions, accepted_removals = _critic_action_sets(critic)
    fields = [selection["keep_beat_ids"], sorted(accepted_additions), sorted(accepted_removals)]
    try:
        build_story_evidence_catalog(candidates, segments)
    except (ValueError, TypeError, KeyError):
        return None
    current, added, removed = fields
    rejected = set(removed)
    fixed = sorted((set(current) | set(added)) - rejected, key=lambda value: float(by_id[value]["start"]))
    if not fixed or not _story_units_complete(fixed, candidates, segments):
        return None
    try:
        source_spans = build_source_span_constraints(candidates, segments,
            selected_beat_ids=fixed, rejected_beat_ids=sorted(rejected))
    except (ValueError, TypeError, KeyError):
        return None
    duration = max([float(row["end"]) for row in segments] or [0.0])
    bounds = effective_duration_bounds(brief, duration)
    target = bounds["maximum_seconds"]
    duration_mode = str(brief.get("duration_mode") or "target")
    minimum_target = bounds["minimum_seconds"]
    cost = _story_selection_cost(fixed, candidates, segments, brief)
    diagnostic = {"kind": "story_budget", "scope": "current_critic_allowed_source", "target_seconds": target,
        "minimum_target_seconds": round(minimum_target, 3), "policy_version": cost["policy_version"],
        "required_policy_minimum_seconds": cost["minimum_safe_seconds"],
        "available_complete_source_upper_bound_seconds": cost["approved_seconds"],
        "current_source_target_interval": _source_selection_target_interval(cost, duration, duration_mode, brief),
        "failed_generation_diagnostic": copy.deepcopy(failure.diagnostic), "applied_to_timeline": False}

    def refuse(why: str, text: str) -> None:
        raise StoryBudgetError(text + " No new draft was applied; the existing edit was kept.", {**diagnostic, "reason": why})

    for key, domain, retained in (
        ("required_context_beat_ids", set(by_id), set(fixed)),
        ("required_context_segment_ids", {str(row["id"]) for row in segments}, set(source_spans["segment_ids"])),
    ):
        prerequisites = selection.get(key, [])
        if (not isinstance(prerequisites, list) or any(not isinstance(value, str) or value not in domain for value in prerequisites)
                or len(prerequisites) != len(set(prerequisites))):
            return None
        if not set(prerequisites) <= retained:
            refuse("extractive_required_context_missing", "Mandatory source context lies outside the fixed selected source; an extractive rough cut cannot add excluded or unselected material.")
    slots = plan.get("slots")
    if not isinstance(slots, list) or not slots:
        return None
    if (not isinstance(chapters, list) or any(not isinstance(chapter, dict) or not isinstance(chapter.get("id"), str)
            or not isinstance(chapter.get("beats"), list)
            or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in chapter["beats"])
            for chapter in chapters)):
        return None
    chapter_members = {str(chapter["id"]): {str(row["id"]) for row in chapter.get("beats", [])}
                       for chapter in chapters}
    for slot in slots:
        if (not isinstance(slot, dict) or not isinstance(slot.get("chapter_ids"), list) or not slot["chapter_ids"]
                or not isinstance(slot.get("required_context_chapter_ids", []), list)
                or any(not isinstance(value, str) or value not in chapter_members
                       for value in slot["chapter_ids"] + slot.get("required_context_chapter_ids", []))):
            return None
        primary = set().union(*(chapter_members.get(str(value), set()) for value in slot.get("chapter_ids", [])))
        context = [chapter_members.get(str(value), set()) for value in slot.get("required_context_chapter_ids", [])]
        if not primary.intersection(fixed) or any(not group.intersection(fixed) for group in context):
            refuse("extractive_required_context_missing", "The fixed source lacks mandatory prerequisite context; an extractive rough cut cannot restore excluded or unselected material.")
    if not cost["fits_target"]:
        refuse("extractive_source_exceeds_target", f"The unchanged complete source needs at least {cost['minimum_safe_seconds']:.2f}s under the safe speech policy for a {target:g}s target. A shorter extractive cut would remove required utterance speech.")
    if cost["approved_seconds"] + .05 + 1e-9 < minimum_target:
        interval = diagnostic["current_source_target_interval"]
        refuse("allowed_source_below_target_minimum", f"The fixed critic-allowed source supplies at most {cost['approved_seconds']:.2f}s, below the {minimum_target:.2f}s target band. Its numeric effective-target interval is {interval['minimum_seconds']:.2f}–{interval['maximum_seconds']:.2f}s, subject to frame validation; this does not establish semantic approval.")
    source_ids = set(source_spans["segment_ids"])
    ordered_ids = [str(row["id"]) for row in segments]
    ranges = [{"start": float(by_id[value]["start"]), "end": float(by_id[value]["end"]), "beat_id": value} for value in fixed]
    rejected_ranges = [{"start": float(by_id[value]["start"]), "end": float(by_id[value]["end"]), "beat_id": value}
                       for value in sorted(rejected, key=lambda value: float(by_id[value]["start"]))]
    return {"editorial_authority": EXTRACTIVE_ROUGH_CUT_AUTHORITY, "semantic_review_status": "not_model_reviewed",
        "generative_approved": False, "review_required": True, "title": "EXTRACTIVE ROUGH CUT",
        "summary": whole_utterance_story_summary(source_spans), "summary_source": SOURCE_SPAN_SUMMARY_SOURCE,
        "keep_ids": [value for value in ordered_ids if value in source_ids],
        "remove_ids": [value for value in ordered_ids if value not in source_ids], "highlight_ids": [],
        "opening_id": source_spans["segment_ids"][0], "closing_id": source_spans["segment_ids"][-1],
        "story_beat_ids": fixed, "story_ranges": ranges, "rejected_beat_ids": sorted(rejected),
        "rejected_segment_ids": [str(value) for identifier in rejected for value in by_id[identifier].get("segment_ids", [])],
        "rejected_story_ranges": rejected_ranges,
        "extractive_requirements": {"fixed_beat_ids": fixed, "critic_requested_beat_ids": [value for value in fixed if value in added],
            "source_span_policy_version": SOURCE_SPAN_POLICY_VERSION, "source_span_constraints": source_spans,
            "duration_mode": duration_mode,
            "cost": cost, "failed_generation_diagnostic": copy.deepcopy(failure.diagnostic),
            "original_critic": copy.deepcopy(critic), "semantic_review_status": "not_model_reviewed", "review_required": True,
            "instruction_coverage": "unverified" if str(brief.get("instruction") or "").strip() else "not_requested",
            "required_context_beat_ids": copy.deepcopy(selection.get("required_context_beat_ids", [])),
            "required_context_segment_ids": copy.deepcopy(selection.get("required_context_segment_ids", []))}}


def _story_decision_from_beats(result: dict[str, Any] | None, beats: list[dict[str, Any]], segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not result or not beats:
        return None
    by_id = {beat["id"]: beat for beat in beats}
    valid = set(by_id)

    def beat_ids(key: str, limit: int | None = None) -> list[str]:
        values = result.get(key, [])
        if not isinstance(values, list):
            return []
        output: list[str] = []
        for value in values:
            identifier = str(value)
            if identifier in valid and identifier not in output:
                output.append(identifier)
            if limit and len(output) >= limit:
                break
        return output

    accepted_additions, accepted_removals = _critic_action_sets(result.get("critic") or {})
    rejected = sorted({str(identifier) for identifier in accepted_removals
                       if str(identifier) in valid}, key=lambda identifier: float(by_id[identifier]["start"]))
    critic_requested = {
        str(identifier) for identifier in accepted_additions
        if str(identifier) in valid and str(identifier) not in rejected
    }
    keep_beats = list(dict.fromkeys(
        [identifier for identifier in beat_ids("keep_beat_ids") if identifier not in rejected]
        + sorted(critic_requested, key=lambda identifier: float(by_id[identifier]["start"]))
    ))
    if not keep_beats:
        return None
    keep_beats = sorted(keep_beats, key=lambda identifier: float(by_id[identifier]["start"]))
    reconciled = _reconcile_critic_actions({**result, "keep_beat_ids": keep_beats})
    final_critic = reconciled.get("critic") or {}
    unresolved_slots = sorted({
        int(row.get("slot_index", index))
        for index, row in enumerate(result.get("slot_map", []))
        if isinstance(row, dict) and not any(str(identifier) in keep_beats for identifier in row.get("beat_ids", []))
    } | {int(index) for index in final_critic.get("unresolved_slot_indexes", [])}
      | {int(index) for index in result.get("unresolved_context_slot_indexes", [])})
    unresolved_slots = sorted(set(unresolved_slots) | {int(index) for index in result.get("unresolved_plan_slot_indexes", [])})
    highlights = [identifier for identifier in beat_ids("highlight_beat_ids", 8) if identifier in keep_beats]
    opening, closing = keep_beats[0], keep_beats[-1]
    selected_segment_ids = {segment_id for identifier in keep_beats for segment_id in by_id[identifier]["segment_ids"]}
    all_segment_ids = [str(item["id"]) for item in segments]

    def representative(beat_id: str, first: bool = False, last: bool = False) -> str | None:
        ids = [str(item) for item in by_id.get(beat_id, {}).get("segment_ids", [])]
        if not ids:
            return None
        if first:
            return ids[0]
        if last:
            return ids[-1]
        segment_by_id = {str(item["id"]): item for item in segments}
        return max(ids, key=lambda identifier: float(segment_by_id.get(identifier, {}).get("editorial_score", 0.0)))

    highlight_segments = [identifier for identifier in (representative(beat_id) for beat_id in highlights) if identifier]
    raw_title = result.get("title")
    # Source IDs establish selection provenance, not support for a generated
    # claim. Until titles have an independent review, display a neutral label.
    title = "CUTROOM story"
    title_ids = beat_ids("title_beat_ids")
    title_reason = "model_suggestion" if isinstance(raw_title, str) and raw_title.strip() else "missing_title"
    if "title_beat_ids" in result and set(title_ids) != set(keep_beats):
        title, title_reason = "CUTROOM story", "selection_changed"
    summary = str(result.get("summary") or "A coherent story selected from the full recording.")[:500]
    summary_source = result.get("summary_source") or "unverified_interpretation"
    source_spans = None
    continuous_playback = None
    if result.get("evidence_policy_version") == EVIDENCE_POLICY_VERSION:
        try:
            proof = validate_story_evidence(
                result.get("slot_map"), beats, segments,
                selected_beat_ids=keep_beats, rejected_beat_ids=rejected,
            )
            if proof != result.get("evidence_proof"):
                return None
            if result.get("source_span_policy_version") != SOURCE_SPAN_POLICY_VERSION:
                return None
            source_spans = validate_source_span_constraints(
                result.get("source_span_constraints"), beats, segments,
                selected_beat_ids=keep_beats, rejected_beat_ids=rejected)
            summary = whole_utterance_story_summary(source_spans)
            summary_source = SOURCE_SPAN_SUMMARY_SOURCE
        except (ValueError, TypeError, KeyError):
            return None
    fixed = (result.get("passage_option_selection") or {}).get("option") or {}
    if fixed.get("explicit_source_continuity_requested"):
        try:
            continuous_playback = continuous_source_playback(beats, segments, keep_beats)
            if (fixed.get("beat_ids") != keep_beats
                    or fixed.get("continuous_source_playback") != continuous_playback
                    or fixed.get("playback_ranges") != continuous_playback["playback_ranges"]):
                return None
        except (ValueError, TypeError, KeyError):
            return None
    return {
        "editorial_authority": "generative_story" if source_spans is not None else "unverified_story",
        "keep_ids": [identifier for identifier in all_segment_ids if identifier in selected_segment_ids],
        "remove_ids": [identifier for identifier in all_segment_ids if identifier not in selected_segment_ids],
        "highlight_ids": highlight_segments,
        "opening_id": representative(opening, first=True) if opening in valid else representative(keep_beats[0], first=True),
        "closing_id": representative(closing, last=True) if closing in valid else representative(keep_beats[-1], last=True),
        "title": title,
        "title_review": {"status": "unverified", "reason": title_reason,
                         "selected_beat_ids": list(keep_beats), "title_beat_ids": title_ids},
        "summary": summary,
        "summary_source": summary_source,
        "story_beat_ids": keep_beats,
        "story_requirements": {
            "required_beat_ids": list(keep_beats),
            "critic_requested_beat_ids": [identifier for identifier in keep_beats if identifier in critic_requested],
            "unresolved_slot_indexes": unresolved_slots,
            "unapplied_critic_actions": len(final_critic.get("unapplied_actions") or []),
            "semantic_mapping_verified": result.get("semantic_mapping_verified") is True,
            "semantic_review_status": result.get("semantic_review_status"),
            "evidence_policy_version": result.get("evidence_policy_version"),
            "evidence_proof": copy.deepcopy(result.get("evidence_proof")),
            "source_span_policy_version": SOURCE_SPAN_POLICY_VERSION if source_spans is not None else None,
            "source_span_constraints": copy.deepcopy(source_spans),
            **({"continuous_source_playback": continuous_playback} if continuous_playback else {}),
            "required_context_beat_ids": copy.deepcopy(result.get("required_context_beat_ids", [])),
            "required_context_segment_ids": copy.deepcopy(result.get("required_context_segment_ids", [])),
            "slot_map": copy.deepcopy(result.get("slot_map") or []),
            "semantic_revision": copy.deepcopy(result.get("semantic_revision")),
        },
        "rejected_beat_ids": rejected,
        "rejected_segment_ids": [identifier for identifier in all_segment_ids
                                 if any(identifier in by_id[beat_id].get("segment_ids", []) for beat_id in rejected)],
        "rejected_story_ranges": [{"start": float(by_id[identifier]["start"]),
                                    "end": float(by_id[identifier]["end"]), "beat_id": identifier}
                                   for identifier in rejected],
        "story_ranges": [
            {"start": float(by_id[identifier]["start"]), "end": float(by_id[identifier]["end"]), "beat_id": identifier,
             **({key:by_id[identifier][key] for key in ("entry_policy","entry_owner_id")}
                if by_id[identifier].get("entry_owner_id") else {})}
            for identifier in keep_beats
        ],
    }


def deterministic_story_edit(beats: list[dict[str, Any]], segments: list[dict[str, Any]], brief: dict[str, Any]) -> dict[str, Any]:
    if not beats:
        return deterministic_edit(segments, {**brief, "goal": "clean"})
    target = effective_duration_bounds(brief)["maximum_seconds"]
    raw_budget = target * (1.08 if target <= 90 else 1.05)
    bucket_count = 5 if target <= 75 else 9 if target <= 210 else 12
    selected: list[dict[str, Any]] = []
    represented: set[int] = set()

    first_band = [beat for beat in beats if float(beat["position"]) <= 0.22]
    if first_band:
        selected.append(max(first_band, key=lambda beat: float(beat["editorial_score"]) + (0.35 if beat.get("role_hint") == "hook" else 0.0)))
    total = sum(float(beat["duration"]) for beat in selected)
    if selected:
        represented.add(min(bucket_count - 1, int(float(selected[0]["position"]) * bucket_count)))

    candidates = [beat for beat in beats if beat not in selected]
    while candidates and total < raw_budget * 0.92:
        def value(beat: dict[str, Any]) -> float:
            bucket = min(bucket_count - 1, int(float(beat["position"]) * bucket_count))
            coverage = 0.28 if bucket not in represented else 0.0
            role_bonus = 0.22 if beat.get("role_hint") in {"example", "result", "conclusion"} else 0.0
            return float(beat["editorial_score"]) + coverage + role_bonus + float(beat.get("novelty", 0.0)) * 0.08
        beat = max(candidates, key=value)
        candidates.remove(beat)
        if total + float(beat["duration"]) > raw_budget * 1.18 and selected:
            continue
        selected.append(beat)
        total += float(beat["duration"])
        represented.add(min(bucket_count - 1, int(float(beat["position"]) * bucket_count)))

    # Prefer a real ending when there is room.
    late = [beat for beat in beats if float(beat["position"]) >= 0.72 and beat not in selected]
    if late:
        ending = max(late, key=lambda beat: float(beat["editorial_score"]) + (0.35 if beat.get("role_hint") == "conclusion" else 0.0))
        if total + float(ending["duration"]) <= raw_budget * 1.18:
            selected.append(ending)
    selected = sorted(selected, key=lambda beat: float(beat["start"]))
    fake_result = {
        "keep_beat_ids": [beat["id"] for beat in selected],
        "highlight_beat_ids": [beat["id"] for beat in sorted(selected, key=lambda beat: float(beat["editorial_score"]), reverse=True)[:6]],
        "opening_beat_id": selected[0]["id"] if selected else None,
        "closing_beat_id": selected[-1]["id"] if selected else None,
        "title": "CUTROOM first draft",
        "summary": "Selected a coherent set of ideas from across the full recording, then removed dead air and retakes inside them.",
    }
    return _story_decision_from_beats(fake_result, beats, segments) or deterministic_edit(segments, {**brief, "goal": "clean"})


def _story_cache_is_reusable(
    story_cache: Any,
    expected_fingerprint: str,
    model: str,
    chapters: list[dict[str, Any]],
) -> bool:
    """Validate persisted model output before it can bypass Story AI passes."""

    try:
        if not isinstance(story_cache, dict):
            return False
        expected_ids = [str(chapter["id"]) for chapter in chapters]
        valid_ids = set(expected_ids)
        if len(valid_ids) != len(expected_ids):
            return False
        if story_cache.get("cache_fingerprint") != expected_fingerprint:
            return False
        if story_cache.get("cache_pipeline") != STORY_CACHE_PIPELINE:
            return False
        if story_cache.get("model") != model:
            return False
        if type(story_cache.get("chapter_count")) is not int or story_cache["chapter_count"] != len(chapters):
            return False

        cached_chapters = story_cache.get("chapters")
        if not isinstance(cached_chapters, list) or len(cached_chapters) != len(chapters):
            return False
        cached_chapter_ids = [
            row.get("id") if isinstance(row, dict) and isinstance(row.get("id"), str) else None
            for row in cached_chapters
        ]
        if cached_chapter_ids != expected_ids or len(set(cached_chapter_ids)) != len(expected_ids):
            return False

        summaries = story_cache.get("chapter_summaries")
        if not isinstance(summaries, list) or len(summaries) != len(chapters):
            return False
        summary_ids = [
            row.get("id") if isinstance(row, dict) and isinstance(row.get("id"), str) else None
            for row in summaries
        ]
        if summary_ids != expected_ids or len(set(summary_ids)) != len(expected_ids):
            return False
        beat_ids_by_chapter = {
            str(chapter["id"]): {
                str(beat["id"])
                for beat in chapter.get("beats", [])
                if isinstance(beat, dict) and "id" in beat
            }
            for chapter in chapters
        }
        list_fields = ("key_points", "key_beat_ids", "depends_on", "unresolved_questions")
        valid_roles = {"setup", "problem", "development", "example", "turn", "result", "conclusion", "other"}
        for row in summaries:
            if not isinstance(row, dict):
                return False
            chapter_id = row["id"]
            if not isinstance(row.get("title"), str) or not isinstance(row.get("summary"), str) or not row["summary"].strip():
                return False
            if row.get("role") not in valid_roles or row.get("summary_source") not in {"model", "model_retry", "extractive"}:
                return False
            if any(not isinstance(row.get(field), list) for field in list_fields):
                return False
            if any(not all(isinstance(value, str) for value in row[field]) for field in list_fields):
                return False
            key_beat_ids = row["key_beat_ids"]
            if not key_beat_ids or not set(key_beat_ids) <= beat_ids_by_chapter.get(chapter_id, set()):
                return False
            if not set(row["depends_on"]) <= (valid_ids - {chapter_id}):
                return False

        outline = story_cache.get("outline")
        if not isinstance(outline, dict):
            return False
        if not isinstance(outline.get("premise"), str) or not isinstance(outline.get("audience_takeaway"), str):
            return False
        story_arc = outline.get("story_arc")
        if not isinstance(story_arc, list) or not story_arc:
            return False
        arc_ids: list[str] = []
        for row in story_arc:
            if not isinstance(row, dict):
                return False
            chapter_id = row.get("chapter_id")
            if not isinstance(chapter_id, str) or chapter_id not in valid_ids:
                return False
            if not isinstance(row.get("function"), str) or not isinstance(row.get("why_it_matters"), str):
                return False
            arc_ids.append(chapter_id)
        if len(arc_ids) != len(set(arc_ids)):
            return False
        for field in ("must_keep_chapter_ids", "optional_chapter_ids"):
            values = outline.get(field)
            if not isinstance(values, list) or not all(isinstance(value, str) and value in valid_ids for value in values):
                return False
        dependencies = outline.get("dependency_pairs")
        if not isinstance(dependencies, list):
            return False
        for row in dependencies:
            if not isinstance(row, dict):
                return False
            before, after, reason = row.get("before"), row.get("after"), row.get("reason")
            if not isinstance(before, str) or not isinstance(after, str) or not isinstance(reason, str):
                return False
            if before not in valid_ids or after not in valid_ids:
                return False
        return True
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def _story_understanding_path(settings, fingerprint):
    from pathlib import Path
    directory = getattr(settings, "cache_dir", None)
    if directory is None or not isinstance(fingerprint, str) or not re.fullmatch(r"(?:[0-9a-f]{32}|[0-9a-f]{64})", fingerprint):
        return None
    return Path(directory) / "story-understanding" / (fingerprint + ".json")


def _load_story_understanding(settings, fingerprint, model, chapters):
    path = _story_understanding_path(settings, fingerprint)
    if path is None:
        return None
    try:
        if path.stat().st_size > 8 * 1024**2:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return value if _story_cache_is_reusable(value, fingerprint, model, chapters) else None


def _save_story_understanding(settings, fingerprint, model, chapters, summaries, outline, cancel_check, plan=None):
    """Checkpoint validated understanding without granting editorial authority."""
    path = _story_understanding_path(settings, fingerprint)
    if path is None:
        return
    value = {"cache_fingerprint": fingerprint, "cache_pipeline": STORY_CACHE_PIPELINE, "model": model,
             "chapter_count": len(chapters),
             "chapters": [{**{key: row[key] for key in ("id", "start", "end", "duration")},
                            "beat_ids": [beat["id"] for beat in row["beats"]]} for row in chapters],
             "chapter_summaries": copy.deepcopy(summaries), "outline": copy.deepcopy(outline),
             "authority": "unverified_understanding_only_no_edit_or_semantic_approval"}
    if plan is not None:
        value["last_proposed_plan"] = copy.deepcopy(plan)  # Evidence only; never bypass fresh plan validation.
    if not _story_cache_is_reusable(value, fingerprint, model, chapters):
        return
    _check_cancelled(cancel_check)
    from .utils import atomic_write_json
    try:
        atomic_write_json(path, value)
    except OSError:
        logging.getLogger(__name__).warning("Story understanding could not be checkpointed locally.")


def _resumable_story_plan(settings, story_cache, chapters, summaries, outline, brief, model, segments,
                          search_identity, cancel_check):
    """Reuse only a validated nomination with matching completed negative windows."""
    if not search_identity or not isinstance(story_cache, dict):
        return None
    plan = story_cache.get("last_proposed_plan")
    if (not isinstance(plan, dict) or not isinstance(plan.get("slots"), list) or len(plan["slots"]) != 1
            or not isinstance(plan["slots"][0], dict) or plan["slots"][0].get("purpose") != SINGLE_PASSAGE_PURPOSE):
        return None
    plan = _candidate_local_context_plan(plan, brief)
    row = plan["slots"][0]
    desired = row.get("desired_seconds")
    if (isinstance(desired, bool) or not isinstance(desired, (float, int)) or not math.isfinite(desired)
            or not 0 < desired <= effective_duration_bounds(brief)["maximum_seconds"]):
        return None
    capacity = _single_passage_plan_capacity(plan, chapters, segments, brief)
    if capacity and capacity["optimistic_upper_bound_seconds"] + .05 < capacity["required_target_minimum_seconds"]:
        return None  # A saved nomination cannot bypass the current numeric invariant.
    from .story_search_checkpoint import CheckpointBusy
    try:
        _validate_configured_story_roles(plan, brief)
        prepared = _prepare_story_window_search(settings, chapters, summaries, outline, plan, brief, model,
                                                segments, search_identity, cancel_check)
        if prepared is None or not prepared["checkpoint"].path.is_file():
            return None
        with prepared["checkpoint"] as checkpoint:
            reusable = any(_cached_story_window_trial(checkpoint.completed([row["id"] for row in window]), window, plan)
                           for window in prepared["windows"])
        return copy.deepcopy(plan) if reusable else None
    except CheckpointBusy:
        raise
    except (OSError, TypeError, ValueError, KeyError, StoryPlanningError):
        return None


@_with_stable_story_context
def hierarchical_story_edit(
    beats: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    settings: Settings,
    brief: dict[str, Any],
    progress: Callable[[float, str], None] | None = None,
    story_cache: dict[str, Any] | None = None,
    cancel_check: Callable[[], None] | None = None,
    *,
    visual_key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _check_cancelled(cancel_check)
    brief = enrich_brief_with_style(brief)
    instruction_contract = assert_instruction_contract(brief)
    status = _ready_story_model_status(settings, brief)
    if status.get("using_fallback") and progress:
        progress(0.01, status["message"])
    model = str(status["selected_model"])
    from .story_search_identity import current_story_search_source, local_story_model_identity
    source_binding = current_story_search_source()
    immutable_model = local_story_model_identity(settings, model) if source_binding else None
    search_identity = ({"source": source_binding, "model": immutable_model} if immutable_model else None)
    if immutable_model:
        status["model_identity"] = copy.deepcopy(immutable_model)
    expected_cache_fingerprint = story_cache_fingerprint(segments, brief, model, visual_key)
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    max_chapters = 8 if mode == "lite" else 16 if mode == "quality" else 12
    chapters = build_story_chapters(beats, max_chapters=max_chapters)
    if len(chapters) < 2:
        # Very short sources do not need multiple chapter calls, but still require a real model pass.
        chapters = build_story_chapters(beats, max_chapters=4)
    if not _story_cache_is_reusable(story_cache, expected_cache_fingerprint, model, chapters):
        story_cache = _load_story_understanding(settings, expected_cache_fingerprint, model, chapters)
    reusable_cache = _story_cache_is_reusable(
        story_cache,
        expected_cache_fingerprint,
        model,
        chapters,
    )
    if reusable_cache:
        _check_cancelled(cancel_check)
        if progress:
            progress(0.32, "Reusing chapter understanding")
        summaries = [dict(item) for item in story_cache["chapter_summaries"]]
        outline = dict(story_cache["outline"])
    else:
        _check_cancelled(cancel_check)
        summaries = _summarize_story_chapters(
            settings,
            chapters,
            brief,
            model,
            progress,
            cancel_check,
        )
        _check_cancelled(cancel_check)
        outline = _build_global_outline(settings, summaries, brief, model, progress, cancel_check, chapters, segments)
        _save_story_understanding(settings, expected_cache_fingerprint, model, chapters, summaries, outline, cancel_check)
    _check_cancelled(cancel_check)
    plan = _resumable_story_plan(settings, story_cache if reusable_cache else None, chapters, summaries, outline,
                                 brief, model, segments, search_identity, cancel_check)
    if plan is None:
        plan = _build_story_plan(settings, summaries, outline, brief, model, progress, cancel_check, segments, chapters)
        _save_story_understanding(settings, expected_cache_fingerprint, model, chapters, summaries, outline, cancel_check, plan)
    elif progress:
        progress(0.69, "Resuming the remaining canonical source windows")
    search_options = {"search_identity": search_identity} if search_identity else {}
    _check_cancelled(cancel_check)
    if cancel_check is None:
        selection, candidates = _select_story_beats(
            settings,
            chapters,
            summaries,
            outline,
            plan,
            brief,
            model,
            progress,
            None,
            segments,
            **search_options,
        )
    else:
        selection, candidates = _select_story_beats(
            settings,
            chapters,
            summaries,
            outline,
            plan,
            brief,
            model,
            progress,
            cancel_check,
            segments,
            **search_options,
        )
    semantic_target = str(brief.get("goal") or "short") == "short"
    precision_selection = copy.deepcopy(selection)
    if not semantic_target:
        selection = _fit_story_selection_to_budget(selection, candidates, plan,
                                                   float(brief.get("target_duration") or 60), chapters)
    _check_cancelled(cancel_check)
    try:
        if cancel_check is None:
            reviewed = _critic_story_selection(
                settings,
                selection,
                candidates,
                outline,
                plan,
                brief,
                model,
                progress,
                None,
                segments,
            )
        else:
            reviewed = _critic_story_selection(
                settings,
                selection,
                candidates,
                outline,
                plan,
                brief,
                model,
                progress,
                cancel_check,
                segments,
            )
    except _InvalidStorySelectionError:
        raise
    except StoryPlanningError as exc:
        # The critic is a safety review, not the source of the edit. A malformed
        # critic response must not erase a complete, slot-validated selection.
        reviewed = dict(selection)
        reviewed["critic"] = {"verdict": "skipped", "issues": [str(exc)], "summary": "Selection kept after critic response failure."}
    extractive_decision = None
    if semantic_target:
        try:
            reviewed = _review_story_target_budget(settings, reviewed, candidates, segments, chapters,
                                                    outline, plan, brief, model, cancel_check)
        except StoryBudgetError as exc:
            _check_cancelled(cancel_check)
            extractive_decision = _extractive_rough_cut_decision(
                reviewed, candidates, segments, chapters, plan, brief, exc)
            if extractive_decision is None:
                raise
    else:
        reviewed = _fit_story_selection_to_budget(reviewed, candidates, plan,
                                                  float(brief.get("target_duration") or 60), chapters)
        reviewed = _verify_non_short_story_evidence(reviewed, precision_selection, candidates, segments, chapters, plan, brief)
    _check_cancelled(cancel_check)
    decision = extractive_decision or _story_decision_from_beats(reviewed, beats, segments)
    if not decision:
        raise StoryPlanningError("Story AI completed its passes but did not produce a safe final selection.")
    _validate_single_source_passage(decision.get("story_beat_ids") or [], chapters, brief)
    if progress:
        progress(1.0, "Extractive rough cut requires review" if extractive_decision else "Story understanding complete")
    hierarchy = {
        "cache_fingerprint": expected_cache_fingerprint,
        "cache_pipeline": STORY_CACHE_PIPELINE,
        "model": model,
        "model_selection": _model_selection_details(status),
        "editorial_authority": decision.get("editorial_authority"),
        "extractive_requirements": copy.deepcopy(decision.get("extractive_requirements")),
        "chapter_count": len(chapters),
        "chapters": [
            {"id": item["id"], "start": item["start"], "end": item["end"], "duration": item["duration"], "beat_ids": item["beat_ids"]}
            for item in chapters
        ],
        "chapter_summaries": summaries,
        "summary_recovery": {
            "focused_retry_chapter_ids": [
                item["id"] for item in summaries if item.get("summary_source") == "model_retry"
            ],
            "extractive_chapter_ids": [
                item["id"] for item in summaries if item.get("summary_source") == "extractive"
            ],
        },
        "outline": outline,
        "plan": plan,
        "selection": {
            "keep_beat_ids": list(decision["story_beat_ids"]),
            "slot_map": [] if extractive_decision else reviewed.get("slot_map", []),
            "mode": reviewed.get("selection_mode", "model"),
            "recovered_slot_indexes": reviewed.get("recovered_slot_indexes", []),
            "budget_fit": reviewed.get("budget_fit"),
              "source_retrieval": copy.deepcopy(reviewed.get("source_retrieval")),
            "semantic_mapping_verified": False if extractive_decision else reviewed.get("semantic_mapping_verified") is True,
            "semantic_review_status": "not_model_reviewed" if extractive_decision else reviewed.get("semantic_review_status"),
            "evidence_policy_version": reviewed.get("evidence_policy_version"),
            "evidence_proof": copy.deepcopy(reviewed.get("evidence_proof")),
            "semantic_revision": copy.deepcopy(reviewed.get("semantic_revision")),
            "passage_option_selection": copy.deepcopy(reviewed.get("passage_option_selection")),
            "passage_option_final_review": copy.deepcopy(reviewed.get("passage_option_final_review")),
            "source_span_policy_version": (decision.get("extractive_requirements") or decision.get("story_requirements") or {}).get("source_span_policy_version"),
            "source_span_constraints": copy.deepcopy((decision.get("extractive_requirements") or decision.get("story_requirements") or {}).get("source_span_constraints")),
        },
        "critic": reviewed.get("critic", {}),
    }
    if extractive_decision:
        hierarchy["failed_generation_diagnostic"] = copy.deepcopy(extractive_decision["extractive_requirements"]["failed_generation_diagnostic"])
        hierarchy["failed_generative_selection"] = copy.deepcopy(reviewed)
    contract_report = evaluate_instruction_contract(
        instruction_contract, segments, decision,
        semantic_verified=not extractive_decision and reviewed.get("semantic_mapping_verified") is True)
    decision["instruction_contract"] = contract_report
    hierarchy["instruction_contract"] = copy.deepcopy(contract_report)
    return decision, hierarchy


def _ollama_chat(settings: Settings, segments: list[dict[str, Any]], brief: dict[str, Any], cancel_check: Callable[[], None] | None = None,
                 *, model_status: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not settings.ai.get("enabled", True):
        return None
    max_segments = int(settings.ai.get("max_llm_segments", 180))
    prompt_segments = compact_segments_for_llm(segments, max_segments)
    total_duration = max((float(item.get("end", 0)) for item in segments), default=0.0)
    compact = [
        {
            "id": item["id"], "text": item["text"], "score": item.get("editorial_score"),
            "position": round(float(item.get("start", 0)) / max(total_duration, 0.001), 4),
            "filler_ratio": item.get("filler_ratio"), "repeat_score": item.get("repeat_score"), "false_start": item.get("false_start"),
        }
        for item in prompt_segments
    ]
    goal = str(brief.get("goal") or "clean")
    editorial_intent = (
        "Preserve the original YouTube structure and meaning. Do not remove useful semantic content unless the user's explicit instruction asks for it. "
        "Dead-air cleanup is handled by a separate audio engine."
        if goal == "youtube"
        else "Prefer a coherent story over maximum cutting. Preserve context, claims and sentence meaning."
    )
    system_prompt = (
        "You are CUTROOM Director, a conservative professional video editor. You receive transcript segment IDs sampled across the full recording. "
        "Never invent timestamps or IDs. " + editorial_intent + " "
        "Remove clear retakes, false starts, filler-only lines, off-topic detours and redundant repetition when appropriate. "
        "Return JSON only with keys: keep_ids, remove_ids, highlight_ids, title, summary, opening_id, closing_id."
    )
    model = str((model_status or _ready_story_model_status(settings, brief))["selected_model"])
    payload = {
        "model": model, "stream": False, "format": "json",
        "options": {"temperature": 0.10, "num_ctx": 8192, "num_predict": 1100},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"brief": brief, "segments": compact}, ensure_ascii=False)},
        ],
    }
    from .cloud_ai import enabled, chat
    if enabled(settings):
        return chat(settings, payload, cancel_check=cancel_check)
    return _call_ollama(settings, payload)


def _validate_llm_result(result: dict[str, Any] | None, segments: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(result, dict) or not result:
        return None
    valid_ids = {item["id"] for item in segments}

    def valid_list(key: str, limit: int | None = None) -> list[str]:
        values = result.get(key, [])
        if not isinstance(values, list):
            return []
        unique: list[str] = []
        for value in values:
            if isinstance(value, str) and value in valid_ids and value not in unique:
                unique.append(value)
            if limit and len(unique) >= limit:
                break
        return unique

    remove = valid_list("remove_ids")
    keep = [item for item in valid_list("keep_ids") if item not in remove]
    highlights = valid_list("highlight_ids", 8)
    if not (keep or remove or highlights) or set(remove) == valid_ids:
        # A title-only/foreign-ID response is not an edit. Removing everything
        # would later restore the whole recording defensively, hiding a no-op.
        return None
    opening = result.get("opening_id")
    closing = result.get("closing_id")
    return {
        "keep_ids": keep,
        "remove_ids": remove,
        "highlight_ids": highlights,
        "title": str(result.get("title") or "AI draft")[:120],
        "summary": str(result.get("summary") or "A coherent first edit based on the transcript.")[:500],
        "opening_id": opening if isinstance(opening, str) and opening in valid_ids else None,
        "closing_id": closing if isinstance(closing, str) and closing in valid_ids else None,
    }


def deterministic_edit(segments: list[dict[str, Any]], brief: dict[str, Any]) -> dict[str, Any]:
    pace = str(brief.get("pace", "balanced"))
    remove_ids: list[str] = []
    for segment in segments:
        remove = bool(segment.get("false_start"))
        remove = remove or float(segment.get("filler_ratio", 0.0)) >= (0.38 if pace == "gentle" else 0.24)
        remove = remove or float(segment.get("repeat_score", 0.0)) >= (0.86 if pace == "gentle" else 0.72)
        remove = remove or float(segment.get("editorial_score", 1.0)) < ({"gentle": 0.18, "balanced": 0.28, "dynamic": 0.38}.get(pace, 0.28))
        if remove:
            remove_ids.append(segment["id"])
    ranked = sorted(segments, key=lambda item: float(item.get("editorial_score", 0.0)), reverse=True)
    highlight_ids = [item["id"] for item in ranked[:8]]
    return {
        "keep_ids": [item["id"] for item in segments if item["id"] not in remove_ids],
        "remove_ids": remove_ids,
        "highlight_ids": highlight_ids,
        "title": "CUTROOM first draft",
        "summary": "Removed obvious dead air, retakes, filler-heavy lines and repeated ideas while preserving continuity.",
        "opening_id": next((item["id"] for item in segments if item["id"] not in remove_ids), None),
        "closing_id": next((item["id"] for item in reversed(segments) if item["id"] not in remove_ids), None),
    }


def plan_edit(
    segments: list[dict[str, Any]],
    settings: Settings,
    brief: dict[str, Any],
    progress: Callable[[float, str], None] | None = None,
    story_cache: dict[str, Any] | None = None,
    cancel_check: Callable[[], None] | None = None,
    visual_moments: dict[str, Any] | None = None,
    *,
    source_window_request: Any = None,
    source_window_state: Callable[[], Any] | None = None,
) -> tuple[dict[str, Any], str]:
    _check_cancelled(cancel_check)
    # Explicit internal opt-in only; no settings/brief/UI toggle. This preview
    # has no decision field and cannot enter the existing draft/apply contract.
    window_original_brief = copy.deepcopy(brief) if source_window_request is not None else None
    if source_window_request is not None:
        from .window_evidence import validate_request_source
        from .window_retrieval import WindowRetrievalRequest, validate_retrieval_source
        from .window_composition import WindowCompositionRequest, validate_composition_source
        from .window_semantics import WindowSemanticRequest
        if isinstance(source_window_request, WindowSemanticRequest):
            validate_composition_source(segments, source_window_request.composition, source_window_state, cancel_check)
        elif isinstance(source_window_request, WindowCompositionRequest):
            validate_composition_source(segments, source_window_request, source_window_state, cancel_check)
        elif isinstance(source_window_request, WindowRetrievalRequest):
            validate_retrieval_source(segments, source_window_request, source_window_state, cancel_check)
        else:
            validate_request_source(segments, source_window_request, source_window_state, cancel_check)
        if str(brief.get("goal") or "short") != "short" or visual_moments is not None:
            raise ValueError("Window evidence preview currently supports transcript-only Shorts")
    elif source_window_state is not None:
        raise ValueError("Window state reader requires an explicit window request")
    brief = enrich_brief_with_style(brief)
    instruction_contract = assert_instruction_contract(brief)

    def reported(editorial: dict[str, Any], engine: str) -> tuple[dict[str, Any], str]:
        decision = editorial["decision"]
        contract_report = decision.get("instruction_contract") or evaluate_instruction_contract(instruction_contract, segments, decision)
        decision["instruction_contract"] = copy.deepcopy(contract_report)
        editorial["instruction_contract"] = copy.deepcopy(contract_report)
        return editorial, engine

    language = str(brief.get("language") or "en")
    enriched = enrich_segments(segments, language)
    if not enriched:
        return reported({"segments": [], "decision": deterministic_edit([], brief), "story_beats": [], "story_hierarchy": None}, "deterministic")

    goal = str(brief.get("goal") or "short")
    if goal in {"short", "podcast"}:
        beats = annotate_story_beats(build_story_beats(
            enriched, language,
            target_seconds=effective_duration_bounds(brief)["maximum_seconds"] if goal == "short" else None,
            independent_asr_entries=(goal == "short" and not explicit_source_continuity_requested(brief)
                and (single_source_passage_requested(brief) or single_output_requested(brief))
                and not _configured_story_roles(brief) and not required_story_role_orders(brief)),
            # Retrieval creates unreviewed whole-ASR alternatives, not an edit.
            # A long unpunctuated owner must not veto numeric window indexing.
            **({"allow_unreviewed_long_spans": True} if source_window_request is not None
               and isinstance(source_window_request, (WindowRetrievalRequest, WindowCompositionRequest, WindowSemanticRequest)) else {}),
        ), visual_moments)
        _check_cancelled(cancel_check)
        if source_window_request is not None:
            if isinstance(source_window_request, WindowSemanticRequest):
                from .window_semantics import prepare_window_semantic_preview
                return prepare_window_semantic_preview(
                    segments, beats, brief, window_original_brief, source_window_request,
                    source_window_state, settings, _call_ollama_story_pass, _story_prompt_tokens, cancel_check,
                ), "source_window_semantic_preview"
            if isinstance(source_window_request, WindowCompositionRequest):
                from .window_composition import prepare_window_composition_preview
                return prepare_window_composition_preview(
                    segments, beats, brief, window_original_brief, source_window_request,
                    source_window_state, cancel_check,
                ), "source_window_composition_preview"
            if isinstance(source_window_request, WindowRetrievalRequest):
                from .window_retrieval import prepare_window_retrieval_preview
                return prepare_window_retrieval_preview(
                    segments, beats, brief, window_original_brief, source_window_request,
                    source_window_state, cancel_check,
                ), "source_window_retrieval_preview"
            from .window_evidence import prepare_window_planner_preview
            return prepare_window_planner_preview(
                segments, beats, brief, window_original_brief, source_window_request,
                source_window_state, cancel_check,
            ), "source_window_evidence_preview"
        # The vision notes change the Story input, so they belong to its cache
        # identity. Without notes the identity is unchanged from earlier versions.
        visual_key = str((visual_moments or {}).get("cache_key") or "")
        noted = bool(visual_key) and any(beat.get("on_screen") for beat in beats)
        decision, hierarchy = hierarchical_story_edit(
            beats,
            enriched,
            settings,
            brief,
            progress,
            story_cache,
            cancel_check,
            **({"visual_key": visual_key} if noted else {}),
        )
        return reported({
            "segments": enriched,
            "decision": decision,
            "story_beats": beats,
            "story_hierarchy": hierarchy,
        }, (EXTRACTIVE_ROUGH_CUT_ENGINE if decision.get("editorial_authority") == EXTRACTIVE_ROUGH_CUT_AUTHORITY else
            str(settings.ai.get("cloud_connection", {}).get("provider") or "groq").replace("-", "_") + "_hierarchical_story"
            if settings.ai.get("cloud_connection", {}).get("mode", "local") != "local"
            else "ollama_hierarchical_story"
        ))

    _check_cancelled(cancel_check)
    status = story_ai_status(settings, brief)
    if settings.ai.get("enabled", True) and not status["ready"]:
        raise StoryAIUnavailableError(str(status["message"]))
    if status.get("using_fallback") and progress:
        progress(0.01, status["message"])
    response = _ollama_chat(settings, enriched, brief, cancel_check=cancel_check, model_status=status)
    llm = _validate_llm_result(response, enriched)
    _check_cancelled(cancel_check)
    if llm:
        return reported({"segments": enriched, "decision": llm, "story_beats": [], "story_hierarchy": None,
                "model_selection": _model_selection_details(status), "warnings": []}, (
            str(settings.ai.get("cloud_connection", {}).get("provider") or "groq").replace("-", "_")
            if settings.ai.get("cloud_connection", {}).get("mode", "local") != "local"
            else "ollama"
        ))
    warning = {
        "type": "story_ai_fallback" if settings.ai.get("enabled", True) else "ai_disabled",
        "message": ("Story AI did not return a valid edit; a basic transcript cleanup draft was created. Review it before exporting."
                    if settings.ai.get("enabled", True) else "AI is disabled; this is a basic transcript cleanup draft."),
    }
    return reported({"segments": enriched, "decision": deterministic_edit(enriched, brief), "story_beats": [], "story_hierarchy": None,
            "model_selection": _model_selection_details(status), "warnings": [warning]}, "deterministic")

def language_from_text(text: str, fallback: str = "en") -> str:
    counts = Counter({
        "he": len(re.findall(r"[\u0590-\u05FF]", text)),
        "ar": len(re.findall(r"[\u0600-\u06FF]", text)),
        "ru": len(re.findall(r"[\u0400-\u04FF]", text)),
        "latin": len(re.findall(r"[A-Za-zÀ-ÿ]", text)),
    })
    key, value = counts.most_common(1)[0]
    if value < 2:
        return fallback
    if key in {"he", "ar", "ru"}:
        return key
    lowered = f" {normalize_text(text)} "
    if any(word in lowered for word in (" el ", " la ", " que ", " para ", " una ", " gracias ")):
        return "es"
    if any(word in lowered for word in (" le ", " les ", " une ", " pour ", " avec ", " merci ")):
        return "fr"
    return "en"
