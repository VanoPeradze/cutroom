"""Actual encoded picture/audio proves lifting reveals underlying tracks, without ripple."""
import copy, math, hashlib
import pytest
from cutroom.editing import apply_manual_edit
from test_media_render import media
from test_rolling_edit import T
from test_rolling_edit_render import native_export
from test_slide_edit_render import signals, sequence, decode, hue


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("mode",["cross","split"])
def test_lift_changes_only_target_window_and_keeps_picture_sound_phase(signals,media,tmp_path,fps,mode):
    p,_,_=sequence(signals,fps,True)
    if mode=="split":
        l=p["manual"]["media_clips"][-1];l.update(start=.183276349,end=2.83,source_start=.25,video_source_start=.36,speed=.75,fade_in=.1,fade_out=.15)
        p["manual"]["media_clips"]=[l]
    first,last=round(.73*fps),round(.73*fps)+fps
    a,b=first/fps,last/fps
    saved=copy.deepcopy(p);originals={f:hashlib.sha256(f.read_bytes()).hexdigest() for f in media[0].iterdir() if f.is_file()}
    pre,x=decode(media,native_export(p,media,tmp_path/"before"))
    apply_manual_edit(p,{"action":"media_track_lift","track_id":T,"start_frame":first,"end_frame":last})
    out,y=decode(media,native_export(p,media,tmp_path/"after"))
    background=copy.deepcopy(saved);background["manual"]["media_clips"]=[]
    back,z=decode(media,native_export(background,media,tmp_path/"underneath"))
    assert len(pre)==len(out)==len(back)==3*fps
    outside=[n for n in range(len(out)) if not first<=n<last]
    error=lambda f,g:sum(abs(a-b) for a,b in zip(f,g))/len(f)
    assert max(error(pre[n],out[n]) for n in outside)<4
    assert all(hue(pre[n])==hue(out[n]) for n in outside)
    assert max(error(back[n],out[n]) for n in range(first,last))<4
    assert max(error(pre[n],out[n]) for n in range(first,last))>20
    # The original program source is muted. With the lifted layer absent,
    # the gap is genuinely silent, not just a black/picture-only overlay.
    quiet=y[round((a+.08)*48000):round((b-.08)*48000)]
    assert max(abs(v) for v in quiet)<.006
    for lo,hi in ((.31,a-.055),(b+.065,2.63)):
        u,v=x[round(lo*48000):round(hi*48000)],y[round(lo*48000):round(hi*48000)]
        xx,yy=sum(i*i for i in u),sum(i*i for i in v)
        assert min(xx,yy)>8
        assert sum(i*j for i,j in zip(u,v))/math.sqrt(xx*yy)>.985
        assert .97<math.sqrt(yy/xx)<1.03
    assert {f:hashlib.sha256(f.read_bytes()).hexdigest() for f in originals}==originals


@pytest.mark.parametrize("normalize",[False,True])
def test_marked_export_keeps_lifted_gap_and_all_remaining_audio(signals,media,tmp_path,normalize):
    fps=25;p,_,_=sequence(signals,fps,True)
    apply_manual_edit(p,{"action":"media_track_lift","track_id":T,"start_frame":18,"end_frame":43})
    full,x=decode(media,native_export(p,media,tmp_path/"full",normalize=normalize))
    part,y=decode(media,native_export(p,media,tmp_path/"marked",(8,65),normalize))
    assert len(full)==75 and len(part)==57
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(part,full[8:65]))<4
    lo,hi=2600,57*1920-2600;u,v=x[8*1920+lo:8*1920+hi],y[lo:hi]
    assert len(u)==len(v) and sum(a*b for a,b in zip(u,v))/math.sqrt(sum(a*a for a in u)*sum(a*a for a in v))>.985
