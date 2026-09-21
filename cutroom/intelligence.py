from __future__ import annotations

import copy
import json
import logging
import queue
import re
import threading
import urllib.error
import urllib.request
from collections import Counter
from difflib import SequenceMatcher
from typing import Any, Callable

from .cache_keys import stable_fingerprint
from .ai_runtime import OLLAMA_RESPONSE_BYTES, open_ollama, read_ollama_json
from .config import Settings
from .utils import clamp, merge_ranges, normalize_text, range_duration

STORY_CACHE_PIPELINE = "hierarchical-story-2026-09-06.full-chapter-input"

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


def build_story_beats(segments: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    """Group transcript segments into editorial ideas rather than isolated lines.

    A two-hour source may have thousands of Whisper segments. CUTROOM should reason
    over 15–35 second ideas (beats), then use real segment boundaries for the final
    cuts. This substantially improves context while keeping the 4B planner light.
    """
    if not segments:
        return []
    ordered = sorted(segments, key=lambda item: (float(item.get("start", 0)), float(item.get("end", 0))))
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in ordered:
        if current:
            gap = float(item.get("start", 0)) - float(current[-1].get("end", 0))
            current_duration = float(current[-1]["end"]) - float(current[0]["start"])
            current_words = sum(len(tokens(str(row.get("text", "")))) for row in current)
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
            )
            if should_break:
                groups.append(current)
                current = []
        current.append(item)
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
    return beats


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


class StoryPlanningError(RuntimeError):
    """The Story AI answered, but a safe coherent plan could not be produced."""


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
                "properties": {"slot_index": {"type": "integer"}, "beat_ids": _STRING_LIST_SCHEMA},
                "required": ["slot_index", "beat_ids"],
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
    },
    "required": ["verdict", "add_beat_ids", "remove_beat_ids", "issues", "summary"],
}


def story_cache_fingerprint(segments: list[dict[str, Any]], brief: dict[str, Any], model: str) -> str:
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
            "brief": dict(brief),
            "language": brief.get("language"),
            "performance_mode": brief.get("performance_mode"),
            "goal": brief.get("goal"),
            "instruction": brief.get("instruction"),
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


def _model_preferences(settings: Settings, brief: dict[str, Any]) -> list[str]:
    base = str(settings.ai.get("editor_model", "qwen3.5:4b"))
    fallbacks = [str(item) for item in settings.ai.get("editor_fallback_models", [])]
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    preferred: list[str] = []
    if mode == "quality":
        preferred.append(str(settings.ai.get("editor_quality_model") or "qwen3.5:9b"))
    elif mode == "lite":
        preferred.append(str(settings.ai.get("editor_lite_model") or "qwen3.5:2b"))
    preferred.extend([base, *fallbacks])
    output: list[str] = []
    for model in preferred:
        clean = model.removesuffix(":latest")
        if clean and clean not in output:
            output.append(clean)
    return output


