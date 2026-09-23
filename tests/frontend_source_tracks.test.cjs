const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const helper = fs.readFileSync(path.join(__dirname, '../web/source-tracks.js'), 'utf8').replace(/^export /gm, '');
const source = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace(/\nboot\(\)\.catch\(\(error\) => \{[\s\S]*?\n\}\);/, '');
const plain = value => JSON.parse(JSON.stringify(value));

function harness() {
  let now = 0, serial = 0;
  const frames = new Map();
  const media = [];
  function element() {
    const classes = new Set();
    return { src: 'fixture.mp4', paused: true, currentTime: 0, hidden: false, dataset: {},
      style: { setProperty(key, value) { this[key] = value; } },
      classList: { add(...keys) { keys.forEach(k => classes.add(k)); }, remove(...keys) { keys.forEach(k => classes.delete(k)); }, toggle(k, on) { on ? classes.add(k) : classes.delete(k); } },
      querySelector() { return this; }, setAttribute() {},
      pause() { this.paused = true; }, play() { this.paused = false; return Promise.resolve(); } };
  }
  const context = vm.createContext({ console, dictionaries: { en: {} }, document: { querySelectorAll: () => media, querySelector: () => null },
    window: {}, setTimeout, clearTimeout, element, performance: { now: () => now },
    requestAnimationFrame: fn => { frames.set(++serial, fn); return serial; },
    cancelAnimationFrame: id => frames.delete(id) });
  const run = code => vm.runInContext(code, context);
  run(helper);
  run(fs.readFileSync(path.join(__dirname, '../web/keyboard.js'), 'utf8').replace(/^export /gm, ''));
  run(fs.readFileSync(path.join(__dirname, '../web/timeline.js'), 'utf8').replace(/^export /gm, ''));
  run(source);
  run(`
    for (const id of ['previewA','previewB','previewPaneA','previewPaneB','previewStage','cameraBadge','playButton','previewPlay','resultPanel','previewCaption']) elements[id] = element();
    elements.resultPanel.hidden = false;
    state.project = {id:'test', sources:{A:{duration:12,has_audio:true},B:{duration:20,has_audio:true}},
      manual:{source_tracks:{A:[{id:'a1',start:0,end:2,source_start:5},{id:'a2',start:8,end:12,source_start:1}],
        B:[{id:'b1',start:2,end:5,source_start:8}]}},
      draft:{keep_ranges:[{start:0,end:12}],camera_plan:[{start:0,end:12,camera:'stacked'}],cuts:[]}};
    state.studio.open=true; state.preview.mode='source';
    globalThis.mixer = {audioSlot:'A',syncOffset:0,screenSlot:'A',cameraSlot:'B',primaryRole:'screen',firstSlot:'B',stackFit:'contain'};
    sourceMixerSettings=()=>mixer;
    applyPreviewPipGeometry=refreshEmbeddedCropControls=applyCompositionCrop=()=>{};
    globalThis.uiTimes=[]; globalThis.playheads=[]; globalThis.messages=[];
    updatePreviewUI=time=>uiTimes.push(time);
    state.timeline={playhead:0,setPlayhead(time){this.playhead=time;playheads.push(time);}};
    toast=message=>messages.push(message);
  `);
  media.push(run('elements.previewA'), run('elements.previewB'));
  return {run, frames, async advance(milliseconds) {
    now += milliseconds;
    const pending = [...frames.values()]; frames.clear(); pending.forEach(fn => fn(now));
    await Promise.resolve(); await Promise.resolve();
  }};
}

test('implicit tracks preserve sync offsets and negative B starts without mutation', () => {
  const {run} = harness();
  run('delete state.project.manual.source_tracks; mixer.syncOffset=3;');
  assert.equal(run('hasSourceTracks(state.project)'), false);
  assert.deepEqual(plain(run('trackClips(state.project,"B",3)')), [{id:'B:base',start:3,end:12,source_start:0}]);
  assert.deepEqual(plain(run('trackClips(state.project,"B",-4)')), [{id:'B:base',start:0,end:12,source_start:4}]);
  assert.equal(run('trackAt(state.project,"B",5,3).sourceTime'), 2);
  assert.equal(run('trackAt(state.project,"B",2,3)'), null);
  assert.equal(run('state.project.manual.source_tracks'), undefined);
});

