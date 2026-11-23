"""Single-track, fixed-duration three-point overwrite: source clocks, retained IDs, and atomic Undo."""
import copy
import hashlib
import pytest
from cutroom.projects import ProjectStore
from test_media_append import library_api, content  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_mixed_media_insert import VIDEO,IMAGE,AUDIO,post
from test_slide_edit import M,triplet
from test_rolling_edit import L,R,T,U
from test_replace_take import NEW


def arrange(p):
    triplet(p);r,mid,other,l=p["manual"]["media_clips"]
    l.update(start=2.,end=4.,fade_in=.15,fade_out=0.)
    mid.update(start=4.,end=6.,motion="pan",fade_in=.15,fade_out=.25)
    r.update(start=6.,end=9.,enabled=False)
    p["assets"][NEW]={**p["assets"][VIDEO],"id":NEW,"name":"Overwrite source"}
    return p


def overwrite(api,**extra):
    return post(api,"media_track_overwrite",**{"track_id":T,"asset_id":NEW,"frame":105,"source_start":.425,"source_end":3.675,**extra})


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("mode",["intersect","exact","gap","bisect","one-left","one-right"])
def test_only_one_lane_changes_and_original_cells_can_be_restored_atomically(unlocked,fps,mode):
    app,_,store,pid=unlocked
    def setup(p):
        arrange(p);p["settings"]["fps"]=fps
        if mode=="bisect":
            m=p["manual"];r,mid,other,l=m["media_clips"];m["media_clips"]=[other,l];l.update(start=2.01234567891,end=8.7890123456,speed=1.5,source_start=.2,video_source_start=1.126,fade_in=.13,fade_out=.22)
    store.update(pid,setup);before=store.load(pid);m=before["manual"];root=store.project_dir(pid)/"media"
    hashes=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    old=hashes();sec,span={"intersect":(3.5,3.25),"exact":(4.,2.),"gap":(9.25,1.),"bisect":(4.25,1.25),"one-left":(3.,1.),"one-right":(6.,.5)}[mode]
    frame=round(sec*fps);beg=round(frame/fps,9);span=round(span*fps)/fps if mode!="exact" else span;src=.425
    res=overwrite(unlocked,frame=frame,source_start=src,source_end=src+span);assert res.status_code==200,res.get_json()
    done=store.load(pid);rows=done["manual"]["media_clips"];placed=rows[-1];ids={r["id"] for r in m["media_clips"]};end=round((frame+round(span*fps))/fps,9)
    assert placed["id"] not in ids and (placed["start"],placed["end"],placed["source_start"],placed["video_source_start"])==(beg,end,src,src)
    assert placed["track_id"]==T and placed["asset_id"]==NEW and placed["speed"]==1 and placed["audio_enabled"]
    tail=list(rows[:-1])
    for original in m["media_clips"]:
        if original["track_id"]!=T or original["end"]<=beg or original["start"]>=end:
            assert tail.pop(0)==original;continue
        left=original["start"]<beg
        if left:assert tail.pop(0)=={**original,"end":beg,"fade_out":0}
        if original["end"]>end:
            row=tail.pop(0);elapsed=end-original["start"];expected={**original,"start":end,"fade_in":0}
            if left:assert row["id"] not in ids|{placed["id"]};expected["id"]=row["id"]
            expected.update(source_start=round(original["source_start"]+elapsed,9),video_source_start=round(original["video_source_start"]+elapsed*original["speed"],9))
            for k in ["source_start","video_source_start"]:assert abs(row[k]-expected[k])<1.1e-9;expected[k]=row[k]
            assert row==expected
    assert tail==[] and done["revision"]==before["revision"]+1 and done["manual"]["history"]=={"undo_count":1,"redo_count":0}
    assert all(done["manual"][k]==v for k,v in m.items() if k not in ("media_clips","_history","history"))
    for k in ("settings","sources","assets","analysis","exports","review_markers"):assert done.get(k)==before.get(k)
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(done) and hashes()==old


@pytest.mark.parametrize("reason",["auto","audio","text","locked","no model","unknown asset","nonvideo","offline","attached unknown","bad duration","bad source","bad frame","fraction","negative","past edit","extend","missing in","missing out","reversed","short","beyond","bool in","str out",
    "full-list split","small left","small right","left fade-in","left fade-out","right fade-in","right fade-out","partial left motion","partial right motion","missing incoming","missing cut original","missing cut preview","not ready cut","no revision","stale","extra"])
