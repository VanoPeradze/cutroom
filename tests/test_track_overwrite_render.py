"""Encoded A/V phase of retained material and the overwrite, not just API geometry."""
import copy,math,subprocess
import pytest
from cutroom.editing import apply_manual_edit
from test_media_render import media
from test_rolling_edit import L,T
from test_rolling_edit_render import native_export
from test_slide_edit_render import signals,sequence,decode,hue
from test_replace_take_render import alternate,magenta,tone
from test_replace_take import NEW


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("mode",["cross","split"])
def test_actual_encoded_overwrite_changes_only_target_window_and_keeps_source_phase(signals,alternate,media,tmp_path,fps,mode):
    p,_,_=sequence(signals,fps,True);p["assets"][NEW]=copy.deepcopy(alternate)
    r,m,l=p["manual"]["media_clips"]
    if mode=="split":
        l.update(start=.183276349,end=2.83,source_start=.25,video_source_start=.36,speed=.75,fade_in=.1,fade_out=.15)
        p["manual"]["media_clips"]=[l]
    first=round(.73*fps);frames=fps;start=first/fps;end=(first+frames)/fps
    pre,x=decode(media,native_export(p,media,tmp_path/"a"))
    apply_manual_edit(p,{"action":"media_track_overwrite","asset_id":NEW,"track_id":T,"frame":first,"source_start":.63,"source_end":1.63})
    out,y=decode(media,native_export(p,media,tmp_path/"b"));assert len(pre)==len(out)==3*fps
    assert [j for j,f in enumerate(out) if magenta(f)]==list(range(first,first+frames))
    outside=[n for n in range(len(out)) if not first<=n<first+frames]
    assert all(hue(pre[n])==hue(out[n]) for n in outside)
    assert max(sum(abs(a-b) for a,b in zip(pre[n],out[n]))/len(pre[n]) for n in outside)<4
    windows=0
    for n in range(first+2,first+frames-2):
        src=.63+n/fps-start
        if min(src%.5,.5-src%.5)<.07:continue
        g=sum(out[n][24*3+1:2*24*3:3])/24
        assert (g>160)==(src%1<.5) and tone(y,round(n/fps*48000))==(730 if src%1<.5 else 1460);windows+=1
    assert windows>fps*.39
    for a,b in ((.30,start-.05),(end+.06,2.64)):
        lo,hi=round(a*48000),round(b*48000);v,w=x[lo:hi],y[lo:hi]
        xx=sum(a*a for a in v);yy=sum(a*a for a in w);xy=sum(a*b for a,b in zip(v,w))
        assert min(xx,yy)>8 and xy/math.sqrt(xx*yy)>.985 and .97<math.sqrt(yy/xx)<1.03


@pytest.mark.parametrize("normalized",[False,True])
def test_full_and_marked_edited_timeline_export_choose_same_shot_and_retained_tail(signals,alternate,media,tmp_path,normalized):
    fps=25;p,_,_=sequence(signals,fps,True);p["assets"][NEW]=copy.deepcopy(alternate);first=18
    apply_manual_edit(p,{"action":"media_track_overwrite","asset_id":NEW,"track_id":T,"frame":first,"source_start":.63,"source_end":1.65})
    full,x=decode(media,native_export(p,media,tmp_path/"full",normalize=normalized))
    crop,y=decode(media,native_export(p,media,tmp_path/"crop",(11,59),normalized));assert len(crop)==48
    assert [magenta(z) for z in crop]==[magenta(z) for z in full[11:59]]
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(crop,full[11:59]))<4
    lo,hi=2600,len(crop)*1920-2600;a,b=x[11*1920+lo:11*1920+hi],y[lo:hi];assert len(a)==len(b)
    assert sum(j*k for j,k in zip(a,b))/math.sqrt(sum(j*j for j in a)*sum(j*j for j in b))>.985
