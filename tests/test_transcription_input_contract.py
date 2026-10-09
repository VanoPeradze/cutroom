import json
import threading

import pytest

from cutroom import director, transcription
from cutroom.config import load_settings
from cutroom.intelligence import StoryPlanningError
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore


@pytest.mark.parametrize('audio_duration', [None, 0, -1, 'bad', float('nan'), float('inf')])
def test_unknown_audio_extent_never_shortens_required_coverage(audio_duration):
    assert director._transcription_duration({'has_audio': True, 'audio_duration': audio_duration}, 45) == 45


@pytest.mark.parametrize('language', ['he', 'en'])
@pytest.mark.parametrize('incomplete', [False, True])
def test_director_uses_audio_extent_and_retains_failure_before_gate(tmp_path, monkeypatch, language, incomplete):
    monkeypatch.setenv('CUTROOM_DATA_DIR', str(tmp_path / 'data'))
    settings = load_settings()
    settings.ai['visual_ai'] = 'off'
    store = ProjectStore(settings)
    project = store.create('Audio extent regression')
    media = store.project_dir(project['id']) / 'media' / 'source-A.mp4'
    media.write_bytes(b'isolated mock media')

    def attach(p):
        p['sources']['A'] = {'relative_path': 'media/source-A.mp4', 'name': 'fixture.mp4',
                             'duration': 45, 'audio_duration': 30, 'has_audio': True,
                             'width': 320, 'height': 180, 'size': media.stat().st_size}
        p['settings'].update(goal='short', spoken_language=language, performance_mode='quality', auto_reframe=False)
    store.update(project['id'], attach)
    before = store.load(project['id'])
    durations = []

    def transcribe(_source, _settings, **kwargs):
        durations.append(kwargs['duration'])
        chunks = [{'start': 0, 'end': 30, 'analyzed_end': 10 if incomplete else 30,
                   'status': 'failed' if incomplete else 'complete'}]
        coverage = transcription._coverage_from_chunks(30, chunks, 1, 'decoder_exhaustion')
        if incomplete:
            error = transcription.TranscriptionIncomplete('native decoder failed', coverage)
            error.diagnostics = {'returncode': 42, 'stderr': 'specific native failure', 'traceback': 'worker traceback'}
            raise error
        return {'duration': 30, 'language': language, 'language_probability': 1,
                'text': 'A clear sentence with enough words to build a useful story.',
                'segments': [{'start': 1, 'end': 8, 'text': 'A clear sentence with enough words to build a useful story.', 'avg_logprob': -.2}],
                'coverage': coverage}

    monkeypatch.setattr(director, 'transcribe', transcribe)
    monkeypatch.setattr(director, 'cuda_available', lambda *_: False)
    monkeypatch.setattr(director, 'analyze_audio', lambda *_a, **_kw: {'available': False, 'ranges': {}, 'summary': {}})
    monkeypatch.setattr(director, 'detect_scenes', lambda *_a, **_kw: [])
    original_gate = director._assert_transcript_complete

    class GatePassed(Exception):
        pass

    def gate(quality):
        original_gate(quality)
        raise GatePassed

    monkeypatch.setattr(director, '_assert_transcript_complete', gate)
    context = JobContext(Job('job_audio_extent', 'director', project['id']), threading.Lock())
    with pytest.raises(StoryPlanningError if incomplete else GatePassed):
        director.analyze_project(context, project['id'], store, settings)
    assert durations == [30]
    after = store.load(project['id'])
    assert after == before  # The gate must never replace drafts or manual edits.
    files = list((store.project_dir(project['id']) / 'analysis-diagnostics').glob('*.json'))
    if incomplete:
        assert len(files) == 1
        diagnostic = json.loads(files[0].read_text(encoding='utf-8'))
        assert diagnostic['source_duration'] == 45 and diagnostic['audio_duration'] == 30
        assert diagnostic['quality']['coverage_status'] == 'incomplete'
        attempt = diagnostic['attempts'][0]
        assert 'native decoder failed' in attempt['warning']
        assert attempt['failure']['worker']['returncode'] == 42
        assert attempt['failure']['worker']['stderr'] == 'specific native failure'
        assert 'text' not in attempt and 'segments' not in attempt
    else:
        assert files == []


@pytest.mark.parametrize("with_coverage", [False, True])
def test_worker_failure_diagnostics_survive_ipc_cleanup(tmp_path, monkeypatch, with_coverage):
    from types import SimpleNamespace
    from pathlib import Path

    monkeypatch.setenv("CUTROOM_DATA_DIR", str(tmp_path / "data"))
    settings = load_settings()
    paths = []

    def failed_worker(command, **kwargs):
        result_path, progress_path = Path(command[-2]), Path(command[-1])
        paths.append(result_path.parent)
        envelope = {"ok": False, "error": "native decoder failed", "traceback": "worker traceback"}
        if with_coverage:
            envelope["coverage"] = {"complete": False, "source_duration": 30}
        result_path.write_text(json.dumps(envelope), encoding="utf-8")
        progress_path.write_text(json.dumps({"progress": 0.4, "message": "Decoding chunk 1"}), encoding="utf-8")
        kwargs["stderr"].write("specific native failure")
        return SimpleNamespace(returncode=42, poll=lambda: 42)

    monkeypatch.setattr(transcription.subprocess, "Popen", failed_worker)
    expected = transcription.TranscriptionIncomplete if with_coverage else RuntimeError
    with pytest.raises(expected) as failure:
        transcription._run_transcription_worker(Path("source.mp4"), settings, "en", None, "quality", 30, None)
    diagnostics = failure.value.diagnostics
    assert diagnostics["returncode"] == 42
    assert diagnostics["traceback"] == "worker traceback"
    assert diagnostics["stderr"] == "specific native failure"
    assert diagnostics["last_progress"]["progress"] == 0.4
    assert not paths[0].exists()
