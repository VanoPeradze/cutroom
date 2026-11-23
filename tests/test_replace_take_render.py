"""Real encoded checks: the same edited shot gets new independent picture and 1x sound."""
import copy
import math
import subprocess

import pytest
from cutroom.editing import apply_manual_edit
from test_media_render import media
from test_replace_take import NEW
from test_rolling_edit import L, R
from test_rolling_edit_render import native_export
from test_slide_edit import M
from test_slide_edit_render import signals, audio_signals, sequence, decode, hue


@pytest.fixture(scope="module")
def alternate(media):
    ff=media[1];root=media[0];f=root/"alternate-take.mp4"
    pic=r"color=c=magenta:s=160x90:r=60:d=3,drawbox=x=0:y=0:w=iw:h=ih/4:color=white:t=fill:enable='lt(mod(t,1),0.5)'"
    tone=r"aevalsrc=0.2*sin(2*PI*if(lt(mod(t\,1)\,0.5)\,730\,1460)*t):s=48000:d=3"
    subprocess.run([ff,"-v","error","-n","-f","lavfi","-i",pic,"-f","lavfi","-i",tone,"-threads","2","-c:v","libx264","-pix_fmt","yuv420p","-c:a","aac","-b:a","192k",str(f)],check=True,timeout=20)
    return {"id":NEW,"kind":"video","status":"ready","duration":3.,"path":f.name,"has_audio":True,"width":160,"height":90}


def replacement(p,kind="video"):
    old=p["manual"]["media_clips"][1]["asset_id"]
    apply_manual_edit(p,{"action":"media_replace_take","clip_id":M,"previous_asset_id":old,"asset_id":NEW,**({"source_start":.63,"source_end":2.4} if kind!="image" else {})})


def magenta(f):
    band=f[7*24*3:]
    r,g,b=(sum(band[i::3])/(len(band)//3) for i in range(3))
    return min(r,b)>180 and g<40


def tone(v, sample):
    b=v[sample-512:sample+512]
    def power(h):return sum(x*math.cos(2*math.pi*i*h/48000) for i,x in enumerate(b))**2+sum(x*math.sin(2*math.pi*i*h/48000) for i,x in enumerate(b))**2
    return max((440,660,700,1050,730,1460,1100,1650),key=power)


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("speed",[.5,2.])
def test_video_after_slide_source_phase_timing_color_and_normal_sound(signals,alternate,media,tmp_path,fps,speed):
    p,beg,count=sequence(signals,fps,True);p["assets"][NEW]=copy.deepcopy(alternate)
    c=p["manual"]["media_clips"][1];c["video_source_start"]=.77;c["speed"]=speed
    apply_manual_edit(p,{"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":beg+3})
    c=p["manual"]["media_clips"][1];start,end=c["start"],c["end"];first=beg+3
    before,x=decode(media,native_export(p,media,tmp_path/"a"));replacement(p)
    after,y=decode(media,native_export(p,media,tmp_path/"b"));assert len(after)==len(before)==3*fps
    outside=[];pic_windows=0;aud_windows=0
    for n,(a,b) in enumerate(zip(before,after)):
        t=n/fps;middle=first<=n<first+count
        assert magenta(b)==middle and not magenta(a)
        if not middle:
            assert hue(a)==hue(b);outside.append(sum(abs(i-j) for i,j in zip(a,b))/len(a));continue
        assert hue(a)=="green"
        # Different clocks: a picture-rate mistake shifts the flashing bar,
        # but ordinary recorded sound must keep its own 1x half-second alternation.
        picture=.63+(t-start)*speed;audio=.63+t-start
        if min(picture%.5,.5-picture%.5)>.08:
            g=sum(b[(1*24)*3+1:(2*24)*3:3])/24
            assert (g>160)==(picture%1<.5),(fps,speed,n,picture,g);pic_windows+=1
        if min(t-start,end-t)>.06 and min(audio%.5,.5-audio%.5)>.05:
            assert tone(y,round(t*48000))==(730 if audio%1<.5 else 1460);aud_windows+=1
    assert max(outside)<4 and pic_windows>=3 and aud_windows>=3
    left=round((start-.16)*48000);right=round((end+.12)*48000)
    for lo,hi in ((12000,left),(right,120000)):
        z,w=x[lo:hi],y[lo:hi]
        assert sum(i*j for i,j in zip(z,w))/math.sqrt(sum(i*i for i in z)*sum(j*j for j in w))>.99


def test_audio_replacement_changes_only_sound_and_keeps_fades(audio_signals,alternate,media,tmp_path):
    p,beg,count=sequence(audio_signals,30,True);p["manual"]["layer_tracks"]["tracks"][0]["kind"]="audio"
    for r in p["manual"]["media_clips"]:r.update(speed=1.,motion="none");r.pop("video_source_start",None)
    asset=copy.deepcopy(alternate);wav=media[0]/"alternate-take.wav"
    subprocess.run([media[1],"-v","error","-n","-i",str(media[0]/asset["path"]),"-vn","-c:a","pcm_s16le",str(wav)],check=True,timeout=12)
    asset.update(path=wav.name,kind="audio",width=0,height=0);p["assets"][NEW]=asset
    pre,x=decode(media,native_export(p,media,tmp_path/"a"));replacement(p,"audio");after,y=decode(media,native_export(p,media,tmp_path/"b"));assert pre==after
    start=p["manual"]["media_clips"][1]["start"];a,b=round((start+.16)*48000),round((start+.42)*48000)
    assert tone(y,a)==1460 and tone(y,b)==730 and tone(x,a)!=tone(y,a) and tone(x,b)!=tone(y,b)
    level=lambda center:math.sqrt(sum(v*v for v in y[center-256:center+256])/512)
    assert .04<level(a) and level(round((start+.02)*48000))<level(a)*.50


def test_still_replacement_changes_only_image_and_adds_no_sound(signals,media,tmp_path):
    p,first,count=sequence(signals,30,False);c=p["manual"]["media_clips"][1]
    for ident,col in ((c["asset_id"],"lime"),(NEW,"magenta")):
        f=media[0]/("replace-"+col+".png")
        subprocess.run([media[1],"-v","error","-n","-f","lavfi","-i",f"color={col}:s=160x90:d=.1".replace("d=.1","d=0.1"),"-frames:v","1","-threads","1",str(f)],check=True,timeout=12)
        p["assets"][ident]={"id":ident,"status":"ready","kind":"image","duration":0.,"width":160,"height":90,"has_audio":False,"path":f.name}
    c.update(speed=1.,source_start=0.,audio_enabled=False);c.pop("video_source_start");pre,x=decode(media,native_export(p,media,tmp_path/"a"));replacement(p,"image")
    aft,y=decode(media,native_export(p,media,tmp_path/"b"));assert x==y
    assert [i for i,fr in enumerate(aft) if magenta(fr)]==list(range(first,first+count))
    assert all(hue(pre[i])=="green" for i in range(first,first+count))
