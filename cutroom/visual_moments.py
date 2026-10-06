"""Local gameplay vision: which parts of a long recording show action.

A vision-capable local Story model (for example Qwen3.5 through Ollama) looks
at small contact sheets, four frames from one short window, and answers
concrete visual questions: is a weapon firing, are enemies visible, is this a
menu or a cutscene? CUTROOM turns those answers into a bounded 0..1 action
score and a short on-screen description. A small model rates "how exciting"
inconsistently, but it answers observable yes/no questions well, so the score
is computed here, not by the model.

Frames never leave this computer: the pass needs a loopback Ollama endpoint,
is skipped for cloud connections, never downloads a model, and never fails an
edit. Missing or partial results simply mean less evidence.
"""
from __future__ import annotations

import base64
import bisect
import http.client
import json
import math
import platform
import queue
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from .ai_runtime import open_ollama, read_ollama_json
from .config import Settings
from .edit_styles import get_edit_style

VISUAL_MOMENTS_VERSION = "gameplay-vision-v1"
WINDOW_SECONDS = 8.0
FRAMES_PER_WINDOW = 4
FRAME_WIDTH = 448
VISUAL_AI_MODES = ("auto", "on", "off")
DEFAULT_BUDGETS = {"lite": 48, "balanced": 120, "quality": 200}
DEFAULT_TIME_LIMIT_SECONDS = 900.0
MAX_CONSECUTIVE_FAILURES = 4

SCREENS = ("gameplay", "cutscene", "menu_or_map", "loading_or_black", "webcam_only", "other")
DEAD_SCREENS = frozenset({"menu_or_map", "loading_or_black"})
# Observable gameplay evidence and how much each contributes to the action
# score. Weights intentionally sum above 1: several signals together saturate.
ACTION_FLAGS = {
    "shooting": 0.38,
    "enemies_visible": 0.18,
    "explosion_fire_or_smoke": 0.16,
    "damage_or_hit_markers": 0.16,
    "player_downed_or_dead": 0.20,
    "fast_movement": 0.10,
}
# Flags describe player-controlled gameplay. A cinematic can look explosive but
# is rarely the clip a creator wants; menus and loading screens are dead time.
SCREEN_WEIGHTS = {
    "gameplay": 1.0,
    "cutscene": 0.35,
    "other": 0.45,
    "webcam_only": 0.25,
    "menu_or_map": 0.0,
    "loading_or_black": 0.0,
}
PLAIN_GAMEPLAY_SCORE = 0.12

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        **{name: {"type": "boolean"} for name in ACTION_FLAGS},
        "screen": {"type": "string", "enum": list(SCREENS)},
        "event": {"type": "string"},
    },
    "required": [*ACTION_FLAGS, "screen", "event"],
}
PROMPT = (
    "Four frames in time order (left-to-right, then top-to-bottom) from 8 seconds of a video game recording. "
    "A small streamer webcam box may sit in a corner; ignore it unless the webcam fills the whole screen. "
    "Answer only from what is visible. shooting: a weapon is firing, muzzle flash, tracers or the player aims and fires. "
    "enemies_visible: hostile characters, red health bars or enemy markers. "
    "explosion_fire_or_smoke: blasts, fire, grenades, gunsmoke. "
    "damage_or_hit_markers: hit markers, damage numbers, red screen edges, armor or health bar dropping. "
    "player_downed_or_dead: downed, revive prompt, death or mission-failed screen. "
    "fast_movement: sprinting, vaulting, driving, sliding, falling. "
    "screen: gameplay (player-controlled, HUD such as health, ammo or objective text visible), "
    "cutscene (cinematic camera, black letterbox bars, recorded video or no HUD), "
    "menu_or_map (inventory, map, settings, lobby), loading_or_black, "
    "webcam_only (a person or room fills the screen), other. "
    "Flags describe gameplay only and are all false for cutscenes, menus and webcam_only. "
    "event: at most 8 words naming what happens."
)

_CAPABILITIES: dict[tuple[str, str], tuple[float, bool]] = {}
_CAPABILITY_TTL_SECONDS = 300.0


class VisualModelError(RuntimeError):
    """The vision model could not answer; the pass degrades without failing an edit."""


def _endpoint(settings: Settings) -> str:
    return str(settings.ai.get("ollama_url") or "http://127.0.0.1:11434").rstrip("/")


