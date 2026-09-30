"""Install and exercise a verified release in a disposable macOS folder.

Run with --archive <combined.zip>. Nothing is installed into the checkout or a
user's existing CUTROOM folder. Homebrew prerequisites must already be present;
only the extracted application's private virtual environment is installed here.
The optional --transcribe downloads the small English Whisper model and uses
macOS speech synthesis; it never invokes a paid API or an Ollama model.
"""
from __future__ import annotations

import argparse
from array import array
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile


def run(command: list[str], *, env: dict[str, str], cwd: Path, timeout: int = 120) -> str:
    """Bound each subprocess, including its children, to the smoke run."""
    process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, start_new_session=os.name == "posix")
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        output, _ = process.communicate()
        raise RuntimeError(f"Timed out after {timeout}s: {command[0]}\n{output[-8000:]}") from None
    if process.returncode:
        raise RuntimeError(f"Command failed ({process.returncode}): {command[0]}\n{output[-8000:]}")
    return output


def extract_mac(archive: Path, destination: Path) -> Path:
    """Extract regular Mac files only, preserving executable modes from the ZIP."""
    with zipfile.ZipFile(archive) as bundle:
        entries = [entry for entry in bundle.infolist() if entry.filename.startswith("mac/")]
        if not entries:
            raise ValueError("The verified combined ZIP has no mac/ folder")
        names: set[str] = set()
        for entry in entries:
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            if (entry.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                    or entry.orig_filename != entry.filename
                    or "\\" in entry.filename or ":" in entry.filename
                    or ".." in path.parts or path.is_absolute()
                    or path.as_posix() != entry.filename
                    or any(ord(char) < 32 for char in entry.filename)
                    or entry.filename.casefold() in names):
                raise ValueError(f"Unsafe Mac archive entry: {entry.filename}")
            names.add(entry.filename.casefold())
        for entry in entries:
            target = destination.joinpath(*PurePosixPath(entry.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as handle:
                handle.write(bundle.read(entry))
            target.chmod(0o755 if entry.external_attr >> 16 & 0o111 else 0o644)
    app = destination / "mac" / "App"
    for name in ("server.py", "config.json", "setup_macos.sh", "run_macos.sh", "preflight_macos.py"):
        if not (app / name).is_file():
            raise ValueError(f"Mac package is missing {name}")
    if (app / ".venv").exists() or (app / "data").exists():
        raise ValueError("The Mac smoke requires a clean package without runtime or user data")
    return app


def isolated_environment(scratch: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("CUTROOM_", "OPENAI_", "ANTHROPIC_"))
           and key not in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    env.update(CUTROOM_DATA_DIR=str(scratch / "test data שלום"), CUTROOM_NO_BROWSER="1",
               PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1",
               HF_HOME=str(scratch / "model cache"), XDG_CACHE_HOME=str(scratch / "cache"),
               HF_HUB_DISABLE_TELEMETRY="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               HOMEBREW_NO_AUTO_UPDATE="1", HOMEBREW_NO_INSTALL_CLEANUP="1")
    return env


def install_and_check(archive: Path, *, transcribe: bool = False) -> dict:
    if sys.platform != "darwin":
        raise RuntimeError("This installation smoke must run on macOS; it is not a simulated Mac test")
    if not (3, 11) <= sys.version_info[:2] < (3, 13):
        raise RuntimeError("Run the installation smoke with native Python 3.11 or 3.12")
    # Import only the stdlib-based verifier from the checkout, never archive code.
    from build_universal_package import verify_package
    verify_package(archive)
    with tempfile.TemporaryDirectory(prefix="CUTROOM Mac smoke שלום ") as directory:
        scratch = Path(directory)
        app = extract_mac(archive, scratch)
        env = isolated_environment(scratch)
        env["CUTROOM_PYTHON"] = sys.executable
        # Fail before setup can offer to install missing machine-wide prerequisites.
        run([sys.executable, str(app / "preflight_macos.py"), "--system-only"],
            env=env, cwd=scratch, timeout=120)
        config = json.loads((app / "config.json").read_text(encoding="utf-8"))
        config.update(host="127.0.0.1", open_browser=False, data_dir=env["CUTROOM_DATA_DIR"])
        config["ai"].update(enabled=False, auto_start_ollama=False,
                            download_models_on_setup=False, ollama_url="http://127.0.0.1:1",
                            whisper_device="cpu", whisper_compute_type="int8")
        config["render"]["prefer_hardware"] = False
        # Only this new extraction is edited. Source and existing app config are never opened.
        (app / "config.json").write_text(json.dumps(config), encoding="utf-8")
        print("Installing the extracted Mac app into a fresh private virtual environment", flush=True)
        print(run(["/bin/bash", str(app / "setup_macos.sh"), "--yes"],
                  env=env, cwd=scratch, timeout=900), flush=True)
        print(run(["/bin/bash", str(app / "run_macos.sh"), "--check"],
                  env=env, cwd=scratch, timeout=180), flush=True)
        python = app / ".venv" / "bin" / "python"
        report = scratch / "worker-report.json"
        command = [str(python), str(Path(__file__).resolve()), "--worker-app", str(app),
                   "--report", str(report)]
        if transcribe:
            command.append("--transcribe")
        print(run(command, env=env, cwd=scratch, timeout=600 if transcribe else 240), flush=True)
        result = json.loads(report.read_text(encoding="utf-8"))
        result.update(package_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
                      fresh_install=True, unicode_and_spaces_path=True)
        return result


def request_json(base: str, path: str, payload: dict | None = None, *, method: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Origin": base})
    # A user's proxy settings must never route this local test off the machine.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=8) as response:
        return json.load(response)


def wait_for_own_server(process: subprocess.Popen, base: str, expected_instance: str) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Mac launcher exited before startup ({process.returncode})")
        try:
            identity = request_json(base, "/api/instance")
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
            continue
        if identity.get("service") != "cutroom" or identity.get("instance_id") != expected_instance:
            raise RuntimeError("Port was taken by another server; refusing to send it any project requests")
        return
    raise RuntimeError("The packaged Mac launcher did not become ready within 60 seconds")


def synthetic_project(settings, app: Path) -> tuple[str, object]:
    from cutroom.media import probe_media
    from cutroom.projects import ProjectStore
    store = ProjectStore(settings)
    project = store.create("Mac synthetic color and tone check")
    for slot, color, frequency in (("A", "red", 440), ("B", "blue", 880)):
        path = store.project_dir(project["id"]) / "media" / f"source-{slot}.mp4"
        run([settings.ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
             f"color=c={color}:s=320x180:r=30:d=3", "-f", "lavfi", "-i",
             f"sine=frequency={frequency}:sample_rate=48000:duration=3",
             "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-t", "3", str(path)], env=dict(os.environ), cwd=app, timeout=30)
        project["sources"][slot] = {"slot": slot, "name": path.name,
                                    "relative_path": f"media/{path.name}", **probe_media(path, settings)}
    project["settings"].update(aspect="9:16", resolution="720", fps=30, quality="fast",
                                captions=True, burn_captions=True, editorial_effects=False)
    project["manual"]["source_mixer"] = {"screen_slot": "A", "camera_slot": "B",
                                            "primary_role": "screen", "audio_slot": "B", "sync_offset": 0.0}
    project["analysis"] = {"sync": {"offset": 0}, "vision": {}, "audio_source": "B", "audio_timeline_offset": 0,
                           "transcript": {"language": "en", "segments": [
                               {"start": .2, "end": .8, "text": "First caption", "words": []},
                               {"start": 2.2, "end": 2.8, "text": "Later caption שלום", "words": []}]}}
    project["draft"] = {"keep_ranges": [{"start": 0, "end": 1}, {"start": 2, "end": 3}],
                        "cuts": [{"start": 1, "end": 2}], "output_duration": 2,
                        "camera_plan": [{"start": 0, "end": 1, "camera": "A"},
                                        {"start": 2, "end": 3, "camera": "B"}]}
    store.save(project)
    return project["id"], store


def check_export(settings, record: dict, expected_dimensions: tuple[int, int]) -> dict:
    from cutroom.media import probe_media
    output = settings.exports_dir / record["name"]
    metadata = probe_media(output, settings)
    assert (metadata["width"], metadata["height"]) == expected_dimensions, metadata
    assert 1.95 <= metadata["duration"] <= 2.1 and metadata["has_audio"], metadata
    assert record["captions_burned"], record
    captions = (settings.exports_dir / record["captions_name"]).read_text(encoding="utf-8")
    assert "First caption" in captions and "Later caption שלום" in captions, captions
    assert "00:00:01,200" in captions, captions  # Second caption follows the removed second.
    for position, channel in ((.4, 0), (1.4, 2)):
        frame = subprocess.check_output([settings.ffmpeg, "-v", "error", "-ss", str(position),
                                         "-i", str(output), "-an", "-frames:v", "1",
                                         "-vf", "scale=320:320", "-pix_fmt", "rgb24",
                                         "-f", "rawvideo", "pipe:1"], timeout=20)
        pixel = frame[(40 * 320 + 160) * 3:(40 * 320 + 160) * 3 + 3]
        assert pixel[channel] > 200 and sum(pixel) - pixel[channel] < 70, tuple(pixel)
        # White subtitle pixels on a solid red/blue background prove actual burning.
        assert sum(min(frame[index:index + 3]) > 160 for index in range(0, len(frame), 3)) > 5
    raw_audio = subprocess.check_output([settings.ffmpeg, "-v", "error", "-i", str(output),
                                         "-vn", "-ac", "1", "-ar", "48000", "-f", "f32le", "pipe:1"], timeout=20)
    samples = array("f", raw_audio)
    for position in (.3, 1.3):
        window = samples[int(position * 48000):int((position + .2) * 48000)]
        frequency = sum(left < 0 <= right for left, right in zip(window, window[1:])) / .2
        assert abs(frequency - 880) < 20, frequency  # B remains the chosen audio on both pictures.
    return {key: metadata[key] for key in ("width", "height", "duration", "has_audio")}


def render_via_http(base: str, project_id: str) -> dict:
    job = request_json(base, f"/api/projects/{project_id}/render", {"quality": "fast"})["job"]
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        job = request_json(base, f"/api/jobs/{job['id']}")["job"]
        if job["status"] == "completed":
            return job["result"]["export"]
        if job["status"] in {"failed", "cancelled", "interrupted"}:
            raise RuntimeError(f"Packaged Mac render did not complete: {job}")
        time.sleep(.2)
    raise RuntimeError(f"Render exceeded 90 seconds: {job}")


def real_cpu_transcription(settings, app: Path) -> dict:
    from cutroom.transcription import transcribe
    speech = settings.cache_dir / "synthetic English.aiff"
    run(["/usr/bin/say", "-v", "Samantha", "-r", "135", "-o", str(speech),
         "The quick brown fox jumps over the lazy dog. This is a local video editing test."],
        env=dict(os.environ), cwd=app, timeout=30)
    settings.ai.update(whisper_model="tiny.en", whisper_models={"lite": "tiny.en"},
                       whisper_device="cpu", whisper_compute_type="int8", whisper_isolate_process=False)
    transcript = transcribe(speech, settings, language="en", performance_mode="lite")
    text = " ".join(row.get("text", "") for row in transcript.get("segments", [])).strip()
    words = {word.strip(".,!?").lower() for word in text.split()}
    assert len(words & {"quick", "brown", "fox", "lazy", "dog", "video", "editing", "test"}) >= 3, text
    return {"status": "passed", "device": "cpu", "model": "tiny.en", "text": text,
            "scope": "synthetic English speech sanity check, not an accuracy benchmark"}


def worker(app: Path, *, transcribe: bool) -> dict:
    sys.path.insert(0, str(app))
    from cutroom.config import load_settings
    from server import _cutroom_instance_id
    # Ask the OS for an unused port; never use or stop an existing CUTROOM instance.
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    os.environ["CUTROOM_PORT"] = str(port)
    settings = load_settings(app / "config.json")
    assert settings.data_dir.resolve() != (app / "data").resolve()
    base = f"http://127.0.0.1:{port}"
    project_id, store = synthetic_project(settings, app)
    log = settings.data_dir / "launcher.log"
    with log.open("w", encoding="utf-8") as handle:
        process = subprocess.Popen(["/bin/bash", str(app.parent / "START CUTROOM.command")],
                                   cwd=app.parent.parent, env=dict(os.environ), stdin=subprocess.DEVNULL,
                                   stdout=handle, stderr=subprocess.STDOUT)
        try:
            wait_for_own_server(process, base, _cutroom_instance_id(settings))
            health = request_json(base, "/api/health")
            assert health["ok"] and health["ffmpeg"] and health["ffprobe"], health
            created = request_json(base, "/api/projects", {"name": "HTTP lifecycle test"})["project"]
            request_json(base, f"/api/projects/{created['id']}", method="DELETE")
            assert request_json(base, f"/api/projects/{project_id}")["project"]["id"] == project_id
            portrait = check_export(settings, render_via_http(base, project_id), (720, 1280))
            request_json(base, f"/api/projects/{project_id}", {"settings": {"aspect": "16:9"}}, method="PATCH")
            landscape = check_export(settings, render_via_http(base, project_id), (1280, 720))
            assert len(store.load(project_id)["exports"]) == 2
        except Exception:
            handle.flush()
            print(log.read_text(encoding="utf-8", errors="replace")[-10000:], file=sys.stderr)
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    transcription = real_cpu_transcription(settings, app) if transcribe else {
        "status": "not_run", "reason": "Use --transcribe to download tiny.en and test real CPU transcription"}
    return {"status": "passed", "platform": platform.platform(), "machine": platform.machine(),
            "python": platform.python_version(), "launcher_health_and_api": "passed",
            "portrait": portrait, "landscape": landscape, "source_audio_and_caption_checks": "passed",
            "transcription": transcription, "manual_finder_gatekeeper_test": "not_run",
            "ollama_and_cloud_ai": "not_run"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path, help="Verified combined release ZIP to extract and install")
    source.add_argument("--worker-app", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help="Optional JSON report, created without overwriting")
    parser.add_argument("--transcribe", action="store_true", help="Also download tiny.en and transcribe synthetic English speech")
    args = parser.parse_args()
    result = (worker(args.worker_app.resolve(), transcribe=args.transcribe) if args.worker_app
              else install_and_check(args.archive.resolve(), transcribe=args.transcribe))
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.report:
        with args.report.open("x", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
