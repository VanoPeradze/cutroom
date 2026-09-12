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
  for(const file of ['source-tracks.js','timeline.js','keyboard.js']) run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
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

test('per-cut focus follows playback time and source instead of global framing', () => {
  const {run}=app();
  run(`state.project.editor_sequence.source_tracks.A[0].crop={x:.1,y:.4,zoom:1};
    state.project.editor_sequence.source_tracks.A[1].crop={x:.9,y:.6,zoom:1.2};`);
  assert.equal(run(`previewCropForLayout('A','A',sourceMixerSettings(),null,1).x`),.1);
  assert.equal(run(`previewCropForLayout('A','A',sourceMixerSettings(),null,4).x`),.9);
  assert.equal(run(`previewCropForLayout('B','A',sourceMixerSettings(),null,4).x`),.5);
  assert.equal(run(`previewCropForLayout('A','side_by_side',sourceMixerSettings(),null,4).x`),.9);
  run(`state.preview.mode='source';`);
  assert.equal(run(`previewCropForLayout('A','A',sourceMixerSettings(),null,4).x`),.5);
});

test('framing saves only the selected range on the chosen source and never patches global crop',async()=>{
  const {run}=app();
  run(`state.manualSelection={start:1,end:2};elements.cropSourceSelect.value='A';
    elements.cropX.value=15;elements.cropY.value=60;elements.cropZoom.value=120;
    loadCropControls=syncSecondaryPreview=()=>{};`);
  const before=run('JSON.stringify(state.project.manual.crop)');
  await run('saveCrop()');
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_crop',slot:'A',start:1,end:2,x:.15,y:.6,zoom:1.2,expected_revision:7});
  assert.equal(run('JSON.stringify(state.project.manual.crop)'),before);
});

test('editorProject overlays a compact read-only view without mutating source metadata or raw AI ranges', () => {
  const {run} = app();
  run(`globalThis.before=JSON.stringify(state.project);
    globalThis.freeze=(value)=>{if(value&&typeof value==='object'){Object.freeze(value);Object.values(value).forEach(freeze);}};
    freeze(state.project);globalThis.view=editorProject();`);
  assert.equal(run('JSON.stringify(state.project)'),run('before'));
  assert.deepEqual(plain(run('view.draft.keep_ranges')),[{start:0,end:6}]);
  assert.deepEqual(plain(run('view.draft.cuts')),[]);
  assert.equal(run('view.sources.A.duration'),20);
  assert.equal(run('view.manual.source_tracks.A[1].source_start'),14);
  assert.equal(run('view.analysis===state.project.analysis'),true);
  assert.equal(run('editorProject(view)===view'),true);
  assert.equal(run('state.project.manual.sequence'),undefined);
  run(`state.preview.mode='source';globalThis.original=playbackProject();`);
  assert.equal(run('original.manual.sequence'),undefined);
  assert.equal(run('original.manual.source_tracks'),undefined);
  assert.equal(run('JSON.stringify(state.project)'),run('before'));
});

test('sequence controls default to Together and retain explicit independent B selection', () => {
  const {run} = app();
  assert.equal(run('activeEditTarget()'),'edit');
  assert.equal(run('targetEditableClips()[0].start'),0);
  assert.equal(run('targetEditableClips()[0].end'),3);
  run(`setEditTarget('B');`);
  assert.equal(run('activeEditTarget()'),'B');
  assert.equal(run('targetEditableClips()[0].source_start'),6);
  run(`setEditTarget('edit');`);
  assert.equal(run('activeEditTarget()'),'edit');
  run(`state.editTarget='B';delete state.project.sources.B;`);
  assert.equal(run('activeEditTarget()'),'edit');
});

