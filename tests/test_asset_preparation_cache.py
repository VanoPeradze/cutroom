from __future__ import annotations

import copy
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from cutroom import asset_preparation as cache_module
from cutroom import media_library as media
from cutroom.asset_preparation import PreparationCache, fingerprint, preparation_lock
from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom.projects import ProjectStateError, ProjectStore


ASSET = "asset_" + "c" * 32


def context():
    return JobContext(Job("job_preparation_cache", "prepare_asset", "unused"), threading.Lock())


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = replace(load_settings(), ffmpeg="synthetic-ffmpeg", ffprobe="synthetic-ffprobe")
    store = ProjectStore(settings)
    pid = store.create("Synthetic cache acceptance")["id"]
    folder = store.project_dir(pid) / "media" / "assets" / ASSET
    folder.mkdir(parents=True)
    source = folder / "original.wav"
    source.write_bytes(b"SYNTHETIC-ORIGINAL")
    asset = {"id": ASSET, "name": "original.wav", "path": source.relative_to(store.project_dir(pid)).as_posix(),
             "kind": "audio", "duration": 2.0, "width": 0, "height": 0, "has_audio": True, "status": "preparing"}
    store.update(pid, lambda value: value["assets"].update({ASSET: asset}))
    calls = {"encode": [], "probe": [], "hook": None, "probe_hook": None}

    def run(args, **kwargs):
        if args[0] == settings.ffprobe:
            path = Path(args[-1])
            assert path.is_file()
            calls["probe"].append(path)
            if calls["probe_hook"]:
                calls["probe_hook"](path)
            extension = path.suffix
            video = {"codec_type": "video", "width": 320 if path.name == "thumbnail.jpg" else 640,
                     "height": 180 if path.name == "thumbnail.jpg" else 360,
                     "codec_name": "mjpeg" if extension == ".jpg" else "png" if extension == ".png" else "h264"}
            streams = ([video] if extension in {".mp4", ".png", ".jpg"} else [])
            if extension in {".mp4", ".m4a"}:
                streams.append({"codec_type": "audio", "codec_name": "aac"})
            return subprocess.CompletedProcess(args, 0, json.dumps({"streams": streams, "format": {"duration": "2.0"}}), "")
        if args[-1] == "pipe:1":
            return subprocess.CompletedProcess(args, 0, b"\0\0\xe8\x03\x30\xf8", b"")
        target = Path(args[-1])
        calls["encode"].append(target)
        target.write_bytes(b"SYNTHETIC-PREPARED" + target.suffix.encode())
        if calls["hook"]:
            calls["hook"](target)
        if kwargs.get("cancel_check"):
            kwargs["cancel_check"]()
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(media, "run_command", run)
    return [settings, store, pid, folder, source, calls]


def prepare(setup, ctx=None):
    settings, store, pid, *_ = setup
    return media.prepare_asset(ctx or context(), pid, ASSET, store, settings)


def asset(setup):
    return setup[1].load(setup[2])["assets"][ASSET]


def generations(setup):
    return sorted(p for p in setup[3].iterdir() if p.name.startswith(("prepared-", ".preparing-")))


def test_reuses_only_complete_validated_generation_without_transcoding(setup):
    assert prepare(setup)["preparation_reused"] is False
    before = copy.deepcopy(asset(setup))
    assert before["status"] == "ready"
    assert before["waveform"] and max(before["waveform"]) == 1
    commands = len(setup[-1]["encode"])
    assert prepare(setup)["preparation_reused"] is True
    assert len(setup[-1]["encode"]) == commands
    assert len(setup[-1]["probe"]) == 2
    assert asset(setup)["preview_path"] == before["preview_path"]
    assert len(generations(setup)) == 1


