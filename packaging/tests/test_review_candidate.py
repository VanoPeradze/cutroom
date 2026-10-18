"""Offline, synthetic qualification checks; no CUTROOM/build code is imported."""
from __future__ import annotations

import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
OVERLAYS = {
    "packaging/mac/START CUTROOM.command": "mac/START CUTROOM.command",
    "packaging/mac/START HERE.html": "mac/START HERE.html",
    "packaging/mac/setup_macos.sh": "mac/App/setup_macos.sh",
    "packaging/mac/run_macos.sh": "mac/App/run_macos.sh",
    "packaging/mac/preflight_macos.py": "mac/App/preflight_macos.py",
    "packaging/mac/constraints-macos.txt": "mac/App/constraints-macos.txt",
    "docs/MAC_BETA.md": "mac/App/docs/MAC_BETA.md",
}
NOT_INCLUDED = ["user media", "projects", "logs", "local config", "runtimes", "models"]
WINDOWS_MANIFEST = "App/TEST_BUILD.json"
COMBINED_MANIFEST = "mac/App/TEST_BUILD.json"
ROOT_FILES = ("server.py", "requirements.txt", "README.md", "LICENSE", "run_windows.bat", "setup_windows.ps1", "package-info.json")
SUPPORT_FILES = ("tests/requirements.txt",)
DOC_FILES = ("docs/GUIDE.md",)
IMAGE_FILES = ("docs/images/editor.png",)
PACKAGING_FILES = ("packaging/windows/START CUTROOM.bat", "packaging/windows/START HERE.html")
SOURCE_TREES = {"cutroom": {".py"}, "web": {".js", ".html"}, "scripts": {".py"}, "tests": {".py", ".cjs"}}
START_TEXT = "CUTROOM {version_label}\nOffline qualification fixture.\n"
DEFAULTS = {"host": "0.0.0.0", "port": 1, "data_dir": "unused", "open_browser": False, "ai": {}, "render": {}}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def clean_temp(directory: tempfile.TemporaryDirectory) -> None:
    path = Path(directory.name).resolve()
    parent = Path(tempfile.gettempdir()).resolve()
    if not path.is_relative_to(parent) or not path.name.startswith("cutroom-qualification-tests-"):
        raise RuntimeError("Refusing cleanup outside the named synthetic test directory")
    directory.cleanup()


def write_zip(path: Path, files: dict[str, bytes], *, comment: bytes = b"", modes: dict[str, int] | None = None,
              extras: tuple[tuple[str, bytes], ...] = ()) -> None:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.comment = comment
        for name, data in [*sorted(files.items()), *extras]:
            item = zipfile.ZipInfo(name)
            item.create_system = 3
            item.compress_type = zipfile.ZIP_DEFLATED
            permissions = 0o755 if name.endswith((".sh", ".command")) else 0o644
            item.external_attr = (modes or {}).get(name, stat.S_IFREG | permissions) << 16
            archive.writestr(item, data)


def read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        return {item.filename: archive.read(item) for item in archive.infolist()}


