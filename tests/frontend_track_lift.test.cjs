const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),{pathToFileURL}=require('node:url');
const math=import(pathToFileURL(path.resolve(__dirname,'../web/track-lift.js')).href);
const id=(kind,c)=>kind+'_'+c.repeat(32),a=c=>id('asset',c),m=c=>id('media',c),t=c=>id('track',c),T=t('d'),U=t('e'),N=t('9'),ns=n=>Math.round(n*1e9)/1e9;
function make(fps=30,split=false){
 const assets=Object.fromEntries([...['1','2','3'].map(v=>[v,'video']),['7','audio']].map(([c,kind])=>[a(c),{id:a(c),kind,name:c,status:'ready',duration:24,has_audio:true}]));
 const row=(c,lo,hi,patch={})=>({id:m(c),asset_id:a(c),track_id:T,start:lo,end:hi,source_start:.4,video_source_start:1.5,speed:1.5,volume_db:-2,muted:false,role:'voice',enabled:true,audio_enabled:true,x:0,y:0,w:1,h:1,fit:'cover',motion:'none',fade_in:0,fade_out:0,...patch});
 const left=row('1',3,5,{fade_in:.10}),inside=row('2',5,6,{motion:'pan',fade_in:.22}),right=row('3',6,9,{speed:.5,enabled:false,fade_out:.13}),other=row('7',4,9,{track_id:U,speed:1});
 return {id:'project_test',revision:8,assets,settings:{fps},draft:{output_duration:14},sources:{A:{duration:14}},editor_sequence:{duration:14},editor_captions:[{id:'existing'}],manual:{media_clips:split?[other,{...left,end:9}]:[right,inside,other,left],text_clips:[],history:{undo_count:2,redo_count:1},audio_mixer:{master_db:-1},layer_tracks:{version:2,tracks:[{id:T,name:'Overlay',kind:'visual',locked:false},{id:U,name:'Score',kind:'audio',locked:true},{id:N,name:'Empty',kind:'visual',locked:false}]}}};
}
const detail=(fps=30)=>({track_id:T,start_frame:Math.round(4.5*fps),end_frame:Math.round(7.3*fps)});
async function saved(p,d){const {planTrackLift}=await math;const q=planTrackLift(p,d);assert.equal(q.issue,'');const out=structuredClone(p);out.manual.media_clips=q.rows.map(n=>({...n,id:n.id??m('b')}));out.revision++;out.manual.history={undo_count:Math.min(20,p.manual.history.undo_count+1),redo_count:0};return out;}
for(const fps of [24,25,30,50,60])for(const split of [false,true]){
 test('One track, two native clocks, independent cells, '+fps+' fps; split='+split,async()=>{const {planTrackLift,verifyTrackLift,describeTrackLift}=await math,p=make(fps,split),before=structuredClone(p),d=detail(fps),z=planTrackLift(p,d);
 assert.equal(z.issue,'');assert.equal(z.track.id,T);assert.deepEqual(p,before);assert.equal(z.rows.find(x=>x.id===m('7')),p.manual.media_clips.find(x=>x.id===m('7')));assert(z.rows.filter(x=>x.track_id===T).every(x=>x.end<=z.start||x.start>=z.end));assert.deepEqual(z.counts,split?{removed:0,trimmed:0,split:1}:{removed:1,trimmed:2,split:0});assert.equal(z.rows.length,split?3:3);
 const r=z.rows.find(x=>x.track_id===T&&x.start===z.end),base=split?p.manual.media_clips[1]:p.manual.media_clips[0];
 assert(r);assert.equal(r.id,split?null:base.id);assert.equal(r.source_start,ns(base.source_start+z.end-base.start));assert.equal(r.video_source_start,ns(base.video_source_start+(z.end-base.start)*base.speed));assert.equal(r.fade_in,0);assert.equal(r.fade_out,base.fade_out);assert.match(describeTrackLift(z),/Out excluded/);assert.equal(verifyTrackLift(p,await saved(p,d),d),'');});
}
for(const [name,range,fps,duration,expected] of [
 ['interior only',{start:4.501,end:7.299},30,14,[136,218]],['exact edges',{start:4.5,end:7.3},30,14,[135,219]],['nanosecond stored frame',{start:.333333333,end:.666666667},30,14,[10,20]],
 ['fractional edit tail',{start:1,end:2.149},25,2.149,[25,53]],['zero',null,30,14,null],['reversed',{start:5,end:4},30,14,null],['negative',{start:-1,end:5},30,14,null],
 ['too short',{start:.033,end:.075},30,14,null],['over end',{start:10,end:15},30,14,null],['nonnumeric',{start:'1',end:2},30,14,null],['unsupported',{start:1,end:3},29.97,14,null]
])test('Frame range '+name,async()=>{const {liftFrameRange}=await math,q=liftFrameRange(range,fps,duration);if(expected)assert.deepEqual([q.start_frame,q.end_frame],expected);else assert(q.issue);});
for(const [name,change] of [
 ['unset lane',(p,d)=>d.track_id=''],['audio lane',(p,d)=>d.track_id=U],['empty lane',(p,d)=>d.track_id=N],['locked',(p)=>p.manual.layer_tracks.tracks[0].locked=true],
 ['unprepared',(p)=>p.assets[a('1')].status='preparing'],['project clock',(p)=>p.editor_sequence.error='broken'],['missing track model',(p)=>delete p.manual.layer_tracks],
 ['fractional frame',(p,d)=>d.start_frame+=.5],['string numeric',(p,d)=>d.start_frame='135'],['reversed frames',(p,d)=>d.end_frame=120],['one frame',(p,d)=>d.end_frame=d.start_frame+1],
 ['past end',(p,d)=>d.end_frame=600],['non-finite duration',p=>p.editor_sequence.duration=NaN],['partial motion',(p)=>p.manual.media_clips.at(-1).motion='zoom'],
 ['fade interior',(p)=>p.manual.media_clips.at(-1).fade_out=1],['tiny survivor',(p,d)=>d.start_frame=91],
 ])test('Refuse without modifying data: '+name,async()=>{const {planTrackLift}=await math,p=make(),d=detail();change(p,d);const prev=structuredClone(p);assert(planTrackLift(p,d).issue);assert.deepEqual(p,prev);});
