"""Bounded public archive transport, including the larger showcase package."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_published_package as published


class PublishedPackageSizeTests(unittest.TestCase):
    def test_showcase_archive_keeps_exact_bytes_and_build_verification(self):
        content = b"A" * (10 * 1024 * 1024 + 1)
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            metadata = root / "release.json"
            release = {"layout": "windows-mac-folders-v1", "bytes": len(content),
                       "sha256": hashlib.sha256(content).hexdigest(),
                       "url": "https://example.invalid/package.zip", "build_id": "expected"}
            metadata.write_text(json.dumps(release), encoding="utf-8")
            response = io.BytesIO(content)
            response.url = release["url"]
            verified = []

            def verify(archive):
                verified.append(archive.read_bytes())
                return {"build_id": "expected"}

            with patch.object(published.urllib.request, "urlopen", return_value=response), \
                    patch.object(published, "verify_package", side_effect=verify):
                target = root / "download.zip"
                self.assertEqual(published.download(metadata, target), target)
                self.assertEqual(target.read_bytes(), content)
                self.assertEqual(verified, [content])

    def test_rejects_oversized_metadata_before_network_or_file_write(self):
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            metadata = root / "release.json"
            metadata.write_text(json.dumps({"layout": "windows-mac-folders-v1",
                "bytes": 16 * 1024 * 1024 + 1, "sha256": "a" * 64,
                "url": "https://example.invalid/package.zip", "build_id": "expected"}), encoding="utf-8")
            with patch.object(published.urllib.request, "urlopen") as fetch:
                with self.assertRaisesRegex(ValueError, "Invalid published release metadata"):
                    published.download(metadata, root / "download.zip")
                fetch.assert_not_called()
            self.assertFalse((root / "download.zip").exists())

    def test_larger_archives_still_reject_corruption_and_excess_response(self):
        content = b"A" * (10 * 1024 * 1024 + 1)
        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            metadata = root / "release.json"
            release = {"layout": "windows-mac-folders-v1", "bytes": len(content),
                       "sha256": hashlib.sha256(content).hexdigest(),
                       "url": "https://example.invalid/package.zip", "build_id": "expected"}
            metadata.write_text(json.dumps(release), encoding="utf-8")
            for body in (b"B" + content[1:], content + b"B"):
                with self.subTest(bytes=len(body)):
                    response = io.BytesIO(body)
                    response.url = release["url"]
                    with patch.object(published.urllib.request, "urlopen", return_value=response), \
                            patch.object(published, "verify_package") as verify:
                        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                            published.download(metadata, root / "download.zip")
                        verify.assert_not_called()
                    self.assertFalse((root / "download.zip").exists())


if __name__ == "__main__":
    unittest.main()