for(const [action,expected,detail] of [
  ['track_split','sequence_split',{slot:'A',time:1}],
  ['track_move','sequence_move',{slot:'B',clip_id:'b1',start:2}],
  ['track_remove_range','sequence_remove_range',{slot:'B',start:1,end:2}],
  ['track_trim','sequence_trim',{slot:'A',clip_id:'a1',start:0,end:2,source_start:4}],
  ['set_camera_layout','sequence_layout',{start:0,end:2,camera:'B'}],
  ['track_reset','sequence_reset',{slot:'B'}],
]) test(`manual ${action} sends ${expected} with revision after flushing queued saves`,async()=>{
  const {run} = app();
  run('flushProjectSaves=async()=>{flushCount++;savedRevision=9;};');
  const result=await run(`applyManualEdit('${action}',${JSON.stringify(detail)})`);
  assert.ok(result);
  assert.equal(run('flushCount'),1);
  const request=plain(run('requests[0]'));
  assert.equal(request.method,'POST');
  assert.deepEqual(request.body,{action:expected,...(action==='track_reset'?{}:detail),expected_revision:9});
  assert.equal(run('state.manualEditBusy'),false);
  assert.equal(run('seeks.at(-1)'),1);
});

test('sequence revision conflict fetches latest once but never replays an edit at stale coordinates',async()=>{
  const {run} = app();
  run(`state.manualSelection={start:1,end:2};api=async(url,options)=>{
    requests.push({url,method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null});
    if(options?.method==='POST')throw Object.assign(new Error('conflict'),{status:409,code:'revision_conflict'});
    return {project:{...state.project,revision:10}};};`);
  assert.equal(await run(`applyManualEdit('track_move',{slot:'A',clip_id:'a1',start:4})`),null);
  assert.deepEqual(plain(run('requests.map(item=>item.method)')),['POST','GET']);
  assert.equal(run('state.project.revision'),10);
  assert.equal(run('state.manualSelection'),null);
  assert.equal(run('state.manualEditBusy'),false);
  assert.match(run('messages.at(-1)'),/select the clip again and retry/);
});

test('timeline split and range removal target one source and keep edit-clock coordinates',async()=>{
  const {run} = app();
  run(`setEditTarget('B');state.manualSelection={start:1,end:2};`);
  await run(`handleTimelineEdit({action:'split',time:2})`);
  await run(`runManualRangeEdit('delete_range')`);
  assert.deepEqual(plain(run('requests.map(item=>({action:item.body.action,slot:item.body.slot,time:item.body.time,start:item.body.start,end:item.body.end}))')),
    [{action:'sequence_split',slot:'B',time:2},{action:'sequence_remove_range',slot:'B',start:1,end:2}]);
});

test('More duplicate uses the selected clip ID and inserts a copy at its edit end',async()=>{
  const {run,nodes} = app();
  run(`bindEvents();setEditTarget('A');state.manualSelection={start:3,end:6};`);
  await nodes.get('clipDuplicate').listeners.click();
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_duplicate',slot:'A',clip_id:'a2',start:6,expected_revision:7});
  assert.deepEqual(plain(run('selections.at(-1)')),{start:6,end:9});
  assert.equal(run('seeks.at(-1)'),6);
  run('state.manualSelection=null;');
  await nodes.get('clipDuplicate').listeners.click();
  assert.equal(run('requests.length'),1,'without a selected clip Duplicate is a no-op');
});

test('Add source footage uses original source bounds and independent edit insertion position',async()=>{
  const {run,nodes} = app();
  run(`setEditTarget('B');state.timeline.playhead=4;`);
  assert.equal(run('openSourceInsert()'),true);
  assert.equal(nodes.get('sourceInsertForm').dataset.target,'B');
  assert.equal(nodes.get('sourceInsertSlot').value,'B');
  assert.equal(nodes.get('sourceInsertSlot').disabled,true);
  assert.equal(nodes.get('sourceInsertAt').value,'00:04.000');
  nodes.get('sourceInsertIn').value='10.250';nodes.get('sourceInsertOut').value='12.750';nodes.get('sourceInsertAt').value='40';
  await run('insertSourceFootage({preventDefault(){}})');
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_insert',slot:'B',start:40,source_start:10.25,source_end:12.75,expected_revision:7});
  assert.deepEqual(plain(run('selections.at(-1)')),{start:40,end:42.5});
  assert.equal(nodes.get('sourceInsertForm').hidden,true);
});

test('source insertion rejects invalid, reversed, out-of-media and shorter-than-frame ranges',async()=>{
  const {run,nodes} = app();
  run("setEditTarget('A');openSourceInsert();");
  for(const [start,end,at] of [['1','0','0'],['-1','2','0'],['1','21','0'],['0','.01','0'],['0','1','86400'],['','','0']]) {
    nodes.get('sourceInsertIn').value=start;nodes.get('sourceInsertOut').value=end;nodes.get('sourceInsertAt').value=at;
    await run('insertSourceFootage({preventDefault(){}})');
  }
  assert.equal(run('requests.length'),0);
  assert.equal(nodes.get('sourceInsertForm').hidden,false);
});

