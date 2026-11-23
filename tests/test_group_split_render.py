"""Encode before and after a mixed split: no invisible seam or sound restart."""
import copy,math
import pytest
from cutroom.editing import apply_manual_edit
from test_media_render import media,project
from test_slide_edit_render import signals,decode
from test_rolling_edit_render import native_export
from test_clip_opacity_render import plates,rgba_asset
from test_mixed_media_insert import media_row,text_row
from test_group_split import V,A,I,X
from test_rolling_edit import T,U


def split_scene(signals,plates,fps,tracked):
    p=project();p["settings"]["fps"]=fps;p["draft"]["output_duration"]=3.
    v=copy.deepcopy(signals[0][signals[1][2]]);a={**copy.deepcopy(signals[0][signals[1][0]]),"kind":"audio"}
    image=rgba_asset(plates[3]);p["assets"]={v["id"]:v,a["id"]:a,image["id"]:image}
    p["manual"].update(media_clips=[
        media_row("1",v["id"],.123456789,2.78,source_start=.1,video_source_start=.2,speed=.75,fade_in=.15,fade_out=.25,x=0.,y=0.,w=.8,h=.8,opacity_percent=57,track_id=T),
        media_row("2",a["id"],.2,2.7,source_start=.2,fade_in=.1,fade_out=.25,track_id=U),
        media_row("3",image["id"],.17,2.85,source_start=0.,audio_enabled=False,fade_in=0.,fade_out=0.,x=.7,y=.7,w=.3,h=.3,opacity_percent=43,track_id="track_"+"c"*32)],
        text_clips=[text_row("1",.19,2.8,text="SOURCE",subtext="Same title",track_id="track_"+"d"*32),text_row("2",.3,2.6,text="Unselected",subtext="",template="plain",position="top",style="clean",track_id="track_"+"e"*32)],
        audio_mixer={"source_muted":True},
        layer_tracks={"version":1,"tracks":[{"id":T,"kind":"visual","name":"Video"},{"id":U,"kind":"audio","name":"Sound"},{"id":"track_"+"c"*32,"kind":"visual","name":"Image"},{"id":"track_"+"d"*32,"kind":"text","name":"Selected text"},{"id":"track_"+"e"*32,"kind":"text","name":"Untouched"}]})
    if not tracked:
        p["manual"].pop("layer_tracks")
        for row in p["manual"]["media_clips"]+p["manual"]["text_clips"]:row.pop("track_id")
    return p


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("tracked",[False,True])
def test_every_encoded_frame_and_sound_sample_survives_mixed_frame_split(signals,plates,media,tmp_path,fps,tracked):
    p=split_scene(signals,plates,fps,tracked);frame=fps+2
    before,x=decode(media,native_export(p,media,tmp_path/"before"))
    apply_manual_edit(p,{"action":"layers_split","clip_ids":[X,I,A,V],"frame":frame})
    after,y=decode(media,native_export(p,media,tmp_path/"after"))
    assert len(before)==len(after)==3*fps
    errors=[sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(before,after)]
    assert max(errors)<4,errors
    assert len(x)==len(y)
    lo,hi=2400,len(x)-2400;a,b=x[lo:hi],y[lo:hi]
    xx,yy=sum(z*z for z in a),sum(z*z for z in b)
    assert xx>8 and yy>8 and sum(i*j for i,j in zip(a,b))/math.sqrt(xx*yy)>.99
    assert .99<math.sqrt(yy/xx)<1.01
    # The seam itself cannot restart or mute sound despite different picture speed.
    lo,hi=round((frame/fps-.08)*48000),round((frame/fps+.08)*48000);a,b=x[lo:hi],y[lo:hi]
    assert sum(i*j for i,j in zip(a,b))/math.sqrt(sum(i*i for i in a)*sum(j*j for j in b))>.99


@pytest.mark.parametrize("normalized",[False,True])
def test_marked_export_matches_full_after_group_split(signals,plates,media,tmp_path,normalized):
    fps=30;p=split_scene(signals,plates,fps,True)
    apply_manual_edit(p,{"action":"layers_split","clip_ids":[X,I,A,V],"frame":32})
    full,x=decode(media,native_export(p,media,tmp_path/"full",normalize=normalized))
    crop,y=decode(media,native_export(p,media,tmp_path/"marked",(13,73),normalized))
    assert len(full)==90 and len(crop)==60
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(crop,full[13:73]))<4
    lo,hi=2400,60*1600-2400;a,b=x[13*1600+lo:13*1600+hi],y[lo:hi]
    assert len(a)==len(b)
    assert sum(i*j for i,j in zip(a,b))/math.sqrt(sum(i*i for i in a)*sum(j*j for j in b))>.985
