"""Grounded critic actions preserve instructions, optional style and final review."""
import copy
import json
from pathlib import Path

import pytest

from cutroom import intelligence as story
from cutroom.config import DEFAULTS, Settings
from cutroom.edit_styles import enrich_brief_with_style


def fixture(language):
    texts = (['I missed the bus because I left late.', 'The next day I left ten minutes earlier.',
              'This time I arrived on time.'] if language == 'en' else
             ['פספסתי את האוטובוס כי יצאתי מאוחר.', 'למחרת יצאתי עשר דקות מוקדם יותר.',
              'הפעם הגעתי בזמן.'])
    instruction = ('Choose one coherent self-contained passage. Do not require a dramatic hook.' if language == 'en' else
                   'בחר קטע אחד ברור ועצמאי. אל תדרוש פתיחה דרמטית.')
    brief = enrich_brief_with_style({'goal':'short', 'target_duration':30, 'duration_mode':'target', 'instruction':instruction})
    segments = story.enrich_segments([{'id':f's{i+1}', 'start':i*10., 'end':(i+1)*10., 'text':text}
                                     for i,text in enumerate(texts)],language)
    beats = [{'id':f'b{i+1}', 'start':r['start'], 'end':r['end'], 'duration':10., 'text':r['text'],
              'segment_ids':[r['id']]} for i,r in enumerate(segments)]
    selection = {'keep_beat_ids':[b['id'] for b in beats], 'highlight_beat_ids':[],
                 'slot_map':[], 'semantic_mapping_verified':False}
    settings = Settings(copy.deepcopy(DEFAULTS),*[Path('.')]*5,'ffmpeg','ffprobe')
    return settings,selection,beats,segments,brief


def response(**patch):
    return {'verdict':'pass', 'add_beat_ids':[], 'remove_beat_ids':[], 'issues':[],
            'summary':'Review interpretation', 'style_notes':[], 'action_evidence':[], **patch}


@pytest.mark.parametrize('language',['he','en'])
def test_advisory_style_does_not_become_a_hard_obligation(language,monkeypatch):
    settings,selection,beats,segments,brief = fixture(language)
    calls=[]
    def call(_settings,payload,*_):
        calls.append(payload)
        return response(style_notes=['A stronger opening could be an optional improvement.'])
    monkeypatch.setattr(story,'_call_ollama_story_pass',call)
    reviewed=story._critic_story_selection(settings,selection,beats,{}, {},brief,'fixture',segments=segments)
    assert reviewed['keep_beat_ids']==selection['keep_beat_ids']
    assert reviewed['critic']['verdict']=='pass'
    assert reviewed['critic']['style_notes']
    assert reviewed['semantic_mapping_verified'] is False
    user=json.loads(calls[0]['messages'][1]['content'])
    assert 'style_profile' not in user['brief'] and 'edit_style' not in user['brief']
    assert user['brief']['instruction']==brief['instruction']
    assert user['style_preferences']['authority']=='advisory_only'
    assert user['style_preferences']['profile']==brief['style_profile']
    assert user['explicit_story_obligations']['roles']==[]
    assert user['source_utterances']==[{**{k:r[k] for k in ['id','start','end','text']},
                                      'selected_in_proposal':True} for r in segments]
    assert user['source_evidence']==story.build_story_evidence_catalog(beats,segments)


@pytest.mark.parametrize('language',['he','en'])
def test_style_only_or_unattributed_removal_remains_an_unverified_proposal(language,monkeypatch):
    settings,selection,beats,segments,brief=fixture(language)
    row={'action':'remove','beat_id':'b1','defect_kind':'explicit_instruction',
         'source_evidence_ids':[story.build_story_evidence_catalog(beats,segments)[0]['id']],
         'instruction_quote':'clear_promise','explanation':'The style demands a stronger hook.'}
    monkeypatch.setattr(story,'_call_ollama_story_pass',lambda *_:response(
        verdict='revise',remove_beat_ids=['b1'],issues=['Hook preference'],action_evidence=[row]))
    saved=copy.deepcopy(selection)
    reviewed=story._critic_story_selection(settings,selection,beats,{}, {},brief,'fixture',segments=segments)
    assert reviewed['keep_beat_ids']==saved['keep_beat_ids']
    assert reviewed['critic']['action_authority']=='proposal'
    assert reviewed['critic']['action_attribution_verified'] is False
    assert reviewed['critic']['action_evidence_error']
    assert reviewed['semantic_mapping_verified'] is False
    assert selection==saved


