import copy
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
import pytest
from test_media_append import api,library_api
from cutroom.project_copy import ProjectCopyCoordinator, ProjectCopyError, inventory

def wait(client,token):
    for _ in range(500):
        r=client.get('/api/project-copies/'+token).get_json()['operation']
        job=client.application.extensions['cutroom_jobs'].get(r.get('job_id')) if r.get('job_id') else None
        if r['status'] not in {'queued','running','publishing'} and (job is None or job.status not in {'queued','running'}):return r
        time.sleep(.01)
    raise AssertionError('copy did not finish')

def start(api,token=None):
    _,client,store,pid=api;token=token or uuid.uuid4().hex
    payload={'expected_revision':store.load(pid)['revision'],'name':'Alternative','operation_token':token}
    response=client.post(f'/api/projects/{pid}/copies',json=payload)
    assert response.status_code in (200,202),response.get_json()
    return token,payload

def test_full_private_copy_independent_and_idempotent(api):
    app,client,store,pid=api
    def seed(p):
        p['_ai_draft_proposal']={'version':2,'saved':'candidate'}
        p['caption_alternatives']={'saved':{'words':['unchanged']}}
        p['manual']['dormant_caption_overrides']={'exact':'buffer'}
    store.update(pid,seed)
    source=store.project_dir(pid);before=store.load(pid);raw=store.state_path(pid).read_bytes()
    (source/'cache'/'proof.txt').write_bytes(b'cache')
    token,payload=start(api);done=wait(client,token)
    assert done['status']=='completed',done
    target=done['copy_project_id'];new=store.load(target)
    for key in before:
        if key not in {'id','name','name_auto','revision','created_at','updated_at','exports','manual'}:assert new[key]==before[key]
    for key in before['manual']:
        if key not in {'history','_history'}:assert new['manual'][key]==before['manual'][key]
    assert new['manual']['_history']=={'undo':[],'redo':[]}
    assert new['exports']==[] and new['revision']==1
    for rel in inventory(source):
        a,b=source/rel,store.project_dir(target)/rel
        assert a.read_bytes()==b.read_bytes() and a.stat().st_ino!=b.stat().st_ino
        assert a.stat().st_mtime_ns==b.stat().st_mtime_ns
    assert store.state_path(pid).read_bytes()==raw
    assert client.post(f'/api/projects/{pid}/copies',json=payload).get_json()['operation']['copy_project_id']==target
    store.delete(target)
    assert client.post(f'/api/projects/{pid}/copies',json=payload).get_json()['operation']['copy_project_id']==target
    assert not store.project_dir(target).exists()
    assert client.post(f'/api/projects/{pid}/copies',json={**payload,'name':'Different'}).status_code==409

@pytest.mark.parametrize('reason',['space','missing','temporary','hardlink','changed'])
def test_failure_no_ghost_original_preserved(api,monkeypatch,reason):
    import cutroom.project_copy as mod
    app,client,store,pid=api;root=store.project_dir(pid)
    if reason=='space':monkeypatch.setattr(mod.shutil,'disk_usage',lambda _:type('Disk',(),{'free':0})())
    if reason=='missing':next((root/'media').glob('source-A*')).unlink()
    if reason=='temporary':(root/'cache'/'.unknown.part').write_bytes(b'pending')
    if reason=='hardlink':
        import os
        os.link(root/'media'/'source-A.mp4',root/'media'/'linked.mp4')
    if reason=='changed':
        original=mod._hash;count=[0]
        def changing(path,check=lambda:None):
            result=original(path,check)
            if 'stage-' in str(path) and path.name!='project.json' and not count[0]:
                count[0]+=1;(root/'media'/'source-A.mp4').write_bytes(b'external change')
            return result
        monkeypatch.setattr(mod,'_hash',changing)
    raw=store.state_path(pid).read_bytes();prior=set(x['id'] for x in store.list())
    token,_=start(api);done=wait(client,token)
    assert done['status']=='failed',done
    assert done['copy_project_id'] is None
    assert set(x['id'] for x in store.list())==prior
    assert store.state_path(pid).read_bytes()==raw
    assert not app.extensions['cutroom_project_copies'].lease.exists()

