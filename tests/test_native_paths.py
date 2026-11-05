from __future__ import annotations

import os
from pathlib import Path

import pytest

from cutroom.native_paths import _extended_windows_path, native_io_path
from cutroom.utils import atomic_write_json


@pytest.mark.parametrize(("ordinary", "expected"), [
    (r"C:\work\media\clip.mp4", r"\\?\C:\work\media\clip.mp4"),
    ("D:/media folder/עברית/part/../clip.mp4", "\\\\?\\D:\\media folder\\עברית\\clip.mp4"),
    (r"\\server\share\folder\..\clip.mp4", r"\\?\UNC\server\share\clip.mp4"),
    (r"\\?\C:\work\.\clip.mp4", r"\\?\C:\work\clip.mp4"),
    (r"\\?\UNC\server\share\folder\..\clip.mp4", r"\\?\UNC\server\share\clip.mp4"),
])
def test_windows_filesystem_paths_are_normalized_and_idempotent(ordinary, expected):
    # Pure lexical cases also run on non-Windows test hosts; no UNC/network I/O.
    assert _extended_windows_path(ordinary) == expected
    assert _extended_windows_path(expected) == expected


@pytest.mark.parametrize("path", [
    "", "relative/clip.mp4", r"C:clip.mp4", r"\root-relative\clip.mp4",
    "C:\\media\\bad\0name.mp4", r"\\.\PhysicalDrive0", r"\\.\pipe\cutroom",
    r"\\?\GLOBALROOT\Device\HarddiskVolume1\clip.mp4", r"\\?\C:relative.mp4",
    r"\\server", r"\\?\UNC\server", r"\\server\..\clip.mp4",
])
def test_windows_paths_reject_relative_device_and_malformed_roots(path):
    with pytest.raises(ValueError):
        _extended_windows_path(path)


def test_native_conversion_does_not_create_or_resolve_missing_paths(tmp_path):
    missing = tmp_path / "missing" / "clip.mp4"
    converted = native_io_path(missing)
    assert not converted.exists()
    assert not (tmp_path / "missing").exists()
    if os.name == "nt":
        assert str(converted).startswith("\\\\?\\")
        assert native_io_path(converted) == converted
    else:
        assert converted == missing


def test_native_conversion_requires_absolute_path_and_rejects_nul():
    for value in ("relative.mp4", "", "bad\0path"):
        with pytest.raises(ValueError):
            native_io_path(value)


@pytest.mark.skipif(os.name != "nt", reason="Windows extended-length filesystem I/O")
def test_deep_filesystem_roundtrip_keeps_relative_metadata_and_original(tmp_path):
    # Only tiny text bytes. No media tools, links, global setting changes or
    # recursive cleanup operations are needed for this regression.
    root = native_io_path(tmp_path.resolve())
    project = root
    while len(str(project)) < 285:
        project /= "deep-local-fixture-0123456789"
    asset = project / "media" / "assets" / ("asset_" + "a" * 32)
    stage = asset / (".preparing-" + "b" * 32)
    stage.mkdir(parents=True)
    original = asset / "original.txt"
    original.write_bytes(b"unchanged original")
    preview = stage / "preview.txt"
    preview.write_bytes(b"tiny preview")
    manifest = stage / "manifest.json"
    atomic_write_json(manifest, {"state": "complete"})
    final = asset / ("prepared-" + "b" * 32)
    stage.replace(final)
    persisted = (final / "preview.txt").relative_to(project).as_posix()
    assert persisted == "media/assets/asset_" + "a" * 32 + "/prepared-" + "b" * 32 + "/preview.txt"
    assert not persisted.startswith(("/", "\\"))
    assert (project / Path(persisted)).read_bytes() == b"tiny preview"
    assert original.read_bytes() == b"unchanged original"
    # Exercise read/list/unlink/rmdir through the same path family used by the
    # preparation cache, preserving the original until all assertions pass.
    assert {path.name for path in final.iterdir()} == {"preview.txt", "manifest.json"}
    (final / "preview.txt").unlink()
    (final / "manifest.json").unlink()
    final.rmdir()
    original.unlink()
    cursor = asset
    while cursor != root:
        parent = cursor.parent
        cursor.rmdir()
        cursor = parent
