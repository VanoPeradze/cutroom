"""Reviewed independent-video insertion reuses linked source time and shared Undo."""
import copy
import pytest
from test_media_append import library_api, append_project, ASSET  # noqa:F401
from cutroom.render import project_caption_items

@pytest.fixture
def unlocked(library_api):
    _,_,store,pid=library_api
    value=append_project();value['id']=pid;value['manual']['track_locks']={};value['draft']['audio_plan']=[]
    store.save({**store.load(pid),**value})
    root=store.project_dir(pid)
    relatives=[x['relative_path'] for x in value['sources'].values()]+[value['assets'][ASSET][k] for k in ('path','preview_path')]
    for relative in relatives:
        p=root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'Synthetic media')
    return library_api

def insert(api,**extra):
    _,client,store,pid=api
    return client.post(f"/api/projects/{pid}/manual/edit",json={"action":"media_insert","asset_id":ASSET,"source_start":.25,"source_end":1.5,"start":5.,"expected_revision":store.load(pid)["revision"],**extra})

def test_linked_insertion_splits_only_at_point_and_preserves_source_crop_audio_and_undo(unlocked):
    _,client,store,pid=unlocked;before=store.load(pid);captions=project_caption_items(before,aligned=False)
    r=insert(unlocked);assert r.status_code==200,r.get_json()
    p=store.load(pid);assert p["manual"]["sequence"]["duration"]==16.25
    new=p["manual"]["media_clips"][-1];assert(new["start"],new["end"],new["source_start"])==(5.,6.25,.25)
    assert new["audio_enabled"] is True
    for slot in ['A','B']:
        for old in before["manual"]["source_tracks"][slot]:
            pieces=[c for c in p["manual"]["source_tracks"][slot] if c.get("caption_origin",c["id"])==old.get("caption_origin",old["id"])]
            assert sum(c["end"]-c["start"] for c in pieces)==pytest.approx(old["end"]-old["start"])
            assert all(c.get("crop")==old.get("crop") for c in pieces)
    assert p["sources"]==before["sources"] and p["assets"]==before["assets"] and p["analysis"]==before["analysis"]
    assert project_caption_items(p,aligned=False)[0]==captions[0]
    snapshot=copy.deepcopy(p["manual"])
    for action in ['undo','redo']:
        result=client.post(f"/api/projects/{pid}/manual/edit",json={"action":action,"expected_revision":store.load(pid)["revision"]});assert result.status_code==200
        if action=='undo':
            restored=store.load(pid)
            for key,value in before["manual"].items():
                if key not in {'history','_history'}:assert restored["manual"].get(key)==value
    after=store.load(pid)
    for key,value in snapshot.items():
        if key not in {'history','_history'}:assert after["manual"].get(key)==value

@pytest.mark.parametrize('kind',['audio','video','image','text'])
def test_wholly_downstream_independent_layers_ripple_without_changing_local_source_time(unlocked,kind):
    _,_,store,pid=unlocked
    def layer(p):
        if kind=='text':p['manual']['text_clips']=[{'id':'text_'+'b'*32,'kind':'caption','start':8.,'end':9.,'text':'User event caption','style':'clean','position':'bottom','scale':100}]
        else:
            p['assets'][ASSET]['kind']=kind
            # Use a distinct ready layer asset so inserted source remains video.
            other='asset_'+'b'*32;p['assets'][other]={**p['assets'][ASSET],'id':other,'kind':kind}
            p['assets'][ASSET]['kind']='video'
            p['manual']['media_clips']=[{'id':'media_'+'b'*32,'asset_id':other,'start':8.,'end':9.,'source_start':1.,'speed':1.,'volume_db':-3.,'muted':False,'role':'voice','fade_in':.1,'fade_out':.1,'x':0.,'y':0.,'w':1.,'h':1.,'fit':'contain','motion':'none','audio_enabled':kind=='audio'}]
    p=store.update(pid,layer);key='text_clips' if kind=='text' else 'media_clips';old=p['manual'][key][0]
    result=insert(unlocked);assert result.status_code==200,result.get_json();row=store.load(pid)['manual'][key][0]
    assert row=={**old,'start':9.25,'end':10.25}

@pytest.mark.parametrize('kind',['media','text','caption','alternative','audio_plan','locked'])
def test_unsupported_crossing_or_protected_state_is_atomic(unlocked,kind):
    _,_,store,pid=unlocked
    def prepare(p):
        if kind=='media':p['manual']['media_clips']=[{'id':'media_'+'c'*32,'asset_id':ASSET,'start':4.,'end':6.,'source_start':0.,'speed':1.,'volume_db':0.,'muted':False,'role':'voice','fade_in':0.,'fade_out':0.,'x':0.,'y':0.,'w':1.,'h':1.,'fit':'cover','motion':'none','audio_enabled':True}]
        if kind=='text':p['manual']['text_clips']=[{'id':'text_'+'c'*32,'kind':'title','start':4.,'end':6.,'text':'Crossing title','style':'clean','position':'center','scale':100}]
        if kind=='caption':p['manual']['caption_overrides']['missing-caption-owner']={'text':'Preserve me'}
        if kind=='audio_plan':p['draft']['audio_plan']=[{'start':0.,'end':10.,'action':'normalize'}]
        if kind=='locked':p['manual']['track_locks']={'A':True}
        if kind=='alternative':
            from cutroom.caption_alternatives import FORMAT,binding,register,geometry
            key=register(p,{'format':FORMAT,'binding':binding(p),'source_interval':[0.,20.],'transcript':{'segments':[{'id':'s','start':0.,'end':20.,'text':'Unverified alternative','words':[]}]}})
            p['manual']['caption_alternative']={'id':key,'geometry':geometry(p)}
    store.update(pid,prepare);before=store.state_path(pid).read_bytes();r=insert(unlocked);assert r.status_code==400,r.get_json();assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize('at',[-1,99,True,float('nan')])
def test_bad_insertion_position_rejected_without_history(unlocked,at):
    _,_,store,pid=unlocked;before=store.state_path(pid).read_bytes();assert insert(unlocked,start=at).status_code==400;assert store.state_path(pid).read_bytes()==before

def test_downstream_manual_caption_text_and_anchor_follow_source(unlocked):
    _,_,store,pid=unlocked
    def add_caption(p):
        p['analysis']['transcript']['segments'].append({'id':'later','start':8.,'end':9.,'text':'Later source words'})
        row=next(x for x in project_caption_items(p,aligned=False) if x['text']=='Later source words')
        p['manual']['caption_overrides'][row['id']]={'text':'Later manual wording'}
        p['manual']['caption_override_anchors'][row['id']]=copy.deepcopy(row['_caption_anchor'])
    store.update(pid,add_caption)
    result=insert(unlocked);assert result.status_code==200,result.get_json()
    row=next(x for x in project_caption_items(store.load(pid),aligned=False) if x['text']=='Later manual wording')
    assert (row['start'],row['end'])==(9.25,10.25)
