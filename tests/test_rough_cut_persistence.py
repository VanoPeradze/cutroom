"""Saved editable rough-cut integration; synthetic source, no inference/media."""
import copy

import pytest

from cutroom import director, intelligence as story
from cutroom.caption_items import effective_transcript
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.sequence import editor_sequence_snapshot
from cutroom.story_candidates import source_identity_rows
from server import _public_project
from test_director_rebuild_cache import semantic_project
from test_early_rough_cut_recovery import failure, request


@pytest.mark.parametrize('language', ['he', 'en'])
@pytest.mark.parametrize('existing_manual_timeline', [False, True])
def test_recovered_draft_reopens_editable_without_losing_manual_work(
    semantic_project, monkeypatch, language, existing_manual_timeline,
):
    store, settings, pid, calls, context = semantic_project
    source_before = source_identity_rows(store.load(pid)['analysis']['transcript']['segments'])
    correction = 'User-reviewed caption.' if language == 'en' else 'כתובית שנערכה בבדיקה.'
    store.update(pid, lambda p: apply_manual_edit(p, {
        'action': 'transcript_text', 'segment_id': 's3', 'text': correction,
    }))
    if existing_manual_timeline:
        store.update(pid, lambda p: apply_manual_edit(p, {'action': 'sequence_split', 'slot': 'A', 'time': 5.}))
    before = store.load(pid)
    manual_before = copy.deepcopy(before['manual'])
    editor_before = editor_sequence_snapshot(before)

    def stopped(_beats, current, *_args, **_kwargs):
        raise failure(current)
    monkeypatch.setattr(story, 'hierarchical_story_edit', stopped)
    monkeypatch.setattr(director, '_plan_edit_with_cancel', lambda c, s, settings, b, **k:
        story.plan_edit(s, settings, b, cancel_check=c.checkpoint))
    result = director.analyze_project(context(), pid, store, settings, request(language))
    # A fresh store exercises the actual serialized project, not the in-memory
    # return value. No actual browser, decoded media or export is implied.
    reopened_store = ProjectStore(settings)
    reopened = reopened_store.load(pid)
    assert calls['transcribe'] == 1
    assert source_identity_rows(reopened['analysis']['transcript']['segments']) == source_before
    assert reopened['draft']['editorial_authority'] == story.EXTRACTIVE_ROUGH_CUT_AUTHORITY
    assert reopened['draft']['review_required'] is True
    assert reopened['draft']['generative_approved'] is False
    assert reopened['draft']['keep_ranges'] == [{'start': 0., 'end': 58.}]
    assert reopened['manual']['caption_corrections'] == manual_before['caption_corrections']
    assert result['timeline_preserved'] is existing_manual_timeline
    assert result['applied_to_timeline'] is not existing_manual_timeline
    if existing_manual_timeline:
        assert reopened['manual'] == manual_before
        assert editor_sequence_snapshot(reopened) == editor_before
    public = _public_project(reopened)
    assert 'error' not in public['editor_sequence']
    assert public['editor_sequence']['duration'] == (60. if existing_manual_timeline else 58.)
    assert '_history' not in public['manual']

    # Subsequent manual correction, saved Undo and saved Redo must work on the
    # generated edit without rewriting canonical ASR or disturbing its geometry.
    changed = correction + ' 2'
    stable_editor = editor_sequence_snapshot(reopened)
    for action, expected in [
        ({'action': 'transcript_text', 'segment_id': 's3', 'text': changed}, changed),
        ({'action': 'undo'}, correction),
        ({'action': 'redo'}, changed),
    ]:
        reopened_store.update(pid, lambda p: apply_manual_edit(p, action))
        current = ProjectStore(settings).load(pid)
        assert current['manual']['caption_corrections']['s3']['text'] == expected
        assert expected in effective_transcript(current)[0]['text']
        assert source_identity_rows(current['analysis']['transcript']['segments']) == source_before
        assert editor_sequence_snapshot(current) == stable_editor
