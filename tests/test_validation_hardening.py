from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = (ROOT / "scripts" / "validate_release.py").read_text(encoding="utf-8")


def test_release_validator_runs_every_discovered_pytest_suite():
    assert 'run("pytest_full", [sys.executable, "-m", "pytest", "-q"]' in VALIDATOR
    assert "core_tests = [" not in VALIDATOR
    assert 'run("pytest_api"' not in VALIDATOR


def test_server_smokes_use_an_isolated_port_and_own_live_process():
    assert "def free_loopback_port()" in VALIDATOR
    assert 'env["CUTROOM_PORT"] = str(port)' in VALIDATOR
    assert "process.poll() is None" in VALIDATOR
    assert 'health.get("ok") is True' in VALIDATOR
    assert 'desktop = temp / "validation-desktop.png"' in VALIDATOR
