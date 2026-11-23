"""Versioned user-owned lanes for imported media and custom text only."""
from __future__ import annotations
import copy
import hashlib
import math
import re

TRACK_RE = re.compile(r"track_[0-9a-f]{32}\Z")
CLIP_RE = re.compile(r"(?:media|text)_[0-9a-f]{32}\Z")
KINDS = {"visual", "audio", "text"}
MAX_TRACKS = 4096
TRACK_ACTION_FIELDS = {
    "layer_tracks_enable": set(),
    "layer_track_lock": {"track_id", "locked"},
    "layer_track_audio": {"track_id", "gain_db", "muted"},
    "layer_track_add": {"kind", "name"},
    "layer_track_rename": {"track_id", "name"},
    "layer_track_reorder": {"track_id", "position"},
    "layer_track_remove": {"track_id"},
    "layer_move": {"clip_id", "track_id", "start"},
}

class LayerTrackError(ValueError):
    pass

def _validate_audio(audio):
    if not isinstance(audio,dict) or set(audio)!={"gain_db","muted"} or type(audio["muted"]) is not bool:
        raise LayerTrackError("Invalid track audio settings")
    gain=audio["gain_db"]
    if isinstance(gain,bool) or not isinstance(gain,(int,float)) or not math.isfinite(gain) or not -60<=gain<=12:
        raise LayerTrackError("Track gain must be finite between -60 and 12 dB")
    return audio

def track_audio_settings(project,track_id):
    model=(project.get("manual") or {}).get("layer_tracks")
    if isinstance(model,dict) and model.get("version")==3:
        track=next((t for t in model["tracks"] if t["id"]==track_id),None)
        if track is not None and track["kind"] in {"visual","audio"}:return dict(_validate_audio(track["audio"]))
    return {"gain_db":0,"muted":False}

def layer_audio_gain(project,clip):
    audio=track_audio_settings(project,clip.get("track_id"))
    return 0.0 if audio["muted"] else 10**(audio["gain_db"]/20)

def _name(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 80:
        raise LayerTrackError("Track names must contain 1 to 80 characters")
    return value.strip()

def _rows(project):
    manual = project.get("manual") or {}
    rows = []
    seen = set()
    for key, prefix, limit in (("media_clips", "media_", 200), ("text_clips", "text_", 2000)):
        values = manual.get(key, [])
        if not isinstance(values, list) or len(values) > limit:
            raise LayerTrackError("Invalid saved layer array")
        for row in values:
            if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not CLIP_RE.fullmatch(row["id"]) or not row["id"].startswith(prefix) or row["id"] in seen:
                raise LayerTrackError("Invalid or ambiguous layer identity")
            seen.add(row["id"])
            start, end = row.get("start"), row.get("end")
            if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in (start,end)) or start < 0 or end <= start:
                raise LayerTrackError("Layer track timing must be finite and positive")
            kind = "text"
            if key == "media_clips":
                asset = (project.get("assets") or {}).get(row.get("asset_id"))
                asset_kind = asset.get("kind") if isinstance(asset,dict) else None
                if asset_kind not in {"video","image","audio"}:
                    raise LayerTrackError("A layer has no known imported asset kind; restore its asset before using tracks")
                kind = "audio" if asset_kind == "audio" else "visual"
            rows.append((row,kind))
    return rows

def _overlap(a,b):
    return min(a["end"],b["end"]) - max(a["start"],b["start"]) > 1e-8

