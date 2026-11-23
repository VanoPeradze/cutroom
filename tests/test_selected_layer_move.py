"""Fixed-duration placement keeps one occurrence's content, phase and identity."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.projects import ProjectStore
from cutroom.editing import apply_manual_edit
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post
from test_selected_layer_trim import render_setup


@pytest.mark.parametrize("key,index", [("media_clips",1),("media_clips",2),("media_clips",3),("text_clips",1),("text_clips",2)])
@pytest.mark.parametrize("destination", [0.,8.123456])
def test_move_preserves_identity_full_content_other_layers_history_and_reopen(unlocked,key,index,destination):
    app,_,store,pid=unlocked
    def prepare(value):
        mixed_layers(value);value["manual"]["track_locks"]={"A":True,"B":True}
        if key=="media_clips" and index==1:value["manual"][key][index]["motion"]="pan"
    store.update(pid,prepare);before=store.load(pid);old=before["manual"][key][index]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    action="text_move" if key=="text_clips" else "media_move"
    response=post(unlocked,action,clip_id=old["id"],start=destination)
    assert response.status_code==200,response.get_json()
    after=store.load(pid);new=after["manual"][key][index]
    expected=copy.deepcopy(before["manual"][key]);expected[index].update(start=destination,end=round(destination+old["end"]-old["start"],6 if key=="text_clips" else 9))
    assert after["manual"][key]==expected and new["id"]==old["id"]
    for field,value in before["manual"].items():
        if field not in (key,"history","_history"):assert after["manual"][field]==value
    for field in ("assets","sources","analysis"):assert after[field]==before[field]
    assert after["manual"]["sequence"]["duration"]==15.
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes


@pytest.mark.parametrize("action,clip", [("media_move","media_"+"2"*32),("text_move","text_"+"2"*32)])
@pytest.mark.parametrize("start", [-1.,14.99,True,None])
def test_invalid_or_insufficient_room_rejects_without_clamping_or_truncation(unlocked,action,clip,start):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,action,clip_id=clip,start=start)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("action,clip", [("media_move","media_"+"2"*32),("text_move","text_"+"2"*32)])
def test_move_requires_explicit_destination_and_rejects_timing_or_content_patch_fields(unlocked,action,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    for fields in ({},{"start":0.,"end":1.},{"start":0.,"source_start":2.}):
        response=post(unlocked,action,clip_id=clip,**fields)
        assert response.status_code==400,response.get_json()
        assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("key,count", [("media_clips",200),("text_clips",2000)])
def test_move_is_allowed_at_occurrence_capacity_because_it_creates_no_copy(unlocked,key,count):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p)
        if key=="media_clips":p["manual"][key]=[media_row("1",VIDEO,4.,6.,id=f"media_{i:032x}") for i in range(count)]
        else:
            p["manual"]["sequence"]["duration"]=300.
            p["manual"][key]=[text_row("1",i*.1,i*.1+.08,id=f"text_{i:032x}") for i in range(count)]
    store.update(pid,prepare);before=store.load(pid)
    action,prefix,start=("media_move","media_",0.) if key=="media_clips" else ("text_move","text_",299.)
    response=post(unlocked,action,clip_id=prefix+"0"*32,start=start)
    assert response.status_code==200,response.get_json()
    after=store.load(pid);assert len(after["manual"][key])==count
    assert after["manual"][key][1:]==before["manual"][key][1:]


def test_text_move_overlap_limit_excludes_old_position_and_allows_exact_adjacency(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["text_clips"]=[text_row("a",0.,1.)]+[text_row("1",3.,5.,id=f"text_{i:032x}") for i in range(16)]
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"text_move",clip_id="text_"+"a"*32,start=3.)
    assert response.status_code==400 and "16" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==before
    assert post(unlocked,"text_move",clip_id="text_"+"a"*32,start=5.).status_code==200
    # Moving one of the 16 existing occupants inside their common span stays at16.
    assert post(unlocked,"text_move",clip_id="text_"+"0"*32,start=2.5).status_code==200


@pytest.mark.parametrize("key,index", [("media_clips",1),("text_clips",1)])
def test_noop_move_preserves_redo_and_consumes_no_history(unlocked,key,index):
    _,_,store,pid=unlocked;value=store.load(pid);mixed_layers(value)
    if key=="media_clips":value["manual"][key][index]["motion"]="pan"
    old=copy.deepcopy(value["manual"][key][index]);action="text_move" if key=="text_clips" else "media_move"
    apply_manual_edit(value,{"action":action,"clip_id":old["id"],"start":8.})
    apply_manual_edit(value,{"action":"undo"});before=copy.deepcopy(value)
    apply_manual_edit(value,{"action":action,"clip_id":old["id"],"start":old["start"]})
    assert value==before and value["manual"]["history"]["redo_count"]==1


@pytest.mark.parametrize("action,clip,start", [("media_move","media_"+"2"*32,13.),("text_move","text_"+"2"*32,12.)])
def test_exact_edit_end_fit_is_supported_without_sequence_extension(unlocked,action,clip,start):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);key="text_clips" if action=="text_move" else "media_clips"
    assert post(unlocked,action,clip_id=clip,start=start).status_code==200
    new=next(row for row in store.load(pid)["manual"][key] if row["id"]==clip)
    assert new["end"]==15. and store.load(pid)["manual"]["sequence"]["duration"]==15.


@pytest.mark.parametrize("action,clip", [("media_move","media_"+"a"*32),("text_move","text_"+"a"*32),("text_move","automatic_caption"),("media_move","A:sequence:0:0")])
def test_stale_or_unsupported_target_never_moves_underlying_footage(unlocked,action,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,action,clip_id=clip,start=0.).status_code==400
    assert store.state_path(pid).read_bytes()==before


def test_unready_asset_and_revision_conflict_remain_atomic(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Elsewhere"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_move",clip_id="media_"+"2"*32,start=0.,expected_revision=revision).status_code==409
    assert store.state_path(pid).read_bytes()==before
    store.update(pid,lambda p:p["assets"][VIDEO].update(status="failed"));before=store.state_path(pid).read_bytes()
    for at in (0.,4.):
        assert post(unlocked,"media_move",clip_id="media_"+"2"*32,start=at).status_code==400
        assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("key,index,fps", [("media_clips",1,24),("media_clips",2,60),("text_clips",1,24),("text_clips",2,30)])
def test_fractional_origin_frame_nudge_retains_duration_and_reverses_exactly(unlocked,key,index,fps):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["settings"]["fps"]=fps;p["manual"][key][index].update(start=4.123456,end=5.234567)
    store.update(pid,prepare);old=copy.deepcopy(store.load(pid)["manual"][key][index]);action="text_move" if key=="text_clips" else "media_move"
    assert post(unlocked,action,clip_id=old["id"],start=old["start"]+1/fps).status_code==200
    current=store.load(pid)["manual"][key][index]
    assert current["start"]==pytest.approx(old["start"]+1/fps,abs=1e-6)
    assert current["end"]-current["start"]==pytest.approx(old["end"]-old["start"],abs=1e-8)
    assert post(unlocked,action,clip_id=old["id"],start=current["start"]-1/fps).status_code==200
    assert store.load(pid)["manual"][key][index]==old


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_encoded_moves_match_reference_and_preserve_local_content_phase(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"move-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:]);store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    def configure(p):
        for row in p["manual"]["media_clips"]:
            row.update(start=.2,end=1.2)
            if p["assets"][row["asset_id"]]["kind"]!="image":row.update(source_start=.5,fade_in=.2,fade_out=.2)
        p["manual"]["media_clips"][0].update(video_source_start=.5,motion=motion)
        p["manual"]["text_clips"][0].update(start=.2,end=1.2)
    store.update(pid,configure);original,original_record=encoded("move-original");before_manual=copy.deepcopy(store.load(pid)["manual"])
    def reference(p):
        for key in ("media_clips","text_clips"):
            for row in p["manual"][key]:row.update(start=1.6,end=2.6)
    store.update(pid,reference);expected,expected_record=encoded("move-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before_manual)))
    for action,clip_id in [("media_move","media_"+digit*32) for digit in "123"]+[("text_move","text_"+"1"*32)]:
        before=content(store.load(pid));response=post(library_api,action,clip_id=clip_id,start=1.6);assert response.status_code==200,response.get_json()
        after=content(store.load(pid));assert post(library_api,"undo").status_code==200 and content(store.load(pid))==before
        assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    actual,record=encoded("move-actual")
    assert len(store.load(pid)["manual"]["media_clips"])==3 and record["manual_text_count"]==1
    for r in (original_record,expected_record,record):assert r["duration"]==pytest.approx(3.,abs=1/30)
    old_audio,wanted_audio,new_audio=(samples(media[1],path) for path in (original,expected,actual))
    for at in (.3,.5,.9,1.1,1.7,1.9,2.3,2.5):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):
            want,got=pixel(media[1],expected,at,x,y),pixel(media[1],actual,at,x,y)
            assert max(abs(a-b) for a,b in zip(want,got))<24,(speed,at,want,got)
        for hz in (440,880):assert tone_level(new_audio,at,hz)==pytest.approx(tone_level(wanted_audio,at,hz),abs=.008)
    def region(path,at):
        frame=subprocess.check_output([media[1],"-v","error","-ss",str(at),"-i",str(path),"-an","-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"])
        return [frame[(y*160+x)*3+c] for y in range(5,45) for x in range(5,75) for c in range(3)]
    for old_time,new_time in ((.3,1.7),(.5,1.9),(.9,2.3),(1.1,2.5)):
        # Lossy fast H.264 differs across GOPs; compare the decoded moving region.
        old,new=region(original,old_time),region(actual,new_time)
        assert sum(abs(a-b) for a,b in zip(old,new))/len(old)<10,(speed,old_time,new_time)
        for hz in (440,880):assert tone_level(new_audio,new_time,hz)==pytest.approx(tone_level(old_audio,old_time,hz),abs=.008)
    assert tone_level(new_audio,.9,440)<.003 and tone_level(new_audio,.9,880)<.003
    assert tone_level(old_audio,2.3,440)<.003 and tone_level(new_audio,2.3,440)>.2
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==3 and all(p.exists() for p in (original,expected,actual))
