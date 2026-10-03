"""Opt-in stabilization must improve shake without replacing the original."""
from __future__ import annotations

import hashlib
import importlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


def _settings():
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    return SimpleNamespace(ffmpeg=ffmpeg, ffprobe=ffprobe, raw={"ffmpeg_threads": 2})


def _command(args):
    return subprocess.run(args, check=True, capture_output=True, timeout=30)


def _make_shaky_video(folder, settings, *, audio_codec="aac", duration=2):
    import numpy as np
    folder.mkdir(parents=True, exist_ok=True)
    pattern = folder / "pattern.ppm"
    # A stationary textured scene with known camera-only translation. No user
    # footage and no moving subjects can disguise stabilization quality here.
    random = np.random.default_rng(817)
    tiles = random.integers(20, 236, size=(70, 90, 3), dtype=np.uint8)
    pixels = np.repeat(np.repeat(tiles, 4, axis=0), 4, axis=1)
    pattern.write_bytes(b"P6\n360 280\n255\n" + pixels.tobytes())
    source = folder / ("shaky source.mkv" if audio_codec != "aac" else "shaky source.mp4")
    _command([
        settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-threads", "2",
        "-loop", "1", "-framerate", "30", "-i", str(pattern),
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(duration), "-vf", "crop=320:240:x='20+8*sin(n*1.7)':y='20+6*cos(n*1.3)',format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-threads", "2",
        "-c:a", audio_codec, str(source),
    ])
    return source


def _streams(path, settings):
    return json.loads(_command([
        settings.ffprobe, "-v", "error", "-count_frames", "-show_streams", "-show_format", "-of", "json", str(path),
    ]).stdout)


def _jitter(path, settings):
    import cv2
    import numpy as np
    raw = _command([
        settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
        "-map", "0:v:0", "-vf", "crop=240:160:40:40,format=gray", "-f", "rawvideo", "pipe:1",
    ]).stdout
    frames = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 160, 240).astype(np.float32)
    shifts = [cv2.phaseCorrelate(frames[index], frames[index + 1])[0] for index in range(len(frames) - 1)]
    return float(np.mean([x * x + y * y for x, y in shifts]) ** .5)


def _pcm(path, settings):
    return _command([
        settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(path),
        "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", "48000", "pipe:1",
    ]).stdout


@pytest.mark.parametrize("threads", [1, 2, 4])
def test_real_two_pass_reduces_jitter_preserves_frame_clock_and_copied_audio(tmp_path, monkeypatch, threads):
    stabilization = importlib.import_module("cutroom.stabilization")
    settings = _settings()
    if not stabilization.stabilization_capability(settings)["available"]:
        pytest.skip("FFmpeg lacks the optional libvidstab filters")
    settings.raw["ffmpeg_threads"] = threads
    run = stabilization._run
    motion_headers = []
    def record_motion_data(args, **kwargs):
        result = run(args, **kwargs)
        if "-vf" in args and "vidstabdetect" in args[args.index("-vf") + 1]:
            motion_headers.append((kwargs["cwd"] / "transforms.trf").read_bytes()[:10])
        return result
    monkeypatch.setattr(stabilization, "_run", record_motion_data)
    folder = tmp_path / "creator footage \u05d1\u05d3\u05d9\u05e7\u05d4"
    source = _make_shaky_video(folder, settings)
    target = folder / "stabilized copy \u05e2\u05d5\u05ea\u05e7.mp4"
    original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    messages = []
    assert stabilization.stabilize_video(source, target, settings, lambda _, message: messages.append(message)) == target.resolve()
    # Binary motion data gave nondeterministic corrections on Windows FFmpeg7.1.1.
    # Verify the actual inter-pass format, while retaining the same quality gate.
    assert motion_headers == [b"VID.STAB 1"]
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original_hash
    before, after = _streams(source, settings), _streams(target, settings)
    video_before = next(row for row in before["streams"] if row["codec_type"] == "video")
    video_after = next(row for row in after["streams"] if row["codec_type"] == "video")
    assert video_after["nb_read_frames"] == video_before["nb_read_frames"] == "60"
    assert video_after["avg_frame_rate"] == video_before["avg_frame_rate"]
    assert (video_after["width"], video_after["height"]) == (320, 240)
    assert abs(float(video_after["duration"]) - float(video_before["duration"])) < .001
    assert abs(float(after["format"]["duration"]) - float(before["format"]["duration"])) < .034
    assert _pcm(source, settings) == _pcm(target, settings)
    before_jitter, after_jitter = _jitter(source, settings), _jitter(target, settings)
    assert before_jitter > 4
    assert after_jitter < before_jitter * .5, (before_jitter, after_jitter)
    assert any("keeping audio unchanged" in message for message in messages)
    assert not list(folder.glob("*.partial.mp4"))


