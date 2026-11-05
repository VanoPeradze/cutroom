"""Contain only a newly launched CUTROOM worker and its descendants.

Windows attaches before a worker's explicit start gate opens. POSIX workers
start a new session; no PID/name scans, shared services or model unload calls.
"""
from __future__ import annotations

import os
import signal
import time


class OwnedProcessTree:
    def __init__(self):
        self.process = None
        self.handle = None
        if os.name != "nt":
            return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_longlong),('job_time',ctypes.c_longlong),
                ('flags',wintypes.DWORD),('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),
                ('active_processes',wintypes.DWORD),('affinity',ctypes.c_size_t),
                ('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class Counters(ctypes.Structure):
            _fields_=[(x,ctypes.c_ulonglong) for x in ['read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes']]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',Counters),('process_memory',ctypes.c_size_t),
                ('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        class Accounting(ctypes.Structure):
            _fields_=[(x,ctypes.c_longlong) for x in ['user_time','kernel_time','period_user','period_kernel']]+[
                (x,wintypes.DWORD) for x in ['page_faults','total','active','terminated']]
        self.Accounting = Accounting
        k=self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        for name,args,restype in [
            ('CreateJobObjectW',[ctypes.c_void_p,wintypes.LPCWSTR],wintypes.HANDLE),
            ('SetInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD],wintypes.BOOL),
            ('AssignProcessToJobObject',[wintypes.HANDLE,wintypes.HANDLE],wintypes.BOOL),
            ('TerminateJobObject',[wintypes.HANDLE,wintypes.UINT],wintypes.BOOL),
            ('QueryInformationJobObject',[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p],wintypes.BOOL),
            ('OpenProcess',[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD],wintypes.HANDLE),
            ('IsProcessInJob',[wintypes.HANDLE,wintypes.HANDLE,ctypes.POINTER(wintypes.BOOL)],wintypes.BOOL),
            ('WaitForSingleObject',[wintypes.HANDLE,wintypes.DWORD],wintypes.DWORD),
            ('CloseHandle',[wintypes.HANDLE],wintypes.BOOL)]:
            fn=getattr(k,name);fn.argtypes=args;fn.restype=restype
        self.handle=k.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        limits=Extended();limits.basic.flags=0x2000  # KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
            error=ctypes.WinError(ctypes.get_last_error());k.CloseHandle(self.handle);self.handle=None;raise error

    def attach(self, process):
        if self.process is not None:raise RuntimeError('Worker tree is already assigned')
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            if not self.kernel.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
                raise ctypes.WinError(ctypes.get_last_error())
        self.process=process

    def _owned_handles(self, job):
        """Query this private Job Object only; never enumerate OS processes."""
        import ctypes
        from ctypes import wintypes
        # CUTROOM's worker has one FFmpeg child at a time; bound unexpected trees.
        class Pids(ctypes.Structure):
            _fields_=[('assigned',wintypes.DWORD),('listed',wintypes.DWORD),('ids',ctypes.c_size_t*256)]
        info=Pids();handles=[]
        if not self.kernel.QueryInformationJobObject(job,3,ctypes.byref(info),ctypes.sizeof(info),None):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.assigned>256:raise RuntimeError('Owned worker tree exceeds its cleanup bound')
        try:
            for pid in info.ids[:info.listed]:
                handle=self.kernel.OpenProcess(0x100000|0x1000,False,pid)
                if not handle:
                    # Absent PID means it exited between the two owned queries.
                    if ctypes.get_last_error()==87:continue
                    raise ctypes.WinError(ctypes.get_last_error())
                belongs=wintypes.BOOL()
                if not self.kernel.IsProcessInJob(handle,job,ctypes.byref(belongs)):
                    self.kernel.CloseHandle(handle);raise ctypes.WinError(ctypes.get_last_error())
                if belongs.value:handles.append(handle)
                else:self.kernel.CloseHandle(handle)  # PID reuse: never wait on another app
            return handles
        except BaseException:
            for handle in handles:self.kernel.CloseHandle(handle)
            raise

    def close(self):
        if os.name == 'nt':
            if self.handle is None:return
            import ctypes
            handle=self.handle;self.handle=None
            children=[]
            try:
                children=self._owned_handles(handle)
                if not self.kernel.TerminateJobObject(handle,1):raise ctypes.WinError(ctypes.get_last_error())
                deadline=time.monotonic()+3.
                for child in children:
                    remaining=max(0,int((deadline-time.monotonic())*1000))
                    if self.kernel.WaitForSingleObject(child,remaining)!=0:
                        raise RuntimeError('CUTROOM child exit was not verified; cleanup is incomplete')
                while True:
                    info=self.Accounting()
                    if not self.kernel.QueryInformationJobObject(handle,1,ctypes.byref(info),ctypes.sizeof(info),None):
                        raise ctypes.WinError(ctypes.get_last_error())
                    if info.active==0:break
                    if time.monotonic()>=deadline:raise RuntimeError('CUTROOM worker cleanup is incomplete; exit was not verified')
                    time.sleep(.02)
            finally:
                for child in children:self.kernel.CloseHandle(child)
                self.kernel.CloseHandle(handle)
        elif self.process is not None:
            # The caller must use start_new_session=True before attaching.
            try:os.killpg(self.process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
        self.process=None
