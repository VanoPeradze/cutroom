import copy, os, json, shutil
from dataclasses import replace
from pathlib import Path
import pytest
from test_asset_preparation_cache import setup, context, ASSET, prepare, asset
from cutroom.preview_repair import FIELD,repair_asset,validate_proof
from cutroom.asset_preparation import PreparationCacheError
from cutroom import media_library as media

@pytest.fixture
def ready(setup,monkeypatch):
    original=media.probe_asset
    def probe(path,kind,settings,**kw):
        if Path(path).name=='original.wav':return {'kind':'audio','duration':2.0,'width':0,'height':0,'has_audio':True}
        return original(path,kind,settings,**kw)
    monkeypatch.setattr(media,'probe_asset',probe)
    prepare(setup);return setup

def repair(s,ctx=None,binding=None):
    return repair_asset(ctx or context(),s[2],ASSET,s[1],s[0],binding or copy.deepcopy(asset(s)))

def test_stamp_and_noop(ready):
    s=ready;before=s[1].project_path(s[2]).read_bytes() if hasattr(s[1],'project_path') else (s[1].project_dir(s[2])/'project.json').read_bytes()
    validate_proof(asset(s)[FIELD]);repair(s)
    assert (s[1].project_dir(s[2])/'project.json').read_bytes()==before

@pytest.mark.parametrize('damage',['missing','corrupt'])
def test_repair(ready,damage):
    s=ready;p=s[1].project_dir(s[2])/asset(s)['preview_path'];before=s[1].load(s[2]);original=s[4].read_bytes()
    if damage=='missing':p.unlink()
    else:p.write_bytes(b'bad')
    repair(s);after=s[1].load(s[2]);assert after['manual']==before['manual'];assert s[4].read_bytes()==original
    assert (s[1].project_dir(s[2])/asset(s)['preview_path']).read_bytes().startswith(b'SYNTHETIC-PREPARED')

def test_proof_pipeline_change(ready):
    s=ready;s[0]=replace(s[0],ffmpeg='other-version');repair(s);assert asset(s)[FIELD]['sha256']

def test_legacy_bootstrap(ready):
    s=ready;s[1].update(s[2],lambda p:(p['assets'][ASSET].pop(FIELD),None)[1]);repair(s);assert FIELD in asset(s)

def test_legacy_pipeline_refusal(ready):
    s=ready;s[1].update(s[2],lambda p:(p['assets'][ASSET].pop(FIELD),None)[1]);before=s[1].load(s[2]);s[0]=replace(s[0],ffmpeg='other-version')
    with pytest.raises(Exception,match='unverifiable'):repair(s)
    assert s[1].load(s[2])==before

def test_changed_original_refusal(ready):
    s=ready;s[4].write_bytes(b'CHANGED---ORIGINAL');before=s[1].load(s[2])
    with pytest.raises(Exception,match='original_changed'):repair(s)
    assert s[1].load(s[2])==before

@pytest.mark.parametrize('mutation',[lambda p:p.update(version=2),lambda p:p.update(size=True),lambda p:p.update(sha256='oops'),lambda p:p.update(extra=1),lambda p:p['metadata'].update(duration=float('nan'))])
def test_malformed_proof(ready,mutation):
    s=ready;s[1].update(s[2],lambda p:mutation(p['assets'][ASSET][FIELD]));before=s[1].load(s[2])
    with pytest.raises(Exception):repair(s)
    assert s[1].load(s[2])==before

