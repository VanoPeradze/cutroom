"""Verify an explicit, unpublished Windows/combined review pair entirely offline.

This is a separate review gate. It never changes an approved release pin, builds
an archive, imports application/build code, installs, or establishes native QA.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
TEXT_SUFFIXES = {".cjs", ".command", ".css", ".csv", ".html", ".ini", ".js", ".json", ".md", ".mjs", ".py", ".sh", ".sha256", ".svg", ".toml", ".txt", ".xml", ".yaml", ".yml"}
TEXT_NAMES = {".editorconfig", ".gitattributes", ".gitignore", ".npmignore", ".nvmrc", "Dockerfile", "LICENSE"}
MAC_OVERLAY = {
    "packaging/mac/START CUTROOM.command": "mac/START CUTROOM.command",
    "packaging/mac/START HERE.html": "mac/START HERE.html",
    "packaging/mac/setup_macos.sh": "mac/App/setup_macos.sh",
    "packaging/mac/run_macos.sh": "mac/App/run_macos.sh",
    "packaging/mac/preflight_macos.py": "mac/App/preflight_macos.py",
    "packaging/mac/constraints-macos.txt": "mac/App/constraints-macos.txt",
    "docs/MAC_BETA.md": "mac/App/docs/MAC_BETA.md",
}
NOT_INCLUDED = ["user media", "projects", "logs", "local config", "runtimes", "models"]
FORBIDDEN_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".wav", ".mp3", ".ogg", ".gguf", ".safetensors", ".onnx", ".log", ".pyc", ".zip"}


class QualificationError(ValueError):
    """The explicit pair cannot pass the private review source gate."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualificationError(message)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def parse_json(data: bytes | str) -> dict:
    try:
        value = json.loads(data, object_pairs_hook=_object,
                           parse_constant=lambda value: (_ for _ in ()).throw(QualificationError("Non-finite JSON number")))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise QualificationError("Invalid JSON document") from error
    require(isinstance(value, dict), "JSON document must be an object")
    return value


def _record(record: dict) -> None:
    require(isinstance(record, dict) and set(record) == {
        "schema_version", "kind", "published", "qualified_for_release", "native_candidate_status", "source", "windows", "combined"
    }, "Unexpected review record fields")
    require(type(record["schema_version"]) is int and record["schema_version"] == 1, "Unsupported review record schema")
    require(record["kind"] == "cutroom-private-review-candidate", "Record must explicitly select private review mode")
    require(record["published"] is False and record["qualified_for_release"] is False
            and record["native_candidate_status"] == "pending", "Review record cannot assert publication or native qualification")
    source = record["source"]
    require(isinstance(source, dict) and set(source) == {"commit", "tree", "archive_sha256", "archive_bytes", "files"}, "Invalid source review pin")
    for key in ("commit", "tree"):
        require(isinstance(source[key], str) and re.fullmatch(r"[a-f0-9]{40}", source[key]) is not None, "Source requires full Git identities")
    for key in ("archive_bytes", "files"):
        require(type(source[key]) is int and source[key] > 0, "Invalid source size/count")
    require(source["archive_bytes"] <= MAX_ARCHIVE_BYTES, "Source archive is too large")
    require(isinstance(source["archive_sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", source["archive_sha256"]) is not None, "Invalid source archive hash")
    for platform in ("windows", "combined"):
        pin = record[platform]
        require(isinstance(pin, dict) and set(pin) == {"bytes", "sha256", "manifest_sha256", "build_id"}, "Invalid archive review pin")
        require(type(pin["bytes"]) is int and 0 < pin["bytes"] <= MAX_ARCHIVE_BYTES, "Invalid archive byte size")
        for key in ("sha256", "manifest_sha256"):
            require(isinstance(pin[key], str) and re.fullmatch(r"[a-f0-9]{64}", pin[key]) is not None, "Invalid archive/manifest hash")
        require(isinstance(pin["build_id"], str) and re.fullmatch(r"CUTROOM-[A-Za-z0-9.-]+", pin["build_id"]) is not None, "Invalid pinned build ID")


def _linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _read(path: Path) -> bytes:
    require(path.is_file() and not _linked(path), "Missing or linked input: " + path.name)
    require(path.stat().st_size <= MAX_ARCHIVE_BYTES, "Input exceeds archive size limit")
    return path.read_bytes()


def _zip(data: bytes, *, directories: bool = False) -> tuple[dict[str, bytes], dict[str, int], bytes]:
    files, modes, seen = {}, {}, set()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            require(0 < len(bundle.infolist()) <= 10000, "Empty or oversized ZIP inventory")
            require(sum(info.file_size for info in bundle.infolist()) <= MAX_ARCHIVE_BYTES, "Expanded ZIP exceeds size limit")
            for info in bundle.infolist():
                raw = info.filename
                name = raw[:-1] if info.is_dir() else raw
                path = PurePosixPath(name)
                require(info.orig_filename == raw and bool(name) and not path.is_absolute()
                        and "\\" not in name and ":" not in name and ".." not in path.parts
                        and "." not in name.split("/") and name == path.as_posix()
                        and not any(ord(c) < 32 for c in name), "Unsafe or normalized ZIP path")
                require(name.casefold() not in seen, "Duplicate/case-colliding ZIP entry")
                seen.add(name.casefold())
                mode = info.external_attr >> 16
                require(not (mode & 0o7000), "ZIP entry has special permission bits")
                require(not info.flag_bits & 1, "Encrypted ZIP input")
                require(info.compress_type in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}, "Unsupported ZIP compression")
                if info.is_dir():
                    require(directories and stat.S_IFMT(mode) in (0, stat.S_IFDIR), "Unexpected directory ZIP entry")
                else:
                    require(stat.S_IFMT(mode) in (0, stat.S_IFREG), "Linked or special ZIP entry")
                    files[name], modes[name] = bundle.read(info), mode
            folded = {name.casefold() for name in files}
            require(not any(parent.as_posix().casefold() in folded for name in files
                            for parent in PurePosixPath(name).parents if parent.as_posix() != "."), "ZIP file/directory collision")
            return files, modes, bundle.comment
    except (zipfile.BadZipFile, EOFError, RuntimeError) as error:
        raise QualificationError("Invalid ZIP or CRC") from error


