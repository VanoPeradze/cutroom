"""A continuous output uses local planning without inventing semantic count."""
import pytest
from cutroom import intelligence
from cutroom.edit_styles import enrich_brief_with_style
from test_single_passage_story_plan import responder, proposal, Settings

@pytest.mark.parametrize('text',['Make one video without cuts.','צור סרטון אחד בלי חיתוכים.'])
def test_continuity_control_enters_existing_local_plan_without_inventing_roles(monkeypatch,text):
    calls=responder(monkeypatch,[proposal()])
    brief=enrich_brief_with_style({'goal':'short','target_duration':60.,'duration_mode':'target','instruction':text,'output_count':1,'source_continuity':'required'})
    result=intelligence._build_story_plan(Settings(),[{'id':'c1'},{'id':'c2'}],{},brief,'fixture')
    assert len(result['slots'])==1
    assert calls[0]['format']['properties']['slots']['maxItems']==1
    assert result['passage_constraint']['source_range_count']==1
    assert result['passage_constraint']['semantic_unit_count'] is None

def test_one_output_without_continuity_does_not_acquire_local_passage_constraint():
    assert not intelligence._local_continuous_plan_requested({'goal':'short','instruction':'Make one video.','output_count':1,'source_continuity':'unspecified'})


def test_review_control_only_does_not_invent_semantic_count_and_reaches_precision(monkeypatch):
    brief=enrich_brief_with_style({'goal':'short','target_duration':60.,'duration_mode':'target','instruction':'Keep the original account.','output_count':1,'source_continuity':'required'})
    responder(monkeypatch,[proposal()])
    result=intelligence._build_story_plan(Settings(),[{'id':'c1'},{'id':'c2'}],{},brief,'fixture')
    assert result['passage_constraint']['semantic_unit_count'] is None
    assert result['passage_constraint']['source_range_origin']=='explicit_review_control'
    assert intelligence._neutral_precision_plan(result,brief)


def test_continuity_control_does_not_change_whole_recording_modes():
    for goal in ('youtube','podcast','clean'):
        assert not intelligence._local_continuous_plan_requested({'goal':goal,'output_count':1,'source_continuity':'required','instruction':'Keep the original account.'})


def test_explicit_narrative_roles_are_retained_under_continuity(monkeypatch):
    brief=enrich_brief_with_style({'goal':'short','target_duration':60.,'duration_mode':'target','instruction':'Structure: context -> result.','output_count':1,'source_continuity':'required'})
    responder(monkeypatch,[proposal(('context','result'))])
    result=intelligence._build_story_plan(Settings(),[{'id':'c1'},{'id':'c2'}],{},brief,'fixture')
    assert [r['purpose'] for r in result['slots']]==['context','result']
    assert all(r['origin']=='user' for r in result['role_requirements'])


def test_insufficient_source_cannot_shrink_explicit_duration_bounds(monkeypatch):
    from cutroom.story_budget import StoryPlanningError
    brief=enrich_brief_with_style({'goal':'short','target_duration':60.,'duration_mode':'target','instruction':'Aim for 45-60 seconds.','output_count':1,'source_continuity':'required'})
    short=proposal();short['slots'][0]['chapter_ids']=['c1']
    responder(monkeypatch,[short])
    source=[{'id':'b1','start':0.,'end':10.,'text':'A short source only.'}]
    chapters=[{'id':'c1','beats':source}]
    with pytest.raises(StoryPlanningError):
        intelligence._build_story_plan(Settings(),[{'id':'c1'}],{},brief,'fixture',segments=source,chapters=chapters)
