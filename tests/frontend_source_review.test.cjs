const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const test=require('node:test');
const source=fs.readFileSync(require('node:path').join(__dirname,'../web/source-review.js'),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,'');
const plain=value=>JSON.parse(JSON.stringify(value));
const project=()=>({id:'p',settings:{fps:30},sources:{A:{duration:12,url:'a.mp4'},B:{duration:12,url:'b.mp4'}},analysis:{audio_source:'A',transcript:{segments:[{start:4,end:6,text:'A speech'}]}},
  manual:{history:{undo_count:0}},editor_sequence:{source_tracks:{A:[{start:0,end:4,source_start:0},{start:4,end:10,source_start:6}],B:[{start:0,end:4,source_start:0},{start:4,end:10,source_start:6}]}}});

function fixture() {
  const nodes={};
  for(const key of ['retry','canvas','scroll','close','slot','scope','restore','remove','undo','previous','next','fit','zoomIn','zoomOut','exact','video','status','quote','selection','summary','effect']) nodes[key]={
    dataset:{review:key},value:'',listeners:{},currentTime:0,paused:true,
    addEventListener(name,fn){this.listeners[name]=fn;},querySelector(){return {};},focus(){this.focused=true;},
    pause(){this.paused=true;},play(){this.paused=false;return Promise.resolve();},load(){},removeAttribute(name){delete this[name];},getAttribute(name){return this[name];}
  };
  const dialog={listeners:{},open:false,querySelectorAll(){return Object.values(nodes);},addEventListener(name,fn){this.listeners[name]=fn;},showModal(){this.open=true;},close(){this.open=false;this.listeners.close?.();}};
  const context=vm.createContext({document:{getElementById(){return dialog;}},formatTime:time=>String(time),TimelineView:class {
    constructor(canvas,scroll,seek,select){this.onSeek=seek;this.onSelect=select;this.zoom=1;}
    setProject(p){this.project=p;}setSelection(r){this.selection=r;}setPlayhead(time){this.playhead=time;}
    selectRange(start,end){this.onSelect({start,end});}fit(){this.zoom=1;}setZoom(z){this.zoom=z;}followPlayhead(){}cancelGesture(){}
  }});
  vm.runInContext(source+'\nglobalThis.SourceReview=SourceReview;globalThis.sourceReviewRanges=sourceReviewRanges;globalThis.reviewSelectionStats=reviewSelectionStats;',context);
  let current=project(),paused=0;
  const requests=[];
  const review=new context.SourceReview({getProject:()=>current,mediaUrl:s=>s.url,pause:()=>paused++,exactInsert:()=>{},applyEdit:async(action,detail)=>{requests.push({action,detail});return current;}});
  return {review,nodes,dialog,context,requests,get current(){return current;},set current(p){current=p;},get paused(){return paused;}};
}

test('placing original footage carries the actual source selection and scope into the editor',()=>{
  const f=fixture();let placement;
  f.review.exactInsert=value=>placement=plain(value);
  f.review.open('edit');f.review.slot='B';f.nodes.scope.value='source';f.review.select({start:2.25,end:5.75});
  f.nodes.exact.onclick();
  assert.equal(f.dialog.open,false);
  assert.equal(f.nodes.video.src,undefined);
  assert.deepEqual(placement,{projectId:'p',slot:'B',scope:'source',source_start:2.25,source_end:5.75});
  assert.equal(f.requests.length,0,'opening placement must not edit');
});

test('placement cannot leave a busy, locked or stale source review',()=>{
  for(const change of [f=>f.review.busy=true,f=>f.current.manual.track_locks={A:true},f=>f.current={...f.current,id:'other'}]) {
    const f=fixture();let calls=0;f.review.exactInsert=()=>calls++;
    f.review.open('edit');change(f);f.nodes.exact.onclick();
    assert.equal(calls,0);assert.equal(f.dialog.open,true);
  }
});

test('source protection permits review but disables changing protected scope',async()=>{
  const f=fixture();f.current.manual={track_locks:{A:true}};
  f.review.open('edit');f.review.select({start:0,end:5});
  assert.equal(f.nodes.restore.disabled,true);assert.equal(f.nodes.remove.disabled,true);
  assert.match(f.nodes.effect.textContent,/locked/);
  await f.review.edit('sequence_source_remove');assert.equal(f.requests.length,0);
  f.review.slot='B';f.nodes.scope.value='B';f.review.refresh(true);
  assert.equal(f.review.protectedSlots().length,0);
});

