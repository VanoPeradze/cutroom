const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('web/timeline.js','utf8');
const context=vm.createContext({window:{devicePixelRatio:1},requestAnimationFrame(){throw Error('No new RAF permitted')}});
vm.runInContext(source.replace(/^export /gm,'')+'\nglobalThis.Timeline=TimelineView',context);
const plain=value=>JSON.parse(JSON.stringify(value));
const id=n=>'track_'+String(n).padStart(32,'0');
function fixture({rtl=false,version=3,legacy=false}={}) {
  const t=Object.create(context.Timeline.prototype), calls={draw:0,focus:0,seek:0,action:0};
  const tracks=Array.from({length:8},(_,i)=>({id:id(i+1),kind:['visual','audio','text'][i%3],name:'Track '+(i+1),
    ...(version>=2?{locked:i===0}:{}),...(version===3&&i%3!==2?{audio:{gain_db:0,muted:false}}:{})}));
  const project={id:'p',revision:9,sources:{A:{duration:120}},settings:{fps:30,burn_captions:false},assets:{v:{kind:'video'}},
    manual:{sequence:{duration:120},media_clips:[],text_clips:[],...(legacy?{}:{layer_tracks:{version,...(version===3?{protection_version:2}:{}),tracks}})}};
  let nativeLeft=0,nativeTop=0,paintWidth=0,paintHeight=0,rectShift=0,rectScale=1;
  const scroll={clientWidth:600,clientHeight:170,clientLeft:2,clientTop:3,isConnected:true,closest:()=>null,
    getBoundingClientRect:()=>({left:21.25,top:40.5,width:604,height:176})};
  const maxLeft=()=>Math.max(0,paintWidth-scroll.clientWidth),maxTop=()=>Math.max(0,paintHeight-scroll.clientHeight);
  Object.defineProperties(scroll,{scrollLeft:{get:()=>nativeLeft,set:v=>nativeLeft=rtl?Math.max(-maxLeft(),Math.min(0,v)):Math.max(0,Math.min(maxLeft(),v))},
    scrollTop:{get:()=>nativeTop,set:v=>nativeTop=Math.max(0,Math.min(maxTop(),v))}});
  const canvas={parentElement:scroll,isConnected:true,focus(){calls.focus++},getBoundingClientRect:()=>({left:21.25+scroll.clientLeft-(rtl?maxLeft()+nativeLeft:nativeLeft)+rectShift,
    top:40.5+scroll.clientTop-nativeTop,width:paintWidth*rectScale,height:paintHeight*rectScale})};
  Object.assign(t,{project,scroll,canvas,zoom:3,sourceReview:false,zoomFocusPending:false,raf:73,afterDraw:null,playhead:91.25,selection:{start:2,end:5},selectedMediaId:'media_keep',selectedMediaIds:()=>['media_keep'],tool:'blade',cutAnchor:8,
    onSeek(){calls.seek++},onMediaAction(){calls.action++},draw(){calls.draw++;paintWidth=this.geometry().width;paintHeight=this.mediaLayout().height;scroll.scrollLeft=nativeLeft;scroll.scrollTop=nativeTop;f.onDraw?.(calls.draw);}});
  const f={t,calls,tracks,onDraw:null,rtl,setRectShift:v=>rectShift=v,setRectScale:v=>rectScale=v,
    paint(){t.draw()}, physicalLeft:()=>rtl?maxLeft()+nativeLeft:nativeLeft,setPhysicalLeft:v=>{scroll.scrollLeft=rtl?v-maxLeft():v},
    state:()=>({zoom:t.zoom,left:nativeLeft,top:nativeTop,raf:t.raf,afterDraw:t.afterDraw,project:t.project,raw:JSON.stringify(t.project),playhead:t.playhead,selection:t.selection,selectedMediaId:t.selectedMediaId,tool:t.tool,cutAnchor:t.cutAnchor,zoomFocusPending:t.zoomFocusPending})};
  f.paint();calls.draw=0;f.setPhysicalLeft(300.25);scroll.scrollTop=210.5;return f;
}
function snapshot(f,values={}){return {zoom:4,leftTime:18.125,vertical:{trackId:id(5),offset:11.75},...values}}
function untouched(f,before){assert.deepEqual(f.state(),before);assert.equal(f.calls.draw,0);assert.equal(f.calls.focus,0);assert.equal(f.calls.seek,0);assert.equal(f.calls.action,0)}

