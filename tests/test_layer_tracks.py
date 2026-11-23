"""Atomic lossless persistence and lane collision tests."""
import copy,json
import pytest
from cutroom.editing import apply_manual_edit,ManualEditError,strip_private_edit_history
from cutroom.layer_tracks import *
from cutroom.projects import ProjectStore
from test_media_append import content,library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers,post,VIDEO,media_row
from test_layer_selection import MEDIA,TEXT,IDS

@pytest.fixture
def tracked(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers)
    r=post(unlocked,'layer_tracks_enable');assert r.status_code==200,r.get_json()
    return unlocked

def test_migration_lossless_deterministic_undo_reopen(unlocked):
    app,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.load(pid);raw=store.state_path(pid).read_bytes()
    assert projected_layer_tracks(before)==projected_layer_tracks(before)
    assert store.state_path(pid).read_bytes()==raw
    assert post(unlocked,'layer_tracks_enable').status_code==200;after=store.load(pid)
    for key in ('media_clips','text_clips'):
        assert [{k:v for k,v in r.items() if k!='track_id'} for r in after['manual'][key]]==before['manual'][key]
    assert after['manual']['history']=={'undo_count':1,'redo_count':0}
    assert post(unlocked,'undo').status_code==200;assert content(store.load(pid))==content(before)
    assert post(unlocked,'redo').status_code==200;assert content(ProjectStore(app.extensions['cutroom_settings']).load(pid))==content(after)
    public=copy.deepcopy(after);strip_private_edit_history(public);assert public['manual']['text_clips'][0]['track_id']==after['manual']['text_clips'][0]['track_id']

