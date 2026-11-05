const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = value => JSON.parse(JSON.stringify(value));
const reselection = /select.*again|reselect|changed/i;

function app() {
  const nodes = new Map();
  const element = id => ({ id, value: '', dataset: {}, hidden: false,
    style: { setProperty() {} }, classList: { add() {}, remove() {}, toggle() {} },
    setAttribute() {}, removeAttribute() {}, addEventListener() {}, focus() {},
    replaceChildren(...children) { this.children=children; },
    querySelector() { return element('child'); }, querySelectorAll() { return []; } });
  const document = {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, element(id)); return nodes.get(id); },
    querySelector() { return null; }, querySelectorAll() { return []; }, addEventListener() {},
  };
  const context = vm.createContext({ document, console, dictionaries: { en: {} }, setTimeout, clearTimeout,
    window: { addEventListener() {} }, performance: { now: () => 0 }, requestAnimationFrame: fn => fn() });
  const run = code => vm.runInContext(code, context);
  for (const file of ['source-tracks.js', 'timeline.js', 'keyboard.js']) {
    run(fs.readFileSync(path.join(__dirname, '../web', file), 'utf8').replace(/^export /gm, ''));
  }
  run(source);
  run(`cacheElements();
    state.project={id:'project_123456abcdef',name:'Synthetic identity fixture',revision:7,settings:{fps:30},
      sources:{A:{duration:20,generation:'genA'},B:{duration:20,generation:'genB'}},
      manual:{source_tracks:{A:[{id:'legacy',start:0,end:20,source_start:0}]},
        media_clips:[{id:'asset-clip',start:0,end:3}],text_clips:[{id:'title',start:0,end:3}]},
      draft:{keep_ranges:[{start:4,end:10}],cuts:[{start:0,end:4},{start:10,end:20}],output_duration:6},
      editor_sequence:{duration:6,active:false,sequence:{duration:6,camera_plan:[{start:0,end:6,camera:'A'}]},
        source_tracks:{A:[{id:'a1',start:0,end:3,source_start:4},{id:'a2',start:3,end:6,source_start:14}],
          B:[{id:'b1',start:0,end:6,source_start:6}]}},
      timeline_bindings:{version:1,revision:7,clock:'edit',selection_scope:'project_revision',
        id_actions:['sequence_split','sequence_trim','sequence_speed'],
        sources:{'primary:A:genA':{kind:'primary',legacy_slot:'A',binding_state:'current_generation',generation:'genA'},
          'primary:B:genB':{kind:'primary',legacy_slot:'B',binding_state:'current_generation',generation:'genB'}},
        tracks:[{id:'track:project_123456abcdef:A',legacy_slot:'A',source_ref:'primary:A:genA',can_edit_by_id:true},
          {id:'track:project_123456abcdef:B',legacy_slot:'B',source_ref:'primary:B:genB',can_edit_by_id:true}],
        clips:[{collection:'primary',track_id:'track:project_123456abcdef:A',id:'a1',source_ref:'primary:A:genA',state:{start:0,end:3,source_start:4}},
          {collection:'primary',track_id:'track:project_123456abcdef:A',id:'a2',source_ref:'primary:A:genA',state:{start:3,end:6,source_start:14}},
          {collection:'primary',track_id:'track:project_123456abcdef:B',id:'b1',source_ref:'primary:B:genB',state:{start:0,end:6,source_start:6}},
          {collection:'library',track_id:null,id:'a1',source_ref:'asset:synthetic',state:{start:1,end:2}}]}};
    state.studio.open=true;state.preview.mode='edit';state.manualSelection={start:0,end:3};
    globalThis.requests=[];globalThis.messages=[];globalThis.flushCount=0;globalThis.clearCount=0;
    globalThis.savedRevision=7;globalThis.renderCount=0;globalThis.seeks=[];
    state.timeline={playhead:1,cancelPendingCut(){},cancelGesture(){},scheduleDraw(){},setProject(){},
      clearSelection(){clearCount++;state.manualSelection=null;},
      selectRange(start,end){state.manualSelection={start,end};}};
    foregroundBusy=()=>false;
    renderReadiness=renderManualControls=renderSourceMixer=hydrateSettings=renderCaptionInspector=()=>{};
    renderDraft=()=>renderCount++;
    pausePreview=pauseAllMedia=()=>{state.preview.playing=false;};
    previewTimelineTime=()=>state.timeline.playhead;
    seekSourcePreview=time=>seeks.push(time);
    setManualSelection=value=>{state.manualSelection=value;};
    toast=message=>messages.push(message);
    flushProjectSaves=async()=>{flushCount++;};
    saveQueueFor=()=>({revision:savedRevision});
    rememberProjectRevision=project=>savedRevision=project.revision;
    api=async(url,options)=>{requests.push({url,method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null});
      const project=JSON.parse(JSON.stringify(state.project));project.revision++;
      if(project.timeline_bindings)project.timeline_bindings.revision=project.revision;
      return {project};};
  `);
  return { run, nodes };
}