test('original timeline unions current clips, including copies and moved clips, not stale draft keeps',()=>{
  const f=fixture(),p=project();
  p.draft={keep_ranges:[{start:0,end:12}]};
  p.editor_sequence.source_tracks.A=[{start:0,end:2,source_start:4},{start:3,end:6,source_start:3},{start:8,end:10,source_start:9}];
  assert.deepEqual(plain(f.context.sourceReviewRanges(p,'A')),{keeps:[{start:3,end:6},{start:9,end:11}],removed:[{start:0,end:3},{start:6,end:9},{start:11,end:12}],duration:12});
  const stats=f.context.reviewSelectionStats(f.context.sourceReviewRanges(p,'A'),{start:4,end:10});
  assert.deepEqual(plain(stats),{kept:3,removed:3});
});

test('opening review pauses the edit and selects first missing range in a separate source player',()=>{
  const f=fixture(); f.review.open('edit');
  assert.equal(f.paused,1);assert.equal(f.nodes.video.src,'a.mp4');assert.equal(f.nodes.canvas.focused,true);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
  assert.equal(f.review.timeline.project.manual,undefined,'source browser must not use edit-clock timeline');
  assert.equal(f.nodes.restore.disabled,false);assert.equal(f.nodes.remove.disabled,true);
  f.nodes.video.listeners.loadedmetadata();assert.equal(f.nodes.video.currentTime,4);
  assert.equal(f.nodes.quote.textContent,'A speech');
});

test('restore sends a source-clock action and respects Together versus B-only',async()=>{
  const f=fixture();f.review.open('edit');await f.review.edit('sequence_source_restore');
  assert.deepEqual(plain(f.requests[0]),{action:'sequence_source_restore',detail:{slot:'A',scope:'edit',source_start:4,source_end:6}});
  f.review.open('B');await f.review.edit('sequence_source_remove');
  assert.deepEqual(plain(f.requests[1].detail),{slot:'B',scope:'B',source_start:4,source_end:6});
  assert.equal(f.nodes.video.src,'b.mp4');assert.notEqual(f.nodes.quote.textContent,'A speech');
});

test('selection and zoom survive updates and kept footage cannot be restored again',()=>{
  const f=fixture();f.review.open();f.review.timeline.zoom=3;f.nodes.video.currentTime=5;
  f.current.editor_sequence.source_tracks.A=[{start:0,end:12,source_start:0}];f.review.refresh();
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
  assert.equal(f.review.timeline.zoom,3);assert.equal(f.nodes.video.currentTime,5);
  assert.equal(f.nodes.restore.disabled,true);assert.equal(f.nodes.remove.disabled,false);
});

test('empty edit exposes entire original; previous and next removed jump by visual sections',()=>{
  const f=fixture();f.current.editor_sequence.source_tracks.A=[];f.review.open();
  assert.deepEqual(plain(f.review.selection),{start:0,end:12});assert.equal(f.nodes.restore.disabled,false);
  f.current.editor_sequence.source_tracks.A=[{start:0,end:2,source_start:2},{start:2,end:4,source_start:7}];f.review.refresh(true);
  f.review.jump(1);assert.deepEqual(plain(f.review.selection),{start:4,end:7});
  f.review.jump(1);assert.deepEqual(plain(f.review.selection),{start:9,end:12});
  f.review.jump(-1);assert.deepEqual(plain(f.review.selection),{start:4,end:7});
});

test('space controls only the source player; closing releases media and stale project cannot edit',async()=>{
  const f=fixture();f.review.open();
  const event={code:'Space',target:{closest:()=>null},preventDefault(){},stopPropagation(){}};
  f.dialog.listeners.keydown(event);assert.equal(f.nodes.video.paused,false);
  f.dialog.listeners.keydown({...event,repeat:true});assert.equal(f.nodes.video.paused,false);
  f.dialog.close();assert.equal(f.nodes.video.paused,true);assert.equal(f.nodes.video.src,undefined);
  f.current={...f.current,id:'another'};await f.review.edit('sequence_source_restore');assert.equal(f.requests.length,0);
});

