"""Release evidence must reject stale payloads and tests that never really ran."""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("editor_release_checks", ROOT / "scripts/check_editor_release.py")
checks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checks)


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "reviewed"
    names = checks.FEATURE_FILES | {
        "requirements.txt", "cutroom/__init__.py", "web/index.html",
        "web/app.js", "web/timeline.js", "web/source-review.js", "web/media-studio.js",
    }
    for name in names:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(f"# reviewed {name}\n".encode())
    return root


def archive(tmp_path, source, *, changed=None, missing=None, extra=None):
    target = tmp_path / "candidate.zip"
    with zipfile.ZipFile(target, "w") as bundle:
        for prefix in ("windows/App/", "mac/App/"):
            for file in source.rglob("*"):
                if not file.is_file():
                    continue
                name = prefix + file.relative_to(source).as_posix()
                if name == missing:
                    continue
                # A legitimate Windows checkout may differ only in line endings.
                data = file.read_bytes().replace(b"\n", b"\r\n") if prefix.startswith("windows") else file.read_bytes()
                bundle.writestr(name, b"stale payload\n" if name == changed else data)
        if extra:
            bundle.writestr(extra, b"unreviewed product code")
    return target


def test_matching_platform_sources_accept_only_line_ending_normalization(source, tmp_path):
    result = checks.verify_source_agreement(archive(tmp_path, source), source)
    assert result["files_per_platform"] == len([p for p in source.rglob("*") if p.is_file()])
    assert result["sha256"]["cutroom/stabilization.py"] == hashlib.sha256((source / "cutroom/stabilization.py").read_bytes()).hexdigest()


@pytest.mark.parametrize("member", ["windows/App/server.py", "mac/App/web/timeline.js"])
def test_changed_product_bytes_in_either_platform_are_rejected(source, tmp_path, member):
    with pytest.raises(ValueError, match="Packaged product source differs"):
        checks.verify_source_agreement(archive(tmp_path, source, changed=member), source)


@pytest.mark.parametrize("member", ["windows/App/cutroom/stabilization_assets.py", "mac/App/web/stabilization-studio.js"])
def test_missing_packaged_feature_source_is_rejected(source, tmp_path, member):
    with pytest.raises(ValueError, match="source inventory differs"):
        checks.verify_source_agreement(archive(tmp_path, source, missing=member), source)


def test_unreviewed_product_source_cannot_hide_in_the_other_platform(source, tmp_path):
    with pytest.raises(ValueError, match="source inventory differs"):
        checks.verify_source_agreement(archive(tmp_path, source, extra="mac/App/cutroom/unreviewed.py"), source)


@pytest.mark.parametrize("feature", ["cutroom/audio.py", "web/stabilization-studio.js"])
def test_reviewed_checkout_missing_required_feature_is_not_a_release_baseline(source, tmp_path, feature):
    candidate = archive(tmp_path, source)
    (source / feature).unlink()
    with pytest.raises(ValueError, match="missing required editor feature"):
        checks.verify_source_agreement(candidate, source)


def junit(tmp_path, names, *, outcome=None):
    suite = ET.Element("testsuite")
    for index, name in enumerate(names):
        case = ET.SubElement(suite, "testcase", classname="tests.editor_release", name=name)
        if outcome and index == 0:
            ET.SubElement(case, outcome)
    target = tmp_path / "features.junit.xml"
    ET.ElementTree(suite).write(target, encoding="utf-8", xml_declaration=True)
    return target


def test_required_evidence_includes_waveform_stabilization_and_mixer_contracts():
    assert {
        "test_source_a_b_waveforms_are_measured_on_native_clocks_and_survive_reopen",
        "test_real_variable_frame_timestamps_and_source_audio_offset_are_preserved",
        "test_copy_is_a_project_asset_and_original_timeline_and_bytes_stay_unchanged",
        "test_real_music_ducking_responds_to_source_speech",
        "test_real_fades_and_mutes_preserve_library_audio_with_silent_source",
        "test_real_chroma_replaces_only_selected_video_and_preserves_audio_and_original",
        "test_real_frame_keys_at_native_geometry_before_downscale_and_preserves_source",
        "test_preset_rebuild_reports_preserved_manual_timeline_and_keeps_undo",
        "test_single_moment_style_does_not_join_distant_semantic_stories",
    } <= checks.REQUIRED_CASES


