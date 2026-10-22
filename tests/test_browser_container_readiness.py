"""Browser readiness needs real container headers, not a misleading suffix."""
import hashlib,json,shutil,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from cutroom import media

MP4='mov,mp4,m4a,3gp,3g2,mj2'
WEBM='matroska,webm'

@pytest.mark.parametrize('suffix,container,ready',[
    ('.mp4',MP4,True),('.MP4',MP4,True),('.mov',MP4,True),('.m4v',MP4,True),
    ('.webm',WEBM,True),('.mkv',WEBM,False),('.part',MP4,False),
    ('.mp4',WEBM,False),('.mp4','avi',False),('.webm',MP4,False),('.mov','avi',False),('.mp4','unknown',False)])
def test_actual_container_and_physical_suffix_must_agree(tmp_path,monkeypatch,suffix,container,ready):
    path=tmp_path/('recording'+suffix);path.write_bytes(b'unchanged test source')
    payload={'streams':[{'codec_type':'video','codec_name':'h264','width':96,'height':64,'avg_frame_rate':'10/1'},
        {'codec_type':'audio','codec_name':'aac'}],'format':{'format_name':container,'duration':'1'}}
    if suffix=='.webm' and container==WEBM:
        payload['streams'][0]['codec_name']='vp9';payload['streams'][1]['codec_name']='opus'
    def probe(command,**kw):
        assert command[-1]==str(path) and kw['timeout']==45
        return SimpleNamespace(stdout=json.dumps(payload))
    monkeypatch.setattr(media,'run_command',probe)
    result=media.probe_media(path,SimpleNamespace(ffprobe='mock'))
    assert result['browser_ready'] is ready and result['format']==container
    assert path.read_bytes()==b'unchanged test source'

@pytest.mark.parametrize('video,audio',[('hevc','aac'),('mpeg4','aac'),('h264','ac3'),('h264','pcm_s16le')])
def test_matching_container_does_not_bypass_codec_checks(tmp_path,monkeypatch,video,audio):
    path=tmp_path/'recording.mp4';path.write_bytes(b'unchanged')
    payload={'streams':[{'codec_type':'video','codec_name':video,'width':96,'height':64},
        {'codec_type':'audio','codec_name':audio}],'format':{'format_name':MP4,'duration':'1'}}
    monkeypatch.setattr(media,'run_command',lambda *a,**k:SimpleNamespace(stdout=json.dumps(payload)))
    assert media.probe_media(path,SimpleNamespace(ffprobe='mock'))['browser_ready'] is False

def test_real_mislabeled_matroska_uses_existing_proxy_path_and_preserves_original(tmp_path):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('Existing FFmpeg/ffprobe runtime required')
    source=tmp_path/'misleading.mp4'
    subprocess.run([ffmpeg,'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','color=c=blue:s=96x64:r=10:d=0.6',
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=0.6','-c:v','libx264','-pix_fmt','yuv420p',
        '-threads','1','-c:a','aac','-f','matroska',str(source)],check=True,capture_output=True,timeout=20)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    settings=SimpleNamespace(ffmpeg=ffmpeg,ffprobe=ffprobe,raw={'ffmpeg_threads':1,'proxy_height':96})
    metadata=media.probe_media(source,settings)
    assert metadata['video_codec']=='h264' and metadata['audio_codec']=='aac'
    assert metadata['format']==WEBM and metadata['browser_ready'] is False
    preview=media.create_proxy(source,tmp_path/'preview.mp4',settings)
    assert media.probe_media(preview,settings)['browser_ready'] is True
    subprocess.run([ffmpeg,'-hide_banner','-nostdin','-v','error','-xerror','-i',str(preview),
        '-map','0:v:0','-map','0:a:0','-f','null','-'],check=True,capture_output=True,timeout=20)
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
