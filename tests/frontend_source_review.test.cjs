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
  for(const key of ['canvas','scroll','close','slot','scope','restore','remove','undo','previous','next','fit','zoomIn','zoomOut','exact','video','status','quote','selection','summary','effect']) nodes[key]={
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
  assert.equal(f.nodes.restore.disabled,false);assert.match(f.nodes.status.textContent,/not changed/);
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
