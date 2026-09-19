from __future__ import annotations

import copy
import hashlib
import http.client
import json
import math
import os
import queue
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import webbrowser
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request, send_file, send_from_directory
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from cutroom import __version__
from cutroom.config import ROOT, Settings, load_settings
from cutroom.ai_runtime import AIRuntime, ollama_environment, resolve_ollama_executable
from cutroom.director import analyze_project, refine_project
from cutroom.edit_styles import UnknownEditStyle, get_edit_style, public_edit_styles
from cutroom.editing import ManualEditError, apply_manual_edit, strip_private_edit_history
from cutroom.sequence import SEQUENCE_ACTION_FIELDS, editor_sequence_snapshot
from cutroom.source_tracks import SourceTrackError
from cutroom.intelligence import story_ai_status
from cutroom.cloud_ai import ConnectionStore, CloudAIError, enabled as cloud_enabled, require_connection
from cutroom.manual_start import start_manual_draft
from cutroom.local_models import (
    OLLAMA_INSTALL_URL, catalog as local_model_catalog,
    install_transcription, supported_install,
)
from cutroom.audio import analyze_audio
from cutroom.captions import (
    CAPTION_POSITION_CHOICES,
    CAPTION_SCALE_RANGE,
    CAPTION_STYLE_CHOICES,
    CAPTION_WORDS_PER_LINE_RANGE,
)
from cutroom.jobs import JobAdmissionError, JobCancelled, JobContext, JobManager
from cutroom.frame_rates import validate_export_fps
from cutroom.media import VIDEO_EXTENSIONS, UploadTooLargeError, copy_upload, create_proxy, extract_thumbnails, probe_media
from cutroom.projects import ProjectStateError, ProjectStore
from cutroom.render import InsufficientStorageError, available_encoders, ensure_render_storage, render_project
from cutroom.utils import sanitize_filename
from cutroom.vision import VISION_ANALYSIS_VERSION, analyze_faces_and_embedded_camera, normalized_vision_sample_count


