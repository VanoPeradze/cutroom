"""Real FFmpeg compositing and audio, not merely filter-string inspection."""
import copy, math, struct, subprocess, zlib
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.media_render import append_media_graph
from test_media_render import media, project
from test_rolling_edit import L,T
from test_rolling_edit_render import native_export
from test_slide_edit_render import signals, decode
from test_mixed_media_insert import media_row

PNG="asset_"+"e"*32


def png(path,w,h,alpha):
    def chunk(k,b):return struct.pack(">I",len(b))+k+b+struct.pack(">I",zlib.crc32(k+b)&0xffffffff)
    # Blue source with native alpha, including exact transparent and opaque bands.
    pixels=b"".join(b"\0"+b"".join(bytes((0,0,255,alpha(x,y))) for x in range(w)) for y in range(h))
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",w,h,8,6,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b""))


@pytest.fixture(scope="module")
def plates(media):
    root=media[0]
    p=root/"opacity-alpha.png";png(p,160,90,lambda x,y:128)
    q=root/"opacity-wide.png";png(q,160,44,lambda x,y:128)
    r=root/"opacity-blue.png";png(r,160,90,lambda x,y:255)
    s=root/"opacity-bands.png";png(s,160,90,lambda x,y:0 if x<50 else 128 if x<110 else 255)
    return [p.name,q.name,r.name,s.name]


def visual_project(asset,opacity=100,**extra):
    p=project();p["settings"]["fps"]=30;p["draft"]["output_duration"]=3.
    p["assets"]={asset["id"]:copy.deepcopy(asset)}
    row=media_row("1",asset["id"],0.,3.,track_id=T,source_start=0.,speed=1.,audio_enabled=asset["kind"]=="video",
        fade_in=0.,fade_out=0.,x=0.,y=0.,w=1.,h=1.,fit="cover",motion="none",volume_db=0.,**extra)
    if opacity!=100:row["opacity_percent"]=opacity
    p["manual"].update(media_clips=[row],audio_mixer={"source_muted":True},layer_tracks={"version":1,"tracks":[{"id":T,"name":"Opacity","kind":"visual"}]})
    return p


def rgba_asset(name,width=160,height=90):
    return {"id":PNG,"name":"Synthetic native alpha","path":name,"kind":"image","status":"ready","width":width,"height":height,"duration":0.,"has_audio":False}


def px(frame,x=12,y=7):
    i=(y*24+x)*3
    return tuple(frame[i:i+3])


@pytest.mark.parametrize("value",[0,25,50,100])
def test_opaque_video_blends_one_occurrence_without_changing_another_or_audio(signals,media,tmp_path,value):
    asset=signals[0][signals[1][2]];p=visual_project(asset)
    first=p["manual"]["media_clips"][0];first.update(end=1.4)
    p["manual"]["media_clips"].append({**first,"id":"media_"+"2"*32,"start":1.5,"end":2.9,"source_start":.2})
    base,x=decode(media,native_export(p,media,tmp_path/"before"))
    if value!=100:apply_manual_edit(p,{"action":"media_set_opacity","clip_id":L,"opacity_percent":value})
    aft,y=decode(media,native_export(p,media,tmp_path/"after"));assert len(base)==len(aft)==90
    underneath=copy.deepcopy(p);underneath["manual"]["media_clips"]=[]
    background,_=decode(media,native_export(underneath,media,tmp_path/"base"))
    r,g,b=px(aft[15]);expected=tuple(a*(1-value/100)+b*value/100 for a,b in zip(px(background[15]),px(base[15])))
    assert max(abs(a-b) for a,b in zip((r,g,b),expected))<9,((r,g,b),expected)
    assert max(sum(abs(a-b) for a,b in zip(base[i],aft[i]))/len(base[i]) for i in range(45,90))<4
    assert len(x)==len(y)
    assert sum(a*b for a,b in zip(x,y))/math.sqrt(sum(a*a for a in x)*sum(a*a for a in y))>.999
    assert .999<math.sqrt(sum(a*a for a in y)/sum(a*a for a in x))<1.001
    if value==0:assert max(abs(v) for v in y[12000:48000])>.1


@pytest.mark.parametrize("value",[0,25,50,100])
def test_png_existing_half_alpha_is_multiplied_not_replaced(plates,media,tmp_path,value):
    p=visual_project(rgba_asset(plates[0]),value)
    images,_=decode(media,native_export(p,media,tmp_path/"alpha"))
    actual=px(images[15]);a=128/255*value/100;expected=(255*(1-a),0,255*a)
    assert max(abs(x-y) for x,y in zip(actual,expected))<8,(actual,expected)