test('explicit empty tracks stay empty; moved clips map timeline to source time', () => {
  const {run} = harness();
  assert.equal(run('trackAt(state.project,"A",1).sourceTime'), 6);
  assert.equal(run('trackAt(state.project,"A",2)'), null);
  assert.equal(run('trackAt(state.project,"A",8).sourceTime'), 1);
  run('state.project.manual.source_tracks.B=[];');
  assert.equal(run('hasSourceTracks(state.project)'), true);
  assert.deepEqual(plain(run('trackClips(state.project,"B")')), []);
});

test('independent clock pauses and seeks without depending on either media clock', async () => {
  const h = harness();
  h.run('globalThis.clock=new SourceTimelineClock(); clock.seek(4); clock.play();');
  await h.advance(2500);
  assert.equal(h.run('clock.time()'), 6.5);
  h.run('clock.pause();'); await h.advance(2000);
  assert.equal(h.run('clock.time()'), 6.5);
  h.run('clock.seek(1); clock.play();'); await h.advance(500);
  assert.equal(h.run('clock.time()'), 1.5);
});

test('playback crosses A gaps, both-track gaps and returns to A with local timestamps', async () => {
  const h = harness();
  h.run('seekPreview(1);');
  assert.equal(h.run('elements.previewA.currentTime'), 6);
  await h.run('playPreview()'); await h.advance(1500);
  assert.equal(h.run('previewTimelineTime()'), 2.5);
  assert.equal(h.run('elements.previewA.hidden && elements.previewA.paused'), true);
  assert.equal(h.run('elements.previewB.hidden'), false);
  assert.equal(h.run('elements.previewB.currentTime'), 8.5);
  assert.equal(h.run('elements.previewB.paused'), false);
  assert.equal(h.run('elements.previewB.muted'), true); // A was chosen for audio; do not switch speakers.
  await h.advance(3500);
  assert.equal(h.run('elements.previewA.hidden && elements.previewB.hidden'), true);
  assert.equal(h.run('state.preview.playing'), true);
  assert.equal(h.run('elements.cameraBadge.textContent'), 'GAP');
  await h.advance(2500);
  assert.equal(h.run('elements.previewA.currentTime'), 1.5);
  assert.equal(h.run('elements.previewA.paused'), false);
  assert.equal(h.run('elements.previewA.hidden'), false);
  await h.advance(4000);
  assert.equal(h.run('previewTimelineTime()'), 12);
  assert.equal(h.run('state.preview.playing'), false);
  assert.equal(h.run('elements.previewA.paused && elements.previewB.paused'), true);
  assert.equal(h.frames.size, 0);
});

test('edited playback skips global cuts; full source and paused seeks can inspect them', async () => {
  const h = harness();
  h.run(`state.project.draft.keep_ranges=[{start:0,end:2},{start:8,end:10}];
    state.project.draft.cuts=[{start:2,end:8},{start:10,end:12}]; state.preview.mode='edit'; seekPreview(3);`);
  assert.equal(h.run('previewTimelineTime()'), 3);
  await h.run('playPreview()');
  assert.equal(h.run('previewTimelineTime()'), 8);
  await h.advance(2200);
  assert.equal(h.run('previewTimelineTime()'), 10);
  assert.equal(h.run('state.preview.playing'), false);
  h.run(`state.preview.mode='source'; seekPreview(3);`);
  await h.run('playPreview()'); await h.advance(1000);
  assert.equal(h.run('previewTimelineTime()'), 4);
  assert.equal(h.run('state.preview.playing'), true);
});

