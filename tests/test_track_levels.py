import copy
import pytest
from test_media_append import api,library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers,VIDEO
from cutroom.layer_tracks import *
from cutroom.editing import apply_manual_edit,ManualEditError

@pytest.fixture
def p(unlocked):
    project=unlocked[2].load(unlocked[3]);mixed_layers(project)
    apply_manual_edit(project,{'action':'layer_tracks_enable'})
    return project

def track(p):return p['manual']['media_clips'][0]['track_id']
def edit(p,**kw):return apply_manual_edit(p,{'action':'layer_track_audio','track_id':track(p),**kw})
def act(p,action,**kw):return apply_manual_edit(p,{'action':action,**kw})

def test_first_edit_noop_history_and_exact_undo(p):
    before=copy.deepcopy(p);edit(p,gain_db=0);assert p==before
    edit(p,gain_db=-6.123456);assert p['manual']['layer_tracks']['version']==3
    assert p['manual']['layer_tracks']['protection_version']==1
    assert track_audio_settings(p,track(p))=={'gain_db':-6.123456,'muted':False}
    act(p,'undo');assert p['manual']['layer_tracks']==before['manual']['layer_tracks']
    act(p,'redo');assert track_audio_settings(p,track(p))['gain_db']==-6.123456

@pytest.mark.parametrize('origin',[1,2])
@pytest.mark.parametrize('later_lock',[False,True])
def test_history_current_lock_floor(p,origin,later_lock):
    identity=track(p)
    if origin==2:
        act(p,'layer_track_lock',track_id=identity,locked=True);act(p,'layer_track_lock',track_id=identity,locked=False)
    edit(p,gain_db=-6)
    if later_lock:
        act(p,'layer_track_lock',track_id=identity,locked=True);act(p,'layer_track_lock',track_id=identity,locked=False)
    act(p,'undo');assert p['manual']['layer_tracks']['version']==(2 if origin==2 or later_lock else 1)
    act(p,'redo');m=p['manual']['layer_tracks'];assert m['version']==3 and m['protection_version']==(2 if origin==2 or later_lock else 1)
    assert all(not t['locked'] for t in m['tracks'])

def test_mix_allowed_locked_and_partial_leaves(p):
    act(p,'layer_track_lock',track_id=track(p),locked=True)
    edit(p,gain_db=-6.123456);edit(p,muted=True);edit(p,gain_db=-2.75)
    assert track_audio_settings(p,track(p))=={'gain_db':-2.75,'muted':True}
    act(p,'undo');assert track_audio_settings(p,track(p))=={'gain_db':-6.123456,'muted':True}
    assert next(t for t in p['manual']['layer_tracks']['tracks'] if t['id']==track(p))['locked']

@pytest.mark.parametrize('bad',[True,None,float('nan'),float('inf'),-61,13,'-6'])
def test_bad_gain_atomic(p,bad):
    before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):edit(p,gain_db=bad)
    assert p==before

@pytest.mark.parametrize('patch',[{}, {'muted':1},{'gain_db':0,'extra':1}])
def test_bad_payload(p,patch):
    with pytest.raises(ManualEditError):edit(p,**patch)

@pytest.mark.parametrize('fault',['locked','extra','audio_extra','text_audio'])
def test_strict_v3(p,fault):
    edit(p,gain_db=-6);m=p['manual']['layer_tracks']
    if fault=='locked':m['tracks'][0]['locked']=True
    elif fault=='extra':m['extra']=0
    elif fault=='audio_extra':next(t for t in m['tracks'] if t['kind']!='text')['audio']['extra']=0
    else:next(t for t in m['tracks'] if t['kind']=='text')['audio']={'gain_db':0,'muted':False}
    with pytest.raises(LayerTrackError):validate_layer_tracks(p)

