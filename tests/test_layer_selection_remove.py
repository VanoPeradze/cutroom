"""Atomic occurrence removal: files and surviving timing are never deleted."""
import copy
import hashlib
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.projects import ProjectStore
from cutroom.layer_selection import prepare_layer_selection_edit
from test_media_append import content, library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers, post, media_row, VIDEO
from test_layer_selection import IDS, MEDIA, TEXT

@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("selection", [IDS, [MEDIA,TEXT], IDS[:3], IDS[3:]])
def test_remove_exact_survivors_one_history_and_reopen(unlocked,locked,selection):
    app,_,store,pid=unlocked
    def setup(p):
        mixed_layers(p)
        p['manual']['track_locks']={'A':locked,'B':locked}
        p['manual']['media_clips'][1]['enabled']=False
        p['manual']['text_clips'][1]['enabled']=False
    store.update(pid,setup);before=store.load(pid)
    files={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in store.project_dir(pid).glob('media/**/*') if p.is_file()}
    response=post(unlocked,'layers_remove',clip_ids=selection)
    assert response.status_code==200,response.get_json()
    after=store.load(pid)
    for key in ('media_clips','text_clips'):
        assert after['manual'][key]==[row for row in before['manual'][key] if row['id'] not in selection]
    for key,value in before['manual'].items():
        if key not in ('media_clips','text_clips','history','_history'):assert after['manual'][key]==value
    for key in ('sources','assets','analysis','settings'):assert after[key]==before[key]
    assert after['revision']==before['revision']+1
    assert after['manual']['history']=={'undo_count':1,'redo_count':0}
    assert post(unlocked,'undo').status_code==200
    assert content(store.load(pid))==content(before)
    assert post(unlocked,'redo').status_code==200
    assert content(ProjectStore(app.extensions['cutroom_settings']).load(pid))==content(after)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}==files

@pytest.mark.parametrize('ids',[None,[],[MEDIA],[MEDIA,MEDIA],[MEDIA,'A'],[MEDIA,'caption_123'],[MEDIA,'text_'+'f'*32],[MEDIA,False],[MEDIA,{}],'all',[MEDIA]*201])
def test_invalid_membership_is_byte_exact(unlocked,ids):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,'layers_remove',clip_ids=ids).status_code==400
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize('extra',[{'delta':0},{'start':1},{'enabled':False},{'clip_id':MEDIA}])
def test_unknown_fields_rejected(unlocked,extra):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,'layers_remove',clip_ids=IDS,**extra).status_code==400
    assert store.state_path(pid).read_bytes()==before

def test_revision_and_busy_gate(unlocked,monkeypatch):
    app,client,store,pid=unlocked;store.update(pid,mixed_layers);rev=store.load(pid)['revision'];store.update(pid,lambda p:p.update(name='concurrent'));before=store.state_path(pid).read_bytes()
    assert client.post(f'/api/projects/{pid}/manual/edit',json={'action':'layers_remove','clip_ids':IDS}).status_code==400
    assert post(unlocked,'layers_remove',clip_ids=IDS,expected_revision=rev).status_code==409
    with monkeypatch.context() as m:
        m.setattr(app.extensions['cutroom_jobs'],'active',lambda **kw:[object()])
        assert post(unlocked,'layers_remove',clip_ids=IDS).status_code==409
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize('key',['media_clips','text_clips'])
@pytest.mark.parametrize('fault',['null','mapping','duplicate','bad_id'])
def test_structural_ambiguity_fails_without_mutation(unlocked,key,fault):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    if fault=='null':p['manual'][key].append(None)
    elif fault=='mapping':p['manual'][key]={}
    elif fault=='duplicate':p['manual'][key].append(copy.deepcopy(p['manual'][key][0]))
    else:p['manual'][key][0]['id']='media_bad'
    before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{'action':'layers_remove','clip_ids':IDS})
    assert p==before