for(const rtl of [false,true]) for(const version of [1,2,3]) test(`capture and restore actual world metrics ${rtl?'RTL':'LTR'} schema${version}`,()=>{
  const f=fixture({rtl,version}),before=f.state(),captured=f.t.captureEditingViewport(),row=f.t.mediaLayout().rows.find(r=>210.5>=r.top&&210.5<r.bottom);
  assert.deepEqual(plain(captured),{zoom:3,leftTime:300.25/f.t.geometry().px,vertical:{trackId:row.trackId,offset:210.5-row.top}});
  const plan=f.t.editingViewportPlan(snapshot(f));assert.ok(plan);untouched(f,before);
  assert.equal(f.t.restoreEditingViewport(snapshot(f)),true);assert.equal(f.t.zoom,4);assert.ok(Math.abs(f.physicalLeft()-18.125*f.t.geometry().px)<1e-9);
  assert.equal(f.t.scroll.scrollTop,plan.top);assert.equal(f.calls.draw,2);assert.equal(f.t.raf,before.raf);assert.equal(f.t.afterDraw,before.afterDraw);
  for(const key of ['project','raw','playhead','selection','selectedMediaId','tool','cutAnchor'])assert.equal(f.state()[key],before[key]);
  assert.equal(f.calls.focus+f.calls.seek+f.calls.action,0);
});
test('null vertical explicitly returns top zero, including legacy rows',()=>{
  for(const legacy of [false,true]){const f=fixture({legacy});assert.equal(f.t.restoreEditingViewport(snapshot(f,{vertical:null})),true);assert.equal(f.t.scroll.scrollTop,0)}
});
test('base rows capture null, never invent A or B stable anchors',()=>{const f=fixture();f.t.scroll.scrollTop=100;assert.equal(f.t.captureEditingViewport().vertical,null)});
test('legacy rows do not borrow a saved track ordinal',()=>{const f=fixture({legacy:true});assert.equal(f.t.captureEditingViewport().vertical,null);const b=f.state();assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);untouched(f,b)});
test('automatic caption rows capture null rather than a guessed lane',()=>{const f=fixture();f.t.project.settings.burn_captions=true;f.t.project.editor_captions=[{id:'c',start:0,end:2,text:'Hi'}];f.paint();f.t.scroll.clientHeight=10;f.t.scroll.scrollTop=f.t.mediaLayout().caption.top+5;f.calls.draw=0;assert.equal(f.t.captureEditingViewport().vertical,null)});
test('vertical row anchor clamps only against the actual scroll extent',()=>{const f=fixture();f.t.scroll.clientHeight=500;f.t.scroll.scrollTop=0;const p=snapshot(f,{vertical:{trackId:id(2),offset:55.9}}),plan=f.t.editingViewportPlan(p);assert.ok(plan);assert.equal(f.t.restoreEditingViewport(p),true);assert.equal(f.t.scroll.scrollTop,f.t.mediaLayout().height-500)});
for(const kind of ['text','audio','visual'])test(`row-specific offset is strictly inside ${kind}`,()=>{const f=fixture(),row=f.t.mediaLayout().rows.find(r=>r.type===kind);assert.ok(f.t.editingViewportPlan(snapshot(f,{vertical:{trackId:row.trackId,offset:row.height-0.00001}})));const before=f.state();assert.equal(f.t.restoreEditingViewport(snapshot(f,{vertical:{trackId:row.trackId,offset:row.height}})),false);untouched(f,before)});
for(const value of [null,[],{}, {zoom:2,leftTime:0}, {zoom:2,leftTime:0,vertical:null,extra:true},
  {zoom:'2',leftTime:0,vertical:null},{zoom:0.99,leftTime:0,vertical:null},{zoom:16.01,leftTime:0,vertical:null},
  {zoom:NaN,leftTime:0,vertical:null},{zoom:Infinity,leftTime:0,vertical:null},{zoom:2,leftTime:'0',vertical:null},
  {zoom:2,leftTime:-.01,vertical:null},{zoom:2,leftTime:Infinity,vertical:null},{zoom:2,leftTime:NaN,vertical:null},
  {zoom:1,leftTime:1,vertical:null},{zoom:2,leftTime:120,vertical:null},{zoom:2,leftTime:0,vertical:{}},
  {zoom:2,leftTime:0,vertical:{trackId:id(1),offset:'0'}},{zoom:2,leftTime:0,vertical:{trackId:id(1),offset:-1}},
  {zoom:2,leftTime:0,vertical:{trackId:'missing',offset:0}},{zoom:2,leftTime:0,vertical:{trackId:id(1),offset:0,extra:1}}])
