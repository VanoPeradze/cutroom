"""Production Track levels fidelity: synthetic assets only, no server or inference."""
from pathlib import Path
import copy,json,hashlib,subprocess,threading,shutil
from test_media_render import media
from test_track_destination_render import prepared
from test_layer_tracks_render import decoded
from cutroom.projects import ProjectStore
from cutroom.jobs import Job,JobContext
from cutroom.render import render_project,build_filter_graph,_render_input_fingerprint
from cutroom.editing import apply_manual_edit
from cutroom.layer_tracks import validate_layer_tracks
from array import array


def test_track_levels_production_parity(media,tmp_path):
    p,store,settings,unused,unchanged=prepared(media,tmp_path)
    root=store.project_dir(p['id'])
    # Two same-role independently owned lanes; separate source frequencies.
    apply_manual_edit(p,{'action':'media_duplicate','clip_id':p['manual']['media_clips'][1]['id'],'start':0.})
    clip2=p['manual']['media_clips'][-1];newasset=copy.deepcopy(p['assets'][clip2['asset_id']]);aid='asset_'+'e'*32
    newasset.update(id=aid,path=f'media/assets/{aid}/second.wav');clip2['asset_id']=aid
    f=root/newasset['path'];f.parent.mkdir(parents=True)
    subprocess.run([media[1],'-v','error','-y','-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=3',str(f)],check=True,capture_output=True)
    p['assets'][aid]=newasset;p['manual']['audio_mixer'].update(source_muted=True,ducking=False,master_db=0)
    p['manual']['media_clips'][0].update(role='voice',audio_enabled=True,volume_db=-8)
    base=copy.deepcopy(p);sourcehash={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file() and f.name!='project.json'}
    results=[]
    def v3(value):
     q=copy.deepcopy(value);q['manual']['layer_tracks']['protection_version']=2 if q['manual']['layer_tracks']['version']==2 else 1;q['manual']['layer_tracks']['version']=3
     for t in q['manual']['layer_tracks']['tracks']:
      t['locked']=t.get('locked',False)
      if t['kind']!='text':t['audio']={'gain_db':0.,'muted':False}
     validate_layer_tracks(q);return q

    def level(q,clip,gain=0.,muted=False):
     track=next(t for t in q['manual']['layer_tracks']['tracks'] if t['id']==clip['track_id']);track['audio']={'gain_db':gain,'muted':muted}

    def encode(q,label):
     shell=store.create(label);identity=shell['id'];dst=store.project_dir(identity)
     for directory in ('media','cache'):
      shutil.copytree(root/directory,dst/directory,dirs_exist_ok=True,copy_function=shutil.copy2)
     value=copy.deepcopy(q);value.update(id=identity,revision=1,exports=[])
     store.state_path(identity).write_text(json.dumps(value),encoding='utf8')
     out=render_project(JobContext(Job(label,'render',identity),threading.Lock()),identity,ProjectStore(settings),settings,{'quality':'fast','_force_software':True})['export']
     path=settings.exports_dir/out['name'];a=decoded(media[1],path,False);v=decoded(media[1],path)
     results.append({'label':label,'path':str(path),'pcm_sha256':hashlib.sha256(a).hexdigest(),'rgb_sha256':hashlib.sha256(v).hexdigest(),'pcm_bytes':len(a),'rgb_bytes':len(v)})
     return a,v

    one=copy.deepcopy(base);two=copy.deepcopy(base);two['manual']['layer_tracks']['version']=2
    for t in two['manual']['layer_tracks']['tracks']:t['locked']=True
    three=v3(two)
    assert build_filter_graph(one,160,90)==build_filter_graph(two,160,90)==build_filter_graph(three,160,90)
    assert _render_input_fingerprint(one)==_render_input_fingerprint(two)==_render_input_fingerprint(three)
    a=encode(one,'unity-v1');assert encode(two,'unity-v2')==a;assert encode(three,'unity-v3')==a
    # Lower just one music lane, leaving second same-role lane + slow video's normal sound untouched.
    q=v3(base);level(q,q['manual']['media_clips'][1],-6.)
    ref=copy.deepcopy(base);ref['manual']['media_clips'][1]['volume_db']-=6
    assert encode(q,'one-lane-minus6')==encode(ref,'reference-clip-minus6')
    q=v3(base);level(q,q['manual']['media_clips'][1],muted=True)
    ref=copy.deepcopy(base);ref['manual']['media_clips'][1]['muted']=True
    assert encode(q,'one-music-lane-muted')==encode(ref,'reference-one-clip-muted')
    # Embedded video sound mute must preserve picture and produce no voice ducking key.
    q=v3(base);level(q,q['manual']['media_clips'][0],muted=True);q['manual']['audio_mixer']['ducking']=True
    assert 'libkeyvoice' not in build_filter_graph(q,160,90)[0]
    r=copy.deepcopy(q);r['manual']['audio_mixer']['ducking']=False
    muted=encode(q,'muted-voice-duck-on');assert muted==encode(r,'muted-voice-duck-off');assert muted[1]==a[1]
    # Track + role gains enter normalization first, master remains after it.
    q=v3(base);level(q,q['manual']['media_clips'][1],-6);level(q,q['manual']['media_clips'][-1],-3)
    q['manual']['audio_mixer']['master_db']=-4;q['draft']['audio_policy']={'normalize':True,'target_lufs':-18}
    ref=copy.deepcopy(base);ref['manual']['media_clips'][1]['volume_db']-=6;ref['manual']['media_clips'][-1]['volume_db']-=3
    ref['manual']['audio_mixer']['master_db']=-4;ref['draft']['audio_policy']=copy.deepcopy(q['draft']['audio_policy'])
    assert encode(q,'track-level-normalized-master')==encode(ref,'reference-normalized-master')
    assert sourcehash=={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in root.rglob('*') if f.is_file() and f.name!='project.json'}

    # Nonneutral audio is scope-affecting; neutral metadata must not invalidate render identity.
    q=v3(base); neutral=_render_input_fingerprint(q)
    level(q,q['manual']['media_clips'][1],-6)
    assert _render_input_fingerprint(q)!=neutral
    changed=_render_input_fingerprint(q)
    q['manual']['layer_tracks']['protection_version']=2
    for t in q['manual']['layer_tracks']['tracks']: t['name']='Renamed'; t['locked']=not t['locked']
    assert _render_input_fingerprint(q)==changed
    q['manual']['layer_tracks']['tracks'].append({'id':'track_'+'f'*32,'kind':'audio','name':'Empty','locked':False,'audio':{'gain_db':-9.,'muted':True}})
    assert _render_input_fingerprint(q)==changed
    (tmp_path/'render-results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    assert len(results)==11