def test_packing_obeys_overlapping_priority(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    p['manual']['media_clips']=[media_row('1',VIDEO,0,4),media_row('2',VIDEO,3,5),media_row('3',VIDEO,4,6),media_row('4',VIDEO,7,8)]
    q=projected_layer_tracks(p);r=q['manual']['media_clips'];rank={t['id']:i for i,t in enumerate(q['manual']['layer_tracks']['tracks'])}
    assert rank[r[0]['track_id']]<rank[r[1]['track_id']]<rank[r[2]['track_id']]
    assert r[3]['track_id']==r[0]['track_id']

def test_crud_identity_and_empty_only_remove(tracked):
    _,_,store,pid=tracked;before=store.load(pid);identity=layer_tracks_render_identity(before)
    assert post(tracked,'layer_track_add',kind='visual',name='  Upper  ').status_code==200
    p=store.load(pid);t=p['manual']['layer_tracks']['tracks'][-1];assert t['name']=='Upper';assert layer_tracks_render_identity(p)==identity
    assert post(tracked,'layer_track_rename',track_id=t['id'],name='Renamed').status_code==200
    assert layer_tracks_render_identity(store.load(pid))==identity
    assert post(tracked,'layer_track_remove',track_id=t['id']).status_code==200
    raw=store.state_path(pid).read_bytes();assert post(tracked,'layer_track_remove',track_id=before['manual']['media_clips'][0]['track_id']).status_code==400;assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize('action,detail',[
 ('media_split',{'clip_id':MEDIA,'time':5}),('text_split',{'clip_id':TEXT,'time':5}),
 ('media_duplicate',{'clip_id':MEDIA,'start':3}),('text_duplicate',{'clip_id':TEXT,'start':3}),
 ('media_insert',{'asset_id':VIDEO,'start':4,'source_start':0,'source_end':1}),
 ('media_add',{'asset_id':VIDEO,'start':4}),('media_append',{'asset_id':VIDEO,'source_start':0,'source_end':1}),
 ('text_add',{'kind':'title','start':4,'end':5,'text':'New','position':'top','scale':100,'style':'clean'}),
 ('text_import',{'format':'srt','content':'1\n00:00:04,000 --> 00:00:05,000\nNew\n','replace':False}),
 ('layers_move',{'clip_ids':IDS,'delta':1}),('layers_remove',{'clip_ids':IDS}),
])
def test_all_derived_and_creation_paths_history(tracked,action,detail):
    _,_,store,pid=tracked;before=store.load(pid);r=post(tracked,action,**detail);assert r.status_code==200,r.get_json()
    after=store.load(pid);validate_layer_tracks(after)
    assert post(tracked,'undo').status_code==200;assert content(store.load(pid))==content(before)
    assert post(tracked,'redo').status_code==200;assert content(store.load(pid))==content(after)

@pytest.mark.parametrize('action,detail',[('media_move',{'start':4}),('media_update',{'start':4,'end':5}),('media_trim',{'edge':'end','time':5}),('layer_move',{'start':4})])
def test_collision_rejection_is_atomic(unlocked,action,detail):
    _,_,store,pid=unlocked
    def setup(p):
        mixed_layers(p);p['manual']['media_clips']=[media_row('1',VIDEO,1,2),media_row('2',VIDEO,4,5)];p['manual']['text_clips']=[]
    store.update(pid,setup);assert post(unlocked,'layer_tracks_enable').status_code==200
    args=dict(detail)
    if action=='layer_move':args['track_id']=store.load(pid)['manual']['media_clips'][0]['track_id']
    raw=store.state_path(pid).read_bytes();r=post(unlocked,action,clip_id='media_'+'1'*32,**args);assert r.status_code==400,r.get_json();assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize('position',['backward','forward','back','front'])
def test_reorder_preserves_all_content_other_bands(tracked,position):
    _,_,store,pid=tracked;p=store.load(pid);t=next(t for t in p['manual']['layer_tracks']['tracks'] if t['kind']=='visual')
    assert post(tracked,'layer_track_reorder',track_id=t['id'],position=position).status_code==200
    q=store.load(pid)
    for k in ('media_clips','text_clips','sequence','source_tracks'):assert q['manual'][k]==p['manual'][k]
    assert [t for t in q['manual']['layer_tracks']['tracks'] if t['kind']!='visual']==[t for t in p['manual']['layer_tracks']['tracks'] if t['kind']!='visual']

@pytest.mark.parametrize('name',[None,'','   ','x'*81,True])
def test_bad_names_atomic(tracked,name):
    _,_,store,pid=tracked;raw=store.state_path(pid).read_bytes();assert post(tracked,'layer_track_add',kind='visual',name=name).status_code==400;assert store.state_path(pid).read_bytes()==raw

def test_unicode_name_codepoints(tracked):
    _,_,store,pid=tracked;name=chr(0x1f600)*80
    assert post(tracked,'layer_track_add',kind='audio',name=' '+name+' ').status_code==200
    assert store.load(pid)['manual']['layer_tracks']['tracks'][-1]['name']==name

@pytest.mark.parametrize('fault',[{'version':2,'tracks':[]},{'version':True,'tracks':[]},{'version':1,'tracks':None},{'version':1,'tracks':[],'other':1}])
def test_future_malformed_model_blocks_edit_and_save(unlocked,fault):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);p['manual']['layer_tracks']=fault;before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{'action':'layers_remove','clip_ids':IDS})
    assert p==before;raw=store.state_path(pid).read_bytes()
    with pytest.raises(LayerTrackError):store.save(p)
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize('fault',['duplicate','missing','kind','nan','name','extra','overlap'])
def test_invalid_membership_structures_fail_closed(tracked,fault):
    _,_,store,pid=tracked;p=store.load(pid);m=p['manual'];r=m['media_clips'][0]
    if fault=='duplicate':m['layer_tracks']['tracks'].append(copy.deepcopy(m['layer_tracks']['tracks'][0]))
    elif fault=='missing':r['track_id']='track_'+'f'*32
    elif fault=='kind':r['track_id']=m['text_clips'][0]['track_id']
    elif fault=='nan':r['start']=float('nan')
    elif fault=='name':m['layer_tracks']['tracks'][0]['name']=' bad '
    elif fault=='extra':m['layer_tracks']['tracks'][0]['mute']=True
    else:m['media_clips'].append({**r,'id':'media_'+'f'*32,'enabled':False})
    before=json.dumps(p,sort_keys=True)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{'action':'layer_track_add','kind':'audio','name':'New'})
    assert json.dumps(p,sort_keys=True)==before

