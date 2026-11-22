"""Real revision-locked HTTP lift, preserved phases, and atomic shared history."""
import copy, hashlib, math
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.track_lift import lift_window
from test_media_append import library_api, content  # noqa:F401
from test_media_insert import unlocked  # noqa:F401
from test_mixed_media_insert import VIDEO, IMAGE, post
from test_track_overwrite import arrange
from test_rolling_edit import L, T, U


def lift(api, **extra):
    return post(api, "media_track_lift", **{"track_id":T,"start_frame":105,"end_frame":204,**extra})


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("mode",["across","whole motion","split","left","right","still","all"])
def test_real_lift_is_nonripple_and_undo_redo_restore_every_other_layer(unlocked,fps,mode):
    _,_,store,pid=unlocked
    def setup(p):
        arrange(p);p["settings"]["fps"]=fps
        if mode in ("split","still"):
            r,m,o,l=p["manual"]["media_clips"]
            l.update(start=2.01234567891,end=8.7890123456,source_start=.2,video_source_start=1.126,speed=1.5,fade_in=.13,fade_out=.22,enabled=False)
            if mode=="still":l.update(asset_id=IMAGE,source_start=0.,speed=1.,audio_enabled=False);l.pop("video_source_start")
            p["manual"]["media_clips"]=[o,l]
    store.update(pid,setup);before=store.load(pid);old=before["manual"]
    root=store.project_dir(pid)/"media"
    hashes=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob("*") if f.is_file()}
    saved=hashes();begin,end={"across":(3.5,6.8),"whole motion":(4,6),"split":(4.25,5.5),"still":(4.25,5.5),"left":(3,4),"right":(6,6.5),"all":(0,15)}[mode]
    first,last=round(begin*fps),round(end*fps);begin,end=round(first/fps,9),round(last/fps,9)
    res=lift(unlocked,start_frame=first,end_frame=last);assert res.status_code==200,res.get_json()
    after=store.load(pid);rows=list(after["manual"]["media_clips"]);ids={r["id"] for r in old["media_clips"]}
    for original in old["media_clips"]:
        if original["track_id"]!=T or original["end"]<=begin or original["start"]>=end:
            assert rows.pop(0)==original;continue
        left=original["start"]<begin
        if left:assert rows.pop(0)=={**original,"end":begin,"fade_out":0}
        if original["end"]>end:
            got=rows.pop(0);want={**original,"start":end,"fade_in":0}
            if left:assert got["id"] not in ids;ids.add(got["id"]);want["id"]=got["id"]
            if before["assets"][original["asset_id"]]["kind"]=="video":
                elapsed=end-original["start"];want.update(source_start=round(original["source_start"]+elapsed,9),video_source_start=round(original.get("video_source_start",original["source_start"])+elapsed*original["speed"],9))
            assert got==want
    assert not rows
    assert after["revision"]==before["revision"]+1
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for k,v in old.items():
        if k not in ("media_clips","history","_history"):assert after["manual"][k]==v
    for k in ("assets","sources","settings","analysis","exports","review_markers"):assert after.get(k)==before.get(k)
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(store.load(pid))==content(after)
    assert hashes()==saved


@pytest.mark.parametrize("reason",["auto","audio","text","locked","legacy","empty","missing first","missing last","boolean first","boolean last","str first","fractional last","negative","reverse","equal","past end","short","fps","stale","no revision","extra","partial motion","left fade","right fade","small left","small right","missing original","missing preview","not ready","invalid source clock","clip cap"])
def test_refused_lift_preserves_exact_file_and_history(unlocked,reason):
    _,client,store,pid=unlocked
    def setup(p):
        arrange(p);m=p["manual"];r,mid,o,l=m["media_clips"]
        if reason=="locked":m["layer_tracks"]["tracks"][0]["locked"]=True
        if reason=="audio":m["layer_tracks"]["tracks"].append({"id":"track_"+"0"*32,"kind":"audio","name":"Audio","locked":False})
        if reason=="legacy":
            m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id")
        if reason=="partial motion":l["motion"]="pan"
        if reason=="left fade":l["fade_out"]=.8
        if reason=="right fade":r["fade_in"]=1.5
        if reason=="small left":l.update(start=3.46,fade_in=0)
        if reason=="small right":r.update(end=6.84,fade_out=0)
        if reason in ("missing original","missing preview"):p["assets"][VIDEO]["path" if reason.endswith("original") else "preview_path"]="media/assets/missing-original.mp4"
        if reason=="not ready":p["assets"][VIDEO]["status"]="waiting"
        if reason=="invalid source clock":l["source_start"]=999
        if reason=="fps":p["settings"]["fps"]=29.97
        if reason=="clip cap":
            l.update(start=2.,end=9.,fade_in=0.,fade_out=0.);m["media_clips"]=[l]
            for i in range(199):
                tid="track_"+format(i+100000,"032x");m["layer_tracks"]["tracks"].append({"id":tid,"kind":"visual","name":str(i),"locked":False})
                m["media_clips"].append({**o,"id":"media_"+format(i+100000,"032x"),"track_id":tid})
    store.update(pid,setup);p=store.load(pid)
    args={"action":"media_track_lift","track_id":T,"start_frame":105,"end_frame":204,"expected_revision":p["revision"]}
    args.update({"auto":{"track_id":""},"audio":{"track_id":"track_"+"0"*32},"text":{"track_id":"track_"+"c"*32},"empty":{"start_frame":300,"end_frame":330},"boolean first":{"start_frame":True},"boolean last":{"end_frame":True},"str first":{"start_frame":"105"},"fractional last":{"end_frame":204.5},"negative":{"start_frame":-1},"reverse":{"start_frame":205},"equal":{"end_frame":105},"past end":{"end_frame":9999},"short":{"end_frame":106},"stale":{"expected_revision":p["revision"]-1},"extra":{"ripple":True}}.get(reason,{}))
    for label,key in [("missing first","start_frame"),("missing last","end_frame"),("no revision","expected_revision")]:
        if reason==label:args.pop(key)
    raw=store.state_path(pid).read_bytes();response=client.post(f"/api/projects/{pid}/manual/edit",json=args)
    assert response.status_code in (400,409),response.get_json()
    assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("fps",[24,25,30,50,60])
def test_frame_window_boundaries_and_end_exclusive(fps):
    p={"settings":{"fps":fps}}
    n=103;end=round(n/fps,9)
    assert lift_window(p,{"start_frame":0,"end_frame":n},end)==(0,end)
    with pytest.raises(ValueError):lift_window(p,{"start_frame":0,"end_frame":n+1},end)
    with pytest.raises(ValueError):lift_window(p,{"start_frame":0,"end_frame":n},end-.0001)
    with pytest.raises(ValueError):lift_window(p,{"start_frame":0,"end_frame":1},15)


def test_lift_does_not_remove_touching_neighbors_and_empty_lift_is_not_an_undo(unlocked):
    _,_,store,pid=unlocked;store.update(pid,arrange);old=store.load(pid)["manual"]["media_clips"]
    assert lift(unlocked,start_frame=120,end_frame=180).status_code==200
    rows=store.load(pid)["manual"]["media_clips"];assert rows==[old[0],old[2],old[3]]
    raw=store.state_path(pid).read_bytes();assert lift(unlocked,start_frame=120,end_frame=180).status_code==400
    assert store.state_path(pid).read_bytes()==raw
