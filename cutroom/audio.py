from __future__ import annotations

import math
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .config import Settings
from .utils import clamp, merge_ranges

AUDIO_PRESETS: dict[str, dict[str, Any]] = {
    "natural": {
        "silence_action": "shorten",
        "silence_min_seconds": 1.20,
        "silence_threshold_dbfs": None,
        "silence_keep_seconds": 0.48,
        "max_remove_ratio": 0.16,
        "quiet_action": "boost",
        "quiet_gain_db": 2.0,
        "loud_action": "lower",
        "loud_gain_db": -2.0,
        "normalize": False,
        "target_lufs": -16.0,
    },
    "clean": {
        "silence_action": "shorten",
        "silence_min_seconds": 0.75,
        "silence_threshold_dbfs": None,
        "silence_keep_seconds": 0.30,
        "max_remove_ratio": 0.28,
        "quiet_action": "boost",
        "quiet_gain_db": 3.0,
        "loud_action": "lower",
        "loud_gain_db": -3.0,
        "normalize": True,
        "target_lufs": -16.0,
    },
    "tight": {
        "silence_action": "shorten",
        "silence_min_seconds": 0.45,
        "silence_threshold_dbfs": None,
        "silence_keep_seconds": 0.16,
        "max_remove_ratio": 0.42,
        "quiet_action": "boost",
        "quiet_gain_db": 4.0,
        "loud_action": "lower",
        "loud_gain_db": -4.0,
        "normalize": True,
        "target_lufs": -15.0,
    },
}


def audio_policy(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(raw or {})
    preset_name = str(raw.get("preset") or "clean")
    base = dict(AUDIO_PRESETS.get(preset_name, AUDIO_PRESETS["clean"]))
    base["preset"] = preset_name if preset_name in AUDIO_PRESETS else "clean"
    for key in (
        "silence_action", "quiet_action", "loud_action", "normalize",
        "silence_min_seconds", "silence_threshold_dbfs", "silence_keep_seconds", "max_remove_ratio",
        "quiet_gain_db", "loud_gain_db", "target_lufs",
    ):
        if key in raw:
            base[key] = raw[key]
    base["silence_action"] = str(base.get("silence_action", "shorten")) if str(base.get("silence_action")) in {"keep", "shorten", "remove"} else "shorten"
    base["quiet_action"] = str(base.get("quiet_action", "boost")) if str(base.get("quiet_action")) in {"keep", "boost"} else "keep"
    base["loud_action"] = str(base.get("loud_action", "lower")) if str(base.get("loud_action")) in {"keep", "lower"} else "keep"
    base["silence_min_seconds"] = clamp(float(base.get("silence_min_seconds", 0.75)), 0.25, 8.0)
    raw_threshold = base.get("silence_threshold_dbfs")
    try:
        base["silence_threshold_dbfs"] = clamp(float(raw_threshold), -72.0, -18.0) if raw_threshold is not None else None
    except (TypeError, ValueError):
        base["silence_threshold_dbfs"] = None
    base["silence_keep_seconds"] = clamp(float(base.get("silence_keep_seconds", 0.30)), 0.08, 2.0)
    base["max_remove_ratio"] = clamp(float(base.get("max_remove_ratio", 0.28)), 0.02, 0.70)
    base["quiet_gain_db"] = clamp(float(base.get("quiet_gain_db", 3.0)), 0.0, 10.0)
    base["loud_gain_db"] = clamp(float(base.get("loud_gain_db", -3.0)), -10.0, 0.0)
    base["target_lufs"] = clamp(float(base.get("target_lufs", -16.0)), -24.0, -10.0)
    base["normalize"] = bool(base.get("normalize", False))
    return base


def _dbfs_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    normalized = samples.astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(normalized * normalized) + 1e-12))
    return max(-120.0, 20.0 * math.log10(max(rms, 1e-6)))


def _dbfs_peak(samples: np.ndarray) -> float:
    if samples.size == 0:
        return -120.0
    peak = float(np.max(np.abs(samples.astype(np.float32)))) / 32768.0
    return max(-120.0, 20.0 * math.log10(max(peak, 1e-6)))


