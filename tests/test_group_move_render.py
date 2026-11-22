"""Actual grouped playback/export equivalence, not a mocked render success."""
from __future__ import annotations
import copy
import hashlib
import subprocess
import pytest
from cutroom.projects import ProjectStore
from test_media_append import content, library_api  # noqa: F401
from test_media_render import media  # noqa: F401
from test_mixed_media_insert import post
from test_selected_layer_trim import render_setup


@pytest.mark.parametrize("speed,motion", [(.5,"pan"),(2.,"zoom_in")])
def test_real_encoded_group_move_preserves_picture_audio_phase_and_one_history(library_api,media,speed,motion):
    from test_media_render import pixel,samples,tone_level
    pattern=media[0]/f"group-move-pattern-{speed}.mp4"
    subprocess.run([media[1],"-v","error","-y","-f","lavfi","-i","testsrc2=s=160x90:r=30:d=3","-f","lavfi","-i","aevalsrc='if(between(t,1,2),0.3*sin(2*PI*440*t),0)':s=48000:d=3","-c:v","libx264","-preset","ultrafast","-c:a","aac","-t","3",str(pattern)],check=True,capture_output=True,timeout=20)
    generated=(*media[:3],pattern,*media[4:]);store,pid,settings,encoded,hashes,originals=render_setup(library_api,generated,speed)
    def configure(p):
        for row in p["manual"]["media_clips"]:
            row.update(start=.2,end=1.2)
            if p["assets"][row["asset_id"]]["kind"]!="image":row.update(source_start=.5,fade_in=.2,fade_out=.2)
        p["manual"]["media_clips"][0].update(video_source_start=.5,motion=motion)
        p["manual"]["text_clips"][0].update(start=.2,end=1.2)
    store.update(pid,configure);original,original_record=encoded("group-original");before_manual=copy.deepcopy(store.load(pid)["manual"])
    def reference(p):
        for key in ("media_clips","text_clips"):
            for row in p["manual"][key]:row.update(start=1.6,end=2.6)
    store.update(pid,reference);expected,expected_record=encoded("group-reference")
    store.update(pid,lambda p:p.update(manual=copy.deepcopy(before_manual)))
    before=content(store.load(pid))
    ids=["media_"+digit*32 for digit in "123"]+["text_"+"1"*32]
    response=post(library_api,"layers_move",clip_ids=ids,delta=1.4)
    assert response.status_code==200,response.get_json()
    after=content(store.load(pid))
    assert store.load(pid)["manual"]["history"]=={"undo_count":1,"redo_count":0}
    for key in ("media_clips","text_clips"):
        for old,new in zip(before_manual[key],store.load(pid)["manual"][key]):
            assert {**new,"start":old["start"],"end":old["end"]}==old
    assert post(library_api,"undo").status_code==200 and content(store.load(pid))==before
    assert post(library_api,"redo").status_code==200 and content(ProjectStore(settings).load(pid))==after
    actual,record=encoded("group-actual")
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
