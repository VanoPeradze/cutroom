"""Runner-only synthetic checks against an extracted Windows source package.

The archive is never modified. No media, project data, or model is uploaded.
This does not claim that the packaged launcher or clean-OS setup was exercised.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen


def run(args: list[str], *, timeout: int = 180) -> bytes:
    result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {result.stderr.decode('utf-8', 'replace')[-4000:]}")
    return result.stdout


def wait_for_json(url: str, process: subprocess.Popen, *, seconds: int = 40) -> dict:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"CUTROOM server exited before responding: {process.returncode}")
        try:
            with urlopen(url, timeout=2) as response:
                return json.load(response)
        except (OSError, URLError):
            time.sleep(0.4)
    raise RuntimeError("CUTROOM server did not respond on its isolated loopback port")


def exercise_server(app: Path, env: dict[str, str], project_id: str, export_name: str, expected_sha: str) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server_env = dict(env, CUTROOM_PORT=str(port))
    base = f"http://127.0.0.1:{port}"
    for attempt in range(2):
        proc = subprocess.Popen([sys.executable, "-B", str(app / "server.py")], cwd=app,
                                env=server_env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            payload = wait_for_json(base + "/api/projects/" + project_id, proc)
            project = payload["project"]
            assert project["settings"]["aspect"] == "9:16", "Saved aspect changed on restart"
            mixer = project["manual"]["source_mixer"]
            assert mixer["screen_slot"] == "A" and mixer["camera_slot"] == "B"
            assert mixer["primary_role"] == "screen" and mixer["first_slot"] == "B"
            with urlopen(base + "/api/exports/" + export_name, timeout=20) as response:
                assert hashlib.sha256(response.read()).hexdigest() == expected_sha, "Export download bytes changed"
        finally:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    app, archive = args.app.resolve(strict=True), args.archive.resolve(strict=True)
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    if not app.is_relative_to(runner_temp) or not archive.is_relative_to(runner_temp):
        raise RuntimeError("This test may only use the temporary runner package")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and FFprobe are required")

    sys.path.insert(0, str(app))
    from cutroom.config import load_settings
    from cutroom.jobs import Job, JobContext
    from cutroom.media import probe_media
    from cutroom.projects import ProjectStore
    from cutroom.render import render_project

    with tempfile.TemporaryDirectory(prefix="cutroom-synthetic-", dir=runner_temp) as name:
        work = Path(name).resolve(strict=True)
        if work == runner_temp or not work.is_relative_to(runner_temp):
            raise RuntimeError("Unsafe temporary test root")
        env = dict(os.environ, CUTROOM_DATA_DIR=str(work / "data"), CUTROOM_FFMPEG=ffmpeg,
                   CUTROOM_FFPROBE=ffprobe, CUTROOM_NO_BROWSER="1", HF_HUB_OFFLINE="1",
                   TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
        os.environ.update({key: env[key] for key in ("CUTROOM_DATA_DIR", "CUTROOM_FFMPEG", "CUTROOM_FFPROBE")})
        config_path = app / "config.json"
        original_config = config_path.read_bytes()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["ai"]["enabled"] = False
        config["ai"]["download_models_on_setup"] = False
        config["render"]["prefer_hardware"] = False
        config["open_browser"] = False
        config_path.write_text(json.dumps(config), encoding="utf-8")
        settings = load_settings()
        store = ProjectStore(settings)
        project = store.create("Synthetic Windows qualification")
        media_dir = store.project_dir(project["id"]) / "media"
        for slot, color, frequency in (("A", "red", 440), ("B", "blue", 660)):
            target = media_dir / f"source-{slot}.mp4"
            run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                 f"color={color}:s=320x180:r=30:d=3", "-f", "lavfi", "-i",
                 f"sine=frequency={frequency}:sample_rate=48000:duration=3", "-c:v", "libx264",
                 "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(target)])
            project["sources"][slot] = {"slot": slot, "name": f"{slot}.mp4",
                                         "relative_path": f"media/source-{slot}.mp4", **probe_media(target, settings)}
        project["settings"].update({"aspect": "9:16", "resolution": "720", "quality": "fast",
                                    "captions": False, "editorial_effects": False})
        project["manual"]["source_mixer"] = {"screen_slot": "A", "camera_slot": "B", "primary_role": "screen",
                                             "audio_slot": "B", "sync_offset": 0.0, "first_slot": "B", "stack_fit": "cover"}
        project["analysis"] = {"sync": {"offset": 0.0}, "vision": {"embedded_camera": None},
                               "transcript": {"segments": []}}
        project["draft"] = {"keep_ranges": [{"start": 0, "end": 3}], "cuts": [],
                            "camera_plan": [{"start": 0, "end": 3, "camera": "stacked"}]}
        store.save(project)
        context = JobContext(Job("windows-synthetic", "render", project["id"]), threading.Lock())
        result = render_project(context, project["id"], store, settings, {"quality": "fast"})
        output = settings.exports_dir / result["export"]["name"]
        metadata = probe_media(output, settings)
        if (metadata["width"], metadata["height"]) != (720, 1280) or not 2.7 <= metadata["duration"] <= 3.3:
            raise RuntimeError(f"Unexpected video dimensions or duration: {metadata}")
        streams = json.loads(run([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))["streams"]
        if not any(stream["codec_type"] == "audio" for stream in streams):
            raise RuntimeError("Export has no audio stream")
        run([ffmpeg, "-v", "error", "-i", str(output), "-f", "null", "-"])
        frame = run([ffmpeg, "-v", "error", "-ss", "0.5", "-i", str(output), "-an", "-frames:v", "1",
                     "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
        if len(frame) != 720 * 1280 * 3:
            raise RuntimeError("Could not decode the full portrait video frame")
        def pixel(y: int) -> tuple[int, ...]:
            offset = (y * 720 + 360) * 3
            return tuple(frame[offset:offset + 3])
        for y in (128, 320, 370):
            rgb = pixel(y)
            if not (rgb[2] > 180 and rgb[0] < 70 and rgb[1] < 70):
                raise RuntimeError(f"Expected blue camera in upper 30% at y={y}: {rgb}")
        for y in (400, 640, 1100):
            rgb = pixel(y)
            if not (rgb[0] > 180 and rgb[1] < 70 and rgb[2] < 70):
                raise RuntimeError(f"Expected red screen in lower 70% at y={y}: {rgb}")
        samples = array("f")
        samples.frombytes(run([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000",
                               "-f", "f32le", "pipe:1"]))
        window = samples[14400:24000]
        if len(window) != 9600:
            raise RuntimeError("Decoded audio is too short")
        rms = (sum(sample * sample for sample in window) / len(window)) ** 0.5
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / 0.2
        if rms < 0.01 or abs(frequency - 660) > 15:
            raise RuntimeError(f"Selected source B audio did not survive export: rms={rms}, hz={frequency}")
        output_sha = hashlib.sha256(output.read_bytes()).hexdigest()
        exercise_server(app, env, project["id"], output.name, output_sha)
        config_path.write_bytes(original_config)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != archive_sha:
            raise RuntimeError("Candidate archive changed")
        report = {"head_sha": os.environ["TESTED_HEAD_SHA"], "candidate_sha256": archive_sha,
                  "mode": "extracted Windows source-beta on hosted Windows runner",
                  "checks": {"portrait_width": 720, "portrait_height": 1280, "duration_seconds": metadata["duration"],
                             "two_source_stacked_30_70_pixels": "passed", "source_B_audio_rms": rms,
                             "source_B_audio_frequency_hz": frequency, "full_decode": "passed",
                             "saved_project_and_export_after_server_restart": "passed"},
                  "limits": ["Packaged native launcher and first-run setup were not run",
                             "No clean OS install, human listening, model, or physical-device test",
                             "AI disabled in extracted test configuration; archive unmodified"]}
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
