"""A temporal-witness adapter cannot approve meaning, duration or explicit roles."""
import copy
import json

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style


def fixture(language='en', target=30):
    texts = (['I missed the bus because I left late.',
              'The next day I left earlier.', 'This time I arrived on time.'] if language == 'en' else
             ['פספסתי את האוטובוס כי יצאתי מאוחר.',
              'למחרת יצאתי מוקדם יותר.', 'הפעם הגעתי בזמן.'])
    instruction = ('Choose one coherent self-contained passage of about thirty seconds. Preserve meaning and complete sentences.'
                   if language == 'en' else
                   'בחר קטע אחד ברור ועצמאי באורך של כשלושים שניות. שמור על המשמעות ועל משפטים שלמים.')
    segments = story.enrich_segments([{'id':f's{i+1}', 'start':i*10., 'end':(i+1)*10., 'text':text}
                                     for i,text in enumerate(texts)], language)
    beats = [{'id':f'b{i+1}', 'start':r['start'], 'end':r['end'], 'duration':10.,
              'segment_ids':[r['id']], 'text':r['text']} for i,r in enumerate(segments)]
    chapters = [{'id':'c1', 'beats':beats, 'start':0., 'end':30.}]
    brief = enrich_brief_with_style({'goal':'short', 'instruction':instruction,
                                    'target_duration':target, 'duration_mode':'target'})
    plan = {'slots':[{'purpose':story.SINGLE_PASSAGE_PURPOSE, 'chapter_ids':['c1'],
                      'required_context_chapter_ids':[], 'desired_seconds':target}]}
    payload,catalog = story._precision_story_payload(beats, segments, chapters, [], {}, plan, brief,
                                                    'fixture', 'balanced', target)
    choices = list(story._story_evidence_choice_catalog(catalog))
    proposal = {'verdict':'fit', 'role_selections':{story.SINGLE_PASSAGE_PURPOSE:{
        'primary_anchor_choice':choices[0], 'additional_primary_evidence_choices':choices[1:],
        'context_evidence_choices_by_chapter':{}}}, 'highlight_beat_ids':[],
        'title':'Diagnostic', 'summary':'Unverified model interpretation'}
    return payload,catalog,proposal,beats,segments,chapters,plan,brief


@pytest.mark.parametrize('language', ['he', 'en'])
def test_neutral_witness_is_only_mechanical_source_attribution(language):
    payload,catalog,proposal,beats,segments,chapters,plan,brief = fixture(language)
    saved = copy.deepcopy(proposal)
    assert story._neutral_precision_plan(plan, brief)
    # Existing decoder still rejects an early witness; adaptation is explicit.
    with pytest.raises(story.StoryPlanningError):
        story._decode_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)
    clean = story._decode_proposed_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)
    assert proposal == saved
    assert clean['keep_beat_ids'] == ['b1','b2','b3']
    assert clean['semantic_mapping_verified'] is False
    assert clean['precision_representation_adapter']['interpretation_verified'] is False
    assert clean['evidence_proof']
    user = json.loads(payload['messages'][1]['content'])
    assert user['brief']['instruction'] == brief['instruction']
    assert user['whole_candidate_selection_cost']['beat_ids'] == ['b1','b2','b3']
    assert user['whole_candidate_selection_cost']['duration_cost'] == story._story_selection_cost(
        ['b1','b2','b3'],beats,segments,brief)


@pytest.mark.parametrize('language', ['he','en'])
def test_adapter_does_not_make_an_impossible_duration_feasible(language):
    _,catalog,proposal,beats,segments,chapters,plan,brief = fixture(language, target=8)
    clean = story._decode_proposed_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)
    assert not story._single_passage_proposal_budget(clean,beats,segments,brief)['feasible']
    assert clean['semantic_mapping_verified'] is False


def test_unknown_source_choice_is_not_repaired():
    _,catalog,proposal,beats,segments,chapters,plan,brief = fixture()
    proposal['role_selections'][story.SINGLE_PASSAGE_PURPOSE]['primary_anchor_choice'] = 'invented [b1:s1:f1]'
    with pytest.raises(story.StoryPlanningError):
        story._decode_proposed_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)


def test_explicit_roles_keep_original_decoder_obligations():
    _,catalog,proposal,beats,segments,chapters,plan,brief = fixture()
    brief = enrich_brief_with_style({**brief, 'instruction':'Start with the result, then show the context.'})
    assert not story._neutral_precision_plan(plan,brief)
    with pytest.raises(story.StoryPlanningError):
        story._decode_proposed_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)


def test_no_fit_is_never_converted_to_a_proposal():
    _,catalog,_,beats,segments,chapters,plan,brief = fixture()
    refusal = {'verdict':'no_fit','reason':'insufficient_context','missing_purposes':[story.SINGLE_PASSAGE_PURPOSE]}
    with pytest.raises(story.StoryBudgetError) as error:
        story._decode_proposed_precision_story_selection(refusal,catalog,beats,segments,chapters,plan,brief)
    assert error.value.diagnostic['precision']['reason'] == 'insufficient_context'


def test_downstream_semantic_refusal_still_blocks_the_proposal(monkeypatch):
    _,catalog,proposal,beats,segments,chapters,plan,brief = fixture()
    clean = story._decode_proposed_precision_story_selection(proposal,catalog,beats,segments,chapters,plan,brief)
    from cutroom.config import DEFAULTS, Settings
    from pathlib import Path
    settings = Settings(copy.deepcopy(DEFAULTS),*[Path('.')]*5,'ffmpeg','ffprobe')
    def refusal(*args,**kwargs):
        raise story.StoryBudgetError('Semantic account is not established', {'reason':'planner_no_fit','applied_to_timeline':False})
    monkeypatch.setattr(story,'_call_ollama_story_pass',refusal)
    with pytest.raises(story.StoryBudgetError):
        story._review_story_target_budget(settings,clean,beats,segments,chapters,{},plan,brief,'fixture')
    assert clean['semantic_mapping_verified'] is False
