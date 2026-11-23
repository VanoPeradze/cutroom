"""Occurrence-local integer opacity: atomic revisions, source identity, and history."""
import copy,hashlib
import pytest
from cutroom.media_library import validate_media_clip, validate_clip_opacity
from cutroom.editing import apply_manual_edit
from cutroom.media_render import append_media_graph
from cutroom.render_inventory import compile_render_inputs, library_clips
from test_media_append import library_api, content
from test_media_insert import unlocked
from test_mixed_media_insert import VIDEO,IMAGE,AUDIO,post,media_row
from test_track_overwrite import arrange
from test_rolling_edit import L,T,U
from test_replace_take import NEW


def opacity(api,clip=L,value=50,**extra):
    return post(api,"media_set_opacity",clip_id=clip,opacity_percent=value,**extra)


@pytest.mark.parametrize("kind",[VIDEO,IMAGE])
@pytest.mark.parametrize("amount",[0,1,25,50,99])
def test_only_one_occurrence_changes_and_undo_redo_restore_exact_manual(unlocked,kind,amount):
    _,_,store,pid=unlocked
    def setup(p):
        arrange(p);r,m,o,l=p["manual"]["media_clips"];l.update(asset_id=kind,source_start=0.,speed=1.,audio_enabled=kind==VIDEO)
        # Same asset on another lane is deliberately not edited.
        o.update(asset_id=kind,source_start=0.,speed=1.,audio_enabled=kind==VIDEO)
    store.update(pid,setup);before=store.load(pid);root=store.project_dir(pid)/"media"
    hashes=lambda:{f.relative_to(root):hashlib.sha256(f.read_bytes()).digest() for f in root.rglob("*") if f.is_file()}
    digest=hashes();r=opacity(unlocked,value=amount);assert r.status_code==200,r.get_json()
    after=store.load(pid);expected=copy.deepcopy(before["manual"]["media_clips"]);expected[-1]["opacity_percent"]=amount
    assert after["manual"]["media_clips"]==expected
    assert after["revision"]==before["revision"]+1
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for k,v in before["manual"].items():
        if k not in ("media_clips","history","_history"):assert after["manual"][k]==v
    for k in ("assets","sources","settings","analysis","exports","review_markers"):assert after.get(k)==before.get(k)
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(store.load(pid))==content(after)
    assert hashes()==digest


def test_same_value_has_no_revision_or_undo_and_default_removes_optional_key(unlocked):
    _,_,store,pid=unlocked;store.update(pid,arrange)
    for value in [100,50,50,100,100]:
        before=store.load(pid);old=next(c for c in before["manual"]["media_clips"] if c["id"]==L).get("opacity_percent",100);raw=store.state_path(pid).read_bytes()
        response=opacity(unlocked,value=value);assert response.status_code==200,response.get_json()
        after=store.load(pid);c=next(c for c in after["manual"]["media_clips"] if c["id"]==L)
        if value==old:assert store.state_path(pid).read_bytes()==raw
        else:assert after["revision"]==before["revision"]+1
        assert c.get("opacity_percent",100)==value
        if value==100:assert "opacity_percent" not in c


@pytest.mark.parametrize("reason",["bool","float","string","none","negative","too large","nan","array","object","missing","unknown","audio","offline","locked","stale","no revision","extra","existing invalid"])
def test_bad_opacity_is_atomic_and_never_silences_audio(unlocked,reason):
    _,client,store,pid=unlocked
    def setup(p):
        arrange(p);l=p["manual"]["media_clips"][-1]
        if reason=="audio":l.update(asset_id=AUDIO,track_id="track_"+"0"*32);p["manual"]["layer_tracks"]["tracks"].append({"id":"track_"+"0"*32,"kind":"audio","name":"Sound","locked":False})
        if reason=="offline":p["assets"][VIDEO]["status"]="waiting"
        if reason=="locked":p["manual"]["layer_tracks"]["tracks"][0]["locked"]=True
        if reason=="existing invalid":l["opacity_percent"]="bad"
    store.update(pid,setup);p=store.load(pid)
    d={"action":"media_set_opacity","clip_id":L,"opacity_percent":50,"expected_revision":p["revision"]}
    values={"bool":True,"float":50.0,"string":"50","none":None,"negative":-1,"too large":101,"nan":float("nan"),"array":[],"object":{}}
    if reason in values:d["opacity_percent"]=values[reason]
    if reason=="missing":d.pop("opacity_percent")
    if reason=="unknown":d["clip_id"]="media_"+"f"*32
    if reason=="stale":d["expected_revision"]-=1
    if reason=="no revision":d.pop("expected_revision")
    if reason=="extra":d["volume_db"]=-60
    raw=store.state_path(pid).read_bytes();r=client.post(f"/api/projects/{pid}/manual/edit",json=d)
    assert r.status_code in (400,409),r.get_json();assert store.state_path(pid).read_bytes()==raw


