const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const plain = value => JSON.parse(JSON.stringify(value));
const source = fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8')
  .replace(/^import .*;\r?\n/gm,'').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/,'');

function app() {
  const nodes = new Map();
  const element = (id='') => {
    const nested = new Map();
    return {id,value:'',dataset:{},hidden:false,attrs:{},listeners:{},style:{setProperty(){}},
      classList:{add(){},remove(){},toggle(){}},
      replaceChildren(...children){this.children=children;},
      setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},
      addEventListener(key,fn){this.listeners[key]=fn;},
      querySelector(key){if(!nested.has(key))nested.set(key,element(key));return nested.get(key);},
      querySelectorAll(){return [];},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;},
    };
  };
  const document = {body:{tagName:'BODY'},activeElement:null,getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-tracks.js','layer-selection.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
  run(source);
  run(`cacheElements();
    state.project={id:'p',name:'Sequence test',revision:7,settings:{fps:30},
      sources:{A:{duration:20,has_audio:true,fps:30},B:{duration:30,has_audio:true}},
      manual:{source_mixer:{audio_slot:'B'},crop:{A:{x:.5}}},
      analysis:{audio_source:'B',audio_timeline_offset:0,transcript:{segments:[{id:'s',start:6,end:8,text:'Speech'}]}},
      draft:{keep_ranges:[{start:4,end:7},{start:14,end:17}],cuts:[{start:0,end:4},{start:7,end:14},{start:17,end:20}],output_duration:6},
      editor_sequence:{duration:6,active:false,sequence:{duration:6,camera_plan:[{start:0,end:6,camera:'stacked'}]},
        source_tracks:{A:[{id:'a1',start:0,end:3,source_start:4},{id:'a2',start:3,end:6,source_start:14}],
          B:[{id:'b1',start:0,end:6,source_start:6}]}}};
    state.studio.open=true;
    globalThis.requests=[];globalThis.selections=[];globalThis.seeks=[];globalThis.messages=[];
    globalThis.savedRevision=7;globalThis.renderCount=0;globalThis.flushCount=0;
    state.timeline={playhead:1,tool:'select',cancelPendingCut(){},setEditTarget(){},
      selectRange(start,end){state.manualSelection={start,end};selections.push({start,end});},
      clearSelection(){state.manualSelection=null;},setProject(){},draw(){}};
    globalThis.realRenderManualControls=renderManualControls;
    renderManualControls=renderSourceMixer=renderReadiness=hydrateSettings=hydrateSourceMixerLayout=highlightTranscriptSelection=()=>{};
    renderDraft=()=>renderCount++;
    pausePreview=pauseAllMedia=()=>{state.preview.playing=false;};
    previewTimelineTime=()=>state.timeline.playhead;
    seekSourcePreview=time=>seeks.push(time);
    openStudioTab=()=>true;
    toast=message=>messages.push(message);
    flushProjectSaves=async()=>{flushCount++;};
    saveQueueFor=()=>({revision:savedRevision});
    rememberProjectRevision=project=>savedRevision=project.revision;
    api=async(url,options)=>{requests.push({url,...options,body:options?.body?JSON.parse(options.body):null});
      return {project:{...state.project,revision:state.project.revision+1}};};
  `);
  return {run,nodes,context};
}



