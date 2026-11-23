"""Current UI output facts compared with real, isolated manual-editor exports."""
import hashlib
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from cutroom.jobs import Job, JobContext
from cutroom import render
from test_empty_manual_workflow import app, chunked_import


def ui_output(project):
    code = r"""
const fs=require('fs'),vm=require('vm'),src=fs.readFileSync('web/app.js','utf8');
const project=JSON.parse(fs.readFileSync(0,'utf8'));
function fn(name){const start=src.indexOf('function '+name+'(');if(start<0)throw Error(name);const next=src.indexOf('\nfunction ',start+10);return src.slice(start,next<0?src.length:next);}
const c=vm.createContext({state:{project},elements:{aspectSelect:{value:project.settings.aspect},resolutionSelect:{value:project.settings.resolution}},selectedFrameRate:()=>project.settings.fps,formatTime:String});
vm.runInContext(['editorProject','previewExportDimensions','outputReviewSnapshot'].map(fn).join('\n'),c);
console.log(JSON.stringify(vm.runInContext('outputReviewSnapshot()',c)));
"""
    result = subprocess.run(['node', '-e', code], input=json.dumps(project), text=True,
                            capture_output=True, check=True, cwd=Path(__file__).resolve().parents[1])
    return json.loads(result.stdout)


@pytest.mark.parametrize('aspect,size,dimensions,fps', [
    ('source', '96x128', [96,128], 30),
    ('source', '160x120', [160,120], 60),
    ('4:5', '96x128', [720,900], 30),
])
def test_real_import_edit_history_reopen_output_review_and_encode(app, tmp_path, monkeypatch, aspect, size, dimensions, fps):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe or not shutil.which('node'):
        pytest.skip('Existing FFmpeg and Node are required for this integration proof')
    media=tmp_path/'generated-colour-and-tone.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i',f'testsrc2=s={size}:r=30:d=2',
        '-f','lavfi','-i','sine=frequency=440:duration=2','-c:v','libx264','-preset','ultrafast',
        '-pix_fmt','yuv420p','-c:a','aac','-shortest',str(media)],check=True,capture_output=True,timeout=20)
    digest=hashlib.sha256(media.read_bytes()).hexdigest()
    client=app.test_client();jobs=app.extensions['cutroom_jobs'];kinds=[];submit=jobs.submit
    def tracked(kind,*args,**kwargs):
        kinds.append(kind);return submit(kind,*args,**kwargs)
    monkeypatch.setattr(jobs,'submit',tracked)
    created=client.post('/api/projects',json={'name':'Synthetic editor-flow proof','initial_settings':{
        'workflow':'manual','goal':'youtube','aspect':aspect,'resolution':'720','fps':fps,
        'captions':False,'burn_captions':False,'editorial_effects':False}})
    assert created.status_code==201
    pid=created.get_json()['project']['id']
    chunked_import(client,pid,media,purpose='source',slot='A')
    def current(): return client.get(f'/api/projects/{pid}').get_json()['project']
    before=current()
    def edit(action,**payload):
        r=client.post(f'/api/projects/{pid}/manual/edit',json={
            'action':action,'expected_revision':current()['revision'],**payload})
        assert r.status_code==200,r.get_json()
        return r.get_json()['project']
    after=edit('sequence_ripple_delete',start=.5,end=1.)
    assert after['editor_sequence']['duration']==pytest.approx(1.5)
    assert edit('undo')['editor_sequence']['duration']==pytest.approx(2.)
    redone=edit('redo')
    assert redone['editor_sequence']==after['editor_sequence']
    reopened=current();snapshot=ui_output(reopened)
    assert snapshot['dimensions']==dimensions==list(render._dimensions(reopened))
    assert snapshot['duration']==pytest.approx(1.5)
    assert snapshot['fps']==fps
    assert kinds==['prepare_source'], 'Manual import and editing must not request AI'
    store=app.extensions['cutroom_store']
    output=render.render_project(JobContext(Job('flow-proof','render',pid),threading.Lock()),pid,
        store,store.settings,{'quality':'fast','_force_software':True})['export']
    video=store.settings.exports_dir/output['name']
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(video)]))
    v=next(row for row in probe['streams'] if row['codec_type']=='video')
    assert [v['width'],v['height']]==snapshot['dimensions']
    assert v['avg_frame_rate']==f'{fps}/1'
    assert int(v['nb_frames'])==round(snapshot['duration']*fps)
    assert float(v['duration'])==pytest.approx(snapshot['duration'],abs=1/fps)
    assert any(row['codec_type']=='audio' for row in probe['streams'])
    assert hashlib.sha256(media.read_bytes()).hexdigest()==digest
    saved=store.load(pid)
    assert hashlib.sha256((store.project_dir(pid)/saved['sources']['A']['relative_path']).read_bytes()).hexdigest()==digest