def validate_layer_tracks(project):
    manual = project.get("manual") or {}
    if "layer_tracks" not in manual:
        if any(isinstance(row,dict) and "track_id" in row for key in ('media_clips','text_clips') for row in (manual.get(key) or []) if isinstance(manual.get(key) or [],list)):
            raise LayerTrackError("Layer track membership has no model; restore the compatible project")
        return None
    model = manual["layer_tracks"]
    if not isinstance(model,dict) or set(model)!=({"version","tracks","protection_version"} if model.get("version")==3 else {"version","tracks"}) or type(model.get("version")) is not int or model["version"] not in (1,2,3):
        raise LayerTrackError("Unsupported or malformed layer track version; this edit requires a compatible CUTROOM version")
    if model["version"]==3 and (type(model.get("protection_version")) is not int or model["protection_version"] not in (1,2)):
        raise LayerTrackError("Invalid protection version")
    tracks = model["tracks"]
    if not isinstance(tracks,list) or len(tracks)>MAX_TRACKS:
        raise LayerTrackError("Invalid layer track list")
    lookup = {}
    for track in tracks:
        if not isinstance(track,dict) or set(track)!=({"id","kind","name","locked"}|({"audio"} if track.get("kind") in {"visual","audio"} else set()) if model["version"]==3 else {"id","kind","name","locked"} if model["version"]==2 else {"id","kind","name"}) or not isinstance(track.get("id"),str) or not TRACK_RE.fullmatch(track["id"]) or track["id"] in lookup or not isinstance(track.get("kind"),str) or track["kind"] not in KINDS:
            raise LayerTrackError("Invalid or duplicate layer track")
        if model["version"]>=2 and type(track.get("locked")) is not bool:
            raise LayerTrackError("Saved track locks must be booleans")
        if model["version"]==3 and model["protection_version"]==1 and track["locked"]:raise LayerTrackError("Version 1 protection cannot contain locks")
        if model["version"]==3 and track["kind"] in {"visual","audio"}:_validate_audio(track.get("audio"))
        if _name(track.get("name")) != track["name"]:
            raise LayerTrackError("Saved track names must be trimmed")
        lookup[track["id"]] = track
    from .sequence import editor_sequence_snapshot
    # Source B changes invalidate the draft but deliberately retain the explicit
    # edit clock and independent layers. Validate that stored sequence without
    # synthesizing or saving a new draft, or enabling editing/export readiness.
    validation_project = project
    if not isinstance(project.get("draft"), dict) and "sequence" in manual:
        from .source_tracks import validate_sequence_version, has_sequence
        validate_sequence_version(project)
        if has_sequence(project):
            validation_project = {**project, "draft": {}}
    snapshot = editor_sequence_snapshot(validation_project)
    if not snapshot:raise LayerTrackError("Open a valid edit before using layer tracks")
    duration = snapshot['duration']
    from .text_clips import _validate_overlaps
    _validate_overlaps((project.get('manual') or {}).get('text_clips', []))
    occupied = {}
    for row,kind in _rows(project):
        if row["end"] > duration + 1e-8:raise LayerTrackError("A layer extends beyond the edit duration")
        identity = row.get("track_id")
        if not isinstance(identity,str) or not TRACK_RE.fullmatch(identity):raise LayerTrackError("Invalid clip track identity")
        track = lookup.get(identity)
        if not track or track["kind"] != kind:
            raise LayerTrackError("A clip must belong to an existing compatible layer track")
        lane = occupied.setdefault(track["id"],[])
        if any(_overlap(row,other) for other in lane):
            raise LayerTrackError("Clips on the same track cannot overlap. Choose an empty destination or another track")
        lane.append(row)
    return model

def _new_track(project, model, kind, name=None, audio=None):
    if not isinstance(kind,str) or kind not in KINDS:
        raise LayerTrackError("Choose a visual, audio or text track")
    if len(model["tracks"]) >= MAX_TRACKS:
        raise LayerTrackError("The project already has the maximum number of tracks")
    used = {t["id"] for t in model["tracks"]}
    index = 0
    while True:
        identity = "track_" + hashlib.sha256(f"{project.get('id','')}:{kind}:{index}".encode()).hexdigest()[:32]
        if identity not in used:break
        index += 1
    track = {"id":identity,"kind":kind,"name":_name(name) if name is not None else f"{'Video' if kind=='visual' else kind.title()} {index+1}"}
    if model["version"]>=2:track["locked"]=False
    if model["version"]==3 and kind in {"visual","audio"}:track["audio"]=dict(audio or {"gain_db":0,"muted":False})
    model["tracks"].append(track)
    return track

