from __future__ import annotations

import copy
import threading
from pathlib import Path
from types import SimpleNamespace

from cutroom import render
from cutroom.jobs import Job, JobContext


class MemoryStore:
    def __init__(self, root: Path, project: dict):
        self.root = root
        self.project = project

    def project_dir(self, _project_id: str) -> Path:
        return self.root

    def load(self, _project_id: str) -> dict:
        return copy.deepcopy(self.project)

    def save(self, project: dict, expected_revision=None) -> dict:
        self.project = copy.deepcopy(project)
        return project

    def update(self, _project_id: str, mutator, expected_revision=None) -> dict:
        project = copy.deepcopy(self.project)
        replacement = mutator(project)
        self.project = copy.deepcopy(project if replacement is None else replacement)
        return copy.deepcopy(self.project)


def test_render_removes_export_files_that_fall_out_of_retention(monkeypatch, tmp_path: Path):
    project_root = tmp_path / "project"
    exports = tmp_path / "exports"
    (project_root / "media").mkdir(parents=True)
    exports.mkdir()
    (project_root / "media" / "source-A.mp4").write_bytes(b"source")

    old_exports = []
    for index in range(20):
        name = f"old-{index}.mp4"
        captions_name = f"old-{index}.srt"
        (exports / name).write_bytes(b"video")
        (exports / captions_name).write_text("caption", encoding="utf-8")
        old_exports.append({"name": name, "captions_name": captions_name})
    project = {
        "id": "project_012345abcdef",
        "name": "storage-test",
        "sources": {
            "A": {
                "relative_path": "media/source-A.mp4",
                "duration": 1.0,
                "has_audio": False,
            },
            "B": None,
        },
        "settings": {"quality": "lite", "burn_captions": False, "captions": False},
        "analysis": None,
        "draft": {
            "keep_ranges": [{"start": 0.0, "end": 1.0}],
            "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "A"}],
        },
        "exports": old_exports,
    }
    store = MemoryStore(project_root, project)
    settings = SimpleNamespace(
        exports_dir=exports,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        raw={"ffmpeg_threads": 2, "render": {"prefer_hardware": False}},
        render={"audio_bitrate": "128k"},
    )

    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", ["-preset", "veryfast"]))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(
        render,
        "probe_media",
        lambda path, _settings: {"width": 320, "height": 240, "duration": 1.0, "fps": 30, "size": path.stat().st_size},
    )

    def fake_run(_context, command, _expected):
        Path(command[-1]).write_bytes(b"rendered")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_test", "render", project["id"]), threading.Lock())
    render.render_project(context, project["id"], store, settings)

    assert len(store.project["exports"]) == 20
    assert not (exports / "old-19.mp4").exists()
    assert not (exports / "old-19.srt").exists()
    assert (exports / "old-0.mp4").exists()


def test_failed_final_probe_does_not_leave_an_orphan_export(monkeypatch, tmp_path: Path):
    project_root = tmp_path / "project"
    exports = tmp_path / "exports"
    (project_root / "media").mkdir(parents=True)
    exports.mkdir()
    (project_root / "media" / "source-A.mp4").write_bytes(b"source")
    project = {
        "id": "project_012345abcdef",
        "name": "orphan-test",
        "sources": {"A": {"relative_path": "media/source-A.mp4", "duration": 1.0, "has_audio": False}, "B": None},
        "settings": {"quality": "lite", "burn_captions": False, "captions": False},
        "analysis": None,
        "draft": {"keep_ranges": [{"start": 0.0, "end": 1.0}], "camera_plan": [{"start": 0.0, "end": 1.0, "camera": "A"}]},
        "exports": [],
    }
    store = MemoryStore(project_root, project)
    settings = SimpleNamespace(
        exports_dir=exports,
        ffmpeg="ffmpeg",
        ffprobe="ffprobe",
        raw={"ffmpeg_threads": 2, "render": {"prefer_hardware": False}},
        render={"audio_bitrate": "128k"},
    )
    monkeypatch.setattr(render, "_dimensions", lambda *_args: (320, 240))
    monkeypatch.setattr(render, "choose_encoder", lambda *_args: ("libx264", []))
    monkeypatch.setattr(render, "build_filter_graph", lambda *_args: ("null", ["-map", "[vout]"], False))
    monkeypatch.setattr(render, "probe_media", lambda *_args: (_ for _ in ()).throw(ValueError("bad output")))

    def fake_run(_context, command, _expected):
        Path(command[-1]).write_bytes(b"broken")
        return 0, ""

    monkeypatch.setattr(render, "_run_ffmpeg_process", fake_run)
    context = JobContext(Job("job_test", "render", project["id"]), threading.Lock())

    try:
        render.render_project(context, project["id"], store, settings)
    except ValueError as error:
        assert str(error) == "bad output"
    else:
        raise AssertionError("probe failure should propagate")

    assert list(exports.iterdir()) == []
