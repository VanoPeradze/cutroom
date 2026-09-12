from __future__ import annotations

import math
from pathlib import Path
from typing import Any


CAPTION_STYLE_CHOICES = frozenset({"clean", "bold", "boxed"})
CAPTION_POSITION_CHOICES = frozenset({"auto", "top", "center", "bottom"})
CAPTION_SCALE_RANGE = (75, 150)
CAPTION_WORDS_PER_LINE_RANGE = (2, 12)
DEFAULT_CAPTION_SETTINGS: dict[str, Any] = {
    "caption_style": "bold",
    "caption_position": "auto",
    "caption_scale": 100,
    "caption_words_per_line": 9,
}


def normalize_caption_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    """Return a safe, backward-compatible caption rendering contract.

    HTTP writes are validated strictly in ``server.py``.  This second boundary
    keeps legacy/imported project JSON from reaching ASS as unchecked values and
    gives projects created before these controls the historical CUTROOM look.
    """

    value = settings if isinstance(settings, dict) else {}
    style = str(value.get("caption_style") or DEFAULT_CAPTION_SETTINGS["caption_style"]).strip().lower()
    if style not in CAPTION_STYLE_CHOICES:
        style = str(DEFAULT_CAPTION_SETTINGS["caption_style"])
    position = str(value.get("caption_position") or DEFAULT_CAPTION_SETTINGS["caption_position"]).strip().lower()
    if position not in CAPTION_POSITION_CHOICES:
        position = str(DEFAULT_CAPTION_SETTINGS["caption_position"])
    scale = value.get("caption_scale", DEFAULT_CAPTION_SETTINGS["caption_scale"])
    if isinstance(scale, bool) or not isinstance(scale, int) or not CAPTION_SCALE_RANGE[0] <= scale <= CAPTION_SCALE_RANGE[1]:
        scale = int(DEFAULT_CAPTION_SETTINGS["caption_scale"])
    words = value.get("caption_words_per_line", DEFAULT_CAPTION_SETTINGS["caption_words_per_line"])
    if isinstance(words, bool) or not isinstance(words, int) or not CAPTION_WORDS_PER_LINE_RANGE[0] <= words <= CAPTION_WORDS_PER_LINE_RANGE[1]:
        words = int(DEFAULT_CAPTION_SETTINGS["caption_words_per_line"])
    return {
        "caption_style": style,
        "caption_position": position,
        "caption_scale": scale,
        "caption_words_per_line": words,
    }


_LAYOUT_AWARE_CAPTION_POSITIONS = {
    # A normal two-source stack can place the camera in either the upper 30% or
    # upper 70% of the frame.  Starting the caption below both possible split
    # points keeps it out of the creator panel without pushing it into the
    # platform controls at the bottom edge.
    "stacked": 0.74,
    # Embedded facecam composition is fixed by the renderer: camera in the upper
    # 30%, screen below it.  Put the caption just inside the screen panel so it
    # does not cover the creator or the lower gameplay HUD.
    "embedded_stack": 0.34,
}


def _timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _output_time(original_time: float, keep_ranges: list[dict[str, Any]]) -> float | None:
    cursor = 0.0
    for item in keep_ranges:
        start, end = float(item["start"]), float(item["end"])
        if start <= original_time <= end:
            return cursor + original_time - start
        cursor += max(0.0, end - start)
    return None


def _segment_kept_intervals(start: float, end: float, keep_ranges: list[dict[str, Any]]) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for keep in keep_ranges:
        keep_start, keep_end = float(keep["start"]), float(keep["end"])
        overlap_start, overlap_end = max(start, keep_start), min(end, keep_end)
        if overlap_end - overlap_start >= 0.05:
            intervals.append((overlap_start, overlap_end))
    return intervals