def test_orphan_membership_fails(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);p['manual']['media_clips'][0]['track_id']='track_'+'1'*32
    with pytest.raises(LayerTrackError):validate_layer_tracks(p)

def test_bad_persisted_version_cannot_background_save(tracked):
    _,_,store,pid=tracked;p=store.load(pid);p['manual']['layer_tracks']['version']=2;path=store.state_path(pid);path.write_text(json.dumps(p));raw=path.read_bytes()
    with pytest.raises(LayerTrackError):store.update(pid,lambda value:value.update(name='Background'))
    assert path.read_bytes()==raw

def test_revision_busy_noops_and_field_contract(tracked,monkeypatch):
    app,client,store,pid=tracked;p=store.load(pid);t=p['manual']['layer_tracks']['tracks'][0];raw=store.state_path(pid).read_bytes()
    assert post(tracked,'layer_tracks_enable').status_code==200;assert store.state_path(pid).read_bytes()==raw
    assert post(tracked,'layer_track_rename',track_id=t['id'],name=t['name']).status_code==200;assert store.state_path(pid).read_bytes()==raw
    assert post(tracked,'layer_track_add',kind='visual',name='New',expected_revision=p['revision']-1).status_code==409
    assert post(tracked,'layer_track_add',kind='visual',name='New',mute=True).status_code==400
    assert client.post(f'/api/projects/{pid}/manual/edit',json={'action':'layer_tracks_enable'}).status_code==400
    with monkeypatch.context() as m:
        m.setattr(app.extensions['cutroom_jobs'],'active',lambda **kw:[object()]);assert post(tracked,'layer_track_add',kind='audio',name='New').status_code==409
    assert store.state_path(pid).read_bytes()==raw

def test_pure_vertical_failed_asset_and_fractional_preservation(tracked):
    _,_,store,pid=tracked;post(tracked,'layer_track_add',kind='visual',name='Off')
    def setup(p):
        p['manual']['media_clips'][0].update(start=.123456789123,end=.987654321987)
        asset=p['manual']['media_clips'][0]['asset_id'];p['assets'][asset]['status']='failed'
    store.update(pid,setup);p=store.load(pid);r=p['manual']['media_clips'][0];target=p['manual']['layer_tracks']['tracks'][-1]['id']
    assert post(tracked,'layer_move',clip_id=r['id'],track_id=target,start=r['start']).status_code==200
    assert {**store.load(pid)['manual']['media_clips'][0],'track_id':r['track_id']}==r
    raw=store.state_path(pid).read_bytes();assert post(tracked,'layer_move',clip_id=r['id'],track_id=target,start=1).status_code==400;assert store.state_path(pid).read_bytes()==raw

def test_legacy_read_and_settings_never_enable(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);raw=store.state_path(pid).read_bytes();assert validate_layer_tracks(store.load(pid)) is None;assert store.state_path(pid).read_bytes()==raw
    store.update(pid,lambda p:p.update(name='Settings'));assert 'layer_tracks' not in store.load(pid)['manual']

def test_missing_kind_blocks_migration_but_failed_known_kind_accepted(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);p['assets'][VIDEO]['status']='failed';validate_layer_tracks(projected_layer_tracks(p));p['assets'][VIDEO].pop('kind')
    with pytest.raises(LayerTrackError):projected_layer_tracks(p)

def test_old_media_reorder_refused(tracked):
    _,_,store,pid=tracked;raw=store.state_path(pid).read_bytes();r=post(tracked,'media_reorder',clip_id=MEDIA,position='front');assert r.status_code==400 and 'whole-track' in r.get_json()['message'];assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize('bad',[[],{},False,12])
