from __future__ import annotations

import io
import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

import server
from cutroom.config import load_settings
from cutroom.jobs import Job, JobCancelled, JobContext
from cutroom import local_models


def _speech_files(cache: Path, model="small", *, complete=True):
    folder = cache / ("models--" + local_models._WHISPER_REPOS[model].replace("/", "--"))
    commit = "a" * 40
    (folder / "refs").mkdir(parents=True)
    (folder / "refs" / "main").write_text(commit)
    snapshot = folder / "snapshots" / commit
    snapshot.mkdir(parents=True)
    for filename in ["config.json", "tokenizer.json", "vocabulary.txt"] + (["model.bin"] if complete else []):
        (snapshot / filename).write_text("test")
    return snapshot


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "huggingface"))
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "ollama"))
    return load_settings(tmp_path / "missing.json")


def test_inventory_reads_files_without_network_or_inference(settings, monkeypatch):
    _speech_files(local_models.speech_cache_dir())
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    monkeypatch.setattr(server, "open_ollama", lambda *_a, **_k: pytest.fail("Inventory contacted a server"))
    monkeypatch.setattr(local_models.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Inventory launched a process"))
    result = local_models.catalog(settings, {"state": "idle", "models": []}, engine_installed=False)
    rows = {row["model"]: row for row in result["models"]}
    assert rows["small"]["installed"] is True
    assert rows["small"]["can_download"] is False
    assert rows["base"]["can_download"] is True
    assert rows["qwen3.5:4b"]["can_download"] is False
    assert result["runtime"]["install_url"] == "https://ollama.com/download"
    assert result["runtime"]["installed"] is False
    assert "Speech models do not require Ollama" in result["runtime"]["message"]
    assert rows["ivrit-ai/whisper-large-v3-turbo-ct2"]["profiles"] == ["quality · Hebrew"]


def test_partial_cache_and_invalid_revision_are_not_installed(settings):
    snapshot = _speech_files(local_models.speech_cache_dir(), complete=False)
    assert not local_models.speech_installed("small")
    (snapshot / "model.bin").write_bytes(b"complete")
    assert local_models.speech_installed("small")
    (snapshot.parent.parent / "refs" / "main").write_text("../../outside")
    assert not local_models.speech_installed("small")


def test_story_status_verifies_manifest_blobs_not_just_filename(settings, monkeypatch):
    root = Path(local_models.os.environ["OLLAMA_MODELS"])
    path = root / "manifests/registry.ollama.ai/library/qwen3.5/4b"
    path.parent.mkdir(parents=True)
    digest = "sha256:" + "b" * 64
    path.write_text(json.dumps({"config": {"digest": digest, "size": 4}, "layers": [{"digest": digest, "size": 4}]}))
    assert not local_models._story_installed("qwen3.5:4b", {})
    blob = root / "blobs" / digest.replace(":", "-")
    blob.parent.mkdir()
    blob.write_bytes(b"data")
    assert local_models._story_installed("qwen3.5:4b", {})
    assert local_models._story_installed("qwen3.5:9b", {"models": ["qwen3.5:9b"]})


def test_custom_models_do_not_become_arbitrary_download_targets(settings):
    settings.ai["whisper_models"]["balanced"] = "private/repo"
    result = local_models.catalog(settings, {}, engine_installed=True)
    assert all(row["model"] != "private/repo" for row in result["models"])
    assert any("custom configured" in note for note in result["notes"])
    assert not local_models.supported_install("transcription", "private/repo")


def _context():
    return JobContext(Job("download-test", "model_install", None), threading.Lock())


def _process(output="", *, running=False, code=0):
    result = SimpleNamespace(stdout=io.StringIO(output), running=running, terminated=False, killed=False)
    result.poll = lambda: None if result.running else code
    def wait(timeout=None):
        result.running = False
        return code
    def terminate():
        result.terminated = True
        result.running = False
    result.wait = wait
    result.terminate = terminate
    result.kill = lambda: setattr(result, "killed", True)
    return result


def test_download_uses_shared_cache_and_fixed_worker_without_loading_model(settings, monkeypatch):
    states = iter([False, True])
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: next(states))
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    monkeypatch.setattr(local_models.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10**12))
    process = _process(json.dumps({"event": "progress", "fraction": 0.5, "completed": 500, "total": 1000, "unit": "B"}) + "\n")
    calls = []
    monkeypatch.setattr(local_models.subprocess, "Popen", lambda argv, **kw: calls.append((argv, kw)) or process)
    context = _context()
    result = local_models.install_transcription(context, "small", settings)
    assert result == {"kind": "transcription", "model": "small", "installed": True}
    argv, kwargs = calls[0]
    assert argv[-3:] == ["cutroom.local_models", "--download", "small"]
    assert kwargs["env"]["HF_HUB_DISABLE_IMPLICIT_TOKEN"] == "1"
    assert kwargs["env"]["HF_HUB_DISABLE_XET"] == "1"
    assert kwargs["env"]["HF_HUB_CACHE"] == str(local_models.speech_cache_dir())
    assert context.job.progress == 1


