"""Explicit creator layout controls, independent of story/face inference."""
import math

FIELDS={"screen_fit","pip_scale","pip_x","pip_y"}

def controls(raw,strict=False):
    result={}
    for key in FIELDS:
        if key not in raw:continue
        value=raw[key]
        if key=="screen_fit": valid=value in {"auto","cover","contain"} if isinstance(value,str) else False
        else:
            low,high=(.15,.55) if key=="pip_scale" else (0.,1.)
            valid=not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high
        if not valid:
            if strict:raise ValueError("Choose screen fit auto/cover/contain, inset width15–55%, and positions0–100%.")
            continue
        result[key]=value
    return result

def pip_geometry(project,width,height,mixer):
    raw=controls(mixer)
    if not any(key in raw for key in ("pip_scale","pip_x","pip_y")):
        w=max(160,int(width*.34)//2*2);h=max(90,int(height*.28)//2*2)
        return w,h,width-w-32,height-h-32
    inset=mixer["camera_slot"] if mixer["primary_role"]=="screen" else mixer["screen_slot"]
    source=project["sources"][inset]
    sw,sh=float(source.get("width") or 0),float(source.get("height") or 0)
    if int(source.get("rotation") or 0)%180:sw,sh=sh,sw
    if not sw>0 or not sh>0:raise ValueError("Read the inset source dimensions before configuring picture in picture.")
    ratio=sw/sh;w=max(2,int(width*raw.get("pip_scale",.34))//2*2);h=max(2,int(w/ratio)//2*2)
    if h>height:h=height//2*2;w=max(2,int(h*ratio)//2*2)
    x=math.floor((width-w)*raw.get("pip_x",1)+.5);y=math.floor((height-h)*raw.get("pip_y",1)+.5)
    return w,h,x,y