def test_duplicate_equal_gain_auto_add_neutral(p):
    edit(p,gain_db=-6);source=p['manual']['media_clips'][0]
    act(p,'media_duplicate',clip_id=source['id'],start=source['start'])
    duplicate=p['manual']['media_clips'][-1]
    assert track_audio_settings(p,duplicate['track_id'])=={'gain_db':-6,'muted':False}
    act(p,'media_add',asset_id=VIDEO,start=0)
    assert track_audio_settings(p,p['manual']['media_clips'][-1]['track_id'])=={'gain_db':0,'muted':False}


@pytest.mark.parametrize('action,detail',[
 ('media_insert',{'asset_id':VIDEO,'start':0,'source_start':0,'source_end':1}),
 ('media_append',{'asset_id':VIDEO,'source_start':0,'source_end':1})])
def test_automatic_creators_use_neutral(p,action,detail):
    edit(p,gain_db=-6);act(p,action,**detail)
    assert track_audio_settings(p,p['manual']['media_clips'][-1]['track_id'])=={'gain_db':0,'muted':False}

def test_split_inherits_levels_and_group_duplicate_preserves(p):
    edit(p,gain_db=-6);source=copy.deepcopy(p['manual']['media_clips'][0]);identity=source['track_id']
    act(p,'media_split',clip_id=source['id'],time=(source['start']+source['end'])/2)
    pieces=[r for r in p['manual']['media_clips'] if r['track_id']==identity and r['start']>=source['start'] and r['end']<=source['end']]
    assert len(pieces)==2
    act(p,'layers_duplicate',clip_ids=[r['id'] for r in pieces],start=source['start'])
    assert all(track_audio_settings(p,r['track_id'])=={'gain_db':-6,'muted':False} for r in p['manual']['media_clips'][-2:])

def test_explicit_destination_adopts_levels_and_identity(p):
    edit(p,gain_db=-6);identity=track(p)
    act(p,'media_append',asset_id=VIDEO,source_start=0,source_end=1,track_id=identity)
    assert p['manual']['media_clips'][-1]['track_id']==identity
    assert track_audio_settings(p,identity)['gain_db']==-6
    rendered=layer_tracks_render_identity(p)
    act(p,'layer_track_rename',track_id=identity,name='Renamed')
    assert layer_tracks_render_identity(p)==rendered


def test_protection_floor_cannot_be_removed_by_content(p):
    edit(p,gain_db=-6);act(p,'layer_track_lock',track_id=track(p),locked=True);act(p,'layer_track_lock',track_id=track(p),locked=False)
    candidate=copy.deepcopy(p);candidate['manual']['layer_tracks']['protection_version']=1
    with pytest.raises(LayerTrackError):validate_locked_layer_changes(p,candidate)


@pytest.mark.parametrize('kind,has_audio,audio_enabled,enabled,expected',[
 ('audio',None,False,True,True),('audio',False,None,True,True),
 ('video',True,None,True,False),('video',True,True,True,True),
 ('video',False,True,True,False),('audio',True,True,False,False)])
def test_identity_matches_renderer_audible(p,kind,has_audio,audio_enabled,enabled,expected):
    row=p['manual']['media_clips'][0];p['manual']['media_clips']=[row];p['manual']['text_clips']=[]
    asset=p['assets'][row['asset_id']];asset['kind']=kind
    if has_audio is None:asset.pop('has_audio',None)
    else:asset['has_audio']=has_audio
    if audio_enabled is None:row.pop('audio_enabled',None)
    else:row['audio_enabled']=audio_enabled
    row['enabled']=enabled
    t=next(t for t in p['manual']['layer_tracks']['tracks'] if t['id']==row['track_id']);t['kind']='audio' if kind=='audio' else 'visual'
    edit(p,gain_db=-6)
    assert bool(layer_tracks_render_identity(p).get('audio_levels'))==expected


from test_layer_tracks import tracked
from test_mixed_media_insert import post

@pytest.fixture
def levels_api(tracked):
    identity=track(tracked[2].load(tracked[3]))
    response=post(tracked,'layer_track_audio',track_id=identity,gain_db=-6.123456)
    assert response.status_code==200,response.get_json()
    return tracked