test('identity binds a versioned primary lane and snapshots only its primary clip rows', () => {
  const { run } = app();
  const before = run('JSON.stringify(state.project)');
  const identity = plain(run("timelineEditIdentity(state.project,'sequence_split',{slot:'A',time:1})"));
  assert.deepEqual(identity.fields, { track_id: 'track:project_123456abcdef:A', source_ref: 'primary:A:genA' });
  assert.deepEqual(JSON.parse(identity.selection), plain(run("state.project.timeline_bindings.clips.filter(row=>row.collection==='primary'&&row.track_id==='track:project_123456abcdef:A')")));
  assert.equal(run('JSON.stringify(state.project)'), before);
});

for (const [name, setup, action] of [
  ['old server', 'delete state.project.timeline_bindings;', 'sequence_split'],
  ['future projection', 'state.project.timeline_bindings.version=2;', 'sequence_split'],
  ['unadvertised action', 'state.project.timeline_bindings.id_actions=[];', 'sequence_split'],
  ['unversioned lane', 'state.project.timeline_bindings.tracks[0].can_edit_by_id=false;', 'sequence_split'],
  ['missing lane', 'state.project.timeline_bindings.tracks=[];', 'sequence_split'],
  ['unsupported identity action', '', 'sequence_move'],
]) {
  test(`identity preserves legacy payload fallback for ${name}`, () => {
    const { run } = app(); run(setup);
    assert.equal(run(`timelineEditIdentity(state.project,'${action}',{slot:'A',clip_id:'a1',time:1})`), null);
  });
}

test('a binding from another project revision requires reselection', () => {
  const { run } = app(); run('state.project.timeline_bindings.revision=6;');
  assert.throws(() => run("timelineEditIdentity(state.project,'sequence_split',{slot:'A',time:1})"), reselection);
});

for (const action of ['sequence_trim', 'sequence_speed']) {
  test(`${action} requires the selected clip on the addressed primary lane`, () => {
    const { run } = app();
    assert.throws(() => run(`timelineEditIdentity(state.project,'${action}',{slot:'B',clip_id:'a1'})`), reselection);
    assert.throws(() => run(`timelineEditIdentity(state.project,'${action}',{slot:'A',clip_id:'deleted'})`), reselection);
    assert.equal(run(`timelineEditIdentity(state.project,'${action}',{slot:'A',clip_id:'a1'}).fields.source_ref`), 'primary:A:genA');
  });
}

