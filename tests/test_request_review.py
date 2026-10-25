"""Request review is deterministic bookkeeping, never semantic/video QA."""
import copy
from types import SimpleNamespace
import pytest

import server
from cutroom import instruction_contract as contracts, intelligence, cache_keys, director
from cutroom.edit_styles import enrich_brief_with_style
from cutroom.story_budget import StoryBudgetError
from test_media_library import api
from test_director_rebuild_cache import semantic_project
from test_director_source_continuity import selected_span, SPAN


def brief(text='', **kw):
    return dict(goal='short', target_duration=60., duration_mode='target',
                instruction=text, aspect='9:16', edit_style='smart', output_count=1,
                source_continuity='unspecified', **kw)


@pytest.mark.parametrize('text',['Make one video.','צור סרטון אחד.'])
def test_explicit_review_continuity_uses_existing_style_and_default_plan_contract(text,monkeypatch):
    b=brief(text);before=copy.deepcopy(b)
    assert not enrich_brief_with_style(b)['style_profile']['selection_policy']['preserve_source_continuity']
    b['source_continuity']='required'
    c=contracts.assert_instruction_contract(b)
    assert c['selection_controls']['source_continuity']=='required'
    assert c['selection_controls']['source_continuity_origin']=='explicit_review_control'
    assert c['verification_status']=='unverified' and c['instruction']==text
    seen=[]
    def planner(beats,segments,settings,enriched,*a,**kw):
        seen.append(enriched)
        return {'keep_ids':['s'],'remove_ids':[],'highlight_ids':[]},{}
    monkeypatch.setattr(intelligence,'hierarchical_story_edit',planner)
    intelligence.plan_edit([{'id':'s','start':0.,'end':60.,'text':'Unchanged source.'}],SimpleNamespace(ai={}),b)
    assert seen[0]['style_profile']['selection_policy']['preserve_source_continuity'] is True
    assert b=={**before,'source_continuity':'required'}


@pytest.mark.parametrize('text,choice',[
    ('Make one video without cuts.','cuts_allowed'),('צור סרטון אחד בלי חיתוכים.','cuts_allowed'),
    ('Allow internal cuts.','required'),('מותר לבצע חיתוכים פנימיים.','required'),
])
def test_opposed_review_and_verbatim_controls_block_before_actual_planner(text,choice,monkeypatch):
    b=brief(text);b['source_continuity']=choice;before=copy.deepcopy(b)
    monkeypatch.setattr(intelligence,'hierarchical_story_edit',lambda *a,**kw:pytest.fail('Conflict reached planner'))
    with pytest.raises(StoryBudgetError) as caught:
        intelligence.plan_edit([{'id':'s','start':0.,'end':60.,'text':'Source.'}],SimpleNamespace(ai={}),b)
    assert caught.value.diagnostic['reason']=='instruction_source_continuity_conflict' and b==before


@pytest.mark.parametrize('text',['Make two videos.','צור שני סרטונים.','Create 3 clips.','תעשה לי שלושה קליפים.'])
def test_unsupported_multiple_outputs_are_visible(text):
    with pytest.raises(StoryBudgetError) as e:contracts.assert_instruction_contract(brief(text))
    assert e.value.diagnostic['reason']=='unsupported_output_count'


@pytest.mark.parametrize('text',['Do not make two videos.','אל תיצור שני סרטונים.','"Make two videos."','If possible, make two videos.'])
def test_quotes_negation_and_conditional_counts_are_not_promoted(text):
    assert not contracts.build_instruction_contract(brief(text))['issues']


@pytest.mark.parametrize('text',['Make one continuous clip.','צור קליפ אחד רציף.'])
def test_ambiguous_continuous_output_requires_a_visible_choice(text):
    with pytest.raises(StoryBudgetError) as e:contracts.assert_instruction_contract(brief(text))
    assert e.value.diagnostic['reason']=='ambiguous_source_continuity'
    b=brief(text);b['source_continuity']='required'
    assert contracts.assert_instruction_contract(b)['selection_controls']['source_continuity']=='required'


