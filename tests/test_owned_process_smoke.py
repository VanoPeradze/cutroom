"""One tiny Windows worker→child cancellation test. No model, media or scan."""
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest
from cutroom import transcription, owned_process
from cutroom.config import load_settings
from cutroom.jobs import JobCancelled
from test_media_library import api
from test_owned_lifecycle import wait
import threading


def test_normal_app_heavy_pools_share_one_processing_slot(api):
    app,_,_,_=api;manager=app.extensions['cutroom_jobs'];entered=threading.Event();release=threading.Event()
    def background(c):entered.set();release.wait(2);return 'prepared'
    try:
        first=manager.submit('prepare_source','synthetic-a',background);assert entered.wait(1)
        second=manager.submit('director','synthetic-b',lambda c:'done')
        wait(lambda:'Waiting for another' in second.message)
        assert second.status=='queued' and first.status=='running'
        release.set();wait(lambda:second.status=='completed')
    finally:release.set()


@pytest.mark.skipif(os.name!='nt',reason='Native Windows ownership qualification; no POSIX claim')
def test_cancelled_worker_terminates_owned_child_and_verifies_exit(tmp_path,monkeypatch,record_property):
    monkeypatch.setenv('CUTROOM_DATA_DIR',str(tmp_path/'data'));settings=load_settings()
    real_popen=subprocess.Popen;real_tree=owned_process.OwnedProcessTree
    record=tmp_path/'owned-pids.json';receipt={};roots=[];child_handle=None
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD];kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)];kernel.GetExitCodeProcess.restype=wintypes.BOOL
    kernel.TerminateProcess.argtypes=[wintypes.HANDLE,wintypes.UINT];kernel.TerminateProcess.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    code='''import sys,json,time,subprocess,os
from pathlib import Path
request=json.loads(Path(sys.argv[1]).read_text('utf8'))
gate=Path(request['owned_start_gate'])
while not gate.exists():time.sleep(.01)
child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
Path(sys.argv[2]).write_text(json.dumps({'worker':os.getpid(),'child':child.pid}),'utf8')
while True:time.sleep(.05)
'''
    def launch(command,**kw):
        p=real_popen([sys.executable,'-c',code,command[-3],str(record)],**kw);roots.append(p);return p
    class ObservedTree(real_tree):
        def close(self):
            if child_handle:receipt['child_alive_after_direct_worker_stop']=kernel.WaitForSingleObject(child_handle,0)==258
            super().close()
            if child_handle:receipt['child_exit_verified_after_tree_close']=kernel.WaitForSingleObject(child_handle,0)==0
    monkeypatch.setattr(owned_process,'OwnedProcessTree',ObservedTree)
    monkeypatch.setattr(transcription.subprocess,'Popen',launch)
    started=time.monotonic()
    def cancel():
        nonlocal child_handle
        if record.exists():
            pids=json.loads(record.read_text('utf8'));receipt.update(pids)
            child_handle=kernel.OpenProcess(0x100000|0x1000|0x1,False,pids['child'])
            assert child_handle,ctypes.WinError(ctypes.get_last_error())
            raise JobCancelled('synthetic cancellation')
        if time.monotonic()-started>10:raise RuntimeError('Smoke worker failed to start within10s')
    try:
        with pytest.raises(JobCancelled):
            transcription._run_transcription_worker(Path('synthetic-unused'),settings,'he',None,'balanced',2,cancel)
        assert receipt['child_alive_after_direct_worker_stop'] is True
        assert receipt['child_exit_verified_after_tree_close'] is True
        assert roots[0].poll() is not None
        code_out=wintypes.DWORD();assert kernel.GetExitCodeProcess(child_handle,ctypes.byref(code_out))
        receipt.update(child_exit_code=code_out.value,worker_exit_code=roots[0].returncode,elapsed_seconds=round(time.monotonic()-started,3))
        assert code_out.value!=259
        record_property('owned_tree_receipt',json.dumps(receipt))
    finally:
        if child_handle:
            if kernel.WaitForSingleObject(child_handle,0)==258:kernel.TerminateProcess(child_handle,1);kernel.WaitForSingleObject(child_handle,3000)
            kernel.CloseHandle(child_handle)
        for p in roots:
            if p.poll() is None:p.terminate();p.wait(timeout=3)