def test_complete_parameterized_junit_is_successful_evidence(tmp_path):
    names = [name + "[synthetic-media]" for name in sorted(checks.REQUIRED_CASES)]
    report = checks.verify_test_report(junit(tmp_path, names))
    assert report["passed"] == len(names)
    assert report["skipped"] == 0


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error"])
def test_successful_process_cannot_hide_a_skipped_or_failed_case(tmp_path, outcome):
    with pytest.raises(RuntimeError, match="failed or skipped"):
        checks.verify_test_report(junit(tmp_path, sorted(checks.REQUIRED_CASES), outcome=outcome))


def test_missing_required_junit_case_is_rejected(tmp_path):
    names = sorted(checks.REQUIRED_CASES)
    with pytest.raises(RuntimeError, match=names[0]):
        checks.verify_test_report(junit(tmp_path, names[1:]))


def test_empty_junit_cannot_pass_release_validation(tmp_path):
    with pytest.raises(RuntimeError, match="no test evidence"):
        checks.verify_test_report(junit(tmp_path, []))


@pytest.mark.parametrize("missing", ["ffmpeg", "ffprobe"])
def test_missing_media_tool_fails_before_any_subprocess(monkeypatch, missing):
    monkeypatch.setattr(checks.shutil, "which", lambda name: None if name == missing else name)
    def forbidden(*args, **kwargs):
        pytest.fail("No command should run when a required media tool is missing")
    monkeypatch.setattr(checks.subprocess, "run", forbidden)
    with pytest.raises(RuntimeError, match="installed FFmpeg and FFprobe"):
        checks.inspect_ffmpeg()


@pytest.mark.parametrize("filters", ["", " ... vidstabdetect V->V detect", " ... vidstabtransform V->V transform"])
def test_real_stabilization_cannot_be_silently_skipped_without_both_filters(monkeypatch, filters):
    monkeypatch.setattr(checks.shutil, "which", lambda name: name)
    monkeypatch.setattr(checks.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=filters))
    with pytest.raises(RuntimeError, match="lacks required vidstab filters"):
        checks.inspect_ffmpeg()


def test_available_filter_inventory_records_the_actual_runtime(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: name)
    def run(command, **kwargs):
        assert kwargs["encoding"] == "utf-8" and kwargs["check"] is True
        assert kwargs["timeout"] == 20
        names = ("vidstabdetect", "vidstabtransform", "chromakey", "overlay", "split", "drawbox", "format", "scale", "crop", "setsar", "setpts")
        text = "".join(f" ... {name} V->V reviewed\n" for name in names) if "-filters" in command else f"{command[0]} version reviewed\n"
        return SimpleNamespace(stdout=text)
    monkeypatch.setattr(checks.subprocess, "run", run)
    result = checks.inspect_ffmpeg()
    assert result["stabilization_filters"] == ["vidstabdetect", "vidstabtransform"]
    assert result["ffmpeg"] == "ffmpeg version reviewed"
    assert result["ffprobe"] == "ffprobe version reviewed"
    assert "chromakey" in result["chroma_filters"]


def test_vidstab_alone_cannot_skip_required_real_chroma_release_check(monkeypatch):
    monkeypatch.setattr(checks.shutil, "which", lambda name: name)
    monkeypatch.setattr(checks.subprocess, "run", lambda *_a, **_k: SimpleNamespace(
        stdout=" ... vidstabdetect V->V detect\n ... vidstabtransform V->V transform\n"))
    with pytest.raises(RuntimeError, match="required media filters.*chromakey"):
        checks.inspect_ffmpeg()
