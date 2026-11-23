"""Actual frontend drag plans/payloads -> saved native edit -> distinctive encode."""
import hashlib
import json
import shutil
import subprocess
import threading
from pathlib import Path

import pytest
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom import render
from test_empty_manual_workflow import app, chunked_import
from test_media_render import pixel, samples, tone_level

ROOT = Path(__file__).resolve().parents[1]


def frontend_drag(project, asset_id, at, track_id, *, mode='add', marked=True):
    # Execute current production resolver, drag planner and MediaStudio.place,
    # not a parallel Python implementation of the new payload arithmetic.
    code = r"""
const fs=require('fs'),vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8')),p=input.project;
const entries=new Map(),storage={getItem:k=>entries.get(k)??null,setItem:(k,v)=>entries.set(k,v)};
const read=f=>fs.readFileSync('web/'+f,'utf8').replace(/^import .*\r?\n/gm,'').replace(/^export /gm,'');
const media=vm.createContext({localStorage:storage,setTimeout:()=>1,clearTimeout(){}});
vm.runInContext(read('media-studio.js')+'\nglobalThis.api={MediaStudio,saveLibraryShotMarks};',media);
const audio=vm.createContext({});vm.runInContext(read('audio-source.js')+'\nglobalThis.api={audioSourceRange,readAudioSourceMarks,saveAudioSourceMarks};',audio);
const tracks=vm.createContext({});vm.runInContext(read('layer-tracks.js')+'\nglobalThis.plan=planLibraryTrackPlacement;',tracks);
const drag=vm.createContext({});vm.runInContext(read('timeline.js')+'\n'+read('timeline-media-drop.js')+'\nglobalThis.plan=libraryDropPlacement;',drag);
const editor={...p,manual:{...p.manual,sequence:p.editor_sequence}},studio=Object.create(media.api.MediaStudio.prototype),asset=p.assets[input.asset_id];
if(input.marked){if(asset.kind==='video')media.api.saveLibraryShotMarks(p,input.asset_id,{source_start:3,source_end:5},storage);else audio.api.saveAudioSourceMarks(p,input.asset_id,{source_start:3,source_end:5},storage);}
let request=null;
Object.assign(studio,{status:{textContent:''},flush:async()=>true,updateImportAvailability(){},syncSourceMonitor(){},render(){},options:{
 project:()=>p,busy:()=>false,pause(){},flushSettings:async()=>{},
 audioSource:{range:audio.api.audioSourceRange,readMarks:(p,id)=>audio.api.readAudioSourceMarks(p,id,storage)},
 placementPreview:(...args)=>tracks.plan(editor,...args),
 edit:async(action,payload,context)=>{if(context.isCurrent()!==true||context.strictRevision!==true)throw Error('Missing current drag guard');request={action,payload};return p;}
}});
const selected=studio.dragSelection(input.asset_id),plan=drag.plan(editor,input.asset_id,input.at,{...selected,trackId:input.track_id,insert:input.mode==='insert',placementPreview:(...a)=>studio.placementPreview(...a),insertionIssue:(...a)=>studio.insertionIssue(...a)});
(async()=>{if(!plan.error)await studio.place(input.asset_id,plan.start,{append:plan.append,...(plan.insert?{insert:true}:{}),trackId:plan.trackId,...selected},{isCurrent:()=>true});console.log(JSON.stringify({plan,request,issue:studio.status.textContent}));})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', code], cwd=ROOT, input=json.dumps({
        'project': project, 'asset_id': asset_id, 'at': at, 'track_id': track_id,
        'mode': mode, 'marked': marked}), text=True, capture_output=True, check=True, timeout=15)
    return json.loads(result.stdout)


def generate(ffmpeg, root, kind):
    base = root/'generated-base.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=black:s=160x90:r=30:d=8',
        '-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(base)],check=True,capture_output=True,timeout=20)
    asset = root/('distinctive-source.mp4' if kind=='video' else 'distinctive-source.wav')
    tone="aevalsrc='0.15*sin(2*PI*if(lt(t,3),330,if(lt(t,4),880,if(lt(t,5),1320,550)))*t)':s=48000:d=8"
    inputs=['-f','lavfi','-i',tone]
    if kind=='video':
        filters="drawbox=x=0:y=0:w=iw:h=ih:color=yellow:t=fill:enable='gte(t,3)*lt(t,4)',drawbox=x=0:y=0:w=iw:h=ih:color=cyan:t=fill:enable='gte(t,4)*lt(t,5)',drawbox=x=0:y=0:w=iw:h=ih:color=red:t=fill:enable='gte(t,5)'"
        inputs=['-f','lavfi','-i','color=blue:s=160x90:r=30:d=8',*inputs,'-vf',filters,'-c:v','libx264','-preset','ultrafast','-crf','18','-pix_fmt','yuv420p','-c:a','aac']
    else: inputs += ['-c:a','pcm_s16le']
    subprocess.run([ffmpeg,'-v','error',*inputs,str(asset)],check=True,capture_output=True,timeout=20)
    return base,asset


@pytest.mark.parametrize('kind,mode', [('video','add'),('video','insert'),('video','append'),('audio','add')])
def test_marked_drag_native_history_reopen_and_distinctive_output(app,tmp_path,monkeypatch,kind,mode):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe or not shutil.which('node'):
        pytest.skip('Existing FFmpeg and Node required for encoded drag acceptance')
    base,asset=generate(ffmpeg,tmp_path,kind)
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in (base,asset)}
    # Prove the synthetic source really has different content outside each mark.
    source_sound=samples(ffmpeg,asset)
    assert tone_level(source_sound,.5,330)>.03 and tone_level(source_sound,5.5,550)>.03
    if kind=='video':
        assert pixel(ffmpeg,asset,.5)[2]>200 and pixel(ffmpeg,asset,5.5)[0]>200
    client=app.test_client();store=app.extensions['cutroom_store'];jobs=app.extensions['cutroom_jobs'];kinds=[];submit=jobs.submit
    def track_job(kind,*args,**kwargs):kinds.append(kind);return submit(kind,*args,**kwargs)
    monkeypatch.setattr(jobs,'submit',track_job)
    r=client.post('/api/projects',json={'name':'Synthetic marked drag','initial_settings':{
        'workflow':'manual','goal':'youtube','aspect':'source','resolution':'720','fps':30,
        'captions':False,'burn_captions':False,'editorial_effects':False}})
    assert r.status_code==201;r=r.get_json()['project'];pid=r['id']
    def current():return client.get(f'/api/projects/{pid}').get_json()['project']
    def edit(action,**payload):
        r=client.post(f'/api/projects/{pid}/manual/edit',json={'action':action,'expected_revision':current()['revision'],**payload})
        assert r.status_code==200,r.get_json();return r.get_json()['project']
    chunked_import(client,pid,base,purpose='source',slot='A')
    imported=chunked_import(client,pid,asset,purpose='asset');aid=imported['asset_id']
    edit('layer_tracks_enable')
    lane=edit('layer_track_add',kind='visual' if kind=='video' else 'audio',name='Chosen source range')['manual']['layer_tracks']['tracks'][-1]['id']
    before=current();at=8 if mode=='append' else 2
    whole=frontend_drag(before,aid,at,lane,mode=mode,marked=False)
    assert not whole['plan'].get('error'),whole
    assert whole['plan']['end']==(at+8 if mode in ('insert','append') else 8)
    assert 'source_start' not in whole['request']['payload'] and 'source_end' not in whole['request']['payload']
    decision=frontend_drag(before,aid,at,lane,mode=mode)
    assert not decision['plan'].get('error'),decision
    assert decision['plan']['start']==at and decision['plan']['end']==at+2
    assert decision['request']['action']=='media_'+mode,decision
    saved=edit(decision['request']['action'],**decision['request']['payload'])
    clip=saved['manual']['media_clips'][-1]
    assert clip['start']==at and clip['end']==at+2 and clip['source_start']==3
    assert clip['track_id']==lane and clip['audio_enabled'] is True and clip['speed']==1
    if kind=='video':assert clip['video_source_start']==3
    assert saved['manual']['history']['undo_count']==before['manual']['history']['undo_count']+1
    assert edit('undo')['manual'].get('media_clips',[])==before['manual'].get('media_clips',[])
    assert edit('redo')['manual']['media_clips']==saved['manual']['media_clips']
    reopened=ProjectStore(store.settings).load(pid)
    assert reopened['manual']['media_clips']==saved['manual']['media_clips']
    assert 'generate' not in kinds and not any('transcrib' in x or 'analysis' in x for x in kinds)
    output=render.render_project(JobContext(Job('marked-drag-proof','render',pid),threading.Lock()),pid,store,store.settings,{'quality':'fast','_force_software':True})['export']
    video=store.settings.exports_dir/output['name']
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(video)]))
    v=next(s for s in probe['streams'] if s['codec_type']=='video');duration=10 if mode in ('insert','append') else 8
    assert [v['width'],v['height']]==[160,90] and v['avg_frame_rate']=='30/1' and int(v['nb_frames'])==duration*30
    if kind=='video':
        # First and last selected frames are yellow/cyan, never outer blue/red.
        for time in [at,at+.25,at+1-1/30]:
            r,g,b=pixel(ffmpeg,video,time);assert r>200 and g>200 and b<50,(time,(r,g,b))
        for time in [at+1,at+1.25,at+2-1/30]:
            r,g,b=pixel(ffmpeg,video,time);assert r<50 and g>200 and b>200,(time,(r,g,b))
    audio=samples(ffmpeg,video)
    for time,freq in [(at+.25,880),(at+1.25,1320)]:
        assert tone_level(audio,time,freq)>.03
        assert tone_level(audio,time,330)<.003 and tone_level(audio,time,550)<.003
    for time in [at-.25,*([at+2] if at+2<duration else [])]:
        assert max(pixel(ffmpeg,video,time))<20
        assert tone_level(audio,time,880)<.003 and tone_level(audio,time,1320)<.003
    assert {p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}==hashes
    stored=store.load(pid);folder=store.project_dir(pid)
    assert hashlib.sha256((folder/stored['sources']['A']['relative_path']).read_bytes()).hexdigest()==hashes[base]
    assert hashlib.sha256((folder/stored['assets'][aid]['path']).read_bytes()).hexdigest()==hashes[asset]
