const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..');
const raw = fs.readFileSync(path.join(root, 'web/app.js'), 'utf8');
const source = raw.replace(/^import .*;\r?\n/gm, '').replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const helperSource = fs.readFileSync(path.join(root, 'web/layer-tracks.js'), 'utf8').replace(/^export /gm, '');
const plain = value => JSON.parse(JSON.stringify(value));

function host(version = 2, protection = 2, count = 4) {
  const helper = vm.createContext({});
  vm.runInContext(helperSource, helper);
  const methods = vm.runInContext('({layerTrackState,layerMutationIssue})', helper);
  const counts = {validate: 0, mutation: 0, explicit: 0, busy: 0, writes: 0};
  const element = () => ({dataset: {}, classList: {add() {}, remove() {}, toggle() {}}, addEventListener() {}, querySelector() {return null;}, querySelectorAll() {return [];}});
  const c = vm.createContext({
    console, setTimeout, clearTimeout, window: {addEventListener() {}}, dictionaries: {en: {}},
    document: {getElementById: element, querySelector() {return null;}, querySelectorAll() {return [];}, addEventListener() {}, documentElement: {}},
    layerTrackState(p) {counts.validate++; return methods.layerTrackState(p);},
    layerMutationIssue(...args) {counts.mutation++; return methods.layerMutationIssue(...args);},
    __explicit() {counts.explicit++; return null;}, __busy() {counts.busy++; return false;},
    __write() {counts.writes++; throw new Error('Paint must never write.');},
  });
  const run = code => vm.runInContext(code, c);
  run(source);
  run(`
    globalThis.tid = n => 'track_' + String(n).padStart(32, '0');
    globalThis.mid = n => 'media_' + String(n).padStart(32, '0');
    globalThis.xid = n => 'text_' + String(n).padStart(32, '0');
    state.project = {id:'project_paint',revision:7,settings:{fps:30},draft:{output_duration:8},
      assets:{v:{kind:'video'},a:{kind:'audio'}},manual:{media_clips:[],text_clips:[],
        layer_tracks:{version:${version},tracks:Array.from({length:${count}},(_,i)=>({id:tid(i),
          name:'Track '+i,kind:i===2?'audio':i===3?'text':'visual',
          ...(${version}>=2?{locked:${protection}===2&&i===1}:{}),
          ...(${version}===3&&i!==3?{audio:{gain_db:i===2?-6.123456789:0,muted:i===2}}:{})})),
          ...(${version}===3?{protection_version:${protection}}:{})}}};
    state.project.manual.media_clips=[{id:mid(0),asset_id:'v',track_id:tid(0),start:0,end:2},
      {id:mid(1),asset_id:'v',track_id:tid(1),start:0,end:2,enabled:false},
      {id:mid(2),asset_id:'a',track_id:tid(2),start:1,end:3}];
    state.project.manual.text_clips=[{id:xid(0),track_id:tid(3),start:0,end:2}];
    state.projectViewToken=11;
    state.timeline={project:{...state.project,__sequenceView:true,manual:{...state.project.manual}}};
    state.mediaStudio={pending:new Map()};state.textStudio={pending:new Map()};state.chromaStudio={};
    explicitPendingDraft=__explicit;foregroundBusy=__busy;
    api=applyManualEdit=flushProjectSaves=pauseAllMedia=seekSourcePreview=__write;
  `);
  return {run, c, counts};
}

function parity(h) {
  const result = h.run('trackHeaderReadiness(state.timeline.project)');
  assert.equal(result.project, h.run('state.timeline.project'));
  assert.deepEqual(Object.keys(result).sort(), ['lockIssue', 'project', 'unlockIssue']);
  assert.equal(typeof result.lockIssue, 'string');
  assert.equal(typeof result.unlockIssue, 'string');
  assert.equal(result.lockIssue, h.run('trackLockIssue(tid(0),true)'));
  if (h.run('state.project.manual.layer_tracks?.tracks?.[1]?.locked===true'))
    assert.equal(result.unlockIssue, h.run('trackLockIssue(tid(1),false)'));
  assert.equal(h.counts.writes, 0);
  return result;
}