def build_srt(
    transcript: dict[str, Any],
    keep_ranges: list[dict[str, Any]],
    target: Path,
    *,
    words_per_caption: int | None = None,
) -> Path:
    if words_per_caption is not None:
        if isinstance(words_per_caption, bool) or not isinstance(words_per_caption, int):
            words_per_caption = int(DEFAULT_CAPTION_SETTINGS["caption_words_per_line"])
        words_per_caption = max(CAPTION_WORDS_PER_LINE_RANGE[0], min(CAPTION_WORDS_PER_LINE_RANGE[1], words_per_caption))
    entries = _caption_entries(transcript, keep_ranges, words_per_caption)
    lines: list[str] = []
    for index, (start, end, text) in enumerate(entries, 1):
        lines.extend([str(index), f"{_timestamp(start)} --> {_timestamp(end)}", text, ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target



def _ass_timestamp(seconds: float) -> str:
    centis = max(0, int(round(float(seconds) * 100)))
    hours, remainder = divmod(centis, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, centis = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def _ass_escape(text: str) -> str:
    return str(text).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _caption_entries(
    transcript: dict[str, Any],
    keep_ranges: list[dict[str, Any]],
    words_per_caption: int | None = 9,
) -> list[tuple[float, float, str]]:
    if words_per_caption is not None:
        words_per_caption = max(CAPTION_WORDS_PER_LINE_RANGE[0], min(CAPTION_WORDS_PER_LINE_RANGE[1], int(words_per_caption)))
    entries: list[tuple[float, float, str]] = []
    for segment in transcript.get("segments", []):
        words = segment.get("words") or []
        if words:
            output_cursor = 0.0
            for keep in keep_ranges:
                keep_start, keep_end = float(keep["start"]), float(keep["end"])
                chunks: list[list[dict[str, Any]]] = [[]]
                for word in words:
                    word_start, word_end = float(word["start"]), float(word["end"])
                    midpoint = (word_start + word_end) / 2
                    if not keep_start <= midpoint < keep_end or word_end <= word_start:
                        continue
                    if chunks[-1] and (
                        word_start - float(chunks[-1][-1]["end"]) > 0.75
                        or (words_per_caption is not None and len(chunks[-1]) >= words_per_caption)
                    ):
                        chunks.append([])
                    chunks[-1].append(word)
                for chunk in chunks:
                    if not chunk:
                        continue
                    # Clip a spoken word crossing a cut to the kept interval.
                    # Project each interval separately so captions neither vanish
                    # at trim edges nor bridge speech removed between two clips.
                    start = output_cursor + max(keep_start, float(chunk[0]["start"])) - keep_start
                    end = output_cursor + min(keep_end, float(chunk[-1]["end"])) - keep_start
                    text = " ".join(str(word.get("word", "")).strip() for word in chunk).strip()
                    if text and end > start:
                        entries.append((start, end, text))
                output_cursor += max(0.0, keep_end - keep_start)
        else:
            text = str(segment.get("text", "")).strip()
            for overlap_start, overlap_end in _segment_kept_intervals(float(segment["start"]), float(segment["end"]), keep_ranges):
                start = _output_time(overlap_start, keep_ranges)
                end = _output_time(overlap_end, keep_ranges)
                if text and start is not None and end is not None and end > start:
                    entries.append((start, end, text))
    return entries


def _finite_time(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _project_layout_ranges(
    layout_ranges: list[dict[str, Any]] | None,
    keep_ranges: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map supported source-time layouts onto the edited output clock.

    ``layout_ranges`` deliberately mirrors the render plan.  Each row is:

    ``{"start": <source seconds>, "end": <source seconds>, "layout": "stacked"}``

    The render plan's ``camera`` key is accepted as an alias for ``layout``, so
    callers may pass plan rows directly.  Invalid, non-finite, reversed and
    unknown rows are ignored; metadata must never be able to inject ASS tags.
    """

    if not isinstance(layout_ranges, list) or not layout_ranges:
        return []
    source_rows: list[dict[str, Any]] = []
    for order, item in enumerate(layout_ranges):
        if not isinstance(item, dict):
            continue
        start = _finite_time(item.get("start"))
        end = _finite_time(item.get("end"))
        layout = str(item.get("layout") or item.get("camera") or "").strip().lower()
        if start is None or end is None or end <= start or layout not in _LAYOUT_AWARE_CAPTION_POSITIONS:
            continue
        source_rows.append({"start": start, "end": end, "layout": layout, "order": order})

    projected: list[dict[str, Any]] = []
    output_cursor = 0.0
    for keep in keep_ranges:
        keep_start = _finite_time(keep.get("start")) if isinstance(keep, dict) else None
        keep_end = _finite_time(keep.get("end")) if isinstance(keep, dict) else None
        if keep_start is None or keep_end is None or keep_end <= keep_start:
            continue
        for row in source_rows:
            overlap_start = max(keep_start, float(row["start"]))
            overlap_end = min(keep_end, float(row["end"]))
            if overlap_end <= overlap_start:
                continue
            projected.append({
                "start": output_cursor + overlap_start - keep_start,
                "end": output_cursor + overlap_end - keep_start,
                "layout": row["layout"],
                "source_start": row["start"],
                "order": row["order"],
            })
        output_cursor += keep_end - keep_start
    return projected


def _layout_at(output_time: float, projected: list[dict[str, Any]]) -> str | None:
    active = [
        item
        for item in projected
        if float(item["start"]) <= output_time < float(item["end"])
    ]
    if not active:
        return None
    # Render plans are normally non-overlapping.  If malformed metadata overlaps,
    # the most recently starting row (then the later input row) wins predictably.
    return str(max(active, key=lambda item: (float(item["start"]), int(item["order"])))["layout"])


def _entries_with_layout(
    entries: list[tuple[float, float, str]],
    projected: list[dict[str, Any]],
) -> list[tuple[float, float, str, str | None]]:
    if not projected:
        return [(start, end, text, None) for start, end, text in entries]
    output: list[tuple[float, float, str, str | None]] = []
    for start, end, text in entries:
        boundaries = {float(start), float(end)}
        for item in projected:
            item_start = float(item["start"])
            item_end = float(item["end"])
            if start < item_start < end:
                boundaries.add(item_start)
            if start < item_end < end:
                boundaries.add(item_end)
        ordered = sorted(boundaries)
        for piece_start, piece_end in zip(ordered, ordered[1:]):
            # ASS timestamps have centisecond precision.  Do not emit a zero-time
            # event when two metadata boundaries are closer than that precision.
            if round(piece_end * 100) <= round(piece_start * 100):
                continue
            midpoint = piece_start + (piece_end - piece_start) / 2
            output.append((piece_start, piece_end, text, _layout_at(midpoint, projected)))
    return output


def _layout_override(
    layout: str | None,
    width: int,
    height: int,
    font_size: int,
    margin_v: int,
    outline: int,
) -> str:
    ratio = _LAYOUT_AWARE_CAPTION_POSITIONS.get(str(layout or ""))
    if ratio is None:
        return ""
    center_x = max(1, int(round(width / 2)))
    minimum_y = max(1, margin_v + outline)
    maximum_y = max(minimum_y, height - margin_v - font_size * 2)
    top_y = max(minimum_y, min(maximum_y, int(round(height * ratio))))
    # an8 makes pos() the top-centre anchor, so wrapped RTL text grows downward
    # into the safe panel rather than back over the creator's face.
    return f"{{\\an8\\pos({center_x},{top_y})}}"


def build_ass(
    transcript: dict[str, Any],
    keep_ranges: list[dict[str, Any]],
    target: Path,
    width: int,
    height: int,
    layout_ranges: list[dict[str, Any]] | None = None,
    *,
    caption_style: str = "bold",
    caption_position: str = "auto",
    caption_scale: int = 100,
    words_per_caption: int = 9,
) -> Path:
    """Build burn-in captions retimed to the edited sequence.

    ASS is used instead of drawtext so Hebrew/Arabic shaping and ordinary Unicode
    subtitles can be handled by libass in a single lightweight render filter.

    ``layout_ranges`` is optional and backward-compatible.  It uses source-time
    rows shaped like ``{"start": 1.0, "end": 4.0, "layout": "stacked"}``.
    ``camera`` may replace ``layout`` so a render-plan row can be supplied
    directly.  Only ``stacked`` and ``embedded_stack`` affect positioning;
    missing or invalid metadata preserves the historical bottom-centred output.
    User-facing style values are deliberately finite presets so project metadata
    can never inject arbitrary ASS syntax.
    """
    normalized = normalize_caption_settings({
        "caption_style": caption_style,
        "caption_position": caption_position,
        "caption_scale": caption_scale,
        "caption_words_per_line": words_per_caption,
    })
    caption_style = normalized["caption_style"]
    caption_position = normalized["caption_position"]
    caption_scale = normalized["caption_scale"]
    words_per_caption = normalized["caption_words_per_line"]
    entries = _caption_entries(transcript, keep_ranges, words_per_caption)
    base_font_size = max(28, min(72, round(height * (0.048 if height >= width else 0.042))))
    font_size = max(20, min(108, round(base_font_size * caption_scale / 100)))
    margin_v = max(32, round(height * 0.075))
    style_values = {
        "bold": {
            "bold": -1, "border_style": 1, "outline": max(2, round(font_size * 0.09)),
            "shadow": 0, "outline_color": "&HCC000000", "back_color": "&H66000000",
        },
        "clean": {
            "bold": 0, "border_style": 1, "outline": max(1, round(font_size * 0.055)),
            "shadow": max(1, round(font_size * 0.025)), "outline_color": "&HD9000000", "back_color": "&H99000000",
        },
        "boxed": {
            "bold": -1, "border_style": 3, "outline": max(3, round(font_size * 0.12)),
            "shadow": 0, "outline_color": "&H00131008", "back_color": "&H99131008",
        },
    }[caption_style]
    outline = int(style_values["outline"])
    alignment = {"auto": 2, "bottom": 2, "center": 5, "top": 8}[caption_position]
    projected_layouts = _project_layout_ranges(layout_ranges, keep_ranges) if caption_position == "auto" else []
    positioned_entries = _entries_with_layout(entries, projected_layouts)
    header = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nScaledBorderAndShadow: yes\nWrapStyle: 2\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,{style_values['outline_color']},{style_values['back_color']},{style_values['bold']},0,0,0,100,100,0,0,{style_values['border_style']},{outline},{style_values['shadow']},{alignment},42,42,{margin_v},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"""
    lines = [header]
    for start, end, value, layout in positioned_entries:
        if not value:
            continue
        override = _layout_override(layout, width, height, font_size, margin_v, outline)
        lines.append(
            f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,"
            f"{override}{_ass_escape(value)}\n"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(lines), encoding="utf-8-sig")
    return target
