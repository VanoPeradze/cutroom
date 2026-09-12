from __future__ import annotations
import json, math, shutil, subprocess, sys, tempfile, threading, wave
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
from cutroom.config import load_settings
from cutroom.jobs import Job, JobContext
from cutroom.media import probe_media
from cutroom.projects import ProjectStore
from cutroom.render import render_project
import cutroom.director as director

def make_wav(path: Path, rate=8000):
    seconds=24
    audio=np.zeros(seconds*rate,dtype=np.float32)
    for start,end in [(0,5),(8,13),(16,24)]:
        t=np.arange((end-start)*rate,dtype=np.float32)/rate
        audio[start*rate:end*rate]=.28*np.sin(2*math.pi*330*t)
    pcm=(audio*32767).astype('<i2')
    with wave.open(str(path),'wb') as h:
        h.setnchannels(1); h.setsampwidth(2); h.setframerate(rate); h.writeframes(pcm.tobytes())

def run(cmd): subprocess.run(cmd,check=True,capture_output=True,text=True)

def main():
    work=Path(tempfile.mkdtemp(prefix='cutroom-youtube-'))
    try:
        ffmpeg=shutil.which('ffmpeg') or 'ffmpeg'; wav=work/'a.wav'; make_wav(wav); src=work/'source.mp4'
        run([ffmpeg,'-hide_banner','-loglevel','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24:duration=24','-i',str(wav),'-c:v','libx264','-preset','ultrafast','-crf','30','-c:a','aac','-shortest',str(src)])
        cfg=json.loads((ROOT/'config.json').read_text()); cfg['data_dir']=str(work/'data'); cfg['render']['prefer_hardware']=False
        cp=work/'config.json'; cp.write_text(json.dumps(cfg)); settings=load_settings(cp); store=ProjectStore(settings); project=store.create('YouTube cleanup')
        media=store.project_dir(project['id'])/'media'/'source-A.mp4'; shutil.copy2(src,media)
        project['sources']['A']={'slot':'A','name':'source.mp4','relative_path':'media/source-A.mp4',**probe_media(media,settings)}
        project['settings'].update({'goal':'youtube','aspect':'16:9','layout':'auto','resolution':'720','quality':'fast','instruction':'','captions':False})
        store.save(project)
        old=director.transcribe
        director.transcribe=lambda *a,**k: (_ for _ in ()).throw(AssertionError('YouTube default must not invoke Whisper'))
        try: director.analyze_project(JobContext(Job('d','director',project['id']),threading.Lock()),project['id'],store,settings)
        finally: director.transcribe=old
        completed=store.load(project['id']); draft=completed['draft']
        assert draft['engine']=='audio_cleanup', draft['engine']
        assert all(item['camera']=='A' for item in draft['camera_plan'])
        assert draft['output_duration'] < 22.0, draft['output_duration']
        assert draft['output_duration'] > 15.0, draft['output_duration']
        rendered=render_project(JobContext(Job('r','render',project['id']),threading.Lock()),project['id'],store,settings,{'quality':'fast'})
        meta=probe_media(settings.exports_dir/rendered['export']['name'],settings)
        assert (meta['width'],meta['height'])==(1280,720),meta
        print(json.dumps({'ok':True,'source':24,'draft':draft['output_duration'],'render':meta['duration'],'engine':draft['engine'],'camera':sorted({x['camera'] for x in draft['camera_plan']})},indent=2))
    finally: shutil.rmtree(work,ignore_errors=True)
if __name__=='__main__': main()