const MID='media_'+'a'.repeat(32), AID='media_'+'b'.repeat(32), TID='text_'+'c'.repeat(32);
function groups(){const h=app();h.run(`
 globalThis.ids=${JSON.stringify([MID,AID,TID])};
 state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10},a:{id:'a',kind:'audio',status:'ready',duration:10}};
 state.project.manual.media_clips=[{id:ids[0],asset_id:'v',start:1.123456789,end:3.23456789,source_start:1,video_source_start:2,speed:.5,motion:'pan',fade_in:.2,fade_out:.2,enabled:false},{id:ids[1],asset_id:'a',start:.5,end:2,source_start:3,speed:1,volume_db:-7.5}];
 state.project.manual.text_clips=[{id:ids[2],start:1.123456,end:3.234567,text:'Saved title',kind:'caption',style:'boxed',scale:125,template:'lower_third',subtext:'Second line'}];
 globalThis.members=[...ids];state.timeline.mediaSelection=ids[0];
 state.timeline.selectedMediaIds=()=>[...members];state.timeline.setMediaSelection=(next,primary)=>{members=[...next];state.timeline.mediaSelection=primary||null;};
 state.timeline.playhead=2;state.timeline.onMediaAction=editLayerAction;
 globalThis.mediaFlush=0;globalThis.textFlush=0;globalThis.previewCount=0;globalThis.groupPreviews=[];
 updateMediaPreview=()=>previewCount++;
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){},select(id){this.selected=id;},previewGroup:p=>groupPreviews.push(['media',p])};
 state.textStudio={flush:async()=>{textFlush++;return true;},render(){},select:async id=>{state.textStudio.selected=id;return true;},previewGroup:p=>groupPreviews.push(['text',p])};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});
 const plan=planLayerGroupDuplicate(state.project,body.clip_ids,body.start),created=[];
 const clone=rows=>[...rows,...rows.filter(row=>body.clip_ids.includes(row.id)).map(row=>{const at=plan.copies.find(item=>item.source_id===row.id),id=row.id.slice(0,row.id.indexOf('_')+1)+(row.id.endsWith('a')?'d':row.id.endsWith('b')?'e':'f').repeat(32);created.push({source_id:row.id,clip_id:id});return {...row,id,start:at.start,end:at.end};})];
 return {project:{...state.project,revision:state.project.revision+1,manual:{...state.project.manual,media_clips:clone(state.project.manual.media_clips),text_clips:clone(state.project.manual.text_clips)}},created};};
 `);return h;}


