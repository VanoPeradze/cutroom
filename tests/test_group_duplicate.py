import copy
import pytest
from cutroom.editing import apply_manual_edit, ManualEditError
from cutroom.projects import ProjectStore
from test_media_append import content, library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers, post
from test_layer_selection import IDS

@pytest.mark.parametrize("tracked",[False,True])
def test_atomic_copy_raw_history_reopen_and_locked_originals(unlocked,tracked):
    app,_,store,pid=unlocked;store.update(pid,mixed_layers)
    if tracked:
        assert post(unlocked,"layer_tracks_enable").status_code==200
        tracks=store.load(pid)["manual"]["layer_tracks"]["tracks"]
        for track in tracks:assert post(unlocked,"layer_track_lock",track_id=track["id"],locked=True).status_code==200
    before=store.load(pid)
    response=post(unlocked,"layers_duplicate",clip_ids=list(reversed(IDS)),start=9.)
    assert response.status_code==200,response.get_json()
    after=store.load(pid)
    receipt=response.get_json()["created"]
    assert [x["source_id"] for x in receipt]==[r["id"] for key in ("media_clips","text_clips") for r in before["manual"][key] if r["id"] in IDS]
    assert len({x["clip_id"] for x in receipt})==len(IDS)
    for key in ("media_clips","text_clips"):
        originals=before["manual"][key];assert after["manual"][key][:len(originals)]==originals
        copies=after["manual"][key][len(originals):]
        expected=[r for r in originals if r["id"] in IDS]
        assert len(copies)==len(expected)
        for row,old in zip(copies,expected):
            assert {k:v for k,v in row.items() if k not in {"id","start","end","track_id"}}=={k:v for k,v in old.items() if k not in {"id","start","end","track_id"}}
            assert row["start"]-old["start"]==7 and row["end"]-old["end"]==7
            if tracked:assert row["track_id"]!=old["track_id"]
    assert after["manual"]["sequence"]==before["manual"]["sequence"]
    assert after["assets"]==before["assets"] and after["sources"]==before["sources"]
    assert after["manual"]["history"]["undo_count"]==before["manual"]["history"]["undo_count"]+1
    assert post(unlocked,"undo").status_code==200
    # Protection format remains version2 while exact content restores.
    assert content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200
    assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)

@pytest.mark.parametrize("extra",[{"start":None},{"start":True},{"start":"2"},{"start":-1},{"start":10},{"delta":1},{"clip_ids":IDS[:1]},{"clip_ids":[IDS[0],IDS[0]]},{"clip_ids":[IDS[0],"A"]},{"clip_ids":[IDS[0],"text_"+"f"*32]}])
def test_refusal_atomic(unlocked,extra):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"layers_duplicate",**({"clip_ids":IDS,"start":9}|extra))
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


def test_same_placement_is_real_copy_and_stale_rejected(unlocked):
    app,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.load(pid)
    assert post(unlocked,"layers_duplicate",clip_ids=IDS,start=2).status_code==200
    raw=store.state_path(pid).read_bytes()
    r=app.test_client().post(f"/api/projects/{pid}/manual/edit",json={"action":"layers_duplicate","clip_ids":IDS,"start":2,"expected_revision":before["revision"]})
    assert r.status_code==409 and store.state_path(pid).read_bytes()==raw


def test_unrelated_offline_occurrence_not_required(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    selected=[p["manual"]["text_clips"][0]["id"],p["manual"]["text_clips"][1]["id"]]
    for asset in p["assets"].values():asset["status"]="failed"
    before=copy.deepcopy(p["manual"]["media_clips"])
    apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":selected,"start":2})
    assert p["manual"]["media_clips"]==before

@pytest.mark.parametrize("field,value",[("start",True),("end",float("nan")),("muted","false"),("speed",None)])
def test_invalid_selected_data_atomic(unlocked,field,value):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);p["manual"]["media_clips"][0][field]=value;before=copy.deepcopy(p)
    ids=[p["manual"]["media_clips"][0]["id"],p["manual"]["text_clips"][0]["id"]]
    with pytest.raises(ManualEditError):apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":ids,"start":2})
    assert p==before


def test_reordered_visual_and_text_priority_not_click_or_array(unlocked):
    from cutroom.layer_tracks import ordered_layer_clips
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    apply_manual_edit(p,{"action":"layer_tracks_enable"})
    p["manual"]["layer_tracks"]["tracks"].reverse()
    expected={kind:[r["id"] for r in ordered_layer_clips(p,kind) if r["id"] in IDS] for kind in ("visual","text")}
    before=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":list(reversed(IDS)),"start":2})
    for kind,key in (("visual","media_clips"),("text","text_clips")):
        old_ids={r["id"] for r in before["manual"][key]}
        added=[r for r in ordered_layer_clips(p,kind) if r["id"] not in old_ids]
        old={r["id"]:r for r in before["manual"][key]}
        for row,identity in zip(added,expected[kind]):
            assert {k:v for k,v in row.items() if k not in {"id","track_id"}}=={k:v for k,v in old[identity].items() if k not in {"id","track_id"}}