def _select_editor_model(settings: Settings, brief: dict[str, Any]) -> str:
    from .cloud_ai import enabled, connection
    if enabled(settings):
        return str(connection(settings)["model"])
    installed = _installed_models(settings)
    preferred = _model_preferences(settings, brief)
    if installed:
        for model in preferred:
            if model in installed:
                return model
    return preferred[0] if preferred else "qwen3.5:4b"


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
                "recommended_model": selected["model"], "reason": None if ready else "cloud_key_required"}
    if not settings.ai.get("enabled", True):
        return {
            "ready": False, "ollama_available": False, "installed_models": [], "selected_model": None,
            "recommended_model": str(settings.ai.get("editor_model", "qwen3.5:4b")).removesuffix(":latest"),
            "reason": "ai_disabled",
        }
    available, installed = _ollama_inventory(settings)
    preferred = _model_preferences(settings, brief)
    selected = next((model for model in preferred if model in installed), None)
    recommended = str(settings.ai.get("editor_model", "qwen3.5:4b")).removesuffix(":latest")
    return {
        "ready": bool(available and selected),
        "ollama_available": available,
        "installed_models": sorted(installed),
        "selected_model": selected,
        "recommended_model": recommended,
        "reason": (
            None
            if available and selected
            else "ollama_unavailable"
            if not available
            else "story_model_missing"
        ),
    }


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
            message = chunk.get("message") if isinstance(chunk.get("message"), dict) else {}
            if isinstance(message.get("content"), str):
                content_parts.append(message["content"])
            if isinstance(message.get("thinking"), str):
                thinking_parts.append(message["thinking"])
            final.update({key: value for key, value in chunk.items() if key != "message"})
            _check_cancelled(cancel_check)
            if chunk.get("done") is True:
                break
        _check_cancelled(cancel_check)
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
    context = min(cap, max(1024, int(options.get("num_ctx") or 8192)))
    estimate = _story_prompt_tokens(payload)
    needed = estimate + reserve
    if needed > context:
        context = min(cap, ((needed + 1023) // 1024) * 1024)
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


def _call_ollama_strict(
    settings: Settings,
    payload: dict[str, Any],
    timeout: int = 180,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    from .cloud_ai import enabled, chat
    if enabled(settings):
        return chat(settings, payload, cancel_check=cancel_check, timeout=timeout)
    # The hierarchy preflights Ollama/model availability once before the first pass.
    # Do not re-query /api/tags before every pass; that adds latency without adding safety.
    clean_payload = copy.deepcopy(payload)
    mode = str(clean_payload.pop("_performance_mode", None) or settings.ai.get("performance_mode") or "auto").lower()
    # Story passes require compact JSON. Explicitly disable model thinking so
    # the response token budget cannot be exhausted before content is emitted.
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
    for attempt in range(2):
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
        last_message = body.get("message", {}) if isinstance(body.get("message"), dict) else {}
        last_reason = str(body.get("done_reason") or "unknown")
        content = last_message.get("content")
        if content:
            try:
                parsed = json.loads(content)
            except (TypeError, json.JSONDecodeError) as exc:
                last_json_error = exc
            else:
                if not isinstance(parsed, dict):
                    raise StoryPlanningError("Story AI returned an invalid structured response.")
                return parsed
        if attempt == 0:
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
    if last_message.get("content"):
        raise StoryPlanningError("Story AI returned invalid JSON after an automatic retry.") from last_json_error
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
                ),
            },
            {"role": "user", "content": json.dumps({"brief": brief, "chapters": summaries}, ensure_ascii=False)},
        ],
    }
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


def _build_story_plan(
    settings: Settings,
    summaries: list[dict[str, Any]],
    outline: dict[str, Any],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    if progress:
        progress(0.56, "Building the narrative")
    target = max(8.0, float(brief.get("target_duration") or 60))
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    if target <= 75:
        shape = "hook, minimum context, strongest proof/example, payoff, complete ending"
    elif target <= 210:
        shape = "hook, setup, reasoning, one or more examples/proofs, result, conclusion"
    else:
        shape = "representative chronological condensed story with setup, development, proof and conclusion"
    style_profile = brief.get("style_profile") or {}
    selection_policy = style_profile.get("selection_policy") or {}
    structure = selection_policy.get("story_structure") or []
    if structure:
        shape = " -> ".join(str(part) for part in structure)
    moment_limit = selection_policy.get("max_moments")
    style_contract = (
        f" Select at most {moment_limit} distinct complete moment(s); preserve this progression within each. "
        "A shorter complete story is preferable to unrelated padding. "
        if moment_limit else ""
    )
    payload = {
        "model": model,
        "stream": False,
        "format": STORY_PLAN_SCHEMA,
        "_performance_mode": mode,
        "options": {"temperature": 0.05, "num_ctx": 12288, "num_predict": 1300},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM Story Producer. Turn the global outline into an editorial plan before any exact clips are chosen. "
                    f"The requested story shape is: {shape}. Respect dependencies: never use a payoff that becomes confusing because its setup was removed. "
                    + style_contract +
                    "Use material from anywhere in the recording when it improves the story. Return JSON only with keys narrative,slots. "
                    "slots is a list of {purpose,chapter_ids,desired_seconds,reason,required_context_chapter_ids}. Only use supplied chapter IDs."
                ),
            },
            {"role": "user", "content": json.dumps({"brief": brief, "target_seconds": target, "outline": outline, "chapters": summaries}, ensure_ascii=False)},
        ],
    }
    result = _call_ollama_story_pass(settings, payload, 240, cancel_check)
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
    minimum_slots = 1 if len(summaries) <= 1 else 2
    if len(slots) < minimum_slots:
        raise StoryPlanningError("Story AI could not build a complete narrative plan.")
    return {"narrative": str(result.get("narrative") or "")[:1000], "slots": slots}