def test_malformed_track_ids_and_kinds_raise_typed_error(tracked,bad):
    _,_,store,pid=tracked;p=store.load(pid);p['manual']['media_clips'][0]['track_id']=bad
    with pytest.raises(LayerTrackError):validate_layer_tracks(p)
    p=store.load(pid);p['manual']['layer_tracks']['tracks'][0]['kind']=bad
    with pytest.raises(LayerTrackError):validate_layer_tracks(p)

def test_track_capacity_and_empty_timeline_model(tracked):
    _,_,store,pid=tracked;p=store.load(pid)
    p['manual']['media_clips']=[];p['manual']['text_clips']=[]
    p['manual']['layer_tracks']['tracks']=[{'id':f'track_{i:032x}','kind':'visual','name':'Empty'} for i in range(4096)]
    validate_layer_tracks(p);before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{'action':'layer_track_add','kind':'audio','name':'Extra'})
    assert p==before

def test_global_text_overlap_limit_does_not_reset_per_track(tracked):
    _,_,store,pid=tracked;p=store.load(pid);original=p['manual']['text_clips'][0]
    p['manual']['text_clips']=[]
    for i in range(17):
        tid=f'track_{i+100:032x}';p['manual']['layer_tracks']['tracks'].append({'id':tid,'kind':'text','name':'Text'})
        p['manual']['text_clips'].append({**original,'id':f'text_{i+100:032x}','track_id':tid,'enabled':False})
    with pytest.raises(ValueError,match='16'):validate_layer_tracks(p)

def test_track_conversion_source_locks_and_content_are_independent(unlocked):
    _,_,store,pid=unlocked
    def setup(p):mixed_layers(p);p['manual']['track_locks']={'A':True,'B':True}
    store.update(pid,setup);before=store.load(pid)
    assert post(unlocked,'layer_tracks_enable').status_code==200
    assert post(unlocked,'layer_track_add',kind='visual',name='New').status_code==200
    after=store.load(pid)
    for key in ('source_tracks','sequence','track_locks','source_mixer'):assert after['manual'].get(key)==before['manual'].get(key)
    for key in ('assets','sources','settings','analysis'):assert after.get(key)==before.get(key)


@pytest.mark.parametrize('fault',['future','malformed','orphan'])
def test_incompatible_tracks_api_returns_reason_without_job_or_write(unlocked,monkeypatch,fault):
    app,client,store,pid=unlocked;store.update(pid,mixed_layers);p=store.load(pid)
    if fault=='future':p['manual']['layer_tracks']={'version':2,'tracks':[]}
    elif fault=='malformed':p['manual']['layer_tracks']={'version':1,'tracks':None}
    else:p['manual']['media_clips'][0]['track_id']='track_'+'a'*32
    path=store.state_path(pid);path.write_text(json.dumps(p),encoding='utf8');raw=path.read_bytes()
    def forbidden(*args,**kwargs):pytest.fail('Invalid track model must not admit a render or estimate storage')
    monkeypatch.setattr('server.ensure_render_storage',forbidden)
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'submit',forbidden)
    # Read still exposes the saved state for a truthful compatibility message.
    assert client.get(f'/api/projects/{pid}').status_code==200
    for method,url,body in [
        ('post',f'/api/projects/{pid}/render',{}),
        ('patch',f'/api/projects/{pid}',{'name':'Must not save'}),
        ('post',f'/api/projects/{pid}/manual/edit',{'action':'layer_tracks_enable','expected_revision':p['revision']}),
    ]:
        response=getattr(client,method)(url,json=body)
        assert response.status_code==409,response.get_json()
        assert response.get_json()['error']=='layer_tracks_incompatible'
        assert response.get_json()['message'] and 'internal' not in response.get_json()['message'].lower()
        assert path.read_bytes()==raw
    assert app.extensions['cutroom_jobs'].active(project_id=pid)==[]