def _assign(project, row, kind, prior, model, audio=None):
    audio=audio or {"gain_db":0,"muted":False}
    lanes = [t for t in model["tracks"] if t["kind"]==kind]
    rank = {t["id"]:i for i,t in enumerate(lanes)}
    # Every preceding overlapping visual/text occurrence remains below this one.
    floor = max((rank[p["track_id"]]+1 for p,k in prior if k==kind and _overlap(p,row)),default=0) if kind!="audio" else 0
    for index,track in enumerate(lanes):
        if not track.get("locked",False) and (kind=="text" or track_audio_settings(project,track["id"])==audio) and index>=floor and not any(p.get("track_id")==track["id"] and _overlap(p,row) for p,k in prior):
            row["track_id"]=track["id"];return
    row["track_id"]=_new_track(project,model,kind,audio=audio)["id"]

def projected_layer_tracks(project):
    """Detached deterministic migration; reads never write or normalize content."""
    validate_layer_tracks(project)
    result=copy.deepcopy(project)
    if "layer_tracks" in (result.get("manual") or {}):return result
    model={"version":1,"tracks":[]};result.setdefault("manual",{})["layer_tracks"]=model
    prior=[]
    for row,kind in _rows(result):
        _assign(result,row,kind,prior,model);prior.append((row,kind))
    validate_layer_tracks(result)
    return result

def assign_new_layer_tracks(before, after, action="", *, pinned_ids=frozenset(), source_track_ids=None):
    """Assign only genuinely new IDs; existing membership is never repaired."""
    if action in {"layers_duplicate", "layers_split", "media_track_overwrite", "media_track_lift"}:
        validate_layer_tracks(after)  # The planner pinned every created piece; never choose another lane.
        return
    model=(after.get("manual") or {}).get("layer_tracks")
    if model is None:return
    old_ids={row["id"] for row,kind in _rows(before)}
    rows=_rows(after)
    existing=[(row,kind) for row,kind in rows if row["id"] in old_ids]
    for row,kind in rows:
        if row["id"] in old_ids:continue
        if row["id"] in pinned_ids:
            existing.append((row,kind))
            continue  # Explicit destinations are validated, never auto-reallocated.
        # A split's inherited lane is valid when free. A duplicate must instead
        # obey its appended painter priority; no existing clip is relocated.
        predecessors=[(p,k) for p,k in rows[:next(i for i,(p,k) in enumerate(rows) if p is row)] if p["id"] in old_ids or "track_id" in p]
        lane=row.get("track_id")
        is_free=lane and not next((t.get("locked",False) for t in model["tracks"] if t["id"]==lane),False) and not any(p.get("track_id")==lane and _overlap(p,row) for p,k in existing)
        if not is_free or action in {"media_duplicate","text_duplicate","layers_duplicate"}:
            audio=track_audio_settings(before,(source_track_ids or {}).get(row["id"],lane)) if action in {"media_duplicate","text_duplicate","layers_duplicate"} else None
            _assign(after,row,kind,predecessors+[(p,k) for p,k in existing if p not in [v for v,_ in predecessors]],model,audio=audio)
        existing.append((row,kind))
    validate_layer_tracks(after)

def ordered_layer_clips(project, kind, clips=None):
    model=validate_layer_tracks(project)
    if clips is None:
        clips=[row for row,k in _rows(project) if k==kind]
    if model is None or kind=="audio":return list(clips)
    rank={t["id"]:i for i,t in enumerate(model["tracks"]) if t["kind"]==kind}
    return sorted(clips,key=lambda row:rank[row["track_id"]])

