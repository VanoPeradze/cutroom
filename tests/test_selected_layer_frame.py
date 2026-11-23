"""Direct viewer framing changes only the saved visual box, with atomic history."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from test_media_append import content,library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers,VIDEO,post
from test_selected_layer_trim import render_setup

RECT={"x":.123456789,"y":.2,"w":.4,"h":.6}
KEYS=("x","y","w","h")

@pytest.mark.parametrize("index",[1,3])
def test_frame_only_changes_geometry_preserving_every_other_field_and_history(unlocked,index):
    app,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["track_locks"]={"A":True,"B":True}
        row=p["manual"]["media_clips"][index]
        row.update(motion="pan",volume_db=-3.123456789123,opaque_metadata={"keep":[1,2]})
        if index==1:row.update(speed=.5,source_start=1.123456789123,video_source_start=2.987654321987)
    store.update(pid,prepare);before=store.load(pid);clip=before["manual"]["media_clips"][index]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    response=post(unlocked,"media_transform",clip_id=clip["id"],**RECT);assert response.status_code==200,response.get_json()
    after=store.load(pid);expected=copy.deepcopy(before["manual"]["media_clips"]);expected[index].update(RECT)
    assert after["manual"]["media_clips"]==expected
    assert response.get_json()["project"]["manual"]["media_clips"][index]==expected[index]
    for key,value in before["manual"].items():
        if key not in ("media_clips","history","_history"):assert after["manual"][key]==value
    for key in ("sources","assets","analysis","settings"):assert after[key]==before[key]
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes

@pytest.mark.parametrize("patch",[
    {"x":-.01},{"y":1.01},{"w":.009},{"h":0},{"x":.9,"w":.2},{"y":.9,"h":.2},
    {"x":True},{"w":None},{"y":"not a number"},{"h":float("inf")},{"x":float("nan")},
])
def test_invalid_geometry_is_rejected_without_mutating_state(unlocked,patch):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_transform",clip_id="media_"+"2"*32,**{**RECT,**patch})
    assert response.status_code==400,response.get_json();assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("key",KEYS)
def test_frame_requires_all_four_fields(unlocked,key):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes();geometry={k:v for k,v in RECT.items() if k!=key}
    assert post(unlocked,"media_transform",clip_id="media_"+"2"*32,**geometry).status_code==400
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("extra",[{"start":1},{"source_start":2},{"enabled":False},{"motion":"none"},{"muted":True}])
def test_frame_rejects_incidental_content_timing_and_audio_changes(unlocked,extra):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_transform",clip_id="media_"+"2"*32,**RECT,**extra).status_code==400
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("clip_id",["media_"+"3"*32,"media_"+"f"*32,"text_"+"2"*32,"A:sequence:0:0","automatic_caption"])
def test_frame_refuses_audio_text_source_and_missing_targets(unlocked,clip_id):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_transform",clip_id=clip_id,**RECT).status_code==400
    assert store.state_path(pid).read_bytes()==before


def test_frame_noop_keeps_redo_and_does_not_normalize_unrelated_fields(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p);clip=p["manual"]["media_clips"][1]
    original={k:clip[k] for k in KEYS}
    apply_manual_edit(p,{"action":"media_transform","clip_id":clip["id"],**RECT});apply_manual_edit(p,{"action":"undo"});before=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"media_transform","clip_id":clip["id"],**original})
    assert p==before and p["manual"]["history"]["redo_count"]==1


def test_frame_canonical_rounding_keeps_bounds_and_disabled_state(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):mixed_layers(p);p["manual"]["media_clips"][3]["enabled"]=False
    store.update(pid,prepare);clip=store.load(pid)["manual"]["media_clips"][3]
    assert post(unlocked,"media_transform",clip_id=clip["id"],x=.333333333333,y=0.,w=.666666666666,h=1.).status_code==200
    after=store.load(pid)["manual"]["media_clips"][3];assert after=={**clip,"x":.333333333,"y":0.,"w":.666666667,"h":1.}


def test_frame_waits_for_ready_asset_and_revision_conflict_is_atomic(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Elsewhere"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_transform",clip_id="media_"+"2"*32,expected_revision=revision,**RECT).status_code==409
    assert store.state_path(pid).read_bytes()==before
    store.update(pid,lambda p:p["assets"][VIDEO].update(status="failed"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_transform",clip_id="media_"+"2"*32,**RECT).status_code==400
    assert store.state_path(pid).read_bytes()==before

@pytest.mark.parametrize("index,fit,motion",[(0,"cover","pan"),(2,"contain","zoom_in")])
def test_real_frame_export_matches_independent_geometry_reference_and_undo(library_api,media,index,fit,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"frame-pattern-{index}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:]);store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,.5)
    def configure(p):p["manual"]["media_clips"][index].update(fit=fit,motion=motion)
    store.update(pid,configure);before=copy.deepcopy(store.load(pid));original,original_record=encoded("frame-original")
    geometry={"x":.1,"y":.15,"w":.6 if index==0 else .3,"h":.55 if index==0 else .3}
    store.update(pid,lambda p:p["manual"]["media_clips"][index].update(geometry));reference,reference_record=encoded("frame-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before["manual"])))
    clip=before["manual"]["media_clips"][index]
    response=post(library_api,"media_transform",clip_id=clip["id"],**geometry);assert response.status_code==200,response.get_json()
    after=content(store.load(pid));actual,record=encoded("frame-native")
    assert store.load(pid)["manual"]["media_clips"][index]=={**clip,**geometry}
    assert post(library_api,"undo").status_code==200 and content(store.load(pid))==content(before)
    undone,undo_record=encoded("frame-undone")
    assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    sounds=[samples(media[1],p) for p in (original,reference,actual,undone)];differences=[]
    for at in (.3,.6,.9,1.3,1.9,2.3,2.6):
        for x,y in ((5,8),(30,15),(70,40),(120,15),(150,20),(80,75)):
            old,ref,got,undo=[pixel(media[1],p,at,x,y) for p in (original,reference,actual,undone)]
            assert max(abs(a-b) for a,b in zip(ref,got))<24
            assert max(abs(a-b) for a,b in zip(old,undo))<24
            differences.append(max(abs(a-b) for a,b in zip(old,got)))
        for hz in (440,880):
            levels=[tone_level(sound,at,hz) for sound in sounds]
            assert levels==pytest.approx([levels[0]]*4,abs=.003)
    assert max(differences)>40,'geometry change must produce a real visual difference'
    assert all(r["duration"]==pytest.approx(3.,abs=1/30) for r in (original_record,reference_record,record,undo_record))
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==4 and all(p.exists() for p in (original,reference,actual,undone))


@pytest.mark.parametrize("bad",[None,"0.1",True,float("nan")])
def test_corrupt_saved_frame_is_rejected_atomically_instead_of_crashing(unlocked,bad):
    _,_,store,pid=unlocked
    def prepare(p):mixed_layers(p);p["manual"]["media_clips"][1]["x"]=bad
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_transform",clip_id="media_"+"2"*32,**RECT)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before
