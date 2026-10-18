"""Native Windows stabilization regressions, separate from the portable gate."""
from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def windows_long_backend(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("Native Windows long-path publication regression")
    stabilization = importlib.import_module("cutroom.stabilization")
    # Preserve the failing geometry: parent203, UUID partial260, target218
    # UTF-16 units. A private generic path contains no creator data.
    padding = 203 - len(str(tmp_path.resolve()).encode("utf-16-le")) // 2 - 1
    assert 1 <= padding <= 255, "The regression needs a shorter pytest temporary root."
    folder = tmp_path / ("p" * padding)
    folder.mkdir()
    assert len(str(folder.resolve()).encode("utf-16-le")) // 2 == 203
    source, target = folder / "source.mp4", folder / "stabilized.mp4"
    source.write_bytes(b"original synthetic bytes")
    settings = SimpleNamespace(ffmpeg="ffmpeg", ffprobe="ffprobe", raw={"ffmpeg_threads": 2})
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
            partial = Path(args[-1])
            assert len(str(partial).encode("utf-16-le")) // 2 == 260
            # Simulate FFmpeg's successfully written long file, independently
            # of the production helper; link/unlink below remain native calls.
            Path("\\\\?\\" + str(partial)).write_bytes(b"complete stabilized video")
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(stabilization, "_run", run)
    try:
        yield stabilization, source, target, settings, calls
    finally:
        # Delete only this test's verified private directory, including a long
        # partial if an assertion exposes a cleanup regression.
        resolved = folder.resolve()
        assert resolved != tmp_path.resolve() and resolved.is_relative_to(tmp_path.resolve())
        shutil.rmtree("\\\\?\\" + str(resolved))


def test_windows_260_unit_partial_is_natively_linked_and_cleaned(windows_long_backend, monkeypatch):
    stabilization, source, target, settings, calls = windows_long_backend
    original = hashlib.sha256(source.read_bytes()).hexdigest()
    link = os.link
    published = []

    def observe(partial, destination):
        assert partial.startswith("\\\\?\\") and destination.startswith("\\\\?\\")
        assert len(partial[4:].encode("utf-16-le")) // 2 == 260
        assert len(destination[4:].encode("utf-16-le")) // 2 == 218
        link(partial, destination)
        assert os.path.samestat(os.stat(partial), os.stat(destination))
        published.append(destination)

    monkeypatch.setattr(stabilization.os, "link", observe)
    assert stabilization.stabilize_video(source, target, settings) == target.resolve()
    assert len(published) == 1 and target.read_bytes() == b"complete stabilized video"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original
    assert not list(target.parent.glob("*.partial.mp4"))
    assert all(not options["cwd"].exists() for _, options in calls if options.get("cwd"))


def test_windows_long_partial_target_race_uses_native_no_replace(windows_long_backend, monkeypatch):
    stabilization, source, target, settings, _ = windows_long_backend
    link = os.link

    def claim_then_link(partial, destination):
        target.write_bytes(b"another completed synthetic copy")
        link(partial, destination)

    monkeypatch.setattr(stabilization.os, "link", claim_then_link)
    with pytest.raises(stabilization.StabilizationError, match="existing"):
        stabilization.stabilize_video(source, target, settings)
    assert target.read_bytes() == b"another completed synthetic copy"
    assert source.read_bytes() == b"original synthetic bytes"
    assert not list(target.parent.glob("*.partial.mp4"))


def test_windows_long_partial_cancellation_after_publication_cleans_our_copy(windows_long_backend):
    stabilization, source, target, settings, _ = windows_long_backend
    from cutroom.jobs import JobCancelled

    def cancel(fraction, _message):
        if fraction == 1:
            assert target.read_bytes() == b"complete stabilized video"
            raise JobCancelled("Synthetic cancellation")

    with pytest.raises(JobCancelled):
        stabilization.stabilize_video(source, target, settings, cancel)
    assert not target.exists() and source.read_bytes() == b"original synthetic bytes"
    assert not list(target.parent.glob("*.partial.mp4"))


def test_windows_long_partial_cancellation_before_publication_cleans_partial(windows_long_backend, monkeypatch):
    stabilization, source, target, settings, _ = windows_long_backend
    from cutroom.jobs import JobCancelled
    run = stabilization._run

    def cancel(args, **kwargs):
        result = run(args, **kwargs)
        if "-vf" in args and "vidstabtransform" in args[args.index("-vf") + 1]:
            raise JobCancelled("Synthetic cancellation")
        return result

    monkeypatch.setattr(stabilization, "_run", cancel)
    with pytest.raises(JobCancelled):
        stabilization.stabilize_video(source, target, settings)
    assert not target.exists() and source.read_bytes() == b"original synthetic bytes"
    assert not list(target.parent.glob("*.partial.mp4"))