def test_cancel_preserves_binding(ready):
    s=ready;(s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();before=s[1].load(s[2]);ctx=context()
    s[-1]['hook']=lambda p:ctx.job.cancel_event.set()
    with pytest.raises(Exception):repair(s,ctx)
    assert s[1].load(s[2])==before

def test_disk_failure(ready):
    s=ready;(s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();before=s[1].load(s[2])
    def fail(p):raise OSError(28,'No space')
    s[-1]['hook']=fail
    with pytest.raises(Exception):repair(s)
    assert s[1].load(s[2])==before

def test_stale_binding(ready):
    s=ready;binding=copy.deepcopy(asset(s));binding['preview_path']='old'
    with pytest.raises(Exception,match='repair_stale'):repair(s,binding=binding)

def test_source_changes_midbuild(ready):
    s=ready;(s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();before=s[1].load(s[2]);s[-1]['hook']=lambda p:s[4].write_bytes(b'CHANGED---ORIGINAL')
    with pytest.raises(Exception,match='preview_repair_failed'):repair(s)
    assert s[1].load(s[2])==before


def test_copied_content_proof_and_legacy_limit(ready):
    s=ready;src=s[4];tmp=src.with_name('copy.wav');shutil.copy2(src,tmp);os.replace(tmp,src)
    repair(s)
    s[1].update(s[2],lambda p:(p['assets'][ASSET].pop(FIELD),None)[1])
    shutil.copy2(src,tmp);os.replace(tmp,src)
    with pytest.raises(Exception,match='unverifiable'):repair(s)

def test_metadata_mismatch(ready):
    s=ready;s[1].update(s[2],lambda p:p['assets'][ASSET].update(duration=3))
    with pytest.raises(Exception,match='original_unverifiable'):repair(s)

def test_unsafe_original_path(ready):
    s=ready;s[1].update(s[2],lambda p:p['assets'][ASSET].update(path='media/assets/../escape.wav'))
    with pytest.raises(Exception,match='original_unsafe|unsafe asset path'):repair(s)

def test_stabilized_preview_does_not_regenerate(ready,monkeypatch):
    from cutroom import stabilization_assets
    s=ready;s[1].update(s[2],lambda p:p['assets'][ASSET].update(_stabilization={'sentinel':True},stabilized=True))
    monkeypatch.setattr(stabilization_assets,'prepare_stabilized_asset',lambda *a:pytest.fail('must not stabilize'))
    (s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();repair(s);assert asset(s)['_stabilization']=={'sentinel':True}

def test_locked_identity_exempts_only_proof():
    from cutroom.layer_tracks import _locked_asset_identity
    a={'id':ASSET,'path':'owned','kind':'audio'}
    assert _locked_asset_identity(a)==_locked_asset_identity({**a,FIELD:{'version':1}})
    assert _locked_asset_identity(a)!=_locked_asset_identity({**a,'path':'other'})

from test_media_library import api
from cutroom.jobs import Job

def test_api_stale_busy_and_terminal_tokens(api,monkeypatch):
    app,client,store,pid=api;jobs=app.extensions['cutroom_jobs'];from test_media_library import ASSET as A
    token='e'*32;url=f'/api/projects/{pid}/assets/{A}/repair-preview';body={'expected_revision':store.load(pid)['revision'],'operation_token':token}
    assert client.post(url,json={**body,'expected_revision':-1}).status_code==409
    held=Job('held','prepare_asset',pid)
    monkeypatch.setattr(jobs,'active',lambda **kw:[held]);assert client.post(url,json=body).status_code==409
    monkeypatch.setattr(jobs,'active',lambda **kw:[])
    terminal=Job('known','prepare_asset',pid,dedupe_key=f"repair:{A}:{body['expected_revision']}:{token}");terminal.status='completed'
    monkeypatch.setattr(jobs,'list',lambda **kw:[terminal])
    response=client.post(url,json=body);assert response.status_code==200;assert response.json['job']['id']=='known'
    assert client.post(url,json={**body,'expected_revision':body['expected_revision']+1}).status_code==409
    monkeypatch.undo()


def test_real_audio_cache_corruption_repair(tmp_path,monkeypatch):
    import wave,math,struct,hashlib,subprocess
    from cutroom.config import load_settings
    from cutroom.projects import ProjectStore
    monkeypatch.setenv('CUTROOM_DATA_DIR',str(tmp_path/'real'))
    settings=load_settings();store=ProjectStore(settings);pid=store.create('real synthetic')['id']
    folder=store.project_dir(pid)/'media/assets'/ASSET;folder.mkdir(parents=True);source=folder/'original.wav'
    with wave.open(str(source),'wb') as wav:
        wav.setparams((1,2,48000,48000,'NONE','not compressed'));wav.writeframes(b''.join(struct.pack('<h',int(8000*math.sin(i*2*math.pi*440/48000))) for i in range(48000)))
    a={'id':ASSET,'name':'tone','path':source.relative_to(store.project_dir(pid)).as_posix(),'status':'preparing',**media.probe_asset(source,'audio',settings)}
    store.update(pid,lambda p:p['assets'].update({ASSET:a}));media.prepare_asset(context(),pid,ASSET,store,settings)
    before=store.load(pid);original=hashlib.sha256(source.read_bytes()).hexdigest();preview=store.project_dir(pid)/before['assets'][ASSET]['preview_path']
    def pcm(path):return subprocess.run([settings.ffmpeg,'-v','error','-i',str(path),'-f','s16le','-acodec','pcm_s16le','-'],capture_output=True,check=True).stdout
    expected=pcm(preview);preview.write_bytes(b'CORRUPTED PREVIEW')
    repair_asset(context(),pid,ASSET,store,settings,copy.deepcopy(before['assets'][ASSET]));after=store.load(pid)
    assert pcm(store.project_dir(pid)/after['assets'][ASSET]['preview_path'])==expected
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original
    assert after['manual']==before['manual'];assert after['assets'][ASSET][FIELD]==before['assets'][ASSET][FIELD]


def test_api_copy_and_import_exclusion(api,monkeypatch):
    app,client,store,pid=api;from test_media_library import ASSET as A
    from cutroom.project_copy import ProjectCopyError
    copies=app.extensions['cutroom_project_copies'];body={'expected_revision':store.load(pid)['revision'],'operation_token':'a'*32};url=f'/api/projects/{pid}/assets/{A}/repair-preview'
    def blocked():raise ProjectCopyError('Finish or cancel copy first')
    monkeypatch.setattr(copies,'require_idle',blocked)
    assert client.post(url,json=body).status_code==409
    monkeypatch.undo()
    uploads=app.extensions['cutroom_upload_storage'];monkeypatch.setattr(uploads,'active_for_project',lambda *a,**kw:True)
    assert client.post(url,json=body).status_code==409
    monkeypatch.undo()

def test_cancel_before_worker_keeps_ready(ready):
    from cutroom.jobs import JobManager
    import threading,time
    s=ready;before=s[1].load(s[2]);jobs=JobManager(workers=1,heavy_workers=1);entered=threading.Event();release=threading.Event()
    def hold(ctx):entered.set();release.wait(5)
    first=jobs.submit('prepare_asset','other',hold,dedupe_key='hold');assert entered.wait(2)
    job=jobs.submit('prepare_asset',s[2],repair_asset,s[2],ASSET,s[1],s[0],copy.deepcopy(asset(s)),dedupe_key='repair:test')
    jobs.cancel(job.id);release.set();jobs.shutdown(wait=True)
    assert job.status=='cancelled';assert s[1].load(s[2])==before


def test_actual_locked_store_repair(ready):
    from cutroom.editing import apply_manual_edit
    s=ready
    def setup_project(p):
        p['sources']['A']={'duration':2};p['draft']={'keep_ranges':[{'start':0,'end':2}],'cuts':[],'output_duration':2,'camera_plan':[{'start':0,'end':2,'camera':'A'}]}
        apply_manual_edit(p,{'action':'media_add','asset_id':ASSET,'start':0,'end':2})
        apply_manual_edit(p,{'action':'layer_tracks_enable'})
        tid=p['manual']['media_clips'][0]['track_id'];apply_manual_edit(p,{'action':'layer_track_lock','track_id':tid,'locked':True})
    s[1].update(s[2],setup_project);before=s[1].load(s[2]);(s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();repair(s)
    assert s[1].load(s[2])['manual']==before['manual']

def wait_job(jobs,identity):
    import time
    for _ in range(400):
        j=jobs.get(identity)
        if j.status not in {'queued','running'}:return j
        time.sleep(.01)
    pytest.fail('job timeout')

def test_real_async_endpoint_and_restart_and_new_token(ready):
    from server import create_app
    from cutroom.jobs import JobManager
    s=ready;s[0].raw['ai']['enabled']=False;app=create_app(s[0]);app.config['TESTING']=True;client=app.test_client();jobs=app.extensions['cutroom_jobs'];url=f'/api/projects/{s[2]}/assets/{ASSET}/repair-preview'
    body={'expected_revision':s[1].load(s[2])['revision'],'operation_token':'1'*32};before=s[1].state_path(s[2]).read_bytes()
    try:
        r=client.post(url,json=body);assert r.status_code==202,r.json
        first=wait_job(jobs,r.json['job']['id']);assert first.status=='completed',first.error
        assert s[1].state_path(s[2]).read_bytes()==before
        assert client.post(url,json=body).json['job']['id']==first.id
        (s[1].project_dir(s[2])/asset(s)['preview_path']).write_bytes(b'new damage')
        second=client.post(url,json={**body,'operation_token':'2'*32});assert second.status_code==202,second.json
        job=wait_job(jobs,second.json['job']['id']);assert job.status=='completed',job.error;assert job.id!=first.id
        assert client.get('/api/jobs/job_unknown_repair').status_code==404
        assert len(jobs.list(project_id=s[2],kind='prepare_asset'))==2
        persistence=jobs.persistence_path
    finally:jobs.shutdown(wait=True,cancel_pending=True)
    restarted=JobManager(persistence_path=persistence)
    try:
        assert restarted.get(first.id).status=='completed'
        app2=create_app(s[0]);app2.config['TESTING']=True
        try:
            recovered=app2.test_client().post(url,json=body);assert recovered.status_code==200,recovered.json;assert recovered.json['job']['id']==first.id
        finally:app2.extensions['cutroom_jobs'].shutdown(wait=True,cancel_pending=True)
    finally:restarted.shutdown(wait=True)

@pytest.mark.parametrize('field,value',[('duration',True),('width',float('inf')),('has_audio',1)])
def test_generated_proof_is_strict(field,value):
    from cutroom.preview_repair import make_proof
    a={'path':'x','kind':'audio','duration':2,'width':0,'height':0,'has_audio':True};a[field]=value
    with pytest.raises(Exception):make_proof(a,{'file':{'size':1,'sha256':'a'*64}})


def test_async_endpoint_cancel_before_callback_replays_terminal_only(ready,monkeypatch):
    from server import create_app
    from cutroom.jobs import JobContext
    import threading
    s=ready;s[0].raw['ai']['enabled']=False;app=create_app(s[0]);app.config['TESTING']=True;client=app.test_client();jobs=app.extensions['cutroom_jobs'];entered=threading.Event();release=threading.Event();original=JobContext.check_cancelled
    def hold(ctx):
        if ctx.job.kind=='prepare_asset' and not entered.is_set():entered.set();release.wait(4)
        return original(ctx)
    monkeypatch.setattr(JobContext,'check_cancelled',hold)
    before=s[1].state_path(s[2]).read_bytes();url=f'/api/projects/{s[2]}/assets/{ASSET}/repair-preview';body={'expected_revision':s[1].load(s[2])['revision'],'operation_token':'3'*32}
    try:
        r=client.post(url,json=body);assert r.status_code==202;identity=r.json['job']['id'];assert entered.wait(2)
        assert client.post(f'/api/jobs/{identity}/cancel',json={}).status_code==202
        release.set();assert wait_job(jobs,identity).status=='cancelled'
        repeated=client.post(url,json=body);assert repeated.status_code==200;assert repeated.json['job']['id']==identity
        assert s[1].state_path(s[2]).read_bytes()==before;assert len(jobs.list(project_id=s[2],kind='prepare_asset'))==1
    finally:release.set();jobs.shutdown(wait=True,cancel_pending=True)

def test_missing_original_safe_reason(ready):
    s=ready;s[4].unlink()
    with pytest.raises(Exception,match='original_missing') as error:repair(s)
    assert str(s[4]) not in str(error.value)

@pytest.mark.parametrize('kind,patch',[('audio',{'width':1}),('audio',{'has_audio':False}),('image',{'duration':1}),('image',{'has_audio':True}),('video',{'width':0}),('video',{'width':1.5}),('video',{'duration':14401})])
def test_kind_specific_proof(kind,patch):
    from cutroom.preview_repair import validate_proof
    value={'version':1,'path':'owned','kind':kind,'size':2,'sha256':'a'*64,'metadata':{'width':0 if kind=='audio' else 640,'height':0 if kind=='audio' else 360,'duration':0 if kind=='image' else 2,'has_audio':kind!='image'}};value['metadata'].update(patch)
    with pytest.raises(Exception,match='original_proof_invalid'):validate_proof(value)

def test_hardlink_original_refused(ready):
    s=ready;os.link(s[4],s[4].with_name('shared.wav'))
    with pytest.raises(Exception,match='original_unsafe'):repair(s)

def test_missing_cache_output_not_original(ready):
    s=ready;(s[1].project_dir(s[2])/asset(s)['preview_path']).unlink()
    def fail(path):raise FileNotFoundError('temporary encoder artifact vanished')
    s[-1]['hook']=fail
    with pytest.raises(Exception,match='preview_repair_failed') as exc:repair(s)
    assert 'original_missing' not in str(exc.value)


def test_api_queued_repair_cancel_does_not_mutate_project(ready):
    from server import create_app
    import threading,time
    s=ready;s[0].raw['ai']['enabled']=False;app=create_app(s[0]);app.config['TESTING']=True;client=app.test_client();jobs=app.extensions['cutroom_jobs'];release=threading.Event()
    # Occupy every background executor slot directly, without creating a conflicting project job.
    tasks=[jobs.background_executor.submit(release.wait,5) for _ in range(jobs.background_executor._max_workers)]
    before=s[1].state_path(s[2]).read_bytes();body={'expected_revision':s[1].load(s[2])['revision'],'operation_token':'4'*32}
    try:
        r=client.post(f'/api/projects/{s[2]}/assets/{ASSET}/repair-preview',json=body);assert r.status_code==202,r.json;identity=r.json['job']['id'];assert jobs.get(identity).status=='queued'
        response=client.post(f'/api/jobs/{identity}/cancel',json={});assert response.status_code==200,response.json
        assert jobs.get(identity).status=='cancelled';assert s[1].state_path(s[2]).read_bytes()==before
    finally:release.set();jobs.shutdown(wait=True,cancel_pending=True)


def test_preview_version_and_public_cache_urls(ready):
    from cutroom.preview_repair import preview_version
    from server import _public_project
    s=ready;before=asset(s);version=preview_version(before);assert version and len(version)==24
    s[1].update(s[2],lambda p:(p['assets'][ASSET].pop(FIELD),None)[1]);result=repair(s)
    assert result['before_preview_version']==result['after_preview_version']==version
    (s[1].project_dir(s[2])/asset(s)['preview_path']).unlink();result=repair(s)
    assert result['before_preview_version']==version and result['after_preview_version']!=version
    public=_public_project(s[1].load(s[2]))['assets'][ASSET]
    assert public['preview_version']==result['after_preview_version'];assert public['url'].endswith('?v='+public['preview_version'])
    assert FIELD not in public and 'path' not in public and 'preparation_identity' not in public


def test_copy_and_repair_admission_exclude_each_other(ready,monkeypatch):
    from server import create_app
    import threading,uuid
    s=ready;s[0].raw['ai']['enabled']=False;app=create_app(s[0]);app.config['TESTING']=True;client=app.test_client();jobs=app.extensions['cutroom_jobs'];copies=app.extensions['cutroom_project_copies'];release=threading.Event();entered=threading.Event()
    repair_url=f'/api/projects/{s[2]}/assets/{ASSET}/repair-preview';copy_url=f'/api/projects/{s[2]}/copies'
    try:
        (s[1].project_dir(s[2])/asset(s)['preview_path']).unlink()
        def hold(path):entered.set();release.wait(5)
        s[-1]['hook']=hold
        revision=s[1].load(s[2])['revision'];response=client.post(repair_url,json={'expected_revision':revision,'operation_token':'5'*32});assert response.status_code==202;assert entered.wait(2)
        refused=client.post(copy_url,json={'expected_revision':revision,'name':'Copy race','operation_token':str(uuid.uuid4())});assert refused.status_code==409,refused.json
        release.set();assert wait_job(jobs,response.json['job']['id']).status=='completed';s[-1]['hook']=None
        release.clear();entered.clear();original=copies._run
        def hold_copy(*args,**kwargs):entered.set();release.wait(5);return original(*args,**kwargs)
        monkeypatch.setattr(copies,'_run',hold_copy)
        revision=s[1].load(s[2])['revision'];response=client.post(copy_url,json={'expected_revision':revision,'name':'Copy race','operation_token':str(uuid.uuid4())});assert response.status_code==202,response.json;assert entered.wait(2)
        refused=client.post(repair_url,json={'expected_revision':revision,'operation_token':'6'*32});assert refused.status_code==409,refused.json
    finally:release.set();jobs.shutdown(wait=True,cancel_pending=True)


def test_proof_backed_absent_preview_path_repairs_with_version(ready):
    from cutroom.preview_repair import preview_version
    from server import _public_project
    s=ready;s[1].update(s[2],lambda p:(p['assets'][ASSET].pop('preview_path'),None)[1]);before=preview_version(asset(s));assert len(before)==24
    assert _public_project(s[1].load(s[2]))['assets'][ASSET]['preview_version']==before
    result=repair(s);assert result['before_preview_version']==before and result['after_preview_version']!=before

def test_unstamped_no_key_exposes_version_but_refuses(ready):
    from cutroom.preview_repair import preview_version
    s=ready
    def remove(p):
        for key in (FIELD,'preview_path','preparation_identity'):p['assets'][ASSET].pop(key,None)
    s[1].update(s[2],remove);assert len(preview_version(asset(s)))==24
    with pytest.raises(Exception,match='original_unverifiable'):repair(s)


@pytest.mark.parametrize("binding", ["legacy_unknown", "proved"])
def test_metadata_probe_mismatch_is_unverifiable(ready, monkeypatch, binding):
    s = ready
    if binding == "legacy_unknown":
        def unstamp(project):
            project["assets"][ASSET].pop(FIELD)
            project["assets"][ASSET].pop("preparation_identity")
        s[1].update(s[2], unstamp)
    before = (s[1].project_dir(s[2]) / "project.json").read_bytes()
    monkeypatch.setattr(media, "probe_asset", lambda *a, **k: {
        "kind": "audio", "duration": 3.0, "width": 0, "height": 0, "has_audio": True})
    with pytest.raises(Exception, match="original_unverifiable"):
        repair(s)
    assert (s[1].project_dir(s[2]) / "project.json").read_bytes() == before


@pytest.mark.parametrize("field,value", [("path", "other.wav"), ("metadata", {"duration": 3.0, "width": 0, "height": 0, "has_audio": True})])
def test_same_content_different_proof_binding_is_unverifiable(ready, field, value):
    s = ready
    s[1].update(s[2], lambda project: project["assets"][ASSET][FIELD].update({field: value}))
    before = (s[1].project_dir(s[2]) / "project.json").read_bytes()
    with pytest.raises(Exception, match="original_unverifiable"):
        repair(s)
    assert (s[1].project_dir(s[2]) / "project.json").read_bytes() == before


def test_known_changed_content_precedes_changed_measured_metadata(ready, monkeypatch):
    s = ready
    s[4].write_bytes(b"Changed original bytes and metadata")
    before = (s[1].project_dir(s[2]) / "project.json").read_bytes()
    probes = []
    def changed_probe(*args, **kwargs):
        probes.append(True)
        return {"kind": "audio", "duration": 3.0, "width": 0, "height": 0, "has_audio": True}
    monkeypatch.setattr(media, "probe_asset", changed_probe)
    with pytest.raises(Exception, match="original_changed"):
        repair(s)
    assert probes == []
    assert (s[1].project_dir(s[2]) / "project.json").read_bytes() == before
