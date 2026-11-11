"""Offline contracts for Hebrew-first profiles and resource-aware local fallback.

Synthetic transcripts, fake runtime probes: these tests do not measure ASR accuracy.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from cutroom import local_models, transcription
from cutroom.config import Settings
from cutroom.jobs import JobCancelled

HEBREW = "ivrit-ai/whisper-large-v3-turbo-ct2"
_REAL_RAM_PROBE = transcription._available_cpu_memory_mb
_REAL_SPEECH_INSTALLED = local_models.speech_installed


@pytest.fixture
def settings(tmp_path):
    return Settings({"ai": {
        "whisper_model": "base", "whisper_models": {"lite": "base", "balanced": "small", "quality": "turbo"},
        "hebrew_whisper_model": HEBREW, "whisper_device": "auto", "whisper_compute_type": "auto",
    }}, tmp_path, tmp_path, tmp_path, tmp_path, tmp_path, "ffmpeg", "ffprobe")


@pytest.fixture(autouse=True)
def no_real_hardware(monkeypatch):
    monkeypatch.delenv("CUTROOM_FAKE_TRANSCRIPT", raising=False)
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    monkeypatch.delenv("CUDA_DEVICE_ORDER", raising=False)
    monkeypatch.setattr(transcription, "cuda_available", lambda _settings=None: True)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cuda", "float16"))
    monkeypatch.setattr(transcription, "_available_cpu_memory_mb", lambda: 16384.0)
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="12000\n"))
    monkeypatch.setattr(local_models, "speech_installed", lambda model: True)


def decode_stub(calls, failure=None):
    def decode(*args, **kwargs):
        calls.append((args, kwargs))
        if failure and len(calls) == 1:
            raise failure
        return {"model": args[2], "device": args[3], "compute_type": args[4],
                "language": args[5] or "en", "language_probability": 0.99,
                "segments": [], "words": [], "text": ""}
    return decode


@pytest.mark.parametrize("mode", ["balanced", "quality"])
@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_explicit_hebrew_uses_ivrit_cached_only(monkeypatch, settings, mode, device):
    calls = []
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: (device, "int8" if device == "cpu" else "float16"))
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode=mode)
    assert calls[0][0][2] == HEBREW
    assert calls[0][1]["local_files_only"] is True
    assert value["execution"]["actual_model"] == value["requested_model"] == HEBREW
    assert value["execution"]["model_policy"] == "hebrew-balanced-quality-v2"


@pytest.mark.parametrize("mode,language,expected", [
    ("lite", "he", "base"), ("balanced", "en", "small"), ("quality", "en", "turbo"),
])
def test_other_language_profiles_unchanged(settings, mode, language, expected):
    assert transcription._model_for_request(settings, mode, language, "cpu") == expected


@pytest.mark.parametrize("free", [4096, 6143, 0])
@pytest.mark.parametrize("configured", ["auto", "cuda"])
def test_hebrew_large_model_headroom_not_balanced_small_budget(monkeypatch, settings, free, configured):
    settings.ai.update(whisper_device=configured, whisper_cuda_min_free_mb={"balanced": 1, "quality": 1})
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=f"{free}\n"))
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="balanced")
    assert calls[0][0][2:5] == (HEBREW, "cpu", "int8")
    assert value["resource_fallback"] == "large_model_cuda_headroom"
    assert "large_model_cpu_may_be_slow" in value["execution"]["resource_warnings"]


@pytest.mark.parametrize("stdout,returncode", [("", 0), ("nan\n", 0), ("12000\n12000\n", 0), ("12000\n", 1)])
def test_uncertain_gpu_does_not_claim_large_model_ready(monkeypatch, settings, stdout, returncode):
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=returncode, stdout=stdout))
    assert transcription._model_resource_check(settings, HEBREW, "cuda", "float16")[:3] == ("cpu", "int8", "large_model_cuda_headroom")


@pytest.mark.parametrize("variable", ["CUDA_VISIBLE_DEVICES", "CUDA_DEVICE_ORDER"])
def test_remapped_gpu_does_not_guess_headroom(monkeypatch, settings, variable):
    monkeypatch.setenv(variable, "0")
    assert transcription._model_resource_check(settings, HEBREW, "cuda", "float16")[0] == "cpu"


def test_cpu_known_insufficient_memory_refuses_without_decode(monkeypatch, settings):
    monkeypatch.setattr(transcription, "_available_cpu_memory_mb", lambda: 4095.0)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cpu", "int8"))
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls))
    with pytest.raises(RuntimeError, match="4 GiB available RAM"):
        transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="balanced")
    assert not calls


def test_unknown_cpu_memory_is_reported_not_claimed_ready(monkeypatch, settings):
    monkeypatch.setattr(transcription, "_available_cpu_memory_mb", lambda: None)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cpu", "int8"))
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub([]))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="quality")
    assert "cpu_memory_unverified" in value["execution"]["resource_warnings"]


def test_cuda_error_retries_same_hebrew_model_on_cpu(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls, RuntimeError("synthetic device failure")))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="balanced")
    assert [call[0][2:5] for call in calls] == [(HEBREW, "cuda", "float16"), (HEBREW, "cpu", "int8")]
    assert all(call[1]["local_files_only"] for call in calls)
    assert value["resource_fallback"] == "device_error"


def test_cancellation_never_retries_a_model(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls, JobCancelled("cancel")))
    with pytest.raises(JobCancelled):
        transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="balanced")
    assert len(calls) == 1


def test_auto_without_cached_ivrit_keeps_small_without_download(monkeypatch, settings):
    monkeypatch.setattr(local_models, "speech_installed", lambda model: model == "small")
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="auto")
    assert calls[0][0][2] == "small"
    assert value["model"] == "small"
    assert len(calls) == 1


@pytest.mark.parametrize("language", ["he", "auto"])
def test_auto_busy_gpu_does_not_move_large_model_to_low_ram_cpu(monkeypatch, settings, language):
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="2000\n"))
    monkeypatch.setattr(transcription, "_available_cpu_memory_mb", lambda: 1024.0)
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cpu", "int8"))
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls))
    transcription._transcribe_in_process(Path("synthetic.wav"), settings, language, performance_mode="auto", duration=3600)
    assert calls[0][0][2:5] == ("base", "cpu", "int8")


def test_missing_hebrew_model_never_calls_loader_or_download(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: False)
    monkeypatch.setattr(transcription, "_MODEL_CACHE", {})
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *args, **kwargs: calls.append(args)))
    with pytest.raises(RuntimeError, match="Setup > Local models"):
        transcription._load_model(settings, "cpu", "int8", HEBREW)
    assert not calls


def test_cached_hebrew_enforces_offline_even_without_caller_flag(monkeypatch, settings):
    calls = []
    monkeypatch.setattr(transcription, "_MODEL_CACHE", {})
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *args, **kwargs: calls.append(kwargs)))
    transcription._load_model(settings, "cpu", "int8", HEBREW)
    assert calls[0]["local_files_only"] is True


def test_fallback_snapshot_uses_exact_model_and_preserves_settings(monkeypatch, settings):
    before = copy.deepcopy(settings.raw)
    checked = []
    monkeypatch.setattr(transcription.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(local_models, "speech_installed", lambda model: checked.append(model) or True)
    frozen = transcription.local_cached_fallback_settings(settings, "he", "balanced")
    assert frozen.ai["whisper_local_files_only"] is True
    assert settings.raw == before
    assert frozen.raw is not settings.raw
    assert HEBREW in checked


@pytest.mark.parametrize("runtime,cache", [(False, True), (True, False)])
def test_fallback_not_ready_is_actionable_before_upload(monkeypatch, settings, runtime, cache):
    monkeypatch.setattr(transcription.importlib.util, "find_spec", lambda _name: object() if runtime else None)
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: cache)
    with pytest.raises(RuntimeError, match="[Ss]etup"):
        transcription.local_cached_fallback_settings(settings, "he", "balanced")


def test_fallback_rejects_known_low_cpu_ram(monkeypatch, settings):
    monkeypatch.setattr(transcription.importlib.util, "find_spec", lambda _name: object())
    monkeypatch.setattr(transcription, "_resolve_device", lambda *_args: ("cpu", "int8"))
    monkeypatch.setattr(transcription, "_available_cpu_memory_mb", lambda: 512)
    with pytest.raises(RuntimeError, match="4 GiB"):
        transcription.local_cached_fallback_settings(settings, "he", "balanced")


def test_catalog_lists_hebrew_for_both_profiles(monkeypatch, settings):
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    row = next(row for row in local_models.catalog(settings, {}, engine_installed=False)["models"] if row["model"] == HEBREW)
    assert row["profiles"] == ["balanced · Hebrew", "quality · Hebrew"]
    assert "Download here before first use" in row["description"]


@pytest.mark.parametrize("platform,output,expected", [
    ("darwin", "Mach Virtual Memory Statistics: (page size of 16384 bytes)\nPages free: 65536.\nPages inactive: 131072.\nPages speculative: 32768.\n", 3584.0),
    ("darwin", "unexpected output", None),
    ("linux", "MemTotal: 10240000 kB\nMemAvailable: 5242880 kB\n", 5120.0),
    ("linux", "MemFree: 100 kB\n", None),
    ("unknown-os", "", None),
])
def test_ram_probe_parsers(monkeypatch, platform, output, expected):
    # Restore the real function, independently of the autouse routing fixture.
    real_probe = _REAL_RAM_PROBE
    monkeypatch.setattr(transcription.sys, "platform", platform)
    monkeypatch.setattr(transcription.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=output))
    monkeypatch.setattr(Path, "read_text", lambda *_a, **_k: output)
    assert real_probe() == expected


def test_windows_ram_probe_uses_available_physical_bytes(monkeypatch):
    import ctypes
    def available(pointer):
        pointer._obj.avail_phys = 5 * 1024 * 1024 * 1024
        return 1
    monkeypatch.setattr(transcription.sys, "platform", "win32")
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=available)), raising=False)
    assert _REAL_RAM_PROBE() == 5120.0


def test_complete_custom_local_model_supports_offline_cache_check(monkeypatch, tmp_path):
    folder = tmp_path / "custom-model"
    folder.mkdir()
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"):
        (folder / name).write_text("synthetic")
    assert _REAL_SPEECH_INSTALLED(str(folder))
    (folder / "model.bin").write_bytes(b"")
    assert not _REAL_SPEECH_INSTALLED(str(folder))


def test_custom_huggingface_model_cache_is_read_without_network(monkeypatch, tmp_path):
    monkeypatch.setattr(local_models, "speech_cache_dir", lambda: tmp_path)
    root = tmp_path / "models--example--custom-whisper"
    revision = "a" * 40
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text(revision)
    snapshot = root / "snapshots" / revision
    snapshot.mkdir(parents=True)
    for name in ("config.json", "model.bin", "tokenizer.json", "vocabulary.json"):
        (snapshot / name).write_text("synthetic")
    assert _REAL_SPEECH_INSTALLED("example/custom-whisper")
    assert not _REAL_SPEECH_INSTALLED("../custom-whisper")


@pytest.mark.parametrize("model", ["base", "small", "Systran/faster-whisper-base"])
def test_caption_override_does_not_make_a_light_model_large(settings, model):
    settings.ai["hebrew_whisper_model"] = model
    assert not transcription._large_speech_model(settings, model)


def test_cancellation_is_checked_before_resource_probes(monkeypatch, settings):
    monkeypatch.setattr(transcription, "_local_request_plan", lambda *_a, **_k: pytest.fail("probed after cancellation"))
    def cancelled():
        raise JobCancelled("cancel")
    with pytest.raises(JobCancelled):
        transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", cancel_check=cancelled)


@pytest.mark.parametrize("duration,expected", [(30, "small"), (3600, "base")])
def test_auto_cuda_execution_failure_uses_light_cpu_model(monkeypatch, settings, duration, expected):
    calls = []
    monkeypatch.setattr(transcription, "_transcribe_once", decode_stub(calls, RuntimeError("synthetic CUDA error")))
    value = transcription._transcribe_in_process(Path("synthetic.wav"), settings, "he", performance_mode="auto", duration=duration)
    assert calls[0][0][2:5] == (HEBREW, "cuda", "float16")
    assert calls[1][0][2:5] == (expected, "cpu", "int8")
    assert value["execution"]["actual_model"] == expected
    assert value["resource_fallback"] == "device_error"
