"""Frame ownership across sparse/VFR source material, input seeks and end holds."""
import subprocess
import pytest
from cutroom.editing import apply_manual_edit
from test_media_render import media
from test_replace_take import NEW
from test_rolling_edit import T
from test_rolling_edit_render import native_export
from test_slide_edit_render import signals,sequence,decode
from test_replace_take_render import alternate


@pytest.fixture(scope="module")
def sparse(media):
    root,ff,*_=media;out=root/"sparse.mp4"
    pic="color=c=red:s=160x90:r=60:d=3,drawbox=x=0:y=0:w=iw:h=ih:color=blue:t=fill:enable='between(n,57,95)',drawbox=x=0:y=0:w=iw:h=ih:color=lime:t=fill:enable='between(n,96,177)',drawbox=x=0:y=0:w=iw:h=ih:color=white:t=fill:enable='gte(n,178)',select='eq(n,0)+eq(n,13)+eq(n,57)+eq(n,96)+eq(n,157)+eq(n,179)'"
    subprocess.run([ff,"-v","error","-n","-f","lavfi","-i",pic,"-f","lavfi","-i","sine=frequency=420:sample_rate=48000:duration=3","-threads","2","-c:v","libx264","-g","2","-bf","0","-fps_mode:v","vfr","-pix_fmt","yuv420p","-c:a","aac",str(out)],check=True,timeout=16)
    return out.name


@pytest.mark.parametrize("mode",["sparse","hold"])
def test_retained_right_uses_the_same_predecessor_even_at_integer_seeks_and_last_frame(media,signals,alternate,sparse,tmp_path,mode):
    fps=30;p,_,_=sequence(signals,fps,True);p["assets"][NEW]=dict(alternate);_,_,l=p["manual"]["media_clips"]
    l.update(start=.13,end=2.87,source_start=.1,video_source_start=.32 if mode=="sparse" else 2.24,speed=.88 if mode=="sparse" else 3.,
             fade_in=0.,fade_out=0.,motion="none",audio_enabled=False)
    p["assets"][l["asset_id"]]["path"]=sparse;p["manual"]["media_clips"]=[l]
    b,_=decode(media,native_export(p,media,tmp_path/"before"));first=27;end=49
    apply_manual_edit(p,{"action":"media_track_overwrite","asset_id":NEW,"track_id":T,"frame":first,"source_start":.5,"source_end":.5+(end-first)/fps})
    a,_=decode(media,native_export(p,media,tmp_path/"after"))
    def color(frame):
        rgb=[sum(frame[j::3])/(len(frame)//3) for j in range(3)]
        return 'white' if min(rgb)>200 else ['red','green','blue'][rgb.index(max(rgb))]
    for i in range(end,84):
        t=l["video_source_start"]+(i/fps-l["start"])*l["speed"]
        expected='white' if t>=179/60 else 'green' if t>=96/60 else 'blue' if t>=57/60 else 'red'
        assert color(b[i])==color(a[i])==expected,(i,t,color(b[i]),color(a[i]),expected)

@pytest.mark.parametrize("audible",[False,True])
def test_late_long_gop_seek_matches_decoding_from_origin_for_retained_piece(media,signals,alternate,tmp_path,monkeypatch,audible):
    from cutroom import render_inventory
    root,ff,*_=media;name="long-gop-overwrite-"+str(int(audible))+".mp4";path=root/name
    subprocess.run([ff,"-v","error","-n","-f","lavfi","-i","testsrc2=size=160x90:rate=60000/1001:duration=18",
        "-f","lavfi","-i",r"aevalsrc=0.17*sin(2*PI*(330*t+9*t*t)):s=48000:d=18",
        "-threads","2","-c:v","libx264","-g","210","-keyint_min","210","-sc_threshold","0","-bf","3","-pix_fmt","yuv420p","-c:a","aac",str(path)],check=True,timeout=24)
    fps=50;p,_,_=sequence(signals,fps,True);p["assets"][NEW]=dict(alternate);_,_,l=p["manual"]["media_clips"]
    p["assets"][l["asset_id"]].update(path=path.name,duration=18.);l.update(start=.1687,end=2.81,source_start=12.392,video_source_start=13.001,speed=1.125,fade_in=.12,fade_out=.14,audio_enabled=audible)
    p["manual"]["media_clips"]=[l]
    apply_manual_edit(p,{"action":"media_track_overwrite","asset_id":NEW,"track_id":T,"frame":43,"source_start":.38,"source_end":1.099})
    optimized,x=decode(media,native_export(p,media,tmp_path/"seek"))
    monkeypatch.setattr(render_inventory,"_library_seek_start",lambda *args:0.)
    reference,y=decode(media,native_export(p,media,tmp_path/"origin"))
    assert len(optimized)==len(reference)==150
    assert max(sum(abs(i-j) for i,j in zip(a,b))/len(a) for a,b in zip(optimized,reference))<2.5
    if audible:
        a=x[85000:124000];b=y[85000:124000]
        assert sum(i*j for i,j in zip(a,b))/((sum(i*i for i in a)*sum(i*i for i in b))**.5)>.997
