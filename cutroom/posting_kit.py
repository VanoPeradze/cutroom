"""Posting kit for one Clips board moment: titles, a description and hashtags.

The basic kit is built only from what the recording already says (its saved
transcript and optional gameplay-vision events). It never invents facts,
runs a model or saves the project. ``ai_posting_kit`` asks the configured
Story AI (local Ollama or the connected cloud model) to rewrite that same
material into stronger titles, and keeps the basic kit as its fallback.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Callable

from .clip_board import _segments, _visual
from .director import _REACTION_CUE, _finite_number

TITLE_CHARS = 80
DESCRIPTION_CHARS = 500
MAX_TITLES = 3
MAX_HASHTAGS = 6
CONTEXT_CHARS = 2400

_HEBREW = re.compile(r"[֐-׿]")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9']+|[א-ת][א-ת\"'׳״]+")
_STOP = frozenset("""
a about after again all also am an and any are as at be because been before being but by can could did do does doing
don't down even every for from get go going gonna got had has have he her here him his how i i'm if in into is it it's
its just know let like look make me more my no not now of off oh ok okay on one only or our out over really right see
she so some still such than that that's the their them then there these they thing think this those through to too up
us very was way we well were what when where which while who why will with would yeah yes you your you're want wanna
את של על עם זה זו זאת אני אתה את הוא היא אנחנו אתם הם הן לא כן גם רק אבל או כי אם מה מי איך למה כמו יש אין היה הייתה
היו להיות עוד כבר אז פה שם כל הכל עכשיו אחד אחת שלי שלך שלו שלה שלנו לי לך לו לה לנו בו בה זהו ככה טוב בסדר אוקיי
""".split())


class PostingKitError(ValueError):
    """The request is invalid (bad range), not merely missing analysis."""


class PostingKitUnavailable(RuntimeError):
    """Story AI cannot write a kit right now; the basic kit remains usable."""


def _language(text: str) -> str:
    letters = [char for char in text if char.isalpha()]
    if not letters:
        return "en"
    hebrew = sum(1 for char in letters if _HEBREW.match(char))
    return "he" if hebrew / len(letters) >= 0.3 else "en"


def _trim(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    space = cut.rfind(" ")
    if space >= limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.;:-") + "…"


def _clip_lines(project: dict[str, Any], start: float, end: float) -> list[str]:
    lines = []
    for row in _segments(project):
        if _finite_number(row.get("end")) > start and _finite_number(row.get("start")) < end:
            text = str(row.get("text") or "").strip()
            if text:
                lines.append(text)
    return lines


def _events(project: dict[str, Any], start: float, end: float) -> list[str]:
    visual = _visual(project)
    if visual is None:
        return []
    found: list[str] = []
    for window in getattr(visual, "windows", []) or []:
        if not isinstance(window, dict):
            continue
        if _finite_number(window.get("end")) <= start or _finite_number(window.get("start")) >= end:
            continue
        event = str(window.get("event") or "").strip()
        if event and event not in found:
            found.append(event)
    return found[:3]


def _keywords(lines: list[str], limit: int = MAX_HASHTAGS) -> list[str]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for line in lines:
        for word in _WORD.findall(line):
            key = word.strip("'\"׳״").lower()
            if len(key) < 3 or key in _STOP or key.isdigit():
                continue
            counts[key] += 1
            first_seen.setdefault(key, len(first_seen))
    ranked = sorted(counts, key=lambda key: (-counts[key], first_seen[key]))
    return ranked[:limit]


def _hashtag(word: str) -> str:
    clean = re.sub(r"[^\w֐-׿]", "", str(word or "").replace(" ", ""))
    return f"#{clean}" if 2 <= len(clean) <= 40 else ""


def _strongest_line(lines: list[str]) -> str:
    """Prefer a reaction or question; otherwise the most substantial early line."""
    for line in lines:
        if "!" in line or _REACTION_CUE.search(line):
            return line
    for line in lines:
        if line.rstrip().endswith("?"):
            return line
    early = lines[:3]
    return max(early, key=len) if early else ""


def build_posting_kit(project: dict[str, Any], start: Any, end: Any, *, goal: str = "short") -> dict[str, Any]:
    duration = _finite_number(((project.get("sources") or {}).get("A") or {}).get("duration"))
    try:
        start, end = float(start), float(end)
    except (TypeError, ValueError) as error:
        raise PostingKitError("Choose a clip with a valid start and end.") from error
    if not (start >= 0 and end > start and (duration <= 0 or end <= duration + 0.5)):
        raise PostingKitError("The clip range is outside this recording.")

    lines = _clip_lines(project, start, end)
    events = _events(project, start, end)
    text = " ".join(lines)
    language = _language(text or " ".join(events))
    hebrew = language == "he"

    titles: list[str] = []
    strongest = _strongest_line(lines)
    if strongest:
        titles.append(_trim(strongest, TITLE_CHARS))
    if events:
        titles.append(_trim(events[0][:1].upper() + events[0][1:], TITLE_CHARS))
    keywords = _keywords(lines, MAX_HASHTAGS - 1)
    if strongest and keywords:
        lead = keywords[0]
        lead = lead if hebrew else lead[:1].upper() + lead[1:]
        candidate = _trim(f"{lead}: {strongest}", TITLE_CHARS)
        if candidate not in titles:
            titles.append(candidate)
    if lines and len(titles) < MAX_TITLES:
        first = _trim(lines[0], TITLE_CHARS)
        if first not in titles:
            titles.append(first)
    titles = [title for title in titles if title][:MAX_TITLES]

    tags = [_hashtag(word) for word in keywords]
    tags += ["#shorts"] if goal != "youtube" else ["#gaming"] if events else []
    hashtags = list(dict.fromkeys(tag for tag in tags if tag))[:MAX_HASHTAGS]

    description = _trim(text, DESCRIPTION_CHARS - 80) if text else _trim(" · ".join(events), DESCRIPTION_CHARS - 80)
    source = "transcript" if lines else "vision" if events else "none"
    if source == "none":
        note = ("אין תמלול לרגע הזה. הוסיפו תמלול כדי לקבל הצעות מתוך מה שנאמר."
                if hebrew else "This moment has no transcript yet. Add a transcript to get suggestions from what was said.")
    else:
        note = ("נבנה ממה שנאמר ברגע הזה. ערכו לפני פרסום."
                if hebrew else "Built from what is said in this moment. Edit before posting.")
    return {
        "start": round(start, 3), "end": round(end, 3), "language": language, "source": source,
        "titles": titles, "description": description, "hashtags": hashtags, "ai": False, "note": note,
    }


def _clean_titles(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    titles = []
    for item in value:
        title = _trim(str(item or "").strip().strip('"“”'), TITLE_CHARS) if isinstance(item, str) else ""
        if title and title not in titles:
            titles.append(title)
    return titles[:MAX_TITLES]


def _clean_hashtags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags = [_hashtag(str(item).lstrip("#")) for item in value if isinstance(item, str)]
    return list(dict.fromkeys(tag for tag in tags if tag))[:MAX_HASHTAGS]


def ai_posting_kit(
    settings: Any,
    project: dict[str, Any],
    start: Any,
    end: Any,
    *,
    goal: str = "short",
    status: Callable[..., dict[str, Any]] | None = None,
    call: Callable[..., dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    base = build_posting_kit(project, start, end, goal=goal)
    if base["source"] == "none":
        raise PostingKitUnavailable(base["note"])
    if status is None or call is None:
        from .intelligence import _call_ollama, story_ai_status
        status = status or story_ai_status
        call = call or _call_ollama
    ready = status(settings, {"goal": goal})
    if not ready.get("ready"):
        raise PostingKitUnavailable(str(ready.get("message") or "Story AI is not ready. Check AI connection."))
    lines = _clip_lines(project, base["start"], base["end"])
    context = _trim(" ".join(lines), CONTEXT_CHARS)
    events = _events(project, base["start"], base["end"])
    language = "Hebrew" if base["language"] == "he" else "English"
    platform = "a YouTube video section" if goal == "youtube" else "a vertical Short, Reel or TikTok"
    system = (
        "You write posting copy for " + platform + " cut from a creator's own recording. "
        "Use only facts present in the transcript and events. Never invent names, results, numbers or claims. "
        f"Write in {language}. Titles: punchy, under 70 characters, no clickbait lies, no emoji spam. "
        "Return JSON only with keys: titles (3 strings), hook (one short opening line for on-screen text), "
        "description (2 sentences max), hashtags (3 to 6 single words without #)."
    )
    payload = {
        "model": str(ready.get("selected_model") or ""), "stream": False, "format": "json",
        "options": {"temperature": 0.6, "num_ctx": 4096, "num_predict": 400},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"transcript": context, "events": events}, ensure_ascii=False)},
        ],
    }
    try:
        result = call(settings, payload, timeout=90)
    except Exception as error:  # Provider errors are reported, never fatal to the board.
        raise PostingKitUnavailable(f"Story AI could not write the kit: {error}") from error
    if not isinstance(result, dict):
        raise PostingKitUnavailable("Story AI returned no usable answer. The basic kit is still available.")
    titles = _clean_titles(result.get("titles"))
    if not titles:
        raise PostingKitUnavailable("Story AI returned no usable titles. The basic kit is still available.")
    hook = _trim(str(result.get("hook") or ""), TITLE_CHARS) if isinstance(result.get("hook"), str) else ""
    description = _trim(str(result.get("description") or ""), DESCRIPTION_CHARS) if isinstance(result.get("description"), str) else ""
    hashtags = _clean_hashtags(result.get("hashtags")) or base["hashtags"]
    return {
        **base,
        "titles": titles,
        "hook": hook,
        "description": description or base["description"],
        "hashtags": hashtags,
        "ai": True,
        "model": ready.get("selected_model"),
        "note": ("נכתב על ידי ה־AI מתוך מה שנאמר ברגע הזה. בדקו לפני פרסום."
                 if base["language"] == "he" else "Written by AI from what is said in this moment. Check before posting."),
    }
