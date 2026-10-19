const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const appSource = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = value => JSON.parse(JSON.stringify(value));

function harness() {
  const nodes = new Map();
  const node = () => ({
    hidden: false, textContent: '', dataset: {}, listeners: {},
    addEventListener(type, listener) { this.listeners[type] = listener; },
    after(child) { nodes.set(child.id, child); },
  });
  const document = { getElementById: id => nodes.get(id), createElement: node };
  const context = vm.createContext({ document, console, dictionaries: { en: {} }, window: {}, setTimeout, clearTimeout });
  const run = code => vm.runInContext(code, context);
  run(fs.readFileSync(path.join(__dirname, '../web/source-tracks.js'), 'utf8').replace(/^export /gm, ''));
  run(appSource);
  run(`
    state.project = {id:'actual-geometry-copy', sources:{A:{duration:2285.583,has_audio:true},B:{duration:158.35,video_duration:158.35}},
      manual:{source_mixer:{screen_slot:'A',camera_slot:'B'}}, analysis:{sync:{offset:0,confidence:.017,reliable:false}},
      draft:{keep_ranges:[{start:244,end:264.6},{start:1086.4,end:1101.8},{start:1185.4,end:1216.2},{start:1307.4,end:1330.6}]},
      editor_sequence:{duration:90,source_tracks:{A:[{id:'a',start:0,end:20.6,source_start:244}],B:[]},sequence:{camera_plan:[]}}};
    sourceMixerControlBusy=()=>false;
  `);
  context.coverageNode = node(); context.helpNode = node();
  run('elements.sourceBCoverage=coverageNode; elements.sourceMixerHelp=helpNode;');
  return { run, nodes };
}

