const test = require('node:test'), assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const app = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm,'')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = s => JSON.parse(JSON.stringify(s));
function setup() {
  const calls=[], frames=new Map(); let seq=0;
  const ctx=vm.createContext({console,document:{querySelectorAll:()=>[]},calls,
    requestAnimationFrame: cb => { frames.set(++seq,cb); return seq; }, cancelAnimationFrame:id=>frames.delete(id)});
  const run=s=>vm.runInContext(s,ctx);
  run(app);
  run(`state.studio.open=true;elements.resultPanel={hidden:false};elements.playButton={disabled:false};
    state.project={id:'p',revision:3,sources:{A:{duration:5}},draft:{},editor_sequence:{duration:5,sequence:{duration:5},source_tracks:{A:[],B:[]}}};
    state.timeline={project:{id:'p',revision:3},selection:{start:1,end:5}};
    state.manualSelection={start:1,end:5};state.projectViewToken=7;
    globalThis.isBusy=false;foregroundBusy=()=>isBusy;state.preview.mode='edit';`);
  return {run,get calls(){return structuredClone(calls);},frames};
}
test('only a current edit-clock selection with matching project/revision is available', () => {
  const {run}=setup();const s=plain(run('rangeAuditionSnapshot()'));
  assert.equal(s.editor,true);assert.equal(s.start,1);assert.equal(s.end,5);assert.equal(s.view,7);
  assert.equal(run("state.timeline.project.revision=2;rangeAuditionSnapshot().editor"),false);
  assert.equal(run("state.timeline.project.revision=3;state.timeline.project.id='other';rangeAuditionSnapshot().editor"),false);
  assert.equal(run("state.timeline.project.id='p';elements.resultPanel.hidden=true;rangeAuditionSnapshot().editor"),false);
});
test('stale host range, occurrence, source mode, pending time entry and native preview readiness remain distinct', () => {
  const {run}=setup();assert.equal(run('state.timeline.selection={start:1,end:4};rangeAuditionSnapshot().start'),null);
  assert.equal(run('state.timeline.mediaSelection="clip";rangeAuditionSnapshot().occurrence'),true);
  assert.equal(run('state.timeline.mediaSelection=null;state.timeline.captionSelection="caption";rangeAuditionSnapshot().occurrence'),true);
  assert.equal(run('state.preview.mode="source";rangeAuditionSnapshot().editMode'),false);
  assert.equal(run('elements.timelineRangeForm={hidden:false,dataset:{dirty:"true"}};rangeAuditionSnapshot().dirtyRange'),true);
  assert.equal(run('elements.playButton.disabled=true;rangeAuditionSnapshot().busy'),true);
  assert.equal(run('elements.playButton.disabled=false;isBusy=true;rangeAuditionSnapshot().busy'),true);
});
function clockHarness() {
  const h=setup();h.run(`state.preview.clock={playing:true,time(){return 5;}};
    state.preview.playing=true; playbackProject=()=>({draft:{keep_ranges:[{start:0,end:5}]}});
    previewUsesIndependentTracks=()=>true;independentPreviewClock=()=>state.preview.clock;timelineDuration=()=>5;
    const directSeek=seekPreview; seekPreview=(...args)=>calls.push(['seek',...args]);pauseAllMedia=()=>{calls.push(['pause']);state.preview.playing=false;};
    syncSecondaryPreview=updatePreviewUI=publishPreviewPlayhead=()=>{throw Error('Unexpected presentation before routing transport');};`);
  return h;
}
test('looping to zero wins over native end-of-project, updates via the shared seek and schedules only one tick', () => {
  const h=clockHarness();
  h.run('state.rangeAudition={next:t=>t===5?0:null};tickIndependentPreview();');
  assert.deepEqual(h.calls,[['seek',0,undefined,true]]);assert.equal(h.frames.size,1);
  h.run('tickIndependentPreview();');assert.equal(h.frames.size,1);assert.equal(h.calls.length,2);
});
test('buffering holds the timeline without resubmitting a native seek or rendering an outside frame', () => {
  const h=clockHarness();h.run("state.preview.clock.seek=t=>{calls.push(['clock',t]);return t};state.rangeAudition={next:()=>({at:2,hold:true})};tickIndependentPreview();");
  assert.deepEqual(h.calls,[['clock',2]]);assert.equal(h.frames.size,1);
});
test('readiness only waits for actually displayed or audible source players and current imported layers', () => {
  const h=setup();h.run(`elements.previewA={src:'a',tagName:'VIDEO',hidden:false,muted:true,readyState:2};
    elements.previewB={src:'b',tagName:'VIDEO',hidden:true,muted:true,readyState:0};
    globalThis.audio={tagName:'AUDIO',readyState:1},globalThisImage={tagName:'IMG',complete:true,naturalWidth:32};
    state.mediaStudio={players:new Map([['a',{element:audio}],['i',{element:globalThisImage}]])};`);
  assert.equal(h.run('rangeAuditionMediaReady()'),false);assert.equal(h.run('audio.readyState=2;rangeAuditionMediaReady()'),true);
  assert.equal(h.run('audio.seeking=true;rangeAuditionMediaReady()'),false);
  assert.equal(h.run('audio.seeking=false;audio.error={code:3};rangeAuditionMediaReady()'),null);
  assert.equal(h.run('audio.error=null;globalThisImage.naturalWidth=0;rangeAuditionMediaReady()'),null);
  assert.equal(h.run('globalThisImage.naturalWidth=32;globalThisImage.complete=false;rangeAuditionMediaReady()'),false);
  assert.equal(h.run("elements.previewA.hidden=true;state.mediaStudio.players.clear();rangeAuditionMediaReady()"),true);
});
test('revoked loop pauses without displaying a stale boundary or scheduling playback', () => {
  const h=clockHarness();h.run('state.rangeAudition={next:()=>false};tickIndependentPreview();');
  assert.deepEqual(h.calls,[['pause']]);assert.equal(h.frames.size,0);
});
test('ordinary playback still pauses and seeks to the exact project end, with no loop ticket', () => {
  const h=clockHarness();h.run('state.rangeAudition={next:()=>null};tickIndependentPreview();');
  assert.deepEqual(h.calls,[['pause'],['seek',5]]);assert.equal(h.frames.size,0);
});
test('only the dedicated wrap can retain a loop through the shared seek path', () => {
  const h=setup();h.run(`invalidateEditingPositionReturn=()=>{};
    playbackProject=()=>state.project;timelineDuration=()=>5;previewUsesIndependentTracks=()=>true;
    independentPreviewClock=()=>({seek:t=>calls.push(['clock',t])});
    state.rangeAudition={clear:()=>calls.push(['clear'])};
    syncSecondaryPreview=t=>calls.push(['media',t,state.preview.seeking]);
    updatePreviewUI=t=>calls.push(['ui',t]);publishPreviewPlayhead=t=>calls.push(['timeline',t]);
    seekPreview(1,undefined,true);seekPreview(3);`);
  assert.deepEqual(h.calls,[['clock',1],['media',1,true],['ui',1],['timeline',1],
    ['clear'],['clock',3],['media',3,true],['ui',3],['timeline',3]]);
});
test('all media pause clears the owned loop even when a native media node is exempt', () => {
  const h=setup();h.run(`state.rangeAudition={clear:()=>calls.push(['clear'])};state.mediaStudio={pause:()=>calls.push(['layers paused'])};
    state.preview.clock={pause:()=>calls.push(['clock paused'])};setPreviewPlaying=b=>calls.push(['playing',b]);pauseAllMedia({});`);
  assert.deepEqual(h.calls,[['clear'],['layers paused'],['clock paused'],['playing',false]]);
});
