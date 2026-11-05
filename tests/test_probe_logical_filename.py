"""Staged source probes use real headers and a logical name without moving bytes.

All ffprobe output is synthetic; these regressions launch no media process.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import media


MP4_FORMAT = "mov,mp4,m4a,3gp,3g2,mj2"
WEBM_FORMAT = "matroska,webm"


def ffprobe_payload(*, container=MP4_FORMAT, video_codec="h264", audio_codec="aac"):
    streams = [{
        "index": 0,
        "codec_type": "video",
        "codec_name": video_codec,
        "width": 1920,
        "height": 1080,
        "pix_fmt": "yuv420p",
        "avg_frame_rate": "30000/1001",
        "r_frame_rate": "30000/1001",
        "duration": "59.940000",
    }]
    if audio_codec is not None:
        streams.append({
            "index": 1,
            "codec_type": "audio",
            "codec_name": audio_codec,
            "sample_rate": "48000",
            "channels": 2,
            "duration": "59.940000",
        })
    return {
        "streams": streams,
        "format": {
            "filename": "/reported/path/which-is-never-the-file-to-open.mp4",
            "format_name": container,
            "duration": "59.940000",
            "size": "999999999",
        },
    }


@pytest.fixture
def mocked_probe(tmp_path, monkeypatch):
    """Provide one tiny staging file and capture the completely mocked probe."""
    staged = tmp_path / "upload-token.part"
    original = b"Synthetic staged bytes; no playable media is needed."
    staged.write_bytes(original)
    settings = SimpleNamespace(ffprobe="ffprobe-must-be-mocked")
    calls = []

    def install(payload):
        serialized = json.dumps(copy.deepcopy(payload))

        def fake_run(command, **kwargs):
            calls.append((list(command), dict(kwargs)))
            assert command[0] == settings.ffprobe
            assert command[-1] == str(staged)
            assert "-show_streams" in command and "-show_format" in command
            assert kwargs["timeout"] == 45
            return SimpleNamespace(stdout=serialized)

        monkeypatch.setattr(media, "run_command", fake_run)

    install(ffprobe_payload())
    return staged, settings, original, calls, install


def test_staged_h264_aac_mp4_uses_original_filename_for_browser_metadata(mocked_probe):
    staged, settings, original, calls, _ = mocked_probe

    result = media.probe_media(staged, settings, original_filename="episode.mp4")

    assert result["browser_ready"] is True
    assert result["mime"] == "video/mp4"
    assert result["format"] == MP4_FORMAT
    assert result["video_codec"] == "h264" and result["audio_codec"] == "aac"
    assert result["size"] == len(original)
    assert result["duration"] == 59.94
    assert (result["width"], result["height"], result["fps"]) == (1920, 1080, 29.97)
    assert len(calls) == 1
    assert staged.suffix == ".part" and staged.read_bytes() == original


@pytest.mark.parametrize(("video_codec", "audio_codec"), [("vp9", "opus"), ("vp8", "vorbis")])
def test_staged_webm_uses_logical_extension_with_compatible_actual_container(mocked_probe, video_codec, audio_codec):
    staged, settings, _, _, install = mocked_probe
    install(ffprobe_payload(container=WEBM_FORMAT, video_codec=video_codec, audio_codec=audio_codec))

    result = media.probe_media(staged, settings, original_filename="episode.webm")

    assert result["browser_ready"] is True
    assert result["mime"] == "video/webm"
    assert result["format"] == WEBM_FORMAT


def test_staged_matroska_keeps_its_non_browser_container_despite_supported_codecs(mocked_probe):
    staged, settings, _, _, install = mocked_probe
    install(ffprobe_payload(container=WEBM_FORMAT))

    result = media.probe_media(staged, settings, original_filename="episode.mkv")

    assert result["browser_ready"] is False
    assert result["format"] == WEBM_FORMAT


@pytest.mark.parametrize(("container", "logical_name"), [
    ("avi", "renamed.mp4"),
    (WEBM_FORMAT, "renamed.mp4"),
    (MP4_FORMAT, "renamed.webm"),
])
def test_logical_name_cannot_override_mismatched_actual_container(mocked_probe, container, logical_name):
    staged, settings, _, _, install = mocked_probe
    # Keep the stream codecs compatible with both existing codec allowlists so
    # rejection must come from the actual-container/name mismatch.
    install(ffprobe_payload(container=container, video_codec="vp9", audio_codec="opus"))

    result = media.probe_media(staged, settings, original_filename=logical_name)

    assert result["browser_ready"] is False
    assert result["format"] == container


@pytest.mark.parametrize(("video_codec", "audio_codec"), [
    ("hevc", "aac"),
    ("mpeg4", "aac"),
    ("h264", "ac3"),
    ("h264", "pcm_s16le"),
])
def test_logical_mp4_name_does_not_make_unsupported_stream_codecs_browser_ready(mocked_probe, video_codec, audio_codec):
    staged, settings, _, _, install = mocked_probe
    install(ffprobe_payload(video_codec=video_codec, audio_codec=audio_codec))

    result = media.probe_media(staged, settings, original_filename="episode.mp4")

    assert result["browser_ready"] is False
    assert result["video_codec"] == video_codec and result["audio_codec"] == audio_codec


@pytest.mark.parametrize(("suffix", "container", "expected_ready"), [
    (".mp4", MP4_FORMAT, True),
    (".mov", MP4_FORMAT, True),
    (".m4v", MP4_FORMAT, True),
    (".mkv", WEBM_FORMAT, False),
    (".part", MP4_FORMAT, False),
])
def test_two_argument_probe_preserves_existing_physical_filename_flow(tmp_path, monkeypatch, suffix, container, expected_ready):
    physical = tmp_path / f"existing-source{suffix}"
    physical.write_bytes(b"Unchanged physical source")
    settings = SimpleNamespace(ffprobe="ffprobe-must-be-mocked")

    def fake_run(command, **_kwargs):
        assert command[-1] == str(physical)
        return SimpleNamespace(stdout=json.dumps(ffprobe_payload(container=container)))

    monkeypatch.setattr(media, "run_command", fake_run)

    result = media.probe_media(physical, settings)

    assert result["browser_ready"] is expected_ready
    assert result["size"] == len(b"Unchanged physical source")
    if suffix == ".mp4":
        assert result["mime"] == "video/mp4"
    elif suffix == ".part":
        assert result["mime"] == "application/octet-stream"


def test_explicit_none_filename_keeps_staged_file_unclassified(mocked_probe):
    staged, settings, _, _, _ = mocked_probe

    result = media.probe_media(staged, settings, original_filename=None)

    assert result["browser_ready"] is False
    assert result["mime"] == "application/octet-stream"


def test_logical_filename_is_never_opened_statted_or_used_for_file_moves(mocked_probe, monkeypatch, tmp_path):
    staged, settings, original, calls, _ = mocked_probe
    # The hint deliberately names a nonexistent location. It may describe the
    # container but must never become a second media input or filesystem target.
    logical_name = str(tmp_path / "not-a-real-source-directory" / "episode.mp4")
    stat_before = staged.stat()
    real_stat = Path.stat
    physical_stats = []

    def guarded_stat(path, *args, **kwargs):
        assert path == staged, "Only the physical staged file may be statted"
        physical_stats.append(path)
        return real_stat(path, *args, **kwargs)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Probing a logical filename must not open or move files")

    with monkeypatch.context() as guarded_patch:
        guarded_patch.setattr(Path, "stat", guarded_stat)
        for name in ("open", "rename", "replace", "unlink"):
            guarded_patch.setattr(Path, name, forbidden)
        result = media.probe_media(staged, settings, original_filename=logical_name)

    assert result["browser_ready"] is True and result["mime"] == "video/mp4"
    assert result["size"] == len(original)  # The ffprobe payload reports a different size.
    assert physical_stats and all(path == staged for path in physical_stats)
    assert len(calls) == 1 and calls[0][0][-1] == str(staged)
    assert staged.read_bytes() == original
    assert staged.stat().st_mtime_ns == stat_before.st_mtime_ns
    assert not (tmp_path / "not-a-real-source-directory").exists()
