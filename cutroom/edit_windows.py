"""Experimental source views and pure clip geometry; NOT wired to the editor.

Canonical ASR rows have one owner. Windows may overlap because they are views,
not alternate transcript owners. Selection resolves them to nonrepeating source
intervals. Nothing here judges meaning, creates a draft, saves or applies edits.
Only whole ASR row boundaries are supported; these are not verified sentence,
speaker, word-accurate or frame-accurate boundaries.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from typing import Any, Callable, Sequence

from .instruction_contract import assert_instruction_contract, effective_duration_bounds

ENABLED_BY_DEFAULT = False  # No production caller; enabling requires a later integration.
VERSION = 1
BOUNDARY_POLICY = "whole-asr-rows-v1"
MAX_ROWS = 20_000
MAX_SELECTED_WINDOWS = 200


class EditWindowError(ValueError):
    """Invalid/stale geometry or unsupported selection, not semantic no-fit."""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _identity(kind: str, value: Any) -> str:
    return kind + ":" + hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise EditWindowError(name + " must be a finite number")
    return float(value)


def _version(value: Any) -> None:
    if type(value) is not int or value != VERSION:
        raise EditWindowError("Unsupported source/view schema version")


@dataclass(frozen=True)
class SourceDescriptor:
    """Caller-supplied identity; no assertion that media was probed or hashed.

    source_seconds = ASR row seconds + asr_origin_seconds. Versions must come
    from the authoritative asset/transcript store, never from a model response.
    """
    asset_id: str
    asset_version: str
    transcript_version: str
    asset_duration: float
    asr_origin_seconds: float = 0.
    timebase: str = "seconds"
    version: int = VERSION

    def __post_init__(self) -> None:
        _version(self.version)
        for name in ("asset_id", "asset_version", "transcript_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise EditWindowError(name + " is required")
        duration = _number(self.asset_duration, "asset duration")
        origin = _number(self.asr_origin_seconds, "ASR origin")
        if self.timebase != "seconds" or duration <= 0 or not 0 <= origin < duration:
            raise EditWindowError("Unsupported timebase or source extent")
        object.__setattr__(self, "asset_duration", duration)
        object.__setattr__(self, "asr_origin_seconds", origin)


@dataclass(frozen=True)
class CanonicalRow:
    id: str
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class CanonicalSource:
    """Detached immutable snapshot, including original words and ASR metadata.

    JSON storage avoids a mutable dict hidden inside a frozen dataclass. Export
    returns a fresh copy. Input order, text and metadata are never repaired.
    """
    descriptor: SourceDescriptor
    transcript_json: str = field(repr=False)
    rows: tuple[CanonicalRow, ...] = field(init=False)
    fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, SourceDescriptor):
            raise EditWindowError("A versioned source descriptor is required")
        try:
            data = json.loads(self.transcript_json)
            encoded = _json(data)
        except (TypeError, ValueError) as exc:
            raise EditWindowError("Transcript must be finite JSON") from exc
        if not isinstance(data, list) or not 0 < len(data) <= MAX_ROWS:
            raise EditWindowError("Canonical source requires 1..20000 ASR rows")
        rows, seen, previous_end = [], set(), 0.
        for item in data:
            if not isinstance(item, dict):
                raise EditWindowError("Canonical rows must be objects")
            row_id, text = item.get("id"), item.get("text")
            if not isinstance(row_id, str) or not row_id.strip() or row_id in seen:
                raise EditWindowError("Canonical row IDs must be nonempty and unique")
            if not isinstance(text, str) or not text.strip():
                raise EditWindowError("Canonical text is required; no source rewriting")
            start, end = _number(item.get("start"), "ASR start"), _number(item.get("end"), "ASR end")
            if start < previous_end or end <= start or end + self.descriptor.asr_origin_seconds > self.descriptor.asset_duration:
                raise EditWindowError("ASR rows must be ordered, nonoverlapping and inside the source")
            origin = self.descriptor.asr_origin_seconds
            mapped_start, mapped_end = start + origin, end + origin
            # Never let float loss turn a positive row/gap into zero duration,
            # accidental overlap or a changed source interval at large offsets.
            if (mapped_end <= mapped_start or
                abs((mapped_end - mapped_start) - (end - start)) > 1e-8 or
                abs((mapped_start - (previous_end + origin)) - (start - previous_end)) > 1e-8):
                raise EditWindowError("Source offset exceeds supported seconds precision")
            rows.append(CanonicalRow(row_id, start, end, text))
            seen.add(row_id)
            previous_end = end
        object.__setattr__(self, "transcript_json", encoded)
        object.__setattr__(self, "rows", tuple(rows))
        object.__setattr__(self, "fingerprint", _identity("source", [asdict(self.descriptor), data]))

    def transcript(self) -> list[dict[str, Any]]:
        return json.loads(self.transcript_json)


def build_canonical_source(rows: list[dict[str, Any]], descriptor: SourceDescriptor) -> CanonicalSource:
    try:
        encoded = _json(rows)
    except (TypeError, ValueError) as exc:
        raise EditWindowError("Transcript must be finite JSON") from exc
    return CanonicalSource(descriptor, encoded)


@dataclass(frozen=True)
class SourceGap:
    left_id: str
    right_id: str
    start: float
    end: float
    status: str = "untranscribed_unverified"


@dataclass(frozen=True)
class EditWindow:
    id: str
    source_fingerprint: str
    row_ids: tuple[str, ...]
    asr_start: float
    asr_end: float
    source_start: float
    source_end: float
    context_before: str | None
    context_after: str | None
    gaps: tuple[SourceGap, ...]
    version: int = VERSION
    boundary_policy: str = BOUNDARY_POLICY
    boundary_evidence: str = "canonical_asr_rows_only"
    context_role: str = "reference_only_not_selected"
    editorial_status: str = "unreviewed"


def _window(source: CanonicalSource, first: int, last: int) -> EditWindow:
    rows, origin = source.rows[first:last + 1], source.descriptor.asr_origin_seconds
    return EditWindow(
        _identity("window", [VERSION, BOUNDARY_POLICY, source.fingerprint, rows[0].id, rows[-1].id]),
        source.fingerprint, tuple(row.id for row in rows), rows[0].start, rows[-1].end,
        rows[0].start + origin, rows[-1].end + origin,
        source.rows[first - 1].id if first else None,
        source.rows[last + 1].id if last + 1 < len(source.rows) else None,
        tuple(SourceGap(a.id, b.id, a.end + origin, b.start + origin)
              for a, b in zip(rows, rows[1:]) if b.start > a.end),
    )


def build_edit_window(source: CanonicalSource, first_id: str, last_id: str) -> EditWindow:
    positions = {row.id: i for i, row in enumerate(source.rows)}
    if first_id not in positions or last_id not in positions or positions[first_id] > positions[last_id]:
        raise EditWindowError("Window requires ordered canonical row boundary IDs")
    return _window(source, positions[first_id], positions[last_id])


def validate_window(source: CanonicalSource, window: EditWindow) -> None:
    if not isinstance(window, EditWindow):
        raise EditWindowError("A source window is required")
    _version(window.version)
    for name in ("asr_start", "asr_end", "source_start", "source_end"):
        _number(getattr(window, name), name)
    for gap in window.gaps:
        if not isinstance(gap, SourceGap):
            raise EditWindowError("Window gap must reference canonical row boundaries")
        _number(gap.start, "gap start")
        _number(gap.end, "gap end")
    if window.source_fingerprint != source.fingerprint or not window.row_ids:
        raise EditWindowError("Stale source/asset/transcript version or empty window")
    expected = build_edit_window(source, window.row_ids[0], window.row_ids[-1])
    if expected != window:
        raise EditWindowError("Window does not match immutable canonical boundaries/context")


def window_rows(source: CanonicalSource, window: EditWindow) -> tuple[CanonicalRow, ...]:
    validate_window(source, window)
    selected = set(window.row_ids)
    return tuple(row for row in source.rows if row.id in selected)


@dataclass(frozen=True)
class WindowCursor:
    query_fingerprint: str
    first: int
    last: int


@dataclass(frozen=True)
class WindowPage:
    windows: tuple[EditWindow, ...]
    inspected_pairs: int
    started_at: tuple[int, int]
    next_cursor: WindowCursor | None
    end_reached: bool  # Traversal exhausted, NOT semantic coverage or no-fit.


def enumerate_edit_windows(
    source: CanonicalSource, *, minimum_seconds: float = 0., maximum_seconds: float = 120.,
    max_windows: int = 128, max_pairs: int = 4096, cursor: WindowCursor | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> WindowPage:
    """Bounded continuous-window index, in source order, resumable without IO.

    No combinations of disjoint runs, scoring, semantic pruning or first-N
    coverage claim. Context neighbors are references, not compulsory inclusion.
    Cancellation propagates; the immutable source and caller cursor stay intact.
    """
    minimum, maximum = _number(minimum_seconds, "minimum"), _number(maximum_seconds, "maximum")
    if not 0 <= minimum <= maximum or maximum == 0:
        raise EditWindowError("Invalid window duration bounds")
    if type(max_windows) is not int or not 1 <= max_windows <= 512 or type(max_pairs) is not int or not 1 <= max_pairs <= 10000:
        raise EditWindowError("Window page/work budget exceeds supported limits")
    query = _identity("window-query", [source.fingerprint, VERSION, BOUNDARY_POLICY, minimum, maximum])
    n = len(source.rows)
    if cursor is None:
        first, last = 0, 0
    elif (not isinstance(cursor, WindowCursor) or cursor.query_fingerprint != query or
          type(cursor.first) is not int or type(cursor.last) is not int or not 0 <= cursor.first <= cursor.last < n):
        raise EditWindowError("Stale or invalid window cursor")
    else:
        first, last = cursor.first, cursor.last
    started, windows, inspected = (first, last), [], 0
    if cancel_check:
        cancel_check()
    while first < n and inspected < max_pairs and len(windows) < max_windows:
        if cancel_check:
            cancel_check()
        inspected += 1
        duration = source.rows[last].end - source.rows[first].start
        if minimum <= duration <= maximum:
            windows.append(_window(source, first, last))
        if duration > maximum or last + 1 == n:
            first += 1
            last = first
        else:
            last += 1
    next_cursor = WindowCursor(query, first, last) if first < n else None
    return WindowPage(tuple(windows), inspected, started, next_cursor, next_cursor is None)


@dataclass(frozen=True)
class SelectedClip:
    id: str
    window_id: str
    row_ids: tuple[str, ...]
    start: float
    end: float
    source_start: float
    source_end: float


@dataclass(frozen=True)
class SelectedSpanPlan:
    id: str
    source_fingerprint: str
    descriptor: SourceDescriptor
    clips: tuple[SelectedClip, ...]
    duration: float
    request_json: str | None
    numeric_bounds_json: str | None
    validation_scope: str = "source_geometry_and_numeric_constraints_only"
    editorial_status: str = "not_assessed"

    def clip_map(self) -> list[dict[str, Any]]:
        """Detached geometry, NOT a project/draft or permission to apply one."""
        return [dict(asdict(clip), asset_id=self.descriptor.asset_id,
                     asset_version=self.descriptor.asset_version) for clip in self.clips]

    def source_at(self, timeline_seconds: float) -> float | None:
        time = _number(timeline_seconds, "timeline time")
        clip = next((c for c in self.clips if c.start <= time < c.end), None)
        return clip.source_start + (time - clip.start) if clip else None

    def timeline_at(self, source_seconds: float) -> float | None:
        time = _number(source_seconds, "source time")
        clip = next((c for c in self.clips if c.source_start <= time < c.source_end), None)
        return clip.start + (time - clip.source_start) if clip else None


def compile_selected_spans(
    source: CanonicalSource, windows: Sequence[EditWindow], *, brief: dict[str, Any] | None = None,
) -> SelectedSpanPlan:
    """Pure speed-1 clip map. M1 supports chronological nonrepeating plans only.

    A one-output request can contain cuts. Explicit no-cuts requires touching
    intervals or a single window (which retains its untranscribed gaps). Even
    explicitly requested repetition/reordering is outside this milestone, never
    silently fulfilled. Numeric checks do NOT verify arbitrary user instructions.
    """
    if not isinstance(windows, Sequence) or not 0 < len(windows) <= MAX_SELECTED_WINDOWS:
        raise EditWindowError("Selection requires 1..200 windows")
    windows = tuple(windows)
    owned_ids: set[str] = set()
    for window in windows:
        validate_window(source, window)
        if owned_ids.intersection(window.row_ids):
            raise EditWindowError("Selection repeats, overlaps or reorders source material; unsupported in M1")
        owned_ids.update(window.row_ids)
    for left, right in zip(windows, windows[1:]):
        if right.source_start < left.source_end:
            raise EditWindowError("Selection repeats, overlaps or reorders source material; unsupported in M1")
    duration = sum(w.source_end - w.source_start for w in windows)
    request, bounds = None, None
    if brief is not None:
        request = _json(brief)  # Snapshot before interpretation; no mutable request in the plan.
        detached = json.loads(request)
        contract = assert_instruction_contract(detached)
        if contract["selection_controls"].get("source_continuity") == "required":
            if any(left.source_end != right.source_start for left, right in zip(windows, windows[1:])):
                raise EditWindowError("Explicit no-cuts instruction conflicts with omitted source intervals")
        bounds = effective_duration_bounds(detached, source.descriptor.asset_duration)
        if duration < bounds["minimum_seconds"] - 1e-7 or duration > bounds["maximum_seconds"] + 1e-7:
            raise EditWindowError("Selected raw source duration violates the numeric request")
    plan_id = _identity("span-plan", [VERSION, source.fingerprint, [w.id for w in windows], request])
    clips, clock = [], 0.
    for window in windows:
        end = clock + (window.source_end - window.source_start)
        clips.append(SelectedClip(_identity("clip", [plan_id, window.id]), window.id, window.row_ids,
                                  clock, end, window.source_start, window.source_end))
        clock = end
    return SelectedSpanPlan(plan_id, source.fingerprint, source.descriptor, tuple(clips), duration,
                            request, _json(bounds) if bounds is not None else None)


def validate_plan(source: CanonicalSource, plan: SelectedSpanPlan) -> None:
    """Recheck a detached result against the CURRENT authoritative snapshot.

    Required at any future consumer boundary. A stored source fingerprint is
    provenance, not permission to apply geometry after the source has changed.
    """
    if not isinstance(plan, SelectedSpanPlan) or plan.source_fingerprint != source.fingerprint or plan.descriptor != source.descriptor:
        raise EditWindowError("Stale selected plan")
    _number(plan.duration, "plan duration")
    if not isinstance(plan.clips, tuple) or not 0 < len(plan.clips) <= MAX_SELECTED_WINDOWS:
        raise EditWindowError("Invalid selected clip inventory")
    windows = []
    for clip in plan.clips:
        if not isinstance(clip, SelectedClip) or not clip.row_ids:
            raise EditWindowError("Empty selected clip")
        for name in ("start", "end", "source_start", "source_end"):
            _number(getattr(clip, name), name)
        windows.append(build_edit_window(source, clip.row_ids[0], clip.row_ids[-1]))
    expected = compile_selected_spans(source, windows, brief=json.loads(plan.request_json) if plan.request_json is not None else None)
    if expected != plan:
        raise EditWindowError("Plan does not match canonical source geometry/request")