def test_render_admission_rechecks_model_after_initial_inspection(tracked,monkeypatch):
    app,client,store,pid=tracked
    import server
    original=server.ensure_render_storage
    def replace_after_estimate(*args,**kwargs):
        p=store.load(pid);p['manual']['layer_tracks']['version']=2
        store.state_path(pid).write_text(json.dumps(p),encoding='utf8')
        return {}
    monkeypatch.setattr(server,'require_layout_coverage',lambda *a,**kw:None)
    monkeypatch.setattr(server,'ensure_render_storage',replace_after_estimate)
    def forbidden(*args,**kwargs):pytest.fail('Changed model must not admit a render')
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'submit',forbidden)
    response=client.post(f'/api/projects/{pid}/render',json={})
    assert response.status_code==409,response.get_json()
    assert response.get_json()['error']=='layer_tracks_incompatible'
    assert app.extensions['cutroom_jobs'].active(project_id=pid)==[]


from test_ai_draft_review import api as ai_api, base_api, review as ai_review, apply as ai_apply, post as ai_post

@pytest.mark.parametrize('isolated',[False,True])
def test_ai_review_apply_history_retains_track_model_and_collision_policy(ai_api,isolated):
    from cutroom.ai_draft_proposals import record_isolated_ai_draft
    from cutroom.sequence import editor_sequence_snapshot
    app,_,store,pid,source=ai_api
    aid='asset_'+'d'*32
    relative=f'media/assets/{aid}/original.mp4'
    target=store.project_dir(pid)/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
    def prepare(p):
        p['settings'].update(captions=False,burn_captions=False)
        p.setdefault('assets',{})[aid]={'id':aid,'kind':'video','status':'ready','duration':20,'width':160,'height':90,'has_audio':True,'path':relative}
    store.update(pid,prepare)
    assert ai_post(ai_api,'media_add',asset_id=aid,start=2,end=3).status_code==200
    assert ai_post(ai_api,'text_add',kind='title',start=1,end=2,text='First').status_code==200
    assert ai_post(ai_api,'text_add',kind='title',start=4,end=5,text='Second').status_code==200
    assert ai_post(ai_api,'layer_tracks_enable').status_code==200
    assert ai_post(ai_api,'layer_track_add',kind='visual',name='Retained empty lane').status_code==200
    if isolated:store.update(pid,lambda p:record_isolated_ai_draft(p,copy.deepcopy(p)))
    before=store.load(pid);raw=store.state_path(pid).read_bytes();original=source.read_bytes()
    response=ai_review(ai_api);assert response.status_code==200,response.get_json()
    proposal=response.get_json()['proposal'];assert proposal['apply_allowed'] and proposal['impact']['text_preserved'],proposal
    assert store.state_path(pid).read_bytes()==raw
    response=ai_apply(ai_api,proposal);assert response.status_code==200,response.get_json()
    after=store.load(pid);validate_layer_tracks(after)
    assert editor_sequence_snapshot(after)['duration']==12
    for key in ('layer_tracks','media_clips','text_clips'):assert after['manual'].get(key)==before['manual'].get(key)
    assert ai_post(ai_api,'undo').status_code==200
    undone=ProjectStore(app.extensions['cutroom_settings']).load(pid)
    assert editor_sequence_snapshot(undone)==editor_sequence_snapshot(before)
    for key in ('layer_tracks','media_clips','text_clips'):assert undone['manual'].get(key)==before['manual'].get(key)
    assert ai_post(ai_api,'redo').status_code==200
    redone=store.load(pid);validate_layer_tracks(redone)
    for key in ('layer_tracks','media_clips','text_clips'):assert redone['manual'].get(key)==after['manual'].get(key)
    raw=store.state_path(pid).read_bytes();first=redone['manual']['text_clips'][0]
    rejected=ai_post(ai_api,'text_move',clip_id=first['id'],start=4)
    assert rejected.status_code==400 and 'overlap' in rejected.get_json()['message']
    assert store.state_path(pid).read_bytes()==raw
    assert source.read_bytes()==original and target.read_bytes()==original
    # Source sequence reset uses the same staged admission, not a track reset.
    reset=ai_post(ai_api,'sequence_reset');assert reset.status_code==200,reset.get_json()
    for key in ('layer_tracks','media_clips','text_clips'):assert store.load(pid)['manual'].get(key)==after['manual'].get(key)

