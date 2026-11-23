"""Two-sided source handles, invariant outside content and atomic history."""
from __future__ import annotations
import copy, hashlib
import pytest
from cutroom.editing import ManualEditError, apply_manual_edit
from cutroom.projects import ProjectStore
from test_media_append import ASSET, content, library_api  # noqa:F401
from test_media_insert import unlocked  # noqa:F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post

L,R=("media_"+c*32 for c in "12")
T="track_"+"a"*32
U="track_"+"b"*32


def setup(value,a=VIDEO,b=VIDEO):
    mixed_layers(value)
    value["settings"]["fps"]=30
    value["manual"].update(media_clips=[
        media_row("2",b,5.,7.5,source_start=2.,video_source_start=3.,speed=.5 if b==VIDEO else 1.,fade_in=0.,fade_out=.25,track_id=T),
        media_row("3",IMAGE,4.,6.,source_start=0.,audio_enabled=False,fade_in=0.,fade_out=0.,track_id=U),
        media_row("1",a,3.,5.,source_start=1.,video_source_start=2.,speed=1.5 if a==VIDEO else 1.,fade_in=.25,fade_out=0.,track_id=T)],
        text_clips=[text_row("7",4.,7.,track_id="track_"+"c"*32)],
        track_locks={"A":True,"B":True},
        layer_tracks={"version":2,"tracks":[{"id":T,"kind":"audio" if a==AUDIO else "visual","name":"Story","locked":False},
            {"id":U,"kind":"visual","name":"Other","locked":True},{"id":"track_"+"c"*32,"kind":"text","name":"Titles","locked":True}]})
    return value


def roll(api,frame,**payload):
    return post(api,"media_roll",**{"left_id":L,"right_id":R,"frame":frame,**payload})


@pytest.mark.parametrize("a,b",[(VIDEO,VIDEO),(IMAGE,VIDEO),(VIDEO,IMAGE),(IMAGE,IMAGE),(AUDIO,AUDIO)])
@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("delta",[-7,11])
def test_roll_only_changes_seam_and_incoming_source_clocks(unlocked,a,b,fps,delta):
    app,_,store,pid=unlocked
    def init(p):
        setup(p,a,b);p["settings"]["fps"]=fps;p["manual"]["media_clips"][0]["enabled"]=False
    store.update(pid,init)
    before=store.load(pid);root=store.project_dir(pid)/"media"
    digest=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    original=digest();cut=round((5*fps+delta)/fps,9)
    response=roll(unlocked,5*fps+delta)
    assert response.status_code==200,response.get_json()
    after=store.load(pid);expected=copy.deepcopy(before["manual"]["media_clips"])
    expected[2]["end"]=expected[0]["start"]=cut
    if b!=IMAGE:expected[0]["source_start"]=round(2+cut-5,9)
    if b==VIDEO:expected[0]["video_source_start"]=round(3+(cut-5)*.5,9)
    assert after["manual"]["media_clips"]==expected
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for k,v in before["manual"].items():
        if k not in ("media_clips","history","_history"):assert after["manual"][k]==v
    for k in ("assets","sources","settings","analysis"):assert before[k]==after[k]
    assert after["manual"]["sequence"]["duration"]==before["manual"]["sequence"]["duration"]
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert digest()==original


@pytest.mark.parametrize("kind,frame,needle",[
    ("locked",160,"Unlock"),("legacy",160,"editable tracks"),("gap",160,"touch"),("tiny_gap",160,"touch"),("wrong_track",160,"same"),
    ("out_motion",160,"motion"),("in_motion",140,"motion"),("out_seam_fade",140,"fades"),("in_seam_fade",160,"fades"),
    ("outer_fade",94,"outer"),("incoming_outer",218,"outer"),("out_short",91,"0.08"),("in_short",224,"0.08"),
    ("out_media",160,"outgoing source"),("out_picture",160,"outgoing picture"),("in_media",140,"incoming source"),
    ("in_picture",140,"incoming picture"),("in_hold",140,"held frame"),("not_ready",140,"ready"),
    ("invalid_fps",160,"fps"),("unknown_left",160,"no longer"),("flipped",160,"touch"),("same_id",160,"distinct"),
    ("missing_frame",None,"integer"),("bool_frame",True,"integer"),("negative",-2,"integer"),("fractional",150.5,"integer"),
    ("big",10**70,"invalid number"),("nan_id",160,"distinct"),("unknown_field",160,"field"),("no_revision",160,"expected_revision")])
