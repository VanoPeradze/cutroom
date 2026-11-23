"""User-owned tracks: compositing only, stable input/audio clocks and real export proof."""
import copy
import hashlib
import json
import shutil
import subprocess
import threading

import pytest
from cutroom.config import DEFAULTS, Settings
from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom.layer_tracks import validate_layer_tracks, ordered_layer_clips, layer_tracks_render_identity
from cutroom.render import build_filter_graph, _render_input_fingerprint, render_project
from cutroom.render_inventory import compile_render_inputs
from cutroom.composition import CHROMA_KEY_DEFAULTS
from test_media_render import media, samples, tone_level, pixel


def fixture_project():
    p={"sources":{"A":{"duration":3.,"width":160,"height":90,"has_audio":True}},
       "settings":{"fps":30,"editorial_effects":False},"manual":{},"assets":{},
       "draft":{"source_duration":3.,"output_duration":3.,"keep_ranges":[{"start":0.,"end":3.}],"cuts":[],"camera_plan":[{"start":0.,"end":3.,"camera":"A"}],"audio_policy":{"normalize":False}},
       "analysis":{"transcript":{"segments":[]}}}
    for n,kind in [(1,'video'),(2,'audio'),(3,'image')]:
        aid='asset_'+str(n)*32
        p['assets'][aid]={'id':aid,'kind':kind,'status':'ready','duration':3.,'has_audio':kind!='image','width':160,'height':90,'path':{1:'source.mp4',2:'music.wav',3:'image.png'}[n]}
        apply_manual_edit(p,{'action':'media_add','asset_id':aid,'start':0.,'end':3.,'audio_enabled':kind=='video','role':'voice' if kind=='video' else 'music'})
    return p


def trackify(p):
    # Explicit reference mapping. Production conversion is separately exercised below.
    tracks=[]
    for i,row in enumerate(p['manual'].get('media_clips',[])+p['manual'].get('text_clips',[])):
        kind='text' if row['id'].startswith('text_') else ('audio' if p['assets'][row['asset_id']]['kind']=='audio' else 'visual')
        tid='track_'+format(i+1,'032x');row['track_id']=tid
        tracks.append({'id':tid,'kind':kind,'name':f'{kind} {i+1}'})
    p['manual']['layer_tracks']={'version':1,'tracks':tracks}
    validate_layer_tracks(p)
    return p


def test_visual_track_order_changes_only_overlay_chain_not_inputs_or_audio():
    p=trackify(fixture_project());p["manual"]["audio_mixer"]={"ducking":True,"source_muted":False};before=copy.deepcopy(p)
    inventory=compile_render_inputs(p);graph0,_,_=build_filter_graph(p,160,90)
    p['manual']['layer_tracks']['tracks'].reverse()
    inventory2=compile_render_inputs(p);graph1,_,_=build_filter_graph(p,160,90)
    assert [e.clip for e in inventory.inputs('library')]==[e.clip for e in inventory2.inputs('library')]
    audio=lambda g:[part for part in g.split(';') if 'libaudio' in part or 'libbus' in part or 'libmix' in part]
    assert audio(graph0)==audio(graph1)
    overlays=lambda g:[part for part in g.split(';') if ']overlay=' in part and '[libvideo' in part]
    assert '[libvideo0]' in overlays(graph0)[0] and '[libvideo2]' in overlays(graph1)[0]
    assert _render_input_fingerprint(before)!=_render_input_fingerprint(p)
    with pytest.raises(ValueError,match='inventory'):inventory.validate(p)


def test_track_names_and_unused_tracks_do_not_change_render_identity():
    p=trackify(fixture_project());before=_render_input_fingerprint(p);inventory=compile_render_inputs(p)
    for row in p['manual']['layer_tracks']['tracks']:row['name']='Renamed'
    p['manual']['layer_tracks']['tracks'].insert(0,{'id':'track_'+'f'*32,'kind':'visual','name':'Empty'})
    assert _render_input_fingerprint(p)==before
    inventory.validate(p)


