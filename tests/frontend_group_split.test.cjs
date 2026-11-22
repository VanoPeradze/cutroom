const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),{pathToFileURL}=require('node:url');
const lib=import(pathToFileURL(path.resolve(__dirname,'../web/group-split.js')).href);
const id=(p,s)=>p+'_'+s.repeat(32),a=id('media','1'),b=id('media','2'),c=id('text','3'),d=id('media','4'),u=id('media','5'),v=id('asset','6'),snd=id('asset','7'),img=id('asset','8');
const ids=[c,a,b],fresh=id=>id.replace(/.$/,'f'),h={undo_count:3,redo_count:2};
function project(){const mk=(id,asset_id,extra={})=>({id,asset_id,start:1.123456789,end:5.88,source_start:.7,speed:1,fade_in:.12,fade_out:.25,motion:'none',...extra});
 return {id:'project_at',revision:2,draft:{output_duration:10,status:'ready',camera:'keep'},editor_sequence:{duration:10},settings:{fps:30},sources:{A:{name:'Original'}},analysis:{text:'keep'},assets:{[v]:{id:v,kind:'video',duration:30,status:'ready'},[snd]:{id:snd,kind:'audio',duration:20,status:'ready'},[img]:{id:img,kind:'image',status:'ready'}},
 manual:{history:{...h},source_tracks:{A:[{start:0,end:10}]},media_clips:[mk(u,v,{start:6,end:7}),mk(a,v,{speed:.75,video_source_start:4.25,opacity_percent:57}),mk(b,snd,{enabled:false}),mk(d,img,{source_start:0})],text_clips:[{id:c,start:.8,end:5.1,text:'A title',style:'bold'}]}};}