def _candidate_beats_for_plan(chapters: list[dict[str, Any]], plan: dict[str, Any]) -> list[dict[str, Any]]:
    wanted: set[str] = set()
    for slot in plan.get("slots", []):
        wanted.update(str(value) for value in slot.get("chapter_ids", []))
        wanted.update(str(value) for value in slot.get("required_context_chapter_ids", []))
    candidates: list[dict[str, Any]] = []
    for chapter in chapters:
        if chapter["id"] in wanted:
            candidates.extend(chapter["beats"])
    return candidates


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
    selected = [
        str(identifier) for identifier in selection.get("keep_beat_ids", [])
        if str(identifier) in valid
    ]
    selected = list(dict.fromkeys(selected))
    target = max(8.0, float(target_duration))
    headroom = 1.12 if target <= 90.0 else 1.08 if target <= 210.0 else 1.05
    ceiling = target * headroom
    slot_rows = selection.get("slot_map", []) if isinstance(selection.get("slot_map"), list) else []
    slot_rows = [item for item in slot_rows if isinstance(item, dict)]
    if not selected and not slot_rows:
        return selection

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
    if before <= ceiling + 0.05 and every_slot_represented:
        return selection

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

    fitted: set[str] = set()
    fitted_slot_map: list[dict[str, Any]] = []
    plan_slots = plan.get("slots", []) if isinstance(plan.get("slots"), list) else []
    beat_to_chapter = {
        str(beat.get("id")): str(chapter.get("id"))
        for chapter in (chapters or [])
        for beat in (chapter.get("beats", []) if isinstance(chapter, dict) else [])
        if isinstance(beat, dict) and beat.get("id") is not None
    }
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
            if str(identifier) in valid
        ]
        primary_chapters = {str(value) for value in slot.get("chapter_ids", [])}
        primary_choices = [
            identifier for identifier in valid
            if primary_chapters and beat_to_chapter.get(identifier) in primary_chapters
        ]
        choices = primary_choices or model_choices
        if not choices:
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

    for identifier in sorted((item for item in selected if item not in fitted), key=extra_value, reverse=True):
        proposed = set(fitted)
        proposed.add(identifier)
        if selection_duration(proposed) <= ceiling + 0.05:
            fitted = proposed

    fitted_ids = sorted(fitted, key=lambda identifier: float(valid[identifier].get("start", 0.0)))
    if not fitted_ids:
        return selection
    after = selection_duration(fitted_ids)
    output = dict(selection)
    output["keep_beat_ids"] = fitted_ids
    output["highlight_beat_ids"] = [identifier for identifier in selection.get("highlight_beat_ids", []) if str(identifier) in fitted]
    output["opening_beat_id"] = fitted_ids[0]
    output["closing_beat_id"] = fitted_ids[-1]
    if fitted_slot_map:
        output["slot_map"] = fitted_slot_map
    output["budget_fit"] = {
        "target_duration": round(target, 3),
        "ceiling": round(ceiling, 3),
        "before_duration": round(before, 3),
        "after_duration": round(after, 3),
        "removed_beat_ids": [identifier for identifier in selected if identifier not in fitted],
    }
    return output


