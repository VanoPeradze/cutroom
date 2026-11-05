"""Continuous source playback across ASR gaps; synthetic, not editorial QA."""
import copy

import pytest

from cutroom import director, intelligence
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.source_continuity import continuous_source_playback
from cutroom.story_budget import StoryBudgetError
from test_director_rebuild_cache import (
    _required_story_editorial, _install_story_editorial, semantic_project,
)
from test_story_passage_options import fixture


TEXT = {
    'en': 'Make one video without cuts. Aim for 45-60 seconds.',
    'he': 'צור סרטון אחד בלי חיתוכים. כוון ל45-60 שניות.',
}


def bound_editorial():
    # 40 seconds of source units, but 50 seconds of actual source playback.
    result = _required_story_editorial([('first', 30., 50.), ('last', 60., 80.)])
    result['decision']['story_requirements']['continuous_source_playback'] = continuous_source_playback(
        result['story_beats'], result['segments'], ['first', 'last'])
    return result


@pytest.mark.parametrize('language', ['he', 'en'])
def test_native_options_preserve_original_audio_between_complete_source_units(language):
    units, segments, chapters, plan, brief = fixture(seconds=16, gap=2, language=language,
        instruction=TEXT[language])
    before = copy.deepcopy((units, segments))
    options = intelligence._passage_options(units, segments, chapters, plan, brief)
    assert len(options['options']) == 1
    option = options['options'][0]
    assert option['playback_ranges'] == [{'start': 0, 'end': 52}]
    assert option['continuous_source_playback']['source'] == [
        {k:r[k] for k in ('id', 'start', 'end', 'text')} for r in segments]
    assert option['continuous_source_playback']['gap_audio'] == 'preserved_unverified'
    assert not option['continuous_source_playback']['semantic_verified']
    assert option['cost']['approved_seconds'] == 52
    assert option['cost']['minimum_safe_seconds'] == 52
    # Mechanical binding does not bypass nomination or final meaning checks.
    assert option['semantic_fit_verified'] is False
    assert (units, segments) == before


@pytest.mark.parametrize('change', ['omitted_speech', 'clipped_speech', 'repeated', 'reordered', 'changed_text'])
def test_continuous_binding_rejects_omitted_clipped_repeated_or_rewritten_speech(change):
    result = bound_editorial()
    units, segments = result['story_beats'], result['segments']
    ids = ['first', 'last']
    if change == 'omitted_speech':
        segments.insert(1, {'id':'negation', 'start':52., 'end':55., 'text':'That is NOT the claim.'})
    elif change == 'clipped_speech':
        segments[0]['start'] = 29.
    elif change == 'repeated':
        ids = ['first', 'first', 'last']
    elif change == 'reordered':
        ids = ['last', 'first']
    else:
        units[0]['text'] = 'Different invented words.'
    with pytest.raises(ValueError):
        continuous_source_playback(units, segments, ids)


@pytest.mark.parametrize('language', ['he', 'en'])
def test_director_uses_envelope_for_duration_and_keeps_attribution_units(language):
    result = bound_editorial()
    before = copy.deepcopy(result)
    policy = enrich_brief_with_style({'goal':'short', 'target_duration':60., 'duration_mode':'target',
                                     'instruction':TEXT[language]})['style_profile']['selection_policy']
    policy['duration_bounds'] = intelligence.effective_duration_bounds({'instruction':TEXT[language],
        'target_duration':60., 'duration_mode':'target'}, 300.)
    ranges = director._select_short_story_ranges(result['segments'], result['decision'], 300., 60.,
                                                selection_policy=policy, fps=30)
    assert ranges == [{'start':30., 'end':80.}]
    proof = director._validate_required_story_selection(result['decision'], result['segments'], 300., 60.,
        selection_policy=policy, keep_ranges=ranges, hierarchy=result['story_hierarchy'], fps=30)
    assert proof['cost']['approved_seconds'] == proof['cost']['minimum_safe_seconds'] == 50.
    assert len(result['decision']['story_ranges']) == 2
    assert result == before
    with pytest.raises(StoryBudgetError) as caught:
        director._validate_required_story_selection(result['decision'], result['segments'], 300., 60.,
            selection_policy=policy, keep_ranges=[{'start':30.,'end':50.},{'start':60.,'end':80.}],
            hierarchy=result['story_hierarchy'], fps=30)
    assert 'continuous_source_playback_changed' in caught.value.diagnostic['reasons']


@pytest.mark.parametrize('change', ['text', 'time', 'binding', 'instruction'])
def test_stale_or_unauthorized_binding_cannot_reach_playback(change):
    result = bound_editorial()
    policy = {'preserve_source_continuity':True}
    if change == 'text':
        result['segments'][0]['text'] = 'A changed source assertion.'
    elif change == 'time':
        result['segments'][0]['end'] = 49.
    elif change == 'binding':
        result['decision']['story_requirements']['continuous_source_playback']['playback_ranges'][0]['end'] = 79.
    else:
        policy['preserve_source_continuity'] = False
    with pytest.raises(ValueError):
        director._select_short_story_ranges(result['segments'], result['decision'],300.,60.,selection_policy=policy)


@pytest.mark.parametrize('language', ['he', 'en'])
def test_full_director_retains_pause_and_caption_source_time(semantic_project, monkeypatch, language):
    store, settings, project_id, _calls, context = semantic_project
    result = bound_editorial()
    _install_story_editorial(monkeypatch, store, project_id, result)
    # Rebind after the fixture's canonical normalization, never alter real ASR.
    result['decision']['story_requirements']['continuous_source_playback'] = continuous_source_playback(
        result['story_beats'], result['segments'], ['first','last'])
    monkeypatch.setattr(director, '_build_reel_candidates', lambda *_a, **_k: [])
    source = store.project_dir(project_id)/'media/source-A.mp4'
    original = source.read_bytes()
    response = director.analyze_project(context(), project_id, store, settings, {
        'instruction':TEXT[language], 'target_duration':60., 'duration_mode':'target',
        'source_continuity':'required', 'output_count':1, 'captions':True, 'fps':30})
    draft = store.load(project_id)['draft']
    assert draft['keep_ranges'] == [{'start':30., 'end':80.}]
    assert draft['output_duration'] == 50.
    assert draft['instruction_contract']['source_continuity_proof']['source_continuity_verified'] is True
    # Same continuous mapping used by caption/export code: the second source
    # utterance begins at30 seconds of output, not20 after a deleted pause.
    from cutroom.captions import build_srt
    caption_path = store.project_dir(project_id)/'continuity-fixture.srt'
    build_srt({'segments':result['segments']}, draft['keep_ranges'], caption_path)
    text = caption_path.read_text(encoding='utf-8-sig')
    assert '00:00:30,' in text
    assert '00:00:20,000 -->' not in text
    assert source.read_bytes() == original


def test_one_output_alone_retains_existing_montage_policy():
    units, segments, chapters, plan, brief = fixture(seconds=16, gap=2,
        instruction='Make one video. Aim for 45-60 seconds.')
    option = intelligence._passage_options(units, segments, chapters, plan, brief)['options'][0]
    assert len(option['playback_ranges']) == 3
    assert 'continuous_source_playback' not in option
    assert option['raw_playable_seconds'] == 48