def _ranges_from_flags(frames: list[dict[str, Any]], key: str, minimum: float, *, gap: float = 0.12) -> list[dict[str, float]]:
    ranges: list[dict[str, float]] = []
    current_start: float | None = None
    current_end = 0.0
    for frame in frames:
        active = bool(frame.get(key))
        start, end = float(frame["start"]), float(frame["end"])
        if active:
            if current_start is None:
                current_start = start
            elif start - current_end > gap:
                if current_end - current_start >= minimum:
                    ranges.append({"start": round(current_start, 3), "end": round(current_end, 3), "duration": round(current_end - current_start, 3)})
                current_start = start
            current_end = end
        elif current_start is not None:
            if current_end - current_start >= minimum:
                ranges.append({"start": round(current_start, 3), "end": round(current_end, 3), "duration": round(current_end - current_start, 3)})
            current_start = None
    if current_start is not None and current_end - current_start >= minimum:
        ranges.append({"start": round(current_start, 3), "end": round(current_end, 3), "duration": round(current_end - current_start, 3)})
    return ranges


def analyze_audio(
    source: Path,
    settings: Settings,
    duration: float,
    *,
    progress: Callable[[float, str], None] | None = None,
    transcript_segments: list[dict[str, Any]] | None = None,
    silence_threshold_dbfs: float | None = None,
    cancel_check: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Create a lightweight, deterministic loudness map from decoded mono PCM.

    This deliberately avoids a neural model. FFmpeg decodes to 8 kHz mono PCM and
    NumPy computes RMS/peak in 200 ms windows. Transcript ranges, when available,
    are used only to distinguish speech from general audio activity.
    """
    sample_rate = int(settings.raw.get("audio_analysis_sample_rate", 8000))
    window_seconds = float(settings.raw.get("audio_analysis_window_seconds", 0.20))
    window_samples = max(160, int(sample_rate * window_seconds))
    command = [
        settings.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1",
    ]
    if cancel_check:
        cancel_check()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None:
        if process.poll() is None:
            process.terminate()
        raise RuntimeError("Could not open decoded audio stream")
    stderr_lines: list[bytes] = []
    audio_chunks: queue.Queue[bytes | None] = queue.Queue(maxsize=6)
    reader_errors: list[BaseException] = []
    stop_readers = threading.Event()

    def queue_audio(value: bytes | None) -> None:
        while not stop_readers.is_set():
            try:
                audio_chunks.put(value, timeout=0.10)
                return
            except queue.Full:
                continue

    def read_stdout() -> None:
        try:
            while not stop_readers.is_set():
                raw = process.stdout.read(window_samples * 2)
                if not raw:
                    break
                queue_audio(raw)
        except BaseException as exc:
            reader_errors.append(exc)
        finally:
            queue_audio(None)

    def drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in iter(process.stderr.readline, b""):
            stderr_lines.append(line)
            # Decode failures can be extremely noisy. Keep only the useful tail
            # instead of allowing either the OS pipe or process memory to grow.
            if len(stderr_lines) > 240:
                del stderr_lines[:80]

    stderr_thread = threading.Thread(
        target=drain_stderr,
        name="cutroom-audio-stderr",
        daemon=True,
    )
    stdout_thread = threading.Thread(
        target=read_stdout,
        name="cutroom-audio-stdout",
        daemon=True,
    )
    stderr_thread.start()
    stdout_thread.start()
    frames: list[dict[str, Any]] = []
    index = 0
    integrated_energy = 0.0
    integrated_samples = 0
    absolute_peak = 0.0
    try:
        while True:
            if cancel_check:
                cancel_check()
            try:
                raw = audio_chunks.get(timeout=0.10)
            except queue.Empty:
                continue
            if raw is None:
                break
            samples = np.frombuffer(raw, dtype=np.int16)
            if samples.size == 0:
                break
            start = index * window_seconds
            actual_duration = samples.size / sample_rate
            end = min(duration, start + actual_duration) if duration > 0 else start + actual_duration
            normalized = samples.astype(np.float32) / 32768.0
            integrated_energy += float(np.sum(normalized * normalized))
            integrated_samples += int(samples.size)
            absolute_peak = max(absolute_peak, float(np.max(np.abs(normalized))))
            frames.append({
                "start": round(start, 3),
                "end": round(end, 3),
                "rms_dbfs": round(_dbfs_rms(samples), 2),
                "peak_dbfs": round(_dbfs_peak(samples), 2),
            })
            index += 1
            if cancel_check:
                cancel_check()
            if progress and index % 25 == 0 and duration > 0:
                progress(min(0.96, end / duration), "Measuring sound")
        while process.poll() is None:
            if cancel_check:
                cancel_check()
            try:
                process.wait(timeout=0.10)
            except subprocess.TimeoutExpired:
                continue
        return_code = int(process.returncode or 0)
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        if reader_errors:
            raise RuntimeError(f"Could not read decoded audio: {reader_errors[-1]}")
        stderr = b"".join(stderr_lines).decode("utf-8", errors="replace")
        if return_code != 0:
            raise RuntimeError(stderr[-2000:] or "FFmpeg audio analysis failed")
    finally:
        stop_readers.set()
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    pass
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)
        try:
            process.stdout.close()
        except OSError:
            pass
        if process.stderr is not None:
            try:
                process.stderr.close()
            except OSError:
                pass

    if not frames:
        return {
            "available": False,
            "duration": duration,
            "ranges": {"silence": [], "quiet_speech": [], "loud_speech": [], "clipping": []},
            "summary": {},
        }

    rms_values = np.array([float(item["rms_dbfs"]) for item in frames], dtype=np.float32)
    noise_floor = float(np.percentile(rms_values, 18))
    energetic = rms_values[rms_values > max(noise_floor + 6.0, -48.0)]
    activity_reference = float(np.median(energetic)) if energetic.size else float(np.percentile(rms_values, 75))
    activity_threshold = max(noise_floor + 7.0, activity_reference - 16.0, -52.0)

    transcript_segments = transcript_segments or []
    speech_rms: list[float] = []
    segment_index = 0
    for frame in frames:
        start, end = float(frame["start"]), float(frame["end"])
        while segment_index < len(transcript_segments) and float(transcript_segments[segment_index].get("end", 0)) <= start:
            segment_index += 1
        speech = False
        check_index = segment_index
        while check_index < len(transcript_segments) and float(transcript_segments[check_index].get("start", 0)) < end:
            segment = transcript_segments[check_index]
            if max(start, float(segment.get("start", 0))) < min(end, float(segment.get("end", 0))):
                speech = True
                break
            check_index += 1
        frame["speech"] = speech
        if speech:
            speech_rms.append(float(frame["rms_dbfs"]))

    speech_reference = float(np.median(speech_rms)) if speech_rms else activity_reference
    quiet_threshold = speech_reference - 9.0
    loud_threshold = min(-6.0, speech_reference + 5.0)
    recommended_silence_threshold = min(activity_threshold, speech_reference - 18.0)
    silence_threshold = (
        clamp(float(silence_threshold_dbfs), -72.0, -18.0)
        if silence_threshold_dbfs is not None
        else recommended_silence_threshold
    )

    for frame in frames:
        rms = float(frame["rms_dbfs"])
        peak = float(frame["peak_dbfs"])
        # A user-selected dB line identifies acoustic silence candidates, but
        # confirmed speech is protected once a transcript is available.
        frame["silence"] = rms < silence_threshold and not (bool(frame.get("speech")) and bool(transcript_segments))
        speech_like = bool(frame.get("speech")) if transcript_segments else rms >= activity_threshold
        frame["quiet_speech"] = speech_like and rms < quiet_threshold and not frame["silence"]
        frame["loud_speech"] = speech_like and rms > loud_threshold
        frame["clipping"] = peak >= -0.35

    integrated_rms = math.sqrt(integrated_energy / max(1, integrated_samples))
    integrated_dbfs = 20.0 * math.log10(max(integrated_rms, 1e-6))
    peak_dbfs = 20.0 * math.log10(max(absolute_peak, 1e-6))
    ranges = {
        "silence": _ranges_from_flags(frames, "silence", 0.30),
        "quiet_speech": _ranges_from_flags(frames, "quiet_speech", 0.40),
        "loud_speech": _ranges_from_flags(frames, "loud_speech", 0.30),
        "clipping": _ranges_from_flags(frames, "clipping", 0.10, gap=0.05),
    }
    # Keep a compact real waveform for the editor timeline. This replaces the
    # decorative synthetic waveform used by older builds without storing every
    # 200 ms analysis frame in project.json.
    max_bins = 900
    group_size = max(1, int(math.ceil(len(frames) / max_bins)))
    waveform: list[dict[str, Any]] = []
    for start_index in range(0, len(frames), group_size):
        group = frames[start_index:start_index + group_size]
        if not group:
            continue
        waveform.append({
            "start": group[0]["start"],
            "end": group[-1]["end"],
            "rms_dbfs": round(float(np.mean([float(item["rms_dbfs"]) for item in group])), 2),
            "peak_dbfs": round(float(max(float(item["peak_dbfs"]) for item in group)), 2),
            "speech": round(sum(1 for item in group if item.get("speech")) / len(group), 2),
        })
    if progress:
        progress(1.0, "Sound profile ready")
    return {
        "available": True,
        "duration": round(duration, 3),
        "sample_rate": sample_rate,
        "window_seconds": window_seconds,
        "summary": {
            "noise_floor_dbfs": round(noise_floor, 2),
            "speech_reference_dbfs": round(speech_reference, 2),
            "silence_threshold_dbfs": round(silence_threshold, 2),
            "recommended_silence_threshold_dbfs": round(recommended_silence_threshold, 2),
            "quiet_threshold_dbfs": round(quiet_threshold, 2),
            "loud_threshold_dbfs": round(loud_threshold, 2),
            "integrated_rms_dbfs": round(integrated_dbfs, 2),
            "peak_dbfs": round(peak_dbfs, 2),
        },
        "ranges": ranges,
        "waveform": waveform,
    }


def build_audio_actions(profile: dict[str, Any], policy_raw: dict[str, Any] | None, duration: float) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    policy = audio_policy(policy_raw)
    ranges = profile.get("ranges", {}) if profile else {}
    cuts: list[dict[str, Any]] = []
    gains: list[dict[str, Any]] = []
    counts = {"silence": 0, "quiet_audio": 0, "loud_audio": 0, "clipping": len(ranges.get("clipping", []))}

    if policy["silence_action"] != "keep":
        candidates: list[dict[str, Any]] = []
        for item in ranges.get("silence", []):
            start, end = float(item["start"]), float(item["end"])
            length = end - start
            if length < float(policy["silence_min_seconds"]):
                continue
            if policy["silence_action"] == "remove":
                pad = 0.06
            else:
                pad = min(length / 2.0, float(policy["silence_keep_seconds"]) / 2.0)
            cut_start, cut_end = start + pad, end - pad
            if cut_end - cut_start >= 0.10:
                candidates.append({
                    "start": round(cut_start, 3), "end": round(cut_end, 3),
                    "reason": "silence", "priority": 1.1 + min(0.6, length / 5.0),
                    "evidence": {
                        "source": "audio",
                        "measured": "silence",
                        "source_range_seconds": round(length, 2),
                        "threshold_dbfs": profile.get("summary", {}).get("silence_threshold_dbfs"),
                    },
                })
        budget = duration * float(policy["max_remove_ratio"])
        used = 0.0
        for item in sorted(candidates, key=lambda value: (value["priority"], value["end"] - value["start"]), reverse=True):
            length = item["end"] - item["start"]
            if used + length > budget and cuts:
                continue
            cuts.append(item)
            used += length
            counts["silence"] += 1

    if policy["quiet_action"] == "boost" and float(policy["quiet_gain_db"]) > 0:
        for item in ranges.get("quiet_speech", []):
            gains.append({"start": item["start"], "end": item["end"], "gain_db": round(float(policy["quiet_gain_db"]), 2), "reason": "quiet_speech"})
            counts["quiet_audio"] += 1
    if policy["loud_action"] == "lower" and float(policy["loud_gain_db"]) < 0:
        for item in ranges.get("loud_speech", []):
            gains.append({"start": item["start"], "end": item["end"], "gain_db": round(float(policy["loud_gain_db"]), 2), "reason": "loud_speech"})
            counts["loud_audio"] += 1

    return cuts, gains, counts


def protect_silence_ranges_from_speech(
    profile: dict[str, Any],
    transcript_segments: list[dict[str, Any]],
    *,
    padding: float = 0.08,
) -> dict[str, Any]:
    """Remove confirmed speech from acoustic silence candidates.

    The pre-Director dB graph intentionally shows every below-threshold region so
    the user can set a useful cut line. Once a transcript exists, however, CUTROOM
    treats detected words as evidence that must not be removed solely because the
    speaker was quiet. Silence ranges are split around speech with a small safety
    pad to preserve consonants and breaths at word boundaries.
    """
    if not transcript_segments or not profile.get("ranges"):
        return profile
    speech = merge_ranges([
        {
            "start": max(0.0, float(item.get("start", 0)) - padding),
            "end": max(0.0, float(item.get("end", 0)) + padding),
        }
        for item in transcript_segments
        if float(item.get("end", 0)) > float(item.get("start", 0))
    ], gap=0.04)
    output = dict(profile)
    ranges = {key: [dict(item) for item in value] for key, value in profile.get("ranges", {}).items()}
    protected: list[dict[str, float]] = []
    for quiet in ranges.get("silence", []):
        pieces = [{"start": float(quiet["start"]), "end": float(quiet["end"])}]
        for spoken in speech:
            next_pieces: list[dict[str, float]] = []
            for piece in pieces:
                start, end = piece["start"], piece["end"]
                cut_start, cut_end = float(spoken["start"]), float(spoken["end"])
                if cut_end <= start or cut_start >= end:
                    next_pieces.append(piece)
                    continue
                if cut_start - start >= 0.10:
                    next_pieces.append({"start": start, "end": min(end, cut_start)})
                if end - cut_end >= 0.10:
                    next_pieces.append({"start": max(start, cut_end), "end": end})
            pieces = next_pieces
            if not pieces:
                break
        for piece in pieces:
            length = piece["end"] - piece["start"]
            if length >= 0.10:
                protected.append({
                    "start": round(piece["start"], 3),
                    "end": round(piece["end"], 3),
                    "duration": round(length, 3),
                })
    ranges["silence"] = protected
    output["ranges"] = ranges
    return output


def constrain_gain_ranges_to_speech(profile: dict[str, Any], transcript_segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Keep quiet/loud gain ranges only where Whisper says speech exists.

    Silence detection stays purely acoustic. This makes gain automation conservative:
    music or background noise is not boosted just because it is quiet.
    """
    if not transcript_segments or not profile.get("ranges"):
        return profile
    output = dict(profile)
    ranges = {key: [dict(item) for item in value] for key, value in profile.get("ranges", {}).items()}

    def overlaps_speech(item: dict[str, Any]) -> bool:
        start, end = float(item.get("start", 0)), float(item.get("end", 0))
        return any(
            max(start, float(segment.get("start", 0))) < min(end, float(segment.get("end", 0)))
            for segment in transcript_segments
        )

    ranges["quiet_speech"] = [item for item in ranges.get("quiet_speech", []) if overlaps_speech(item)]
    ranges["loud_speech"] = [item for item in ranges.get("loud_speech", []) if overlaps_speech(item)]
    output["ranges"] = ranges
    return output