JSON_BODY_LIMIT = 1024 * 1024
UPLOAD_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{16,128}")
UPLOAD_TRANSACTION_TTL_SECONDS = 10 * 60
MAX_UPLOAD_TRANSACTIONS = 512
SOURCE_TRACK_EDIT_FIELDS = {
    "track_split": {"slot", "time"},
    "track_remove_range": {"slot", "start", "end"},
    "track_restore_range": {"slot", "start", "end"},
    "track_move": {"slot", "clip_id", "start"},
    "track_trim": {"slot", "clip_id", "start", "end", "source_start"},
    "track_reset": {"slot"},
}
JSON_BODY_ENDPOINTS = {
    "create_project",
    "patch_project",
    "manual_edit",
    "run_director",
    "refine",
    "render",
    "cancel_job",
    "install_model",
    "prepare_ai_runtime",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
FOREGROUND_JOB_KINDS = {"director", "refine", "render"}
INSTANCE_PROTOCOL_VERSION = 1
INSTANCE_RESPONSE_LIMIT = 4 * 1024
LEGACY_SYSTEM_RESPONSE_LIMIT = 256 * 1024
SETTINGS_FIELDS = {
    "workflow",
    "edit_style",
    "goal",
    "aspect",
    "pace",
    "target_duration",
    "layout",
    "audio_source",
    "quality",
    "resolution",
    "fps",
    "auto_reframe",
    "editorial_effects",
    "captions",
    "burn_captions",
    "caption_style",
    "caption_position",
    "caption_scale",
    "caption_words_per_line",
    "spoken_language",
    "performance_mode",
    "audio_cleanup",
    "instruction",
}
AUDIO_CLEANUP_FIELDS = {
    "preset",
    "silence_action",
    "silence_min_seconds",
    "silence_threshold_dbfs",
    "silence_keep_seconds",
    "max_remove_ratio",
    "quiet_action",
    "quiet_gain_db",
    "loud_action",
    "loud_gain_db",
    "normalize",
    "target_lufs",
}


class ServerStartupError(RuntimeError):
    """A local server startup failure that should be shown without a traceback."""
SETTING_CHOICES = {
    "workflow": {"ai", "manual"},
    "goal": {"short", "youtube", "podcast", "clean"},
    "aspect": {"9:16", "16:9", "1:1", "4:5", "source"},
    "pace": {"gentle", "balanced", "dynamic"},
    "layout": {"auto", "A", "B", "screen", "camera", "stacked", "side_by_side", "pip", "embedded_stack"},
    "audio_source": {"A", "B"},
    "quality": {"fast", "balanced", "quality"},
    "resolution": {"720", "1080"},
    "performance_mode": {"auto", "lite", "balanced", "quality"},
    "caption_style": CAPTION_STYLE_CHOICES,
    "caption_position": CAPTION_POSITION_CHOICES,
}
AUDIO_CLEANUP_CHOICES = {
    "preset": {"natural", "clean", "tight"},
    "silence_action": {"keep", "shorten", "remove"},
    "quiet_action": {"keep", "boost"},
    "loud_action": {"keep", "lower"},
}
AUDIO_CLEANUP_RANGES = {
    "silence_min_seconds": (0.25, 8.0),
    "silence_threshold_dbfs": (-72.0, -18.0),
    "silence_keep_seconds": (0.08, 2.0),
    "max_remove_ratio": (0.02, 0.70),
    "quiet_gain_db": (0.0, 10.0),
    "loud_gain_db": (-10.0, 0.0),
    "target_lufs": (-24.0, -10.0),
}


class APIInputError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _host_name(value: str) -> str | None:
    try:
        return urllib.parse.urlsplit(f"//{value}").hostname
    except ValueError:
        return None


def _is_loopback_host(value: str | None) -> bool:
    if not value:
        return False
    clean = value.lower().rstrip(".")
    if clean == "localhost":
        return True
    try:
        import ipaddress

        return ipaddress.ip_address(clean).is_loopback
    except ValueError:
        return False


def _origin_matches_request(origin: str) -> bool:
    try:
        source = urllib.parse.urlsplit(origin)
        target = urllib.parse.urlsplit(f"{request.scheme}://{request.host}")
        source_port = source.port or (443 if source.scheme == "https" else 80)
        target_port = target.port or (443 if target.scheme == "https" else 80)
    except ValueError:
        return False
    if source.scheme not in {"http", "https"} or source.hostname is None or target.hostname is None:
        return False
    return (
        source.scheme == target.scheme
        and source.hostname.lower().rstrip(".") == target.hostname.lower().rstrip(".")
        and source_port == target_port
    )


def _validate_json_sanity(value: Any, *, depth: int = 0) -> None:
    if depth > 8:
        raise APIInputError("invalid_json", "JSON nesting is too deep.")
    if isinstance(value, dict):
        if len(value) > 128:
            raise APIInputError("invalid_json", "JSON object contains too many fields.")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 80:
                raise APIInputError("invalid_json", "JSON field names must be short strings.")
            _validate_json_sanity(item, depth=depth + 1)
        return
    if isinstance(value, list):
        if len(value) > 1000:
            raise APIInputError("invalid_json", "JSON array contains too many items.")
        for item in value:
            _validate_json_sanity(item, depth=depth + 1)
        return
    if isinstance(value, str):
        if len(value) > 20_000:
            raise APIInputError("invalid_json", "JSON string is too long.")
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        try:
            valid_number = math.isfinite(float(value)) and abs(value) <= 1_000_000_000_000
        except (OverflowError, ValueError):
            valid_number = False
        if not valid_number:
            raise APIInputError("invalid_json", "JSON contains an invalid number.")
        return
    raise APIInputError("invalid_json", "JSON contains an unsupported value.")


def _json_object() -> dict[str, Any]:
    if request.content_length == 0:
        return {}
    if request.content_length is None and not request.is_json:
        return {}
    if not request.is_json:
        raise APIInputError("json_required", "This endpoint accepts a JSON object.", 415)
    try:
        payload = request.get_json(silent=False)
    except BadRequest as exc:
        raise APIInputError("invalid_json", "Request body is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise APIInputError("invalid_json_type", "JSON request body must be an object.")
    _validate_json_sanity(payload)
    return payload


def _reject_unknown_fields(payload: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise APIInputError("unknown_field", f"Unsupported JSON field: {unknown[0]}")


def _require_optional_string(payload: dict[str, Any], key: str, *, max_length: int) -> None:
    if key in payload and (not isinstance(payload[key], str) or len(payload[key]) > max_length):
        raise APIInputError("invalid_field", f"{key} must be a string of at most {max_length} characters.")


def _validate_language(value: Any, key: str) -> None:
    if not isinstance(value, str) or not re_safe_language(value):
        raise APIInputError("invalid_field", f"{key} must be auto or a short language code such as en or he.")


def _validate_finite_number(
    value: Any,
    key: str,
    *,
    minimum: float,
    maximum: float,
    allow_none: bool = False,
) -> None:
    if allow_none and value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise APIInputError("invalid_field", f"{key} must be a number between {minimum:g} and {maximum:g}.")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise APIInputError("invalid_field", f"{key} must be between {minimum:g} and {maximum:g}.")


def _validate_settings_payload(payload: dict[str, Any]) -> None:
    _reject_unknown_fields(payload, SETTINGS_FIELDS)
    if "fps" in payload:
        try:
            validate_export_fps(payload["fps"])
        except ValueError as exc:
            raise APIInputError("invalid_field", str(exc)) from exc
    string_limits = {
        "workflow": 16,
        "edit_style": 40,
        "goal": 24,
        "pace": 24,
        "instruction": 8000,
        "aspect": 16,
        "layout": 32,
        "resolution": 16,
        "quality": 24,
        "audio_source": 8,
        "spoken_language": 24,
        "performance_mode": 24,
        "caption_style": 16,
        "caption_position": 16,
    }
    for key, limit in string_limits.items():
        _require_optional_string(payload, key, max_length=limit)
    if "edit_style" in payload:
        try:
            get_edit_style(payload["edit_style"], strict=True)
        except UnknownEditStyle as exc:
            raise APIInputError("invalid_edit_style", f"Unknown edit style: {exc}") from exc
    for key, choices in SETTING_CHOICES.items():
        if key in payload and payload[key] not in choices:
            raise APIInputError("invalid_field", f"{key} has an unsupported value.")
    if "spoken_language" in payload:
        _validate_language(payload["spoken_language"], "spoken_language")
    for key in ("auto_reframe", "editorial_effects", "captions", "burn_captions"):
        if key in payload and not isinstance(payload[key], bool):
            raise APIInputError("invalid_field", f"{key} must be a boolean.")
    if "caption_scale" in payload:
        value = payload["caption_scale"]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not CAPTION_SCALE_RANGE[0] <= value <= CAPTION_SCALE_RANGE[1]
        ):
            raise APIInputError(
                "invalid_field",
                "caption_scale must be an integer percentage between "
                f"{CAPTION_SCALE_RANGE[0]} and {CAPTION_SCALE_RANGE[1]}.",
            )
    if "caption_words_per_line" in payload:
        value = payload["caption_words_per_line"]
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not CAPTION_WORDS_PER_LINE_RANGE[0] <= value <= CAPTION_WORDS_PER_LINE_RANGE[1]
        ):
            raise APIInputError(
                "invalid_field",
                "caption_words_per_line must be an integer between "
                f"{CAPTION_WORDS_PER_LINE_RANGE[0]} and {CAPTION_WORDS_PER_LINE_RANGE[1]}.",
            )
    if "target_duration" in payload:
        value = payload["target_duration"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < float(value) <= 86_400:
            raise APIInputError("invalid_field", "target_duration must be between 0 and 86400 seconds.")
    if "audio_cleanup" in payload:
        cleanup = payload["audio_cleanup"]
        if not isinstance(cleanup, dict):
            raise APIInputError("invalid_field", "audio_cleanup must be an object.")
        _reject_unknown_fields(cleanup, AUDIO_CLEANUP_FIELDS)
        for key, choices in AUDIO_CLEANUP_CHOICES.items():
            if key in cleanup and cleanup[key] not in choices:
                raise APIInputError("invalid_field", f"audio_cleanup.{key} has an unsupported value.")
        if "normalize" in cleanup and not isinstance(cleanup["normalize"], bool):
            raise APIInputError("invalid_field", "audio_cleanup.normalize must be a boolean.")
        for key, (minimum, maximum) in AUDIO_CLEANUP_RANGES.items():
            if key in cleanup:
                _validate_finite_number(
                    cleanup[key],
                    f"audio_cleanup.{key}",
                    minimum=minimum,
                    maximum=maximum,
                    allow_none=key == "silence_threshold_dbfs",
                )


def _validate_manual_payload(payload: dict[str, Any]) -> None:
    _reject_unknown_fields(payload, {"cuts", "keep_ranges", "camera_plan", "crop"})
    for key in ("cuts", "keep_ranges", "camera_plan"):
        if key not in payload:
            continue
        rows = payload[key]
        if not isinstance(rows, list) or len(rows) > 500 or any(not isinstance(item, dict) for item in rows):
            raise APIInputError("invalid_field", f"{key} must be an array of at most 500 objects.")
        for item in rows:
            if set(item) - ({"start", "end", "reason", "camera", "layout"} if key == "camera_plan" else {"start", "end", "reason"}):
                raise APIInputError("invalid_field", f"{key} contains an unsupported field.")
            if "start" not in item or "end" not in item:
                raise APIInputError("invalid_field", f"{key} entries require start and end.")
            _validate_finite_number(item["start"], f"{key}.start", minimum=0.0, maximum=604_800.0)
            _validate_finite_number(item["end"], f"{key}.end", minimum=0.0, maximum=604_800.0)
            if float(item["end"]) <= float(item["start"]):
                raise APIInputError("invalid_field", f"{key} entries must end after they start.")
            if "reason" in item and (not isinstance(item["reason"], str) or len(item["reason"]) > 240):
                raise APIInputError("invalid_field", f"{key}.reason must be a short string.")
            if key == "camera_plan":
                layout = item.get("camera", item.get("layout"))
                if layout not in {"A", "B", "screen", "camera", "stacked", "side_by_side", "pip", "embedded_stack"}:
                    raise APIInputError("invalid_field", "camera_plan entries require a supported camera or layout.")
    if "crop" in payload and not isinstance(payload["crop"], dict):
        raise APIInputError("invalid_field", "crop must be an object.")
    if isinstance(payload.get("crop"), dict):
        crop = payload["crop"]
        if set(crop) - {"A", "B"}:
            raise APIInputError("invalid_field", "crop accepts only source A or B.")
        for slot, values in crop.items():
            if not isinstance(values, dict) or set(values) - {"x", "y", "zoom"}:
                raise APIInputError("invalid_field", f"crop.{slot} must contain only x, y and zoom.")
            for key in ("x", "y"):
                if key in values:
                    _validate_finite_number(values[key], f"crop.{slot}.{key}", minimum=0.0, maximum=1.0)
            if "zoom" in values:
                _validate_finite_number(values["zoom"], f"crop.{slot}.zoom", minimum=1.0, maximum=3.0)


def _safe_project_child(project_root: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    root = project_root.resolve()
    # Project files are portable between Windows/Linux releases. Treat either
    # separator as a path boundary before the containment check.
    candidate = (root / relative.replace("\\", "/")).resolve()
    return candidate if root in candidate.parents else None


def _cleanup_old_source(project_root: Path, slot: str, source: Any, keep: Path | None = None) -> None:
    if not isinstance(source, dict):
        return
    keep = keep.resolve() if keep is not None else None
    for key in ("relative_path", "preview_relative_path"):
        path = _safe_project_child(project_root, source.get(key))
        if path is not None and path != keep:
            path.unlink(missing_ok=True)
    thumbnails = project_root / "cache" / f"thumbnails-{slot}"
    if thumbnails.is_dir():
        shutil.rmtree(thumbnails)


_SCREEN_SOURCE_HINTS = frozenset({
    "capture", "desktop", "display", "game", "gameplay", "monitor", "obs", "screen", "screencast",
})
_CAMERA_SOURCE_HINTS = frozenset({
    "cam", "camera", "face", "facecam", "iphone", "phone", "selfie", "talking", "webcam",
})
_SOURCE_MIXER_LAYOUTS = frozenset({"auto", "screen", "camera", "stacked", "side_by_side", "pip"})


def _source_role_scores(source: dict[str, Any]) -> tuple[float, float]:
    """Return deterministic screen/camera evidence without pretending it is AI certainty."""

    name = Path(str(source.get("name") or "")).stem.casefold()
    tokens = set(re.findall(r"[a-z0-9]+", name))
    # Compound names such as ``face-cam`` and ``screenrecording`` are common.
    compact = "".join(tokens)
    screen_score = float(len(tokens & _SCREEN_SOURCE_HINTS) * 3)
    camera_score = float(len(tokens & _CAMERA_SOURCE_HINTS) * 3)
    if "screen" in compact or "gameplay" in compact or "screencast" in compact:
        screen_score += 3.0
    if "facecam" in compact or "webcam" in compact or "selfie" in compact:
        camera_score += 3.0

    try:
        width = max(0.0, float(source.get("width") or 0))
        height = max(0.0, float(source.get("height") or 0))
    except (TypeError, ValueError):
        width = height = 0.0
    if width > 0 and height > 0:
        ratio = width / height
        if ratio >= 1.45:
            screen_score += 1.5
        elif ratio <= 0.82:
            camera_score += 1.25
    return screen_score, camera_score


def _inferred_source_mixer(project: dict[str, Any]) -> dict[str, Any]:
    """Suggest stable roles from filenames and shape, falling back to upload order."""

    sources = project.get("sources") or {}
    source_a = sources.get("A") if isinstance(sources.get("A"), dict) else None
    source_b = sources.get("B") if isinstance(sources.get("B"), dict) else None
    if not source_a or not source_b:
        return {"screen_slot": "A", "camera_slot": "B", "primary_role": "screen", "audio_slot": "A"}

    a_screen, a_camera = _source_role_scores(source_a)
    b_screen, b_camera = _source_role_scores(source_b)
    a_as_screen = a_screen + b_camera
    b_as_screen = b_screen + a_camera
    if b_as_screen > a_as_screen:
        screen_slot, camera_slot = "B", "A"
    else:
        screen_slot, camera_slot = "A", "B"

    audio_slot = "A"
    if not source_a.get("has_audio") and source_b.get("has_audio"):
        audio_slot = "B"
    return {
        "screen_slot": screen_slot,
        "camera_slot": camera_slot,
        "primary_role": "screen",
        "audio_slot": audio_slot,
        # Physical ordering is deliberately predictable; the Source Mixer can
        # change this independently from semantic screen/camera roles.
        "first_slot": "A",
    }


def _preserved_source_mixer(project: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any] | None:
    """Keep still-valid user routing while invalidating synchronization to replaced media."""

    screen_slot = str(previous.get("screen_slot") or "").upper()
    camera_slot = str(previous.get("camera_slot") or "").upper()
    if {screen_slot, camera_slot} != {"A", "B"}:
        return None
    sources = project.get("sources") or {}
    if not all(isinstance(sources.get(slot), dict) for slot in ("A", "B")):
        return None
    primary_role = str(previous.get("primary_role") or "screen").lower()
    if primary_role not in {"screen", "camera"}:
        primary_role = "screen"
    first_slot = str(previous.get("first_slot") or "A").upper()
    if first_slot not in {"A", "B"}:
        first_slot = "A"
    audio_slot = str(previous.get("audio_slot") or "A").upper()
    if audio_slot not in {"A", "B"} or not (sources.get(audio_slot) or {}).get("has_audio"):
        audio_slot = (
            "A" if (sources.get("A") or {}).get("has_audio")
            else "B" if (sources.get("B") or {}).get("has_audio")
            else "A"
        )
    mixer: dict[str, Any] = {
        "screen_slot": screen_slot,
        "camera_slot": camera_slot,
        "primary_role": primary_role,
        "audio_slot": audio_slot,
        "first_slot": first_slot,
    }
    default_layout = str(previous.get("default_layout") or "").lower()
    if default_layout in _SOURCE_MIXER_LAYOUTS:
        mixer["default_layout"] = default_layout
    if previous.get("stack_fit") in {"cover", "contain"}:
        mixer["stack_fit"] = previous["stack_fit"]
    return mixer


def _reset_manual_after_source_change(
    project: dict[str, Any],
    slot: str,
    *,
    replacing: bool = False,
) -> None:
    """Drop decisions that are no longer anchored to the current footage.

    Source A owns the edit timeline, so replacing it invalidates every manual
    time range. Source B can change without invalidating A's cuts, but its
    framing, crop, synchronization and undo history must not leak to the new
    camera/screen recording.
    """

    previous = project.get("manual") if isinstance(project.get("manual"), dict) else {}
    keep_a_timeline = slot == "B"
    crop = previous.get("crop") if isinstance(previous.get("crop"), dict) else {}
    previous_cuts = previous.get("cuts") if isinstance(previous.get("cuts"), list) else []
    previous_keeps = previous.get("keep_ranges") if isinstance(previous.get("keep_ranges"), list) else []
    restored_ranges = previous.get("keeps") if isinstance(previous.get("keeps"), list) else []
    previous_mixer = previous.get("source_mixer") if isinstance(previous.get("source_mixer"), dict) else {}
    had_embedded_camera = isinstance(previous.get("embedded_camera"), dict)
    preserve_replaced_b = slot == "B" and replacing
    source_mixer = _preserved_source_mixer(project, previous_mixer) if preserve_replaced_b else None
    if source_mixer is None:
        source_mixer = _inferred_source_mixer(project)

    project["manual"] = {
        "cuts": list(previous_cuts) if keep_a_timeline else [],
        "keep_ranges": list(previous_keeps) if keep_a_timeline else [],
        "keeps": list(restored_ranges) if keep_a_timeline else [],
        "camera_plan": [],
        "camera_overrides": [],
        "source_mixer": source_mixer,
        "crop": {"A": dict(crop["A"])} if keep_a_timeline and isinstance(crop.get("A"), dict) else {},
        "history": {"undo_count": 0, "redo_count": 0},
    }
    # B replacement/removal must not discard independent A clip edits. B's
    # local media mapping is obsolete, however, and must never reach its new
    # recording. Preserve explicit [] as an intentional empty A track.
    previous_tracks = previous.get("source_tracks")
    if keep_a_timeline and isinstance(previous_tracks, dict) and "A" in previous_tracks:
        project["manual"]["source_tracks"] = {"A": copy.deepcopy(previous_tracks["A"])}
    previous_sequence = previous.get("sequence")
    if keep_a_timeline and isinstance(previous_sequence, dict) and previous_sequence.get("version") == 1:
        sequence = copy.deepcopy(previous_sequence)
        base_tracks = sequence.get("base_source_tracks")
        if isinstance(base_tracks, dict):
            base_tracks.pop("B", None)
        project["manual"]["sequence"] = sequence
        # The new/removed B has no mapping on a previously rearranged clock.
        # An explicit empty lane prevents accidental reuse or wrong alignment.
        project["manual"].setdefault("source_tracks", {"A": []})["B"] = []
    # A manual embedded facecam belongs to the exact single source A. Replacing
    # A or adding a real source B invalidates that composition, so do not leave
    # an orphaned embedded_stack setting that would hide the new footage.
    if had_embedded_camera and str((project.get("settings") or {}).get("layout") or "") == "embedded_stack":
        project.setdefault("settings", {})["layout"] = "auto"


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    configured_host = str(settings.raw.get("host", "127.0.0.1")).strip()
    if not _is_loopback_host(configured_host):
        raise ValueError(
            "CUTROOM has no remote authentication and must use a loopback host "
            "such as 127.0.0.1, localhost, or ::1. Refusing to bind to a LAN/public address."
        )
    settings.raw["host"] = configured_host
    store = ProjectStore(settings)
    jobs = JobManager(
        int(settings.raw.get("job_workers", 2)),
        int(settings.raw.get("background_workers", 2)),
        persistence_path=settings.cache_dir / "jobs.json",
        max_pending=int(settings.raw.get("max_pending_jobs", 32)),
        retention_seconds=float(settings.raw.get("job_retention_seconds", 24 * 60 * 60)),
    )
    app = Flask(__name__, static_folder=str(ROOT / "web"), static_url_path="/assets")
    max_upload_bytes = int(float(settings.raw.get("max_upload_gb", 40)) * 1024**3)
    # Leave room for multipart headers while enforcing the actual file limit in copy_upload().
    app.config["MAX_CONTENT_LENGTH"] = max_upload_bytes + 32 * 1024**2
    app.extensions["cutroom_settings"] = settings
    app.extensions["cutroom_store"] = store
    app.extensions["cutroom_jobs"] = jobs
    ai_runtime = AIRuntime(settings)
    app.extensions["cutroom_ai_runtime"] = ai_runtime
    connections = ConnectionStore(settings)
    app.extensions["cutroom_connections"] = connections
    configured_loopback = True
    # Source mutations, project deletion and job admission share one small gate.
    # This closes races where two requests both saw an idle project, or where a
    # just-deleted/replaced source received a stale preparation job afterwards.
    project_job_gate = threading.RLock()
    active_uploads: dict[str, int] = {}
    upload_transactions: dict[tuple[str, str, str], dict[str, Any]] = {}

    def discard_upload_rollback(state: dict[str, Any]) -> None:
        expiration = state.pop("expiration", None)
        if isinstance(expiration, threading.Timer):
            expiration.cancel()
        rollback_path = state.pop("rollback_path", None)
        state.pop("previous_source", None)
        if isinstance(rollback_path, Path):
            try:
                rollback_path.unlink(missing_ok=True)
            except OSError as exc:
                app.logger.warning("Could not remove expired upload rollback: %s", exc)

    def prune_upload_transactions(now: float) -> None:
        expired = [
            key
            for key, state in upload_transactions.items()
            if not state.get("active") and now - float(state.get("updated_at", now)) > UPLOAD_TRANSACTION_TTL_SECONDS
        ]
        for key in expired:
            state = upload_transactions.pop(key, None)
            if state is not None:
                discard_upload_rollback(state)
        if len(upload_transactions) < MAX_UPLOAD_TRANSACTIONS:
            return
        inactive = sorted(
            (
                (float(state.get("updated_at", now)), key)
                for key, state in upload_transactions.items()
                if not state.get("active")
            ),
            key=lambda item: item[0],
        )
        for _updated_at, key in inactive:
            if len(upload_transactions) < MAX_UPLOAD_TRANSACTIONS:
                break
            state = upload_transactions.pop(key, None)
            if state is not None:
                discard_upload_rollback(state)

    def upload_cancel_requested(key: tuple[str, str, str], generation: str) -> bool:
        with project_job_gate:
            state = upload_transactions.get(key)
            return bool(
                state
                and state.get("generation") == generation
                and state.get("cancelled")
            )

    def expire_upload_transaction(key: tuple[str, str, str], generation: str) -> None:
        with project_job_gate:
            state = upload_transactions.get(key)
            if (
                not state
                or state.get("active")
                or state.get("generation") != generation
                or time.monotonic() - float(state.get("updated_at", 0)) < UPLOAD_TRANSACTION_TTL_SECONDS
            ):
                return
            upload_transactions.pop(key, None)
            discard_upload_rollback(state)

    def submit_project_job(
        kind: str,
        project_id: str,
        function,
        *args,
        validate_project=None,
        job_identity: Any = None,
        **kwargs,
    ):
        with project_job_gate:
            downloading = jobs.active(kind="model_install", limit=1)
            if downloading and kind in FOREGROUND_JOB_KINDS:
                raise JobAdmissionError(
                    "Finish or cancel the model download before starting AI processing or export. You can continue editing manually.",
                    code="job_conflict", active_job_id=downloading[0].id,
                )
            latest_project = store.load(project_id)
            if validate_project is not None:
                validate_project(latest_project)
            identity = json.dumps(
                {"revision": latest_project.get("revision"), "request": job_identity},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            dedupe_key = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
            for active_job in jobs.active(project_id=project_id):
                if active_job.kind in FOREGROUND_JOB_KINDS and (
                    active_job.kind != kind or active_job.dedupe_key != dedupe_key
                ):
                    raise JobAdmissionError(
                        f"A {active_job.kind} job is already active for this project.",
                        code="job_conflict",
                        active_job_id=active_job.id,
                    )
            return jobs.submit(kind, project_id, function, *args, dedupe_key=dedupe_key, **kwargs)

    @app.before_request
    def protect_local_api():
        if not request.path.startswith("/api/"):
            return None
        if request.endpoint in JSON_BODY_ENDPOINTS or request.endpoint in {"save_ai_connection", "manual_draft"}:
            request.max_content_length = JSON_BODY_LIMIT
            if request.content_length is not None and request.content_length > JSON_BODY_LIMIT:
                raise RequestEntityTooLarge()
        if configured_loopback and not _is_loopback_host(_host_name(request.host)):
            raise APIInputError("invalid_host", "CUTROOM's local API only accepts loopback hosts.", 421)
        if request.method in UNSAFE_METHODS:
            if request.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
                raise APIInputError("cross_site_request", "Cross-site API requests are not allowed.", 403)
            origin = request.headers.get("Origin")
            if origin and not _origin_matches_request(origin):
                raise APIInputError("invalid_origin", "The request origin does not match this CUTROOM instance.", 403)
        return None

    @app.after_request
    def headers(response: Response) -> Response:
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cache-Control"] = "no-store" if request.path.startswith("/api/") else "public, max-age=300"
        return response

    @app.errorhandler(APIInputError)
    def handle_api_input(error: APIInputError):
        return jsonify({"error": error.code, "message": error.message}), error.status

    @app.errorhandler(CloudAIError)
    def handle_cloud_error(error):
        return jsonify({"error": "cloud_ai_unavailable", "message": str(error)}), 409

    @app.errorhandler(JobAdmissionError)
    def handle_job_admission(error: JobAdmissionError):
        status = 409 if error.code == "job_conflict" else 429
        return jsonify({
            "error": error.code,
            "message": str(error),
            "active_job_id": error.active_job_id,
        }), status

    @app.errorhandler(FileNotFoundError)
    def handle_missing_local_resource(error: FileNotFoundError):
        # A browser can legitimately remember a project from another extracted CUTROOM
        # folder. Missing local projects/files are a normal 404, not a server crash.
        return jsonify({
            "error": "not_found",
            "message": "The requested local project or file no longer exists.",
        }), 404

    @app.errorhandler(ProjectStateError)
    def handle_corrupt_project(error: ProjectStateError):
        app.logger.error("Unreadable project state: %s", error)
        return jsonify({
            "error": "corrupt_project",
            "message": "This project's local state is damaged. Restore its project.json backup or create a new project.",
        }), 409

    @app.errorhandler(Exception)
    def handle_error(error: Exception):
        # RequestEntityTooLarge is an HTTPException subclass, so it must be checked first.
        if isinstance(error, RequestEntityTooLarge):
            if request.endpoint in JSON_BODY_ENDPOINTS:
                return jsonify({
                    "error": "request_too_large",
                    "message": "JSON request body is larger than the allowed limit.",
                    "max_json_body_bytes": JSON_BODY_LIMIT,
                }), 413
            return jsonify({
                "error": "file_too_large",
                "message": "The selected video is larger than the configured upload limit.",
                "max_upload_bytes": max_upload_bytes,
            }), 413
        if isinstance(error, HTTPException):
            return jsonify({"error": error.name, "message": error.description}), error.code
        if isinstance(error, RuntimeError) and str(error) == "revision_conflict":
            return jsonify({
                "error": "revision_conflict",
                "message": "The project changed before this update was saved. Reload it and try again.",
            }), 409
        if isinstance(error, RuntimeError) and str(error) in {
            "project_changed_during_analysis",
            "project_changed_during_render",
        }:
            return jsonify({
                "error": str(error),
                "message": "The project changed while CUTROOM was working. Start the operation again with the latest edit.",
            }), 409
        if isinstance(error, RuntimeError) and str(error) == "captions_out_of_date":
            return jsonify({
                "error": "captions_out_of_date",
                "message": "Captions no longer match the selected audio source or sync offset. Rebuild the Draft before exporting captions.",
            }), 409
        app.logger.exception("Unhandled error")
        return jsonify({"error": type(error).__name__, "message": str(error)}), 500

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "web", "index.html")

    @app.get("/favicon.ico")
    def favicon():
        # Browsers may request the legacy path before parsing the SVG link.
        return app.send_static_file("favicon.svg")

    @app.get("/api/health")
    def health():
        ffmpeg_ok = _command_ok([settings.ffmpeg, "-version"])
        ffprobe_ok = _command_ok([settings.ffprobe, "-version"])
        return jsonify({
            "ok": ffmpeg_ok and ffprobe_ok,
            "version": __version__,
            "ffmpeg": ffmpeg_ok,
            "ffprobe": ffprobe_ok,
            "ollama": _ollama_status(settings),
        })

    @app.get("/api/instance")
    def instance_info():
        response = jsonify({
            "service": "cutroom",
            "protocol": INSTANCE_PROTOCOL_VERSION,
            "instance_id": _cutroom_instance_id(settings),
            "version": __version__,
        })
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/system")
    def system_info():
        disk = shutil.disk_usage(settings.data_dir)
        instance_id = _cutroom_instance_id(settings)
        return jsonify({
            "product": "CUTROOM",
            "version": __version__,
            "vision_analysis_version": VISION_ANALYSIS_VERSION,
            "instance_id": instance_id,
            "python": sys.version.split()[0],
            "platform": sys.platform,
            "encoders": sorted(available_encoders(settings)),
            "models": _model_status(connections.job_settings(settings)),
            "runtime": {"state": "cloud", "available": connections.public()["configured"]} if connections.public()["mode"] != "local" else ai_runtime.snapshot(),
            "ai_connection": connections.public(),
            "edit_styles": public_edit_styles(),
            "data_dir": str(settings.data_dir),
            "limits": {
                "max_upload_gb": float(settings.raw.get("max_upload_gb", 40)),
                "max_upload_bytes": max_upload_bytes,
                "max_json_body_bytes": JSON_BODY_LIMIT,
                "transport_request_body_bytes": int(app.config["MAX_CONTENT_LENGTH"]),
                "disk_free_bytes": int(disk.free),
                "disk_total_bytes": int(disk.total),
            },
        })

    @app.get("/api/ai/connection")
    def ai_connection():
        return jsonify({"connection": connections.public()})

    @app.post("/api/ai/connection")
    def save_ai_connection():
        payload = _json_object()
        with project_job_gate:
            if jobs.active():
                raise APIInputError("project_busy", "Wait for active processing to finish before changing AI connection.", 409)
            try:
                selected = connections.update(payload)
            except ValueError as error:
                raise APIInputError("invalid_connection", str(error)) from error
        return jsonify({"connection": selected})

    @app.post("/api/runtime/prepare")
    def prepare_ai_runtime():
        payload = _json_object()
        _reject_unknown_fields(payload, {"performance_mode"})
        _validate_settings_payload(payload)
        selected_settings = connections.job_settings(settings)
        if cloud_enabled(selected_settings):
            require_connection(selected_settings)
            return jsonify({"runtime": {"state": "cloud", "available": True}, "story_ai": story_ai_status(selected_settings, payload)})
        # This explicit action only starts/checks the engine. Downloading a model
        # remains a separate, user-approved action through /api/models/install.
        runtime = ai_runtime.ensure_ready(timeout=30, retry=True)
        story = story_ai_status(settings, payload)
        return jsonify({"runtime": runtime, "story_ai": story})

    @app.get("/api/projects")
    def list_projects():
        return jsonify({"projects": store.list()})

    @app.post("/api/projects")
    def create_project():
        payload = _json_object()
        _reject_unknown_fields(payload, {"name", "initial_settings"})
        _require_optional_string(payload, "name", max_length=120)
        initial = payload.get("initial_settings", {})
        if not isinstance(initial, dict):
            raise APIInputError("invalid_field", "Initial settings must be an object.")
        _validate_settings_payload(initial)
        return jsonify({"project": store.create(payload.get("name") or "Untitled project", initial_settings=initial)}), 201

    @app.get("/api/projects/<project_id>")
    def get_project(project_id: str):
        return jsonify({"project": _public_project(store.load(project_id))})

    @app.patch("/api/projects/<project_id>")
    def patch_project(project_id: str):
        payload = _json_object()
        _reject_unknown_fields(payload, {"name", "language", "settings", "manual", "expected_revision"})
        _require_optional_string(payload, "name", max_length=120)
        _require_optional_string(payload, "language", max_length=24)
        if "language" in payload:
            _validate_language(payload["language"], "language")
        if "settings" in payload:
            if not isinstance(payload["settings"], dict):
                raise APIInputError("invalid_field", "settings must be an object.")
            _validate_settings_payload(payload["settings"])
        if "manual" in payload and not isinstance(payload["manual"], dict):
            raise APIInputError("invalid_field", "manual must be an object.")
        if "manual" in payload:
            _validate_manual_payload(payload["manual"])
        expected_revision = payload.pop("expected_revision", None)
        if expected_revision is not None and (isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision < 1):
            raise APIInputError("invalid_field", "expected_revision must be a positive integer.")
        return jsonify({"project": _public_project(store.patch(project_id, payload, expected_revision=expected_revision))})

    @app.post("/api/projects/<project_id>/manual/edit")
    def manual_edit(project_id: str):
        payload = _json_object()
        action = str(payload.get("action") or "").strip().lower()
        track_fields = SEQUENCE_ACTION_FIELDS.get(action, SOURCE_TRACK_EDIT_FIELDS.get(action))
        _reject_unknown_fields(
            payload,
            {"action", "expected_revision", *track_fields} if track_fields is not None else {
                "action", "start", "end", "new_start", "new_end", "time", "segment_id", "text", "layout",
                "screen_slot", "camera_slot", "primary_role", "audio_slot", "first_slot", "sync_offset", "default_layout", "stack_fit",
                "enabled", "x", "y", "w", "h", "content_x", "content_y",
                "candidate_id",
                "expected_revision",
            },
        )
        if track_fields is not None:
            optional = {"mode", "slot"} if action in {"sequence_move_range", "sequence_close_gaps", "sequence_trim_edge"} else {"mode"}
            missing = sorted(track_fields - optional - payload.keys())
            if missing:
                raise APIInputError("invalid_field", f"Required source track field: {missing[0]}")
            _require_optional_string(payload, "slot", max_length=1)
            _require_optional_string(payload, "clip_id", max_length=128)
            _require_optional_string(payload, "mode", max_length=16)
        expected_revision = payload.pop("expected_revision", None)
        if action in SEQUENCE_ACTION_FIELDS and expected_revision is None:
            raise APIInputError("invalid_field", "Sequence edits require the displayed project's expected_revision.")
        if expected_revision is not None and (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision < 1
        ):
            raise APIInputError("invalid_field", "expected_revision must be a positive integer.")
        try:
            project = store.update(
                project_id,
                lambda current: apply_manual_edit(current, payload),
                expected_revision=expected_revision,
            )
        except ManualEditError as error:
            raise APIInputError("invalid_manual_edit", str(error)) from error
        return jsonify({"project": _public_project(project)})

    @app.delete("/api/projects/<project_id>")
    def delete_project(project_id: str):
        with project_job_gate:
            store.load(project_id)
            if active_uploads.get(project_id, 0):
                raise APIInputError(
                    "project_busy",
                    "A source upload is still in progress. Cancel it or wait before deleting the project.",
                    409,
                )
            jobs.cancel_project(project_id)
            active = jobs.active(project_id=project_id)
            if active:
                raise APIInputError(
                    "project_busy",
                    "Project jobs are being cancelled. Try deleting again in a moment.",
                    409,
                )
            for transaction_key in [key for key in upload_transactions if key[0] == project_id]:
                transaction = upload_transactions.pop(transaction_key)
                discard_upload_rollback(transaction)
            try:
                store.delete(project_id)
            except OSError as exc:
                raise APIInputError(
                    "project_files_busy",
                    "Windows is still closing a project media file. Try deleting the project again in a moment.",
                    409,
                ) from exc
        return jsonify({"ok": True})

    @app.post("/api/projects/<project_id>/sources/<slot>")
    def upload_source(project_id: str, slot: str):
        slot = slot.upper()
        if slot not in {"A", "B"}:
            return jsonify({"error": "invalid_slot", "message": "Slot must be A or B."}), 400
        # Reject obviously oversized multipart requests before Flask parses the file body.
        content_length = int(request.content_length or 0)
        if content_length > max_upload_bytes + 16 * 1024**2:
            return jsonify({
                "error": "file_too_large",
                "message": "The selected video is larger than the configured upload limit.",
                "max_upload_bytes": max_upload_bytes,
            }), 413
        disk = shutil.disk_usage(settings.data_dir)
        # Keep 1 GiB free so a successful upload does not completely fill the drive.
        if content_length and disk.free < content_length + 1024**3:
            return jsonify({
                "error": "insufficient_storage",
                "message": "There is not enough free disk space to import this video.",
                "disk_free_bytes": int(disk.free),
            }), 507
        supplied_token = str(request.headers.get("X-Cutroom-Upload-Token") or "").strip()
        if supplied_token and not UPLOAD_TOKEN_PATTERN.fullmatch(supplied_token):
            raise APIInputError(
                "invalid_upload_token",
                "X-Cutroom-Upload-Token must contain 16-128 letters, numbers, underscores, or hyphens.",
            )
        upload_token = supplied_token or uuid.uuid4().hex
        transaction_id = uuid.uuid4().hex
        transaction_key = (project_id, slot, upload_token)
        project_root = store.project_dir(project_id)
        media_dir = project_root / "media"
        staging: Path | None = None
        destination: Path | None = None
        backup: Path | None = None
        rollback_path: Path | None = None
        previous_media_path: Path | None = None
        installed_destination = False
        previous_source: dict[str, Any] | None = None
        with project_job_gate:
            store.load(project_id)
            now = time.monotonic()
            prune_upload_transactions(now)
            existing_transaction = upload_transactions.get(transaction_key)
            if existing_transaction is not None:
                if existing_transaction.get("cancelled"):
                    return jsonify({
                        "error": "upload_cancelled",
                        "message": "The upload was cancelled before it started.",
                        "upload_token": upload_token,
                    }), 409
                raise APIInputError(
                    "upload_token_reused",
                    "This upload token is already in use. Start the upload again with a new token.",
                    409,
                )
            if len(upload_transactions) >= MAX_UPLOAD_TRANSACTIONS:
                raise APIInputError(
                    "too_many_uploads",
                    "Too many upload transactions are active. Wait for an import to finish and try again.",
                    429,
                )
            upload_transactions[transaction_key] = {
                "generation": transaction_id,
                "cancelled": False,
                "active": True,
                "updated_at": now,
            }
            active_uploads[project_id] = active_uploads.get(project_id, 0) + 1
        try:
            uploaded = request.files.get("file")
            if not uploaded or not uploaded.filename:
                return jsonify({"error": "missing_file", "message": "Choose a video file."}), 400
            filename = sanitize_filename(uploaded.filename)
            extension = Path(filename).suffix.lower()
            if extension not in VIDEO_EXTENSIONS:
                return jsonify({"error": "unsupported_format", "message": f"Unsupported video format: {extension or 'unknown'}"}), 415
            destination = media_dir / f"source-{slot}{extension}"
            staging = media_dir / f".upload-{slot}-{transaction_id}{extension}"
            backup = media_dir / f".{destination.name}.{transaction_id}.backup"
            if upload_cancel_requested(transaction_key, transaction_id):
                return jsonify({
                    "error": "upload_cancelled",
                    "message": "The upload was cancelled.",
                    "upload_token": upload_token,
                }), 409
            try:
                copy_upload(uploaded, staging, max_upload_bytes)
            except UploadTooLargeError:
                return jsonify({
                    "error": "file_too_large",
                    "message": "The selected video is larger than the configured upload limit.",
                    "max_upload_bytes": max_upload_bytes,
                }), 413
            if upload_cancel_requested(transaction_key, transaction_id):
                return jsonify({
                    "error": "upload_cancelled",
                    "message": "The upload was cancelled.",
                    "upload_token": upload_token,
                }), 409
            try:
                metadata = probe_media(staging, settings)
            except (ValueError, subprocess.SubprocessError):
                return jsonify({
                    "error": "invalid_media",
                    "message": "The selected file could not be read as a valid video.",
                }), 422
            if upload_cancel_requested(transaction_key, transaction_id):
                return jsonify({
                    "error": "upload_cancelled",
                    "message": "The upload was cancelled.",
                    "upload_token": upload_token,
                }), 409

            source_record = {
                "slot": slot,
                "name": filename,
                "generation": transaction_id,
                "relative_path": destination.relative_to(project_root).as_posix(),
                **metadata,
                "preview_relative_path": None,
                "preparation": "queued",
            }

            def commit_upload(project: dict[str, Any]) -> None:
                nonlocal installed_destination, previous_source, previous_media_path, rollback_path
                current = project.setdefault("sources", {}).get(slot)
                previous_source = json.loads(json.dumps(current)) if isinstance(current, dict) else None
                if previous_source is not None:
                    previous_media_path = _safe_project_child(project_root, previous_source.get("relative_path"))
                    if previous_media_path is not None and previous_media_path.is_file():
                        rollback_path = media_dir / f".rollback-{slot}-{transaction_id}{previous_media_path.suffix.lower()}"
                        previous_media_path.replace(rollback_path)
                if destination.exists():
                    destination.replace(backup)
                staging.replace(destination)
                installed_destination = True
                project["sources"][slot] = source_record
                project.setdefault("pre_analysis", {}).setdefault("audio", {}).pop(slot, None)
                project.setdefault("pre_analysis", {}).setdefault("vision", {}).pop(slot, None)
                project["analysis"] = None
                project["draft"] = None
                _reset_manual_after_source_change(project, slot, replacing=previous_source is not None)

            with project_job_gate:
                transaction = upload_transactions.get(transaction_key)
                if not transaction or transaction.get("generation") != transaction_id or transaction.get("cancelled"):
                    return jsonify({
                        "error": "upload_cancelled",
                        "message": "The upload was cancelled.",
                        "upload_token": upload_token,
                    }), 409
                try:
                    project = store.update(project_id, commit_upload)
                except Exception:
                    if installed_destination:
                        destination.unlink(missing_ok=True)
                    if backup.exists():
                        backup.replace(destination)
                    if rollback_path is not None and rollback_path.exists() and previous_media_path is not None:
                        previous_media_path.parent.mkdir(parents=True, exist_ok=True)
                        rollback_path.replace(previous_media_path)
                    raise

                transaction["previous_source"] = previous_source
                transaction["rollback_path"] = rollback_path
                transaction["committed"] = True
                for other_key, other_transaction in upload_transactions.items():
                    if other_key[:2] != (project_id, slot) or other_key == transaction_key:
                        continue
                    other_transaction["superseded"] = True
                    discard_upload_rollback(other_transaction)
                try:
                    backup.unlink(missing_ok=True)
                except OSError as exc:
                    app.logger.warning("Could not remove the upload rollback backup: %s", exc)
                try:
                    _cleanup_old_source(project_root, slot, previous_source, keep=destination)
                except OSError as exc:
                    app.logger.warning("Could not remove superseded source assets: %s", exc)
                for active_job in jobs.active(project_id=project_id, kind="prepare_source"):
                    if str(active_job.dedupe_key).split(":", 1)[0] == slot:
                        jobs.cancel(active_job.id)
                try:
                    job = jobs.submit(
                        "prepare_source",
                        project_id,
                        _prepare_source,
                        project_id,
                        slot,
                        transaction_id,
                        store,
                        settings,
                        dedupe_key=f"{slot}:{transaction_id}",
                    )
                except JobAdmissionError as exc:
                    # The import is already durable. Report success and leave a
                    # retryable state instead of returning an error that falsely
                    # implies the user's footage was lost.
                    _mark_source_preparation(
                        store,
                        project_id,
                        slot,
                        transaction_id,
                        "failed",
                        f"Preparation queue unavailable: {exc}",
                    )
                    project = store.load(project_id)
                    job = None
        finally:
            if staging is not None:
                staging.unlink(missing_ok=True)
            with project_job_gate:
                remaining_uploads = active_uploads.get(project_id, 0) - 1
                if remaining_uploads > 0:
                    active_uploads[project_id] = remaining_uploads
                else:
                    active_uploads.pop(project_id, None)
                transaction = upload_transactions.get(transaction_key)
                if transaction and transaction.get("generation") == transaction_id:
                    transaction["active"] = False
                    transaction["updated_at"] = time.monotonic()
                    if isinstance(transaction.get("rollback_path"), Path):
                        expiration = threading.Timer(
                            UPLOAD_TRANSACTION_TTL_SECONDS + 1,
                            expire_upload_transaction,
                            args=(transaction_key, transaction_id),
                        )
                        expiration.daemon = True
                        transaction["expiration"] = expiration
                        expiration.start()
                prune_upload_transactions(time.monotonic())
        public_project = _public_project(project)
        return jsonify({
            "project": public_project,
            "source": public_project.get("sources", {}).get(slot),
            "job": job.public() if job is not None else None,
            "preparation_deferred": job is None,
            "upload_token": upload_token,
        }), 201

    @app.post("/api/projects/<project_id>/sources/<slot>/uploads/<upload_token>/cancel")
    def cancel_source_upload(project_id: str, slot: str, upload_token: str):
        slot = slot.upper()
        if slot not in {"A", "B"}:
            raise APIInputError("invalid_slot", "Slot must be A or B.")
        if not UPLOAD_TOKEN_PATTERN.fullmatch(upload_token):
            raise APIInputError(
                "invalid_upload_token",
                "Upload token must contain 16-128 letters, numbers, underscores, or hyphens.",
            )

        transaction_key = (project_id, slot, upload_token)
        removed = False
        restored = False
        rollback_available = True
        with project_job_gate:
            project = store.load(project_id)
            now = time.monotonic()
            prune_upload_transactions(now)
            transaction = upload_transactions.get(transaction_key)
            known_upload = transaction is not None
            if transaction is None:
                if len(upload_transactions) >= MAX_UPLOAD_TRANSACTIONS:
                    raise APIInputError(
                        "too_many_uploads",
                        "Too many upload transactions are active. Wait for an import to finish and try again.",
                        429,
                    )
                transaction = {
                    "generation": None,
                    "cancelled": True,
                    "active": False,
                    "updated_at": now,
                }
                upload_transactions[transaction_key] = transaction
            else:
                transaction["cancelled"] = True
                transaction["updated_at"] = now

            generation = str(transaction.get("generation") or "")
            active = bool(transaction.get("active"))
            if generation and not transaction.get("superseded"):
                current = project.get("sources", {}).get(slot)
                if isinstance(current, dict) and str(current.get("generation") or "") == generation:
                    uploaded_source = json.loads(json.dumps(current))
                    replacement_source = transaction.get("previous_source")
                    if isinstance(replacement_source, dict):
                        replacement_source = json.loads(json.dumps(replacement_source))
                    else:
                        replacement_source = None
                    rollback_path = transaction.get("rollback_path")
                    rollback_available = replacement_source is None or (
                        isinstance(rollback_path, Path) and rollback_path.is_file()
                    )
                    if rollback_available:
                        for active_job in jobs.active(project_id=project_id, kind="prepare_source"):
                            if str(active_job.dedupe_key) == f"{slot}:{generation}":
                                jobs.cancel(active_job.id)

                        current_path = _safe_project_child(
                            store.project_dir(project_id),
                            uploaded_source.get("relative_path"),
                        )
                        replacement_path = (
                            _safe_project_child(store.project_dir(project_id), replacement_source.get("relative_path"))
                            if replacement_source is not None
                            else None
                        )
                        cancelled_path = store.project_dir(project_id) / "media" / (
                            f".cancelled-{slot}-{generation}{current_path.suffix if current_path is not None else ''}"
                        )
                        moved_current = False
                        restored_file = False
                        if current_path is not None and current_path.is_file():
                            current_path.replace(cancelled_path)
                            moved_current = True
                        if replacement_source is not None:
                            if replacement_path is None or not isinstance(rollback_path, Path):
                                raise RuntimeError("Invalid upload rollback state")
                            replacement_path.parent.mkdir(parents=True, exist_ok=True)
                            rollback_path.replace(replacement_path)
                            restored_file = True

                        def roll_back_cancelled_upload(latest: dict[str, Any]) -> None:
                            source = latest.setdefault("sources", {}).get(slot)
                            if not isinstance(source, dict) or str(source.get("generation") or "") != generation:
                                raise RuntimeError("upload_generation_changed")
                            if replacement_source is not None:
                                replacement_source["preview_relative_path"] = None
                                replacement_source["thumbnail_names"] = []
                                replacement_source["preparation"] = "queued"
                                replacement_source.pop("preparation_error", None)
                                replacement_source["audio_profile_ready"] = False
                            latest["sources"][slot] = replacement_source
                            latest.setdefault("pre_analysis", {}).setdefault("audio", {}).pop(slot, None)
                            latest.setdefault("pre_analysis", {}).setdefault("vision", {}).pop(slot, None)
                            latest["analysis"] = None
                            latest["draft"] = None
                            _reset_manual_after_source_change(
                                latest,
                                slot,
                                replacing=replacement_source is not None,
                            )

                        try:
                            project = store.update(project_id, roll_back_cancelled_upload)
                        except Exception:
                            if restored_file and replacement_path is not None and isinstance(rollback_path, Path):
                                replacement_path.replace(rollback_path)
                            if moved_current and current_path is not None and cancelled_path.exists():
                                current_path.parent.mkdir(parents=True, exist_ok=True)
                                cancelled_path.replace(current_path)
                            raise
                        else:
                            removed = True
                            restored = replacement_source is not None
                            cancelled_path.unlink(missing_ok=True)
                            transaction["rolled_back"] = True
                            transaction["superseded"] = True
                            discard_upload_rollback(transaction)
                            try:
                                _cleanup_old_source(
                                    store.project_dir(project_id),
                                    slot,
                                    uploaded_source,
                                    keep=replacement_path,
                                )
                            except OSError as exc:
                                app.logger.warning("Could not remove cancelled upload assets: %s", exc)
                            if replacement_source is not None:
                                restored_generation = str(replacement_source.get("generation") or "")
                                try:
                                    jobs.submit(
                                        "prepare_source",
                                        project_id,
                                        _prepare_source,
                                        project_id,
                                        slot,
                                        restored_generation,
                                        store,
                                        settings,
                                        dedupe_key=f"{slot}:{restored_generation}",
                                    )
                                except JobAdmissionError as exc:
                                    _mark_source_preparation(
                                        store,
                                        project_id,
                                        slot,
                                        restored_generation,
                                        "failed",
                                        f"Preparation queue unavailable: {exc}",
                                    )
                                    project = store.load(project_id)

        return jsonify({
            "cancelled": True,
            "active": active,
            "removed": removed,
            "restored": restored,
            "rollback_available": rollback_available,
            "known_upload": known_upload,
        }), 202

    @app.delete("/api/projects/<project_id>/sources/<slot>")
    def remove_source(project_id: str, slot: str):
        slot = slot.upper()
        if slot not in {"A", "B"}:
            return jsonify({"error": "invalid_slot", "message": "Slot must be A or B."}), 400
        previous_source: dict[str, Any] | None = None

        class SourceAlreadyMissing(RuntimeError):
            pass

        def remove(project: dict[str, Any]) -> None:
            nonlocal previous_source
            source = project.setdefault("sources", {}).get(slot)
            if not isinstance(source, dict):
                raise SourceAlreadyMissing()
            previous_source = dict(source) if isinstance(source, dict) else None
            project["sources"][slot] = None
            project.setdefault("pre_analysis", {}).setdefault("audio", {}).pop(slot, None)
            project.setdefault("pre_analysis", {}).setdefault("vision", {}).pop(slot, None)
            project["analysis"] = None
            project["draft"] = None
            _reset_manual_after_source_change(project, slot)

        with project_job_gate:
            for active_job in jobs.active(project_id=project_id, kind="prepare_source"):
                if str(active_job.dedupe_key).split(":", 1)[0] == slot:
                    jobs.cancel(active_job.id)
            try:
                project = store.update(project_id, remove)
            except SourceAlreadyMissing:
                project = store.load(project_id)
            else:
                try:
                    _cleanup_old_source(store.project_dir(project_id), slot, previous_source)
                except OSError as exc:
                    app.logger.warning("Could not remove source assets: %s", exc)
            for transaction_key, transaction in list(upload_transactions.items()):
                if transaction_key[:2] != (project_id, slot):
                    continue
                transaction["superseded"] = True
                discard_upload_rollback(transaction)
        return jsonify({"project": _public_project(project)})

    @app.post("/api/projects/<project_id>/sources/<slot>/prepare")
    def retry_source_preparation(project_id: str, slot: str):
        slot = slot.upper()
        if slot not in {"A", "B"}:
            raise APIInputError("invalid_slot", "Slot must be A or B.")
        project = store.load(project_id)
        source = project.get("sources", {}).get(slot)
        if not source:
            raise APIInputError("source_required", f"Source {slot} is missing.", 404)
        generation = str(source.get("generation") or "")
        if not generation:
            raise APIInputError("invalid_source", "The source cannot be prepared because its generation is missing.", 409)
        dedupe_key = f"{slot}:{generation}"
        active = [
            job for job in jobs.active(project_id=project_id, kind="prepare_source")
            if job.dedupe_key == dedupe_key
        ]
        if active:
            return jsonify({"project": _public_project(project), "job": active[0].public()}), 200

        def mark_queued(latest: dict[str, Any]) -> None:
            current = latest.get("sources", {}).get(slot)
            if not current or str(current.get("generation") or "") != generation:
                raise RuntimeError("project_changed_during_analysis")
            current["preparation"] = "queued"

        with project_job_gate:
            # Reload and validate inside the same admission gate used by source
            # replacement/deletion, otherwise a retry can enqueue stale work.
            project = store.update(project_id, mark_queued)
            try:
                job = jobs.submit(
                    "prepare_source",
                    project_id,
                    _prepare_source,
                    project_id,
                    slot,
                    generation,
                    store,
                    settings,
                    dedupe_key=dedupe_key,
                )
            except JobAdmissionError as exc:
                _mark_source_preparation(
                    store,
                    project_id,
                    slot,
                    generation,
                    "failed",
                    f"Preparation queue unavailable: {exc}",
                )
                raise
        return jsonify({"project": _public_project(project), "job": job.public()}), 202

    @app.post("/api/projects/<project_id>/manual-draft")
    def manual_draft(project_id: str):
        payload = _json_object()
        _reject_unknown_fields(payload, {"expected_revision"})
        revision = payload.get("expected_revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise APIInputError("invalid_revision", "Refresh the project before starting your timeline.")
        with project_job_gate:
            if jobs.active(project_id=project_id) or active_uploads.get(project_id, 0):
                raise APIInputError("project_busy", "Wait for your recordings to finish preparing.", 409)
            try:
                project = store.update(project_id, start_manual_draft, expected_revision=revision)
            except ManualEditError as error:
                raise APIInputError("invalid_manual_edit", str(error)) from error
        return jsonify({"project": _public_project(project)})

    @app.post("/api/projects/<project_id>/director")
    def run_director(project_id: str):
        payload = _json_object()
        _validate_settings_payload(payload)
        project = store.load(project_id)
        if not project.get("sources", {}).get("A"):
            return jsonify({"error": "source_required", "message": "Add source A before generating an edit."}), 400
        effective = dict(project.get("settings", {}))
        effective.update(payload)
        goal = str(effective.get("goal") or "short")
        selected_settings = connections.job_settings(settings)
        if cloud_enabled(selected_settings):
            require_connection(selected_settings)
        if goal in {"short", "podcast"}:
            status = story_ai_status(selected_settings, effective)
            if not status["ready"]:
                return jsonify({
                    "error": "story_ai_required",
                    "message": (
                        "Story AI is disabled in CUTROOM configuration."
                        if status["reason"] == "ai_disabled"
                        else "Local Story AI is not ready. Use Retry AI to prepare the engine, then retry this edit."
                        if status["reason"] == "ollama_unavailable"
                        else f"Story AI model {status['recommended_model']} must be installed before this edit can be created."
                    ),
                    "story_ai": status,
                    "runtime": ai_runtime.snapshot(),
                    "recommended_model": status["recommended_model"],
                }), 409
        def require_source(latest: dict[str, Any]) -> None:
            if not latest.get("sources", {}).get("A"):
                raise APIInputError("source_required", "Add source A before generating an edit.")

        job = submit_project_job(
            "director",
            project_id,
            analyze_project,
            project_id,
            store,
            selected_settings,
            payload,
            validate_project=require_source,
            job_identity=payload,
        )
        return jsonify({"job": job.public()}), 202

    @app.post("/api/projects/<project_id>/director/refine")
    def refine(project_id: str):
        payload = _json_object()
        _reject_unknown_fields(payload, {"command"})
        _require_optional_string(payload, "command", max_length=32)
        command = payload.get("command") or ""
        if command not in {"shorter", "keep_more", "more_energy", "fewer_switches", "focus_speaker", "new_variation"}:
            raise APIInputError("invalid_command", "Unknown refinement command.")
        def require_draft(latest: dict[str, Any]) -> None:
            if not latest.get("sources", {}).get("A") or not latest.get("draft"):
                raise APIInputError("draft_required", "Generate a draft before refining it.")
            if command == "new_variation" and (
                latest["draft"].get("goal") != "short"
                or latest.get("settings", {}).get("goal") != "short"
            ):
                raise APIInputError(
                    "invalid_variation", "Build a Short draft before requesting another cut.",
                )

        job = submit_project_job(
            "refine",
            project_id,
            refine_project,
            project_id,
            store,
            connections.job_settings(settings),
            command,
            validate_project=require_draft,
            job_identity={"command": command},
        )
        return jsonify({"job": job.public()}), 202

    @app.post("/api/projects/<project_id>/render")
    def render(project_id: str):
        payload = _json_object()
        _reject_unknown_fields(payload, {"quality", "fps"})
        if "fps" in payload:
            try:
                validate_export_fps(payload["fps"])
            except ValueError as exc:
                raise APIInputError("invalid_field", str(exc)) from exc
        _require_optional_string(payload, "quality", max_length=24)
        if "quality" in payload and payload["quality"] not in {"fast", "balanced", "quality"}:
            raise APIInputError("invalid_field", "quality must be fast, balanced or quality.")
        project = store.load(project_id)
        if not project.get("draft"):
            return jsonify({"error": "draft_required", "message": "Generate or create a draft before rendering."}), 400
        try:
            ensure_render_storage(project, settings, store.project_dir(project_id), payload)
        except InsufficientStorageError as error:
            return jsonify(error.as_dict()), error.status_code
        def require_renderable(latest: dict[str, Any]) -> None:
            if not latest.get("sources", {}).get("A") or not latest.get("draft"):
                raise APIInputError("draft_required", "Generate or create a draft before rendering.")

        job = submit_project_job(
            "render",
            project_id,
            render_project,
            project_id,
            store,
            settings,
            payload,
            validate_project=require_renderable,
            job_identity=payload,
        )
        return jsonify({"job": job.public()}), 202

    @app.get("/api/jobs/<job_id>")
    def get_job(job_id: str):
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "not_found", "message": "Job not found."}), 404
        return jsonify({"job": job.public()})

    @app.get("/api/jobs")
    def list_jobs():
        project_id = request.args.get("project_id")
        if project_id:
            store.load(project_id)
        return jsonify({"jobs": jobs.recovery_snapshot(project_id)})

    @app.get("/api/projects/<project_id>/jobs/active")
    def active_project_jobs(project_id: str):
        store.load(project_id)
        return jsonify({
            "jobs": [job.public() for job in jobs.active(project_id=project_id)],
            "recent": jobs.recovery_snapshot(project_id, limit=20),
        })

    @app.post("/api/jobs/<job_id>/cancel")
    def cancel_job(job_id: str):
        payload = _json_object()
        _reject_unknown_fields(payload, set())
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "not_found", "message": "Job not found."}), 404

        # Cancellation is deliberately idempotent. A late/repeated request still
        # returns the authoritative terminal record instead of looking like a
        # network failure to a polling client.
        accepted = jobs.cancel(job_id)
        latest = jobs.get(job_id) or job
        response = {
            "ok": True,
            "accepted": bool(accepted),
            "status": latest.status,
            "job": latest.public(),
        }
        return jsonify(response), (202 if accepted and latest.status in {"queued", "running"} else 200)

    @app.get("/api/projects/<project_id>/media/<slot>")
    def project_media(project_id: str, slot: str):
        project = store.load(project_id)
        source = project.get("sources", {}).get(slot.upper())
        if not source:
            return jsonify({"error": "not_found", "message": "Source not found."}), 404
        relative = source.get("preview_relative_path") or source.get("relative_path")
        path = _safe_project_child(store.project_dir(project_id), relative)
        if (path is None or not path.is_file()) and source.get("browser_ready"):
            # Proxies are disposable caches; a missing one must not hide a
            # compatible original. Do not fall back to unsupported codecs.
            path = _safe_project_child(store.project_dir(project_id), source.get("relative_path"))
        if path is None or not path.is_file():
            return jsonify({"error": "not_found", "message": "Source file not found."}), 404
        return send_file(path, conditional=True, download_name=source.get("name") or path.name)

    @app.get("/api/projects/<project_id>/cache/<path:relative>")
    def project_cache(project_id: str, relative: str):
        cache_dir = (store.project_dir(project_id) / "cache").resolve()
        path = (cache_dir / relative).resolve()
        if cache_dir not in path.parents or not path.is_file():
            return jsonify({"error": "not_found", "message": "Cache item not found."}), 404
        return send_file(path, conditional=True)

    @app.get("/api/exports/<path:filename>")
    def download_export(filename: str):
        safe = Path(filename).name
        if not safe or filename != safe:
            return jsonify({"error": "not_found", "message": "Export not found."}), 404
        export_root = settings.exports_dir.resolve()
        path = (export_root / safe).resolve()
        if path.parent != export_root or not path.is_file():
            return jsonify({"error": "not_found", "message": "Export not found."}), 404
        return send_file(path, conditional=True, as_attachment=True, download_name=safe)

    @app.get("/api/models/local")
    def local_models():
        # Disk/cached status only: opening the setup panel must not download,
        # launch a daemon, contact model hosts, or load inference libraries.
        result = local_model_catalog(settings, ai_runtime.snapshot(), engine_installed=bool(resolve_ollama_executable()))
        result["jobs"] = [job.public() for job in jobs.list(kind="model_install", limit=30)]
        return jsonify(result)

    @app.post("/api/models/install")
    def install_model():
        payload = _json_object()
        _reject_unknown_fields(payload, {"kind", "model"})
        _require_optional_string(payload, "kind", max_length=24)
        _require_optional_string(payload, "model", max_length=120)
        kind = payload.get("kind") or "editor"
        default_model = settings.ai.get("whisper_model", "base") if kind == "transcription" else settings.ai.get("editor_model", "qwen3.5:4b")
        model = str(payload.get("model") or default_model)
        if kind not in {"editor", "transcription"}:
            return jsonify({"error": "unsupported_kind", "message": "Choose Story AI or speech transcription from Local models."}), 400
        if not re_safe_model(model):
            return jsonify({"error": "invalid_model", "message": "Invalid model name."}), 400
        if not supported_install(kind, model):
            return jsonify({"error": "unsupported_model", "message": "Choose a supported model from Local models. Custom model downloads are not accepted here."}), 400
        dedupe_key = model if kind == "editor" else f"transcription:{model}"

        def check_download_admission():
            active_processing = next((job for job in jobs.active() if job.kind in FOREGROUND_JOB_KINDS), None)
            if active_processing:
                raise JobAdmissionError("Finish or cancel active AI processing or export before downloading models.",
                                        code="job_conflict", active_job_id=active_processing.id)
            active_downloads = jobs.active(kind="model_install")
            conflicting = next((job for job in active_downloads if job.dedupe_key != dedupe_key), None)
            if conflicting:
                raise JobAdmissionError("One model is already downloading. Finish or cancel it before starting another.",
                                        code="job_conflict", active_job_id=conflicting.id)
            return next((job for job in active_downloads if job.dedupe_key == dedupe_key), None)

        with project_job_gate:
            existing_download = check_download_admission()
            if existing_download:
                return jsonify({"job": existing_download.public()}), 202
        if kind == "editor":
            # A slow daemon start must not lock the manual editor. Recheck
            # admission after the probe so competing requests cannot overlap.
            runtime = ai_runtime.ensure_ready(timeout=30, retry=True)
            if not runtime["available"]:
                return jsonify({
                    "error": "ai_runtime_unavailable", "message": runtime["message"], "runtime": runtime,
                    "install_url": OLLAMA_INSTALL_URL,
                }), 409
        with project_job_gate:
            check_download_admission()
            job = jobs.submit(
                "model_install", None,
                _install_ollama_model if kind == "editor" else install_transcription,
                model, settings, dedupe_key=dedupe_key,
            )
        return jsonify({"job": job.public()}), 202

    return app


