const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const plain = value => JSON.parse(JSON.stringify(value));
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');

function app() {
  const nodes = new Map();
  const element = (id = '') => {
    const children = new Map();
    return {id, value:'', textContent:'', dataset:{}, hidden:false, disabled:false, attrs:{}, listeners:{},
      style:{setProperty(){}}, classList:{add(){},remove(){},toggle(){}},
      setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];},
      addEventListener(key,callback){this.listeners[key]=callback;},
      querySelector(key){if(!children.has(key))children.set(key,element(key));return children.get(key);},
      querySelectorAll(){return [];}, append(){}, focus(){}, scrollIntoView(){},
      showModal(){this.open=true;this.shown=(this.shown||0)+1;},
    };
  };
  const document = {getElementById(id){if(!nodes.has(id))nodes.set(id,element(id));return nodes.get(id);},
    createElement:element,querySelector(){return null;},querySelectorAll(){return [];},addEventListener(){}};
  const context = vm.createContext({document,console,dictionaries:{en:{}},setTimeout,clearTimeout,
    window:{addEventListener(){}},requestAnimationFrame:callback=>callback(),performance:{now:()=>0}});
  const run = code=>vm.runInContext(code,context);
  for (const file of ['source-tracks.js','timeline.js','keyboard.js']) {
    run(fs.readFileSync(path.join(__dirname,'../web',file),'utf8').replace(/^export /gm,''));
  }
  run(source);
  run(`cacheElements();
    state.project={id:'friendly',name:'Together fixture',revision:7,settings:{fps:30,aspect:'9:16'},
      sources:{A:{duration:20,has_audio:true},B:{duration:30,has_audio:true}},manual:{},
      analysis:{audio_source:'B'},draft:{output_duration:6,keep_ranges:[{start:4,end:7},{start:14,end:17}]},
      editor_sequence:{duration:6,active:false,sequence:{version:1,duration:6,camera_plan:[{start:0,end:6,camera:'stacked'}]},
        source_tracks:{A:[{id:'a1',start:0,end:3,source_start:4},{id:'a2',start:3,end:6,source_start:14}],
          B:[{id:'b1',start:0,end:2,source_start:6},{id:'b2',start:2,end:6,source_start:10}]}}};
    state.studio.open=true;
    globalThis.requests=[];globalThis.selections=[];globalThis.seeks=[];globalThis.messages=[];globalThis.targets=[];
    globalThis.savedRevision=7;globalThis.flushCount=0;globalThis.renderLocks=0;
    state.timeline={playhead:1,tool:'select',cancelPendingCut(){},setEditTarget(target){targets.push(target);},
      selectRange(start,end){state.manualSelection={start,end};selections.push({start,end});},
      clearSelection(){state.manualSelection=null;},setProject(){},draw(){}};
    globalThis.realRenderReadiness=renderReadiness;
    renderManualControls=renderSourceMixer=renderReadiness=hydrateSettings=hydrateSourceMixerLayout=highlightTranscriptSelection=()=>{};
    renderDraft=renderDraftActions=renderActiveJobBar=renderModelStatus=()=>{};
    pausePreview=pauseAllMedia=()=>{state.preview.playing=false;};
    previewTimelineTime=()=>state.timeline.playhead;
    seekSourcePreview=time=>seeks.push(time);
    openStudioTab=()=>true;toast=message=>messages.push(message);
    flushProjectSaves=async()=>{flushCount++;};
    saveQueueFor=()=>({revision:savedRevision});rememberProjectRevision=project=>savedRevision=project.revision;
    acquireJobStartLock=()=>{renderLocks++;return null;};
    api=async(url,options)=>{requests.push({url,method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null});
      return {project:{...state.project,revision:state.project.revision+1}};};
  `);
  return {run,nodes};
}

test('new sequence editors default to Together and unavailable source targets return to Together',()=>{
  const {run}=app();
  assert.equal(run('activeEditTarget()'),'edit');
  run(`setEditTarget('B');`);
  assert.equal(run('activeEditTarget()'),'B');
  run(`delete state.project.sources.B;`);
  assert.equal(run('activeEditTarget()'),'edit');
  run(`setEditTarget('edit');`);
  assert.equal(run('activeEditTarget()'),'edit');
});

