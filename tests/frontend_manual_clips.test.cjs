const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const src=n=>fs.readFileSync(path.join(__dirname,'../web',n),'utf8');
const lib=vm.runInNewContext(src('manual-clips.js').replace(/^export /gm,'')+
  '\n;({manualClipRows,manualClipTimes,editClock,manualClipLength,manualStatusText,sourcePieces,manualExportItem,batchItemLabel})');
const {makeExportRangePlan}=vm.runInNewContext(src('range-export.js').replace(/^export /gm,'')+'\n;({makeExportRangePlan})');
const row=(a=60,b=180,i=1,over={})=>({id:'mclip_'+String(i).padStart(12,'0'),name:'Clip '+i,start_frame:a,end_frame:b,fps:30,status:'ready',...over});
const reg=(...items)=>({version:1,items});const plain=x=>JSON.parse(JSON.stringify(x));

test('saved lists sort by edit time; unknown or malformed lists are unavailable, not empty',()=>{
  assert.deepEqual(plain(lib.manualClipRows(undefined)),[]);
  assert.deepEqual(plain(lib.manualClipRows(reg(row(600,690,2),row()))).map(r=>r.start_frame),[60,600]);
  for(const bad of [{version:2,items:[]},{version:1,items:[],unavailable:true},reg(row(0,0)),reg(row(),row()),reg(row(0,30,1,{fps:29.97})),
      reg(row(0,30,1,{status:'other'})),reg(row(0,30,1,{id:'x'})),reg(row(0,30,1,{name:''}))])
    assert.equal(lib.manualClipRows(bad),null);
});
test('times and labels come from output frames',()=>{
  assert.deepEqual(plain(lib.manualClipTimes(row(60,180))),{start:2,end:6,duration:4});
  assert.equal(lib.editClock(3725.9),'1:02:05');assert.equal(lib.editClock(65),'1:05');
  assert.equal(lib.manualClipLength(row(0,45)),'1.5s');assert.equal(lib.manualClipLength(row(0,3600)),'2:00');
  assert.match(lib.manualStatusText('changed'),/Needs review/);assert.equal(lib.manualStatusText('ready'),'');
});
test('preview pieces follow the edit across a cut and respect speed',()=>{
  const clips=[{start:0,end:10,source_start:0},{start:10,end:35,source_start:15},{start:35,end:40,source_start:50,video_speed:2}];
  assert.deepEqual(plain(lib.sourcePieces(clips,8,12)),[{start:8,end:10,from:8,to:10},{start:10,end:12,from:15,to:17}]);
  assert.deepEqual(plain(lib.sourcePieces(clips,36,38)),[{start:36,end:38,from:52,to:56}]);
  assert.deepEqual(plain(lib.sourcePieces(clips,50,60)),[]);
});
test('batch items keep exact frames and the saved id',()=>{
  const item=lib.manualExportItem(row(600,690,2,{name:'After the cut'}));
  assert.equal(item.manual,true);assert.equal(item.id,'mclip_000000000002');assert.equal(item.start_frame,600);assert.equal(item.end,23);
  assert.equal(lib.batchItemLabel(item),'After the cut');assert.equal(lib.batchItemLabel({rank:3}),'Clip 3');
});

