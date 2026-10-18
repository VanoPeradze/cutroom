"""Synthetic, offline metadata checks; no artifacts, models or app code run."""
from __future__ import annotations

import argparse
import copy
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Missing review transport module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewAssetMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.transport = load_module("cutroom_review_asset_metadata_test", ROOT / "packaging/review_asset_metadata.py")
        cls.native = cls.transport._adapter()
        cls.verifier = cls.native._load_verifier()

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory(prefix="cutroom-review-metadata-tests-")
        self.addCleanup(self.cleanup_temp)
        self.repo = Path(self.directory.name)
        self.record_path = self.repo / "packaging/review-candidates/1111111.json"
        self.record_path.parent.mkdir(parents=True)
        self.metadata_path = self.repo / "draft-release.json"
        self.record = {
            "schema_version": 1, "kind": "cutroom-private-review-candidate",
            "published": False, "qualified_for_release": False, "native_candidate_status": "pending",
            "source": {"commit": "1" * 40, "tree": "2" * 40, "archive_sha256": "3" * 64,
                       "archive_bytes": 300, "files": 3},
            "windows": {"bytes": 100, "sha256": "4" * 64, "manifest_sha256": "5" * 64,
                        "build_id": "CUTROOM-1.2-beta-20261018-035807"},
            "combined": {"bytes": 200, "sha256": "6" * 64, "manifest_sha256": "7" * 64,
                         "build_id": "CUTROOM-1.2-beta-mac-20261018-035808"},
        }
        self.record_path.write_text(json.dumps(self.record), encoding="utf-8")
        self.metadata = {
            "id": 123, "url": self.transport.API_ROOT + "/releases/123", "draft": True,
            "published_at": None, "tag_name": "cutroom-review-1111111", "target_commitish": "1" * 40,
            "assets": [
                {"id": 200 + i, "name": name, "size": pin["bytes"], "state": "uploaded",
                 "url": self.transport.API_ROOT + f"/releases/assets/{200 + i}",
                 "digest": "sha256:" + pin["sha256"]}
                for i, (name, pin) in enumerate(self.transport.expected_assets(self.record).items())
            ],
        }
        self.write_metadata()

    def cleanup_temp(self) -> None:
        target = Path(self.directory.name).resolve()
        if target.parent != Path(tempfile.gettempdir()).resolve() or not target.name.startswith("cutroom-review-metadata-tests-"):
            raise RuntimeError("Refusing cleanup outside the synthetic metadata test directory")
        self.directory.cleanup()

    def write_metadata(self) -> None:
        self.metadata_path.write_text(json.dumps(self.metadata), encoding="utf-8")

    def trusted_adapter(self):
        return SimpleNamespace(_load_verifier=lambda: self.verifier,
                               _committed_record=Mock(return_value=(self.record, {"head": "8" * 40})))

    def validate(self, metadata=None, *, release_id=123, repository="VanoPeradze/cutroom"):
        return self.transport.validate_metadata(self.metadata if metadata is None else metadata,
                                                self.record, release_id, repository)

    def select(self):
        return self.transport.select_assets(self.metadata_path, self.record_path, 123, self.repo)

    def test_valid_metadata_selects_only_safe_ids_and_pinned_names(self) -> None:
        self.metadata["assets"].reverse()
        self.metadata["assets"][0]["browser_download_url"] = "https://untrusted.example/unused"
        self.assertEqual(self.validate(), ((200, "CUTROOM-1.2-Beta-Windows-review-1111111.zip"),
                                          (201, "CUTROOM-1.2-Beta-combined-review-1111111.zip"),
                                          (202, "SOURCE-1111111.zip")))

    def test_absent_api_digest_still_requires_size_and_later_byte_gate(self) -> None:
        for asset in self.metadata["assets"]:
            del asset["digest"]
        self.assertEqual(len(self.validate()), 3)

    def test_published_or_wrong_release_identity_is_rejected(self) -> None:
        mutations = {"draft": (False, 1, "true"), "published_at": ("2026-10-18T00:00:00Z", False),
                     "id": (124, True, "123"), "tag_name": ("v1.2-beta", "cutroom-review-2222222"),
                     "target_commitish": ("main", "1" * 7, "2" * 40),
                     "url": ("https://api.github.com/repos/other/repo/releases/123",
                             "http://api.github.com/repos/VanoPeradze/cutroom/releases/123",
                             self.metadata["url"] + "?redirect=evil")}
        for field, values in mutations.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    bad = copy.deepcopy(self.metadata)
                    bad[field] = value
                    with self.assertRaises(ValueError):
                        self.validate(bad)
        del self.metadata["published_at"]
        with self.assertRaises(ValueError):
            self.validate()

    def test_invalid_requested_release_ids_and_repository_are_rejected(self) -> None:
        for value in (True, 0, -1, "123", 1 << 63):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(release_id=value)
        with self.assertRaises(ValueError):
            self.validate(repository="other/cutroom")

    def test_asset_inventory_is_exact(self) -> None:
        for assets in (None, {}, [], self.metadata["assets"][:2], self.metadata["assets"] * 2):
            with self.subTest(assets=assets), self.assertRaises(ValueError):
                self.validate({**self.metadata, "assets": assets})
        bad = copy.deepcopy(self.metadata)
        bad["assets"][2] = copy.deepcopy(bad["assets"][0])
        with self.assertRaises(ValueError):
            self.validate(bad)

    def test_unsafe_or_unexpected_asset_names_are_rejected(self) -> None:
        for name in ("../SOURCE-1111111.zip", "SOURCE-1111111.zip\n123\tnew.zip",
                     "/SOURCE-1111111.zip", "SOURCE-1111111.ZIP", "SOURCE-1111111.zip/", True):
            with self.subTest(name=name):
                bad = copy.deepcopy(self.metadata)
                bad["assets"][0]["name"] = name
                with self.assertRaises(ValueError):
                    self.validate(bad)

    def test_bad_asset_identity_size_digest_and_upload_state_are_rejected(self) -> None:
        mutations = {"id": (True, 0, -1, "200", 201, 1 << 63), "size": (True, 0, 101, "100"),
                     "state": ("new", "open", True),
                     "digest": (None, "", "sha256:" + "8" * 64, "sha512:" + "4" * 64,
                                "sha256:" + "A" * 64, "sha256:" + "4" * 63),
                     "url": ("https://evil.example/asset", self.transport.API_ROOT + "/releases/assets/201")}
        for field, values in mutations.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    bad = copy.deepcopy(self.metadata)
                    bad["assets"][0][field] = value
                    with self.assertRaises(ValueError):
                        self.validate(bad)

    def test_record_schema_is_checked_after_git_binding(self) -> None:
        self.record["windows"]["sha256"] = "malformed"
        with patch.object(self.transport, "_adapter", return_value=self.trusted_adapter()):
            with self.assertRaises(ValueError):
                self.select()

    def test_untrusted_or_dirty_record_stops_metadata_processing(self) -> None:
        adapter = self.trusted_adapter()
        adapter._committed_record.side_effect = ValueError("Review record has uncommitted changes")
        with patch.object(self.transport, "_adapter", return_value=adapter):
            with patch.object(self.transport, "validate_metadata") as validate:
                with self.assertRaisesRegex(ValueError, "uncommitted"):
                    self.select()
                validate.assert_not_called()

    def test_record_is_rechecked_and_changed_provenance_rejected(self) -> None:
        adapter = self.trusted_adapter()
        adapter._committed_record.side_effect = [(self.record, {"head": "8" * 40}),
                                                (self.record, {"head": "9" * 40})]
        with patch.object(self.transport, "_adapter", return_value=adapter):
            with self.assertRaisesRegex(ValueError, "record changed"):
                self.select()

    def test_duplicate_json_keys_are_rejected(self) -> None:
        self.metadata_path.write_text('{"id":123,"id":123}', encoding="utf-8")
        with patch.object(self.transport, "_adapter", return_value=self.trusted_adapter()):
            with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
                self.select()

    def test_metadata_only_path_performs_no_writes(self) -> None:
        before = {path.relative_to(self.repo): path.read_bytes() for path in self.repo.rglob("*") if path.is_file()}
        adapter = self.trusted_adapter()
        with patch.object(self.transport, "_adapter", return_value=adapter):
            self.assertEqual(len(self.select()), 3)
        self.assertEqual(adapter._committed_record.call_count, 2)
        self.assertEqual(before, {path.relative_to(self.repo): path.read_bytes()
                                  for path in self.repo.rglob("*") if path.is_file()})

    def test_cli_prints_only_tsv_after_success_and_nothing_after_failure(self) -> None:
        args = ["--metadata", str(self.metadata_path), "--record", str(self.record_path),
                "--release-id", "123", "--repo", str(self.repo)]
        for succeeds in (True, False):
            stdout, stderr = io.StringIO(), io.StringIO()
            result = {"return_value": ((200, "SOURCE-1111111.zip"),)} if succeeds else {"side_effect": ValueError("rejected")}
            with self.subTest(succeeds=succeeds), patch.object(self.transport, "select_assets", **result):
                with redirect_stdout(stdout), redirect_stderr(stderr):
                    status = self.transport.main(args)
                self.assertEqual(status, 0 if succeeds else 1)
                self.assertEqual(stdout.getvalue(), "200\tSOURCE-1111111.zip\n" if succeeds else "")
                self.assertEqual(bool(stderr.getvalue()), not succeeds)

    def test_cli_rejects_noncanonical_release_id(self) -> None:
        for value in ("0", "-1", "01", "true", "1;touch unsafe", "9" * 30):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                self.transport._release_id(value)

    def test_real_git_binding_rejects_changed_and_uncommitted_record(self) -> None:
        def git(*args):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
        git("init", "--quiet")
        relative = self.record_path.relative_to(self.repo).as_posix()
        git("add", "--", relative)
        with self.assertRaises(ValueError):
            self.select()
        git("-c", "user.name=Review fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "--quiet", "-m", "Synthetic committed review record")
        self.assertEqual(len(self.select()), 3)
        self.record_path.write_text(json.dumps(self.record) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "committed HEAD"):
            self.select()


if __name__ == "__main__":
    unittest.main()
