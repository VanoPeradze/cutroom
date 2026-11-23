"""Independent saved-project copies with durable, retry-safe publication receipts."""
from __future__ import annotations
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import threading
import time
from .jobs import JobCancelled
from .utils import atomic_write_json, new_id, now_iso
from .upload_storage import process_alive, RESERVE_BYTES

TOKEN = re.compile(r"[A-Za-z0-9_-]{16,96}\Z")
ACTIVE = {"queued", "running", "publishing"}

class ProjectCopyError(ValueError):
    def __init__(self, message, code="project_copy_conflict", status=409):
        super().__init__(message)
        self.code, self.status = code, status

def copy_directory(settings):
    return settings.projects_dir.parent / ".project-copies"

def require_source_writable(settings, project_id):
    lease = copy_directory(settings) / "lease.json"
    if lease.exists():
        try: data = json.loads(lease.read_text(encoding="utf8"))
        except (OSError, ValueError):
            raise ProjectCopyError("Project copy recovery is required before changing projects.")
        if project_id in {data.get("source_project_id"), data.get("destination_id")}:
            raise ProjectCopyError("Finish or cancel the project copy before changing its source.", "project_copy_active")

def _regular(path):
    s = path.lstat()
    if stat.S_ISLNK(s.st_mode) or getattr(s,"st_file_attributes",0) & 0x400:
        raise ProjectCopyError("Linked or reparse-point files cannot be copied safely.")
    if not stat.S_ISREG(s.st_mode) or s.st_nlink != 1:
        raise ProjectCopyError("Project copies require independently owned regular files.")
    return s

def _hash(path, check=lambda:None):
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            check(); block=stream.read(4*1024*1024)
            if not block:break
            digest.update(block)
    return digest.hexdigest()

def inventory(root):
    result={}
    for top in ("media","cache"):
        folder=root/top
        if not folder.exists():continue
        for parent,dirs,files in os.walk(folder,followlinks=False):
            for name in ["."]+dirs:
                path=Path(parent) if name=="." else Path(parent)/name
                s=path.lstat()
                if name!="." and (name.startswith(".") or name.endswith(".lock")):
                    raise ProjectCopyError("Finish or repair temporary media preparation before copying.")
                if not stat.S_ISDIR(s.st_mode) or getattr(s,"st_file_attributes",0)&0x400 or path.is_symlink():
                    raise ProjectCopyError("Linked project directories cannot be copied safely.")
            for name in files:
                path=Path(parent)/name; s=_regular(path)
                rel=path.relative_to(root).as_posix()
                if name==".preparation.lock" and path.parent.parent==root/"media"/"assets":
                    continue  # Runtime OS-lock marker, not saved project content.
                if any(part.startswith(".") for part in Path(rel).parts) or name.endswith((".tmp",".part",".partial",".lock")):
                    raise ProjectCopyError("Finish or repair temporary media preparation before copying.")
                result[rel]={"size":s.st_size,"mtime_ns":s.st_mtime_ns,"ctime_ns":s.st_ctime_ns,"ino":s.st_ino,"dev":s.st_dev}
    return result