test('A ended/pause events do not stop the independent timeline; explicit Pause does', async () => {
  const h = harness();
  h.run('seekPreview(1);'); await h.run('playPreview()');
  h.run('elements.previewA.pause(); stopPreviewPlayback();');
  assert.equal(h.run('state.preview.playing'), true);
  await h.advance(1500);
  h.run('pauseAllMedia();');
  assert.equal(h.run('elements.previewA.paused && elements.previewB.paused'), true);
  await h.advance(3000);
  assert.equal(h.run('previewTimelineTime()'), 2.5);
  assert.equal(h.frames.size, 0);
});

test('late media play promise cannot restart a paused timeline or another project', async () => {
  const h = harness();
  h.run(`seekPreview(3); elements.previewB.play=()=>new Promise(resolve=>{
    globalThis.finishPlay=()=>{elements.previewB.paused=false;resolve();}; });`);
  await h.run('playPreview()');
  h.run('pauseAllMedia(); state.project.id="new-project"; finishPlay();');
  await Promise.resolve(); await Promise.resolve();
  assert.equal(h.run('elements.previewB.paused'), true);
  assert.equal(h.run('state.preview.playing'), false);
});

test('a loading player cancelled at a track gap does not stop the remaining track', async () => {
  const h = harness();
  h.run(`seekPreview(1.9);
    elements.previewA.play=function() {
      this.paused=false;
      return new Promise((resolve,reject)=>{globalThis.rejectPlay=reject;});
    };
    elements.previewA.pause=function() {
      this.paused=true;
      const error=new Error('The play() request was interrupted by a call to pause().');
      error.name='AbortError'; rejectPlay?.(error);
    };`);
  await h.run('playPreview()');
  await h.advance(200);
  assert.equal(h.run('state.preview.playing'), true);
  assert.equal(h.run('elements.previewB.paused'), false);
  assert.equal(h.run('messages.length'), 0);
  await h.advance(200);
  assert.ok(h.run('previewPlaybackTime()') > 2.2);
});

test('an unexpected player failure still stops playback and reports the error', async () => {
  const h = harness();
  h.run(`elements.previewA.play=()=>Promise.reject(new Error('Decoder failed'));`);
  await h.run('playPreview()');
  await h.advance(0);
  assert.equal(h.run('state.preview.playing'), false);
  assert.deepEqual(plain(h.run('messages')), ['Decoder failed']);
});

test('the edit mixer owns audio without repeatedly starting hidden source videos', async () => {
  for (const audioSlot of ['A', 'B']) {
    const h = harness();
    const camera = audioSlot === 'A' ? 'B' : 'A';
    h.run(`state.preview.mode='edit'; mixer.audioSlot='${audioSlot}';
      state.mediaStudio={resumeAudio(){},sync(){},pause(){}};
      state.project.manual.source_tracks.B=[{id:'b',start:0,end:12,source_start:0}];
      state.project.draft.camera_plan=[{start:0,end:12,camera:'${camera}'}];
      globalThis.starts={A:0,B:0};
      for(const slot of ['A','B']) elements['preview'+slot].play=function(){
        starts[slot]++; this.paused=false; return Promise.resolve();
      };`);
    await h.run('playPreview()');
    for (let frame = 0; frame < 3; frame++) await h.advance(16);
    assert.equal(h.run(`starts.${audioSlot}`), 0, 'the hidden audio source is played by the mixer only');
    assert.equal(h.run(`starts.${camera}`), 1, 'visible picture keeps playing without restart');
    assert.equal(h.run('elements.previewA.muted && elements.previewB.muted'), true);
    assert.equal(h.run('state.preview.playing'), true);
  }
});

test('the edit mixer also prevents hidden B audio playback with the original media clock', () => {
  const h = harness();
  h.run(`delete state.project.manual.source_tracks; state.preview.mode='edit'; mixer.audioSlot='B';
    state.mediaStudio={sync(){},pause(){}};
    state.project.draft.camera_plan=[{start:0,end:12,camera:'A'}];
    state.preview.playing=true; elements.previewA.paused=false;
    globalThis.bStarts=0;
    elements.previewB.play=function(){bStarts++;this.paused=false;return Promise.resolve();};
    syncSecondaryPreview(1);`);
  assert.equal(h.run('bStarts'), 0);
  assert.equal(h.run('elements.previewA.muted && elements.previewB.muted'), true);
  h.run(`state.preview.mode='source'; syncSecondaryPreview(1);`);
  assert.equal(h.run('bStarts'), 1, 'Full source retains native source audio playback');
  assert.equal(h.run('elements.previewB.muted'), false);
});