@pytest.mark.parametrize('invalid',[None,{}, {'version':2,'tracks':[]}, {'version':1,'tracks':[]}])
def test_unknown_or_malformed_track_model_fails_before_render(invalid):
    p=fixture_project();p['manual']['layer_tracks']=invalid
    for call in [compile_render_inputs,_render_input_fingerprint,lambda p:build_filter_graph(p,160,90)]:
        with pytest.raises(ValueError):call(p)


def test_legacy_render_identity_and_graph_are_not_modified_on_read():
    p=fixture_project();before=copy.deepcopy(p)
    _render_input_fingerprint(p);compile_render_inputs(p);build_filter_graph(p,160,90)
    assert p==before and 'layer_tracks' not in p['manual']


def decoded(ffmpeg,path,video=True):
    args=['-an','-pix_fmt','rgb24','-f','rawvideo'] if video else ['-vn','-ac','2','-ar','48000','-f','f32le']
    return subprocess.check_output([ffmpeg,'-v','error','-i',str(path),*args,'pipe:1'])


def test_production_encode_migration_and_visual_order_preserve_audio(media,tmp_path,monkeypatch):
    raw=copy.deepcopy(DEFAULTS);raw['render'].update(prefer_hardware=False,min_free_mb=0)
    data=tmp_path/'data';projects,exports,cache=(data/name for name in ('projects','exports','cache'))
    for folder in (projects,exports,cache):folder.mkdir(parents=True)
    settings=Settings(raw,tmp_path,data,projects,exports,cache,media[1],media[2]);store=ProjectStore(settings)
    p=store.create('track renderer synthetic');p.update(fixture_project());pid=p['id'];root=store.project_dir(pid)
    p['sources']['A']['relative_path']='media/source.mp4'
    for old,name in [(media[3],'source.mp4'),(media[4],'music.wav'),(media[5],'image.png')]:shutil.copyfile(old,root/'media'/name)
    for asset in p['assets'].values():
        old=root/'media'/asset['path'];asset['path']=f"media/assets/{asset['id']}/{asset['path']}"
        destination=root/asset['path'];destination.parent.mkdir(parents=True);shutil.copyfile(old,destination)
    p['settings'].update(aspect='source',resolution='1440',quality='fast',burn_captions=True,captions=True,editorial_effects=False)
    p['analysis']['transcript']={'segments':[{'start':.2,'end':2.8,'text':'Original caption'}]}
    slow,music,image=p['manual']['media_clips']
    slow.update(speed=.5,video_source_start=.25,audio_enabled=True,role='voice',volume_db=-4,fade_in=.1,fade_out=.2)
    image.update(x=.45,y=.1,w=.5,h=.65,motion='pan',fit='contain')
    music.update(volume_db=-12,fade_in=.2,fade_out=.2)
    p['manual']['audio_mixer']={'source_muted':True,'master_db':-3,'ducking':False}
    apply_manual_edit(p,{'action':'text_add','kind':'title','text':'Track title','start':.4,'end':2.6,'position':'bottom','scale':75,'template':'lower_third','subtext':'Retained'})
    apply_manual_edit(p,{'action':'text_add','kind':'caption','text':'Custom caption','start':.6,'end':2.4,'position':'top','scale':75})
    # A real transparent keyed foreground, independently decoded and composited.
    aid='asset_'+'4'*32;keyfile=root/f'media/assets/{aid}/key.mp4';keyfile.parent.mkdir(parents=True)
    subprocess.run([media[1],'-v','error','-y','-f','lavfi','-i','color=0x00ff00:s=160x90:r=30:d=3,drawbox=x=10:y=10:w=30:h=30:color=red:t=fill','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(keyfile)],check=True,capture_output=True,timeout=20)
    p['assets'][aid]={'id':aid,'kind':'video','status':'ready','duration':3.,'has_audio':False,'width':160,'height':90,'path':f'media/assets/{aid}/key.mp4'}
    apply_manual_edit(p,{'action':'media_add','asset_id':aid,'start':0.,'end':3.,'motion':'zoom_in','audio_enabled':False})
    apply_manual_edit(p,{'action':'set_chroma_key','slot':aid,**CHROMA_KEY_DEFAULTS,'enabled':True,'background_mode':'transparent'})
    # Disabled/offline occurrence remains owned, but export must not open its path.
    offline='asset_'+'5'*32;p['assets'][offline]={'id':offline,'kind':'image','status':'failed','path':f'media/assets/{offline}/missing.png'}
    disabled=copy.deepcopy(image);disabled.update(id='media_'+'e'*32,asset_id=offline,enabled=False);p['manual']['media_clips'].append(disabled)
    store.save(p);originals=[root/'media'/name for name in ('source.mp4','music.wav','image.png')]+[keyfile]
    hashes={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}
    def encode(label):
        record=render_project(JobContext(Job(label,'render',pid),threading.Lock()),pid,store,settings,{'quality':'fast','_force_software':True})['export']
        return settings.exports_dir/record['name']
    old=encode('tracks-legacy');legacy=store.load(pid)
    converted=copy.deepcopy(legacy);apply_manual_edit(converted,{"action":"layer_tracks_enable"});store.save(converted)
    migrated=encode('tracks-migrated')
    assert decoded(media[1],old)==decoded(media[1],migrated)
    assert decoded(media[1],old,False)==decoded(media[1],migrated,False)
    moved=store.load(pid);visuals=[t for t in moved['manual']['layer_tracks']['tracks'] if t['kind']=='visual']
    # Put the pan image below the slow full-frame video; foreground key remains top.
    apply_manual_edit(moved,{'action':'layer_track_reorder','track_id':visuals[1]['id'],'position':'backward'})
    store.save(moved);reordered=encode('tracks-reordered')
    assert decoded(media[1],old)!=decoded(media[1],reordered)
    assert decoded(media[1],old,False)==decoded(media[1],reordered,False)
    undone=store.load(pid);apply_manual_edit(undone,{'action':'undo'});store.save(undone);undo_output=encode('tracks-reorder-undone')
    assert decoded(media[1],undo_output)==decoded(media[1],migrated)
    assert decoded(media[1],undo_output,False)==decoded(media[1],migrated,False)
    undone=store.load(pid);apply_manual_edit(undone,{'action':'redo'});store.save(undone)
    sound=samples(media[1],reordered)
    assert tone_level(sound,.5,440)<.003 and tone_level(sound,1.3,440)>.03
    # Saved state survives a fresh store, and original files are untouched.
    assert ProjectStore(settings).load(pid)['manual']['layer_tracks']==moved['manual']['layer_tracks']
    # A true occurrence move to a newly created visual lane, with timing retained.
    vertical=store.load(pid);apply_manual_edit(vertical,{'action':'layer_track_add','kind':'visual','name':'New upper picture'})
    destination=vertical['manual']['layer_tracks']['tracks'][-1]['id']
    source_clip=copy.deepcopy(vertical['manual']['media_clips'][0])
    apply_manual_edit(vertical,{'action':'layer_move','clip_id':source_clip['id'],'track_id':destination,'start':source_clip['start']})
    assert {k:v for k,v in vertical['manual']['media_clips'][0].items() if k!='track_id'}=={k:v for k,v in source_clip.items() if k!='track_id'}
    store.save(vertical);vertical_output=encode('tracks-vertical-move')
    assert decoded(media[1],vertical_output)!=decoded(media[1],reordered)
    assert decoded(media[1],vertical_output,False)==decoded(media[1],reordered,False)
    assert pixel(media[1],vertical_output,1.3,5,5)[0]>200  # .9s picture while 1.3s sound is audible
    assert pixel(media[1],vertical_output,2.,5,5)[1]>200
    # A render-affecting track change during a real encode cannot commit stale output.
    import cutroom.render as renderer
    original_run=renderer._run_ffmpeg_process;changed=[];exports_before=len(store.load(pid)['exports'])
    def change_after_encode(*args,**kwargs):
        result=original_run(*args,**kwargs)
        if result[0]==0 and not changed:
            changed.append(True)
            store.update(pid,lambda current:apply_manual_edit(current,{'action':'layer_track_reorder','track_id':destination,'position':'back'}))
        return result
    monkeypatch.setattr(renderer,'_run_ffmpeg_process',change_after_encode)
    with pytest.raises(RuntimeError,match='project_changed_during_render'):encode('tracks-stale-render')
    assert changed and len(store.load(pid)['exports'])==exports_before
    assert {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}==hashes


def test_real_custom_text_track_order_preserves_legacy_ass_layers(media,tmp_path):
    from cutroom.captions import build_ass
    from cutroom.text_clips import validated_text_clips
    p=fixture_project();p['manual']['media_clips']=[]
    for text,start,scale in [('AAAAAA',.1,150),('BBBBBB',.2,75)]:
        apply_manual_edit(p,{'action':'text_add','kind':'title','text':text,'start':start,'end':2.,'position':'center','scale':scale,'style':'boxed'})
    def frame(label,value):
        rows=ordered_layer_clips(value,'text',validated_text_clips(value,enabled_only=True))
        target=tmp_path/f'{label}.ass';build_ass({},[],target,160,90,text_clips=rows)
        # Do not alter legacy custom Layer1 / automatic Layer0 behavior.
        assert all(line.startswith('Dialogue: 1,') for line in target.read_text(encoding='utf-8-sig').splitlines() if line.startswith('Dialogue:'))
        escaped=target.resolve().as_posix().replace(':','\\:')
        return subprocess.check_output([media[1],'-v','error','-f','lavfi','-i','color=blue:s=160x90:r=30:d=1','-vf',f"ass=filename='{escaped}'",'-ss','0.8','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    legacy=frame('legacy-text',p);apply_manual_edit(p,{'action':'layer_tracks_enable'})
    assert frame('migrated-text',p)==legacy
    tid=p['manual']['text_clips'][0]['track_id'];apply_manual_edit(p,{'action':'layer_track_reorder','track_id':tid,'position':'front'})
    assert frame('reordered-text',p)!=legacy
    apply_manual_edit(p,{'action':'undo'});assert frame('undone-text',p)==legacy


def test_disabled_bad_membership_and_same_track_overlap_fail_before_filtering():
    p=trackify(fixture_project());p['manual']['media_clips'][0]['enabled']=False
    p['manual']['media_clips'][0]['track_id']='track_'+'f'*32
    with pytest.raises(ValueError):compile_render_inputs(p)
    p=trackify(fixture_project());p['manual']['media_clips'][2]['track_id']=p['manual']['media_clips'][0]['track_id']
    with pytest.raises(ValueError):build_filter_graph(p,160,90)


def test_production_ab_source_mapping_conversion_and_undo_parity(media, tmp_path):
    """Actual A/B base edits stay outside imported tracks, including B sound gaps."""
    raw = copy.deepcopy(DEFAULTS)
    raw['render'].update(prefer_hardware=False, min_free_mb=0)
    data = tmp_path / 'data'
    projects, exports, cache = (data / name for name in ('projects', 'exports', 'cache'))
    for folder in (projects, exports, cache):
        folder.mkdir(parents=True)
    settings = Settings(raw, tmp_path, data, projects, exports, cache, media[1], media[2])
    store = ProjectStore(settings)
    p = store.create('A B migration parity')
    p.update(fixture_project())
    pid = p['id']
    root = store.project_dir(pid)
    for old, name in [(media[3], 'source.mp4'), (media[4], 'music.wav'), (media[5], 'image.png')]:
        shutil.copyfile(old, root / 'media' / name)
    bfile = root / 'media' / 'camera-b.mp4'
    subprocess.run([media[1], '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'color=yellow:s=160x90:r=30:d=3', '-f', 'lavfi', '-i',
        'sine=frequency=660:sample_rate=48000:duration=3', '-c:v', 'libx264',
        '-preset', 'ultrafast', '-c:a', 'aac', '-t', '3', str(bfile)],
        check=True, capture_output=True, timeout=20)
    p['sources']['A']['relative_path'] = 'media/source.mp4'
    p['sources']['B'] = dict(p['sources']['A'], relative_path='media/camera-b.mp4')
    for asset in p['assets'].values():
        source = root / 'media' / asset['path']
        asset['path'] = f"media/assets/{asset['id']}/{asset['path']}"
        destination = root / asset['path']
        destination.parent.mkdir(parents=True)
        shutil.copyfile(source, destination)
    p['settings'].update(aspect='source', resolution='1440', quality='fast',
        burn_captions=True, captions=True, editorial_effects=False, audio_source='B')
    p['draft']['camera_plan'] = [{'start':0., 'end':1., 'camera':'A'},
        {'start':1., 'end':2., 'camera':'B'}, {'start':2., 'end':3., 'camera':'stacked'}]
    p['manual']['source_tracks'] = {
        'A':[{'id':'A:first', 'start':0., 'end':1.5, 'source_start':1.},
             {'id':'A:last', 'start':2., 'end':3., 'source_start':0.}],
        'B':[{'id':'B:first', 'start':0., 'end':.75, 'source_start':1.5},
             {'id':'B:last', 'start':1.25, 'end':3., 'source_start':0.}]}
    p['manual']['source_mixer'] = {'screen_slot':'A', 'camera_slot':'B',
        'primary_role':'screen', 'audio_slot':'B', 'sync_offset':0.}
    p['manual']['audio_mixer'] = {'source_muted':False, 'source_db':0., 'ducking':False}
    video, music, image = p['manual']['media_clips']
    video.update(x=.65, y=.05, w=.3, h=.3, speed=.5, video_source_start=.25, audio_enabled=False)
    music.update(volume_db=-18)
    image.update(x=.05, y=.65, w=.2, h=.3)
    p['analysis'].update(audio_source='B', audio_timeline_offset=0.)
    p['analysis']['transcript'] = {'segments':[{'start':.1, 'end':2.9, 'text':'Automatic A B caption'}]}
    apply_manual_edit(p, {'action':'text_add', 'kind':'title', 'text':'Custom title',
        'start':.2, 'end':2.8, 'position':'top', 'scale':75})
    protected = copy.deepcopy({k:p[k] for k in ('sources', 'draft', 'analysis')})
    base_tracks = copy.deepcopy(p['manual']['source_tracks'])
    mixer = copy.deepcopy(p['manual']['source_mixer'])
    originals = [root / 'media' / n for n in ('source.mp4','camera-b.mp4','music.wav','image.png')]
    originals += [root / a['path'] for a in p['assets'].values()]
    hashes = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals}
    store.save(p)
    def encode(label):
        # Fresh store load on every leg, not only an in-memory graph comparison.
        fresh = ProjectStore(settings)
        result = render_project(JobContext(Job(label, 'render', pid), threading.Lock()),
            pid, fresh, settings, {'quality':'fast', '_force_software':True})['export']
        return settings.exports_dir / result['name']
    legacy = encode('ab-legacy')
    migrated = ProjectStore(settings).load(pid)
    apply_manual_edit(migrated, {'action':'layer_tracks_enable'})
    store.save(migrated)
    converted = encode('ab-converted')
    restored = ProjectStore(settings).load(pid)
    apply_manual_edit(restored, {'action':'undo'})
    store.save(restored)
    undone = encode('ab-undo')
    for output in (converted, undone):
        assert decoded(media[1], output) == decoded(media[1], legacy)
        assert decoded(media[1], output, False) == decoded(media[1], legacy, False)
    audio = samples(media[1], legacy)
    assert tone_level(audio, .4, 660) > .02
    assert tone_level(audio, 1., 660) < .003  # Explicit B gap, not fallback to A.
    assert tone_level(audio, 1.6, 660) > .02
    final = ProjectStore(settings).load(pid)
    assert 'layer_tracks' not in final['manual']
    assert final['manual']['source_tracks'] == base_tracks
    assert final['manual']['source_mixer'] == mixer
    assert final['sources'] == protected['sources']
    assert final['analysis'] == protected['analysis']
    # Existing Undo refreshes edited_at and materializes absent optional defaults.
    def draft_content(value):
        value = copy.deepcopy(value)
        value.pop('edited_at', None)
        for key, default in [('edit_points', []), ('removed_duration', None), ('active_reel_candidate', None)]:
            value.setdefault(key, default)
        return value
    assert draft_content(final['draft']) == draft_content(protected['draft'])
    assert {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals} == hashes