test('minimum edit length follows export fps and source insertion admits a single valid frame',async()=>{
  for(const fps of [24,25,30,50,60]) {
    const {run,nodes} = app();
    run(`state.project.settings.fps=${fps};openSourceInsert();`);
    assert.equal(run('minimumEditLength()'),1/fps);
    nodes.get('sourceInsertIn').value='1';nodes.get('sourceInsertOut').value=(1+1/fps).toFixed(6);nodes.get('sourceInsertAt').value='0';
    await run('insertSourceFootage({preventDefault(){}})');
    assert.equal(run('requests.length'),1);
  }
});

test('unsupported or missing sequence fps defaults to 30 without changing legacy minimums',()=>{
  const {run} = app();
  for(const fps of [null,0,29.97,120,'invalid']) {
    run(`state.project.settings.fps=${JSON.stringify(fps)};`);
    assert.equal(run('minimumEditLength()'),1/30);
  }
  run(`state.project.settings.fps='25';`);
  assert.equal(run('minimumEditLength()'),1/25);
  run('delete state.project.editor_sequence;');
  assert.equal(run('minimumEditLength()'),.08);
});

test('Studio status reports the current extended sequence duration, not the original AI draft',()=>{
  const {run,nodes} = app();
  run(`state.project.draft.output_duration=10;state.project.draft.aspect='9:16';`);
  for(const duration of [19,22]) {
    run(`state.project.editor_sequence.duration=${duration};state.project.editor_sequence.sequence.duration=${duration};updateStudioStatus();`);
    assert.equal(nodes.get('studioDraftStatus').textContent,`00:${duration} · 9:16`);
    assert.equal(run('state.project.draft.output_duration'),10);
  }
  run(`state.draftDirtyReasons.add('pace');updateStudioStatus();`);
  assert.equal(nodes.get('studioDraftStatus').textContent,'00:22 · 9:16 · Rebuild required');
  run('delete state.project.editor_sequence;state.draftDirtyReasons.clear();updateStudioStatus();');
  assert.equal(nodes.get('studioDraftStatus').textContent,'00:10 · 9:16');
});

test('transcript source target uses canonical analyzed audio provenance, not an unrelated field or current mixer guess',()=>{
  const {run} = app();
  run(`state.project.analysis.audio_source='B';state.project.analysis.transcript.source_slot='A';`);
  assert.equal(run('transcriptSourceSlot()'),'B');
  run(`delete state.project.analysis.audio_source;state.project.draft.audio_source='B';state.project.manual.source_mixer.audio_slot='A';`);
  assert.equal(run('transcriptSourceSlot()'),'B');
  run(`state.project.analysis.audio_source='b';`);
  assert.equal(run('transcriptSourceSlot()'),'B');
});

for(const operation of ['duplicate','move','insert']) test(`${operation} completion cannot select, seek or retarget a newly opened project`,async()=>{
  const {run} = app();
  run(`bindEvents();state.manualSelection={start:0,end:3};
    globalThis.originalProject=state.project;
    applyManualEdit=()=>new Promise(resolve=>{globalThis.finish=resolve;});`);
  if(operation==='duplicate')run('globalThis.pending=elements.clipDuplicate.listeners.click();');
  if(operation==='move')run(`globalThis.pending=handleTimelineEdit({action:'track_move',slot:'A',clip_id:'a1',start:4});`);
  if(operation==='insert')run(`openSourceInsert();globalThis.pending=insertSourceFootage({preventDefault(){}});`);
  run(`state.project={...originalProject,id:'another-project'};state.editTarget='B';
    state.manualSelection={start:10,end:11};selections=[];seeks=[];finish(originalProject);`);
  await run('pending');
  assert.equal(run('state.project.id'),'another-project');
  assert.equal(run('activeEditTarget()'),'B');
  assert.deepEqual(plain(run('state.manualSelection')),{start:10,end:11});
  assert.deepEqual(plain(run('selections')),[]);
  assert.deepEqual(plain(run('seeks')),[]);
});
