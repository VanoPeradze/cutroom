"""Large original previews use bounded mocked preparation and real tiny hashes."""
from __future__ import annotations

import copy
import errno
import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import asset_preparation as cache_module
from cutroom import media_library as media
from cutroom.asset_preparation import PreparationCache, PreparationCacheError
from cutroom.jobs import JobCancelled
from cutroom.native_paths import native_io_path
from test_asset_preparation_cache import ASSET, context, setup as cache_setup


GIB = 1024**3
MP4_FORMAT = "mov,mp4,m4a,3gp,3g2,mj2"


def compatible_metadata(**changes):
    return {"kind": "video", "duration": 2.0, "width": 1920, "height": 1080, "has_audio": True,
            "video_codec": "h264", "audio_codec": "aac", "audio_channels": 2,
            "format": MP4_FORMAT, "pixel_format": "yuv420p", "rotation": 0, **changes}


@pytest.fixture
def large(cache_setup, monkeypatch):
    settings, store, pid, folder, old_source, _ = cache_setup
    source = folder / "original.mp4"
    old_source.rename(source)
    metadata = compatible_metadata()
    store.update(pid, lambda value: value["assets"][ASSET].update(
        name=source.name, path=source.relative_to(store.project_dir(pid)).as_posix(),
        **{key: metadata[key] for key in ("kind", "duration", "width", "height", "has_audio")}))
    env = SimpleNamespace(settings=settings, store=store, pid=pid, folder=folder, source=source,
                          metadata=metadata, reported_size=3 * GIB + 17, commands=[], probes=[], checks=[],
                          identities=[], build_hook=None, probe_hook=None)
    real_identity = cache_module.source_identity
    real_unchanged = cache_module.assert_source_unchanged

    def simulated_size_identity(path, asset, target_settings, check):
        _, identity = real_identity(path, asset, target_settings, check)
        # Only the branch-selection size is synthetic. File generation and
        # SHA-256 still describe the actual tiny bytes and are checked below.
        identity["file"]["size"] = env.reported_size
        key = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        env.identities.append((key, copy.deepcopy(identity)))
        return key, identity

    def unchanged(path, identity, check, *, content):
        env.checks.append(content)
        physical_identity = copy.deepcopy(identity)
        physical_identity["file"]["size"] = identity["file"]["generation"][2]
        return real_unchanged(path, physical_identity, check, content=content)

    def run(args, **kwargs):
        path = Path(args[-1])
        if args[0] == settings.ffprobe:
            assert path.is_file()
            # Production uses Windows' extended spelling. Normalize only the
            # recorder, proving that both spellings still name the same file.
            if path.samefile(env.source):
                recorded = env.source
            else:
                root = store.project_dir(pid)
                try:
                    relative = path.relative_to(native_io_path(root))
                except ValueError:
                    relative = path.relative_to(root)
                recorded = root / relative
            assert path.samefile(recorded)
            env.probes.append(recorded)
            if env.probe_hook:
                env.probe_hook(path)
            item = env.metadata
            thumbnail = path.name == "thumbnail.jpg"
            video = {"codec_type": "video", "codec_name": "mjpeg" if thumbnail else item["video_codec"],
                     "width": 320 if thumbnail else item["width"], "height": 180 if thumbnail else item["height"],
                     "pix_fmt": "yuvj420p" if thumbnail else item["pixel_format"],
                     "side_data_list": [{"rotation": 0 if thumbnail else item["rotation"]}]}
            streams = [video]
            if not thumbnail and item["has_audio"]:
                streams.append({"codec_type": "audio", "codec_name": item["audio_codec"], "channels": item["audio_channels"]})
            payload = {"streams": streams, "format": {"duration": str(item["duration"]),
                                                       "format_name": "image2" if thumbnail else item["format"]}}
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        # Full proxies and full-source PCM are forbidden in this fixture.
        assert args[0] == settings.ffmpeg
        if path.name != "thumbnail.jpg" or args[-1] == "pipe:1":
            pytest.fail("Large preparation must not transcode a full preview or extract a waveform")
        assert args[args.index("-frames:v") + 1] == "1" and "-an" in args
        assert kwargs["timeout"] <= 60 and kwargs["timeout"] > 0
        assert callable(kwargs.get("cancel_check"))
        env.commands.append((list(args), dict(kwargs)))
        path.write_bytes(b"SYNTHETIC-BOUNDED-THUMBNAIL")
        if env.build_hook:
            env.build_hook(path)
        kwargs["cancel_check"]()
        return subprocess.CompletedProcess(args, 0, "", "")

    def forbidden_builder(*_args, **_kwargs):
        pytest.fail("Large preparation must not enter the legacy full-preview builder")

    monkeypatch.setattr(media, "source_identity", simulated_size_identity)
    monkeypatch.setattr(media, "assert_source_unchanged", unchanged)
    monkeypatch.setattr(media, "run_command", run)
    monkeypatch.setattr(media, "_build_asset_preview", forbidden_builder)
    return env