def _command_ok(command: list[str]) -> bool:
    try:
        return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _reserve_server_sockets(host: str, port: int) -> list[socket.socket]:
    """Bind and retain every resolved local socket until Waitress takes ownership."""
    candidates: list[socket.socket] = []
    seen: set[tuple[int, tuple[Any, ...]]] = set()
    try:
        try:
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise ServerStartupError(f"CUTROOM could not resolve its local host {host!r}: {exc}") from exc
        for family, socktype, protocol, _canonical_name, address in addresses:
            identity = (family, tuple(address))
            if identity in seen:
                continue
            seen.add(identity)
            candidate = socket.socket(family, socktype, protocol)
            try:
                if family == socket.AF_INET6 and hasattr(socket, "IPV6_V6ONLY"):
                    candidate.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    candidate.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                candidate.bind(address)
            except OSError as exc:
                candidate.close()
                raise ServerStartupError(
                    f"CUTROOM cannot start because {host}:{port} is already in use or unavailable. "
                    "Close the other program or choose another CUTROOM_PORT."
                ) from exc
            candidates.append(candidate)
        if not candidates:
            raise ServerStartupError(f"CUTROOM could not find a local address for {host!r}.")
        return candidates
    except Exception:
        for candidate in candidates:
            candidate.close()
        raise


