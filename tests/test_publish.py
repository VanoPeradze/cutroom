from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import publish


@pytest.mark.parametrize("name", ["data/project.json", "nested/.env", ".env.local", ".tools/run.py",
                                  "web/recording.mp4", "weights.gguf", "my.key", "ai-connection.json",
                                  "a/../b.py", "/outside.py", "a\\b.py", "C:/outside.py"])
def test_rejects_private_runtime_or_noncanonical_paths(name):
    with pytest.raises(publish.PublishError):
        publish.scan_payload({name: b"test"})


@pytest.mark.parametrize("token", ["gsk_" + "A" * 40, "sk-proj-" + "A" * 40,
                                   "ghp_" + "a" * 40, "github_pat_" + "b" * 50,
                                   "AIza" + "c" * 35, "AKIA" + "A" * 16,
                                   "-----BEGIN " + "PRIVATE KEY-----"])
def test_rejects_recognizable_secrets_without_echoing_them(token):
    with pytest.raises(publish.PublishError) as caught:
        publish.scan_payload({"web/test.js": token.encode()})
    assert token not in str(caught.value)
    assert "web/test.js" in str(caught.value)


def test_rejects_literal_secret_but_accepts_explicit_synthetic_fixture():
    publish.scan_payload({"tests/fixture.py": b'api_key = "test-not-a-real-credential"'})
    with pytest.raises(publish.PublishError):
        publish.scan_payload({"web/config.js": b'api_key = "' + b"longRandomCredential123456789" + b'"'})


def test_safe_palette_documentation_and_binary_test_capture_pass():
    publish.scan_payload({
        "web/colors.css": b":root { --ink: #081013; --primary: #7459a3; --accent: #44b9c6; }",
        "docs/API.md": b'Use an environment variable. Example: api_key = "<YOUR_PROVIDER_API_KEY>"',
        "docs/images/welcome.png": b"\x89PNG\r\n\x1a\n\x00\xff\x80synthetic-test",
    })


@pytest.mark.parametrize("change", [{"host": "0.0.0.0"}, {"data_dir": "C:/Private"},
                                    {"api_key": "private"}, {"ffmpeg": "C:/my-tools/ffmpeg.exe"},
                                    {"ai": {"ollama_url": "https://external.example"}}])
def test_config_must_not_contain_personal_overrides(change):
    config = {"host": "127.0.0.1", "data_dir": "data", "ai": {"ollama_url": "http://127.0.0.1:11434"}}
    config.update(change)
    with pytest.raises(publish.PublishError, match="config.json"):
        publish.scan_payload({"config.json": json.dumps(config).encode()})


def test_generated_defaults_pass_and_no_real_environment_is_read():
    payload = publish.builder.collect_payload(publish.ROOT)
    publish.scan_payload(payload)
    assert "data/ai-connection.json" not in payload


@pytest.mark.parametrize("url", ["https://github.com/VanoPeradze/cutroom.git",
                                 "git@github.com:VanoPeradze/cutroom.git",
                                 "https://github.com/VanoPeradze/cutroom"])
def test_expected_github_urls(url):
    assert publish.parse_github_remote(url) == "VanoPeradze/cutroom"


@pytest.mark.parametrize("url", ["https://token@github.com/owner/repo.git", "https://github.com.evil.test/owner/repo",
                                 "file:///private/repo", "https://example.com/owner/repo", "--upload-pack=evil"])
def test_rejects_credential_urls_and_other_hosts(url):
    with pytest.raises(publish.PublishError):
        publish.parse_github_remote(url)


@pytest.mark.parametrize("change", [{"private": False}, {"visibility": "public"}, {"archived": True},
                                    {"disabled": True}, {"permissions": {"push": False}},
                                    {"permissions": None}, {"full_name": "somebody/else"}])
def test_private_repository_verification_fails_closed(tmp_path, monkeypatch, change):
    reply = {"full_name": publish.DEFAULT_REPO, "private": True, "permissions": {"push": True}}
    reply.update(change)
    monkeypatch.setattr(publish, "run", lambda *a, **k: json.dumps(reply).encode())
    with pytest.raises(publish.PublishError):
        publish.private_repository(tmp_path, publish.DEFAULT_REPO)


