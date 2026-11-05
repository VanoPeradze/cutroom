const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

// Unit contracts for the real player seek setter and pending library saves.
// DOM/HTTP are synthetic; this does not qualify browser decoding or playback.
const mediaSource = fs.readFileSync(path.join(__dirname, '../web/media-studio.js'), 'utf8')
  .replace(/^export /gm, '');
const appSource = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = value => JSON.parse(JSON.stringify(value));

function deferred() {
  let resolve;
  const promise = new Promise(yes => { resolve = yes; });
  return {promise, resolve};
}

function mediaClass() {
  const context = vm.createContext({window: {}, document: {},
    performance: {now: () => 1000}, setTimeout: () => 1, clearTimeout() {}});
  vm.runInContext(mediaSource + '\nglobalThis.loadedMediaStudio = MediaStudio;', context);
  return context.loadedMediaStudio;
}

function player(currentTime) {
  let value = currentTime;
  const seeks = [];
  const element = {paused: true, pauseCount: 0, pause() { this.pauseCount++; }};
  Object.defineProperty(element, 'currentTime', {
    get() { return value; },
    set(next) { seeks.push(next); value = next; },
  });
  return {item: {element, token: 0}, seeks};
}

for (const [name, current, target] of [
  ['one-frame-step', 5, 5 + 1 / 30],
  ['short-source-in', 0, .1],
]) {
  test(`paused library video seeks exactly for ${name}`, () => {
    const studio = Object.create(mediaClass().prototype);
    studio.mixer = () => ({master_db: 0});
    const {item, seeks} = player(current);
    studio.syncPlayer(item, target, 1, false, 0);
    assert.deepEqual(seeks, [target], 'a sub-120ms paused seek must reach the media element');
    assert.equal(item.element.currentTime, target);
    assert.equal(item.element.pauseCount, 1);
  });
}

test('an already aligned paused library player does not seek again', () => {
  const studio = Object.create(mediaClass().prototype);
  studio.mixer = () => ({master_db: 0});
  const {item, seeks} = player(5);
  studio.syncPlayer(item, 5, 1, false, 0);
  assert.deepEqual(seeks, []);
  assert.equal(item.element.pauseCount, 1);
});

test('playing library video retains the small drift tolerance', () => {
  const studio = Object.create(mediaClass().prototype);
  studio.mixer = () => ({master_db: 0});
  const {item, seeks} = player(5);
  item.element.paused = false;
  studio.syncPlayer(item, 5 + 1 / 30, 1, true, 0);
  assert.deepEqual(seeks, [], 'normal playback must not continually seek to correct one frame');
  assert.equal(item.wanted, true);
  assert.equal(item.element.pauseCount, 0);
});

function app() {
  const context = vm.createContext({console, MediaStudio: mediaClass(),
    document: {}, window: {}, dictionaries: {en: {}},
    setTimeout: () => 1, clearTimeout() {}, performance: {now: () => 1000}});
  const run = code => vm.runInContext(code, context);
  run(appSource);
  run(`
    state.project={id:'one',name:'Synthetic library fixture',revision:7,settings:{},
      sources:{A:{duration:10}},draft:{engine:'manual'},
      manual:{audio_mixer:{music_db:0},media_clips:[{id:'third',asset_id:'asset',start:10,end:13,volume_db:-2}]}};
    const clone=value=>JSON.parse(JSON.stringify(value));
    globalThis.serverProject=clone(state.project);
    const earlier=clone(serverProject);earlier.manual.media_clips[0].volume_db=-20;earlier.manual.audio_mixer.music_db=-20;
    globalThis.history=[earlier];globalThis.requests=[];globalThis.messages=[];
    globalThis.rejectMedia=false;globalThis.beforeMedia=async()=>{};globalThis.savedRevision=7;
    elements.projectName={value:''};
    state.timeline={cancelPendingCut(){},clearSelection(){},selectRange(){},scheduleDraw(){}};
    state.textStudio={async flush(){return true;},render(){}};
    renderReadiness=renderManualControls=renderSourceMixer=renderCaptionInspector=hydrateSettings=renderDraft=()=>{};
    updateMediaPreview=()=>{};pausePreview=()=>{};previewTimelineTime=()=>11;seekSourcePreview=()=>{};
    toast=message=>messages.push(message);flushProjectSaves=async()=>{};
    saveQueueFor=()=>({revision:savedRevision});rememberProjectRevision=project=>savedRevision=project.revision;
    api=async(url,options)=>{
      const body=JSON.parse(options.body);requests.push({projectId:url.split('/')[3],...body});
      if(body.action==='media_update'||body.action==='set_audio_mixer'){
        await beforeMedia();if(rejectMedia)throw new Error('Synthetic library save failure');
        history.push(clone(serverProject));
        if(body.action==='set_audio_mixer'){
          const {action,expected_revision,...patch}=body;Object.assign(serverProject.manual.audio_mixer,patch);
        }else{
          const {action,expected_revision,clip_id,...patch}=body;
          Object.assign(serverProject.manual.media_clips.find(clip=>clip.id===clip_id),patch);
        }
      }else if(body.action==='undo'){
        assertHistoryAvailable();const revision=serverProject.revision;serverProject=history.pop();serverProject.revision=revision;
      }else throw new Error('Unexpected fixture action '+body.action);
      serverProject.revision++;return {project:clone(serverProject)};
    };
    function assertHistoryAvailable(){if(!history.length)throw new Error('No undo entry');}
    state.mediaStudio=Object.create(MediaStudio.prototype);
    Object.assign(state.mediaStudio,{projectId:'one',selected:'third',pending:new Map(),overrides:new Map(),players:new Map(),saving:null,
      status:{textContent:''},render(){},renderMixer(){},
      options:{project:()=>state.project,edit:(action,detail)=>applyManualEdit(action,detail),
        preview(){},pause(){},busy:()=>state.manualEditBusy}});
  `);
  return {run, context};
}