test('audio tail does not show frozen video and does not choose another audio source', () => {
  const h = harness();
  h.run(`state.project.sources.B.video_duration=9; mixer.audioSlot='B'; seekPreview(4);`);
  assert.equal(h.run('elements.previewA.hidden && elements.previewB.hidden'), true);
  assert.equal(h.run('elements.previewB.currentTime'), 10);
  assert.equal(h.run('elements.previewB.muted'), false);
  assert.equal(h.run('elements.previewA.muted'), true);
});

test('captions follow the edited analyzed audio source and disappear in its gaps', () => {
  const h = harness();
  h.run(`state.project.analysis={audio_source:'B',audio_timeline_offset:4,
    transcript:{segments:[{start:12,end:15,text:'Correct speaker',words:[{start:12,end:15,word:'Correct'}]}]}};
    mixer.audioSlot='B'; captionBurnEnabled=()=>true;
    captionSettingsFromControls=()=>({words:4,style:'clean',position:'bottom',scale:100});
    updatePreviewCaption(3);`);
  assert.equal(h.run('elements.previewCaption.textContent'), 'Correct');
  assert.equal(h.run('elements.previewCaption.hidden'), false);
  h.run('updatePreviewCaption(7);');
  assert.equal(h.run('elements.previewCaption.hidden'), true);
  h.run(`mixer.audioSlot='A'; updatePreviewCaption(1);`);
  assert.equal(h.run('elements.previewCaption.hidden'), true);
});

test('wordless captions survive a B-only edit and keep their clipped segment clock', () => {
  const h = harness();
  h.run(`state.project.manual.source_tracks={B:[]};
    state.project.analysis={audio_source:'A',transcript:{segments:[{start:0,end:2,text:'Still here',words:[]}]}};
    captionBurnEnabled=()=>true;
    captionSettingsFromControls=()=>({words:4,style:'clean',position:'bottom',scale:100});
    updatePreviewCaption(1);`);
  assert.equal(h.run('elements.previewCaption.hidden'), false);
  assert.equal(h.run('elements.previewCaption.textContent'), 'Still here');
  h.run('delete state.project.analysis.transcript.segments[0].words; updatePreviewCaption(1);');
  assert.equal(h.run('elements.previewCaption.textContent'), 'Still here');
});

test('boundary caption words use midpoint ownership matching export and hide outside mapped words', () => {
  const h = harness();
  h.run(`state.project.manual.source_tracks.A=[{id:'a',start:0,end:2,source_start:5}];
    state.project.analysis={audio_source:'A',transcript:{segments:[{start:4,end:8,text:'before inside after',words:[
      {start:4,end:5.2,word:'before'},{start:5.2,end:6.6,word:'inside'},{start:6.6,end:7.6,word:'after'}]}]}};
    captionBurnEnabled=()=>true;
    captionSettingsFromControls=()=>({words:4,style:'clean',position:'bottom',scale:100});
    updatePreviewCaption(.5);`);
  assert.equal(h.run('elements.previewCaption.textContent'), 'inside');
  h.run('updatePreviewCaption(.1);');
  assert.equal(h.run('elements.previewCaption.hidden'), true);
  h.run('updatePreviewCaption(1.9);');
  assert.equal(h.run('elements.previewCaption.hidden'), true);
});