const app=src('app.js');
const slice=(a,b)=>{const i=app.indexOf(a),j=app.indexOf(b,i);assert(i>0&&j>i,a);return app.slice(i,j);};
const hostSrc=slice('function adoptManualClips(','async function openClipBoard()');
function host(over={}){
  const s={studio:{open:true},projectViewToken:4,preview:{playing:false},manualClipSaving:false,
    project:{id:'p',revision:9,editor_sequence:{sequence:{},source_tracks:{},duration:35},settings:{fps:30},sources:{A:{}},draft:{}},
    timeline:{project:{id:'p',revision:9},playhead:12.5,selection:{start:2,end:6},selectionIsRange:true,draws:0,scheduleDraw(){this.draws++;}}};
  s.manualSelection=s.timeline.selection;
  const button={hidden:true,disabled:true,title:''},toasts=[],calls=[],seeks=[];
  const c=vm.createContext({state:s,elements:{resultPanel:{hidden:false},playButton:{disabled:false},addToClipsButton:button},
    manualClipRows:lib.manualClipRows,sourcePieces:lib.sourcePieces,editClock:lib.editClock,makeExportRangePlan,
    foregroundBusy:()=>false,previewUsesSourceTime:()=>false,rangeInputPending:()=>false,requireResolvedExplicitDrafts:()=>true,requireSavedTranscript:()=>true,
    flushProjectSaves:async()=>{},editorProject:()=>({...s.project}),rememberProjectRevision:p=>{s.remembered=p.revision;},
    toast:m=>toasts.push(m),seekSourcePreview:t=>seeks.push(t),seekPreview:t=>seeks.push(t),setActiveJob(){},
    api:async(url,opts)=>{calls.push([url,opts&&JSON.parse(opts.body)]);return over.reply?over.reply(s):{project_id:'p',previous_revision:9,revision:10,clip_id:'mclip_000000000001',manual_clips:reg(row())};},
    ...over.ctx});
  vm.runInContext(app.slice(app.indexOf('function rangeAuditionSnapshot()'),app.indexOf('// A long-GOP browser seek')),c);
  vm.runInContext(hostSrc,c);
  return {c,s,button,toasts,calls,seeks};
}
test('Add to Clips saves the marked frames without seeking, cutting or clearing the marks',async()=>{
  const h=host();h.c.syncAddToClipsButton();
  assert.equal(h.button.hidden,false);assert.equal(h.button.disabled,false);
  const sel=h.s.timeline.selection;await h.c.addRangeToClips();
  assert.equal(h.calls.length,1);
  assert.deepEqual(h.calls[0],['/api/projects/p/manual-clips',{action:'add',start_frame:60,end_frame:180,fps:30,expected_revision:9}]);
  assert.equal(h.s.project.revision,10);assert.equal(h.s.timeline.project.revision,10);assert.equal(h.s.remembered,10);
  assert.equal(h.s.timeline.selection,sel);assert.equal(h.s.timeline.playhead,12.5);assert.deepEqual(h.seeks,[]);
  assert.equal(h.s.project.manual_clips.items.length,1);assert.match(h.toasts.at(-1),/Saved to Clips as Clip 1/);
  assert.equal(h.s.manualClipSaving,false);
});
test('Add to Clips is unavailable without In/Out, in Full source, or while busy',()=>{
  for(const change of [h=>{h.s.timeline.selectionIsRange=false;},h=>{h.c.previewUsesSourceTime=()=>true;},h=>{h.c.foregroundBusy=()=>true;}]){
    const h=host();change(h);h.c.syncAddToClipsButton();assert.equal(h.button.disabled,true);
  }
});
test('marks that change during the pending save are not saved',async()=>{
  const h=host();h.c.flushProjectSaves=async()=>{h.s.timeline.selection=h.s.manualSelection={start:3,end:6};};
  await h.c.addRangeToClips();assert.equal(h.calls.length,0);assert.match(h.toasts.at(-1),/marks changed/);
});
test('a receipt for a different revision is not adopted',async()=>{
  const h=host({reply:()=>({project_id:'p',previous_revision:9,revision:12,clip_id:'mclip_000000000001',manual_clips:reg(row())})});
  await h.c.addRangeToClips();assert.equal(h.s.project.revision,9);assert.equal(h.s.project.manual_clips,undefined);
});
test('rename, remove and keep go through the narrow receipt with the current revision',async()=>{
  const h=host();await h.c.writeManualClip({action:'rename',id:'mclip_000000000001',name:'Hook'});
  assert.deepEqual(h.calls[0][1],{action:'rename',id:'mclip_000000000001',name:'Hook',expected_revision:9});
  assert.equal(h.s.project.revision,10);
  const busy=host();busy.c.foregroundBusy=()=>true;
  await assert.rejects(busy.c.writeManualClip({action:'remove',id:'mclip_000000000001'}),/Wait/);assert.equal(busy.calls.length,0);
});

const batchSrc=slice('async function exportClipBatch(','// --- Manual clips');
function batch(results){
  const s={project:{id:'p',revision:5,settings:{fps:30},editor_sequence:{}}},bodies=[];let n=0;
  const c=vm.createContext({state:s,clipBatchSupported:()=>true,flushCurrentProjectSaves:async()=>true,savedLayerTrackIssue:()=>'',hasTimelineFootage:()=>true,
    exportRequiresDraftRebuild:()=>false,requireResolvedExplicitDrafts:()=>true,requireSavedTranscript:()=>true,pauseAllMedia(){},
    acquireJobStartLock:()=>({}),releaseJobStartLock(){},setActiveJob(){},clearActiveJob(){},friendlyRenderError:m=>m,t:x=>x,setTimeout:f=>f(),
    clipTimelineRange:()=>null,completeExportJob:async()=>{s.project={...s.project,revision:s.project.revision+1};},
    postRender:async(_projectId,body)=>{bodies.push(body);const r=results[n++];
      if(r instanceof Error)throw r;return{job:{id:'j'+n,status:r,result:{url:'/x'+n,export:{name:'n'+n}}}};},
    api:async()=>({job:{status:'completed'}})});
  vm.runInContext(batchSrc,c);return{c,s,bodies};
}
test('manual clips export their exact frames with their id; one failure does not stop the queue',async()=>{
  const fail=Object.assign(new Error('The edit changed inside this clip. Review it in Clips before exporting.'),{code:'clip_changed'});
  const b=batch([fail,'completed']);
  const items=[lib.manualExportItem(row(60,180,1)),lib.manualExportItem(row(600,690,2))];
  const results=await b.c.exportClipBatch(items);
  assert.deepEqual(plain(b.bodies),[{clip:'mclip_000000000001',range:{start_frame:60,end_frame:180,fps:30,expected_revision:5}},
    {clip:'mclip_000000000002',range:{start_frame:600,end_frame:690,fps:30,expected_revision:5}}]);
  assert.match(results[0].error,/Review it in Clips/);assert.equal(results[1].url,'/x2');
});
test('a frame-rate change fails that clip only',async()=>{
  const b=batch(['completed']);
  const results=await b.c.exportClipBatch([lib.manualExportItem(row(0,25,1,{fps:25})),lib.manualExportItem(row(60,90,2))]);
  assert.match(results[0].error,/frame rate/);assert.equal(results[1].url,'/x1');assert.equal(b.bodies.length,1);
});
