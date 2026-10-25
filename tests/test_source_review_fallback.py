"""Synthetic source review through real preview/apply/history transactions."""
import copy

import pytest

from cutroom.review_candidates import build_review_shelf,media_identity,publish_failed_review
from cutroom.story_budget import StoryPlanningError
from cutroom.jobs import JobCancelled
from cutroom import director
from test_reel_proposals import api
from test_director_rebuild_cache import semantic_project


REQUEST={'instruction':'Make one video without cuts. Aim for45-60seconds.','goal':'short',
         'output_count':1,'source_continuity':'required','duration_mode':'target','target_duration':60.,'aspect':'9:16','fps':30}


@pytest.fixture
def shelf(api):
    app,client,store,pid,path=api
    def setup(p):
        p['sources']['A']['duration']=70.
        p['analysis']['transcript']={'language':'en','segments':[
            {'id':'before','start':0.,'end':10.,'text':'Earlier reference.'},
            {'id':'selected1','start':10.,'end':30.,'text':'First unverified source statement.'},
            {'id':'selected2','start':35.,'end':60.,'text':'Second unverified source statement.'},
            {'id':'after','start':60.,'end':70.,'text':'Later reference.'}]}
        p['draft']=None
    store.update(pid,setup)
    options={'review_candidates':[{'id':'native_candidate','playback_ranges':[{'start':10.,'end':60.}],
                                  'segment_ids':['selected1','selected2'],'false_model_claim':'invented accusation'}]}
    publish_failed_review(store,pid,REQUEST,options,'source-v1')
    return api,options


def preview(shelf):
    api,_=shelf;_,client,store,pid,_=api;p=store.load(pid);candidate=p['analysis']['review_candidates']['items'][0]
    return client.post(f'/api/projects/{pid}/reel-proposal',json={'candidate_id':candidate['id'],'expected_revision':p['revision']})


def apply(shelf,proposal,**extra):
    _,client,_,pid,_=shelf[0]
    return client.post(f'/api/projects/{pid}/manual/edit',json={'action':'apply_review_candidate',
        'candidate_id':proposal['candidate_id'],'proposal_id':proposal['proposal_id'],'expected_revision':proposal['revision'],**extra})


def test_unapproved_preview_leaves_project_bytes_and_source_unchanged(shelf):
    _,_,store,pid,source=shelf[0];path=store.state_path(pid);before=path.read_bytes();media=source.read_bytes()
    response=preview(shelf);assert response.status_code==200,response.get_json();p=response.get_json()['proposal']
    assert p['ranges']==[{'start':10.,'end':60.}] and p['output_duration']==50.
    assert p['kind']=='unverified_source_candidate' and p['semantic_approval'] is False
    assert 'invented accusation' not in str(p)
    assert path.read_bytes()==before and source.read_bytes()==media
    assert store.load(pid)['draft'] is None


def test_apply_undo_redo_restores_no_draft_and_preserves_manual_and_source(shelf):
    _,client,store,pid,source=shelf[0];before=store.load(pid);media=source.read_bytes()
    proposal=preview(shelf).get_json()['proposal'];response=apply(shelf,proposal)
    assert response.status_code==200,response.get_json()
    p=store.load(pid);assert p['draft']['keep_ranges']==proposal['ranges']
    assert p['draft']['generative_approved'] is False and p['draft']['status']=='requires_review'
    assert p['draft']['semantic_approval'] is False
    for key in ('cuts','keeps','camera_overrides','source_mixer'):assert p['manual'][key]==before['manual'][key]
    response=client.post(f'/api/projects/{pid}/manual/edit',json={'action':'undo','expected_revision':p['revision']})
    assert response.status_code==200,response.get_json();p=store.load(pid)
    assert p['draft'] is None and p['settings']==before['settings']
    response=client.post(f'/api/projects/{pid}/manual/edit',json={'action':'redo','expected_revision':p['revision']})
    assert response.status_code==200,response.get_json()
    assert store.load(pid)['draft']['keep_ranges']==proposal['ranges']
    assert source.read_bytes()==media


@pytest.mark.parametrize('change',['media','source','project','request','transcript'])
def test_stale_preview_cannot_overwrite_changed_state(shelf,change):
    _,_,store,pid,source=shelf[0];proposal=preview(shelf).get_json()['proposal']
    if change=='media':source.write_bytes(source.read_bytes()+b'changed')
    else:
        def edit(p):
            if change=='source':p['sources']['A']['generation']='new-source'
            if change=='project':p['manual']['cuts'].append({'start':1.,'end':2.})
            if change=='request':p['settings']['instruction']='A later explicit request.'
            if change=='transcript':p['analysis']['transcript']['segments'][1]['text']='Changed source.'
        store.update(pid,edit)
    before=store.state_path(pid).read_bytes();response=apply(shelf,proposal)
    assert response.status_code in (400,409),response.get_json()
    assert store.state_path(pid).read_bytes()==before


def test_repeated_apply_and_missing_review_token_are_rejected(shelf):
    _,client,store,pid,_=shelf[0];proposal=preview(shelf).get_json()['proposal']
    assert client.post(f'/api/projects/{pid}/manual/edit',json={'action':'apply_review_candidate','candidate_id':proposal['candidate_id'],'expected_revision':proposal['revision']}).status_code==400
    assert apply(shelf,proposal).status_code==200
    before=store.state_path(pid).read_bytes();assert apply(shelf,proposal).status_code==409
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize('bad',['duration','cut','missing_speech','repeat','multi_source'])
def test_invalid_candidate_never_enters_review_shelf(shelf,bad):
    api,options=shelf;_,_,store,pid,_=api;p=store.load(pid);options=copy.deepcopy(options)
    if bad=='duration':options['review_candidates'][0]['playback_ranges']=[{'start':0.,'end':10.}]
    if bad=='cut':options['review_candidates'][0]['playback_ranges']=[{'start':10.,'end':30.},{'start':35.,'end':60.}]
    if bad=='missing_speech':options['review_candidates'][0]['segment_ids']=['selected1']
    if bad=='repeat':options['review_candidates'][0]['segment_ids'].append('selected1')
    if bad=='multi_source':p['sources']['B']={'duration':70.}
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):build_review_shelf(p,REQUEST,options,{})
    assert p==before


def test_real_director_failure_publishes_only_unapplied_candidates(semantic_project,monkeypatch):
    store,settings,pid,_calls,context=semantic_project
    before=store.load(pid)
    def fail(*_a,**_k):
        raise StoryPlanningError('Unverified model assessment.',{'outcome':'technical_error','reason':'passage_verification_unfinished',
            'passage_options':{'review_candidates':[{'playback_ranges':[{'start':30.,'end':88.}],
                'segment_ids':[f's{i}' for i in range(3,9)]}]}})
    monkeypatch.setattr(director,'_plan_edit_with_cancel',fail)
    with pytest.raises(StoryPlanningError) as caught:director.analyze_project(context(),pid,store,settings,REQUEST)
    p=store.load(pid)
    assert caught.value.diagnostic.get('review_available') is True,caught.value.diagnostic
    assert p['analysis']['review_candidates']['status']=='needs_user_review'
    assert p['draft']==before['draft'] and p['manual']==before['manual']
    assert p['analysis']['review_candidates']['revision']==p['revision']