function receipt(p,items=ids,frame=94){const q=structuredClone(p),t=Math.round(frame/p.settings.fps*1e9)/1e9,n=x=>Math.round(x*1e9)/1e9,created=[];
 for(const key of ['media_clips','text_clips'])q.manual[key]=q.manual[key].flatMap(old=>{
   if(!items.includes(old.id))return [old];const left={...old,end:t},right={...old,id:fresh(old.id),start:t};created.push({source_id:old.id,clip_id:right.id});
   if(key==='media_clips'){left.fade_out=0;right.fade_in=0;const kind=p.assets[old.asset_id].kind;if(kind!=='image')right.source_start=n(old.source_start+(t-old.start));if(kind==='video')right.video_source_start=n((old.video_source_start??old.source_start)+(t-old.start)*old.speed);}
   return [left,right];});q.revision++;q.draft.edited_at='now';q.manual.history={undo_count:Math.min(20,(p.manual.history?.undo_count||0)+1),redo_count:0};return {q,created};
}
for(const fps of [24,25,30,50,60])test('One exact common frame; raw clocks and order at '+fps+' fps',async()=>{const m=await lib,p=project();p.settings.fps=fps;const snapshot=structuredClone(p),frame=Math.round(3.137*fps),items=[b,c,a,d];const plan=m.planGroupSplit(p,items,frame),{q,created}=receipt(p,items,frame);assert.equal(m.groupSplitFrame(p,3.137),frame);assert.equal(plan.issue,'');assert.equal(plan.time,Math.round(frame/fps*1e9)/1e9);assert.deepEqual(p,snapshot);const r=m.verifyGroupSplit(p,q,items,frame,created.reverse());assert.equal(r.issue,'');assert.deepEqual(r.ids,items.map(fresh));assert.equal(r.mapping[c],fresh(c));});
for(const [name,mut,items=ids,frame=94]of [
 ['missing project',p=>delete p.id],['draft error',p=>p.editor_sequence.error='broken'],['unsupported fps',p=>p.settings.fps=29.97],['negative revision',p=>p.revision=-1],
 ['malformed empty history',p=>p.manual.history=[]],['negative history',p=>p.manual.history.undo_count=-1],['unknown redo count',p=>delete p.manual.history.redo_count],
 ['outside selected passage',()=>{},ids,20],['only edge',()=>{},ids,0],['after edit',()=>{},ids,400],['noninteger frame',()=>{},ids,94.2],['nonfinite frame',()=>{},ids,NaN],
 ['single',()=>{},[a]],['repeated',()=>{},[a,a]],['wrong identifier',()=>{},[v,c]],['missing row',()=>{},[a,id('text','9')]],['too many selected',()=>{},Array(201).fill(a)],
 ['invalid asset membership',p=>p.assets[v].id=snd],['unready source',p=>p.assets[snd].status='missing'],['unknown file type',p=>p.assets[snd].kind='generated'],
 ['animated picture',p=>p.manual.media_clips[1].motion='pan'],['audio enters fade',p=>p.manual.media_clips[2].fade_in=2.5],['audio leaves fade',p=>p.manual.media_clips[2].fade_out=3],
 ['text starts afterwards',p=>p.manual.text_clips[0].start=3.5],['too little left',p=>p.manual.text_clips[0].start=3.1],['too little right',p=>p.manual.text_clips[0].end=3.16],
 ['chapter title built-in fade',p=>p.manual.text_clips[0].template='chapter'],['ambiguous ID',p=>p.manual.media_clips.push({...p.manual.media_clips[0]})],
 ['unknown track model',p=>p.manual.layer_tracks={version:88,tracks:[]}],['bad picture origin',p=>p.manual.media_clips[1].video_source_start=NaN],['nonfinite bounds',p=>p.manual.text_clips[0].end=NaN],
 ['whole selection exceeds media limit',p=>{while(p.manual.media_clips.length<200){const j=p.manual.media_clips.length;p.manual.media_clips.push({...p.manual.media_clips[0],id:'media_'+(300+j).toString(16).padStart(32,'0')});}}]
])test('Atomic split refused before save: '+name,async()=>{const m=await lib,p=project();mut(p);const same=structuredClone(p);assert.ok(m.planGroupSplit(p,items,frame).issue);assert.deepEqual(p,same);});
for(const [name,mut]of [
 ['wrong revision',(q)=>q.revision++],['wrong project',q=>q.id='somewhere'],['history did not advance',q=>q.manual.history.undo_count=3],['redo retained',q=>q.manual.history.redo_count=1],['bad history keys',q=>q.manual.history.extra=0],
 ['original source',q=>q.sources.A.name='X'],['edit fps',q=>q.settings.fps=60],['primary camera',q=>q.manual.source_tracks.A[0].end=9],['other geometry',q=>q.editor_sequence.duration=11],['draft content',q=>q.draft.camera='other'],
 ['changed unselected occurrence',q=>q.manual.media_clips[0].enabled=false],['reordered selected pieces',q=>q.manual.media_clips.reverse()],['extra piece',q=>q.manual.text_clips.push({...q.manual.text_clips[0]})],
 ['right audio phase',q=>q.manual.media_clips.find(r=>r.id===fresh(b)).source_start+=.01],['right picture phase',q=>q.manual.media_clips.find(r=>r.id===fresh(a)).video_source_start+=1],
 ['opacity discarded',q=>delete q.manual.media_clips.find(r=>r.id===fresh(a)).opacity_percent],['text restyled',q=>q.manual.text_clips[1].style='plain'],['old ID lost',q=>q.manual.text_clips[0].id=fresh(c)],
 ['extra receipt entry',(_q,r)=>r.push({...r[0]})],['source repeated',(_q,r)=>r[1]={...r[0]}],['incorrect kind',(_q,r)=>r[0].clip_id=fresh(c)],['reused original ID',(_q,r)=>r[0].clip_id=u],['unknown extra receipt field',(_q,r)=>r[0].extra=true],
 ])test('Do not accept a mismatched save: '+name,async()=>{const m=await lib,p=project(),{q,created}=receipt(p);mut(q,created);assert.ok(m.verifyGroupSplit(p,q,ids,94,created).issue);});
