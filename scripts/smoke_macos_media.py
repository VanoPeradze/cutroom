"""Real HTTP/manual-edit/media checks for the disposable packaged Mac smoke.

Only synthetic media and projects created by smoke_macos are used. This module
is test tooling, never shipped in the frozen Windows or published Mac app.
"""
from __future__ import annotations

from array import array
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request


def upload(base: str, path: str, source: Path) -> dict:
    from smoke_macos import request_json
    boundary = "CUTROOM-smoke-" + os.urandom(16).hex()
    header = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
              f'filename="{source.name}"\r\nContent-Type: application/octet-stream\r\n\r\n')
    data = header.encode("utf-8") + source.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(base + path, data=data, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}", "Origin": base,
    })
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=60) as response:
        result = json.load(response)
    job = result.get("job")
    deadline = time.monotonic() + 90
    while job and job["status"] != "completed":
        if job["status"] in {"failed", "cancelled", "interrupted"}:
            raise RuntimeError(f"Synthetic media preparation failed: {job}")
        if time.monotonic() >= deadline:
            raise RuntimeError("Synthetic media preparation exceeded 90 seconds")
        time.sleep(.2)
        job = request_json(base, f"/api/jobs/{job['id']}")["job"]
    return result


def frame(ffmpeg: str, output: Path, at: float, size: int = 160) -> bytes:
    data = subprocess.check_output([
        ffmpeg, "-v", "error", "-ss", str(at), "-i", str(output), "-an", "-frames:v", "1",
        "-vf", f"scale={size}:{size}", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ], timeout=30)
    assert len(data) == size * size * 3, len(data)
    return data


def pixel(data: bytes, x: int, y: int) -> tuple[int, ...]:
    offset = (y * 160 + x) * 3
    return tuple(data[offset:offset + 3])


def tone_level(samples: array, at: float, frequency: int) -> float:
    window = samples[round(at * 48000):round(at * 48000) + 4800]
    assert len(window) == 4800
    return 2 * abs(sum(sample * complex(math.cos(2 * math.pi * frequency * index / 48000),
                                        math.sin(2 * math.pi * frequency * index / 48000))
                       for index, sample in enumerate(window))) / len(window)


def assert_export(settings, record: dict, dimensions: tuple[int, int], fps: int):
    from cutroom.media import probe_media
    output = settings.exports_dir / record["name"]
    metadata = probe_media(output, settings)
    assert (metadata["width"], metadata["height"]) == dimensions, metadata
    assert abs(metadata["fps"] - fps) < .01, metadata
    assert abs(metadata["duration"] - 2) < .1 and metadata["has_audio"], metadata
    return output, {key: metadata[key] for key in ("width", "height", "fps", "duration", "has_audio")}


