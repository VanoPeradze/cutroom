const test=require('node:test'), assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const read=name=>fs.readFileSync(path.join(__dirname,'../web',name),'utf8');
const helpers=read('range-export.js').replace(/^export /gm,''), app=read('app.js');
const functions=app.slice(app.indexOf('function currentExportRangePlan()'),app.indexOf('function openExportDialog('))
 +app.slice(app.indexOf('async function startExport()'),app.indexOf('function friendlyRenderError('));
const api=vm.runInNewContext(helpers+'\n;({makeExportRangePlan,sameExportRangePlan,exportFrameTime,exportRangeLabel})');
const good={id:'demo',view:2,revision:7,duration:6,editor:true,editMode:true,start:.7,end:1.4};
const plain=v=>JSON.parse(JSON.stringify(v));
for(const fps of [24,25,30,50,60])test(fps+' fps: integer and last-frame interval never includes Out',()=>{
 const e=api.makeExportRangePlan({...good,start:6-1/fps,end:6},fps);
 assert.deepEqual(plain(e.range),{start_frame:6*fps-1,end_frame:6*fps,fps,expected_revision:7});
 assert.equal(api.exportFrameTime(e.range.end_frame,fps),'00:00:06:00');
});
for(const [name,patch] of Object.entries({source:{editMode:false},absent:{editor:false},
 dirty:{dirtyRange:true},occurrence:{occurrence:true},noRevision:{revision:null},reversed:{start:2,end:1},
 point:{end:.7},outside:{end:6.01},negative:{start:-1},tiny:{start:.701,end:.702},invalid:{end:NaN}}))
 test('no selection export for '+name,()=>assert.equal(api.makeExportRangePlan({...good,...patch},30),null));
for(const [name,patch] of Object.entries({project:{id:'next'},view:{view:3},revision:{revision:8},
 duration:{duration:7},subframeIn:{start:.701},subframeOut:{end:1.401}}))
 test('range intent does not survive '+name+' changing',()=>{
 const a=api.makeExportRangePlan(good,30),b=api.makeExportRangePlan({...good,...patch},30);
 assert(!api.sameExportRangePlan(a,b));
});
test('tie rounds up; frame interval and label describe exported not typed times',()=>{
 const a=api.makeExportRangePlan({...good,start:1.25,end:1.75},30);
 assert.equal(api.exportRangeLabel(a.range),'00:00:01:08 → 00:00:01:23 · 15 frames');
 assert.equal(api.makeExportRangePlan(good,29.97),null);
 assert(!api.sameExportRangePlan(a,api.makeExportRangePlan({...good,start:1.25,end:1.75},60)));
});

