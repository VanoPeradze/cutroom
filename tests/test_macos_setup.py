from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
MAC = ROOT / "packaging" / "mac"
SPEC = importlib.util.spec_from_file_location("mac_preflight", MAC / "preflight_macos.py")
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)
BASH = shutil.which("bash")
if BASH is None and Path("C:/Program Files/Git/bin/bash.exe").is_file():
    BASH = "C:/Program Files/Git/bin/bash.exe"
needs_bash = pytest.mark.skipif(BASH is None, reason="Bash is required for Mac launcher tests")


def test_mac_shell_files_are_lf_and_parse():
    for name in ("START CUTROOM.command", "setup_macos.sh", "run_macos.sh"):
        data = (MAC / name).read_bytes()
        assert data.startswith(b"#!/bin/bash\n")
        assert b"\r" not in data
        if BASH:
            subprocess.run([BASH, "-n", (MAC / name).as_posix()], check=True)


def test_preflight_requires_subtitles_h264_and_aac(monkeypatch):
    monkeypatch.setenv("CUTROOM_FFMPEG", "/some path/ffmpeg")
    monkeypatch.setenv("CUTROOM_FFPROBE", "/some path/ffprobe")
    calls = []

    def capture(command, *args):
        calls.append((command, args))
        if "-filters" in args:
            return " ... scale V->V Scale video\n"
        if "-encoders" in args:
            return " V..... h264_videotoolbox H.264\n"
        return "ffmpeg version test"

    monkeypatch.setattr(preflight, "_capture", capture)
    failures = preflight.check_system()
    assert any("libass" in item for item in failures)
    assert any("libx264" in item for item in failures)
    assert any("aac" in item for item in failures)
    assert calls[0][0] == "/some path/ffmpeg"
    assert calls[-1][0] == "/some path/ffprobe"


def test_preflight_accepts_full_ffmpeg_and_reports_missing_commands(monkeypatch):
    def capture(command, *args):
        if "-filters" in args:
            return " ... subtitles V->V Render subtitles using libass\n"
        if "-encoders" in args:
            return " V....D libx264 H.264\n A..... aac AAC\n"
        return "version"

    monkeypatch.setattr(preflight, "_capture", capture)
    assert preflight.check_system() == []
    monkeypatch.setattr(preflight, "_capture", lambda *args: (_ for _ in ()).throw(FileNotFoundError("missing")))
    assert len(preflight.check_system()) == 2


def test_python_import_failure_is_actionable(monkeypatch):
    monkeypatch.delenv("CUTROOM_MAC_ARCH", raising=False)

    def broken_import(name):
        if name == "faster_whisper":
            raise OSError("native library cannot load")

    monkeypatch.setattr(preflight.importlib, "import_module", broken_import)
    assert any("faster_whisper: OSError: native library cannot load" in error for error in preflight.check_python())


@pytest.mark.parametrize("code", [0, 1, 9])
def test_launch_preserves_server_exit_code_without_spawning(monkeypatch, code):
    def server(path, *, run_name):
        assert Path(path).name == "server.py"
        assert run_name == "__main__"
        raise SystemExit(code)

    monkeypatch.delenv("CUTROOM_FINDER_LAUNCH", raising=False)
    monkeypatch.setattr(preflight.runpy, "run_path", server)
    assert preflight.main(["--launch"]) == code


@pytest.fixture
def shell_app(tmp_path):
    # Quoting must hold for spaces, Unicode and shell metacharacters.
    app = tmp_path / "CUTROOM עברית $(touch INJECTED) ;" / "App"
    app.mkdir(parents=True)
    for name in ("setup_macos.sh", "run_macos.sh", "preflight_macos.py"):
        shutil.copyfile(MAC / name, app / name)
    (app / "requirements.txt").write_text("flask\n", encoding="utf-8")
    (app / "server.py").write_text("# fake server\n", encoding="utf-8")
    mock_bin = tmp_path / "mock commands"
    mock_bin.mkdir()
    python = mock_bin / "python3.12"
    python.write_text(
        "#!/bin/bash\nset -eu\n"
        'printf "%s\\n" "$*" >> "$CUTROOM_TEST_CALLS"\n'
        'if [[ "$1" == -c ]]; then exit 0; fi\n'
        'if [[ "$1" == -m && "$2" == venv ]]; then\n'
        '  mkdir -p "$3/bin"\n'
        '  cp "$CUTROOM_TEST_PYTHON" "$3/bin/python"\n'
        '  chmod +x "$3/bin/python"\n'
        '  exit 0\nfi\n'
        'if [[ "$1" == -m && "$2" == pip ]]; then\n'
        '  if [[ "${CUTROOM_TEST_PIP_FAIL:-}" == yes ]]; then exit 9; fi\n'
        '  if [[ "$*" == *requirements.txt* ]]; then touch "$CUTROOM_TEST_APP/.mock-ready"; fi\n'
        '  exit 0\nfi\n'
        'if [[ "${2:-}" == --system-only ]]; then\n'
        '  [[ "${CUTROOM_TEST_SYSTEM_MISSING:-}" != yes || -f "$CUTROOM_TEST_APP/.mock-system" ]]\n'
        '  exit $?\nfi\n'
        'if [[ "${2:-}" == --launch || "$1" == *server.py ]]; then\n'
        '  printf "SERVER %s %s\\n" "${CUTROOM_PORT:-}" "${CUTROOM_DATA_DIR:-}" >> "$CUTROOM_TEST_CALLS"\n'
        '  exit 0\nfi\n'
        'if [[ "$1" == *preflight_macos.py ]]; then [[ -f "$CUTROOM_TEST_APP/.mock-ready" ]]; exit $?; fi\nexit 88\n',
        encoding="utf-8", newline="\n",
    )
    python.chmod(0o755)
    brew = mock_bin / "brew"
    brew.write_text(
        '#!/bin/bash\nset -eu\nprintf "BREW %s\\n" "$*" >> "$CUTROOM_TEST_CALLS"\n'
        'touch "$CUTROOM_TEST_APP/.mock-system"\n', encoding="utf-8", newline="\n",
    )
    brew.chmod(0o755)
    env = os.environ.copy()
    for key in ("CUTROOM_PYTHON", "CUTROOM_MAC_ARCH", "CUTROOM_FFMPEG", "CUTROOM_FFPROBE"):
        env.pop(key, None)
    env.update(
        PATH=str(mock_bin) + os.pathsep + env.get("PATH", ""),
        CUTROOM_PYTHON=python.as_posix(), CUTROOM_TEST_PYTHON=python.as_posix(),
        CUTROOM_TEST_APP=app.as_posix(), CUTROOM_TEST_CALLS=(tmp_path / "calls.txt").as_posix(),
    )
    return app, env