@pytest.mark.parametrize('language',['he','en'])
def test_real_off_topic_evidence_is_attributed_but_not_certified_semantically(language,monkeypatch):
    settings,selection,beats,segments,brief=fixture(language)
    text='My unrelated cake recipe uses flour.' if language=='en' else 'במתכון העוגה הלא קשור שלי יש קמח.'
    beats[1]['text']=segments[1]['text']=text
    catalog=story.build_story_evidence_catalog(beats,segments)
    ids=[next(r['id'] for r in catalog if r['beat_id']==key) for key in ['b1','b2']]
    row={'action':'remove','beat_id':'b2','defect_kind':'off_topic','source_evidence_ids':ids,
         'instruction_quote':'','explanation':'The cake is unrelated to the bus account.'}
    monkeypatch.setattr(story,'_call_ollama_story_pass',lambda *_:response(
        verdict='revise',remove_beat_ids=['b2'],issues=['Unrelated source topic'],action_evidence=[row]))
    reviewed=story._critic_story_selection(settings,selection,beats,{}, {},brief,'fixture',segments=segments)
    assert reviewed['keep_beat_ids']==['b1','b2','b3']
    assert reviewed['critic']['proposed_beat_ids']==['b1','b3']
    assert reviewed['critic']['requested_removed']==['b2']
    proof=reviewed['critic']['grounded_actions'][0]
    assert proof['source_evidence_ids']==ids and proof['source_evidence']==[r for r in catalog if r['id'] in ids]
    assert proof['interpretation_verified'] is False
    assert reviewed['semantic_mapping_verified'] is False


@pytest.mark.parametrize('language',['he','en'])
def test_explicit_instruction_can_authorize_a_source_grounded_proposal(language,monkeypatch):
    settings,selection,beats,segments,brief=fixture(language)
    instruction='Remove the first passage.' if language=='en' else 'הסר את הקטע הראשון.'
    brief['instruction']=instruction
    row={'action':'remove','beat_id':'b1','defect_kind':'explicit_instruction',
         'source_evidence_ids':[story.build_story_evidence_catalog(beats,segments)[0]['id']],
         'instruction_quote':instruction,'explanation':'Propose following this explicit instruction; final review remains required.'}
    monkeypatch.setattr(story,'_call_ollama_story_pass',lambda *_:response(
        verdict='revise',remove_beat_ids=['b1'],issues=['Explicit removal request'],action_evidence=[row]))
    reviewed=story._critic_story_selection(settings,selection,beats,{}, {},brief,'fixture',segments=segments)
    assert reviewed['keep_beat_ids']==['b1','b2','b3']
    assert reviewed['critic']['proposed_beat_ids']==['b2','b3']
    proof=reviewed['critic']['grounded_actions'][0]
    assert proof['instruction_evidence']['quote']==instruction
    assert proof['interpretation_verified'] is False


def test_no_asr_does_not_authorize_unattributed_visual_deletions(monkeypatch):
    settings,selection,beats,_segments,brief=fixture('en')
    monkeypatch.setattr(story,'_call_ollama_story_pass',lambda *_:response(
        verdict='revise',remove_beat_ids=['b1'],issues=['Unverified visual claim']))
    reviewed=story._critic_story_selection(settings,selection,beats,{}, {},brief,'fixture')
    assert reviewed['keep_beat_ids']==selection['keep_beat_ids']
    assert reviewed['critic']['action_authority']=='proposal'
    assert reviewed['critic']['action_attribution_verified'] is False


@pytest.mark.parametrize('bad_response',[
    response(verdict='revise',remove_beat_ids=['unknown'],issues=['Unknown source action']),
    response(verdict='pass',remove_beat_ids=['b1']),
    {'remove_beat_ids':['b1']},
])
def test_ungrounded_deletion_cannot_enter_the_skipped_critic_fallback(monkeypatch,bad_response):
    settings,selection,beats,segments,brief=fixture('he')
    plan={'slots':[{'purpose':story.SINGLE_PASSAGE_PURPOSE,'chapter_ids':['c001'],
                    'required_context_chapter_ids':[],'desired_seconds':30}]}
    monkeypatch.setattr(story,'_ready_story_model_status',lambda *_:{'selected_model':'fixture'})
    monkeypatch.setattr(story,'_load_story_understanding',lambda *_:None)
    monkeypatch.setattr(story,'_save_story_understanding',lambda *_,**__:None)
    monkeypatch.setattr(story,'_summarize_story_chapters',lambda *_:[{'id':'c001'}])
    monkeypatch.setattr(story,'_build_global_outline',lambda *_:{})
    monkeypatch.setattr(story,'_build_story_plan',lambda *_:copy.deepcopy(plan))
    monkeypatch.setattr(story,'_select_story_beats',lambda *_,**__:(copy.deepcopy(selection),beats))
    monkeypatch.setattr(story,'_call_ollama_story_pass',lambda *_:copy.deepcopy(bad_response))
    def no_final_review(*_,**__):
        raise AssertionError('An unattributed action must not be converted to a skipped critic.')
    monkeypatch.setattr(story,'_review_story_target_budget',no_final_review)
    saved=copy.deepcopy(selection)
    with pytest.raises(story._InvalidStorySelectionError):
        story.hierarchical_story_edit(beats,segments,settings,brief)
    assert selection==saved