def layer_tracks_render_identity(project):
    model=validate_layer_tracks(project)
    if model is None:return None
    # Only compositing order changes output; names and empty lanes do not.
    result={"version":1,"visual":[r["id"] for r in ordered_layer_clips(project,"visual")],
            "text":[r["id"] for r in ordered_layer_clips(project,"text")]}
    from .render_inventory import audible
    levels=[]
    for row in (project.get("manual") or {}).get("media_clips",[]):
        asset=(project.get("assets") or {}).get(row.get("asset_id"),{})
        if not audible(row,asset):continue
        audio=track_audio_settings(project,row.get("track_id"))
        if audio!={"gain_db":0,"muted":False}:levels.append({"clip_id":row["id"],**audio})
    if levels:result["audio_levels"]=levels
    return result


def prepare_layer_track_edit(project,payload):
    action=payload.get("action")
    if action not in TRACK_ACTION_FIELDS or set(payload)-{"action","expected_revision",*TRACK_ACTION_FIELDS[action]}:
        raise LayerTrackError("Unknown layer track edit or field")
    if not isinstance(project.get("draft"),dict):raise LayerTrackError("Open an edit before using layer tracks")
    model=validate_layer_tracks(project)
    if action=="layer_tracks_enable":
        if model is not None:return None
        staged=projected_layer_tracks(project)
        return {key:staged['manual'][key] for key in ("layer_tracks","media_clips","text_clips") if key in staged['manual']}
    if model is None:raise LayerTrackError("Enable persistent layer tracks before editing them")
    staged=copy.deepcopy(project);manual=staged['manual'];model=manual['layer_tracks'];tracks=model['tracks']
    if action=="layer_track_add":_new_track(staged,model,payload.get('kind'),_name(payload.get('name')))
    else:
        identity=payload.get('track_id')
        track=next((t for t in tracks if t['id']==identity),None)
        if track is None:raise LayerTrackError("Choose an existing layer track")
        if action=="layer_track_audio":
            if track["kind"]=="text":raise LayerTrackError("Text tracks have no audio")
            if not ({"gain_db","muted"}&set(payload)):raise LayerTrackError("Change gain or mute")
            audio=_validate_audio({**track_audio_settings(staged,identity),**{key:payload[key] for key in ("gain_db","muted") if key in payload}})
            if track_audio_settings(staged,identity)==audio:return None
            if model["version"]<3:
                model["protection_version"]=model["version"];model["version"]=3
                for item in tracks:
                    item.setdefault("locked",False)
                    if item["kind"]!="text":item["audio"]={"gain_db":0,"muted":False}
            track["audio"]=dict(audio)
        elif action=="layer_track_rename":track['name']=_name(payload.get('name'))
        elif action=="layer_track_remove":
            if any(r.get('track_id')==identity for r,k in _rows(staged)):raise LayerTrackError("Only empty tracks can be removed; move or remove their clips first")
            tracks.remove(track)
        elif action=="layer_track_reorder":
            position=payload.get('position');same=[i for i,t in enumerate(tracks) if t['kind']==track['kind']];old=same.index(tracks.index(track))
            if position not in {'backward','forward','back','front'}:raise LayerTrackError("Choose a valid track order")
            dest={'back':0,'front':len(same)-1,'backward':max(0,old-1),'forward':min(len(same)-1,old+1)}[position]
            values=[tracks[i] for i in same];values.insert(dest,values.pop(old))
            for i,value in zip(same,values):tracks[i]=value
        elif action=="layer_move":
            row=next((r for r,k in _rows(staged) if r['id']==payload.get('clip_id')),None)
            if row is None:raise LayerTrackError("Choose an existing imported media or custom text clip")
            start=payload.get('start')
            if isinstance(start,bool) or not isinstance(start,(int,float)) or not math.isfinite(start) or start<0:raise LayerTrackError("Choose a finite nonnegative start")
            from .sequence import editor_sequence_snapshot
            duration=editor_sequence_snapshot(staged)['duration'];precision=6 if row['id'].startswith('text_') else 9
            factor=10**precision
            end=row['end'] if start==row['start'] else math.floor((start+row['end']-row['start'])*factor+.5)/factor
            if start!=row['start']:
                if row['id'].startswith('text_'):
                    from .text_clips import validate_text_clip
                    validate_text_clip({**row,'start':start,'end':end},duration)
                else:
                    from .media_library import validate_media_clip
                    validate_media_clip(staged,{**row,'start':start,'end':end},duration)
            if end>duration+1e-8:raise LayerTrackError("Keep the whole clip inside the edit")
            row.update(track_id=identity,start=start,end=end)
    validate_layer_tracks(staged)
    result={key:manual[key] for key in ('layer_tracks','media_clips','text_clips') if key in manual and manual[key]!=project['manual'].get(key)}
    return result or None