def test_real_incompatible_audio_is_explicitly_encoded_as_aac(tmp_path):
    stabilization = importlib.import_module("cutroom.stabilization")
    settings = _settings()
    if not stabilization.stabilization_capability(settings)["available"]:
        pytest.skip("FFmpeg lacks the optional libvidstab filters")
    source = _make_shaky_video(tmp_path, settings, audio_codec="pcm_s16le", duration=1)
    target = tmp_path / "aac copy.mp4"
    messages = []
    stabilization.stabilize_video(source, target, settings, lambda _, message: messages.append(message))
    streams = _streams(target, settings)["streams"]
    assert next(row for row in streams if row["codec_type"] == "audio")["codec_name"] == "aac"
    assert len(_pcm(target, settings)) / (48000 * 2) == pytest.approx(1, abs=.03)
    assert any("converting audio to AAC" in message for message in messages)


@pytest.fixture
def fake_backend(tmp_path, monkeypatch):
    stabilization = importlib.import_module("cutroom.stabilization")
    source = tmp_path / "original.mp4"
    source.write_bytes(b"original bytes")
    target = tmp_path / "copy.mp4"
    settings = SimpleNamespace(ffmpeg="ffmpeg", ffprobe="ffprobe", raw={"ffmpeg_threads": 200})
    metadata = {"duration": 2., "video_duration": 2., "fps": 30., "width": 320, "height": 240,
                "has_audio": True, "audio_codec": "aac"}
    monkeypatch.setattr(stabilization, "probe_media", lambda *_, **__: dict(metadata))
    calls = []
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if "-filters" in args:
            return subprocess.CompletedProcess(args, 0, " ... vidstabdetect V->V\n ... vidstabtransform V->V\n", "")
        if "vidstabdetect" in args[args.index("-vf") + 1]:
            (kwargs["cwd"] / "transforms.trf").write_text("motion")
        else:
            Path(args[-1]).write_bytes(b"complete stabilized video")
        return subprocess.CompletedProcess(args, 0, "", "")
    monkeypatch.setattr(stabilization, "_run", run)
    return stabilization, source, target, settings, calls


def test_cancelled_transform_does_not_commit_or_leave_partial_files(fake_backend, monkeypatch):
    stabilization, source, target, settings, calls = fake_backend
    from cutroom.jobs import JobCancelled
    original = stabilization._run
    def cancel(args, **kwargs):
        result = original(args, **kwargs)
        if "-vf" in args and "vidstabtransform" in args[args.index("-vf") + 1]:
            raise JobCancelled("Job cancelled")
        return result
    monkeypatch.setattr(stabilization, "_run", cancel)
    with pytest.raises(JobCancelled):
        stabilization.stabilize_video(source, target, settings)
    assert source.read_bytes() == b"original bytes" and not target.exists()
    assert not list(target.parent.glob("*.partial.mp4"))
    assert all(not call[1]["cwd"].exists() for call in calls if call[1].get("cwd"))


def test_missing_filters_fail_before_processing_and_keep_original(fake_backend, monkeypatch):
    stabilization, source, target, settings, _ = fake_backend
    monkeypatch.setattr(stabilization, "_run", lambda args, **_: subprocess.CompletedProcess(args, 0, " ... deshake V->V\n", ""))
    with pytest.raises(stabilization.StabilizationError, match="vidstab"):
        stabilization.stabilize_video(source, target, settings)
    assert source.read_bytes() == b"original bytes" and not target.exists()