for (const [input, expected, detail] of [
  ['track_split', 'sequence_split', { slot: 'B', time: 1 }],
  ['track_trim', 'sequence_trim', { slot: 'A', clip_id: 'a1', start: 0, end: 2, source_start: 4 }],
  ['sequence_speed', 'sequence_speed', { slot: 'A', clip_id: 'a1', speed: 1.5 }],
]) {
  test(`${input} submits identity fields while keeping the existing action payload`, async () => {
    const { run } = app();
    await run(`applyManualEdit('${input}',${JSON.stringify(detail)})`);
    const body = plain(run('requests[0].body'));
    assert.deepEqual(body, { action: expected, ...detail, expected_revision: 7,
      track_id: `track:project_123456abcdef:${detail.slot}`, source_ref: `primary:${detail.slot}:gen${detail.slot}` });
    assert.equal(Object.hasOwn(body, 'selection'), false, 'selection fingerprint is local, never sent to the API');
  });
}

test('a pending settings save may advance revision while preserving the displayed lane identity', async () => {
  const { run } = app();
  run(`flushProjectSaves=async()=>{flushCount++;state.project.revision=8;
    state.project.timeline_bindings.revision=8;savedRevision=8;};`);
  await run("applyManualEdit('sequence_trim',{slot:'A',clip_id:'a1',start:0,end:2,source_start:4})");
  assert.equal(run('requests.length'), 1);
  assert.equal(run('requests[0].body.expected_revision'), 8);
  assert.equal(run('requests[0].body.source_ref'), 'primary:A:genA');
});

test('a text flush cannot replace the displayed clip geometry before identity capture', async () => {
  const { run } = app();
  run(`state.textStudio={render(){},async flush(){
    state.project.timeline_bindings.clips[0].state.end=2.5;
    state.project.revision=8;state.project.timeline_bindings.revision=8;savedRevision=8;
    return true;
  }};`);
  assert.equal(await run("applyManualEdit('sequence_trim',{slot:'A',clip_id:'a1',start:0,end:2,source_start:4})"), null);
  assert.equal(run('requests.filter(row=>row.method===\'POST\').length'), 0);
  assert.match(run('messages.at(-1)'), reselection);
  assert.equal(run('state.manualEditBusy'), false);
  assert.equal(run('state.manualEditPromise'), null);
});

test('switching projects during text flush cannot apply the displayed selection to the new project', async () => {
  const { run } = app();
  run(`state.textStudio={render(){},async flush(){
    state.project={...state.project,id:'project_fedcba654321'};
    return true;
  }};`);
  assert.equal(await run("applyManualEdit('sequence_split',{slot:'A',time:1})"), null);
  assert.deepEqual(plain(run('requests')), []);
  assert.equal(run('state.manualEditBusy'), false);
  assert.equal(run('state.manualEditPromise'), null);
});

for (const [name, change] of [
  ['source generation', "state.project.timeline_bindings.tracks[0].source_ref='primary:A:replacement';"],
  ['clip geometry', 'state.project.timeline_bindings.clips[0].state.end=2.5;'],
]) {
  test(`a pending save that changes ${name} aborts before an edit POST`, async () => {
    const { run } = app();
    run(`flushProjectSaves=async()=>{flushCount++;state.project.revision=8;state.project.timeline_bindings.revision=8;savedRevision=8;${change}};`);
    assert.equal(await run("applyManualEdit('sequence_trim',{slot:'A',clip_id:'a1',start:0,end:2,source_start:4})"), null);
    assert.equal(run('requests.filter(row=>row.method===\'POST\').length'), 0);
    assert.match(run('messages.at(-1)'), reselection);
    assert.equal(run('state.manualEditBusy'), false);
    assert.equal(run('state.manualEditPromise'), null);
  });
}

test('a stale projection after a pending save cannot address an edit with a newer revision', async () => {
  const { run } = app();
  run('flushProjectSaves=async()=>{flushCount++;state.project.revision=8;savedRevision=8;};');
  assert.equal(await run("applyManualEdit('sequence_split',{slot:'A',time:1})"), null);
  assert.equal(run('requests.length'), 0);
  assert.match(run('messages.at(-1)'), reselection);
});