def explicit_media_destination(project, payload):
    """Validate identity/kind only; occupancy is checked after the complete edit."""
    action = str(payload.get("action") or "").strip().lower() if isinstance(payload,dict) else ""
    if action not in {"media_add", "media_insert", "media_append"} or "track_id" not in payload:
        return None
    model = validate_layer_tracks(project)
    if model is None:
        raise LayerTrackError("Enable persistent layer tracks before choosing a destination")
    identity = payload["track_id"]
    if not isinstance(identity, str) or not TRACK_RE.fullmatch(identity):
        raise LayerTrackError("Choose a valid destination track")
    track = next((track for track in model["tracks"] if track["id"] == identity), None)
    if track is None:
        raise LayerTrackError("The destination track no longer exists")
    if track.get("locked",False):
        raise LayerTrackError("The destination track is locked. Unlock it before adding clips.")
    asset_id = payload.get("asset_id")
    asset = (project.get("assets") or {}).get(asset_id) if isinstance(asset_id,str) else None
    kind = asset.get("kind") if isinstance(asset,dict) else None
    if kind not in {"video","audio","image"} or track["kind"] != ("audio" if kind == "audio" else "visual"):
        raise LayerTrackError("Choose a destination track compatible with this media")
    return identity


def locked_layer_tracks(project):
    model = validate_layer_tracks(project)
    return tuple(track["id"] for track in model["tracks"] if track.get("locked",False)) if model else ()


def require_layer_tracks_unlocked(project):
    if locked_layer_tracks(project):
        raise LayerTrackError("A layer track is locked. Unlock it before replacing or removing its content.")


def protected_layer_assets(project):
    locked = set(locked_layer_tracks(project))
    assets = {row["asset_id"] for row,kind in _rows(project) if row.get("track_id") in locked and kind != "text"}
    # A keyed background is part of the protected visual source identity too.
    from .composition import normalize_chroma_key
    effects = (project.get("manual") or {}).get("chroma_key") or {}
    for aid in tuple(assets):
        config = normalize_chroma_key(effects.get(aid) if isinstance(effects,dict) else None)
        if config.get("enabled") and config.get("background_mode") != "transparent" and config.get("background_asset_id"):
            assets.add(config["background_asset_id"])
    return assets


def require_layer_asset_unlocked(project, asset_id):
    if asset_id in protected_layer_assets(project):
        raise LayerTrackError("This asset belongs to a locked layer track. Unlock it before regenerating its original.")


def _locked_asset_identity(value):
    # Only derived preparation metadata may refresh while its content is locked.
    mutable = {"_original_content_proof","status","preparation","preparation_error","error","preview_path","thumbnail_path","waveform","audio_profile_ready","prepared_at","updated_at","preparation_identity","preparation_pipeline","preview_mode"}
    return {key:item for key,item in value.items() if key not in mutable} if isinstance(value,dict) else value


