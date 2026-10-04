"""Render the real 8 ms A/B mismatch after adding local music, without AI."""
from array import array
import json
import math
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from cutroom.editing import apply_manual_edit
from cutroom.media import probe_media
from cutroom.media_render import library_input_args
from cutroom.render import _frame_aligned_plan, build_filter_graph
from cutroom.sequence import materialize_sequence
from test_source_duration_boundary import boundary_project, geometry


@pytest.mark.parametrize("fps", [30, 60])
def test_real_eight_ms_secondary_eof_music_export_keeps_frames_audio_and_source_end(tmp_path, fps):
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg runtime is not installed")
    paths, sources = [], {}
    # 125 fps expresses 3.008 exactly, and PCM avoids codec padding so the
    # independently probed container/video/audio clocks carry the real mismatch.
    for slot, color, duration, frequency in (("A", "red", 3.008, 440), ("B", "blue", 3, 660)):
        path = tmp_path / f"{slot}.mov"
        subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                        f"color={color}:s=160x100:r=125:d={duration}", "-f", "lavfi", "-i",
                        f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
                        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "pcm_s16le", "-t", str(duration), str(path)],
                       check=True, capture_output=True, timeout=20)
        paths.append(path)
        sources[slot] = probe_media(path, SimpleNamespace(ffprobe=ffprobe))
        assert sources[slot]["duration"] == duration
        assert sources[slot]["video_duration"] == duration
        assert sources[slot]["audio_duration"] == duration
    music = tmp_path / "music.wav"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=880:sample_rate=48000:duration=1", str(music)],
                   check=True, capture_output=True, timeout=10)
    value = boundary_project(fps=fps)
    value["sources"] = sources
    value["settings"]["editorial_effects"] = False
    value["manual"]["source_mixer"].update(first_slot="B", audio_slot="A", stack_fit="cover")
    value["draft"]["camera_plan"] = [{"start": 0, "end": 3.008, "camera": "stacked"}]
    asset_id = "asset_" + "c" * 32
    value["assets"] = {asset_id: {"id": asset_id, "kind": "audio", "duration": 1, "status": "ready", "path": "music.wav"}}
    apply_manual_edit(value, {"action": "media_add", "asset_id": asset_id, "start": 0})
    value, duration = materialize_sequence(value)
    assert duration == 2.008
    assert geometry(value, "A") == [(0, 1, 0), (1, 2.008, 2)]
    assert geometry(value, "B") == [(0, 1, 0), (1, 2, 2)]
    plan = _frame_aligned_plan(value)
    assert plan == [{"start": 0, "end": 2, "camera": "stacked", "_start_frame": 0, "_end_frame": 2 * fps}]
    graph, maps, has_audio = build_filter_graph(value, 160, 100)
    assert has_audio
    script, output = tmp_path / "graph.txt", tmp_path / "boundary.mp4"
    script.write_text(graph, encoding="utf-8")
    result = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(paths[0]), "-i", str(paths[1]),
                             *library_input_args(value, tmp_path), "-filter_complex_script", str(script), *maps,
                             "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-r", str(fps), str(output)],
                            capture_output=True, timeout=25)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    metadata = json.loads(subprocess.check_output([ffprobe, "-v", "error", "-show_streams", "-of", "json", str(output)]))
    video = next(row for row in metadata["streams"] if row["codec_type"] == "video")
    audio = next(row for row in metadata["streams"] if row["codec_type"] == "audio")
    assert video["avg_frame_rate"] == f"{fps}/1"
    assert int(video["nb_frames"]) == 2 * fps
    assert float(video["duration"]) == 2
    assert float(audio["duration"]) == pytest.approx(2, abs=1 / 48000)
    pixels = subprocess.check_output([ffmpeg, "-v", "error", "-sseof", str(-1 / fps), "-i", str(output),
                                      "-frames:v", "1", "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1"])
    for y, channel in ((10, 2), (70, 0)):
        offset = (y * 160 + 80) * 3
        assert pixels[offset + channel] > 200  # Last frame contains both real sources, never a black tail.
    samples = array("f", subprocess.check_output([ffmpeg, "-v", "error", "-i", str(output), "-vn", "-ac", "1",
                                                  "-ar", "48000", "-f", "f32le", "pipe:1"]))
    def tone_level(at, frequency):
        window = samples[round(at * 48000):round((at + 0.1) * 48000)]
        return 2 * abs(sum(sample * complex(math.cos(2 * math.pi * frequency * index / 48000),
                                            math.sin(2 * math.pi * frequency * index / 48000))
                           for index, sample in enumerate(window))) / len(window)
    assert tone_level(0.4, 440) > 0.05 and tone_level(0.4, 880) > 0.05
    assert tone_level(1.4, 440) > 0.05 and tone_level(1.4, 880) < 0.005
    assert tone_level(0.4, 660) < 0.005  # Selected A audio never switches to source B.
