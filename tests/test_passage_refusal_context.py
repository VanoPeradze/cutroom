"""Refusal attribution is mechanical evidence, not semantic entailment."""
import copy
import json
from types import SimpleNamespace

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.passage_binding import PASSAGE_REASON_CONTRACT
from test_story_passage_options import fixture


def source(language='en'):
    units, segments, chapters, plan, brief = fixture(seconds=16, gap=2, language=language,
        instruction=('Make one video without cuts. Aim for45-60seconds.' if language=='en' else
                     'צור סרטון אחד בלי חיתוכים. כוון ל45-60 שניות.'))
    brief = enrich_brief_with_style(brief)
    options = story._passage_options(units,segments,chapters,plan,brief)
    options['receipt']['rationale_contract'] = PASSAGE_REASON_CONTRACT
    return units,segments,chapters,plan,brief,options


@pytest.mark.parametrize('language',['he','en'])
def test_nomination_separates_style_and_renderer_defaults_from_verbatim_request(language):
    units,segments,chapters,plan,brief,options = source(language)
    before = copy.deepcopy(brief)
    payload = story._passage_option_request(SimpleNamespace(ai={}),options,units,segments,brief,'fixture')
    data = json.loads(payload['messages'][1]['content'])
    assert data['brief']['instruction'] == brief['instruction']
    assert data['duration_bounds']['minimum_seconds'] == 45.
    assert data['duration_bounds']['maximum_seconds'] == 60.
    assert 'style_profile' not in data['brief'] and 'story_contract' not in data['brief']
    assert data['style_preferences']['authority'] == 'advisory_not_rejection_requirements'
    assert data['passage_candidates'][0]['playback_ranges'] == [{'start':0,'end':52}]
    assert data['source_utterances'] and brief == before


@pytest.mark.parametrize('citations',[[],['foreign'],['s999']])
def test_uncited_or_foreign_refusal_is_invalid_model_output(citations):
    units,segments,chapters,plan,brief,options = source()
    reply = dict(verdict='no_fit',candidate_id=None,semantic_reason='An unsupported source interpretation.',
                 refusal_category='semantic_rejection',cited_segment_ids=citations,reason_evidence=[])
    with pytest.raises(story.StoryPlanningError) as caught:
        story._decode_passage_option_choice(reply,options,units,segments,chapters,plan,brief)
    assert caught.value.diagnostic['outcome'] == 'invalid_model_output'
    assert caught.value.diagnostic['source_wide_no_fit_proven'] is False


@pytest.mark.parametrize('language',['he','en'])
def test_cited_refusal_preserves_exact_words_without_proving_interpretation(language):
    units,segments,chapters,plan,brief,options = source(language)
    reply = dict(verdict='no_fit',candidate_id=None,semantic_reason='Fixture claim needing independent review.',
                 refusal_category='semantic_rejection',cited_segment_ids=[segments[1]['id']],reason_evidence=[])
    with pytest.raises(story.StoryBudgetError) as caught:
        story._decode_passage_option_choice(reply,options,units,segments,chapters,plan,brief)
    d = caught.value.diagnostic
    assert d['refusal_source_quotes'] == [{k:segments[1][k] for k in ('id','start','end','text')}]
    assert d['refusal_interpretation_verified'] is False and d['semantic_result_verified'] is False


def test_partial_coverage_is_explicit_incomplete_search(monkeypatch):
    units,segments,chapters,plan,brief = fixture(count=5,seconds=16,gap=2,
        instruction='Make one video without cuts. Aim for45-60seconds.')
    def reject(_settings,payload,*_args):
        data=json.loads(payload['messages'][1]['content'])
        return dict(verdict='no_fit',candidate_id=None,semantic_reason='Fixture rejection; not audio truth.',
            refusal_category='semantic_rejection',cited_segment_ids=[data['source_utterances'][0]['id']],reason_evidence=[])
    monkeypatch.setattr(story,'_call_ollama_story_pass',reject)
    import cutroom.passage_binding as binding
    monkeypatch.setattr(binding,'MAX_PASSAGE_ASSESSMENTS',1)
    monkeypatch.setattr(binding,'assessment_options',lambda rows,_ids:rows[:1])
    with pytest.raises(story.StoryBudgetError) as caught:
        story._select_passage_option(SimpleNamespace(ai={}),units,segments,chapters,plan,brief,'fixture',None)
    d=caught.value.diagnostic
    assert d['search_status']=='incomplete'
    assert d['reviewed_candidate_count']==1 and d['unreviewed_candidate_count']>0
    assert d['source_wide_no_fit_proven'] is False and d['applied_to_timeline'] is False
    assert 'incomplete search' in str(caught.value)