def _git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args], input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    require(result.returncode == 0, "Local Git source query failed")
    return result.stdout


def _text_allowed(name: str, data: bytes) -> bool:
    path = PurePosixPath(name)
    if path.suffix.lower() in {".bat", ".ps1"} or b"\0" in data:
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
        return False
    try:
        data.decode("utf-8")
    except UnicodeError:
        return False
    return True


def _source_equal(name: str, left: bytes, right: bytes) -> bool:
    return left == right or (_text_allowed(name, left) and _text_allowed(name, right)
                             and left.replace(b"\r\n", b"\n") == right.replace(b"\r\n", b"\n"))


def _bind_git(repo: Path, source: dict[str, bytes], pin: dict) -> dict:
    commit = _git(repo, "rev-parse", "--verify", pin["commit"] + "^{commit}").decode("ascii").strip()
    tree = _git(repo, "rev-parse", pin["commit"] + "^{tree}").decode("ascii").strip()
    require(commit == pin["commit"] and tree == pin["tree"], "Pinned Git commit/tree mismatch")
    entries = {}
    for entry in _git(repo, "ls-tree", "-r", "-z", "--full-tree", commit).split(b"\0"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode("ascii").split()
        require(mode in {"100644", "100755"} and kind == "blob", "Linked/non-blob Git source")
        entries[name.decode("utf-8")] = oid
    require(set(entries) == set(source) and len(source) == pin["files"], "Frozen source inventory differs from pinned Git tree")
    batch = _git(repo, "cat-file", "--batch", data=b"".join(oid.encode("ascii") + b"\n" for oid in entries.values()))
    offset, exact = 0, 0
    for name, oid in entries.items():
        end = batch.index(b"\n", offset)
        got, kind, amount = batch[offset:end].decode("ascii").split()
        size = int(amount)
        blob = batch[end + 1:end + 1 + size]
        offset = end + size + 2
        require(got == oid and kind == "blob" and len(blob) == size, "Invalid Git blob response")
        object_id = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0" + blob, usedforsecurity=False).hexdigest()
        require(object_id == oid, "Git blob content does not match its object identity")
        require(_source_equal(name, source[name], blob), "Frozen source differs from Git blob: " + name)
        exact += source[name] == blob
    require(offset == len(batch), "Unconsumed Git blob response")
    return {"files": len(source), "git_blob_exact": exact, "declared_line_ending_only": len(source) - exact}


def _literal(data: bytes, name: str):
    try:
        for node in ast.parse(data).body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            if any(isinstance(target, ast.Name) and target.id == name for target in targets):
                return ast.literal_eval(node.value)
    except (SyntaxError, ValueError, TypeError) as error:
        raise QualificationError("Invalid frozen AST literal: " + name) from error
    raise QualificationError("Missing frozen AST literal: " + name)


def _payload_inputs(source: dict[str, bytes]) -> tuple[set[str], dict[str, set[str]]]:
    builder = source.get("scripts/build_test_package.py", b"")
    required = set()
    for name in ("ROOT_FILES", "SUPPORT_FILES", "DOC_FILES", "IMAGE_FILES", "PACKAGING_FILES"):
        values = _literal(builder, name)
        require(isinstance(values, (tuple, list)) and all(isinstance(value, str) for value in values), "Invalid frozen input allowlist")
        required.update(values)
    trees = _literal(builder, "SOURCE_TREES")
    require(isinstance(trees, dict) and all(isinstance(name, str) and isinstance(suffixes, set)
            and all(isinstance(suffix, str) for suffix in suffixes) for name, suffixes in trees.items()), "Invalid frozen source trees")
    for name in source:
        path = PurePosixPath(name)
        if path.parts[0] in trees and path.suffix.lower() in trees[path.parts[0]] and not any(part.startswith(".") or part == "__pycache__" for part in path.parts[1:]):
            required.add(name)
    require(required <= source.keys(), "Frozen source is missing a required package input")
    require(_literal(source.get("scripts/build_universal_package.py", b""), "MAC_OVERLAY") == MAC_OVERLAY, "Frozen Mac overlay policy differs")
    require(MAC_OVERLAY.keys() <= source.keys(), "Frozen source is missing a Mac overlay")
    return required, trees


def _report_policy(record: dict, source_archive: Path) -> tuple[set[str], dict[str, set[str]]]:
    """Read output protections from the exact frozen policy, without executing it."""
    _record(record)
    data = _read(source_archive)
    pin = record["source"]
    require(len(data) == pin["archive_bytes"] and sha(data) == pin["archive_sha256"], "Pinned source archive size/hash mismatch")
    source, _, comment = _zip(data, directories=True)
    require(comment == pin["commit"].encode("ascii") and len(source) == pin["files"], "Invalid frozen source policy identity")
    return _payload_inputs(source)


def _report_path(output: Path, repo: Path, inputs: tuple[Path, ...], required: set[str], trees: dict,
                 *, previous: tuple[Path, Path] | None = None) -> tuple[Path, Path]:
    """Keep report creation outside every frozen product source tree and input."""
    require(output.suffix.lower() == ".json", "--output must be a new .json report")
    require(not os.path.lexists(output), "--output must be a new file")
    target, root = output.resolve(), repo.resolve()
    require(not os.path.lexists(target), "--output must be a new file")
    require(target.parent.is_dir(), "--output parent directory must already exist")
    require(target.suffix.lower() == ".json", "--output must resolve to a .json report")
    require(target not in {path.resolve() for path in inputs}, "--output cannot replace a verification input")
    protected = {(root / name).resolve() for name in required | MAC_OVERLAY.keys()}
    require(target not in protected, "--output cannot be a packaged source/overlay file")
    for name in trees:
        directory = (root / name).resolve()
        require(target != directory and not target.is_relative_to(directory), "--output cannot be inside a packaged source tree")
    require(previous is None or (target, root) == previous, "Report/source path changed during qualification")
    return target, root


def _current_inputs(repo: Path, required: set[str], trees: dict, source: dict[str, bytes]) -> dict[str, bytes]:
    root = repo.resolve()
    require(root.is_dir() and not _linked(repo), "Current source root is linked/missing")
    result = {}

    def read(name: str) -> bytes:
        path = root.joinpath(*PurePosixPath(name).parts)
        require(path.resolve().is_relative_to(root), "Current input escapes source root")
        current = path
        while current != root:
            require(current.exists() and not _linked(current), "Missing or linked current input: " + name)
            current = current.parent
        return _read(path)

    for name in required | MAC_OVERLAY.keys():
        result[name] = read(name)

    def walk(directory: Path, suffixes: set[str]) -> None:
        require(directory.is_dir() and not _linked(directory), "Missing or linked current source tree")
        for path in sorted(directory.iterdir()):
            if path.name.startswith(".") or path.name == "__pycache__":
                continue
            require(not _linked(path), "Linked current source tree entry")
            if path.is_dir():
                walk(path, suffixes)
            elif path.suffix.lower() in suffixes:
                name = path.relative_to(root).as_posix()
                result[name] = read(name)
    for name, suffixes in trees.items():
        walk(root / name, suffixes)
    require(set(result) == required | MAC_OVERLAY.keys(), "Current package input inventory changed")
    for name, data in result.items():
        require(_source_equal(name, data, source[name]), "Current package input changed: " + name)
    return result


def _manifest(files: dict[str, bytes], name: str, pin: dict) -> dict:
    require(name in files and sha(files[name]) == pin["manifest_sha256"], "Pinned manifest hash mismatch")
    manifest = parse_json(files[name])
    require(manifest.get("build_id") == pin["build_id"], "Pinned manifest build ID mismatch")
    inventory = manifest.get("files")
    require(isinstance(inventory, dict) and bool(inventory) and set(files) == set(inventory) | {name}
            and name not in inventory, "Manifest inventory mismatch")
    for path, digest in inventory.items():
        require(isinstance(digest, str) and re.fullmatch(r"[a-f0-9]{64}", digest) is not None
                and sha(files[path]) == digest, "Manifest payload checksum mismatch: " + path)
    return manifest


def qualify(record: dict, windows_zip: Path, combined_zip: Path, source_archive: Path, repo: Path) -> dict:
    """Pure read-only qualification. The supplied record is an explicit trust anchor."""
    _record(record)
    archive_data = {}
    for name, path, pin in (("source", source_archive, record["source"]), ("windows", windows_zip, record["windows"]), ("combined", combined_zip, record["combined"])):
        data = _read(path)
        size = pin["archive_bytes"] if name == "source" else pin["bytes"]
        digest = pin["archive_sha256"] if name == "source" else pin["sha256"]
        require(len(data) == size and sha(data) == digest, "Pinned " + name + " archive size/hash mismatch")
        archive_data[name] = data
    source, _, comment = _zip(archive_data["source"], directories=True)
    require(comment == record["source"]["commit"].encode("ascii"), "Source archive commit comment mismatch")
    binding = _bind_git(repo, source, record["source"])
    required, trees = _payload_inputs(source)
    current = _current_inputs(repo, required, trees, source)
    windows, _, _ = _zip(archive_data["windows"])
    combined, modes, _ = _zip(archive_data["combined"])
    wm = _manifest(windows, "App/TEST_BUILD.json", record["windows"])
    cm = _manifest(combined, "mac/App/TEST_BUILD.json", record["combined"])
    version = _literal(source["cutroom/__init__.py"], "__version__")
    label = _literal(source["cutroom/__init__.py"], "__version_label__")
    for manifest in (wm, cm):
        require(manifest.get("app_version") == version and manifest.get("app_version_label") == label
                and manifest.get("kind") == "public-source-beta" and manifest.get("not_included") == NOT_INCLUDED,
                "Package version/privacy metadata differs from frozen source")
    require(all(wm.get(key) == value for key, value in {"layout": "windows-app-folder-v1", "archive_root": "", "source_directory": "App", "launcher": "START CUTROOM.bat", "help": "START HERE.html", "configuration": "fresh application defaults, loopback only"}.items()), "Windows layout/default metadata mismatch")
    require(wm.get("clean_machine_install_verified") is False and cm.get("mac_manual_install_verified") is False,
            "Package must retain unverified installation flags")
    require(cm.get("layout") == "windows-mac-folders-v1" and cm.get("windows_files_unchanged") is True
            and cm.get("windows_baseline_sha256") == record["windows"]["sha256"] and "documentation_revision" not in cm,
            "Combined review provenance mismatch")
    expected = {"App/" + name: source[name] for name in required}
    defaults = copy.deepcopy(_literal(source["cutroom/config.py"], "DEFAULTS"))
    require(isinstance(defaults, dict) and isinstance(defaults.get("ai"), dict), "Invalid frozen default configuration")
    defaults.update(host="127.0.0.1", port=8765, data_dir="data", open_browser=True)
    defaults["ai"].update(ollama_url="http://127.0.0.1:11434", download_models_on_setup=False)
    expected["App/config.json"] = (json.dumps(defaults, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    template = _literal(source["scripts/build_test_package.py"], "START_TEXT")
    expected["App/START_TESTING.txt"] = template.format(version_label=label).replace("\n", "\r\n").encode("ascii")
    for name in _literal(source["scripts/build_test_package.py"], "PACKAGING_FILES"):
        expected[PurePosixPath(name).name] = source[name]
    require(set(windows) == set(expected) | {"App/TEST_BUILD.json"}, "Windows payload differs from full frozen allowlist")
    for name, data in expected.items():
        require(windows[name] == data, "Windows payload differs from frozen source/generated defaults: " + name)
    combined_expected = {"windows/" + name: data for name, data in windows.items()}
    combined_expected.update({"mac/" + name: data for name, data in windows.items() if name.startswith("App/") and name != "App/TEST_BUILD.json"})
    combined_expected.update({destination: source[name].replace(b"\r\n", b"\n") for name, destination in MAC_OVERLAY.items()})
    require(set(combined) == set(combined_expected) | {"mac/App/TEST_BUILD.json"}, "Combined payload differs from full frozen allowlist")
    for name, data in combined_expected.items():
        require(combined[name] == data, "Combined payload differs from Windows/frozen overlay: " + name)
    for name, mode in modes.items():
        require(stat.S_IMODE(mode) == (0o755 if name.endswith((".sh", ".command")) else 0o644), "Combined permissions differ: " + name)
    for name in MAC_OVERLAY.values():
        if name.endswith((".sh", ".command")):
            require(combined[name].startswith(b"#!/bin/bash\n") and b"\r" not in combined[name], "Mac launcher requires LF bash shebang: " + name)
    require(not any({part.lower() for part in PurePosixPath(name).parts} & {".git", ".venv", "node_modules", "__pycache__", "data", "projects", "exports", "logs", "cache", "models", ".aws", ".ssh"} for name in combined), "Forbidden private/runtime payload")
    require(not any(PurePosixPath(name).suffix.lower() in FORBIDDEN_SUFFIXES for name in combined), "Forbidden media/model/log archive entry")
    # Detect concurrent input changes before returning a successful review record.
    require(_current_inputs(repo, required, trees, source) == current, "Current package inputs changed during qualification")
    require(all(_read(path) == archive_data[name] for name, path in (("source", source_archive), ("windows", windows_zip), ("combined", combined_zip))), "Archive changed during qualification")
    return {"schema_version": 1, "verdict": "passed_private_review_source_gate", "kind": "private_unpublished_review_qualification",
        "published": False, "qualified_for_release": False, "native_candidate_status": "pending",
        "public_native_ci_gate": "unchanged; approved release baseline not replaced or qualified by this review",
        "record_canonical_sha256": sha((json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")),
        "verifier_sha256": sha(_read(Path(__file__))),
        "source_comparison_policy": "exact bytes, allowing declared UTF-8 CRLF/LF differences only; BAT/PS1 and binaries exact",
        "source": {**record["source"], **binding}, "windows": record["windows"], "combined": record["combined"],
        "checks": {"current_source_inputs": len(current), "frozen_payload_source_files": len(required),
            "windows_entries_preserved": len(windows), "shared_app_entries": sum(name.startswith("App/") and name != "App/TEST_BUILD.json" for name in windows),
            "mac_overlays": len(MAC_OVERLAY), "combined_entries": len(combined), "combined_manifest_hashes": len(cm["files"]),
            "full_input_inventory": True, "fresh_defaults": True, "privacy_allowlist": True, "permissions": True},
        "not_performed": ["publication", "approved pin update", "native installation", "tiny.en download/transcription", "models", "human listening/editing QA"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True, type=Path)
    parser.add_argument("--windows-zip", required=True, type=Path)
    parser.add_argument("--combined-zip", required=True, type=Path)
    parser.add_argument("--source-archive", required=True, type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, help="New private .json report outside packaged source trees; refuses overwrite")
    args = parser.parse_args(argv)
    record = None
    output_policy = None
    output_location = None
    inputs = (args.record, args.windows_zip, args.combined_zip, args.source_archive)
    if args.output:
        # Validate before qualification: even a failure report must not create a
        # package input or replace one of the files being verified.
        try:
            record = parse_json(_read(args.record))
            output_policy = _report_policy(record, args.source_archive)
            output_location = _report_path(args.output, args.repo, inputs, *output_policy)
        except (QualificationError, OSError, RuntimeError) as error:
            parser.error(str(error))
    try:
        if record is None:
            record = parse_json(_read(args.record))
        report = qualify(record, args.windows_zip, args.combined_zip, args.source_archive, args.repo)
        result = 0
    except (QualificationError, OSError, subprocess.SubprocessError) as error:
        report = {"schema_version": 1, "verdict": "failed_private_review_source_gate", "published": False,
                  "qualified_for_release": False, "native_candidate_status": "pending", "reason": str(error)}
        result = 1
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        try:
            destination, _ = _report_path(args.output, args.repo, inputs, *output_policy, previous=output_location)
        except (QualificationError, OSError, RuntimeError) as error:
            parser.error(str(error))
        with destination.open("x", encoding="utf-8", newline="\n") as out:
            out.write(payload)
    print(payload, end="")
    return result


if __name__ == "__main__":
    sys.exit(main())
