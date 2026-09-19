"""Prepare a clean tester ZIP or deliberately push a reviewed, private Git branch.

Default invocation is local/read-only. This is not a hosted CUTROOM deployment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import build_test_package as builder

DEFAULT_REPO = "VanoPeradze/cutroom"
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_HISTORY_BYTES = 128 * 1024 * 1024
MAX_HISTORY_OBJECTS = 20000
PRIVATE_PARTS = {"data", ".git", ".venv", ".tools", "dist", "node_modules", "__pycache__",
                 ".pytest_cache", ".codex", ".agents", "models", "validation-work"}
PRIVATE_FILES = {".runtime-paths.cmd", ".setup-complete", ".verified", "ai-connection.json",
                 "validation-report.json", "validation_report_he.md"}
PRIVATE_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".log", ".mp4", ".mov", ".mkv",
                    ".avi", ".webm", ".wav", ".mp3", ".m4a", ".flac", ".gguf",
                    ".safetensors", ".pt", ".pth", ".zip", ".exe", ".dll", ".sqlite", ".db"}
SECRET_PATTERNS = (
    ("provider API key", re.compile(rb"\b(?:gsk_[A-Za-z0-9]{24,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,})\b")),
    ("GitHub token", re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})\b")),
    ("Google API key", re.compile(rb"\bAIza[A-Za-z0-9_-]{30,}\b")),
    ("AWS access key", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("private key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
)
LITERAL_CREDENTIAL = re.compile(
    rb"(?:api[_-]?key|access[_-]?token|client[_-]?secret|password)[\"']?\s*[:=]\s*[\"']([^\"'\r\n]{20,})[\"']", re.I
)


class PublishError(RuntimeError):
    """A safe, actionable failure; never includes credentials or remote responses."""


def run(root: Path, command: list[str], *, input_bytes: bytes | None = None,
        timeout: int = 60) -> bytes:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GH_PROMPT_DISABLED="1")
    try:
        result = subprocess.run(command, cwd=root, input=input_bytes, capture_output=True,
                                timeout=timeout, check=False, env=env)
    except FileNotFoundError as exc:
        raise PublishError(f"{command[0]} was not found. Install/configure it yourself, then retry.") from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublishError(f"{command[0]} could not complete. Check your environment/network and retry.") from exc
    if result.returncode:
        # Git/HTTP diagnostics can contain credential-bearing URLs or response bodies.
        raise PublishError(f"{command[0]} {command[1]} failed (exit {result.returncode}). "
                           "Check access, authentication and repository state. Nothing is retried automatically.")
    return result.stdout


def git(root: Path, *args: str, **kwargs) -> bytes:
    return run(root, ["git", *args], **kwargs)


def path_issue(name: str) -> str | None:
    path = PurePosixPath(name)
    parts = path.parts
    if not parts or name != path.as_posix() or path.is_absolute() or ".." in parts:
        return "non-canonical path"
    if any(char in name for char in ('\\', ':', '"')) or any(ord(char) < 32 for char in name):
        return "unsafe or ambiguous path"
    lowered = [part.lower() for part in parts]
    if any(part in PRIVATE_PARTS or part == ".env" or part.startswith(".env.") for part in lowered):
        return "private/runtime directory or environment file"
    if lowered[-1] in PRIVATE_FILES or path.suffix.lower() in PRIVATE_SUFFIXES:
        return "private/runtime file or unapproved media"
    return None


def scan_payload(payload: dict[str, bytes]) -> None:
    """Conservative guardrails, not a replacement for human/security review."""
    for name, data in sorted(payload.items()):
        problem = path_issue(name)
        if problem:
            raise PublishError(f"Blocked {name!r}: {problem}.")
        if len(data) > MAX_FILE_BYTES:
            raise PublishError(f"Blocked {name!r}: unexpectedly large source file.")
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(data):
                raise PublishError(f"Blocked {name!r}: possible {label}. Review privately; the value is not printed.")
        for match in LITERAL_CREDENTIAL.finditer(data):
            value = match.group(1).strip().lower()
            if not value.startswith((b"test-", b"example", b"fake-", b"dummy-", b"your", b"<")):
                raise PublishError(f"Blocked {name!r}: possible hard-coded credential. Review privately.")
        if name == "config.json":
            validate_config(data)


def validate_config(data: bytes) -> None:
    try:
        config = json.loads(data)
        if not isinstance(config, dict):
            raise ValueError("not an object")
        if config.get("host") != "127.0.0.1" or config.get("data_dir") != "data":
            raise ValueError("not portable loopback defaults")
        ai = config.get("ai", {})
        if not isinstance(ai, dict) or ai.get("ollama_url") != "http://127.0.0.1:11434":
            raise ValueError("custom AI address")

        def inspect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if re.search(r"(?:api.?key|token|secret|password|cloud_connection)", key, re.I) and item:
                        raise ValueError("personal connection settings")
                    inspect(item)
            elif isinstance(value, list):
                for item in value:
                    inspect(item)
            elif isinstance(value, str) and re.search(r"^(?:[A-Za-z]:[\\/]|/(?:Users|home)/|\\\\)", value):
                raise ValueError("machine-specific path")

        inspect(config)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PublishError("Blocked config.json: it must contain shareable application defaults, "
                           "not personal paths, keys or connection settings.") from exc


def local_plan(root: Path) -> dict[str, bytes]:
    payload = builder.collect_payload(root)
    scan_payload(payload)
    print("CUTROOM publishing preflight - LOCAL ONLY\n")
    print(f"Clean package candidate: {len(payload)} files, {sum(map(len, payload.values())) / 1024 / 1024:.2f} MiB before ZIP.")
    print("Exact candidate inventory (current source files; config.json is generated from defaults):")
    for name in sorted(payload):
        print(f"  {name} ({len(payload[name])} bytes)")
    try:
        changes = git(root, "status", "--porcelain=v1", "--untracked-files=all").decode("utf-8", errors="replace").strip()
        print("\nGit working tree: " + ("has changes; push is blocked until reviewed and committed." if changes else "clean."))
    except PublishError:
        print("\nNo usable Git checkout. A clean tester ZIP can still be built.")
    print("\nNo uploads, installs, commits, tests or account changes were performed.")
    print("Automated guardrails are not a security audit or proof of editing quality.")
    print("Next: PUBLISH.bat package       - create a local tester ZIP")
    print("      PUBLISH.bat git           - inspect a private GitHub push (read-only network checks)")
    print("      PUBLISH.bat git --publish - tests + explicit confirmation before one branch push")
    print("Expo hosting is not configured for this Python/FFmpeg app. See docs/PUBLISHING.md.")
    return payload


def package(root: Path) -> Path:
    local_plan(root)
    output = root / "dist"
    if output.is_symlink() or (output.exists() and builder._is_link(output)):
        raise PublishError("dist must be a real local directory, not a link/junction.")
    if not output.resolve().is_relative_to(root.resolve()):
        raise PublishError("Package output must stay inside this checkout's dist directory.")
    # Scan the exact archive snapshot as well as the earlier plan; never expose an unscanned ZIP.
    with tempfile.TemporaryDirectory(prefix="cutroom-publish-") as temporary:
        staged = builder.build_package(root, Path(temporary))
        manifest = builder.verify_package(staged)
        with zipfile.ZipFile(staged) as archive:
            payload = {name: archive.read(manifest["build_id"] + "/" + name) for name in manifest["files"]}
        scan_payload(payload)
        output.mkdir(exist_ok=True)
        target = output / staged.name
        checksum = target.with_suffix(".zip.sha256")
        if target.exists() or checksum.exists():
            raise PublishError("A package with this timestamp already exists. Wait a second and retry; nothing is overwritten.")
        with staged.open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination)
        with checksum.open("x", encoding="ascii") as destination:
            destination.write(f"{hashlib.sha256(target.read_bytes()).hexdigest()}  {target.name}\n")
    print(f"\nCreated: {target}")
    print(f"Checksum: {checksum}")
    print("Local files only. No upload. ZIP contains current source, not model weights or installed runtimes.")
    print("Test the extracted ZIP on a second PC before sharing; startup needs internet for initial dependencies.")
    return target


def parse_github_remote(url: str) -> str:
    match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", url)
    if not match:
        raise PublishError("origin must be a credential-free github.com HTTPS or SSH repository URL.")
    return match.group(1)


def private_repository(root: Path, repo: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise PublishError("Repository must use owner/name format.")
    raw = run(root, ["gh", "api", "--hostname", "github.com", f"repos/{repo}"])
    try:
        details = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise PublishError("Could not verify GitHub repository visibility.") from exc
    if not isinstance(details, dict) or str(details.get("full_name", "")).lower() != repo.lower():
        raise PublishError("GitHub returned a different repository. Publishing stopped.")
    if details.get("private") is not True or details.get("visibility", "private") != "private":
        raise PublishError("Publishing requires an existing PRIVATE repository. Visibility will not be changed.")
    if details.get("archived") or details.get("disabled"):
        raise PublishError("Repository is archived or disabled.")
    permissions = details.get("permissions")
    if not isinstance(permissions, dict) or permissions.get("push") is not True:
        raise PublishError("The current GitHub account does not have verified push permission.")


def scan_history(root: Path, head: str) -> int:
    """Inspect all reachable object paths/content, including files deleted before HEAD."""
    commits = git(root, "rev-list", head).decode("ascii").splitlines()
    if len(commits) > 256:
        raise PublishError("History exceeds the built-in commit limit; use a dedicated secret audit before publishing.")
    aliases: dict[str, set[str]] = {}
    # rev-list --objects alone reports only one path per object. A private .env
    # file may share bytes with a harmless filename, so inspect every tree too.
    for commit in commits:
        entries = git(root, "ls-tree", "-r", "-z", commit).split(b"\0")
        for entry in entries:
            if not entry:
                continue
            metadata, name_bytes = entry.split(b"\t", 1)
            mode, kind, oid_bytes = metadata.split()
            name = name_bytes.decode("utf-8", errors="strict")
            if mode not in (b"100644", b"100755") or kind != b"blob":
                raise PublishError(f"Blocked historical path {name!r}: linked file or submodule needs separate review.")
            problem = path_issue(name)
            if problem:
                raise PublishError(f"Blocked historical path {name!r}: {problem}. Review history before pushing.")
            aliases.setdefault(oid_bytes.decode("ascii"), set()).add(name)
    lines = git(root, "rev-list", "--objects", head).decode("utf-8", errors="strict").splitlines()
    if len(lines) > MAX_HISTORY_OBJECTS:
        raise PublishError("History exceeds the built-in review limit; use a dedicated secret audit before publishing.")
    names = {}
    for line in lines:
        oid, _, name = line.partition(" ")
        if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", oid):
            raise PublishError("Unexpected Git object identifier.")
        if name:
            problem = path_issue(name)
            if problem:
                raise PublishError(f"Blocked historical path {name!r}: {problem}. Review history before pushing.")
        names[oid] = name
    check = git(root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                input_bytes=("\n".join(names) + "\n").encode("ascii"))
    blobs, total = [], 0
    for line in check.decode("ascii").splitlines():
        oid, kind, size_text = line.split()
        size = int(size_text)
        if kind != "blob":
            continue
        if size > MAX_FILE_BYTES:
            raise PublishError(f"Blocked historical file {names[oid]!r}: larger than the source-file limit.")
        total += size
        if total > MAX_HISTORY_BYTES:
            raise PublishError("History exceeds the built-in byte limit; use a dedicated secret audit.")
        blobs.append((oid, size))
    if not blobs:
        raise PublishError("No committed source files to publish.")
    contents = git(root, "cat-file", "--batch", input_bytes=("\n".join(oid for oid, _ in blobs) + "\n").encode("ascii"))
    cursor = 0
    for oid, expected_size in blobs:
        end = contents.find(b"\n", cursor)
        if contents[cursor:end] != f"{oid} blob {expected_size}".encode("ascii"):
            raise PublishError("Git object scan was incomplete.")
        start = end + 1
        data = contents[start:start + expected_size]
        if len(data) != expected_size or contents[start + expected_size:start + expected_size + 1] != b"\n":
            raise PublishError("Git object data was incomplete.")
        scan_payload({name: data for name in aliases.get(oid, {names[oid] or f"unnamed-{oid}"})})
        cursor = start + expected_size + 1
    return len(blobs)


def git_plan(root: Path, repo: str = DEFAULT_REPO, *, allow_new_branch: bool = False) -> dict[str, str]:
    top = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if top != root.resolve():
        raise PublishError("Run PUBLISH from the CUTROOM repository root, not a parent repository.")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all").strip():
        raise PublishError("Git has uncommitted or untracked files. Review and commit only intended source files first. "
                           "This script never stages, commits, stashes or deletes your work.")
    urls = []
    for options in (("remote", "get-url", "--all", "origin"), ("remote", "get-url", "--push", "--all", "origin")):
        current = git(root, *options).decode().strip().splitlines()
        if len(current) != 1 or parse_github_remote(current[0]).lower() != repo.lower():
            raise PublishError("origin does not point exclusively to the expected repository. No remote was changed.")
        urls.extend(current)
    private_repository(root, repo)
    branch = git(root, "symbolic-ref", "--quiet", "--short", "HEAD").decode().strip()
    git(root, "check-ref-format", "refs/heads/" + branch)
    head = git(root, "rev-parse", "HEAD").decode().strip()
    count = scan_history(root, head)
    files = git(root, "ls-tree", "--name-only", "-r", head).decode().splitlines()
    # A single explicit refspec and a validated URL cannot pick up additional configured push refs.
    target = urls[-1]
    remote = git(root, "ls-remote", "--refs", target, "refs/heads/" + branch).decode().strip()
    if remote:
        remote_head, remote_ref = remote.split()
        if remote_ref != "refs/heads/" + branch:
            raise PublishError("Remote branch response did not match the intended target.")
        try:
            git(root, "merge-base", "--is-ancestor", remote_head, head)
        except PublishError as exc:
            raise PublishError("Remote branch is ahead/diverged, or its commit is not available locally. "
                               "Fetch and review it yourself; no force push or automatic merge is performed.") from exc
    elif not allow_new_branch:
        raise PublishError("This branch does not exist remotely. Re-run with --new-branch only if you intend to create it.")
    print(f"Private GitHub target: {repo}\nBranch: {branch}\nExact commit: {head}")
    print(f"Scanned {count} historical file versions; {len(files)} files at HEAD:")
    for name in files:
        print("  " + name)
    print("One branch only. No tags, release, ZIP upload, website deployment or visibility change.")
    print("No staging, commit, force push, credentials setup or automatic repository creation.")
    print("Guardrails cannot detect every secret. Review commit history and media rights yourself.")
    return {"repo": repo, "branch": branch, "head": head, "target": target}


def publish_git(root: Path, repo: str, *, allow_new_branch: bool = False) -> None:
    before = git_plan(root, repo, allow_new_branch=allow_new_branch)
    if not sys.stdin.isatty():
        raise PublishError("Publishing requires an interactive terminal and exact typed confirmation.")
    if not shutil.which("node"):
        raise PublishError("Node.js is required to run the frontend regression tests before publishing.")
    print("\nRunning local regression tests before confirmation. This does not test real cloud keys or a clean-PC installation.", flush=True)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=root, check=False)
    if result.returncode:
        raise PublishError("Regression tests failed. No push attempted.")
    phrase = f"PUSH {before['repo']} {before['branch']} {before['head'][:12]}"
    print("\nOnly type the following if this is the reviewed commit and intended PRIVATE repository:")
    print(phrase)
    if input("> ").strip() != phrase:
        raise PublishError("Confirmation did not match. No push attempted.")
    # Re-check after tests/user review; never publish a different commit or changed destination.
    after = git_plan(root, repo, allow_new_branch=allow_new_branch)
    if after != before:
        raise PublishError("Repository state changed during review. Start again; no push attempted.")
    print("Pushing the explicitly confirmed commit...", flush=True)
    git(root, "push", "--porcelain", "--no-follow-tags", "--recurse-submodules=no",
        before["target"], f"{before['head']}:refs/heads/{before['branch']}", timeout=180)
    print("Push completed. Repository visibility was not changed. This does not deploy a running website.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="action")
    subcommands.add_parser("plan", help="Local package inventory and guardrails; no writes or network")
    subcommands.add_parser("package", help="Create a clean local ZIP; no upload")
    git_parser = subcommands.add_parser("git", help="Read-only GitHub/branch preflight unless --publish is supplied")
    git_parser.add_argument("--repo", default=DEFAULT_REPO, help="Expected existing PRIVATE GitHub owner/repo")
    git_parser.add_argument("--new-branch", action="store_true", help="Explicitly allow creation of the current branch on origin")
    git_parser.add_argument("--publish", action="store_true", help="Run tests and request exact typed confirmation before pushing")
    subcommands.add_parser("expo", help="Explain why this build is not an Expo deployment")
    args = parser.parse_args(argv)
    try:
        if args.action in (None, "plan"):
            local_plan(ROOT)
        elif args.action == "package":
            package(ROOT)
        elif args.action == "git":
            if args.publish:
                publish_git(ROOT, args.repo, allow_new_branch=args.new_branch)
            else:
                git_plan(ROOT, args.repo, allow_new_branch=args.new_branch)
                print("\nRead-only preflight complete. No push was performed. Use git --publish to proceed deliberately.")
        elif args.action == "expo":
            raise PublishError("Expo deployment is NOT configured: CUTROOM currently runs Python, FFmpeg and local AI. "
                               "EAS Hosting expects an Expo/React web build and cannot run this backend as-is. "
                               "No Expo command, installation, upload or billable resource was created. See docs/PUBLISHING.md.")
    except (PublishError, OSError, ValueError, zipfile.BadZipFile) as exc:
        print(f"\nStopped: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. If interrupted during a push, check GitHub before trying again.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