test('Together selection uses every A/B clip boundary, independent targets retain their own original media',()=>{
  const {run}=app();
  assert.deepEqual(plain(run('targetEditableClips()')),[
    {start:0,end:2,index:0},{start:2,end:3,index:1},{start:3,end:6,index:2},
  ]);
  assert.deepEqual(plain(run(`targetEditableClips('A')`)),[
    {id:'a1',start:0,end:3,source_start:4},{id:'a2',start:3,end:6,source_start:14},
  ]);
  assert.deepEqual(plain(run(`targetEditableClips('B')`)),[
    {id:'b1',start:0,end:2,source_start:6},{id:'b2',start:2,end:6,source_start:10},
  ]);
});

test('switching Together, A, and B preserves the selected time and mark-in',()=>{
  const {run}=app();
  run(`state.manualSelection={start:1,end:2};state.markIn={projectId:'friendly',time:.5};`);
  for (const target of ['A','B','edit']) {
    run(`setEditTarget('${target}');`);
    assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:2});
    assert.deepEqual(plain(run('state.markIn')),{projectId:'friendly',time:.5});
    assert.equal(run('activeEditTarget()'),target);
  }
  run(`setEditTarget('A',true);`);
  assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:2});
  assert.deepEqual(plain(run('targets')),['A','B','edit']);
});

test('Together Remove closes time on both tracks instead of secretly using the transcript audio lane',async()=>{
  const {run}=app();
  run('state.manualSelection={start:1,end:2};');
  await run(`runManualRangeEdit('delete_range')`);
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_ripple_delete',start:1,end:2,expected_revision:7});
  assert.equal(run('flushCount'),1);
});

test('per-source Remove remains independent even when transcript audio comes from the other source',async()=>{
  const {run}=app();
  run(`setEditTarget('A');state.manualSelection={start:1,end:2};`);
  await run(`runManualRangeEdit('delete_range')`);
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_remove_range',slot:'A',start:1,end:2,expected_revision:7});
});

test('Together timeline split and delete dispatch linked operations without a source slot',async()=>{
  const {run}=app();
  await run(`handleTimelineEdit({action:'split',time:1.5})`);
  await run(`handleTimelineEdit({action:'delete_range',start:2,end:3})`);
  assert.deepEqual(plain(run('requests.map(item=>item.body)')),[
    {action:'sequence_split_all',time:1.5,expected_revision:7},
    {action:'sequence_ripple_delete',start:2,end:3,expected_revision:8},
  ]);
});

test('explicit timeline source targeting overrides Together without changing the other track',async()=>{
  const {run}=app();
  await run(`handleTimelineEdit({action:'split',target:'B',time:1.5})`);
  await run(`handleTimelineEdit({action:'delete_range',target:'A',start:2,end:3})`);
  assert.deepEqual(plain(run('requests.map(item=>item.body)')),[
    {action:'sequence_split',slot:'B',time:1.5,expected_revision:7},
    {action:'sequence_remove_range',slot:'A',start:2,end:3,expected_revision:8},
  ]);
});

test('Together move closes the origin and selects only the moved block after save',async()=>{
  const {run}=app();
  await run(`handleTimelineEdit({action:'sequence_move_range',start:0,end:2,to:4})`);
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_move_range',start:0,end:2,to:4,mode:'ripple',expected_revision:7});
  assert.deepEqual(plain(run('selections.at(-1)')),{start:4,end:6});
  assert.equal(run('seeks.at(-1)'),4);
  assert.equal(run('activeEditTarget()'),'edit');
});

test('independent A move closes the origin on A without moving B',async()=>{
  const {run}=app();
  run(`setEditTarget('A');`);
  await run(`handleTimelineEdit({action:'track_move',slot:'A',clip_id:'a1',start:4})`);
  assert.equal(run('requests[0].body.action'),'sequence_move');
  assert.equal(run('requests[0].body.mode'),'ripple');
  assert.equal(run('requests[0].body.clip_id'),'a1');
});