def test_offline_disabled_corrupt_removed_content_is_not_move_validated(unlocked):
    _,_,store,pid=unlocked
    def setup(p):
        mixed_layers(p)
        p['assets'][VIDEO]['status']='failed'
        p['manual']['media_clips'][0].update(enabled=False,asset_id='missing',source_start=-99)
        p['manual']['text_clips'][0].update(enabled=False,text='')
    store.update(pid,setup);before=store.load(pid)
    response=post(unlocked,'layers_remove',clip_ids=[MEDIA,TEXT]);assert response.status_code==200,response.get_json()
    assert post(unlocked,'undo').status_code==200
    assert content(store.load(pid))==content(before)

def test_maximum_selection_can_empty_independent_timeline_without_duration_loss(unlocked):
    _,_,store,pid=unlocked
    def setup(p):
        mixed_layers(p);p['manual']['source_tracks']={'A':[],'B':[]}
        p['manual']['media_clips']=[media_row('1',VIDEO,1,2,id=f'media_{i:032x}') for i in range(200)]
        p['manual']['text_clips']=[]
    store.update(pid,setup);before=store.load(pid)
    assert post(unlocked,'layers_remove',clip_ids=[r['id'] for r in before['manual']['media_clips']]).status_code==200
    after=store.load(pid);assert after['manual']['media_clips']==[]
    assert after['manual']['sequence']==before['manual']['sequence']
    assert after['manual']['source_tracks']==before['manual']['source_tracks']
    assert after['assets']==before['assets']

def test_prepare_is_detached_and_preserves_surviving_raw_fields(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    p['manual']['media_clips'][-1]['private_extra']={'fraction':.123456789123}
    before=copy.deepcopy(p);payload={'action':'layers_remove','clip_ids':[MEDIA,TEXT]}
    result=prepare_layer_selection_edit(p,payload)
    assert p==before
    result['media_clips'][-1]['private_extra']['fraction']=0
    assert p==before


def test_real_production_remove_reveals_source_and_preserves_export_duration(library_api,media):
    from test_selected_layer_trim import render_setup
    from test_media_render import samples,tone_level
    import subprocess
    store,pid,settings,encoded,hashes,originals=render_setup(library_api,media,.5)
    original,original_record=encoded('remove-original')
    before=store.load(pid);selected=['media_'+'1'*32,'media_'+'2'*32,'text_'+'1'*32]
    def reference(p):
        for key in ('media_clips','text_clips'):
            p['manual'][key]=[row for row in p['manual'][key] if row['id'] not in selected]
    store.update(pid,reference);expected,expected_record=encoded('remove-reference')
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before['manual'])))
    response=post(library_api,'layers_remove',clip_ids=selected);assert response.status_code==200,response.get_json()
    actual,record=encoded('remove-actual')
    def frame(path):
        return subprocess.check_output([media[1],'-v','error','-ss','1.4','-i',str(path),'-an','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    old,want,got=map(frame,(original,expected,actual))
    assert len(want)==len(got)>0
    assert sum(abs(a-b) for a,b in zip(want,got))/len(got)<2
    assert sum(abs(a-b) for a,b in zip(old,got))/len(got)>1
    old_audio,new_audio=samples(media[1],original),samples(media[1],actual)
    assert tone_level(old_audio,1.4,880)>.01
    assert tone_level(new_audio,1.4,880)<.003
    for item in (original_record,expected_record,record):assert item['duration']==pytest.approx(3,abs=1/30)
    assert record['manual_text_count']==0
    assert len(store.load(pid)['manual']['media_clips'])==1
    assert post(library_api,'undo').status_code==200
    assert content(store.load(pid))==content(before)
    assert post(library_api,'redo').status_code==200
    assert len(ProjectStore(settings).load(pid)['manual']['media_clips'])==1
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert all(p.exists() for p in (original,expected,actual))

from test_media_render import media