for (const [version, protection] of [[1,1],[2,2],[3,1],[3,2]]) {
  test(`paint receipt matches direct action readiness for v${version}/pv${protection}`, () => parity(host(version, protection)));
  test(`v${version}/pv${protection} local draft bypass is consumed only for a saved locked row`, () => {
    const h = host(version, protection);
    h.run('explicitPendingDraft=()=>({detail:"Keep the unsaved Chroma candidate."});state.mediaStudio.pending.set(mid(0),{start:2})');
    const result = parity(h);
    assert.match(result.lockIssue, /Chroma/);
    assert.equal(result.unlockIssue, '');
    if (version === 1 || protection === 1) assert.match(h.run('trackLockIssue(tid(1),false)'), /Chroma/);
  });
}

const contexts = [
  'state.project.draft=null',
  'state.captionContextSave={}',
  'state.timeline.gesture={kind:"move"}',
  'state.timeline.scrubbing=true',
  'state.timeline.libraryDragActive=true',
  'state.timeline.mediaSelectionPending={}',
  'state.timeline.mediaSourceOpening={}',
  'state.mediaStudio.frameEditorState={dragging:true}',
  'state.embeddedEditor.dragging=true',
  'state.manualEditBusy=true',
  'foregroundBusy=()=>true',
  'state.transcriptSaving=true',
  'state.timeline.editPending=true',
  'state.mediaStudio.saving=Promise.resolve(true)',
  'state.textStudio.saving=Promise.resolve(true)',
  'state.chromaStudio.saving=Promise.resolve(true)',
  'state.mediaStudio.pending.set(mid(0),{start:2})',
  'state.textStudio.pending.set(xid(0),{text:"kept"})',
  'state.timeline.trackLockPending={}',
  'explicitPendingDraft=()=>({detail:"Save or discard captions."})',
  'explicitPendingDraft=()=>({detail:"Save or discard track level."});state.captionContextSave={};state.timeline.gesture={};state.manualEditBusy=true',
  'state.captionContextSave={};state.timeline.gesture={};state.manualEditBusy=true',
  'state.timeline.gesture={};state.manualEditBusy=true',
];
for (const setup of contexts) test(`paint and direct guard reason ordering: ${setup}`, () => {const h=host(3,2); h.run(setup); parity(h);});

for (const setup of [
  'state.project.manual.layer_tracks.version=99',
  'state.project.manual.layer_tracks.tracks[0].audio.gain_db=NaN',
  'state.project.manual.layer_tracks.tracks[0].audio.muted="yes"',
  'state.project.manual.layer_tracks.tracks[3].locked="yes"',
  'state.project.manual.layer_tracks.protection_version=1',
  'state.project.manual.media_clips[0].track_id=tid(999)',
  'state.project.manual.media_clips.push({...state.project.manual.media_clips[0],id:mid(99)})',
  'state.project.manual.text_clips=null',
  'delete state.project.manual.layer_tracks;delete state.timeline.project.manual.layer_tracks',
]) test(`complete saved-model validation fails closed: ${setup}`, () => {
  const h=host(3,2); h.run(setup); const r=parity(h); assert.ok(r.lockIssue); assert.equal(r.unlockIssue,r.lockIssue);
});

test('legacy project without saved membership stays compatible without inventing a model', () => {
  const h=host(1,1);
  h.run('delete state.project.manual.layer_tracks;delete state.timeline.project.manual.layer_tracks;for(const c of [...state.project.manual.media_clips,...state.project.manual.text_clips])delete c.track_id');
  assert.equal(parity(h).lockIssue, '');
});
test('missing protection helper keeps canonical v1 behavior and fails closed for protected schemas', () => {
  for(const version of [1,2,3]) {const h=host(version,version===1?1:2);h.run('layerMutationIssue=undefined');const r=parity(h);assert.equal(Boolean(r.lockIssue),version>=2);}
});
test('a missing validation helper cannot manufacture a usable paint receipt', () => {
  const h=host();h.run('layerTrackState=undefined');const r=h.run('trackHeaderReadiness(state.timeline.project)');assert.match(r.lockIssue,/unavailable/);assert.equal(r.unlockIssue,r.lockIssue);
});