def test_failed_pass_is_sanitized_and_leaves_no_output(fake_backend, monkeypatch):
    stabilization, source, target, settings, _ = fake_backend
    original = stabilization._run
    def fail(args, **kwargs):
        if "-vf" in args:
            raise subprocess.CalledProcessError(1, args, stderr="private creator file name")
        return original(args, **kwargs)
    monkeypatch.setattr(stabilization, "_run", fail)
    with pytest.raises(stabilization.StabilizationError) as error:
        stabilization.stabilize_video(source, target, settings)
    assert "private creator" not in str(error.value)
    assert not target.exists() and not list(target.parent.glob("*.partial.mp4"))
    assert source.read_bytes() == b"original bytes"


@pytest.mark.parametrize("options", [{"smoothing": True}, {"smoothing": -1}, {"smoothing": 61}, {"smoothing": 1.5}, {"shakiness": 0}, {"shakiness": 11}, {"shakiness": "5"}])
def test_invalid_parameters_fail_before_commands(fake_backend, options):
    stabilization, source, target, settings, calls = fake_backend
    with pytest.raises(stabilization.StabilizationError, match="integer"):
        stabilization.stabilize_video(source, target, settings, **options)
    assert not calls and not target.exists()


def test_output_never_overwrites_existing_file_or_original(fake_backend):
    stabilization, source, target, settings, calls = fake_backend
    target.write_bytes(b"previous good copy")
    with pytest.raises(stabilization.StabilizationError, match="existing"):
        stabilization.stabilize_video(source, target, settings)
    with pytest.raises(stabilization.StabilizationError, match="original"):
        stabilization.stabilize_video(source, source, settings)
    assert source.read_bytes() == b"original bytes" and target.read_bytes() == b"previous good copy"
    assert not calls


def test_copy_is_verified_then_published_with_bounded_cpu_and_local_protocols(fake_backend):
    stabilization, source, target, settings, calls = fake_backend
    stabilization.stabilize_video(source, target, settings)
    assert target.read_bytes() == b"complete stabilized video"
    for args, kwargs in calls[1:]:
        assert args[args.index("-threads") + 1] == "4"
        assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
        assert kwargs["timeout"] <= 4 * 3600 and kwargs["threads"] == 4
    assert calls[-1][0][calls[-1][0].index("-fps_mode") + 1] == "passthrough"


def test_cancellation_after_atomic_publication_removes_only_our_new_copy(fake_backend):
    stabilization, source, target, settings, _ = fake_backend
    from cutroom.jobs import JobCancelled
    def progress(fraction, _):
        if fraction == 1:
            assert target.read_bytes() == b"complete stabilized video"
            raise JobCancelled("Job cancelled")
    with pytest.raises(JobCancelled):
        stabilization.stabilize_video(source, target, settings, progress)
    assert not target.exists() and source.read_bytes() == b"original bytes"


def test_new_file_claimed_during_processing_is_never_overwritten(fake_backend, monkeypatch):
    stabilization, source, target, settings, _ = fake_backend
    link = stabilization.os.link
    def claim_then_link(partial, destination):
        target.write_bytes(b"another completed copy")
        link(partial, destination)
    monkeypatch.setattr(stabilization.os, "link", claim_then_link)
    with pytest.raises(stabilization.StabilizationError, match="existing"):
        stabilization.stabilize_video(source, target, settings)
    assert target.read_bytes() == b"another completed copy" and source.read_bytes() == b"original bytes"


def test_invalid_output_clock_is_rejected_before_publication(fake_backend, monkeypatch):
    stabilization, source, target, settings, _ = fake_backend
    probe = stabilization.probe_media
    def wrong_clock(path, *_args, **_kwargs):
        metadata = probe(path, settings)
        if path != source:
            metadata["video_duration"] = 5
        return metadata
    monkeypatch.setattr(stabilization, "probe_media", wrong_clock)
    with pytest.raises(stabilization.StabilizationError, match="clock"):
        stabilization.stabilize_video(source, target, settings)
    assert not target.exists() and not list(target.parent.glob("*.partial.mp4"))


