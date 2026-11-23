"""Atomic three-occurrence slides on the edit clock (original media remains untouched)."""
import copy, hashlib
import pytest
from cutroom.projects import ProjectStore
from test_media_append import library_api, content  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_mixed_media_insert import VIDEO, AUDIO, IMAGE, media_row, post
from test_rolling_edit import L, R, T, U, setup

M="media_"+"4"*32


def triplet(p,kinds=(VIDEO,VIDEO,VIDEO)):
    a,b,c=kinds;setup(p,a,c);m=p["manual"];right,_,left=m["media_clips"]
    right.update(start=6.5,end=8.5)
    mid=media_row("4",b,5.,6.5,source_start=1.75,video_source_start=2.25,speed=2. if b==VIDEO else 1.,
                  volume_db=-3.5,fade_in=.12,fade_out=.18,motion="none" if b==AUDIO else "pan",track_id=T)
    m["media_clips"].insert(1,mid)
    return p


def slide(api,f,**changes):
    return post(api,"media_slide",**{"left_id":L,"clip_id":M,"right_id":R,"frame":f,**changes})


@pytest.mark.parametrize("kinds",[(VIDEO,VIDEO,VIDEO),(IMAGE,VIDEO,IMAGE),(VIDEO,IMAGE,VIDEO),(AUDIO,AUDIO,AUDIO)])
@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("n",[-8,11])
def test_center_content_moves_intact_but_neighbors_keep_outside_clocks(unlocked,kinds,fps,n):
    app,_,store,pid=unlocked
    def arrange(p):triplet(p,kinds);p["settings"]["fps"]=fps
    store.update(pid,arrange);before=store.load(pid);root=store.project_dir(pid)/"media"
    hash_files=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    orig=hash_files();f=5*fps+n;target=round(f/fps,9)
    end=round((f+round(1.5*fps))/fps,9) if (1.5*fps).is_integer() else target+1.5
    answer=slide(unlocked,f);assert answer.status_code==200,answer.get_json()
    after=store.load(pid);expected=copy.deepcopy(before["manual"]["media_clips"]);r,m,other,l=expected
    m["start"]=l["end"]=target;m["end"]=r["start"]=end
    if kinds[2]!=IMAGE:r["source_start"]=round(2+end-6.5,9)
    if kinds[2]==VIDEO:r["video_source_start"]=round(3+(end-6.5)*.5,9)
    assert after["manual"]["media_clips"]==expected
    for key in ("sources","assets","settings","analysis","review_markers"):assert before.get(key)==after.get(key)
    assert before["manual"].keys()-{"_history","history"}==after["manual"].keys()-{"_history","history"}
    for key,val in before["manual"].items():
        if key not in {"_history","history","media_clips"}:assert after["manual"][key]==val
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0} and after["revision"]==before["revision"]+1
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after) and hash_files()==orig


@pytest.mark.parametrize("why",["left gap","right gap","tiny","other track","locked","no tracks","flip","duplicate","unknown","missing middle",
    "left motion","right motion","left fade","right fade","outer left","outer right","left media","left picture","right media","right picture",
    "right hold","short left","short right","negative","float","bool","extra","no revision","stale","missing source","missing preview"])
def test_refuse_whole_slide_and_save_nothing(unlocked,why):
    _,client,store,pid=unlocked
    def arrange(p):
        triplet(p,(VIDEO,IMAGE,VIDEO) if why.startswith("missing ") and why!="missing middle" else (VIDEO,VIDEO,VIDEO));m=p["manual"];r,c,_,l=m["media_clips"]
        if why=="left gap":c["start"]+=.01
        if why=="right gap":r["start"]+=.01
        if why=="tiny":c["start"]+=1e-10
        if why=="other track":r["track_id"]=U
        if why=="locked":m["layer_tracks"]["tracks"][0]["locked"]=True
        if why=="no tracks":
            m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id")
        if why=="left motion":l["motion"]="zoom_in"
        if why=="right motion":r["motion"]="pan"
        if why=="left fade":l["fade_out"]=.05
        if why=="right fade":r["fade_in"]=.05
        if why=="outer left":l["fade_in"]=1.91
        if why=="outer right":r["fade_out"]=1.95
        if why=="left media":l["source_start"]=18.
        if why=="left picture":l["video_source_start"]=17.
        if why=="right media":r["source_start"]=.01
        if why=="right picture":r["video_source_start"]=.01
        if why=="right hold":r["video_source_start"]=21.
        if why=="missing source":p["assets"][IMAGE]["path"]="media/assets/missing.mp4"
        if why=="missing preview":p["assets"][IMAGE]["preview_path"]="media/assets/missing-proxy.mp4"
    store.update(pid,arrange);v=store.load(pid);raw=store.state_path(pid).read_bytes()
    frame=145 if why in {"outer left","right media","right picture","right hold"} else 159
    d={"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":frame,"expected_revision":v["revision"]}
    if why=="flip":d["left_id"],d["right_id"]=R,L
    if why=="duplicate":d["clip_id"]=d["left_id"]
    if why=="unknown":d["clip_id"]="media_"+"f"*32
    if why=="missing middle":d.pop("clip_id")
    if why in ("short left","short right","negative","float","bool"):d["frame"]={"short left":92,"short right":208,"negative":-1,"float":150.5,"bool":True}[why]
    if why=="extra":d["offset"]=1
    if why=="no revision":d.pop("expected_revision")
    if why=="stale":d["expected_revision"]-=1
    res=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert res.status_code==(409 if why in ("stale","missing source","missing preview") else 400),res.get_json()
    assert store.state_path(pid).read_bytes()==raw


def test_noop_keeps_exact_revision_state_disk_and_disabled_middle_can_slide(unlocked):
    _,_,store,pid=unlocked
    def arrange(p):triplet(p);p["manual"]["media_clips"][1]["enabled"]=False
    store.update(pid,arrange);before=store.state_path(pid).read_bytes()
    assert slide(unlocked,150).status_code==200 and store.state_path(pid).read_bytes()==before
    assert slide(unlocked,157).status_code==200 and store.load(pid)["manual"]["media_clips"][1]["enabled"] is False


@pytest.mark.parametrize("start,end,frame,draw_end",[(5.033333333,5.366666667,152,5.4),(5.,5.333333333,151,5.366666667),(5.01234567891,6.12567891237,153,None)])
def test_rational_duration_stays_exactly_on_frame_but_legacy_subframe_length_is_preserved(unlocked,start,end,frame,draw_end):
    _,_,store,pid=unlocked
    def arrange(p):
        triplet(p);r,m,_,l=p["manual"]["media_clips"];m["start"]=l["end"]=start;r["start"]=m["end"]=end;m["fade_in"]=m["fade_out"]=0.
    store.update(pid,arrange);res=slide(unlocked,frame);assert res.status_code==200,res.get_json();r,m,_,l=store.load(pid)["manual"]["media_clips"]
    assert r["start"]==m["end"] and l["end"]==m["start"]
    if draw_end is not None:assert r["start"]==draw_end and m["start"]==round(frame/30,9)
    else:
        assert m["start"]==start+2/30 and m["end"]==end+2/30
        assert abs((m["end"]-m["start"])-(end-start))<1e-14
