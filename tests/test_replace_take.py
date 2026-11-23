"""Replacing an occurrence must never rebind a file, ripple, or split shared history."""
import copy
import hashlib
import pytest
from cutroom.projects import ProjectStore
from test_media_append import library_api, content  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_mixed_media_insert import VIDEO, AUDIO, IMAGE, post
from test_slide_edit import triplet, slide, M
from test_rolling_edit import T

NEW = "asset_" + "8"*32


def arrange(p, kind=VIDEO):
    triplet(p,(kind, kind, kind))
    p["assets"][NEW] = {**p["assets"][kind], "id":NEW,"name":"An alternate take"}
    # A genuine repeated reference on the same and a locked track. It stays
    # bound to the old/new files without either shared file being touched.
    other=p["manual"]["media_clips"][2]
    if kind!=AUDIO: other["asset_id"]=NEW
    else: other["asset_id"]=IMAGE
    return p


def replace(api, kind=VIDEO, **extra):
    d={"clip_id":M,"previous_asset_id":kind,"asset_id":NEW}
    if kind!=IMAGE:d["source_start"]=.5555555555
    return post(api,"media_replace_take",**{**d,**extra})


@pytest.mark.parametrize("kind",[VIDEO,AUDIO,IMAGE])
@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("legacy",[False,True])
def test_exactly_one_selected_take_keeps_edges_motion_sound_and_complete_undo(unlocked,kind,fps,legacy):
    app,_,store,pid=unlocked
    def setup(p):
        arrange(p,kind);p["settings"]["fps"]=fps;m=p["manual"];r,c,_,l=m["media_clips"];l["end"]=c["start"]=5.01234567891;c["end"]=r["start"]=6.52345678912
        c.update(muted=True,enabled=False,role="effects",fit="contain",w=.75,x=.125,volume_db=-6.2)
        if legacy:
            m.pop("layer_tracks")
            for row in m["text_clips"]+m["media_clips"]:row.pop("track_id")
    store.update(pid,setup)
    before=store.load(pid);root=store.project_dir(pid)/"media"
    hashes=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    old=hashes();r=replace(unlocked,kind);assert r.status_code==200,r.get_json()
    after=store.load(pid);assert after["revision"]==before["revision"]+1
    expected=copy.deepcopy(before["manual"]["media_clips"]);patch={"asset_id":NEW}
    if kind!=IMAGE:patch["source_start"]=.555555556
    if kind==VIDEO:patch["video_source_start"]=.555555556
    expected[1].update(patch);assert after["manual"]["media_clips"]==expected
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for k,v in before["manual"].items():
        if k not in {"_history","history","media_clips"}:assert after["manual"][k]==v
    for k in ("sources","assets","settings","analysis","exports","review_markers"):assert before.get(k)==after.get(k)
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert old==hashes()


def test_after_three_shot_slide_replace_and_each_undo_is_one_step(unlocked):
    _,_,store,pid=unlocked;store.update(pid,arrange);v=store.load(pid)
    assert slide(unlocked,161).status_code==200;rolled=store.load(pid)
    take=replace(unlocked,source_start=2.125,source_end=5.125);assert take.status_code==200,take.get_json()
    done=store.load(pid);assert done["manual"]["history"]["undo_count"]==2
    assert (done["manual"]["media_clips"][1]["start"],done["manual"]["media_clips"][1]["end"])==(5.366666667,6.866666667)
    for old,new in zip(rolled["manual"]["media_clips"],done["manual"]["media_clips"]):
        assert new==({**old,"asset_id":NEW,"source_start":2.125,"video_source_start":2.125} if old["id"]==M else old)
    for expected in (rolled,v):assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(expected)


@pytest.mark.parametrize("why",["missing clip","duplicate selection","old mismatch","same file","invalid id","unknown file","not ready","old not ready","wrong kind","locked",
    "new silent","old silent","unknown sound","new keyed","old keyed","absent in","extra field","in string","in bool","negative in","past eof",
    "empty range","out beyond","out bool","short normal","short picture","short source","old missing original","old missing proxy","new missing original","new missing proxy",
    "no revision","stale","still with clock","invalid duration"])
def test_blocked_or_stale_writes_no_project_byte_or_history(unlocked,why):
    _,client,store,pid=unlocked;kind=IMAGE if why=="still with clock" else VIDEO
    def init(p):
        arrange(p,kind);asset=p["assets"][NEW];old=p["assets"][kind]
        if why=="duplicate selection":
            # Legacy untracked state can represent duplicate occurrence IDs;
            # modern saved tracks already reject these at ProjectStore.save.
            p["manual"].pop("layer_tracks")
            for row in p["manual"]["media_clips"]+p["manual"]["text_clips"]:row.pop("track_id")
            p["manual"]["media_clips"].append(copy.deepcopy(p["manual"]["media_clips"][1]))
        if why=="not ready":asset["status"]="waiting"
        if why=="old not ready":old["status"]="waiting"
        if why=="wrong kind":asset["kind"]="image"
        if why=="locked":p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True
        if why=="new silent":asset["has_audio"]=False
        if why=="old silent":old["has_audio"]=False
        if why=="unknown sound":asset.pop("has_audio")
        if why in ("old keyed","new keyed"):p["manual"]["chroma_key"]={kind if why=="old keyed" else NEW:{"enabled":True}}
        if why=="short source":asset["duration"]=2.1
        if why=="invalid duration":asset["duration"]=0
        if "missing original" in why or "missing proxy" in why:
            a=old if why.startswith("old") else asset;a["path" if "original" in why else "preview_path"]="media/assets/not-present.mp4"
    store.update(pid,init);p=store.load(pid);d={"action":"media_replace_take","clip_id":M,"previous_asset_id":kind,"asset_id":NEW,"source_start":.5,"expected_revision":p["revision"]}
    if why=="missing clip":d.pop("clip_id")
    if why=="old mismatch":d["previous_asset_id"]=NEW
    if why=="same file":d["asset_id"]=kind
    if why=="invalid id":d["asset_id"]=[]
    if why=="unknown file":d["asset_id"]="asset_"+"f"*32
    if why=="absent in":d.pop("source_start")
    if why=="extra field":d["speed"]=1
    if why=="no revision":d.pop("expected_revision")
    if why=="stale":d["expected_revision"]-=1
    for label,v in [("in string","1"),("in bool",True),("negative in",-.00000000001),("past eof",20.1)]:
        if why==label:d["source_start"]=v
    for label,v in [("empty range",.5),("out beyond",20.5),("out bool",False),("short normal",1.3),("short picture",3.49)]:
        if why==label:d["source_end"]=v
    before=store.state_path(pid).read_bytes();res=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert res.status_code in {400,409},res.get_json();assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("incoming",[False,True])
def test_explicit_video_sound_off_permits_mixed_stream_availability_without_enabling_anything(unlocked,incoming):
    _,_,store,pid=unlocked
    def init(p):
        arrange(p);p["assets"][VIDEO]["has_audio"]=not incoming;p["assets"][NEW]["has_audio"]=incoming;p["manual"]["media_clips"][1]["audio_enabled"]=False
    store.update(pid,init)
    assert replace(unlocked).status_code==200 and store.load(pid)["manual"]["media_clips"][1]["audio_enabled"] is False
