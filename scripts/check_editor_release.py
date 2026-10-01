"""Exercise local editor media features without installing software or models.

The release CI checks an approved combined ZIP with the already installed test
runtime. Tests run against its extracted Mac App, never the checkout's product
modules. --source is an explicitly labelled local source-only diagnostic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEST_FILES = (
    "test_waveform_preparation.py", "test_stabilization.py",
    "test_stabilization_api.py", "test_media_command_encoding.py",
    "test_chroma_settings.py", "test_chroma_editing.py", "test_chroma_render.py", "test_chroma_image_background.py", "test_chroma_api.py",
    "test_director_rebuild_cache.py", "test_style_story_selection.py",
    "test_editor_model_selection.py",
    "test_media_render.py",
)
SELECTORS = tuple(f"tests/{name}" for name in TEST_FILES[:-1]) + (
    "tests/test_media_render.py::test_real_music_ducking_responds_to_source_speech",
    "tests/test_media_render.py::test_real_fades_and_mutes_preserve_library_audio_with_silent_source",
)
REQUIRED_CASES = {
    "test_source_a_b_waveforms_are_measured_on_native_clocks_and_survive_reopen",
    "test_source_no_audio_and_silent_audio_have_distinct_measured_states",
    "test_imported_audio_waveforms_have_real_peaks_and_survive_public_projection",
    "test_real_two_pass_reduces_jitter_preserves_frame_clock_and_copied_audio",
    "test_real_incompatible_audio_is_explicitly_encoded_as_aac",
    "test_real_silent_source_produces_silent_copy",
    "test_real_variable_frame_timestamps_and_source_audio_offset_are_preserved",
    "test_missing_filters_fail_before_processing_and_keep_original",
    "test_cancelled_transform_does_not_commit_or_leave_partial_files",
    "test_missing_filter_does_not_create_assets_or_jobs",
    "test_copy_is_a_project_asset_and_original_timeline_and_bytes_stay_unchanged",
    "test_real_synthetic_stabilization_copy_prepares_waveform_and_downloads_original_resolution",
    "test_real_music_ducking_responds_to_source_speech",
    "test_real_fades_and_mutes_preserve_library_audio_with_silent_source",
    "test_real_chroma_replaces_only_selected_video_and_preserves_audio_and_original",
    "test_real_chroma_keeps_independent_removed_footage_black",
    "test_real_frame_keys_at_native_geometry_before_downscale_and_preserves_source",
    "test_real_nonuniform_image_background_and_library_overlay_keep_pixels_audio_and_sources",
    "test_real_render_project_keeps_unused_existing_b_before_background_image",
    "test_real_shared_image_nodes_generate_the_same_known_png_preview_pixels",
    "test_missing_filter_never_mutates_project_but_disabling_remains_possible",
    "test_preset_rebuild_reports_preserved_manual_timeline_and_keeps_undo",
    "test_preset_without_manual_sequence_is_applied_to_editor_timeline",
    "test_clean_vod_keeps_natural_cleanup_controls_and_full_recording",
    "test_single_moment_style_does_not_join_distant_semantic_stories",
    "test_commentary_preserves_planned_ending_when_separate_story_parts_fit_budget",
    "test_final_review_exposes_planned_ending_lost_to_unavoidable_budget",
    "test_saved_commentary_keeps_planned_anchors_with_truthful_review",
    "test_no_available_configured_model_never_sends_request_to_missing_model",
    "test_installed_fallback_is_usable_but_identified_as_different_model",
    "test_missing_or_unusable_model_edit_is_labelled_basic_cleanup",
}
FEATURE_FILES = {
    "cutroom/audio.py", "cutroom/media.py", "cutroom/sequence.py",
    "cutroom/stabilization.py", "cutroom/stabilization_assets.py", "server.py",
    "web/stabilization-studio.js", "web/stabilization-studio.css",
    "cutroom/composition.py", "cutroom/effects.py", "cutroom/director.py", "cutroom/intelligence.py",
    "web/chroma-studio.js", "web/chroma-studio.css",
}


def normalized(data: bytes) -> bytes:
    # Normalize checkout line-ending differences without changing source content.
    return data.replace(b"\r\n", b"\n")


def verify_source_agreement(archive: Path, root: Path) -> dict:
    """Pin both packaged product source trees to the reviewed checkout."""
    names = {"server.py", "requirements.txt"}
    names.update(path.relative_to(root).as_posix() for path in (root / "cutroom").rglob("*.py"))
    names.update(path.relative_to(root).as_posix() for path in (root / "web").rglob("*")
                 if path.is_file() and path.suffix in {".js", ".css", ".html"})
    if not FEATURE_FILES <= names or any(not (root / name).is_file() for name in names):
        raise ValueError("The reviewed checkout is missing required editor feature source")
    hashes = {}
    with zipfile.ZipFile(archive) as bundle:
        members = set(bundle.namelist())
        for prefix in ("windows/App/", "mac/App/"):
            actual = {name[len(prefix):] for name in members if name.startswith(prefix)
                      and (name[len(prefix):] in {"server.py", "requirements.txt"}
                           or name[len(prefix):].startswith("cutroom/") and name.endswith(".py")
                           or name[len(prefix):].startswith("web/") and Path(name).suffix in {".js", ".css", ".html"})}
            if actual != names:
                raise ValueError(f"Packaged product source inventory differs from checkout: {prefix}")
            for name in sorted(names):
                reviewed = normalized((root / name).read_bytes())
                if normalized(bundle.read(prefix + name)) != reviewed:
                    raise ValueError(f"Packaged product source differs from checkout: {prefix}{name}")
                hashes[name] = hashlib.sha256(reviewed).hexdigest()
    return {"files_per_platform": len(names), "normalization": "CRLF to LF only", "sha256": hashes}


def inspect_ffmpeg() -> dict:
    """Release runners must supply vidstab; product capability remains optional."""
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Release feature checks require installed FFmpeg and FFprobe")
    def output(command):
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=20, check=True)
        return result.stdout
    filters = output([ffmpeg, "-nostdin", "-hide_banner", "-filters"])
    required = {"vidstabdetect", "vidstabtransform", "chromakey", "overlay", "split", "drawbox", "format", "scale", "crop", "setsar", "setpts"}
    found = set(re.findall(r"^\s*[.TSC]{3}\s+(\w+)\s+", filters, re.MULTILINE))
    if not {"vidstabdetect", "vidstabtransform"} <= found:
        raise RuntimeError("This release runner lacks required vidstab filters; real stabilization tests must not skip")
    if missing := required - found:
        raise RuntimeError(f"This release runner lacks required media filters: {', '.join(sorted(missing))}; real media tests must not skip")
    return {"ffmpeg": output([ffmpeg, "-version"]).splitlines()[0],
            "ffprobe": output([ffprobe, "-version"]).splitlines()[0],
            "stabilization_filters": ["vidstabdetect", "vidstabtransform"],
            "chroma_filters": sorted(required - {"vidstabdetect", "vidstabtransform"})}


def verify_test_report(path: Path) -> dict:
    """A successful pytest process alone cannot prove required real media ran."""
    cases = list(ET.parse(path).getroot().iter("testcase"))
    if not cases:
        raise RuntimeError("The feature suite produced no test evidence")
    for case in cases:
        if any(case.find(tag) is not None for tag in ("skipped", "failure", "error")):
            raise RuntimeError(f"Required feature test failed or skipped: {case.get('name')}")
    observed = {case.get("name", "").split("[", 1)[0] for case in cases}
    if missing := REQUIRED_CASES - observed:
        raise RuntimeError(f"Required feature tests were not collected: {', '.join(sorted(missing))}")
    return {"passed": len(cases), "skipped": 0, "required_cases": sorted(REQUIRED_CASES),
            "test_cases": [f"{case.get('classname')}::{case.get('name')}" for case in cases]}


def run_feature_tests(app: Path, scratch: Path, root: Path, *, stage_tests: bool) -> dict:
    if stage_tests:
        tests = app / "tests"
        for name in TEST_FILES:
            # The approved source package includes tests. Run those exact bytes;
            # never replace a stale packaged test with the checkout's version.
            packaged = tests / name
            if not packaged.is_file() or normalized(packaged.read_bytes()) != normalized((root / "tests" / name).read_bytes()):
                raise ValueError(f"Packaged feature test differs from checkout: {name}")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("CUTROOM_", "OPENAI_", "ANTHROPIC_"))
           and key not in {"PYTHONPATH", "PYTHONHOME", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"}}
    env.update(CUTROOM_DATA_DIR=str(scratch / "data"), CUTROOM_NO_BROWSER="1",
               PYTHONPATH=str(app), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1",
               PIP_NO_INDEX="1", HF_HUB_DISABLE_TELEMETRY="1")
    junit = scratch / "features.junit.xml"
    command = [sys.executable, "-B", "-X", "utf8", "-m", "pytest", "-q", "-o", "addopts=",
               "--basetemp", str(scratch / "pytest"), "--junitxml", str(junit), *SELECTORS]
    result = subprocess.run(command, cwd=app, env=env, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
    if result.returncode:
        raise RuntimeError(f"Extracted editor feature tests failed ({result.returncode}):\n{result.stdout[-10000:]}\n{result.stderr[-3000:]}")
    report = verify_test_report(junit)
    report["pytest_output"] = result.stdout.strip()
    report["test_source_sha256"] = {name: hashlib.sha256((root / "tests" / name).read_bytes()).hexdigest()
                                   for name in TEST_FILES}
    return report


def check_release(*, archive: Path | None = None, root: Path = ROOT) -> dict:
    result = {"mode": "extracted-candidate" if archive else "source-only",
              "platform": sys.platform, "architecture": platform.machine(),
              "python": platform.python_version(), "commit": os.environ.get("GITHUB_SHA"),
              "manual_mac_checks": "not performed", "runtime": inspect_ffmpeg()}
    with tempfile.TemporaryDirectory(prefix="CUTROOM editor features ") as directory:
        scratch = Path(directory)
        if archive:
            # Strict approved-baseline verification precedes all archive extraction.
            from build_universal_package import verify_package
            from smoke_macos import extract_mac
            manifest = verify_package(archive)
            result["archive"] = {"sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                                 "size_bytes": archive.stat().st_size, "build_id": manifest["build_id"]}
            result["source_agreement"] = verify_source_agreement(archive, root)
            app = extract_mac(archive, scratch)
        else:
            app = root
        result["features"] = run_feature_tests(app, scratch, root, stage_tests=archive is not None)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--archive", type=Path, help="Strictly verified combined candidate ZIP")
    mode.add_argument("--source", action="store_true", help="Local source-only diagnostic; does not verify a package")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = check_release(archive=args.archive.resolve() if args.archive else None)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    with args.report.open("x", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
