"""Compare real rendered pictures and audio before/after a three-point slide."""
import copy,math,subprocess
from array import array
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.frame_rates import first_display_frame
from test_media_render import media,project
from test_mixed_media_insert import media_row
from test_rolling_edit import L,R,T
from test_rolling_edit_render import native_export
from test_slide_edit import M


@pytest.fixture(scope="module")
def signals(media):
    root,ffmpeg,*_=media; ids=["asset_"+c*32 for c in "142"];assets={}
    for i,(color,hz) in enumerate([("red",440),("lime",700),("blue",1100)]):
        f=root/f"slide-{i}.mp4";ident=ids[i]
        picture=f"color=c={color}:s=160x90:r=60:d=3,drawgrid=w=30:h=300:t=2:c=black,drawbox=x=0:y=0:w=iw:h=ih/4:color=white:t=fill:enable='lt(mod(t,1),0.5)'"
        tone=rf"aevalsrc=0.20*sin(2*PI*if(lt(mod(t\,1)\,0.5)\,{hz}\,{hz*1.5})*t):s=48000:d=3"
        subprocess.run([ffmpeg,"-v","error","-n","-f","lavfi","-i",picture,"-f","lavfi","-i",tone,"-threads","2","-c:v","libx264","-pix_fmt","yuv420p","-preset","veryfast","-c:a","aac","-b:a","192k",str(f)],check=True,timeout=20)
        assets[ident]={"id":ident,"name":color,"kind":"video","status":"ready","duration":3.,"width":160,"height":90,"has_audio":True,"path":f.name}
    return assets,ids