def test_same_size_original_edit_with_restored_mtime_invalidates_cache(setup):
    prepare(setup)
    old = asset(setup)
    source = setup[4]
    timestamp = source.stat()
    source.write_bytes(b"CHANGED---ORIGINAL")
    assert source.stat().st_size == timestamp.st_size
    os.utime(source, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
    assert prepare(setup)["preparation_reused"] is False
    assert asset(setup)["preparation_identity"] != old["preparation_identity"]
    assert len(generations(setup)) == 1


def test_pipeline_option_change_invalidates_but_bounds_generations(setup):
    prepare(setup)
    original_identity = asset(setup)["preparation_identity"]
    for threads in range(5, 15):
        setup[0].raw["ffmpeg_threads"] = threads
        assert prepare(setup)["preparation_reused"] is False
        assert len(generations(setup)) == 1
    assert asset(setup)["preparation_identity"] != original_identity


def test_changed_ffmpeg_binary_identity_invalidates_cache(setup, tmp_path):
    executable = tmp_path / "synthetic-ffmpeg.exe"
    executable.write_bytes(b"tool-one")
    setup[0] = replace(setup[0], ffmpeg=str(executable))
    prepare(setup)
    previous = asset(setup)["preparation_identity"]
    executable.write_bytes(b"tool-two-updated")
    assert prepare(setup)["preparation_reused"] is False
    assert asset(setup)["preparation_identity"] != previous


@pytest.mark.parametrize("damage", ["truncate", "same_size", "missing_manifest", "corrupt_manifest"])
def test_corrupted_or_incomplete_cache_is_never_reused(setup, damage):
    prepare(setup)
    previous = asset(setup)
    preview = setup[1].project_dir(setup[2]) / previous["preview_path"]
    if damage == "truncate":
        preview.write_bytes(b"")
    elif damage == "same_size":
        preview.write_bytes(b"X" * preview.stat().st_size)
    elif damage == "missing_manifest":
        (preview.parent / "manifest.json").unlink()
    else:
        (preview.parent / "manifest.json").write_text("{incomplete", encoding="utf-8")
    assert prepare(setup)["preparation_reused"] is False
    assert asset(setup)["preview_path"] != previous["preview_path"]
    # Unverifiable ownership is retained for explicit local review.
    assert len(generations(setup)) == (2 if "manifest" in damage else 1)


def test_video_thumbnail_and_audio_are_required_before_ready(setup):
    setup[1].update(setup[2], lambda project: project["assets"][ASSET].update(kind="video", width=640, height=360))
    prepare(setup)
    previous = asset(setup)
    thumbnail = setup[1].project_dir(setup[2]) / previous["thumbnail_path"]
    thumbnail.unlink()
    assert prepare(setup)["preparation_reused"] is False
    assert len(generations(setup)) == 1
    assert (setup[1].project_dir(setup[2]) / asset(setup)["thumbnail_path"]).is_file()


@pytest.mark.parametrize("cancel", [False, True])
def test_failed_refresh_preserves_exact_ready_project_and_old_files(setup, cancel):
    prepare(setup)
    store, pid = setup[1:3]
    before = store.state_path(pid).read_bytes()
    previous = asset(setup)
    preview = store.project_dir(pid) / previous["preview_path"]
    old_bytes = preview.read_bytes()
    setup[0].raw["ffmpeg_threads"] += 1
    ctx = context()
    def fail(_target):
        if cancel:
            ctx.job.cancel_event.set()
            raise JobCancelled("Job cancelled")
        raise OSError("Synthetic encoder failure")
    setup[-1]["hook"] = fail
    with pytest.raises(JobCancelled if cancel else media.MediaLibraryError):
        prepare(setup, ctx)
    assert store.state_path(pid).read_bytes() == before
    assert preview.read_bytes() == old_bytes
    assert len(generations(setup)) == 1


@pytest.mark.parametrize("cancel", [False, True])
def test_initial_failure_cleans_only_owned_partials_and_sets_honest_status(setup, cancel):
    unrelated = setup[3] / "personal-note.txt"
    unrelated.write_bytes(b"do not change")
    ctx = context()
    def fail(_target):
        if cancel:
            raise JobCancelled("Job cancelled")
        raise OSError("Synthetic encoder failure")
    setup[-1]["hook"] = fail
    with pytest.raises(JobCancelled if cancel else media.MediaLibraryError):
        prepare(setup, ctx)
    assert asset(setup)["status"] == ("cancelled" if cancel else "failed")
    assert not generations(setup)
    assert unrelated.read_bytes() == b"do not change"
    assert setup[4].read_bytes() == b"SYNTHETIC-ORIGINAL"


def test_original_change_during_encode_never_publishes_ready(setup):
    setup[-1]["hook"] = lambda _target: setup[4].write_bytes(b"changed while preparing")
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert asset(setup)["status"] == "failed"
    assert "preview_path" not in asset(setup)
    assert not generations(setup)


def test_original_change_during_artifact_validation_removes_unbound_generation(setup):
    setup[-1]["probe_hook"] = lambda _path: setup[4].write_bytes(b"changed during validation")
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert asset(setup)["status"] == "failed"
    assert not generations(setup)


def test_binding_change_during_encode_does_not_overwrite_newer_asset(setup):
    newer_source = setup[3] / "newer.wav"
    newer_source.write_bytes(b"newer original")
    def change(_target):
        setup[1].update(setup[2], lambda project: project["assets"][ASSET].update(
            path=newer_source.relative_to(setup[1].project_dir(setup[2])).as_posix(), status="cancelled"))
    setup[-1]["hook"] = change
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert asset(setup)["status"] == "cancelled"
    assert asset(setup)["path"].endswith("newer.wav")
    assert "preview_path" not in asset(setup)
    assert not generations(setup)


def test_cancel_after_generation_publication_keeps_previous_ready_binding(setup, monkeypatch):
    prepare(setup)
    before = setup[1].state_path(setup[2]).read_bytes()
    setup[0].raw["ffmpeg_threads"] += 1
    ctx = context()
    publish = PreparationCache.publish
    def cancel(self, *args):
        result = publish(self, *args)
        ctx.job.cancel_event.set()
        return result
    monkeypatch.setattr(PreparationCache, "publish", cancel)
    with pytest.raises(JobCancelled):
        prepare(setup, ctx)
    assert setup[1].state_path(setup[2]).read_bytes() == before
    assert len(generations(setup)) == 1


def test_metadata_write_failure_keeps_old_generation_and_removes_new_one(setup, monkeypatch):
    prepare(setup)
    before = setup[1].state_path(setup[2]).read_bytes()
    original_update = setup[1].update
    setup[0].raw["ffmpeg_threads"] += 1
    def reject(project_id, mutator, *args, **kwargs):
        candidate = setup[1].load(project_id)
        mutator(candidate)
        raise OSError("Synthetic metadata write failure")
    monkeypatch.setattr(setup[1], "update", reject)
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    monkeypatch.setattr(setup[1], "update", original_update)
    assert setup[1].state_path(setup[2]).read_bytes() == before
    assert len(generations(setup)) == 1


def test_same_asset_concurrent_preparation_serializes_and_reuses(setup):
    started, release = threading.Event(), threading.Event()
    def pause(_target):
        started.set()
        assert release.wait(3)
    setup[-1]["hook"] = pause
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(prepare, setup)
        assert started.wait(3)
        second = pool.submit(prepare, setup)
        time.sleep(0.08)
        assert len(setup[-1]["encode"]) == 1
        release.set()
        assert first.result(timeout=5)["preparation_reused"] is False
        assert second.result(timeout=5)["preparation_reused"] is True
    assert len(setup[-1]["encode"]) == 1
    assert len(generations(setup)) == 1


def test_waiting_preparation_can_cancel_without_touching_ready_media(setup):
    prepare(setup)
    before = setup[1].state_path(setup[2]).read_bytes()
    ctx = context()
    with preparation_lock(setup[3], lambda: None), ThreadPoolExecutor(max_workers=1) as pool:
        waiting = pool.submit(prepare, setup, ctx)
        time.sleep(0.08)
        ctx.job.cancel_event.set()
        with pytest.raises(JobCancelled):
            waiting.result(timeout=2)
    assert setup[1].state_path(setup[2]).read_bytes() == before
    assert len(generations(setup)) == 1


def test_pinned_history_generations_are_retained_and_eight_is_a_safe_bound(setup):
    cache = PreparationCache(setup[1].project_dir(setup[2]), setup[3], lambda: None,
                             lambda path, kind: {"kind": kind})
    references = []
    for _ in range(8):
        stage = cache.new_stage()
        (stage / "preview.m4a").write_bytes(b"synthetic cached media")
        final, updates = cache.publish(stage, "0" * 64, "audio", [])
        references.append(updates["preview_path"])
    setup[1].update(setup[2], lambda project: project.update(legacy_history={"prepared_paths": references}))
    with pytest.raises(media.MediaLibraryError) as error:
        prepare(setup)
    assert "Eight media preparation generations" in str(error.value.__cause__)
    assert len(generations(setup)) == 8
    assert not setup[-1]["encode"]
    assert all((setup[1].project_dir(setup[2]) / reference).is_file() for reference in references)


def test_owned_recovery_rejects_unknown_files_and_never_deletes_them(setup):
    cache = PreparationCache(setup[1].project_dir(setup[2]), setup[3], lambda: None, lambda *_: {})
    stale = cache.new_stage()
    (stale / "preview.m4a").write_bytes(b"unfinished")
    unknown = cache.new_stage()
    (unknown / "unrelated.txt").write_bytes(b"untouched")
    cache.cleanup(setup[1].load(setup[2]))
    assert not stale.exists()
    assert (unknown / "unrelated.txt").read_bytes() == b"untouched"


def test_streaming_hash_has_cancellation_points_and_does_not_modify_source(tmp_path):
    source = tmp_path / "bounded.bin"
    source.write_bytes(b"X" * (cache_module.HASH_BLOCK_BYTES * 2 + 5))
    before = source.stat()
    count = 0
    def cancel():
        nonlocal count
        count += 1
        if count == 3:
            raise JobCancelled("cancelled while hashing")
    with pytest.raises(JobCancelled):
        fingerprint(source, cancel)
    assert count == 3
    assert source.stat().st_size == before.st_size
    assert source.stat().st_mtime_ns == before.st_mtime_ns


def test_cache_directory_and_output_links_cannot_escape_asset_root(setup):
    project_dir = setup[1].project_dir(setup[2])
    with pytest.raises(ValueError, match="Invalid media preparation directory"):
        PreparationCache(project_dir, project_dir / "media" / "outside", lambda: None, lambda *_: {})
    cache = PreparationCache(project_dir, setup[3], lambda: None, lambda *_: {})
    stage = cache.new_stage()
    target = project_dir / "unrelated.txt"
    target.write_bytes(b"untouched")
    try:
        (stage / "preview.m4a").symlink_to(target)
    except OSError:
        pytest.skip("This Windows account cannot create symbolic links")
    assert cache.remove_owned(stage) is False
    assert target.read_bytes() == b"untouched"
    with pytest.raises(ValueError, match="Invalid prepared media file"):
        cache.publish(stage, "0" * 64, "audio", [])


@pytest.mark.parametrize("damage", ["missing", "cache_init"])
@pytest.mark.parametrize("ready", [False, True], ids=["initial", "refresh"])
def test_failure_before_hashing_records_initial_failure_but_preserves_ready_bytes(setup, monkeypatch, damage, ready):
    if ready:
        prepare(setup)
    store, pid = setup[1:3]
    if damage == "missing":
        setup[4].unlink()
    else:
        def reject_cache(*_args, **_kwargs):
            raise cache_module.PreparationCacheError("Synthetic cache initialization failure")
        monkeypatch.setattr(media, "PreparationCache", reject_cache)
    before = store.state_path(pid).read_bytes()
    old_generations = generations(setup)
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    if ready:
        assert store.state_path(pid).read_bytes() == before
    else:
        assert asset(setup)["status"] == "failed"
        assert "preview_path" not in asset(setup)
    assert generations(setup) == old_generations


@pytest.mark.parametrize("ready", [False, True], ids=["initial", "refresh"])
def test_unsafe_persisted_path_is_rejected_without_rewriting_project_or_media(setup, ready):
    if ready:
        prepare(setup)
    store, pid = setup[1:3]
    store.update(pid, lambda project: project["assets"][ASSET].update(path="outside.wav"))
    before = store.state_path(pid).read_bytes()
    old_generations = generations(setup)
    commands = len(setup[-1]["encode"])
    with pytest.raises(media.MediaLibraryError) as caught:
        prepare(setup)
    assert isinstance(caught.value.__cause__, ProjectStateError)
    assert store.state_path(pid).read_bytes() == before
    assert generations(setup) == old_generations
    assert len(setup[-1]["encode"]) == commands


@pytest.mark.parametrize("waiting_outcome", ["busy", "cancelled"])
def test_waiter_failure_does_not_change_active_initial_preparation(setup, monkeypatch, waiting_outcome):
    before = setup[1].state_path(setup[2]).read_bytes()

    @contextmanager
    def blocked_lock(*_args):
        if waiting_outcome == "cancelled":
            raise JobCancelled("Synthetic waiting cancellation")
        raise cache_module.PreparationBusy("Synthetic busy owner")
        yield  # pragma: no cover -- context manager never acquires this asset.

    monkeypatch.setattr(media, "preparation_lock", blocked_lock)
    with pytest.raises(JobCancelled if waiting_outcome == "cancelled" else media.MediaLibraryError):
        prepare(setup)
    assert setup[1].state_path(setup[2]).read_bytes() == before
    assert not generations(setup)
    assert not setup[-1]["encode"]


def test_fatal_lock_setup_failure_does_not_leave_new_asset_preparing(setup, monkeypatch):
    @contextmanager
    def unavailable_lock(*_args):
        raise OSError("Synthetic unavailable lock directory")
        yield  # pragma: no cover

    monkeypatch.setattr(media, "preparation_lock", unavailable_lock)
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert asset(setup)["status"] == "failed"
    assert not setup[-1]["encode"]


@pytest.mark.parametrize("change", [
    {"status": "ready"}, {"status": "cancelled"}, {"kind": "video"}, {"duration": 3.0},
    {"width": 640}, {"height": 360}, {"has_audio": False}, {"preparation_identity": "newer-identity"},
    {"preview_path": "media/assets/newer/preview.m4a"}, {"thumbnail_path": "media/assets/newer/thumbnail.jpg"},
])
def test_newer_binding_or_status_is_not_overwritten_or_resaved_after_rejection(setup, change):
    saved_bytes = []
    store, pid = setup[1:3]

    def replace_binding(_target):
        store.update(pid, lambda project: project["assets"][ASSET].update(change))
        saved_bytes.append(store.state_path(pid).read_bytes())

    setup[-1]["hook"] = replace_binding
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert len(saved_bytes) == 1
    assert store.state_path(pid).read_bytes() == saved_bytes[0]
    assert all(asset(setup)[key] == value for key, value in change.items())
    assert not generations(setup)


def test_repeated_initial_failure_does_not_resave_already_failed_status(setup):
    setup[4].unlink()
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    before = setup[1].state_path(setup[2]).read_bytes()
    with pytest.raises(media.MediaLibraryError):
        prepare(setup)
    assert setup[1].state_path(setup[2]).read_bytes() == before


def test_first_lock_does_not_write_into_another_owners_byte_region(setup):
    path = setup[3] / ".preparation.lock"
    assert not path.exists()
    with preparation_lock(setup[3], lambda: None):
        first_identity = path.stat().st_ino
        assert path.stat().st_size == 0
    with preparation_lock(setup[3], lambda: None):
        assert path.stat().st_ino == first_identity
        assert path.stat().st_size == 0
