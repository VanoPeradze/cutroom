"""Recommend one edit style from saved, measured evidence.

This is advisory: it reads the saved transcript and the optional gameplay
vision pass, never calls a model, never changes project settings, and always
explains itself so the user can accept or ignore it. Without evidence it says
so instead of guessing.
"""
from __future__ import annotations

import math
from typing import Any

from .edit_styles import get_edit_style, style_family
from .visual_moments import usable_windows

SHORT_GOALS = {"short", "podcast"}
LONG_GOALS = {"youtube", "clean"}
# A recording that is mostly speech and shows no gameplay is treated as talk.
TALK_SPEECH_COVERAGE = 0.55
GAMEPLAY_SHARE = 0.35


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _speech_coverage(segments: list[dict[str, Any]], duration: float) -> float | None:
    if duration <= 0 or not segments:
        return None
    ranges = sorted(
        (max(0.0, _number(row.get("start"))), min(duration, _number(row.get("end"))))
        for row in segments
        if isinstance(row, dict) and str(row.get("text") or "").strip()
    )
    covered, cursor = 0.0, 0.0
    for start, end in ranges:
        start = max(start, cursor)
        if end > start:
            covered += end - start
            cursor = end
    return round(min(1.0, covered / duration), 3)


def _gameplay_share(visual: Any) -> float | None:
    windows = usable_windows(visual if isinstance(visual, dict) else None)
    if not windows:
        return None
    total = sum(row["end"] - row["start"] for row in windows)
    gameplay = sum(row["end"] - row["start"] for row in windows if row.get("screen") == "gameplay")
    return round(gameplay / total, 3) if total > 0 else None


def _speaker_count(segments: list[dict[str, Any]], video_map: Any) -> int:
    speakers = (video_map or {}).get("speakers") if isinstance(video_map, dict) else None
    if isinstance(speakers, dict) and speakers.get("available"):
        return int(speakers.get("count") or 0)
    return len({str(row.get("speaker")) for row in segments if isinstance(row, dict) and row.get("speaker")})


def recommend_style(project: dict[str, Any], goal: Any = None) -> dict[str, Any]:
    settings = project.get("settings") or {}
    goal = str(goal or settings.get("goal") or "short")
    analysis = project.get("analysis") or {}
    segments = [row for row in analysis.get("segments") or [] if isinstance(row, dict)]
    duration = _number(((project.get("sources") or {}).get("A") or {}).get("duration"))
    coverage = _speech_coverage(segments, duration)
    gameplay = _gameplay_share(analysis.get("visual_moments"))
    signals = {"goal": goal, "duration_seconds": round(duration, 1), "speech_coverage": coverage,
               "gameplay_share": gameplay, "speakers": _speaker_count(segments, analysis.get("video_map"))}

    def result(style_id: str, confidence: str, he: str, en: str) -> dict[str, Any]:
        style = get_edit_style(style_id, strict=True)
        return {"style": style["id"], "family": style_family(style["id"]), "name": style["name"],
                "confidence": confidence, "reason": {"he": he, "en": en}, "signals": signals}

    talk = coverage is not None and coverage >= TALK_SPEECH_COVERAGE and not (gameplay or 0.0) >= GAMEPLAY_SHARE
    is_gameplay = gameplay is not None and gameplay >= GAMEPLAY_SHARE
    if goal in LONG_GOALS:
        if is_gameplay:
            return result("gameplay_youtube", "high", "רוב ההקלטה היא משחק, אז כדאי לקצר אותה לפי הסדר עם פרקים.",
                          "Most of the recording is gameplay, so condense it in order with chapters.")
        if talk:
            return result("youtube_explainer", "high", "רוב ההקלטה היא דיבור, אז כדאי לנקות שקטים, מילות מילוי וטייקים חוזרים.",
                          "Most of the recording is speech, so clean pauses, filler words and repeated takes.")
        return result("clean_vod", "low", "אין עדיין מספיק ראיות על התוכן, אז הכי בטוח רק להוריד שקט.",
                      "There is not enough evidence about the content yet, so the safest edit only removes dead air.")
    if is_gameplay:
        return result("stream_highlights", "high", "יש הרבה משחק בהקלטה, אז רגעי שיא יתפסו הכי טוב ב-Shorts.",
                      "The recording has a lot of gameplay, so highlights will work best as Shorts.")
    if talk:
        if signals["speakers"] >= 2 or goal == "podcast":
            return result("talking_clips", "high", "זו שיחה בין כמה אנשים, אז כדאי לחתוך מחשבות שלמות שנפתחות במשפט חזק.",
                          "This is a conversation, so cut complete thoughts that open on a strong line.")
        return result("talking_clips", "medium", "רוב ההקלטה היא דיבור, אז כדאי לחתוך מחשבה שלמה שנפתחת במשפט חזק.",
                      "Most of the recording is speech, so cut one complete thought that opens on a strong line.")
    if coverage is None and gameplay is None:
        return result("smart", "low", "עדיין אין תמלול או ניתוח וידאו, אז אוטומטי הוא נקודת ההתחלה הכי טובה.",
                      "There is no transcript or video analysis yet, so Auto is the best starting point.")
    return result("smart", "medium", "התוכן מעורב, אז אוטומטי יאזן בין דיבור לרגעים חזקים.",
                  "The content is mixed, so Auto balances speech and strong moments.")
