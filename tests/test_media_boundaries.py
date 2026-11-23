"""Approved local media I/O keeps trusted program and storage boundaries."""
from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cutroom import media
from cutroom.media_library import AssetUploadReservation, MediaLibraryError, safe_asset_path


class MediaBoundaryTests(unittest.TestCase):
    def test_native_program_remains_fixed_with_unicode_input_data(self):
        command = [sys.executable, "-c", "import sys; print(sys.argv[1])", "local קובץ.mp4"]
        for cancel_check in (None, lambda: None):
            with self.subTest(cooperative=cancel_check is not None):
                completed = media.run_command(command, timeout=6, cancel_check=cancel_check)
                self.assertEqual(completed.stdout.strip(), command[-1])
                self.assertEqual(completed.args, command)

    def test_missing_bare_program_never_launches(self):
        with patch.object(media.shutil, "which", return_value=None), patch.object(subprocess, "run") as launch:
            with self.assertRaises(FileNotFoundError):
                media.run_command(["unavailable-media-program", "-version"], timeout=1)
            launch.assert_not_called()

    def test_asset_root_returns_ordinary_legacy_and_nested_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            direct = root / "media" / "assets" / "music.wav"
            nested = direct.parent / "prepared-media" / "preview.mp4"
            nested.parent.mkdir(parents=True)
            self.assertEqual(safe_asset_path(root, "media/assets/music.wav"), direct)
            self.assertEqual(safe_asset_path(root, r"media\assets\prepared-media\preview.mp4"), nested)
            with self.assertRaises(FileNotFoundError):
                safe_asset_path(root, "media/alternate.wav")

    def test_nested_upload_replaces_atomically_and_leaves_unowned_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            dest = root / "selected" / "recording.mp4"
            dest.parent.mkdir()
            dest.write_bytes(b"old")
            token = "d" * 32
            unowned = dest.parent / ("." + token)
            unowned.write_bytes(b"existing staging")
            with patch.object(media.uuid, "uuid4", return_value=SimpleNamespace(hex=token)):
                with self.assertRaises(FileExistsError):
                    media.copy_upload(SimpleNamespace(stream=io.BytesIO(b"new")), dest, 3, root=root)
            self.assertEqual(unowned.read_bytes(), b"existing staging")
            self.assertEqual(dest.read_bytes(), b"old")
            self.assertEqual(media.copy_upload(SimpleNamespace(stream=io.BytesIO(b"new")), dest, 3, root=root), 3)
            self.assertEqual(dest.read_bytes(), b"new")
            self.assertEqual(set(dest.parent.iterdir()), {dest, unowned})

    def test_upload_validates_destination_before_creating_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            trusted = root / "approved"
            trusted.mkdir()
            unrelated = root / "unrelated" / "recording.mp4"
            with self.assertRaises(ValueError):
                media.copy_upload(SimpleNamespace(stream=io.BytesIO(b"new")), unrelated, 3, root=trusted)
            self.assertFalse(unrelated.parent.exists())


    def test_asset_reservation_rolls_back_only_its_owned_original(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            selected = AssetUploadReservation(project, "asset_" + "b" * 32, "Footage.MP4")
            original = selected.new_original_path()
            self.assertEqual(original.name, "original.mp4")
            original.write_bytes(b"reserved original")
            selected.record_original()
            foreign = original.parent / "unrelated.txt"
            foreign.write_bytes(b"existing local data")
            selected.discard()
            self.assertFalse(original.exists())
            self.assertEqual(foreign.read_bytes(), b"existing local data")
            with self.assertRaises(MediaLibraryError):
                AssetUploadReservation(project, "asset_" + "b" * 32, "Footage.MP4")
            self.assertEqual(foreign.read_bytes(), b"existing local data")

    def test_asset_reservation_does_not_clear_a_replaced_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory).resolve()
            selected = AssetUploadReservation(project, "asset_" + "c" * 32, "Footage.MP4")
            original = selected.new_original_path()
            original.write_bytes(b"reserved original")
            selected.record_original()
            previous_folder = original.parent.rename(original.parent.with_name("old-library-folder"))
            original.parent.mkdir()
            original.write_bytes(b"independently stored file")
            selected.discard()
            self.assertEqual(original.read_bytes(), b"independently stored file")
            self.assertEqual((previous_folder / original.name).read_bytes(), b"reserved original")
            with self.assertRaises(MediaLibraryError):
                selected.new_original_path()


if __name__ == "__main__":
    unittest.main()
