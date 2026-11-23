"""Retained edit Resume: independent post-reset production-render reference."""
import copy
import hashlib
import subprocess
import pytest
from cutroom.editing import apply_manual_edit
from cutroom.projects import ProjectStore
from cutroom.sequence import editor_sequence_snapshot
from cutroom.render import project_caption_items
from test_media_render import media, samples, tone_level, pixel
from test_layer_tracks_render import decoded
from test_track_destination_render import prepared


def retained_fixture(media,tmp_path):
    p,store,settings,encode,_=prepared(media,tmp_path)
    root=store.project_dir(p['id']);original=root/'media/source.mp4';long_source=root/'media/source-eight.mp4'
    subprocess.run([media[1],'-v','error','-y','-stream_loop','-1','-i',str(original),
        '-t','8','-c:v','libx264','-preset','ultrafast','-c:a','aac',str(long_source)],
        check=True,capture_output=True,timeout=30)
    p['sources']['A'].update(duration=8.,relative_path='media/source-eight.mp4')
    manual=p['manual']
    manual['sequence']={'version':1,'duration':24.,'camera_plan':[
        {'start':0.,'end':12.,'camera':'A'},{'start':12.,'end':24.,'camera':'stacked'}],
        'base_source_tracks':{'A':[{'id':'A:base','start':0.,'end':8.,'source_start':0.}]}}
    manual['source_tracks']={'A':[{'id':'A:retained-left','start':0.,'end':4.,'source_start':0.},
        {'id':'A:retained-later','start':12.,'end':16.,'source_start':4.}], 'B':[]}
    manual['source_mixer'].update(audio_slot='A')
    manual['audio_mixer'].update(master_db=-3.,source_db=-4.,ducking=False)
    slow,music,image=manual['media_clips']
    slow.update(start=20.,end=23.,source_start=0.,video_source_start=.25,speed=.5,
        audio_enabled=True,fade_in=.1,fade_out=.2)
    music.update(start=20.,end=23.,source_start=0.,volume_db=-18.)
    image.update(start=0.,end=24.,x=.05,y=.65,w=.2,h=.3,motion='pan',fit='contain')
    manual['text_clips'][0].update(start=20.,end=23.,text='Retained after A ends',subtext='No transcript rebuilt')
    manual.pop('_history',None);manual['history']={'undo_count':0,'redo_count':0}
    p['analysis']=None;p['draft']=None
    store.save(p);p=ProjectStore(settings).load(p['id'])
    files=[f for f in (root/'media').rglob('*') if f.is_file()]
    hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    return p,store,settings,encode,lambda: {str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}==hashes


def test_resume_retained_24_second_edit_matches_independent_reference(media,tmp_path):
    from cutroom.retained_edit import resume_retained_edit
    p,store,settings,encode,hashes_ok=retained_fixture(media,tmp_path)
    protected=copy.deepcopy({key:p[key] for key in ('manual','settings','analysis','sources','assets')})
    # Independently authored neutral ORIGINAL-source scaffold, not helper output.
    reference=copy.deepcopy(p)
    reference['draft']={'engine':'manual_reference','status':'ready','source_duration':8.,
        'output_duration':8.,'target_duration':8.,'removed_duration':0.,'cuts':[],
        'keep_ranges':[{'start':0.,'end':8.}],
        'camera_plan':[{'start':0.,'end':8.,'camera':'A'}], 'audio_plan':[],
        'audio_policy':{'normalize':False},'audio_source':'A'}
    expected=encode(reference,'retained-independent-reference')
    store.save(p)
    resumed=ProjectStore(settings).load(p['id'])
    resume_retained_edit(resumed)
    assert {key:resumed[key] for key in protected}==protected
    assert resumed['draft']['source_duration']==8.
    assert editor_sequence_snapshot(resumed)['duration']==24.
    assert resumed['manual']['source_tracks']['B']==[]
    assert project_caption_items(resumed)==[]  # No fabricated automatic transcript.
    actual=encode(resumed,'retained-actual-resume')
    assert decoded(media[1],actual)==decoded(media[1],expected)
    assert decoded(media[1],actual,False)==decoded(media[1],expected,False)
    # Actual picture/sound past A EOF, including independent half-speed picture.
    assert pixel(media[1],actual,21.3,5,5)[0]>200
    assert tone_level(samples(media[1],actual),21.3,440)>.015
    reopened=ProjectStore(settings).load(p['id'])
    assert editor_sequence_snapshot(reopened)['duration']==24.
    assert {key:reopened[key] for key in protected}==protected
    clip=reopened['manual']['media_clips'][0]
    apply_manual_edit(reopened,{'action':'media_set_enabled','clip_id':clip['id'],'enabled':False})
    changed=encode(reopened,'retained-next-edit')
    assert decoded(media[1],changed)!=decoded(media[1],actual)
    apply_manual_edit(reopened,{'action':'undo'})
    restored=encode(reopened,'retained-next-edit-undone')
    assert decoded(media[1],restored)==decoded(media[1],actual)
    assert decoded(media[1],restored,False)==decoded(media[1],actual,False)
    assert reopened['manual']['media_clips']==protected['manual']['media_clips']
    assert reopened['manual']['layer_tracks']==protected['manual']['layer_tracks']
    assert hashes_ok()


def test_resume_empty_retained_sequence_stays_unexportable(media,tmp_path):
    from cutroom.retained_edit import resume_retained_edit
    p,store,settings,encode,hashes_ok=retained_fixture(media,tmp_path)
    p['manual']['sequence'].update(duration=0.,camera_plan=[])
    p['manual']['source_tracks']={'A':[],'B':[]}
    p['manual']['media_clips']=[];p['manual']['text_clips']=[]
    before=copy.deepcopy(p['manual'])
    resume_retained_edit(p)
    assert p['manual']==before and editor_sequence_snapshot(p)['duration']==0.
    with pytest.raises(ValueError,match='Add footage'):
        encode(p,'retained-empty-refused')
    assert hashes_ok()