for (const setup of [
  'state.timeline.project={...state.timeline.project,id:"other"}',
  'state.timeline.project={...state.timeline.project,revision:6}',
  'state.timeline.project={...state.timeline.project,manual:{...state.timeline.project.manual,layer_tracks:structuredCloneForTest(state.project.manual.layer_tracks)}}',
]) test(`paint rejects mismatched timeline identity: ${setup}`, () => {
  const h=host();h.run('globalThis.structuredCloneForTest=v=>JSON.parse(JSON.stringify(v));'+setup);
  const r=h.run('trackHeaderReadiness(state.timeline.project)');assert.match(r.lockIssue,/timeline changed/);assert.equal(h.counts.validate,0);
});
test('an older timeline object is not accepted even with the same project identity', () => {
  const h=host();h.run('globalThis.oldView=state.timeline.project;state.timeline.project={...oldView}');
  assert.match(h.run('trackHeaderReadiness(oldView).lockIssue'),/timeline changed/);
});
for (const change of [
  'state.project={...state.project}',
  'state.projectViewToken++',
  'state.project.revision++',
  'state.timeline.project={...state.timeline.project}',
  'state.project.manual.layer_tracks={...state.project.manual.layer_tracks}',
]) test(`synchronous consumer reentry invalidates receipt: ${change}`, () => {
  const h=host();h.run(`explicitPendingDraft=()=>{${change};return null;}`);
  const r=h.run('trackHeaderReadiness(state.timeline.project)');assert.match(r.lockIssue,/timeline changed/);assert.equal(r.unlockIssue,r.lockIssue);
});

