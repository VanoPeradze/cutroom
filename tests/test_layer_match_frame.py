import copy
import pytest
import cutroom.editing as editing
import cutroom.layer_selection as selection
from cutroom.layer_selection import _match_frame as prepare
ACTION = "layers_match_frame"
from test_media_append import append_project,content,library_api
from test_media_insert import unlocked
from test_mixed_media_insert import mixed_layers,post
from cutroom.projects import ProjectStore

def setup(version=0,pv=1):
    p=append_project();mixed_layers(p)
    rows=p["manual"]["media_clips"]
    p["manual"]["media_clips"]=[rows[0],rows[1],rows[3]]
    rows=p["manual"]["media_clips"]
    rows[0]["opaque_metadata"]={"preserve":[1,{"x":"original"}]}
    rows[1]["custom_extra"]=["target",None]
    rows[0].update(x=.333333333333,y=.123456789123,w=.4,h=.5,fit="cover")
    rows[1].pop("fit");rows[1]["enabled"]=False
    rows[2].update(**{k:rows[0][k] for k in ("x","y","w","h")});rows[2].pop("fit")
    if version:
        tracks=[]
        for i,row in enumerate(rows):
            tid="track_"+format(i+1,"032x");row["track_id"]=tid
            t={"id":tid,"kind":"visual","name":str(i)}
            if version>=2:t["locked"]=False
            if version==3:t["audio"]={"gain_db":-3.1234,"muted":False}
            tracks.append(t)
        # Existing unrelated custom text remains legal on its own text lanes.
        for i,row in enumerate(p["manual"]["text_clips"]):
            tid="track_"+format(i+10,"032x");row["track_id"]=tid
            tracks.append({"id":tid,"kind":"text","name":"Text",**({"locked":False} if version>=2 else {})})
        p["manual"]["layer_tracks"]={"version":version,"tracks":tracks,**({"protection_version":pv} if version==3 else {})}
    return p

def payload(p):
    ids=[r["id"] for r in p["manual"]["media_clips"]]
    return {"action":ACTION,"clip_ids":ids,"reference_id":ids[0]}

@pytest.mark.parametrize("version,pv",[(0,1),(1,1),(2,2),(3,1),(3,2)])
def test_api_exact_one_history_noop_undo_reopen(unlocked,version,pv):
    app,client,store,pid=unlocked;p=setup(version,pv);p["id"]=pid
    store.save({**store.load(pid),**p});before=store.load(pid);q=payload(before)
    response=post(unlocked,ACTION,**{k:v for k,v in q.items() if k!="action"});assert response.status_code==200,response.get_json()
    after=store.load(pid);expected=copy.deepcopy(before["manual"]["media_clips"])
    for k in ("x","y","w","h"):expected[1][k]=expected[0][k]
    assert after["manual"]["media_clips"]==expected
    assert "fit" not in expected[1] and "fit" not in expected[2]
    assert after["revision"]==before["revision"]+1
    for key in ("assets","sources","settings","analysis"):assert after[key]==before[key]
    for key,value in before["manual"].items():
        if key not in ("media_clips","history","_history"):assert after["manual"][key]==value
    raw=store.state_path(pid).read_bytes();assert post(unlocked,ACTION,**{k:v for k,v in q.items() if k!="action"}).status_code==200;assert store.state_path(pid).read_bytes()==raw
    assert post(unlocked,"undo").status_code==200;assert content(store.load(pid))==content(before);assert store.load(pid)["manual"]["media_clips"]==before["manual"]["media_clips"]
    assert post(unlocked,"redo").status_code==200;assert content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    raw=store.state_path(pid).read_bytes();res=client.post(f"/api/projects/{pid}/manual/edit",json={**q,"expected_revision":before["revision"]});assert res.status_code==409;assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("bad",["duplicate","missing","reference","audio","text","bool","string","nan","bounds","fit","unready","late","locked","locked_noop","future","unknown","one","overlimit"])