def sequence(signals,fps,subframe):
    p=project();p["settings"]["fps"]=fps;p["draft"]["output_duration"]=3.;p["assets"]=copy.deepcopy(signals[0]);a,b,c=signals[1]
    first,count=fps+1,max(8,fps//2)
    start=(first-.37)/fps if subframe else round(first/fps,9);end=(first+count-.81)/fps if subframe else round((first+count)/fps,9)
    def row(k,a,i,o,**rest):return media_row(k,a,i,o,track_id=T,x=0.,y=0.,w=1.,h=1.,fit="cover",audio_enabled=True,role="voice",volume_db=0.,**rest)
    p["manual"].update(media_clips=[
        row("2",c,end,2.88,source_start=1.,video_source_start=.7,speed=.5,fade_in=0.,fade_out=.15),
        row("4",b,start,end,source_start=.28,video_source_start=.28,speed=2.,motion="pan",fade_in=.11,fade_out=.13),
        row("1",a,.16,start,source_start=.8,video_source_start=.4,speed=1.5,fade_in=.08,fade_out=0.)],
        audio_mixer={"source_muted":True},layer_tracks={"version":1,"tracks":[{"kind":"visual","name":"Three shots","id":T}]})
    return p,first,count


def decode(media,out):
    ff=media[1]
    raw=subprocess.check_output([ff,"-v","error","-i",str(out),"-an","-vf","scale=24:14","-pix_fmt","rgb24","-f","rawvideo","pipe:1"],timeout=15)
    size=24*14*3;assert len(raw)%size==0
    pcm=array("f",subprocess.check_output([ff,"-v","error","-i",str(out),"-vn","-ac","1","-ar","48000","-f","f32le","pipe:1"],timeout=15))
    return [raw[n:n+size] for n in range(0,len(raw),size)],pcm


def hue(frame):
    vals=[sum(frame[7*24*3+k::3]) for k in range(3)]
    return ["red","green","blue"][vals.index(max(vals))]


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("subframe",[False,True])
@pytest.mark.parametrize("step",[-4,5])
def test_center_pixels_source_motion_and_sound_translate_by_exact_frames(signals,media,tmp_path,fps,subframe,step):
    p,first,count=sequence(signals,fps,subframe);pre,old_audio=decode(media,native_export(p,media,tmp_path/"pre"))
    apply_manual_edit(p,{"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":first+step})
    center=p["manual"]["media_clips"][1]
    assert (first_display_frame(center["start"],fps),first_display_frame(center["end"],fps))==(first+step,first+count+step)
    aft,new_audio=decode(media,native_export(p,media,tmp_path/"post"))
    assert len(pre)==len(aft)==3*fps
    for pictures,beg in [(pre,first),(aft,first+step)]:
        assert [hue(frame) for frame in pictures[beg-2:beg+count+2]]==["red"]*2+["green"]*count+["blue"]*2
    # Not just a color test: the asymmetric moving grid and flashing top bar
    # expose source-clock, motion-phase or repeated-frame errors inside the shot.
    image_errors=[sum(abs(a-b) for a,b in zip(pre[n],aft[n+step]))/len(pre[n]) for n in range(first,first+count)]
    assert max(image_errors)<5.,image_errors
    # AAC packet boundaries differ after retiming; allow codec noise but not a
    # source offset, missing center audio, re-timed pitch or reshaped envelope.
    samples=48000//fps;lo=first*samples+1800;hi=(first+count)*samples-1800
    x,y=old_audio[lo:hi],new_audio[lo+step*samples:hi+step*samples]
    xx=sum(a*a for a in x);yy=sum(a*a for a in y);xy=sum(a*b for a,b in zip(x,y))
    assert len(x)==len(y)>10000 and xx>8 and yy>8
    assert xy/math.sqrt(xx*yy)>.975 and .96<math.sqrt(yy/xx)<1.04


@pytest.mark.parametrize("fps",[25,50])
@pytest.mark.parametrize("normalized",[False,True])
def test_marked_export_preserves_the_same_slid_shot_frames_at_25_and_50(signals,media,tmp_path,fps,normalized):
    p,first,count=sequence(signals,fps,True)
    apply_manual_edit(p,{"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":first+5})
    whole,audio=decode(media,native_export(p,media,tmp_path/"full",normalize=normalized))
    beg,fin=6,3*fps-4
    part,short=decode(media,native_export(p,media,tmp_path/"part",(beg,fin),normalized))
    assert len(whole)==3*fps and len(part)==fin-beg
    assert [hue(fr) for fr in part]==[hue(fr) for fr in whole[beg:fin]]
    assert max(sum(abs(a-b) for a,b in zip(fr,qr))/len(fr) for fr,qr in zip(part,whole[beg:fin]))<5.
    k=48000//fps;lo,hi=2400,len(part)*k-2400
    x,y=audio[beg*k+lo:beg*k+hi],short[lo:hi];assert len(x)==len(y)>70000
    corr=sum(a*b for a,b in zip(x,y))/math.sqrt(sum(a*a for a in x)*sum(b*b for b in y))
    assert corr>.985


@pytest.fixture(scope="module")
def audio_signals(media,signals):
    assets,ids=copy.deepcopy(signals)
    for asset in assets.values():
        src=media[0]/asset["path"];wav=src.with_suffix(".wav")
        subprocess.run([media[1],"-v","error","-n","-i",str(src),"-vn","-c:a","pcm_s16le",str(wav)],check=True,timeout=12)
        asset.update(kind="audio",path=wav.name,width=0,height=0)
    return assets,ids


@pytest.mark.parametrize("step",[-6,8])
def test_audio_only_slide_keeps_the_picture_fixed_and_moves_the_same_recording(audio_signals,media,tmp_path,step):
    fps=30;p,first,count=sequence(audio_signals,fps,False)
    p["manual"]["layer_tracks"]["tracks"][0]["kind"]="audio"
    for row in p["manual"]["media_clips"]:
        row.pop("video_source_start");row.update(speed=1.,motion="none")
    before,x=decode(media,native_export(p,media,tmp_path/"a"))
    apply_manual_edit(p,{"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":first+step})
    after,y=decode(media,native_export(p,media,tmp_path/"b"));assert before==after
    a,b=(first+1)*1600,(first+count-1)*1600;left=x[a:b];right=y[a+step*1600:b+step*1600]
    corr=sum(i*j for i,j in zip(left,right))/math.sqrt(sum(i*i for i in left)*sum(j*j for j in right))
    assert corr>.985 and len(left)==len(right)
    pivot=(first+step//2)*1600
    def frequency(v):
        block=v[pivot:pivot+1024]
        def power(h):return abs(sum(z*complex(math.cos(j*2*math.pi*h/48000),math.sin(j*2*math.pi*h/48000)) for j,z in enumerate(block)))**2
        return max([440,660,700,1050],key=power)
    assert (frequency(x) in (700,1050))==(step>0)
    assert (frequency(y) in (700,1050))==(step<0)


def test_slide_a_still_between_two_videos_without_inventing_sound(signals,media,tmp_path):
    p,first,count=sequence(signals,30,False);m=p["manual"]["media_clips"][1];asset=p["assets"][m["asset_id"]]
    still=tmp_path/"slide-still.png"
    subprocess.run([media[1],"-v","error","-n","-i",str(media[0]/asset["path"]),"-frames:v","1",str(still)],check=True,timeout=10)
    # native_export copies the fixture paths into a new safe project store.
    asset.update(kind="image",path=str(still),duration=0.,has_audio=False)
    m.update(speed=1.,source_start=0.,audio_enabled=False);m.pop("video_source_start")
    pre,x=decode(media,native_export(p,media,tmp_path/"still-pre"))
    step=6;apply_manual_edit(p,{"action":"media_slide","left_id":L,"clip_id":M,"right_id":R,"frame":first+step})
    aft,y=decode(media,native_export(p,media,tmp_path/"still-post"));assert len(pre)==len(aft)==90
    assert [hue(fr) for fr in aft[first+step-1:first+count+step+1]]==["red"]+["green"]*count+["blue"]
    assert max(sum(abs(a-b) for a,b in zip(pre[i],aft[i+step]))/len(pre[i]) for i in range(first,first+count))<4.
    for pcm,n in ((x,first),(y,first+step)):
        silence=pcm[(n+2)*1600:(n+count-2)*1600];assert max(abs(z) for z in silence)<.002