def run_setup(app, env, *args, answer="", extra=""):
    return subprocess.run(
        [BASH, "-c", 'source "$1"; cutroom_prepare_environment() { :; }; ' + extra + ' cutroom_setup_main "${@:2}"',
         "test-setup", (app / "setup_macos.sh").as_posix(), *args],
        input=answer, capture_output=True, text=True, encoding="utf-8", env=env, cwd=app, timeout=30,
    )


def calls(env):
    path = Path(env["CUTROOM_TEST_CALLS"])
    return path.read_text(encoding="utf-8") if path.exists() else ""


@needs_bash
def test_cancel_has_no_downloads_or_environment(shell_app):
    app, env = shell_app
    result = run_setup(app, env, answer="no\n")
    assert result.returncode == 1, result.stderr
    assert "Setup cancelled" in result.stdout
    assert " pip " not in calls(env)
    assert "BREW install" not in calls(env)
    assert not (app / ".venv").exists()
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_explicit_install_and_offline_second_setup(shell_app):
    app, env = shell_app
    result = run_setup(app, env, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "pip install" in calls(env)
    assert (app / ".venv/bin/python").exists()
    assert not (app / ".setup-macos.lock").exists()
    assert not (app / "INJECTED").exists()
    before = calls(env)
    result = run_setup(app, env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No downloads" in result.stdout
    assert "pip" not in calls(env)[len(before):]
    assert "BREW" not in calls(env)[len(before):]


@needs_bash
def test_brew_install_requires_consent_and_uses_full_formula(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_SYSTEM_MISSING"] = "yes"
    cancelled = run_setup(app, env, answer="\n")
    assert cancelled.returncode == 1
    assert "BREW install" not in calls(env)
    installed = run_setup(app, env, answer="yes\n")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert "BREW install ffmpeg-full" in calls(env)


@needs_bash
def test_missing_homebrew_prints_official_help_without_install(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_SYSTEM_MISSING"] = "yes"
    result = run_setup(
        app, env, "--yes",
        extra='command() { if [[ "$*" == "-v brew" || "$*" == "-v open" ]]; then return 1; else builtin command "$@"; fi; };',
    )
    assert result.returncode == 1
    assert "https://brew.sh/" in result.stderr
    assert "brew install python@3.12 ffmpeg-full" in result.stderr
    assert "pip install" not in calls(env)


@needs_bash
def test_failed_install_releases_lock_and_does_not_claim_success(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_PIP_FAIL"] = "yes"
    result = run_setup(app, env, "--yes")
    assert result.returncode == 9
    assert "setup completed" not in result.stdout
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_runtime_check_and_launch_are_offline_and_preserve_environment(shell_app):
    app, env = shell_app
    result = run_setup(app, env, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    # The sourced function can be replaced in this fixture to exercise the Mac
    # launcher on Linux and Windows Git Bash without pretending the host is Mac.
    with (app / "setup_macos.sh").open("a", encoding="utf-8", newline="\n") as source:
        source.write("\ncutroom_prepare_environment() { :; }\n")
    env.update(CUTROOM_PORT="19432", CUTROOM_DATA_DIR="space עברית path")
    before = calls(env)
    for arguments in (("--check",), ()):
        result = subprocess.run(
            [BASH, (app / "run_macos.sh").as_posix(), *arguments],
            env=env, cwd=app, capture_output=True, text=True, encoding="utf-8", timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    subsequent = calls(env)[len(before):]
    assert "pip" not in subsequent
    assert "BREW" not in subsequent
    assert "SERVER 19432 space עברית path" in subsequent


@needs_bash
def test_check_never_triggers_setup(shell_app):
    app, env = shell_app
    with (app / "setup_macos.sh").open("a", encoding="utf-8", newline="\n") as source:
        source.write("\ncutroom_prepare_environment() { :; }\n")
    result = subprocess.run(
        [BASH, (app / "run_macos.sh").as_posix(), "--check"],
        env=env, cwd=app, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 1
    assert "has not been set up" in result.stderr
    assert "pip" not in calls(env)
