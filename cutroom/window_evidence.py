"""Disabled-by-default planner preview bridging views to existing evidence IDs.

The existing beat partition remains the sole owner of canonical ASR rows.
Windows reference its quotations; they never become competing beat owners.
This boundary returns geometry/evidence only, not an editorial decision or draft.
No cache reuse, model, project persistence, media access or application occurs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import re
from typing import Any, Callable

from .edit_windows import (
    CanonicalSource, EditWindow, EditWindowError, SourceDescriptor,
    build_canonical_source, compile_selected_spans, validate_window, window_rows,
    _identity, _json,
)
from .instruction_contract import assert_instruction_contract
from .story_evidence import EVIDENCE_POLICY_VERSION, build_story_evidence_catalog

WINDOW_EVIDENCE_POLICY = "canonical-window-evidence-preview-v1"
MAX_ALTERNATIVE_WINDOWS = 512


@dataclass(frozen=True)
class WindowSourceState:
    """Current project revision and source versions, supplied by a trusted reader.

    A future Director consumer must derive this from its authoritative store,
    rechecking before application. A saved result never grants apply authority.
    """
    project_id: str
    revision: int
    descriptor: SourceDescriptor

    def __post_init__(self) -> None:
        if (not isinstance(self.project_id, str) or not re.fullmatch(r"project_[0-9a-f]{12}", self.project_id)
                or type(self.revision) is not int or self.revision < 1
                or not isinstance(self.descriptor, SourceDescriptor)):
            raise EditWindowError("Current canonical project/source identity is required")


@dataclass(frozen=True)
class WindowEvidenceRequest:
    source: CanonicalSource
    state: WindowSourceState
    windows: tuple[EditWindow, ...]
    selected_window_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (not isinstance(self.source, CanonicalSource) or not isinstance(self.state, WindowSourceState)
                or self.state.descriptor != self.source.descriptor):
            raise EditWindowError("Window request must bind the canonical source and project version")
        if not isinstance(self.windows, (list, tuple)) or not 0 < len(self.windows) <= MAX_ALTERNATIVE_WINDOWS:
            raise EditWindowError("Window request needs 1..512 bounded alternatives")
        if not isinstance(self.selected_window_ids, (list, tuple)) or len(self.selected_window_ids) > 200:
            raise EditWindowError("Selected window IDs must be a bounded sequence")
        windows, selected = tuple(self.windows), tuple(self.selected_window_ids)
        if not all(isinstance(w, EditWindow) for w in windows):
            raise EditWindowError("Only immutable edit windows are supported")
        ids = [w.id for w in windows]
        if len(ids) != len(set(ids)) or not all(isinstance(i, str) for i in selected) or len(selected) != len(set(selected)):
            raise EditWindowError("Alternative and selected window IDs must be unique")
        if not set(selected) <= set(ids):
            raise EditWindowError("Selection references an unknown alternative window")
        object.__setattr__(self, "windows", windows)
        object.__setattr__(self, "selected_window_ids", selected)


def _checkpoint(request: WindowEvidenceRequest, read_current: Callable[[], WindowSourceState] | None,
                cancel_check: Callable[[], None] | None) -> None:
    check_source_state(request.state, read_current, cancel_check)


def check_source_state(expected: WindowSourceState, read_current: Callable[[], WindowSourceState] | None,
                       cancel_check: Callable[[], None] | None) -> None:
    if cancel_check:
        cancel_check()
    if not callable(read_current):
        raise EditWindowError("Experimental planner requires a current project/source reader")
    current = read_current()
    if cancel_check:
        cancel_check()
    if not isinstance(current, WindowSourceState) or current != expected:
        raise EditWindowError("Project/source changed during window planning")


def validate_bound_source(segments: list[dict[str, Any]], source: CanonicalSource, state: WindowSourceState,
                          read_current: Callable[[], WindowSourceState] | None,
                          cancel_check: Callable[[], None] | None) -> None:
    check_source_state(state, read_current, cancel_check)
    if source.descriptor != state.descriptor or build_canonical_source(segments, source.descriptor).fingerprint != source.fingerprint:
        raise EditWindowError("Planner input differs from full canonical transcript")


def validate_request_source(segments: list[dict[str, Any]], request: WindowEvidenceRequest,
                            read_current: Callable[[], WindowSourceState] | None,
                            cancel_check: Callable[[], None] | None = None) -> None:
    if not isinstance(request, WindowEvidenceRequest):
        raise EditWindowError("Planner opt-in requires an immutable window request")
    # Full input, including unselected rows and word metadata, must match. Never
    # refill the source with a selected-only transcript or normalized paraphrase.
    validate_bound_source(segments, request.source, request.state, read_current, cancel_check)
    for window in request.windows:
        if cancel_check:
            cancel_check()
        validate_window(request.source, window)


@dataclass(frozen=True)
class CanonicalEvidenceIndex:
    source_fingerprint: str
    fingerprint: str
    catalog_json: str
    ownership: tuple[tuple[str, str], ...]

    def catalog(self) -> list[dict[str, Any]]:
        """Exact existing catalog shape/IDs in ASR seconds, detached on export."""
        return json.loads(self.catalog_json)


def build_canonical_evidence_index(source: CanonicalSource, beats: list[dict[str, Any]]) -> CanonicalEvidenceIndex:
    catalog = build_story_evidence_catalog(beats, source.transcript())
    # Keep the old catalog's ambiguity checks, adding complete ownership at this
    # full-source boundary. An alternative view is never an owner in this table.
    owners = {row_id: beat["id"] for beat in beats for row_id in beat["segment_ids"]}
    if set(owners) != {row.id for row in source.rows}:
        raise EditWindowError("Canonical evidence needs complete source ownership")
    ownership = tuple((row.id, owners[row.id]) for row in source.rows)
    fingerprint = _identity("canonical-evidence", [WINDOW_EVIDENCE_POLICY, EVIDENCE_POLICY_VERSION,
                                                 source.fingerprint, ownership, catalog])
    return CanonicalEvidenceIndex(source.fingerprint, fingerprint, _json(catalog), ownership)


def project_evidence(index: CanonicalEvidenceIndex, reference_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    """Resolve only the requested IDs. Empty selected scope NEVER means full."""
    if len(reference_ids) != len(set(reference_ids)):
        raise EditWindowError("Duplicate evidence references")
    by_id = {row["id"]: row for row in index.catalog()}
    if any(reference not in by_id for reference in reference_ids):
        raise EditWindowError("Unknown canonical evidence reference")
    return [by_id[reference] for reference in reference_ids]


def prepare_window_planner_preview(
    segments: list[dict[str, Any]], beats: list[dict[str, Any]], brief: dict[str, Any],
    original_brief: dict[str, Any], request: WindowEvidenceRequest,
    read_current: Callable[[], WindowSourceState] | None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    validate_request_source(segments, request, read_current, cancel_check)
    source = request.source
    index = build_canonical_evidence_index(source, beats)
    catalog = index.catalog()
    by_segment: dict[str, list[str]] = {row.id: [] for row in source.rows}
    for fragment in catalog:
        by_segment[fragment["segment_id"]].append(fragment["id"])
    views = []
    for window in request.windows:
        if cancel_check:
            cancel_check()
        views.append({
            "window_id": window.id, "row_ids": list(window.row_ids),
            "evidence_ids": [reference for row_id in window.row_ids for reference in by_segment[row_id]],
            "context_before_evidence_ids": list(by_segment.get(window.context_before, [])),
            "context_after_evidence_ids": list(by_segment.get(window.context_after, [])),
            "context_role": window.context_role, "boundary_policy": window.boundary_policy,
            "source_start": window.source_start, "source_end": window.source_end,
            "asr_start": window.asr_start, "asr_end": window.asr_end,
            "gaps": [asdict(gap) for gap in window.gaps],
            "exact_text_by_row": [{"segment_id": row.id, "text": row.text} for row in window_rows(source, window)],
        })
    plan, selected_ids, selection = None, (), None
    if request.selected_window_ids:
        by_id = {window.id: window for window in request.windows}
        selected = [by_id[identifier] for identifier in request.selected_window_ids]
        plan = compile_selected_spans(source, selected, brief=brief)
        selected_rows = tuple(row_id for window in selected for row_id in window.row_ids)
        selected_set = set(selected_rows)
        selected_ids = tuple(reference for row_id in selected_rows for reference in by_segment[row_id])
        selection = {"plan_id": plan.id, "window_ids": list(request.selected_window_ids),
                     "row_ids": list(selected_rows), "clip_map": plan.clip_map(), "duration": plan.duration,
                     "exact_text_by_row": [{"segment_id": row.id, "text": row.text}
                                           for row in source.rows if row.id in selected_set],
                     "numeric_bounds": json.loads(plan.numeric_bounds_json)}
    identity = {"policy": WINDOW_EVIDENCE_POLICY, "evidence_policy": EVIDENCE_POLICY_VERSION,
                "canonical_source": source.fingerprint, "canonical_evidence": index.fingerprint,
                "project_source_state": asdict(request.state), "views": views,
                "selection": selection, "original_request": original_brief, "effective_request": brief}
    cache_key = _identity("window-planner-preview", identity)
    _checkpoint(request, read_current, cancel_check)
    return {"status": "evidence_mapping_preview_only", "policy": WINDOW_EVIDENCE_POLICY,
            "cache_key": cache_key, "cache_reuse": "not_implemented_no_story_cache_read_or_write",
            "source_fingerprint": source.fingerprint, "source_descriptor": asdict(source.descriptor),
            "project_source_state": asdict(request.state), "canonical_evidence_fingerprint": index.fingerprint,
            "canonical_ownership": [{"segment_id": s, "beat_id": b} for s, b in index.ownership],
            "canonical_evidence": catalog, "views": views,
            "selected_evidence": project_evidence(index, selected_ids), "selection": selection,
            "original_request": json.loads(_json(original_brief)),
            "instruction_contract": assert_instruction_contract(brief),
            "editorial_status": "not_assessed"}
