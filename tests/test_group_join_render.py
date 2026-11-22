"""Through-edit joining has no encoded A/V seam and preserves other later work."""
import copy,math
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.group_split import group_split_receipt
from test_media_render import media
from test_slide_edit_render import signals,decode
from test_clip_opacity_render import plates
from test_group_split_render import split_scene
from test_group_split import V,A,I,X
from test_rolling_edit_render import native_export


def split(p,frame):
    before=copy.deepcopy(p);payload={"action":"layers_split","clip_ids":[V,A,I,X],"frame":frame}
    apply_manual_edit(p,payload)
    return {r["source_id"]:r["clip_id"] for r in group_split_receipt(before,p,payload)}


@pytest.mark.parametrize("fps",[24,25,30,50,60])
@pytest.mark.parametrize("tracked",[False,True])
@pytest.mark.parametrize("target",[V,A,I,X])
def test_joined_occurrence_keeps_every_frame_and_sound_phase(signals,plates,media,tmp_path,fps,tracked,target):
    p=split_scene(signals,plates,fps,tracked);mapping=split(p,fps+2)
    # Join is not Undo: an independent later authored change must remain visible.
    p["manual"]["text_clips"][-1]["text"]="LATER WORK"
    pre,x=decode(media,native_export(p,media,tmp_path/"split"))
    apply_manual_edit(p,{"action":"layers_join","clip_ids":[mapping[target],target]})
    aft,y=decode(media,native_export(p,media,tmp_path/"joined"))
    assert p["manual"]["text_clips"][-1]["text"]=="LATER WORK"
    assert len(pre)==len(aft)==3*fps
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(pre,aft))<4
    assert len(x)==len(y)
    for lo,hi in [(2400,len(x)-2400),(round(((fps+2)/fps-.08)*48000),round(((fps+2)/fps+.08)*48000))]:
        a,b=x[lo:hi],y[lo:hi];xx,yy=sum(i*i for i in a),sum(i*i for i in b)
        assert sum(i*j for i,j in zip(a,b))/math.sqrt(xx*yy)>.99 and .99<math.sqrt(yy/xx)<1.01


@pytest.mark.parametrize("normalize",[False,True])
def test_full_and_marked_export_match_after_join(signals,plates,media,tmp_path,normalize):
    p=split_scene(signals,plates,30,True);mapping=split(p,32)
    apply_manual_edit(p,{"action":"layers_join","clip_ids":[V,mapping[V]]})
    full,x=decode(media,native_export(p,media,tmp_path/"full",normalize=normalize))
    part,y=decode(media,native_export(p,media,tmp_path/"marked",(13,73),normalize))
    assert len(full)==90 and len(part)==60
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(part,full[13:73]))<4
    a,b=x[13*1600+2400:73*1600-2400],y[2400:60*1600-2400]
    assert len(a)==len(b) and sum(i*j for i,j in zip(a,b))/math.sqrt(sum(i*i for i in a)*sum(j*j for j in b))>.985


@pytest.mark.parametrize("fps",[25,30])
def test_fast_picture_held_last_frame_is_still_a_continuous_join(signals,plates,media,tmp_path,fps):
    p=split_scene(signals,plates,fps,True);p["manual"]["media_clips"][0]["speed"]=4.
    mapping=split(p,fps+2)
    pre,x=decode(media,native_export(p,media,tmp_path/"split-hold"))
    apply_manual_edit(p,{"action":"layers_join","clip_ids":[V,mapping[V]]})
    aft,y=decode(media,native_export(p,media,tmp_path/"joined-hold"))
    assert len(pre)==len(aft)==3*fps
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(pre,aft))<4
    assert len(x)==len(y) and sum(a*b for a,b in zip(x,y))/math.sqrt(sum(a*a for a in x)*sum(a*a for a in y))>.99