test('body drop beyond the end selects the clamped position, not a phantom tail',async()=>{
  const {run}=app();
  await run(`handleTimelineEdit({action:'sequence_move_range',start:0,end:2,to:100})`);
  assert.equal(run('requests[0].body.to'),4);
  assert.deepEqual(plain(run('selections.at(-1)')),{start:4,end:6});
});

test('Together left trim selects ripple-adjusted times; independent trim keeps its source clock',async()=>{
  const {run}=app();
  await run(`handleTimelineEdit({action:'sequence_trim_edge',start:0,end:2,edge:'start',time:1})`);
  assert.equal(run('requests[0].body.action'),'sequence_trim_edge');
  assert.deepEqual(plain(run('selections.at(-1)')),{start:0,end:1});
  await run(`handleTimelineEdit({action:'sequence_trim_edge',slot:'A',start:0,end:2,edge:'start',time:1})`);
  assert.deepEqual(plain(run('selections.at(-1)')),{start:1,end:2});
});

test('a saved split selects the right-hand cut, not the whole video',async()=>{
  const {run}=app();
  run(`applyManualEdit=async()=>{
    state.project.editor_sequence.source_tracks.A=[{id:'left',start:0,end:1,source_start:0},{id:'right',start:1,end:2,source_start:1}];
    state.project.editor_sequence.source_tracks.B=[];
    return state.project;
  };`);
  await run(`handleTimelineEdit({action:'split',time:1.004})`);
  assert.deepEqual(plain(run('selections.at(-1)')),{start:1,end:2});
});

test('a delayed Together move cannot select or seek a newly opened project',async()=>{
  const {run}=app();
  run(`globalThis.oldProject=state.project;
    applyManualEdit=()=>new Promise(resolve=>{globalThis.finish=resolve;});
    globalThis.pending=handleTimelineEdit({action:'sequence_move_range',start:0,end:2,to:4});
    state.project={...oldProject,id:'other'};state.manualSelection={start:1,end:3};
    finish(oldProject);`);
  await run('pending');
  assert.deepEqual(plain(run('selections')),[]);
  assert.deepEqual(plain(run('seeks')),[]);
  assert.deepEqual(plain(run('state.manualSelection')),{start:1,end:3});
});

test('Together revision conflict refreshes once and never replays a stale destructive range',async()=>{
  const {run}=app();
  run(`api=async(url,options)=>{
    requests.push({url,method:options?.method||'GET'});
    if(options?.method==='POST')throw Object.assign(new Error('conflict'),{status:409,code:'revision_conflict'});
    return {project:{...state.project,revision:10}};};state.manualSelection={start:1,end:2};`);
  assert.equal(await run(`handleTimelineEdit({action:'delete_range',start:1,end:2})`),null);
  assert.deepEqual(plain(run('requests.map(item=>item.method)')),['POST','GET']);
  assert.equal(run('state.project.revision'),10);
  assert.equal(run('state.manualSelection'),null);
});

test('empty sequence durations remain zero instead of falling back to physical media or old draft length',()=>{
  const {run}=app();
  run(`state.project.editor_sequence.duration=0;state.project.editor_sequence.sequence.duration=0;
    state.project.editor_sequence.source_tracks={A:[],B:[]};`);
  assert.equal(run('editorDuration()'),0);
  assert.equal(run('editDuration()'),0);
  assert.equal(run('hasTimelineFootage()'),false);
  assert.deepEqual(plain(run('targetEditableClips()')),[]);
  assert.equal(run('state.project.sources.A.duration'),20);
  assert.equal(run('state.project.draft.output_duration'),6);
});