def test_held_copy_blocks_source_and_files_not_other_edits_cancel(api,monkeypatch):
    import cutroom.project_copy as mod
    app,client,store,pid=api;other=store.create('Other');entered=threading.Event();release=threading.Event()
    original=mod.inventory
    def held(root):
        if root==store.project_dir(pid) and not entered.is_set():entered.set();assert release.wait(5)
        return original(root)
    monkeypatch.setattr(mod,'inventory',held)
    token,_=start(api);assert entered.wait(3)
    try:
        assert client.get('/api/project-copies').get_json()['operations'][0]['operation_token']==token
        with pytest.raises(ProjectCopyError):store.patch(pid,{'name':'No'})
        with pytest.raises(ProjectCopyError):store.delete(pid)
        store.patch(other['id'],{'name':'Allowed'})
        assert client.get(f'/api/projects/{pid}').status_code==200
        assert client.post('/api/models/install',json={}).status_code==409
        assert client.post('/api/runtime/prepare',json={}).status_code==409
        asset=next(iter(store.load(pid)['assets']))
        for route in [f'/api/projects/{pid}/assets',f'/api/projects/{pid}/assets/{asset}/prepare',
                      f'/api/projects/{pid}/sources/A',f'/api/projects/{pid}/sources/A/prepare',
                      f'/api/projects/{pid}/render',f'/api/projects/{pid}/stabilize']:
            assert client.post(route,json={}).status_code==409
        assert client.get(f'/api/projects/{pid}/chroma-preview/A?time=1&revision={store.load(pid)["revision"]}').status_code==409
        assert client.get(f'/api/projects/{pid}').get_json()['project']['project_copy']['operation_token']==token
        store.patch(other['id'],{'manual':{'crop':{'A':{'x':.5,'y':.5,'zoom':1.1}}}})
        assert client.post(f'/api/projects/{pid}/uploads/preflight',json={}).status_code==409
        assert client.post('/api/project-copies/'+token+'/cancel',json={}).status_code==200
    finally:release.set()
    assert wait(client,token)['status']=='cancelled'
    store.patch(pid,{'name':'After cancellation'})

def test_bad_revision_and_unknown_cancel(api):
    _,client,store,pid=api
    assert client.post(f'/api/projects/{pid}/copies',json={'name':'X','expected_revision':1,'operation_token':uuid.uuid4().hex}).status_code==409
    assert client.post('/api/project-copies/'+uuid.uuid4().hex+'/cancel',json={}).status_code==404

def test_dead_owner_recovery_validates_published_files(api,monkeypatch):
    import cutroom.project_copy as mod
    app,client,store,pid=api;token,_=start(api);done=wait(client,token);assert done['status']=='completed',done
    c=app.extensions['cutroom_project_copies'];r=c.get(token);r['status']='publishing';c._save(r)
    c.lease.write_text(json.dumps({'pid':99999999,'operation_token':token,'source_project_id':pid}))
    monkeypatch.setattr(mod,'process_alive',lambda _:False)
    c.recover();assert c.get(token)['status']=='completed' and not c.lease.exists()
    r=c.get(token);r['status']='publishing';c._save(r)
    (store.project_dir(done['copy_project_id'])/'media'/'source-A.mp4').write_bytes(b'damaged')
    c.lease.write_text(json.dumps({'pid':99999999,'operation_token':token,'source_project_id':pid}))
    c.recover();assert c.lease.exists() and c.get(token)['status']=='publishing'

def test_preparation_marker_is_runtime_only(api):
    app,client,store,pid=api
    asset=next(iter(store.load(pid)['assets']))
    marker=store.project_dir(pid)/'media'/'assets'/asset/'.preparation.lock'
    marker.write_bytes(b'')
    token,_=start(api);done=wait(client,token)
    assert done['status']=='completed',done
    assert not (store.project_dir(done['copy_project_id'])/marker.relative_to(store.project_dir(pid))).exists()
    assert marker.exists()