@pytest.mark.parametrize("motion",["none","pan","zoom_in"])
def test_alpha_png_bands_under_partial_opacity_keep_transparent_pixels(plates,media,tmp_path,motion):
    p=visual_project(rgba_asset(plates[3]),50);p["manual"]["media_clips"][0]["motion"]=motion
    images,_=decode(media,native_export(p,media,tmp_path/"bands"))
    frame=images[12];actual=[px(frame,x,7) for x in [2,12,21]]
    expected=[(255,0,0),(191,0,64),(128,0,128)]
    assert all(max(abs(a-b) for a,b in zip(x,y))<10 for x,y in zip(actual,expected)),(motion,actual)


def test_contain_matte_multiplies_the_whole_existing_visual_box(plates,media,tmp_path):
    p=visual_project(rgba_asset(plates[1],160,44),50);p["manual"]["media_clips"][0]["fit"]="contain"
    images,_=decode(media,native_export(p,media,tmp_path/"contain"))
    # Existing contain means a black matte, not transparent padding; the matte
    # and the already translucent image are both attenuated by occurrence opacity.
    assert max(abs(a-b) for a,b in zip(px(images[15],12,1),(128,0,0)))<9
    assert max(abs(a-b) for a,b in zip(px(images[15],12,7),(191,0,64)))<9


def test_default_graph_is_identical_and_zero_keeps_audio_input(signals):
    p=visual_project(signals[0][signals[1][2]])
    before=append_media_graph(p,160,90,3.,"[base]","[sound]")
    p["manual"]["media_clips"][0]["opacity_percent"]=100
    assert append_media_graph(p,160,90,3.,"[base]","[sound]")==before
    p["manual"]["media_clips"][0]["opacity_percent"]=0
    filters,_,sound=append_media_graph(p,160,90,3.,"[base]","[sound]")
    assert "colorchannelmixer=aa=0.00" in ";".join(filters) and sound
    assert any("atrim" in f and "[1:a]" in f for f in filters)


@pytest.fixture(scope="module")
def keyed(media):
    path=media[0]/"opacity-key.mp4"
    subprocess.run([media[1],"-v","error","-n","-f","lavfi","-i","color=lime:s=160x90:r=30:d=3,drawbox=x=50:y=25:w=60:h=40:color=blue:t=fill","-threads","2","-c:v","libx264","-pix_fmt","yuv420p","-preset","veryfast",str(path)],check=True,timeout=20)
    return {"id":"asset_"+"f"*32,"name":"Synthetic green and blue","path":path.name,"kind":"video","status":"ready","width":160,"height":90,"duration":3.,"has_audio":False}


@pytest.mark.parametrize("motion",["none","pan","zoom_in"])
@pytest.mark.parametrize("fit",["cover","contain"])
def test_opacity_multiplies_chroma_alpha_after_key_fit_and_motion(keyed,media,tmp_path,motion,fit):
    from cutroom.composition import CHROMA_KEY_DEFAULTS
    p=visual_project(keyed,50);p["manual"]["media_clips"][0].update(motion=motion,fit=fit)
    p["manual"]["chroma_key"]={keyed["id"]:{**CHROMA_KEY_DEFAULTS,"enabled":True,"background_mode":"transparent"}}
    frames,_=decode(media,native_export(p,media,tmp_path/"keyed"))
    corner,center=px(frames[15],2,2),px(frames[15],12,7)
    assert corner[0]>235 and max(corner[1:])<12,corner
    assert max(abs(a-b) for a,b in zip(center,(128,0,128)))<10,center


@pytest.mark.parametrize("fps",[25,50])
@pytest.mark.parametrize("normalize",[False,True])
def test_marked_export_has_same_partial_alpha_and_same_sound(plates,media,tmp_path,fps,normalize):
    p=visual_project(rgba_asset(plates[3]),37);p["settings"]["fps"]=fps;p["manual"]["audio_mixer"]={"source_muted":False}
    whole,x=decode(media,native_export(p,media,tmp_path/"full",normalize=normalize))
    start,end=round(.4*fps),round(2.6*fps)
    part,y=decode(media,native_export(p,media,tmp_path/"marked",(start,end),normalize))
    assert len(whole)==3*fps and len(part)==end-start
    assert max(sum(abs(a-b) for a,b in zip(f,g))/len(f) for f,g in zip(part,whole[start:end]))<4
    samples=48000//fps;lo,hi=2600,(end-start)*samples-2600
    a,b=x[start*samples+lo:start*samples+hi],y[lo:hi]
    assert len(a)==len(b)
    assert sum(j*k for j,k in zip(a,b))/math.sqrt(sum(j*j for j in a)*sum(j*j for j in b))>.985