def test_reject_atomic(bad):
    p=setup(2);q=payload(p);rows=p["manual"]["media_clips"]
    if bad=="duplicate":q["clip_ids"][1]=q["clip_ids"][0]
    if bad=="missing":q["clip_ids"][1]="media_"+"f"*32
    if bad=="reference":q["reference_id"]="media_"+"f"*32
    if bad=="audio":p["assets"][rows[1]["asset_id"]]["kind"]="audio"
    if bad=="text":q["clip_ids"][1]=p["manual"]["text_clips"][0]["id"]
    if bad in ("bool","string","nan","bounds"):rows[0]["x"]={"bool":True,"string":"0.1","nan":float("nan"),"bounds":1.1}[bad]
    if bad=="fit":rows[0]["fit"]=None
    if bad=="unready":p["assets"][rows[1]["asset_id"]]["status"]="failed"
    if bad=="late":rows[-1]["w"]="invalid"
    if bad in ("locked","locked_noop"):p["manual"]["layer_tracks"]["tracks"][2 if bad=="locked_noop" else 1]["locked"]=True
    if bad=="future":p["manual"]["layer_tracks"]["version"]=99
    if bad=="unknown":q["fit"]="cover"
    if bad=="one":q["clip_ids"]=q["clip_ids"][:1]
    if bad=="overlimit":q["clip_ids"]=["media_"+format(i,"032x") for i in range(201)]
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):editing.apply_manual_edit(p,q)
    # nan is intentionally non-reflexive; deep copies retain the same immutable float.
    assert p==before

def test_locked_reference_allowed():
    p=setup(2);p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True;before=copy.deepcopy(p["manual"]["media_clips"][0]);editing.apply_manual_edit(p,payload(p));assert p["manual"]["media_clips"][0]==before

def test_full_200_and_exact_five_field_oracle():
    p=setup();base=p["manual"]["media_clips"][1];p["manual"]["media_clips"]=[p["manual"]["media_clips"][0]]+[dict(copy.deepcopy(base),id="media_"+format(i+100,"032x")) for i in range(199)]
    before=copy.deepcopy(p);q=payload(p);result=prepare(p,q)
    oracle=copy.deepcopy(before["manual"]["media_clips"])
    for row in oracle[1:]:
        for key in ("x","y","w","h"):row[key]=oracle[0][key]
    assert result=={"media_clips":oracle};assert p==before
    p["manual"].update(result);assert prepare(p,q) is None

def test_api_busy_missing_revision_unknown(unlocked,monkeypatch):
    app,client,store,pid=unlocked;p=setup();p["id"]=pid;store.save({**store.load(pid),**p});q=payload(store.load(pid));raw=store.state_path(pid).read_bytes()
    endpoint=f"/api/projects/{pid}/manual/edit"
    assert client.post(endpoint,json=q).status_code==400
    assert client.post(endpoint,json={**q,"expected_revision":store.load(pid)["revision"],"fit":"cover"}).status_code==400
    with monkeypatch.context() as m:
        m.setattr(app.extensions["cutroom_jobs"],"active",lambda **_:[object()])
        assert post(unlocked,ACTION,**{k:v for k,v in q.items() if k!="action"}).status_code==409
    assert store.state_path(pid).read_bytes()==raw

def test_absent_reference_fit_and_optional_metadata_unchanged():
    p=setup();rows=p["manual"]["media_clips"];rows[0].pop("fit");rows[1].pop("video_source_start",None);rows[0]["metadata"]={"opaque":[1,2]}
    before=copy.deepcopy(rows);result=prepare(p,payload(p));assert result["media_clips"][0]==before[0];assert "video_source_start" not in result["media_clips"][1];assert "fit" not in result["media_clips"][1]

def test_unselected_unavailable_row_is_untouched():
    p=setup();q=payload(p);asset_id="asset_"+"a"*32
    p["assets"][asset_id]={"id":asset_id,"kind":"audio","status":"failed"}
    row={"id":"media_"+"e"*32,"asset_id":asset_id,"start":1,"end":2,"opaque":"unavailable"}
    p["manual"]["media_clips"].append(row);result=prepare(p,q);assert result["media_clips"][-1]==row

@pytest.mark.parametrize("source_fit,target_fit",[("contain","cover"),("cover","contain")])
def test_fit_only_and_nonfirst_reference(source_fit,target_fit):
    p=setup();rows=p["manual"]["media_clips"];rows[0]["fit"]=source_fit
    for row in rows[1:]:
        row.update({k:rows[0][k] for k in ("x","y","w","h")});row["fit"]=target_fit
    q=payload(p);q["clip_ids"].reverse();before=copy.deepcopy(rows);result=prepare(p,q)
    assert result["media_clips"][0]==before[0]
    for i in (1,2):assert result["media_clips"][i]=={**before[i],"fit":source_fit}

def test_sparse_effective_noop_with_fit_changing_member():
    p=setup();rows=p["manual"]["media_clips"]
    for row in rows[1:]:row.update({k:rows[0][k] for k in ("x","y","w","h")})
    rows[1]["fit"]="contain";before=copy.deepcopy(rows);result=prepare(p,payload(p))
    assert result["media_clips"][1]=={**before[1],"fit":"cover"};assert result["media_clips"][2]==before[2];assert "fit" not in result["media_clips"][2]