def _select_story_beats(
    settings: Settings,
    chapters: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    outline: dict[str, Any],
    plan: dict[str, Any],
    brief: dict[str, Any],
    model: str,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if progress:
        progress(0.70, "Choosing the exact moments")
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    target = max(8.0, float(brief.get("target_duration") or 60))
    candidates = _candidate_beats_for_plan(chapters, plan)
    if not candidates:
        raise StoryPlanningError("Story plan did not reference any usable source material.")
    # Keep the exact-selection pass bounded while preserving all planned chapters.
    max_candidates = 72 if mode == "lite" else 120 if mode == "quality" else 96
    if len(candidates) > max_candidates:
        by_chapter: dict[str, list[dict[str, Any]]] = {}
        beat_to_chapter = {str(beat["id"]): chapter["id"] for chapter in chapters for beat in chapter["beats"]}
        key_beats_by_chapter = {str(item["id"]): {str(value) for value in item.get("key_beat_ids", [])} for item in summaries}
        for beat in candidates:
            by_chapter.setdefault(beat_to_chapter[str(beat["id"])], []).append(beat)
        reduced: list[dict[str, Any]] = []
        quota = max(4, max_candidates // max(1, len(by_chapter)))
        for chapter_id, rows in by_chapter.items():
            rows = sorted(rows, key=lambda item: float(item["start"]))
            keep_ids: set[str] = {str(rows[0]["id"]), str(rows[-1]["id"])}
            keep_ids.update(identifier for identifier in key_beats_by_chapter.get(chapter_id, set()) if any(str(row["id"]) == identifier for row in rows))
            keep_ids.update(str(row["id"]) for row in rows if row.get("role_hint"))
            # Preserve the internal progression of the chapter instead of re-ranking
            # it into disconnected highlight lines. Fill remaining quota uniformly.
            remaining = max(0, quota - len(keep_ids))
            if remaining:
                for slot in range(remaining):
                    index = min(len(rows) - 1, int(round(slot * (len(rows) - 1) / max(1, remaining - 1))))
                    keep_ids.add(str(rows[index]["id"]))
            if len(keep_ids) > quota:
                essentials = {str(rows[0]["id"]), str(rows[-1]["id"])} | key_beats_by_chapter.get(chapter_id, set())
                kept_rows = [row for row in rows if str(row["id"]) in keep_ids]
                kept_rows.sort(key=lambda row: (str(row["id"]) in essentials, bool(row.get("role_hint")), float(row.get("editorial_score", 0))), reverse=True)
                keep_ids = {str(row["id"]) for row in kept_rows[:quota]}
            reduced.extend(item for item in rows if str(item["id"]) in keep_ids)
        candidates = sorted(reduced, key=lambda item: float(item["start"]))[:max_candidates]
    valid = {str(item["id"]): item for item in candidates}
    valid_ids = set(valid)
    payload = {
        "model": model,
        "stream": False,
        "format": STORY_SELECTION_SCHEMA,
        "_performance_mode": mode,
        "options": {"temperature": 0.04, "num_ctx": 16384 if mode == "quality" else 12288, "num_predict": 1500},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM's precision editor. The story has already been understood and planned. Now choose the exact STORY BEATS that best realize each slot. "
                    "Do not optimize for dramatic standalone quotes. Preserve complete ideas, prerequisite context, chronology and cause/effect. "
                    "Stay close to the target duration; audio cleanup happens later. Every planned story slot must receive at least one beat. "
                    "Return JSON only with keys slot_selections,highlight_beat_ids,opening_beat_id,closing_beat_id,title,summary. "
                    "slot_selections is a list of {slot_index,beat_ids}; only use beats from that slot's chapter_ids or required_context_chapter_ids. Only use supplied beat IDs."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "brief": brief,
                    "target_seconds": target,
                    "outline": outline,
                    "plan": plan,
                    "chapter_summaries": summaries,
                    "candidate_beats": [
                        {"id": beat["id"], "start": beat["start"], "duration": beat["duration"], "role": beat.get("role_hint"), "text": _balanced_excerpt(str(beat.get("text", "")), 520)}
                        for beat in candidates
                    ],
                }, ensure_ascii=False),
            },
        ],
    }
    selection_error: str | None = None
    try:
        result = _call_ollama_story_pass(
            settings,
            payload,
            300 if mode == "quality" else 220,
            cancel_check,
        )
    except StoryPlanningError as exc:
        # Chapter understanding, the global outline and the narrative plan are
        # already model-authored. If only the final schema pass drifts, recover
        # exact source beats from that plan instead of throwing all prior work away.
        result = {}
        selection_error = str(exc)
    beat_to_chapter = {str(beat["id"]): chapter["id"] for chapter in chapters for beat in chapter["beats"]}
    raw_slots = result.get("slot_selections") if isinstance(result.get("slot_selections"), list) else []
    slot_map: list[dict[str, Any]] = []
    keep: list[str] = []
    seen_slots: set[int] = set()
    for row in raw_slots:
        if not isinstance(row, dict):
            continue
        try:
            slot_index = int(row.get("slot_index"))
        except (TypeError, ValueError):
            continue
        if slot_index < 0 or slot_index >= len(plan.get("slots", [])) or slot_index in seen_slots:
            continue
        slot = plan["slots"][slot_index]
        allowed_chapters = {str(value) for value in slot.get("chapter_ids", [])} | {str(value) for value in slot.get("required_context_chapter_ids", [])}
        beat_ids = [
            str(value) for value in row.get("beat_ids", [])
            if str(value) in valid_ids and beat_to_chapter.get(str(value)) in allowed_chapters
        ]
        if not beat_ids:
            continue
        seen_slots.add(slot_index)
        beat_ids = sorted(dict.fromkeys(beat_ids), key=lambda identifier: float(valid[identifier]["start"]))
        slot_map.append({"slot_index": slot_index, "purpose": slot.get("purpose"), "beat_ids": beat_ids})
        for identifier in beat_ids:
            if identifier not in keep:
                keep.append(identifier)
    expected_slots = set(range(len(plan.get("slots", []))))
    recovered_slots: list[int] = []
    key_beat_ids = {
        str(value)
        for summary in summaries
        for value in summary.get("key_beat_ids", [])
        if str(value) in valid_ids
    }
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
    for slot_index in sorted(expected_slots - seen_slots):
        slot = plan["slots"][slot_index]
        allowed_chapters = {str(value) for value in slot.get("chapter_ids", [])} | {
            str(value) for value in slot.get("required_context_chapter_ids", [])
        }
        available = [
            beat for identifier, beat in valid.items()
            if beat_to_chapter.get(identifier) in allowed_chapters
        ]
        if not available:
            continue
        purpose = str(slot.get("purpose") or "").lower()
        expected_roles = next((roles for cue, roles in role_groups.items() if cue in purpose), set())
        unused = [beat for beat in available if str(beat["id"]) not in keep]
        chosen = max(
            unused or available,
            key=lambda beat: (
                1 if str(beat["id"]) in key_beat_ids else 0,
                1 if str(beat.get("role_hint") or "") in expected_roles else 0,
                float(beat.get("editorial_score", 0.0)),
                float(beat.get("novelty", 0.0)),
                -float(beat.get("start", 0.0)) if slot_index == 0 else float(beat.get("start", 0.0)),
            ),
        )
        identifier = str(chosen["id"])
        seen_slots.add(slot_index)
        recovered_slots.append(slot_index)
        slot_map.append({"slot_index": slot_index, "purpose": slot.get("purpose"), "beat_ids": [identifier]})
        if identifier not in keep:
            keep.append(identifier)
    if seen_slots != expected_slots:
        raise StoryPlanningError("Story AI left one or more narrative slots without source material.")
    keep.sort(key=lambda identifier: float(valid[identifier]["start"]))
    minimum_keep = 1 if len(candidates) <= 1 else 2
    if len(keep) < minimum_keep:
        raise StoryPlanningError("Story AI did not select enough coherent source material.")
    clean = {
        "keep_beat_ids": keep,
        "slot_map": sorted(slot_map, key=lambda item: item["slot_index"]),
        "highlight_beat_ids": [str(value) for value in result.get("highlight_beat_ids", []) if str(value) in valid_ids][:8],
        "opening_beat_id": str(result.get("opening_beat_id") or "") if str(result.get("opening_beat_id") or "") in valid_ids else keep[0],
        "closing_beat_id": str(result.get("closing_beat_id") or "") if str(result.get("closing_beat_id") or "") in valid_ids else keep[-1],
        "title": str(result.get("title") or "CUTROOM story")[:120],
        "summary": str(result.get("summary") or "")[:600],
        "selection_mode": "ai_plan_recovery" if recovered_slots or selection_error else "model",
        "recovered_slot_indexes": recovered_slots,
        "recovery_reason": selection_error,
    }
    return clean, candidates


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
) -> dict[str, Any]:
    if progress:
        progress(0.84, "Checking continuity and context")
    valid = {str(item["id"]): item for item in candidates}
    selected = [identifier for identifier in selection.get("keep_beat_ids", []) if identifier in valid]
    selected_rows = [
        {"id": identifier, "start": valid[identifier]["start"], "text": _balanced_excerpt(str(valid[identifier].get("text", "")), 520)}
        for identifier in selected
    ]
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    payload = {
        "model": model,
        "stream": False,
        "format": STORY_CRITIC_SCHEMA,
        "_performance_mode": mode,
        "options": {"temperature": 0.03, "num_ctx": 12288, "num_predict": 900},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are CUTROOM's continuity critic. Audit the proposed edit as if the viewer has never seen the source. "
                    "Check whether references still make sense, setup exists before payoff, transitions are understandable, claims have enough context, and repeated ideas are not wasting the time budget. "
                    "You may add or remove only supplied candidate beat IDs. Return JSON only with keys verdict,add_beat_ids,remove_beat_ids,issues,summary. verdict is pass or revise."
                ),
            },
            {"role": "user", "content": json.dumps({
                "brief": brief, "outline": outline, "plan": plan, "selected": selected_rows,
                "candidates": [{"id": identifier, "start": row["start"], "text": _balanced_excerpt(str(row.get("text", "")), 300)} for identifier, row in valid.items()],
            }, ensure_ascii=False)},
        ],
    }
    result = _call_ollama_story_pass(settings, payload, 220, cancel_check)
    additions = [str(value) for value in result.get("add_beat_ids", []) if str(value) in valid]
    removals = {str(value) for value in result.get("remove_beat_ids", []) if str(value) in valid}
    final = [identifier for identifier in selected if identifier not in removals]
    for identifier in additions:
        if identifier not in final:
            final.append(identifier)
    final.sort(key=lambda identifier: float(valid[identifier]["start"]))
    for slot in selection.get("slot_map", []):
        slot_ids = [identifier for identifier in slot.get("beat_ids", []) if identifier in valid]
        if slot_ids and not any(identifier in final for identifier in slot_ids):
            final.append(slot_ids[0])
    final = sorted(dict.fromkeys(final), key=lambda identifier: float(valid[identifier]["start"]))
    minimum_final = 1 if len(valid) <= 1 else 2
    if len(final) < minimum_final:
        raise StoryPlanningError("Story critic rejected too much material; no safe coherent edit remained.")
    output = dict(selection)
    output["keep_beat_ids"] = final
    output["opening_beat_id"] = final[0]
    output["closing_beat_id"] = final[-1]
    output["critic"] = {
        "verdict": str(result.get("verdict") or "pass")[:16],
        "issues": [str(value)[:320] for value in result.get("issues", []) if str(value).strip()][:8],
        "summary": str(result.get("summary") or "")[:600],
        "added": additions,
        "removed": sorted(removals),
    }
    return output


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

    keep_beats = beat_ids("keep_beat_ids")
    highlights = beat_ids("highlight_beat_ids", 8)
    opening = str(result.get("opening_beat_id") or "")
    closing = str(result.get("closing_beat_id") or "")
    if opening in valid and opening not in keep_beats:
        keep_beats.append(opening)
    if closing in valid and closing not in keep_beats:
        keep_beats.append(closing)
    if not keep_beats:
        return None
    keep_beats = sorted(keep_beats, key=lambda identifier: float(by_id[identifier]["start"]))
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
    return {
        "keep_ids": [identifier for identifier in all_segment_ids if identifier in selected_segment_ids],
        "remove_ids": [identifier for identifier in all_segment_ids if identifier not in selected_segment_ids],
        "highlight_ids": highlight_segments,
        "opening_id": representative(opening, first=True) if opening in valid else representative(keep_beats[0], first=True),
        "closing_id": representative(closing, last=True) if closing in valid else representative(keep_beats[-1], last=True),
        "title": str(result.get("title") or "CUTROOM story")[:120],
        "summary": str(result.get("summary") or "A coherent story selected from the full recording.")[:500],
        "story_beat_ids": keep_beats,
        "story_ranges": [
            {"start": float(by_id[identifier]["start"]), "end": float(by_id[identifier]["end"]), "beat_id": identifier}
            for identifier in keep_beats
        ],
    }


