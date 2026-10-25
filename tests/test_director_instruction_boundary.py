import copy
import threading

import pytest

from cutroom import director
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.story_budget import StoryBudgetError, StoryPlanningError


@pytest.mark.parametrize('instruction', [
    'Make it 30 seconds.',
    '\u05d0\u05e0\u05d9 \u05e8\u05d5\u05e6\u05d4 \u05e1\u05e8\u05d8\u05d5\u05df \u05d1\u05d0\u05d5\u05e8\u05da 30 \u05e9\u05e0\u05d9\u05d5\u05ea.',
])
def test_conflicting_duration_rejected_before_media_work_and_without_changing_saved_edit(tmp_path, monkeypatch, instruction):
    monkeypatch.setenv('CUTROOM_DATA_DIR', str(tmp_path / 'data'))
    settings = load_settings()
    store = ProjectStore(settings)
    project = store.create('Existing local edit')
    source = store.project_dir(project['id']) / 'media' / 'source-A.mp4'
    source.write_bytes(b'unchanged source; probing must not start')

    def attach(value):
        value['sources']['A'] = {'slot': 'A', 'relative_path': 'media/source-A.mp4',
                                 'duration': 120.0, 'has_audio': True, 'generation': 'original'}
        value['settings'].update(goal='short', target_duration=60, duration_mode='target')
        value['draft'] = {'keep_ranges': [{'start': 10, 'end': 40}], 'title': 'Keep this edit'}
        value['manual']['_history'] = {'undo': [{'action': 'fixture'}], 'redo': []}

    store.update(project['id'], attach)
    before = copy.deepcopy(store.load(project['id']))
    calls = []

    def forbidden(*args, **kwargs):
        calls.append(True)
        raise AssertionError('No media or model work should run for a known request conflict')

    monkeypatch.setattr(director, 'transcribe', forbidden)
    monkeypatch.setattr(director, 'analyze_audio', forbidden)
    context = JobContext(Job('job_request', 'director', project['id']), threading.Lock())
    with pytest.raises(StoryBudgetError) as raised:
        director.analyze_project(context, project['id'], store, settings, {'instruction': instruction})
    assert raised.value.diagnostic['outcome'] == 'constraint_conflict'
    assert raised.value.diagnostic['applied_to_timeline'] is False
    assert not calls
    assert store.load(project['id']) == before
    assert source.read_bytes() == b'unchanged source; probing must not start'


@pytest.mark.parametrize('reason', ['incomplete_transcription', 'uncovered_detected_speech'])
def test_transcript_coverage_failure_is_technical_not_an_editorial_rejection(reason):
    with pytest.raises(StoryPlanningError) as raised:
        director._assert_transcript_complete({'reasons': [reason]})
    assert raised.value.diagnostic == {'outcome': 'technical_error', 'reason': reason, 'applied_to_timeline': False}
