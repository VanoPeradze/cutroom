"""Keep keyed Media alpha until it meets earlier timeline layers."""
import copy
import shutil
import subprocess

import pytest

from cutroom.composition import CHROMA_KEY_DEFAULTS, normalize_chroma_key
from cutroom.editing import ManualEditError, apply_manual_edit
from test_chroma_all_sources import VIDEO, asset, with_videos
from test_chroma_api import api, apply, frame
from test_chroma_editing import change
from test_chroma_image_background import image_media, _image_render
from test_chroma_render import KEY, _pixel, _samples, chroma_media


@pytest.mark.parametrize('motion', ['none', 'pan', 'zoom_in'])
@pytest.mark.parametrize('fit', ['cover', 'contain'])
def test_transparent_media_keeps_background_audio_timing_and_foreground(image_media, tmp_path, motion, fit):
    media, root, _, _ = image_media
    ffmpeg, _, sources = media
    path = root / asset()['path']
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(sources[1], path)
    value = with_videos()
    value['manual']['chroma_key'] = {'A':dict(KEY)}
    value['manual']['media_clips'] = []
    # Consecutive uses of one asset, with different source-in points and speed.
    value['manual']['media_clips'] = [
        {'id':'one','asset_id':VIDEO,'start':.2,'end':1,'source_start':.25,'speed':1,'fit':fit,'motion':motion,'w':.8,'h':1,'audio_enabled':False},
        {'id':'two','asset_id':VIDEO,'start':1,'end':1.8,'source_start':.1,'speed':2,'fit':fit,'motion':motion,'w':.8,'h':1,'audio_enabled':False},
    ]
    baseline = _image_render(value, media, root, tmp_path, 'underneath')
    apply_manual_edit(value,change(slot=VIDEO,background_mode='transparent'))
    output = _image_render(value,media,root,tmp_path,'keyed-layer')
    for at in (.1,.5,1.5,1.9):
        background = _pixel(ffmpeg,output,at)
        assert background[2]>200 and max(background[:2])<30, background
    foreground = _pixel(ffmpeg,output,.5,128,90)
    assert foreground[0]>200 and max(foreground[1:])<30, foreground
    before,after = _samples(ffmpeg,baseline),_samples(ffmpeg,output)
    assert len(before)==len(after)
    assert max(abs(a-b) for a,b in zip(before,after))<1e-6


def test_mode_is_optional_for_old_projects_and_layer_choice_is_undoable():
    old = dict(KEY)
    assert normalize_chroma_key(old)['background_mode']=='replace'
    value=with_videos()
    apply_manual_edit(value,change(slot=VIDEO,background_mode='transparent'))
    saved=copy.deepcopy(value['manual']['chroma_key'])
    apply_manual_edit(value,{'action':'undo'})
    assert VIDEO not in value['manual'].get('chroma_key',{})
    apply_manual_edit(value,{'action':'redo'})
    assert value['manual']['chroma_key']==saved
    before=copy.deepcopy(value)
    with pytest.raises(ManualEditError,match='Media'):
        apply_manual_edit(value,change(slot='A',background_mode='transparent'))
    assert value==before


def test_layer_frame_retains_alpha_and_old_api_clients_can_omit_mode(api, chroma_media):
    _,client,store,pid,_=api
    ffmpeg,_,sources=chroma_media
    path=store.project_dir(pid)/asset()['path']
    path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(sources[1],path)
    store.update(pid,lambda p:p['assets'].update({VIDEO:asset()}))
    assert apply(client,store,pid,slot=VIDEO,background_mode='transparent').status_code==200
    response=frame(client,store,pid,slot=VIDEO)
    assert response.status_code==200
    png=path.parent/'key.png';png.write_bytes(response.data)
    pixels=subprocess.check_output([ffmpeg,'-v','error','-i',str(png),'-frames:v','1','-pix_fmt','rgba','-f','rawvideo','pipe:1'])
    assert pixels[(16*320+16)*4+3]==0
    assert pixels[(90*320+160)*4+3]>250
    payload={'action':'set_chroma_key','slot':VIDEO,**{k:v for k,v in CHROMA_KEY_DEFAULTS.items() if k!='background_mode'},'enabled':True,'expected_revision':store.load(pid)['revision']}
    result=client.post(f'/api/projects/{pid}/manual/edit',json=payload)
    assert result.status_code==200
    assert store.load(pid)['manual']['chroma_key'][VIDEO]['background_mode']=='replace'
