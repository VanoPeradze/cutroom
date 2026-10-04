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


def test_preflight_accepts_compatible_ffmpeg_and_reports_missing_commands(monkeypatch):
    def capture(command, *args):
        if "-filters" in args:
            return " ... subtitles V->V Render subtitles using libass\n"
        if "-encoders" in args:
            return " V....D libx264 H.264\n A..... aac AAC\n"
        if "-h" in args:
            return "-filter_complex_script filename  read a filtergraph\n-vsync  video sync\n"
        return "version"

    monkeypatch.setattr(preflight, "_capture", capture)
    assert preflight.check_system() == []
    monkeypatch.setattr(preflight, "_capture", lambda *args: (_ for _ in ()).throw(FileNotFoundError("missing")))
    assert len(preflight.check_system()) == 2


@pytest.mark.parametrize("missing", ["-filter_complex_script", "-vsync"])
def test_preflight_rejects_removed_render_options_even_with_all_codecs(monkeypatch, missing):
    def capture(command, *args):
        if "-filters" in args:
            return " ... subtitles V->V Render subtitles using libass\n"
        if "-encoders" in args:
            return " V....D libx264 H.264\n A..... aac AAC\n"
        if "-h" in args:
            return "\n".join(f"{option} value  description" for option in ("-filter_complex_script", "-vsync") if option != missing)
        return "ffmpeg version 9.0.1"

    monkeypatch.setattr(preflight, "_capture", capture)
    failures = preflight.check_system()
    assert len(failures) == 1
    assert missing in failures[0]
    assert "use ffmpeg@7" in failures[0]


def test_override_validation_does_not_require_unconfigured_binary(monkeypatch):
    monkeypatch.delenv("CUTROOM_FFMPEG", raising=False)
    monkeypatch.setenv("CUTROOM_FFPROBE", "/chosen path/ffprobe")
    called = []
    monkeypatch.setattr(preflight, "_capture", lambda command, *args: called.append(command) or "version")
    assert preflight.check_system(only_overrides=True) == []
    assert called == ["/chosen path/ffprobe"]


def test_python_import_failure_is_actionable(monkeypatch):
    monkeypatch.delenv("CUTROOM_MAC_ARCH", raising=False)

    def broken_import(name):
        if name == "faster_whisper":
            raise OSError("native library cannot load")

    monkeypatch.setattr(preflight.importlib, "import_module", broken_import)
    assert any("faster_whisper: OSError: native library cannot load" in error for error in preflight.check_python())


@pytest.mark.parametrize("version", ["19.0.0", "19.1.2", "18.0.0", "unrecognized"])
def test_python_preflight_rejects_incompatible_pyav_even_without_imports(monkeypatch, version):
    monkeypatch.setattr(preflight, "package_version", lambda name: version)
    failures = preflight.check_python(imports=False)
    assert any(f"PyAV {version} is incompatible" in failure for failure in failures)


@pytest.mark.parametrize("version", ["18.1.0", "18.2.1"])
def test_python_preflight_accepts_constrained_pyav(monkeypatch, version):
    monkeypatch.setattr(preflight, "package_version", lambda name: version)
    assert not any("PyAV" in failure for failure in preflight.check_python(imports=False))


