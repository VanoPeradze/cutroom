"""Atomic mixed selection split and verification receipt, including raw styles."""
import copy,hashlib
import pytest
from cutroom.editing import apply_manual_edit,ManualEditError
from cutroom.group_split import prepare_group_split,group_split_receipt
from test_media_append import library_api,content
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers,media_row,text_row,VIDEO,AUDIO,IMAGE,post
from test_rolling_edit import T,U

V="media_"+"1"*32
A="media_"+"2"*32
I="media_"+"3"*32
X="text_"+"1"*32
IDS=[V,A,I,X]


def arrange(p,tracked=True):
    mixed_layers(p)
    p["manual"].update(media_clips=[
        media_row("1",VIDEO,2.123456789,8.123456789,source_start=.4,video_source_start=.3,speed=1.75,fade_in=.15,fade_out=.2,opacity_percent=37,track_id=T,enabled=False),
        media_row("2",AUDIO,1.3,7.75,source_start=.23,fade_in=.3,fade_out=.4,track_id=U,role="music"),
        media_row("3",IMAGE,2.,7.,source_start=0.,fade_in=0.,fade_out=0.,track_id="track_"+"c"*32),
        media_row("4",VIDEO,9.,10.,source_start=0.,track_id=T)],
        text_clips=[text_row("1",2.123456789,8.123456789,track_id="track_"+"d"*32),text_row("2",10.,11.,track_id="track_"+"d"*32)],
        track_locks={"A":True,"B":True},
        layer_tracks={"version":2,"tracks":[{"id":T,"kind":"visual","name":"Video","locked":False},{"id":U,"kind":"audio","name":"Sound","locked":False},{"id":"track_"+"c"*32,"kind":"visual","name":"Image","locked":False},{"id":"track_"+"d"*32,"kind":"text","name":"Title","locked":False}]})
    if not tracked:
        p["manual"].pop("layer_tracks")
        for key in ("media_clips","text_clips"):
            for row in p["manual"][key]:row.pop("track_id")
    return p


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("tracked",[False,True])
def test_mixed_split_receipt_raw_parity_and_atomic_history(unlocked,fps,tracked):
    _,_,store,pid=unlocked
    def setup(p):arrange(p,tracked);p["settings"]["fps"]=fps
    store.update(pid,setup);before=store.load(pid);frame=4*fps+2;seam=round(frame/fps,9)
    root=store.project_dir(pid)/"media";hashes=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    original=hashes();response=post(unlocked,"layers_split",clip_ids=list(reversed(IDS)),frame=frame);assert response.status_code==200,response.get_json()
    after=store.load(pid);receipt=response.get_json()["created"];assert [r["source_id"] for r in receipt]==IDS
    mapping={r["source_id"]:r["clip_id"] for r in receipt};assert len(set(mapping.values()))==4
    for key in ("media_clips","text_clips"):
        actual=iter(after["manual"][key])
        for old in before["manual"][key]:
            left=next(actual)
            if old["id"] not in IDS:assert left==old;continue
            right=next(actual);a={**old,"end":seam};b={**old,"id":mapping[old["id"]],"start":seam}
            if key=="media_clips":
                a["fade_out"]=0;b["fade_in"]=0;kind=before["assets"][old["asset_id"]]["kind"]
                if kind!="image":b["source_start"]=round(old["source_start"]+seam-old["start"],9)
                if kind=="video":b["video_source_start"]=round(old["video_source_start"]+(seam-old["start"])*old["speed"],9)
            assert left==a and right==b
        assert list(actual)==[]
    assert after["revision"]==before["revision"]+1 and after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for k,v in before["manual"].items():
        if k not in ("media_clips","text_clips","history","_history"):assert after["manual"][k]==v
    for k in ("settings","sources","assets","analysis","exports","review_markers"):assert before.get(k)==after.get(k)
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(store.load(pid))==content(after)
    assert hashes()==original