def test_rejected_overwrite_changes_no_state_or_media_history(unlocked,reason):
    _,client,store,pid=unlocked
    def setup(p):
        arrange(p);m=p["manual"];r,mid,o,l=m["media_clips"];a=p["assets"][NEW]
        if reason=="audio":m["layer_tracks"]["tracks"].append({"id":"track_"+"0"*32,"name":"Audio destination","kind":"audio","locked":False})
        if reason=="locked":m["layer_tracks"]["tracks"][0]["locked"]=True
        if reason=="no model":
            m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id")
        if reason=="offline":a["status"]="waiting"
        if reason=="attached unknown":a.pop("has_audio")
        if reason=="bad duration":a["duration"]=0
        if reason=="small left":l["start"]=3.46;l["fade_in"]=0
        if reason=="small right":r["end"]=6.79;r["fade_out"]=0
        if reason=="left fade-in":l["fade_in"]=1.75
        if reason=="left fade-out":l["fade_out"]=.75
        if reason=="right fade-in":r["fade_in"]=1.
        if reason=="right fade-out":r["fade_out"]=2.5
        if reason=="partial left motion":l["motion"]="pan"
        if reason=="partial right motion":r["motion"]="zoom_in"
        if reason=="missing incoming":a["path"]="media/assets/not-present.mp4"
        if reason in ("missing cut original","missing cut preview","not ready cut"):
            v=p["assets"][VIDEO]
            if reason=="not ready cut":v["status"]="waiting"
            else:v["path" if reason.endswith("original") else "preview_path"]="media/assets/not-present.mp4"
        if reason=="full-list split":
            m["media_clips"]=[l];l.update(start=2.,end=8.5)
            # 199 unrelated tiny clips on their own explicit occupied tracks.
            others=[]
            for i in range(199):
                tid="track_"+format(i+100000,'032x');m["layer_tracks"]["tracks"].append({"id":tid,"kind":"visual","name":str(i),"locked":False})
                others.append({**o,"id":"media_"+format(i+100000,'032x'),"track_id":tid})
            m["media_clips"]+=others
    store.update(pid,setup);v=store.load(pid);d={"action":"media_track_overwrite","track_id":T,"asset_id":NEW,"frame":105,"source_start":.425,"source_end":3.675,"expected_revision":v["revision"]}
    changes={"auto":{"track_id":""},"audio":{"track_id":"track_"+"0"*32},"text":{"track_id":"track_"+"c"*32},"unknown asset":{"asset_id":"asset_"+"0"*32},"nonvideo":{"asset_id":IMAGE},"bad source":{"asset_id":[]},"bad frame":{"frame":True},"fraction":{"frame":10.25},"negative":{"frame":-1},"past edit":{"frame":99999},"extend":{"frame":int(v["manual"]["sequence"]["duration"]*30)-3},"reversed":{"source_end":.2},"short":{"source_end":.45},"beyond":{"source_end":99},"bool in":{"source_start":False},"str out":{"source_end":"1.2"},"stale":{"expected_revision":v["revision"]-1},"extra":{"ripple":True}}
    d.update(changes.get(reason,{}))
    for label,key in (("no revision","expected_revision"),("missing in","source_start"),("missing out","source_end")):
        if reason==label:d.pop(key)
    raw=store.state_path(pid).read_bytes();res=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert res.status_code in {400,409},res.get_json();assert store.state_path(pid).read_bytes()==raw


def test_still_right_remainder_has_no_fabricated_source_clocks(unlocked):
    _,_,store,pid=unlocked
    def setup(p):
        arrange(p);r,m,o,l=p["manual"]["media_clips"];p["manual"]["media_clips"]=[o,{**o,"id":L,"track_id":T,"start":2.3,"end":9.4,"motion":"none","source_start":0.}]
    store.update(pid,setup);pre=store.load(pid)["manual"]["media_clips"][1];assert overwrite(unlocked).status_code==200
    other,left,right,shot=store.load(pid)["manual"]["media_clips"];assert left["id"]==pre["id"] and right["id"]!=left["id"] and right["source_start"]==0.
    assert ("video_source_start" in right)==("video_source_start" in pre)