test('199 saved headers need one host model validation, not one per row', () => {
  const h=host(3,2,199), before=h.run('JSON.stringify(state.project)');
  const r=h.run('trackHeaderReadiness(state.timeline.project)');
  assert.equal(r.lockIssue,'');assert.deepEqual(h.counts,{validate:1,mutation:0,explicit:1,busy:1,writes:0});
  assert.equal(h.run('JSON.stringify(state.project)'),before);
  for(let i=0;i<199;i++) assert.equal(r.lockIssue,'');
  assert.equal(h.counts.validate,1);
});
test('each paint samples current state anew with no persistent cache', () => {
  const h=host(3,2,199);
  assert.equal(h.run('trackHeaderReadiness(state.timeline.project).lockIssue'),'');
  h.run('state.manualEditBusy=true');assert.match(h.run('trackHeaderReadiness(state.timeline.project).lockIssue'),/Wait/);
  h.run('state.manualEditBusy=false;state.project.manual.layer_tracks.tracks[150].audio.muted="bad"');
  assert.match(h.run('trackHeaderReadiness(state.timeline.project).lockIssue'),/invalid/);
  assert.equal(h.counts.validate,3);assert.equal(h.counts.writes,0);
});
test('a previously permissive paint receipt cannot authorize a later busy action', () => {
  const h=host();h.run('globalThis.receipt=trackHeaderReadiness(state.timeline.project);state.manualEditBusy=true');
  assert.equal(h.run('receipt.lockIssue'),'');assert.match(h.run('trackLockIssue(tid(0),true)'),/Wait/);
});
test('new protected local draft after painting is freshly checked by the direct callback', () => {
  const h=host();h.run('trackHeaderReadiness(state.timeline.project);explicitPendingDraft=()=>({detail:"Retain unsaved text."})');
  assert.match(h.run('trackLockIssue(tid(0),true)'),/unsaved text/);assert.equal(h.run('trackLockIssue(tid(1),false)'),'');
});
test('new malformed saved state after painting cannot use old readiness', () => {
  const h=host(3,2);h.run('trackHeaderReadiness(state.timeline.project);state.project.manual.layer_tracks.tracks[2].audio.muted=null');
  assert.match(h.run('trackLockIssue(tid(1),false)'),/invalid/);
});
test('paint factory is additive wiring only; no stored receipt or action admission dependency', () => {
  assert.match(raw,/onTrackManage: openLayerTrackManager, trackLockIssue, trackHeaderReadiness,/);
  const body=raw.slice(raw.indexOf('function trackHeaderReadiness('),raw.indexOf('function renderLayerTrackControls('));
  assert.doesNotMatch(body,/\bawait\b|\bapi\(|createLayerMutationPlanner\(|layerMutationIssue\(|trackLockIssue\(|state\.[\w.]+\s*=(?!=)/);
  assert.equal((body.match(/layerTrackState\(saved\)/g)||[]).length,1);
});

const timelineContext = vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(root,'web/timeline.js'),'utf8').replace(/^export /gm,'')+';globalThis.T=TimelineView;',timelineContext);
const scheduleDrawSource = timelineContext.T.prototype.scheduleDraw.toString();
function pausedHost() {
  const h=host();
  h.run(`
    globalThis.frames=[];globalThis.paints=[];globalThis.focusCalls=0;
    requestAnimationFrame=callback=>{frames.push(callback);return frames.length;};
    state.timeline.raf=null;
    state.timeline.scheduleDraw=({${scheduleDrawSource}}).scheduleDraw;
    state.timeline.draw=()=>paints.push(trackHeaderReadiness(state.timeline.project));
    renderLayerTrackControls=()=>{};selectedLayerGroupIds=()=>[];
    state.timeline.playhead=1.25;state.timeline.mediaSelection=mid(0);
  `);
  return h;
}
test('paused draft readiness refresh schedules one existing draw before the optional save-status node', () => {
  const h=pausedHost(), before=h.run('JSON.stringify(state.project)');
  h.run('explicitPendingDraft=()=>({detail:"Correct the track level number."});renderProjectSaveState()');
  assert.equal(h.run('frames.length'),1);assert.equal(h.run('paints.length'),0);
  h.run('frames.shift()()');assert.match(h.run('paints[0].lockIssue'),/track level number/);
  assert.equal(h.run('paints[0].unlockIssue'),'');assert.equal(h.run('frames.length'),0);
  assert.equal(h.run('JSON.stringify(state.project)'),before);
  assert.equal(h.run('state.timeline.playhead'),1.25);assert.equal(h.run('state.timeline.mediaSelection'),h.run('mid(0)'));
  assert.equal(h.counts.writes,0);
});
test('repeated save-readiness notifications coalesce without replacing owned post-draw focus', () => {
  const h=pausedHost();
  h.run('state.timeline.scheduleDraw(()=>focusCalls++);renderProjectSaveState();renderProjectSaveState();renderProjectSaveState()');
  assert.equal(h.run('frames.length'),1);h.run('frames.shift()()');
  assert.equal(h.run('paints.length'),1);assert.equal(h.run('focusCalls'),1);assert.equal(h.run('frames.length'),0);
});
test('paused cancellation updates readiness at the next paint, with no persistent snapshot or new loop', () => {
  const h=pausedHost();h.run('explicitPendingDraft=()=>({detail:"Keep draft"});renderProjectSaveState();frames.shift()()');
  assert.match(h.run('paints[0].lockIssue'),/Keep draft/);
  h.run('explicitPendingDraft=()=>null;renderProjectSaveState();frames.shift()()');
  assert.equal(h.run('paints[1].lockIssue'),'');assert.equal(h.run('frames.length'),0);
  assert.equal(h.counts.writes,0);
});
test('save status remains safe before the main timeline exists', () => {
  const h=pausedHost();h.run('state.timeline=null;renderProjectSaveState()');assert.equal(h.run('frames.length'),0);assert.equal(h.counts.writes,0);
});