@pytest.mark.parametrize('isolated',[False,True])
def test_ai_shorter_proposal_cannot_strand_tracked_layers(ai_api,isolated):
    from cutroom.ai_draft_proposals import record_isolated_ai_draft
    _,_,store,pid,_=ai_api
    store.update(pid,lambda p:p['settings'].update(captions=False,burn_captions=False))
    assert ai_post(ai_api,'text_add',kind='title',start=15,end=18,text='Keep this occurrence').status_code==200
    assert ai_post(ai_api,'layer_tracks_enable').status_code==200
    if isolated:store.update(pid,lambda p:record_isolated_ai_draft(p,copy.deepcopy(p)))
    raw=store.state_path(pid).read_bytes();response=ai_review(ai_api)
    assert response.status_code==200,response.get_json()
    proposal=response.get_json()['proposal'];assert not proposal['apply_allowed'] and proposal['apply_issue']
    refused=ai_apply(ai_api,proposal);assert refused.status_code in (400,409),refused.get_json()
    assert store.state_path(pid).read_bytes()==raw
    validate_layer_tracks(store.load(pid))


@pytest.mark.parametrize('fault',['future','malformed','orphan'])
@pytest.mark.parametrize('endpoint',['director','director/refine','uploads/preflight','sources/A','assets'])
def test_incompatible_model_cannot_start_ai_or_allocate_upload(unlocked,monkeypatch,fault,endpoint):
    app,client,store,pid=unlocked;store.update(pid,mixed_layers);p=store.load(pid)
    if fault=='future':p['manual']['layer_tracks']={'version':2,'tracks':[]}
    elif fault=='malformed':p['manual']['layer_tracks']={'version':1,'tracks':None}
    else:p['manual']['media_clips'][0]['track_id']='track_'+'a'*32
    path=store.state_path(pid);path.write_text(json.dumps(p),encoding='utf8');raw=path.read_bytes()
    before={str(f.relative_to(store.project_dir(pid))):f.read_bytes() for f in store.project_dir(pid).rglob('*') if f.is_file()}
    def forbidden(*args,**kwargs):pytest.fail('Invalid model reached provider/job/preallocation work')
    monkeypatch.setattr(app.extensions['cutroom_connections'],'job_settings',forbidden)
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'submit',forbidden)
    monkeypatch.setattr('server.story_ai_status',forbidden)
    payload={'command':'shorter'} if endpoint.endswith('refine') else {'purpose':'asset','filename':'new.mp4','size_bytes':100} if endpoint=='uploads/preflight' else {}
    response=client.post(f'/api/projects/{pid}/{endpoint}',json=payload)
    assert response.status_code==409,response.get_json()
    assert response.get_json()['error']=='layer_tracks_incompatible'
    assert path.read_bytes()==raw
    assert {str(f.relative_to(store.project_dir(pid))):f.read_bytes() for f in store.project_dir(pid).rglob('*') if f.is_file()}==before
    assert app.extensions['cutroom_jobs'].active(project_id=pid)==[]


def test_common_job_gate_rechecks_tracks_after_provider_settings_snapshot(tracked,monkeypatch):
    app,client,store,pid=tracked
    def settings_then_corrupt(*args,**kwargs):
        p=store.load(pid);p['manual']['layer_tracks']['version']=2
        store.state_path(pid).write_text(json.dumps(p),encoding='utf8')
        return app.extensions['cutroom_settings']
    def forbidden(*args,**kwargs):pytest.fail('Common job gate admitted incompatible tracks')
    monkeypatch.setattr(app.extensions['cutroom_connections'],'job_settings',settings_then_corrupt)
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'submit',forbidden)
    response=client.post(f'/api/projects/{pid}/director/refine',json={'command':'shorter'})
    assert response.status_code==409,response.get_json()
    assert response.get_json()['error']=='layer_tracks_incompatible'
    assert app.extensions['cutroom_jobs'].active(project_id=pid)==[]