function host(){
 const whole={},marked={},cell={small:{},b:{},querySelector(k){return this[k]}};
 const scope={value:'whole',querySelector(k){return k.includes('whole')?whole:marked}};
 const e={exportScope:scope,exportScopeField:{},exportScopeHelp:{},exportScopeLabel:{},exportFpsSelect:{value:'30'},
 exportSummary:{lastElementChild:cell},exportActions:{},exportProgress:{},exportFrameRateField:{},exportTitle:{},exportDescription:{},downloadExport:{}};
 const state={project:{id:'demo',settings:{fps:30},draft:{output_duration:6}},projectViewToken:2,timeline:{selectionIsRange:true}},snap={...good},posts=[],alerts=[];
 const c=vm.createContext({state,elements:e,snap,posts,alerts,rangeAuditionSnapshot:()=>({...snap}),
 editorProject:()=>state.project,uiCopy:(_he,en)=>en,t:k=>k,formatTime:String,toast:m=>alerts.push(m),
 savedLayerTrackIssue:()=>'',requireResolvedExplicitDrafts:()=>true,requireSavedTranscript:()=>true,hasTimelineFootage:()=>true,
 exportRequiresDraftRebuild:()=>false,pauseAllMedia:()=>{},document:{getElementById:()=>null},liveEmbeddedCameraRequest:()=>false,
 acquireJobStartLock:()=>1,releaseJobStartLock:()=>{},showExportLayoutWarning:()=>{},assertJobStartNotCancelled:()=>{},
 flushProjectSaves:async()=>{},api:async(u,o)=>{posts.push([u,JSON.parse(o.body)]);return{job:{id:'job'}}},
 setActiveJob:()=>{},pollExportJob:async()=>({}),completeExportJob:async()=>{},friendlyRenderError:m=>m});
 vm.runInContext(helpers+'\n'+functions,c);const call=s=>vm.runInContext(s,c);
 return {call,ctx:c,state,snap,e,scope,whole,marked,cell,posts,alerts,select:()=>{scope.value='selection';call('refreshExportScope({choose:true})')}};
}
test('range choice is explicit, shows frame-grid duration, and new dialog goes back to whole',()=>{
 const h=host();h.call('refreshExportScope({reset:true})');assert.equal(h.scope.value,'whole');assert(!h.marked.disabled);
 h.select();assert.equal(h.cell.b.textContent,'00:00:00:21');assert.match(h.e.exportScopeHelp.textContent,/21 frames.*exclusive/);
 h.call('refreshExportScope({reset:true})');assert.equal(h.scope.value,'whole');assert.equal(h.state.markedExportIntent,null);
 assert.equal(h.cell.b.textContent,'6');
});
test('clicking a source clip does not turn its numeric extent into an export range',()=>{
 const h=host();h.state.timeline.selectionIsRange=false;h.call('refreshExportScope({reset:true})');
 assert(h.marked.disabled);assert.equal(h.scope.value,'whole');assert.equal(h.state.markedExportIntent,null);
});
test('whole timeline dispatch contains no hidden scope or FPS overrides',async()=>{
 const h=host();h.call('refreshExportScope({reset:true})');await h.call('startExport()');
 assert.deepEqual(h.posts,[['/api/projects/demo/render',{}]]);
});
test('marked API action sends only exact reviewed output frames and revision',async()=>{
 const h=host();h.select();await h.call('startExport()');
 assert.deepEqual(h.posts,[['/api/projects/demo/render',{range:{start_frame:21,end_frame:42,fps:30,expected_revision:7}}]]);
});
for(const [name,change] of [['accepted revision',h=>h.snap.revision++],['new raw marks',h=>h.snap.end+=.001],
 ['switched to a source occurrence',h=>h.snap.occurrence=true],['changed FPS control',h=>h.e.exportFpsSelect.value='60'],
 ['user selected whole while saving',h=>h.scope.value='whole']])
 test(name+' during async save refuses to send any output job',async()=>{
 const h=host();h.select();h.ctx.flushProjectSaves=async()=>change(h);await h.call('startExport()');
 assert.deepEqual(h.posts,[]);assert.match(h.e.exportDescription.textContent,/changed/);
 });
test('optional SRT belongs to the displayed export; stale links disappear instead of using a full-edit subtitle file',()=>{
 const h=host(),attrs={},link={removeAttribute(k){delete this[k]}};h.e.downloadExportCaptions=link;
 h.ctx.captionRecord={range:{start_frame:1,end_frame:5,fps:30},captions_name:'marked.srt',captions_url:'/api/exports/marked.srt'};
 h.call('showExportSubtitles(captionRecord)');assert.equal(link.href,'/api/exports/marked.srt');assert.equal(link.download,'marked.srt');assert.equal(link.hidden,false);assert.match(link.textContent,/range subtitles/);
 h.call('showExportSubtitles(captionRecord,true)');assert.match(link.textContent,/Previous range/);
 h.call('showExportSubtitles(null)');assert.equal(link.hidden,true);assert.equal(link.href,undefined);assert.equal(link.download,undefined);
});
test('stale marks before submit stay visibly invalid, not silently upgraded to entire edit',async()=>{
 const h=host();h.select();h.snap.start=null;h.call('refreshExportScope()');assert.equal(h.scope.value,'selection');
 assert.equal(h.cell.b.textContent,'?');await h.call('startExport()');assert.deepEqual(h.posts,[]);assert.match(h.alerts[0],/changed/);
});