def test_queued_cancel_and_lost_response_retry(api,monkeypatch):
    from cutroom.jobs import Job
    app,client,store,pid=api;jobs=app.extensions['cutroom_jobs'];captured=[]
    def queued(kind,project,fn,*args,**kwargs):
        job=Job('job_'+uuid.uuid4().hex,kind,project,dedupe_key=kwargs['dedupe_key']);captured.append(job)
        return job
    monkeypatch.setattr(jobs,'submit',queued)
    monkeypatch.setattr(jobs,'get',lambda identity:captured[0])
    def cancel(identity):captured[0].status='cancelled';return True
    monkeypatch.setattr(jobs,'cancel',cancel)
    token,payload=start(api)
    assert client.post(f'/api/projects/{pid}/copies',json=payload).get_json()['operation']['job_id']==captured[0].id
    assert len(captured)==1
    response=client.post('/api/project-copies/'+token+'/cancel',json={})
    assert response.get_json()['operation']['status']=='cancelled'
    assert not app.extensions['cutroom_project_copies'].lease.exists()
    assert client.post(f'/api/projects/{pid}/copies',json=payload).get_json()['operation']['status']=='cancelled'
    assert len(captured)==1

@pytest.mark.parametrize('window',['receipt_only','partial_lease','valid_lease'])
def test_interrupted_admission_recovery(api,monkeypatch,window):
    import cutroom.project_copy as mod
    app,_,store,pid=api;c=app.extensions['cutroom_project_copies'];token=uuid.uuid4().hex
    r=dict(operation_token=token,source_project_id=pid,source_revision=store.load(pid)['revision'],name='Interrupted',destination_id='project_'+uuid.uuid4().hex[:12],status='queued',owner_pid=99999999,cancel_requested=False)
    c._save(r)
    if window=='partial_lease':c.lease.write_text('{')
    if window=='valid_lease':c.lease.write_text(json.dumps({'pid':99999999,'operation_token':token,'source_project_id':pid}))
    monkeypatch.setattr(mod,'process_alive',lambda _:False)
    c.recover()
    assert c.get(token)['status']=='interrupted' and not c.lease.exists()


def test_admission_pin_detects_change_before_worker(api,monkeypatch):
    app,client,store,pid=api;c=app.extensions['cutroom_project_copies'];entered=threading.Event();release=threading.Event();old=c._run
    def delayed(*args):entered.set();assert release.wait(5);return old(*args)
    monkeypatch.setattr(c,'_run',delayed)
    token,_=start(api);assert entered.wait(3)
    raw=json.loads(store.state_path(pid).read_text());raw['name']='External same revision edit'
    store.state_path(pid).write_text(json.dumps(raw))
    release.set();done=wait(client,token)
    assert done['status']=='failed' and 'before copying' in done['error']


def test_early_transport_and_running_writer_exclusion(api):
    app,client,store,pid=api;c=app.extensions['cutroom_project_copies'];storage=app.extensions['cutroom_upload_storage']
    c.begin_writer()
    try:
        assert client.post(f'/api/projects/{pid}/copies',json={'name':'X','expected_revision':store.load(pid)['revision'],'operation_token':uuid.uuid4().hex}).status_code==409
    finally:c.end_writer()
    c.lease.write_text(json.dumps({'pid':123,'source_project_id':pid,'operation_token':uuid.uuid4().hex}))
    from cutroom.upload_storage import UploadStorageError
    with pytest.raises(UploadStorageError):storage.admit_legacy(10,data_path=store.project_dir(pid)/'media')
    with pytest.raises(UploadStorageError):storage.begin_transport(pid,uuid.uuid4().hex,0,10)
    c.lease.unlink()


def test_second_discoverable_server_refused(api,monkeypatch):
    import cutroom.project_copy as mod
    app,client,store,pid=api;c=app.extensions['cutroom_project_copies'];(c.owners/'99999999.json').write_text(json.dumps({'pid':99999999}))
    monkeypatch.setattr(mod,'process_alive',lambda _:True)
    assert client.post(f'/api/projects/{pid}/copies',json={'name':'X','expected_revision':store.load(pid)['revision'],'operation_token':uuid.uuid4().hex}).status_code==409

