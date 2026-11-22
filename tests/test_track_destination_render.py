"""Real production proof for deliberate imported-layer track destinations."""
import copy
import hashlib
import shutil
import subprocess
import threading
import pytest
from cutroom.config import DEFAULTS, Settings
from cutroom.projects import ProjectStore
from cutroom.editing import apply_manual_edit
from cutroom.jobs import Job, JobContext
from cutroom.render import render_project
from test_media_render import media, samples, tone_level, pixel
from test_layer_tracks_render import fixture_project, decoded


def prepared(media, tmp_path):
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

    # Keep the crossing slow clip audible; its picture clock remains independent.
    video.update(x=0., y=0., w=1., h=1., audio_enabled=True, volume_db=-8)
    apply_manual_edit(p, {'action':'layer_tracks_enable'})
    originals = [f for f in (root/'media').rglob('*') if f.is_file()]
    hashes = {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals}
    store.save(p)
    def encode(value, label):
        store.save(value)
        result = render_project(JobContext(Job(label,'render',pid),threading.Lock()), pid,
            ProjectStore(settings),settings,{'quality':'fast','_force_software':True})['export']
        return settings.exports_dir/result['name']
    def unchanged():
        assert {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in originals} == hashes
    return p, store, settings, encode, unchanged


def new_visual(p, name):
    apply_manual_edit(p, {'action':'layer_track_add','kind':'visual','name':name})
    return p['manual']['layer_tracks']['tracks'][-1]['id']


def test_explicit_lower_upper_add_changes_picture_only(media,tmp_path):
    p,store,settings,encode,unchanged=prepared(media,tmp_path)
    low=new_visual(p,'Chosen lower')
    apply_manual_edit(p,{'action':'layer_track_reorder','track_id':low,'position':'back'})
    high=new_visual(p,'Chosen upper')
    baseline=copy.deepcopy(p)
    asset=p['manual']['media_clips'][2]['asset_id']
    def added(track):
        value=copy.deepcopy(baseline)
        apply_manual_edit(value,{'action':'media_add','asset_id':asset,'start':0.,'end':3.,
            'track_id':track,'x':0.,'y':0.,'w':1.,'h':1.})
        assert value['manual']['media_clips'][-1]['track_id']==track
        return value
    lower=added(low);upper=added(high)
    out_low=encode(lower,'chosen-lower');out_high=encode(upper,'chosen-upper')
    assert decoded(media[1],out_low)!=decoded(media[1],out_high)
    assert decoded(media[1],out_low,False)==decoded(media[1],out_high,False)
    reopened=ProjectStore(settings).load(p['id'])
    assert reopened['manual']['media_clips']==upper['manual']['media_clips']
    apply_manual_edit(reopened,{'action':'undo'})
    assert reopened['manual']['media_clips']==baseline['manual']['media_clips']
    restored=encode(reopened,'chosen-add-undone')
    original=encode(baseline,'chosen-add-baseline')
    assert decoded(media[1],restored)==decoded(media[1],original)
    assert decoded(media[1],restored,False)==decoded(media[1],original,False)
    unchanged()


def test_chosen_crossing_insert_and_append_match_automatic_output(media,tmp_path):
    p,store,settings,encode,unchanged=prepared(media,tmp_path)
    baseline=copy.deepcopy(p)
    slow=p['manual']['media_clips'][0]
    aid=slow['asset_id'];lane=slow['track_id']
    request={'action':'media_insert','asset_id':aid,'source_start':1.,'source_end':2.,'start':1.5}
    automatic=copy.deepcopy(baseline);apply_manual_edit(automatic,request)
    explicit=copy.deepcopy(baseline);apply_manual_edit(explicit,{**request,'track_id':lane})
    clips=explicit['manual']['media_clips'];placed=clips[-1]
    assert placed['track_id']==lane and placed['start']==1.5 and placed['end']==2.5
    left=next(c for c in clips if c['id']==slow['id'])
    right=next(c for c in clips if c['asset_id']==aid and c['id'] not in {slow['id'],placed['id']})
    assert left['track_id']==right['track_id']==lane
    assert left['end']==1.5 and right['start']==2.5 and right['end']==4.
    assert right['source_start']==1.5 and right['video_source_start']==1.
    assert right['speed']==.5
    assert explicit['manual']['source_tracks']==automatic['manual']['source_tracks']
    content=lambda rows:[{k:v for k,v in row.items() if k!='id'} for row in rows]
    assert content(explicit['manual']['text_clips'])==content(automatic['manual']['text_clips'])
    # IDs of split copies are intentionally fresh; compare their content below.
    out_auto=encode(automatic,'destination-auto-insert')
    out_explicit=encode(explicit,'destination-chosen-insert')
    assert decoded(media[1],out_auto)==decoded(media[1],out_explicit)
    assert decoded(media[1],out_auto,False)==decoded(media[1],out_explicit,False)
    audio=samples(media[1],out_explicit)
    assert tone_level(audio,.4,660)>.02 and tone_level(audio,1.,660)<.003
    reopened=ProjectStore(settings).load(p['id'])
    assert reopened['manual']['layer_tracks']==explicit['manual']['layer_tracks']
    apply_manual_edit(reopened,{'action':'undo'})
    assert reopened['manual']['source_tracks']==baseline['manual']['source_tracks']
    assert reopened['manual']['media_clips']==baseline['manual']['media_clips']
    assert reopened['manual']['text_clips']==baseline['manual']['text_clips']
    original=encode(baseline,'destination-baseline');undone=encode(reopened,'destination-undone')
    assert decoded(media[1],original)==decoded(media[1],undone)
    assert decoded(media[1],original,False)==decoded(media[1],undone,False)
    append={'action':'media_append','asset_id':aid,'source_start':1.,'source_end':2.}
    a=copy.deepcopy(baseline);b=copy.deepcopy(baseline)
    apply_manual_edit(a,append);apply_manual_edit(b,{**append,'track_id':lane})
    assert b['manual']['media_clips'][-1]['track_id']==lane
    auto_tail=encode(a,'destination-auto-append');chosen_tail=encode(b,'destination-chosen-append')
    assert decoded(media[1],auto_tail)==decoded(media[1],chosen_tail)
    assert decoded(media[1],auto_tail,False)==decoded(media[1],chosen_tail,False)
    unchanged()