def snapshot(root: Path) -> dict[str, str]:
    return {path.relative_to(root).as_posix(): digest(path.read_bytes())
            for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


class ReviewCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        spec = importlib.util.spec_from_file_location("cutroom_review_candidate_under_test", ROOT / "packaging/verify_review_candidate.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("Qualification verifier is unavailable")
        cls.verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.verifier)
        cls.base_temp = tempfile.TemporaryDirectory(prefix="cutroom-qualification-tests-template-")
        cls.addClassCleanup(clean_temp, cls.base_temp)
        cls.template = Path(cls.base_temp.name)
        repo = cls.template / "repo"
        repo.mkdir()
        cls.source_files = cls.make_source()
        for name, data in cls.source_files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        git_env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
                   "GIT_TERMINAL_PROMPT": "0"}
        def git(*args: str) -> str:
            result = subprocess.run(["git", "-c", "core.autocrlf=false", "-c", "core.hooksPath=" + str(cls.template / "no-hooks"),
                                     "-c", "commit.gpgsign=false", "-c", "user.name=Qualification fixture",
                                     "-c", "user.email=fixture@example.invalid", *args], cwd=repo, env=git_env,
                                    check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.stdout.decode("utf-8").strip()
        git("init", "--quiet")
        git("add", "--all")
        git("commit", "--quiet", "-m", "Synthetic frozen source A")
        cls.commit = git("rev-parse", "HEAD")
        cls.tree = git("rev-parse", "HEAD^{tree}")
        write_zip(cls.template / "source.zip", cls.source_files, comment=cls.commit.encode("ascii"))
        payload_names = set(ROOT_FILES + SUPPORT_FILES + DOC_FILES + IMAGE_FILES + PACKAGING_FILES)
        for name in cls.source_files:
            path = Path(name)
            if any(name.startswith(top + "/") and path.suffix in suffixes for top, suffixes in SOURCE_TREES.items()):
                payload_names.add(name)
        cls.payload = {name: cls.source_files[name] for name in payload_names}
        defaults = copy.deepcopy(DEFAULTS)
        defaults.update(host="127.0.0.1", port=8765, data_dir="data", open_browser=True)
        defaults["ai"].update(ollama_url="http://127.0.0.1:11434", download_models_on_setup=False)
        cls.payload["config.json"] = json_bytes(defaults)
        cls.payload["START_TESTING.txt"] = START_TEXT.format(version_label="1.2 Beta").replace("\n", "\r\n").encode("ascii")
        windows = {"App/" + name: data for name, data in cls.payload.items()}
        windows.update({Path(name).name: cls.source_files[name] for name in PACKAGING_FILES})
        windows[WINDOWS_MANIFEST] = json_bytes(cls.windows_manifest(windows))
        write_zip(cls.template / "windows.zip", windows)
        combined = cls.combined_files(windows)
        write_zip(cls.template / "combined.zip", combined)

    @staticmethod
    def make_source() -> dict[str, bytes]:
        files = {name: ("Synthetic source: " + name + "\n").encode() for name in ROOT_FILES + SUPPORT_FILES + DOC_FILES + IMAGE_FILES + PACKAGING_FILES}
        files.update({
            "cutroom/__init__.py": b'__version__ = "1.2-beta"\n__version_label__ = "1.2 Beta"\nraise RuntimeError("App imports forbidden")\n',
            "cutroom/config.py": ("DEFAULTS: dict = " + repr(DEFAULTS) + "\nraise RuntimeError('App imports forbidden')\n").encode(),
            "cutroom/editor.py": b"VALUE = 'frozen A'\n",
            "web/app.js": b"const fixture = 'frozen A';\n",
            "tests/fixture.cjs": b"// No tests are executed by qualification.\n",
            "config.json": b'{"not_a_package_input":true}\n',
            "docs/images/editor.png": b"\x89PNG\r\n\x1a\nsynthetic-binary\r\n",
            "run_windows.bat": b"@echo off\r\nexit /b 0\r\n",
            "setup_windows.ps1": b"Write-Output 'fixture'\r\n",
        })
        constants = {"ROOT_FILES": ROOT_FILES, "SUPPORT_FILES": SUPPORT_FILES, "DOC_FILES": DOC_FILES,
                     "IMAGE_FILES": IMAGE_FILES, "PACKAGING_FILES": PACKAGING_FILES, "SOURCE_TREES": SOURCE_TREES,
                     "START_TEXT": START_TEXT, "WINDOWS_LAYOUT": "windows-app-folder-v1", "WINDOWS_LAUNCHER": "START CUTROOM.bat",
                     "WINDOWS_HELP": "START HERE.html", "WINDOWS_SOURCE_DIRECTORY": "App"}
        files["scripts/build_test_package.py"] = ("\n".join(name + " = " + repr(value) for name, value in constants.items())
                                                  + "\nraise RuntimeError('Builder imports forbidden')\n").encode()
        files["scripts/build_universal_package.py"] = ("MAC_OVERLAY = " + repr(OVERLAYS)
                                                       + "\nraise RuntimeError('Builder imports forbidden')\n").encode()
        for source in OVERLAYS:
            files[source] = b"#!/bin/bash\r\nexit 0\r\n" if source.endswith((".sh", ".command")) else ("Synthetic Mac overlay: " + source + "\r\n").encode()
        return files

    @staticmethod
    def windows_manifest(files: dict[str, bytes]) -> dict:
        return {"build_id": "CUTROOM-1.2-beta-unit-windows", "app_version": "1.2-beta", "app_version_label": "1.2 Beta",
                "kind": "public-source-beta", "layout": "windows-app-folder-v1", "archive_root": "", "source_directory": "App",
                "launcher": "START CUTROOM.bat", "help": "START HERE.html", "created_utc": "2026-10-18T00:00:00+00:00",
                "target": "Windows x64 first-run testing; no bundled runtime", "clean_machine_install_verified": False,
                "configuration": "fresh application defaults, loopback only", "not_included": list(NOT_INCLUDED),
                "files": {name: digest(data) for name, data in sorted(files.items()) if name != WINDOWS_MANIFEST}}

    @classmethod
    def combined_files(cls, windows: dict[str, bytes]) -> dict[str, bytes]:
        files = {"windows/" + name: data for name, data in windows.items()}
        files.update({"mac/" + name: data for name, data in windows.items() if name.startswith("App/") and name != WINDOWS_MANIFEST})
        files.update({destination: cls.source_files[source].replace(b"\r\n", b"\n") for source, destination in OVERLAYS.items()})
        windows_bytes_path = cls.template / "windows.zip"
        manifest = {"build_id": "CUTROOM-1.2-beta-mac-unit", "app_version": "1.2-beta", "app_version_label": "1.2 Beta",
                    "layout": "windows-mac-folders-v1", "kind": "public-source-beta", "created_utc": "2026-10-18T00:00:00+00:00",
                    "windows_baseline_sha256": digest(windows_bytes_path.read_bytes()), "windows_files_unchanged": True,
                    "mac_manual_install_verified": False,
                    "mac_target": "macOS 15+, Apple Silicon and Intel; CPU transcription; unnotarized source launcher",
                    "not_included": list(NOT_INCLUDED), "files": {name: digest(data) for name, data in sorted(files.items())}}
        files[COMBINED_MANIFEST] = json_bytes(manifest)
        return files

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cutroom-qualification-tests-case-")
        self.addCleanup(clean_temp, self.temp)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        shutil.copytree(self.template / "repo", self.repo)
        self.windows = self.root / "windows.zip"
        self.combined = self.root / "combined.zip"
        self.source = self.root / "source.zip"
        for path in (self.windows, self.combined, self.source):
            shutil.copyfile(self.template / path.name, path)
        self.record = {"schema_version": 1, "kind": "cutroom-private-review-candidate", "published": False,
                       "qualified_for_release": False, "native_candidate_status": "pending",
                       "source": {"commit": self.commit, "tree": self.tree, "archive_sha256": digest(self.source.read_bytes()),
                                  "archive_bytes": self.source.stat().st_size, "files": len(self.source_files)},
                       "windows": {}, "combined": {}}
        self.repin()

    def repin(self) -> None:
        for key, path, manifest_name in (("windows", self.windows, WINDOWS_MANIFEST), ("combined", self.combined, COMBINED_MANIFEST)):
            files = read_zip(path)
            self.record[key] = {"bytes": path.stat().st_size, "sha256": digest(path.read_bytes()),
                                "manifest_sha256": digest(files[manifest_name]), "build_id": json.loads(files[manifest_name])["build_id"]}

    def rewrite_combined(self, mutate=lambda files: None, *, modes=None, extras=()) -> None:
        files = read_zip(self.combined)
        mutate(files)
        manifest = json.loads(files[COMBINED_MANIFEST])
        manifest["files"] = {name: digest(data) for name, data in sorted(files.items()) if name != COMBINED_MANIFEST}
        files[COMBINED_MANIFEST] = json_bytes(manifest)
        write_zip(self.combined, files, modes=modes, extras=extras)
        self.repin()

    def rewrite_windows(self, mutate) -> None:
        files = read_zip(self.windows)
        mutate(files)
        manifest = json.loads(files[WINDOWS_MANIFEST])
        manifest["files"] = {name: digest(data) for name, data in sorted(files.items()) if name != WINDOWS_MANIFEST}
        files[WINDOWS_MANIFEST] = json_bytes(manifest)
        write_zip(self.windows, files)
        combined = self.combined_files(files)
        cm = json.loads(combined[COMBINED_MANIFEST])
        cm["windows_baseline_sha256"] = digest(self.windows.read_bytes())
        combined[COMBINED_MANIFEST] = json_bytes(cm)
        write_zip(self.combined, combined)
        self.repin()

    def qualify(self):
        return self.verifier.qualify(self.record, self.windows, self.combined, self.source, self.repo)

    def reject(self) -> None:
        with self.assertRaises(self.verifier.QualificationError):
            self.qualify()

    def cli_with_pass_sentinel(self, output: Path):
        record_path = self.root / "review-record.json"
        record_path.write_bytes(json_bytes(self.record))
        arguments = ["--record", str(record_path), "--windows-zip", str(self.windows),
                     "--combined-zip", str(self.combined), "--source-archive", str(self.source),
                     "--repo", str(self.repo), "--output", str(output)]
        sentinel = {"verdict": "passed_private_review_source_gate", "published": False,
                    "qualified_for_release": False, "native_candidate_status": "pending"}
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(self.verifier, "qualify", return_value=sentinel) as qualify:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                try:
                    code = self.verifier.main(arguments)
                except SystemExit as error:
                    code = error.code
        return code, qualify, stdout.getvalue(), stderr.getvalue(), sentinel

    def test_cli_rejects_new_package_source_outputs_before_qualification(self):
        for name in ("web/new.js", "cutroom/new.py", "web/new.json", "cutroom/new.json", "scripts/new.json", "tests/new.json"):
            with self.subTest(name=name):
                output = self.repo / name
                code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
                self.assertNotEqual(code, 0, "Unsafe output accepted; created=" + str(output.exists()))
                qualify.assert_not_called()
                self.assertFalse(output.exists())

    def test_cli_allows_a_new_json_report_in_ignored_dist(self):
        output = self.repo / "dist/qualification.json"
        output.parent.mkdir()
        code, qualify, stdout, _, sentinel = self.cli_with_pass_sentinel(output)
        self.assertEqual(code, 0)
        qualify.assert_called_once_with(self.record, self.windows, self.combined, self.source, self.repo)
        self.assertEqual(json.loads(output.read_bytes()), sentinel)
        self.assertEqual(json.loads(stdout), sentinel)

    def test_cli_refuses_existing_output_without_qualifying_or_overwriting(self):
        output = self.repo / "dist/qualification.json"
        output.parent.mkdir()
        original = b'{"previous_report":true}\n'
        output.write_bytes(original)
        code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
        self.assertNotEqual(code, 0)
        qualify.assert_not_called()
        self.assertEqual(output.read_bytes(), original)

    def test_cli_rejects_non_json_report_before_qualification(self):
        output = self.root / "qualification.txt"
        code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
        self.assertNotEqual(code, 0)
        qualify.assert_not_called()
        self.assertFalse(output.exists())

    def test_cli_protects_required_overlay_and_input_paths_before_qualification(self):
        # A missing required JSON input must not become an apparently valid
        # report merely because the output is new and has the right extension.
        for name in ("package-info.json", "packaging/mac/preflight_macos.py"):
            with self.subTest(name=name):
                output = self.repo / name
                original = output.read_bytes()
                output.unlink()
                code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
                self.assertNotEqual(code, 0)
                qualify.assert_not_called()
                self.assertFalse(output.exists())
                output.write_bytes(original)
        record_path = self.root / "review-record.json"
        record_path.write_bytes(json_bytes(self.record))
        for output in (record_path, self.windows, self.combined, self.source):
            with self.subTest(input=output.name):
                original = output.read_bytes()
                code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
                self.assertNotEqual(code, 0)
                qualify.assert_not_called()
                self.assertEqual(output.read_bytes(), original)

    def test_cli_resolved_alias_into_package_tree_is_rejected(self):
        # Model a directory alias without requiring Windows symlink privileges.
        output = self.root / "outside-report.json"
        destination = self.repo / "web/aliased-report.json"
        original_resolve = Path.resolve
        def resolve(path, *args, **kwargs):
            if path == output:
                return destination
            return original_resolve(path, *args, **kwargs)
        with patch.object(Path, "resolve", resolve):
            code, qualify, _, _, _ = self.cli_with_pass_sentinel(output)
        self.assertNotEqual(code, 0)
        qualify.assert_not_called()
        self.assertFalse(output.exists())
        self.assertFalse(destination.exists())

    def test_valid_pair_is_read_only_and_cannot_claim_release_or_native_qa(self):
        before = snapshot(self.root)
        result = self.qualify()
        self.assertIsInstance(result, dict)
        self.assertEqual(snapshot(self.root), before)
        self.assertIs(result.get("published"), False)
        self.assertIs(result.get("qualified_for_release"), False)
        self.assertEqual(result.get("native_candidate_status"), "pending")

    def test_declared_utf8_text_allows_only_crlf_lf_conversion(self):
        path = self.repo / "README.md"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.qualify()

    def test_bat_ps1_and_binary_inputs_are_byte_exact(self):
        for name in ("run_windows.bat", "setup_windows.ps1", "docs/images/editor.png"):
            with self.subTest(name=name):
                path = self.repo / name
                original = path.read_bytes()
                path.write_bytes(original.replace(b"\r\n", b"\n"))
                self.reject()
                path.write_bytes(original)

    def test_excluded_verifier_files_do_not_change_product_input_inventory(self):
        for name in ("packaging/verify_review_candidate.py", "packaging/tests/test_review_candidate.py"):
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"# Excluded qualification tooling.\n")
        self.qualify()

    def test_current_local_config_is_not_packaged_or_executed(self):
        (self.repo / "config.json").write_bytes(b'{"secret":"PRIVATE_SENTINEL"}\n')
        self.qualify()
        self.assertNotIn(b"PRIVATE_SENTINEL", b"".join(read_zip(self.windows).values()))

    def test_archive_and_manifest_pins_are_independently_required(self):
        for target, key in (("windows", "sha256"), ("combined", "sha256"), ("windows", "manifest_sha256"), ("combined", "manifest_sha256")):
            with self.subTest(target=target, key=key):
                before = copy.deepcopy(self.record)
                self.record[target][key] = "0" * 64
                self.reject()
                self.record = before

    def test_previous_self_consistent_pair_cannot_replace_the_pinned_candidate(self):
        current_record = copy.deepcopy(self.record)
        self.rewrite_windows(lambda files: files.__setitem__("App/server.py", b"# Previous product source.\n"))
        self.record = current_record
        self.reject()

    def test_rehashed_application_and_generated_payload_tampering_is_rejected(self):
        for name, data in (("App/server.py", b"# Changed source.\n"), ("App/config.json", b'{"host":"0.0.0.0"}\n'),
                           ("App/START_TESTING.txt", b"Changed first-run guidance\r\n")):
            with self.subTest(name=name):
                self.setUp_archive_pair()
                self.rewrite_windows(lambda files: files.__setitem__(name, data))
                self.reject()

    def setUp_archive_pair(self):
        for path in (self.windows, self.combined):
            shutil.copyfile(self.template / path.name, path)
        self.repin()

    def test_every_category_of_current_source_input_is_bound(self):
        names = ("server.py", "requirements.txt", "scripts/build_test_package.py", "tests/fixture.cjs", "docs/GUIDE.md",
                 "docs/images/editor.png", "packaging/windows/START HERE.html", "packaging/mac/preflight_macos.py")
        for name in names:
            with self.subTest(name=name):
                path = self.repo / name
                original = path.read_bytes()
                path.write_bytes(original + b"changed")
                self.reject()
                path.write_bytes(original)

    def test_added_and_deleted_allowed_input_paths_are_rejected(self):
        extra = self.repo / "cutroom/extra.py"
        extra.write_bytes(b"NEW = True\n")
        self.reject()
        extra.unlink()
        required = self.repo / "docs/GUIDE.md"
        required.unlink()
        self.reject()

    def test_rehashed_mac_overlay_or_shared_app_tampering_is_rejected(self):
        for name in ("mac/App/preflight_macos.py", "mac/App/server.py"):
            with self.subTest(name=name):
                self.setUp_archive_pair()
                self.rewrite_combined(lambda files: files.__setitem__(name, b"changed\n"))
                self.reject()

    def test_private_extra_entry_is_rejected_even_when_rehashed(self):
        self.rewrite_combined(lambda files: files.__setitem__("mac/App/data/projects/private.json", b"PRIVATE_SENTINEL"))
        self.reject()

    def test_launcher_permissions_and_special_bits_are_rejected(self):
        for mode in (stat.S_IFREG | 0o644, stat.S_IFREG | 0o4755, stat.S_IFLNK | 0o755):
            with self.subTest(mode=oct(mode)):
                self.setUp_archive_pair()
                self.rewrite_combined(modes={"mac/START CUTROOM.command": mode})
                self.reject()

    def test_duplicate_unsafe_and_file_directory_collisions_are_rejected(self):
        cases = (("mac/App/server.py", b"duplicate"), ("mac/App/SERVER.py", b"case collision"),
                 ("mac/../private.txt", b"traversal"), ("mac/App/server.py/child", b"collision"))
        for name, data in cases:
            with self.subTest(name=name):
                self.setUp_archive_pair()
                self.rewrite_combined(extras=((name, data),))
                self.reject()

    def test_source_archive_needs_real_git_content_and_exact_inventory(self):
        for change in ("modified", "extra", "comment"):
            with self.subTest(change=change):
                files = dict(self.source_files)
                comment = self.commit.encode("ascii")
                if change == "modified": files["server.py"] += b"changed"
                elif change == "extra": files["cutroom/extra.py"] = b"unexpected\n"
                else: comment = b"0" * 40
                write_zip(self.source, files, comment=comment)
                self.record["source"].update(archive_bytes=self.source.stat().st_size, archive_sha256=digest(self.source.read_bytes()), files=len(files))
                self.reject()

    def test_git_replace_refs_cannot_rewrite_frozen_blob_identity(self):
        replacement = b"# Synthetic replacement blob; not in frozen source A.\n"
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        def git(*args, data=None):
            return subprocess.run(["git", "-C", str(self.repo), *args], input=data, env=env, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()
        original_oid = git("rev-parse", self.commit + ":server.py")
        replacement_oid = git("hash-object", "-w", "--stdin", data=replacement)
        git("replace", original_oid, replacement_oid)
        (self.repo / "server.py").write_bytes(replacement)
        source = dict(self.source_files)
        source["server.py"] = replacement
        write_zip(self.source, source, comment=self.commit.encode("ascii"))
        self.record["source"].update(archive_bytes=self.source.stat().st_size, archive_sha256=digest(self.source.read_bytes()))
        self.rewrite_windows(lambda files: files.__setitem__("App/server.py", replacement))
        self.reject()

    def test_source_commit_tree_and_record_types_fail_closed(self):
        changes = (("source", "commit", "0" * 40), ("source", "tree", "0" * 40), ("source", "archive_bytes", True),
                   ("source", "files", 0), ("windows", "bytes", -1), ("combined", "build_id", "different"))
        for section, key, value in changes:
            with self.subTest(section=section, key=key):
                before = copy.deepcopy(self.record)
                self.record[section][key] = value
                self.reject()
                self.record = before
        self.record["schema_version"] = True
        self.reject()

    def test_record_cannot_promote_publication_release_or_native_state(self):
        for key, value in (("published", True), ("qualified_for_release", True), ("native_candidate_status", "passed"),
                           ("kind", "public-release")):
            with self.subTest(key=key):
                before = copy.deepcopy(self.record)
                self.record[key] = value
                self.reject()
                self.record = before

    def test_json_parser_rejects_duplicate_keys_and_nonfinite_numbers(self):
        for raw in (b'{"source":{"commit":"first","commit":"second"}}',
                    b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}'):
            with self.subTest(raw=raw):
                with self.assertRaises(self.verifier.QualificationError):
                    self.verifier.parse_json(raw)


if __name__ == "__main__":
    unittest.main()