@pytest.mark.parametrize('point',['mid_write','rename','first_receipt','lease','final_receipt'])
def test_fault_boundaries(api,monkeypatch,point):
    import errno
    import cutroom.project_copy as mod
    app,client,store,pid=api;c=app.extensions['cutroom_project_copies'];raw=store.state_path(pid).read_bytes();prior={p['id'] for p in store.list()}
    original_open=Path.open;original_rename=Path.rename;original_save=c._save;triggered=[False]
    class BrokenWriter:
        def __init__(self,f):self.f=f
        def __enter__(self):return self
        def __exit__(self,*args):self.f.close()
        def write(self,block):
            self.f.write(block[:2]);triggered[0]=True
            raise OSError(errno.ENOSPC,'Injected disk exhaustion')
        def __getattr__(self,name):return getattr(self.f,name)
    def opened(path,*args,**kwargs):
        mode=args[0] if args else kwargs.get('mode','r')
        if point=='lease' and path==c.lease and mode=='x':raise OSError(errno.ENOSPC,'Injected lease exhaustion')
        handle=original_open(path,*args,**kwargs)
        if point=='mid_write' and 'stage-' in str(path) and mode=='xb' and not triggered[0]:return BrokenWriter(handle)
        return handle
    def renamed(path,destination):
        if point=='rename' and path.name.startswith('stage-'):raise OSError(errno.EACCES,'Injected publication refusal')
        return original_rename(path,destination)
    def saved(r):
        if point=='first_receipt' and not c._path(r['operation_token']).exists():raise OSError(errno.ENOSPC,'Injected first receipt exhaustion')
        if point=='final_receipt' and r['status']=='completed':raise OSError(errno.ENOSPC,'Injected final receipt exhaustion')
        return original_save(r)
    monkeypatch.setattr(Path,'open',opened);monkeypatch.setattr(Path,'rename',renamed);monkeypatch.setattr(c,'_save',saved)
    token=uuid.uuid4().hex;payload={'name':'Fault copy','expected_revision':store.load(pid)['revision'],'operation_token':token}
    if point=='first_receipt':
        assert client.post(f'/api/projects/{pid}/copies',json=payload).status_code in (500,507)
        assert not c.lease.exists()
    elif point=='lease':
        assert client.post(f'/api/projects/{pid}/copies',json=payload).status_code==409
        assert c.get(token)['status']=='failed' and not c.lease.exists()
    else:
        assert client.post(f'/api/projects/{pid}/copies',json=payload).status_code==202
        if point=='final_receipt':
            for _ in range(500):
                if c.get(token)['status']=='publishing' and store.project_dir(c.get(token)['destination_id']).exists():break
                time.sleep(.01)
            assert c.lease.exists()
            with c.gate:
                destination_id=c.get(token)['destination_id']
                assert destination_id not in {p['id'] for p in store.list()}
                visible=client.get(f'/api/projects/{destination_id}').get_json()
                assert visible['project']['project_copy']['operation_token']==token
                assert visible['project']['project_copy']['status']=='publishing'
                assert client.patch(f'/api/projects/{destination_id}',json={'name':'Too early'}).status_code==409
                monkeypatch.setattr(c,'_save',original_save)
            assert wait(client,token)['status']=='completed' and not c.lease.exists()
            assert len({p['id'] for p in store.list()}-prior)==1
        else:assert wait(client,token)['status']=='failed'
    assert store.state_path(pid).read_bytes()==raw
    if point!='final_receipt':assert {p['id'] for p in store.list()}==prior


def test_terminal_cleanup_receipt_retries_only_owned_stage(api,monkeypatch):
    app,_,store,pid=api;c=app.extensions['cutroom_project_copies'];token=uuid.uuid4().hex
    stage=c.root/('stage-'+token);stage.mkdir();(stage/'partial').write_bytes(b'partial')
    r=dict(operation_token=token,source_project_id=pid,source_revision=store.load(pid)['revision'],name='Cancelled',destination_id='project_'+uuid.uuid4().hex[:12],status='cancelled',owner_pid=99999999,cancel_requested=True,cleanup_pending=True)
    c._save(r);original=c._cleanup
    def locked(record):raise PermissionError('Temporarily held file')
    monkeypatch.setattr(c,'_cleanup',locked);c.recover()
    assert stage.exists() and c.get(token)['cleanup_pending']
    monkeypatch.setattr(c,'_cleanup',original);c.recover()
    assert not stage.exists() and not c.get(token).get('cleanup_pending')


