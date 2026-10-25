"""Entry HTML revalidates; versioned assets retain caching. No test extras."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cutroom.config import load_settings
from server import create_app


class EntryDocumentCacheTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="cr-entry-http-")
        self.addCleanup(temp.cleanup)
        self.temp = Path(temp.name)
        environment = patch.dict(os.environ, {"CUTROOM_DATA_DIR": str(self.temp / "data")})
        environment.start()
        self.addCleanup(environment.stop)
        settings = load_settings(self.temp / "no-user-config.json")
        settings.ai.update(enabled=False, auto_start_ollama=False, download_models_on_setup=False)
        settings.raw.update(open_browser=False, job_workers=1, background_workers=1)
        app = create_app(settings)
        self.addCleanup(app.extensions["cutroom_jobs"].shutdown, wait=True, cancel_pending=True)
        self.client = app.test_client()

    def assert_entry(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cache_control.no_cache)
        self.assertIsNone(response.cache_control.max_age)
        self.assertTrue(response.headers.get("ETag"))
        self.assertIn(b"/assets/app.js?v=", response.data)

    def test_entry_requires_revalidation(self):
        self.assert_entry("/")

    def test_query_entry_requires_revalidation(self):
        self.assert_entry("/?project=existing")

    def test_head_entry_retains_validator(self):
        initial = self.client.get("/")
        response = self.client.head("/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"")
        self.assertEqual(response.headers["ETag"], initial.headers["ETag"])
        self.assertTrue(response.cache_control.no_cache)

    def test_entry_304_still_requires_revalidation(self):
        initial = self.client.get("/")
        response = self.client.get("/", headers={"If-None-Match": initial.headers["ETag"]})
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response.data, b"")
        self.assertEqual(response.headers["ETag"], initial.headers["ETag"])
        self.assertTrue(response.cache_control.no_cache)

    def assert_asset(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cache_control.public)
        self.assertEqual(response.cache_control.max_age, 300)
        self.assertFalse(response.cache_control.no_cache)
        self.assertTrue(response.headers.get("ETag"))

    def test_versioned_stylesheet_retains_cache(self):
        self.assert_asset("/assets/styles.css?v=1.2-beta-20261024-cache1")

    def test_versioned_imported_module_retains_cache(self):
        self.assert_asset("/assets/media-studio.js?v=1.2-beta-20261024-cache1")

    def test_asset_304_retains_cache(self):
        path = "/assets/styles.css?v=1.2-beta-20261024-cache1"
        initial = self.client.get(path)
        response = self.client.get(path, headers={"If-None-Match": initial.headers["ETag"]})
        self.assertEqual(response.status_code, 304)
        self.assertTrue(response.cache_control.public)
        self.assertEqual(response.cache_control.max_age, 300)

    def assert_api(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.cache_control.no_store)

    def test_health_remains_no_store(self):
        self.assert_api("/api/health")

    def test_instance_remains_no_store(self):
        self.assert_api("/api/instance")