@pytest.mark.parametrize('legacy',[False,True])
@pytest.mark.parametrize('slot,operation',[('B','replace'),('B','remove'),('B','first_add'),('A','replace'),('A','remove')])
def test_actual_source_changes_preserve_only_b_independent_tracks(tracked,monkeypatch,slot,operation,legacy):
    import io
    import server
    from test_backend_hardening import _probe, _QueuedJob
    app,client,store,pid=tracked
    assert post(tracked,'layer_track_add',kind='visual',name='Keep empty lane').status_code==200
    if operation=='first_add':
        def without_b(p):
            p['sources'].pop('B',None)
            p['manual']['source_tracks']['B']=[]
        store.update(pid,without_b)
    if legacy:
        def remove_sequence(p):
            p['manual'].pop('sequence',None)
            p['manual'].pop('source_tracks',None)
        store.update(pid,remove_sequence)
    before=store.load(pid)
    from cutroom.sequence import materialize_sequence
    anchored,_=materialize_sequence(before)
    independent={k:copy.deepcopy(before['manual'].get(k)) for k in ('layer_tracks','media_clips','text_clips','audio_mixer')}
    assets=copy.deepcopy(before['assets'])
    media_files={str(p):p.read_bytes() for p in (store.project_dir(pid)/'media'/'assets').rglob('*') if p.is_file()}
    monkeypatch.setattr(server,'probe_media',_probe)
    monkeypatch.setattr(app.extensions['cutroom_jobs'],'submit',lambda *args,**kwargs:_QueuedJob())
    if operation=='remove':
        response=client.delete(f'/api/projects/{pid}/sources/{slot}')
    else:
        response=client.post(f'/api/projects/{pid}/sources/{slot}',data={'file':(io.BytesIO(b'new generated source'),f'new-{slot}.mp4')},content_type='multipart/form-data')
    assert response.status_code==(200 if operation=='remove' else 201),response.get_json()
    after=ProjectStore(app.extensions['cutroom_settings']).load(pid)
    validate_layer_tracks(after)
    if slot=='B':
        assert {k:after['manual'].get(k) for k in independent}==independent
        assert after['manual']['source_tracks']['A']==anchored['manual']['source_tracks']['A']
        assert after['manual']['sequence']['duration']==anchored['manual']['sequence']['duration']
    else:
        assert 'layer_tracks' not in after['manual']
        assert not after['manual'].get('media_clips') and not after['manual'].get('text_clips')
    assert after['assets']==assets
    assert all(__import__('pathlib').Path(path).read_bytes()==raw for path,raw in media_files.items())
    assert after['manual']['history']=={'undo_count':0,'redo_count':0}


@pytest.mark.parametrize('sequence',[None,{}, {'version':2,'duration':15}, {'version':1,'duration':float('nan'),'camera_plan':[]}, {'version':1,'duration':15,'camera_plan':None}])
def test_draftless_retained_tracks_require_valid_explicit_sequence(tracked,sequence):
    _,_,store,pid=tracked;p=store.load(pid);p['draft']=None;p['manual']['sequence']=sequence
    with pytest.raises(ValueError):validate_layer_tracks(p)


def test_draftless_retained_tracks_validate_bounds_and_recover_without_migration(tracked):
    _,_,store,pid=tracked;before=store.load(pid)
    import server
    def reset(p):
        p['draft']=None
        server._reset_manual_after_source_change(p,'B',replacing=True)
    store.update(pid,reset);pending=store.load(pid)
    assert pending['draft'] is None
    assert pending['manual']['layer_tracks']==before['manual']['layer_tracks']
    invalid=copy.deepcopy(pending);invalid['manual']['sequence']['duration']=1
    with pytest.raises(ValueError):validate_layer_tracks(invalid)
    store.update(pid,lambda p:p.update(draft=copy.deepcopy(before['draft'])))
    recovered=store.load(pid);validate_layer_tracks(recovered)
    for key in ('layer_tracks','media_clips','text_clips'):assert recovered['manual'][key]==before['manual'][key]
