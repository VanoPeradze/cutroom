import json
import time

import pytest

from cutroom.jobs import Job, JobManager
from cutroom.story_budget import StoryBudgetError


@pytest.mark.parametrize('outcome', [
    'technical_error', 'invalid_model_output', 'constraint_conflict', 'editorial_no_fit',
])
def test_story_failure_keeps_progress_edit_authority_and_private_diagnostics(outcome):
    manager = JobManager(workers=1)
    diagnostic = {'outcome': outcome, 'reason': 'semantic_no_fit',
                  'private_context': 'private-user-source', 'traceback': 'secret/path',
                  'instruction_contract': {'instruction': 'private instruction'}}

    def reject(context):
        context.update(.73, 'Reviewing story meaning')
        raise StoryBudgetError('The existing edit was kept.', diagnostic)

    try:
        job = manager.submit('director', 'project_outcome', reject)
        deadline = time.monotonic() + 3
        while job.status not in {'failed', 'completed'} and time.monotonic() < deadline:
            time.sleep(.01)
        public = job.public()
        assert public['status'] == 'failed' and public['progress'] == .73
        assert public['failure'] == {'outcome': outcome, 'reason': 'semantic_no_fit', 'applied_to_timeline': False}
        assert public['result'] is None
        assert job.result['diagnostic']['private_context'] == 'private-user-source'
        encoded = json.dumps(public)
        assert 'private-user-source' not in encoded and 'private instruction' not in encoded and 'secret/path' not in encoded
        restored = Job.from_persistence_record(job.persistence_record())
        assert restored.public()['failure'] == public['failure']
        assert restored.progress == .73
        assert 'private-user-source' not in json.dumps(job.persistence_record())
    finally:
        manager.shutdown()


def test_untrusted_failure_fields_and_reason_are_not_published_or_persisted():
    job = Job('job_private', 'director', 'project_test', status='failed',
              failure={'outcome': 'editorial_no_fit', 'reason': 'C:/private-user/model.json',
                       'traceback': 'private traceback', 'applied_to_timeline': False})
    assert job.public()['failure'] == {'outcome': 'editorial_no_fit', 'applied_to_timeline': False}
    assert 'C:/private-user' not in json.dumps(job.persistence_record())
    assert 'private traceback' not in json.dumps(job.persistence_record())
    job.failure = {'outcome': 'unknown', 'traceback': 'private'}
    assert 'failure' not in job.public()
    job.failure = {'outcome': []}
    assert 'failure' not in job.public()
    job.failure = {'outcome': 'technical_error', 'applied_to_timeline': True}
    assert 'failure' not in job.public()


def test_completed_job_does_not_republish_a_stale_failure():
    job = Job('job_recovered', 'director', 'project_test', status='completed',
              result={'draft_id': 'draft_current'}, failure={'outcome': 'technical_error'})
    assert 'failure' not in job.public() and 'failure' not in job.persistence_record()
    assert job.public()['result'] == {'draft_id': 'draft_current'}


def test_actual_unavailable_story_runtime_is_a_technical_failure():
    from cutroom.intelligence import StoryAIUnavailableError
    manager = JobManager(workers=1)
    try:
        def unavailable(context):
            context.update(.6, 'Connecting to Story AI')
            raise StoryAIUnavailableError('Story AI is not running.')
        job = manager.submit('director', 'project_runtime', unavailable)
        deadline = time.monotonic() + 3
        while job.status not in {'failed', 'completed'} and time.monotonic() < deadline:
            time.sleep(.01)
        assert job.public()['failure'] == {'outcome': 'technical_error', 'reason': 'story_ai_unavailable', 'applied_to_timeline': False}
        assert job.progress == .6
    finally:
        manager.shutdown()
