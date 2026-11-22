"""Whole-occurrence copies at an explicit destination, without ripple or truncation."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.projects import ProjectStore
from test_media_append import ASSET, content, library_api  # noqa: F401
from test_media_insert import unlocked  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import mixed_layers, media_row, text_row, VIDEO, AUDIO, IMAGE, post
from test_selected_layer_trim import render_setup


@pytest.mark.parametrize("key,index", [("media_clips",1),("media_clips",2),("media_clips",3),("text_clips",1),("text_clips",2)])
@pytest.mark.parametrize("destination", [0.,8.123456])
def test_duplicate_preserves_full_occurrence_and_other_layers_selectable_new_id_history_reopen(unlocked,key,index,destination):
    app,_,store,pid=unlocked
    def prepare(value):
        mixed_layers(value);value["manual"]["track_locks"]={"A":True,"B":True}
        if key=="media_clips" and index==1:value["manual"][key][index]["motion"]="pan"
    store.update(pid,prepare);before=store.load(pid);old=before["manual"][key][index]
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (store.project_dir(pid)/"media").rglob("*") if p.is_file()}
    action="text_duplicate" if key=="text_clips" else "media_duplicate"
    response=post(unlocked,action,clip_id=old["id"],start=destination)
    assert response.status_code==200,response.get_json()
    after=store.load(pid);new=after["manual"][key][-1]
    assert after["manual"][key][:-1]==before["manual"][key]
    assert new["id"] not in {row["id"] for row in before["manual"][key]}
    assert new["start"]==destination and new["end"]-new["start"]==pytest.approx(old["end"]-old["start"],abs=1e-8)
    for field,value in old.items():
        if field not in ("id","start","end"):assert new[field]==value
    for field,value in before["manual"].items():
        if field not in (key,"history","_history"):assert after["manual"][field]==value
    for field in ("assets","sources","analysis"):assert after[field]==before[field]
    assert after["manual"]["sequence"]["duration"]==15.
    assert after["manual"]["history"]=={"undo_count":1,"redo_count":0}
    assert post(unlocked,"undo").status_code==200 and content(store.load(pid))==content(before)
    assert post(unlocked,"redo").status_code==200 and content(ProjectStore(app.extensions["cutroom_settings"]).load(pid))==content(after)
    # Removing the actual new copy cannot remove the original occurrence.
    assert post(unlocked,"text_remove" if key=="text_clips" else "media_remove",clip_id=new["id"]).status_code==200
    assert store.load(pid)["manual"][key]==before["manual"][key]
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes


@pytest.mark.parametrize("action,clip", [("media_duplicate","media_"+"2"*32),("text_duplicate","text_"+"2"*32)])
@pytest.mark.parametrize("start", [-1.,14.99,True,None])
def test_duplicate_invalid_or_insufficient_room_rejects_atomically(unlocked,action,clip,start):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    response=post(unlocked,action,clip_id=clip,start=start)
    assert response.status_code==400,response.get_json()
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("key,count", [("media_clips",200),("text_clips",2000)])
def test_duplicate_capacity_does_not_replace_an_existing_occurrence(unlocked,key,count):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p)
        if key=="media_clips":p["manual"][key]=[media_row("1",VIDEO,4.,6.,id=f"media_{i:032x}") for i in range(count)]
        else:
            p["manual"]["sequence"]["duration"]=300.
            p["manual"][key]=[text_row("1",i*.1,i*.1+.08,id=f"text_{i:032x}") for i in range(count)]
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    action,prefix=("media_duplicate","media_") if key=="media_clips" else ("text_duplicate","text_")
    response=post(unlocked,action,clip_id=prefix+"0"*32,start=0.)
    assert response.status_code==400 and str(count) in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==before


def test_duplicate_text_overlap_limit_and_exact_nonoverlap_boundary(unlocked):
    _,_,store,pid=unlocked
    def prepare(p):
        mixed_layers(p);p["manual"]["text_clips"]=[text_row("1",1.,3.,id=f"text_{i:032x}") for i in range(16)]
    store.update(pid,prepare);before=store.state_path(pid).read_bytes()
    response=post(unlocked,"text_duplicate",clip_id="text_"+"0"*32,start=2.)
    assert response.status_code==400 and "16" in response.get_json()["message"]
    assert store.state_path(pid).read_bytes()==before
    assert post(unlocked,"text_duplicate",clip_id="text_"+"0"*32,start=3.).status_code==200


@pytest.mark.parametrize("action,clip,start", [("media_duplicate","media_"+"2"*32,13.),("text_duplicate","text_"+"2"*32,12.)])
def test_exact_end_fit_and_legacy_api_default_are_supported(unlocked,action,clip,start):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);key="text_clips" if action=="text_duplicate" else "media_clips"
    old=next(row for row in store.load(pid)["manual"][key] if row["id"]==clip)
    assert post(unlocked,action,clip_id=clip,start=start).status_code==200
    assert store.load(pid)["manual"][key][-1]["end"]==15.
    assert post(unlocked,"undo").status_code==200
    assert post(unlocked,action,clip_id=clip).status_code==200
    new=store.load(pid)["manual"][key][-1];assert (new["start"],new["end"])==(old["start"],old["end"])


@pytest.mark.parametrize("action,clip", [("media_duplicate","media_"+"a"*32),("text_duplicate","text_"+"a"*32),("text_duplicate","automatic_caption"),("media_duplicate","A:sequence:0:0")])
def test_stale_or_unsupported_target_never_duplicates_underlying_footage(unlocked,action,clip):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);before=store.state_path(pid).read_bytes()
    assert post(unlocked,action,clip_id=clip,start=0.).status_code==400
    assert store.state_path(pid).read_bytes()==before


def test_unready_asset_and_revision_conflict_remain_atomic(unlocked):
    _,_,store,pid=unlocked;store.update(pid,mixed_layers);revision=store.load(pid)["revision"]
    store.update(pid,lambda p:p.update(name="Elsewhere"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_duplicate",clip_id="media_"+"2"*32,start=0.,expected_revision=revision).status_code==409
    assert store.state_path(pid).read_bytes()==before
    store.update(pid,lambda p:p["assets"][VIDEO].update(status="failed"));before=store.state_path(pid).read_bytes()
    assert post(unlocked,"media_duplicate",clip_id="media_"+"2"*32,start=0.).status_code==400
    assert store.state_path(pid).read_bytes()==before


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_encoded_copies_match_reference_and_replay_original_content_at_new_position(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"duplicate-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:])
    store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    def configure(p):
        for row in p["manual"]["media_clips"]:
            row.update(start=.2,end=1.2)
            if p["assets"][row["asset_id"]]["kind"]!="image":row.update(source_start=.5,fade_in=.2,fade_out=.2)
        p["manual"]["media_clips"][0].update(video_source_start=.5,motion=motion)
        p["manual"]["text_clips"][0].update(start=.2,end=1.2)
    store.update(pid,configure);original,original_record=encoded("duplicate-original")
    before_manual=copy.deepcopy(store.load(pid)["manual"])
    def reference(p):
        for key,prefix in (("media_clips","media_"),("text_clips","text_")):
            rows=copy.deepcopy(p["manual"][key])
            p["manual"][key].extend({**r,"id":prefix+f"{100+i:032x}","start":1.6,"end":2.6} for i,r in enumerate(rows))
    store.update(pid,reference);expected,expected_record=encoded("duplicate-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before_manual)))
    for action,clip_id in [("media_duplicate","media_"+digit*32) for digit in "123"]+[("text_duplicate","text_"+"1"*32)]:
        before=content(store.load(pid));response=post(library_api,action,clip_id=clip_id,start=1.6);assert response.status_code==200,response.get_json()
        after=content(store.load(pid));assert post(library_api,"undo").status_code==200 and content(store.load(pid))==before
        assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    actual,record=encoded("duplicate-actual")
    assert len(store.load(pid)["manual"]["media_clips"])==6 and record["manual_text_count"]==2
    for r in (original_record,expected_record,record):assert r["duration"]==pytest.approx(3.,abs=1/30)
    old_audio,wanted_audio,new_audio=(samples(media[1],path) for path in (original,expected,actual))
    for at in (.3,.5,.9,1.1,1.7,1.9,2.3,2.5):
        for x,y in ((30,15),(50,40),(120,15),(80,75)):
            want,got=pixel(media[1],expected,at,x,y),pixel(media[1],actual,at,x,y)
            assert max(abs(a-b) for a,b in zip(want,got))<24,(speed,at,want,got)
        for hz in (440,880):assert tone_level(new_audio,at,hz)==pytest.approx(tone_level(wanted_audio,at,hz),abs=.008)
    for old_time,new_time in ((.3,1.7),(.5,1.9),(.9,2.3),(1.1,2.5)):
        # Fast H.264 quantizes this high-detail moving pattern differently at
        # the second GOP. Compare the full picture region, not one noisy pixel;
        # the independently constructed reference above still matches at every
        # sampled point. Both placements use exact output-frame boundaries.
        def picture_region(path, at):
            frame=subprocess.check_output([media[1],"-v","error","-ss",str(at),"-i",str(path),"-an","-frames:v","1","-pix_fmt","rgb24","-f","rawvideo","pipe:1"])
            return [frame[(y*160+x)*3+c] for y in range(5,45) for x in range(5,75) for c in range(3)]
        old,new=picture_region(original,old_time),picture_region(actual,new_time)
        assert sum(abs(a-b) for a,b in zip(old,new))/len(old)<10,(speed,old_time,new_time)
        old_still,new_still=pixel(media[1],original,old_time,120,15),pixel(media[1],actual,new_time,120,15)
        assert max(abs(a-b) for a,b in zip(old_still,new_still))<24
        for hz in (440,880):assert tone_level(new_audio,new_time,hz)==pytest.approx(tone_level(old_audio,old_time,hz),abs=.008)
    assert tone_level(old_audio,2.3,440)<.003 and tone_level(new_audio,2.3,440)>.2
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}==hashes
    assert len(store.load(pid)["exports"])==3 and all(p.exists() for p in (original,expected,actual))
