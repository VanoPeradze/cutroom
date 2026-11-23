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



function monitor(){const h=app();h.run(`
 state.projectViewToken=3;globalThis.cardOpen=true;globalThis.admitted=true;
 state.project.manual.media_clips=[];state.project.manual.text_clips=[];
 state.project.assets={v:{id:'v',kind:'video',status:'ready',duration:10}};
 state.textStudio={flush:async()=>true,render(){}};
 globalThis.options={strictRevision:true,isCurrent:()=>cardOpen,admissionCurrent:()=>admitted&&cardOpen};
 globalThis.detail={asset_id:'v',source_start:1,source_end:3,start:2};
 globalThis.submit=action=>applyManualEdit(action,detail,options);
 `);return h;}
for(const action of ['media_append','media_insert']){
 test(`${action} source monitor sends one revision-qualified native action`,async()=>{const {run}=monitor();assert.ok(await run(`submit('${action}')`));assert.equal(run('requests.length'),1);assert.equal(run('requests[0].body.expected_revision'),7);assert.equal(run('state.project.revision'),8);assert.equal(run('state.manualEditBusy'),false);});
 test(`${action} stale 409 refreshes latest history without replay`,async()=>{const {run}=monitor();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12,manual:{...state.project.manual,history:{undo_count:1}}}};};`);assert.equal(await run(`submit('${action}')`),null);assert.equal(run('requests.length'),2);assert.equal(run('state.project.revision'),12);assert.equal(run('state.project.manual.history.undo_count'),1);assert.match(run('messages.at(-1)'),/latest version.*source destination/);assert.equal(run('seeks.at(-1)'),1);});
 test(`${action} accepts committed result after card closes in same view without reopening`,async()=>{const {run}=monitor();run(`api=async()=>{cardOpen=false;state.timeline.playhead=4;return {project:{...state.project,revision:8}};};`);assert.ok(await run(`submit('${action}')`));assert.equal(run('state.project.revision'),8);assert.equal(run('cardOpen'),false);assert.equal(run('seeks.at(-1)'),4);});
 for(const mutation of ['state.projectViewToken++','state.project={...state.project,id:"other"}'])test(`${action} late result cannot overwrite another view: ${mutation}`,async()=>{const {run}=monitor();run(`api=async()=>{const project={...state.project,revision:8};${mutation};return {project};};`);assert.ok(await run(`submit('${action}')`));assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);assert.equal(run('seeks.length'),0);});
 test(`${action} late response does not overwrite a newer local revision`,async()=>{const {run}=monitor();run(`api=async()=>{const project={...state.project,revision:8};state.project={...state.project,revision:10};return {project};};`);await run(`submit('${action}')`);assert.equal(run('state.project.revision'),10);assert.equal(run('renderCount'),0);});
 test(`${action} admission change while saves flush cancels before request`,async()=>{const {run}=monitor();run(`flushProjectSaves=async()=>{state.timeline.playhead=4;admitted=false;};`);assert.equal(await run(`submit('${action}')`),null);assert.equal(run('requests.length'),0);});
 test(`${action} stale response after same-project view switch does not fetch/adopt`,async()=>{const {run}=monitor();run(`api=async(url,options)=>{requests.push({url,options});state.projectViewToken++;const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;};`);assert.equal(await run(`submit('${action}')`),null);assert.equal(run('requests.length'),1);assert.equal(run('state.project.revision'),7);});
}
test('source monitor readiness prioritizes explicit draft and recorded speech recovery',()=>{const {run}=monitor();run(`explicitPendingDraft=()=>({detail:'Apply or discard chroma'});`);assert.equal(run('sourceMonitorIssue()'),'Apply or discard chroma');run(`explicitPendingDraft=()=>null;pendingTranscriptBuffers=()=>[{}];`);assert.match(run('sourceMonitorIssue()'),/recorded-speech/);});
for(const pending of ['state.textStudio.dirty=()=>true','state.textStudio.pending=new Map([[1,1]])','state.textStudio.saving=true','state.mediaStudio={pending:new Map([[1,1]])}','state.sourceMixerSavePending=true','state.sourceSyncPending=true','state.saveQueues.set("p",{pending:{fps:24}})','state.saveQueues.set("p",{inFlight:true})'])test(`source monitor rejects pending work: ${pending}`,()=>{const {run}=monitor();run(`explicitPendingDraft=()=>null;pendingTranscriptBuffers=()=>[];liveEmbeddedCameraRequest=()=>false;${pending};`);assert.match(run('sourceMonitorIssue()'),/Wait for the current changes/);});
test('source monitor is ready only after all queues clear',()=>{const {run}=monitor();run('explicitPendingDraft=()=>null;pendingTranscriptBuffers=()=>[];liveEmbeddedCameraRequest=()=>false;');assert.equal(run('sourceMonitorIssue()'),'');});
test('source transport pauses program and other media, excluding its own native video',()=>{const {run}=monitor();const body=source.match(/function pauseAllMedia\(except = null\) \{[\s\S]*?\n\}/)[0];run(body);run(`globalThis.paused=[];globalThis.sourceVideo={pause:()=>paused.push('source')};document.querySelectorAll=()=>[sourceVideo,{pause:()=>paused.push('program')},{pause:()=>paused.push('audio')}];state.mediaStudio={pause:()=>paused.push('studio')};setPreviewPlaying=value=>paused.push(value);pauseAllMedia(sourceVideo);`);assert.deepEqual(plain(run('paused')),['studio','program','audio',false]);});
test('program play invalidates source playback even when program admission is blocked',async()=>{const {run}=monitor();run(`globalThis.sourcePauses=0;state.mediaStudio={pauseSourceMonitor:()=>sourcePauses++,resumeAudio(){}};state.project.sources={};`);await run('playPreview()');assert.equal(run('sourcePauses'),1);});
test('actual app wiring pins view token and exposes source-safe transport and placement',()=>{assert.match(source,/token: \(\) => state.projectViewToken/);assert.match(source,/pauseProgram: source => pauseAllMedia\(source\)/);assert.match(source,/seekSourcePreview\(clip.end\);renderManualControls\(\)/);assert.match(source,/if\(tab!=="media"\)state.mediaStudio\?\.closeSourceMonitor/);const media=fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8');assert.match(media,/strictRevision:Boolean\(monitor\)/);assert.match(media,/admissionCurrent:.*options.time.*-start/);});

for(const action of ['media_append','media_insert'])test(`${action} stale refresh cannot roll back newer visible history`,async()=>{const {run}=monitor();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}const project={...state.project,revision:12};state.project={...state.project,revision:15,manual:{...state.project.manual,history:{undo_count:3}}};return {project};};`);assert.equal(await run(`submit('${action}')`),null);assert.equal(run('state.project.revision'),15);assert.equal(run('state.project.manual.history.undo_count'),3);assert.equal(run('requests.length'),2);});
test('refreshed conflict history is immediately usable by native Undo',async()=>{const {run}=monitor();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const body=JSON.parse(options.body);if(body.action==='undo')return {project:{...state.project,revision:13,manual:{...state.project.manual,history:{undo_count:0}}}};const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12,manual:{...state.project.manual,history:{undo_count:1}}}};};`);assert.equal(await run("submit('media_append')"),null);assert.ok(await run("applyManualEdit('undo')"));assert.equal(run('state.project.revision'),13);assert.equal(run('state.project.manual.history.undo_count'),0);assert.equal(run('JSON.parse(requests[2].options.body).expected_revision'),12);});

for(const action of ['media_append','media_insert'])test(`${action} view switch during conflict refresh cannot adopt old project`,async()=>{const {run}=monitor();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}state.projectViewToken++;return {project:{...state.project,revision:12}};};`);assert.equal(await run(`submit('${action}')`),null);assert.equal(run('state.project.revision'),7);assert.equal(run('renderCount'),0);});
for(const setup of ['cardOpen=false','state.textStudio.flush=async()=>{cardOpen=false;return true;}','flushProjectSaves=async()=>{cardOpen=false;}'])test(`closed source session cannot admit a new write: ${setup}`,async()=>{const {run}=monitor();run(setup);assert.equal(await run("submit('media_append')"),null);assert.equal(run('requests.length'),0);});
test('source admission error releases busy state and does not submit',async()=>{const {run}=monitor();run(`options.admissionCurrent=()=>{throw new Error('Source destination changed');};`);assert.equal(await run("submit('media_insert')"),null);assert.equal(run('state.manualEditBusy'),false);assert.equal(run('requests.length'),0);assert.match(run('messages.at(-1)'),/Source destination changed/);});