def test_python_preflight_rejects_rosetta_python_for_native_arm_runtime(monkeypatch):
    monkeypatch.setenv("CUTROOM_MAC_ARCH", "arm64")
    monkeypatch.setattr(preflight.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(preflight, "package_version", lambda name: "18.1.0")
    assert any("Python architecture x86_64 does not match this Mac (arm64)" in failure
               for failure in preflight.check_python(imports=False))


def test_macos_constraint_preserves_faster_whisper_audio_api():
    constraints = (MAC / "constraints-macos.txt").read_text(encoding="utf-8").splitlines()
    assert "av>=18.1.0,<19" in constraints


@pytest.mark.parametrize("code", [0, 1, 9])
def test_launch_preserves_server_exit_code_without_spawning(monkeypatch, code):
    def server():
        raise SystemExit(code)

    monkeypatch.delenv("CUTROOM_FINDER_LAUNCH", raising=False)
    monkeypatch.setattr(preflight, "run_macos_server", server)
    assert preflight.main(["--launch"]) == code


@pytest.fixture
def shell_app(tmp_path):
    # Quoting must hold for spaces, Unicode and shell metacharacters.
    app = tmp_path / "CUTROOM עברית $(touch INJECTED) ;" / "App"
    app.mkdir(parents=True)
    for name in ("setup_macos.sh", "run_macos.sh", "preflight_macos.py", "constraints-macos.txt"):
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
        'if [[ "$1" == -m && "$2" == ensurepip ]]; then\n'
        '  if [[ "${CUTROOM_TEST_ENSUREPIP_FAIL:-}" == yes ]]; then printf "ensurepip fixture failure\\n" >&2; exit 7; fi\n'
        '  touch "$CUTROOM_TEST_APP/.mock-pip-restored"\n'
        '  exit 0\nfi\n'
        'if [[ "$1" == -m && "$2" == pip ]]; then\n'
        '  if [[ "${CUTROOM_TEST_NO_PIP:-}" == yes && ! -f "$CUTROOM_TEST_APP/.mock-pip-restored" ]]; then\n'
        '    printf "No module named pip\\n" >&2\n'
        '    exit 1\n'
        '  fi\n'
        '  if [[ "${CUTROOM_TEST_PIP_FAIL:-}" == yes ]]; then exit 9; fi\n'
        '  if [[ "$*" == *requirements.txt* ]]; then touch "$CUTROOM_TEST_APP/.mock-ready"; fi\n'
        '  exit 0\nfi\n'
        'if [[ "${2:-}" == --overrides-only ]]; then\n'
        '  [[ "${CUTROOM_TEST_BAD_OVERRIDE:-}" != yes ]]\n'
        '  exit $?\nfi\n'
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
    assert "-r requirements.txt -c constraints-macos.txt" in calls(env)
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
def test_existing_incompatible_python_environment_repairs_with_constraints(shell_app):
    app, env = shell_app
    (app / ".venv/bin").mkdir(parents=True)
    shutil.copyfile(env["CUTROOM_TEST_PYTHON"], app / ".venv/bin/python")
    (app / ".venv/bin/python").chmod(0o755)
    # Native Python works, but the mock's Python preflight rejects this runtime.
    result = run_setup(app, env, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "--force-reinstall -r requirements.txt -c constraints-macos.txt" in calls(env)
    assert (app / ".mock-ready").exists()


@needs_bash
def test_brew_install_requires_consent_and_uses_compatible_formula(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_SYSTEM_MISSING"] = "yes"
    cancelled = run_setup(app, env, answer="\n")
    assert cancelled.returncode == 1
    assert "BREW install" not in calls(env)
    installed = run_setup(app, env, answer="yes\n")
    assert installed.returncode == 0, installed.stdout + installed.stderr
    assert "BREW install ffmpeg@7" in calls(env)


@needs_bash
def test_missing_homebrew_prints_official_help_without_install(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_SYSTEM_MISSING"] = "yes"
    result = run_setup(
        app, env, "--yes",
        extra='command() { if [[ "$*" == "-v brew" || "$*" == "-v open" ]]; then return 1; else builtin command "$@"; fi; };',
    )
    assert result.returncode == 1
    assert "Homebrew: https://brew.sh/" in result.stderr.splitlines()
    assert "brew install python@3.12 ffmpeg@7" in result.stderr
    assert "pip install" not in calls(env)


@needs_bash
def test_incompatible_explicit_ffmpeg_override_stops_before_downloads(shell_app):
    app, env = shell_app
    env["CUTROOM_FFMPEG"] = "/chosen incompatible/ffmpeg"
    env["CUTROOM_TEST_BAD_OVERRIDE"] = "yes"
    result = run_setup(app, env, "--yes")
    assert result.returncode == 1
    assert "custom CUTROOM_FFMPEG/CUTROOM_FFPROBE path is incompatible" in result.stderr
    assert "pip install" not in calls(env)
    assert "BREW install" not in calls(env)
    assert not (app / ".venv").exists()


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


@needs_bash
def test_closed_stdin_cancels_without_downloads(shell_app):
    app, env = shell_app
    result = run_setup(app, env, answer="")
    assert result.returncode == 1
    assert "Setup cancelled" in result.stdout
    assert "pip install" not in calls(env)
    assert "BREW install" not in calls(env)
    assert not (app / ".venv").exists()


@needs_bash
def test_no_python_or_homebrew_has_actionable_help_without_changes(shell_app):
    app, env = shell_app
    env.pop("CUTROOM_PYTHON")
    result = run_setup(
        app, env, "--yes",
        extra='cutroom_resolve_python() { return 1; }; '
              'command() { if [[ "$*" == "-v brew" || "$*" == "-v open" ]]; then return 1; else builtin command "$@"; fi; };',
    )
    assert result.returncode == 1
    assert "Homebrew is not installed." in result.stderr
    assert "  brew install python@3.12 ffmpeg@7" in result.stderr.splitlines()
    assert not (app / ".venv").exists()
    assert not (app / ".setup-macos.lock").exists()
    assert calls(env) == ""


@needs_bash
def test_missing_python_installs_only_after_consent_then_checks_runtime(shell_app):
    app, env = shell_app
    env.pop("CUTROOM_PYTHON")
    resolver = ('cutroom_resolve_python() { '
                'if [[ -f "$CUTROOM_TEST_APP/.mock-system" ]]; then printf "%s\\n" "$CUTROOM_TEST_PYTHON"; else return 1; fi; };')
    declined = run_setup(app, env, answer="no\n", extra=resolver)
    assert declined.returncode == 1
    assert "BREW install" not in calls(env)
    result = run_setup(app, env, "--yes", extra=resolver)
    assert result.returncode == 0, result.stdout + result.stderr
    commands = calls(env)
    assert commands.index("BREW install python@3.12") < commands.index("-m venv .venv")
    assert "BREW install ffmpeg@7" in commands
    assert "-r requirements.txt -c constraints-macos.txt" in commands


@needs_bash
def test_existing_setup_lock_is_preserved_without_installing(shell_app):
    app, env = shell_app
    lock = app / ".setup-macos.lock"
    lock.mkdir()
    marker = lock / "other-setup-owner"
    marker.write_text("leave this setup alone", encoding="utf-8")
    result = run_setup(app, env, "--yes")
    assert result.returncode == 1
    assert "Another setup may be running" in result.stderr
    assert marker.read_text(encoding="utf-8") == "leave this setup alone"
    assert "pip install" not in calls(env)
    assert "BREW install" not in calls(env)


@needs_bash
def test_retry_after_partial_pip_install_reuses_venv_and_repairs(shell_app):
    app, env = shell_app
    env["CUTROOM_TEST_PIP_FAIL"] = "yes"
    failed = run_setup(app, env, "--yes")
    assert failed.returncode == 9
    assert (app / ".venv/bin/python").exists()
    assert not (app / ".setup-macos.lock").exists()
    env.pop("CUTROOM_TEST_PIP_FAIL")
    before = calls(env)
    retry = run_setup(app, env, "--yes")
    assert retry.returncode == 0, retry.stdout + retry.stderr
    subsequent = calls(env)[len(before):]
    assert "-m venv" not in subsequent
    assert "--force-reinstall -r requirements.txt -c constraints-macos.txt" in subsequent
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_recovers_valid_venv_without_pip(shell_app):
    app, env = shell_app
    (app / ".venv/bin").mkdir(parents=True)
    shutil.copyfile(env["CUTROOM_TEST_PYTHON"], app / ".venv/bin/python")
    (app / ".venv/bin/python").chmod(0o755)
    env["CUTROOM_TEST_NO_PIP"] = "yes"
    declined = run_setup(app, env, answer="no\n")
    assert declined.returncode == 1
    assert "-m ensurepip" not in calls(env)
    assert not (app / ".mock-pip-restored").exists()
    result = run_setup(app, env, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (app / ".mock-pip-restored").exists()
    commands = calls(env)
    assert commands.index("-m ensurepip --upgrade") < commands.index("-m pip install")
    assert "--force-reinstall -r requirements.txt -c constraints-macos.txt" in calls(env)
    assert (app / ".mock-ready").exists()
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_ensurepip_failure_stops_once_with_actionable_recovery(shell_app):
    app, env = shell_app
    (app / ".venv/bin").mkdir(parents=True)
    shutil.copyfile(env["CUTROOM_TEST_PYTHON"], app / ".venv/bin/python")
    (app / ".venv/bin/python").chmod(0o755)
    env.update(CUTROOM_TEST_NO_PIP="yes", CUTROOM_TEST_ENSUREPIP_FAIL="yes")
    result = run_setup(app, env, "--yes")
    assert result.returncode == 1
    assert "CUTROOM could not restore pip" in result.stderr
    assert "rename App/.venv to an unused name" in result.stderr
    assert calls(env).count("-m ensurepip --upgrade") == 1
    assert "-m pip install" not in calls(env)
    assert "setup completed" not in result.stdout
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_broken_venv_is_preserved_when_recreated(shell_app):
    app, env = shell_app
    broken = app / ".venv"
    broken.mkdir()
    (broken / "saved-environment-file").write_text("preserve", encoding="utf-8")
    result = run_setup(app, env, "--yes")
    assert result.returncode == 0, result.stdout + result.stderr
    backups = list(app.glob(".venv.previous-*"))
    assert len(backups) == 1
    assert (backups[0] / "saved-environment-file").read_text(encoding="utf-8") == "preserve"
    assert (app / ".venv/bin/python").exists()


@needs_bash
def test_unusable_ffmpeg_after_brew_stops_before_python_install(shell_app):
    app, env = shell_app
    result = run_setup(app, env, "--yes", extra="cutroom_system_ready() { return 1; };")
    assert result.returncode == 1
    assert "BREW install ffmpeg@7" in calls(env)
    assert "FFmpeg is still unavailable or lacks required codecs/options" in result.stderr
    assert "pip install" not in calls(env)
    assert not (app / ".venv").exists()
    assert not (app / ".setup-macos.lock").exists()


@needs_bash
def test_macos_14_is_rejected_before_dependency_discovery(shell_app):
    app, env = shell_app
    result = subprocess.run(
        [BASH, "-c", 'source "$1"; uname() { if [[ "$1" == -s ]]; then printf "Darwin\\n"; else printf "x86_64\\n"; fi; }; '
         'sw_vers() { printf "14.7.0\\n"; }; cutroom_help() { :; }; cutroom_prepare_environment',
         "test-old-mac", (app / "setup_macos.sh").as_posix()],
        env=env, cwd=app, capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 1
    assert "requires macOS 15 or later (found 14.7.0)" in result.stderr
    assert calls(env) == ""


@needs_bash
def test_top_level_launcher_reports_incomplete_extraction_without_hanging(tmp_path):
    folder = tmp_path / "Unpacked חלקי download"
    folder.mkdir()
    launcher = folder / "START CUTROOM.command"
    shutil.copyfile(MAC / launcher.name, launcher)
    result = subprocess.run(
        [BASH, launcher.as_posix()], input="", capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 1
    assert "The App folder is missing" in result.stderr
    assert "START HERE.html" in result.stderr
