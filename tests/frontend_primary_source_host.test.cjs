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
  const document = {getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:fn=>fn(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for(const file of ['source-tracks.js','timeline.js','keyboard.js','layer-selection.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
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


function primary(){const h=app();h.run(`
 state.projectViewToken=3;state.studio.open=true;globalThis.opened=[];globalThis.closed=[];globalThis.flushes=0;
 globalThis.realPrimaryOpen=openSourceReview;
 globalThis.SourceReview=class{constructor(options){globalThis.dockOptions=options;}open(target,options){opened.push({target,options});return true;}close(options){closed.push(options);}sync(){}pausePreview(){}};
 flushCurrentProjectSaves=async()=>{flushes++;return true;};sourceMonitorIssue=()=>'';
 document.activeElement={id:'pool-A'};
 state.timeline.setMediaSelection=(ids,primary)=>{state.timeline.mediaSelection=primary;globalThis.groupCleared=ids;};
 state.mediaStudio={closeSourceMonitor(){globalThis.importedClosed=true;}};
 `);return h;}

test('primary source entry flushes first then opens real Media dock with requested slot and unchanged edit',async()=>{
 const {run}=primary();const before=plain(run('state.project'));assert.equal(await run('openSourceReview({slot:"B"})'),true);
 assert.equal(run('flushes'),1);assert.equal(run('importedClosed'),true);assert.equal(run('opened[0].target'),'edit');assert.equal(run('opened[0].options.slot'),'B');assert.equal(run('opened[0].options.opener.id'),'pool-A');assert.deepEqual(plain(run('state.project')),before);
 assert.equal(run('dockOptions.dock.root.id'),'studioPanelMedia');assert.equal(run('dockOptions.dock.token()'),3);assert.equal(run('dockOptions.dock.visible()'),true);
});
for(const before of ['state.manualEditBusy=true','foregroundBusy=()=>true','state.project.editor_sequence=null'])test(`primary entry refuses before flushing: ${before}`,async()=>{const {run}=primary();run(before);assert.equal(await run('openSourceReview()'),false);assert.equal(run('flushes'),0);assert.equal(run('opened.length'),0);});
for(const change of ['state.projectViewToken++','state.project={...state.project,id:"other"}','closePrimarySourceReview()','state.manualEditBusy=true','state.project.editor_sequence=null'])test(`held source open cannot change newer context: ${change}`,async()=>{const {run}=primary();run(`flushCurrentProjectSaves=async()=>{${change};return true;};`);assert.equal(await run('openSourceReview()'),false);assert.equal(run('opened.length'),0);});
test('source open respects rejected local drafts and post-flush pending readiness',async()=>{const {run}=primary();run('flushCurrentProjectSaves=async()=>false');assert.equal(await run('openSourceReview()'),false);run('flushCurrentProjectSaves=async()=>true;sourceMonitorIssue=()=>"Save draft first";');assert.equal(await run('openSourceReview()'),false);assert.equal(run('opened.length'),0);assert.equal(run('messages.at(-1)'),'Save draft first');});
test('source open cannot override rejected Studio navigation',async()=>{const {run}=primary();run('openStudioTab=()=>false');assert.equal(await run('openSourceReview()'),false);assert.equal(run('opened.length'),0);assert.equal(run('globalThis.importedClosed'),undefined);});
test('primary source opening clears only temporary imported group not source range',async()=>{const {run}=primary();run('selectedLayerGroupIds=()=>["v","t"];state.manualSelection={start:1,end:2};');await run('openSourceReview()');assert.deepEqual(plain(run('groupCleared')),[]);assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:2});});
test('primary dock validates actual pane, pending work and source-exclusive playback',async()=>{const {run}=primary();await run('openSourceReview()');run('globalThis.except=null;pauseAllMedia=video=>except=video;globalThis.source={};dockOptions.dock.pauseProgram(source);');assert.equal(run('except===source'),true);run('document.getElementById("studioInspector").dataset.workbenchPane="ai"');assert.equal(run('dockOptions.dock.visible()'),false);run('document.getElementById("studioInspector").dataset.workbenchPane="inspector";document.getElementById("studioPanelMedia").inert=true');assert.equal(run('dockOptions.dock.visible()'),false);run('state.manualEditBusy=true');assert.equal(run('dockOptions.dock.busy()'),true);});
test('closing primary source invalidates pending open even without created controller',()=>{const {run}=primary();run('closePrimarySourceReview();closePrimarySourceReview()');assert.equal(run('state.primarySourceOpenEpoch'),2);});
test('closing primary source defaults to force but never focus theft',async()=>{const {run}=primary();await run('openSourceReview()');run('closePrimarySourceReview()');assert.deepEqual(plain(run('closed.at(-1)')),{force:true,restoreFocus:false});});
test('primary source program transport stops its preview before program admission',async()=>{const {run}=primary();run('globalThis.pauses=0;state.sourceReview={pausePreview:()=>pauses++};state.mediaStudio={pauseSourceMonitor(){},resumeAudio(){}};state.project.sources={};');await run('playPreview()');assert.equal(run('pauses'),1);});

test('source entry wiring uses slot-aware controller instead of modal query manipulation',()=>{assert.match(source,/reviewSource: slot => \{ void openSourceReview\(\{slot\}\); \}/);assert.doesNotMatch(source,/dialog\?\.open && select/);assert.match(source,/selected: id => \{ if\(id\)closePrimarySourceReview\(\)/);});
test('primary context and exact handoff invalidate on pane, AI and editor exits',()=>{assert.match(source,/if\(tab!=="media"\)closePrimarySourceReview\(\)/);assert.match(source,/if\(tab!=="timeline"\)closeSourceInsert\(\)/);assert.match(source,/if\(!nextOpen\)\{[^\n]*closePrimarySourceReview\(\);closeSourceInsert\(\)/);assert.match(source,/workbenchPane==="ai"\)\{[^\n]*closePrimarySourceReview\(\);closeSourceInsert\(\)/);assert.match(source,/state\.sourceReview\?\.sync\?\.\(\)/);});

function placement(){const h=app();h.run(`state.projectViewToken=2;state.mediaStudio={flush:async()=>true};selectEditTool=()=>{};globalThis.calls=[];globalThis.nativeEdit=applyManualEdit;openSourceInsert({slot:'B',scope:'source',source_start:2.125,source_end:3.75});`);return h;}
test('exact placement captures view and saved revision along with source identity',()=>{const {run}=placement();assert.equal(run('state.sourceInsertSession.viewToken'),2);assert.equal(run('state.sourceInsertSession.revision'),7);assert.equal(run('sourceInsertPlan().sourceStart'),2.125);assert.equal(run('sourceInsertPlan().sourceEnd'),3.75);assert.equal(run('sourceInsertPlan().target'),'B');});
for(const mutation of ['state.projectViewToken++','state.project={...state.project,revision:8}','state.project.sources.B.duration=29'])test(`exact placement refuses stale admission: ${mutation}`,async()=>{const {run}=placement();run(mutation);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/edit or source changed/);});
test('source placement calls strict one-shot native edit with reviewed clocks',async()=>{const {run}=placement();run(`applyManualEdit=async(action,detail,options)=>{calls.push({action,detail,options});state.project={...state.project,revision:8};return state.project;};`);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('calls[0].action'),'sequence_insert');assert.equal(run('calls[0].options.strictRevision'),true);assert.deepEqual(plain(run('calls[0].detail')),{slot:'B',start:1,source_start:2.125,source_end:3.75});assert.equal(run('state.sourceInsertSession'),null);assert.equal(run('seeks.at(-1)'),1);});
for(const change of ['state.projectViewToken++','closeSourceInsert()','state.sourceInsertSession={...state.sourceInsertSession}','elements.sourceInsertForm.hidden=true'])test(`late accepted placement cannot reopen or select after ${change}`,async()=>{const {run}=placement();run(`applyManualEdit=async()=>{${change};state.project={...state.project,revision:8};return state.project;};`);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('seeks.length'),0);assert.equal(run('selections.length'),0);});
for(const change of ['state.project.revision++','state.projectViewToken++','closeSourceInsert()'])test(`exact placement rechecks after save queues: ${change}`,async()=>{const {run}=placement();run(`flushProjectSaves=async()=>{${change};};`);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('requests.length'),0);});
test('exact placement real 409 refreshes once without silently retrying source placement',async()=>{const {run}=placement();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12,manual:{...state.project.manual,history:{undo_count:1}}}};};`);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('requests.length'),2);assert.equal(run('state.project.revision'),12);assert.equal(run('state.project.manual.history.undo_count'),1);assert.equal(run('selections.length'),0);assert.equal(run('elements.sourceInsertForm.hidden'),false);});
test('exact placement held action rejects repeat and source scope change invalidates session',async()=>{const {run}=placement();run(`globalThis.release=null;applyManualEdit=async()=>{calls.push(1);return await new Promise(resolve=>release=resolve);};globalThis.pending=insertSourceFootage({preventDefault(){}});`);await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('calls.length'),1);run('state.project={...state.project,revision:8};release(state.project)');await run('pending');assert.equal(run('calls.length'),1);});
test('primary source shell keeps real controls and separates optional help from A/B effect',()=>{const html=fs.readFileSync(path.join(__dirname,'../web/index.html'),'utf8');const block=html.slice(html.indexOf('<dialog id="sourceReviewDialog"'),html.indexOf('<dialog id="localModelSetupDialog"'));assert.equal((html.match(/data-review="video"/g)||[]).length,1);assert.match(block,/canvas data-review="canvas" height="180"/);assert.match(block,/data-review="refresh" hidden>Use current edit/);assert.ok(block.indexOf('data-review="effect"')<block.indexOf('class="source-review-help"'));assert.match(block,/source time and the selected scope, not imported-layer insertion/);});

test('newer primary open wins when an older save flush completes later',async()=>{const {run}=primary();run(`globalThis.release=null;globalThis.count=0;flushCurrentProjectSaves=async()=>++count===1?await new Promise(resolve=>release=resolve):true;globalThis.first=openSourceReview({slot:'A'});`);assert.equal(await run('openSourceReview({slot:"B"})'),true);run('release(true)');assert.equal(await run('first'),false);assert.equal(run('opened.length'),1);assert.equal(run('opened[0].options.slot'),'B');});
for(const action of ['sequence_source_restore','sequence_source_remove','undo']){
 test(`primary ${action} retains one strict transaction and native expected revision`,async()=>{const {run}=app();run(`state.projectViewToken=4;globalThis.current=true;globalThis.admission=true;`);assert.ok(await run(`applyManualEdit('${action}',{slot:'A',scope:'edit',source_start:2,source_end:3},{strictRevision:true,isCurrent:()=>current,admissionCurrent:()=>admission})`));assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.expected_revision'),7);assert.equal(run('requests[0].body.action'),action);assert.equal(run('state.project.revision'),8);});
 test(`primary ${action} stale conflict never replays reviewed source operation`,async()=>{const {run}=app();run(`state.projectViewToken=4;api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:11}};};`);await run(`applyManualEdit('${action}',{slot:'A',scope:'edit',source_start:2,source_end:3},{strictRevision:true})`);assert.equal(run('requests.length'),2);assert.equal(run('state.project.revision'),11);assert.equal(run('seeks.at(-1)'),1);});
 test(`primary ${action} accepted late response cannot overwrite another view`,async()=>{const {run}=app();run(`state.projectViewToken=4;api=async()=>{const project={...state.project,revision:8};state.projectViewToken++;return {project};};`);await run(`applyManualEdit('${action}',{slot:'A',scope:'edit',source_start:2,source_end:3},{strictRevision:true})`);assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);});
}

test('exact placement refuses explicit draft before submission',async()=>{const {run}=placement();run('sourceMonitorIssue=()=>"Apply or discard the Chroma draft";');await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/Chroma draft/);});
test('exact placement rechecks explicit draft introduced during awaited save',async()=>{const {run}=placement();run('globalThis.pendingDraft=false;sourceMonitorIssue=()=>pendingDraft?"Save caption":"";flushProjectSaves=async()=>{pendingDraft=true;};');await run('insertSourceFootage({preventDefault(){}})');assert.equal(run('requests.length'),0);assert.equal(run('selections.length'),0);});

for(const bad of ['{...state.project,id:"other",revision:8}','{...state.project,revision:7.5}','{...state.project,revision:null}'])test(`strict source edit rejects invalid successful receipt: ${bad}`,async()=>{const {run}=app();run(`api=async()=>({project:${bad}});`);assert.equal(await run('applyManualEdit("sequence_source_restore",{slot:"A",scope:"edit",source_start:2,source_end:3},{strictRevision:true})'),null);assert.equal(run('state.project.id'),'p');assert.equal(run('state.project.revision'),7);assert.equal(run('savedRevision'),7);assert.equal(run('renderCount'),0);assert.match(run('messages.at(-1)'),/invalid project/);});

test('explicit draft status immediately refreshes open exact placement without clearing typed values',()=>{const {run}=placement();run('globalThis.issue="";sourceMonitorIssue=()=>issue;elements.sourceInsertIn.value="2.123456789";elements.sourceInsertOut.value="3.75";renderProjectSaveState();');assert.equal(run('elements.sourceInsertApply.disabled'),false);run('issue="Discard or apply Chroma";renderProjectSaveState()');assert.equal(run('elements.sourceInsertApply.disabled'),true);assert.match(run('elements.sourceInsertStatus.textContent'),/Chroma/);assert.equal(run('elements.sourceInsertIn.value'),'2.123456789');run('issue="";renderProjectSaveState()');assert.equal(run('elements.sourceInsertApply.disabled'),false);assert.equal(run('elements.sourceInsertIn.value'),'2.123456789');assert.equal(run('requests.length'),0);});
