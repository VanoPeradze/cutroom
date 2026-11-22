"""Score a CUTROOM edit against a human reference, offline and read-only.

One recording: ``evaluate_edit.py reference.json project.json``.
An evaluation set: ``evaluate_edit.py --suite suite.json`` where the manifest
lists reference/project pairs and optional pass thresholds. The report is JSON
on stdout; exit code 1 means a suite threshold failed, 2 means bad input.

Everything is on the source A clock (seconds), the same clock the reference
author hears when playing the original recording. Nothing is rendered,
transcribed or sent anywhere. See docs/EDIT_EVALUATION.md.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLDS = {
    "must_keep_recall": 0.9,     # at least 90% of must-keep seconds stay
    "must_cut_leak": 0.2,        # at most 20% of must-cut seconds survive
    "highlight_hit_rate": 0.5,   # half the human highlights appear on the Clips board
    "mid_word_cut_rate": 0.1,    # at most 10% of cut boundaries split a word
}


class InputError(ValueError):
    pass


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InputError(f"{path}: {error}") from error


def _ranges(rows: Any, name: str) -> list[tuple[float, float]]:
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise InputError(f"{name} must be an array of {{start, end}} objects.")
    clean = []
    for row in rows:
        try:
            start, end = float(row["start"]), float(row["end"])
        except (TypeError, KeyError, ValueError) as error:
            raise InputError(f"{name} entries need numeric start and end.") from error
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise InputError(f"{name} entries need 0 <= start < end.")
        clean.append((start, end))
    return _merge(clean)


def _merge(rows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(rows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _total(rows: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in rows)


def _overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    total, i, j = 0.0, 0, 0
    while i < len(a) and j < len(b):
        total += max(0.0, min(a[i][1], b[j][1]) - max(a[i][0], b[j][0]))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return total


def _ratio(numerator: float, denominator: float) -> float | None:
    return round(numerator / denominator, 4) if denominator > 0 else None


def _kept_ranges(project: dict[str, Any]) -> list[tuple[float, float]]:
    draft = project.get("draft") or {}
    keeps = _ranges(draft.get("keep_ranges"), "draft.keep_ranges")
    if keeps:
        return keeps
    duration = float(((project.get("sources") or {}).get("A") or {}).get("duration") or 0)
    return [(0.0, duration)] if duration > 0 else []


def _words(project: dict[str, Any]) -> list[tuple[float, float]]:
    analysis = project.get("analysis") or {}
    transcript = analysis.get("transcript") or {}
    segments = transcript.get("segments") if isinstance(transcript, dict) else None
    segments = segments if isinstance(segments, list) else analysis.get("segments") or []
    words = []
    for segment in segments:
        for word in (segment or {}).get("words") or []:
            try:
                start, end = float(word["start"]), float(word["end"])
            except (TypeError, KeyError, ValueError):
                continue
            if math.isfinite(start) and math.isfinite(end) and end > start:
                words.append((start, end))
    return sorted(words)


def _mid_word_boundaries(keeps: list[tuple[float, float]], words: list[tuple[float, float]], duration: float) -> tuple[int, int]:
    """Cut boundaries strictly inside a word (more than 40 ms from either edge)."""
    boundaries = [edge for start, end in keeps for edge in (start, end) if 0.05 < edge < duration - 0.05]
    split = sum(1 for edge in boundaries if any(start + 0.04 < edge < end - 0.04 for start, end in words))
    return split, len(boundaries)


def _board(project: dict[str, Any], length: int, count: int) -> list[tuple[float, float]] | None:
    try:
        sys.path.insert(0, str(ROOT))
        from cutroom.clip_board import build_clip_board
        board = build_clip_board(project, length=length, count=count)
    except Exception:  # The board is optional; a missing analysis is not an input error.
        return None
    if not board.get("available"):
        return None
    return [(float(clip["start"]), float(clip["end"])) for clip in board.get("clips") or []]


def evaluate(reference: dict[str, Any], project: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(reference, dict) or not isinstance(project, dict):
        raise InputError("The reference and the project must be JSON objects.")
    must_keep = _ranges(reference.get("must_keep"), "must_keep")
    must_cut = _ranges(reference.get("must_cut"), "must_cut")
    highlights = _ranges(reference.get("highlights"), "highlights")
    if _overlap(must_keep, must_cut) > 0:
        raise InputError("must_keep and must_cut overlap; a second cannot be both.")
    keeps = _kept_ranges(project)
    duration = float(((project.get("sources") or {}).get("A") or {}).get("duration") or 0) or (keeps[-1][1] if keeps else 0)
    output = _total(keeps)
    report: dict[str, Any] = {
        "project_id": project.get("id"),
        "source_duration": round(duration, 3),
        "output_duration": round(output, 3),
        "kept_ratio": _ratio(output, duration),
        "must_keep_recall": _ratio(_overlap(must_keep, keeps), _total(must_keep)),
        "must_cut_leak": _ratio(_overlap(must_cut, keeps), _total(must_cut)),
    }
    target = reference.get("target_duration")
    if isinstance(target, (int, float)) and not isinstance(target, bool) and target > 0:
        report["target_duration"] = float(target)
        report["duration_error"] = round(abs(output - float(target)) / float(target), 4)
    split, boundaries = _mid_word_boundaries(keeps, _words(project), duration)
    report["cut_boundaries"] = boundaries
    report["mid_word_cuts"] = split
    report["mid_word_cut_rate"] = _ratio(split, boundaries) if boundaries else 0.0
    if highlights:
        length = int(reference.get("clip_length") or 30)
        board = _board(project, length if length in (15, 30, 45, 60, 90) else 30,
                       max(1, min(int(reference.get("clip_count") or max(len(highlights), 5)), 20)))
        if board is None:
            report["highlight_hit_rate"] = None
            report["highlight_note"] = "The Clips board is unavailable for this project (missing audio profile)."
        else:
            hits = [any(start < b_end and end > b_start for b_start, b_end in board) for start, end in highlights]
            useful = [any(start < h_end and end > h_start for h_start, h_end in highlights) for start, end in board]
            report["highlight_hit_rate"] = _ratio(sum(hits), len(hits))
            report["board_precision"] = _ratio(sum(useful), len(useful))
    chapters = reference.get("chapters")
    found = (project.get("draft") or {}).get("chapters") or []
    if isinstance(chapters, list) and chapters:
        try:
            wanted = sorted(float(row["source_start"] if isinstance(row, dict) else row) for row in chapters)
        except (TypeError, KeyError, ValueError) as error:
            raise InputError("chapters must be numbers or {source_start} objects.") from error
        starts = [float(row.get("source_start", row.get("start", 0))) for row in found if isinstance(row, dict)]
        report["chapter_count"] = {"reference": len(wanted), "draft": len(starts)}
        report["chapter_mean_error_seconds"] = (
            round(sum(min(abs(time - other) for other in starts) for time in wanted) / len(wanted), 2) if starts else None)
    return report


def _passes(report: dict[str, Any], thresholds: dict[str, float]) -> list[str]:
    failures = []
    for key, limit in thresholds.items():
        value = report.get(key)
        if value is None:
            continue
        higher_is_better = key in {"must_keep_recall", "highlight_hit_rate", "board_precision"}
        if (value < limit) if higher_is_better else (value > limit):
            failures.append(f"{key}={value} (limit {limit})")
    return failures


def run_suite(manifest_path: Path) -> tuple[dict[str, Any], bool]:
    manifest = _load(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("cases"), list) or not manifest["cases"]:
        raise InputError("The suite needs a non-empty cases array.")
    thresholds = {**DEFAULT_THRESHOLDS, **(manifest.get("thresholds") or {})}
    base = manifest_path.parent
    results, ok = [], True
    for index, case in enumerate(manifest["cases"], start=1):
        if not isinstance(case, dict) or not case.get("reference") or not case.get("project"):
            raise InputError(f"Case {index} needs reference and project paths.")
        report = evaluate(_load(base / case["reference"]), _load(base / case["project"]))
        failures = _passes(report, thresholds)
        ok = ok and not failures
        results.append({"name": case.get("name") or f"case-{index}", **report, "passed": not failures, "failures": failures})
    summary: dict[str, Any] = {"cases": len(results), "passed": sum(row["passed"] for row in results)}
    for key in ("must_keep_recall", "must_cut_leak", "highlight_hit_rate", "board_precision", "mid_word_cut_rate", "duration_error"):
        values = [row[key] for row in results if isinstance(row.get(key), (int, float))]
        if values:
            summary[f"mean_{key}"] = round(sum(values) / len(values), 4)
    return {"thresholds": thresholds, "summary": summary, "results": results}, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", nargs="?", type=Path)
    parser.add_argument("project", nargs="?", type=Path)
    parser.add_argument("--suite", type=Path, help="manifest of reference/project pairs")
    args = parser.parse_args(argv)
    try:
        if args.suite:
            report, ok = run_suite(args.suite)
        elif args.reference and args.project:
            report, ok = evaluate(_load(args.reference), _load(args.project)), True
        else:
            parser.error("give reference and project, or --suite manifest.json")
    except InputError as error:
        print(f"evaluate_edit: {error}", file=sys.stderr)
        return 2
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