test('invalid viewport refuses before assignment '+JSON.stringify(value),()=>{const f=fixture(),b=f.state();assert.equal(f.t.editingViewportPlan(value),null);assert.equal(f.t.restoreEditingViewport(value),false);untouched(f,b)});
for(const flag of ['sourceReview','gesture','scrubbing','selecting','libraryDragActive','editPending','mediaSelectionPending','mediaSourceOpening','trackLockPending','zoomFocusPending'])test('pending ownership blocks capture and restore '+flag,()=>{const f=fixture();f.t[flag]=true;const b=f.state();assert.equal(f.t.captureEditingViewport(),null);assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);untouched(f,b)});
for(const reason of ['zeroWidth','zeroHeight','disconnected','wrongParent','stalePaint','scaledCanvas','unavailable','badRevision','badTracks','orphan'])test('unmeasured or unsupported layout leaves viewport untouched '+reason,()=>{
  const f=fixture();if(reason==='zeroWidth')f.t.scroll.clientWidth=0;else if(reason==='zeroHeight')f.t.scroll.clientHeight=0;
  else if(reason==='disconnected')f.t.canvas.isConnected=false;else if(reason==='wrongParent')f.t.canvas.parentElement={};else if(reason==='stalePaint')f.t.zoom=5;
  else if(reason==='scaledCanvas')f.setRectScale(2);else if(reason==='unavailable')f.t.project.__timelineUnavailable=true;else if(reason==='badRevision')f.t.project.revision=0;
  else if(reason==='badTracks')f.t.project.manual.layer_tracks.version=999;else f.t.project.manual.media_clips.push({id:'m',asset_id:'v',start:1,end:4,track_id:'missing'});
  const b=f.state();assert.equal(f.t.captureEditingViewport(),null);assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);untouched(f,b);
});
test('a caller plan cannot authorize a later unsupported project',()=>{const f=fixture(),p=snapshot(f);assert.ok(f.t.editingViewportPlan(p));f.t.project={...f.t.project,__timelineUnavailable:true};const b=f.state();assert.equal(f.t.restoreEditingViewport(p),false);untouched(f,b)});
test('physical verification failure restores old zoom and scroll without taking RAF ownership',()=>{const f=fixture(),b=f.state();f.onDraw=n=>{if(n===1)f.setRectShift(-20);else f.setRectShift(0)};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);assert.deepEqual(f.state(),b);assert.equal(f.calls.focus+f.calls.seek+f.calls.action,0)});
test('renderer exception fails closed and restores the old viewport when still owned',()=>{const f=fixture(),b=f.state();f.onDraw=n=>{if(n===1)throw Error('Draw failed')};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);assert.deepEqual(f.state(),b)});
test('project replacement during draw is never overwritten by rollback',()=>{const f=fixture();const next={...f.t.project,id:'new'};f.onDraw=n=>{if(n===1){f.t.project=next;f.t.zoom=7;f.t.scroll.scrollLeft=123}};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);assert.equal(f.t.project,next);assert.equal(f.t.zoom,7);assert.equal(f.t.scroll.scrollLeft,123)});
test('revision replacement during draw invalidates apply',()=>{const f=fixture();f.onDraw=n=>{if(n===1)f.t.project.revision++};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);assert.equal(f.calls.draw,1)});
test('same model row-layout change cannot adopt a stale anchor',()=>{const f=fixture();f.onDraw=n=>{if(n===1)f.t.project.manual.layer_tracks.tracks.reverse()};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false)});
test('viewport resize during draw does not report a successful old-width restoration',()=>{const f=fixture();f.onDraw=n=>{if(n===1)f.t.scroll.clientWidth=450};assert.equal(f.t.restoreEditingViewport(snapshot(f)),false)});

test('pending selection-zoom callback refuses restoration without clearing or invoking it',()=>{const f=fixture(),after=()=>{f.t.scroll.scrollLeft=999};f.t.afterDraw=after;const before=f.state();assert.equal(f.t.captureEditingViewport(),null);assert.equal(f.t.restoreEditingViewport(snapshot(f)),false);untouched(f,before);assert.equal(f.t.afterDraw,after)});