def test_refusals_write_nothing(unlocked,kind,frame,needle):
    _,client,store,pid=unlocked
    def init(p):
        setup(p);m=p["manual"];right,other,left=m["media_clips"]
        if kind=="locked":m["layer_tracks"]["tracks"][0]["locked"]=True
        if kind=="legacy":
            m.pop("layer_tracks")
            for r in m["media_clips"]+m["text_clips"]:r.pop("track_id")
        if kind in ("gap","tiny_gap"):right["start"]+=.001 if kind=="gap" else 1e-10
        if kind=="wrong_track":right["track_id"]=U;other["end"]=4.5
        if kind=="out_motion":left["motion"]="pan"
        if kind=="in_motion":right["motion"]="zoom_in"
        if kind=="out_seam_fade":left["fade_out"]=.1
        if kind=="in_seam_fade":right["fade_in"]=.1
        if kind=="out_media":left["source_start"]=18.
        if kind=="out_picture":left["video_source_start"]=17.
        if kind=="in_media":right["source_start"]=.1
        if kind=="in_picture":right["video_source_start"]=.1
        if kind=="in_hold":right["video_source_start"]=21.
        if kind=="not_ready":p["assets"][VIDEO]["status"]="failed"
        if kind=="invalid_fps":p["settings"]["fps"]=29.97
    store.update(pid,init);raw=store.state_path(pid).read_bytes()
    d={"action":"media_roll","left_id":L,"right_id":R,"frame":frame,"expected_revision":store.load(pid)["revision"]}
    if kind=="unknown_left":d["left_id"]="media_"+"e"*32
    if kind=="flipped":d["left_id"],d["right_id"]=R,L
    if kind=="same_id":d["right_id"]=L
    if kind=="nan_id":d["left_id"]={}
    if kind=="unknown_field":d["force"]=True
    if kind=="no_revision":d.pop("expected_revision")
    response=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert response.status_code==400 and needle.lower() in str(response.get_json()).lower(),response.get_json()
    assert store.state_path(pid).read_bytes()==raw


def test_stale_missing_asset_and_noop_preserve_revision_history_and_exact_bytes(unlocked):
    _,client,store,pid=unlocked;store.update(pid,setup)
    raw=store.state_path(pid).read_bytes();rev=store.load(pid)["revision"]
    assert roll(unlocked,150).status_code==200 and store.state_path(pid).read_bytes()==raw
    ok=roll(unlocked,159);assert ok.status_code==200,ok.get_json()
    raw=store.state_path(pid).read_bytes();d={"action":"media_roll","left_id":L,"right_id":R,"frame":144,"expected_revision":rev}
    stale=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert stale.status_code==409 and store.state_path(pid).read_bytes()==raw
    store.update(pid,lambda p:p["assets"][VIDEO].update(preview_path="media/assets/missing-preview.mp4"))
    raw=store.state_path(pid).read_bytes();res=roll(unlocked,140)
    assert res.status_code==409 and res.get_json()["error"]=="asset_unavailable" and store.state_path(pid).read_bytes()==raw


def test_fractional_seam_preserves_untouched_fields_without_normalizing_legacy_values(unlocked):
    _,_,store,pid=unlocked
    def setup_legacy(p):
        setup(p);right,_,left=p["manual"]["media_clips"];left["end"]=right["start"]=4.9952
        left["x"]=right["x"]=.1234567890123;right.pop("video_source_start")
    store.update(pid,setup_legacy);before=store.load(pid);res=roll(unlocked,151);assert res.status_code==200,res.get_json()
    after=store.load(pid);right,_,left=after["manual"]["media_clips"];assert left["x"]==right["x"]==.1234567890123
    c=round(151/30,9);assert right["video_source_start"]==round(2.+(c-4.9952)*.5,9) and "video_source_start" not in before["manual"]["media_clips"][0]
