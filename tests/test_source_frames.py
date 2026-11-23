"""Original decoded PTS/frame pixels, VFR/CFR marks, and real exported bounds."""
import base64
from bisect import bisect_right
import hashlib
import json
import shutil
import subprocess
import threading
import sys
import re
from types import SimpleNamespace

import pytest
from cutroom.source_frames import frame_index, SourceFrameError
from cutroom.jobs import Job, JobContext
from cutroom.projects import ProjectStore
from cutroom import render
from test_empty_manual_workflow import app, chunked_import


def index_data(points=(1000,1040,1160,1200), end=300):
    return {'streams':[{'codec_type':'video','time_base':'1/1000','start_pts':1000,'duration_ts':end,'width':160,'height':90}],
            'format':{'start_time':'1.000000'},'frames':[{'best_effort_timestamp':n,'pkt_dts':-999,'avg_frame_rate':'30/1'} for n in points]}


def test_decoded_pts_not_dts_or_nominal_rate_and_video_end_not_audio_tail():
    points,end=frame_index(index_data(),1.5)
    assert points==(0.,.04,.16,.2) and end==.3
    data=index_data();del data['streams'][0]['duration_ts']
    assert frame_index(data,1.5)[1] is None,'Unknown last picture duration is never guessed from FPS or container tail'


@pytest.mark.parametrize('mutate',[
    lambda d:d['frames'].clear(),lambda d:d['frames'][1].update(best_effort_timestamp=1000),
    lambda d:d['frames'][1].pop('best_effort_timestamp'),lambda d:d['frames'][0].update(best_effort_timestamp=999),
    lambda d:d['streams'][0].update(time_base='0/0'),lambda d:d['format'].pop('start_time'),
    lambda d:d['streams'][0].update(disposition={'attached_pic':1}),lambda d:d['streams'][0].update(width=1000000),
])
def test_ambiguous_or_incomplete_index_is_refused_not_sorted_or_interpolated(mutate):
    data=index_data();mutate(data)
    with pytest.raises(SourceFrameError):frame_index(data,1.5)


def generate(ffmpeg,root,vfr,offset=0,bframes=0,malformed_end=False):
    base=root/'base.mp4';source=root/'numbered-colour-original.mp4'
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=black:s=160x90:r=24:d=1',
        '-c:v','libx264','-preset','ultrafast',str(base)],check=True,capture_output=True,timeout=20)
    colours=['red','lime','blue','yellow','cyan','magenta']
    filters=','.join(f"drawbox=x=0:y=0:w=iw:h=ih:color={c}:t=fill:enable='eq(n,{i})'" for i,c in enumerate(colours))
    if vfr and not malformed_end:filters="select='eq(n,0)+eq(n,1)+eq(n,5)+eq(n,8)+eq(n,13)+eq(n,17)',"+filters
    if vfr and malformed_end:filters+=",setpts='if(eq(N,0),0,if(eq(N,1),1,if(eq(N,2),5,if(eq(N,3),8,if(eq(N,4),13,17)))))'"
    subprocess.run([ffmpeg,'-v','error','-f','lavfi','-i','color=black:s=160x90:r=30:d='+('0.6' if vfr and not malformed_end else '0.2'),
        '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1.2','-vf',filters,
        '-fps_mode','vfr','-c:v','libx264','-preset','medium','-bf',str(bframes),'-crf','12','-pix_fmt','yuv420p','-c:a','aac',
        '-output_ts_offset',str(offset),str(source)],check=True,capture_output=True,timeout=20)
    return base,source


def png_pixel(ffmpeg,response):
    data=base64.b64decode(response['image'].split(',',1)[1])
    raw=subprocess.check_output([ffmpeg,'-v','error','-i','pipe:0','-frames:v','1','-pix_fmt','rgb24','-f','rawvideo','pipe:1'],input=data)
    return tuple(raw[(45*160+80)*3:(45*160+80)*3+3])