def test_private_repository_check_is_read_only(tmp_path, monkeypatch):
    calls = []

    def run(root, command):
        calls.append(command)
        return json.dumps({"full_name": publish.DEFAULT_REPO, "private": True, "permissions": {"push": True}}).encode()

    monkeypatch.setattr(publish, "run", run)
    publish.private_repository(tmp_path, publish.DEFAULT_REPO)
    assert calls == [["gh", "api", "--hostname", "github.com", "repos/VanoPeradze/cutroom"]]


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
    for field, value in (("user.name", "CUTROOM synthetic test"), ("user.email", "synthetic@example.invalid"),
                         ("commit.gpgsign", "false"), ("core.hooksPath", ".git/unused-test-hooks")):
        subprocess.run(["git", "-C", str(root), "config", field, value], check=True, capture_output=True)
    return root


def commit_fixture(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    publish.git(root, "add", "--", name)
    publish.git(root, "commit", "--quiet", "-m", "Synthetic test fixture")
    return publish.git(root, "rev-parse", "HEAD").decode().strip()


def test_history_scans_deleted_secrets(repository):
    commit_fixture(repository, "source.py", ("gsk_" + "A" * 40).encode())
    head = commit_fixture(repository, "source.py", b"safe after removal")
    with pytest.raises(publish.PublishError, match="API key"):
        publish.scan_history(repository, head)


def test_history_checks_private_alias_even_when_content_is_identical(repository):
    commit_fixture(repository, "README.md", b"same bytes")
    head = commit_fixture(repository, ".env", b"same bytes")
    with pytest.raises(publish.PublishError, match="historical path"):
        publish.scan_history(repository, head)


def test_clean_history_passes(repository):
    commit_fixture(repository, "README.md", b"safe first version")
    head = commit_fixture(repository, "README.md", b"safe second version")
    assert publish.scan_history(repository, head) == 2


def test_dirty_tree_blocks_before_any_remote_check(repository, monkeypatch):
    commit_fixture(repository, "README.md", b"safe")
    (repository / "unreviewed.txt").write_text("leave this alone")
    monkeypatch.setattr(publish, "private_repository", lambda *a: pytest.fail("must not contact GitHub yet"))
    with pytest.raises(publish.PublishError, match="uncommitted or untracked"):
        publish.git_plan(repository)
    assert (repository / "unreviewed.txt").read_text() == "leave this alone"


def test_default_action_does_not_package_or_publish(monkeypatch):
    calls = []
    monkeypatch.setattr(publish, "local_plan", lambda root: calls.append("plan"))
    monkeypatch.setattr(publish, "package", lambda *a: pytest.fail("no package"))
    monkeypatch.setattr(publish, "git_plan", lambda *a, **kw: pytest.fail("no remote"))
    assert publish.main([]) == 0
    assert calls == ["plan"]


def test_git_without_publish_only_does_preflight(monkeypatch):
    calls = []
    monkeypatch.setattr(publish, "git_plan", lambda *a, **k: calls.append(k))
    monkeypatch.setattr(publish, "publish_git", lambda *a, **k: pytest.fail("no push"))
    assert publish.main(["git"]) == 0
    assert calls == [{"allow_new_branch": False}]


@pytest.mark.parametrize("condition", ["normal", "new-branch", "new-approved", "diverged", "wrong-origin", "multiple-targets"])
def test_git_plan_checks_exact_target_and_fast_forward(tmp_path, monkeypatch, condition):
    calls = []
    target = "https://github.com/VanoPeradze/cutroom.git"

    def git(root, *args, **kwargs):
        calls.append(args)
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path).encode()
        if args[0] == "status":
            return b""
        if args[0] == "remote":
            if condition == "wrong-origin":
                return b"https://github.com/other/private.git"
            return (target + ("\n" + target if condition == "multiple-targets" else "")).encode()
        if args[0] == "symbolic-ref":
            return b"beta"
        if args[0] == "check-ref-format":
            return b""
        if args == ("rev-parse", "HEAD"):
            return b"a" * 40
        if args[0] == "ls-tree":
            return b"README.md\n"
        if args[0] == "ls-remote":
            return b"" if condition.startswith("new-") else b"b" * 40 + b"\trefs/heads/beta"
        if args[0] == "merge-base":
            if condition == "diverged":
                raise publish.PublishError("diverged")
            return b""
        pytest.fail(f"Unexpected command {args}")

    monkeypatch.setattr(publish, "git", git)
    monkeypatch.setattr(publish, "private_repository", lambda *a: None)
    monkeypatch.setattr(publish, "scan_history", lambda *a: 1)
    if condition in ("normal", "new-approved"):
        plan = publish.git_plan(tmp_path, allow_new_branch=condition == "new-approved")
        assert plan["head"] == "a" * 40 and plan["target"] == target
    else:
        with pytest.raises(publish.PublishError):
            publish.git_plan(tmp_path)
    assert not any(command[0] in {"push", "fetch", "add", "commit", "merge"} for command in calls)


