import sys
from types import SimpleNamespace

from cutroom import transcription


def test_cuda_registration_keeps_handles_and_deduplicates_known_installed_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("ProgramFiles", raising=False)
    folder = tmp_path / "Programs/Ollama/lib/ollama/cuda_v12"
    folder.mkdir(parents=True)
    for name in ("cublas64_12.dll", "cublasLt64_12.dll"):
        (folder / name).write_bytes(b"synthetic registration fixture")
    calls = []
    handle = object()
    monkeypatch.setattr(transcription.os, "add_dll_directory", lambda path: calls.append(path) or handle, raising=False)
    monkeypatch.setattr(transcription, "_WINDOWS_CUDA_DLL_HANDLES", {})
    transcription._register_windows_cuda_runtime()
    transcription._register_windows_cuda_runtime()
    assert calls == [str(folder)]
    assert list(transcription._WINDOWS_CUDA_DLL_HANDLES.values()) == [handle]


def test_cuda_registration_skips_relative_or_incomplete_locations(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "relative-location")
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    folder = tmp_path / "Ollama/lib/ollama/cuda_v12"
    folder.mkdir(parents=True)
    (folder / "cublas64_12.dll").write_bytes(b"missing sibling fixture")
    calls = []
    monkeypatch.setattr(transcription.os, "add_dll_directory", lambda path: calls.append(path), raising=False)
    monkeypatch.setattr(transcription, "_WINDOWS_CUDA_DLL_HANDLES", {})
    transcription._register_windows_cuda_runtime()
    assert calls == []


def test_model_registers_cuda_before_construction_and_does_not_touch_cpu(monkeypatch):
    calls = []
    monkeypatch.setattr(transcription, "_MODEL_CACHE", {})
    monkeypatch.setattr(transcription, "_register_windows_cuda_runtime", lambda: calls.append("register"))
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=lambda *args, **kw: calls.append(kw["device"]) or object()))
    settings = SimpleNamespace(ai={"whisper_model": "synthetic-model"})
    transcription._load_model(settings, "cpu", "int8")
    transcription._load_model(settings, "cuda", "float16")
    transcription._load_model(settings, "cuda", "float16")
    assert calls == ["cpu", "register", "cuda"]