def prepare(env, ctx=None):
    return media.prepare_asset(ctx or context(), env.pid, ASSET, env.store, env.settings)


def asset(env):
    return env.store.load(env.pid)["assets"][ASSET]


def generations(env):
    return sorted(path for path in env.folder.iterdir() if path.name.startswith(("prepared-", ".preparing-")))


def cache(env):
    ctx = context()
    return PreparationCache(env.store.project_dir(env.pid), env.folder, ctx.check_cancelled,
                            lambda path, kind: media._probe_prepared_asset(path, kind, asset(env), env.settings, ctx))


@pytest.mark.parametrize(("kind", "configured", "expected"), [
    ("video", 40 * GIB, 40 * GIB), ("video", GIB, GIB),
    ("audio", 40 * GIB, 512 * 1024**2), ("image", 40 * GIB, 32 * 1024**2),
], ids=["large-video", "configured-video", "audio-unchanged", "image-unchanged"])
def test_video_size_limit_uses_configuration_without_changing_other_media_caps(kind, configured, expected):
    assert media.asset_size_limit(kind, configured) == expected


@pytest.mark.parametrize(("suffix", "has_audio"), [(".mp4", True), (".m4v", False)], ids=["mp4-aac", "m4v-silent"])
def test_large_compatible_video_binds_original_and_caches_only_thumbnail_with_fresh_probe(large, suffix, has_audio):
    if large.source.suffix != suffix:
        changed = large.source.with_suffix(suffix)
        large.source.rename(changed)
        large.source = changed
    large.metadata.update(has_audio=has_audio, audio_codec="aac" if has_audio else None,
                          audio_channels=2 if has_audio else None)
    large.store.update(large.pid, lambda value: value["assets"][ASSET].update(
        path=large.source.relative_to(large.store.project_dir(large.pid)).as_posix(), has_audio=has_audio))
    original = large.source.read_bytes()

    assert prepare(large)["preparation_reused"] is False

    ready = asset(large)
    assert ready["status"] == "ready" and ready["preview_path"] == ready["path"]
    assert ready["preview_mode"] == "original" and ready["waveform"] == []
    assert large.probes[0] == large.source and len(large.commands) == 1
    final = large.store.project_dir(large.pid) / ready["thumbnail_path"]
    record = json.loads((final.parent / "manifest.json").read_text(encoding="utf-8"))
    assert record["preview_mode"] == "original" and record["original_preview"] == ready["path"]
    assert set(record["artifacts"]) == {"thumbnail.jpg"}
    assert record["identity"] == ready["preparation_identity"] == large.identities[-1][0]
    assert large.identities[-1][1]["file"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert {path.name for path in final.parent.iterdir()} == {"manifest.json", "thumbnail.jpg"}
    assert True in large.checks and False in large.checks
    assert large.source.read_bytes() == original


def test_reuse_reprobes_original_and_validates_thumbnail_without_rebuilding_or_waveform(large):
    prepare(large)
    ready = copy.deepcopy(asset(large))
    probes_before = len(large.probes)
    assert prepare(large)["preparation_reused"] is True
    assert len(large.commands) == 1
    assert large.probes[probes_before:] == [large.source, large.store.project_dir(large.pid) / ready["thumbnail_path"]]
    assert asset(large) == ready and len(generations(large)) == 1


@pytest.mark.parametrize(("suffix", "patch"), [
    (".mkv", {}), (".mp4", {"format": "matroska,webm"}),
    (".mp4", {"video_codec": "hevc"}), (".mp4", {"pixel_format": "yuv420p10le"}),
    (".mp4", {"audio_codec": "ac3"}), (".mp4", {"audio_channels": 6}),
    (".mp4", {"rotation": 90}),
], ids=["mkv", "renamed-container", "hevc", "ten-bit", "ac3", "surround", "rotation"])
def test_large_incompatible_original_fails_actionably_without_conversion_or_source_change(large, suffix, patch):
    if suffix != large.source.suffix:
        changed = large.source.with_suffix(suffix)
        large.source.rename(changed)
        large.source = changed
        large.store.update(large.pid, lambda value: value["assets"][ASSET].update(
            path=changed.relative_to(large.store.project_dir(large.pid)).as_posix()))
    large.metadata.update(patch)
    original = large.source.read_bytes()
    with pytest.raises(media.MediaLibraryError, match="MP4.*H.264"):
        prepare(large)
    assert asset(large)["status"] == "failed" and "preview_path" not in asset(large)
    assert not large.commands and not generations(large)
    assert large.source.read_bytes() == original


def test_fresh_original_probe_can_invalidate_a_previously_compatible_cached_binding(large):
    prepare(large)
    before = large.store.state_path(large.pid).read_bytes()
    large.metadata["video_codec"] = "hevc"
    with pytest.raises(media.MediaLibraryError, match="MP4.*H.264"):
        prepare(large)
    assert large.store.state_path(large.pid).read_bytes() == before
    assert len(large.commands) == 1 and len(generations(large)) == 1


def test_cancellation_during_incompatible_original_probe_remains_cancellation(large):
    ctx = context()
    large.metadata["video_codec"] = "hevc"
    large.probe_hook = lambda _path: ctx.job.cancel_event.set()
    with pytest.raises(JobCancelled):
        prepare(large, ctx)
    assert asset(large)["status"] == "cancelled" and "preview_path" not in asset(large)
    assert not large.commands and not generations(large)


def test_original_compatibility_does_not_introduce_a_1920_pixel_dimension_cap():
    assert media._original_video_preview_compatible(Path("original.mp4"), compatible_metadata(width=4096, height=2160)) is True


def test_probe_includes_container_pixel_format_rotation_and_channel_evidence(large):
    result = media.probe_asset(large.source, "video", large.settings, include_codecs=True)
    assert {key: result[key] for key in ("format", "pixel_format", "rotation", "audio_channels")} == {
        "format": MP4_FORMAT, "pixel_format": "yuv420p", "rotation": 0, "audio_channels": 2,
    }


@pytest.mark.parametrize("ready", [False, True], ids=["initial", "ready-refresh"])
def test_cancelled_original_thumbnail_cleans_owned_stage_and_preserves_ready_binding(large, ready):
    if ready:
        prepare(large)
        large.settings.raw["ffmpeg_threads"] += 1
    before = large.store.state_path(large.pid).read_bytes()
    original = large.source.read_bytes()
    ctx = context()
    def cancel(_target):
        ctx.job.cancel_event.set()
        raise JobCancelled("Job cancelled")
    large.build_hook = cancel
    with pytest.raises(JobCancelled):
        prepare(large, ctx)
    if ready:
        assert large.store.state_path(large.pid).read_bytes() == before
    else:
        assert asset(large)["status"] == "cancelled" and "preview_path" not in asset(large)
    assert len(generations(large)) == int(ready)
    assert large.source.read_bytes() == original


@pytest.mark.parametrize("stage", ["build", "validate"], ids=["during-thumbnail", "during-validation"])
def test_source_hash_change_never_binds_original_preview_or_leaves_unbound_generation(large, stage):
    changed = b"CHANGED-EXTERNALLY"
    if stage == "build":
        large.build_hook = lambda _target: large.source.write_bytes(changed)
    else:
        large.probe_hook = lambda path: large.source.write_bytes(changed) if path.name == "thumbnail.jpg" else None
    with pytest.raises(media.MediaLibraryError):
        prepare(large)
    assert asset(large)["status"] == "failed" and "preview_path" not in asset(large)
    assert large.source.read_bytes() == changed and not generations(large)


def test_newer_asset_binding_wins_cas_and_both_originals_survive(large):
    newer = large.folder / "newer.mp4"
    newer.write_bytes(b"NEWER-ORIGINAL")
    original = large.source.read_bytes()
    def replace_binding(_target):
        large.store.update(large.pid, lambda value: value["assets"][ASSET].update(
            path=newer.relative_to(large.store.project_dir(large.pid)).as_posix(), status="cancelled"))
    large.build_hook = replace_binding
    with pytest.raises(media.MediaLibraryError):
        prepare(large)
    current = asset(large)
    assert current["status"] == "cancelled" and current["path"].endswith("newer.mp4")
    assert "preview_path" not in current and not generations(large)
    assert newer.read_bytes() == b"NEWER-ORIGINAL" and large.source.read_bytes() == original


def test_full_source_hash_and_pipeline_changes_invalidate_original_thumbnail_cache(large):
    prepare(large)
    first = asset(large)["preparation_identity"]
    timestamp = large.source.stat()
    large.source.write_bytes(b"X" * timestamp.st_size)
    os.utime(large.source, ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
    assert prepare(large)["preparation_reused"] is False
    second = asset(large)["preparation_identity"]
    assert second != first
    large.settings.raw["ffmpeg_threads"] += 1
    assert prepare(large)["preparation_reused"] is False
    assert asset(large)["preparation_identity"] != second
    assert len(large.commands) == 3 and len(generations(large)) == 1


@pytest.mark.parametrize("damage", ["mode", "original-path", "thumbnail-hash", "thumbnail-metadata"],
                         ids=["mode", "path", "hash", "metadata"])
def test_cache_requires_original_mode_path_hash_and_probed_thumbnail_metadata(large, damage):
    prepare(large)
    ready = asset(large)
    final = (large.store.project_dir(large.pid) / ready["thumbnail_path"]).parent
    manifest = final / "manifest.json"
    record = json.loads(manifest.read_text(encoding="utf-8"))
    if damage == "mode":
        record["preview_mode"] = "prepared"
    elif damage == "original-path":
        record["original_preview"] = ready["path"].replace("original.mp4", "different.mp4")
    elif damage == "thumbnail-hash":
        (final / "thumbnail.jpg").write_bytes(b"X" * (final / "thumbnail.jpg").stat().st_size)
    else:
        record["artifacts"]["thumbnail.jpg"]["metadata"]["width"] = 999
    manifest.write_text(json.dumps(record), encoding="utf-8")
    assert cache(large).read(final, ready["preparation_identity"], "video", original_preview=ready["path"]) is None
    assert large.source.read_bytes() == b"SYNTHETIC-ORIGINAL"


@pytest.mark.parametrize("bad", ["../original.mp4", "/outside/original.mp4", "media/assets/other/original.mp4"],
                         ids=["traversal", "absolute", "foreign-folder"])
def test_cache_publish_rejects_unsafe_original_preview_without_touching_original(large, bad):
    instance = cache(large)
    stage = instance.new_stage()
    (stage / "thumbnail.jpg").write_bytes(b"SYNTHETIC-THUMBNAIL")
    original = large.source.read_bytes()
    with pytest.raises(PreparationCacheError):
        instance.publish(stage, "0" * 64, "video", [], original_preview=bad)
    assert instance.remove_owned(stage) is True
    assert large.source.read_bytes() == original


@pytest.mark.parametrize("invalid", ["missing", "directory", "symlink"], ids=["missing", "directory", "symlink"])
def test_cache_original_preview_requires_an_existing_regular_unlinked_file(large, invalid):
    selected = large.folder / f"invalid-{invalid}.mp4"
    if invalid == "directory":
        selected.mkdir()
    elif invalid == "symlink":
        try:
            selected.symlink_to(large.source)
        except OSError as error:
            if error.errno in {errno.EACCES, errno.EPERM} or getattr(error, "winerror", None) == 1314:
                pytest.skip("This account cannot create a test symlink")
            raise
    instance = cache(large)
    stage = instance.new_stage()
    (stage / "thumbnail.jpg").write_bytes(b"SYNTHETIC-THUMBNAIL")
    relative = selected.relative_to(large.store.project_dir(large.pid)).as_posix()
    original = large.source.read_bytes()
    with pytest.raises(PreparationCacheError):
        instance.publish(stage, "0" * 64, "video", [], original_preview=relative)
    assert instance.remove_owned(stage) is True
    assert large.source.read_bytes() == original


def test_late_logical_source_rebinding_is_rejected_before_ready_commit(large, monkeypatch):
    newer = large.folder / "newer.mp4"
    newer.write_bytes(b"DIFFERENT-ORIGINAL")
    original = large.source.read_bytes()
    selected_path = asset(large)["path"]
    real_publish, real_safe_path = PreparationCache.publish, media.safe_asset_path
    published = []

    def publish(instance, *args, **kwargs):
        result = real_publish(instance, *args, **kwargs)
        published.append(True)
        return result

    def rebound(project_dir, relative):
        result = real_safe_path(project_dir, relative)
        return newer if published and relative == selected_path else result

    monkeypatch.setattr(PreparationCache, "publish", publish)
    monkeypatch.setattr(media, "safe_asset_path", rebound)
    with pytest.raises(media.MediaLibraryError):
        prepare(large)
    assert published and asset(large)["status"] == "failed"
    assert "preview_path" not in asset(large) and not generations(large)
    assert large.source.read_bytes() == original and newer.read_bytes() == b"DIFFERENT-ORIGINAL"


def test_original_preview_cache_cleanup_removes_only_owned_thumbnail_generation(large):
    prepare(large)
    original = large.source.read_bytes()
    note = large.folder / "personal-note.txt"
    note.write_bytes(b"UNRELATED")
    instance = cache(large)
    assert len(instance.cleanup(large.store.load(large.pid))) == 1
    assert instance.cleanup({"assets": {ASSET: {"path": asset(large)["path"], "preview_path": asset(large)["path"]}}}) == []
    assert not generations(large)
    assert large.source.read_bytes() == original and note.read_bytes() == b"UNRELATED"


def test_exact_large_threshold_keeps_legacy_small_preview_path(large, monkeypatch):
    large.reported_size = 2 * GIB
    calls = []
    def build(_context, source, _asset, _settings, folder):
        calls.append(source)
        (folder / "preview.mp4").write_bytes(b"SYNTHETIC-SMALL-PREVIEW")
        (folder / "thumbnail.jpg").write_bytes(b"SYNTHETIC-SMALL-THUMBNAIL")
        return [.25, 1]
    monkeypatch.setattr(media, "_build_asset_preview", build)
    prepare(large)
    ready = asset(large)
    assert len(calls) == 1 and calls[0].samefile(large.source) and ready["preview_mode"] == "prepared"
    assert ready["preview_path"] != ready["path"] and ready["waveform"] == [.25, 1]
    assert large.source not in large.probes and not large.commands