def test_download_cancel_terminates_network_worker(settings, monkeypatch):
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: False)
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    monkeypatch.setattr(local_models.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10**12))
    context = _context()
    process = _process(running=True)
    def launch(*_args, **_kwargs):
        context.job.cancel_event.set()
        return process
    monkeypatch.setattr(local_models.subprocess, "Popen", launch)
    with pytest.raises(JobCancelled):
        local_models.install_transcription(context, "small", settings)
    assert process.terminated


def test_download_failure_is_actionable_and_does_not_expose_remote_response(settings, monkeypatch):
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: False)
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    monkeypatch.setattr(local_models.shutil, "disk_usage", lambda _path: SimpleNamespace(free=10**12))
    process = _process('private-secret-log\n{"event":"error","code":"download"}\n', code=1)
    monkeypatch.setattr(local_models.subprocess, "Popen", lambda *_a, **_k: process)
    with pytest.raises(RuntimeError, match="Check your connection") as error:
        local_models.install_transcription(_context(), "small", settings)
    assert "secret" not in str(error.value)


def test_download_checks_space_before_start_and_skips_complete_model(settings, monkeypatch):
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: False)
    monkeypatch.setattr(local_models, "_dependency_available", lambda _name: True)
    monkeypatch.setattr(local_models.shutil, "disk_usage", lambda _path: SimpleNamespace(free=1))
    monkeypatch.setattr(local_models.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Started without disk space"))
    with pytest.raises(RuntimeError, match="free space"):
        local_models.install_transcription(_context(), "small", settings)
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: True)
    assert local_models.install_transcription(_context(), "small", settings)["already_installed"]


def test_worker_uses_public_weights_only_and_emits_real_progress(settings, monkeypatch, capsys):
    import huggingface_hub
    snapshot = _speech_files(local_models.speech_cache_dir())
    calls = []
    def download(repo, **kwargs):
        calls.append((repo, kwargs))
        with kwargs["tqdm_class"](total=100, unit="B") as progress:
            progress.update(50)
            progress.update(50)
        return str(snapshot)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    assert local_models._download_worker("small") == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["event"] == "complete"
    assert any(event.get("fraction") == 0.5 and event["completed"] == 50 for event in events)
    repo, kwargs = calls[0]
    assert repo == "Systran/faster-whisper-small"
    assert kwargs["token"] is False
    assert kwargs["endpoint"] == "https://huggingface.co"
    assert "*.py" not in kwargs["allow_patterns"]
    assert kwargs["cache_dir"] == str(local_models.speech_cache_dir())


def test_worker_rejects_partial_success_and_unknown_models(settings, monkeypatch, capsys):
    import huggingface_hub
    snapshot = _speech_files(local_models.speech_cache_dir(), complete=False)
    monkeypatch.setattr(huggingface_hub, "snapshot_download", lambda *_a, **_kw: str(snapshot))
    assert local_models._download_worker("small") == 1
    assert json.loads(capsys.readouterr().out)["code"] == "download"
    assert local_models._download_worker("unknown/private") == 2