test('actual nonoverlap geometry warns about empty edited B without changing original clips', () => {
  const { run, nodes } = harness();
  const before = run('JSON.stringify(state.project)');
  run('renderSourceBCoverage();');
  assert.match(run('elements.sourceBCoverage.textContent'), /No B footage is mapped into this edit/);
  assert.match(run('elements.sourceBCoverage.textContent'), /00:00\.000-02:38\.350 on source A's clock/);
  assert.equal(run('elements.sourceBCoverage.dataset.warning'), 'true');
  assert.match(nodes.get('sourceBCoverageNotice').textContent, /Sync unconfirmed/);
  assert.equal(nodes.get('sourceBCoverageNotice').hidden, false);
  assert.equal(nodes.get('sourceBReviewPlacement').hidden, false);
  assert.equal(run('JSON.stringify(state.project)'), before);
});

test('Review B placement opens original B only and never sends a timeline edit', () => {
  const { run, nodes } = harness();
  run(`renderSourceBCoverage(); globalThis.actions=[];
    setEditTarget=slot=>actions.push(['target',slot]); openSourceReview=()=>actions.push(['review']);`);
  nodes.get('sourceBReviewPlacement').listeners.click();
  assert.deepEqual(plain(run('actions')), [['target', 'B'], ['review']]);
  assert.deepEqual(plain(run('state.project.editor_sequence.source_tracks.B')), []);
  run('sourceMixerControlBusy=()=>true;');
  nodes.get('sourceBReviewPlacement').listeners.click();
  assert.equal(run('actions.length'), 2);
});

test('coverage distinguishes signed original alignment from explicit edited gaps', () => {
  const { run } = harness();
  run('delete state.project.editor_sequence;');
  assert.equal(run('sourceBEditCoverage(state.project,sourceMixerSettings()).covered'), 0);
  run('state.project.manual.source_mixer.sync_offset=244;');
  assert.ok(Math.abs(run('sourceBEditCoverage(state.project,sourceMixerSettings()).covered') - 20.6) < 1e-8);
  run('state.project.manual.source_tracks={B:[]};');
  assert.equal(run('sourceBEditCoverage(state.project,sourceMixerSettings()).covered'), 0, 'offset must not repopulate an explicit empty track');
});

test('partial selection coverage merges overlap and clips at actual video end', () => {
  const { run } = harness();
  run(`state.project.sources.B.video_duration=10;
    state.project.editor_sequence.source_tracks.B=[{start:0,end:8,source_start:5},{start:3,end:6,source_start:1}];
    state.manualSelection={start:0,end:8}; renderSourceBCoverage();`);
  assert.equal(run('sourceBEditCoverage(editorProject(),sourceMixerSettings(),state.manualSelection).covered'), 6);
  assert.match(run('elements.sourceBCoverage.textContent'), /B covers 6\.00 of 8\.00 seconds in the selection/);
  run('state.manualSelection={start:3,end:5}; renderSourceBCoverage();');
  assert.match(run('elements.sourceBCoverage.textContent'), /B has footage throughout the selection/);
});

test('automatic zero fallback is never labeled a confirmed start and diagnostics survive', () => {
  const { run } = harness();
  assert.match(run('sourceSyncDescription()'), /^Sync unconfirmed: 0\.00s is not a verified shared start/);
  run(`state.project.analysis.sync={offset:0,confidence:.9,reliable:false,status:'unconfirmed',warning:'No unique shared audio match.'};`);
  assert.match(run('sourceSyncDescription()'), /Sync unconfirmed.*No unique shared audio match/);
  run(`state.project.analysis.sync={offset:12.5,confidence:.9,reliable:true,status:'confirmed'};`);
  assert.match(run('sourceSyncDescription()'), /Automatic audio match: 12\.50s/);
  run('state.project.manual.source_mixer.sync_offset=0;');
  assert.match(run('sourceSyncDescription()'), /Manual offset: 0\.00s.*Check a shared moment/);
});

test('explicit clip and manual placement metadata never become an automatic audio match', () => {
  const { run } = harness();
  for (const [method, label] of [['source_tracks', /Independent B clip placement/], ['manual', /Manual source placement/]]) {
    run(`state.project.analysis.sync={method:'${method}',offset:5,confidence:1,reliable:true};`);
    assert.match(run('sourceSyncDescription()'), label);
    assert.doesNotMatch(run('sourceSyncDescription()'), /^Automatic audio match/);
    run('state.project.analysis.sync.status="unconfirmed";');
    assert.match(run('sourceSyncDescription()'), /^Sync unconfirmed:/, 'explicit unconfirmed status overrides high confidence');
  }
  run(`state.project.analysis.sync={method:'other_measurement',offset:5,confidence:1,reliable:true};`);
  assert.match(run('sourceSyncDescription()'), /^Sync unconfirmed:/, 'unknown methods cannot claim an audio match');
  run(`state.project.analysis.sync={method:'audio_cross_correlation',offset:5,confidence:1,reliable:false};`);
  assert.match(run('sourceSyncDescription()'), /^Sync unconfirmed:/, 'explicit failure overrides legacy confidence');
  run('delete state.project.analysis.sync.reliable;');
  assert.match(run('sourceSyncDescription()'), /^Automatic audio match:/, 'actual legacy audio metadata remains supported');
});

test('explicit picture retiming preserves held video coverage independently from longer source audio', () => {
  const { run } = harness();
  run(`state.project.sources.B={duration:20,video_duration:10,has_audio:true};
    state.project.editor_sequence.duration=20;
    state.project.editor_sequence.source_tracks.B=[{start:0,end:20,source_start:0,video_speed:1,video_source_start:0}];
    renderSourceBCoverage();`);
  assert.equal(run('sourceBEditCoverage(editorProject(),sourceMixerSettings()).covered'), 20);
  assert.match(run('elements.sourceBCoverage.textContent'), /B has footage throughout this edit/);
  assert.doesNotMatch(run('elements.sourceBCoverage.textContent'), /audio.*silent/);
  run('delete state.project.editor_sequence.source_tracks.B[0].video_speed; renderSourceBCoverage();');
  assert.equal(run('sourceBEditCoverage(editorProject(),sourceMixerSettings()).covered'), 10);
  assert.match(run('elements.sourceBCoverage.textContent'), /Gaps in B.s picture/);
  assert.doesNotMatch(run('elements.sourceBCoverage.textContent'), /audio.*silent/, 'picture coverage does not establish audio gaps');
});

test('switching to a one-source project removes stale B coverage and placement notices', () => {
  const { run, nodes } = harness();
  run('renderSourceBCoverage(); delete state.project.sources.B; renderSourceBCoverage();');
  assert.equal(nodes.get('sourceBCoverageNotice').hidden, true);
  assert.equal(nodes.get('sourceBReviewPlacement').hidden, true);
  assert.equal(run('elements.sourceBCoverage.textContent'), '');
});
