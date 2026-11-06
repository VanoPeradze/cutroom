"""Import recovery uses disposable projects and never launches a real media tool."""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cutroom import media, media_library
from cutroom.config import load_settings
from cutroom.jobs import JobCancelled
from server import create_app


def probe_result():
    return subprocess.CompletedProcess([], 0, json.dumps({
        "streams": [{"codec_type": "video", "codec_name": "h264", "width": 640,
                     "height": 360, "duration": "2", "avg_frame_rate": "30/1"}],
        "format": {"duration": "2", "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    }), "")


class MediaProbeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="cutroom-probe-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {
            "CUTROOM_DATA_DIR": str(self.root / "data"), "CUTROOM_NO_BROWSER": "1",
            "CUTROOM_FFPROBE": str(self.root / "not-installed-ffprobe.exe"),
            "CUTROOM_FFMPEG": str(self.root / "not-installed-ffmpeg.exe"),
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.settings = load_settings(self.root / "no-user-configuration.json")
        self.settings.raw["ai"].update(enabled=False, auto_start_ollama=False)
        self.app = create_app(self.settings)
        self.app.config.update(TESTING=True)
        self.manager = self.app.extensions["cutroom_jobs"]
        self.addCleanup(self.manager.shutdown, wait=True, cancel_pending=True)
        self.addCleanup(self.app.extensions["cutroom_upload_storage"].close)
        self.client = self.app.test_client()
        created = self.client.post("/api/projects", json={"name": "Synthetic \u05e2\u05e8\u05d9\u05db\u05d4"})
        self.assertEqual(created.status_code, 201)
        self.pid = created.get_json()["project"]["id"]
        self.url = f"/api/projects/{self.pid}"
        self.store = self.app.extensions["cutroom_store"]
        self.project_dir = self.store.project_dir(self.pid)

    def upload(self, target="sources/A", filename="synthetic.mp4"):
        return self.client.post(f"{self.url}/{target}", data={
            "file": (io.BytesIO(b"disposable synthetic bytes"), filename),
        }, content_type="multipart/form-data")

    def assert_dependency_error(self, response):
        self.assertEqual(response.status_code, 503, response.get_json())
        body = response.get_json()
        self.assertEqual(body["error"], "media_probe_unavailable")
        self.assertIn("FFprobe", body["message"])
        self.assertIn("repair CUTROOM", body["message"])
        self.assertIn("retry", body["message"])
        self.assertNotIn(str(self.root), response.get_data(as_text=True))
        self.assertNotIn("private diagnostic", response.get_data(as_text=True))

    def assert_unchanged(self, before):
        self.assertEqual((self.project_dir / "project.json").read_bytes(), before)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(self.manager.active(project_id=self.pid))

    def chunked_upload(self, target="sources/A"):
        purpose = "asset" if target == "assets" else "source"
        body = b"disposable synthetic bytes"
        preflight = self.client.post(f"{self.url}/uploads/preflight", json={
            "purpose": purpose, "slot": None if purpose == "asset" else target[-1],
            "filename": "synthetic.mp4", "size_bytes": len(body),
        })
        self.assertEqual(preflight.status_code, 201, preflight.get_json())
        receipt = preflight.get_json()
        transferred = self.client.put(receipt["upload_url"], data=body,
            content_type="application/octet-stream", headers={"X-Cutroom-Upload-Offset": "0"})
        self.assertEqual(transferred.status_code, 200, transferred.get_json())
        return self.client.post(f"{self.url}/{target}", headers={
            "X-Cutroom-Upload-Transport": "chunked-v1", "X-Cutroom-Upload-Token": receipt["upload_token"],
        })

    def test_chunked_import_failure_releases_reservations_and_preserves_project(self):
        before = (self.project_dir / "project.json").read_bytes()
        storage = self.app.extensions["cutroom_upload_storage"]
        for target in ("sources/A", "sources/B", "assets"):
            with self.subTest(target=target):
                self.assert_dependency_error(self.chunked_upload(target))
                self.assert_unchanged(before)
                self.assertFalse(storage.tickets)
                self.assertFalse(any(p.is_file() for p in (self.project_dir / "media").rglob("*")))

    def test_chunked_retry_accepts_a_fresh_upload_after_probe_recovers(self):
        self.assert_dependency_error(self.chunked_upload())
        with patch("cutroom.media.subprocess.run", return_value=probe_result()), \
             patch("server._prepare_source", return_value={"synthetic": True}):
            response = self.chunked_upload()
        self.assertEqual(response.status_code, 201, response.get_json())
        source = self.store.load(self.pid)["sources"]["A"]
        self.assertEqual((self.project_dir / source["relative_path"]).read_bytes(), b"disposable synthetic bytes")
        self.assertFalse(self.app.extensions["cutroom_upload_storage"].tickets)

    def test_missing_executable_is_actionable_for_both_source_slots(self):
        before = (self.project_dir / "project.json").read_bytes()
        # This intentionally nonexistent executable is inside the test's own
        # temporary directory. No installed system FFprobe is accessed.
        for slot in ("A", "B"):
            with self.subTest(slot=slot):
                self.assert_dependency_error(self.upload(f"sources/{slot}"))
                self.assert_unchanged(before)
                self.assertFalse(list((self.project_dir / "media").rglob("*.*")))

    def test_probe_permission_failure_does_not_imply_a_deleted_project(self):
        before = (self.project_dir / "project.json").read_bytes()
        with patch("cutroom.media.subprocess.run", side_effect=PermissionError("private diagnostic")):
            for slot in ("A", "B"):
                self.assert_dependency_error(self.upload(f"sources/{slot}"))
        self.assert_unchanged(before)

    def test_library_video_audio_and_image_launch_failures_leave_no_assets(self):
        before = (self.project_dir / "project.json").read_bytes()
        for error in (FileNotFoundError, PermissionError):
            for suffix in ("mp4", "wav", "png"):
                with self.subTest(error=error.__name__, suffix=suffix):
                    with patch("cutroom.media.subprocess.run", side_effect=error("private diagnostic")):
                        self.assert_dependency_error(self.upload("assets", f"synthetic.{suffix}"))
                    self.assert_unchanged(before)
                    self.assertFalse(any(p.is_file() for p in (self.project_dir / "media").rglob("*")))
                    self.assertFalse(self.store.load(self.pid).get("assets"))

    def test_failed_replacement_keeps_original_source_bytes_edit_and_revision(self):
        original = self.project_dir / "media" / "source-A.mp4"
        original.write_bytes(b"original synthetic source must survive")

        def seed(project):
            project["sources"]["A"] = {"slot": "A", "name": "original.mp4",
                "relative_path": "media/source-A.mp4", "duration": 2, "width": 640,
                "height": 360, "has_audio": False, "generation": "original", "preparation": "ready"}
            project["manual"]["audio_mixer"] = {"source_db": -5}
            project["settings"]["aspect"] = "9:16"

        self.store.update(self.pid, seed)
        before = (self.project_dir / "project.json").read_bytes()
        self.assert_dependency_error(self.upload())
        self.assert_unchanged(before)
        self.assertEqual(original.read_bytes(), b"original synthetic source must survive")
        self.assertEqual(list((self.project_dir / "media").glob("*")), [original])

    def test_source_retry_can_import_after_probe_becomes_available(self):
        self.assert_dependency_error(self.upload())
        # Only exercise admission/persistence here; actual encoding is covered
        # by release CI. This preparation stub starts no media process.
        with patch("cutroom.media.subprocess.run", return_value=probe_result()), \
             patch("server._prepare_source", return_value={"synthetic": True}):
            response = self.upload()
        self.assertEqual(response.status_code, 201, response.get_json())
        source = self.store.load(self.pid)["sources"]["A"]
        self.assertEqual(source["name"], "synthetic.mp4")
        self.assertEqual((self.project_dir / source["relative_path"]).read_bytes(), b"disposable synthetic bytes")

    def test_library_retry_can_import_after_probe_becomes_available(self):
        self.assert_dependency_error(self.upload("assets"))
        with patch("cutroom.media.subprocess.run", return_value=probe_result()), \
             patch("server.prepare_asset", return_value={"synthetic": True}):
            response = self.upload("assets")
        self.assertEqual(response.status_code, 202, response.get_json())
        asset_id = response.get_json()["asset_id"]
        asset = self.store.load(self.pid)["assets"][asset_id]
        self.assertEqual((self.project_dir / asset["path"]).read_bytes(), b"disposable synthetic bytes")

    def test_invalid_media_retains_existing_validation_responses(self):
        for target, status in (("sources/A", 422), ("assets", 400)):
            with self.subTest(target=target):
                with patch("cutroom.media.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["synthetic-probe"])):
                    response = self.upload(target)
                self.assertEqual(response.status_code, status, response.get_json())
                self.assertEqual(response.get_json()["error"], "invalid_media")

    def test_missing_project_retains_404_without_attempting_probe(self):
        with patch("cutroom.media.subprocess.run") as launch:
            response = self.client.post("/api/projects/project_000000000000/sources/A", data={
                "file": (io.BytesIO(b"synthetic"), "synthetic.mp4"),
            }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "not_found")
        launch.assert_not_called()

    def test_missing_input_after_successful_probe_is_not_a_dependency_failure(self):
        with patch("cutroom.media.subprocess.run", return_value=probe_result()):
            with self.assertRaises(FileNotFoundError):
                media.probe_media(self.root / "absent-input.mp4", self.settings)

    def test_cancellable_library_probe_classifies_launch_failure(self):
        with patch("cutroom.media.subprocess.Popen", side_effect=FileNotFoundError("private diagnostic")):
            with self.assertRaises(media.MediaProbeUnavailableError):
                media_library.probe_asset(self.root / "synthetic.mp4", "video", self.settings, cancel_check=lambda: None)

    def test_cancellation_is_not_reclassified_as_a_missing_dependency(self):
        def cancel():
            raise JobCancelled("Synthetic cancellation")

        with patch("cutroom.media.subprocess.Popen") as launch:
            with self.assertRaises(JobCancelled):
                media_library.probe_asset(self.root / "synthetic.mp4", "video", self.settings, cancel_check=cancel)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
