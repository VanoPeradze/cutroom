"""Visual stacking changes only saved visual order, not content or timeline tracks."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.projects import ProjectStore
from cutroom.editing import apply_manual_edit
from cutroom.render import _render_input_fingerprint
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, VIDEO, AUDIO, IMAGE, post
from test_selected_layer_trim import render_setup


@pytest.mark.parametrize("digit,position,order", [
    ("2","backward","21345"),("2","forward","14325"),("2","back","21345"),("2","front","14352"),
    ("4","backward","14325"),("4","forward","12354"),("4","back","41325"),("4","front","12354"),
    ("1","front","24351"),("5","back","51324"),
])
def test_visual_slots_reorder_exactly_with_history_and_fresh_reopen(unlocked,digit,position,order):
    app,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["track_locks"]={"A":True,"B":True}
        p["manual"]["media_clips"][1].update(motion="pan",custom_metadata={"retain":"exact"})
    store.update(pid,prepare);before=store.load(pid);old=before["manual"]["media_clips"]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    fingerprint=_render_input_fingerprint(before)
    response=post(unlocked,"media_reorder",clip_id="media_"+digit*32,position=position)
    assert response.status_code==200,response.get_json()
    after=store.load(pid);assert after["manual"]["media_clips"]==[old[int(n)-1] for n in order]
    assert after["manual"]["media_clips"][2]==old[2]  # audio-only slot is not moved
    for field,value in before["manual"].items():
        if field not in ("media_clips","history","_history"):assert after["manual"][field]==value
    for field in ("assets","sources","analysis"):assert after[field]==before[field]
    assert _render_input_fingerprint(after)!=fingerprint
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes


@pytest.mark.parametrize("position", [None,True,1,"up","",[],{}])
def test_bad_stack_position_is_atomic(unlocked,position):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_reorder",clip_id="media_"+"2"*32,position=position)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


def test_stack_requires_explicit_position_and_rejects_incidental_clip_fields(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    for fields in ({},{"position":"front","start":0.},{"position":"front","source_start":2.},{"position":"front","asset_id":IMAGE}):
        response=post(unlocked,"media_reorder",clip_id="media_"+"2"*32,**fields)
        assert response.status_code==400,response.get_json()
        assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("clip", ["media_"+"3"*32,"text_"+"2"*32,"automatic_caption","A:sequence:0:0","media_"+"f"*32])
def test_nonvisual_or_stale_target_never_reorders_audio_text_or_underlying_source(unlocked,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_reorder",clip_id=clip,position="front").status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("change", ["missing","unready","unknown_kind","duplicate_id"])
def test_unknown_stack_members_fail_closed_without_partial_reorder(unlocked,change):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p)
        if change=="missing":p["assets"].pop(IMAGE)
        if change=="unready":p["assets"][IMAGE]["status"]="failed"
        if change=="unknown_kind":p["assets"][IMAGE]["kind"]="unknown"
        if change=="duplicate_id":p["manual"]["media_clips"][4]["id"]=p["manual"]["media_clips"][0]["id"]
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_reorder",clip_id="media_"+"2"*32,position="front").status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("digit,position", [("1","back"),("1","backward"),("5","front"),("5","forward")])
def test_stack_boundary_noop_preserves_redo_and_all_saved_fields(unlocked,digit,position):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    apply_manual_edit(p,{"action":"media_reorder","clip_id":"media_"+"2"*32,"position":"front"})
    apply_manual_edit(p,{"action":"undo"});before=copy.deepcopy(p)
    apply_manual_edit(p,{"action":"media_reorder","clip_id":"media_"+digit*32,"position":position})
    assert p==before and p["manual"]["history"]["redo_count"]==1


def test_single_visual_and_audio_slots_have_no_order_change(unlocked):
    _,_,store,pid=unlocked;p=store.load(pid);mixed_layers(p)
    p["manual"]["media_clips"]=[media_row("3",AUDIO,0.,1.),media_row("1",VIDEO,0.,1.),media_row("4",AUDIO,2.,3.)]
    before=copy.deepcopy(p)
    for position in ("front","back","forward","backward"):
        apply_manual_edit(p,{"action":"media_reorder","clip_id":"media_"+"1"*32,"position":position})
        assert p==before


def test_capacity_and_nonoverlapping_visuals_have_deterministic_global_order(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p)
        p["manual"]["media_clips"]=[media_row("1",AUDIO if i%3==1 else VIDEO,1.+i%10,2.+i%10,id=f"media_{i:032x}") for i in range(200)]
    store.update(pid,prepare);before=store.load(pid);rows=before["manual"]["media_clips"]
    assert post(unlocked,"media_reorder",clip_id="media_"+"0"*32,position="front").status_code==200
    moved=store.load(pid)["manual"]["media_clips"]
    assert len(moved)==200 and moved[198]==rows[0] and moved[199]==rows[199]
    assert [r for r in moved if before["assets"][r["asset_id"]]["kind"]=="video"]==[r for r in rows[1:] if before["assets"][r["asset_id"]]["kind"]=="video"]+[rows[0]]
    assert all(moved[i]==rows[i] for i in range(200) if i%3==1)


def test_stale_revision_does_not_replay_relative_stacking_action(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    assert post(unlocked,"media_reorder",clip_id="media_"+"4"*32,position="back").status_code==200
    before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_reorder",clip_id="media_"+"2"*32,position="forward",expected_revision=revision).status_code==409
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_encoded_stacking_changes_visual_priority_only_and_retains_sound(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"stack-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:]);store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    def configure(p):
        p["manual"]["media_clips"][0].update(motion=motion,x=0.,y=0.,w=1.,h=1.)
        p["manual"]["media_clips"][2].update(x=0.,y=0.,w=1.,h=1.,motion="pan")
        p["manual"]["media_clips"].insert(2,media_row("4",ASSET,.5,2.5,source_start=0.,video_source_start=.25,speed=1.5,fade_in=.15,fade_out=.3,x=0.,y=0.,w=1.,h=1.,role="voice",volume_db=-9.))
    store.update(pid,configure);original,old_record=encoded("stack-original");before_manual=copy.deepcopy(store.load(pid)["manual"])
    # Independent reference permutes visual slots, including two audible videos, not the intervening music.
    def reference(p):
        rows=p["manual"]["media_clips"];rows[0],rows[2],rows[3]=rows[2],rows[3],rows[0]
    store.update(pid,reference);expected,expected_record=encoded("stack-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before_manual)))
    before=content(store.load(pid));response=post(library_api,"media_reorder",clip_id="media_"+"1"*32,position="front");assert response.status_code==200,response.get_json()
    after=content(store.load(pid));assert post(library_api,"undo").status_code==200 and content(store.load(pid))==before
    assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    actual,record=encoded("stack-actual")
    assert record["manual_text_count"]==1 and store.load(pid)["manual"]["media_clips"][1]==before_manual["media_clips"][1]
    for r in (old_record,expected_record,record):assert r["duration"]==pytest.approx(3.,abs=1/30)
    old_audio,wanted_audio,new_audio=(samples(media[1],path) for path in (original,expected,actual))
    for at in (.3,.6,.9,1.3,1.9,2.3,2.6):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):
            want,got=pixel(media[1],expected,at,x,y),pixel(media[1],actual,at,x,y)
            assert max(abs(a-b) for a,b in zip(want,got))<24,(speed,at,want,got)
        for hz in (440,880):
            assert tone_level(new_audio,at,hz)==pytest.approx(tone_level(wanted_audio,at,hz),abs=.003)
            assert tone_level(new_audio,at,hz)==pytest.approx(tone_level(old_audio,at,hz),abs=.003)
    # Originally the yellow image hides the moving picture; now the video wins.
    old,new=pixel(media[1],original,1.3,120,45),pixel(media[1],actual,1.3,120,45)
    assert old[0]>180 and old[1]>180 and old[2]<60
    assert sum(abs(a-b) for a,b in zip(old,new))>80,(old,new)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==3 and all(p.exists() for p in (original,expected,actual))