def test_package_scans_exact_archive_snapshot_before_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(publish, "local_plan", lambda root: {})
    monkeypatch.setattr(publish.builder, "build_package", lambda root, output: output / "candidate.zip")
    monkeypatch.setattr(publish.builder, "verify_package", lambda path: {"build_id": "CUTROOM-test", "files": {"source.py": "unused"}})

    class Archive:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, name):
            return ("gsk_" + "A" * 40).encode()

    monkeypatch.setattr(publish.zipfile, "ZipFile", Archive)
    with pytest.raises(publish.PublishError, match="API key"):
        publish.package(tmp_path)
    assert not (tmp_path / "dist").exists()


def test_subprocess_failure_never_echoes_remote_diagnostics(tmp_path, monkeypatch):
    private_diagnostic = b"credential-bearing URL or remote response"
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", private_diagnostic))
    with pytest.raises(publish.PublishError) as caught:
        publish.run(tmp_path, ["git", "ls-remote", "origin"])
    assert "credential-bearing" not in str(caught.value)


def test_expo_stops_without_running_commands(monkeypatch, capsys):
    monkeypatch.setattr(publish, "run", lambda *a, **k: pytest.fail("no Expo commands"))
    assert publish.main(["expo"]) == 1
    assert "NOT configured" in capsys.readouterr().err


@pytest.mark.parametrize("scenario", ["tests-fail", "wrong-confirmation", "state-changed", "headless", "success"])
def test_git_publish_requires_tests_confirmation_and_unchanged_state(tmp_path, monkeypatch, scenario):
    calls = []
    original = {"repo": publish.DEFAULT_REPO, "branch": "beta", "head": "a" * 40,
                "target": "https://github.com/VanoPeradze/cutroom.git"}
    snapshots = iter([original, {**original, "head": "b" * 40} if scenario == "state-changed" else original])
    monkeypatch.setattr(publish, "git_plan", lambda *a, **k: next(snapshots))
    monkeypatch.setattr(publish.sys.stdin, "isatty", lambda: scenario != "headless")
    monkeypatch.setattr(publish.shutil, "which", lambda executable: "node")
    monkeypatch.setattr(publish.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1 if scenario == "tests-fail" else 0))
    phrase = f"PUSH {publish.DEFAULT_REPO} beta {'a' * 12}"
    monkeypatch.setattr("builtins.input", lambda *a: "no" if scenario == "wrong-confirmation" else phrase)
    monkeypatch.setattr(publish, "git", lambda root, *args, **kw: calls.append(args))
    if scenario == "success":
        publish.publish_git(tmp_path, publish.DEFAULT_REPO)
        assert calls == [("push", "--porcelain", "--no-follow-tags", "--recurse-submodules=no",
                          original["target"], f"{'a' * 40}:refs/heads/beta")]
    else:
        with pytest.raises(publish.PublishError):
            publish.publish_git(tmp_path, publish.DEFAULT_REPO)
        assert calls == []


def test_bat_is_small_ascii_launcher_not_a_shell_publish_script():
    path = publish.ROOT / "PUBLISH.bat"
    source = path.read_text(encoding="ascii")
    assert b"\n" not in path.read_bytes().replace(b"\r\n", b"")
    assert '"scripts\\publish.py" %*' in source
    assert "DisableDelayedExpansion" in source
    assert "git add" not in source and "git push" not in source
    assert "pip install" not in source and "npx" not in source
