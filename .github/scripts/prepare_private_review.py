"""Build Git-bound, unpublished review inputs from this run's tested Windows ZIP."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import zipfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "--no-replace-objects", "-C", str(root), *args], check=True,
                          capture_output=True, stdin=subprocess.DEVNULL, timeout=60).stdout


def pin_zip(path: Path, manifest_path: str) -> dict:
    data = path.read_bytes()
    with zipfile.ZipFile(path) as package:
        raw = package.read(manifest_path)
        manifest = json.loads(raw)
    return {"bytes": len(data), "sha256": sha(data), "manifest_sha256": sha(raw),
            "build_id": manifest["build_id"]}


def source_archive(root: Path, source_sha: str, output: Path) -> tuple[str, int]:
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    tree = git(root, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    if head != source_sha:
        raise RuntimeError("Candidate checkout is not the tested PR head")
    entries = []
    for line in git(root, "ls-tree", "-r", "-z", "--full-tree", "HEAD").split(b"\0"):
        if not line:
            continue
        header, raw_name = line.split(b"\t", 1)
        mode, kind, _ = header.decode("ascii").split()
        name = raw_name.decode("utf-8")
        relative = PurePosixPath(name)
        if mode not in {"100644", "100755"} or kind != "blob" or relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise RuntimeError("Unsafe tracked source entry")
        path = root.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise RuntimeError(f"Unsafe source file: {name}")
        entries.append((name, mode, path))
    if not entries:
        raise RuntimeError("Tracked source inventory is empty")
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.comment = source_sha.encode("ascii")
        for name, mode, path in entries:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if mode == "100755" else 0o100644) << 16
            archive.writestr(info, path.read_bytes())
    return tree, len(entries)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--windows-zip", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path, required=True)
    parser.add_argument("--feature-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve(strict=True)
    runner_temp = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    windows = args.windows_zip.resolve(strict=True)
    output = args.output_dir.resolve()
    if not windows.is_relative_to(runner_temp) or not output.is_relative_to(runner_temp) or output == runner_temp or output.exists():
        raise RuntimeError("Review inputs must use a fresh runner-temporary directory")
    source_sha = os.environ["TESTED_HEAD_SHA"]
    smoke = json.loads(args.smoke_report.read_text(encoding="utf-8"))
    features = json.loads(args.feature_report.read_text(encoding="utf-8"))
    pin = pin_zip(windows, "App/TEST_BUILD.json")
    if (smoke["head_sha"] != source_sha or smoke["candidate_sha256"] != pin["sha256"]
            or smoke["checks"]["direct_setup"] != "passed_direct_unmodified_setup_without_ollama"
            or smoke["checks"]["saved_project_and_export_after_server_restart"] != "passed"
            or features["passed"] < 1 or features["skipped"] != 0):
        raise RuntimeError("Windows evidence does not qualify these candidate bytes")

    output.mkdir()
    source = output / "candidate-source.zip"
    source_tree, source_count = source_archive(root, source_sha, source)
    baseline = {**pin, "review_only": True, "published": False, "qualified_for_release": False}
    baseline_path = output / "temporary-windows-baseline.json"
    baseline_path.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(root / "scripts"))
    import build_universal_package as universal
    combined = universal.build_package(root, windows, runner_temp / "cutroom-private-combined",
                                       windows_baseline=baseline_path)
    universal.verify_package(combined, windows_baseline=baseline_path)
    combined_pin = pin_zip(combined, "mac/App/TEST_BUILD.json")
    source_bytes = source.read_bytes()
    record = {"schema_version": 1, "kind": "cutroom-private-review-candidate", "published": False,
              "qualified_for_release": False, "native_candidate_status": "pending",
              "source": {"commit": source_sha, "tree": source_tree, "archive_sha256": sha(source_bytes),
                         "archive_bytes": len(source_bytes), "files": source_count},
              "windows": pin, "combined": combined_pin}
    verifier = load_module("private_review_verifier", root / "packaging" / "verify_review_candidate.py")
    result = verifier.qualify(record, windows, combined, source, root)
    if result.get("verdict") != "passed_private_review_source_gate":
        raise RuntimeError("Private source qualification failed")
    shutil.copy2(windows, output / "candidate-windows.zip")
    shutil.copy2(combined, output / "candidate-combined.zip")
    (output / "review-record.json").write_bytes((json.dumps(record, indent=2) + "\n").encode("utf-8"))
    (output / "source-qualification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("PRIVATE_REVIEW_RECORD_BEGIN")
    print(json.dumps(record, indent=2))
    print("PRIVATE_REVIEW_RECORD_END")
    print("PRIVATE_REVIEW_RECORD_JSON=" + json.dumps(record, separators=(",", ":")))


if __name__ == "__main__":
    main()