def _assert_server_port_available(host: str, port: int) -> None:
    """Compatibility check for callers that do not need to retain the reservation."""
    candidates = _reserve_server_sockets(host, port)
    for candidate in candidates:
        candidate.close()


def _cutroom_instance_id(settings: Settings) -> str:
    """Return a stable, non-secret identity for one local CUTROOM data store."""
    return hashlib.sha256(str(settings.data_dir.resolve()).encode("utf-8")).hexdigest()[:16]


def _read_local_json(
    host: str,
    port: int,
    path: str,
    *,
    timeout: float,
    max_bytes: int,
) -> tuple[int | None, dict[str, Any] | None]:
    """Read one bounded loopback JSON response without proxies or redirects."""
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        connection.request(
            "GET",
            path,
            headers={"Accept": "application/json", "Connection": "close", "User-Agent": f"CUTROOM/{__version__}"},
        )
        response = connection.getresponse()
        status = int(response.status)
        raw = response.read(max_bytes + 1)
    except (OSError, TimeoutError, ValueError, http.client.HTTPException):
        return None, None
    finally:
        connection.close()
    if len(raw) > max_bytes:
        return status, None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return status, None
    if not isinstance(payload, dict):
        return status, None
    return status, payload


def _probe_existing_cutroom_server(
    host: str,
    port: int,
    expected_instance_id: str,
    *,
    timeout: float = 0.8,
) -> str:
    """Classify an occupied port without constructing a second CUTROOM app."""
    status, payload = _read_local_json(
        host,
        port,
        "/api/instance",
        timeout=timeout,
        max_bytes=INSTANCE_RESPONSE_LIMIT,
    )
    legacy = status == 404
    if legacy:
        status, payload = _read_local_json(
            host,
            port,
            "/api/system",
            timeout=max(timeout, 2.5),
            max_bytes=LEGACY_SYSTEM_RESPONSE_LIMIT,
        )
    if status != 200 or not payload:
        return "unknown"
    if legacy:
        if payload.get("product") not in (None, "CUTROOM"):
            return "unknown"
    elif payload.get("service") != "cutroom" or payload.get("protocol") != INSTANCE_PROTOCOL_VERSION:
        return "unknown"
    if payload.get("instance_id") != expected_instance_id:
        return "different_instance"
    if payload.get("version") != __version__:
        return "different_version"
    return "match"