@pytest.mark.parametrize("reason",["single","empty","repeat","unknown","AB","auto caption","wrong type","missing frame","bool","float","string","negative","zero","end","past","fps","locked video","locked audio","locked title","chapter","motion","fade in","fade out","tiny left","tiny right","not crossing","missing source","unready","media cap","text cap","stale","no revision","extra"])
def test_split_rejection_is_byte_atomic(unlocked,reason):
    _,client,store,pid=unlocked
    def setup(p):
        arrange(p);m=p["manual"];v,a,i,other=m["media_clips"]
        if reason.startswith("locked"):
            k={"locked video":0,"locked audio":1,"locked title":3}[reason];m["layer_tracks"]["tracks"][k]["locked"]=True
        if reason=="chapter":m["text_clips"][0]["template"]="chapter"
        if reason=="motion":v["motion"]="pan"
        if reason=="fade in":v["fade_in"]=3.
        if reason=="fade out":v["fade_out"]=5.
        if reason=="tiny left":v.update(start=3.97,fade_in=0.)
        if reason=="tiny right":v.update(end=4.03,fade_out=0.)
        if reason=="not crossing":v.update(start=5.,end=8.)
        if reason=="missing source":
            v["asset_id"]="asset_"+"0"*32;m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id",None)
        if reason=="unready":p["assets"][VIDEO]["status"]="waiting"
        if reason=="fps":p["settings"]["fps"]=29.97
        if reason=="media cap":
            for n in range(196):
                m["media_clips"].append({**other,"id":"media_"+format(n+100,"032x"),"start":10.+n*.02,"end":10.1+n*.02});m["media_clips"][-1].pop("track_id",None)
            m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id",None)
        if reason=="text cap":
            m.pop("layer_tracks")
            for row in m["media_clips"]+m["text_clips"]:row.pop("track_id",None)
            # Extra rows are syntactically valid; the cap rejects before overlap validation.
            for n in range(1998):m["text_clips"].append({**m["text_clips"][-1],"id":"text_"+format(n+100,"032x")})
    store.update(pid,setup);p=store.load(pid)
    d={"action":"layers_split","clip_ids":IDS,"frame":120,"expected_revision":p["revision"]}
    changes={"single":{"clip_ids":[V]},"empty":{"clip_ids":[]},"repeat":{"clip_ids":[V,V]},"unknown":{"clip_ids":[V,"text_"+"0"*32]},"AB":{"clip_ids":[V,"A:0"]},"auto caption":{"clip_ids":[V,"caption:0"]},"wrong type":{"clip_ids":"V"},"bool":{"frame":True},"float":{"frame":120.0},"string":{"frame":"120"},"negative":{"frame":-1},"zero":{"frame":0},"end":{"frame":450},"past":{"frame":9999},"stale":{"expected_revision":p["revision"]-1},"extra":{"time":4.}}
    d.update(changes.get(reason,{}))
    if reason=="missing frame":d.pop("frame")
    if reason=="no revision":d.pop("expected_revision")
    raw=store.state_path(pid).read_bytes();response=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert response.status_code in (400,409),response.get_json()
    assert store.state_path(pid).read_bytes()==raw


def test_corrupt_identity_and_receipt_tampering_are_rejected(unlocked):
    _,_,store,pid=unlocked;store.update(pid,arrange);before=store.load(pid);payload={"action":"layers_split","clip_ids":IDS,"frame":122}
    corrupt=copy.deepcopy(before);corrupt["assets"][VIDEO]["id"]="asset_"+"0"*32
    with pytest.raises(ValueError):prepare_group_split(corrupt,payload)
    after=copy.deepcopy(before);apply_manual_edit(after,payload);receipt=group_split_receipt(before,after,payload);assert len(receipt)==4
    for mode in ("id","sound","appearance","order","unselected","text"):
        bad=copy.deepcopy(after);m=bad["manual"]
        if mode=="id":m["media_clips"][1]["id"]=V
        if mode=="sound":m["media_clips"][1]["source_start"]+=.1
        if mode=="appearance":m["media_clips"][1]["opacity_percent"]=100
        if mode=="order":m["media_clips"][0],m["media_clips"][1]=m["media_clips"][1],m["media_clips"][0]
        if mode=="unselected":m["media_clips"][-1]["volume_db"]=0
        if mode=="text":m["text_clips"][1]["subtext"]="tampered"
        with pytest.raises(ValueError):group_split_receipt(before,bad,payload)


@pytest.mark.parametrize("members",[[V,A],[V,I],[I,X],[X,"text_"+"2"*32]])
def test_visual_audio_and_text_only_subsets_leave_every_unselected_row_raw(unlocked,members):
    _,_,store,pid=unlocked
    def setup(p):
        arrange(p,False)
        p["manual"]["text_clips"][-1].update(start=3.,end=7.)
    store.update(pid,setup);before=store.load(pid)
    response=post(unlocked,"layers_split",clip_ids=members,frame=123);assert response.status_code==200,response.get_json()
    after=store.load(pid);mapping={x["source_id"]:x["clip_id"] for x in response.get_json()["created"]};assert set(mapping)==set(members)
    for key in ("media_clips","text_clips"):
        originals={x["id"]:x for x in before["manual"][key]}
        actual={x["id"]:x for x in after["manual"][key]}
        for ident,row in originals.items():
            if ident not in members:assert actual[ident]==row
            else:assert actual[ident]["end"]==actual[mapping[ident]]["start"]==4.1
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
