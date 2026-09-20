"""The downloaded beta has one obvious launcher; no installer runs in these tests."""
import os
from html.parser import HTMLParser
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "packaging/windows/START CUTROOM.bat"


def test_download_launcher_is_portable_and_does_not_duplicate_installation():
    data = LAUNCHER.read_bytes()
    text = data.decode("ascii")
    assert b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    assert 'pushd "%~dp0App"' in text
    assert "DisableDelayedExpansion" in text
    assert "call run_windows.bat" in text
    assert "popd" in text
    assert "exit /b %CUTROOM_LAUNCH_EXIT%" in text
    assert "Extract All" in text
    for command in ("pip install", "winget install", "powershell", "start http", "del /", "rmdir"):
        assert command not in text.lower()


def test_offline_help_has_shipped_links_and_one_clear_launcher():
    from cutroom import __version_label__
    from scripts.build_test_package import collect_payload

    payload = collect_payload(ROOT)
    help_text = payload["packaging/windows/START HERE.html"].decode("utf-8")
    assert __version_label__ in help_text
    assert __version_label__ in LAUNCHER.read_text(encoding="ascii")
    assert "START CUTROOM.bat" in help_text
    assert "Extract All" in help_text
    assert "App/data" in help_text
    assert "<script" not in help_text.lower()

    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            values = dict(attrs)
            assert not any(name.startswith("on") for name in values)
            if tag == "a" and "href" in values:
                url = urlsplit(values["href"])
                if not url.scheme and url.path:
                    path = unquote(url.path)
                    assert path.startswith("App/")
                    assert path.removeprefix("App/") in payload, path
            if tag in {"script", "link", "img", "iframe"}:
                pytest.fail("The offline help must not depend on external assets or embedded content")

    Links().feed(help_text)


@pytest.mark.skipif(os.name != "nt", reason="Runs Windows cmd.exe with a harmless stub, not real setup")
@pytest.mark.parametrize("result", [0, 23])
def test_download_launcher_runs_app_from_its_directory_and_preserves_exit_code(tmp_path, result):
    folder = tmp_path / "CUTROOM space & bang!"
    app = folder / "App"
    app.mkdir(parents=True)
    launcher = folder / "START CUTROOM.bat"
    launcher.write_bytes(LAUNCHER.read_bytes())
    (app / "run_windows.bat").write_bytes(
        f'@echo off\r\ncd\r\nexit /b {result}\r\n'.encode("ascii")
    )
    completed = subprocess.run(
        f'cmd.exe /d /v:off /s /c ""{launcher}""', cwd=tmp_path,
        capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == result, completed.stdout + completed.stderr
    assert str(app) in completed.stdout


@pytest.mark.skipif(os.name != "nt", reason="Runs Windows cmd.exe only")
def test_missing_app_shows_extract_all_help_without_running_any_installer(tmp_path):
    launcher = tmp_path / "START CUTROOM.bat"
    launcher.write_bytes(LAUNCHER.read_bytes())
    completed = subprocess.run(
        f'cmd.exe /d /v:off /s /c ""{launcher}""', cwd=tmp_path,
        capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
    )
    assert completed.returncode == 1
    assert "Extract All" in completed.stdout
    assert "App folder" in completed.stdout