def test_profile_choice_never_changes_when_models_are_downloaded(settings, monkeypatch):
    original = json.dumps(settings.raw, sort_keys=True)
    monkeypatch.setattr(local_models, "speech_installed", lambda _model: True)
    local_models.install_transcription(_context(), "turbo", settings)
    assert json.dumps(settings.raw, sort_keys=True) == original


@pytest.fixture
def app(settings, monkeypatch):
    runtime = SimpleNamespace(snapshot=lambda: {"state": "idle", "available": False, "models": []},
                              ensure_ready=lambda **_kw: {"state": "ready", "available": True})
    monkeypatch.setattr(server, "AIRuntime", lambda _settings: runtime)
    monkeypatch.setattr(server, "resolve_ollama_executable", lambda: None)
    application = server.create_app(settings)
    application.config["TESTING"] = True
    yield application
    application.extensions["cutroom_jobs"].shutdown(wait=True, cancel_pending=True)


def test_catalog_api_is_read_only_and_includes_global_download_jobs(app, monkeypatch):
    monkeypatch.setattr(server, "open_ollama", lambda *_a, **_k: pytest.fail("Network on inventory"))
    client = app.test_client()
    result = client.get("/api/models/local")
    assert result.status_code == 200
    assert result.json["jobs"] == []
    assert result.json["models"]
    assert app.extensions["cutroom_jobs"].active() == []


@pytest.mark.parametrize("payload", [
    {"kind": "transcription", "model": "private/repo"},
    {"kind": "editor", "model": "other/model"},
    {"kind": "transcription", "model": "../outside"},
    {"kind": "unknown", "model": "small"},
    {"kind": "transcription", "model": []},
])
def test_install_api_rejects_unapproved_targets(app, payload):
    response = app.test_client().post("/api/models/install", json=payload)
    assert response.status_code == 400
    assert app.extensions["cutroom_jobs"].active() == []


def test_install_api_supports_polling_cancel_recovery_and_deduplication(app, monkeypatch):
    started = threading.Event()
    def download(context, model, _settings):
        started.set()
        context.update(0.25, "Downloading model files")
        while True:
            context.cancellable_wait(0.05)
    monkeypatch.setattr(server, "install_transcription", download)
    client = app.test_client()
    body = {"kind": "transcription", "model": "small"}
    response = client.post("/api/models/install", json=body)
    assert response.status_code == 202
    assert started.wait(2)
    job_id = response.json["job"]["id"]
    assert client.post("/api/models/install", json=body).json["job"]["id"] == job_id
    assert client.post("/api/models/install", json={"kind": "transcription", "model": "base"}).status_code == 409
    assert client.get("/api/models/local").json["jobs"][0]["id"] == job_id
    cancellation = client.post(f"/api/jobs/{job_id}/cancel", json={})
    # A cooperative worker can stop before the route constructs its response:
    # 202 means winding down; 200 also succeeds when cancellation is immediate.
    assert cancellation.status_code in {200, 202}
    assert cancellation.json["ok"] is True
    assert cancellation.json["accepted"] is True
    assert cancellation.json["job"]["cancel_requested"] is True
    for _ in range(100):
        if app.extensions["cutroom_jobs"].get(job_id).status == "cancelled":
            break
        time.sleep(0.01)
    assert app.extensions["cutroom_jobs"].get(job_id).status == "cancelled"
    repeated = client.post(f"/api/jobs/{job_id}/cancel", json={})
    assert repeated.status_code == 200
    assert repeated.json["accepted"] is False
    assert repeated.json["job"]["status"] == "cancelled"


def test_install_api_cannot_overlap_processing(app):
    job = app.extensions["cutroom_jobs"].submit("director", "project-test", lambda context: context.cancellable_wait(5))
    response = app.test_client().post("/api/models/install", json={"kind": "transcription", "model": "small"})
    assert response.status_code == 409
    assert response.json["active_job_id"] == job.id


def test_install_api_keeps_same_origin_and_body_size_guards(app):
    client = app.test_client()
    assert client.post("/api/models/install", json={"model": "small"}, headers={"Origin": "https://untrusted.example"}).status_code == 403
    assert client.post("/api/models/install", data='"' + 'a' * server.JSON_BODY_LIMIT + '"', content_type="application/json").status_code == 413
