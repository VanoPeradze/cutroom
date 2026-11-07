"""Desktop bootstrap checks without downloads, actual browsers or project access."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cutroom_desktop_launcher", ROOT / "scripts" / "desktop_windows.py")
desktop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(desktop)


class DesktopLauncherTests(unittest.TestCase):
    def test_finds_only_existing_chrome(self):
        with tempfile.TemporaryDirectory(prefix="cutroom-desktop-unit-") as folder:
            root = Path(folder)
            chrome = root / "Google" / "Chrome" / "Application" / "chrome.exe"
            chrome.parent.mkdir(parents=True)
            chrome.write_bytes(b"synthetic not executable")
            self.assertEqual(desktop.find_chrome({"ProgramFiles": folder}), chrome)

    def test_existing_edge_is_not_a_fallback(self):
        with tempfile.TemporaryDirectory(prefix="cutroom-desktop-unit-") as folder:
            edge = Path(folder) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            edge.parent.mkdir(parents=True)
            edge.write_bytes(b"synthetic not executable")
            with self.assertRaisesRegex(RuntimeError, "Google Chrome is not installed"):
                desktop.find_chrome({"ProgramFiles": folder})

    def test_missing_chrome_does_not_install(self):
        with patch.object(desktop.subprocess, "Popen") as process:
            with self.assertRaisesRegex(RuntimeError, "No software was installed"):
                desktop.find_chrome({})
            process.assert_not_called()

    def test_app_window_has_private_profile_and_no_browser_tab(self):
        args = desktop.chrome_arguments(Path("chrome.exe"), "http://127.0.0.1:8765", Path("C:/private-profile"))
        self.assertIn("--app=http://127.0.0.1:8765", args)
        self.assertIn("--user-data-dir=C:\\private-profile" if desktop.os.name == "nt" else "--user-data-dir=C:/private-profile", args)
        self.assertIn("--disable-background-mode", args)

    def test_nonlocal_and_credential_urls_are_rejected(self):
        for url in ("https://example.org", "http://192.168.1.4:8765", "file:///C:/private", "http://me@localhost:8765", "http://localhost:8765/?secret=x", "http://localhost:8765/#x", "http://localhost:8765/admin"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                desktop.chrome_arguments(Path("chrome.exe"), url, Path("profile"))

    def test_ipv6_loopback_is_supported(self):
        self.assertIn("--app=http://[::1]:8765", desktop.chrome_arguments(Path("chrome.exe"), "http://[::1]:8765", Path("profile")))

    def test_ready_engine_is_accepted_without_kill(self):
        child = Mock()
        desktop.wait_for_backend(lambda: "match", child)
        child.poll.assert_not_called()
        child.terminate.assert_not_called()

    def test_wrong_engine_is_never_stopped(self):
        for identity in ("different_instance", "different_version"):
            child = Mock()
            with self.assertRaisesRegex(RuntimeError, "Nothing was stopped"):
                desktop.wait_for_backend(lambda: identity, child)
            child.terminate.assert_not_called()
            child.kill.assert_not_called()

    def test_startup_failure_is_visible(self):
        child = Mock()
        child.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "engine stopped"):
            desktop.wait_for_backend(lambda: "unknown", child)

    def test_timeout_does_not_kill_possible_live_work(self):
        child = Mock()
        child.poll.return_value = None
        ticks = iter([0, 0, 2])
        with self.assertRaisesRegex(RuntimeError, "No processes were terminated"):
            desktop.wait_for_backend(lambda: "unknown", child, timeout=1, clock=lambda: next(ticks), sleep=lambda _: None)
        child.terminate.assert_not_called()
        child.kill.assert_not_called()

    def test_backend_starts_without_setup_or_browser(self):
        with tempfile.TemporaryDirectory(prefix="cutroom-desktop-unit-") as folder:
            root = Path(folder)
            with patch.object(desktop.subprocess, "Popen") as process:
                desktop.launch_backend(root / "python.exe", root, root / "logs" / "engine.log")
            args, kwargs = process.call_args
            self.assertEqual(args[0][-1], "server")
            self.assertNotIn("setup", " ".join(args[0]))
            self.assertEqual(kwargs["env"]["CUTROOM_NO_BROWSER"], "1")
            self.assertEqual(kwargs["cwd"], str(root))


if __name__ == "__main__":
    unittest.main()