def test_capacity_and_text_overlap_atomic(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    row=p["manual"]["media_clips"][0]
    p["manual"]["media_clips"]=[{**row,"id":"media_"+format(i,"032x")} for i in range(200)]
    before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":[p["manual"]["media_clips"][i]["id"] for i in (0,1)],"start":2})
    assert p==before
    mixed_layers(p);row=p["manual"]["text_clips"][0]
    p["manual"]["text_clips"]=[{**row,"id":"text_"+format(i,"032x")} for i in range(16)]
    before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":[p["manual"]["text_clips"][i]["id"] for i in (0,1)],"start":row["start"]})
    assert p==before


from test_media_render import media

def test_actual_mixed_duplicate_encode_matches_independent_reference(media,tmp_path):
    import hashlib,threading,uuid
    from test_track_destination_render import prepared
    from test_layer_tracks_render import decoded
    from cutroom.layer_tracks import ordered_layer_clips
    from cutroom.render import render_project
    from cutroom.jobs import Job,JobContext
    p,store,settings,_,unchanged = prepared(media,tmp_path)
    # The fixture helper supplies source/asset copies only in the test workspace.
    p["settings"].update(captions=False,burn_captions=False)
    p["analysis"]=None
    p["manual"]["sequence"]={"version":1,"duration":6.,"camera_plan":[{"start":0.,"end":6.,"camera":"A"}]}
    p["manual"]["source_tracks"]={"A":[],"B":[]}
    p["manual"]["audio_mixer"]={"source_muted":True,"ducking":False}
    if "layer_tracks" not in p["manual"]:apply_manual_edit(p,{"action":"layer_tracks_enable"})
    p["manual"]["layer_tracks"]["tracks"].reverse()
    p["manual"]["media_clips"][0]["enabled"]=False
    ids=[r["id"] for key in ("media_clips","text_clips") for r in p["manual"].get(key,[])]
    before=copy.deepcopy(p);reference=copy.deepcopy(p)
    for key,kind in (("media_clips",None),("text_clips","text")):
        rows=before["manual"].get(key,[])
        if kind:ordered=ordered_layer_clips(before,kind)
        else:
            visual=iter(ordered_layer_clips(before,"visual"))
            ordered=[r if before["assets"][r["asset_id"]]["kind"]=="audio" else next(visual) for r in rows]
        for old in ordered:
            row=copy.deepcopy(old);row.update(id=("text_" if kind else "media_")+uuid.uuid4().hex,start=old["start"]+3,end=old["end"]+3)
            lane="track_"+uuid.uuid4().hex;row["track_id"]=lane
            trackkind=kind or ("audio" if before["assets"][old["asset_id"]]["kind"]=="audio" else "visual")
            reference["manual"]["layer_tracks"]["tracks"].append({"id":lane,"kind":trackkind,"name":"Reference copy"})
            reference["manual"][key].append(row)
    apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":list(reversed(ids)),"start":3})
    # Earliest original begins at0; all content clocks remain intact.
    def encode(value,tag):
        store.save(value)
        record=render_project(JobContext(Job(tag,"render",value["id"]),threading.Lock()),value["id"],store,settings,{"quality":"fast"})["export"]
        return settings.exports_dir/record["name"]
    first=encode(reference,"reference");second=encode(p,"copied")
    assert decoded(media[1],first)==decoded(media[1],second)
    assert decoded(media[1],first,False)==decoded(media[1],second,False)
    unchanged()


def test_revision_required_no_write(unlocked):
    app,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    r=app.test_client().post(f"/api/projects/{pid}/manual/edit",json={"action":"layers_duplicate","clip_ids":IDS,"start":2})
    assert r.status_code==400 and store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("start",[2.0000005,2+1/24,8.999999999])
def test_shared_translation_precision(unlocked,start):
    import math
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);before=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":IDS,"start":start})
    for key,precision in (("media_clips",9),("text_clips",6)):
        old=[r for r in before["manual"][key] if r["id"] in IDS];new=p["manual"][key][len(before["manual"][key]):]
        for a,b in zip(old,new):
            for edge in ("start","end"):assert b[edge]==math.floor((a[edge]+start-2)*10**precision+.5)/10**precision


def test_busy_and_receipt_failure_are_atomic(unlocked,monkeypatch):
    import server
    app,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    with monkeypatch.context() as m:
        m.setattr(app.extensions["cutroom_jobs"],"active",lambda **_:[object()])
        assert post(unlocked,"layers_duplicate",clip_ids=IDS,start=2).status_code==409
    assert store.state_path(pid).read_bytes()==before
    with monkeypatch.context() as m:
        def refuse(*args):raise ValueError("Receipt did not match")
        m.setattr(server,"group_duplicate_receipt",refuse)
        assert post(unlocked,"layers_duplicate",clip_ids=IDS,start=2).status_code==400
    assert store.state_path(pid).read_bytes()==before


def test_selected_unavailable_is_refused(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    row=next(r for r in p["manual"]["media_clips"] if r["id"] in IDS)
    p["assets"][row["asset_id"]]["status"]="failed";before=copy.deepcopy(p)
    with pytest.raises(ManualEditError):apply_manual_edit(p,{"action":"layers_duplicate","clip_ids":IDS,"start":2})
    assert p==before