for (const code of ['revision_conflict', 'source_binding_conflict']) {
  test(`${code} refreshes the project and clears selection without retrying the edit`, async () => {
    const { run } = app();
    run(`globalThis.remote=JSON.parse(JSON.stringify(state.project));remote.revision=9;remote.timeline_bindings.revision=9;
      api=async(url,options)=>{requests.push({url,method:options?.method||'GET',body:options?.body?JSON.parse(options.body):null});
        if(options?.method==='POST'){const error=new Error('Synthetic conflict');error.status=409;error.code='${code}';throw error;}
        return {project:remote};};`);
    assert.equal(await run("applyManualEdit('sequence_trim',{slot:'A',clip_id:'a1',start:0,end:2,source_start:4})"), null);
    assert.deepEqual(plain(run('requests.map(row=>row.method)')), ['POST', 'GET']);
    assert.equal(run('state.project.revision'), 9);
    assert.equal(run('state.manualSelection'), null);
    assert.ok(run('clearCount') > 0);
    assert.match(run('messages.at(-1)'), reselection);
    assert.equal(run('state.manualEditBusy'), false);
  });
}

for (const [name, setup, action, detail] of [
  ['old server', 'delete state.project.timeline_bindings;', 'sequence_split', { slot: 'A', time: 1 }],
  ['non-ID sequence action', '', 'sequence_move', { slot: 'B', clip_id: 'b1', start: 2 }],
]) {
  test(`${name} submits the existing payload without identity additions`, async () => {
    const { run } = app(); run(setup);
    await run(`applyManualEdit('${action}',${JSON.stringify(detail)})`);
    assert.deepEqual(plain(run('requests[0].body')), { action, ...detail, expected_revision: 7 });
  });
}

test('an unavailable sequence view is detached, empty, and cannot fall back to source playback', () => {
  const { run } = app();
  run("state.project.editor_sequence={error:'Unsupported timeline version'};globalThis.before=JSON.stringify(state.project);globalThis.view=editorProject();");
  assert.equal(run('view.__timelineUnavailable'), true);
  assert.equal(run('timelineDuration(view)'), 0);
  assert.deepEqual(plain(run('view.manual.source_tracks')), { A: [], B: [] });
  assert.deepEqual(plain(run('view.manual.media_clips')), []);
  assert.deepEqual(plain(run('view.manual.text_clips')), []);
  assert.deepEqual(plain(run('view.draft.keep_ranges')), []);
  assert.equal(run('view.draft.output_duration'), 0);
  assert.equal(run('JSON.stringify(state.project)'), run('before'));
  run("state.preview.mode='source';globalThis.playback=playbackProject();");
  assert.equal(run('playback.__timelineUnavailable'), true);
  assert.equal(run('timelineDuration(playback)'), 0);
  assert.deepEqual(plain(run("trackClips(playback,'A')")), []);
});

test('an unavailable sequence rejects manual edits before flushing or issuing requests', async () => {
  const { run } = app();
  run("state.project.editor_sequence={error:'Unsupported timeline version'};state.textStudio={async flush(){throw new Error('must not flush unavailable view');}};");
  assert.equal(await run("applyManualEdit('sequence_split',{slot:'A',time:1})"), null);
  assert.equal(run('flushCount'), 0);
  assert.deepEqual(plain(run('requests')), []);
  assert.match(run('messages.at(-1)'), /timeline|unavailable/i);
});

test('an unavailable sequence blocks opening export before source footage can be used as fallback', () => {
  const { run } = app();
  run("state.project.editor_sequence={error:'Unsupported timeline version'};globalThis.openedSourceReview=0;openSourceReview=()=>openedSourceReview++;requireSavedTranscript=()=>true;");
  run('openExportDialog();');
  assert.equal(run('openedSourceReview'), 0);
  assert.deepEqual(plain(run('requests')), []);
  assert.match(run('messages.at(-1)'), /timeline|unavailable/i);
});