function sequenceHarness() {
  const h = harness();
  h.run(`state.preview.mode='edit';
    state.project.editor_sequence={duration:4,sequence:{duration:4,camera_plan:[{start:0,end:4,camera:'stacked'}]},source_tracks:{
      A:[{id:'seqA1',start:0,end:2,source_start:5},{id:'seqA2',start:2,end:4,source_start:1}],
      B:[{id:'seqB',start:0,end:4,source_start:8}]}};`);
  return h;
}

test('Edited cut uses the compact sequence projection and its own media clocks', async () => {
  const h = sequenceHarness();
  h.run('seekPreview(1.5);');
  assert.equal(h.run('previewTimelineTime()'), 1.5);
  assert.equal(h.run('elements.previewA.currentTime'), 6.5);
  assert.equal(h.run('elements.previewB.currentTime'), 9.5);
  await h.run('playPreview()'); await h.advance(1000);
  assert.equal(h.run('previewTimelineTime()'), 2.5);
  assert.equal(h.run('elements.previewA.currentTime'), 1.5);
  assert.equal(h.run('elements.previewB.currentTime'), 10.5);
  assert.equal(h.run('state.timeline.playhead'), 2.5);
  await h.advance(2000);
  assert.equal(h.run('previewTimelineTime()'), 4);
  assert.equal(h.run('state.preview.playing'), false);
  assert.equal(h.run('state.project.manual.source_tracks.A[0].source_start'), 5, 'raw project is not rewritten by viewing');
});

test('Full source auditions original A; timeline remains on edit time across both mode switches', () => {
  const h = sequenceHarness();
  h.run('seekPreview(2.5); setPreviewMode("source");');
  assert.equal(h.run('previewUsesIndependentTracks()'), false);
  assert.equal(h.run('previewPlaybackTime()'), 1.5);
  assert.equal(h.run('previewTimelineTime()'), 2.5);
  assert.equal(h.run('state.timeline.playhead'), 2.5);
  h.run('elements.previewA.currentTime=2; onPreviewTimeUpdate();');
  assert.equal(h.run('state.timeline.playhead'), 3);
  h.run('seekPreview(10); onPreviewTimeUpdate();');
  assert.equal(h.run('previewPlaybackTime()'), 10);
  assert.equal(h.run('previewTimelineTime()'), 3, 'unmapped original footage does not move the edit cursor to raw time');
  assert.equal(h.run('state.timeline.playhead'), 3);
  h.run('setPreviewMode("edit");');
  assert.equal(h.run('previewPlaybackTime()'), 3);
  assert.equal(h.run('elements.previewA.currentTime'), 2);
  assert.equal(h.run('state.preview.playing'), false);
});

test('timeline clicks in Full source map through A clips without changing the playback choice', () => {
  const h = sequenceHarness();
  h.run('setPreviewMode("source"); seekSourcePreview(1.25); onPreviewTimeUpdate();');
  assert.equal(h.run('state.preview.mode'), 'source');
  assert.equal(h.run('elements.previewA.currentTime'), 6.25);
  assert.equal(h.run('previewTimelineTime()'), 1.25);
  h.run('seekSourcePreview(4); onPreviewTimeUpdate();');
  assert.equal(h.run('previewTimelineTime()'), 4, 'exact sequence end remains selected despite half-open source mapping');
  assert.equal(h.run('elements.previewA.currentTime'), 3);
  h.run('setPreviewMode("edit");');
  assert.equal(h.run('previewTimelineTime()'), 4);
});

test('a Full source click in an A gap preserves the edit cursor and explains unavailable original A', () => {
  const h = sequenceHarness();
  h.run(`state.project.editor_sequence.duration=6; state.project.editor_sequence.sequence.duration=6;
    state.project.editor_sequence.source_tracks.A=[{id:'a',start:0,end:2,source_start:5}];
    state.project.editor_sequence.source_tracks.B=[{id:'b',start:0,end:6,source_start:8}];
    seekPreview(1); setPreviewMode('source'); seekSourcePreview(4); onPreviewTimeUpdate();`);
  assert.equal(h.run('elements.previewA.currentTime'), 6);
  assert.equal(h.run('previewTimelineTime()'), 4);
  assert.equal(h.run('state.preview.sourceUnmapped'), true);
  h.run('setPreviewMode("edit");');
  assert.equal(h.run('previewTimelineTime()'), 4);
  assert.equal(h.run('elements.previewA.hidden'), true);
  assert.equal(h.run('elements.previewB.currentTime'), 12);
});