class ProjectCopyCoordinator:
    def __init__(self,store,jobs,gate,idle):
        self.store,self.jobs,self.gate,self.idle=store,jobs,gate,idle
        self.root=copy_directory(store.settings)
        self.root.mkdir(parents=True,exist_ok=True)
        info=self.root.lstat()
        if self.root.resolve().parent!=store.settings.projects_dir.resolve().parent or self.root.is_symlink() or getattr(info,"st_file_attributes",0)&0x400:
            raise ProjectCopyError("Unsafe project copy receipt directory.")
        self.owners=self.root/"servers"
        self.owners.mkdir(exist_ok=True)
        if self.owners.is_symlink() or getattr(self.owners.lstat(),"st_file_attributes",0)&0x400:
            raise ProjectCopyError("Unsafe copy server ownership directory.")
        atomic_write_json(self.owners/(str(os.getpid())+".json"),{"pid":os.getpid()})
        self.lease=self.root/"lease.json"
        if self.lease.exists() or self.lease.is_symlink():_regular(self.lease)
        self.writers=0
        self.recover()

    def _path(self,token):
        if not isinstance(token,str) or not TOKEN.fullmatch(token):
            raise ProjectCopyError("Use a valid copy operation token.","invalid_field",400)
        path=self.root/(token+".json")
        if path.exists() or path.is_symlink():_regular(path)
        return path

    def _save(self,record):
        with self.gate:
            path=self._path(record["operation_token"])
            if path.exists():
                prior=json.loads(path.read_text(encoding="utf8"))
                record["cancel_requested"]=bool(record.get("cancel_requested") or prior.get("cancel_requested"))
            atomic_write_json(path,record)

    def get(self,token):
        try:record=json.loads(self._path(token).read_text(encoding="utf8"))
        except FileNotFoundError:raise ProjectCopyError("Copy operation not found.","not_found",404)
        if record.get("operation_token")!=token:raise ProjectCopyError("Copy receipt is invalid.")
        return record

    def poll(self,token):
        with self.gate:
            r=self.get(token)
            job=self.jobs.get(r.get("job_id")) if r.get("job_id") else None
            if (r["status"] in {"queued","running"} and job is not None
                    and job.status not in {"queued","running"} and r.get("owner_pid")==os.getpid()):
                # JobManager may cancel/fail before invoking our worker at all.
                # Reconcile only the exact current receipt/lease/job binding.
                owner=json.loads(self.lease.read_text(encoding="utf8")) if self.lease.exists() else None
                expected={"pid":os.getpid(),"source_project_id":r["source_project_id"],
                          "destination_id":r["destination_id"],"operation_token":token}
                if (owner!=expected or job.kind!="project_copy" or job.project_id!=r["source_project_id"] or job.dedupe_key!=token):
                    raise ProjectCopyError("Copy ownership needs manual recovery.","project_copy_recovery")
                destination=self.store.project_dir(r["destination_id"])
                if destination.exists() or destination.is_symlink():
                    raise ProjectCopyError("Copy destination needs publication recovery.","project_copy_recovery")
                try:self._cleanup(r)
                except OSError:r["cleanup_pending"]=True
                cancelled=job.status=="cancelled"
                r.update(status="cancelled" if cancelled else "failed",
                         error="Copy cancelled before publication; original unchanged." if cancelled else "Copy worker stopped before publication; original unchanged.")
                self._save(r);self.lease.unlink()
            if (r["status"]=="publishing" and self.lease.exists() and r.get("owner_pid")==os.getpid()
                    and job is not None and job.status not in {"queued","running"} and not r.get("recovery_failed")):
                owner=json.loads(self.lease.read_text(encoding="utf8"))
                expected={"pid":os.getpid(),"source_project_id":r["source_project_id"],
                          "destination_id":r["destination_id"],"operation_token":token}
                if (owner!=expected or job.kind!="project_copy" or job.project_id!=r["source_project_id"] or job.dedupe_key!=token):
                    raise ProjectCopyError("Copy ownership needs manual recovery.","project_copy_recovery")
                recovered=self.jobs.submit("project_copy",r["source_project_id"],self._recover_published,token,
                                           dedupe_key=token,deduplicate=False)
                r["job_id"]=recovered.id;self._save(r)
            return r

    def _recover_published(self,context,token):
        with self.gate:r=self.get(token)
        destination=self.store.project_dir(r["destination_id"])
        try:
            context.commit()
            if not r.get("state_sha256") or _hash(destination/"project.json")!=r["state_sha256"] or set(inventory(destination))!=set(r.get("file_hashes",{})):
                raise ProjectCopyError("Published copy identity differs; manual recovery is required.")
            for rel,digest in r["file_hashes"].items():
                if _hash(destination/rel)!=digest:raise ProjectCopyError("Published copy media differs; manual recovery is required.")
            with self.gate:
                r.update(status="completed",progress=1,error=None);self._save(r);self.lease.unlink()
            return {"copy_project_id":r["destination_id"],"operation_token":token}
        except (ProjectCopyError, FileNotFoundError) as exc:
            r.update(recovery_failed=True,error="Published copy verification failed; manual recovery is required.");self._save(r);raise

    def public(self,r):
        return {k:r.get(k) for k in ("operation_token","source_project_id","source_revision","name","status","progress","copied_bytes","total_bytes","job_id","error","cancel_requested")} | {"copy_project_id":r["destination_id"] if r["status"]=="completed" else None}

    def active(self):
        with self.gate:
            if not self.lease.exists():return []
            try:
                owner=json.loads(self.lease.read_text(encoding="utf8"))
                record=self.poll(owner["operation_token"])
                return [self.public(record)] if self.lease.exists() else []
            except (ValueError,KeyError,OSError) as exc:
                raise ProjectCopyError("Project copy recovery is required; its source remains protected.","project_copy_recovery") from exc

    def for_project(self,project_id):
        with self.gate:
            operations=self.active()
            if not operations:return None
            owner=json.loads(self.lease.read_text(encoding="utf8"))
            return operations[0] if project_id in {owner.get("source_project_id"),owner.get("destination_id")} else None

    def require_idle(self):
        if self.lease.exists():raise ProjectCopyError("Finish or cancel the project copy first.","project_copy_active")

    def begin_writer(self):
        with self.gate:
            self.require_idle();self.writers+=1
    def end_writer(self):
        with self.gate:self.writers=max(0,self.writers-1)

    def recover(self):
        if not self.lease.exists():
            for path in self.root.glob("*.json"):
                if path.name=="lease.json":continue
                try:
                    r=json.loads(path.read_text(encoding="utf8"))
                    if r.get("cleanup_pending") and r.get("status") not in ACTIVE:
                        self._cleanup(r);r.pop("cleanup_pending",None);self._save(r)
                    if r.get("status") in ACTIVE and not process_alive(int(r.get("owner_pid",0))):
                        r.update(status="interrupted",error="Copy interrupted before admission completed.")
                        self._cleanup(r);self._save(r)
                except (ValueError,KeyError,OSError):continue
            return
        try:
            try:owner=json.loads(self.lease.read_text(encoding="utf8"))
            except ValueError:
                candidates=[]
                for path in self.root.glob("*.json"):
                    if path.name=="lease.json":continue
                    r=json.loads(path.read_text(encoding="utf8"))
                    if r.get("status") in ACTIVE:candidates.append(r)
                if len(candidates)!=1:return
                r=candidates[0]
                owner={"pid":r["owner_pid"],"operation_token":r["operation_token"]}

            if process_alive(int(owner["pid"])):return
            r=self.get(owner["operation_token"])
            destination=self.store.project_dir(r["destination_id"])
            if destination.exists():
                if (r.get("state_sha256") and _hash(destination/"project.json")==r["state_sha256"]
                    and set(inventory(destination))==set(r.get("file_hashes",{}))
                    and all(_hash(destination/rel)==digest for rel,digest in r.get("file_hashes",{}).items())):
                    r.update(status="completed",progress=1,error=None)
                else:raise ProjectCopyError("Copy publication requires manual recovery; destination identity differs.")
            else:
                r.update(status="interrupted",error="Copy interrupted before publication. Start a new copy to retry.")
            self._cleanup(r);self._save(r);self.lease.unlink()
        except (KeyError,ValueError,OSError):
            # Unknown ownership must remain fenced, not be deleted speculatively.
            return

    def _cleanup(self,r):
        stage=self.root/("stage-"+r["operation_token"])
        if stage.exists():
            if (stage.is_symlink() or getattr(stage.lstat(),"st_file_attributes",0)&0x400
                    or not stage.is_dir() or stage.resolve().parent!=self.root.resolve()):raise ProjectCopyError("Unsafe copy staging directory")
            shutil.rmtree(stage)

    def start(self,source,revision,name,token):
        path=self._path(token)
        if type(revision)!=int or revision<1 or not isinstance(name,str) or not name.strip() or len(name.strip())>120:
            raise ProjectCopyError("Choose a name and current saved revision.","invalid_field",400)
        name=name.strip()
        with self.gate:
            if path.exists():
                r=self.get(token)
                if (r["source_project_id"],r["source_revision"],r["name"])!=(source,revision,name):raise ProjectCopyError("This token already belongs to a different copy request.")
                return self.public(self.poll(token))
            self.require_idle()
            for owner_path in self.owners.glob("*.json"):
                _regular(owner_path)
                try:owner_pid=int(json.loads(owner_path.read_text(encoding="utf8"))["pid"])
                except (ValueError,KeyError):raise ProjectCopyError("Server ownership needs recovery before copying.")
                if owner_pid!=os.getpid() and process_alive(owner_pid):
                    raise ProjectCopyError("Close the other CUTROOM server using this data directory before copying.")
            if self.writers or self.jobs.active() or not self.idle():raise ProjectCopyError("Finish active jobs and imports before copying a project.","project_busy")
            with self.store._lock_for(source):
                project=self.store.load(source)
                if project["revision"]!=revision:raise ProjectCopyError("The source changed. Refresh before copying.","revision_conflict")
                from .source_tracks import validate_sequence_version
                from .layer_tracks import validate_layer_tracks
                validate_sequence_version(project);validate_layer_tracks(project)
                r=dict(operation_token=token,source_project_id=source,source_revision=revision,name=name,destination_id=new_id("project"),status="queued",progress=0,copied_bytes=0,total_bytes=0,job_id=None,error=None,cancel_requested=False)
                r["owner_pid"]=os.getpid()
                _regular(self.store.state_path(source))
                r["source_state_sha256"]=_hash(self.store.state_path(source))
                owner={"pid":os.getpid(),"source_project_id":source,"destination_id":r["destination_id"],"operation_token":token}
                # Exclusive creation prevents a second cooperating process admitting another copy.
                self._save(r)
                lease_created=False
                try:
                    handle=self.lease.open("x",encoding="utf8");lease_created=True
                    with handle as f:json.dump(owner,f);f.flush();os.fsync(f.fileno())
                except OSError as exc:
                    if lease_created:self.lease.unlink(missing_ok=True)
                    r.update(status="failed",error="Could not reserve independent copy storage.");self._save(r)
                    raise ProjectCopyError("Could not reserve independent copy storage.") from exc
                try:
                    job=self.jobs.submit("project_copy",source,self._run,token,project,dedupe_key=token)
                    # Worker takes this same short gate before reading its receipt.
                    r["job_id"]=job.id;self._save(r)
                except Exception:
                    r.update(status="failed",error="Could not start project copy.");self._save(r);self.lease.unlink(missing_ok=True);raise
            return self.public(r)

    def cancel(self,token):
        with self.gate:
            r=self.get(token)
            if r["status"]=="publishing" and self.store.project_dir(r["destination_id"]).exists():
                return self.public(self.poll(token))
            if r["status"] in ACTIVE and r.get("job_id"):
                r["cancel_requested"]=True;self._save(r);self.jobs.cancel(r["job_id"])
                job=self.jobs.get(r["job_id"])
                if job is not None and job.status=="cancelled" and r["status"]=="queued":
                    r.update(status="cancelled",error="Copy cancelled before it started.")
                    self._save(r);self.lease.unlink(missing_ok=True)
            return self.public(r)

    def _run(self,context,token,project):
        with self.gate:r=self.get(token)
        stage=self.root/("stage-"+token);source=self.store.project_dir(project["id"])
        published=False
        try:
            r.update(status="running");self._save(r)
            raw=(source/"project.json").read_bytes()
            if hashlib.sha256(raw).hexdigest()!=r["source_state_sha256"]:
                raise ProjectCopyError("Source state changed before copying.","revision_conflict")
            files=inventory(source)
            for item,keys in [(v,("relative_path","preview_relative_path")) for v in project.get("sources",{}).values() if v] + [(v,("path","preview_path","thumbnail_path")) for v in project.get("assets",{}).values()]:
                if not isinstance(item.get(keys[0]),str) or not item[keys[0]]:
                    raise ProjectCopyError("A referenced original media file is unavailable.")
                if item.get("preparation") in {"queued","running","preparing"} or item.get("status") in {"queued","running","preparing"}:
                    raise ProjectCopyError("Finish media preparation before copying.")
                for key in keys:
                    relative=item.get(key)
                    if relative is not None and (not isinstance(relative,str) or relative.replace("\\","/") not in files):
                        raise ProjectCopyError("A referenced project media file is missing or outside the owned media/cache trees.")
            total=sum(x["size"] for x in files.values());r["total_bytes"]=total;self._save(r)
            if shutil.disk_usage(self.root).free < total+len(raw)+RESERVE_BYTES:raise ProjectCopyError("Not enough free disk space for an independent project copy.","insufficient_storage")
            stage.mkdir();(stage/"media").mkdir();(stage/"cache").mkdir()
            hashes={};done=0;last_progress=0
            for rel,meta in sorted(files.items()):
                context.check_cancelled();src=source/rel;dst=stage/rel;dst.parent.mkdir(parents=True,exist_ok=True)
                digest=hashlib.sha256()
                with src.open("rb") as inp,dst.open("xb") as out:
                    while True:
                        context.check_cancelled();block=inp.read(4*1024*1024)
                        if not block:break
                        out.write(block);digest.update(block);done+=len(block)
                        context.update(.85*done/max(1,total),"Copying saved media")
                        if time.monotonic()-last_progress>.3:
                            r.update(copied_bytes=done,progress=.85*done/max(1,total));self._save(r);last_progress=time.monotonic()
                    out.flush();os.fsync(out.fileno())
                shutil.copystat(src,dst,follow_symlinks=False)
                hashes[rel]=digest.hexdigest()
                if _hash(dst,context.check_cancelled)!=hashes[rel]:raise ProjectCopyError("Copied media verification failed.")
                r.update(copied_bytes=done,progress=.85*done/max(1,total));self._save(r)
            if set(inventory(stage))!=set(files):raise ProjectCopyError("Copied file inventory changed during verification.")
            for rel,digest in hashes.items():
                if _hash(stage/rel,context.check_cancelled)!=digest:raise ProjectCopyError("Copied media changed before publication.")
            if inventory(source)!=files:raise ProjectCopyError("Source files changed during copying.")
            for rel,digest in hashes.items():
                if _hash(source/rel,context.check_cancelled)!=digest:raise ProjectCopyError("Source content changed during copying.")
            if inventory(source)!=files:raise ProjectCopyError("Source files changed during verification.")
            if (source/"project.json").read_bytes()!=raw or self.store.load(project["id"])["revision"]!=r["source_revision"]:raise ProjectCopyError("The source project changed during copying.","revision_conflict")
            cloned=copy.deepcopy(project);cloned.update(id=r["destination_id"],name=r["name"],revision=1,created_at=now_iso(),updated_at=now_iso(),exports=[]);cloned.pop("name_auto",None)
            manual=cloned.setdefault("manual",{});manual["_history"]={"undo":[],"redo":[]};manual["history"]={"undo_count":0,"redo_count":0}
            atomic_write_json(stage/"project.json",cloned)
            r["file_hashes"]=hashes
            r["state_sha256"]=_hash(stage/"project.json");r.update(status="publishing",progress=.99);self._save(r)
            with self.gate:
                context.commit()
                destination=self.store.project_dir(r["destination_id"])
                if destination.exists():raise ProjectCopyError("The reserved copy destination already exists.")
                stage.rename(destination);published=True
                r.update(status="completed",progress=1,copied_bytes=total,error=None);self._save(r)
            return {"copy_project_id":r["destination_id"],"operation_token":token}
        except Exception as exc:
            if not published:
                r.update(status="cancelled" if isinstance(exc,JobCancelled) else "failed",error="Copy cancelled; original unchanged." if isinstance(exc,JobCancelled) else str(exc)[:500])
                try:self._cleanup(r)
                except OSError:r["cleanup_pending"]=True
                self._save(r)
            raise
        finally:
            with self.gate:
                # Publication receipt must be durable before releasing the fence.
                if not published or self.get(token)["status"]=="completed":self.lease.unlink(missing_ok=True)