for (const [name, queue, action, field] of [
  ['clip', "state.mediaStudio.queueClip('third',{volume_db:-9})", 'media_update', 'state.project.manual.media_clips[0].volume_db'],
  ['mixer', 'state.mediaStudio.queueMixer({music_db:-14})', 'set_audio_mixer', 'state.project.manual.audio_mixer.music_db'],
]) {
  test(`Undo flushes a pending ${name} edit first through the real nonrecursive manual-edit callback`, async () => {
    const {run} = app();
    const original = run(field);
    run(queue);
    assert.ok(await run("applyManualEdit('undo')"));
    // Run the scheduled-save equivalent too: it must be empty after Undo.
    assert.equal(await run('state.mediaStudio.flush()'), true);
    assert.deepEqual(plain(run('requests.map(row=>row.action)')), [action, 'undo']);
    assert.equal(run(field), original, 'Undo restores the value before the visible pending adjustment');
    assert.equal(run('state.mediaStudio.pending.size'), 0);
    assert.equal(run('state.mediaStudio.overrides.size'), 0);
    assert.equal(run('state.manualEditBusy'), false);
    assert.equal(run('state.manualEditPromise'), null);
  });
}

test('a failed pending library save prevents Undo from touching the prior history entry', async () => {
  const {run} = app();
  const original = run('JSON.stringify(state.project)');
  run("rejectMedia=true;state.mediaStudio.queueClip('third',{volume_db:-9});");
  assert.equal(await run("applyManualEdit('undo')"), null);
  assert.deepEqual(plain(run('requests.map(row=>row.action)')), ['media_update']);
  assert.equal(run('JSON.stringify(state.project)'), original);
  assert.equal(run('history.length'), 1);
  // applyManualEdit reports the server error through the toast and returns
  // null; MediaStudio separately reports rollback in its persistent status.
  assert.match(run('state.mediaStudio.status.textContent'), /Not saved:.*Previous settings restored/i);
  assert.match(run('messages.join(" ")'), /Synthetic library save failure/);
  assert.equal(run('state.manualEditBusy'), false);
});

test('switching projects during the pending library flush cannot Undo the newly opened project', async () => {
  const {run, context} = app();
  const gate = deferred();context.saveGate = gate.promise;
  run("beforeMedia=()=>saveGate;state.mediaStudio.queueClip('third',{volume_db:-9});");
  const undo = run("applyManualEdit('undo')");
  try {
    for (let turn = 0; turn < 10; turn++) await Promise.resolve();
    assert.deepEqual(plain(run('requests.map(row=>row.action)')), ['media_update'], 'Undo must wait outside the manual-edit busy section');
    run("state.project={id:'two',name:'New project',revision:3,draft:{engine:'manual'},manual:{media_clips:[]}};savedRevision=3;state.mediaStudio.selected='new-project-selection';");
  } finally {
    gate.resolve();
    await undo;
  }
  assert.deepEqual(plain(run('requests.map(row=>[row.projectId,row.action])')), [['one','media_update']]);
  assert.equal(run('state.project.id'), 'two');
  assert.equal(run('state.project.revision'), 3);
  assert.equal(run('state.mediaStudio.selected'), 'new-project-selection');
  assert.equal(run('state.manualEditBusy'), false);
});