test('extended sequence positions beyond physical A duration are reachable and stop at sequence end', async () => {
  const h = sequenceHarness();
  h.run(`state.project.editor_sequence.duration=18; state.project.editor_sequence.sequence.duration=18;
    state.project.editor_sequence.source_tracks.A=[{id:'a',start:14,end:18,source_start:1}];
    state.project.editor_sequence.source_tracks.B=[{id:'b',start:0,end:18,source_start:0}];
    seekPreview(16);`);
  assert.equal(h.run('elements.previewA.currentTime'), 3);
  assert.equal(h.run('previewTimelineTime()'), 16);
  await h.run('playPreview()'); await h.advance(3000);
  assert.equal(h.run('previewTimelineTime()'), 18);
  assert.equal(h.run('state.preview.playing'), false);
});

test('caption preview follows active playback clock while transcript selection always maps the edit', () => {
  const h = sequenceHarness();
  h.run(`state.project.analysis={audio_source:'A',transcript:{segments:[
      {id:'early',start:1,end:3,text:'Early original',words:[]},{id:'late',start:5,end:7,text:'Late original',words:[]}]}};
    captionBurnEnabled=()=>true;
    captionSettingsFromControls=()=>({words:4,style:'clean',position:'bottom',scale:100});
    seekPreview(1); updatePreviewCaption(previewPlaybackTime());`);
  assert.equal(h.run('elements.previewCaption.textContent'), 'Late original');
  assert.deepEqual(plain(h.run('transcriptTimelineMapping(5,7).ranges')), [{start:0,end:2}]);
  h.run('setPreviewMode("source"); seekPreview(1); updatePreviewCaption(previewPlaybackTime());');
  assert.equal(h.run('elements.previewCaption.textContent'), 'Early original');
  assert.deepEqual(plain(h.run('transcriptTimelineMapping(5,7).ranges')), [{start:0,end:2}]);
});

test('Full source frame stepping moves original frames even outside the compact edit', () => {
  const h = sequenceHarness();
  h.run(`setPreviewMode('source'); seekPreview(10); state.keyboardProfile='cutroom';
    handleEditorShortcut({key:'ArrowRight',preventDefault(){}});`);
  assert.ok(Math.abs(h.run('elements.previewA.currentTime') - (10 + 1/30)) < 1e-9);
  assert.equal(h.run('state.preview.mode'), 'source');
});

test('embedded camera virtual B follows the same A source clip across compact edit joins', async () => {
  const h = sequenceHarness();
  h.run(`delete state.project.sources.B;
    state.project.sources.A.width=1920; state.project.sources.A.height=1080;
    state.project.editor_sequence.sequence.camera_plan=[{start:0,end:4,camera:'embedded_stack'}];
    embeddedLayoutConfirmed=()=>true;
    embeddedCameraCandidate=()=>({x:0,y:0,w:1,h:.3,content_region:{x:0,y:.3,w:1,h:.7},content_focus:{x:.5,y:.5}});
    elements.previewStage.dataset.aspect='9:16'; seekPreview(1.5);`);
  assert.equal(h.run('elements.previewB.currentTime'), 6.5);
  assert.equal(h.run('elements.previewB.hidden'), false);
  assert.equal(h.run('elements.previewB.muted'), true);
  await h.run('playPreview()'); await h.advance(1000);
  assert.equal(h.run('elements.previewA.currentTime'), 1.5);
  assert.equal(h.run('elements.previewB.currentTime'), 1.5);
  assert.equal(h.run('elements.previewB.paused'), false, 'late play guard recognizes virtual B as A footage');
  h.run('pauseAllMedia();');
  assert.equal(h.run('elements.previewA.paused && elements.previewB.paused'), true);
});
