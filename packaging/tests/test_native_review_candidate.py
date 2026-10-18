"""Synthetic review orchestration checks; native gates are explicit test doubles."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
PIN_PATHS = (
    ".github/download-request-baseline.json",
    "packaging/windows/release-baseline.json",
    "packaging/windows/validation-baseline.json",
    "packaging/mac/release-candidate.json",
    "packaging/mac/validation-baseline.json",
    "website/release.json",
)


def load_file(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Review test module is unavailable: " + path.name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeReviewCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Compose the fixture rather than inheriting its test methods. Importing
        # it only defines fixtures; its synthetic Git setup runs at test time.
        cls.support = load_file("cutroom_native_review_fixture_support", ROOT / "packaging/tests/test_review_candidate.py")
        cls.fixture_class = cls.support.ReviewCandidateTests
        cls.addClassCleanup(cls.fixture_class.doClassCleanups)
        cls.fixture_class.setUpClass()
        cls.subject = load_file("cutroom_native_review_candidate_under_test", ROOT / "packaging/native_review_candidate.py")

    def setUp(self) -> None:
        self.fixture = self.fixture_class("test_valid_pair_is_read_only_and_cannot_claim_release_or_native_qa")
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.repo = self.fixture.repo
        self.output = self.fixture.root / "native-review-output"
        self.record = self.repo / "packaging/review-candidates" / (self.fixture.commit[:7] + ".json")
        self.record.parent.mkdir(parents=True, exist_ok=True)
        self.record.write_bytes(self.support.json_bytes(self.fixture.record))
        for name in PIN_PATHS:
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.support.json_bytes({"synthetic_protected_pin": name}))
        self.git("add", "--", self.record.relative_to(self.repo).as_posix(), *PIN_PATHS)
        self.git("commit", "--quiet", "-m", "Commit independent synthetic review trust anchor")

    def git(self, *args: str) -> str:
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
               "GIT_TERMINAL_PROMPT": "0"}
        result = subprocess.run(
            ["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=" + str(self.fixture.root / "no-hooks"),
             "-c", "commit.gpgsign=false", "-c", "user.name=Native review fixture",
             "-c", "user.email=fixture@example.invalid", *args],
            cwd=self.repo, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        return result.stdout.decode("utf-8").strip()

    def prepare(self, *, record=None, output=None, **kwargs):
        return self.subject.prepare(
            self.record if record is None else record,
            self.fixture.windows, self.fixture.combined, self.fixture.source, self.repo,
            self.output if output is None else output, **kwargs,
        )

    def reject_before_output(self, **kwargs):
        with patch.object(self.subject, "_load_native_modules") as load:
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                self.prepare(**kwargs)
        load.assert_not_called()
        output = kwargs.get("output", self.output)
        self.assertFalse(output.exists())

    def cli(self, *extra: str):
        arguments = ["--record", str(self.record), "--windows-zip", str(self.fixture.windows),
                     "--combined-zip", str(self.fixture.combined), "--source-archive", str(self.fixture.source),
                     "--repo", str(self.repo), "--output-dir", str(self.output), *extra]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = self.subject.main(arguments)
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def native_doubles(self, *, fail_at=None, transcribe=False):
        calls = []
        install_repairs = []
        app = self.output / "scratch/mac/App"
        manifest = json.loads(self.support.read_zip(self.fixture.combined)[self.support.COMBINED_MANIFEST])

        def step(name):
            calls.append(name)
            if name == fail_at:
                raise RuntimeError("Synthetic native gate failure: " + name)

        def verify_package(archive, *, windows_baseline):
            step("verify_package")
            self.assertEqual(Path(archive), self.fixture.combined)
            baseline = Path(windows_baseline)
            self.assertEqual(baseline, self.output / "windows-baseline.json")
            self.assertTrue(baseline.is_file())
            pin = json.loads(baseline.read_bytes())
            for key in ("sha256", "bytes", "manifest_sha256", "build_id"):
                self.assertEqual(pin[key], self.fixture.record["windows"][key])
            return manifest

        def inspect_ffmpeg():
            step("inspect_ffmpeg")
            return {"ffmpeg": "synthetic", "ffprobe": "synthetic",
                    "stabilization_filters": ["vidstabdetect", "vidstabtransform"]}

        def verify_source_agreement(archive, repo):
            step("verify_source_agreement")
            self.assertEqual((Path(archive), Path(repo)), (self.fixture.combined, self.repo))
            return {"files_per_platform": 1, "normalization": "CRLF to LF only", "sha256": {}}

        def extract_mac(archive, scratch):
            nonlocal app
            step("extract_mac")
            self.assertEqual(Path(archive), self.fixture.combined)
            scratch = Path(scratch)
            self.assertTrue(scratch.name.startswith("CUTROOM editor features "))
            self.assertEqual(scratch.parent.resolve(), Path(tempfile.gettempdir()).resolve())
            app = scratch / "mac/App"
            app.mkdir(parents=True)
            return app

        def run_feature_tests(actual_app, scratch, repo, *, stage_tests):
            step("run_feature_tests")
            self.assertEqual(Path(actual_app), app)
            self.assertEqual(Path(scratch), app.parent.parent)
            self.assertEqual(Path(repo), self.repo)
            self.assertIs(stage_tests, True)
            return {"passed": 1, "skipped": 0, "required_cases": ["synthetic_case"],
                    "test_cases": ["synthetic_case"]}

        def install_and_check(archive, *, windows_baseline, repair_missing_pip, transcribe):
            install_repairs.append(repair_missing_pip)
            self.assertLessEqual(len(install_repairs), 2)
            self.assertEqual(install_repairs, [False, True][:len(install_repairs)])
            step("install_and_check_recovery" if repair_missing_pip else "install_and_check")
            self.assertEqual(Path(archive), self.fixture.combined)
            self.assertEqual(Path(windows_baseline), self.output / "windows-baseline.json")
            self.assertIs(transcribe, False if repair_missing_pip else expected_transcribe)
            return {"status": "passed", "installation": "synthetic", "transcription_enabled": transcribe,
                    "restart": "synthetic checked"}

        expected_transcribe = transcribe
        modules = SimpleNamespace(
            universal=SimpleNamespace(verify_package=verify_package),
            editor=SimpleNamespace(inspect_ffmpeg=inspect_ffmpeg, verify_source_agreement=verify_source_agreement,
                                   run_feature_tests=run_feature_tests),
            smoke=SimpleNamespace(extract_mac=extract_mac, install_and_check=install_and_check,
                                  verify_package=verify_package),
        )
        return modules, calls

    def test_default_preparation_qualifies_identity_without_loading_native_or_asr(self):
        pins = {name: (self.repo / name).read_bytes() for name in PIN_PATHS}
        archives = {path: path.read_bytes() for path in (self.fixture.source, self.fixture.windows, self.fixture.combined)}
        with patch.object(self.subject, "_load_native_modules", side_effect=AssertionError("Native/model work was not authorized")) as load:
            result = self.prepare()
        load.assert_not_called()
        self.assertIsInstance(result, dict)
        self.assertEqual({path.name for path in self.output.iterdir()}, {"windows-baseline.json", "preparation.json"})
        self.assertEqual(json.loads((self.output / "preparation.json").read_bytes()), result)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in PIN_PATHS}, pins)
        self.assertEqual({path: path.read_bytes() for path in archives}, archives)
        baseline = json.loads((self.output / "windows-baseline.json").read_bytes())
        self.assertEqual(baseline["sha256"], self.fixture.record["windows"]["sha256"])
        self.assertEqual(baseline["manifest_sha256"], self.fixture.record["windows"]["manifest_sha256"])

    def test_uncommitted_record_cannot_be_its_own_trust_anchor(self):
        untracked = self.record.with_name("untracked.json")
        untracked.write_bytes(self.record.read_bytes())
        self.reject_before_output(record=untracked)

    def test_record_must_be_inside_the_committed_review_record_directory(self):
        outside = self.fixture.root / "review-record.json"
        outside.write_bytes(self.record.read_bytes())
        self.reject_before_output(record=outside)

    def test_dirty_record_bytes_fail_even_when_json_meaning_is_unchanged(self):
        self.record.write_bytes(self.record.read_bytes() + b"\n")
        self.reject_before_output()

    def test_dirty_record_index_fails_even_when_worktree_matches_head(self):
        original = self.record.read_bytes()
        self.record.write_bytes(original + b"\n")
        self.git("add", "--", self.record.relative_to(self.repo).as_posix())
        self.record.write_bytes(original)
        self.reject_before_output()

    def test_archive_hash_failures_never_create_output_or_load_native_modules(self):
        for path in (self.fixture.windows, self.fixture.combined, self.fixture.source):
            with self.subTest(archive=path.name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"unexpected archive bytes")
                    self.reject_before_output()
                finally:
                    path.write_bytes(original)

    def test_changed_current_source_fails_before_output(self):
        path = self.repo / "server.py"
        path.write_bytes(path.read_bytes() + b"changed source\n")
        self.reject_before_output()

    def test_missing_protected_public_pin_fails_before_output(self):
        (self.repo / PIN_PATHS[0]).unlink()
        self.reject_before_output()

    def test_output_cannot_be_created_inside_packaged_or_runtime_directories(self):
        for name in ("cutroom/new-review", "web/new-review", "scripts/new-review", "tests/new-review",
                     "packaging/new-review", "App/new-review", ".git/new-review", ".venv/new-review"):
            with self.subTest(path=name):
                output = self.repo / name
                output.parent.mkdir(parents=True, exist_ok=True)
                self.reject_before_output(output=output)

    def test_external_output_cannot_be_inside_an_app_or_runtime_component(self):
        for name in ("App", ".git", ".venv"):
            with self.subTest(component=name):
                parent = self.fixture.root / name
                parent.mkdir()
                self.reject_before_output(output=parent / "native-review")

    def test_new_output_under_repo_dist_is_allowed(self):
        dist = self.repo / "dist"
        dist.mkdir()
        output = dist / "private-review"
        with patch.object(self.subject, "_load_native_modules") as load:
            self.prepare(output=output)
        load.assert_not_called()
        self.assertTrue((output / "preparation.json").is_file())

    def test_missing_output_parent_is_not_implicitly_created(self):
        output = self.fixture.root / "missing-parent/native-review"
        self.reject_before_output(output=output)
        self.assertFalse(output.parent.exists())

    def test_existing_output_is_not_reused_or_overwritten(self):
        self.output.mkdir()
        previous = self.output / "preparation.json"
        original = b'{"previous_review":true}\n'
        previous.write_bytes(original)
        with patch.object(self.subject, "_load_native_modules") as load:
            with self.assertRaises((ValueError, RuntimeError, OSError)):
                self.prepare()
        load.assert_not_called()
        self.assertEqual(previous.read_bytes(), original)
        self.assertEqual({path.name for path in self.output.iterdir()}, {"preparation.json"})

    def test_transcription_requires_explicit_native_mode_before_output(self):
        self.reject_before_output(transcribe=True)

    def test_native_platform_guard_refuses_non_darwin_and_non_python312(self):
        for platform, version in (("win32", (3, 12, 0)), ("linux", (3, 12, 0)),
                                  ("darwin", (3, 11, 9)), ("darwin", (3, 13, 0))):
            with self.subTest(platform=platform, version=version):
                with patch.object(self.subject.sys, "platform", platform), patch.object(self.subject.sys, "version_info", version):
                    with self.assertRaises((ValueError, RuntimeError)):
                        self.subject._require_native_platform()
        with patch.object(self.subject.sys, "platform", "darwin"), patch.object(self.subject.sys, "version_info", (3, 12, 0)):
            self.subject._require_native_platform()

    def test_native_calls_strict_gates_in_order_without_replacing_functions(self):
        modules, calls = self.native_doubles()
        before = tuple((module, key, getattr(module, key)) for module, keys in (
            (modules.universal, ("verify_package",)),
            (modules.editor, ("inspect_ffmpeg", "verify_source_agreement", "run_feature_tests")),
            (modules.smoke, ("verify_package", "extract_mac", "install_and_check")),
        ) for key in keys)
        pins = {name: (self.repo / name).read_bytes() for name in PIN_PATHS}
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules) as load:
            result = self.prepare(native=True)
        load.assert_called_once_with(self.repo)
        self.assertEqual(calls, ["verify_package", "inspect_ffmpeg", "verify_source_agreement", "extract_mac",
                                 "run_feature_tests", "install_and_check", "install_and_check_recovery"])
        for module, key, function in before:
            self.assertIs(getattr(module, key), function)
        self.assertEqual({name: (self.repo / name).read_bytes() for name in PIN_PATHS}, pins)
        feature_path = self.output / "editor-features.json"
        self.assertTrue(feature_path.is_file())
        feature_report = json.loads(feature_path.read_bytes())
        self.assertEqual(feature_report["platform"], self.subject.sys.platform)
        self.assertEqual(feature_report["commit"], result["record"]["head"])
        self.assertEqual(feature_report["candidate_source_commit"], self.fixture.record["source"]["commit"])
        self.assertTrue(feature_report["architecture"])
        self.assertTrue(feature_report["python"])
        self.assertTrue((self.output / "macos-fresh-install.json").is_file())
        self.assertTrue((self.output / "macos-missing-pip.json").is_file())
        self.assertTrue((self.output / "native-review.json").is_file())

    def test_native_transcription_is_requested_only_for_explicit_fresh_install(self):
        modules, calls = self.native_doubles(transcribe=True)
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            self.prepare(native=True, transcribe=True)
        self.assertEqual(calls[-2:], ["install_and_check", "install_and_check_recovery"])
        fresh = json.loads((self.output / "macos-fresh-install.json").read_bytes())
        recovery = json.loads((self.output / "macos-missing-pip.json").read_bytes())
        self.assertIs(fresh["transcription_enabled"], True)
        self.assertIs(recovery["transcription_enabled"], False)

    def test_failed_strict_package_gate_prevents_all_later_native_calls(self):
        modules, calls = self.native_doubles(fail_at="verify_package")
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native gate failure"):
                self.prepare(native=True)
        self.assertEqual(calls, ["verify_package"])
        self.assertFalse((self.output / "native-review.json").exists())

    def test_failed_source_agreement_prevents_extraction_features_and_install(self):
        modules, calls = self.native_doubles(fail_at="verify_source_agreement")
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native gate failure"):
                self.prepare(native=True)
        self.assertEqual(calls, ["verify_package", "inspect_ffmpeg", "verify_source_agreement"])
        self.assertFalse((self.output / "native-review.json").exists())

    def test_failed_feature_gate_prevents_install_restart_and_transcription(self):
        modules, calls = self.native_doubles(fail_at="run_feature_tests", transcribe=True)
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native gate failure"):
                self.prepare(native=True, transcribe=True)
        self.assertEqual(calls[-1], "run_feature_tests")
        self.assertNotIn("install_and_check", calls)
        self.assertFalse((self.output / "native-review.json").exists())

    def test_native_install_failure_is_not_swallowed_as_an_old_restart_exception(self):
        modules, calls = self.native_doubles(fail_at="install_and_check")
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native gate failure"):
                self.prepare(native=True)
        self.assertEqual(calls[-1], "install_and_check")
        self.assertFalse((self.output / "native-review.json").exists())

    def test_native_missing_pip_recovery_failure_prevents_final_acceptance(self):
        modules, calls = self.native_doubles(fail_at="install_and_check_recovery")
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaisesRegex(RuntimeError, "Synthetic native gate failure"):
                self.prepare(native=True)
        self.assertEqual(calls[-2:], ["install_and_check", "install_and_check_recovery"])
        self.assertTrue((self.output / "macos-fresh-install.json").is_file())
        self.assertFalse((self.output / "native-review.json").exists())

    def test_nonpassing_install_report_cannot_qualify_native_checks(self):
        modules, calls = self.native_doubles()
        original = modules.smoke.install_and_check

        def nonpassing(*args, **kwargs):
            return {**original(*args, **kwargs), "status": "known_failure"}

        modules.smoke.install_and_check = nonpassing
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaises(ValueError):
                self.prepare(native=True)
        self.assertEqual(calls[-1], "install_and_check")
        self.assertFalse((self.output / "native-review.json").exists())

    def test_nonpassing_recovery_report_cannot_qualify_native_checks(self):
        modules, calls = self.native_doubles()
        original = modules.smoke.install_and_check

        def nonpassing(*args, **kwargs):
            report = original(*args, **kwargs)
            return {**report, "status": "known_failure"} if kwargs["repair_missing_pip"] else report

        modules.smoke.install_and_check = nonpassing
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaises(ValueError):
                self.prepare(native=True)
        self.assertEqual(calls[-2:], ["install_and_check", "install_and_check_recovery"])
        self.assertFalse((self.output / "native-review.json").exists())

    def test_native_checkpoint_rejects_changed_public_pin_before_install(self):
        modules, calls = self.native_doubles()
        original = modules.editor.run_feature_tests

        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            (self.repo / PIN_PATHS[0]).write_bytes(b"unexpected changed public pin\n")
            return result

        modules.editor.run_feature_tests = tamper
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaises(ValueError):
                self.prepare(native=True)
        self.assertNotIn("install_and_check", calls)
        self.assertFalse((self.output / "native-review.json").exists())

    def test_native_checkpoint_rejects_changed_private_baseline_before_install(self):
        modules, calls = self.native_doubles()
        original = modules.editor.run_feature_tests

        def tamper(*args, **kwargs):
            result = original(*args, **kwargs)
            baseline = self.output / "windows-baseline.json"
            baseline.write_bytes(baseline.read_bytes() + b"\n")
            return result

        modules.editor.run_feature_tests = tamper
        with patch.object(self.subject, "_require_native_platform"), patch.object(self.subject, "_load_native_modules", return_value=modules):
            with self.assertRaises(ValueError):
                self.prepare(native=True)
        self.assertNotIn("install_and_check", calls)
        self.assertFalse((self.output / "native-review.json").exists())

    def test_cli_transcribe_without_native_is_rejected_without_outputs_or_native_loading(self):
        with patch.object(self.subject, "prepare", wraps=self.subject.prepare) as prepare, patch.object(self.subject, "_load_native_modules") as load:
            code, _, _ = self.cli("--transcribe")
        self.assertNotEqual(code, 0)
        self.assertEqual(prepare.call_count, 1)
        self.assertIs(prepare.call_args.kwargs["native"], False)
        self.assertIs(prepare.call_args.kwargs["transcribe"], True)
        load.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_cli_defaults_do_not_request_native_execution_or_transcription(self):
        with patch.object(self.subject, "prepare", return_value={"status": "synthetic_prepared"}) as prepare:
            code, _, _ = self.cli()
        self.assertEqual(code, 0)
        self.assertEqual(prepare.call_count, 1)
        self.assertEqual(prepare.call_args.args, (self.record, self.fixture.windows, self.fixture.combined,
                                                self.fixture.source, self.repo, self.output))
        self.assertIs(prepare.call_args.kwargs.get("native", False), False)
        self.assertIs(prepare.call_args.kwargs.get("transcribe", False), False)

    def test_cli_explicit_native_and_transcribe_flags_are_forwarded(self):
        with patch.object(self.subject, "prepare", return_value={"status": "synthetic_native_result"}) as prepare:
            code, _, _ = self.cli("--native", "--transcribe")
        self.assertEqual(code, 0)
        prepare.assert_called_once_with(self.record, self.fixture.windows, self.fixture.combined,
                                        self.fixture.source, self.repo, self.output, native=True, transcribe=True)


if __name__ == "__main__":
    unittest.main()
