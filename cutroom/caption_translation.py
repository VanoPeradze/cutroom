"""Translate the edit's captions into a subtitle file in another language.

The translation is a separate .srt for upload next to the video (YouTube,
Instagram and TikTok accept these). The project's own captions, words and
timing are never changed. Lines keep their edit-time timing; Story AI only
rewrites the text, in small batches, and any line it does not return keeps
its original text so the file always matches the video.
"""
from __future__ import annotations

import json
from typing import Any, Callable

LANGUAGES = {
    "en": "English", "he": "Hebrew", "ar": "Arabic", "es": "Spanish", "fr": "French", "de": "German",
    "ru": "Russian", "pt": "Portuguese", "it": "Italian", "hi": "Hindi", "ja": "Japanese", "zh": "Chinese (Simplified)",
}
BATCH = 30
MAX_LINES = 1500
MAX_CHARS = 300


class TranslationUnavailable(RuntimeError):
    """Story AI is not ready or gave nothing usable."""


def srt_time(seconds: float) -> str:
    ms = max(0, int(round(float(seconds) * 1000)))
    return f"{ms // 3_600_000:02d}:{ms // 60_000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def caption_lines(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Visible caption lines in edit time: [{start, end, text}]."""
    lines = []
    for item in items or []:
        if item.get("hidden"):
            continue
        text = " ".join(str(item.get("text") or "").split())[:MAX_CHARS]
        start, end = float(item.get("start") or 0), float(item.get("end") or 0)
        if text and end > start:
            lines.append({"start": start, "end": end, "text": text})
    return sorted(lines, key=lambda line: line["start"])[:MAX_LINES]


def build_srt(lines: list[dict[str, Any]]) -> str:
    blocks = [f"{n}\n{srt_time(line['start'])} --> {srt_time(line['end'])}\n{line['text']}\n"
              for n, line in enumerate(lines, 1)]
    return "\n".join(blocks)


def translate_lines(lines: list[dict[str, Any]], language: str, ask: Callable[[list[dict[str, Any]], str], Any]) -> tuple[list[dict[str, Any]], int]:
    """Returns (translated lines, number of lines Story AI actually translated)."""
    name = LANGUAGES[language]
    out = [dict(line) for line in lines]
    done = 0
    for first in range(0, len(lines), BATCH):
        chunk = [{"i": first + k, "text": line["text"]} for k, line in enumerate(lines[first:first + BATCH])]
        answer = ask(chunk, name)
        rows = answer.get("lines") if isinstance(answer, dict) else None
        if not isinstance(rows, list):
            continue
        wanted = {row["i"] for row in chunk}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("text"), str):
                continue
            try:
                index = int(row.get("i"))
            except (TypeError, ValueError):
                continue
            text = " ".join(row["text"].split())[:MAX_CHARS]
            if index in wanted and text:
                out[index]["text"] = text
                wanted.discard(index)
                done += 1
    return out, done


def translate_project_captions(settings: Any, items: list[dict[str, Any]], language: str, *,
                               status: Callable[..., dict[str, Any]] | None = None,
                               call: Callable[..., Any] | None = None) -> dict[str, Any]:
    if language not in LANGUAGES:
        raise ValueError("Choose a supported language.")
    lines = caption_lines(items)
    if not lines:
        raise TranslationUnavailable("There are no captions to translate. Transcribe the recording first.")
    if status is None or call is None:
        from .intelligence import _call_ollama, story_ai_status
        status = status or story_ai_status
        call = call or _call_ollama
    ready = status(settings, {"goal": "short"})
    if not ready.get("ready"):
        raise TranslationUnavailable(str(ready.get("message") or "Story AI is not ready. Check AI connection."))
    model = str(ready.get("selected_model") or "")

    def ask(chunk: list[dict[str, Any]], name: str) -> Any:
        system = (
            f"You translate video subtitles into {name}. Translate each line's meaning naturally and briefly, "
            "as spoken subtitles. Keep names, numbers and brand names. Do not add, merge, split or explain lines. "
            'Return JSON only: {"lines": [{"i": <same number>, "text": "<translation>"}]} with one entry per input line.'
        )
        payload = {
            "model": model, "stream": False, "format": "json",
            "options": {"temperature": 0.2, "num_ctx": 4096, "num_predict": 1600},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps({"lines": chunk}, ensure_ascii=False)}],
        }
        try:
            return call(settings, payload, timeout=120)
        except Exception as error:  # Reported to the user; the project is untouched.
            raise TranslationUnavailable(f"Story AI could not translate: {error}") from error

    translated, done = translate_lines(lines, language, ask)
    if not done:
        raise TranslationUnavailable("Story AI returned no usable translation. Try again or choose another model.")
    return {"srt": build_srt(translated), "language": language, "language_name": LANGUAGES[language],
            "lines": len(lines), "translated": done, "model": ready.get("selected_model")}