test('Legacy missing history can start one empty Undo stack; configured Undo ceiling stays 20',async()=>{const m=await lib;for(const n of [undefined,20]){const p=project();if(n==null)delete p.manual.history;else p.manual.history.undo_count=n;const {q,created}=receipt(p);assert.equal(m.verifyGroupSplit(p,q,ids,94,created).issue,'');}});
test('Real toolbar, current keymap Split and group inspector converge on the same atomic command (not a series of single edits)',()=>{const s=fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8');assert.match(s,/data-group-split="playhead"/);assert.match(s,/manualSplit\.addEventListener\("click", \(\) => splitTimelineSelection\(\)\)/);assert.match(s,/else if\(action==="split"\)void splitTimelineSelection\(\)/);assert.match(s,/const ids=selectedLayerGroupIds\(\);if\(ids.length\)return splitTimelineLayerGroup\(ids,time\)/);});

// Exercise the real host functions, including admission/late-response ownership.
const hostSource=fs.readFileSync(path.resolve(__dirname,'../web/app.js'),'utf8').split('function groupSplitIssue(own=null){')[1].split('function groupSelectionIssue()')[0];
async function harness(){
 const m=await lib,p=project(),log={requests:[],notices:[],selected:[],times:[],draws:0},tl={project:p,playhead:3.133333333,mediaSelection:c,selected:[...ids],
 setMediaSelection(x,primary){this.selected=[...x];this.mediaSelection=primary;log.selected.push([...x]);},scheduleDraw(){log.draws++;}};
 const state={project:p,projectViewToken:7,timeline:tl,studio:{open:true},preview:{playing:false,mode:'edit'},mediaStudio:{render(){}},activeUploads:new Set(),jobStartLocks:new Set(),groupSplitFences:new Map(),manualEditBusy:false};
 const cfg={target:'edit',source:'',range:false,pane:'group',gesture:false,status:{kind:'saved'},during:null,rejected:null,changeReceipt:null,newer:false};
 const deps={state,structuredClone,console,Map,Number,Set,Math,JSON,Promise,Boolean,Object,Array,Error,encodeURIComponent,
 planGroupSplit:m.planGroupSplit,verifyGroupSplit:m.verifyGroupSplit,groupSplitFrame:m.groupSplitFrame,
 previewUsesSourceTime:()=>state.preview.mode!=='edit',activeEditTarget:()=>cfg.target,selectedLayerGroupIds:()=>tl.selected,
 document:{querySelector:()=>cfg.dialog||null,documentElement:{classList:{contains:()=>cfg.gesture}}},
 previewRepairBusy:()=>false,projectCopySourceBusy:()=>false,rangeInputPending:()=>cfg.range,foregroundBusy:()=>state.manualEditBusy||!!cfg.foreground,
 sourceMonitorIssue:()=>cfg.source,projectSaveStatus:()=>cfg.status,hasUnsavedProjectWork:()=>!!cfg.unsaved,layerGroupDuplicateContext:()=>cfg.pane,
 editorProject:()=>state.project,renderReadiness(){},renderManualControls(){},renderProjectSaveState(){},rememberProjectRevision(){},updateMediaPreview(){},
 previewTimelineTime:()=>tl.playhead,toast:t=>log.notices.push(t),api:async(url,req)=>{
   const body=JSON.parse(req.body);log.requests.push({url,...body});
   assert.equal(state.manualEditBusy,true);assert.equal(req.method,'POST');
   if(cfg.during)await cfg.during();if(cfg.rejected)throw cfg.rejected;
   const {q,created}=receipt(p,ids,94);if(cfg.changeReceipt)cfg.changeReceipt(q,created);return {project:q,created};
 }};
 const e=vm.runInNewContext('function groupSplitIssue(own=null){'+hostSource+'\n;({groupSplitIssue,splitTimelineLayerGroup,groupSplitAvailability})',deps);
 return {e,tl,state,cfg,log,p};
}
test('Host sends exactly one revision-bound POST at the displayed frame, selects verified right primary, and does not seek or flush',async()=>{const {e,state,tl,log}=await harness();const r=await e.splitTimelineLayerGroup(ids);assert.equal(r.revision,3);assert.equal(state.project.revision,3);assert.equal(log.requests.length,1);assert.deepEqual(log.requests[0],{url:'/api/projects/project_at/manual/edit',action:'layers_split',clip_ids:ids,frame:94,expected_revision:2});assert.deepEqual(tl.selected,ids.map(fresh));assert.equal(tl.mediaSelection,fresh(c));assert.equal(tl.playhead,3.133333333);assert.equal(state.manualEditBusy,false);assert.equal(state.manualEditPromise,null);});
for(const [name,flag]of [['source mode',h=>h.state.preview.mode='source'],['source A target',h=>h.cfg.target='A'],['playing',h=>h.state.preview.playing=true],['gesture',h=>h.tl.gesture={}],['editing numeric',h=>h.cfg.gesture=true],['typed range',h=>h.cfg.range=true],['pending settings',h=>h.cfg.status={kind:'saving',detail:'Saving settings'}],['incomplete caption',h=>h.cfg.source='Save caption'],['other unsaved input',h=>h.cfg.unsaved=true],['another pending request',h=>h.state.groupSplitPending={}],['open modal',h=>h.cfg.dialog={}],['stale revision',h=>h.tl.project={...h.p,revision:1}],['moved clock',h=>h.tl.playhead=1],['new membership',h=>h.tl.selected=[c,a,d]],['malformed history',h=>h.p.manual.history=[]],['membership changed when cut cancelled',h=>h.tl.cancelPendingCut=()=>{h.tl.selected=[a,b]}]]){
 test('Host will not post through '+name,async()=>{const h=await harness();flag(h);const r=await h.e.splitTimelineLayerGroup(ids);assert.equal(r,null);assert.equal(h.log.requests.length,0);assert.equal(h.log.selected.length,0);});
}
for(const [name,change]of [['new pane',h=>h.cfg.pane='media'],['changed selection',h=>{h.tl.mediaSelection=b;h.tl.selected=[b,d]}],['new playhead frame',h=>h.tl.playhead=4],['playing now',h=>h.state.preview.playing=true],['inspecting source',h=>h.state.preview.mode='source']]){
 test('A confirmed late save never steals '+name,async()=>{const h=await harness();h.cfg.during=()=>change(h);const r=await h.e.splitTimelineLayerGroup(ids);assert.equal(r.revision,3);assert.equal(h.state.project.revision,3);assert.equal(h.log.selected.length,0);});
}
for(const [name,mut]of [['lost response',h=>h.cfg.rejected=new Error('lost')],['conflict',h=>h.cfg.rejected=Object.assign(new Error('stale'),{status:409})],['incomplete receipt',h=>h.cfg.changeReceipt=(_q,r)=>r.pop()],['unexpected source change',h=>h.cfg.changeReceipt=q=>q.sources.A.name='different']]){
 test('Uncertain save fenced until reopen, no automatic or second POST: '+name,async()=>{const h=await harness();mut(h);assert.equal(await h.e.splitTimelineLayerGroup(ids),null);assert.equal(await h.e.splitTimelineLayerGroup(ids),null);assert.equal(h.log.requests.length,1);assert.equal(h.state.project,h.p);assert.equal(h.log.selected.length,0);assert.ok(h.state.groupSplitFences.has(h.p.id));});
}
test('Known validation rejection is not presented as a save',async()=>{const h=await harness();h.cfg.rejected=Object.assign(new Error('clip locked'),{status:422});assert.equal(await h.e.splitTimelineLayerGroup(ids),null);assert.equal(h.state.groupSplitFences.size,0);assert.equal(h.state.project,h.p);assert.match(h.log.notices.at(-1),/clip locked/);});
test('A reply to an old project is verified but cannot replace the visible project',async()=>{const h=await harness(),other={...project(),id:'another',revision:8};h.cfg.during=()=>{h.state.project=other;h.state.projectViewToken++};const r=await h.e.splitTimelineLayerGroup(ids);assert.equal(r?.revision,3);assert.equal(h.state.project,other);assert.equal(h.log.selected.length,0);});
