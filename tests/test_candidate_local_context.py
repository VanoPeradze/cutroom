"""Local context obligations are source-specific, not a universal story arc."""
import copy

import pytest

from cutroom import intelligence as story
from cutroom.edit_styles import enrich_brief_with_style
from test_story_passage_options import fixture
from test_single_passage_story_plan import responder, proposal, Settings


TEXT = {'en':'Make one video without cuts. Aim for45-60seconds.',
        'he':'צור סרטון אחד בלי חיתוכים. כוון ל45-60 שניות.'}


def local_fixture(language):
    units, segments, _chapters, plan, brief = fixture(count=6,seconds=16,gap=2,
        instruction=TEXT[language],language=language)
    chapters=[{'id':'c1','beats':units[:2]},{'id':'c2','beats':units[2:]}]
    plan['slots'][0].update(chapter_ids=['c1','c2'],required_context_chapter_ids=['c1'])
    return units,segments,chapters,plan,enrich_brief_with_style(brief)


@pytest.mark.parametrize('language',['he','en'])
def test_local_plan_retains_reference_without_global_exclusion(language):
    units,segments,chapters,plan,brief=local_fixture(language)
    before=copy.deepcopy(plan)
    old=story._passage_options(units,segments,chapters,plan,brief)
    local=story._candidate_local_context_plan(plan,brief)
    new=story._passage_options(units,segments,chapters,local,brief)
    assert len(old['options'])==2 and len(new['options'])==4
    assert local['slots'][0]['required_context_chapter_ids']==[]
    assert local['slots'][0]['reference_context_chapter_ids']==['c1']
    assert local['context_policy']['semantic_verified'] is False
    assert all(45 <= r['raw_playable_seconds'] <= 60 and len(r['playback_ranges'])==1 for r in new['options'])
    assert all(r['semantic_fit_verified'] is False for r in new['options'])
    assert plan==before
    assert story._candidate_local_context_plan(local,brief)==local


@pytest.mark.parametrize('instruction',[
    'Make one video without cuts. Structure: context -> result.',
    'צור סרטון אחד בלי חיתוכים. מבנה: הקשר -> תוצאה.',
])
def test_explicit_user_roles_are_not_downgraded(instruction):
    _,_,_,plan,brief=local_fixture('en')
    brief=enrich_brief_with_style({**brief,'instruction':instruction})
    assert story._configured_story_roles(brief)
    assert story._candidate_local_context_plan(plan,brief)==plan


def test_one_output_without_explicit_continuity_preserves_existing_role_path():
    _,_,_,plan,brief=local_fixture('en')
    brief=enrich_brief_with_style({**brief,'instruction':'Make one video.','source_continuity':'unspecified'})
    assert story._candidate_local_context_plan(plan,brief)==plan


@pytest.mark.parametrize('language',['he','en'])
def test_actual_plan_builder_applies_local_context_scope(monkeypatch,language):
    raw=proposal();raw['slots'][0]['chapter_ids']=['c1','c2'];raw['slots'][0]['required_context_chapter_ids']=['c1']
    responder(monkeypatch,[raw])
    result=story._build_story_plan(Settings(),[{'id':'c1'},{'id':'c2'}],{},
        enrich_brief_with_style({'goal':'short','target_duration':60.,'duration_mode':'target',
                                'instruction':TEXT[language],'output_count':1}),'fixture')
    assert result['slots'][0]['required_context_chapter_ids']==[]
    assert result['slots'][0]['reference_context_chapter_ids']==['c1']


@pytest.mark.parametrize('language',['he','en'])
@pytest.mark.parametrize('case',['real_missing_referent','foreign_reference','missing_evidence','uncertain'])
def test_continuous_final_review_requires_exact_candidate_context_evidence(language,case):
    units,segments,chapters,plan,brief=fixture(count=4,seconds=16,gap=2,
        instruction=TEXT[language],language=language)
    texts=(['Mara is the named editor.','She chose to review the report.','The review found a false claim.','That is why review matters.']
           if language=='en' else ['שם העורכת הוא מיכל.','היא בחרה לבדוק את הדוח.','הבדיקה מצאה טענה שגויה.','לכן הבדיקה חשובה.'])
    for unit,segment,text in zip(units,segments,texts):
        unit['text']=segment['text']=text;segment['words'][0]['word']=text
    option=story._passage_options(units,segments,chapters,plan,brief)['options'][-1]
    assert segments[0]['id'] not in option['segment_ids']
    catalog=story.build_story_evidence_catalog(units,segments)
    proposal_value=story._passage_option_proposal(option,catalog,chapters,plan)
    evidence={'kind':'missing_context','source_segment_ids':[option['segment_ids'][0]],
              'missing_context_segment_ids':[segments[0]['id']],'join_id':None,'instruction_quote':''}
    reply={'verdict':'no_fit','candidate_id':option['id'],'semantic_reason':'The pronoun needs its named referent.',
           'refusal_category':'semantic_rejection','cited_segment_ids':[option['segment_ids'][0]],
           'critic_action_decisions':[],'rejection_evidence':[evidence]}
    if case=='foreign_reference':evidence['missing_context_segment_ids']=['foreign']
    if case=='missing_evidence':reply['rejection_evidence']=[]
    if case=='uncertain':reply.update(refusal_category='uncertain',rejection_evidence=[])
    with pytest.raises(story.StoryPlanningError) as caught:
        story._decode_fixed_passage_final(reply,option,proposal_value,[],segments)
    expected={'real_missing_referent':'fixed_candidate_semantic_rejection',
              'foreign_reference':'final_review_evidence_invalid',
              'missing_evidence':'final_review_evidence_invalid','uncertain':'fixed_candidate_verification_unfinished'}[case]
    assert caught.value.diagnostic['reason']==expected
    assert caught.value.diagnostic['source_wide_no_fit_proven'] is False
    assert caught.value.diagnostic['applied_to_timeline'] is False
