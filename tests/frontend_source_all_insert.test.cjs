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
  const media=vm.createContext({window:{},document:{},setTimeout,clearTimeout});
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/media-studio.js'),'utf8').replace(/^export /gm,'')+';globalThis.readiness=libraryInsertReadiness;',media);
  context.libraryInsertReadiness=media.readiness;
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


function placement(setup = '', target = 'edit') {
  const h=app(); h.run(`state.projectViewToken=2; state.mediaStudio={flush:async()=>true};
    selectEditTool=()=>{}; savedLayerTrackIssue=()=>'';
    state.project.assets={v:{kind:'video',status:'ready'},a:{kind:'audio',status:'ready'},i:{kind:'image',status:'ready'}};
    state.project.manual.media_clips=[]; state.project.manual.text_clips=[];
    ${setup}
    openSourceInsert({slot:'B',scope:'${target}',source_start:2.125,source_end:3.75});
    elements.sourceInsertMode.value='insert_all'; renderSourceInsert();`); return h;
}
const submit='insertSourceFootage({preventDefault(){}})';

test('opening original-source placement keeps legacy default and exact frame-boundary At',()=>{
 const {run}=app();run(`selectEditTool=()=>{};state.timeline.playhead=1.033333333;openSourceInsert({slot:'A',scope:'edit',source_start:2.123456789,source_end:3.123456789});`);
 assert.equal(run('elements.sourceInsertMode.value'),'insert');assert.equal(run('elements.sourceInsertAt.value'),'1.033333333');
 assert.equal(run('sourceInsertPlan().start'),1.033333333);assert.equal(run('sourceInsertPlan().sourceStart'),2.123456789);
});
test('explicit all-layer submission uses one native revision transaction and no audio routing mutation',async()=>{
 const {run}=placement();const before=plain(run('state.project.manual'));await run(submit);
 assert.equal(run('requests.length'),1);assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_insert_all',slot:'B',start:1,source_start:2.125,source_end:3.75,expected_revision:7});
 assert.deepEqual(plain(run('state.project.manual')),before);assert.equal(run('state.project.revision'),8);assert.equal(run('state.sourceInsertSession'),null);
 assert.deepEqual(plain(run('selections.at(-1)')),{start:1,end:2.625});assert.equal(run('seeks.at(-1)'),1);
});
for(const [target,mode,action] of [['edit','insert','sequence_insert_linked'],['source','insert','sequence_insert'],['edit','overwrite','sequence_overwrite']])test(`existing ${target} ${mode} retains ${action}`,async()=>{
 const {run}=placement('',target);run(`elements.sourceInsertMode.value='${mode}';`);await run(submit);assert.equal(run('requests[0].body.action'),action);
 assert.equal(run('requests[0].body.scope'),mode==='overwrite'?'edit':undefined);
});
test('source-only scope disables all-layer option and forged choice never widens scope',async()=>{
 const {run}=placement('','source');assert.equal(run(`elements.sourceInsertMode.querySelector('option[value="insert_all"]').disabled`),true);
 assert.equal(run('activeEditTarget()'),'B');assert.equal(run('elements.sourceInsertApply.disabled'),true);await run(submit);
 assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/Together.*not widened/);
});
for(const slot of ['A','B'])test(`all-layer insertion refuses ${slot} lock even for empty source lane or tail`,async()=>{
 const {run}=placement(`state.project.manual.track_locks={${slot}:true};state.project.editor_sequence.source_tracks.${slot}=[];state.timeline.playhead=6;`);
 assert.equal(run('elements.sourceInsertApply.disabled'),true);await run(submit);assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),new RegExp('Track '+slot+'.*locked'));
});
for(const at of [0,6])test(`all-layer valid boundary ${at} accepts without changing reviewed position`,()=>{
 const {run}=placement(`state.timeline.playhead=${at};`);assert.equal(run('sourceInsertPlan().start'),at);assert.equal(run('elements.sourceInsertApply.disabled'),false);
});
for(const value of ['6.01','-1','nonsense'])test(`all-layer invalid At ${value} refuses`,async()=>{
 const {run}=placement();run(`elements.sourceInsertAt.value='${value}';renderSourceInsert();`);assert.equal(run('elements.sourceInsertApply.disabled'),true);await run(submit);assert.equal(run('requests.length'),0);
});
test('legacy sources-only insertion still admits beyond-end position',()=>{const {run}=placement();run('elements.sourceInsertMode.value="insert";elements.sourceInsertAt.value="7"');assert.equal(run('sourceInsertPlan().start'),7);});
test('source interval shorter than output frame refuses all-layer insertion',()=>{const {run}=placement();run('elements.sourceInsertOut.value="2.14"');assert.throws(()=>run('sourceInsertPlan()'),/Choose source times/);});
test('24-hour total capacity is enforced for all-layer insertion',()=>{const {run}=placement('state.project.editor_sequence.duration=86400;');assert.equal(run('elements.sourceInsertApply.disabled'),true);assert.match(run('elements.sourceInsertStatus.textContent'),/24 hours/);});
test('selected edit range supplies insertion length rather than replacement and exact endpoints survive toggle',()=>{
 const {run}=placement('state.manualSelection={start:1.033333333,end:2.066666666};');run('elements.sourceInsertZone.value="selection";renderSourceInsert()');
 assert.equal(run('sourceInsertPlan().start'),1.033333333);assert.ok(Math.abs(run('sourceInsertPlan().length')-1.033333333)<1e-12);
 assert.equal(run('elements.sourceInsertAt.value'),'1.033333333');assert.match(run('elements.sourceInsertStatus.textContent'),/inserted length; it is not replaced/);
 assert.equal(run('elements.sourceInsertAt.disabled'),true);run('elements.sourceInsertZone.value="playhead";renderSourceInsert()');assert.equal(run('elements.sourceInsertAt.value'),'00:01.000');assert.equal(run('elements.sourceInsertOut.value'),'00:03.750');
});
for(const audio of ['A','B'])test(`all-layer disclosure uses global source audio ${audio}, not selected picture or transcript source`,()=>{
 const {run}=placement(`state.project.manual.source_mixer.audio_slot='${audio}';`);assert.match(run('elements.sourceInsertStatus.textContent'),new RegExp('Source audio stays routed to '+audio));
 if(audio==='A')assert.match(run('elements.sourceInsertStatus.textContent'),/does not switch its sound.*silent/);else assert.match(run('elements.sourceInsertStatus.textContent'),/does not change mix or gain/);
 assert.equal(run('requests.length'),0);
});
for(const kind of ['video','audio','image'])test(`supported crossing ${kind} keeps readiness and no optimistic mutation`,()=>{
 const id={video:'v',audio:'a',image:'i'}[kind];const {run}=placement(`state.project.manual.media_clips=[{id:'m',asset_id:'${id}',start:0,end:3,source_start:.25,video_source_start:.125,speed:.5,enabled:false,fade_in:.3,fade_out:.4}];`);
 assert.equal(run('elements.sourceInsertApply.disabled'),false);assert.equal(run('state.project.manual.media_clips.length'),1);assert.equal(run('state.project.manual.media_clips[0].enabled'),false);
});
test('crossing custom text is supported and later motion remains untouched',()=>{
 const {run}=placement(`state.project.manual.text_clips=[{id:'t',start:0,end:3,text:'Title'}];state.project.manual.media_clips=[{id:'m',asset_id:'i',start:3,end:5,motion:'pan_left'}];`);
 assert.equal(run('elements.sourceInsertApply.disabled'),false);assert.equal(run('state.project.manual.text_clips[0].end'),3);
});
for(const [fields,reason] of [["asset_id:'i',motion:'pan_left'",/animated/],["asset_id:'v',fade_in:1.1",/fade/],["asset_id:'a',fade_out:2.1",/fade/],["asset_id:'v',start:.95",/shorter/],["asset_id:'missing'",/not ready/]])test(`all-layer crossing refusal: ${fields}`,()=>{
 const {run}=placement(`state.project.manual.media_clips=[{id:'m',asset_id:'v',start:0,end:3,${fields}}];`);assert.equal(run('elements.sourceInsertApply.disabled'),true);assert.match(run('elements.sourceInsertStatus.textContent'),reason);
});
test('fractional existing boundary is not rounded into a forbidden tiny split',()=>{
 const {run}=placement(`state.timeline.playhead=1.033333333;state.project.manual.media_clips=[{id:'m',asset_id:'i',start:1.033333333,end:3,motion:'pan_left'}];`);
 assert.equal(run('sourceInsertPlan().start'),1.033333333);assert.equal(run('elements.sourceInsertApply.disabled'),false);
});
test('source insertion reserves no imported slot: full 200 boundary allowed while library default is refused',()=>{
 const {run}=placement(`state.project.manual.media_clips=Array.from({length:200},(_,i)=>({id:'m'+i,asset_id:'i',start:2,end:3}));`);
 assert.equal(run('elements.sourceInsertApply.disabled'),false);assert.match(run('libraryInsertReadiness(editorProject(),1,1)'),/200 media/);
 assert.equal(run('libraryInsertReadiness(editorProject(),1,1,0)'),'');assert.match(run('libraryInsertReadiness(editorProject(),1,1,2)'),/insertion type/);
});
for(const [key,count,reason] of [['media_clips',200,/200 media/],['text_clips',2000,/2000 text/]])test(`crossing split respects ${key} exact capacity`,()=>{
 const {run}=placement(`state.project.manual.${key}=Array.from({length:${count}},(_,i)=>({id:'r'+i,asset_id:'i',start:0,end:3}));`);
 assert.equal(run('elements.sourceInsertApply.disabled'),true);assert.match(run('elements.sourceInsertStatus.textContent'),reason);
});
for(const [setup,reason] of [
 ["state.project.draft.audio_plan=[{}]",/timed audio plan/],
 ["state.project.caption_alternative_status={active_id:'alternative'}",/alternative caption/],
 ["state.project.manual.caption_dormant_overrides={x:{}}",/uncertain ownership/],
 ["state.project.manual.caption_overrides={missing:{text:'x'}}",/owner is unavailable/],
 ["state.project.manual.caption_overrides={x:{text:'x'}};state.project.editor_captions=[{id:'x',start:0,end:2}]",/caption crosses/]
])test(`middle insertion caption/audio guard: ${reason}`,()=>{
 const {run}=placement(setup+';');assert.equal(run('elements.sourceInsertApply.disabled'),true);assert.match(run('elements.sourceInsertStatus.textContent'),reason);
 run('closeSourceInsert();state.timeline.playhead=6;openSourceInsert({scope:"edit",slot:"B",source_start:2,source_end:3});elements.sourceInsertMode.value="insert_all";renderSourceInsert()');assert.equal(run('elements.sourceInsertApply.disabled'),false);
});
test('known caption edit ending at insertion boundary is admitted',()=>{const {run}=placement(`state.project.manual.caption_overrides={x:{text:'x'}};state.project.editor_captions=[{id:'x',start:0,end:1}];`);assert.equal(run('elements.sourceInsertApply.disabled'),false);});
for(const change of ['state.project.revision++','state.projectViewToken++','state.project.manual.media_clips.push({id:"later",start:4,end:5})','state.project.manual.text_clips.push({id:"later",start:4,end:5})','state.project.manual.layer_tracks={version:1,tracks:[]}','state.project.assets.v.status="failed"','state.project.manual.caption_overrides={x:{}}','state.project.manual.source_mixer.audio_slot="A"','state.project.editor_captions=[{id:"x",start:0,end:2}]'])test(`raw reviewed identity change is refused without request: ${change}`,async()=>{
 const {run}=placement();run(change);await run(submit);assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/edit or source changed/);
});
for(const change of ['elements.sourceInsertMode.value="insert"','elements.sourceInsertAt.value="2"','elements.sourceInsertIn.value="1"','elements.sourceInsertSlot.value="A"','state.projectViewToken++','closeSourceInsert()'])test(`awaited save cannot submit a different reviewed intent: ${change}`,async()=>{
 const {run}=placement();run(`flushProjectSaves=async()=>{${change};};`);await run(submit);assert.equal(run('requests.length'),0);assert.equal(run('selections.length'),0);
});
test('pending all-layer transaction disables real controls and rejects repeats',async()=>{
 const {run}=placement();run(`globalThis.release=null;globalThis.calls=0;applyManualEdit=async()=>{calls++;return await new Promise(r=>release=r)};globalThis.pending=insertSourceFootage({preventDefault(){}});`);
 for(const name of ['sourceInsertIn','sourceInsertOut','sourceInsertAt','sourceInsertSlot','sourceInsertMode','sourceInsertZone','sourceInsertCancel','sourceInsertApply'])assert.equal(run(`elements.${name}.disabled`),true,name);
 await run(submit);assert.equal(run('calls'),1);run('state.project={...state.project,revision:8};release(state.project)');await run('pending');assert.equal(run('calls'),1);
});
for(const change of ['state.projectViewToken++','closeSourceInsert()','state.sourceInsertSession={...state.sourceInsertSession}'])test(`late accepted all-layer insertion cannot hijack navigation: ${change}`,async()=>{
 const {run}=placement();run(`applyManualEdit=async()=>{${change};state.project={...state.project,revision:8};return state.project};`);await run(submit);assert.equal(run('selections.length'),0);assert.equal(run('seeks.length'),0);
});
test('all-layer revision conflict refreshes once, exposes history and never replays',async()=>{
 const {run}=placement();run(`api=async(url,options)=>{requests.push({url,options});if(options?.method==='POST'){const e=new Error('conflict');e.status=409;e.code='revision_conflict';throw e;}return {project:{...state.project,revision:12,manual:{...state.project.manual,history:{undo_count:1}}}};};`);
 await run(submit);assert.equal(run('requests.length'),2);assert.equal(run('requests.filter(r=>r.options?.method==="POST").length'),1);assert.equal(run('state.project.revision'),12);assert.equal(run('state.project.manual.history.undo_count'),1);assert.equal(run('selections.length'),0);
});
test('unapplied explicit draft blocks all-layer insertion and retained state cannot enter it',async()=>{
 const {run}=placement();run('sourceMonitorIssue=()=>"Apply or discard Chroma"');await run(submit);assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/Chroma/);
 run('closeSourceInsert();requireResumedEdit=()=>false');assert.equal(run('openSourceInsert({scope:"edit"})'),false);assert.equal(run('state.sourceInsertSession'),null);
});
test('unsupported saved track model blocks all-layer action before request',async()=>{const {run}=placement();run('savedLayerTrackIssue=()=>"Track version is unavailable";renderSourceInsert()');assert.equal(run('elements.sourceInsertApply.disabled'),true);await run(submit);assert.equal(run('requests.length'),0);assert.match(run('elements.sourceInsertStatus.textContent'),/Track version/);});