for(const [name,change] of [
 ['double revision',p=>p.revision++],['lost history',p=>p.manual.history.undo_count=2],['unexpected redo',p=>p.manual.history.redo_count=1],
 ['new claims old ID',p=>p.manual.media_clips.at(-1).id=m('1')],['new ID invalid',p=>p.manual.media_clips.at(-1).id='bad'],
 ['wrong sound clock',p=>p.manual.media_clips.at(-1).source_start+=.03],['wrong picture clock',p=>p.manual.media_clips.at(-1).video_source_start+=.03],
 ['shifted another track',p=>p.manual.media_clips[0].start+=.3],['lost source',p=>p.sources.A.duration=9],['changed primary',p=>p.editor_sequence.duration--],
 ['changed text',p=>p.manual.text_clips.push({id:'rogue'})],['global mix changed',p=>p.manual.audio_mixer.master_db=2],
 ['extra cell',p=>p.manual.media_clips.push(p.manual.media_clips[0])]
 ])test('Reject unverified saved lift: '+name,async()=>{const {verifyTrackLift}=await math,p=make(30,true),d=detail(),q=await saved(p,d);change(q);assert(verifyTrackLift(p,q,d));});

function fake(){
 class E{constructor(){this.listeners={};this.value='';this.textContent='';this.disabled=false;this.open=false;this.hidden=false;this.children=[];}addEventListener(k,f){this.listeners[k]=f}removeEventListener(k){delete this.listeners[k]}fire(k){this.listeners[k]?.()}replaceChildren(...v){this.children=v;this.value=v[0]?.value||'';}}
 const root=new E(),lane=new E(),status=new E(),apply=new E(),receipt=new E(),nodes={'#trackLiftLane':lane,'#trackLiftStatus':status,'#trackLiftApply':apply,'#trackLiftReceipt':receipt};root.ownerDocument={createElement:()=>new E};root.querySelector=k=>nodes[k];
 let ctx={project:make(),view:1,range:{start:4.5,end:7.3},issue:''},calls=[],finish;const commit=async(owner,d,owns)=>{calls.push({owner,d,owns});return new Promise(r=>finish=r);};return {root,lane,status,apply,receipt,calls,snapshot:()=>ctx,ctx,commit,finish:(p)=>finish(p)};
}
const tick=()=>new Promise(r=>setImmediate(r));
test('Disclosure does not guess the lane and double activation submits once; valid receipt prevents a repeat',async()=>{const {initTrackLift}=await math,g=fake();const ctl=initTrackLift(g.root,g);g.root.open=true;g.root.fire('toggle');assert(g.apply.disabled);assert.equal(g.lane.value,'');assert.deepEqual(g.lane.children.map(n=>n.value),['',T,N]);g.lane.value=T;g.lane.fire('change');assert(!g.apply.disabled);assert.match(g.status.textContent,/Remove 1 whole, trim 2, split 0/);g.apply.fire('click');g.apply.fire('click');assert.equal(g.calls.length,1);const q=await saved(g.ctx.project,g.calls[0].d);g.ctx.project=q;g.finish(q);await tick();assert(!g.receipt.hidden);assert.match(g.receipt.textContent,/Undo/);assert(g.apply.disabled);assert.match(g.status.textContent,/already empty/);ctl.destroy();});
test('A different current selection cannot submit an unreviewed retained window',async()=>{const {initTrackLift}=await math,g=fake();initTrackLift(g.root,g);g.root.open=true;g.root.fire('toggle');g.lane.value=T;g.lane.fire('change');g.ctx.range={start:4.2,end:7.3};g.apply.fire('click');assert.equal(g.calls.length,0);assert(!g.apply.disabled);});
test('Closing after admission does not restore a stale receipt in a new project or family of tracks',async()=>{const {initTrackLift}=await math,g=fake();const ctl=initTrackLift(g.root,g);g.root.open=true;g.root.fire('toggle');g.lane.value=T;g.lane.fire('change');g.apply.fire('click');const sent=g.calls[0];g.root.open=false;g.root.fire('toggle');assert(!sent.owns());const q=await saved(g.ctx.project,sent.d);g.ctx.project={...make(),id:'project_other'};g.ctx.view++;g.finish(q);await tick();g.root.open=true;g.root.fire('toggle');assert.equal(g.lane.value,'');assert(g.receipt.hidden);assert(g.apply.disabled);ctl.destroy();});
test('Readiness denial disables and never submits the command',async()=>{const {initTrackLift}=await math,g=fake();const ctl=initTrackLift(g.root,g);g.root.open=true;g.root.fire('toggle');g.lane.value=T;g.ctx.issue='Save the pending caption first.';g.lane.fire('change');assert(g.apply.disabled);g.apply.fire('click');assert.equal(g.calls.length,0);assert.match(g.status.textContent,/caption/);ctl.destroy();});