test('timeline footage availability respects both explicit empty lanes and a valid B-only sequence',()=>{
  const {run}=app();
  run(`state.project.editor_sequence.source_tracks.A=[];`);
  assert.equal(run('hasTimelineFootage()'),true,'B-only edit is exportable');
  run(`state.project.editor_sequence.source_tracks.B=[];`);
  assert.equal(run('hasTimelineFootage()'),false,'positive-duration gaps are not exportable footage');
  run(`delete state.project.editor_sequence;`);
  assert.equal(run('hasTimelineFootage()'),true,'legacy drafts retain their original readiness contract');
  run('state.project=null;');
  assert.equal(run('hasTimelineFootage()'),false);
});

test('empty timeline disables all primary export buttons',()=>{
  const {run,nodes}=app();
  run(`state.project.editor_sequence.source_tracks={A:[],B:[]};realRenderReadiness();`);
  for (const id of ['renderButton','resultRenderButton','studioRenderButton']) assert.equal(nodes.get(id).disabled,true,id);
});

test('empty timeline cannot open a new export or acquire a render job lock',async()=>{
  const {run,nodes}=app();
  run(`state.sourceReview={open(){return true;}};state.project.editor_sequence.duration=0;state.project.editor_sequence.sequence.duration=0;
    state.project.editor_sequence.source_tracks={A:[],B:[]};openExportDialog();`);
  assert.equal(nodes.get('exportDialog').shown||0,0);
  await run('startExport()');
  assert.equal(run('renderLocks'),0);
  assert.equal(run('requests.length'),0);
  assert.match(run('messages.join(" ")'),/footage|empty|timeline/i);
});

test('Add footage in Together inserts on the chosen source while preserving linked insertion semantics',async()=>{
  const {run,nodes}=app();
  assert.equal(run('openSourceInsert()'),true);
  assert.equal(nodes.get('sourceInsertSlot').value,'B');
  assert.equal(nodes.get('sourceInsertSlot').disabled,false);
  nodes.get('sourceInsertSlot').value='A';nodes.get('sourceInsertIn').value='4';
  nodes.get('sourceInsertOut').value='6';nodes.get('sourceInsertAt').value='2';
  await run('insertSourceFootage({preventDefault(){}})');
  assert.deepEqual(plain(run('requests[0].body')),{action:'sequence_insert_linked',slot:'A',start:2,source_start:4,source_end:6,expected_revision:7});
  assert.equal(run('activeEditTarget()'),'edit');
});

test('changing the editing target closes Add footage, while reselecting the same target keeps it open',()=>{
  const {run,nodes}=app();
  run('openSourceInsert();');
  assert.equal(nodes.get('sourceInsertForm').hidden,false);
  run(`setEditTarget('edit');`);
  assert.equal(nodes.get('sourceInsertForm').hidden,false);
  run(`setEditTarget('A');`);
  assert.equal(nodes.get('sourceInsertForm').hidden,true);
  run(`openSourceInsert();setEditTarget('B',true);`);
  assert.equal(nodes.get('sourceInsertForm').hidden,true,'canvas target changes cannot leave stale insertion controls open');
});

test('a stale Add footage submission cannot insert with the previous Together or independent scope',async()=>{
  for(const [opened,current] of [['edit','A'],['B','edit'],['A','B']]) {
    const {run,nodes}=app();
    run(`setEditTarget('${opened}');openSourceInsert();state.editTarget='${current}';`);
    // Simulate a delayed form event without calling the normal close handler.
    nodes.get('sourceInsertForm').hidden=false;
    await run('insertSourceFootage({preventDefault(){}})');
    assert.equal(nodes.get('sourceInsertForm').hidden,true);
    assert.equal(run('requests.length'),0);
    assert.equal(run('activeEditTarget()'),current);
  }
});

