"""Bounded local caption proposals; canonical speech and edits stay immutable."""
from __future__ import annotations
import copy
import importlib.util
import ctypes
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from .caption_alternatives import FORMAT, binding, register, review
from .local_models import _WHISPER_REPOS, _complete_speech_snapshot, speech_cache_dir
from .transcription import _extract_audio_chunk, _model_for_request, transcribe

MAX_SECONDS = 90.

def available_memory():
    """A narrow physical-memory read; no process inventory or system changes."""
    try:
        if os.name == "nt":
            class Memory(ctypes.Structure):
                _fields_ = [("length",ctypes.c_ulong),("load",ctypes.c_ulong)] + [(name,ctypes.c_ulonglong) for name in
                    ("total","available","page_total","page_available","virtual_total","virtual_available","extended")]
            value=Memory();value.length=ctypes.sizeof(value)
            return value.available if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)) else None
        return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (OSError,ValueError,AttributeError):
        return None

def cached_model(settings, language):
    name = _model_for_request(settings, "quality", language, "cpu")
    if name in _WHISPER_REPOS:
        base = speech_cache_dir() / ("models--" + _WHISPER_REPOS[name].replace("/", "--"))
        try:
            ref = (base / "refs/main").read_text("utf8").strip()
            if not re.fullmatch(r"[0-9a-fA-F]{40,64}", ref): return None
            path = base / "snapshots" / ref
        except OSError: return None
    else:
        path = Path(name)
        if not path.is_absolute(): return None
    return path if _complete_speech_snapshot(path) else None

def source_interval(project):
    binding(project)
    ranges = review(project, "original")["ranges"]
    if len(ranges) != 1:
        raise ValueError("Generate captions for one continuous source range. Cuts or multiple source ranges are not supported yet.")
    start, end = ranges[0]["start"], ranges[0]["end"]
    if not 0 < end-start <= MAX_SECONDS:
        raise ValueError("This local caption review supports an edit of at most 90 seconds. Trim the edit first.")
    rows = ((project.get("manual") or {}).get("source_tracks") or {}).get("A", [])
    if any(row.get("source_ref", "primary:A") != "primary:A" or float(row.get("video_speed", 1)) != 1 for row in rows):
        raise ValueError("Caption generation requires original source A at normal speed, without library-source substitutions.")
    if not project["sources"]["A"].get("has_audio"):
        raise ValueError("The source has no audio to transcribe.")
    return [start, end]

def readiness(project, settings, language, selection=None):
    if language not in {"he", "en"}: raise ValueError("Choose Hebrew or English explicitly.")
    scope=None
    if selection is not None:
        from .caption_ranges import selected_scope
        scope=selected_scope(project,selection)
        interval=[min(p[2] for p in scope["pieces"]),max(p[3] for p in scope["pieces"])]
    else: interval = source_interval(project)
    model = cached_model(settings, language)
    available = importlib.util.find_spec("faster_whisper") is not None
    memory = available_memory()
    if memory is not None and memory < 8*1024**3:
        return {"ready":False,"language":language,"source_interval":interval,"duration":interval[1]-interval[0],
                "message":"Keep at least 8 GiB physical RAM available before local caption generation."}
    if len(project.get("caption_alternatives") or {}) >= 3:
        return {"ready":False,"message":"This project already has three saved alternatives. No new inference was started."}
    return {"ready": bool(model and available), "language": language, "source_interval": interval,
            "duration": (scope["timeline_range"][1]-scope["timeline_range"][0]) if scope else interval[1]-interval[0], "scope":scope, "model": model.parent.parent.name.removeprefix("models--").replace("--", "/") if model else None,
            "message": "Local cached model ready. Generated captions require listening and explicit Apply." if model and available else
            "A complete cached speech model and faster-whisper are required. Check Local models; this action never downloads or installs anything."}

def generate(context, project_id, store, settings, language, expected_revision, selection=None):
    project = store.load(project_id)
    if project["revision"] != expected_revision: raise RuntimeError("revision_conflict")
    state = readiness(project, settings, language, selection)
    if not state["ready"]: raise ValueError(state["message"])
    model = cached_model(settings, language)
    start, end = state["source_interval"]
    source = store.project_dir(project_id) / project["sources"]["A"]["relative_path"]
    source = source.resolve(); media_root = (store.project_dir(project_id) / "media").resolve()
    if not source.is_relative_to(media_root) or not source.is_file(): raise ValueError("The original source file is unavailable.")
    if shutil.disk_usage(settings.cache_dir).free < 128*1024**2: raise ValueError("Keep at least 128 MiB free for the bounded audio scratch file.")
    selected = copy.deepcopy(settings)
    selected.ai.update(cloud_connection={"mode":"local"}, whisper_device="cpu", whisper_compute_type="int8",
        whisper_model=str(model), whisper_models={"quality":str(model)}, hebrew_whisper_model=str(model),
        whisper_isolate_process=True, whisper_local_files_only=True, download_models_on_setup=False)
    started = time.monotonic()
    def check():
        context.check_cancelled()
        memory = available_memory()
        if memory is not None and memory < 4.5*1024**3:
            raise RuntimeError("Caption generation stopped to retain 4.5 GiB available RAM. Nothing was applied.")
        if time.monotonic()-started > 180: raise RuntimeError("Local caption generation exceeded its 180-second budget. Nothing was applied.")
    context.update(.02, "Extracting this edit's source audio locally")
    pieces=state.get("scope",{}).get("pieces") if state.get("scope") else [[0,end-start,start,end]]
    shifted={"language":language,"model":state["model"],"segments":[]}
    with tempfile.TemporaryDirectory(prefix="caption-review-", dir=settings.cache_dir) as folder:
        for n,(_,_,a,b) in enumerate(pieces):
            audio = _extract_audio_chunk(source, Path(folder)/f"speech-{n}.wav", selected, a, b-a, check)
            transcript = transcribe(audio, selected, language=language, performance_mode="quality", duration=b-a,
                progress=lambda value,message: context.update(.08+((n+value)/len(pieces))*.82,message), cancel_check=check)
            check()
            for i,raw in enumerate(transcript.get("segments") or []):
                row=copy.deepcopy(raw);row["id"]=f"p{n}:"+str(row.get("id") or f"asr-{i}")
                row["start"]=round(float(row["start"])+a,6);row["end"]=round(float(row["end"])+a,6)
                for word in row.get("words") or []:
                    word["start"]=round(float(word["start"])+a,6);word["end"]=round(float(word["end"])+a,6)
                shifted["segments"].append(row)
    envelope = {"format":FORMAT,"binding":binding(project),"source_interval":[start,end],
                "label":f"Local {language} ASR · unverified", "transcript":shifted}
    if state.get("scope"):envelope["scope"]=state["scope"]
    check(); context.update(.95,"Saving an unverified alternative for review; original captions remain active")
    result = {}
    def save(current):
        check()
        if binding(current) != envelope["binding"]: raise ValueError("The source or original transcript changed. Generate again.")
        result["alternative_id"] = register(current, envelope)
        context.commit()
    store.update(project_id, save, expected_revision=expected_revision)
    return {**result,"source_interval":[start,end],"language":language,"model":state["model"],"applied":False,"verified_by_listening":False}