@pytest.mark.parametrize("kind,op",[(kind,op) for kind in (VIDEO,IMAGE) for op in ("media_trim","media_split","media_duplicate","media_move","media_slip","media_set_enabled","media_transform","media_update","media_replace_take","media_track_overwrite","media_track_lift") if not (kind==IMAGE and op=="media_slip")])
def test_existing_edit_operators_preserve_occurrence_appearance(unlocked,op,kind):
    _,_,store,pid=unlocked
    def setup(p):
        arrange(p);m=p["manual"];r,mid,o,l=m["media_clips"];l.update(start=2.,end=9.,opacity_percent=37,fade_in=0.,fade_out=0.);m["media_clips"]=[o,l]
        if kind==IMAGE:
            l.update(asset_id=IMAGE,source_start=0.,speed=1.,audio_enabled=False);l.pop("video_source_start",None)
            if op=="media_replace_take":p["assets"][NEW]={**p["assets"][IMAGE],"id":NEW}
    store.update(pid,setup);before=store.load(pid)
    args={
        "media_trim":{"clip_id":L,"edge":"start","time":3.},
        "media_split":{"clip_id":L,"time":5.},
        "media_duplicate":{"clip_id":L,"start":2.},
        "media_move":{"clip_id":L,"start":3.},
        "media_slip":{"clip_id":L,"source_start":2.},
        "media_set_enabled":{"clip_id":L,"enabled":False},
        "media_transform":{"clip_id":L,"x":0.,"y":0.,"w":.5,"h":.5},
        "media_update":{"clip_id":L,"volume_db":-7},
        "media_replace_take":{"clip_id":L,"previous_asset_id":VIDEO,"asset_id":NEW,"source_start":.25,"source_end":19.},
        "media_track_overwrite":{"track_id":T,"asset_id":NEW,"source_start":.2,"source_end":1.2,"frame":120},
        "media_track_lift":{"track_id":T,"start_frame":120,"end_frame":150},
    }[op]
    if kind==IMAGE and op=="media_replace_take":
        args["previous_asset_id"]=IMAGE;args.pop("source_start");args.pop("source_end")
    r=post(unlocked,op,**args);assert r.status_code==200,r.get_json()
    rows=store.load(pid)["manual"]["media_clips"]
    # The unrelated locked lane remains opaque; newly overwritten shot is default.
    assert rows[0]==before["manual"]["media_clips"][0]
    old_pieces=[c for c in rows[1:] if not (op=="media_track_overwrite" and c["asset_id"]==NEW)]
    assert old_pieces and all(c["opacity_percent"]==37 for c in old_pieces)
    if op=="media_track_overwrite":assert "opacity_percent" not in rows[-1]
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)


@pytest.mark.parametrize("value",[True,-1,101,50.0,"50",None,{},[]])
def test_invalid_persisted_opacity_cannot_silently_render(value):
    p={"manual":{"media_clips":[{"id":L,"asset_id":VIDEO,"opacity_percent":value}]},"assets":{VIDEO:{"kind":"video","status":"ready"}}}
    with pytest.raises(ValueError):library_clips(p)


def test_sound_asset_cannot_persist_visual_opacity():
    with pytest.raises(ValueError):validate_clip_opacity({"opacity_percent":100},{"kind":"audio"})


def test_corrupt_asset_identity_is_refused_before_mutation(unlocked):
    from cutroom.media_library import prepare_media_edit
    _,_,store,pid=unlocked;store.update(pid,arrange);p=store.load(pid)
    p["assets"][VIDEO]["id"]=NEW;before=copy.deepcopy(p)
    with pytest.raises(ValueError,match="ready imported"):
        prepare_media_edit(p,{"action":"media_set_opacity","clip_id":L,"opacity_percent":50})
    assert p==before
