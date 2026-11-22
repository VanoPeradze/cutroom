"""Long-form gameplay edit for YouTube: condense a recording, keep its order.

A full gameplay session is mostly travel, menus and quiet stretches around a
few strong passages. This selects the strongest continuous stretches up to the
requested maximum length, keeps them in chronological order, removes silent
menus/loading screens and measured dead air inside what is kept, and proposes
YouTube chapters. It uses only saved, measured evidence (sound levels, optional
transcript timing and optional gameplay vision). It never invents story.
"""
from __future__ import annotations

import math
from typing import Any

from .director import (
    _energy_levels,
    _finite_number,
    _moment_signals,
    _snap_moment_to_speech,
)
from .utils import invert_ranges, merge_ranges, range_duration
from .visual_moments import DEAD_SCREENS, VisualTimeline

LONGFORM_GAMEPLAY_STYLE = "gameplay_youtube"
_BLOCK_SECONDS = {"gentle": 15.0, "balanced": 10.0, "dynamic": 8.0}
_MIN_STRETCH_BLOCKS = {"gentle": 3, "balanced": 2, "dynamic": 2}
_CHAPTER_GAP_SECONDS = 75.0
_MIN_CHAPTER_SECONDS = 10.0
_MAX_CHAPTERS = 12
_MIN_DEAD_AIR_SECONDS = 1.2


def uses_longform_gameplay(goal: Any, brief: dict[str, Any]) -> bool:
    return str(goal or "") == "youtube" and str(brief.get("edit_style") or "") == LONGFORM_GAMEPLAY_STYLE


def _blocks(duration: float, size: float) -> list[tuple[float, float]]:
    count = max(1, math.ceil(duration / size))
    return [(round(index * size, 3), round(min(duration, (index + 1) * size), 3)) for index in range(count)]


def _dead(visual: VisualTimeline | None, start: float, end: float, segments: list[dict[str, Any]]) -> bool:
    if not visual:
        return False
    seen = visual.evidence(start, end)
    if not seen or float(seen.get("dead") or 0.0) < 0.6:
        return False
    return not any(_finite_number(row.get("start")) < end and _finite_number(row.get("end")) > start for row in segments)


def _output_time(source_time: float, keep: list[dict[str, float]]) -> float:
    elapsed = 0.0
    for row in keep:
        if source_time <= row["start"]:
            break
        elapsed += min(source_time, row["end"]) - row["start"]
    return round(elapsed, 3)


def _chapter_title(index: int, start: float, end: float, visual: VisualTimeline | None) -> str:
    seen = visual.evidence(start, end) if visual else None
    event = str((seen or {}).get("event") or "").strip().rstrip(".")
    if event:
        return event if len(event) <= 48 else event[:47].rstrip() + "…"
    return f"Part {index}"


def _chapters(keep: list[dict[str, float]], visual: VisualTimeline | None) -> list[dict[str, Any]]:
    """Group kept stretches by source gaps; YouTube needs 0:00 and 3+ chapters."""
    if not keep:
        return []
    # Every kept stretch starts as a candidate chapter (a cut is a natural seam);
    # the closest neighbours merge until there is about one chapter per
    # _CHAPTER_GAP_SECONDS of finished video, between 3 and _MAX_CHAPTERS.
    output = range_duration(keep)
    wanted = max(3, min(_MAX_CHAPTERS, round(output / _CHAPTER_GAP_SECONDS)))
    groups: list[list[dict[str, float]]] = [[row] for row in keep if row["end"] - row["start"] > 0.5]
    while len(groups) > wanted:
        # Merge the pair separated by the smallest source gap.
        gaps = [groups[i + 1][0]["start"] - groups[i][-1]["end"] for i in range(len(groups) - 1)]
        index = gaps.index(min(gaps))
        groups[index:index + 2] = [groups[index] + groups[index + 1]]
    chapters: list[dict[str, Any]] = []
    for group in groups:
        start, end = group[0]["start"], group[-1]["end"]
        output_start = _output_time(start, keep)
        output_end = _output_time(end, keep)
        if chapters and output_end - output_start < _MIN_CHAPTER_SECONDS:
            chapters[-1]["source_end"] = round(end, 3)
            chapters[-1]["end"] = output_end
            continue
        chapters.append({"start": output_start, "end": output_end, "source_start": round(start, 3), "source_end": round(end, 3)})
    if chapters:
        chapters[0]["start"] = 0.0
    for index, chapter in enumerate(chapters, start=1):
        chapter["title"] = _chapter_title(index, chapter["source_start"], chapter["source_end"], visual)
    return chapters if len(chapters) >= 3 else []