def extended_render_checks(settings, base: str, project_id: str, store) -> dict:
    from smoke_macos import request_json, render_via_http, run
    seed_media = store.project_dir(project_id) / "media"
    # MOV/10-bit HEVC is a common Mac input path, distinct from the H.264 MP4
    # baseline. This is synthetic SDR footage, not an HDR/iPhone accuracy test.
    mov = seed_media / "10-bit source.mov"
    run([settings.ffmpeg, "-v", "error", "-i", str(seed_media / "source-A.mp4"),
         "-c:v", "libx265", "-preset", "ultrafast", "-pix_fmt", "yuv420p10le",
         "-x265-params", "pools=1:frame-threads=1:log-level=error", "-tag:v", "hvc1",
         # Preserve the existing AAC duration so this codec smoke is independent
         # of the known sub-frame A/B duration-boundary regression.
         "-c:a", "copy", str(mov)], env=dict(os.environ), cwd=seed_media, timeout=60)
    project = request_json(base, "/api/projects", {
        "name": "Mac manual uploads שלום", "initial_settings": {
            "workflow": "manual", "goal": "short", "aspect": "9:16", "layout": "stacked",
            "resolution": "720", "fps": 60, "quality": "fast", "editorial_effects": False,
        },
    })["project"]
    path = f"/api/projects/{project['id']}"
    for slot in ("A", "B"):
        upload(base, f"{path}/sources/{slot}", mov if slot == "A" else seed_media / "source-B.mp4")
    project = request_json(base, path)["project"]
    assert all(project["sources"][slot] for slot in ("A", "B"))
    source_duration = project["sources"]["A"]["duration"]
    project = request_json(base, path + "/manual-draft", {"expected_revision": project["revision"]})["project"]
    assert project["draft"]["engine"] == "manual"

    def edit(action, **fields):
        current = request_json(base, path)["project"]
        try:
            return request_json(base, path + "/manual/edit", {
                "action": action, "expected_revision": current["revision"], **fields,
            })["project"]
        except urllib.error.HTTPError as error:
            raise AssertionError(f"Synthetic {action} failed: {error.read(4000).decode('utf-8')}") from error

    edit("split", time=1)
    edit("delete_range", start=1, end=2)
    edit("set_source_mixer", screen_slot="A", camera_slot="B", primary_role="screen",
         audio_slot="B", default_layout="stacked", stack_fit="cover")
    edit("set_camera_layout", layout="stacked", start=0, end=source_duration)
    stacked, stack_metadata = assert_export(settings, render_via_http(base, project["id"]), (720, 1280), 60)
    for at in (.4, 1.4):
        data = frame(settings.ffmpeg, stacked, at)
        top, bottom = pixel(data, 80, 24), pixel(data, 80, 110)
        assert top[2] > 200 and top[0] < 50, top  # Camera B above screen A.
        assert bottom[0] > 200 and bottom[2] < 50, bottom
        blue_rows = sum(pixel(data, 80, y)[2] > 180 for y in range(160))
        assert 36 <= blue_rows <= 56, blue_rows  # Camera occupies about 30%, not 50%.

    # Exercise actual file imports and preparation, not just project dictionaries.
    assets = settings.cache_dir / "extra media שלום"
    assets.mkdir()
    image = assets / "yellow still שלום.png"
    music = assets / "music 1000Hz.wav"
    run([settings.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "color=yellow:s=80x80",
         "-frames:v", "1", str(image)], env=dict(os.environ), cwd=assets, timeout=30)
    run([settings.ffmpeg, "-v", "error", "-f", "lavfi", "-i", "sine=frequency=1000:sample_rate=48000:duration=3",
         str(music)], env=dict(os.environ), cwd=assets, timeout=30)
    image_id = upload(base, path + "/assets", image)["asset_id"]
    music_id = upload(base, path + "/assets", music)["asset_id"]
    broll_id = upload(base, path + "/assets", seed_media / "source-B.mp4")["asset_id"]
    for asset_id in (image_id, music_id, broll_id):
        assert request_json(base, path)["project"]["assets"][asset_id]["status"] == "ready"
    edit("media_add", asset_id=image_id, start=.15, end=.85, x=.5, y=.05, w=.4, h=.4)
    edit("media_add", asset_id=broll_id, start=1.1, end=1.9, x=.5, y=.05, w=.4, h=.4, audio_enabled=False)
    edit("media_add", asset_id=music_id, start=0, end=2, role="music")
    edit("set_audio_mixer", source_muted=True, music_db=-6, ducking=False)
    edit("text_import", format="srt", replace=False,
         content="1\n00:00:00,200 --> 00:00:00,800\nImported שלום\n\n2\n00:00:01,200 --> 00:00:01,800\nSecond caption\n")
    edit("text_add", kind="title", start=.2, end=.8, text="Mac title", position="center")
    edit("set_camera_layout", layout="screen", start=0, end=source_duration)
    cases = []
    for resolution, dimensions, fps in (("1440", (2560, 1440), 60), ("2160", (3840, 2160), 30)):
        request_json(base, path, {"settings": {
            "aspect": "16:9", "resolution": resolution, "fps": fps, "captions": True, "burn_captions": True,
        }}, method="PATCH")
        record = render_via_http(base, project["id"])
        output, metadata = assert_export(settings, record, dimensions, fps)
        assert record["captions_burned"], record
        captions = (settings.exports_dir / record["captions_name"]).read_text(encoding="utf-8")
        assert "Imported שלום" in captions and "Second caption" in captions
        first, second = frame(settings.ffmpeg, output, .5), frame(settings.ffmpeg, output, 1.5)
        still, broll = pixel(first, 112, 32), pixel(second, 112, 32)
        assert still[0] > 190 and still[1] > 190 and still[2] < 60, still
        assert broll[2] > 190 and broll[0] < 60, broll
        text_frame = frame(settings.ffmpeg, output, .5, size=480)
        # Sample at a readable size: shrinking 4K text to 160 px destroys its
        # white interiors. Check title and subtitle bands independently.
        for start_row, end_row in ((200, 280), (384, 480)):
            assert sum(min(text_frame[i:i + 3]) > 170
                       for i in range(start_row * 480 * 3, end_row * 480 * 3, 3)) > 10
        samples = array("f", subprocess.check_output([
            settings.ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1", "-ar", "48000",
            "-f", "f32le", "pipe:1",
        ], timeout=30))
        music_level = tone_level(samples, .3, 1000)
        assert .035 < music_level < .085, music_level  # -6 dB gain on 0.125 amplitude input.
        assert tone_level(samples, .3, 880) < .008  # Original B speech is actually muted.
        cases.append(metadata)
    return {"http_source_uploads": "passed", "mov_10bit_hevc_input": "passed", "manual_split_and_remove": "passed",
            "stacked_camera_above_screen": stack_metadata, "exports": cases,
            "image_broll_music_imports": "passed", "mixer_gain_and_source_mute": "passed",
            "srt_import_and_title_burning": "passed"}