def _http_server_url(host: str, port: int) -> str:
    """Build a browser-safe local URL, including bracketed IPv6 literals."""
    display_host = str(host).strip()
    if ":" in display_host and not display_host.startswith("["):
        display_host = f"[{display_host}]"
    return f"http://{display_host}:{int(port)}"


def _ollama_status(settings: Settings) -> dict[str, Any]:
    endpoint = str(settings.ai.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(endpoint, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"available": True, "models": [model.get("name") for model in payload.get("models", [])]}
    except Exception:
        return {"available": False, "models": []}


def _model_status(settings: Settings) -> dict[str, Any]:
    try:
        import faster_whisper  # noqa: F401
        whisper_installed = True
    except ImportError:
        whisper_installed = False
    ollama = {"available": False, "models": []} if cloud_enabled(settings) else _ollama_status(settings)
    configured = str(settings.ai.get("editor_model", "qwen3.5:4b"))
    story = story_ai_status(settings, {})
    return {
        "whisper_installed": whisper_installed,
        "whisper_model": settings.ai.get("whisper_model", "base"),
        "hebrew_whisper_model": settings.ai.get("hebrew_whisper_model"),
        "ollama": ollama,
        "editor_model": configured,
        "editor_quality_model": settings.ai.get("editor_quality_model", "qwen3.5:9b"),
        "editor_lite_model": settings.ai.get("editor_lite_model", "qwen3.5:2b"),
        "editor_model_installed": any(str(name).replace(":latest", "") == configured.replace(":latest", "") for name in ollama.get("models", [])),
        "story_ai_ready": bool(story.get("ready")),
        "selected_story_model": story.get("selected_model"),
        "recommended_story_model": story.get("recommended_model"),
    }


def re_safe_model(value: str) -> bool:
    import re
    if not isinstance(value, str) or not value or len(value) > 120:
        return False
    if value.startswith(("-", "/")) or "//" in value or any(part in {"", ".", ".."} for part in value.split("/")):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?", value))


def re_safe_language(value: str) -> bool:
    import re
    return value == "auto" or bool(re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})?", value))