def condense_longform(
    *,
    duration: float,
    target_duration: float,
    sound_profile: dict[str, Any] | None,
    segments: list[dict[str, Any]] | None,
    visual: VisualTimeline | None,
    pace: str = "balanced",
    audio_candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return cuts, counts, chapters and a summary, or None without evidence."""
    duration = _finite_number(duration)
    if duration <= 0:
        return None
    waveform = [row for row in (sound_profile or {}).get("waveform") or [] if isinstance(row, dict)]
    levels = _energy_levels(waveform) if waveform else None
    if not levels:
        return None
    segments = [row for row in segments or [] if isinstance(row, dict)]
    pace = pace if pace in _BLOCK_SECONDS else "balanced"
    size = _BLOCK_SECONDS[pace]
    target = max(60.0, min(duration, _finite_number(target_duration, 600.0)))
    blocks = _blocks(duration, size)
    scores: list[float] = []
    dead_blocks = 0
    for start, end in blocks:
        if _dead(visual, start, end, segments):
            scores.append(-1.0)
            dead_blocks += 1
        else:
            scores.append(float(_moment_signals(start, end, waveform, segments, levels, visual)["score"]))

    chosen = [False] * len(blocks)
    budget = target * 0.92
    used = 0.0
    for index in sorted(range(len(blocks)), key=lambda i: (-scores[i], i)):
        if scores[index] < 0:
            continue
        length = blocks[index][1] - blocks[index][0]
        if used + length > budget + 1e-6:
            continue
        chosen[index] = True
        used += length

    # Fill one-block holes between kept stretches: a jump cut costs more than it saves.
    for index in range(1, len(blocks) - 1):
        if not chosen[index] and chosen[index - 1] and chosen[index + 1] and scores[index] >= 0:
            chosen[index] = True

    def kept_seconds() -> float:
        return sum(end - start for (start, end), selected in zip(blocks, chosen) if selected)

    # The length is a ceiling: shave the weakest block at a stretch edge, so
    # trimming never opens a new jump cut in the middle of a stretch.
    while kept_seconds() > target + 1e-6:
        edges = [i for i, selected in enumerate(chosen) if selected
                 and (i == 0 or not chosen[i - 1] or i == len(blocks) - 1 or not chosen[i + 1])]
        if not edges:
            break
        chosen[min(edges, key=lambda i: (scores[i], -i))] = False
    # Drop stretches too short to follow; their time is not reassigned.
    minimum = _MIN_STRETCH_BLOCKS[pace]
    index = 0
    while index < len(blocks):
        if not chosen[index]:
            index += 1
            continue
        end = index
        while end + 1 < len(blocks) and chosen[end + 1]:
            end += 1
        if end - index + 1 < minimum:
            for position in range(index, end + 1):
                chosen[position] = False
        index = end + 1
    if not any(chosen):
        return None

    keep: list[dict[str, float]] = []
    for (start, end), selected in zip(blocks, chosen):
        if selected:
            if keep and abs(keep[-1]["end"] - start) < 1e-6:
                keep[-1]["end"] = end
            else:
                keep.append({"start": start, "end": end})
    stretches_removed = sum(1 for row in invert_ranges(keep, duration) if row["end"] - row["start"] > 0.5)
    snapped = []
    for row in keep:
        start, end = _snap_moment_to_speech(row["start"], row["end"], segments, duration)
        if end - start >= size:
            snapped.append({"start": round(start, 3), "end": round(end, 3)})
    keep = merge_ranges(snapped, gap=0.0) if snapped else keep

    cuts = merge_ranges(invert_ranges(keep, duration), gap=0.0)
    dead_air = 0
    for item in audio_candidates or []:
        if item.get("reason") != "silence":
            continue
        start, end = _finite_number(item.get("start")), _finite_number(item.get("end"))
        if end - start < _MIN_DEAD_AIR_SECONDS:
            continue
        if any(row["start"] <= start and end <= row["end"] for row in keep):
            cuts.append({"start": round(start, 3), "end": round(end, 3)})
            dead_air += 1
    cuts = merge_ranges(cuts, gap=0.0)
    final_keep = invert_ranges(cuts, duration)
    output = range_duration(final_keep)
    counts = {key: value for key, value in {
        "longform_selection": stretches_removed,
        "dead_screen": dead_blocks,
        "silence": dead_air,
    }.items() if value}
    chapters = _chapters(final_keep, visual)
    summary = (
        f"Condensed {round(duration / 60)} minutes of gameplay to {max(1, round(output / 60))} minutes, "
        f"keeping the strongest stretches in their original order"
        + (" and dropping silent menus and loading screens" if dead_blocks else "")
        + ". Chosen from measured sound" + (" and on-screen action" if visual else "")
        + "; review the cuts before export."
    )
    return {"cuts": cuts, "counts": counts, "chapters": chapters, "summary": summary,
            "seconds": round(output, 3), "stretches": len(final_keep)}