def test_empty_project_copy_has_fresh_history(api):
    app,client,store,_=api;p=store.create('Empty')
    token,_=start((app,client,store,p['id']));done=wait(client,token)
    assert done['status']=='completed',done
    result=store.load(done['copy_project_id'])
    assert result['draft'] is None and result['sources']=={'A':None,'B':None}
    assert result['assets']=={} and result['exports']==[]

@pytest.mark.parametrize('bad',['missing_path','preparing','empty_stage'])
def test_required_dependency_not_silently_omitted(api,bad):
    app,client,store,pid=api
    def modify(p):
        if bad=='missing_path':p['sources']['A'].pop('relative_path')
        if bad=='preparing':p['sources']['A']['preparation']='preparing'
    store.update(pid,lambda p:p['manual'].update(track_locks={'A':False,'B':False}))
    store.update(pid,modify)
    if bad=='empty_stage':(store.project_dir(pid)/'cache'/'.preparing-stale').mkdir()
    token,_=start(api);done=wait(client,token)
    assert done['status']=='failed' and done['copy_project_id'] is None


@pytest.mark.parametrize('failure',[False,True])
def test_terminal_job_before_copy_callback_reconciles(api,monkeypatch,failure):
    from cutroom.jobs import JobContext
    app,client,store,pid=api;c=app.extensions['cutroom_project_copies']
    entered=threading.Event();release=threading.Event();called=[]
    original=JobContext.check_cancelled;worker=c._run
    def checkpoint(context):
        if context.job.kind=='project_copy' and not entered.is_set():
            assert context.job.status=='running'
            entered.set();assert release.wait(5)
            if failure:raise RuntimeError('Injected failure before callback')
        return original(context)
    def run(*args):called.append(True);return worker(*args)
    monkeypatch.setattr(JobContext,'check_cancelled',checkpoint);monkeypatch.setattr(c,'_run',run)
    before=store.state_path(pid).read_bytes();prior={p['id'] for p in store.list()}
    token,payload=start(api)
    try:
        assert entered.wait(5)
        assert c.get(token)['status']=='queued' and c.lease.exists()
        if not failure:assert client.post('/api/project-copies/'+token+'/cancel',json={}).status_code==200
    finally:release.set()
    done=wait(client,token)
    assert done['status']==('failed' if failure else 'cancelled')
    assert not called and not c.lease.exists()
    assert not (c.root/('stage-'+token)).exists()
    assert store.state_path(pid).read_bytes()==before and {p['id'] for p in store.list()}==prior
    assert client.get('/api/project-copies').get_json()['operations']==[]
    assert client.get(f'/api/projects/{pid}').get_json()['project']['project_copy'] is None
    assert client.post(f'/api/projects/{pid}/copies',json=payload).get_json()['operation']['status']==done['status']
    assert client.patch(f'/api/projects/{pid}',json={'name':'Editable again'}).status_code==200


@pytest.mark.parametrize('status',['queued','running','publishing'])
def test_terminal_recovery_refuses_foreign_job_token(api,monkeypatch,status):
    import os
    from types import SimpleNamespace
    app,_,store,pid=api;c=app.extensions['cutroom_project_copies'];token=uuid.uuid4().hex
    destination='project_'+uuid.uuid4().hex[:12]
    r=dict(operation_token=token,source_project_id=pid,source_revision=store.load(pid)['revision'],name='Protected',destination_id=destination,status=status,owner_pid=os.getpid(),job_id='foreign',cancel_requested=False)
    c._save(r)
    c.lease.write_text(json.dumps(dict(pid=os.getpid(),source_project_id=pid,destination_id=destination,operation_token=token)))
    stage=c.root/('stage-'+token);stage.mkdir();(stage/'partial').write_bytes(b'protected')
    monkeypatch.setattr(c.jobs,'get',lambda _:SimpleNamespace(status='cancelled',kind='project_copy',project_id=pid,dedupe_key='different-token'))
    with pytest.raises(ProjectCopyError,match='ownership'):c.poll(token)
    assert c.lease.exists() and (stage/'partial').read_bytes()==b'protected'
    assert c.get(token)['status']==status