def test_local_probe_restricts_protocols_and_obeys_cancellation(monkeypatch):
    stabilization = importlib.import_module("cutroom.stabilization")
    settings = SimpleNamespace(ffprobe="ffprobe")
    captured = []
    cancel = lambda: None
    def inspect(args, **options):
        captured.append((args, options))
        return subprocess.CompletedProcess(args, 0, json.dumps({"streams": [
            {"codec_type": "video", "duration": "1", "width": 320, "height": 240, "avg_frame_rate": "30/1"},
        ]}), "")
    monkeypatch.setattr(stabilization, "_run", inspect)
    assert stabilization.probe_media(Path("local.mp4"), settings, cancel_check=cancel)["duration"] == 1
    args, options = captured[0]
    assert args[args.index("-protocol_whitelist") + 1] == "file,pipe"
    assert options["cancel_check"] is cancel and options["timeout"] == 45


def test_actual_cancellable_child_is_terminated_and_both_pipes_closed(monkeypatch):
    stabilization = importlib.import_module("cutroom.stabilization")
    from cutroom.jobs import JobCancelled
    processes = []
    popen = stabilization.subprocess.Popen
    def record(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process
    monkeypatch.setattr(stabilization.subprocess, "Popen", record)
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise JobCancelled("Job cancelled")
    start = time.monotonic()
    with pytest.raises(JobCancelled):
        stabilization._run([sys.executable, "-c", "import time; print('ready', flush=True); time.sleep(30)"],
                           timeout=3, cancel_check=cancel)
    assert time.monotonic() - start < 3
    assert processes[0].poll() is not None
    assert processes[0].stdout.closed and processes[0].stderr.closed


def test_real_silent_source_produces_silent_copy(tmp_path):
    stabilization = importlib.import_module("cutroom.stabilization")
    settings = _settings()
    if not stabilization.stabilization_capability(settings)["available"]:
        pytest.skip("FFmpeg lacks the optional libvidstab filters")
    original = _make_shaky_video(tmp_path, settings, duration=1)
    silent = tmp_path / "silent.mp4"
    _command([settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(original),
              "-an", "-c:v", "copy", str(silent)])
    target = tmp_path / "silent stabilized.mp4"
    stabilization.stabilize_video(silent, target, settings)
    streams = _streams(target, settings)["streams"]
    assert all(row["codec_type"] != "audio" for row in streams)
    assert next(row for row in streams if row["codec_type"] == "video")["nb_read_frames"] == "30"


def test_real_variable_frame_timestamps_and_source_audio_offset_are_preserved(tmp_path):
    stabilization = importlib.import_module("cutroom.stabilization")
    settings = _settings()
    if not stabilization.stabilization_capability(settings)["available"]:
        pytest.skip("FFmpeg lacks the optional libvidstab filters")
    original = _make_shaky_video(tmp_path, settings, duration=1)
    source = tmp_path / "vfr offset source.mp4"
    _command([settings.ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-i", str(original),
              "-vf", "setpts=PTS+0.1/TB+0.04*floor(N/5)/TB", "-c:v", "libx264", "-threads", "2",
              "-fps_mode", "passthrough", "-enc_time_base:v", "filter", "-c:a", "copy", str(source)])
    target = tmp_path / "vfr offset stabilized.mp4"
    stabilization.stabilize_video(source, target, settings)
    def frame_times(path):
        payload = json.loads(_command([
            settings.ffprobe, "-v", "error", "-select_streams", "v:0", "-show_frames",
            "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path),
        ]).stdout)
        return [float(frame["best_effort_timestamp_time"]) for frame in payload["frames"]]
    before, after = frame_times(source), frame_times(target)
    assert len(before) == len(after) == 30
    assert before[0] == pytest.approx(.1, abs=.001)
    assert len({round(before[index + 1] - before[index], 4) for index in range(len(before) - 1)}) > 1
    assert after == pytest.approx(before, abs=.0001)
    assert _pcm(source, settings) == _pcm(target, settings)