@pytest.mark.parametrize('text',['Aim for 45-60 seconds.','כוון ל45-60 שניות.'])
def test_review_retains_explicit_duration_range_over_style_defaults(text):
    b=brief(text);b.update(duration_mode='style',target_duration=30.)
    bounds=contracts.effective_duration_bounds(b)
    assert (bounds['minimum_seconds'],bounds['maximum_seconds'])==(45.,60.)
    assert bounds['origin']=='explicit_user_range'


@pytest.mark.parametrize('text',['Use 16:9.','יחס תמונה 16:9.'])
def test_explicit_aspect_conflict_is_not_silently_overridden(text):
    with pytest.raises(StoryBudgetError) as e:contracts.assert_instruction_contract(brief(text))
    assert e.value.diagnostic['reason']=='instruction_aspect_conflict'


def test_readonly_api_review_and_direct_job_preflight_do_not_start_ai_or_mutate(api,monkeypatch):
    _,client,store,pid=api;path=store.state_path(pid);before=path.read_bytes()
    monkeypatch.setattr(server,'story_ai_status',lambda *a,**kw:pytest.fail('Blocked request reached AI'))
    b=brief('צור סרטון אחד בלי חיתוכים.');b['source_continuity']='cuts_allowed'
    r=client.post(f'/api/projects/{pid}/director/request-review',json=b)
    assert r.status_code==200,r.get_json()
    data=r.get_json();assert not data['ready'] and data['revision']==store.load(pid)['revision']
    assert data['contract']['instruction']==b['instruction']
    blocked=client.post(f'/api/projects/{pid}/director',json=b)
    assert blocked.status_code==400,blocked.get_json()
    assert path.read_bytes()==before
    b=brief('Make one video.');b['source_continuity']='required'
    r=client.post(f'/api/projects/{pid}/director/request-review',json=b)
    assert r.get_json()['ready'] and path.read_bytes()==before


@pytest.mark.parametrize('text',['Make one video.','צור סרטון אחד.'])
def test_actual_director_review_control_preserves_pauses_and_persists(text,semantic_project,monkeypatch):
    store,settings,pid,calls,context=semantic_project;policies=selected_span(monkeypatch)
    b=brief(text);b.update(target_duration=30.,source_continuity='required')
    director.analyze_project(context(),pid,store,settings,b)
    saved=store.load(pid)
    assert saved['draft']['keep_ranges']==SPAN
    assert saved['settings']['instruction']==text and saved['settings']['source_continuity']=='required'
    assert policies and all(x['preserve_source_continuity'] for x in policies)
    proof=saved['draft']['instruction_contract']['source_continuity_proof']
    assert proof['source_continuity_verified'] and not proof['semantic_coherence_verified']


def test_control_cache_identity_changes_story_without_retranscription():
    settings=SimpleNamespace(ai={},raw={});b=brief();other={**b,'source_continuity':'required'}
    one=cache_keys.build_analysis_cache_fingerprints({},settings,b,{})
    two=cache_keys.build_analysis_cache_fingerprints({},settings,other,{})
    assert one['story']!=two['story']
    assert all(one[k]==two[k] for k in ('source','transcript','scenes','vision'))


def test_review_uses_same_available_source_duration_as_director(api):
    _,client,store,pid=api
    data=client.post(f'/api/projects/{pid}/director/request-review',json=brief()).get_json()
    duration=store.load(pid)['sources']['A']['duration']
    assert data['source_duration']==duration
    assert data['duration_bounds']==contracts.effective_duration_bounds(brief(),duration)


def test_nonshort_review_does_not_offer_disconnected_highlight_duration():
    b=brief('Make exactly 60 seconds.');b.update(goal='youtube',aspect='16:9')
    with pytest.raises(StoryBudgetError) as e:contracts.assert_instruction_contract(b)
    assert e.value.diagnostic['reason']=='unsupported_mode_duration'