def test_api_partial_revision_noop_and_reopen(levels_api):
    from cutroom.projects import ProjectStore
    app,client,store,pid=levels_api;before=store.load(pid);identity=track(before)
    assert post(levels_api,'layer_track_audio',track_id=identity,muted=True).status_code==200
    accepted=store.load(pid);raw=store.state_path(pid).read_bytes()
    stale=client.post(f'/api/projects/{pid}/manual/edit',json={'action':'layer_track_audio','track_id':identity,'gain_db':-2.5,'expected_revision':before['revision']})
    assert stale.status_code==409 and store.state_path(pid).read_bytes()==raw
    assert post(levels_api,'layer_track_audio',track_id=identity,gain_db=-2.5).status_code==200
    assert track_audio_settings(store.load(pid),identity)=={'gain_db':-2.5,'muted':True}
    raw=store.state_path(pid).read_bytes()
    assert post(levels_api,'layer_track_audio',track_id=identity,gain_db=-2.5).status_code==200
    assert store.state_path(pid).read_bytes()==raw
    assert post(levels_api,'undo').status_code==200
    assert track_audio_settings(store.load(pid),identity)=={'gain_db':-6.123456,'muted':True}
    assert post(levels_api,'redo').status_code==200
    assert ProjectStore(app.extensions['cutroom_settings']).load(pid)==store.load(pid)

@pytest.mark.parametrize('fields',[{}, {'gain_db':True},{'muted':1},{'gain_db':-6,'extra':0}])
def test_api_invalid_atomic(levels_api,fields):
    _,_,store,pid=levels_api;raw=store.state_path(pid).read_bytes()
    assert post(levels_api,'layer_track_audio',track_id=track(store.load(pid)),**fields).status_code==400
    assert store.state_path(pid).read_bytes()==raw

def test_api_requires_revision_and_busy(levels_api,monkeypatch):
    app,client,store,pid=levels_api;raw=store.state_path(pid).read_bytes();identity=track(store.load(pid))
    assert client.post(f'/api/projects/{pid}/manual/edit',json={'action':'layer_track_audio','track_id':identity,'muted':True}).status_code==400
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'active',lambda **kw:[object()])
    assert post(levels_api,'layer_track_audio',track_id=identity,muted=True).status_code==409
    assert store.state_path(pid).read_bytes()==raw
    monkeypatch.undo()

@pytest.mark.parametrize('operation',['replace','remove','first_add'])
def test_v3_actual_b_reset_retains_levels(levels_api,monkeypatch,operation):
    from test_layer_tracks import test_actual_source_changes_preserve_only_b_independent_tracks
    test_actual_source_changes_preserve_only_b_independent_tracks(levels_api,monkeypatch,'B',operation,False)

def test_v3_retained_resume_exact(levels_api):
    import server
    from test_retained_edit import test_resume_exact_preservation_readonly_status_next_edit_undo
    _,_,store,pid=levels_api
    def reset(project):
        project['sources']['A']['preparation']='ready';project['analysis']=None;project['draft']=None
        server._reset_manual_after_source_change(project,'B',replacing=True)
    store.update(pid,reset)
    test_resume_exact_preservation_readonly_status_next_edit_undo(levels_api)

def test_v3_copy_independent_levels_history(levels_api):
    from test_project_copy import start,wait,inventory
    _,client,store,pid=levels_api;before=store.load(pid);raw=store.state_path(pid).read_bytes()
    token,_=start(levels_api);done=wait(client,token);assert done['status']=='completed',done
    after=store.load(done['copy_project_id'])
    for key in ('layer_tracks','media_clips','text_clips','sequence','source_tracks'):
        assert after['manual'][key]==before['manual'][key]
    assert after['manual']['_history']=={'undo':[],'redo':[]}
    for rel in inventory(store.project_dir(pid)):
        a=store.project_dir(pid)/rel;b=store.project_dir(after['id'])/rel
        assert a.read_bytes()==b.read_bytes() and a.stat().st_ino!=b.stat().st_ino
    assert store.state_path(pid).read_bytes()==raw