def validate_locked_layer_changes(before, after):
    locked = set(locked_layer_tracks(before))
    old_model = (before.get("manual") or {}).get("layer_tracks")
    after_model = (after.get("manual") or {}).get("layer_tracks")
    if (isinstance(old_model,dict) and old_model.get("protection_version",2 if old_model.get("version")==2 else 1)==2
            and isinstance(after_model,dict) and after_model.get("protection_version",2 if after_model.get("version")==2 else 1)<2):
        raise LayerTrackError("A version 2 track model cannot be downgraded by a content edit.")
    if not locked:return
    new_model = validate_layer_tracks(after)
    if new_model is None:
        raise LayerTrackError("A locked layer track cannot be removed. Unlock it first.")
    old_tracks = {t["id"]:t for t in old_model["tracks"]}
    new_tracks = {t["id"]:t for t in new_model["tracks"]}
    old_rows,new_rows = _rows(before),_rows(after)
    for identity in locked:
        if identity not in new_tracks or new_tracks[identity]["kind"]!=old_tracks[identity]["kind"]:
            raise LayerTrackError("A locked layer track cannot be removed or changed.")
        if [r for r,k in old_rows if r.get("track_id")==identity] != [r for r,k in new_rows if r.get("track_id")==identity]:
            raise LayerTrackError("A layer track is locked. Unlock it before changing its clips.")
        kind=old_tracks[identity]["kind"]
        old_order=[t["id"] for t in old_model["tracks"] if t["kind"]==kind]
        new_order=[t["id"] for t in new_model["tracks"] if t["kind"]==kind]
        for other in set(old_order)&set(new_order):
            if (old_order.index(other)<old_order.index(identity)) != (new_order.index(other)<new_order.index(identity)):
                raise LayerTrackError("Track ordering cannot cross a locked layer track.")
    protected=protected_layer_assets(before)
    for aid in protected:
        if _locked_asset_identity((before.get("assets") or {}).get(aid)) != _locked_asset_identity((after.get("assets") or {}).get(aid)):
            raise LayerTrackError("A locked layer's original asset cannot be changed or removed.")
        old_effects=(before.get("manual") or {}).get("chroma_key")
        new_effects=(after.get("manual") or {}).get("chroma_key")
        old_effect=old_effects.get(aid) if isinstance(old_effects,dict) else old_effects
        new_effect=new_effects.get(aid) if isinstance(new_effects,dict) else new_effects
        if old_effect!=new_effect:
            raise LayerTrackError("Chroma Key belongs to a locked layer track. Unlock it before changing the effect.")


def restore_current_layer_locks(before, after):
    """History restores content, never historical protection preferences."""
    validate_layer_tracks(after)  # never reinterpret future/malformed history
    old = (before.get("manual") or {}).get("layer_tracks")
    new = (after.get("manual") or {}).get("layer_tracks")
    if not isinstance(new,dict):return  # invariant refuses removal when currently locked
    current={t["id"]:t.get("locked",False) for t in old["tracks"]} if isinstance(old,dict) else {}
    floor=(old.get("protection_version",2 if old.get("version")==2 else 1) if isinstance(old,dict) else 1)
    if new["version"]==3:
        new["protection_version"]=floor
        for track in new["tracks"]:track["locked"]=current.get(track["id"],False)
    elif floor==2 or new["version"]==2:
        new["version"]=2
        for track in new["tracks"]:track["locked"]=current.get(track["id"],False)



def set_layer_track_lock(project,payload):
    if set(payload)-{"action","track_id","locked","expected_revision"} or type(payload.get("locked")) is not bool:
        raise LayerTrackError("Choose a track and an explicit boolean lock state")
    if not isinstance(project.get("draft"),dict):raise LayerTrackError("Open an edit before changing track locks")
    model=validate_layer_tracks(project)
    if model is None:raise LayerTrackError("Enable persistent layer tracks before locking them")
    track=next((t for t in model["tracks"] if t["id"]==payload.get("track_id")),None)
    if track is None:raise LayerTrackError("Choose an existing layer track")
    if model["version"]==1:
        if not payload["locked"]:return
        model["version"]=2
        for item in model["tracks"]:item["locked"]=False
    if model["version"]==3 and payload["locked"]:model["protection_version"]=2
    track["locked"]=payload["locked"]