def deterministic_story_edit(beats: list[dict[str, Any]], segments: list[dict[str, Any]], brief: dict[str, Any]) -> dict[str, Any]:
    if not beats:
        return deterministic_edit(segments, {**brief, "goal": "clean"})
    target = max(10.0, float(brief.get("target_duration", 60)))
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


def hierarchical_story_edit(
    beats: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    settings: Settings,
    brief: dict[str, Any],
    progress: Callable[[float, str], None] | None = None,
    story_cache: dict[str, Any] | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _check_cancelled(cancel_check)
    status = story_ai_status(settings, brief)
    if not status["ready"]:
        recommended = status["recommended_model"]
        if status["reason"] == "cloud_key_required":
            provider_label = str(status.get("provider_label") or "cloud AI")
            raise StoryAIUnavailableError(f"Connect {provider_label} in AI connection before creating a cloud edit.")
        if status["reason"] == "ollama_unavailable":
            raise StoryAIUnavailableError("Story AI requires Ollama to be running before a semantic edit can be created.")
        raise StoryAIUnavailableError(f"Story AI model {recommended} must be installed before creating a semantic edit.")
    model = str(status["selected_model"])
    expected_cache_fingerprint = story_cache_fingerprint(segments, brief, model)
    mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode", "auto"))
    max_chapters = 8 if mode == "lite" else 16 if mode == "quality" else 12
    chapters = build_story_chapters(beats, max_chapters=max_chapters)
    if len(chapters) < 2:
        # Very short sources do not need multiple chapter calls, but still require a real model pass.
        chapters = build_story_chapters(beats, max_chapters=4)
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
        if cancel_check is None:
            outline = _build_global_outline(settings, summaries, brief, model, progress)
        else:
            outline = _build_global_outline(
                settings,
                summaries,
                brief,
                model,
                progress,
                cancel_check,
            )
    _check_cancelled(cancel_check)
    if cancel_check is None:
        plan = _build_story_plan(settings, summaries, outline, brief, model, progress)
    else:
        plan = _build_story_plan(
            settings,
            summaries,
            outline,
            brief,
            model,
            progress,
            cancel_check,
        )
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
        )
    selection = _fit_story_selection_to_budget(
        selection,
        candidates,
        plan,
        float(brief.get("target_duration") or 60),
        chapters,
    )
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
            )
    except StoryPlanningError as exc:
        # The critic is a safety review, not the source of the edit. A malformed
        # critic response must not erase a complete, slot-validated selection.
        reviewed = dict(selection)
        reviewed["critic"] = {"verdict": "skipped", "issues": [str(exc)], "summary": "Selection kept after critic response failure."}
    reviewed = _fit_story_selection_to_budget(
        reviewed,
        candidates,
        plan,
        float(brief.get("target_duration") or 60),
        chapters,
    )
    _check_cancelled(cancel_check)
    decision = _story_decision_from_beats(reviewed, beats, segments)
    if not decision:
        raise StoryPlanningError("Story AI completed its passes but did not produce a safe final selection.")
    if progress:
        progress(1.0, "Story understanding complete")
    hierarchy = {
        "cache_fingerprint": expected_cache_fingerprint,
        "cache_pipeline": STORY_CACHE_PIPELINE,
        "model": model,
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
            "mode": reviewed.get("selection_mode", "model"),
            "recovered_slot_indexes": reviewed.get("recovered_slot_indexes", []),
            "budget_fit": reviewed.get("budget_fit"),
        },
        "critic": reviewed.get("critic", {}),
    }
    return decision, hierarchy