function bindMain(h){const start=source.indexOf('  elements.clipDuplicate.addEventListener("click",');const end=source.indexOf('\n  });',start);assert.ok(start>0&&end>start);h.run(source.slice(start,end+6));return h.nodes.get('clipDuplicate').listeners.click;}
const createdIds=['media_'+'d'.repeat(32),'media_'+'e'.repeat(32),'text_'+'f'.repeat(32)];
test('existing main Duplicate copies the whole arrangement in one strict legacy transaction and selects only verified new IDs',async()=>{
 const h=groups(),{run}=h;run('globalThis.before=JSON.stringify(state.project);state.manualSelection={start:0,end:6};selectedTimelineClip=()=>{throw Error("no source fallback")};');
 assert.ok(await bindMain(h)());assert.deepEqual(plain(run('requests[0].body')),{action:'layers_duplicate',clip_ids:[MID,AID,TID],start:2,expected_revision:7});
 const before=JSON.parse(run('before')),after=plain(run('state.project'));assert.deepEqual(after.manual.media_clips.slice(0,2),before.manual.media_clips);assert.deepEqual(after.manual.text_clips.slice(0,1),before.manual.text_clips);
 for(const key of ['sources','assets','settings','editor_sequence','draft','analysis'])assert.deepEqual(after[key],before[key]);
 assert.deepEqual(plain(run('members')),createdIds);assert.equal(run('state.timeline.mediaSelection'),createdIds[0]);assert.equal(run('state.manualSelection'),null);
 assert.equal(run('requests.length'),1);assert.equal(run('mediaFlush'),1);assert.equal(run('textFlush'),1);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);assert.ok(run('previewCount')>0);
});
test('group dispatch and main routing never invoke singular duplicate or source commands',async()=>{for(const entry of ['editLayerAction("layers_duplicate",{clip_ids:ids,start:2})','duplicateTimelineSelection(2)']){const {run}=groups();run('duplicateTimelineLayer=()=>{throw Error("singular fallback")};');assert.ok(await run(entry));assert.equal(run('requests[0].body.action'),'layers_duplicate');}});
test('earliest member anchors one frame-quantized placement and same-position is still a real copy',async()=>{for(const [at,expected] of [[2.516,2.5],[.5,.5]]){const {run}=groups();assert.ok(await run(`duplicateTimelineLayerGroup(ids,${at})`));assert.equal(run('requests[0].body.start'),expected);assert.equal(run('state.project.manual.media_clips.length'),4);assert.equal(run('state.project.manual.media_clips[2].source_start'),1);assert.equal(run('state.project.manual.media_clips[2].video_source_start'),2);assert.equal(run('state.project.manual.media_clips[2].enabled'),false);}});
for(const setup of ['state.manualEditBusy=true','state.transcriptSaving=true','state.captionDirty=true','state.captionContextSave=true','state.timeline.gesture={kind:"media_group"}','state.timeline.scrubbing=true','state.timeline.libraryDragActive=true','state.timeline.mediaSelectionPending=true','state.timeline.mediaSourceOpening=true','state.timeline.trackLockPending=true','state.timeline.editPending=true','state.chromaStudio={projectId:"p",pendingDrafts:()=>[{slot:"A",issue:"Apply Chroma draft first"}]}'])test('group duplicate refuses pending context: '+setup,async()=>{const {run}=groups();run(setup);assert.ok(run('layerGroupDuplicateIssue(ids,2)'));assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.length'),0);assert.deepEqual(plain(run('members')),[MID,AID,TID]);});
for(const at of ['-1','5','NaN','Infinity','true','null'])test('whole group destination must fit without clamp: '+at,async()=>{const {run}=groups();const before=run('JSON.stringify(state.project)');assert.equal(await run(`duplicateTimelineLayerGroup(ids,${at})`),null);assert.equal(run('requests.length'),0);assert.equal(run('JSON.stringify(state.project)'),before);});
for(const setup of ['state.textStudio.flush=async()=>false','state.mediaStudio.flush=async()=>false','state.textStudio.flush=async()=>{members=ids.slice(1);return true;}','state.textStudio.flush=async()=>{state.projectViewToken=99;return true;}','state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start++;return true;}','flushProjectSaves=async()=>{state.timeline.gesture={};}','flushProjectSaves=async()=>{state.project.assets.v.path="changed";}','flushProjectSaves=async()=>{state.project.settings.fps=24;}','state.textStudio.flush=async()=>{state.project.id="other";return true;}','state.textStudio.flush=async()=>{elements.advancedPanel.dataset.aiRequestContext="editor";return true;}'])test('preflush changes abort the pinned selection/destination: '+setup,async()=>{const {run}=groups();run(setup);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.length'),0);});
test('two clicks waiting on inspector flush admit at most one copy command',async()=>{const {run}=groups();run('let release;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>wait;globalThis.first=duplicateTimelineLayerGroup(ids,2);globalThis.second=duplicateTimelineLayerGroup(ids,2);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
test('copy destination stays pinned if transport clock changes during a pending save',async()=>{const {run}=groups();run('state.preview.playing=true;state.textStudio.flush=async()=>{if(state.preview.playing)throw Error("not paused");state.timeline.playhead=3;return true;}');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('requests[0].body.start'),2);assert.equal(run('state.timeline.playhead'),3);assert.equal(run('seeks.length'),0);});
test('real revision refusal refreshes once, preserves originals and never replays legacy copy',async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('requests.length'),2);assert.equal(run('state.project.revision'),15);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.match(run('messages.at(-1)'),/copy destination/);});
for(const setup of ['elements.advancedPanel.dataset.aiRequestContext="editor"','members=ids.slice(1)','state.preview.mode="source"'])test('late accepted same-view copy updates saved scene without taking newer selection/pane/clock: '+setup,async()=>{const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${setup};state.timeline.playhead=4;return result;};`);assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('state.project.revision'),8);assert.equal(run('state.project.manual.media_clips.length'),4);assert.notDeepEqual(plain(run('members')),createdIds);assert.equal(run('state.timeline.playhead'),4);assert.equal(run('seeks.length'),0);assert.equal(run('renderCount'),0);});
for(const setup of ['state.projectViewToken=88','state.project={...state.project,id:"other"}'])test('late success leaves a different project/view untouched: '+setup,async()=>{const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${setup};return result;};`);assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('state.project.revision'),7);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.equal(run('previewCount'),0);});
test('older accepted copy does not replace newer same-view state or select stale copies',async()=>{const {run}=groups();run('const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);state.project={...state.project,revision:20,name:"Newer"};return result;};');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('state.project.revision'),20);assert.equal(run('state.project.name'),'Newer');assert.deepEqual(plain(run('members')),[MID,AID,TID]);});
for(const change of ['delete result.created','result.created=[]','result.created[0].clip_id=ids[0]','result.created[1].source_id=ids[0]','result.project.id="foreign"','result.project.revision=7','result.project.manual.media_clips[2].source_start=99','result.project.manual.media_clips[0].volume_db=99','result.project.manual.media_clips.push({...result.project.manual.media_clips[2],id:"media_"+"9".repeat(32)})'])test('unverified copy receipt is never installed/selected: '+change,async()=>{const {run}=groups();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${change};return result;};`);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.length'),1);assert.equal(run('state.project.revision'),7);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.match(run('messages.at(-1)'),/copy response|invalid project/);});
test('failure keeps original group and allows one deliberate retry',async()=>{const {run}=groups();run('const originalApi=api;globalThis.retryApi=originalApi;api=async()=>{throw Error("offline")};');assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.deepEqual(plain(run('members')),[MID,AID,TID]);run('api=retryApi');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.deepEqual(plain(run('members')),createdIds);});
test('main readiness, pending release and explicit-draft recovery are truthful without rebuilding editor',()=>{const {run,nodes}=groups();run('renderDuplicateAvailability(2)');assert.equal(nodes.get('clipDuplicate').disabled,false);assert.match(nodes.get('clipDuplicate').textContent,/3 clips/);assert.equal(nodes.get('clipDuplicate').attrs['aria-describedby'],'layerGroupDuplicateHelp');run('state.timeline.mediaSelectionPending=true;renderLayerGroupControls(2)');assert.equal(nodes.get('clipDuplicate').disabled,true);run('state.timeline.mediaSelectionPending=false;renderLayerGroupControls(2)');assert.equal(nodes.get('clipDuplicate').disabled,false);run('state.captionDirty=true;renderProjectSaveState()');assert.equal(nodes.get('clipDuplicate').disabled,true);run('state.captionDirty=false;renderProjectSaveState()');assert.equal(nodes.get('clipDuplicate').disabled,false);assert.equal(run('renderCount'),0);});
test('Full source published readiness uses mapped edited playhead, not original time',()=>{const {run,nodes}=groups();run('elements.studioPanelFraming.hidden=true;publishPreviewPlayhead(18,2)');assert.equal(nodes.get('clipDuplicate').disabled,false);run('publishPreviewPlayhead(18,5)');assert.equal(nodes.get('clipDuplicate').disabled,true);assert.equal(run('requests.length'),0);});
test('group copy adds no profile shortcut, toolbar clone, or speculative preview mutation',()=>{assert.match(source,/mediaGroupDuplicateIssue: layerGroupDuplicateIssue/);assert.match(source,/data-group-duplicate aria-describedby="layerGroupDuplicateHelp"/);assert.match(source,/verifyLayerGroupDuplicate\(copyBefore,payload.project,detail.clip_ids,detail.start,payload.created\)/);const keys=fs.readFileSync(path.join(__dirname,'../web/keyboard.js'),'utf8');assert.doesNotMatch(keys,/duplicate/);});

for(const setup of ['elements.advancedPanel.dataset.aiRequestContext="editor"','members=ids.slice(1)','state.preview.mode="source"'])test('late409 refresh cannot hijack a newer pane/selection/clock: '+setup,async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){${setup};state.timeline.playhead=4;const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('state.project.revision'),15);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);assert.equal(run('state.timeline.playhead'),4);assert.notDeepEqual(plain(run('members')),createdIds);assert.match(run('messages.at(-1)'),/not repeated/);});

test('same-membership primary change during preflush cancels old copy admission',async()=>{const {run}=groups();run('state.textStudio.flush=async()=>{state.timeline.mediaSelection=ids[1];return true;}');assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.length'),0);assert.equal(run('state.timeline.mediaSelection'),AID);});
test('newer same-group primary after admission is not replaced by the old copy selection',async()=>{const {run}=groups();run('const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);state.timeline.mediaSelection=ids[1];return result;};');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('state.project.revision'),8);assert.deepEqual(plain(run('members')),[MID,AID,TID]);assert.equal(run('state.timeline.mediaSelection'),AID);});

test('clock-only seek during refused POST retains the current cursor without replay/rebuild',async()=>{const {run}=groups();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){state.timeline.playhead=4;const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('state.project.revision'),15);assert.equal(run('state.timeline.playhead'),4);assert.equal(run('seeks.length'),0);assert.equal(run('renderCount'),0);});
for(const draft of ['[]','"broken"','true','null'])test('retained or malformed draft cannot offer grouped Duplicate: '+draft,async()=>{const {run,nodes}=groups();run(`state.project.draft=${draft};renderDuplicateAvailability(2)`);assert.equal(nodes.get('clipDuplicate').disabled,true);assert.equal(await run('duplicateTimelineLayerGroup(ids,2)'),null);assert.equal(run('requests.length'),0);});
function focusHarness(){const h=groups();h.run(`globalThis.focusEvents=new Map();globalThis.frames=[];globalThis.focused=0;requestAnimationFrame=fn=>frames.push(fn);document.addEventListener=(type,fn)=>focusEvents.set(type,fn);document.removeEventListener=(type,fn)=>{if(focusEvents.get(type)===fn)focusEvents.delete(type)};window.addEventListener=(type,fn)=>focusEvents.set(type,fn);window.removeEventListener=document.removeEventListener;globalThis.owner={isConnected:true,hidden:false,disabled:false,getClientRects:()=>[{}],focus(options){focused++;document.activeElement=this;globalThis.focusOptions=options}};document.activeElement=owner;globalThis.finishFocus=ownGroupDuplicateFocus(owner);document.activeElement=document.body;`);return h;}
test('duplicate completion restores only its own lost-to-body button focus after readiness settles',()=>{const {run}=focusHarness();run('finishFocus(true)');assert.equal(run('focused'),0);run('frames.shift()()');assert.equal(run('focused'),1);assert.deepEqual(plain(run('focusOptions')),{preventScroll:true});assert.equal(run('focusEvents.size'),0);});
for(const setup of ['focusEvents.get("pointerdown")({target:owner})','focusEvents.get("keydown")({key:"Tab"})','focusEvents.get("focusin")({target:{}})','focusEvents.get("blur")({})','state.projectViewToken++','state.project={...state.project,id:"other"}','elements.advancedPanel.dataset.aiRequestContext="editor"','owner.isConnected=false','owner.hidden=true','owner.disabled=true','owner.getClientRects=()=>[]','document.activeElement={}'])test('duplicate focus never steals newer interaction/navigation: '+setup,()=>{const {run}=focusHarness();run(setup+';finishFocus(true);frames.shift()();');assert.equal(run('focused'),0);assert.equal(run('focusEvents.size'),0);});
test('failed duplicate focus ownership always cleans up without refocusing',()=>{const {run}=focusHarness();run('finishFocus(false);frames.shift()();');assert.equal(run('focused'),0);assert.equal(run('focusEvents.size'),0);});
test('main native button passes its current focus owner to successful group action',async()=>{const h=groups(),{run}=h;run('globalThis.focusOwner=null;duplicateTimelineLayerGroup=async(ids,start,options)=>{focusOwner=options.focusOwner;return true};');const button=h.nodes.get('clipDuplicate');assert.equal(await bindMain(h)({currentTarget:button}),true);assert.equal(run('focusOwner'),button);});

test('owned successful copy reveals its mapped primary row without seek or zoom change',async()=>{const {run}=groups();run('globalThis.reveals=[];state.timeline.revealMedia=id=>reveals.push(id);state.timeline.scroll={scrollTop:0,scrollLeft:20,clientHeight:300,clientWidth:800};state.timeline.zoom=2;');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.deepEqual(plain(run('reveals')),[createdIds[0]]);assert.equal(run('state.timeline.zoom'),2);assert.equal(run('seeks.length'),0);});
for(const change of ['state.timeline.scroll.scrollTop=25','state.timeline.scroll.scrollLeft=40','state.timeline.scroll.clientHeight=400','state.timeline.zoom=3','state.timeline.playhead=4'])test('newer viewport/clock navigation prevents automatic copy-row reveal: '+change,async()=>{const {run}=groups();run(`globalThis.reveals=[];state.timeline.revealMedia=id=>reveals.push(id);state.timeline.scroll={scrollTop:0,scrollLeft:20,clientHeight:300,clientWidth:800};state.timeline.zoom=2;const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${change};return result;};`);assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('reveals.length'),0);assert.equal(run('seeks.length'),0);});

test('copy-row reveal waits for scheduled canvas height instead of clamping into old extent',async()=>{const {run}=groups();run('globalThis.reveals=[];globalThis.frames=[];requestAnimationFrame=fn=>frames.push(fn);state.timeline.revealMedia=id=>reveals.push(id);');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));assert.equal(run('reveals.length'),0);run('frames.splice(0).forEach(fn=>fn())');assert.deepEqual(plain(run('reveals')),[createdIds[0]]);});
for(const change of ['state.projectViewToken++','state.project.revision++','members=ids.slice(1)','elements.advancedPanel.dataset.aiRequestContext="editor"','state.timeline.playhead=4'])test('settlement-to-frame navigation cancels only the deferred copy reveal: '+change,async()=>{const {run}=groups();run('globalThis.reveals=[];globalThis.frames=[];requestAnimationFrame=fn=>frames.push(fn);state.timeline.revealMedia=id=>reveals.push(id);');assert.ok(await run('duplicateTimelineLayerGroup(ids,2)'));run(change+';frames.splice(0).forEach(fn=>fn());');assert.equal(run('reveals.length'),0);assert.equal(run('seeks.length'),0);});