def _settings_block(settings: Settings) -> dict[str, Any]:
    value = settings.raw.get("visual_moments") if isinstance(getattr(settings, "raw", None), dict) else None
    return value if isinstance(value, dict) else {}


def model_supports_vision(settings: Settings, model: str, timeout: float = 5.0) -> bool:
    """Ask the local engine whether a model accepts images. Never downloads."""
    model = str(model or "").strip()
    if not model:
        return False
    key = (_endpoint(settings), model)
    cached = _CAPABILITIES.get(key)
    if cached and time.monotonic() - cached[0] < _CAPABILITY_TTL_SECONDS:
        return cached[1]
    request = urllib.request.Request(
        key[0] + "/api/show",
        data=json.dumps({"model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_ollama(request, timeout=timeout) as response:
            body = read_ollama_json(response, 4 * 1024 * 1024)
        capabilities = body.get("capabilities") if isinstance(body, dict) else None
        capable = isinstance(capabilities, list) and "vision" in capabilities
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException):
        # Unknown is treated as "no": the pass is advisory and must not guess.
        capable = False
    _CAPABILITIES[key] = (time.monotonic(), capable)
    return capable


def accelerated_inference_available(settings: Settings) -> bool:
    """A GPU-class device that makes a few hundred image prompts take minutes."""
    if sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}:
        return True  # Ollama uses Metal on Apple Silicon.
    try:
        from .transcription import cuda_available
        return bool(cuda_available(settings))
    except Exception:
        return False


def normalized_visual_mode(value: Any) -> str:
    text = str(value or "auto").strip().lower()
    return text if text in VISUAL_AI_MODES else "auto"


def visual_budget(settings: Settings, performance_mode: str, *, accelerated: bool) -> int:
    configured = _settings_block(settings).get("budget")
    budgets = {**DEFAULT_BUDGETS, **(configured if isinstance(configured, dict) else {})}
    mode = performance_mode if performance_mode in budgets else "balanced"
    try:
        budget = int(budgets[mode])
    except (TypeError, ValueError):
        budget = DEFAULT_BUDGETS["balanced"]
    if not accelerated:
        # On CPU every image prompt is slow; an explicit "On" still gets a
        # bounded, useful pass instead of an hour-long one.
        budget = min(budget, int(budgets.get("lite", DEFAULT_BUDGETS["lite"])))
    return max(8, min(400, budget))


def resolve_visual_pass(
    settings: Settings,
    brief: dict[str, Any],
    *,
    cloud: bool,
    accelerated: bool,
    story_status: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Decide whether the gameplay vision pass runs, and with which model.

    ``auto`` runs only for streamer styles on a GPU-class device, where it is
    fast and relevant. ``on`` runs for any Short on any device. ``off`` never
    runs. Cloud connections never run it: frames are not uploaded.
    """
    mode = normalized_visual_mode(brief.get("visual_ai") or settings.ai.get("visual_ai"))
    plan: dict[str, Any] = {"mode": mode, "run": False, "model": None, "budget": 0, "reason": None,
                            "accelerated": bool(accelerated)}

    def skip(reason: str) -> dict[str, Any]:
        return {**plan, "reason": reason}

    if mode == "off":
        return skip("off")
    if str(brief.get("goal") or "short") != "short":
        return skip("not_short")
    if cloud:
        return skip("cloud_connection")
    if not settings.ai.get("enabled", True):
        return skip("ai_disabled")
    if mode == "auto" and get_edit_style(brief.get("edit_style")).get("category") != "streamer":
        return skip("not_gameplay_style")
    if mode == "auto" and not accelerated:
        return skip("no_accelerator")
    status = story_status()
    model = str(status.get("selected_model") or "") if status.get("ready") else ""
    if not model:
        return skip("story_ai_unavailable")
    if not model_supports_vision(settings, model):
        return skip("model_without_vision")
    performance_mode = str(brief.get("performance_mode") or settings.ai.get("performance_mode") or "auto")
    return {**plan, "run": True, "model": model,
            "budget": visual_budget(settings, performance_mode, accelerated=accelerated)}


def plan_windows(
    duration: float,
    budget: int,
    waveform: list[dict[str, Any]] | None = None,
    window_seconds: float = WINDOW_SECONDS,
) -> tuple[list[tuple[float, float]], float]:
    """Choose analysis windows and the timeline stride each window represents.

    Short recordings are tiled completely. Long ones get an even grid (most of
    the budget, so nothing is skipped by design) plus the loudest moments,
    where gameplay action usually is.
    """
    duration = max(0.0, float(duration))
    window = max(2.0, float(window_seconds))
    budget = max(1, int(budget))
    if duration <= 0:
        return [], window
    if duration <= window:
        return [(0.0, round(duration, 3))], max(window, duration)
    tiles = math.ceil(duration / window)
    if tiles <= budget:
        starts = [min(index * window, max(0.0, duration - window)) for index in range(tiles)]
        return [(round(start, 3), round(min(duration, start + window), 3)) for start in starts], window

    grid_count = max(1, int(round(budget * 0.75)))
    stride = duration / grid_count
    windows: list[tuple[float, float]] = []
    for index in range(grid_count):
        center = stride * (index + 0.5)
        start = max(0.0, min(duration - window, center - window / 2.0))
        windows.append((start, start + window))

    rows = [row for row in (waveform or []) if isinstance(row, dict)]

    def energy(row: dict[str, Any]) -> float:
        try:
            rms = float(row.get("rms_dbfs", -120.0))
            peak = float(row.get("peak_dbfs", -120.0))
        except (TypeError, ValueError):
            return -120.0
        return rms * 0.72 + peak * 0.28 if math.isfinite(rms) and math.isfinite(peak) else -120.0

    centers = sorted((start + end) / 2.0 for start, end in windows)
    extra = budget - grid_count
    for row in sorted(rows, key=energy, reverse=True):
        if extra <= 0:
            break
        try:
            center = (float(row["start"]) + float(row["end"])) / 2.0
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(center) or not 0.0 <= center <= duration:
            continue
        position = bisect.bisect_left(centers, center)
        neighbours = centers[max(0, position - 1):position + 1]
        if any(abs(center - other) < window for other in neighbours):
            continue
        start = max(0.0, min(duration - window, center - window / 2.0))
        windows.append((start, start + window))
        bisect.insort(centers, center)
        extra -= 1
    windows.sort()
    return [(round(start, 3), round(end, 3)) for start, end in windows], stride


def parse_answer(content: Any) -> dict[str, Any] | None:
    """Validate one model answer; anything unexpected is rejected, not guessed."""
    try:
        data = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    screen = str(data.get("screen") or "").strip().lower()
    if screen not in SCREENS:
        return None
    flags = [name for name in ACTION_FLAGS if data.get(name) is True] if screen == "gameplay" else []
    event = " ".join(str(data.get("event") or "").split())
    words = event.split(" ")
    if len(words) > 12:
        event = " ".join(words[:12])
    return {"screen": screen, "flags": flags, "event": event[:90]}


def score_answer(screen: str, flags: list[str]) -> float:
    weight = SCREEN_WEIGHTS.get(screen, SCREEN_WEIGHTS["other"])
    if weight <= 0:
        return 0.0
    raw = PLAIN_GAMEPLAY_SCORE + sum(ACTION_FLAGS.get(name, 0.0) for name in flags)
    return round(max(0.0, min(1.0, raw)) * weight, 3)


def _ask(settings: Settings, model: str, image_b64: str, timeout: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": ANSWER_SCHEMA,
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 160},
        "messages": [{"role": "user", "content": PROMPT, "images": [image_b64]}],
    }
    request = urllib.request.Request(
        _endpoint(settings) + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_ollama(request, timeout=timeout) as response:
            body = read_ollama_json(response)
    except urllib.error.HTTPError as exc:
        raise VisualModelError(f"The local model rejected the image request (HTTP {exc.code}).") from exc
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as exc:
        raise VisualModelError(f"The local model did not answer: {type(exc).__name__}.") from exc
    answer = parse_answer((body.get("message") or {}).get("content") if isinstance(body, dict) else None)
    if answer is None:
        raise VisualModelError("The local model returned an unusable visual answer.")
    return answer


def _contact_sheet(capture: Any, cv2: Any, numpy: Any, start: float, end: float) -> bytes | None:
    """Four evenly spaced frames, 2x2, small enough for a quick image prompt."""
    frames = []
    for index in range(FRAMES_PER_WINDOW):
        timestamp = start + (end - start) * (index + 0.5) / FRAMES_PER_WINDOW
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue
        height = max(1, int(round(frame.shape[0] * FRAME_WIDTH / max(1, frame.shape[1]))))
        frames.append(cv2.resize(frame, (FRAME_WIDTH, height), interpolation=cv2.INTER_AREA))
    if not frames:
        return None
    while len(frames) < FRAMES_PER_WINDOW:
        frames.append(frames[-1])
    if len({frame.shape for frame in frames}) != 1:
        frames = [cv2.resize(frame, (frames[0].shape[1], frames[0].shape[0])) for frame in frames]
    sheet = numpy.vstack([numpy.hstack(frames[0:2]), numpy.hstack(frames[2:4])])
    ok, encoded = cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return encoded.tobytes() if ok else None


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"version": VISUAL_MOMENTS_VERSION, "available": False, "reason": reason, "windows": [], **extra}


def analyze_visual_moments(
    path: Path,
    duration: float,
    settings: Settings,
    model: str,
    *,
    budget: int,
    waveform: list[dict[str, Any]] | None = None,
    progress: Callable[[float, str], None] | None = None,
    cancel_check: Callable[[], None] | None = None,
    time_limit: float | None = None,
    ask: Callable[[Settings, str, str, float], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Rate sampled windows of ``path``. Cancellation propagates; failures degrade."""
    if cancel_check:
        cancel_check()
    try:
        import cv2
        import numpy
    except ImportError:
        return _unavailable("opencv_not_installed")
    windows, stride = plan_windows(duration, budget, waveform)
    if not windows:
        return _unavailable("empty_source")
    if time_limit is None:
        try:
            time_limit = float(_settings_block(settings).get("max_seconds", DEFAULT_TIME_LIMIT_SECONDS))
        except (TypeError, ValueError):
            time_limit = DEFAULT_TIME_LIMIT_SECONDS
    ask = ask or _ask
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        capture.release()
        return _unavailable("video_open_failed")

    sheets: queue.Queue[tuple[int, bytes | None] | None] = queue.Queue(maxsize=4)
    stopped = threading.Event()

    def produce() -> None:
        # Decoding runs one window ahead of the model so the GPU is not idle
        # while OpenCV seeks. The capture is owned by this thread only.
        try:
            for index, (start, end) in enumerate(windows):
                if stopped.is_set():
                    return
                try:
                    image = _contact_sheet(capture, cv2, numpy, start, end)
                except Exception:
                    image = None
                while not stopped.is_set():
                    try:
                        sheets.put((index, image), timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            while not stopped.is_set():
                try:
                    sheets.put(None, timeout=0.1)
                    break
                except queue.Full:
                    continue

    producer = threading.Thread(target=produce, name="cutroom-visual-frames", daemon=True)
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    failures = 0
    consecutive_failures = 0
    unreadable = 0
    stop_reason: str | None = None
    first_call = True
    producer.start()
    try:
        while True:
            if cancel_check:
                cancel_check()
            try:
                item = sheets.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is None:
                break
            index, image = item
            if image is None:
                unreadable += 1
                continue
            if time.monotonic() - started > float(time_limit):
                stop_reason = "time_limit"
                break
            start, end = windows[index]
            try:
                # The first request may load the model into memory.
                answer = ask(settings, model, base64.b64encode(image).decode("ascii"), 240.0 if first_call else 120.0)
            except VisualModelError as exc:
                failures += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES or (first_call and "HTTP" in str(exc)):
                    stop_reason = "model_failed"
                    break
                continue
            finally:
                first_call = False
            consecutive_failures = 0
            results.append({
                "start": start,
                "end": end,
                "screen": answer["screen"],
                "flags": answer["flags"],
                "score": score_answer(answer["screen"], answer["flags"]),
                "event": answer["event"],
            })
            if progress:
                done = index + 1
                progress(done / len(windows), f"Watching the gameplay · {done}/{len(windows)} moments")
    finally:
        stopped.set()
        producer.join(timeout=5)
        capture.release()

    elapsed = round(time.monotonic() - started, 2)
    planned = len(windows)
    analyzed = len(results)
    if analyzed < max(3, math.ceil(planned * 0.25)):
        return _unavailable(stop_reason or "insufficient_results", model=model, planned_windows=planned,
                            analyzed_windows=analyzed, failed_windows=failures, elapsed_seconds=elapsed)
    return {
        "version": VISUAL_MOMENTS_VERSION,
        "available": True,
        "reason": None,
        "model": model,
        "window_seconds": WINDOW_SECONDS,
        "frames_per_window": FRAMES_PER_WINDOW,
        "frame_width": FRAME_WIDTH,
        "stride_seconds": round(stride, 3),
        "planned_windows": planned,
        "analyzed_windows": analyzed,
        "failed_windows": failures,
        "unreadable_windows": unreadable,
        "partial": bool(stop_reason) or analyzed < planned,
        "stop_reason": stop_reason,
        "elapsed_seconds": elapsed,
        "windows": results,
    }


def usable_windows(visual: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(visual, dict) or visual.get("available") is not True:
        return []
    output = []
    for row in visual.get("windows") or []:
        try:
            start, end, score = float(row["start"]), float(row["end"]), float(row["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if end > start and math.isfinite(score):
            output.append({**row, "start": start, "end": end, "score": max(0.0, min(1.0, score))})
    return sorted(output, key=lambda row: row["start"])


def _reach(visual: dict[str, Any], windows: list[dict[str, Any]]) -> float:
    """How far around its analyzed span a sampled window may speak for the timeline."""
    try:
        stride = float(visual.get("stride_seconds") or 0.0)
        window = float(visual.get("window_seconds") or WINDOW_SECONDS)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, (stride - window) / 2.0) if math.isfinite(stride) else 0.0


class VisualTimeline:
    """Fast lookups of visual evidence for arbitrary source ranges."""

    def __init__(self, visual: dict[str, Any] | None):
        self.windows = usable_windows(visual)
        self.reach = _reach(visual or {}, self.windows)
        self._starts = [row["start"] - self.reach for row in self.windows]

    def __bool__(self) -> bool:
        return bool(self.windows)

    def _overlapping(self, start: float, end: float) -> list[tuple[dict[str, Any], float]]:
        if not self.windows or end <= start:
            return []
        rows: list[tuple[dict[str, Any], float]] = []
        upper = bisect.bisect_right(self._starts, end)
        for row in self.windows[:upper]:
            left, right = row["start"] - self.reach, row["end"] + self.reach
            overlap = min(end, right) - max(start, left)
            if overlap > 0:
                rows.append((row, overlap))
        return rows

    def evidence(self, start: float, end: float) -> dict[str, Any] | None:
        """Action (0..1), share of dead screens and the strongest on-screen event."""
        rows = self._overlapping(float(start), float(end))
        if not rows:
            return None
        total = sum(overlap for _, overlap in rows)
        mean = sum(row["score"] * overlap for row, overlap in rows) / total
        strongest = max(rows, key=lambda pair: (pair[0]["score"], pair[1]))[0]
        dead = sum(overlap for row, overlap in rows if row.get("screen") in DEAD_SCREENS) / total
        screens: dict[str, float] = {}
        for row, overlap in rows:
            screens[str(row.get("screen") or "other")] = screens.get(str(row.get("screen") or "other"), 0.0) + overlap
        return {
            "action": round(strongest["score"] * 0.6 + mean * 0.4, 3),
            "dead": round(dead, 3),
            "screen": max(screens, key=screens.get),
            "event": str(strongest.get("event") or "") if strongest["score"] >= 0.3 else "",
        }

    def at(self, time_point: float) -> dict[str, Any] | None:
        return self.evidence(time_point - 0.5, time_point + 0.5)


def on_screen_note(evidence: dict[str, Any] | None) -> str | None:
    """A compact, honest description for the Story model; None adds nothing."""
    if not evidence:
        return None
    screen = str(evidence.get("screen") or "other")
    event = str(evidence.get("event") or "").strip()
    if float(evidence.get("dead", 0.0)) >= 0.6:
        return "menu, map or loading screen"
    if screen == "cutscene":
        return f"cutscene: {event}" if event else "cutscene"
    action = float(evidence.get("action", 0.0))
    if action >= 0.45 and event:
        return f"gameplay action {round(action * 10)}/10: {event}"
    return None


def summary(visual: dict[str, Any] | None, plan: dict[str, Any] | None = None) -> dict[str, Any]:
    """Small, UI-safe description of what the pass did (or why it did not run)."""
    windows = usable_windows(visual)
    plan = plan or {}
    return {
        "mode": plan.get("mode") or "auto",
        "used": bool(windows),
        "reason": None if windows else (plan.get("reason") or (visual or {}).get("reason")),
        "model": (visual or {}).get("model") or plan.get("model"),
        "analyzed_windows": len(windows),
        "action_windows": sum(1 for row in windows if row["score"] >= 0.5),
        "dead_windows": sum(1 for row in windows if row.get("screen") in DEAD_SCREENS),
        "partial": bool((visual or {}).get("partial")),
    }