test('failed edit keeps original selection and allows retry; busy blocks duplicate submissions',async()=>{
  const f=fixture();f.review.open();let resolve;
  f.review.applyEdit=()=>new Promise(done=>resolve=done);
  const pending=f.review.edit('sequence_source_restore');
  assert.equal(f.nodes.restore.disabled,true);assert.equal(f.nodes.slot.disabled,true);
  await f.review.edit('sequence_source_restore');resolve(null);await pending;
  assert.equal(f.nodes.restore.disabled,false);assert.match(f.nodes.status.textContent,/not confirmed/);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
});
test('B transcript and waveform are mapped back from analysis clock to B original time',()=>{
  const f=fixture();f.current.analysis={audio_source:'B',audio_timeline_offset:2,transcript:{segments:[{start:6,end:8,text:'B speech'}]},audio:{waveform:[{start:6,end:7,peak:.8}],ranges:{silence:[{start:7,end:8}]}}};
  f.review.open('B');f.nodes.video.listeners.loadedmetadata();
  assert.equal(f.nodes.quote.textContent,'B speech');
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio.waveform),[{start:4,end:5,peak:.8}]);
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio.ranges.silence),[{start:5,end:6}]);
  assert.equal(f.current.analysis.audio.waveform[0].start,6,'original analysis stays untouched');
});

test('manual original-source review draws uploaded A and B profiles in their native clocks',()=>{
  const f=fixture();
  f.current.pre_analysis={audio:{
    A:{waveform:[{start:1,end:2,rms_dbfs:-24}]},
    B:{waveform:[{start:4,end:5,rms_dbfs:-18}]},
  }};
  f.review.open('A');
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio?.waveform || []),[{start:1,end:2,rms_dbfs:-24}]);
  f.review.open('B');
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio?.waveform || []),[{start:4,end:5,rms_dbfs:-18}]);
  assert.equal(f.current.pre_analysis.audio.B.waveform[0].start,4,'uploaded measurement stays untouched');
});

test('uploaded B waveform wins over legacy shifted analysis without changing annotation clocks',()=>{
  const f=fixture();
  f.current.analysis={audio_source:'B',audio_timeline_offset:2,audio:{waveform:[{start:6,end:7,rms_dbfs:-30}],ranges:{silence:[{start:7,end:8}]}},transcript:{segments:[{start:6,end:8,text:'B speech'}]}};
  f.current.pre_analysis={audio:{B:{available:true,waveform:[{start:4,end:5,rms_dbfs:-18}]}}};
  f.review.open('B');f.nodes.video.listeners.loadedmetadata();
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio.waveform),[{start:4,end:5,rms_dbfs:-18}]);
  assert.equal(f.nodes.quote.textContent,'B speech');
  assert.equal(f.current.analysis.audio.waveform[0].start,6);
});

test('source review distinguishes no audio and unavailable preparation from measured silence',()=>{
  const f=fixture();
  f.current.pre_analysis={audio:{A:{available:true,waveform:[{start:0,end:1,rms_dbfs:-100,peak_dbfs:-100}]}}};
  f.review.open('A');
  assert.equal(f.review.timeline.project.analysis.audio.waveform.length,1,'measured silence retains its actual bins');
  f.current.sources.A.has_audio=false;f.review.refresh();
  assert.equal(f.review.timeline.project.analysis.audio,null);
  f.current.sources.A.has_audio=true;f.current.pre_analysis.audio.A={available:false,waveform:[],warning:'decode failed'};
  f.review.refresh();
  assert.equal(f.review.timeline.project.analysis.audio.available,false);
  assert.equal(f.review.timeline.project.analysis.audio.warning,'decode failed');
});

test('failed source preview can retry without changing selection, zoom or saved edits',()=>{
  const f=fixture(); f.review.open(); f.review.select({start:4,end:6}); f.review.timeline.zoom=3;
  const before=JSON.stringify(f.current);
  f.nodes.video.listeners.error();
  assert.equal(f.nodes.retry.hidden,false); assert.match(f.nodes.status.textContent,/retry/);
  f.nodes.retry.onclick();
  assert.equal(f.nodes.retry.hidden,true); assert.match(f.nodes.status.textContent,/Loading/);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6}); assert.equal(f.review.timeline.zoom,3);
  f.nodes.video.listeners.loadedmetadata();
  assert.equal(f.nodes.video.currentTime,4); assert.match(f.nodes.status.textContent,/Preview ready/);
  assert.equal(JSON.stringify(f.current),before); assert.equal(f.requests.length,0);
});