def _install_ollama_model(context: JobContext, model: str, settings: Settings) -> dict[str, Any]:
    context.check_cancelled()
    executable = resolve_ollama_executable()
    if not executable:
        raise RuntimeError("Ollama is not installed. Install the local engine once, then use Retry AI.")
    context.update(0.02, f"Installing {model}")
    process = subprocess.Popen(
        [executable, "pull", model],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace", env=ollama_environment(settings),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    output: list[str] = []
    lines: queue.Queue[str] = queue.Queue(maxsize=256)
    reader_done = threading.Event()
    stop_reader = threading.Event()

    def read_output() -> None:
        try:
            if process.stdout is None:
                return
            for line in process.stdout:
                while not stop_reader.is_set():
                    try:
                        lines.put(line, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            reader_done.set()

    reader = threading.Thread(target=read_output, name=f"cutroom-ollama-{context.job.id}", daemon=True)
    reader.start()
    try:
        while True:
            context.check_cancelled()
            try:
                line = lines.get(timeout=0.1)
            except queue.Empty:
                if process.poll() is not None and reader_done.is_set():
                    break
                continue
            output.append(line.rstrip())
            if len(output) > 40:
                del output[:20]
            clean_line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line).strip()
            percent = re.search(r"(?:^|\s)(\d{1,3})%", clean_line)
            # Ollama reports each layer separately; this is current-layer
            # progress, never a fabricated overall download percentage.
            progress = min(0.94, max(0.02, int(percent.group(1)) / 100 * 0.94)) if percent else context.job.progress
            context.update(progress, (f"Current layer: {clean_line}" if percent else clean_line)[-160:] or f"Installing {model}")
        context.checkpoint()
        if process.wait() != 0:
            raise RuntimeError("Ollama could not download the selected model. Check your internet connection, free disk space, and Ollama version, then retry.")
        context.update(1.0, f"{model} is ready")
        return {"model": model, "installed": True, "log": output[-20:]}
    finally:
        stop_reader.set()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        reader.join(timeout=1)


def _mark_source_preparation(
    store: ProjectStore,
    project_id: str,
    slot: str,
    generation: str,
    status: str,
    error: str | None = None,
) -> None:
    class StaleSource(RuntimeError):
        pass

    def mark(latest: dict[str, Any]) -> None:
        current = latest.get("sources", {}).get(slot)
        if not current or str(current.get("generation") or "") != generation:
            raise StaleSource()
        current["preparation"] = status
        if error:
            current["preparation_error"] = error[:500]
        else:
            current.pop("preparation_error", None)

    try:
        store.update(project_id, mark)
    except (FileNotFoundError, StaleSource):
        # The source/project was intentionally replaced or removed. Its newer
        # state must never be overwritten by the stale worker finishing.
        return


def _prepare_source(
    context: JobContext,
    project_id: str,
    slot: str,
    generation: str,
    store: ProjectStore,
    settings: Settings,
) -> dict[str, Any]:
    try:
        return _prepare_source_impl(context, project_id, slot, generation, store, settings)
    except JobCancelled:
        _mark_source_preparation(store, project_id, slot, generation, "cancelled")
        raise
    except Exception as exc:
        _mark_source_preparation(
            store,
            project_id,
            slot,
            generation,
            "failed",
            f"{type(exc).__name__}: {exc}",
        )
        raise


def _prepare_source_impl(
    context: JobContext,
    project_id: str,
    slot: str,
    generation: str,
    store: ProjectStore,
    settings: Settings,
) -> dict[str, Any]:
    project = store.load(project_id)
    source = project.get("sources", {}).get(slot)
    if not source or source.get("generation") != generation:
        raise JobCancelled("Source was replaced before preparation started")
    path = _safe_project_child(store.project_dir(project_id), source.get("relative_path"))
    if path is None or not path.is_file():
        raise RuntimeError("Source media path is missing or outside the project")

    # Embedded-camera discovery samples only a handful of frames and is much
    # cheaper than scanning a multi-hour audio track. Run it first for source A so
    # the user can confirm a baked-in camera within seconds while the rest of the
    # background preparation continues.
    vision_profile: dict[str, Any] | None = None
    if slot == "A":
        context.update(0.03, "Looking for a camera inside the recording")
        sample_map = settings.raw.get("vision_samples", {}) if isinstance(settings.raw.get("vision_samples"), dict) else {}
        preparation_samples = normalized_vision_sample_count(sample_map.get("lite", 12), 12)
        try:
            vision_profile = analyze_faces_and_embedded_camera(
                path,
                float(source.get("duration", 0)),
                progress=lambda value, message: context.update(0.03 + value * 0.04, message),
                samples=preparation_samples,
                cancel_check=context.check_cancelled,
            )
            vision_profile = {
                **vision_profile,
                "source_generation": generation,
                "sample_count": preparation_samples,
                "profile": "lite",
            }
        except JobCancelled:
            raise
        except Exception as exc:
            vision_profile = {
                "version": VISION_ANALYSIS_VERSION,
                "available": False,
                "reason": "preparation_error",
                "warning": f"{type(exc).__name__}: {exc}",
                "embedded_camera": None,
                "source_generation": generation,
                "sample_count": preparation_samples,
                "profile": "lite",
            }
        context.checkpoint("Saving camera detection")

        def save_vision_profile(latest: dict[str, Any]) -> None:
            current = latest.get("sources", {}).get(slot)
            if not current or current.get("generation") != generation:
                raise JobCancelled("Source was replaced during camera detection")
            latest.setdefault("pre_analysis", {}).setdefault("vision", {})[slot] = vision_profile
            current["embedded_camera_detected"] = bool((vision_profile or {}).get("embedded_camera"))

        store.update(project_id, save_vision_profile)
        # This explicit post-save boundary lets the UI refresh without racing the
        # project write or waiting for the full audio scan/proxy.
        context.update(0.075, "Camera detection ready")

    # Measure audio before building a proxy. This gives the user a real dB waveform
    # and recommended silence line without waiting for browser transcoding.
    audio_start = 0.08 if slot == "A" else 0.03
    audio_span = 0.21 if slot == "A" else 0.26
    context.update(audio_start, "Measuring audio levels")
    if source.get("has_audio"):
        try:
            audio_profile = analyze_audio(
                path,
                settings,
                float(source.get("duration", 0)),
                progress=lambda value, message: context.update(audio_start + value * audio_span, message),
                cancel_check=context.check_cancelled,
            )
        except JobCancelled:
            raise
        except Exception as exc:
            audio_profile = {"available": False, "ranges": {}, "waveform": [], "summary": {}, "warning": f"{type(exc).__name__}: {exc}"}
    else:
        audio_profile = {"available": False, "ranges": {}, "waveform": [], "summary": {}, "warning": "Source has no audio track"}
    context.checkpoint("Saving audio analysis")

    def save_audio_profile(latest: dict[str, Any]) -> None:
        current = latest.get("sources", {}).get(slot)
        if not current or current.get("generation") != generation:
            raise JobCancelled("Source was replaced during preparation")
        latest.setdefault("pre_analysis", {}).setdefault("audio", {})[slot] = audio_profile
        current["audio_profile_ready"] = bool(audio_profile.get("available"))

    store.update(project_id, save_audio_profile)
    # Publish only after the profile is durable; polling at this progress cannot
    # consume its one refresh on a state that has not been saved yet.
    context.update(0.295, "Source analysis ready")

    context.update(0.30, "Checking browser compatibility")
    preview_relative = None
    if not source.get("browser_ready"):
        cached_preview = _safe_project_child(store.project_dir(project_id), source.get("preview_relative_path"))
        if cached_preview is not None and cached_preview.is_file():
            preview_relative = cached_preview.relative_to(store.project_dir(project_id)).as_posix()
            context.update(0.85, "Reusing browser preview")
        else:
            preview = store.project_dir(project_id) / "cache" / f"proxy-{slot}.mp4"
            try:
                create_proxy(
                    path,
                    preview,
                    settings,
                    progress=lambda value, message: context.update(0.30 + value * 0.55, message),
                    cancel_check=context.check_cancelled,
                )
                context.checkpoint()
            except JobCancelled:
                preview.unlink(missing_ok=True)
                raise
            preview_relative = preview.relative_to(store.project_dir(project_id)).as_posix()
    context.update(0.88, "Preparing timeline frames")
    thumbnails: list[str] = []
    try:
        thumb_dir = store.project_dir(project_id) / "cache" / f"thumbnails-{slot}"
        thumb_source = (store.project_dir(project_id) / preview_relative) if preview_relative else path
        context.checkpoint()
        cached_names = [
            Path(str(name)).name
            for name in (source.get("thumbnail_names") or [])[:12]
            if str(name).strip()
        ]
        cached_thumbnails_are_complete = bool(
            len(cached_names) == 12
            and all((thumb_dir / name).is_file() for name in cached_names)
        )
        if cached_thumbnails_are_complete:
            thumbnails = cached_names
            context.update(0.98, "Reusing timeline frames")
        else:
            thumbnails = extract_thumbnails(
                thumb_source,
                thumb_dir,
                float(source.get("duration", 0)),
                settings,
                count=12,
                cancel_check=context.check_cancelled,
            )
        context.checkpoint()
    except JobCancelled:
        raise
    except Exception:
        thumbnails = []

    def finish_preparation(latest: dict[str, Any]) -> None:
        current = latest.get("sources", {}).get(slot)
        if not current or current.get("generation") != generation:
            raise JobCancelled("Source was replaced during preparation")
        current["preview_relative_path"] = preview_relative
        current["thumbnail_names"] = thumbnails
        current["preparation"] = "ready"
        current.pop("preparation_error", None)
    context.checkpoint("Saving prepared source")
    context.commit()
    store.update(project_id, finish_preparation)
    context.update(1.0, "Source ready")
    return {
        "slot": slot,
        "preview": preview_relative,
        "thumbnails": thumbnails,
        "audio_profile_ready": bool(audio_profile.get("available")),
        "embedded_camera_detected": bool((vision_profile or {}).get("embedded_camera")),
    }


def _public_project(project: dict[str, Any]) -> dict[str, Any]:
    public = json.loads(json.dumps(project))
    strip_private_edit_history(public)
    try:
        public["editor_sequence"] = editor_sequence_snapshot(public)
    except SourceTrackError as error:
        # A malformed old draft must remain openable; report the editor issue
        # without silently replacing its footage with a different sequence.
        public["editor_sequence"] = {"error": str(error)}
    project_id = public["id"]
    for slot, source in public.get("sources", {}).items():
        if source:
            source.pop("relative_path", None)
            source.pop("preview_relative_path", None)
            source["url"] = f"/api/projects/{project_id}/media/{slot}"
            names = list(source.get("thumbnail_names") or [])
            source["thumbnail_urls"] = [f"/api/projects/{project_id}/cache/thumbnails-{slot}/{Path(name).name}" for name in names]
    analysis = public.get("analysis")
    if analysis and analysis.get("waveform"):
        waveform_name = Path(analysis["waveform"]).name
        analysis["waveform_url"] = f"/api/projects/{project_id}/cache/{waveform_name}"
    if analysis:
        thumbs = analysis.get("thumbnails", {}).get("A", [])
        analysis.setdefault("thumbnail_urls", {})["A"] = [f"/api/projects/{project_id}/cache/thumbnails-A/{name}" for name in thumbs]
    for export in public.get("exports", []):
        export.pop("relative_path", None)
        export["url"] = f"/api/exports/{export['name']}"
    return public


def main() -> None:
    settings = load_settings()
    host = str(settings.raw.get("host", "127.0.0.1"))
    port = int(settings.raw.get("port", 8765))
    url = _http_server_url(host, port)
    instance_id = _cutroom_instance_id(settings)
    try:
        reserved_sockets = _reserve_server_sockets(host, port)
    except ServerStartupError as error:
        owner = _probe_existing_cutroom_server(host, port, instance_id)
        if owner == "match":
            print(f"CUTROOM AI {__version__} is already running at {url}")
            if settings.raw.get("open_browser", True) and os.environ.get("CUTROOM_NO_BROWSER") != "1":
                try:
                    webbrowser.open(url)
                except Exception:
                    print(f"Open CUTROOM in your browser: {url}")
            return
        if owner == "different_instance":
            raise ServerStartupError(
                f"{host}:{port} is used by another CUTROOM data folder. "
                "Close that CUTROOM window or choose another CUTROOM_PORT."
            ) from error
        if owner == "different_version":
            raise ServerStartupError(
                f"{host}:{port} is used by a different CUTROOM version. "
                "Close it before starting this version, or choose another CUTROOM_PORT."
            ) from error
        raise

    app = None
    jobs = None
    try:
        app = create_app(settings)
        jobs = app.extensions["cutroom_jobs"]
        # Start only after owning the CUTROOM port; re-opening the launcher must
        # reuse an existing instance instead of creating another AI supervisor.
        if app.extensions["cutroom_connections"].public()["mode"] == "local":
            app.extensions["cutroom_ai_runtime"].start_background()
        if settings.raw.get("open_browser", True) and os.environ.get("CUTROOM_NO_BROWSER") != "1":
            threading.Timer(1.2, lambda: webbrowser.open(url)).start()
        try:
            from waitress import serve
            request_body_limit = int(app.config.get("MAX_CONTENT_LENGTH") or (float(settings.raw.get("max_upload_gb", 40)) * 1024**3 + 32 * 1024**2))
            print(f"CUTROOM AI {__version__} — {url}")
            print(f"Upload transport limit: {request_body_limit / 1024**3:.1f} GiB")
            serve(
                app,
                sockets=reserved_sockets,
                threads=8,
                channel_timeout=3600,
                max_request_body_size=request_body_limit,
            )
        except ImportError:
            for candidate in reserved_sockets:
                candidate.close()
            reserved_sockets = []
            app.run(host=host, port=port, debug=False, threaded=True)
    finally:
        for candidate in reserved_sockets:
            candidate.close()
        if jobs is not None:
            jobs.shutdown(wait=False, cancel_pending=True)


if __name__ == "__main__":
    try:
        main()
    except ServerStartupError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