@pytest.mark.parametrize("index",[1,2])
def test_every_v3_target_locked_even_noop(index):
    p=setup(3,2);rows=p["manual"]["media_clips"]
    for row in rows[1:]:row.update({k:rows[0][k] for k in ("x","y","w","h")})
    p["manual"]["layer_tracks"]["tracks"][index]["locked"]=True;before=copy.deepcopy(p)
    with pytest.raises(ValueError):editing.apply_manual_edit(p,payload(p))
    assert p==before

@pytest.mark.parametrize("bad",["media_over","media_array","media_duplicate","text_array","text_id","text_duplicate","text_over","huge_int"])
def test_legacy_global_integrity_api_rollback(unlocked,bad):
    app,client,store,pid=unlocked;p=setup();p["id"]=pid;q=payload(p)
    if bad=="media_over":p["manual"]["media_clips"] += [dict(p["manual"]["media_clips"][0],id="media_"+format(i+100,"032x")) for i in range(198)]
    if bad=="media_array":p["manual"]["media_clips"]={}
    if bad=="media_duplicate":p["manual"]["media_clips"].append(copy.deepcopy(p["manual"]["media_clips"][0]))
    if bad=="text_array":p["manual"]["text_clips"]={}
    if bad=="text_id":p["manual"]["text_clips"][0]["id"]="invalid"
    if bad=="text_duplicate":p["manual"]["text_clips"].append(copy.deepcopy(p["manual"]["text_clips"][0]))
    if bad=="text_over":p["manual"]["text_clips"]=[dict(p["manual"]["text_clips"][0],id="text_"+format(i,"032x")) for i in range(2001)]
    if bad=="huge_int":p["manual"]["media_clips"][0]["x"]=10**400
    before=copy.deepcopy(p)
    with pytest.raises(ValueError):prepare(p,q)
    assert p==before
    # Inject malformed legacy state as a read result; no invalid fixture is persisted.
    original_load=store.load
    def loaded(project_id):
        value=original_load(project_id)
        if project_id==pid:
            revision=value["revision"];value.update(copy.deepcopy(p));value["revision"]=revision
        return value
    raw=store.state_path(pid).read_bytes()
    from unittest.mock import patch
    with patch.object(store,"load",side_effect=loaded):
        response=client.post(f"/api/projects/{pid}/manual/edit",json={**q,"expected_revision":original_load(pid)["revision"]})
        assert response.status_code in (400,409),response.get_json()
    assert store.state_path(pid).read_bytes()==raw

@pytest.mark.parametrize("version,pv",[(0,1),(1,1),(2,2),(3,1),(3,2)])
@pytest.mark.parametrize("fit_only",[False,True])
def test_public_receipt_with_saved_proposal(unlocked,version,pv,fit_only):
    import os,json
    from pathlib import Path
    from cutroom.ai_draft_proposals import record_ai_draft_proposal
    app,client,store,pid=unlocked;p=setup(version,pv);p["id"]=pid
    rows=p["manual"]["media_clips"]
    if fit_only:
        rows[1].update({k:rows[0][k] for k in ("x","y","w","h")});rows[1]["fit"]="contain"
    if version==2 or version==3 and pv==2:p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True
    record_ai_draft_proposal(p);store.save({**store.load(pid),**p});before=store.load(pid);q=payload(before);q["clip_ids"].reverse()
    public_before=client.get(f"/api/projects/{pid}").get_json()
    response=post(unlocked,ACTION,**{k:v for k,v in q.items() if k!="action"});assert response.status_code==200,response.get_json()
    after=store.load(pid);assert after["_ai_draft_proposal"]==before["_ai_draft_proposal"]
    undo=post(unlocked,"undo");assert undo.status_code==200;assert store.load(pid)["manual"]["media_clips"]==before["manual"]["media_clips"]
    redo=post(unlocked,"redo");assert redo.status_code==200;assert store.load(pid)["manual"]["media_clips"]==after["manual"]["media_clips"]
    if os.environ.get("MATCH_FRAME_RECEIPTS"):
        path=Path(os.environ["MATCH_FRAME_RECEIPTS"]);path.mkdir(parents=True,exist_ok=True)
        (path/f"public-v{version}-pv{pv}-fit{int(fit_only)}.json").write_text(json.dumps({"before":public_before,"after":response.get_json(),"undo":undo.get_json(),"redo":redo.get_json(),"payload":{**q,"expected_revision":before["revision"]}},ensure_ascii=False),encoding="utf8")