// Exercise the actual application guard, not only its pure edit planner.
const hostSource=require('node:fs').readFileSync(path.resolve(__dirname,'../web/app.js'),'utf8').replace(/\r\n/g,'\n');
const hostFns=hostSource.slice(hostSource.indexOf('function trackLiftSnapshot('),hostSource.indexOf('function rollingSnapshot('));
function host(){
 const p=make(),s={project:p,studio:{open:true},timeline:{project:p},projectViewToken:3,manualSelection:{start:4.5,end:7.3},mediaStudio:{},preview:{playing:false},activeUploads:new Set(),jobStartLocks:new Set()};
 const nodes={studioPanelTimeline:{hidden:false},editClipTools:{hidden:false},studioInspector:{dataset:{}}};
 const env={state:s,document:{getElementById:id=>nodes[id],querySelector:()=>null},rangeInputPending:()=>false,previewUsesSourceTime:()=>false,activeEditTarget:()=>'edit',
 selectedLayerGroupIds:()=>[],projectCopySourceBusy:()=>false,previewRepairBusy:()=>false,sourceMonitorIssue:()=>'',foregroundBusy:()=>false,projectSaveStatus:()=>({kind:'saved'}),hasUnsavedProjectWork:()=>false,planTrackLift:()=>({issue:''})};
 require('node:vm').runInNewContext(hostFns,env);return {s,p,env,nodes};
}
for(const [name,alter] of [
 ['no studio',({s})=>s.studio.open=false],['revision mismatch',({s,p})=>s.timeline.project={...p,revision:3}],['missing timeline',({s})=>s.timeline=null],['no saved edit',({p})=>delete p.editor_sequence],
 ['wrong room',({nodes})=>nodes.studioPanelTimeline.hidden=true],['effects pane',({nodes})=>nodes.editClipTools.hidden=true],['AI pane',({nodes})=>nodes.studioInspector.dataset.workbenchPane='ai'],
 ['Program source',({env})=>env.previewUsesSourceTime=()=>true],['playing',({s})=>s.preview.playing=true],['A/B target',({env})=>env.activeEditTarget=()=>'A'],
 ['typed but unselected time',({env})=>env.rangeInputPending=x=>x==='timeline'],['multi-selection',({env})=>env.selectedLayerGroupIds=()=>['a','b']],['dragging',({s})=>s.timeline.gesture={}],
 ['source open pending',({s})=>s.timeline.mediaSourceOpening=true],['upload',({s})=>s.activeUploads.add('x')],['queue',({s})=>s.mediaStudio.importQueue={running:true}],
 ['unsubmitted draft',({env})=>env.hasUnsavedProjectWork=()=>true],['save barrier',({env})=>env.sourceMonitorIssue=()=>'caption draft'],['processing',({s})=>s.activeJob={}],
 ])test('Real lift host rejects '+name,()=>{const h=host();alter(h);assert(h.env.trackLiftSnapshot().issue);});
test('A submitted operation retains exact view, track, selection and revision ownership throughout admission',async()=>{const {env,s,p}=host();let posted=0,guards;
 const owner={id:p.id,view:3,revision:p.revision,range:{...s.manualSelection},track:T},d=detail();let stillOwns=true;
 env.applyManualEdit=async(action,payload,g)=>{posted++;assert.equal(action,'media_track_lift');assert.deepEqual(payload,d);guards=g;return p};
 await env.commitTrackLift(owner,d,()=>stillOwns);assert.equal(posted,1);assert(guards.strictRevision&&guards.isCurrent()&&guards.admissionCurrent());
 s.manualSelection={start:4.4,end:7.3};assert(!guards.admissionCurrent());s.manualSelection={...owner.range};s.projectViewToken++;assert(!guards.isCurrent());
 s.projectViewToken--;s.project={...p,revision:p.revision+1};assert(!guards.isCurrent());s.project=p;stillOwns=false;assert(!guards.isCurrent());
 await env.commitTrackLift(owner,d,()=>false);await env.commitTrackLift({...owner,track:N},d,()=>true);assert.equal(posted,1);});
