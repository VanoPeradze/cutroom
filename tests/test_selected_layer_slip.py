"""Fixed-range media Slip preserves source-clock offsets and every timeline property."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, VIDEO, AUDIO, IMAGE, post
from test_selected_layer_trim import render_setup, edit_roundtrip


@pytest.mark.parametrize("kind,speed,motion", [(VIDEO,.25,"none"),(VIDEO,.5,"pan"),(VIDEO,1.,"zoom_in"),(VIDEO,2.,"pan"),(VIDEO,4.,"none"),(AUDIO,1.,"none")])
@pytest.mark.parametrize("delta", [-.25,.25])
def test_slip_changes_only_content_and_preserves_fades_motion_selection_and_history(unlocked, kind, speed, motion, delta):
    app, _, store, pid = unlocked
    def prepare(value):
        mixed_layers(value)
        value["manual"]["track_locks"] = {"A":True,"B":True}
        value["manual"]["media_clips"][1] = media_row("2",kind,4.123456789,6.234567891,source_start=2.,video_source_start=3.,speed=speed,motion=motion)
        if kind == AUDIO: value["manual"]["media_clips"][1].pop("video_source_start")
    store.update(pid,prepare)
    before=store.load(pid);old=before["manual"]["media_clips"][1]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    result=post(unlocked,"media_slip",clip_id=old["id"],source_start=old["source_start"]+delta)
    assert result.status_code==200,result.get_json()
    after=store.load(pid);row=after["manual"]["media_clips"][1]
    assert row["source_start"]==old["source_start"]+delta
    if kind==VIDEO: assert row["video_source_start"]==old["video_source_start"]+delta*speed
    for key,value in old.items():
        if key not in ("source_start","video_source_start"): assert row[key]==value
    for key,value in before["manual"].items():
        if key not in ("media_clips","history","_history"): assert after["manual"][key]==value
    assert after["manual"]["media_clips"][:1]==before["manual"]["media_clips"][:1]
    assert after["manual"]["media_clips"][2:]==before["manual"]["media_clips"][2:]
    for key in ("assets","sources","analysis"): assert after[key]==before[key]
    assert after["manual"]["sequence"]["duration"]==15.
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes


@pytest.mark.parametrize("source", [-1.,19.,True,None,"invalid",float("inf")])
def test_slip_invalid_or_unavailable_source_rejects_atomically(unlocked,source):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_slip",clip_id="media_"+"2"*32,source_start=source)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("action", ["media_slip","media_update"])
@pytest.mark.parametrize("source", [0.,.75])
def test_source_change_never_silently_clamps_negative_independent_picture(unlocked,action,source):
    _,_,store,pid=unlocked
    def prepare(value):
        mixed_layers(value);value["manual"]["media_clips"][1].update(source_start=1.,video_source_start=.25,speed=2.)
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    response=post(unlocked,action,clip_id="media_"+"2"*32,source_start=source)
    assert response.status_code==400 and "cannot be clamped" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("clip", ["media_"+"4"*32,"text_"+"2"*32,"A:sequence:0:0","media_"+"a"*32])
def test_slip_unsupported_or_stale_target_does_not_move_another_layer(unlocked,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_slip",clip_id=clip,source_start=1.)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


def test_slip_noop_on_faded_animated_video_consumes_no_history(unlocked):
    _,_,store,pid=unlocked;value=store.load(pid);mixed_layers(value)
    value["manual"]["media_clips"][1]["motion"]="pan";before=copy.deepcopy(value)
    apply_manual_edit(value,{"action":"media_slip","clip_id":"media_"+"2"*32,"source_start":1.})
    assert value==before


@pytest.mark.parametrize("source", [.875,18.])
def test_exact_picture_zero_and_source_out_bounds_are_supported(unlocked,source):
    _,_,store,pid=unlocked
    def prepare(value):
        mixed_layers(value);value["manual"]["media_clips"][1].update(source_start=1.,video_source_start=.25,speed=2.)
    store.update(pid,prepare)
    response=post(unlocked,"media_slip",clip_id="media_"+"2"*32,source_start=source)
    assert response.status_code==200,response.get_json()
    row=store.load(pid)["manual"]["media_clips"][1]
    assert row["video_source_start"]==.25+(source-1.)*2 and (row["start"],row["end"])==(4.,6.)


def test_picture_hold_and_late_source_changes_remain_independent(unlocked):
    _,_,store,pid=unlocked
    def prepare(value):
        mixed_layers(value);value["manual"]["media_clips"][1].update(video_source_start=25.,speed=2.)
    store.update(pid,prepare)
    assert post(unlocked,"media_slip",clip_id="media_"+"2"*32,source_start=2.).status_code==200
    row=store.load(pid)["manual"]["media_clips"][1];assert row["source_start"]==2. and row["video_source_start"]==27.


def test_slip_revision_conflict_and_unready_asset_are_atomic(unlocked):
    _,client,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Other window"));before=store.state_path(pid).read_bytes()
    response=post(unlocked,"media_slip",clip_id="media_"+"2"*32,source_start=2.,expected_revision=revision)
    assert response.status_code==409 and store.state_path(pid).read_bytes()==before
    store.update(pid,lambda p:p["assets"][VIDEO].update(status="failed"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_slip",clip_id="media_"+"2"*32,source_start=2.).status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_encoded_slip_matches_fixed_range_reference_with_fades_motion_and_audio(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"slip-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:])
    store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    store.update(pid,lambda p:p["manual"]["media_clips"][0].update(motion=motion))
    original,original_record=encoded("slip-original")
    before_rows=copy.deepcopy(store.load(pid)["manual"]["media_clips"])
    def reference(p):
        p["manual"]["media_clips"][0].update(source_start=1.,video_source_start=.5+.5*speed)
        p["manual"]["media_clips"][1]["source_start"]=.5
    store.update(pid,reference);expected,expected_record=encoded("slip-reference")
    store.update(pid,lambda p:p["manual"].update(media_clips=copy.deepcopy(before_rows)))
    for digit,start in (("1",1.),("2",.5)):
        edit_roundtrip(library_api,"media_slip",clip_id="media_"+digit*32,source_start=start)
    actual,record=encoded("slip-actual")
    for r in (original_record,expected_record,record):assert r["duration"]==pytest.approx(3.,abs=1/30)
    expected_audio,actual_audio,old_audio=(samples(media[1],path) for path in (expected,actual,original))
    differences=[]
    for at in (.6,.9,1.3,1.8,2.3):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):
            wanted,got= pixel(media[1],expected,at,x,y),pixel(media[1],actual,at,x,y)
            assert max(abs(a-b) for a,b in zip(wanted,got))<24,(speed,motion,at,wanted,got)
            if x<80: differences.append(max(abs(a-b) for a,b in zip(pixel(media[1],original,at,x,y),got)))
        for hz in (440,880):assert tone_level(actual_audio,at,hz)==pytest.approx(tone_level(expected_audio,at,hz),abs=.008)
    def frame(path):
        return subprocess.check_output([media[1],"-v","error","-ss","0.9","-i",str(path),"-an","-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"])
    old_frame,new_frame=frame(original),frame(actual)
    changed=sum(max(abs(old_frame[(y*160+x)*3+c]-new_frame[(y*160+x)*3+c]) for c in range(3))>20 for y in range(90) for x in range(80))
    assert changed>50,"Slip must change decoded source pictures, not just metadata"
    assert tone_level(actual_audio,.9,440)>.2 and tone_level(old_audio,.9,440)<.01
    # Old clip fade timing is preserved at its fixed head and tail.
    assert tone_level(actual_audio,.6,440)==pytest.approx(tone_level(expected_audio,.6,440),abs=.008)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==3 and all(p.exists() for p in (original,expected,actual))