test('switching from a failed source clears its error after the next source loads',()=>{
  const f=fixture(); f.review.open('A'); f.nodes.video.listeners.error();
  f.nodes.slot.value='B'; f.nodes.slot.onchange();
  assert.equal(f.nodes.video.src,'b.mp4'); assert.equal(f.nodes.retry.hidden,true);
  f.nodes.video.listeners.loadedmetadata(); assert.doesNotMatch(f.nodes.status.textContent,/could not/);
  assert.match(f.nodes.status.textContent,/Preview ready/);
});

test('retry cannot load a closed dialog, another project or a busy edit',()=>{
  const f=fixture(); f.review.open(); f.dialog.close(); f.nodes.retry.onclick();
  assert.equal(f.nodes.video.src,undefined);
  f.review.open(); f.current={...f.current,id:'other'}; assert.equal(f.review.loadPreview(),false);
  f.current={...f.current,id:'p'}; f.review.busy=true; assert.equal(f.review.loadPreview(),false);
});

test('retry keeps the preview cursor inside the selected range',()=>{
  const f=fixture(); f.review.open(); f.review.select({start:4,end:6});
  f.nodes.video.currentTime=5; f.nodes.video.listeners.error(); f.nodes.retry.onclick();
  f.nodes.video.listeners.loadedmetadata(); assert.equal(f.nodes.video.currentTime,5);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
});


test('retry preserves a cursor at zero even when the selection starts later',()=>{
  const f=fixture(); f.review.open(); f.review.select({start:4,end:6});
  f.nodes.video.currentTime=0; f.nodes.video.listeners.error(); f.nodes.retry.onclick();
  f.nodes.video.listeners.loadedmetadata();
  assert.equal(f.nodes.video.currentTime,0);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
});

test('an unexpected edit failure ends loading and does not claim the edit was unchanged',async()=>{
  const f=fixture(); f.review.open();
  f.review.applyEdit=async()=>{ throw new Error('connection lost'); };
  await assert.doesNotReject(f.review.edit('sequence_source_restore'));
  assert.equal(f.review.busy,false);
  assert.equal(f.nodes.restore.disabled,false);
  assert.match(f.nodes.status.textContent,/could not confirm/i);
  assert.match(f.nodes.status.textContent,/reopen/i);
  assert.deepEqual(plain(f.review.selection),{start:4,end:6});
});


test('source B does not invent a clock for old waveform or transcript data',()=>{
  for(const value of [undefined,null,'','  ',false,{},NaN,Infinity]) {
    const f=fixture();
    f.current.analysis={audio_source:'B',audio:{waveform:[{start:4,end:5,peak:.8}]},
      transcript:{segments:[{start:4,end:6,text:'B speech'}]}};
    if(value!==undefined) f.current.analysis.audio_timeline_offset=value;
    f.review.open('B'); f.nodes.video.listeners.loadedmetadata();
    assert.equal(f.review.timeline.project.analysis.audio,null,'unknown B clock must not plot old analysis waveform');
    assert.notEqual(f.nodes.quote.textContent,'B speech','unknown B clock must not match a transcript segment');
  }
});

test('an explicit zero offset retains source B transcript and waveform',()=>{
  const f=fixture();
  f.current.analysis={audio_source:'B',audio_timeline_offset:0,audio:{waveform:[{start:4,end:5,peak:.8}]},
    transcript:{segments:[{start:4,end:6,text:'B speech'}]}};
  f.review.open('B'); f.nodes.video.listeners.loadedmetadata();
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio.waveform),[{start:4,end:5,peak:.8}]);
  assert.equal(f.nodes.quote.textContent,'B speech');
});

test('a native source B waveform remains usable without an analysis offset',()=>{
  const f=fixture();
  f.current.analysis={audio_source:'B',audio:{waveform:[{start:4,end:5,peak:.8}]}};
  f.current.pre_analysis={audio:{B:{available:true,waveform:[{start:1,end:2,peak:.6}]}}};
  f.review.open('B');
  assert.deepEqual(plain(f.review.timeline.project.analysis.audio.waveform),[{start:1,end:2,peak:.6}]);
});
