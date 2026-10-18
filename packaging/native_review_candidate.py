"""Prepare an unpublished, source-pinned candidate; opt in to native Mac checks.

The default path only reads local files and Git objects. Existing application
scripts and approved public pins are never edited or replaced.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from types import SimpleNamespace


PUBLIC_PINS = (
    ".github/download-request-baseline.json",
    "packaging/windows/release-baseline.json",
    "packaging/windows/validation-baseline.json",
    "packaging/mac/validation-baseline.json",
    "packaging/mac/release-candidate.json",
    "website/release.json",
)


def _load_verifier():
    path = Path(__file__).with_name("verify_review_candidate.py")
    spec = importlib.util.spec_from_file_location("cutroom_native_review_identity", path)
    if spec is None or spec.loader is None:
        raise ValueError("The private review verifier is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require_native_platform() -> None:
    if sys.platform != "darwin" or sys.version_info[:2] != (3, 12):
        raise ValueError("--native requires native macOS with Python 3.12")


def _plain_path(path: Path, root: Path, verifier) -> Path:
    target = path.resolve()
    verifier.require(".." not in path.parts and path.absolute().is_relative_to(root) and target.is_relative_to(root),
                     "Input escapes the review checkout")
    absolute = path.absolute()
    for current in (absolute, *absolute.parents):
        if current == root:
            return target
        verifier.require(current.exists() and not verifier._linked(current), "Linked or missing review input")
    raise ValueError("Review input has no qualified checkout ancestor")


def _committed_record(path: Path, repo: Path, verifier) -> tuple[dict, dict]:
    target = _plain_path(path, repo, verifier)
    relative = target.relative_to(repo).as_posix()
    verifier.require(target.parent == repo / "packaging/review-candidates" and target.suffix == ".json",
                     "Select a committed packaging/review-candidates JSON record")
    data = verifier._read(target)
    committed = verifier._git(repo, "show", "HEAD:" + relative)
    verifier.require(data == committed, "Review record differs from its committed HEAD blob")
    dirty = verifier._git(repo, "status", "--porcelain=v1", "--untracked-files=all", "--", relative)
    verifier.require(not dirty, "Review record has uncommitted changes")
    provenance = {"path": relative, "sha256": verifier.sha(data),
                  "head": verifier._git(repo, "rev-parse", "HEAD").decode("ascii").strip(),
                  "blob": verifier._git(repo, "rev-parse", "HEAD:" + relative).decode("ascii").strip()}
    return verifier.parse_json(data), provenance


def _public_pins(repo: Path, verifier) -> dict[str, str]:
    return {name: verifier.sha(verifier._read(_plain_path(repo / name, repo, verifier)))
            for name in PUBLIC_PINS}


def _output_location(path: Path, repo: Path, verifier) -> tuple[Path, tuple[int, int]]:
    verifier.require(not os.path.lexists(path), "--output-dir must be a new directory")
    verifier.require(path.parent.is_dir(), "--output-dir parent must already exist")
    target = path.resolve()
    verifier.require(not os.path.lexists(target), "--output-dir must resolve to a new directory")
    verifier.require(not any(part.casefold() in {"app", ".git", ".venv"} for part in target.parts),
                     "Reports cannot be written inside an App, Git or runtime directory")
    if target.is_relative_to(repo):
        verifier.require(target != repo / "dist" and target.is_relative_to(repo / "dist"),
                         "Reports inside the checkout must use a new directory under dist")
    parent = target.parent.stat()
    return target, (parent.st_dev, parent.st_ino)


def _write_json(output: Path, name: str, value: dict, stamp: tuple[int, int], verifier) -> None:
    state = output.stat()
    verifier.require(not verifier._linked(output) and output.resolve() == output
                     and (state.st_dev, state.st_ino) == stamp, "Report directory changed")
    with (output / name).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def _load_native_modules(repo: Path) -> SimpleNamespace:
    before = sys.path[:]
    try:
        sys.path[:0] = [str(repo / "scripts"), str(repo)]
        modules = [importlib.import_module(name) for name in
                   ("build_universal_package", "check_editor_release", "smoke_macos")]
        for module in modules:
            if Path(module.__file__).resolve() != repo / "scripts" / (module.__name__ + ".py"):
                raise ValueError("Native helper was loaded outside the qualified checkout")
        return SimpleNamespace(universal=modules[0], editor=modules[1], smoke=modules[2])
    finally:
        sys.path[:] = before


def prepare(record_path: Path, windows_zip: Path, combined_zip: Path, source_archive: Path,
            repo: Path, output_dir: Path, *, native: bool = False, transcribe: bool = False) -> dict:
    """Qualify first; create fresh reports, then optionally run native helpers."""
    if transcribe and not native:
        raise ValueError("--transcribe requires the explicit --native opt-in")
    if native:
        _require_native_platform()
    verifier = _load_verifier()
    verifier.require(repo.is_dir() and not verifier._linked(repo), "Missing or linked checkout")
    repo = repo.resolve()
    record_path, windows_zip, combined_zip, source_archive = (
        Path(path).absolute() for path in (record_path, windows_zip, combined_zip, source_archive))
    output_dir = Path(output_dir).absolute()
    location = _output_location(output_dir, repo, verifier)
    record, provenance = _committed_record(record_path, repo, verifier)
    pins = _public_pins(repo, verifier)
    qualification = verifier.qualify(record, windows_zip, combined_zip, source_archive, repo)

    def checkpoint() -> None:
        current, current_provenance = _committed_record(record_path, repo, verifier)
        verifier.require(current == record and current_provenance == provenance, "Review record changed")
        verifier.require(_public_pins(repo, verifier) == pins, "Approved public pins changed")
        verifier.require(verifier.qualify(record, windows_zip, combined_zip, source_archive, repo)
                         == qualification, "Review source qualification changed")

    windows, _, _ = verifier._zip(verifier._read(windows_zip))
    manifest = verifier._manifest(windows, "App/TEST_BUILD.json", record["windows"])
    baseline = {**record["windows"], "app_version": manifest["app_version"],
                "review_only": True, "published": False, "qualified_for_release": False}
    checkpoint()
    verifier.require(_output_location(output_dir, repo, verifier) == location, "Output location changed")
    output, _ = location
    output.mkdir()
    state = output.stat()
    stamp = (state.st_dev, state.st_ino)
    _write_json(output, "windows-baseline.json", baseline, stamp, verifier)
    baseline_path = output / "windows-baseline.json"
    baseline_hash = verifier.sha(verifier._read(baseline_path))
    result = {"schema_version": 1, "kind": "private_unpublished_native_review",
              "verdict": "prepared_private_native_review", "published": False,
              "qualified_for_release": False, "native_candidate_status": "pending",
              "record": provenance, "qualification": qualification, "public_pins": pins,
              "windows_baseline_sha256": baseline_hash, "native_requested": native,
              "transcription_requested": transcribe}
    _write_json(output, "preparation.json", result, stamp, verifier)
    if not native:
        checkpoint()
        return result

    def native_checkpoint() -> None:
        checkpoint()
        verifier.require(verifier.sha(verifier._read(baseline_path)) == baseline_hash,
                         "Private review baseline changed")

    native_checkpoint()
    try:
        modules = _load_native_modules(repo)
        verified = modules.universal.verify_package(combined_zip, windows_baseline=baseline_path)
        runtime = modules.editor.inspect_ffmpeg()
        source_agreement = modules.editor.verify_source_agreement(combined_zip, repo)
        with tempfile.TemporaryDirectory(prefix="CUTROOM editor features ") as directory:
            scratch = Path(directory)
            app = modules.smoke.extract_mac(combined_zip, scratch)
            features = modules.editor.run_feature_tests(app, scratch, repo, stage_tests=True)
    finally:
        native_checkpoint()
    feature_report = {"mode": "private-review-extracted-candidate", "platform": sys.platform,
                      "architecture": platform.machine(), "python": platform.python_version(),
                      "commit": provenance["head"], "candidate_source_commit": record["source"]["commit"],
                      "archive": record["combined"],
                      "verified_build_id": verified["build_id"], "runtime": runtime,
                      "source_agreement": source_agreement, "features": features}
    _write_json(output, "editor-features.json", feature_report, stamp, verifier)
    try:
        smoke = modules.smoke.install_and_check(combined_zip, windows_baseline=baseline_path,
                                               repair_missing_pip=False, transcribe=transcribe)
    finally:
        native_checkpoint()
    verifier.require(smoke.get("status") == "passed", "Candidate native smoke did not pass")
    _write_json(output, "macos-fresh-install.json", smoke, stamp, verifier)
    try:
        recovery = modules.smoke.install_and_check(combined_zip, windows_baseline=baseline_path,
                                                  repair_missing_pip=True, transcribe=False)
    finally:
        native_checkpoint()
    verifier.require(recovery.get("status") == "passed", "Candidate missing-pip recovery did not pass")
    _write_json(output, "macos-missing-pip.json", recovery, stamp, verifier)
    result = {**result, "verdict": "passed_private_native_review_checks",
              "native_candidate_status": "passed_native_checks", "features": feature_report,
              "installation": {"empty_app_install": smoke, "missing_pip_recovery": recovery},
              "public_pins_unchanged": True,
              "human_acceptance": "not_performed", "qualified_for_release": False}
    _write_json(output, "native-review.json", result, stamp, verifier)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("record", "windows-zip", "combined-zip", "source-archive", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--native", action="store_true", help="Run existing native Mac acceptance helpers")
    parser.add_argument("--transcribe", action="store_true", help="With --native, explicitly allow tiny.en transcription")
    args = parser.parse_args(argv)
    try:
        result = prepare(args.record, args.windows_zip, args.combined_zip, args.source_archive,
                         args.repo, args.output_dir, native=args.native, transcribe=args.transcribe)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print("Private native review failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