def _ollama_chat(settings: Settings, segments: list[dict[str, Any]], brief: dict[str, Any], cancel_check: Callable[[], None] | None = None) -> dict[str, Any] | None:
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
    model = _select_editor_model(settings, brief)
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
    if not result:
        return None
    valid_ids = {item["id"] for item in segments}

    def valid_list(key: str, limit: int | None = None) -> list[str]:
        values = result.get(key, [])
        if not isinstance(values, list):
            return []
        unique: list[str] = []
        for value in values:
            if value in valid_ids and value not in unique:
                unique.append(value)
            if limit and len(unique) >= limit:
                break
        return unique

    remove = valid_list("remove_ids")
    keep = [item for item in valid_list("keep_ids") if item not in remove]
    highlights = valid_list("highlight_ids", 8)
    return {
        "keep_ids": keep,
        "remove_ids": remove,
        "highlight_ids": highlights,
        "title": str(result.get("title") or "AI draft")[:120],
        "summary": str(result.get("summary") or "A coherent first edit based on the transcript.")[:500],
        "opening_id": result.get("opening_id") if result.get("opening_id") in valid_ids else None,
        "closing_id": result.get("closing_id") if result.get("closing_id") in valid_ids else None,
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
) -> tuple[dict[str, Any], str]:
    _check_cancelled(cancel_check)
    language = str(brief.get("language") or "en")
    enriched = enrich_segments(segments, language)
    if not enriched:
        return {"segments": [], "decision": deterministic_edit([], brief), "story_beats": [], "story_hierarchy": None}, "deterministic"

    goal = str(brief.get("goal") or "short")
    if goal in {"short", "podcast"}:
        beats = build_story_beats(enriched, language)
        _check_cancelled(cancel_check)
        decision, hierarchy = hierarchical_story_edit(
            beats,
            enriched,
            settings,
            brief,
            progress,
            story_cache,
            cancel_check,
        )
        return {
            "segments": enriched,
            "decision": decision,
            "story_beats": beats,
            "story_hierarchy": hierarchy,
        }, (
            str(settings.ai.get("cloud_connection", {}).get("provider") or "groq").replace("-", "_") + "_hierarchical_story"
            if settings.ai.get("cloud_connection", {}).get("mode", "local") != "local"
            else "ollama_hierarchical_story"
        )

    _check_cancelled(cancel_check)
    from .cloud_ai import enabled
    response = _ollama_chat(settings, enriched, brief, cancel_check=cancel_check) if enabled(settings) else _ollama_chat(settings, enriched, brief)
    llm = _validate_llm_result(response, enriched)
    _check_cancelled(cancel_check)
    if llm:
        return {"segments": enriched, "decision": llm, "story_beats": [], "story_hierarchy": None}, (
            str(settings.ai.get("cloud_connection", {}).get("provider") or "groq").replace("-", "_")
            if settings.ai.get("cloud_connection", {}).get("mode", "local") != "local"
            else "ollama"
        )
    return {"segments": enriched, "decision": deterministic_edit(enriched, brief), "story_beats": [], "story_hierarchy": None}, "deterministic"

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
