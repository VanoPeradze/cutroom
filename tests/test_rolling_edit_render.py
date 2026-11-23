"""Output-frame ownership of a rolled seam, including decimal thirds."""
import copy, hashlib, shutil, subprocess, threading
import pytest
from cutroom.config import DEFAULTS, Settings
from cutroom.projects import ProjectStore
from cutroom.jobs import Job, JobContext
from cutroom.render import render_project
from cutroom.editing import apply_manual_edit
from test_media_render import media, project
from test_mixed_media_insert import VIDEO,IMAGE,media_row
from test_rolling_edit import L,R,T


def native_export(p,media,tmp_path,scope=None,normalize=False):
    raw=copy.deepcopy(DEFAULTS);raw["ffmpeg_threads"]=2;raw["render"].update(prefer_hardware=False,min_free_mb=0)
    data=tmp_path/"data";projects,exports,cache=(data/n for n in ("projects","exports","cache"))
    for f in (projects,exports,cache):f.mkdir(parents=True)
    cfg=Settings(raw,tmp_path,data,projects,exports,cache,media[1],media[2]);store=ProjectStore(cfg);v=store.create("Synthetic roll proof")
    v.update(copy.deepcopy(p));v["settings"].update(aspect="source",quality="fast",burn_captions=False);v["draft"]["audio_policy"]={"normalize":normalize,"target_lufs":-16}
    folder=store.project_dir(v["id"])/"media";shutil.copyfile(media[3],folder/"source.mp4");v["sources"]["A"]["relative_path"]="media/source.mp4"
    for asset in v["assets"].values():
        source=media[0]/asset["path"];target=folder/"assets"/asset["id"]/source.name;target.parent.mkdir(parents=True);shutil.copyfile(source,target)
        asset["path"]=target.relative_to(folder.parent).as_posix()
    saved=store.save(v);options={"_force_software":True,"quality":"fast"}
    if scope:options["range"]={"start_frame":scope[0],"end_frame":scope[1],"fps":v["settings"]["fps"],"expected_revision":saved["revision"]}
    job=Job("test-only","render",v["id"]);timer=threading.Timer(24,job.cancel_event.set);timer.start()
    try:rec=render_project(JobContext(job,threading.Lock()),v["id"],store,cfg,options)["export"]
    finally:timer.cancel()
    return cfg.exports_dir/rec["name"]


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("direction",[-1,1])
def test_native_render_picks_incoming_on_exact_cut_frame(media,tmp_path,fps,direction):
    p=project();p["settings"]["fps"]=fps;p["draft"]["output_duration"]=3.
    p["assets"]={
        VIDEO:{"id":VIDEO,"kind":"video","name":"Outgoing","status":"ready","path":"source.mp4","duration":3.,"width":160,"height":90,"has_audio":True},
        IMAGE:{"id":IMAGE,"kind":"image","name":"Incoming","status":"ready","path":"image.png","duration":0.,"width":80,"height":80,"has_audio":False},
    }
    def row(id,asset,start,end,**extra):
        return media_row(id,asset,start,end,x=0.,y=0.,w=1.,h=1.,fit="cover",fade_in=0.,fade_out=0.,
                         source_start=0.,track_id=T,**extra)
    # Non-chronological storage must not give the outgoing picture an extra frame.
    p["manual"].update(media_clips=[row("2",IMAGE,1.5,2.75,audio_enabled=False),row("1",VIDEO,.25,1.5,speed=.5,video_source_start=0.,audio_enabled=True)],
                       layer_tracks={"version":1,"tracks":[{"kind":"visual","name":"Picture","id":T}]},
                       audio_mixer={"source_muted":True})
    seam=round(1.5*fps)+direction*2
    apply_manual_edit(p,{"action":"media_roll","left_id":L,"right_id":R,"frame":seam})
    output=native_export(p,media,tmp_path)
    raw=subprocess.check_output([media[1],"-v","error","-i",str(output),"-an","-vf","scale=2:2:flags=neighbor","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],timeout=15)
    assert len(raw)==3*fps*12
    for f in range(seam-4,seam+5):
        r,g,b=raw[f*12:f*12+3]
        assert r>160 and b<60 and (g<60 if f<seam else g>180), (fps,seam,f,(r,g,b))


@pytest.mark.parametrize("normalize",[False,True])
def test_marked_output_finishes_inside_a_source_gap_with_adjacent_av_shots(media,tmp_path,normalize,monkeypatch):
    # An early trim of both mapped streams used to stall FFmpeg's split/concat
    # scheduler here. The test times out its own render, not the pytest process.
    p=project();p["draft"]["output_duration"]=3.;p["settings"]["fps"]=30
    a,b="asset_"+"1"*32,"asset_"+"2"*32
    p["assets"]={k:{"id":k,"kind":"video","status":"ready","path":"source.mp4","width":160,"height":90,"has_audio":True,"duration":3.} for k in (a,b)}
    def shot(id,asset,start,end,src,pic,speed):
        return media_row(id,asset,start,end,x=0.,y=0.,w=1.,h=1.,fit="cover",fade_in=0.,fade_out=0.,
                         source_start=src,video_source_start=pic,speed=speed,track_id=T)
    p["manual"].update(sequence={"version":1,"duration":9.,"camera_plan":[{"start":0.,"end":9.,"camera":"A"}],"base_source_tracks":None},
        source_tracks={"A":[{"id":"A:first","start":0.,"end":1.,"source_start":0.},{"id":"A:last","start":4.,"end":6.,"source_start":1.}],"B":[]},
        media_clips=[shot("2",b,1.8,2.8,1.1,1.4,.5),shot("1",a,.8,1.8,.1,.25,1.5)],
        audio_mixer={"source_muted":True},layer_tracks={"version":1,"tracks":[{"kind":"visual","name":"Story","id":T}]})
    apply_manual_edit(p,{"action":"media_roll","left_id":L,"right_id":R,"frame":61})
    stages=[]
    if normalize:
        import cutroom.render as renderer
        original_runner=renderer._run_ffmpeg_process
        def capture_stage(ctx,cmd,duration):
            if "-i" in cmd and str(cmd[cmd.index("-i")+1]).endswith(".render-stage.mov"):
                pcm=subprocess.check_output([media[1],"-v","error","-i",cmd[cmd.index("-i")+1],"-map","0:a:0","-c:a","copy","-f","s24le","pipe:1"],timeout=15)
                stages.append((len(pcm),hashlib.sha256(pcm).digest()))
            return original_runner(ctx,cmd,duration)
        monkeypatch.setattr(renderer,"_run_ffmpeg_process",capture_stage)
        native_export(p,media,tmp_path/"whole",normalize=True)
    path=native_export(p,media,tmp_path/"excerpt",(35,80),normalize)
    if normalize:
        assert len(stages)==2 and stages[0]==stages[1] and stages[1][0]==9*48000*2*3
    raw=subprocess.check_output([media[1],"-v","error","-i",str(path),"-an","-vf","scale=2:2","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],timeout=12)
    assert len(raw)==45*12
    ac=subprocess.check_output([media[1],"-v","error","-i",str(path),"-vn","-ac","1","-f","s16le","pipe:1"],timeout=12)
    assert len(ac)>=48_000*2 and any(ac)

