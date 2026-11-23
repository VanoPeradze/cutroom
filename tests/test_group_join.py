"""Joining a through edit retains later work, outside timing and source phase."""
import copy,hashlib
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.group_join import prepare_group_join,group_join_receipt
from test_media_append import library_api,content
from test_media_insert import unlocked
from test_mixed_media_insert import post,VIDEO
from test_group_split import arrange,IDS,V,A,I,X
from cutroom.group_split import group_split_receipt


def split_setup(p,tracked=True,fps=30):
    arrange(p,tracked);p["settings"]["fps"]=fps
    before=copy.deepcopy(p);payload={"action":"layers_split","clip_ids":IDS,"frame":4*fps+2}
    apply_manual_edit(p,payload)
    return {r["source_id"]:r["clip_id"] for r in group_split_receipt(before,p,payload)}


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("tracked",[False,True])
@pytest.mark.parametrize("target",[V,A,I,X])
def test_join_does_not_undo_later_work_and_has_one_history_step(unlocked,fps,tracked,target):
    _,_,store,pid=unlocked;mapping={};original={}
    def setup(p):
        arrange(p,tracked);p["settings"]["fps"]=fps;original.update(copy.deepcopy(p))
        mapping.update(split_setup(p,tracked,fps))
    store.update(pid,setup)
    # An unrelated intentional change AFTER splitting must survive Join.
    other="media_"+"4"*32;assert post(unlocked,"media_update",clip_id=other,volume_db=-11).status_code==200
    before=store.load(pid);payload={"action":"layers_join","clip_ids":[mapping[target],target]}
    root=store.project_dir(pid)/"media";digest=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    hashes=digest();response=post(unlocked,"layers_join",clip_ids=payload["clip_ids"]);assert response.status_code==200,response.get_json()
    done=store.load(pid);receipt=group_join_receipt(before,done,payload);assert receipt=={"clip_id":target,"retired_clip_id":mapping[target]}
    key="media_clips" if target.startswith("media_") else "text_clips"
    restored=next(r for r in done["manual"][key] if r["id"]==target)
    assert restored==next(r for r in original["manual"][key] if r["id"]==target)
    for k in ("media_clips","text_clips"):
        expected=[r for r in before["manual"][k] if r["id"] not in {target,mapping[target]}]
        assert [r for r in done["manual"][k] if r["id"]!=target]==expected
    for k,v in before["manual"].items():
        if k not in ("media_clips","text_clips","history","_history"):assert done["manual"][k]==v
    assert done["revision"]==before["revision"]+1 and done["manual"]["history"]["undo_count"]==before["manual"]["history"]["undo_count"]+1
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(store.load(pid))==content(done)
    assert digest()==hashes