@pytest.mark.parametrize('vfr,offset',[(False,0),(True,0),(True,5)])
def test_actual_original_frames_mark_history_reopen_and_export_exclude_next_picture(app,tmp_path,vfr,offset):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('Existing FFmpeg required')
    base,source=generate(ffmpeg,tmp_path,vfr,offset=offset);original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_streams','-show_format','-of','json',str(source)]))
    real,video_end=frame_index(probe,float(probe['format']['duration']))
    assert len(real)==6
    assert len({round(b-a,6) for a,b in zip(real,real[1:])})>1 if vfr else len({round(b-a,6) for a,b in zip(real,real[1:])})==1
    assert real[-1]<.7,'This fixture has a genuine longer audio tail'
    assert real[-1]<video_end<1.2
    if offset:assert float(probe['format']['start_time'])>0
    client=app.test_client();store=app.extensions['cutroom_store']
    made=client.post('/api/projects',json={'name':'Synthetic exact frame proof','initial_settings':{'workflow':'manual','goal':'youtube','aspect':'source','resolution':'720','fps':24,'captions':False,'burn_captions':False,'editorial_effects':False}})
    assert made.status_code==201;pid=made.get_json()['project']['id']
    chunked_import(client,pid,base,purpose='source',slot='A');aid=chunked_import(client,pid,source,purpose='asset')['asset_id']
    def current():return client.get(f'/api/projects/{pid}').get_json()['project']
    before=current();bytes_before=store.state_path(pid).read_bytes()
    endpoint=f'/api/projects/{pid}/assets/{aid}/frame-step'
    def step(at,direction='next',previous=None):
        q={'time':at,'direction':direction}
        if previous:q.update(index=previous['index'],token=previous['token'])
        response=client.get(endpoint,query_string=q);assert response.status_code==200,response.get_json();return response.get_json()
    green=step(real[0]);assert green['index']==1 and green['time']==real[1] and green['end']==real[2]
    assert png_pixel(ffmpeg,green)[1]>200 and png_pixel(ffmpeg,green)[0]<30
    blue=step(green['time'],previous=green);assert blue['index']==2 and png_pixel(ffmpeg,blue)[2]>200
    yellow=step(blue['time'],previous=blue);assert yellow['index']==3 and yellow['end']==real[4]
    assert min(png_pixel(ffmpeg,yellow)[:2])>200 and png_pixel(ffmpeg,yellow)[2]<30
    backward=step(yellow['time'],'previous',yellow);assert backward['index']==2 and backward['time']==blue['time']
    last=step(real[-1]);assert last['index']==5 and last['end']==video_end
    assert store.state_path(pid).read_bytes()==bytes_before,'Frame navigation must not save or advance the project'
    stale=client.get(endpoint,query_string={'time':green['time'],'direction':'next','index':1,'token':'0'*64});assert stale.status_code==409
    assert client.get(endpoint+'?time=0&time=1&direction=next').status_code==400
    assert client.get(endpoint,query_string={'time':'NaN','direction':'next'}).status_code==400
    def edit(action,**payload):
        r=client.post(f'/api/projects/{pid}/manual/edit',json={'action':action,'expected_revision':current()['revision'],**payload});assert r.status_code==200,r.get_json();return r.get_json()['project']
    saved=edit('media_append',asset_id=aid,source_start=green['time'],source_end=yellow['end'])
    clip=saved['manual']['media_clips'][-1]
    assert clip['source_start']==green['time'] and clip['video_source_start']==green['time']
    assert clip['end']-clip['start']==pytest.approx(yellow['end']-green['time'],abs=1e-9)
    assert edit('undo')['manual'].get('media_clips',[])==before['manual'].get('media_clips',[])
    assert edit('redo')['manual']['media_clips']==saved['manual']['media_clips']
    assert ProjectStore(store.settings).load(pid)['manual']['media_clips']==saved['manual']['media_clips']
    exported=render.render_project(JobContext(Job('source-frame-proof','render',pid),threading.Lock()),pid,store,store.settings,{'quality':'fast','_force_software':True})['export']
    output=store.settings.exports_dir/exported['name']
    data=json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-of','json',str(output)]));stream=next(x for x in data['streams'] if x['codec_type']=='video')
    count=10 if vfr else 2 # Existing project renderer rounds total output frames to nearest, not ceiling.
    assert int(stream['nb_frames'])==24+count and stream['avg_frame_rate']=='24/1'
    # Decode every output frame in order, never approximate output seek samples.
    raw=subprocess.check_output([ffmpeg,'-v','error','-i',str(output),'-an','-vf','scale=1:1','-fps_mode','passthrough','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    assert len(raw)==(24+count)*3
    observed=[]
    for frame in range(count):
        rgb=tuple(raw[(24+frame)*3:(25+frame)*3]);r,g,b=rgb
        actual='green' if g>180 and r<40 and b<40 else 'blue' if b>180 and r<40 and g<40 else 'yellow' if min(r,g)>180 and b<40 else 'outside'
        source_index=bisect_right(real,green['time']+frame/24+1e-9)-1
        expected={1:'green',2:'blue',3:'yellow'}[source_index]
        assert actual==expected,(frame,rgb,expected,'Every encoded picture must agree with the selected original interval')
        observed.append(actual)
    assert observed==(['green']*4+['blue']*2+['yellow']*4 if vfr else ['green','blue'])
    # The 30 FPS source has only two output samples at 24 FPS; no invented third frame.
    assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
    stored=store.load(pid);assert hashlib.sha256((store.project_dir(pid)/stored['assets'][aid]['path']).read_bytes()).hexdigest()==original_hash


def test_nonzero_container_origin_uses_original_presentation_clock(tmp_path):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('Existing FFmpeg required')
    _,source=generate(ffmpeg,tmp_path,True,offset=5)
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_streams','-show_format','-of','json',str(source)]))
    assert float(probe['format']['start_time'])>0
    points,end=frame_index(probe,2)
    origin=float(probe['format']['start_time']);tb=probe['streams'][0]['time_base']
    from fractions import Fraction
    # Independent FFmpeg demux/filter output, not another copy of our formula.
    shown=subprocess.run([ffmpeg,'-hide_banner','-i',str(source),'-an','-vf','showinfo','-f','null','-'],capture_output=True,text=True,encoding='utf8',check=True).stderr
    decoded=[int(n) for n in re.findall(r'\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:',shown)]
    assert points==tuple(round(float(n*Fraction(tb)),9) for n in decoded)
    assert points[1]!=round(float(probe['frames'][1]['best_effort_timestamp']*Fraction(tb))-origin,9),'Decimal subtraction is not the FFmpeg stream-tick clock'
    assert points[-1]<end<1.2


@pytest.mark.parametrize('pipe',['stdout','stderr'])
def test_stream_output_cap_kills_and_reaps_without_buffering_excess(monkeypatch,pipe):
    import cutroom.source_frames as frames
    actual=frames.subprocess.Popen;children=[]
    def launch(*args,**kwargs):
        p=actual(*args,**kwargs);children.append(p);return p
    monkeypatch.setattr(frames.subprocess,'Popen',launch)
    monkeypatch.setattr(frames,'MAX_ERROR_BYTES',1024)
    code=f"import sys,time;sys.{pipe}.buffer.write(b'x'*2000000);sys.{pipe}.flush();time.sleep(20)"
    with pytest.raises(SourceFrameError,match='output limit'):
        frames.bounded_command([sys.executable,'-c',code],limit=1024,timeout=2)
    assert len(children)==1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed


@pytest.mark.parametrize('reason',['timeout','cancel','nonzero'])
def test_bounded_decoder_always_reaps_on_timeout_cancellation_and_failure(monkeypatch,reason):
    import cutroom.source_frames as frames
    actual=frames.subprocess.Popen;children=[];checks=0
    def launch(*args,**kwargs):
        p=actual(*args,**kwargs);children.append(p);return p
    def check():
        nonlocal checks
        checks+=1
        if reason=='cancel' and checks>1:raise SourceFrameError('Source replaced',409)
    monkeypatch.setattr(frames.subprocess,'Popen',launch)
    code='import sys,time;'+('sys.exit(7)' if reason=='nonzero' else 'time.sleep(20)')
    with pytest.raises(SourceFrameError):frames.bounded_command([sys.executable,'-c',code],limit=1024,timeout=.1,cancel_check=check)
    assert len(children)==1 and children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stderr.closed


def fake_review(tmp_path):
    from cutroom.source_frames import SourceFrameReview
    aid='asset_'+'a'*32;file=tmp_path/'media'/'assets'/aid/'original.mp4';file.parent.mkdir(parents=True);file.write_bytes(b'owned fixture')
    asset={'id':aid,'kind':'video','status':'ready','path':str(file.relative_to(tmp_path)).replace('\\','/'),
           'duration':1.5,'width':160,'height':90,'preview_path':'separate-proxy.mp4'}
    project={'id':'p','assets':{aid:asset}}
    store=SimpleNamespace(load=lambda pid:project if pid=='p' else {'assets':{}},project_dir=lambda pid:tmp_path)
    review=SourceFrameReview(store,SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe'))
    return review,asset,file,aid


@pytest.mark.parametrize('change',[
    {'duration':601},{'duration':float('inf')},{'duration':True},{'duration':0},
    {'width':1000000},{'width':True},{'height':0},{'width':None},{'kind':'audio'},{'status':'missing'},
    {'path':'../../foreign.mp4'}, {'id':'asset_'+'b'*32}
])
def test_asset_bounds_and_original_ownership_are_checked_before_any_decoder(tmp_path,monkeypatch,change):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path);asset.update(change)
    def forbidden(*args,**kwargs):raise AssertionError('No decoder may run for inadmissible source')
    monkeypatch.setattr(frames,'bounded_command',forbidden)
    with pytest.raises(SourceFrameError):review.step('p',aid,{'time':'0','direction':'next'})
    assert not review.indices and not review.images


def test_large_original_and_busy_gate_refuse_before_any_decoder(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path);monkeypatch.setattr(frames,'MAX_FILE_BYTES',2)
    with pytest.raises(SourceFrameError,match='size'):review.step('p',aid,{'time':'0','direction':'next'})
    review.gate.acquire()
    try:
        with pytest.raises(SourceFrameError,match='Another') as error:review.step('p',aid,{'time':'0','direction':'next'})
        assert error.value.status==409
    finally:review.gate.release()


def test_complete_index_and_png_are_cached_but_original_change_revokes_confirmed_token(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path);calls=[]
    def decode(args,**kwargs):
        calls.append(args);kwargs['cancel_check']()
        return json.dumps(index_data()).encode() if args[0]=='ffprobe' else b'\x89PNG\r\n\x1a\nfixture'
    monkeypatch.setattr(frames,'bounded_command',decode)
    first=review.step('p',aid,{'time':'0','direction':'next'});assert first['time']==.04 and len(calls)==2
    again=review.step('p',aid,{'time':'.04','direction':'next','index':'1','token':first['token']});assert again['index']==2 and len(calls)==3
    back=review.step('p',aid,{'time':'.16','direction':'previous','index':'2','token':first['token']});assert back['index']==1 and len(calls)==3
    file.write_bytes(b'replaced original with different byte length')
    with pytest.raises(SourceFrameError,match='changed') as error:review.step('p',aid,{'time':'.04','direction':'next','index':'1','token':first['token']})
    assert error.value.status==409 and len(calls)==3
    changed=review.step('p',aid,{'time':'0','direction':'next'});assert changed['token']!=first['token'] and len(calls)==5
    assert all(str(frames.native_io_path(file)) in args for args in calls)
    assert all('separate-proxy.mp4' not in str(args) for args in calls)


def test_source_change_during_probe_or_image_cannot_cache_stale_content(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    for stage in ['ffprobe','ffmpeg']:
        child=tmp_path/stage;child.mkdir();review,asset,file,aid=fake_review(child)
        def decode(args,**kwargs):
            result=json.dumps(index_data()).encode() if args[0]=='ffprobe' else b'\x89PNG\r\n\x1a\nfixture'
            if args[0]==stage:file.write_bytes(b'changed')
            return result
        monkeypatch.setattr(frames,'bounded_command',decode)
        with pytest.raises(SourceFrameError,match='changed'):review.step('p',aid,{'time':'0','direction':'next'})
        assert not review.images
        if stage=='ffprobe':assert not review.indices
        assert not review.gate.locked()


def test_no_partial_index_or_guessed_last_frame_after_frame_cap_or_missing_pts(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path)
    monkeypatch.setattr(frames,'MAX_FRAMES',3)
    monkeypatch.setattr(frames,'bounded_command',lambda *a,**k:json.dumps(index_data()).encode())
    with pytest.raises(SourceFrameError):review.step('p',aid,{'time':'0','direction':'next'})
    assert not review.indices and not review.images
    monkeypatch.setattr(frames,'MAX_FRAMES',50000)
    data=index_data();data['frames'][2].pop('best_effort_timestamp')
    monkeypatch.setattr(frames,'bounded_command',lambda *a,**k:json.dumps(data).encode())
    with pytest.raises(SourceFrameError):review.step('p',aid,{'time':'0','direction':'next'})
    assert not review.indices and not review.images


def test_index_and_image_lru_limits_are_real(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path)
    monkeypatch.setattr(frames,'bounded_command',lambda args,**k:json.dumps(index_data()).encode() if args[0]=='ffprobe' else b'\x89PNG\r\n\x1a\nfixture')
    for n in range(12):
        file.write_bytes(b'original'+b'x'*n)
        review.step('p',aid,{'time':'0','direction':'next'})
    assert len(review.indices)==4 and len(review.images)==8


@pytest.mark.parametrize('query',[
    {'time':'-1','direction':'next'}, {'time':'nan','direction':'next'}, {'time':'Infinity','direction':'next'},
    {'time':'0','direction':'next','filename':'foreign'}, {'time':'0','direction':'next','index':'1'},
    {'time':'0','direction':'next','token':'0'*64}, {'time':'0','direction':'right'},
    {'time':'0','direction':'next','index':'1.0','token':'0'*64},
])
def test_invalid_step_request_is_rejected_before_loading_source(tmp_path,query):
    review,asset,file,aid=fake_review(tmp_path)
    with pytest.raises(SourceFrameError) as error:review.step('p',aid,query)
    assert error.value.status==400 and not review.indices



def test_inconsistent_b_frame_vfr_end_is_explicitly_unavailable_not_a_false_exact_edit(app,tmp_path):
    ffmpeg,ffprobe=shutil.which('ffmpeg'),shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:pytest.skip('Existing FFmpeg required')
    base,source=generate(ffmpeg,tmp_path,True,bframes=2,malformed_end=True)
    probe=json.loads(subprocess.check_output([ffprobe,'-v','error','-select_streams','v:0','-show_frames','-show_streams','-show_format','-of','json',str(source)]))
    from fractions import Fraction
    stream=probe['streams'][0];declared_end=(stream['start_pts']+stream['duration_ts'])*Fraction(stream['time_base'])
    last_pts=probe['frames'][-1]['best_effort_timestamp']*Fraction(stream['time_base'])
    assert declared_end<=last_pts,'The defensive fixture genuinely contradicts decoded presentation end'
    with pytest.raises(SourceFrameError):frame_index(probe,1.2)
    client=app.test_client();pid=client.post('/api/projects',json={'name':'Synthetic contradictory original'}).get_json()['project']['id']
    aid=chunked_import(client,pid,source,purpose='asset')['asset_id'];store=app.extensions['cutroom_store'];before=store.state_path(pid).read_bytes()
    result=client.get(f'/api/projects/{pid}/assets/{aid}/frame-step',query_string={'time':0,'direction':'next'})
    assert result.status_code==422 and 'ambiguous' in str(result.get_json())
    assert store.state_path(pid).read_bytes()==before



def test_timebase_that_cannot_preserve_whole_second_seek_offsets_is_not_guessed():
    data=index_data();data['streams'][0]['time_base']='1001/30000'
    with pytest.raises(SourceFrameError):frame_index(data,600)


def test_existing_render_picture_end_cannot_clamp_an_exact_shown_frame(tmp_path,monkeypatch):
    import cutroom.source_frames as frames
    review,asset,file,aid=fake_review(tmp_path);asset['picture_end']=.2
    monkeypatch.setattr(frames,'bounded_command',lambda *a,**k:json.dumps(index_data()).encode())
    with pytest.raises(SourceFrameError,match='render endpoint'):review.step('p',aid,{'time':'0','direction':'next'})
    assert not review.indices and not review.images
