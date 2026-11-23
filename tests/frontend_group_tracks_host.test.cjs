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
  const document = {createElement:tag=>element(tag),body:{tagName:'BODY'},activeElement:null,getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-tracks.js','layer-selection.js','layer-group-tracks.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^import .*;\r?\n/gm,'').replace(/^export /gm,''));
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

const MID='media_'+'a'.repeat(32), RID='media_'+'b'.repeat(32), TXT='text_'+'c'.repeat(32),lane=n=>'track_'+String(n).repeat(32);
function group(){const h=app();h.run(`
 globalThis.ids=${JSON.stringify([MID,RID])};globalThis.lanes=${JSON.stringify([lane(1),lane(2),lane(3),lane(4),lane(5)])};
 state.project.assets={v:{kind:'video',status:'ready',duration:20,path:'media/a.mp4'}};
 const clip=(id,track_id,start,end)=>({id,track_id,asset_id:'v',start,end,source_start:1.23456789,video_source_start:2.123456789,speed:.5,motion:'pan',fade_in:.1,fade_out:.2,enabled:false,muted:true,volume_db:-7.25,role:'effects',fit:'cover',x:.15,y:.2,w:.8,h:.7});
 state.project.manual.layer_tracks={version:2,tracks:lanes.map((id,i)=>({id,kind:'visual',name:'Picture '+i,locked:false}))};
 state.project.manual.media_clips=[clip(ids[0],lanes[0],1.123456789123,3.234567891234),clip(ids[1],lanes[2],1.4,3.5)];state.project.manual.text_clips=[];
 globalThis.members=[...ids];state.timeline.mediaSelection=ids[0];state.timeline.selectedMediaIds=()=>[...members];state.timeline.setMediaSelection=(next,primary)=>{members=[...next];state.timeline.mediaSelection=primary||null;};
 state.timeline.playhead=2;globalThis.mediaFlush=0;globalThis.textFlush=0;globalThis.pauseCount=0;globalThis.groupPreviews=[];globalThis.previewCount=0;globalThis.reveals=[];
 state.timeline.scroll={scrollTop:0,scrollLeft:20,clientHeight:300,clientWidth:800};state.timeline.zoom=2;state.timeline.revealMedia=id=>reveals.push(id);
 updateMediaPreview=()=>previewCount++;pauseAllMedia=()=>{pauseCount++;state.preview.playing=false;};
 state.mediaStudio={flush:async()=>{mediaFlush++;return true;},render(){},previewGroup:p=>groupPreviews.push(['media',p])};
 state.textStudio={flush:async()=>{textFlush++;return true;},render(){},previewGroup:p=>groupPreviews.push(['text',p])};
 api=async(url,options)=>{const body=JSON.parse(options.body);requests.push({url,body});const plan=planLayerGroupRelocate(state.project,body.clip_ids,body.anchor_id,body.track_id,body.delta);if(plan.issue)throw Error(plan.issue);
 const project=JSON.parse(JSON.stringify(state.project));project.revision++;for(const key of ['media_clips','text_clips'])project.manual[key]=project.manual[key].map(row=>{const p=plan.patches.find(x=>x.clip_id===row.id);return p?{...row,start:p.start,end:p.end,track_id:p.track_id}:row;});return {project};};
 `);return h;}