@pytest.mark.parametrize("reason",["single","three","duplicate","unknown","AB","gap","overlap","subframe","raw interleave","raw reverse","track","locked","asset","unready","sound","picture","speed","gain","enabled","opacity","crop","fade left","fade right","motion","different text","chapter","caption","mixed","bad id","stale","no revision","extra"])
def test_join_refuses_without_saving_or_consuming_history(unlocked,reason):
    _,client,store,pid=unlocked;mapping={}
    def setup(p):
        mapping.update(split_setup(p));m=p["manual"];rows=m["media_clips"];left,right=rows[:2]
        if reason=="gap":right["start"]+=.1
        if reason=="overlap":right["start"]-=.1;m.pop("layer_tracks");[r.pop("track_id",None) for r in rows+m["text_clips"]]
        if reason=="subframe":left["end"]=right["start"]=4.123456789
        if reason=="raw interleave":rows[1],rows[2]=rows[2],rows[1]
        if reason=="raw reverse":rows[0],rows[1]=rows[1],rows[0]
        if reason=="track":right["track_id"]="track_"+"c"*32;rows[5]["track_id"]=left["track_id"] # keep model valid
        if reason=="locked":m["layer_tracks"]["tracks"][0]["locked"]=True
        if reason=="asset":right["asset_id"]=rows[4]["asset_id"]
        if reason=="unready":p["assets"][VIDEO]["status"]="waiting"
        if reason=="sound":right["source_start"]+=.01
        if reason=="picture":right["video_source_start"]+=.01
        if reason=="speed":right["speed"]=1.
        if reason=="gain":right["volume_db"]=-9
        if reason=="enabled":right["enabled"]=True
        if reason=="opacity":right["opacity_percent"]=100
        if reason=="crop":right["x"]=0.
        if reason=="fade left":left["fade_out"]=.1
        if reason=="fade right":right["fade_in"]=.1
        if reason=="motion":left["motion"]=right["motion"]="pan"
        if reason in ("different text","chapter","caption"):
            l,r=m["text_clips"][:2]
            if reason=="different text":r["text"]="Different"
            if reason=="chapter":l["template"]=r["template"]="chapter"
            if reason=="caption":l["kind"]=r["kind"]="caption"
    store.update(pid,setup);p=store.load(pid);target=X if reason in ("different text","chapter","caption") else V
    d={"action":"layers_join","clip_ids":[target,mapping[target]],"expected_revision":p["revision"]}
    changes={"single":{"clip_ids":[V]},"three":{"clip_ids":[V,A,I]},"duplicate":{"clip_ids":[V,V]},"unknown":{"clip_ids":[V,"media_"+"0"*32]},"AB":{"clip_ids":[V,"A:0"]},"mixed":{"clip_ids":[V,X]},"bad id":{"clip_ids":[V,None]},"stale":{"expected_revision":p["revision"]-1},"extra":{"frame":122}}
    d.update(changes.get(reason,{}))
    if reason=="no revision":d.pop("expected_revision")
    raw=store.state_path(pid).read_bytes();response=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert response.status_code in (400,409),response.get_json();assert store.state_path(pid).read_bytes()==raw


def test_reversible_defaults_and_independent_source_clock_fallback(unlocked):
    _,_,store,pid=unlocked;mapping={}
    def setup(p):
        arrange(p);v=p["manual"]["media_clips"][0];v.pop("enabled");v.pop("opacity_percent");v.pop("video_source_start")
        before=copy.deepcopy(p);args={"action":"layers_split","clip_ids":[V,X],"frame":122};apply_manual_edit(p,args)
        mapping.update({r["source_id"]:r["clip_id"] for r in group_split_receipt(before,p,args)})
        # Semantically identical defaults must not prevent rejoining a genuine split.
        p["manual"]["media_clips"][1].update(enabled=True,opacity_percent=100)
    store.update(pid,setup);before=store.load(pid);r=post(unlocked,"layers_join",clip_ids=[V,mapping[V]]);assert r.status_code==200,r.get_json()
    result=store.load(pid)["manual"]["media_clips"][0]
    assert "video_source_start" not in result and "opacity_percent" not in result and "enabled" not in result
    assert result["source_start"]==before["manual"]["media_clips"][0]["source_start"]


def test_receipt_rejects_changed_retained_content_and_unrelated_rows(unlocked):
    _,_,store,pid=unlocked;mapping={};store.update(pid,lambda p:mapping.update(split_setup(p)))
    before=store.load(pid);payload={"action":"layers_join","clip_ids":[V,mapping[V]]};after=copy.deepcopy(before);apply_manual_edit(after,payload)
    assert group_join_receipt(before,after,payload)["clip_id"]==V
    for key in ["source_start","opacity_percent","end"]:
        bad=copy.deepcopy(after);bad["manual"]["media_clips"][0][key]+=1
        with pytest.raises(ValueError):group_join_receipt(before,bad,payload)
    bad=copy.deepcopy(after);bad["manual"]["text_clips"][-1]["text"]="Unrelated"
    with pytest.raises(ValueError):group_join_receipt(before,bad,payload)


def test_retired_right_cannot_be_joined_twice_or_replace_later_work(unlocked):
    _,_,store,pid=unlocked;mapping={};store.update(pid,lambda p:mapping.update(split_setup(p)))
    ids=[V,mapping[V]];assert post(unlocked,"layers_join",clip_ids=ids).status_code==200
    raw=store.state_path(pid).read_bytes();r=post(unlocked,"layers_join",clip_ids=ids)
    assert r.status_code==400 and store.state_path(pid).read_bytes()==raw
