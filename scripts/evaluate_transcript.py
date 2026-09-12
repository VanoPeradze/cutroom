"""Score local transcript JSON against human reference text, without ASR models."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import unicodedata
from typing import Any, Sequence


def normalize_text(text: str) -> str:
    """Normalize compatibility/case, remove punctuation and invisible formatting."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = unicodedata.normalize("NFKC", text)
    return " ".join("".join(
        char for char in text
        if not unicodedata.category(char).startswith("P")
        and unicodedata.category(char) != "Cf"
    ).split())


def edit_distance(reference: Sequence[str], hypothesis: Sequence[str]) -> int:
    """Exact Levenshtein distance using bit vectors, for words or code points.

    Python's arbitrary-width integers avoid a quadratic Python-level character
    matrix for long recordings. Each bit represents one position in the shorter
    sequence; substitutions, insertions and deletions all have unit cost.
    """
    if len(reference) > len(hypothesis):
        reference, hypothesis = hypothesis, reference
    length = len(reference)
    if not length:
        return len(hypothesis)
    matches: dict[str, int] = {}
    for position, token in enumerate(reference):
        matches[token] = matches.get(token, 0) | (1 << position)
    mask = (1 << length) - 1
    high_bit = 1 << (length - 1)
    positive, negative, distance = mask, 0, length
    for token in hypothesis:
        equal = matches.get(token, 0)
        vertical = equal | negative
        horizontal = (((equal & positive) + positive) ^ positive) | equal
        positive_horizontal = negative | ~(horizontal | positive)
        negative_horizontal = positive & horizontal
        if positive_horizontal & high_bit:
            distance += 1
        elif negative_horizontal & high_bit:
            distance -= 1
        positive_horizontal = (positive_horizontal << 1) | 1
        negative_horizontal <<= 1
        positive = (negative_horizontal | ~(vertical | positive_horizontal)) & mask
        negative = positive_horizontal & vertical
    return distance


def _metric(reference: Sequence[str], hypothesis: Sequence[str]) -> dict[str, Any]:
    errors = edit_distance(reference, hypothesis)
    return {
        "errors": errors,
        "reference_units": len(reference),
        "hypothesis_units": len(hypothesis),
        "rate": errors / len(reference) if reference else (0.0 if not hypothesis else None),
        "status": "ok" if reference else "empty_reference",
    }


def _transcript(document: Any) -> dict[str, Any]:
    if isinstance(document, dict) and "analysis" in document:
        analysis = document["analysis"]
        if not isinstance(analysis, dict) or "transcript" not in analysis:
            raise ValueError("Project JSON must contain analysis.transcript")
        document = analysis["transcript"]
    if isinstance(document, list):
        document = {"segments": document}
    if not isinstance(document, dict) or not any(
        key in document for key in ("text", "segments", "speech_intervals")
    ):
        raise ValueError("Expected transcript text, segments, or speech_intervals")
    if "text" in document and not isinstance(document["text"], str):
        raise ValueError("Transcript text must be a string")
    if "segments" in document:
        if not isinstance(document["segments"], list):
            raise ValueError("Transcript segments must be an array")
        for row in document["segments"]:
            if not isinstance(row, dict) or not isinstance(row.get("text", ""), str):
                raise ValueError("Each segment must be an object with string text")
    return document


def _text(transcript: dict[str, Any]) -> str:
    return normalize_text(transcript.get("text", " ".join(
        segment.get("text", "") for segment in transcript.get("segments", [])
    )))


def _merge_intervals(rows: list[dict[str, Any]]) -> list[tuple[float, float]]:
    intervals = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every timing interval must be an object")
        values = (row.get("start"), row.get("end"))
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise ValueError("Timing start/end must be finite numbers in seconds")
        start, end = map(float, values)
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("Timing requires finite 0 <= start < end")
        intervals.append((start, end))
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _timings(transcript: dict[str, Any], *, reference: bool) -> tuple[Any, str | None]:
    if reference and "speech_intervals" in transcript:
        if not isinstance(transcript["speech_intervals"], list):
            raise ValueError("speech_intervals must be an array")
        return _merge_intervals(transcript["speech_intervals"]), "speech_intervals"
    if "segments" not in transcript:
        return None, None
    segments = transcript["segments"]
    if segments and not any("start" in row or "end" in row for row in segments):
        return None, None
    # Validate all rows before excluding empty-text segments from speech coverage.
    _merge_intervals(segments)
    return _merge_intervals([row for row in segments if normalize_text(row.get("text", ""))]), "segments"


def _timing_metrics(reference: dict[str, Any], hypothesis: dict[str, Any]) -> dict[str, Any]:
    expected, expected_source = _timings(reference, reference=True)
    predicted, predicted_source = _timings(hypothesis, reference=False)
    result: dict[str, Any] = {
        "status": "unavailable",
        "reference_intervals_source": expected_source,
        "hypothesis_intervals_source": predicted_source,
        "speech_coverage": None,
    }
    if expected is None or predicted is None:
        result["reason"] = "Both reference speech intervals and timed hypothesis segments are required"
        return result
    expected_seconds = sum(end - start for start, end in expected)
    predicted_seconds = sum(end - start for start, end in predicted)
    overlap = 0.0
    left = right = 0
    while left < len(expected) and right < len(predicted):
        overlap += max(0.0, min(expected[left][1], predicted[right][1]) - max(expected[left][0], predicted[right][0]))
        if expected[left][1] <= predicted[right][1]:
            left += 1
        else:
            right += 1
    result.update({
        "status": "ok" if expected_seconds else "empty_reference",
        "reference_speech_seconds": expected_seconds,
        "hypothesis_speech_seconds": predicted_seconds,
        "covered_reference_speech_seconds": overlap,
        "missed_reference_speech_seconds": max(0.0, expected_seconds - overlap),
        "outside_reference_speech_seconds": max(0.0, predicted_seconds - overlap),
        "speech_coverage": min(1.0, overlap / expected_seconds) if expected_seconds else None,
    })
    return result


def evaluate(reference: Any, hypothesis: Any) -> dict[str, Any]:
    """Return JSON-safe lexical errors and coverage of annotated speech intervals."""
    reference, hypothesis = _transcript(reference), _transcript(hypothesis)
    expected, predicted = _text(reference), _text(hypothesis)
    return {
        "schema_version": 1,
        "normalization": "NFKC + casefold; Unicode punctuation/format controls removed; whitespace collapsed",
        "wer": _metric(expected.split(), predicted.split()),
        "cer": _metric(expected.replace(" ", ""), predicted.replace(" ", "")),
        "timing": _timing_metrics(reference, hypothesis),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Human reference transcript JSON")
    parser.add_argument("hypothesis", type=Path, help="CUTROOM transcript or project JSON")
    arguments = parser.parse_args(argv)
    try:
        reference = json.loads(arguments.reference.read_text(encoding="utf-8-sig"))
        hypothesis = json.loads(arguments.hypothesis.read_text(encoding="utf-8-sig"))
        result = evaluate(reference, hypothesis)
    except (OSError, UnicodeError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