test('one strict vertical transaction preserves exact fractional clocks, IDs, order and primary',async()=>{
 const {run}=group();const before=plain(run('state.project'));assert.ok(await run('relocateTimelineLayerGroup(ids,ids[1],0,lanes[3])'));
 assert.deepEqual(plain(run('requests[0].body')),{action:'layers_relocate',clip_ids:[MID,RID],anchor_id:RID,track_id:lane(4),delta:0,expected_revision:7});
 const after=plain(run('state.project'));for(let i=0;i<2;i++){assert.deepEqual({...after.manual.media_clips[i],track_id:before.manual.media_clips[i].track_id},before.manual.media_clips[i]);}
 for(const key of ['layer_tracks','source_mixer','crop','text_clips'])assert.deepEqual(after.manual[key],before.manual[key]);
 for(const key of ['sources','assets','settings','analysis','draft','editor_sequence'])assert.deepEqual(after[key],before[key]);
 assert.deepEqual(plain(run('members')),[MID,RID]);assert.equal(run('state.timeline.mediaSelection'),MID);assert.equal(run('state.timeline.playhead'),2);
 assert.equal(run('requests.length'),1);assert.equal(run('textFlush'),1);assert.equal(run('mediaFlush'),1);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);assert.deepEqual(plain(run('reveals')),[MID]);
});
test('body action routes to relocation, not horizontal or singular fallback',async()=>{const {run}=group();run('moveTimelineLayerGroup=()=>{throw Error("fallback")};');assert.ok(await run('editLayerAction("layers_relocate",{clip_ids:ids,anchor_id:ids[0],track_id:lanes[1],delta:.2})'));assert.equal(run('requests[0].body.action'),'layers_relocate');assert.equal(run('state.project.manual.media_clips[0].start'),1.323456789);});
test('exact unchanged placement is a no-write/no-pause no-op',async()=>{const {run}=group();assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[0])'));assert.equal(run('pauseCount'),0);assert.equal(run('requests.length'),0);});
for(const setup of ['state.manualEditBusy=true','state.transcriptSaving=true','state.captionDirty=true','state.captionContextSave=true','state.timeline.gesture={kind:"media_group"}','state.timeline.scrubbing=true','state.timeline.libraryDragActive=true','state.timeline.mediaSelectionPending=true','state.timeline.mediaSourceOpening=true','state.timeline.trackLockPending=true','state.timeline.editPending=true','state.mediaStudio.frameEditor={active:true}','state.chromaStudio={projectId:"p",pendingDrafts:()=>[{slot:"A",issue:"Apply Chroma draft first"}]}'])test('pending guard refuses relocation: '+setup,async()=>{const {run}=group();run(setup);assert.ok(run('layerGroupRelocateIssue(ids,ids[0],0,lanes[1])'));assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.equal(run('requests.length'),0);});
test('canonical drag preview remains usable during its owned gesture, commit refuses active gesture',async()=>{const {run}=group();run('state.timeline.gesture={kind:"media_group"}');assert.equal(run('layerGroupRelocatePlan(ids,ids[0],0,lanes[1]).issue'),'');assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);});
test('exact timeline-owned pending token admits one released drag, not a keyboard repeat',async()=>{const {run}=group();run('state.timeline.editPending=true;state.timeline.mediaGroupRelocationPending={projectId:"p",ids:[...ids],anchorId:ids[0],trackId:lanes[1],delta:0};');assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.ok(await run('editLayerAction("layers_relocate",{clip_ids:ids,anchor_id:ids[0],track_id:lanes[1],delta:0})'));assert.equal(run('requests.length'),1);});
for(const change of ['request.projectId="other"','request.ids=ids.slice(1)','request.anchorId=ids[1]','request.trackId=lanes[2]','request.delta=.1'])test('a different pending intent cannot bypass the input lock: '+change,async()=>{const {run}=group();run('state.timeline.editPending=true;globalThis.request=state.timeline.mediaGroupRelocationPending={projectId:"p",ids:[...ids],anchorId:ids[0],trackId:lanes[1],delta:0};'+change);assert.equal(await run('editLayerAction("layers_relocate",{clip_ids:ids,anchor_id:ids[0],track_id:lanes[1],delta:0})'),null);assert.equal(run('requests.length'),0);});
test('replaced timeline ownership during preflush cancels the prior request',async()=>{const {run}=group();run('state.timeline.editPending=true;state.timeline.mediaGroupRelocationPending={projectId:"p",ids:[...ids],anchorId:ids[0],trackId:lanes[1],delta:0};state.textStudio.flush=async()=>{state.timeline.mediaGroupRelocationPending={};return true;};');assert.equal(await run('editLayerAction("layers_relocate",{clip_ids:ids,anchor_id:ids[0],track_id:lanes[1],delta:0})'),null);assert.equal(run('requests.length'),0);});
for(const setup of ['state.project.manual.layer_tracks.tracks[0].locked=true','state.project.manual.layer_tracks.tracks[1].locked=true','delete state.project.manual.layer_tracks','state.project.assets.v.status="failed"','state.project.draft=[]','state.project.draft=null'])test('invalid/incompatible saved state refuses: '+setup,async()=>{const {run}=group();run(setup);assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.equal(run('requests.length'),0);});
test('intermediate locked lane is not a destination and does not block a jump',async()=>{const {run}=group();run('state.project.manual.layer_tracks.tracks[1].locked=true');assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[2])'));});
for(const setup of ['state.textStudio.flush=async()=>false','state.mediaStudio.flush=async()=>false','state.textStudio.flush=async()=>{members=ids.slice(1);return true;}','state.textStudio.flush=async()=>{state.projectViewToken++;return true;}','state.mediaStudio.flush=async()=>{state.project.manual.media_clips[0].source_start++;return true;}','flushProjectSaves=async()=>{state.timeline.gesture={};}','flushProjectSaves=async()=>{state.project.settings.fps=24;}','state.textStudio.flush=async()=>{state.timeline.mediaSelection=ids[1];return true;}','state.textStudio.flush=async()=>{elements.advancedPanel.dataset.aiRequestContext="editor";return true;}'])test('preflush changes abort the pinned group: '+setup,async()=>{const {run}=group();run(setup);assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.equal(run('requests.length'),0);});
test('two waiting callers submit once and pause before awaits',async()=>{const {run}=group();run('state.preview.playing=true;let release;const wait=new Promise(r=>release=r);state.textStudio.flush=()=>{if(state.preview.playing)throw Error("not paused");return wait;};globalThis.first=relocateTimelineLayerGroup(ids,ids[0],0,lanes[1]);globalThis.second=relocateTimelineLayerGroup(ids,ids[0],0,lanes[1]);release(true);');await run('Promise.all([first,second])');assert.equal(run('requests.length'),1);});
for(const change of ['elements.advancedPanel.dataset.aiRequestContext="editor"','members=ids.slice(1)','state.preview.mode="source"','state.timeline.mediaSelection=ids[1]','state.timeline.playhead=4'])test('late accepted relocation preserves newer context: '+change,async()=>{const {run}=group();run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${change};return result;};`);assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'));assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);assert.equal(run('reveals.length'),0);});
for(const change of ['elements.advancedPanel.dataset.aiRequestContext="editor"','members=ids.slice(1)','state.preview.mode="source"','state.timeline.playhead=4'])test('real409 refresh is in-place, no replay: '+change,async()=>{const {run}=group();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){${change};const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:15}};};`);assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.equal(run('state.project.revision'),15);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);assert.match(run('messages.at(-1)'),/not repeated/);});
for(const edit of ['result.project.manual.media_clips[0].source_start++','result.project.manual.media_clips[1].track_id=lanes[2]','result.project.manual.layer_tracks.tracks.reverse()','result.project.settings.fps=60','result.project.manual.media_clips.reverse()'])test('tampered/partial receipt is not installed: '+edit,async()=>{const {run}=group();const before=run('JSON.stringify(state.project)');run(`const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);${edit};return result;};`);assert.equal(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'),null);assert.equal(run('JSON.stringify(state.project)'),before);assert.match(run('messages.at(-1)'),/could not be verified/);});
test('older accepted response cannot replace newer same-project snapshot',async()=>{const {run}=group();run('const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);state.project={...state.project,revision:20};return result;};');assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'));assert.equal(run('state.project.revision'),20);assert.equal(run('reveals.length'),0);});
test('new project view is not hydrated by old completion',async()=>{const {run}=group();run('const originalApi=api;api=async(...args)=>{const result=await originalApi(...args);state.projectViewToken++;return result;};');assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'));assert.equal(run('state.project.revision'),7);assert.equal(run('reveals.length'),0);});
test('track ghosts clear time previews and pause without installing track overrides',()=>{const {run}=group();run('state.preview.playing=true;previewLayerGroup([{clip_id:ids[0],start:1,end:3,track_id:lanes[1]}]);');assert.equal(run('state.preview.playing'),false);assert.deepEqual(plain(run('groupPreviews')),[['media',null],['text',null]]);assert.equal(run('requests.length'),0);});
test('legacy time-only previews still use their existing live overrides',()=>{const {run}=group();run('previewLayerGroup([{clip_id:ids[0],start:1,end:3}]);');assert.deepEqual(plain(run('groupPreviews[0][1]')),[{clip_id:MID,start:1,end:3}]);});
test('deferred row reveal respects newer real scroll/zoom ownership',async()=>{const {run}=group();run('globalThis.frames=[];requestAnimationFrame=fn=>frames.push(fn);');assert.ok(await run('relocateTimelineLayerGroup(ids,ids[0],0,lanes[1])'));run('state.timeline.scroll.scrollTop=200;frames.splice(0).forEach(fn=>fn());');assert.equal(run('reveals.length'),0);assert.equal(run('seeks.length'),0);});
test('existing panel contains one local destination chooser, no new toolbar/shortcut',()=>{assert.match(source,/data-group-track-controls data-editor-shortcuts="off"/);assert.match(source,/data-group-relocate aria-describedby="layerGroupTrackStatus"/);assert.match(source,/mediaGroupRelocatePreview: layerGroupRelocatePlan/);assert.match(source,/verifyLayerGroupRelocate\(relocateBefore,payload.project,detail.clip_ids,detail.anchor_id,detail.track_id,detail.delta\)/);assert.doesNotMatch(fs.readFileSync(path.join(__dirname,'../web/keyboard.js'),'utf8'),/relocate/);});

function controls(){const h=group();h.run(`globalThis.controlNodes=new Map();globalThis.box={querySelector(key){return controlNodes.get(key)}};for(const key of ['[data-group-track]','[data-group-relocate]','[data-group-track-status]','[data-group-track-label]'])controlNodes.set(key,{value:'',disabled:false,hidden:false,replaceChildren(...options){this.options=options},focus(){document.activeElement=this},isConnected:true,getClientRects:()=>[{}]});globalThis.panel={querySelector(key){return key==='[data-group-track-controls]'?box:controlNodes.get(key)}};state.layerGroupPanel=panel;renderLayerGroupTrackControls(panel,ids);`);return h;}
test('keyboard chooser does not write, preserves a local choice on passive sync and marks no-op honestly',()=>{const {run}=controls();assert.equal(run('panel.groupTrackChoice'),lane(1));assert.equal(run('controlNodes.get("[data-group-relocate]").disabled'),true);run('panel.groupTrackChoice=lanes[1];renderLayerGroupTrackControls(panel,ids);state.timeline.playhead=4;renderLayerGroupTrackControls(panel,ids);');assert.equal(run('panel.groupTrackChoice'),lane(2));assert.equal(run('controlNodes.get("[data-group-relocate]").disabled'),false);assert.equal(run('requests.length'),0);});
test('missing selected destination remains explicit and never silently reroutes',()=>{const {run}=controls();run('panel.groupTrackChoice=lanes[4];state.project.manual.layer_tracks.tracks.pop();renderLayerGroupTrackControls(panel,ids);');assert.equal(run('panel.groupTrackChoice'),lane(5));assert.equal(run('controlNodes.get("[data-group-relocate]").disabled'),true);assert.equal(run('controlNodes.get("[data-group-track]").options[0].textContent'),'Destination no longer available');assert.equal(run('requests.length'),0);});
test('draft/Discard readiness refreshes existing chooser without clearing local destination',()=>{const {run}=controls();run('panel.groupTrackChoice=lanes[1];state.captionDirty=true;renderLayerGroupTrackControls(panel,ids);');assert.equal(run('controlNodes.get("[data-group-relocate]").disabled'),true);run('state.captionDirty=false;renderLayerGroupTrackControls(panel,ids);');assert.equal(run('controlNodes.get("[data-group-relocate]").disabled'),false);assert.equal(run('panel.groupTrackChoice'),lane(2));});
test('new primary selection resets keyboard anchor choice, not the selected members',()=>{const {run}=controls();run('panel.groupTrackChoice=lanes[1];state.timeline.mediaSelection=ids[1];renderLayerGroupTrackControls(panel,ids);');assert.equal(run('panel.groupTrackChoice'),lane(3));assert.deepEqual(plain(run('members')),[MID,RID]);});
function focusHarness(){const h=controls();h.run(`globalThis.events=new Map();globalThis.frames=[];requestAnimationFrame=fn=>frames.push(fn);document.addEventListener=(key,fn)=>events.set(key,fn);document.removeEventListener=(key,fn)=>{if(events.get(key)===fn)events.delete(key)};window.addEventListener=document.addEventListener;window.removeEventListener=document.removeEventListener;globalThis.owner=controlNodes.get('[data-group-relocate]');owner.disabled=false;document.activeElement=owner;globalThis.finish=ownGroupRelocateFocus(owner);document.activeElement=document.body;`);return h;}
test('successful own keyboard action returns focus to chooser when Apply becomes no-op disabled',()=>{const {run}=focusHarness();run('owner.disabled=true;finish(true);frames.shift()();');assert.equal(run('document.activeElement===controlNodes.get("[data-group-track]")'),true);assert.equal(run('events.size'),0);});
for(const change of ['events.get("keydown")({key:"Tab"})','events.get("pointerdown")({})','events.get("focusin")({target:{}})','events.get("blur")({})','state.projectViewToken++','state.timeline.mediaSelection=ids[1]','members=ids.slice(1)','elements.advancedPanel.dataset.aiRequestContext="editor"','owner.isConnected=false','document.activeElement={}'])test('focus completion respects newer ownership: '+change,()=>{const {run}=focusHarness();run(change+';finish(true);frames.shift()();');assert.equal(run('document.activeElement===owner'),false);assert.equal(run('document.activeElement===controlNodes.get("[data-group-track]")'),false);assert.equal(run('events.size'),0);});



