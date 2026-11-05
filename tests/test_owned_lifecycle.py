"""No model/media loads: ownership mocks and bounded threaded job fixtures."""
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from cutroom import owned_process, transcription, transcription_worker
from cutroom.config import load_settings
from cutroom.jobs import JobManager, JobCancelled


def wait(predicate, seconds=2.):
    deadline=time.monotonic()+seconds
    while not predicate():
        if time.monotonic()>deadline:pytest.fail('Lifecycle condition timed out')
        time.sleep(.01)


def test_common_heavy_limit_keeps_waiting_job_queued_and_cancel_does_not_stop_owner():
    manager=JobManager(workers=2,background_workers=2,heavy_workers=1)
    entered=threading.Event();release=threading.Event();calls=[]
    def first(ctx):entered.set();release.wait(2);calls.append('first');return 'first'
    try:
        owner=manager.submit('prepare_source','p1',first);assert entered.wait(1)
        queued=manager.submit('director','p2',lambda c:calls.append('second'))
        wait(lambda:'Waiting for another' in queued.message)
        assert queued.status=='queued' and owner.status=='running'
        assert manager.submit('director','p2',lambda c:pytest.fail('duplicate')) is queued
        assert manager.cancel(queued.id)
        wait(lambda:queued.status=='cancelled')
        assert owner.status=='running' and calls==[]
        release.set();wait(lambda:owner.status=='completed')
        next_job=manager.submit('render','p3',lambda c:'third')
        wait(lambda:next_job.status=='completed');assert next_job.result=='third'
    finally:release.set();manager.shutdown(cancel_pending=True)


def test_shared_slot_released_after_failure_and_committed_cancel_remains_completed():
    manager=JobManager(heavy_workers=1)
    def broken(c):raise RuntimeError('synthetic failure')
    try:
        one=manager.submit('render','p',broken);wait(lambda:one.status=='failed')
        def committed(c):c.commit();c.job.cancel_event.set();return 'saved'
        two=manager.submit('director','other',committed);wait(lambda:two.status=='completed')
        assert two.result=='saved' and not two.public()['cancel_requested']
    finally:manager.shutdown(cancel_pending=True)


def test_worker_attaches_before_gate_and_closes_tree_before_ipc_cleanup(tmp_path,monkeypatch):
    monkeypatch.setenv('CUTROOM_DATA_DIR',str(tmp_path/'data'));settings=load_settings();seen=[];paths=[]
    class Tree:
        def attach(self,p):
            assert not paths[0].exists();seen.append('attached')
        def close(self):
            assert paths[0].exists();seen.append('closed')
    def launch(command,**kw):
        request=json.loads(Path(command[-3]).read_text('utf8'));paths.append(Path(request['owned_start_gate']))
        Path(command[-2]).write_text(json.dumps({'ok':True,'result':{'segments':[]}}),'utf8')
        return SimpleNamespace(returncode=0,poll=lambda:0)
    monkeypatch.setattr(owned_process,'OwnedProcessTree',Tree)
    monkeypatch.setattr(transcription.subprocess,'Popen',launch)
    assert transcription._run_transcription_worker(Path('source'),settings,'he',None,'balanced',2,None)=={'segments':[]}
    assert seen==['attached','closed'] and not paths[0].parent.exists()


def test_assignment_failure_never_opens_gate_or_starts_model(tmp_path,monkeypatch):
    monkeypatch.setenv('CUTROOM_DATA_DIR',str(tmp_path/'data'));settings=load_settings();seen=[]
    process=SimpleNamespace(returncode=None,poll=lambda:None,terminate=lambda:seen.append('stop'),wait=lambda **kw:0)
    class Tree:
        def attach(self,p):raise RuntimeError('containment unavailable')
        def close(self):seen.append('close')
    monkeypatch.setattr(owned_process,'OwnedProcessTree',Tree)
    monkeypatch.setattr(transcription.subprocess,'Popen',lambda *a,**k:process)
    with pytest.raises(RuntimeError,match='containment unavailable'):
        transcription._run_transcription_worker(Path('source'),settings,'en',None,'balanced',2,None)
    assert 'stop' in seen and seen[-2:]==['close','stop']


def test_cleanup_uncertainty_is_failure_instead_of_false_cancel(tmp_path,monkeypatch):
    monkeypatch.setenv('CUTROOM_DATA_DIR',str(tmp_path/'data'));settings=load_settings()
    process=SimpleNamespace(returncode=None,poll=lambda:None,terminate=lambda:None,wait=lambda **kw:0)
    class Tree:
        def attach(self,p):pass
        def close(self):raise RuntimeError('cleanup incomplete')
    monkeypatch.setattr(owned_process,'OwnedProcessTree',Tree)
    monkeypatch.setattr(transcription.subprocess,'Popen',lambda *a,**k:process)
    def cancel():raise JobCancelled('cancel')
    with pytest.raises(RuntimeError,match='cleanup incomplete'):
        transcription._run_transcription_worker(Path('source'),settings,'en',None,'balanced',2,cancel)


def test_worker_rejects_gate_outside_own_ipc_before_transcription(tmp_path,monkeypatch):
    request=tmp_path/'request.json';result=tmp_path/'result.json'
    request.write_text(json.dumps({'owned_start_gate':str(tmp_path.parent/'other')}),'utf8')
    monkeypatch.setattr(transcription_worker,'_transcribe_in_process',lambda *a,**k:pytest.fail('model started'))
    assert transcription_worker.run(request,result,tmp_path/'progress.json')==1
    assert 'Invalid worker ownership gate' in json.loads(result.read_text('utf8'))['error']


def test_zero_job_count_does_not_skip_waiting_for_known_child_handle():
    """Recorded Windows smoke race: count can reach zero before exit is signaled."""
    if owned_process.os.name!='nt':pytest.skip('Windows Job Object mock contract')
    import ctypes
    from ctypes import wintypes
    calls=[]
    class Accounting(ctypes.Structure):_fields_=[('active',wintypes.DWORD)]
    class Kernel:
        def TerminateJobObject(self,*args):calls.append('terminate-own-job');return True
        def WaitForSingleObject(self,handle,timeout):
            assert handle==456 and timeout>=0;calls.append('wait-child-exit');return 0
        def QueryInformationJobObject(self,handle,kind,pointer,*args):
            pointer._obj.active=0;calls.append('query-own-count');return True
        def CloseHandle(self,handle):calls.append(('close',handle));return True
    tree=object.__new__(owned_process.OwnedProcessTree);tree.handle=123;tree.process=None
    tree.kernel=Kernel();tree.Accounting=Accounting;tree._owned_handles=lambda job:[456]
    tree.close()
    assert calls.index('wait-child-exit')<calls.index('query-own-count')
    assert ('close',456) in calls and ('close',123) in calls and tree.handle is None