test('publishing the preview playhead refreshes Split availability using the actual edit cursor',()=>{
  const {run,nodes}=app();
  run(`globalThis.splitChecks=[];state.timeline.setPlayhead=time=>{state.timeline.playhead=time;};
    state.timeline.canSplitAt=time=>{splitChecks.push(time);return time>0&&time<6;};`);
  run('publishPreviewPlayhead(0);');
  assert.equal(nodes.get('manualSplit').disabled,true);
  run('publishPreviewPlayhead(2);');
  assert.equal(nodes.get('manualSplit').disabled,false);
  assert.equal(run('state.timeline.playhead'),2);
  run('publishPreviewPlayhead(10);');
  assert.equal(nodes.get('manualSplit').disabled,true);
  assert.equal(run('state.timeline.playhead'),6,'cursor is clamped to edited duration');
  assert.deepEqual(plain(run('splitChecks')),[0,2,6]);
  for(const flag of ['manualEditBusy','transcriptSaving']) {
    run(`state.${flag}=true;publishPreviewPlayhead(2);`);
    assert.equal(nodes.get('manualSplit').disabled,true,flag);
    run(`state.${flag}=false;`);
  }
});

test('Full source preview maps its cursor to the edit clock before checking Split availability',()=>{
  const {run,nodes}=app();
  run(`state.preview.mode='source';globalThis.splitChecks=[];
    state.timeline.setPlayhead=time=>{state.timeline.playhead=time;};
    state.timeline.canSplitAt=time=>{splitChecks.push(time);return time===1;};
    publishPreviewPlayhead(5);`);
  assert.equal(run('state.preview.editCursor'),1);
  assert.equal(run('state.timeline.playhead'),1);
  assert.equal(nodes.get('manualSplit').disabled,false);
  assert.deepEqual(plain(run('splitChecks')),[1]);
});

test('keyboard Split rejects unsafe cut positions before intercepting the shortcut or submitting an edit',()=>{
  const {run}=app();
  run(`globalThis.edits=[];globalThis.splitChecks=[];globalThis.prevented=0;
    handleTimelineEdit=edit=>edits.push(edit);
    state.timeline.canSplitAt=time=>{splitChecks.push(time);return time===1;};
    globalThis.splitKey=()=>({key:'s',code:'KeyS',target:elements.timelineCanvas,preventDefault(){prevented++;}});
    state.timeline.playhead=.001;handleEditorShortcut(splitKey());`);
  assert.deepEqual(plain(run('edits')),[]);
  assert.equal(run('prevented'),0);
  run('state.timeline.playhead=1;handleEditorShortcut(splitKey());');
  assert.deepEqual(plain(run('edits')),[{action:'split',time:1}]);
  assert.equal(run('prevented'),1);
  assert.deepEqual(plain(run('splitChecks')),[.001,1]);
});

for(const [mode,fps,sourceFps] of [['edit',60,24],['edit',25,60],['source',60,24],['source',25,60]]) {
  test(`${mode} frame stepping uses ${mode==='edit'?'the edit':'original source'} frame rate (${fps}/${sourceFps} FPS)`,()=>{
    const {run}=app();
    run(`state.project.settings.fps=${fps};state.project.sources.A.fps=${sourceFps};state.preview.mode='${mode}';
      state.timeline.playhead=2;previewPlaybackTime=()=>5;globalThis.rawSeeks=[];
      seekPreview=time=>rawSeeks.push(time);
      globalThis.frameKey=key=>({key,target:elements.timelineCanvas,preventDefault(){}});
      handleEditorShortcut(frameKey('ArrowRight'));handleEditorShortcut(frameKey('ArrowLeft'));`);
    const actual=plain(run(mode==='edit'?'seeks':'rawSeeks'));
    const base=mode==='edit'?2:5, step=1/(mode==='edit'?fps:sourceFps);
    assert.equal(actual.length,2);
    assert.ok(Math.abs(actual[0]-(base+step))<1e-10);
    assert.ok(Math.abs(actual[1]-(base-step))<1e-10);
    assert.deepEqual(plain(run(mode==='edit'?'rawSeeks':'seeks')),[],'step must use the matching coordinate space');
  });
}

test('legacy non-sequence frame stepping retains original-source FPS',()=>{
  const {run}=app();
  run(`delete state.project.editor_sequence;state.project.settings.fps=60;state.project.sources.A.fps=24;
    state.timeline.playhead=2;handleEditorShortcut({key:'ArrowRight',target:elements.timelineCanvas,preventDefault(){}});`);
  assert.ok(Math.abs(run('seeks.at(-1)')-(2+1/24))<1e-10);
});
