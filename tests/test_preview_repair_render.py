from typing import Any
from cutroom.render import stable_fingerprint, validate_layer_tracks, source_chroma_key, chroma_video_targets, layer_tracks_render_identity
import copy,hashlib,json,threading,subprocess
from pathlib import Path
from test_media_render import media
from test_track_destination_render import prepared
from test_layer_tracks_render import decoded
from cutroom.render import render_project,build_filter_graph,_render_input_fingerprint
from cutroom.render_inventory import compile_render_inputs
from cutroom.projects import ProjectStore
from cutroom.jobs import Job,JobContext
from cutroom.media_library import prepare_asset,probe_asset
from cutroom.preview_repair import repair_asset,FIELD
from cutroom.stabilization import stabilize_video

def legacy_render_input_fingerprint(project: dict[str, Any]) -> str:
    """Identify every project field that can change the rendered pixels/audio."""
    validate_layer_tracks(project)
    settings = project.get("settings") or {}
    analysis = project.get("analysis") or {}
    manual = project.get("manual") or {}
    return stable_fingerprint(
        "render-input-2026-09-05.fps",
        {
            "sources": project.get("sources"),
            "assets": project.get("assets"),
            "draft": project.get("draft"),
            "settings": {
                key: settings.get(key)
                for key in (
                    "aspect", "resolution", "quality", "fps", "captions", "burn_captions", "editorial_effects",
                    "caption_style", "caption_position", "caption_scale", "caption_words_per_line",
                )
            },
            "manual": {
                **({"chroma_key": {slot: source_chroma_key(project, slot) for slot in chroma_video_targets(project)
                                    if source_chroma_key(project, slot)["enabled"]}}
                   if any(source_chroma_key(project, slot)["enabled"] for slot in chroma_video_targets(project)) else {}),
                "crop": manual.get("crop"),
                "source_mixer": manual.get("source_mixer"),
                "source_tracks": manual.get("source_tracks"),
                "sequence": manual.get("sequence"),
                "camera_overrides": manual.get("camera_overrides"),
                "media_clips": manual.get("media_clips"),
                "text_clips": manual.get("text_clips"),
                "audio_mixer": manual.get("audio_mixer"),
                **({"layer_tracks": layer_tracks_render_identity(project)}
                   if "layer_tracks" in manual else {}),
                # Only present once the user edits a caption, so older exports stay current.
                **({key: manual.get(key) for key in ("caption_corrections", "caption_overrides", "caption_override_anchors") if manual.get(key)}
                   if settings.get("captions") or settings.get("burn_captions") else {}),
            },
            "transcript": analysis.get("transcript") if settings.get("captions") or settings.get("burn_captions") else None,
            "caption_provenance": {
                "audio_source": analysis.get("audio_source"),
                "audio_timeline_offset": analysis.get("audio_timeline_offset"),
            } if settings.get("captions") or settings.get("burn_captions") else None,
            "story_beats": analysis.get("story_beats") if settings.get("editorial_effects", True) is not False else None,
        },
    )

def test_repair_render(media,tmp_path,monkeypatch):
    p,store,settings,_,_=prepared(media,tmp_path);pid=p['id'];root=store.project_dir(pid)
    video,music,image=p['manual']['media_clips'];aid=video['asset_id'];a=p['assets'][aid]
    # Generate a real stabilized original once; preview repair must never run this again.
    source=root/a['path'];target=source.with_name('stabilized.mp4')
    stabilize_video(source,target,settings)
    a.update(path=target.relative_to(root).as_posix(),stabilized=True,_stabilization={'proof_fixture':True})
    a.update(probe_asset(target,'video',settings))
    model=p['manual']['layer_tracks'];model.update(version=3,protection_version=1)
    for t in model['tracks']:
        t['locked']=False
        if t['kind']!='text':t['audio']={'gain_db':-6.0 if t['id']==video['track_id'] else 0.,'muted':t['id']==music['track_id']}
    for asset in p['assets'].values():asset.update(probe_asset(root/asset['path'],asset['kind'],settings))
    store.save(p)
    def context(label):return JobContext(Job(label,'prepare_asset',pid),threading.Lock())
    for id in list(p['assets']):prepare_asset(context('prepare'),pid,id,store,settings)
    base=store.load(pid);manual=copy.deepcopy(base['manual']);results=[]
    originals=[root/a['path'] for a in base['assets'].values()]+[root/a['relative_path'] for a in base['sources'].values()]
    hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals}
    def encode(label):
        out=render_project(context(label),pid,ProjectStore(settings),settings,{'quality':'fast','_force_software':True})['export'];path=settings.exports_dir/out['name']
        pcm=decoded(media[1],path,False);rgb=decoded(media[1],path)
        results.append({'label':label,'path':str(path),'pcm':hashlib.sha256(pcm).hexdigest(),'rgb':hashlib.sha256(rgb).hexdigest()});return pcm,rgb
    unstamped=copy.deepcopy(base)
    for a in unstamped['assets'].values():a.pop(FIELD,None)
    assert legacy_render_input_fingerprint(unstamped)==_render_input_fingerprint(unstamped)
    assert _render_input_fingerprint(unstamped)==_render_input_fingerprint(base)
    assert build_filter_graph(unstamped,160,90)==build_filter_graph(base,160,90)
    assert compile_render_inputs(unstamped).input_args(root)==compile_render_inputs(base).input_args(root)
    store.save(unstamped);before=encode('unstamped');store.save(base);assert encode('stamped')==before
    # Repair cannot silently regenerate stabilized content.
    monkeypatch.setattr('cutroom.stabilization.stabilize_video',lambda *a,**k:(_ for _ in ()).throw(AssertionError('stabilization forbidden')))
    monkeypatch.setattr('cutroom.stabilization_assets.prepare_stabilized_asset',lambda *a,**k:(_ for _ in ()).throw(AssertionError('stabilization forbidden')))
    for id,damage in [(aid,'missing'),(image['asset_id'],'corrupt')]:
        current=store.load(pid);asset=current['assets'][id];preview=root/asset['preview_path']
        if damage=='missing':preview.unlink()
        else:preview.write_bytes(b'not a preview')
        repair_asset(context('repair'),pid,id,store,settings,copy.deepcopy(asset))
        after=store.load(pid);assert after['manual']==manual;assert after['settings']==base['settings'];assert after['analysis']==base['analysis'];assert after['draft']==base['draft']
        subprocess.run([media[1],'-v','error','-i',str(root/after['assets'][id]['preview_path']),'-frames:v','1','-f','null','-'],check=True,capture_output=True)
        assert encode(damage)==before
    assert hashes=={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals}
    identity=_render_input_fingerprint(base)
    for key,value in [('path','media/other.mp4'),('preview_path','cache/other.mp4'),('preparation_identity','different'),('_other_private',True)]:
        q=copy.deepcopy(base);q['assets'][aid][key]=value;assert _render_input_fingerprint(q)!=identity
    q=copy.deepcopy(base);q['assets'][aid][FIELD]={'arbitrary':'excluded proof only'};assert _render_input_fingerprint(q)==identity
    # Byte changes are admitted/refused by the proof, not magically hashed by project-only fingerprint.
    original_bytes=target.read_bytes();target.write_bytes(b'changed original');state=store.load(pid)
    import pytest
    with pytest.raises(Exception,match='content proof|metadata|Invalid|preview_repair_failed'):
        repair_asset(context('changed'),pid,aid,store,settings,copy.deepcopy(state['assets'][aid]))
    assert store.load(pid)==state
    target.write_bytes(original_bytes)
    (tmp_path/'renderer-results.json').write_text(json.dumps(results,indent=2))
